"""T-C: a process does not start while pgstac and the registry hold a dataset's
items differently (adr/0011 §7 D2, Otto's answer M4-01a F2).

The collection is loaded as *materialized*; the registry the app is built with
says *federated* for the same id. Every request would then be routed past the
items pgstac really holds.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

import psycopg
import pytest

from earthx.api import tiler
from earthx.api.item_source import ItemHoldingMismatch
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.pgstac import load_collection, use_pgstac_search_path
from earthx.catalog.registry import CoverageProvider, DatasetRegistry, ItemHolding

pytestmark = pytest.mark.anyio

DATASET = "earthx-test-holding-check"

FEDERATED = replace(
    SENTINEL_2_L2A,
    dataset_id=DATASET,
    source=replace(SENTINEL_2_L2A.source, source_collection_id=DATASET, harvest_run=None),
)
MATERIALIZED = replace(
    FEDERATED,
    source=replace(FEDERATED.source, item_holding=ItemHolding.MATERIALIZED),
    coverage=replace(FEDERATED.coverage, provider=CoverageProvider.LOCAL_SQL),
)


@pytest.fixture
def loaded_as_materialized(require_postgres_env: None) -> Iterator[None]:
    with psycopg.connect(autocommit=True) as conn:
        load_collection(conn, MATERIALIZED)
    yield
    with psycopg.connect(autocommit=True) as conn:
        use_pgstac_search_path(conn)
        conn.execute("SELECT pgstac.delete_collection(%s)", (DATASET,))


class TestTiler:
    async def test_a_different_holding_stops_the_start(self, loaded_as_materialized: None) -> None:
        app = tiler.build_app(DatasetRegistry((FEDERATED,)))
        with pytest.raises(ItemHoldingMismatch, match=DATASET):
            async with app.router.lifespan_context(app):
                pass

    async def test_the_same_holding_starts(self, loaded_as_materialized: None) -> None:
        app = tiler.build_app(DatasetRegistry((MATERIALIZED,)))
        async with app.router.lifespan_context(app):
            assert app.state.earthx_item_source is not None
