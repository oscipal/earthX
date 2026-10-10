"""Every registry entry's items: an asset with band names also carries the core field ``bands`` (M4-23).

One synthetic item per dataset, taken through the adapter path that item would take
(the EOPF normaliser, the Earth Search pass-through, the DEM item builder). A new
registry entry fails ``test_every_registry_entry_is_covered`` until it is added here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import httpx
import pytest

from earthx.adapters.cop_dem_bucket import _item as dem_item
from earthx.adapters.earth_search import get_item as earth_search_item
from earthx.adapters.eopf_stac import normalize_item
from earthx.catalog.datasets import COP_DEM_GLO_30, REGISTRY, SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3

from .conftest import answering, load

pytestmark = pytest.mark.anyio


def assets_missing_bands(item: Mapping[str, Any]) -> list[str]:
    """The assets that name bands (``eo:bands``) but do not carry ``bands``."""
    return [
        key
        for key, asset in item["assets"].items()
        if isinstance(asset, Mapping) and asset.get("eo:bands") and not asset.get("bands")
    ]


def eopf_item() -> dict[str, Any]:
    assets = {
        "SR_10m": {
            "href": "https://data.eodc.eu/synth/1.zarr/measurements/reflectance/r10m",
            "bands": [{"name": "b04", "eo:common_name": "red"}, {"name": "b08", "eo:common_name": "nir"}],
        },
        "SR_20m": {"href": "https://data.eodc.eu/synth/1.zarr/measurements/reflectance/r20m", "bands": [{"name": "b05"}]},
        "product_metadata": {"href": "https://data.eodc.eu/synth/1.zarr/product"},
    }
    return normalize_item({"type": "Feature", "id": "SYNTH_A", "stac_version": "1.1.0", "assets": assets})


async def earth_search_fixture() -> dict[str, Any]:
    gateway, _ = answering(httpx.Response(200, json=load("item")))
    async with gateway:
        return await earth_search_item(SENTINEL_2_L2A, "SYNTH_T00AAA_20240601T100000_L2A", gateway=gateway)


def dem_fixture() -> dict[str, Any]:
    config = replace(COP_DEM_GLO_30, source=replace(COP_DEM_GLO_30.source, endpoint="https://dem.example"))
    return dem_item("Copernicus_DSM_10_N47_00_E009_00_DEM", (9.0, 47.0, 10.0, 48.0), config=config)


async def items_by_dataset() -> dict[str, dict[str, Any]]:
    return {
        SENTINEL_2_L2A.dataset_id: await earth_search_fixture(),
        SENTINEL_2_L2A_ZARR3.dataset_id: eopf_item(),
        COP_DEM_GLO_30.dataset_id: dem_fixture(),
    }


def test_every_registry_entry_is_covered() -> None:
    covered = {SENTINEL_2_L2A.dataset_id, SENTINEL_2_L2A_ZARR3.dataset_id, COP_DEM_GLO_30.dataset_id}
    assert {entry.dataset_id for entry in REGISTRY} == covered


async def test_every_asset_with_bands_carries_the_core_field() -> None:
    for dataset_id, item in (await items_by_dataset()).items():
        assert assets_missing_bands(item) == [], dataset_id


async def test_the_zarr_item_does_name_its_bands_so_the_check_is_not_vacuous() -> None:
    item = (await items_by_dataset())[SENTINEL_2_L2A_ZARR3.dataset_id]
    assert [band["name"] for band in item["assets"]["SR_10m"]["bands"]] == ["b04", "b08"]
    assert "bands" not in item["assets"]["product_metadata"]


def test_the_check_notices_an_asset_that_lost_its_bands() -> None:
    item = eopf_item()
    del item["assets"]["SR_10m"]["bands"]
    assert assets_missing_bands(item) == ["SR_10m"]
    item["assets"]["SR_20m"]["bands"] = []
    assert assets_missing_bands(item) == ["SR_10m", "SR_20m"]
