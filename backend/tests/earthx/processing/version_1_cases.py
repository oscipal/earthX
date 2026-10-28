"""Orders of recipe version 1 as the panel sent them before NM4-43c, over synthetic COGs.

One place for the data of :mod:`test_version_1_values` and of the script that recorded the values with the core of
before: the hashes in the test are those the core of recipe version 1 wrote for these very recipes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy

from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved

WIDTH, HEIGHT = 1300, 1100
NDVI = {"op": "band_math", "op_version": 1, "params": {"expression": "(nir - red) / (nir + red)"}}
MASK = {"op": "mask", "op_version": 1, "params": {"source": "scl", "classes": [3, 8, 9, 10]}}
NORMALIZE = {
    "op": "normalize",
    "op_version": 1,
    "params": {"in_min": 0.0, "in_max": 0.5, "out_min": 0.0, "out_max": 255.0, "clip": True},
}
TWICE = {"op": "band_math", "op_version": 1, "params": {"expression": "band_math * 2 + 1"}}

#: Name → (assets of the order, steps).
CASES: dict[str, tuple[tuple[str, ...], list[dict[str, Any]]]] = {
    "mask-then-ndvi": (("red", "nir", "scl"), [MASK, NDVI]),
    "mask-then-normalize": (("red", "nir", "scl"), [MASK, NORMALIZE]),
    "normalize-then-two-expressions": (("red", "nir"), [NORMALIZE, NDVI, TWICE]),
    "ndvi-alone": (("red", "nir"), [NDVI]),
    "mask-alone": (("red", "nir", "scl"), [MASK]),
    "no-step": (("red", "nir", "scl"), []),
}


def scl_layer(width: int, height: int) -> numpy.ndarray:
    """Classes 1..11 in diagonal stripes, with a nodata (0) corner."""
    rows, cols = numpy.indices((height, width))
    data = (1 + (rows // 3 + cols // 2) % 11).astype("uint8")
    data[:4, :4] = 0
    return data


def build(root: Path) -> dict[str, Path]:
    """``red`` and ``nir`` at 10 m, ``scl`` at 20 m over the same extent."""
    return {
        "red": sources.build_band_cog(root / "red.tif", sources.ramp(WIDTH, HEIGHT, 1200)),
        "nir": sources.build_band_cog(root / "nir.tif", sources.ramp(WIDTH, HEIGHT, 3400)),
        "scl": sources.build_band_cog(
            root / "scl.tif", scl_layer(WIDTH // 2, HEIGHT // 2), scale=None, offset=None, resolution=20.0
        ),
    }


def recipe_of_version_1(case: str) -> dict[str, Any]:
    assets, steps = CASES[case]
    entries = []
    for asset in assets:
        layer = asset == "scl"
        entry = resolved(
            "ITEM_A", asset, href=sources.url(asset), scale=None if layer else 0.0001, offset=None if layer else -0.1
        )
        if layer:
            entry["bands"] = [{"data_type": "uint8", "nodata": 0, "scale": None, "offset": None}]
            entry["gsd"] = 20.0
        entries.append(entry)
    return {
        "recipe_version": 1,
        "inputs": [
            {"name": "s2", "dataset": "synthetic", "groups": [["ITEM_A"]], "assets": list(assets), "resolved": entries}
        ],
        "aoi": sources.whole(WIDTH, HEIGHT),
        "steps": steps,
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }
