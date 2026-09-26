"""A valid registry entry to vary from.

Every test below changes exactly one thing about it, so a failure names the rule
that was broken rather than the entry that was malformed.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from earthx.catalog.registry import (
    AccessInfo,
    AdapterKind,
    BrowseMode,
    Capabilities,
    CoverageInfo,
    CoverageProvider,
    DataClass,
    DataFormat,
    DatasetConfig,
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
)


@pytest.fixture
def valid_config() -> DatasetConfig:
    return DatasetConfig(
        dataset_id="test-dataset",
        title="Test dataset",
        description="Synthetic entry, used only by the tests.",
        doi="10.5555/test",
        citation="Test publisher (2026): Test dataset, version 1.",
        data_class=DataClass.RASTER_TIME_SERIES,
        format=DataFormat.COG,
        spatial_extent=SpatialExtent(bbox=(-10.0, -10.0, 10.0, 10.0)),
        temporal_extent=TemporalExtent(
            start=datetime(2020, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
        ),
        capabilities=Capabilities(
            roi=True,
            time_range=True,
            band_math=True,
            interpolation=True,
            ml_processing=False,
            quad_pol=False,
            single_coverage_product=False,
        ),
        license=LicenseInfo(
            spdx_id="CC-BY-4.0",
            name="Creative Commons Attribution 4.0",
            url="https://example.invalid/license",
            commercial_use=True,
            distribution=True,
            derivatives=True,
            share_alike=False,
            attribution_required=True,
            tier=LicenseTier.PROCESSING,
            attribution_modified="Contains modified test data {year}",
            attribution_unmodified="Test data {year}",
            terms=TermsOfUse(
                url="https://example.invalid/terms",
                notice={"en": "Terms: {terms_url}"},
            ),
        ),
        access=AccessInfo(
            token_free_checked_at=date(2026, 1, 1),
            method="anonymous HTTPS",
            cors=None,
        ),
        source=SourceInfo(
            adapter=AdapterKind.EARTH_SEARCH_V1,
            endpoint="https://example.invalid/v1",
            source_collection_id="test-collection",
            asset_hosts=("assets.example.invalid",),
            harvest_run=None,
            item_holding=ItemHolding.FEDERATED,
        ),
        coverage=CoverageInfo(
            provider=CoverageProvider.UPSTREAM_AGGREGATION,
            typical_footprint_km=110.0,
            max_geotile_level=8,
        ),
        default_render=DefaultRender(
            title="True colour",
            assets=("red", "green", "blue"),
            rescale=((0.0, 3000.0), (0.0, 3000.0), (0.0, 3000.0)),
            colormap_name=None,
            expression=None,
            resampling="nearest",
        ),
        viewer=ViewerInfo(
            group_by=("datetime",),
            min_zoom=0,
            max_zoom=19,
            # FULL_RESOLUTION needs no `access.cors=True` and no freistellung
            # threshold — the least constrained combination, so a test that
            # varies something unrelated to browse/grouping does not also
            # have to satisfy QUICKLOOK's cross-field rule.
            browse=BrowseMode.FULL_RESOLUTION,
            quicklook_nodata_max=None,
            results_group_by=("datetime",),
        ),
        health=HealthInfo(status=HealthStatus.OK),
        maturity=Maturity.STABLE,
        zarr=None,
    )


@pytest.fixture
def vary(valid_config: DatasetConfig):
    """Return the valid entry with one field group replaced."""

    def _vary(**changes: object) -> DatasetConfig:
        return replace(valid_config, **changes)

    return _vary
