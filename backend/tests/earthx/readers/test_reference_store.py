"""One time step of a NetCDF-4 file, read through its chunk references (adr/0029 A2, §8a.1; M5-11 plan §4.3).

The references come from `discovery` (``netcdf_refs``) over the synthetic files of `mini_netcdf.py`; the reader
fetches through its gateway seam from the same fake source. Checked: the values are bitwise those ``h5py`` and GDAL
read from the file, a day costs the chunks it touches, every request carries ``If-Match``, a replaced file ends in
``source_changed``, and nothing the item says is trusted without a check.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy
import pytest
import rasterio
from rasterio.warp import transform_bounds
from rio_tiler.constants import WEB_MERCATOR_TMS, WGS84_CRS

from earthx.discovery.netcdf_refs import reference_file, step_references
from earthx.gateway import Policy
from earthx.readers import AssetRejected, source_failure_kind
from earthx.readers.reference_store import (
    ReferenceMismatch,
    ReferencesInvalid,
    SourceChanged,
    configure_chunk_cache,
    parse_references,
)
from earthx.readers.zarr_reader import InvalidReferences, ZarrReader, reference_asset
from tests.earthx.readers import mini_netcdf
from tests.earthx.readers.mini_netcdf import POLICY, URL, Source, from_memory

ITEM = "synthetic-netcdf-20240104"


@pytest.fixture(autouse=True)
def no_cache() -> Iterator[None]:
    configure_chunk_cache(0)
    yield
    configure_chunk_cache(0)


def made(tmp_path: Path, **options: object) -> tuple[Path, Source, Any]:
    path = mini_netcdf.build(tmp_path / "file.nc", **options)  # type: ignore[arg-type]
    source = Source(path.read_bytes())

    async def run() -> Any:
        async with source.gateway() as gateway:
            return await reference_file(gateway, URL, mini_netcdf.VARIABLE)

    refs = asyncio.run(run())
    source.seen.clear()
    return path, source, refs


def opened(refs: Any, step: int, *, policy: Policy = POLICY, crs: str | None = "EPSG:2056") -> ZarrReader:
    asset = reference_asset(
        URL, step_references(refs, step), policy, dataset_id=mini_netcdf.DATASET, item_id=ITEM, asset="TabsD",
        crs=crs, resolve=from_memory,
    )
    return ZarrReader(asset)


def expected(step: int) -> numpy.ndarray:
    """The day as the file holds it, north up, the fill value as NaN."""
    day = mini_netcdf.values()[step][::-1]
    return numpy.where(day == numpy.float32(mini_netcdf.FILL), numpy.float32("nan"), day)


LAYOUTS = [
    pytest.param({}, id="one-chunk-per-day"),
    pytest.param({"chunks": (4, 12, 20), "shuffle": True, "zlib": True}, id="shuffle-zlib-four-days"),
    pytest.param({"chunks": (2, 24, 37), "zlib": True}, id="zlib-two-days"),
    pytest.param({"chunks": None}, id="contiguous"),
    pytest.param({"south_to_north": False}, id="north-to-south"),
]


class TestValues:
    @pytest.mark.parametrize("options", LAYOUTS)
    @pytest.mark.parametrize("step", [0, 3, 5])
    def test_bitwise_the_day_of_the_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, options: dict[str, object], step: int
    ) -> None:
        _, source, refs = made(tmp_path, **options)
        source.serve_readers(monkeypatch)
        with opened(refs, step) as reader:
            values = reader.input.values
        assert values.dtype == numpy.float32
        assert numpy.array_equal(values, expected(step), equal_nan=True)

    def test_bitwise_what_gdal_reads(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The counter-check of adr/0029 §4: the netCDF driver of GDAL on the file on disk."""
        path, source, refs = made(tmp_path, chunks=(4, 12, 20), shuffle=True, zlib=True)
        source.serve_readers(monkeypatch)
        with rasterio.open(f"netcdf:{path}:{mini_netcdf.VARIABLE}") as gdal:
            band = gdal.read(5, masked=True).filled(numpy.nan)
            transform = gdal.transform
        with opened(refs, 4) as reader:
            assert numpy.array_equal(reader.input.values, band, equal_nan=True)
            assert reader.input.rio.transform() == transform

    def test_placed_north_up_in_lv95(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _, source, refs = made(tmp_path)
        source.serve_readers(monkeypatch)
        with opened(refs, 0) as reader:
            assert reader.input.rio.crs.to_epsg() == 2056
            transform = reader.input.rio.transform()
        assert (transform.a, transform.e) == (1000.0, -1000.0)
        assert (transform.c, transform.f) == (mini_netcdf.WEST, mini_netcdf.SOUTH + 1000.0 * mini_netcdf.ROWS)

    def test_a_tile_and_statistics_through_rio_tiler(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _, source, refs = made(tmp_path)
        source.serve_readers(monkeypatch)
        west, south, east, north = transform_bounds(
            "EPSG:2056", WGS84_CRS, mini_netcdf.WEST, mini_netcdf.SOUTH,
            mini_netcdf.WEST + 37_000, mini_netcdf.SOUTH + 24_000,
        )
        tile = WEB_MERCATOR_TMS.tile((west + east) / 2, (south + north) / 2, 9)
        with opened(refs, 2) as reader:
            image = reader.tile(tile.x, tile.y, tile.z)
            statistics = reader.statistics()
        assert image.count == 1 and not image.array.mask.all()
        day = expected(2)
        (band,) = statistics.values()
        assert band.min == pytest.approx(float(numpy.nanmin(day)))


class TestRequests:
    def test_a_day_is_one_ranged_request_with_if_match(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _, source, refs = made(tmp_path)
        source.serve_readers(monkeypatch)
        with opened(refs, 3) as reader:
            reader.input.values  # noqa: B018 — reading is the point
        (request,) = source.seen
        (_, offset, length), = step_references(refs, 3)["chunk_refs"]
        assert request.headers["range"] == f"bytes={offset}-{offset + length - 1}"
        assert request.headers["if-match"] == source.etag
        assert "if-range" not in request.headers

    def test_only_the_chunks_of_the_days_row(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _, source, refs = made(tmp_path, chunks=(4, 12, 20), shuffle=True, zlib=True)
        source.serve_readers(monkeypatch)
        with opened(refs, 5) as reader:
            reader.input.values  # noqa: B018
        assert len(source.seen) == len(step_references(refs, 5)["chunk_refs"]) == 4

    def test_the_tiler_cache_fetches_a_chunk_once(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _, source, refs = made(tmp_path)
        source.serve_readers(monkeypatch)
        configure_chunk_cache(1024 * 1024)
        for _ in range(3):
            with opened(refs, 1) as reader:
                reader.input.values  # noqa: B018
        assert len(source.seen) == 1

    def test_without_the_cache_every_reader_fetches(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Workers and the runner keep nothing between calls (KLAERUNGEN B9)."""
        _, source, refs = made(tmp_path)
        source.serve_readers(monkeypatch)
        for _ in range(2):
            with opened(refs, 1) as reader:
                reader.input.values  # noqa: B018
        assert len(source.seen) == 2

    def test_opening_reads_no_chunk(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _, source, refs = made(tmp_path)
        source.serve_readers(monkeypatch)
        with opened(refs, 1):
            pass
        assert source.seen == []


class TestFailures:
    def test_a_replaced_file_is_source_changed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _, source, refs = made(tmp_path)
        source.serve_readers(monkeypatch)
        source.replace(mini_netcdf.build(tmp_path / "new.nc", mini_netcdf.values(seed=5)).read_bytes())
        with opened(refs, 0) as reader, pytest.raises(SourceChanged) as caught:
            reader.input.values  # noqa: B018
        assert source_failure_kind(caught.value) == "source_changed"

    def test_a_source_that_ignores_the_range(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _, source, refs = made(tmp_path)
        source.serve_readers(monkeypatch)
        source.ignore_range = True
        with opened(refs, 0) as reader, pytest.raises(ReferenceMismatch, match="status 200"):
            reader.input.values  # noqa: B018

    def test_an_answer_cut_short(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _, source, refs = made(tmp_path)
        source.serve_readers(monkeypatch)
        source.short = True
        with opened(refs, 0) as reader, pytest.raises(ReferenceMismatch):
            reader.input.values  # noqa: B018

    def test_a_host_outside_the_policy_costs_no_request(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _, source, refs = made(tmp_path)
        source.serve_readers(monkeypatch)
        with pytest.raises(AssetRejected):
            opened(refs, 0, policy=Policy(allowed_hosts=frozenset({"other.example.invalid"})))
        assert source.seen == []

    def test_broken_references_are_refused_before_any_request(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _, source, _ = made(tmp_path)
        source.serve_readers(monkeypatch)
        with pytest.raises(InvalidReferences, match="earthx:refs"):
            reference_asset(URL, {"etag": source.etag}, POLICY, dataset_id="d", item_id="i", asset="TabsD", resolve=from_memory)
        assert source.seen == []


def good() -> dict[str, Any]:
    return {
        "etag": '"abc-1"',
        "variable": "TabsD",
        "dtype": "<f4",
        "shape": [24, 37],
        "chunks": [1, 24, 37],
        "time_offset": 0,
        "filters": [],
        "fill_value": -999.99,
        "transform": [1000.0, 0.0, 2600000.0, 0.0, 1000.0, 1150000.0],
        "chunk_refs": [[[0, 0, 0], 4096, 3552]],
    }


class TestParse:
    def test_the_good_form(self) -> None:
        refs = parse_references(good(), URL)
        assert refs.y_ascending and refs.chunk_refs[0].offset == 4096

    @pytest.mark.parametrize(
        ("change", "field"),
        [
            ({"etag": 'W/"abc"'}, "etag"),
            ({"etag": "abc"}, "etag"),
            ({"variable": "a/b"}, "variable"),
            ({"dtype": "float32"}, "dtype"),
            ({"dtype": "<c8"}, "dtype"),
            ({"shape": [24]}, "shape"),
            ({"shape": [0, 37]}, "shape"),
            ({"chunks": [1, 24, True]}, "chunks"),
            ({"time_offset": 1}, "time_offset"),
            ({"filters": ["szip"]}, "filters"),
            ({"filters": ["zlib", "shuffle"]}, "order"),
            ({"fill_value": float("nan")}, "fill_value"),
            ({"fill_value": "x"}, "fill_value"),
            ({"transform": [1000.0, 1.0, 0.0, 0.0, 1000.0, 0.0]}, "north-up"),
            ({"transform": [1000.0, 0.0, 0.0, 0.0, 1000.0]}, "transform"),
            ({"chunk_refs": [[[0, 2, 0], 0, 10]]}, "outside the grid"),
            ({"chunk_refs": [[[1, 0, 0], 0, 10]]}, "outside the grid"),
            ({"chunk_refs": [[[0, 0, 0], -1, 10]]}, "byte range"),
            ({"chunk_refs": [[[0, 0, 0], 0, 9 * 1024 * 1024]]}, "byte range"),
            ({"chunk_refs": [[[0, 0, 0], 0, 10], [[0, 0, 0], 20, 10]]}, "twice"),
            ({"chunk_refs": [[0, 0, 10]]}, "index, offset, length"),
            ({"unknown": 1}, "exactly its fields"),
        ],
    )
    def test_a_broken_field(self, change: dict[str, Any], field: str) -> None:
        with pytest.raises(ReferencesInvalid, match=field):
            parse_references({**good(), **change}, URL)

    def test_not_an_object(self) -> None:
        with pytest.raises(ReferencesInvalid):
            parse_references([1, 2], URL)
