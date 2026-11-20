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
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any

from earthx.catalog.datasets import CATALOG_DIR
from earthx.catalog.entry_files import EntryFileError, read_yaml
from earthx.catalog.glossary import normalize
from earthx.catalog.listed import load_regions
from earthx.catalog.municipalities import MUNICIPALITY_CODE, Municipality, load_municipalities

__all__ = [
    "PLACE_NAMES_FILE",
    "geonames_ids",
    "Extent",
    "PlaceDirectory",
    "box_of_codes",
    "load_place_directory",
    "region_boxes",
    "spatial_extent",
    "time_span",
]

PLACE_NAMES_FILE = CATALOG_DIR / "place_names.yaml"
_KEYS = frozenset(
    {
        "places",
        "ambiguous",
        "designations",
        "municipal_designations",
        "whole_country",
        "whole_country_prefixes",
        "beyond",
        "beyond_prefixes",
        "approximate",
        "not_places",
        "not_place_prefixes",
        "alpha3",
        "geonames",
    }
)
_GEONAMES = re.compile(r"(?:https?://)?(?:sws\.|www\.)?geonames\.org/(\d{1,10})(?:/[^\s,;]*)?", re.IGNORECASE)
_CODE = re.compile(r"[A-Z]{2}")
_EU_COUNTRY = re.compile(r"publications\.europa\.eu/resource/authority/country/([A-Z0-9]{2,3})\b", re.IGNORECASE)
#: What ``place_codes`` returns for a text beyond any one state ("Europa"): no region, and no fallback (plan A25).
BEYOND = "!"
_PARENTHESES = re.compile(r"\(([^()]*)\)")
#: How the parts of one place text are separated: a list or a double name ("Kanton Bern / Canton de Berne").
_PARTS = re.compile(r"\s*(?:/|;|,|\||\s+und\s+|\s+et\s+|\s+and\s+)\s*", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Extent:
    """The spatial extent of a find: its basis, the regions it names (codes of ``regions.json``, states included), and
    for ``source`` the box and geometry of the source; ``unresolved`` is a place text that matched nothing."""

    basis: str
    codes: tuple[str, ...] = ()
    #: For ``place``: the places a text named (regions or municipalities), whose outlines are the footprint.
    places: tuple[str, ...] = ()
    #: Where a bare name is a city and a canton ("Zug"), which one the publisher decided: ``"zug: Kanton"`` (plan §13d).
    choice: str | None = None
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
    whole_country_prefixes: tuple[str, ...]
    beyond: frozenset[str]
    beyond_prefixes: tuple[str, ...]
    not_place_prefixes: tuple[str, ...]
    alpha3: Mapping[str, str]
    before: tuple[str, ...]
    after: tuple[str, ...]
    not_places: frozenset[str]
    geonames: Mapping[str, str]
    #: Every code of ``regions.json`` → its level, for the two-letter codes of a text.
    levels: Mapping[str, str]
    #: Normal name of a municipality → its code (``municipalities.json``, F9); on its own only where no region and no
    #: other municipality has the name, else only after one of ``municipal_designations``.
    municipal: Mapping[str, str] = field(default_factory=dict)
    municipal_designated: Mapping[str, str] = field(default_factory=dict)
    municipal_designations: tuple[str, ...] = ()
    #: The box of every municipality of the directory, for the extent of a find that names one.
    municipal_boxes: Mapping[str, tuple[float, float, float, float]] = field(default_factory=dict)

    def code_of(self, text: str, country: str | None) -> str | None:
        """The code of a two-letter abbreviation: a subdivision of ``country`` first (``FR`` at opendata.swiss is the
        canton, not France), else a state (plan A15)."""
        if not _CODE.fullmatch(text):
            return None
        if country is not None and self.levels.get(f"{country}-{text}") == "subdivision":
            return f"{country}-{text}"
        return text if self.levels.get(text) == "state" else None

    def name_code(self, normal: str, *, municipal: bool = True) -> str | None:
        """The code of a normal name: a region, plain or after a designation; then, with ``municipal``, a municipality
        on its own name or after one of its designations ("Stadt Bern")."""
        if normal in self.plain:
            return self.plain[normal]
        for designation in self.designations:
            if normal.startswith(designation + " ") and (rest := normal[len(designation) + 1 :]) in self.designated:
                return self.designated[rest]
        if municipal and normal in self.municipal:
            return self.municipal[normal]
        return self.designated_municipality(normal)

    def designated_municipality(self, normal: str) -> str | None:
        """A municipality named after one of its designations ("Stadt Zürich", "Commune de Riehen")."""
        for designation in self.municipal_designations:
            prefix = designation + " "
            if normal.startswith(prefix) and (rest := normal[len(prefix) :]) in self.municipal_designated:
                return self.municipal_designated[rest]
        return None


def _names(data: Mapping[str, Any], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and normalize(item) for item in value):
        raise EntryFileError(f"{PLACE_NAMES_FILE.name}: {key} is a list of names")
    return value


def _municipal_names(municipalities: Sequence[Municipality], taken: Collection[str]) -> tuple[dict, dict]:
    """Normal name → code of the municipalities: the official name, and each part of a double name ("Biel/Bienne").
    A name two municipalities share counts for none; a name a region has counts only after a designation."""
    seen: dict[str, set[str]] = {}
    for item in municipalities:
        names = {item.name, *item.name.split("/")} if "/" in item.name else {item.name}
        for name in names:
            if normal := normalize(name):
                seen.setdefault(normal, set()).add(item.code)
    designated = {name: next(iter(codes)) for name, codes in seen.items() if len(codes) == 1}
    plain = {name: code for name, code in designated.items() if name not in taken}
    return plain, designated


def read_place_directory(
    path: Path, regions: Mapping[str, str], municipalities: Sequence[Municipality] = ()
) -> PlaceDirectory:
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
    alpha3 = data["alpha3"]
    if not isinstance(alpha3, dict) or not all(
        isinstance(k, str) and re.fullmatch(r"[A-Z]{3}", k) and regions.get(v) == "state" for k, v in alpha3.items()
    ):
        raise EntryFileError(f"{path.name}: alpha3 maps ISO 3166-1 alpha-3 codes to states of regions.json")
    # The longest designation first, so that "Canton de" is tried before "Canton".
    designations = tuple(sorted({normalize(d) for d in _names(data, "designations")}, key=len, reverse=True))
    # A name a region holds on its own stays the region's; an ambiguous one ("Bern") is the municipality's.
    municipal, municipal_designated = _municipal_names(municipalities, set(plain))
    municipal_designations = tuple(
        sorted({normalize(d) for d in _names(data, "municipal_designations")}, key=len, reverse=True)
    )
    return PlaceDirectory(
        plain=plain,
        designated=designated,
        designations=designations,
        municipal=municipal,
        municipal_designated=municipal_designated,
        municipal_designations=municipal_designations,
        municipal_boxes={item.code: _box_of(item.outline) for item in municipalities},
        whole_country=frozenset(normalize(text) for text in _names(data, "whole_country")),
        whole_country_prefixes=tuple(normalize(text) for text in _names(data, "whole_country_prefixes")),
        beyond=frozenset(normalize(text) for text in _names(data, "beyond")),
        beyond_prefixes=tuple(normalize(text) for text in _names(data, "beyond_prefixes")),
        not_place_prefixes=tuple(normalize(text) for text in _names(data, "not_place_prefixes")),
        alpha3=dict(alpha3),
        before=tuple(sorted({normalize(t) for t in _names(approximate, "before")}, key=len, reverse=True)),
        after=tuple(sorted({normalize(t) for t in _names(approximate, "after")}, key=len, reverse=True)),
        not_places=frozenset(normalize(text) for text in _names(data, "not_places")),
        geonames=dict(geonames),
        levels=regions,
    )


@cache
def load_place_directory() -> PlaceDirectory:
    """The directory of the image, read once per process."""
    regions = {region.code: region.level for region in load_regions()}
    return read_place_directory(PLACE_NAMES_FILE, regions, load_municipalities())


def _box_of(outline: Mapping[str, Any]) -> tuple[float, float, float, float]:
    points: list[tuple[float, float]] = []

    def walk(value: Any) -> None:
        if isinstance(value, list) and value and isinstance(value[0], (int, float)):
            points.append((float(value[0]), float(value[1])))
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(outline["coordinates"])
    return min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)


