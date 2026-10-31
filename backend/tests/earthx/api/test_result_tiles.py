"""The tiles of a job result: read from the object store, without a database (M4-13c-5, plan §3.4).

A synthetic COG is uploaded to an in-process S3 (`moto`) the way the supervisor does it. GDAL cannot reach
that server, so the one seam is `result_tiles.gdal_path`: it receives the URL that `objectstore` signed
(and the tests look at it) and hands GDAL the local file instead. Everything else is the real app.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import numpy
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio._env import get_gdal_config
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles
from rio_tiler.constants import WEB_MERCATOR_TMS

from earthx.api import result_tiles
from earthx.api.result_tiles import HEAD_KEPT, URL_REUSED, ResultSources
from earthx.api.tiler import build_app
from earthx.logging import JsonFormatter
from earthx.objectstore.client import S3
from earthx.objectstore.errors import StoreUnavailable
from earthx.objectstore.results import MIN_REMAINING, RESULT_TTL, Store, new_result_id, upload_result
from tests.earthx.processing import sources

from ..objectstore.conftest import ENDPOINT, store, store_env  # noqa: F401 - fixtures

SIZE = 256
ZOOM = 14
# The raster below in WGS 84, and the tile of zoom 14 over its middle.
BOUNDS = transform_bounds(
    sources.CRS,
    "EPSG:4326",
    sources.ORIGIN_X,
    sources.ORIGIN_Y - SIZE * sources.RESOLUTION,
    sources.ORIGIN_X + SIZE * sources.RESOLUTION,
    sources.ORIGIN_Y,
)
_MIDDLE = WEB_MERCATOR_TMS.tile((BOUNDS[0] + BOUNDS[2]) / 2, (BOUNDS[1] + BOUNDS[3]) / 2, ZOOM)
TILE = (_MIDDLE.z, _MIDDLE.x, _MIDDLE.y)
# A tile that holds the whole raster, for the tests of the mask: its left half is the left half of the picture.
_WIDE = WEB_MERCATOR_TMS.tile((BOUNDS[0] + BOUNDS[2]) / 2, (BOUNDS[1] + BOUNDS[3]) / 2, 11)
_WIDE_BOUNDS = WEB_MERCATOR_TMS.bounds(_WIDE)
assert _WIDE_BOUNDS.left < BOUNDS[0] and BOUNDS[2] < _WIDE_BOUNDS.right, "choose another level"
assert _WIDE_BOUNDS.bottom < BOUNDS[1] and BOUNDS[3] < _WIDE_BOUNDS.top, "choose another level"
WIDE = (_WIDE.z, _WIDE.x, _WIDE.y)


@pytest.fixture(scope="module")
def result_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A one-band float32 COG in UTM 32N, the kind a band-math job writes."""
    root = tmp_path_factory.mktemp("result-tiles")
    plain = root / "plain.tif"
    rows, cols = numpy.indices((SIZE, SIZE))
    with rasterio.open(
        plain,
        "w",
        driver="GTiff",
        width=SIZE,
        height=SIZE,
        count=1,
        dtype="float32",
        crs=sources.CRS,
        transform=from_origin(sources.ORIGIN_X, sources.ORIGIN_Y, sources.RESOLUTION, sources.RESOLUTION),
        nodata=-9999.0,
    ) as destination:
        destination.write(((rows + cols) / (2 * SIZE) * 2 - 1).astype("float32"), 1)
    target = root / "result.tif"
    cog_translate(str(plain), str(target), cog_profiles.get("deflate"), quiet=True)
    return target


def _mask_file(root: Path, name: str, inside) -> Path:
    """A ``mask.tif`` as the job writes it: 1 inside the area, 0 outside, on the grid of the result."""
    rows, cols = numpy.indices((SIZE, SIZE))
    data = inside(rows, cols).astype("uint8")
    path = root / f"{name}.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=SIZE,
        height=SIZE,
        count=1,
        dtype="uint8",
        crs=sources.CRS,
        transform=from_origin(sources.ORIGIN_X, sources.ORIGIN_Y, sources.RESOLUTION, sources.RESOLUTION),
        tiled=True,
        blockxsize=128,
        blockysize=128,
        compress="deflate",
    ) as destination:
        destination.write(data, 1)
    return path


