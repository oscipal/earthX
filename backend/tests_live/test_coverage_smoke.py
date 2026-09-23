"""T-D: does the coverage aggregation still answer the way §3 of the plan measured?

Runs on a schedule in GitHub Actions, never in a pull request and never in a cloud
session (adr/0002 §2) — plans/m2-05-coverage.md §7.1 records why a cloud session
cannot reach the source through `gateway` at all (the gateway pins the checked
*address*, and the environment's egress allowance is name-based). The `curl`
measurements of the plan's §3 are the evidence for this PR; this test is what turns
that evidence into something CI checks on every scheduled run from here on.

One request only (adr/0005 §3.6, K5: rücksichtsvoll gegenüber der Quelle): a
filtered aggregation over a historic window, the same corner of the archive
`test_earth_search_smoke.py` already uses, so a surprise here is comparable with it.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx
import pytest

from earthx.adapters.earth_search_coverage import aggregate_coverage
from earthx.catalog.coverage import CoverageQuery
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.gateway import Policy
from earthx.gateway.client import Gateway

pytestmark = [pytest.mark.anyio, pytest.mark.live_dataset("sentinel-2-c1-l2a")]

# The same box and window as adr/0004 §3.2 and §3.1 of the plan measured.
BBOX = (5.0, 45.0, 15.0, 55.0)
WINDOW = (datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc))

# K6 (ENTSCHEIDUNGSLOG 2026-09-19): under 1 s, typically under 0,5 s.
LATENCY_TARGET_S = 1.0


@pytest.fixture
async def gateway():
    host = httpx.URL(SENTINEL_2_L2A.source.endpoint).host
    async with Gateway(Policy(allowed_hosts=frozenset({host}))) as gateway:
        yield gateway


async def test_a_filtered_aggregation_answers_within_the_latency_target(gateway: Gateway) -> None:
    query = CoverageQuery(
        dataset_id=SENTINEL_2_L2A.dataset_id,
        level=8,
        bbox=BBOX,
        start=WINDOW[0],
        end=WINDOW[1],
    )

    started = time.monotonic()
    result = await aggregate_coverage(query, SENTINEL_2_L2A, gateway=gateway)
    elapsed = time.monotonic() - started

    assert result.cells, "no cells in a window that held some when the plan measured it"
    assert result.total_count is not None, "no total_count — Regel V could not prove completeness at all"
    assert elapsed < LATENCY_TARGET_S, f"took {elapsed:.2f}s, target is {LATENCY_TARGET_S}s (K6)"
