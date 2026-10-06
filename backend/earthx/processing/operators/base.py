"""What an operator is (adr/0014 §5.2, §5.6, §5.7).

An operator is a registration, not a route: an identifier with a version, a
strict parameter model (from which the panel's JSON Schema comes, K8), what it
requires of a dataset, the tiers it runs in, a cost factor, how it changes the
raster's metadata and its kernel.

Two kinds, because they need different things from the core:

* ``pixel`` — a kernel from :class:`~rio_tiler.models.ImageData` to
  ``ImageData``, the type a tile carries, so the tile (T1) and the job (T2) call
  the very same function (§6.2). The core hands it one block at a time.
* ``grid`` — a kernel that computes one block of a new grid from a source dataset
  in the run's work directory (approved F3): ``run(source, target, window,
  params) -> MaskedArray``. Its plan (block size, ``tolerance``,
  ``warp_mem_limit``) is part of the operator and versioned with ``op_version``
  (§3.4). Only ``T2``.

Two deviations from the sketch in §5.2, both in plan M4-07a §3.2: ``cost_factor``
instead of a full ``estimate`` (the estimate itself is computed once, in
:mod:`earthx.processing.plan`), and ``extra_requirements`` for flags that depend on
the parameters (``interpolation`` for a resampling other than ``nearest``, §5.3).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel
from rasterio.transform import Affine

from earthx.catalog.registry import Capabilities, DataClass, LicenseTier

__all__ = ["BandMeta", "Operator", "RasterMeta", "Requirement", "Tier"]

_OP_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CAPABILITY_NAMES = frozenset(field.name for field in fields(Capabilities))


class Tier(Enum):
    """Where an operator runs (§5.7). The local runner runs the T2 core (T2L is not a value)."""

    T1 = "T1"
    T2 = "T2"


@dataclass(frozen=True, slots=True)
class Requirement:
    """What a dataset has to allow for an operator (B10, B11)."""

    #: Names of :class:`~earthx.catalog.registry.Capabilities` flags; all must be ``True``.
    capabilities: frozenset[str]
    #: Empty means any data class.
    data_classes: frozenset[DataClass]
    license_tier: LicenseTier

    def __post_init__(self) -> None:
        unknown = self.capabilities - _CAPABILITY_NAMES
        if unknown:
            raise ValueError(f"unknown capability flags {sorted(unknown)}")


@dataclass(frozen=True, slots=True)
class BandMeta:
    """One band of a raster as the result describes it."""

    name: str
    data_type: str
    nodata: float | None
    unit: str | None = None
    scale: float = 1.0
    offset: float = 0.0


@dataclass(frozen=True, slots=True)
class RasterMeta:
    """The small description every operator maps onto a new one (§5.6).

    ``resampled`` is the honesty flag of principle 2.9: a step that resamples or
    reprojects sets it, and panel and download show it.
    """

    crs: str
    transform: Affine
    width: int
    height: int
    bands: tuple[BandMeta, ...]
    resampled: bool = False

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        left, top = self.transform @ (0, 0)
        right, bottom = self.transform @ (self.width, self.height)
        return (min(left, right), min(top, bottom), max(left, right), max(top, bottom))

    @property
    def resolution(self) -> tuple[float, float]:
        return (abs(self.transform.a), abs(self.transform.e))


def _no_extra_requirements(params: BaseModel) -> frozenset[str]:
    return frozenset()


@dataclass(frozen=True, slots=True)
class Operator:
    """One registered operator in one version."""

    op: str
    op_version: int
    category: str
    title: str
    description: str
    citation: str | None
    params: type[BaseModel]
    requires: Requirement
    tiers: frozenset[Tier]
    kind: Literal["pixel", "grid"]
    cost_factor: Callable[[BaseModel], float]
    transform: Callable[[RasterMeta, BaseModel], RasterMeta]
    run: Callable[..., Any]
    lineage: Callable[[BaseModel], str]
    extra_requirements: Callable[[BaseModel], frozenset[str]] = field(default=_no_extra_requirements)

    def __post_init__(self) -> None:
        if not _OP_NAME.match(self.op):
            raise ValueError(f"operator name {self.op!r} is lower case, digits and underscores")
        if self.op_version < 1:
            raise ValueError("op_version starts at 1")
        if not self.tiers:
            raise ValueError(f"{self.op} runs in no tier")
        if self.kind == "grid" and self.tiers != frozenset({Tier.T2}):
            raise ValueError(f"{self.op}: a grid operator runs in T2 only (§6.1)")
        config = self.params.model_config
        if config.get("strict") is not True or config.get("extra") != "forbid":
            raise ValueError(f"{self.op}: the parameter model is strict and forbids extra fields (§5.1)")
