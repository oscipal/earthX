"""The registry entries: Sentinel-2 L2A over Earth Search v1 (COG), and
Sentinel-2 L2A over the EOPF Sentinel Zarr Samples Service (Zarr, D23).

Decided in docs/adr/0003-erster-datensatz.md §6 (first token-free dataset) and
§11.2 (licence), and in docs/adr/0007-zweites-format-zarr.md §12.11 (second
dataset — the fifteen implementation conditions). Nothing here is a decision of
its own; every value carries the place it comes from.

KLAERUNGEN B13 stage M1-M4: entries live in Python. From M5 they become curated
YAML and this module turns into the loader that builds the same objects.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

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
    ItemHolding,
    LicenseInfo,
    LicenseTier,
    Maturity,
    SourceInfo,
    SpatialExtent,
    TemporalExtent,
    TermsOfUse,
    ViewerInfo,
    ZarrInfo,
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
    # The collection's own `cite-as` link (read from the source on 22.09.2026, M2-08
    # plan §3), the same seam the second entry takes its DOI from. adr/0003 left
    # onboarding checklist point 3 open because M1 read nothing from the source; the
    # link was there all along. It names the ESA product, not Element 84's COG
    # distribution — which is why it differs from the Zarr entry's DOI rather than
    # repeating it. No separate persistent citation beyond it.
    doi="https://doi.org/10.5270/S2_-742ikth",
    citation=None,
    data_class=DataClass.RASTER_TIME_SERIES,
    format=DataFormat.COG,
    # Both extents as the upstream collection reports them, read on 22.09.2026 (M2-08
    # plan §3), replacing the M1 placeholders. The source states the whole globe for
    # the spatial extent — wider than Sentinel-2 actually flies, but it is the
    # source's own claim and not ours to narrow. The start is the first acquisition
    # the collection carries; the end stays open because the archive still grows.
    spatial_extent=SpatialExtent(bbox=(-180.0, -90.0, 180.0, 90.0)),
    temporal_extent=TemporalExtent(
        start=datetime(2015, 6, 27, 10, 25, 31, 456000, tzinfo=timezone.utc),
        end=None,
    ),
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
        item_holding=ItemHolding.FEDERATED,
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
    # The viewer groups the items of one acquisition day per MGRS tile into one step
    # of the time line (Otto, 20.09.2026). `datetime` enters the key as its UTC date,
    # `grid:code` is the MGRS tile Earth Search carries on every item of this
    # collection. M2-07a reads this field and implements nothing of its own.
    # Zoom levels released for the tile path (M2-10, Otto 22.09.2026 F2 a): exactly
    # what the viewer already did before the field existed, now said out loud at the
    # entry instead of defaulted in the client's code (KLAERUNGEN B10). z19 is
    # several times past this source's ~10 m/px (≈z14 near the equator, coarser
    # towards the poles) — headroom to zoom into real detail, without letting an
    # ordinary scroll-zoom run up to MapLibre's own ceiling of z22. There is no
    # lower bound to set: a COG carries overviews, so a tile at z0 costs a read of
    # the coarsest overview and nothing more.
    viewer=ViewerInfo(group_by=("datetime", "grid:code"), min_zoom=0, max_zoom=19),
    # Not health in the sense M5 will measure it: adr/0003 §10.1 got HTTP 200 on
    # /v1/collections/sentinel-2-c1-l2a, nothing beyond that. The reachability date
    # itself lives on `access.token_free_checked_at` (point 6), not here.
    health=HealthInfo(status=HealthStatus.OK),
    # Element 84's Collection 1 is a released, versioned product line, not a pilot.
    maturity=Maturity.STABLE,
    zarr=None,
)

# adr/0007 §12: measured against the real collection on 20.09.2026 (Nachmessung
# M2-03b) and again on 22.09.2026 in the M2-09b plan step (§3 of the plan) — both
# hold unchanged. The reachability the field below records is this session's own
# recheck, over `curl`, not a claim that a Cloud session can reach it through
# `gateway` (adr/0002 T-D, plan §10 F7).
_EOPF_CHECKED = date(2026, 9, 22)

# Same Sentinel Data Legal Notice as the first dataset (D18, adr/0007 §12.6): the
# EOPF item itself links an alias host (sentinel.esa.int) for the identical
# document; the canonical URL from adr/0003 is kept so both entries carry one
# record of the same terms rather than two that happen to agree today.
SENTINEL_2_L2A_ZARR3 = DatasetConfig(
    # The upstream collection id, and the *only* Sentinel-2 collection of this
    # source in the registry (adr/0007 §12.11 point 12): `sentinel-2-l2a` (the
    # older, ungrouped v2 layout) shares item ids with this one for current days
    # and is deliberately left out, or the two would collide in the federated
    # search's id space.
    dataset_id="sentinel-2-l2a-zarr3",
    title="Sentinel-2 L2A (Zarr3)",
    description=(
        "Sentinel-2 Level-2A as cloud-native Zarr (v3), served by the EOPF "
        "Sentinel Zarr Samples Service (EODC) from data.eodc.eu. Six resolution "
        "groups from 10 m to 720 m in one sharded store, CRS carried in the store "
        "itself (adr/0007 §12.3). The provider marks this collection 'staging' "
        "(earthx:maturity) — it may disappear without notice (adr/0007 §12.11 "
        "point 14)."
    ),
    # The collection's own `cite-as` link (checked 22.09.2026); no separate
    # persistent citation beyond it.
    doi="https://doi.org/10.5270/S2_-znk9xsj",
    citation=None,
    data_class=DataClass.RASTER_TIME_SERIES,
    format=DataFormat.ZARR,
    # Measured at the collection itself (adr/0007 §12.6, rechecked 22.09.2026):
    # not a placeholder like the first dataset's M1 entry — M2-09b reads the
    # source before writing this.
    spatial_extent=SpatialExtent(bbox=(-33.00058364868164, 34.20681381225586, 179.58160400390625, 72.0995864868164)),
    # Start is the earliest item measured (adr/0007 §12.6: "erst ab 16. Juli
    # belegt"); the end stays open — the archive is a moving, growing window
    # (rund 1300 Items/Tag), not a closed one like a one-off product.
    temporal_extent=TemporalExtent(start=datetime(2026, 7, 16, 10, 6, 1, tzinfo=timezone.utc), end=None),
    capabilities=Capabilities(
        roi=True,
        time_range=True,
        band_math=True,
        interpolation=True,
        ml_processing=True,
        # Optical, dual-pol source data — decomp.py stays out (ENTSCHEIDUNGEN §3).
        quad_pol=False,
        # A time series, not a single coverage: density, not extent (adr/0004 §5).
        single_coverage_product=False,
    ),
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
        attribution_modified="Contains modified Copernicus Sentinel data {year}",
        attribution_unmodified="Copernicus Sentinel data {year}",
        # Identical text to the first dataset (D18) — one Sentinel Data Legal
        # Notice, passed on the same way regardless of which source served the
        # pixels. Otto, 22.09.2026 (M2-15): the platform offers no language
        # choice at all, so the key set is exactly {"en"} — TermsOfUse checks
        # this now (catalog/registry.py).
        terms=TermsOfUse(
            url=_LEGAL_NOTICE_URL,
            notice={
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
        token_free_checked_at=_EOPF_CHECKED,
        method="anonymous HTTPS, no authentication header (adr/0007 §12.1, rechecked 22.09.2026)",
        # Measured at data.eodc.eu, not at the older objects.eodc.eu (adr/0007
        # §12.8): `Access-Control-Allow-Origin: *`, including on the `Range`
        # header a Zarr reader needs. The viewer may load a quicklook straight
        # from the source under this flag — moot here, since there is none
        # (§12.7); the flag stays correct regardless of who reads it.
        cors=True,
    ),
    source=SourceInfo(
        adapter=AdapterKind.EOPF_STAC_V1,
        endpoint="https://stac.core.eopf.eodc.eu",
        source_collection_id="sentinel-2-l2a-zarr3",
        # The only asset host this dataset opens (adr/0007 §12.11 point 5):
        # `objects.eodc.eu` belongs to the older `sentinel-2-l2a` collection, and
        # `zipped_product` (1.2 GB, also on data.eodc.eu) is kept out by naming no
        # asset key for it anywhere a reader would resolve one, not by the host
        # allowlist (point 10 — the allowlist alone no longer keeps it out).
        asset_hosts=("data.eodc.eu",),
        harvest_run=None,
        item_holding=ItemHolding.FEDERATED,
    ),
    coverage=CoverageInfo(
        provider=CoverageProvider.SAMPLE,
        # Same granule size as the first dataset — this is still Sentinel-2, only
        # a different store — so the same footprint and the same derived cap
        # apply (max_geotile_level_for(110.0) == 8, checked by _check_coverage).
        typical_footprint_km=110.0,
        max_geotile_level=8,
    ),
    # True colour from the `r10m`/`SR_10m` group, which carries b02/b03/b04/b08 on
    # every level (plan §3.3) — the band selection this depends on. `(0.0, 0.30)`
    # per band is a deliberate starting point, not a measurement (plan §4.5, §10
    # F6): `mask_and_scale` hands this reader reflectance as a float, not the 8-bit
    # RGB `visual` already is for the first dataset, and `/statistics` overwrites
    # it with the scene's own range before anyone looks at a pixel (Z4, F18).
    #
    # One asset, not three: a Zarr band is never pre-stacked into one RGB file the
    # way `visual` is (adr/0007 §12.7), and the tile route resolves exactly one
    # asset per request (`api.tiler.dataset_asset_path`) — three separate asset
    # keys here would each render one band alone, grayscale, one at a time (the
    # M2-09b-2 bug this comment is the fix for). `readers.zarr_reader.ZarrReader`
    # reads several comma-separated variables of one group and composites them,
    # in the order named — this is that one asset key.
    default_render=DefaultRender(
        title="True colour",
        assets=("SR_10m:b04,b03,b02",),
        rescale=((0.0, 0.30), (0.0, 0.30), (0.0, 0.30)),
        colormap_name=None,
        expression=None,
        resampling="nearest",
    ),
    # Same grouping key as the first dataset: one acquisition day per MGRS tile.
    # Measured at a real item (22.09.2026): both `datetime` and `grid:code` are
    # present on every item of this collection.
    # Zoom levels released for the tile path (D23/F9, adr/0007 §12.10, measured):
    # below z8 one tile shows several scenes, which is the coverage map's job and
    # not the tile path's; above z14 the store has nothing finer than r10m, so a
    # client overzooms the last level — which costs *less*, since the window read
    # gets smaller. The level itself is still computed from the requested tile's
    # own ground resolution (api.tiler._target_gsd), never looked up from the zoom.
    viewer=ViewerInfo(group_by=("datetime", "grid:code"), min_zoom=8, max_zoom=14),
    health=HealthInfo(status=HealthStatus.OK),
    # adr/0007 §12.11 point 14 (Otto's first F8 condition): the provider calls
    # this collection "staging" in its own title, and that must not be something
    # a user finds out only once the source disappears.
    maturity=Maturity.STAGING,
    # Bands live inside resolution groups (adr/0007 §12.3, plan §3.2): an asset
    # href names the group only, and the tile URL's asset key carries the
    # variable after ":" (plan §10 F2). `multiscales` follows a named pilot
    # convention (measured, plan §3 / adr/0007 §12.3, §12.11 point 2).
    zarr=ZarrInfo(
        variable_separator=":",
        multiscales_convention="zarr-conventions/multiscales v0.1 (pilot)",
    ),
)

# M3-11b, F1: no single acquisition instant exists for the DEM (`adr/0009`
# §10.1) — a period instead, the same for every tile and for the collection
# itself, belonging to the *product*, not a measurement of one scene. Read
# from the Product Handbook (v5.0, 29.11.2022, p. 30): "the TanDEM-X/WorldDEM
# has been acquired between December 2010 and January 2015." Exported because
# `adapters.cop_dem_bucket` stamps every item with the same two instants —
# `adapters` may import `catalog` (`.importlinter`), not the other way round,
# so the constant lives here rather than being duplicated at both ends.
DEM_ACQUISITION_START = datetime(2010, 12, 1, tzinfo=timezone.utc)
DEM_ACQUISITION_END = datetime(2015, 1, 31, 23, 59, 59, tzinfo=timezone.utc)

# adr/0003 §11.1: the licence PDF the AWS registry entry and the CDSE COP-DEM
# page both link, read on 18.09.2026 and rechecked 26.09.2026 (M3-11b plan §2.7).
_DEM_LICENSE_URL = (
    "https://dataspace.copernicus.eu/sites/default/files/media/files/2025-06/"
    "copernicus_contributing_mission_data_access_v2_cop_dem_licenses.pdf"
)

# The licence's own vocabulary (Art. 6 a/b) and its liability waiver (Art. 6 c),
# read from the primary document on 18.09.2026 (`adr/0003` §11.1) and reused
# here verbatim rather than paraphrased.
_DEM_ATTRIBUTION = (
    "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 "
    "provided under COPERNICUS by the European Union and ESA; all rights reserved"
)

COP_DEM_GLO_30 = DatasetConfig(
    # The name Earth Search and Microsoft Planetary Computer both use for the
    # same product (M3-11b plan §3.6, F4) — no collision with either of the
    # two entries above, because this one is not federated through them.
    dataset_id="cop-dem-glo-30",
    title="Copernicus DEM GLO-30",
    description=(
        "Copernicus DEM GLO-30 Public: global 30 m digital surface model from "
        "the TanDEM-X mission (acquired December 2010 to January 2015), as "
        "cloud-optimized GeoTIFF in 1° × 1° tiles, read directly "
        "from the AWS Open Data bucket (state of 9 May 2022, adr/0009 §7.3). "
        "Oceans carry no tiles, and 25 tiles between 38° and 42° N and "
        "43° and 51° E are withheld from public release by the "
        "Copernicus programme (adr/0009 §10.3)."
    ),
    # The product's own citation DOI (M3-11b plan §2.7, read from the CDSE
    # COP-DEM page 26.09.2026) — the same page `adr/0003` §11.1 reads the
    # licence from. Not specific to the GLO-30 instance; it is what the source
    # itself asks to be cited with.
    doi="https://doi.org/10.5270/ESA-c5d3d65",
    citation=None,
    # A single elevation model, not a stream of acquisitions (P24, adr/0009 §6):
    # `single_coverage_product` below follows from this, not the other way round.
    data_class=DataClass.RASTER_STATIC,
    format=DataFormat.COG,
    # From the bucket's own tile list (M3-11b plan §2.1, §2.6): latitudes S90 to
    # N83, longitudes W180 to E179 (so the nominal cells reach N84/E180).
    spatial_extent=SpatialExtent(bbox=(-180.0, -90.0, 180.0, 84.0)),
    temporal_extent=TemporalExtent(start=DEM_ACQUISITION_START, end=DEM_ACQUISITION_END),
    capabilities=Capabilities(
        roi=True,
        # No acquisition stream to filter by date (M3-11b F1) — a search with a
        # time window is a question this dataset does not answer differently
        # from one without (the ADR-decided behaviour for M3-12/M3-13: shown
        # regardless of the chosen range, never date-filtered).
        time_range=False,
        band_math=True,
        interpolation=True,
        ml_processing=True,
        # No complex quad-pol data — decomp.py stays out (ENTSCHEIDUNGEN §3).
        quad_pol=False,
        # One elevation model, not a time series: extent, not density (adr/0004 §5).
        single_coverage_product=True,
    ),
    license=LicenseInfo(
        spdx_id=None,
        name="Licence for Copernicus DEM instance COP-DEM-GLO-30-F Global 30m Full, Free & Open",
        url=_DEM_LICENSE_URL,
        commercial_use=True,
        distribution=True,
        derivatives=True,
        share_alike=False,
        attribution_required=True,
        tier=LicenseTier.PROCESSING,
        # Art. 6 b: the modified-data wording adds "produced using Copernicus
        # WorldDEM-30" to the same attribution the unmodified data carries.
        attribution_modified=f"{_DEM_ATTRIBUTION}; produced using Copernicus WorldDEM-30",
        attribution_unmodified=_DEM_ATTRIBUTION,
        terms=TermsOfUse(
            url=_DEM_LICENSE_URL,
            notice={
                # Art. 6 c, the licence's own liability waiver, shortened only
                # where it names the licence itself (`adr/0003` §11.1).
                "en": (
                    "Use is subject to the Licence for Copernicus DEM instance "
                    "COP-DEM-GLO-30-F Global 30m Full, Free & Open: {terms_url}. "
                    "The organisations in charge of the Copernicus programme, "
                    "the European Union and ESA, do not incur any liability for "
                    "the use of this data."
                ),
            },
        ),
    ),
    access=AccessInfo(
        token_free_checked_at=date(2026, 9, 26),
        method="anonymous HTTPS, no authentication header (M3-11b plan §2.1)",
        # Measured 26.09.2026 (M3-11b plan §2.2): no Access-Control-Allow-Origin
        # on a plain GET. Moot for this dataset — it has no quicklook a browser
        # would load straight from the source (M3-12 decides what appears
        # instead: the full-resolution AOI crop, per the M3-11b F11 Nachtrag).
        cors=False,
    ),
    source=SourceInfo(
        adapter=AdapterKind.COP_DEM_BUCKET,
        endpoint="https://copernicus-dem-30m.s3.amazonaws.com",
        # The bucket has no STAC collection of its own (`adr/0009` §5) — its own
        # name is the closest thing to a source-side identifier.
        source_collection_id="copernicus-dem-30m",
        # The global bucket name (`adr/0009` §10.2, M3-11b plan §2): never the
        # bare `s3.amazonaws.com` or `amazonaws.com`, which would open every
        # bucket on AWS to `gateway`'s allowlist (`registry.py`
        # `DatasetConfig._check_source`).
        asset_hosts=("copernicus-dem-30m.s3.amazonaws.com",),
        harvest_run=None,
        item_holding=ItemHolding.MATERIALIZED,
    ),
    coverage=CoverageInfo(
        provider=CoverageProvider.LOCAL_SQL,
        # The nominal 1x1-degree cell a tile name gives (`adapters.
        # cop_dem_bucket`); `max_geotile_level_for(111.0) == 8`, checked by
        # `DatasetConfig._check_coverage`.
        typical_footprint_km=111.0,
        max_geotile_level=8,
    ),
    default_render=DefaultRender(
        title="Elevation",
        assets=("data",),
        # 0..5000 m: covers every measured tile's p98 (max 5907 m at the
        # Himalaya sample, M3-11b plan §2.4) except the very highest peaks,
        # which saturate white rather than clip to a flat colour — the
        # trade-off `terrain` is chosen for (F6).
        rescale=((0.0, 5000.0),),
        colormap_name="terrain",
        expression=None,
        resampling="nearest",
    ),
    # F7: every tile shares the same `start_datetime` (there is only one), so
    # grouping by it puts every DEM tile in one group — a AOI crop over several
    # tiles becomes one merged file (P19), the way a Sentinel-2 overpass does.
    # z8 is roughly one DEM tile wide; z15 is three levels past the native
    # ~30 m/px resolution, for zooming into real detail without reaching
    # MapLibre's own z22 ceiling on a dataset with nothing finer to give past it.
    viewer=ViewerInfo(group_by=("start_datetime",), min_zoom=8, max_zoom=15),
    health=HealthInfo(status=HealthStatus.OK),
    # A released, versioned product (state of 9 May 2022), not a pilot.
    maturity=Maturity.STABLE,
    zarr=None,
)

REGISTRY = DatasetRegistry((SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3, COP_DEM_GLO_30))
