"""The index presets of the registry, checked against the step they fill (NM4-14 plan §8.1).

A preset is no operator of its own: one click in the panel fills an ordinary ``band_math`` step of version 2 with
its ``expression`` and ``name``. ``catalog`` checks the form of a preset but cannot import ``processing``; what only
``band_math`` and the tiler know is checked here, when ``api`` is built, the way ``adapters.check_adapter_specs``
checks the adapters. ``api`` serves the collection the panel reads the presets from, so a preset that a user could not
type into the panel stops that start instead of becoming a button that is refused. The tiler does not call this: its
start stays without ``processing`` (``test_tiler_start_is_light``).
"""

from __future__ import annotations

from rio_tiler.colormap import cmap

from earthx.catalog.registry import ConfigError, DatasetRegistry
from earthx.processing.operators.band_math import check_expression, check_name

__all__ = ["IndexPresetMismatch", "check_index_presets"]


class IndexPresetMismatch(ConfigError):
    """A preset of the registry that ``band_math`` or the tiler would refuse."""


def check_index_presets(registry: DatasetRegistry) -> None:
    """Refuse a registry whose presets ``band_math`` (version 2) would not take, or whose colormap the tiler lacks.

    The bands ``band_math`` reads off the expression are matched against the entry once more, so that the text check
    in ``catalog`` and the syntax tree here cannot drift apart unnoticed.
    """
    colormaps = set(cmap.list())
    problems: list[str] = []
    for config in registry:
        bands = set(config.band_units) - set(config.auxiliary_assets) - ({config.mask.asset} if config.mask else set())
        for preset in config.index_presets:
            where = f"{config.dataset_id}: the index preset {preset.name}"
            try:
                check_name(preset.name)
            except ValueError as error:
                problems.append(f"{where}: {error}")
            try:
                read = check_expression(preset.expression)
            except ValueError as error:
                problems.append(f"{where}: {error}")
            else:
                if unknown := read - bands:
                    problems.append(f"{where}: reads {', '.join(sorted(unknown))}, which is no band of the data")
            if preset.colormap_name not in colormaps:
                problems.append(f"{where}: the tiler knows no colormap {preset.colormap_name!r}")
    if problems:
        raise IndexPresetMismatch("; ".join(problems))
