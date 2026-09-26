"""T-A/T-B: `adapters.cop_dem_bucket` against a mocked bucket.

Everything goes through `gateway` with a mock transport, so these tests also
prove the reconciliation the plan asked for (`docs/plans/m3-11b-dem-adapter.md`
§3.2, F2): a tile the list names but the bucket does not have, a tile the
bucket itself withholds, and a bucket prefix the list never named — none of
the three is trusted blindly ("Quell-Listen lügen", `adr/0009` §11).
"""

from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from earthx.adapters import NotMaterialized, UnsupportedSource, UpstreamShapeError, materialize_items
from earthx.adapters.cop_dem_bucket import COG_MEDIA_TYPE, MAX_NOT_LOADABLE_FRACTION
from earthx.catalog.datasets import COP_DEM_GLO_30, DEM_ACQUISITION_END, DEM_ACQUISITION_START, SENTINEL_2_L2A
from earthx.gateway import Policy
from earthx.gateway.client import Gateway

pytestmark = pytest.mark.anyio

HOST = "bucket.example.invalid"
POLICY = Policy(allowed_hosts=frozenset({HOST}))

TILE_NE = "Copernicus_DSM_COG_10_N46_00_E010_00_DEM"
TILE_NW = "Copernicus_DSM_COG_10_N46_00_W010_00_DEM"
TILE_SE = "Copernicus_DSM_COG_10_S34_00_E018_00_DEM"
TILE_SW = "Copernicus_DSM_COG_10_S34_00_W018_00_DEM"
TILE_POLAR = "Copernicus_DSM_COG_10_S90_00_W180_00_DEM"

_BLACKLIST_NAME = "Copernicus_DSM_10_{coord}_DEM.tif"


def _config() -> object:
    """The registry entry, with the synthetic host in place of the real bucket."""
    return replace(
        COP_DEM_GLO_30, source=replace(COP_DEM_GLO_30.source, endpoint=f"https://{HOST}", asset_hosts=(HOST,))
    )


def _public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def gateway_for(handler):
    async def sleep(seconds: float) -> None:
        return None

    return Gateway(POLICY, transport=httpx.MockTransport(handler), resolve=_public, sleep=sleep)


def _listing_xml(prefixes: list[str], *, next_token: str | None = None) -> bytes:
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">',
    ]
    for prefix in prefixes:
        parts.append(f"<CommonPrefixes><Prefix>{prefix}/</Prefix></CommonPrefixes>")
    if next_token is not None:
        parts.append(f"<NextContinuationToken>{next_token}</NextContinuationToken>")
    parts.append("</ListBucketResult>")
    return "".join(parts).encode()


def bucket(
    *,
    tile_list_names: list[str],
    listing_pages: list[list[str]] | None = None,
    blacklist_names: list[str] | None = None,
    etag: str = '"synthetic-etag"',
    line_sep: str = "\r\n",
) -> tuple[Gateway, list[httpx.Request]]:
    """A gateway answering the three requests `materialize_items` makes, plus the
    requests it saw — one bucket listing page unless `listing_pages` names more.
    """
    seen: list[httpx.Request] = []
    pages = listing_pages if listing_pages is not None else [tile_list_names]
    tile_list_body = line_sep.join(tile_list_names).encode() + (line_sep.encode() if tile_list_names else b"")
    blacklist_body = "\n".join(blacklist_names or []).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path.endswith("/tileList.txt"):
            return httpx.Response(200, content=tile_list_body, headers={"etag": etag})
        if path.endswith("/blacklist.txt"):
            return httpx.Response(200, content=blacklist_body)
        token = request.url.params.get("continuation-token")
        index = 0 if token is None else int(token)
        is_last = index == len(pages) - 1
        body = _listing_xml(pages[index], next_token=None if is_last else str(index + 1))
        return httpx.Response(200, content=body)

    return gateway_for(handler), seen


def _many_tile_names(count: int) -> list[str]:
    """``count`` distinct, valid tile names, none of them one of this module's own
    single-tile fixtures (lon starts at 20, every fixture tile sits at 10 or 18) —
    for a reconciliation case that has to stay under the abort threshold (§3.2) to
    be about anything but the abort."""
    names = []
    lat = 0
    lon = 20
    while len(names) < count:
        names.append(f"Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM")
        lat += 1
        if lat > 89:
            lat = 0
            lon += 1
    return names


