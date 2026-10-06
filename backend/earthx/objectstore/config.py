"""Where the object store is and which key this process uses (adr/0015 §9.1).

Read once, from the process environment, at start — never from a recipe, a
request or the database (Auflage F2). Only `S3_*` names: rasterio hands
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` to GDAL in every process as soon
as it builds an `AWSSession` (§3.1), so this module never reads them.

Each key comes either as a value (`S3_ACCESS_KEY`) or as a file
(`S3_ACCESS_KEY_FILE`), never both. Every error names the variable and never
its value, and :class:`StoreConfig` prints no field.

Endpoints are parsed with a pattern rather than `urllib.parse`: `urllib` is on
the client list of `http-only-in-gateway`, which covers this package too.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from earthx.objectstore.errors import StoreConfigError

ENDPOINT = "S3_ENDPOINT"
PUBLIC_ENDPOINT = "S3_PUBLIC_ENDPOINT"
REGION = "S3_REGION"
BUCKET = "S3_BUCKET"
ACCESS_KEY = "S3_ACCESS_KEY"
SECRET_KEY = "S3_SECRET_KEY"
ADDRESSING_STYLE = "S3_ADDRESSING_STYLE"
LIFECYCLE_CHECK = "S3_LIFECYCLE_CHECK"

ADDRESSING_STYLES = frozenset({"path", "virtual"})
LIFECYCLE_CHECKS = frozenset({"required", "off"})

# Scheme, host (name, IPv4 or bracketed IPv6), optional port, at most a trailing
# slash. No user part, path, query or fragment: a path would become part of
# every signature, and a user part would be a second place for a key.
_ENDPOINT_RE = re.compile(
    r"^(?P<scheme>https?)://"
    r"(?P<host>[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?|\[[0-9A-Fa-f:.]+\])"
    r"(?::(?P<port>[0-9]{1,5}))?/?$"
)
# Plain http only for a store on this machine (adr/0015 §6.3, Kleinentscheidung).
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})
_REGION_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
# Same rule as compose/objectstore/bootstrap.py.
_BUCKET_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61})[a-z0-9]$")


@dataclass(frozen=True, repr=False)
class StoreConfig:
    endpoint: str
    public_endpoint: str
    region: str
    bucket: str
    access_key: str
    secret_key: str
    addressing_style: str
    lifecycle_check: str

    def __repr__(self) -> str:
        return "StoreConfig(<from S3_* environment>)"

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] | None = None) -> StoreConfig:
        env = os.environ if environ is None else environ
        endpoint = _endpoint(env, ENDPOINT)
        public_endpoint = _endpoint(env, PUBLIC_ENDPOINT)
        if not public_endpoint.startswith("https://") and _host(public_endpoint) not in _LOCAL_HOSTS:
            raise StoreConfigError(f"{PUBLIC_ENDPOINT} must use https unless it is localhost or 127.0.0.1")
        return cls(
            endpoint=endpoint,
            public_endpoint=public_endpoint,
            region=_matching(env, REGION, _REGION_RE),
            bucket=_matching(env, BUCKET, _BUCKET_RE),
            access_key=_key(env, ACCESS_KEY),
            secret_key=_key(env, SECRET_KEY),
            addressing_style=_choice(env, ADDRESSING_STYLE, ADDRESSING_STYLES, "path"),
            lifecycle_check=_choice(env, LIFECYCLE_CHECK, LIFECYCLE_CHECKS, "required"),
        )


def _value(env: Mapping[str, str], name: str) -> str:
    """The stripped value, with an empty one treated as unset (compose passes `${X:-}`)."""
    return env.get(name, "").strip()


def _required(env: Mapping[str, str], name: str) -> str:
    value = _value(env, name)
    if not value:
        raise StoreConfigError(f"{name} is not set")
    return value


def _endpoint(env: Mapping[str, str], name: str) -> str:
    value = _required(env, name)
    match = _ENDPOINT_RE.match(value)
    if match is None or (match["port"] is not None and not 0 < int(match["port"]) < 65536):
        raise StoreConfigError(f"{name} must be http(s)://host[:port] with no path, query or user part")
    return value.rstrip("/")


def _host(endpoint: str) -> str:
    match = _ENDPOINT_RE.match(endpoint)
    assert match is not None
    return match["host"].lower()


def _matching(env: Mapping[str, str], name: str, pattern: re.Pattern[str]) -> str:
    value = _required(env, name)
    if not pattern.match(value):
        raise StoreConfigError(f"{name} is not valid")
    return value


def _choice(env: Mapping[str, str], name: str, allowed: frozenset[str], default: str) -> str:
    value = _value(env, name) or default
    if value not in allowed:
        raise StoreConfigError(f"{name} must be one of {', '.join(sorted(allowed))}")
    return value


def _key(env: Mapping[str, str], name: str) -> str:
    file_name = f"{name}_FILE"
    value, path = _value(env, name), _value(env, file_name)
    if value and path:
        raise StoreConfigError(f"set either {name} or {file_name}, not both")
    if path:
        try:
            value = Path(path).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            raise StoreConfigError(f"{file_name} names a file that cannot be read") from None
        if not value:
            raise StoreConfigError(f"{file_name} names an empty file")
    if not value:
        raise StoreConfigError(f"{name} or {file_name} is not set")
    return value
