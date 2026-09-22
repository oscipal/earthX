"""Band addressing and level choice, wired through `api.tiler._resolve_asset_path`.

`test_tiler_zarr.py` proves the tile route serves a Zarr dataset end to end, over
a store addressed the M2-09a way (the href's own last segment is the variable).
This module is the M2-09b-2 case: a dataset whose `ZarrInfo.variable_separator`
means an item asset (`SR_10m`) names a *group*, and the tile URL's asset key
carries the variable after the separator (plan §10 F2) — and, together with it,
that a requested resolution picks a `multiscales` level (§12.11 point 2).

`_resolve_asset_path` is exercised directly rather than through the tile route:
what is being checked here is which group and variable it built, which the PNG
bytes of a rendered tile would not show directly.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from earthx.api.tiler import _resolve_asset_path, _target_gsd
from earthx.catalog.datasets import SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3
from earthx.catalog.registry import DataFormat, ZarrInfo
from earthx.gateway import Policy
from earthx.readers.zarr_reader import ZarrReader
from tests.earthx.readers import mini_zarr_composite, mini_zarr_multiscales
from tests.earthx.readers.mini_zarr_composite import GROUP as COMPOSITE_GROUP
from tests.earthx.readers.mini_zarr_multiscales import BASE_URL, GROUPS, HOST, ITEM_CRS, PARENT_GROUP, group_size

DATASET = "synthetic-zarr-groups"
ITEM = "SYNTH_GROUPS_20260102T100000"
ITEM_ASSET = "SR_10m"

CONFIG = replace(
    SENTINEL_2_L2A,
    dataset_id=DATASET,
    format=DataFormat.ZARR,
    source=replace(SENTINEL_2_L2A.source, asset_hosts=(HOST,)),
    zarr=ZarrInfo(variable_separator=":", multiscales_convention="test"),
)

STAC_ITEM: dict[str, Any] = {
    "id": ITEM,
    "properties": {"proj:code": ITEM_CRS},
    "assets": {ITEM_ASSET: {"href": f"{BASE_URL}/{PARENT_GROUP}/r10m"}},
}

# A second, distinct dataset id/config sharing the same host — for the one test
# that needs three real, distinguishable bands rather than the multiscales store's
# single "b04" (`mini_zarr_composite.py`).
COMPOSITE_DATASET = "synthetic-zarr-composite-render"
COMPOSITE_CONFIG = replace(CONFIG, dataset_id=COMPOSITE_DATASET)
COMPOSITE_STAC_ITEM: dict[str, Any] = {
    "id": ITEM,
    "properties": {"proj:code": ITEM_CRS},
    "assets": {ITEM_ASSET: {"href": f"{BASE_URL}/{COMPOSITE_GROUP}"}},
}


@pytest.fixture(scope="module")
def composite_store_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return mini_zarr_composite.build_mini_zarr_composite(tmp_path_factory.mktemp("zarr-composite-render") / "mini.zarr")


@pytest.fixture
def composite_requests(composite_store_root: Path, monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    return mini_zarr_composite.serve_store(composite_store_root, monkeypatch)


def composite_state() -> Any:
    return SimpleNamespace(
        earthx_registry=SimpleNamespace(get=lambda dataset_id: COMPOSITE_CONFIG),
        earthx_policy=Policy(allowed_hosts=frozenset({HOST})),
        earthx_resolver=mini_zarr_composite.from_memory,
    )


@pytest.fixture(scope="module")
def store_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return mini_zarr_multiscales.build_mini_zarr_multiscales(tmp_path_factory.mktemp("zarr-groups") / "mini.zarr")


@pytest.fixture
def requests(store_root: Path, monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    return mini_zarr_multiscales.serve_store(store_root, monkeypatch)


def state() -> Any:
    return SimpleNamespace(
        earthx_registry=SimpleNamespace(get=lambda dataset_id: CONFIG),
        earthx_policy=Policy(allowed_hosts=frozenset({HOST})),
        earthx_resolver=mini_zarr_multiscales.from_memory,
    )


class TestTheAssetKeySplitsIntoGroupAndVariable:
    def test_the_variable_after_the_separator_is_read_out_of_the_group_the_asset_names(
        self, requests: list[httpx.Request]
    ) -> None:
        built = _resolve_asset_path(state(), STAC_ITEM, config=CONFIG, item=ITEM, asset="SR_10m:b04")
        assert built.group == f"{PARENT_GROUP}/r10m"
        assert built.variable == "b04"

    def test_an_asset_key_without_the_separator_is_refused_as_a_bad_request(
        self, requests: list[httpx.Request]
    ) -> None:
        """The caller's own query parameter is malformed — 400, not a 502 about the
        item's own addresses."""
        with pytest.raises(HTTPException) as raised:
            _resolve_asset_path(state(), STAC_ITEM, config=CONFIG, item=ITEM, asset="SR_10m")
        assert raised.value.status_code == 400
        assert "variable" in raised.value.detail

    def test_an_unknown_item_asset_before_the_separator_is_a_404_not_a_502(
        self, requests: list[httpx.Request]
    ) -> None:
        with pytest.raises(HTTPException) as raised:
            _resolve_asset_path(state(), STAC_ITEM, config=CONFIG, item=ITEM, asset="nope:b04")
        assert raised.value.status_code == 404


