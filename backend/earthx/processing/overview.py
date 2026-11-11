"""The core of an overview pyramid: one tile from files, one level up from four tiles, one tile as bytes
(M5-30b part 8, adr/0032 §5.2, §8.2).

Pure functions on arrays: no database, no queue, no object store (KLAERUNGEN B9). `jobs` decides which tiles are
built, stores what :func:`encode_tile` returns and hands the children of a parent back in.

**What a tile holds:** the first band of the default render, in the data type and with the nodata of the source,
512 px square on the grid of WebMercatorQuad. Colour, stretch and band maths stay with the tiler (adr/0032 §5.2).
**Levels:** the pyramid goes from z0 to one level below ``min_zoom`` (:func:`levels`); the base level is read from the
files, every level above is made from four tiles below it. A tile without a valid pixel is ``None`` and not stored.

**Reading with spacing:** GDAL opens its connections itself, so each file is opened between ``pacer.wait(host)`` and
``pacer.account(host, requests)``, with the requests counted from GDAL's debug lines (:func:`counting_gdal_lines`);
the lines are not logged. The core names the pacer by a :class:`Pacer` protocol: `gateway`'s ``HostPacer`` fits it,
and the core may not import `gateway` (architekturplan.md 3.1).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Protocol

import morecantile
import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rio_tiler.errors import TileOutsideBounds
from rio_tiler.models import ImageData

from earthx.catalog.registry import OverviewResampling
from earthx.readers.access import counting_gdal_lines
from earthx.readers.cog import AssetPath, CogReader, asset_host

__all__ = [
    "TILE_SIZE",
    "Pacer",
    "base_hash",
    "base_tile",
    "base_zoom",
    "children_of",
    "encode_tile",
    "levels",
    "parent_tile",
    "tile_image",
]

#: The side of a stored tile in pixels.
TILE_SIZE = 512
_TMS = morecantile.tms.get("WebMercatorQuad")


class Pacer(Protocol):
    """What the reading needs of a spacing per host; `gateway`'s ``HostPacer`` fits it structurally."""

    def wait(self, host: str) -> None: ...

    def account(self, host: str, requests: int) -> None: ...


def base_zoom(min_zoom: int) -> int:
    """The level read from the files: one below ``min_zoom`` (GLO-30 7 → 6, WorldCover 5 → 4)."""
    if isinstance(min_zoom, bool) or not isinstance(min_zoom, int) or not 1 <= min_zoom <= _TMS.maxzoom + 1:
        raise ValueError("a pyramid lies below a min_zoom of 1 or more")
    return min_zoom - 1


def levels(min_zoom: int) -> tuple[int, ...]:
    """The levels of the pyramid, z0 up to the base level."""
    return tuple(range(base_zoom(min_zoom) + 1))


def children_of(tile: morecantile.Tile) -> tuple[morecantile.Tile, ...]:
    """The four tiles one level down, in the order :func:`parent_tile` takes them: NW, NE, SW, SE."""
    x, y, z = tile.x * 2, tile.y * 2, tile.z + 1
    return tuple(morecantile.Tile(x + dx, y + dy, z) for dy in (0, 1) for dx in (0, 1))


def tile_image(array: np.ma.MaskedArray, tile: morecantile.Tile, *, nodata: float | None) -> ImageData:
    """A tile's 2-D array as an image on the tile's own EPSG:3857 bounds."""
    return ImageData(
        np.ma.asarray(array)[np.newaxis], crs=_TMS.rasterio_crs, bounds=_TMS.xy_bounds(tile), nodata=nodata
    )


def _valid(array: np.ma.MaskedArray) -> np.ndarray:
    """The pixels that hold a value: not masked, and for floats finite."""
    valid = ~np.ma.getmaskarray(array)
    if np.issubdtype(array.dtype, np.floating):
        valid &= np.isfinite(np.ma.getdata(array))
    return valid


