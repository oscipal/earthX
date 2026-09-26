"""Onboarding checklist point 9, per registry entry: search → display → clipped download.

Version v1 of the point (D4, 20.09.2026): until there is a processing step (M4),
the chain that stands in for "at least one processing step tested end to end" is
**search → display → clipped download**, against fixtures.

The depth is F4 (a) of the plan: the search runs through the entry's own adapter,
display and download through the real routes on a ``TestClient``. ``/stac/search``
itself is left out because it hangs on pgstac, and the federation layer it adds is
what ``tests/integration/test_api_federating.py`` already covers — running it here
would bind an admission rule to a database being up.

What is real and what is synthetic is spelled out in `synthetic_chain.py`. The
short version: everything except the answers.
"""

from __future__ import annotations

import re
import zipfile
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from earthx.access.download import NOTICE_FILENAME
from earthx.adapters import SearchParams, materialize_items, search_items
from earthx.api.tiler import build_app
from earthx.catalog.datasets import REGISTRY
from earthx.catalog.registry import DatasetConfig, ItemHolding, group_key
from tests.catalog import synthetic_chain
from tests.catalog.synthetic_chain import Chain, UnsupportedFormat
from tests.catalog.test_onboarding_checklist import CHECKED_ELSEWHERE, CHECKLIST

pytestmark = pytest.mark.anyio

