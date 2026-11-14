"""``terrain``: slope, aspect or hillshade of a band of heights (M5-10, adr/0030 F3, adr/0023 F5).

A ``focal`` operator with a halo of one pixel: each pixel from its 3 × 3 window, by the formulas of ``gdaldem``
(GDAL 3.12, ``apps/gdaldem_lib.cpp``): the gradient after Horn (eight neighbours, the default) or Zevenbergen and
Thorne (four), slope in degrees or percent, aspect as an azimuth (0 = north, clockwise, a flat pixel has none),
hillshade 1 to 255 for one light or ``gdaldem``'s weighted four (``multidirectional``). Unlike ``gdaldem`` the
aspect takes the size of the pixel into account, which matters where the pixels are not square on the ground.

**Pixel size in metres** (plan M5-10 F3), per row from the CRS and where the row lies, never from the block, so that a
block of another size gives the same values: on a geographic CRS from the radii of curvature of its ellipsoid; on Web
Mercator (the tiles) the projected size times the scale at that latitude; any other projected CRS in its unit of
length, as ``gdaldem`` does.

**Edges** (plan M5-10 F2): a pixel whose window reaches a masked pixel or past the raster is masked, as ``gdaldem``
does without ``-compute_edges``. The core reads the halo from the data, past the AOI too.

Values are computed in ``float64`` and returned as ``float32``; each pixel from its own window in a fixed order, so
the job and the runner agree to the bit.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any, Literal

import numpy
import pyproj
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from rio_tiler.models import ImageData

from earthx.catalog.registry import LicenseTier
from earthx.processing.errors import RecipeInvalid, UnsupportedRecipe
from earthx.processing.operators.band_math import MAX_NAME_CHARS, check_name
from earthx.processing.operators.base import BandMeta, BandUse, Operator, RasterMeta, Requirement, Tier

__all__ = ["HEIGHT_UNIT", "TERRAIN", "TerrainParams"]

#: The unit a band of heights has to carry: the formulas compare heights with horizontal distances in metres.
HEIGHT_UNIT = "m"

_HALO = 1
_PSEUDO_MERCATOR = "Popular Visualisation Pseudo Mercator"
_HILLSHADE_FIELDS = ("altitude", "z_factor", "multidirectional")
_PRODUCT_FIELDS: dict[str, tuple[str, ...]] = {
    "slope": ("slope_unit",),
    "aspect": (),
    "hillshade": _HILLSHADE_FIELDS,
}
_OPTIONAL_FIELDS = ("slope_unit", "azimuth", *_HILLSHADE_FIELDS)
_UNITS = {"degrees": "deg", "percent": "%"}


class TerrainParams(BaseModel):
    """The panel's form (K8): what to compute from which band of heights; the fields of the other products stay out."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    product: Literal["slope", "aspect", "hillshade"] = Field(description="What to compute from the heights.")
    bands: list[str] = Field(min_length=1, max_length=1, description="The band of heights, in metres.")
    name: str = Field(
        min_length=1,
        max_length=MAX_NAME_CHARS,
        description="Name of the new band: a letter, then letters, digits or _; free in the data and the other results.",
    )
    method: Literal["horn", "zevenbergen_thorne"] = Field(
        default="horn", description="Gradient after Horn (eight neighbours) or Zevenbergen and Thorne (four)."
    )
    slope_unit: Literal["degrees", "percent"] | None = Field(default=None, description="slope: degrees or percent.")
    azimuth: float | None = Field(
        default=None, ge=0, lt=360, allow_inf_nan=False, description="hillshade: direction of the light, 0 = north."
    )
    altitude: float | None = Field(
        default=None, ge=0, le=90, allow_inf_nan=False, description="hillshade: height of the light above the horizon."
    )
    z_factor: float | None = Field(
        default=None, gt=0, le=1e6, allow_inf_nan=False, description="hillshade: factor on the heights."
    )
    multidirectional: bool | None = Field(
        default=None, description="hillshade: light from four directions, without azimuth."
    )

    @field_validator("name")
    @classmethod
    def _free_name(cls, value: str) -> str:
        check_name(value)
        return value

    @model_validator(mode="after")
    def _fields_of_product(self) -> TerrainParams:
        given = {field for field in _OPTIONAL_FIELDS if getattr(self, field) is not None}
        wanted = set(_PRODUCT_FIELDS[self.product])
        if self.product == "hillshade" and self.multidirectional is False:
            wanted.add("azimuth")
        if missing := sorted(wanted - given):
            raise ValueError(f"{self.product} needs {', '.join(missing)}")
        if foreign := sorted(given - wanted):
            raise ValueError(f"{self.product} takes no {', '.join(foreign)}")
        return self


