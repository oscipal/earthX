"""A third synthetic Zarr store: one group, three single-band variables, each a
distinct constant value — built to show a composite tile in one glance rather
than to resemble the real EOPF layout the other two stores copy.

Where `mini_zarr.py`'s bands differ by random noise (real but not eyeballable)
and carry a `time` axis (which itself becomes extra bands, per its own docstring),
this store isolates exactly one thing: whether three *named* variables of a group
come back as three distinguishable channels of one image, in the order they were
asked for. A constant value per band makes that a direct equality check on pixels,
not a statistical one.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy
import xarray

from tests.earthx.readers.mini_zarr import BASE_URL, HOST, POLICY, from_memory, serve_store  # noqa: F401

#: One value per band, chosen far enough apart that a decode or channel-order bug
#: cannot land on another band's value by accident.
BAND_VALUES = {"b04": 4000, "b03": 12000, "b02": 20000}

#: The one group this store has.
GROUP = "r10m"

#: Small enough that a tile crosses several chunks — the laziness this store is
#: also used to check (a window must not cost the whole band).
SIZE = 64
CHUNK = (16, 16)

ORIGIN_X, ORIGIN_Y = 600000.0, 5700000.0
ITEM_CRS = "EPSG:32632"
RESOLUTION_M = 10.0


def build_mini_zarr_composite(root: Path) -> Path:
    dataset = xarray.Dataset(
        {name: (("y", "x"), numpy.full((SIZE, SIZE), value, dtype="uint16")) for name, value in BAND_VALUES.items()},
        coords={
            "y": ORIGIN_Y - (numpy.arange(SIZE) + 0.5) * RESOLUTION_M,
            "x": ORIGIN_X + (numpy.arange(SIZE) + 0.5) * RESOLUTION_M,
        },
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dataset.to_zarr(
            root,
            group=GROUP,
            mode="a",
            zarr_format=3,
            consolidated=True,
            encoding={name: {"chunks": CHUNK} for name in dataset.data_vars},
        )
    return root


def store_bounds() -> tuple[float, float, float, float]:
    side = SIZE * RESOLUTION_M
    return (ORIGIN_X, ORIGIN_Y - side, ORIGIN_X + side, ORIGIN_Y)
