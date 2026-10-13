"""The live smoke tests, replayed without the network (M4-27).

``backend/tests_live`` never runs in a pull request (adr/0002 §2), so a call there that
no longer fits a signature only showed up in the daily run: ``search_items`` lost its
default for ``adapters=`` in M4-01b and the smoke was red for five days. This file runs
every test of that directory against a transport double that answers from the recorded
fixtures in ``tests/fixtures``.

What it catches: a signature, an import or an attribute that moved. What it cannot
catch, and is not meant to: the source changing. The fixtures are synthetic, so the
replay stays green when Earth Search changes; the scheduled run is what notices that.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

from earthx.gateway import Gateway

pytestmark = pytest.mark.anyio

TESTS = Path(__file__).resolve().parent
LIVE = TESTS.parent / "tests_live"
SMOKE_FILES = sorted(LIVE.glob("test_*.py"))

# A minimal TIFF header and a bucket listing, written by hand: there is no recording of
# the DEM bucket (plans/m3-11b-dem-adapter.md §2 measured it by hand).
TIFF_HEADER = b"II*\x00\x08\x00\x00\x00" + b"\x00" * 8
BUCKET_LISTING = b"<ListBucketResult><Prefix></Prefix><CommonPrefixes><Prefix>Copernicus_DSM_COG_10_N00_00_E006_00_DEM/</Prefix></CommonPrefixes></ListBucketResult>"


def _fixture(directory: str, name: str) -> dict[str, Any]:
    return json.loads((TESTS / "fixtures" / directory / f"{name}.json").read_text(encoding="utf-8"))


def _json(payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json=payload)


def _stac_double(directory: str) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path.endswith("/search"):
            return _json(_fixture(directory, "search_page_1"))
        if request.method == "GET" and "/items/" in path:
            # The live test asks for the id the search just returned; the recorded item has its own.
            return _json({**_fixture(directory, "item"), "id": path.rsplit("/", 1)[-1]})
        raise AssertionError(f"the double has no answer for {request.method} {request.url}")

    return handler


def _coverage_double(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and request.url.path.endswith("/aggregate"):
        return _json(_fixture("earth_search", "aggregate_complete"))
    raise AssertionError(f"the double has no answer for {request.method} {request.url}")


def _dem_double(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/tileList.txt"):
        return httpx.Response(304, headers={"etag": request.headers.get("if-none-match", "")})
    if path.endswith(".tif"):
        return httpx.Response(206, content=TIFF_HEADER[:16])
    if request.url.params.get("list-type"):
        return httpx.Response(200, content=BUCKET_LISTING)
    raise AssertionError(f"the double has no answer for {request.method} {request.url}")


DOUBLES: dict[str, Callable[[httpx.Request], httpx.Response]] = {
    "test_earth_search_smoke": _stac_double("earth_search"),
    "test_eopf_smoke": _stac_double("eopf_stac"),
    "test_coverage_smoke": _coverage_double,
    "test_cop_dem_smoke": _dem_double,
}


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"tests_live_dry_run.{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _smoke_tests(module: ModuleType) -> list[Callable[..., Any]]:
    return [
        function
        for name, function in inspect.getmembers(module, inspect.iscoroutinefunction)
        if name.startswith("test_") and function.__module__ == module.__name__
    ]


def _replaying(module: ModuleType, handler: Callable[[httpx.Request], httpx.Response]) -> None:
    """Make the module's own ``open_gateway`` build a gateway over the double."""

    async def no_sleep(seconds: float) -> None:
        return None

    def gateway(policy: Any) -> Gateway:
        return Gateway(
            policy,
            transport=httpx.MockTransport(handler),
            resolve=lambda host, port: ("93.184.216.34",),
            sleep=no_sleep,
        )

    module.Gateway = gateway


def test_every_smoke_file_has_a_double() -> None:
    """A new file in ``tests_live`` without a double would run unchecked in every PR."""
    assert SMOKE_FILES, "no live smoke file found"
    assert {path.stem for path in SMOKE_FILES} == set(DOUBLES)


@pytest.mark.parametrize("path", SMOKE_FILES, ids=lambda path: path.stem)
async def test_the_live_smoke_replays_against_the_recorded_fixtures(path: Path) -> None:
    module = _load(path)
    tests = _smoke_tests(module)
    assert tests, f"{path.name} holds no smoke test"
    _replaying(module, DOUBLES[path.stem])

    for smoke in tests:
        assert list(inspect.signature(smoke).parameters) == ["gateway"], (
            f"{smoke.__name__} takes more than the gateway; teach this replay how to supply it"
        )
        async with module.open_gateway() as gateway:
            await smoke(gateway=gateway)
