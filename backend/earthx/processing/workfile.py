"""The one place `processing` opens a file itself: inside the run's work directory (plan M4-07a §3.5, F4).

Every source is read through `readers`, where each address has passed
``check_url`` (adr/0014 §7.3 point 1). What remains are the core's own files —
intermediate passes, the result, the AOI mask — and they are opened here and
nowhere else, by a bare file name under the work directory. No URL, no ``/vsi…``
path, no path that leaves the directory, not by ``..`` and not by a symbolic link
(Otto, 06.10.2026). The one other thing opened here is a view of a single band of a work file
that is already open (:func:`open_workfile_band`, NM4-43b). ``test_no_direct_open.py`` holds every other module of
`processing` to that over its syntax tree.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import rasterio

from earthx.processing.errors import WorkfileRejected

__all__ = ["open_workfile", "open_workfile_band", "workfile_path"]

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


def open_workfile_band(source: Any, band: int) -> Any:
    """Band ``band`` (1-based) of the open work file ``source`` as a read-only dataset of one band.

    ``source`` is a file of the core's intermediate form: ``float64``, NaN as nodata. The view is a VRT
    document handed to ``rasterio.open`` as text, so nothing is written to the work directory, and it
    names the file of ``source`` only after that has passed :func:`workfile_path`.
    """
    if not 1 <= band <= source.count:
        raise WorkfileRejected("a work file has no such band")
    path = Path(source.name)
    if workfile_path(path.parent, path.name) != path.resolve():
        raise WorkfileRejected("a work file stays inside the work directory")
    height, width = source.block_shapes[band - 1]
    document = (
        f'<VRTDataset rasterXSize="{source.width}" rasterYSize="{source.height}">'
        f"<SRS>{escape(source.crs.to_wkt())}</SRS>"
        f"<GeoTransform>{', '.join(repr(value) for value in source.transform.to_gdal())}</GeoTransform>"
        '<VRTRasterBand dataType="Float64" band="1"><NoDataValue>nan</NoDataValue>'
        f'<SimpleSource><SourceFilename relativeToVRT="0">{escape(str(path))}</SourceFilename>'
        f"<SourceBand>{band}</SourceBand>"
        f'<SourceProperties RasterXSize="{source.width}" RasterYSize="{source.height}" DataType="Float64" '
        f'BlockXSize="{width}" BlockYSize="{height}"/>'
        f'<SrcRect xOff="0" yOff="0" xSize="{source.width}" ySize="{source.height}"/>'
        f'<DstRect xOff="0" yOff="0" xSize="{source.width}" ySize="{source.height}"/>'
        "</SimpleSource></VRTRasterBand></VRTDataset>"
    )
    return rasterio.open(document)
