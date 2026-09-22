"""The sentinel-2-l2a-zarr3 entry against what docs/ decided about it.

Every assertion here has a place it comes from: adr/0007 §12 (the M2-03b
remeasurement) and §12.11 (the fifteen implementation conditions), plus the
M2-09b plan step's own recheck (plan §3). If one fails, either the entry drifted
or a decision changed — both need a look at the document, not a quick fix.
"""

from __future__ import annotations

from datetime import date

from earthx.catalog.datasets import SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3
from earthx.catalog.registry import (
    AdapterKind,
    CoverageProvider,
    DataClass,
    DataFormat,
    LicenseTier,
    Maturity,
)


def test_source_is_the_eopf_stac_api() -> None:
    """adr/0007 §12: the v3 store, served by the EOPF Sentinel Zarr Samples Service."""
    assert SENTINEL_2_L2A_ZARR3.source.adapter is AdapterKind.EOPF_STAC_V1
    assert SENTINEL_2_L2A_ZARR3.source.endpoint.startswith("https://")
    assert SENTINEL_2_L2A_ZARR3.format is DataFormat.ZARR
    assert SENTINEL_2_L2A_ZARR3.data_class is DataClass.RASTER_TIME_SERIES


def test_our_id_is_the_upstream_ones_and_the_only_one_taken() -> None:
    """adr/0007 §12.11 point 12: `sentinel-2-l2a` (the older v2 layout) shares item
    ids with this collection for current days — taking both would collide in the
    federated search's id space, so only `…-zarr3` is in the registry."""
    assert SENTINEL_2_L2A_ZARR3.dataset_id == "sentinel-2-l2a-zarr3"
    assert SENTINEL_2_L2A_ZARR3.dataset_id == SENTINEL_2_L2A_ZARR3.source.source_collection_id
    assert SENTINEL_2_L2A_ZARR3.dataset_id != "sentinel-2-l2a"


def test_items_are_federated_not_harvested() -> None:
    """architekturplan.md 5.2: the source has a search API, so nothing is copied."""
    assert SENTINEL_2_L2A_ZARR3.source.harvest_run is None


def test_the_asset_host_is_the_open_one_not_the_older_collections() -> None:
    """adr/0007 §12.11 point 5: only `data.eodc.eu`. `objects.eodc.eu` belongs to
    the older `sentinel-2-l2a` collection, which is not aggregated here."""
    assert SENTINEL_2_L2A_ZARR3.source.asset_hosts == ("data.eodc.eu",)


def test_the_source_sends_cors() -> None:
    """adr/0007 §12.8/§12.11 point 4, measured at data.eodc.eu (not objects.eodc.eu,
    where §3.9 found none) — includes the `Range` header a Zarr reader needs."""
    assert SENTINEL_2_L2A_ZARR3.access.cors is True


def test_the_license_matches_the_first_dataset() -> None:
    """D18: same fields as the first dataset — one Sentinel Data Legal Notice."""
    lic = SENTINEL_2_L2A_ZARR3.license
    assert lic.tier is LicenseTier.PROCESSING
    assert lic.commercial_use is True
    assert lic.derivatives is True
    assert lic.distribution is True
    assert lic.url == SENTINEL_2_L2A.license.url
    assert lic.terms is not None
    assert lic.terms.url == SENTINEL_2_L2A.license.terms.url


def test_quad_pol_is_off() -> None:
    """ENTSCHEIDUNGEN §3: decomp.py needs complex quad-pol data; this source has none."""
    assert SENTINEL_2_L2A_ZARR3.capabilities.quad_pol is False


def test_coverage_is_a_declared_sample() -> None:
    """adr/0007 §12.11 point 13: no `numberMatched`, no `/aggregations` — the
    upstream-aggregation path from the first dataset does not apply here."""
    coverage = SENTINEL_2_L2A_ZARR3.coverage
    assert coverage.provider is CoverageProvider.SAMPLE
    assert SENTINEL_2_L2A_ZARR3.capabilities.single_coverage_product is False


def test_the_grid_cap_follows_the_same_footprint_as_the_first_dataset() -> None:
    """Same granule size (110 km, a Sentinel-2 MGRS tile) as the first dataset, so
    the same derived cap applies — not a new measurement (M2-09b plan §4.1)."""
    assert SENTINEL_2_L2A_ZARR3.coverage.typical_footprint_km == SENTINEL_2_L2A.coverage.typical_footprint_km
    assert SENTINEL_2_L2A_ZARR3.coverage.max_geotile_level == SENTINEL_2_L2A.coverage.max_geotile_level


def test_the_viewer_groups_one_acquisition_day_per_mgrs_tile() -> None:
    """Same key as the first dataset (M2-09b plan §3.1): `datetime` and `grid:code`
    are both present on every item of this collection, measured 22.09.2026."""
    viewer = SENTINEL_2_L2A_ZARR3.viewer
    assert viewer is not None
    assert viewer.group_by == ("datetime", "grid:code")


def test_default_render_is_left_open_for_m2_09b_2() -> None:
    """adr/0007 §12.11 points 2 and 8: the standard visualisation depends on the
    resolution and band selection M2-09b-2 builds — not yet decided here."""
    assert SENTINEL_2_L2A_ZARR3.default_render is None


def test_maturity_is_staging() -> None:
    """adr/0007 §12.11 point 14 (Otto's first F8 condition): the provider calls this
    collection "staging" in its own title, and the registry must say so too."""
    assert SENTINEL_2_L2A_ZARR3.maturity is Maturity.STAGING
    assert SENTINEL_2_L2A.maturity is Maturity.STABLE


def test_zarr_info_records_the_group_addressing_and_the_pilot_convention() -> None:
    """M2-09b plan §3.2/§10 F2: the asset href names a resolution group, not a
    variable — the tile URL's asset key carries the variable after `:`."""
    zarr = SENTINEL_2_L2A_ZARR3.zarr
    assert zarr is not None
    assert zarr.variable_separator == ":"
    assert zarr.multiscales_convention is not None
    assert SENTINEL_2_L2A.zarr is None


def test_zipped_product_is_not_reachable_as_an_asset() -> None:
    """adr/0007 §12.11 point 10: the 1.2 GB archive lives on the now-open
    data.eodc.eu, so the host allowlist alone no longer keeps it out — nothing in
    the entry names `zipped_product` as an asset key a reader could resolve."""
    assert "zipped_product" not in SENTINEL_2_L2A_ZARR3.description


def test_access_and_health_are_dated() -> None:
    """Onboarding checklist points 6 and 10: the check has a date and it is visible."""
    checked = date(2026, 9, 22)
    assert SENTINEL_2_L2A_ZARR3.access.token_free_checked_at == checked
    assert SENTINEL_2_L2A_ZARR3.health.last_checked_ok == checked


def test_the_doi_is_the_collections_cite_as_link() -> None:
    """Checklist point 3: the collection names its own DOI, measured 22.09.2026."""
    assert SENTINEL_2_L2A_ZARR3.doi is not None
    assert SENTINEL_2_L2A_ZARR3.doi.startswith("https://doi.org/")


def test_temporal_extent_starts_fixed_and_ends_open() -> None:
    """adr/0007 §12.6: a moving, growing archive (rund 1300 Items/Tag) is not a
    closed window like a one-off product's."""
    extent = SENTINEL_2_L2A_ZARR3.temporal_extent
    assert extent.start is not None
    assert extent.end is None
