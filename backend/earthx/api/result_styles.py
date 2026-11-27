"""The QGIS styles of a raster job's ZIP (M5-64): ``result.qml`` beside ``result.tif``, ``mask.qml`` beside ``mask.tif``.

`api` lays the ZIP out when it is downloaded (``processing_route._job_members``), so the style is the look the result
has in the app at that moment (plan F3): the look the download names, else the look of the band where its values are
the source's, the look of the operator of the last step, the look of an index preset whose expression the band has,
or viridis on the usual scale. A look without numbers takes the statistics the result carries (M4-32), which are those
the app draws with; nothing is read from the raster.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from earthx.access.qgis_style import (
    MASK_STYLE,
    ExportStyles,
    Stats,
    file_style,
    parse_order_look,
)
from earthx.catalog.registry import ClassRow, DatasetConfig, Look
from earthx.processing.operators import OperatorRegistry

__all__ = ["MASK_STYLE", "result_style"]


def result_style(
    properties: Mapping[str, Any],
    recipe: Mapping[str, Any],
    *,
    config: DatasetConfig | None,
    operators: OperatorRegistry,
    look: Any = None,
) -> str | None:
    """``result.qml`` for a result with ``properties`` (its STAC properties) made by ``recipe``; ``look`` as an order's.

    ``None`` for a result that names no bands (made before M4-32): nothing says what to draw. A :class:`ValueError`
    for a look the download cannot carry.
    """
    bands = properties.get("bands")
    if not isinstance(bands, list) or not bands or not all(isinstance(band, Mapping) for band in bands):
        if look is not None:
            parse_order_look(look)
        return None
    keys = [str(band.get("name", "")) for band in bands]
    classes = [_classes_of(band) for band in bands]
    looks = {key: found for key, band in zip(keys, bands, strict=True) if (found := _default_look(key, band, recipe, config, operators))}
    rgb = None
    if look is not None:
        ordered, rgb = parse_order_look(look)
        if len(keys) == 1 and len(ordered) == 1:
            # A result of one band: the app draws that band, whatever name it knows it by (it often knows none).
            ordered = {keys[0]: next(iter(ordered.values()))}
        looks.update(ordered)
    true_color = tuple(config.true_color) if config is not None and len(config.true_color) == 3 else None
    styles = ExportStyles(looks, rgb, true_color)  # type: ignore[arg-type]
    return file_style(len(bands), keys, classes, styles, lambda index: _stats_of(bands[index]))


def _classes_of(band: Mapping[str, Any]) -> tuple[ClassRow, ...] | None:
    """The classes the result names for a band whose values are classes, as the core writes them (``_stac_classes``)."""
    rows = band.get("classification:classes")
    if not isinstance(rows, list) or not rows:
        return None
    try:
        return tuple(ClassRow(int(row["value"]), str(row.get("title") or row["name"]), f"#{row['color_hint']}") for row in rows)
    except (KeyError, TypeError, ValueError):
        return None


def _stats_of(band: Mapping[str, Any]) -> Stats | None:
    statistics = band.get("statistics")
    if not isinstance(statistics, Mapping):
        return None
    try:
        minimum, maximum = float(statistics["minimum"]), float(statistics["maximum"])
        return Stats(
            float(statistics.get("percentile_2", minimum)), float(statistics.get("percentile_98", maximum)), minimum, maximum
        )
    except (KeyError, TypeError, ValueError):
        return None


def _default_look(
    name: str,
    band: Mapping[str, Any],
    recipe: Mapping[str, Any],
    config: DatasetConfig | None,
    operators: OperatorRegistry,
) -> Look | None:
    """The look the app gives the band when nobody has changed it (plan §4.3)."""
    if band.get("earthx:source_values") and config is not None:
        resolved = config.look_of(name)
        if resolved is not None:
            return resolved.look
    steps = recipe.get("steps")
    if not isinstance(steps, Sequence) or not steps or not isinstance(steps[-1], Mapping):
        return None
    last = steps[-1]
    params = last.get("params") if isinstance(last.get("params"), Mapping) else {}
    try:
        operator = operators.operator(str(last.get("op")), int(last.get("op_version", 0)))
    except (KeyError, ValueError, TypeError):
        operator = None
    if operator is not None and operator.looks is not None:
        found = operator.looks.by_value.get(str(params.get(operator.looks.param)))
        if found is not None:
            return found
    expression = params.get("expression")
    if config is not None and isinstance(expression, str) and params.get("name", name) == name:
        plain = "".join(expression.split())
        for preset in config.index_presets:
            if "".join(preset.expression.split()) == plain:
                return Look(preset.colormap_name, "fixed", float(preset.rescale[0]), float(preset.rescale[1]))
    return None