@cache
def region_boxes() -> Mapping[str, tuple[float, float, float, float]]:
    """The box of every region of ``regions.json``."""
    return {region.code: _box_of(region.outline) for region in load_regions()}


def named_codes(codes: Iterable[str]) -> tuple[str, ...]:
    """The codes a text named: a state is left out where one of its subdivisions stands beside it."""
    codes = set(codes)
    return tuple(sorted(c for c in codes if "-" in c or not any(o.startswith(c + "-") for o in codes)))


def _union_box(
    boxes: Mapping[str, tuple[float, float, float, float]], codes: Iterable[str]
) -> tuple[float, float, float, float] | None:
    found = [boxes[c] for c in codes if c in boxes]
    if not found:
        return None
    return min(b[0] for b in found), min(b[1] for b in found), max(b[2] for b in found), max(b[3] for b in found)


def box_of_codes(codes: Iterable[str]) -> tuple[float, float, float, float] | None:
    """The box around the regions a text named (plan A7); ``None`` where none is known."""
    boxes = [region_boxes()[c] for c in named_codes(codes) if c in region_boxes()]
    if not boxes:
        return None
    return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)


def _states(codes: Iterable[str]) -> tuple[str, ...]:
    """The regions of places: a subdivision with its state, a municipality as its canton and state (a municipality is
    no region of an entry, F9), each once, sorted."""
    regions: set[str] = set()
    for code in codes:
        if MUNICIPALITY_CODE.fullmatch(code):
            regions |= {code[:5], code[:2]}
        else:
            regions |= {code, code.split("-")[0]}
    return tuple(sorted(regions))


