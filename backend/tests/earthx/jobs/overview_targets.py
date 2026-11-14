"""Stand-ins for the child of a pyramid build, in the two steps `jobs` runs (M5-30b part 8b-2).

They take ``(workdir, conn)`` like :func:`earthx.jobs.overview_child.run_child` and speak its messages. The pyramid they
leave is two base tiles at z2 (``1/1`` and ``2/1``) with the three tiles above them; what they do is set by environment
variables, which a spawned child inherits. They import almost nothing, so a child that runs one stays light.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

BASE = 2
HASHES = {"1/1": "h1", "2/1": None}
TILES = ("2/1/1", "2/2/1", "1/0/0", "1/1/0", "0/0/0")


def _job(workdir: str) -> dict[str, Any]:
    return json.loads((Path(workdir) / "job.json").read_text())


def _plan(workdir: str, conn: Any) -> None:
    hashes = json.loads(os.environ["PLAN_HASHES"]) if "PLAN_HASHES" in os.environ else HASHES
    (Path(workdir) / "plan.json").write_text(json.dumps({"base_zoom": BASE, "tiles": hashes}))
    conn.send(("done", {"tiles": len(hashes), "peak_mb": 1.0}))
    conn.close()


def _build(workdir: str, conn: Any) -> None:
    job = _job(workdir)
    root = Path(workdir)
    reused = {f"{BASE}/{key}" for key in job["reuse"]}
    for index, name in enumerate(TILES, start=1):
        path = root / "tiles" / f"{name}.tif"
        path.parent.mkdir(parents=True, exist_ok=True)
        if name not in reused:
            path.write_bytes(b"read")
        conn.send(("progress", index, len(TILES), 1.0))
    hashes = json.loads(os.environ["PLAN_HASHES"]) if "PLAN_HASHES" in os.environ else HASHES
    manifest = {"base_zoom": BASE, "tiles": list(TILES), "base_hashes": {k: v for k, v in hashes.items() if v}}
    (root / "manifest.json").write_text(json.dumps(manifest))
    conn.send(("done", {"tiles": len(TILES), "peak_mb": 1.0}))
    conn.close()


def succeed(workdir: str, conn: Any) -> None:
    """Both steps succeed; the build step waits ``OVERVIEW_DELAY`` seconds first."""
    if _job(workdir)["mode"] == "plan":
        _plan(workdir, conn)
        return
    time.sleep(float(os.environ.get("OVERVIEW_DELAY", "0")))
    _build(workdir, conn)


def fail(workdir: str, conn: Any) -> None:
    """The build step reports ``CHILD_KIND`` as its failure."""
    if _job(workdir)["mode"] == "plan":
        _plan(workdir, conn)
        return
    conn.send(("progress", 1, 5, 1.0))
    conn.send(("failed", os.environ["CHILD_KIND"]))
    conn.close()


def fail_once(workdir: str, conn: Any) -> None:
    """The first build step of the container reports ``CHILD_KIND``, the later ones succeed (a marker file next to the work directory)."""
    marker = Path(workdir).parent / "failed-once"
    if _job(workdir)["mode"] == "build" and not marker.exists():
        marker.write_text("x")
        fail(workdir, conn)
    else:
        succeed(workdir, conn)


def crash(workdir: str, conn: Any) -> None:
    """The build step dies by a signal with no word, as the kernel's out-of-memory killer does."""
    if _job(workdir)["mode"] == "plan":
        _plan(workdir, conn)
        return
    conn.send(("progress", 1, 5, 99.0))
    time.sleep(0.2)
    os.kill(os.getpid(), signal.SIGKILL)


def exit_silently(workdir: str, conn: Any) -> None:
    if _job(workdir)["mode"] == "plan":
        _plan(workdir, conn)
        return
    sys.exit(0)


def hang(workdir: str, conn: Any) -> None:
    """The build step says one thing and then nothing, for ever; only a kill ends it."""
    if _job(workdir)["mode"] == "plan":
        _plan(workdir, conn)
        return
    conn.send(("progress", 1, 5, 1.0))
    time.sleep(3600)


def plan_fails(workdir: str, conn: Any) -> None:
    conn.send(("failed", os.environ["CHILD_KIND"]))
    conn.close()
