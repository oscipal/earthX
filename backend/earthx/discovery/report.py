"""The report of a harvested source: derive, dedupe, stack, approval file (M5-20 plan §5, §12; adr/0033 §8).

    python -m earthx.discovery.report <source_id> [--classify] [--out DIR]

Asks no source. For every find the harvest extracted it derives a row of ``earthx_listed_entry``: the blocklist, the
extent (``enrich``), the rule R-G (``geodata``), the licence rule (``catalog.licences``) and the keys of dedupe. Then
it settles finds that went away, finds the main entry of every group of duplicates across all sources, and forms the
stack of the source: every row in review. Where the stack is new it writes the report and the approval file with
``decision: pending`` into ``--out`` (``backend/catalog/approvals`` of the checkout, mounted by the script); Otto
checks the sample and merges, ``catalog-load`` publishes. Nothing becomes visible here.

``--classify`` writes nothing: it shows what the rule R-G, the directory of places and the licence rules make of the
source, with two samples for the release of the rule (plan §7, §13b).

The output names titles, links and publishers (public metadata of the catalogue), never a person or an area of a user.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import cache
from pathlib import Path
from typing import Any

import psycopg

from earthx.catalog import collection as collection_module
from earthx.catalog import licences as licences_module
from earthx.catalog import listed as listed_module
from earthx.catalog.approvals import next_file_stem
from earthx.catalog.collection import SCIENTIFIC_EXTENSION, STAC_VERSION
from earthx.catalog.datasets import CATALOG_DIR, registry
from earthx.catalog.entry_files import EntryFileError, dump_yaml
from earthx.catalog.licences import LicenceCatalogue, LicenceMatch, load_licences, normal_statement
from earthx.catalog.listed import HAND_SOURCE, BlockRule, content_sha256, link_host, load_blocked, sort_title
from earthx.catalog.listed_store import apply_blocklist, is_blocked
from earthx.catalog.listing_store import (
    HarvestedRow,
    Stack,
    apply_duplicates,
    dedupe_rows,
    derivations,
    form_stack,
    settle_missing,
    write_harvested,
)
from earthx.catalog.municipalities import MUNICIPALITIES_FILE
from earthx.catalog.registry import ConfigError, LicenseInfo, doi_name
from earthx.catalog.sources import MAX_DEDUPE_RANK, SourceConfig, SourceProtocol, read_sources
from earthx.discovery import dedupe, enrich, geodata
from earthx.discovery.dedupe import Member, find_keys, main_entries, namespaced, shared_key, with_listings
from earthx.discovery.enrich import (
    PLACE_NAMES_FILE,
    Extent,
    PlaceDirectory,
    box_of_codes,
    geonames_ids,
    load_place_directory,
    spatial_extent,
    time_span,
)
from earthx.discovery.extract import resource_kind
from earthx.discovery.flags import Flag, FlagEntry, flags_of, load_flag_rules
from earthx.discovery.geodata import GEODATA_FILE, Classified, GeodataRule, classify, load_geodata_rule
from earthx.discovery.links import api_pattern
from earthx.logging import configure_logging

__all__ = ["Derived", "ReportResult", "derive", "main", "run_report"]

#: The size of each sample (adr/0033 §8.2, N2: 15 at random, 15 aimed; plan §7: 15 hidden; §13b: 20 pairs).
SAMPLE_RANDOM = 15
SAMPLE_AIMED = 15
SAMPLE_HIDDEN = 15
SAMPLE_PAIRS = 20
#: The size of each sample of ``--classify`` (plan §7: two samples of 30).
CLASSIFY_SAMPLE = 30
_BATCH = 500
_WORLD = (-180.0, -90.0, 180.0, 90.0)


@dataclass(frozen=True, slots=True)
class Derived:
    """What the report makes of one find: the row and the steps that decided it."""

    row: HarvestedRow
    extent: Extent
    classified: Classified
    licence: LicenceMatch
    statements: tuple[str, ...]


def dataset_id(source_id: str, key: str) -> str:
    """The id of a harvested entry (plan A1): ``<source>.<key>`` where the key fits an id, else a hash of it."""
    candidate = f"{source_id}.{key}"
    if len(candidate) <= 128 and all(c in "abcdefghijklmnopqrstuvwxyz0123456789._-" for c in key) and key:
        return candidate
    return f"{source_id}.h{hashlib.sha256(key.encode('utf-8')).hexdigest()[:20]}"


def _span_literal(span: tuple[datetime | None, datetime | None] | None) -> str | None:
    if span is None:
        return None
    start, end = span
    return f"[{'' if start is None else start.isoformat()},{'' if end is None else end.isoformat()}]"


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat().replace("+00:00", "Z")


def _box_geojson(box: Sequence[float]) -> dict[str, Any]:
    """A box as a GeoJSON polygon, cut in two where it crosses the antimeridian (east below west)."""
    west, south, east, north = box

    def ring(w: float, e: float) -> list[list[list[float]]]:
        return [[[w, south], [e, south], [e, north], [w, north], [w, south]]]

    if east >= west:
        return {"type": "Polygon", "coordinates": ring(west, east)}
    return {"type": "MultiPolygon", "coordinates": [ring(west, 180.0), ring(-180.0, east)]}


def _licence_block(licence: LicenseInfo | None, publisher: str | None) -> dict[str, Any] | None:
    if licence is None:
        return None
    name = publisher or ""
    return {
        "spdx_id": licence.spdx_id,
        "name": licence.name,
        "url": licence.url,
        "commercial_use": licence.commercial_use,
        "distribution": licence.distribution,
        "derivatives": licence.derivatives,
        "share_alike": licence.share_alike,
        "attribution_required": licence.attribution_required,
        # A listed entry is always in the catalogue tier (adr/0033 §6.2).
        "tier": "catalog",
        "attribution_modified": None
        if licence.attribution_modified is None
        else licence.attribution_modified.replace("{publisher}", name),
        "attribution_unmodified": None
        if licence.attribution_unmodified is None
        else licence.attribution_unmodified.replace("{publisher}", name),
        "terms_url": None if licence.terms is None else licence.terms.url,
        "terms_notice": None if licence.terms is None else dict(licence.terms.notice),
    }


def _collection(
    found: Mapping[str, Any],
    source: SourceConfig,
    entry_id: str,
    extent: Extent,
    span: tuple[datetime | None, datetime | None] | None,
    licence: LicenceMatch,
) -> dict[str, Any]:
    """The STAC Collection of a harvested entry, in the form of a hand entry (``listed.to_listed_collection``)."""
    publisher = found.get("publisher")
    try:
        doi = doi_name(found.get("doi")) if isinstance(found.get("doi"), str) else None
    except ConfigError:
        # "N/A" or "DOI: 10…" in a STAC sci:doi: no DOI rather than no entry.
        doi = None
    if extent.basis in ("source", "place") and extent.bbox is not None:
        box: Sequence[float] = extent.bbox
    else:
        box = box_of_codes(extent.codes) or _WORLD
    links: list[dict[str, str]] = [{"rel": "via", "href": found["source_url"], "title": "Source"}]
    if licence.license is not None:
        links.append({"rel": "license", "href": licence.license.url, "title": licence.license.name})
    if doi:
        links.append({"rel": "cite-as", "href": f"https://doi.org/{doi}"})
    collection: dict[str, Any] = {
        "type": "Collection",
        "stac_version": STAC_VERSION,
        "stac_extensions": [SCIENTIFIC_EXTENSION] if doi else [],
        "id": entry_id,
        "title": found["title"],
        "description": found.get("description") or found["title"],
        "keywords": list(found.get("keywords") or ()),
        "license": "other"
        if licence.license is None
        else (licence.license.spdx_id or ("proprietary" if STAC_VERSION.startswith("1.0") else "other")),
        "providers": [] if not publisher else [{"name": publisher, "roles": ["licensor"]}],
        "extent": {
            "spatial": {"bbox": [list(box)]},
            "temporal": {"interval": [[_iso(span[0]), _iso(span[1])] if span else [None, None]]},
        },
        "links": links,
        "earthx:entry": "listed",
        "earthx:data_kind": found["data_kind"],
        "earthx:coverage_states": None,
        "earthx:category": found["category"],
        "earthx:license_flags": _licence_block(licence.license, publisher),
        "earthx:legal_status": "cleared" if licence.license is not None else None,
        "earthx:legal_note": None,
        "earthx:access": {"account": found.get("account"), "account_provider": None, "delivery": found.get("delivery")},
        "earthx:listing": {
            "source_url": found["source_url"],
            "publisher": publisher,
            "approved_on": None,
            "source_id": source.source_id,
            "source_key": found["source_key"],
            "source_rank": found.get("source_rank"),
            "license_rule": licence.rule,
        },
        # Where the extent comes from (plan §6.1, A7): only source and place stand for a footprint.
        "earthx:extent_basis": extent.basis,
        "earthx:distributions": [
            {key: d.get(key) for key in ("href", "format", "media_type", "title")}
            for d in found.get("distributions") or ()
            if isinstance(d, dict)
        ],
        "earthx:maturity": source.maturity.value,
    }
    if doi:
        collection["sci:doi"] = doi
    return collection


def _file_sha(path: Path) -> bytes:
    return hashlib.sha256(path.read_bytes() if path.exists() else b"").digest()


@cache
def _code_fingerprint() -> bytes:
    """The code and the rule files a row is derived with: a change re-derives every find (plan §5)."""
    digest = hashlib.sha256()
    for module in (enrich, geodata, dedupe, licences_module, listed_module, collection_module):
        digest.update(Path(module.__file__).read_bytes())  # type: ignore[arg-type]
    digest.update(Path(__file__).read_bytes())
    for path in (PLACE_NAMES_FILE, GEODATA_FILE, CATALOG_DIR / "regions.json", MUNICIPALITIES_FILE):
        digest.update(_file_sha(path))
    return digest.digest()


def derivation_version(source: SourceConfig, known: Mapping[str, str], licences: LicenceCatalogue | None) -> str:
    digest = hashlib.sha256(_code_fingerprint())
    digest.update(b"" if licences is None else licences.fingerprint.encode())
    digest.update(
        json.dumps(
            [source.country, source.maturity.value, source.dedupe_collection_links, sorted(known.items())]
        ).encode()
    )
    return digest.hexdigest()


def derive(
    found: Mapping[str, Any],
    extracted_sha256: str,
    source: SourceConfig,
    *,
    directory: PlaceDirectory,
    rule: GeodataRule,
    licences: LicenceCatalogue,
    known: Mapping[str, str],
    version: str,
) -> Derived:
    """The row of one extracted find (plan §5): extent, R-G, licence, dedupe keys; pure."""
    key = found["source_key"]
    entry_id = dataset_id(source.source_id, key)
    extent = spatial_extent(found, country=source.country, directory=directory)
    classified = classify(found, extent, country=source.country, rule=rule)
    statements = tuple(s for s in found.get("licence_statements") or () if isinstance(s, str))
    licence = licences.match(source.source_id, found.get("publisher"), statements)
    if classified.hidden:
        verdict, waiting = "not_geodata", None
    elif found.get("account") is None or found.get("delivery") is None:
        # M5-19 §5.2: the source names no way to get the data; never guessed.
        verdict, waiting = "needs_rule", "no_access"
    elif licence.reason is not None:
        verdict, waiting = "needs_rule", licence.reason
    else:
        verdict, waiting = "ok", None
    span = time_span(found.get("temporal"))
    content = _collection(found, source, entry_id, extent, span, licence)
    stac_host = source.host if source.protocol is SourceProtocol.STAC_API else None
    footprint = None
    if extent.basis == "source" and extent.bbox is not None:
        footprint = dict(extent.geometry) if isinstance(extent.geometry, Mapping) else _box_geojson(extent.bbox)
    row = HarvestedRow(
        dataset_id=entry_id,
        source_id=source.source_id,
        source_key=key,
        verdict=verdict,
        waiting_reason=waiting,
        content=content,
        content_sha256=content_sha256(content),
        sort_title=sort_title(found["title"]),
        footprint=footprint,
        footprint_codes=extent.places if extent.basis == "place" else None,
        regions=None if extent.basis == "source" else extent.codes,
        time_span=_span_literal(span),
        keywords=tuple(found.get("keywords") or ()) or ("other",),
        data_kind=found["data_kind"],
        category=found["category"],
        account=found.get("account"),
        delivery=found.get("delivery"),
        publisher=found.get("publisher"),
        link_host=link_host(found["source_url"]),
        license_ref=None if not licence.refs or licence.reason else "+".join(licence.refs),
        license_rule=licence.rule,
        extent_basis=extent.basis,
        dedupe_keys=find_keys(
            found, stac_host=stac_host, known=known, collection_links=source.dedupe_collection_links
        ),
        derived_sha256=hashlib.sha256(f"{extracted_sha256} {version}".encode()).hexdigest(),
    )
    return Derived(row, extent, classified, licence, statements)


def known_collections(conn: psycopg.Connection, sources: Mapping[str, SourceConfig]) -> dict[str, str]:
    """Namespaced collection ids (id → host) of the STAC sources and of the full entries (plan §8, §13b)."""
    known: dict[str, str] = {}
    stac = {s.source_id: s.host for s in sources.values() if s.protocol is SourceProtocol.STAC_API}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT source_id, source_key FROM public.earthx_record_state WHERE state = 'extracted'"
            " AND source_id = ANY(%s)",
            (list(stac),),
        )
        for source_id, key in cur.fetchall():
            if namespaced(key):
                known[key.lower()] = stac[source_id]
    for _config, host, collection_id in _full_collections():
        if namespaced(collection_id):
            known.setdefault(collection_id.lower(), host)
    return known


def _full_collections() -> list[tuple[Any, str, str]]:
    found = []
    for config in registry():
        source = config.source
        collection_id = getattr(source, "source_collection_id", None)
        endpoint = getattr(source, "endpoint", None)
        if collection_id and endpoint:
            found.append((config, endpoint.split("://", 1)[1].split("/", 1)[0].lower(), collection_id))
    return found


def _full_members() -> list[Member]:
    members = []
    listings = _listings()
    by_id = {config.dataset_id: config for config in registry()}
    collections = {config.dataset_id: (host, cid) for config, host, cid in _full_collections()}
    for dataset, config in by_id.items():
        keys = set()
        if dataset in collections:
            keys.add(f"coll:{collections[dataset][0]}/{collections[dataset][1]}")
        name = doi_name(config.doi)
        if name:
            keys.add(f"doi:{name.lower()}")
        keys.update(f"also:{listing}" for listing, owner in listings.items() if owner == dataset)
        if keys:
            members.append(Member(dataset, tuple(sorted(keys)), (0,)))
    return members


def _listings() -> Mapping[str, str]:
    """The listings of full entries in harvested catalogues, ``<source id>:<identifier>`` → dataset id."""
    return registry().listings


def _rank(source: SourceConfig | None, source_id: str, source_rank: int | None, footprint: bool) -> tuple[Any, ...]:
    """The rank of a harvested find among duplicates; a source no longer in sources/ ranks last."""
    dedupe_rank = MAX_DEDUPE_RANK + 1 if source is None else source.dedupe_rank
    return (2, dedupe_rank, source_rank or 9, not footprint, source_id)


def _members(conn: psycopg.Connection, sources: Mapping[str, SourceConfig], skip: str | None = None) -> list[Member]:
    """The full entries and the rows of the database (but those of the source ``skip``) as members of the groups."""
    members = _full_members()
    listings = _listings()
    for row in dedupe_rows(conn):
        if row.source_id == skip:
            continue
        if row.source_id == HAND_SOURCE:
            rank: tuple[Any, ...] = (1,)
        else:
            rank = _rank(sources.get(row.source_id), row.source_id, row.source_rank, row.footprint)
        members.append(Member(row.dataset_id, with_listings(row.source_id, row.keys, listings), rank, row.source_id))
    return members


def _dedupe(conn: psycopg.Connection, sources: Mapping[str, SourceConfig]) -> dict[str, str]:
    return main_entries(_members(conn, sources))


#: What ``--classify`` knows of a find to place it among the duplicates: its member and its title.
@dataclass(frozen=True, slots=True)
class DedupeFind:
    member: Member
    title: str
    verdict: str


@dataclass(frozen=True, slots=True)
class TitleMatch:
    """A listed find whose title is that of a full entry (Otto, 24.11.2026): a candidate for ``also_listed_as``, only
    ever proposed. ``key`` is ``<source id>:<identifier>`` as the field wants it, ``None`` for a find without one."""

    find_id: str
    find_title: str
    full_id: str
    full_title: str
    source_id: str
    publisher: str
    key: str | None


def title_key(title: str) -> str:
    """A title as it is compared with the titles of the full entries: lower case, every run of other characters one blank."""
    return re.sub(r"[\W_]+", " ", title.casefold()).strip()


def _full_titles() -> dict[str, list[tuple[str, str]]]:
    titles: dict[str, list[tuple[str, str]]] = {}
    for config in registry():
        titles.setdefault(title_key(config.title), []).append((config.dataset_id, config.title))
    return titles


#: A duplicate, its main entry and the key they share.
Pair = tuple[str, str, str]
_NO_KEY = "voller oder Handeintrag"
_KEY_KINDS = {"doi": "DOI", "id": "Kennung", "coll": "Collection-ID"}


@dataclass(frozen=True, slots=True)
class DedupeCompare:
    """The pairs that touch a source, as the database holds them (the last real report) and as the keys of this
    derivation would make them (Otto, 23.11.2026), the rows of the source by state, and examples with titles."""

    before: tuple[Pair, ...]
    now: tuple[Pair, ...]
    lost: tuple[Pair, ...]
    new: tuple[Pair, ...]
    #: Finds with the verdict ``ok`` that would go as duplicates.
    ok_duplicates: int
    states: Mapping[str, int]
    #: Examples of the pairs now and of the lost ones, each as (title of the duplicate, its id, title of the main entry,
    #: its id, key).
    examples_now: tuple[tuple[str, str, str, str, str], ...]
    examples_lost: tuple[tuple[str, str, str, str, str], ...]
    examples_new: tuple[tuple[str, str, str, str, str], ...]


def _pairs_of(members: Sequence[Member], own: set[str]) -> tuple[Pair, ...]:
    keys = {member.dataset_id: member.keys for member in members}
    pairs = [
        (duplicate, main, shared_key(keys[duplicate], keys[main]) or _NO_KEY)
        for duplicate, main in main_entries(members).items()
        if duplicate in own or main in own
    ]
    return tuple(sorted(pairs))


def _titled(
    conn: psycopg.Connection, known: Mapping[str, str], pairs: Sequence[Pair]
) -> tuple[tuple[str, str, str, str, str], ...]:
    """``pairs`` with the titles of both sides: those ``known``, else the listed entry's (a full entry has none: its id)."""
    titles = dict(known)
    missing = sorted({i for d, m, _ in pairs for i in (d, m) if i not in titles})
    if missing:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT dataset_id, content->>'title' FROM public.earthx_listed_entry WHERE dataset_id = ANY(%s)",
                (missing,),
            )
            titles.update({dataset_id: title for dataset_id, title in cur.fetchall() if title})
    return tuple((titles.get(d, d), d, titles.get(m, m), m, key) for d, m, key in pairs)


