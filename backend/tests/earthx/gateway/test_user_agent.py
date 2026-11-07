"""One User-Agent per instance, on every request, never set by a caller (M5-18 §3.1, adr/0025 F9)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from earthx.gateway import DEFAULT_USER_AGENT, USER_AGENT_ENV, Policy, user_agent_from_env
from earthx.gateway.client import Gateway
from earthx.gateway.gdal import gdal_options
from earthx.gateway.policy import product_token

HOST = "catalog.example.org"
OTHER = "mirror.example.org"
URL = f"https://{HOST}/collections"
OWN = "EarthX-test/0.0 (+https://example.invalid)"

pytestmark = pytest.mark.anyio


def public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def build(handler: Callable, policy: Policy) -> Gateway:
    async def sleep(seconds: float) -> None:
        return None

    return Gateway(policy, transport=httpx.MockTransport(handler), resolve=public, sleep=sleep)


BAD_VALUES = [
    pytest.param(" ", id="only-space"),
    pytest.param(" EarthX/0.1", id="leading-space"),
    pytest.param("EarthX/0.1\r\nX-Injected: 1", id="header-injection"),
    pytest.param("EarthX/0.1\tTab", id="tab"),
    pytest.param("EarthX/0.1 (+https://exämple.org)", id="non-ascii"),
    pytest.param("E" * 257, id="too-long"),
    pytest.param("EarthX/0.1 (person@example.org)", id="mail-address"),
]


class TestValue:
    def test_unset_or_empty_gives_the_default(self) -> None:
        assert user_agent_from_env({}) == DEFAULT_USER_AGENT
        assert user_agent_from_env({USER_AGENT_ENV: "  "}) == DEFAULT_USER_AGENT

    def test_the_variable_names_the_instance(self) -> None:
        assert user_agent_from_env({USER_AGENT_ENV: OWN}) == OWN

    def test_a_policy_takes_the_instance_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(USER_AGENT_ENV, OWN)
        assert Policy(allowed_hosts=frozenset({HOST})).user_agent == OWN

    def test_the_default_itself_passes_the_check(self) -> None:
        assert Policy(allowed_hosts=frozenset(), user_agent=DEFAULT_USER_AGENT).user_agent == DEFAULT_USER_AGENT

    @pytest.mark.parametrize("value", BAD_VALUES[1:])
    def test_a_bad_variable_stops_the_start_without_repeating_the_value(self, value: str) -> None:
        with pytest.raises(ValueError) as raised:
            user_agent_from_env({USER_AGENT_ENV: value})
        assert USER_AGENT_ENV in str(raised.value)
        assert value.strip() not in str(raised.value)

    @pytest.mark.parametrize("value", [*BAD_VALUES, pytest.param("", id="empty")])
    def test_a_bad_value_builds_no_policy(self, value: str) -> None:
        with pytest.raises(ValueError):
            Policy(allowed_hosts=frozenset(), user_agent=value)

    def test_a_bad_variable_builds_no_policy_either(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(USER_AGENT_ENV, "EarthX\nX: 1")
        with pytest.raises(ValueError):
            Policy(allowed_hosts=frozenset())

    @pytest.mark.parametrize(
        ("value", "token"),
        [(DEFAULT_USER_AGENT, "EarthX"), ("OwnCrawler", "OwnCrawler"), ("Own Crawler/1", "Own")],
    )
    def test_the_product_token_is_the_name_before_slash_or_space(self, value: str, token: str) -> None:
        assert product_token(value) == token


class TestOnTheWire:
    @pytest.mark.parametrize("method", ["get", "head", "post_json"])
    async def test_every_method_carries_it(self, method: str) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={})

        async with build(handler, Policy(allowed_hosts=frozenset({HOST}), user_agent=OWN)) as gateway:
            if method == "post_json":
                await gateway.post_json(URL, json={})
            else:
                await getattr(gateway, method)(URL)
        assert seen[0].headers["user-agent"] == OWN

    @pytest.mark.parametrize("name", ["User-Agent", "user-agent", "USER-AGENT"])
    async def test_a_caller_cannot_set_it(self, name: str) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={})

        async with build(handler, Policy(allowed_hosts=frozenset({HOST}), user_agent=OWN)) as gateway:
            await gateway.get(URL, headers={name: "curl/8.0", "Accept": "application/json"})
        assert seen[0].headers.get_list("user-agent") == [OWN]
        assert seen[0].headers["accept"] == "application/json"

    async def test_retries_and_redirect_hops_carry_it(self) -> None:
        seen: list[httpx.Request] = []
        answers = [
            httpx.Response(503),
            httpx.Response(302, headers={"location": f"https://{OTHER}/collections"}),
            httpx.Response(200, json={}),
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return answers.pop(0)

        policy = Policy(allowed_hosts=frozenset({HOST, OTHER}), user_agent=OWN)
        async with build(handler, policy) as gateway:
            await gateway.get(URL)
        assert [request.headers["host"] for request in seen] == [HOST, HOST, OTHER]
        assert {request.headers["user-agent"] for request in seen} == {OWN}

    def test_gdal_sends_the_same_value(self) -> None:
        options = gdal_options(Policy(allowed_hosts=frozenset({HOST}), user_agent=OWN))
        assert options["GDAL_HTTP_USERAGENT"] == OWN
