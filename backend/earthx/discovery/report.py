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
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import cache
from pathlib import Path
from typing import Any

import psycopg
import yaml

from earthx.catalog import collection as collection_module
from earthx.catalog import licences as licences_module
from earthx.catalog import listed as listed_module
from earthx.catalog.collection import SCIENTIFIC_EXTENSION, STAC_VERSION
from earthx.catalog.datasets import CATALOG_DIR, registry
from earthx.catalog.entry_files import EntryFileError
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
from earthx.discovery.dedupe import Member, find_keys, main_entries, namespaced
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
from earthx.discovery.geodata import GEODATA_FILE, Classified, GeodataRule, classify, load_geodata_rule
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
    digest.update(json.dumps([source.country, source.maturity.value, sorted(known.items())]).encode())
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
        dedupe_keys=find_keys(found, stac_host=stac_host, known=known),
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
    by_id = {config.dataset_id: config for config in registry()}
    collections = {config.dataset_id: (host, cid) for config, host, cid in _full_collections()}
    for dataset, config in by_id.items():
        keys = set()
        if dataset in collections:
            keys.add(f"coll:{collections[dataset][0]}/{collections[dataset][1]}")
        name = doi_name(config.doi)
        if name:
            keys.add(f"doi:{name.lower()}")
        if keys:
            members.append(Member(dataset, tuple(sorted(keys)), (0,)))
    return members


def _dedupe(conn: psycopg.Connection, sources: Mapping[str, SourceConfig]) -> dict[str, str]:
    members = _full_members()
    for row in dedupe_rows(conn):
        source = sources.get(row.source_id)
        if row.source_id == HAND_SOURCE:
            rank: tuple[Any, ...] = (1,)
        else:
            # A source no longer in sources/ ranks last.
            dedupe_rank = MAX_DEDUPE_RANK + 1 if source is None else source.dedupe_rank
            rank = (2, dedupe_rank, row.source_rank or 9, not row.footprint, row.source_id)
        members.append(Member(row.dataset_id, row.keys, rank))
    return main_entries(members)


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
    deleted: int = 0
    missing: int = 0
    tombstones: int = 0
    duplicates: tuple[int, int] = (0, 0)
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
        _count(result, derived, found)
        if not classify_only and stored.get(key) != derived.row.derived_sha256:
            batch.append(derived.row)
            if len(batch) >= _BATCH:
                flush()
    if classify_only:
        return result
    if batch:
        flush()
    with conn.transaction():
        missing = settle_missing(conn, source.source_id, blocked_keys)
        result.deleted, result.missing, result.tombstones = missing.deleted, missing.marked, missing.tombstones
        apply_blocklist(conn, blocklist)
    with conn.transaction():
        result.duplicates = apply_duplicates(conn, _dedupe(conn, sources))
    with conn.transaction():
        result.stack = form_stack(conn, source.source_id)
    return result


def _count(result: ReportResult, derived: Derived, found: Mapping[str, Any]) -> None:
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
    if row.waiting_reason in ("unknown_licence", "not_granted"):
        for statement in derived.statements:
            result.pairs[(row.publisher or "–", normal_statement(statement)[:100])] += 1
    entry = (row.dataset_id, str(found.get("title"))[:120], str(found.get("source_url")))
    if derived.classified.outcome == "not_geodata":
        result.hidden.append(entry)
    elif derived.classified.outcome == "undecided":
        result.undecided.append(entry)


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


def classify_text(source: SourceConfig, result: ReportResult) -> str:
    """The output of ``--classify``: counts and the two samples for the release of R-G (plan §7)."""
    seed = f"{source.source_id}:{derivation_version(source, {}, None)}"
    lines = [f"Einstufung {source.source_id} (nichts geschrieben): {result.finds} Funde, gesperrt {result.blocked}"]
    lines.append("Ergebnis: " + ", ".join(f"{k} {v}" for k, v in sorted(result.verdicts.items())))
    lines.append("Ausdehnung: " + ", ".join(f"{k} {v}" for k, v in sorted(result.bases.items())))
    lines.append("Warten: " + (", ".join(f"{k} {v}" for k, v in sorted(result.waiting.items())) or "–"))
    lines.append("Signale (häufigste 30):")
    lines += [f"  {count:>7}  {name}" for name, count in result.signals.most_common(30)]
    lines.append(f"Stichprobe verborgen als Nicht-Geodaten ({len(result.hidden)} insgesamt):")
    lines += [f"  - {t}  <{u}>" for _, t, u in _sample(result.hidden, CLASSIFY_SAMPLE, seed)]
    lines.append(f"Stichprobe Geodaten ohne Signal, Grenzfälle ({len(result.undecided)} insgesamt):")
    lines += [f"  - {t}  <{u}>" for _, t, u in _sample(result.undecided, CLASSIFY_SAMPLE, seed)]
    lines.append("Ortstexte ohne Treffer (häufigste 30):")
    lines += [f"  {count:>7}  {text}" for text, count in result.unresolved.most_common(30)]
    lines.append(f"Kein Zugangsweg (no_access, {sum(result.access_reasons.values())}), nach Grund:")
    lines += [f"  {count:>7}  {reason}" for reason, count in result.access_reasons.most_common()]
    lines.append("  10 Beispiele (Grund | Titel | Link | Formate):")
    lines += [f"  - {r} | {t} | <{u}> | {f}" for r, t, u, f in _sample(result.no_access, 10, seed)]
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


