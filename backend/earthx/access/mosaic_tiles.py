"""The mosaic tile: the scenes of one overpass read into one tile (M4-17a, adr/0006 §4.2 M1).

`api` hands in the scenes as :class:`MosaicScenes` — already cleared through the gateway,
cut down to those that touch the tile, and sorted by
:func:`~earthx.access.crop_rules.mosaic_order` (M4-17b). This module only reads them, with
the rule of the crop, the export job and the mosaic job: per band and pixel the first valid
element in the order of the list (rio-tiler's ``FirstMethod``, the same rule as
:func:`~earthx.access.crop_rules.merge_first_valid`; S5). Nothing here sorts, and nothing
here opens an address that did not come in as an :class:`~earthx.readers.cog.AssetPath` or
a :class:`~earthx.readers.zarr_reader.ZarrAsset`.

**In portions of four** (:data:`MOSAIC_THREADS`, plan M4-17 Frage 5): rio-tiler reads a
portion in parallel and then asks whether every pixel is filled; a tile that the first
scenes cover is done without opening the rest.

**The GDAL configuration follows into the threads.** ``rasterio.Env`` lives in the thread
that entered it; the portion is read in threads of its own. The factory hands the reader the
configuration of the route (its ``environment_dependency``, ``gdal_options`` of the gateway
policy, M1-03), and :meth:`MosaicTileReader.tile` enters it again around every scene.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import morecantile
import rasterio
from attrs import define
from fastapi import Depends
from rasterio.warp import transform_bounds
from rio_tiler.constants import WGS84_CRS
from rio_tiler.errors import EmptyMosaicError, RioTilerError, TileOutsideBounds
from rio_tiler.models import ImageData
from rio_tiler.mosaic import mosaic_reader
from rio_tiler.mosaic.methods.defaults import FirstMethod
from titiler.core.dependencies import DefaultDependency

from earthx.access.tiles import EarthxTilerFactory, open_asset
from earthx.readers.cog import AssetPath
from earthx.readers.zarr_reader import ZarrAsset

__all__ = [
    "MOSAIC_THREADS",
    "EarthxMosaicTilerFactory",
    "MosaicBandsDiffer",
    "MosaicReaderParams",
    "MosaicScenes",
    "MosaicTileReader",
    "open_mosaic",
]

#: Scenes read at the same time, and the size of the portion after which the tile is checked for full.
MOSAIC_THREADS = 4


class MosaicBandsDiffer(RioTilerError):
    """The scenes of one mosaic do not have the same number of bands: a ``422``, not a crash in rio-tiler's ``assert``."""

    status_code = 422


@dataclass(frozen=True, slots=True)
class MosaicScenes:
    """The scenes of one mosaic tile in the order they are read, and where the whole mosaic lies.

    ``bounds`` is west, south, east, north in EPSG:4326 over every scene of the URL, not only
    those of the tile: a TileJSON names the extent of the layer.
    """

    dataset_id: str
    scenes: tuple[AssetPath | ZarrAsset, ...]
    bounds: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        if not self.scenes:
            raise ValueError("a mosaic has at least one scene")
        for scene in self.scenes:
            if not isinstance(scene, (AssetPath, ZarrAsset)):
                raise TypeError("a mosaic reads scenes the gateway cleared, not plain strings (KLAERUNGEN B8)")


@dataclass(frozen=True, slots=True)
class MosaicReaderParams:
    """What the mosaic factory passes its reader besides the scenes: the GDAL configuration of the route."""

    gdal_config: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"gdal_config": dict(self.gdal_config)}


