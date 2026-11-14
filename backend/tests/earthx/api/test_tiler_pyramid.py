"""The tile below the first level from the overview pyramid (M5-30b part 9, plan §8.11, adr/0032 §5.2).

The real app over synthetic data: the pyramid is a set of tiles that `processing.overview.encode_tile` writes, in an
in-process S3 (`moto`), under the keys `objectstore` names; the rows of `earthx_overview` come from a double of the one
SQL function the route asks (the function itself is tested against a real database in
`integration/test_overview_state.py`). ``RELIEF`` is a dataset with a pyramid and released from z7; ``TERRAIN`` is a
dataset released from z13 that has ``RELIEF`` as its substitute, as swissALTI3D has GLO-30.
"""

from __future__ import annotations

import ast
import io
import logging
from collections.abc import Callable, Iterator
from contextlib import ExitStack, asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import morecantile
import numpy
import psycopg
import pytest
import rasterio
from fastapi import FastAPI
from fastapi.testclient import TestClient

import earthx
from earthx.api import mosaic_tiles, overview_tiles
from earthx.api.tiler import build_app
from earthx.catalog.pgstac import OverviewState
from earthx.catalog.registry import (
    DatasetRegistry,
    ItemHolding,
    LegalStatus,
    OverviewMode,
    OverviewResampling,
    SearchCapabilities,
    SpatialExtent,
)
from earthx.objectstore.client import S3
from earthx.objectstore.errors import StoreUnavailable
from earthx.objectstore.overviews import EXTEND_WINDOW, upload_tile
from earthx.objectstore.results import Store
from earthx.processing.overview import encode_tile, tile_image
from tests.catalog.entries import SENTINEL_2_L2A
from tests.earthx.access.test_mosaic_tiles import SEAM_X, TILE
from tests.earthx.api.test_tiler_mosaic import ZONE_32, Scenes, _serve
from tests.earthx.processing import sources
from tests.earthx.readers import mini_zarr

from ..objectstore.conftest import store, store_env  # noqa: F401 - fixtures
from .test_tiler_overview import WITH_POOL, Catalogue

RELIEF_ID, TERRAIN_ID, PLAIN_ID, PROTO_ID = "synthetic-relief", "synthetic-terrain", "synthetic-plain", "proto-relief"
VERSION = "0123456789abcdef"
NODATA = -9999.0
TMS = morecantile.tms.get("WebMercatorQuad")

#: A part of Europe: the tile of every level that holds it, and the extent TERRAIN stands for inside it.
LON, LAT = 8.2, 46.8
EXTENT = (7.0, 46.0, 9.0, 47.5)

_PLAIN = replace(
    SENTINEL_2_L2A,
    dataset_id=PLAIN_ID,
    source=replace(SENTINEL_2_L2A.source, asset_hosts=(sources.HOST,)),
    band_units={**SENTINEL_2_L2A.band_units, SENTINEL_2_L2A.default_render.assets[0]: "m"},
)
RELIEF = replace(
    _PLAIN,
    dataset_id=RELIEF_ID,
    viewer=replace(
        _PLAIN.viewer,
        min_zoom=7,
        max_zoom=15,
        overview=OverviewMode.PYRAMID,
        overview_resampling=OverviewResampling.AVERAGE,
        overview_substitute=None,
    ),
)
PROTOTYPE = replace(RELIEF, dataset_id=PROTO_ID, legal_status=LegalStatus.UNCLEAR, legal_note="synthetic: a prototype source")
TERRAIN = replace(
    _PLAIN,
    dataset_id=TERRAIN_ID,
    spatial_extent=SpatialExtent(EXTENT),
    viewer=replace(
        _PLAIN.viewer,
        min_zoom=13,
        max_zoom=20,
        overview=OverviewMode.SUBSTITUTE,
        overview_resampling=None,
        overview_substitute=RELIEF_ID,
    ),
)
REGISTRY = DatasetRegistry((RELIEF, TERRAIN, _PLAIN, PROTOTYPE))


def tile_at(z: int) -> Any:
    return TMS.tile(LON, LAT, z)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def wall(self) -> datetime:
        return datetime(2026, 11, 14, tzinfo=UTC)


