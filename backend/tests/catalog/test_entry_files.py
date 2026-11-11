"""Reading a registry entry from YAML strictly (docs/plans/m5/m5-13-yaml-lader.md §3.2, §4).

Every case writes a file into ``tmp_path``: the DEM entry as plain data, changed in one place. The source of truth
for what an entry may hold stays the dataclasses; these tests only hold that the file layer neither drops nor
reinterprets anything on the way there.
"""

from __future__ import annotations

import copy
from datetime import date
from pathlib import Path

import pytest
import yaml

from earthx.catalog import registry as registry_module
from earthx.catalog.datasets import CATALOG_DIR
from earthx.catalog.entry_files import EntryFileError, load_entry, load_retired, read_yaml, to_plain
from earthx.catalog.registry import ENTRY_FILE_CONFIG, DatasetConfig, LicenseTier, RetiredDataset
from tests.catalog.entries import COP_DEM_GLO_30, RETIRED

DEM = COP_DEM_GLO_30.dataset_id


def _plain() -> dict:
    return copy.deepcopy(to_plain(COP_DEM_GLO_30))


def _write(tmp_path: Path, data: object, name: str = f"{DEM}.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def _write_text(tmp_path: Path, text: str, name: str = f"{DEM}.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_an_entry_comes_back_equal_through_its_file(tmp_path: Path) -> None:
    assert load_entry(_write(tmp_path, _plain())) == COP_DEM_GLO_30


def test_the_plain_data_of_a_loaded_entry_is_what_its_file_holds(tmp_path: Path) -> None:
    path = _write(tmp_path, _plain())
    assert to_plain(load_entry(path)) == read_yaml(path)


def test_retired_datasets_come_back_equal_through_their_file(tmp_path: Path) -> None:
    path = _write(tmp_path, [to_plain(gone) for gone in RETIRED], "retired.yaml")
    assert load_retired(path) == RETIRED


@pytest.mark.parametrize(
    ("change", "where"),
    [
        (lambda d: d.update(colour="red"), "colour"),
        (lambda d: d["license"].update(colour="red"), "license.colour"),
        (lambda d: d["providers"][0].update(colour="red"), "providers.0.colour"),
    ],
    ids=["top", "nested", "in-a-list"],
)
def test_an_unknown_field_is_an_error_with_its_path(tmp_path: Path, change, where: str) -> None:
    data = _plain()
    change(data)
    with pytest.raises(EntryFileError, match=rf"{DEM}\.yaml: .*{where}"):
        load_entry(_write(tmp_path, data))


@pytest.mark.parametrize(("parent", "field"), [((), "gsd"), (("license",), "tier"), (("access",), "cors")])
def test_a_missing_field_is_an_error(tmp_path: Path, parent: tuple[str, ...], field: str) -> None:
    data = _plain()
    target = data
    for key in parent:
        target = target[key]
    del target[field]
    with pytest.raises(EntryFileError, match=".".join((*parent, field))):
        load_entry(_write(tmp_path, data))


@pytest.mark.parametrize("word", ["yes", "no", "on", "off", "y", "n"])
def test_a_yaml_1_1_boolean_word_is_no_boolean(tmp_path: Path, word: str) -> None:
    text = yaml.safe_dump(_plain(), sort_keys=False).replace("commercial_use: true", f"commercial_use: {word}")
    with pytest.raises(EntryFileError, match="license.commercial_use"):
        load_entry(_write_text(tmp_path, text))


def test_an_unquoted_date_reads_as_the_date(tmp_path: Path) -> None:
    text = yaml.safe_dump(_plain(), sort_keys=False)
    checked = COP_DEM_GLO_30.access.token_free_checked_at.isoformat()
    assert f"token_free_checked_at: '{checked}'" in text
    entry = load_entry(_write_text(tmp_path, text.replace(f"'{checked}'", checked)))
    assert entry.access.token_free_checked_at == date.fromisoformat(checked)


def test_a_sexagesimal_number_stays_text(tmp_path: Path) -> None:
    data = _plain()
    data["gsd"] = ["1:30"]
    with pytest.raises(EntryFileError, match="gsd.0"):
        load_entry(_write(tmp_path, data))


@pytest.mark.parametrize(
    ("field", "value"),
    [("title", 123), ("gsd", ["thirty"]), ("license", "CC-BY-4.0"), ("keywords", "elevation"), ("description", None)],
)
def test_a_value_of_the_wrong_type_is_an_error(tmp_path: Path, field: str, value: object) -> None:
    data = _plain()
    data[field] = value
    with pytest.raises(EntryFileError, match=rf"\b{field}\b"):
        load_entry(_write(tmp_path, data))


def test_an_unknown_enum_value_is_an_error(tmp_path: Path) -> None:
    data = _plain()
    data["license"]["tier"] = "everything"
    with pytest.raises(EntryFileError, match="license.tier"):
        load_entry(_write(tmp_path, data))


def test_a_check_of_the_dataclass_still_holds(tmp_path: Path) -> None:
    data = _plain()
    data["gsd"] = []
    with pytest.raises(EntryFileError, match=DEM):
        load_entry(_write(tmp_path, data))


def test_the_message_names_no_value(tmp_path: Path) -> None:
    data = _plain()
    data["title"] = 4711
    data["license"]["tier"] = "secret-tier-value"
    with pytest.raises(EntryFileError) as raised:
        load_entry(_write(tmp_path, data))
    assert "4711" not in str(raised.value) and "secret-tier-value" not in str(raised.value)


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("title: a\ntitle: b\n", "duplicate key"),
        ("a: &x 1\nb: *x\n", "anchor"),
        ("a: [1\n", "not valid YAML"),
        ("a: *nowhere\n", "alias"),
        ("license:\n  name: a\n  name: b\n", "duplicate key"),
        ("1: a\n'1': b\n", "key is not text"),
        ("band_units:\n  true: m\n", "key is not text"),
        ("? [a]\n: 1\n", "key is not text"),
        ("a: !!python/object:os.system x\n", "not valid YAML"),
    ],
    ids=[
        "duplicate-key",
        "anchor-and-alias",
        "broken",
        "alias-alone",
        "nested-duplicate-key",
        "number-key",
        "boolean-key",
        "compound-key",
        "python-tag",
    ],
)
def test_a_file_that_is_no_plain_yaml_is_an_error(tmp_path: Path, text: str, problem: str) -> None:
    with pytest.raises(EntryFileError, match=problem):
        load_entry(_write_text(tmp_path, text))


