"""The operator registry and the applicability check (adr/0014 §5.1–§5.3).

An immutable mapping ``(op, op_version) → Operator``. :data:`REGISTRY` is the one
the platform runs; it holds ``reproject`` (M4-10); band math (M4-09) registers here too. A caller that needs more — a test, and later the
composition root that hands in the quad-pol operator from `datasets/` (§12) —
builds its own with :meth:`OperatorRegistry.with_operators`, and passes it to
``processing.run``.

:func:`applicable` checks against the ``DatasetConfig`` it is handed, never
against ``catalog.datasets`` (adr/0011 §6.2): `api` calls it when it accepts a
recipe and when it lists processes per dataset. The worker core only checks that
operator and version exist and the parameters validate.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel

from earthx.catalog.registry import DatasetConfig, LicenseTier
from earthx.processing.errors import UnknownOperator
from earthx.processing.operators.base import Operator
from earthx.processing.operators.reproject import REPROJECT

__all__ = ["JSON_SCHEMA_DIALECT", "REGISTRY", "OperatorRegistry", "applicable"]

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

_TIER_ORDER = (LicenseTier.CATALOG, LicenseTier.DISPLAY, LicenseTier.PROCESSING)


class OperatorRegistry(Mapping[tuple[str, int], Operator]):
    """Operators by name and version; a second registration of the same pair is refused."""

    __slots__ = ("_operators",)

    def __init__(self, operators: Iterable[Operator] = ()) -> None:
        collected: dict[tuple[str, int], Operator] = {}
        for operator in operators:
            key = (operator.op, operator.op_version)
            if key in collected:
                raise ValueError(f"operator {operator.op} version {operator.op_version} is registered twice")
            collected[key] = operator
        self._operators = MappingProxyType(collected)

    def __getitem__(self, key: tuple[str, int]) -> Operator:
        return self._operators[key]

    def __iter__(self) -> Iterator[tuple[str, int]]:
        return iter(self._operators)

    def __len__(self) -> int:
        return len(self._operators)

    def with_operators(self, *operators: Operator) -> OperatorRegistry:
        """A new registry with these operators added; this one stays as it is."""
        return OperatorRegistry([*self._operators.values(), *operators])

    def operator(self, op: str, op_version: int) -> Operator:
        """The operator, or :class:`UnknownOperator` (`422` in `api`, never a silent upgrade, §4.3)."""
        try:
            return self._operators[(op, op_version)]
        except KeyError:
            raise UnknownOperator(f"operator {op!r} version {op_version} is not available") from None

    def params_model(self, op: str, op_version: int) -> type[BaseModel]:
        """For :func:`earthx.processing.recipe.parse_recipe`; raises ``LookupError`` when unknown."""
        operator = self._operators.get((op, op_version))
        if operator is None:
            raise LookupError(op)
        return operator.params

    def params_schema(self, op: str, op_version: int) -> dict[str, Any]:
        """The parameters as JSON Schema 2020-12, the form the panel is built from (K8)."""
        schema = self.operator(op, op_version).params.model_json_schema()
        return {"$schema": JSON_SCHEMA_DIALECT, **schema}


REGISTRY = OperatorRegistry([REPROJECT])


def applicable(operator: Operator, config: DatasetConfig, params: BaseModel | None = None) -> list[str]:
    """Why ``operator`` may not run on this dataset; empty means it may.

    Every flag the operator requires has to be set on the entry (B10); with
    ``params`` the flags the parameters add as well (``interpolation`` for a
    resampling other than ``nearest``). The licence has to reach the operator's
    tier (B11); ``commercial_use=false`` only matters with accounts (M6).
    """
    reasons = []
    required = set(operator.requires.capabilities)
    if params is not None:
        required |= operator.extra_requirements(params)
    for flag in sorted(required):
        if not getattr(config.capabilities, flag):
            reasons.append(f"{config.dataset_id} does not allow {flag}")
    data_classes = operator.requires.data_classes
    if data_classes and config.data_class not in data_classes:
        reasons.append(f"{operator.op} does not apply to {config.data_class.value} data")
    if _TIER_ORDER.index(config.license.tier) < _TIER_ORDER.index(operator.requires.license_tier):
        reasons.append(f"the licence of {config.dataset_id} does not allow {operator.requires.license_tier.value}")
    return reasons
