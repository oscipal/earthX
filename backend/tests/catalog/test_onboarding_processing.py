"""Onboarding checklist point 9, version v2, per registry entry: one operator run against fixtures.

Fassung v2 (M4 Q14, adr/0014 §11) replaces the chain of v1, which stays as its own test in
``test_onboarding_endtoend.py`` because it checks the clip. The chain here has six links:

1. the search through the entry's own adapter,
2. ``access.resolve_asset``,
3. an order, accepted by ``api`` as a validated, hashed recipe,
4. the run of the core (T2),
5. a readable result COG with transformed metadata, ``recipe.json`` and ``citation.bib``,
6. for band math: the tile (T1) equals the job on the native level.

Which operator proves the point for which entry is a decision of this test, not a property of the
dataset (adr/0014 §11): :data:`OPERATOR_FOR`. An entry without one fails
:func:`test_every_registry_entry_has_an_operator`. What is synthetic is spelled out in
`synthetic_chain.py`; here the stores additionally carry ``scale``/``offset`` or CF attributes like
the real sources, otherwise the scaling rule of §5.4 would go unchecked.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import numpy
import pytest
import rasterio
from fastapi.testclient import TestClient
from morecantile import Tile
from rasterio.io import MemoryFile
from rasterio.warp import transform as warp_transform
from rasterio.warp import transform_bounds
from rio_cogeo.cogeo import cog_validate
from rio_tiler.constants import WEB_MERCATOR_TMS, WGS84_CRS
from rio_tiler.io import Reader

from earthx.access.resolve import ResolvedAsset, resolve_asset
from earthx.adapters import ADAPTER_SPECS, SearchParams, materialize_items, search_items
from earthx.api.citation import citation_bib
from earthx.api.intake import AcceptedOrder, accept_order, job_recipe_json
from earthx.api.tiler import build_app
from earthx.catalog.datasets import REGISTRY
from earthx.catalog.registry import DataFormat, DatasetConfig, DatasetRegistry, ItemHolding
from earthx.gateway import Gateway
from earthx.processing import RunResult, run
from earthx.processing.operators import REGISTRY as OPERATORS
from earthx.processing.operators import applicable
from earthx.processing.recipe import recipe_hash
from tests.catalog import synthetic_chain
from tests.catalog.synthetic_chain import UnsupportedFormat
from tests.catalog.test_onboarding_checklist import CHECKED_ELSEWHERE, CHECKLIST
from tests.earthx.processing import sources
from tests.earthx.readers import mini_dem, mini_zarr, mini_zarr_cf

#: Q14: band math for the two Sentinel-2 entries, reprojection for the DEM.
OPERATOR_FOR = {
    "sentinel-2-c1-l2a": "band_math",
    "sentinel-2-l2a-zarr3": "band_math",
    "cop-dem-glo-30": "reproject",
}

ENTRIES = list(REGISTRY)
BAND_MATH_ENTRIES = [config for config in ENTRIES if OPERATOR_FOR.get(config.dataset_id) == "band_math"]

SIDE = 300  # pixels of a synthetic Sentinel-2 band
ZOOM = 14  # a level that reads the native resolution of both Sentinel-2 stores
ZARR_ASSET = "SR_10m:b04,b08"
REPROJECT = {"crs": "EPSG:32632", "resolution": 100.0, "resampling": "bilinear"}
BAND = {"data_type": "uint16", "nodata": 0, "raster:scale": sources.SCALE, "raster:offset": sources.OFFSET}


def missing_assignments(dataset_ids: Iterable[str]) -> list[str]:
    return sorted(set(dataset_ids) - set(OPERATOR_FOR))


@dataclass(frozen=True)
class Scenario:
    """One entry wired to synthetic stores, and the order that runs one operator on them."""

    config: DatasetConfig
    registry: DatasetRegistry
    item: dict[str, Any]
    assets: list[str]
    aoi: dict[str, Any]
    step: dict[str, Any]
    #: Where the scaling comes from (adr/0014 §5.4): ``item``, ``store-cf`` or ``none``.
    scaling: str
    gateway: Gateway
    #: Names of the bands the result carries.
    result_bands: list[str]
    #: The tile for link 6 (band math only).
    tile: tuple[int, int, int] | None

    @property
    def order(self) -> str:
        return json.dumps(
            {
                "recipe_version": 1,
                "inputs": [
                    {"name": "input", "dataset": self.config.dataset_id, "groups": [[self.item["id"]]], "assets": self.assets}
                ],
                "aoi": self.aoi,
                "steps": [self.step],
                "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
            }
        )


def _ndvi(red: str, nir: str) -> dict[str, Any]:
    params = {"expression": f"({nir} - {red}) / ({nir} + {red})"}
    return {"op": "band_math", "op_version": 1, "params": params}


def _whole(bounds: tuple[float, ...]) -> dict[str, Any]:
    """The AOI that is the whole store, so the job covers every pixel a tile may ask for."""
    return sources.aoi_around(*bounds)


def _central_tile(bounds: tuple[float, ...], crs: str) -> tuple[int, int, int]:
    west, south, east, north = transform_bounds(crs, WGS84_CRS, *bounds)
    tile = WEB_MERCATOR_TMS.tile((west + east) / 2, (south + north) / 2, ZOOM)
    return tile.z, tile.x, tile.y


def build(config: DatasetConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Scenario:
    """A scenario for one entry, or :class:`UnsupportedFormat` — never a quiet pass."""
    if config.format is DataFormat.COG and config.source.item_holding is ItemHolding.MATERIALIZED:
        return _dem(config, tmp_path, monkeypatch)
    if config.format is DataFormat.COG:
        return _cog_pair(config, tmp_path, monkeypatch)
    if config.format is DataFormat.ZARR:
        return _zarr_pair(config, tmp_path, monkeypatch)
    raise UnsupportedFormat(f"no synthetic store for format {config.format.value!r}")


def _federated(
    config: DatasetConfig, item: dict[str, Any], assets: list[str], aoi: dict[str, Any], step: dict[str, Any], **rest: Any
) -> Scenario:
    synthetic = replace(config, source=replace(config.source, asset_hosts=(synthetic_chain.HOST,)))
    gateway, _ = synthetic_chain.gateway_answering_search(synthetic, item)
    return Scenario(
        config=synthetic,
        registry=DatasetRegistry((synthetic,)),
        item=item,
        assets=assets,
        aoi=aoi,
        step=step,
        gateway=gateway,
        **rest,
    )


def _cog_pair(config: DatasetConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Scenario:
    files = {
        name: sources.build_band_cog(tmp_path / f"{name}.tif", sources.ramp(SIDE, SIDE, base))
        for name, base in (("red", 1200), ("nir", 3400))
    }
    sources.serve({sources.url(name): path for name, path in files.items()}, monkeypatch)
    synthetic_chain.resolve_from_memory(monkeypatch)
    bounds = (
        sources.ORIGIN_X,
        sources.ORIGIN_Y - SIDE * sources.RESOLUTION,
        sources.ORIGIN_X + SIDE * sources.RESOLUTION,
        sources.ORIGIN_Y,
    )
    item = synthetic_chain.stac_item("red", sources.url("red"), bounds, sources.RESOLUTION)
    item["assets"] = {
        name: {
            "href": sources.url(name),
            "gsd": sources.RESOLUTION,
            "raster:bands": [BAND],
            "file:checksum": f"1220{name:0<64}",
        }
        for name in files
    }
    return _federated(
        config, item, ["red", "nir"], _whole(bounds), _ndvi("red", "nir"),
        scaling="item", result_bands=["band_math"], tile=_central_tile(bounds, sources.CRS),
    )


def _zarr_pair(config: DatasetConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Scenario:
    root = mini_zarr_cf.build_mini_zarr_cf(tmp_path / "mini.zarr")
    sources.serve({}, monkeypatch, zarr_root=root)
    synthetic_chain.resolve_from_memory(monkeypatch)
    bounds = mini_zarr_cf.store_bounds()
    # The item carries no scaling, like the real EOPF items: the store's CF attributes do (F7a).
    item = synthetic_chain.stac_item("SR_10m", mini_zarr_cf.GROUP_URL, bounds, mini_zarr_cf.RESOLUTION_M)
    item["properties"]["updated"] = "2026-01-03T00:00:00Z"
    return _federated(
        config, item, [ZARR_ASSET], _whole(bounds), _ndvi("b04", "b08"),
        scaling="store-cf", result_bands=["band_math"], tile=_central_tile(bounds, mini_zarr_cf.ITEM_CRS),
    )


def _dem(config: DatasetConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Scenario:
    sources.serve({}, monkeypatch)  # the resolver; the COG itself is served below
    mini_dem.serve_dem(mini_dem.build_mini_dem(tmp_path / "mini_dem.tif"), monkeypatch)
    synthetic_chain.resolve_from_memory(monkeypatch)
    synthetic = replace(
        config, source=replace(config.source, endpoint=f"https://{synthetic_chain.HOST}", asset_hosts=(synthetic_chain.HOST,))
    )
    item = synthetic_chain.dem_item(mini_dem.TILE_NAME, mini_dem.BOUNDS, config=synthetic, gsd=30.0)
    gateway, _ = synthetic_chain.gateway_answering_materialize(synthetic, item)
    return Scenario(
        config=synthetic,
        registry=DatasetRegistry((synthetic,)),
        item=item,
        assets=["data"],
        aoi=synthetic_chain.aoi_wgs84(mini_dem.BOUNDS),
        step={"op": "reproject", "op_version": 2, "params": REPROJECT},
        scaling="none",
        gateway=gateway,
        result_bands=["data"],
        tile=None,
    )


@dataclass(frozen=True)
class Walk:
    """Everything the six links produced."""

    found: dict[str, Any]
    ref: ResolvedAsset
    accepted: AcceptedOrder
    result: RunResult
    ticks: list[tuple[int, int]]
    recipe_json: dict[str, Any]
    citation: str


async def _found_and_accepted(s: Scenario) -> tuple[dict[str, Any], AcceptedOrder]:
    if s.config.source.item_holding is ItemHolding.MATERIALIZED:
        outcome = await materialize_items(s.config, adapters=ADAPTER_SPECS, gateway=s.gateway, known_version=None)
        (found,) = outcome.items
    else:
        page = await search_items(s.config, SearchParams(limit=10), adapters=ADAPTER_SPECS, gateway=s.gateway)
        (found,) = page.items

    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        return found

    accepted = await accept_order(
        s.order, registry=s.registry, operators=OPERATORS, item_source=item_source, gateway=s.gateway
    )
    return found, accepted


def walk(s: Scenario, workdir: Path) -> Walk:
    found, accepted = asyncio.run(_found_and_accepted(s))
    ref = resolve_asset(found, s.config, s.assets[0])
    ticks: list[tuple[int, int]] = []
    workdir.mkdir()
    result = run(accepted.recipe, workdir=workdir, progress=lambda done, total: ticks.append((done, total)))
    now = datetime.now(UTC)
    document = job_recipe_json(
        accepted.recipe.model_dump(mode="json"),
        config=s.config,
        result={"engine": result.engine, "scaling": [applied.model_dump(mode="json") for applied in result.scaling]},
        started=now,
        finished=now,
    )
    return Walk(
        found=found,
        ref=ref,
        accepted=accepted,
        result=result,
        ticks=ticks,
        recipe_json=json.loads(document),
        citation=citation_bib(s.config, downloaded=date.today()).decode("utf-8"),
    )


@pytest.fixture(params=ENTRIES, ids=[config.dataset_id for config in ENTRIES])
def scenario(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Scenario:
    (tmp_path / "stores").mkdir()
    return build(request.param, tmp_path / "stores", monkeypatch)


@pytest.fixture
def walked(scenario: Scenario, tmp_path: Path) -> Walk:
    return walk(scenario, tmp_path / "job")


@pytest.fixture(params=BAND_MATH_ENTRIES, ids=[config.dataset_id for config in BAND_MATH_ENTRIES])
def band_math(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Scenario:
    (tmp_path / "stores").mkdir()
    return build(request.param, tmp_path / "stores", monkeypatch)


# --------------------------------------------------------------------------------
# The guards: a point that cannot pass by accident.
# --------------------------------------------------------------------------------


def test_this_module_is_the_one_the_checklist_points_at() -> None:
    assert CHECKED_ELSEWHERE[9] == __name__
    assert "Fassung v2" in CHECKLIST[9]


def test_every_registry_entry_has_an_operator() -> None:
    assert missing_assignments(config.dataset_id for config in ENTRIES) == []


def test_a_fourth_entry_without_an_operator_is_found() -> None:
    """The guard names the entry; ``test_every_registry_entry_has_an_operator`` turns that into a failure."""
    assert missing_assignments([*OPERATOR_FOR, "fourth-dataset"]) == ["fourth-dataset"]


def test_every_assigned_operator_exists_and_applies_to_its_entry() -> None:
    for config in ENTRIES:
        operator = OPERATORS.operator(OPERATOR_FOR[config.dataset_id], 2 if OPERATOR_FOR[config.dataset_id] == "reproject" else 1)
        params = operator.params.model_validate(REPROJECT if operator.op == "reproject" else {"expression": "a + b"})
        assert applicable(operator, config, params) == [], config.dataset_id


def test_a_format_without_a_synthetic_store_fails_instead_of_passing(
    valid_config: DatasetConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(UnsupportedFormat, match="legacy"):
        build(replace(valid_config, format=DataFormat.LEGACY), tmp_path, monkeypatch)


# --------------------------------------------------------------------------------
# Links 1 to 5, per entry.
# --------------------------------------------------------------------------------


def test_the_search_finds_the_item_through_the_entrys_own_adapter(scenario: Scenario, walked: Walk) -> None:
    """Link 1. The item that went on is the one the adapter returned, not the fixture's own."""
    assert walked.found["id"] == scenario.item["id"]


