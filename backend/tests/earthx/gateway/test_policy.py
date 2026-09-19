"""The rules that need no network: host spelling, allowlist, URL shape, length."""

from __future__ import annotations

import pytest

from earthx.gateway import ALLOWED_HOSTS_ENV, Policy, UrlRejected, UrlTooLong, normalize_host, policy_from_env
from earthx.gateway.policy import inspect_url

SOURCE = "earth-search.aws.element84.com"


def policy(*hosts: str, **limits: object) -> Policy:
    return Policy(allowed_hosts=frozenset(hosts), **limits)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("EARTH-Search.AWS.Element84.com", SOURCE),
        (f"{SOURCE}.", SOURCE),
        ("  " + SOURCE + "  ", SOURCE),
        ("bücher.example", "xn--bcher-kva.example"),
        ("xn--bcher-kva.example", "xn--bcher-kva.example"),
    ],
)
def test_a_host_has_exactly_one_spelling(given: str, expected: str) -> None:
    assert normalize_host(given) == expected


@pytest.mark.parametrize(
    "host",
    [
        "",
        "   ",
        "127.0.0.1",  # IP literal
        "169.254.169.254",  # cloud metadata
        "::1",
        "[::1]",
        "0177.0.0.1",  # octal spelling of a loopback address
        "2130706433",  # decimal spelling of a loopback address
        "localhost",  # single label, and not a name the allowlist can hold
        "example..com",
        "-bad.example",
        "bad-.example",
        "a" * 64 + ".example",
        "exa mple.com",
    ],
)
def test_a_host_that_is_not_a_plain_name_is_rejected(host: str) -> None:
    with pytest.raises(UrlRejected):
        normalize_host(host)


@pytest.mark.parametrize("host", [SOURCE, "sub." + SOURCE, "a.b." + SOURCE])
def test_the_host_and_its_subdomains_are_allowed(host: str) -> None:
    assert policy(SOURCE).allows_host(host) is True


@pytest.mark.parametrize(
    "host",
    [
        "evil" + SOURCE,  # the endswith weakness the prototype still carries
        "xevil-search.aws.element84.com",
        SOURCE + ".evil.tld",
        "element84.com",
        "aws.element84.com",
    ],
)
def test_a_lookalike_host_is_not_allowed(host: str) -> None:
    assert policy(SOURCE).allows_host(host) is False


def test_an_empty_allowlist_allows_nothing() -> None:
    assert policy().allows_host(SOURCE) is False


def test_allowlist_entries_are_normalized_like_every_other_host() -> None:
    assert policy("EARTH-Search.AWS.Element84.com.").allows_host(SOURCE) is True


def test_an_allowlist_entry_that_is_not_a_name_is_refused_at_build_time() -> None:
    with pytest.raises(UrlRejected):
        policy("10.0.0.1")


@pytest.mark.parametrize(
    "url",
    [
        f"http://{SOURCE}/v1",
        f"ftp://{SOURCE}/v1",
        "file:///etc/passwd",
        f"//{SOURCE}/v1",
        f"htt+ps://{SOURCE}/v1",
        f"https://user:pass@{SOURCE}/v1",
        f"https://{SOURCE}:8443/v1",
        f"https://{SOURCE}:notaport/v1",
        f"https://evil{SOURCE}/v1",
        "https:///v1",
    ],
)
def test_a_url_that_breaks_a_rule_never_becomes_a_request(url: str) -> None:
    with pytest.raises(UrlRejected):
        inspect_url(url, policy(SOURCE))


def test_a_url_that_keeps_every_rule_passes() -> None:
    parts = inspect_url(f"https://{SOURCE}/v1/search?limit=10", policy(SOURCE))
    assert (parts.host, parts.port) == (SOURCE, 443)


def test_a_url_just_under_the_limit_passes_and_just_over_it_does_not() -> None:
    base = f"https://{SOURCE}/v1/aggregate?intersects="
    limit = 8192
    inspect_url(base + "x" * (limit - len(base)), policy(SOURCE))
    with pytest.raises(UrlTooLong) as raised:
        inspect_url(base + "x" * (limit - len(base) + 1), policy(SOURCE))
    assert (raised.value.length, raised.value.limit) == (limit + 1, limit)


def test_a_url_to_a_forbidden_host_is_rejected_for_the_host_not_its_length() -> None:
    with pytest.raises(UrlRejected):
        inspect_url("https://evil.tld/v1?q=" + "x" * 9000, policy(SOURCE))


def test_an_unset_environment_variable_allows_nothing() -> None:
    assert policy_from_env({}).allowed_hosts == frozenset()


def test_the_environment_variable_is_a_comma_separated_list() -> None:
    built = policy_from_env({ALLOWED_HOSTS_ENV: f" {SOURCE} , Example.COM ,, "})
    assert built.allowed_hosts == frozenset({SOURCE, "example.com"})
