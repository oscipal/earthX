"""T-D: is the EOPF Sentinel Zarr Samples Service still the source our fixtures
imitate — the second dataset's live smoke (M2-08 plan §11 F3).

Same reasoning as ``test_earth_search_smoke.py``: no recording can answer whether
the source still looks like this, so a schedule does, never a pull request and never
a cloud session (adr/0002 §2). A red run here colours no PR red; it leaves the
onboarding checklist's point 10 (Fassung v1.1) sitting on its last green date instead
— exactly what "staging" (`earthx:maturity`) is supposed to make visible.

Deliberately small (adr/0005 §3.6, K5): two metadata requests, no assets, a window
closed and in the past. `stac.core.eopf.eodc.eu` was measured directly on
2026-09-23 for this PR (the M2-09b plan session could not reach it — its own fixture
README at ``tests/fixtures/eopf_stac/README.md`` says so — `gateway` still does not
open to a cloud session, adr/0002 Nachtrag M2-13, so this was a direct `curl`, the
same way M2-08-1 measured Earth Search): the collection's archive starts
2026-07-16T10:06:01Z, and the one scene found in its first two weeks sits over
southern Germany. That scene, not the one M2-09b's hand-written fixtures invented, is
what this test asks for again on every scheduled run.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from earthx.adapters import SearchParams, get_item, search_items
from earthx.catalog.datasets import SENTINEL_2_L2A_ZARR3
from earthx.gateway import Policy
from earthx.gateway.client import Gateway

pytestmark = [pytest.mark.anyio, pytest.mark.live_dataset("sentinel-2-l2a-zarr3")]

# The scene measured on 2026-09-23: id S2C_MSIL2A_20260716T100601_N0512_R022_T32UQU_…,
# bbox roughly [11.67, 47.69, 13.21, 48.72]. The window is the archive's own opening
# fortnight, long closed by the time this runs again.
BBOX = (12.0, 48.0, 12.5, 48.3)
WINDOW = (datetime(2026, 7, 16, tzinfo=timezone.utc), datetime(2026, 7, 31, 23, 59, 59, tzinfo=timezone.utc))


@pytest.fixture
async def gateway():
    """The real gateway against the real host, with the allowlist from the registry."""
    host = httpx.URL(SENTINEL_2_L2A_ZARR3.source.endpoint).host
    async with Gateway(Policy(allowed_hosts=frozenset({host}))) as gateway:
        yield gateway


async def test_the_source_still_answers_the_way_our_fixtures_say(gateway: Gateway) -> None:
    """Search and single item, in two requests, through the adapter.

    Asserted is what the synthetic fixtures depend on: an item comes back for the
    scene measured on 2026-09-23, and it can be fetched by its own id without a
    search in front of it (adr/0001 Z1). Unlike Earth Search, this source's search
    answers carry no ``numberMatched``/``context`` (``tests/fixtures/eopf_stac/
    README.md``) — asserting a match count here would fail against the real source
    on every run, not just when something moved.
    """
    page = await search_items(
        SENTINEL_2_L2A_ZARR3.dataset_id,
        SearchParams(bbox=BBOX, start=WINDOW[0], end=WINDOW[1], limit=2),
        gateway=gateway,
    )

    assert page.items, "no item in the archive's opening fortnight over the measured scene"
    assert page.matched is None, "numberMatched appeared — the fixtures no longer match this source's shape"

    item = await get_item(SENTINEL_2_L2A_ZARR3.dataset_id, page.items[0]["id"], gateway=gateway)
    assert item["id"] == page.items[0]["id"]
    assert item["collection"] == SENTINEL_2_L2A_ZARR3.source.source_collection_id
