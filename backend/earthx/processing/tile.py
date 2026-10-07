"""The tile of an operator (T1): the same inputs, scaling and kernel as the job (adr/0014 §6.2).

`api` builds an :class:`OperatorInput` from the path of a tile URL — the assets named
in it, already cleared through the gateway policy, with the bands and the scaling
source the item describes — and TiTiler's factory opens :class:`OperatorTileReader` on
it. The reader reads each asset's tile through :class:`~earthx.processing.source.Source`
(physical values, named bands, the grid rule of the core) and merges them into one
image; the operator's kernel then runs as TiTiler's ``process_dependency``, the very
function a job calls on a block.

The tile is a *preview* below the native level: rio-tiler reads an overview there, and
only on the native level is the tile bit-identical with the job (§6.3, F9).
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel
from rio_tiler.errors import RioTilerError
from rio_tiler.models import ImageData

from earthx.processing.operators.base import BandMeta, Operator, RasterMeta
from earthx.processing.recipe import ResolvedInput
from earthx.processing.source import Source, common_grid, merge_images
from earthx.readers.cog import AssetPath
from earthx.readers.zarr_reader import ZarrAsset

__all__ = ["OperatorInput", "OperatorTileReader", "TileOptionRefused"]


class TileOptionRefused(RioTilerError):
    """A tile option that has no meaning for an operator's tile (`400` in `api`)."""


@dataclass(frozen=True, slots=True)
class OperatorInput:
    """What the path of an operator tile stands for: its assets, the operator and its parameters."""

    inputs: tuple[tuple[ResolvedInput, AssetPath | ZarrAsset], ...]
    operator: Operator
    params: BaseModel


class OperatorTileReader:
    """Opens the assets of an :class:`OperatorInput` and reads the merged tile in physical values."""

    def __init__(self, source: OperatorInput, *, tms: Any = None, **options: Any) -> None:
        if options:
            raise TileOptionRefused("this reader takes no reader options")
        self._input = source
        self._tms = tms
        self._stack = ExitStack()
        self._sources: list[Source] = []

    def __enter__(self) -> OperatorTileReader:
        try:
            self._sources = [Source.open(entry, target, self._stack) for entry, target in self._input.inputs]
            finest, resampled = common_grid(self._sources)
            bands = tuple(
                BandMeta(name, "float32", None) for source in self._sources for name in source.names
            )
            meta = RasterMeta(finest.crs.to_string(), finest.transform, finest.width, finest.height, bands, resampled)
            # The names and the syntax are judged before the first pixel, as in a job.
            self._input.operator.transform(meta, self._input.params)
        except BaseException:
            self._stack.close()
            raise
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self._stack.close()

    @property
    def _first(self) -> Source:
        return self._sources[0]

    @property
    def minzoom(self) -> int:
        return self._first.reader.minzoom

    @property
    def maxzoom(self) -> int:
        return self._first.reader.maxzoom

    def get_geographic_bounds(self, crs: Any) -> tuple[float, float, float, float]:
        return self._first.reader.get_geographic_bounds(crs)

    def info(self) -> SimpleNamespace:
        return SimpleNamespace(band_descriptions=None, dtype="float32", minmax=None)

    def tile(
        self,
        x: int,
        y: int,
        z: int,
        *,
        tilesize: int | None = None,
        resampling_method: str | None = None,
        buffer: float | None = None,
        padding: int | None = None,
        **refused: Any,
    ) -> ImageData:
        """The merged tile, in physical values; options that would change the values are refused."""
        if refused:
            raise TileOptionRefused(
                f"{', '.join(sorted(refused))} cannot be used with op: the tile is computed in physical values"
            )
        if resampling_method not in (None, "nearest"):
            raise TileOptionRefused("an operator tile is read with nearest resampling")
        options: dict[str, Any] = {"resampling_method": "nearest"}
        for name, value in (("tilesize", tilesize), ("buffer", buffer), ("padding", padding)):
            if value is not None:
                options[name] = value
        return merge_images([source.read_tile(x, y, z, **options) for source in self._sources])
