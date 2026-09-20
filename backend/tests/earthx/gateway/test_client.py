"""What the client does with limits, errors, redirects and repetition."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable

import httpx
import pytest

from earthx.gateway import AddressRejected, Policy, UrlRejected, UrlTooLong
from earthx.gateway.client import Gateway, GatewayResponse
from earthx.gateway.errors import ResponseTooLarge, TooManyRedirects, UpstreamError, UpstreamTimeout

HOST = "earth-search.aws.element84.com"
OTHER = "cdn.example.org"
URL = f"https://{HOST}/v1/search"
POLICY = Policy(allowed_hosts=frozenset({HOST, OTHER}))

pytestmark = pytest.mark.anyio


def public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def build(handler: Callable, policy: Policy = POLICY, resolve: Callable = public) -> tuple[Gateway, list[float]]:
    """A gateway whose transport, resolver and waiting are all under test control."""
    delays: list[float] = []

    async def sleep(seconds: float) -> None:
        delays.append(seconds)

    return Gateway(policy, transport=httpx.MockTransport(handler), resolve=resolve, sleep=sleep), delays


def replies(*responses: httpx.Response) -> tuple[Callable, list[httpx.Request]]:
    """A handler that answers with the given responses in order, and keeps the requests."""
    seen: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return handler, seen


async def test_a_plain_get_comes_back_as_a_gateway_response() -> None:
    handler, _ = replies(httpx.Response(200, json={"type": "FeatureCollection"}))
    gateway, _delays = build(handler)
    async with gateway:
        response = await gateway.get(URL)
    assert isinstance(response, GatewayResponse)
    assert response.status_code == 200
    assert response.json() == {"type": "FeatureCollection"}


async def test_the_query_string_is_assembled_by_the_gateway() -> None:
    handler, seen = replies(httpx.Response(200, json={}))
    gateway, _ = build(handler)
    async with gateway:
        await gateway.get(f"https://{HOST}/v1/aggregate", params={"intersects": "POLYGON", "limit": 10})
    assert dict(seen[0].url.params) == {"intersects": "POLYGON", "limit": "10"}


async def test_a_declared_body_over_the_limit_is_refused() -> None:
    handler, _ = replies(httpx.Response(200, content=b"x" * 3000))
    gateway, _ = build(handler, policy=Policy(allowed_hosts=frozenset({HOST}), max_response_bytes=2000))
    async with gateway:
        with pytest.raises(ResponseTooLarge) as raised:
            await gateway.get(URL)
    assert raised.value.limit == 2000


async def test_a_body_that_only_grows_while_reading_is_refused_too() -> None:
    async def body() -> AsyncIterator[bytes]:
        for _ in range(5):
            yield b"x" * 1000

    handler, _ = replies(httpx.Response(200, content=body()))
    gateway, _ = build(handler, policy=Policy(allowed_hosts=frozenset({HOST}), max_response_bytes=2000))
    async with gateway:
        with pytest.raises(ResponseTooLarge):
            await gateway.get(URL)


@pytest.mark.parametrize("status", [400, 404, 422])
async def test_an_answer_we_do_not_pass_on_keeps_its_status_code(status: int) -> None:
    handler, _ = replies(httpx.Response(status, text="datetime value is invalid"))
    gateway, _ = build(handler)
    async with gateway:
        with pytest.raises(UpstreamError) as raised:
            await gateway.get(URL)
    assert raised.value.status_code == status
    assert "datetime value is invalid" in raised.value.excerpt


async def test_a_304_is_an_answer_not_an_error() -> None:
    handler, _ = replies(httpx.Response(304, headers={"etag": 'W/"abc"'}))
    gateway, _ = build(handler)
    async with gateway:
        response = await gateway.get(URL)
    assert response.status_code == 304


async def test_a_503_is_tried_again_and_then_succeeds() -> None:
    handler, seen = replies(httpx.Response(503), httpx.Response(200, json={}))
    gateway, delays = build(handler)
    async with gateway:
        response = await gateway.get(URL)
    assert (response.status_code, len(seen), len(delays)) == (200, 2, 1)


async def test_three_failures_give_up_and_keep_the_status() -> None:
    handler, seen = replies(httpx.Response(503))
    gateway, delays = build(handler)
    async with gateway:
        with pytest.raises(UpstreamError) as raised:
            await gateway.get(URL)
    assert (raised.value.status_code, len(seen), len(delays)) == (503, 3, 2)


async def test_retry_after_is_obeyed_but_capped() -> None:
    handler, _ = replies(httpx.Response(429, headers={"retry-after": "120"}), httpx.Response(200, json={}))
    gateway, delays = build(handler)
    async with gateway:
        await gateway.get(URL)
    assert delays == [10.0]


async def test_a_post_is_not_repeated_unless_the_caller_allows_it() -> None:
    handler, seen = replies(httpx.Response(503))
    gateway, _ = build(handler)
    async with gateway:
        with pytest.raises(UpstreamError):
            await gateway.post_json(URL, json={"limit": 10})
    assert len(seen) == 1


async def test_a_post_the_caller_calls_safe_is_repeated() -> None:
    handler, seen = replies(httpx.Response(503), httpx.Response(200, json={}))
    gateway, _ = build(handler)
    async with gateway:
        await gateway.post_json(URL, json={"limit": 10}, retry=True)
    assert len(seen) == 2


async def test_a_source_that_does_not_answer_in_time_is_a_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow")

    gateway, delays = build(handler)
    async with gateway:
        with pytest.raises(UpstreamTimeout):
            await gateway.get(URL)
    assert len(delays) == 2


def redirecting(location: str, status: int = 302) -> tuple[Callable, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/v1/search":
            return httpx.Response(status, headers={"location": location})
        return httpx.Response(200, json={"hop": request.url.path})

    return handler, seen


async def test_a_redirect_within_the_allowlist_is_followed() -> None:
    handler, seen = redirecting(f"https://{OTHER}/v1/items")
    gateway, _ = build(handler)
    async with gateway:
        response = await gateway.get(URL)
    assert response.json() == {"hop": "/v1/items"}
    assert [request.headers["host"] for request in seen] == [HOST, OTHER]


@pytest.mark.parametrize("location", ["https://evil.tld/v1", f"http://{OTHER}/v1", f"https://{OTHER}:8443/v1"])
async def test_a_redirect_that_leaves_the_rules_is_refused(location: str) -> None:
    handler, _ = redirecting(location)
    gateway, _ = build(handler)
    async with gateway:
        with pytest.raises(UrlRejected):
            await gateway.get(URL)


async def test_a_redirect_to_a_private_address_is_refused() -> None:
    def resolve(host: str, port: int) -> tuple[str, ...]:
        return ("10.0.0.1",) if host == OTHER else ("93.184.216.34",)

    handler, _ = redirecting(f"https://{OTHER}/v1/items")
    gateway, _ = build(handler, resolve=resolve)
    async with gateway:
        with pytest.raises(AddressRejected):
            await gateway.get(URL)


async def test_a_redirect_chain_past_the_limit_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": f"https://{HOST}/v1/search"})

    gateway, _ = build(handler)
    async with gateway:
        with pytest.raises(TooManyRedirects):
            await gateway.get(URL)


@pytest.mark.parametrize("status", [301, 302, 303])
async def test_a_redirect_that_would_drop_the_body_is_refused(status: int) -> None:
    """Changed while reviewing M1-06, where the consequence became visible.

    Turning `POST /search` into a GET drops the search body, and the source answers
    with an unfiltered default page. The caller cannot tell that from its own
    results, so it gets an error instead of a plausible wrong answer.
    """
    handler, seen = redirecting(f"https://{OTHER}/v1/items", status=status)
    gateway, _ = build(handler)
    async with gateway:
        with pytest.raises(UpstreamError) as error:
            await gateway.post_json(URL, json={"limit": 10})
    assert error.value.status_code == status
    assert [request.method for request in seen] == ["POST"]


@pytest.mark.parametrize("status", [301, 302, 303])
async def test_a_get_still_follows_these(status: int) -> None:
    """The refusal above is about a body, not about the status code.

    Assets on S3 and CDNs routinely answer a GET with a 302, and a GET has nothing
    that following could drop — so nothing changes for the reader path (M2).
    """
    handler, seen = redirecting(f"https://{OTHER}/v1/items", status=status)
    gateway, _ = build(handler)
    async with gateway:
        response = await gateway.get(URL)
    assert response.json() == {"hop": "/v1/items"}
    assert [request.method for request in seen] == ["GET", "GET"]


@pytest.mark.parametrize("status", [307, 308])
async def test_a_redirect_that_keeps_the_body_is_followed(status: int) -> None:
    """307 and 308 carry method and body over, so nothing is lost by following."""
    handler, seen = redirecting(f"https://{OTHER}/v1/items", status=status)
    gateway, _ = build(handler)
    async with gateway:
        response = await gateway.post_json(URL, json={"limit": 10})
    assert response.json() == {"hop": "/v1/items"}
    assert [request.method for request in seen] == ["POST", "POST"]
    assert json.loads(seen[1].content) == {"limit": 10}


async def test_only_six_requests_reach_one_host_at_a_time() -> None:
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
        return httpx.Response(200, json={})

    gateway, _ = build(handler)
    async with gateway:
        requests = [asyncio.create_task(gateway.get(URL)) for _ in range(12)]
        await asyncio.wait_for(crowded.wait(), timeout=2)
        await asyncio.sleep(0.05)  # long enough for a seventh to slip through, if it could
        assert live == POLICY.max_connections_per_host
        release.set()
        await asyncio.gather(*requests)
    assert peak == POLICY.max_connections_per_host


async def test_the_aoi_never_reaches_the_log(caplog: pytest.LogCaptureFixture) -> None:
    handler, _ = replies(httpx.Response(200, json={}))
    gateway, _ = build(handler)
    with caplog.at_level(logging.INFO, logger="earthx.gateway"):
        async with gateway:
            await gateway.get(f"https://{HOST}/v1/aggregate", params={"intersects": "POINT(7.1234 51.5678)"})

    written = " ".join(str(value) for record in caplog.records for value in vars(record).values())
    assert "51.5678" not in written
    assert "7.1234" not in written
    assert caplog.records[0].gateway_host == HOST
    assert caplog.records[0].gateway_query_sha


class TestTheQueryStringStaysOurRefusal:
    """A long query string is refused in our words, not in httpx's (M2-05).

    The coverage aggregation puts an AOI into the query string, because
    ``/aggregate`` takes no POST (adr/0004 §3.1). adr/0004 §3.4 tells the caller to
    simplify and say so when the URL gets too long — which only works if the refusal
    it catches is ``UrlTooLong`` in every case, including the ones ``httpx`` would
    refuse on its own before ``check_url`` ever runs.
    """

    async def test_a_query_string_over_the_policy_limit_is_refused(self) -> None:
        handler, seen = replies(httpx.Response(200, json={}))
        gateway, _delays = build(handler)
        async with gateway:
            with pytest.raises(UrlTooLong):
                await gateway.get(URL, params={"intersects": "x" * (POLICY.max_url_bytes + 100)})
        assert seen == []

    async def test_a_query_string_over_the_httpx_limit_is_refused_the_same_way(self) -> None:
        """Without the conversion this raises ``httpx.InvalidURL`` through the seam."""
        handler, seen = replies(httpx.Response(200, json={}))
        gateway, _delays = build(handler)
        async with gateway:
            with pytest.raises(UrlTooLong) as raised:
                await gateway.get(URL, params={"intersects": "x" * 100_000})
        assert seen == []
        assert raised.value.limit == POLICY.max_url_bytes
        assert raised.value.length > raised.value.limit

    async def test_no_refusal_repeats_the_query_string(self) -> None:
        """projektplan.md 7, point 6: the AOI belongs in neither a log nor a traceback."""
        handler, _ = replies(httpx.Response(200, json={}))
        gateway, _delays = build(handler)
        area = "5.25,45.75,15.25,55.75" + "x" * 100_000
        async with gateway:
            with pytest.raises(UrlTooLong) as raised:
                await gateway.get(URL, params={"intersects": area})
        assert "45.75" not in str(raised.value)

    async def test_a_malformed_url_is_not_called_too_long(self) -> None:
        """httpx raises the same error for a bad host as for a long URL.

        Calling both "too long" would send the coverage adapter of adr/0004 §3.4 off
        shrinking an AOI that was never the problem, so the two are told apart.
        """
        handler, seen = replies(httpx.Response(200, json={}))
        gateway, _delays = build(handler)
        async with gateway:
            with pytest.raises(UrlRejected) as raised:
                await gateway.get("https://earth-search.aws.element84.com:notanumber/v1", params={"a": "b"})
        assert seen == []
        # Pins the refusal to the assembly step: check_url would word it differently.
        assert "cannot be assembled" in str(raised.value)
