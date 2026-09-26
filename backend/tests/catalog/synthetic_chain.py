"""One synthetic source per registry entry, for onboarding checklist point 9.

Point 9 in its v1 wording (D4) is the chain **search → display → clipped
download**, run against fixtures. Running it per registry entry means the chain
has to work out what a given entry needs, and there are exactly two things that
differ: which adapter answers a search, and which reader opens the bytes. Both
follow from the entry itself, so this module dispatches on it rather than on the
dataset id — a third dataset in either format gets point 9 without a line here.

What is synthetic and what is real, precisely:

* **Real:** the entry, its adapter, the search request the adapter builds from
  the endpoint, the tile and download routes, the gateway allowlist, the
  ``check_url`` on every address, the readers, and the rendering.
* **Synthetic:** the answers. The search comes back from an
  ``httpx.MockTransport``, and the asset is a store written by
  `mini_cog.py` or `mini_zarr_composite.py` on the spot.
* **Replaced, and only this:** ``asset_hosts`` on the entry's copy, so the
  synthetic store's host is the one the allowlist admits. The endpoint stays the
  real one, so the adapter builds the URL it really builds.

Both synthetic stores sit on the same ground in the same UTM zone, which is why
one AOI and one tile serve either format.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from rasterio.warp import transform_bounds
from rio_tiler.constants import WEB_MERCATOR_TMS, WGS84_CRS

from earthx.catalog.registry import DataFormat, DatasetConfig, DatasetRegistry, ItemHolding, ViewerInfo
from earthx.gateway import Gateway, Policy, check_url, host_of
from tests.earthx.readers import mini_cog, mini_dem, mini_zarr, mini_zarr_composite

#: The one host both synthetic stores live on.
HOST = mini_zarr.HOST

#: The item every chain searches for and then renders.
ITEM_ID = "SYNTH_CHAIN_20260102T100000"

#: What the mini stores have in common: UTM 32N, upper left at the same corner.
CRS = mini_zarr.ITEM_CRS

#: href, bounds in :data:`CRS`, the ground sample distance and a reader of the
#: read log. The `gsd` (M3-18) is each format's own real resolution constant,
#: not invented: without it on the item, the download route's size estimate
#: (`access.download.plan_outputs`, F1) falls back to its conservative worst
#: case and refuses even this chain's small AOI.
_Asset = tuple[str, tuple[float, ...], float, Callable[[], list[str]]]


class UnsupportedFormat(Exception):
    """No synthetic asset for this format — the right answer, not a skip.

    A dataset in a third format must not pass point 9 quietly just because the
    chain has nothing to run it against.
    """


@dataclass(frozen=True)
class Chain:
    """Everything one run of the chain needs, already wired to one entry."""

    config: DatasetConfig
    registry: DatasetRegistry
    item: dict[str, Any]
    #: The asset key as a tile URL carries it — the entry's own standard
    #: visualisation (checklist point 8), so display uses what the registry says.
    render_asset: str
    aoi: dict[str, Any]
    tile: tuple[int, int, int]
    gateway: Gateway
    #: Every search request the adapter sent, in order.
    searched: list[httpx.Request]
    #: The asset addresses the read path fetched, read at call time. A callable
    #: rather than a list, because the two formats keep their log in different
    #: shapes and both fill it *while* the chain runs.
    read_addresses: Callable[[], list[str]]

    @property
    def dataset_id(self) -> str:
        return self.config.dataset_id


def item_asset_key(config: DatasetConfig, render_asset: str) -> str:
    """The key the *item* carries, from the key a *tile URL* carries.

    For a Zarr entry with a separator the two differ: the item names a group
    (``SR_10m``) and the URL names group and variables (``SR_10m:b04,b03,b02``,
    M2-09b F2). Everywhere else they are the same string.
    """
    separator = config.zarr.variable_separator if config.zarr else None
    return render_asset.split(separator)[0] if separator else render_asset


def build(config: DatasetConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Chain:
    """A chain for one registry entry, or :class:`UnsupportedFormat`."""
    if config.default_render is None:
        # Point 8 has already fallen for such an entry; point 9 would then be
        # testing an asset key this module invented.
        raise UnsupportedFormat(f"{config.dataset_id} has no standard visualisation to display")
    render_asset = config.default_render.assets[0]

    if config.source.item_holding is ItemHolding.MATERIALIZED:
        # M3-11b F9: link 1 is *creation*, not search — a materialized entry has
        # no search API to answer one. `_build_materialized` builds `chain.item`
        # by hand, the same way `_stac_item` below does for a federated entry;
        # the real adapter (`adapters.cop_dem_bucket.materialize_items`) is
        # exercised separately, against a canned bucket of its own
        # (`test_onboarding_endtoend.py`'s replacement for link 1).
        return _build_materialized(config, render_asset, tmp_path, monkeypatch)

    if config.format is DataFormat.COG:
        href, bounds, gsd, read_addresses = _cog_asset(tmp_path, monkeypatch)
    elif config.format is DataFormat.ZARR:
        href, bounds, gsd, read_addresses = _zarr_asset(tmp_path, monkeypatch)
    else:
        raise UnsupportedFormat(f"no synthetic asset for format {config.format.value!r}")

    synthetic = replace(config, source=replace(config.source, asset_hosts=(HOST,)))
    item = _stac_item(item_asset_key(config, render_asset), href, bounds, gsd)
    gateway, searched = _gateway_answering_search(synthetic, item)
    _resolve_from_memory(monkeypatch)

    return Chain(
        config=synthetic,
        registry=DatasetRegistry((synthetic,)),
        item=item,
        render_asset=render_asset,
        aoi=_aoi(bounds),
        tile=_covering_tile(bounds, config.viewer),
        gateway=gateway,
        searched=searched,
        read_addresses=read_addresses,
    )


def _cog_asset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Asset:
    path = mini_cog.build_mini_cog(tmp_path / "mini.tif")
    cleared = mini_cog.serve_cog(path, monkeypatch)
    side = mini_cog.SIZE * mini_cog.RESOLUTION
    bounds = (mini_cog.ORIGIN_X, mini_cog.ORIGIN_Y - side, mini_cog.ORIGIN_X + side, mini_cog.ORIGIN_Y)
    return mini_cog.ASSET_URL, bounds, mini_cog.RESOLUTION, lambda: list(cleared)


def _zarr_asset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Asset:
    """The composite store, because its variables are the ones the real Zarr
    entry's standard visualisation names (``b04``, ``b03``, ``b02``)."""
    root = mini_zarr_composite.build_mini_zarr_composite(tmp_path / "mini.zarr")
    requests = mini_zarr_composite.serve_store(root, monkeypatch)
    side = mini_zarr_composite.SIZE * mini_zarr_composite.RESOLUTION_M
    bounds = (
        mini_zarr_composite.ORIGIN_X,
        mini_zarr_composite.ORIGIN_Y - side,
        mini_zarr_composite.ORIGIN_X + side,
        mini_zarr_composite.ORIGIN_Y,
    )
    # Every byte of a Zarr read is a gateway request, so the request log *is* the
    # list of fetched addresses — a stronger statement than the COG side can make,
    # where GDAL owns the socket (readers/cog.py docstring, KLAERUNGEN B8).
    href = f"{mini_zarr.BASE_URL}/{mini_zarr_composite.GROUP}"
    return href, bounds, mini_zarr_composite.RESOLUTION_M, lambda: [str(request.url) for request in requests]