def stack_sample(conn: psycopg.Connection, stack: Stack) -> list[dict[str, Any]]:
    """N2 (adr/0033 §8.2): 15 aimed (rules, hosts, ways of access new to the source, largest first), 15 at random."""
    ids = [entry[0] for entry in stack.entries]
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


def _pairs(conn: psycopg.Connection, source_id: str, seed: str) -> list[tuple[str, str, str, str]]:
    """Up to 20 pairs (duplicate, main) that touch the source, drawn with ``seed`` (plan §13b)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT d.dataset_id, d.content->>'title', d.duplicate_of, coalesce(m.content->>'title', d.duplicate_of)"
            " FROM public.earthx_listed_entry d LEFT JOIN public.earthx_listed_entry m ON m.dataset_id = d.duplicate_of"
            " WHERE d.state = 'duplicate' AND (d.source_id = %s OR m.source_id = %s) ORDER BY d.dataset_id",
            (source_id, source_id),
        )
        return _sample(cur.fetchall(), SAMPLE_PAIRS, seed)


def approval_document(source: SourceConfig, stack: Stack, sample: list[dict[str, Any]], rows, day: date) -> dict:  # type: ignore[no-untyped-def]
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
    }


class _PlainDumper(yaml.SafeDumper):
    """YAML without anchors: the strict loader of the entries refuses them (``entry_files``)."""

    def ignore_aliases(self, data: Any) -> bool:
        return True


_APPROVAL_HEAD = """\
# Approval of a run of the harvest (adr/0033 §8; M5-20 plan §12), written by `discovery report`. Check the sample in
# the report beside this file: open each link, compare licence, publisher, access, extent and that it is geodata; set
# `ok: true` or `ok: false` for every entry. Then set `decision` (approved or rejected) and `decided_on` (the day).
# `excluded_rules` takes licence rules whose entries stay out; `revoked_on` hides again what this file published.
# Never a name, an address or the words of a request here: the repository is public.
"""


def report_markdown(
    source: SourceConfig, result: ReportResult, sample: list[dict[str, Any]], rows, pairs, day: date
) -> str:  # type: ignore[no-untyped-def]
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
        "## Stichprobe (in der Freigabedatei abhaken)",
        "",
    ]
    for item in sample:
        row = rows[item["dataset_id"]]
        lines.append(f"- [{item['why']}] {row['title']} — <{row['source_url']}> — `{row['license_rule']}`")
    seed = stack.fingerprint
    lines += ["", "## Verborgen als Nicht-Geodaten (Stichprobe)", ""]
    lines += [f"- {t} — <{u}>" for _, t, u in _sample(result.hidden, SAMPLE_HIDDEN, seed)]
    lines += ["", "## Dubletten (Stichprobe, Duplikat → Haupteintrag)", ""]
    lines += [f"- {a} „{ta}“ → {b} „{tb}“" for a, ta, b, tb in pairs]
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
    sample = stack_sample(conn, stack)
    rows = _rows(conn, [item["dataset_id"] for item in sample])
    pairs = _pairs(conn, source.source_id, stack.fingerprint)
    out.mkdir(parents=True, exist_ok=True)
    stem, number = f"{day.isoformat()}-{source.source_id}", 1
    while (out / f"{stem}.yaml").exists():
        number += 1
        stem = f"{day.isoformat()}-{source.source_id}-{number}"
    approval = out / f"{stem}.yaml"
    document = approval_document(source, stack, sample, rows, day)
    approval.write_text(_APPROVAL_HEAD + yaml.dump(document, Dumper=_PlainDumper, sort_keys=False, allow_unicode=True), encoding="utf-8")
    markdown = out / f"{stem}.md"
    markdown.write_text(report_markdown(source, result, sample, rows, pairs, day), encoding="utf-8")
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
