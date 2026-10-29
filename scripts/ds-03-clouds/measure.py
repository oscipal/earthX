#!/usr/bin/env python3
"""Cost and accuracy of the cloud share in an AOI from Sentinel-2's scene classification (DS-03 plan §6.2, §6.16).

One-time network step, metadata only. The script makes no request of its own for it: the platform's `gateway`
connects without the HTTPS proxy a cloud session has to use, so the search answers are saved first with ``curl``.
Six boxes of one degree (no one's AOI), each over a season, and seven small boxes over the year 2024 for the counts:

    mkdir -p <dir>/searches <dir>/counts
    search() {  # name, bbox, datetime, limit, file
      curl -sS -X POST https://earth-search.aws.element84.com/v1/search -H 'Content-Type: application/json' \\
        -d "{\\"collections\\":[\\"sentinel-2-c1-l2a\\"],\\"bbox\\":[$2],\\"datetime\\":\\"$3\\",\\"limit\\":$4}" -o "$5"
    }
    search alps   10,47,11,48     2024-06-01T00:00:00Z/2024-07-31T23:59:59Z 200 <dir>/searches/alps.json
    search amazon -60,-10,-59,-9  2025-01-01T00:00:00Z/2025-03-31T23:59:59Z 200 <dir>/searches/amazon.json
    search sahara 5,25,6,26       2024-04-01T00:00:00Z/2024-06-30T23:59:59Z 200 <dir>/searches/sahara.json
    search norway 10,61,11,62     2024-02-15T00:00:00Z/2024-04-15T23:59:59Z 200 <dir>/searches/norway.json
    search coast  -9.5,38,-8.5,39 2024-10-01T00:00:00Z/2024-12-31T23:59:59Z 200 <dir>/searches/coast.json
    search ganges 85,25,86,26     2024-07-01T00:00:00Z/2024-09-30T23:59:59Z 200 <dir>/searches/ganges.json
    year=2024-01-01T00:00:00Z/2024-12-31T23:59:59Z
    search small-alps   10.5,47.5,10.52,47.52   $year 1 <dir>/counts/small-alps.json
    search small-alps2  11,47,11.02,47.02       $year 1 <dir>/counts/small-alps2.json
    search small-amazon -59.5,-9.5,-59.48,-9.48 $year 1 <dir>/counts/small-amazon.json
    search small-sahara 5.5,25.5,5.52,25.52     $year 1 <dir>/counts/small-sahara.json
    search small-norway 10.5,61.5,10.52,61.52   $year 1 <dir>/counts/small-norway.json
    search small-coast  -9,38.5,-8.98,38.52     $year 1 <dir>/counts/small-coast.json
    search small-ganges 85.5,25.5,85.52,25.52   $year 1 <dir>/counts/small-ganges.json
    search mid-alps     10.5,47.5,10.9,47.78    $year 1 <dir>/counts/mid-alps.json
    search mid-norway   10.5,61.5,11.1,61.92    $year 1 <dir>/counts/mid-norway.json
    search mid-coast    -9,38.5,-8.6,38.78      $year 1 <dir>/counts/mid-coast.json
    search large-alps   10,47,11.3,47.91        $year 1 <dir>/counts/large-alps.json

Then, from the repository root:

    PYTHONPATH=backend python scripts/ds-03-clouds/measure.py prepare <dir>
    PYTHONPATH=backend python scripts/ds-03-clouds/measure.py accuracy <dir>
    PYTHONPATH=backend python scripts/ds-03-clouds/measure.py timing <dir>
    PYTHONPATH=backend python scripts/ds-03-clouds/measure.py parallel <dir> --km 10 --factor 1 --workers 8
    PYTHONPATH=backend python scripts/ds-03-clouds/measure.py summary <dir>

``prepare`` keeps eight scenes per box, spread over ``eo:cloud_cover`` from the clearest to the cloudiest, with less
than 60 % without data. Every read goes to the ``scl`` asset of the scene, cleared by ``gateway.check_url`` against
the asset hosts of the registry entry and opened as ``gateway.vsicurl_path`` with ``gateway.gdal_options``, the path
the platform takes.

``accuracy`` reads each scene whole at 20 m and on its four overviews (8 scenes at a time), lays six circles of 1, 3,
10, 30 and 100 km per scene (seeded by the scene, so a rerun lays the same ones) with at least 10 % valid pixels, and
counts the share of the classes 8, 9, 10 (and 3, 8, 9, 10) among the valid pixels (SCL ≠ 0, pixel centres in the
circle): on 20 m, on each overview (``MODE``, as the file holds them) and on every k-th pixel of 20 m for comparison.

``timing`` reads, one after the other and cold (``CPL_VSIL_CURL_NON_CACHED``), the window of a circle in the middle
of every third scene, for 1, 10, 30 and 110 km and each level; ``parallel`` reads all scenes with ``--workers``
threads. Bytes and requests come from GDAL's debug log (``Downloading a-b`` and the size request), per thread.

Nothing of a place is printed and nothing leaves ``<dir>``: no coordinates, no address; a failed read is recorded by
the class of its error only, because GDAL's messages name addresses. The data are Sentinel-2 L2A under the open
Copernicus licence; none of it belongs in the repository.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import Window

from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.gateway import Policy, check_url
from earthx.gateway.gdal import gdal_options, vsicurl_path

CLOUD = (8, 9, 10)
CLOUD_AND_SHADOW = (3, 8, 9, 10)
FACTORS = (1, 2, 4, 8, 16)  # 20 m and the four overviews of the file
ACCURACY_KM = (1, 3, 10, 30, 100)
TIMING_KM = (1, 10, 30, 110)
PER_SIZE = 6
PER_BOX = 8
MAX_NODATA = 60
NATIVE_M = 20

POLICY = Policy(allowed_hosts=frozenset(SENTINEL_2_L2A.source.asset_hosts))
RANGE = re.compile(r"Downloading (\d+)-(\d+)")
_network = threading.local()


class _NetworkCount(logging.Handler):
    """Bytes and requests of GDAL's debug lines, for the thread that reads."""

    def emit(self, record: logging.LogRecord) -> None:
        counts = getattr(_network, "counts", None)
        if counts is None:
            return
        message = record.getMessage()
        match = RANGE.search(message)
        if match:
            counts["bytes"] += int(match.group(2)) - int(match.group(1)) + 1
            counts["requests"] += 1
        elif "GetFileSize" in message:
            counts["requests"] += 1