def _stored_pairs(conn: psycopg.Connection, source_id: str) -> tuple[Pair, ...]:
    """The duplicates the database holds (the last real report, ``catalog-load``) that touch the source, with the key
    their rows share; a full entry carries the keys of the registry."""
    full = {member.dataset_id: member.keys for member in _full_members()}
    listings = _listings()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT d.dataset_id, d.duplicate_of, d.source_id, coalesce(d.dedupe_keys, '{}'),"
            " coalesce(m.dedupe_keys, '{}') FROM public.earthx_listed_entry d"
            " LEFT JOIN public.earthx_listed_entry m ON m.dataset_id = d.duplicate_of"
            " WHERE d.state = 'duplicate' AND (d.source_id = %s OR m.source_id = %s)",
            (source_id, source_id),
        )
        rows = cur.fetchall()
    pairs = [
        (
            duplicate,
            main,
            shared_key(with_listings(duplicate_source, duplicate_keys, listings), full.get(main) or main_keys)
            or _NO_KEY,
        )
        for duplicate, main, duplicate_source, duplicate_keys, main_keys in rows
    ]
    return tuple(sorted(pairs))


def compare_duplicates(
    conn: psycopg.Connection,
    sources: Mapping[str, SourceConfig],
    source_id: str,
    finds: Sequence[DedupeFind],
    seed: str,
) -> DedupeCompare:
    """The pairs of ``source_id`` before (the keys in the database) and now (``finds`` derived anew); writes nothing.
    The ten examples of each are drawn with ``seed``."""
    own = {row.dataset_id for row in dedupe_rows(conn) if row.source_id == source_id}
    own |= {f.member.dataset_id for f in finds}
    before = _stored_pairs(conn, source_id)
    now = _pairs_of([*_members(conn, sources, skip=source_id), *(f.member for f in finds)], own)
    before_pairs, now_pairs = {(d, m) for d, m, _ in before}, {(d, m) for d, m, _ in now}
    # A pair that only changed its key (the main entry stays) is the same pair.
    lost = tuple(pair for pair in before if pair[:2] not in now_pairs)
    new = tuple(pair for pair in now if pair[:2] not in before_pairs)
    verdicts = {f.member.dataset_id: f.verdict for f in finds}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT state, count(*) FROM public.earthx_listed_entry WHERE source_id = %s GROUP BY 1", (source_id,)
        )
        states = dict(cur.fetchall())
    titles = {f.member.dataset_id: f.title for f in finds}
    return DedupeCompare(
        before=before,
        now=now,
        lost=lost,
        new=new,
        ok_duplicates=sum(1 for duplicate, _main, _key in now if verdicts.get(duplicate) == "ok"),
        states=states,
        examples_now=_titled(conn, titles, _sample(now, 10, seed)),
        examples_lost=_titled(conn, titles, _sample(lost, 10, seed)),
        examples_new=_titled(conn, titles, _sample(new, 10, seed)),
    )


