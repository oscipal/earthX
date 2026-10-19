"""``GET /processing/crs/{code}`` (M4-13c-3): the unit of a target CRS, from the local EPSG database.

Built with ``api.main.build_app`` itself, without its lifespan: the route needs no database, no
gateway and no job API. Every test that reaches the route runs with the sockets shut, so an answer
that depended on PROJ's network could not come.
"""

from __future__ import annotations

import logging
import socket
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pyproj
import pytest
from fastapi.testclient import TestClient

from earthx.api import crs_info
from earthx.api.main import build_app
from tests.conftest import own_log_text


@pytest.fixture(autouse=True)
def shut_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("the CRS route opened a socket")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


@pytest.fixture
def client() -> Iterator[TestClient]:
    crs_info.crs_description.cache_clear()
    was = pyproj.network.is_network_enabled()
    try:
        yield TestClient(build_app())
    finally:
        pyproj.network.set_network_enabled(was)
        crs_info.crs_description.cache_clear()


def ask(client: TestClient, code: str):
    return client.get(f"/processing/crs/{code}")


class TestWhatItAnswers:
    def test_a_projected_crs_in_metres(self, client: TestClient) -> None:
        response = ask(client, "EPSG:3035")
        assert response.status_code == 200
        assert response.json() == {
            "code": "EPSG:3035",
            "name": "ETRS89-extended / LAEA Europe",
            "kind": "projected",
            "unit": {"name": "metre", "kind": "linear", "toBase": 1.0},
        }

    def test_a_geographic_crs_in_degrees(self, client: TestClient) -> None:
        body = ask(client, "EPSG:4326").json()
        assert body["kind"] == "geographic"
        assert body["unit"] == {"name": "degree", "kind": "angular", "toBase": 1.0}

    def test_a_projected_crs_in_feet_gives_the_factor_to_metres(self, client: TestClient) -> None:
        body = ask(client, "EPSG:2227").json()
        assert body["kind"] == "projected"
        assert body["unit"]["name"] == "US survey foot"
        assert body["unit"]["kind"] == "linear"
        assert body["unit"]["toBase"] == pytest.approx(1200 / 3937)

    def test_a_three_dimensional_geographic_crs_counts_its_horizontal_axes(self, client: TestClient) -> None:
        body = ask(client, "EPSG:4979").json()
        assert body["kind"] == "geographic"
        assert body["unit"]["name"] == "degree"

    def test_a_compound_crs_is_asked_for_its_horizontal_part(self, client: TestClient) -> None:
        body = ask(client, "EPSG:7415").json()
        assert body["kind"] == "projected"
        assert body["unit"] == {"name": "metre", "kind": "linear", "toBase": 1.0}

    def test_a_height_in_feet_is_other_and_linear(self, client: TestClient) -> None:
        body = ask(client, "EPSG:5702").json()
        assert body["kind"] == "other"
        assert body["unit"]["kind"] == "linear"
        assert body["unit"]["toBase"] == pytest.approx(1200 / 3937)

    def test_the_colon_may_be_escaped_in_the_address(self, client: TestClient) -> None:
        assert client.get("/processing/crs/EPSG%3A3035").json()["code"] == "EPSG:3035"

    def test_an_answer_may_be_cached_for_a_day(self, client: TestClient) -> None:
        assert ask(client, "EPSG:3035").headers["Cache-Control"] == "public, max-age=86400"


class TestWhatItRefuses:
    def test_an_unknown_code_is_422_and_says_which(self, client: TestClient) -> None:
        response = ask(client, "EPSG:99999")
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["detail"] == "EPSG:99999 is not a CRS this platform knows"

    @pytest.mark.parametrize(
        "code",
        [
            "epsg:3035",
            "EPSG:303",
            "EPSG:3035000",
            "EPSG:",
            "EPSG:30 35",
            "EPSG:3035%0A",
            "EPSG:３０３５",  # full-width digits
            "ESRI:54009",
            "3035",
            "EPSG:-3035",
            "EPSG:3035.0",
            "urn:ogc:def:crs:EPSG::3035",
            "PROJ:+proj=longlat",
        ],
    )
    def test_a_code_that_is_no_epsg_code_is_422(self, client: TestClient, code: str) -> None:
        response = ask(client, code)
        assert response.status_code == 422
        assert response.json()["detail"] == "not an EPSG code like EPSG:3035"

    def test_a_refusal_is_not_cached(self, client: TestClient) -> None:
        assert "public" not in ask(client, "EPSG:99999").headers.get("Cache-Control", "")

    def test_only_get_is_taken(self, client: TestClient) -> None:
        assert client.post("/processing/crs/EPSG:3035").status_code == 405

    @pytest.mark.parametrize(
        ("units", "message"),
        [
            ([("", 1.0), ("", 1.0)], "the CRS names no unit for its axes"),
            ([("unknown", 1.0), ("unknown", 1.0)], "the CRS names no unit for its axes"),
            ([("metre", 0.0), ("metre", 0.0)], "the CRS names no unit for its axes"),
            ([("metre", float("nan")), ("metre", float("nan"))], "the CRS names no unit for its axes"),
            ([("metre", 1.0), ("foot", 0.3048)], "the axes of the CRS have different units"),
        ],
    )
    def test_a_crs_without_a_usable_unit_is_422(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, units: list[tuple[str, float]], message: str
    ) -> None:
        axes = [SimpleNamespace(unit_name=name, unit_conversion_factor=factor) for name, factor in units]
        stub = SimpleNamespace(
            name="Made up", is_compound=False, is_geographic=False, is_projected=True, axis_info=axes
        )
        monkeypatch.setattr(crs_info.pyproj.CRS, "from_user_input", lambda code: stub)
        response = ask(client, "EPSG:3035")
        assert response.status_code == 422
        assert response.json()["detail"] == message


class TestNoNetwork:
    @pytest.mark.parametrize("code", ["EPSG:3035", "EPSG:4326", "EPSG:2227", "EPSG:7415", "EPSG:99999", "EPSG:12"])
    def test_every_case_answers_with_proj_network_on_and_the_sockets_shut(
        self, monkeypatch: pytest.MonkeyPatch, code: str
    ) -> None:
        monkeypatch.setenv("PROJ_NETWORK", "ON")
        pyproj.network.set_network_enabled(True)
        crs_info.crs_description.cache_clear()
        try:
            client = TestClient(build_app())
            assert pyproj.network.is_network_enabled() is False
            assert ask(client, code).status_code in {200, 422}
        finally:
            pyproj.network.set_network_enabled(False)
            crs_info.crs_description.cache_clear()

    def test_the_start_switches_the_network_off_whatever_was_set_before(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROJ_NETWORK", "ON")
        pyproj.network.set_network_enabled(True)
        try:
            build_app()
            assert pyproj.network.is_network_enabled() is False
        finally:
            pyproj.network.set_network_enabled(False)


def test_nothing_but_the_code_is_logged(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        for code in ("EPSG:3035", "EPSG:99999", "epsg:3035"):
            ask(client, code)
    text = " ".join(own_log_text(record) for record in caplog.records)
    assert "LAEA" not in text and "ETRS89" not in text and "metre" not in text
