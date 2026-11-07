"""T-A/T-B: `adapters.esa_worldcover_bucket` against a mocked bucket (M5-07 plan §4.2).

The grid and the listing are synthetic; everything goes through `gateway` with a mock transport. The checks the plan
asks for: the grid's names and polygons, files missing from the bucket below and above 1 %, files the grid never named,
an unchanged grid (`304`), and the registry errors a caller can make.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from earthx.adapters import (
    ADAPTER_SPECS,
    NotMaterialized,
    UnsupportedSource,
    UpstreamShapeError,
    esa_worldcover_bucket,
    materialize_items,
)
from earthx.adapters.cop_dem_bucket import COG_MEDIA_TYPE
from earthx.catalog.registry import ItemHolding, TemporalExtent
from earthx.gateway import Policy
from earthx.gateway.client import Gateway
from tests.catalog.entries import ESA_WORLDCOVER_2020, ESA_WORLDCOVER_2021

pytestmark = pytest.mark.anyio

HOST = "bucket.example.invalid"
POLICY = Policy(allowed_hosts=frozenset({HOST}))
ETAG = '"synthetic-grid"'


def _config(entry=ESA_WORLDCOVER_2021):
    return replace(entry, source=replace(entry.source, endpoint=f"https://{HOST}", asset_hosts=(HOST,)))


def _public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def _cell(tile: str) -> list[list[float]]:
    south = int(tile[1:3]) * (1 if tile[0] == "N" else -1)
    west = int(tile[4:7]) * (1 if tile[3] == "E" else -1)
    return [[west, south], [west + 3, south], [west + 3, south + 3], [west, south + 3], [west, south]]


def grid(tiles: list[str], *, ring=None) -> bytes:
    features = [
        {"type": "Feature", "properties": {"ll_tile": tile}, "geometry": {"type": "Polygon", "coordinates": [ring or _cell(tile)]}}
        for tile in tiles
    ]
    return json.dumps({"type": "FeatureCollection", "features": features}).encode()


def key(tile: str, prefix: str = "v200/2021") -> str:
    version, year = prefix.split("/")
    return f"{prefix}/map/ESA_WorldCover_10m_{year}_{version}_{tile}_Map.tif"


def _listing(keys: list[str], next_token: str | None) -> bytes:
    body = "".join(f"<Contents><Key>{k}</Key></Contents>" for k in keys)
    token = f"<NextContinuationToken>{next_token}</NextContinuationToken>" if next_token else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        f"{body}{token}</ListBucketResult>"
    ).encode()


def bucket(grid_body: bytes, pages: list[list[str]], *, etag: str | None = ETAG):
    """A gateway answering the grid and the listing pages, and the requests it saw."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/esa_worldcover_grid.geojson":
            if request.headers.get("if-none-match") == ETAG:
                return httpx.Response(304)
            return httpx.Response(200, content=grid_body, headers={"etag": etag} if etag else {})
        if request.url.path == "/":
            page = int(request.url.params.get("continuation-token", "0"))
            following = str(page + 1) if page + 1 < len(pages) else None
            return httpx.Response(200, content=_listing(pages[page], following))
        return httpx.Response(404)

    async def sleep(seconds: float) -> None:
        return None

    return Gateway(POLICY, transport=httpx.MockTransport(handler), resolve=_public, sleep=sleep), seen


async def _run(gateway, config=None, known_version=None):
    return await materialize_items(config or _config(), adapters=ADAPTER_SPECS, gateway=gateway, known_version=known_version)


TILES = ["N45E006", "N45E009", "S03W060"]


class TestNormalRun:
    async def test_every_grid_tile_with_a_file_becomes_an_item(self) -> None:
        gateway, seen = bucket(grid(TILES), [[key(t) for t in TILES]])
        outcome = await _run(gateway)
        assert outcome.status == "loaded"
        assert outcome.source_version == ETAG
        assert (outcome.listed, outcome.in_bucket, outcome.missing, outcome.unknown) == (3, 3, 0, 0)
        item = next(i for i in outcome.items if i["id"] == "ESA_WorldCover_10m_2021_v200_S03W060")
        assert item["bbox"] == [-60.0, -3.0, -57.0, 0.0]
        assert item["collection"] == "esa-worldcover-2021"
        assert item["properties"]["datetime"] is None
        assert item["properties"]["start_datetime"] == "2021-01-01T00:00:00Z"
        assert item["properties"]["end_datetime"] == "2021-12-31T23:59:59Z"
        assert item["assets"] == {"map": {"href": f"https://{HOST}/{key('S03W060')}", "type": COG_MEDIA_TYPE, "roles": ["data"]}}
        # The listing asks for the map files of this state only.
        assert seen[1].url.params["prefix"] == "v200/2021/map/"

    async def test_the_2020_state_reads_its_own_prefix(self) -> None:
        gateway, seen = bucket(grid(TILES), [[key(t, "v100/2020") for t in TILES]])
        outcome = await _run(gateway, _config(ESA_WORLDCOVER_2020))
        assert {i["id"] for i in outcome.items} == {f"ESA_WorldCover_10m_2020_v100_{t}" for t in TILES}
        assert seen[1].url.params["prefix"] == "v100/2020/map/"

    async def test_the_listing_is_followed_over_its_pages(self) -> None:
        gateway, seen = bucket(grid(TILES), [[key(TILES[0])], [key(TILES[1])], [key(TILES[2])]])
        outcome = await _run(gateway)
        assert len(outcome.items) == 3
        assert [r.url.params.get("continuation-token") for r in seen[1:]] == [None, "1", "2"]

    async def test_an_unchanged_grid_builds_nothing(self) -> None:
        gateway, seen = bucket(grid(TILES), [[key(t) for t in TILES]])
        outcome = await _run(gateway, known_version=ETAG)
        assert (outcome.status, outcome.items, outcome.source_version) == ("unchanged", (), ETAG)
        assert len(seen) == 1

    async def test_a_file_the_grid_never_named_is_counted_not_loaded(self) -> None:
        gateway, _ = bucket(grid(TILES), [[key(t) for t in TILES] + [key("N00E000")]])
        outcome = await _run(gateway)
        assert (outcome.unknown, len(outcome.items)) == (1, 3)


