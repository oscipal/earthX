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

    def tile_url(self, result_id: str, query: str = "") -> str:
        z, x, y = TILE
        return f"/results/{result_id}/tiles/WebMercatorQuad/{z}/{x}/{y}.png?rescale=-1,1&colormap_name=rdylgn{query}"


@pytest.fixture
def uploaded(store: Store, result_file: Path) -> str:  # noqa: F811
    result_id = new_result_id()
    upload_result(store, result_id, "result.tif", result_file)
    return result_id


@pytest.fixture
def rig(store: Store, result_file: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:  # noqa: F811
    """The real tiler app on a registry-less lifespan: no pool, no item source — only the result routes."""
    opened: list[str] = []

    def local(url: str) -> str:
        opened.append(url)
        return str(result_file)

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
        yield made


# --- the tile -------------------------------------------------------------------------------------


def test_a_tile_is_rendered_from_the_stored_result(rig: Rig, uploaded: str) -> None:
    response = rig.client.get(rig.tile_url(uploaded))
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")


def test_gdal_is_given_a_url_signed_for_the_internal_endpoint_and_read_only(rig: Rig, uploaded: str) -> None:
    rig.client.get(rig.tile_url(uploaded))
    (url,) = set(rig.opened)
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    assert f"{parts.scheme}://{parts.netloc}" == ENDPOINT
    assert parts.path == f"/earthx/results/{uploaded}/result.tif"
    assert int(query["X-Amz-Expires"][0]) <= 15 * 60
    # Nothing in it asks for a download name: this URL is for GDAL, not for a person.
    assert "response-content-disposition" not in query


def test_the_tilejson_describes_the_result_and_its_tiles(rig: Rig, uploaded: str) -> None:
    response = rig.client.get(f"/results/{uploaded}/WebMercatorQuad/tilejson.json")
    assert response.status_code == 200
    body = response.json()
    west, south, east, north = body["bounds"]
    assert (west, south, east, north) == pytest.approx(BOUNDS, abs=1e-4)
    assert body["minzoom"] <= body["maxzoom"]
    assert body["tiles"][0].split("?")[0].endswith(f"/results/{uploaded}/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}")


def test_the_tiles_are_read_in_the_data_of_the_result_not_resampled_to_a_flat_picture(rig: Rig, uploaded: str) -> None:
    low = rig.client.get(rig.tile_url(uploaded))
    other = rig.client.get(rig.tile_url(uploaded).replace("rescale=-1,1", "rescale=0,0.1"))
    assert low.status_code == other.status_code == 200
    assert low.content != other.content


def test_the_route_runs_without_a_database(rig: Rig, uploaded: str) -> None:
    app = rig.client.app
    assert getattr(app.state, "earthx_cache_pool", None) is None
    assert rig.client.get(rig.tile_url(uploaded)).status_code == 200


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


def test_only_the_tiles_and_the_tilejson_exist(rig: Rig, uploaded: str) -> None:
    for tail in ("info", "statistics", "point/9.5,47.0", "WebMercatorQuad/WMTSCapabilities.xml", "bbox/9,47,10,48.png", "preview"):
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
    assert len(rig.heads) == 1
    assert len(rig.signed) == 1

    rig.clock.advance(seconds=HEAD_KEPT.total_seconds() + 1)
    assert rig.client.get(rig.tile_url(uploaded)).status_code == 200
    assert len(rig.heads) == 2
    assert len(rig.signed) == 1, "the same URL: GDAL's read cache is keyed by it"

    rig.clock.advance(seconds=URL_REUSED.total_seconds())
    assert rig.client.get(rig.tile_url(uploaded)).status_code == 200
    assert len(rig.signed) == 2, "signed again before the first one ran out"


def test_the_memory_is_bounded(rig: Rig, store: Store, result_file: Path) -> None:  # noqa: F811
    sources_ = rig.client.app.state.earthx_results
    ids = [new_result_id() for _ in range(result_tiles.CACHE_SIZE + 5)]
    for result_id in ids:
        upload_result(store, result_id, "result.tif", result_file)
        sources_.url(result_id)
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
