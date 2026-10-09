"""Operators that exist only in the test tree (plan M4-07a §3.2).

``scale`` is a ``pixel`` operator: every band times ``factor``, as float32, the
mask unchanged. ``coarsen`` is a ``grid`` operator: the same CRS at ``factor``
times the pixel size, read with ``nearest`` from the source in the work
directory. Neither exists on the platform; M4-09 and M4-10 bring the real ones.
"""

from __future__ import annotations

import numpy
from pydantic import BaseModel, ConfigDict, Field
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window
from rio_tiler.models import ImageData

from earthx.catalog.registry import LicenseTier
from earthx.processing.operators import REGISTRY, BandMeta, Operator, RasterMeta, Requirement, Tier


class ScaleParams(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    factor: float
    label: str | None = None


class CoarsenParams(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    factor: int = Field(ge=2, le=16)


def _scale(image: ImageData, params: ScaleParams) -> ImageData:
    data = image.array.astype("float32") * numpy.float32(params.factor)
    return ImageData(
        data,
        bounds=image.bounds,
        crs=image.crs,
        band_names=list(image.band_names),
        nodata=image.nodata,
    )


def _scale_meta(meta: RasterMeta, params: ScaleParams) -> RasterMeta:
    bands = tuple(BandMeta(name=band.name, data_type="float32", nodata=band.nodata) for band in meta.bands)
    return RasterMeta(meta.crs, meta.transform, meta.width, meta.height, bands, meta.resampled)


def _coarsen_meta(meta: RasterMeta, params: CoarsenParams) -> RasterMeta:
    factor = params.factor
    width = -(-meta.width // factor)
    height = -(-meta.height // factor)
    transform = meta.transform @ Affine.scale(factor, factor)
    return RasterMeta(meta.crs, transform, width, height, meta.bands, resampled=True)


def _coarsen(source, target: RasterMeta, window: Window, params: CoarsenParams) -> numpy.ma.MaskedArray:
    with WarpedVRT(
        source,
        crs=target.crs,
        transform=target.transform,
        width=target.width,
        height=target.height,
        resampling=Resampling.nearest,
    ) as vrt:
        return vrt.read(window=window, masked=True)


SCALE = Operator(
    op="scale",
    op_version=1,
    category="test",
    title="Scale",
    description="Every band times a factor.",
    citation=None,
    params=ScaleParams,
    requires=Requirement(
        capabilities=frozenset({"band_math"}), data_classes=frozenset(), license_tier=LicenseTier.PROCESSING
    ),
    tiers=frozenset({Tier.T1, Tier.T2}),
    kind="pixel",
    cost_factor=lambda params: 1.0,
    transform=_scale_meta,
    run=_scale,
    lineage=lambda params: f"scaled by {params.factor}",
)

COARSEN = Operator(
    op="coarsen",
    op_version=1,
    category="test",
    title="Coarsen",
    description="The same CRS at a coarser pixel size, nearest neighbour.",
    citation=None,
    params=CoarsenParams,
    requires=Requirement(
        capabilities=frozenset({"reprojection"}), data_classes=frozenset(), license_tier=LicenseTier.PROCESSING
    ),
    tiers=frozenset({Tier.T2}),
    kind="grid",
    cost_factor=lambda params: 0.4,
    transform=_coarsen_meta,
    run=_coarsen,
    lineage=lambda params: f"coarsened by {params.factor} (nearest)",
)

#: The platform's registry plus both test operators.
OPERATORS = REGISTRY.with_operators(SCALE, COARSEN)
