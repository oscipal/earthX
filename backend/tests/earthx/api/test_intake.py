"""Order intake (M4-07b): an order becomes a recipe, or is turned away by name.

Everything is synthetic and offline. The items have the shape each source's item
has (measured in adr/0014 §3.1, §17.1, §17.10) on invented ids; the item source is a
function; the ``HEAD`` goes through a real ``Gateway`` over a mock transport, so the
``check_url`` road is the one that runs in production.
"""

from __future__ import annotations

import copy
import json
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, get_args

import httpx
import pytest

from earthx.access.download import compute_crop_region, parse_aoi_geometry, plan_outputs
from earthx.adapters.errors import UnknownCollection
from earthx.api.intake import (
    MAX_ORDER_ASSETS,
    MAX_ORDER_ITEMS,
    MAX_ORDER_STEPS,
    OrderRefused,
    accept_order,
    check_recipe_hosts,
    crop_recipe_json,
    estimate_order,
)
from earthx.api.item_source import MaterializedCatalogUnavailable, MaterializedItemNotFound, Stage, fetch_item_or_refuse
from earthx.catalog.datasets import REGISTRY
from earthx.catalog.registry import DatasetConfig, DatasetRegistry, LicenseTier
from earthx.gateway import Gateway, Policy, UpstreamError
from earthx.processing.operators import OperatorRegistry, Tier
from earthx.processing.plan import export_outputs
from earthx.processing.recipe import cache_key, recipe_from_data, recipe_hash
from tests.conftest import own_log_text
from tests.earthx.processing.testops import OPERATORS, SCALE

pytestmark = pytest.mark.anyio

S2 = REGISTRY.get("sentinel-2-c1-l2a")
EOPF = REGISTRY.get("sentinel-2-l2a-zarr3")
DEM = REGISTRY.get("cop-dem-glo-30")

S2_HOST = S2.source.asset_hosts[0]
EOPF_HOST = EOPF.source.asset_hosts[0]
DEM_HOST = DEM.source.asset_hosts[0]

#: A small synthetic square, inside the footprints below.
SQUARE = {
    "type": "Polygon",
    "coordinates": [[[9.0, 47.0], [9.01, 47.0], [9.01, 47.01], [9.0, 47.01], [9.0, 47.0]]],
}
RASTER = {"kind": "raster", "format": "cog", "dtype": "float32"}
SCALE_STEP = {"op": "scale", "op_version": 1, "params": {"factor": 2.0}}

# --- synthetic items ---------------------------------------------------------


def _footprint(bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    west, south, east, north = bbox
    return {
        "type": "Polygon",
        "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
    }


NEAR = (8.9, 46.9, 9.1, 47.1)
FAR = (20.0, 10.0, 20.2, 10.2)


def s2_item(item_id: str = "S2_A", bbox: tuple[float, float, float, float] = NEAR, **assets: Any) -> dict[str, Any]:
    """STAC 1.0 as Earth Search serves it: checksum and scaling on each asset."""

    def asset(name: str) -> dict[str, Any]:
        return {
            "href": f"https://{S2_HOST}/tiles/{item_id}/{name}.tif",
            "file:checksum": f"1220{item_id}{name}",
            "raster:bands": [
                {"nodata": 0, "data_type": "uint16", "scale": 0.0001, "offset": -0.1, "spatial_resolution": 10}
            ],
        }

    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": item_id,
        "bbox": list(bbox),
        "geometry": _footprint(bbox),
        "properties": {"datetime": "2026-06-01T10:00:00Z", "updated": "2026-06-02T00:00:00Z", "proj:epsg": 32632},
        "assets": {"red": asset("B04"), "nir": asset("B08"), **assets},
    }


def eopf_item(item_id: str = "EOPF_A", bbox: tuple[float, float, float, float] = NEAR) -> dict[str, Any]:
    """STAC 1.1 as the EOPF adapter normalises it: one unnamed ``raster:bands`` entry, no scaling, no checksum."""
    return {
        "type": "Feature",
        "stac_version": "1.1.0",
        "id": item_id,
        "bbox": list(bbox),
        "geometry": _footprint(bbox),
        "properties": {
            "datetime": "2026-06-01T10:00:00Z",
            "updated": "2026-06-03T00:00:00Z",
            "proj:code": "EPSG:32632",
        },
        "assets": {
            "SR_10m": {
                "href": f"https://{EOPF_HOST}/zarr/{item_id}/measurements/r10m",
                "gsd": 10,
                "raster:bands": [{"nodata": 0, "data_type": "uint16", "spatial_resolution": 10}],
                "eo:bands": [{"name": "b04"}, {"name": "b08"}],
            }
        },
    }


def dem_item(
    name: str = "DEM_N47_E009", bbox: tuple[float, float, float, float] = (9.0 - 0.5, 46.5, 9.5, 47.5)
) -> dict[str, Any]:
    """As ``cop_dem_bucket._item`` builds it: one ``data`` asset, no bands, no checksum, no ``updated``."""
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": name,
        "bbox": list(bbox),
        "geometry": _footprint(bbox),
        "properties": {"datetime": None, "gsd": 30.0, "proj:code": "EPSG:4326"},
        "assets": {"data": {"href": f"https://{DEM_HOST}/{name}/{name}.tif"}},
    }


# --- the surroundings of one intake -------------------------------------------


class Source:
    """The item source: items by (dataset, id); what it lacks is the source's own 404."""

    def __init__(self, *items: tuple[DatasetConfig, dict[str, Any]]) -> None:
        self.items = {(config.dataset_id, item["id"]): item for config, item in items}
        self.calls: list[tuple[str, str]] = []

    async def __call__(self, dataset: str, item_id: str) -> dict[str, Any]:
        self.calls.append((dataset, item_id))
        try:
            return copy.deepcopy(self.items[(dataset, item_id)])
        except KeyError:
            if REGISTRY.get(dataset).source.item_holding.value == "materialized":
                raise MaterializedItemNotFound(item_id) from None
            raise UpstreamError(404, "not found") from None


