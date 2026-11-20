"""The colormaps the tiles take, and the list the browser chooses from (UI-03d, Otto 2.11.2026).

rio-tiler's own colormaps, and two it lacks that QGIS brings by default (``rocket`` and ``mako``, from seaborn,
BSD-3-Clause; ``colormap_data/``). Every tile route takes exactly these names as ``colormap_name``
(:data:`COLORMAP_PARAMS`), and ``GET /colormaps`` lists them with a group and a small preview, so that the browser keeps
no list of its own. A name ending in ``_r`` is the same colormap reversed, for every colormap (rio-tiler has none for
``cfastie``, ``rplumbo`` and ``schwarzwald``: their table is reversed here); the list names it beside its colormap.

The groups follow matplotlib's colormap reference and cmocean's documentation:
https://github.com/matplotlib/matplotlib/blob/main/galleries/examples/color/colormap_reference.py and
https://github.com/matplotlib/cmocean/blob/main/docs/source/index.rst. ``cfastie``, ``rplumbo`` and ``schwarzwald`` are
rio-tiler's own and in neither; they are "other".
"""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

from rio_tiler.colormap import cmap as RIO_TILER_COLORMAPS
from titiler.core.dependencies import create_colormap_dependency

from earthx.catalog.datasets import registry

__all__ = ["CLASS_TABLES", "COLORMAPS", "COLORMAP_PARAMS", "GROUPS", "PREVIEW_STOPS", "REVERSED", "catalog"]

_DATA = Path(__file__).with_name("colormap_data")

#: The colormaps added to rio-tiler's, each a file of 256 RGB triples in ``colormap_data/`` (origin and licence in it).
_ADDED = ("rocket", "mako")


def _class_tables() -> dict[str, dict[int, tuple[int, int, int, int]]]:
    """The tables of classes, by the ``colormap_name`` of the standard picture of each entry whose picture is a band of
    classes (M5-07 plan F4, M5-62): the colour of every class from the registry, its value without a class see-through.

    They paint a class layer as its source does, with no stretch: the tiles take them as ``colormap_name`` like every
    other, but they are no ramp to choose for other data, so the list leaves them out and none has a reversed one.
    Entries that share a name (the two states of WorldCover) must give the same table. The released entries only, read
    without the start check of the instance (adr/0024 R5), as the runner reads them: importing this module needs no
    setting of the process.
    """
    tables: dict[str, dict[int, tuple[int, int, int, int]]] = {}
    for entry in registry(prototype=False):
        render = entry.default_render
        if render is None or render.colormap_name is None or len(render.assets) != 1:
            continue
        classes = entry.band_classes.get(render.assets[0])
        if classes is None:
            continue
        table = {row.value: (*(int(row.colour[i : i + 2], 16) for i in (1, 3, 5)), 255) for row in classes.rows()}
        if classes.nodata is not None:
            table[classes.nodata] = (0, 0, 0, 0)
        if tables.setdefault(render.colormap_name, table) != table:
            raise ValueError(f"two entries give the class table {render.colormap_name} different colours")
    return tables


_CLASSES = _class_tables()

#: The names of the tables of classes (:func:`_class_tables`).
CLASS_TABLES = tuple(_CLASSES)

REVERSED = "_r"

GROUPS: dict[str, tuple[str, ...]] = {
    "sequential": (
        "viridis", "plasma", "inferno", "magma", "cividis", "rocket", "mako",
        "greys", "purples", "blues", "greens", "oranges", "reds", "ylorbr", "ylorrd", "orrd", "purd", "rdpu", "bupu",
        "gnbu", "pubu", "ylgnbu", "pubugn", "bugn", "ylgn",
        "gray", "binary", "gist_gray", "gist_yarg", "bone", "pink", "spring", "summer", "autumn", "winter", "cool",
        "wistia", "hot", "afmhot", "gist_heat", "copper",
        "thermal", "haline", "solar", "ice", "oxy", "deep", "dense", "algae", "matter", "turbid", "speed", "amp",
        "tempo", "rain",
    ),
    "diverging": (
        "rdylgn", "rdbu", "rdylbu", "spectral", "piyg", "prgn", "brbg", "puor", "rdgy", "coolwarm", "bwr", "seismic",
        "balance", "delta", "curl", "diff", "tarn",
    ),
    "cyclic": ("twilight", "twilight_shifted", "hsv", "phase"),
    "qualitative": ("tab10", "tab20", "tab20b", "tab20c", "set1", "set2", "set3", "pastel1", "pastel2", "paired", "accent", "dark2"),
    "other": (
        "terrain", "gist_earth", "topo", "ocean", "turbo", "jet", "rainbow", "gist_rainbow", "nipy_spectral", "gist_ncar",
        "gist_stern", "gnuplot", "gnuplot2", "cmrmap", "cubehelix", "brg", "flag", "prism", "cfastie", "rplumbo",
        "schwarzwald",
    ),
}  # fmt: skip

#: Colours of the preview of each colormap in the list: enough for a smooth strip, few enough for a short answer.
PREVIEW_STOPS = 16


def _added() -> dict[str, dict[int, tuple[int, int, int, int]]]:
    """The added colormaps and their reversed ones, as rio-tiler registers a colormap: 256 entries of RGBA."""
    added: dict[str, dict[int, tuple[int, int, int, int]]] = {}
    for name in _ADDED:
        rgb = json.loads((_DATA / f"{name}.json").read_text(encoding="utf-8"))["rgb"]
        if len(rgb) != 256:
            raise ValueError(f"the colormap {name} has {len(rgb)} colours, not 256")
        table = [(int(r), int(g), int(b), 255) for r, g, b in rgb]
        added[name] = dict(enumerate(table))
        added[f"{name}{REVERSED}"] = dict(enumerate(reversed(table)))
    added.update(_CLASSES)
    # rio-tiler's own ones without a reversed one get it here, so that "Reverse" holds for every colormap.
    names = set(RIO_TILER_COLORMAPS.list())
    for name in sorted(names):
        if name.endswith(REVERSED) or f"{name}{REVERSED}" in names:
            continue
        own = RIO_TILER_COLORMAPS.get(name)
        values = [own[key] for key in sorted(own)]
        added[f"{name}{REVERSED}"] = dict(zip(sorted(own), reversed(values), strict=True))
    return added


COLORMAPS = RIO_TILER_COLORMAPS.register(_added())

#: The ``colormap_name`` of every tile route: the names of :data:`COLORMAPS` and no other.
COLORMAP_PARAMS: Callable[..., Any] = create_colormap_dependency(COLORMAPS)


def _preview(name: str) -> list[str]:
    table = COLORMAPS.get(name)
    keys = sorted(table)
    picks = [keys[round(i * (len(keys) - 1) / (PREVIEW_STOPS - 1))] for i in range(PREVIEW_STOPS)]
    return ["#{:02x}{:02x}{:02x}".format(*table[key][:3]) for key in picks]


@cache
def catalog() -> dict[str, Any]:
    """The answer of ``GET /colormaps``: the groups in their order, each colormap with its preview and its reversed name."""
    names = set(COLORMAPS.list())
    return {
        "groups": [
            {
                "name": group,
                "colormaps": [
                    {
                        "name": name,
                        "reversed": f"{name}{REVERSED}" if f"{name}{REVERSED}" in names else None,
                        "colors": _preview(name),
                    }
                    for name in members
                ],
            }
            for group, members in GROUPS.items()
        ]
    }
