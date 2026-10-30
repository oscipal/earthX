"""The child of one run for ``job_bench.py`` (NM4-62): the real ``earthx.jobs.child`` with two seams and timings.

The supervisor starts it as ``ChildTarget("job_child", "run_child")``. It replaces what ``run_tiler.py`` replaces for
GDAL and nothing else: the resolver answers from memory, and the cleared ``/vsicurl/`` path points at
``BENCH_SOURCE`` (``slow_source.py``). Then it runs ``earthx.jobs.child.run_child`` as the worker does.

One JSON line per run goes to ``BENCH_CHILD_LOG``: wall-clock stamps (child started, imports done, ended) and the
time of each phase in ms. Phases nest: ``read`` and ``kernels`` happen inside ``pass_pixel``, the reads and writes of
the work files inside ``pass_grid``.
"""

import functools
import json
import os
import time


def run_child(workdir: str, conn) -> None:
    started = time.time()
    import earthx.jobs.child as child
    import earthx.processing.core as core
    import earthx.processing.mosaic as mosaic
    import earthx.processing.source as source
    import earthx.readers.access as access
    import earthx.readers.cog as cog

    imported = time.time()
    phases: dict[str, float] = {}
    counts: dict[str, int] = {}

    def timed(name: str, function, key=None):
        @functools.wraps(function)
        def wrapper(*a, **k):
            begin = time.perf_counter()
            try:
                return function(*a, **k)
            finally:
                label = key(*a, **k) if key else name
                phases[label] = phases.get(label, 0.0) + (time.perf_counter() - begin) * 1000
                counts[label] = counts.get(label, 0) + 1
        return wrapper

    access.resolve_host = lambda host, port: ("93.184.216.34",)
    cleared = cog.vsicurl_path
    cog.vsicurl_path = lambda checked: f"/vsicurl/{os.environ['BENCH_SOURCE']}/" + "/".join(
        cleared(checked).rsplit("/", 2)[1:])

    source.Source.open = classmethod(timed("open", source.Source.open.__func__))
    core.open_mosaic = timed("open", core.open_mosaic)
    source.Source.read = timed("read", source.Source.read)
    mosaic.MosaicSource.read = timed("read", mosaic.MosaicSource.read)
    core._pixel_kernels = timed("kernels", core._pixel_kernels)
    core._write_mask = timed("mask", core._write_mask)
    core._run_pass = timed("pass", core._run_pass, key=lambda state, segment, *a, **k: f"pass_{segment.kind}")
    core.cog_translate = timed("cog", core.cog_translate)
    child.run = timed("run", child.run)
    try:
        child.run_child(workdir, conn)
    finally:
        record = {"workdir": os.path.basename(workdir), "started": started, "imported": imported, "ended": time.time(),
                  "phases": {name: round(ms, 1) for name, ms in phases.items()}, "counts": counts}
        with open(os.environ["BENCH_CHILD_LOG"], "a") as log:
            log.write(json.dumps(record) + "\n")
