"""The mosaic of one overpass: its order, its target CRS, its grid and its blocks (M4-12a).

One input, one group, several items — the scenes of one overpass. The core reads them into one
raster in the CRS most of them share; the steps of the recipe then run on that raster as on
the raster of one item.

**One rule, from the list.** Per band and pixel the first valid element wins, in the order
of the list the recipe carries (:func:`~earthx.access.crop_rules.merge_first_valid`, the rule
of the synchronous crop and the export job). The core does not sort and has no second rule.
`api` sorts the list when it makes the recipe (:func:`mosaic_order`): first the scenes in
the target CRS, so that the values nearest to the source win where scenes overlap, then the
others, each part by item id. The same overpass thus gives the same recipe in whatever order
it was asked for (Otto, 10.10.2026, F3 and F4).

**The target CRS** (:func:`target_crs`) is the one most scenes are in; a tie goes to the
smaller EPSG number, whatever the order. The grid is that of the first scene (the finest of
its assets), extended to the union of all scenes and snapped outward to its pixels.

**Scenes on the grid are read without a warp**; every other scene (another CRS, another
pixel size, an origin that is no whole number of pixels away) through a ``WarpedVRT`` onto
the grid with ``nearest`` and the constants of the ``reproject`` operator (K1). A
Sentinel-2 overpass over two UTM zones is the usual case: the tiles of one zone share one
grid, those of the other are warped. Reading skips the scenes that do not touch a block, and
stops reading once every element of a block is filled.

Nothing here opens an address; :func:`open_mosaic` opens through ``open_asset_ref`` like the
single-item run, so every address has passed ``check_url``.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from contextlib import ExitStack

import numpy
import rasterio
from rasterio.crs import CRS
from rasterio.errors import CRSError
from rasterio.transform import Affine
from rasterio.warp import transform_bounds
from rasterio.windows import Window
from rio_tiler.models import ImageData

from earthx.access.crop_rules import merge_first_valid
from earthx.access.resolve import open_asset_ref
from earthx.processing.errors import UnsupportedRecipe
from earthx.processing.operators.reproject import TOLERANCE, WARP_MEM_LIMIT_MB
from earthx.processing.recipe import Recipe
from earthx.processing.source import Source
from earthx.processing.warped import WarpedItem, cache_per_item
from earthx.readers import read_access_for
from earthx.readers.cog import CogReader

__all__ = ["MosaicSource", "mosaic_order", "open_mosaic", "target_crs"]

#: A pixel offset or size counts as a whole number within this (of a pixel).
_PIXEL_TOLERANCE = 1e-3

#: Relative slack when comparing two pixel sizes.
_SIZE_TOLERANCE = 1e-6

_NO_EPSG = 1 << 30


def _epsg(crs: str) -> int:
    try:
        return CRS.from_user_input(crs).to_epsg() or _NO_EPSG
    except CRSError:
        return _NO_EPSG


def target_crs(crs_by_item: Mapping[str, str | None]) -> str | None:
    """The CRS most items are in; a tie goes to the smaller EPSG number (F4), whatever the order.

    ``None`` when no item names its CRS (a DEM tile without ``proj:code``): the core then
    takes the CRS of the first file.
    """
    counts = Counter(crs for crs in crs_by_item.values() if crs is not None)
    if not counts:
        return None
    return min(counts, key=lambda crs: (-counts[crs], _epsg(crs), crs))


def mosaic_order(crs_by_item: Mapping[str, str | None]) -> list[str]:
    """The items in the order the mosaic reads them: those in the target CRS first, each part by id (F3)."""
    target = target_crs(crs_by_item)
    return sorted(crs_by_item, key=lambda item_id: (crs_by_item[item_id] != target, item_id))


def _north_up(source: Source) -> bool:
    t = source.transform
    return t.b == 0 and t.d == 0 and t.a > 0 and t.e < 0


def _on_grid(anchor: Source, source: Source) -> bool:
    """Whether ``source`` lies on the pixel grid of ``anchor``: same CRS and pixel size, an origin whole pixels away."""
    if source.crs != anchor.crs:
        return False
    t, u = source.transform, anchor.transform
    if not (math.isclose(t.a, u.a, rel_tol=_SIZE_TOLERANCE) and math.isclose(t.e, u.e, rel_tol=_SIZE_TOLERANCE)):
        return False
    columns, rows = (t.c - u.c) / u.a, (u.f - t.f) / -u.e
    return abs(columns - round(columns)) < _PIXEL_TOLERANCE and abs(rows - round(rows)) < _PIXEL_TOLERANCE


def _bounds_in(source: Source, crs: CRS) -> tuple[float, float, float, float]:
    """``(left, bottom, right, top)`` of the source's raster in ``crs``."""
    t = source.transform
    left, top = t.c, t.f
    right, bottom = t @ (source.width, source.height)
    if source.crs == crs:
        return left, bottom, right, top
    return transform_bounds(source.crs, crs, left, bottom, right, top, densify_pts=21)