# The shapes of an area: all of it, nothing, the left half, everything but the top right quarter (the union
# of footprints of a "Whole scene" is such an L).
MASKS = {
    "all": lambda rows, cols: numpy.ones_like(rows),
    "none": lambda rows, cols: numpy.zeros_like(rows),
    "left": lambda rows, cols: cols < SIZE // 2,
    "ell": lambda rows, cols: ~((rows < SIZE // 2) & (cols >= SIZE // 2)),
}
SHARE = {"all": 1.0, "none": 0.0, "left": 0.5, "ell": 0.75}


@pytest.fixture(scope="module")
def mask_files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("result-masks")
    return {name: _mask_file(root, name, inside) for name, inside in MASKS.items()}


class Clock:
    """A clock the tests move: `monotonic` for ages in the cache, `now` for the end of a result's life."""

    def __init__(self, now: datetime) -> None:
        self.seconds = 0.0
        self.wall = now

    def monotonic(self) -> float:
        return self.seconds

    def now(self) -> datetime:
        return self.wall

    def advance(self, **delta: float) -> None:
        step = timedelta(**delta)
        self.seconds += step.total_seconds()
        self.wall += step


class Rig:
    def __init__(
        self, client: TestClient, store: Store, clock: Clock, opened: list[str], heads: list[str]  # noqa: F811
    ) -> None:
        self.client = client
        self.store = store
        self.clock = clock
        self.opened = opened  # what GDAL was given, one entry per read
        self.heads = heads  # the keys the store was asked the age of
        self.signed: list[int] = []  # one entry (the lifetime in seconds) per URL signed for GDAL

        self.masks: dict[str, Path] = {}  # the mask GDAL is given for a result id, if not the whole raster

    def tile_url(self, result_id: str, query: str = "", ext: str = "png", tile: tuple[int, int, int] = TILE) -> str:
        z, x, y = tile
        return f"/results/{result_id}/tiles/WebMercatorQuad/{z}/{x}/{y}.{ext}?rescale=-1,1&colormap_name=rdylgn{query}"


@pytest.fixture
def uploaded(store: Store, result_file: Path, mask_files: dict[str, Path]) -> str:  # noqa: F811
    result_id = new_result_id()
    upload_result(store, result_id, "result.tif", result_file)
    upload_result(store, result_id, "mask.tif", mask_files["all"])
    return result_id


@pytest.fixture
def rig(
    store: Store,  # noqa: F811
    result_file: Path,
    mask_files: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Rig]:
    """The real tiler app on a registry-less lifespan: no pool, no item source — only the result routes."""
    opened: list[str] = []
    masks: dict[str, Path] = {}

    def local(url: str) -> str:
        opened.append(url)
        _, result_id, name = urlsplit(url).path.rsplit("/", 2)
        return str(masks.get(result_id, mask_files["all"])) if name == "mask.tif" else str(result_file)

    monkeypatch.setattr(result_tiles, "gdal_path", local)
    # The object was written "now" by moto; the clock starts a minute later.
    clock = Clock(datetime.now(UTC) + timedelta(minutes=1))
    heads: list[str] = []
    original = S3.head_modified

    def counted(self: S3, key: str) -> datetime:
        heads.append(key)
        return original(self, key)

    monkeypatch.setattr(S3, "head_modified", counted)
    signed: list[int] = []
    sign = S3.presign_read

    def counted_sign(self: S3, key: str, expires_in: int) -> str:
        signed.append(expires_in)
        return sign(self, key, expires_in)

    monkeypatch.setattr(S3, "presign_read", counted_sign)

    @asynccontextmanager
    async def lifespan(app):
        app.state.earthx_results = ResultSources(store, clock=clock.monotonic, now=clock.now)
        yield

    app = build_app(lifespan=lifespan)
    with TestClient(app) as client:
        made = Rig(client, store, clock, opened, heads)
        made.signed = signed
        made.masks = masks
        yield made


# --- the tile -------------------------------------------------------------------------------------


def test_a_tile_is_rendered_from_the_stored_result(rig: Rig, uploaded: str) -> None:
    response = rig.client.get(rig.tile_url(uploaded))
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")


def test_gdal_is_given_urls_signed_for_the_internal_endpoint_for_the_result_and_its_mask(
    rig: Rig, uploaded: str
) -> None:
    rig.client.get(rig.tile_url(uploaded))
    urls = set(rig.opened)
    assert {urlsplit(url).path for url in urls} == {
        f"/earthx/results/{uploaded}/result.tif",
        f"/earthx/results/{uploaded}/mask.tif",
    }
    for url in urls:
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        assert f"{parts.scheme}://{parts.netloc}" == ENDPOINT
        assert int(query["X-Amz-Expires"][0]) <= 15 * 60
        # Nothing in it asks for a download name: this URL is for GDAL, not for a person.
        assert "response-content-disposition" not in query


def test_the_tiles_of_a_result_are_read_under_the_tile_profile_of_the_tiler(
    rig: Rig, uploaded: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NM4-26 §13: every route of the tiler carries the same `/vsicurl/` cache size and the tiles read serially."""
    seen: list[tuple[str, str]] = []

    class Recording(result_tiles.ResultReader):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            names = ("GDAL_HTTP_MULTIRANGE", "CPL_VSIL_CURL_CACHE_SIZE")
            seen.append((str(get_gdal_config(names[0])), str(get_gdal_config(names[1]))))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(result_tiles, "ResultReader", Recording)
    assert rig.client.get(rig.tile_url(uploaded)).status_code == 200
    assert seen == [("SERIAL", str(256 * 1024 * 1024))]


def test_the_tilejson_describes_the_result_and_its_tiles(rig: Rig, uploaded: str) -> None:
    response = rig.client.get(f"/results/{uploaded}/WebMercatorQuad/tilejson.json")
    assert response.status_code == 200
    body = response.json()
    west, south, east, north = body["bounds"]
    assert (west, south, east, north) == pytest.approx(BOUNDS, abs=1e-4)
    assert body["minzoom"] <= body["maxzoom"]
    assert body["tiles"][0].split("?")[0].endswith(f"/results/{uploaded}/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}")


def test_the_tilejson_hands_out_tiles_of_256_px_like_the_viewer_draws(rig: Rig, uploaded: str) -> None:
    (template,) = rig.client.get(f"/results/{uploaded}/WebMercatorQuad/tilejson.json").json()["tiles"]
    assert "tilesize=256" in template


@pytest.mark.parametrize("size", ["1024", "4096"])
def test_a_tile_of_another_size_than_256_or_512_is_a_400_and_reads_nothing(rig: Rig, uploaded: str, size: str) -> None:
    response = rig.client.get(rig.tile_url(uploaded, f"&tilesize={size}"))
    assert response.status_code == 400
    assert response.json()["detail"] == "tilesize is 256 or 512"
    assert rig.opened == [] and rig.heads == []


def test_the_tiles_are_read_in_the_data_of_the_result_not_resampled_to_a_flat_picture(rig: Rig, uploaded: str) -> None:
    low = rig.client.get(rig.tile_url(uploaded))
    other = rig.client.get(rig.tile_url(uploaded).replace("rescale=-1,1", "rescale=0,0.1"))
    assert low.status_code == other.status_code == 200
    assert low.content != other.content


def test_the_route_runs_without_a_database(rig: Rig, uploaded: str) -> None:
    app = rig.client.app
    assert getattr(app.state, "earthx_cache_pool", None) is None
    assert rig.client.get(rig.tile_url(uploaded)).status_code == 200


# --- the shape on the map: the mask of the result (Otto, 20.10.2026) ---------------------------------


def _opaque(response) -> numpy.ndarray:
    """The pixels of a tile that are drawn: the alpha band of the GeoTIFF the tile route gives."""
    assert response.status_code == 200, response.text
    with MemoryFile(response.content) as memory, memory.open() as dataset:
        return dataset.read(dataset.count) > 0


def _masked_result(rig: Rig, store: Store, mask_files: dict[str, Path], result_file: Path, kind: str) -> str:  # noqa: F811
    result_id = new_result_id()
    upload_result(store, result_id, "result.tif", result_file)
    upload_result(store, result_id, "mask.tif", mask_files[kind])
    rig.masks[result_id] = mask_files[kind]
    return result_id


@pytest.fixture
def whole(rig: Rig, uploaded: str) -> numpy.ndarray:
    """What is drawn of the result with a mask that marks all of it: the raster's own extent in the tile."""
    drawn = _opaque(rig.client.get(rig.tile_url(uploaded, ext="tif", tile=WIDE)))
    assert drawn.any(), "the tile lies over the raster"
    return drawn


@pytest.mark.parametrize("kind", ["left", "ell"])
def test_the_tile_shows_only_what_the_mask_marks(
    rig: Rig, store: Store, mask_files: dict[str, Path], result_file: Path, whole: numpy.ndarray, kind: str  # noqa: F811
) -> None:
    result_id = _masked_result(rig, store, mask_files, result_file, kind)
    drawn = _opaque(rig.client.get(rig.tile_url(result_id, ext="tif", tile=WIDE)))
    assert not (drawn & ~whole).any(), "the mask only takes pixels away, it adds none"
    assert drawn.sum() / whole.sum() == pytest.approx(SHARE[kind], abs=0.08)
    assert drawn.sum() < whole.sum()


def test_a_mask_that_marks_nothing_leaves_a_tile_nobody_sees(
    rig: Rig, store: Store, mask_files: dict[str, Path], result_file: Path, whole: numpy.ndarray  # noqa: F811
) -> None:
    result_id = _masked_result(rig, store, mask_files, result_file, "none")
    response = rig.client.get(rig.tile_url(result_id, ext="tif"))
    assert not _opaque(response).any()
    png = rig.client.get(rig.tile_url(result_id))
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"


def test_the_same_mask_cuts_every_style(
    rig: Rig, store: Store, mask_files: dict[str, Path], result_file: Path, whole: numpy.ndarray  # noqa: F811
) -> None:
    result_id = _masked_result(rig, store, mask_files, result_file, "left")
    plain = _opaque(rig.client.get(rig.tile_url(result_id, ext="tif", tile=WIDE)))
    other = _opaque(rig.client.get(rig.tile_url(result_id, "&bidx=1", ext="tif", tile=WIDE).replace("rdylgn", "viridis")))
    assert (plain == other).all()


def test_the_files_in_the_store_stay_what_the_job_wrote(
    rig: Rig, store: Store, mask_files: dict[str, Path], result_file: Path  # noqa: F811
) -> None:
    """The download is the bounding box with its mask: the tiler reads, and changes nothing."""
    result_id = _masked_result(rig, store, mask_files, result_file, "left")
    keys = {"result.tif": result_file, "mask.tif": mask_files["left"]}
    before = {name: store.s3._internal.get_object(Bucket="earthx", Key=f"results/{result_id}/{name}")["Body"].read() for name in keys}
    assert rig.client.get(rig.tile_url(result_id, ext="tif")).status_code == 200
    for name, path in keys.items():
        stored = store.s3._internal.get_object(Bucket="earthx", Key=f"results/{result_id}/{name}")["Body"].read()
        assert stored == before[name] == path.read_bytes(), name
    with rasterio.open(result_file) as raster:
        assert not numpy.ma.getmaskarray(raster.read(1, masked=True)).any(), "no pixel of result.tif is taken away"


def test_a_result_without_its_mask_is_not_served(rig: Rig, store: Store, result_file: Path) -> None:  # noqa: F811
    result_id = new_result_id()
    upload_result(store, result_id, "result.tif", result_file)
    response = rig.client.get(rig.tile_url(result_id))
    assert response.status_code == 404
    assert response.json() == {"detail": "there is no such result"}
    assert rig.opened == []


# --- what is refused --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "parameter",
    [
        "expression=b1*2",
        "algorithm=hillshade",
        "algorithm_params=%7B%7D",
        "op=band_math",
        "op_version=1",
        'params=%7B"expression":"b1"%7D',
    ],
)
def test_a_free_parameter_or_an_operator_is_refused(rig: Rig, uploaded: str, parameter: str) -> None:
    response = rig.client.get(rig.tile_url(uploaded, f"&{parameter}"))
    assert response.status_code == 400
    assert "not accepted" in response.json()["detail"]
    assert rig.opened == []


@pytest.mark.parametrize(
    "result_id",
    ["x", "a" * 21, "a" * 23, "a" * 21 + "/", "a" * 21 + ".", "a" * 21 + " ", "%2e%2e%2f" + "a" * 12, "ä" * 22, "../" + "a" * 19],
)
def test_a_made_up_result_id_is_a_404_before_anything_is_read(rig: Rig, result_id: str) -> None:
    response = rig.client.get(f"/results/{result_id}/WebMercatorQuad/tilejson.json")
    assert response.status_code == 404
    assert len(rig.heads) == 0
    assert rig.opened == []


def test_a_result_that_is_not_in_the_store_is_a_404(rig: Rig) -> None:
    response = rig.client.get(rig.tile_url(new_result_id()))
    assert response.status_code == 404
    assert response.json() == {"detail": "there is no such result"}
    assert rig.opened == []


def test_only_the_tiles_the_tilejson_and_the_statistics_exist(rig: Rig, uploaded: str) -> None:
    """The statistics are the one route plan M4-13c §5 left out that NM4-65 added (`test_result_statistics`)."""
    for tail in ("info", "point/9.5,47.0", "WebMercatorQuad/WMTSCapabilities.xml", "bbox/9,47,10,48.png", "preview"):
        assert rig.client.get(f"/results/{uploaded}/{tail}").status_code in (404, 405), tail
    assert rig.client.post(f"/results/{uploaded}/tiles/WebMercatorQuad/14/1/1").status_code == 405


@pytest.mark.parametrize("method", ["put", "delete", "patch"])
def test_a_result_cannot_be_changed_through_the_tiler(rig: Rig, uploaded: str, method: str) -> None:
    assert getattr(rig.client, method)(rig.tile_url(uploaded)).status_code == 405


# --- its life: 7 days from the day it was written ------------------------------------------------


def test_the_result_is_served_up_to_a_minute_before_its_end_and_gone_from_then_on(rig: Rig, uploaded: str) -> None:
    rig.clock.wall = datetime.now(UTC) + RESULT_TTL - MIN_REMAINING - timedelta(seconds=30)
    assert rig.client.get(rig.tile_url(uploaded)).status_code == 200
    rig.clock.wall = datetime.now(UTC) + RESULT_TTL - MIN_REMAINING + timedelta(seconds=30)
    response = rig.client.get(rig.tile_url(uploaded))
    assert response.status_code == 410
    assert response.json() == {"detail": "the result has expired"}


def test_a_result_past_its_end_is_gone_even_with_a_url_still_cached(rig: Rig, uploaded: str) -> None:
    assert rig.client.get(rig.tile_url(uploaded)).status_code == 200
    rig.clock.wall = datetime.now(UTC) + RESULT_TTL + timedelta(hours=1)
    assert rig.client.get(rig.tile_url(uploaded)).status_code == 410
    assert rig.client.get(f"/results/{uploaded}/WebMercatorQuad/tilejson.json").status_code == 410


def test_the_end_is_the_day_it_was_written_plus_seven_days(rig: Rig, uploaded: str, store: Store) -> None:  # noqa: F811
    from earthx.objectstore.results import result_modified

    written = result_modified(store, uploaded, "result.tif")
    rig.clock.wall = written + RESULT_TTL - MIN_REMAINING - timedelta(seconds=1)
    assert rig.client.get(rig.tile_url(uploaded)).status_code == 200
    rig.clock.wall = written + RESULT_TTL - MIN_REMAINING
    assert rig.client.get(rig.tile_url(uploaded)).status_code == 200  # exactly 60 s left is still served
    rig.clock.wall = written + RESULT_TTL - MIN_REMAINING + timedelta(seconds=1)
    assert rig.client.get(rig.tile_url(uploaded)).status_code == 410


# --- what the process remembers --------------------------------------------------------------------


def test_the_head_answer_is_believed_for_60_seconds_and_the_url_for_10_minutes(rig: Rig, uploaded: str) -> None:
    for _ in range(3):
        assert rig.client.get(rig.tile_url(uploaded)).status_code == 200
    assert len(rig.heads) == 2, "one head for the result, one for its mask"
    assert len(rig.signed) == 2

    rig.clock.advance(seconds=HEAD_KEPT.total_seconds() + 1)
    assert rig.client.get(rig.tile_url(uploaded)).status_code == 200
    assert len(rig.heads) == 4
    assert len(rig.signed) == 2, "the same URLs: GDAL's read cache is keyed by them"

    rig.clock.advance(seconds=URL_REUSED.total_seconds())
    assert rig.client.get(rig.tile_url(uploaded)).status_code == 200
    assert len(rig.signed) == 4, "signed again before the first ones ran out"


def test_the_memory_is_bounded(rig: Rig, store: Store, result_file: Path, mask_files: dict[str, Path]) -> None:  # noqa: F811
    sources_ = rig.client.app.state.earthx_results
    ids = [new_result_id() for _ in range(result_tiles.CACHE_SIZE + 5)]
    for result_id in ids:
        upload_result(store, result_id, "result.tif", result_file)
        upload_result(store, result_id, "mask.tif", mask_files["all"])
        sources_.urls(result_id)
    assert len(sources_._entries) == result_tiles.CACHE_SIZE


# --- when the store is not there -----------------------------------------------------------------


def test_a_store_that_cannot_be_reached_is_a_503_that_names_nothing(
    rig: Rig, uploaded: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(self: Any, key: str) -> datetime:
        raise StoreUnavailable("object store HeadObject failed (SlowDown, HTTP 503)")

    monkeypatch.setattr(S3, "head_modified", broken)
    with caplog.at_level(logging.DEBUG):
        response = rig.client.get(rig.tile_url(uploaded))
    assert response.status_code == 503
    assert uploaded not in response.text and "SlowDown" not in response.text
    assert uploaded not in caplog.text


def test_a_tiler_without_the_store_serves_no_results_and_says_so(uploaded: str, result_file: Path) -> None:
    @asynccontextmanager
    async def lifespan(app):
        app.state.earthx_results = None
        yield

    with TestClient(build_app(lifespan=lifespan)) as client:
        response = client.get(f"/results/{uploaded}/WebMercatorQuad/tilejson.json")
    assert response.status_code == 503
    assert response.json() == {"detail": "results are not served by this process"}


def test_the_start_without_s3_settings_still_serves_and_logs_the_setting_not_a_value(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    for name in ("S3_ENDPOINT", "S3_PUBLIC_ENDPOINT", "S3_REGION", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("S3_ENDPOINT", "not a url with secret-value")
    with caplog.at_level(logging.WARNING, logger="earthx.api.tiler"):
        assert result_tiles_unavailable()
    assert "S3_ENDPOINT" in caplog.text
    assert "secret-value" not in caplog.text


def result_tiles_unavailable() -> bool:
    from earthx.api import tiler

    return tiler._result_sources() is None


# --- the log -----------------------------------------------------------------------------------------


def test_the_result_id_is_not_in_the_access_log(rig: Rig, uploaded: str, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        assert rig.client.get(rig.tile_url(uploaded)).status_code == 200
        assert rig.client.get(f"/results/{uploaded}/WebMercatorQuad/tilejson.json").status_code == 200
    records = [r for r in caplog.records if r.name == "earthx.request"]
    assert len(records) == 2
    assert all(record.path.startswith("/results/{resultID}/") for record in records)
    assert uploaded not in caplog.text


def test_a_read_error_leaves_neither_the_signed_url_nor_the_result_id_in_the_log(
    rig: Rig, uploaded: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GDAL puts the path it could not open into its own warning; the line that reaches stdout hides it."""
    signed = f"http://127.0.0.1:1/earthx/results/{uploaded}/result.tif?X-Amz-Credential=GKkeyid%2F20261020&X-Amz-Signature=deadbeef"
    monkeypatch.setattr(result_tiles, "gdal_path", lambda url: f"/vsicurl/{signed}")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logging.getLogger().addHandler(handler)
    try:
        response = rig.client.get(rig.tile_url(uploaded))
    finally:
        logging.getLogger().removeHandler(handler)
    out = stream.getvalue()
    assert response.status_code == 502
    assert "HTTP response code on" in out, "GDAL's warning is there, so the check below looks at something"
    for secret in ("deadbeef", "GKkeyid", uploaded):
        assert secret not in out


def test_the_same_read_error_of_a_source_keeps_its_traceback(caplog: pytest.LogCaptureFixture) -> None:
    """Counter-sample: only a result's route loses the traceback."""
    from types import SimpleNamespace

    from earthx.api.tiler import _may_log_detail

    assert _may_log_detail(SimpleNamespace(url=SimpleNamespace(path="/collections/a/items/b/tiles/WebMercatorQuad/1/2/3")))
    assert not _may_log_detail(SimpleNamespace(url=SimpleNamespace(path=f"/results/{new_result_id()}/tiles/x")))


# --- the shape of a refusal -----------------------------------------------------------------------------


def test_a_json_body_of_a_refusal_has_nothing_but_a_detail(rig: Rig, uploaded: str) -> None:
    response = rig.client.get(rig.tile_url(uploaded, "&op=x"))
    assert set(json.loads(response.text)) == {"detail"}
