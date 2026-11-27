"""The tables of the colour ramps, 256 RGBA colours each, without the tiler around them (M5-64).

The tiles draw with them (``access.colormaps`` registers them with titiler) and the QGIS style of an export writes them
(``access.qgis_style``), so that a band looks the same in the app and in QGIS. rio-tiler's colormaps, ``rocket`` and
``mako`` from ``colormap_data/`` (seaborn, BSD-3-Clause), and a reversed table (``_r``) for every one that lacks it.
Nothing here loads titiler or the registry: the worker core writes styles too.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from rio_tiler.colormap import cmap as RIO_TILER_COLORMAPS

__all__ = ["ADDED", "REVERSED", "ramp_colours", "ramp_tables"]

_DATA = Path(__file__).with_name("colormap_data")

#: The colormaps added to rio-tiler's, each a file of 256 RGB triples in ``colormap_data/`` (origin and licence in it).
ADDED = ("rocket", "mako")

REVERSED = "_r"

Colour = tuple[int, int, int, int]


@cache
def ramp_tables() -> dict[str, dict[int, Colour]]:
    """The added colormaps and the reversed ones rio-tiler lacks, as rio-tiler registers a colormap: 256 entries of RGBA."""
    added: dict[str, dict[int, Colour]] = {}
    for name in ADDED:
        rgb = json.loads((_DATA / f"{name}.json").read_text(encoding="utf-8"))["rgb"]
        if len(rgb) != 256:
            raise ValueError(f"the colormap {name} has {len(rgb)} colours, not 256")
        table = [(int(r), int(g), int(b), 255) for r, g, b in rgb]
        added[name] = dict(enumerate(table))
        added[f"{name}{REVERSED}"] = dict(enumerate(reversed(table)))
    names = set(RIO_TILER_COLORMAPS.list())
    for name in sorted(names):
        if name.endswith(REVERSED) or f"{name}{REVERSED}" in names:
            continue
        own = RIO_TILER_COLORMAPS.get(name)
        values = [own[key] for key in sorted(own)]
        added[f"{name}{REVERSED}"] = dict(zip(sorted(own), reversed(values), strict=True))
    return added


def ramp_colours(name: str) -> list[Colour] | None:
    """The 256 colours of the ramp ``name`` in the order of the values, or ``None`` for a name the tiles do not know."""
    table = ramp_tables().get(name)
    if table is None:
        try:
            table = RIO_TILER_COLORMAPS.get(name)
        except Exception:  # rio-tiler raises its own error for an unknown name
            return None
    colours = [tuple(int(c) for c in table[key]) for key in sorted(table)]
    return colours if len(colours) == 256 else None  # type: ignore[return-value]
