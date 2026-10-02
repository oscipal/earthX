"""`readers` refuses an asset address with exactly one class (adr/0011 §6.4).

`access` and `processing` may not import `gateway`, so they can only tell a refused
address from any other failure if `readers` raises its own class for it — for every
reason ``check_url`` has, not only for ``UrlRejected``.
"""

from __future__ import annotations

import pytest

from earthx.gateway import AddressRejected, GatewayError, Policy, UrlRejected
from earthx.readers import AssetRejected
from earthx.readers.cog import asset_path
from earthx.readers.zarr_reader import split_asset_href, split_asset_key, zarr_asset

HOST = "assets.example.invalid"
POLICY = Policy(allowed_hosts=frozenset({HOST}))
COG_HREF = f"https://{HOST}/secret-path/item/TCI.tif"
ZARR_HREF = f"https://{HOST}/secret-path/product.zarr/r20m/b04"


def public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def private(host: str, port: int) -> tuple[str, ...]:
    return ("10.0.0.1",)


def open_cog(href: str, resolve=public):
    return asset_path(href, POLICY, dataset_id="d", item_id="i", asset="visual", resolve=resolve)


def open_zarr(href: str, resolve=public):
    return zarr_asset(href, POLICY, dataset_id="d", item_id="i", asset="b04", resolve=resolve)


@pytest.mark.parametrize("opener", [open_cog, open_zarr])
class TestEveryRefusalOfCheckUrlIsAssetRejected:
    def test_a_host_outside_the_allowlist(self, opener) -> None:
        href = COG_HREF if opener is open_cog else ZARR_HREF
        with pytest.raises(AssetRejected) as caught:
            opener(href.replace(HOST, "elsewhere.example.invalid"))
        assert type(caught.value.__cause__) is UrlRejected

    def test_a_host_that_resolves_to_a_private_address(self, opener) -> None:
        """``AddressRejected`` is no ``UrlRejected``; before M4-01a it passed through as is."""
        href = COG_HREF if opener is open_cog else ZARR_HREF
        with pytest.raises(AssetRejected) as caught:
            opener(href, resolve=private)
        assert isinstance(caught.value.__cause__, AddressRejected)

    def test_the_refusal_names_no_path(self, opener) -> None:
        href = COG_HREF if opener is open_cog else ZARR_HREF
        with pytest.raises(AssetRejected) as caught:
            opener(href, resolve=private)
        assert "secret-path" not in str(caught.value)

    def test_it_is_still_caught_as_before(self, opener) -> None:
        href = COG_HREF if opener is open_cog else ZARR_HREF
        with pytest.raises(UrlRejected):
            opener(href.replace(HOST, "elsewhere.example.invalid"))
        with pytest.raises(GatewayError):
            opener(href, resolve=private)


def test_a_cleared_address_still_opens() -> None:
    assert open_cog(COG_HREF) == f"/vsicurl/{COG_HREF}"
    assert open_zarr(ZARR_HREF).variable == "b04"


@pytest.mark.parametrize("key", ["SR_10m", "SR_10m:", ":b04", ""])
def test_a_key_without_a_variable_is_asset_rejected(key: str) -> None:
    with pytest.raises(AssetRejected):
        split_asset_key(key, ":")


@pytest.mark.parametrize("variable", [None, "b04"])
def test_an_href_without_a_store_is_asset_rejected(variable: str | None) -> None:
    with pytest.raises(AssetRejected):
        split_asset_href(f"https://{HOST}/products/mini/r20m", variable=variable)


def test_an_href_without_a_variable_is_asset_rejected() -> None:
    with pytest.raises(AssetRejected):
        open_zarr(f"https://{HOST}/product.zarr/")
