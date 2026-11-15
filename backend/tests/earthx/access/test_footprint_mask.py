"""Masking a tile to footprints (M5-30b, adr/0032 Nachtrag 15.11.2026): the pixels outside become nodata."""

from __future__ import annotations

import morecantile
import numpy
import pytest
from rio_tiler.models import ImageData
from shapely.geometry import MultiPolygon, Polygon, box

from earthx.access.footprint_mask import cut_to_footprints

TMS = morecantile.tms.get("WebMercatorQuad")
TILE = morecantile.Tile(x=8, y=5, z=4)  # a tile of the grid; its lon/lat bounds are the footprints' frame


def image(*, masked: numpy.ndarray | None = None, size: int = 64) -> ImageData:
    left, bottom, right, top = TMS.xy_bounds(TILE)
    data = numpy.full((1, size, size), 7.0, dtype="float32")
    mask = numpy.zeros((1, size, size), dtype=bool) if masked is None else masked
    return ImageData(numpy.ma.MaskedArray(data, mask=mask), bounds=(left, bottom, right, top), crs=TMS.rasterio_crs)


def west_half() -> Polygon:
    west, south, east, north = TMS.bounds(TILE)
    return box(west, south, (west + east) / 2, north)


def test_the_pixels_over_the_footprints_stay_and_the_others_are_masked() -> None:
    cut = cut_to_footprints(image(), west_half(), TMS.rasterio_crs)
    mask = numpy.ma.getmaskarray(cut.array)[0]
    assert not mask[:, :28].any() and mask[:, 36:].all()
    assert (numpy.ma.getdata(cut.array) == 7.0).all(), "values are kept, only the mask changes"


def test_what_was_masked_before_stays_masked() -> None:
    before = numpy.zeros((1, 64, 64), dtype=bool)
    before[:, :, :5] = True
    cut = cut_to_footprints(image(masked=before), west_half(), TMS.rasterio_crs)
    assert numpy.ma.getmaskarray(cut.array)[0, :, :5].all() and not numpy.ma.getmaskarray(cut.array)[0, :, 5:28].any()


def test_footprints_that_miss_the_tile_mask_everything() -> None:
    far = box(-100.0, 40.0, -99.0, 41.0)
    assert numpy.ma.getmaskarray(cut_to_footprints(image(), far, TMS.rasterio_crs).array).all()


def test_an_empty_union_masks_everything() -> None:
    assert numpy.ma.getmaskarray(cut_to_footprints(image(), Polygon(), TMS.rasterio_crs).array).all()


def test_two_footprints_leave_both_and_nothing_between() -> None:
    west, south, east, north = TMS.bounds(TILE)
    width = (east - west) / 10
    two = MultiPolygon([box(west, south, west + width, north), box(east - width, south, east, north)])
    mask = numpy.ma.getmaskarray(cut_to_footprints(image(), two, TMS.rasterio_crs).array)[0]
    assert not mask[:, :4].any() and not mask[:, -4:].any() and mask[:, 12:52].all()


@pytest.mark.parametrize("size", [32, 256])
def test_it_works_at_any_tile_size(size: int) -> None:
    mask = numpy.ma.getmaskarray(cut_to_footprints(image(size=size), west_half(), TMS.rasterio_crs).array)[0]
    assert not mask[:, : size // 2 - 4].any() and mask[:, size // 2 + 4 :].all()