def test_the_asset_resolves_to_a_reader_and_a_host_the_entry_names(scenario: Scenario, walked: Walk) -> None:
    """Link 2."""
    expected = "zarr" if scenario.config.format is DataFormat.ZARR else "cog"
    assert walked.ref.reader == expected
    assert walked.ref.dataset_id == scenario.config.dataset_id
    assert walked.ref.href.startswith(f"https://{synthetic_chain.HOST}/")
    assert (walked.ref.variable is not None) == (expected == "zarr")


def test_the_order_becomes_a_validated_hashed_recipe_that_carries_the_scaling_source(
    scenario: Scenario, walked: Walk
) -> None:
    """Link 3. The recipe has an id of its own and a hash that does not depend on it (adr/0014 §4.4)."""
    recipe = walked.accepted.recipe
    assert recipe.recipe_id
    assert re.fullmatch(r"c1:[0-9a-f]{64}", recipe_hash(recipe))
    assert recipe_hash(recipe.model_copy(update={"recipe_id": "another"})) == recipe_hash(recipe)
    assert [step.op for step in recipe.steps] == [OPERATOR_FOR[scenario.config.dataset_id]]
    assert {entry.scaling for entry in recipe.inputs[0].resolved} == {scenario.scaling}
    assert walked.ref.href in {entry.asset.href for entry in recipe.inputs[0].resolved}
    if scenario.config.source.item_holding is not ItemHolding.MATERIALIZED:
        assert all(entry.version is not None for entry in recipe.inputs[0].resolved)
        assert walked.accepted.cacheable


