"""The mosaic tile of the tiler: the scenes of one overpass as one surface (M4-17b, plan M4-17 §4, §5).

The real app (`api.tiler.build_app`) over synthetic scenes of zone 32 and 33, served through the real
`readers`: ``sources.serve`` swaps only the last step of the COG path for a local file per address, so
the registry, the licence tier, ``check_url`` and the allowlist all run for real. Each scene is a flat
``uint8`` COG with a value of its own, so that the winner of a pixel can be read off it. The item source
is a double that records what it was asked, and so is the source of items by id; the selections live in memory
(`mosaic_selections.py`; their SQL is tested against a real database).

A mosaic is asked for in two steps since M5-30b part 3: the selection of its scenes is created
(``POST /collections/{dataset}/mosaic``), then its tiles and TileJSON are asked for by the id that came back.

The part that needs a clock and a gateway — the item fetches — is in `test_mosaic_item_fetches.py`.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
from collections.abc import Callable, Iterator
from contextlib import ExitStack, asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy
import psycopg
import pytest
import rasterio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pyproj import Transformer
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles
from shapely.geometry import box, mapping

from earthx.access import mosaic_tiles as mosaic_reading
from earthx.access.crop_rules import mosaic_order
from earthx.adapters.errors import UnknownCollection
from earthx.api import mosaic_tiles
from earthx.api import tiler as tiler_module
from earthx.api.tiler import MOSAIC_ROUTER_PREFIX, MOSAIC_SELECTION_ROUTE, build_app
from earthx.catalog.mosaic_selection import selection_id
from earthx.catalog.registry import DatasetRegistry, LicenseTier, OverviewMode, OverviewResampling, SearchCapabilities
from earthx.gateway import UpstreamError, check_url
from tests.catalog.entries import COP_DEM_GLO_30, SENTINEL_2_L2A
from tests.conftest import own_log_text
from tests.earthx.access.test_mosaic_tiles import SEAM_X, SEAM_Y, TILE, TMS, TOP
from tests.earthx.access.test_mosaic_tiles import _at as value_at
from tests.earthx.api.mosaic_selections import MemorySelections, batch_source_of, create
from tests.earthx.processing import sources
from tests.earthx.processing import test_mosaic as job
from tests.earthx.readers import mini_zarr

ZONE_32, ZONE_33 = "EPSG:32632", "EPSG:32633"
DATASET = "synthetic-mosaic"
DISPLAY_DATASET = "synthetic-display"
NO_VIEWER = "synthetic-no-viewer"
CATALOG_ONLY = "synthetic-catalog"
DEM = COP_DEM_GLO_30.dataset_id
BASE = f"/collections/{DATASET}/mosaic"
ASSET = "visual"
POOL = object()  # a stand-in for the cache pool: the route only asks whether there is one

SYNTHETIC = replace(SENTINEL_2_L2A, dataset_id=DATASET, source=replace(SENTINEL_2_L2A.source, asset_hosts=(sources.HOST,)))
REGISTRY = DatasetRegistry(
    (
        SYNTHETIC,
        replace(SYNTHETIC, dataset_id=NO_VIEWER, viewer=None, search_capabilities=SearchCapabilities(evaluate=False, aoi_coverage=False)),
        replace(
            SYNTHETIC,
            dataset_id=CATALOG_ONLY,
            viewer=None,
            search_capabilities=SearchCapabilities(evaluate=False, aoi_coverage=False),
            license=replace(SYNTHETIC.license, tier=LicenseTier.CATALOG),
        ),
        replace(SYNTHETIC, dataset_id=DISPLAY_DATASET, license=replace(SYNTHETIC.license, tier=LicenseTier.DISPLAY)),
        COP_DEM_GLO_30,
    )
)

ROWS = 1000


def _released(*, min_zoom: int, max_zoom: int) -> Any:
    """The viewer of ``SYNTHETIC`` released for another zoom range; a pyramid serves what lies below it (adr/0032 §9)."""
    return replace(
        SYNTHETIC.viewer,
        min_zoom=min_zoom,
        max_zoom=max_zoom,
        overview=OverviewMode.PYRAMID,
        overview_resampling=OverviewResampling.AVERAGE,
    )


def _cog(path: Path, crs: str, left: float, width_m: float, value: int, *, top: float = TOP, bands: int = 1) -> Path:
    """A flat ``uint8`` COG of ``crs`` from ``left`` to ``left + width_m`` in x, 10 km tall, with ``value``."""
    width = round(width_m / 10)
    plain = path.with_suffix(".plain.tif")
    profile = {
        "driver": "GTiff", "dtype": "uint8", "count": bands, "height": ROWS, "width": width, "crs": crs,
        "transform": from_origin(left, top, 10.0, 10.0), "nodata": 0,
    }  # fmt: skip
    with rasterio.open(plain, "w", **profile) as destination:
        destination.write(numpy.full((bands, ROWS, width), value, dtype="uint8"))
    cog_translate(plain, path, cog_profiles.get("deflate"), quiet=True)
    plain.unlink()
    return path


def _item(
    item_id: str,
    crs: str,
    left: float,
    width_m: float,
    *,
    top: float = TOP,
    overpass: str = "D1",
    assets: tuple[str, ...] = (ASSET,),
) -> dict[str, Any]:
    """The STAC item of a scene made by :func:`_cog`: footprint, CRS, overpass and the address of each asset."""
    west, south, east, north = transform_bounds(crs, "EPSG:4326", left, top - ROWS * 10, left + width_m, top)
    return {
        "id": item_id,
        "type": "Feature",
        "bbox": [west, south, east, north],
        "geometry": mapping(box(west, south, east, north)),
        "properties": {"proj:code": crs, "datetime": "2026-07-24T10:00:00Z", "s2:datatake_id": overpass},
        "assets": {asset: {"href": sources.url(f"{item_id}-{asset}")} for asset in assets},
    }


class Scenes:
    """The scenes a test serves: the item of each, the file behind it, and what the double was asked."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.items: dict[str, dict[str, Any]] = {}
        self.files: dict[str, Path] = {}
        self.fetched: list[str] = []  # the items fetched one by one, as a tile fetches the ones it reads
        self.batches: list[list[str]] = []  # the calls that fetched items by id, as the creation of a selection does
        self.selections = MemorySelections()
        self.cleared: list[str] = []  # the addresses that passed `check_url`
        self.opened: list[str] = []  # the scenes a tile opened to read, by item id
        self.served = False

    def add(self, item_id: str, crs: str, left: float, width_m: float, value: int, **options: Any) -> None:
        bands = options.pop("bands", 1)
        top = options.get("top", TOP)
        file = _cog(self.root / f"{item_id}.tif", crs, left, width_m, value, top=top, bands=bands)
        self.items[item_id] = _item(item_id, crs, left, width_m, **options)
        self.files[sources.url(f"{item_id}-{ASSET}")] = file

    def alias(self, item_id: str, original: str, **changes: Any) -> None:
        """Another item that reads the file of ``original``: only its id (and what ``changes`` sets) differs."""
        item = json.loads(json.dumps(self.items[original]))
        item["id"] = item_id
        item["properties"].update(changes.pop("properties", {}))
        item.update(changes)
        item["assets"] = {asset: {"href": sources.url(f"{item_id}-{asset}")} for asset in item["assets"]}
        self.items[item_id] = item
        self.files[sources.url(f"{item_id}-{ASSET}")] = self.files[sources.url(f"{original}-{ASSET}")]

    async def source(self, dataset_id: str, item_id: str) -> dict[str, Any]:
        self.fetched.append(item_id)
        if dataset_id not in REGISTRY:
            raise UnknownCollection(dataset_id)
        if dataset_id == DEM or item_id not in self.items:
            raise UpstreamError(404, "not found")
        return json.loads(json.dumps(self.items[item_id]))

    async def batch_source(self, dataset_id: str, item_ids: Any) -> list[dict[str, Any]]:
        if dataset_id not in REGISTRY:
            raise UnknownCollection(dataset_id)
        return await batch_source_of({} if dataset_id == DEM else self.items, self.batches)(dataset_id, item_ids)


@pytest.fixture
def scenes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Scenes:
    return Scenes(tmp_path)


def _serve(scenes: Scenes, monkeypatch: pytest.MonkeyPatch) -> None:
    """Let the readers open the files of ``scenes`` (once, however many apps a test builds)."""
    if scenes.served:
        return
    scenes.served = True
    scenes.cleared = sources.serve(scenes.files, monkeypatch)
    original = mosaic_reading.open_asset

    def recording(scene: Any, **options: Any) -> Any:
        scenes.opened.append(scene.item_id)
        return original(scene, **options)

    monkeypatch.setattr(mosaic_reading, "open_asset", recording)
    for module in ("earthx.readers.zarr_reader", "earthx.readers.cog"):
        monkeypatch.setattr(
            f"{module}.check_url", lambda url, policy, **_: check_url(url, policy, resolve=mini_zarr.from_memory)
        )


