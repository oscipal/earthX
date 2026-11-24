"""New spellings of a graded standard licence (M5-67 plan §7): what fits one licence by S1-S3, what never does, and
the file they go to."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from earthx.catalog.entry_files import EntryFileError
from earthx.catalog.licences import LICENSES_DIR, Spelling, load_licences
from earthx.catalog.sources import read_sources
from earthx.discovery.grants import read_grant_to_all
from earthx.discovery.spellings import Proposal, dump_spellings, merge_spellings, propose, standard_refs

CATALOGUE = load_licences(read_sources(), LICENSES_DIR)
STANDARD = standard_refs(CATALOGUE, read_grant_to_all(CATALOGUE.terms).licenses)


def found(statement: str) -> tuple[str, str] | None:
    proposals = propose([statement], CATALOGUE, STANDARD)
    return (proposals[0].license_ref, proposals[0].rule) if proposals else None


def test_the_standard_licences_are_graded_granted_and_named_by_spdx_or_their_licensor() -> None:
    assert {"cc0-1.0", "cc-by-4.0", "dl-de-by-2.0", "dl-de-zero-2.0", "opendata-swiss-by"} <= STANDARD
    # Graded, but not granted to all (official work), a grade of its own (K6) or a publisher's own licence.
    assert not {"de-official-work", "nb-gdikom-b", "lba-free-use"} & STANDARD


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("http://www.creativecommons.org/publicdomain/zero/1.0/legalcode", ("cc0-1.0", "S1")),
        ("https://creativecommons.org/publicdomain/zero/1.0/deed.fr", ("cc0-1.0", "S1")),
        ("https://opendata.swiss/de/terms-of-use#terms_by", ("opendata-swiss-by", "S1")),
        ("https://opendata.swiss/fr/terms-of-use/#terms_open", ("opendata-swiss-open", "S1")),
        ("CC BY 4.0", ("cc-by-4.0", "S2")),
        ("cc_by_4.0", ("cc-by-4.0", "S2")),
        ("DL-DE BY 2.0", ("dl-de-by-2.0", "S2")),
        ("Datenlizenz Deutschland - Zero - Version 2.0", ("dl-de-zero-2.0", "S3")),
        ("datenlizenz  deutschland — zero — version 2.0", ("dl-de-zero-2.0", "S3")),
    ],
)
def test_a_spelling_that_fits_exactly_one_standard_licence(statement: str, expected: tuple[str, str]) -> None:
    assert found(statement) == expected


@pytest.mark.parametrize(
    "statement",
    [
        "CC BY",  # no version
        "CC BY 3.0",  # no such licence graded (only the German port)
        "CC BY-NC-SA 4.0",  # not graded
        "https://opendata.swiss/de/terms-of-use",  # the fragment carries the meaning
        "https://creativecommons.org/licenses/by-nc/4.0/",  # NC where none is graded with this address
        "Datenlizenz Deutschland – Zero – Version 2.0. Quelle: Landkreis Leer",  # a text with an addition
        "CC BY 4.0 und ODbL",  # two licences
        "Es gelten keine Zugriffsbeschränkungen",  # no licence
        "§ 5 UrhG (amtliches Werk) 1965",  # graded, never granted to all
    ],
)
def test_a_statement_that_waits(statement: str) -> None:
    assert found(statement) is None


def test_a_known_statement_is_no_new_spelling() -> None:
    assert propose(["https://creativecommons.org/publicdomain/zero/1.0"], CATALOGUE, STANDARD) == []


def test_an_ambiguous_spelling_is_none(tmp_path: Path) -> None:
    terms = (LICENSES_DIR / "terms.yaml").read_text(encoding="utf-8")
    # Give CC BY 4.0's identifier to a second graded licence: the identifier no longer names exactly one.
    terms = terms.replace("spdx_id: CC0-1.0", "spdx_id: CC-BY-4.0")
    (tmp_path / "terms.yaml").write_text(terms, encoding="utf-8")
    catalogue = load_licences(read_sources(), tmp_path)
    assert propose(["CC BY 4.0"], catalogue, frozenset({"cc0-1.0", "cc-by-4.0"})) == []


def _catalogue_with(tmp_path: Path, spellings: str) -> Path:
    (tmp_path / "terms.yaml").write_text((LICENSES_DIR / "terms.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "spellings.yaml").write_text(spellings, encoding="utf-8")
    return tmp_path


def test_a_spelling_counts_like_a_match_and_changes_the_fingerprint(tmp_path: Path) -> None:
    line = "- {license_ref: cc-by-4.0, statement: CC BY 4.0, rule: S2, added_on: 2026-11-24}\n"
    catalogue = load_licences(read_sources(), _catalogue_with(tmp_path, line))
    assert catalogue.by_statement["CC BY 4.0"] == "cc-by-4.0" and catalogue.spellings == {"CC BY 4.0": "cc-by-4.0"}
    (tmp_path / "plain").mkdir()
    plain = load_licences(read_sources(), _catalogue_with(tmp_path / "plain", "[]\n"))
    assert "CC BY 4.0" not in plain.by_statement and plain.fingerprint != catalogue.fingerprint


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("- {license_ref: cc-by-9.9, statement: x, rule: S2, added_on: 2026-11-24}", "not in terms.yaml"),
        ("- {license_ref: cc-by-4.0, statement: x, rule: S9, added_on: 2026-11-24}", "S1, S2 or S3"),
        (
            "- {license_ref: cc-by-4.0, statement: 'https://creativecommons.org/publicdomain/zero/1.0', rule: S1,"
            " added_on: 2026-11-24}",
            "already means cc0-1.0",
        ),
        ("- {license_ref: cc-by-4.0, statement: x, rule: S2, added_on: 2999-01-01}", "future"),
        ("- {license_ref: cc-by-4.0, statement: ' ', rule: S2, added_on: 2026-11-24}", "non-blank"),
        ("- {license_ref: lba-free-use, statement: LBA 1.0, rule: S2, added_on: 2026-11-24}", "standard licence"),
        (
            "- {license_ref: cc-by-4.0, statement: x, rule: S2, added_on: 2026-11-24, withdrawn_on: 2026-11-20}",
            "before added_on",
        ),
    ],
)
def test_a_wrong_spelling_file(tmp_path: Path, line: str, message: str) -> None:
    with pytest.raises(EntryFileError, match=message):
        load_licences(read_sources(), _catalogue_with(tmp_path, line + "\n"))


def test_merge_keeps_old_lines_and_their_day_and_dump_loads_again(tmp_path: Path) -> None:
    old = Spelling("cc0-1.0", "CC0 1.0", "S2", date(2026, 11, 20))
    merged = merge_spellings(
        [old], [Proposal("cc0-1.0", "CC0 1.0", "S2"), Proposal("cc-by-4.0", "CC BY 4.0", "S2")], date(2026, 11, 24)
    )
    assert merged == [Spelling("cc-by-4.0", "CC BY 4.0", "S2", date(2026, 11, 24)), old]
    catalogue = load_licences(read_sources(), _catalogue_with(tmp_path, dump_spellings(merged)))
    assert set(catalogue.spellings) == {"CC0 1.0", "CC BY 4.0"}


def test_a_withdrawn_spelling_counts_no_more_and_is_never_added_again(tmp_path: Path) -> None:
    line = "- {license_ref: cc-by-4.0, statement: CC BY 4.0, rule: S2, added_on: 2026-11-20, withdrawn_on: 2026-11-24}\n"
    directory = _catalogue_with(tmp_path, line)
    catalogue = load_licences(read_sources(), directory)
    assert "CC BY 4.0" not in catalogue.by_statement
    old = Spelling("cc-by-4.0", "CC BY 4.0", "S2", date(2026, 11, 20), date(2026, 11, 24))
    merged = merge_spellings([old], [Proposal("cc-by-4.0", "CC BY 4.0", "S2")], date(2026, 11, 25))
    assert merged == [old]
    assert "withdrawn_on: 2026-11-24" in dump_spellings(merged)