def test_the_core_ran_block_by_block_and_said_where_the_scaling_came_from(scenario: Scenario, walked: Walk) -> None:
    """Link 4."""
    assert walked.ticks and walked.ticks[-1][0] == walked.ticks[-1][1] == walked.result.blocks
    assert [applied.source for applied in walked.result.scaling] == [scenario.scaling] * len(walked.result.scaling)
    assert walked.result.valid_pixels > 0


def test_the_result_is_a_readable_cog_with_transformed_metadata(scenario: Scenario, walked: Walk) -> None:
    """Link 5, first half."""
    result = walked.result
    is_valid, errors, _ = cog_validate(str(result.path))
    assert is_valid, errors
    with rasterio.open(result.path) as dataset:
        assert dataset.count == len(scenario.result_bands) and dataset.dtypes[0] == "float32"
        assert (dataset.width, dataset.height) == (result.meta.width, result.meta.height)
        crs = dataset.crs.to_string()
    assert [band.name for band in result.meta.bands] == scenario.result_bands
    assert result.properties["processing:lineage"].startswith(scenario.step["op"].replace("_", " "))
    if scenario.step["op"] == "reproject":
        assert crs == REPROJECT["crs"] and result.meta.resampled is True
        assert result.properties["earthx:resampled"] is True


