"""Dataset registry: what the platform knows about a dataset before it asks the source.

One entry per dataset, as a frozen dataclass; since M5-13 the entries are YAML files under
``backend/catalog/`` that ``catalog.entry_files`` reads into these classes (KLAERUNGEN B13, stage 2). The
fields mirror the ``earthx:`` fields of architekturplan.md 5.1, so that
``collection.to_stac_collection`` is a mapping and not an interpretation.

Nothing here has a default value where KLAERUNGEN B10 asks for a flag to be set
deliberately. Forgetting one is a ``TypeError`` at the entry, not a wrong answer
later on.
"""

from __future__ import annotations

import keyword
import math
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from fnmatch import fnmatchcase
from types import MappingProxyType
from typing import Protocol

# Circumference at the equator, in kilometres. Geotile level z splits it into
# 2**z columns, so a cell is EARTH_CIRCUMFERENCE_KM / 2**z wide (adr/0004 §5).
EARTH_CIRCUMFERENCE_KM = 40075.0

# Highest tile zoom a registry entry may release (M2-10). MapLibre's own ceiling is
# z22 and a Web Mercator tile there is about 4 cm wide at the equator — several
# orders past any imagery this platform serves. A level beyond this is an entry
# mistake, not a wish, and the same reasoning as MAX_GEOTILE_LEVEL in
# catalog/coverage.py: a grid finer than the data is a number, not a picture.
MAX_TILE_ZOOM = 22

# A unit is a symbol, not a sentence (UCUM: "m", "1", "mm/h"); the longest in use stays far below this.
MAX_UNIT_CHARS = 32
MAX_GROUP_CHARS = 24


class DataClass(Enum):
    """Data type class of a dataset (projektuebersicht.md §5). Raster only for now."""

    RASTER_TIME_SERIES = "raster-time-series"
    RASTER_STATIC = "raster-static"


class DataFormat(Enum):
    """Storage format. The order is the preference of the onboarding checklist, point 5."""

    ZARR = "zarr"
    COG = "cog"
    LEGACY = "legacy"


class Georeferencing(Enum):
    """Where the position of a pixel comes from, the same way in tile, crop, job and runner (adr/0018 F1, DS-04a).

    ``GEOTRANSFORM``: the file carries a CRS and a geotransform. ``GCP_TPS``: the file carries only ground control
    points (Sentinel-1 GRD in radar geometry); the readers place it with a thin-plate spline through them. The values
    are those of ``earthx.readers.cog.Georeferencing``, which ``readers`` keeps on its own because it may not import
    ``catalog`` (architekturplan.md 3.1).
    """

    GEOTRANSFORM = "geotransform"
    GCP_TPS = "gcp_tps"


class LicenseTier(Enum):
    """What the licence allows the platform to do (KLAERUNGEN B11)."""

    CATALOG = "catalog"
    DISPLAY = "display"
    PROCESSING = "processing"


class AdapterKind(Enum):
    """Which adapter speaks the protocol of the source (architekturplan.md 6.1)."""

    EARTH_SEARCH_V1 = "earth-search-v1"
    # M3-11b: this one only *materializes* items (adapters.materialize_items), it
    # never searches or answers a single-item request — its `AdapterSpec` in
    # `adapters/spec.py` offers `materialize` alone. A `SourceInfo` naming this
    # kind always carries `item_holding=MATERIALIZED` (checked by
    # `DatasetConfig._check_item_holding` only indirectly, through the
    # coverage-provider pairing — nothing here ties an `AdapterKind` to an
    # `ItemHolding` value, by design, per M3-11a K-05).
    COP_DEM_BUCKET = "cop-dem-bucket"
    # M5-07: a materializer like the one above, for both ESA WorldCover states (adr/0023 §8.3).
    ESA_WORLDCOVER_BUCKET = "esa-worldcover-bucket"


class ItemHolding(Enum):
    """Where the items of a dataset live (architekturplan.md 5.2, M3-11a K-05).

    A separate question from :class:`AdapterKind`: the adapter names *which*
    protocol produces the items, this names *where they end up*. Before M3-11a a
    collection counted as materialized whenever its ``adapter`` was one this
    dispatch did not know — a coincidence, not a decision, and a typo in the
    adapter value would have quietly fallen into that case too (adr/0009 §11,
    M3-02 K-05). Every entry sets this explicitly (KLAERUNGEN B10).
    """

    FEDERATED = "federated"
    MATERIALIZED = "materialized"


class CoverageProvider(Enum):
    """How the coverage density of a dataset is answered (adr/0004 §5)."""

    UPSTREAM_AGGREGATION = "upstream-aggregation"
    LOCAL_SQL = "local-sql"


class HealthStatus(Enum):
    """Result of the last check of the source (onboarding checklist, point 10)."""

    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class BrowseMode(Enum):
    """What the viewer shows right after a search, before any tile is requested
    (M3-12, Otto 26.09.2026 Nachtrag 2 / M3-11b F11).

    ``QUICKLOOK`` — the source publishes a quicklook a browser can load
    cross-origin and crop on its own canvas (Sentinel-2 COG). ``PREVIEW_TILES``
    — no quicklook, but the dataset is released from a zoom level coarse
    enough that one tile over an item stands in for one (the Zarr dataset,
    which has no thumbnail/overview/preview/visual asset anywhere, adr/0007
    §12.7). ``FULL_RESOLUTION`` — neither: the viewer shows the AOI crop in
    full resolution straight after the search, the way the DEM does, because
    it has no browsable quicklook and is not meaningfully previewable at a
    coarse tile level either.

    No default (KLAERUNGEN B10): before this field, the frontend guessed this
    from whether an item happened to carry a thumbnail asset (``datasets.ts``
    ``quicklookPlan``) — a source-specific fact the registry now states
    outright instead.
    """

    QUICKLOOK = "quicklook"
    PREVIEW_TILES = "preview_tiles"
    FULL_RESOLUTION = "full_resolution"


class Maturity(Enum):
    """How settled the *source* itself is — not a measurement like ``HealthStatus``,
    a fact about the dataset that belongs with licence and attribution
    (architekturplan.md 5.1, tenth ``earthx:`` field; adr/0007 §12.11 point 14).

    A source can answer every request correctly and still be ``STAGING``: the
    provider's own naming says it may disappear without notice. The platform must
    not let a user find that out only once it does.
    """

    STABLE = "stable"
    STAGING = "staging"
    EXPERIMENTAL = "experimental"


class DatasetCategory(Enum):
    """The group of a dataset in the Data catalogue (UI-05 plan §5, F1), in the order the catalogue shows the groups."""

    OPTICAL = "optical"
    RADAR = "radar"
    ELEVATION = "elevation"
    LAND_COVER = "land_cover"
    WEATHER_CLIMATE = "weather_climate"


class LegalStatus(Enum):
    """Whether the legal footing of the source is settled (adr/0024 R1, R3). Only Otto sets it, like every licence tier.

    ``UNCLEAR`` marks a prototype source: loaded only in Otto's local instance (adr/0024 R5), its id carries
    :data:`PROTOTYPE_PREFIX`. It says nothing about what the source needs to be read; that is ``AccessInfo.account``.
    """

    CLEARED = "cleared"
    UNCLEAR = "unclear"


class AccountKind(Enum):
    """What reading the assets of a dataset needs (adr/0027 §6.1, F8). Independent of ``LegalStatus``."""

    #: Metadata and assets anonymous, without any proof.
    NONE = "none"
    #: The source hands everyone a proof without an account (adr/0018 F4, conditions (a)-(d)).
    ANONYMOUS_TOKEN = "anonymous_token"
    #: The assets need a free account (CDSE download, Earthdata, CDS, ...): a catalogue entry with a link only (W0).
    FREE_ACCOUNT = "free_account"
    #: The assets need a cloud account of one's own, and the reader pays the transfer: W0 only.
    REQUESTER_PAYS = "requester_pays"


class AccountPath(Enum):
    """The ways to read an account source beyond the link (adr/0027 §5). None is released in M5."""

    W2A = "W2a"
    W2B = "W2b"
    W3 = "W3"
    W4 = "W4"


#: The prefix of every prototype dataset id (adr/0024 R3): visible in each address, recipe, file name and cache key.
PROTOTYPE_PREFIX = "proto-"


class ProviderRole(Enum):
    """The roles of a STAC provider (STAC Collection spec, Provider Object)."""

    PRODUCER = "producer"
    LICENSOR = "licensor"
    PROCESSOR = "processor"
    HOST = "host"


#: ``data_region`` of an entry whose storage operator or place is not shown yet (adr/0023 F7).
UNKNOWN_DATA_REGION = "unknown"
_DATA_REGION_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*:[a-z0-9]+(?:-[a-z0-9]+)*")
# Virtual-hosted S3 names (adr/0022 §7.2): with a region (`<bucket>.s3.<region>.amazonaws.com`) and without.
_AWS_REGION_HOST_RE = re.compile(r"[a-z0-9.-]+\.s3[.-](?P<region>[a-z]{2}(?:-gov)?-[a-z]+-\d)\.amazonaws\.com")
_AWS_HOST_RE = re.compile(r"(?:[a-z0-9.-]+\.)?amazonaws\.com")


class ConfigError(ValueError):
    """A registry entry contradicts a rule from docs/."""


_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:")
_DOI_NAME = re.compile(r"10\.\d{4,9}/[^\s{}]+")


#: What ``readers.zarr_reader`` puts between the variables of one Zarr asset key (``SR_10m:b04,b03``). The catalog
#: may not import the readers; a test holds the two equal.
VARIABLE_LIST_SEPARATOR = ","


