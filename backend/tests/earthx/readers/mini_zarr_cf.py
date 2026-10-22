"""A synthetic Zarr store whose variables carry CF scaling, like the EOPF products.

The real stores keep ``uint16`` with ``scale_factor 0.0001``, ``add_offset -0.1``
and ``_FillValue 0`` as attributes (adr/0014 §3.11, §17.10), and the reader decodes
them by default. This store copies exactly that shape, so a test can tell a decoded
read from a raw one (``decode_cf=False``, §5.4, F7a) by value.

Two variables, ``b04`` and ``b08``, on one 10 m grid in UTM 32N; the raw values
are fixed rather than random, so expected physical values are written down in the
test rather than recomputed by it. ``0`` is the fill value and marks one corner.

A second group, ``scl20m``, holds the scene classification layer ``scl`` the way the EOPF
products do (``uint8``, classes 0 to 11, CF attributes ``scale_factor 1``, ``add_offset 0``,
``_FillValue 0``) on the 20 m grid of the same extent, so the operator ``mask`` reads a nested
grid from a Zarr store (M4-18a). Its fill value marks the top left 2×2 pixels, the same ground
as the fill corner of the bands.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy
import xarray

from tests.earthx.readers.mini_zarr import HOST, STORE_PATH

GROUP = "r10m"
SCL_GROUP = "scl20m"
SIZE = 48
SCL_SIZE = SIZE // 2
SCL_RESOLUTION_M = 2 * 10.0
CHUNK = (16, 16)
ORIGIN_X, ORIGIN_Y = 600000.0, 5700000.0
ITEM_CRS = "EPSG:32632"
RESOLUTION_M = 10.0

SCALE = 0.0001
OFFSET = -0.1
FILL = 0

#: The asset address of the group, as an item would name it; a variable follows it.
GROUP_URL = f"https://{HOST}{STORE_PATH}/{GROUP}"
SCL_URL = f"https://{HOST}{STORE_PATH}/{SCL_GROUP}"


def raw_band(name: str) -> numpy.ndarray:
    """The stored ``uint16`` values of one variable, fill value in the top left 4×4."""
    base = {"b04": 1200, "b08": 3400}[name]
    rows, cols = numpy.indices((SIZE, SIZE))
    raw = (base + rows * 7 + cols * 3).astype("uint16")
    raw[:4, :4] = FILL
    return raw


def raw_classes() -> numpy.ndarray:
    """The stored ``uint8`` classes: every value 1 to 11 occurs, ``0`` (fill) in the top left 2×2."""
    rows, cols = numpy.indices((SCL_SIZE, SCL_SIZE))
    raw = (1 + (rows * 5 + cols * 3) % 11).astype("uint8")
    raw[:2, :2] = FILL
    return raw


def build_mini_zarr_cf(root: Path) -> Path:
    """Write the store under ``root`` through xarray's own CF encoding and return it."""
    variables = {}
    for name in ("b04", "b08"):
        raw = raw_band(name)
        physical = numpy.where(raw == FILL, numpy.nan, raw * SCALE + OFFSET)
        variables[name] = (("y", "x"), physical)
    dataset = xarray.Dataset(
        variables,
        coords={
            "y": ORIGIN_Y - (numpy.arange(SIZE) + 0.5) * RESOLUTION_M,
            "x": ORIGIN_X + (numpy.arange(SIZE) + 0.5) * RESOLUTION_M,
        },
    )
    encoding = {
        name: {"dtype": "uint16", "scale_factor": SCALE, "add_offset": OFFSET, "_FillValue": FILL, "chunks": CHUNK}
        for name in dataset.data_vars
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dataset.to_zarr(root, group=GROUP, mode="a", zarr_format=3, consolidated=True, encoding=encoding)
    raw = raw_classes()
    classes = xarray.Dataset(
        {"scl": (("y", "x"), numpy.where(raw == FILL, numpy.nan, raw.astype("float32")))},
        coords={
            "y": ORIGIN_Y - (numpy.arange(SCL_SIZE) + 0.5) * SCL_RESOLUTION_M,
            "x": ORIGIN_X + (numpy.arange(SCL_SIZE) + 0.5) * SCL_RESOLUTION_M,
        },
    )
    layer_encoding = {"scl": {"dtype": "uint8", "scale_factor": 1.0, "add_offset": 0.0, "_FillValue": FILL, "chunks": (12, 12)}}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        classes.to_zarr(root, group=SCL_GROUP, mode="a", zarr_format=3, consolidated=True, encoding=layer_encoding)
    return root


def store_bounds() -> tuple[float, float, float, float]:
    side = SIZE * RESOLUTION_M
    return (ORIGIN_X, ORIGIN_Y - side, ORIGIN_X + side, ORIGIN_Y)