def base_tile(
    scenes: Sequence[AssetPath],
    tile: morecantile.Tile,
    *,
    resampling: OverviewResampling,
    pacer: Pacer,
    gdal_config: Mapping[str, str],
) -> ImageData | None:
    """The tile at the base level from the files that touch it, or ``None`` when no pixel is valid.

    ``scenes`` are cleared paths in the order of the mosaic (the first valid pixel wins, as in the mosaic tile);
    a file the tile does not touch is skipped, any other failure fails the tile, since a file left out silently would
    let another one win. Each file is read in the coarsest overview that serves 512 px, resampled with ``resampling``,
    under ``pacer`` when it is a remote file. Reading stops once every pixel is filled.
    """
    if not isinstance(resampling, OverviewResampling):
        raise TypeError("resampling is an OverviewResampling")
    method = resampling.value
    values: np.ndarray | None = None
    holes: np.ndarray | None = None
    nodata: float | None = None
    for scene in scenes:
        image = _read(scene, tile, method, pacer, gdal_config)
        if image is None:
            continue
        band = image.array[0]
        usable = _valid(band)
        if values is None or holes is None:
            values, holes, nodata = np.array(np.ma.getdata(band)), ~usable, image.nodata
        else:
            if band.dtype != values.dtype:
                raise ValueError("the files of one tile differ in data type")
            take = holes & usable
            values[take] = np.ma.getdata(band)[take]
            holes &= ~take
            nodata = image.nodata if nodata is None else nodata
        if not holes.any():
            break
    if values is None or holes is None or holes.all():
        return None
    return tile_image(np.ma.array(values, mask=holes), tile, nodata=nodata)


def _read(
    scene: AssetPath, tile: morecantile.Tile, method: str, pacer: Pacer, gdal_config: Mapping[str, str]
) -> ImageData | None:
    """One file's tile, or ``None`` if the file does not touch it; a remote file is read between ``wait`` and ``account``."""
    if not isinstance(scene, AssetPath):
        raise TypeError("a pyramid reads files the gateway cleared, not plain strings (KLAERUNGEN B8)")
    host = asset_host(scene)
    options = {**gdal_config, "CPL_DEBUG": "ON"} if host else dict(gdal_config)
    with counting_gdal_lines(own_thread_only=True) as counter:
        if host:
            pacer.wait(host)
        try:
            with rasterio.Env(**options), CogReader(scene, tms=_TMS) as reader:
                return reader.tile(
                    tile.x,
                    tile.y,
                    tile.z,
                    tilesize=TILE_SIZE,
                    indexes=1,
                    resampling_method=method,
                    reproject_method=method,
                )
        except TileOutsideBounds:
            return None
        finally:
            if host:
                pacer.account(host, counter.take()[0])