def single_asset_keys(asset: str, separator: str | None) -> list[str]:
    """The keys ``band_units`` is read by for one asset key an order names: a Zarr group has one per variable."""
    if separator is None:
        return [asset]
    group, found, variables = asset.partition(separator)
    if not found:
        return [asset]
    return [f"{group}{separator}{variable}" for variable in variables.split(VARIABLE_LIST_SEPARATOR)]


def doi_name(doi: str | None) -> str | None:
    """The DOI name (``10.5270/...``) of a registry ``doi``, which may be a resolver URL.

    The entries keep the URL the source's ``cite-as`` link gives (adr/0014 §10.2);
    STAC's ``sci:doi`` and BibTeX's ``doi`` want the name. ``None`` for a missing or
    blank value; anything else that is no DOI name is a :class:`ConfigError`, so a
    typo fails here rather than ending up as a wrong citation.
    """
    if doi is None or not doi.strip():
        return None
    text = doi.strip()
    for prefix in _DOI_PREFIXES:
        if text.lower().startswith(prefix):
            text = text[len(prefix) :]
            break
    if not _DOI_NAME.fullmatch(text):
        raise ConfigError(f"{doi!r} is no DOI name or DOI resolver URL")
    return text


class UnknownDatasetError(LookupError):
    """No entry for this dataset id.

    Deliberately its own type: adr/0005 rule I turns an unknown collection into a
    404, and it must not be confused with an empty result that merely looks valid.
    """


class RetiredDatasetError(UnknownDatasetError):
    """The id belongs to a dataset that left the registry (adr/0017).

    An :class:`UnknownDatasetError` for everything that does not care why; the routes that
    can say why answer ``410`` with :attr:`retired` instead of ``404`` or ``422``.
    """

    def __init__(self, retired: RetiredDataset) -> None:
        super().__init__(retired.dataset_id)
        self.retired = retired


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
    #: Reprojection and resampling to another grid (adr/0014 §5.3, F6; R3). A
    #: method other than ``nearest`` needs ``interpolation`` as well.
    reprojection: bool
    #: ``mask`` hides the classes a recipe names of the layer in ``DatasetConfig.mask``
    #: (adr/0014 §15m); set exactly where that layer is described.
    masking: bool
    #: ``mask_values`` hides the pixels where any band meets a condition (DS-06). Generic like band math: it needs
    #: no layer in the entry, but every entry switches it on by itself (B10).
    value_masking: bool
    #: ``normalize``: a fixed range onto another (M4-18). Generic like band math, but
    #: every entry switches it on by itself (B10).
    normalization: bool
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
    """What reading the source needs, and the evidence of the anonymous check (onboarding checklist, point 6).

    ``token_free_checked_at`` is the day of that check, ``None`` exactly where ``account`` says it cannot pass
    (``free_account``, ``requester_pays``). ``account_provider`` names the identity service of an account source for
    the hint and the link, never the address of a token endpoint; ``account_paths`` the ways released for this dataset
    beyond the link. The rules between the four, and with the licence tier, are ``DatasetConfig._check_access``
    (adr/0027 §6.1).
    """

    token_free_checked_at: date | None
    method: str
    cors: bool | None
    account: AccountKind
    account_provider: str | None
    account_paths: tuple[AccountPath, ...]


@dataclass(frozen=True, slots=True)
class SourceInfo:
    """Where the items come from. adr/0005 rule I branches on this per collection.

    ``asset_hosts`` names the hosts the *assets* of this dataset lie on, which is a
    different question from where the catalogue answers (adr/0006 §3.3): the gateway
    builds its allowlist from both, and without the asset hosts every read of a COG
    is refused while the search still works. Hosts, not URLs — one entry per name,
    exactly as it appears in an asset href.

    ``item_holding`` decides whether ``/stac/search`` federates a live request to
    ``endpoint`` (``FEDERATED``) or answers from this platform's own pgstac
    (``MATERIALIZED``, M3-11a) — see :class:`ItemHolding`. ``adapter`` stays set
    either way: for a federated dataset it is asked at search and item-fetch time,
    for a materialized one it is the adapter the one-off load in ``discovery`` used
    to build the items in the first place (M3-11b).

    ``data_region`` is where the storage of the assets lies, as ``<operator>:<place>`` with the operator of the
    storage, not the agency (``aws:eu-central-1``, ``eodc:vienna``), or ``unknown`` until both are shown
    (adr/0022 §7.2, adr/0023 F7). It sits next to ``asset_hosts`` because the start check reads it against them
    (M5-07 plan F1).
    """

    adapter: AdapterKind
    endpoint: str
    source_collection_id: str
    asset_hosts: tuple[str, ...]
    item_holding: ItemHolding
    data_region: str


# An https address with a host and nothing blank in it: what the catalogue may put behind a link.
_HTTPS_URL_RE = re.compile(r"https://[^\s/?#]+(?:[/?#]\S*)?")


@dataclass(frozen=True, slots=True)
class Provider:
    """One organisation behind the data, as a STAC provider (UI-05 plan §5, F2), taken over from the source.

    ``url`` is None where the source names none or only a plain ``http`` one: the catalogue links it, and a link the
    platform shows leaves the house over https only (KLAERUNGEN B8).
    """

    name: str
    roles: tuple[ProviderRole, ...]
    url: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ConfigError("a provider needs a name")
        if not isinstance(self.roles, tuple) or not self.roles:
            raise ConfigError(f"provider {self.name!r} names no role")
        if not all(isinstance(role, ProviderRole) for role in self.roles):
            raise ConfigError(f"provider {self.name!r}: every role must be one of {[r.value for r in ProviderRole]}")
        if len(set(self.roles)) != len(self.roles):
            raise ConfigError(f"provider {self.name!r} names a role twice")
        if self.url is not None and not (isinstance(self.url, str) and _HTTPS_URL_RE.fullmatch(self.url)):
            raise ConfigError(f"provider {self.name!r}: url {self.url!r} is not https")


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
class ZarrInfo:
    """What ``readers.zarr_reader`` needs to know about *this* store's layout,
    beyond what it assumes by default (adr/0007 §7 point 7, §12.11 point 2).

    ``None`` for the whole dataset (the field on :class:`DatasetConfig`) covers
    every COG dataset and a Zarr dataset that addresses exactly the way M2-09a's
    synthetic Mini-Zarr does — the variable is the asset href's own last path
    segment, and ``multiscales`` is either absent or not needed.

    ``variable_separator`` — an asset whose href already names a *group*, not a
    variable (measured at the EOPF Zarr products: ``SR_10m`` points at
    ``…/measurements/reflectance/r10m``, a group with several bands) cannot say
    which variable a tile wants from its href alone. The tile URL's asset key
    carries the variable instead, split off by this separator — a key
    ``"SR_10m:b04"`` with separator ``":"`` names the item asset ``SR_10m`` and,
    within the group its href points at, the variable ``b04``. The reader that
    reads this field is M2-09b-2; here it is only recorded.

    ``multiscales_convention`` — the name and version ``multiscales`` declares at
    the store's own metadata, kept as a record because it is a pilot
    (``zarr-conventions/multiscales`` v0.1 at the time of measurement) and *not*
    a promise that the reader parses only that one version. ``None`` where the
    store carries no ``multiscales`` attribute at all.
    """

    variable_separator: str | None
    multiscales_convention: str | None

    def __post_init__(self) -> None:
        if self.variable_separator is not None and not self.variable_separator:
            raise ConfigError("zarr.variable_separator must not be an empty string")


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
        if self.expression is not None:
            # The tiler no longer takes a free `expression` (plan M4-09, F3): an expression is
            # `op=band_math`, in physical values. Until M4-13 maps the standard visualisation
            # onto `op`, a registry entry that carried one would be a visualisation that 400s.
            raise ConfigError("default_render.expression is not served: the tiler takes op=band_math (M4-09)")
        if not self.assets:
            raise ConfigError("default_render needs an asset")
        for low, high in self.rescale or ():
            if low >= high:
                raise ConfigError(f"default_render rescale ({low}, {high}) is empty or inverted")
        if self.colormap_name is not None and len(self.assets) > 1:
            raise ConfigError(
                "default_render: a colormap paints one band, so it cannot go with several assets"
            )


def _check_property_names(field_name: str, values: tuple[str, ...]) -> None:
    """The one rule ``group_by`` and ``results_group_by`` (M3-12) share: at least
    one property, no repeats, and no ``properties.`` prefix (the prefix is
    implied, ``ViewerInfo`` reads a bare name)."""
    if not values:
        raise ConfigError(f"viewer.{field_name} needs at least one property (KLAERUNGEN B10)")
    if len(set(values)) != len(values):
        raise ConfigError(f"viewer.{field_name} repeats a property: {values}")
    for name in values:
        if not name or name != name.strip():
            raise ConfigError(f"viewer.{field_name} entry {name!r} is not a property name")
        if name.startswith("properties."):
            raise ConfigError(
                f"viewer.{field_name} entry {name!r} carries the `properties.` prefix, which is implied"
            )


