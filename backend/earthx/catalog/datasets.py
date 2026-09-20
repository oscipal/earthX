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
    TermsOfUse,
)

# Reachability of earth-search.aws.element84.com, measured in adr/0003 §10.1.
_REACHABILITY_CHECKED = date(2026, 9, 18)

# The licence of the data and, since Otto's decision of 19.09.2026, also the terms
# we pass on at a download. Read from the primary source on 19.09.2026.
_LEGAL_NOTICE_URL = "https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice"

SENTINEL_2_L2A = DatasetConfig(
    # The same id as the upstream collection, by Otto's decision of 19.09.2026: the
    # shorter "sentinel-2-l2a" is the name of the older Earth Search collection that
    # Collection 1 replaces (adr/0003 §3, Option B), so it would be read as that one.
    dataset_id="sentinel-2-c1-l2a",
    title="Sentinel-2 L2A",
    description=(
        "Sentinel-2 Level-2A, Collection 1, as cloud-optimized GeoTIFF from baseline "
        "5.0 on. Served by Earth Search v1 (Element 84) from the Registry of Open "
        "Data on AWS (adr/0003 §3, Option B)."
    ),
    # Onboarding checklist point 3 is open: adr/0003 names no DOI and no persistent
    # citation for this collection, and M1 reads nothing from the source.
    doi=None,
    citation=None,
    data_class=DataClass.RASTER_TIME_SERIES,
    format=DataFormat.COG,
    # Placeholder, not a measurement: STAC needs an extent, and M1 reads nothing
    # from the source. Sentinel-2 does not in fact reach the poles; M2 replaces
    # both extents with the ones the upstream collection reports.
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
        url=_LEGAL_NOTICE_URL,
        commercial_use=True,
        distribution=True,
        derivatives=True,
        share_alike=False,
        attribution_required=True,
        tier=LicenseTier.PROCESSING,
        # {year} is filled in where data leaves the platform (adr/0003 §11.2:
        # the notice belongs on the download, not only in a footer).
        attribution_modified="Contains modified Copernicus Sentinel data {year}",
        attribution_unmodified="Copernicus Sentinel data {year}",
        # Read from the Legal Notice itself on 19.09.2026 (the host is released).
        # The document carries no disclaimer by the provider; it carries a waiver by
        # the user, plus "without any express or implied warranty". Otto settled the
        # wording on the same day: we pass on the source's terms, not our own, and the
        # text stays free of the attribution above, which goes in front of it.
        terms=TermsOfUse(
            url=_LEGAL_NOTICE_URL,
            notice={
                "de": (
                    "Die Nutzung unterliegt dem Sentinel Data Legal Notice: {terms_url}. "
                    "Die Daten werden ohne ausdrückliche oder stillschweigende Gewährleistung "
                    "bereitgestellt, auch nicht hinsichtlich Qualität und Eignung für einen "
                    "bestimmten Zweck; mit ihrer Nutzung verzichtet der Nutzer auf "
                    "Schadensersatzansprüche gegenüber der EU und den Datenanbietern. Der "
                    "Verzicht erfasst jede Streitigkeit, einschließlich vertraglicher und "
                    "deliktischer Ansprüche, vor Gericht, im Schiedsverfahren oder in jeder "
                    "anderen Form der Streitbeilegung."
                ),
                # The Legal Notice's own words, shortened only where it names itself:
                # "without any express or implied warranty, including as regards quality
                # and suitability for any purpose", "renounces to any claims for damages
                # against the European Union and the providers of the said Data and
                # Information", "any dispute, including contracts and torts claims, that
                # might be filed in court, in arbitration or in any other form of dispute
                # settlement".
                "en": (
                    "Use is subject to the Sentinel Data Legal Notice: {terms_url}. The data "
                    "are provided without any express or implied warranty, including as regards "
                    "quality and suitability for any purpose; by using them the user renounces "
                    "any claims for damages against the European Union and the providers of the "
                    "data. The waiver encompasses any dispute, including contracts and torts "
                    "claims, that might be filed in court, in arbitration or in any other form "
                    "of dispute settlement."
                ),
            },
        ),
    ),
    access=AccessInfo(
        token_free_checked_at=_REACHABILITY_CHECKED,
        method="anonymous HTTPS, no authentication header (adr/0003 §10.1)",
        # Measured in adr/0006 §3.6, at the asset bucket and at Earth Search itself:
        # `Access-Control-Allow-Origin: *`. The viewer decides on this field whether it
        # loads a quicklook straight from the source — for Sentinel-2 it may, and that
        # is why there is no asset proxy (D14).
        cors=True,
    ),
    # adr/0005 rule I branches on this per collection: an unknown one is a 404,
    # not the empty, valid-looking result Earth Search returns for it.
    source=SourceInfo(
        adapter=AdapterKind.EARTH_SEARCH_V1,
        endpoint="https://earth-search.aws.element84.com/v1",
        # Collection 1 (adr/0003 §6): COGs only, from baseline 5.0 on.
        source_collection_id="sentinel-2-c1-l2a",
        # Measured at real items in adr/0006 §3.7: all 22 assets of this collection lie
        # on this one host. `sentinel-cogs…amazonaws.com` belongs to the older
        # collection and deliberately stays out of the allowlist.
        asset_hosts=("e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com",),
        # Federated items, nothing harvested into our own pgstac (architekturplan.md 5.2).
        harvest_run=None,
    ),
    coverage=CoverageInfo(
        provider=CoverageProvider.UPSTREAM_AGGREGATION,
        # z8 is Otto's setting for this dataset (adr/0004 §5, decision log 19.09.2026).
        # The footprint width is the granule size of Sentinel-2, which docs/ does not
        # record — see the PR. The two are checked against each other, but the level
        # is the decision and the width is not derived from it.
        typical_footprint_km=110.0,
        max_geotile_level=8,
    ),
    # Onboarding checklist point 8, filled in M2-04 from a measurement at real assets
    # (see the PR): `visual` is the TCI the source already renders as 8-bit RGB, which
    # is why the stretch is the identity. Measured `p2/p98` over five scenes on four
    # continents (July 2026, cloud cover below 10 %): the second percentile runs from 9
    # over vegetation to 202 over desert, so any fixed stretch other than the identity
    # would clip a whole climate zone. The scene-specific stretch is what `/statistics`
    # is for — the viewer asks once per item and overwrites `rescale` (adr/0006 §5,
    # F18); this value is only the picture before anyone touches a control.
    default_render=DefaultRender(
        title="True colour (TCI)",
        assets=("visual",),
        rescale=((0.0, 255.0), (0.0, 255.0), (0.0, 255.0)),
        colormap_name=None,
        expression=None,
        # rio-tiler's own default, named rather than implied (KLAERUNGEN B10).
        resampling="nearest",
    ),
    # Reachability, not health in the sense M5 will measure it: adr/0003 §10.1 got
    # HTTP 200 on /v1/collections/sentinel-2-c1-l2a, nothing beyond that.
    health=HealthInfo(status=HealthStatus.OK, last_checked_ok=_REACHABILITY_CHECKED),
)

REGISTRY = DatasetRegistry((SENTINEL_2_L2A,))
