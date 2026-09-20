"""The statistics endpoint answers the same thing twice, and a broken cache is only slow.

The two properties adr/0006 asks of the cache (§5 "Zu Frage 3", E5) are the two
things that cannot be read off the code: that a hit and a cold read are the same
answer, and that a cache which raises costs a read rather than the request. Both
are checked here against a reader that returns numbers from memory — no network,
no database, and no GDAL (adr/0002 §2).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from rio_tiler.models import BandStatistics

from earthx.access.tiles import EarthxTilerFactory, statistics_cache_key
from earthx.readers.cog import AssetPath

PATH = AssetPath("/vsicurl/https://assets.example.invalid/x.tif", dataset_id="d", item_id="i", asset="visual")

# Built through rio-tiler's own model rather than typed out: the endpoint answers
# `dict[str, BandStatistics]`, and a hand-written dict would drift from it silently.
STATISTICS = {
    "b1": BandStatistics(
        min=0.0,
        max=255.0,
        mean=100.0,
        count=10.0,
        sum=1000.0,
        std=5.0,
        median=100.0,
        majority=100.0,
        minority=0.0,
        unique=3.0,
        histogram=[[10.0], [0.0, 255.0]],
        valid_percent=100.0,
        masked_pixels=0.0,
        valid_pixels=10.0,
        percentile_2=12.0,
        percentile_98=240.0,
        description="b1",
    ).model_dump(mode="json")
}


class Recording:
    """A cache that works, and counts what it was asked to do."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.reads = 0
        self.writes = 0

    async def get(self, key: str) -> dict[str, Any] | None:
        self.reads += 1
        return self.rows.get(key)

    async def set(self, key: str, value: dict[str, Any], *, dataset_id: str) -> None:
        self.writes += 1
        self.rows[key] = value


class Broken:
    """A cache that fails at both ends, the way an unreachable database does."""

    async def get(self, key: str) -> dict[str, Any] | None:
        raise RuntimeError("no database")

    async def set(self, key: str, value: dict[str, Any], *, dataset_id: str) -> None:
        raise RuntimeError("no database")


@pytest.fixture
def reads() -> list[str]:
    return []


@pytest.fixture
def client_for(reads: list[str], monkeypatch: pytest.MonkeyPatch):
    """An app whose statistics come from memory, with the cache the test hands in.

    The read is the one thing these tests must not do for real — it would need GDAL
    and a network. Everything around it (the cache, the key, the answer) is the code
    under test.
    """

    def fake_read(reader, src_path, **kwargs) -> dict[str, Any]:
        reads.append(src_path)
        return STATISTICS

    monkeypatch.setattr("earthx.access.tiles._read_statistics", fake_read)

    def build(cache: object | None) -> TestClient:
        factory = EarthxTilerFactory(
            path_dependency=lambda: PATH,
            environment_dependency=lambda: {},
            stats_cache_dependency=lambda: cache,
            name="tiles",
        )
        app = FastAPI()
        app.include_router(factory.router)
        return TestClient(app)

    return build


def test_a_cold_read_is_stored_and_the_second_call_is_answered_from_the_cache(
    client_for, reads: list[str]
) -> None:
    cache = Recording()
    client = client_for(cache)

    first = client.get("/statistics")
    second = client.get("/statistics")

    assert first.status_code == 200
    assert first.json() == second.json()
    assert reads == [PATH], "the second call read the asset again"
    assert (cache.writes, len(cache.rows)) == (1, 1)


def test_a_broken_cache_costs_a_read_and_nothing_else(client_for, reads: list[str]) -> None:
    """E5: an empty or unreachable cache makes the platform slower, never wrong."""
    client = client_for(Broken())

    first = client.get("/statistics")
    second = client.get("/statistics")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == STATISTICS
    assert reads == [PATH, PATH]


def test_without_a_cache_the_endpoint_still_answers(client_for) -> None:
    response = client_for(None).get("/statistics")
    assert response.status_code == 200
    assert response.json() == STATISTICS


def test_two_different_questions_do_not_share_an_entry(client_for) -> None:
    """The band selection changes the numbers, so it has to change the key."""
    cache = Recording()
    client = client_for(cache)

    client.get("/statistics")
    client.get("/statistics", params={"bidx": 2})

    assert len(cache.rows) == 2


class TestTheKey:
    def test_the_same_question_written_twice_is_one_key(self) -> None:
        first = statistics_cache_key(PATH, {"stats": {"percentiles": [2, 98]}, "layer": {}})
        second = statistics_cache_key(PATH, {"layer": {}, "stats": {"percentiles": [2, 98]}})
        assert first == second

    def test_another_item_is_another_key(self) -> None:
        other = AssetPath(str(PATH), dataset_id="d", item_id="other", asset="visual")
        assert statistics_cache_key(PATH, {}) != statistics_cache_key(other, {})

    def test_the_key_carries_no_address(self) -> None:
        """A key ends up in a database column; an address must not (projektplan.md 7)."""
        key = statistics_cache_key(PATH, {})
        assert "assets.example.invalid" not in key
        assert len(key) == 64


def test_the_route_set_is_the_one_m2_04_decided_on() -> None:
    """No viewer, no /bbox, no /feature (adr/0006 §3.1) — and one statistics route."""
    factory = EarthxTilerFactory(path_dependency=lambda: PATH, name="tiles")
    paths = {route.path for route in factory.router.routes}

    assert "/statistics" in paths
    assert not [route for route in factory.router.routes if "POST" in getattr(route, "methods", set())]
    assert not [path for path in paths if "map.html" in path or path.startswith("/bbox") or path == "/feature"]
    assert any(path.startswith("/tiles/") for path in paths)
    assert any("tilejson.json" in path for path in paths)
