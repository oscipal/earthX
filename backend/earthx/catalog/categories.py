"""The categories of the Data catalogue and how an entry gets one (M5-40 plan §4b; G1-G6, Otto 15.11.2026).

``backend/catalog/categories.yaml`` holds the list of categories in the order of the groups, the tables from the INSPIRE
themes and the EU data themes of DCAT-AP to a category, and terms for CKAN groups and keywords. Full and listed
entries share the list: a full entry names its category under ``datasets/``, a hand entry under ``listed/``, and for a
harvested entry :func:`category_of` derives it from the metadata of the source (M5-19).

The file is read as strictly as the registry (``catalog.entry_files``); every code and every term stands at most once,
every category a table names is one of the list, and the INSPIRE and EU codes are the ones of the two vocabularies.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import earthx
from earthx.catalog.entry_files import EntryFileError, read_yaml
from earthx.catalog.glossary import normalize

__all__ = ["CATEGORIES_FILE", "OTHER", "Categories", "Evidence", "category_of", "load_categories"]

# The same place as `datasets.CATALOG_DIR`; not imported from there, because `datasets` reads this module.
CATEGORIES_FILE = Path(earthx.__file__).resolve().parents[1] / "catalog" / "categories.yaml"
#: The category of an entry nothing assigns; the last group of the Data catalogue.
OTHER = "other"
_ID = re.compile(r"[a-z][a-z_]{0,31}")

#: The 34 themes of the INSPIRE directive (2007/2/EC, annexes I-III), by the code of their URI
#: ``http://inspire.ec.europa.eu/theme/<code>``. Checked on 15.11.2026 against two mirrors of the register on GitHub
#: (the register itself is not reachable from the session; M5-40 plan §8).
INSPIRE_THEMES = frozenset(
    "ac ad af am au br bu cp ef el er ge gg gn hb hh hy lc lu mf mr nz of oi pd pf ps rs sd so sr su tn us".split()
)
#: The 14 codes of the EU data themes (``http://publications.europa.eu/resource/authority/data-theme/<CODE>``), checked
#: the same way.
EU_DATA_THEMES = frozenset("AGRI ECON EDUC ENER ENVI GOVE HEAL INTR JUST OP_DATPRO REGI SOCI TECH TRAN".split())
_KEYS = frozenset({"categories", "inspire", "eu_data_themes", "coarse_eu_data_themes", "terms"})
_CATEGORY_KEYS = frozenset({"id", "title", "search_text"})


@dataclass(frozen=True, slots=True)
class Categories:
    """The list of categories and the tables, as checked."""

    #: The ids in the order of the groups, ``other`` last.
    ids: tuple[str, ...]
    titles: Mapping[str, str]
    search_texts: Mapping[str, str]
    inspire: Mapping[str, str]
    eu_data_themes: Mapping[str, str]
    coarse_eu_data_themes: frozenset[str]
    #: Each term after :func:`~earthx.catalog.glossary.normalize`, to its category.
    terms: Mapping[str, str]

    def rank(self, category: str) -> int:
        return self.ids.index(category)


@dataclass(frozen=True, slots=True)
class Evidence:
    """What the metadata of a source say about the subject of an entry: theme URIs or codes, CKAN groups, keywords."""

    inspire_themes: tuple[str, ...] = ()
    eu_data_themes: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()


def _bad(path: Path, where: str, problem: str) -> EntryFileError:
    return EntryFileError(f"{path.name}: {where}: {problem}")


def _table(path: Path, data: Any, name: str, ids: tuple[str, ...], known: frozenset[str]) -> dict[str, str]:
    """``{category: [code, ...]}`` as ``{code: category}``; every code known and at most once."""
    if not isinstance(data, dict):
        raise _bad(path, name, "a mapping of category to codes")
    table: dict[str, str] = {}
    for category, codes in data.items():
        if category not in ids:
            raise _bad(path, name, f"{category!r} is no category of the list")
        if not isinstance(codes, list) or not codes:
            raise _bad(path, f"{name}.{category}", "a list of at least one code")
        for code in codes:
            if not isinstance(code, str) or code not in known:
                raise _bad(path, f"{name}.{category}", f"{code!r} is no code of the vocabulary")
            if code in table:
                raise _bad(path, f"{name}.{category}", f"{code} stands twice")
            table[code] = category
    return table


def read_categories(path: Path = CATEGORIES_FILE) -> Categories:
    """The categories of ``path``, checked; any problem is an :class:`EntryFileError` naming the place."""
    data = read_yaml(path)
    if not isinstance(data, dict) or set(data) != _KEYS:
        raise EntryFileError(f"{path.name}: holds exactly {', '.join(sorted(_KEYS))}")
    entries = data["categories"]
    if not isinstance(entries, list) or not entries:
        raise _bad(path, "categories", "a list of at least one category")
    ids: list[str] = []
    titles: dict[str, str] = {}
    texts: dict[str, str] = {}
    for index, entry in enumerate(entries):
        where = f"categories[{index}]"
        if not isinstance(entry, dict) or set(entry) != _CATEGORY_KEYS:
            raise _bad(path, where, f"holds exactly {', '.join(sorted(_CATEGORY_KEYS))}")
        category, title, text = entry["id"], entry["title"], entry["search_text"]
        if not isinstance(category, str) or not _ID.fullmatch(category):
            raise _bad(path, where, "id is lower-case letters and '_'")
        if category in titles:
            raise _bad(path, where, f"{category} stands twice")
        if not isinstance(title, str) or not title.strip():
            raise _bad(path, where, "title is a non-blank text")
        if not isinstance(text, str):
            raise _bad(path, where, "search_text is a text")
        ids.append(category)
        titles[category] = title
        texts[category] = text
    if ids[-1] != OTHER:
        raise _bad(path, "categories", f"{OTHER} is the last category")
    order = tuple(ids)
    inspire = _table(path, data["inspire"], "inspire", order, INSPIRE_THEMES)
    eu = _table(path, data["eu_data_themes"], "eu_data_themes", order, EU_DATA_THEMES)
    coarse = data["coarse_eu_data_themes"]
    if not isinstance(coarse, list) or not all(isinstance(code, str) and code in eu for code in coarse):
        raise _bad(path, "coarse_eu_data_themes", "a list of codes of eu_data_themes")
    terms: dict[str, str] = {}
    if not isinstance(data["terms"], dict):
        raise _bad(path, "terms", "a mapping of category to terms")
    for category, words in data["terms"].items():
        if category not in order or category == OTHER:
            raise _bad(path, "terms", f"{category!r} is no category of the list other than {OTHER}")
        if not isinstance(words, list) or not words:
            raise _bad(path, f"terms.{category}", "a list of at least one term")
        for word in words:
            term = normalize(word) if isinstance(word, str) else ""
            if not term:
                raise _bad(path, f"terms.{category}", f"{word!r} is no term")
            if term in terms:
                raise _bad(path, f"terms.{category}", f"{word!r} stands twice")
            terms[term] = category
    return Categories(order, titles, texts, inspire, eu, frozenset(coarse), terms)


@cache
def load_categories() -> Categories:
    """The categories of the image, read once per process."""
    return read_categories()


def _code(value: str) -> str:
    """The code of a theme URI (``…/theme/hy``, ``…/data-theme/ENVI``), or the value itself where it is a code."""
    return value.strip().rstrip("/").rsplit("/", 1)[-1]


def _best(categories: Categories, found: Iterable[str]) -> str | None:
    """The highest category of the list among ``found``, ``other`` not counted."""
    ranked = sorted((categories.rank(c), c) for c in set(found) if c != OTHER)
    return ranked[0][1] if ranked else None


def _by_terms(categories: Categories, values: Iterable[str]) -> str | None:
    """The category the terms give for ``values``: a term counts where its words stand as whole words in a value."""
    found = []
    for value in values:
        padded = f" {normalize(value)} "
        found += [category for term, category in categories.terms.items() if f" {term} " in padded]
    return _best(categories, found)


def category_of(evidence: Evidence, categories: Categories | None = None) -> str:
    """The category of an entry from the metadata of its source, by the rule of ``categories.yaml`` (G3 = 1).

    INSPIRE theme, then EU data theme, then CKAN group, then keyword: the first that gives a category other than
    ``other`` decides, the highest of the list where one kind gives several. A coarse EU data theme gives way to a
    group or a keyword. Nothing matches: ``other``.
    """
    categories = load_categories() if categories is None else categories
    inspire = _best(categories, (categories.inspire.get(_code(v), OTHER) for v in evidence.inspire_themes))
    if inspire is not None:
        return inspire
    eu_codes = [_code(v) for v in evidence.eu_data_themes]
    precise = _best(
        categories,
        (categories.eu_data_themes.get(c, OTHER) for c in eu_codes if c not in categories.coarse_eu_data_themes),
    )
    if precise is not None:
        return precise
    by_terms = _by_terms(categories, evidence.groups) or _by_terms(categories, evidence.keywords)
    if by_terms is not None:
        return by_terms
    coarse = _best(categories, (categories.eu_data_themes.get(c, OTHER) for c in eu_codes))
    return coarse if coarse is not None else OTHER
