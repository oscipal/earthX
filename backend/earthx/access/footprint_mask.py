"""Mask a tile to the union of footprints (M5-30b, adr/0032 Nachtrag 15.11.2026: the pictures below ``min_zoom`` of a search).

A map cannot clip a raster by polygons, so the tile is masked on the server: the pixels whose centre lies outside the
footprints become nodata, which the route renders transparent. The footprints are in EPSG:4326, the tile in its grid's
CRS. Nothing here reads a file or opens an address.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy
from pyproj import Transformer
from rasterio.features import geometry_mask
from rasterio.transform import from_bounds
from rio_tiler.models import ImageData
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

__all__ = ["cut_to_footprints"]


@lru_cache(maxsize=8)
def _to_grid(crs: str) -> Transformer:
    return Transformer.from_crs("EPSG:4326", crs, always_xy=True)


def cut_to_footprints(image: ImageData, footprints: BaseGeometry, crs: Any) -> ImageData:
    """``image`` with every pixel whose centre lies outside ``footprints`` (lon/lat) masked; ``crs`` is that of the tile."""
    height, width = image.array.shape[-2:]
    left, bottom, right, top = image.bounds
    projected = transform(_to_grid(str(image.crs or crs)).transform, footprints)
    if projected.is_empty:
        inside = numpy.zeros((height, width), dtype=bool)
    else:
        inside = geometry_mask(
            [projected], out_shape=(height, width), transform=from_bounds(left, bottom, right, top, width, height), invert=True
        )
    mask = numpy.ma.getmaskarray(image.array) | ~inside[None]
    image.array = numpy.ma.MaskedArray(numpy.ma.getdata(image.array), mask=mask)
    return image