def test_an_explicit_timestamp_tag_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(EntryFileError, match="no text, number"):
        load_entry(_write_text(tmp_path, "title: !!timestamp 2026-01-01\n"))


@pytest.mark.parametrize("text", ["", "- a\n- b\n", "just text\n"], ids=["empty", "list", "scalar"])
def test_an_entry_is_a_mapping(tmp_path: Path, text: str) -> None:
    with pytest.raises(EntryFileError, match="mapping"):
        load_entry(_write_text(tmp_path, text))


def test_binary_garbage_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / f"{DEM}.yaml"
    path.write_bytes(b"\xff\xfe\x00\x81garbage")
    with pytest.raises(EntryFileError, match="UTF-8"):
        load_entry(path)


def test_the_file_is_named_after_its_dataset_id(tmp_path: Path) -> None:
    with pytest.raises(EntryFileError, match="<dataset_id>.yaml"):
        load_entry(_write(tmp_path, _plain(), "elevation.yaml"))


def test_retired_datasets_are_a_list(tmp_path: Path) -> None:
    with pytest.raises(EntryFileError, match="list"):
        load_retired(_write(tmp_path, to_plain(RETIRED[0]), "retired.yaml"))


def test_an_error_in_a_retired_dataset_names_its_place(tmp_path: Path) -> None:
    data = [to_plain(gone) for gone in RETIRED]
    data[0]["retired_on"] = "yesterday"
    with pytest.raises(EntryFileError, match=r"retired\.yaml\[0\]: retired_on"):
        load_retired(_write(tmp_path, data, "retired.yaml"))