def parent_tile(
    children: Sequence[np.ma.MaskedArray | None], resampling: OverviewResampling
) -> np.ma.MaskedArray | None:
    """The tile one level up from its four children (NW, NE, SW, SE as in :func:`children_of`), or ``None``.

    Each pixel is made from the 2×2 pixels of a child that hold a value; masked and non-finite pixels do not count,
    and a pixel with none is masked. ``average``: their mean, rounded for integers. ``mode``: the most frequent value,
    the smallest of equals (classes). ``nearest``: the first of top-left, top-right, bottom-left, bottom-right.
    A missing child is nodata; no child with a value gives ``None``.
    """
    if not isinstance(resampling, OverviewResampling):
        raise TypeError("resampling is an OverviewResampling")
    if len(children) != 4:
        raise ValueError("a tile has four children")
    present = [child for child in children if child is not None]
    if not present:
        return None
    dtype = present[0].dtype
    if any(child.dtype != dtype or child.shape != (TILE_SIZE, TILE_SIZE) for child in present):
        raise ValueError(f"the children are {TILE_SIZE} px square and of one data type")
    half = TILE_SIZE // 2
    values = np.zeros((TILE_SIZE, TILE_SIZE), dtype)
    holes = np.ones((TILE_SIZE, TILE_SIZE), bool)
    for index, child in enumerate(children):
        if child is None:
            continue
        rows, cols = (
            slice((index // 2) * half, (index // 2 + 1) * half),
            slice((index % 2) * half, (index % 2 + 1) * half),
        )
        values[rows, cols], holes[rows, cols] = _halve(child, resampling)
    if holes.all():
        return None
    return np.ma.array(values, mask=holes)


def _halve(array: np.ma.MaskedArray, resampling: OverviewResampling) -> tuple[np.ndarray, np.ndarray]:
    """``array`` at half the size, with the mask of the pixels that had no value in their 2×2 block."""
    size = array.shape[0] // 2
    blocks = np.ma.getdata(array).reshape(size, 2, size, 2).transpose(0, 2, 1, 3).reshape(size, size, 4)
    valid = _valid(array).reshape(size, 2, size, 2).transpose(0, 2, 1, 3).reshape(size, size, 4)
    count = valid.sum(axis=2)
    if resampling is OverviewResampling.AVERAGE:
        mean = np.where(valid, blocks, 0).sum(axis=2, dtype=np.float64) / np.maximum(count, 1)
        result = mean if np.issubdtype(array.dtype, np.floating) else np.rint(mean)
    elif resampling is OverviewResampling.MODE:
        same = (blocks[..., :, None] == blocks[..., None, :]) & valid[..., :, None] & valid[..., None, :]
        votes = same.sum(axis=3)
        biggest = (votes == votes.max(axis=2, keepdims=True)) & valid
        top = np.inf if np.issubdtype(array.dtype, np.floating) else np.iinfo(array.dtype).max
        result = np.where(biggest, blocks, top).min(axis=2)
    else:
        result = np.take_along_axis(blocks, valid.argmax(axis=2)[..., None], axis=2)[..., 0]
    return np.where(count > 0, result, 0).astype(array.dtype), count == 0


def encode_tile(image: ImageData) -> bytes:
    """The first band of ``image`` as a stored tile: 512 px GeoTIFF, tiled, DEFLATE with a predictor, EPSG:3857.

    Predictor 3 for floating point, 2 for integers (adr/0032 §5.2). Masked pixels hold the nodata of the image; a
    float tile without one gets NaN, an integer tile with holes needs one (a ``ValueError`` otherwise).
    """
    if image.crs != _TMS.rasterio_crs or image.bounds is None:
        raise ValueError("a stored tile lies in EPSG:3857 with its bounds")
    band = image.array[0]
    if band.shape != (TILE_SIZE, TILE_SIZE):
        raise ValueError(f"a stored tile is {TILE_SIZE} px square")
    floating = np.issubdtype(band.dtype, np.floating)
    holes = ~_valid(band)
    nodata = image.nodata
    if nodata is None and floating:
        nodata = float("nan")
    if nodata is None and holes.any():
        raise ValueError("an integer tile with holes needs a nodata value")
    values = np.where(holes, band.dtype.type(nodata) if nodata is not None else 0, np.ma.getdata(band))
    profile = {
        "driver": "GTiff", "width": TILE_SIZE, "height": TILE_SIZE, "count": 1, "dtype": band.dtype.name,
        "crs": image.crs, "transform": image.transform, "nodata": nodata, "tiled": True,
        "blockxsize": TILE_SIZE, "blockysize": TILE_SIZE, "compress": "DEFLATE", "predictor": 3 if floating else 2,
    }  # fmt: skip
    with MemoryFile() as memory:
        with memory.open(**profile) as target:
            target.write(values.astype(band.dtype), 1)
        return memory.read()


def base_hash(items: Iterable[Mapping[str, object]]) -> str:
    """The hash of the items a base tile read: over each ``id`` and ``properties.updated``, whatever their order.

    The same hash for a new version means the tile need not be read again and may be copied (adr/0032 §5.2, F3). An
    item without ``id`` or ``updated`` has no stable version, so that is a ``ValueError`` rather than a hash that
    would match a changed item.
    """
    pairs = []
    for item in items:
        properties = item.get("properties")
        updated = properties.get("updated") if isinstance(properties, Mapping) else None
        if not isinstance(item.get("id"), str) or not item["id"] or not isinstance(updated, str) or not updated:
            raise ValueError("an item needs an id and properties.updated to be part of a tile's hash")
        pairs.append([item["id"], updated])
    return hashlib.sha256(json.dumps(sorted(pairs), separators=(",", ":")).encode()).hexdigest()
