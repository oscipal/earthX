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
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
OBJECTSTORE_DIR = REPO / "compose" / "objectstore"
BOOTSTRAP_PATH = OBJECTSTORE_DIR / "bootstrap.py"


def _load_bootstrap():
    # bootstrap.py does `import redact` (a sibling module, not a package) the
    # same way it works when run as `python /objectstore/bootstrap.py` inside
    # the container: Python puts a script's own directory on sys.path[0].
    # Loading it here by file path skips that, so it is added explicitly.
    if str(OBJECTSTORE_DIR) not in sys.path:
        sys.path.insert(0, str(OBJECTSTORE_DIR))
    spec = importlib.util.spec_from_file_location("objectstore_bootstrap", BOOTSTRAP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bootstrap = _load_bootstrap()


@pytest.fixture
def secrets_dir(tmp_path, monkeypatch):
    directory = tmp_path / "secrets"
    monkeypatch.setenv("OBJECTSTORE_SECRETS_DIR", str(directory))
    # M4-06: the service keys live in volumes of their own.
    monkeypatch.setenv("OBJECTSTORE_JOBS_KEY_DIR", str(tmp_path / "keys-jobs"))
    monkeypatch.setenv("OBJECTSTORE_API_KEY_DIR", str(tmp_path / "keys-api"))
    for var in ("S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_BUCKET"):
        monkeypatch.delenv(var, raising=False)
    return directory


class FakeAdminApi:
    """A minimal stand-in for Garage's admin API v2, driven by call sequence
    rather than a socket: `bootstrap._admin_request` is monkeypatched to
    `handle` below."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}
        self.key_names: dict[str, str] = {}
        self.buckets: dict[str, str] = {}
        self.permissions: dict[str, dict[str, bool]] = {}
        self.lifecycle_rules: dict[str, list] = {}
        self.import_calls = 0
        self.create_calls = 0
        self.allow_calls = 0
        self.update_calls = 0
        self._next_error: tuple[int, dict] | None = None
        self._next_import_error: tuple[int, dict] | None = None
        self.drop_lifecycle_rules = False

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
            if self._next_import_error is not None:
                status, info = self._next_import_error
                self._next_import_error = None
                return status, info
            self.import_calls += 1
            self.keys[body["accessKeyId"]] = body["secretAccessKey"]
            self.key_names[body["accessKeyId"]] = body["name"]
            return 201, {"accessKeyId": body["accessKeyId"]}

        if path.startswith("/v2/GetBucketInfo?id="):
            bucket_id = path.split("id=")[1]
            rules = [] if self.drop_lifecycle_rules else self.lifecycle_rules.get(bucket_id, [])
            return 200, {"id": bucket_id, "lifecycleRules": rules}

        if path.startswith("/v2/UpdateBucket?id="):
            self.update_calls += 1
            bucket_id = path.split("id=")[1]
            self.lifecycle_rules[bucket_id] = body["lifecycleRules"]
            return 200, {"id": bucket_id, "lifecycleRules": body["lifecycleRules"]}

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

        if path in ("/v2/AllowBucketKey", "/v2/DenyBucketKey"):
            allow = path == "/v2/AllowBucketKey"
            self.allow_calls += allow
            granted = self.permissions.setdefault(body["accessKeyId"], {"read": False, "write": False, "owner": False})
            for name, flag in body["permissions"].items():
                if flag:
                    granted[name] = allow
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
    # rpc_secret is not read by `init` (only Garage itself uses it), but a
    # real secrets volume always has all four files, so tests that check
    # "no credential in the output" (_all_credentials) expect it here too.
    (secrets_dir / "rpc_secret").write_text("test-rpc-secret")
    (secrets_dir / "admin_token").write_text("test-admin-token")
    (secrets_dir / "s3_access_key").write_text("a-valid-access-key")
    (secrets_dir / "s3_secret_key").write_text(secret_key)
    (secrets_dir / "s3_bucket").write_text("earthx")
    for label in ("jobs", "api"):
        directory = secrets_dir.parent / f"keys-{label}"
        directory.mkdir(exist_ok=True)
        (directory / "access_key").write_text(f"GK{label}servicekey0001")
        (directory / "secret_key").write_text(f"{label}-service-secret-0000000000")


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

    assert fake_admin.import_calls == 3
    assert fake_admin.create_calls == 1
    assert fake_admin.allow_calls == 3
    assert fake_admin.keys["a-valid-access-key"] == "a-sixteen-char-secret"
    assert "earthx" in fake_admin.buckets


def test_init_second_run_does_not_recreate_key_or_bucket(secrets_dir, fake_admin):
    _write_secrets_for_init(secrets_dir)

    bootstrap.cmd_init(init_args())
    bootstrap.cmd_init(init_args())

    assert fake_admin.import_calls == 3
    assert fake_admin.create_calls == 1
    assert fake_admin.allow_calls == 6  # granted again each run; idempotent on Garage's side


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


def _all_credentials(directory: Path) -> list[str]:
    """Every value that must never reach stdout/stderr from `secrets` or
    `init`. This is deliberately wider than "secret": `objectstore-secrets`
    and `objectstore-init` run as `docker compose up` services, so their
    output lands in `docker compose logs` and, in CI, in a log GitHub serves
    publicly (the repo is public, ENTSCHEIDUNGEN_2026-09-18.md §4) — the
    access key id is not classified as a secret, but it identifies this run's
    credentials just as precisely, so it is withheld from these two
    subcommands too. Only `show`, run by hand, is meant to print it.
    """
    return [
        (directory / name).read_text().strip()
        for name in ("rpc_secret", "admin_token", "s3_access_key", "s3_secret_key")
    ] + [
        (directory.parent / f"keys-{label}" / name).read_text().strip()
        for label in ("jobs", "api")
        for name in ("access_key", "secret_key")
    ]


def test_secrets_output_never_contains_any_credential_when_generated(secrets_dir, capsys):
    bootstrap.main(["secrets"])
    credentials = _all_credentials(secrets_dir)

    captured = capsys.readouterr()
    for value in credentials:
        assert value not in captured.out
        assert value not in captured.err


def test_secrets_output_never_contains_any_credential_on_a_second_run(secrets_dir, capsys):
    bootstrap.main(["secrets"])
    capsys.readouterr()  # discard the first run's output
    bootstrap.main(["secrets"])  # the "already present, unchanged" branch
    credentials = _all_credentials(secrets_dir)

    captured = capsys.readouterr()
    for value in credentials:
        assert value not in captured.out
        assert value not in captured.err


def test_secrets_output_never_contains_a_credential_given_via_env(secrets_dir, monkeypatch, capsys):
    monkeypatch.setenv("S3_ACCESS_KEY", "my-access-key")
    monkeypatch.setenv("S3_SECRET_KEY", "a-sixteen-char-secret")
    bootstrap.main(["secrets"])

    captured = capsys.readouterr()
    assert "my-access-key" not in captured.out
    assert "a-sixteen-char-secret" not in captured.out


def test_init_successful_run_output_never_contains_any_credential(secrets_dir, fake_admin, capsys):
    _write_secrets_for_init(secrets_dir)
    bootstrap.cmd_init(init_args())
    credentials = _all_credentials(secrets_dir)

    captured = capsys.readouterr()
    for value in credentials:
        assert value not in captured.out
        assert value not in captured.err


def test_init_output_never_contains_credentials_even_when_reflected_in_an_error(
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


# --- M4-06: service keys and the lifecycle rule (adr/0015 §6.4, §7.3) -------


def _service_key(secrets_dir: Path, label: str, name: str = "access_key") -> str:
    return (secrets_dir.parent / f"keys-{label}" / name).read_text().strip()


def test_secrets_creates_both_service_keys_in_their_own_directories(secrets_dir):
    assert bootstrap.main(["secrets"]) == 0

    seen = set()
    for label in ("jobs", "api"):
        directory = secrets_dir.parent / f"keys-{label}"
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        assert sorted(p.name for p in directory.iterdir()) == ["access_key", "secret_key"]
        for name in ("access_key", "secret_key"):
            assert stat.S_IMODE((directory / name).stat().st_mode) == 0o600
        access_key = _service_key(secrets_dir, label)
        assert re.match(r"^GK[0-9a-f]{24}$", access_key)
        assert re.match(r"^[0-9a-f]{64}$", _service_key(secrets_dir, label, "secret_key"))
        seen.add(access_key)
    seen.add((secrets_dir / "s3_access_key").read_text().strip())
    assert len(seen) == 3


def test_secrets_second_run_keeps_the_service_keys(secrets_dir):
    assert bootstrap.main(["secrets"]) == 0
    before = {label: _service_key(secrets_dir, label, "secret_key") for label in ("jobs", "api")}
    assert bootstrap.main(["secrets"]) == 0
    assert {label: _service_key(secrets_dir, label, "secret_key") for label in ("jobs", "api")} == before


def test_the_service_keys_never_come_from_env(secrets_dir, monkeypatch):
    """adr/0015 §9.1: `.env` pins only the owner key; the service keys are always generated."""
    monkeypatch.setenv("S3_ACCESS_KEY", "my-access-key")
    monkeypatch.setenv("S3_SECRET_KEY", "a-sixteen-char-secret")
    assert bootstrap.main(["secrets"]) == 0
    for label in ("jobs", "api"):
        assert _service_key(secrets_dir, label) != "my-access-key"
        assert _service_key(secrets_dir, label, "secret_key") != "a-sixteen-char-secret"


def test_secrets_refuses_half_a_service_key(secrets_dir, capsys):
    assert bootstrap.main(["secrets"]) == 0
    (secrets_dir.parent / "keys-api" / "secret_key").unlink()
    assert bootstrap.main(["secrets"]) == 1
    assert "api service key" in capsys.readouterr().err


def test_init_gives_each_key_exactly_its_rights(secrets_dir, fake_admin):
    _write_secrets_for_init(secrets_dir)
    bootstrap.cmd_init(init_args())

    jobs, api = _service_key(secrets_dir, "jobs"), _service_key(secrets_dir, "api")
    assert fake_admin.key_names[jobs] == "earthx-jobs"
    assert fake_admin.key_names[api] == "earthx-api"
    assert fake_admin.permissions[jobs] == {"read": True, "write": True, "owner": False}
    assert fake_admin.permissions[api] == {"read": True, "write": False, "owner": False}
    assert fake_admin.permissions["a-valid-access-key"] == {"read": True, "write": True, "owner": True}


def test_init_takes_rights_away_from_an_api_key_that_had_more(secrets_dir, fake_admin):
    _write_secrets_for_init(secrets_dir)
    api = _service_key(secrets_dir, "api")
    fake_admin.permissions[api] = {"read": True, "write": True, "owner": True}

    bootstrap.cmd_init(init_args())

    assert fake_admin.permissions[api] == {"read": True, "write": False, "owner": False}


def test_init_sets_exactly_the_results_rule_and_says_so(secrets_dir, fake_admin, capsys):
    _write_secrets_for_init(secrets_dir)
    bucket_id = "bucket-1"
    fake_admin.lifecycle_rules[bucket_id] = [{"ID": "expire-results", "Status": "Enabled", "Filter": {"Prefix": "smoke/"}}]

    bootstrap.cmd_init(init_args())

    assert fake_admin.lifecycle_rules[bucket_id] == [
        {
            "ID": "results-7d",
            "Status": "Enabled",
            "Filter": {"Prefix": "results/"},
            "Expiration": {"Days": 7},
            "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
        }
    ]
    out = capsys.readouterr().out
    assert (
        "objectstore-init: lifecycle rule results-7d set (prefix results/, expire after 7 days, "
        "abort multipart after 1 day)"
    ) in out.splitlines()


def test_init_sets_the_rule_again_on_every_run(secrets_dir, fake_admin):
    _write_secrets_for_init(secrets_dir)
    bootstrap.cmd_init(init_args())
    bootstrap.cmd_init(init_args())
    assert fake_admin.update_calls == 2
    assert fake_admin.import_calls == 3


def test_init_fails_when_the_rule_does_not_read_back(secrets_dir, fake_admin):
    _write_secrets_for_init(secrets_dir)
    fake_admin.drop_lifecycle_rules = True
    with pytest.raises(bootstrap.BootstrapError, match="did not read back"):
        bootstrap.cmd_init(init_args())


@pytest.mark.parametrize("label", ["owner", "jobs", "api"])
def test_a_key_with_a_different_secret_is_refused_without_naming_its_id(secrets_dir, fake_admin, label):
    _write_secrets_for_init(secrets_dir)
    key_id = "a-valid-access-key" if label == "owner" else _service_key(secrets_dir, label)
    fake_admin.keys[key_id] = "a-completely-different-secret"

    with pytest.raises(bootstrap.BootstrapError, match="different secret") as excinfo:
        bootstrap.cmd_init(init_args())
    assert key_id not in str(excinfo.value)


def test_a_failed_service_key_import_echoing_credentials_is_redacted(secrets_dir, fake_admin):
    _write_secrets_for_init(secrets_dir)
    jobs_id = _service_key(secrets_dir, "jobs")
    jobs_secret = _service_key(secrets_dir, "jobs", "secret_key")
    fake_admin.keys["a-valid-access-key"] = "a-sixteen-char-secret"  # owner key already there
    fake_admin._next_import_error = (400, {"error": f"bad key {jobs_id} / {jobs_secret} / test-admin-token"})

    with pytest.raises(bootstrap.BootstrapError) as excinfo:
        bootstrap.cmd_init(init_args())
    for value in (jobs_id, jobs_secret, "test-admin-token"):
        assert value not in str(excinfo.value)


def test_show_prints_the_service_keys_under_their_own_names(secrets_dir, capsys):
    bootstrap.main(["secrets"])
    capsys.readouterr()
    assert bootstrap.main(["show"]) == 0
    out = capsys.readouterr().out
    for label in ("jobs", "api"):
        assert f"S3_{label.upper()}_ACCESS_KEY={_service_key(secrets_dir, label)}" in out
        assert f"S3_{label.upper()}_SECRET_KEY={_service_key(secrets_dir, label, 'secret_key')}" in out
