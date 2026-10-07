"""The child process of one run: the worker core and nothing else (adr/0013 §5.3, §6.2).

`jobs` starts it with ``multiprocessing.get_context("spawn")`` and a pipe. It knows no
database, no queue and no object store (KLAERUNGEN B9): this module imports `processing`
and the standard library, and `earthx/jobs/__init__.py` imports nothing, so a child never
loads psycopg or the supervisor. ``test_child.py`` starts one and reads ``sys.modules``.

What goes over the pipe, child to supervisor:

* ``("progress", done, total, peak_mb)`` after every block;
* ``("done", info)`` when the run finished and ``result.tif`` and ``mask.tif`` lie in the
  work directory; ``info`` is plain data about the result, never an address or a coordinate;
* ``("failed", kind)``, ``kind`` a short name from :func:`~earthx.processing.failure_kind`.

And supervisor to child: ``"cancel"``, read between blocks. The callback then raises
:class:`~earthx.processing.RunCancelled`, the core removes its files, and the child
reports ``("failed", "cancelled")``.

``peak_mb`` is ``VmHWM`` from ``/proc/self/status``, not ``ru_maxrss``: on Linux
``ru_maxrss`` survives ``exec`` and reports the parent's peak (plan M4-07a §9.3).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from earthx.processing import RunCancelled, failure_kind, run, worker_environment
from earthx.processing.operators import REGISTRY
from earthx.processing.recipe import parse_recipe

__all__ = ["guard", "high_water_mb", "run_child"]

RECIPE_NAME = "recipe.json"


def high_water_mb() -> float:
    """Peak resident memory of this process in MB; ``0.0`` where ``/proc`` has none."""
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) / 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0.0


def guard(conn: Any, work: Callable[[], None]) -> None:
    """Run ``work``; whatever it raises becomes ``("failed", kind)`` and nothing else leaves the child."""
    try:
        work()
    except BaseException as error:  # noqa: BLE001 - the child's edge: every failure is named, none escapes
        try:
            conn.send(("failed", failure_kind(error)))
        except OSError:
            pass  # the supervisor is gone; the run is its to settle
        finally:
            conn.close()


def _run(workdir: Path, conn: Any) -> None:
    recipe = parse_recipe((workdir / RECIPE_NAME).read_bytes(), REGISTRY)

    def progress(done: int, total: int) -> None:
        conn.send(("progress", done, total, high_water_mb()))
        if conn.poll() and conn.recv() == "cancel":
            raise RunCancelled()

    with worker_environment():
        result = run(recipe, workdir=workdir, progress=progress)
    conn.send(
        (
            "done",
            {
                "properties": result.properties,
                "scaling": [applied.model_dump(mode="json") for applied in result.scaling],
                "blocks": result.blocks,
                "valid_pixels": result.valid_pixels,
                "engine": result.engine,
                "width": result.meta.width,
                "height": result.meta.height,
                "bands": len(result.meta.bands),
                "bytes": result.path.stat().st_size,
                "peak_mb": round(high_water_mb(), 1),
            },
        )
    )
    conn.close()


def run_child(workdir: str, conn: Any) -> None:
    """The target of the child process: run the recipe in ``workdir/recipe.json`` there."""
    guard(conn, lambda: _run(Path(workdir), conn))