@dataclass(frozen=True, slots=True)
class ViewerInfo:
    """What the viewer takes from the catalogue instead of from its own code.

    M2 fills three things: ``group_by``, the key that turns a list of items into the
    steps of the time line and into the scenes of one mosaic (Inventar F5, F11), and
    the two zoom levels that bound the tile path for this dataset (M2-10, Otto
    22.09.2026 F1 a).

    No default on any of them (KLAERUNGEN B10): a dataset whose items nobody has
    looked at has no grouping, and guessing one would group scenes that do not belong
    together; a dataset nobody has measured has no released zoom range either, and
    guessing one would let a client ask for a tile that costs a hundred times what
    the source can add to it.

    **``min_zoom`` / ``max_zoom`` — the tile levels this dataset is released for.**
    Below ``min_zoom`` one tile shows several scenes, which is the coverage map's job
    and not the tile path's (adr/0007 §12.10). Above ``max_zoom`` the source has
    nothing finer to give, so a client overzooms the last level instead of asking for
    a tile that reads the same pixels again. Both are read by the viewer *and*
    enforced by the tile route (``api.tiler``, Otto's first addition to F1): the field
    is the boundary of the tile path, not a recommendation to a well-behaved client.

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

    M3-12 adds three more fields, all still without a default (B10):

    **``browse``** — see :class:`BrowseMode`.

    **``quicklook_nodata_max``** — for ``browse=QUICKLOOK`` only: a quicklook
    pixel with every band at or below this value is keyed transparent, so the
    dark padding around an irregular scene does not paint over the basemap
    (Sentinel-2's JPEGs are ``16``). ``None`` where the quicklook needs no such
    freistellung. Must be ``None`` for the other two ``browse`` values — a
    dataset that shows no quicklook has nothing for this to apply to.

    **``results_group_by``** — the grouping key the *results list* heads its
    groups by (V-4/D30) and the download route reuses as its per-group merge
    (P19, M3-17): the same rule as ``group_by`` above, but a second field
    because it may name a property ``group_by`` deliberately does not (M3-02
    F-01) — Sentinel-2 COG groups its tile-and-day key display by day and
    overpass instead (``s2:datatake_id``), a Zarr dataset by day and
    overpass under its own vocabulary where a source has one, and the DEM has
    only one group for the whole dataset (``start_datetime``, every tile
    shares the one acquisition period, M3-11b F7). Unlike the pre-M3-12
    ``displayGroupBy`` in the frontend, there is no runtime fallback to
    ``group_by`` when an item happens to lack the property: the registry
    states the key that always applies, and a genuinely broken item still
    surfaces as ``MissingProperty``, the same way a broken ``group_by`` item
    always has.

    A note on ``min_zoom`` for a dataset released from tiles that are already
    clipped to their own item's extent (M3-09 onward: the tile URL of one item
    is clipped to that item; the mosaic tile of M4-17 is the one URL that names
    several items, from z8 up whatever ``min_zoom`` says): the reasoning above
    ("below it one tile shows several scenes") does not hold there — an item's own tile costs the same
    at every zoom down to where it stops touching its neighbours (measured for
    the DEM, M3-12 plan step §3: z0 through z8 read the same overview block).
    ``min_zoom`` is then a cost floor on how many tiles a viewport can ask for
    at once, not a resolution floor; the DEM sets it to ``0`` on that basis.
    """

    group_by: tuple[str, ...]
    min_zoom: int
    max_zoom: int
    browse: BrowseMode
    quicklook_nodata_max: int | None
    results_group_by: tuple[str, ...]

    def __post_init__(self) -> None:
        self._check_group_by()
        self._check_zoom()
        self._check_results_group_by()
        self._check_browse()

    def _check_group_by(self) -> None:
        _check_property_names("group_by", self.group_by)

    def _check_results_group_by(self) -> None:
        _check_property_names("results_group_by", self.results_group_by)

    def _check_browse(self) -> None:
        if self.browse is BrowseMode.QUICKLOOK:
            value = self.quicklook_nodata_max
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ConfigError("viewer.quicklook_nodata_max must be a whole number 0..255, or None")
                if not 0 <= value <= 255:
                    raise ConfigError(f"viewer.quicklook_nodata_max {value} lies outside 0..255")
        elif self.quicklook_nodata_max is not None:
            raise ConfigError(
                f"viewer.quicklook_nodata_max is set but browse is {self.browse.value}, not quicklook "
                "(a dataset without a browsable quicklook has nothing for it to key transparent)"
            )

    def _check_zoom(self) -> None:
        for name, level in (("min_zoom", self.min_zoom), ("max_zoom", self.max_zoom)):
            # `bool` is an `int` in Python, and `True` as a zoom level is a typo
            # nobody meant — a registry entry says a number or it says nothing.
            if isinstance(level, bool) or not isinstance(level, int):
                raise ConfigError(f"viewer.{name} must be a whole zoom level, not {level!r}")
            if not 0 <= level <= MAX_TILE_ZOOM:
                raise ConfigError(f"viewer.{name} {level} lies outside 0..{MAX_TILE_ZOOM}")
        if self.min_zoom > self.max_zoom:
            raise ConfigError(
                f"viewer zoom range is empty: min_zoom {self.min_zoom} is above max_zoom {self.max_zoom}"
            )


class MissingProperty(LookupError):
    """An item does not carry a property the grouping key is built from.

    Its own type, and never silently skipped: a key that quietly loses one of its
    parts would merge two groups that do not belong together, and the time line
    would show one step where there are two.
    """


def group_key(
    item: Mapping[str, object], viewer: ViewerInfo, fields: Sequence[str] | None = None
) -> tuple[str, ...]:
    """The grouping key of one item, following the rule of :class:`ViewerInfo`.

    Each entry of ``fields`` becomes one part of the key: a STAC instant as its
    UTC date (``YYYY-MM-DD``), anything else as its own text. The parts stay in the
    order the registry names them, because the key is read by people too. ``fields``
    is ``group_by`` unless the caller names the other key of the registry,
    ``results_group_by`` — the overpass (P19, M4-12), which one mosaic job covers.
    """
    properties = item.get("properties")
    if not isinstance(properties, Mapping):
        raise MissingProperty("the item carries no properties")
    key: list[str] = []
    for name in viewer.group_by if fields is None else fields:
        if name not in properties:
            raise MissingProperty(name)
        key.append(_key_part(properties[name]))
    return tuple(key)


def overpass_key(item: Mapping[str, object], viewer: ViewerInfo) -> tuple[str, ...]:
    """The key of the overpass ``item`` belongs to: its ``results_group_by`` (P19, M4-12a).

    The one rule for "which scenes are one overpass": the groups of the results list (mirrored in the front end's
    ``grouping.ts``), the mosaic job and the mosaic tile, and the search per pass all take it from here. Raises
    :class:`MissingProperty` for an item that lacks a part of it."""
    return group_key(item, viewer, viewer.results_group_by)


def group_by_overpass(
    items: Iterable[Mapping[str, object]], viewer: ViewerInfo
) -> dict[tuple[str, ...], list[Mapping[str, object]]]:
    """``items`` grouped by :func:`overpass_key`, each group in the order the items came in, the groups in order of their first.

    An item without a key part raises :class:`MissingProperty`, as the list of results fails on it (``grouping.ts``)."""
    groups: dict[tuple[str, ...], list[Mapping[str, object]]] = {}
    for item in items:
        groups.setdefault(overpass_key(item, viewer), []).append(item)
    return groups


#: The STAC instant of a scene's acquisition; where the overpass key names it, the dataset has a day of acquisition.
ACQUISITION_INSTANT = "datetime"


def acquisition_day(item: Mapping[str, object], viewer: ViewerInfo) -> date | None:
    """The UTC day a scene was acquired — the day of its overpass — or ``None`` if the dataset has none.

    The one rule for "which day is this scene's" (Otto, 14.10.2026), taken from the overpass key
    (``results_group_by``): where it holds the STAC instant ``datetime``, that part of the key is the
    day, turned into the UTC date by :func:`group_key` — for that part alone, so an item that lacks
    another part of the key (the datatake) still has its day. A dataset whose key holds no such
    instant has no single day of acquisition: the DEM's key is ``start_datetime``, the start of one
    acquisition period shared by every tile. An item that lacks the property, or holds no instant
    there, has none either: a name is no reason to refuse the item.
    """
    if ACQUISITION_INSTANT not in viewer.results_group_by:
        return None
    try:
        (day,) = group_key(item, viewer, (ACQUISITION_INSTANT,))
        return date.fromisoformat(day)
    except (MissingProperty, ValueError):
        return None


#: The STAC properties that date an acquisition: the instant, or the start and end of a period.
ACQUISITION_PROPERTIES = ("datetime", "start_datetime", "end_datetime")


class AcquisitionYearMissing(ValueError):
    """An item names no usable acquisition date, so the year of its attribution is unknown."""


@dataclass(frozen=True, slots=True)
class AcquisitionYears:
    """The calendar years (UTC) the scenes of an order were acquired in: the one year, or the span.

    What "[Year]" of the Sentinel notice means is not defined by the Sentinel Data Legal Notice; the
    platform reads it as the year of acquisition (Otto, 25.10.2026, NM4-01, adr/0014 §4.5) and writes
    several years as a span, ``2024–2025``.
    """

    first: int
    last: int

    def __post_init__(self) -> None:
        if not 1 <= self.first <= self.last <= 9999:
            raise ValueError("the first year is not after the last, and both have four digits")

    def __str__(self) -> str:
        return str(self.first) if self.first == self.last else f"{self.first}\N{EN DASH}{self.last}"


def acquisition_years(items: Iterable[Mapping[str, object]]) -> AcquisitionYears:
    """The years ``items`` were acquired in, from ``datetime``, ``start_datetime`` and ``end_datetime``.

    Every instant an item carries counts, so a period that crosses New Year gives a span. Never the
    clock: an item with none of the three, or only text that is no instant, raises
    :class:`AcquisitionYearMissing`, as does an empty ``items``.
    """
    years: list[int] = []
    for item in items:
        properties = item.get("properties")
        found = [
            _instant_year(properties[name])
            for name in ACQUISITION_PROPERTIES
            if isinstance(properties, Mapping) and properties.get(name) is not None
        ]
        if not found:
            raise AcquisitionYearMissing("an item carries no acquisition date (datetime or start_datetime)")
        years.extend(found)
    if not years:
        raise AcquisitionYearMissing("no item to take an acquisition date from")
    return AcquisitionYears(min(years), max(years))


