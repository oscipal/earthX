#!/usr/bin/env python3
"""A pyramid build's reads through its real supervisor, against the synthetic source (M5-37 plan §7, M4).

    PYTHONPATH=backend:scripts/tile-bench python scripts/tile-bench/pyramid_turns.py \\
        --source http://127.0.0.1:9100 --files 30 [--shared] --out build.jsonl

The supervisor is `earthx.jobs.overview_builder.OverviewBuilder` and runs one step (`_step`) as a build does: it spawns
a child, watches it and answers its messages. The child is :func:`child` below, not the overview child: it reads
``--files`` base tiles from the synthetic COGs through the core (`processing.overview.base_tile`) the way a build reads its
files, with the pacer the overview child would hand in. That is ``PipePacer`` where it exists (the branch: every turn
from the supervisor, kept in Postgres) and ``HostPacer`` otherwise (`main`: spacing in the child's own memory). With
``--shared`` the supervisor gets the host's places and spacing; leave it out on `main`, whose supervisor knows none.

Two seams, as in `run_tiler.py`: GDAL reads ``/vsicurl/<source>/f<i>/B04.tif`` (a URL of its own per file, so no read
answers from another's cache), and the host a read counts against is :data:`HOST`, not the local source. The interval
is ``EARTHX_OVERVIEW_HOST_INTERVAL_S`` (0.25 s unless set). One JSON line to ``--out`` with the step's wall time and the
requests GDAL made. Postgres from the ``PG*`` variables.
"""

import argparse
import json
import multiprocessing
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

HOST = "bench-cogs.example.org"


def child(workdir: str, conn) -> None:
    """The stand-in for the overview child: reads ``files`` tiles of the synthetic scene, one file each."""
    sys.modules["boto3"] = None  # as in the image (run_tiler.py)
    import morecantile

    from earthx.catalog.registry import OverviewResampling
    from earthx.processing import overview
    from earthx.readers.access import process_gdal_options
    from earthx.readers.cog import AssetPath

    try:
        from earthx.jobs.overview_child import PipePacer

        pacer = PipePacer(conn)
    except ImportError:
        from earthx.readers.access import host_pacer

        pacer = host_pacer()
    overview.asset_host = lambda path: HOST if str(path).startswith("/vsicurl/") else None
    job = json.loads((Path(workdir) / "job.json").read_text())
    tms = morecantile.tms.get("WebMercatorQuad")
    tile = tms.tile(9.6, 47.3, 9)
    options = {key: value for key, value in process_gdal_options().items() if key != "GDAL_CACHEMAX"}
    requests = 0
    original = pacer.account

    def counting(host: str, count: int, **outcome: object) -> None:
        nonlocal requests
        requests += count
        original(host, count, **outcome)

    pacer.account = counting
    for index in range(job["files"]):
        scene = AssetPath(f"/vsicurl/{job['source']}/f{job['run']}-{index}/B04.tif", dataset_id="bench",
                          item_id=f"f{index}", asset="B04")
        overview.base_tile([scene], tile, resampling=OverviewResampling.AVERAGE, pacer=pacer, gdal_config=options)
        conn.send(("progress", index + 1, job["files"], 1.0))
    conn.send(("done", {"tiles": job["files"], "requests": requests, "peak_mb": 1.0}))
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--files", type=int, default=30)
    parser.add_argument("--shared", action="store_true")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    import psycopg

    from earthx.jobs import overviews
    from earthx.jobs.config import WorkerConfig
    from earthx.jobs.entry import ChildTarget
    from earthx.jobs.overview_builder import OverviewBuilder

    options = {}
    if args.shared:
        from earthx.jobs.source_hosts import HostTurns
        from earthx.readers.access import overview_host_interval

        options["source_limits"] = {HOST: HostTurns(32, overview_host_interval())}
        with psycopg.connect(autocommit=True) as conn:
            conn.execute("DELETE FROM public.earthx_source_lease WHERE host = %s", (HOST,))
            conn.execute("DELETE FROM public.earthx_source_host WHERE host = %s", (HOST,))
    with tempfile.TemporaryDirectory() as root, psycopg.connect(autocommit=True) as conn:
        config = WorkerConfig(workdir=Path(root), progress_seconds=0.0)
        builder = OverviewBuilder(
            config, None, name="bench", pyramids={"bench": (HOST,)}, context=multiprocessing.get_context("spawn"),
            stopping=threading.Event(), connect=lambda: conn, database_ok=lambda: None,
            target=ChildTarget("pyramid_turns", "child"), **options,
        )  # fmt: skip
        build = overviews.Build(dataset_id="bench", version="v", source_version="v", attempt=1, hosts=(HOST,))
        job = {"dataset_id": "bench", "files": args.files, "source": args.source, "run": os.getpid()}
        started = time.monotonic()
        done = builder._step(conn, build, Path(root), job, lambda: None, write_progress=False)
        ended = time.monotonic()
    with open(args.out, "a", encoding="utf-8") as out:
        out.write(json.dumps({"start": started, "end": ended, "requests": done["requests"], "files": args.files}) + "\n")
    print(f"{args.files} files, {done['requests']} requests, {ended - started:.1f} s", file=sys.stderr)


if __name__ == "__main__":
    main()
