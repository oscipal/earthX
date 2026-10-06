"""One registry per app (M4-01b): ``/coverage`` answers from the registry the app
was built with, not from the module-wide ``REGISTRY`` it used to be mounted with.

Built with ``api.main.build_app`` itself, without its lifespan and without a
database (``earthx_cache_pool = None``); the gateway is under test control, the
same way ``test_coverage_route.py`` mounts the route alone.
"""

from __future__ import annotations

from dataclasses import replace

import httpx
from fastapi.testclient import TestClient

from earthx.api.main import build_app
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.registry import DatasetRegistry
from tests.earthx.adapters.conftest import answering, load

# Known to this app only; the module-wide registry has no such dataset.
OWN = replace(SENTINEL_2_L2A, dataset_id="earthx-test-own-registry")


def client_for(gateway) -> TestClient:
    app = build_app(DatasetRegistry((OWN,)))
    app.state.earthx_gateway = gateway
    app.state.earthx_cache_pool = None
    return TestClient(app)


def test_coverage_answers_an_entry_only_this_apps_registry_knows() -> None:
    gateway, seen = answering(httpx.Response(200, json=load("aggregate_complete")))
    response = client_for(gateway).get(f"/coverage/{OWN.dataset_id}", params={"zoom": 5, "bbox": "5,45,15,55"})
    assert response.status_code == 200
    assert response.json()["dataset_id"] == OWN.dataset_id
    assert len(seen) == 1


def test_coverage_refuses_an_entry_only_the_module_registry_knows() -> None:
    gateway, seen = answering(httpx.Response(200, json=load("aggregate_complete")))
    response = client_for(gateway).get(f"/coverage/{SENTINEL_2_L2A.dataset_id}", params={"zoom": 5})
    assert response.status_code == 404
    assert seen == []
