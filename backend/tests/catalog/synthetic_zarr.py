"""A registry entry in Zarr that names no real source, for every test that needs one.

The registry has no Zarr dataset since adr/0017: the Zarr reader, the CF scaling, the group-and-variable
asset keys and the tolerance of adr/0014 §15d stay, and are tested on this entry and the synthetic stores
of `tests/earthx/readers`. Everything real about the dataset is the platform's own: its fields are those
a Zarr entry has to carry (``ZarrInfo``, a ``mask`` with a variable, ``band_units`` with a group pattern,
a viewer with the released zooms of a tile path). Everything of a source is invented: the id, the
reserved host of the synthetic stores, an endpoint that does not resolve.

``TEST_ENTRIES`` is what a test that runs "for every entry" iterates: the registry's and this one. It is
never added to ``REGISTRY``; a guard test holds that apart.
"""

from __future__ import annotations

from dataclasses import replace

from earthx.catalog.datasets import REGISTRY, SENTINEL_2_L2A
from earthx.catalog.registry import (
    BrowseMode,
    DataFormat,
    DatasetConfig,
    DatasetRegistry,
    MaskSource,
    ViewerInfo,
    ZarrInfo,
)
from tests.earthx.readers import mini_zarr

DATASET_ID = "synthetic-zarr"


def without_cloud_share(entry: DatasetConfig) -> DatasetConfig:
    """``entry`` with no cloud classes and no filter within the AOI (DS-03 plan §6.19).

    A test that makes a Zarr, legacy or mask-less entry out of Sentinel-2's needs this: the share is offered only
    for a COG with cloud classes, and the registry refuses the other combinations at the start.
    """
    return replace(
        entry,
        mask=replace(entry.mask, cloud_classes=frozenset(), cloud_note=""),
        search_filters=tuple(replace(item, within_aoi=False) for item in entry.search_filters),
    )


SYNTHETIC_ZARR: DatasetConfig = replace(
    SENTINEL_2_L2A,
    dataset_id=DATASET_ID,
    title="Synthetic Zarr dataset",
    description="A Zarr entry for tests; it names no source.",
    doi=None,
    format=DataFormat.ZARR,
    source=replace(
        SENTINEL_2_L2A.source,
        endpoint="https://stac.example.invalid",
        source_collection_id=DATASET_ID,
        asset_hosts=(mini_zarr.HOST,),
    ),
    # True colour from one group, the variables composed in the order named: the key a tile URL carries.
    default_render=replace(
        SENTINEL_2_L2A.default_render,
        title="True colour",
        assets=("SR_10m:b04,b03,b02",),
        rescale=((0.0, 0.30), (0.0, 0.30), (0.0, 0.30)),
    ),
    viewer=ViewerInfo(
        group_by=("datetime", "grid:code"),
        min_zoom=8,
        max_zoom=14,
        browse=BrowseMode.PREVIEW_TILES,
        quicklook_nodata_max=None,
        results_group_by=("datetime", "grid:code"),
    ),
    zarr=ZarrInfo(variable_separator=":", multiscales_convention="zarr-conventions/multiscales v0.1 (pilot)"),
    mask=MaskSource(
        asset="SCL_20m:scl",
        band="scl",
        classes=SENTINEL_2_L2A.mask.classes,
        suggested=SENTINEL_2_L2A.mask.suggested,
        reference=SENTINEL_2_L2A.mask.reference,
        note=SENTINEL_2_L2A.mask.note,
        cloud_classes=frozenset(),
        cloud_note="",
    ),
    band_units={"SR_*": "1", "SCL_20m:scl": None},
    auxiliary_assets=(),
    # The Zarr layer has no cloud classes (DS-03 plan §6.19), so none of the inherited filters is "within AOI".
    search_filters=tuple(replace(entry, within_aoi=False) for entry in SENTINEL_2_L2A.search_filters),
)

TEST_ENTRIES: tuple[DatasetConfig, ...] = (*REGISTRY, SYNTHETIC_ZARR)


def registry_with_zarr() -> DatasetRegistry:
    """The platform's registry and the synthetic Zarr entry, retired datasets included."""
    return DatasetRegistry(TEST_ENTRIES, retired=tuple(REGISTRY.retired))
