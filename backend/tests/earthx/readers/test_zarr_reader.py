"""Tile, statistic and AOI crop out of a synthetic Zarr store — every byte through the gateway.

The acceptance criteria of M2-09a, in the order the task names them:

* a tile, a statistic and a crop come out of the synthetic store;
* every byte read demonstrably passes `gateway`;
* an unknown variable or an unknown group ends in a defined error rather than a
  traceback.

The store is the one `mini_zarr.py` writes, the transport is the one
`conftest.py` puts inside the gateway, and ``tests/conftest.py`` forbids a socket
throughout: nothing here touches EOPF or any other source.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import numpy
import pytest
import xarray
from rasterio.warp import transform_bounds
from rio_tiler.constants import WEB_MERCATOR_TMS, WGS84_CRS
from zarr.abc.store import OffsetByteRequest, RangeByteRequest, SuffixByteRequest
from zarr.core.buffer import default_buffer_prototype

from earthx.gateway import Policy, UrlRejected
from earthx.readers.zarr_reader import (
    GatewayStore,
    MissingCrs,
    StoreNotReadable,
    UnknownGroup,
    UnknownVariable,
    ZarrAsset,
    ZarrReader,
    split_asset_href,
    split_asset_key,
    zarr_asset,
)
from tests.earthx.readers import mini_zarr
from tests.earthx.readers.mini_zarr import BASE_URL, HOST, POLICY, from_memory

DATASET = "synthetic-zarr"
ITEM = "SYNTH_20260102T100000"


def asset(
    group: str = "r20m",
    variable: str = "b04",
    *,
    crs: str | None = mini_zarr.ITEM_CRS,
    policy: Policy = POLICY,
) -> ZarrAsset:
    """What the catalogue hands the reader: an item's asset href plus its ``proj:code``."""
    return zarr_asset(
        f"{BASE_URL}/{group}/{variable}",
        policy,
        dataset_id=DATASET,
        item_id=ITEM,
        asset=variable,
        crs=crs,
        resolve=from_memory,
    )


def covering_tile(zoom: int) -> tuple[int, int, int]:
    """A web-mercator tile over the middle of the store, at ``zoom``."""
    west, south, east, north = transform_bounds(
        mini_zarr.ITEM_CRS, WGS84_CRS, *mini_zarr.store_bounds()
    )
    tile = WEB_MERCATOR_TMS.tile((west + east) / 2, (south + north) / 2, zoom)
    return tile.z, tile.x, tile.y


def aoi_over_the_store() -> dict[str, object]:
    """A GeoJSON polygon over the middle quarter of the store, in WGS84."""
    west, south, east, north = transform_bounds(
        mini_zarr.ITEM_CRS, WGS84_CRS, *mini_zarr.store_bounds()
    )
    left, right = west + (east - west) / 4, east - (east - west) / 4
    bottom, top = south + (north - south) / 4, north - (north - south) / 4
    return {
        "type": "Polygon",
        "coordinates": [[[left, bottom], [right, bottom], [right, top], [left, top], [left, bottom]]],
    }


class TestTheThreeThingsTheTaskAsksFor:
    """Kachel, Statistik und Zuschnitt aus dem synthetischen Zarr."""

    def test_a_tile_comes_out_of_the_store(self, requests: list[httpx.Request]) -> None:
        with ZarrReader(asset()) as reader:
            z, x, y = covering_tile(reader.maxzoom)
            image = reader.tile(x, y, z)
        assert image.data.shape[1:] == (256, 256)
        assert image.data.any()
        assert requests

    def test_the_statistic_is_the_statistic_of_the_data(self, requests: list[httpx.Request]) -> None:
        """Measured against the array itself, not against a remembered number."""
        with ZarrReader(asset(group="r60m", variable="b08")) as reader:
            statistics = reader.preview().statistics()
        written = mini_zarr.resolution_group(mini_zarr.GROUPS["r60m"])["b08"]
        for band in statistics.values():
            assert band.min >= float(written.min())
            assert band.max <= float(written.max())

    def test_a_crop_is_the_part_of_the_store_the_aoi_covers(self, requests: list[httpx.Request]) -> None:
        with ZarrReader(asset()) as reader:
            whole = reader.preview()
            crop = reader.feature(aoi_over_the_store())
        assert crop.data.any()
        # A quarter of the width in each direction, give or take the reprojection.
        assert 0 < crop.width < whole.width

    def test_the_crop_path_of_the_download_takes_a_zarr_asset_too(
        self, requests: list[httpx.Request]
    ) -> None:
        """M2-06's crop is reader-agnostic; this is the proof rather than the hope."""
        from earthx.access.download import crop_asset

        image = crop_asset(ZarrReader, (asset(),), aoi_over_the_store())
        assert image.data.any()