def _floor(value: float) -> int:
    return math.floor(value + _PIXEL_TOLERANCE)


def _ceil(value: float) -> int:
    return math.ceil(value - _PIXEL_TOLERANCE)


class _Member:
    """One scene's asset in a mosaic: its source, whether it lies on the grid, where it reaches."""

    def __init__(self, source: Source, on_grid: bool, bounds: tuple[float, float, float, float]) -> None:
        self.source = source
        self.on_grid = on_grid
        self.bounds = bounds
        self.warped: WarpedItem | None = None

    def extent(self, grid: Affine) -> tuple[int, int, int, int]:
        """``(col0, row0, col1, row1)`` in the pixels of ``grid``: exact on the grid, a pixel wider off it."""
        left, bottom, right, top = self.bounds
        col0, col1 = (left - grid.c) / grid.a, (right - grid.c) / grid.a
        row0, row1 = (grid.f - top) / -grid.e, (grid.f - bottom) / -grid.e
        if self.on_grid:
            return round(col0), round(row0), round(col1), round(row1)
        return math.floor(col0) - 1, math.floor(row0) - 1, math.ceil(col1) + 1, math.ceil(row1) + 1


class MosaicSource(Source):
    """The scenes of an overpass as one input asset: a :class:`Source` the core reads like any other.

    It takes the bands, data type, nodata and scaling of the first scene — the others must
    agree — and a grid of its own: the first scene's pixel size over the extent of all.
    """

    def __init__(self, members: Sequence[_Member], extent: tuple[float, float, float, float], stack: ExitStack):
        anchor = members[0].source
        self.entry = anchor.entry
        self.reader = anchor.reader
        self.crs = anchor.crs
        self.names, self.data_types, self.nodata, self.scaling = anchor.names, anchor.data_types, anchor.nodata, anchor.scaling
        left, bottom, right, top = extent
        self.transform = Affine(anchor.transform.a, 0, left, 0, anchor.transform.e, top)
        self.width = round((right - left) / anchor.transform.a)
        self.height = round((top - bottom) / -anchor.transform.e)
        self.warps = any(not member.on_grid for member in members)
        self._members = list(members)
        self._extent = extent
        self._stack = stack

    def _warped(self, member: _Member, grid: Affine) -> WarpedItem:
        if member.warped is None:
            left, bottom, right, top = self._extent
            member.warped = WarpedItem(
                member.source.reader.dataset,  # type: ignore[union-attr]  # a COG, checked at opening
                grid,
                round((right - left) / grid.a),
                round((top - bottom) / -grid.e),
                alone=False,
                stack=self._stack,
                crs=self.crs,
                warp_options={"tolerance": TOLERANCE, "warp_mem_limit": WARP_MEM_LIMIT_MB},
            )
        return member.warped

    def _piece(self, member: _Member, block: Window, grid: Affine) -> numpy.ma.MaskedArray | None:
        """The part of ``block`` this member reaches, placed in an otherwise masked block; ``None`` if it reaches none."""
        col0, row0, col1, row1 = member.extent(grid)
        left, top = max(block.col_off, col0), max(block.row_off, row0)
        right = min(block.col_off + block.width, col1)
        bottom = min(block.row_off + block.height, row1)
        if right <= left or bottom <= top:
            return None
        part = Window(left, top, right - left, bottom - top)
        if member.on_grid:
            image = member.source.read(part, grid)
        else:
            raw = self._warped(member, grid).read(part)
            bounds = rasterio.windows.bounds(part, grid)
            image = member.source.physical(
                ImageData(raw, bounds=bounds, crs=self.crs, band_names=[f"b{i + 1}" for i in range(raw.shape[0])])
            )
        shape = (image.count, int(block.height), int(block.width))
        piece = numpy.ma.MaskedArray(numpy.zeros(shape, image.array.dtype), mask=numpy.ones(shape, bool))
        rows = slice(top - block.row_off, bottom - block.row_off)
        columns = slice(left - block.col_off, right - block.col_off)
        piece.data[:, rows, columns] = image.array.data
        piece.mask[:, rows, columns] = numpy.ma.getmaskarray(image.array)
        return piece

    def _pieces(self, block: Window, grid: Affine) -> Iterator[numpy.ma.MaskedArray]:
        for member in self._members:
            piece = self._piece(member, block, grid)
            if piece is not None:
                yield piece

    def read(self, window: Window, grid: Affine | None = None) -> ImageData:
        """``window`` of the grid ``grid`` (the mosaic's own by default), in physical values.

        The first valid element per band and pixel of the scenes that reach the block, in the
        order of the list; where no scene reaches, the block is masked.
        """
        grid = self.transform if grid is None else grid
        left, top = grid @ (window.col_off, window.row_off)
        right, bottom = grid @ (window.col_off + window.width, window.row_off + window.height)
        pieces = self._pieces(window, grid)
        first = next(pieces, None)
        if first is None:
            shape = (len(self.names), int(window.height), int(window.width))
            dtype = numpy.float32 if self.scaling.applied_by_core else numpy.dtype(self.data_types[0])
            array = numpy.ma.MaskedArray(numpy.zeros(shape, dtype), mask=numpy.ones(shape, bool))
        else:
            array = merge_first_valid(_chain(first, pieces))
        nodata = self.nodata[0] if len(set(self.nodata)) == 1 else None
        return ImageData(
            array, bounds=(left, bottom, right, top), crs=self.crs, band_names=list(self.names), nodata=nodata
        )


