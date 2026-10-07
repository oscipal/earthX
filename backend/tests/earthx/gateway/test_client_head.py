"""``Gateway.head`` walks the same road as ``get`` (M4-07b, Otto's condition).

A ``HEAD`` answers with headers only, so the one thing it must not share with
``get`` is the size limit of a body. Everything else — the allowlist, the scheme,
the port, the length, private addresses, every redirect hop, the cap per host, the
retry rules — is the same code, and each of those is tried here once more for
``HEAD`` so that a later change to ``_send`` cannot quietly give it a shortcut.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import httpx
import pytest

from earthx.gateway import AddressRejected, Policy, UrlRejected, UrlTooLong
from earthx.gateway.client import Gateway
from earthx.gateway.errors import TooManyRedirects, UpstreamError, UpstreamTimeout

HOST = "copernicus-dem-30m.s3.amazonaws.com"
OTHER = "cdn.example.org"
URL = f"https://{HOST}/Copernicus_DSM_COG_10_N47_00_E009_00_DEM/Copernicus_DSM_COG_10_N47_00_E009_00_DEM.tif"
POLICY = Policy(allowed_hosts=frozenset({HOST, OTHER}))

pytestmark = pytest.mark.anyio


def public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def build(handler: Callable, policy: Policy = POLICY, resolve: Callable = public) -> tuple[Gateway, list[float]]:
    delays: list[float] = []

    async def sleep(seconds: float) -> None:
        delays.append(seconds)

    return Gateway(policy, transport=httpx.MockTransport(handler), resolve=resolve, sleep=sleep), delays


def replies(*responses: httpx.Response) -> tuple[Callable, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return handler, seen


async def test_a_head_gives_the_headers_and_no_body() -> None:
    handler, seen = replies(httpx.Response(200, headers={"ETag": '"0e70a7b"', "Content-Length": "26000000"}))
    gateway, _ = build(handler)
    async with gateway:
        response = await gateway.head(URL)
    assert response.status_code == 200
    assert response.headers["etag"] == '"0e70a7b"'
    assert response.content == b""
    assert [request.method for request in seen] == ["HEAD"]


async def test_a_declared_length_over_the_body_limit_is_no_reason_to_refuse_a_head() -> None:
    """A whole COG's ``Content-Length`` is far over 8 MB; ``get`` refuses it, ``head`` must not."""
    declared = POLICY.max_response_bytes * 10
    handler, _ = replies(httpx.Response(200, headers={"Content-Length": str(declared), "ETag": '"x"'}))
    gateway, _ = build(handler)
    async with gateway:
        response = await gateway.head(URL)
    assert response.headers["content-length"] == str(declared)


async def test_a_head_on_a_host_off_the_allowlist_is_refused_before_anything_is_sent() -> None:
    handler, seen = replies(httpx.Response(200))
    gateway, _ = build(handler)
    async with gateway:
        with pytest.raises(UrlRejected):
            await gateway.head("https://evil.tld/a.tif")
    assert seen == []


@pytest.mark.parametrize(
    "url",
    [
        f"http://{HOST}/a.tif",
        f"https://{HOST}:8443/a.tif",
        f"https://user:secret@{HOST}/a.tif",
        f"https://evil-{HOST}/a.tif",
        "https://127.0.0.1/a.tif",
        "https://[::1]/a.tif",
    ],
)
async def test_a_head_refuses_what_a_get_refuses(url: str) -> None:
    handler, seen = replies(httpx.Response(200))
    gateway, _ = build(handler)
    async with gateway:
        with pytest.raises(UrlRejected):
            await gateway.head(url)
        with pytest.raises(UrlRejected):
            await gateway.get(url)
    assert seen == []


async def test_a_head_with_a_url_over_the_limit_is_refused() -> None:
    handler, seen = replies(httpx.Response(200))
    gateway, _ = build(handler)
    async with gateway:
        with pytest.raises(UrlTooLong):
            await gateway.head(URL + "?" + "a" * POLICY.max_url_bytes)
    assert seen == []


async def test_a_head_to_a_name_that_resolves_to_a_private_address_is_refused() -> None:
    def resolve(host: str, port: int) -> tuple[str, ...]:
        return ("10.0.0.1",)

    handler, seen = replies(httpx.Response(200))
    gateway, _ = build(handler, resolve=resolve)
    async with gateway:
        with pytest.raises(AddressRejected):
            await gateway.head(URL)
    assert seen == []


