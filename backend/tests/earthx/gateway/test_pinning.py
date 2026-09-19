"""The connection goes to the checked address; the certificate still has to fit the name.

Resolving the name a second time would reopen the gap the check just closed
(the plan, F2). Connecting to the address alone would be worse than the gap:
a certificate checked against ``93.184.216.34`` proves nothing. So the address
is what we connect to, and the name is what TLS is verified against.
"""

from __future__ import annotations

import ssl

import httpcore
import httpx
import pytest

from earthx.gateway import Policy
from earthx.gateway.client import Gateway

HOST = "earth-search.aws.element84.com"
ADDRESS = "93.184.216.34"
POLICY = Policy(allowed_hosts=frozenset({HOST}))

pytestmark = pytest.mark.anyio


def resolve(host: str, port: int) -> tuple[str, ...]:
    return (ADDRESS,)


async def test_the_address_is_connected_and_the_name_is_kept_for_tls() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url_host"] = request.url.host
        seen["host_header"] = request.headers["host"]
        seen["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(200, json={})

    async with Gateway(POLICY, transport=httpx.MockTransport(handler), resolve=resolve) as gateway:
        await gateway.get(f"https://{HOST}/v1/search")

    assert seen == {"url_host": ADDRESS, "host_header": HOST, "sni": HOST}


class _Stream(httpcore.AsyncNetworkStream):
    """Answers one canned HTTP/1.1 response and writes down how TLS was started."""

    def __init__(self, record: dict[str, object]) -> None:
        self._record = record
        self._reply = b"HTTP/1.1 200 OK\r\ncontent-length: 2\r\n\r\n{}"

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        reply, self._reply = self._reply[:max_bytes], self._reply[max_bytes:]
        return reply

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self._record.setdefault("request", b"")
        self._record["request"] = self._record["request"] + buffer  # type: ignore[operator]

    async def aclose(self) -> None:
        return None

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.AsyncNetworkStream:
        self._record["server_hostname"] = server_hostname
        self._record["check_hostname"] = ssl_context.check_hostname
        self._record["verify_mode"] = ssl_context.verify_mode
        return self

    def get_extra_info(self, info: str) -> object:
        return None


class _Backend(httpcore.AsyncNetworkBackend):
    def __init__(self, record: dict[str, object]) -> None:
        self._record = record

    async def connect_tcp(self, host: str, port: int, *args: object, **kwargs: object) -> httpcore.AsyncNetworkStream:
        self._record["connected_to"] = (host, port)
        return _Stream(self._record)


async def test_tls_is_verified_against_the_name_although_the_address_is_connected() -> None:
    """Runs through the real httpx and httpcore, only the socket is a double.

    This is the assumption the pinning rests on, so it is asserted rather than
    believed: httpcore takes `sni_hostname` as `server_hostname`, and that is
    the name `ssl` checks the certificate against.
    """
    record: dict[str, object] = {}
    transport = httpx.AsyncHTTPTransport()
    transport._pool = httpcore.AsyncConnectionPool(
        ssl_context=httpx.create_ssl_context(),
        network_backend=_Backend(record),
    )

    async with Gateway(POLICY, transport=transport, resolve=resolve) as gateway:
        response = await gateway.get(f"https://{HOST}/v1/search")

    assert response.status_code == 200
    assert record["connected_to"] == (ADDRESS, 443)
    assert record["server_hostname"] == HOST
    assert record["check_hostname"] is True
    assert record["verify_mode"] == ssl.CERT_REQUIRED
    assert f"host: {HOST}".encode() in bytes(record["request"]).lower()  # type: ignore[arg-type]


async def test_a_caller_cannot_set_the_host_header_itself() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.headers.get_list("host")
        return httpx.Response(200, json={})

    async with Gateway(POLICY, transport=httpx.MockTransport(handler), resolve=resolve) as gateway:
        await gateway.get(f"https://{HOST}/v1/search", headers={"Host": "evil.tld", "accept": "application/json"})

    assert seen["host"] == [HOST]
