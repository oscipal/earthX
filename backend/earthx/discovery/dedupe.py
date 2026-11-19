"""Dedupe: one main entry per dataset across sources (M5-20 plan §8, §13b; F4 = 1).

Keys are exact, never fuzzy, and never the page of a dataset at its provider (Otto's measurement M6: shared pages are
collection pages within one source, never the same dataset across sources):

* ``doi:`` the DOI;
* ``id:`` the DCAT identifier of the dataset;
* ``coll:<host>/<id>`` a STAC collection: its own id for a find of a STAC source or a full entry, and for any other
  find the id of a collection that stands as a whole token in one of its addresses (opendata.swiss names the FSDI
  collections it lists, M7). Only ids with two dots or more are looked for in addresses (``ch.swisstopo.x``): a short
  id such as ``sentinel-2-l2a`` is too common a word. A find whose addresses name several collections gets none.

Finds that share a key, directly or through others, are one group; its main entry is the one first by rank (full
entry, hand entry, then the source's ``dedupe_rank``, the rank of the link "Source", a footprint, the source and the
key). Pure: no database, no request.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

__all__ = ["Member", "collection_tokens", "find_keys", "main_entries"]

#: How an address is cut into tokens: an id is whole between these.
_DELIMITERS = re.compile(r"[/?&=#,;:\s|]+")
_NAMESPACED = re.compile(r"[a-z0-9][a-z0-9_-]*(?:\.[a-z0-9_-]+){2,}")


def collection_tokens(addresses: Iterable[str], known: Mapping[str, str]) -> set[str]:
    """The keys of the known collections (id → host) whose ids stand as whole tokens in ``addresses``."""
    found: set[str] = set()
    for address in addresses:
        for token in _DELIMITERS.split(address.lower()):
            host = known.get(token)
            if host is not None:
                found.add(f"coll:{host}/{token}")
    return found


def namespaced(collection_id: str) -> bool:
    """Whether an id is long enough to be looked for in the addresses of other finds."""
    return _NAMESPACED.fullmatch(collection_id.lower()) is not None


def find_keys(
    found: Mapping[str, Any], *, stac_host: str | None, known: Mapping[str, str]
) -> tuple[str, ...]:
    """The dedupe keys of an intermediate form; ``stac_host`` is the host of a STAC source, ``None`` otherwise."""
    keys: set[str] = set()
    doi = found.get("doi")
    if isinstance(doi, str) and doi.strip():
        keys.add(f"doi:{doi.strip().lower()}")
    identifier = found.get("identifier")
    if isinstance(identifier, str) and identifier.strip():
        keys.add(f"id:{identifier.strip()}")
    if stac_host is not None:
        keys.add(f"coll:{stac_host}/{found['source_key']}")
    else:
        addresses = [found.get("source_url"), found.get("landing_url")]
        addresses += [d.get("href") for d in found.get("distributions") or () if isinstance(d, dict)]
        tokens = collection_tokens((a for a in addresses if isinstance(a, str)), known)
        if len(tokens) == 1:
            keys |= tokens
    return tuple(sorted(keys))


@dataclass(frozen=True, slots=True)
class Member:
    """One entry that takes part in dedupe; ``rank`` orders a group (the smallest is the main entry)."""

    dataset_id: str
    keys: tuple[str, ...]
    rank: tuple[Any, ...]


def main_entries(members: Iterable[Member]) -> dict[str, str]:
    """For every member that is not the main entry of its group, the id of that main entry."""
    members = list(members)
    parent: dict[str, str] = {}

    def root(item: str) -> str:
        while parent.setdefault(item, item) != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    by_key: dict[str, str] = {}
    for member in members:
        root(member.dataset_id)
        for key in member.keys:
            if key in by_key:
                parent[root(member.dataset_id)] = root(by_key[key])
            else:
                by_key[key] = member.dataset_id
    groups: dict[str, list[Member]] = {}
    for member in members:
        groups.setdefault(root(member.dataset_id), []).append(member)
    duplicates: dict[str, str] = {}
    for group in groups.values():
        if len(group) < 2:
            continue
        main = min(group, key=lambda m: (m.rank, m.dataset_id))
        duplicates.update({m.dataset_id: main.dataset_id for m in group if m is not main})
    return duplicates