def _drop_approximate(normal: str, directory: PlaceDirectory) -> str:
    for word in directory.after:
        if normal.endswith(" " + word):
            normal = normal[: -len(word) - 1]
    for word in directory.before:
        if normal.startswith(word + " "):
            normal = normal[len(word) + 1 :]
    return normal


def _part(text: str, directory: PlaceDirectory, country: str | None, *, abbreviation: bool) -> str | None:
    """What one part of a place text is: a code, ``""`` for a part that is passed over, ``*`` for the whole state of
    the catalogue, ``None`` for no place. A two-letter abbreviation counts only as the whole text or in parentheses
    (plan A15): in a list ("DE, FR, IT") it is a state as often as a canton."""
    stripped = text.strip()
    if not stripped:
        return ""
    code = directory.code_of(stripped, country) if abbreviation else None
    if code is not None:
        return code
    normal = normalize(stripped)
    if not normal or normal in directory.not_places or normal in directory.after:
        return ""
    if normal in directory.whole_country:
        return "*"
    return directory.name_code(normal) or directory.name_code(_drop_approximate(normal, directory))


def geonames_ids(text: str) -> list[str]:
    """The GeoNames ids of the addresses ``sws.geonames.org/<id>`` in a place text (F10)."""
    return _GEONAMES.findall(text)


def _starts(normal: str, prefixes: Iterable[str]) -> bool:
    return any(normal == prefix or normal.startswith(prefix) for prefix in prefixes)


def place_codes(text: str, directory: PlaceDirectory, country: str | None) -> tuple[str, ...] | str | None:
    """The places a place text names: their codes, ``"*"`` for the whole state of the catalogue, :data:`BEYOND` for
    a text beyond any one state, ``""`` for a text that is no place at all, ``None`` where a part names no place of
    the directory."""
    ids = _GEONAMES.findall(text)
    if ids:
        codes = [directory.geonames.get(i) for i in ids]
        return None if None in codes else tuple(sorted(set(codes)))  # type: ignore[arg-type]
    countries = _EU_COUNTRY.findall(text)
    if countries:
        # The EU vocabulary of countries: its code, alpha-2 or alpha-3 (Otto, 20.11.2026).
        codes = [c.upper() if directory.levels.get(c.upper()) == "state" else directory.alpha3.get(c.upper()) for c in countries]
        return None if None in codes else tuple(sorted(set(codes)))  # type: ignore[arg-type]
    normal = normalize(text)
    if normal in directory.beyond or _starts(normal, directory.beyond_prefixes):
        return BEYOND
    if _starts(normal, directory.whole_country_prefixes):
        return "*"
    if _starts(normal, directory.not_place_prefixes):
        return ""
    whole = _part(text, directory, country, abbreviation=True)
    if whole is not None:
        # "République et canton de Genève" is one name, not a list at "et".
        return "*" if whole == "*" else (whole,) if whole else ""
    found: set[str] = set()
    inner = _PARENTHESES.findall(text)
    outer = text
    # "X und angrenzende Gebiete": the words after the core go before the text is cut at "und".
    normal_whole = normalize(text)
    for word in directory.after:
        if normal_whole.endswith(" " + word):
            outer = text[: _cut(text, word)]
    # In parentheses: an abbreviation that confirms the name before it ("Jura (JU)" is the canton, though "Jura" alone
    # is ambiguous), a designation ("Bern (Kanton)"), or a note that is no place ("Basel (Stadtplan 1987 - 1992)").
    confirmed = {code for part in inner if (code := directory.code_of(part.strip(), country)) is not None}
    designation = next((normalize(p) for p in inner if normalize(p) in directory.designations), None)
    for part in _PARTS.split(_PARENTHESES.sub(" ", outer)):
        name = _drop_approximate(normalize(part), directory)
        if directory.designated.get(name) in confirmed:
            found.add(directory.designated[name])
            continue
        if designation is not None and (code := directory.name_code(f"{designation} {name}", municipal=False)):
            found.add(code)
            continue
        outcome = _part(part, directory, country, abbreviation=False)
        if outcome is None:
            return None
        if outcome:
            found.add(outcome)
    for part in inner:
        outcome = _part(part, directory, country, abbreviation=True)
        if outcome and outcome != "*":
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
            # A municipality only after its designation ("Stadt Zürich"): "Wald" in "Amt für Wald" is none.
            code = directory.name_code(" ".join(words[start:end]), municipal=False)
            if code is not None:
                spans.append((start, end, code))
    kept = {code for s, e, code in spans if not any(s2 <= s and e <= e2 and (s2, e2) != (s, e) for s2, e2, _ in spans)}
    return next(iter(kept)) if len(kept) == 1 else None


