"""The one place `processing` opens a file itself: inside the run's work directory (plan M4-07a §3.5, F4).

Every source is read through `readers`, where each address has passed
``check_url`` (adr/0014 §7.3 point 1). What remains are the core's own files —
intermediate passes, the result, the AOI mask — and they are opened here and
nowhere else, by a bare file name under the work directory. No URL, no ``/vsi…``
path, no path that leaves the directory, not by ``..`` and not by a symbolic link
(Otto, 06.10.2026). ``test_no_direct_open.py`` holds every other module of
`processing` to that over its syntax tree.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import rasterio

from earthx.processing.errors import WorkfileRejected

__all__ = ["open_workfile", "workfile_path"]

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def workfile_path(workdir: Path, name: str) -> Path:
    """``workdir / name``, or :class:`WorkfileRejected` if that is anything but a plain file there."""
    if not isinstance(workdir, Path):
        raise WorkfileRejected("the work directory is a pathlib.Path")
    if not isinstance(name, str) or not _NAME.match(name) or ".." in name:
        raise WorkfileRejected("a work file is a plain file name")
    root = workdir.resolve(strict=True)
    if not root.is_dir():
        raise WorkfileRejected("the work directory is not a directory")
    path = root / name
    if path.is_symlink() or path.resolve().parent != root:
        raise WorkfileRejected("a work file stays inside the work directory")
    return path


def open_workfile(workdir: Path, name: str, mode: str = "r", **profile: Any) -> Any:
    """Open a GeoTIFF in the work directory for reading (``"r"``) or writing (``"w"``)."""
    if mode not in ("r", "w"):
        raise WorkfileRejected("a work file is opened for reading or writing")
    return rasterio.open(workfile_path(workdir, name), mode, **profile)