@dataclass
class ReportResult:
    """The counts of one report and what it wrote."""

    source_id: str
    finds: int = 0
    written: int = 0
    blocked: int = 0
    verdicts: Counter[str] = field(default_factory=Counter)
    waiting: Counter[str] = field(default_factory=Counter)
    bases: Counter[str] = field(default_factory=Counter)
    signals: Counter[str] = field(default_factory=Counter)
    unresolved: Counter[str] = field(default_factory=Counter)
    #: GeoNames ids of place texts the table of place_names.yaml does not hold yet (F10 = 1).
    geonames: Counter[str] = field(default_factory=Counter)
    #: Bare names that are a city and its canton, by what the publisher decided ("zug: Kanton"), plan §13d.
    choices: Counter[str] = field(default_factory=Counter)
    #: Why a find has no known way to the data (``no_access``), and the finds by reason (plan §13d, Otto's point 4).
    access_reasons: Counter[str] = field(default_factory=Counter)
    no_access: list[tuple[str, str, str, str]] = field(default_factory=list)
    #: Every licence statement (normal form) of the source's finds, with its publishers, for Otto's grading (point 7).
    statements: dict[str, Counter[str]] = field(default_factory=dict)
    pairs: Counter[tuple[str, str]] = field(default_factory=Counter)
    hidden: list[tuple[str, str, str]] = field(default_factory=list)
    undecided: list[tuple[str, str, str]] = field(default_factory=list)
    #: Links "Source" that fell to another rank because the better one was a collective page (Otto, 21.11.2026), by
    #: the move ("1 → 2"), and each as (title, skipped address, its rank, link now, its rank).
    link_moves: Counter[str] = field(default_factory=Counter)
    link_examples: list[tuple[str, str, int, str, int]] = field(default_factory=list)
    #: Links "Source" that look like a machine interface (Otto, 23.11.2026), by pattern, and each as (pattern, title, link).
    api_links: Counter[str] = field(default_factory=Counter)
    api_examples: list[tuple[str, str, str]] = field(default_factory=list)
    #: Finds hidden as no geodata by publisher, without and with the rule on weak geo signals (Otto, 23.11.2026), and
    #: the weak signals that no longer keep a find.
    hidden_before: Counter[str] = field(default_factory=Counter)
    hidden_after: Counter[str] = field(default_factory=Counter)
    overruled_signals: Counter[str] = field(default_factory=Counter)
    deleted: int = 0
    missing: int = 0
    tombstones: int = 0
    duplicates: tuple[int, int] = (0, 0)
    #: ``--classify`` only: the pairs before and now (:func:`compare_duplicates`), the texts of the examples.
    dedupe: DedupeCompare | None = None
    #: Listed finds with the title of a full entry that are not its duplicates (proposals for ``also_listed_as``).
    title_candidates: tuple[TitleMatch, ...] = ()
    stack: Stack | None = None
    files: tuple[Path, ...] = ()
    #: Finds that could not be derived or that Postgres refused: counted, never the reason of a stop.
    failed: int = 0


