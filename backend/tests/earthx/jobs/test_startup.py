"""The worker starts only with the results/ lifecycle rule (adr/0015 §7.3, F8; §12 point 8)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from moto import mock_aws

from earthx.jobs import main
from earthx.objectstore.errors import LifecycleMissing, StoreConfigError
from earthx.objectstore.results import Store

from ..objectstore.conftest import ACCESS_KEY, BUCKET, ENDPOINT, REGION, RESULTS_RULE, SECRET_KEY, put_rules

REPO = Path(__file__).resolve().parents[4]
CONFIG_VALUES = (ACCESS_KEY, SECRET_KEY, "objectstore", "localhost", BUCKET, REGION)


@pytest.fixture
def environment(store_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> Iterator[Store]:
    """The worker's compose environment in `os.environ`, a bucket in moto, no rule yet."""
    for name, value in store_env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("MOTO_S3_CUSTOM_ENDPOINTS", ENDPOINT)
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
