"""Operator registry: what an operator is, which ones exist, where they apply (adr/0014 §5)."""

from earthx.processing.operators.band_math import BAND_MATH, BAND_MATH_V2, BandMathParams, BandMathParamsV2
from earthx.processing.operators.base import BandMeta, BandUse, Operator, RasterMeta, Requirement, Tier
from earthx.processing.operators.mask import MASK, MASK_V2, MaskParams
from earthx.processing.operators.mask_values import MASK_VALUES, MaskValuesParams
from earthx.processing.operators.normalize import (
    NORMALIZE,
    NORMALIZE_V2,
    NORMALIZE_V3,
    NORMALIZE_V4,
    NormalizeParams,
    NormalizeParamsV2,
    NormalizeParamsV3,
    NormalizeParamsV4,
)
from earthx.processing.operators.registry import JSON_SCHEMA_DIALECT, REGISTRY, OperatorRegistry, applicable
from earthx.processing.operators.reproject import (
    REPROJECT,
    REPROJECT_V2,
    REPROJECT_V3,
    ReprojectParams,
    ReprojectParamsV2,
)

__all__ = [
    "JSON_SCHEMA_DIALECT",
    "REGISTRY",
    "BAND_MATH",
    "BAND_MATH_V2",
    "BandMathParams",
    "BandMathParamsV2",
    "BandMeta",
    "BandUse",
    "MASK",
    "MASK_V2",
    "MASK_VALUES",
    "NORMALIZE",
    "NORMALIZE_V2",
    "NORMALIZE_V3",
    "NORMALIZE_V4",
    "MaskParams",
    "MaskValuesParams",
    "NormalizeParams",
    "NormalizeParamsV2",
    "NormalizeParamsV3",
    "NormalizeParamsV4",
    "REPROJECT",
    "REPROJECT_V2",
    "REPROJECT_V3",
    "Operator",
    "OperatorRegistry",
    "RasterMeta",
    "ReprojectParams",
    "ReprojectParamsV2",
    "Requirement",
    "Tier",
    "applicable",
]
