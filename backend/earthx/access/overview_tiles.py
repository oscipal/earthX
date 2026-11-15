"""A tile of an overview pyramid, drawn like any other tile (M5-30b part 9, adr/0032 §5.2, plan §8.11).

`api` fetches the stored tile from the object store (it alone may import `objectstore`) and hands the bytes in as a
:class:`PyramidTile`. This module only reads them: the tile is a small GeoTIFF of the WebMercatorQuad grid with one band,
512 px, in the data type and with the nodata of the source, so the factory's colour scale, colormap and nodata
handling are those of every other tile of the dataset (adr/0032 §5.2: the pyramid holds values, not pictures). Nothing
here opens an address, and the bytes never leave the process.

A pyramid tile is **one read of an object** and has no read budget. It takes no place of the gate of the file reads
(:data:`~earthx.access.mosaic_tiles.TILE_GATE`), so it never queues behind them, but a place of its own gate
(:data:`PYRAMID_GATE`): it, too, holds a thread of the shared pool for the read of the object and for the rendering, and a
zoomed-out view over a slow store must not fill that pool (plan M5-30b §8.11).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import morecantile
import numpy
import rasterio
from attrs import define
from rasterio.io import MemoryFile
from rio_tiler.errors import RioTilerError, TileOutsideBounds
from rio_tiler.io.rasterio import Reader
from rio_tiler.models import ImageData
from shapely.geometry.base import BaseGeometry

from earthx.access.footprint_mask import cut_to_footprints
from earthx.access.mosaic_tiles import EarthxMosaicTilerFactory, TileGate, TilePlace, grown_options, open_mosaic

__all__ = [
    "EarthxOverviewTilerFactory",
    "PYRAMID_GATE",
    "PYRAMID_PLACES",
    "PyramidBandRefused",
    "PyramidTile",
    "PyramidTileInvalid",
    "PyramidTileReader",
    "open_overview",
]

#: Pyramid tiles read at once in a process. Eight: a tile is a read of one object of about half a megabyte and a rendering,
#: some tens of milliseconds on a store next door, so eight places carry well over a hundred tiles a second, and they hold at
#: most eight of the roughly 40 threads of the pool the other synchronous routes share, however slow the store is.
PYRAMID_PLACES = 8
PYRAMID_GATE = TileGate(PYRAMID_PLACES)

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

    ``place`` is the place at :data:`PYRAMID_GATE` the tile waited for; the reader gives it back when it is done.
    ``extent`` is west, south, east, north in EPSG:4326, or ``None``: pixels outside it are transparent. A dataset
    draws its own pyramid whole; a substitute's pyramid lies under another dataset and stops at that dataset's extent
    (plan M5-30b §8.8, "Ausdehnung = gewählter Datensatz").
    """

    dataset_id: str
    data: bytes
    extent: tuple[float, float, float, float] | None = None
    place: TilePlace | None = field(default=None, compare=False)
    #: Footprints (EPSG:4326) the picture is masked to, or ``None``: the pyramid of a search is drawn over its hits only
    #: (adr/0032 Nachtrag 15.11.2026). Pixels outside are transparent.
    mask: BaseGeometry | None = field(default=None, compare=False)
    #: Steps run on the tile (M5-10 part B): its values are read with the file's scale and offset.
    physical: bool = False
    #: The pixels a ``focal`` first step needs around the tile; the stored tiles around it are ``neighbours``.
    halo: int = 0
    #: The stored tiles around this one as ``(dx, dy, bytes)``, one step of the grid away; a tile without data is missing.
    neighbours: tuple[tuple[int, int, bytes], ...] = field(default=(), compare=False)

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
        try:
            indexes = kwargs.get("indexes")
            if indexes is not None and any(index != 1 for index in ((indexes,) if isinstance(indexes, int) else indexes)):
                raise PyramidBandRefused("a tile of an overview has one band; bidx is 1")
            options = grown_options(self.source.halo, self.source.physical, kwargs)
            try:
                if self.source.halo:
                    image = self._read_grown(tile_x, tile_y, tile_z, **options)
                else:
                    with MemoryFile(self.source.data) as memory, memory.open() as dataset:
                        image = self._read(dataset, tile_x, tile_y, tile_z, **options)
            except rasterio.errors.RasterioError:
                raise PyramidTileInvalid("the stored overview tile is not a readable raster") from None
            if self.source.extent is not None:
                image = self._cut_to_extent(image, self.source.extent)
            if self.source.mask is not None:
                image = cut_to_footprints(image, self.source.mask, self.tms.rasterio_crs)
            return image
        finally:
            if self.source.place is not None:
                self.source.place.release()

    def _check_place(self, dataset: Any, tile_x: int, tile_y: int, tile_z: int) -> None:
        wanted = self.tms.xy_bounds(morecantile.Tile(tile_x, tile_y, tile_z))
        left, bottom, right, top = dataset.bounds
        misplaced = max(abs(left - wanted.left), abs(bottom - wanted.bottom), abs(right - wanted.right), abs(top - wanted.top))
        if dataset.crs != self.tms.rasterio_crs or misplaced > _CORNER_TOLERANCE_M:
            raise PyramidTileInvalid("the stored overview tile does not lie where its key says")

    def _read_grown(self, tile_x: int, tile_y: int, tile_z: int, **options: Any) -> ImageData:
        """The tile grown by its halo, from the stored tile and those around it, the first valid pixel winning.

        Each stored tile is read over the grown bounds and is empty where it does not reach; a neighbour without data is
        missing and leaves its part empty (G4: no seams where there are data)."""
        halo = int(options.pop("buffer"))
        size = int(options.pop("tilesize", 256) or 256)
        bounds = self.tms.xy_bounds(morecantile.Tile(tile_x, tile_y, tile_z))
        step = (bounds.right - bounds.left) / size
        grown = (bounds.left - halo * step, bounds.bottom - halo * step, bounds.right + halo * step, bounds.top + halo * step)
        side = size + 2 * halo
        merged: ImageData | None = None
        for dx, dy, data in ((0, 0, self.source.data), *self.source.neighbours):
            with MemoryFile(data) as memory, memory.open() as dataset:
                self._check_place(dataset, tile_x + dx, tile_y + dy, tile_z)
                with Reader(input="overview", dataset=dataset, tms=self.tms) as reader:
                    part = reader.part(
                        grown,
                        dst_crs=self.tms.rasterio_crs,
                        bounds_crs=self.tms.rasterio_crs,
                        width=side,
                        height=side,
                        max_size=None,
                        **options,
                    )
            # Each stored tile gives the pixels of the grown tile that lie in it, and no more: GDAL's bilinear reads past the
            # edge of a file with the edge's value, which would cover the neighbour's real one.
            own = numpy.zeros((side, side), dtype=bool)
            rows = slice(halo + dy * size, halo + (dy + 1) * size)
            columns = slice(halo + dx * size, halo + (dx + 1) * size)
            own[max(rows.start, 0) : max(rows.stop, 0), max(columns.start, 0) : max(columns.stop, 0)] = True
            empty = ~own[None] | numpy.ma.getmaskarray(part.array)
            if merged is None:
                merged = part
                merged.array = numpy.ma.MaskedArray(numpy.ma.getdata(part.array), mask=empty)
                continue
            filled = ~numpy.ma.getmaskarray(merged.array)
            values = numpy.where(filled, numpy.ma.getdata(merged.array), numpy.ma.getdata(part.array))
            merged.array = numpy.ma.MaskedArray(values, mask=~filled & empty)
        assert merged is not None  # the stored tile itself is always read
        return merged

    def _read(self, dataset: Any, tile_x: int, tile_y: int, tile_z: int, **kwargs: Any) -> ImageData:
        self._check_place(dataset, tile_x, tile_y, tile_z)
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
