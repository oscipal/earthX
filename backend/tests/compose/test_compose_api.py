"""docker-compose.yml starts `api` the way the job API needs it (M4-08b).

Read as YAML; Docker never runs in the session (adr/0002 §1). The CI job `compose-topology`
starts the real thing.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
API = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))["services"]["api"]
COMMAND = [str(part) for part in API["command"]]


def test_it_keeps_the_flag_that_keeps_the_query_string_out_of_the_log() -> None:
    assert "--no-access-log" in COMMAND


def test_a_progress_stream_does_not_hold_the_shutdown_longer_than_compose_waits() -> None:
    """uvicorn waits for open connections before the lifespan's shutdown; a stream of a waiting job never ends."""
    assert "--timeout-graceful-shutdown" in COMMAND
    seconds = int(COMMAND[COMMAND.index("--timeout-graceful-shutdown") + 1])
    stop = int(str(API.get("stop_grace_period", "10s")).rstrip("s"))
    assert 0 < seconds < stop


def test_it_has_what_it_needs_to_sign_result_links_and_to_start() -> None:
    env = API["environment"]
    for name in (
        "S3_ENDPOINT",
        "S3_PUBLIC_ENDPOINT",
        "S3_REGION",
        "S3_BUCKET",
        "S3_ACCESS_KEY_FILE",
        "S3_SECRET_KEY_FILE",
    ):
        assert name in env, f"api does not start without {name} (M4-08b F7)"
    assert "S3_LIFECYCLE_CHECK" not in env
    assert any(str(volume).endswith(":ro") and "objectstore-key-api" in str(volume) for volume in API["volumes"])


def test_it_waits_for_the_tables_of_the_queue_and_the_store_keys() -> None:
    depends = API["depends_on"]
    assert depends["catalog-load"]["condition"] == "service_completed_successfully"
    assert depends["objectstore-init"]["condition"] == "service_completed_successfully"
    assert depends["postgres"]["condition"] == "service_healthy"
