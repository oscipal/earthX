"""docker-compose.yml hands each process only its own object store key (M4-06, adr/0015 §6.4, §9.1).

Read as YAML; Docker never runs in the session (adr/0002 §1). The CI job
`compose-topology` starts the real thing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
SERVICES = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))["services"]

KEY_VOLUMES = {"api": "objectstore-key-api", "worker": "objectstore-key-jobs"}


def _volumes(service: str) -> list[str]:
    return [entry.split(":")[0] for entry in SERVICES[service].get("volumes", [])]


def _environment(service: str) -> dict[str, str]:
    return SERVICES[service].get("environment") or {}


@pytest.mark.parametrize("service", sorted(KEY_VOLUMES))
def test_api_and_worker_get_the_store_and_their_own_key_only(service: str) -> None:
    env = _environment(service)
    assert env["S3_ENDPOINT"] == "http://objectstore:3900"
    assert env["S3_PUBLIC_ENDPOINT"] == "http://localhost:3900"
    assert env["S3_REGION"] == "garage"
    assert env["S3_ACCESS_KEY_FILE"].startswith("/run/secrets/objectstore/")
    assert env["S3_SECRET_KEY_FILE"].startswith("/run/secrets/objectstore/")
    assert "S3_ACCESS_KEY" not in env and "S3_SECRET_KEY" not in env
    assert [v for v in _volumes(service) if v.startswith("objectstore-")] == [KEY_VOLUMES[service]]
    assert all(entry.endswith(":ro") for entry in SERVICES[service]["volumes"])


@pytest.mark.parametrize("service", ["tiler", "harvester"])
def test_the_other_processes_get_no_store(service: str) -> None:
    assert not [name for name in _environment(service) if name.startswith("S3_")]
    assert not [v for v in _volumes(service) if v.startswith("objectstore-")]


@pytest.mark.parametrize("service", sorted(SERVICES))
def test_no_service_gets_aws_names(service: str) -> None:
    """rasterio hands AWS_* to GDAL in every process (adr/0015 §3.1)."""
    assert not [name for name in _environment(service) if name.startswith("AWS_")]


def test_only_the_one_shot_steps_see_the_admin_volume() -> None:
    with_admin = {name for name in SERVICES if "objectstore-secrets" in _volumes(name)}
    assert with_admin == {"objectstore-secrets", "objectstore", "objectstore-init"}


def test_the_bootstrap_steps_see_both_service_keys() -> None:
    assert set(KEY_VOLUMES.values()) <= set(_volumes("objectstore-secrets"))
    assert set(KEY_VOLUMES.values()) <= set(_volumes("objectstore-init"))


def test_garage_does_not_log_requests_with_their_key_id() -> None:
    """Garage's request log names the access key of every request (`(key GK…)`,
    `GetKeyInfo?id=GK…`); measured 56, 24 and 22 lines for the three keys of one
    local run against the official image, none with this filter. The CI prints
    `docker compose logs` on a failed start before it masks the keys."""
    assert _environment("objectstore")["RUST_LOG"] == "netapp=info,garage=info,garage_api_common=error"