def _app(scenes: Scenes, *, pool: Any = POOL) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.earthx_item_source = scenes.source
        app.state.earthx_item_batches = scenes.batch_source
        app.state.earthx_cache_pool = pool
        app.state.earthx_mosaic_selections = None if pool is None else scenes.selections
        yield

    app = build_app(REGISTRY, lifespan=lifespan)
    app.state.earthx_resolver = mini_zarr.from_memory
    return app


@pytest.fixture
def client(scenes: Scenes, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., TestClient]]:
    """Builds the real app over the scenes added so far; every client is closed with the test."""
    stack = ExitStack()

    def build(pool: Any = POOL) -> TestClient:
        _serve(scenes, monkeypatch)
        return stack.enter_context(TestClient(_app(scenes, pool=pool)))

    with stack:
        yield build


def _select(
    api: TestClient, items: list[str], assets: tuple[str, ...] = (ASSET,), dataset: str = DATASET
) -> str:
    """The id of the selection of ``items`` read from ``assets``, created through the route."""
    return create(api, dataset, items, assets)


def _tile_path(
    selection: str, z: int = TILE.z, x: int = TILE.x, y: int = TILE.y, *, extension: str = "npy", dataset: str = DATASET
) -> str:
    return f"/collections/{dataset}/mosaic/{selection}/tiles/WebMercatorQuad/{z}/{x}/{y}.{extension}"


def _tilejson_path(selection: str, dataset: str = DATASET) -> str:
    return f"/collections/{dataset}/mosaic/{selection}/WebMercatorQuad/tilejson.json"


def _query(**extra: str) -> list[tuple[str, str]]:
    return list(extra.items())


def _array(response: Any) -> numpy.ndarray:
    assert response.status_code == 200, response.text
    return numpy.load(io.BytesIO(response.content))


def _seam(scenes: Scenes) -> None:
    """Two scenes of zone 32 either side of the seam in the middle of the tile, and one far away."""
    scenes.add("WEST", ZONE_32, SEAM_X - 4000.0, 4000.0, 100)
    scenes.add("EAST", ZONE_32, SEAM_X, 4000.0, 200)
    scenes.add("FAR", ZONE_32, SEAM_X + 60_000.0, 4000.0, 250)


