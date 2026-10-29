"""Operator registry: what an operator is, which ones exist, where they apply (adr/0014 §5)."""

from earthx.processing.operators.band_math import BAND_MATH, BandMathParams
from earthx.processing.operators.base import BandMeta, Operator, RasterMeta, Requirement, Tier
from earthx.processing.operators.mask import MASK, MaskParams
from earthx.processing.operators.normalize import NORMALIZE, NormalizeParams
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
    "BandMathParams",
    "BandMeta",
    "MASK",
    "NORMALIZE",
    "MaskParams",
    "NormalizeParams",
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