class TestEveryByteGoesThroughTheGateway:
    """The M2-09a acceptance criterion that carries KLAERUNGEN B8 into this reader."""

    def test_the_store_counts_exactly_the_requests_the_gateway_made(
        self, requests: list[httpx.Request]
    ) -> None:
        store = GatewayStore(BASE_URL, POLICY, resolve=from_memory)
        dataset = xarray.open_zarr(store, group="r20m", consolidated=True, zarr_format=3, chunks=None)
        try:
            float(dataset["b04"].isel(time=0, y=0, x=0))
        finally:
            dataset.close()
            store.close()
        assert store.request_count == len(requests) > 0
        # The gateway connects to the address it checked and carries the name in the
        # `Host` header (M1-03): nothing can move between the check and the socket.
        assert {request.headers["host"] for request in requests} == {HOST}

    def test_an_address_outside_the_allowlist_never_becomes_an_asset(self) -> None:
        """The refusal happens when the asset is built, before a single chunk is asked for."""
        with pytest.raises(UrlRejected):
            asset(policy=Policy(allowed_hosts=frozenset({"elsewhere.example.invalid"})))

    def test_a_host_the_policy_drops_later_still_cannot_be_read(
        self, requests: list[httpx.Request]
    ) -> None:
        """`check_url` runs again inside the gateway, per key, not once at the start."""
        store = GatewayStore(BASE_URL, Policy(allowed_hosts=frozenset({"elsewhere.example.invalid"})))
        with pytest.raises(UrlRejected):
            xarray.open_zarr(store, group="r20m", consolidated=True, zarr_format=3, chunks=None)
        assert requests == []

    def test_the_reader_refuses_a_plain_string(self) -> None:
        """The way around the catalogue, closed the same way `CogReader` closes it."""
        with pytest.raises(TypeError, match="ZarrAsset"):
            ZarrReader(f"{BASE_URL}/r20m/b04")


class TestTheStoreItself:
    """The store is the part that talks to the source; its contract is checked directly."""

    @pytest.fixture
    def store(self, requests: list[httpx.Request]) -> GatewayStore:
        return GatewayStore(BASE_URL, POLICY, resolve=from_memory)

    @pytest.fixture
    def key(self, store_root: Path) -> str:
        return "r20m/b04/c/0/0/0"

    @pytest.mark.anyio
    async def test_a_whole_key_comes_back_whole(self, store: GatewayStore, key: str, store_root: Path) -> None:
        buffer = await store.get(key, default_buffer_prototype())
        assert buffer is not None
        assert buffer.to_bytes() == (store_root / key).read_bytes()

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        ("request_", "expected_header", "slice_"),
        [
            (RangeByteRequest(2, 10), "bytes=2-9", slice(2, 10)),
            (OffsetByteRequest(4), "bytes=4-", slice(4, None)),
            (SuffixByteRequest(6), "bytes=-6", slice(-6, None)),
        ],
    )
    async def test_the_three_byte_ranges_become_the_one_http_header(
        self,
        store: GatewayStore,
        key: str,
        store_root: Path,
        requests: list[httpx.Request],
        request_: object,
        expected_header: str,
        slice_: slice,
    ) -> None:
        """Mandatory, not an optimisation: a sharded store would otherwise send the shard."""
        buffer = await store.get(key, default_buffer_prototype(), request_)
        assert requests[-1].headers["range"] == expected_header
        assert buffer is not None
        assert buffer.to_bytes() == (store_root / key).read_bytes()[slice_]

    @pytest.mark.anyio
    async def test_a_key_the_source_does_not_have_is_none_rather_than_an_error(
        self, store: GatewayStore
    ) -> None:
        """zarr probes for keys that need not exist; a 404 is an answer, not a failure."""
        assert await store.get("r20m/b04/c/9/9/9", default_buffer_prototype()) is None

    @pytest.mark.anyio
    async def test_existence_is_not_a_download(
        self, store: GatewayStore, key: str, requests: list[httpx.Request]
    ) -> None:
        assert await store.exists(key) is True
        assert requests[-1].headers["range"] == "bytes=0-0"
        assert await store.exists("r20m/b04/c/9/9/9") is False

    @pytest.mark.anyio
    async def test_the_store_does_not_write(self, store: GatewayStore) -> None:
        """A reader that could write to a source is a reader nobody should point anywhere."""
        assert store.read_only is True
        assert store.supports_writes is False
        assert store.supports_deletes is False
        with pytest.raises(NotImplementedError):
            await store.set("anything", default_buffer_prototype().buffer.from_bytes(b""))
        with pytest.raises(NotImplementedError):
            await store.delete("anything")

    def test_the_store_does_not_list(self, store: GatewayStore) -> None:
        """The names come from the catalogue; the store answers with consolidated metadata."""
        assert store.supports_listing is False
        with pytest.raises(NotImplementedError, match="consolidated"):
            store.list()
        with pytest.raises(NotImplementedError, match="consolidated"):
            store.list_dir("")
        with pytest.raises(NotImplementedError, match="consolidated"):
            store.list_prefix("")

    def test_the_store_never_repeats_the_address_it_reads(self, store: GatewayStore) -> None:
        """projektplan.md 7: no source address in a log line or an error text."""
        assert HOST not in repr(store)