def _instant_year(value: object) -> int:
    if not isinstance(value, (str, datetime)):
        raise AcquisitionYearMissing("an item's acquisition date is no instant")
    try:
        instant = datetime.fromisoformat(value) if isinstance(value, str) else value
    except ValueError:
        raise AcquisitionYearMissing("an item's acquisition date is no instant") from None
    if instant.tzinfo is not None:
        instant = instant.astimezone(timezone.utc)
    return instant.year


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
    """Status of the source (KLAERUNGEN B12, Fassung v1.1 of point 10).

    Carries no "last checked successfully" date: the only one this field ever held
    was the date of the onboarding check itself, not of an actual health check, and
    labelling it that way was the mix-up Otto ruled out (M2-08 plan §4.4,
    ENTSCHEIDUNGSLOG 22.09.2026). A real check date arrives with M5's own health
    checks, on a field of its own.
    """

    status: HealthStatus


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
        # An instant without a zone would be read as UTC by one reader and as local time by the next, and cannot be
        # compared with one that has a zone; a YAML entry names the offset (M5-13 review).
        for name in ("start", "end"):
            instant = getattr(self, name)
            if instant is not None and (not isinstance(instant, datetime) or instant.utcoffset() is None):
                raise ConfigError(f"temporal extent {name} is an instant with a time zone offset")
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ConfigError(f"temporal extent ends before it starts: {self.start} to {self.end}")


def max_geotile_level_for(typical_footprint_km: float) -> int:
    """Finest geotile level whose cell is still at least one footprint wide (adr/0004 §5)."""
    if typical_footprint_km <= 0:
        raise ConfigError("typical_footprint_km must be greater than zero")
    if typical_footprint_km > EARTH_CIRCUMFERENCE_KM:
        raise ConfigError(f"typical_footprint_km {typical_footprint_km} is wider than the planet")
    return math.floor(math.log2(EARTH_CIRCUMFERENCE_KM / typical_footprint_km))


#: Largest class value a mask layer may carry (``uint16``).
MAX_MASK_VALUE = 65535


@dataclass(frozen=True, slots=True)
class MaskClass:
    """One class of a classification layer: the value in the pixels and the source's name for it."""

    value: int
    label: str


@dataclass(frozen=True, slots=True)
class MaskSource:
    """Where the operator ``mask`` reads its classes from for this dataset (M4-18, adr/0014 §15m).

    ``asset`` is the key an order names (``scl``, ``SCL_20m:scl`` for a Zarr group),
    ``band`` the name the layer carries in the core, which is what a recipe's ``source``
    must equal. ``classes`` lists every class the layer knows, ascending, with the names
    of ``reference``; ``suggested`` is what the panel ticks first and is never applied
    unless a recipe names it (B10). ``note`` is the help text's remark on the names.

    ``cloud_classes`` are the classes that count as cloud when the search measures the cloud share inside an AOI
    (DS-03 plan §6.6, §6.10); empty means the dataset has no such share. They are a subset of ``classes`` and the
    layer must be a COG, because the share is read from the overviews of the file itself. ``cloud_note`` is one
    sentence on the limits of the classification, shown as a tooltip; it may be empty only without ``cloud_classes``.
    Neither has a default (B10): an entry says on purpose whether it offers the share.

    ``share_classes`` are the classes of the other shares the search can measure inside the AOI (DS-03c): one
    :class:`ShareClasses` per measure that counts classes (every measure but the cloud share, which has
    ``cloud_classes`` above, and the no-data share, which is class ``nodata`` of the file). An entry without any says
    so with an empty tuple (B10).
    """

    asset: str
    band: str
    classes: tuple[MaskClass, ...]
    suggested: frozenset[int]
    reference: str
    note: str
    cloud_classes: frozenset[int]
    cloud_note: str
    share_classes: tuple[ShareClasses, ...]


class FilterKind(Enum):
    """How a search filter narrows a property (DS-02 plan §6.3)."""

    RANGE = "range"  # a number between two bounds, either of them open
    VALUES = "values"  # one of a fixed list of texts


class AoiMeasure(Enum):
    """What a filter measures inside the AOI instead of on the whole scene (DS-03 plan §6.10, Otto 31.10.2026).

    Every measure has a property of its own, reserved under ``earthx:``: the name a search sends the range under and a
    collection publishes as ``within_aoi``. All measures of a scene come from the one reading of its classification.
    """

    CLOUD_SHARE = "earthx:aoi_cloud_cover"  # clouds in percent of the valid pixels of the AOI
    NODATA_SHARE = "earthx:aoi_nodata"  # pixels of the AOI without a valid pixel, in percent of the AOI
    # DS-03c (Otto, 05.11.2026): one share per class of the classification, in percent of the valid pixels of the AOI,
    # counted in the same reading as the cloud share. The classes are the dataset's (`MaskSource.share_classes`).
    CIRRUS_SHARE = "earthx:aoi_thin_cirrus"
    SHADOW_SHARE = "earthx:aoi_cloud_shadow"
    SNOW_SHARE = "earthx:aoi_snow_ice"
    WATER_SHARE = "earthx:aoi_water"
    VEGETATION_SHARE = "earthx:aoi_vegetation"
    NOT_VEGETATED_SHARE = "earthx:aoi_not_vegetated"


@dataclass(frozen=True, slots=True)
class ShareClasses:
    """The classes of the classification that make up one share (:class:`AoiMeasure`) inside the AOI."""

    measure: AoiMeasure
    classes: frozenset[int]


#: The measures that count the classes `MaskSource.share_classes` names (the cloud share has `cloud_classes`, the no-data share
#: the file's `nodata`).
CLASS_MEASURES = frozenset(AoiMeasure) - {AoiMeasure.CLOUD_SHARE, AoiMeasure.NODATA_SHARE}

# A STAC property as the source names it: ``platform``, ``eo:cloud_cover``. ``earthx:`` is kept free for filters the
# platform computes itself (DS-03), ``datetime`` has its own field.
FILTER_PROPERTY = re.compile(r"\A[a-z0-9_]+(:[a-z0-9_]+)?\Z")
RESERVED_FILTER_PREFIX = "earthx:"


@dataclass(frozen=True, slots=True)
class FilterValue:
    """One value a ``VALUES`` filter offers: the text the source holds and what the panel shows."""

    value: str
    label: str


@dataclass(frozen=True, slots=True)
class SearchFilter:
    """A filter the search offers for one dataset (DS-02 plan §6.3). ``title`` and ``description`` are shown as they
    stand. ``minimum``, ``maximum`` and ``integer`` belong to a ``RANGE``, ``values`` to a ``VALUES`` filter.

    ``within_aoi`` names what the filter measures inside the AOI when the search asks for it (:class:`AoiMeasure`),
    ``None`` on a filter that has no area to measure (DS-03 plan §6.10); a measure needs ``MaskSource.cloud_classes``
    and stands on at most one filter of the dataset. ``group`` is the heading the filter stands under in the
    pop-up (DS-02c), e.g. "Clouds": the filters of one group follow each other, and the order of the registry is the
    order shown.

    ``area_based`` says the filter is a share of an area (of the scene, or of the AOI where ``within_aoi`` is set): a
    search per pass evaluates it over the merged scenes of an overpass, weighting the scenes by the area each adds to
    the mosaic (DS-03c). A filter without it (the satellite, the sun) has no area; a pass meets it if its scenes do.
    No defaults (B10)."""

    property: str
    kind: FilterKind
    title: str
    description: str
    unit: str | None
    minimum: float | None
    maximum: float | None
    integer: bool
    values: tuple[FilterValue, ...]
    within_aoi: AoiMeasure | None
    group: str
    area_based: bool


@dataclass(frozen=True, slots=True)
class SearchCapabilities:
    """What a dataset's search can do beyond its filters (DS-03c, published as ``earthx:search_capabilities``).

    ``evaluate``: the search can judge the filters per overpass as well as per scene (needs filters, a source whose
    page the platform walks, and an overpass key that holds the acquisition instant). ``aoi_coverage``: the filter
    "AOI coverage" (the share of the AOI the outlines of the scenes cover) is offered. No defaults (B10)."""

    evaluate: bool
    aoi_coverage: bool