def _stac_item(asset_key: str, href: str, bounds: tuple[float, ...], gsd: float) -> dict[str, Any]:
    """The item the synthetic source answers with.

    It carries a real footprint in WGS84, because the download route filters the
    given items by their geometry before it opens anything (M2-06) — an item
    without one is not a stand-in for a scene, it is a scene that is nowhere.
    """
    west, south, east, north = transform_bounds(CRS, WGS84_CRS, *bounds)
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {
        "id": ITEM_ID,
        "type": "Feature",
        "stac_version": "1.0.0",
        "collection": "synthetic",
        "bbox": [west, south, east, north],
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {
            # `datetime` and `grid:code` are what both entries group by
            # (earthx:viewer, D19), so the grouping key of the viewer can be
            # built from this item without a second fixture.
            "datetime": "2026-01-02T10:00:00Z",
            "grid:code": "MGRS-32TNS",
            # The Zarr store carries no CRS of its own (adr/0007 §3.4); for the
            # COG it is redundant and harmless.
            "proj:code": CRS,
            # M3-18's download size estimate (`plan_outputs`, F1) falls back here
            # for a Zarr composite key (`SR_10m:b04,b03,b02`), which never matches
            # the bare group name this item's own `assets` carries — the same
            # fallback a real EOPF item's `properties.gsd` is measured to serve
            # (plan §3), not this fixture's own workaround.
            "gsd": gsd,
        },
        "assets": {asset_key: {"href": href, "gsd": gsd}},
        "links": [],
    }


