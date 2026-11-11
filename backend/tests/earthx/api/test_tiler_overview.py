"""The tile of a substitute: below its first level a dataset shows the picture of another (plan M5-30b §4.8, A5).

The real app over synthetic scenes, as `test_tiler_mosaic.py`: the readers, the registry, the licence tier and
`check_url` run for real; the items of the substitute come from a double of the pgstac search that records the
rectangle it was asked for. ``TERRAIN`` is released from z13, so the tile of z12 the scenes lie under is a tile of its
substitute ``SURFACE``.
"""

from __future__ import annotations

import ast
import io
import json
from collections.abc import Callable, Iterator
from contextlib import ExitStack, asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy
import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import earthx
from earthx.api import mosaic_tiles
from earthx.api.tiler import OVERVIEW_ROUTER_PREFIX, build_app
from earthx.catalog.registry import (
    DatasetRegistry,
    ItemHolding,
    LicenseTier,
    OverviewMode,
    SearchCapabilities,
)
from tests.catalog.entries import SENTINEL_2_L2A
from tests.earthx.access.test_mosaic_tiles import SEAM_X, TILE, TMS
from tests.earthx.access.test_mosaic_tiles import _at as value_at
from tests.earthx.api.test_tiler_mosaic import ASSET, ZONE_32, Scenes, _serve
from tests.earthx.processing import sources
from tests.earthx.readers import mini_zarr

SURFACE_ID, TERRAIN_ID, PLAIN_ID = "synthetic-surface", "synthetic-terrain", "synthetic-plain"
BASE = f"/collections/{TERRAIN_ID}/overview"

# The picture of both is read in metres: the registry compares the unit of the default band of the two datasets.
_PLAIN = replace(
    SENTINEL_2_L2A,
    dataset_id=PLAIN_ID,
    source=replace(SENTINEL_2_L2A.source, asset_hosts=(sources.HOST,)),
    band_units={**SENTINEL_2_L2A.band_units, ASSET: "m"},
)
#: The dataset whose items the tile reads: held in our own pgstac, as GLO-30 is.
SURFACE = replace(
    _PLAIN,
    dataset_id=SURFACE_ID,
    source=replace(_PLAIN.source, item_holding=ItemHolding.MATERIALIZED, source_collection_id=SURFACE_ID),
    coverage=replace(_PLAIN.coverage, provider=_PLAIN.coverage.provider.LOCAL_SQL),
    search_filters=(),
    search_capabilities=SearchCapabilities(evaluate=False, aoi_coverage=False),
)
#: The dataset that shows it below z13 (swissALTI3D's place in the released registry).
TERRAIN = replace(
    _PLAIN,
    dataset_id=TERRAIN_ID,
    viewer=replace(
        _PLAIN.viewer,
        min_zoom=13,
        max_zoom=20,
        overview=OverviewMode.SUBSTITUTE,
        overview_resampling=None,
        overview_substitute=SURFACE_ID,
    ),
)
REGISTRY = DatasetRegistry((TERRAIN, SURFACE, _PLAIN))


class Pool:
    """A stand-in for the pool of the tiler: it hands out a connection, and the search double ignores it."""

    def connection(self) -> Any:
        @asynccontextmanager
        async def connection() -> Any:
            yield object()

        return connection()


WITH_POOL = Pool()


class Catalogue:
    """The pgstac search as a double: the items it holds, and the rectangles it was asked for."""

    def __init__(self, scenes: Scenes) -> None:
        self.scenes = scenes
        self.asked: list[tuple[str, tuple[float, float, float, float], int]] = []
        self.fail: Exception | None = None
        self.holds: set[str] | None = None  # the ids of the items it holds, or all of the scenes

    async def search(
        self, conn: Any, dataset_id: str, bbox: tuple[float, float, float, float], limit: int
    ) -> list[Any]:
        self.asked.append((dataset_id, tuple(bbox), limit))
        if self.fail is not None:
            raise self.fail
        held = [item for item_id, item in self.scenes.items.items() if self.holds is None or item_id in self.holds]
        return [dict(item, collection=dataset_id) for item in held][:limit]


@pytest.fixture
def scenes(tmp_path: Path) -> Scenes:
    return Scenes(tmp_path)


@pytest.fixture
def catalogue(scenes: Scenes, monkeypatch: pytest.MonkeyPatch) -> Catalogue:
    catalogue = Catalogue(scenes)
    monkeypatch.setattr(mosaic_tiles, "search_items_in_bbox_async", catalogue.search)
    return catalogue