def _stream(conn: psycopg.Connection, source_id: str):  # type: ignore[no-untyped-def]
    with conn.cursor(name="earthx_report", withhold=True) as cur:
        cur.execute(
            "SELECT source_key, extracted, extracted_sha256 FROM public.earthx_record_state"
            " WHERE source_id = %s AND state = 'extracted' ORDER BY source_key",
            (source_id,),
        )
        yield from cur


def _check_municipalities(conn: psycopg.Connection, directory: PlaceDirectory) -> None:
    """The footprint of a municipality comes from ``earthx_municipality``: every municipality the directory knows must
    be there, or the row of a find naming it would have no footprint. ``catalog-load`` writes them."""
    codes = list(directory.municipal_boxes)
    if not codes:
        return
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM public.earthx_municipality WHERE code = ANY(%s)", (codes,))
        row = cur.fetchone()
    if row is None or row[0] != len(codes):
        raise ConfigError(
            "earthx_municipality does not hold the municipalities of municipalities.json; run catalog-load first"
            " (docker compose up -d)"
        )


def _blocked(rules: Sequence[BlockRule], source_id: str, found: Mapping[str, Any]) -> bool:
    try:
        host = link_host(found["source_url"])
    except ConfigError:
        host = ""
    values = {"source_id": source_id, "source_key": found["source_key"], "publisher": found.get("publisher") or ""}
    return any(is_blocked(rule, host=host, **values) for rule in rules)