def test_recipe_json_and_citation_are_there_and_say_what_ran(scenario: Scenario, walked: Walk) -> None:
    """Link 5, second half."""
    document = walked.recipe_json
    assert document["recipe_id"] == walked.accepted.recipe.recipe_id
    assert [step["op"] for step in document["steps"]] == [scenario.step["op"]]
    assert document["provenance"]["kind"] == "job" and document["provenance"]["engine"] == walked.result.engine
    assert {entry["source"] for entry in document["provenance"]["scaling"]} == {scenario.scaling}
    assert walked.citation.startswith("@misc{") and scenario.config.title in walked.citation


# --------------------------------------------------------------------------------
# Link 6: for band math, the tile is the job on the native level (adr/0014 §6.4).
# --------------------------------------------------------------------------------


def _client(s: Scenario, found: dict[str, Any]) -> TestClient:
    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        return found

    @asynccontextmanager
    async def lifespan(app):
        app.state.earthx_item_source = item_source
        yield

    app = build_app(s.registry, lifespan=lifespan)
    app.state.earthx_resolver = mini_zarr.from_memory
    return TestClient(app)


def _decode(content: bytes) -> numpy.ma.MaskedArray:
    """Band 1 of the GeoTIFF tile is the data, band 2 the alpha, whose sign is the mask."""
    with MemoryFile(content) as memory, memory.open() as dataset:
        data, alpha = dataset.read(1), dataset.read(2)
    return numpy.ma.masked_array(data, mask=alpha <= 0)


