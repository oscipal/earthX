"""T-D: is the ATOM service of the BEV still the source the BEV ALS-DGM entry describes? (M5-09 plan §4.6)

Runs on the schedule of the live smokes in GitHub Actions, never in a pull request and never in a cloud session. Small
on purpose (adr/0005 §3.6): the service feed, one dataset feed, a HEAD and one range of 16 bytes. Everything goes
through the gateway and the adapter's own reading of the feeds; the materialization itself reads 56 feeds and is
Otto's local run, not a smoke.

It checks what the entry and the materialization assume (M5-09 plan §2.4, A2): the newest reference date of the model
is the entry's, so a new date is reported before a run stops on it; that date has its 55 tiles, each with a DOI and a
dataset feed; a dataset feed holds exactly the one file on the asset host; the file is a TIFF read anonymously by range
and carries an ETag, the version of an input.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timezone

import httpx
import pytest

from earthx.adapters import bev_atom
from earthx.catalog.datasets import registry
from earthx.gateway import Policy
from earthx.gateway.client import Gateway

BEV = registry().get("bev-als-dgm")
MODEL = BEV.source.source_collection_id.removeprefix("ALS ")
#: The tiles of every date measured on 16.11.2026 (M5-09 plan §2.4).
TILES = 55

pytestmark = [pytest.mark.anyio, pytest.mark.live_dataset("bev-als-dgm")]


@asynccontextmanager
async def open_gateway() -> AsyncIterator[Gateway]:
    """The real gateway against the BEV, with the allowlist from the registry."""
    hosts = {httpx.URL(BEV.source.endpoint).host, *BEV.source.asset_hosts}
    async with Gateway(Policy(allowed_hosts=frozenset(hosts))) as gateway:
        yield gateway


@pytest.fixture
async def gateway() -> AsyncIterator[Gateway]:
    async with open_gateway() as gateway:
        yield gateway


async def _newest(gateway: Gateway):
    by_date, _ = bev_atom.tiles_by_date((await gateway.get(BEV.source.endpoint)).content, MODEL)
    newest = max(by_date)
    return newest, by_date[newest]


async def test_the_newest_reference_date_is_the_entrys_and_has_its_tiles(gateway: Gateway) -> None:
    """A newer date stops the run until ``temporal_extent`` is followed up (plan A2); this reports it first."""
    newest, tiles = await _newest(gateway)
    assert newest == BEV.temporal_extent.start.astimezone(timezone.utc).date(), (
        f"the newest reference date is {newest}; follow temporal_extent and the attribution year of the entry up"
    )
    assert len(tiles) == TILES, f"the newest date has {len(tiles)} tiles, not {TILES}"
    assert all(bev_atom.doi_of(entry) for entry in tiles.values()), "a tile's identifier is no longer its DOI"
    assert all(bev_atom.dataset_feed_of(entry) for entry in tiles.values()), "a tile no longer links one dataset feed"


async def test_one_dataset_feed_holds_its_one_file_read_anonymously(gateway: Gateway) -> None:
    """The first tile's dataset feed names one file on the asset host; ``206`` on a range, a TIFF, an ETag."""
    newest, tiles = await _newest(gateway)
    tile, entry = min(tiles.items())
    feed = await gateway.get(bev_atom.dataset_feed_of(entry))
    href = bev_atom.file_of(feed.content, model=MODEL, tile=tile, day=newest, asset_hosts=BEV.source.asset_hosts)
    assert href, "the dataset feed no longer holds exactly one file of the known path"
    head = await gateway.head(href)
    assert head.headers.get("etag"), "the file carries no ETag; the version of an input needs one"
    part = await gateway.get(href, headers={"range": "bytes=0-15"})
    assert part.status_code == 206
    assert part.content[:2] in (b"II", b"MM")
