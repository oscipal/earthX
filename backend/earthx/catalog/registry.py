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
from dataclasses import dataclass
from datetime import date
from enum import Enum

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
class LicenseInfo:
    """Licence as a machine-readable field plus the texts the platform has to pass on.

    ``spdx_id`` is None where no SPDX identifier exists; then name and URL carry the
    licence (projektuebersicht.md §5: "SPDX-Kennung, sonst Freitext").
    """

    spdx_id: str | None
    name: str
    url: str
    stac_license: str
    commercial_use: bool
    derivatives: bool
    share_alike: bool
    attribution_required: bool
    tier: LicenseTier
    attribution_modified: str | None
    attribution_unmodified: str | None
    liability_notice: str | None


@dataclass(frozen=True, slots=True)
class AccessInfo:
    """Evidence that the source answers without a token (onboarding checklist, point 6)."""

    token_free_checked_at: date
    method: str
    cors: bool | None


@dataclass(frozen=True, slots=True)
class SourceInfo:
    """Where the items come from. adr/0005 rule I branches on this per collection."""

    adapter: AdapterKind
    endpoint: str
    source_collection_id: str
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
    """Standard visualisation (onboarding checklist, point 8)."""

    bands: tuple[str, ...]
    stretch: tuple[float, float]
    colormap: str | None


@dataclass(frozen=True, slots=True)
class HealthInfo:
    """Status and "last checked successfully" (KLAERUNGEN B12)."""

    status: HealthStatus
    last_checked_ok: date | None


@dataclass(frozen=True, slots=True)
class SpatialExtent:
    """Bounding box in WGS84, as STAC writes it: west, south, east, north."""

    bbox: tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class TemporalExtent:
    """Start and end of the dataset. ``None`` is open, as STAC allows.

    Both open means not yet read from the source — M1 does not fetch anything.
    """

    start: date | None
    end: date | None


def max_geotile_level_for(typical_footprint_km: float) -> int:
    """Finest geotile level whose cell is still at least one footprint wide (adr/0004 §5)."""
    if typical_footprint_km <= 0:
        raise ConfigError("typical_footprint_km must be greater than zero")
    return math.floor(math.log2(EARTH_CIRCUMFERENCE_KM / typical_footprint_km))


@dataclass(frozen=True, slots=True)
class DatasetConfig:
    """One dataset, everything the platform decides about it before asking the source."""

    dataset_id: str
    title: str
    description: str
    data_class: DataClass
    format: DataFormat
    spatial_extent: SpatialExtent
    temporal_extent: TemporalExtent
    capabilities: Capabilities
    license: LicenseInfo
    access: AccessInfo
    source: SourceInfo
    coverage: CoverageInfo
    default_render: DefaultRender
    health: HealthInfo

    def __post_init__(self) -> None:
        self._check_license_tier()
        self._check_attribution()
        self._check_coverage()

    def _check_license_tier(self) -> None:
        """KLAERUNGEN B11: display and processing need distribution and modification."""
        if self.license.tier is LicenseTier.CATALOG:
            return
        if not self.license.derivatives:
            raise ConfigError(
                f"{self.dataset_id}: tier {self.license.tier.value} needs derivatives=True "
                "(KLAERUNGEN B11 — a no-derivatives dataset stays a catalogue entry with a link)"
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

    def __iter__(self):
        return iter(self._by_id.values())

    def __len__(self) -> int:
        return len(self._by_id)
