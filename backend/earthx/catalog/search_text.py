"""The search text of a dataset, in four weighted parts (adr/0026 §4.1; M5-22 plan §3.2).

| weight | content |
|---|---|
| A | id, title |
| B | keywords, place names from the extent (F4), the group of the Data catalogue |
| C | description |
| D | bands with their unit, the quick processings, "true color", the data class, the providers, the access, the terms
  of each capability the dataset offers (F5) |

A listed entry (:func:`listed_search_text`) has the same four parts from the fields of its row: the titles of its
duplicates next to its own on A, so that a word only a duplicate's title has finds the main entry; the names its
regions have in ``place_names.yaml`` (German, English, French, Italian) as its place names on B; its publisher and
access on D.

Keywords are on B, not on A as the ADR has it (plan A1, Otto 11.11.2026): WorldCover names ``sentinel-2`` among its
keywords and would otherwise tie with Sentinel-2 for "Sentinel-2". What a dataset cannot do is not in its text: only
its own quick processings, only the terms of capabilities it offers, never a general operator every dataset has.

:attr:`SearchText.text_hash` covers the four parts and :data:`SEARCH_TEXT_VERSION`; ``catalog-load`` rewrites a row of
the index when it changes, and `api` refuses to start on an index whose hashes differ from its own (plan A3).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, fields
from functools import cache
from pathlib import Path

import earthx
from earthx.catalog.categories import Categories, load_categories
from earthx.catalog.entry_files import EntryFileError, read_yaml
from earthx.catalog.glossary import normalize
from earthx.catalog.places import Places, place_terms
from earthx.catalog.registry import AccountKind, Capabilities, ConfigError, DataClass, DatasetConfig

#: Raised whenever the way the text is built changes, so every row of the index is rewritten.
SEARCH_TEXT_VERSION = 1

CAPABILITY_TERMS_FILE = Path(earthx.__file__).resolve().parents[1] / "catalog" / "capability_terms.yaml"
#: The names of the regions (M5-20, F2 = 1); the search reads only its section ``places``.
PLACE_NAMES_FILE = CAPABILITY_TERMS_FILE.with_name("place_names.yaml")

DATA_CLASS_WORDS = {DataClass.RASTER_TIME_SERIES: "raster time series", DataClass.RASTER_STATIC: "static raster"}
#: Only what a user has to know before choosing: no words where the data is open.
ACCESS_WORDS = {AccountKind.FREE_ACCOUNT: "free account required", AccountKind.REQUESTER_PAYS: "requester pays"}
TRUE_COLOR_WORDS = "true color"
#: A unit that says nothing about the band ("1" for reflectance and indices).
_DIMENSIONLESS = "1"

_CAPABILITY_NAMES = frozenset(field.name for field in fields(Capabilities))


@dataclass(frozen=True, slots=True)
class CapabilityTerms:
    #: Capabilities of the general operators: in no text.
    general: frozenset[str]
    #: Terms per dataset-specific capability.
    terms: Mapping[str, tuple[str, ...]]


def load_capability_terms(path: Path = CAPABILITY_TERMS_FILE) -> CapabilityTerms:
    """The terms in ``path``, checked; :class:`ConfigError` names the file and what is wrong."""
    try:
        data = read_yaml(path)
    except EntryFileError as error:
        raise ConfigError(str(error)) from None
    if not isinstance(data, dict) or set(data) != {"general", "terms"}:
        raise ConfigError(f"{path.name}: has exactly the keys 'general' and 'terms'")
    general, terms = data["general"], data["terms"]
    if not isinstance(general, list) or not all(isinstance(name, str) for name in general):
        raise ConfigError(f"{path.name}: 'general' is a list of capability names")
    if not isinstance(terms, dict):
        raise ConfigError(f"{path.name}: 'terms' maps a capability to its terms")
    for name in [*general, *terms]:
        if name not in _CAPABILITY_NAMES:
            raise ConfigError(f"{path.name}: {name!r} is no capability of an entry")
    if len(set(general)) != len(general) or set(general) & set(terms):
        raise ConfigError(f"{path.name}: each capability is named once, under 'general' or under 'terms'")
    for name, words in terms.items():
        if (
            not isinstance(words, list)
            or not words
            or not all(isinstance(word, str) and normalize(word) for word in words)
            or len({normalize(word) for word in words}) != len(words)
        ):
            raise ConfigError(f"{path.name}: the terms of {name!r} are a list of different, non-empty texts")
    return CapabilityTerms(frozenset(general), {name: tuple(words) for name, words in terms.items()})


@cache
def capability_terms() -> CapabilityTerms:
    """The capability terms of this process, read once."""
    return load_capability_terms()


@dataclass(frozen=True, slots=True)
class SearchText:
    dataset_id: str
    a: str
    b: str
    c: str
    d: str
    #: Id, title and keywords, normalized: what the trigram arm compares a query with.
    trigram_text: str

    @property
    def text_hash(self) -> str:
        """SHA-256 over the version of the text and its four parts (M5-23 adds the model)."""
        payload = json.dumps([SEARCH_TEXT_VERSION, self.a, self.b, self.c, self.d], ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _lines(*parts: str) -> str:
    """The non-empty parts, one per line, each once (a keyword that is also a place name, or the group's name)."""
    unique: dict[str, str] = {}
    for part in parts:
        if normalize(part):
            unique.setdefault(normalize(part), part)
    return "\n".join(unique.values())


def search_text(
    config: DatasetConfig,
    *,
    places: Places | None = None,
    terms: CapabilityTerms | None = None,
    categories: Categories | None = None,
) -> SearchText:
    """The search text of ``config``; the words of its category are the ``search_text`` of ``categories.yaml``."""
    terms = capability_terms() if terms is None else terms
    categories = load_categories() if categories is None else categories
    bands = [
        key.replace("*", " ") if unit in (None, _DIMENSIONLESS) else f"{key.replace('*', ' ')} {unit}"
        for key, unit in config.band_units.items()
        if key not in config.auxiliary_assets
    ]
    presets = [
        f"{preset.name} {preset.title}"
        for preset in (*config.index_presets, *config.composite_presets, *config.step_presets)
    ]
    offered = [
        word
        for capability, words in terms.terms.items()
        if getattr(config.capabilities, capability) is True
        for word in words
    ]
    return SearchText(
        dataset_id=config.dataset_id,
        a=_lines(config.dataset_id, config.title),
        b=_lines(
            *config.keywords,
            *place_terms(config.spatial_extent.bbox, places),
            categories.search_texts.get(config.category, ""),
        ),
        c=config.description,
        d=_lines(
            *bands,
            *presets,
            *(row.name for classes in config.band_classes.values() for row in classes.classes),
            TRUE_COLOR_WORDS if config.true_color else "",
            DATA_CLASS_WORDS[config.data_class],
            *(provider.name for provider in config.providers),
            ACCESS_WORDS.get(config.access.account, ""),
            *offered,
        ),
        trigram_text=" ".join(
            dict.fromkeys(
                normalize(part) for part in (config.dataset_id, config.title, *config.keywords) if normalize(part)
            )
        ),
    )


@dataclass(frozen=True, slots=True)
class ListedFields:
    """What the search text of a published listed entry is built from: fields of its row in ``earthx_listed_entry``."""

    dataset_id: str
    title: str
    description: str
    keywords: tuple[str, ...]
    category: str
    publisher: str
    account: str
    region_names: tuple[str, ...]
    duplicate_titles: tuple[str, ...]


def listed_search_text(entry: ListedFields, *, categories: Categories | None = None) -> SearchText:
    """The search text of a listed entry, in the parts of :func:`search_text`."""
    categories = load_categories() if categories is None else categories
    titles = (entry.title, *entry.duplicate_titles)
    return SearchText(
        dataset_id=entry.dataset_id,
        a=_lines(entry.dataset_id, *titles),
        b=_lines(*entry.keywords, *entry.region_names, categories.search_texts.get(entry.category, "")),
        c=entry.description,
        d=_lines(entry.publisher, ACCESS_WORDS.get(AccountKind(entry.account), "")),
        trigram_text=" ".join(
            dict.fromkeys(normalize(part) for part in (entry.dataset_id, *titles, *entry.keywords) if normalize(part))
        ),
    )


def read_region_names(path: Path = PLACE_NAMES_FILE) -> dict[str, tuple[str, ...]]:
    """The names of each region code in the section ``places`` of ``path``; :class:`ConfigError` where it is malformed."""
    try:
        data = read_yaml(path)
    except EntryFileError as error:
        raise ConfigError(str(error)) from None
    places = data.get("places") if isinstance(data, dict) else None
    if not isinstance(places, dict) or not all(
        isinstance(code, str) and isinstance(names, list) and all(isinstance(n, str) and n for n in names)
        for code, names in places.items()
    ):
        raise ConfigError(f"{path.name}: 'places' maps a region code to a list of names")
    return {code: tuple(names) for code, names in places.items()}


@cache
def region_names() -> dict[str, tuple[str, ...]]:
    """The names of the regions for this process, read once."""
    return read_region_names()


def listed_text_salt() -> str:
    """What every search text of a listed entry depends on besides its row: when it changes, every row is rebuilt."""
    payload = json.dumps(
        [SEARCH_TEXT_VERSION, sorted(region_names().items()), sorted(load_categories().search_texts.items())],
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
