"""The licence catalogue and the grants per source (adr/0033 §6.2, L2; M5-20 plan §9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from earthx.catalog.entry_files import EntryFileError
from earthx.catalog.licences import LICENSES_DIR, load_licences, normal_statement
from earthx.catalog.registry import LicenseTier
from earthx.catalog.sources import read_sources

TERM = """\
- license_ref: {ref}
  matches: {matches}
  license:
    spdx_id: {spdx}
    name: Example licence {ref}
    url: https://licences.example.org/{ref}
    commercial_use: {commercial}
    distribution: true
    derivatives: {derivatives}
    share_alike: false
    attribution_required: true
    tier: {tier}
    attribution_modified: "{{publisher}} (modified)"
    attribution_unmodified: "{{publisher}}"
    terms: null
  approved_on: 2026-11-19
"""


def _term(
    ref: str, matches: str, *, spdx: str = "null", commercial: str = "true", derivatives: str = "true", tier: str = "catalog"
) -> str:
    return TERM.format(ref=ref, matches=matches, spdx=spdx, commercial=commercial, derivatives=derivatives, tier=tier)


def _write(tmp_path: Path, terms: str, grants: dict[str, str] | None = None) -> Path:
    (tmp_path / "terms.yaml").write_text(terms, encoding="utf-8")
    (tmp_path / "grants").mkdir()
    for source, text in (grants or {}).items():
        (tmp_path / "grants" / f"{source}.yaml").write_text(text, encoding="utf-8")
    return tmp_path


BY = _term("cc-by-4.0", "[CC-BY-4.0, 'http://dcat-ap.de/def/licenses/cc-by/4.0']", spdx="CC-BY-4.0")
NC = _term("cc-by-nc-4.0", "[CC-BY-NC-4.0]", commercial="false")
GRANTS = {
    "govdata": """\
- publisher: Amt für Beispiele
  licenses: [cc-by-4.0, cc-by-nc-4.0]
  approved_on: 2026-11-19
- publisher: Stadt Beispiel
  licenses: [cc-by-4.0]
  approved_on: 2026-11-19
