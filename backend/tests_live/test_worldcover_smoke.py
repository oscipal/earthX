"""T-D: does the ESA WorldCover bucket still answer the way M5-07 measured it?

Runs on a schedule in GitHub Actions, never in a pull request (`adr/0002` §2), like `test_cop_dem_smoke.py`. The
measurements are `docs/plans/m5/m5-07-worldcover.md` §2, from 06.11.2026. Few requests (adr/0005 §3.6, K5):

1. a conditional ``GET`` on the tile grid against the measured ETag, expecting ``304``: the grid has not moved;
2. one small page of the listing of each state;
3. a range read of a few bytes on one real tile of each state.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest

from earthx.catalog.datasets import ESA_WORLDCOVER_2020, ESA_WORLDCOVER_2021
from earthx.gateway import Policy
from earthx.gateway.client import Gateway

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.live_dataset("esa-worldcover-2020"),
    pytest.mark.live_dataset("esa-worldcover-2021"),
]

# Measured 06.11.2026 (M5-07 plan §2); the grid dates from 06.03.2023.
KNOWN_GRID_ETAG = '"ff83a264e6364861d4e71681b868f886"'

# One tile both states have (measured), read a handful of header bytes, never the file.
KNOWN_TILE = "N45E009"

STATES = [ESA_WORLDCOVER_2020, ESA_WORLDCOVER_2021]


@asynccontextmanager
async def open_gateway() -> AsyncIterator[Gateway]:
    host = httpx.URL(ESA_WORLDCOVER_2021.source.endpoint).host
    async with Gateway(Policy(allowed_hosts=frozenset({host}))) as gateway:
        yield gateway


@pytest.fixture
async def gateway() -> AsyncIterator[Gateway]:
    async with open_gateway() as gateway:
        yield gateway


async def test_the_grid_etag_is_unchanged(gateway: Gateway) -> None:
    response = await gateway.get(
        f"{ESA_WORLDCOVER_2021.source.endpoint}/esa_worldcover_grid.geojson",
        headers={"if-none-match": KNOWN_GRID_ETAG},
    )
    assert response.status_code == 304, (
        f"the WorldCover grid answered {response.status_code}, not 304 — the bucket has changed since M5-07 measured "
        "it (plan §2); re-measure before the next materialize run"
    )


async def test_one_page_of_each_state_still_answers(gateway: Gateway) -> None:
    for entry in STATES:
        response = await gateway.get(
            f"{entry.source.endpoint}/",
            params={"list-type": "2", "prefix": f"{entry.source.source_collection_id}/map/", "max-keys": "5"},
        )
        assert response.status_code == 200, entry.dataset_id
        assert b"_Map.tif</Key>" in response.content, entry.dataset_id


async def test_a_known_tile_of_each_state_answers_a_range_read(gateway: Gateway) -> None:
    for entry in STATES:
        version, year = entry.source.source_collection_id.split("/")
        response = await gateway.get(
            f"{entry.source.endpoint}/{version}/{year}/map/ESA_WorldCover_10m_{year}_{version}_{KNOWN_TILE}_Map.tif",
            headers={"range": "bytes=0-15"},
        )
        assert response.status_code in (200, 206), f"{entry.dataset_id}: unexpected status {response.status_code}"
        # A TIFF's byte-order mark, little- or big-endian.
        assert response.content[:2] in (b"II", b"MM"), entry.dataset_id