def run_report(
    conn: psycopg.Connection,
    source: SourceConfig,
    *,
    sources: Mapping[str, SourceConfig],
    licences: LicenceCatalogue,
    blocklist: Sequence[BlockRule],
    classify_only: bool = False,
    directory: PlaceDirectory | None = None,
    rule: GeodataRule | None = None,
) -> ReportResult:
    """One report of ``source`` against ``conn`` (autocommit); with ``classify_only`` nothing is written."""
    directory = load_place_directory() if directory is None else directory
    rule = load_geodata_rule() if rule is None else rule
    _check_municipalities(conn, directory)
    known = known_collections(conn, sources)
    version = derivation_version(source, known, licences)
    stored = {} if classify_only else derivations(conn, source.source_id)
    result = ReportResult(source.source_id)
    blocked_keys: list[str] = []
    batch: list[HarvestedRow] = []
    placed: list[DedupeFind] = []
    full_titles = _full_titles()
    matches: list[TitleMatch] = []

    def flush() -> None:
        with conn.transaction(), conn.cursor() as cur:
            written, refused = write_harvested(cur, batch)
        result.written += written
        result.failed += len(refused)
        batch.clear()

    for key, found, extracted_sha in _stream(conn, source.source_id):
        result.finds += 1
        if _blocked(blocklist, source.source_id, found):
            result.blocked += 1
            blocked_keys.append(key)
            continue
        try:
            derived = derive(
                found, extracted_sha, source, directory=directory, rule=rule, licences=licences, known=known,
                version=version,
            )
        except (ConfigError, ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
            # One find of a foreign shape must not stop the report of every other one; its row stays as it was.
            result.failed += 1
            continue
        _count(result, derived, found, licences)
        if not derived.classified.hidden:
            identifier = found.get("identifier")
            listing = f"{source.source_id}:{identifier}" if isinstance(identifier, str) and identifier.strip() else None
            matches += [
                TitleMatch(
                    derived.row.dataset_id,
                    str(found.get("title"))[:120],
                    full_id,
                    full_title,
                    source.source_id,
                    derived.row.publisher or "–",
                    listing,
                )
                for full_id, full_title in full_titles.get(title_key(str(found.get("title"))), ())
            ]
        if classify_only and not derived.classified.hidden:
            rank = _rank(source, source.source_id, int(found.get("source_rank") or 0), derived.row.footprint is not None)
            keys = with_listings(source.source_id, derived.row.dedupe_keys, _listings())
            member = Member(derived.row.dataset_id, keys, rank, source.source_id)
            placed.append(DedupeFind(member, str(found.get("title"))[:120], derived.row.verdict))
        if not classify_only and stored.get(key) != derived.row.derived_sha256:
            batch.append(derived.row)
            if len(batch) >= _BATCH:
                flush()
    if classify_only:
        result.dedupe = compare_duplicates(conn, sources, source.source_id, placed, classify_seed(source))
        result.title_candidates = _candidates(matches, {d: m for d, m, _ in result.dedupe.now})
        return result
    if batch:
        flush()
    with conn.transaction():
        missing = settle_missing(conn, source.source_id, blocked_keys)
        result.deleted, result.missing, result.tombstones = missing.deleted, missing.marked, missing.tombstones
        apply_blocklist(conn, blocklist)
    with conn.transaction():
        duplicates = _dedupe(conn, sources)
        result.duplicates = apply_duplicates(conn, duplicates)
    result.title_candidates = _candidates(matches, duplicates)
    with conn.transaction():
        result.stack = form_stack(conn, source.source_id)
    return result


def _candidates(matches: Sequence[TitleMatch], duplicates: Mapping[str, str]) -> tuple[TitleMatch, ...]:
    """The finds with a full entry's title that are not yet its duplicates, sorted."""
    return tuple(sorted((m for m in matches if duplicates.get(m.find_id) != m.full_id), key=lambda m: (m.full_id, m.find_id)))


def candidate_lines(candidates: Sequence[TitleMatch], limit: int = 50) -> list[str]:
    """The proposals for ``also_listed_as``: full entry, find, source, publisher and the key to write."""
    lines = [
        f"  - {m.full_id} „{m.full_title}“ | {m.find_id} „{m.find_title}“ | {m.source_id} | {m.publisher[:80]}"
        f" | {m.key or '(Fund ohne Kennung)'}"
        for m in candidates[:limit]
    ]
    if len(candidates) > limit:
        lines.append(f"  … und {len(candidates) - limit} weitere")
    return lines


def _count(result: ReportResult, derived: Derived, found: Mapping[str, Any], licences: LicenceCatalogue) -> None:
    row = derived.row
    result.verdicts[row.verdict] += 1
    result.bases[derived.extent.basis] += 1
    if row.waiting_reason:
        result.waiting[row.waiting_reason] += 1
    if derived.extent.unresolved:
        result.unresolved[derived.extent.unresolved[:80]] += 1
        for geonames_id in geonames_ids(derived.extent.unresolved):
            result.geonames[geonames_id] += 1
    if derived.extent.choice:
        result.choices[derived.extent.choice] += 1
    if row.waiting_reason == "no_access":
        reason, formats = access_reason(found)
        result.access_reasons[reason] += 1
        result.no_access.append((reason, str(found.get("title"))[:100], str(found.get("source_url")), formats))
    for signal in (*derived.classified.geo, *derived.classified.not_geo):
        # Signals are "kind:value" or a kind alone ("inspire").
        result.signals[signal[:60]] += 1
    for statement in {normal_statement(s) for s in derived.statements if normal_statement(s)}:
        result.statements.setdefault(statement, Counter())[row.publisher or "–"] += 1
    if row.waiting_reason == "unknown_licence":
        # Only the statements the catalogue does not know: a known one beside it is no reason to wait (Otto,
        # 23.11.2026: a publisher's pair showed what was granted, the cause was the identifier beside the address).
        for statement in {normal_statement(s) for s in derived.statements if normal_statement(s)}:
            if statement not in licences.by_statement and not licences.is_not_a_licence(statement):
                result.pairs[(row.publisher or "–", statement[:100])] += 1
    elif row.waiting_reason == "not_granted":
        result.pairs[(row.publisher or "–", _not_granted(licences, row.source_id, row.publisher, derived.licence.refs))] += 1
    skipped = found.get("skipped_url")
    if isinstance(skipped, str):
        was, now = int(found.get("skipped_rank") or 0), int(found.get("source_rank") or 0)
        result.link_moves[f"{was} → {now}"] += 1
        result.link_examples.append((str(found.get("title"))[:100], skipped, was, str(found.get("source_url")), now))
    if pattern := api_pattern(found.get("source_url")):
        result.api_links[pattern] += 1
        result.api_examples.append((pattern, str(found.get("title"))[:100], str(found.get("source_url"))))
    entry = (row.dataset_id, str(found.get("title"))[:120], str(found.get("source_url")))
    if derived.classified.outcome == "not_geodata":
        result.hidden.append(entry)
        result.hidden_after[row.publisher or "–"] += 1
        if derived.classified.weak_overruled:
            result.overruled_signals.update(signal.split(":", 1)[0] for signal in derived.classified.geo)
        else:
            result.hidden_before[row.publisher or "–"] += 1
    elif derived.classified.outcome == "undecided":
        result.undecided.append(entry)


def _not_granted(licences: LicenceCatalogue, source_id: str, publisher: str | None, refs: Sequence[str]) -> str:
    """Why a find waits as ``not_granted``, for the waiting list (Otto, 23.11.2026: a pair showed a granted licence):
    the publisher has no line in ``grants/``, or the licences of the find not granted to it."""
    granted = licences.grants.get(source_id, {}).get(publisher or "")
    if granted is None:
        return f"Herausgeber ohne Zeile in grants/{source_id}.yaml (Lizenzen: {', '.join(refs)})"
    return "nicht freigegeben: " + ", ".join(ref for ref in refs if ref not in granted)


def access_reason(found: Mapping[str, Any]) -> tuple[str, str]:
    """Why the extract found no way to the data of a find, from its intermediate form, and the formats of its files:
    the source restricts access (``access_rights`` not public), names no resource with a usable address, names only
    pages, or names formats the format table does not know. Resources with a plain ``http`` address are not kept in the
    intermediate form and so count as none."""
    distributions = [d for d in found.get("distributions") or () if isinstance(d, dict)]
    kinds = [resource_kind(d.get("format"), d.get("media_type")) for d in distributions]
    formats = ", ".join(sorted({str(d.get("format") or d.get("media_type") or "–") for d in distributions})) or "–"
    if found.get("delivery") is not None:
        return "access_rights eingeschränkt oder nicht öffentlich", formats
    if not distributions:
        return "keine Ressource mit https-Adresse", formats
    if all(kind == "page" for kind in kinds):
        return "nur Seiten (HTML)", formats
    if any(kind is None for kind in kinds):
        return "Format unbekannt", formats
    return "nur Dokumentation oder Sonstiges", formats


def _sample(items: Sequence[Any], size: int, seed: str) -> list[Any]:
    """``size`` items drawn with ``seed`` (the fingerprint of the stack, so the draw can be repeated, adr/0033 §8.2)."""
    if len(items) <= size:
        return list(items)
    return random.Random(seed).sample(list(items), size)


def _by_kind(pairs: Iterable[Pair]) -> str:
    counts = Counter(_KEY_KINDS.get(key.split(":", 1)[0], key) for _, _, key in pairs)
    return ", ".join(f"{kind} {counts[kind]}" for kind in (*_KEY_KINDS.values(), _NO_KEY) if counts[kind]) or "–"


def _dedupe_lines(compare: DedupeCompare | None) -> list[str]:
    """The section on duplicates of ``--classify`` (Otto, 23.11.2026): the pairs that touch the source, by kind of key,
    against the last real report, and examples; nothing is written."""
    if compare is None:
        return []
    states = ", ".join(f"{state} {count}" for state, count in sorted(compare.states.items())) or "–"
    lines = [
        "Dubletten (gerechnet mit den Schlüsseln dieser Ableitung; nichts geschrieben):",
        f"  Zeilen der Quelle in der Datenbank (letzter Bericht), nach Stand: {states}",
        f"  Paare jetzt {len(compare.now)} (nach Schlüsselart: {_by_kind(compare.now)}); davon Funde mit Ergebnis ok,"
        f" die als Dublette abgehen: {compare.ok_duplicates}",
        f"  Paare im Stand der Datenbank {len(compare.before)} (nach Schlüsselart: {_by_kind(compare.before)})",
        f"  Weggefallen {len(compare.lost)} (nach Schlüsselart: {_by_kind(compare.lost)}), neu {len(compare.new)}"
        f" (nach Schlüsselart: {_by_kind(compare.new)})",
    ]
    for name, examples in (
        ("jetzt", compare.examples_now),
        ("weggefallen", compare.examples_lost),
        ("neu", compare.examples_new),
    ):
        lines.append(f"  10 Beispiele {name} (Duplikat | Haupteintrag | Schlüssel):")
        lines += [f"  - {t} <{d}> | {mt} <{m}> | {key}" for t, d, mt, m, key in examples]
    return lines


def classify_seed(source: SourceConfig) -> str:
    return f"{source.source_id}:{derivation_version(source, {}, None)}"


def classify_text(source: SourceConfig, result: ReportResult) -> str:
    """The output of ``--classify``: counts and the two samples for the release of R-G (plan §7)."""
    seed = classify_seed(source)
    lines = [f"Einstufung {source.source_id} (nichts geschrieben): {result.finds} Funde, gesperrt {result.blocked}"]
    lines.append("Ergebnis: " + ", ".join(f"{k} {v}" for k, v in sorted(result.verdicts.items())))
    lines.append("Ausdehnung: " + ", ".join(f"{k} {v}" for k, v in sorted(result.bases.items())))
    lines.append("Warten: " + (", ".join(f"{k} {v}" for k, v in sorted(result.waiting.items())) or "–"))
    lines.append("Signale (häufigste 30):")
    lines += [f"  {count:>7}  {name}" for name, count in result.signals.most_common(30)]
    lines.append(f"Stichprobe verborgen als Nicht-Geodaten ({len(result.hidden)} insgesamt):")
    lines += [f"  - {t}  <{u}>" for _, t, u in _sample(result.hidden, CLASSIFY_SAMPLE, seed)]
    changed = {p: result.hidden_after[p] - result.hidden_before[p] for p in result.hidden_after}
    lines.append(
        f"Verborgen je Herausgeber ohne/mit Regel schwacher Geo-Signale ({sum(result.hidden_before.values())} →"
        f" {sum(result.hidden_after.values())}; häufigste 30 Änderungen, Herausgeber | vorher | nachher):"
    )
    lines += [
        f"  {publisher[:80]} | {result.hidden_before[publisher]} | {result.hidden_after[publisher]}"
        for publisher, _ in sorted(changed.items(), key=lambda item: (-item[1], item[0]))[:30]
        if changed[publisher]
    ]
    lines.append("  Schwache Geo-Signale, die diese Funde vorher hielten: " + (
        ", ".join(f"{k} {v}" for k, v in sorted(result.overruled_signals.items())) or "–"
    ))
    lines.append(f"Stichprobe Geodaten ohne Signal, Grenzfälle ({len(result.undecided)} insgesamt):")
    lines += [f"  - {t}  <{u}>" for _, t, u in _sample(result.undecided, CLASSIFY_SAMPLE, seed)]
    lines.append("Ortstexte ohne Treffer (häufigste 30):")
    lines += [f"  {count:>7}  {text}" for text, count in result.unresolved.most_common(30)]
    lines.append(f"Kein Zugangsweg (no_access, {sum(result.access_reasons.values())}), nach Grund:")
    lines += [f"  {count:>7}  {reason}" for reason, count in result.access_reasons.most_common()]
    lines.append("  10 Beispiele (Grund | Titel | Link | Formate):")
    lines += [f"  - {r} | {t} | <{u}> | {f}" for r, t, u, f in _sample(result.no_access, 10, seed)]
    moved = sum(result.link_moves.values())
    lines.append(
        f"Link „Source“ wegen Sammelseite auf einen anderen Rang gefallen ({moved} von {result.finds}), nach Rang:"
    )
    lines += [f"  {count:>7}  Rang {move}" for move, count in sorted(result.link_moves.items())]
    lines.append("  10 Beispiele (Titel | Sammelseite, Rang | Link jetzt, Rang):")
    lines += [f"  - {t} | <{u}>, {r} | <{n}>, {m}" for t, u, r, n, m in _sample(result.link_examples, 10, seed)]
    lines.append(f"Link „Source“ mit Muster einer Schnittstelle ({sum(result.api_links.values())}), nach Muster:")
    lines += [f"  {count:>7}  {pattern}" for pattern, count in result.api_links.most_common()]
    lines.append("  10 Beispiele (Muster | Titel | Link):")
    lines += [f"  - {p} | {t} | <{u}>" for p, t, u in _sample(result.api_examples, 10, seed)]
    lines += _dedupe_lines(result.dedupe)
    lines.append(
        f"Kandidaten für also_listed_as ({len(result.title_candidates)}; Titel gleich dem eines vollen Eintrags, nur ein"
        " Vorschlag, nie automatisch eingetragen; voller Eintrag | Fund | Quelle | Herausgeber | Schlüssel):"
    )
    lines += candidate_lines(result.title_candidates)
    lines.append("Gleichnamige Stadt und Kanton, je Name und Entscheid nach Herausgeber:")
    lines += [f"  {count:>7}  {choice}" for choice, count in sorted(result.choices.items())]
    lines.append(f"GeoNames-IDs ohne Zuordnung ({len(result.geonames)} verschiedene, häufigste 50):")
    lines += [f"  {count:>7}  https://sws.geonames.org/{gid}/" for gid, count in result.geonames.most_common(50)]
    lines.append(f"Lizenzangaben ({len(result.statements)} verschiedene, häufigste 60; Funde | Angabe | häufigste Herausgeber):")
    by_count = sorted(result.statements.items(), key=lambda item: (-sum(item[1].values()), item[0]))
    for statement, publishers in by_count[:60]:
        top = "; ".join(f"{name} {count}" for name, count in publishers.most_common(3))
        lines.append(f"  {sum(publishers.values()):>7}  {statement[:160]} | {top}")
    # Wording for `matches` in terms.yaml must be verbatim: the 200 most frequent statements whole, one JSON per line.
    lines.append("Lizenzangaben vollständig (häufigste 200, je Zeile JSON mit Zahl und Angabe):")
    lines += [
        "  " + json.dumps({"finds": sum(publishers.values()), "statement": statement}, ensure_ascii=False)
        for statement, publishers in by_count[:200]
    ]
    lines.append("Warteliste nach Paar Herausgeber, Lizenzangabe (häufigste 20):")
    lines += [f"  {count:>7}  {pub} | {stmt}" for (pub, stmt), count in result.pairs.most_common(20)]
    return "\n".join(lines)


def _rows(conn: psycopg.Connection, ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT dataset_id, content->>'title', content->'earthx:listing'->>'source_url', license_rule, link_host,"
            " account, delivery, source_id FROM public.earthx_listed_entry WHERE dataset_id = ANY(%s)",
            (list(ids),),
        )
        names = ("title", "source_url", "license_rule", "link_host", "account", "delivery", "source_id")
        return {row[0]: dict(zip(names, row[1:], strict=True)) for row in cur.fetchall()}


def stack_flags(conn: psycopg.Connection, stack: Stack) -> dict[str, tuple[Flag, ...]]:
    """The warning signs of the entries of ``stack`` that have one (M5-67 plan §5): they stay out of the sample and
    out of the approval."""
    rules, rule = load_flag_rules(), load_geodata_rule()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT dataset_id, coalesce(content->>'title', ''), coalesce(content->>'description', ''), keywords,"
            " coalesce(publisher, ''), category, data_kind, coalesce(content->'earthx:listing'->>'source_url', '')"
            " FROM public.earthx_listed_entry WHERE dataset_id = ANY(%s)",
            ([entry[0] for entry in stack.entries],),
        )
        rows = cur.fetchall()
    found = {}
    for dataset_id, title, description, keywords, publisher, category, data_kind, link in rows:
        entry = FlagEntry(dataset_id, title, description, tuple(keywords or ()), publisher, category, data_kind, link)
        flags = flags_of(entry, rules, rule)
        if flags:
            found[dataset_id] = flags
    return found


