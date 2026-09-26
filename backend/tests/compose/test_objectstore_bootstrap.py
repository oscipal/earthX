"""Tests for compose/objectstore/bootstrap.py (M3-23, adr/0012).

`bootstrap.py` is operational code for the compose topology, not part of the
EarthX application (it lives outside `backend/earthx/`), so it is imported
here by path rather than as a package.

The suite's own `no_network` fixture (backend/tests/conftest.py) forbids any
test from opening a socket, on purpose — the same rule that keeps a data
source out of reach applies here. `init`'s admin-API calls are therefore
exercised against a fake `_admin_request`, a plain function replacing the
real one, rather than a real HTTP server: no socket, no DNS lookup, and the
fake still sees the exact same (method, path, body) sequence a real Garage
admin API would.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import stat
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
BOOTSTRAP_PATH = REPO / "compose" / "objectstore" / "bootstrap.py"


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location("objectstore_bootstrap", BOOTSTRAP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bootstrap = _load_bootstrap()


@pytest.fixture
def secrets_dir(tmp_path, monkeypatch):
    directory = tmp_path / "secrets"
    monkeypatch.setenv("OBJECTSTORE_SECRETS_DIR", str(directory))
    for var in ("S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_BUCKET"):
        monkeypatch.delenv(var, raising=False)
    return directory


class FakeAdminApi:
    """A minimal stand-in for Garage's admin API v2, driven by call sequence
    rather than a socket: `bootstrap._admin_request` is monkeypatched to
    `handle` below."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}
        self.buckets: dict[str, str] = {}
        self.import_calls = 0
        self.create_calls = 0
        self.allow_calls = 0
        self._next_error: tuple[int, dict] | None = None

    def fail_next_bucket_lookup_with(self, status: int, error: str) -> None:
        self._next_error = (status, {"error": error})

    def handle(self, base_url: str, token: str, method: str, path: str, body: dict | None = None):
        if path == "/v2/GetClusterHealth":
            return 200, {"status": "healthy"}

        if path.startswith("/v2/GetKeyInfo"):
            key_id = path.split("id=")[1].split("&")[0]
            secret = self.keys.get(key_id)
            if secret is None:
                return 404, {"error": "key not found"}
            return 200, {"accessKeyId": key_id, "secretAccessKey": secret}

        if path == "/v2/ImportKey":
            self.import_calls += 1
            self.keys[body["accessKeyId"]] = body["secretAccessKey"]
            return 201, {"accessKeyId": body["accessKeyId"]}

        if path.startswith("/v2/GetBucketInfo"):
            if self._next_error is not None:
                status, info = self._next_error
                self._next_error = None
                return status, info
            alias = path.split("globalAlias=")[1]
            bucket_id = self.buckets.get(alias)
            if bucket_id is None:
                return 404, {"error": "bucket not found"}
            return 200, {"id": bucket_id, "globalAliases": [alias]}

        if path == "/v2/CreateBucket":
            self.create_calls += 1
            alias = body["globalAlias"]
            bucket_id = f"bucket-{len(self.buckets) + 1}"
            self.buckets[alias] = bucket_id
            return 201, {"id": bucket_id, "globalAliases": [alias]}

        if path == "/v2/AllowBucketKey":
            self.allow_calls += 1
            return 200, {"id": body["bucketId"]}

        raise AssertionError(f"unexpected admin API call: {method} {path}")


@pytest.fixture
def fake_admin(monkeypatch):
    api = FakeAdminApi()
    monkeypatch.setattr(bootstrap, "_admin_request", api.handle)
    return api


def init_args(admin_url: str = "http://objectstore:3903", attempts: int = 5, delay: float = 0.0) -> argparse.Namespace:
    return argparse.Namespace(admin_url=admin_url, attempts=attempts, delay=delay)


