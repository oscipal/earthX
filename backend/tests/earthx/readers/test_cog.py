"""The address a COG is read from passed the gateway — or there is no address.

Part (b) of KLAERUNGEN B8, which M1-03 could only prepare because there was no
reader yet: every URL handed to rasterio has passed ``check_url`` first. The two
tests that carry it are :func:`test_an_address_outside_the_allowlist_is_refused`
and :func:`test_a_plain_string_is_not_a_dataset` — one for the way in, one for
the way around it.
"""

from __future__ import annotations

import pytest

from earthx.gateway import Policy, UrlRejected, check_url
from earthx.readers.cog import AssetPath, CogReader, asset_path

HOST = "assets.example.invalid"
HREF = f"https://{HOST}/collection/item/TCI.tif"


@pytest.fixture
def policy() -> Policy:
    return Policy(allowed_hosts=frozenset({HOST}))


@pytest.fixture
def without_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve from memory. The refusals below happen before any lookup; the two
    tests that get as far as an address would otherwise need one."""
    monkeypatch.setattr(
        "earthx.readers.cog.check_url",
        # `**_` swallows the resolver `asset_path` hands on (M2-14): these tests
        # answer from memory whatever the caller would have resolved with.
        lambda url, policy, **_: check_url(url, policy, resolve=lambda host, port: ("93.184.216.34",)),
    )


def path(href: str, policy: Policy) -> AssetPath:
    return asset_path(href, policy, dataset_id="test-dataset", item_id="test-item", asset="visual")


def test_a_cleared_address_becomes_a_vsicurl_path(policy: Policy, without_dns: None) -> None:
    assert path(HREF, policy) == f"/vsicurl/{HREF}"


def test_the_path_remembers_what_it_is(policy: Policy, without_dns: None) -> None:
    """`access` keys the statistics cache on these three, instead of parsing the URL."""
    built = path(HREF, policy)
    assert (built.dataset_id, built.item_id, built.asset) == ("test-dataset", "test-item", "visual")


@pytest.mark.parametrize(
    "href",
    [
        # The host of the older Sentinel-2 collection: reachable, and still not ours
        # (adr/0006 §3.7). This is the failure the registry's asset_hosts prevents.
        "https://sentinel-cogs.s3.us-west-2.amazonaws.com/x/TCI.tif",
        "https://attacker.example.invalid/x.tif",
        # Same name as the allowed host, one label short of it.
        "https://evil-assets.example.invalid/x.tif",
    ],
)
def test_an_address_outside_the_allowlist_is_refused(href: str, policy: Policy) -> None:
    with pytest.raises(UrlRejected):
        path(href, policy)


@pytest.mark.parametrize(
    "href",
    [
        f"http://{HOST}/x.tif",  # adr/0006 §5 "Zu Frage 6": https only
        f"s3://{HOST}/x.tif",
        f"https://user:secret@{HOST}/x.tif",
        f"https://{HOST}:8443/x.tif",
        # Neither the cloud metadata address nor its decimal spelling is a name.
        "https://169.254.169.254/latest/meta-data/",
        "https://2852039166/x.tif",
    ],
)
def test_an_address_that_is_not_a_plain_https_name_is_refused(href: str, policy: Policy) -> None:
    with pytest.raises(UrlRejected):
        path(href, policy)


def test_a_plain_string_is_not_a_dataset() -> None:
    """The way around the check: hand the reader an address that never saw one.

    It has to fail at the reader too, not only at the dependency that normally builds
    the path — otherwise the guarantee would rest on nobody ever wiring it differently.
    """
    with pytest.raises(TypeError, match="AssetPath"):
        CogReader("/vsicurl/https://attacker.example.invalid/x.tif")


def test_a_looks_like_a_path_string_is_not_one_either() -> None:
    with pytest.raises(TypeError, match="AssetPath"):
        CogReader("https://attacker.example.invalid/x.tif")


def test_the_caller_s_resolver_is_the_one_that_is_asked(policy: Policy) -> None:
    """``asset_path`` hands ``resolve`` on to ``check_url`` rather than resolving
    itself — that argument is how the tiler gets its cached resolver in (M2-14)."""
    asked: list[str] = []

    def resolve(host: str, port: int) -> tuple[str, ...]:
        asked.append(host)
        return ("93.184.216.34",)

    path = asset_path(HREF, policy, dataset_id="d", item_id="i", asset="visual", resolve=resolve)
    assert path == f"/vsicurl/{HREF}"
    assert asked == [HOST]