def _params(params: BaseModel) -> TerrainParams:
    assert isinstance(params, TerrainParams)
    return params


@lru_cache(maxsize=32)
def _parsed(wkt: str) -> pyproj.CRS:
    return pyproj.CRS.from_wkt(wkt)


def _radii(crs: pyproj.CRS, latitude: numpy.ndarray) -> tuple[numpy.ndarray, numpy.ndarray]:
    """The radius of curvature along the parallel (``N cos φ``) and along the meridian (``M``) at ``latitude``."""
    ellipsoid = crs.ellipsoid
    if ellipsoid is None:
        raise UnsupportedRecipe("terrain needs a coordinate reference system with an ellipsoid")
    a = ellipsoid.semi_major_metre
    e2 = (
        0.0
        if not ellipsoid.inverse_flattening
        else (2 - 1 / ellipsoid.inverse_flattening) / ellipsoid.inverse_flattening
    )
    w = numpy.sqrt(1 - e2 * numpy.sin(latitude) ** 2)
    return a / w * numpy.cos(latitude), a * (1 - e2) / w**3


def pixel_metres(image: ImageData) -> tuple[numpy.ndarray, numpy.ndarray]:
    """The size of a pixel on the ground in metres, east-west and north-south, for each row inside the halo.

    Arrays of shape ``(rows - 2, 1)``; each row is measured at its own centre."""
    if image.crs is None:
        raise UnsupportedRecipe("terrain needs a raster placed in a coordinate reference system")
    crs = _parsed(image.crs.to_wkt())
    left, bottom, right, top = image.bounds
    x_size = abs(right - left) / image.width
    y_size = abs(top - bottom) / image.height
    centres = top - (numpy.arange(_HALO, image.height - _HALO, dtype="float64") + 0.5) * (top - bottom) / image.height
    if crs.is_geographic:
        if crs.axis_info[0].unit_name != "degree":
            raise UnsupportedRecipe("terrain reads a geographic CRS in degrees only")
        along_parallel, along_meridian = _radii(crs, numpy.radians(centres))
        east, north = math.radians(x_size) * along_parallel, math.radians(y_size) * along_meridian
    elif (
        crs.is_projected
        and crs.coordinate_operation is not None
        and crs.coordinate_operation.method_name == _PSEUDO_MERCATOR
    ):
        radius = crs.ellipsoid.semi_major_metre if crs.ellipsoid is not None else 6378137.0
        latitude = numpy.arctan(numpy.sinh(centres / radius))
        along_parallel, along_meridian = _radii(crs, latitude)
        # x is radius · λ and y grows by radius / cos φ per radian of latitude.
        east, north = x_size * along_parallel / radius, y_size * along_meridian * numpy.cos(latitude) / radius
    elif crs.is_projected:
        factor = crs.axis_info[0].unit_conversion_factor
        east, north = numpy.full(centres.shape, x_size * factor), numpy.full(centres.shape, y_size * factor)
    else:
        raise UnsupportedRecipe("terrain needs a geographic or projected coordinate reference system")
    return east[:, None], north[:, None]


def _gradient(
    heights: numpy.ndarray, east: numpy.ndarray, north: numpy.ndarray, method: str
) -> tuple[numpy.ndarray, numpy.ndarray]:
    """The rise per metre towards east and towards north of each pixel inside the halo."""
    a, b, c = heights[:-2, :-2], heights[:-2, 1:-1], heights[:-2, 2:]
    d, f = heights[1:-1, :-2], heights[1:-1, 2:]
    g, h, i = heights[2:, :-2], heights[2:, 1:-1], heights[2:, 2:]
    if method == "horn":
        return ((c + f + f + i) - (a + d + d + g)) / (8 * east), ((a + b + b + c) - (g + h + h + i)) / (8 * north)
    return (f - d) / (2 * east), (b - h) / (2 * north)


