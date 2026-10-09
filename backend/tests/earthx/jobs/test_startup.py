"""The worker starts only with the results/ lifecycle rule (adr/0015 §7.3, F8; §12 point 8), the queue tables and a valid configuration."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
import yaml
from fastapi.testclient import TestClient
from moto import mock_aws

from earthx.jobs import main
from earthx.jobs.config import WorkerConfigError
from earthx.jobs.worker import Supervisor
from earthx.objectstore.errors import LifecycleMissing, StoreConfigError
from earthx.objectstore.results import Store

from ..objectstore.conftest import ACCESS_KEY, BUCKET, ENDPOINT, REGION, RESULTS_RULE, SECRET_KEY, put_rules

REPO = Path(__file__).resolve().parents[4]
CONFIG_VALUES = (ACCESS_KEY, SECRET_KEY, "objectstore", "localhost", BUCKET, REGION)


@pytest.fixture
def environment(
    store_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, db: psycopg.Connection, tmp_path: Path
) -> Iterator[Store]:
    """The worker's compose environment in `os.environ`, a bucket in moto, no rule yet, and a database with the queue."""
    for name, value in store_env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("MOTO_S3_CUSTOM_ENDPOINTS", ENDPOINT)
    monkeypatch.setenv("WORKER_WORKDIR", str(tmp_path / "work"))
    monkeypatch.setenv("WORKER_POLL_SECONDS", "0.2")
    with mock_aws():
        store = Store.from_environ()
        store.s3._internal.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
        yield store


def _messages(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(record.getMessage() for record in caplog.records)


def _no_config_values(text: str) -> None:
    for value in CONFIG_VALUES:
        assert value not in text


def test_the_worker_starts_with_the_rule(environment: Store) -> None:
    put_rules(environment, [RESULTS_RULE])
    with TestClient(main.app) as client:
        assert client.get("/health").json() == {"status": "ok", "service": "worker"}
        assert isinstance(main.app.state.store, Store)
        assert isinstance(main.app.state.supervisor, Supervisor)
        supervisor = main.app.state.supervisor
        assert supervisor.healthy()
    assert not supervisor.healthy(), "the supervisor stops with the app"
    assert main.app.state.supervisor is None


def test_the_health_answer_is_503_while_the_supervisor_is_not_healthy(
    environment: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    put_rules(environment, [RESULTS_RULE])
    with TestClient(main.app) as client:
        monkeypatch.setattr(main.app.state.supervisor, "healthy", lambda: False)
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable", "service": "worker"}


def test_without_a_supervisor_the_health_answer_is_what_it_always_was() -> None:
    """An app whose lifespan did not run (the access-log test) has nothing to ask."""
    fresh = TestClient(main.app)
    assert fresh.get("/health").json() == {"status": "ok", "service": "worker"}


def test_the_worker_does_not_start_without_the_queue_tables(
    environment: Store, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    put_rules(environment, [RESULTS_RULE])
    monkeypatch.setenv("PGDATABASE", "template1")
    with pytest.raises(RuntimeError, match="migration 006"), TestClient(main.app):
        pass
    assert "worker not started" in _messages(caplog) and "migration 006" in _messages(caplog)


def test_the_worker_does_not_start_when_the_database_is_unreachable_and_logs_only_the_class(
    environment: Store, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    put_rules(environment, [RESULTS_RULE])
    monkeypatch.setenv("PGHOST", "127.0.0.1")
    monkeypatch.setenv("PGPORT", "1")
    with pytest.raises(psycopg.OperationalError), TestClient(main.app):
        pass
    logged = _messages(caplog)
    assert "the database is not reachable (OperationalError)" in logged
    assert "127.0.0.1" not in logged and "port 1" not in logged


@pytest.mark.parametrize(
    ("variable", "value", "message"),
    [
        ("WORKER_SLOTS", "0", "WORKER_SLOTS must be at least 1"),
        ("WORKER_SLOTS", "many", "WORKER_SLOTS is not a number"),
        ("WORKER_POLL_SECONDS", "soon", "WORKER_POLL_SECONDS is not a number"),
        ("WORKER_LEASE_SECONDS", "-5", "WORKER_LEASE_SECONDS must be a finite number greater than 0"),
    ],
)
def test_the_worker_does_not_start_with_a_bad_setting_and_names_the_variable_not_the_value(
    environment: Store,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    variable: str,
    value: str,
    message: str,
) -> None:
    put_rules(environment, [RESULTS_RULE])
    monkeypatch.setenv(variable, value)
    with pytest.raises(WorkerConfigError, match=message), TestClient(main.app):
        pass
    assert f"={value}" not in _messages(caplog) and f" {value}" not in _messages(caplog).replace(message, "")


@pytest.mark.parametrize(
    "rules",
    [[], [{**RESULTS_RULE, "Status": "Disabled"}], [{**RESULTS_RULE, "Expiration": {"Days": 30}}]],
    ids=["no-rule", "disabled", "30-days"],
)
def test_the_worker_does_not_start_without_the_rule(
    environment: Store, rules: list[dict], caplog: pytest.LogCaptureFixture
) -> None:
    if rules:
        put_rules(environment, rules)
    with pytest.raises(LifecycleMissing), TestClient(main.app):
        pass
    logged = _messages(caplog)
    assert "worker not started" in logged and "results/" in logged
    _no_config_values(logged)


def test_the_worker_does_not_start_without_configuration(
    environment: Store, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("S3_SECRET_KEY_FILE")
    with pytest.raises(StoreConfigError, match="S3_SECRET_KEY"), TestClient(main.app):
        pass
    _no_config_values(_messages(caplog))


def test_switched_off_writes_exactly_one_warning_without_values(
    environment: Store, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("S3_LIFECYCLE_CHECK", "off")

    def must_not_run(store: Store) -> bool:
        raise AssertionError("the rule is read although the check is off")

    monkeypatch.setattr(main, "lifecycle_ok", must_not_run)
    with caplog.at_level(logging.WARNING), TestClient(main.app) as client:
        assert client.get("/health").status_code == 200
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "S3_LIFECYCLE_CHECK" in warnings[0].getMessage()
    _no_config_values(_messages(caplog))


def _compose() -> str:
    return (REPO / "docker-compose.yml").read_text(encoding="utf-8")


def test_compose_never_switches_the_check_off() -> None:
    """Auflage F8: not in the file at all, so no service can inherit it."""
    assert "S3_LIFECYCLE_CHECK" not in _compose()
    for name, service in yaml.safe_load(_compose())["services"].items():
        environment = service.get("environment") or {}
        names = environment if isinstance(environment, dict) else [entry.split("=")[0] for entry in environment]
        assert "S3_LIFECYCLE_CHECK" not in names, name