def stack_sample(
    conn: psycopg.Connection, stack: Stack, flagged: Iterable[str] = ()
) -> list[dict[str, Any]]:
    """N2 (adr/0033 §8.2): 15 aimed (rules, hosts, ways of access new to the source, largest first), 15 at random;
    never an entry with a warning sign (``flagged``), which stays out anyway."""
    left_out = set(flagged)
    ids = [entry[0] for entry in stack.entries if entry[0] not in left_out]
    if len(ids) <= SAMPLE_RANDOM + SAMPLE_AIMED:
        return [{"dataset_id": i, "why": "all"} for i in ids]
    rows = _rows(conn, ids)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT license_rule, link_host, account || '/' || delivery FROM public.earthx_listed_entry"
            " WHERE source_id = (SELECT source_id FROM public.earthx_listing_batch WHERE batch_id = %s)"
            " AND state = 'published'",
            (stack.batch_id,),
        )
        published = cur.fetchall()
    seen_rules = {r[0] for r in published}
    seen_hosts = {r[1] for r in published}
    seen_access = {r[2] for r in published}
    chosen: list[dict[str, Any]] = []
    taken: set[str] = set()
    for why, value_of, seen in (
        ("new_rule", lambda r: r["license_rule"], seen_rules),
        ("new_host", lambda r: r["link_host"], seen_hosts),
        ("new_access", lambda r: f"{r['account']}/{r['delivery']}", seen_access),
    ):
        groups = Counter(value_of(rows[i]) for i in ids if value_of(rows[i]) not in seen)
        for value, _ in groups.most_common():
            if len(chosen) >= SAMPLE_AIMED:
                break
            pick = next((i for i in sorted(ids) if value_of(rows[i]) == value and i not in taken), None)
            if pick is not None:
                chosen.append({"dataset_id": pick, "why": why})
                taken.add(pick)
    rest = [i for i in ids if i not in taken]
    chosen += [{"dataset_id": i, "why": "random"} for i in _sample(rest, SAMPLE_RANDOM, stack.fingerprint)]
    return chosen


