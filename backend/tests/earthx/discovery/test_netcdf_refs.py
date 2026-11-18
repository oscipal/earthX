"""Chunk references made with ``h5py`` through the gateway (adr/0029 A2, M5-11 plan §4.2).

Every file is synthetic (`tests/earthx/readers/mini_netcdf.py`) and served by a fake source behind a real
:class:`~earthx.gateway.Gateway`; nothing reaches a network. The references are checked against what ``h5py`` reads
from the same file on disk, and the layouts the readers would not read faithfully are refused.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import h5py
import numpy
import pytest

from earthx.discovery.netcdf_refs import (
    PAGE_BYTES,
    CrsMismatch,
    FileChanged,
    FileReferences,
    GatewayFile,
    UnsupportedLayout,
    reference_file,
    step_references,
)
from earthx.gateway import UpstreamTimeout, UrlRejected
from earthx.readers.reference_store import parse_references
from tests.earthx.readers import mini_netcdf
from tests.earthx.readers.mini_netcdf import URL, VARIABLE, Source


def references(source: Source, url: str = URL, variable: str = VARIABLE) -> FileReferences:
    async def run() -> FileReferences:
        async with source.gateway() as gateway:
            return await reference_file(gateway, url, variable)

    return asyncio.run(run())


def built(tmp_path: Path, **options: object) -> tuple[Path, Source]:
    path = mini_netcdf.build(tmp_path / "file.nc", **options)  # type: ignore[arg-type]
    return path, Source(path.read_bytes())


def chunks_on_disk(path: Path) -> dict[tuple[int, int, int], tuple[int, int]]:
    with h5py.File(path, "r") as hdf:
        array = hdf[VARIABLE]
        found = {}
        for number in range(array.id.get_num_chunks()):
            info = array.id.get_chunk_info(number)
            key = tuple(p // c for p, c in zip(info.chunk_offset, array.chunks, strict=True))
            found[key] = (info.byte_offset, info.size)
        return found


class TestReferences:
    def test_one_chunk_per_day_as_h5py_reads_it_from_disk(self, tmp_path: Path) -> None:
        path, source = built(tmp_path)
        refs = references(source)
        assert dict(refs.layout.chunk_index) == chunks_on_disk(path)
        assert refs.layout.chunks == (1, mini_netcdf.ROWS, mini_netcdf.COLUMNS)
        assert refs.layout.filters == ()
        assert refs.layout.dtype == "<f4"
        assert refs.layout.fill_value == pytest.approx(mini_netcdf.FILL)
        assert refs.layout.crs == "EPSG:2056"
        assert refs.etag == source.etag and refs.size == len(source.body)

    def test_the_header_costs_a_few_page_requests_and_no_data(self, tmp_path: Path) -> None:
        _, source = built(tmp_path)
        references(source)
        assert 1 <= len(source.seen) <= 8
        assert all(request.headers["range"].startswith("bytes=") for request in source.seen)
        # The first page learns the ETag; every later one is sent with it.
        assert "if-match" not in source.seen[0].headers
        assert all(request.headers["if-match"] == source.etag for request in source.seen[1:])

    def test_the_grid_is_placed_from_the_cell_centres(self, tmp_path: Path) -> None:
        _, source = built(tmp_path)
        a, b, c, d, e, f = references(source).layout.transform
        assert (a, b, d, e) == (1000.0, 0.0, 0.0, 1000.0)  # rows south to north: e > 0
        assert (c, f) == (mini_netcdf.WEST, mini_netcdf.SOUTH)

    def test_rows_stored_north_to_south_give_a_negative_step(self, tmp_path: Path) -> None:
        _, source = built(tmp_path, south_to_north=False)
        assert references(source).layout.transform[4] == -1000.0

    def test_the_days_of_the_time_axis(self, tmp_path: Path) -> None:
        _, source = built(tmp_path)
        refs = references(source)
        assert refs.times[0] == datetime(2024, 1, 1, tzinfo=UTC)
        assert refs.times[-1] == datetime(2024, 1, mini_netcdf.STEPS, tzinfo=UTC)
        assert refs.time_bounds is None

    def test_time_bounds_where_the_file_names_them(self, tmp_path: Path) -> None:
        _, source = built(tmp_path, bounds=True)
        start, end = references(source).time_bounds[1]  # type: ignore[index]
        assert (start, end) == (datetime(2024, 1, 2, 6, tzinfo=UTC), datetime(2024, 1, 3, 6, tzinfo=UTC))

    def test_shuffle_and_zlib_over_several_days(self, tmp_path: Path) -> None:
        path, source = built(tmp_path, chunks=(4, 12, 20), shuffle=True, zlib=True)
        refs = references(source)
        assert refs.layout.filters == ("shuffle", "zlib")
        assert dict(refs.layout.chunk_index) == chunks_on_disk(path)
        step = step_references(refs, 5)
        assert (step["time_offset"], step["chunks"]) == (1, [4, 12, 20])
        # The second row of chunks (days 4 and 5), every chunk of it and none of the first row.
        expected = {(0, i[1], i[2]): v for i, v in chunks_on_disk(path).items() if i[0] == 1}
        assert {tuple(index): (offset, length) for index, offset, length in step["chunk_refs"]} == expected

    def test_missing_days_are_missing_time_steps_not_a_failure(self, tmp_path: Path) -> None:
        """Fourth run (18.11.2026): one year of SrelD has gaps. A day the file does not carry is no time step."""
        days = [0.0, 1.0, 2.0, 5.0, 6.0, 9.0]
        _, source = built(tmp_path, time_values=numpy.array(days))
        refs = references(source)
        assert [time.day for time in refs.times] == [1, 2, 3, 6, 7, 10]
        assert len(refs.times) == refs.layout.shape[0]
        assert all(step_references(refs, step)["chunk_refs"] for step in range(len(days)))

    def test_a_contiguous_array_is_one_chunk(self, tmp_path: Path) -> None:
        _, source = built(tmp_path, chunks=None)
        refs = references(source)
        assert refs.layout.chunks == refs.layout.shape
        assert list(refs.layout.chunk_index) == [(0, 0, 0)]

    def test_each_steps_references_are_what_the_readers_accept(self, tmp_path: Path) -> None:
        _, source = built(tmp_path, chunks=(2, 12, 20), shuffle=True, zlib=True)
        refs = references(source)
        for step in range(mini_netcdf.STEPS):
            parsed = parse_references(step_references(refs, step), URL)
            assert parsed.time_offset == step % 2
            assert parsed.etag == source.etag

    def test_without_a_name_the_one_array_over_time_is_taken(self, tmp_path: Path) -> None:
        _, source = built(tmp_path)
        layout = references(source, variable=None).layout  # type: ignore[arg-type]
        assert (layout.variable, layout.units) == (VARIABLE, "degC")

    def test_a_step_outside_the_file(self, tmp_path: Path) -> None:
        _, source = built(tmp_path)
        with pytest.raises(IndexError):
            step_references(references(source), mini_netcdf.STEPS)


class TestRefused:
    @pytest.mark.parametrize(
        ("options", "reason"),
        [
            ({"fletcher32": True}, "filter"),
            ({"extra_attributes": {"scale_factor": 0.1}}, "scale_factor"),
            ({"even": False}, "evenly spaced"),
            ({"calendar": "360_day"}, "calendar"),
            ({"time_units": "months since 2024-01-01"}, "days, hours"),
            ({"grid_mapping": {**mini_netcdf.LV95, "false_easting": 600000.0}}, "EPSG"),
            ({"grid_mapping": {"grid_mapping_name": "no_such_projection"}}, "coordinate reference system|EPSG"),
            ({"extra_attributes": {"_FillValue": 1e40}}, "_FillValue"),
        ],
    )
    def test_a_layout_the_readers_would_not_read_faithfully(
        self, tmp_path: Path, options: dict[str, object], reason: str
    ) -> None:
        _, source = built(tmp_path, **options)
        with pytest.raises(UnsupportedLayout, match=reason):
            references(source)

    @pytest.mark.parametrize("attribute", ["crs_wkt", "spatial_ref"])
    def test_lv95_written_as_esri_wkt_is_epsg_2056(self, tmp_path: Path, attribute: str) -> None:
        """Fourth run (18.11.2026): the grid_mapping carries an ESRI WKT, from which pyproj names the unit "Degree"
        where EPSG:2056 says "degree". Compared with their case, all 295 files were refused (third run)."""
        from pyproj import CRS

        mapping = {**mini_netcdf.LV95, attribute: CRS.from_epsg(2056).to_wkt("WKT1_ESRI")}
        _, source = built(tmp_path, grid_mapping=mapping)
        assert references(source).layout.crs == "EPSG:2056"

    def test_a_mismatching_grid_mapping_carries_its_attributes(self, tmp_path: Path) -> None:
        _, source = built(tmp_path, grid_mapping={**mini_netcdf.LV95, "false_easting": 600000.0})
        with pytest.raises(CrsMismatch) as caught:
            references(source)
        assert caught.value.attributes["false_easting"] == 600000.0
        assert caught.value.attributes["grid_mapping_name"] == "oblique_mercator"

    def test_a_measurement_may_read_past_a_mismatching_grid_mapping(self, tmp_path: Path) -> None:
        """Only for the probe: the layout without a CRS, the attributes kept; the platform stays strict by default."""
        _, source = built(tmp_path, grid_mapping={**mini_netcdf.LV95, "false_easting": 600000.0})

        async def run() -> FileReferences:
            async with source.gateway() as gateway:
                return await reference_file(gateway, URL, VARIABLE, strict_crs=False)

        layout = asyncio.run(run()).layout
        assert layout.crs is None
        assert layout.grid_mapping["false_easting"] == 600000.0
        assert layout.dtype == "<f4"

    def test_unwritten_chunks_without_a_fill_value(self, tmp_path: Path) -> None:
        path = mini_netcdf.build(tmp_path / "file.nc")
        with h5py.File(path, "a") as hdf:
            sparse = hdf.create_dataset(
                "TmaxD", shape=(mini_netcdf.STEPS, mini_netcdf.ROWS, mini_netcdf.COLUMNS), dtype="<f4",
                chunks=(1, mini_netcdf.ROWS, mini_netcdf.COLUMNS),
            )
            sparse[0] = mini_netcdf.values()[0]
            sparse.attrs["grid_mapping"] = "swiss_lv95_coordinates"
            for dimension, name in enumerate(("time", "N", "E")):
                sparse.dims[dimension].attach_scale(hdf[name])
        with pytest.raises(UnsupportedLayout, match="never written"):
            references(Source(path.read_bytes()), variable="TmaxD")

    def test_an_array_named_like_an_axis_of_the_readers(self, tmp_path: Path) -> None:
        path = mini_netcdf.build(tmp_path / "file.nc")
        with h5py.File(path, "a") as hdf:
            hdf["x"] = hdf[VARIABLE]
        with pytest.raises(UnsupportedLayout, match="like an axis"):
            references(Source(path.read_bytes()), variable="x")

    def test_an_etag_the_readers_would_refuse(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _, source = built(tmp_path)
        monkeypatch.setattr(Source, "etag", property(lambda self: '""'))
        with pytest.raises(UnsupportedLayout, match="strong ETag"):
            references(source)

    def test_a_page_that_does_not_arrive_in_time(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import time

        from earthx.discovery import netcdf_refs

        _, source = built(tmp_path)
        monkeypatch.setattr(netcdf_refs, "_PAGE_TIMEOUT_S", 0.05)
        handler = source.handler

        def slow(request):  # type: ignore[no-untyped-def]
            time.sleep(0.3)
            return handler(request)

        source.handler = slow  # type: ignore[method-assign]
        with pytest.raises(UpstreamTimeout):
            references(source)

    def test_a_file_object_is_never_read_on_its_own_loop(self) -> None:
        source = Source(bytes(1000))

        async def run() -> None:
            async with source.gateway() as gateway:
                GatewayFile(gateway, URL, asyncio.get_running_loop())

        with pytest.raises(RuntimeError, match="thread of its own"):
            asyncio.run(run())

    def test_an_array_the_file_does_not_carry(self, tmp_path: Path) -> None:
        _, source = built(tmp_path)
        with pytest.raises(UnsupportedLayout, match="no array"):
            references(source, variable="RhiresD")

    def test_without_a_name_two_arrays_over_time_are_ambiguous(self, tmp_path: Path) -> None:
        path = mini_netcdf.build(tmp_path / "file.nc")
        with h5py.File(path, "a") as hdf:
            second = hdf.create_dataset("TminD", data=mini_netcdf.values())
            for dimension, name in enumerate(("time", "N", "E")):
                second.dims[dimension].attach_scale(hdf[name])
        with pytest.raises(UnsupportedLayout, match="not exactly one"):
            references(Source(path.read_bytes()), variable=None)  # type: ignore[arg-type]

    def test_a_file_that_is_no_hdf5(self) -> None:
        with pytest.raises(UnsupportedLayout, match="no HDF5"):
            references(Source(b"CDF\x01" + bytes(4000)))

    def test_a_source_that_ignores_the_range(self, tmp_path: Path) -> None:
        _, source = built(tmp_path)
        source.ignore_range = True
        with pytest.raises(UnsupportedLayout, match="200, not 206"):
            references(source)

    def test_a_source_without_a_strong_etag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _, source = built(tmp_path)
        monkeypatch.setattr(Source, "etag", property(lambda self: 'W/"weak"'))
        with pytest.raises(UnsupportedLayout, match="strong ETag"):
            references(source)

    def test_a_file_replaced_while_it_is_read(self) -> None:
        """Every page after the first is sent with ``If-Match``: a replaced file never mixes two versions."""
        source = Source(bytes(range(256)) * 1024)  # four pages

        async def run() -> None:
            async with source.gateway() as gateway:
                loop = asyncio.get_running_loop()
                file = await asyncio.to_thread(GatewayFile, gateway, URL, loop)
                source.replace(bytes(len(source.body)))
                await asyncio.to_thread(file.seek, 3 * PAGE_BYTES)
                await asyncio.to_thread(file.read, 10)

        with pytest.raises(FileChanged):
            asyncio.run(run())

    def test_an_address_outside_the_policy_costs_no_request(self, tmp_path: Path) -> None:
        _, source = built(tmp_path)
        with pytest.raises(UrlRejected):
            references(source, url="https://elsewhere.example.invalid/file.nc")
        assert source.seen == []


def test_the_reference_values_match_the_file(tmp_path: Path) -> None:
    """The bytes the references name decode to the day ``h5py`` reads from disk."""
    path, source = built(tmp_path, chunks=(3, 24, 37), shuffle=True, zlib=True)
    refs = step_references(references(source), 4)
    (_, offset, length), = refs["chunk_refs"]
    raw = path.read_bytes()[offset : offset + length]
    import zlib

    unshuffled = numpy.frombuffer(zlib.decompress(raw), dtype="u1").reshape(4, -1).T.ravel()
    day = numpy.frombuffer(unshuffled.tobytes(), dtype="<f4").reshape(3, 24, 37)[refs["time_offset"]]
    assert numpy.array_equal(day, mini_netcdf.values()[4])
