"""The format of a file from its first 16 KB, without GDAL (M5-20 plan §14.1.3): synthetic files only."""

from __future__ import annotations

import struct

import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from earthx.discovery.probe import HEAD_BYTES, sniff


def _raster(driver: str = "GTiff", **options: object) -> bytes:
    profile = {
        "driver": driver,
        "width": 1024,
        "height": 512,
        "count": 1,
        "dtype": "int16",
        "crs": "EPSG:2056",
        "transform": from_origin(2_600_000, 1_200_000, 1, 1),
    }
    profile.update(options)
    with MemoryFile() as memory:
        with memory.open(**profile) as dataset:
            dataset.write(np.zeros((profile["count"], profile["height"], profile["width"]), dtype=profile["dtype"]))
        return memory.read()


def _tiff(entries: list[tuple[int, int, int, int]], *, following: int = 0, order: str = "<") -> bytes:
    """A classic TIFF with one directory at offset 8 of ``(tag, type, count, inline value)`` entries."""
    magic = b"II*\x00" if order == "<" else b"MM\x00*"
    body = struct.pack(f"{order}H", len(entries))
    for tag, field_type, count, value in entries:
        body += struct.pack(f"{order}HHII", tag, field_type, count, value)
    return magic + struct.pack(f"{order}I", 8) + body + struct.pack(f"{order}I", following)


class TestTiff:
    def test_a_cog_with_all_it_names(self) -> None:
        found = sniff(_raster("COG", count=2, nodata=-9999, blocksize=256)[:HEAD_BYTES])
        assert found.format == "cog" and found.readable
        header = found.tiff
        assert header is not None
        assert (header.width, header.height, header.bands, header.data_type) == (1024, 512, 2, "int16")
        assert (header.tiled, header.tile_size, header.epsg, header.nodata) == (True, (256, 256), 2056, "-9999")
        assert header.overviews == 2

    def test_a_striped_geotiff_is_readable_but_no_cog(self) -> None:
        found = sniff(_raster(dtype="float32", crs="EPSG:4326", transform=from_origin(7, 47, 0.01, 0.01))[:HEAD_BYTES])
        assert found.format == "geotiff" and found.readable
        assert found.tiff is not None
        assert (found.tiff.tiled, found.tiff.data_type, found.tiff.epsg, found.tiff.overviews) == (False, "float32", 4326, 0)

    def test_a_big_tiff(self) -> None:
        found = sniff(_raster(BIGTIFF="YES", tiled=True, blockxsize=128, blockysize=128, dtype="uint8")[:HEAD_BYTES])
        assert found.big_tiff and found.format == "geotiff"
        assert found.tiff is not None and found.tiff.tile_size == (128, 128)

    def test_big_endian(self) -> None:
        found = sniff(_tiff([(256, 3, 1, 70 << 16), (257, 3, 1, 30 << 16), (258, 3, 1, 8 << 16)], order=">"))
        assert found.tiff is not None and (found.tiff.width, found.tiff.height, found.tiff.data_type) == (70, 30, "uint8")

    def test_a_tiff_without_geo_keys_is_no_geodata(self) -> None:
        found = sniff(_tiff([(256, 3, 1, 70), (257, 3, 1, 30), (258, 3, 1, 16), (339, 3, 1, 2)]))
        assert found.format == "tiff" and not found.readable
        assert found.tiff is not None and found.tiff.data_type == "int16"

    def test_the_layout_note_alone_makes_no_cog(self) -> None:
        # A striped file with the note copied in front: the note is no proof of tiles.
        data = _raster()
        noted = data[:8] + b"LAYOUT=IFDS_BEFORE_DATA\n" + data[8 + 24 :]
        assert sniff(noted[:HEAD_BYTES]).format != "cog"

    def test_what_lies_beyond_the_bytes_is_unknown(self) -> None:
        # The directory points past the 16 KB (libtiff writes it at the end): no COG, and "no geodata" is not said.
        data = b"II*\x00" + struct.pack("<I", 100_000) + b"\x00" * 100
        found = sniff(data)
        assert found.format == "tiff_unread" and not found.readable
        assert found.tiff is not None and found.tiff.width is None and found.tiff.overviews is None

    def test_a_cut_directory(self) -> None:
        whole = _tiff([(256, 3, 1, 70), (257, 3, 1, 30)])
        assert sniff(whole[:20]).tiff is not None and sniff(whole[:20]).tiff.width is None  # type: ignore[union-attr]

    def test_a_loop_of_directories_stops(self) -> None:
        # The next directory is the first again: no endless chain, the overviews are unknown.
        found = sniff(_tiff([(256, 3, 1, 70)], following=8))
        assert found.tiff is not None and found.tiff.overviews is None

    def test_a_crafted_count_is_not_read(self) -> None:
        data = b"II*\x00" + struct.pack("<I", 8) + struct.pack("<H", 60_000) + b"\x00" * 64
        assert sniff(data).tiff is not None and sniff(data).tiff.width is None  # type: ignore[union-attr]

    def test_a_value_list_pointing_past_the_end(self) -> None:
        # BitsPerSample with three values lies at an offset beyond the bytes: no data type.
        found = sniff(_tiff([(256, 3, 1, 70), (258, 3, 3, 1_000_000)]))
        assert found.tiff is not None and found.tiff.data_type is None and found.tiff.width == 70

    def test_geo_keys_whose_values_lie_beyond_the_bytes_still_make_a_geotiff(self) -> None:
        # A large tile index before the GeoKeys (review): the directory names them, their values are unknown.
        found = sniff(_tiff([(256, 3, 1, 70), (258, 3, 1, 8), (34735, 3, 32, 1_000_000)]))
        assert found.format == "geotiff" and found.tiff is not None and found.tiff.epsg is None

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 2.5, 1e300])
    def test_a_float_tag_that_is_no_whole_number(self, value: float) -> None:
        # Review: BitsPerSample, Width or GeoKeys as type 12 with NaN or infinity broke the whole step.
        double = struct.pack("<d", value)
        data = b"II*\x00" + struct.pack("<I", 8) + struct.pack("<H", 3)
        data += struct.pack("<HHII", 256, 12, 1, 50) + struct.pack("<HHII", 258, 12, 1, 58)
        data += struct.pack("<HHII", 34735, 12, 4, 58) + struct.pack("<I", 0) + double * 4
        found = sniff(data)
        assert found.tiff is not None and found.tiff.width is None and found.tiff.data_type is None
        assert found.tiff.epsg is None

    def test_a_mask_is_no_overview(self) -> None:
        # Two further directories: a mask (NewSubfileType 4) and an overview (1).
        first = _tiff([(256, 3, 1, 70), (34735, 3, 4, 0)], following=38)
        mask = struct.pack("<H", 1) + struct.pack("<HHII", 254, 4, 1, 4) + struct.pack("<I", 56)
        overview = struct.pack("<H", 1) + struct.pack("<HHII", 254, 4, 1, 1) + struct.pack("<I", 0)
        found = sniff(first + mask + overview)
        assert found.tiff is not None and found.tiff.overviews == 1

    def test_user_defined_crs_has_no_epsg(self) -> None:
        found = sniff(_raster(crs="+proj=tmerc +lat_0=0 +lon_0=9 +k=1 +x_0=0 +y_0=0 +ellps=bessel +units=m")[:HEAD_BYTES])
        assert found.format == "geotiff" and found.tiff is not None and found.tiff.epsg is None