def redirecting(location: str, status: int = 302) -> tuple[Callable, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == HOST or request.headers["host"] == HOST:
            return httpx.Response(status, headers={"location": location})
        return httpx.Response(200, headers={"ETag": '"far"'})

    return handler, seen


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_a_redirect_within_the_allowlist_is_followed_as_a_head(status: int) -> None:
    handler, seen = redirecting(f"https://{OTHER}/a.tif", status=status)
    gateway, _ = build(handler)
    async with gateway:
        response = await gateway.head(URL)
    assert response.headers["etag"] == '"far"'
    assert [request.method for request in seen] == ["HEAD", "HEAD"]
    assert [request.headers["host"] for request in seen] == [HOST, OTHER]


@pytest.mark.parametrize("location", ["https://evil.tld/a.tif", f"http://{OTHER}/a.tif", f"https://{OTHER}:8443/a.tif"])
async def test_a_redirect_target_that_leaves_the_rules_is_refused(location: str) -> None:
    handler, seen = redirecting(location)
    gateway, _ = build(handler)
    async with gateway:
        with pytest.raises(UrlRejected):
            await gateway.head(URL)
    assert len(seen) == 1


async def test_a_redirect_target_with_a_private_address_is_refused() -> None:
    """Every hop is checked, not only the first: the second name resolves inside."""

    def resolve(host: str, port: int) -> tuple[str, ...]:
        return ("169.254.169.254",) if host == OTHER else ("93.184.216.34",)

    handler, seen = redirecting(f"https://{OTHER}/a.tif")
    gateway, _ = build(handler, resolve=resolve)
    async with gateway:
        with pytest.raises(AddressRejected):
            await gateway.head(URL)
    assert len(seen) == 1


async def test_a_redirect_loop_is_cut_off() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": URL})

    gateway, _ = build(handler)
    async with gateway:
        with pytest.raises(TooManyRedirects):
            await gateway.head(URL)


@pytest.mark.parametrize("status", [404, 410, 403, 405])
async def test_an_answer_from_400_up_is_an_upstream_error_with_its_status(status: int) -> None:
    handler, _ = replies(httpx.Response(status))
    gateway, _ = build(handler)
    async with gateway:
        with pytest.raises(UpstreamError) as error:
            await gateway.head(URL)
    assert error.value.status_code == status


async def test_a_503_is_tried_again_for_a_head_and_then_succeeds() -> None:
    handler, seen = replies(httpx.Response(503), httpx.Response(200, headers={"ETag": '"ok"'}))
    gateway, delays = build(handler)
    async with gateway:
        response = await gateway.head(URL)
    assert response.headers["etag"] == '"ok"'
    assert len(seen) == 2
    assert len(delays) == 1


async def test_a_head_the_caller_marks_unsafe_to_repeat_is_not_retried() -> None:
    handler, seen = replies(httpx.Response(503))
    gateway, _ = build(handler)
    async with gateway:
        with pytest.raises(UpstreamError) as error:
            await gateway.head(URL, retry=False)
    assert error.value.status_code == 503
    assert len(seen) == 1


async def test_a_source_that_does_not_answer_a_head_in_time_is_a_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow")

    gateway, _ = build(handler)
    async with gateway:
        with pytest.raises(UpstreamTimeout):
            await gateway.head(URL)


async def test_heads_share_the_cap_per_host_with_everything_else() -> None:
    live = 0
    peak = 0
    crowded = asyncio.Event()
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        if live >= POLICY.max_connections_per_host:
            crowded.set()
        await release.wait()
        live -= 1
        return httpx.Response(200, headers={"ETag": '"x"'})

    gateway, _ = build(handler)
    async with gateway:
        requests = [asyncio.create_task(gateway.head(URL)) for _ in range(12)]
        await asyncio.wait_for(crowded.wait(), timeout=2)
        await asyncio.sleep(0.05)
        assert live == POLICY.max_connections_per_host
        release.set()
        await asyncio.gather(*requests)
    assert peak == POLICY.max_connections_per_host


async def test_a_head_never_logs_its_query(caplog: pytest.LogCaptureFixture) -> None:
    handler, _ = replies(httpx.Response(200, headers={"ETag": '"x"'}))
    gateway, _ = build(handler)
    with caplog.at_level(logging.INFO, logger="earthx.gateway"):
        async with gateway:
            await gateway.head(URL + "?bbox=9.0,47.0,9.01,47.01")
    assert caplog.records
    assert "9.01,47.01" not in caplog.text
    assert "bbox" not in caplog.text


async def test_a_head_within_a_narrower_policy_refuses_a_redirect_to_a_host_outside_it() -> None:
    """``within`` only narrows: ``OTHER`` is on the gateway's own list, but not on this one's."""
    handler, seen = redirecting(f"https://{OTHER}/a.tif")
    gateway, _ = build(handler)
    async with gateway:
        with pytest.raises(UrlRejected):
            await gateway.head(URL, within=Policy(allowed_hosts=frozenset({HOST})))
    assert len(seen) == 1


async def test_a_head_within_a_policy_still_follows_a_redirect_inside_it() -> None:
    handler, seen = redirecting(f"https://{OTHER}/a.tif")
    gateway, _ = build(handler)
    async with gateway:
        response = await gateway.head(URL, within=Policy(allowed_hosts=frozenset({HOST, OTHER})))
    assert response.headers["etag"] == '"far"'
    assert len(seen) == 2


async def test_within_never_widens_the_gateways_own_policy() -> None:
    handler, seen = redirecting("https://evil.tld/a.tif")
    gateway, _ = build(handler)
    async with gateway:
        with pytest.raises(UrlRejected):
            await gateway.head(URL, within=Policy(allowed_hosts=frozenset({HOST, "evil.tld"})))
    assert len(seen) == 1


async def test_a_host_outside_within_is_refused_before_it_is_resolved() -> None:
    resolved: list[str] = []

    def resolve(host: str, port: int) -> tuple[str, ...]:
        resolved.append(host)
        return ("93.184.216.34",)

    handler, seen = replies(httpx.Response(200))
    gateway, _ = build(handler, resolve=resolve)
    async with gateway:
        with pytest.raises(UrlRejected):
            await gateway.head(f"https://{OTHER}/a.tif", within=Policy(allowed_hosts=frozenset({HOST})))
    assert resolved == [] and seen == []