def unchanged_bucket(*, known_etag: str) -> tuple[Gateway, list[httpx.Request]]:
    """A gateway that answers `tileList.txt` with `304` for exactly `known_etag`."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.url.path.endswith("/tileList.txt"), "an unchanged run must ask nothing else"
        if request.headers.get("if-none-match") == known_etag:
            return httpx.Response(304)
        raise AssertionError("If-None-Match did not carry the known version")

    return gateway_for(handler), seen


class TestALoadedRun:
    async def test_every_listed_and_bucketed_tile_becomes_an_item(self) -> None:
        gateway, seen = bucket(tile_list_names=[TILE_NE, TILE_SW])
        async with gateway:
            outcome = await materialize_items(_config(), gateway=gateway, known_version=None)

        assert outcome.status == "loaded"
        assert outcome.source_version == '"synthetic-etag"'
        assert {item["id"] for item in outcome.items} == {TILE_NE, TILE_SW}
        assert outcome.listed == outcome.in_bucket == 2
        assert outcome.missing == outcome.withheld == outcome.unknown == 0
        paths = [request.url.path for request in seen]
        assert paths[0].endswith("/tileList.txt")
        assert paths[1].endswith("/blacklist.txt")
        assert paths[2] == "/"

    async def test_the_conditional_header_carries_the_known_version(self) -> None:
        gateway, seen = bucket(tile_list_names=[TILE_NE], etag='"v2"')
        async with gateway:
            await materialize_items(_config(), gateway=gateway, known_version='"v1"')
        assert seen[0].headers["if-none-match"] == '"v1"'

    async def test_no_conditional_header_without_a_known_version(self) -> None:
        gateway, seen = bucket(tile_list_names=[TILE_NE])
        async with gateway:
            await materialize_items(_config(), gateway=gateway, known_version=None)
        assert "if-none-match" not in seen[0].headers

    async def test_a_trailing_blank_line_is_ignored(self) -> None:
        gateway, _ = bucket(tile_list_names=[TILE_NE, "", ""])
        async with gateway:
            outcome = await materialize_items(_config(), gateway=gateway, known_version=None)
        assert [item["id"] for item in outcome.items] == [TILE_NE]

    async def test_a_paginated_listing_is_combined(self) -> None:
        gateway, seen = bucket(
            tile_list_names=[TILE_NE, TILE_SW, TILE_SE],
            listing_pages=[[TILE_NE], [TILE_SW], [TILE_SE]],
        )
        async with gateway:
            outcome = await materialize_items(_config(), gateway=gateway, known_version=None)
        assert outcome.in_bucket == 3
        assert {item["id"] for item in outcome.items} == {TILE_NE, TILE_SW, TILE_SE}
        listing_requests = [request for request in seen if request.url.path == "/"]
        assert len(listing_requests) == 3


class TestUnchanged:
    async def test_a_304_is_reported_without_reading_anything_else(self) -> None:
        gateway, seen = unchanged_bucket(known_etag='"same"')
        async with gateway:
            outcome = await materialize_items(_config(), gateway=gateway, known_version='"same"')
        assert outcome.status == "unchanged"
        assert outcome.source_version == '"same"'
        assert outcome.items == ()
        assert outcome.listed == outcome.in_bucket == outcome.missing == outcome.withheld == outcome.unknown == 0
        assert len(seen) == 1


class TestReconciliation:
    """Each case adds its excluded tile to a large-enough list that it stays under
    the 1% abort threshold (`TestAbort` below tests that threshold on its own)."""

    async def test_a_listed_tile_missing_from_the_bucket_is_excluded_and_counted(self) -> None:
        names = _many_tile_names(200) + [TILE_NE]
        gateway, _ = bucket(tile_list_names=names, listing_pages=[_many_tile_names(200)])
        async with gateway:
            outcome = await materialize_items(_config(), gateway=gateway, known_version=None)
        assert TILE_NE not in {item["id"] for item in outcome.items}
        assert outcome.missing == 1
        assert outcome.withheld == 0

    async def test_a_withheld_tile_is_excluded_even_though_the_bucket_has_it(self) -> None:
        names = _many_tile_names(200) + [TILE_NE]
        gateway, _ = bucket(
            tile_list_names=names,
            blacklist_names=[_BLACKLIST_NAME.format(coord="N46_00_E010_00")],
        )
        async with gateway:
            outcome = await materialize_items(_config(), gateway=gateway, known_version=None)
        assert TILE_NE not in {item["id"] for item in outcome.items}
        assert outcome.withheld == 1
        assert outcome.missing == 0

    async def test_an_unlisted_bucket_prefix_is_counted_but_never_loaded(self) -> None:
        base = _many_tile_names(200)
        gateway, _ = bucket(tile_list_names=base, listing_pages=[base + [TILE_NE]])
        async with gateway:
            outcome = await materialize_items(_config(), gateway=gateway, known_version=None)
        assert TILE_NE not in {item["id"] for item in outcome.items}
        assert outcome.unknown == 1

    async def test_a_withheld_tile_absent_from_the_bucket_counts_once_not_twice(self) -> None:
        """A tile can be both listed-but-absent and blacklisted; §3.2's ``missing``
        only ever names what withholding does not already explain."""
        names = _many_tile_names(200) + [TILE_NE]
        gateway, _ = bucket(
            tile_list_names=names,
            listing_pages=[_many_tile_names(200)],
            blacklist_names=[_BLACKLIST_NAME.format(coord="N46_00_E010_00")],
        )
        async with gateway:
            outcome = await materialize_items(_config(), gateway=gateway, known_version=None)
        assert outcome.withheld == 1
        assert outcome.missing == 0


class TestAbort:
    async def test_an_empty_bucket_listing_aborts(self) -> None:
        gateway, _ = bucket(tile_list_names=[TILE_NE], listing_pages=[[]])
        async with gateway:
            with pytest.raises(UpstreamShapeError, match="no prefixes"):
                await materialize_items(_config(), gateway=gateway, known_version=None)

    async def test_at_the_one_percent_threshold_nothing_aborts(self) -> None:
        names = [f"Copernicus_DSM_COG_10_N{lat:02d}_00_E010_00_DEM" for lat in range(90)]  # 90 tiles
        # Exactly one missing of ninety is ~1.11%, over the threshold on purpose —
        # this case is the boundary check for the *fraction*, not the count: a
        # hundred-tile list with exactly one missing (1.00%) must not abort.
        names_hundred = names + [f"Copernicus_DSM_COG_10_N{lat:02d}_00_E011_00_DEM" for lat in range(10)]
        assert len(names_hundred) == 100
        missing_one = names_hundred[0]
        gateway, _ = bucket(tile_list_names=names_hundred, listing_pages=[names_hundred[1:]])
        async with gateway:
            outcome = await materialize_items(_config(), gateway=gateway, known_version=None)
        assert outcome.missing == 1
        assert missing_one not in {item["id"] for item in outcome.items}
        assert MAX_NOT_LOADABLE_FRACTION == 0.01

    async def test_over_the_threshold_aborts_without_writing_anything(self) -> None:
        names = [f"Copernicus_DSM_COG_10_N{lat:02d}_00_E010_00_DEM" for lat in range(90)]
        names += [f"Copernicus_DSM_COG_10_N{lat:02d}_00_E011_00_DEM" for lat in range(10)]
        assert len(names) == 100
        # Two of a hundred missing is 2%, over the 1% threshold.
        gateway, _ = bucket(tile_list_names=names, listing_pages=[names[2:]])
        async with gateway:
            with pytest.raises(UpstreamShapeError, match="not loadable"):
                await materialize_items(_config(), gateway=gateway, known_version=None)


class TestMalformedSource:
    async def test_a_line_that_does_not_fit_the_tile_name_pattern_fails_the_whole_run(self) -> None:
        gateway, _ = bucket(tile_list_names=[TILE_NE, "not-a-dem-tile-name"])
        async with gateway:
            with pytest.raises(UpstreamShapeError, match="does not match"):
                await materialize_items(_config(), gateway=gateway, known_version=None)

    async def test_a_response_without_an_etag_fails(self) -> None:
        async def sleep(seconds: float) -> None:
            return None

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=f"{TILE_NE}\r\n".encode())

        gateway = Gateway(POLICY, transport=httpx.MockTransport(handler), resolve=_public, sleep=sleep)
        async with gateway:
            with pytest.raises(UpstreamShapeError, match="ETag"):
                await materialize_items(_config(), gateway=gateway, known_version=None)

    async def test_a_bucket_listing_that_is_not_xml_fails(self) -> None:
        async def sleep(seconds: float) -> None:
            return None

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/tileList.txt"):
                return httpx.Response(200, content=f"{TILE_NE}\r\n".encode(), headers={"etag": '"e"'})
            if path.endswith("/blacklist.txt"):
                return httpx.Response(200, content=b"")
            return httpx.Response(200, content=b"not xml at all")

        gateway = Gateway(POLICY, transport=httpx.MockTransport(handler), resolve=_public, sleep=sleep)
        async with gateway:
            with pytest.raises(UpstreamShapeError, match="not valid XML"):
                await materialize_items(_config(), gateway=gateway, known_version=None)


class TestItemShape:
    @pytest.mark.parametrize(
        ("name", "bbox"),
        [
            (TILE_NE, [10.0, 46.0, 11.0, 47.0]),
            (TILE_NW, [-10.0, 46.0, -9.0, 47.0]),
            (TILE_SE, [18.0, -34.0, 19.0, -33.0]),
            (TILE_SW, [-18.0, -34.0, -17.0, -33.0]),
            (TILE_POLAR, [-180.0, -90.0, -179.0, -89.0]),
        ],
    )
    async def test_the_nominal_bbox_matches_the_tile_name(self, name: str, bbox: list[float]) -> None:
        gateway, _ = bucket(tile_list_names=[name])
        async with gateway:
            outcome = await materialize_items(_config(), gateway=gateway, known_version=None)
        (item,) = outcome.items
        assert item["bbox"] == bbox
        assert item["geometry"]["type"] == "Polygon"

    async def test_the_asset_points_at_the_endpoint_configured_host(self) -> None:
        gateway, _ = bucket(tile_list_names=[TILE_NE])
        async with gateway:
            outcome = await materialize_items(_config(), gateway=gateway, known_version=None)
        (item,) = outcome.items
        asset = item["assets"]["data"]
        assert asset["href"] == f"https://{HOST}/{TILE_NE}/{TILE_NE}.tif"
        assert asset["type"] == COG_MEDIA_TYPE
        assert asset["roles"] == ["data"]

    async def test_the_item_carries_the_collection_id_and_no_datetime(self) -> None:
        gateway, _ = bucket(tile_list_names=[TILE_NE])
        async with gateway:
            outcome = await materialize_items(_config(), gateway=gateway, known_version=None)
        (item,) = outcome.items
        assert item["collection"] == _config().dataset_id
        assert item["properties"]["datetime"] is None
        assert item["properties"]["gsd"] == 30.0
        assert item["properties"]["proj:code"] == "EPSG:4326"

    async def test_the_acquisition_period_matches_the_registry_constants(self) -> None:
        gateway, _ = bucket(tile_list_names=[TILE_NE])
        async with gateway:
            outcome = await materialize_items(_config(), gateway=gateway, known_version=None)
        (item,) = outcome.items
        assert item["properties"]["start_datetime"] == DEM_ACQUISITION_START.strftime("%Y-%m-%dT%H:%M:%SZ")
        assert item["properties"]["end_datetime"] == DEM_ACQUISITION_END.strftime("%Y-%m-%dT%H:%M:%SZ")


class TestDispatch:
    async def test_a_federated_dataset_is_refused(self) -> None:
        gateway, seen = bucket(tile_list_names=[TILE_NE])
        async with gateway:
            with pytest.raises(NotMaterialized):
                await materialize_items(SENTINEL_2_L2A, gateway=gateway, known_version=None)
        assert seen == []

    async def test_a_materialized_kind_no_materializer_knows_is_refused(self) -> None:
        """A dispatch mistake, not a real dataset — the same posture
        `adapters._adapter_for` takes for an unknown `AdapterKind` (`test_dispatch.py`)."""
        stranded = replace(_config(), source=replace(_config().source, adapter=SENTINEL_2_L2A.source.adapter))
        gateway, seen = bucket(tile_list_names=[TILE_NE])
        async with gateway:
            with pytest.raises(UnsupportedSource, match="no materializer dispatch knows"):
                await materialize_items(stranded, gateway=gateway, known_version=None)
        assert seen == []
