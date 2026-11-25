"""Warning signs on a harvested find (M5-67 plan §5): each sign alone, near misses, cleared signs and the rules file."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from earthx.catalog.entry_files import EntryFileError
from earthx.discovery.flags import FLAGS_FILE, FlagEntry, flags_of, load_flag_rules, read_flag_rules
from earthx.discovery.geodata import load_geodata_rule

RULES = load_flag_rules()
GEODATA = load_geodata_rule()
PLAIN = FlagEntry(
    dataset_id="govdata.x",
    title="Bodenkarte des Kantons Zug",
    description="Synthetisch.",
    keywords=("boden",),
    publisher="Amt für Umwelt",
    category="geology_soil",
    data_kind="vector",
    link="https://amt.example.org/daten/bodenkarte",
)


def codes(**changes: object) -> list[tuple[str, str]]:
    return [(f.code, f.why) for f in flags_of(replace(PLAIN, **changes), RULES, GEODATA)]  # type: ignore[arg-type]


def test_a_plain_entry_has_no_sign() -> None:
    assert codes() == []


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"title": "Bibliothekenstatistik der Öffentlichen Bibliotheken im Kanton Thurgau"}, "W1"),
        ({"title": "Aktuelle Lage in der Stadt Aachen zum Corona-Virus"}, "W1"),
        ({"title": "Verkehrsstatistiken Zählstellen"}, "W1"),
        ({"title": "snowBedFoam solver"}, "W1"),
        ({"publisher": "Identitas AG"}, "W2"),
        ({"publisher": "Statistisches Landesamt des Freistaates Sachsen"}, "W2"),
        ({"link": "https://www.amt.example.org/de/"}, "W3"),
        ({"link": "https://www.amt.example.org/umwelt/home.html"}, "W3"),
        ({"link": "https://www.amt.example.org/de/startseite"}, "W3"),
        ({"category": "optical", "data_kind": "table"}, "W4"),
        ({"category": "elevation", "data_kind": "document"}, "W4"),
        ({"title": "[BfTMAP] KOPIE MItarbeiter als Dienst"}, "W5"),
        ({"title": "Testdaten Wasserleitungen"}, "W5"),
        ({"description": "Fragen an hans.muster@amt.example.org"}, "W6"),
        ({"description": "Auskunft unter Tel. 041 728 33 11"}, "W6"),
        ({"description": "Auskunft: +41 41 728 33 11"}, "W6"),
        ({"title": "AB"}, "W7"),
        ({"title": "bodenkarte_2020.zip"}, "W7"),
    ],
)
def test_each_sign(changes: dict[str, object], expected: str) -> None:
    assert expected in [code for code, _ in codes(**changes)]


@pytest.mark.parametrize(
    "changes",
    [
        {"title": "Alarmanlagen der Gemeinde"},  # no "test" or "lärm" inside a word
        {"title": "Testament des Grafen, Karte"},
        {"link": "https://www.amt.example.org/umwelt/boden/karte-2020"},
        {"link": "https://data.geo.admin.ch/browser/index.html#/collections/ch.bafu.boden"},
        {"category": "optical", "data_kind": "raster"},
        {"category": "elevation", "data_kind": "service"},
        {"description": "Stand 2020-01-31, Version 1.2.3, Massstab 1:25 000"},
        {"title": "Karte der Wanderwege in der Gemeinde Zug.Stadt"},
    ],
)
def test_near_misses_give_no_sign(changes: dict[str, object]) -> None:
    assert codes(**changes) == []


def test_a_mail_address_is_never_quoted_in_the_sign() -> None:
    assert codes(description="hans.muster@amt.example.org") == [("W6", "mail")]


def test_a_cleared_sign_is_passed_over_and_only_for_that_entry() -> None:
    rules = replace(RULES, cleared=frozenset({("govdata.x", "W1")}))
    entry = replace(PLAIN, title="Verkehrsstatistik Zählstellen", publisher="Identitas AG")
    assert [f.code for f in flags_of(entry, rules, GEODATA)] == ["W2"]
    assert [f.code for f in flags_of(replace(entry, dataset_id="govdata.y"), rules, GEODATA)] == ["W1", "W2"]


def test_the_shipped_rules_load() -> None:
    rules = read_flag_rules(FLAGS_FILE)
    assert rules.imagery_categories == {"optical", "radar", "elevation"} and not rules.cleared


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"imagery_categories": ["satellite"]}, "categories of categories.yaml"),
        ({"imagery_kinds": ["picture"]}, "data kinds"),
        ({"min_title_chars": 0}, "min_title_chars"),
        ({"cleared": [{"dataset_id": "govdata.x", "code": "W9", "cleared_on": "2026-11-25"}]}, "cleared holds"),
        ({"cleared": [{"dataset_id": "../x", "code": "W1", "cleared_on": "2026-11-25"}]}, "cleared holds"),
        ({"general_pages": ["Start Seite"]}, "single plain words"),
        ({"copy_words": ["*ko*pie"]}, "one end of one word"),
        ({"extra": 1}, "holds exactly"),
    ],
)
def test_a_wrong_rules_file(tmp_path: Path, change: dict[str, object], message: str) -> None:
    data = yaml.safe_load(FLAGS_FILE.read_text(encoding="utf-8"))
    data.update(change)
    path = tmp_path / "flags.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(EntryFileError, match=message):
        read_flag_rules(path)


def test_a_cleared_entry_with_a_day_loads(tmp_path: Path) -> None:
    text = FLAGS_FILE.read_text(encoding="utf-8").replace(
        "cleared: []", "cleared:\n  - {dataset_id: govdata.x, code: W1, cleared_on: 2026-11-25}"
    )
    path = tmp_path / "flags.yaml"
    path.write_text(text, encoding="utf-8")
    assert read_flag_rules(path).cleared == {("govdata.x", "W1")}


@pytest.mark.parametrize("cleared", ["", "cleared:\n", "cleared: []\n"])
def test_a_rules_file_without_cleared_entries_loads_with_none(tmp_path: Path, cleared: str) -> None:
    # M5-67 fix 2: nothing cleared is the usual state, so the key may be missing or empty; every other key stays required.
    text = FLAGS_FILE.read_text(encoding="utf-8").replace("cleared: []\n", cleared)
    path = tmp_path / "flags.yaml"
    path.write_text(text, encoding="utf-8")
    assert read_flag_rules(path).cleared == frozenset()


def test_a_rules_file_without_a_rule_does_not_load_as_if_it_had_none(tmp_path: Path) -> None:
    # An empty file is no rule set: without the words the warning signs would let everything through.
    path = tmp_path / "flags.yaml"
    path.write_text("cleared: []\n", encoding="utf-8")
    with pytest.raises(EntryFileError, match="holds exactly"):
        read_flag_rules(path)
    path.write_text("", encoding="utf-8")
    with pytest.raises(EntryFileError, match="holds exactly"):
        read_flag_rules(path)
