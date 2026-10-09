"""Names the function a child process runs, without importing it in the supervisor.

A spawned child finds its target by pickle, which needs the function object, and the
object would pull `processing` (rasterio, GDAL, numpy) into the supervisor, which has no
use for it (adr/0013 §5.3, plan M4-08a K3). :class:`ChildTarget` is a small callable that
pickles as its two names and imports the function only in the child.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

__all__ = ["ChildTarget"]


@dataclass(frozen=True, slots=True)
class ChildTarget:
    module: str = "earthx.jobs.child"
    name: str = "run_child"

    def __call__(self, workdir: str, conn: Any) -> None:
        getattr(importlib.import_module(self.module), self.name)(workdir, conn)