class TestTargetGsdPicksTheLevel:
    """`_resolve_asset_path` only carries `target_gsd` onto the asset it builds —
    the level swap itself happens once the reader opens (`test_zarr_levels.py`
    proves that in isolation); here it is proven end to end, asset build through
    to the group actually read."""

    def test_a_target_gsd_swaps_the_group_for_a_coarser_level(self, requests: list[httpx.Request]) -> None:
        built = _resolve_asset_path(
            state(), STAC_ITEM, config=CONFIG, item=ITEM, asset="SR_10m:b04", target_gsd=GROUPS["r60m"]
        )
        assert built.group == f"{PARENT_GROUP}/r10m"
        assert built.target_gsd == GROUPS["r60m"]
        with ZarrReader(built) as reader:
            assert reader.input.sizes["x"] == group_size(GROUPS["r60m"])

    def test_without_a_target_gsd_the_items_own_group_is_kept(self, requests: list[httpx.Request]) -> None:
        built = _resolve_asset_path(state(), STAC_ITEM, config=CONFIG, item=ITEM, asset="SR_10m:b04")
        assert built.target_gsd is None
        with ZarrReader(built) as reader:
            assert reader.input.sizes["x"] == group_size(GROUPS["r10m"])


def _request(path: str, path_params: dict[str, object]) -> Request:
    return Request({"type": "http", "path": path, "path_params": path_params, "headers": [], "method": "GET"})


class TestTargetGsdFromTheRequest:
    """adr/0007 §12.10/§12.11 point 8: what picks a level for a route, without that
    route's dependency having to say so itself (`request.path_params`, not a
    parameter of ``dataset_asset_path`` — see its own docstring)."""

    def test_statistics_asks_for_the_coarsest_level_there_is(self) -> None:
        request = _request(f"/collections/{DATASET}/items/{ITEM}/statistics", {})
        assert _target_gsd(request, STAC_ITEM) == float("inf")

    def test_a_route_without_a_tile_or_statistics_shape_asks_for_nothing(self) -> None:
        request = _request(f"/collections/{DATASET}/items/{ITEM}/preview", {})
        assert _target_gsd(request, STAC_ITEM) is None

    def test_a_tile_route_computes_a_real_resolution_from_its_own_bounds(self) -> None:
        request = _request(
            f"/collections/{DATASET}/items/{ITEM}/tiles/WebMercatorQuad/10/551/351",
            {"z": 10, "x": 551, "y": 351, "tileMatrixSetId": "WebMercatorQuad"},
        )
        gsd = _target_gsd(request, STAC_ITEM)
        assert gsd is not None
        assert gsd > 0

    def test_a_tile_further_from_the_equator_computes_a_finer_resolution(self) -> None:
        """adr/0007 §12.10: the real ground resolution of a Web Mercator tile scales
        with `cos(latitude)` — the same `z` further north covers less real ground."""
        equator = _request(
            f"/collections/{DATASET}/items/{ITEM}/tiles/WebMercatorQuad/10/551/511",
            {"z": 10, "x": 551, "y": 511, "tileMatrixSetId": "WebMercatorQuad"},
        )
        near_pole = _request(
            f"/collections/{DATASET}/items/{ITEM}/tiles/WebMercatorQuad/10/551/100",
            {"z": 10, "x": 551, "y": 100, "tileMatrixSetId": "WebMercatorQuad"},
        )
        assert _target_gsd(near_pole, STAC_ITEM) < _target_gsd(equator, STAC_ITEM)

    def test_an_unknown_tile_matrix_set_falls_back_to_no_target_rather_than_failing(self) -> None:
        request = _request(
            f"/collections/{DATASET}/items/{ITEM}/tiles/NotATms/10/551/351",
            {"z": 10, "x": 551, "y": 351, "tileMatrixSetId": "NotATms"},
        )
        assert _target_gsd(request, STAC_ITEM) is None

    def test_an_item_without_a_crs_falls_back_to_no_target(self) -> None:
        request = _request(
            f"/collections/{DATASET}/items/{ITEM}/tiles/WebMercatorQuad/10/551/351",
            {"z": 10, "x": 551, "y": 351, "tileMatrixSetId": "WebMercatorQuad"},
        )
        assert _target_gsd(request, {**STAC_ITEM, "properties": {}}) is None


class TestTheDefaultRenderAssetKeyRoundTrips:
    """`SENTINEL_2_L2A_ZARR3.default_render.assets` is exactly
    ``("SR_10m:b04,b03,b02",)`` (M2-09b-2's post-release fix) — proven here through
    the same `_resolve_asset_path` a live tile request calls, not assumed."""

    def test_the_exact_default_render_asset_key_builds_a_three_band_asset(
        self, composite_requests: list[httpx.Request]
    ) -> None:
        (asset_key,) = SENTINEL_2_L2A_ZARR3.default_render.assets
        built = _resolve_asset_path(
            composite_state(), COMPOSITE_STAC_ITEM, config=COMPOSITE_CONFIG, item=ITEM, asset=asset_key
        )
        assert built.variable == "b04,b03,b02"
        with ZarrReader(built) as reader:
            image = reader.preview()
        assert image.count == 3
