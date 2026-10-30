"""The statistics a run writes (M4-32): GDAL tags over the whole ``result.tif``, ``statistics`` over the mask.

Checked against an independent computation on the files the run left: ``result.tif`` and
``mask.tif`` read back with rasterio, the exact mean from ``Fraction``, the percentiles from
``numpy.percentile(method="inverted_cdf")`` (plan M4-32 §6.10, §7).
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import numpy
import pytest
import rasterio
from rasterio.warp import transform_geom

from earthx.processing import run
from earthx.processing.statistics import gdal_tags
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import recipe_of_data, resolved
from tests.earthx.processing.testops import OPERATORS

SIZE = 700
SCALE_2 = {"op": "scale", "op_version": 1, "params": {"factor": 2.0}}
#: Raw value of the two corners of the AOI's box that lie outside the triangle.
CORNER = 55000
BIN = 2.0**-7


def _recipe(aoi: dict, *, dtype: str = "float32", step: dict = SCALE_2, **entry_options) -> dict:
    return {
        "recipe_version": 1,
        "inputs": [
            {
                "name": "s2",
                "dataset": "synthetic",
                "groups": [["ITEM_A"]],
                "assets": ["band"],
                "resolved": [resolved("ITEM_A", "band", href=sources.url("band"), **entry_options)],
            }
        ],
        "aoi": aoi,
        "steps": [step],
        "output": {"kind": "raster", "format": "cog", "dtype": dtype},
    }


def _run(data: dict, workdir: Path):
    workdir.mkdir(exist_ok=True)
    return run(recipe_of_data(data, OPERATORS), workdir=workdir, progress=lambda done, total: None, operators=OPERATORS)


def _triangle() -> dict:
    """The AOI of ``test_core_run``: a triangle whose box is raster rows and columns 100–600."""
    left, top = sources.ORIGIN_X + 1000.0, sources.ORIGIN_Y - 1000.0
    ring = [[left + 5, top - 4995], [left + 4995, top - 4995], [left + 2500, top - 5], [left + 5, top - 4995]]
    return transform_geom(sources.CRS, "EPSG:4326", {"type": "Polygon", "coordinates": [ring]})


@pytest.fixture
def band(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> numpy.ndarray:
    """A ramp of small values, with high ones in the two upper corners of the triangle's box."""
    raw = sources.ramp(SIZE, SIZE, 1200) % 4000 + 1
    raw[100:200, 100:150] = CORNER
    raw[100:200, 550:600] = CORNER
    path = sources.build_band_cog(tmp_path / "band.tif", raw)
    sources.serve({sources.url("band"): path}, monkeypatch)
    return raw


def _files(result) -> tuple[numpy.ma.MaskedArray, numpy.ndarray, dict[str, str]]:
    with rasterio.open(result.path) as dataset:
        data, tags = dataset.read(1, masked=True), dataset.tags(1)
    with rasterio.open(result.mask_path) as dataset:
        inside = dataset.read(1) == 1
    return data, inside, tags


def _exact_mean(values: numpy.ndarray) -> float:
    return float(sum(map(Fraction, values.astype(numpy.float64).tolist())) / values.size)


def _assert_matches(summary: dict, values: numpy.ndarray, pixels: int, *, exact: bool) -> None:
    assert summary["count"] == values.size
    assert summary["valid_percent"] == 100.0 * values.size / pixels
    assert (summary["minimum"], summary["maximum"]) == (values.min(), values.max())
    assert summary["mean"] == _exact_mean(values)
    assert summary["stddev"] == pytest.approx(float(values.astype(numpy.float64).std()), rel=1e-9)
    for percent, outward in ((2, -1), (98, 1)):
        true = float(numpy.percentile(values.astype(numpy.float64), percent, method="inverted_cdf"))
        reported = summary[f"percentile_{percent}"]
        if exact:
            assert reported == true
        else:
            assert 0 <= (reported - true) * outward <= abs(true) * BIN