for _name in ("rasterio._env", "rasterio._err", "rasterio._io", "rasterio._base"):
    _logger = logging.getLogger(_name)
    _logger.setLevel(logging.DEBUG)
    _logger.addHandler(_NetworkCount())
    _logger.propagate = False


def _path(href: str) -> str:
    return vsicurl_path(check_url(href, POLICY))


def _env(cold: bool) -> dict[str, str]:
    """The platform's GDAL options; ``cold`` adds the debug log the counts come from and switches the cache off."""
    if not cold:
        return gdal_options(POLICY)
    host = next(iter(POLICY.allowed_hosts))
    return {**gdal_options(POLICY), "CPL_DEBUG": "ON", "CPL_VSIL_CURL_NON_CACHED": f"/vsicurl/https://{host}"}


def _open(href: str, factor: int):
    """The file at 20 m (``factor`` 1) or one of its overviews (2, 4, 8, 16)."""
    if factor == 1:
        return rasterio.open(_path(href))
    return rasterio.open(_path(href), overview_level=int(math.log2(factor)) - 1)


def _circle(x: float, y: float, radius: float, vertices: int = 64) -> dict[str, object]:
    ring = [
        (x + radius * math.cos(2 * math.pi * i / vertices), y + radius * math.sin(2 * math.pi * i / vertices))
        for i in range(vertices)
    ]
    return {"type": "Polygon", "coordinates": [[*ring, ring[0]]]}


def _window(geometry: dict[str, object], transform, width: int, height: int) -> Window:
    """The pixels of the raster whose centres can lie in ``geometry``, clipped to the raster."""
    xs = [point[0] for point in geometry["coordinates"][0]]
    ys = [point[1] for point in geometry["coordinates"][0]]
    inverse = ~transform
    col0, row0 = inverse * (min(xs), max(ys))
    col1, row1 = inverse * (max(xs), min(ys))
    col0, row0 = max(0, math.floor(col0)), max(0, math.floor(row0))
    col1, row1 = min(width, math.ceil(col1)), min(height, math.ceil(row1))
    return Window(col0, row0, max(0, col1 - col0), max(0, row1 - row0))


