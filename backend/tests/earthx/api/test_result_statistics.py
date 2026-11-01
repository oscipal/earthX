"""The statistics of a job result: ``GET /results/{result_id}/statistics`` (NM4-65, adr/0006 Nachtrag NM4-65).

The rig is that of `test_result_tiles` (an in-process S3, GDAL given the local file in place of the signed URL), with
files of its own: synthetic rasters from a seeded generator, each with the ``mask.tif`` the job would have written. The
numbers are checked against numpy on the same arrays, not against the code that computes them.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import numpy
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from earthx.api import result_tiles
from earthx.api.result_tiles import STATISTICS_MAX_AGE, ResultSources
from earthx.api.tiler import build_app
from earthx.objectstore.results import MIN_REMAINING, RESULT_TTL, Store, new_result_id, upload_result
from tests.earthx.api.test_result_tiles import Clock
from tests.earthx.processing import sources

from ..objectstore.conftest import store, store_env  # noqa: F401 - fixtures

# ruff: noqa: F811
HEIGHT, WIDTH = 120, 160
BAND_NAMES = ("red", "nir", "empty")
PERCENTILES = tuple(range(1, 100))
SUMMARY = {"minimum", "maximum", "mean", "stddev", "count", "valid_percent"}
EVERY_KEY = SUMMARY | {f"percentile_{percent}" for percent in PERCENTILES}


def _write(path: Path, data: numpy.ndarray, *, nodata: float | None, names: tuple[str, ...] = ()) -> Path:
    bands, height, width = data.shape
    with rasterio.open(
        path, "w", driver="GTiff", width=width, height=height, count=bands, dtype=str(data.dtype), crs=sources.CRS,
        transform=from_origin(sources.ORIGIN_X, sources.ORIGIN_Y, sources.RESOLUTION, sources.RESOLUTION),
        nodata=nodata, tiled=True, blockxsize=64, blockysize=64,
    ) as destination:  # fmt: skip
        destination.write(data)
        for index, name in enumerate(names, start=1):
            destination.set_band_description(index, name)
    return path


def _inside(height: int = HEIGHT, width: int = WIDTH) -> numpy.ndarray:
    """The area: the left 60 %, without a hole at the top left corner."""
    rows, cols = numpy.indices((height, width))
    return (cols < width * 0.6) & ~((rows < 20) & (cols < 20))


def _mask(path: Path, inside: numpy.ndarray) -> Path:
    return _write(path, inside.astype("uint8")[None], nodata=None)


@dataclass
class Rig:
    client: TestClient
    store: Store
    clock: Clock
    files: dict[tuple[str, str], Path]
    opened: list[str] = field(default_factory=list)
    heads: list[str] = field(default_factory=list)

    def put(self, result: Path, mask: Path | None) -> str:
        result_id = new_result_id()
        upload_result(self.store, result_id, "result.tif", result)
        self.files[(result_id, "result.tif")] = result
        if mask is not None:
            upload_result(self.store, result_id, "mask.tif", mask)
            self.files[(result_id, "mask.tif")] = mask
        return result_id

    def get(self, result_id: str, query: str = ""):
        return self.client.get(f"/results/{result_id}/statistics{query}")


@pytest.fixture
def rig(store: Store, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    files: dict[tuple[str, str], Path] = {}
    opened: list[str] = []

    def local(url: str) -> str:
        opened.append(url)
        _, result_id, name = urlsplit(url).path.rsplit("/", 2)
        return str(files[(result_id, name)])

    monkeypatch.setattr(result_tiles, "gdal_path", local)
    clock = Clock(datetime.now(UTC) + timedelta(minutes=1))
    heads: list[str] = []
    original = type(store.s3).head_modified

    def counted(self, key: str) -> datetime:
        heads.append(key)
        return original(self, key)

    monkeypatch.setattr(type(store.s3), "head_modified", counted)

    @asynccontextmanager
    async def lifespan(app):
        app.state.earthx_results = ResultSources(store, clock=clock.monotonic, now=clock.now)
        yield

    with TestClient(build_app(lifespan=lifespan)) as client:
        yield Rig(client, store, clock, files, opened, heads)


@pytest.fixture(scope="module")
def counts(tmp_path_factory: pytest.TempPathFactory) -> numpy.ndarray:
    """Three uint16 bands: ``red`` and ``nir`` with scattered nodata (0), ``empty`` all nodata."""
    generator = numpy.random.default_rng(7)
    data = generator.integers(1, 5000, size=(3, HEIGHT, WIDTH), dtype=numpy.uint16)
    data[0][generator.random((HEIGHT, WIDTH)) < 0.1] = 0
    data[1] = (data[1] // 3).clip(1)  # another range than band 1
    data[1][generator.random((HEIGHT, WIDTH)) < 0.25] = 0
    data[2] = 0
    return data


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory, counts: numpy.ndarray) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("result-statistics")
    generator = numpy.random.default_rng(11)
    reflectance = generator.normal(0.3, 0.2, size=(1, HEIGHT, WIDTH)).astype("float32")
    reflectance[0][generator.random((HEIGHT, WIDTH)) < 0.1] = -9999.0
    return {
        "counts": _write(root / "counts.tif", counts, nodata=0, names=BAND_NAMES),
        "unnamed": _write(root / "unnamed.tif", counts[:1], nodata=0),
        "reflectance": _write(root / "reflectance.tif", reflectance, nodata=-9999.0, names=("NDVI",)),
        "inside": _mask(root / "inside.tif", _inside()),
        "everything": _mask(root / "everything.tif", numpy.ones((HEIGHT, WIDTH), dtype=bool)),
        "nothing": _mask(root / "nothing.tif", numpy.zeros((HEIGHT, WIDTH), dtype=bool)),
    }


def _expected(values: numpy.ndarray, area_pixels: int) -> dict[str, float]:
    """The statistics of the valid values, by numpy and by the nearest-rank rule, not by the histogram."""
    ordered = numpy.sort(values.astype(numpy.float64))
    count = ordered.size
    expected: dict[str, float] = {
        "minimum": ordered[0],
        "maximum": ordered[-1],
        "mean": ordered.mean(),
        "stddev": ordered.std(),
        "count": count,
        "valid_percent": 100.0 * count / area_pixels,
    }
    for percent in PERCENTILES:
        expected[f"percentile_{percent}"] = ordered[max(1, -(-percent * count // 100)) - 1]
    return expected


class TestTheAnswer:
    def test_it_has_the_form_of_the_bands_of_the_results_document(self, rig: Rig, files: dict[str, Path]) -> None:
        response = rig.get(rig.put(files["counts"], files["inside"]))
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "application/json"
        body = response.json()
        assert set(body) == {"bands"}
        assert [band["name"] for band in body["bands"]] == list(BAND_NAMES)
        assert {band["data_type"] for band in body["bands"]} == {"uint16"}
        assert all(set(band) == {"name", "data_type", "statistics"} for band in body["bands"])
        assert set(body["bands"][0]["statistics"]) == EVERY_KEY

    def test_a_band_without_a_description_is_named_by_its_number(self, rig: Rig, files: dict[str, Path]) -> None:
        bands = rig.get(rig.put(files["unnamed"], files["inside"])).json()["bands"]
        assert [band["name"] for band in bands] == ["1"]

    def test_the_grid_it_was_read_on_is_not_part_of_it(self, rig: Rig, files: dict[str, Path]) -> None:
        text = rig.get(rig.put(files["counts"], files["inside"])).text
        for word in ("factor", "exact", "pixels", "4096"):
            assert word not in text

    def test_the_percentiles_rise_from_the_minimum_to_the_maximum(self, rig: Rig, files: dict[str, Path]) -> None:
        for file in ("counts", "reflectance"):
            statistics = rig.get(rig.put(files[file], files["inside"])).json()["bands"][0]["statistics"]
            ladder = [statistics["minimum"], *(statistics[f"percentile_{p}"] for p in PERCENTILES), statistics["maximum"]]
            assert ladder == sorted(ladder), file


class TestTheNumbers:
    @pytest.mark.parametrize("index", [0, 1])
    def test_integers_are_exact_over_the_pixels_the_mask_marks(
        self, rig: Rig, files: dict[str, Path], counts: numpy.ndarray, index: int
    ) -> None:
        inside = _inside()
        values = counts[index][inside & (counts[index] != 0)]
        got = rig.get(rig.put(files["counts"], files["inside"])).json()["bands"][index]["statistics"]
        expected = _expected(values, int(inside.sum()))
        assert set(got) == set(expected)
        for name, value in expected.items():
            assert got[name] == pytest.approx(value, rel=1e-9), name
        for percent in PERCENTILES:  # a whole number of 16 bits has a bin of its own: the nearest rank, exact
            assert got[f"percentile_{percent}"] == expected[f"percentile_{percent}"], percent

    def test_only_the_marked_pixels_count(self, rig: Rig, files: dict[str, Path], counts: numpy.ndarray) -> None:
        everything = rig.get(rig.put(files["counts"], files["everything"])).json()["bands"][0]["statistics"]
        marked = rig.get(rig.put(files["counts"], files["inside"])).json()["bands"][0]["statistics"]
        assert everything["count"] == int((counts[0] != 0).sum())
        assert marked["count"] == int((_inside() & (counts[0] != 0)).sum()) < everything["count"]
        assert marked["mean"] != everything["mean"]

    def test_floats_agree_with_numpy_within_the_width_of_a_bin(
        self, rig: Rig, files: dict[str, Path]
    ) -> None:
        with rasterio.open(files["reflectance"]) as raster:
            data = raster.read(1)
        inside = _inside()
        values = data[inside & (data != -9999.0)]
        band = rig.get(rig.put(files["reflectance"], files["inside"])).json()["bands"][0]
        assert band["data_type"] == "float32"
        got = band["statistics"]
        expected = _expected(values, int(inside.sum()))
        for name in ("minimum", "maximum", "count", "valid_percent"):
            assert got[name] == pytest.approx(expected[name], rel=1e-6), name
        assert got["mean"] == pytest.approx(expected["mean"], rel=1e-5)
        assert got["stddev"] == pytest.approx(expected["stddev"], rel=1e-4)
        for percent in PERCENTILES:  # 65 536 bins of a relative width of 2^-7
            assert got[f"percentile_{percent}"] == pytest.approx(
                expected[f"percentile_{percent}"], rel=2**-6, abs=1e-6
            ), percent

    def test_nodata_is_not_counted_and_lowers_the_valid_percent(
        self, rig: Rig, files: dict[str, Path], counts: numpy.ndarray
    ) -> None:
        got = rig.get(rig.put(files["counts"], files["inside"])).json()["bands"][1]["statistics"]
        area = int(_inside().sum())
        assert got["count"] == int((_inside() & (counts[1] != 0)).sum())
        assert 70 < got["valid_percent"] < 80 and got["valid_percent"] == pytest.approx(100 * got["count"] / area)

    def test_the_same_answer_every_time(self, rig: Rig, files: dict[str, Path]) -> None:
        first = rig.get(rig.put(files["reflectance"], files["inside"])).text
        assert rig.get(rig.put(files["reflectance"], files["inside"])).text == first


class TestWhereNothingIsCounted:
    def test_a_mask_that_hides_everything_leaves_no_valid_pixel_in_any_band(
        self, rig: Rig, files: dict[str, Path]
    ) -> None:
        bands = rig.get(rig.put(files["counts"], files["nothing"])).json()["bands"]
        assert [band["name"] for band in bands] == list(BAND_NAMES)
        assert all(band["statistics"] == {"count": 0, "valid_percent": 0.0} for band in bands)

    def test_a_band_that_is_all_nodata_is_empty_beside_its_neighbours(self, rig: Rig, files: dict[str, Path]) -> None:
        bands = rig.get(rig.put(files["counts"], files["inside"])).json()["bands"]
        assert bands[2]["statistics"] == {"count": 0, "valid_percent": 0.0}
        assert bands[0]["statistics"]["count"] > 0 and bands[1]["statistics"]["count"] > 0


class TestTheSizeItIsCountedOn:
    def test_a_raster_over_the_limit_is_counted_on_a_coarser_grid(
        self, rig: Rig, files: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        full = rig.get(rig.put(files["reflectance"], files["everything"])).json()["bands"][0]["statistics"]
        monkeypatch.setattr(result_tiles, "STATISTICS_MAX_PIXELS", 40 * 30)  # 4800 of 19 200 pixels: every second one
        coarse = rig.get(rig.put(files["reflectance"], files["everything"]))
        assert coarse.status_code == 200, coarse.text
        got = coarse.json()["bands"][0]["statistics"]
        assert 0 < got["count"] <= 40 * 30 < full["count"]
        assert got["mean"] == pytest.approx(full["mean"], abs=0.05)
        assert got["percentile_50"] == pytest.approx(full["percentile_50"], abs=0.1)
        assert set(got) == set(full)

    def test_strips_of_rows_give_the_numbers_of_one_read(
        self, rig: Rig, files: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        whole = rig.get(rig.put(files["counts"], files["inside"])).json()
        monkeypatch.setattr(result_tiles, "_STRIP_PIXELS", 3 * WIDTH + 1)  # three rows at a time, 40 strips
        strips = rig.get(rig.put(files["counts"], files["inside"])).json()
        for one, other in zip(whole["bands"], strips["bands"], strict=True):
            assert other["statistics"] == pytest.approx(one["statistics"], rel=1e-12)


class TestWhatIsRefused:
    def test_a_result_that_is_not_there_is_a_404(self, rig: Rig) -> None:
        response = rig.get(new_result_id())
        assert response.status_code == 404
        assert response.json() == {"detail": "there is no such result"}
        assert rig.opened == []

    def test_a_result_without_its_mask_is_a_404_and_nothing_is_read(self, rig: Rig, files: dict[str, Path]) -> None:
        response = rig.get(rig.put(files["counts"], None))
        assert response.status_code == 404
        assert rig.opened == []

    @pytest.mark.parametrize(
        "result_id", ["x", "a" * 21, "a" * 23, "a" * 21 + "/", "%2e%2e%2f" + "a" * 12, "ä" * 22, "../" + "a" * 19]
    )
    def test_a_made_up_result_id_is_a_404_before_anything_is_read(self, rig: Rig, result_id: str) -> None:
        assert rig.get(result_id).status_code == 404
        assert rig.heads == [] and rig.opened == []

    def test_a_result_that_is_about_to_expire_is_a_410(self, rig: Rig, files: dict[str, Path]) -> None:
        result_id = rig.put(files["counts"], files["inside"])
        rig.clock.wall = datetime.now(UTC) + RESULT_TTL - MIN_REMAINING - timedelta(seconds=30)
        assert rig.get(result_id).status_code == 200
        rig.clock.wall = datetime.now(UTC) + RESULT_TTL - MIN_REMAINING + timedelta(seconds=30)
        response = rig.get(result_id)
        assert response.status_code == 410
        assert response.json() == {"detail": "the result has expired"}

    def test_a_result_past_its_end_is_gone_even_after_it_was_served(self, rig: Rig, files: dict[str, Path]) -> None:
        result_id = rig.put(files["counts"], files["inside"])
        assert rig.get(result_id).status_code == 200
        rig.clock.wall = datetime.now(UTC) + RESULT_TTL + timedelta(hours=1)
        assert rig.get(result_id).status_code == 410

    @pytest.mark.parametrize("parameter", ["op=band_math", "expression=b1*2", "params=%7B%7D", "algorithm=hillshade"])
    def test_a_free_parameter_is_a_400_as_on_the_tiles(self, rig: Rig, files: dict[str, Path], parameter: str) -> None:
        result_id = rig.put(files["counts"], files["inside"])
        response = rig.get(result_id, f"?{parameter}")
        assert response.status_code == 400
        assert "not accepted" in response.json()["detail"]
        assert rig.opened == []

    def test_a_parameter_nobody_asked_for_does_not_change_the_answer(self, rig: Rig, files: dict[str, Path]) -> None:
        result_id = rig.put(files["counts"], files["inside"])
        assert rig.get(result_id, "?bidx=2&percentiles=5").json() == rig.get(result_id).json()

    @pytest.mark.parametrize("method", ["post", "put", "delete", "patch"])
    def test_it_only_reads(self, rig: Rig, files: dict[str, Path], method: str) -> None:
        result_id = rig.put(files["counts"], files["inside"])
        assert getattr(rig.client, method)(f"/results/{result_id}/statistics").status_code == 405

    def test_a_mask_of_another_grid_is_not_counted_with_the_result(
        self, rig: Rig, files: dict[str, Path], tmp_path: Path
    ) -> None:
        smaller = _mask(tmp_path / "small.tif", numpy.ones((HEIGHT // 2, WIDTH), dtype=bool))
        response = rig.get(rig.put(files["counts"], smaller))
        assert response.status_code == 502
        assert response.json() == {"detail": "the mask does not belong to the result"}

    def test_a_data_type_the_statistics_do_not_know_is_a_422(self, rig: Rig, files: dict[str, Path], tmp_path: Path) -> None:
        wide = _write(tmp_path / "wide.tif", numpy.arange(HEIGHT * WIDTH, dtype="int64").reshape(1, HEIGHT, WIDTH), nodata=None)
        response = rig.get(rig.put(wide, files["everything"]))
        assert response.status_code == 422
        assert "data type" in response.json()["detail"]

    def test_a_tiler_without_the_store_serves_no_results_and_says_so(self, files: dict[str, Path]) -> None:
        @asynccontextmanager
        async def lifespan(app):
            app.state.earthx_results = None
            yield

        with TestClient(build_app(lifespan=lifespan)) as client:
            response = client.get(f"/results/{new_result_id()}/statistics")
        assert response.status_code == 503
        assert response.json() == {"detail": "results are not served by this process"}


class TestCaching:
    def test_a_client_may_keep_it_for_a_few_minutes(self, rig: Rig, files: dict[str, Path]) -> None:
        response = rig.get(rig.put(files["counts"], files["inside"]))
        assert response.headers["cache-control"] == f"private, max-age={int(STATISTICS_MAX_AGE.total_seconds())}"

    def test_never_beyond_the_end_of_the_result(self, rig: Rig, files: dict[str, Path]) -> None:
        result_id = rig.put(files["counts"], files["inside"])
        rig.clock.wall = datetime.now(UTC) + RESULT_TTL - MIN_REMAINING - timedelta(seconds=90)
        age = int(rig.get(result_id).headers["cache-control"].rsplit("=", 1)[1])
        assert 80 <= age <= 90

    def test_the_store_is_asked_as_for_a_tile(self, rig: Rig, files: dict[str, Path]) -> None:
        rig.get(rig.put(files["counts"], files["inside"]))
        assert len(rig.heads) == 2, "one head for the result, one for its mask"


class TestTheLog:
    def test_the_result_id_and_the_numbers_are_not_in_the_log(
        self, rig: Rig, files: dict[str, Path], caplog: pytest.LogCaptureFixture
    ) -> None:
        result_id = rig.put(files["counts"], files["inside"])
        with caplog.at_level(logging.DEBUG):
            assert rig.get(result_id).status_code == 200
        records = [record for record in caplog.records if record.name == "earthx.request"]
        assert len(records) == 1 and records[0].path == "/results/{resultID}/statistics"
        assert result_id not in caplog.text