def _gateway_answering_search(
    config: DatasetConfig, item: dict[str, Any]
) -> tuple[Gateway, list[httpx.Request]]:
    """A gateway that answers any search with one page holding ``item``."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "stac_version": "1.0.0",
                "features": [item],
                "numberMatched": 1,
                "links": [],
            },
        )

    async def sleep(seconds: float) -> None:
        return None

    # The entry's own endpoint, so the adapter's real URL building is what gets
    # cleared — not a host this module invented.
    policy = Policy(allowed_hosts=frozenset({HOST, host_of(config.source.endpoint)}))
    return (
        Gateway(policy, transport=httpx.MockTransport(handler), resolve=mini_zarr.from_memory, sleep=sleep),
        seen,
    )


def _resolve_from_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both readers resolve from memory. ``tests/conftest.py`` forbids a real lookup."""
    for module in ("earthx.readers.cog", "earthx.readers.zarr_reader"):
        monkeypatch.setattr(
            f"{module}.check_url",
            lambda url, policy, **_: check_url(url, policy, resolve=mini_zarr.from_memory),
        )


def _aoi(bounds: tuple[float, ...]) -> dict[str, Any]:
    """A small box in the middle of the data, as WGS84 GeoJSON."""
    return _aoi_wgs84(transform_bounds(CRS, WGS84_CRS, *bounds))


def _aoi_wgs84(bounds: tuple[float, float, float, float]) -> dict[str, Any]:
    """The same shrink-to-quarter box as :func:`_aoi`, for bounds already in WGS84
    (the DEM branch, whose nominal cell needs no transform, M3-11b F3)."""
    west, south, east, north = bounds
    dx, dy = (east - west) / 4, (north - south) / 4
    left, right = west + dx, east - dx
    bottom, top = south + dy, north - dy
    return {
        "type": "Polygon",
        "coordinates": [[[left, bottom], [right, bottom], [right, top], [left, top], [left, bottom]]],
    }


def _covering_tile(bounds: tuple[float, ...], viewer: ViewerInfo | None) -> tuple[int, int, int]:
    """A web-mercator tile over the middle of the data, at a level the entry releases.

    The finest released level, which is what a client asks for once it has zoomed
    in (`earthx:viewer`, M2-10). The level has to come from the entry rather than
    from the grid: since M2-10 the tile route refuses anything outside the released
    range, so a chain that picked the first level fitting the synthetic store would
    prove nothing about the dataset — it would test a request no client may send.

    A tile that *contains* the centre always intersects the data, so the finest
    released level always answers; whether it is filled edge to edge is not what
    point 9 is about.
    """
    return _covering_tile_wgs84(transform_bounds(CRS, WGS84_CRS, *bounds), viewer)


def _covering_tile_wgs84(bounds: tuple[float, float, float, float], viewer: ViewerInfo | None) -> tuple[int, int, int]:
    """The same search as :func:`_covering_tile`, for bounds already in WGS84."""
    west, south, east, north = bounds
    centre = ((west + east) / 2, (south + north) / 2)
    lowest = WEB_MERCATOR_TMS.minzoom if viewer is None else viewer.min_zoom
    finest = WEB_MERCATOR_TMS.maxzoom if viewer is None else viewer.max_zoom
    for zoom in range(finest, lowest - 1, -1):
        tile = WEB_MERCATOR_TMS.tile(*centre, zoom)
        tile_bounds = WEB_MERCATOR_TMS.bounds(tile)
        if tile_bounds.left < east and tile_bounds.right > west:
            if tile_bounds.bottom < north and tile_bounds.top > south:
                return (zoom, tile.x, tile.y)
    raise AssertionError("no released level of the grid touches the synthetic store")


