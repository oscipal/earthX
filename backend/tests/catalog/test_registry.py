"""What a registry entry must not get away with.

The rules under test are decisions from docs/, not preferences: KLAERUNGEN B10
(every capability set deliberately), B11 (licence tier), adr/0004 §5 (the grid cap
and one-off products) and adr/0005 rule I (an unknown dataset is an error, not an
empty result).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from earthx.catalog.datasets import REGISTRY, SENTINEL_2_L2A
from earthx.catalog.registry import (
    Capabilities,
    ConfigError,
    CoverageProvider,
    DatasetConfig,
    DatasetRegistry,
    DefaultRender,
    HealthInfo,
    HealthStatus,
    LicenseTier,
    SpatialExtent,
    TemporalExtent,
    UnknownDatasetError,
    max_geotile_level_for,
)


class TestCapabilitiesAreExplicit:
    """KLAERUNGEN B10: a forgotten flag must not silently default to anything."""

    @pytest.mark.parametrize(
        "omitted",
        [
            "roi",
            "time_range",
            "band_math",
            "interpolation",
            "ml_processing",
            "quad_pol",
            "single_coverage_product",
        ],
    )
    def test_omitting_any_flag_is_an_error(self, omitted: str) -> None:
        flags = {
            "roi": True,
            "time_range": True,
            "band_math": True,
            "interpolation": True,
            "ml_processing": False,
            "quad_pol": False,
            "single_coverage_product": False,
        }
        del flags[omitted]
        with pytest.raises(TypeError, match=omitted):
            Capabilities(**flags)

    def test_a_flag_cannot_be_changed_after_the_fact(self, valid_config) -> None:
        with pytest.raises(AttributeError):
            valid_config.capabilities.quad_pol = True


class TestLicenseTier:
    """KLAERUNGEN B11: no modification allowed means catalogue entry with a link."""

    @pytest.mark.parametrize("tier", [LicenseTier.DISPLAY, LicenseTier.PROCESSING])
    def test_no_derivatives_above_catalog_is_rejected(self, valid_config, vary, tier) -> None:
        license_info = replace(valid_config.license, derivatives=False, tier=tier)
        with pytest.raises(ConfigError, match="derivatives"):
            vary(license=license_info)

    def test_no_derivatives_is_fine_as_a_catalog_entry(self, valid_config, vary) -> None:
        license_info = replace(valid_config.license, derivatives=False, tier=LicenseTier.CATALOG)
        assert vary(license=license_info).license.tier is LicenseTier.CATALOG

    @pytest.mark.parametrize("tier", [LicenseTier.DISPLAY, LicenseTier.PROCESSING])
    def test_no_distribution_above_catalog_is_rejected(self, valid_config, vary, tier) -> None:
        """B11 asks for distribution *and* modification; modification alone is not enough."""
        license_info = replace(valid_config.license, distribution=False, tier=tier)
        with pytest.raises(ConfigError, match="distribution"):
            vary(license=license_info)

    def test_a_licence_without_spdx_needs_a_name_and_a_url(self, valid_config, vary) -> None:
        """projektuebersicht.md §5: an SPDX identifier, or free text that identifies it."""
        license_info = replace(valid_config.license, spdx_id=None, name="", url="")
        with pytest.raises(ConfigError, match="SPDX"):
            vary(license=license_info)

    def test_a_licence_without_spdx_but_with_a_name_is_fine(self, valid_config, vary) -> None:
        license_info = replace(valid_config.license, spdx_id=None)
        assert vary(license=license_info).license.spdx_id is None

    def test_required_attribution_without_a_text_is_rejected(self, valid_config, vary) -> None:
        license_info = replace(
            valid_config.license,
            attribution_required=True,
            attribution_modified=None,
            attribution_unmodified=None,
        )
        with pytest.raises(ConfigError, match="attribution"):
            vary(license=license_info)


class TestCoverage:
    """adr/0004 §5: the cap follows from the footprint, and a one-off has no density."""

    def test_a_finer_grid_than_the_footprint_allows_is_rejected(self, valid_config, vary) -> None:
        coverage = replace(valid_config.coverage, max_geotile_level=9)
        with pytest.raises(ConfigError, match="z8"):
            vary(coverage=coverage)

    def test_a_coarser_grid_is_allowed(self, valid_config, vary) -> None:
        coverage = replace(valid_config.coverage, max_geotile_level=6)
        assert vary(coverage=coverage).coverage.max_geotile_level == 6

    def test_a_one_off_product_cannot_use_upstream_aggregation(self, valid_config, vary) -> None:
        capabilities = replace(valid_config.capabilities, single_coverage_product=True)
        with pytest.raises(ConfigError, match="extent"):
            vary(capabilities=capabilities)

    def test_a_one_off_product_may_use_a_sample(self, valid_config, vary) -> None:
        capabilities = replace(valid_config.capabilities, single_coverage_product=True)
        coverage = replace(valid_config.coverage, provider=CoverageProvider.SAMPLE)
        assert vary(capabilities=capabilities, coverage=coverage).coverage.provider is CoverageProvider.SAMPLE

    def test_a_footprint_of_zero_is_rejected(self, valid_config, vary) -> None:
        coverage = replace(valid_config.coverage, typical_footprint_km=0.0)
        with pytest.raises(ConfigError, match="greater than zero"):
            vary(coverage=coverage)

    def test_a_negative_grid_level_is_rejected(self, valid_config, vary) -> None:
        coverage = replace(valid_config.coverage, max_geotile_level=-1)
        with pytest.raises(ConfigError, match="negative"):
            vary(coverage=coverage)

    def test_a_footprint_wider_than_the_planet_is_rejected(self) -> None:
        with pytest.raises(ConfigError, match="wider than the planet"):
            max_geotile_level_for(50_000.0)

    def test_a_sentinel_2_footprint_caps_the_grid_at_z8(self) -> None:
        """The cap and the granule size agree.

        Not a derivation of z8: adr/0004 §5 sets that level, and any width between
        78.3 and 156.5 km would produce it. The check is that the two do not
        contradict each other.
        """
        assert max_geotile_level_for(110.0) == 8


class TestLookup:
    """adr/0005 rule I: an unknown collection is a 404, never an empty result."""

    def test_unknown_dataset_raises_its_own_error(self) -> None:
        with pytest.raises(UnknownDatasetError, match="does-not-exist"):
            REGISTRY.get("does-not-exist")

    def test_known_dataset_is_returned(self) -> None:
        assert REGISTRY.get("sentinel-2-c1-l2a") is SENTINEL_2_L2A

    def test_a_duplicate_id_is_rejected(self) -> None:
        with pytest.raises(ConfigError, match="duplicate"):
            DatasetRegistry((SENTINEL_2_L2A, SENTINEL_2_L2A))

    def test_membership_and_length(self) -> None:
        assert "sentinel-2-c1-l2a" in REGISTRY
        assert "does-not-exist" not in REGISTRY
        assert len(REGISTRY) == len(list(REGISTRY))


class TestMalformedInput:
    """Wrong values, not just missing ones — the entry is written by hand."""

    @pytest.mark.parametrize(
        "bbox",
        [
            (-200.0, -10.0, 10.0, 10.0),
            (-10.0, -100.0, 10.0, 10.0),
            (10.0, -10.0, -10.0, 10.0),
            (-10.0, 10.0, 10.0, -10.0),
            (-10.0, -10.0, -10.0, 10.0),
        ],
        ids=["west out of range", "south out of range", "west past east", "south past north", "empty"],
    )
    def test_a_broken_bbox_is_rejected(self, bbox) -> None:
        with pytest.raises(ConfigError, match="bbox"):
            SpatialExtent(bbox=bbox)

    def test_an_extent_that_ends_before_it_starts_is_rejected(self) -> None:
        with pytest.raises(ConfigError, match="ends before"):
            TemporalExtent(
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2020, 1, 1, tzinfo=timezone.utc),
            )

    @pytest.mark.parametrize("stretch", [(1.0, 1.0), (3000.0, 0.0)])
    def test_an_empty_or_inverted_stretch_is_rejected(self, stretch) -> None:
        with pytest.raises(ConfigError, match="stretch"):
            DefaultRender(bands=("red",), stretch=stretch, colormap=None)

    def test_a_visualisation_without_bands_is_rejected(self) -> None:
        with pytest.raises(ConfigError, match="band"):
            DefaultRender(bands=(), stretch=(0.0, 1.0), colormap=None)

    def test_health_ok_without_a_date_is_rejected(self) -> None:
        """KLAERUNGEN B12: "last checked successfully" has to be set to mean anything."""
        with pytest.raises(ConfigError, match="last successful check"):
            HealthInfo(status=HealthStatus.OK, last_checked_ok=None)

    def test_health_unknown_without_a_date_is_fine(self) -> None:
        assert HealthInfo(status=HealthStatus.UNKNOWN, last_checked_ok=None).last_checked_ok is None

    @pytest.mark.parametrize("endpoint", ["http://example.invalid/v1", "file:///etc/passwd", "example.invalid"])
    def test_a_non_https_endpoint_is_rejected(self, valid_config, vary, endpoint) -> None:
        """KLAERUNGEN B8: only https goes out, and the registry is where it is named."""
        with pytest.raises(ConfigError, match="https"):
            vary(source=replace(valid_config.source, endpoint=endpoint))


class TestEveryEntry:
    """KLAERUNGEN B10 asks for a check per entry, not per entry we happened to write."""

    @pytest.fixture(params=list(REGISTRY), ids=lambda entry: entry.dataset_id)
    def entry(self, request) -> DatasetConfig:
        return request.param

    def test_the_endpoint_is_https(self, entry: DatasetConfig) -> None:
        assert entry.source.endpoint.startswith("https://")

    def test_the_licence_is_identifiable(self, entry: DatasetConfig) -> None:
        assert entry.license.spdx_id or (entry.license.name and entry.license.url)

    def test_a_required_attribution_has_its_text(self, entry: DatasetConfig) -> None:
        if entry.license.attribution_required:
            assert entry.license.attribution_modified or entry.license.attribution_unmodified

    def test_the_grid_cap_fits_the_footprint(self, entry: DatasetConfig) -> None:
        assert entry.coverage.max_geotile_level <= max_geotile_level_for(entry.coverage.typical_footprint_km)

    def test_a_healthy_entry_says_when_it_was_checked(self, entry: DatasetConfig) -> None:
        if entry.health.status is HealthStatus.OK:
            assert entry.health.last_checked_ok is not None

    def test_the_id_is_the_one_it_is_filed_under(self, entry: DatasetConfig) -> None:
        assert REGISTRY.get(entry.dataset_id) is entry
