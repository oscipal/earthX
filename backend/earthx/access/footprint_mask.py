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

__all__ = ["cut_to_footprints", "cut_to_raster"]


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


@lru_cache(maxsize=16)
def _between(source: str, target: str) -> Transformer:
    return Transformer.from_crs(source, target, always_xy=True)


def cut_to_raster(image: ImageData, crs: Any, bounds: tuple[float, float, float, float]) -> ImageData:
    """``image`` with every pixel whose centre lies outside a raster's ``bounds`` (in its own ``crs``) masked.

    For a tile read past the edge of a file with a halo (M5-10, adr/0030 F3): GDAL's bilinear gives such pixels the value
    of the edge. Past the data that would invent a neighbour where the job has none; in a mosaic the next scene fills them
    with its own. Near a seam each scene still interpolates without the pixels of the other (a limit of reading scene by
    scene, measured in plan M5-10 §11.6).
    """
    height, width = image.array.shape[-2:]
    left, bottom, right, top = image.bounds
    columns = left + (numpy.arange(width) + 0.5) * (right - left) / width
    rows = top - (numpy.arange(height) + 0.5) * (top - bottom) / height
    xs, ys = numpy.meshgrid(columns, rows)
    if str(image.crs) != str(crs):
        xs, ys = _between(str(image.crs), str(crs)).transform(xs, ys)
    west, south, east, north = bounds
    inside = (xs >= west) & (xs <= east) & (ys >= south) & (ys <= north)
    image.array = numpy.ma.MaskedArray(numpy.ma.getdata(image.array), mask=numpy.ma.getmaskarray(image.array) | ~inside[None])
    return image
