"""Dataset registry: what the platform knows about a dataset before it asks the source.

One entry per dataset, as a frozen dataclass (KLAERUNGEN B13, stage M1-M4). The
fields mirror the ``earthx:`` fields of architekturplan.md 5.1, so that
``collection.to_stac_collection`` is a mapping and not an interpretation.

Nothing here has a default value where KLAERUNGEN B10 asks for a flag to be set
deliberately. Forgetting one is a ``TypeError`` at the entry, not a wrong answer
later on.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from types import MappingProxyType

# Circumference at the equator, in kilometres. Geotile level z splits it into
# 2**z columns, so a cell is EARTH_CIRCUMFERENCE_KM / 2**z wide (adr/0004 §5).
EARTH_CIRCUMFERENCE_KM = 40075.0


class DataClass(Enum):
    """Data type class of a dataset (projektuebersicht.md §5). Raster only for now."""

    RASTER_TIME_SERIES = "raster-time-series"
    RASTER_STATIC = "raster-static"


class DataFormat(Enum):
    """Storage format. The order is the preference of the onboarding checklist, point 5."""

    ZARR = "zarr"
    COG = "cog"
    LEGACY = "legacy"


class LicenseTier(Enum):
    """What the licence allows the platform to do (KLAERUNGEN B11)."""

    CATALOG = "catalog"
    DISPLAY = "display"
    PROCESSING = "processing"


class AdapterKind(Enum):
    """Which adapter speaks the protocol of the source (architekturplan.md 6.1)."""

    EARTH_SEARCH_V1 = "earth-search-v1"


class CoverageProvider(Enum):
    """How the coverage density of a dataset is answered (adr/0004 §5)."""

    UPSTREAM_AGGREGATION = "upstream-aggregation"
    LOCAL_SQL = "local-sql"
    SAMPLE = "sample"


class HealthStatus(Enum):
    """Result of the last check of the source (onboarding checklist, point 10)."""

    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ConfigError(ValueError):
    """A registry entry contradicts a rule from docs/."""


class UnknownDatasetError(LookupError):
    """No entry for this dataset id.

    Deliberately its own type: adr/0005 rule I turns an unknown collection into a
    404, and it must not be confused with an empty result that merely looks valid.
    """


@dataclass(frozen=True, slots=True)
class Capabilities:
    """What the platform offers for this dataset. No defaults — see KLAERUNGEN B10.

    Generic operators are harmless because nothing is implicitly on; dataset-specific
    ones (decomp.py) stay bound to a flag only matching data can set.
    """

    roi: bool
    time_range: bool
    band_math: bool
    interpolation: bool
    ml_processing: bool
    quad_pol: bool
    single_coverage_product: bool


@dataclass(frozen=True, slots=True)
class TermsOfUse:
    """The source's own terms, passed on to whoever receives data from us.

    Otto's decision of 19.09.2026: at a download the platform passes on the terms
    of the source, not a disclaimer of its own. The platform's own terms of use are
    a separate, open question (decision log, same date).

    ``notice`` holds one text, keyed ``en``. The platform offers no language
    choice (Otto, 22.09.2026): the key stays only so the text lines up with the
    same placeholder handling as ``attribution_modified``/``_unmodified``, not
    to invite a second language back in. It states the terms only: the
    attribution stays a separate text and is put in front of it where data
    leaves the platform (Otto, 19.09.2026), so that neither is repeated and a
    notice for unmodified data cannot end up claiming the data were modified.
    ``{terms_url}`` is filled with ``url``.
    """

    url: str
    notice: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.url.startswith("https://"):
            raise ConfigError(f"terms url {self.url!r} is not https")
        if set(self.notice) != {"en"}:
            raise ConfigError(
                "terms notice must carry exactly one text, keyed 'en' "
                "(the platform offers no language choice, Otto 22.09.2026)"
            )
        for language, text in self.notice.items():
            if "{terms_url}" not in text:
                raise ConfigError(f"terms notice [{language}] does not link the terms ({{terms_url}})")
            # Filling it in is the only thing ever done with this text, so a
            # placeholder we do not supply has to fail here, not at a download.
            try:
                text.format(terms_url=self.url)
            except (KeyError, IndexError) as error:
                raise ConfigError(
                    f"terms notice [{language}] uses a placeholder we do not fill: {error}"
                ) from None
        object.__setattr__(self, "notice", MappingProxyType(dict(self.notice)))


@dataclass(frozen=True, slots=True)
class LicenseInfo:
    """Licence as a machine-readable field plus the texts the platform has to pass on.

    ``spdx_id`` is None where no SPDX identifier exists; then name and URL carry the
    licence (projektuebersicht.md §5: "SPDX-Kennung, sonst Freitext").
    """

    spdx_id: str | None
    name: str
    url: str
    commercial_use: bool
    distribution: bool
    derivatives: bool
    share_alike: bool
    attribution_required: bool
    tier: LicenseTier
    attribution_modified: str | None
    attribution_unmodified: str | None
    terms: TermsOfUse | None


@dataclass(frozen=True, slots=True)
class AccessInfo:
    """Evidence that the source answers without a token (onboarding checklist, point 6)."""

    token_free_checked_at: date
    method: str
    cors: bool | None


@dataclass(frozen=True, slots=True)
class SourceInfo:
    """Where the items come from. adr/0005 rule I branches on this per collection.

    ``asset_hosts`` names the hosts the *assets* of this dataset lie on, which is a
    different question from where the catalogue answers (adr/0006 §3.3): the gateway
    builds its allowlist from both, and without the asset hosts every read of a COG
    is refused while the search still works. Hosts, not URLs — one entry per name,
    exactly as it appears in an asset href.
    """

    adapter: AdapterKind
    endpoint: str
    source_collection_id: str
    asset_hosts: tuple[str, ...]
    harvest_run: str | None


@dataclass(frozen=True, slots=True)
class CoverageInfo:
    """The three coverage fields adr/0004 §6 asks M1-04 for.

    ``max_geotile_level`` is the per-dataset cap: once a cell gets smaller than a
    footprint, the centroid rule draws a dot pattern instead of a coverage (§3.3).
    """

    provider: CoverageProvider
    typical_footprint_km: float
    max_geotile_level: int


@dataclass(frozen=True, slots=True)
class DefaultRender:
    """Standard visualisation (onboarding checklist, point 8; adr/0001 FZ7).

    The field names follow the STAC ``render`` extension, on adr/0006 §5's
    recommendation: the same values can later be published as ``renders`` on our own
    collection without a translation step, and they are the parameters the tile URL
    carries anyway (``assets``, ``rescale``, ``colormap_name``, ``expression``,
    ``resampling`` — adr/0006 §5 "Zu Frage 3").

    ``rescale`` is the *starting point* of the display controls, not a fixed stretch:
    the viewer asks ``/statistics`` for the item it shows and overwrites it (F18).
    """

    title: str
    assets: tuple[str, ...]
    rescale: tuple[tuple[float, float], ...] | None
    colormap_name: str | None
    expression: str | None
    resampling: str

    def __post_init__(self) -> None:
        if not self.assets and not self.expression:
            raise ConfigError("default_render needs an asset or an expression")
        for low, high in self.rescale or ():
            if low >= high:
                raise ConfigError(f"default_render rescale ({low}, {high}) is empty or inverted")
        if self.colormap_name is not None and len(self.assets) > 1:
            raise ConfigError(
                "default_render: a colormap paints one band, so it cannot go with several assets"
            )


@dataclass(frozen=True, slots=True)
class ViewerInfo:
    """What the viewer takes from the catalogue instead of from its own code.

    M2 fills one thing, and the field stays that narrow until something else is
    actually needed: ``group_by``, the key that turns a list of items into the steps
    of the time line and into the scenes of one mosaic (Inventar F5, F11).

    No default (KLAERUNGEN B10): a dataset whose items nobody has looked at has no
    grouping, and guessing one would group scenes that do not belong together.

    **``group_by`` — item property names, in the order in which they make the key.**
    ``properties.`` is implied and must not be written. One rule goes with the field,
    and it is the only one a reader has to know:

        A property that holds a STAC instant enters the key as its **UTC date**.

    Because a time line groups an acquisition day, not a second — and because the
    date is the one in UTC, an instant written in another offset is grouped by the
    day it falls on in UTC, not by its local day. :func:`group_key` is the reference
    implementation of exactly this rule, and the test beside it is what keeps the
    sentence above and the behaviour from drifting apart; M2-07a reads the field,
    mirrors that function and decides nothing of its own.

    For Sentinel-2 the key is the acquisition day plus the MGRS tile:
    ``("datetime", "grid:code")``.
    """

    group_by: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.group_by:
            raise ConfigError("viewer.group_by needs at least one property (KLAERUNGEN B10)")
        if len(set(self.group_by)) != len(self.group_by):
            raise ConfigError(f"viewer.group_by repeats a property: {self.group_by}")
        for name in self.group_by:
            if not name or name != name.strip():
                raise ConfigError(f"viewer.group_by entry {name!r} is not a property name")
            if name.startswith("properties."):
                raise ConfigError(
                    f"viewer.group_by entry {name!r} carries the `properties.` prefix, which is implied"
                )


class MissingProperty(LookupError):
    """An item does not carry a property the grouping key is built from.

    Its own type, and never silently skipped: a key that quietly loses one of its
    parts would merge two groups that do not belong together, and the time line
    would show one step where there are two.
    """


def group_key(item: Mapping[str, object], viewer: ViewerInfo) -> tuple[str, ...]:
    """The grouping key of one item, following the rule of :class:`ViewerInfo`.

    Each entry of ``group_by`` becomes one part of the key: a STAC instant as its
    UTC date (``YYYY-MM-DD``), anything else as its own text. The parts stay in the
    order the registry names them, because the key is read by people too.
    """
    properties = item.get("properties")
    if not isinstance(properties, Mapping):
        raise MissingProperty("the item carries no properties")
    key: list[str] = []
    for name in viewer.group_by:
        if name not in properties:
            raise MissingProperty(name)
        key.append(_key_part(properties[name]))
    return tuple(key)


def _key_part(value: object) -> str:
    """A STAC instant as its UTC date, everything else as its own text."""
    if isinstance(value, datetime):
        return _utc_date(value)
    if isinstance(value, str):
        try:
            return _utc_date(datetime.fromisoformat(value))
        except ValueError:
            # Not an instant — a grid code, a platform name, a bare date. It is the
            # key part as it stands; guessing a format for it is how a key starts
            # meaning two things.
            return value
    return str(value)


def _utc_date(instant: datetime) -> str:
    """The date in UTC. An instant without an offset is read as UTC, as STAC writes them."""
    if instant.tzinfo is not None:
        instant = instant.astimezone(timezone.utc)
    return instant.date().isoformat()


@dataclass(frozen=True, slots=True)
class HealthInfo:
    """Status and "last checked successfully" (KLAERUNGEN B12)."""

    status: HealthStatus
    last_checked_ok: date | None

    def __post_init__(self) -> None:
        if self.status is HealthStatus.OK and self.last_checked_ok is None:
            raise ConfigError("health status ok without a date of the last successful check (KLAERUNGEN B12)")


@dataclass(frozen=True, slots=True)
class SpatialExtent:
    """Bounding box in WGS84, as STAC writes it: west, south, east, north."""

    bbox: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        west, south, east, north = self.bbox
        if not (-180.0 <= west <= 180.0 and -180.0 <= east <= 180.0):
            raise ConfigError(f"bbox longitudes out of range: {self.bbox}")
        if not (-90.0 <= south <= 90.0 and -90.0 <= north <= 90.0):
            raise ConfigError(f"bbox latitudes out of range: {self.bbox}")
        if south >= north:
            raise ConfigError(f"bbox is empty or upside down: {self.bbox}")
        if west >= east:
            raise ConfigError(f"bbox is empty or inverted: {self.bbox} (a dateline crossing is not supported yet)")


@dataclass(frozen=True, slots=True)
class TemporalExtent:
    """Start and end of the dataset. ``None`` is open, as STAC allows.

    Instants, not dates: an end written as midnight would silently cut the last
    day off the extent. Both open means not yet read from the source — M1 does
    not fetch anything.
    """

    start: datetime | None
    end: datetime | None

    def __post_init__(self) -> None:
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ConfigError(f"temporal extent ends before it starts: {self.start} to {self.end}")


def max_geotile_level_for(typical_footprint_km: float) -> int:
    """Finest geotile level whose cell is still at least one footprint wide (adr/0004 §5)."""
    if typical_footprint_km <= 0:
        raise ConfigError("typical_footprint_km must be greater than zero")
    if typical_footprint_km > EARTH_CIRCUMFERENCE_KM:
        raise ConfigError(f"typical_footprint_km {typical_footprint_km} is wider than the planet")
    return math.floor(math.log2(EARTH_CIRCUMFERENCE_KM / typical_footprint_km))


@dataclass(frozen=True, slots=True)
class DatasetConfig:
    """One dataset, everything the platform decides about it before asking the source."""

    dataset_id: str
    title: str
    description: str
    # Onboarding checklist, point 3: a DOI where one exists, otherwise a persistent
    # citation. Both None means the point is still open for this dataset.
    doi: str | None
    citation: str | None
    data_class: DataClass
    format: DataFormat
    spatial_extent: SpatialExtent
    temporal_extent: TemporalExtent
    capabilities: Capabilities
    license: LicenseInfo
    access: AccessInfo
    source: SourceInfo
    coverage: CoverageInfo
    # None where the standard visualisation is not defined yet. For Sentinel-2 L2A
    # that is deliberate: m1-fundament.md §2 puts it in M2.
    default_render: DefaultRender | None
    # None where nobody has decided how the viewer groups the items of this dataset.
    viewer: ViewerInfo | None
    health: HealthInfo

    def __post_init__(self) -> None:
        self._check_license_is_identifiable()
        self._check_license_tier()
        self._check_attribution()
        self._check_coverage()
        self._check_source()

    def _check_license_is_identifiable(self) -> None:
        """An SPDX identifier, or else name and URL (projektuebersicht.md §5)."""
        if self.license.spdx_id:
            return
        if not (self.license.name and self.license.url):
            raise ConfigError(
                f"{self.dataset_id}: a licence without an SPDX identifier needs a name and a URL"
            )

    def _check_license_tier(self) -> None:
        """KLAERUNGEN B11: display and processing need distribution and modification."""
        if self.license.tier is LicenseTier.CATALOG:
            return
        missing = [
            name
            for name, allowed in (("distribution", self.license.distribution), ("derivatives", self.license.derivatives))
            if not allowed
        ]
        if missing:
            raise ConfigError(
                f"{self.dataset_id}: tier {self.license.tier.value} needs {' and '.join(missing)}=True "
                "(KLAERUNGEN B11 — without distribution and modification a dataset stays a "
                "catalogue entry with a link)"
            )

    def _check_attribution(self) -> None:
        """A required attribution without its text cannot be delivered with a download."""
        if self.license.attribution_required and not (
            self.license.attribution_modified or self.license.attribution_unmodified
        ):
            raise ConfigError(
                f"{self.dataset_id}: attribution_required=True without an attribution text"
            )

    def _check_coverage(self) -> None:
        """The grid cap follows from the footprint; a one-off product has no density."""
        if self.coverage.max_geotile_level < 0:
            raise ConfigError(f"{self.dataset_id}: max_geotile_level must not be negative")
        allowed = max_geotile_level_for(self.coverage.typical_footprint_km)
        if self.coverage.max_geotile_level > allowed:
            raise ConfigError(
                f"{self.dataset_id}: max_geotile_level {self.coverage.max_geotile_level} is finer than "
                f"z{allowed}, the finest level whose cell still holds a "
                f"{self.coverage.typical_footprint_km} km footprint (adr/0004 §5)"
            )
        if (
            self.capabilities.single_coverage_product
            and self.coverage.provider is CoverageProvider.UPSTREAM_AGGREGATION
        ):
            raise ConfigError(
                f"{self.dataset_id}: a one-off product has an extent, not a density — "
                "upstream aggregation does not apply (adr/0004 §5)"
            )

    def _check_source(self) -> None:
        """Only https leaves the house (KLAERUNGEN B8); gateway enforces the rest."""
        if not self.source.endpoint.startswith("https://"):
            raise ConfigError(
                f"{self.dataset_id}: endpoint {self.source.endpoint!r} is not https (KLAERUNGEN B8)"
            )
        for host in self.source.asset_hosts:
            # A host, not a URL: what goes into the allowlist is compared against the
            # host of an href, so a scheme, a path or a port here would never match and
            # would quietly close the read path instead of opening it (adr/0006 §3.3).
            # https itself is not a choice per dataset — `gateway.inspect_url` refuses
            # every other scheme for everyone.
            if not host or host != host.strip().lower() or any(c in host for c in ":/?#@ ") or "." not in host:
                raise ConfigError(
                    f"{self.dataset_id}: asset_hosts entry {host!r} is not a bare host name "
                    "(no scheme, no path, no port, lower case)"
                )


class DatasetRegistry:
    """The entries, looked up by dataset id."""

    def __init__(self, entries: tuple[DatasetConfig, ...]) -> None:
        self._by_id = {entry.dataset_id: entry for entry in entries}
        if len(self._by_id) != len(entries):
            raise ConfigError("duplicate dataset_id in the registry")

    def get(self, dataset_id: str) -> DatasetConfig:
        """Return the entry, or raise ``UnknownDatasetError`` — never None (adr/0005 rule I)."""
        try:
            return self._by_id[dataset_id]
        except KeyError:
            raise UnknownDatasetError(dataset_id) from None

    def __contains__(self, dataset_id: object) -> bool:
        return dataset_id in self._by_id

    def __iter__(self) -> Iterator[DatasetConfig]:
        return iter(self._by_id.values())

    def __len__(self) -> int:
        return len(self._by_id)