@pytest.fixture
def client(
    scenes: Scenes, catalogue: Catalogue, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[..., TestClient]]:
    """The real app over ``registry``, with a pool or without; every client is closed with the test."""
    stack = ExitStack()

    def build(registry: DatasetRegistry = REGISTRY, *, pool: Any = WITH_POOL, item_source: Any = None) -> TestClient:
        _serve(scenes, monkeypatch)

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> Any:
            app.state.earthx_item_source = item_source
            app.state.earthx_cache_pool = pool
            yield

        app = build_app(registry, lifespan=lifespan)
        app.state.earthx_resolver = mini_zarr.from_memory
        return stack.enter_context(TestClient(app))

    with stack:
        yield build


def _path(z: int = TILE.z, x: int = TILE.x, y: int = TILE.y, *, extension: str = "npy", base: str = BASE) -> str:
    return f"{base}/tiles/WebMercatorQuad/{z}/{x}/{y}.{extension}"


def _array(response: Any) -> numpy.ndarray:
    assert response.status_code == 200, response.text
    return numpy.load(io.BytesIO(response.content))


def _seam(scenes: Scenes) -> None:
    """Two scenes either side of the seam in the middle of the tile, and one far away."""
    scenes.add("WEST", ZONE_32, SEAM_X - 4000.0, 4000.0, 100)
    scenes.add("EAST", ZONE_32, SEAM_X, 4000.0, 200)
    scenes.add("FAR", ZONE_32, SEAM_X + 60_000.0, 4000.0, 250)


class TestTheTileOfTheSubstitute:
    def test_the_tile_is_the_picture_of_the_substitutes_scenes_and_says_so(self, scenes, catalogue, client) -> None:
        _seam(scenes)
        response = client().get(_path())
        tile = _array(response)
        assert value_at(tile, SEAM_X - 500.0) == 100
        assert value_at(tile, SEAM_X + 500.0) == 200
        assert response.headers[mosaic_tiles.SOURCE_HEADER] == mosaic_tiles.SUBSTITUTE_SOURCE
        assert mosaic_tiles.PARTIAL_HEADER not in response.headers

    def test_the_items_are_those_of_the_substitute_in_the_rectangle_of_the_tile(
        self, scenes, catalogue, client
    ) -> None:
        _seam(scenes)
        _array(client().get(_path()))
        ((dataset_id, bbox, limit),) = catalogue.asked
        assert dataset_id == SURFACE_ID
        assert bbox == pytest.approx(tuple(TMS.bounds(TILE)))
        assert limit == mosaic_tiles.SUBSTITUTE_ITEM_CAP + 1

    def test_a_scene_away_from_the_tile_is_not_opened(self, scenes, catalogue, client) -> None:
        _seam(scenes)
        _array(client().get(_path()))
        assert sorted(scenes.opened) == ["EAST", "WEST"]
        assert not [address for address in scenes.cleared if "FAR" in address]

    def test_every_address_goes_through_the_gateway_policy(self, scenes, catalogue, client) -> None:
        _seam(scenes)
        scenes.items["WEST"]["assets"][ASSET]["href"] = "https://elsewhere.example.invalid/west.tif"
        response = client().get(_path())
        assert response.status_code == 502
        assert scenes.opened == []

    def test_the_asset_is_the_first_of_the_default_render_an_item_has(self, scenes, catalogue, client) -> None:
        _seam(scenes)
        del scenes.items["EAST"]["assets"][ASSET]
        scenes.items["EAST"]["assets"]["other"] = {"href": sources.url("EAST-other")}
        tile = _array(client().get(_path()))
        assert scenes.opened == ["WEST"]
        assert value_at(tile, SEAM_X - 500.0) == 100

    def test_without_any_scene_that_has_the_asset_there_is_no_tile(self, scenes, catalogue, client) -> None:
        _seam(scenes)
        for item in scenes.items.values():
            item["assets"] = {"other": {"href": sources.url("x")}}
        assert client().get(_path()).status_code == 404

    def test_a_tile_no_scene_touches_is_a_404(self, scenes, catalogue, client) -> None:
        scenes.add("FAR", ZONE_32, SEAM_X + 60_000.0, 4000.0, 250)
        assert client().get(_path()).status_code == 404
        assert scenes.opened == []

    def test_the_same_url_gives_the_same_bytes_whoever_asks(self, scenes, catalogue, client) -> None:
        _seam(scenes)
        first, second = (client().get(_path(extension="png")) for _ in range(2))
        assert first.status_code == 200 and first.content == second.content

    def test_the_display_parameters_of_the_request_are_applied(self, scenes, catalogue, client) -> None:
        _seam(scenes)
        api = client()
        plain = api.get(_path(extension="png"))
        stretched = api.get(_path(extension="png"), params={"rescale": "0,1000"})
        coloured = api.get(_path(extension="png"), params={"rescale": "0,255", "colormap_name": "viridis"})
        assert plain.status_code == stretched.status_code == coloured.status_code == 200
        assert len({plain.content, stretched.content, coloured.content}) == 3
        assert value_at(_array(api.get(_path(), params={"rescale": "0,1000"})), SEAM_X - 500.0) != 100

    def test_the_tile_is_the_size_the_client_asks_for_as_on_every_mosaic_tile(self, scenes, catalogue, client) -> None:
        """The viewer asks for 512 px (`tilesize` in its template); the factory's own 512 is the TileJSON's default."""
        _seam(scenes)
        api = client()
        assert _array(api.get(_path(), params={"tilesize": "512"})).shape[-2:] == (512, 512)
        assert _array(api.get(_path(), params={"tilesize": "256"})).shape[-2:] == (256, 256)


