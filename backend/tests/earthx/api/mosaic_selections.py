"""Doubles for the selection of a mosaic (M5-30b part 3) in tests that run the real tiler without a database.

``MemorySelections`` keeps what the real store keeps, as the JSON document of the row, so that a selection read back has
gone through the same round trip; ``batch_source_of`` is the source of items by id, which records what it was asked.
The SQL of the real store is tested against a real Postgres in ``backend/tests/integration/test_mosaic_selection.py``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from fastapi.testclient import TestClient

from earthx.api.mosaic_selection import Selection


class MemorySelections:
    """The stored selections of an app: an id to ``(dataset, document)``, with a way to let one expire."""

    def __init__(self) -> None:
        self.rows: dict[str, tuple[str, dict[str, Any]]] = {}
        self.renewed: list[str] = []

    async def get(self, selection_id: str) -> Selection | None:
        row = self.rows.get(selection_id)
        return None if row is None else Selection.from_document(selection_id, *row)

    async def renew(self, selection_id: str) -> bool:
        if selection_id in self.rows:
            self.renewed.append(selection_id)
        return selection_id in self.rows

    async def put(self, selection: Selection) -> None:
        self.rows[selection.selection_id] = (selection.dataset_id, json.loads(json.dumps(selection.document())))

    def expire(self, selection_id: str) -> None:
        del self.rows[selection_id]


def batch_source_of(items: Mapping[str, dict[str, Any]], asked: list[list[str]] | None = None) -> Any:
    """An ``ItemBatchSource`` over ``items``: the ones it has, each as a copy; ``asked`` gets one entry per call."""

    async def batch(dataset_id: str, item_ids: Sequence[str]) -> list[dict[str, Any]]:
        if asked is not None:
            asked.append(list(item_ids))
        return [json.loads(json.dumps(items[item_id])) for item_id in item_ids if item_id in items]

    return batch


def create(api: TestClient, dataset: str, items: Sequence[str], assets: Sequence[str]) -> str:
    """Create the selection through the route and return its id; the route must have taken it (``201`` or ``200``)."""
    response = api.post(f"/collections/{dataset}/mosaic", json={"items": list(items), "assets": list(assets)})
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]
