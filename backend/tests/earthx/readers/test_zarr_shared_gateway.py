"""The Zarr stores of a process share one gateway, and so one cap per host (M5-36 §4.2, M5-35 §2.1).

Before, every store built a gateway of its own: four Zarr scenes of one mosaic tile could put four times the cap on
one host. The stores here read the synthetic store of `mini_zarr.py` through the reader's gateway seam.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from zarr.core.buffer import default_buffer_prototype

from earthx.gateway import CachingResolver, Policy
from earthx.gateway.client import Gateway
from earthx.readers import zarr_reader
from earthx.readers.zarr_reader import GatewayStore, close_shared_gateways, shared_gateway
from tests.earthx.readers.mini_zarr import BASE_URL, HOST, POLICY, _respond, from_memory

pytestmark = pytest.mark.anyio
KEY = "r20m/b04/c/0/0/0"


@pytest.fixture(autouse=True)
def no_shared_gateway_left():
    close_shared_gateways()
    yield
    close_shared_gateways()


class Peak:
    def __init__(self) -> None:
        self.now = 0
        self.most = 0


def slow_source(monkeypatch: pytest.MonkeyPatch, root: Path, peak: Peak) -> list[Gateway]:
    """Serve ``root`` a little slowly, count the requests in flight, and keep every gateway the seam builds."""
    built: list[Gateway] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        peak.now += 1
        peak.most = max(peak.most, peak.now)
        await asyncio.sleep(0.01)
        peak.now -= 1
        return _respond(root, request)

    def open_gateway(policy: Policy, resolve) -> Gateway:
        gateway = Gateway(policy, transport=httpx.MockTransport(handler), resolve=resolve)
        built.append(gateway)
        return gateway

    monkeypatch.setattr(zarr_reader, "open_gateway", open_gateway)
    return built


async def test_stores_of_one_process_share_one_gateway_and_its_cap(
    monkeypatch: pytest.MonkeyPatch, store_root: Path
) -> None:
    peak = Peak()
    built = slow_source(monkeypatch, store_root, peak)
    capped = Policy(allowed_hosts=frozenset({HOST}), host_connections={HOST: 2})
    stores = [GatewayStore(BASE_URL, capped, resolve=from_memory) for _ in range(4)]
    await asyncio.gather(*(store.get(KEY, default_buffer_prototype()) for store in stores * 3))
    assert len(built) == 1
    assert peak.most == 2


async def test_closing_a_store_leaves_the_shared_gateway_open(
    monkeypatch: pytest.MonkeyPatch, store_root: Path
) -> None:
    built = slow_source(monkeypatch, store_root, Peak())
    first, second = (GatewayStore(BASE_URL, POLICY, resolve=from_memory) for _ in range(2))
    await first.get(KEY, default_buffer_prototype())
    first.close()
    assert await second.get(KEY, default_buffer_prototype()) is not None
    assert len(built) == 1


async def test_another_policy_gets_a_gateway_of_its_own_an_equal_one_does_not(
    monkeypatch: pytest.MonkeyPatch, store_root: Path
) -> None:
    built = slow_source(monkeypatch, store_root, Peak())
    wider = Policy(allowed_hosts=frozenset({HOST, "other.example.invalid"}))
    for policy in [POLICY, Policy(allowed_hosts=frozenset({HOST})), wider]:
        await GatewayStore(BASE_URL, policy, resolve=from_memory).get(KEY, default_buffer_prototype())
    assert len(built) == 2


async def test_a_resolver_built_per_run_leaves_no_gateway_per_run_behind(
    monkeypatch: pytest.MonkeyPatch, store_root: Path
) -> None:
    # `readers.access.read_access_for` builds a CachingResolver for every run; keyed by it, each area statistic of a
    # Zarr dataset in the tiler would leave a client behind (review of M5-36 PR 1).
    built = slow_source(monkeypatch, store_root, Peak())
    for _ in range(5):
        fresh = CachingResolver(resolve=from_memory)
        await GatewayStore(BASE_URL, POLICY, resolve=fresh).get(KEY, default_buffer_prototype())
    assert len(built) == 1


async def test_after_closing_the_next_read_builds_a_new_gateway(
    monkeypatch: pytest.MonkeyPatch, store_root: Path
) -> None:
    built = slow_source(monkeypatch, store_root, Peak())
    store = GatewayStore(BASE_URL, POLICY, resolve=from_memory)
    await store.get(KEY, default_buffer_prototype())
    close_shared_gateways()
    await asyncio.sleep(0)
    assert await store.get(KEY, default_buffer_prototype()) is not None
    assert len(built) == 2


def test_a_gateway_of_a_closed_loop_is_dropped(monkeypatch: pytest.MonkeyPatch, store_root: Path) -> None:
    built = slow_source(monkeypatch, store_root, Peak())

    async def take() -> Gateway:
        return shared_gateway(POLICY, from_memory)

    first = asyncio.run(take())
    second = asyncio.run(take())
    assert first is not second and len(built) == 2
    assert len(zarr_reader._SHARED) == 1


def test_outside_an_event_loop_there_is_no_shared_gateway() -> None:
    with pytest.raises(RuntimeError):
        shared_gateway(POLICY, from_memory)