class TestOtherFormats:
    @pytest.mark.parametrize("magic", [b"CDF\x01", b"CDF\x02", b"CDF\x05"])
    def test_netcdf_classic(self, magic: bytes) -> None:
        assert sniff(magic + b"\x00" * 60).format == "netcdf"

    @pytest.mark.parametrize("offset", [0, 512, 1024])
    def test_hdf5(self, offset: int) -> None:
        assert sniff(b"\x00" * offset + b"\x89HDF\r\n\x1a\n" + b"\x00" * 64).format == "hdf5"

    def test_hdf4_is_no_readable_format(self) -> None:
        found = sniff(b"\x0e\x03\x13\x01" + b"\x00" * 60)
        assert found.format == "hdf4" and not found.readable

    @pytest.mark.parametrize("url", ["https://d.example.org/a.zarr/zarr.json", "https://d.example.org/a.zarr/.zgroup"])
    def test_zarr_by_its_metadata(self, url: str) -> None:
        assert sniff(b'{"zarr_format": 3}', url).format == "zarr"

    def test_json_elsewhere_is_no_zarr(self) -> None:
        assert sniff(b'{"zarr_format": 3}', "https://d.example.org/meta.json").format == "unknown"


class TestMisuse:
    @pytest.mark.parametrize("data", [b"", b"\x00", b"II", b"II*\x00", b"MM\x00+\x00\x08"])
    def test_too_few_bytes(self, data: bytes) -> None:
        assert not sniff(data).readable

    def test_an_error_page_with_200(self) -> None:
        found = sniff(b"<!DOCTYPE html><html><title>Login</title></html>")
        assert found.format == "html" and not found.readable

    def test_random_bytes(self) -> None:
        assert sniff(bytes(range(256)) * 64).format == "unknown"

    def test_the_document_names_no_more_than_the_header(self) -> None:
        document = sniff(_raster("COG", blocksize=256)[:HEAD_BYTES]).to_document()
        assert document["format"] == "cog" and document["tiff"]["tile_size"] == [256, 256]
        assert set(document) == {"format", "tiff"}