def _hillshade(gx: numpy.ndarray, gy: numpy.ndarray, params: TerrainParams) -> numpy.ndarray:
    """``gdaldem hillshade``: 1 where the light does not reach, up to 255 facing it."""
    assert params.altitude is not None and params.z_factor is not None
    z = params.z_factor
    sin_alt = math.sin(math.radians(params.altitude))
    cos_alt_z = math.cos(math.radians(params.altitude)) * z
    squared = gx * gx + gy * gy
    root = numpy.sqrt(1 + z * z * squared)
    if not params.multidirectional:
        assert params.azimuth is not None
        azimuth = math.radians(params.azimuth)
        cang = (sin_alt - cos_alt_z * (gx * math.sin(azimuth) + gy * math.cos(azimuth))) / root
        return numpy.where(cang <= 0, 1.0, 1 + 254 * cang)
    # gdaldem's weights of the lights from 225, 270, 315 and 360 degrees (Mark 1992), in its own signs.
    x, y = -gx, gy
    cos225 = math.cos(math.radians(225))
    lights = [
        numpy.maximum(sin_alt + (x - y) * cos225 * cos_alt_z, 0),
        numpy.maximum(sin_alt - x * cos_alt_z, 0),
        numpy.maximum(sin_alt + (x + y) * cos225 * cos_alt_z, 0),
        numpy.maximum(sin_alt - y * cos_alt_z, 0),
    ]
    w225 = 0.5 * squared - x * y
    weights = [w225, x * x, squared - w225, y * y]
    with numpy.errstate(invalid="ignore", divide="ignore"):
        weighted = sum(weight * light for weight, light in zip(weights, lights, strict=True)) / squared
    return numpy.where(squared == 0, 1 + 254 * sin_alt, 1 + 127 * weighted / root)


def _computed(
    heights: numpy.ndarray, invalid: numpy.ndarray, image: ImageData, params: TerrainParams
) -> tuple[numpy.ndarray, numpy.ndarray]:
    east, north = pixel_metres(image)
    gx, gy = _gradient(heights, east, north, params.method)
    rows, cols = invalid.shape
    # A pixel is masked where any pixel of its window is (gdaldem without -compute_edges).
    mask = numpy.zeros((rows - 2 * _HALO, cols - 2 * _HALO), dtype=bool)
    for dr in range(3):
        for dc in range(3):
            mask |= invalid[dr : rows - 2 + dr, dc : cols - 2 + dc]
    if params.product == "slope":
        steepness = numpy.sqrt(gx * gx + gy * gy)
        values = 100 * steepness if params.slope_unit == "percent" else numpy.degrees(numpy.arctan(steepness))
    elif params.product == "aspect":
        values = numpy.degrees(numpy.arctan2(-gx, -gy)) % 360
        mask |= (gx == 0) & (gy == 0)
    else:
        values = _hillshade(gx, gy, params)
    mask |= ~numpy.isfinite(values)
    result = numpy.where(mask, numpy.nan, values).astype("float32")
    if params.product == "aspect":
        result[result == numpy.float32(360)] = 0  # 359.99999… rounds up in 32 bits
    return result, mask


def _run(image: ImageData, params: BaseModel) -> ImageData:
    """The stock without its halo and the new band; a block smaller than the window is refused."""
    step = _params(params)
    names = list(image.band_names)
    if step.bands[0] not in names:
        raise RecipeInvalid(f"terrain reads {step.bands[0]}, which the input does not have: {', '.join(names)}")
    if image.height <= 2 * _HALO or image.width <= 2 * _HALO:
        raise RecipeInvalid("terrain needs a block larger than its window")
    band = image.array[names.index(step.bands[0])]
    heights = numpy.ma.getdata(band).astype("float64")
    invalid = numpy.ma.getmaskarray(band) | ~numpy.isfinite(heights)
    values, mask = _computed(numpy.where(invalid, 0.0, heights), invalid, image, step)
    inner = image.array[:, _HALO:-_HALO, _HALO:-_HALO]
    added = numpy.ma.MaskedArray(values[None], mask=mask[None])
    stock = numpy.ma.concatenate([inner, added.astype(numpy.promote_types(inner.dtype, "float32"))])
    left, bottom, right, top = image.bounds
    x_size, y_size = (right - left) / image.width, (top - bottom) / image.height
    bounds = (left + _HALO * x_size, bottom + _HALO * y_size, right - _HALO * x_size, top - _HALO * y_size)
    return ImageData(stock, bounds=bounds, crs=image.crs, band_names=[*names, step.name], nodata=image.nodata)