class Heads:
    """The ``HEAD`` side: answers by path, counts what was asked."""

    def __init__(self, answer: Callable[[httpx.Request], httpx.Response] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self._answer = answer or (lambda request: httpx.Response(200, headers={"ETag": f'"etag-{request.url.path}"'}))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._answer(request)


def gateway_for(heads: Heads) -> Gateway:
    async def no_wait(seconds: float) -> None:
        return None

    return Gateway(
        Policy(allowed_hosts=frozenset({S2_HOST, EOPF_HOST, DEM_HOST, "cdn.example.org"})),
        transport=httpx.MockTransport(heads),
        resolve=lambda host, port: ("93.184.216.34",),
        sleep=no_wait,
    )


def order(
    dataset: str = "sentinel-2-c1-l2a",
    groups: tuple[tuple[str, ...], ...] = (("S2_A",),),
    assets: tuple[str, ...] = ("red", "nir"),
    **override: Any,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "recipe_version": 1,
        "inputs": [{"name": "scene", "dataset": dataset, "groups": [list(g) for g in groups], "assets": list(assets)}],
        "aoi": SQUARE,
        "steps": [SCALE_STEP],
        "output": RASTER,
    }
    document.update(override)
    return document


async def accept(
    document: dict[str, Any] | str | bytes,
    source: Source,
    heads: Heads | None = None,
    *,
    registry: DatasetRegistry = REGISTRY,
    operators: OperatorRegistry = OPERATORS,
    aoi_provenance: dict[str, str] | None = None,
):
    raw = document if isinstance(document, (str, bytes)) else json.dumps(document)
    heads = heads or Heads()
    async with gateway_for(heads) as gateway:
        return await accept_order(
            raw,
            registry=registry,
            operators=operators,
            item_source=source,
            gateway=gateway,
            aoi_provenance=aoi_provenance,
        )


async def refused(
    document: dict[str, Any] | str | bytes, source: Source, heads: Heads | None = None, **kw: Any
) -> OrderRefused:
    with pytest.raises(OrderRefused) as error:
        await accept(document, source, heads, **kw)
    return error.value


# --- one dataset after the other -----------------------------------------------


class TestEarthSearchSentinel2:
    async def test_checksum_bands_scaling_and_gsd_come_off_the_item_without_a_request(self) -> None:
        heads = Heads()
        accepted = await accept(order(), Source((S2, s2_item())), heads)
        entry = accepted.recipe.inputs[0]
        assert [resolved.asset.asset for resolved in entry.resolved] == ["red", "nir"]
        red = entry.resolved[0]
        assert red.version is not None
        assert (red.version.kind, red.version.value) == ("file:checksum", "1220S2_AB04")
        assert (red.bands[0].scale, red.bands[0].offset, red.bands[0].nodata) == (0.0001, -0.1, 0.0)
        assert red.bands[0].data_type == "uint16"
        assert red.scaling == "item"
        assert red.gsd == 10.0
        assert red.asset.reader == "cog"
        assert red.asset.crs == "EPSG:32632"
        assert heads.requests == []
        assert accepted.cacheable
        assert accepted.skipped_items == ()

    async def test_the_recipe_runs_through_the_core_models_unchanged(self) -> None:
        accepted = await accept(order(), Source((S2, s2_item())))
        again = recipe_from_data(accepted.recipe.model_dump(mode="json"), OPERATORS)
        assert recipe_hash(again) == recipe_hash(accepted.recipe)
        assert cache_key(again) is not None

    async def test_an_item_without_a_scaling_is_read_as_it_is(self) -> None:
        item = s2_item()
        for asset in ("red", "nir"):
            item["assets"][asset]["raster:bands"] = [{"nodata": 0, "data_type": "uint16"}]
        accepted = await accept(order(), Source((S2, item)))
        assert {resolved.scaling for resolved in accepted.recipe.inputs[0].resolved} == {"none"}

    async def test_stac_11_band_fields_count_as_well(self) -> None:
        item = s2_item()
        item["assets"]["red"].pop("raster:bands")
        item["assets"]["red"]["bands"] = [
            {"name": "red", "raster:scale": 0.0001, "raster:offset": -0.1, "nodata": 0, "data_type": "uint16"}
        ]
        accepted = await accept(order(assets=("red",)), Source((S2, item)))
        band = accepted.recipe.inputs[0].resolved[0].bands[0]
        assert (band.scale, band.offset) == (0.0001, -0.1)
        assert accepted.recipe.inputs[0].resolved[0].scaling == "item"


class TestEopfZarr:
    KEY = "SR_10m:b04,b08"

    async def test_updated_is_the_version_and_the_store_decides_the_scaling(self) -> None:
        heads = Heads()
        accepted = await accept(
            order("sentinel-2-l2a-zarr3", (("EOPF_A",),), (self.KEY,)), Source((EOPF, eopf_item())), heads
        )
        resolved = accepted.recipe.inputs[0].resolved[0]
        assert resolved.version is not None
        assert (resolved.version.kind, resolved.version.value) == ("updated", "2026-06-03T00:00:00Z")
        assert resolved.scaling == "store-cf"
        assert (resolved.asset.reader, resolved.asset.variable) == ("zarr", "b04,b08")
        assert resolved.gsd == 10.0
        # One unnamed entry describes the whole asset and holds for each variable (F3).
        assert len(resolved.bands) == 2
        assert {(band.data_type, band.nodata) for band in resolved.bands} == {("uint16", 0.0)}
        assert heads.requests == [], "an ETag on a group of objects would not describe the data (F2)"
        assert accepted.cacheable

    async def test_named_band_entries_are_matched_by_name(self) -> None:
        item = eopf_item()
        item["assets"]["SR_10m"].pop("raster:bands")
        item["assets"]["SR_10m"]["bands"] = [
            {"name": "b04", "raster:scale": 0.0001, "raster:offset": -0.1, "data_type": "uint16", "nodata": 0},
            {"name": "b08", "raster:scale": 0.0002, "raster:offset": 0.0, "data_type": "uint16", "nodata": 0},
        ]
        accepted = await accept(
            order("sentinel-2-l2a-zarr3", (("EOPF_A",),), ("SR_10m:b08,b04",)), Source((EOPF, item))
        )
        resolved = accepted.recipe.inputs[0].resolved[0]
        assert [band.scale for band in resolved.bands] == [0.0002, 0.0001]
        assert resolved.scaling == "item"

    async def test_two_unnamed_entries_for_other_variables_describe_nothing(self) -> None:
        item = eopf_item()
        item["assets"]["SR_10m"]["raster:bands"] = [{"data_type": "uint16"}, {"data_type": "uint8"}]
        accepted = await accept(order("sentinel-2-l2a-zarr3", (("EOPF_A",),), (self.KEY,)), Source((EOPF, item)))
        resolved = accepted.recipe.inputs[0].resolved[0]
        assert [(band.data_type, band.scale) for band in resolved.bands] == [(None, None), (None, None)]
        assert resolved.scaling == "store-cf"

    async def test_a_group_key_without_a_variable_is_the_callers_mistake(self) -> None:
        error = await refused(order("sentinel-2-l2a-zarr3", (("EOPF_A",),), ("SR_10m",)), Source((EOPF, eopf_item())))
        assert error.status_code == 422


class TestCopernicusDem:
    TILES = (("DEM_N47_E009",), ("DEM_N47_E010",))

    def source(self) -> Source:
        return Source(
            (DEM, dem_item("DEM_N47_E009")),
            (DEM, dem_item("DEM_N47_E010", (9.5, 46.5, 10.5, 47.5))),
        )

    def order(self, tiles: tuple[tuple[str, ...], ...] = (("DEM_N47_E009",),), **kw: Any) -> dict[str, Any]:
        return order("cop-dem-glo-30", tiles, ("data",), **kw)

    async def test_the_etag_of_a_head_is_the_version_one_request_per_tile(self) -> None:
        heads = Heads()
        aoi = {
            "type": "Polygon",
            "coordinates": [[[9.4, 47.0], [9.6, 47.0], [9.6, 47.1], [9.4, 47.1], [9.4, 47.0]]],
        }
        accepted = await accept(self.order(self.TILES, aoi=aoi), self.source(), heads)
        resolved = accepted.recipe.inputs[0].resolved
        assert [entry.version.kind for entry in resolved if entry.version] == ["etag", "etag"]
        assert len(heads.requests) == 2
        assert {request.method for request in heads.requests} == {"HEAD"}
        assert resolved[0].bands == []
        assert resolved[0].scaling == "none"
        assert resolved[0].gsd == 30.0
        assert accepted.cacheable

    async def test_a_materialized_item_source_failing_is_named(self) -> None:
        async def down(dataset: str, item_id: str) -> dict[str, Any]:
            raise MaterializedCatalogUnavailable(dataset)

        error = await refused(self.order(), down)  # type: ignore[arg-type]
        assert error.status_code == 503

    @pytest.mark.parametrize(
        "answer",
        [
            httpx.Response(200),
            httpx.Response(200, headers={"ETag": 'W/"weak"'}),
            httpx.Response(200, headers={"ETag": '"' + "x" * 300 + '"'}),
        ],
        ids=["no etag", "weak etag", "etag over 256 characters"],
    )
    async def test_an_answer_without_a_usable_etag_leaves_the_version_empty(self, answer: httpx.Response) -> None:
        accepted = await accept(self.order(), self.source(), Heads(lambda request: answer))
        assert accepted.recipe.inputs[0].resolved[0].version is None
        assert not accepted.cacheable

    @pytest.mark.parametrize("status", [404, 410])
    async def test_an_input_the_source_no_longer_has_refuses_the_order(self, status: int) -> None:
        error = await refused(self.order(), self.source(), Heads(lambda request: httpx.Response(status)))
        assert error.status_code == 502
        assert "DEM_N47_E009" in error.detail
        assert "https://" not in error.detail

    @pytest.mark.parametrize("status", [403, 405, 503])
    async def test_any_other_failure_goes_on_without_a_version_and_warns_without_the_address(
        self, status: int, caplog: pytest.LogCaptureFixture
    ) -> None:
        heads = Heads(lambda request: httpx.Response(status))
        with caplog.at_level(logging.INFO):
            accepted = await accept(self.order(), self.source(), heads)
        assert accepted.recipe.inputs[0].resolved[0].version is None
        assert not accepted.cacheable
        warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert warnings[0].order_error == "UpstreamError"  # type: ignore[attr-defined]
        assert warnings[0].order_item == "DEM_N47_E009"  # type: ignore[attr-defined]
        assert "https://" not in own_log_text(warnings[0])

    async def test_a_head_that_times_out_goes_on_without_a_version(self, caplog: pytest.LogCaptureFixture) -> None:
        def slow(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("too slow")

        with caplog.at_level(logging.WARNING):
            accepted = await accept(self.order(), self.source(), Heads(slow))
        assert accepted.recipe.inputs[0].resolved[0].version is None
        assert [record.order_error for record in caplog.records if record.levelno == logging.WARNING] == [  # type: ignore[attr-defined]
            "UpstreamTimeout"
        ]

    async def test_a_head_redirected_off_the_allowlist_goes_on_without_a_version(self) -> None:
        heads = Heads(lambda request: httpx.Response(302, headers={"location": "https://evil.example/x.tif"}))
        accepted = await accept(self.order(), self.source(), heads)
        assert accepted.recipe.inputs[0].resolved[0].version is None
        assert len(heads.requests) == 1

    async def test_the_etag_comes_before_updated_where_a_cog_has_both(self) -> None:
        item = dem_item()
        item["properties"]["updated"] = "2026-06-02T00:00:00Z"
        accepted = await accept(
            self.order(), Source((DEM, item)), Heads(lambda r: httpx.Response(200, headers={"ETag": '"e"'}))
        )
        assert accepted.recipe.inputs[0].resolved[0].version.kind == "etag"  # type: ignore[union-attr]

    async def test_a_failed_head_does_not_fall_back_to_updated(self) -> None:
        """Otto, M4-07b F6: an empty version, not a different kind of version."""
        item = dem_item()
        item["properties"]["updated"] = "2026-06-02T00:00:00Z"
        accepted = await accept(self.order(), Source((DEM, item)), Heads(lambda r: httpx.Response(403)))
        assert accepted.recipe.inputs[0].resolved[0].version is None

    async def test_a_head_redirected_to_another_datasets_host_goes_on_without_a_version(self) -> None:
        """The host is on the process's list (it serves Sentinel-2), but not on this dataset's."""
        heads = Heads(lambda request: httpx.Response(302, headers={"location": f"https://{S2_HOST}/x.tif"}))
        accepted = await accept(self.order(), self.source(), heads)
        assert accepted.recipe.inputs[0].resolved[0].version is None
        assert len(heads.requests) == 1, "the redirect was not followed"

    async def test_a_checksum_spares_the_head(self) -> None:
        item = dem_item()
        item["assets"]["data"]["file:checksum"] = "1220abc"
        heads = Heads()
        accepted = await accept(self.order(), Source((DEM, item)), heads)
        assert heads.requests == []
        assert accepted.recipe.inputs[0].resolved[0].version.kind == "file:checksum"  # type: ignore[union-attr]


# --- the host check (adr/0014 §8) ------------------------------------------------


class TestHosts:
    @pytest.mark.parametrize(
        "href",
        [
            f"https://{EOPF_HOST}/tiles/x/B04.tif",  # another dataset's host
            f"https://evil-{S2_HOST}/tiles/x/B04.tif",  # a name that merely ends alike
            f"https://{S2_HOST}.evil.example/tiles/x/B04.tif",
            f"http://{S2_HOST}/tiles/x/B04.tif",
            f"https://{S2_HOST}:8443/tiles/x/B04.tif",
            f"https://user:secret@{S2_HOST}/tiles/x/B04.tif",
            "https://127.0.0.1/x.tif",
            "file:///etc/passwd",
        ],
    )
    async def test_an_item_pointing_outside_its_datasets_hosts_is_not_passed_on(self, href: str) -> None:
        item = s2_item()
        item["assets"]["red"]["href"] = href
        heads = Heads()
        error = await refused(order(), Source((S2, item)), heads)
        assert error.status_code == 502
        assert "asset_hosts" in error.detail
        assert href not in error.detail
        assert heads.requests == []

    async def test_an_address_over_the_length_limit_is_refused_not_a_crash(self) -> None:
        item = s2_item()
        item["assets"]["red"]["href"] = f"https://{S2_HOST}/" + "a" * 9000
        error = await refused(order(assets=("red",)), Source((S2, item)))
        assert error.status_code == 502

    async def test_a_recipe_address_over_the_limit_in_bytes_is_refused_not_a_crash(self) -> None:
        accepted = await accept(order(assets=("red",)), Source((S2, s2_item())))
        data = accepted.recipe.model_dump(mode="json")
        # Under 8192 characters, over 8192 bytes: the model lets it by, the policy does not.
        data["inputs"][0]["resolved"][0]["asset"]["href"] = f"https://{S2_HOST}/" + "ä" * 4200
        forged = recipe_from_data(data, OPERATORS)
        with pytest.raises(OrderRefused) as error:
            check_recipe_hosts(forged, REGISTRY)
        assert error.value.status_code == 400

    async def test_a_real_subdomain_of_a_declared_host_is_a_declared_host(self) -> None:
        item = s2_item()
        item["assets"]["red"]["href"] = f"https://mirror.{S2_HOST}/tiles/x/B04.tif"
        accepted = await accept(order(assets=("red",)), Source((S2, item)))
        assert accepted.recipe.inputs[0].resolved[0].asset.href.startswith("https://mirror.")

    async def test_a_recipe_with_a_foreign_address_is_refused_wherever_it_came_from(self) -> None:
        accepted = await accept(order(), Source((S2, s2_item())))
        check_recipe_hosts(accepted.recipe, REGISTRY)  # the honest one passes
        data = accepted.recipe.model_dump(mode="json")
        data["inputs"][0]["resolved"][1]["asset"]["href"] = "https://evil.example/B08.tif"
        forged = recipe_from_data(data, OPERATORS)
        with pytest.raises(OrderRefused) as error:
            check_recipe_hosts(forged, REGISTRY)
        assert error.value.status_code == 400
        assert "evil.example" not in error.value.detail

    async def test_a_recipe_for_a_dataset_the_registry_lacks_is_refused(self) -> None:
        accepted = await accept(order(), Source((S2, s2_item())))
        with pytest.raises(OrderRefused) as error:
            check_recipe_hosts(accepted.recipe, DatasetRegistry((EOPF,)))
        assert error.value.status_code == 400

    @pytest.mark.parametrize("key", ["resolved", "recipe_id"])
    async def test_a_recipe_is_not_an_order(self, key: str) -> None:
        accepted = await accept(order(), Source((S2, s2_item())))
        document = accepted.recipe.model_dump(mode="json")
        if key == "resolved":
            document.pop("recipe_id")
        source = Source((S2, s2_item()))
        error = await refused(document, source)
        assert error.status_code == 400
        assert "without addresses" in error.detail
        assert source.calls == []


# --- turned away by name ---------------------------------------------------------


class TestRefusals:
    @pytest.fixture
    def source(self) -> Source:
        return Source((S2, s2_item()))

    @pytest.mark.parametrize(
        ("raw", "needle"),
        [
            ("not json", "not a JSON document"),
            ("[]", "invalid order"),
            ('{"recipe_version": 1, "recipe_version": 1}', "duplicate key"),
            ('{"recipe_version": NaN}', "I-JSON"),
        ],
    )
    async def test_something_that_is_not_an_order(self, source: Source, raw: str, needle: str) -> None:
        error = await refused(raw, source)
        assert error.status_code == 422
        assert needle in error.detail
        assert source.calls == []

    async def test_an_unknown_field_a_wrong_version_or_a_string_for_a_number(self, source: Source) -> None:
        for broken in (
            order(extra="x"),
            order(recipe_version=2),
            order(steps=[{"op": "scale", "op_version": 1, "params": {"factor": "2"}}]),
            order(aoi={"type": "Point", "coordinates": [9.0, 47.0]}),
        ):
            assert (await refused(broken, source)).status_code == 422
        assert source.calls == []

    async def test_a_self_intersecting_aoi_is_refused_before_anything_is_fetched(self, source: Source) -> None:
        bowtie = {
            "type": "Polygon",
            "coordinates": [[[9.0, 47.0], [9.01, 47.01], [9.01, 47.0], [9.0, 47.01], [9.0, 47.0]]],
        }
        error = await refused(order(aoi=bowtie), source)
        assert error.status_code == 422
        assert source.calls == []

    async def test_an_unknown_dataset(self, source: Source) -> None:
        error = await refused(order("no-such-dataset"), source)
        assert error.status_code == 422
        assert "no-such-dataset" in error.detail
        assert source.calls == []

    @pytest.mark.parametrize(
        "step",
        [
            {"op": "no_such_operator", "op_version": 1, "params": {}},
            {"op": "scale", "op_version": 9, "params": {"factor": 2.0}},
        ],
    )
    async def test_an_operator_or_version_this_platform_does_not_run(
        self, source: Source, step: dict[str, Any]
    ) -> None:
        error = await refused(order(steps=[step]), source)
        assert error.status_code == 422
        assert source.calls == []

    async def test_an_operator_the_dataset_does_not_allow(self) -> None:
        no_math = replace(S2, capabilities=replace(S2.capabilities, band_math=False))
        source = Source((S2, s2_item()))
        error = await refused(order(), source, registry=DatasetRegistry((no_math,)))
        assert error.status_code == 422
        assert "band_math" in error.detail
        assert source.calls == [], "a refusal that needs no item costs no request to the source"

    async def test_a_licence_below_processing(self) -> None:
        display = replace(S2, license=replace(S2.license, tier=LicenseTier.DISPLAY))
        source = Source((S2, s2_item()))
        error = await refused(order(), source, registry=DatasetRegistry((display,)))
        assert error.status_code == 403
        assert source.calls == []

    async def test_a_band_the_inputs_do_not_have_is_refused_naming_the_bands_before_any_job(
        self, source: Source
    ) -> None:
        step = {"op": "band_math", "op_version": 1, "params": {"expression": "(swir - red) / (swir + red)"}}
        error = await refused(order(steps=[step]), source)
        assert (error.status_code, error.stage) == (422, "applicable")
        assert "swir" in error.detail and "red, nir" in error.detail

    async def test_an_expression_outside_r5_is_refused_with_the_reason(self, source: Source) -> None:
        step = {"op": "band_math", "op_version": 1, "params": {"expression": "log(red)"}}
        error = await refused(order(steps=[step]), source)
        # The order layer names the field and the kind of error, never the text (adr/0014 §4.7).
        assert error.status_code == 422 and "step 0 (band_math)" in error.detail and "expression" in error.detail
        assert "log" not in error.detail

    async def test_band_math_over_the_bands_of_the_order_is_accepted(self, source: Source) -> None:
        step = {"op": "band_math", "op_version": 1, "params": {"expression": "(nir - red) / (nir + red)"}}
        accepted = await accept(order(steps=[step]), source)
        assert [s.op for s in accepted.recipe.steps] == ["band_math"]

    async def test_where_the_item_does_not_count_the_bands_the_name_check_waits_for_the_file(self) -> None:
        """The DEM item describes no bands: a COG may hold several, so the core checks when it has the file."""
        step = {"op": "band_math", "op_version": 1, "params": {"expression": "data_2 - data_1"}}
        source = Source((DEM, dem_item("DEM_N47_E009")))
        accepted = await accept(order("cop-dem-glo-30", (("DEM_N47_E009",),), ("data",), steps=[step]), source)
        assert accepted.recipe.steps[0].op == "band_math"

    async def test_an_operator_that_only_runs_as_a_tile_is_no_job(self, source: Source) -> None:
        tile_only = replace(SCALE, op="tile_only", tiers=frozenset({Tier.T1}))
        error = await refused(
            order(steps=[{"op": "tile_only", "op_version": 1, "params": {"factor": 2.0}}]),
            source,
            operators=OPERATORS.with_operators(tile_only),
        )
        assert error.status_code == 422
        assert "does not run as a job" in error.detail

    async def test_two_inputs(self, source: Source) -> None:
        document = order()
        document["inputs"].append({**document["inputs"][0], "name": "second"})
        assert (await refused(document, source)).status_code == 422

    async def test_the_caps_are_judged_before_the_network(self, source: Source) -> None:
        too_many_items = order(groups=tuple((f"S2_{i}",) for i in range(MAX_ORDER_ITEMS + 1)))
        error = await refused(too_many_items, source)
        assert error.status_code == 413
        too_many_assets = order(assets=tuple(f"a{i}" for i in range(MAX_ORDER_ASSETS + 1)))
        assert (await refused(too_many_assets, source)).status_code == 422
        too_many_steps = order(steps=[SCALE_STEP] * (MAX_ORDER_STEPS + 1))
        assert (await refused(too_many_steps, source)).status_code == 422
        assert source.calls == []

    async def test_exactly_at_the_cap_is_fine(self) -> None:
        ids = [f"S2_{i}" for i in range(MAX_ORDER_ITEMS)]
        source = Source(*((S2, s2_item(item_id)) for item_id in ids))
        accepted = await accept(order(groups=tuple((i,) for i in ids)), source)
        assert len(accepted.recipe.inputs[0].resolved) == MAX_ORDER_ITEMS * 2

    async def test_an_item_the_source_does_not_have(self) -> None:
        error = await refused(order(), Source())
        assert error.status_code == 422
        assert "S2_A" in error.detail

    async def test_a_materialized_item_the_catalogue_does_not_have(self) -> None:
        error = await refused(order("cop-dem-glo-30", (("DEM_X",),), ("data",)), Source())
        assert error.status_code == 422

    async def test_the_first_missing_item_in_order_is_the_one_named(self) -> None:
        source = Source((S2, s2_item("S2_A")))
        error = await refused(order(groups=(("S2_A",), ("S2_B",), ("S2_C",))), source)
        assert "S2_B" in error.detail

    async def test_an_item_that_is_not_the_one_asked_for(self) -> None:
        source = Source((S2, s2_item("S2_OTHER")))
        source.items[("sentinel-2-c1-l2a", "S2_A")] = s2_item("S2_OTHER")
        error = await refused(order(), source)
        assert error.status_code == 502

    async def test_a_source_that_answers_wrongly_or_not_at_all(self) -> None:
        async def broken(dataset: str, item_id: str) -> dict[str, Any]:
            raise UpstreamError(500, "boom with ?bbox=9.0,47.0")

        error = await refused(order(), broken)  # type: ignore[arg-type]
        assert error.status_code == 502
        assert "bbox" not in error.detail

    async def test_an_asset_the_item_does_not_carry(self, source: Source) -> None:
        error = await refused(order(assets=("red", "swir")), source)
        assert error.status_code == 422
        assert "swir" in error.detail

    async def test_an_aoi_no_item_touches(self, source: Source) -> None:
        far = {
            "type": "Polygon",
            "coordinates": [[[100.0, 10.0], [100.1, 10.0], [100.1, 10.1], [100.0, 10.1], [100.0, 10.0]]],
        }
        error = await refused(order(aoi=far), source)
        assert error.status_code == 422
        assert "does not touch" in error.detail

    async def test_an_aoi_the_bbox_reaches_but_the_footprint_does_not(self) -> None:
        """A rotated scene: the bbox is a rectangle, the footprint a sliver (bug A of PR #86)."""
        item = s2_item()
        item["geometry"] = {
            "type": "Polygon",
            "coordinates": [[[8.9, 46.9], [8.95, 46.9], [8.9, 46.95], [8.9, 46.9]]],
        }
        error = await refused(order(), Source((S2, item)))
        assert error.status_code == 422

    @pytest.mark.parametrize(
        "band",
        [
            {"scale": "0.0001"},
            {"scale": float("inf")},
            {"offset": True},
            {"data_type": "uint17"},
            {"nodata": "not-a-number"},
        ],
    )
    async def test_an_item_whose_bands_are_not_described_correctly_is_the_sources_mistake(
        self, band: dict[str, Any]
    ) -> None:
        item = s2_item()
        item["assets"]["red"]["raster:bands"] = [{"data_type": "uint16", **band}]
        error = await refused(order(), Source((S2, item)))
        assert error.status_code == 502


class TestStages:
    """Every refusal names where it happened, as one of a fixed set, and the log line carries it."""

    @staticmethod
    async def _cases() -> dict[str, tuple[Any, ...]]:
        no_math = replace(S2, capabilities=replace(S2.capabilities, band_math=False))
        display = replace(S2, license=replace(S2.license, tier=LicenseTier.DISPLAY))
        foreign = s2_item()
        foreign["assets"]["red"]["href"] = f"https://{EOPF_HOST}/x.tif"
        odd_bands = s2_item()
        odd_bands["assets"]["red"]["raster:bands"] = {"scale": 2}
        long_crs = s2_item()
        long_crs["properties"]["proj:code"] = "EPSG:" + "9" * 300
        far = {
            "type": "Polygon",
            "coordinates": [[[100.0, 10.0], [100.1, 10.0], [100.1, 10.1], [100.0, 10.1], [100.0, 10.0]]],
        }
        good = Source((S2, s2_item()))
        return {
            "order": (order(recipe_version=2), good, {}),
            "size": (order(groups=tuple((f"S2_{i}",) for i in range(MAX_ORDER_ITEMS + 1))), good, {}),
            "dataset": (order("no-such-dataset"), good, {}),
            "license": (order(), good, {"registry": DatasetRegistry((display,))}),
            "applicable": (order(), good, {"registry": DatasetRegistry((no_math,))}),
            "items": (order(), Source(), {}),
            "aoi": (order(aoi=far), good, {}),
            "resolve": (order(assets=("swir",)), good, {}),
            "hosts": (order(assets=("red",)), Source((S2, foreign)), {}),
            "bands": (order(assets=("red",)), Source((S2, odd_bands)), {}),
            "recipe": (order(assets=("red",)), Source((S2, long_crs)), {}),
        }

    async def test_each_stage_is_named_by_the_refusal_and_by_the_log(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING, logger="httpx")
        cases = await self._cases()
        with caplog.at_level(logging.INFO, logger="earthx.api.intake"):
            for stage, (document, source, extra) in cases.items():
                error = await refused(document, source, **extra)
                assert error.stage == stage, error.detail
        logged = [record for record in caplog.records if record.getMessage() == "order refused"]
        assert [record.order_stage for record in logged] == list(cases)  # type: ignore[attr-defined]

    async def test_a_version_that_is_gone_names_its_stage(self) -> None:
        source = Source((DEM, dem_item()))
        error = await refused(
            order("cop-dem-glo-30", (("DEM_N47_E009",),), ("data",)), source, Heads(lambda r: httpx.Response(404))
        )
        assert error.stage == "version"

    async def test_the_stages_are_a_fixed_set_and_none_is_left_unproved(self) -> None:
        cases = await self._cases()
        assert set(get_args(Stage)) - set(cases) == {"version"}, "`version` is proved by the test above"
        assert len(set(get_args(Stage))) == len(get_args(Stage))

    async def test_the_log_line_carries_the_stage_and_nothing_of_the_order(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING, logger="httpx")
        far = {
            "type": "Polygon",
            "coordinates": [[[100.0, 10.0], [100.1, 10.0], [100.1, 10.1], [100.0, 10.1], [100.0, 10.0]]],
        }
        with caplog.at_level(logging.DEBUG):
            await refused(order(aoi=far), Source((S2, s2_item())))
        (record,) = [r for r in caplog.records if r.getMessage() == "order refused"]
        assert (record.order_stage, record.order_status) == ("aoi", 422)  # type: ignore[attr-defined]
        text = own_log_text(record)
        for forbidden in ("100.1", "https://", "c1:", "bbox", "?"):
            assert forbidden not in text, forbidden


class TestMalformedItems:
    """What an item says wrongly is the source's mistake: a 502 by name, never a crash and never a guess."""

    async def test_a_checksum_or_update_time_too_long_for_a_version(self) -> None:
        item = s2_item()
        item["assets"]["red"]["file:checksum"] = "x" * 300
        error = await refused(order(assets=("red",)), Source((S2, item)))
        assert error.status_code == 502
        eopf = eopf_item()
        eopf["properties"]["updated"] = "y" * 300
        error = await refused(order("sentinel-2-l2a-zarr3", (("EOPF_A",),), ("SR_10m:b04",)), Source((EOPF, eopf)))
        assert error.status_code == 502

    @pytest.mark.parametrize(
        "bands",
        [
            [None, {"data_type": "uint16", "scale": 0.5, "offset": 1.0}],
            {"scale": 2},
            "uint16",
            [[1, 2]],
        ],
        ids=["a null entry shifts the next", "an object for a list", "a string", "a list in a list"],
    )
    async def test_band_descriptions_that_are_not_a_list_of_objects(self, bands: Any) -> None:
        item = s2_item()
        item["assets"]["red"]["raster:bands"] = bands
        error = await refused(order(assets=("red",)), Source((S2, item)))
        assert error.status_code == 502
        assert "raster:bands" in error.detail

    async def test_two_bands_with_one_name(self) -> None:
        item = eopf_item()
        item["assets"]["SR_10m"].pop("raster:bands")
        item["assets"]["SR_10m"]["bands"] = [
            {"name": "b04", "raster:scale": 0.1},
            {"name": "b04", "raster:scale": 0.2},
        ]
        error = await refused(order("sentinel-2-l2a-zarr3", (("EOPF_A",),), ("SR_10m:b04",)), Source((EOPF, item)))
        assert error.status_code == 502
        assert "share a name" in error.detail

    async def test_a_bbox_that_is_not_four_numbers(self) -> None:
        item = s2_item()
        item["bbox"] = ["a", "b", "c", "d"]
        error = await refused(order(), Source((S2, item)))
        assert error.status_code == 502


class TestGroups:
    async def test_a_group_the_aoi_does_not_touch_is_left_out_and_named(self) -> None:
        source = Source((S2, s2_item("S2_A")), (S2, s2_item("S2_FAR", FAR)))
        accepted = await accept(order(groups=(("S2_A",), ("S2_FAR",))), source)
        assert accepted.recipe.inputs[0].groups == [["S2_A"]]
        assert accepted.skipped_items == ("S2_FAR",)
        assert {entry.asset.item_id for entry in accepted.recipe.inputs[0].resolved} == {"S2_A"}

    async def test_an_item_of_a_surviving_group_that_the_aoi_does_not_touch_is_left_out_too(self) -> None:
        source = Source((S2, s2_item("S2_A")), (S2, s2_item("S2_FAR", FAR)))
        accepted = await accept(order(groups=(("S2_A", "S2_FAR"),)), source)
        assert accepted.recipe.inputs[0].groups == [["S2_A"]]
        assert accepted.skipped_items == ("S2_FAR",)

    async def test_two_surviving_groups_keep_their_order(self) -> None:
        source = Source((S2, s2_item("S2_B")), (S2, s2_item("S2_A")))
        accepted = await accept(order(groups=(("S2_B",), ("S2_A",))), source)
        assert accepted.recipe.inputs[0].groups == [["S2_B"], ["S2_A"]]


class TestIdentifiers:
    async def test_every_order_gets_its_own_recipe_id_and_the_hash_does_not_see_it(self) -> None:
        source = Source((S2, s2_item()))
        first = await accept(order(), source)
        second = await accept(order(), source)
        assert len(first.recipe.recipe_id or "") == 22
        assert first.recipe.recipe_id != second.recipe.recipe_id
        assert recipe_hash(first.recipe) == recipe_hash(second.recipe)

    async def test_a_recipe_without_a_version_for_an_input_is_not_cacheable(self) -> None:
        item = eopf_item()
        item["properties"].pop("updated")
        accepted = await accept(order("sentinel-2-l2a-zarr3", (("EOPF_A",),), ("SR_10m:b04",)), Source((EOPF, item)))
        assert accepted.recipe.inputs[0].resolved[0].version is None
        assert not accepted.cacheable


class TestLogs:
    async def test_nothing_in_any_log_names_an_aoi_an_address_or_a_hash(self, caplog: pytest.LogCaptureFixture) -> None:
        source = Source((DEM, dem_item()), (S2, s2_item()))
        # As in production: `configure_logging` keeps the libraries that log a full URL
        # (httpx among them) at WARNING (earthx/logging.py, `_URL_LOGGING_LIBRARIES`).
        caplog.set_level(logging.WARNING, logger="httpx")
        with caplog.at_level(logging.DEBUG):
            await accept(order("cop-dem-glo-30", (("DEM_N47_E009",),), ("data",)), source)
            await accept(order(), source)
            await refused(order(assets=("swir",)), source)
            await refused(
                order(
                    aoi={
                        "type": "Polygon",
                        "coordinates": [[[100.0, 10.0], [100.1, 10.0], [100.1, 10.1], [100.0, 10.0]]],
                    }
                ),
                source,
            )
        assert caplog.records
        text = "\n".join(own_log_text(record) for record in caplog.records)
        for forbidden in ("47.01", "9.01", "100.1", "https://", "c1:", S2_HOST + "/tiles", "evil"):
            assert forbidden not in text, forbidden
        accepted = [record for record in caplog.records if record.getMessage() == "order accepted"]
        assert len(accepted) == 2
        assert all(len(record.order_recipe_id) == 22 for record in accepted)  # type: ignore[attr-defined]


# --- fetch_item_or_refuse ---------------------------------------------------------------


class TestFetchItem:
    async def test_an_unknown_collection_follows_the_status_the_caller_names(self) -> None:
        async def unknown(dataset: str, item_id: str) -> dict[str, Any]:
            raise UnknownCollection(dataset)

        with pytest.raises(OrderRefused) as tile:
            await fetch_item_or_refuse(unknown, "nope", "x")
        with pytest.raises(OrderRefused) as body:
            await fetch_item_or_refuse(unknown, "nope", "x", not_found=422)
        assert (tile.value.status_code, body.value.status_code) == (404, 422)

    async def test_a_timeout_is_a_504(self) -> None:
        from earthx.gateway import UpstreamTimeout

        async def slow(dataset: str, item_id: str) -> dict[str, Any]:
            raise UpstreamTimeout("x")

        with pytest.raises(OrderRefused) as error:
            await fetch_item_or_refuse(slow, "d", "i")
        assert error.value.status_code == 504


# --- recipe.json of the crop (adr/0014 §10.1) ----------------------------------------


class TestEstimateOrder:
    """M4-13a: stages 1 to 6 of intake and a recipe without versions, for the cost estimate."""

    @staticmethod
    async def estimate(document: dict[str, Any] | str | bytes, source: Source, **kw: Any):
        raw = document if isinstance(document, (str, bytes)) else json.dumps(document)
        kw.setdefault("registry", REGISTRY)
        kw.setdefault("operators", OPERATORS)
        return await estimate_order(raw, item_source=source, **kw)

    async def test_the_recipe_has_neither_a_version_nor_an_identifier(self) -> None:
        estimated = await self.estimate(order(), Source((S2, s2_item())))
        assert estimated.recipe.recipe_id is None
        resolved = estimated.recipe.inputs[0].resolved
        assert len(resolved) == 2 and all(entry.version is None for entry in resolved)
        assert estimated.skipped_items == ()

    async def test_the_rest_of_the_recipe_is_the_one_an_order_becomes(self) -> None:
        source = Source((S2, s2_item()))
        estimated = await self.estimate(order(), source)
        accepted = await accept(order(), source)
        unversioned = [entry.model_copy(update={"version": None}) for entry in accepted.recipe.inputs[0].resolved]
        assert estimated.recipe.inputs[0].resolved == unversioned
        assert estimated.recipe.steps == accepted.recipe.steps and estimated.recipe.aoi == accepted.recipe.aoi

    async def test_items_the_area_does_not_touch_are_named(self) -> None:
        source = Source((S2, s2_item()), (S2, s2_item("S2_FAR", FAR)))
        estimated = await self.estimate(order(groups=(("S2_A", "S2_FAR"),)), source)
        assert estimated.skipped_items == ("S2_FAR",)
        assert estimated.recipe.inputs[0].groups == [["S2_A"]]

    async def test_it_refuses_where_accepting_refuses_with_the_same_status_and_stage(self) -> None:
        for stage, (document, source, kw) in (await TestStages._cases()).items():
            expected = await refused(document, source, **kw)
            with pytest.raises(OrderRefused) as error:
                await self.estimate(document, source, **kw)
            assert (error.value.status_code, error.value.stage, error.value.detail) == (
                expected.status_code,
                expected.stage,
                expected.detail,
            ), stage

    async def test_a_version_is_never_asked_for(self) -> None:
        item = s2_item()
        for asset in ("red", "nir"):
            item["assets"][asset].pop("file:checksum")
        item["properties"].pop("updated")
        # There is no gateway to pass: whatever the source would say about the assets is not heard.
        estimated = await self.estimate(order(), Source((S2, item)))
        assert all(entry.version is None for entry in estimated.recipe.inputs[0].resolved)

    async def test_an_order_with_a_recipe_id_is_turned_away_as_for_a_job(self) -> None:
        with pytest.raises(OrderRefused) as error:
            await self.estimate(order(recipe_id="A" * 22), Source((S2, s2_item())))
        assert (error.value.status_code, error.value.stage) == (400, "order")


AT = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def crop(config: DatasetConfig, groups: list[list[dict[str, Any]]], assets: list[str], **kw: Any) -> dict[str, Any]:
    raw = crop_recipe_json(
        config, groups=groups, assets=assets, aoi=SQUARE, resolution_factor=kw.pop("factor", 1), accepted_at=AT
    )
    assert raw.endswith(b"\n")
    return json.loads(raw)


class TestCropRecipeJson:
    def test_the_same_schema_as_a_job_with_no_steps_and_the_crop_described(self) -> None:
        document = crop(S2, [[s2_item()]], ["red", "nir"], factor=4)
        provenance = document.pop("provenance")
        recipe = recipe_from_data(document, OPERATORS)
        assert recipe.steps == []
        assert document["output"] == {
            "kind": "crop",
            "format": "cog",
            "resolution_factor": 4,
            "extent": "bbox(aoi ∩ footprints)",
            "mask": "file",
        }
        assert recipe.inputs[0].resolved[0].version.kind == "file:checksum"  # type: ignore[union-attr]
        assert "recipe_id" not in document
        assert provenance["execution"] == "cloud"
        assert provenance["kind"] == "sync-download"
        assert provenance["self_attested"] is False
        assert provenance["started"].startswith("2026-10-07T12:00:00")
        assert set(provenance["engine"]) == {"earthx", "gdal", "rasterio", "numexpr", "numpy"}
        assert provenance["scaling"] == []
        assert "2026" in provenance["attribution"][0]

    def test_no_hash_anywhere(self) -> None:
        raw = crop_recipe_json(
            S2, groups=[[s2_item()]], assets=["red"], aoi=SQUARE, resolution_factor=1, accepted_at=AT
        )
        assert b"c1:" not in raw

    def test_a_dem_tile_carries_no_version_and_no_request_is_made(self) -> None:
        document = crop(DEM, [[dem_item()]], ["data"])
        assert document["inputs"][0]["resolved"][0]["version"] is None

    def test_eopf_carries_updated(self) -> None:
        document = crop(EOPF, [[eopf_item()]], ["SR_10m:b04"])
        assert document["inputs"][0]["resolved"][0]["version"]["kind"] == "updated"

    def test_two_groups_keep_their_shape(self) -> None:
        document = crop(S2, [[s2_item("S2_A")], [s2_item("S2_B")]], ["red"])
        assert document["inputs"][0]["groups"] == [["S2_A"], ["S2_B"]]

    def test_the_same_input_gives_the_same_bytes(self) -> None:
        one = crop_recipe_json(
            S2, groups=[[s2_item()]], assets=["red"], aoi=SQUARE, resolution_factor=1, accepted_at=AT
        )
        two = crop_recipe_json(
            S2, groups=[[s2_item()]], assets=["red"], aoi=SQUARE, resolution_factor=1, accepted_at=AT
        )
        assert one == two

    def test_an_item_pointing_off_the_dataset_is_refused_here_too(self) -> None:
        item = s2_item()
        item["assets"]["red"]["href"] = "https://evil.example/B04.tif"
        with pytest.raises(OrderRefused) as error:
            crop_recipe_json(S2, groups=[[item]], assets=["red"], aoi=SQUARE, resolution_factor=1, accepted_at=AT)
        assert error.value.status_code == 502

    def test_an_aoi_with_properties_keeps_only_its_geometry(self) -> None:
        """A place-search AOI carries its provenance in `properties` (M3-07b); the notice reads it, the recipe does not."""
        aoi = {**SQUARE, "properties": {"attribution": "OSM contributors"}}
        raw = crop_recipe_json(S2, groups=[[s2_item()]], assets=["red"], aoi=aoi, resolution_factor=1, accepted_at=AT)
        assert json.loads(raw)["aoi"] == SQUARE
        assert b"OSM" not in raw

    def test_a_checksum_too_long_for_a_version_is_refused_not_a_crash(self) -> None:
        item = s2_item()
        item["assets"]["red"]["file:checksum"] = "x" * 300
        with pytest.raises(OrderRefused) as error:
            crop_recipe_json(S2, groups=[[item]], assets=["red"], aoi=SQUARE, resolution_factor=1, accepted_at=AT)
        assert error.value.status_code == 502

    def test_a_resolution_that_no_download_offers_is_refused(self) -> None:
        with pytest.raises(OrderRefused):
            crop_recipe_json(S2, groups=[[s2_item()]], assets=["red"], aoi=SQUARE, resolution_factor=3, accepted_at=AT)

    def test_every_item_brings_its_footprint_and_one_without_a_polygon_brings_none(self) -> None:
        with_polygon = s2_item("S2_A")
        without = {**s2_item("S2_B"), "geometry": {"type": "Point", "coordinates": [9.0, 47.0]}}
        document = crop(S2, [[with_polygon, without]], ["red"])
        footprints = document["inputs"][0]["footprints"]
        assert footprints["S2_A"] == with_polygon["geometry"]
        assert footprints["S2_B"] is None


# --- an export (M4-11a) ------------------------------------------------------------

CROP = {"kind": "crop", "format": "cog", "resolution_factor": 1, "extent": "bbox(aoi ∩ footprints)", "mask": "file"}
PLACE = {"attribution": "© OpenStreetMap contributors", "license": "ODbL-1.0", "source": "Nominatim"}


def export_order(groups: tuple[tuple[str, ...], ...] = (("S2_A",),), **override: Any) -> dict[str, Any]:
    return order(groups=groups, assets=("visual",), **{"steps": [], "output": CROP, **override})


def visual_item(item_id: str, bbox: tuple[float, float, float, float] = NEAR) -> dict[str, Any]:
    item = s2_item(item_id, bbox)
    item["assets"]["visual"] = {
        "href": f"https://{S2_HOST}/{item_id}/TCI.tif",
        "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "gsd": 10,
        "raster:bands": [{"data_type": "uint8", "nodata": 0}] * 3,
    }
    return item


class TestAnExport:
    async def test_it_becomes_a_crop_recipe_with_footprints_and_its_side_files(self) -> None:
        source = Source((S2, visual_item("S2_A")), (S2, visual_item("S2_B")), (S2, visual_item("S2_C")))
        accepted = await accept(export_order((("S2_A", "S2_B"), ("S2_C",))), source)
        recipe = accepted.recipe
        assert recipe.output.kind == "crop" and recipe.steps == []
        assert set(recipe.inputs[0].footprints or {}) == {"S2_A", "S2_B", "S2_C"}
        assert accepted.cacheable is False
        assert accepted.attachments is not None
        notice = accepted.attachments.files["ATTRIBUTION.txt"]
        assert "Group 1 (group-01/): S2_A, S2_B" in notice and "Group 2 (group-02/): S2_C" in notice
        assert "visual (visual.tif, mask: visual_mask.tif)" in notice
        assert accepted.attachments.files["citation.bib"].startswith("@misc{sentinel-2-c1-l2a,")
        assert json.loads(accepted.attachments.files["aoi.geojson"]) == SQUARE
        assert accepted.attachments.attribution and "Copernicus" in accepted.attachments.attribution[0]

    async def test_the_origin_of_a_place_aoi_reaches_the_side_files_and_never_the_recipe(self) -> None:
        source = Source((S2, visual_item("S2_A")))
        plain = await accept(export_order(), source)
        placed = await accept(export_order(), source, aoi_provenance=PLACE)
        assert placed.attachments is not None
        assert "AOI geometry: © OpenStreetMap contributors, ODbL-1.0 (via Nominatim)" in placed.attachments.files[
            "ATTRIBUTION.txt"
        ]
        assert json.loads(placed.attachments.files["aoi.geojson"])["properties"] == PLACE
        assert "properties" not in placed.recipe.aoi.model_dump(mode="json")
        assert recipe_hash(placed.recipe) == recipe_hash(plain.recipe)

    async def test_only_groups_left_out_entirely_are_named_as_left_out(self) -> None:
        source = Source(
            (S2, visual_item("S2_A")), (S2, visual_item("S2_FAR", FAR)), (S2, visual_item("S2_GONE", FAR))
        )
        accepted = await accept(export_order((("S2_A", "S2_FAR"), ("S2_GONE",))), source)
        assert accepted.attachments is not None
        notice = accepted.attachments.files["ATTRIBUTION.txt"]
        assert "Not covered by the AOI, left out: S2_GONE" in notice
        assert "S2_FAR" not in notice
        assert accepted.skipped_items == ("S2_FAR", "S2_GONE")

    async def test_a_group_is_judged_by_the_footprints_the_recipe_carries(self) -> None:
        """A footprint the recipe cannot carry (no polygon) does not keep a group the AOI misses: 422, not 500."""
        odd = visual_item("S2_ODD")
        odd["geometry"] = {"type": "GeometryCollection", "geometries": [_footprint(NEAR)]}
        rotated = visual_item("S2_ROT")  # its bbox reaches the AOI, its footprint does not
        rotated["geometry"] = _footprint(FAR)
        source = Source((S2, odd), (S2, rotated))
        error = await refused(export_order((("S2_ODD", "S2_ROT"),)), source)
        assert error.status_code == 422 and error.stage == "aoi"

    async def test_an_export_with_steps_is_refused(self) -> None:
        error = await refused(export_order(steps=[SCALE_STEP]), Source((S2, visual_item("S2_A"))))
        assert error.status_code == 422 and "no steps" in error.detail

    async def test_an_export_at_a_coarser_resolution_is_refused(self) -> None:
        error = await refused(export_order(output={**CROP, "resolution_factor": 2}), Source((S2, visual_item("S2_A"))))
        assert error.status_code == 422 and "native resolution" in error.detail

    async def test_a_zarr_dataset_is_refused_before_any_item_is_fetched(self) -> None:
        source = Source((EOPF, eopf_item()))
        document = order(dataset=EOPF.dataset_id, groups=(("EOPF_A",),), assets=("SR_10m:b04",), steps=[], output=CROP)
        error = await refused(document, source)
        assert error.status_code == 422 and "COG assets only" in error.detail
        assert source.calls == []

    async def test_an_export_over_5_gb_is_refused_by_the_estimate(self) -> None:
        wide = (8.0, 45.0, 14.0, 50.0)
        aoi = _footprint(wide)
        error = await refused(export_order(aoi=aoi), Source((S2, visual_item("S2_A", wide))))
        assert error.status_code == 413 and error.stage == "size"
        assert "5000 MB" in error.detail

    async def test_aoi_provenance_belongs_to_an_export_only(self) -> None:
        source = Source((S2, s2_item()))
        with pytest.raises(OrderRefused) as caught:
            await accept(order(), source, aoi_provenance=PLACE)
        assert caught.value.status_code == 400 and source.calls == []


class TestTheJobsCapMatchesTheCropsEstimate:
    """M4-11 K5: the crop route offers a job by its own estimate; the job must count the same bytes."""

    @staticmethod
    def _crop_total(items: list[dict[str, Any]]) -> int:
        aoi = parse_aoi_geometry(SQUARE)
        region = compute_crop_region(items, aoi)
        return sum(output.total_bytes for output in plan_outputs(items, ["visual"], region))

    async def test_the_export_is_estimated_as_the_crop_estimates_it(self) -> None:
        items = [visual_item("S2_A"), visual_item("S2_B", (8.95, 46.95, 9.2, 47.2))]
        accepted = await accept(export_order((("S2_A", "S2_B"),)), Source(*((S2, item) for item in items)))
        assert sum(output.total_bytes for output in export_outputs(accepted.recipe)) == self._crop_total(items)

    async def test_the_cap_holds_to_the_byte(self, monkeypatch: pytest.MonkeyPatch) -> None:
        total = self._crop_total([visual_item("S2_A")])
        source = Source((S2, visual_item("S2_A")))
        monkeypatch.setattr("earthx.processing.plan.MAX_EXPORT_JOB_BYTES", total)
        assert (await accept(export_order(), source)).attachments is not None
        monkeypatch.setattr("earthx.processing.plan.MAX_EXPORT_JOB_BYTES", total - 1)
        assert (await refused(export_order(), source)).status_code == 413
