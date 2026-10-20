"""Start targets of the two shells around the core, each in a fresh ``spawn`` process (adr/0016 §7.2).

Both put the sources behind the same seams before they import their entry: the last step
of the COG path (``vsicurl_path``) points at local files, the resolver gives a fixed
public answer, the Zarr store answers through a ``MockTransport``. ``check_url``, the
allowlist, the readers and the core run as in production. ``boto3`` is hidden first,
as it is absent in the image.

What a target reads comes from environment variables the test sets before it starts the
process: ``RUNNER_COGS`` (JSON, address → file) and ``RUNNER_ZARR`` (the store's root).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _seams() -> None:
    sys.modules["boto3"] = None  # type: ignore[assignment]
    import httpx

    import earthx.readers.access as read_access
    import earthx.readers.cog as cog_reader
    import earthx.readers.zarr_reader as zarr_reader
    from earthx.gateway import Gateway
    from tests.earthx.readers import mini_zarr

    files = json.loads(os.environ.get("RUNNER_COGS", "{}"))
    cog_reader.vsicurl_path = lambda checked: files[getattr(checked, "url", str(checked))]
    read_access.resolve_host = mini_zarr.from_memory
    root = os.environ.get("RUNNER_ZARR")
    if root:

        def open_gateway(policy: Any, resolve: Any) -> Gateway:
            handler = httpx.MockTransport(lambda request: mini_zarr._respond(Path(root), request))
            return Gateway(policy, transport=handler, resolve=resolve)

        zarr_reader.open_gateway = open_gateway


def job(workdir: str, conn: Any) -> None:
    """The child `jobs` starts for a run, on ``workdir/recipe.json``."""
    _seams()
    from earthx.jobs.child import run_child

    run_child(workdir, conn)


def runner(recipe: str, out: str, conn: Any) -> None:
    """``python -m earthx.runner run`` with the synthetic registry; sends the exit code."""
    _seams()
    from earthx.runner.cli import main
    from tests.earthx.runner.support import registry

    conn.send(main(["run", recipe, "--out", out], registry=registry()))
    conn.close()


def probe_modules(conn: Any) -> None:
    """What a process has loaded after importing the runner's entry, `boto3` hidden as in the image."""
    sys.modules["boto3"] = None  # type: ignore[assignment]
    import earthx.runner.cli  # noqa: F401

    conn.send(sorted(name for name, module in sys.modules.items() if module is not None))
    conn.close()
