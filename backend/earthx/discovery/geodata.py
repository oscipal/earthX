"""The rule R-G: whether a harvested find is no geodata (M5-20 plan §7, §13b; F3 = 1).

A find is ``not_geodata`` only where it has no geo signal and at least one non-geo signal; with neither it counts as
geodata ("undecided" in the classification, so that ``report --classify`` can show the borderline cases). The signals
and the words live in ``backend/catalog/geodata.yaml``; the code only reads them. Pure: no database, no request.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from earthx.catalog.categories import load_categories
from earthx.catalog.datasets import CATALOG_DIR
from earthx.catalog.entry_files import EntryFileError, read_yaml
from earthx.catalog.glossary import normalize
from earthx.discovery.enrich import Extent, region_boxes
from earthx.discovery.extract import resource_kind

__all__ = ["GEODATA_FILE", "Classified", "GeodataRule", "classify", "load_geodata_rule", "read_geodata_rule"]

GEODATA_FILE = CATALOG_DIR / "geodata.yaml"
_KEYS = frozenset(
    {"geo_data_kinds", "geo_categories", "extent_share_below", "geo_terms", "not_geo_eu_themes", "not_geo_terms"}
)
_DATA_KINDS = frozenset({"raster", "vector", "table", "document", "service", "other"})
_EU_THEME = re.compile(r"[A-Z_]{2,12}")


@dataclass(frozen=True, slots=True)
class Terms:
    """Words to look for: whole word sequences, word ends (``*x``) and word starts (``x*``), all normal."""

    sequences: tuple[tuple[str, ...], ...]
    ends: tuple[str, ...]
    starts: tuple[str, ...]

    def found(self, texts: Iterable[str]) -> list[str]:
        hits = []
        for text in texts:
            words = normalize(text).split()
            for sequence in self.sequences:
                size = len(sequence)
                if any(tuple(words[i : i + size]) == sequence for i in range(len(words) - size + 1)):
                    hits.append(" ".join(sequence))
            hits += [f"*{end}" for end in self.ends if any(w.endswith(end) for w in words)]
            hits += [f"{start}*" for start in self.starts if any(w.startswith(start) for w in words)]
        return hits


def _terms(values: list[str], where: str) -> Terms:
    sequences, ends, starts = [], [], []
    for value in values:
        if not isinstance(value, str) or not normalize(value.strip("*")):
            raise EntryFileError(f"{GEODATA_FILE.name}: {where} holds non-blank words")
        normal = normalize(value.strip("*"))
        if value.startswith("*") or value.endswith("*"):
            if " " in normal or (value.startswith("*") and value.endswith("*")):
                raise EntryFileError(f"{GEODATA_FILE.name}: {where}: '*' stands at one end of one word")
            (ends if value.startswith("*") else starts).append(normal)
        else:
            sequences.append(tuple(normal.split()))
    return Terms(tuple(dict.fromkeys(sequences)), tuple(dict.fromkeys(ends)), tuple(dict.fromkeys(starts)))


@dataclass(frozen=True, slots=True)
class GeodataRule:
    geo_data_kinds: frozenset[str]
    geo_categories: frozenset[str]
    extent_share_below: float
    geo_terms: Terms
    not_geo_eu_themes: frozenset[str]
    not_geo_terms: Terms


def read_geodata_rule(path: Path) -> GeodataRule:
    data = read_yaml(path)
    if not isinstance(data, dict) or set(data) != _KEYS:
        raise EntryFileError(f"{path.name}: holds exactly {', '.join(sorted(_KEYS))}")
    for key in _KEYS - {"extent_share_below"}:
        if not isinstance(data[key], list):
            raise EntryFileError(f"{path.name}: {key} is a list")
    if not set(data["geo_data_kinds"]) <= _DATA_KINDS:
        raise EntryFileError(f"{path.name}: geo_data_kinds names data kinds of the extract only")
    if not set(data["geo_categories"]) <= set(load_categories().ids):
        raise EntryFileError(f"{path.name}: geo_categories names categories of categories.yaml only")
    if not all(isinstance(code, str) and _EU_THEME.fullmatch(code) for code in data["not_geo_eu_themes"]):
        raise EntryFileError(f"{path.name}: not_geo_eu_themes holds codes of EU data themes")
    share = data["extent_share_below"]
    if isinstance(share, bool) or not isinstance(share, (int, float)) or not 0 < share <= 1:
        raise EntryFileError(f"{path.name}: extent_share_below is a share above 0 and at most 1")
    return GeodataRule(
        geo_data_kinds=frozenset(data["geo_data_kinds"]),
        geo_categories=frozenset(data["geo_categories"]),
        extent_share_below=float(share),
        geo_terms=_terms(data["geo_terms"], "geo_terms"),
        not_geo_eu_themes=frozenset(data["not_geo_eu_themes"]),
        not_geo_terms=_terms(data["not_geo_terms"], "not_geo_terms"),
    )


@cache
def load_geodata_rule() -> GeodataRule:
    return read_geodata_rule(GEODATA_FILE)


def _area(box: tuple[float, float, float, float]) -> float:
    west, south, east, north = box
    return ((east - west) % 360 or (360.0 if east != west else 0.0)) * (north - south)


@dataclass(frozen=True, slots=True)
class Classified:
    """``geodata``, ``not_geodata`` or ``undecided`` (counted as geodata) and the signals that decided it."""

    outcome: str
    geo: tuple[str, ...]
    not_geo: tuple[str, ...]

    @property
    def hidden(self) -> bool:
        return self.outcome == "not_geodata"


def classify(found: Mapping[str, Any], extent: Extent, *, country: str | None, rule: GeodataRule) -> Classified:
    """The verdict of R-G on an intermediate form and its extent (plan §7)."""
    geo: list[str] = []
    if found.get("data_kind") in rule.geo_data_kinds:
        geo.append(f"data_kind:{found['data_kind']}")
    for distribution in found.get("distributions") or ():
        if isinstance(distribution, dict):
            kind = resource_kind(distribution.get("format"), distribution.get("media_type"))
            if kind in rule.geo_data_kinds:
                geo.append(f"format:{kind}")
                break
    themes = [t for t in found.get("themes") or () if isinstance(t, str)]
    if any(t.startswith("inspire:") for t in themes):
        geo.append("inspire")
    if found.get("category") in rule.geo_categories:
        geo.append(f"category:{found['category']}")
    if extent.basis == "place" and any("-" in code for code in extent.codes):
        geo.append("extent:place")
    if extent.basis == "source" and extent.bbox is not None:
        state = None if country is None else region_boxes().get(country)
        if state is None or _area(extent.bbox) < rule.extent_share_below * _area(state):
            geo.append("extent:source")
    title, keywords = found.get("title") or "", [k for k in found.get("keywords") or () if isinstance(k, str)]
    geo += [f"term:{hit}" for hit in dict.fromkeys(rule.geo_terms.found([title, *keywords]))]
    not_geo = [f"eu:{t[3:]}" for t in themes if t.startswith("eu:") and t[3:] in rule.not_geo_eu_themes]
    publisher = found.get("publisher") if isinstance(found.get("publisher"), str) else ""
    not_geo += [f"term:{hit}" for hit in dict.fromkeys(rule.not_geo_terms.found([title, *keywords, publisher]))]
    if geo:
        outcome = "geodata"
    elif not_geo:
        outcome = "not_geodata"
    else:
        outcome = "undecided"
    return Classified(outcome, tuple(geo), tuple(not_geo))