class TestWhatTheRealSourceDoesDifferently:
    """The four deviations `mini_zarr.py` copies, each one read back."""

    @pytest.mark.parametrize("group", list(mini_zarr.GROUPS))
    def test_every_resolution_group_is_a_level_of_its_own(
        self, group: str, requests: list[httpx.Request]
    ) -> None:
        """Resolution groups instead of `multiscales` (§3.4): the level is the address."""
        with ZarrReader(asset(group=group)) as reader:
            assert reader.width == int(mini_zarr.FINEST_SIZE * 10.0 / mini_zarr.GROUPS[group])
            assert reader.bounds == pytest.approx(mini_zarr.store_bounds())

    def test_the_crs_comes_from_the_item_because_the_store_has_none(
        self, requests: list[httpx.Request]
    ) -> None:
        with ZarrReader(asset()) as reader:
            assert reader.crs.to_string() == mini_zarr.ITEM_CRS

    def test_without_a_crs_from_either_side_the_reader_refuses_to_guess(
        self, requests: list[httpx.Request]
    ) -> None:
        with pytest.raises(MissingCrs, match="proj:code"):
            ZarrReader(asset(crs=None))

    def test_a_proj_code_that_is_not_a_crs_is_a_defined_error_too(
        self, requests: list[httpx.Request]
    ) -> None:
        with pytest.raises(MissingCrs, match="not a usable"):
            ZarrReader(asset(crs="EPSG:not-a-number"))

    @pytest.mark.parametrize("variable", list(mini_zarr.VARIABLES))
    def test_a_group_carries_several_variables_and_the_asset_picks_one(
        self, variable: str, requests: list[httpx.Request]
    ) -> None:
        with ZarrReader(asset(variable=variable)) as reader:
            assert reader.input.name == variable

    def test_the_time_axis_arrives_as_the_bands_of_the_image(
        self, requests: list[httpx.Request]
    ) -> None:
        """A dimension rather than an item property — the case §6 point 6 asks for."""
        with ZarrReader(asset()) as reader:
            assert len(reader.band_descriptions) == len(mini_zarr.TIMES)
            assert reader.band_descriptions[0].startswith(mini_zarr.TIMES[0][:10])

    def test_a_window_reads_fewer_chunks_than_the_whole_level(
        self, requests: list[httpx.Request]
    ) -> None:
        """Small chunks, so a window costs the chunks it touches and not the level."""
        with ZarrReader(asset(group="r10m")) as reader:
            numpy.asarray(reader.input.isel(time=0, y=slice(0, 16), x=slice(0, 16)))
        windowed = len(requests)
        requests.clear()
        with ZarrReader(asset(group="r10m")) as reader:
            numpy.asarray(reader.input)
        assert windowed < len(requests)


