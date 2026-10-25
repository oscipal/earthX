#!/usr/bin/env python3
"""The real tiler over a synthetic source, with the time of each phase of every request (NM4-26).

    PYTHONPATH=backend python scripts/tile-bench/run_tiler.py --source http://127.0.0.1:9100 [--item-ms 300]
        [--port 8101] [--workers 1] [--log tiler.jsonl]

The app is ``earthx.api.tiler.build_app`` with its real lifespan (Postgres from the ``PG*`` variables, for the item
cache), single process as in ``docker-compose.yml`` unless ``--workers`` says otherwise. Three seams are replaced, the
ones the tests replace too, and nothing between them: the name resolver answers from memory; the gateway's transport
answers every item from a hand-written synthetic one after ``--item-ms`` (the item fetch at the source); and GDAL's
``/vsicurl/`` path, built from the cleared address as always, is pointed at ``--source`` (``slow_source.py``).

``boto3`` is set aside as in the image: it is only in the dev lock (through ``moto``), and with it rasterio builds an
AWS session for every ``rasterio.Env``, which costs about 100 ms of CPU per tile that production does not spend.

``EXTRA_GDAL=KEY=VALUE,...`` adds to the GDAL options of ``gateway.gdal_options`` (``KEY=-`` removes one).
One JSON line per request to ``--log``: ``total`` and the phases in ms; one line per item fetched at the source.
"""

import argparse
import asyncio
import contextvars
import functools
import json
import os
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("--source", required=True)
parser.add_argument("--item-ms", type=float, default=300)
parser.add_argument("--port", type=int, default=8101)
parser.add_argument("--log", default="tiler.jsonl")
parser.add_argument("--workers", type=int, default=1)
# uvicorn's workers import this module again; they read the arguments from the environment.
args = parser.parse_args(os.environ["TILE_BENCH_ARGS"].split() if "TILE_BENCH_ARGS" in os.environ else None)
os.environ.setdefault("TILE_BENCH_ARGS", " ".join(sys.argv[1:]))

import fastapi.dependencies.utils  # noqa: E402
import fastapi.routing  # noqa: E402
import httpx  # noqa: E402
import rasterio.session  # noqa: E402
import titiler.core.utils  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402

import earthx.api.tiler as tiler  # noqa: E402
import earthx.readers.cog as cog  # noqa: E402

rasterio.session.boto3 = None

PHASES: contextvars.ContextVar[dict] = contextvars.ContextVar("phases")
LOG = open(args.log, "a", buffering=1)
ASSET_HOST = "https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com"
FOOTPRINT = [10.3119, 46.8326, 11.8028, 47.8459]


def synthetic_item(item_id: str) -> dict:
    """An Earth Search item as the adapter reads it, written by hand for the COGs of ``make_cogs.py``."""
    grid = {"gsd": 10, "proj:shape": [10980, 10980], "proj:transform": [10, 0, 600000, 0, -10, 5300040]}
    cog_type = "image/tiff; application=geotiff; profile=cloud-optimized"
    reflectance = {"nodata": 0, "data_type": "uint16", "spatial_resolution": 10, "scale": 0.0001, "offset": -0.1}

    def band(name: str, common: str) -> dict:
        return {"name": name, "common_name": common}

    west, south, east, north = FOOTPRINT
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": item_id,
        "collection": "sentinel-2-c1-l2a",
        "bbox": FOOTPRINT,
        "geometry": {"type": "Polygon",
                     "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]},
        "properties": {"datetime": "2026-08-01T10:20:39Z", "proj:code": "EPSG:32632", "eo:cloud_cover": 1.0},
        "links": [],
        "assets": {
            "red": {"href": f"{ASSET_HOST}/synth/{item_id}/B04.tif", "type": cog_type, "roles": ["data", "reflectance"],
                    "eo:bands": [band("B04", "red")], "raster:bands": [reflectance], **grid},
            "nir": {"href": f"{ASSET_HOST}/synth/{item_id}/B08.tif", "type": cog_type, "roles": ["data", "reflectance"],
                    "eo:bands": [band("B08", "nir")], "raster:bands": [reflectance], **grid},
            "visual": {"href": f"{ASSET_HOST}/synth/{item_id}/TCI.tif", "type": cog_type, "roles": ["visual"],
                       "eo:bands": [band("B04", "red"), band("B03", "green"), band("B02", "blue")],
                       "raster:bands": [{"nodata": 0, "data_type": "uint8", "spatial_resolution": 10}] * 3, **grid},
        },
    }


def add(name: str, ms: float) -> None:
    phases = PHASES.get(None)
    if phases is not None:
        phases[name] = phases.get(name, 0.0) + ms


def timed(name: str, function):
    @functools.wraps(function)
    def wrapper(*a, **k):
        started = time.perf_counter()
        try:
            return function(*a, **k)
        finally:
            add(name, (time.perf_counter() - started) * 1000)
    return wrapper


