#!/usr/bin/env python3
"""What an exact measure of ``normalize`` costs in the job, and how far the preview's coarser one lies off (NM4-71).

    curl -sS -X POST https://earth-search.aws.element84.com/v1/search -H 'Content-Type: application/json' \\
      -d '{"collections":["sentinel-2-c1-l2a"],"datetime":"2025-08-01T00:00:00Z/2025-09-01T00:00:00Z",
           "limit":100,"query":{"grid:code":{"eq":"MGRS-32UPU"},"eo:cloud_cover":{"lt":5}}}' -o items.json
    PYTHONPATH=backend python -W ignore scripts/nm4-71-normalize/measure.py prepare <dir> --items items.json
    PYTHONPATH=backend python -W ignore scripts/nm4-71-normalize/measure.py run <dir> [--cases ...] [--variants ...]
    PYTHONPATH=backend python -W ignore scripts/nm4-71-normalize/measure.py summary <dir>

``prepare`` takes the clearest whole scene of the file (no nodata) and builds the orders with
``api.intake.estimate_order``, the path an order takes before it is queued: the whole scene (no AOI, the union of
the footprints) and squares of 20, 41 and 82 km around its middle (2048², 4096², 8192² at 10 m). Nothing of the
place is printed: no coordinates, no item id, no address.

Cases: ``<area>-1`` normalizes ``red``, ``<area>-4`` normalizes ``blue``, ``green``, ``red``, ``nir``, each as a
percentile stretch 2–98 % onto 0–1 (the numbers in the recipe are placeholders; the cost does not depend on them).
``<area>-idx`` is the start of a chain with NDVI (``band_math``) beside five bands, for the deviation of the preview.

Variants, each in a child process of its own (cold, as a worker): ``job`` today's run with the numbers in the recipe
(``processing.core.run``); ``exact`` the measure of the start of the chain on the job's own grid
(``core.area_statistics`` without a limit, what option (b) runs in ``api`` and option (a) as a pass of its own reads);
``preview`` the same with today's limit of 2048² (the route of NM4-19); ``workfile`` a prototype of option (a): the
steps before ``normalize`` into a ``float64`` work file while counting the bands of the step over the AOI, the exact
percentiles refined from that file, then the rest of the chain from it; ``truth`` every valid value of the area held
and sorted, for the error of the histogram; ``disk`` the real run of ``normalize`` version 4 (cases ``<area>-v4-1``, ``<area>-v4-4``)
with the highest level of its work directory against ``disk_needed``. One JSON line per run: seconds (per phase), peak RSS (``ru_maxrss``), the
bytes GDAL downloaded (``CPL_VSIL_SHOW_NETWORK_STATS``) and the measured numbers. ``NM4_71_WORK_COMPRESS=none``
writes the work file of ``workfile`` without compression (the job's files are deflate).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import resource
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path

import numpy
from shapely.geometry import box, shape

from earthx.processing.operators import REGISTRY

DATASET = "sentinel-2-c1-l2a"
AREAS = {"whole": None, "s20": 20.48, "s41": 40.96, "s82": 81.92}
ONE = ["red"]
FOUR = ["blue", "green", "red", "nir"]
INDEX_BANDS = ["blue", "green", "red", "nir", "swir16", "NDVI"]
NDVI = {"op": "band_math", "op_version": 2, "params": {"expression": "(nir-red)/(nir+red)", "name": "NDVI"}}
VARIANTS = ("job", "exact", "preview", "workfile", "truth", "disk")
#: What a case of cost (``<area>-1``, ``<area>-4``) and a case of deviation (``<area>-idx``) run.
_COST_VARIANTS = ("job", "exact", "workfile")
_INDEX_VARIANTS = ("exact", "preview", "truth")
_V4_VARIANTS = ("disk",)
PERCENTS = (2, 25, 50, 75, 98)
UNLIMITED = 10**12


def _normalize_v4(bands: list[str]) -> dict:
    """The step as the panel sends it since NM4-71: version 4, no numbers; the job measures them."""
    step = _normalize(bands)
    params = {key: value for key, value in step["params"].items() if key != "measured"}
    return {**step, "op_version": 4, "params": params}


def _normalize(bands: list[str]) -> dict:
    return {
        "op": "normalize",
        "op_version": 3,
        "params": {
            "method": "percentile",
            "bands": bands,
            "low": 2,
            "high": 98,
            "out_min": 0,
            "out_max": 1,
            "clip": True,
            "measured": {"factor": 1, "bands": {name: {"p_low": 0.0, "p_high": 0.3} for name in bands}},
        },
    }


def _cases() -> dict[str, tuple[str | None, list[dict], list[str]]]:
    cases: dict[str, tuple[str | None, list[dict], list[str]]] = {}
    for area in AREAS:
        cases[f"{area}-1"] = (area, [_normalize(ONE)], ONE)
        cases[f"{area}-4"] = (area, [_normalize(FOUR)], FOUR)
        cases[f"{area}-idx"] = (area, [NDVI], INDEX_BANDS)
        cases[f"{area}-v4-1"] = (area, [_normalize_v4(ONE)], ONE)
        cases[f"{area}-v4-4"] = (area, [_normalize_v4(FOUR)], FOUR)
    return cases


CASES = _cases()


# --- prepare ------------------------------------------------------------------


def _square(lon: float, lat: float, km: float) -> dict:
    half_lat = km / 2 / 111.32
    half_lon = half_lat / max(numpy.cos(numpy.radians(lat)), 0.01)
    return box(lon - half_lon, lat - half_lat, lon + half_lon, lat + half_lat).__geo_interface__


async def _prepare(out: Path, items_path: Path) -> None:
    from earthx.api import intake
    from earthx.catalog.datasets import REGISTRY as DATASETS

    found = json.loads(items_path.read_text())["features"]
    whole = [item for item in found if item["properties"].get("s2:nodata_pixel_percentage", 100) < 0.01]
    if not whole:
        raise SystemExit("no whole scene in the file")
    item = min(whole, key=lambda item: item["properties"].get("eo:cloud_cover", 100))
    centre = shape(item["geometry"]).representative_point()

    async def item_source(dataset: str, item_id: str) -> dict:
        return item

    out.mkdir(parents=True, exist_ok=True)
    for name, (area, steps, bands) in CASES.items():
        km = AREAS[area]
        order = {
            "recipe_version": 2,
            "inputs": [{"name": "s2", "dataset": DATASET, "groups": [[item["id"]]]}],
            **({} if km is None else {"aoi": _square(centre.x, centre.y, km)}),
            "steps": steps,
            "output": {"kind": "raster", "format": "cog", "dtype": "float32", "bands": bands},
        }
        estimated = await intake.estimate_order(
            json.dumps(order), registry=DATASETS, operators=REGISTRY, item_source=item_source
        )
        (out / f"{name}.json").write_text(estimated.recipe.model_dump_json())
    print(json.dumps({"cases": len(CASES)}))


# --- the variants -------------------------------------------------------------


def _prefix(recipe):
    """The start of the chain before ``normalize``, its bands as output in ``float64``: what the panel measures."""
    steps = list(recipe.steps)
    position = next((i for i, step in enumerate(steps) if step.op == "normalize"), len(steps))
    bands = steps[position].params["bands"] if position < len(steps) else list(recipe.output.bands)
    output = recipe.output.model_copy(update={"bands": bands, "dtype": "float64"})
    return recipe.model_copy(update={"steps": steps[:position], "output": output})


def _numbers(bands: list[dict]) -> dict:
    keys = ("minimum", "maximum", "mean", "stddev", "count", *(f"percentile_{p}" for p in PERCENTS))
    return {band["name"]: {key: band["statistics"].get(key) for key in keys} for band in bands}


def _area(recipe, max_pixels: int) -> dict:
    import rasterio

    from earthx.processing import core
    from earthx.processing.statistics import MEASURE_PERCENTILES
    from earthx.readers import process_gdal_options

    with rasterio.Env(**process_gdal_options()):
        started = time.perf_counter()
        measured = core.area_statistics(_prefix(recipe), max_pixels=max_pixels, extra_percentiles=MEASURE_PERCENTILES)
        seconds = time.perf_counter() - started
    return {
        "seconds": round(seconds, 2),
        "factor": measured.factor,
        "pixels_read": measured.pixels_read,
        "numbers": _numbers(measured.bands),
    }


def _job(recipe, workdir: Path) -> dict:
    from earthx.processing.core import run

    started = time.perf_counter()
    result = run(recipe, workdir=workdir, progress=lambda done, total: None, operators=REGISTRY)
    return {
        "seconds": round(time.perf_counter() - started, 2),
        "pixels": result.meta.width * result.meta.height,
        "result_mb": round(result.path.stat().st_size / 1e6, 2),
    }


def _exact_percentile(values: numpy.ndarray, percent: int) -> float:
    """The nearest rank of ``values`` (one dimension), as the histogram counts it."""
    rank = max(1, -(-percent * values.size // 100))
    return float(numpy.partition(values, rank - 1)[rank - 1])


def _refine(path: Path, indices: list[int], coarse: list, inside_path: Path, percents: tuple[int, ...]) -> list[dict]:
    """The exact float32 percentiles from the work file: a second histogram of the low 16 bits inside the target bin."""
    import rasterio

    from earthx.processing import statistics as stats

    targets = []
    for statistics in coarse:
        cumulative = numpy.cumsum(statistics._histogram)
        wanted = {}
        for percent in percents:
            rank = max(1, -(-percent * statistics.count // 100))
            index = int(numpy.searchsorted(cumulative, rank))
            before = int(cumulative[index - 1]) if index else 0
            wanted[percent] = (index, rank - before)
        targets.append(wanted)
    fine = [{p: numpy.zeros(1 << 16, dtype=numpy.int64) for p in percents} for _ in indices]
    with rasterio.open(path) as src, rasterio.open(inside_path) as mask:
        for _, window in src.block_windows(1):
            inside = mask.read(1, window=window) == 1
            for slot, band in enumerate(indices):
                values = src.read(band + 1, window=window)
                values = values[inside & numpy.isfinite(values)].astype(numpy.float32)
                keys = stats._float_keys(values)
                pattern = values.view(numpy.uint32)
                flip = (values.view(numpy.int32) >> 31).view(numpy.uint32) | stats._SIGN32
                low = ((pattern ^ flip) & numpy.uint32(0xFFFF)).astype(numpy.intp)
                for percent, (index, _) in targets[slot].items():
                    hit = keys == index
                    if hit.any():
                        fine[slot][percent] += numpy.bincount(low[hit], minlength=1 << 16)
    result = []
    for slot in range(len(indices)):
        exact = {}
        for percent, (index, within) in targets[slot].items():
            low = int(numpy.searchsorted(numpy.cumsum(fine[slot][percent]), within))
            exact[f"percentile_{percent}"] = float(stats._unkey((index << 16) | low))
        result.append(exact)
    return result


def _workfile(recipe, workdir: Path) -> dict:
    """Option (a) as a prototype: count while the steps before ``normalize`` are written, then the rest from the file."""
    import rasterio
    from rio_cogeo.cogeo import cog_translate
    from rio_cogeo.profiles import cog_profiles

    from earthx.processing import core
    from earthx.processing.operators.normalize import BandValues, Measured
    from earthx.processing.plan import Segment, crop_window, plan_steps, stock_steps
    from earthx.processing.statistics import MEASURE_PERCENTILES, BandStatistics
    from earthx.processing.workfile import open_workfile, workfile_path
    from earthx.readers import process_gdal_options

    if os.environ.get("NM4_71_WORK_COMPRESS") == "none":
        profile = core._profile

        def plain_work_file(meta, dtype, nodata, interleave=None):
            # Only the work file between the passes (stored band by band); the last pass stays as the job writes it.
            found = profile(meta, dtype, nodata, interleave)
            return {k: v for k, v in found.items() if k != "compress"} if interleave == "band" else found

        core._profile = plain_work_file
    phases: dict[str, float] = {}
    output = recipe.output
    planned = plan_steps(recipe.steps, REGISTRY)
    state = core._Run(workdir, lambda done, total: None)
    aoi = recipe.aoi.model_dump(mode="json")
    with ExitStack() as stack:
        stack.enter_context(rasterio.Env(**process_gdal_options()))
        started = time.perf_counter()
        sources = core._open_sources(recipe, stack)
        finest, _ = core.common_grid(sources)
        window, transform = crop_window(aoi, finest.crs.to_string(), finest.transform, finest.width, finest.height)
        meta0 = core._source_meta(sources, finest, window, transform)
        steps = stock_steps(meta0, planned, output.bands)
        cut = next(i for i, step in enumerate(steps) if step.operator.op == "normalize")
        before, after = tuple(steps[:cut]), list(steps[cut:])
        step = after[0]
        meta1 = core._transform_meta(meta0, before)
        meta2 = core._transform_meta(meta1, tuple(after))
        core._write_mask(state, meta2, aoi)
        phases["open_and_mask"] = time.perf_counter() - started

        names = [band.name for band in meta1.bands]
        indices = [names.index(name) for name in step.params.bands]
        counted = [BandStatistics("float64") for _ in indices]
        inside_pixels = 0
        mask = stack.enter_context(open_workfile(workdir, core.MASK_NAME))

        def block(w):
            nonlocal inside_pixels
            data = core._pixel_kernels(core._read_block(sources, finest.transform, window, w), before).array
            inside = mask.read(1, window=w) == 1
            inside_pixels += int(inside.sum())
            values = numpy.ma.getdata(data)
            valid = ~numpy.ma.getmaskarray(data)
            for slot, band in enumerate(indices):
                counted[slot].add(values[band][valid[band] & inside].astype("float64"))
            return data

        started = time.perf_counter()
        state.write_pass("pass-0.tif", meta1, "float64", float("nan"), block, False)
        phases["pass_count_and_write"] = time.perf_counter() - started
        summaries = [s.summary(max(inside_pixels, 1), MEASURE_PERCENTILES) for s in counted]

        started = time.perf_counter()
        refined = _refine(
            workfile_path(workdir, "pass-0.tif"), indices, counted, workfile_path(workdir, core.MASK_NAME), PERCENTS
        )
        phases["refine"] = time.perf_counter() - started
        work_mb = workfile_path(workdir, "pass-0.tif").stat().st_size / 1e6

        measured = Measured(
            factor=1,
            bands={
                name: BandValues(p_low=float(summary["percentile_2"]), p_high=float(summary["percentile_98"]))
                for name, summary in zip(step.params.bands, summaries, strict=True)
            },
        )
        after[0] = replace(step, params=step.params.model_copy(update={"measured": measured}))
        started = time.perf_counter()
        applied = core._run_pass(
            state,
            Segment("pixel", tuple(after)),
            None,
            finest.transform,
            "pass-0.tif",
            window,
            meta1,
            meta2,
            output,
            True,
        )
        phases["pass_apply"] = time.perf_counter() - started
        started = time.perf_counter()
        result = state.new_file(core.RESULT_NAME)
        with open_workfile(workdir, applied) as plain:
            cog_translate(
                plain,
                str(workfile_path(workdir, result)),
                cog_profiles.get("deflate"),
                in_memory=False,
                quiet=True,
                forward_band_tags=True,
            )
        phases["cog"] = time.perf_counter() - started
    return {
        "seconds": round(sum(phases.values()), 2),
        "phases": {key: round(value, 2) for key, value in phases.items()},
        "work_mb": round(work_mb, 1),
        "pixels": meta2.width * meta2.height,
        "numbers": {
            name: {**{k: s.get(k) for k in ("percentile_2", "percentile_98")}, "refined": r}
            for name, s, r in zip(step.params.bands, summaries, refined, strict=True)
        },
    }


def _truth(recipe) -> dict:
    """Every valid value of the area on the job's grid, held and sorted: the exact nearest-rank percentiles."""
    import rasterio
    from rasterio.warp import transform_geom

    from earthx.processing import core
    from earthx.processing.plan import crop_window, plan_steps, stock_steps
    from earthx.readers import process_gdal_options

    prefix = _prefix(recipe)
    planned = plan_steps(prefix.steps, REGISTRY)
    aoi = prefix.aoi.model_dump(mode="json")
    started = time.perf_counter()
    with ExitStack() as stack:
        stack.enter_context(rasterio.Env(**process_gdal_options()))
        sources = core._open_sources(prefix, stack)
        finest, _ = core.common_grid(sources)
        window, transform = crop_window(aoi, finest.crs.to_string(), finest.transform, finest.width, finest.height)
        meta0 = core._source_meta(sources, finest, window, transform)
        steps = tuple(stock_steps(meta0, planned, prefix.output.bands))
        meta = core._transform_meta(meta0, steps)
        geometry = transform_geom("EPSG:4326", meta.crs, aoi)
        parts: list[list[numpy.ndarray]] = [[] for _ in meta.bands]
        for block in core._blocks(meta.width, meta.height):
            data = core._pixel_kernels(core._read_block(sources, finest.transform, window, block), steps).array
            inside = core._mask_block(geometry, block, meta.transform) == 1
            values = numpy.ma.getdata(data)
            valid = ~numpy.ma.getmaskarray(data)
            for index in range(len(meta.bands)):
                chosen = values[index][valid[index] & inside & numpy.isfinite(values[index])]
                parts[index].append(chosen.astype(numpy.float32))
    numbers = {}
    for band, chunks in zip(meta.bands, parts, strict=True):
        values = numpy.concatenate(chunks)
        numbers[band.name] = {f"percentile_{p}": _exact_percentile(values, p) for p in PERCENTS}
        numbers[band.name]["count"] = int(values.size)
        del values
    return {"seconds": round(time.perf_counter() - started, 2), "numbers": numbers}


