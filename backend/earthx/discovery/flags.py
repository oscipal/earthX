"""Warning signs on a harvested find (M5-67; docs/plans/m5/m5-67-harvest-automatisch.md §5; adr/0033 §8.5).

A find of a stack with a warning sign stays out of the sample and out of the approval (``excluded_entries``): it waits
in review and stands in the list of findings, so that "im Zweifel wartet ein Fund" (Otto, 24.11.2026). The words live
in ``backend/catalog/flags.yaml`` and, for W1 and W2, in ``geodata.yaml``; a warning Otto cleared for an entry is
passed over. Pure: no database, no request.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

from earthx.catalog.categories import load_categories
from earthx.catalog.datasets import CATALOG_DIR
from earthx.catalog.entry_files import EntryFileError, read_yaml
from earthx.catalog.glossary import normalize
from earthx.discovery.geodata import GeodataRule, Terms, parse_terms
from earthx.discovery.links import is_collection_page, url_parts

__all__ = ["CODES", "FLAGS_FILE", "Flag", "FlagEntry", "FlagRules", "flags_of", "load_flag_rules", "read_flag_rules"]

FLAGS_FILE = CATALOG_DIR / "flags.yaml"
CODES = ("W1", "W2", "W3", "W4", "W5", "W6", "W7")
_KEYS = frozenset(
    {
        "statistics_words",
        "general_pages",
        "imagery_categories",
        "imagery_kinds",
        "copy_words",
        "min_title_chars",
        "file_endings",
        "cleared",
    }
)
_KINDS = frozenset({"raster", "vector", "table", "document", "service", "other"})
_MAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# An international number or one after "Tel"/"Telefon"/"phone": at least 8 digits in a run of digits and separators.
_PHONE = re.compile(r"(?:\+|\b00)\d[\d ()/.-]{7,}\d|\b(?:tel|telefon|phone|fon)\.?:?\s*\+?\d[\d ()/.-]{6,}\d", re.I)
_DATASET_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")


@dataclass(frozen=True, slots=True)
class FlagRules:
    statistics_words: Terms
    general_pages: frozenset[str]
    imagery_categories: frozenset[str]
    imagery_kinds: frozenset[str]
    copy_words: Terms
    min_title_chars: int
    file_endings: frozenset[str]
    cleared: frozenset[tuple[str, str]]


def _list(path: Path, data: Mapping[str, object], key: str) -> list:  # type: ignore[type-arg]
    value = data[key]
    if not isinstance(value, list):
        raise EntryFileError(f"{path.name}: {key} is a list")
    return value


def _is_day(value: object) -> bool:
    if isinstance(value, date):
        return True
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _cleared(path: Path, values: list) -> frozenset[tuple[str, str]]:  # type: ignore[type-arg]
    found = set()
    for item in values:
        if (
            not isinstance(item, dict)
            or set(item) != {"dataset_id", "code", "cleared_on"}
            or not isinstance(item["dataset_id"], str)
            or not _DATASET_ID.fullmatch(item["dataset_id"])
            or item["code"] not in CODES
            or not _is_day(item["cleared_on"])
        ):
            raise EntryFileError(f"{path.name}: cleared holds dataset_id, code (W1-W7) and cleared_on (a day)")
        found.add((item["dataset_id"], item["code"]))
    return frozenset(found)


def read_flag_rules(path: Path) -> FlagRules:
    data = read_yaml(path)
    if not isinstance(data, dict) or set(data) != _KEYS:
        raise EntryFileError(f"{path.name}: holds exactly {', '.join(sorted(_KEYS))}")
    categories = set(load_categories().ids)
    imagery = set(_list(path, data, "imagery_categories"))
    if not imagery <= categories:
        raise EntryFileError(f"{path.name}: imagery_categories names categories of categories.yaml only")
    kinds = set(_list(path, data, "imagery_kinds"))
    if not kinds <= _KINDS:
        raise EntryFileError(f"{path.name}: imagery_kinds names data kinds of the extract only")
    minimum = data["min_title_chars"]
    if isinstance(minimum, bool) or not isinstance(minimum, int) or not 1 <= minimum <= 40:
        raise EntryFileError(f"{path.name}: min_title_chars is a whole number from 1 to 40")
    words = {key: [str(v) for v in _list(path, data, key)] for key in ("general_pages", "file_endings")}
    if not all(w and " " not in w and normalize(w) == w.lower() for values in words.values() for w in values):
        raise EntryFileError(f"{path.name}: general_pages and file_endings hold single plain words")
    return FlagRules(
        statistics_words=parse_terms(_list(path, data, "statistics_words"), "statistics_words", path.name),
        general_pages=frozenset(w.lower() for w in words["general_pages"]),
        imagery_categories=frozenset(imagery),
        imagery_kinds=frozenset(kinds),
        copy_words=parse_terms(_list(path, data, "copy_words"), "copy_words", path.name),
        min_title_chars=minimum,
        file_endings=frozenset(w.lower() for w in words["file_endings"]),
        cleared=_cleared(path, _list(path, data, "cleared")),
    )


@cache
def load_flag_rules() -> FlagRules:
    return read_flag_rules(FLAGS_FILE)


@dataclass(frozen=True, slots=True)
class FlagEntry:
    """What the warning signs look at: an entry of a stack as the report wrote it."""

    dataset_id: str
    title: str
    description: str
    keywords: tuple[str, ...]
    publisher: str
    category: str
    data_kind: str
    link: str


@dataclass(frozen=True, slots=True)
class Flag:
    code: str
    #: What gave it: the word, the category or a short code; never a mail address or a number from the text.
    why: str


def _general_page(link: str, rules: FlagRules) -> str | None:
    if is_collection_page(link):
        return "page_of_provider"
    parts = url_parts(link)
    # A query or a fragment names the page among its siblings (a STAC browser's "#/collections/<id>").
    if parts is None or parts[2] or len(parts[3]) > 2:
        return None
    last = next((p for p in reversed(parts[1].split("/")) if p), "")
    stem = last.rsplit(".", 1)[0].lower() if "." in last else last.lower()
    return stem if stem in rules.general_pages else None


def flags_of(entry: FlagEntry, rules: FlagRules, geodata: GeodataRule) -> tuple[Flag, ...]:
    """The warning signs of ``entry``, by code; those Otto cleared for it are left out."""
    found: list[Flag] = []
    title = entry.title or ""
    words = geodata.not_geo_terms.found([title]) + geodata.software_terms.found([title])
    words += rules.statistics_words.found([title])
    if words:
        found.append(Flag("W1", words[0]))
    publisher = geodata.not_geo_publishers.found([entry.publisher]) + geodata.statistics_publishers.found(
        [entry.publisher]
    )
    if publisher:
        found.append(Flag("W2", publisher[0]))
    page = _general_page(entry.link, rules)
    if page is not None:
        found.append(Flag("W3", page))
    if entry.category in rules.imagery_categories and entry.data_kind not in rules.imagery_kinds:
        found.append(Flag("W4", f"{entry.category}/{entry.data_kind}"))
    copy = rules.copy_words.found([title])
    if copy:
        found.append(Flag("W5", copy[0]))
    text = f"{title}\n{entry.description}"
    if _MAIL.search(text):
        found.append(Flag("W6", "mail"))
    elif _PHONE.search(text):
        found.append(Flag("W6", "phone"))
    plain = normalize(title).replace(" ", "")
    ending = title.strip().rsplit(".", 1)[-1].lower() if "." in title.strip() else ""
    if len(plain) < rules.min_title_chars:
        found.append(Flag("W7", "short"))
    elif ending in rules.file_endings and " " not in title.strip():
        found.append(Flag("W7", f"file:{ending}"))
    return tuple(f for f in found if (entry.dataset_id, f.code) not in rules.cleared)
