"""Stand-ins for the child process, and the real child with its sources put behind two seams.

A target takes ``(workdir, conn)`` like :func:`earthx.jobs.child.run_child` and speaks the
same messages over the pipe. They are module-level functions because a spawned process
finds its target by import; and they import almost nothing at the top, so a child that
runs one does not carry what the test process has loaded (psycopg, botocore, rasterio).

What a target does is chosen by environment variables the test sets before it starts the
supervisor: a spawned process inherits them.
"""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path
from typing import Any


def _write_result(workdir: str) -> dict[str, Any]:
    (Path(workdir) / "result.tif").write_bytes(b"result-bytes")
    (Path(workdir) / "mask.tif").write_bytes(b"mask-bytes")
    return {"blocks": 2, "bytes": 12, "peak_mb": 1.0, "width": 4, "height": 4, "bands": 1, "properties": {}}


def _delay() -> float:
    return float(os.environ.get("CHILD_DELAY", "0"))


def succeed(workdir: str, conn: Any) -> None:
    """Two progress messages, ``CHILD_DELAY`` seconds apart, then result and mask."""
    conn.send(("progress", 1, 2, 1.0))
    time.sleep(_delay())
    conn.send(("progress", 2, 2, 1.0))
    conn.send(("done", _write_result(workdir)))
    conn.close()


def fail(workdir: str, conn: Any) -> None:
    """Report ``CHILD_KIND`` as the failure."""
    conn.send(("progress", 1, 2, 1.5))
    conn.send(("failed", os.environ["CHILD_KIND"]))
    conn.close()


def die_by_signal(workdir: str, conn: Any) -> None:
    """What the kernel's out-of-memory killer does: the child ends by ``SIGKILL`` with no word."""
    conn.send(("progress", 1, 4, 321.5))
    time.sleep(0.2)
    os.kill(os.getpid(), signal.SIGKILL)


def exit_silently(workdir: str, conn: Any) -> None:
    sys.exit(0)


def hang(workdir: str, conn: Any) -> None:
    """Ignores the cancel message and keeps going: only a kill ends it."""
    conn.send(("progress", 1, 100, 1.0))
    while True:
        time.sleep(0.05)


def cooperate(workdir: str, conn: Any) -> None:
    """Runs block by block and stops at the next one after the cancel message, like the core."""
    from earthx.jobs.child import guard
    from earthx.processing import RunCancelled

    def work() -> None:
        for block in range(1, 1000):
            conn.send(("progress", block, 1000, 1.0))
            if conn.poll() and conn.recv() == "cancel":
                raise RunCancelled()
            time.sleep(0.02)

    guard(conn, work)


def run_out_of_memory(workdir: str, conn: Any) -> None:
    """A real `MemoryError`: the address space is limited, then more is asked for, through the child's guard."""
    import resource

    from earthx.jobs.child import guard

    def work() -> None:
        conn.send(("progress", 1, 2, 1.0))
        limit = 700 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        blocks = [bytearray(100 * 1024 * 1024) for _ in range(20)]  # 2 GB against a limit of 700 MB
        conn.send(("done", {"blocks": len(blocks)}))

    guard(conn, work)


def probe_modules(conn: Any) -> None:
    """What the child has loaded after it imported what `jobs` makes it import; `boto3` hidden as in the image."""
    import multiprocessing

    sys.modules["boto3"] = None  # type: ignore[assignment]
    import earthx.jobs.child  # noqa: F401

    loaded = sorted(name for name, module in sys.modules.items() if module is not None)
    conn.send((multiprocessing.get_start_method(), loaded))
    conn.close()


def end_to_end(workdir: str, conn: Any) -> None:
    """The real child on a synthetic scene: the readers' two last steps point at a local COG.

    ``CHILD_COG`` is the file. Everything else — `check_url`, the allowlist, the reader,
    the core — runs as in production (the seams of tests/earthx/processing/sources.py).
    `boto3` is hidden first, so the peak measured is the image's.
    """
    sys.modules["boto3"] = None  # type: ignore[assignment]
    import earthx.readers.access as read_access
    import earthx.readers.cog as cog_reader
    from earthx.jobs.child import run_child

    cog = os.environ["CHILD_COG"]
    cog_reader.vsicurl_path = lambda checked: cog
    read_access.resolve_host = lambda host, port=443: ("93.184.216.34",)
    run_child(workdir, conn)


def fail_first_attempt(workdir: str, conn: Any) -> None:
    """The first attempt of a run fails with ``CHILD_KIND``; the next ones succeed. The work directory is `<run>-<attempt>`."""
    if int(Path(workdir).name.split("-")[1]) == 1:
        fail(workdir, conn)
    else:
        succeed(workdir, conn)


def done_without_files(workdir: str, conn: Any) -> None:
    """Claims success but wrote nothing."""
    conn.send(("done", {"blocks": 1}))
    conn.close()


def write_modules(workdir: str, conn: Any) -> None:
    """Write what this child has loaded to ``PROBE_OUT``, then say it failed (there is nothing to upload)."""
    import json

    sys.modules["boto3"] = None  # type: ignore[assignment]
    import earthx.jobs.child  # noqa: F401

    loaded = sorted(name for name, module in sys.modules.items() if module is not None)
    Path(os.environ["PROBE_OUT"]).write_text(json.dumps(loaded))
    conn.send(("failed", "unknown"))
    conn.close()
