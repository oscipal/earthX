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
  licence_class: {klass}
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
    ref: str,
    matches: str,
    *,
    spdx: str = "null",
    commercial: str = "true",
    derivatives: str = "true",
    tier: str = "catalog",
    klass: str = "K2",
) -> str:
    return TERM.format(
        ref=ref, matches=matches, spdx=spdx, commercial=commercial, derivatives=derivatives, tier=tier, klass=klass
    )


def _write(tmp_path: Path, terms: str, grants: dict[str, str] | None = None) -> Path:
    (tmp_path / "terms.yaml").write_text(terms, encoding="utf-8")
    (tmp_path / "grants").mkdir()
    for source, text in (grants or {}).items():
        (tmp_path / "grants" / f"{source}.yaml").write_text(text, encoding="utf-8")
    return tmp_path


BY = _term("cc-by-4.0", "[CC-BY-4.0, 'http://dcat-ap.de/def/licenses/cc-by/4.0']", spdx="CC-BY-4.0")
NC = _term("cc-by-nc-4.0", "[CC-BY-NC-4.0]", commercial="false", klass="K4")
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
    """Otto's grading of 20.11.2026 (plan §13f): the classes of the licence list with his changes."""

    @pytest.fixture(scope="class")
    def catalogue(self):  # type: ignore[no-untyped-def]
        return load_licences(read_sources(), LICENSES_DIR)

    @pytest.mark.parametrize(
        ("statement", "ref"),
        [
            ("http://dcat-ap.de/def/licenses/dl-by-de/2.0", "dl-de-by-2.0"),
            ("dl-by-de/2.0", "dl-de-by-2.0"),
            ("https://www.govdata.de/dl-de/by-2-0", "dl-de-by-2.0"),
            ("http://www.govdata.de/dl-de/by-2-0/", "dl-de-by-2.0"),
            ("Datenlizenz Deutschland – Zero – Version 2.0", "dl-de-zero-2.0"),
            ("https://opendata.swiss/terms-of-use#terms_by", "opendata-swiss-by"),
            ("https://opendata.swiss/en/terms-of-use/#terms_by", "opendata-swiss-by"),
            ("http://dcat-ap.de/def/licenses/officialWork", "de-official-work"),
            ("http://www.gesetze-im-internet.de/urhg/__5.html", "de-official-work"),
            ("http://disclaimer.admin.ch", "admin-ch-disclaimer"),
        ],
    )
    def test_every_spelling_of_a_licence_means_the_same_ref(self, catalogue, statement: str, ref: str) -> None:  # type: ignore[no-untyped-def]
        assert catalogue.by_statement[normal_statement(statement)] == ref

    @pytest.mark.parametrize(
        "statement",
        [
            "mdd-nrw-nutzungsbedingungen",
            "Weitere Informationen zu den Daten und Veröffentlichungen erhalten Sie über das Portal.",
            "http://inspire.ec.europa.eu/metadata-codelist/LimitationsOnPublicAccess/noLimitations",
        ],
    )
    def test_statements_without_a_licence_are_not_graded(self, catalogue, statement: str) -> None:  # type: ignore[no-untyped-def]
        # K7: not taken in; their finds wait.
        assert normal_statement(statement) not in catalogue.by_statement

    def test_the_classes_set_the_flags(self, catalogue) -> None:  # type: ignore[no-untyped-def]
        def flags(ref: str) -> tuple[bool, ...]:
            lic = catalogue.terms[ref].license
            return (lic.distribution, lic.commercial_use, lic.derivatives, lic.share_alike, lic.attribution_required)

        assert flags("cc0-1.0") == flags("de-official-work") == (True, True, True, False, False)
        assert flags("lba-free-use") == flags("cc-by-4.0") == (True, True, True, False, True)
        assert flags("odbl-1.0") == (True, True, True, True, True)
        assert flags("opendata-swiss-by-ask") == (True, False, True, False, True)
        assert flags("cc-by-nd-4.0") == (True, True, False, False, True)
        assert flags("nb-gdikom-b") == flags("admin-ch-terms") == (False, False, False, False, False)

    def test_the_tiers_otto_graded(self, catalogue) -> None:  # type: ignore[no-untyped-def]
        # Otto, 25.11.2026 (plan §14.1.12, F16): processing for K1 and K2, every other class stays in the catalogue.
        by_class: dict[str, set[LicenseTier]] = {}
        for term in catalogue.terms.values():
            by_class.setdefault(term.licence_class, set()).add(term.license.tier)
        assert by_class["K1"] == by_class["K2"] == {LicenseTier.PROCESSING}
        assert all(by_class[k] == {LicenseTier.CATALOG} for k in ("K3", "K4", "K5", "K6"))
        assert catalogue.terms["cc-by-sa-4.0"].licence_class == "K3"
        assert catalogue.terms["cc-by-4.0"].license.tier is LicenseTier.PROCESSING

    def test_the_texts_of_the_attribution_otto_named(self, catalogue) -> None:  # type: ignore[no-untyped-def]
        assert catalogue.terms["swisstopo-ogd"].license.attribution_unmodified == "© swisstopo"
        assert catalogue.terms["lba-free-use"].license.attribution_unmodified == "© Luftfahrt-Bundesamt"
        assert catalogue.terms["dl-de-by-2.0"].license.attribution_unmodified == (
            "{publisher}, Datenlizenz Deutschland – Namensnennung – Version 2.0"
        )
        sie_duerfen = next(s for s in catalogue.by_statement if s.startswith("Sie dürfen:\nTeilen"))
        assert catalogue.by_statement[sie_duerfen] == "cc-by-4.0"

    def test_the_identifier_beside_the_address_does_not_make_a_granted_find_wait(self, catalogue) -> None:  # type: ignore[no-untyped-def]
        # Otto, 23.11.2026: 224 finds of the Sächsisches Landesamt für Umwelt, Landwirtschaft und Geologie waited with
        # the identifier "dl-by-de/2.0" beside the address of the same licence.
        publisher = "Sächsisches Landesamt für Umwelt, Landwirtschaft und Geologie"
        found = catalogue.match("govdata", publisher, ["dl-by-de/2.0", "http://dcat-ap.de/def/licenses/dl-by-de/2.0"])
        assert (found.reason, found.refs) == (None, ("dl-de-by-2.0",))
        assert catalogue.match("govdata", publisher, ["dl-by-de/2.0"]).reason is None

    def test_a_find_with_one_statement_without_a_licence_still_waits(self, catalogue) -> None:  # type: ignore[no-untyped-def]
        found = catalogue.match("govdata", "Amt", ["http://dcat-ap.de/def/licenses/dl-by-de/2.0", "mdd-nrw-nutzungsbedingungen"])
        assert found.reason == "unknown_licence"


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

    @pytest.mark.parametrize("klass", ["K3", "K4", "K5", "K6"])
    def test_a_tier_above_catalog_outside_k1_and_k2(self, tmp_path: Path, klass: str) -> None:
        # Otto, 25.11.2026: only K1 and K2 go above the catalogue; share alike (K3) cannot pass on to results.
        with pytest.raises(EntryFileError, match="only for the classes K1 and K2"):
            _catalogue(tmp_path, _term("sa", "[SA]", tier="processing", klass=klass), grants={})

    @pytest.mark.parametrize("tier", ["catalog", "display", "processing"])
    def test_k1_and_k2_may_take_any_tier(self, tmp_path: Path, tier: str) -> None:
        catalogue = _catalogue(tmp_path, _term("by", "[BY]", tier=tier, klass="K1"), grants={})
        assert catalogue.terms["by"].license.tier.value == tier

    @pytest.mark.parametrize("klass", ["K0", "K7", "k2", "", "2"])
    def test_an_unknown_class(self, tmp_path: Path, klass: str) -> None:
        with pytest.raises(EntryFileError, match="licence_class is one of"):
            _catalogue(tmp_path, _term("x", "[X]", klass=f"'{klass}'"), grants={})

    def test_a_missing_class(self, tmp_path: Path) -> None:
        with pytest.raises(EntryFileError):
            _catalogue(tmp_path, _term("x", "[X]").replace("  licence_class: K2\n", ""), grants={})

    def test_a_k2_licence_without_commercial_use_is_misclassed(self, tmp_path: Path) -> None:
        # A non-commercial licence filed as K2 would reach the processing tier: the class is checked against the flags.
        with pytest.raises(EntryFileError, match="allows commercial use"):
            _catalogue(tmp_path, _term("nc", "[NC]", commercial="false", klass="K2"), grants={})

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