class Rows:
    """The rows of ``earthx_overview`` as the one function the route asks gives them, and what it was asked."""

    def __init__(self) -> None:
        self.states: dict[str, OverviewState] = {}
        self.asked: list[tuple[str, datetime]] = []
        self.confirmed_after: dict[str, datetime | None] = {}
        self.fail: Exception | None = None

    def ready(self, *dataset_ids: str) -> None:
        for dataset_id in dataset_ids:
            self.states[dataset_id] = OverviewState("ready", VERSION)

    async def __call__(
        self, conn: Any, dataset_id: str, *, fresh_after: datetime, confirmed_after: datetime | None = None
    ) -> OverviewState:
        self.asked.append((dataset_id, fresh_after))
        self.confirmed_after[dataset_id] = confirmed_after
        if self.fail is not None:
            raise self.fail
        return self.states.get(dataset_id, OverviewState("none"))


def stored_tile(z: int, *, left: float = 100.0, right: float = 200.0, holes: int = 10) -> bytes:
    """The bytes of a tile of the pyramid: ``left`` and ``right`` halves, the first ``holes`` columns without a value."""
    values = numpy.full((512, 512), left, dtype="float32")
    values[:, 256:] = right
    mask = numpy.zeros((512, 512), dtype=bool)
    mask[:, :holes] = True
    return encode_tile(tile_image(numpy.ma.array(values, mask=mask), tile_at(z), nodata=NODATA))


