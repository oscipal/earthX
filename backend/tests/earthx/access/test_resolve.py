"""Access resolution in `access` (M4-01a, adr/0011 §6.4): pure, serialisable, and
importable by `processing` without a database or `gateway`.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from earthx.access.resolve import (
    AssetNotOnItem,
    InvalidAssetKey,
    MalformedItem,
    NoReader,
    ResolvedAsset,
    open_asset_ref,
    resolve_asset,
)
from earthx.catalog.datasets import COP_DEM_GLO_30, SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3
from earthx.catalog.registry import DataFormat, ZarrInfo
from earthx.gateway import Policy, UrlRejected
from earthx.readers import AssetRejected
from earthx.readers.cog import AssetPath
from earthx.readers.zarr_reader import ZarrAsset

HOST = "assets.example.invalid"
POLICY = Policy(allowed_hosts=frozenset({HOST}))
RESOLVE_PY = Path(__file__).resolve().parents[3] / "earthx" / "access" / "resolve.py"

COG = replace(SENTINEL_2_L2A, source=replace(SENTINEL_2_L2A.source, asset_hosts=(HOST,)))
ZARR_GROUPS = replace(SENTINEL_2_L2A_ZARR3, source=replace(SENTINEL_2_L2A_ZARR3.source, asset_hosts=(HOST,)))
ZARR_PLAIN = replace(ZARR_GROUPS, zarr=ZarrInfo(variable_separator=None, multiscales_convention="test"))
DEM = replace(COP_DEM_GLO_30, source=replace(COP_DEM_GLO_30.source, asset_hosts=(HOST,)))

COG_ITEM: dict[str, Any] = {
    "id": "S2B_32TMT_20260101_0_L2A",
    "properties": {"proj:epsg": 32632},
    "assets": {"visual": {"href": f"https://{HOST}/s2/TCI.tif"}},
}
ZARR_ITEM: dict[str, Any] = {
    "id": "S2B_MSIL2A_20260101T100000",
    "properties": {"proj:code": "EPSG:32632"},
    "assets": {
        "SR_10m": {"href": f"https://{HOST}/p/product.zarr/measurements/reflectance/r10m"},
        "tci": {"href": f"https://{HOST}/p/product.zarr/quality/r10m/tci"},
    },
}
# The shape `adapters/cop_dem_bucket.py` materializes: one `data` asset, no time.
DEM_ITEM: dict[str, Any] = {
    "id": "Copernicus_DSM_COG_10_N00_00_E000_00_DEM",
    "properties": {"datetime": None, "proj:code": "EPSG:4326"},
    "assets": {"data": {"href": f"https://{HOST}/Copernicus_DSM_COG_10_N00_00_E000_00_DEM.tif"}},
}


def public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


class TestResolveAsset:
    def test_a_cog_asset(self) -> None:
        assert resolve_asset(COG_ITEM, COG, "visual") == ResolvedAsset(
            dataset_id=COG.dataset_id,
            item_id=COG_ITEM["id"],
            asset="visual",
            reader="cog",
            href=f"https://{HOST}/s2/TCI.tif",
            variable=None,
            crs="EPSG:32632",
        )

    def test_a_zarr_key_is_split_at_the_registrys_separator(self) -> None:
        ref = resolve_asset(ZARR_ITEM, ZARR_GROUPS, "SR_10m:b04")
        assert (ref.reader, ref.asset, ref.variable) == ("zarr", "SR_10m:b04", "b04")
        assert ref.href == ZARR_ITEM["assets"]["SR_10m"]["href"]
        assert ref.crs == "EPSG:32632"

    def test_a_zarr_key_without_a_separator_is_the_items_own_key(self) -> None:
        ref = resolve_asset(ZARR_ITEM, ZARR_PLAIN, "tci")
        assert (ref.reader, ref.variable, ref.href) == ("zarr", None, ZARR_ITEM["assets"]["tci"]["href"])

    def test_a_materialized_item(self) -> None:
        ref = resolve_asset(DEM_ITEM, DEM, "data")
        assert (ref.dataset_id, ref.reader, ref.crs) == (COP_DEM_GLO_30.dataset_id, "cog", "EPSG:4326")

    def test_an_item_without_a_crs_resolves_with_none(self) -> None:
        assert resolve_asset({**COG_ITEM, "properties": {}}, COG, "visual").crs is None

    def test_a_format_without_a_reader_is_refused_before_anything_else(self) -> None:
        legacy = replace(COG, format=DataFormat.LEGACY)
        with pytest.raises(NoReader, match="no reader"):
            resolve_asset({}, legacy, "visual")

    @pytest.mark.parametrize("key", ["SR_10m", "SR_10m:", ":b04"])
    def test_a_zarr_key_without_a_variable_is_the_callers_mistake(self, key: str) -> None:
        with pytest.raises(InvalidAssetKey):
            resolve_asset(ZARR_ITEM, ZARR_GROUPS, key)

    def test_the_key_is_checked_before_the_item(self) -> None:
        with pytest.raises(InvalidAssetKey):
            resolve_asset({}, ZARR_GROUPS, "SR_10m")

    @pytest.mark.parametrize(
        "item",
        [
            {**COG_ITEM, "assets": {}},
            {**COG_ITEM, "assets": None},
            {**COG_ITEM, "assets": ["visual"]},
            {**COG_ITEM, "assets": {"visual": "https://elsewhere"}},
            {**COG_ITEM, "assets": {"visual": {"href": 42}}},
            {**COG_ITEM, "assets": {"visual": {"href": ""}}},
        ],
    )
    def test_an_asset_the_item_does_not_carry(self, item: dict[str, Any]) -> None:
        with pytest.raises(AssetNotOnItem, match="'visual'"):
            resolve_asset(item, COG, "visual")

    @pytest.mark.parametrize("item_id", [None, "", 7])
    def test_an_item_without_an_id(self, item_id: object) -> None:
        with pytest.raises(MalformedItem):
            resolve_asset({**COG_ITEM, "id": item_id}, COG, "visual")

    def test_a_foreign_host_is_not_judged_here(self) -> None:
        """Only ``check_url`` at opening decides about an address, with DNS."""
        item = {**COG_ITEM, "assets": {"visual": {"href": "https://elsewhere.example.invalid/x.tif"}}}
        assert resolve_asset(item, COG, "visual").href == "https://elsewhere.example.invalid/x.tif"

    def test_nothing_is_fetched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def no_check(*args: object, **kwargs: object) -> None:
            raise AssertionError("resolve_asset must not check or fetch")

        monkeypatch.setattr("earthx.readers.cog.check_url", no_check)
        monkeypatch.setattr("earthx.readers.zarr_reader.check_url", no_check)
        resolve_asset(COG_ITEM, COG, "visual")
        resolve_asset(ZARR_ITEM, ZARR_GROUPS, "SR_10m:b04")


class TestJsonRoundTrip:
    @pytest.mark.parametrize(
        ("item", "config", "key"),
        [(COG_ITEM, COG, "visual"), (ZARR_ITEM, ZARR_GROUPS, "SR_10m:b04"), (DEM_ITEM, DEM, "data")],
    )
    def test_there_and_back(self, item: dict[str, Any], config: Any, key: str) -> None:
        ref = resolve_asset(item, config, key)
        assert ResolvedAsset.from_json(json.loads(json.dumps(ref.to_json()))) == ref

    def good(self) -> dict[str, Any]:
        return resolve_asset(ZARR_ITEM, ZARR_GROUPS, "SR_10m:b04").to_json()

    def test_an_unknown_field_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown"):
            ResolvedAsset.from_json({**self.good(), "policy": "allow-all"})

    @pytest.mark.parametrize("field", ["dataset_id", "item_id", "asset", "reader", "href", "variable", "crs"])
    def test_every_field_is_required(self, field: str) -> None:
        data = self.good()
        del data[field]
        with pytest.raises(ValueError, match="missing"):
            ResolvedAsset.from_json(data)

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("dataset_id", ""),
            ("item_id", 42),
            ("asset", None),
            ("href", ["https://x"]),
            ("reader", "gdal"),
            ("reader", None),
            ("variable", ""),
            ("variable", 4),
            ("crs", 32632),
        ],
    )
    def test_a_wrong_value_is_refused(self, field: str, value: object) -> None:
        with pytest.raises(ValueError):
            ResolvedAsset.from_json({**self.good(), field: value})

    def test_a_cog_carries_no_variable(self) -> None:
        data = resolve_asset(COG_ITEM, COG, "visual").to_json()
        with pytest.raises(ValueError, match="Zarr"):
            ResolvedAsset.from_json({**data, "variable": "b04"})

    @pytest.mark.parametrize("data", [None, [], "{}", 1])
    def test_not_an_object(self, data: object) -> None:
        with pytest.raises(ValueError):
            ResolvedAsset.from_json(data)  # type: ignore[arg-type]


class TestOpenAssetRef:
    def test_a_cog_opens_as_an_asset_path(self) -> None:
        opened = open_asset_ref(resolve_asset(COG_ITEM, COG, "visual"), POLICY, public)
        assert isinstance(opened, AssetPath)
        assert opened == f"/vsicurl/https://{HOST}/s2/TCI.tif"
        assert (opened.dataset_id, opened.item_id, opened.asset) == (COG.dataset_id, COG_ITEM["id"], "visual")

    def test_a_zarr_asset_opens_with_group_variable_crs_and_level(self) -> None:
        opened = open_asset_ref(resolve_asset(ZARR_ITEM, ZARR_GROUPS, "SR_10m:b04"), POLICY, public, target_gsd=60.0)
        assert isinstance(opened, ZarrAsset)
        assert opened.store_url == f"https://{HOST}/p/product.zarr"
        assert (opened.group, opened.variable, opened.crs) == ("measurements/reflectance/r10m", "b04", "EPSG:32632")
        assert (opened.asset, opened.target_gsd) == ("SR_10m:b04", 60.0)

    def test_a_ref_from_json_opens_the_same(self) -> None:
        ref = resolve_asset(ZARR_ITEM, ZARR_GROUPS, "SR_10m:b04")
        again = ResolvedAsset.from_json(json.loads(json.dumps(ref.to_json())))
        assert open_asset_ref(again, POLICY, public) == open_asset_ref(ref, POLICY, public)

    @pytest.mark.parametrize(("item", "config", "key"), [(COG_ITEM, COG, "visual"), (ZARR_ITEM, ZARR_GROUPS, "SR_10m:b04")])
    def test_a_foreign_host_is_asset_rejected(self, item: dict[str, Any], config: Any, key: str) -> None:
        ref = resolve_asset(item, config, key)
        with pytest.raises(AssetRejected) as caught:
            open_asset_ref(ref, Policy(allowed_hosts=frozenset({"elsewhere.example.invalid"})), public)
        assert isinstance(caught.value, UrlRejected)

    def test_a_hand_written_ref_cannot_skip_the_check(self) -> None:
        """A recipe file is input from outside: its href still passes ``check_url``."""
        ref = ResolvedAsset.from_json(
            {
                "dataset_id": "d",
                "item_id": "i",
                "asset": "visual",
                "reader": "cog",
                "href": "https://169.254.169.254/latest/meta-data/",
                "variable": None,
                "crs": None,
            }
        )
        with pytest.raises(AssetRejected):
            open_asset_ref(ref, POLICY, public)


class TestImportsForProcessing:
    """`processing` will import this module; the chain rule of `.importlinter`
    (``no-database-in-worker-core``) counts what it reaches."""

    def test_the_module_imports_no_gateway_and_only_the_registry_from_catalog(self) -> None:
        tree = ast.parse(RESOLVE_PY.read_text())
        imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        imported |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        assert not {name for name in imported if name.startswith("earthx.gateway")}
        assert {name for name in imported if name.startswith("earthx.catalog")} == {"earthx.catalog.registry"}

    def test_importing_it_reaches_no_database(self) -> None:
        probe = (
            "import sys, earthx.access.resolve; "
            "print(sorted(m for m in sys.modules if m.split('.')[0] == 'psycopg' "
            "or m in ('earthx.catalog.datasets', 'earthx.catalog.pgstac', 'earthx.catalog.search_cache', 'earthx.api')))"
        )
        backend = RESOLVE_PY.parents[2]
        result = subprocess.run(
            [sys.executable, "-c", probe], cwd=backend, capture_output=True, text=True, check=True, timeout=120
        )
        assert result.stdout.strip() == "[]"