def test_to_plain_writes_enums_dates_and_sets_as_plain_values() -> None:
    plain = to_plain(COP_DEM_GLO_30)
    assert plain["license"]["tier"] == LicenseTier.PROCESSING.value
    assert plain["temporal_extent"]["start"] == COP_DEM_GLO_30.temporal_extent.start.isoformat()
    assert list(plain) == [name for name in COP_DEM_GLO_30.__dataclass_fields__]


def test_an_instant_without_a_time_zone_is_an_error(tmp_path: Path) -> None:
    data = _plain()
    data["temporal_extent"]["start"] = "2010-12-01T00:00:00"
    with pytest.raises(EntryFileError, match="time zone offset"):
        load_entry(_write(tmp_path, data))


@pytest.mark.parametrize(
    "path", sorted((CATALOG_DIR / "datasets").glob("*.yaml")), ids=lambda path: path.name
)
def test_every_entry_file_round_trips(path: Path) -> None:
    """Plan §3.3: what an entry file holds is exactly what its entry gives back, so no field is lost on the way."""
    assert to_plain(load_entry(path)) == read_yaml(path)


def test_the_retired_file_round_trips() -> None:
    path = CATALOG_DIR / "retired.yaml"
    assert [to_plain(gone) for gone in load_retired(path)] == read_yaml(path)


def _dataclasses_below(kind: type, seen: set[type]) -> None:
    import dataclasses
    import typing

    if kind in seen:
        return
    seen.add(kind)
    hints = typing.get_type_hints(kind, vars(registry_module))
    for field in dataclasses.fields(kind):
        stack = [hints[field.name]]
        while stack:
            hint = stack.pop()
            stack.extend(typing.get_args(hint))
            if isinstance(hint, type) and dataclasses.is_dataclass(hint):
                _dataclasses_below(hint, seen)


def test_every_dataclass_of_an_entry_is_read_strictly() -> None:
    """A new nested dataclass without ``ENTRY_FILE_CONFIG`` would quietly accept unknown fields."""
    seen: set[type] = set()
    for kind in (DatasetConfig, RetiredDataset):
        _dataclasses_below(kind, seen)
    loose = sorted(kind.__name__ for kind in seen if getattr(kind, "__pydantic_config__", None) is not ENTRY_FILE_CONFIG)
    assert not loose


@pytest.mark.parametrize("field", ["overview", "overview_resampling"])
def test_the_overview_fields_of_the_viewer_are_not_optional(tmp_path: Path, field: str) -> None:
    data = _plain()
    del data["viewer"][field]
    with pytest.raises(EntryFileError, match=rf"viewer\.{field}"):
        load_entry(_write(tmp_path, data))


@pytest.mark.parametrize("field", ["overview", "overview_resampling"])
def test_an_unknown_overview_value_is_an_error(tmp_path: Path, field: str) -> None:
    data = _plain()
    data["viewer"][field] = "bilinear"
    with pytest.raises(EntryFileError, match=rf"viewer\.{field}"):
        load_entry(_write(tmp_path, data))


def test_the_checks_of_the_overview_hold_in_a_file(tmp_path: Path) -> None:
    data = _plain()
    data["viewer"].update(overview="own", overview_resampling=None, min_zoom=3)
    with pytest.raises(EntryFileError, match="no image below min_zoom"):
        load_entry(_write(tmp_path, data))
    data["viewer"].update(overview="pyramid", overview_resampling=None)
    with pytest.raises(EntryFileError, match="overview_resampling is required"):
        load_entry(_write(tmp_path, data))
