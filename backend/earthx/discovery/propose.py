"""Candidates of the full way: ``discovery propose`` (M5-20 plan §11, §14.1; adr/0025 §6.1 V1, §6.3, §6.5 P1; adr/0031
§4.4, §8; adr/0033 §11 "Gelistet wird voll").

    python -m earthx.discovery.propose [<source>...] [--trial] [--out DIR] [--json FILE] [--day YYYY-MM-DD]

A visible listed entry (``published``: main entry of its group, link checked, licence graded and granted) becomes a
candidate for a full entry where all of this holds (plan §14.1.2, F6 = 1, F16, F17 = 1, A33):

1. a raster in a format a full entry reads (COG/GeoTIFF, NetCDF/HDF5, Zarr), as a file of the find or an asset of a
   STAC collection;
2. its licence allows a full entry: the tier from ``terms.yaml`` is above ``catalog`` (Otto, 25.11.2026: K1 and K2);
3. a key by which a full entry takes over the listed row: the collection of a STAC source (``coll:``), an identifier
   unique in its source (``also_listed_as``), or a DOI unique in its source; no full entry has it yet;
4. Verify passed without an account (adr/0025 §6.3): ``HEAD`` and the first 16 KB (``Range``) of at most three files,
   ``200``/``206`` and a readable format from the bytes (:mod:`earthx.discovery.probe`); ``401``/``403`` is an account.

New candidates come before changed ones, then by publisher and id; at most :data:`MAX_PER_SOURCE` a source and run, and
Verify for at most :data:`MAX_VERIFIED_PER_SOURCE` (A34). A candidate whose harvested part, licence and takeover are as
on disk is left alone and asks nothing (A35). A candidate whose listed row is no longer visible gets the new state,
without a request; no file is ever deleted (A37).

Each candidate is two files under ``backend/catalog/candidates/<source>/``: ``<listed id>.yaml`` (what was harvested,
the proposed id and takeover, the licence with its decision by rules (F15 = 1), Verify, empty fields for the
onboarding) and ``<listed id>.probe.json`` (the normalised collection and 1-3 items of a STAC source with the result of
Verify, at most 50 KB; metadata only). In the trial run nothing is decided (A39). Every text passes ``cycle.clean``.

Requests only through ``gateway`` (KLAERUNGEN B8): the items of a STAC source with the source's own policy (its host,
spacing, ``robots.txt``); the files with exactly their hosts, one connection and 1 s apart where ``hosts.yaml`` names no
other limit, without ``robots.txt`` (A6), at most :data:`MAX_NEW_HOSTS` hosts a run that ``hosts.yaml`` does not know. A
redirect to another host leaves a file unchecked. Nothing of a file is kept but the result.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
import yaml

from earthx.catalog.datasets import CATALOG_DIR, registry
from earthx.catalog.entry_files import EntryFileError
from earthx.catalog.hosts import HostLimit
from earthx.catalog.licences import LicenceCatalogue, load_licences
from earthx.catalog.registry import MAX_LISTING_IDENTIFIER_CHARS, ConfigError, LicenseInfo, LicenseTier
from earthx.catalog.sources import SourceConfig, SourceProtocol, read_sources
from earthx.discovery.cycle import clean
from earthx.discovery.extract import _format_token
from earthx.discovery.harvest import source_policy
from earthx.discovery.links import url_parts
from earthx.discovery.probe import HEAD_BYTES, sniff
from earthx.discovery.report import _full_members, dump_approval
from earthx.discovery.source_gateway import open_source_gateway
from earthx.gateway import (
    Gateway,
    GatewayError,
    Policy,
    ResponseTooLarge,
    UpstreamError,
    UrlRejected,
    normalize_host,
    user_agent_from_env,
)
from earthx.logging import configure_logging

__all__ = [
    "CANDIDATES_DIR",
    "MAX_NEW_HOSTS",
    "MAX_PER_SOURCE",
    "MAX_VERIFIED_PER_SOURCE",
    "ProposeRun",
    "Takeover",
    "declared_files",
    "proposed_id",
    "run_propose",
    "takeover_of",
]

CANDIDATES_DIR = CATALOG_DIR / "candidates"
#: Candidates written for one source in one run (adr/0025 F4, M5-20 plan §11).
MAX_PER_SOURCE = 20
#: Finds verified for one source in one run, until :data:`MAX_PER_SOURCE` passed (A34).
MAX_VERIFIED_PER_SOURCE = 60
#: Hosts of files a run asks that ``hosts.yaml`` does not know (A6).
MAX_NEW_HOSTS = 50
#: Files and items asked of one candidate (adr/0025 §6.3, adr/0031 §4.4).
MAX_FILES = 3
MAX_ITEMS = 3
#: The probe beside a candidate (adr/0031 §4.4).
MAX_PROBE_BYTES = 50 * 1024
MAX_DISTRIBUTIONS = 10
MAX_DESCRIPTION_CHARS = 4000
#: The ``Origin`` of the CORS test, until the platform has a public address (A36).
ORIGIN = "https://earthx.invalid"
#: Formats a full entry reads, as catalogues write them (after ``extract._format_token``) and as media types.
_FORMAT_TOKENS = frozenset("TIFF TIF GEOTIFF COG NETCDF NC HDF HDF5 ZARR".split())
_MEDIA_TYPES = (
    "image/tiff",
    "application/x-netcdf",
    "application/netcdf",
    "application/x-hdf",
    "application/x-hdf5",
    "application/vnd+zarr",
    "application/vnd.zarr",
)
_AWS_REGION = re.compile(r"[a-z0-9.-]+\.s3[.-](?P<region>[a-z]{2}(?:-gov)?-[a-z]+-\d)\.amazonaws\.com")
#: The day and the decision of a candidate, which a rewrite with the same content keeps.
_KEPT = ("first_proposed",)

OpenGateway = Callable[[Policy], AbstractAsyncContextManager[Gateway]]


# --- Pure parts -------------------------------------------------------------------------------------------------------


def readable_declared(format_: str | None, media_type: str | None) -> bool:
    """Whether a file says it is in a format a full entry reads, by its format or its media type."""
    if format_ and _format_token(format_) in _FORMAT_TOKENS:
        return True
    return bool(media_type) and media_type.split(";", 1)[0].strip().lower().startswith(_MEDIA_TYPES)


def _https(href: object) -> bool:
    return isinstance(href, str) and href.lower().startswith("https://") and len(href) <= 2048


def declared_files(found: Mapping[str, Any]) -> list[str]:
    """The files of a find that say they are readable rasters, ``https`` only, at most :data:`MAX_FILES`."""
    hrefs: list[str] = []
    for item in found.get("distributions") or ():
        if not isinstance(item, Mapping):
            continue
        href = item.get("href")
        if _https(href) and readable_declared(item.get("format"), item.get("media_type")) and href not in hrefs:
            hrefs.append(str(href))
    return hrefs[:MAX_FILES]


@dataclass(frozen=True, slots=True)
class Takeover:
    """How a full entry made from the candidate takes over the listed row (plan §14.1.5)."""

    #: ``coll`` (the full entry's STAC source), ``also_listed_as`` (its field) or ``doi``.
    via: str
    key: str
    also_listed_as: tuple[str, ...] = ()

    def to_document(self) -> dict[str, Any]:
        document: dict[str, Any] = {"via": self.via, "key": self.key}
        if self.also_listed_as:
            document["also_listed_as"] = list(self.also_listed_as)
        return document


_IDENTIFIER = re.compile(r"[^\s\x00-\x1f\x7f]{1,%d}" % MAX_LISTING_IDENTIFIER_CHARS)


def takeover_of(source_id: str, keys: Iterable[str], repeated: Iterable[str]) -> Takeover | None:
    """The way a full entry takes over a row with ``keys``; ``repeated`` are the keys more than one row of the source
    holds (no key then: ``also_listed_as`` would take them all). ``None`` where there is none (F17 = 1)."""
    keys = sorted(keys)
    repeated = set(repeated)
    for key in keys:
        if key.startswith("coll:"):
            return Takeover("coll", key)
    for key in keys:
        identifier = key[3:]
        if key.startswith("id:") and key not in repeated and _IDENTIFIER.fullmatch(identifier):
            listing = f"{source_id}:{identifier}"
            return Takeover("also_listed_as", f"also:{listing}", (listing,))
    for key in keys:
        if key.startswith("doi:") and key not in repeated:
            return Takeover("doi", key)
    return None


_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"})


def _slug(text: str, limit: int = 60) -> str:
    ascii_text = unicodedata.normalize("NFKD", text.translate(_UMLAUTS)).encode("ascii", "ignore").decode("ascii")
    words = re.findall(r"[a-z0-9]+", ascii_text.lower())
    slug = ""
    for word in words:
        if len(slug) + len(word) + (1 if slug else 0) > limit:
            break
        slug = f"{slug}-{word}" if slug else word
    return slug or (words[0][:limit] if words else "")


_STAC_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")


def proposed_id(source: SourceConfig, found: Mapping[str, Any], taken: Iterable[str]) -> str:
    """A readable id for the full entry (F17 = 1): the collection id of a STAC source, else the title as a short form
    of ``[a-z0-9-]``; where that is taken already, the source in front. Only a proposal: the onboarding decides."""
    key = str(found.get("source_key") or "").lower()
    if source.protocol is SourceProtocol.STAC_API and _STAC_ID.fullmatch(key):
        base = key
    else:
        base = _slug(str(found.get("title") or "")) or f"{source.source_id}-{_slug(key, 20)}"
    taken = set(taken)
    if base not in taken:
        return base
    with_source = f"{source.source_id}-{base}"[:128]
    number = 2
    candidate = with_source
    while candidate in taken:
        candidate = f"{with_source[:120]}-{number}"
        number += 1
    return candidate


def data_region(hosts: Iterable[str]) -> str | None:
    """``aws:<region>`` where the files lie in one region of S3 (adr/0022), else ``None``."""
    regions = {match["region"] for host in hosts if (match := _AWS_REGION.fullmatch(host))}
    return f"aws:{regions.pop()}" if len(regions) == 1 else None


def _host(url: str) -> str | None:
    parts = url_parts(url)
    if parts is None:
        return None
    try:
        return normalize_host(parts[0])
    except UrlRejected:
        return None


# --- Verify -----------------------------------------------------------------------------------------------------------


@dataclass(slots=True)
class FileCheck:
    """What one file answered (adr/0025 §6.3); only codes and headers, never content."""

    href: str
    outcome: str  # passed, failed, account, unchecked
    reason: str
    status: int | None = None
    media_type: str | None = None
    length: int | None = None
    accept_ranges: str | None = None
    partial: bool | None = None
    cors: str | None = None
    final_host: str | None = None
    format: dict[str, Any] | None = None

    def to_document(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__slots__ if getattr(self, name) is not None}


def _cors(headers: Mapping[str, str]) -> str:
    allowed = headers.get("access-control-allow-origin", "").strip()
    if allowed == "*":
        return "any"
    return "origin" if allowed == ORIGIN else "none"


def _length(headers: Mapping[str, str]) -> int | None:
    ranged = headers.get("content-range", "")
    if "/" in ranged and ranged.rsplit("/", 1)[1].isdigit():
        return int(ranged.rsplit("/", 1)[1])
    declared = headers.get("content-length", "")
    return int(declared) if declared.isdigit() else None


def _failed(href: str, error: GatewayError) -> FileCheck:
    if isinstance(error, UpstreamError):
        code = error.status_code
        if code in (401, 403):
            return FileCheck(href, "account", f"http_{code}", status=code)
        transient = code == 429 or code >= 500
        return FileCheck(href, "unchecked" if transient else "failed", f"http_{code}", status=code)
    if isinstance(error, UrlRejected) and "allowlist" in str(error.reason):
        return FileCheck(href, "unchecked", "redirect_host")
    return FileCheck(href, "unchecked", type(error).__name__.lower())


async def check_file(gateway: Gateway, href: str) -> FileCheck:
    """``HEAD``, then ``GET`` of the first :data:`HEAD_BYTES` with ``Origin``; the format from the bytes."""
    head_headers: Mapping[str, str] = {}
    try:
        head_headers = (await gateway.head(href, headers={"Origin": ORIGIN}, retry=False)).headers
    except UpstreamError as error:
        # Some hosts answer HEAD with 405 or 501 and GET with the file: then the GET says it.
        if error.status_code not in (405, 501):
            return _failed(href, error)
    except GatewayError as error:
        return _failed(href, error)
    try:
        response = await gateway.get(
            href, headers={"Range": f"bytes=0-{HEAD_BYTES - 1}", "Origin": ORIGIN}, retry=False
        )
    except ResponseTooLarge:
        # The host ignored Range and sends the whole file: reachable, but no partial reads, so no full entry reads it.
        return FileCheck(href, "failed", "no_range", status=200, partial=False)
    except GatewayError as error:
        return _failed(href, error)
    headers = {**head_headers, **response.headers}
    sniffed = sniff(response.content[:HEAD_BYTES], response.url or href)
    passed = response.status_code in (200, 206) and sniffed.readable
    return FileCheck(
        href,
        "passed" if passed else "failed",
        "ok" if passed else f"format_{sniffed.format}",
        status=response.status_code,
        media_type=headers.get("content-type"),
        length=_length(headers),
        accept_ranges=headers.get("accept-ranges"),
        partial=response.status_code == 206,
        cors=_cors(headers),
        final_host=_host(response.url) if response.url else None,
        format=sniffed.to_document(),
    )


def file_policy(allowed: frozenset[str], hosts: Mapping[str, HostLimit]) -> Policy:
    """Exactly the hosts of the files; ``hosts.yaml`` limits where it has them, else one connection and 1 s apart. No
    ``robots.txt`` for a ``HEAD`` and a ``Range`` of a file (A6); room for 16 KB and a host that sends a little more."""
    known = {host: hosts[host] for host in allowed if host in hosts}
    return Policy(
        allowed_hosts=allowed,
        max_connections_per_host=1,
        host_connections={host: limit.connections for host, limit in known.items()},
        host_intervals={host: limit.interval_s for host, limit in known.items() if limit.interval_s is not None},
        host_read_timeouts={host: limit.timeout_s for host, limit in known.items() if limit.timeout_s is not None},
        min_interval_s=1.0,
        obey_robots=False,
        max_redirects=5,
        max_response_bytes=4 * HEAD_BYTES,
        read_timeout_s=30.0,
        retry_rate_limited=False,
    )


def _data_assets(item: Mapping[str, Any]) -> list[str]:
    assets = item.get("assets")
    found = []
    for asset in assets.values() if isinstance(assets, Mapping) else ():
        if not isinstance(asset, Mapping) or not _https(asset.get("href")):
            continue
        roles = asset.get("roles") or ()
        if readable_declared(None, asset.get("type")) or ("data" in roles and not asset.get("type")):
            found.append(str(asset["href"]))
    return found


async def fetch_items(gateway: Gateway, source: SourceConfig, collection_id: str) -> tuple[list[dict[str, Any]], str]:
    """At most :data:`MAX_ITEMS` items of a STAC collection, and ``ok`` or why there are none."""
    url = f"{source.endpoint.rstrip('/')}/collections/{collection_id}/items"
    try:
        response = await gateway.get(url, params={"limit": MAX_ITEMS}, retry=False)
        features = response.json().get("features")
    except GatewayError as error:
        return [], _failed(url, error).reason
    except (ValueError, AttributeError):
        return [], "items_unreadable"
    items = [f for f in features or () if isinstance(f, dict)][:MAX_ITEMS] if isinstance(features, list) else []
    return items, "ok" if items else "no_items"


# --- The database -----------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Row:
    dataset_id: str
    source_key: str
    state: str
    content: Mapping[str, Any]
    keys: tuple[str, ...]
    publisher: str | None
    license_rule: str | None
    found: Mapping[str, Any]


def _rows(conn: psycopg.Connection, source_id: str) -> list[Row]:
    """The visible raster rows of a source with their intermediate form (A33)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT e.dataset_id, e.source_key, e.state, e.content, e.dedupe_keys, e.publisher, e.license_rule,"
            " s.extracted FROM public.earthx_listed_entry e"
            " JOIN public.earthx_record_state s ON s.source_id = e.source_id AND s.source_key = e.source_key"
            " WHERE e.source_id = %s AND e.state = 'published' AND e.data_kind = 'raster' AND s.state = 'extracted'"
            " ORDER BY e.dataset_id",
            (source_id,),
        )
        return [Row(r[0], r[1], r[2], r[3], tuple(r[4] or ()), r[5], r[6], r[7]) for r in cur.fetchall()]


