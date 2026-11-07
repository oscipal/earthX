"""``access.account`` and its rules (adr/0027 §6.1, M5-13 plan §3.4 and §8a)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.registry import AccessInfo, AccountKind, AccountPath, ConfigError, DatasetConfig, LicenseTier
from tests.catalog.entries import REGISTRY

CHECKED = date(2026, 11, 7)


def _with(
    entry: DatasetConfig,
    account: AccountKind,
    *,
    tier: LicenseTier = LicenseTier.CATALOG,
    provider: str | None = None,
    checked: date | None = None,
    paths: tuple = (),
) -> DatasetConfig:
    """``entry`` with this access, at ``tier``; a catalogue entry names no viewer (KLAERUNGEN B11)."""
    access = AccessInfo(
        token_free_checked_at=checked,
        method="anonymous HTTPS",
        cors=None,
        account=account,
        account_provider=provider,
        account_paths=paths,
    )
    viewer = None if tier is LicenseTier.CATALOG else entry.viewer
    return replace(entry, access=access, license=replace(entry.license, tier=tier), viewer=viewer)


@pytest.mark.parametrize("entry", list(REGISTRY), ids=lambda entry: entry.dataset_id)
def test_every_entry_reads_without_an_account(entry: DatasetConfig) -> None:
    assert entry.access.account is AccountKind.NONE
    assert entry.access.account_provider is None
    assert entry.access.account_paths == ()
    assert entry.access.token_free_checked_at is not None


class TestWhatIsAllowed:
    def test_none_at_any_tier(self, valid_config: DatasetConfig) -> None:
        for tier in LicenseTier:
            _with(valid_config, AccountKind.NONE, tier=tier, checked=CHECKED)

    def test_anonymous_token_as_a_catalogue_entry_with_its_check(self, valid_config: DatasetConfig) -> None:
        _with(valid_config, AccountKind.ANONYMOUS_TOKEN, checked=CHECKED)

    def test_free_account_as_a_catalogue_entry_with_a_provider(self, valid_config: DatasetConfig) -> None:
        _with(valid_config, AccountKind.FREE_ACCOUNT, provider="cdse")

    @pytest.mark.parametrize("provider", [None, "aws"])
    def test_requester_pays_as_a_catalogue_entry(self, valid_config: DatasetConfig, provider: str | None) -> None:
        _with(valid_config, AccountKind.REQUESTER_PAYS, provider=provider)


class TestWhatIsRefused:
    @pytest.mark.parametrize("account", [AccountKind.FREE_ACCOUNT, AccountKind.REQUESTER_PAYS])
    @pytest.mark.parametrize("tier", [LicenseTier.DISPLAY, LicenseTier.PROCESSING])
    def test_an_account_source_above_the_catalogue(
        self, valid_config: DatasetConfig, account: AccountKind, tier: LicenseTier
    ) -> None:
        with pytest.raises(ConfigError, match="allows licence tier catalog only"):
            _with(valid_config, account, tier=tier, provider="cdse")

    @pytest.mark.parametrize("tier", [LicenseTier.DISPLAY, LicenseTier.PROCESSING])
    def test_an_anonymous_token_above_the_catalogue(self, valid_config: DatasetConfig, tier: LicenseTier) -> None:
        # Until the sentence of adr/0018 §12 stands in ENTSCHEIDUNGEN (M5-13 plan §8a).
        with pytest.raises(ConfigError, match="allows licence tier catalog only"):
            _with(valid_config, AccountKind.ANONYMOUS_TOKEN, tier=tier, checked=CHECKED)

    @pytest.mark.parametrize("account", list(AccountKind))
    @pytest.mark.parametrize("path", list(AccountPath))
    def test_any_account_path(self, valid_config: DatasetConfig, account: AccountKind, path: AccountPath) -> None:
        anonymous = account in (AccountKind.NONE, AccountKind.ANONYMOUS_TOKEN)
        with pytest.raises(ConfigError, match="account_paths stays empty"):
            _with(
                valid_config,
                account,
                provider=None if anonymous else "cdse",
                checked=CHECKED if anonymous else None,
                paths=(path,),
            )

    @pytest.mark.parametrize("account", [AccountKind.NONE, AccountKind.ANONYMOUS_TOKEN])
    def test_a_provider_on_an_anonymous_source(self, valid_config: DatasetConfig, account: AccountKind) -> None:
        with pytest.raises(ConfigError, match="names no account_provider"):
            _with(valid_config, account, provider="cdse", checked=CHECKED)

    def test_free_account_without_a_provider(self, valid_config: DatasetConfig) -> None:
        with pytest.raises(ConfigError, match="names its account_provider"):
            _with(valid_config, AccountKind.FREE_ACCOUNT)

    @pytest.mark.parametrize("provider", ["", "  "])
    def test_a_blank_provider(self, valid_config: DatasetConfig, provider: str) -> None:
        with pytest.raises(ConfigError, match="a name or null"):
            _with(valid_config, AccountKind.FREE_ACCOUNT, provider=provider)

    @pytest.mark.parametrize("account", [AccountKind.FREE_ACCOUNT, AccountKind.REQUESTER_PAYS])
    def test_a_check_date_on_an_account_source(self, valid_config: DatasetConfig, account: AccountKind) -> None:
        with pytest.raises(ConfigError, match="token_free_checked_at is set exactly"):
            _with(valid_config, account, provider="cdse", checked=CHECKED)

    @pytest.mark.parametrize("account", [AccountKind.NONE, AccountKind.ANONYMOUS_TOKEN])
    def test_no_check_date_on_an_anonymous_source(self, valid_config: DatasetConfig, account: AccountKind) -> None:
        with pytest.raises(ConfigError, match="token_free_checked_at is set exactly"):
            _with(valid_config, account)

    def test_an_account_that_is_no_account_kind(self, valid_config: DatasetConfig) -> None:
        with pytest.raises(ConfigError, match="access.account must be one of"):
            replace(valid_config, access=replace(valid_config.access, account="none"))

    def test_paths_that_are_no_tuple_of_paths(self, valid_config: DatasetConfig) -> None:
        with pytest.raises(ConfigError, match="tuple of AccountPath"):
            replace(valid_config, access=replace(valid_config.access, account_paths=("W2a",)))


def test_the_collection_carries_the_account(valid_config: DatasetConfig) -> None:
    access = to_stac_collection(valid_config)["earthx:access"]
    assert (access["account"], access["account_provider"], access["account_paths"]) == ("none", None, [])
    listed = to_stac_collection(_with(valid_config, AccountKind.FREE_ACCOUNT, provider="cdse"))["earthx:access"]
    assert (listed["account"], listed["account_provider"], listed["token_free_checked_at"]) == (
        "free_account",
        "cdse",
        None,
    )
