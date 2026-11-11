"""The search text of a dataset, in four weighted parts (adr/0026 §4.1; M5-22 plan §3.2).

| weight | content |
|---|---|
| A | id, title |
| B | keywords, place names from the extent (F4), the group of the Data catalogue |
| C | description |
| D | bands with their unit, the quick processings, "true color", the data class, the providers, the access, the terms
  of each capability the dataset offers (F5) |

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
from earthx.catalog.entry_files import EntryFileError, read_yaml
from earthx.catalog.glossary import normalize
from earthx.catalog.places import Places, place_terms
from earthx.catalog.registry import AccountKind, Capabilities, ConfigError, DataClass, DatasetCategory, DatasetConfig

#: Raised whenever the way the text is built changes, so every row of the index is rewritten.
SEARCH_TEXT_VERSION = 1

CAPABILITY_TERMS_FILE = Path(earthx.__file__).resolve().parents[1] / "catalog" / "capability_terms.yaml"

#: The names of the groups as the Data catalogue shows them (``frontend/src/catalogue.ts``).
CATEGORY_NAMES = {
    DatasetCategory.OPTICAL: "optical",
    DatasetCategory.RADAR: "radar",
    DatasetCategory.ELEVATION: "elevation",
    DatasetCategory.LAND_COVER: "land cover",
    DatasetCategory.WEATHER_CLIMATE: "weather and climate",
}
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
    config: DatasetConfig, *, places: Places | None = None, terms: CapabilityTerms | None = None
) -> SearchText:
    """The search text of ``config``."""
    terms = capability_terms() if terms is None else terms
    bands = [
        key.replace("*", " ") if unit in (None, _DIMENSIONLESS) else f"{key.replace('*', ' ')} {unit}"
        for key, unit in config.band_units.items()
        if key not in config.auxiliary_assets
    ]
    presets = [f"{preset.name} {preset.title}" for preset in config.index_presets]
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
            CATEGORY_NAMES[config.category],
        ),
        c=config.description,
        d=_lines(
            *bands,
            *presets,
            TRUE_COLOR_WORDS if config.true_color else "",
            DATA_CLASS_WORDS[config.data_class],
            *(provider.name for provider in config.providers),
            ACCESS_WORDS.get(config.access.account, ""),
            *offered,
        ),
        trigram_text=" ".join(
            dict.fromkeys(normalize(" ".join((config.dataset_id, config.title, *config.keywords))).split())
        ),
    )