def _repeated(conn: psycopg.Connection, source_id: str) -> set[str]:
    """The identifier and DOI keys more than one row of a source holds."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT key FROM public.earthx_listed_entry, unnest(dedupe_keys) AS key WHERE source_id = %s"
            " AND state NOT IN ('tombstone', 'superseded') AND (key LIKE 'id:%%' OR key LIKE 'doi:%%')"
            " GROUP BY key HAVING count(*) > 1",
            (source_id,),
        )
        return {row[0] for row in cur.fetchall()}


def _states(conn: psycopg.Connection, ids: Sequence[str]) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT dataset_id, state FROM public.earthx_listed_entry WHERE dataset_id = ANY(%s)", (list(ids),))
        return {row[0]: row[1] for row in cur.fetchall()}


# --- The candidate file -----------------------------------------------------------------------------------------------


def _licence_document(licence: LicenseInfo, publisher: str | None) -> dict[str, Any]:
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
        "tier": licence.tier.value,
        "attribution_modified": None
        if licence.attribution_modified is None
        else licence.attribution_modified.replace("{publisher}", name),
        "attribution_unmodified": None
        if licence.attribution_unmodified is None
        else licence.attribution_unmodified.replace("{publisher}", name),
        "terms_url": None if licence.terms is None else licence.terms.url,
    }


def _harvested(row: Row) -> dict[str, Any]:
    found, content = row.found, row.content
    bbox = ((content.get("extent") or {}).get("spatial") or {}).get("bbox") or [None]
    interval = ((content.get("extent") or {}).get("temporal") or {}).get("interval") or [[None, None]]
    description = str(found.get("description") or "")
    return {
        "title": found.get("title"),
        "description": description[:MAX_DESCRIPTION_CHARS],
        "publisher": row.publisher,
        "keywords": list(found.get("keywords") or ()),
        "doi": content.get("sci:doi"),
        "licence_statements": list(found.get("licence_statements") or ()),
        "bbox": bbox[0],
        "extent_basis": content.get("earthx:extent_basis"),
        "temporal": list(interval[0]),
        "source_url": found.get("source_url"),
        "landing_url": found.get("landing_url"),
        "distributions": [
            {key: d.get(key) for key in ("href", "format", "media_type", "title")}
            for d in (found.get("distributions") or ())[:MAX_DISTRIBUTIONS]
            if isinstance(d, Mapping)
        ],
    }


def candidate_document(
    row: Row,
    source: SourceConfig,
    *,
    proposed: str,
    takeover: Takeover,
    licence: LicenseInfo,
    refs: Sequence[str],
    day: date,
    trial: bool,
) -> dict[str, Any]:
    """A candidate without Verify: the part ``propose`` compares with the file on disk (A35)."""
    return {
        "source_id": source.source_id,
        "source_key": row.source_key,
        "listed_id": row.dataset_id,
        "listed_state": row.state,
        "first_proposed": day,
        "proposed_id": proposed,
        "takeover": takeover.to_document(),
        "harvested": _harvested(row),
        "licence": {
            "license_ref": list(refs),
            "license_rule": row.license_rule,
            "license": _licence_document(licence, row.publisher),
            # F15 = 1: decided by the rules that made the listed entry visible; the trial run decides nothing (A39).
            "legal_status": None if trial else "cleared",
            "decided_by": None if trial else "rules",
            "decided_on": None if trial else day,
        },
        "verify": None,
        "onboarding": {"way": None, "profile": None, "notes": None},
    }


def _comparable(document: Mapping[str, Any]) -> dict[str, Any]:
    """A candidate as it is compared with the file on disk: without its days and Verify (A35)."""
    found = {key: value for key, value in document.items() if key not in ("first_proposed", "verify", "onboarding")}
    licence = dict(found.get("licence") or {})
    licence.pop("decided_on", None)
    found["licence"] = licence
    return json.loads(json.dumps(clean_document(found), default=str))


def clean_document(value: Any) -> Any:
    """Every text of a document through ``cycle.clean``: no signed address, hash, mail address or local path."""
    if isinstance(value, str):
        return clean(value)
    if isinstance(value, Mapping):
        return {key: clean_document(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_document(item) for item in value]
    return value


def probe_document(row: Row, items: Sequence[Mapping[str, Any]], verify: Mapping[str, Any]) -> str:
    """The probe beside a candidate (adr/0031 §4.4): the collection, 1-3 items and Verify, at most 50 KB."""
    collection = dict(row.content)
    items = list(items)

    def text() -> str:
        document = {"collection": collection, "items": items, "verify": verify}
        return json.dumps(clean_document(document), ensure_ascii=False, indent=1, sort_keys=True) + "\n"

    while len(text().encode("utf-8")) > MAX_PROBE_BYTES and items:
        items.pop()
    if len(text().encode("utf-8")) > MAX_PROBE_BYTES:
        collection["description"] = str(collection.get("description") or "")[:2000]
        collection["earthx:distributions"] = list(collection.get("earthx:distributions") or ())[:MAX_DISTRIBUTIONS]
        collection["keywords"] = list(collection.get("keywords") or ())[:50]
    return text()


def _read(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return document if isinstance(document, dict) else None


# --- One run ----------------------------------------------------------------------------------------------------------


@dataclass(slots=True)
class SourceCount:
    new: int = 0
    changed: int = 0
    unchanged: int = 0
    state_updated: int = 0
    skipped: Counter[str] = field(default_factory=Counter)
    #: The candidates written in this run: id, title, format, licence, tier, decision.
    written: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


@dataclass(slots=True)
class ProposeRun:
    trial: bool
    sources: dict[str, SourceCount] = field(default_factory=dict)
    new_hosts: set[str] = field(default_factory=set)

    def numbers(self) -> dict[str, Any]:
        return {
            "trial": self.trial,
            "new_hosts": len(self.new_hosts),
            "sources": {
                source_id: {
                    "new": count.new,
                    "changed": count.changed,
                    "unchanged": count.unchanged,
                    "state_updated": count.state_updated,
                    "skipped": dict(sorted(count.skipped.items())),
                    "written": count.written,
                    "error": count.error,
                }
                for source_id, count in sorted(self.sources.items())
            },
        }


@dataclass(slots=True)
class _Pending:
    row: Row
    document: dict[str, Any]
    path: Path
    new: bool
    files: list[str] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)
    item_reason: str = "ok"
    checks: list[FileCheck] = field(default_factory=list)


def _full_keys() -> set[str]:
    return {key for member in _full_members() for key in member.keys}


def _select(
    conn: psycopg.Connection,
    source: SourceConfig,
    *,
    licences: LicenceCatalogue,
    out: Path,
    day: date,
    trial: bool,
    full_keys: set[str],
    taken_ids: set[str],
    count: SourceCount,
) -> list[_Pending]:
    """The finds of a source that may become candidates before Verify, new ones first (plan §14.1.2)."""
    folder = out / source.source_id
    repeated = _repeated(conn, source.source_id)
    pending: list[_Pending] = []
    for row in _rows(conn, source.source_id):
        stac = source.protocol is SourceProtocol.STAC_API
        files = [] if stac else declared_files(row.found)
        if not stac and not files:
            count.skipped["no_format"] += 1
            continue
        takeover = takeover_of(source.source_id, row.keys, repeated)
        if takeover is None:
            count.skipped["no_takeover"] += 1
            continue
        if set(row.keys) & full_keys:
            count.skipped["full_entry"] += 1
            continue
        match = licences.match(source.source_id, row.publisher, row.found.get("licence_statements") or ())
        if match.license is None or match.rule != row.license_rule:
            # The catalogue changed since the report: the next report decides the row again.
            count.skipped["licence_changed"] += 1
            continue
        if match.license.tier is LicenseTier.CATALOG:
            # adr/0031 §8: a licence in the catalogue tier keeps the entry listed (Otto, 25.11.2026: only K1 and K2).
            count.skipped["tier_catalog"] += 1
            continue
        path = folder / f"{row.dataset_id}.yaml"
        old = _read(path)
        proposed = old["proposed_id"] if old and isinstance(old.get("proposed_id"), str) else None
        if proposed is None:
            proposed = proposed_id(source, row.found, taken_ids)
        taken_ids.add(proposed)
        document = candidate_document(
            row, source, proposed=proposed, takeover=takeover, licence=match.license, refs=match.refs, day=day,
            trial=trial,
        )
        if old is not None:
            for key in _KEPT:
                document[key] = old.get(key, document[key])
            if old.get("onboarding"):
                document["onboarding"] = old["onboarding"]
            if _comparable(old) == _comparable(document):
                count.unchanged += 1
                continue
        pending.append(_Pending(row, document, path, old is None, files))
    pending.sort(key=lambda p: (not p.new, p.row.publisher or "", p.row.dataset_id))
    over = max(0, len(pending) - MAX_VERIFIED_PER_SOURCE)
    if over:
        count.skipped["budget"] += over
    return pending[:MAX_VERIFIED_PER_SOURCE]


async def _verify(
    pending: Sequence[_Pending],
    source: SourceConfig,
    *,
    hosts: Mapping[str, HostLimit],
    open_gateway: OpenGateway,
    run: ProposeRun,
) -> None:
    """Items of a STAC source, then the files of every pending candidate (plan §14.1.3)."""
    if source.protocol is SourceProtocol.STAC_API and pending:
        async with open_gateway(source_policy(source, hosts)) as gateway:
            for item in pending:
                item.items, item.item_reason = await fetch_items(gateway, source, item.row.source_key)
                hrefs: list[str] = []
                for feature in item.items:
                    for href in _data_assets(feature):
                        if href not in hrefs:
                            hrefs.append(href)
                            break
                item.files = hrefs[:MAX_FILES]
    wanted = {host for item in pending for href in item.files if (host := _host(href))}
    allowed = set()
    for host in sorted(wanted):
        if host in hosts or host in run.new_hosts:
            allowed.add(host)
        elif len(run.new_hosts) < MAX_NEW_HOSTS:
            run.new_hosts.add(host)
            allowed.add(host)
    if not allowed:
        for item in pending:
            item.checks = [FileCheck(href, "unchecked", "host_limit") for href in item.files]
        return
    async with open_gateway(file_policy(frozenset(allowed), hosts)) as gateway:
        for item in pending:
            for href in item.files:
                host = _host(href)
                if host is None or host not in allowed:
                    item.checks.append(FileCheck(href, "unchecked", "host_limit" if host else "bad_address"))
                else:
                    item.checks.append(await check_file(gateway, href))


def _outcome(item: _Pending) -> str:
    """``passed`` or why a find is no candidate after Verify."""
    if not item.files:
        return "no_items" if item.item_reason != "ok" else "no_format"
    if any(check.outcome == "account" for check in item.checks):
        return "account"
    if any(check.outcome == "passed" for check in item.checks):
        return "passed"
    return "verify_failed"


def _write(item: _Pending, *, day: date, trial: bool) -> dict[str, Any]:
    hosts = sorted({check.final_host or _host(check.href) or "" for check in item.checks if check.outcome == "passed"})
    verify = {
        "checked_on": day,
        "files": [check.to_document() for check in item.checks],
        "items": len(item.items),
        "account": "none",
        "data_region": data_region(hosts),
    }
    document = dict(item.document)
    document["verify"] = verify
    item.path.parent.mkdir(parents=True, exist_ok=True)
    item.path.write_text(dump_approval(clean_document(document)), encoding="utf-8")
    probe = item.path.with_name(f"{item.row.dataset_id}.probe.json")
    probe.write_text(probe_document(item.row, item.items, json.loads(json.dumps(verify, default=str))), encoding="utf-8")
    passed = next(check for check in item.checks if check.outcome == "passed")
    return {
        "listed_id": item.row.dataset_id,
        "proposed_id": document["proposed_id"],
        "title": document["harvested"]["title"],
        "format": (passed.format or {}).get("format"),
        "license": document["licence"]["license"]["spdx_id"] or document["licence"]["license"]["name"],
        "tier": document["licence"]["license"]["tier"],
        "decision": "cleared" if not trial else "trial",
        "new": item.new,
    }


def _update_states(conn: psycopg.Connection, source: SourceConfig, out: Path, count: SourceCount) -> None:
    """Candidates on disk whose listed row is no longer visible get its state; no request, no file deleted (A37)."""
    folder = out / source.source_id
    if not folder.is_dir():
        return
    paths = {path.stem: path for path in folder.glob("*.yaml")}
    states = _states(conn, list(paths))
    for listed_id, path in sorted(paths.items()):
        document = _read(path)
        if document is None:
            continue
        state = states.get(listed_id, "gone")
        if state != "published" and document.get("listed_state") != state:
            document["listed_state"] = state
            path.write_text(dump_approval(document), encoding="utf-8")
            count.state_updated += 1


def propose_source(
    conn: psycopg.Connection,
    source: SourceConfig,
    *,
    licences: LicenceCatalogue,
    hosts: Mapping[str, HostLimit],
    out: Path,
    day: date,
    trial: bool,
    open_gateway: OpenGateway,
    run: ProposeRun,
    full_keys: set[str],
    taken_ids: set[str],
) -> SourceCount:
    count = SourceCount()
    _update_states(conn, source, out, count)
    pending = _select(
        conn, source, licences=licences, out=out, day=day, trial=trial, full_keys=full_keys, taken_ids=taken_ids,
        count=count,
    )
    asyncio.run(_verify(pending, source, hosts=hosts, open_gateway=open_gateway, run=run))
    for item in pending:
        outcome = _outcome(item)
        if outcome != "passed":
            count.skipped[outcome] += 1
        elif len(count.written) >= MAX_PER_SOURCE:
            count.skipped["limit"] += 1
        else:
            count.written.append(_write(item, day=day, trial=trial))
            if item.new:
                count.new += 1
            else:
                count.changed += 1
    return count


def run_propose(
    conn: psycopg.Connection,
    sources: Sequence[SourceConfig],
    *,
    licences: LicenceCatalogue,
    hosts: Mapping[str, HostLimit],
    out: Path = CANDIDATES_DIR,
    day: date,
    trial: bool = False,
    open_gateway: OpenGateway = open_source_gateway,
) -> ProposeRun:
    """Propose the candidates of ``sources``; a source that fails is counted with its error, the others go on."""
    run = ProposeRun(trial)
    full_keys = _full_keys()
    taken = {config.dataset_id for config in registry()}
    taken |= {str(d.get("proposed_id")) for path in out.glob("*/*.yaml") if (d := _read(path)) and d.get("proposed_id")}
    for source in sources:
        try:
            run.sources[source.source_id] = propose_source(
                conn, source, licences=licences, hosts=hosts, out=out, day=day, trial=trial,
                open_gateway=open_gateway, run=run, full_keys=full_keys, taken_ids=taken,
            )
        except (GatewayError, psycopg.Error, OSError, yaml.YAMLError) as error:
            run.sources[source.source_id] = SourceCount(error=type(error).__name__)
    return run


_SKIPPED = {
    "no_format": "kein lesbares Format",
    "no_takeover": "nicht ablösbar",
    "full_entry": "schon voller Eintrag",
    "licence_changed": "Lizenz seit dem Bericht geändert",
    "tier_catalog": "Lizenzstufe catalog",
    "budget": "über dem Verify-Budget",
    "no_items": "keine Items",
    "account": "Konto",
    "verify_failed": "Verify gescheitert",
    "limit": "über der Grenze 20",
}


def summary_text(run: ProposeRun) -> str:
    """The run in German, one line a source."""
    lines = ["Kandidaten des vollen Wegs" + (" (Probelauf: nichts entschieden)" if run.trial else "")]
    for source_id, count in sorted(run.sources.items()):
        if count.error:
            lines.append(f"  {source_id}: gescheitert ({count.error})")
            continue
        skipped = ", ".join(f"{_SKIPPED.get(k, k)} {n}" for k, n in sorted(count.skipped.items())) or "–"
        lines.append(
            f"  {source_id}: neu {count.new}, geändert {count.changed}, unverändert {count.unchanged},"
            f" Zustand fortgeschrieben {count.state_updated}; übersprungen: {skipped}"
        )
    lines.append(f"  neue Datei-Hosts in diesem Lauf: {len(run.new_hosts)}")
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m earthx.discovery.propose", description=__doc__.splitlines()[0])
    parser.add_argument("sources", nargs="*", help="source ids (default: every enabled source)")
    parser.add_argument("--trial", action="store_true", help="the first harvest run: write, decide nothing")
    parser.add_argument("--out", type=Path, default=CANDIDATES_DIR, help="the folder of the candidates")
    parser.add_argument("--json", type=Path, default=None, help="also write the numbers as JSON (harvest cycle)")
    parser.add_argument("--day", type=date.fromisoformat, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    configure_logging()
    try:
        user_agent_from_env()
        known = read_sources()
        licences = load_licences(known)
        hosts = registry().host_limits
        unknown = [s for s in args.sources if s not in known]
        if unknown:
            raise ValueError(f"no source of that id: {', '.join(unknown)}")
        chosen = [known[s] for s in args.sources] if args.sources else [s for s in known.values() if s.enabled]
    except (ValueError, ConfigError, EntryFileError) as error:
        print(f"propose failed: {error}", file=sys.stderr)
        return 1
    try:
        with psycopg.connect(autocommit=True) as conn:
            run = run_propose(
                conn, chosen, licences=licences, hosts=hosts, out=args.out, day=args.day or date.today(),
                trial=args.trial,
            )
    except psycopg.Error as error:
        print(f"propose failed: database error {type(error).__name__}", file=sys.stderr)
        return 1
    if args.json is not None:
        args.json.write_text(json.dumps(run.numbers(), ensure_ascii=False, default=str), encoding="utf-8")
    print(summary_text(run))
    return 1 if run.sources and all(count.error for count in run.sources.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
