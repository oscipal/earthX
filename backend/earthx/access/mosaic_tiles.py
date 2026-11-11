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
configuration of the route (its ``environment_dependency``, ``tile_gdal_options`` of the gateway
policy, M1-03, NM4-26), and :meth:`MosaicTileReader.tile` enters it again around every scene.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
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
    "MAX_MOSAIC_THREADS",
    "MOSAIC_THREADS",
    "EarthxMosaicTilerFactory",
    "MosaicBandsDiffer",
    "MosaicOutOfTime",
    "MosaicReaderParams",
    "MosaicScenes",
    "MosaicTileReader",
    "ReadBudget",
    "open_mosaic",
]

#: Scenes read at the same time, and the size of the portion after which the tile is checked for full. Four after
#: Otto's run of 11.11.2026 (plan M5-30b §8.6): eight threads made a cold tile of swissALTI3D 25 % faster and a warm one
#: no faster (the read is bound by the CPU), and four stay under the six connections per host of the gateway.
MOSAIC_THREADS = 4
#: The most threads a reader may be given (the measurement compares counts up to this one).
MAX_MOSAIC_THREADS = 16


class MosaicBandsDiffer(RioTilerError):
    """The scenes of one mosaic do not have the same number of bands: a ``422``, not a crash in rio-tiler's ``assert``."""

    status_code = 422


class MosaicOutOfTime(RioTilerError):
    """The time of a tile ran out before any scene was read: a ``503`` the client may ask again (adr/0032 §6.2)."""

    status_code = 503


class ReadBudget:
    """The time one mosaic tile may read for (adr/0032 §6.2, F6), and whether it ran out.

    The clock starts with the read of the tile. A scene that has not begun when the time is up is not read: the tile
    keeps what the scenes before it gave, in the order of the mosaic. Such a tile depends on how fast the source
    answered, so the route sends it with ``no-store`` (``timed_out``); a scene already being read finishes.
    """

    def __init__(self, seconds: float, *, clock: Callable[[], float] = time.monotonic) -> None:
        if not seconds > 0:
            raise ValueError("a read budget is a positive number of seconds")
        self.seconds = seconds
        self._clock = clock
        self._deadline: float | None = None
        self.timed_out = False

    def start(self) -> None:
        self._deadline = self._clock() + self.seconds

    def spent(self) -> bool:
        """``True`` once the time is up; from then on the budget says it timed out."""
        if self._deadline is not None and self._clock() >= self._deadline:
            self.timed_out = True
        return self.timed_out


class _NotRead(Exception):
    """A scene the budget left out; skipped like a scene outside the tile."""


@dataclass(frozen=True, slots=True)
class MosaicScenes:
    """The scenes of one mosaic tile in the order they are read, and where the whole mosaic lies.

    ``bounds`` is west, south, east, north in EPSG:4326 over every scene of the URL, not only
    those of the tile: a TileJSON names the extent of the layer. ``budget`` is the time the tile may read
    for; ``None`` for a TileJSON, which reads no tile.
    """

    dataset_id: str
    scenes: tuple[AssetPath | ZarrAsset, ...]
    bounds: tuple[float, float, float, float]
    budget: ReadBudget | None = field(default=None, compare=False)

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
    """What TiTiler's tile and TileJSON routes need of a reader, over the scenes of a mosaic.

    ``threads`` is the number of scenes read at the same time and the size of a portion; the routes leave it at
    :data:`MOSAIC_THREADS`, the measurement of the tile path (`api.measure_tiles`) compares other counts.
    """

    def __init__(
        self,
        source: MosaicScenes,
        *,
        tms: morecantile.TileMatrixSet | None = None,
        gdal_config: Mapping[str, Any] | None = None,
        threads: int = MOSAIC_THREADS,
        **options: Any,
    ) -> None:
        if not isinstance(source, MosaicScenes):
            raise TypeError("a mosaic tile reads MosaicScenes")
        if not 1 <= threads <= MAX_MOSAIC_THREADS:
            raise ValueError(f"threads is 1 to {MAX_MOSAIC_THREADS}")
        self.threads = threads
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

        Only ``TileOutsideBounds`` skips a scene, and the end of the read budget: a scene that has not begun when
        the time is up is left out, so the tile keeps what the scenes before it gave. Any other failure fails the
        tile: a scene left out silently would let another one win where they overlap.
        """

        band_counts: set[int] = set()
        lock = threading.Lock()
        budget = self.source.budget
        if budget is not None:
            budget.start()

        def read(scene: AssetPath | ZarrAsset, x: int, y: int, z: int, **options: Any) -> ImageData:
            if budget is not None and budget.spent():
                raise _NotRead
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
                threads=self.threads,
                chunk_size=self.threads,
                allowed_exceptions=(TileOutsideBounds, _NotRead),
                **kwargs,
            )
        except EmptyMosaicError:
            if budget is not None and budget.timed_out:
                raise MosaicOutOfTime("the tile ran out of time before a scene was read; ask again") from None
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
    a ``reader_dependency`` handed in would replace it silently, so it is refused. `api` hands in a reader of its
    own for a mosaic with steps (NM4-04); `access` imports nothing of the worker core that reads it.
    """

    reader: Any = open_mosaic
    # A mosaic is drawn with tiles of 512 px (NM4-29 §15): its tiles are dear and a view asks for a third of them.
    tile_size: int = 512

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
        first zoom level can stack single scenes the same way (plan M4-17 §4.1, §4.6); with steps also their ``unit``
        (NM4-04)."""
        return {**super().tilejson_extras(src_dst), "earthx:order": list(src_dst.order)}

    def register_routes(self) -> None:
        self.tile()
        self.tilejson()
