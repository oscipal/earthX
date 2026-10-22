"""The mosaic tile of the tiler: the scenes of one overpass as one surface (M4-17b, plan M4-17 §4, §5).

The real app (`api.tiler.build_app`) over synthetic scenes of zone 32 and 33, served through the real
`readers`: ``sources.serve`` swaps only the last step of the COG path for a local file per address, so
the registry, the licence tier, ``check_url`` and the allowlist all run for real. Each scene is a flat
``uint8`` COG with a value of its own, so that the winner of a pixel can be read off it. The item source
is a double that records what it was asked.

The part that needs a clock and a gateway — the item fetches — is in `test_mosaic_item_fetches.py`.
"""

from __future__ import annotations

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
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles
from shapely.geometry import box, mapping

from earthx.access import mosaic_tiles as mosaic_reading
from earthx.access.crop_rules import mosaic_order
from earthx.adapters.errors import UnknownCollection
from earthx.api import mosaic_tiles
from earthx.api.tiler import MOSAIC_ROUTER_PREFIX, build_app
from earthx.catalog.datasets import COP_DEM_GLO_30, SENTINEL_2_L2A
from earthx.catalog.registry import DatasetRegistry, LicenseTier
from earthx.gateway import UpstreamError, check_url
from tests.conftest import own_log_text
from tests.earthx.access.test_mosaic_tiles import SEAM_X, SEAM_Y, TILE, TMS, TOP
from tests.earthx.access.test_mosaic_tiles import _at as value_at
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
        replace(SYNTHETIC, dataset_id=NO_VIEWER, viewer=None),
        replace(
            SYNTHETIC,
            dataset_id=CATALOG_ONLY,
            viewer=None,
            license=replace(SYNTHETIC.license, tier=LicenseTier.CATALOG),
        ),
        replace(SYNTHETIC, dataset_id=DISPLAY_DATASET, license=replace(SYNTHETIC.license, tier=LicenseTier.DISPLAY)),
        COP_DEM_GLO_30,
    )
)

ROWS = 1000


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
        self.fetched: list[str] = []
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
        app.state.earthx_cache_pool = pool
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


def _tile_path(z: int = TILE.z, x: int = TILE.x, y: int = TILE.y, *, extension: str = "npy") -> str:
    return f"{BASE}/tiles/WebMercatorQuad/{z}/{x}/{y}.{extension}"


