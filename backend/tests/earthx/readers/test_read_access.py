"""The worker's read factory: allowlist from the recipe's addresses, GDAL options for the process (adr/0014 §8)."""

from __future__ import annotations

import pytest

from earthx.gateway.gdal import gdal_options
from earthx.gateway.policy import Policy
from earthx.readers import AssetRejected
from earthx.readers.access import GDAL_CACHEMAX_MB, process_gdal_options, read_access_for


class TestProcessGdalOptions:
    def test_are_the_gateway_options_plus_the_block_cache(self) -> None:
        options = dict(process_gdal_options())
        assert options.pop("GDAL_CACHEMAX") == str(GDAL_CACHEMAX_MB) == "64"
        assert options == gdal_options(Policy(allowed_hosts=frozenset()))

    def test_do_not_depend_on_any_allowlist(self) -> None:
        assert gdal_options(Policy(allowed_hosts=frozenset({"a.example"}))) == gdal_options(
            Policy(allowed_hosts=frozenset())
        )

    def test_cannot_be_changed_by_a_caller(self) -> None:
        with pytest.raises(TypeError):
            process_gdal_options()["GDAL_CACHEMAX"] = "4096"  # type: ignore[index]


class TestReadAccessFor:
    def test_the_allowlist_is_exactly_the_hosts_of_the_addresses(self) -> None:
        access = read_access_for(
            [
                "https://Data.Example.org/a/B04.tif",
                "https://data.example.org/a/B08.tif",
                "https://other.example.net/store.zarr/r10m",
            ]
        )
        assert access.policy.allowed_hosts == frozenset({"data.example.org", "other.example.net"})
        assert not access.policy.allows_host("example.org")
        assert dict(access.gdal_options) == dict(process_gdal_options())

    def test_each_run_gets_its_own_resolver(self) -> None:
        first = read_access_for(["https://data.example.org/a.tif"])
        second = read_access_for(["https://data.example.org/a.tif"])
        assert first.resolve is not second.resolve

    @pytest.mark.parametrize(
        "href",
        ["not an address", "https:///no-host.tif", "https://127.0.0.1/a.tif", "https://[::1]/a.tif"],
    )
    def test_an_address_without_a_valid_host_is_refused_without_repeating_it(self, href: str) -> None:
        with pytest.raises(AssetRejected) as caught:
            read_access_for(["https://data.example.org/a.tif", href])
        assert href not in str(caught.value)
        assert "127.0.0.1" not in str(caught.value)

    def test_no_address_at_all_is_refused(self) -> None:
        with pytest.raises(AssetRejected):
            read_access_for([])
