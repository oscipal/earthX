"""The two halves together: a URL is cleared only if its addresses are, too."""

from __future__ import annotations

import pytest

from earthx.gateway import AddressRejected, Policy, UrlRejected, UrlTooLong, check_url

SOURCE = "earth-search.aws.element84.com"
POLICY = Policy(allowed_hosts=frozenset({SOURCE}))


def resolver(*addresses: str, calls: list[str] | None = None):
    def resolve(host: str, port: int) -> tuple[str, ...]:
        if calls is not None:
            calls.append(host)
        return addresses

    return resolve


def test_a_cleared_url_carries_the_address_to_connect_to() -> None:
    checked = check_url(f"https://{SOURCE}/v1/search", POLICY, resolve=resolver("93.184.216.34", "8.8.8.8"))
    assert (checked.host, checked.port, checked.address) == (SOURCE, 443, "93.184.216.34")
    assert checked.addresses == ("93.184.216.34", "8.8.8.8")


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1"])
def test_an_allowed_name_pointing_inwards_is_still_refused(address: str) -> None:
    with pytest.raises(AddressRejected):
        check_url(f"https://{SOURCE}/v1", POLICY, resolve=resolver(address))


def test_a_name_with_one_public_and_one_private_address_is_refused() -> None:
    with pytest.raises(AddressRejected):
        check_url(f"https://{SOURCE}/v1", POLICY, resolve=resolver("93.184.216.34", "127.0.0.1"))


def test_a_url_refused_on_sight_never_reaches_the_resolver() -> None:
    calls: list[str] = []
    with pytest.raises(UrlRejected):
        check_url("https://evil.tld/v1", POLICY, resolve=resolver("93.184.216.34", calls=calls))
    assert calls == []


def test_an_aoi_too_large_for_the_query_string_never_reaches_the_resolver() -> None:
    calls: list[str] = []
    url = f"https://{SOURCE}/v1/aggregate?intersects=" + "x" * 9000
    with pytest.raises(UrlTooLong) as raised:
        check_url(url, POLICY, resolve=resolver("93.184.216.34", calls=calls))
    assert raised.value.limit == 8192
    assert calls == []


def test_the_reason_never_repeats_the_query_string() -> None:
    aoi = "POLYGON((7.1234 51.5678, 7.1235 51.5679))"
    with pytest.raises(UrlRejected) as raised:
        check_url(f"http://{SOURCE}/v1/search?intersects={aoi}", POLICY, resolve=resolver("93.184.216.34"))
    assert "51.5678" not in str(raised.value)
