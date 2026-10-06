"""``decode_cf``: the one generic switch between a decoded and a raw Zarr read (adr/0014 §5.4, F7a).

With the item's own scaling the worker applies it to raw values, so the reader must be
able to read the store as stored; without it, the reader's CF decoding stays exactly
what it was. Both cases on the same store, compared by value.
"""

from __future__ import annotations

from pathlib import Path

import numpy
import pytest

from earthx.access.resolve import ResolvedAsset, open_asset_ref
from earthx.readers.zarr_reader import ZarrReader, zarr_asset
from tests.earthx.readers import mini_zarr_cf
from tests.earthx.readers.mini_zarr import POLICY, from_memory


@pytest.fixture(scope="module")
def cf_store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return mini_zarr_cf.build_mini_zarr_cf(tmp_path_factory.mktemp("cf") / "mini.zarr")


@pytest.fixture
def served(cf_store: Path, serve) -> None:
    serve(cf_store)


def _read(decode_cf: bool):
    asset = zarr_asset(
        f"{mini_zarr_cf.GROUP_URL}/b04",
        POLICY,
        dataset_id="d",
        item_id="i",
        asset="r10m:b04",
        crs=mini_zarr_cf.ITEM_CRS,
        resolve=from_memory,
        decode_cf=decode_cf,
    )
    with ZarrReader(asset) as reader:
        attrs = dict(reader.input.attrs)
        image = reader.part(
            mini_zarr_cf.store_bounds(),
            dst_crs=mini_zarr_cf.ITEM_CRS,
            bounds_crs=mini_zarr_cf.ITEM_CRS,
            width=mini_zarr_cf.SIZE,
            height=mini_zarr_cf.SIZE,
        )
    return image, attrs


@pytest.mark.usefixtures("served")
class TestDecodeCf:
    def test_the_default_still_decodes_to_physical_values(self) -> None:
        image, attrs = _read(decode_cf=True)
        raw = mini_zarr_cf.raw_band("b04")
        assert image.array.dtype.kind == "f"
        valid = raw != mini_zarr_cf.FILL
        expected = raw[valid] * mini_zarr_cf.SCALE + mini_zarr_cf.OFFSET
        numpy.testing.assert_allclose(image.array.data[0][valid], expected)
        assert "scale_factor" not in attrs

    def test_off_reads_the_stored_integers_and_keeps_the_attributes(self) -> None:
        image, attrs = _read(decode_cf=False)
        assert image.array.dtype == numpy.uint16
        numpy.testing.assert_array_equal(image.array.data[0], mini_zarr_cf.raw_band("b04"))
        assert attrs["scale_factor"] == mini_zarr_cf.SCALE
        assert attrs["add_offset"] == mini_zarr_cf.OFFSET

    def test_off_still_masks_the_fill_value(self) -> None:
        image, _ = _read(decode_cf=False)
        mask = numpy.ma.getmaskarray(image.array)[0]
        assert mask[:4, :4].all()
        assert not mask[4:, 4:].any()


def test_open_asset_ref_hands_the_switch_to_the_zarr_asset() -> None:
    ref = ResolvedAsset(
        dataset_id="d",
        item_id="i",
        asset="r10m:b04",
        reader="zarr",
        href=mini_zarr_cf.GROUP_URL,
        variable="b04",
        crs=mini_zarr_cf.ITEM_CRS,
    )
    assert open_asset_ref(ref, POLICY, from_memory).decode_cf is True
    assert open_asset_ref(ref, POLICY, from_memory, decode_cf=False).decode_cf is False