ENTRIES = list(REGISTRY)
ENTRY_IDS = [config.dataset_id for config in ENTRIES]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(params=ENTRIES, ids=ENTRY_IDS)
def chain(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Chain:
    return synthetic_chain.build(request.param, tmp_path, monkeypatch)


@pytest.fixture
def client(chain: Chain) -> TestClient:
    """The real app over the chain's synthetic source, with no database behind it."""

    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        return chain.item

    @asynccontextmanager
    async def lifespan(app):
        app.state.earthx_item_source = item_source
        yield

    app = build_app(chain.registry, lifespan=lifespan)
    app.state.earthx_resolver = synthetic_chain.mini_zarr.from_memory
    with TestClient(app) as test_client:
        yield test_client


def test_this_module_is_the_one_the_checklist_points_at() -> None:
    """Point 9 is checked here, and the checklist says so — in both directions."""
    assert CHECKED_ELSEWHERE[9] == __name__
    assert "Suche -> Anzeige -> Zuschnitt-Download" in CHECKLIST[9]


# --------------------------------------------------------------------------------
# The three links, each on its own, and then the chain.
# --------------------------------------------------------------------------------


async def test_search_reaches_the_source_through_its_own_adapter(chain: Chain) -> None:
    """Link 1. For a federated entry: the request is the one the adapter really
    builds from the endpoint. For a materialized entry (M3-11b F9): item
    *creation* through the real adapter against the synthetic bucket, instead —
    there is no search request to build."""
    if chain.config.source.item_holding is ItemHolding.MATERIALIZED:
        outcome = await materialize_items(chain.config, gateway=chain.gateway, known_version=None)
        assert [item["id"] for item in outcome.items] == [chain.item["id"]]
        assert outcome.items[0]["bbox"] == chain.item["bbox"]
        paths = {request.url.path for request in chain.searched}
        assert paths == {"/tileList.txt", "/blacklist.txt", "/"}
        return

    page = await search_items(
        chain.dataset_id,
        SearchParams(limit=10),
        gateway=chain.gateway,
        registry=chain.registry,
    )

    assert [item["id"] for item in page.items] == [synthetic_chain.ITEM_ID]

    (request,) = chain.searched
    endpoint = httpx.URL(chain.config.source.endpoint)
    # The address is the pinned one and the name lives in the Host header — that
    # is `gateway`'s address pinning (M1-03), not a quirk of the fixture.
    assert request.url.path == f"{endpoint.path.rstrip('/')}/search"
    assert request.headers["host"] == endpoint.host


async def test_a_found_item_carries_the_key_the_viewer_groups_by(chain: Chain) -> None:
    """Link 1, second half: D19 — the viewer builds its time step from this item.

    Without it the search would succeed and the viewer would still have nothing to
    put on the time line, which is not "end to end" in any useful sense.
    """
    viewer = chain.config.viewer
    assert viewer is not None, "an entry the viewer cannot group has no display step"
    key = group_key(chain.item, viewer)
    assert len(key) == len(viewer.group_by)
    # A STAC instant enters the key as its UTC date (D19) — the date itself
    # differs by entry (a federated Sentinel-2 item vs. the DEM's fixed
    # acquisition period, M3-11b F1), so only the shape is checked here.
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", key[0])


def test_display_renders_a_tile_from_the_registrys_own_visualisation(
    client: TestClient, chain: Chain
) -> None:
    """Link 2. The asset key is checklist point 8's value, not one invented here."""
    zoom, x, y = chain.tile
    response = client.get(
        f"/collections/{chain.dataset_id}/items/{chain.item['id']}"
        f"/tiles/WebMercatorQuad/{zoom}/{x}/{y}.png",
        params={"asset": chain.render_asset},
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert chain.read_addresses(), "the tile was rendered without reading the asset"


def test_the_clipped_download_is_a_zip_of_raster_and_notice(client: TestClient, chain: Chain) -> None:
    """Link 3. A ZIP with the crop and the terms the licence says to pass on (M2-06)."""
    response = client.post(
        f"/collections/{chain.dataset_id}/download",
        json={
            "groups": [[chain.item["id"]]],
            "assets": [chain.render_asset],
            "aoi": chain.aoi,
        },
    )

    assert response.status_code == 200, response.text
    names = zipfile.ZipFile(BytesIO(response.content)).namelist()
    assert NOTICE_FILENAME in names
    assert any(name.endswith(".tif") for name in names), names


def test_the_notice_carries_attribution_and_terms_of_this_entry(
    client: TestClient, chain: Chain
) -> None:
    """Point 4 and point 9 meet here: the licence text travels with the pixels."""
    response = client.post(
        f"/collections/{chain.dataset_id}/download",
        json={"groups": [[chain.item["id"]]], "assets": [chain.render_asset], "aoi": chain.aoi},
    )
    assert response.status_code == 200, response.text

    notice = zipfile.ZipFile(BytesIO(response.content)).read(NOTICE_FILENAME).decode("utf-8")
    licence = chain.config.license
    if licence.attribution_required:
        stem = (licence.attribution_modified or licence.attribution_unmodified or "").split("{year}")[0].strip()
        assert stem and stem in notice
    if licence.terms is not None:
        assert licence.terms.url in notice


async def test_the_whole_chain_runs_for_this_entry(chain: Chain, client: TestClient) -> None:
    """Point 9 itself: one item, found (or, materialized, created), displayed and
    downloaded, in that order."""
    if chain.config.source.item_holding is ItemHolding.MATERIALIZED:
        outcome = await materialize_items(chain.config, gateway=chain.gateway, known_version=None)
        (found,) = outcome.items
    else:
        page = await search_items(
            chain.dataset_id, SearchParams(limit=10), gateway=chain.gateway, registry=chain.registry
        )
        (found,) = page.items

    zoom, x, y = chain.tile
    tile = client.get(
        f"/collections/{chain.dataset_id}/items/{found['id']}/tiles/WebMercatorQuad/{zoom}/{x}/{y}.png",
        params={"asset": chain.render_asset},
    )
    assert tile.status_code == 200, tile.text

    crop = client.post(
        f"/collections/{chain.dataset_id}/download",
        json={"groups": [[found["id"]]], "assets": [chain.render_asset], "aoi": chain.aoi},
    )
    assert crop.status_code == 200, crop.text
    assert NOTICE_FILENAME in zipfile.ZipFile(BytesIO(crop.content)).namelist()


# --------------------------------------------------------------------------------
# What the chain refuses, so point 9 cannot pass by accident.
# --------------------------------------------------------------------------------


def test_an_asset_on_a_host_the_entry_does_not_name_is_refused(
    client: TestClient, chain: Chain
) -> None:
    """The allowlist is part of the chain, not a layer the fixtures step around."""
    chain.item["assets"][synthetic_chain.item_asset_key(chain.config, chain.render_asset)] = {
        "href": "https://elsewhere.example.invalid/products/mini.tif"
    }
    zoom, x, y = chain.tile
    response = client.get(
        f"/collections/{chain.dataset_id}/items/{chain.item['id']}"
        f"/tiles/WebMercatorQuad/{zoom}/{x}/{y}.png",
        params={"asset": chain.render_asset},
    )
    assert response.status_code == 502, response.text


def test_an_aoi_outside_the_item_downloads_nothing(client: TestClient, chain: Chain) -> None:
    """The item has a real footprint, so an AOI elsewhere is refused before any read."""
    outside = {"type": "Polygon", "coordinates": [[[50, 50], [51, 50], [51, 51], [50, 51], [50, 50]]]}
    response = client.post(
        f"/collections/{chain.dataset_id}/download",
        json={"groups": [[chain.item["id"]]], "assets": [chain.render_asset], "aoi": outside},
    )
    assert response.status_code == 400, response.text
    assert not chain.read_addresses(), "nothing may be read for an AOI that touches no item"


def test_a_format_without_a_synthetic_asset_is_a_failure_not_a_skip(
    valid_config: DatasetConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A third format must fail point 9 loudly until someone writes its fixture."""
    from dataclasses import replace

    from earthx.catalog.registry import DataFormat

    with pytest.raises(UnsupportedFormat, match="legacy"):
        synthetic_chain.build(replace(valid_config, format=DataFormat.LEGACY), tmp_path, monkeypatch)


def test_an_entry_without_a_standard_visualisation_has_no_display_step(
    valid_config: DatasetConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    with pytest.raises(UnsupportedFormat, match="standard visualisation"):
        synthetic_chain.build(replace(valid_config, default_render=None), tmp_path, monkeypatch)
