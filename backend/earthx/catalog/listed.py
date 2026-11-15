"""Listed entries: catalogue entries with a link, of any data kind, kept in Postgres (adr/0033, M5-40 plan §5.2).

A listed entry is no :class:`~earthx.catalog.registry.DatasetConfig`: it has no format, no capabilities, no viewer,
and it is never read into the registry of a process (M5-35 B5). It lives in ``earthx_listed_entry`` (migration
``021``); ``catalog-load`` writes the hand entries of ``backend/catalog/listed/`` there, and from M5-20 the harvest
writes the rest. This module holds what is read from files: the entry itself, the blocklist
``backend/catalog/blocked.yaml`` (adr/0033 §9) and the region outlines ``backend/catalog/regions.json``. All three are
read as strictly as the registry (``catalog.entry_files``), and an error names the file and the field, never a value.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import Enum
from functools import cache
from pathlib import Path
from typing import Any

from earthx.catalog.categories import Categories, load_categories
from earthx.catalog.collection import (
    SCIENTIFIC_EXTENSION,
    STAC_VERSION,
    _earthx_license_flags,
    _isoformat,
    _links,
    _providers,
    _scientific,
    _stac_license,
)
from earthx.catalog.datasets import CATALOG_DIR
from earthx.catalog.entry_files import EntryFileError, _validate, read_yaml
from earthx.catalog.glossary import normalize
from earthx.catalog.registry import (
    CATEGORY_ID,
    ENTRY_FILE_CONFIG,
    PROTOTYPE_PREFIX,
    AccountKind,
    ConfigError,
    LegalStatus,
    LicenseInfo,
    LicenseTier,
    Maturity,
    Provider,
    SpatialExtent,
    TemporalExtent,
    doi_name,
)

__all__ = [
    "BLOCKED_FILE",
    "HAND_SOURCE",
    "LISTED_DIR",
    "REGIONS_FILE",
    "BlockReason",
    "BlockRule",
    "BlockScope",
    "DataKind",
    "DeliveryKind",
    "ListedAccess",
    "ListedEntry",
    "Region",
    "content_sha256",
    "file_sha256",
    "link_host",
    "listed_keywords",
    "load_catalog_tags",
    "read_catalog_tags",
    "load_blocked",
    "load_listed",
    "load_regions",
    "sort_title",
    "to_listed_collection",
]

LISTED_DIR = CATALOG_DIR / "listed"
BLOCKED_FILE = CATALOG_DIR / "blocked.yaml"
REGIONS_FILE = CATALOG_DIR / "regions.json"
CATALOG_TAGS_FILE = CATALOG_DIR / "catalog_tags.yaml"
#: The ``source_id`` of a hand entry: its key at the source is its id (plan A3).
HAND_SOURCE = "listed"
_README = "README.md"
_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_HOST = re.compile(r"(?=.{1,253}\Z)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+")
_HTTPS_URL = re.compile(r"https://[^\s/?#]+(?:[/?#]\S*)?")
#: The host of an https address that ``_HTTPS_URL`` accepted: after ``https://``, before a port, path, query or
#: fragment, without user info. ``catalog`` parses no URL with a client library (KLAERUNGEN B8, `.importlinter`).
_URL_HOST = re.compile(r"https://(?:[^\s/?#@]*@)?(\[[^\]/]+\]|[^\s/?#:@]+)")


class DataKind(Enum):
    """What the data is (adr/0033 §5); a field of the entry, no group of the Data catalogue (M5-40 plan A8)."""

    RASTER = "raster"
    VECTOR = "vector"
    TABLE = "table"
    DOCUMENT = "document"
    SERVICE = "service"
    OTHER = "other"


class DeliveryKind(Enum):
    """How the source hands the data out (adr/0033 §5, adr/0027 §6.1 addendum); independent of the account."""

    DOWNLOAD = "download"
    SERVICE = "service"
    ORDER = "order"
    ON_REQUEST = "on_request"


@dataclass(frozen=True, slots=True)
class ListedAccess:
    """What getting the data needs: an account (with ``paid``) and the way of delivery. ``account_provider`` names the
    service an account is held at, as for a full entry (adr/0027 §6.1)."""

    account: AccountKind
    account_provider: str | None
    delivery: DeliveryKind


@dataclass(frozen=True, slots=True)
class ListedEntry:
    """One listed entry: the head of a full entry (adr/0025 §6.1a) plus data kind, delivery and the link to the source.

    ``source_url`` is the landing page at the source, the one link the catalogue offers. ``publisher`` is the
    organisation that publishes the data, as the source names it: what a blocklist line of scope ``publisher`` matches.
    ``approved_on`` is the day Otto released the entry: for a hand entry the day of its file (plan A3). The regions are
    derived from the extent when the entry is written, never read from a file. No field has a default (KLAERUNGEN B10).
    """

    dataset_id: str
    title: str
    description: str
    keywords: tuple[str, ...]
    providers: tuple[Provider, ...]
    publisher: str
    doi: str | None
    citation: str | None
    data_kind: DataKind
    category: str
    spatial_extent: SpatialExtent
    temporal_extent: TemporalExtent
    license: LicenseInfo
    legal_status: LegalStatus
    access: ListedAccess
    source_url: str
    maturity: Maturity
    approved_on: date

    def __post_init__(self) -> None:
        if not isinstance(self.dataset_id, str) or not _ID.fullmatch(self.dataset_id):
            raise ConfigError("a listed entry's id is lower-case letters, digits, '.', '_' and '-', at most 128")
        if self.dataset_id.startswith(PROTOTYPE_PREFIX):
            raise ConfigError(f"{self.dataset_id}: a listed entry is never a prototype (adr/0033 F8)")
        for name in ("title", "description", "publisher"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ConfigError(f"{self.dataset_id}: {name} is a non-blank text")
        if not isinstance(self.category, str) or not CATEGORY_ID.fullmatch(self.category):
            raise ConfigError(f"{self.dataset_id}: category is the id of a category of categories.yaml")
        if not self.keywords or not all(isinstance(word, str) and word.strip() for word in self.keywords):
            raise ConfigError(f"{self.dataset_id}: keywords names at least one keyword, each a non-blank text")
        if not self.providers:
            raise ConfigError(f"{self.dataset_id}: providers names no provider")
        try:
            doi_name(self.doi)
        except ConfigError as error:
            raise ConfigError(f"{self.dataset_id}: {error}") from None
        if self.license.tier is not LicenseTier.CATALOG:
            raise ConfigError(f"{self.dataset_id}: a listed entry has licence tier catalog (adr/0025 §6.1a)")
        if not (self.license.spdx_id or (self.license.name and self.license.url)):
            raise ConfigError(f"{self.dataset_id}: the licence needs an SPDX identifier or a name and a URL")
        if self.legal_status is not LegalStatus.CLEARED:
            raise ConfigError(f"{self.dataset_id}: a listed entry has legal_status cleared (adr/0033 F8)")
        if not _HTTPS_URL.fullmatch(self.source_url):
            raise ConfigError(f"{self.dataset_id}: source_url is an https address")
        provider = self.access.account_provider
        if provider is not None and not provider.strip():
            raise ConfigError(f"{self.dataset_id}: access.account_provider is a name or null")
        anonymous = self.access.account in (AccountKind.NONE, AccountKind.ANONYMOUS_TOKEN)
        if anonymous and provider is not None:
            raise ConfigError(
                f"{self.dataset_id}: access.account {self.access.account.value} names no account_provider"
            )
        if self.access.account is AccountKind.FREE_ACCOUNT and provider is None:
            raise ConfigError(f"{self.dataset_id}: access.account free_account names its account_provider")


class BlockScope(Enum):
    """What one line of the blocklist removes (adr/0033 §9)."""

    ENTRY = "entry"
    PUBLISHER = "publisher"
    HOST = "host"
    SOURCE = "source"


class BlockReason(Enum):
    """Why it is removed: a code, never the words or the name of whoever asked (adr/0033 §9; the repo is public)."""

    PROVIDER_REQUEST = "provider_request"
    NOT_GEODATA = "not_geodata"
    QUALITY = "quality"
    LEGAL = "legal"
    OTHER = "other"


#: The fields each scope names besides ``scope``, ``reason``, ``blocked_on`` and ``license_hash``.
_SCOPE_FIELDS = {
    BlockScope.ENTRY: frozenset({"source_id", "source_key"}),
    BlockScope.PUBLISHER: frozenset({"source_id", "publisher"}),
    BlockScope.HOST: frozenset({"host"}),
    BlockScope.SOURCE: frozenset({"source_id"}),
}
_SCOPED = ("source_id", "source_key", "publisher", "host")


@dataclass(frozen=True, slots=True)
class BlockRule:
    """One line of ``blocked.yaml``. There is no field for free text, so no name, address or wording of a request can
    go in (adr/0033 §9). ``license_hash`` is for M5-20: present the find again once its licence changes."""

    scope: BlockScope
    reason: BlockReason
    blocked_on: date
    source_id: str | None = None
    source_key: str | None = None
    publisher: str | None = None
    host: str | None = None
    license_hash: str | None = None

    def __post_init__(self) -> None:
        wanted = _SCOPE_FIELDS[self.scope]
        for name in _SCOPED:
            value = getattr(self, name)
            if (name in wanted) != (value is not None):
                need = "names" if name in wanted else "does not name"
                raise ConfigError(f"a line of scope {self.scope.value} {need} {name}")
            if value is not None and not value.strip():
                raise ConfigError(f"{name} is a non-blank text")
        if self.host is not None and not _HOST.fullmatch(self.host):
            raise ConfigError("host is a lower-case host name, without scheme, port or path")
        if self.license_hash is not None and not re.fullmatch(r"[0-9a-f]{64}", self.license_hash):
            raise ConfigError("license_hash is a SHA-256 in lower-case hex")

    @property
    def key(self) -> tuple[object, ...]:
        return (self.scope, self.source_id, self.source_key, self.publisher, self.host)


for _part in (ListedAccess, ListedEntry, BlockRule):
    _part.__pydantic_config__ = ENTRY_FILE_CONFIG  # type: ignore[attr-defined]
del _part


@dataclass(frozen=True, slots=True)
class Region:
    """A state (ISO 3166-1) or a subdivision (ISO 3166-2) and its outline as GeoJSON."""

    code: str
    level: str
    name: str
    outline: Mapping[str, Any]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_listed(directory: Path = LISTED_DIR) -> tuple[tuple[ListedEntry, str], ...]:
    """The hand entries of ``directory``, each with the SHA-256 of its file; an absent directory holds none.

    The file of an entry is ``<dataset_id>.yaml``; any other file but a README is an error, as under ``datasets/``.
    """
    if not directory.exists():
        return ()
    found = []
    for path in sorted(directory.iterdir()):
        if path.name == _README:
            continue
        if not path.is_file() or path.suffix != ".yaml":
            raise EntryFileError(f"{directory.name}/{path.name}: only <dataset_id>.yaml files and a README belong here")
        data = read_yaml(path)
        if not isinstance(data, Mapping):
            raise EntryFileError(f"{directory.name}/{path.name}: an entry is a mapping of its fields")
        entry = _validate(ListedEntry, data, f"{directory.name}/{path.name}")
        if path.name != f"{entry.dataset_id}.yaml":
            raise EntryFileError(f"{directory.name}/{path.name}: the file of an entry is named <dataset_id>.yaml")
        if entry.category not in load_categories().ids:
            raise EntryFileError(f"{directory.name}/{path.name}: category {entry.category} is not one of categories.yaml")
        found.append((entry, file_sha256(path)))
    return tuple(found)


def load_blocked(path: Path = BLOCKED_FILE) -> tuple[BlockRule, ...]:
    """The lines of the blocklist; an absent file blocks nothing. A line twice, or a day after ``today``, is an error."""
    if not path.exists():
        return ()
    data = read_yaml(path)
    if data is None:
        return ()
    if not isinstance(data, list):
        raise EntryFileError(f"{path.name}: the blocklist is a list")
    rules = tuple(_validate(BlockRule, item, f"{path.name}[{index}]") for index, item in enumerate(data))
    seen: set[tuple[object, ...]] = set()
    for index, rule in enumerate(rules):
        if rule.key in seen:
            raise EntryFileError(f"{path.name}[{index}]: the same line stands twice")
        seen.add(rule.key)
        if rule.blocked_on > date.today():
            raise EntryFileError(f"{path.name}[{index}]: blocked_on lies in the future")
    return rules


_REGION_KEYS = frozenset({"source", "release", "files", "script", "tolerance_deg", "regions"})
_REGION_FIELDS = frozenset({"code", "name", "level", "outline"})
_REGION_CODE = re.compile(r"[A-Z]{2}(-[A-Z0-9]{1,3})?")


def load_regions(path: Path = REGIONS_FILE) -> tuple[Region, ...]:
    """The regions of ``regions.json`` (written by ``scripts/write-region-outlines.py``), checked in shape."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EntryFileError(f"{path.name}: cannot be read as JSON ({type(error).__name__})") from None
    if not isinstance(data, dict) or set(data) != _REGION_KEYS or not isinstance(data["regions"], list):
        raise EntryFileError(f"{path.name}: holds exactly {', '.join(sorted(_REGION_KEYS))}")
    regions = []
    for index, item in enumerate(data["regions"]):
        if not isinstance(item, dict) or set(item) != _REGION_FIELDS:
            raise EntryFileError(f"{path.name}: regions[{index}] holds exactly {', '.join(sorted(_REGION_FIELDS))}")
        code, level = item["code"], item["level"]
        if not isinstance(code, str) or not _REGION_CODE.fullmatch(code):
            raise EntryFileError(f"{path.name}: regions[{index}].code is no ISO 3166 code")
        if level != ("state" if "-" not in code else "subdivision"):
            raise EntryFileError(f"{path.name}: regions[{index}].level does not match its code")
        outline = item["outline"]
        if not isinstance(outline, dict) or outline.get("type") not in ("Polygon", "MultiPolygon"):
            raise EntryFileError(f"{path.name}: regions[{index}].outline is a Polygon or MultiPolygon")
        regions.append(Region(code=code, level=level, name=str(item["name"]), outline=outline))
    if len({region.code for region in regions}) != len(regions):
        raise EntryFileError(f"{path.name}: a region code stands twice")
    return tuple(regions)


