"""Enrich: the spatial and temporal extent of a harvested find (M5-20 plan §6, §13b; F1 = 1, F2 = 1).

The spatial extent is taken from the first of these steps that gives one; ``basis`` says which (plan §6.1):

1. ``source`` — the geometry or box the source gives.
2. ``place`` — a place text of the source that names places of the directory, all of them (``place_names.yaml``).
3. ``publisher`` — a publisher whose name holds exactly one place of the directory.
4. ``catalog`` — the state of the catalogue (``country`` of the seed), also for a text that names the whole state by
   its parts ("Kantone", "Gemeinden").
5. ``none``.

Only the first two give a footprint (an area search finds them); the others give regions only. Nothing is guessed:
a name that is also a municipality's matches only after a designation ("Kanton Bern"), a text with one part that is
no place of the directory matches nothing, and a place in a title is never read. Pure: no database, no request.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any

from earthx.catalog.datasets import CATALOG_DIR
from earthx.catalog.entry_files import EntryFileError, read_yaml
from earthx.catalog.glossary import normalize
from earthx.catalog.listed import load_regions

__all__ = ["PLACE_NAMES_FILE", "Extent", "PlaceDirectory", "load_place_directory", "spatial_extent", "time_span"]

PLACE_NAMES_FILE = CATALOG_DIR / "place_names.yaml"
_KEYS = frozenset({"places", "ambiguous", "designations", "whole_country", "approximate", "not_places", "geonames"})
_GEONAMES = re.compile(r"(?:https?://)?(?:sws\.|www\.)?geonames\.org/(\d{1,10})(?:/[^\s,;]*)?", re.IGNORECASE)
_CODE = re.compile(r"[A-Z]{2}")
_PARENTHESES = re.compile(r"\(([^()]*)\)")
#: How the parts of one place text are separated: a list or a double name ("Kanton Bern / Canton de Berne").
_PARTS = re.compile(r"\s*(?:/|;|,|\||\s+und\s+|\s+et\s+|\s+and\s+)\s*", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Extent:
    """The spatial extent of a find: its basis, the regions it names (codes of ``regions.json``, states included), and
    for ``source`` the box and geometry of the source; ``unresolved`` is a place text that matched nothing."""

    basis: str
    codes: tuple[str, ...] = ()
    bbox: tuple[float, float, float, float] | None = None
    geometry: Mapping[str, Any] | None = None
    unresolved: str | None = None

    @property
    def has_footprint(self) -> bool:
        return self.basis in ("source", "place")


@dataclass(frozen=True, slots=True)
class PlaceDirectory:
    #: Normal name → code, for names that match on their own.
    plain: Mapping[str, str]
    #: Normal name → code, for every name, after a designation.
    designated: Mapping[str, str]
    designations: tuple[str, ...]
    whole_country: frozenset[str]
    before: tuple[str, ...]
    after: tuple[str, ...]
    not_places: frozenset[str]
    geonames: Mapping[str, str]
    #: Every code of ``regions.json`` → its level, for the two-letter codes of a text.
    levels: Mapping[str, str]

    def code_of(self, text: str, country: str | None) -> str | None:
        """The code of a two-letter abbreviation: a subdivision of ``country`` first (``FR`` at opendata.swiss is the
        canton, not France), else a state (plan A15)."""
        if not _CODE.fullmatch(text):
            return None
        if country is not None and self.levels.get(f"{country}-{text}") == "subdivision":
            return f"{country}-{text}"
        return text if self.levels.get(text) == "state" else None

    def name_code(self, normal: str) -> str | None:
        """The code of a normal name, plain or after one of the designations."""
        if normal in self.plain:
            return self.plain[normal]
        for designation in self.designations:
            if normal.startswith(designation + " ") and (rest := normal[len(designation) + 1 :]) in self.designated:
                return self.designated[rest]
        return None


def _names(data: Mapping[str, Any], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and normalize(item) for item in value):
        raise EntryFileError(f"{PLACE_NAMES_FILE.name}: {key} is a list of names")
    return value


def read_place_directory(path: Path, regions: Mapping[str, str]) -> PlaceDirectory:
    """The directory of ``path`` against the codes of ``regions`` (code → level); a name stands under one code only."""
    data = read_yaml(path)
    if not isinstance(data, dict) or set(data) != _KEYS:
        raise EntryFileError(f"{path.name}: holds exactly {', '.join(sorted(_KEYS))}")
    places, geonames, approximate = data["places"], data["geonames"], data["approximate"]
    if not isinstance(places, dict) or not isinstance(geonames, dict):
        raise EntryFileError(f"{path.name}: places and geonames are mappings")
    if not isinstance(approximate, dict) or set(approximate) != {"before", "after"}:
        raise EntryFileError(f"{path.name}: approximate holds before and after")
    ambiguous = {normalize(name) for name in _names(data, "ambiguous")}
    plain: dict[str, str] = {}
    designated: dict[str, str] = {}
    for code in places:
        if code not in regions:
            raise EntryFileError(f"{path.name}: places names {code}, which regions.json lacks")
        for name in _names(places, code):
            normal = normalize(name)
            if designated.get(normal, code) != code:
                raise EntryFileError(f"{path.name}: the name {name!r} stands under two codes")
            designated[normal] = code
            if normal not in ambiguous:
                plain[normal] = code
    if unknown := sorted(ambiguous - set(designated)):
        raise EntryFileError(f"{path.name}: ambiguous names no place: {', '.join(unknown)}")
    for key, code in geonames.items():
        if not isinstance(key, str) or not key.isdigit() or code not in regions:
            raise EntryFileError(f"{path.name}: geonames maps a numeric id (as text) to a code of regions.json")
    # The longest designation first, so that "Canton de" is tried before "Canton".
    designations = tuple(sorted({normalize(d) for d in _names(data, "designations")}, key=len, reverse=True))
    return PlaceDirectory(
        plain=plain,
        designated=designated,
        designations=designations,
        whole_country=frozenset(normalize(text) for text in _names(data, "whole_country")),
        before=tuple(sorted({normalize(t) for t in _names(approximate, "before")}, key=len, reverse=True)),
        after=tuple(sorted({normalize(t) for t in _names(approximate, "after")}, key=len, reverse=True)),
        not_places=frozenset(normalize(text) for text in _names(data, "not_places")),
        geonames=dict(geonames),
        levels=regions,
    )


@cache
def load_place_directory() -> PlaceDirectory:
    """The directory of the image, read once per process."""
    return read_place_directory(PLACE_NAMES_FILE, {region.code: region.level for region in load_regions()})


def _states(codes: Iterable[str]) -> tuple[str, ...]:
    """The codes with the state of every subdivision, each once, sorted."""
    return tuple(sorted({part for code in codes for part in (code, code.split("-")[0])}))


def _drop_approximate(normal: str, directory: PlaceDirectory) -> str:
    for word in directory.after:
        if normal.endswith(" " + word):
            normal = normal[: -len(word) - 1]
    for word in directory.before:
        if normal.startswith(word + " "):
            normal = normal[len(word) + 1 :]
    return normal


def _part(text: str, directory: PlaceDirectory, country: str | None) -> str | None:
    """What one part of a place text is: a code, ``""`` for a part that is passed over, ``*`` for the whole state of
    the catalogue, ``None`` for no place."""
    stripped = text.strip()
    if not stripped:
        return ""
    code = directory.code_of(stripped, country)
    if code is not None:
        return code
    normal = normalize(stripped)
    if not normal or normal in directory.not_places or normal in directory.after:
        return ""
    if normal in directory.whole_country:
        return "*"
    return directory.name_code(normal) or directory.name_code(_drop_approximate(normal, directory))


def place_codes(text: str, directory: PlaceDirectory, country: str | None) -> tuple[str, ...] | str | None:
    """The places a place text names: their codes, ``"*"`` for the whole state of the catalogue, ``""`` for a text
    that is no place at all, ``None`` where one part names no place of the directory."""
    ids = _GEONAMES.findall(text)
    if ids:
        codes = [directory.geonames.get(i) for i in ids]
        return None if None in codes else tuple(sorted(set(codes)))  # type: ignore[arg-type]
    whole = _part(text, directory, country)
    if whole is not None:
        # "République et canton de Genève" is one name, not a list at "et".
        return "*" if whole == "*" else (whole,) if whole else ""
    found: set[str] = set()
    inner = _PARENTHESES.findall(text)
    parts = [*_PARTS.split(_PARENTHESES.sub(" ", text)), *inner]
    # "X und angrenzende Gebiete": the words after the core go before the text is cut at "und".
    normal_whole = normalize(text)
    for word in directory.after:
        if normal_whole.endswith(" " + word):
            parts = [*_PARTS.split(_PARENTHESES.sub(" ", text[: _cut(text, word)])), *inner]
    for part in parts:
        outcome = _part(part, directory, country)
        if outcome is None:
            return None
        if outcome:
            found.add(outcome)
    if not found:
        return ""
    if "*" in found:
        return "*" if found == {"*"} else None
    return tuple(sorted(found))


def _cut(text: str, words: str) -> int:
    """Where the trailing ``words`` (normal form) begin in ``text``."""
    for index in range(len(text) - 1, -1, -1):
        if normalize(text[index:]) == words:
            return index
    return len(text)


def publisher_code(publisher: str, directory: PlaceDirectory) -> str | None:
    """The one place the name of a publisher holds, as a whole sequence of words; none where it holds none or several.

    A name inside a longer one does not count ("Sachsen" in "Sachsen-Anhalt"), nor an ambiguous name without its
    designation ("Stadt Zürich" names no canton).
    """
    words = normalize(publisher).split()
    spans: list[tuple[int, int, str]] = []
    for start in range(len(words)):
        for end in range(start + 1, min(len(words), start + 8) + 1):
            code = directory.name_code(" ".join(words[start:end]))
            if code is not None:
                spans.append((start, end, code))
    kept = {code for s, e, code in spans if not any(s2 <= s and e <= e2 and (s2, e2) != (s, e) for s2, e2, _ in spans)}
    return next(iter(kept)) if len(kept) == 1 else None


def spatial_extent(
    found: Mapping[str, Any], *, country: str | None, directory: PlaceDirectory | None = None
) -> Extent:
    """The spatial extent of an intermediate form (``bbox``, ``geometry``, ``spatial_text``, ``publisher``)."""
    directory = load_place_directory() if directory is None else directory
    bbox = found.get("bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        return Extent("source", bbox=tuple(float(v) for v in bbox), geometry=found.get("geometry"))  # type: ignore[arg-type]
    text = found.get("spatial_text")
    unresolved = None
    if isinstance(text, str) and text.strip():
        codes = place_codes(text, directory, country)
        if codes == "*" and country is not None:
            return Extent("catalog", codes=(country,))
        if isinstance(codes, tuple) and codes:
            return Extent("place", codes=_states(codes))
        if codes is None:
            unresolved = text
    publisher = found.get("publisher")
    if isinstance(publisher, str) and (code := publisher_code(publisher, directory)) is not None:
        return Extent("publisher", codes=_states([code]), unresolved=unresolved)
    if country is not None:
        return Extent("catalog", codes=(country,), unresolved=unresolved)
    return Extent("none", unresolved=unresolved)


_DATE = re.compile(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?")


def _instant(value: object, *, end: bool) -> datetime | None:
    """An instant of a date text: a year, a month, a day (the whole of it, so the end is its last second) or an ISO
    instant (UTC where it names no zone); ``None`` for anything else."""
    if not isinstance(value, str) or not (text := value.strip()):
        return None
    match = _DATE.fullmatch(text)
    if match:
        year, month, day = int(match[1]), match[2], match[3]
        try:
            first = datetime(year, int(month or 1), int(day or 1), tzinfo=UTC)
        except ValueError:
            return None
        if not end:
            return first
        if day:
            after = first + timedelta(days=1)
        elif month:
            after = first.replace(year=year + (first.month == 12), month=first.month % 12 + 1)
        else:
            after = first.replace(year=year + 1)
        return after - timedelta(seconds=1)
    try:
        instant = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return instant.replace(tzinfo=UTC) if instant.tzinfo is None else instant.astimezone(UTC)


def time_span(temporal: object) -> tuple[datetime | None, datetime | None] | None:
    """The period of an intermediate form's ``temporal`` (start and end texts), open ends allowed (plan §6.3); none
    where neither end is a date or the end lies before the start."""
    if not isinstance(temporal, (list, tuple)) or len(temporal) != 2:
        return None
    start, end = _instant(temporal[0], end=False), _instant(temporal[1], end=True)
    if start is None and end is None:
        return None
    if start is not None and end is not None and end < start:
        return None
    return start, end
