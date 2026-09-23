"""T-D: is Earth Search still the source our fixtures imitate?

The one question no recording can answer (adr/0002 §2). It runs on a schedule in
GitHub Actions, never in a pull request and never in a cloud session.

Deliberately small (adr/0005 §3.6, K5: rücksichtsvoll gegenüber der Quelle): two
metadata requests per run, no assets, a page of two items over a historic window. The
window is closed and in the past, so the answer is stable and the run says something
about the source rather than about today's weather over Europe.

It goes through the adapter and the gateway rather than around them: a smoke test of
a code path nobody uses would prove the wrong thing.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from earthx.adapters import SearchParams, get_item, search_items
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.gateway import Policy
from earthx.gateway.client import Gateway

pytestmark = [pytest.mark.anyio, pytest.mark.live_dataset("sentinel-2-c1-l2a")]

# A small box over Central Europe and a month that closed long ago — the same corner
# of the archive adr/0005 §3 measured, so a surprise here is comparable with it.
BBOX = (9.0, 48.0, 10.0, 49.0)
WINDOW = (datetime(2024, 6, 1, tzinfo=timezone.utc), datetime(2024, 6, 30, tzinfo=timezone.utc))


@pytest.fixture
async def gateway():
    """The real gateway against the real host, with the allowlist from the registry."""
    host = httpx.URL(SENTINEL_2_L2A.source.endpoint).host
    async with Gateway(Policy(allowed_hosts=frozenset({host}))) as gateway:
        yield gateway


async def test_the_source_still_answers_the_way_our_fixtures_say(gateway: Gateway) -> None:
    """Search and single item, in two requests, through the adapter.

    Asserted is what the synthetic fixtures depend on: items come back, the match
    count is a number, and an item can be fetched by its id without a search in front
    of it (adr/0001 Z1). If this fails, the fixtures in
    ``backend/tests/fixtures/earth_search/`` are describing a source that has moved.
    """
    page = await search_items(
        SENTINEL_2_L2A.dataset_id,
        SearchParams(bbox=BBOX, start=WINDOW[0], end=WINDOW[1], limit=2),
        gateway=gateway,
    )

    assert page.items, "no items in a window that held some when adr/0005 measured it"
    assert isinstance(page.matched, int), "the match count is gone or is no longer a number"
    assert page.next_page_token, "no next page, although the window holds more than two items"

    item = await get_item(SENTINEL_2_L2A.dataset_id, page.items[0]["id"], gateway=gateway)
    assert item["id"] == page.items[0]["id"]
    assert item["collection"] == SENTINEL_2_L2A.source.source_collection_id