#: The longest keyword kept; a longer one is a sentence or a list, not a keyword.
MAX_KEYWORD_CHARS = 80
_LETTER = re.compile(r"[^\W\d_]")
_UUID = re.compile(r"[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}")
_HEX = re.compile(r"[0-9a-f]{16,}")
#: Words of a category's title that say nothing on their own.
_JOINING_WORDS = frozenset({"and"})


def _is_technical(keyword: str) -> bool:
    """A keyword that is an address, an identifier or no word at all (M5-40 plan A11): checked by its form only."""
    return (
        len(keyword) > MAX_KEYWORD_CHARS
        or _LETTER.search(keyword) is None
        or "://" in keyword
        or "@" in keyword
        or keyword.startswith("www.")
        or _UUID.fullmatch(keyword) is not None
        or _HEX.fullmatch(keyword) is not None
    )


def _normal_keyword(value: str) -> str:
    return " ".join(value.lower().split())


def read_catalog_tags(path: Path = CATALOG_TAGS_FILE) -> frozenset[str]:
    """The keywords about the catalogue rather than the data (``catalog_tags.yaml``), normalized like keywords.

    A list of non-blank texts, each once after normalization; an empty list is fine.
    """
    data = read_yaml(path)
    if data is None:
        return frozenset()
    if not isinstance(data, list):
        raise EntryFileError(f"{path.name}: the catalogue tags are a list")
    tags: set[str] = set()
    for index, value in enumerate(data):
        tag = _normal_keyword(value) if isinstance(value, str) else ""
        if not tag:
            raise EntryFileError(f"{path.name}[{index}]: a tag is a non-blank text")
        if tag in tags:
            raise EntryFileError(f"{path.name}[{index}]: {tag} stands twice")
        tags.add(tag)
    return frozenset(tags)