@pytest.mark.usefixtures("band")
class TestAnAreaWhoseBoxHoldsOtherValues:
    def test_the_tags_describe_the_whole_file(self, tmp_path: Path) -> None:
        result = _run(_recipe(_triangle()), tmp_path / "work")
        data, _, tags = _files(result)
        whole = {name: float(tags[tag]) for name, tag in _TAG_NAMES.items()}
        _assert_matches(whole | {"count": data.count()}, data.compressed(), data.size, exact=False)

    def test_the_properties_describe_the_area_only(self, tmp_path: Path) -> None:
        result = _run(_recipe(_triangle()), tmp_path / "work")
        data, inside, tags = _files(result)
        assert 0 < inside.sum() < inside.size
        area = result.properties["bands"][0]["statistics"]
        _assert_matches(area, data[inside].compressed(), int(inside.sum()), exact=False)
        corner = (CORNER * sources.SCALE + sources.OFFSET) * 2.0
        assert float(tags["STATISTICS_MAXIMUM"]) == pytest.approx(corner, rel=1e-6)
        assert area["maximum"] < corner / 5
        assert area["percentile_98"] < float(tags["EARTHX_PERCENTILE_98"])

    def test_gdal_reads_the_stored_values(self, tmp_path: Path) -> None:
        result = _run(_recipe(_triangle()), tmp_path / "work")
        _, _, tags = _files(result)
        with rasterio.open(result.path) as dataset:
            (stored,) = dataset.stats(indexes=[1])  # GDALGetRasterStatistics: the tags, if all four are there
        assert (stored.min, stored.max, stored.mean, stored.std) == tuple(
            float(tags[f"STATISTICS_{name}"]) for name in ("MINIMUM", "MAXIMUM", "MEAN", "STDDEV")
        )

    def test_computed_twice_the_same_bytes(self, tmp_path: Path) -> None:
        first = _run(_recipe(_triangle()), tmp_path / "one")
        second = _run(_recipe(_triangle()), tmp_path / "two")
        assert first.path.read_bytes() == second.path.read_bytes()
        assert first.properties == second.properties


_TAG_NAMES = {
    "minimum": "STATISTICS_MINIMUM",
    "maximum": "STATISTICS_MAXIMUM",
    "mean": "STATISTICS_MEAN",
    "stddev": "STATISTICS_STDDEV",
    "valid_percent": "STATISTICS_VALID_PERCENT",
    "percentile_2": "EARTHX_PERCENTILE_2",
    "percentile_98": "EARTHX_PERCENTILE_98",
}


def test_for_a_whole_scene_file_and_area_agree(tmp_path: Path, band: numpy.ndarray) -> None:
    result = _run(_recipe(sources.whole(SIZE, SIZE)), tmp_path / "work")
    data, inside, tags = _files(result)
    assert inside.all()
    area = result.properties["bands"][0]["statistics"]
    assert gdal_tags(area) == tags
    assert area["maximum"] == pytest.approx((CORNER * sources.SCALE + sources.OFFSET) * 2.0, rel=1e-6)


def test_an_integer_output_with_nodata_has_exact_percentiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = sources.ramp(300, 300, 100)
    bare = sources.build_band_cog(tmp_path / "bare.tif", raw, scale=None, offset=None)
    sources.serve({sources.url("band"): bare}, monkeypatch)
    result = _run(_recipe(sources.whole(300, 300), dtype="uint16", scale=None, offset=None), tmp_path / "work")
    data, _, tags = _files(result)
    area = result.properties["bands"][0]["statistics"]
    assert data.count() == raw.size - 64  # the nodata corner of `ramp`
    _assert_matches(area, data.compressed(), data.size, exact=True)
    assert isinstance(area["percentile_2"], int)
    assert tags["STATISTICS_MINIMUM"] == repr(area["minimum"])


def test_a_value_rounded_onto_nodata_is_not_counted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``uint16`` with nodata 0: a scaled value below 0.5 is written as 0 and reads back as nodata (review M4-32a)."""
    raw = sources.ramp(300, 300, 100)
    bare = sources.build_band_cog(tmp_path / "bare.tif", raw, scale=None, offset=None)
    sources.serve({sources.url("band"): bare}, monkeypatch)
    shrink = {"op": "scale", "op_version": 1, "params": {"factor": 0.001}}
    data = _recipe(sources.whole(300, 300), dtype="uint16", step=shrink, scale=None, offset=None)
    result = _run(data, tmp_path / "work")
    written, _, tags = _files(result)
    assert 0 < written.count() < raw.size - 64 - 1000  # many valid inputs became nodata on the way out
    area = result.properties["bands"][0]["statistics"]
    _assert_matches(area, written.compressed(), written.size, exact=True)
    assert area["minimum"] >= 1 and float(tags["STATISTICS_MINIMUM"]) >= 1
    assert tags == gdal_tags(area)


@pytest.mark.parametrize(
    "raw",
    [
        numpy.full((300, 300), 3000, dtype="uint16"),
        numpy.where(numpy.indices((300, 300)).sum(axis=0) % 2 == 0, 3000, 3001).astype("uint16"),
    ],
    ids=["one value", "two values one step apart"],
)
def test_a_flat_raster_has_statistics_and_a_run_that_does_not_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw: numpy.ndarray
) -> None:
    """The histogram of the pass has a fixed bin per value, so values that are (nearly) one number need no special case."""
    path = sources.build_band_cog(tmp_path / "flat.tif", raw)
    sources.serve({sources.url("band"): path}, monkeypatch)
    result = _run(_recipe(sources.whole(300, 300)), tmp_path / "work")
    data, _, tags = _files(result)
    area = result.properties["bands"][0]["statistics"]
    _assert_matches(area, data.compressed(), data.size, exact=False)
    assert area["minimum"] <= area["percentile_2"] <= area["percentile_98"] <= area["maximum"]
    assert tags == gdal_tags(area)