def _filter_problem(search_filter: SearchFilter) -> str | None:
    """The rule a search filter breaks, or None."""
    name = search_filter.property
    if not isinstance(name, str) or not FILTER_PROPERTY.match(name) or name == "datetime":
        return f"{name!r} is not a property a filter can name"
    if name.startswith(RESERVED_FILTER_PREFIX):
        return f"{name!r} uses the prefix {RESERVED_FILTER_PREFIX!r}, which is kept for filters the platform computes"
    if not search_filter.title.strip() or not search_filter.description.strip():
        return f"the filter on {name!r} has a title and a description"
    if search_filter.within_aoi is not None and not isinstance(search_filter.within_aoi, AoiMeasure):
        return f"within_aoi of the filter on {name!r} is an AoiMeasure or None"
    if not isinstance(search_filter.area_based, bool):
        return f"area_based of the filter on {name!r} is true or false"
    if search_filter.area_based and search_filter.kind is not FilterKind.RANGE:
        return f"the area-based filter on {name!r} is a range"
    group = search_filter.group
    if not isinstance(group, str) or not group.strip() or group != group.strip() or len(group) > MAX_GROUP_CHARS:
        return f"the group of the filter on {name!r} is a short non-blank text"
    unit = search_filter.unit
    if unit is not None and (not unit.strip() or unit != unit.strip() or len(unit) > MAX_UNIT_CHARS):
        return f"the unit of the filter on {name!r} is a short non-blank text or None"
    if search_filter.kind is FilterKind.RANGE:
        low, high = search_filter.minimum, search_filter.maximum
        if search_filter.values or low is None or high is None or not (_is_finite_number(low) and _is_finite_number(high)):
            return f"the range filter on {name!r} has a finite minimum and maximum and no values"
        if not low < high:
            return f"the range filter on {name!r} has a minimum below its maximum"
        if search_filter.integer and not (float(low).is_integer() and float(high).is_integer()):
            return f"the whole-number filter on {name!r} has whole-number bounds"
        return None
    if search_filter.minimum is not None or search_filter.maximum is not None or search_filter.integer:
        return f"the values filter on {name!r} has no bounds"
    texts = [entry.value for entry in search_filter.values]
    if len(texts) < 2 or len(set(texts)) != len(texts):
        return f"the values filter on {name!r} offers at least two values, each once"
    if not all(entry.value.strip() and entry.label.strip() for entry in search_filter.values):
        return f"every value of the filter on {name!r} has a text and a label"
    return None


# The name of the band a preset's step adds: the pattern of ``band_math.check_name`` (adr/0020 §6), which the start of
# ``api`` applies in full (``processing.index_presets``); ``catalog`` cannot import ``processing``.
INDEX_PRESET_NAME = re.compile(r"\A[A-Za-z][A-Za-z0-9_]{0,31}\Z")
# A name in an expression that is no call: what has to be a band of the dataset. Numbers such as ``1e5`` are no name;
# Python's keywords (``if``, ``and``) are left to band_math, which refuses them with a reason of its own.
_EXPRESSION_BAND = re.compile(r"(?<![A-Za-z0-9_.])[A-Za-z_][A-Za-z0-9_]*(?![A-Za-z0-9_])(?!\s*\()")


@dataclass(frozen=True, slots=True)
class IndexPreset:
    """A common index the panel offers as one click, which fills an ordinary ``band_math`` step (NM4-14 plan §8.1).

    ``name`` is the band the step adds and the text of the button, ``expression`` names the bands of this dataset as a
    user would type them. ``rescale`` and ``colormap_name`` are how a band with this expression is drawn, in the field
    names of the STAC render extension like ``DefaultRender``. ``formula`` is the formula in the words of Awesome
    Spectral Indices, ``reference`` the source of the formula as that catalogue names it. No defaults (B10).
    """

    name: str
    title: str
    expression: str
    rescale: tuple[float, float]
    colormap_name: str
    formula: str
    reference: str


