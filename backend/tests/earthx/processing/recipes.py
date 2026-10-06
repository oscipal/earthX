"""Synthetic orders and recipes for the processing tests, as plain JSON data.

Every value is invented: the host is reserved (``.invalid``), the AOI is a small
synthetic square, and nothing here names a real item.
"""

from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

HOST = "store.example.invalid"


class ScaleParams(BaseModel):
    """Parameters of the test operators: one float and one optional label."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    factor: float
    label: str | None = None


class FakeOperators:
    """The lookup :func:`earthx.processing.recipe.parse_recipe` needs, with one operator."""

    def params_model(self, op: str, op_version: int) -> type[BaseModel]:
        if (op, op_version) == ("scale", 1):
            return ScaleParams
        raise LookupError(op)


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
