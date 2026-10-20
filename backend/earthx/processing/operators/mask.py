"""``mask``: hide the pixels whose class in a classification layer the recipe names (adr/0014 §15k).

An operator for ``T1`` and ``T2``. The layer is one of the bands of the input — the order names its asset
(``scl``, ``SCL_20m:scl``), the registry says which one (``DatasetConfig.mask``) — so the tile (T1) and the job
(T2) call the very same function on the same image. Every other band keeps its name, values and type; the
pixels it hides are masked in all of them, and the layer itself leaves the result (K2): whoever needs it reads it
without the mask.

A pixel is hidden where the layer holds one of ``classes`` **or** is masked itself (nodata, F3). The comparison
is exact, ``numpy.isin`` on the values as read; a coarser layer has been brought onto the finer grid with
``nearest`` before, which only repeats pixels, so it holds no value the file does not (plan §8).

Nothing here is a float computation, which is why the result is bit-stable across machines (R5, §15c).
"""

from __future__ import annotations

from typing import Annotated, Any

import numpy
from pydantic import BaseModel, ConfigDict, Field, field_validator
from rio_tiler.models import ImageData

from earthx.catalog.registry import MAX_MASK_VALUE, DatasetConfig, LicenseTier
from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators.base import Operator, RasterMeta, Requirement, Tier

__all__ = ["MASK", "MAX_CLASSES", "MaskParams"]

MAX_CLASSES = 64

_MAX_SOURCE_CHARS = 64


class MaskParams(BaseModel):
    """The panel's form (K8): the layer's band name and the classes to hide, both always given (B10)."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    # No `pattern` here: the Rust `regex` of pydantic and ECMA-262 read it differently (§5.1).
    source: str = Field(
        min_length=1,
        max_length=_MAX_SOURCE_CHARS,
        description="Band name of the classification layer, as the registry names it.",
    )
    classes: list[Annotated[int, Field(ge=0, le=MAX_MASK_VALUE)]] = Field(
        min_length=1,
        max_length=MAX_CLASSES,
        description="Class values to hide, ascending and each once.",
    )

    @field_validator("source")
    @classmethod
    def _printable(cls, value: str) -> str:
        if not all("!" <= char <= "~" for char in value):
            raise ValueError("source is printable ASCII without spaces")
        return value

    @field_validator("classes")
    @classmethod
    def _ascending(cls, value: list[int]) -> list[int]:
        # One mask, one way to write it: two orders would be two recipes with two hashes (K3).
        if value != sorted(set(value)):
            raise ValueError("classes are listed ascending, each value once")
        return value


def _others(names: list[str], source: str) -> list[int]:
    if source not in names:
        raise RecipeInvalid(f"mask source {source!r} is not among the bands: {', '.join(names)}")
    others = [index for index, name in enumerate(names) if name != source]
    if not others:
        raise RecipeInvalid("the order holds only the classification layer, so there is nothing to mask")
    return others


def _run(image: ImageData, params: BaseModel) -> ImageData:
    assert isinstance(params, MaskParams)
    names = list(image.band_names)
    others = _others(names, params.source)
    layer = image.array[names.index(params.source)]
    hidden = numpy.isin(numpy.ma.getdata(layer), params.classes) | numpy.ma.getmaskarray(layer)
    kept = image.array[others]
    array = numpy.ma.MaskedArray(numpy.ma.getdata(kept), mask=numpy.ma.getmaskarray(kept) | hidden[None])
    return ImageData(
        array, bounds=image.bounds, crs=image.crs, band_names=[names[index] for index in others], nodata=image.nodata
    )


def _transform(meta: RasterMeta, params: BaseModel) -> RasterMeta:
    """The bands without the layer; also the check, before any block is read, that the layer is there."""
    assert isinstance(params, MaskParams)
    names = [band.name for band in meta.bands]
    others = _others(names, params.source)
    bands = tuple(meta.bands[index] for index in others)
    return RasterMeta(meta.crs, meta.transform, meta.width, meta.height, bands, meta.resampled)


def _lineage(params: BaseModel) -> str:
    assert isinstance(params, MaskParams)
    return f"mask: {params.source} classes {', '.join(map(str, params.classes))}"


def _properties(params: BaseModel) -> dict[str, Any]:
    assert isinstance(params, MaskParams)
    return {"earthx:mask": {"source": params.source, "classes": list(params.classes)}}


def _dataset_check(config: DatasetConfig, params: BaseModel) -> list[str]:
    """The layer and the classes have to be the ones the entry describes (a mask over ``red`` is no mask)."""
    assert isinstance(params, MaskParams)
    layer = config.mask
    if layer is None:
        return []
    reasons = []
    if params.source != layer.band:
        reasons.append(f"{config.dataset_id} masks with its layer {layer.band!r}, not {params.source!r}")
    unknown = sorted(set(params.classes) - {entry.value for entry in layer.classes})
    if unknown:
        reasons.append(f"the layer {layer.band!r} of {config.dataset_id} has no class {', '.join(map(str, unknown))}")
    return reasons


MASK = Operator(
    op="mask",
    op_version=1,
    category="quality",
    title="Mask",
    description="Hide the pixels that a classification layer assigns to the chosen classes, such as cloud.",
    citation=None,
    params=MaskParams,
    requires=Requirement(
        capabilities=frozenset({"masking"}), data_classes=frozenset(), license_tier=LicenseTier.PROCESSING
    ),
    tiers=frozenset({Tier.T1, Tier.T2}),
    kind="pixel",
    cost_factor=lambda params: 0.2,
    transform=_transform,
    run=_run,
    lineage=_lineage,
    properties=_properties,
    dataset_check=_dataset_check,
)