def timed_threadpool(prefix: str):
    """``run_in_threadpool`` with the wait for a thread and the run in it measured apart."""
    async def run(target, /, *a, **k):
        scheduled = time.perf_counter()

        def inner(*ia, **ik):
            started = time.perf_counter()
            add(f"{prefix}_wait", (started - scheduled) * 1000)
            try:
                return target(*ia, **ik)
            finally:
                add(f"{prefix}_run", (time.perf_counter() - started) * 1000)

        return await run_in_threadpool(inner, *a, **k)
    return run


def instrumented_app():
    """The tiler with the three seams and the timings, built once per process.

    uvicorn's workers import this file twice (as ``__mp_main__`` and as ``run_tiler``); a second build would wrap
    every function again and count each phase twice.
    """
    if hasattr(tiler, "tile_bench_app"):
        return tiler.tile_bench_app

    # Seam 1: the resolver answers from memory, with an address `check_addresses` accepts.
    def resolve(host: str, port: int) -> tuple[str, ...]:
        return ("93.184.216.34",)


    # Seam 2: the item, after a delay, through the real gateway client, adapter and item cache.
    async def answer_item(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(args.item_ms / 1000)
        item_id = request.url.path.rsplit("/", 1)[1]
        LOG.write(json.dumps({"source_item_fetch": item_id, "pid": os.getpid()}) + "\n")
        return httpx.Response(200, json=synthetic_item(item_id))


    class SyntheticSourceGateway(tiler.Gateway):
        def __init__(self, policy, **kwargs):
            super().__init__(policy, transport=httpx.MockTransport(answer_item), **kwargs)


    tiler.Gateway = SyntheticSourceGateway

    # Seam 3: GDAL reads the cleared path's last two segments from the slow source.
    _vsicurl_path = cog.vsicurl_path


    def local_vsicurl_path(checked) -> str:
        return f"/vsicurl/{args.source}/{'/'.join(_vsicurl_path(checked).rsplit('/', 2)[1:])}"


    cog.vsicurl_path = local_vsicurl_path

    # Extra GDAL options for an experiment.
    _gdal_options = tiler.gdal_options


    def gdal_options(policy) -> dict[str, str]:
        options = _gdal_options(policy)
        for pair in filter(None, os.environ.get("EXTRA_GDAL", "").split(",")):
            key, value = pair.split("=", 1)
            if value == "-":
                options.pop(key, None)
            else:
                options[key] = value
        return options


    tiler.gdal_options = gdal_options

    # The phases.
    _fetch_item = tiler._fetch_item


    async def fetch_item(state, dataset, item):
        started = time.perf_counter()
        try:
            return await _fetch_item(state, dataset, item)
        finally:
            add("item", (time.perf_counter() - started) * 1000)


    tiler._fetch_item = fetch_item
    _dataset_asset_path = tiler.dataset_asset_path


    @functools.wraps(_dataset_asset_path)
    async def dataset_asset_path(*a, **k):
        started = time.perf_counter()
        try:
            return await _dataset_asset_path(*a, **k)
        finally:
            add("dependency", (time.perf_counter() - started) * 1000)


    tiler.dataset_asset_path = dataset_asset_path
    _operator_post_process = tiler.operator_post_process


    @functools.wraps(_operator_post_process)
    def operator_post_process(*a, **k):
        chain = _operator_post_process(*a, **k)
        return None if chain is None else timed("compute", chain)


    tiler.operator_post_process = operator_post_process
    cog.CogReader.__attrs_post_init__ = timed("open", cog.CogReader.__attrs_post_init__)
    cog.CogReader.tile = timed("read", cog.CogReader.tile)
    titiler.core.utils.render = timed("encode", titiler.core.utils.render)
    fastapi.routing.run_in_threadpool = timed_threadpool("endpoint")
    fastapi.dependencies.utils.run_in_threadpool = timed_threadpool("syncdeps")

    app = tiler.build_app()
    app.state.earthx_resolver = resolve


    class Timing:
        """Outermost middleware: one line per request with the total and the phases."""

        def __init__(self, inner):
            self.inner = inner

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                return await self.inner(scope, receive, send)
            phases: dict = {}
            token = PHASES.set(phases)
            started = time.perf_counter()
            status = {}

            async def send_and_note(message):
                if message["type"] == "http.response.start":
                    status["code"] = message["status"]
                await send(message)

            try:
                await self.inner(scope, receive, send_and_note)
            finally:
                record = {key: round(value, 1) for key, value in phases.items()}
                record.update(path=scope["path"].rsplit("/", 4)[-4:], status=status.get("code"),
                              total=round((time.perf_counter() - started) * 1000, 1), pid=os.getpid())
                LOG.write(json.dumps(record) + "\n")
                PHASES.reset(token)


    app.add_middleware(Timing)
    tiler.tile_bench_app = app
    return app


app = instrumented_app()

if __name__ == "__main__":
    import uvicorn

    if args.workers > 1:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        uvicorn.run("run_tiler:app", host="127.0.0.1", port=args.port, workers=args.workers, access_log=False,
                    log_level="warning")
    else:
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning")