def _disk(recipe, workdir: Path) -> dict:
    """The real run of version 4 with the highest level of the work directory, sampled in ``progress`` and by a thread."""
    import threading

    from earthx.processing.core import run
    from earthx.processing.plan import disk_needed

    peak = 0

    def level() -> None:
        nonlocal peak
        size = 0
        for entry in os.scandir(workdir):
            try:
                size += entry.stat().st_size
            except FileNotFoundError:
                pass
        peak = max(peak, size)

    done = threading.Event()

    def sample() -> None:
        while not done.wait(0.2):
            level()

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    started = time.perf_counter()
    try:
        result = run(recipe, workdir=workdir, progress=lambda done_blocks, total: level(), operators=REGISTRY)
    finally:
        done.set()
        sampler.join()
    seconds = time.perf_counter() - started
    level()
    return {
        "seconds": round(seconds, 2),
        "pixels": result.meta.width * result.meta.height,
        "peak_disk_mb": round(peak / 1e6, 1),
        "disk_needed_mb": round(disk_needed(recipe, REGISTRY) / 1e6, 1),
        "result_mb": round(result.path.stat().st_size / 1e6, 2),
        "measured": result.properties.get("earthx:normalize"),
    }


def _child(path: Path, variant: str) -> None:
    from earthx.processing.core import worker_environment
    from earthx.processing.recipe import parse_recipe

    recipe = parse_recipe(path.read_text(), REGISTRY)
    with tempfile.TemporaryDirectory(dir=os.environ.get("NM4_71_WORKDIR")) as workdir, worker_environment():
        if variant == "job":
            line = _job(recipe, Path(workdir))
        elif variant == "exact":
            line = _area(recipe, UNLIMITED)
        elif variant == "preview":
            from earthx.processing.core import MAX_AREA_PIXELS

            line = _area(recipe, MAX_AREA_PIXELS)
        elif variant == "workfile":
            line = _workfile(recipe, Path(workdir))
        elif variant == "disk":
            line = _disk(recipe, Path(workdir))
        else:
            line = _truth(recipe)
    line["rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    print(json.dumps(line), flush=True)


# --- run and summary ------------------------------------------------------------


def _network(text: str) -> dict:
    """GDAL's totals only; the per-file part names addresses and is dropped."""
    if not text.strip():
        return {"read_mb": None, "gets": None}
    methods = json.loads(text)["methods"]
    return {
        "read_mb": round(methods.get("GET", {}).get("downloaded_bytes", 0) / 1e6, 1),
        "gets": methods.get("GET", {}).get("count", 0),
    }


def _run(directory: Path, cases: list[str], variants: list[str]) -> None:
    results = directory / "results.jsonl"
    env = {**os.environ, "CPL_VSIL_SHOW_NETWORK_STATS": "YES"}
    for name in cases:
        for variant in variants:
            if name.endswith("-idx"):
                wanted = _INDEX_VARIANTS
            else:
                wanted = _V4_VARIANTS if "-v4-" in name else _COST_VARIANTS
            if variant not in wanted:
                continue
            child = subprocess.run(
                [sys.executable, "-W", "ignore", __file__, "_child", str(directory / f"{name}.json"), variant],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            if child.returncode != 0:
                lines = child.stderr.strip().splitlines()
                kind = lines[-1].split(":", 1)[0][:100] if lines else f"exit code {child.returncode}"
                line = {"case": name, "variant": variant, "error": kind}
            else:
                own, _, network = child.stdout.partition("Network statistics:")
                line = {
                    "case": name,
                    "variant": variant,
                    **json.loads(own.strip().splitlines()[-1]),
                    **_network(network),
                }
            print(json.dumps({k: v for k, v in line.items() if k != "numbers"}), flush=True)
            with results.open("a") as file:
                file.write(json.dumps(line) + "\n")


def _summary(directory: Path) -> None:
    lines = [json.loads(line) for line in (directory / "results.jsonl").read_text().splitlines()]
    print("| case | variant | s | phases | peak RSS MB | read MB | GETs | factor | work file MB |")
    print("|---|---|---|---|---|---|---|---|---|")
    for line in lines:
        if "error" in line:
            print(f"| {line['case']} | {line['variant']} | failed: {line['error']} |")
            continue
        phases = ", ".join(f"{k} {v}" for k, v in line.get("phases", {}).items())
        print(
            f"| {line['case']} | {line['variant']} | {line['seconds']} | {phases} | {line['rss_mb']} | "
            f"{line.get('read_mb')} | {line.get('gets')} | {line.get('factor', '')} | {line.get('work_mb', '')} |"
        )
    print()
    print("Deviation of the preview from the exact measure, in % of the exact span (p98 - p2; IQR; stddev):")
    print("| area | band | factor | p2 | p98 | p25 | median | p75 | mean | stddev |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    by = {(line["case"], line["variant"]): line for line in lines if "error" not in line}
    for area in AREAS:
        exact, preview = by.get((f"{area}-idx", "exact")), by.get((f"{area}-idx", "preview"))
        if not exact or not preview:
            continue
        for band, e in exact["numbers"].items():
            p = preview["numbers"][band]
            span = e["percentile_98"] - e["percentile_2"]
            iqr = e["percentile_75"] - e["percentile_25"]

            def off(key: str, scale: float, e=e, p=p) -> str:
                return f"{100 * abs(p[key] - e[key]) / scale:.2f}" if scale else "–"

            print(
                f"| {area} | {band} | {preview['factor']} | {off('percentile_2', span)} | {off('percentile_98', span)} "
                f"| {off('percentile_25', iqr)} | {off('percentile_50', iqr)} | {off('percentile_75', iqr)} "
                f"| {off('mean', e['stddev'])} | {off('stddev', e['stddev'])} |"
            )
    print()
    print("Error of the histogram (exact of the job) against the sorted values, in % of the exact span:")
    print("| area | band | values | p2 | p25 | median | p75 | p98 |")
    print("|---|---|---|---|---|---|---|---|")
    for area in AREAS:
        exact, truth = by.get((f"{area}-idx", "exact")), by.get((f"{area}-idx", "truth"))
        if not exact or not truth:
            continue
        for band, t in truth["numbers"].items():
            e = exact["numbers"][band]
            span = t["percentile_98"] - t["percentile_2"]
            cells = " | ".join(
                f"{100 * abs(e[f'percentile_{p}'] - t[f'percentile_{p}']) / span:.3f}" if span else "–"
                for p in PERCENTS
            )
            print(f"| {area} | {band} | {t['count']} | {cells} |")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["prepare", "run", "summary", "_child"])
    parser.add_argument("path", type=Path)
    parser.add_argument("variant", nargs="?", choices=VARIANTS)
    parser.add_argument("--items", type=Path, help="a STAC ItemCollection of the search (see the module text)")
    parser.add_argument("--cases", nargs="+", default=list(CASES), choices=list(CASES))
    parser.add_argument("--variants", nargs="+", default=list(VARIANTS), choices=VARIANTS)
    args = parser.parse_args()
    if args.mode == "prepare":
        if args.items is None:
            parser.error("prepare needs --items")
        asyncio.run(_prepare(args.path, args.items))
    elif args.mode == "run":
        _run(args.path, args.cases, args.variants)
    elif args.mode == "summary":
        _summary(args.path)
    else:
        _child(args.path, args.variant)


if __name__ == "__main__":
    main()
