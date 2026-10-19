"""The unit of a target CRS, for the cell size of ``reproject`` (M4-13c-3; plan §3.7).

``reproject`` takes its pixel size "in the units of the target CRS". The panel shows what that
means (10 m, 0.0003° ≈ 33 m) before the order is sent; this module answers from ``pyproj``'s
bundled EPSG database.

**It reads nothing from the network.** PROJ may fetch grids and definitions on demand when
``PROJ_NETWORK=ON``; :func:`switch_off_proj_network` turns that off for the PROJ of ``pyproj`` at start,
whatever the environment says (approved F6, 15.10.2026). The PROJ inside ``rasterio`` is another
library and is not touched. A code the local database lacks is unknown here.
"""

from __future__ import annotations

import copy
import math
import re
from functools import lru_cache
from typing import Any

import pyproj
from pyproj.exceptions import CRSError

__all__ = ["CrsRefused", "crs_description", "switch_off_proj_network"]

#: What the order's ``crs`` parameter takes (``ReprojectParams.crs``); ``re.fullmatch``, because ``$``
#: would let a trailing line break through.
_CODE = re.compile(r"EPSG:[0-9]{4,6}")

_DEGREE_IN_RADIANS = math.pi / 180.0


class CrsRefused(ValueError):
    """The code names no CRS the platform can give a unit for; the text is for the person who typed it."""


def switch_off_proj_network() -> None:
    """No PROJ request leaves the process, whatever ``PROJ_NETWORK`` says."""
    pyproj.network.set_network_enabled(False)


def _unit_of(axes: list[Any]) -> tuple[str, float]:
    """The one unit all ``axes`` share, or why there is none."""
    unusable = not axes or any(
        axis.unit_name in {"", "unknown"}
        or not math.isfinite(axis.unit_conversion_factor)
        or axis.unit_conversion_factor <= 0
        for axis in axes
    )
    if unusable:
        raise CrsRefused("the CRS names no unit for its axes")
    units = {(axis.unit_name, axis.unit_conversion_factor) for axis in axes}
    if len(units) > 1:
        raise CrsRefused("the axes of the CRS have different units")
    return units.pop()


@lru_cache(maxsize=512)
def _describe(code: str) -> tuple[dict[str, Any] | None, str | None]:
    """The description or the reason for a refusal; both are cached, so a run of unknown codes costs once each."""
    if not _CODE.fullmatch(code):
        return None, "not an EPSG code like EPSG:3035"
    try:
        crs = pyproj.CRS.from_user_input(code)
    except CRSError:
        return None, f"{code} is not a CRS this platform knows"
    horizontal = crs.sub_crs_list[0] if crs.is_compound and crs.sub_crs_list else crs
    if horizontal.is_geographic:
        kind, unit_kind = "geographic", "angular"
        axes = list(horizontal.axis_info[:2])
    elif horizontal.is_projected:
        kind, unit_kind = "projected", "linear"
        axes = list(horizontal.axis_info[:2])
    else:
        # Vertical and geocentric CRS: no EPSG entry of either has an angular axis.
        kind, unit_kind = "other", "linear"
        axes = list(horizontal.axis_info)
    try:
        unit_name, factor = _unit_of(axes)
    except CrsRefused as refused:
        return None, str(refused)
    # pyproj gives an angle in radians; the panel speaks degrees.
    to_base = factor / _DEGREE_IN_RADIANS if unit_kind == "angular" else factor
    description = {
        "code": code,
        "name": crs.name,
        "kind": kind,
        "unit": {"name": unit_name, "kind": unit_kind, "toBase": to_base},
    }
    return description, None


def crs_description(code: str) -> dict[str, Any]:
    """``{"code", "name", "kind", "unit": {"name", "kind", "toBase"}}`` for an EPSG code.

    ``toBase`` is the factor to metres for a linear unit and to degrees for an angular one.
    Of a compound CRS the horizontal part counts: its cells are laid out there.
    """
    description, reason = _describe(code)
    if description is None:
        raise CrsRefused(reason or "unknown")
    return copy.deepcopy(description)
