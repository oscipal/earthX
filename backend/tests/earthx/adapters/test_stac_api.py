"""M5-08: one module for STAC APIs, one dialect per source (adr/0011 F6, §8.2).

What Earth Search sends and answers is pinned in ``test_earth_search_golden.py`` and
``test_earth_search.py``; this covers the dialect itself and its tie to the spec table.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from earthx.adapters import ADAPTER_SPECS, UnsupportedSource
from earthx.adapters.federated_search import FilterSupport
from earthx.adapters.stac_api import DIALECTS, EARTH_SEARCH, StacDialect, dialect_of, query_extension
from earthx.catalog.registry import AdapterKind
from earthx.catalog.search_filters import RangeCondition
from tests.catalog.entries import COP_DEM_GLO_30, SENTINEL_2_L2A


class TestDialect:
    def test_conditions_without_a_query_at_the_source_are_refused(self) -> None:
        with pytest.raises(ValueError, match="conditions are written exactly when"):
            replace(EARTH_SEARCH, filters=replace(EARTH_SEARCH.filters, query=False))

    def test_a_query_at_the_source_without_a_writer_is_refused(self) -> None:
        with pytest.raises(ValueError, match="conditions are written exactly when"):
            replace(EARTH_SEARCH, write_conditions=None)

    def test_a_source_without_a_query_needs_no_writer(self) -> None:
        dialect = StacDialect(
            kind=AdapterKind.EARTH_SEARCH_V1,
            marker_field="cursor",
            filters=FilterSupport(intersects=True, ids=True, cql2=False, query=False),
            write_conditions=None,
            normalize_item=lambda item: item,
        )
        assert dialect.write_conditions is None

    def test_earth_search_writes_the_query_extension(self) -> None:
        conditions = {"eo:cloud_cover": RangeCondition(minimum=None, maximum=20.0)}
        assert EARTH_SEARCH.write_conditions is not None
        assert EARTH_SEARCH.write_conditions(conditions) == {"query": query_extension(conditions)}


class TestTheTable:
    def test_every_dialect_is_keyed_by_its_own_kind(self) -> None:
        assert all(kind is dialect.kind for kind, dialect in DIALECTS.items())

    def test_the_spec_table_declares_the_filters_of_the_dialect(self) -> None:
        """One measurement, one place: the dispatch refuses by the spec, the body is built by the dialect."""
        for kind, dialect in DIALECTS.items():
            assert ADAPTER_SPECS[kind].filters is dialect.filters

    def test_the_earth_search_entry_finds_its_dialect(self) -> None:
        assert dialect_of(SENTINEL_2_L2A) is EARTH_SEARCH

    def test_an_entry_of_a_bucket_has_no_dialect(self) -> None:
        with pytest.raises(UnsupportedSource, match="is no STAC API"):
            dialect_of(COP_DEM_GLO_30)
