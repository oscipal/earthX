"""The cap per host on the files a process reads (M5-36 §5.2): ``readers.limits`` and its use in ``CogReader``.

The counter is set per process; every test sets its own and takes it away again. The files are not opened: a
reader's open is replaced where a test only asks whether a slot is held and given back.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
import rasterio

from earthx.gateway import Policy, ReadSlots
from earthx.readers import limits
from earthx.readers.cog import AssetPath, CogReader
from earthx.readers.limits import limit_reads, read_slot, read_slots, uncounted

HOST = "bucket.example.org"
OTHER = "other.example.org"


@pytest.fixture
def slots():
    counter = ReadSlots(Policy(allowed_hosts=frozenset({HOST, OTHER}), max_connections_per_host=1))
    limit_reads(counter)
    yield counter
    limit_reads(None)


def held(counter: ReadSlots, host: str = HOST) -> int:
    state = counter._hosts.get(host)
    return 0 if state is None else state.held


def test_without_a_counter_nothing_is_counted() -> None:
    limit_reads(None)
    with read_slot(HOST):
        assert limits.process_slots() is None


def test_a_file_on_disk_and_a_host_off_the_allowlist_take_no_slot(slots: ReadSlots) -> None:
    with read_slot(None), read_slot("objectstore.internal.example"):
        assert slots._hosts == {}


def test_a_second_file_of_the_same_host_in_one_thread_takes_no_second_slot(slots: ReadSlots) -> None:
    with read_slot(HOST), read_slot(HOST):
        assert held(slots) == 1
    assert held(slots) == 0


def test_readers_closed_out_of_order_give_every_slot_back(slots: ReadSlots) -> None:
    first, second = read_slot(HOST), read_slot(OTHER)
    first.__enter__()
    second.__enter__()
    first.__exit__(None, None, None)
    with read_slot(HOST):  # the host is free again for this thread, and counted again
        assert held(slots) == 1
    second.__exit__(None, None, None)
    assert (held(slots), held(slots, OTHER)) == (0, 0)


def test_threads_never_hold_more_than_the_cap(slots: ReadSlots) -> None:
    inside, most, lock = [0], [0], threading.Lock()

    def read() -> None:
        with read_slot(HOST):
            with lock:
                inside[0] += 1
                most[0] = max(most[0], inside[0])
            threading.Event().wait(0.005)
            with lock:
                inside[0] -= 1

    with ThreadPoolExecutor(max_workers=6) as pool:
        for future in [pool.submit(read) for _ in range(12)]:
            future.result(timeout=5)
    assert most[0] == 1 and held(slots) == 0


def test_files_opened_uncounted_take_their_slot_where_they_are_read(slots: ReadSlots) -> None:
    # The first scene of a mosaic tile with steps: opened in the route's thread, read in a thread of the tile.
    with uncounted([HOST, None]), read_slot(HOST):
        assert held(slots) == 0
    with ThreadPoolExecutor(max_workers=2) as pool:

        def read() -> int:
            with read_slots([OTHER, HOST, None, HOST]):
                return held(slots) + held(slots, OTHER)

        assert [future.result(timeout=2) for future in [pool.submit(read), pool.submit(read)]] == [2, 2]
    assert (held(slots), held(slots, OTHER)) == (0, 0)


def test_a_reader_holds_its_slot_from_open_to_close_and_gives_it_back_when_the_open_fails(
    slots: ReadSlots, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = AssetPath(f"/vsicurl/https://{HOST}/scene.tif", dataset_id="d", item_id="i", asset="a")
    seen = []

    def refuse(*_args, **_kwargs):
        seen.append(held(slots))
        raise rasterio.errors.RasterioIOError("synthetic: the source did not answer")

    monkeypatch.setattr("earthx.readers.cog.rasterio.open", refuse)
    with pytest.raises(rasterio.errors.RasterioIOError):
        CogReader(path)
    assert seen == [1] and held(slots) == 0


@pytest.mark.parametrize("endpoint", ["http://objectstore:9000", "http://127.0.0.1:9000"])
def test_a_result_of_the_object_store_is_read_without_a_slot(
    slots: ReadSlots, monkeypatch: pytest.MonkeyPatch, endpoint: str
) -> None:
    # The store's endpoint need not be a name the gateway accepts (adr/0015 §14c); it is no source either.
    path = AssetPath(f"/vsicurl/{endpoint}/results/r/out.tif", dataset_id="", item_id="", asset="out.tif")
    seen = []

    def refuse(*_args, **_kwargs):
        seen.append(dict(slots._hosts))
        raise rasterio.errors.RasterioIOError("synthetic")

    monkeypatch.setattr("earthx.readers.cog.rasterio.open", refuse)
    with pytest.raises(rasterio.errors.RasterioIOError):
        CogReader(path)
    assert seen == [{}]
