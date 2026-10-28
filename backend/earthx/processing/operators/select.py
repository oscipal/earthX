"""``select_bands``: the planner's own step that drops the bands nobody needs and puts the rest in order (adr/0020 §4).

Not in the registry and not in a recipe: :func:`~earthx.processing.plan.stock_steps` puts it between the steps
of a job where the stock holds a band that no later step and not the output needs, and at the end, so that the
bands of a result are those of ``output.bands`` in that order. A dropped band is not warped, not written and not
counted; the bands that stay keep their values, because every step works per band or per pixel.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from rio_tiler.models import ImageData

from earthx.catalog.registry import LicenseTier
from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators.base import Operator, RasterMeta, Requirement, Tier

__all__ = ["SELECT_BANDS", "SelectParams"]


class SelectParams(BaseModel):
    """The names to keep, in the order the stock is to have afterwards."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    names: tuple[str, ...]


def _indices(names: list[str], wanted: tuple[str, ...]) -> list[int]:
    missing = [name for name in wanted if name not in names]
    if missing:
        raise RecipeInvalid(f"the bands {', '.join(missing)} are not among the bands: {', '.join(names)}")
    return [names.index(name) for name in wanted]


def _run(image: ImageData, params: BaseModel) -> ImageData:
    assert isinstance(params, SelectParams)
    indices = _indices(list(image.band_names), params.names)
    return ImageData(
        image.array[indices], bounds=image.bounds, crs=image.crs, band_names=list(params.names), nodata=image.nodata
    )


def _transform(meta: RasterMeta, params: BaseModel) -> RasterMeta:
    assert isinstance(params, SelectParams)
    indices = _indices([band.name for band in meta.bands], params.names)
    bands = tuple(meta.bands[index] for index in indices)
    return RasterMeta(meta.crs, meta.transform, meta.width, meta.height, bands, meta.resampled)


SELECT_BANDS = Operator(
    op="select_bands",
    op_version=1,
    category="bands",
    title="Select bands",
    description="Keep the bands named, in this order (planned by the core, never ordered).",
    citation=None,
    params=SelectParams,
    requires=Requirement(capabilities=frozenset(), data_classes=frozenset(), license_tier=LicenseTier.PROCESSING),
    tiers=frozenset({Tier.T2}),
    kind="pixel",
    cost_factor=lambda params: 0.0,
    transform=_transform,
    run=_run,
    lineage=lambda params: "",
    method=lambda params: "",
)
