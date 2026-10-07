"""One input asset, opened once, read in physical values: for the job (T2) and for the tile (T1).

It used to be a private class of :mod:`earthx.processing.core`. It is public because the
tile of `api` reads inputs the same way a job does (adr/0014 §6.2): the same readers,
the same scaling of §5.4 (:func:`~earthx.processing.scaling.apply_scaling`), the same
band names, the same rule for rasters that are not one grid. Nothing here opens an
address; the caller hands in an asset that already passed ``check_url``.

**Rasters of different resolution (plan M4-09, F2).** Assets of one input share a grid
when CRS, transform and size agree. Otherwise they may still be *nested*: the same CRS
and the same extent, north-up, and every pixel size a whole multiple of the finest.
Then the coarser assets are read onto the finest grid with ``nearest``, which only
repeats pixels, and the result is marked resampled (principle 2.9). Anything else is
:class:`~earthx.processing.errors.GridMismatch`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from contextlib import ExitStack
from typing import Any

from rasterio.crs import CRS
from rasterio.transform import Affine
from rasterio.windows import Window
from rio_tiler.models import ImageData

from earthx.processing.errors import GridMismatch
from earthx.processing.recipe import ResolvedInput
from earthx.processing.scaling import Scaling, apply_scaling, scaling_for_cog, scaling_for_zarr
from earthx.readers.cog import AssetPath, CogReader
from earthx.readers.zarr_reader import VARIABLE_LIST_SEPARATOR, ZarrAsset, ZarrReader

__all__ = ["Source", "common_grid", "expected_band_names", "merge_images"]

#: Relative slack when comparing pixel sizes and extents of two rasters.
_GRID_TOLERANCE = 1e-6


class Source:
    """One input asset, opened once: its grid, its scaling, its blocks and tiles in physical values."""

    def __init__(self, entry: ResolvedInput, reader: CogReader | ZarrReader) -> None:
        self.entry = entry
        self.reader = reader
        self.crs = CRS.from_user_input(reader.crs)
        self.transform: Affine = reader.transform
        self.width: int = reader.width
        self.height: int = reader.height
        what = f"{entry.asset.dataset_id}/{entry.asset.item_id}/{entry.asset.asset}"
        if isinstance(reader, CogReader):
            dataset = reader.dataset
            self.scaling: Scaling = scaling_for_cog(entry.scaling, entry.bands, dataset.scales, dataset.offsets, what)
            count = dataset.count
            self.names = [entry.asset.asset] if count == 1 else [f"{entry.asset.asset}_{i + 1}" for i in range(count)]
            self.data_types = list(dataset.dtypes)
            self.nodata = [dataset.nodata] * count
        else:
            arrays = reader.arrays
            source = [array.attrs if entry.scaling == "item" else array.encoding for array in arrays]
            self.scaling = scaling_for_zarr(entry.scaling, entry.bands, source, what)
            self.names = [str(array.name) for array in arrays]
            self.data_types = [str(array.dtype) for array in arrays]
            self.nodata = [array.rio.nodata for array in arrays]
        self.nodata = [None if value is None else float(value) for value in self.nodata]

    @classmethod
    def open(cls, entry: ResolvedInput, target: AssetPath | ZarrAsset, stack: ExitStack) -> Source:
        """The reader for ``target`` entered into ``stack`` (closed with it), and the source on top of it."""
        reader = CogReader(target) if isinstance(target, AssetPath) else ZarrReader(target)
        stack.enter_context(reader)
        return cls(entry, reader)

    def same_grid(self, other: Source) -> bool:
        return (
            self.crs == other.crs
            and self.transform.almost_equals(other.transform)
            and (self.width, self.height) == (other.width, other.height)
        )

    def _named(self, image: ImageData) -> ImageData:
        image = apply_scaling(image, self.scaling)
        if len(self.names) == image.count:
            image.band_names = list(self.names)
        return image

    def read(self, window: Window, grid: Affine | None = None) -> ImageData:
        """``window`` of the grid ``grid`` (this source's own by default), in physical values.

        An exact window, no warp, when ``grid`` is this source's own (or equal to it up to
        rounding, so that two assets of one grid are read with the very same bounds); on a
        finer grid the reader repeats pixels with ``nearest``.
        """
        transform = self.transform if grid is None or self.transform.almost_equals(grid) else grid
        left, top = transform @ (window.col_off, window.row_off)
        right, bottom = transform @ (window.col_off + window.width, window.row_off + window.height)
        image = self.reader.part(
            (left, bottom, right, top),
            dst_crs=self.crs,
            bounds_crs=self.crs,
            width=int(window.width),
            height=int(window.height),
            max_size=None,
        )
        return self._named(image)

    def read_tile(self, x: int, y: int, z: int, **options: Any) -> ImageData:
        """One map tile, in physical values; ``options`` are the reader's own (``tilesize`` and the like)."""
        return self._named(self.reader.tile(x, y, z, **options))


