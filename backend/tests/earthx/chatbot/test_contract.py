"""The chatbot reads what the catalogue really writes (contract test, plan m7a §6).

The tool tests run against hand-written answers; those can drift from what the API
serves without any test noticing. This file closes that gap for the collections:
it builds every registry entry with the same function that loads it into pgstac
(`catalog.collection.to_stac_collection`) and checks that the chatbot finds each
one and reads the fields it promises. If the catalogue renames a field the chatbot
relies on, this fails in the same pull request.

The test may import `catalog`; the chatbot itself may not (.importlinter).
"""

from __future__ import annotations

import pytest

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.datasets import REGISTRY
from earthx.chatbot import summaries

COLLECTIONS = [to_stac_collection(config) for config in REGISTRY]


@pytest.mark.parametrize("collection", COLLECTIONS, ids=[c["id"] for c in COLLECTIONS])
def test_every_catalogue_collection_yields_a_complete_detail(collection: dict) -> None:
    detail = summaries.collection_detail(collection)
    assert detail["id"] == collection["id"]
    assert detail["title"]
    assert detail["description"]
    assert detail["license"]
    assert detail["bbox"] is not None and len(detail["bbox"]) == 4
    assert detail["interval"] is not None
    for field in ("earthx:data_class", "earthx:capabilities", "earthx:license_flags", "earthx:maturity"):
        assert field in detail, field
    assert "earthx:source" not in detail


@pytest.mark.parametrize("collection", COLLECTIONS, ids=[c["id"] for c in COLLECTIONS])
def test_every_catalogue_collection_is_found_by_its_own_title(collection: dict) -> None:
    words = collection["title"].lower().split()
    box = tuple(collection["extent"]["spatial"]["bbox"][0])
    assert summaries.matches(collection, words, box, None)


def test_the_licence_flags_the_chatbot_quotes_are_the_ones_the_catalogue_writes() -> None:
    for collection in COLLECTIONS:
        flags = summaries.collection_detail(collection)["earthx:license_flags"]
        assert {"spdx_id", "commercial_use", "attribution_required", "tier"} <= set(flags)
