#!/usr/bin/env python3
"""Cost of a raster job by number of bands, scenes and band math (NM4-43, adr/0020 §3.2).

    curl -sS -X POST https://earth-search.aws.element84.com/v1/search -H 'Content-Type: application/json' \\
      -d '{"collections":["sentinel-2-c1-l2a"],"datetime":"2026-04-01T00:00:00Z/2026-10-01T00:00:00Z",
           "limit":200,"query":{"grid:code":{"eq":"MGRS-32TPT"},"eo:cloud_cover":{"lt":80}}}' -o items.json
    PYTHONPATH=backend python scripts/nm4-43-bands/measure.py prepare <dir> --items items.json [--km 10] [--scenes 25]
    PYTHONPATH=backend python scripts/nm4-43-bands/measure.py run <dir> [--scenes 1] [--configs ...]
    PYTHONPATH=backend python scripts/nm4-43-bands/measure.py summary <dir>

The search is a plain ``curl`` for one MGRS tile (about 110 km, no one's AOI): the platform's `gateway` connects
without the HTTPS proxy a cloud session has to use, so the script takes the items from that file and
makes no request of its own for metadata. ``prepare`` keeps the whole scenes of the most frequent MGRS
tile, one per day, places a square of ``--km`` around the middle of the area all of them cover, and
builds one recipe per configuration and scene with ``api.intake.estimate_order``, the path an order
takes before it is queued. Nothing of the place is printed: no coordinates, no item ids, no address;
a failed run is recorded by the class of its error only, because GDAL's messages name addresses.

``run`` computes each recipe with ``processing.core.run`` in a child process of its own, as a worker
does, and appends one line of JSON per run to ``<dir>/results.jsonl``: wall time, peak RSS
(``ru_maxrss``), the bytes GDAL downloaded and the requests it sent (``CPL_VSIL_SHOW_NETWORK_STATS``),
the size of ``result.tif``, and the platform's own estimate of the same recipe for comparison.

Configurations: 2 bands (``red``, ``nir``), 16 (what "Select all bands" takes today: every data
asset but the mask layer ``scl``) and all 17 data assets; each without a step, with ``band_math``
as it is today (the output is the one result band) and with ``band_math_append``, a script-only
operator that keeps every input band and adds the result as one more band — the model adr/0020
proposes. It is not registered anywhere in the platform.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy
from rio_tiler.models import ImageData
from shapely.geometry import box, shape

from earthx.processing.operators import REGISTRY, RasterMeta
from earthx.processing.operators.band_math import BAND_MATH, BandMathParams

DATASET = "sentinel-2-c1-l2a"

TWO = ["red", "nir"]
#: Every GeoTIFF data asset of the collection; the auxiliary assets ``visual`` and ``preview`` are no bands (adr/0014 §15s).
ALL = [
    "coastal", "blue", "green", "red", "rededge1", "rededge2", "rededge3", "nir", "nir08", "nir09",
    "swir16", "swir22", "aot", "wvp", "scl", "cloud", "snow",
]  # fmt: skip
SIXTEEN = [band for band in ALL if band != "scl"]
BANDS = {"2": TWO, "16": SIXTEEN, "17": ALL}

EXPRESSION = "(nir-red)/(nir+red)"
APPENDED = "Band_Math_1"
STEPS = {
    "none": [],
    "bm": [{"op": "band_math", "op_version": 1, "params": {"expression": EXPRESSION}}],
    "append": [{"op": "band_math_append", "op_version": 1, "params": {"expression": EXPRESSION}}],
}
CONFIGS = [f"{bands}-{steps}" for bands in BANDS for steps in STEPS]


def _append_run(image: ImageData, params: BandMathParams) -> ImageData:
    result = BAND_MATH.run(image, params)
    data = numpy.ma.concatenate([image.array.astype("float64"), result.array.astype("float64")])
    return ImageData(data, bounds=image.bounds, crs=image.crs, band_names=[*image.band_names, APPENDED], nodata=None)


def _append_transform(meta: RasterMeta, params: BandMathParams) -> RasterMeta:
    added = BAND_MATH.transform(meta, params).bands[0]
    bands = (*meta.bands, replace(added, name=APPENDED))
    return RasterMeta(meta.crs, meta.transform, meta.width, meta.height, bands, meta.resampled)


#: Band math that adds a band instead of replacing them; only here, never in the platform.
BAND_MATH_APPEND = replace(BAND_MATH, op="band_math_append", run=_append_run, transform=_append_transform)
OPERATORS = REGISTRY.with_operators(BAND_MATH_APPEND)


# --- prepare ------------------------------------------------------------------


def _square(lon: float, lat: float, km: float) -> dict:
    half_lat = km / 2 / 111.32
    half_lon = half_lat / max(numpy.cos(numpy.radians(lat)), 0.01)
    return box(lon - half_lon, lat - half_lat, lon + half_lon, lat + half_lat).__geo_interface__


def _items(path: Path, scenes: int) -> list[dict]:
    """Whole scenes of the most frequent MGRS tile in ``path``, one per day, the clearest first."""
    found = json.loads(path.read_text())["features"]
    tiles = Counter(item["properties"].get("grid:code") for item in found)
    tile = tiles.most_common(1)[0][0]
    candidates = [item for item in found if item["properties"].get("grid:code") == tile]
    largest = max(shape(item["geometry"]).area for item in candidates)
    full = [item for item in candidates if shape(item["geometry"]).area > 0.9 * largest]
    full.sort(key=lambda item: item["properties"].get("eo:cloud_cover", 100))
    days, chosen = set(), []
    for item in full:
        day = item["properties"]["datetime"][:10]
        if day not in days:
            days.add(day)
            chosen.append(item)
        if len(chosen) == scenes:
            break
    if len(chosen) < scenes:
        raise SystemExit(f"only {len(chosen)} whole scenes of one tile found, {scenes} wanted")
    return chosen


async def _prepare(out: Path, items_path: Path, km: float, scenes: int) -> None:
    from earthx.api import intake
    from earthx.catalog.datasets import REGISTRY as DATASETS

    # The cap of 16 assets (M4-07b F5) is what is measured here, so it is lifted for this process only.
    intake.MAX_ORDER_ASSETS = len(ALL)

    items = _items(items_path, scenes)
    common = shape(items[0]["geometry"])
    for item in items[1:]:
        common = common.intersection(shape(item["geometry"]))
    centre = common.representative_point()
    aoi = _square(centre.x, centre.y, km)
    by_id = {item["id"]: item for item in items}

    async def item_source(dataset: str, item_id: str) -> dict:
        return by_id[item_id]

    out.mkdir(parents=True, exist_ok=True)
    for name in CONFIGS:
        bands, steps = name.split("-")
        for index, item in enumerate(items):
            order = {
                "recipe_version": 1,
                "inputs": [{"name": "s2", "dataset": DATASET, "groups": [[item["id"]]], "assets": BANDS[bands]}],
                "aoi": aoi,
                "steps": STEPS[steps],
                "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
            }
            estimated = await intake.estimate_order(
                json.dumps(order), registry=DATASETS, operators=OPERATORS, item_source=item_source
            )
            (out / f"{name}.{index:02d}.json").write_text(estimated.recipe.model_dump_json())
    print(json.dumps({"configs": len(CONFIGS), "scenes": len(items), "km": km}))


# --- run ----------------------------------------------------------------------


def _child(path: Path) -> None:
    """One run in this process; prints one JSON line. GDAL prints its network statistics at exit."""
    from earthx.processing.core import run as run_recipe
    from earthx.processing.core import worker_environment
    from earthx.processing.plan import disk_needed, estimate
    from earthx.processing.recipe import parse_recipe

    recipe = parse_recipe(path.read_text(), OPERATORS)
    cost = estimate(recipe, OPERATORS)
    disk = disk_needed(recipe, OPERATORS)
    baseline = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    with tempfile.TemporaryDirectory() as workdir, worker_environment():
        started = time.perf_counter()
        result = run_recipe(recipe, workdir=Path(workdir), progress=lambda done, total: None, operators=OPERATORS)
        seconds = time.perf_counter() - started
        size = result.path.stat().st_size
    print(
        json.dumps(
            {
                "seconds": round(seconds, 2),
                "rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
                "rss_baseline_mb": round(baseline / 1024, 1),
                "out_bands": len(result.meta.bands),
                "pixels": result.meta.width * result.meta.height,
                "result_mb": round(size / 1e6, 2),
                "est_seconds": round(cost.seconds, 2),
                "est_input_mb": round(cost.input_bytes / 1e6, 2),
                "est_output_mb": round(cost.output_bytes / 1e6, 2),
                "est_disk_mb": round(disk / 1e6, 1),
            }
        ),
        flush=True,
    )


def _network(text: str) -> dict:
    """GDAL's totals only; the per-file part names addresses and is dropped."""
    if not text.strip():
        return {"read_mb": None, "gets": None, "heads": None}
    methods = json.loads(text)["methods"]
    return {
        "read_mb": round(methods.get("GET", {}).get("downloaded_bytes", 0) / 1e6, 2),
        "gets": methods.get("GET", {}).get("count", 0),
        "heads": methods.get("HEAD", {}).get("count", 0),
    }


