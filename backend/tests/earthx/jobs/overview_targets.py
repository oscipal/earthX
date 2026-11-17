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


def fail_with_detail(workdir: str, conn: Any) -> None:
    """The build step fails as the real child does for a bug it does not know: ``unknown`` with where and why."""
    if _job(workdir)["mode"] == "plan":
        _plan(workdir, conn)
        return
    conn.send(("progress", 1, 5, 1.0))
    detail = {"step": "build", "error": "RasterioIOError", "reason": "HTTP response code on <address> 0", "tile": "6/33/22"}
    conn.send(("failed", "unknown", detail))
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


OMITTED = {"2/1": {"kind": "unreadable", "error": "RasterioIOError", "reason": "not recognized as a supported file format"}}


def omit(workdir: str, conn: Any) -> None:
    """The build step leaves the base tile ``2/1`` out, as a file that stays unreadable does, and makes the levels above."""
    if _job(workdir)["mode"] == "plan":
        _plan(workdir, conn)
        return
    root = Path(workdir)
    tiles = [name for name in TILES if name != "2/2/1"]
    for index, name in enumerate(tiles, start=1):
        path = root / "tiles" / f"{name}.tif"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"read")
        conn.send(("progress", index, len(tiles), 1.0))
    manifest = {"base_zoom": BASE, "tiles": tiles, "base_hashes": {"1/1": "h1"}, "omitted": OMITTED}
    (root / "manifest.json").write_text(json.dumps(manifest))
    conn.send(("done", {"tiles": len(tiles), "peak_mb": 1.0}))
    conn.close()


def _patch_plan(workdir: str, conn: Any) -> None:
    only = _job(workdir)["only"]
    assert only == ["2/1"], only
    (Path(workdir) / "plan.json").write_text(json.dumps({"base_zoom": BASE, "fetch": ["2/1/1", "1/0/0", "1/1/0"]}))
    conn.send(("done", {"tiles": 3, "peak_mb": 1.0}))
    conn.close()


def _fetched(workdir: str) -> None:
    """The stored tiles the levels above need were put in the work directory before the step ran."""
    for name in ("2/1/1", "1/0/0", "1/1/0"):
        if not (Path(workdir) / "tiles" / f"{name}.tif").is_file():
            raise FileNotFoundError("a sibling of the retry was not fetched")


def patch_ok(workdir: str, conn: Any) -> None:
    """The retry reads the omitted tile now: it makes it and the tiles above, and recovers it."""
    mode = _job(workdir)["mode"]
    if mode == "plan":
        _plan(workdir, conn)
    elif mode == "build":
        omit(workdir, conn)
    elif mode == "patch_plan":
        _patch_plan(workdir, conn)
    else:
        _fetched(workdir)
        root = Path(workdir)
        tiles = ["2/2/1", "1/1/0", "0/0/0"]
        for name in tiles:
            path = root / "tiles" / f"{name}.tif"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"made again")
        manifest = {"base_zoom": BASE, "tiles": tiles, "base_hashes": {"2/1": "h2"}, "omitted": {}, "recovered": ["2/1"]}
        (root / "manifest.json").write_text(json.dumps(manifest))
        conn.send(("done", {"tiles": 3, "peak_mb": 1.0}))
        conn.close()


def patch_again(workdir: str, conn: Any) -> None:
    """The retry fails again for the file: nothing is made, the tile stays omitted with the new reason."""
    mode = _job(workdir)["mode"]
    if mode == "plan":
        _plan(workdir, conn)
    elif mode == "build":
        omit(workdir, conn)
    elif mode == "patch_plan":
        _patch_plan(workdir, conn)
    else:
        _fetched(workdir)
        again = {"2/1": {"kind": "source_5xx", "error": "RasterioIOError", "reason": "HTTP response code: 503"}}
        manifest = {"base_zoom": BASE, "tiles": [], "base_hashes": {}, "omitted": again, "recovered": []}
        (Path(workdir) / "manifest.json").write_text(json.dumps(manifest))
        conn.send(("done", {"tiles": 0, "peak_mb": 1.0}))
        conn.close()