def _pairs(conn: psycopg.Connection, source_id: str, seed: str) -> list[tuple[str, str, str, str, str]]:
    """Up to 20 pairs (duplicate, main, the key they share) that touch the source, drawn with ``seed`` (plan §13b)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT d.dataset_id, d.content->>'title', d.duplicate_of, coalesce(m.content->>'title', d.duplicate_of),"
            " coalesce(d.dedupe_keys, '{}'), coalesce(m.dedupe_keys, '{}')"
            " FROM public.earthx_listed_entry d LEFT JOIN public.earthx_listed_entry m ON m.dataset_id = d.duplicate_of"
            " WHERE d.state = 'duplicate' AND (d.source_id = %s OR m.source_id = %s) ORDER BY d.dataset_id",
            (source_id, source_id),
        )
        rows = cur.fetchall()
    pairs = [(a, ta, b, tb, shared_key(ka, kb) or "voller oder Handeintrag") for a, ta, b, tb, ka, kb in rows]
    return _sample(pairs, SAMPLE_PAIRS, seed)


def approval_document(  # type: ignore[no-untyped-def]
    source: SourceConfig, stack: Stack, sample: list[dict[str, Any]], rows, day: date, excluded: Sequence[str] = ()
) -> dict:
    return {
        "source_id": source.source_id,
        "batch_id": stack.batch_id,
        "fingerprint": stack.fingerprint,
        "created_on": day,
        "entries": len(stack.entries),
        "decision": "pending",
        "decided_on": None,
        "excluded_rules": [],
        "revoked_on": None,
        "sample": [
            {
                "dataset_id": item["dataset_id"],
                "why": item["why"],
                "title": rows[item["dataset_id"]]["title"],
                "source_url": rows[item["dataset_id"]]["source_url"],
                "license_rule": rows[item["dataset_id"]]["license_rule"],
                "ok": None,
            }
            for item in sample
        ],
        "excluded_entries": sorted(excluded),
    }


_APPROVAL_HEAD = """\
# Approval of a run of the harvest (adr/0033 §8; M5-20 plan §12), written by `discovery report`. Check the sample in
# the report beside this file: open each link, compare licence, publisher, access, extent and that it is geodata; set
# `ok: true` or `ok: false` for every entry. Then set `decision` (approved or rejected) and `decided_on` (the day).
# `excluded_rules` takes licence rules whose entries stay out; `revoked_on` hides again what this file published.
# `excluded_entries` are entries with a warning sign (M5-67 plan §5, in the report); they stay out and wait.
# Only entries whose own link passed the automatic check become visible (M5-67 plan §4). Never a name, an address or the words of a request here: the repository is public.
"""


def _flag_lines(flagged: Mapping[str, tuple[Flag, ...]], rows: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Per code the number of entries and up to ten of them, sorted, with the word that gave the sign."""
    by_code: dict[str, list[tuple[str, str]]] = {}
    for dataset_id, flags in sorted(flagged.items()):
        for flag in flags:
            by_code.setdefault(flag.code, []).append((dataset_id, flag.why))
    lines = []
    for code, items in sorted(by_code.items()):
        lines.append(f"- {code}: {len(items)}")
        for dataset_id, why in items[:10]:
            row = rows.get(dataset_id, {})
            if any(flag.code == "W6" for flag in flagged[dataset_id]):
                # A mail address or a phone number in the title or the description never goes into the repository.
                lines.append(f"  - {dataset_id} (Titel und Link nicht gezeigt: Kontaktangabe) — `{why}`")
            else:
                lines.append(f"  - {row.get('title', dataset_id)} — <{row.get('source_url', '')}> — `{why}`")
    return lines or ["- keine"]


def dump_approval(document: Mapping[str, Any]) -> str:
    """An approval file as the report writes it: the head of comments, then the fields in their order, no anchors."""
    return _APPROVAL_HEAD + dump_yaml(dict(document))


def report_numbers(conn: psycopg.Connection, result: ReportResult) -> dict[str, Any]:
    """The numbers of a report for the files of a harvest run (M5-67 plan §9): counts, the stack, the files, and the
    warning signs of the stack by code with up to ten entries each (a find with a mail address or a phone number by
    its id only)."""
    flagged: dict[str, list[dict[str, str]]] = {}
    if result.stack is not None:
        flags = stack_flags(conn, result.stack)
        titles = _rows(conn, sorted(flags)) if flags else {}
        for dataset_id, signs in sorted(flags.items()):
            contact = any(sign.code == "W6" for sign in signs)
            for sign in signs:
                entries = flagged.setdefault(sign.code, [])
                row = titles.get(dataset_id, {})
                entries.append(
                    {
                        "dataset_id": dataset_id,
                        "title": "" if contact else str(row.get("title") or ""),
                        "link": "" if contact else str(row.get("source_url") or ""),
                        "why": sign.why,
                    }
                )
    return {
        "source_id": result.source_id,
        "finds": result.finds,
        "written": result.written,
        "blocked": result.blocked,
        "failed": result.failed,
        "verdicts": dict(result.verdicts),
        "waiting": dict(result.waiting),
        "stack": None
        if result.stack is None
        else {"batch_id": result.stack.batch_id, "entries": len(result.stack.entries), "created": result.stack.created},
        "files": [path.name for path in result.files],
        "flagged": {code: {"count": len(items), "examples": items[:10]} for code, items in flagged.items()},
    }


