"""One cap per host and process, for threads and event loops together (M5-36 §4.1).

`ReadSlots` was the cap of GDAL readers only; the gateway's client kept a semaphore of its own per object. These
tests hold the one counter both sides now share: the cap per host from ``Policy.host_connections``, the order of
waiters across both sides, a cancelled waiter, and two gateways of one process on one counter.
"""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from earthx.gateway import Policy, ReadSlots, instance_share, source_instances_from_env
from earthx.gateway.client import Gateway
from earthx.gateway.slots import _Waiter

HOST = "bucket.example.org"
OTHER = "other.example.org"
pytestmark = pytest.mark.anyio


def policy(**limits: object) -> Policy:
    return Policy(allowed_hosts=frozenset({HOST, OTHER}), **limits)  # type: ignore[arg-type]


class Peak:
    """How many holders are inside at once, and the most there ever were; safe from threads and a loop."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.now = 0
        self.most = 0

    def enter(self) -> None:
        with self._lock:
            self.now += 1
            self.most = max(self.most, self.now)

    def leave(self) -> None:
        with self._lock:
            self.now -= 1


class TestTheCapPerHost:
    def test_a_host_of_its_own_overrides_the_default_and_a_subdomain_takes_its_parents(self) -> None:
        caps = policy(host_connections={"Example.ORG.": 3, HOST: 9})
        assert caps.connections_for(HOST) == 9
        assert caps.connections_for(OTHER) == 3
        assert caps.connections_for("elsewhere.net") == 6

    @pytest.mark.parametrize("count", [0, -1, 257, True, 1.5, "4"])
    def test_a_cap_that_is_no_whole_number_from_1_to_256_is_refused(self, count: object) -> None:
        with pytest.raises(ValueError, match="from 1 to 256"):
            policy(host_connections={HOST: count})

    def test_a_default_cap_below_one_is_refused(self) -> None:
        with pytest.raises(ValueError, match="from 1 to 256"):
            policy(max_connections_per_host=0)

    def test_the_slots_follow_the_cap_of_each_host(self) -> None:
        slots, peaks = ReadSlots(policy(host_connections={HOST: 1, OTHER: 3})), {HOST: Peak(), OTHER: Peak()}

        def read(host: str) -> None:
            with slots.slot(host):
                peaks[host].enter()
                time.sleep(0.01)
                peaks[host].leave()

        with ThreadPoolExecutor(max_workers=12) as pool:
            for future in [pool.submit(read, host) for host in [HOST, OTHER] * 8]:
                future.result()
        assert peaks[HOST].most == 1
        assert 1 < peaks[OTHER].most <= 3


class TestAThreadThatStopsWaiting:
    def test_an_interrupted_thread_leaves_the_queue_and_the_slot_reaches_the_next(self, monkeypatch) -> None:
        slots = ReadSlots(policy(max_connections_per_host=1))
        held = slots.slot(HOST)
        held.__enter__()
        real_wait = threading.Event.wait

        def interrupted(event: threading.Event, timeout: float | None = None) -> bool:
            raise KeyboardInterrupt

        monkeypatch.setattr(threading.Event, "wait", interrupted)
        with pytest.raises(KeyboardInterrupt), slots.slot(HOST):
            pytest.fail("the block must not run")
        monkeypatch.setattr(threading.Event, "wait", real_wait)
        assert not slots._hosts[HOST].waiters
        held.__exit__(None, None, None)
        with slots.slot(HOST):
            assert slots._hosts[HOST].held == 1
        assert slots._hosts[HOST].held == 0


class TestOnTheEventLoop:
    async def test_tasks_never_exceed_the_cap(self) -> None:
        slots, peak = ReadSlots(policy(max_connections_per_host=2)), Peak()

        async def hold() -> None:
            async with slots.aslot(HOST):
                peak.enter()
                await asyncio.sleep(0.005)
                peak.leave()

        await asyncio.gather(*(hold() for _ in range(12)))
        assert peak.most == 2 and peak.now == 0

    async def test_threads_and_tasks_share_one_cap(self) -> None:
        slots, peak = ReadSlots(policy(max_connections_per_host=3)), Peak()

        def read() -> None:
            with slots.slot(HOST):
                peak.enter()
                time.sleep(0.01)
                peak.leave()

        async def fetch() -> None:
            async with slots.aslot(HOST):
                peak.enter()
                await asyncio.sleep(0.01)
                peak.leave()

        with ThreadPoolExecutor(max_workers=8) as pool:
            threads = [asyncio.wrap_future(pool.submit(read)) for _ in range(8)]
            await asyncio.gather(*threads, *(fetch() for _ in range(8)))
        assert peak.most == 3 and peak.now == 0

    async def test_waiters_are_served_in_the_order_they_asked_on_either_side(self) -> None:
        slots, order = ReadSlots(policy(max_connections_per_host=1)), []
        held = slots.aslot(HOST)
        await held.__aenter__()

        def read() -> None:
            with slots.slot(HOST):
                order.append("thread")

        async def fetch() -> None:
            async with slots.aslot(HOST):
                order.append("task")

        pool = ThreadPoolExecutor(max_workers=1)
        thread = asyncio.wrap_future(pool.submit(read))
        while not slots._hosts[HOST].waiters:
            await asyncio.sleep(0.001)
        task = asyncio.create_task(fetch())
        await asyncio.sleep(0.01)
        await held.__aexit__(None, None, None)
        await asyncio.gather(thread, task)
        pool.shutdown()
        assert order == ["thread", "task"]

    async def test_a_cancelled_waiter_leaves_the_queue_and_takes_no_slot(self) -> None:
        slots = ReadSlots(policy(max_connections_per_host=1))
        async with slots.aslot(HOST):
            waiting = asyncio.create_task(slots.aslot(HOST).__aenter__())
            await asyncio.sleep(0.005)
            waiting.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiting
            assert not slots._hosts[HOST].waiters
        async with asyncio.timeout(1), slots.aslot(HOST):
            assert slots._hosts[HOST].held == 1
        assert slots._hosts[HOST].held == 0

    async def test_a_slot_handed_to_a_waiter_that_is_cancelled_passes_on(self) -> None:
        slots, inside = ReadSlots(policy(max_connections_per_host=1)), asyncio.Event()
        held = slots.aslot(HOST)
        await held.__aenter__()
        first = asyncio.create_task(slots.aslot(HOST).__aenter__())
        await asyncio.sleep(0.005)

        async def second() -> None:
            async with slots.aslot(HOST):
                inside.set()

        later = asyncio.create_task(second())
        await asyncio.sleep(0.005)
        await held.__aexit__(None, None, None)  # hands the slot to `first` ...
        first.cancel()  # ... which is cancelled before it runs
        with pytest.raises(asyncio.CancelledError):
            await first
        async with asyncio.timeout(1):
            await later
        assert inside.is_set() and slots._hosts[HOST].held == 0

    async def test_a_waiter_whose_loop_has_closed_is_passed_over(self) -> None:
        slots = ReadSlots(policy(max_connections_per_host=1))
        gone = asyncio.new_event_loop()
        held = slots.slot(HOST)
        held.__enter__()
        with slots._lock:
            stale = _Waiter(gone)
            slots._hosts[HOST].waiters.append(stale)
        gone.close()
        took = []

        def read() -> None:
            with slots.slot(HOST):
                took.append(True)

        with ThreadPoolExecutor(max_workers=1) as pool:
            thread = pool.submit(read)
            while len(slots._hosts[HOST].waiters) < 2:
                time.sleep(0.001)
            held.__exit__(None, None, None)
            thread.result(timeout=1)
        assert took == [True] and not stale.granted and slots._hosts[HOST].held == 0

    async def test_an_error_in_the_block_gives_the_slot_back(self) -> None:
        slots = ReadSlots(policy(max_connections_per_host=1))
        with pytest.raises(RuntimeError):
            async with slots.aslot(HOST):
                raise RuntimeError("the read failed")
        assert slots._hosts[HOST].held == 0


class TestGatewaysOfOneProcess:
    async def test_two_gateways_on_one_counter_keep_its_cap_together(self) -> None:
        caps = policy(host_connections={HOST: 2})
        slots, peak = ReadSlots(caps), Peak()

        async def handler(request: httpx.Request) -> httpx.Response:
            peak.enter()
            await asyncio.sleep(0.01)
            peak.leave()
            return httpx.Response(200, content=b"{}")

        def build() -> Gateway:
            return Gateway(
                caps, transport=httpx.MockTransport(handler), resolve=lambda *_: ("93.184.216.34",), slots=slots
            )

        async with build() as one, build() as two:
            await asyncio.gather(*(gateway.get(f"https://{HOST}/x") for gateway in [one, two] * 5))
        assert peak.most == 2

    def test_slots_that_miss_a_host_of_the_policy_are_refused(self) -> None:
        narrow = ReadSlots(Policy(allowed_hosts=frozenset({HOST})))
        with pytest.raises(ValueError, match="cover every host"):
            Gateway(policy(), slots=narrow)


class TestTheNumberOfInstances:
    @pytest.mark.parametrize(("raw", "count"), [("", 1), ("  ", 1), ("1", 1), ("2", 2), (" 3 ", 3), ("256", 256)])
    def test_a_whole_number_from_1_to_256_or_nothing(self, raw: str, count: int) -> None:
        assert source_instances_from_env({"EARTHX_SOURCE_INSTANCES": raw}) == count
        assert source_instances_from_env({}) == 1

    @pytest.mark.parametrize("raw", ["0", "-1", "257", "2.5", "two", "1e2", "٣"])
    def test_anything_else_stops_the_start_and_names_the_variable_not_the_value(self, raw: str) -> None:
        with pytest.raises(ValueError, match="EARTHX_SOURCE_INSTANCES") as raised:
            source_instances_from_env({"EARTHX_SOURCE_INSTANCES": raw})
        assert raw not in str(raised.value)

    @pytest.mark.parametrize(("cap", "instances", "share"), [(32, 1, 32), (32, 2, 16), (6, 4, 1), (6, 7, 1), (1, 3, 1)])
    def test_the_share_is_rounded_down_and_never_below_one(self, cap: int, instances: int, share: int) -> None:
        assert instance_share(cap, instances) == share
