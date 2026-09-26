"""The read-back check every generated download file passes before delivery (M3-22, F1).

The files come from the real writers (`_masked_array_to_cog_bytes`,
`_write_mask_tif_bytes`) on a small synthetic array; the defects are made by
hand, one per test: truncated, a flipped tile, empty, not a TIFF at all, a
mask on the wrong grid or with values other than 0/1.
"""

from __future__ import annotations

import logging
import zipfile
from io import BytesIO

import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from earthx.access import download as dl

CRS = "EPSG:32632"
TRANSFORM = from_origin(600000, 5700000, 10, 10)
# Bigger than one 512 px COG block, so the data file gets an overview level.
SIZE = 700


def _valid_crop(size: int = SIZE) -> dl.AssetCropBytes:
    rng = np.random.default_rng(0)
    data = rng.integers(1, 255, (3, size, size), dtype="uint8")
    array = np.ma.MaskedArray(data, mask=np.zeros_like(data, dtype=bool))
    inside = np.zeros((size, size), dtype="uint8")
    inside[size // 4 : 3 * size // 4, size // 4 : 3 * size // 4] = 1
    return dl.AssetCropBytes(
        data=dl._masked_array_to_cog_bytes(array, TRANSFORM, CRS, 0),
        mask=dl._write_mask_tif_bytes(inside, transform=TRANSFORM, crs=CRS),
    )


@pytest.fixture(scope="module")
def valid_crop() -> dl.AssetCropBytes:
    return _valid_crop()


def _flip_tile_bytes(data: bytes) -> bytes:
    """Invert a run of bytes inside the first full-resolution tile, header untouched."""
    with MemoryFile(data) as mem, mem.open() as dataset:
        offset = int(dataset.get_tag_item("BLOCK_OFFSET_0_0", "TIFF", bidx=1))
    corrupted = bytearray(data)
    for index in range(offset + 16, offset + 80):
        corrupted[index] ^= 0xFF
    return bytes(corrupted)


def _mask_bytes(inside: np.ndarray, *, transform=TRANSFORM, count: int = 1) -> bytes:
    height, width = inside.shape
    profile = {
        "driver": "GTiff", "dtype": "uint8", "count": count, "height": height, "width": width,
        "crs": CRS, "transform": transform,
    }
    with MemoryFile() as mem:
        with mem.open(**profile) as dst:
            for band in range(1, count + 1):
                dst.write(inside, band)
        return mem.read()


class TestTheCheckAcceptsAGoodFile:
    def test_a_freshly_written_crop_passes(self, valid_crop: dl.AssetCropBytes) -> None:
        with MemoryFile(valid_crop.data) as mem, mem.open() as dataset:
            assert dataset.overviews(1), "the fixture must exercise the overview read"
            assert dataset.compression.name == "deflate"
        dl._verify_asset_crop(valid_crop)


class TestTheCheckRejectsABrokenFile:
    def test_a_truncated_data_file(self, valid_crop: dl.AssetCropBytes) -> None:
        broken = dl.AssetCropBytes(data=valid_crop.data[: len(valid_crop.data) // 2], mask=valid_crop.mask)
        with pytest.raises(dl.CorruptOutput):
            dl._verify_asset_crop(broken)

    def test_a_tile_that_does_not_decode(self, valid_crop: dl.AssetCropBytes) -> None:
        broken = dl.AssetCropBytes(data=_flip_tile_bytes(valid_crop.data), mask=valid_crop.mask)
        with pytest.raises(dl.CorruptOutput, match="does not read back"):
            dl._verify_asset_crop(broken)

    def test_a_truncated_mask_file(self, valid_crop: dl.AssetCropBytes) -> None:
        broken = dl.AssetCropBytes(data=valid_crop.data, mask=valid_crop.mask[:200])
        with pytest.raises(dl.CorruptOutput):
            dl._verify_asset_crop(broken)

    @pytest.mark.parametrize("which", ["data", "mask"])
    def test_an_empty_file(self, valid_crop: dl.AssetCropBytes, which: str) -> None:
        crop = dl.AssetCropBytes(
            data=b"" if which == "data" else valid_crop.data,
            mask=b"" if which == "mask" else valid_crop.mask,
        )
        with pytest.raises(dl.CorruptOutput, match="empty"):
            dl._verify_asset_crop(crop)

    def test_json_instead_of_a_tiff(self, valid_crop: dl.AssetCropBytes) -> None:
        with pytest.raises(dl.CorruptOutput):
            dl._verify_asset_crop(dl.AssetCropBytes(data=b'{"type": "Polygon"}', mask=valid_crop.mask))

    def test_a_png_instead_of_a_tiff(self, valid_crop: dl.AssetCropBytes) -> None:
        """GDAL opens a PNG happily — only the driver check tells it apart."""
        with MemoryFile() as mem:
            with mem.open(driver="PNG", width=8, height=8, count=1, dtype="uint8") as dst:
                dst.write(np.ones((1, 8, 8), dtype="uint8"))
            png = mem.read()
        with pytest.raises(dl.CorruptOutput, match="not a GeoTIFF"):
            dl._verify_asset_crop(dl.AssetCropBytes(data=png, mask=valid_crop.mask))

    def test_a_mask_on_another_grid(self, valid_crop: dl.AssetCropBytes) -> None:
        shifted = _mask_bytes(np.ones((SIZE, SIZE), dtype="uint8"), transform=from_origin(600010, 5700000, 10, 10))
        with pytest.raises(dl.CorruptOutput, match="same grid"):
            dl._verify_asset_crop(dl.AssetCropBytes(data=valid_crop.data, mask=shifted))

    def test_a_mask_of_another_size(self, valid_crop: dl.AssetCropBytes) -> None:
        smaller = _mask_bytes(np.ones((SIZE - 1, SIZE), dtype="uint8"))
        with pytest.raises(dl.CorruptOutput, match="same grid"):
            dl._verify_asset_crop(dl.AssetCropBytes(data=valid_crop.data, mask=smaller))

    def test_a_mask_with_values_other_than_0_and_1(self, valid_crop: dl.AssetCropBytes) -> None:
        twos = _mask_bytes(np.full((SIZE, SIZE), 2, dtype="uint8"))
        with pytest.raises(dl.CorruptOutput, match="0 and 1"):
            dl._verify_asset_crop(dl.AssetCropBytes(data=valid_crop.data, mask=twos))

    def test_a_mask_with_two_bands(self, valid_crop: dl.AssetCropBytes) -> None:
        two_bands = _mask_bytes(np.ones((SIZE, SIZE), dtype="uint8"), count=2)
        with pytest.raises(dl.CorruptOutput, match="single uint8 band"):
            dl._verify_asset_crop(dl.AssetCropBytes(data=valid_crop.data, mask=two_bands))


class TestOneRetry:
    def _call(self) -> dl.AssetCropBytes:
        return dl._verified_crop(
            lambda path: None, (), {"type": "Point", "coordinates": [0, 0]},
            asset="visual", width=None, height=None, mask_geometry={"type": "Point", "coordinates": [0, 0]},
        )

    def test_a_broken_first_write_is_replaced_by_a_good_second_one(
        self, valid_crop: dl.AssetCropBytes, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        broken = dl.AssetCropBytes(data=valid_crop.data[:100], mask=valid_crop.mask)
        writes = iter([broken, valid_crop])
        monkeypatch.setattr(dl, "crop_asset_to_cog_bytes", lambda *args, **kwargs: next(writes))
        with caplog.at_level(logging.WARNING, logger="earthx.access.download"):
            assert self._call() is valid_crop
        assert [record.levelno for record in caplog.records] == [logging.WARNING]
        assert "'visual'" in caplog.records[0].getMessage()

    def test_two_broken_writes_raise(
        self, valid_crop: dl.AssetCropBytes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = []

        def always_broken(*args: object, **kwargs: object) -> dl.AssetCropBytes:
            calls.append(1)
            return dl.AssetCropBytes(data=valid_crop.data[:100], mask=valid_crop.mask)

        monkeypatch.setattr(dl, "crop_asset_to_cog_bytes", always_broken)
        with pytest.raises(dl.CorruptOutput):
            self._call()
        assert len(calls) == 2, "exactly one retry, never more"

    def test_a_good_first_write_is_not_repeated(
        self, valid_crop: dl.AssetCropBytes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = []

        def good(*args: object, **kwargs: object) -> dl.AssetCropBytes:
            calls.append(1)
            return valid_crop

        monkeypatch.setattr(dl, "crop_asset_to_cog_bytes", good)
        self._call()
        assert len(calls) == 1


class TestTheZipCheck:
    def _zip(self, payload: bytes) -> BytesIO:
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("visual.tif", payload)
        return buffer

    def test_a_sound_zip_passes(self) -> None:
        dl._verify_zip(self._zip(b"x" * 10_000))

    def test_a_flipped_byte_in_an_entry_fails(self) -> None:
        payload = np.random.default_rng(1).integers(0, 255, 10_000, dtype="uint8").tobytes()
        raw = bytearray(self._zip(payload).getvalue())
        raw[200] ^= 0xFF
        with pytest.raises(dl.CorruptOutput):
            dl._verify_zip(BytesIO(bytes(raw)))

    def test_bytes_that_are_no_zip_at_all_fail(self) -> None:
        with pytest.raises(dl.CorruptOutput, match="does not read back"):
            dl._verify_zip(BytesIO(b"not a zip archive"))
