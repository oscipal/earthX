"""The child process of one pyramid build: the worker core and nothing else (M5-30b part 8b-2, adr/0013 §5.3, adr/0032 §5.2).

Started like the child of a run (``spawn``, a pipe) and speaking its messages: ``("progress", done, total, peak_mb)``
per tile, then ``("done", info)`` or ``("failed", kind)``. It knows no database and no object store: it reads
``job.json`` and ``items.jsonl`` that `jobs` left in the work directory and writes ``plan.json`` or the tiles and
``manifest.json`` there (:mod:`earthx.processing.overview_build`). ``job.json`` says which of the two steps this
child is (``"mode": "plan"`` or ``"build"``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from earthx.jobs.child import guard, high_water_mb
from earthx.logging import configure_logging
from earthx.processing import overview_build, worker_environment

__all__ = ["run_child"]


def _run(workdir: Path, conn: Any) -> None:
    mode = json.loads((workdir / overview_build.JOB_NAME).read_text(encoding="utf-8")).get("mode")
    if mode not in ("plan", "build"):
        raise ValueError("job.json names a step: plan or build")

    def progress(done: int, total: int) -> None:
        conn.send(("progress", done, total, high_water_mb()))

    with worker_environment():
        if mode == "plan":
            info: dict[str, Any] = {"tiles": len(overview_build.plan_pyramid(workdir)["tiles"])}
        else:
            manifest = overview_build.build_pyramid(workdir, progress)
            info = {"tiles": len(manifest["tiles"])}
    conn.send(("done", {**info, "peak_mb": round(high_water_mb(), 1)}))
    conn.close()


def run_child(workdir: str, conn: Any) -> None:
    """The target of the child process: one step of a pyramid build in ``workdir``."""
    configure_logging()
    guard(conn, lambda: _run(Path(workdir), conn))
