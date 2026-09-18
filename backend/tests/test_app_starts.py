"""The application starts and answers its metadata routes without any network.

These are the first tests in the repository; they exist so CI checks something
real from day one (docs/adr/0002-testaufteilung.md). They deliberately cover
only routes that need neither a data source nor a token.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

SECRET_MARKERS = ("token", "secret", "password", "client_secret", "authorization")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_app_exposes_every_router() -> None:
    """Read the paths from the OpenAPI schema — `app.routes` nests included routers."""
    paths = set(app.openapi()["paths"])
    assert {"/", "/api/health", "/api/config"} <= paths
    for prefix in ("search", "tiles", "download", "decompose", "stitch", "coverage", "asset", "geocode"):
        assert any(path.startswith(f"/api/{prefix}") for path in paths), prefix


def test_root_reports_name_and_version(client: TestClient) -> None:
    body = client.get("/").json()
    assert body["version"]
    assert body["docs"] == "/docs"


def test_health_is_ok(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_config_works_without_a_token(client: TestClient) -> None:
    body = client.get("/api/config").json()
    assert body["token"] == {"configured": False, "kind": None}


def test_config_leaks_no_secret_value(client: TestClient) -> None:
    """The response describes the token's state, never a credential."""
    from app.config import get_settings

    raw = client.get("/api/config").text
    assert get_settings().oidc_client_secret not in raw
    for key, value in client.get("/api/config").json().items():
        if key == "token":
            continue
        assert not any(marker in str(value).lower() for marker in SECRET_MARKERS)


def test_unknown_route_is_a_clean_404(client: TestClient) -> None:
    assert client.get("/api/does-not-exist").status_code == 404


def test_wrong_method_is_rejected(client: TestClient) -> None:
    assert client.post("/api/health").status_code == 405
