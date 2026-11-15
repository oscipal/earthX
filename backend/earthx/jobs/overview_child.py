"""The child process of one pyramid build: the worker core and nothing else (M5-30b part 8b-2, adr/0013 §5.3, adr/0032 §5.2).

Started like the child of a run (``spawn``, a pipe) and speaking its messages: ``("progress", done, total, peak_mb)``
per tile, then ``("done", info)`` or ``("failed", kind)``. It knows no database and no object store: it reads
``job.json`` and ``items.jsonl`` that `jobs` left in the work directory and writes ``plan.json`` or the tiles and
``manifest.json`` there (:mod:`earthx.processing.overview_build`). ``job.json`` says which step this child is: ``"plan"``
and ``"build"`` for a pyramid, ``"patch_plan"`` and ``"patch"`` for the retry of its omitted base tiles. A failed step sends its
kind and, as a third part, where and why (:func:`failure_detail`), which the supervisor logs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from earthx.jobs.child import guard, high_water_mb
from earthx.logging import configure_logging
from earthx.processing import overview_build, worker_environment

__all__ = ["failure_detail", "run_child"]


def failure_detail(error: BaseException, step: str) -> dict[str, str]:
    """What the supervisor logs of a failed step: the step, the class, a short reason and the tile, never an address.

    :func:`~earthx.processing.overview_build.describe` takes every URL, path and host name out of the reason and keeps
    none for a lookup error (its message is a key, which can be an item's id). ``tile`` is ``z/x/y`` where the failure
    happened at a tile (the world grid, no AOI; Otto, 15.11.2026). An item's id or a bucket key is not named here.
    """
    return {"step": step, **overview_build.describe(error)}


def _run(workdir: Path, conn: Any, step: list[str]) -> None:
    mode = json.loads((workdir / overview_build.JOB_NAME).read_text(encoding="utf-8")).get("mode")
    step.append(str(mode))
    if mode not in ("plan", "build", "patch_plan", "patch"):
        raise ValueError("job.json names a step: plan, build, patch_plan or patch")

    def progress(done: int, total: int) -> None:
        conn.send(("progress", done, total, high_water_mb()))

    with worker_environment():
        if mode == "plan":
            info: dict[str, Any] = {"tiles": len(overview_build.plan_pyramid(workdir)["tiles"])}
        elif mode == "patch_plan":
            info = {"tiles": len(overview_build.plan_patch(workdir)["fetch"])}
        elif mode == "patch":
            info = {"tiles": len(overview_build.patch_pyramid(workdir, progress)["tiles"])}
        else:
            manifest = overview_build.build_pyramid(workdir, progress)
            info = {"tiles": len(manifest["tiles"])}
    conn.send(("done", {**info, "peak_mb": round(high_water_mb(), 1)}))
    conn.close()


def run_child(workdir: str, conn: Any) -> None:
    """The target of the child process: one step of a pyramid build in ``workdir``."""
    configure_logging()
    step: list[str] = []
    guard(
        conn,
        lambda: _run(Path(workdir), conn, step),
        detail=lambda error: failure_detail(error, step[0] if step else "start"),
    )
