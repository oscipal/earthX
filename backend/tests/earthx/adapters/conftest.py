"""Shared pieces for the adapter tests: a gateway under test control, and fixtures.

No test here reaches the network: the transport is an ``httpx.MockTransport`` and the
resolver is handed in, exactly as in the gateway tests. The answers come from
``backend/tests/fixtures/earth_search/``, which is synthetic (see the README there).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.gateway import Policy
from earthx.gateway.client import Gateway

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "earth_search"

# The host of the one dataset in the registry, so the tests run against the real
# endpoint value rather than an invented one.
HOST = "earth-search.aws.element84.com"
POLICY = Policy(allowed_hosts=frozenset({HOST}))


def load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


@pytest.fixture
def dataset_id() -> str:
    return SENTINEL_2_L2A.dataset_id


def gateway_for(handler: Callable[[httpx.Request], httpx.Response]) -> Gateway:
    """A gateway whose transport, resolver and waiting are all under test control."""

    async def sleep(seconds: float) -> None:
        return None

    return Gateway(POLICY, transport=httpx.MockTransport(handler), resolve=_public, sleep=sleep)


def answering(*responses: httpx.Response) -> tuple[Gateway, list[httpx.Request]]:
    """A gateway that answers with the given responses in order, plus the requests seen."""
    seen: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return gateway_for(handler), seen


def body_of(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content)
