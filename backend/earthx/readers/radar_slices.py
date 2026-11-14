"""A result in radar geometry drawn slice by slice exactly as its scenes are drawn (DS-04d, Otto 14.11.2026).

A scene placed by GCPs is drawn through a ``WarpedVRT`` with the thin-plate spline of its GCPs. GDAL lays that warp on
an intermediate grid whose origin and pixel size follow from the size of the file and its GCPs. A result is a window of
the scene, or of several slices joined: drawn by its own GCPs, it gets another intermediate grid (and, for a pass, one
spline through the GCPs of all slices), so its pixels do not lie on the pixels of the scenes (measured: most pixels of
a tile off by one, and more at the seam of a pass).

So the job writes, beside its own GCPs, where each slice lies in the result and the slice's own size and GCPs
(:data:`SLICES_TAG`). For the map, each slice is rebuilt as a virtual file of the scene's size with the scene's GCPs,
the result's rows at their place and nothing elsewhere (:func:`slice_document`); warped like the scene, every pixel of
the result lies exactly on its source pixel.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from rasterio.crs import CRS

__all__ = ["SLICES_TAG", "slice_document", "slices_of", "slices_tag"]

#: The dataset tag of a result in radar geometry that names its slices (JSON).
SLICES_TAG = "EARTHX_RADAR_SLICES"

_GDAL_TYPES = {
    "uint8": "Byte", "int8": "Int8", "uint16": "UInt16", "int16": "Int16", "uint32": "UInt32", "int32": "Int32",
    "float32": "Float32", "float64": "Float64",
}  # fmt: skip


def slices_tag(slices: Sequence[Mapping[str, Any]]) -> str:
    """The tag for ``slices``: per slice its ``width`` and ``height``, ``row`` and ``col`` (where its first pixel lies in
    the result, negative where the result starts inside it), ``gcp_crs``, and ``gcps`` as ``[row, col, x, y, z]``."""
    return json.dumps({"version": 1, "slices": list(slices)}, separators=(",", ":"), allow_nan=False)


def slices_of(tags: Mapping[str, str]) -> list[dict[str, Any]] | None:
    """The slices a result names in its tags, or ``None`` for a file that names none."""
    text = tags.get(SLICES_TAG)
    if not text:
        return None
    data = json.loads(text)
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("slices"), list):
        raise ValueError(f"{SLICES_TAG} is not a list of slices of version 1")
    return data["slices"]


def _nodata(value: float | None) -> str:
    if value is None:
        return ""
    return "<NoDataValue>nan</NoDataValue>" if math.isnan(value) else f"<NoDataValue>{value!r}</NoDataValue>"


def slice_document(path: str, dataset: Any, piece: Mapping[str, Any]) -> str | None:
    """A VRT of the scene's size and GCPs holding the rows of ``dataset`` (opened from ``path``) that belong to the
    slice ``piece``; ``None`` where the result holds none of it. Opened as text, nothing is written to disk."""
    width, height = int(piece["width"]), int(piece["height"])
    row, col = int(piece["row"]), int(piece["col"])
    top, bottom = max(0, row), min(dataset.height, row + height)
    left, right = max(0, col), min(dataset.width, col + width)
    if bottom <= top or right <= left:
        return None
    rect = (
        f'<SrcRect xOff="{left}" yOff="{top}" xSize="{right - left}" ySize="{bottom - top}"/>'
        f'<DstRect xOff="{left - col}" yOff="{top - row}" xSize="{right - left}" ySize="{bottom - top}"/>'
    )
    gcps = "".join(
        f'<GCP Id="{index}" Pixel={quoteattr(repr(float(c)))} Line={quoteattr(repr(float(r)))} '
        f"X={quoteattr(repr(float(x)))} Y={quoteattr(repr(float(y)))} Z={quoteattr(repr(float(z)))}/>"
        for index, (r, c, x, y, z) in enumerate(piece["gcps"])
    )
    projection = quoteattr(CRS.from_user_input(piece["gcp_crs"]).to_wkt())
    bands = "".join(
        f'<VRTRasterBand dataType="{_GDAL_TYPES[dtype]}" band="{band}">{_nodata(dataset.nodata)}'
        f'<SimpleSource><SourceFilename relativeToVRT="0">{escape(path)}</SourceFilename>'
        f"<SourceBand>{band}</SourceBand>{rect}</SimpleSource></VRTRasterBand>"
        for band, dtype in enumerate(dataset.dtypes, start=1)
    )
    return (
        f'<VRTDataset rasterXSize="{width}" rasterYSize="{height}">'
        f"<GCPList Projection={projection}>{gcps}</GCPList>{bands}</VRTDataset>"
    )
