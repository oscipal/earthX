"""docker-compose.yml wires the worker to the queue (M4-08a, adr/0013 §5.3, §5.7).

Read as YAML; Docker never runs in the session (adr/0002 §1). The CI job `compose-topology`
starts the real thing, and its step "Restart one service" restarts `worker`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
SERVICES = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
WORKER = SERVICES["worker"]


def test_the_worker_reaches_postgres_with_the_same_names_as_api_and_by_reference_only() -> None:
    env = WORKER["environment"]
    assert env["PGHOST"] == "postgres"
    for name in ("PGUSER", "PGPASSWORD", "PGDATABASE"):
        assert env[name] == SERVICES["api"]["environment"][name]
        assert str(env[name]).startswith("${"), f"{name} is read from the environment of compose, never written here"


def test_the_worker_waits_for_the_migration_that_creates_the_queue_tables() -> None:
    depends = WORKER["depends_on"]
    assert depends["catalog-load"]["condition"] == "service_completed_successfully"
    assert depends["postgres"]["condition"] == "service_healthy"


def test_the_settings_of_a_container_keep_their_defaults_and_the_cap_is_not_one_of_them() -> None:
    """Adr/0013 §5.7: slots, lease, heartbeat, polling are per container and default; cap and host limit are a row."""
    text = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    assert "WORKER_" not in text.replace("(WORKER_*)", "")
    assert "GLOBAL_CAP" not in text.upper() and "HOST_CAP" not in text.upper()


def test_the_worker_has_time_to_end_its_children_on_stop() -> None:
    seconds = int(str(WORKER["stop_grace_period"]).rstrip("s"))
    assert seconds >= 30


def test_the_worker_still_gets_no_credentials_in_the_file() -> None:
    text = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    worker_section = text[text.index("\n  worker:") : text.index("\n  harvester:")]
    for line in worker_section.splitlines():
        stripped = line.strip()
        if stripped.startswith(("PGPASSWORD", "S3_SECRET_KEY", "S3_ACCESS_KEY")):
            assert "${" in stripped or "_FILE" in stripped, stripped