def _run(directory: Path, scenes: int, configs: list[str]) -> None:
    results = directory / "results.jsonl"
    env = {**os.environ, "CPL_VSIL_SHOW_NETWORK_STATS": "YES"}
    for name in configs:
        for index in range(scenes):
            path = directory / f"{name}.{index:02d}.json"
            child = subprocess.run(
                [sys.executable, __file__, "_child", str(path)], capture_output=True, text=True, env=env, check=False
            )
            if child.returncode != 0:
                lines = child.stderr.strip().splitlines()
                kind = lines[-1].split(":", 1)[0][:100] if lines else f"exit code {child.returncode}"
                line = {"config": name, "scene": index, "error": kind}
            else:
                # GDAL writes its statistics to stdout after the line of the run.
                own, _, network = child.stdout.partition("Network statistics:")
                measured = json.loads(own.strip().splitlines()[-1])
                line = {"config": name, "scene": index, **measured, **_network(network)}
            print(json.dumps(line), flush=True)
            with results.open("a") as file:
                file.write(json.dumps(line) + "\n")


def _summary(directory: Path) -> None:
    lines = [json.loads(line) for line in (directory / "results.jsonl").read_text().splitlines()]
    print(
        "| config | runs | out bands | s (median) | s (min–max) | s (sum) | peak RSS MB (max) | baseline MB (max) "
        "| read MB (median) | read MB (sum) | GETs (median) | result MB (median) | est. s | est. output MB "
        "| est. disk MB |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name in CONFIGS:
        runs = [line for line in lines if line["config"] == name and "error" not in line]
        errors = [line for line in lines if line["config"] == name and "error" in line]
        if errors:
            print(f"| {name} | {len(errors)} failed | {errors[0]['error']} |")
        if not runs:
            continue

        def median(key: str, runs: list[dict] = runs) -> float | None:
            values = [line[key] for line in runs if line[key] is not None]
            return round(statistics.median(values), 2) if values else None

        def total(key: str, runs: list[dict] = runs) -> float | None:
            values = [line[key] for line in runs if line[key] is not None]
            return round(sum(values), 1) if values else None

        seconds = [line["seconds"] for line in runs]
        print(
            f"| {name} | {len(runs)} | {runs[0]['out_bands']} | {median('seconds')} | "
            f"{min(seconds)}–{max(seconds)} | {total('seconds')} | {max(line['rss_mb'] for line in runs)} | "
            f"{max(line['rss_baseline_mb'] for line in runs)} | {median('read_mb')} | {total('read_mb')} | "
            f"{median('gets')} | {median('result_mb')} | {median('est_seconds')} | {median('est_output_mb')} | "
            f"{median('est_disk_mb')} |"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["prepare", "run", "summary", "_child"])
    parser.add_argument("path", type=Path)
    parser.add_argument("--items", type=Path, help="a STAC ItemCollection of the search (see the module text)")
    parser.add_argument("--km", type=float, default=10.0)
    parser.add_argument("--scenes", type=int, default=25)
    parser.add_argument("--configs", nargs="+", default=CONFIGS, choices=CONFIGS)
    args = parser.parse_args()
    if args.mode == "prepare":
        if args.items is None:
            parser.error("prepare needs --items")
        asyncio.run(_prepare(args.path, args.items, args.km, args.scenes))
    elif args.mode == "run":
        _run(args.path, args.scenes, args.configs)
    elif args.mode == "summary":
        _summary(args.path)
    else:
        _child(args.path)


if __name__ == "__main__":
    main()
