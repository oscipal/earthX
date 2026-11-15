"""Listed entries, the blocklist and the region outlines, read from files (M5-40 plan §5.2, §5.4, §5.5, §5.8; adr/0033).

Every case writes into ``tmp_path`` or builds a ``ListedEntry`` through its dataclass, so the checks of
``__post_init__`` are the ones under test. The files are strict like the registry's (``catalog.entry_files``): an
unknown field, a missing one and a YAML 1.1 boolean word are errors, and an error names the field, never its value.
The query side (``read_query`` and its token) lives here too: it is pure and decides what a request may ask.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from fastapi import HTTPException

from earthx.api.collection_search import (
    DEFAULT_PAGE,
    MAX_LISTING_PAGE,
    MAX_TEXT_PAGE,
    encode_token,
    read_query,
)
from earthx.catalog.entry_files import EntryFileError, load_entry, to_plain
from earthx.catalog.listed import (
    REGIONS_FILE,
    BlockReason,
    BlockScope,
    DeliveryKind,
    ListedAccess,
    content_sha256,
    link_host,
    load_blocked,
    load_listed,
    load_regions,
    sort_title,
    to_listed_collection,
)
from earthx.catalog.registry import (
    AccessInfo,
    AccountKind,
    ConfigError,
    DatasetConfig,
    LegalStatus,
    LicenseTier,
)
from tests.catalog.entries import COP_DEM_GLO_30
from tests.catalog.listed_entries import listed_entry, plain_entry, write_entry, write_plain

SECRET = "Jane-Doe-asked-by-mail"


def _write_text(directory: Path, text: str, name: str) -> Path:
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


# --- load_listed: the normal case ------------------------------------------------------------------------------------


def test_hand_entries_come_back_equal_through_their_files_with_the_hash_of_each(tmp_path: Path) -> None:
    first, second = listed_entry("example-atlas"), listed_entry("example-bathymetry", title="Example bathymetry")
    write_entry(tmp_path, second)
    write_entry(tmp_path, first)
    found = load_listed(tmp_path)
    assert [entry for entry, _ in found] == [first, second]  # in the order of the file names
    for entry, file_hash in found:
        assert file_hash == hashlib.sha256((tmp_path / f"{entry.dataset_id}.yaml").read_bytes()).hexdigest()


def test_the_hash_changes_with_a_byte_of_the_file(tmp_path: Path) -> None:
    path = write_entry(tmp_path)
    before = load_listed(tmp_path)[0][1]
    path.write_text(path.read_text(encoding="utf-8") + "\n# a comment\n", encoding="utf-8")
    after = load_listed(tmp_path)[0]
    assert after[1] != before and after[0] == listed_entry()


def test_an_absent_directory_holds_no_entry(tmp_path: Path) -> None:
    assert load_listed(tmp_path / "nowhere") == ()


def test_a_directory_with_a_readme_only_holds_no_entry(tmp_path: Path) -> None:
    _write_text(tmp_path, "# Hand entries\n", "README.md")
    assert load_listed(tmp_path) == ()


def test_a_readme_next_to_entries_is_not_read_as_one(tmp_path: Path) -> None:
    _write_text(tmp_path, "not: an entry\n", "README.md")
    write_entry(tmp_path)
    assert [entry.dataset_id for entry, _ in load_listed(tmp_path)] == ["example-atlas"]


def test_a_paid_listed_entry_reads(tmp_path: Path) -> None:
    access = ListedAccess(AccountKind.PAID, None, DeliveryKind.ORDER)
    entry = listed_entry("example-paid", access=access)
    write_entry(tmp_path, entry)
    assert load_listed(tmp_path)[0][0].access.account is AccountKind.PAID


def test_open_ends_of_the_period_read(tmp_path: Path) -> None:
    data = plain_entry()
    data["temporal_extent"] = {"start": None, "end": None}
    write_plain(tmp_path, data, "example-atlas.yaml")
    entry = load_listed(tmp_path)[0][0]
    assert (entry.temporal_extent.start, entry.temporal_extent.end) == (None, None)


# --- load_listed: what a file may not be ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "where"),
    [
        (lambda d: d.update(colour="red"), "colour"),
        (lambda d: d["license"].update(colour="red"), "license.colour"),
        (lambda d: d["access"].update(colour="red"), "access.colour"),
        (lambda d: d["providers"][0].update(colour="red"), "providers.0.colour"),
        (lambda d: d.update(regions=["DE"]), "regions"),  # the regions are derived, never read from a file
    ],
    ids=["top", "licence", "access", "in-a-list", "regions"],
)
def test_an_unknown_field_is_an_error_with_its_path(tmp_path: Path, change, where: str) -> None:
    data = plain_entry()
    change(data)
    write_plain(tmp_path, data, "example-atlas.yaml")
    with pytest.raises(EntryFileError, match=rf"example-atlas\.yaml: .*{where}"):
        load_listed(tmp_path)


@pytest.mark.parametrize("field", list(plain_entry()), ids=str)
def test_every_field_of_an_entry_is_required(tmp_path: Path, field: str) -> None:
    data = plain_entry()
    del data[field]
    write_plain(tmp_path, data, "example-atlas.yaml")
    with pytest.raises(EntryFileError, match=rf"\b{field}\b"):
        load_listed(tmp_path)


@pytest.mark.parametrize(("parent", "field"), [("license", "tier"), ("access", "delivery"), ("access", "account")])
def test_every_field_of_a_part_is_required(tmp_path: Path, parent: str, field: str) -> None:
    data = plain_entry()
    del data[parent][field]
    write_plain(tmp_path, data, "example-atlas.yaml")
    with pytest.raises(EntryFileError, match=f"{parent}.{field}"):
        load_listed(tmp_path)


@pytest.mark.parametrize("word", ["yes", "no", "on", "off", "y", "n"])
def test_a_yaml_1_1_boolean_word_is_no_boolean(tmp_path: Path, word: str) -> None:
    text = yaml.safe_dump(plain_entry(), sort_keys=False).replace("commercial_use: true", f"commercial_use: {word}")
    assert word in text
    _write_text(tmp_path, text, "example-atlas.yaml")
    with pytest.raises(EntryFileError, match="license.commercial_use"):
        load_listed(tmp_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [("title", 123), ("keywords", "atlas"), ("data_kind", "everything"), ("approved_on", "10.11.2026"), ("doi", 5)],
)
def test_a_value_of_the_wrong_type_or_kind_is_an_error(tmp_path: Path, field: str, value: object) -> None:
    data = plain_entry()
    data[field] = value
    write_plain(tmp_path, data, "example-atlas.yaml")
    with pytest.raises(EntryFileError, match=rf"\b{field}\b"):
        load_listed(tmp_path)


def test_an_error_names_the_field_and_not_its_value(tmp_path: Path) -> None:
    data = plain_entry()
    data["data_kind"] = SECRET
    write_plain(tmp_path, data, "example-atlas.yaml")
    with pytest.raises(EntryFileError) as error:
        load_listed(tmp_path)
    assert "data_kind" in str(error.value) and SECRET not in str(error.value)


def test_a_file_named_after_another_id_is_an_error(tmp_path: Path) -> None:
    write_entry(tmp_path, listed_entry("example-atlas"), name="example-other.yaml")
    with pytest.raises(EntryFileError, match="named <dataset_id>.yaml"):
        load_listed(tmp_path)


@pytest.mark.parametrize("name", ["example-atlas.yml", "example-atlas.yaml.bak", "notes.txt", "readme.md", "README"])
def test_a_stray_file_is_an_error(tmp_path: Path, name: str) -> None:
    _write_text(tmp_path, "x", name)
    with pytest.raises(EntryFileError, match="only <dataset_id>.yaml files and a README"):
        load_listed(tmp_path)


def test_a_stray_directory_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "nested.yaml").mkdir()
    with pytest.raises(EntryFileError, match="only <dataset_id>.yaml files and a README"):
        load_listed(tmp_path)


@pytest.mark.parametrize("text", ["", "- a\n- b\n", "just text\n", "42\n"], ids=["empty", "list", "text", "number"])
def test_a_file_that_is_no_mapping_is_an_error(tmp_path: Path, text: str) -> None:
    _write_text(tmp_path, text, "example-atlas.yaml")
    with pytest.raises(EntryFileError, match="mapping of its fields"):
        load_listed(tmp_path)


@pytest.mark.parametrize(
    "text",
    ["title: [unclosed\n", "title: a\ntitle: b\n", "a: &x 1\nb: *x\n", "1: one\n"],
    ids=["syntax", "duplicate-key", "alias", "key-not-text"],
)
def test_a_file_that_is_not_strict_yaml_is_an_error(tmp_path: Path, text: str) -> None:
    _write_text(tmp_path, text, "example-atlas.yaml")
    with pytest.raises(EntryFileError, match="example-atlas.yaml"):
        load_listed(tmp_path)


def test_a_file_that_is_no_utf8_text_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "example-atlas.yaml").write_bytes(b"title: \xff\xfe\n")
    with pytest.raises(EntryFileError, match="UTF-8"):
        load_listed(tmp_path)


def test_one_bad_file_stops_the_whole_read(tmp_path: Path) -> None:
    write_entry(tmp_path, listed_entry("example-atlas"))
    data = plain_entry(listed_entry("example-bad"))
    data["source_url"] = "http://data.example.org/bad"
    write_plain(tmp_path, data, "example-bad.yaml")
    with pytest.raises(EntryFileError, match="example-bad.yaml"):
        load_listed(tmp_path)


# --- ListedEntry: the checks of the head -----------------------------------------------------------------------------


@pytest.mark.parametrize("dataset_id", ["proto-atlas", "proto-"])
def test_a_prototype_id_is_refused(dataset_id: str) -> None:
    with pytest.raises(ConfigError, match="never a prototype"):
        listed_entry(dataset_id)


@pytest.mark.parametrize(
    "dataset_id",
    ["", "Example", "-example", ".example", "example atlas", "example/atlas", "exämple", "e" * 129, "example\n"],
    ids=["empty", "upper", "dash", "dot", "space", "slash", "umlaut", "long", "newline"],
)
def test_a_bad_id_is_refused(dataset_id: str) -> None:
    with pytest.raises(ConfigError, match="a listed entry's id is"):
        listed_entry(dataset_id)


def test_an_id_of_128_characters_is_fine() -> None:
    assert listed_entry("a" * 128).dataset_id == "a" * 128


@pytest.mark.parametrize("tier", [LicenseTier.DISPLAY, LicenseTier.PROCESSING])
def test_a_tier_above_the_catalogue_is_refused(tier: LicenseTier) -> None:
    base = listed_entry()
    with pytest.raises(ConfigError, match="licence tier catalog"):
        replace(base, license=replace(base.license, tier=tier))


def test_a_licence_without_spdx_needs_name_and_url() -> None:
    base = listed_entry()
    assert replace(base, license=replace(base.license, spdx_id=None)).license.spdx_id is None
    with pytest.raises(ConfigError, match="SPDX identifier or a name and a URL"):
        replace(base, license=replace(base.license, spdx_id=None, url=""))


def test_an_unclear_legal_status_is_refused() -> None:
    with pytest.raises(ConfigError, match="legal_status cleared"):
        listed_entry(legal_status=LegalStatus.UNCLEAR)


@pytest.mark.parametrize(
    "url",
    [
        "http://data.example.org/atlas",
        "ftp://data.example.org/atlas",
        "data.example.org/atlas",
        "https://",
        "https:///atlas",
        "https://data.example.org/a b",
        "",
        " https://data.example.org/atlas",
    ],
)
def test_a_link_that_is_no_https_address_is_refused(url: str) -> None:
    with pytest.raises(ConfigError, match="source_url is an https address"):
        listed_entry(source_url=url)


@pytest.mark.parametrize("field", ["publisher", "title", "description"])
@pytest.mark.parametrize("text", ["", "   ", "\n"])
def test_a_blank_text_is_refused(field: str, text: str) -> None:
    with pytest.raises(ConfigError, match=f"{field} is a non-blank text"):
        listed_entry(**{field: text})


@pytest.mark.parametrize("keywords", [(), ("",), ("atlas", "  ")], ids=["none", "blank", "one-blank"])
def test_keywords_name_at_least_one_nonblank_keyword(keywords: tuple[str, ...]) -> None:
    with pytest.raises(ConfigError, match="keywords names at least one keyword"):
        listed_entry(keywords=keywords)


def test_no_provider_is_refused() -> None:
    with pytest.raises(ConfigError, match="names no provider"):
        listed_entry(providers=())


@pytest.mark.parametrize("doi", ["not a doi", "10.", "10.5555", "https://example.org/10.5555/x"])
def test_a_bad_doi_is_refused(doi: str) -> None:
    with pytest.raises(ConfigError, match="is no DOI name"):
        listed_entry(doi=doi)


@pytest.mark.parametrize("doi", [None, "", "10.5555/example", "doi:10.5555/example", "https://doi.org/10.5555/example"])
def test_a_doi_name_or_resolver_url_is_fine(doi: str | None) -> None:
    assert listed_entry(doi=doi).doi == doi


# --- ListedEntry: the account ----------------------------------------------------------------------------------------


def test_free_account_without_a_provider_is_refused() -> None:
    with pytest.raises(ConfigError, match="names its account_provider"):
        listed_entry(access=ListedAccess(AccountKind.FREE_ACCOUNT, None, DeliveryKind.DOWNLOAD))


@pytest.mark.parametrize("account", [AccountKind.NONE, AccountKind.ANONYMOUS_TOKEN])
def test_an_anonymous_source_with_a_provider_is_refused(account: AccountKind) -> None:
    with pytest.raises(ConfigError, match="names no account_provider"):
        listed_entry(access=ListedAccess(account, "example-idp", DeliveryKind.DOWNLOAD))


@pytest.mark.parametrize("provider", ["", "  "])
def test_a_blank_account_provider_is_refused(provider: str) -> None:
    with pytest.raises(ConfigError, match="a name or null"):
        listed_entry(access=ListedAccess(AccountKind.FREE_ACCOUNT, provider, DeliveryKind.DOWNLOAD))


@pytest.mark.parametrize(
    ("account", "provider"),
    [
        (AccountKind.NONE, None),
        (AccountKind.ANONYMOUS_TOKEN, None),
        (AccountKind.FREE_ACCOUNT, "example-idp"),
        (AccountKind.REQUESTER_PAYS, None),
        (AccountKind.REQUESTER_PAYS, "example-cloud"),
        (AccountKind.PAID, None),
        (AccountKind.PAID, "example-shop"),
    ],
)
@pytest.mark.parametrize("delivery", list(DeliveryKind))
def test_every_allowed_account_and_delivery_is_fine_for_a_listed_entry(
    account: AccountKind, provider: str | None, delivery: DeliveryKind
) -> None:
    assert listed_entry(access=ListedAccess(account, provider, delivery)).access.account is account


def test_an_account_that_is_no_account_kind_does_not_read_from_a_file(tmp_path: Path) -> None:
    data = plain_entry()
    data["access"]["account"] = "gratis"
    write_plain(tmp_path, data, "example-atlas.yaml")
    with pytest.raises(EntryFileError, match="access.account"):
        load_listed(tmp_path)


def test_paid_in_a_full_entry_is_a_config_error(valid_config: DatasetConfig) -> None:
    # Misuse: `paid` is for listed entries only (adr/0033 §5); a full entry under datasets/ must not carry it.
    access = AccessInfo(
        token_free_checked_at=None,
        method="anonymous HTTPS",
        cors=None,
        account=AccountKind.PAID,
        account_provider=None,
        account_paths=(),
    )
    with pytest.raises(ConfigError, match="paid is for listed entries only"):
        replace(
            valid_config,
            access=access,
            license=replace(valid_config.license, tier=LicenseTier.CATALOG),
            viewer=None,
        )


def test_paid_in_the_file_of_a_full_entry_is_a_load_error(tmp_path: Path) -> None:
    data = copy.deepcopy(to_plain(COP_DEM_GLO_30))
    data["access"]["account"] = "paid"
    data["access"]["token_free_checked_at"] = None
    path = write_plain(tmp_path, data, f"{COP_DEM_GLO_30.dataset_id}.yaml")
    with pytest.raises(EntryFileError, match="paid is for listed entries only"):
        load_entry(path)


# --- the collection of a listed entry --------------------------------------------------------------------------------


def test_the_collection_of_a_listed_entry_has_no_viewer_no_capabilities_and_no_source() -> None:
    collection = to_listed_collection(listed_entry())
    assert collection["earthx:entry"] == "listed" and collection["id"] == "example-atlas"
    assert not {"earthx:viewer", "earthx:capabilities", "earthx:source", "earthx:regions"} & set(collection)
    assert collection["earthx:access"] == {"account": "none", "account_provider": None, "delivery": "download"}
    assert {"rel": "via", "href": "https://data.example.org/example-atlas", "title": "Source"} in collection["links"]


def test_the_hash_of_the_collection_does_not_depend_on_the_order_of_its_keys() -> None:
    collection = to_listed_collection(listed_entry())
    assert content_sha256(collection) == content_sha256(dict(reversed(list(collection.items()))))
    assert content_sha256(collection) != content_sha256(to_listed_collection(listed_entry(title="Other")))


# --- load_blocked ----------------------------------------------------------------------------------------------------

_DAY = "2026-11-01"
_HASH = "ab" * 32


def _blocked(tmp_path: Path, text: str) -> Path:
    return _write_text(tmp_path, text, "blocked.yaml")


@pytest.mark.parametrize("text", [None, "", "[]\n", "# only comments\n"], ids=["absent", "empty", "list", "comments"])
def test_no_line_blocks_nothing(tmp_path: Path, text: str | None) -> None:
    path = tmp_path / "blocked.yaml" if text is None else _blocked(tmp_path, text)
    assert load_blocked(path) == ()


@pytest.mark.parametrize(
    ("lines", "scope"),
    [
        ("source_id: src-1\n  source_key: key-1", BlockScope.ENTRY),
        ("source_id: src-1\n  publisher: Example Geodata Office", BlockScope.PUBLISHER),
        ("host: data.example.org", BlockScope.HOST),
        ("source_id: src-1", BlockScope.SOURCE),
    ],
    ids=lambda value: value.value if isinstance(value, BlockScope) else None,
)
def test_each_scope_reads(tmp_path: Path, lines: str, scope: BlockScope) -> None:
    (rule,) = load_blocked(
        _blocked(tmp_path, f"- scope: {scope.value}\n  {lines}\n  reason: quality\n  blocked_on: {_DAY}\n")
    )
    assert (rule.scope, rule.reason, rule.blocked_on) == (scope, BlockReason.QUALITY, date(2026, 11, 1))


@pytest.mark.parametrize("reason", [reason.value for reason in BlockReason])
def test_each_reason_reads(tmp_path: Path, reason: str) -> None:
    text = f"- scope: source\n  source_id: src-1\n  reason: {reason}\n  blocked_on: {_DAY}\n"
    assert load_blocked(_blocked(tmp_path, text))[0].reason is BlockReason(reason)


def test_a_licence_hash_is_optional_and_reads(tmp_path: Path) -> None:
    text = f"- scope: host\n  host: data.example.org\n  reason: legal\n  blocked_on: {_DAY}\n  license_hash: {_HASH}\n"
    assert load_blocked(_blocked(tmp_path, text))[0].license_hash == _HASH


def test_several_lines_read_in_order(tmp_path: Path) -> None:
    text = (
        f"- {{scope: source, source_id: src-1, reason: other, blocked_on: {_DAY}}}\n"
        f"- {{scope: host, host: data.example.org, reason: legal, blocked_on: {_DAY}}}\n"
    )
    assert [rule.scope for rule in load_blocked(_blocked(tmp_path, text))] == [BlockScope.SOURCE, BlockScope.HOST]


def _line(scope: str, **fields: str) -> str:
    body = {"scope": scope, **fields, "reason": "quality", "blocked_on": _DAY}
    return yaml.safe_dump([body], sort_keys=False)


@pytest.mark.parametrize(
    ("scope", "fields"),
    [
        ("entry", {"source_id": "src-1"}),  # the key is missing
        ("entry", {"source_key": "key-1"}),  # the source is missing
        ("entry", {"source_id": "src-1", "source_key": "key-1", "publisher": "P"}),
        ("entry", {"source_id": "src-1", "source_key": "key-1", "host": "data.example.org"}),
        ("publisher", {"publisher": "P"}),  # the source is missing
        ("publisher", {"source_id": "src-1"}),  # the publisher is missing
        ("publisher", {"source_id": "src-1", "publisher": "P", "source_key": "key-1"}),
        ("host", {}),
        ("host", {"host": "data.example.org", "source_id": "src-1"}),
        ("source", {}),
        ("source", {"source_id": "src-1", "host": "data.example.org"}),
        ("source", {"source_id": "src-1", "source_key": "key-1"}),
    ],
)
def test_a_scoped_field_that_is_missing_or_does_not_belong_is_an_error(
    tmp_path: Path, scope: str, fields: dict[str, str]
) -> None:
    with pytest.raises(EntryFileError, match="a line of scope"):
        load_blocked(_blocked(tmp_path, _line(scope, **fields)))


@pytest.mark.parametrize("field", ["scope", "reason", "blocked_on"])
def test_a_line_without_its_fixed_field_is_an_error(tmp_path: Path, field: str) -> None:
    body = {"scope": "source", "source_id": "src-1", "reason": "quality", "blocked_on": _DAY}
    del body[field]
    with pytest.raises(EntryFileError, match=rf"blocked.yaml\[0\].*{field}"):
        load_blocked(_blocked(tmp_path, yaml.safe_dump([body])))


@pytest.mark.parametrize("scope", ["everything", "Entry", "", "dataset"])
def test_an_unknown_scope_is_an_error(tmp_path: Path, scope: str) -> None:
    with pytest.raises(EntryFileError, match="scope"):
        load_blocked(_blocked(tmp_path, _line(scope, source_id="src-1")))


@pytest.mark.parametrize("reason", ["spam", "Legal", "", "source_removed"])
def test_an_unknown_reason_is_an_error_and_source_removed_is_not_one_to_give(tmp_path: Path, reason: str) -> None:
    # `source_removed` is the reason the loader gives a vanished hand entry; no line of the blocklist may claim it.
    text = f"- scope: source\n  source_id: src-1\n  reason: '{reason}'\n  blocked_on: {_DAY}\n"
    with pytest.raises(EntryFileError, match="reason"):
        load_blocked(_blocked(tmp_path, text))


@pytest.mark.parametrize("field", ["note", "comment", "name", "email", "requested_by", "text", "reason_text"])
def test_a_free_text_field_is_refused_and_its_text_is_not_repeated(tmp_path: Path, field: str) -> None:
    text = f"- scope: source\n  source_id: src-1\n  reason: legal\n  blocked_on: {_DAY}\n  {field}: {SECRET}\n"
    with pytest.raises(EntryFileError) as error:
        load_blocked(_blocked(tmp_path, text))
    assert field in str(error.value) and SECRET not in str(error.value)


@pytest.mark.parametrize("days", [1, 2, 400])
def test_a_day_in_the_future_is_an_error(tmp_path: Path, days: int) -> None:
    text = (
        f"- scope: source\n  source_id: src-1\n  reason: legal\n  blocked_on: {date.today() + timedelta(days=days)}\n"
    )
    with pytest.raises(EntryFileError, match=r"blocked.yaml\[0\]: blocked_on lies in the future"):
        load_blocked(_blocked(tmp_path, text))


@pytest.mark.parametrize("days", [0, -1])
def test_today_and_the_days_before_are_fine(tmp_path: Path, days: int) -> None:
    day = date.today() + timedelta(days=days)
    text = f"- scope: source\n  source_id: src-1\n  reason: legal\n  blocked_on: {day}\n"
    assert load_blocked(_blocked(tmp_path, text))[0].blocked_on == day


@pytest.mark.parametrize("day", ["01.11.2026", "2026-13-45", "yesterday", "'2026-11-01T10:00:00Z'", "20261101"])
def test_a_day_that_is_no_iso_date_is_an_error(tmp_path: Path, day: str) -> None:
    text = f"- scope: source\n  source_id: src-1\n  reason: legal\n  blocked_on: {day}\n"
    with pytest.raises(EntryFileError, match="blocked_on"):
        load_blocked(_blocked(tmp_path, text))


def test_the_same_line_twice_is_an_error(tmp_path: Path) -> None:
    line = "- scope: entry\n  source_id: src-1\n  source_key: key-1\n  reason: legal\n  blocked_on: 2026-11-01\n"
    with pytest.raises(EntryFileError, match=r"blocked.yaml\[1\]: the same line stands twice"):
        load_blocked(_blocked(tmp_path, line + line))


def test_the_same_target_with_another_reason_or_day_stands_twice_as_well(tmp_path: Path) -> None:
    text = (
        "- {scope: host, host: data.example.org, reason: legal, blocked_on: 2026-11-01}\n"
        "- {scope: host, host: data.example.org, reason: quality, blocked_on: 2026-11-02}\n"
    )
    with pytest.raises(EntryFileError, match="the same line stands twice"):
        load_blocked(_blocked(tmp_path, text))


def test_the_same_values_under_two_scopes_are_two_lines(tmp_path: Path) -> None:
    text = (
        "- {scope: source, source_id: src-1, reason: legal, blocked_on: 2026-11-01}\n"
        "- {scope: publisher, source_id: src-1, publisher: P, reason: legal, blocked_on: 2026-11-01}\n"
    )
    assert len(load_blocked(_blocked(tmp_path, text))) == 2


@pytest.mark.parametrize(
    "host",
    [
        "https://data.example.org",
        "data.example.org/path",
        "data.example.org:8443",
        "Data.Example.org",
        "DATA.EXAMPLE.ORG",
        "localhost",
        "-data.example.org",
        "data..example.org",
        "data.example.org.",
        "data example.org",
        "user@data.example.org",
        "exämple.org",
        "'  '",
        "''",
        "a." + "b" * 64 + ".org",
    ],
)
def test_a_host_that_is_not_a_plain_lower_case_name_is_an_error(tmp_path: Path, host: str) -> None:
    quoted = host if host.startswith("'") else f"'{host}'"
    text = f"- scope: host\n  host: {quoted}\n  reason: legal\n  blocked_on: {_DAY}\n"
    with pytest.raises(EntryFileError, match="host"):
        load_blocked(_blocked(tmp_path, text))


@pytest.mark.parametrize(
    "host", ["data.example.org", "xn--bcher-kva.example", "a-b.example.org", "a.b.c.d.example.org"]
)
def test_a_plain_host_name_reads(tmp_path: Path, host: str) -> None:
    text = f"- scope: host\n  host: {host}\n  reason: legal\n  blocked_on: {_DAY}\n"
    assert load_blocked(_blocked(tmp_path, text))[0].host == host


@pytest.mark.parametrize("license_hash", ["AB" * 32, "ab" * 31, "ab" * 33, "xy" * 32, "", "sha256:" + "ab" * 32])
def test_a_licence_hash_that_is_no_lower_case_sha256_is_an_error(tmp_path: Path, license_hash: str) -> None:
    text = f"- scope: source\n  source_id: src-1\n  reason: legal\n  blocked_on: {_DAY}\n  license_hash: '{license_hash}'\n"
    with pytest.raises(EntryFileError, match="license_hash"):
        load_blocked(_blocked(tmp_path, text))


@pytest.mark.parametrize("field", ["source_id", "source_key", "publisher"])
def test_a_blank_scoped_text_is_an_error(tmp_path: Path, field: str) -> None:
    fields = {"source_id": "src-1", "source_key": "key-1", "publisher": "P"}
    fields[field] = "  "
    scope = "publisher" if field == "publisher" else "entry"
    if scope == "publisher":
        fields.pop("source_key")
    else:
        fields.pop("publisher")
    with pytest.raises(EntryFileError, match=f"{field} is a non-blank text"):
        load_blocked(_blocked(tmp_path, _line(scope, **fields)))


@pytest.mark.parametrize("text", ["scope: source\n", "just text\n", "42\n"], ids=["mapping", "text", "number"])
def test_a_blocklist_that_is_no_list_is_an_error(tmp_path: Path, text: str) -> None:
    with pytest.raises(EntryFileError, match="the blocklist is a list"):
        load_blocked(_blocked(tmp_path, text))


@pytest.mark.parametrize("text", ["- just text\n", "- 42\n", "- [a, b]\n", "- null\n"])
def test_a_line_that_is_no_mapping_is_an_error(tmp_path: Path, text: str) -> None:
    with pytest.raises(EntryFileError, match=r"blocked.yaml\[0\]"):
        load_blocked(_blocked(tmp_path, text))


def test_a_blocklist_with_a_yaml_error_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(EntryFileError, match="not valid YAML"):
        load_blocked(_blocked(tmp_path, "- scope: [unclosed\n"))


# --- load_regions ----------------------------------------------------------------------------------------------------


def test_the_shipped_outlines_are_299_regions_of_which_237_are_states() -> None:
    regions = load_regions(REGIONS_FILE)
    assert len(regions) == 299
    assert sum(region.level == "state" for region in regions) == 237
    assert sum(region.level == "subdivision" for region in regions) == 62
    assert len({region.code for region in regions}) == len(regions)
    assert {"DE", "DE-BY", "AT", "CH", "LI"} <= {region.code for region in regions}
    assert all(region.outline["type"] in ("Polygon", "MultiPolygon") for region in regions)


def test_the_shipped_subdivisions_are_those_of_de_at_ch_and_li() -> None:
    countries = {region.code.split("-")[0] for region in load_regions(REGIONS_FILE) if region.level == "subdivision"}
    assert countries == {"DE", "AT", "CH", "LI"}


def _square(west: float = 0.0) -> dict:
    ring = [[west, 0.0], [west + 1.0, 0.0], [west + 1.0, 1.0], [west, 1.0], [west, 0.0]]
    return {"type": "Polygon", "coordinates": [ring]}


def _regions_file() -> dict:
    return {
        "source": "Synthetic outlines for the tests",
        "release": "0",
        "files": {},
        "script": "none",
        "tolerance_deg": {"state": 0.0, "subdivision": 0.0},
        "regions": [
            {"code": "XA", "name": "Land A", "level": "state", "outline": _square(0.0)},
            {"code": "XA-B", "name": "Part B", "level": "subdivision", "outline": _square(5.0)},
        ],
    }


def _write_regions(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "regions.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_a_valid_small_file_reads(tmp_path: Path) -> None:
    regions = load_regions(_write_regions(tmp_path, _regions_file()))
    assert [(region.code, region.level, region.name) for region in regions] == [
        ("XA", "state", "Land A"),
        ("XA-B", "subdivision", "Part B"),
    ]


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.pop("tolerance_deg"),
        lambda d: d.update(colour="red"),
        lambda d: d.update(regions={"XA": 1}),
        lambda d: d["regions"][0].pop("name"),
        lambda d: d["regions"][0].update(colour="red"),
        lambda d: d["regions"][0].pop("outline"),
        lambda d: d["regions"].__setitem__(0, "XA"),
    ],
    ids=["missing-key", "extra-key", "regions-no-list", "region-missing-key", "region-extra-key", "no-outline", "text"],
)
def test_a_file_with_the_wrong_keys_is_an_error(tmp_path: Path, change) -> None:
    data = _regions_file()
    change(data)
    with pytest.raises(EntryFileError, match="regions.json: .*holds exactly"):
        load_regions(_write_regions(tmp_path, data))


@pytest.mark.parametrize("code", ["xa", "XAA", "X", "XA-", "XA-ABCD", "XA-b", "XA_B", " XA", "", "XA\n"])
def test_a_code_that_is_no_iso_3166_code_is_an_error(tmp_path: Path, code: str) -> None:
    data = _regions_file()
    data["regions"][0]["code"] = code
    with pytest.raises(EntryFileError, match=r"regions\[0\]\.code is no ISO 3166 code"):
        load_regions(_write_regions(tmp_path, data))


@pytest.mark.parametrize("code", [5, None, ["XA"]])
def test_a_code_that_is_no_text_is_an_error(tmp_path: Path, code: object) -> None:
    data = _regions_file()
    data["regions"][0]["code"] = code
    with pytest.raises(EntryFileError, match=r"regions\[0\]\.code"):
        load_regions(_write_regions(tmp_path, data))


@pytest.mark.parametrize(("index", "level"), [(0, "subdivision"), (1, "state"), (0, "province"), (0, None)])
def test_a_level_that_does_not_match_its_code_is_an_error(tmp_path: Path, index: int, level: object) -> None:
    data = _regions_file()
    data["regions"][index]["level"] = level
    with pytest.raises(EntryFileError, match=rf"regions\[{index}\]\.level does not match its code"):
        load_regions(_write_regions(tmp_path, data))


def test_a_code_twice_is_an_error(tmp_path: Path) -> None:
    data = _regions_file()
    data["regions"].append(copy.deepcopy(data["regions"][0]))
    with pytest.raises(EntryFileError, match="a region code stands twice"):
        load_regions(_write_regions(tmp_path, data))


@pytest.mark.parametrize(
    "outline",
    [
        {"type": "Point", "coordinates": [0, 0]},
        {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
        {"type": "GeometryCollection", "geometries": []},
        {"coordinates": []},
        {},
        "POLYGON((0 0, 1 0, 1 1, 0 0))",
        None,
        [],
    ],
    ids=["point", "line", "collection", "no-type", "empty", "wkt", "null", "list"],
)
def test_an_outline_that_is_no_polygon_is_an_error(tmp_path: Path, outline: object) -> None:
    data = _regions_file()
    data["regions"][1]["outline"] = outline
    with pytest.raises(EntryFileError, match=r"regions\[1\]\.outline is a Polygon or MultiPolygon"):
        load_regions(_write_regions(tmp_path, data))


@pytest.mark.parametrize("text", ["", "not json", "[1, 2]", '"text"', "null", "{"])
def test_a_file_that_is_no_json_object_is_an_error(tmp_path: Path, text: str) -> None:
    path = tmp_path / "regions.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(EntryFileError, match="regions.json"):
        load_regions(path)


def test_an_absent_outline_file_is_an_error_and_not_an_empty_list(tmp_path: Path) -> None:
    with pytest.raises(EntryFileError, match="cannot be read as JSON"):
        load_regions(tmp_path / "regions.json")


def test_an_outline_file_that_is_no_utf8_text_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "regions.json"
    path.write_bytes(b"\xff\xfe{}")
    with pytest.raises(EntryFileError, match="cannot be read as JSON"):
        load_regions(path)


# --- sort_title and link_host ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "key"),
    [
        ("Example Atlas", "example atlas"),
        ("  Zürich   Cadastre  ", "zurich cadastre"),
        ("Sentinel-1 GRD", "sentinel 1 grd"),
        ("Größe_Ärger", "grosse arger"),
        ("", ""),
        ("---", ""),
    ],
)
def test_the_sort_title_is_lower_case_without_accents_and_with_single_spaces(title: str, key: str) -> None:
    assert sort_title(title) == key


def test_titles_that_differ_only_in_case_or_accent_have_one_sort_title() -> None:
    assert sort_title("Éclair") == sort_title("ECLAIR") == sort_title("eclair")


@pytest.mark.parametrize(
    ("url", "host"),
    [
        ("https://data.example.org/atlas", "data.example.org"),
        ("https://Data.Example.ORG/atlas", "data.example.org"),
        ("https://data.example.org:8443/atlas?x=1#top", "data.example.org"),
        ("https://reader@data.example.org/atlas", "data.example.org"),
        ("https://data.example.org", "data.example.org"),
    ],
)
def test_the_link_host_is_the_lower_case_host_name(url: str, host: str) -> None:
    assert link_host(url) == host


@pytest.mark.parametrize("url", ["", "https:///atlas", "atlas", "https://:8443/atlas"])
def test_a_link_without_a_host_is_an_error(url: str) -> None:
    with pytest.raises(ConfigError, match="has no host"):
        link_host(url)


# --- read_query: the token -------------------------------------------------------------------------------------------


def _query(**params: object):
    base: dict[str, object] = {
        "q": None,
        "bbox": None,
        "intersects": None,
        "datetime": None,
        "limit": None,
        "offset": None,
    }
    return read_query(**{**base, **params})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "key",
    [("example atlas", "example-atlas"), ("zurich cadastre", "a"), ("", ""), ("größe ünï ☃", "id.with_chars-1")],
)
def test_a_token_round_trips_through_read_query(key: tuple[str, str]) -> None:
    assert _query(token=encode_token(key)).after == key


def test_a_token_is_ascii_and_fit_for_a_url() -> None:
    token = encode_token(("größe ☃", "id"))
    assert token.isascii() and " " not in token


def test_a_query_without_a_token_starts_at_the_first_page() -> None:
    assert _query().after is None


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


@pytest.mark.parametrize(
    "token",
    [
        "!!!",
        "not base64 at all",
        "a",
        _b64(b"not json"),
        _b64(b"\xff\xfe"),
        _b64(b""),
        _b64(json.dumps(["only one"]).encode()),
        _b64(json.dumps(["a", "b", "c"]).encode()),
        _b64(json.dumps([1, 2]).encode()),
        _b64(json.dumps(["a", None]).encode()),
        _b64(json.dumps({"a": "b"}).encode()),
        _b64(json.dumps("ab").encode()),
        _b64(json.dumps(None).encode()),
        "ü" * 10,
        "A" * 1001,
        encode_token(("x" * 1000, "id")),
    ],
    ids=lambda value: str(value)[:12],
)
def test_a_token_this_api_did_not_give_out_is_a_400(token: str) -> None:
    with pytest.raises(HTTPException) as error:
        _query(token=token)
    assert error.value.status_code == 400 and "token" in error.value.detail


def test_a_refused_token_is_not_repeated_in_the_answer() -> None:
    token = _b64(b"secret-" + SECRET.encode())
    with pytest.raises(HTTPException) as error:
        _query(token=token)
    assert token not in error.value.detail and SECRET not in error.value.detail


def test_a_token_with_text_is_a_400() -> None:
    with pytest.raises(HTTPException) as error:
        _query(q="atlas", token=encode_token(("a", "b")))
    assert error.value.status_code == 400 and "token" in error.value.detail


def test_a_whitespace_text_is_no_text_so_a_token_is_fine() -> None:
    assert _query(q="   ", token=encode_token(("a", "b"))).after == ("a", "b")


# --- read_query: pages -----------------------------------------------------------------------------------------------


def test_an_offset_without_text_is_a_400_even_if_it_is_zero() -> None:
    for offset in (0, 20):
        with pytest.raises(HTTPException) as error:
            _query(offset=offset)
        assert error.value.status_code == 400 and "token" in error.value.detail


def test_an_offset_with_text_is_a_page_of_the_ranked_search() -> None:
    query = _query(q="atlas", offset=40)
    assert (query.text, query.offset, query.after) == ("atlas", 40, None)


@pytest.mark.parametrize(
    ("limit", "expected"),
    [(None, DEFAULT_PAGE), (1, 1), (999, 999), (1000, 1000), (1001, 1000), (10**9, 1000)],
)
def test_without_text_the_limit_defaults_to_100_and_is_capped_at_1000(limit: int | None, expected: int) -> None:
    assert (DEFAULT_PAGE, MAX_LISTING_PAGE) == (100, 1000)
    assert _query(limit=limit).limit == expected


@pytest.mark.parametrize("limit", [(None, 20), (5, 5), (20, 20), (21, 20), (1000, 20)])
def test_with_text_the_limit_defaults_to_20_and_is_capped_at_20(limit: tuple[int | None, int]) -> None:
    assert MAX_TEXT_PAGE == 20
    assert _query(q="atlas", limit=limit[0]).limit == limit[1]


# --- read_query: entry, region, area ---------------------------------------------------------------------------------


@pytest.mark.parametrize("entry", [None, "full", "listed"])
def test_an_entry_kind_reads(entry: str | None) -> None:
    assert _query(entry=entry).entry == entry
    assert _query(q="atlas", entry=entry).entry == entry


@pytest.mark.parametrize("entry", ["", "all", "Full", "LISTED", "full,listed", " full"])
def test_an_entry_that_is_not_full_or_listed_is_a_400(entry: str) -> None:
    for text in (None, "atlas"):
        with pytest.raises(HTTPException) as error:
            _query(q=text, entry=entry)
        assert error.value.status_code == 400 and "entry" in error.value.detail


def test_regions_read_from_a_list_or_a_comma_separated_text_sorted_and_without_duplicates() -> None:
    assert _query(region="DE-BY, AT,DE-BY").regions == ("AT", "DE-BY")
    assert _query(region=["DE-BY", "AT", "AT"]).regions == ("AT", "DE-BY")
    assert _query(region=None).regions == ()


@pytest.mark.parametrize(
    "region",
    ["de", "DEU", "DE-", "DE-BAYE", "DE-by", "DE BY", "Bavaria", "", ",", "DE,", "DE;AT", "D1", "1D"],
)
def test_a_region_that_is_no_iso_3166_code_is_a_400(region: str) -> None:
    for value in (region, [region]):
        with pytest.raises(HTTPException) as error:
            _query(region=value)
        assert error.value.status_code == 400 and "region" in error.value.detail


def test_a_region_list_that_is_empty_is_a_400() -> None:
    with pytest.raises(HTTPException) as error:
        _query(region=[])
    assert error.value.status_code == 400


def test_fifty_regions_are_a_filter_and_fifty_one_are_not() -> None:
    codes = [f"A{letter}" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"] + [
        f"B{letter}" for letter in "ABCDEFGHIJKLMNOPQRSTUVWX"
    ]
    assert len(codes) == 50
    assert len(_query(region=codes).regions) == 50
    assert len(_query(region=",".join(codes)).regions) == 50
    for value in (codes + ["BY"], ",".join(codes + ["BY"]), ["AA"] * 51):
        with pytest.raises(HTTPException) as error:
            _query(region=value)
        assert error.value.status_code == 400 and "at most 50" in error.value.detail


def test_a_refused_region_is_not_repeated_in_the_answer() -> None:
    with pytest.raises(HTTPException) as error:
        _query(region="Bavaria-ish")
    assert "Bavaria-ish" not in error.value.detail


def test_a_region_is_checked_with_text_too() -> None:
    with pytest.raises(HTTPException):
        _query(q="atlas", region="xx")
    assert _query(q="atlas", region="DE").regions == ("DE",)


def test_bbox_and_intersects_together_are_a_400() -> None:
    with pytest.raises(HTTPException) as error:
        _query(bbox="7,46,8,47", intersects=object())
    assert error.value.status_code == 400


# --- the category (M5-40 G1-G6, G5 = 2) ------------------------------------------------------------------------------


def test_a_hand_entry_names_a_category_of_the_list(tmp_path: Path) -> None:
    write_entry(tmp_path, listed_entry("example-atlas", category="boundaries"))
    [(entry, _)] = load_listed(tmp_path)
    assert entry.category == "boundaries"
    assert to_listed_collection(entry)["earthx:category"] == "boundaries"


def test_a_category_the_list_does_not_have_is_an_error(tmp_path: Path) -> None:
    write_entry(tmp_path, listed_entry("example-atlas", category="volcanoes"))
    with pytest.raises(EntryFileError, match="volcanoes is not one of categories.yaml"):
        load_listed(tmp_path)


@pytest.mark.parametrize("category", ["Water", "", "land cover", "water-and-sea"])
def test_a_category_that_is_no_id_is_refused(category: str) -> None:
    with pytest.raises(ConfigError, match="category"):
        listed_entry("example-atlas", category=category)


def test_a_category_filter_reaches_the_query() -> None:
    assert (
        read_query(
            q=None, bbox=None, intersects=None, datetime=None, limit=None, offset=None, category="water"
        ).category
        == "water"
    )


@pytest.mark.parametrize("category", ["volcanoes", "Water", ""])
def test_a_category_filter_that_is_no_category_is_a_400(category: str) -> None:
    with pytest.raises(HTTPException) as caught:
        read_query(q=None, bbox=None, intersects=None, datetime=None, limit=None, offset=None, category=category)
    assert caught.value.status_code == 400