class TestTheBudget:
    def test_more_scenes_than_the_budget_are_read_up_to_it_and_the_rest_is_said_in_a_header(
        self, scenes, catalogue, client
    ) -> None:
        scenes.add("S00", ZONE_32, SEAM_X - 5000.0, 10_000.0, 10)
        for n in range(1, mosaic_tiles.TILE_FILE_BUDGET + 2):
            scenes.alias(f"S{n:02d}", "S00")
        response = client().get(_path())
        assert response.status_code == 200, response.text
        assert response.headers[mosaic_tiles.PARTIAL_HEADER] == "2"
        assert response.headers[mosaic_tiles.SOURCE_HEADER] == mosaic_tiles.SUBSTITUTE_SOURCE
        assert "no-store" not in response.headers.get("cache-control", "")

    def test_a_catalogue_with_more_items_than_the_cap_says_one_more_was_left_out(
        self, scenes, catalogue, client, monkeypatch
    ) -> None:
        _seam(scenes)
        monkeypatch.setattr(mosaic_tiles, "SUBSTITUTE_ITEM_CAP", 2)
        response = client().get(_path())
        assert response.status_code == 200, response.text
        assert response.headers[mosaic_tiles.PARTIAL_HEADER] == "1"
        assert sorted(scenes.opened) == ["EAST", "WEST"]

    def test_a_tile_whose_time_runs_out_is_not_stored_and_does_not_name_a_source(
        self, scenes, catalogue, client, monkeypatch
    ) -> None:
        _seam(scenes)
        monkeypatch.setattr(mosaic_tiles, "TILE_TIME_BUDGET_S", 1e-9)
        response = client().get(_path())
        assert response.status_code == 503, response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.headers[mosaic_tiles.PARTIAL_HEADER] == "time"
        assert mosaic_tiles.SOURCE_HEADER not in response.headers