def _chain(first: numpy.ma.MaskedArray, rest: Iterator[numpy.ma.MaskedArray]) -> Iterator[numpy.ma.MaskedArray]:
    yield first
    yield from rest


def _check_alike(asset: str, members: Sequence[Source]) -> None:
    anchor = members[0]
    for other in members[1:]:
        if (other.names, other.data_types, other.nodata) != (anchor.names, anchor.data_types, anchor.nodata):
            raise UnsupportedRecipe(f"the scenes of the mosaic differ in the bands, data type or nodata of {asset!r}")
        if other.scaling != anchor.scaling:
            raise UnsupportedRecipe(f"the scenes of the mosaic scale {asset!r} differently")


def open_mosaic(recipe: Recipe, stack: ExitStack) -> list[MosaicSource]:
    """One :class:`MosaicSource` per asset of the recipe's one input, its scenes opened into ``stack``.

    The scenes are in the order of the recipe's group. The read caches of the open files
    share the budget of one file (:func:`~earthx.processing.warped.cache_per_item`), so that
    a mosaic of many scenes costs what one scene costs.
    """
    entry = recipe.inputs[0]
    access = read_access_for(recipe.hrefs())
    resolved = {(item.asset.item_id, item.asset.asset): item for item in entry.resolved}
    items = entry.groups[0]
    sources: dict[str, list[Source]] = {asset: [] for asset in entry.assets}
    with rasterio.Env(VSI_CACHE_SIZE=str(cache_per_item(len(items) * len(entry.assets)))):
        for item_id in items:
            for asset in entry.assets:
                scene = resolved[(item_id, asset)]
                target = open_asset_ref(
                    scene.asset.to_asset(), access.policy, access.resolve, decode_cf=scene.scaling == "store-cf"
                )
                sources[asset].append(Source.open(scene, target, stack))
    for asset, scenes in sources.items():
        if not all(_north_up(scene) for scene in scenes):
            raise UnsupportedRecipe("only north-up grids are mosaicked")
        _check_alike(asset, scenes)
    anchors = [scenes[0] for scenes in sources.values()]
    coarse_x = max(anchor.transform.a for anchor in anchors)
    coarse_y = max(-anchor.transform.e for anchor in anchors)
    crs = anchors[0].crs
    members: dict[str, list[_Member]] = {}
    bounds = []
    for asset, scenes in sources.items():
        members[asset] = []
        for scene in scenes:
            on_grid = _on_grid(scenes[0], scene)
            if not on_grid and not isinstance(scene.reader, CogReader):
                raise UnsupportedRecipe("a Zarr scene that does not lie on the mosaic grid cannot be warped yet")
            reach = _bounds_in(scene, crs)
            members[asset].append(_Member(scene, on_grid, reach))
            bounds.append(reach)
    # Snapped outward to the coarsest pixel of the first scene, from its own origin, so that the
    # extent is whole pixels for every asset of it (the nested assets of `common_grid`).
    origin_x, origin_y = anchors[0].transform.c, anchors[0].transform.f
    left = origin_x + _floor((min(b[0] for b in bounds) - origin_x) / coarse_x) * coarse_x
    right = origin_x + _ceil((max(b[2] for b in bounds) - origin_x) / coarse_x) * coarse_x
    top = origin_y - _floor((origin_y - max(b[3] for b in bounds)) / coarse_y) * coarse_y
    bottom = origin_y - _ceil((origin_y - min(b[1] for b in bounds)) / coarse_y) * coarse_y
    return [MosaicSource(scenes, (left, bottom, right, top), stack) for scenes in members.values()]

