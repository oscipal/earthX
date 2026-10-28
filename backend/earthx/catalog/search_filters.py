"""What a search asks of a dataset's filters, independent of how a request spells it (DS-02 plan §6.5, B).

``api`` reads a request (the STAC ``query`` form today) into these conditions, checked against the dataset's
:class:`~earthx.catalog.registry.SearchFilter`; an adapter writes them in its source's own form. A source that
speaks CQL2 instead needs a translation in its adapter, not a change here.

No message names a value of the request: an error text becomes a response body and can become a log line.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from earthx.catalog.registry import FilterKind, SearchFilter

# More than any filter offers today (three satellites); a longer list is no choice but a mistake.
MAX_VALUES = 32


class InvalidFilter(ValueError):
    """A condition the dataset's filter does not allow."""


@dataclass(frozen=True, slots=True)
class RangeCondition:
    """``minimum <= value <= maximum``; a bound that is None is open."""

    minimum: float | None
    maximum: float | None


@dataclass(frozen=True, slots=True)
class ValuesCondition:
    """The value is one of ``values`` (sorted, each once)."""

    values: tuple[str, ...]


Condition = RangeCondition | ValuesCondition
# The conditions on one dataset, by property.
FilterConditions = Mapping[str, Condition]


def range_condition(search_filter: SearchFilter, minimum: Any, maximum: Any) -> RangeCondition:
    """A checked range on a ``RANGE`` filter: numbers inside its bounds, whole where it asks for that, low ≤ high."""
    name = search_filter.property
    if search_filter.kind is not FilterKind.RANGE:
        raise InvalidFilter(f"{name} takes a list of values, not a range")
    if minimum is None and maximum is None:
        raise InvalidFilter(f"the range on {name} has no bound")
    low = _bound(search_filter, minimum)
    high = _bound(search_filter, maximum)
    if low is not None and high is not None and low > high:
        raise InvalidFilter(f"the range on {name} ends below its start")
    return RangeCondition(minimum=low, maximum=high)


def _bound(search_filter: SearchFilter, value: Any) -> float | None:
    if value is None:
        return None
    name = search_filter.property
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InvalidFilter(f"a bound on {name} is not a number")
    low, high = search_filter.minimum, search_filter.maximum  # both set on a RANGE (registry)
    if low is None or high is None or not low <= value <= high:
        raise InvalidFilter(f"a bound on {name} lies outside the range the filter offers")
    if search_filter.integer and not float(value).is_integer():
        raise InvalidFilter(f"a bound on {name} is not a whole number")
    return float(value)


def values_condition(search_filter: SearchFilter, values: Any) -> ValuesCondition:
    """A checked choice on a ``VALUES`` filter: a non-empty list of values it offers, each once."""
    name = search_filter.property
    if search_filter.kind is not FilterKind.VALUES:
        raise InvalidFilter(f"{name} takes a range, not a list of values")
    if not isinstance(values, list) or not values or len(values) > MAX_VALUES:
        raise InvalidFilter(f"the values for {name} are a non-empty list")
    offered = {entry.value for entry in search_filter.values}
    if not all(isinstance(value, str) and value in offered for value in values):
        raise InvalidFilter(f"a value for {name} is not one it offers")
    if len(set(values)) != len(values):
        raise InvalidFilter(f"a value for {name} is listed twice")
    return ValuesCondition(values=tuple(sorted(values)))


def conditions_key(conditions: FilterConditions) -> dict[str, list[Any]]:
    """The conditions as plain JSON in one spelling, for a search fingerprint: the same question hashes the same."""
    key: dict[str, list[Any]] = {}
    for name, condition in sorted(conditions.items()):
        if isinstance(condition, RangeCondition):
            key[name] = ["range", condition.minimum, condition.maximum]
        else:
            key[name] = ["values", list(condition.values)]
    return key