class TestTheDefinedErrors:
    """An unknown group or variable ends in a named failure, never in a traceback."""

    def test_a_group_the_item_advertises_and_the_store_does_not_have(
        self, requests: list[httpx.Request]
    ) -> None:
        """Exactly how `TCI_10m` fails in the real source (§3.5)."""
        with pytest.raises(UnknownGroup, match="does not have"):
            ZarrReader(asset(group=mini_zarr.MISSING_GROUP))

    def test_an_unknown_variable_in_a_group_that_exists(self, requests: list[httpx.Request]) -> None:
        with pytest.raises(UnknownVariable, match="b99"):
            ZarrReader(asset(variable="b99"))

    def test_the_errors_name_the_dataset_and_the_item_but_never_the_address(
        self, requests: list[httpx.Request]
    ) -> None:
        with pytest.raises(UnknownVariable) as raised:
            ZarrReader(asset(variable="b99"))
        assert DATASET in str(raised.value) and ITEM in str(raised.value)
        assert HOST not in str(raised.value)

    def test_a_store_without_consolidated_metadata_is_refused_rather_than_crawled(
        self, tmp_path: Path, serve: object
    ) -> None:
        """Listing is off by decision (§3.10), so the reader has to say so itself."""
        plain = tmp_path / "mini.zarr"
        mini_zarr.resolution_group(20.0).to_zarr(plain, group="r20m", mode="a", zarr_format=3, consolidated=False)
        serve(plain)  # type: ignore[operator]
        with pytest.raises(StoreNotReadable, match="listing"):
            ZarrReader(asset())

    @pytest.mark.parametrize(
        "href",
        [
            # No store: nothing says where the consolidated metadata is.
            f"https://{HOST}/products/mini/r20m/b04",
            # A store and no variable to read out of it.
            f"{BASE_URL}/",
            "b04",
            "",
        ],
    )
    def test_an_href_that_does_not_name_a_store_and_a_variable_is_refused(self, href: str) -> None:
        with pytest.raises(UrlRejected):
            zarr_asset(href, POLICY, dataset_id=DATASET, item_id=ITEM, asset="b04", resolve=from_memory)


class TestGroupAddressing:
    """M2-09b-2, plan §10 F2: a Zarr asset whose href names a *group*, not a
    variable — the sentinel-2-l2a-zarr3 shape (§3.2), where the tile URL's asset
    key carries the variable after the registry's ``ZarrInfo.variable_separator``.
    """

    def test_split_asset_href_with_a_variable_keeps_the_whole_tail_as_the_group(self) -> None:
        store_url, group, variable = split_asset_href(f"{BASE_URL}/r20m", variable="b04")
        assert store_url == BASE_URL
        assert group == "r20m"
        assert variable == "b04"

    def test_split_asset_href_with_a_variable_and_no_store_segment_is_refused(self) -> None:
        with pytest.raises(UrlRejected):
            split_asset_href("https://store.example.invalid/products/mini/r20m", variable="b04")

    def test_zarr_asset_reads_the_group_the_href_names_and_the_variable_given_separately(self) -> None:
        built = zarr_asset(
            f"{BASE_URL}/r20m", POLICY, dataset_id=DATASET, item_id=ITEM, asset="SR_20m:b04",
            resolve=from_memory, variable="b04",
        )
        assert built.group == "r20m"
        assert built.variable == "b04"

    @pytest.mark.parametrize(
        ("asset_key", "separator", "expected"),
        [
            ("SR_10m:b04", ":", ("SR_10m", "b04")),
            ("visual", None, ("visual", None)),
        ],
    )
    def test_split_asset_key(self, asset_key: str, separator: str | None, expected: tuple[str, str | None]) -> None:
        assert split_asset_key(asset_key, separator) == expected

    @pytest.mark.parametrize(
        ("asset_key", "separator"),
        [
            ("SR_10m", ":"),  # no separator in the key at all
            ("SR_10m:", ":"),  # nothing after the separator
            (":b04", ":"),  # nothing before it
        ],
    )
    def test_split_asset_key_refuses_a_key_it_cannot_split(self, asset_key: str, separator: str | None) -> None:
        with pytest.raises(UrlRejected):
            split_asset_key(asset_key, separator)

    def test_zipped_product_still_fails_the_same_way_with_group_addressing(self) -> None:
        """§3.2: `zipped_product`'s href ends `.zarr.zip`, not `.zarr` — no store
        segment for either addressing convention to find (plan §6, point 3)."""
        with pytest.raises(UrlRejected):
            zarr_asset(
                f"{BASE_URL}.zip", POLICY, dataset_id=DATASET, item_id=ITEM, asset="zipped_product",
                resolve=from_memory, variable="b04",
            )


def test_the_reader_never_stacks_the_bands_of_a_group() -> None:
    """`to_dataarray`/`to_array` materialise every variable — 1.5 GB in the measurement.

    A rule about the source rather than about a call site, so it is checked over the
    module's text: an implementation that reaches for the convenient function fails
    here rather than in a container (adr/0007 §12.11, M2-09b's conditions).
    """
    import earthx.readers.zarr_reader as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    body = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    for forbidden in (".to_dataarray(", ".to_array("):
        assert forbidden not in body