class Pyramids:
    """The object store with the pyramid tiles of a test in it, and the reads it was asked for."""

    def __init__(self, held: Store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.store = held
        self.tmp_path = tmp_path
        self.reads: list[str] = []
        self.fail: Exception | None = None
        original = S3.get_bytes_and_metadata

        def counting(client: S3, key: str) -> Any:
            self.reads.append(key)
            if self.fail is not None:
                raise self.fail
            return original(client, key)

        monkeypatch.setattr(S3, "get_bytes_and_metadata", counting)

    def put(self, dataset_id: str, z: int, data: bytes | None = None, *, version: str = VERSION) -> None:
        path = self.tmp_path / f"{dataset_id}-{z}.tif"
        path.write_bytes(stored_tile(z) if data is None else data)
        tile = tile_at(z)
        upload_tile(self.store, dataset_id, version, z, tile.x, tile.y, path, checked_at=datetime(2026, 11, 14, tzinfo=UTC))


@pytest.fixture
def rows(monkeypatch: pytest.MonkeyPatch) -> Rows:
    rows = Rows()
    monkeypatch.setattr(overview_tiles, "overview_state_async", rows)
    return rows


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def pyramids(store: Store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Pyramids:  # noqa: F811
    return Pyramids(store, tmp_path, monkeypatch)


@pytest.fixture
def client(
    rows: Rows, clock: Clock, pyramids: Pyramids, store: Store  # noqa: F811
) -> Iterator[Callable[..., TestClient]]:
    stack = ExitStack()

    def build(*, pool: Any = WITH_POOL, sources_: Any = "default", registry: DatasetRegistry = REGISTRY) -> TestClient:
        @asynccontextmanager
        async def lifespan(app: FastAPI) -> Any:
            app.state.earthx_cache_pool = pool
            app.state.earthx_overviews = (
                overview_tiles.OverviewSources(store, clock=clock.monotonic, now=clock.wall)
                if sources_ == "default"
                else sources_
            )
            yield

        return stack.enter_context(TestClient(build_app(registry, lifespan=lifespan)))

    with stack:
        yield build


def path(dataset: str, z: int, *, extension: str = "npy", x: int | None = None, y: int | None = None) -> str:
    tile = tile_at(z) if z >= 0 else tile_at(0)
    return f"/collections/{dataset}/overview/tiles/WebMercatorQuad/{z}/{tile.x if x is None else x}/{tile.y if y is None else y}.{extension}"


def array(response: Any) -> numpy.ndarray:
    assert response.status_code == 200, response.text
    return numpy.load(io.BytesIO(response.content))


def alpha(response: Any) -> numpy.ndarray:
    """The transparency of a PNG tile: 0 where the picture has no pixel, 255 where it has."""
    assert response.status_code == 200, response.text
    with rasterio.MemoryFile(response.content) as memory, memory.open() as picture:
        return picture.read(picture.count)


class TestTheTileOfAPyramid:
    def test_a_ready_pyramid_gives_its_tile_and_says_where_it_comes_from(self, rows, pyramids, client) -> None:
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6)
        response = client().get(path(RELIEF_ID, 6), params={"tilesize": "512"})
        tile = array(response)
        assert tile.shape[-2:] == (512, 512)
        assert tile[0, 100, 100] == 100 and tile[0, 100, 400] == 200
        assert response.headers[mosaic_tiles.SOURCE_HEADER] == overview_tiles.OVERVIEW_SOURCE == "overview"
        assert overview_tiles.OVERVIEW_HEADER not in response.headers
        assert "no-store" not in response.headers.get("cache-control", "")

    def test_the_pixels_without_a_value_are_transparent(self, rows, pyramids, client) -> None:
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6)
        transparency = alpha(client().get(path(RELIEF_ID, 6, extension="png"), params={"tilesize": "512", "rescale": "0,255"}))
        assert (transparency[:, :10] == 0).all() and (transparency[:, 10:] == 255).all()

    def test_it_is_read_from_the_key_of_its_version_and_nothing_else(self, rows, pyramids, client) -> None:
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6)
        tile = tile_at(6)
        array(client().get(path(RELIEF_ID, 6)))
        assert pyramids.reads == [f"overviews/{RELIEF_ID}/{VERSION}/6/{tile.x}/{tile.y}.tif"]

    def test_the_display_parameters_of_the_request_are_applied_as_on_every_tile(self, rows, pyramids, client) -> None:
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6)
        api = client()
        plain = api.get(path(RELIEF_ID, 6, extension="png"))
        stretched = api.get(path(RELIEF_ID, 6, extension="png"), params={"rescale": "0,1000"})
        coloured = api.get(path(RELIEF_ID, 6, extension="png"), params={"rescale": "0,255", "colormap_name": "viridis"})
        assert plain.status_code == stretched.status_code == coloured.status_code == 200
        assert len({plain.content, stretched.content, coloured.content}) == 3
        assert array(api.get(path(RELIEF_ID, 6), params={"rescale": "0,1000"}))[0, 100, 100] != 100

    def test_the_tile_is_the_size_the_client_asks_for(self, rows, pyramids, client) -> None:
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6)
        api = client()
        assert array(api.get(path(RELIEF_ID, 6), params={"tilesize": "512"})).shape[-2:] == (512, 512)
        assert array(api.get(path(RELIEF_ID, 6), params={"tilesize": "256"})).shape[-2:] == (256, 256)

    def test_the_same_url_gives_the_same_bytes_whoever_asks(self, rows, pyramids, client) -> None:
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6)
        first, second = (client().get(path(RELIEF_ID, 6, extension="png")) for _ in range(2))
        assert first.status_code == 200 and first.content == second.content

    def test_the_lowest_level_has_a_tile(self, rows, pyramids, client) -> None:
        rows.ready(RELIEF_ID)
        tile = tile_at(0)
        path_ = pyramids.tmp_path / "root.tif"
        path_.write_bytes(stored_tile(0))
        upload_tile(pyramids.store, RELIEF_ID, VERSION, 0, tile.x, tile.y, path_, checked_at=datetime(2026, 11, 14, tzinfo=UTC))
        assert client().get(path(RELIEF_ID, 0)).status_code == 200

    def test_a_prototype_source_is_sent_private_no_store(self, rows, pyramids, client) -> None:
        """The words of adr/0024 R7, on the tile of a pyramid and on every other answer for the source."""
        rows.ready(PROTO_ID, RELIEF_ID)
        pyramids.put(PROTO_ID, 6)
        pyramids.put(RELIEF_ID, 6)
        api = client()
        proto = api.get(path(PROTO_ID, 6))
        assert proto.status_code == 200 and proto.headers["cache-control"] == "private, no-store"
        assert "no-store" not in api.get(path(RELIEF_ID, 6)).headers.get("cache-control", "")

    def test_the_answers_without_a_tile_of_a_prototype_source_are_private_no_store_too(
        self, rows, pyramids, client
    ) -> None:
        rows.ready(PROTO_ID)
        api = client()
        no_data = api.get(path(PROTO_ID, 5))  # ready, and no object for this tile
        assert no_data.status_code == 404 and no_data.headers["cache-control"] == "private, no-store"
        rows.states[PROTO_ID] = OverviewState("building")
        api2 = client()
        building = api2.get(path(PROTO_ID, 5))
        assert building.status_code == 404 and building.headers["cache-control"] == "private, no-store"
        assert building.headers[overview_tiles.OVERVIEW_HEADER] == "building"
        assert client(sources_=None).get(path(PROTO_ID, 5)).headers["cache-control"] == "private, no-store"

    def test_the_term_asked_for_is_that_of_the_dataset(self, rows, pyramids, client, clock) -> None:
        rows.ready(RELIEF_ID, PROTO_ID)
        pyramids.put(RELIEF_ID, 6)
        pyramids.put(PROTO_ID, 6)
        api = client()
        api.get(path(RELIEF_ID, 6))
        api.get(path(PROTO_ID, 6))
        (_, regular), (_, prototype) = rows.asked
        assert (clock.wall() - regular).days == 30 and (clock.wall() - prototype).days == 7

    def test_a_confirmation_counts_inside_the_window_of_the_worker_for_a_regular_source_and_never_for_a_prototype(
        self, rows, pyramids, client, clock
    ) -> None:
        rows.ready(RELIEF_ID, PROTO_ID)
        pyramids.put(RELIEF_ID, 6)
        pyramids.put(PROTO_ID, 6)
        api = client()
        api.get(path(RELIEF_ID, 6))
        api.get(path(PROTO_ID, 6))
        assert clock.wall() - rows.confirmed_after[RELIEF_ID] == EXTEND_WINDOW
        from earthx.jobs import overviews as worker_rules

        assert worker_rules.EXTEND_WINDOW is EXTEND_WINDOW, "the sweep of the worker and the route read one window"
        assert rows.confirmed_after[PROTO_ID] is None


