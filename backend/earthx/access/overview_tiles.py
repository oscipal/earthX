"""A tile of an overview pyramid, drawn like any other tile (M5-30b part 9, adr/0032 §5.2, plan §8.11).

`api` fetches the stored tile from the object store (it alone may import `objectstore`) and hands the bytes in as a
:class:`PyramidTile`. This module only reads them: the tile is a small GeoTIFF of the WebMercatorQuad grid with one band,
512 px, in the data type and with the nodata of the source, so the factory's colour scale, colormap and nodata
handling are those of every other tile of the dataset (adr/0032 §5.2: the pyramid holds values, not pictures). Nothing
here opens an address, and the bytes never leave the process.

A pyramid tile is **one read of an object that is already in memory**: it takes no place of the gate of
:mod:`earthx.access.mosaic_tiles` and has no read budget.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import morecantile
import numpy
import rasterio
from attrs import define
from rasterio.io import MemoryFile
from rio_tiler.errors import RioTilerError, TileOutsideBounds
from rio_tiler.io.rasterio import Reader
from rio_tiler.models import ImageData

from earthx.access.mosaic_tiles import EarthxMosaicTilerFactory, open_mosaic

__all__ = [
    "EarthxOverviewTilerFactory",
    "PyramidBandRefused",
    "PyramidTile",
    "PyramidTileInvalid",
    "PyramidTileReader",
    "open_overview",
]

#: How far (metres) the corners of a stored tile may lie from those of the tile it is stored for: a tile of this grid is
#: written from the grid itself, so anything beyond float noise is a foreign file.
_CORNER_TOLERANCE_M = 0.01


class PyramidTileInvalid(RioTilerError):
    """The stored tile is not the tile its key says: a ``502``, the store's side of the line, never a crash in GDAL."""

    status_code = 502


class PyramidBandRefused(RioTilerError):
    """A band other than the first: a pyramid holds one band (adr/0032 §5.2), and asking for another is a ``400``."""

    status_code = 400


@dataclass(frozen=True, slots=True, repr=False)
class PyramidTile:
    """One tile of a pyramid as bytes, and where its picture ends.

    ``extent`` is west, south, east, north in EPSG:4326, or ``None``: pixels outside it are transparent. A dataset
    draws its own pyramid whole; a substitute's pyramid lies under another dataset and stops at that dataset's extent
    (plan M5-30b §8.8, "Ausdehnung = gewählter Datensatz").
    """

    dataset_id: str
    data: bytes
    extent: tuple[float, float, float, float] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.data, bytes) or not self.data:
            raise ValueError("a pyramid tile is the bytes of a stored tile")

    def __repr__(self) -> str:
        return f"PyramidTile(dataset_id={self.dataset_id!r}, {len(self.data)} bytes)"


class PyramidTileReader:
    """What TiTiler's tile route needs of a reader, over one stored tile (and no TileJSON, no info)."""

    def __init__(
        self,
        source: PyramidTile,
        *,
        tms: morecantile.TileMatrixSet | None = None,
        gdal_config: Mapping[str, Any] | None = None,
        **options: Any,
    ) -> None:
        if not isinstance(source, PyramidTile):
            raise TypeError("a pyramid tile reader reads a PyramidTile")
        self.source = source
        self.tms = tms or morecantile.tms.get("WebMercatorQuad")

    def __enter__(self) -> PyramidTileReader:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        return None

    @property
    def minzoom(self) -> int:
        return self.tms.minzoom

    @property
    def maxzoom(self) -> int:
        return self.tms.maxzoom

    def tile(self, tile_x: int, tile_y: int, tile_z: int, **kwargs: Any) -> ImageData:
        """The stored tile, read as a tile of this grid, at the size and with the options of the request."""
        indexes = kwargs.get("indexes")
        if indexes is not None and any(index != 1 for index in ((indexes,) if isinstance(indexes, int) else indexes)):
            raise PyramidBandRefused("a tile of an overview has one band; bidx is 1")
        try:
            with MemoryFile(self.source.data) as memory, memory.open() as dataset:
                image = self._read(dataset, tile_x, tile_y, tile_z, **kwargs)
        except rasterio.errors.RasterioError:
            raise PyramidTileInvalid("the stored overview tile is not a readable raster") from None
        if self.source.extent is not None:
            image = self._cut_to_extent(image, self.source.extent)
        return image

    def _read(self, dataset: Any, tile_x: int, tile_y: int, tile_z: int, **kwargs: Any) -> ImageData:
        wanted = self.tms.xy_bounds(morecantile.Tile(tile_x, tile_y, tile_z))
        left, bottom, right, top = dataset.bounds
        misplaced = max(abs(left - wanted.left), abs(bottom - wanted.bottom), abs(right - wanted.right), abs(top - wanted.top))
        if dataset.crs != self.tms.rasterio_crs or misplaced > _CORNER_TOLERANCE_M:
            raise PyramidTileInvalid("the stored overview tile does not lie where its key says")
        with Reader(input="overview", dataset=dataset, tms=self.tms) as reader:
            try:
                return reader.tile(tile_x, tile_y, tile_z, **kwargs)
            except TileOutsideBounds:
                raise PyramidTileInvalid("the stored overview tile does not lie where its key says") from None

    def _cut_to_extent(self, image: ImageData, extent: tuple[float, float, float, float]) -> ImageData:
        """Mask the pixels whose centre lies outside ``extent``; the box of a lon/lat rectangle is a rectangle in this grid."""
        west, south = self.tms.xy(extent[0], extent[1])
        east, north = self.tms.xy(extent[2], extent[3])
        left, bottom, right, top = image.bounds
        height, width = image.array.shape[-2:]
        columns = left + (numpy.arange(width) + 0.5) * (right - left) / width
        rows = top - (numpy.arange(height) + 0.5) * (top - bottom) / height
        inside = ((columns >= west) & (columns <= east))[None, :] & ((rows >= south) & (rows <= north))[:, None]
        mask = numpy.ma.getmaskarray(image.array) | ~inside[None]
        image.array = numpy.ma.MaskedArray(numpy.ma.getdata(image.array), mask=mask)
        return image

    def get_geographic_bounds(self, crs: Any) -> tuple[float, float, float, float]:
        raise NotImplementedError("a pyramid tile has no TileJSON")

    def info(self) -> Any:
        raise NotImplementedError("a pyramid tile has no info")


def open_overview(src_path: Any, **reader_params: Any) -> Any:
    """The reader of the overview route in the shape TiTiler calls it: ours for a stored tile, the mosaic's for scenes."""
    if isinstance(src_path, PyramidTile):
        return PyramidTileReader(src_path, **reader_params)
    return open_mosaic(src_path, **reader_params)


@define(kw_only=True)
class EarthxOverviewTilerFactory(EarthxMosaicTilerFactory):
    """The tile of the mosaic factory, over what a dataset shows below its first level, and no other route (plan M5-30b §4.8).

    A substitute's scenes are read by the mosaic's reader under its budget; a pyramid's tile is read by
    :class:`PyramidTileReader`. A TileJSON, statistics, info and point of either would make it something a client can ask
    about; it is a picture below the first level and nothing more. What is read comes from the path dependency, which `api`
    writes for this route.
    """

    reader: Any = open_overview

    def register_routes(self) -> None:
        self.tile()
