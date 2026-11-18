"""How a harvest run waits when its source asks it to slow down (Otto, 18.11.2026; plan §12.5).

A 429 is waited for by its Retry-After, else for minutes, doubling; a host the breaker paused after them is waited for
the same way; the run's hold on its source is renewed while it waits; past the budget of waiting the run stops.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from earthx.catalog.harvest_store import RunCounts
from earthx.discovery import harvest
from earthx.discovery.harvest import BACKOFF_BUDGET_S, BACKOFF_FIRST_S, HEARTBEAT_S, _Fetcher, _retry_after_s
from earthx.gateway import GatewayResponse, HostResting, UpstreamError

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
OK = GatewayResponse(200, {}, b"{}")


class Source:
    """Answers each request with the next of ``answers``: a response, or an exception to raise."""

    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.asked = 0

    async def get(self, url: str, **_: Any) -> GatewayResponse:
        self.asked += 1
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def _fetcher(source: Source, budget: int = 50) -> tuple[_Fetcher, list[float], list[int], RunCounts]:
    slept: list[float] = []
    renewed: list[int] = []
    counts = RunCounts()

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    fetch = _Fetcher(
        source,  # type: ignore[arg-type]
        "ckan.example.org",
        counts,
        budget,
        renew=lambda: renewed.append(1),
        sleep=sleep,
        now=lambda: NOW,
    )
    return fetch, slept, renewed, counts


def limited(retry_after: str | None = None) -> UpstreamError:
    return UpstreamError(429, "slow down", retry_after=retry_after)


async def test_retry_after_is_waited_for_in_heartbeats() -> None:
    fetch, slept, renewed, counts = _fetcher(Source(limited("150"), OK))
    assert await fetch("https://ckan.example.org/api/3/action/package_search") is OK
    assert slept == [HEARTBEAT_S, HEARTBEAT_S, 30.0] and len(renewed) == 3
    assert (fetch.rate_limited, fetch.waited_s, counts.requests) == (1, 150.0, 2)


async def test_without_retry_after_the_wait_doubles_from_minutes_on() -> None:
    fetch, slept, _, _ = _fetcher(Source(limited(), limited(), limited(), OK))
    await fetch("https://ckan.example.org/x")
    assert fetch.waited_s == BACKOFF_FIRST_S * (1 + 2 + 4)
    assert all(step <= HEARTBEAT_S for step in slept)


async def test_a_host_the_breaker_paused_after_the_429s_is_waited_for() -> None:
    fetch, _, _, counts = _fetcher(Source(limited(), HostResting("paused", host="ckan.example.org"), OK))
    await fetch("https://ckan.example.org/x")
    # The paused host was not asked: two requests went out.
    assert (fetch.waited_s, counts.requests) == (BACKOFF_FIRST_S * 3, 2)


async def test_a_resting_host_without_a_429_before_ends_the_run() -> None:
    fetch, slept, _, _ = _fetcher(Source(HostResting("robots.txt not readable", host="ckan.example.org")))
    with pytest.raises(HostResting):
        await fetch("https://ckan.example.org/x")
    assert slept == []


async def test_other_errors_are_not_waited_for() -> None:
    fetch, slept, _, _ = _fetcher(Source(UpstreamError(503, "down")))
    with pytest.raises(UpstreamError):
        await fetch("https://ckan.example.org/x")
    assert slept == []


async def test_past_the_budget_of_waiting_the_run_stops() -> None:
    fetch, _, _, _ = _fetcher(Source(*[limited() for _ in range(20)]))
    with pytest.raises(harvest._RateLimited):
        await fetch("https://ckan.example.org/x")
    assert fetch.waited_s <= BACKOFF_BUDGET_S


async def test_a_retry_after_longer_than_the_budget_stops_at_once() -> None:
    fetch, slept, _, _ = _fetcher(Source(limited(str(int(BACKOFF_BUDGET_S) + 1))))
    with pytest.raises(harvest._RateLimited):
        await fetch("https://ckan.example.org/x")
    assert slept == []


async def test_the_budget_of_requests_counts_the_429s() -> None:
    fetch, _, _, _ = _fetcher(Source(limited(), limited(), OK), budget=2)
    with pytest.raises(harvest._BudgetSpent):
        await fetch("https://ckan.example.org/x")


@pytest.mark.parametrize(
    ("value", "seconds"),
    [
        ("120", 120.0),
        (" 7 ", 7.0),
        ("Wed, 18 Nov 2026 12:05:00 GMT", 300.0),
        ("Wed, 18 Nov 2026 11:00:00 GMT", 0.0),
        ("soon", None),
        ("-5", None),
        ("²", None),
        ("", None),
        (None, None),
    ],
)
def test_retry_after_as_seconds_or_a_date(value: str | None, seconds: float | None) -> None:
    assert _retry_after_s(value, NOW) == seconds