class TestWithoutAPyramid:
    @pytest.mark.parametrize(
        ("state", "reason"),
        [
            (OverviewState("building"), "building"),
            (OverviewState("failed", failure_kind="source_timeout"), "failed"),
            (OverviewState("failed", failure_kind="expired"), "failed"),
            (OverviewState("none"), "building"),
        ],
    )
    def test_the_tile_is_a_404_that_says_why_and_is_not_kept(self, rows, pyramids, client, state, reason) -> None:
        rows.states[RELIEF_ID] = state
        response = client().get(path(RELIEF_ID, 6))
        assert response.status_code == 404
        assert response.headers[overview_tiles.OVERVIEW_HEADER] == reason
        assert response.headers["cache-control"] == "no-store"
        assert mosaic_tiles.SOURCE_HEADER not in response.headers
        assert pyramids.reads == []

    def test_a_pyramid_that_is_there_but_has_no_object_for_the_tile_is_a_404_without_a_reason(
        self, rows, pyramids, client
    ) -> None:
        """A tile without data is not stored, so an absent object is such a tile, whatever the row says."""
        rows.ready(RELIEF_ID)
        response = client().get(path(RELIEF_ID, 5))
        assert response.status_code == 404
        assert overview_tiles.OVERVIEW_HEADER not in response.headers
        assert len(pyramids.reads) == 1

    def test_a_tile_of_another_version_is_not_read(self, rows, pyramids, client) -> None:
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6, version="fedcba9876543210")
        assert client().get(path(RELIEF_ID, 6)).status_code == 404

    def test_an_unreachable_store_is_a_503_that_names_nothing(self, rows, pyramids, client, caplog) -> None:
        rows.ready(RELIEF_ID)

        pyramids.fail = StoreUnavailable("GetObject: could not connect to http://objectstore.internal.invalid:3900")
        with caplog.at_level(logging.WARNING):
            response = client().get(path(RELIEF_ID, 6))
        assert response.status_code == 503
        assert "internal" not in response.text and "internal" not in caplog.text
        assert overview_tiles.OVERVIEW_HEADER not in response.headers

    def test_a_process_without_a_key_for_the_store_is_a_503(self, rows, client) -> None:
        rows.ready(RELIEF_ID)
        assert client(sources_=None).get(path(RELIEF_ID, 6)).status_code == 503

    def test_without_the_catalogue_database_it_is_a_503(self, rows, pyramids, client) -> None:
        assert client(pool=None).get(path(RELIEF_ID, 6)).status_code == 503
        assert pyramids.reads == []

    def test_a_failing_catalogue_is_a_503_that_does_not_name_the_database(self, rows, pyramids, client) -> None:
        rows.fail = psycopg.OperationalError("connection to server at db.internal.invalid failed")
        response = client().get(path(RELIEF_ID, 6))
        assert response.status_code == 503 and "internal" not in response.text

    def test_a_stored_object_that_is_no_raster_is_a_502_not_a_crash(self, rows, pyramids, client) -> None:
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6, b"not a tiff at all")
        assert client().get(path(RELIEF_ID, 6)).status_code == 502

    def test_a_stored_tile_that_lies_elsewhere_is_a_502(self, rows, pyramids, client) -> None:
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6, stored_tile(5))  # the bytes of another tile under the key of this one
        assert client().get(path(RELIEF_ID, 6)).status_code == 502


