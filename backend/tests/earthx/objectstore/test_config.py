"""`StoreConfig` comes only from S3_* and never prints a value (adr/0015 §9.1, F2, F12)."""

from __future__ import annotations

from pathlib import Path

import pytest

from earthx.objectstore.config import StoreConfig
from earthx.objectstore.errors import StoreConfigError

from .conftest import ACCESS_KEY, SECRET_KEY


def _error(env: dict[str, str]) -> str:
    with pytest.raises(StoreConfigError) as caught:
        StoreConfig.from_environ(env)
    return str(caught.value)


def test_a_complete_environment_is_read(store_env: dict[str, str]) -> None:
    config = StoreConfig.from_environ(store_env)
    assert config.endpoint == "http://objectstore:3900"
    assert config.public_endpoint == "http://localhost:3900"
    assert (config.region, config.bucket) == ("garage", "earthx")
    assert (config.access_key, config.secret_key) == (ACCESS_KEY, SECRET_KEY)
    assert (config.addressing_style, config.lifecycle_check) == ("path", "required")


def test_the_repr_shows_no_value(store_env: dict[str, str]) -> None:
    text = repr(StoreConfig.from_environ(store_env)) + str(StoreConfig.from_environ(store_env))
    for value in (ACCESS_KEY, SECRET_KEY, "objectstore", "localhost", "earthx", "garage"):
        assert value not in text


def test_keys_can_come_as_values(store_env: dict[str, str]) -> None:
    del store_env["S3_ACCESS_KEY_FILE"], store_env["S3_SECRET_KEY_FILE"]
    store_env |= {"S3_ACCESS_KEY": ACCESS_KEY, "S3_SECRET_KEY": SECRET_KEY}
    config = StoreConfig.from_environ(store_env)
    assert (config.access_key, config.secret_key) == (ACCESS_KEY, SECRET_KEY)


@pytest.mark.parametrize(
    "name",
    ["S3_ENDPOINT", "S3_PUBLIC_ENDPOINT", "S3_REGION", "S3_BUCKET", "S3_ACCESS_KEY_FILE", "S3_SECRET_KEY_FILE"],
)
def test_a_missing_variable_is_named_without_any_value(store_env: dict[str, str], name: str) -> None:
    del store_env[name]
    message = _error(store_env)
    assert name.removesuffix("_FILE") in message
    for value in (ACCESS_KEY, SECRET_KEY, "objectstore:3900", "localhost:3900"):
        assert value not in message


def test_an_empty_value_counts_as_unset(store_env: dict[str, str]) -> None:
    store_env["S3_BUCKET"] = "  "
    assert "S3_BUCKET is not set" in _error(store_env)


def test_the_aws_names_are_never_read(store_env: dict[str, str]) -> None:
    """rasterio hands AWS_* to GDAL in every process (adr/0015 §3.1); the module uses S3_* only."""
    del store_env["S3_ACCESS_KEY_FILE"], store_env["S3_SECRET_KEY_FILE"]
    store_env |= {"AWS_ACCESS_KEY_ID": ACCESS_KEY, "AWS_SECRET_ACCESS_KEY": SECRET_KEY}
    assert "S3_ACCESS_KEY" in _error(store_env)


def test_value_and_file_together_are_refused(store_env: dict[str, str]) -> None:
    store_env["S3_SECRET_KEY"] = SECRET_KEY
    message = _error(store_env)
    assert "S3_SECRET_KEY" in message and "not both" in message
    assert SECRET_KEY not in message


def test_an_unreadable_key_file_is_named_not_shown(store_env: dict[str, str], tmp_path: Path) -> None:
    store_env["S3_SECRET_KEY_FILE"] = str(tmp_path / "missing")
    message = _error(store_env)
    assert "S3_SECRET_KEY_FILE" in message
    assert str(tmp_path) not in message


def test_an_empty_key_file_is_refused(store_env: dict[str, str]) -> None:
    Path(store_env["S3_ACCESS_KEY_FILE"]).write_text("\n")
    assert "S3_ACCESS_KEY_FILE names an empty file" in _error(store_env)


@pytest.mark.parametrize(
    "endpoint",
    [
        "objectstore:3900",
        "ftp://objectstore:3900",
        "http://objectstore:3900/bucket",
        "http://objectstore:3900?x=1",
        "http://user:pass@objectstore:3900",
        "http://objectstore:0",
        "http://objectstore:70000",
        "http://-objectstore",
        "http://objectstore:3900#frag",
    ],
)
def test_an_endpoint_with_more_than_scheme_host_and_port_is_refused(store_env: dict[str, str], endpoint: str) -> None:
    store_env["S3_ENDPOINT"] = endpoint
    message = _error(store_env)
    assert "S3_ENDPOINT" in message
    assert endpoint not in message


@pytest.mark.parametrize(
    "endpoint", ["http://objectstore:3900/", "https://s3.example.eu", "http://[::1]:3900", "http://10.0.0.5:3900"]
)
def test_a_plain_endpoint_is_accepted(store_env: dict[str, str], endpoint: str) -> None:
    store_env["S3_ENDPOINT"] = endpoint
    assert StoreConfig.from_environ(store_env).endpoint == endpoint.rstrip("/")


@pytest.mark.parametrize("endpoint", ["http://s3.example.eu", "http://objectstore:3900", "http://[::1]:3900"])
def test_the_public_endpoint_needs_https_unless_local(store_env: dict[str, str], endpoint: str) -> None:
    store_env["S3_PUBLIC_ENDPOINT"] = endpoint
    assert "S3_PUBLIC_ENDPOINT must use https" in _error(store_env)


@pytest.mark.parametrize("endpoint", ["https://s3.example.eu", "http://127.0.0.1:3900", "http://LOCALHOST:3900"])
def test_the_public_endpoint_accepts_https_and_local_http(store_env: dict[str, str], endpoint: str) -> None:
    store_env["S3_PUBLIC_ENDPOINT"] = endpoint
    assert StoreConfig.from_environ(store_env).public_endpoint == endpoint


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("S3_BUCKET", "Earthx"),
        ("S3_BUCKET", "xy"),
        ("S3_BUCKET", "earthx/../other"),
        ("S3_REGION", "eu central"),
        ("S3_ADDRESSING_STYLE", "auto"),
        ("S3_LIFECYCLE_CHECK", "false"),
    ],
)
def test_invalid_values_are_refused_by_name(store_env: dict[str, str], name: str, value: str) -> None:
    store_env[name] = value
    message = _error(store_env)
    assert name in message
    assert value not in message


def test_the_lifecycle_check_can_be_switched_off(store_env: dict[str, str]) -> None:
    store_env["S3_LIFECYCLE_CHECK"] = "off"
    assert StoreConfig.from_environ(store_env).lifecycle_check == "off"