DISCLAIMER = "Es erfolgt ein kompletter Haftungsausschluss. Es wird keinerlei Gewähr für die Richtigkeit übernommen und"
NOT_A_LICENCE = f"""\
- {{statement: Es gelten keine Zugriffsbeschränkungen, kind: access, added_on: 2026-11-25}}
- {{statement: 'https://portal.example.org/api/feed/dcat-ap.json', kind: feed, added_on: 2026-11-25}}
- {{statement: '{DISCLAIMER}', kind: disclaimer, match: prefix, added_on: 2026-11-25}}
"""


class TestNotALicence:
    """M5-67 §23.5 (Otto's rule of 19.11.2026): statements that are never a licence count for no match."""

    def _with(self, tmp_path: Path, text: str = NOT_A_LICENCE):
        directory = _write(tmp_path, BY + NC, GRANTS)
        (directory / "not_a_licence.yaml").write_text(text, encoding="utf-8")
        return load_licences(SOURCES, directory)

    @pytest.mark.parametrize(
        ("statements", "reason"),
        [
            (["Es gelten keine Zugriffsbeschränkungen"], "no_licence"),
            (["https://portal.example.org/api/feed/dcat-ap.json/", " Es gelten keine Zugriffsbeschränkungen "],
             "no_licence"),
            ([DISCLAIMER + " Schäden, die …"], "no_licence"),
            (["Es gelten keine Zugriffsbeschränkungen", "CC-BY-4.0"], None),  # the graded licence decides (F18)
            (["Es gelten keine Zugriffsbeschränkungen", "something else"], "unknown_licence"),
            (["es gelten keine Zugriffsbeschränkungen"], "unknown_licence"),  # verbatim, case counts
            (["Es gelten keine Zugriffsbeschränkungen!"], "unknown_licence"),
            ([DISCLAIMER[:-10]], "unknown_licence"),  # shorter than the beginning
        ],
    )
    def test_what_waits_and_how(self, tmp_path: Path, statements: list[str], reason: str | None) -> None:
        assert self._with(tmp_path).match("govdata", "Amt für Beispiele", statements).reason == reason

    def test_the_list_changes_the_fingerprint(self, tmp_path: Path) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        assert self._with(tmp_path / "a").fingerprint != self._with(tmp_path / "b", "[]\n").fingerprint

    def test_the_shipped_list_loads_and_holds_no_licence_name(self) -> None:
        catalogue = load_licences(read_sources(), LICENSES_DIR)
        assert "Es gelten keine Zugriffsbeschränkungen" in catalogue.not_licences
        assert not catalogue.is_not_a_licence("mdd-nrw-nutzungsbedingungen")  # F19: terms of use, maybe a licence
        assert catalogue.match("govdata", "x", ["Es gelten keine Zugriffsbeschränkungen."]).reason == "no_licence"

    @pytest.mark.parametrize(
        ("text", "message"),
        [
            ("x: 1\n", "a list"),
            ("- {statement: ' ', kind: note, added_on: 2026-11-25}\n", "non-blank"),
            ("- {statement: a, kind: licence, added_on: 2026-11-25}\n", "kind is one of"),
            ("- {statement: a, kind: note, match: fuzzy, added_on: 2026-11-25}\n", "exact or prefix"),
            ("- {statement: Kurz, kind: note, match: prefix, added_on: 2026-11-25}\n", "at least 80"),
            ("- {statement: a, kind: note, added_on: 2999-01-01}\n", "in the future"),
            ("- {statement: CC-BY-4.0, kind: note, added_on: 2026-11-25}\n", "means cc-by-4.0"),
            ("- {statement: a, kind: note, added_on: 2026-11-25}\n- {statement: a/, kind: page, added_on: 2026-11-25}\n",
             "twice"),
            ("- {statement: a, kind: note, added_on: 2026-11-25, surprise: 1}\n", "surprise"),
        ],
    )
    def test_a_wrong_line(self, tmp_path: Path, text: str, message: str) -> None:
        with pytest.raises(EntryFileError, match=message):
            self._with(tmp_path, text)

    def test_a_prefix_that_would_take_a_licence_is_refused(self, tmp_path: Path) -> None:
        long_licence = _term("long", f"['{DISCLAIMER} aber CC BY']", spdx="CC-BY-4.0")
        directory = _write(tmp_path, long_licence)
        (directory / "not_a_licence.yaml").write_text(
            f"- {{statement: '{DISCLAIMER}', kind: disclaimer, match: prefix, added_on: 2026-11-25}}\n", encoding="utf-8"
        )
        with pytest.raises(EntryFileError, match="means long"):
            load_licences(SOURCES, directory)
