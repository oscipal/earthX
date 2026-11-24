"""Dedupe: one main entry per dataset across sources (M5-20 plan §8, §13b; F4 = 1).

Keys are exact, never fuzzy, and never the page of a dataset at its provider (Otto's measurement M6: shared pages are
collection pages within one source, never the same dataset across sources):

* ``doi:`` the DOI;
* ``id:`` the DCAT identifier of the dataset;
* ``coll:<host>/<id>`` a STAC collection: its own id for a find of a STAC source or a full entry, and for any other
  find the id of a collection that stands as a whole token in its identifier or in the page of the dataset itself
  (opendata.swiss names the FSDI collections it lists, M7). Only ids with two dots or more are looked for
  (``ch.swisstopo.x``): a short id such as ``sentinel-2-l2a`` is too common a word. A find that names several
  collections there gets none. A collection id in a distribution or in a reference is no key (Otto, 23.11.2026: a
  GovData find linking to a collection of the FSDI is not that collection), but for a source that says so
  (``dedupe_collection_links``, opendata.swiss; Otto, 24.11.2026) a viewer link of the FSDI in its files, its link
  candidates or its skipped page counts too: ``map.geo.admin.ch`` with ``layers=`` and ``data.geo.admin.ch`` with
  ``/collections/<id>``, and only where all addresses together name exactly one known collection.

A DOI or identifier is a key only where it is unique (Otto, 23.11.2026): on at most one find of each source and on at
most :data:`MAX_SHARED` finds in all. Two finds of one source with the same DOI or identifier are two datasets that
share a placeholder of their portal, not one dataset twice.

A find is a duplicate only of a main entry it shares a key with itself, never through a chain of other finds (Otto,
23.11.2026: a chain joined datasets that share no key). The finds are taken by rank (full entry, hand entry, then the
source's ``dedupe_rank``, the rank of the link "Source", a footprint, the source and the key); each one not yet placed
becomes a main entry and takes every unplaced find that shares one of its keys. Pure: no database, no request.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "MAX_SHARED",
    "Member",
    "collection_tokens",
    "find_keys",
    "linked_collections",
    "main_entries",
    "namespaced",
    "shared_key",
]

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


_VIEWER_LINK = re.compile(r"https://(?P<host>map|data)\.geo\.admin\.ch(?::443)?(?:[/?#]|$)", re.IGNORECASE)
_LAYERS = re.compile(r"[?&]layers=([^&#]*)", re.IGNORECASE)
_COLLECTION_PATH = re.compile(r"/collections/([^/?#&]+)", re.IGNORECASE)
#: The two escapes that matter in a ``layers=`` value: the comma between layers and the ``@`` before a parameter.
_ESCAPES = re.compile(r"%(2c|40)", re.IGNORECASE)


def linked_collections(addresses: Iterable[str], known: Mapping[str, str]) -> set[str]:
    """The keys of the known collections a viewer link of the FSDI among ``addresses`` names: the ids of ``layers=`` at
    ``map.geo.admin.ch`` (comma separated, a ``@parameter`` of a layer dropped) and the id after ``/collections/`` at
    ``data.geo.admin.ch``. Any other address names none."""
    found: set[str] = set()
    for address in addresses:
        match = _VIEWER_LINK.match(address)
        if match is None:
            continue
        values = _LAYERS.findall(address) if match["host"].lower() == "map" else _COLLECTION_PATH.findall(address)
        for value in values:
            for part in _ESCAPES.sub(lambda m: "," if m[1].lower() == "2c" else "@", value).split(","):
                token = part.split("@", 1)[0].strip().lower()
                host = known.get(token)
                if host is not None:
                    found.add(f"coll:{host}/{token}")
    return found


def _linked_addresses(found: Mapping[str, Any]) -> list[str]:
    """The addresses of a find that are no page of the dataset itself: its files, its link candidates (pairs of rank and
    address) and the page the link "Source" skipped."""
    addresses = [d.get("href") for d in found.get("distributions") or () if isinstance(d, dict)]
    addresses += [c[1] for c in found.get("link_candidates") or () if isinstance(c, (list, tuple)) and len(c) == 2]
    addresses.append(found.get("skipped_url"))
    return [a for a in addresses if isinstance(a, str)]


def namespaced(collection_id: str) -> bool:
    """Whether an id is long enough to be looked for in the addresses of other finds."""
    return _NAMESPACED.fullmatch(collection_id.lower()) is not None


def find_keys(
    found: Mapping[str, Any], *, stac_host: str | None, known: Mapping[str, str], collection_links: bool = False
) -> tuple[str, ...]:
    """The dedupe keys of an intermediate form; ``stac_host`` is the host of a STAC source, ``None`` otherwise.
    ``collection_links`` is the switch of the source (``dedupe_collection_links``)."""
    keys: set[str] = set()
    doi = found.get("doi")
    if isinstance(doi, str) and doi.strip():
        keys.add(f"doi:{doi.strip().lower()}")
    identifier = found.get("identifier")
    if isinstance(identifier, str) and identifier.strip():
        keys.add(f"id:{identifier.strip()}")
    if stac_host is not None:
        keys.add(f"coll:{stac_host}/{str(found['source_key']).lower()}")
    else:
        addresses = [found.get("identifier"), found.get("source_url"), found.get("landing_url")]
        tokens = collection_tokens((a for a in addresses if isinstance(a, str)), known)
        if collection_links:
            tokens |= linked_collections(_linked_addresses(found), known)
        if len(tokens) == 1:
            keys |= tokens
    return tuple(sorted(keys))


@dataclass(frozen=True, slots=True)
class Member:
    """One entry that takes part in dedupe; ``rank`` orders the entries (the smallest is a main entry first).
    ``source`` is the source of a harvested find, ``None`` for a full or hand entry."""

    dataset_id: str
    keys: tuple[str, ...]
    rank: tuple[Any, ...]
    source: str | None = None


#: A DOI or identifier on more finds than this is a placeholder of a portal ("1", the portal's address), no key: a
#: wrong group hides real datasets, which weighs more than a missed one (review M5-20 PR 1).
MAX_SHARED = 5


def _usable(members: list[Member]) -> set[str]:
    """The keys that are unique: a collection id always; a DOI or identifier on at most one find of each source and on
    at most :data:`MAX_SHARED` finds in all."""
    total: dict[str, int] = {}
    per_source: dict[tuple[str | None, str], int] = {}
    for member in members:
        for key in member.keys:
            total[key] = total.get(key, 0) + 1
            if member.source is not None:
                per_source[(member.source, key)] = per_source.get((member.source, key), 0) + 1
    repeated = {key for (_source, key), count in per_source.items() if count > 1}
    return {k for k, n in total.items() if k.startswith("coll:") or (n <= MAX_SHARED and k not in repeated)}


def main_entries(members: Iterable[Member]) -> dict[str, str]:
    """For every member that is not a main entry, the id of the main entry it shares a key with."""
    members = list(members)
    usable = _usable(members)
    by_key: dict[str, list[Member]] = {}
    for member in members:
        for key in member.keys:
            if key in usable:
                by_key.setdefault(key, []).append(member)
    placed: set[str] = set()
    duplicates: dict[str, str] = {}
    for main in sorted(members, key=lambda m: (m.rank, m.dataset_id)):
        if main.dataset_id in placed:
            continue
        placed.add(main.dataset_id)
        for key in main.keys:
            for other in by_key.get(key, ()):
                if other.dataset_id not in placed:
                    placed.add(other.dataset_id)
                    duplicates[other.dataset_id] = main.dataset_id
    return duplicates


def shared_key(duplicate: Iterable[str], main: Iterable[str]) -> str | None:
    """The first key a duplicate and its main entry share, for the report; ``None`` where they share none."""
    common = sorted(set(duplicate) & set(main))
    return common[0] if common else None