class MosaicTileReader:
    """What TiTiler's tile and TileJSON routes need of a reader, over the scenes of a mosaic."""

    def __init__(
        self,
        source: MosaicScenes,
        *,
        tms: morecantile.TileMatrixSet | None = None,
        gdal_config: Mapping[str, Any] | None = None,
        **options: Any,
    ) -> None:
        if not isinstance(source, MosaicScenes):
            raise TypeError("a mosaic tile reads MosaicScenes")
        self.source = source
        self.tms = tms or morecantile.tms.get("WebMercatorQuad")
        self.gdal_config = dict(gdal_config or {})
        self.options = options

    def __enter__(self) -> MosaicTileReader:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        return None

    @property
    def minzoom(self) -> int:
        return self.tms.minzoom

    @property
    def maxzoom(self) -> int:
        return self.tms.maxzoom

    @property
    def order(self) -> tuple[str, ...]:
        """The item ids in the order the tile reads them."""
        return tuple(scene.item_id for scene in self.source.scenes)

    def get_geographic_bounds(self, crs: Any) -> tuple[float, float, float, float]:
        if crs == WGS84_CRS:
            return self.source.bounds
        return transform_bounds(WGS84_CRS, crs, *self.source.bounds, densify_pts=21)

    def info(self) -> Any:
        """The bands of the first scene; the scenes of one mosaic carry the same bands (M4-12a)."""
        with open_asset(self.source.scenes[0], tms=self.tms, **self.options) as reader:
            return reader.info()

    def tile(self, tile_x: int, tile_y: int, tile_z: int, **kwargs: Any) -> ImageData:
        """The tile, scene by scene in the order of the list, the first valid pixel winning.

        Only ``TileOutsideBounds`` skips a scene. Any other failure fails the tile: a scene left
        out silently would let another one win where they overlap.
        """

        band_counts: set[int] = set()
        lock = threading.Lock()

        def read(scene: AssetPath | ZarrAsset, x: int, y: int, z: int, **options: Any) -> ImageData:
            with rasterio.Env(**self.gdal_config), open_asset(scene, tms=self.tms, **self.options) as reader:
                image = reader.tile(x, y, z, **options)
            with lock:
                band_counts.add(image.count)
                if len(band_counts) > 1:
                    raise MosaicBandsDiffer("the scenes of a mosaic have to have the same number of bands")
            return image

        try:
            image, _ = mosaic_reader(
                list(self.source.scenes),
                read,
                tile_x,
                tile_y,
                tile_z,
                pixel_selection=FirstMethod(),
                threads=MOSAIC_THREADS,
                chunk_size=MOSAIC_THREADS,
                allowed_exceptions=(TileOutsideBounds,),
                **kwargs,
            )
        except EmptyMosaicError:
            raise TileOutsideBounds("the tile does not touch these scenes") from None
        return image


def open_mosaic(src_path: Any, **reader_params: Any) -> MosaicTileReader:
    """The reader of the mosaic factory, in the shape TiTiler calls it (``self.reader(src_path, …)``)."""
    return MosaicTileReader(src_path, **reader_params)


@define(kw_only=True)
class EarthxMosaicTilerFactory(EarthxTilerFactory):
    """The tile and the TileJSON of :class:`EarthxTilerFactory`, over a mosaic, and nothing else.

    No ``/info``, ``/statistics``, ``/point`` or ``/tilesets``: the viewer measures the stretch
    on one scene as before (plan M4-17 §6), and a route nobody needs is a route nobody secures.

    The reader's parameters are the GDAL configuration of the route (:class:`MosaicReaderParams`);
    a ``reader_dependency`` handed in would replace it silently, so it is refused.
    """

    reader: Any = open_mosaic

    def __attrs_post_init__(self) -> None:
        if self.reader_dependency is not DefaultDependency:
            raise TypeError("the mosaic factory sets its own reader_dependency (the GDAL configuration of the route)")
        environment = self.environment_dependency

        def mosaic_reader_params(env: dict[str, Any] = Depends(environment)) -> MosaicReaderParams:  # noqa: B008
            return MosaicReaderParams(env)

        self.reader_dependency = mosaic_reader_params
        super().__attrs_post_init__()

    def tilejson_extras(self, src_dst: Any) -> dict[str, Any]:
        """``earthx:order``: the scenes in the order a tile reads them, so a client below the mosaic's
        first zoom level can stack single scenes the same way (plan M4-17 §4.1, §4.6)."""
        return {"earthx:order": list(src_dst.order)}

    def register_routes(self) -> None:
        self.tile()
        self.tilejson()