def _shares(classes: numpy.ndarray, transform, geometry: dict[str, object]) -> dict[str, object]:
    """Pixels of the AOI, valid ones among them, and the cloud share of the valid ones in percent."""
    window = _window(geometry, transform, classes.shape[1], classes.shape[0])
    part = classes[window.row_off : window.row_off + window.height, window.col_off : window.col_off + window.width]
    if part.size == 0:
        return {"n": 0, "valid": 0, "cloud": None, "cloud_shadow": None}
    inside = ~geometry_mask([geometry], out_shape=part.shape, transform=rasterio.windows.transform(window, transform))
    values = part[inside]
    valid = values[values != 0]
    share = {
        name: float(numpy.isin(valid, wanted).mean() * 100) if valid.size else None
        for name, wanted in (("cloud", CLOUD), ("cloud_shadow", CLOUD_AND_SHADOW))
    }
    return {"n": int(values.size), "valid": int(valid.size), **share}


def prepare(folder: Path) -> None:
    scenes = []
    for answer in sorted((folder / "searches").glob("*.json")):
        features = json.loads(answer.read_text())["features"]
        kept = [f for f in features if f["properties"].get("s2:nodata_pixel_percentage", 0) < MAX_NODATA]
        kept.sort(key=lambda feature: feature["properties"]["eo:cloud_cover"])
        if len(kept) >= PER_BOX:
            picks = sorted({round(i * (len(kept) - 1) / (PER_BOX - 1)) for i in range(PER_BOX)})
        else:
            picks = range(len(kept))
        for index in picks:
            feature = kept[index]
            scenes.append(
                {
                    "box": answer.stem,
                    "id": feature["id"],
                    "cloud_cover": feature["properties"]["eo:cloud_cover"],
                    "href": feature["assets"]["scl"]["href"],
                    "size": feature["assets"]["scl"].get("file:size"),
                }
            )
    (folder / "scenes.json").write_text(json.dumps(scenes, indent=1))
    print(f"{len(scenes)} scenes from {len({scene['box'] for scene in scenes})} boxes")


def _accuracy_of(scene: dict[str, object]) -> tuple[list[dict[str, object]], dict[str, object]]:
    with rasterio.Env(**_env(cold=False)):
        grids = {}
        for factor in FACTORS:
            with _open(scene["href"], factor) as source:
                grids[factor] = (source.read(1), source.transform)
                if factor == 1:
                    layout = {
                        "overviews": source.overviews(1),
                        "resampling": source.tags().get("OVR_RESAMPLING_ALG"),
                        "nodata": source.nodata,
                    }
    native, transform = grids[1]
    rows = []
    rng = random.Random(scene["id"])
    span = native.shape[0] * NATIVE_M
    for km in ACCURACY_KM:
        radius = km * 500
        made = tries = 0
        while made < PER_SIZE and tries < 60:
            tries += 1
            x = transform.c + rng.uniform(radius, span - radius)
            y = transform.f - rng.uniform(radius, span - radius)
            geometry = _circle(x, y, radius)
            reference = _shares(native, transform, geometry)
            if reference["valid"] < 0.1 * reference["n"]:
                continue
            made += 1
            row = {"km": km, "cloud_cover": scene["cloud_cover"], "ref": reference, "mode": {}, "nearest": {}}
            for factor in FACTORS[1:]:
                row["mode"][factor] = _shares(*grids[factor], geometry)
                offset = factor // 2
                every = native[offset::factor, offset::factor]
                shifted = transform * rasterio.Affine.translation(offset, offset) * rasterio.Affine.scale(factor)
                row["nearest"][factor] = _shares(every, shifted, geometry)
            rows.append(row)
    valid = native[native != 0]
    tile = {
        "cloud_cover": scene["cloud_cover"],
        "cloud": float(numpy.isin(valid, CLOUD).mean() * 100) if valid.size else None,
        "cloud_shadow": float(numpy.isin(valid, CLOUD_AND_SHADOW).mean() * 100) if valid.size else None,
        "class_1": int((native == 1).sum()),
        "size": scene["size"],
        **layout,
    }
    return rows, tile


