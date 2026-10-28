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

Deviations from the sketch in §5.2: ``cost_factor`` instead of a full ``estimate``
(the estimate itself is computed once, in :mod:`earthx.processing.plan`),
``extra_requirements`` for flags that depend on the parameters (``interpolation`` for
a resampling other than ``nearest``, §5.3; plan M4-07a §3.2), and ``properties`` for
what a step adds to the result's STAC properties (plan M4-09, §5.6), and ``dataset_check``
for what the parameters must agree with in the entry itself, such as the layer ``mask`` reads (plan M4-18, adr/0014 §15m).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel
from rasterio.transform import Affine

from earthx.catalog.registry import Capabilities, DataClass, DatasetConfig, LicenseTier

__all__ = ["BandMeta", "BandUse", "Operator", "RasterMeta", "Requirement", "Tier"]

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
    #: The values of this band were brought onto another grid (read from a coarser asset, warped from another
    #: zone, reprojected). The result is marked resampled only if a band that is in it was (NM4-43c, backlog 51);
    #: a layer that only hides pixels does not count.
    resampled: bool = False


@dataclass(frozen=True, slots=True)
class BandUse:
    """Which bands of the stock one step needs and changes (adr/0020 §4); the planner drops what nobody needs.

    The default is a step that keeps every band by name and needs none besides the ones it passes on.
    """

    #: Bands the step reads besides the ones it passes on: the names of an expression, the layer of a mask.
    reads: frozenset[str] = frozenset()
    #: The name of the one band the step adds to the stock, ``band_math``'s result; ``None`` for a step that adds none.
    adds: str | None = None
    #: The bands whose values the step changes; ``None`` for all. A step that changes none the output keeps is not run.
    acts_on: frozenset[str] | None = None


@dataclass(frozen=True, slots=True)
class RasterMeta:
    """The small description every operator maps onto a new one (§5.6).

    ``resampled`` is the honesty flag of principle 2.9: a step that resamples or
    reprojects sets it, and panel and download show it. For a result of the core it is the
    flag of the bands in it (:attr:`BandMeta.resampled`).
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


def _no_properties(params: BaseModel) -> dict[str, Any]:
    return {}


def _no_dataset_reasons(config: DatasetConfig, params: BaseModel) -> list[str]:
    return []


def _keeps_every_band(params: BaseModel) -> BandUse:
    return BandUse()


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
    #: One sentence of the methods text (M4-19a): what the step did, for a paper's methods section.
    method: Callable[[BaseModel], str]
    extra_requirements: Callable[[BaseModel], frozenset[str]] = field(default=_no_extra_requirements)
    #: STAC properties this step adds to the result, such as ``processing:expression`` (§5.6).
    properties: Callable[[BaseModel], dict[str, Any]] = field(default=_no_properties)
    #: Why these parameters do not fit this entry (empty means they do); only :func:`applicable` calls it.
    dataset_check: Callable[[DatasetConfig, BaseModel], list[str]] = field(default=_no_dataset_reasons)
    #: Which bands of the stock the step needs and changes (:class:`BandUse`), for the planner (adr/0020 §4).
    bands_used: Callable[[BaseModel], BandUse] = field(default=_keeps_every_band)
    #: The same step for a stock that the planner narrowed: ``restrict(params, kept)`` keeps of the bands the step changes
    #: only those in ``kept`` (``normalize``). ``None`` for a step that names no bands.
    restrict: Callable[[BaseModel, frozenset[str]], BaseModel] | None = None
    #: Whether the step works on the stock of named bands (recipe version 2). ``False`` is a step of recipe
    #: version 1, which replaces or removes bands: it stays for the tile and for old recipes, which are
    #: rewritten before the core sees them (:mod:`earthx.processing.upgrade`), and no job runs it.
    stock: bool = True
    #: Whether the process description offers this version. The highest *listed* version of an operator is
    #: offered; one that is only accepted (or not yet offered) is not (NM4-43c: version 2 of the bands steps comes
    #: with the panel that sends it).
    listed: bool = True

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
