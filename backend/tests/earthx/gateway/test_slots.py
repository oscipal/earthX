"""`ReadSlots`: the per-host limit on GDAL readers in one process (DS-03 plan §6.9 F2d, adr/0005 §6)."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from earthx.gateway import Policy, ReadSlots, UrlRejected

HOST = "bucket.example.org"
OTHER = "other.example.org"


def slots(limit: int = 2) -> ReadSlots:
    return ReadSlots(Policy(allowed_hosts=frozenset({HOST, OTHER}), max_connections_per_host=limit))


class Counter:
    """How many readers are inside at once, and the most there ever were."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.now = 0
        self.peak = 0

    def enter(self) -> None:
        with self._lock:
            self.now += 1
            self.peak = max(self.peak, self.now)

    def leave(self) -> None:
        with self._lock:
            self.now -= 1


def _read(read_slots: ReadSlots, host: str, counter: Counter) -> None:
    with read_slots.slot(host):
        counter.enter()
        time.sleep(0.02)
        counter.leave()


class TestTheLimit:
    def test_many_threads_on_one_host_never_exceed_the_limit(self) -> None:
        read_slots, counter = slots(2), Counter()
        with ThreadPoolExecutor(max_workers=12) as pool:
            for future in [pool.submit(_read, read_slots, HOST, counter) for _ in range(24)]:
                future.result()
        assert 1 <= counter.peak <= 2 and counter.now == 0

    def test_the_default_policy_limit_is_six(self) -> None:
        # Six readers must be inside at once to pass the barrier, so a lower limit fails it; a seventh may not join.
        read_slots, counter = ReadSlots(Policy(allowed_hosts=frozenset({HOST}))), Counter()
        together = threading.Barrier(6)

        def read() -> None:
            with read_slots.slot(HOST):
                counter.enter()
                together.wait(timeout=5)
                time.sleep(0.02)
                counter.leave()

        with ThreadPoolExecutor(max_workers=12) as pool:
            for future in [pool.submit(read) for _ in range(12)]:
                future.result()
        assert counter.peak == 6

    def test_a_third_reader_waits_until_a_slot_is_free(self) -> None:
        read_slots = slots(2)
        release, inside, started = threading.Event(), threading.Barrier(3), threading.Event()

        def hold() -> None:
            with read_slots.slot(HOST):
                inside.wait(timeout=5)
                release.wait(timeout=5)

        def third() -> None:
            with read_slots.slot(HOST):
                started.set()

        holders = [threading.Thread(target=hold) for _ in range(2)]
        for thread in holders:
            thread.start()
        inside.wait(timeout=5)
        waiting = threading.Thread(target=third)
        waiting.start()
        assert not started.wait(timeout=0.1)
        release.set()
        assert started.wait(timeout=5)
        for thread in (*holders, waiting):
            thread.join(timeout=5)

    def test_a_slot_comes_back_after_an_error(self) -> None:
        read_slots = slots(1)
        with pytest.raises(RuntimeError), read_slots.slot(HOST):
            raise RuntimeError("the read failed")
        acquired = threading.Event()

        def again() -> None:
            with read_slots.slot(HOST):
                acquired.set()

        thread = threading.Thread(target=again)
        thread.start()
        assert acquired.wait(timeout=5)
        thread.join(timeout=5)


class TestTheHosts:
    def test_another_host_is_independent(self) -> None:
        read_slots = slots(1)
        entered = threading.Event()
        with read_slots.slot(HOST):

            def other() -> None:
                with read_slots.slot(OTHER):
                    entered.set()

            thread = threading.Thread(target=other)
            thread.start()
            assert entered.wait(timeout=5)
            thread.join(timeout=5)

    @pytest.mark.parametrize("spelling", ["BUCKET.Example.org", "bucket.example.org.", "  bucket.example.org "])
    def test_the_spelling_of_a_host_shares_its_slot(self, spelling: str) -> None:
        read_slots, counter = slots(1), Counter()
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(_read, read_slots, HOST if index % 2 else spelling, counter) for index in range(8)]
            for future in futures:
                future.result()
        assert counter.peak == 1

    def test_the_semaphore_is_made_once_per_host_under_a_race(self) -> None:
        read_slots, counter = slots(3), Counter()
        barrier = threading.Barrier(8)

        def read() -> None:
            barrier.wait(timeout=5)
            _read(read_slots, HOST, counter)

        with ThreadPoolExecutor(max_workers=8) as pool:
            for future in [pool.submit(read) for _ in range(8)]:
                future.result()
        assert counter.peak <= 3


class TestMisuse:
    @pytest.mark.parametrize("host", ["", "127.0.0.1", "[::1]", "no-dot"])
    def test_a_host_that_is_no_name_is_refused(self, host: str) -> None:
        with pytest.raises(UrlRejected), slots().slot(host):
            pytest.fail("the block must not run")

    def test_a_host_off_the_allowlist_gets_no_slot(self) -> None:
        with pytest.raises(UrlRejected, match="allowlist"), slots().slot("elsewhere.example.org"):
            pytest.fail("the block must not run")

    @pytest.mark.parametrize("limit", [0, -1])
    def test_a_limit_below_one_is_refused(self, limit: int) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            slots(limit)