class TestMissingFiles:
    @staticmethod
    def _many(count: int) -> list[str]:
        return [f"N{lat:02d}E{lon:03d}" for lat in range(0, 81, 3) for lon in range(0, 178, 3)][:count]

    async def test_one_missing_in_more_than_a_hundred_is_skipped(self) -> None:
        tiles = self._many(120)
        gateway, _ = bucket(grid(tiles), [[key(t) for t in tiles[1:]]])
        outcome = await _run(gateway)
        assert (outcome.missing, len(outcome.items)) == (1, 119)

    async def test_more_than_one_percent_missing_aborts(self) -> None:
        gateway, _ = bucket(grid(TILES), [[key(t) for t in TILES[1:]]])
        with pytest.raises(UpstreamShapeError, match="1% abort"):
            await _run(gateway)

    async def test_a_state_without_files_aborts(self) -> None:
        gateway, _ = bucket(grid(TILES), [[]])
        with pytest.raises(UpstreamShapeError, match="no file"):
            await _run(gateway)


class TestUntrustedGrid:
    @pytest.mark.parametrize("tile", ["N45E9", "X45E009", "n45e009", "N45E009 ", "N88E000", "N00E180", 45])
    async def test_a_tile_name_that_does_not_fit_aborts(self, tile) -> None:
        body = json.dumps(
            {"type": "FeatureCollection", "features": [{"properties": {"ll_tile": tile}, "geometry": {"coordinates": [_cell("N45E009")]}}]}
        ).encode()
        gateway, _ = bucket(body, [[key("N45E009")]])
        with pytest.raises(UpstreamShapeError):
            await _run(gateway)

    async def test_a_polygon_that_is_not_the_named_cell_aborts(self) -> None:
        gateway, _ = bucket(grid(["N45E009"], ring=_cell("N45E006")), [[key("N45E009")]])
        with pytest.raises(UpstreamShapeError, match="not the cell"):
            await _run(gateway)

    async def test_a_tile_twice_aborts(self) -> None:
        gateway, _ = bucket(grid(["N45E009", "N45E009"]), [[key("N45E009")]])
        with pytest.raises(UpstreamShapeError, match="twice"):
            await _run(gateway)

    @pytest.mark.parametrize(
        "body",
        [b"not json", b"[]", b'{"type": "FeatureCollection"}', b'{"features": []}', b'{"features": [{"properties": {}}]}'],
    )
    async def test_a_broken_grid_aborts(self, body) -> None:
        gateway, _ = bucket(body, [[key("N45E009")]])
        with pytest.raises(UpstreamShapeError):
            await _run(gateway)

    async def test_a_grid_without_an_etag_aborts(self) -> None:
        gateway, _ = bucket(grid(TILES), [[key(t) for t in TILES]], etag=None)
        with pytest.raises(UpstreamShapeError, match="ETag"):
            await _run(gateway)

    async def test_a_broken_listing_aborts(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith(".geojson"):
                return httpx.Response(200, content=grid(TILES), headers={"etag": ETAG})
            return httpx.Response(200, content=b"<not-closed")

        gateway = Gateway(POLICY, transport=httpx.MockTransport(handler), resolve=_public)
        with pytest.raises(UpstreamShapeError, match="XML"):
            await _run(gateway)


class TestMisuse:
    async def test_a_federated_entry_is_refused(self) -> None:
        """The registry forbids the pairing itself; the adapter refuses it all the same, before any request."""
        config = SimpleNamespace(dataset_id="x", source=SimpleNamespace(item_holding=ItemHolding.FEDERATED))
        gateway, seen = bucket(grid(TILES), [[]])
        with pytest.raises(NotMaterialized):
            await esa_worldcover_bucket.materialize_items(config, gateway=gateway, known_version=None)
        assert seen == []

    @pytest.mark.parametrize("state", ["v200", "2021", "v200/2021/map", "v2/2021", "../v200/2021"])
    async def test_a_source_collection_id_that_is_no_state_is_refused(self, state) -> None:
        config = _config()
        config = replace(config, source=replace(config.source, source_collection_id=state))
        gateway, seen = bucket(grid(TILES), [[]])
        with pytest.raises(UnsupportedSource, match="version"):
            await _run(gateway, config)
        assert seen == []

    async def test_an_open_end_is_refused(self) -> None:
        config = replace(_config(), temporal_extent=TemporalExtent(start=datetime(2021, 1, 1, tzinfo=timezone.utc), end=None))
        gateway, _ = bucket(grid(TILES), [[]])
        with pytest.raises(UnsupportedSource, match="no end"):
            await _run(gateway, config)