def _preset_problem(preset: IndexPreset, bands: set[str], not_bands: set[str]) -> str | None:
    """The rule an index preset breaks, as the end of a sentence about it, or None."""
    for field_name in ("title", "expression", "colormap_name", "formula"):
        value = getattr(preset, field_name)
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            return f"has a non-blank {field_name}"
    used = {name for name in _EXPRESSION_BAND.findall(preset.expression) if not keyword.iskeyword(name)}
    if used & not_bands:
        return f"reads {', '.join(sorted(used & not_bands))}, which is no band of the data"
    if unknown := used - bands:
        return f"reads {', '.join(sorted(unknown))}, which the entry does not know (band_units)"
    if not used:
        return "reads no band"
    rescale = preset.rescale
    if (
        not isinstance(rescale, tuple)
        or len(rescale) != 2
        or not all(_is_finite_number(bound) for bound in rescale)
        or not rescale[0] < rescale[1]
    ):
        return "has a rescale of two finite numbers, the lower first"
    if not isinstance(preset.reference, str) or not preset.reference.startswith("https://"):
        return "names the source of its formula with an https:// address"
    return None


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_whole_number(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True, slots=True)
class DatasetConfig:
    """One dataset, everything the platform decides about it before asking the source."""

    dataset_id: str
    title: str
    description: str
    # What the viewer's dataset filter matches besides title and description (M3-10,
    # published as STAC `keywords`). No default (KLAERUNGEN B10): an entry names them
    # on purpose, at least one.
    keywords: tuple[str, ...]
    # The group of the Data catalogue (UI-05 plan §5, F1; published as `earthx:category`). No default (KLAERUNGEN B10).
    category: DatasetCategory
    # Who produces, licenses, processes and hosts the data, as the source names them (UI-05 plan §5, F2; published as
    # STAC `providers`), at least one. No default (KLAERUNGEN B10).
    providers: tuple[Provider, ...]
    # The ground sample distances of the data in metres, ascending, at least one (UI-05 plan §5, F2; published as STAC
    # `summaries.gsd`). No default (KLAERUNGEN B10).
    gsd: tuple[float, ...]
    # Onboarding checklist, point 3: a DOI where one exists, otherwise a persistent
    # citation. Both None means the point is still open for this dataset.
    doi: str | None
    citation: str | None
    data_class: DataClass
    format: DataFormat
    # How the readers place the pixels (adr/0018 F1, DS-04a), published as `earthx:georeferencing`. No default
    # (KLAERUNGEN B10): an entry names it, and a file that disagrees with it is not read.
    georeferencing: Georeferencing
    spatial_extent: SpatialExtent
    temporal_extent: TemporalExtent
    capabilities: Capabilities
    license: LicenseInfo
    # Whether the legal footing is settled (adr/0024 R3), and for ``unclear`` one sentence on what is unclear, no legal
    # opinion; ``None`` for ``cleared``. No default (KLAERUNGEN B10).
    legal_status: LegalStatus
    legal_note: str | None
    access: AccessInfo
    source: SourceInfo
    coverage: CoverageInfo
    # None where the standard visualisation is not defined yet. For Sentinel-2 L2A
    # that is deliberate: plans/m1/m1-fundament.md §2 puts it in M2.
    default_render: DefaultRender | None
    # None where nobody has decided how the viewer groups the items of this dataset.
    viewer: ViewerInfo | None
    health: HealthInfo
    # How settled the source itself is (architekturplan.md 5.1, tenth field;
    # adr/0007 §12.11 point 14). No default (KLAERUNGEN B10): every entry says this
    # on purpose, it is part of the truth about the dataset like the licence.
    maturity: Maturity
    # None for a COG dataset and for a Zarr dataset addressed the M2-09a way (see
    # ZarrInfo). A dataset whose store needs anything more says so here, not with a
    # branch on `dataset_id` somewhere in `readers`.
    zarr: ZarrInfo | None
    # The classification layer ``mask`` reads, or None where the dataset has none (the
    # DEM). No default (KLAERUNGEN B10): an entry says so on purpose, and ``masking`` in
    # its capabilities agrees with it.
    mask: MaskSource | None
    # The unit of the values of an asset after the scaling, by asset key as an order names
    # it (``red``, ``SR_10m:b04``); a key may carry ``*`` for a whole group (``SR_*``). ``None``
    # says "unknown" on purpose. No default (KLAERUNGEN B10): an entry decides. An item that
    # names a unit itself goes first (adr/0014 §15n). The default render and the mask layer
    # each need a key.
    band_units: Mapping[str, str | None]
    # The assets that help to look at or read the data but are no band of it (a true-colour picture, a preview), by
    # asset key. The panel keeps them out of "Select all"; a user can still pick one. No default (KLAERUNGEN B10):
    # an entry says so, with an empty tuple where it has none. The mask layer is named by ``mask``, not here.
    auxiliary_assets: tuple[str, ...]
    # The filters the search offers for this dataset, in the order the panel shows them (DS-02). No default
    # (KLAERUNGEN B10): an entry says so, with an empty tuple where it offers none.
    search_filters: tuple[SearchFilter, ...]
    # What the search can do besides filter (DS-03c). No default (KLAERUNGEN B10).
    search_capabilities: SearchCapabilities
    # The indices the panel offers as one click each (NM4-14), in the order of the buttons. No default (KLAERUNGEN
    # B10): an entry says so, with an empty tuple where it offers none.
    index_presets: tuple[IndexPreset, ...]
    # The three bands of a true-colour picture, red, green, blue in this order (NM4-64), or an empty tuple where the
    # data has no such picture (the DEM). Names of bands of the data, not of a picture made from them (``visual``). No
    # default (KLAERUNGEN B10): an entry says so.
    true_color: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "band_units", MappingProxyType(dict(self.band_units)))
        self._check_keywords()
        self._check_catalogue_fields()
        self._check_doi()
        self._check_license_is_identifiable()
        self._check_license_tier()
        self._check_legal_status()
        self._check_access()
        self._check_attribution()
        self._check_coverage()
        self._check_source()
        self._check_item_holding()
        self._check_zarr()
        self._check_georeferencing()
        self._check_browse_cors()
        self._check_mask()
        self._check_band_units()
        self._check_auxiliary_assets()
        self._check_search_filters()
        self._check_index_presets()
        self._check_true_color()

    def search_filter(self, name: str) -> SearchFilter | None:
        """The filter on the property ``name``, or None where the entry offers none."""
        return next((entry for entry in self.search_filters if entry.property == name), None)

    def _check_search_filters(self) -> None:
        """Every filter is well formed, each property once, and only on items the source searches (DS-02 plan §6.3).

        Whether the source can apply them is ``adapters.check_adapter_specs``' question.
        """
        if isinstance(self.search_filters, SearchFilter) or not isinstance(self.search_filters, tuple):
            raise ConfigError(f"{self.dataset_id}: search_filters is a tuple of SearchFilter")
        for entry in self.search_filters:
            if not isinstance(entry, SearchFilter):
                raise ConfigError(f"{self.dataset_id}: search_filters is a tuple of SearchFilter")
            if problem := _filter_problem(entry):
                raise ConfigError(f"{self.dataset_id}: {problem}")
        names = [entry.property for entry in self.search_filters]
        if len(set(names)) != len(names):
            raise ConfigError(f"{self.dataset_id}: search_filters names a property twice")
        groups = [entry.group for entry in self.search_filters]
        if any(group != groups[i - 1] and group in groups[: i - 1] for i, group in enumerate(groups) if i):
            raise ConfigError(f"{self.dataset_id}: the filters of one group follow each other")
        if names and self.source.item_holding is not ItemHolding.FEDERATED:
            # Our own items are searched by pgstac, which applies no filter of this kind yet (DS-02 plan §6.5).
            raise ConfigError(f"{self.dataset_id}: search filters need federated items")
        self._check_within_aoi()
        self._check_search_capabilities()

    def _check_search_capabilities(self) -> None:
        """Evaluating per overpass needs filters and a source the platform walks; the pass is the overpass key."""
        capabilities = self.search_capabilities
        if not isinstance(capabilities, SearchCapabilities) or not all(
            isinstance(flag, bool) for flag in (capabilities.evaluate, capabilities.aoi_coverage)
        ):
            raise ConfigError(f"{self.dataset_id}: search_capabilities is a SearchCapabilities of two flags")
        if capabilities.evaluate:
            if not self.search_filters:
                raise ConfigError(f"{self.dataset_id}: evaluate per pass needs search filters to judge")
            if self.source.item_holding is not ItemHolding.FEDERATED:
                raise ConfigError(f"{self.dataset_id}: evaluate per pass needs federated items")
            if self.viewer is None or ACQUISITION_INSTANT not in self.viewer.results_group_by:
                raise ConfigError(
                    f"{self.dataset_id}: evaluate per pass needs an overpass key that holds {ACQUISITION_INSTANT!r}"
                )

    def _check_within_aoi(self) -> None:
        """Each :class:`AoiMeasure` sits on at most one filter: a percentage from 0 to 100 the AOI measure can stand in for.

        Every measure is read from the classification layer, so each needs a mask with ``cloud_classes``: that is what
        makes the layer a COG (``_check_mask``) and gives the cache one key for all measures of a scene. A mask without
        cloud classes would allow the no-data share alone; nothing in the plan decides that yet.
        """
        marked = [entry for entry in self.search_filters if entry.within_aoi is not None]
        measures = [entry.within_aoi for entry in marked]
        if len(set(measures)) != len(measures):
            raise ConfigError(f"{self.dataset_id}: a within_aoi measure is set on more than one filter")
        for entry in marked:
            if entry.kind is not FilterKind.RANGE or entry.minimum != 0 or entry.maximum != 100 or entry.unit != "%":
                raise ConfigError(
                    f"{self.dataset_id}: within_aoi on {entry.property!r} needs a range filter from 0 to 100 in '%'"
                )
            if not entry.area_based:
                raise ConfigError(f"{self.dataset_id}: within_aoi on {entry.property!r} needs an area-based filter")
            if self.mask is None or not self.mask.cloud_classes:
                raise ConfigError(
                    f"{self.dataset_id}: within_aoi on {entry.property!r} needs a mask with cloud_classes"
                )
            if entry.within_aoi in CLASS_MEASURES and entry.within_aoi not in {
                share.measure for share in self.mask.share_classes
            }:
                raise ConfigError(f"{self.dataset_id}: within_aoi on {entry.property!r} needs share_classes for its measure")

    def band_unit(self, asset: str) -> str | None:
        """The unit the entry names for ``asset`` (one key, not a list of variables), or ``None`` where it names none.

        The exact key goes first, then a key with a ``*`` (the entry allows no two that overlap).
        """
        if asset in self.band_units:
            return self.band_units[asset]
        for pattern, unit in self.band_units.items():
            if "*" in pattern and fnmatchcase(asset, pattern):
                return unit
        return None

    def _check_band_units(self) -> None:
        """Keys and units are usable text, and what the viewer draws by default has an entry (M4-19b)."""
        for key, unit in self.band_units.items():
            if not isinstance(key, str) or not key.strip() or key != key.strip():
                raise ConfigError(f"{self.dataset_id}: a band unit is keyed by an asset, not {key!r}")
            # Only `*` is a wildcard; the viewer reads the keys the same way, and fnmatch would also read these.
            if any(char in key for char in "?[]"):
                raise ConfigError(f"{self.dataset_id}: the key {key!r} of a band unit uses a wildcard other than '*'")
            if unit is not None and (not isinstance(unit, str) or not unit.strip() or unit != unit.strip()):
                raise ConfigError(f"{self.dataset_id}: the unit of {key!r} is a non-blank text or None")
            if unit is not None and len(unit) > MAX_UNIT_CHARS:
                raise ConfigError(f"{self.dataset_id}: the unit of {key!r} is longer than {MAX_UNIT_CHARS} characters")
        # The collection travels through JSONB, which does not keep the order of keys: two patterns that can both
        # match one asset would be read in an order nobody chose.
        patterns = [key for key in self.band_units if "*" in key]
        for first in patterns:
            for second in patterns:
                if first != second and fnmatchcase(first, second):
                    raise ConfigError(f"{self.dataset_id}: the patterns {second!r} and {first!r} of band_units overlap")
        separator = self.zarr.variable_separator if self.zarr is not None else None
        wanted = list(self.default_render.assets) if self.default_render is not None else []
        if self.mask is not None:
            wanted.append(self.mask.asset)
        listed = tuple(self.band_units)
        for order_asset in wanted:
            for key in single_asset_keys(order_asset, separator):
                if not any(key == pattern or ("*" in pattern and fnmatchcase(key, pattern)) for pattern in listed):
                    raise ConfigError(f"{self.dataset_id}: band_units has no entry for {key!r}, which the entry reads itself")

    def _check_auxiliary_assets(self) -> None:
        """The auxiliary assets are distinct, usable keys, and none is the mask layer."""
        keys = self.auxiliary_assets
        if isinstance(keys, str) or any(not isinstance(key, str) or not key.strip() or key != key.strip() for key in keys):
            raise ConfigError(f"{self.dataset_id}: auxiliary_assets is a tuple of asset keys")
        if len(set(keys)) != len(keys):
            raise ConfigError(f"{self.dataset_id}: auxiliary_assets names an asset twice")
        if self.mask is not None and self.mask.asset in keys:
            raise ConfigError(f"{self.dataset_id}: the mask layer {self.mask.asset!r} is named by mask, not auxiliary_assets")

    def _check_index_presets(self) -> None:
        """The presets are well formed, each name once, and name only bands of the data (NM4-14 plan §8.1).

        Whether ``band_math`` takes the expression and the name, and whether the tiler knows the colormap, is
        ``processing.index_presets.check_index_presets``' question.
        """
        presets = self.index_presets
        if isinstance(presets, IndexPreset) or not isinstance(presets, tuple):
            raise ConfigError(f"{self.dataset_id}: index_presets is a tuple of IndexPreset")
        if presets and not self.capabilities.band_math:
            raise ConfigError(f"{self.dataset_id}: index presets fill a band_math step, but band_math is off")
        bands = {key for key in self.band_units if "*" not in key}
        not_bands = set(self.auxiliary_assets) | ({self.mask.asset} if self.mask is not None else set())
        taken = {key.casefold() for key in self.band_units}
        seen: set[str] = set()
        for preset in presets:
            if not isinstance(preset, IndexPreset):
                raise ConfigError(f"{self.dataset_id}: index_presets is a tuple of IndexPreset")
            name = preset.name
            if not isinstance(name, str) or not INDEX_PRESET_NAME.match(name):
                raise ConfigError(f"{self.dataset_id}: {name!r} is not a name a band_math step can add")
            if name.casefold() in seen:
                raise ConfigError(f"{self.dataset_id}: the index preset {name} is named twice (case ignored)")
            seen.add(name.casefold())
            if name.casefold() in taken:
                raise ConfigError(f"{self.dataset_id}: the index preset {name} has the name of a band of the data")
            if problem := _preset_problem(preset, bands, not_bands):
                raise ConfigError(f"{self.dataset_id}: the index preset {name} {problem}")

    def _check_true_color(self) -> None:
        """Empty, or three different bands of the data: red, green, blue (NM4-64)."""
        names = self.true_color
        if isinstance(names, str) or not isinstance(names, tuple):
            raise ConfigError(f"{self.dataset_id}: true_color is a tuple of three band names, or empty")
        if not names:
            return
        if len(names) != 3 or any(not isinstance(name, str) for name in names):
            raise ConfigError(f"{self.dataset_id}: true_color names red, green and blue, three bands, or none")
        if len(set(names)) != 3:
            raise ConfigError(f"{self.dataset_id}: true_color names three different bands")
        bands = {key for key in self.band_units if "*" not in key}
        not_bands = set(self.auxiliary_assets) | ({self.mask.asset} if self.mask is not None else set())
        for name in names:
            if name in not_bands or name not in bands:
                raise ConfigError(f"{self.dataset_id}: true_color names {name!r}, which is no band of the data")

    def _check_mask(self) -> None:
        """``masking`` and ``mask`` agree, and the description of the layer is consistent (M4-18)."""
        mask = self.mask
        if mask is None:
            if self.capabilities.masking:
                raise ConfigError(f"{self.dataset_id}: masking is on, but the entry describes no mask layer")
            return
        if not self.capabilities.masking:
            raise ConfigError(f"{self.dataset_id}: the entry describes a mask layer, but masking is off")
        if not mask.asset or not mask.band or not mask.note.strip():
            raise ConfigError(f"{self.dataset_id}: a mask layer names its asset, band and a note")
        # A Zarr group is addressed as ``<asset>:<variable>`` (plan M4-13, ZarrInfo); a COG asset key holds no colon.
        variable = mask.asset.rsplit(":", 1)[-1]
        if variable != mask.band:
            raise ConfigError(
                f"{self.dataset_id}: mask band {mask.band!r} is not what asset {mask.asset!r} reads as {variable!r}"
            )
        if not mask.reference.startswith("https://"):
            raise ConfigError(f"{self.dataset_id}: the source of the mask classes is not an https URL")
        values = [entry.value for entry in mask.classes]
        if not values or values != sorted(set(values)):
            raise ConfigError(f"{self.dataset_id}: mask classes are listed ascending, each value once")
        if not all(isinstance(value, int) and 0 <= value <= MAX_MASK_VALUE for value in values):
            raise ConfigError(f"{self.dataset_id}: mask class values are whole numbers from 0 to {MAX_MASK_VALUE}")
        if not all(entry.label.strip() for entry in mask.classes):
            raise ConfigError(f"{self.dataset_id}: every mask class has a name")
        if not mask.suggested <= set(values):
            raise ConfigError(f"{self.dataset_id}: suggested mask classes are among the listed ones")
        cloud = mask.cloud_classes
        if not isinstance(cloud, frozenset) or not all(_is_whole_number(value) for value in cloud):
            raise ConfigError(f"{self.dataset_id}: cloud_classes is a frozenset of whole numbers")
        if not cloud <= set(values):
            raise ConfigError(f"{self.dataset_id}: cloud_classes are among the listed mask classes")
        if not isinstance(mask.cloud_note, str):
            raise ConfigError(f"{self.dataset_id}: cloud_note is a text, empty without cloud_classes")
        self._check_share_classes(mask, values)
        if not cloud:
            return
        if not mask.cloud_note.strip():
            raise ConfigError(f"{self.dataset_id}: cloud_classes need a cloud_note on the limits of the classification")
        if self.format is not DataFormat.COG:
            raise ConfigError(
                f"{self.dataset_id}: cloud_classes need a COG: the cloud share is read from the overviews of the "
                f"file itself, and a {self.format.value} dataset needs a reader of its own first (DS-03 plan §6.19)"
            )

    def _check_share_classes(self, mask: MaskSource, values: list[int]) -> None:
        """Each class share names classes of the layer, once per measure, and only measures that count classes."""
        if not isinstance(mask.share_classes, tuple) or not all(isinstance(e, ShareClasses) for e in mask.share_classes):
            raise ConfigError(f"{self.dataset_id}: share_classes is a tuple of ShareClasses")
        measures = [entry.measure for entry in mask.share_classes]
        if len(set(measures)) != len(measures):
            raise ConfigError(f"{self.dataset_id}: share_classes names a measure twice")
        for entry in mask.share_classes:
            if entry.measure not in CLASS_MEASURES:
                raise ConfigError(f"{self.dataset_id}: share_classes cannot name {entry.measure.value}")
            classes = entry.classes
            if not isinstance(classes, frozenset) or not classes or not all(_is_whole_number(v) for v in classes):
                raise ConfigError(f"{self.dataset_id}: the classes of {entry.measure.value} are a non-empty frozenset of whole numbers")
            if not classes <= set(values):
                raise ConfigError(f"{self.dataset_id}: the classes of {entry.measure.value} are among the listed mask classes")
        if mask.share_classes and not mask.cloud_classes:
            raise ConfigError(f"{self.dataset_id}: share_classes need cloud_classes: one reading of a COG gives every share")

    def _check_keywords(self) -> None:
        """At least one keyword, each a non-blank string (M3-10): the viewer's filter
        reads them, and a blank one would match every search word it is a part of."""
        if not isinstance(self.keywords, tuple):
            raise ConfigError(f"{self.dataset_id}: keywords must be a tuple of strings, not one string")
        if not self.keywords:
            raise ConfigError(f"{self.dataset_id}: keywords names no keyword")
        if not all(isinstance(word, str) and word.strip() for word in self.keywords):
            raise ConfigError(f"{self.dataset_id}: every keyword must be a non-blank string")

    def _check_catalogue_fields(self) -> None:
        """Group, providers and resolution of the Data catalogue (UI-05 plan §5): set, of the right kind, gsd ascending."""
        if not isinstance(self.category, DatasetCategory):
            raise ConfigError(f"{self.dataset_id}: category must be one of {[c.value for c in DatasetCategory]}")
        if not isinstance(self.providers, tuple) or not self.providers:
            raise ConfigError(f"{self.dataset_id}: providers names no provider")
        if not all(isinstance(provider, Provider) for provider in self.providers):
            raise ConfigError(f"{self.dataset_id}: every provider must be a Provider")
        if not isinstance(self.gsd, tuple) or not self.gsd:
            raise ConfigError(f"{self.dataset_id}: gsd names no resolution")
        if not all(_is_finite_number(value) and value > 0 for value in self.gsd):
            raise ConfigError(f"{self.dataset_id}: every gsd must be a number of metres greater than zero")
        if list(self.gsd) != sorted(set(self.gsd)):
            raise ConfigError(f"{self.dataset_id}: gsd must be ascending, each value once")

    def _check_doi(self) -> None:
        """A DOI that is no DOI stops the start (M4-14, Otto 07.10.2026), not the first citation.

        A blank one is left to onboarding checklist point 3, which names it as a finding.
        """
        try:
            doi_name(self.doi)
        except ConfigError as error:
            raise ConfigError(f"{self.dataset_id}: {error}") from None

    def _check_license_is_identifiable(self) -> None:
        """An SPDX identifier, or else name and URL (projektuebersicht.md §5)."""
        if self.license.spdx_id:
            return
        if not (self.license.name and self.license.url):
            raise ConfigError(
                f"{self.dataset_id}: a licence without an SPDX identifier needs a name and a URL"
            )

    def _check_legal_status(self) -> None:
        """``unclear`` if and only if the id has the prototype prefix, and only then a note (adr/0024 R3)."""
        if not isinstance(self.legal_status, LegalStatus):
            raise ConfigError(f"{self.dataset_id}: legal_status must be one of {[s.value for s in LegalStatus]}")
        prototype = self.dataset_id.startswith(PROTOTYPE_PREFIX)
        if self.legal_status is LegalStatus.UNCLEAR and not prototype:
            raise ConfigError(f"{self.dataset_id}: legal_status unclear needs an id starting with {PROTOTYPE_PREFIX!r}")
        if self.legal_status is LegalStatus.CLEARED and prototype:
            raise ConfigError(f"{self.dataset_id}: an id starting with {PROTOTYPE_PREFIX!r} needs legal_status unclear")
        if self.legal_status is LegalStatus.UNCLEAR:
            if not isinstance(self.legal_note, str) or not self.legal_note.strip():
                raise ConfigError(f"{self.dataset_id}: legal_status unclear needs a legal_note saying what is unclear")
        elif self.legal_note is not None:
            raise ConfigError(f"{self.dataset_id}: legal_note belongs to legal_status unclear only")

    def _check_access(self) -> None:
        """The start check of adr/0027 §6.1 between ``access.account``, its other fields and the licence tier."""
        access = self.access
        if not isinstance(access.account, AccountKind):
            raise ConfigError(f"{self.dataset_id}: access.account must be one of {[k.value for k in AccountKind]}")
        if not isinstance(access.account_paths, tuple) or not all(
            isinstance(path, AccountPath) for path in access.account_paths
        ):
            raise ConfigError(f"{self.dataset_id}: access.account_paths is a tuple of AccountPath")
        # No way beyond the link (W0) is released (adr/0027 §9): a value here comes with a decision of Otto and a change
        # of this check, never with an entry alone.
        if access.account_paths:
            raise ConfigError(f"{self.dataset_id}: access.account_paths stays empty, no account path is released")
        provider = access.account_provider
        if provider is not None and (not isinstance(provider, str) or not provider.strip()):
            raise ConfigError(f"{self.dataset_id}: access.account_provider is a name or null")
        anonymous = access.account in (AccountKind.NONE, AccountKind.ANONYMOUS_TOKEN)
        if anonymous and provider is not None:
            raise ConfigError(f"{self.dataset_id}: access.account {access.account.value} names no account_provider")
        if access.account is AccountKind.FREE_ACCOUNT and provider is None:
            raise ConfigError(f"{self.dataset_id}: access.account free_account names its account_provider")
        if anonymous != (access.token_free_checked_at is not None):
            raise ConfigError(
                f"{self.dataset_id}: access.token_free_checked_at is set exactly for access.account none and "
                "anonymous_token"
            )
        # An account source is a catalogue entry with a link (W0) while no account path is released (adr/0027 §6.1).
        # `anonymous_token` is held to the same tier until Otto has taken the sentence of adr/0018 §12 into
        # ENTSCHEIDUNGEN_2026-09-18.md (part B, Planetary Computer RTC; adr/0027 §6.1 "bis dahin wie free_account"). DS-04
        # does not lift it: Sentinel-1 GRD over Earth Search needs no token (M5-13 plan §8a, correction to F3).
        if access.account is not AccountKind.NONE and self.license.tier is not LicenseTier.CATALOG:
            raise ConfigError(
                f"{self.dataset_id}: access.account {access.account.value} allows licence tier catalog only "
                "(adr/0027 §6.1)"
            )

    def _check_license_tier(self) -> None:
        """KLAERUNGEN B11: display and processing need distribution and modification;
        a catalogue-only entry names no viewer (M3-02 K-03, Otto's answer of
        23.09.2026, closed by M3-11a) — nothing at that tier is ever rendered by
        this platform, so a ``viewer`` field on it would name a grouping and a zoom
        range for a tile route that refuses every request anyway (K-26).
        """
        if self.license.tier is LicenseTier.CATALOG:
            if self.viewer is not None:
                raise ConfigError(
                    f"{self.dataset_id}: tier catalog names a viewer, but a catalogue "
                    "entry is never displayed here (KLAERUNGEN B11, M3-02 K-03)"
                )
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
        self._check_data_region()

    def _check_data_region(self) -> None:
        """The form of adr/0023 F7, and the region an AWS host names in itself (adr/0022 §7.2, M5-07 plan F2).

        A host ``<bucket>.s3.<region>.amazonaws.com`` asks for exactly ``aws:<region>``; an AWS host without a region
        in its name (``<bucket>.s3.amazonaws.com``) asks for the operator ``aws`` only, the region being a measurement
        the entry notes beside it. Other hosts say nothing about where they store (``adr/0023`` §7.3).
        """
        region = self.source.data_region
        if not isinstance(region, str) or not (region == UNKNOWN_DATA_REGION or _DATA_REGION_RE.fullmatch(region)):
            raise ConfigError(
                f"{self.dataset_id}: data_region {region!r} is neither <operator>:<place> "
                f"(lower case, digits, hyphens) nor {UNKNOWN_DATA_REGION!r} (adr/0023 F7)"
            )
        named = {match["region"] for host in self.source.asset_hosts if (match := _AWS_REGION_HOST_RE.fullmatch(host))}
        if len(named) > 1:
            raise ConfigError(f"{self.dataset_id}: asset_hosts lie in more than one AWS region: {sorted(named)}")
        if named:
            expected = f"aws:{named.pop()}"
            if region != expected:
                raise ConfigError(f"{self.dataset_id}: data_region {region!r} contradicts its asset host ({expected})")
        elif any(_AWS_HOST_RE.fullmatch(host) for host in self.source.asset_hosts) and not region.startswith("aws:"):
            raise ConfigError(f"{self.dataset_id}: data_region {region!r} names no aws region for an AWS asset host")

    def _check_zarr(self) -> None:
        """``ZarrInfo`` describes a Zarr store; a COG entry has nothing for it to say."""
        if self.zarr is not None and self.format is not DataFormat.ZARR:
            raise ConfigError(
                f"{self.dataset_id}: zarr info is set but format is {self.format.value}, not zarr"
            )

    def _check_georeferencing(self) -> None:
        """Ground control points are read from a COG only; a Zarr store is placed by its own coordinates."""
        if not isinstance(self.georeferencing, Georeferencing):
            raise ConfigError(f"{self.dataset_id}: georeferencing is a Georeferencing")
        if self.georeferencing is Georeferencing.GCP_TPS and self.format is not DataFormat.COG:
            raise ConfigError(f"{self.dataset_id}: georeferencing gcp_tps needs format cog, not {self.format.value}")

    def _check_browse_cors(self) -> None:
        """M3-12, F-11: a quicklook the browser keys transparent on its own canvas
        needs to load cross-origin from the asset host — without
        ``Access-Control-Allow-Origin`` the canvas read throws (`mapLayers.ts`
        ``keyBlackToTransparent``). A dataset that has not measured CORS on its
        asset host cannot claim a browsable quicklook."""
        if self.viewer is not None and self.viewer.browse is BrowseMode.QUICKLOOK and not self.access.cors:
            raise ConfigError(
                f"{self.dataset_id}: viewer.browse=quicklook needs access.cors=True "
                "(a canvas cannot key a cross-origin quicklook transparent without it)"
            )

    def _check_item_holding(self) -> None:
        """M3-11a K-05: which coverage provider makes sense follows from where the
        items live, not the other way around.

        A materialized dataset has no search API to aggregate at and nothing to
        sample (adr/0009 §7) — its coverage can only come from its own items
        (``local-sql``, M3-11c). A federated one is the reverse: ``local-sql``
        would count rows nobody ever wrote for it.
        """
        if self.source.item_holding is ItemHolding.MATERIALIZED:
            if self.coverage.provider is not CoverageProvider.LOCAL_SQL:
                raise ConfigError(
                    f"{self.dataset_id}: materialized items need coverage.provider=local-sql "
                    "(adr/0009 §7 — no search API to aggregate at or sample)"
                )
        elif self.coverage.provider is CoverageProvider.LOCAL_SQL:
            raise ConfigError(
                f"{self.dataset_id}: federated items cannot use coverage.provider=local-sql "
                "(no items of this dataset are held in our own pgstac)"
            )