"""
}
SOURCES = ("govdata", "opendata-swiss")


def _catalogue(tmp_path: Path, terms: str = BY + NC, grants: dict[str, str] | None = None):
    return load_licences(SOURCES, _write(tmp_path, terms, GRANTS if grants is None else grants))


class TestTheShippedFiles:
    def test_they_load_and_are_empty_until_otto_grades_the_first_licences(self) -> None:
        # F5 = 1: license-checker proposes, Otto writes; nothing graded by the session.
        catalogue = load_licences(read_sources(), LICENSES_DIR)
        assert dict(catalogue.terms) == {} and dict(catalogue.grants) == {}


class TestMatch:
    def test_a_granted_statement_gives_the_licence_and_the_rule(self, tmp_path: Path) -> None:
        statement = "http://dcat-ap.de/def/licenses/cc-by/4.0/"
        found = _catalogue(tmp_path).match("govdata", "Amt für Beispiele", [statement])
        assert (found.reason, found.rule, found.refs) == (None, "govdata/Amt für Beispiele/cc-by-4.0", ("cc-by-4.0",))
        assert found.license is not None and found.license.spdx_id == "CC-BY-4.0"

    @pytest.mark.parametrize(
        ("statements", "reason"),
        [
            ([], "no_licence"),
            (["  "], "no_licence"),
            (["cc-by-4.0"], "unknown_licence"),  # case counts: verbatim only
            (["CC BY 4.0"], "unknown_licence"),
            (["CC-BY-4.0", "something else"], "unknown_licence"),
        ],
    )
    def test_what_waits(self, tmp_path: Path, statements: list[str], reason: str) -> None:
        assert _catalogue(tmp_path).match("govdata", "Amt für Beispiele", statements).reason == reason

    def test_a_licence_not_granted_to_the_publisher_waits(self, tmp_path: Path) -> None:
        catalogue = _catalogue(tmp_path)
        assert catalogue.match("govdata", "Stadt Beispiel", ["CC-BY-NC-4.0"]).reason == "not_granted"
        assert catalogue.match("govdata", "Unbekannt", ["CC-BY-4.0"]).reason == "not_granted"
        assert catalogue.match("govdata", None, ["CC-BY-4.0"]).reason == "not_granted"
        assert catalogue.match("opendata-swiss", "Amt für Beispiele", ["CC-BY-4.0"]).reason == "not_granted"

    def test_the_publisher_is_compared_exactly(self, tmp_path: Path) -> None:
        assert _catalogue(tmp_path).match("govdata", "amt für beispiele", ["CC-BY-4.0"]).reason == "not_granted"

    def test_several_licences_give_the_narrowest(self, tmp_path: Path) -> None:
        # Plan A10: every flag only where all allow it, the grade of the narrowest.
        found = _catalogue(tmp_path).match("govdata", "Amt für Beispiele", ["CC-BY-4.0", "CC-BY-NC-4.0"])
        assert found.reason is None and found.rule == "govdata/Amt für Beispiele/cc-by-4.0+cc-by-nc-4.0"
        assert found.license is not None and not found.license.commercial_use
        assert found.license.tier is LicenseTier.CATALOG

    def test_a_statement_twice_counts_once(self, tmp_path: Path) -> None:
        found = _catalogue(tmp_path).match("govdata", "Stadt Beispiel", ["CC-BY-4.0", "CC-BY-4.0/"])
        assert found.refs == ("cc-by-4.0",)


@pytest.mark.parametrize(("value", "normal"), [(" a/ ", "a"), ("a//", "a/"), ("A", "A"), ("", "")])
def test_normal_statement(value: str, normal: str) -> None:
    assert normal_statement(value) == normal


class TestLoadErrors:
    def test_a_statement_meaning_two_licences(self, tmp_path: Path) -> None:
        with pytest.raises(EntryFileError, match="already means cc-by-4.0"):
            _catalogue(tmp_path, BY + _term("other", "['CC-BY-4.0/']"), grants={})

    def test_a_licence_ref_twice(self, tmp_path: Path) -> None:
        with pytest.raises(EntryFileError, match="stands twice"):
            _catalogue(tmp_path, BY + _term("cc-by-4.0", "[x]"), grants={})

    def test_a_tier_above_catalog_without_derivatives(self, tmp_path: Path) -> None:
        # KLAERUNGEN B11: without derivatives only the catalogue.
        with pytest.raises(EntryFileError, match="tier above catalog needs derivatives"):
            _catalogue(tmp_path, _term("nd", "[ND]", derivatives="false", tier="display"), grants={})

    def test_an_unknown_field(self, tmp_path: Path) -> None:
        with pytest.raises(EntryFileError):
            _catalogue(tmp_path, BY.replace("  approved_on:", "  note: x\n  approved_on:"), grants={})

    def test_no_matches(self, tmp_path: Path) -> None:
        with pytest.raises(EntryFileError, match="matches names at least one"):
            _catalogue(tmp_path, _term("x", "[]"), grants={})

    def test_a_grant_of_a_licence_not_in_the_catalogue(self, tmp_path: Path) -> None:
        grants = {"govdata": "- {publisher: A, licenses: [dl-de-by-2.0], approved_on: 2026-11-19}\n"}
        with pytest.raises(EntryFileError, match="not in terms.yaml: dl-de-by-2.0"):
            _catalogue(tmp_path, grants=grants)

    def test_a_grant_of_an_unknown_source(self, tmp_path: Path) -> None:
        with pytest.raises(EntryFileError, match="no source of that id"):
            _catalogue(tmp_path, grants={"nowhere": "[]\n"})

    def test_a_publisher_twice(self, tmp_path: Path) -> None:
        line = "- {publisher: A, licenses: [cc-by-4.0], approved_on: 2026-11-19}\n"
        with pytest.raises(EntryFileError, match="publisher stands twice"):
            _catalogue(tmp_path, grants={"govdata": line + line})

    def test_a_publisher_with_blanks_at_the_edges(self, tmp_path: Path) -> None:
        line = "- {publisher: ' A', licenses: [cc-by-4.0], approved_on: 2026-11-19}\n"
        with pytest.raises(EntryFileError, match="exactly"):
            _catalogue(tmp_path, grants={"govdata": line})

    def test_a_day_in_the_future(self, tmp_path: Path) -> None:
        line = "- {publisher: A, licenses: [cc-by-4.0], approved_on: 2999-01-01}\n"
        with pytest.raises(EntryFileError, match="future"):
            _catalogue(tmp_path, grants={"govdata": line})

    def test_another_file_in_grants(self, tmp_path: Path) -> None:
        directory = _write(tmp_path, BY)
        (directory / "grants" / "notes.txt").write_text("x", encoding="utf-8")
        with pytest.raises(EntryFileError, match="only <source_id>.yaml"):
            load_licences(SOURCES, directory)