def _query(items: list[str], **extra: str) -> list[tuple[str, str]]:
    return [("item", item_id) for item_id in items] + [("asset", ASSET)] + list(extra.items())


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
        tile = _array(client().get(_tile_path(), params=_query(["WEST", "EAST"])))
        assert value_at(tile, SEAM_X - 500.0) == 100
        assert value_at(tile, SEAM_X + 500.0) == 200
        assert all(value_at(tile, x) is not None for x in numpy.arange(SEAM_X - 1500.0, SEAM_X + 1500.0, 30.0))

    def test_the_order_of_the_ids_in_the_url_does_not_change_the_bytes(self, scenes: Scenes, client) -> None:
        scenes.add("A", ZONE_32, SEAM_X - 4000.0, 5000.0, 100)
        scenes.add("B", ZONE_32, SEAM_X - 1000.0, 5000.0, 200)
        api = client()
        forward = api.get(_tile_path(), params=_query(["A", "B"]))
        backward = api.get(_tile_path(), params=_query(["B", "A"]))
        assert forward.content == backward.content
        # where both have data the scene that sorts first wins, whatever the URL says
        assert value_at(_array(forward), SEAM_X - 500.0) == 100

    def test_a_scene_away_from_the_tile_is_not_opened(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        _array(client().get(_tile_path(), params=_query(["WEST", "EAST", "FAR"])))
        assert sorted(scenes.opened) == ["EAST", "WEST"]
        assert not [address for address in scenes.cleared if "FAR" in address]  # its address was never even cleared

    def test_a_tile_that_is_full_after_the_first_portion_does_not_open_the_next(self, scenes: Scenes, client) -> None:
        names = [f"S{n}" for n in range(1, 7)]
        scenes.add("S1", ZONE_32, SEAM_X - 5000.0, 10_000.0, 10)
        for name in names[1:]:
            scenes.alias(name, "S1")
        _array(client().get(_tile_path(), params=_query(names)))
        assert sorted(scenes.opened) == ["S1", "S2", "S3", "S4"]

    def test_two_fresh_apps_answer_the_same_url_with_the_same_bytes(
        self, scenes: Scenes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _seam(scenes)
        _serve(scenes, monkeypatch)
        answers = []
        for _ in range(2):
            with TestClient(_app(scenes)) as api:
                answers.append(api.get(_tile_path(), params=_query(["WEST", "EAST"])).content)
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
        tile = _array(client().get(_tile_path(), params=_query(["A", "B", "C"])))
        assert value_at(tile, SEAM_X - 1000.0) == 2
        assert value_at(tile, SEAM_X + 1000.0) == 3
        assert 1 not in numpy.unique(tile[0][tile[-1] != 0])


class TestTheTargetZoneComesFromTheWholeList:
    def test_a_tile_that_touches_only_some_scenes_still_uses_the_target_zone_of_all(self, scenes: Scenes, client) -> None:
        """Two zone-32 scenes far away make zone 32 the target; X (32) and Y, Z (33) lie at the tile.

        Over the whole list zone 32 is the target and X wins where it has data. Computed from the scenes of
        the tile alone, zone 33 would be the target and Y would win there (plan §4.4)."""
        x33, y33 = Transformer.from_crs(ZONE_32, ZONE_33, always_xy=True).transform(SEAM_X, SEAM_Y)
        scenes.add("F1", ZONE_32, SEAM_X + 60_000.0, 4000.0, 9)
        scenes.add("F2", ZONE_32, SEAM_X + 70_000.0, 4000.0, 9)
        scenes.add("X", ZONE_32, SEAM_X - 5000.0, 5000.0, 1)
        scenes.add("Y", ZONE_33, x33 - 5000.0, 10_000.0, 2, top=y33 + 5000.0)
        scenes.add("Z", ZONE_33, x33 - 5000.0, 10_000.0, 3, top=y33 + 5000.0)
        tile = _array(client().get(_tile_path(), params=_query(["F1", "F2", "X", "Y", "Z"])))
        assert value_at(tile, SEAM_X - 1000.0) == 1
        assert value_at(tile, SEAM_X + 1000.0) == 2


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
            tile = _array(api.get(_tile_path(cell.z, cell.x, cell.y), params=_query(asked)))
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
        response = client().get(f"{BASE}/WebMercatorQuad/tilejson.json", params=_query(["EAST", "FAR", "WEST"]))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["earthx:order"] == ["EAST", "FAR", "WEST"]
        assert (body["minzoom"], body["maxzoom"]) == (8, 19)
        west, south, east, north = body["bounds"]
        assert west < scenes.items["WEST"]["bbox"][0] + 1e-9 and east > scenes.items["FAR"]["bbox"][2] - 1e-9
        assert south < north
        (template,) = body["tiles"]
        assert template.startswith("http://testserver" + BASE + "/tiles/WebMercatorQuad/{z}/{x}/{y}")
        assert template.count("item=") == 3 and f"asset={ASSET}" in template

    def test_the_order_is_the_jobs_not_the_urls(self, scenes: Scenes, client) -> None:
        scenes.add("A", ZONE_33, 500_000.0, 4000.0, 1, top=5_700_000.0)
        scenes.add("B", ZONE_32, SEAM_X, 4000.0, 2)
        scenes.add("C", ZONE_32, SEAM_X + 3000.0, 4000.0, 3)
        body = client().get(f"{BASE}/WebMercatorQuad/tilejson.json", params=_query(["A", "B", "C"])).json()
        assert body["earthx:order"] == ["B", "C", "A"]  # zone 32 has two scenes, so it is the target

    def test_a_zoom_asked_for_must_stay_in_the_range_the_mosaic_serves(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        narrowed = api.get(f"{BASE}/WebMercatorQuad/tilejson.json", params=_query(["WEST", "EAST"], minzoom="10"))
        assert narrowed.status_code == 200 and narrowed.json()["minzoom"] == 10
        below = api.get(f"{BASE}/WebMercatorQuad/tilejson.json", params=_query(["WEST", "EAST"], minzoom="5"))
        assert below.status_code == 400  # a mosaic starts at z8, though the registry releases the dataset from z0


class TestAnswersToWrongRequests:
    @pytest.mark.parametrize(
        ("items", "why"),
        [
            (["WEST"], "one item"),
            ([f"S{n}" for n in range(65)], "65 items"),
            (["WEST", "WEST"], "twice the same item"),
        ],
    )
    def test_the_number_of_items_is_two_to_64_each_once_and_nothing_is_fetched(
        self, scenes: Scenes, client, items: list[str], why: str
    ) -> None:
        _seam(scenes)
        response = client().get(_tile_path(), params=_query(items))
        assert response.status_code == 400, why
        assert scenes.fetched == []

    def test_a_missing_item_is_a_404(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        response = client().get(_tile_path(), params=_query(["WEST", "NOWHERE"]))
        assert response.status_code == 404
        assert "NOWHERE" in response.json()["detail"]

    def test_a_missing_asset_on_one_scene_is_a_404(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        del scenes.items["EAST"]["assets"][ASSET]
        scenes.items["EAST"]["assets"]["other"] = {"href": sources.url("EAST-other")}
        response = client().get(_tile_path(), params=_query(["WEST", "EAST"]))
        assert response.status_code == 404
        assert scenes.opened == []

    def test_scenes_of_two_overpasses_are_a_422_that_names_the_ones_apart(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        scenes.items["EAST"]["properties"]["s2:datatake_id"] = "D2"
        response = client().get(_tile_path(), params=_query(["WEST", "EAST"]))
        assert response.status_code == 422
        assert "EAST" in response.json()["detail"] and "one overpass" in response.json()["detail"]
        assert scenes.opened == []

    def test_an_item_that_lacks_the_overpass_is_the_sources_502(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        del scenes.items["EAST"]["properties"]["s2:datatake_id"]
        assert client().get(_tile_path(), params=_query(["WEST", "EAST"])).status_code == 502

    def test_more_scenes_than_a_tile_reads_is_a_422_zoom_in(self, scenes: Scenes, client) -> None:
        scenes.add("S00", ZONE_32, SEAM_X - 5000.0, 10_000.0, 10)
        names = ["S00"] + [f"S{n:02d}" for n in range(1, mosaic_tiles.MAX_SCENES_PER_TILE + 1)]
        for name in names[1:]:
            scenes.alias(name, "S00")
        response = client().get(_tile_path(), params=_query(names))
        assert response.status_code == 422 and "zoom in" in response.json()["detail"]
        assert scenes.opened == []
        # the same number of scenes is fine as soon as one is away from the tile
        scenes.alias("S99", "S00", bbox=[0.0, 0.0, 0.1, 0.1], geometry=mapping(box(0.0, 0.0, 0.1, 0.1)))
        ok = client().get(_tile_path(), params=_query(names[:-1] + ["S99"]))
        assert ok.status_code == 200, ok.text

    def test_a_tile_no_scene_touches_is_a_404(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        assert client().get(_tile_path(), params=_query(["FAR", "WEST"])).status_code == 200
        scenes.opened.clear()
        away = TMS.tile(0.0, 0.0, 12)
        response = client().get(_tile_path(away.z, away.x, away.y), params=_query(["WEST", "EAST"]))
        assert response.status_code == 404
        assert scenes.opened == []

    def test_below_z8_it_is_a_400_before_any_item_is_fetched(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        response = client().get(_tile_path(7, 64, 41), params=_query(["WEST", "EAST"]))
        assert response.status_code == 400 and "z8" in response.json()["detail"]
        assert scenes.fetched == []

    def test_a_level_the_dataset_is_not_released_for_is_a_400_before_any_item_is_fetched(
        self, scenes: Scenes, client
    ) -> None:
        _seam(scenes)
        response = client().get(_tile_path(20, 1, 1), params=_query(["WEST", "EAST"]))
        assert response.status_code == 400
        assert scenes.fetched == []

    def test_a_tile_outside_the_matrix_is_a_404_before_any_item_is_fetched(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        response = client().get(_tile_path(9, 5000, 1), params=_query(["WEST", "EAST"]))
        assert response.status_code == 404
        assert scenes.fetched == []

    def test_a_dataset_without_a_released_range_is_a_501(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        path = f"/collections/{NO_VIEWER}/mosaic"
        assert api.get(f"{path}/tiles/WebMercatorQuad/10/1/1.png", params=_query(["WEST", "EAST"])).status_code == 501
        assert api.get(f"{path}/WebMercatorQuad/tilejson.json", params=_query(["WEST", "EAST"])).status_code == 501
        assert scenes.fetched == []

    def test_a_dataset_released_only_below_z8_has_no_mosaic(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        api.app.state.earthx_registry = DatasetRegistry(
            (replace(SYNTHETIC, viewer=replace(SYNTHETIC.viewer, min_zoom=2, max_zoom=7)),)
        )
        for path in (_tile_path(), f"{BASE}/WebMercatorQuad/tilejson.json"):
            assert api.get(path, params=_query(["WEST", "EAST"])).status_code == 400, path
        assert scenes.fetched == []

    def test_a_dataset_released_from_a_higher_level_starts_its_mosaic_there(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        api.app.state.earthx_registry = DatasetRegistry(
            (replace(SYNTHETIC, viewer=replace(SYNTHETIC.viewer, min_zoom=10, max_zoom=14)),)
        )
        body = api.get(f"{BASE}/WebMercatorQuad/tilejson.json", params=_query(["WEST", "EAST"])).json()
        assert (body["minzoom"], body["maxzoom"]) == (10, 14)

    def test_a_dataset_below_licence_tier_display_is_a_403(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        response = client().get(
            f"/collections/{CATALOG_ONLY}/mosaic/tiles/WebMercatorQuad/10/1/1.png", params=_query(["WEST", "EAST"])
        )
        assert response.status_code == 403
        assert scenes.fetched == []

    def test_a_display_tier_dataset_gets_its_mosaic(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        response = client().get(
            f"/collections/{DISPLAY_DATASET}/mosaic/tiles/WebMercatorQuad/{TILE.z}/{TILE.x}/{TILE.y}.npy",
            params=_query(["WEST", "EAST"]),
        )
        assert response.status_code == 200, response.text

    def test_an_unknown_dataset_is_a_404(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        response = client().get(
            "/collections/no-such-dataset/mosaic/tiles/WebMercatorQuad/10/1/1.png", params=_query(["WEST", "EAST"])
        )
        assert response.status_code == 404

    def test_an_address_the_dataset_does_not_declare_is_a_502_and_nothing_is_read(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        scenes.items["EAST"]["assets"][ASSET]["href"] = "https://elsewhere.example.invalid/east.tif"
        response = client().get(_tile_path(), params=_query(["WEST", "EAST"]))
        assert response.status_code == 502
        assert "asset_hosts" in response.json()["detail"]
        assert scenes.opened == []

    def test_scenes_with_another_number_of_bands_are_a_422_and_not_a_crash(self, scenes: Scenes, client) -> None:
        scenes.add("ONE", ZONE_32, SEAM_X - 4000.0, 4000.0, 100)
        scenes.add("TWO", ZONE_32, SEAM_X, 4000.0, 200, bands=2)
        response = client().get(_tile_path(), params=_query(["ONE", "TWO"]))
        assert response.status_code == 422, response.text
        assert "number of bands" in response.json()["detail"]


class TestNothingIsFetchedForARequestThatIsRefused:
    """Otto, 22.10.2026: the format, z/x/y, the tile matrix set and every other parameter come first."""

    @pytest.mark.parametrize(
        ("path", "extra"),
        [
            (f"{BASE}/tiles/WebMercatorQuad/{TILE.z}/{TILE.x}/{TILE.y}.xyz", {}),
            (f"{BASE}/tiles/NoSuchGrid/{TILE.z}/{TILE.x}/{TILE.y}.png", {}),
            (f"{BASE}/tiles/WorldCRS84Quad/{TILE.z}/{TILE.x}/{TILE.y}.png", {}),
            (f"{BASE}/tiles/WebMercatorQuad/{TILE.z}/x/{TILE.y}.png", {}),
            (f"{BASE}/tiles/WebMercatorQuad/abc/{TILE.x}/{TILE.y}.png", {}),
            (f"{BASE}/tiles/WebMercatorQuad/{TILE.z}/{TILE.x}/{TILE.y}.png", {"tilesize": "0"}),
            (f"{BASE}/tiles/WebMercatorQuad/{TILE.z}/{TILE.x}/{TILE.y}.png", {"tilesize": "big"}),
            (f"{BASE}/tiles/WebMercatorQuad/{TILE.z}/{TILE.x}/{TILE.y}.png", {"bidx": "first"}),
            (f"{BASE}/tiles/WebMercatorQuad/{TILE.z}/{TILE.x}/{TILE.y}.png", {"resampling": "magic"}),
            (f"{BASE}/tiles/WebMercatorQuad/{TILE.z}/{TILE.x}/{TILE.y}.png", {"padding": "wide"}),
            (f"{BASE}/NoSuchGrid/tilejson.json", {}),
            (f"{BASE}/WebMercatorQuad/tilejson.json", {"minzoom": "low"}),
            (f"{BASE}/WebMercatorQuad/tilejson.json", {"tilesize": "0"}),
            (f"{BASE}/WebMercatorQuad/tilejson.json", {"tile_format": "gif"}),
        ],
    )
    def test_an_invalid_request_is_a_400_or_422_and_asks_the_source_for_nothing(
        self, scenes: Scenes, client, path: str, extra: dict[str, str]
    ) -> None:
        _seam(scenes)
        response = client().get(path, params=_query(["WEST", "EAST"], **extra))
        assert response.status_code in (400, 422), (path, extra, response.status_code)
        assert scenes.fetched == []

    def test_the_same_requests_without_the_fault_do_fetch(self, scenes: Scenes, client) -> None:
        """The counter counts: a valid request does ask the source for its items."""
        _seam(scenes)
        assert client().get(_tile_path(), params=_query(["WEST", "EAST"], tilesize="256")).status_code == 200
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
        for path in (_tile_path(), f"{BASE}/WebMercatorQuad/tilejson.json"):
            assert client().get(path, params=_query(["WEST", "EAST"])).status_code == 502, path

    @pytest.mark.parametrize("heights", [False, True])
    def test_without_a_geometry_the_bbox_is_the_outline_with_four_or_six_numbers(
        self, scenes: Scenes, client, heights: bool
    ) -> None:
        _seam(scenes)
        for name in ("WEST", "EAST"):
            west, south, east, north = scenes.items[name]["bbox"]
            scenes.items[name]["geometry"] = None
            scenes.items[name]["bbox"] = [west, south, 0, east, north, 100] if heights else [west, south, east, north]
        assert _array(client().get(_tile_path(), params=_query(["WEST", "EAST"])))[0].any()

    def test_a_bbox_of_five_numbers_is_the_sources_502(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        scenes.items["EAST"]["geometry"] = None
        scenes.items["EAST"]["bbox"] = [0, 0, 1, 1, 2]
        assert client().get(_tile_path(), params=_query(["WEST", "EAST"])).status_code == 502

    def test_a_band_chosen_with_bidx_makes_scenes_of_other_band_counts_a_mosaic(self, scenes: Scenes, client) -> None:
        scenes.add("ONE", ZONE_32, SEAM_X - 4000.0, 4000.0, 100)
        scenes.add("TWO", ZONE_32, SEAM_X, 4000.0, 200, bands=2)
        response = client().get(_tile_path(), params=_query(["ONE", "TWO"], bidx="1"))
        assert response.status_code == 200, response.text


class TestWhatTheUrlMayCarry:
    """Plan §4.1, §4.8 test 7: ids and one asset, and nothing that could name an area, an operator or an address."""

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
        ],
    )
    def test_a_parameter_that_could_carry_an_area_an_operator_or_an_address_is_a_400(
        self, scenes: Scenes, client, extra: dict[str, str]
    ) -> None:
        _seam(scenes)
        api = client()
        for path in (_tile_path(), f"{BASE}/WebMercatorQuad/tilejson.json"):
            assert api.get(path, params=_query(["WEST", "EAST"], **extra)).status_code == 400, path
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
        response = client().get(
            f"/collections/{dataset}/mosaic/tiles/WebMercatorQuad/10/1/1.png", params=_query(["WEST", item_id])
        )
        assert response.status_code == 400
        assert item_id.strip() == "" or item_id not in response.text
        assert scenes.fetched == []

    def test_two_assets_or_none_are_a_400(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        api = client()
        both = api.get(_tile_path(), params=[("item", "WEST"), ("item", "EAST"), ("asset", "a"), ("asset", "b")])
        none = api.get(_tile_path(), params=[("item", "WEST"), ("item", "EAST")])
        assert both.status_code == none.status_code == 400

    def test_an_item_of_another_dataset_is_the_sources_404(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        response = client().get(
            f"/collections/{DEM}/mosaic/tiles/WebMercatorQuad/10/1/1.png", params=_query(["WEST", "EAST"])
        )
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
        assert {"item", "asset"} <= names
        assert not names & {"url", "aoi", "bbox", "geometry", "intersects", "expression", "algorithm", "op", "params"}

    def test_only_the_tile_and_the_tilejson_exist(self, scenes: Scenes, client) -> None:
        paths = [path for path in client().app.openapi()["paths"] if path.startswith(MOSAIC_ROUTER_PREFIX)]
        assert sorted(paths) == [
            f"{MOSAIC_ROUTER_PREFIX}/tiles/{{tileMatrixSetId}}/{{z}}/{{x}}/{{y}}",
            f"{MOSAIC_ROUTER_PREFIX}/tiles/{{tileMatrixSetId}}/{{z}}/{{x}}/{{y}}.{{format}}",
            f"{MOSAIC_ROUTER_PREFIX}/{{tileMatrixSetId}}/tilejson.json",
        ]


class TestWithoutTheItemCache:
    """Plan §11 Auflage 3: a clear answer with its reason, never a ``500``."""

    def test_without_a_pool_a_mosaic_is_a_503_that_says_why_and_the_tile_of_one_item_goes_on(
        self, scenes: Scenes, client
    ) -> None:
        _seam(scenes)
        api = client(pool=None)
        for path in (_tile_path(), f"{BASE}/WebMercatorQuad/tilejson.json"):
            response = api.get(path, params=_query(["WEST", "EAST"]))
            assert response.status_code == 503, path
            assert "item cache" in response.json()["detail"]
        assert scenes.fetched == []
        single = api.get(
            f"/collections/{DATASET}/items/WEST/tiles/WebMercatorQuad/{TILE.z}/{TILE.x}/{TILE.y}.npy",
            params={"asset": ASSET},
        )
        assert single.status_code == 200, single.text

    def test_a_materialized_dataset_without_a_pool_is_a_503_too(self, scenes: Scenes, client) -> None:
        response = client(pool=None).get(
            f"/collections/{DEM}/mosaic/tiles/WebMercatorQuad/10/1/1.png", params=_query(["A", "B"])
        )
        assert response.status_code == 503 and "item cache" in response.json()["detail"]

    def test_a_wrong_request_is_still_a_400_without_a_pool(self, scenes: Scenes, client) -> None:
        _seam(scenes)
        assert client(pool=None).get(_tile_path(), params=_query(["WEST"])).status_code == 400

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
        api.app.state.earthx_item_source = failing
        root = logging.getLogger()
        root.addHandler(caplog.handler)
        try:
            if isinstance(failure, psycopg.Error):
                response = api.get(_tile_path(), params=_query(["WEST", "EAST"]))
                assert response.status_code == 503 and "item cache" in response.json()["detail"]
                text = " ".join(own_log_text(record) + str(record.exc_info) for record in caplog.records)
                assert type(failure).__name__ in text  # a line was logged
                assert "internal.example" not in text and "secret" not in text and "earthx_search_cache" not in text
            else:
                with pytest.raises(TimeoutError):
                    api.get(_tile_path(), params=_query(["WEST", "EAST"]))
        finally:
            root.removeHandler(caplog.handler)


class TestTheLog:
    def test_it_says_how_many_scenes_a_tile_read_and_names_no_coordinate(
        self, scenes: Scenes, client, caplog: pytest.LogCaptureFixture
    ) -> None:
        _seam(scenes)
        api = client()  # building the app replaces the root handlers, so the capture comes after it
        root = logging.getLogger()
        root.addHandler(caplog.handler)
        try:
            assert api.get(_tile_path(), params=_query(["WEST", "EAST", "FAR"])).status_code == 200
        finally:
            root.removeHandler(caplog.handler)
        lines = [own_log_text(record) for record in caplog.records]
        assert any("mosaic tile reads 2 of 3 scenes" in line for line in lines), lines  # lines were logged at all
        coordinates = [
            number
            for item in scenes.items.values()
            for number in item["bbox"]
        ] + list(TMS.bounds(TILE))
        text = " ".join(lines)
        for value in coordinates:
            assert f"{value:.3f}" not in text and f"{value:.4f}" not in text