class Attributable(Protocol):
    """What the attribution, the notice and ``citation.bib`` of a download read of a dataset.

    A registry entry has it, and so has a retired dataset: a job finished before the entry left
    keeps its attribution, its terms and its citation until it expires (adr/0017 rule III).
    """

    @property
    def dataset_id(self) -> str: ...

    @property
    def title(self) -> str: ...

    @property
    def doi(self) -> str | None: ...

    @property
    def citation(self) -> str | None: ...

    @property
    def license(self) -> LicenseInfo: ...


@dataclass(frozen=True, slots=True)
class RetiredDataset:
    """A dataset that left the registry, with the licence block and the citation it had (adr/0017 rule III).

    Data, not code: the list lives in ``backend/catalog/retired.yaml``. ``recipe.json`` files of the user have
    no expiry, so the id stays on the list; the licence block and the citation are those of the last
    entry and keep the side files of a finished job complete.
    """

    dataset_id: str
    title: str
    doi: str | None
    citation: str | None
    license: LicenseInfo
    retired_on: date
    #: The dataset that shows the same thing now.
    successor: str
    #: Why it left, one English sentence without a full stop.
    reason: str

    def __post_init__(self) -> None:
        for name in ("dataset_id", "title", "successor", "reason"):
            if not getattr(self, name).strip():
                raise ConfigError(f"a retired dataset needs a {name}")

    @property
    def message(self) -> str:
        """The text of a ``410``: what left, when, why, and where to go instead."""
        return (
            f"dataset {self.dataset_id!r} was retired on {self.retired_on.isoformat()}: {self.reason}; "
            f"use {self.successor!r} instead"
        )