def accuracy(folder: Path) -> None:
    scenes = json.loads((folder / "scenes.json").read_text())
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(_accuracy_of, scenes))
    out = {"rows": [row for rows, _ in results for row in rows], "tiles": [tile for _, tile in results]}
    (folder / "accuracy.json").write_text(json.dumps(out))
    print(f"{len(out['rows'])} AOIs on {len(out['tiles'])} scenes")


def _read_cold(href: str, km: float, factor: int) -> dict[str, object]:
    """One cold read of the window of a circle of ``km`` in the middle of the file, at ``factor``."""
    _network.counts = {"bytes": 0, "requests": 0}
    started = time.perf_counter()
    try:
        with rasterio.Env(**_env(cold=True)), _open(href, factor) as source:
            opened = time.perf_counter() - started
            transform = source.transform
            span = source.width * transform.a
            geometry = _circle(transform.c + span / 2, transform.f - span / 2, min(km * 500, span / 2))
            window = _window(geometry, transform, source.width, source.height)
            classes = source.read(1, window=window)
            inside = ~geometry_mask([geometry], out_shape=classes.shape, transform=source.window_transform(window))
        error = None
    except Exception as failure:  # GDAL's text names the address; the class only.
        opened, inside, error = None, numpy.zeros(0, bool), type(failure).__name__
    counts, _network.counts = _network.counts, None
    return {
        "km": km,
        "factor": factor,
        "seconds": time.perf_counter() - started,
        "open": opened,
        "pixels": int(inside.sum()),
        "error": error,
        **counts,
    }


def timing(folder: Path) -> None:
    scenes = json.loads((folder / "scenes.json").read_text())[::3]
    with (folder / "timing.jsonl").open("w") as out:
        for scene in scenes:
            for km in TIMING_KM:
                for factor in FACTORS:
                    out.write(json.dumps({**_read_cold(scene["href"], km, factor), "size": scene["size"]}) + "\n")
    print(f"{len(scenes)} scenes read")


def parallel(folder: Path, km: float, factor: int, workers: int) -> None:
    scenes = json.loads((folder / "scenes.json").read_text())
    started = time.perf_counter()
    with ThreadPoolExecutor(workers) as pool:
        reads = list(pool.map(lambda scene: _read_cold(scene["href"], km, factor), scenes))
    line = {
        "km": km,
        "factor": factor,
        "workers": workers,
        "scenes": len(reads),
        "seconds": round(time.perf_counter() - started, 2),
        "bytes": sum(read["bytes"] for read in reads),
        "requests": sum(read["requests"] for read in reads),
        "errors": sum(1 for read in reads if read["error"]),
    }
    with (folder / "parallel.jsonl").open("a") as out:
        out.write(json.dumps(line) + "\n")
    print(json.dumps(line))


def _stats(errors: list[float]) -> str:
    if not errors:
        return "–"
    return f"{numpy.median(errors):.2f} / {numpy.percentile(errors, 95):.2f} / {max(errors):.1f}"


