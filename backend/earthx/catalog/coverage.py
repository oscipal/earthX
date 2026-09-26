"""The coverage seam: one question, one answer, whoever answers it (adr/0004 §5).

The question is "how dense is dataset X under filter F on grid level z", the answer
is cells with a count, a time histogram and — the part that makes it trustworthy — a
**checked** completeness. Which of the three ways of adr/0004 §5 answers it is decided
by the registry entry of the dataset, not by the caller: upstream aggregation, SQL in
our own PostGIS, or a declared sample.

Why the seam is here and not in ``adapters``: the grid, the counting rule, the level
caps and rule V are the platform's decisions and hold for every source
(``architekturplan.md`` 3.1, "STAC-Modell, pgstac, Suche"). What a *particular* source
speaks — that Earth Search answers ``/aggregate`` only on GET, what its parameters are
called, where it truncates — stays in ``adapters``. That is also the direction the
import contracts allow: ``adapters`` may import ``catalog``, never the other way
round.

Two properties are deliberate and both are about not claiming more than was measured:

* **``overflow`` is not believed.** Earth Search reports ``overflow: 0`` even where a
  third of the scenes are missing (adr/0004 §3.3 and its note of 20.09.2026). Only
  ``sum(cells) == total_count`` decides, and :func:`check_completeness` is where that
  happens — a function, so it can be tested rather than trusted.
* **A cap clamps, it does not refuse.** Asking for a finer level than a dataset or the
  source can carry returns the coarser map with the level it actually used. The map
  gets coarser, never empty — the same posture as E5 on the answering side.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from earthx.catalog.registry import DatasetConfig

# adr/0004 §5, Otto's answer to question 3 of 19.09.2026: below this many hits the
# viewer draws the real footprints instead of a density. It lives here, once, so that
# the rule is the same wherever it is asked and can be checked in pytest; the zoom
# stays the additional brake and sits in the frontend (M2-07c).
FOOTPRINT_THRESHOLD = 500

# adr/0004 §3.3, note of 20.09.2026: without a spatial filter the source truncates
# from z7 on, and the answer passes the ~500 kB mark at which §5 wants to reconsider
# vector tiles. A world view asks z0 to z3 in practice — this only stops someone
# asking for z8 with no bounding box.
WORLD_LEVEL_CAP = 6

# Geotile is the XYZ scheme of the map itself (adr/0004 §3.7), so a level is a zoom.
# Geotile itself runs out here — below a metre a cell is past any imagery — and Earth
# Search happens to draw the same line: a precision outside 0..29 comes back as a 400
# (measured 20.09.2026, plans/m2-05-coverage.md §3.4). The bound is the grid's, the
# measurement only confirms it, so it stays in `catalog` with the rest of the grid.
MAX_GEOTILE_LEVEL = 29

# Measured on 20.09.2026 (plans/m2-05-coverage.md §3.1): Earth Search ignores
# ``datetime_frequency_interval`` — day, month, year and even a nonsense value all
# return the same monthly buckets. So the histogram is monthly, and no caller is
# offered a choice that would not be kept. A finer histogram is a new measurement and
# a decision of its own, not a parameter.
HISTOGRAM_INTERVAL = "month"


class CoverageError(Exception):
    """Base of the errors this seam raises, so a caller can catch the family."""


class InvalidCoverageQuery(CoverageError, ValueError):
    """The request breaks one of our own rules, before anything is sent upstream."""


class CoverageProviderMismatch(CoverageError, LookupError):
    """This dataset is answered by another way than the one that was asked.

    A dispatch mistake, not a user error — the counterpart of ``UnsupportedSource``
    for the search path.
    """


class UpstreamCoverageShapeError(CoverageError, RuntimeError):
    """The source answered something that is not an aggregation we can read."""


class Completeness(Enum):
    """The mandatory field of rule V (adr/0004 §5), in the wording of its note of
    20.09.2026: English on the wire, German in the UI and in the ADR.

    ``complete`` = vollständig, ``truncated`` = gekappt, ``sample`` = Stichprobe.
    """

    COMPLETE = "complete"
    TRUNCATED = "truncated"
    SAMPLE = "sample"


@dataclass(frozen=True, slots=True)
class CoverageCell:
    """One grid cell and how many scenes have their centroid in it.

    The key is the geotile key ``z/x/y``, exactly as the source writes it — there is
    nothing to translate. :func:`cell_bbox` turns it into a box where one is needed;
    on the wire it stays the key, which keeps the world overview at z6 near 160 kB
    instead of the ~570 kB a ready-made polygon would cost (Otto, F4 of 20.09.2026).
    """

    key: str
    count: int


@dataclass(frozen=True, slots=True)
class HistogramBucket:
    """One step of the time histogram, from the same request as the cells."""

    start: datetime
    count: int


@dataclass(frozen=True, slots=True)
class CoverageQuery:
    """What is being asked. Checked here, so an unchecked one cannot exist.

    ``level`` is the geotile level the answer should use. It is *not* clamped in here:
    clamping needs the registry entry, so :func:`level_for_viewport` does it and the
    caller passes the result. What this checks is only what can be wrong on its own.
    """

    dataset_id: str
    level: int
    bbox: tuple[float, float, float, float] | None = None
    intersects: Mapping[str, Any] | None = None
    start: datetime | None = None
    end: datetime | None = None
    max_cloud_cover: float | None = None

    def __post_init__(self) -> None:
        self._check_level()
        self._check_area()
        self._check_time()
        self._check_cloud_cover()

    @property
    def has_spatial_filter(self) -> bool:
        return self.bbox is not None or self.intersects is not None

    @property
    def is_unfiltered(self) -> bool:
        """True for the world overview: no area, no time window, no cloud filter.

        This is the one answer Otto gave the long lifetime on 20.09.2026 (F3): at
        thirty million items a day's new scenes change nothing visible, and it is the
        view every user sees first.
        """
        return not self.has_spatial_filter and self.start is None and self.end is None and self.max_cloud_cover is None

    def _check_level(self) -> None:
        if not 0 <= self.level <= MAX_GEOTILE_LEVEL:
            raise InvalidCoverageQuery(f"grid level {self.level} is outside 0..{MAX_GEOTILE_LEVEL}")

    def _check_area(self) -> None:
        # No message below names a coordinate: an exception text becomes a log line and
        # an error body, and the AOI belongs in neither (projektplan.md 7, point 6).
        if self.bbox is not None and self.intersects is not None:
            raise InvalidCoverageQuery("bbox and intersects ask two different questions; send one")
        if self.bbox is not None:
            if len(self.bbox) != 4:
                raise InvalidCoverageQuery("bbox needs four values: west, south, east, north")
            west, south, east, north = self.bbox
            if not all(-90.0 <= value <= 90.0 for value in (south, north)):
                raise InvalidCoverageQuery("bbox latitudes are outside ±90")
            if not all(-180.0 <= value <= 180.0 for value in (west, east)):
                raise InvalidCoverageQuery("bbox longitudes are outside ±180")
            if south >= north:
                raise InvalidCoverageQuery("bbox is upside down: south is not below north")
        if self.intersects is not None:
            self._check_geometry(self.intersects)

    @staticmethod
    def _check_geometry(geometry: Mapping[str, Any]) -> None:
        """Enough of a check that nothing shapeless reaches a query string.

        Not a full GeoJSON validator — the source is the authority on its own input.
        This refuses what would otherwise be serialised into a URL without anyone ever
        having looked at it.
        """
        if not isinstance(geometry, Mapping):
            raise InvalidCoverageQuery("intersects is not a GeoJSON object")
        kind = geometry.get("type")
        if kind not in {"Polygon", "MultiPolygon"}:
            raise InvalidCoverageQuery("intersects needs a Polygon or MultiPolygon")
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or not coordinates:
            raise InvalidCoverageQuery("intersects carries no coordinates")
        if kind == "Polygon":
            rings = coordinates
        else:
            rings = [ring for shape in coordinates if isinstance(shape, list) for ring in shape]
        if not any(_is_ring(ring) for ring in rings):
            # Without this, ``{"coordinates": [[]]}`` passes and is serialised into a
            # query string, and the refusal arrives from the source as a 400 instead of
            # from us before anything is sent.
            raise InvalidCoverageQuery("intersects has no ring with at least four positions")
        for ring in rings:
            if _is_ring(ring):
                _check_ring_bounds(ring)

    def _check_time(self) -> None:
        for name, value in (("start", self.start), ("end", self.end)):
            if value is not None and value.tzinfo is None:
                raise InvalidCoverageQuery(f"{name} has no timezone; STAC instants carry one")
        if self.start is not None and self.end is not None and self.start > self.end:
            raise InvalidCoverageQuery("time window ends before it starts")

    def _check_cloud_cover(self) -> None:
        # The one content filter of M2, listed rather than passed through: a free query
        # parameter would be an open door outwards again, and CQL2 stays off anyway
        # (adr/0005 rule VI).
        if self.max_cloud_cover is None:
            return
        if not 0.0 <= self.max_cloud_cover <= 100.0:
            raise InvalidCoverageQuery("max_cloud_cover is a percentage, so it lies between 0 and 100")


@dataclass(frozen=True, slots=True)
class CoverageResult:
    """The answer, the same shape whichever way produced it (adr/0004 K3)."""

    dataset_id: str
    level: int
    cells: tuple[CoverageCell, ...]
    total_count: int | None
    completeness: Completeness
    histogram: tuple[HistogramBucket, ...]
    from_cache: bool
    # Constant for now, and named rather than assumed: every way of adr/0004 §5 counts
    # a scene into exactly one cell, and the legend says so ("Aufnahmen mit Mittelpunkt
    # in der Zelle"). A second grid or a second counting rule would have to say so here.
    grid: str = "geotile"
    counting: str = "centroid"
    # Set only by :func:`extent_result` and the ``local-sql`` area way
    # (`catalog.local_coverage.area_coverage`, M3-11c): a one-off product has
    # nothing to count, so it answers with the ground it covers instead of a
    # density (adr/0004 §5, "Wo welcher Teil liegt" / "Einmal-Produkte"). For the
    # area way this is the bbox of ``area`` below, not the collection's own extent.
    extent: tuple[float, float, float, float] | None = None
    # Set only by the ``local-sql`` area way (M3-11c, adr/0009 §6 F5): the union of
    # a materialized one-off product's own item footprints, as a GeoJSON
    # ``MultiPolygon`` — the honest coverage of a dataset with nothing to count,
    # cropped to whatever spatial filter the query carried. ``None`` everywhere
    # else, including the ``extent_result`` way, which answers a different question
    # (the collection's declared extent, not a union of items).
    area: Mapping[str, Any] | None = None
    # Filters the query carried that this answer could not honour and silently
    # dropped rather than reject (Otto, 26.09.2026, M3-11c): ``"datetime"`` for a
    # dataset with ``capabilities.time_range=False``, ``"max_cloud_cover"`` on the
    # area way, which has no cloud cover to filter on. Named, not just dropped, so
    # the frontend can say so instead of the map quietly answering a narrower
    # question than the one asked (the same posture as `completeness=truncated`).
    ignored_filters: tuple[str, ...] = ()

    @property
    def counted(self) -> int:
        """What the cells add up to — derived, never passed in.

        Rule V lives on this number being the cells' own sum. As a field it could be
        set to something the cells do not say, and the check would then compare the
        total against a number with no relation to the map.
        """
        return sum(cell.count for cell in self.cells)

    @property
    def max_count(self) -> int:
        """The largest cell, which is where the frontend anchors its log scale."""
        return max((cell.count for cell in self.cells), default=0)

    @property
    def footprints_advised(self) -> bool:
        """Whether to draw real footprints instead of the density (adr/0004 §5).

        ``total_count is None`` — a declared sample — deliberately keeps the density:
        the replacement rule for M2-07c says footprints must not appear automatically
        where there is no checked total to compare against.
        """
        return self.total_count is not None and self.total_count < FOOTPRINT_THRESHOLD


class CoverageSource(Protocol):
    """Whoever answers the question, answers exactly this.

    Only the query and the dataset entry, nothing else: the three ways of adr/0004 §5
    need different things to do their work — the upstream way a gateway and a cache,
    the local one a database connection — and a seam that named any of them would be
    the shape of one way rather than of the question. Whoever assembles the parts binds
    them before handing the source over, which is what ``api`` does for the federated
    search already.
    """

    async def __call__(self, query: CoverageQuery, config: DatasetConfig) -> CoverageResult:
        """Density, histogram and a checked completeness for this query."""
        ...


@runtime_checkable
class CoverageCache(Protocol):
    """A key-value store with an expiry. Missing is normal; failing is survivable.

    The same shape as ``earthx.adapters.cache.SearchCache`` and satisfied by the same
    ``PostgresSearchCache``. It is declared a second time rather than imported because
    the two point in opposite directions: ``SearchCache`` is what ``adapters`` asks of
    ``catalog``, this is what the seam in ``catalog`` asks of whoever answers it, and
    ``catalog`` must not import ``adapters`` (architekturplan.md 3.1).
    """

    async def get(self, key: str) -> dict[str, Any] | None:
        """The stored value, or None if it is absent or expired."""
        ...

    async def set(self, key: str, value: dict[str, Any], *, ttl_s: float, dataset_id: str) -> None:
        """Store a value for ``ttl_s`` seconds."""
        ...


def check_completeness(
    counted: int,
    total_count: int | None,
    *,
    simplified_aoi: bool = False,
    sampled: bool = False,
) -> Completeness:
    """Rule V of adr/0004 §5 as a function, so it is checked and not intended.

    Four cases, and three of them are the ones that cost a map its honesty:

    * a declared sample is a sample, whatever the numbers say;
    * a simplified or boxed AOI answers a different question than the one asked
      (adr/0004 §3.4), so the answer is truncated even when the sums agree;
    * **without a ``total_count`` there is nothing to compare against**, and a source
      that cannot state a total cannot prove completeness (note of 20.09.2026);
    * otherwise it is complete exactly when the cells add up to the total. The source's
      own ``overflow`` never enters into it — it reports 0 while a third of the scenes
      are missing (adr/0004 §3.3).
    """
    if sampled:
        return Completeness.SAMPLE
    if simplified_aoi or total_count is None or counted != total_count:
        return Completeness.TRUNCATED
    return Completeness.COMPLETE


def extent_result(dataset_id: str, bbox: tuple[float, float, float, float]) -> CoverageResult:
    """The answer for a one-off product: its extent, not a density (adr/0004 §5).

    Checked *before* a provider is even asked (``registry.py`` already forbids the
    combination of ``single_coverage_product`` with upstream aggregation) — a single
    coverage has nothing to count, so there is no cell, no histogram, and its
    completeness is trivially whole: the extent is what the collection states,
    nothing is being compared against a total that does not apply here.
    """
    return CoverageResult(
        dataset_id=dataset_id,
        level=0,
        cells=(),
        total_count=None,
        completeness=Completeness.COMPLETE,
        histogram=(),
        from_cache=False,
        extent=bbox,
    )


def level_for_viewport(zoom: int, config: DatasetConfig, *, has_spatial_filter: bool) -> int:
    """The grid level to ask for: the map's zoom under both caps of adr/0004 §5.

    Clamped, never refused — a level finer than the caps allow returns the coarser map
    with the level it used, and the caller reports that level in the answer.

    Cap one is the dataset's own (``max_geotile_level``): once a cell is smaller than a
    footprint, the centroid rule draws a dot pattern instead of a coverage. Cap two is
    the world cap of the note of 20.09.2026: without a spatial filter the source
    truncates from z7 on anyway.
    """
    level = max(0, min(int(zoom), MAX_GEOTILE_LEVEL))
    level = min(level, config.coverage.max_geotile_level)
    if not has_spatial_filter:
        level = min(level, WORLD_LEVEL_CAP)
    return level


def parse_cell_key(key: str) -> tuple[int, int, int]:
    """Read a geotile key ``z/x/y``, or say why it is not one.

    Strict on purpose: the key comes from outside and ends up in a map layer. A key
    whose column or row lies outside ``2**z`` is not a cell that exists.
    """
    parts = key.split("/")
    if len(parts) != 3:
        raise UpstreamCoverageShapeError(f"grid key {key!r} is not z/x/y")
    try:
        level, column, row = (int(part) for part in parts)
    except ValueError:
        raise UpstreamCoverageShapeError(f"grid key {key!r} has a part that is not a number") from None
    if not 0 <= level <= MAX_GEOTILE_LEVEL:
        raise UpstreamCoverageShapeError(f"grid key {key!r} names a level outside 0..{MAX_GEOTILE_LEVEL}")
    side = 1 << level
    if not (0 <= column < side and 0 <= row < side):
        raise UpstreamCoverageShapeError(f"grid key {key!r} lies outside the grid of its own level")
    return level, column, row


def cell_bbox(key: str) -> tuple[float, float, float, float]:
    """The cell as west, south, east, north in WGS84.

    Geotile is the ordinary XYZ scheme: columns run east from the antimeridian, rows
    run south from the top of the Web-Mercator square. Kept here rather than in the
    frontend or the adapter because both the local SQL way and the tests need the very
    same arithmetic (adr/0004 §3.7).
    """
    level, column, row = parse_cell_key(key)
    side = 1 << level
    west = column / side * 360.0 - 180.0
    east = (column + 1) / side * 360.0 - 180.0
    north = _mercator_latitude(row / side)
    south = _mercator_latitude((row + 1) / side)
    return (west, south, east, north)


def geotile_key(longitude: float, latitude: float, level: int) -> str:
    """The geotile cell whose area contains a WGS84 point — the inverse of
    :func:`cell_bbox`.

    For a coverage way that rasterizes itself instead of asking a source to
    (adr/0004 §5, Option 6, the declared-sample way of M2-09b-3): a footprint is
    counted into the one cell its centroid falls in, by the same grid and the
    same centroid rule every other way uses — this is that arithmetic, kept here
    rather than in `adapters` because it is the grid's own definition, not
    anything about a particular source (module docstring above).

    A point at the edge of the grid — past ±180° longitude, or past the Mercator
    limit near a pole — is clamped into the nearest cell rather than refused: a
    measured centroid is never truly outside the world it came from, only
    outside the numeric range this projection can draw, and refusing it would
    turn one odd footprint into a failed request instead of one cell that is a
    little off.
    """
    side = 1 << level
    column = min(side - 1, max(0, int((_clamped_longitude(longitude) + 180.0) / 360.0 * side)))
    row = min(side - 1, max(0, int(_mercator_row(latitude) * side)))
    return f"{level}/{column}/{row}"


# atan(sinh(pi)) in degrees — where `_mercator_latitude`'s row 0 already lands, so the
# forward mapping below clamps to exactly the range the grid can already draw.
_MAX_MERCATOR_LATITUDE = 85.05112877980659


def _clamped_longitude(longitude: float) -> float:
    return max(-180.0, min(180.0, longitude))


def _clamped_latitude(latitude: float) -> float:
    return max(-_MAX_MERCATOR_LATITUDE, min(_MAX_MERCATOR_LATITUDE, latitude))


def _mercator_row(latitude: float) -> float:
    """Fraction of the way down the Web-Mercator square — the inverse of
    `_mercator_latitude`, by solving its formula for `fraction`."""
    radians = math.radians(_clamped_latitude(latitude))
    return (1.0 - math.asinh(math.tan(radians)) / math.pi) / 2.0


def _check_ring_bounds(ring: list[Any]) -> None:
    """Every corner of a ring lies on the globe.

    Otherwise a polygon with a longitude of 999 and a latitude of 888 is accepted
    (the source answers ``200`` and a plausible-looking number instead of refusing
    it — adr/0005 §3.5 describes the same silent acceptance for a bbox). None of the
    values enters the message (projektplan.md 7, point 6).
    """
    for longitude, latitude, *_rest in ring:
        if not -180.0 <= float(longitude) <= 180.0:
            raise InvalidCoverageQuery("intersects longitude is outside ±180")
        if not -90.0 <= float(latitude) <= 90.0:
            raise InvalidCoverageQuery("intersects latitude is outside ±90")


def _is_ring(ring: Any) -> bool:
    """A closed outline needs four positions of two numbers, three of them distinct."""
    return (
        isinstance(ring, list)
        and len(ring) >= 4
        and all(isinstance(point, (list, tuple)) and len(point) >= 2 for point in ring)
        and all(_is_number(value) for point in ring for value in point[:2])
    )


def _is_number(value: Any) -> bool:
    """A coordinate, and not a bool — ``True`` is an ``int`` and would pass otherwise."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _mercator_latitude(fraction: float) -> float:
    """Latitude at ``fraction`` of the way down the Web-Mercator square."""
    return math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * fraction))))
