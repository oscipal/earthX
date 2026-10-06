"""Operator registry: what an operator is, which ones exist, where they apply (adr/0014 §5)."""

from earthx.processing.operators.base import BandMeta, Operator, RasterMeta, Requirement, Tier
from earthx.processing.operators.registry import JSON_SCHEMA_DIALECT, REGISTRY, OperatorRegistry, applicable

__all__ = [
    "JSON_SCHEMA_DIALECT",
    "REGISTRY",
    "BandMeta",
    "Operator",
    "OperatorRegistry",
    "RasterMeta",
    "Requirement",
    "Tier",
    "applicable",
]