def summary(folder: Path) -> None:
    if (folder / "accuracy.json").exists():
        data = json.loads((folder / "accuracy.json").read_text())
        rows, tiles = data["rows"], data["tiles"]
        mixed = [row for row in rows if row["ref"]["cloud"] is not None and 1 < row["ref"]["cloud"] < 99]
        print(f"accuracy: {len(rows)} AOIs, {len(mixed)} with a mixed sky; |error| in points, median / p95 / max")
        for km in ACCURACY_KM:
            cells = []
            for factor in FACTORS[1:]:
                key = str(factor)
                errors = [
                    abs(row["mode"][key]["cloud"] - row["ref"]["cloud"])
                    for row in mixed
                    if row["km"] == km and row["mode"][key]["cloud"] is not None
                ]
                cells.append(f"{factor * NATIVE_M} m {_stats(errors)}")
            print(f"  {km:>3} km: " + " | ".join(cells))
        print("  by pixels of the AOI on the level read: MODE overview | every k-th pixel")
        for low, high in ((0, 100), (100, 1_000), (1_000, 10_000), (10_000, 100_000), (100_000, 10**12)):
            found = {"mode": [], "nearest": []}
            for row in mixed:
                for kind, errors in found.items():
                    for factor in FACTORS[1:]:
                        cell = row[kind][str(factor)]
                        if low <= cell["n"] < high:
                            errors.append(100.0 if cell["cloud"] is None else abs(cell["cloud"] - row["ref"]["cloud"]))
            print(f"    {low}–{high}: n={len(found['mode'])} {_stats(found['mode'])} | {_stats(found['nearest'])}")
        for factor in FACTORS[1:]:
            key = str(factor)
            middle = [row for row in rows if row["ref"]["cloud"] is not None and 5 < row["ref"]["cloud"] < 95]
            mode = [
                row["mode"][key]["cloud"] - row["ref"]["cloud"]
                for row in middle
                if row["mode"][key]["cloud"] is not None
            ]
            near = [
                row["nearest"][key]["cloud"] - row["ref"]["cloud"]
                for row in middle
                if row["nearest"][key]["cloud"] is not None
            ]
            print(
                f"  mean signed error {factor * NATIVE_M} m: MODE {numpy.mean(mode):+.2f}, every k-th {numpy.mean(near):+.2f}"
            )
        cloud = [abs(tile["cloud"] - tile["cloud_cover"]) for tile in tiles if tile["cloud"] is not None]
        shadow = [tile["cloud_shadow"] - tile["cloud_cover"] for tile in tiles if tile["cloud_shadow"] is not None]
        print(f"  whole file, classes 8-10 over SCL != 0 vs eo:cloud_cover: max |difference| {max(cloud):.3f}")
        print(
            f"  with shadows: median +{numpy.median(shadow):.2f}, max +{max(shadow):.2f}; class 1 pixels {sum(t['class_1'] for t in tiles)}"
        )
        sizes = [tile["size"] / 1e6 for tile in tiles]
        layouts = {(tuple(tile["overviews"]), tile["resampling"], tile["nodata"]) for tile in tiles}
        print(
            f"  files: {min(sizes):.2f}–{max(sizes):.2f} MB, median {numpy.median(sizes):.2f}; overviews, resampling, nodata: {layouts}"
        )
        for km in (1, 10, 30):
            apart = [
                abs(row["ref"]["cloud"] - row["cloud_cover"])
                for row in rows
                if row["km"] == km and row["ref"]["cloud"] is not None
            ]
            print(
                f"  AOI {km} km against eo:cloud_cover: median {numpy.median(apart):.1f} points,"
                f" over 20 points in {numpy.mean(numpy.array(apart) > 20) * 100:.0f} %"
            )
    if (folder / "timing.jsonl").exists():
        reads = [json.loads(line) for line in (folder / "timing.jsonl").read_text().splitlines()]
        print("timing, cold, one after the other: seconds median / p90 | KB median / max | requests | pixels")
        for km in TIMING_KM:
            for factor in FACTORS:
                cell = [read for read in reads if read["km"] == km and read["factor"] == factor and not read["error"]]
                seconds = [read["seconds"] for read in cell]
                kilobytes = [read["bytes"] / 1024 for read in cell]
                print(
                    f"  {km:>3} km {factor * NATIVE_M:>3} m: {numpy.median(seconds):.2f} / {numpy.percentile(seconds, 90):.2f}"
                    f" | {numpy.median(kilobytes):.0f} / {max(kilobytes):.0f}"
                    f" | {numpy.median([read['requests'] for read in cell]):.0f}"
                    f" | {int(numpy.median([read['pixels'] for read in cell]))}"
                )
        print(f"  open: {numpy.median([read['open'] for read in reads if read['open'] is not None]):.2f} s median")
    if (folder / "parallel.jsonl").exists():
        print("parallel:")
        for line in (folder / "parallel.jsonl").read_text().splitlines():
            print("  " + line)
    if (folder / "counts").is_dir():
        print("scenes in 2024 (numberMatched):")
        for answer in sorted((folder / "counts").glob("*.json")):
            print(f"  {answer.stem}: {json.loads(answer.read_text()).get('numberMatched')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("command", choices=("prepare", "accuracy", "timing", "parallel", "summary"))
    parser.add_argument("folder", type=Path)
    parser.add_argument("--km", type=float, default=10)
    parser.add_argument("--factor", type=int, default=1, choices=FACTORS)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.command == "parallel":
        parallel(args.folder, args.km, args.factor, args.workers)
    else:
        {"prepare": prepare, "accuracy": accuracy, "timing": timing, "summary": summary}[args.command](args.folder)


if __name__ == "__main__":
    sys.exit(main())