# --------------------------------------------------------------------------------
# Materialized entries (M3-11b): no search, an item built once from a tile name.
# --------------------------------------------------------------------------------


def _dem_item(
    name: str, bbox: tuple[float, float, float, float], *, config: DatasetConfig, gsd: float
) -> dict[str, Any]:
    """A DEM-shaped item, hand-built like :func:`_stac_item` is for a federated
    entry: no `datetime`, a `start_/end_datetime` period instead (M3-11b F1), and
    its geometry the tile's own *nominal* cell (F3) — large enough to contain the
    synthetic COG's real footprint (`mini_dem.BOUNDS` is exactly that cell), which
    is all the download route's AOI-intersection check needs; the actual pixel
    read goes through the file's own embedded CRS and transform, not this field.
    """
    west, south, east, north = bbox
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    href = f"{config.source.endpoint}/{name}/{name}.tif"
    return {
        "id": name,
        "type": "Feature",
        "stac_version": "1.0.0",
        "collection": config.dataset_id,
        "bbox": [west, south, east, north],
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {
            "datetime": None,
            "start_datetime": "2010-12-01T00:00:00Z",
            "end_datetime": "2015-01-31T23:59:59Z",
            "gsd": gsd,
            "proj:code": "EPSG:4326",
        },
        "assets": {"data": {"href": href, "gsd": gsd}},
        "links": [],
    }


def _gateway_answering_materialize(config: DatasetConfig, item: dict[str, Any]) -> tuple[Gateway, list[httpx.Request]]:
    """A gateway that answers `tileList.txt`, `blacklist.txt` and the bucket
    listing with exactly the one tile `item` names — enough for
    `adapters.materialize_items` to build that same item for real."""
    seen: list[httpx.Request] = []
    name = item["id"]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path.endswith("/tileList.txt"):
            return httpx.Response(200, content=f"{name}\r\n".encode(), headers={"etag": '"synthetic"'})
        if path.endswith("/blacklist.txt"):
            return httpx.Response(200, content=b"")
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            f"<CommonPrefixes><Prefix>{name}/</Prefix></CommonPrefixes>"
            "</ListBucketResult>"
        ).encode()
        return httpx.Response(200, content=body)

    async def sleep(seconds: float) -> None:
        return None

    policy = Policy(allowed_hosts=frozenset({HOST, host_of(config.source.endpoint)}))
    return (
        Gateway(policy, transport=httpx.MockTransport(handler), resolve=mini_zarr.from_memory, sleep=sleep),
        seen,
    )


def _build_materialized(
    config: DatasetConfig, render_asset: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Chain:
    if config.format is not DataFormat.COG:
        raise UnsupportedFormat(f"no synthetic materialize chain for format {config.format.value!r}")
    path = mini_dem.build_mini_dem(tmp_path / "mini_dem.tif")
    read_addresses = mini_dem.serve_dem(path, monkeypatch)
    # Only the host has to match what the real adapter builds an href from
    # (`config.source.endpoint`/`.tif`): `vsicurl_path` is monkeypatched above to
    # serve the local file regardless of the path it is asked for.
    synthetic = replace(config, source=replace(config.source, endpoint=f"https://{HOST}", asset_hosts=(HOST,)))
    item = _dem_item(mini_dem.TILE_NAME, mini_dem.BOUNDS, config=synthetic, gsd=30.0)
    gateway, searched = _gateway_answering_materialize(synthetic, item)
    _resolve_from_memory(monkeypatch)

    return Chain(
        config=synthetic,
        registry=DatasetRegistry((synthetic,)),
        item=item,
        render_asset=render_asset,
        aoi=_aoi_wgs84(mini_dem.BOUNDS),
        tile=_covering_tile_wgs84(mini_dem.BOUNDS, config.viewer),
        gateway=gateway,
        searched=searched,
        read_addresses=lambda: list(read_addresses),
    )
