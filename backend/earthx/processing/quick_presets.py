"""The composite and step presets of the registry, checked against the steps they fill (adr/0030 F7, M5-14).

Like an index preset (:mod:`earthx.processing.index_presets`) a composite or step preset is no operator of its own: one
click under "Quick processing" fills ordinary steps, three ``band_math`` steps of version 2 for a composite, the step of
its operator for a step preset. ``catalog`` checks the form but cannot import ``processing``; what only the operators and
the tiler know is checked here, when ``api`` is built. A preset the dataset cannot do (a flag it lacks, an operator that
runs as a job only, a look the tiler cannot paint) stops that start instead of becoming a button that is refused.
"""

from __future__ import annotations

import json

from pydantic import ValidationError
from rio_tiler.colormap import cmap

from earthx.catalog.registry import COMPOSITE_CHANNEL_SUFFIXES, ConfigError, DatasetConfig, DatasetRegistry, StepPreset
from earthx.processing.operators.band_math import check_expression, check_name
from earthx.processing.operators.base import Tier
from earthx.processing.operators.registry import REGISTRY, OperatorRegistry, applicable

__all__ = ["QuickPresetMismatch", "check_quick_presets"]


class QuickPresetMismatch(ConfigError):
    """A composite or step preset of the registry that its steps or the tiler would refuse."""


def _bands_of(config: DatasetConfig) -> set[str]:
    return set(config.band_units) - set(config.auxiliary_assets) - ({config.mask.asset} if config.mask else set())


def _composite_problems(config: DatasetConfig) -> list[str]:
    problems: list[str] = []
    bands = _bands_of(config)
    for preset in config.composite_presets:
        where = f"{config.dataset_id}: the composite preset {preset.name}"
        for channel, end in zip(preset.channels, COMPOSITE_CHANNEL_SUFFIXES, strict=True):
            try:
                check_name(preset.name + end)
                read = check_expression(channel)
            except ValueError as error:
                problems.append(f"{where}: {error}")
                continue
            if unknown := read - bands:
                problems.append(f"{where}: reads {', '.join(sorted(unknown))}, which is no band of the data")
    return problems


def _step_problem(config: DatasetConfig, preset: StepPreset, operators: OperatorRegistry) -> str | None:
    operator = operators.get((preset.op, preset.op_version))
    if operator is None or not operator.listed or not operator.stock:
        return f"names {preset.op} version {preset.op_version}, which the panel does not offer"
    if Tier.T1 not in operator.tiers or operator.kind not in ("pixel", "focal"):
        return f"{preset.op} does not run as a tile"
    if "name" not in operator.params.model_fields:
        return f"{preset.op} adds no named band"
    try:
        params = operator.params.model_validate_json(json.dumps({**preset.params, "name": preset.name}))
    except (TypeError, ValueError) as error:
        detail = (
            "; ".join(f"{'.'.join(map(str, e['loc'])) or 'params'}: {e['msg']}" for e in error.errors(include_url=False))
            if isinstance(error, ValidationError)
            else str(error)
        )
        return f"has parameters {preset.op} refuses: {detail}"
    if reasons := applicable(operator, config, params):
        return f"cannot run here: {'; '.join(reasons)}"
    use = operator.bands_used(params)
    if use.adds != preset.name:
        return f"does not add the band {preset.name}"
    if unknown := set(use.reads) - _bands_of(config):
        return f"reads {', '.join(sorted(unknown))}, which is no band of the data"
    look = operator.looks.of(params) if operator.looks is not None else None
    if look is None:
        return f"has no look of {preset.op} to be drawn with (adr/0035)"
    if look.colormap not in set(cmap.list()):
        return f"is drawn with the colormap {look.colormap!r}, which the tiler does not know"
    return None


def check_quick_presets(registry: DatasetRegistry, operators: OperatorRegistry = REGISTRY) -> None:
    """Refuse a registry with a composite or step preset its steps would not take, or the tiler could not draw."""
    problems: list[str] = []
    for config in registry:
        problems.extend(_composite_problems(config))
        for preset in config.step_presets:
            if problem := _step_problem(config, preset, operators):
                problems.append(f"{config.dataset_id}: the step preset {preset.name} {problem}")
    if problems:
        raise QuickPresetMismatch("; ".join(problems))
