"""The only code that fetches.

Every request is cleared by :func:`check_url` first, and it is the cleared
address the client connects to — the name is not resolved a second time, so
nothing can move between the check and the connection. The hostname still
carries the TLS handshake: it goes out as SNI and as the ``Host`` header, and
the certificate is therefore verified against the name, not the address
(``httpcore`` passes ``sni_hostname`` on as ``server_hostname``).

Redirects are followed here, not by ``httpx``, because every hop has to pass
the same check (KLAERUNGEN B8) — that is the point where ``pystac_client``
fails (adr/0005 §3.8).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from earthx.gateway.checks import CheckedUrl, check_url
from earthx.gateway.errors import (
    ResponseTooLarge,
    TooManyRedirects,
    UpstreamError,
    UpstreamTimeout,
    UpstreamUnreachable,
)
from earthx.gateway.policy import Policy
from earthx.gateway.resolver import resolve_host

LOGGER = logging.getLogger("earthx.gateway")

RETRY_STATUS = frozenset({429, 502, 503, 504})
REDIRECT_STATUS = frozenset({301, 302, 303, 307, 308})
MAX_ATTEMPTS = 3
BACKOFF_S = (0.5, 1.0, 2.0)
MAX_RETRY_AFTER_S = 10.0
EXCERPT_CHARS = 500


@dataclass(frozen=True)
class GatewayResponse:
    """What a source answered, with ``httpx`` left behind the seam."""

    status_code: int
    headers: Mapping[str, str]
    content: bytes

    def json(self) -> Any:
        return json.loads(self.content)


def _dumps(payload: Any) -> bytes:
    """Serialize a JSON body here, where the ``json`` module is not shadowed."""
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _query_digest(url: str) -> str:
    """A short hash of the query string, because the AOI must not reach a log."""
    query = httpx.URL(url).query
    return hashlib.sha256(query).hexdigest()[:12] if query else ""


class Gateway:
    """Fetches, and refuses. Holds no state that a restart would miss."""

    def __init__(
        self,
        policy: Policy,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        resolve: Callable[[str, int], tuple[str, ...]] = resolve_host,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._policy = policy
        self._resolve = resolve
        self._sleep = sleep
        # The per-host cap is the semaphore below, not httpx's global pool limit:
        # six connections per host is a rule about the source (adr/0005 §6).
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._client = httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            timeout=httpx.Timeout(
                connect=policy.connect_timeout_s,
                read=policy.read_timeout_s,
                write=policy.connect_timeout_s,
                pool=policy.connect_timeout_s,
            ),
        )

    async def __aenter__(self) -> Gateway:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> GatewayResponse:
        """Fetch a URL, assembling the query string here.

        ``/aggregate`` at Earth Search takes no POST (adr/0004 §3.1), so an AOI
        has to survive as a query parameter — up to the length limit, which
        ``check_url`` enforces before anything is sent.
        """
        return await self._send("GET", url, params=params, headers=headers)

    async def post_json(
        self,
        url: str,
        *,
        json: Any,
        headers: Mapping[str, str] | None = None,
        retry: bool = False,
    ) -> GatewayResponse:
        """POST a JSON body. Retried only if the caller says the call is safe to repeat."""
        body = _dumps(json)
        merged = {"content-type": "application/json", **(dict(headers) if headers else {})}
        return await self._send("POST", url, headers=merged, content=body, retry=retry)

    async def _send(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
        retry: bool = True,
    ) -> GatewayResponse:
        target = str(httpx.URL(url, params=params)) if params else url
        redirects = 0
        while True:
            checked = check_url(target, self._policy, resolve=self._resolve)
            async with self._semaphore(checked.host):
                response = await self._attempt(
                    method, checked, headers=headers, content=content, retry=retry, redirects=redirects
                )
            if response.status_code not in REDIRECT_STATUS:
                if response.status_code >= 400:
                    raise UpstreamError(response.status_code, response.content[:EXCERPT_CHARS].decode(errors="replace"))
                return response
            location = response.headers.get("location")
            if not location:
                raise UpstreamError(response.status_code, "redirect without a location")
            redirects += 1
            if redirects > self._policy.max_redirects:
                raise TooManyRedirects(self._policy.max_redirects)
            target = str(httpx.URL(checked.url).join(location))
            if response.status_code in {301, 302, 303} and content is not None:
                # Following this would drop the body and ask a different question:
                # `POST /search` reduced to `GET /search` comes back as an unfiltered
                # default page, which the caller cannot tell from its own results
                # (found reviewing M1-06). 307 and 308 keep method and body, so they
                # are followed as before.
                raise UpstreamError(response.status_code, "redirect would drop the request body")

    async def _attempt(
        self,
        method: str,
        checked: CheckedUrl,
        *,
        headers: Mapping[str, str] | None,
        content: bytes | None,
        retry: bool,
        redirects: int,
    ) -> GatewayResponse:
        may_retry = method == "GET" or retry
        for attempt in range(1, MAX_ATTEMPTS + 1):
            started = time.monotonic()
            last = attempt == MAX_ATTEMPTS
            try:
                response = await self._once(method, checked, headers=headers, content=content)
            except httpx.TimeoutException as exc:
                self._log(method, checked, started, attempt, redirects, error="timeout")
                if last or not may_retry:
                    raise UpstreamTimeout(f"{checked.host} did not answer in time") from exc
            except httpx.TransportError as exc:
                self._log(method, checked, started, attempt, redirects, error="transport")
                if last or not may_retry:
                    raise UpstreamUnreachable(f"{checked.host} could not be reached") from exc
            else:
                self._log(method, checked, started, attempt, redirects, response=response)
                if not (response.status_code in RETRY_STATUS and may_retry and not last):
                    return response
                await self._wait(attempt, response.headers.get("retry-after"))
                continue
            await self._wait(attempt, None)
        raise AssertionError("unreachable: the last attempt either returns or raises")

    async def _once(
        self,
        method: str,
        checked: CheckedUrl,
        *,
        headers: Mapping[str, str] | None,
        content: bytes | None,
    ) -> GatewayResponse:
        # A caller does not get to set Host: it decides which certificate the
        # connection is checked against, and that is the gateway's call.
        given = {name: value for name, value in (headers or {}).items() if name.lower() != "host"}
        request = self._client.build_request(
            method,
            httpx.URL(checked.url).copy_with(host=checked.address),
            content=content,
            headers={**given, "Host": checked.host},
            extensions={"sni_hostname": checked.host},
        )
        response = await self._client.send(request, stream=True)
        try:
            body = await self._read(response)
        finally:
            await response.aclose()
        return GatewayResponse(
            status_code=response.status_code,
            headers={name.lower(): value for name, value in response.headers.items()},
            content=body,
        )

    async def _read(self, response: httpx.Response) -> bytes:
        limit = self._policy.max_response_bytes
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            raise ResponseTooLarge(int(declared), limit)
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > limit:
                raise ResponseTooLarge(size, limit)
            chunks.append(chunk)
        return b"".join(chunks)

    def _semaphore(self, host: str) -> asyncio.Semaphore:
        if host not in self._semaphores:
            self._semaphores[host] = asyncio.Semaphore(self._policy.max_connections_per_host)
        return self._semaphores[host]

    async def _wait(self, attempt: int, retry_after: str | None) -> None:
        delay = BACKOFF_S[min(attempt, len(BACKOFF_S)) - 1] * random.uniform(0.8, 1.2)
        if retry_after and retry_after.strip().isdigit():
            delay = min(float(retry_after.strip()), MAX_RETRY_AFTER_S)
        await self._sleep(delay)

    def _log(
        self,
        method: str,
        checked: CheckedUrl,
        started: float,
        attempt: int,
        redirects: int,
        *,
        response: GatewayResponse | None = None,
        error: str | None = None,
    ) -> None:
        """One line per attempt. Never the query string — the AOI lives there."""
        LOGGER.info(
            "gateway request",
            extra={
                "gateway_host": checked.host,
                "gateway_method": method,
                "gateway_path": httpx.URL(checked.url).path,
                "gateway_query_sha": _query_digest(checked.url),
                "gateway_status": response.status_code if response else None,
                "gateway_bytes": len(response.content) if response else 0,
                "gateway_duration_ms": round((time.monotonic() - started) * 1000, 1),
                "gateway_attempt": attempt,
                "gateway_redirects": redirects,
                "gateway_error": error,
            },
        )
