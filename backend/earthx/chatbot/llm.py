"""A narrow client for the Anthropic Messages API, sent through the gateway (plan m7a F3).

No SDK: it opens connections itself and follows redirects unchecked, the reason
adr/0005 rule IV keeps ``pystac_client`` out. One POST per call, through
``Gateway.post_json`` like every other outgoing request (KLAERUNGEN B8).

The model name and the key are handed in by the caller, which reads them from the
environment; neither is written in code, and the key never reaches a log or an error.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from earthx.gateway import Gateway, GatewayError, UpstreamError

MESSAGES_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
MAX_TOKENS = 16000
EXCERPT_CHARS = 300


class ModelError(RuntimeError):
    """The model could not be asked, or answered with something unusable."""


class ChatModel(Protocol):
    """One request to a language model: the transcript in, the next assistant message out."""

    async def create(
        self,
        *,
        system: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
        allow_tools: bool,
    ) -> dict[str, Any]: ...


class AnthropicMessages:
    """``ChatModel`` over ``POST /v1/messages``."""

    def __init__(self, gateway: Gateway, *, api_key: str, model: str, url: str = MESSAGES_URL) -> None:
        if not api_key or not model:
            raise ValueError("the Messages API needs a key and a model name")
        self._gateway = gateway
        self._headers = {"x-api-key": api_key, "anthropic-version": API_VERSION}
        self._model = model
        self._url = url

    async def create(
        self,
        *,
        system: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
        allow_tools: bool,
    ) -> dict[str, Any]:
        body = {
            "model": self._model,
            "max_tokens": MAX_TOKENS,
            "system": system,
            "messages": list(messages),
            # The tools stay declared even when none may be called: the API refuses a
            # transcript with tool_use blocks but no tool definitions.
            "tools": list(tools),
            "tool_choice": {"type": "auto" if allow_tools else "none"},
        }
        try:
            # Asking again changes nothing but the bill, so 429 and 5xx are retried.
            response = await self._gateway.post_json(self._url, json=body, headers=self._headers, retry=True)
        except UpstreamError as error:
            # The API's error body names the problem (unknown model, bad key) and
            # never repeats the key.
            detail = f": {error.excerpt[:EXCERPT_CHARS]}" if error.excerpt else ""
            raise ModelError(f"the language model answered {error.status_code}{detail}") from None
        except GatewayError as error:
            raise ModelError(f"the language model could not be reached: {type(error).__name__}") from None
        try:
            message = response.json()
        except ValueError:
            raise ModelError("the language model answered with something that is not JSON") from None
        if not isinstance(message, dict) or not isinstance(message.get("content"), list):
            raise ModelError("the language model answered without a content list")
        return message
