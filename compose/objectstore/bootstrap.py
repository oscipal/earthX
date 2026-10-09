#!/usr/bin/env python3
"""Bootstrap the `objectstore` (Garage) service for the compose topology.

M3-23 (adr/0012). This is operational code for the compose topology, not
part of the EarthX application: it lives outside `backend/earthx/`, no
platform module imports it, and it uses only the standard library. It talks
exclusively to the `objectstore` service inside the compose network — the
same network the healthchecks already reach with `curl` — never to a data
source, so it does not fall under `gateway` (KLAERUNGEN B8: that rule covers
how the *application* reaches data sources). How the application itself will
reach the object store is `earthx.objectstore` (M4-06, adr/0015); this
script only prepares the store for it: the keys `api` and `worker` use, and the
bucket rule the worker checks before it starts.

Garage's image is `FROM scratch` (no shell, no curl), so this script cannot
run *inside* that container. Instead it runs as two one-shot steps built
from the backend image, before and after Garage starts:

  secrets   Generate the RPC secret, admin token and (unless given via env)
            the S3 access key/secret, as 0600 files in a shared volume; and
            the two service keys (M4-06, adr/0015 §6.4), each into a volume of
            its own. Idempotent: existing files are never overwritten.
  init      Against Garage's already-running admin API, import the S3 key
            and create the bucket if missing, then grant the key full
            access; import the service keys with their own rights (`jobs`
            reads and writes, `api` only reads) and set the lifecycle rule
            for `results/` (adr/0015 §7.3). Idempotent.
  show      Print the S3 access key id and secret from the secrets volume,
            and the two service keys, for a person to use locally (e.g. with
            the `aws` CLI) and for the CI smoke step, which masks them. Never
            written to a log by the other subcommands.

Neither `secrets` nor `init` ever print a credential — not the RPC secret,
the admin token, the S3 secret key, or even the access key id, since
`docker compose up` runs them as services and their output lands in
`docker compose logs` and, in CI, in a log GitHub serves publicly (the repo
is public, ENTSCHEIDUNGEN_2026-09-18.md §4). `show` is the one subcommand a
human runs interactively, on their own terminal, for that reason.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets as secrets_module
import stat
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple

from redact import redact

# Garage's own limits (src/model/key_table.rs, v2.4.1): enforced here too so
# a bad `.env` value fails fast, before Garage itself rejects it.
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,}$")
_SECRET_RE = re.compile(r"^[\x21-\x7e]{16,}$")
# A deliberately narrow S3 bucket name check (AWS's own rule is more
# permissive with dots and IPv4-looking names, neither of which this
# platform needs): 3-63 chars, lowercase alphanumeric and hyphens, not
# starting or ending with a hyphen.
_BUCKET_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61})[a-z0-9]$")

DEFAULT_BUCKET = "earthx"
KEY_NAME = "earthx-platform"


class ServiceKey(NamedTuple):
    """A key one process uses (adr/0015 §6.4, plan M4-06 F3): always generated,
    never from `.env`, in a volume only that process mounts."""

    label: str
    name: str
    dir_env: str
    default_dir: str
    permissions: dict[str, bool]

    def directory(self) -> Path:
        return Path(os.environ.get(self.dir_env, self.default_dir))


SERVICE_KEYS = (
    # `worker` writes and deletes results; it may not own the bucket.
    ServiceKey(
        "jobs", "earthx-jobs", "OBJECTSTORE_JOBS_KEY_DIR", "/keys/jobs", {"read": True, "write": True, "owner": False}
    ),
    # `api` only signs GET URLs: a URL signed with it can neither write nor delete (§3.3).
    ServiceKey(
        "api", "earthx-api", "OBJECTSTORE_API_KEY_DIR", "/keys/api", {"read": True, "write": False, "owner": False}
    ),
)

# adr/0015 §7.3. The worker recognises it by content, not by its ID (plan M4-06 F4).
LIFECYCLE_RULE = {
    "ID": "results-7d",
    "Status": "Enabled",
    "Filter": {"Prefix": "results/"},
    "Expiration": {"Days": 7},
    "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
}


class BootstrapError(RuntimeError):
    """Raised for any condition that should stop the compose topology."""


def _secrets_dir() -> Path:
    return Path(os.environ.get("OBJECTSTORE_SECRETS_DIR", "/secrets"))


def _write_secret_file(path: Path, value: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(value)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _read_secret_file(path: Path) -> str:
    return path.read_text().strip()


def _validate_key_id(key_id: str) -> None:
    if not _KEY_ID_RE.match(key_id):
        raise BootstrapError(
            "S3_ACCESS_KEY must be at least 8 characters, using only "
            "letters, digits, '-', '_' and '.' (Garage's own rule)."
        )


def _validate_secret(secret: str) -> None:
    if not _SECRET_RE.match(secret):
        raise BootstrapError(
            "S3_SECRET_KEY must be at least 16 printable ASCII characters, "
            "with no whitespace (Garage's own rule)."
        )


def _validate_bucket(bucket: str) -> None:
    if not _BUCKET_RE.match(bucket):
        raise BootstrapError(
            f"S3_BUCKET {bucket!r} is not a valid bucket name (3-63 lowercase "
            "letters, digits or hyphens, not starting or ending in a hyphen)."
        )


def cmd_secrets(_: argparse.Namespace) -> None:
    """Create any missing secret files. Never overwrites an existing one."""
    directory = _secrets_dir()
    directory.mkdir(parents=True, exist_ok=True)
    if stat.S_IMODE(directory.stat().st_mode) & 0o077:
        directory.chmod(0o700)

    access_key_env = os.environ.get("S3_ACCESS_KEY", "").strip()
    secret_key_env = os.environ.get("S3_SECRET_KEY", "").strip()
    if bool(access_key_env) != bool(secret_key_env):
        raise BootstrapError(
            "Set both S3_ACCESS_KEY and S3_SECRET_KEY, or neither (to have "
            "them generated)."
        )

    bucket = os.environ.get("S3_BUCKET", "").strip() or DEFAULT_BUCKET
    _validate_bucket(bucket)

    rpc_secret_path = directory / "rpc_secret"
    if not rpc_secret_path.exists():
        _write_secret_file(rpc_secret_path, secrets_module.token_hex(32))
        print("objectstore-secrets: generated rpc_secret")

    admin_token_path = directory / "admin_token"
    if not admin_token_path.exists():
        _write_secret_file(admin_token_path, secrets_module.token_urlsafe(32))
        print("objectstore-secrets: generated admin_token")

    access_key_path = directory / "s3_access_key"
    secret_key_path = directory / "s3_secret_key"
    if access_key_path.exists() or secret_key_path.exists():
        if not (access_key_path.exists() and secret_key_path.exists()):
            raise BootstrapError(
                "Only one of s3_access_key/s3_secret_key exists in the "
                "secrets volume; remove both to regenerate, or restore the "
                "missing file."
            )
        if access_key_env and _read_secret_file(access_key_path) != access_key_env:
            raise BootstrapError(
                "S3_ACCESS_KEY in .env does not match the key already "
                "stored in the secrets volume. Either unset it or delete "
                "the objectstore-secrets volume (this deletes no data, "
                "only credentials)."
            )
        print("objectstore-secrets: S3 key already present, unchanged")
    else:
        if access_key_env:
            _validate_key_id(access_key_env)
            _validate_secret(secret_key_env)
            access_key, secret_key = access_key_env, secret_key_env
            source = ".env"
        else:
            access_key = "GK" + secrets_module.token_hex(12)
            secret_key = secrets_module.token_hex(32)
            source = "generated"
        _write_secret_file(access_key_path, access_key)
        _write_secret_file(secret_key_path, secret_key)
        # Not even the access key id goes to stdout here: this is a service
        # started by `docker compose up`, so its output lands in
        # `docker compose logs` and, in CI, in a log GitHub serves publicly
        # (the repo is public, ENTSCHEIDUNGEN_2026-09-18.md §4). The `show`
        # subcommand below is the one place credentials are printed, and only
        # for a person to run by hand on their own terminal.
        print(f"objectstore-secrets: S3 key created ({source})")

    bucket_path = directory / "s3_bucket"
    if not bucket_path.exists():
        _write_secret_file(bucket_path, bucket)
    elif _read_secret_file(bucket_path) != bucket:
        raise BootstrapError(
            f"S3_BUCKET changed from {_read_secret_file(bucket_path)!r} to "
            f"{bucket!r}; Garage does not rename buckets. Delete the "
            "objectstore-secrets volume to start over, or set S3_BUCKET "
            "back."
        )

    for key in SERVICE_KEYS:
        _ensure_service_key(key)


def _ensure_service_key(key: ServiceKey) -> None:
    directory = key.directory()
    directory.mkdir(parents=True, exist_ok=True)
    if stat.S_IMODE(directory.stat().st_mode) & 0o077:
        directory.chmod(0o700)
    access_key_path = directory / "access_key"
    secret_key_path = directory / "secret_key"
    if access_key_path.exists() and secret_key_path.exists():
        print(f"objectstore-secrets: service key for {key.label} already present, unchanged")
        return
    if access_key_path.exists() or secret_key_path.exists():
        raise BootstrapError(
            f"Only one of access_key/secret_key exists for the {key.label} service "
            "key; remove both to regenerate, or restore the missing file."
        )
    _write_secret_file(access_key_path, "GK" + secrets_module.token_hex(12))
    _write_secret_file(secret_key_path, secrets_module.token_hex(32))
    print(f"objectstore-secrets: service key for {key.label} created")


def _admin_request(
    base_url: str, token: str, method: str, path: str, body: dict | None = None
) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = resp.read()
            return resp.status, (json.loads(payload) if payload else {})
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            return exc.code, json.loads(payload)
        except json.JSONDecodeError:
            return exc.code, {"error": payload.decode(errors="replace")}


def _wait_for_admin_api(base_url: str, token: str, attempts: int, delay: float) -> None:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            status, _ = _admin_request(base_url, token, "GET", "/v2/GetClusterHealth")
            if status < 500:
                return
        except OSError as exc:  # connection refused, DNS not ready yet, ...
            last_error = exc
        time.sleep(delay)
    raise BootstrapError(
        f"objectstore admin API at {base_url} did not answer after "
        f"{attempts} attempts: {last_error}"
    )


def cmd_init(args: argparse.Namespace) -> None:
    """Import the S3 key and create the bucket, over the admin API."""
    directory = _secrets_dir()
    admin_token = _read_secret_file(directory / "admin_token")
    access_key = _read_secret_file(directory / "s3_access_key")
    secret_key = _read_secret_file(directory / "s3_secret_key")
    bucket = _read_secret_file(directory / "s3_bucket")
    base_url = args.admin_url

    # The admin API could in principle echo the token, the secret or the
    # access key id back inside an error body (e.g. "invalid Authorization:
    # Bearer <token>"); every error text built from a response goes through
    # this before it can reach an exception message, stdout or a log.
    def error_text(status: int, info: dict) -> str:
        return redact(f"{status}: {info.get('error', info)}", admin_token, secret_key, access_key)

    _wait_for_admin_api(base_url, admin_token, args.attempts, args.delay)

    status, info = _admin_request(
        base_url, admin_token, "GET", f"/v2/GetKeyInfo?id={access_key}&showSecretKey=true"
    )
    if status == 404:
        status, info = _admin_request(
            base_url,
            admin_token,
            "POST",
            "/v2/ImportKey",
            {"accessKeyId": access_key, "secretAccessKey": secret_key, "name": KEY_NAME},
        )
        if status not in (200, 201):
            raise BootstrapError(f"ImportKey failed ({error_text(status, info)})")
        print("objectstore-init: imported S3 key")
    elif status == 200:
        existing_secret = info.get("secretAccessKey")
        if existing_secret is not None and existing_secret != secret_key:
            # No key id here: this error lands in `docker compose logs` and the CI log.
            raise BootstrapError(
                f"S3 key {KEY_NAME} already exists in Garage with a "
                "different secret than the one in the secrets volume. "
                "Refusing to overwrite it."
            )
        print("objectstore-init: S3 key already imported")
    else:
        raise BootstrapError(f"GetKeyInfo failed ({error_text(status, info)})")

    status, info = _admin_request(
        base_url, admin_token, "GET", f"/v2/GetBucketInfo?globalAlias={bucket}"
    )
    if status == 404:
        status, info = _admin_request(
            base_url, admin_token, "POST", "/v2/CreateBucket", {"globalAlias": bucket}
        )
        if status not in (200, 201):
            raise BootstrapError(f"CreateBucket failed ({error_text(status, info)})")
        print(f"objectstore-init: created bucket {bucket}")
        bucket_id = info["id"]
    elif status == 200:
        print(f"objectstore-init: bucket {bucket} already exists")
        bucket_id = info["id"]
    else:
        raise BootstrapError(f"GetBucketInfo failed ({error_text(status, info)})")

    status, info = _admin_request(
        base_url,
        admin_token,
        "POST",
        "/v2/AllowBucketKey",
        {
            "bucketId": bucket_id,
            "accessKeyId": access_key,
            "permissions": {"read": True, "write": True, "owner": True},
        },
    )
    if status != 200:
        raise BootstrapError(f"AllowBucketKey failed ({error_text(status, info)})")
    print("objectstore-init: granted key access to the bucket")

    for key in SERVICE_KEYS:
        _init_service_key(base_url, admin_token, bucket_id, key, error_text)

    _set_lifecycle_rule(base_url, admin_token, bucket_id, error_text)


def _init_service_key(base_url: str, admin_token: str, bucket_id: str, key: ServiceKey, error_text) -> None:
    """Import one service key and give it exactly its rights on the bucket.

    Allow what it needs, then deny the rest: a key from an earlier run with
    more rights loses them (plan M4-06, Kleinentscheidung).
    """
    directory = key.directory()
    access_key = _read_secret_file(directory / "access_key")
    secret_key = _read_secret_file(directory / "secret_key")

    def text(status: int, info: dict) -> str:
        return redact(error_text(status, info), access_key, secret_key)

    status, info = _admin_request(base_url, admin_token, "GET", f"/v2/GetKeyInfo?id={access_key}&showSecretKey=true")
    if status == 404:
        status, info = _admin_request(
            base_url,
            admin_token,
            "POST",
            "/v2/ImportKey",
            {"accessKeyId": access_key, "secretAccessKey": secret_key, "name": key.name},
        )
        if status not in (200, 201):
            raise BootstrapError(f"ImportKey for {key.label} failed ({text(status, info)})")
        print(f"objectstore-init: imported service key for {key.label}")
    elif status == 200:
        existing_secret = info.get("secretAccessKey")
        if existing_secret is not None and existing_secret != secret_key:
            raise BootstrapError(
                f"Service key {key.name} already exists in Garage with a different "
                "secret than the one in its volume. Refusing to overwrite it."
            )
        print(f"objectstore-init: service key for {key.label} already imported")
    else:
        raise BootstrapError(f"GetKeyInfo for {key.label} failed ({text(status, info)})")

    allow = {name: value for name, value in key.permissions.items() if value}
    deny = {name: True for name, value in key.permissions.items() if not value}
    for endpoint, permissions in (("/v2/AllowBucketKey", allow), ("/v2/DenyBucketKey", deny)):
        status, info = _admin_request(
            base_url,
            admin_token,
            "POST",
            endpoint,
            {"bucketId": bucket_id, "accessKeyId": access_key, "permissions": permissions},
        )
        if status != 200:
            raise BootstrapError(f"{endpoint.rsplit('/', 1)[1]} for {key.label} failed ({text(status, info)})")
    rights = ", ".join(name for name in ("read", "write", "owner") if key.permissions[name])
    print(f"objectstore-init: service key for {key.label} may {rights}")


def _is_lifecycle_rule(rule: dict) -> bool:
    """The rule of adr/0015 §7.3, by content (the same test as `earthx.objectstore`)."""
    filter_ = rule.get("Filter") or {}
    return (
        rule.get("Status") == "Enabled"
        and set(filter_) == {"Prefix"}
        and filter_.get("Prefix") == LIFECYCLE_RULE["Filter"]["Prefix"]
        and (rule.get("Expiration") or {}).get("Days") == LIFECYCLE_RULE["Expiration"]["Days"]
        and (rule.get("AbortIncompleteMultipartUpload") or {}).get("DaysAfterInitiation")
        == LIFECYCLE_RULE["AbortIncompleteMultipartUpload"]["DaysAfterInitiation"]
    )


def _set_lifecycle_rule(base_url: str, admin_token: str, bucket_id: str, error_text) -> None:
    """Set the bucket's lifecycle rules to exactly the `results/` rule, then read them back.

    Over the admin API (adr/0015 §7.3, W1): the application's keys never change the
    bucket configuration. Further prefixes get rules of their own when they arise.
    """
    status, info = _admin_request(
        base_url, admin_token, "POST", f"/v2/UpdateBucket?id={bucket_id}", {"lifecycleRules": [LIFECYCLE_RULE]}
    )
    if status != 200:
        raise BootstrapError(f"UpdateBucket failed ({error_text(status, info)})")
    status, info = _admin_request(base_url, admin_token, "GET", f"/v2/GetBucketInfo?id={bucket_id}")
    if status != 200:
        raise BootstrapError(f"GetBucketInfo failed ({error_text(status, info)})")
    rules = [rule for rule in info.get("lifecycleRules") or [] if _is_lifecycle_rule(rule)]
    if not rules:
        raise BootstrapError("the lifecycle rule for results/ did not read back after UpdateBucket")
    rule = rules[0]
    print(
        f"objectstore-init: lifecycle rule {rule.get('ID', '(no id)')} set "
        f"(prefix {rule['Filter']['Prefix']}, expire after {rule['Expiration']['Days']} days, "
        f"abort multipart after {rule['AbortIncompleteMultipartUpload']['DaysAfterInitiation']} day)"
    )


def cmd_show(_: argparse.Namespace) -> None:
    """Print the S3 access key and secret, and the two service keys."""
    directory = _secrets_dir()
    access_key = _read_secret_file(directory / "s3_access_key")
    secret_key = _read_secret_file(directory / "s3_secret_key")
    bucket = _read_secret_file(directory / "s3_bucket")
    print(f"S3_ACCESS_KEY={access_key}")
    print(f"S3_SECRET_KEY={secret_key}")
    print(f"S3_BUCKET={bucket}")
    for key in SERVICE_KEYS:
        prefix = f"S3_{key.label.upper()}"
        print(f"{prefix}_ACCESS_KEY={_read_secret_file(key.directory() / 'access_key')}")
        print(f"{prefix}_SECRET_KEY={_read_secret_file(key.directory() / 'secret_key')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("secrets", help="Generate missing secret files.")

    init_parser = subparsers.add_parser("init", help="Create the S3 key and bucket.")
    init_parser.add_argument(
        "--admin-url", default=os.environ.get("OBJECTSTORE_ADMIN_URL", "http://objectstore:3903")
    )
    init_parser.add_argument("--attempts", type=int, default=30)
    init_parser.add_argument("--delay", type=float, default=2.0)

    subparsers.add_parser("show", help="Print the S3 credentials.")

    args = parser.parse_args(argv)
    handler = {"secrets": cmd_secrets, "init": cmd_init, "show": cmd_show}[args.command]
    try:
        handler(args)
    except BootstrapError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
