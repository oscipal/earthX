"""Synthetic orders and recipes for the processing tests, as plain JSON data.

Every value is invented: the host is reserved (``.invalid``), the AOI is a small
synthetic square, and nothing here names a real item.
"""

from __future__ import annotations

import copy
from typing import Any, Literal

HOST = "store.example.invalid"

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[9.0, 47.0], [9.01, 47.0], [9.01, 47.01], [9.0, 47.01], [9.0, 47.0]]],
}


def resolved(
    item: str,
    asset: str,
    *,
    reader: Literal["cog", "zarr"] = "cog",
    scale: float | None = 0.0001,
    offset: float | None = -0.1,
    version: dict[str, str] | None = None,
    href: str | None = None,
    variable: str | None = None,
) -> dict[str, Any]:
    scaled = scale is not None or offset is not None
    return {
        "asset": {
            "dataset_id": "synthetic",
            "item_id": item,
            "asset": asset,
            "reader": reader,
            "href": href or f"https://{HOST}/{item}/{asset}.tif",
            "variable": variable,
            "crs": "EPSG:32632",
        },
        "version": version if version is not None else {"kind": "file:checksum", "value": f"1220{item}{asset}"},
        "bands": [{"data_type": "uint16", "nodata": 0, "scale": scale, "offset": offset}],
        "scaling": "item" if scaled else ("store-cf" if reader == "zarr" else "none"),
        "gsd": 10.0,
    }


def recipe_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "recipe_version": 1,
        "inputs": [
            {
                "name": "s2",
                "dataset": "synthetic",
                "groups": [["ITEM_A"]],
                "assets": ["red", "nir"],
                "resolved": [resolved("ITEM_A", "red"), resolved("ITEM_A", "nir")],
            }
        ],
        "aoi": copy.deepcopy(SQUARE),
        "steps": [{"op": "scale", "op_version": 1, "params": {"factor": 2.0}}],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }
    data.update(overrides)
    return data


def request_data() -> dict[str, Any]:
    data = recipe_data()
    for entry in data["inputs"]:
        del entry["resolved"]
    return data


CROP = {
    "kind": "crop",
    "format": "cog",
    "resolution_factor": 1,
    "extent": "bbox(aoi ∩ footprints)",
    "mask": "file",
}


def crop_data(groups: list[list[str]] | None = None, assets: tuple[str, ...] = ("visual",)) -> dict[str, Any]:
    """An export recipe (M4-11a): the crop output, no steps, a footprint per item (the AOI's square)."""
    groups = copy.deepcopy(groups or [["ITEM_A"]])
    items = [item for group in groups for item in group]
    return recipe_data(
        inputs=[
            {
                "name": "input",
                "dataset": "synthetic",
                "groups": groups,
                "assets": list(assets),
                "resolved": [
                    resolved(item, asset, scale=None, offset=None) for item in items for asset in assets
                ],
                "footprints": {item: copy.deepcopy(SQUARE) for item in items},
            }
        ],
        steps=[],
        output=dict(CROP),
    )
