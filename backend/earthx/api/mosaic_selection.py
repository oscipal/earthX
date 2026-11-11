"""A mosaic selection as `api` holds it: what the tiles need of it, and where it is kept (M5-30b part 3, adr/0032 §10.2).

The creation of a selection (``POST /collections/{dataset}/mosaic``) fetches its scenes once, checks them (one overpass,
the same scaling, units and bands over all scenes and assets) and derives what every tile of the mosaic then needs
without fetching the scenes again: the order they are read in (`access.crop_rules.mosaic_order`), the outline of each as
the item carries it, the extent, and how the first scene describes each asset (the scenes are alike, so it stands for all).
A tile reads a selection by its id and fetches only the items it reads; the TileJSON fetches none.

The row of the selection is the truth (`catalog.mosaic_selection`, seven days). The process keeps the last ones in memory
for a few minutes, which is safe because the content of an id never changes; after that the row is asked again, so an
expired selection answers ``410`` at most a few minutes late.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from shapely.geometry.base import BaseGeometry

from earthx.api.mosaic_tiles import footprints_of, union_bounds
from earthx.catalog import mosaic_selection as stored

__all__ = ["LOADED_KEPT_S", "LOADED_MAX_ENTRIES", "LOADED_MAX_ITEMS", "Selection", "SelectionStore", "outline_source"]

#: How long a loaded selection may be served from memory before its row is asked again.
LOADED_KEPT_S = 120.0
#: At most this many selections in memory, and this many scenes over all of them (a selection of 2 000 scenes weighs more).
LOADED_MAX_ENTRIES = 256
LOADED_MAX_ITEMS = 20_000


def outline_source(item: Mapping[str, Any]) -> dict[str, Any]:
    """What :func:`~earthx.api.mosaic_tiles.footprints_of` reads of an item: its geometry, or its bbox where it has none."""
    return {"geometry": item["geometry"]} if item.get("geometry") else {"bbox": item.get("bbox")}


@dataclass(frozen=True, slots=True)
class Selection:
    """The content of a selection with what the tiles derive from it."""

    selection_id: str
    dataset_id: str
    assets: tuple[str, ...]
    items: tuple[str, ...]
    #: The item ids in the order the mosaic reads them.
    order: tuple[str, ...]
    #: Per item what :func:`outline_source` gave; the stored form of ``outlines``.
    sources: Mapping[str, dict[str, Any]]
    #: West, south, east, north in EPSG:4326 over every scene.
    bounds: tuple[float, float, float, float]
    outlines: Mapping[str, BaseGeometry]
    #: Per asset the first scene's description (a ``ResolvedInput`` as JSON): the bands, scaling and unit all scenes share.
    described: Mapping[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        selection_id: str,
        dataset_id: str,
        assets: Sequence[str],
        sources: Mapping[str, dict[str, Any]],
        order: Sequence[str],
        described: Mapping[str, dict[str, Any]],
    ) -> Selection:
        """From the outline sources of the items (checked as a tile would, :class:`OrderRefused` ``502`` for a broken one)."""
        outlines = footprints_of(sources)
        return cls(
            selection_id,
            dataset_id,
            tuple(sorted(set(assets))),
            tuple(sorted(sources)),
            tuple(order),
            dict(sources),
            union_bounds(outlines),
            outlines,
            dict(described),
        )

    def document(self) -> dict[str, Any]:
        """The ``content`` of the row: the hashed content and what was derived from it."""
        return {
            "dataset": self.dataset_id,
            "assets": list(self.assets),
            "items": list(self.items),
            "order": list(self.order),
            "outlines": dict(self.sources),
            "bounds": list(self.bounds),
            "described": dict(self.described),
        }

    @classmethod
    def from_document(cls, selection_id: str, dataset_id: str, content: Mapping[str, Any]) -> Selection:
        sources = content["outlines"]
        outlines = footprints_of(sources)
        west, south, east, north = content["bounds"]
        return cls(
            selection_id,
            dataset_id,
            tuple(content["assets"]),
            tuple(content["items"]),
            tuple(content["order"]),
            dict(sources),
            (west, south, east, north),
            outlines,
            dict(content["described"]),
        )


class SelectionStore:
    """The selections of the tiler: the table over a pool, with the last ones in memory.

    A connection of the pool only around a read or a write. A database failure is the caller's to map (a ``503``).
    """

    def __init__(
        self,
        pool: Any,
        *,
        clock: Callable[[], float] = time.monotonic,
        kept_s: float = LOADED_KEPT_S,
        max_entries: int = LOADED_MAX_ENTRIES,
        max_items: int = LOADED_MAX_ITEMS,
    ) -> None:
        self._pool = pool
        self._clock = clock
        self._kept_s = kept_s
        self._max_entries = max_entries
        self._max_items = max_items
        self._loaded: OrderedDict[str, tuple[float, Selection]] = OrderedDict()

    async def get(self, selection_id: str) -> Selection | None:
        """The selection, or ``None`` if there is none by this id or it has expired."""
        kept = self._loaded.get(selection_id)
        if kept is not None:
            if self._clock() - kept[0] <= self._kept_s:
                self._loaded.move_to_end(selection_id)
                return kept[1]
            del self._loaded[selection_id]
        async with self._pool.connection() as conn:
            row = await stored.load(conn, selection_id)
        if row is None:
            return None
        selection = Selection.from_document(selection_id, *row)
        self._remember(selection)
        return selection

    async def renew(self, selection_id: str) -> bool:
        """Move the end of an existing selection seven days out; ``False`` if there is none (or it has expired)."""
        async with self._pool.connection() as conn:
            return await stored.renew(conn, selection_id)

    async def put(self, selection: Selection) -> None:
        async with self._pool.connection() as conn:
            await stored.save(conn, selection.selection_id, selection.dataset_id, selection.document())
        self._remember(selection)

    def _remember(self, selection: Selection) -> None:
        self._loaded[selection.selection_id] = (self._clock(), selection)
        self._loaded.move_to_end(selection.selection_id)
        weight = sum(len(kept.items) for _, kept in self._loaded.values())
        while self._loaded and (len(self._loaded) > self._max_entries or weight > self._max_items):
            _, (_, dropped) = self._loaded.popitem(last=False)
            weight -= len(dropped.items)