def report_markdown(  # type: ignore[no-untyped-def]
    source: SourceConfig,
    result: ReportResult,
    sample: list[dict[str, Any]],
    rows,
    pairs,
    day: date,
    flagged: Mapping[str, tuple[Flag, ...]] | None = None,
) -> str:
    stack = result.stack
    assert stack is not None
    lines = [
        f"# Lauf-Bericht {source.source_id}, {day.isoformat()}",
        "",
        f"Stapel {stack.batch_id}, {len(stack.entries)} Einträge, Fingerabdruck `{stack.fingerprint}`.",
        "",
        "## Zahlen",
        "",
        f"- Funde {result.finds}, gesperrt {result.blocked}, neu oder geändert geschrieben {result.written}",
        "- Ergebnis: " + ", ".join(f"{k} {v}" for k, v in sorted(result.verdicts.items())),
        "- Warten: " + (", ".join(f"{k} {v}" for k, v in sorted(result.waiting.items())) or "–"),
        "- Ausdehnung: " + ", ".join(f"{k} {v}" for k, v in sorted(result.bases.items())),
        f"- Dubletten markiert {result.duplicates[0]}, wiederhergestellt {result.duplicates[1]}",
        f"- Weg bei der Quelle: zum ersten Mal {result.missing}, Grabstein {result.tombstones};"
        f" nie veröffentlicht und entfernt {result.deleted}",
        "",
        "## Warteliste (die 20 größten Paare Herausgeber, Lizenzangabe)",
        "",
        *[f"- {count} — {pub} — `{stmt}`" for (pub, stmt), count in result.pairs.most_common(20)],
        "",
        f"## Warnzeichen ({len(flagged or {})} Einträge bleiben draußen und warten)",
        "",
        *_flag_lines(flagged or {}, rows),
        "",
        "## Stichprobe (in der Freigabedatei abhaken)",
        "",
    ]
    for item in sample:
        row = rows[item["dataset_id"]]
        lines.append(f"- [{item['why']}] {row['title']} — <{row['source_url']}> — `{row['license_rule']}`")
    seed = stack.fingerprint
    lines += ["", "## Verborgen als Nicht-Geodaten (Stichprobe)", ""]
    lines += [f"- {t} — <{u}>" for _, t, u in _sample(result.hidden, SAMPLE_HIDDEN, seed)]
    lines += ["", "## Dubletten (Stichprobe, Duplikat → Haupteintrag, gemeinsamer Schlüssel)", ""]
    lines += [f"- {a} „{ta}“ → {b} „{tb}“ — `{key}`" for a, ta, b, tb, key in pairs]
    lines += [
        "",
        f"## Kandidaten für also_listed_as ({len(result.title_candidates)}; nur ein Vorschlag, nie automatisch eingetragen)",
        "",
        "Gelistete Funde, deren Titel dem eines vollen Eintrags gleicht (voller Eintrag | Fund | Quelle | Herausgeber |"
        " Schlüssel):",
        "",
    ]
    lines += [line.replace("  - ", "- ", 1) for line in candidate_lines(result.title_candidates)]
    return "\n".join(lines) + "\n"


def _has_file(out: Path, fingerprint: str) -> bool:
    return out.is_dir() and any(fingerprint in path.read_text(encoding="utf-8") for path in out.glob("*.yaml"))


def write_files(
    conn: psycopg.Connection, source: SourceConfig, result: ReportResult, out: Path, day: date
) -> tuple[Path, ...]:
    """The approval file and its report for a new stack under ``out``; for the open stack again where its file is not
    there (a branch thrown away, a write that failed), else nothing."""
    stack = result.stack
    if stack is None or (not stack.created and _has_file(out, stack.fingerprint)):
        return ()
    flagged = stack_flags(conn, stack)
    sample = stack_sample(conn, stack, flagged)
    rows = _rows(conn, [item["dataset_id"] for item in sample] + sorted(flagged))
    pairs = _pairs(conn, source.source_id, stack.fingerprint)
    out.mkdir(parents=True, exist_ok=True)
    stem = next_file_stem(out, day, source.source_id)
    approval = out / f"{stem}.yaml"
    document = approval_document(source, stack, sample, rows, day, excluded=list(flagged))
    approval.write_text(dump_approval(document), encoding="utf-8")
    markdown = out / f"{stem}.md"
    markdown.write_text(report_markdown(source, result, sample, rows, pairs, day, flagged), encoding="utf-8")
    return approval, markdown


def summary(source: SourceConfig, result: ReportResult) -> str:
    lines = [
        f"Bericht {source.source_id}: {result.finds} Funde, gesperrt {result.blocked}, geschrieben {result.written},"
        f" fehlerhaft {result.failed}",
        "Ergebnis: " + ", ".join(f"{k} {v}" for k, v in sorted(result.verdicts.items())),
        "Warten: " + (", ".join(f"{k} {v}" for k, v in sorted(result.waiting.items())) or "–"),
        f"Dubletten markiert {result.duplicates[0]}, wiederhergestellt {result.duplicates[1]}",
    ]
    if result.stack is None:
        lines.append("Kein Eintrag in Prüfung: kein Stapel, keine Freigabedatei.")
    elif not result.files:
        lines.append(f"Stapel {result.stack.batch_id} unverändert ({len(result.stack.entries)} Einträge): keine neue Datei.")
    else:
        lines.append(f"Neuer Stapel {result.stack.batch_id}, {len(result.stack.entries)} Einträge.")
        lines += [f"Geschrieben: {path.name}" for path in result.files]
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report one harvested source: derive, dedupe, stack (M5-20).")
    parser.add_argument("source_id")
    parser.add_argument("--classify", action="store_true", help="show the rule R-G and the samples, write nothing")
    parser.add_argument("--out", type=Path, default=CATALOG_DIR / "approvals", help="where the approval file goes")
    parser.add_argument("--json", type=Path, default=None, help="also write the numbers as JSON (harvest cycle)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    configure_logging()
    try:
        sources = read_sources()
        licences = load_licences(sources)
        blocklist = load_blocked()
        load_place_directory()
        load_geodata_rule()
        load_flag_rules()
    except (ConfigError, EntryFileError) as error:
        print(f"report failed: {error}", file=sys.stderr)
        return 1
    source = sources.get(args.source_id)
    if source is None:
        print(f"report failed: no source {args.source_id!r} in backend/catalog/sources/", file=sys.stderr)
        return 1
    try:
        with psycopg.connect(autocommit=True) as conn:
            result = run_report(
                conn, source, sources=sources, licences=licences, blocklist=blocklist, classify_only=args.classify
            )
            if args.classify:
                print(classify_text(source, result))
                return 0
            result.files = write_files(conn, source, result, args.out, date.today())
            if args.json is not None:
                args.json.write_text(json.dumps(report_numbers(conn, result), ensure_ascii=False), encoding="utf-8")
    except ConfigError as error:
        print(f"report failed: {error}", file=sys.stderr)
        return 1
    except psycopg.Error as error:
        print(f"report failed: database error {type(error).__name__} ({error.sqlstate or 'no state'})", file=sys.stderr)
        return 1
    except OSError as error:
        # The stack stays open in the database; the next report writes its file where this one could not.
        print(f"report failed: the approval file cannot be written ({type(error).__name__})", file=sys.stderr)
        return 1
    print(summary(source, result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
