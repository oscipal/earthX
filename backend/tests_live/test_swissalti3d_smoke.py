"""T-D: is the STAC API of the FSDI still the source the swissALTI3D entry describes? (M5-08 plan §4.7)

Runs on the schedule of the live smokes in GitHub Actions, never in a pull request and never in a cloud session. Small
on purpose (adr/0005 §3.6): nine metadata requests and one range of 16 bytes. Everything goes through the gateway, the
search and the item through the STAC module as on the platform; the materialization itself reads about a thousand pages
and is Otto's local run, not a smoke.

It checks what the entry and the materialization assume (M5-08 plan §2, §7 R1): the collection answers a conditional
request with ``304``, the next page comes from ``cursor``, every item fits the fixed asset keys and the tile pattern,
the COG of 0.5 m is read anonymously by range, the newest state lies inside the entry's period, and the collection's
``updated`` is not older than the newest item. That last check is half of risk R1: ``updated`` moves with the items.
Whether the ETag moves too is not something one run can see, and while the source answers ``304`` the ETag alone
decides (plan §12, §13).
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
import pytest

from earthx.adapters.federated_search import SearchParams
from earthx.adapters.stac_api import get_item, search_items
from earthx.catalog.datasets import registry
from earthx.gateway import Policy
from earthx.gateway.client import Gateway

SWISSALTI3D = registry().get("swissalti3d")

pytestmark = [pytest.mark.anyio, pytest.mark.live_dataset("swissalti3d")]

#: A coarse box over the middle of Switzerland: many tiles, so a second page always exists.
BBOX = (7.0, 46.5, 8.0, 47.0)
COLLECTION_URL = (
    f"{SWISSALTI3D.source.endpoint}/collections/{SWISSALTI3D.source.source_collection_id}"
)


@asynccontextmanager
async def open_gateway() -> AsyncIterator[Gateway]:
    """The real gateway against the FSDI, with the allowlist from the registry."""
    hosts = {httpx.URL(SWISSALTI3D.source.endpoint).host, *SWISSALTI3D.source.asset_hosts}
    async with Gateway(Policy(allowed_hosts=frozenset(hosts))) as gateway:
        yield gateway


@pytest.fixture
async def gateway() -> AsyncIterator[Gateway]:
    async with open_gateway() as gateway:
        yield gateway


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def test_the_collection_answers_its_etag_with_304(gateway: Gateway) -> None:
    """The materialization asks with ``If-None-Match`` first (M5-08 plan §4.2)."""
    first = await gateway.get(COLLECTION_URL)
    assert first.status_code == 200
    etag = first.headers.get("etag")
    assert etag, "the collection answered without an ETag; the version of a run needs one"
    assert first.json().get("updated"), "the collection carries no updated; the version of a run needs one"
    again = await gateway.get(COLLECTION_URL, headers={"if-none-match": etag})
    assert again.status_code == 304


async def test_two_pages_of_items_fit_the_entry(gateway: Gateway) -> None:
    """The second page comes from ``cursor``; every item fits the asset keys and the tile pattern."""
    first = await search_items(SWISSALTI3D, SearchParams(bbox=BBOX, limit=2), gateway=gateway)
    assert len(first.items) == 2 and first.next_page_token, "no second page in a box of many tiles"
    second = await search_items(
        SWISSALTI3D, SearchParams(bbox=BBOX, limit=2, page_token=first.next_page_token), gateway=gateway
    )
    items = [*first.items, *second.items]
    assert first.skipped == second.skipped == 0, "an item no longer fits source.asset_keys"
    assert len({item["id"] for item in items}) == len(items), "the second page repeats the first"
    keys = [rule.key for rule in SWISSALTI3D.source.asset_keys]
    host = SWISSALTI3D.source.asset_hosts[0]
    pattern = re.compile(SWISSALTI3D.source.item_states.tile_pattern)
    for item in items:
        assert set(item["assets"]) == set(keys)
        assert all(asset["href"].startswith(f"https://{host}/") for asset in item["assets"].values())
        assert pattern.fullmatch(item["id"]), "an item id no longer names its tile"
        assert item["collection"] == SWISSALTI3D.source.source_collection_id
        assert item["properties"].get("datetime")


async def test_one_item_and_its_cog_are_read_anonymously(gateway: Gateway) -> None:
    """One item by id, with the fixed keys, and a range of its COG of 0.5 m: ``206`` and a TIFF."""
    page = await search_items(SWISSALTI3D, SearchParams(bbox=BBOX, limit=1), gateway=gateway)
    item = await get_item(SWISSALTI3D, page.items[0]["id"], gateway=gateway)
    asset = item["assets"][SWISSALTI3D.default_render.assets[0]]
    assert asset["href"].startswith(f"https://{SWISSALTI3D.source.asset_hosts[0]}/")
    assert asset.get("file:checksum"), "the version of an input is its file:checksum"
    part = await gateway.get(asset["href"], headers={"range": "bytes=0-15"})
    assert part.status_code == 206
    assert part.content[:2] in (b"II", b"MM")


async def test_the_newest_state_lies_in_the_period_and_under_the_collection_updated(gateway: Gateway) -> None:
    """A state after the end of ``temporal_extent`` needs the entry updated; ``updated`` of the collection has to move
    with the items (half of R1, see the module docstring)."""
    collection = (await gateway.get(COLLECTION_URL)).json()

    async def newest(field: str) -> dict:
        body = {
            "collections": [SWISSALTI3D.source.source_collection_id],
            "limit": 1,
            "sortby": [{"field": f"properties.{field}", "direction": "desc"}],
        }
        answer = await gateway.post_json(f"{SWISSALTI3D.source.endpoint}/search", json=body, retry=True)
        (feature,) = answer.json()["features"]
        return feature["properties"]

    latest_state = _instant((await newest("datetime"))["datetime"])
    assert latest_state <= SWISSALTI3D.temporal_extent.end, (
        f"a state of {latest_state.year} is newer than the entry's period; update temporal_extent.end"
    )
    latest_update = _instant((await newest("updated"))["updated"])
    assert latest_update <= _instant(collection["updated"]), (
        "an item was updated after the collection's own updated; updated no longer follows the items (R1)"
    )
