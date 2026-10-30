#!/usr/bin/env python3
"""Jobs through the real queue and worker over the synthetic source, timed from the job's own stamps (NM4-62).

    PYTHONPATH=backend python scripts/tile-bench/job_bench.py --case reproject [--reps 5] [--out jobs.jsonl]
    PYTHONPATH=backend python scripts/tile-bench/job_bench.py --sequence [--poll 3]

What runs is what ``api`` and ``worker`` run for ``POST /processing/processes/recipe/execution``: the order goes through
``accept_order`` and ``check_recipe_hosts`` into ``submit``, a ``Supervisor`` with the default ``WorkerConfig`` picks
the run up, starts the real child (``job_child.py``) and uploads the result. Replaced are only the seams the tests
replace: the item comes from ``synthetic_item.py`` (with a ``file:checksum``, so no ``HEAD`` goes out), GDAL reads
from ``BENCH_SOURCE`` (``slow_source.py``), the object store is ``moto`` in this process. Postgres comes from the
``PG*`` variables and needs the migrations of the code under test (``python -m earthx.catalog.load``).

``--case`` is one of ``CASES``: the order of ``scripts/try-job.ps1`` (one asset, ``reproject`` to EPSG:3035 at 20 m,
0.01°) or an NDVI with ``mask`` (0.05°). Every repetition has a new item version, so a new cache key and a real run.
One JSON line per job: the stamps of the job (accepted, running, finished) as ``queue_ms`` and ``run_ms``, the
supervisor's parts (child start, child, upload) and the child's phases.

``--sequence`` plays the job part of ``try-job.ps1`` twice with the same item version: place, poll every ``--poll``
seconds until done, place again, delete both. One JSON line per round: wall time and whether the first order was a
cache hit at once.

The orders are of recipe version 1, as ``try-job.ps1`` sends them, so both sides of a comparison read the same bytes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

# A spawned child imports this file again as `__mp_main__`; in `worker` that is uvicorn's small `__main__`. Without
# the guard the child would load `api`, `moto` and the queue before its run, which `worker` does not.
if __name__ == "__main__":
    import psycopg
    from moto import mock_aws
    from synthetic_item import synthetic_item

    from earthx.api.intake import accept_order, check_recipe_hosts
    from earthx.catalog.datasets import REGISTRY
    from earthx.jobs.config import WorkerConfig
    from earthx.jobs.entry import ChildTarget
    from earthx.jobs.submit import dismiss, job_status, submit
    from earthx.jobs.worker import Supervisor
    from earthx.objectstore.results import Store
    from earthx.processing.operators import REGISTRY as OPERATORS

CENTRE = (11.05, 47.35)  # view.py
ITEM = "SYNTH_T32TPT_20260801T102039_L2A"
BUCKET = "earthx"


def square(size: float) -> dict:
    lon, lat = CENTRE
    half = size / 2
    ring = [[lon - half, lat - half], [lon + half, lat - half], [lon + half, lat + half], [lon - half, lat + half],
            [lon - half, lat - half]]
    return {"type": "Polygon", "coordinates": [ring]}


CASES = {
    "reproject": {
        "assets": ["red"], "size": 0.01,
        "steps": [{"op": "reproject", "op_version": 2,
                   "params": {"crs": "EPSG:3035", "resolution": 20.0, "resampling": "bilinear"}}],
    },
    "ndvi_mask": {
        "assets": ["red", "nir", "scl"], "size": 0.05,
        "steps": [{"op": "mask", "op_version": 1, "params": {"source": "scl", "classes": [8, 9, 10]}},
                  {"op": "band_math", "op_version": 1, "params": {"expression": "(nir - red) / (nir + red)"}}],
    },
}


def order(case: str) -> str:
    spec = CASES[case]
    return json.dumps({
        "recipe_version": 1,
        "inputs": [{"name": "scene", "dataset": "sentinel-2-c1-l2a", "groups": [[ITEM]], "assets": spec["assets"]}],
        "aoi": square(spec["size"]),
        "steps": spec["steps"],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    })


class NoGateway:
    """Every asset carries a checksum, so intake never asks the source for a ``HEAD``; if it did, this says so."""

    def __getattr__(self, name: str):
        raise RuntimeError(f"the bench gateway was asked for {name}")


def place(conn: psycopg.Connection, raw: str, version: str) -> tuple[str, float]:
    async def item_source(dataset_id: str, item_id: str) -> dict:
        return synthetic_item(item_id, version)

    begin = time.perf_counter()
    accepted = asyncio.run(accept_order(raw, registry=REGISTRY, operators=OPERATORS, item_source=item_source,
                                        gateway=NoGateway()))
    check_recipe_hosts(accepted.recipe, REGISTRY)
    job_id = submit(conn, accepted.recipe, operators=OPERATORS, acquired_on=accepted.acquired_on,
                    scene_aoi=accepted.scene_aoi)
    return job_id, (time.perf_counter() - begin) * 1000


def wait(conn: psycopg.Connection, job_id: str, every: float, timeout: float = 600) -> str:
    deadline = time.monotonic() + timeout
    while True:
        status = job_status(conn, job_id).status
        if status in ("successful", "failed", "dismissed") or time.monotonic() > deadline:
            return status
        time.sleep(every)


def stamps(conn: psycopg.Connection, job_id: str) -> dict:
    row = conn.execute(
        """
        SELECT r.run_id, r.attempt, extract(epoch FROM j.created_at), extract(epoch FROM r.started_at),
               extract(epoch FROM r.finished_at)
        FROM public.earthx_job j JOIN public.earthx_run r ON r.run_id = j.run_id WHERE j.job_id = %s
        """,
        (job_id,),
    ).fetchone()
    run_id, attempt, created, started, finished = row
    return {"workdir": f"{run_id}-{attempt}", "created": float(created), "started": float(started),
            "finished": float(finished)}


def timed_supervisor(supervisor: Supervisor, parts: dict) -> None:
    """Note per work directory when the child was started, when it ended and how long the upload took."""
    start_child, watch, upload = supervisor._start_child, supervisor._watch, supervisor._upload_and_finish

    def _start_child(workdir: Path):
        parts.setdefault(workdir.name, {})["child_start"] = time.time()
        return start_child(workdir)

    def _watch(conn, picked, *a, **k):
        try:
            return watch(conn, picked, *a, **k)
        finally:
            parts.setdefault(f"{picked.run_id}-{picked.attempt}", {})["child_end"] = time.time()

    def _upload_and_finish(conn, picked, info, workdir):
        begin = time.perf_counter()
        try:
            return upload(conn, picked, info, workdir)
        finally:
            parts.setdefault(workdir.name, {})["upload_ms"] = (time.perf_counter() - begin) * 1000

    supervisor._start_child, supervisor._watch, supervisor._upload_and_finish = _start_child, _watch, _upload_and_finish


def child_records(path: Path) -> dict:
    if not path.exists():
        return {}
    return {record["workdir"]: record for record in map(json.loads, path.read_text().splitlines())}


def measure(conn: psycopg.Connection, case: str, reps: int, parts: dict, child_log: Path, out) -> None:
    raw = order(case)
    for rep in range(reps):
        job_id, accept_ms = place(conn, raw, uuid.uuid4().hex)
        status = wait(conn, job_id, 0.05)
        times = stamps(conn, job_id)
        time.sleep(0.2)  # the child's line is written as it ends, the supervisor may still be closing
        child = child_records(child_log).get(times["workdir"], {})
        part = parts.get(times["workdir"], {})
        record = {
            "case": case, "rep": rep, "status": status, "accept_ms": round(accept_ms, 1),
            "queue_ms": round((times["started"] - times["created"]) * 1000, 1),
            "run_ms": round((times["finished"] - times["started"]) * 1000, 1),
            "job_ms": round((times["finished"] - times["created"]) * 1000, 1),
        }
        if part and child:
            record.update(
                claim_to_child_ms=round((part["child_start"] - times["started"]) * 1000, 1),
                spawn_ms=round((child["started"] - part["child_start"]) * 1000, 1),
                import_ms=round((child["imported"] - child["started"]) * 1000, 1),
                child_ms=round((part["child_end"] - part["child_start"]) * 1000, 1),
                upload_ms=round(part.get("upload_ms", 0.0), 1),
                **{f"child_{name}_ms": ms for name, ms in child["phases"].items()},
                passes=child["counts"],
            )
        out.write(json.dumps(record) + "\n")
        print(json.dumps(record), flush=True)


def sequence(conn: psycopg.Connection, poll: float, out) -> None:
    """The job part of ``try-job.ps1``, twice, with the same order and the same item version."""
    raw, version = order("reproject"), uuid.uuid4().hex
    for round_ in (1, 2):
        begin = time.perf_counter()
        first, _ = place(conn, raw, version)
        hit = job_status(conn, first).status == "successful"
        status = "successful" if hit else wait(conn, first, poll)
        second, _ = place(conn, raw, version)
        second_hit = job_status(conn, second).status == "successful"
        for job_id in (first, second):
            dismiss(conn, job_id)
        record = {"case": "sequence", "round": round_, "poll_s": poll, "status": status, "first_hit": hit,
                  "second_hit": second_hit, "wall_ms": round((time.perf_counter() - begin) * 1000, 1)}
        out.write(json.dumps(record) + "\n")
        print(json.dumps(record), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=sorted(CASES), default="reproject")
    parser.add_argument("--reps", type=int, default=5)
    parser.add_argument("--sequence", action="store_true")
    parser.add_argument("--poll", type=float, default=3.0)
    parser.add_argument("--source", default="http://127.0.0.1:9100")
    parser.add_argument("--out", default="jobs.jsonl")
    args = parser.parse_args()
    scratch = Path(tempfile.mkdtemp(prefix="job-bench-"))
    child_log = scratch / "child.jsonl"
    os.environ.update(BENCH_SOURCE=args.source, BENCH_CHILD_LOG=str(child_log))
    (scratch / "access_key").write_text("GKbenchaccesskey0001\n")
    (scratch / "secret_key").write_text("bench-secret-key-000000000000000\n")
    os.environ["MOTO_S3_CUSTOM_ENDPOINTS"] = "http://objectstore:3900"
    store_env = {"S3_ENDPOINT": "http://objectstore:3900", "S3_PUBLIC_ENDPOINT": "http://localhost:3900",
                 "S3_REGION": "garage", "S3_BUCKET": BUCKET, "S3_ACCESS_KEY_FILE": str(scratch / "access_key"),
                 "S3_SECRET_KEY_FILE": str(scratch / "secret_key")}
    # The child finds this directory (and with it `job_child`) through the path a spawned process inherits.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    with mock_aws(), psycopg.connect(autocommit=True) as conn, open(args.out, "a", buffering=1) as out:
        store = Store.from_environ(store_env)
        store.s3._internal.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "garage"})
        config = WorkerConfig(workdir=scratch / "runs", cleanup_first_seconds=1e9)
        supervisor = Supervisor(config, store, target=ChildTarget("job_child", "run_child"), name="job-bench")
        parts: dict = {}
        timed_supervisor(supervisor, parts)
        supervisor.start()
        try:
            if args.sequence:
                sequence(conn, args.poll, out)
            else:
                measure(conn, args.case, args.reps, parts, child_log, out)
        finally:
            supervisor.stop(30)


if __name__ == "__main__":
    main()