def _write_secrets_for_init(secrets_dir: Path, secret_key: str = "a-sixteen-char-secret") -> None:
    secrets_dir.mkdir(parents=True, exist_ok=True)
    (secrets_dir / "admin_token").write_text("test-admin-token")
    (secrets_dir / "s3_access_key").write_text("a-valid-access-key")
    (secrets_dir / "s3_secret_key").write_text(secret_key)
    (secrets_dir / "s3_bucket").write_text("earthx")


# --- secrets --------------------------------------------------------------


def test_secrets_creates_all_files_with_valid_formats_and_permissions(secrets_dir):
    assert bootstrap.main(["secrets"]) == 0

    names = {"rpc_secret", "admin_token", "s3_access_key", "s3_secret_key", "s3_bucket"}
    for name in names:
        path = secrets_dir / name
        assert path.exists()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    access_key = (secrets_dir / "s3_access_key").read_text().strip()
    secret_key = (secrets_dir / "s3_secret_key").read_text().strip()
    assert re.match(r"^[A-Za-z0-9._-]{8,}$", access_key)
    assert re.match(r"^[\x21-\x7e]{16,}$", secret_key)
    assert (secrets_dir / "s3_bucket").read_text().strip() == "earthx"
    assert len((secrets_dir / "rpc_secret").read_text().strip()) == 64


def test_secrets_second_run_changes_nothing(secrets_dir):
    assert bootstrap.main(["secrets"]) == 0
    before = {p.name: (p.read_text(), p.stat().st_mtime_ns) for p in secrets_dir.iterdir()}

    assert bootstrap.main(["secrets"]) == 0
    after = {p.name: (p.read_text(), p.stat().st_mtime_ns) for p in secrets_dir.iterdir()}

    assert before == after


def test_secrets_uses_env_values_when_both_are_set(secrets_dir, monkeypatch):
    monkeypatch.setenv("S3_ACCESS_KEY", "my-access-key")
    monkeypatch.setenv("S3_SECRET_KEY", "a-sixteen-char-secret")
    monkeypatch.setenv("S3_BUCKET", "my-results")

    assert bootstrap.main(["secrets"]) == 0

    assert (secrets_dir / "s3_access_key").read_text().strip() == "my-access-key"
    assert (secrets_dir / "s3_secret_key").read_text().strip() == "a-sixteen-char-secret"
    assert (secrets_dir / "s3_bucket").read_text().strip() == "my-results"


