"""The gateway with a coordinator handed in: shared turn, place and breaker per host (M5-37 §4, §5.1)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest

from earthx.gateway import (
    MAX_SHARED_WAIT_S,
    HostResting,
    Policy,
    UpstreamError,
    UpstreamTimeout,
    UpstreamUnreachable,
    UrlRejected,
)
from earthx.gateway.client import Gateway

HOST = "data.example.org"
URL = f"https://{HOST}/items"

pytestmark = pytest.mark.anyio


def public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


class Recorder:
    """A coordinator that writes down what it is asked, in order, and answers each turn with ``delay``."""

    def __init__(self, delay: float = 0.0, paused: float = 0.0, broken: bool = False) -> None:
        self.delay = delay
        self.paused = paused
        self.broken = broken
        self.calls: list[tuple] = []
        self.held = 0

    async def reserve(self, host: str, interval_s: float, max_wait_s: float) -> float:
        self.calls.append(("reserve", host, interval_s))
        assert max_wait_s == MAX_SHARED_WAIT_S
        if self.broken:
            raise ConnectionError("the database is gone")
        return self.delay

    async def pause_left(self, host: str) -> float:
        self.calls.append(("pause_left", host))
        return self.paused

    @asynccontextmanager
    async def place(self, host: str, cap: int) -> AsyncIterator[int]:
        self.calls.append(("place", host, cap))
        self.held += 1
        try:
            yield 1
        finally:
            self.held -= 1
            self.calls.append(("release", host))

    async def report(self, host: str, *, failed: bool, retry_after_s: float | None = None) -> None:
        self.calls.append(("report", host, failed, retry_after_s))

    def reports(self) -> list[tuple]:
        return [call[2:] for call in self.calls if call[0] == "report"]


def build(coordinator: Recorder, handler, policy: Policy | None = None, slept: list[float] | None = None) -> Gateway:
    async def sleep(seconds: float) -> None:
        if slept is not None:
            slept.append(seconds)

    return Gateway(
        policy or Policy(allowed_hosts=frozenset({HOST})),
        transport=httpx.MockTransport(handler),
        resolve=public,
        sleep=sleep,
        coordinator=coordinator,
    )


def answering(*statuses: int, headers: dict[str, str | bytes] | None = None):
    queue = list(statuses)

    def handle(request: httpx.Request) -> httpx.Response:
        status = queue.pop(0) if len(queue) > 1 else queue[0]
        return httpx.Response(status, headers=headers or {}, json={})

    return handle


async def test_each_attempt_takes_a_turn_with_the_hosts_interval_and_one_place_holds_the_request() -> None:
    coordinator = Recorder()
    policy = Policy(allowed_hosts=frozenset({HOST}), host_intervals={HOST: 1.0}, host_connections={HOST: 4})
    async with build(coordinator, answering(503, 200), policy) as gateway:
        await gateway.get(URL)
    assert coordinator.calls == [
        ("place", HOST, 4),
        ("reserve", HOST, 1.0),
        ("report", HOST, True, None),
        ("reserve", HOST, 1.0),
        ("report", HOST, False, None),
        ("release", HOST),
    ]


async def test_a_host_without_an_interval_still_takes_a_turn_because_a_pause_moves_it() -> None:
    coordinator = Recorder()
    async with build(coordinator, answering(200)) as gateway:
        await gateway.get(URL)
    assert ("reserve", HOST, 0.0) in coordinator.calls


async def test_the_gateway_sleeps_the_wait_of_its_turn() -> None:
    slept: list[float] = []
    async with build(Recorder(delay=12.5), answering(200), slept=slept) as gateway:
        await gateway.get(URL)
    assert slept == [12.5]


async def test_a_turn_further_off_than_a_minute_lets_the_host_rest_without_sending() -> None:
    sent: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={})

    coordinator = Recorder(delay=MAX_SHARED_WAIT_S + 1)
    async with build(coordinator, handle) as gateway:
        with pytest.raises(HostResting) as raised:
            await gateway.get(URL)
    assert sent == []
    assert raised.value.host == HOST
    assert coordinator.held == 0
    assert coordinator.reports() == []


async def test_a_turn_of_exactly_a_minute_is_still_waited_for() -> None:
    slept: list[float] = []
    async with build(Recorder(delay=MAX_SHARED_WAIT_S), answering(200), slept=slept) as gateway:
        await gateway.get(URL)
    assert slept == [MAX_SHARED_WAIT_S]


@pytest.mark.parametrize("status", [200, 204, 304, 400, 404, 410])
async def test_any_answer_below_500_but_429_is_a_success_of_the_host(status: int) -> None:
    coordinator = Recorder()
    async with build(coordinator, answering(status)) as gateway:
        try:
            await gateway.get(URL)
        except UpstreamError:
            pass
    assert coordinator.reports() == [(False, None)]


async def test_a_500_is_a_failure_though_it_is_not_retried() -> None:
    coordinator = Recorder()
    async with build(coordinator, answering(500)) as gateway:
        with pytest.raises(UpstreamError):
            await gateway.get(URL)
    assert coordinator.reports() == [(True, None)]


async def test_every_failed_attempt_counts_and_carries_a_retry_after_in_seconds() -> None:
    coordinator = Recorder()
    async with build(coordinator, answering(429, headers={"retry-after": "7"})) as gateway:
        with pytest.raises(UpstreamError):
            await gateway.get(URL)
    assert coordinator.reports() == [(True, 7.0)] * 3


@pytest.mark.parametrize("value", ["", "soon", "Wed, 21 Oct 2026 07:28:00 GMT", "-5", "1.5", b"\xb2"])
async def test_a_retry_after_that_is_not_whole_seconds_goes_without_one(value: str | bytes) -> None:
    coordinator = Recorder()
    async with build(coordinator, answering(503, 200, headers={"retry-after": value})) as gateway:
        await gateway.get(URL)
    assert coordinator.reports()[0] == (True, None)


async def test_a_timeout_and_a_refused_connection_are_failures_and_the_place_goes_back() -> None:
    def time_out(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    for handler, error in ((time_out, UpstreamTimeout), (refuse, UpstreamUnreachable)):
        coordinator = Recorder()
        async with build(coordinator, handler) as gateway:
            with pytest.raises(error):
                await gateway.get(URL, retry=False)
        assert coordinator.reports() == [(True, None)]
        assert coordinator.held == 0


async def test_a_url_the_gateway_refuses_asks_no_turn_and_reports_nothing() -> None:
    coordinator = Recorder()
    async with build(coordinator, answering(200)) as gateway:
        with pytest.raises(UrlRejected):
            await gateway.get("https://elsewhere.example.net/x")
    assert coordinator.calls == []


async def test_a_cancelled_request_gives_its_place_back() -> None:
    started = asyncio.Event()

    async def hang(request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.sleep(3600)
        return httpx.Response(200)

    coordinator = Recorder()
    async with build(coordinator, hang) as gateway:
        task = asyncio.create_task(gateway.get(URL))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert coordinator.held == 0
    assert coordinator.calls[-1] == ("release", HOST)


async def test_without_a_coordinator_nothing_changes_for_a_host_without_an_interval() -> None:
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    gateway = Gateway(
        Policy(allowed_hosts=frozenset({HOST})),
        transport=httpx.MockTransport(answering(200)),
        resolve=public,
        sleep=sleep,
    )
    async with gateway:
        await gateway.get(URL)
    assert slept == []


async def test_a_host_paused_while_the_turn_was_waited_for_is_not_asked() -> None:
    """Review S3: turns handed out before the breaker opened must not send into the pause."""
    sent: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={})

    coordinator = Recorder(delay=2.0, paused=300.0)
    async with build(coordinator, handle) as gateway:
        with pytest.raises(HostResting):
            await gateway.get(URL)
    assert sent == []
    assert coordinator.held == 0


async def test_a_short_pause_found_after_the_turn_is_waited_out_before_sending() -> None:
    slept: list[float] = []
    async with build(Recorder(delay=2.0, paused=5.0), answering(200), slept=slept) as gateway:
        await gateway.get(URL)
    assert slept == [2.0, 5.0]


async def test_a_turn_without_a_wait_does_not_ask_for_a_pause() -> None:
    coordinator = Recorder()
    async with build(coordinator, answering(200)) as gateway:
        await gateway.get(URL)
    assert not [call for call in coordinator.calls if call[0] == "pause_left"]


async def test_without_the_database_nothing_is_sent() -> None:
    sent: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={})

    coordinator = Recorder(broken=True)
    async with build(coordinator, handle) as gateway:
        with pytest.raises(ConnectionError):
            await gateway.get(URL)
    assert sent == []
    assert coordinator.held == 0


async def test_an_odd_retry_after_on_a_success_does_not_break_the_request() -> None:
    """Review S4: the header is read on every answer now, so a digit outside ASCII must not raise."""
    coordinator = Recorder()
    async with build(coordinator, answering(200, headers={"retry-after": b"\xb2"})) as gateway:
        await gateway.get(URL)
    assert coordinator.reports() == [(False, None)]
