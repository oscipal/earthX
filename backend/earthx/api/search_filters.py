"""The search filters of a request, read into conditions per collection (DS-02 plan §6.4).

Two spellings, never both in one request:

* ``query`` — the STAC query extension, for every searched collection whose registry entry offers the property.
  A collection that does not is searched without it and names it in ``ignored_filters_by_collection``, like
  ``datetime`` on a dataset without a time axis; a property no searched collection offers is a ``400``.
* ``query_by_collection`` — ``{collection: <query>}``, the values of each dataset on their own (Otto, 28.10.2026,
  A). Every property must be one its collection offers; nothing is dropped.

Only ``gte``/``lte`` on a range and ``in`` on a list of values. The checks on the values themselves are
``catalog.search_filters``', independent of this spelling. No message names a value of the request.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from earthx.catalog.registry import FILTER_PROPERTY, RESERVED_FILTER_PREFIX, FilterKind, SearchFilter
from earthx.catalog.search_filters import (
    Condition,
    FilterConditions,
    InvalidFilter,
    range_condition,
    values_condition,
)

FILTER_KEYS = frozenset({"query", "query_by_collection"})
_RANGE_OPERATORS = frozenset({"gte", "lte"})
_VALUES_OPERATORS = frozenset({"in"})


@dataclass(frozen=True, slots=True)
class SearchConditions:
    """The conditions each searched collection gets, and the properties of ``query`` a collection does not offer."""

    by_collection: Mapping[str, FilterConditions] = field(default_factory=dict)
    dropped: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


def read_search_conditions(
    body: Mapping[str, Any],
    collection_ids: Sequence[str],
    filters_of: Callable[[str], tuple[SearchFilter, ...]],
) -> SearchConditions:
    """The conditions of a search body over ``collection_ids``; raises :class:`InvalidFilter` for a request a
    caller has to change."""
    query = body.get("query")
    per_collection = body.get("query_by_collection")
    if query is not None and per_collection is not None:
        raise InvalidFilter("send query or query_by_collection, not both")
    offered = {cid: {entry.property: entry for entry in filters_of(cid)} for cid in collection_ids}
    if query is not None:
        return _read_shared(_object(query, "query"), collection_ids, offered)
    if per_collection is not None:
        return _read_per_collection(_object(per_collection, "query_by_collection"), offered)
    return SearchConditions()


def _read_shared(
    query: Mapping[str, Any], collection_ids: Sequence[str], offered: Mapping[str, Mapping[str, SearchFilter]]
) -> SearchConditions:
    by_collection: dict[str, dict[str, Condition]] = {}
    dropped: dict[str, list[str]] = {}
    for name, operators in query.items():
        owners = [cid for cid in collection_ids if name in offered[cid]]
        if not owners:
            raise InvalidFilter(f"{_named(name)} is no filter of a searched collection")
        for cid in collection_ids:
            if cid in owners:
                by_collection.setdefault(cid, {})[name] = _condition(offered[cid][name], operators)
            else:
                dropped.setdefault(cid, []).append(name)
    return SearchConditions(
        by_collection=by_collection, dropped={cid: tuple(sorted(names)) for cid, names in dropped.items()}
    )


def _read_per_collection(
    per_collection: Mapping[str, Any], offered: Mapping[str, Mapping[str, SearchFilter]]
) -> SearchConditions:
    by_collection: dict[str, dict[str, Condition]] = {}
    for cid, query in per_collection.items():
        if cid not in offered:
            raise InvalidFilter("query_by_collection names a collection the search does not")
        for name, operators in _object(query, "query_by_collection").items():
            search_filter = offered[cid].get(name)
            if search_filter is None:
                raise InvalidFilter(f"{_named(name)} is no filter of the collection it is given for")
            by_collection.setdefault(cid, {})[name] = _condition(search_filter, operators)
    return SearchConditions(by_collection=by_collection)


def _condition(search_filter: SearchFilter, operators: Any) -> Condition:
    name = search_filter.property
    if not isinstance(operators, Mapping) or not operators:
        raise InvalidFilter(f"the condition on {name} is an object of operators")
    if search_filter.kind is FilterKind.RANGE:
        if not set(operators) <= _RANGE_OPERATORS:
            raise InvalidFilter(f"{name} takes the operators gte and lte")
        return range_condition(search_filter, operators.get("gte"), operators.get("lte"))
    if set(operators) != _VALUES_OPERATORS:
        raise InvalidFilter(f"{name} takes the operator in")
    return values_condition(search_filter, operators["in"])


def _object(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise InvalidFilter(f"{name} is a JSON object")
    return value


def _named(name: str) -> str:
    """A property of the request in a message only where it has the form of one; anything else stays unnamed."""
    if not FILTER_PROPERTY.match(name):
        return "a property"
    if name.startswith(RESERVED_FILTER_PREFIX):
        return f"{name} (computed by the platform, not offered yet)"
    return name