@pytest.mark.parametrize(
    "env",
    [
        {"S3_ACCESS_KEY": "only-the-access-key"},
        {"S3_SECRET_KEY": "only-the-secret-key-set"},
    ],
)
def test_secrets_rejects_only_one_of_access_or_secret(secrets_dir, monkeypatch, env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert bootstrap.main(["secrets"]) == 1


def test_secrets_rejects_short_access_key(secrets_dir, monkeypatch):
    monkeypatch.setenv("S3_ACCESS_KEY", "short")
    monkeypatch.setenv("S3_SECRET_KEY", "a-sixteen-char-secret")
    assert bootstrap.main(["secrets"]) == 1


def test_secrets_rejects_short_secret_key(secrets_dir, monkeypatch):
    monkeypatch.setenv("S3_ACCESS_KEY", "a-valid-access-key")
    monkeypatch.setenv("S3_SECRET_KEY", "too-short")
    assert bootstrap.main(["secrets"]) == 1


def test_secrets_rejects_secret_key_with_whitespace(secrets_dir, monkeypatch):
    monkeypatch.setenv("S3_ACCESS_KEY", "a-valid-access-key")
    monkeypatch.setenv("S3_SECRET_KEY", "has a space in it!")
    assert bootstrap.main(["secrets"]) == 1


def test_secrets_rejects_invalid_bucket_name(secrets_dir, monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "UPPERCASE_not_allowed")
    assert bootstrap.main(["secrets"]) == 1


def test_secrets_rejects_env_key_mismatching_stored_key(secrets_dir):
    assert bootstrap.main(["secrets"]) == 0  # generates a key

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("S3_ACCESS_KEY", "a-different-access-key")
        mp.setenv("S3_SECRET_KEY", "a-different-sixteen-char-key")
        assert bootstrap.main(["secrets"]) == 1


# --- init -------------------------------------------------------------


def test_init_imports_key_creates_bucket_and_grants_access(secrets_dir, fake_admin):
    _write_secrets_for_init(secrets_dir)

    bootstrap.cmd_init(init_args())

    assert fake_admin.import_calls == 1
    assert fake_admin.create_calls == 1
    assert fake_admin.allow_calls == 1
    assert fake_admin.keys["a-valid-access-key"] == "a-sixteen-char-secret"
    assert "earthx" in fake_admin.buckets


def test_init_second_run_does_not_recreate_key_or_bucket(secrets_dir, fake_admin):
    _write_secrets_for_init(secrets_dir)

    bootstrap.cmd_init(init_args())
    bootstrap.cmd_init(init_args())

    assert fake_admin.import_calls == 1
    assert fake_admin.create_calls == 1
    assert fake_admin.allow_calls == 2  # granted again each run; idempotent on Garage's side


def test_init_rejects_key_that_exists_with_a_different_secret(secrets_dir, fake_admin):
    _write_secrets_for_init(secrets_dir)
    fake_admin.keys["a-valid-access-key"] = "a-completely-different-secret"

    with pytest.raises(bootstrap.BootstrapError, match="different secret"):
        bootstrap.cmd_init(init_args())


def test_init_gives_up_after_limited_retries_when_unreachable(secrets_dir, monkeypatch):
    _write_secrets_for_init(secrets_dir)

    def always_unreachable(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(bootstrap, "_admin_request", always_unreachable)

    with pytest.raises(bootstrap.BootstrapError, match="did not answer"):
        bootstrap.cmd_init(init_args(attempts=2, delay=0.0))


# --- no secret leaks ----------------------------------------------------


def test_secrets_output_never_contains_secret_values(secrets_dir, capsys):
    bootstrap.main(["secrets"])
    rpc_secret = (secrets_dir / "rpc_secret").read_text().strip()
    admin_token = (secrets_dir / "admin_token").read_text().strip()
    secret_key = (secrets_dir / "s3_secret_key").read_text().strip()

    captured = capsys.readouterr()
    for secret in (rpc_secret, admin_token, secret_key):
        assert secret not in captured.out
        assert secret not in captured.err


def test_init_output_never_contains_secret_values_even_when_reflected_in_an_error(
    secrets_dir, fake_admin, capsys
):
    _write_secrets_for_init(secrets_dir)
    admin_token = (secrets_dir / "admin_token").read_text().strip()
    secret_key = (secrets_dir / "s3_secret_key").read_text().strip()
    # Simulate an admin API that echoes the caller's token/secret in an error body.
    fake_admin.fail_next_bucket_lookup_with(
        500, f"internal error for token {admin_token} / {secret_key}"
    )

    with pytest.raises(bootstrap.BootstrapError) as excinfo:
        bootstrap.cmd_init(init_args())

    assert admin_token not in str(excinfo.value)
    assert secret_key not in str(excinfo.value)

    captured = capsys.readouterr()
    assert admin_token not in captured.out
    assert secret_key not in captured.out


# --- show ---------------------------------------------------------------


def test_show_prints_the_stored_credentials(secrets_dir, capsys):
    bootstrap.main(["secrets"])
    assert bootstrap.main(["show"]) == 0

    access_key = (secrets_dir / "s3_access_key").read_text().strip()
    secret_key = (secrets_dir / "s3_secret_key").read_text().strip()
    captured = capsys.readouterr()
    assert f"S3_ACCESS_KEY={access_key}" in captured.out
    assert f"S3_SECRET_KEY={secret_key}" in captured.out
