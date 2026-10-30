"""Synthetic recipe files and a registry for the runner's tests.

Every value is invented: the host is reserved (``.invalid``), the scenes are the ramps of
`tests/earthx/processing/sources.py` and the CF store of `mini_zarr_cf`, the AOIs lie
on their synthetic ground. The registry is a copy of a real entry with only its id and
``asset_hosts`` replaced, as in `tests/catalog/synthetic_chain.py`.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.registry import DatasetRegistry
from earthx.processing.methods import recipe_with_methods
from earthx.processing.recipe import engine_versions, job_recipe_document
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved
from tests.earthx.readers import mini_zarr_cf

HOST = sources.HOST
WIDTH, HEIGHT = 1300, 1100
ATTRIBUTION = ["Synthetic data, no source"]

#: R5 only (adr/0014 §15c): `where`, `sqrt`, arithmetic, comparisons.
EXPRESSION = "where(nir > red, sqrt(nir - red), 0) / (nir + red)"


def registry() -> DatasetRegistry:
    """One entry ``synthetic`` whose assets lie on the fixtures' host."""
    synthetic = replace(
        SENTINEL_2_L2A, dataset_id="synthetic", source=replace(SENTINEL_2_L2A.source, asset_hosts=(HOST,))
    )
    return DatasetRegistry((synthetic,))


def band_math_recipe(expression: str = EXPRESSION) -> dict[str, Any]:
    """Band math over two scaled COG bands, across a block border."""
    entries = [resolved("ITEM_A", asset, href=sources.url(asset)) for asset in ("red", "nir")]
    return {
        "recipe_version": 1,
        "inputs": [
            {
                "name": "s2",
                "dataset": "synthetic",
                "groups": [["ITEM_A"]],
                "assets": ["red", "nir"],
                "resolved": entries,
            }
        ],
        "aoi": sources.whole(WIDTH, HEIGHT),
        "steps": [{"op": "band_math", "op_version": 1, "params": {"expression": expression}}],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
        "recipe_id": "A" * 22,
    }


def band_math_recipe_v2(expression: str = EXPRESSION, name: str = "Index") -> dict[str, Any]:
    """The same recipe as :func:`band_math_recipe`, written as recipe version 2: a named result and ``output.bands``."""
    recipe = band_math_recipe(expression)
    recipe["recipe_version"] = 2
    recipe["steps"] = [{"op": "band_math", "op_version": 2, "params": {"expression": expression, "name": name}}]
    recipe["output"] = {**recipe["output"], "bands": [name]}
    return recipe


NORMALIZE_METHODS: dict[str, dict[str, Any]] = {
    "linear": {"method": "linear", "bands": ["red", "nir"], "in_min": 0.0, "in_max": 0.5, "out_min": 0.0, "out_max": 255.0, "clip": True},
    "percentile": {
        "method": "percentile",
        "bands": ["red", "nir"],
        "low": 2,
        "high": 98,
        "out_min": 0.0,
        "out_max": 1.0,
        "clip": True,
        "measured": {"factor": 1, "bands": {"red": {"p_low": 0.12, "p_high": 0.3}, "nir": {"p_low": 0.35, "p_high": 0.5}}},
    },
    "zscore": {
        "method": "zscore",
        "bands": ["red", "nir"],
        "measured": {"factor": 1, "bands": {"red": {"mean": 0.2, "stddev": 0.05}, "nir": {"mean": 0.4, "stddev": 0.08}}},
    },
    "robust": {
        "method": "robust",
        "bands": ["red", "nir"],
        "measured": {
            "factor": 3,
            "bands": {"red": {"p25": 0.15, "median": 0.2, "p75": 0.25}, "nir": {"p25": 0.35, "median": 0.4, "p75": 0.46}},
        },
    },
}


def normalize_recipe(method: str = "percentile", params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Version 3 of ``normalize`` over two scaled COG bands (NM4-11): the numbers of the method stand in the recipe."""
    recipe = band_math_recipe()
    recipe["recipe_version"] = 2
    recipe["steps"] = [{"op": "normalize", "op_version": 3, "params": params or NORMALIZE_METHODS[method]}]
    recipe["output"] = {**recipe["output"], "bands": ["red", "nir"]}
    return recipe


def reproject_recipe(resampling: str = "bilinear") -> dict[str, Any]:
    """A reprojection of one band of the CF store, decoded by the store's own attributes."""
    key = "r10m:b04"
    entry = resolved("ITEM_Z", key, reader="zarr", scale=None, offset=None, href=mini_zarr_cf.GROUP_URL, variable="b04")
    params = {"crs": "EPSG:3035", "resolution": 10.0, "resampling": resampling}
    return {
        "recipe_version": 1,
        "inputs": [{"name": "z", "dataset": "synthetic", "groups": [["ITEM_Z"]], "assets": [key], "resolved": [entry]}],
        "aoi": sources.whole(mini_zarr_cf.SIZE, mini_zarr_cf.SIZE),
        "steps": [{"op": "reproject", "op_version": 3, "params": params}],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
        "recipe_id": "B" * 22,
    }


def recipe_file(recipe: dict[str, Any], *, engine: dict[str, str] | None = None, methods: bool = True) -> bytes:
    """``recipe.json`` as `api` serves it for a job: the recipe and the provenance of the cloud run, with its methods text.

    ``methods=False`` for a recipe that is none (the text is written from a valid one only): a hand-made file.
    """
    document = job_recipe_document(
        recipe,
        attribution=ATTRIBUTION,
        result={"engine": engine if engine is not None else engine_versions(), "scaling": []},
        started=datetime(2026, 10, 20, 8, 0, tzinfo=UTC),
        finished=datetime(2026, 10, 20, 8, 1, tzinfo=UTC),
    )
    return recipe_with_methods(document) if methods else document