class TestWhatTheRouteRefuses:
    def test_a_level_from_the_first_level_of_the_dataset_on_is_a_400_before_anything_is_asked(
        self, scenes, catalogue, client
    ) -> None:
        _seam(scenes)
        api = client()
        for z in (13, 14, 20, 30, -1):
            response = api.get(_path(z, 0, 0))
            assert response.status_code == 400, (z, response.text)
        assert "z13" in api.get(_path(13, 0, 0)).json()["detail"]
        assert catalogue.asked == []

    def test_a_tile_outside_the_matrix_is_a_404_before_anything_is_asked(self, scenes, catalogue, client) -> None:
        _seam(scenes)
        assert client().get(_path(9, 5000, 1)).status_code == 404
        assert catalogue.asked == []

    def test_the_lowest_level_has_a_tile(self, scenes, catalogue, client) -> None:
        _seam(scenes)
        assert client().get(_path(0, 0, 0)).status_code == 200

    def test_a_dataset_without_a_substitute_is_a_404(self, scenes, catalogue, client) -> None:
        _seam(scenes)
        api = client()
        for dataset in (PLAIN_ID, SURFACE_ID, "no-such-dataset"):
            response = api.get(_path(base=f"/collections/{dataset}/overview"))
            assert response.status_code == 404, (dataset, response.text)
        assert catalogue.asked == []

    def test_a_dataset_without_a_viewer_is_a_404(self, scenes, catalogue, client) -> None:
        _seam(scenes)
        bare = replace(
            _PLAIN,
            dataset_id="synthetic-bare",
            viewer=None,
            search_capabilities=SearchCapabilities(evaluate=False, aoi_coverage=False),
        )
        api = client(DatasetRegistry((TERRAIN, SURFACE, bare)))
        assert api.get(_path(base="/collections/synthetic-bare/overview")).status_code == 404

    def test_a_dataset_below_display_is_a_403_before_anything_is_asked(self, scenes, catalogue, client) -> None:
        _seam(scenes)
        catalogue_only = replace(
            TERRAIN,
            license=replace(TERRAIN.license, tier=LicenseTier.CATALOG),
            viewer=None,
            search_capabilities=SearchCapabilities(evaluate=False, aoi_coverage=False),
        )
        api = client(DatasetRegistry((catalogue_only, SURFACE)))
        assert api.get(_path()).status_code == 403
        assert catalogue.asked == []

    def test_a_substitute_below_display_is_a_403_too(self, scenes, catalogue, client) -> None:
        """The registry refuses such a pair when it is built; the route does not rely on that alone."""
        _seam(scenes)
        registry = DatasetRegistry((TERRAIN, SURFACE))
        lowered = replace(SURFACE, license=replace(SURFACE.license))
        object.__setattr__(lowered.license, "tier", LicenseTier.CATALOG)  # what no registry would let in
        registry._by_id[SURFACE_ID] = lowered
        assert client(registry).get(_path()).status_code == 403
        assert catalogue.asked == []

    def test_a_federated_substitute_is_a_501_until_there_is_one(self, scenes, catalogue, client) -> None:
        _seam(scenes)
        federated = replace(
            SURFACE,
            source=replace(SURFACE.source, item_holding=ItemHolding.FEDERATED),
            coverage=replace(SURFACE.coverage, provider=_PLAIN.coverage.provider),
        )
        assert client(DatasetRegistry((TERRAIN, federated))).get(_path()).status_code == 501
        assert catalogue.asked == []

    def test_without_the_catalogue_database_it_is_a_503(self, scenes, catalogue, client) -> None:
        _seam(scenes)
        response = client(pool=None).get(_path())
        assert response.status_code == 503
        assert scenes.opened == []

    def test_a_failing_catalogue_is_a_503_that_does_not_name_the_database(self, scenes, catalogue, client) -> None:
        _seam(scenes)
        catalogue.fail = psycopg.OperationalError("connection to server at db.internal.invalid failed")
        response = client().get(_path())
        assert response.status_code == 503
        assert "internal" not in response.text

    @pytest.mark.parametrize("parameter", ["expression", "algorithm", "algorithm_params"])
    def test_a_free_expression_is_refused_as_on_every_tile(self, scenes, catalogue, client, parameter) -> None:
        _seam(scenes)
        assert client().get(_path(), params={parameter: "b1"}).status_code == 400
        assert catalogue.asked == []

    def test_a_tile_size_the_tiler_does_not_serve_is_refused_before_anything_is_asked(
        self, scenes, catalogue, client
    ) -> None:
        _seam(scenes)
        assert client().get(_path(), params={"tilesize": "100"}).status_code == 400
        assert catalogue.asked == []

    @pytest.mark.parametrize("tail", ["WebMercatorQuad/tilejson.json", "WebMercatorQuad/info", "statistics", "info"])
    def test_there_is_no_route_but_the_tile(self, scenes, catalogue, client, tail: str) -> None:
        _seam(scenes)
        api = client()
        for method in ("get", "post"):
            assert getattr(api, method)(f"{BASE}/{tail}").status_code in (404, 405)
        assert api.post(_path()).status_code == 405

    def test_the_prefix_is_the_one_the_client_builds(self) -> None:
        assert OVERVIEW_ROUTER_PREFIX == "/collections/{dataset}/overview"


