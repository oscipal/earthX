"""What the outlines of scenes say about an area, without reading a pixel (DS-03c).

Two questions are answered from the ``geometry`` of the items alone:

* **Coverage** of an AOI: the part of the AOI that lies inside the outline of one scene, or inside the union of the
  outlines of the scenes of an overpass (:meth:`AoiOutlines.coverage`). The outline is the footprint the source
  gives, not the valid pixels inside it; what is missing in a footprint is the filter "No data"'s question.
* **Weights** of the scenes of an overpass (:func:`mosaic_weights`): the area each scene adds to the mosaic when the
  scenes are laid in the order of the mosaic and a place that an earlier scene already has counts for that scene only.
  They weight the values the items carry (the cloud cover of a scene, the share of water) into one value for the pass.

Areas are computed in an equal-area projection (EPSG:6933), so that a share of degrees does not stand in for a share
of ground. Nothing here opens a connection or logs anything; an outline that is not a valid polygon on the globe is
``None`` and the caller says what that means for its question.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import shapely
from rasterio.warp import transform_geom
from shapely.errors import ShapelyError
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

#: The projection areas are computed in: cylindrical equal-area on the WGS 84 ellipsoid.
EQUAL_AREA = "EPSG:6933"

_AREA_TYPES = frozenset({"Polygon", "MultiPolygon"})


def outline_of(item: Mapping[str, Any]) -> BaseGeometry | None:
    """The outline of ``item`` in the equal-area projection, or ``None`` where it has none that is an area.

    A ring that crosses itself is repaired (``make_valid``), as sources sometimes write one; an outline without area is
    none."""
    geometry = item.get("geometry")
    if not isinstance(geometry, Mapping) or geometry.get("type") not in _AREA_TYPES:
        return None
    return _projected(geometry)


def _projected(geometry: Mapping[str, Any]) -> BaseGeometry | None:
    try:
        flat = shape(dict(geometry))
        if not flat.is_valid:
            flat = shapely.make_valid(flat)
        flat = _polygonal(flat)
        bounds = flat.bounds if flat is not None else ()
        if flat is None or not all(math.isfinite(v) for v in bounds):
            return None
        if not (-180 <= bounds[0] <= bounds[2] <= 180 and -90 <= bounds[1] <= bounds[3] <= 90):
            return None
        projected = shape(transform_geom("EPSG:4326", EQUAL_AREA, mapping(flat)))
    except (ShapelyError, ValueError, TypeError, KeyError, AttributeError, IndexError):
        return None
    if projected.is_empty or projected.area <= 0 or not math.isfinite(projected.area):
        return None
    return projected


def _polygonal(geometry: BaseGeometry) -> BaseGeometry | None:
    """The polygons of ``geometry``, whatever else ``make_valid`` left in it."""
    if geometry.geom_type in _AREA_TYPES:
        return geometry
    parts = [part for part in getattr(geometry, "geoms", ()) if part.geom_type in _AREA_TYPES]
    return unary_union(parts) if parts else None


class AoiOutlines:
    """The AOI in the equal-area projection, against which outlines are measured."""

    def __init__(self, aoi: Mapping[str, Any]) -> None:
        area = _projected(aoi)
        if area is None:
            raise ValueError("the AOI is not a valid polygon on the globe")
        self._area = area

    def touches(self, outline: BaseGeometry) -> bool:
        """Whether ``outline`` (from :func:`outline_of`) shares any area with the AOI."""
        try:
            return bool(self._area.intersection(outline).area > 0)
        except ShapelyError:
            return True  # not told apart from touching: the caller reads to be sure

    def coverage(self, outlines: Sequence[BaseGeometry | None]) -> float | None:
        """The share of the AOI inside the union of ``outlines`` in percent, one decimal; ``None`` if one is missing.

        One outline is the coverage of a scene, the outlines of an overpass its coverage as a whole. A scene without
        an outline cannot be said to cover or not to cover, so the question has no answer."""
        if not outlines or any(outline is None for outline in outlines):
            return None
        try:
            covered = unary_union([outline for outline in outlines if outline is not None]).intersection(self._area)
        except ShapelyError:
            return None
        return round(min(100.0, 100 * covered.area / self._area.area), 1)


def mosaic_weights(outlines: Sequence[BaseGeometry | None]) -> list[float] | None:
    """The area each scene adds to the mosaic, in the order given (the order of the mosaic), or ``None``.

    The first scene weighs its outline; each later scene what its outline holds that the ones before do not. A place in an
    overlap is thereby counted once, for the scene the mosaic takes it from. ``None`` if an outline is missing: the weights
    of the others would not add up to the pass."""
    if any(outline is None for outline in outlines):
        return None
    weights: list[float] = []
    taken: BaseGeometry | None = None
    try:
        for outline in outlines:
            assert outline is not None
            weights.append(outline.area if taken is None else outline.difference(taken).area)
            taken = outline if taken is None else taken.union(outline)
    except ShapelyError:
        return None
    return weights