class TestOneSurfaceOverASceneBoundary:
    """The acceptance of M4-17: a tile over a seam is one surface, not two."""

    def test_two_scenes_over_the_seam_are_one_surface_without_a_gap(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        tile = _array(api.get(_tile_path(_select(api, ["WEST", "EAST"]))))
        assert value_at(tile, SEAM_X - 500.0) == 100
        assert value_at(tile, SEAM_X + 500.0) == 200
        assert all(value_at(tile, x) is not None for x in numpy.arange(SEAM_X - 1500.0, SEAM_X + 1500.0, 30.0))

    def test_the_order_of_the_ids_given_does_not_change_the_id_or_the_bytes(self, scenes: Scenes, client) -> None:
        scenes.add("A", ZONE_32, SEAM_X - 4000.0, 5000.0, 100)
        scenes.add("B", ZONE_32, SEAM_X - 1000.0, 5000.0, 200)
        api = client()
        forward, backward = _select(api, ["A", "B"]), _select(api, ["B", "A"])
        assert forward == backward
        first, second = api.get(_tile_path(forward)), api.get(_tile_path(backward))
        assert first.content == second.content
        # where both have data the scene that sorts first wins, whatever the creation says
        assert value_at(_array(first), SEAM_X - 500.0) == 100

    def test_a_scene_away_from_the_tile_is_not_opened(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        _array(api.get(_tile_path(_select(api, ["WEST", "EAST", "FAR"]))))
        assert sorted(scenes.opened) == ["EAST", "WEST"]
        assert not [address for address in scenes.cleared if "FAR" in address]  # its address was never even cleared

    def test_a_tile_that_is_full_after_the_first_portion_does_not_open_the_next(self, scenes: Scenes, client) -> None:
        names = [f"S{n}" for n in range(1, 7)]
        scenes.add("S1", ZONE_32, SEAM_X - 5000.0, 10_000.0, 10)
        for name in names[1:]:
            scenes.alias(name, "S1")
        api = client()
        _array(api.get(_tile_path(_select(api, names))))
        assert sorted(scenes.opened) == ["S1", "S2", "S3", "S4"]

    def test_two_fresh_apps_answer_the_same_url_with_the_same_bytes(
        self, scenes: Scenes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _seam(scenes)
        _serve(scenes, monkeypatch)
        answers = []
        with TestClient(_app(scenes)) as api:
            chosen = _select(api, ["WEST", "EAST"])
        for _ in range(2):
            with TestClient(_app(scenes)) as api:  # the selection is in the store, not in the app
                answers.append(api.get(_tile_path(chosen)).content)
        assert answers[0] == answers[1]


class TestTheOrderIsTheMosaicJobs:
    def test_a_scene_in_the_target_zone_wins_over_one_in_the_other_zone_that_sorts_first(
        self, scenes: Scenes, client
    ) -> None:
        """"A" lies in zone 33 and covers the tile, "B" and "C" in zone 32 cover it between them: zone 32 is the
        target, so B and C are read first and A fills nothing — the job's rule, not the order of the ids."""
        x33, y33 = Transformer.from_crs(ZONE_32, ZONE_33, always_xy=True).transform(SEAM_X, SEAM_Y)
        scenes.add("A", ZONE_33, x33 - 5000.0, 10_000.0, 1, top=y33 + 5000.0)
        scenes.add("B", ZONE_32, SEAM_X - 5000.0, 5000.0, 2)
        scenes.add("C", ZONE_32, SEAM_X, 5000.0, 3)
        api = client()
        tile = _array(api.get(_tile_path(_select(api, ["A", "B", "C"]))))
        assert value_at(tile, SEAM_X - 1000.0) == 2
        assert value_at(tile, SEAM_X + 1000.0) == 3
        assert 1 not in numpy.unique(tile[0][tile[-1] != 0])


class TestTheTileJsonNamesWhatTheSelectionStored:
    def test_it_names_the_data_type_the_scenes_share_and_fetches_no_item(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        for item in scenes.items.values():
            item["assets"][ASSET]["raster:bands"] = [{"data_type": "uint8", "nodata": 0}]
        api = client()
        body = api.get(_tilejson_path(_select(api, ["WEST", "EAST"]))).json()
        assert body["data_type"] == "uint8" and body["earthx:order"] == ["EAST", "WEST"]
        assert scenes.fetched == []

    def test_scenes_that_scale_the_asset_differently_are_refused_at_the_creation(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        scenes.items["WEST"]["assets"][ASSET]["raster:bands"] = [{"data_type": "uint8", "raster:scale": 0.5}]
        scenes.items["EAST"]["assets"][ASSET]["raster:bands"] = [{"data_type": "uint8", "raster:scale": 2.0}]
        response = client().post(BASE, json={"items": ["WEST", "EAST"], "assets": [ASSET]})
        assert response.status_code == 422
        assert response.json()["detail"] == f"the scenes of the mosaic scale {ASSET!r} differently"
        assert scenes.selections.rows == {}


class TestOneOrderForEveryAsset:
    """M5-30b part 3, F6: the selection stores one order, taken from the CRS of the scenes, for all its assets.

    A Sentinel-2 item names its CRS once, in ``proj:code`` of the item (the Earth Search form; ``proj:epsg`` is the older
    spelling of the same), and every asset of the scene lies in it. An overpass over two UTM zones, as over Austria, has
    scenes of zone 32 and of zone 33, and each scene's assets lie in that scene's zone.
    """

    NAMES_32, NAMES_33 = ("A32", "B32"), ("C33", "D33", "E33")

    def _overpass(self, scenes: Scenes) -> None:
        x33, y33 = Transformer.from_crs(ZONE_32, ZONE_33, always_xy=True).transform(SEAM_X, SEAM_Y)
        for n, name in enumerate(self.NAMES_32):
            scenes.add(name, ZONE_32, SEAM_X - 60_000.0 + n * 20_000.0, 10_000.0, 10 + n, assets=("red", "nir"))
        for n, name in enumerate(self.NAMES_33):
            scenes.add(name, ZONE_33, x33 + n * 20_000.0, 10_000.0, 20 + n, top=y33 + 5000.0, assets=("red", "nir"))

    def test_the_two_zones_of_one_overpass_are_taken_and_ordered_like_the_job_for_every_asset(
        self, scenes: Scenes, client
    ) -> None:
        self._overpass(scenes)
        assert {item["properties"]["proj:code"] for item in scenes.items.values()} == {ZONE_32, ZONE_33}
        assert all("proj:code" not in asset for item in scenes.items.values() for asset in item["assets"].values())
        everything = [*self.NAMES_32, *self.NAMES_33]
        by_zone = {name: item["properties"]["proj:code"] for name, item in scenes.items.items()}
        expected = mosaic_order(by_zone)
        assert expected == [*self.NAMES_33, *self.NAMES_32]  # zone 33 has the most scenes, so it is the target
        api = client()
        stored = []
        for assets in (("red", "nir"), ("nir",), ("red",)):
            response = api.post(BASE, json={"items": everything, "assets": list(assets)})
            assert response.status_code == 201, response.text
            stored.append(scenes.selections.rows[response.json()["id"]][1]["order"])
            if len(assets) == 1:  # a TileJSON without steps names one asset
                assert api.get(response.json()["tilejson"]).json()["earthx:order"] == expected
        assert stored == [expected] * 3

    def test_assets_of_one_scene_in_different_crs_are_a_422_and_nothing_is_stored(
        self, scenes: Scenes, client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Items do not name a CRS per asset, so the resolution gives them one only if it changes; then one scene
        could belong to two zones, and the one stored order could not stand for both assets."""
        self._overpass(scenes)
        resolve = tiler_module._resolve_ref

        def resolve_nir_of_a32_in_zone_33(stac_item: Any, *, config: Any, item: str, asset: str) -> Any:
            ref = resolve(stac_item, config=config, item=item, asset=asset)
            return replace(ref, crs=ZONE_33) if (item, asset) == ("A32", "nir") else ref

        monkeypatch.setattr(tiler_module, "_resolve_ref", resolve_nir_of_a32_in_zone_33)
        api = client()
        everything = [*self.NAMES_32, *self.NAMES_33]
        response = api.post(BASE, json={"items": everything, "assets": ["red", "nir"]})
        assert response.status_code == 422, response.text
        assert "'A32'" in response.json()["detail"] and "different coordinate reference systems" in response.json()["detail"]
        assert scenes.selections.rows == {}
        assert api.post(BASE, json={"items": everything, "assets": ["red"]}).status_code == 201  # one asset cannot differ


class TestTheTargetZoneComesFromTheWholeList:
    def test_a_tile_that_touches_only_some_scenes_still_uses_the_target_zone_of_all(self, scenes: Scenes, client) -> None:
        """Two zone-32 scenes far away make zone 32 the target; X (32) and Y, Z (33) lie at the tile.

        Over the whole list zone 32 is the target and X wins where it has data. Computed from the scenes of
        the tile alone, zone 33 would be the target and Y would win there (plan §4.4). The selection takes the order
        from the whole list once, and the tile reads it from there."""
        x33, y33 = Transformer.from_crs(ZONE_32, ZONE_33, always_xy=True).transform(SEAM_X, SEAM_Y)
        scenes.add("F1", ZONE_32, SEAM_X + 60_000.0, 4000.0, 9)
        scenes.add("F2", ZONE_32, SEAM_X + 70_000.0, 4000.0, 9)
        scenes.add("X", ZONE_32, SEAM_X - 5000.0, 5000.0, 1)
        scenes.add("Y", ZONE_33, x33 - 5000.0, 10_000.0, 2, top=y33 + 5000.0)
        scenes.add("Z", ZONE_33, x33 - 5000.0, 10_000.0, 3, top=y33 + 5000.0)
        api = client()
        tile = _array(api.get(_tile_path(_select(api, ["F1", "F2", "X", "Y", "Z"]))))
        assert value_at(tile, SEAM_X - 1000.0) == 1
        assert value_at(tile, SEAM_X + 1000.0) == 2
        assert sorted(scenes.fetched) == ["X", "Y", "Z"]  # the two far away were not fetched for this tile


class TestTheRuleOfTheMosaicJob:
    """S5: the tile picks the scene the mosaic job picks over the same list — on its own scenes and zones."""

    @pytest.fixture
    def overpass(self, scenes: Scenes) -> Scenes:
        """The scenes of the mosaic job tests: A and B overlap in zone 32, C is zone 33 over B's east edge."""
        for name in "ABC":
            crs, x, y, width, height = job.GEOMETRY[name]
            west, south, east, north = transform_bounds(crs, "EPSG:4326", x, y - height * 10, x + width * 10, y)
            scenes.items[name] = {
                "id": name,
                "type": "Feature",
                "bbox": [west, south, east, north],
                "geometry": mapping(box(west, south, east, north)),
                "properties": {"proj:code": crs, "datetime": "2026-07-24T10:00:00Z", "s2:datatake_id": "D1"},
                "assets": {ASSET: {"href": sources.url(f"{name}-{ASSET}")}},
            }
            file = job._cog(scenes.root / f"{name}.tif", name)
            scenes.files[sources.url(f"{name}-{ASSET}")] = file
            scenes.files[sources.url(f"{name}_red")] = file  # where the job's recipe looks for it
        return scenes

    @pytest.mark.parametrize("asked", [["A", "B", "C"], ["C", "B", "A"]])
    def test_the_same_scene_wins_at_the_same_places_as_in_the_job(
        self, overpass: Scenes, client, asked: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = client()
        chosen = _select(api, asked)
        crs_by_item = {name: job.GEOMETRY[name][0] for name in "ABC"}
        assert mosaic_order(crs_by_item) == ["A", "B", "C"]
        result = job._run(job._recipe(mosaic_order(crs_by_item)), tmp_path)
        probes = {"A": 601000.0, "A+B": 603500.0, "B": 605000.0, "B+C": 606500.0, "C": 608000.0}
        y = sources.ORIGIN_Y - 1500.0
        with rasterio.open(result.path) as dataset:
            data = dataset.read(masked=True)
            from_job = {label: job._scene_of(job._at(dataset, data, x, y)) for label, x in probes.items()}
        to_wgs = Transformer.from_crs(ZONE_32, "EPSG:4326", always_xy=True)
        from_tile = {}
        for label, x in probes.items():
            cell = TMS.tile(*to_wgs.transform(x, y), 12)
            tile = _array(api.get(_tile_path(chosen, cell.z, cell.x, cell.y)))
            raw = _raw_at(tile, cell, x, y)
            from_tile[label] = "A" if raw < 10000 else ("B" if raw < 30000 else "C")
        assert from_tile == from_job
        assert from_tile == {"A": "A", "A+B": "A", "B": "B", "B+C": "B", "C": "C"}


def _raw_at(tile: numpy.ndarray, cell: Any, x: float, y: float) -> int:
    """The value of a tile of the job scenes at a zone-32 point (metres)."""
    left, bottom, right, top = TMS.xy_bounds(cell)
    mx, my = Transformer.from_crs(ZONE_32, "EPSG:3857", always_xy=True).transform(x, y)
    size = tile.shape[-1]
    return int(tile[0, int((top - my) / (top - bottom) * size), int((mx - left) / (right - left) * size)])


class TestTheTileJson:
    def test_it_names_the_extent_the_zoom_range_and_the_order_a_tile_reads(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        chosen = _select(api, ["EAST", "FAR", "WEST"])
        response = api.get(_tilejson_path(chosen))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["earthx:order"] == ["EAST", "FAR", "WEST"]
        assert (body["minzoom"], body["maxzoom"]) == (0, 19)
        west, south, east, north = body["bounds"]
        assert west < scenes.items["WEST"]["bbox"][0] + 1e-9 and east > scenes.items["FAR"]["bbox"][2] - 1e-9
        assert south < north
        (template,) = body["tiles"]
        assert template.startswith(f"http://testserver{BASE}/{chosen}/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}")
        assert "item=" not in template and "asset=" not in template  # the selection names both

    def test_it_fetches_no_item_and_clears_no_address(self, scenes: Scenes, client) -> None:
        """It answers from the order and the extent the selection stores (M5-30b part 3)."""
        _seam(scenes)
        api = client()
        chosen = _select(api, ["EAST", "FAR", "WEST"])
        assert api.get(_tilejson_path(chosen)).status_code == 200
        assert scenes.fetched == [] and scenes.opened == []
        assert not [address for address in scenes.cleared if any(name in address for name in ("EAST", "FAR", "WEST"))]

    def test_its_tiles_are_512_px_unless_asked_for_256(self, scenes: Scenes, client) -> None:
        """The viewer draws a mosaic at 512 px (NM4-29 §15); the document hands out the same tiles."""
        _seam(scenes)
        api = client()
        chosen = _select(api, ["WEST", "EAST"])
        (default,) = api.get(_tilejson_path(chosen)).json()["tiles"]
        (asked,) = api.get(_tilejson_path(chosen), params=_query(tilesize="256")).json()["tiles"]
        assert "tilesize=512" in default and "tilesize=256" in asked

    def test_a_tile_of_512_px_is_512_px(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        assert _array(api.get(_tile_path(_select(api, ["WEST", "EAST"])), params=_query(tilesize="512"))).shape[-2:] == (
            512,
            512,
        )

    def test_the_order_is_the_jobs_not_the_creations(self, scenes: Scenes, client) -> None:
        scenes.add("A", ZONE_33, 500_000.0, 4000.0, 1, top=5_700_000.0)
        scenes.add("B", ZONE_32, SEAM_X, 4000.0, 2)
        scenes.add("C", ZONE_32, SEAM_X + 3000.0, 4000.0, 3)
        api = client()
        body = api.get(_tilejson_path(_select(api, ["A", "B", "C"]))).json()
        assert body["earthx:order"] == ["B", "C", "A"]  # zone 32 has two scenes, so it is the target

    def test_a_zoom_asked_for_must_stay_in_the_range_the_mosaic_serves(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        path = _tilejson_path(_select(api, ["WEST", "EAST"]))
        narrowed = api.get(path, params=_query(minzoom="10"))
        assert narrowed.status_code == 200 and narrowed.json()["minzoom"] == 10
        # Every released level has a mosaic since M5-30b (adr/0032 §6.2); the registry releases this dataset from z0.
        low = api.get(path, params=_query(minzoom="0"))
        assert low.status_code == 200 and low.json()["minzoom"] == 0
        above = api.get(path, params=_query(maxzoom="25"))
        assert above.status_code == 400


class TestAnswersToWrongRequests:
    @pytest.mark.parametrize(
        ("items", "why"),
        [
            (["WEST"], "one item"),
            ([f"S{n}" for n in range(mosaic_tiles.MAX_SELECTION_ITEMS + 1)], "one more than the limit"),
            (["WEST", "WEST"], "twice the same item"),
        ],
    )
    def test_the_number_of_items_is_two_to_2000_each_once_and_nothing_is_fetched(
        self, scenes: Scenes, client, items: list[str], why: str
    ) -> None:
        _seam(scenes)
        response = client().post(BASE, json={"items": items, "assets": [ASSET]})
        assert response.status_code == 400, why
        assert scenes.fetched == [] and scenes.batches == []

    def test_a_missing_item_is_a_404_that_names_it(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        response = client().post(BASE, json={"items": ["WEST", "NOWHERE"], "assets": [ASSET]})
        assert response.status_code == 404
        assert "NOWHERE" in response.json()["detail"]

    def test_a_missing_asset_on_one_scene_is_a_404(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        del scenes.items["EAST"]["assets"][ASSET]
        scenes.items["EAST"]["assets"]["other"] = {"href": sources.url("EAST-other")}
        response = client().post(BASE, json={"items": ["WEST", "EAST"], "assets": [ASSET]})
        assert response.status_code == 404
        assert scenes.opened == [] and scenes.selections.rows == {}

    def test_scenes_of_two_overpasses_are_a_422_that_names_the_ones_apart(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        scenes.items["EAST"]["properties"]["s2:datatake_id"] = "D2"
        response = client().post(BASE, json={"items": ["WEST", "EAST"], "assets": [ASSET]})
        assert response.status_code == 422
        assert "EAST" in response.json()["detail"] and "one overpass" in response.json()["detail"]
        assert scenes.opened == [] and scenes.selections.rows == {}

    def test_an_item_that_lacks_the_overpass_is_the_sources_502(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        del scenes.items["EAST"]["properties"]["s2:datatake_id"]
        assert client().post(BASE, json={"items": ["WEST", "EAST"], "assets": [ASSET]}).status_code == 502

    def test_more_scenes_than_the_budget_are_read_up_to_it_and_the_rest_is_said_in_a_header(
        self, scenes: Scenes, client
    ) -> None:
        """adr/0032 §6.2: the first scenes of the mosaic's order up to the budget, the same picture for the same URL."""
        scenes.add("S00", ZONE_32, SEAM_X - 5000.0, 10_000.0, 10)
        names = ["S00"] + [f"S{n:02d}" for n in range(1, mosaic_tiles.TILE_FILE_BUDGET + 2)]
        for name in names[1:]:
            scenes.alias(name, "S00")
        api = client()
        chosen = _select(api, names)
        first = api.get(_tile_path(chosen))
        assert first.status_code == 200, first.text
        assert first.headers[mosaic_tiles.PARTIAL_HEADER] == "2"
        assert "no-store" not in first.headers.get("cache-control", "")
        assert len(scenes.fetched) == mosaic_tiles.TILE_FILE_BUDGET  # the 32 it reads, not the 34 of the selection
        again = api.get(_tile_path(_select(api, list(reversed(names)))))
        assert again.content == first.content
        # within the budget the header is not there
        within = api.get(_tile_path(_select(api, names[: mosaic_tiles.TILE_FILE_BUDGET])))
        assert within.status_code == 200 and mosaic_tiles.PARTIAL_HEADER not in within.headers

    def test_a_tile_whose_time_runs_out_is_not_stored_anywhere(
        self, scenes: Scenes, client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _seam(scenes)
        monkeypatch.setattr(mosaic_tiles, "TILE_TIME_BUDGET_S", 1e-9)
        api = client()
        response = api.get(_tile_path(_select(api, ["WEST", "EAST"])))
        assert response.status_code == 503, response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.headers[mosaic_tiles.PARTIAL_HEADER] == "time"

    def test_the_time_budget_does_not_reach_the_tilejson(
        self, scenes: Scenes, client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _seam(scenes)
        monkeypatch.setattr(mosaic_tiles, "TILE_TIME_BUDGET_S", 1e-9)
        api = client()
        tilejson = api.get(_tilejson_path(_select(api, ["WEST", "EAST"])))
        assert tilejson.status_code == 200 and mosaic_tiles.PARTIAL_HEADER not in tilejson.headers

    def test_the_file_budget_counts_the_assets_of_each_scene(self) -> None:
        outlines = {f"S{n}": box(-1.0, -1.0, 1.0, 1.0) for n in range(20)}
        grid = (TMS, TMS.tile(0.0, 0.0, 10))
        order = sorted(outlines)
        one = mosaic_tiles.scenes_touching(order, outlines, grid)
        four = mosaic_tiles.scenes_touching(order, outlines, grid, files_per_scene=4)
        assert (len(one.read), one.left_out) == (20, 0)
        assert four.read == order[: mosaic_tiles.TILE_FILE_BUDGET // 4]
        assert four.left_out == 20 - mosaic_tiles.TILE_FILE_BUDGET // 4
        with pytest.raises(ValueError):
            mosaic_tiles.scenes_touching(order, outlines, grid, files_per_scene=0)

    def test_a_tile_no_scene_touches_is_a_404_and_fetches_nothing(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        chosen = _select(api, ["FAR", "WEST"])
        assert api.get(_tile_path(chosen)).status_code == 200
        scenes.opened.clear()
        scenes.fetched.clear()
        away = TMS.tile(0.0, 0.0, 12)
        response = api.get(_tile_path(chosen, away.z, away.x, away.y))
        assert response.status_code == 404
        assert scenes.opened == [] and scenes.fetched == []

    def test_below_z8_it_is_a_mosaic_too(self, scenes: Scenes, client) -> None:
        """adr/0032 §6.2: the first zoom level of a mosaic is the dataset's, not z8."""
        _seam(scenes)
        low = TMS.tile(*TMS.lnglat(*TMS.xy_bounds(TILE)[:2]), 3)
        api = client()
        response = api.get(_tile_path(_select(api, ["WEST", "EAST"]), low.z, low.x, low.y))
        assert response.status_code == 200, response.text
        assert mosaic_tiles.PARTIAL_HEADER not in response.headers

    def test_a_level_the_dataset_is_not_released_for_is_a_400_before_any_item_is_fetched(
        self, scenes: Scenes, client
    ) -> None:
        _seam(scenes)
        api = client()
        response = api.get(_tile_path(_select(api, ["WEST", "EAST"]), 20, 1, 1))
        assert response.status_code == 400
        assert scenes.fetched == []

    def test_a_tile_outside_the_matrix_is_a_404_before_any_item_is_fetched(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        response = api.get(_tile_path(_select(api, ["WEST", "EAST"]), 9, 5000, 1))
        assert response.status_code == 404
        assert scenes.fetched == []

    def test_a_dataset_without_a_released_range_is_a_501_before_anything_is_fetched(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        path = f"/collections/{NO_VIEWER}/mosaic"
        assert api.post(path, json={"items": ["WEST", "EAST"], "assets": [ASSET]}).status_code == 501
        assert api.get(f"{path}/{'0' * 32}/tiles/WebMercatorQuad/10/1/1.png").status_code == 501
        assert api.get(f"{path}/{'0' * 32}/WebMercatorQuad/tilejson.json").status_code == 501
        assert scenes.fetched == [] and scenes.batches == []

    def test_a_dataset_released_only_below_z8_has_its_mosaic_there(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        chosen = _select(api, ["WEST", "EAST"])
        api.app.state.earthx_registry = DatasetRegistry(
            (replace(SYNTHETIC, viewer=_released(min_zoom=2, max_zoom=7)),)
        )
        body = api.get(_tilejson_path(chosen)).json()
        assert (body["minzoom"], body["maxzoom"]) == (2, 7)
        assert api.get(_tile_path(chosen)).status_code == 400  # z12 is not released
        assert scenes.fetched == []

    def test_a_dataset_released_from_a_higher_level_starts_its_mosaic_there(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        chosen = _select(api, ["WEST", "EAST"])
        api.app.state.earthx_registry = DatasetRegistry(
            (replace(SYNTHETIC, viewer=_released(min_zoom=10, max_zoom=14)),)
        )
        body = api.get(_tilejson_path(chosen)).json()
        assert (body["minzoom"], body["maxzoom"]) == (10, 14)

    def test_a_dataset_below_licence_tier_display_is_a_403_before_anything_is_fetched(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        path = f"/collections/{CATALOG_ONLY}/mosaic"
        assert api.post(path, json={"items": ["WEST", "EAST"], "assets": [ASSET]}).status_code == 403
        assert api.get(f"{path}/{'0' * 32}/tiles/WebMercatorQuad/10/1/1.png").status_code == 403
        assert scenes.fetched == [] and scenes.batches == []

    def test_a_display_tier_dataset_gets_its_mosaic(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        chosen = _select(api, ["WEST", "EAST"], dataset=DISPLAY_DATASET)
        response = api.get(_tile_path(chosen, dataset=DISPLAY_DATASET))
        assert response.status_code == 200, response.text

    def test_an_unknown_dataset_is_a_404(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        assert api.post("/collections/no-such-dataset/mosaic", json={"items": ["WEST", "EAST"], "assets": [ASSET]}).status_code == 404
        assert api.get(f"/collections/no-such-dataset/mosaic/{'0' * 32}/tiles/WebMercatorQuad/10/1/1.png").status_code == 404
        assert scenes.batches == []

    def test_an_address_the_dataset_does_not_declare_is_a_502_and_nothing_is_read(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        scenes.items["EAST"]["assets"][ASSET]["href"] = "https://elsewhere.example.invalid/east.tif"
        api = client()
        response = api.get(_tile_path(_select(api, ["WEST", "EAST"])))
        assert response.status_code == 502
        assert "asset_hosts" in response.json()["detail"]
        assert scenes.opened == []

    def test_scenes_with_another_number_of_bands_are_a_422_and_not_a_crash(self, scenes: Scenes, client) -> None:
        scenes.add("ONE", ZONE_32, SEAM_X - 4000.0, 4000.0, 100)
        scenes.add("TWO", ZONE_32, SEAM_X, 4000.0, 200, bands=2)
        api = client()
        response = api.get(_tile_path(_select(api, ["ONE", "TWO"])))
        assert response.status_code == 422, response.text
        assert "number of bands" in response.json()["detail"]


class TestNothingIsFetchedForARequestThatIsRefused:
    """Otto, 22.10.2026: the format, z/x/y, the tile matrix set and every other parameter come first."""

    @pytest.mark.parametrize(
        ("path", "extra"),
        [
            (f"{BASE}/SEL/tiles/WebMercatorQuad/{TILE.z}/{TILE.x}/{TILE.y}.xyz", {}),
            (f"{BASE}/SEL/tiles/NoSuchGrid/{TILE.z}/{TILE.x}/{TILE.y}.png", {}),
            (f"{BASE}/SEL/tiles/WorldCRS84Quad/{TILE.z}/{TILE.x}/{TILE.y}.png", {}),
            (f"{BASE}/SEL/tiles/WebMercatorQuad/{TILE.z}/x/{TILE.y}.png", {}),
            (f"{BASE}/SEL/tiles/WebMercatorQuad/abc/{TILE.x}/{TILE.y}.png", {}),
            (f"{BASE}/SEL/tiles/WebMercatorQuad/{TILE.z}/{TILE.x}/{TILE.y}.png", {"tilesize": "0"}),
            (f"{BASE}/SEL/tiles/WebMercatorQuad/{TILE.z}/{TILE.x}/{TILE.y}.png", {"tilesize": "big"}),
            (f"{BASE}/SEL/tiles/WebMercatorQuad/{TILE.z}/{TILE.x}/{TILE.y}.png", {"tilesize": "1024"}),
            (f"{BASE}/SEL/tiles/WebMercatorQuad/{TILE.z}/{TILE.x}/{TILE.y}.png", {"tilesize": "4096"}),
            (f"{BASE}/SEL/tiles/WebMercatorQuad/{TILE.z}/{TILE.x}/{TILE.y}.png", {"bidx": "first"}),
            (f"{BASE}/SEL/tiles/WebMercatorQuad/{TILE.z}/{TILE.x}/{TILE.y}.png", {"resampling": "magic"}),
            (f"{BASE}/SEL/tiles/WebMercatorQuad/{TILE.z}/{TILE.x}/{TILE.y}.png", {"padding": "wide"}),
            (f"{BASE}/SEL/NoSuchGrid/tilejson.json", {}),
            (f"{BASE}/SEL/WebMercatorQuad/tilejson.json", {"minzoom": "low"}),
            (f"{BASE}/SEL/WebMercatorQuad/tilejson.json", {"tilesize": "0"}),
            (f"{BASE}/SEL/WebMercatorQuad/tilejson.json", {"tilesize": "4096"}),
            (f"{BASE}/SEL/WebMercatorQuad/tilejson.json", {"tile_format": "gif"}),
        ],
    )
    def test_an_invalid_request_is_a_400_or_422_and_asks_the_source_for_nothing(
        self, scenes: Scenes, client, path: str, extra: dict[str, str]
    ) -> None:
        _seam(scenes)
        api = client()
        response = api.get(path.replace("SEL", _select(api, ["WEST", "EAST"])), params=_query(**extra))
        assert response.status_code in (400, 422), (path, extra, response.status_code)
        assert scenes.fetched == []

    def test_the_same_requests_without_the_fault_do_fetch(self, scenes: Scenes, client) -> None:
        """The counter counts: a valid request does ask the source for the items it reads."""
        _seam(scenes)
        api = client()
        assert api.get(_tile_path(_select(api, ["WEST", "EAST"])), params=_query(tilesize="256")).status_code == 200
        assert sorted(scenes.fetched) == ["EAST", "WEST"]


class TestWhatTheItemsCarry:
    @pytest.mark.parametrize(
        "geometry",
        [{"type": "Polygon", "coordinates": []}, {"type": "GeometryCollection", "geometries": []}, {"type": "Nope"}],
    )
    def test_an_item_with_an_empty_or_broken_outline_is_the_sources_502(
        self, scenes: Scenes, client, geometry: dict[str, Any]
    ) -> None:
        _seam(scenes)
        scenes.items["EAST"]["geometry"] = geometry
        assert client().post(BASE, json={"items": ["WEST", "EAST"], "assets": [ASSET]}).status_code == 502
        assert scenes.selections.rows == {}

    @pytest.mark.parametrize("heights", [False, True])
    def test_without_a_geometry_the_bbox_is_the_outline_with_four_or_six_numbers(
        self, scenes: Scenes, client, heights: bool
    ) -> None:
        _seam(scenes)
        for name in ("WEST", "EAST"):
            west, south, east, north = scenes.items[name]["bbox"]
            scenes.items[name]["geometry"] = None
            scenes.items[name]["bbox"] = [west, south, 0, east, north, 100] if heights else [west, south, east, north]
        api = client()
        assert _array(api.get(_tile_path(_select(api, ["WEST", "EAST"]))))[0].any()

    def test_the_outline_is_stored_as_the_item_carries_it(self, scenes: Scenes, client) -> None:
        """A geometry that is no rectangle stays what it is, and an item without one keeps its bbox (not their bounds)."""
        _seam(scenes)
        west, south, east, north = scenes.items["WEST"]["bbox"]
        triangle = {"type": "Polygon", "coordinates": [[[west, south], [east, south], [west, north], [west, south]]]}
        scenes.items["WEST"]["geometry"] = triangle
        scenes.items["EAST"]["geometry"] = None
        api = client()
        chosen = _select(api, ["WEST", "EAST"])
        _, document = scenes.selections.rows[chosen]
        assert document["outlines"]["WEST"] == {"geometry": triangle}
        assert document["outlines"]["EAST"] == {"bbox": scenes.items["EAST"]["bbox"]}
        assert sorted(document["order"]) == ["EAST", "WEST"]
        assert document["bounds"][0] <= west and document["bounds"][2] >= scenes.items["EAST"]["bbox"][2]

    def test_a_bbox_of_five_numbers_is_the_sources_502(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        scenes.items["EAST"]["geometry"] = None
        scenes.items["EAST"]["bbox"] = [0, 0, 1, 1, 2]
        assert client().post(BASE, json={"items": ["WEST", "EAST"], "assets": [ASSET]}).status_code == 502

    def test_an_item_with_neither_geometry_nor_bbox_is_the_sources_502(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        scenes.items["EAST"]["geometry"] = None
        del scenes.items["EAST"]["bbox"]
        assert client().post(BASE, json={"items": ["WEST", "EAST"], "assets": [ASSET]}).status_code == 502

    def test_a_band_chosen_with_bidx_makes_scenes_of_other_band_counts_a_mosaic(self, scenes: Scenes, client) -> None:
        scenes.add("ONE", ZONE_32, SEAM_X - 4000.0, 4000.0, 100)
        scenes.add("TWO", ZONE_32, SEAM_X, 4000.0, 200, bands=2)
        api = client()
        response = api.get(_tile_path(_select(api, ["ONE", "TWO"])), params=_query(bidx="1"))
        assert response.status_code == 200, response.text


class TestWhatTheUrlMayCarry:
    """Plan §4.1, §4.8 test 7: the selection and the display, and nothing that could name an area, an operator or an address."""

    @pytest.mark.parametrize(
        "extra",
        [
            {"bbox": "1,2,3,4"},
            {"aoi": "x"},
            {"geometry": "{}"},
            {"intersects": "{}"},
            {"url": "https://attacker.example.invalid/x.tif"},
            {"URL": "https://attacker.example.invalid/x.tif"},
            {"filter": "S_INTERSECTS(geometry,POLYGON((10.5 51.4,10.6 51.4,10.6 51.5,10.5 51.4)))"},
            {"bbox ": "1,2,3,4"},
            {"bbox-crs": "x"},
            {"anything": "else"},
            {"expression": "b1+b2"},
            {"algorithm": "hillshade"},
            {"algorithm_params": "{}"},
            {"op": "band_math"},
            {"op_version": "1"},
            {"params": "{}"},
            {"item": "WEST"},  # the selection names the scenes and the asset; the URL no longer does
            {"asset": ASSET},
        ],
    )
    def test_a_parameter_that_could_carry_an_area_or_an_address_or_half_a_step_is_a_400(
        self, scenes: Scenes, client, extra: dict[str, str]
    ) -> None:
        _seam(scenes)
        api = client()
        chosen = _select(api, ["WEST", "EAST"])
        for path in (_tile_path(chosen), _tilejson_path(chosen)):
            assert api.get(path, params=_query(**extra)).status_code == 400, path
        assert scenes.fetched == []

    @pytest.mark.parametrize(
        "item_id",
        ["../etc/passwd", "a b", "https://attacker.example.invalid/x", "a/b", "a?b=c", "", "-leading", "x" * 256],
    )
    @pytest.mark.parametrize("dataset", [DATASET, DEM])
    def test_an_item_id_that_is_no_id_is_a_400_for_a_federated_and_a_materialized_dataset(
        self, scenes: Scenes, client, dataset: str, item_id: str
    ) -> None:
        _seam(scenes)
        response = client().post(f"/collections/{dataset}/mosaic", json={"items": ["WEST", item_id], "assets": [ASSET]})
        assert response.status_code == 400
        assert item_id.strip() == "" or item_id not in response.text
        assert scenes.fetched == [] and scenes.batches == []

    @pytest.mark.parametrize(
        "assets", [[], ["a", "b", "c", "d", "e"], [ASSET, ASSET], [""], ["x" * 129]], ids=["none", "five", "twice", "empty", "long"]
    )
    def test_the_assets_are_one_to_four_each_once(self, scenes: Scenes, client, assets: list[str]) -> None:
        _seam(scenes)
        response = client().post(BASE, json={"items": ["WEST", "EAST"], "assets": assets})
        assert response.status_code == 400
        assert scenes.batches == []

    def test_two_assets_are_a_selection_but_a_tile_without_steps_reads_one(self, scenes: Scenes, client) -> None:
        scenes.add("WEST", ZONE_32, SEAM_X - 4000.0, 4000.0, 100, assets=(ASSET, "other"))
        scenes.add("EAST", ZONE_32, SEAM_X, 4000.0, 200, assets=(ASSET, "other"))
        api = client()
        chosen = _select(api, ["WEST", "EAST"], assets=(ASSET, "other"))
        response = api.get(_tile_path(chosen))
        assert response.status_code == 400 and "op" in response.json()["detail"]
        assert scenes.fetched == []

    def test_an_item_of_another_dataset_is_the_sources_404(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        response = client().post(f"/collections/{DEM}/mosaic", json={"items": ["WEST", "EAST"], "assets": [ASSET]})
        assert response.status_code == 404

    def test_the_schema_has_no_parameter_that_could_carry_an_area_or_an_address(self, scenes: Scenes, client) -> None:
        schema = client().app.openapi()
        mosaic = {path: operations for path, operations in schema["paths"].items() if path.startswith(MOSAIC_ROUTER_PREFIX)}
        assert len(mosaic) == 3  # the tile with and without a format, and the TileJSON
        names = {
            parameter["name"].lower()
            for operations in mosaic.values()
            for operation in operations.values()
            for parameter in operation["parameters"]
        }
        assert {"selection", "op", "op_version", "params"} <= names  # the steps of NM4-04
        assert not names & {"item", "asset", "url", "aoi", "bbox", "geometry", "intersects", "expression", "algorithm"}

    def test_only_the_tile_and_the_tilejson_exist_under_a_selection(self, scenes: Scenes, client) -> None:
        paths = [path for path in client().app.openapi()["paths"] if path.startswith(MOSAIC_ROUTER_PREFIX)]
        assert sorted(paths) == [
            f"{MOSAIC_ROUTER_PREFIX}/tiles/{{tileMatrixSetId}}/{{z}}/{{x}}/{{y}}",
            f"{MOSAIC_ROUTER_PREFIX}/tiles/{{tileMatrixSetId}}/{{z}}/{{x}}/{{y}}.{{format}}",
            f"{MOSAIC_ROUTER_PREFIX}/{{tileMatrixSetId}}/tilejson.json",
        ]

    def test_the_creation_is_a_post_and_its_body_schema_forbids_other_fields(self, scenes: Scenes, client) -> None:
        operations = client().app.openapi()["paths"][MOSAIC_SELECTION_ROUTE]
        assert list(operations) == ["post"]
        body = operations["post"]["requestBody"]["content"]["application/json"]["schema"]
        assert sorted(body["properties"]) == ["assets", "items"] and body["additionalProperties"] is False


class TestWithoutTheItemCache:
    """Plan §11 Auflage 3: a clear answer with its reason, never a ``500``."""

    def test_without_a_pool_a_mosaic_is_a_503_that_says_why_and_the_tile_of_one_item_goes_on(
        self, scenes: Scenes, client
    ) -> None:
        _seam(scenes)
        api = client(pool=None)
        creation = api.post(BASE, json={"items": ["WEST", "EAST"], "assets": [ASSET]})
        assert creation.status_code == 503 and "item cache" in creation.json()["detail"]
        for path in (_tile_path("0" * 32), _tilejson_path("0" * 32)):
            response = api.get(path)
            assert response.status_code == 503, path
            assert "item cache" in response.json()["detail"]
        assert scenes.fetched == [] and scenes.batches == []
        single = api.get(
            f"/collections/{DATASET}/items/WEST/tiles/WebMercatorQuad/{TILE.z}/{TILE.x}/{TILE.y}.npy",
            params={"asset": ASSET},
        )
        assert single.status_code == 200, single.text

    def test_a_materialized_dataset_without_a_pool_is_a_503_too(self, scenes: Scenes, client) -> None:
        response = client(pool=None).post(f"/collections/{DEM}/mosaic", json={"items": ["A", "B"], "assets": [ASSET]})
        assert response.status_code == 503 and "item cache" in response.json()["detail"]

    def test_a_wrong_request_is_still_a_400_without_a_pool(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client(pool=None)
        assert api.post(BASE, json={"items": ["WEST"], "assets": [ASSET]}).status_code == 400
        assert api.get(_tile_path("NOT-AN-ID")).status_code == 400

    @pytest.mark.parametrize(
        "failure",
        [
            psycopg.OperationalError("connection to server at db.internal.example failed for user secret"),
            psycopg.InterfaceError("the connection is closed"),
            psycopg.errors.UndefinedTable('relation "public.earthx_search_cache" does not exist'),
            TimeoutError(),
        ],
    )
    def test_an_item_cache_that_fails_is_a_503_and_another_failure_is_not_hidden(
        self, scenes: Scenes, client, failure: Exception, caplog: pytest.LogCaptureFixture
    ) -> None:
        _seam(scenes)

        async def failing(dataset_id: str, item_id: str) -> dict[str, Any]:
            raise failure

        api = client()
        chosen = _select(api, ["WEST", "EAST"])
        api.app.state.earthx_item_source = failing
        root = logging.getLogger()
        root.addHandler(caplog.handler)
        try:
            if isinstance(failure, psycopg.Error):
                response = api.get(_tile_path(chosen))
                assert response.status_code == 503 and "item cache" in response.json()["detail"]
                text = " ".join(own_log_text(record) + str(record.exc_info) for record in caplog.records)
                assert type(failure).__name__ in text  # a line was logged
                assert "internal.example" not in text and "secret" not in text and "earthx_search_cache" not in text
            else:
                with pytest.raises(TimeoutError):
                    api.get(_tile_path(chosen))
        finally:
            root.removeHandler(caplog.handler)

    @pytest.mark.parametrize("where", ["batch", "get", "renew", "put"])
    def test_a_database_that_fails_under_a_selection_is_a_503_without_its_text(
        self, scenes: Scenes, client, where: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        _seam(scenes)
        failure = psycopg.OperationalError("connection to server at db.internal.example failed for user secret")

        async def failing(*args: Any) -> Any:
            raise failure

        api = client()
        chosen = _select(api, ["WEST", "EAST"])
        if where == "batch":
            api.app.state.earthx_item_batches = failing
            scenes.selections.expire(chosen)
        else:
            setattr(scenes.selections, where, failing)
            if where == "put":
                scenes.selections.expire(chosen)
        root = logging.getLogger()
        root.addHandler(caplog.handler)
        try:
            if where == "get":
                response = api.get(_tile_path(chosen))
            else:
                response = api.post(BASE, json={"items": ["WEST", "EAST"], "assets": [ASSET]})
        finally:
            root.removeHandler(caplog.handler)
        assert response.status_code == 503 and "catalogue database" in response.json()["detail"]
        text = " ".join(own_log_text(record) + str(record.exc_info) for record in caplog.records)
        assert "OperationalError" in text and "internal.example" not in text and "secret" not in text


class TestTheLog:
    def test_it_says_how_many_scenes_a_tile_read_and_names_no_coordinate(
        self, scenes: Scenes, client, caplog: pytest.LogCaptureFixture
    ) -> None:
        _seam(scenes)
        api = client()  # building the app replaces the root handlers, so the capture comes after it
        root = logging.getLogger()
        root.addHandler(caplog.handler)
        try:
            chosen = _select(api, ["WEST", "EAST", "FAR"])
            assert api.get(_tile_path(chosen)).status_code == 200
        finally:
            root.removeHandler(caplog.handler)
        lines = [own_log_text(record) for record in caplog.records]
        assert any("mosaic tile reads 2 of 3 scenes" in line for line in lines), lines  # lines were logged at all
        assert any("mosaic selection created with 3 scenes" in line for line in lines), lines
        coordinates = [number for item in scenes.items.values() for number in item["bbox"]] + list(TMS.bounds(TILE))
        text = " ".join(lines)
        for value in coordinates:
            assert f"{value:.3f}" not in text and f"{value:.4f}" not in text


class TestTheSelection:
    """M5-30b part 3 (adr/0032 §10.2): the id is the hash of the content, and the URL stays the whole description."""

    def test_the_id_is_the_first_32_hex_characters_of_the_sha256_of_the_canonical_content(self) -> None:
        canonical = json.dumps({"dataset": "d", "assets": ["a", "b"], "items": ["x", "y"]}, sort_keys=True, separators=(",", ":"))
        expected = hashlib.sha256(canonical.encode()).hexdigest()[:32]
        assert selection_id("d", ["b", "a"], ["y", "x"]) == selection_id("d", ["a", "b"], ["x", "y"]) == expected
        assert canonical == '{"assets":["a","b"],"dataset":"d","items":["x","y"]}'

    def test_it_answers_201_with_the_id_and_where_its_tiles_are_and_200_where_it_exists(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        body = {"items": ["EAST", "WEST"], "assets": [ASSET]}
        created = api.post(BASE, json=body)
        assert created.status_code == 201, created.text
        chosen = created.json()["id"]
        assert chosen == selection_id(DATASET, [ASSET], ["WEST", "EAST"])
        assert created.json() == {
            "id": chosen,
            "tiles": f"{BASE}/{chosen}/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}",
            "tilejson": f"{BASE}/{chosen}/WebMercatorQuad/tilejson.json",
        }
        again = api.post(BASE, json={"items": ["WEST", "EAST"], "assets": [ASSET]})
        assert again.status_code == 200 and again.json() == created.json()
        assert scenes.selections.renewed == [chosen]  # the second one only moved the end out

    def test_creating_one_that_exists_asks_the_source_for_nothing(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        _select(api, ["WEST", "EAST"])
        asked = len(scenes.batches)
        _select(api, ["EAST", "WEST"])
        assert len(scenes.batches) == asked

    def test_another_asset_or_another_dataset_is_another_id(self, scenes: Scenes, client) -> None:
        scenes.add("WEST", ZONE_32, SEAM_X - 4000.0, 4000.0, 100, assets=(ASSET, "other"))
        scenes.add("EAST", ZONE_32, SEAM_X, 4000.0, 200, assets=(ASSET, "other"))
        api = client()
        ids = {
            _select(api, ["WEST", "EAST"]),
            _select(api, ["WEST", "EAST"], assets=("other",)),
            _select(api, ["WEST", "EAST"], assets=(ASSET, "other")),
            _select(api, ["WEST", "EAST"], dataset=DISPLAY_DATASET),
        }
        assert len(ids) == 4
        assert _select(api, ["WEST", "EAST"], assets=("other", ASSET)) in ids  # the order of the assets is no content

    def test_another_set_of_scenes_is_another_id(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        assert _select(api, ["WEST", "EAST"]) != _select(api, ["WEST", "FAR"])

    def test_2000_scenes_are_taken_in_batches_of_a_hundred_and_no_item_is_fetched_alone(
        self, scenes: Scenes, client
    ) -> None:
        names = [f"S{n:04d}" for n in range(mosaic_tiles.MAX_SELECTION_ITEMS)]
        scenes.add(names[0], ZONE_32, SEAM_X - 5000.0, 10_000.0, 10)
        for name in names[1:]:
            scenes.alias(name, names[0])
        api = client()
        chosen = _select(api, names)
        assert len(scenes.batches) == 20 and all(len(batch) == 100 for batch in scenes.batches)
        assert sorted(sum(scenes.batches, [])) == names
        assert scenes.fetched == []
        # a tile reads its 32 and fetches those and no more
        response = api.get(_tile_path(chosen))
        assert response.status_code == 200, response.text
        assert len(scenes.fetched) == mosaic_tiles.TILE_FILE_BUDGET
        assert response.headers[mosaic_tiles.PARTIAL_HEADER] == str(len(names) - mosaic_tiles.TILE_FILE_BUDGET)

    def test_a_selection_over_the_limit_is_refused_before_the_source_is_asked(self, scenes: Scenes, client) -> None:
        names = [f"S{n:04d}" for n in range(mosaic_tiles.MAX_SELECTION_ITEMS + 1)]
        response = client().post(BASE, json={"items": names, "assets": [ASSET]})
        assert response.status_code == 400 and "2000" in response.json()["detail"]
        assert response.text.count("S0001") == 0  # a refusal does not echo the list
        assert scenes.batches == [] and scenes.fetched == []

    def test_an_id_that_is_not_stored_is_a_410_that_says_how_to_create_it_again(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        for path in (_tile_path("0" * 32), _tilejson_path("0" * 32)):
            response = api.get(path)
            assert response.status_code == 410, path
            assert f"POST /collections/{DATASET}/mosaic" in response.json()["detail"]
        assert scenes.fetched == []

    @pytest.mark.parametrize(
        "malformed",
        ["0" * 31, "0" * 33, "A" * 32, "g" * 32, "0" * 16 + "-" + "0" * 15],
        ids=["short", "long", "upper case", "not hex", "dash"],
    )
    def test_an_id_that_does_not_look_like_one_is_a_400_and_nothing_is_looked_up(
        self, scenes: Scenes, client, malformed: str
    ) -> None:
        _seam(scenes)
        api = client()
        api.app.state.earthx_mosaic_selections = None  # looking it up would be a 503
        for path in (_tile_path(malformed), _tilejson_path(malformed)):
            assert api.get(path).status_code == 400, path

    def test_a_selection_of_one_dataset_asked_under_another_is_a_404(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        chosen = _select(api, ["WEST", "EAST"])
        response = api.get(_tile_path(chosen, dataset=DISPLAY_DATASET))
        assert response.status_code == 404
        assert api.get(_tilejson_path(chosen, dataset=DISPLAY_DATASET)).status_code == 404
        assert scenes.fetched == []

    def test_an_expired_selection_is_a_410_and_creating_it_again_gives_the_same_id_and_the_same_picture(
        self, scenes: Scenes, client
    ) -> None:
        _seam(scenes)
        api = client()
        chosen = _select(api, ["WEST", "EAST"])
        before = api.get(_tile_path(chosen)).content
        scenes.selections.expire(chosen)
        assert api.get(_tile_path(chosen)).status_code == 410
        assert api.get(_tilejson_path(chosen)).status_code == 410
        recreated = api.post(BASE, json={"items": ["EAST", "WEST"], "assets": [ASSET]})
        assert recreated.status_code == 201 and recreated.json()["id"] == chosen
        assert api.get(_tile_path(chosen)).content == before

    def test_a_tile_fetches_only_the_items_it_reads(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        chosen = _select(api, ["WEST", "EAST", "FAR"])
        assert scenes.fetched == []
        _array(api.get(_tile_path(chosen)))
        assert sorted(scenes.fetched) == ["EAST", "WEST"]

    @pytest.mark.parametrize(
        "body",
        [
            {"items": ["WEST", "EAST"], "assets": [ASSET], "aoi": []},
            {"items": "WEST", "assets": [ASSET]},
            {"items": [1, 2], "assets": [ASSET]},
            {"assets": [ASSET]},
            {"items": ["WEST", "EAST"]},
            ["WEST", "EAST"],
        ],
        ids=["other field", "items a string", "items numbers", "no items", "no assets", "a list"],
    )
    def test_a_body_of_another_shape_is_a_422_that_names_the_field_and_echoes_no_value(
        self, scenes: Scenes, client, body: Any
    ) -> None:
        _seam(scenes)
        response = client().post(BASE, json=body)
        assert response.status_code == 422, response.text
        assert "WEST" not in response.text and "EAST" not in response.text
        assert scenes.batches == []

    def test_a_body_that_is_no_json_is_a_422(self, scenes: Scenes, client) -> None:
        response = client().post(BASE, content=b"{not json", headers={"content-type": "application/json"})
        assert response.status_code == 422 and scenes.batches == []

    def test_a_body_over_128_kb_is_a_413_from_its_length_before_it_is_read(self, scenes: Scenes, client) -> None:
        limit = mosaic_tiles.MAX_SELECTION_BODY_BYTES
        response = client().post(BASE, content=b" " * (limit + 1), headers={"content-type": "application/json"})
        assert response.status_code == 413 and str(limit) in response.json()["detail"]
        assert scenes.batches == []

    def test_a_body_over_128_kb_without_a_length_is_a_413_too(self, scenes: Scenes, client) -> None:
        limit = mosaic_tiles.MAX_SELECTION_BODY_BYTES

        def chunks() -> Iterator[bytes]:
            for _ in range(limit // 1024 + 2):
                yield b" " * 1024

        response = client().post(BASE, content=chunks(), headers={"content-type": "application/json"})
        assert response.status_code == 413
        assert scenes.batches == []

    def test_a_body_of_2000_ids_of_60_characters_is_under_the_limit(self) -> None:
        ids = [f"S2C_{n:04d}_".ljust(60, "x") for n in range(mosaic_tiles.MAX_SELECTION_ITEMS)]
        assert len(json.dumps({"items": ids, "assets": [ASSET]}).encode()) < mosaic_tiles.MAX_SELECTION_BODY_BYTES

    def test_the_items_of_the_selection_are_those_the_source_returned_not_those_it_added(self, scenes: Scenes, client) -> None:
        """A source that answers a search by id with more than was asked for does not put more into the selection."""
        _seam(scenes)
        api = client()

        async def generous(dataset_id: str, item_ids: Any) -> list[dict[str, Any]]:
            return [json.loads(json.dumps(item)) for item in scenes.items.values()]

        api.app.state.earthx_item_batches = generous
        chosen = _select(api, ["WEST", "EAST"])
        assert scenes.selections.rows[chosen][1]["items"] == ["EAST", "WEST"]
        assert sorted(scenes.selections.rows[chosen][1]["outlines"]) == ["EAST", "WEST"]


class TestTheOrderWithoutAMosaic:
    """``POST /collections/{dataset}/scene-order`` (NM4-24): the order of a pass the map draws scene by scene."""

    ROUTE = f"/collections/{DATASET}/scene-order"

    def _zones(self, scenes: Scenes) -> None:
        """"A" lies in zone 33, "B" and "C" in zone 32: zone 32 is the target, so A comes last although it sorts first."""
        x33, y33 = Transformer.from_crs(ZONE_32, ZONE_33, always_xy=True).transform(SEAM_X, SEAM_Y)
        scenes.add("A", ZONE_33, x33 - 5000.0, 10_000.0, 1, top=y33 + 5000.0)
        scenes.add("B", ZONE_32, SEAM_X - 5000.0, 5000.0, 2)
        scenes.add("C", ZONE_32, SEAM_X, 5000.0, 3)

    @pytest.mark.parametrize("ids", [["A", "B", "C"], ["C", "B", "A"], ["B", "A", "C"]])
    def test_it_is_the_order_of_the_mosaic_job_whatever_the_order_asked(self, scenes: Scenes, client, ids: list[str]) -> None:
        self._zones(scenes)
        answer = client().post(self.ROUTE, json={"items": ids, "asset": ASSET})
        assert answer.status_code == 200, answer.text
        assert answer.json() == {"order": ["B", "C", "A"]}
        assert answer.json()["order"] == mosaic_order({"A": ZONE_33, "B": ZONE_32, "C": ZONE_32})

    def test_it_is_the_order_the_mosaic_tile_names_in_its_tilejson(self, scenes: Scenes, client) -> None:
        self._zones(scenes)
        api = client()
        tilejson = api.get(_tilejson_path(_select(api, ["A", "B", "C"]))).json()
        answer = api.post(self.ROUTE, json={"items": ["C", "A", "B"], "asset": ASSET}).json()
        assert answer["order"] == tilejson["earthx:order"]

    def test_it_reads_no_pixel(self, scenes: Scenes, client) -> None:
        self._zones(scenes)
        client().post(self.ROUTE, json={"items": ["A", "B", "C"], "asset": ASSET})
        assert scenes.opened == []

    def test_more_than_64_scenes_are_ordered(self, scenes: Scenes, client) -> None:
        names = [f"S{n:03d}" for n in range(70)]
        scenes.add(names[0], ZONE_32, SEAM_X - 5000.0, 4000.0, 10)
        for name in names[1:]:
            scenes.alias(name, names[0])
        answer = client().post(self.ROUTE, json={"items": names[::-1], "asset": ASSET})
        assert answer.status_code == 200, answer.text
        assert answer.json()["order"] == names

    @pytest.mark.parametrize(
        "body",
        [
            {"items": ["A"], "asset": ASSET},
            {"items": ["A", "A"], "asset": ASSET},
            {"items": [f"S{n}" for n in range(501)], "asset": ASSET},
            {"items": ["A", "B/../C"], "asset": ASSET},
            {"items": ["A", "B"], "asset": ""},
            {"items": ["A", "B"]},
            {"items": ["A", "B"], "asset": ASSET, "aoi": {}},
            {"asset": ASSET},
        ],
    )
    def test_a_malformed_body_is_refused_before_anything_is_fetched(self, scenes: Scenes, client, body: dict) -> None:
        self._zones(scenes)
        answer = client().post(self.ROUTE, json=body)
        assert answer.status_code in (400, 422), answer.text
        assert scenes.fetched == []

    def test_a_dataset_below_the_display_tier_and_an_unknown_one_are_refused(self, scenes: Scenes, client) -> None:
        self._zones(scenes)
        api = client()
        body = {"items": ["A", "B"], "asset": ASSET}
        assert api.post(f"/collections/{CATALOG_ONLY}/scene-order", json=body).status_code == 403
        assert api.post("/collections/no-such-dataset/scene-order", json=body).status_code == 404
        assert scenes.fetched == []

    def test_a_scene_the_source_does_not_know_and_an_asset_a_scene_lacks_are_refused(self, scenes: Scenes, client) -> None:
        self._zones(scenes)
        api = client()
        assert api.post(self.ROUTE, json={"items": ["A", "GONE"], "asset": ASSET}).status_code == 404
        assert api.post(self.ROUTE, json={"items": ["A", "B"], "asset": "nothing"}).status_code in (400, 404)

    def test_without_the_item_cache_it_says_so(self, scenes: Scenes, client) -> None:
        self._zones(scenes)
        answer = client(pool=None).post(self.ROUTE, json={"items": ["A", "B"], "asset": ASSET})
        assert answer.status_code == 503
        assert scenes.fetched == []

    def test_get_is_not_the_way_to_ask(self, scenes: Scenes, client) -> None:
        assert client().get(self.ROUTE).status_code in (404, 405, 422)


class TestAColourPictureTakesARangeForEachChannel:
    """UI-03d: the mosaic of the view's true-colour asset, ``rescale`` once per channel in the order of its bands."""

    def test_each_channel_is_stretched_by_its_own_range(self, scenes: Scenes, client) -> None:
        scenes.add("A", ZONE_32, SEAM_X - 4000.0, 5000.0, 100, bands=3)
        scenes.add("B", ZONE_32, SEAM_X - 1000.0, 5000.0, 100, bands=3)
        params = [("rescale", "0,200"), ("rescale", "100,300"), ("rescale", "0,100")]
        api = client()
        response = api.get(_tile_path(_select(api, ["A", "B"]), extension="png"), params=params)
        assert response.status_code == 200, response.text
        with MemoryFile(response.content) as memory, memory.open() as picture:
            red, green, blue, alpha = picture.read()
        inside = alpha > 0
        assert inside.any()
        assert set(numpy.unique(red[inside])) <= {127, 128}
        assert set(numpy.unique(green[inside])) == {0}
        assert set(numpy.unique(blue[inside])) == {255}

    def test_one_range_still_stretches_all_three_alike(self, scenes: Scenes, client) -> None:
        scenes.add("A", ZONE_32, SEAM_X - 4000.0, 5000.0, 100, bands=3)
        scenes.add("B", ZONE_32, SEAM_X - 1000.0, 5000.0, 100, bands=3)
        api = client()
        response = api.get(_tile_path(_select(api, ["A", "B"]), extension="png"), params=[("rescale", "0,200")])
        with MemoryFile(response.content) as memory, memory.open() as picture:
            red, green, blue, alpha = picture.read()
        inside = alpha > 0
        assert numpy.array_equal(red[inside], green[inside]) and numpy.array_equal(red[inside], blue[inside])