def _unit(params: TerrainParams) -> str | None:
    if params.product == "slope":
        assert params.slope_unit is not None
        return _UNITS[params.slope_unit]
    return "deg" if params.product == "aspect" else None


def _transform(meta: RasterMeta, params: BaseModel) -> RasterMeta:
    """The bands and one more; also the check, before any block is read, that the band is one of heights in metres."""
    step = _params(params)
    bands = {band.name: band for band in meta.bands}
    source = bands.get(step.bands[0])
    if source is None:
        raise RecipeInvalid(f"terrain reads {step.bands[0]}, which the input does not have: {', '.join(bands)}")
    if source.unit != HEIGHT_UNIT:
        raise RecipeInvalid(f"terrain reads heights in metres; {source.name} is in {source.unit or 'no unit'}")
    if step.name.casefold() in {name.casefold() for name in bands}:
        raise RecipeInvalid(f"{step.name} is used twice")
    band = BandMeta(
        name=step.name, data_type="float32", nodata=float("nan"), unit=_unit(step), resampled=source.resampled
    )
    return RasterMeta(meta.crs, meta.transform, meta.width, meta.height, (*meta.bands, band), meta.resampled)


def _bands_used(params: BaseModel) -> BandUse:
    step = _params(params)
    return BandUse(reads=frozenset(step.bands), adds=step.name)


_METHODS = {"horn": "Horn (1981)", "zevenbergen_thorne": "Zevenbergen and Thorne (1987)"}


def _what(step: TerrainParams) -> str:
    if step.product == "slope":
        return f"slope in {step.slope_unit}"
    if step.product == "aspect":
        return "aspect as an azimuth from north"
    light = "light from four directions" if step.multidirectional else f"light from azimuth {step.azimuth:g}°"
    return f"hillshade ({light}, altitude {step.altitude:g}°, z-factor {step.z_factor:g})"


def _lineage(params: BaseModel) -> str:
    step = _params(params)
    return f"terrain: {step.name} = {step.product} of {step.bands[0]} ({step.method})"


def _method(params: BaseModel) -> str:
    step = _params(params)
    return (
        f"A band named {step.name} was computed as the {_what(step)} of {step.bands[0]} from the 3 × 3 window of each "
        f"pixel, with the gradient after {_METHODS[step.method]} and the pixel size in metres at each row; pixels whose "
        "window reaches a gap or the edge of the data were left empty."
    )


def _properties(params: BaseModel) -> dict[str, Any]:
    step = _params(params)
    return {"earthx:terrain": step.model_dump(mode="json", exclude_none=True)}


TERRAIN = Operator(
    op="terrain",
    op_version=1,
    category="terrain",
    title="Terrain",
    description="Compute slope, aspect or hillshade from a band of heights and add it to the bands.",
    citation=(
        "Horn, B. K. P. (1981): Hill shading and the reflectance map. Proceedings of the IEEE 69(1), 14–47. "
        "Zevenbergen, L. W., Thorne, C. R. (1987): Quantitative analysis of land surface topography. "
        "Earth Surface Processes and Landforms 12(1), 47–56."
    ),
    params=TerrainParams,
    requires=Requirement(
        capabilities=frozenset({"terrain"}), data_classes=frozenset(), license_tier=LicenseTier.PROCESSING
    ),
    tiers=frozenset({Tier.T1, Tier.T2}),
    kind="focal",
    halo=_HALO,
    # adr/0030 §7: nine neighbours, a gradient and a trigonometric function, like band math with its statistics.
    cost_factor=lambda params: 1.2,
    transform=_transform,
    run=_run,
    lineage=_lineage,
    method=_method,
    properties=_properties,
    bands_used=_bands_used,
    # Accepted in recipes, not yet offered: the panel builds its form, whose fields depend on the product, with the
    # tile in the second part of M5-10 (plan §9a).
    listed=False,
)
