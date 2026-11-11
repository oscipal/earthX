"""The glossary of the dataset search and the split of a query (docs/plans/m5/m5-22-suche-lexikalisch.md §3.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from earthx.catalog.glossary import GLOSSARY_FILE, Glossary, Unit, load_glossary, normalize, parse_query
from earthx.catalog.registry import ConfigError

KNOWN = load_glossary(Path(GLOSSARY_FILE))


def _glossary(tmp_path: Path, text: str) -> Glossary:
    path = tmp_path / "glossary.yaml"
    path.write_text(text, encoding="utf-8")
    return load_glossary(path)


def _group_of(term: str) -> tuple[str, ...]:
    return KNOWN.groups[KNOWN.index[tuple(normalize(term).split())]]


@pytest.mark.parametrize(
    ("text", "normal"),
    [
        ("Höhenmodell", "hohenmodell"),
        ("Straße", "strasse"),
        ("Sentinel-2", "sentinel 2"),
        ("  bare/sparse  Vegetation ", "bare sparse vegetation"),
        ("Øresund", "oresund"),
        ("snake_case", "snake case"),
        ("🌍 !?", ""),
    ],
)
def test_normalize(text, normal):
    assert normalize(text) == normal


def test_surface_and_terrain_models_are_different_groups():
    # adr/0026 §4.2 and Q11, Q12: a DSM is no DTM.
    assert "DSM" not in _group_of("DTM")
    assert "DTM" not in _group_of("DSM")
    assert "DEM" not in _group_of("DTM") and "DEM" not in _group_of("DSM")
    assert "Geländemodell" in _group_of("digital terrain model")
    assert "Oberflächenmodell" in _group_of("digital surface model")


@pytest.mark.parametrize(
    ("term", "partner"),
    [
        ("Bodenreflexion", "surface reflectance"),
        ("Echtfarben", "true color"),
        ("Vegetationsindex", "vegetation index"),
        ("Schneebedeckung", "snow cover"),
        ("Wasserflächen", "water bodies"),
        ("Radarbild", "radar image"),
        ("Rückstreuung", "backscatter"),
        ("Landbedeckung", "land cover"),
        ("Höhenmodell", "elevation model"),
    ],
)
def test_terms_the_plan_names_share_a_group(term, partner):
    assert partner in _group_of(term)


@pytest.mark.parametrize(
    ("query", "units"),
    [
        # Longest match first: "digitales Oberflächenmodell" is one term, not "digitales" and a second unit.
        ("digitales Oberflächenmodell", [_group_of("DSM")]),
        ("Sentinel 2", [_group_of("S2")]),
        ("SENTINEL-2", [_group_of("S2")]),
        ("sentinel-2-c1-l2a", [_group_of("S2"), ("c1-l2a",)]),
        ("Höhenmodell Österreich", [_group_of("DEM"), ("osterreich",)]),
        ("Radarbilder bei Bewölkung", [_group_of("radar image"), ("bei",), ("bewolkung",)]),
        # The same group twice is one condition.
        ("digital terrain model bare earth", [_group_of("DTM")]),
        ("land cover, 2021", [_group_of("land cover"), ("2021",)]),
        ("'; DROP TABLE x; --", [("drop",), ("table",), ("x",)]),
        ("\\ ' ;", []),
        ("🌍🌍", []),
        ("", []),
    ],
)
def test_parse_query(query, units):
    assert [unit.terms for unit in parse_query(query, KNOWN)] == units


def test_a_glossary_unit_is_marked_and_a_word_is_not():
    assert parse_query("NDVI DEM", KNOWN) == (Unit(("ndvi",), False), Unit(_group_of("DEM"), True))


def test_words_of_different_chunks_stay_apart():
    assert [unit.terms for unit in parse_query("water-index quality", KNOWN)] == [("water-index",), ("quality",)]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("groups: []\n", "'groups' is a non-empty list"),
        ("other: []\n", "exactly the key 'groups'"),
        ("groups:\n- [alone]\n", "at least two terms"),
        ("groups:\n- not a list\n", "at least two terms"),
        ("groups:\n- [a, '']\n", "is no term"),
        ("groups:\n- [a, '--']\n", "is no term"),
        ("groups:\n- [a, 3]\n", "is no term"),
        ("groups:\n- [Höhe, hohe]\n", "given twice"),
        ("groups:\n- [DSM, surface model]\n- [DTM, dsm]\n", "in group 1 as well"),
        ("groups:\n- [Sentinel-2, s2]\n- [sentinel 2, x]\n", "in group 1 as well"),
        ("groups:\n  - [a, b\n", "not valid YAML"),
    ],
)
def test_a_malformed_glossary_is_refused(tmp_path, text, message):
    with pytest.raises(ConfigError, match=message):
        _glossary(tmp_path, text)


def test_a_missing_glossary_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="cannot be read"):
        load_glossary(tmp_path / "glossary.yaml")