@cache
def load_catalog_tags() -> frozenset[str]:
    """The catalogue tags of the image, read once per process."""
    return read_catalog_tags()


def listed_keywords(
    raw: Iterable[object],
    category: str,
    categories: Categories | None = None,
    catalog_tags: frozenset[str] | None = None,
) -> tuple[str, ...]:
    """The keywords of a listed entry from those of its source (CKAN tags, DCAT keywords, INSPIRE keywords).

    Lower case, every run of white space one space, each once in the order the source gives them; empty and technical
    ones (:func:`_is_technical`) and the tags of ``catalog_tags.yaml`` are dropped. Where none is left, the words of the title of the entry's category in
    ``categories.yaml`` stand in, so that no entry is without keywords (Otto, 15.11.2026). Pure: the harvest calls it
    (M5-19), ``catalog-load`` for the hand entries.
    """
    catalog_tags = load_catalog_tags() if catalog_tags is None else catalog_tags
    kept: dict[str, None] = {}
    for value in (raw,) if isinstance(raw, str) else raw:
        if not isinstance(value, str):
            continue
        keyword = _normal_keyword(value)
        if keyword and keyword not in catalog_tags and not _is_technical(keyword):
            kept.setdefault(keyword, None)
    if kept:
        return tuple(kept)
    categories = load_categories() if categories is None else categories
    if category not in categories.titles:
        raise ConfigError(f"category {category!r} is not one of categories.yaml")
    words = (word.strip(",") for word in categories.titles[category].lower().split())
    return tuple(dict.fromkeys(word for word in words if word and word not in _JOINING_WORDS))