def patch_breaks(workdir: str, conn: Any) -> None:
    """The retry fails for a reason that is not a file: the step says so and the pyramid is left as it is."""
    if _job(workdir)["mode"] == "patch":
        conn.send(("failed", "unknown", {"step": "patch", "error": "ArithmeticError", "reason": "a bug", "tile": "2/2/1"}))
        conn.close()
    else:
        patch_ok(workdir, conn)


def patch_slow(workdir: str, conn: Any) -> None:
    """The retry's read takes a while: a marker says it began, so a test can take the turn away meanwhile."""
    if _job(workdir)["mode"] == "patch":
        (Path(workdir) / "started").write_text("")
        time.sleep(3.0)
    patch_ok(workdir, conn)


def patch_again_slow(workdir: str, conn: Any) -> None:
    """The retry fails again, but only after a while, so that two workers that both retry would overlap."""
    if _job(workdir)["mode"] == "patch":
        time.sleep(1.0)
    patch_again(workdir, conn)


def _paced(workdir: str, conn: Any, host: str) -> None:
    """Read ``PACED_FILES`` files on ``host`` the way the real child does (M5-37): ask for each turn, wait, account.

    When each turn was given goes to ``turns.json`` next to the work directory (it is removed with it otherwise);
    ``PACED_FAIL`` files in a row are accounted as a failure of the source.
    """
    if _job(workdir)["mode"] == "plan":
        _plan(workdir, conn)
        return
    given: list[float] = []
    failing = int(os.environ.get("PACED_FAIL", "0"))
    for index in range(int(os.environ.get("PACED_FILES", "3"))):
        conn.send(("pace", host))
        if conn.recv() != ("go",):
            raise RuntimeError("no turn")
        given.append(time.time())
        conn.send(("account", host, int(os.environ.get("PACED_REQUESTS", "1")), index < failing, None))
    (Path(workdir).parent / "turns.json").write_text(json.dumps(given))
    _build(workdir, conn)


def paced(workdir: str, conn: Any) -> None:
    """Reads its files on ``PACED_HOST``."""
    _paced(workdir, conn, os.environ["PACED_HOST"])


def paced_elsewhere(workdir: str, conn: Any) -> None:
    """Asks for a turn on a host the build does not read."""
    _paced(workdir, conn, "elsewhere.example.invalid")


def _misbehave(workdir: str, conn: Any, then: str) -> None:
    """Ask for a turn on ``PACED_HOST`` and then do ``then`` instead of reading and accounting as a child should."""
    if _job(workdir)["mode"] == "plan":
        _plan(workdir, conn)
        return
    host = os.environ["PACED_HOST"]
    if then == "account_unasked":
        conn.send(("account", host, 1, False, None))
        time.sleep(30)
        return
    conn.send(("pace", host))
    if then == "pace_twice":
        conn.send(("pace", host))
        time.sleep(30)
        return
    if conn.recv() != ("go",):
        raise RuntimeError("no turn")
    if then == "hang":
        time.sleep(3600)
    elif then == "die":
        os._exit(0)
    elif then == "odd_account":
        conn.send(("account", host, "many", False, None))
        time.sleep(30)


def paced_hang(workdir: str, conn: Any) -> None:
    """Gets its turn and hangs while it holds the place, as a read stuck in GDAL would."""
    _misbehave(workdir, conn, "hang")


def paced_die(workdir: str, conn: Any) -> None:
    """Gets its turn and dies before it accounts."""
    _misbehave(workdir, conn, "die")


def paced_odd_account(workdir: str, conn: Any) -> None:
    """Accounts with a count that is not one."""
    _misbehave(workdir, conn, "odd_account")


def paced_account_unasked(workdir: str, conn: Any) -> None:
    """Accounts for a turn it never asked for."""
    _misbehave(workdir, conn, "account_unasked")


def paced_pace_twice(workdir: str, conn: Any) -> None:
    """Asks for a second turn before the first is given."""
    _misbehave(workdir, conn, "pace_twice")