class TestWhatNeverComesFromTheSubstitute:
    """Statistics, crop and the rest hang on the dataset and its items; the substitute is a picture of the tile route only.

    ``T1`` is an item of ``TERRAIN`` itself, ``SUB1`` one of its substitute. Whatever else is asked of ``TERRAIN``, only the
    address of ``T1`` is ever cleared; below its first level the tile reads ``SUB1`` and never ``T1``.
    """

    @pytest.fixture
    def pair(self, scenes: Scenes, catalogue: Catalogue) -> list[tuple[str, str]]:
        scenes.add("T1", ZONE_32, SEAM_X - 4000.0, 8000.0, 50)
        scenes.add("SUB1", ZONE_32, SEAM_X - 4000.0, 8000.0, 200)
        catalogue.holds = {"SUB1"}
        fetched: list[tuple[str, str]] = []

        async def source(dataset_id: str, item_id: str) -> dict[str, Any]:
            fetched.append((dataset_id, item_id))
            if (dataset_id, item_id) != (TERRAIN_ID, "T1"):
                raise AssertionError(f"{dataset_id}/{item_id} is not an item of the dataset that is asked for")
            return json.loads(json.dumps(scenes.items["T1"]))

        self.source = source
        return fetched

    def test_the_statistics_of_the_dataset_are_those_of_its_own_item(self, scenes, catalogue, client, pair) -> None:
        response = client(item_source=self.source).get(
            f"{BASE.replace('overview', 'items/T1')}/statistics", params={"asset": ASSET}
        )
        assert response.status_code == 200, response.text
        # the flat value of T1 (50), not that of the substitute's item over the same place (200)
        assert "50.0" in response.text and "200.0" not in response.text
        assert pair == [(TERRAIN_ID, "T1")]
        assert catalogue.asked == []
        assert [address for address in scenes.cleared if "SUB1" in address] == []

    def test_the_tile_below_the_first_level_reads_the_substitute_and_not_the_dataset(
        self, scenes, catalogue, client, pair
    ) -> None:
        tile = _array(client(item_source=self.source).get(_path()))
        assert value_at(tile, SEAM_X + 500.0) == 200
        assert [address for address in scenes.cleared if "T1" in address] == []
        assert pair == []

    def test_the_tile_of_the_dataset_from_its_first_level_on_reads_its_own_item(
        self, scenes, catalogue, client, pair
    ) -> None:
        z13 = TMS.tile(*TMS.lnglat(*TMS.xy_bounds(TILE)[:2]), 13)
        response = client(item_source=self.source).get(
            f"/collections/{TERRAIN_ID}/items/T1/tiles/WebMercatorQuad/{z13.z}/{z13.x}/{z13.y}.npy",
            params={"asset": ASSET},
        )
        assert response.status_code == 200, response.text
        assert pair == [(TERRAIN_ID, "T1")]
        assert catalogue.asked == []
        assert [address for address in scenes.cleared if "SUB1" in address] == []


def _references(tree: ast.AST) -> Iterator[tuple[str, str]]:
    """Every use of the name of the substitute or of what reads it in a module: (kind, name of the function it is in)."""
    wanted = {"overview_substitute", "items_in_tile", "search_items_in_bbox_async", "SUBSTITUTE"}

    def walk(node: ast.AST, inside: str) -> Iterator[tuple[str, str]]:
        for child in ast.iter_child_nodes(node):
            where = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else inside
            name = (
                child.attr if isinstance(child, ast.Attribute)
                else child.id if isinstance(child, ast.Name)
                else child.arg if isinstance(child, ast.keyword) and child.arg
                else child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                else child.value if isinstance(child, ast.Constant) and isinstance(child.value, str)
                else None
            )  # fmt: skip
            if name in wanted:
                yield name, where
            yield from walk(child, where)

    return walk(tree, "<module>")


def test_no_code_but_the_registry_the_collection_and_the_substitute_route_names_the_substitute() -> None:
    """The routes of statistics, histogram, area statistics, crop and download, and the jobs, cannot read the substitute by name.

    A scan of the code of ``earthx``: the places that may mention it are the registry that checks the pair, the collection
    that publishes it, the search that finds its items and the one path dependency of its tile route.
    """
    root = Path(earthx.__file__).parent
    found: dict[str, set[tuple[str, str]]] = {}
    for path in sorted(root.rglob("*.py")):
        uses = set(_references(ast.parse(path.read_text())))
        if uses:
            found[path.relative_to(root).as_posix()] = uses
    assert set(found) == {
        "api/mosaic_tiles.py",
        "api/tiler.py",
        "catalog/collection.py",
        "catalog/pgstac.py",
        "catalog/registry.py",
    }
    assert {where for _, where in found["api/tiler.py"]} == {"overview_scenes"}
    assert {name for name, _ in found["api/tiler.py"]} == {"overview_substitute", "items_in_tile", "SUBSTITUTE"}
    assert {where for _, where in found["api/mosaic_tiles.py"]} == {"items_in_tile", "<module>"}
    assert {where for _, where in found["catalog/collection.py"]} == {"to_stac_collection"}
