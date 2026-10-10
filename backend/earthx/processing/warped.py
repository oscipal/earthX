"""One item's asset warped onto a given grid, read block by block (M4-11a, M4-12a).

The export job and the mosaic job read an item the way ``rio_tiler`` reads it, but into a
grid of their own and a block at a time: a ``WarpedVRT`` onto the output grid with
``nearest``, the validity from the value of nodata or, where a file declares none, from an
alpha band. Two ways, because the crop does two (``alone``): a single item as the crop's
windowed path reads it, several as ``Reader.part`` reads each item of a mosaic.

Nothing here opens an address; the caller hands in a dataset that already passed
``check_url`` in `readers`.
"""

from __future__ import annotations

import math
from contextlib import ExitStack
from typing import Any

import numpy
from rasterio.dtypes import dtype_ranges
from rasterio.enums import ColorInterp, Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window
from rio_tiler.constants import WGS84_CRS

from earthx.readers import process_gdal_options

__all__ = ["WarpedItem", "cache_per_item"]

#: The least read cache an open item keeps (:func:`cache_per_item`): a COG block of
#: 1024² ``uint16`` is 2 MB uncompressed, deflated about half of that.
_MIN_CACHE_PER_ITEM = 1024 * 1024


def cache_per_item(items: int) -> int:
    """The share of ``VSI_CACHE_SIZE`` each open item of a group gets, so that a group costs what one item costs.

    GDAL gives every open file a read cache of its own of ``VSI_CACHE_SIZE`` (64 MB for a
    worker, `readers.process_gdal_options`), taken when the file is opened. The crop opens
    the items of a mosaic one after the other; the export and the mosaic job keep them open together, so the
    one item's budget is split between them (Otto, 08.10.2026: the limit holds per item;
    measured +64 MB per further item before this). A cache changes no value read.
    """
    budget = int(process_gdal_options()["VSI_CACHE_SIZE"])
    return max(_MIN_CACHE_PER_ITEM, budget // items)


class WarpedItem:
    """One item's asset warped onto the output grid, read block by block.

    ``crs`` is the CRS of the grid (EPSG:4326 for the crop, the mosaic's own for a mosaic);
    ``warp_options`` are further ``WarpedVRT`` options, none for the export so that its
    bytes stay those of the crop.
    """

    def __init__(
        self,
        dataset: Any,
        transform: Any,
        width: int,
        height: int,
        *,
        alone: bool,
        stack: ExitStack,
        crs: Any = WGS84_CRS,
        warp_options: dict[str, Any] | None = None,
    ):
        options = warp_options or {}
        self.alpha: int | None = None
        if alone:
            # The crop's windowed path (`_write_native_windowed_cog`): a plain warp.
            self.vrt = stack.enter_context(
                WarpedVRT(
                    dataset, crs=crs, transform=transform, width=width, height=height,
                    resampling=Resampling.nearest, **options,
                )  # fmt: skip
            )
            self.nodata = self.vrt.nodata
            self.indexes = list(range(1, self.vrt.count + 1))
            self.mosaic = False
            return
        # As `rio_tiler.reader.read` warps one item of a mosaic (`Reader.part`).
        self.mosaic = True
        nodata = dataset.nodata
        params: dict[str, Any] = {
            "crs": crs, "add_alpha": True, "resampling": Resampling.nearest, "dtype": dataset.dtypes[0],
        }  # fmt: skip
        if nodata is not None:
            params.update({"nodata": nodata, "add_alpha": False, "src_nodata": nodata})
        source_alpha = ColorInterp.alpha in dataset.colorinterp
        if source_alpha:
            params["add_alpha"] = False
        self.vrt = stack.enter_context(
            WarpedVRT(dataset, transform=transform, width=width, height=height, **params, **options)
        )
        self.nodata = nodata
        interp = self.vrt.colorinterp
        self.indexes = [i + 1 for i, colour in enumerate(interp) if colour != ColorInterp.alpha]
        if ColorInterp.alpha in interp and nodata is None:
            self.alpha = interp.index(ColorInterp.alpha) + 1
        self._source_alpha = source_alpha

    @property
    def dtype(self) -> str:
        return self.vrt.dtypes[self.indexes[0] - 1]

    def read(self, window: Window) -> numpy.ma.MaskedArray:
        if not self.mosaic:
            return self.vrt.read(window=window, masked=True)
        if self.alpha is not None:
            values = self.vrt.read(indexes=[*self.indexes, self.alpha], window=window)
            values, alpha = values[:-1], values[-1]
            _, opaque = dtype_ranges[str(values.dtype)]
            if not self._source_alpha and alpha.max() == 255:
                opaque = 255
            data = numpy.ma.MaskedArray(values)
            data.mask = numpy.broadcast_to(alpha != opaque, values.shape).copy()
            return data
        data = self.vrt.read(indexes=self.indexes, window=window, masked=True, fill_value=self.nodata)
        if self.nodata is not None:
            data.mask = numpy.isnan(data.data) if math.isnan(self.nodata) else data.data == self.nodata
        return data