def sort_title(title: str) -> str:
    """The key of the order of the catalogue: the title in lower case, without accents, words joined by one space."""
    return normalize(title)


def link_host(url: str) -> str:
    """The host of the link to the source, in lower case: what a blocklist line of scope ``host`` matches."""
    match = _URL_HOST.match(url)
    if match is None:
        raise ConfigError("the link to the source has no host")
    return match.group(1).lower()


def to_listed_collection(entry: ListedEntry) -> dict[str, object]:
    """The STAC Collection of a listed entry as it is stored; ``api`` adds ``earthx:regions`` from the column when it
    serves it, so that a change of the region outlines needs no rewrite of the stored documents.

    No ``earthx:viewer``, no capabilities, no ``earthx:source``: nothing of the platform reads it (adr/0025 §6.1a).
    ``earthx:listing`` says where it comes from and since when it is approved (adr/0033 §10).
    """
    scientific = _scientific(entry)  # type: ignore[arg-type]
    collection: dict[str, object] = {
        "type": "Collection",
        "stac_version": STAC_VERSION,
        "stac_extensions": [SCIENTIFIC_EXTENSION] if scientific else [],
        "id": entry.dataset_id,
        "title": entry.title,
        "description": entry.description,
        # Normalized like the keywords of a harvested entry, and the same as the column (M5-40, Otto 15.11.2026).
        "keywords": list(listed_keywords(entry.keywords, entry.category)),
        "license": _stac_license(entry.license),
        "providers": _providers(entry),  # type: ignore[arg-type]
        "extent": {
            "spatial": {"bbox": [list(entry.spatial_extent.bbox)]},
            "temporal": {
                "interval": [[_isoformat(entry.temporal_extent.start), _isoformat(entry.temporal_extent.end)]]
            },
        },
        "links": [
            {"rel": "via", "href": entry.source_url, "title": "Source"},
            *_links(entry),  # type: ignore[arg-type]
        ],
        "earthx:entry": "listed",
        "earthx:data_kind": entry.data_kind.value,
        "earthx:category": entry.category,
        "earthx:license_flags": _earthx_license_flags(entry),  # type: ignore[arg-type]
        "earthx:legal_status": entry.legal_status.value,
        "earthx:legal_note": None,
        "earthx:access": {
            "account": entry.access.account.value,
            "account_provider": entry.access.account_provider,
            "delivery": entry.access.delivery.value,
        },
        "earthx:listing": {
            "source_url": entry.source_url,
            "publisher": entry.publisher,
            "approved_on": entry.approved_on.isoformat(),
        },
        "earthx:maturity": entry.maturity.value,
    }
    collection.update(scientific)
    return collection


def content_sha256(collection: Mapping[str, object]) -> str:
    """The hash of a collection's normal form: its JSON with sorted keys."""
    text = json.dumps(collection, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
