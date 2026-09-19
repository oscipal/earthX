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


def test_our_id_is_the_upstream_one_not_the_collection_it_replaces() -> None:
    """Otto, 19.09.2026: the short "sentinel-2-l2a" is the older Earth Search
    collection that Collection 1 replaces (adr/0003 §3). Using it for our entry
    would read as that one.
    """
    assert SENTINEL_2_L2A.dataset_id == "sentinel-2-c1-l2a"
    assert SENTINEL_2_L2A.dataset_id == SENTINEL_2_L2A.source.source_collection_id


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


def test_attribution_texts_are_present() -> None:
    """They travel with the download, so they cannot be missing (adr/0003 §11.2)."""
    lic = SENTINEL_2_L2A.license
    assert lic.attribution_modified == "Contains modified Copernicus Sentinel data {year}"
    assert lic.attribution_unmodified == "Copernicus Sentinel data {year}"
    assert "{year}" in lic.attribution_modified


def test_the_terms_come_from_the_source_not_from_us() -> None:
    """Otto, 19.09.2026: at a download we pass on the source's terms.

    The Legal Notice carries no disclaimer by the provider — it carries a waiver by
    the user and "without any express or implied warranty". An earlier draft of this
    entry borrowed a disclaimer from the Copernicus DEM licence (adr/0003 §11.1),
    which inverted the direction; the text now follows the document that applies.
    """
    terms = SENTINEL_2_L2A.license.terms
    assert terms is not None
    assert terms.url.endswith("Sentinel_Data_Legal_Notice")
    assert set(terms.notice) == {"de", "en"}


def test_both_terms_texts_name_the_waiver_and_the_missing_warranty() -> None:
    terms = SENTINEL_2_L2A.license.terms
    assert "ohne Gewähr" in terms.notice["de"]
    assert "Schadensersatzansprüche" in terms.notice["de"]
    assert "without" in terms.notice["en"] and "warranty" in terms.notice["en"]
    assert "renounces any claims for damages" in terms.notice["en"]


def test_the_terms_text_can_be_filled_in_at_a_download() -> None:
    """The one placeholder resolves, and nothing else is left over."""
    terms = SENTINEL_2_L2A.license.terms
    for text in terms.notice.values():
        filled = text.format(terms_url=terms.url)
        assert "{" not in filled and "}" not in filled
        assert terms.url in filled


def test_the_terms_text_carries_no_attribution() -> None:
    """Otto, 19.09.2026: attribution stays separate and goes in front of the terms.

    Repeating it here would either duplicate it, or claim modified data where we pass
    on unmodified ones — the two attribution texts differ in exactly that.
    """
    lic = SENTINEL_2_L2A.license
    for text in lic.terms.notice.values():
        assert "{year}" not in text
        assert "Copernicus Sentinel data" not in text
        assert "Copernicus-Sentinel-Daten" not in text


def test_license_has_no_spdx_id_but_names_its_source() -> None:
    """No SPDX identifier exists for the Legal Notice (projektuebersicht.md §5)."""
    lic = SENTINEL_2_L2A.license
    assert lic.spdx_id is None
    assert lic.name and lic.url.startswith("https://")


def test_quad_pol_is_off() -> None:
    """ENTSCHEIDUNGEN §3: decomp.py needs complex quad-pol data; Sentinel-2 has none."""
    assert SENTINEL_2_L2A.capabilities.quad_pol is False


def test_coverage_is_upstream_aggregation_capped_at_z8() -> None:
    """adr/0004 §5: Earth Search aggregates, and a 110 km footprint caps the grid."""
    coverage = SENTINEL_2_L2A.coverage
    assert coverage.provider is CoverageProvider.UPSTREAM_AGGREGATION
    assert coverage.max_geotile_level == 8
    assert SENTINEL_2_L2A.capabilities.single_coverage_product is False


def test_the_standard_visualisation_is_open() -> None:
    """Checklist point 8 is not answered by docs/; m1-fundament.md §2 puts it in M2."""
    assert SENTINEL_2_L2A.default_render is None


def test_the_citation_is_open() -> None:
    """Checklist point 3: adr/0003 names neither a DOI nor a persistent citation."""
    assert SENTINEL_2_L2A.doi is None
    assert SENTINEL_2_L2A.citation is None


def test_distribution_and_modification_are_both_allowed() -> None:
    """KLAERUNGEN B11 needs both for tier Processing, not modification alone."""
    assert SENTINEL_2_L2A.license.distribution is True
    assert SENTINEL_2_L2A.license.derivatives is True


def test_access_and_health_are_dated() -> None:
    """Onboarding checklist points 6 and 10: the check has a date and it is visible."""
    assert SENTINEL_2_L2A.access.token_free_checked_at == date(2026, 9, 18)
    assert SENTINEL_2_L2A.health.last_checked_ok == date(2026, 9, 18)
