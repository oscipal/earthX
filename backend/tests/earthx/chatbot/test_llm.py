"""The Messages API client against a synthetic API, without a network and without a real key."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from earthx.chatbot.llm import API_VERSION, MESSAGES_URL, AnthropicMessages, ModelError
from earthx.gateway import Gateway, Policy, host_of

pytestmark = pytest.mark.anyio

FAKE_KEY = "test-key-not-a-secret"
MODEL = "test-model"
POLICY = Policy(allowed_hosts=frozenset({host_of(MESSAGES_URL)}))
TOOLS = [{"name": "search_collections", "input_schema": {"type": "object"}}]
MESSAGE = {"role": "assistant", "content": [{"type": "text", "text": "Hello"}], "stop_reason": "end_turn"}


def public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


async def no_sleep(_: float) -> None:
    return None


def build(
    handler: Callable[[httpx.Request], httpx.Response], policy: Policy = POLICY
) -> tuple[AnthropicMessages, Gateway]:
    gateway = Gateway(policy, transport=httpx.MockTransport(handler), resolve=public, sleep=no_sleep)
    return AnthropicMessages(gateway, api_key=FAKE_KEY, model=MODEL), gateway


async def ask(client: AnthropicMessages, *, allow_tools: bool = True) -> dict[str, Any]:
    return await client.create(
        system="be brief", messages=[{"role": "user", "content": "hi"}], tools=TOOLS, allow_tools=allow_tools
    )


async def test_it_posts_model_system_messages_and_tools_with_the_key_in_a_header() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=MESSAGE)

    client, gateway = build(handler)
    async with gateway:
        assert await ask(client) == MESSAGE
    request = seen[0]
    body = json.loads(request.content)
    # The gateway connects to the address it checked and names the host in the header.
    assert request.method == "POST" and request.url.path == "/v1/messages"
    assert request.headers["host"] == host_of(MESSAGES_URL)
    assert request.headers["x-api-key"] == FAKE_KEY
    assert request.headers["anthropic-version"] == API_VERSION
    assert FAKE_KEY not in request.content.decode()
    assert body["model"] == MODEL and body["system"] == "be brief"
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert body["tools"] == TOOLS and body["tool_choice"] == {"type": "auto"}


async def test_without_tools_allowed_they_stay_declared_but_cannot_be_chosen() -> None:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=MESSAGE)

    client, gateway = build(handler)
    async with gateway:
        await ask(client, allow_tools=False)
    assert bodies[0]["tools"] == TOOLS and bodies[0]["tool_choice"] == {"type": "none"}


@pytest.mark.parametrize("status", [400, 401, 404, 500])
async def test_an_error_status_becomes_a_model_error_without_the_key(status: int) -> None:
    error = {"type": "error", "error": {"type": "invalid_request_error", "message": "model: not found"}}
    client, gateway = build(lambda request: httpx.Response(status, json=error))
    async with gateway:
        with pytest.raises(ModelError) as raised:
            await ask(client)
    assert str(status) in str(raised.value)
    assert FAKE_KEY not in str(raised.value)
    assert raised.value.__cause__ is None


async def test_rate_limits_are_retried() -> None:
    answers = iter([httpx.Response(429), httpx.Response(200, json=MESSAGE)])
    client, gateway = build(lambda request: next(answers))
    async with gateway:
        assert await ask(client) == MESSAGE


async def test_an_unreachable_api_becomes_a_model_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client, gateway = build(handler)
    async with gateway:
        with pytest.raises(ModelError, match="could not be reached"):
            await ask(client)


async def test_a_host_outside_the_allowlist_is_never_asked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the gateway must refuse before sending")

    client, gateway = build(handler, Policy(allowed_hosts=frozenset({"stac.example.invalid"})))
    async with gateway:
        with pytest.raises(ModelError, match="UrlRejected"):
            await ask(client)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"<html>not json</html>"),
        httpx.Response(200, json=["a", "list"]),
        httpx.Response(200, json={"role": "assistant"}),
        httpx.Response(200, json={"content": "a string"}),
    ],
)
async def test_an_unusable_answer_becomes_a_model_error(response: httpx.Response) -> None:
    client, gateway = build(lambda request: response)
    async with gateway:
        with pytest.raises(ModelError):
            await ask(client)


@pytest.mark.parametrize(("api_key", "model"), [("", MODEL), (FAKE_KEY, "")])
async def test_a_missing_key_or_model_is_refused_up_front(api_key: str, model: str) -> None:
    async with Gateway(POLICY) as gateway:
        with pytest.raises(ValueError):
            AnthropicMessages(gateway, api_key=api_key, model=model)
