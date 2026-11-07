"""The least time between two starts to one host (adr/0025 §6.2, M5-18 §3.2)."""

from __future__ import annotations

import asyncio
import math

import httpx
import pytest

from earthx.gateway import Policy, UrlRejected
from earthx.gateway.client import Gateway

HOST = "catalog.example.org"
SUB = "api.catalog.example.org"
OTHER = "mirror.example.net"

pytestmark = pytest.mark.anyio


def public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


class FakeTime:
    """A clock that only moves when the gateway sleeps; records every start per host."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.starts: list[tuple[str, float]] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds
        await asyncio.sleep(0)

    def handler(self, *answers: httpx.Response):
        queue = list(answers)

        def handle(request: httpx.Request) -> httpx.Response:
            self.starts.append((request.headers["host"], self.now))
            return queue.pop(0) if len(queue) > 1 else queue[0]

        return handle


def build(time: FakeTime, policy: Policy, *answers: httpx.Response) -> Gateway:
    handler = time.handler(*(answers or (httpx.Response(200, json={}),)))
    return Gateway(
        policy, transport=httpx.MockTransport(handler), resolve=public, sleep=time.sleep, clock=time.clock
    )


def starts_of(time: FakeTime, host: str) -> list[float]:
    return [at - 1000.0 for name, at in time.starts if name == host]


async def test_two_requests_to_one_host_start_an_interval_apart() -> None:
    time = FakeTime()
    async with build(time, Policy(allowed_hosts=frozenset({HOST}), min_interval_s=2.0)) as gateway:
        await gateway.get(f"https://{HOST}/a")
        await gateway.get(f"https://{HOST}/b")
    assert starts_of(time, HOST) == [0.0, 2.0]


async def test_different_hosts_do_not_wait_for_each_other() -> None:
    time = FakeTime()
    async with build(time, Policy(allowed_hosts=frozenset({HOST, OTHER}), min_interval_s=2.0)) as gateway:
        await gateway.get(f"https://{HOST}/a")
        await gateway.get(f"https://{OTHER}/a")
    assert starts_of(time, HOST) == [0.0]
    assert starts_of(time, OTHER) == [0.0]


async def test_the_default_never_waits() -> None:
    time = FakeTime()
    async with build(time, Policy(allowed_hosts=frozenset({HOST}))) as gateway:
        for _ in range(3):
            await gateway.get(f"https://{HOST}/a")
    assert starts_of(time, HOST) == [0.0, 0.0, 0.0]


async def test_a_host_entry_wins_and_a_subdomain_inherits_it() -> None:
    time = FakeTime()
    policy = Policy(allowed_hosts=frozenset({HOST}), min_interval_s=1.0, host_intervals={"Catalog.Example.org.": 5.0})
    assert policy.interval_for(SUB) == 5.0
    assert policy.interval_for("example.org") == 1.0
    async with build(time, policy) as gateway:
        await gateway.get(f"https://{SUB}/a")
        await gateway.get(f"https://{SUB}/b")
    assert starts_of(time, SUB) == [0.0, 5.0]


async def test_six_concurrent_requests_still_start_one_interval_apart() -> None:
    """The clock stands still, so each request's wait is its distance from the first start."""
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    policy = Policy(allowed_hosts=frozenset({HOST}), min_interval_s=1.0)
    handler = FakeTime().handler(httpx.Response(200, json={}))
    gateway = Gateway(policy, transport=httpx.MockTransport(handler), resolve=public, sleep=sleep, clock=lambda: 0.0)
    async with gateway:
        await asyncio.gather(*(gateway.get(f"https://{HOST}/{index}") for index in range(6)))
    assert sorted(waits) == [1.0, 2.0, 3.0, 4.0, 5.0]


async def test_a_retry_waits_for_its_backoff_and_keeps_the_spacing() -> None:
    time = FakeTime()
    policy = Policy(allowed_hosts=frozenset({HOST}), min_interval_s=3.0)
    async with build(time, policy, httpx.Response(503, headers={"retry-after": "1"}), httpx.Response(200)) as gateway:
        await gateway.get(f"https://{HOST}/a")
    first, second = starts_of(time, HOST)
    assert second - first >= 3.0


async def test_a_redirect_hop_counts_at_the_host_it_goes_to() -> None:
    time = FakeTime()
    policy = Policy(allowed_hosts=frozenset({HOST, OTHER}), min_interval_s=4.0)
    redirect = httpx.Response(302, headers={"location": f"https://{OTHER}/a"})
    async with build(time, policy, redirect, httpx.Response(200)) as gateway:
        await gateway.get(f"https://{HOST}/a")
        await gateway.get(f"https://{OTHER}/b")
    assert starts_of(time, HOST) == [0.0]
    assert starts_of(time, OTHER) == [0.0, 4.0]


@pytest.mark.parametrize("value", [-1.0, math.nan, math.inf, 300.5])
def test_a_bad_default_builds_no_policy(value: float) -> None:
    with pytest.raises(ValueError):
        Policy(allowed_hosts=frozenset({HOST}), min_interval_s=value)


@pytest.mark.parametrize("value", [-0.1, math.nan, 1000.0])
def test_a_bad_host_entry_builds_no_policy(value: float) -> None:
    with pytest.raises(ValueError):
        Policy(allowed_hosts=frozenset({HOST}), host_intervals={HOST: value})


@pytest.mark.parametrize("host", ["127.0.0.1", "", "not a host"])
def test_a_host_entry_that_is_no_name_builds_no_policy(host: str) -> None:
    with pytest.raises(UrlRejected):
        Policy(allowed_hosts=frozenset({HOST}), host_intervals={host: 1.0})


def test_the_host_table_cannot_be_changed_afterwards() -> None:
    policy = Policy(allowed_hosts=frozenset({HOST}), host_intervals={HOST: 1.0})
    with pytest.raises(TypeError):
        policy.host_intervals[HOST] = 0.0  # type: ignore[index]
