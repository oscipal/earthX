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

New and changed candidates are verified in an order that turns with the day (A46), in rounds until
:data:`MAX_PER_SOURCE` passed or :data:`MAX_VERIFIED_PER_SOURCE` were asked (A34). A candidate whose harvested part, licence and takeover are as
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
import hashlib
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
from earthx.catalog.entry_files import EntryFileError, dump_yaml
from earthx.catalog.hosts import HostLimit
from earthx.catalog.licences import LicenceCatalogue, load_licences
from earthx.catalog.registry import MAX_LISTING_IDENTIFIER_CHARS, ConfigError, LicenseInfo, LicenseTier
from earthx.catalog.sources import SourceConfig, SourceProtocol, read_sources
from earthx.discovery.cycle import SKIPPED_TEXT, clean
from earthx.discovery.dedupe import MAX_SHARED
from earthx.discovery.extract import _format_token
from earthx.discovery.harvest import source_policy
from earthx.discovery.links import url_parts
from earthx.discovery.probe import HEAD_BYTES, sniff
from earthx.discovery.report import _full_members
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


def readable_declared(format_: object, media_type: object) -> bool:
    """Whether a file says it is in a format a full entry reads, by its format or its media type."""
    if isinstance(format_, str) and format_ and _format_token(format_) in _FORMAT_TOKENS:
        return True
    return isinstance(media_type, str) and media_type.split(";", 1)[0].strip().lower().startswith(_MEDIA_TYPES)


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
    """The way a full entry takes over a row with ``keys``; ``repeated`` are the keys dedupe does not use (on more than
    one row of the source, where ``also_listed_as`` would take them all, or on more finds than ``dedupe.MAX_SHARED``).
    ``None`` where there is none (F17 = 1)."""
    keys = sorted(keys)
    repeated = set(repeated)
    for key in keys:
        if key.startswith("coll:"):
            return Takeover("coll", key)
    for key in keys:
        identifier = key[3:]
        # A key that ``clean`` would change (a mail or hash form) cannot stand in the public candidate file verbatim.
        if key.startswith("id:") and key not in repeated and _IDENTIFIER.fullmatch(identifier) and clean(key) == key:
            listing = f"{source_id}:{identifier}"
            return Takeover("also_listed_as", f"also:{listing}", (listing,))
    for key in keys:
        if key.startswith("doi:") and key not in repeated and clean(key) == key:
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


_DIGITS = re.compile(r"[0-9]{1,19}")


def _length(headers: Mapping[str, str]) -> int | None:
    total = headers.get("content-range", "").rsplit("/", 1)[-1].strip()
    if _DIGITS.fullmatch(total):
        return int(total)
    declared = headers.get("content-length", "").strip()
    return int(declared) if _DIGITS.fullmatch(declared) else None


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
    """``HEAD``, then ``GET`` of the first :data:`HEAD_BYTES` with ``Origin``; the format from the bytes. Whatever a
    foreign host sends, the result is a :class:`FileCheck`: an answer no rule foresaw is ``unchecked``, never an error
    that stops the run (review M5-20 PR 2)."""
    try:
        return await _check_file(gateway, href)
    except Exception as error:  # noqa: BLE001 - a foreign host must not stop the run; only the kind is kept
        return FileCheck(href, "unchecked", f"error_{type(error).__name__.lower()}"[:60])


