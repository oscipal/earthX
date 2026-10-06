"""compose/objectstore/smoke.py prints no key and no key id, also on failure (M4-06).

Otto's condition to plan M4-06 F2: the CI job hands the smoke three key pairs
(owner, `jobs`, `api`), and none of them, nor any key id, may appear in the
public CI log. GitHub masks them (`::add-mask::`); this checks the second
guard, `smoke.py`'s own redaction, without a running Garage.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
OBJECTSTORE_DIR = REPO / "compose" / "objectstore"

KEYS = {
    "S3_ACCESS_KEY": "GKowner000000000000000001",
    "S3_SECRET_KEY": "owner-secret-000000000000000000001",
    "S3_JOBS_ACCESS_KEY": "GKjobs0000000000000000001",
    "S3_JOBS_SECRET_KEY": "jobs-secret-0000000000000000000001",
    "S3_API_ACCESS_KEY": "GKapi00000000000000000001",
    "S3_API_SECRET_KEY": "api-secret-00000000000000000000001",
}


def _load_smoke():
    if str(OBJECTSTORE_DIR) not in sys.path:
        sys.path.insert(0, str(OBJECTSTORE_DIR))
    spec = importlib.util.spec_from_file_location("objectstore_smoke", OBJECTSTORE_DIR / "smoke.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


smoke = _load_smoke()


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in KEYS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("S3_BUCKET", "earthx")
    monkeypatch.setattr(sys, "argv", ["smoke.py", "--write-marker"])


class _Echoing:
    """A client whose every call fails with a message that names every key, as
    Garage's `AccessDenied` names the key id (adr/0015 §3.2)."""

    def __getattr__(self, name: str):  # noqa: ANN204
        def fail(*args: object, **kwargs: object) -> None:
            raise RuntimeError("denied: " + " ".join(KEYS.values()))

        return fail


def _assert_nothing_leaks(capsys: pytest.CaptureFixture[str]) -> str:
    captured = capsys.readouterr()
    for value in KEYS.values():
        assert value not in captured.out
        assert value not in captured.err
    return captured.err


def test_a_failing_store_call_prints_no_key(environment: None, monkeypatch, capsys) -> None:
    monkeypatch.setattr(smoke, "_client", lambda *args: _Echoing())
    assert smoke.main() == 1
    assert "object store smoke failed: denied:" in _assert_nothing_leaks(capsys)


def test_a_failure_in_the_service_key_suite_prints_no_key(environment: None, monkeypatch, capsys) -> None:
    monkeypatch.setattr(smoke, "run_full_suite", lambda *args: None)

    def failing_suite(*args: object) -> None:
        raise RuntimeError(f"AccessDenied: No such key: {KEYS['S3_API_ACCESS_KEY']}")

    monkeypatch.setattr(smoke, "run_service_key_suite", failing_suite)
    assert smoke.main() == 1
    assert "No such key: <redacted>" in _assert_nothing_leaks(capsys)


def test_a_failed_check_exits_with_one_and_a_redacted_line(environment: None, monkeypatch, capsys) -> None:
    monkeypatch.setattr(smoke, "run_full_suite", lambda *args: smoke.check("Multipart upload", False))
    assert smoke.main() == 1
    assert "smoke check failed: Multipart upload" in _assert_nothing_leaks(capsys)


def test_a_missing_service_key_fails_without_printing_the_others(
    environment: None, monkeypatch, capsys
) -> None:
    monkeypatch.delenv("S3_API_SECRET_KEY")
    monkeypatch.setattr(smoke, "run_full_suite", lambda *args: None)
    assert smoke.main() == 1
    assert "S3_API_SECRET_KEY" in _assert_nothing_leaks(capsys)


def test_the_smoke_only_reads_the_lifecycle_configuration() -> None:
    """Writing one replaces the whole configuration, and the worker needs the rule."""
    source = (OBJECTSTORE_DIR / "smoke.py").read_text(encoding="utf-8")
    assert "get_bucket_lifecycle_configuration" in source
    for write in ("put_bucket_lifecycle", "delete_bucket_lifecycle"):
        assert write not in source


def test_the_smoke_uses_botocore_not_boto3() -> None:
    source = (OBJECTSTORE_DIR / "smoke.py").read_text(encoding="utf-8")
    assert "import botocore" in source
    assert "import boto3" not in source and "boto3." not in source