class DatasetRegistry:
    """The entries, looked up by dataset id, and the datasets that left (adr/0017)."""

    def __init__(self, entries: tuple[DatasetConfig, ...], retired: tuple[RetiredDataset, ...] = ()) -> None:
        self._by_id = {entry.dataset_id: entry for entry in entries}
        if len(self._by_id) != len(entries):
            raise ConfigError("duplicate dataset_id in the registry")
        self._retired = {entry.dataset_id: entry for entry in retired}
        if len(self._retired) != len(retired):
            raise ConfigError("duplicate dataset_id among the retired datasets")
        if overlap := sorted(self._by_id.keys() & self._retired.keys()):
            raise ConfigError(f"a dataset is registered and retired at once: {', '.join(overlap)}")
        for gone in self._retired.values():
            if gone.successor not in self._by_id:
                raise ConfigError(f"the successor of {gone.dataset_id!r} is not in the registry")

    def get(self, dataset_id: str) -> DatasetConfig:
        """Return the entry, or raise ``UnknownDatasetError`` — never None (adr/0005 rule I).

        A retired id raises :class:`RetiredDatasetError`, which is an ``UnknownDatasetError`` too.
        """
        try:
            return self._by_id[dataset_id]
        except KeyError:
            if (gone := self._retired.get(dataset_id)) is not None:
                raise RetiredDatasetError(gone) from None
            raise UnknownDatasetError(dataset_id) from None

    def attributable(self, dataset_id: str) -> Attributable | None:
        """The entry or the retired dataset with this id — what a finished job's side files need — or None."""
        return self._by_id.get(dataset_id) or self._retired.get(dataset_id)

    @property
    def retired(self) -> tuple[RetiredDataset, ...]:
        return tuple(self._retired.values())

    def __contains__(self, dataset_id: object) -> bool:
        return dataset_id in self._by_id

    def __iter__(self) -> Iterator[DatasetConfig]:
        return iter(self._by_id.values())

    def __len__(self) -> int:
        return len(self._by_id)


# How the YAML entries are read (docs/plans/m5/m5-13-yaml-lader.md §3.2, F1): `catalog.entry_files` checks a file
# against these very dataclasses with pydantic, strictly and without unknown fields, so there is no second schema next
# to them. A plain dict, so this module does not import pydantic; it is what pydantic reads off a stdlib dataclass.
ENTRY_FILE_CONFIG = {"strict": True, "extra": "forbid"}
for _entry_part in (
    Capabilities,
    TermsOfUse,
    LicenseInfo,
    AccessInfo,
    SourceInfo,
    Provider,
    CoverageInfo,
    ZarrInfo,
    DefaultRender,
    ViewerInfo,
    HealthInfo,
    SpatialExtent,
    TemporalExtent,
    MaskClass,
    MaskSource,
    ShareClasses,
    FilterValue,
    SearchFilter,
    SearchCapabilities,
    IndexPreset,
    DatasetConfig,
    RetiredDataset,
):
    _entry_part.__pydantic_config__ = ENTRY_FILE_CONFIG
del _entry_part
