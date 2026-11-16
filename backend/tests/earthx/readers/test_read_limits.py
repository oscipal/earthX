"""The cap per host on the files a process reads (M5-36 §5.2): ``readers.limits`` and its use in ``CogReader``.

The counter is set per process; every test sets its own and takes it away again. The files are not opened: a
reader's open is replaced where a test only asks whether a slot is held and given back.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
import rasterio

from earthx.gateway import Policy, ReadSlots
from earthx.readers import limits
from earthx.readers.cog import AssetPath, CogReader
from earthx.readers.limits import carry_held, hold_hosts, limit_reads, read_slot

HOST = "bucket.example.org"
OTHER = "other.example.org"
pytestmark = pytest.mark.anyio


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


async def test_slots_held_in_the_event_loop_cover_the_readers_of_the_request(slots: ReadSlots) -> None:
    async with hold_hosts([OTHER, HOST, None, HOST]):
        assert (held(slots), held(slots, OTHER)) == (1, 1)
        # The thread pool of a route copies the context: its readers take no second slot and do not wait.
        await asyncio.wait_for(asyncio.to_thread(lambda: read_slot(HOST).__enter__()), timeout=2)
        assert held(slots) == 1
    assert (held(slots), held(slots, OTHER)) == (0, 0)


async def test_threads_of_their_own_read_under_the_held_slots_only_when_carried(slots: ReadSlots) -> None:
    def read() -> int:
        with read_slot(HOST):
            return held(slots)

    with ThreadPoolExecutor(max_workers=2) as pool:
        async with hold_hosts([HOST]):
            assert pool.submit(carry_held(read)).result(timeout=2) == 1
            # Without carrying, a thread of its own waits for the slot the request holds.
            waiting = pool.submit(read)
            await asyncio.sleep(0.05)
            assert not waiting.done()
        assert waiting.result(timeout=2) == 1


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
