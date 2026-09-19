"""The registry entries. One dataset so far: Sentinel-2 L2A over Earth Search v1.

Decided in docs/adr/0003-erster-datensatz.md §6 (first token-free dataset) and
§11.2 (licence). Nothing here is a decision of its own; every value carries the
place it comes from.

KLAERUNGEN B13 stage M1-M4: entries live in Python. From M5 they become curated
YAML and this module turns into the loader that builds the same objects.
"""

from __future__ import annotations

from datetime import date

from earthx.catalog.registry import (
    AccessInfo,
    AdapterKind,
    Capabilities,
    CoverageInfo,
    CoverageProvider,
    DataClass,
    DataFormat,
    DatasetConfig,
    DatasetRegistry,
    DefaultRender,
    HealthInfo,
    HealthStatus,
    LicenseInfo,
    LicenseTier,
    SourceInfo,
    SpatialExtent,
    TemporalExtent,
)

# Reachability of earth-search.aws.element84.com, measured in adr/0003 §10.1.
_REACHABILITY_CHECKED = date(2026, 9, 18)

SENTINEL_2_L2A = DatasetConfig(
    dataset_id="sentinel-2-l2a",
    title="Sentinel-2 L2A",
    description=(
        "Bottom-of-atmosphere reflectance from Sentinel-2 MSI, Collection 1, as "
        "cloud-optimized GeoTIFF. Served by Earth Search v1 (Element 84) from the "
        "Registry of Open Data on AWS."
    ),
    data_class=DataClass.RASTER_TIME_SERIES,
    format=DataFormat.COG,
    # Global and open at both ends: M1 reads nothing from the source, so the real
    # extent of the upstream collection is not known here yet. M2 fills it in.
    spatial_extent=SpatialExtent(bbox=(-180.0, -90.0, 180.0, 90.0)),
    temporal_extent=TemporalExtent(start=None, end=None),
    # Every flag set deliberately (KLAERUNGEN B10). These say what the dataset is
    # suited for under its licence, not what the platform has already built.
    capabilities=Capabilities(
        roi=True,
        time_range=True,
        band_math=True,
        interpolation=True,
        ml_processing=True,
        # No complex quad-pol data — decomp.py stays out (ENTSCHEIDUNGEN §3).
        quad_pol=False,
        # A time series, not a single coverage: density, not extent (adr/0004 §5).
        single_coverage_product=False,
    ),
    # adr/0003 §11.2: checked by Otto against the Sentinel Data Legal Notice.
    # Tier Processing — modification and distribution are explicitly allowed and
    # the text knows no non-commercial reservation.
    license=LicenseInfo(
        spdx_id=None,
        name="Sentinel Data Legal Notice",
        url="https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice",
        stac_license="proprietary",
        commercial_use=True,
        derivatives=True,
        share_alike=False,
        attribution_required=True,
        tier=LicenseTier.PROCESSING,
        # {year} is filled in where data leaves the platform (adr/0003 §11.2:
        # the notice belongs on the download, not only in a footer).
        attribution_modified="Contains modified Copernicus Sentinel data {year}",
        attribution_unmodified="Copernicus Sentinel data {year}",
        # Shortened to the part adr/0003 §11.1 quotes; the hosts carrying the full
        # wording are blocked from a session (§11.3), so it is not transcribed here.
        liability_notice=(
            "The organisations in charge of the Copernicus programme do not incur any liability."
        ),
    ),
    access=AccessInfo(
        token_free_checked_at=_REACHABILITY_CHECKED,
        method="anonymous HTTPS, no authentication header (adr/0003 §10.1)",
        # Not measured: §10.1 checked status codes, not CORS headers.
        cors=None,
    ),
    # adr/0005 rule I branches on this per collection: an unknown one is a 404,
    # not the empty, valid-looking result Earth Search returns for it.
    source=SourceInfo(
        adapter=AdapterKind.EARTH_SEARCH_V1,
        endpoint="https://earth-search.aws.element84.com/v1",
        # Collection 1 (adr/0003 §6): COGs only, from baseline 5.0 on.
        source_collection_id="sentinel-2-c1-l2a",
        # Federated items, nothing harvested into our own pgstac (architekturplan.md 5.2).
        harvest_run=None,
    ),
    coverage=CoverageInfo(
        provider=CoverageProvider.UPSTREAM_AGGREGATION,
        # A Sentinel-2 tile covers roughly 110 km by 110 km, which puts the cap at
        # geotile z8 — the level adr/0004 §5 names for this dataset.
        typical_footprint_km=110.0,
        max_geotile_level=8,
    ),
    default_render=DefaultRender(
        bands=("red", "green", "blue"),
        stretch=(0.0, 3000.0),
        colormap=None,
    ),
    health=HealthInfo(status=HealthStatus.OK, last_checked_ok=_REACHABILITY_CHECKED),
)

REGISTRY = DatasetRegistry((SENTINEL_2_L2A,))
