"""The search text of a dataset and the terms per capability (docs/plans/m5/m5-22-suche-lexikalisch.md §3.2, F5)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from earthx.catalog.registry import AccountKind, ConfigError, DataClass, DatasetCategory, LicenseTier
from earthx.catalog.search_text import (
    CATEGORY_NAMES,
    DATA_CLASS_WORDS,
    CapabilityTerms,
    load_capability_terms,
    search_text,
)
from earthx.processing.operators import REGISTRY as OPERATORS
from tests.catalog.entries import COP_DEM_GLO_30, ESA_WORLDCOVER_2020, REGISTRY, SENTINEL_2_L2A, SWISSALTI3D

NO_TERMS = CapabilityTerms(frozenset(), {})


def test_the_parts_carry_their_fields():
    text = search_text(SWISSALTI3D, terms=NO_TERMS)
    assert search_text(SENTINEL_2_L2A, terms=NO_TERMS).a.splitlines() == ["sentinel-2-c1-l2a", "Sentinel-2 L2A"]
    # Id and title differ only in case here, so the title is not given again.
    assert text.a.splitlines() == ["swissalti3d"]
    assert {"DTM", "Geländemodell", "Switzerland", "Schweiz", "Liechtenstein", "elevation"} <= set(text.b.splitlines())
    assert text.c == SWISSALTI3D.description
    assert {"dtm m", "static raster", "Federal Office of Topography swisstopo"} <= set(text.d.splitlines())


def test_keywords_are_on_b_not_on_a():
    # Plan A1: WorldCover names sentinel-2 among its keywords; on A it would tie with Sentinel-2 itself.
    text = search_text(ESA_WORLDCOVER_2020, terms=NO_TERMS)
    assert "sentinel-2" in text.b.splitlines()
    assert "sentinel-2" not in text.a


def test_a_line_is_given_once():
    # swissALTI3D names Switzerland as a keyword and gets it again from its extent.
    lines = search_text(SWISSALTI3D, terms=NO_TERMS).b.splitlines()
    assert lines.count("Switzerland") == 1 and "elevation" in lines and lines.count("elevation") == 1


def test_a_global_dataset_says_so_and_names_no_country():
    lines = search_text(COP_DEM_GLO_30, terms=NO_TERMS).b.splitlines()
    assert {"global", "worldwide", "weltweit"} <= set(lines)
    assert "Switzerland" not in lines


def test_quick_processings_and_true_color_only_where_the_entry_has_them():
    s2 = search_text(SENTINEL_2_L2A, terms=NO_TERMS).d
    assert "NDVI Normalized Difference Vegetation Index" in s2 and "true color" in s2
    dem = search_text(COP_DEM_GLO_30, terms=NO_TERMS).d
    assert "NDVI" not in dem and "true color" not in dem


def test_auxiliary_assets_and_dimensionless_units_stay_out():
    lines = search_text(SENTINEL_2_L2A, terms=NO_TERMS).d.splitlines()
    assert "red" in lines and "red 1" not in lines and "wvp cm" in lines
    assert "visual" not in lines and "preview" not in lines


@pytest.mark.parametrize(
    ("account", "words"),
    [(AccountKind.FREE_ACCOUNT, "free account required"), (AccountKind.REQUESTER_PAYS, "requester pays")],
)
def test_access_that_needs_something_is_named(valid_config, account, words):
    access = dataclasses.replace(
        valid_config.access, account=account, account_provider="Example account", token_free_checked_at=None
    )
    # An account source is a catalogue entry with a link and no viewer (adr/0027 §6.1, KLAERUNGEN B11).
    license = dataclasses.replace(valid_config.license, tier=LicenseTier.CATALOG)
    config = dataclasses.replace(valid_config, access=access, license=license, viewer=None)
    assert words in search_text(config, terms=NO_TERMS).d.splitlines()


def test_open_access_adds_no_words():
    assert "account" not in search_text(SWISSALTI3D, terms=NO_TERMS).d


def test_terms_of_a_capability_only_where_it_is_offered():
    terms = CapabilityTerms(frozenset(), {"quad_pol": ("Pauli decomposition", "Pauli-Zerlegung")})
    assert "Pauli decomposition" not in search_text(SENTINEL_2_L2A, terms=terms).d
    offering = dataclasses.replace(
        SENTINEL_2_L2A, capabilities=dataclasses.replace(SENTINEL_2_L2A.capabilities, quad_pol=True)
    )
    assert {"Pauli decomposition", "Pauli-Zerlegung"} <= set(search_text(offering, terms=terms).d.splitlines())


def test_no_general_operator_in_any_text():
    for config in REGISTRY:
        text = search_text(config)
        for word in ("band math", "reprojection", "normalization", "mask values", "value masking"):
            assert word not in text.d.lower(), (config.dataset_id, word)


def test_every_group_and_data_class_has_words():
    assert set(CATEGORY_NAMES) == set(DatasetCategory)
    assert set(DATA_CLASS_WORDS) == set(DataClass)


def test_the_hash_is_stable_and_follows_every_part():
    text = search_text(SWISSALTI3D, terms=NO_TERMS)
    assert text.text_hash == search_text(SWISSALTI3D, terms=NO_TERMS).text_hash
    hashes = {text.text_hash}
    for part in ("a", "b", "c", "d"):
        hashes.add(dataclasses.replace(text, **{part: getattr(text, part) + " x"}).text_hash)
    assert len(hashes) == 5


def test_the_hash_follows_the_version(monkeypatch):
    before = search_text(SWISSALTI3D, terms=NO_TERMS).text_hash
    monkeypatch.setattr("earthx.catalog.search_text.SEARCH_TEXT_VERSION", 2)
    assert search_text(SWISSALTI3D, terms=NO_TERMS).text_hash != before


def test_the_trigram_text_is_lower_case_without_accents_each_word_once():
    trigram = search_text(SWISSALTI3D, terms=NO_TERMS).trigram_text
    assert "gelandemodell" in trigram.split() and trigram == trigram.lower()
    assert trigram.split().count("swissalti3d") == 1


# --- terms per capability ----------------------------------------------------------------------------------------------


def test_every_capability_an_operator_needs_has_terms_or_is_general():
    # F5: catalog cannot read the operator registry, so this test holds the two together.
    terms = load_capability_terms()
    needed = {name for operator in OPERATORS.values() for name in operator.requires.capabilities}
    assert needed <= terms.general | set(terms.terms), sorted(needed - terms.general - set(terms.terms))


def _terms(tmp_path: Path, text: str) -> CapabilityTerms:
    path = tmp_path / "capability_terms.yaml"
    path.write_text(text, encoding="utf-8")
    return load_capability_terms(path)


def test_terms_load(tmp_path):
    terms = _terms(tmp_path, "general: [band_math]\nterms:\n  quad_pol: [Pauli, Pauli-Zerlegung]\n")
    assert terms.terms == {"quad_pol": ("Pauli", "Pauli-Zerlegung")}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("general: []\n", "exactly the keys"),
        ("general: [warp]\nterms: {}\n", "no capability"),
        ("general: []\nterms:\n  terrain: [slope]\n", "no capability"),
        ("general: [band_math, band_math]\nterms: {}\n", "named once"),
        ("general: [quad_pol]\nterms:\n  quad_pol: [Pauli]\n", "named once"),
        ("general: []\nterms:\n  quad_pol: []\n", "different, non-empty"),
        ("general: []\nterms:\n  quad_pol: [Pauli, pauli]\n", "different, non-empty"),
        ("general: []\nterms:\n  quad_pol: ['--']\n", "different, non-empty"),
        ("general: band_math\nterms: {}\n", "list of capability names"),
        ("general: []\nterms: [quad_pol]\n", "maps a capability"),
    ],
)
def test_malformed_terms_are_refused(tmp_path, text, message):
    with pytest.raises(ConfigError, match=message):
        _terms(tmp_path, text)