def expected_band_names(entry: ResolvedInput) -> list[str] | None:
    """The names the bands of this asset will carry, or ``None`` where only the file knows.

    A Zarr asset is addressed per variable, so its names are known. A COG asset has one
    band named like the asset, or ``<asset>_<i>`` per band; the item says how many only
    where it describes its bands.
    """
    asset = entry.asset
    if asset.reader == "zarr":
        return asset.variable.split(VARIABLE_LIST_SEPARATOR) if asset.variable else None
    if not entry.bands:
        return None
    if len(entry.bands) == 1:
        return [asset.asset]
    return [f"{asset.asset}_{i + 1}" for i in range(len(entry.bands))]


def _ratio(coarse: float, fine: float) -> int | None:
    ratio = coarse / fine
    nearest = round(ratio)
    return nearest if nearest >= 1 and math.isclose(ratio, nearest, rel_tol=_GRID_TOLERANCE) else None


def _nested_in(finest: Source, other: Source) -> bool:
    if other.crs != finest.crs:
        return False
    for source in (finest, other):
        if source.transform.b != 0 or source.transform.d != 0 or source.transform.a <= 0 or source.transform.e >= 0:
            return False
    fine_x, fine_y = abs(finest.transform.a), abs(finest.transform.e)
    other_x, other_y = abs(other.transform.a), abs(other.transform.e)
    if _ratio(other_x, fine_x) is None or _ratio(other_y, fine_y) is None:
        return False
    slack = fine_x * 1e-3
    left, top = finest.transform @ (0, 0)
    right, bottom = finest.transform @ (finest.width, finest.height)
    other_left, other_top = other.transform @ (0, 0)
    other_right, other_bottom = other.transform @ (other.width, other.height)
    return all(
        math.isclose(a, b, abs_tol=slack)
        for a, b in ((left, other_left), (top, other_top), (right, other_right), (bottom, other_bottom))
    )


def common_grid(sources: Sequence[Source]) -> tuple[Source, bool]:
    """The source whose grid the others are read onto, and whether any of them has to be resampled.

    Raises :class:`GridMismatch` for assets that are neither one grid nor nested.
    """
    finest = min(sources, key=lambda source: abs(source.transform.a) * abs(source.transform.e))
    if all(finest.same_grid(other) for other in sources):
        return finest, False
    for other in sources:
        if not finest.same_grid(other) and not _nested_in(finest, other):
            raise GridMismatch(
                "the assets of this input do not share one grid: they differ in CRS or extent, "
                "or one pixel size is not a whole multiple of the finest"
            )
    return finest, True


def merge_images(images: list[ImageData]) -> ImageData:
    """The bands of several images of one grid as one image, band names in the order given."""
    if len(images) == 1:
        return images[0]
    merged = ImageData.create_from_list(images)
    names = [name for image in images for name in image.band_names]
    nodata = {image.nodata for image in images}
    return ImageData(
        merged.array,
        bounds=merged.bounds,
        crs=merged.crs,
        band_names=names,
        nodata=nodata.pop() if len(nodata) == 1 else None,
    )
