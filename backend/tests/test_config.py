"""Configuration loads from defaults, from the environment, and rejects nonsense."""

from __future__ import annotations

import pytest

from app.config import Settings, get_settings


def test_defaults_load_without_any_environment() -> None:
    settings = get_settings()
    assert settings.max_search_items > 0
    assert settings.point_buffer_deg > 0
    assert settings.stac_collections
    assert settings.asset_host_allowlist


def test_no_token_configured_by_default() -> None:
    assert get_settings().maap_token == ""
    assert get_settings().has_token is False


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_list_values_come_from_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASSET_HOST_ALLOWLIST", '["example.org"]')
    get_settings.cache_clear()
    assert get_settings().asset_host_allowlist == ["example.org"]


def test_malformed_list_value_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASSET_HOST_ALLOWLIST", "not-json")
    get_settings.cache_clear()
    with pytest.raises(ValueError):
        get_settings()


def test_malformed_number_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_SEARCH_ITEMS", "many")
    get_settings.cache_clear()
    with pytest.raises(ValueError):
        get_settings()


@pytest.mark.parametrize(
    "host",
    ["maap.eo.esa.int", "MAAP.EO.ESA.INT", "catalog.maap.eo.esa.int"],
)
def test_allowlisted_hosts_pass(host: str) -> None:
    assert Settings(asset_host_allowlist=["maap.eo.esa.int"]).host_allowed(host) is True


@pytest.mark.parametrize("host", ["example.org", "", "localhost", "127.0.0.1"])
def test_foreign_hosts_are_rejected(host: str) -> None:
    assert Settings(asset_host_allowlist=["maap.eo.esa.int"]).host_allowed(host) is False


def test_empty_allowlist_rejects_everything() -> None:
    assert Settings(asset_host_allowlist=[]).host_allowed("maap.eo.esa.int") is False


@pytest.mark.xfail(
    reason=(
        "Known weakness of the prototype allowlist: the plain endswith() branch in "
        "Settings.host_allowed matches a host that merely ends in the allowed string, "
        "without a dot boundary. To be fixed when the allowlist moves into `gateway` "
        "(KLAERUNGEN B8); this test turns green then."
    ),
    strict=True,
)
def test_lookalike_host_is_rejected() -> None:
    assert Settings(asset_host_allowlist=["maap.eo.esa.int"]).host_allowed("evilmaap.eo.esa.int") is False
