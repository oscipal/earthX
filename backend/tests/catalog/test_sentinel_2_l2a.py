"""The Sentinel-2 L2A entry against what docs/ decided about it.

Every assertion here has a place it comes from. If one fails, either the entry
drifted or a decision changed — both need a look at the document, not a quick fix.
"""

from __future__ import annotations

from datetime import date

from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.registry import (
    AdapterKind,
    CoverageProvider,
    DataClass,
    DataFormat,
    LicenseTier,
)


def test_source_is_earth_search_collection_one() -> None:
    """adr/0003 §6: Collection 1, COGs only."""
    assert SENTINEL_2_L2A.source.adapter is AdapterKind.EARTH_SEARCH_V1
    assert SENTINEL_2_L2A.source.source_collection_id == "sentinel-2-c1-l2a"
    assert SENTINEL_2_L2A.source.endpoint.startswith("https://")
    assert SENTINEL_2_L2A.format is DataFormat.COG
    assert SENTINEL_2_L2A.data_class is DataClass.RASTER_TIME_SERIES


def test_items_are_federated_not_harvested() -> None:
    """architekturplan.md 5.2: Earth Search has a search API, so nothing is copied."""
    assert SENTINEL_2_L2A.source.harvest_run is None


def test_license_is_processing_with_the_flags_from_adr_0003() -> None:
    """adr/0003 §11.2, checked by Otto against the Sentinel Data Legal Notice."""
    lic = SENTINEL_2_L2A.license
    assert lic.tier is LicenseTier.PROCESSING
    assert lic.commercial_use is True
    assert lic.derivatives is True
    assert lic.share_alike is False
    assert lic.attribution_required is True


def test_attribution_and_liability_texts_are_present() -> None:
    """They travel with the download, so they cannot be missing (adr/0003 §11.2)."""
    lic = SENTINEL_2_L2A.license
    assert lic.attribution_modified == "Contains modified Copernicus Sentinel data {year}"
    assert lic.attribution_unmodified == "Copernicus Sentinel data {year}"
    assert lic.liability_notice
    assert "{year}" in lic.attribution_modified


def test_license_has_no_spdx_id_but_names_its_source() -> None:
    """No SPDX identifier exists for the Legal Notice (projektuebersicht.md §5)."""
    lic = SENTINEL_2_L2A.license
    assert lic.spdx_id is None
    assert lic.name and lic.url.startswith("https://")
    assert lic.stac_license == "proprietary"


def test_quad_pol_is_off() -> None:
    """ENTSCHEIDUNGEN §3: decomp.py needs complex quad-pol data; Sentinel-2 has none."""
    assert SENTINEL_2_L2A.capabilities.quad_pol is False


def test_coverage_is_upstream_aggregation_capped_at_z8() -> None:
    """adr/0004 §5: Earth Search aggregates, and a 110 km footprint caps the grid."""
    coverage = SENTINEL_2_L2A.coverage
    assert coverage.provider is CoverageProvider.UPSTREAM_AGGREGATION
    assert coverage.max_geotile_level == 8
    assert SENTINEL_2_L2A.capabilities.single_coverage_product is False


def test_access_and_health_are_dated() -> None:
    """Onboarding checklist points 6 and 10: the check has a date and it is visible."""
    assert SENTINEL_2_L2A.access.token_free_checked_at == date(2026, 9, 18)
    assert SENTINEL_2_L2A.health.last_checked_ok == date(2026, 9, 18)