class TestWhatTheRouteRefuses:
    def test_a_level_from_the_first_level_of_the_dataset_on_is_a_400_before_anything_is_asked(
        self, rows, pyramids, client
    ) -> None:
        rows.ready(RELIEF_ID)
        api = client()
        for z in (7, 8, 15, 30, -1):
            response = api.get(path(RELIEF_ID, z, x=0, y=0))
            assert response.status_code == 400, (z, response.text)
        assert "z7" in api.get(path(RELIEF_ID, 7, x=0, y=0)).json()["detail"]
        assert rows.asked == [] and pyramids.reads == []

    def test_a_tile_outside_the_matrix_is_a_404_before_anything_is_asked(self, rows, pyramids, client) -> None:
        rows.ready(RELIEF_ID)
        api = client()
        assert api.get(path(RELIEF_ID, 3, x=8, y=0)).status_code == 404
        assert api.get(path(RELIEF_ID, 3, x=0, y=99)).status_code == 404
        assert rows.asked == [] and pyramids.reads == []

    @pytest.mark.parametrize("tail", ["a/0.npy", "0/b.npy"])
    def test_a_tile_that_is_not_a_number_is_refused_before_anything_is_asked(self, rows, pyramids, client, tail) -> None:
        rows.ready(RELIEF_ID)
        response = client().get(f"/collections/{RELIEF_ID}/overview/tiles/WebMercatorQuad/3/{tail}")
        assert response.status_code == 400
        assert rows.asked == [] and pyramids.reads == []

    def test_a_dataset_without_a_pyramid_or_a_substitute_is_a_404(self, rows, pyramids, client) -> None:
        rows.ready(RELIEF_ID)
        api = client()
        for dataset in (PLAIN_ID, "no-such-dataset"):
            assert api.get(path(dataset, 3)).status_code == 404, dataset
        assert rows.asked == [] and pyramids.reads == []

    @pytest.mark.parametrize("parameter", ["expression", "algorithm", "algorithm_params"])
    def test_a_free_expression_is_refused_as_on_every_tile(self, rows, pyramids, client, parameter) -> None:
        rows.ready(RELIEF_ID)
        assert client().get(path(RELIEF_ID, 6), params={parameter: "b1"}).status_code == 400
        assert rows.asked == []

    def test_a_tile_size_the_tiler_does_not_serve_is_refused_before_anything_is_asked(self, rows, pyramids, client) -> None:
        rows.ready(RELIEF_ID)
        assert client().get(path(RELIEF_ID, 6), params={"tilesize": "100"}).status_code == 400
        assert rows.asked == []

    def test_a_band_the_pyramid_does_not_have_is_a_400(self, rows, pyramids, client) -> None:
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6)
        api = client()
        assert api.get(path(RELIEF_ID, 6), params={"bidx": "2"}).status_code == 400
        assert api.get(path(RELIEF_ID, 6), params={"bidx": "1"}).status_code == 200

    @pytest.mark.parametrize("tail", ["WebMercatorQuad/tilejson.json", "WebMercatorQuad/info", "statistics", "info"])
    def test_there_is_no_route_but_the_tile(self, rows, client, tail: str) -> None:
        api = client()
        for method in ("get", "post"):
            assert getattr(api, method)(f"/collections/{RELIEF_ID}/overview/{tail}").status_code in (404, 405)


class TestFromTheFirstLevelOnTheOriginalsServe:
    def test_the_route_of_the_dataset_s_own_tiles_reads_no_pyramid_and_is_not_released_below_its_first_level(
        self, rows, pyramids, client
    ) -> None:
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6)
        below = f"/collections/{RELIEF_ID}/items/ANY/tiles/WebMercatorQuad/6/{tile_at(6).x}/{tile_at(6).y}.npy"
        assert client().get(below, params={"asset": "B04"}).status_code == 400
        assert pyramids.reads == [] and rows.asked == []