def _in_country(code: str, country: str | None) -> bool:
    return country is None or code == country or code.startswith(country + "-")


def _city_or_canton(
    text: str, municipality: str, publisher: object, directory: PlaceDirectory, country: str | None
) -> tuple[tuple[str, ...], str | None]:
    """A bare name that is a city and its canton ("Zug", "Schwyz", "St. Gallen"): the canton where the publisher is an
    office of that canton ("Kanton Zug", "Amt für Geoinformation Kanton Schwyz"), else the city (Otto, 20.11.2026)."""
    name = _drop_approximate(normalize(text), directory)
    canton = municipality[:5]
    if directory.designated.get(name) != canton:
        return (municipality,), None
    office = publisher_code(publisher, directory) if isinstance(publisher, str) else None
    if office == canton and _in_country(canton, country):
        return (canton,), f"{name}: Kanton"
    return (municipality,), f"{name}: Stadt"


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
        if codes == BEYOND:
            # "Europa", "Welt": no region, and not the state of the catalogue either (plan A25).
            return Extent("none")
        if codes == "*" and country is not None:
            return Extent("catalog", codes=(country,))
        if isinstance(codes, tuple) and codes and not all(_in_country(code, country) for code in codes if "-" in code):
            # "Vienne" at opendata.swiss is no Bundesland of Austria: a subdivision counts only in the state of the
            # catalogue (review M5-20 PR 1).
            codes = None
        choice = None
        if isinstance(codes, tuple) and len(codes) == 1 and MUNICIPALITY_CODE.fullmatch(codes[0]):
            codes, choice = _city_or_canton(text, codes[0], found.get("publisher"), directory, country)
        if isinstance(codes, tuple) and codes:
            if all("-" not in code for code in codes):
                # Only whole states ("Schweiz"): regions without a footprint, or every area in the state would find
                # the entry (plan A19, F11).
                return Extent("catalog", codes=codes)
            boxes = {**region_boxes(), **directory.municipal_boxes}
            return Extent("place", codes=_states(codes), places=codes, bbox=_union_box(boxes, codes), choice=choice)
        if codes is None:
            unresolved = text
    publisher = found.get("publisher")
    code = publisher_code(publisher, directory) if isinstance(publisher, str) else None
    if code is not None and _in_country(code, country):
        # Only a place in the state of the catalogue: "Sächsische Schweiz" at GovData is no Switzerland.
        return Extent("publisher", codes=_states([code]), unresolved=unresolved)
    if country is not None:
        return Extent("catalog", codes=(country,), unresolved=unresolved)
    return Extent("none", unresolved=unresolved)


_DATE = re.compile(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?")
#: An end in this year or later is an open end.
OPEN_END_YEAR = 9999


def _instant(value: object, *, end: bool) -> datetime | None:
    """An instant of a date text: a year, a month, a day (the whole of it, so the end is its last second) or an ISO
    instant (UTC where it names no zone); ``None`` for anything else."""
    if not isinstance(value, str) or not (text := value.strip()):
        return None
    match = _DATE.fullmatch(text)
    try:
        if match:
            year, month, day = int(match[1]), match[2], match[3]
            if end and year >= OPEN_END_YEAR:
                # "9999-12-31" is how DCAT and INSPIRE metadata write an open end.
                return None
            first = datetime(year, int(month or 1), int(day or 1), tzinfo=UTC)
            if not end:
                return first
            if day:
                after = first + timedelta(days=1)
            elif month:
                after = first.replace(year=year + (first.month == 12), month=first.month % 12 + 1)
            else:
                after = first.replace(year=year + 1)
            return after - timedelta(seconds=1)
        instant = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if end and instant.year >= OPEN_END_YEAR:
            return None
        return instant.replace(tzinfo=UTC) if instant.tzinfo is None else instant.astimezone(UTC)
    except (ValueError, OverflowError):
        return None


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
