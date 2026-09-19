"""What a registry entry must not get away with.

The rules under test are decisions from docs/, not preferences: KLAERUNGEN B10
(every capability set deliberately), B11 (licence tier), adr/0004 §5 (the grid cap
and one-off products) and adr/0005 rule I (an unknown dataset is an error, not an
empty result).
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from earthx.catalog.datasets import REGISTRY, SENTINEL_2_L2A
from earthx.catalog.registry import (
    Capabilities,
    ConfigError,
    CoverageProvider,
    DatasetRegistry,
    LicenseTier,
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

    def test_a_sentinel_2_footprint_caps_the_grid_at_z8(self) -> None:
        """The number adr/0004 §5 names, derived rather than copied."""
        assert max_geotile_level_for(110.0) == 8


class TestLookup:
    """adr/0005 rule I: an unknown collection is a 404, never an empty result."""

    def test_unknown_dataset_raises_its_own_error(self) -> None:
        with pytest.raises(UnknownDatasetError, match="does-not-exist"):
            REGISTRY.get("does-not-exist")

    def test_known_dataset_is_returned(self) -> None:
        assert REGISTRY.get("sentinel-2-l2a") is SENTINEL_2_L2A

    def test_a_duplicate_id_is_rejected(self) -> None:
        with pytest.raises(ConfigError, match="duplicate"):
            DatasetRegistry((SENTINEL_2_L2A, SENTINEL_2_L2A))

    def test_membership_and_length(self) -> None:
        assert "sentinel-2-l2a" in REGISTRY
        assert "does-not-exist" not in REGISTRY
        assert len(REGISTRY) == len(list(REGISTRY))