class TestTheStateIsKeptForAShortTime:
    def test_a_ready_answer_is_believed_for_a_while_then_asked_again(self, rows, pyramids, client, clock) -> None:
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6)
        api = client()
        for _ in range(5):
            assert api.get(path(RELIEF_ID, 6)).status_code == 200
        assert len(rows.asked) == 1
        clock.now += overview_tiles.READY_KEPT + 1
        api.get(path(RELIEF_ID, 6))
        assert len(rows.asked) == 2

    def test_another_answer_is_believed_for_less_so_that_the_map_finds_the_pyramid_soon(
        self, rows, pyramids, client, clock
    ) -> None:
        rows.states[RELIEF_ID] = OverviewState("building")
        pyramids.put(RELIEF_ID, 6)
        api = client()
        assert api.get(path(RELIEF_ID, 6)).status_code == 404
        rows.ready(RELIEF_ID)  # the build ended
        assert api.get(path(RELIEF_ID, 6)).status_code == 404
        clock.now += overview_tiles.UNREADY_KEPT + 0.1
        assert api.get(path(RELIEF_ID, 6)).status_code == 200
        assert overview_tiles.UNREADY_KEPT < overview_tiles.READY_KEPT

    def test_each_dataset_has_its_own_answer(self, rows, pyramids, client) -> None:
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6)
        api = client()
        assert api.get(path(RELIEF_ID, 6)).status_code == 200
        assert api.get(path(PROTO_ID, 6)).headers[overview_tiles.OVERVIEW_HEADER] == "building"


class TestTheSubstituteBelowTheLevelOfItsSubstitute:
    """swissALTI3D below z13 shows GLO-30; below z7 that is GLO-30's pyramid, cut to the extent of swissALTI3D."""

    def test_the_tile_is_the_pyramid_of_the_substitute_and_says_substitute(self, rows, pyramids, client) -> None:
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6)
        response = client().get(path(TERRAIN_ID, 6), params={"tilesize": "512"})
        tile = array(response)
        assert response.headers[mosaic_tiles.SOURCE_HEADER] == mosaic_tiles.SUBSTITUTE_SOURCE
        assert [dataset for dataset, _ in rows.asked] == [RELIEF_ID]
        assert pyramids.reads[0].startswith(f"overviews/{RELIEF_ID}/")
        assert tile[0, 256, 256] in (100, 200)

    def test_the_picture_stops_at_the_extent_of_the_dataset_that_is_drawn(self, rows, pyramids, client) -> None:
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 5)
        response = client().get(path(TERRAIN_ID, 5, extension="png"), params={"tilesize": "512", "rescale": "0,255"})
        left, bottom, right, top = TMS.xy_bounds(tile_at(5))
        west, south = TMS.xy(EXTENT[0], EXTENT[1])
        east, north = TMS.xy(EXTENT[2], EXTENT[3])
        columns = left + (numpy.arange(512) + 0.5) * (right - left) / 512
        rows_ = top - (numpy.arange(512) + 0.5) * (top - bottom) / 512
        inside = ((columns >= west) & (columns <= east))[None, :] & ((rows_ >= south) & (rows_ <= north))[:, None]
        shown = alpha(response) != 0
        # Over the extent exactly what the pyramid has (but its 10 columns without a value); outside it nothing.
        assert not shown[~inside].any()
        assert shown[inside].mean() > 0.9 and inside.any() and (~inside).any()

    def test_a_tile_over_nothing_of_the_dataset_is_a_404_before_anything_is_asked(self, rows, pyramids, client) -> None:
        rows.ready(RELIEF_ID)
        far = TMS.tile(-100.0, 40.0, 6)
        response = client().get(path(TERRAIN_ID, 6, x=far.x, y=far.y))
        assert response.status_code == 404
        assert rows.asked == [] and pyramids.reads == []

    @pytest.mark.parametrize(
        ("state", "reason"), [(OverviewState("building"), "building"), (OverviewState("failed", failure_kind="x"), "failed")]
    )
    def test_without_the_pyramid_of_the_substitute_it_is_a_404_that_says_why(
        self, rows, pyramids, client, state, reason
    ) -> None:
        rows.states[RELIEF_ID] = state
        response = client().get(path(TERRAIN_ID, 6))
        assert response.status_code == 404 and response.headers[overview_tiles.OVERVIEW_HEADER] == reason
        assert [dataset for dataset, _ in rows.asked] == [RELIEF_ID]

    def test_the_pyramid_of_the_dataset_itself_is_never_asked_for_a_substitute(self, rows, pyramids, client) -> None:
        rows.ready(TERRAIN_ID, RELIEF_ID)
        pyramids.put(RELIEF_ID, 6)
        client().get(path(TERRAIN_ID, 6))
        assert TERRAIN_ID not in [dataset for dataset, _ in rows.asked]

    def test_the_level_below_the_dataset_is_the_limit_for_the_dataset_not_for_the_substitute(
        self, rows, pyramids, client
    ) -> None:
        rows.ready(RELIEF_ID)
        assert client().get(path(TERRAIN_ID, 13, x=0, y=0)).status_code == 400


