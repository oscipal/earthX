"""Recipes of version 1 over a mosaic and with integer output, as the core of before NM4-43c ran them.

The scenes and the geometry are those of :mod:`test_mosaic` (two UTM zones, ``uint16``); the hashes in
:mod:`test_version_1_mosaic` are those the core of recipe version 1 wrote for these very recipes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.earthx.processing import test_mosaic as mosaic

BAND_MATH = {"op": "band_math", "op_version": 1, "params": {"expression": "red * 2"}}

#: Name → (items of the one group, steps, scaled by the item, output type).
CASES: dict[str, tuple[list[str], list[dict[str, Any]], bool, str]] = {
    "mosaic-scaled": (["A", "B", "C"], [], True, "float32"),
    "mosaic-band-math": (["A", "B", "C"], [BAND_MATH], True, "float32"),
    "mosaic-uint16": (["A", "B", "C"], [], False, "uint16"),
    "scene-uint16": (["A"], [], False, "uint16"),
}


def build_scenes(root: Path, *, scaled: bool) -> dict[str, Path]:
    """The scenes with the scale and offset of the item in the file, or without (a file that carries a scaling nobody declares is refused)."""
    scale = mosaic.sources.SCALE if scaled else None
    return {item: mosaic._cog(root / f"{item}.tif", item, scale=scale) for item in "ABC"}


def recipe_of_version_1(case: str) -> dict[str, Any]:
    items, steps, scaled, dtype = CASES[case]
    data = mosaic._recipe(items, steps=steps, scale=mosaic.sources.SCALE if scaled else None)
    data["output"]["dtype"] = dtype
    return data
