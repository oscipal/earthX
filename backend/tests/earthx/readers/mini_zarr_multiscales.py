"""A second synthetic Zarr store, this one with a `multiscales` layout.

`mini_zarr.py` builds the M2-09a shape — resolution groups as plain siblings, no
`multiscales` anywhere, which is the fallback case (§12.11 point 2). This module
builds the other shape, the one M2-09b-2's level choice is for: a parent group
(``reflectance``, standing in for the measured ``measurements/reflectance``, §12.3)
that carries a ``multiscales`` attribute naming three child groups as its
``layout``, each with its own ``spatial:transform``. The first element of that
affine is the resolution a level stands for, exactly as §12.3 measured it.

Three levels are enough to tell "coarsest that is still fine enough", "finest
available" and "coarsest available" apart, which is everything
`readers.zarr_reader._select_level` decides between.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy
import xarray
import zarr

from tests.earthx.readers.mini_zarr import BASE_URL, HOST, POLICY, from_memory, serve_store  # noqa: F401

#: Resolution groups, coarsest last — same convention as `mini_zarr.GROUPS`.
GROUPS = {"r10m": 10.0, "r20m": 20.0, "r60m": 60.0}

#: The variable every group carries.
VARIABLE = "b04"

#: Pixels per side of the finest group; the others cover the same ground at their
#: own pixel size, same rule as `mini_zarr.FINEST_SIZE`. A multiple of 6 (the ratio
#: between the finest and the coarsest level here), so no level degenerates to a
#: single pixel wide.
FINEST_SIZE = 24

#: Upper-left corner, in the same unnamed metres as `mini_zarr` uses.
ORIGIN_X, ORIGIN_Y = 100000.0, 5800000.0
ITEM_CRS = "EPSG:32632"

#: The group the `multiscales` attribute sits on — the parent of every level.
PARENT_GROUP = "reflectance"

#: A level `multiscales` names that the store does not actually have — the
#: "kaputtes layout" case: an entry naming a level with no group behind it.
DANGLING_LEVEL = "r120m"


def build_mini_zarr_multiscales(root: Path) -> Path:
    """Write the store under ``root``, with `multiscales` on ``PARENT_GROUP``."""
    layout = []
    for name, resolution in GROUPS.items():
        dataset = _level(resolution)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            dataset.to_zarr(
                root,
                group=f"{PARENT_GROUP}/{name}",
                mode="a",
                zarr_format=3,
                consolidated=False,
            )
        layout.append({"asset": name, "spatial:transform": [resolution, 0.0, ORIGIN_X, 0.0, -resolution, ORIGIN_Y]})
    parent = zarr.open_group(store=str(root), path=PARENT_GROUP, mode="a", zarr_format=3)
    parent.attrs["multiscales"] = {"layout": layout}
    zarr.consolidate_metadata(str(root))
    return root


def _level(resolution: float) -> xarray.Dataset:
    size = int(FINEST_SIZE * GROUPS["r10m"] / resolution)
    generator = numpy.random.default_rng(seed=int(resolution))
    return xarray.Dataset(
        {VARIABLE: (("y", "x"), generator.integers(1, 10_000, (size, size)).astype("uint16"))},
        coords={
            "y": ORIGIN_Y - (numpy.arange(size) + 0.5) * resolution,
            "x": ORIGIN_X + (numpy.arange(size) + 0.5) * resolution,
        },
    )


def group_size(resolution: float) -> int:
    """The pixel side of the level at ``resolution`` — what a test checks a read against."""
    return int(FINEST_SIZE * GROUPS["r10m"] / resolution)