def _zarr_boundary_distance(tile: tuple[int, int, int]) -> numpy.ndarray:
    """Per tile pixel, how far its centre lies from the nearest source pixel boundary (in source pixels)."""
    bounds = WEB_MERCATOR_TMS.xy_bounds(Tile(x=tile[1], y=tile[2], z=tile[0]))
    step = (bounds.right - bounds.left) / 256
    grid_x, grid_y = numpy.meshgrid(
        bounds.left + (numpy.arange(256) + 0.5) * step, bounds.top - (numpy.arange(256) + 0.5) * step
    )
    x, y = warp_transform("EPSG:3857", mini_zarr_cf.ITEM_CRS, grid_x.ravel().tolist(), grid_y.ravel().tolist())
    col = (numpy.array(x).reshape(256, 256) - mini_zarr_cf.ORIGIN_X) / mini_zarr_cf.RESOLUTION_M
    row = (mini_zarr_cf.ORIGIN_Y - numpy.array(y).reshape(256, 256)) / mini_zarr_cf.RESOLUTION_M
    return numpy.minimum(numpy.abs(col - numpy.round(col)), numpy.abs(row - numpy.round(row)))


def test_the_tile_equals_the_job_on_the_native_level(band_math: Scenario, tmp_path: Path) -> None:
    s = band_math
    walked = walk(s, tmp_path / "job")
    assert s.tile is not None
    zoom, x, y = s.tile
    asset = "&".join(f"asset={quote(asset)}" for asset in s.assets)
    params = quote(json.dumps(s.step["params"]))
    with _client(s, walked.found) as client:
        response = client.get(
            f"/collections/{s.config.dataset_id}/items/{walked.found['id']}/tiles/WebMercatorQuad/{zoom}/{x}/{y}.tif"
            f"?{asset}&op=band_math&op_version=1&params={params}"
        )
    assert response.status_code == 200, response.text
    from_tile = _decode(response.content)
    with Reader(str(walked.result.path)) as reader:
        from_job = reader.tile(x, y, zoom, resampling_method="nearest", tilesize=256).array[0]

    assert (~from_tile.mask).sum() > 1000
    job_mask = numpy.ma.getmaskarray(from_job)
    differing = (from_tile.mask != job_mask) | (~from_tile.mask & ~job_mask & (from_tile.data != from_job.data))
    if s.scaling == "item":
        assert not differing.any()  # COG: one warp on both sides, no tolerance (§6.4)
    else:
        # Zarr: where nearest may pick the neighbour, within 0.125 source pixel of a boundary (§15d).
        assert not (differing & (_zarr_boundary_distance(s.tile) > 0.125)).any()


def test_a_tile_of_a_different_expression_is_not_the_job(band_math: Scenario, tmp_path: Path) -> None:
    """The comparison can fail: another expression gives other pixels."""
    s = band_math
    walked = walk(s, tmp_path / "job")
    assert s.tile is not None
    zoom, x, y = s.tile
    other = {"expression": s.step["params"]["expression"].replace("-", "+", 1)}
    asset = "&".join(f"asset={quote(asset)}" for asset in s.assets)
    with _client(s, walked.found) as client:
        response = client.get(
            f"/collections/{s.config.dataset_id}/items/{walked.found['id']}/tiles/WebMercatorQuad/{zoom}/{x}/{y}.tif"
            f"?{asset}&op=band_math&op_version=1&params={quote(json.dumps(other))}"
        )
    assert response.status_code == 200, response.text
    from_tile = _decode(response.content)
    with Reader(str(walked.result.path)) as reader:
        from_job = reader.tile(x, y, zoom, resampling_method="nearest", tilesize=256).array[0]
    valid = ~from_tile.mask & ~numpy.ma.getmaskarray(from_job)
    assert (from_tile.data[valid] != from_job.data[valid]).any()
