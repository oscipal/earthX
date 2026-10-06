"""The shared item source of `api` and `tiler` (M3-11a §3.3, moved out of
`api/tiler.py` in M4-01a), and the start-up comparison of pgstac with the registry.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from earthx.adapters import UnknownCollection
from earthx.api.item_source import (
    ItemHoldingMismatch,
    MaterializedCatalogUnavailable,
    MaterializedItemNotFound,
    build_item_source,
    check_item_holdings,
    item_holding_of,
)
from earthx.catalog.datasets import REGISTRY, SENTINEL_2_L2A
from earthx.catalog.registry import CoverageProvider, DatasetConfig, DatasetRegistry, ItemHolding


def _materialized_entry() -> Any:
    return replace(
        SENTINEL_2_L2A,
        source=replace(SENTINEL_2_L2A.source, item_holding=ItemHolding.MATERIALIZED),
        coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL),
    )


class _FakeConnection:
    """Stands in for whatever ``pool.connection()`` yields — ``fetch_item`` is
    monkeypatched in every test that uses this, so nothing here ever runs a query."""

    async def __aenter__(self) -> "_FakeConnection":
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class _FakePool:
    def connection(self) -> _FakeConnection:
        return _FakeConnection()


class TestBuildItemSourceDispatchesByHolding:
    """M3-11a §3.3: the tiler's own item source, one level below any route — a
    materialized dataset reads pgstac directly (`catalog.pgstac.fetch_item`), a
    federated one still goes through the adapter and gateway exactly as before.
    """

    @pytest.mark.anyio
    async def test_a_materialized_item_comes_from_pgstac(self, monkeypatch: pytest.MonkeyPatch) -> None:
        materialized = _materialized_entry()
        registry = DatasetRegistry((materialized,))
        seen: list[tuple[str, str]] = []

        async def fake_fetch_item(conn: object, dataset_id: str, item_id: str) -> dict[str, Any]:
            seen.append((dataset_id, item_id))
            return {"id": item_id, "type": "Feature"}

        monkeypatch.setattr("earthx.api.item_source.fetch_item", fake_fetch_item)
        item_source = build_item_source(registry, gateway=object(), pool=_FakePool())

        item = await item_source(materialized.dataset_id, "some-item")

        assert item == {"id": "some-item", "type": "Feature"}
        assert seen == [(materialized.dataset_id, "some-item")]

    @pytest.mark.anyio
    async def test_a_materialized_item_missing_in_pgstac_is_reported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        materialized = _materialized_entry()
        registry = DatasetRegistry((materialized,))

        async def fake_fetch_item(conn: object, dataset_id: str, item_id: str) -> None:
            return None

        monkeypatch.setattr("earthx.api.item_source.fetch_item", fake_fetch_item)
        item_source = build_item_source(registry, gateway=object(), pool=_FakePool())

        with pytest.raises(MaterializedItemNotFound):
            await item_source(materialized.dataset_id, "no-such-item")

    @pytest.mark.anyio
    async def test_a_materialized_dataset_without_a_pool_is_unavailable(self) -> None:
        """Unlike a federated dataset, where no pool merely means no cache (E5), a
        materialized dataset's items have no other place to come from at all."""
        materialized = _materialized_entry()
        registry = DatasetRegistry((materialized,))
        item_source = build_item_source(registry, gateway=object(), pool=None)

        with pytest.raises(MaterializedCatalogUnavailable):
            await item_source(materialized.dataset_id, "some-item")

    @pytest.mark.anyio
    async def test_a_federated_dataset_is_unaffected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The pre-existing path — no pool, straight to the adapter — still runs for
        a federated entry, proving the new branch above did not swallow it."""
        seen: list[str] = []

        async def fake_get_item(config: DatasetConfig, item_id: str, *, gateway: object) -> dict[str, Any]:
            seen.append(config.dataset_id)
            return {"id": item_id}

        monkeypatch.setattr("earthx.api.item_source.get_item", fake_get_item)
        item_source = build_item_source(REGISTRY, gateway=object(), pool=None)

        item = await item_source(SENTINEL_2_L2A.dataset_id, "some-item")

        assert item == {"id": "some-item"}
        assert seen == [SENTINEL_2_L2A.dataset_id]


class TestItemHoldingOf:
    def test_the_registry_decides(self) -> None:
        registry = DatasetRegistry((_materialized_entry(),))
        assert item_holding_of(registry, SENTINEL_2_L2A.dataset_id) is ItemHolding.MATERIALIZED
        assert item_holding_of(REGISTRY, SENTINEL_2_L2A.dataset_id) is ItemHolding.FEDERATED

    def test_an_unknown_dataset_is_an_unknown_collection(self) -> None:
        with pytest.raises(UnknownCollection):
            item_holding_of(REGISTRY, "no-such-dataset")


class TestCheckItemHoldings:
    """Otto, M4-01a F2: the start fails only where both know a collection and
    disagree; a collection only pgstac knows is a warning."""

    @pytest.fixture
    def stored(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, str | None]:
        holdings: dict[str, str | None] = {}

        async def fake_read(conn: object) -> dict[str, str | None]:
            return dict(holdings)

        monkeypatch.setattr("earthx.api.item_source.read_item_holdings", fake_read)
        return holdings

    @pytest.mark.anyio
    async def test_agreeing_holdings_pass(self, stored: dict[str, str | None]) -> None:
        stored.update({config.dataset_id: config.source.item_holding.value for config in REGISTRY})
        assert await check_item_holdings(REGISTRY, object()) == ()

    @pytest.mark.anyio
    async def test_an_empty_catalogue_passes(self, stored: dict[str, str | None]) -> None:
        """A registry entry pgstac does not know is pgstac's own 404 later (rule I)."""
        assert await check_item_holdings(REGISTRY, object()) == ()

    @pytest.mark.anyio
    @pytest.mark.parametrize("value", ["materialized", None, "harvested"])
    async def test_a_different_holding_stops_the_start(self, stored: dict[str, str | None], value: str | None) -> None:
        stored.update({config.dataset_id: config.source.item_holding.value for config in REGISTRY})
        stored[SENTINEL_2_L2A.dataset_id] = value
        with pytest.raises(ItemHoldingMismatch, match=SENTINEL_2_L2A.dataset_id) as caught:
            await check_item_holdings(REGISTRY, object())
        assert "catalog.load" in str(caught.value)

    @pytest.mark.anyio
    async def test_every_mismatch_is_named(self, stored: dict[str, str | None]) -> None:
        stored.update({config.dataset_id: "other" for config in REGISTRY})
        with pytest.raises(ItemHoldingMismatch) as caught:
            await check_item_holdings(REGISTRY, object())
        assert all(config.dataset_id in str(caught.value) for config in REGISTRY)

    @pytest.mark.anyio
    async def test_a_collection_only_pgstac_knows_is_a_warning(
        self, stored: dict[str, str | None], caplog: pytest.LogCaptureFixture
    ) -> None:
        stored.update({"left-over": "federated", "broken": None})
        with caplog.at_level("WARNING", logger="earthx.api.item_source"):
            assert await check_item_holdings(REGISTRY, object()) == ("broken", "left-over")
        [record] = caplog.records
        assert record.collections == ["broken", "left-over"]
