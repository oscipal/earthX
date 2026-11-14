"""Synthetic slices of one radar pass, placed by GCPs only, like consecutive Sentinel-1 GRD slices (DS-04d).

Written by this module, no binary in the repository (ENTSCHEIDUNGEN §4). Measured at the source (plan
`docs/plans/m5/ds-04d-radargeometrie.md` §2) and copied here: the second slice begins exactly one line interval after
the last line of the first, both share the line interval and the ground range of column 0, and their widths differ.

Every pixel carries its own value: ``line * WIDTH + col + 1`` over the whole pass (``uint16``, 0 is nodata), so a test
reads from a value which line of the pass and which column it came from. Lines run southward, columns eastward, with a
gentle bend that no affine fit takes up; the GCPs lie on a coarse grid that includes the first and last line and the
first and last column of each slice, as in the annotation of a real slice.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy
import rasterio
from rasterio.control import GroundControlPoint
from rasterio.crs import CRS

#: Lines of each slice and the widths of the two slices (the second is narrower, as measured).
HEIGHT = 64
WIDTHS = (80, 72)

#: The widest slice: the width of a joined pass.
WIDTH = max(WIDTHS)

NODATA = 0

ORIGIN_LON = 11.0
ORIGIN_LAT = 46.5
STEP_LON = 0.00013
STEP_LAT = 0.00009

#: The bend across the pass, in pixels.
BEND_PIXELS = 3.0

#: Seconds from one line to the next (Sentinel-1 IW: about 1.5 ms).
LINE_INTERVAL = timedelta(microseconds=1500)

#: The time of the first line of the pass.
START = datetime(2026, 10, 26, 5, 34, 34, 496759, tzinfo=timezone.utc)

GCP_CRS = CRS.from_epsg(4326)

#: The item properties that carry the times of the first and last line (the registry's ``line_times``).
FIRST_LINE = "start_datetime"
LAST_LINE = "end_datetime"


def position(line: float, col: float) -> tuple[float, float]:
    """Longitude and latitude of the pixel/line position ``line``, ``col`` of the pass."""
    bend = BEND_PIXELS * math.sin(math.pi * line / (2 * HEIGHT)) * math.sin(math.pi * col / WIDTH)
    return ORIGIN_LON + (col + bend) * STEP_LON, ORIGIN_LAT - (line + 0.5 * bend) * STEP_LAT


def gcps(first_line: int, width: int, col_shift: float = 0.0) -> list[GroundControlPoint]:
    """The GCPs of a slice whose first line is line ``first_line`` of the pass; ``col_shift`` moves its columns."""
    rows = sorted({0, HEIGHT // 2, HEIGHT - 1})
    cols = sorted({0, width // 2, width - 1})
    points = []
    for row in rows:
        for col in cols:
            lon, lat = position(first_line + row + 0.5, col + 0.5 + col_shift)
            points.append(GroundControlPoint(row=row + 0.5, col=col + 0.5, x=lon, y=lat, z=0.0))
    return points


def build_slice(path: Path, index: int, *, col_shift: float = 0.0) -> Path:
    """Write slice ``index`` (0 or 1) of the pass to ``path``: tiled, with overviews, GCPs only."""
    width = WIDTHS[index]
    first_line = index * HEIGHT
    lines = numpy.arange(first_line, first_line + HEIGHT, dtype="uint32")[:, None]
    cols = numpy.arange(width, dtype="uint32")[None, :]
    data = (lines * WIDTH + cols + 1).astype("uint16")[None]
    profile = {
        "driver": "GTiff", "dtype": "uint16", "count": 1, "height": HEIGHT, "width": width, "nodata": NODATA,
        "tiled": True, "blockxsize": 32, "blockysize": 32,
        "gcps": gcps(first_line, width, col_shift), "crs": GCP_CRS,
    }  # fmt: skip
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)
        dst.build_overviews([2], rasterio.enums.Resampling.nearest)
    return path


def first_line_time(index: int, *, gap_lines: int = 0) -> datetime:
    return START + LINE_INTERVAL * (index * HEIGHT + gap_lines)


def item(index: int, *, gap_lines: int = 0, item_id: str | None = None) -> dict[str, Any]:
    """A STAC item of slice ``index`` with the times of its first and last line; ``gap_lines`` delays it."""
    first = first_line_time(index, gap_lines=gap_lines)
    last = first + LINE_INTERVAL * (HEIGHT - 1)
    return {
        "type": "Feature",
        "id": item_id or f"slice-{index}",
        "properties": {
            "datetime": first.isoformat(),
            FIRST_LINE: first.isoformat(),
            LAST_LINE: last.isoformat(),
        },
    }


def value_at(value: int) -> tuple[int, int]:
    """The line of the pass and the column a pixel value came from."""
    return divmod(int(value) - 1, WIDTH)