class TestFromTheLevelOfTheSubstituteOnTheFilesAreRead:
    """z7 to z12 of a dataset that stands in for another is read from the files of the stand-in, as before: its budget
    (32 files, 4 s) and its item cap hold, and the pyramid of the stand-in is not asked."""

    def test_the_tile_reads_the_files_and_not_the_pyramid(self, tmp_path, monkeypatch, rows, pyramids, store) -> None:  # noqa: F811
        scenes = Scenes(tmp_path)
        catalogue = Catalogue(scenes)
        monkeypatch.setattr(mosaic_tiles, "search_items_in_bbox_async", catalogue.search)
        _serve(scenes, monkeypatch)
        scenes.add("WEST", ZONE_32, SEAM_X - 4000.0, 4000.0, 100)
        scenes.add("EAST", ZONE_32, SEAM_X, 4000.0, 200)
        files = replace(
            RELIEF,
            source=replace(RELIEF.source, item_holding=ItemHolding.MATERIALIZED, source_collection_id=RELIEF_ID),
            coverage=replace(RELIEF.coverage, provider=RELIEF.coverage.provider.LOCAL_SQL),
            search_filters=(),
            search_capabilities=SearchCapabilities(evaluate=False, aoi_coverage=False),
        )
        wide = replace(TERRAIN, spatial_extent=_PLAIN.spatial_extent)
        rows.ready(RELIEF_ID)
        pyramids.put(RELIEF_ID, 6)

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> Any:
            app.state.earthx_cache_pool = WITH_POOL
            app.state.earthx_overviews = overview_tiles.OverviewSources(store)
            yield

        app = build_app(DatasetRegistry((files, wide, _PLAIN)), lifespan=lifespan)
        app.state.earthx_resolver = mini_zarr.from_memory
        with TestClient(app) as api:
            response = api.get(f"/collections/{TERRAIN_ID}/overview/tiles/WebMercatorQuad/{TILE.z}/{TILE.x}/{TILE.y}.npy")
        assert response.status_code == 200, response.text
        assert response.headers[mosaic_tiles.SOURCE_HEADER] == mosaic_tiles.SUBSTITUTE_SOURCE
        assert sorted(scenes.opened) == ["EAST", "WEST"]
        assert [dataset for dataset, *_ in catalogue.asked] == [RELIEF_ID]
        assert rows.asked == [] and pyramids.reads == []


def test_only_the_tile_route_of_the_overview_can_reach_a_pyramid() -> None:
    """Statistics, crop, download and jobs read the originals: no other code names the store of the pyramids.

    A scan of the code of ``earthx`` for the state kept on the app (``earthx_overviews``), the class that reads it and the
    function that asks the rows: they appear in the module of the route, in the one function of the tiler that builds the
    tile and in those that hang the state on the app.
    """
    root = Path(earthx.__file__).parent
    wanted = {"earthx_overviews", "OverviewSources", "overview_state_async"}
    found: dict[str, set[str]] = {}

    def walk(node: ast.AST, inside: str, into: set[str]) -> None:
        for child in ast.iter_child_nodes(node):
            where = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else inside
            name = child.attr if isinstance(child, ast.Attribute) else child.id if isinstance(child, ast.Name) else None
            if name in wanted:
                into.add(where)
            if isinstance(child, ast.Constant) and child.value in wanted:
                into.add(where)
            walk(child, where, into)

    for path in sorted(root.rglob("*.py")):
        places: set[str] = set()
        walk(ast.parse(path.read_text()), "<module>", places)
        if places:
            found[path.relative_to(root).as_posix()] = places
    assert set(found) == {"api/overview_tiles.py", "api/tiler.py"}
    assert found["api/tiler.py"] == {"_pyramid_tile", "_overview_sources", "_lifespan", "build_app"}