async def _check_file(gateway: Gateway, href: str) -> FileCheck:
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
        # The host ignored Range and sends the whole file (or an error page larger than the limit): no partial reads,
        # so no full entry reads it. The status is not known: the size stops the read before it.
        return FileCheck(href, "failed", "no_range", partial=False)
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
        roles = asset.get("roles")
        data_role = isinstance(roles, (list, tuple)) and "data" in roles
        if readable_declared(None, asset.get("type")) or (data_role and asset.get("type") is None):
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
    except Exception:  # noqa: BLE001 - an answer of a foreign shape: no items, never an error that stops the run
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
    """The identifier and DOI keys of a source that dedupe does not use (``dedupe._usable``): on more than one row of
    the source, or on more than :data:`~earthx.discovery.dedupe.MAX_SHARED` rows of all sources."""
    with conn.cursor() as cur:
        cur.execute(
            "WITH k AS (SELECT key, source_id FROM public.earthx_listed_entry, unnest(dedupe_keys) AS key"
            " WHERE state NOT IN ('tombstone', 'superseded') AND (key LIKE 'id:%%' OR key LIKE 'doi:%%')"
            " AND key IN (SELECT unnest(dedupe_keys) FROM public.earthx_listed_entry WHERE source_id = %(source)s))"
            " SELECT key FROM k GROUP BY key"
            " HAVING count(*) FILTER (WHERE source_id = %(source)s) > 1 OR count(*) > %(shared)s",
            {"source": source_id, "shared": MAX_SHARED},
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


#: Fields a full entry takes over verbatim: never cleaned, or a key would no longer meet its row (review M5-20 PR 2).
_BINDING = frozenset({"source_id", "source_key", "listed_id", "proposed_id", "takeover"})
_CANDIDATE_HEAD = """\
# A candidate for a full entry (M5-20 plan §14.1; adr/0031 §4.4, §8), written by `discovery propose` in a harvest run.
# What was harvested, the proposed id and how the full entry takes over the listed row (`takeover`), the licence with
# its decision by rules (F15 = 1) and the result of Verify. The fields under `onboarding` are for the onboarding of the
# full entry. To take a candidate out, block its entry in backend/catalog/blocked.yaml; this file is never deleted.
"""


def dump_candidate(document: Mapping[str, Any]) -> str:
    """A candidate file: its head, then the fields, every text but the binding ones cleaned, no anchors."""
    cleaned = {key: value if key in _BINDING else clean_document(value) for key, value in document.items()}
    return _CANDIDATE_HEAD + dump_yaml(cleaned)


def _comparable(document: Mapping[str, Any]) -> dict[str, Any]:
    """A candidate as it is compared with the file on disk: as the file would hold it, without its days and Verify
    (A35). Through YAML and back, so that a text YAML reads differently (U+0085) does not count as a change."""
    found = {key: value for key, value in document.items() if key not in ("first_proposed", "verify", "onboarding")}
    licence = dict(found.get("licence") or {})
    licence.pop("decided_on", None)
    found["licence"] = licence
    return json.loads(json.dumps(yaml.safe_load(dump_candidate(found)), default=str, sort_keys=True))


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
    if len(text().encode("utf-8")) > MAX_PROBE_BYTES:
        # Still too large (large summaries or item assets): the head of the collection only.
        collection = {key: collection[key] for key in _PROBE_HEAD if key in collection}
        collection["description"] = str(collection.get("description") or "")[:2000]
    return text()


#: What a probe keeps of a collection that does not fit otherwise.
_PROBE_HEAD = ("type", "stac_version", "id", "title", "description", "license", "extent", "earthx:extent_basis")


class _Unreadable(Exception):
    """A candidate file on disk that is no YAML mapping (spoilt by hand): left alone and counted."""


def _read(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as error:
        raise _Unreadable(path.name) from error
    if not isinstance(document, dict):
        raise _Unreadable(path.name)
    return document


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
    """The finds of a source that may become candidates before Verify, new and changed ones in an order that turns
    with the day (A46): a find that fails Verify in every run does not keep the others from their turn."""
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
        try:
            old = _read(path)
        except _Unreadable:
            count.skipped["file_unreadable"] += 1
            continue
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
    pending.sort(key=lambda p: hashlib.sha256(f"{day.isoformat()} {p.row.dataset_id}".encode()).hexdigest())
    return pending


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
    item.path.write_text(dump_candidate(document), encoding="utf-8")
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
        try:
            document = _read(path)
        except _Unreadable:
            count.skipped["file_unreadable"] += 1
            continue
        if document is None:
            continue
        state = states.get(listed_id, "gone")
        if state != "published" and document.get("listed_state") != state:
            document["listed_state"] = state
            path.write_text(dump_candidate(document), encoding="utf-8")
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
    # In rounds, until 20 passed or 60 were asked (A34): no request for a find the run cannot write any more.
    verified = 0
    while pending and len(count.written) < MAX_PER_SOURCE and verified < MAX_VERIFIED_PER_SOURCE:
        size = min(MAX_PER_SOURCE - len(count.written), MAX_VERIFIED_PER_SOURCE - verified)
        batch, pending = pending[:size], pending[size:]
        verified += len(batch)
        asyncio.run(_verify(batch, source, hosts=hosts, open_gateway=open_gateway, run=run))
        for item in batch:
            outcome = _outcome(item)
            if outcome != "passed":
                count.skipped[outcome] += 1
            else:
                count.written.append(_write(item, day=day, trial=trial))
                if item.new:
                    count.new += 1
                else:
                    count.changed += 1
    if pending:
        count.skipped["limit" if len(count.written) >= MAX_PER_SOURCE else "budget"] += len(pending)
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
    for path in out.glob("*/*.yaml"):
        try:
            document = _read(path)
        except _Unreadable:
            continue
        if document and isinstance(document.get("proposed_id"), str):
            taken.add(document["proposed_id"])
    for source in sources:
        try:
            run.sources[source.source_id] = propose_source(
                conn, source, licences=licences, hosts=hosts, out=out, day=day, trial=trial,
                open_gateway=open_gateway, run=run, full_keys=full_keys, taken_ids=taken,
            )
        except psycopg.Error:
            raise
        except Exception as error:  # noqa: BLE001 - one source must not cost the others their candidates
            run.sources[source.source_id] = SourceCount(error=type(error).__name__)
    return run


def summary_text(run: ProposeRun) -> str:
    """The run in German, one line a source."""
    lines = ["Kandidaten des vollen Wegs" + (" (Probelauf: nichts entschieden)" if run.trial else "")]
    for source_id, count in sorted(run.sources.items()):
        if count.error:
            lines.append(f"  {source_id}: gescheitert ({count.error})")
            continue
        skipped = ", ".join(f"{SKIPPED_TEXT.get(k, k)} {n}" for k, n in sorted(count.skipped.items())) or "–"
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
