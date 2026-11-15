"""The categories of the Data catalogue and the rule that gives an entry one (M5-40 plan §4b; G1-G6).

The real ``categories.yaml`` against the vocabularies and the decisions of the plan; broken copies of it against the
checks of the reader; :func:`category_of` against each step of the rule, on the real file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from earthx.catalog.categories import (
    CATEGORIES_FILE,
    EU_DATA_THEMES,
    INSPIRE_THEMES,
    OTHER,
    Evidence,
    category_of,
    load_categories,
    read_categories,
)
from earthx.catalog.entry_files import EntryFileError

CATEGORIES = load_categories()


def test_the_list_is_the_one_of_the_plan_in_its_order() -> None:
    # G1 = 1: the five categories of before, seven new ones, other last.
    assert CATEGORIES.ids == (
        "optical",
        "radar",
        "elevation",
        "land_cover",
        "weather_climate",
        "water",
        "nature",
        "geology_soil",
        "boundaries",
        "infrastructure",
        "population",
        "agriculture",
        "other",
    )


def test_every_inspire_theme_and_every_eu_data_theme_has_a_category() -> None:
    assert len(INSPIRE_THEMES) == 34 and len(EU_DATA_THEMES) == 14
    assert set(CATEGORIES.inspire) == INSPIRE_THEMES
    assert set(CATEGORIES.eu_data_themes) == EU_DATA_THEMES


@pytest.mark.parametrize(
    ("code", "category"),
    [
        ("oi", "optical"),
        ("el", "elevation"),
        ("lu", "land_cover"),
        ("hy", "water"),
        ("am", "nature"),
        ("mr", "geology_soil"),
        ("cp", "boundaries"),
        ("er", "infrastructure"),
        ("hh", "population"),
        ("af", "agriculture"),
        ("rs", OTHER),
    ],
)
def test_the_inspire_table_of_the_plan(code: str, category: str) -> None:
    assert CATEGORIES.inspire[code] == category


def test_the_coarse_eu_data_themes() -> None:
    assert CATEGORIES.coarse_eu_data_themes == {"ENVI", "AGRI", "SOCI"}


# --- the rule ---------------------------------------------------------------------------------------------------------


def test_an_inspire_theme_decides_first_as_a_uri_or_a_code() -> None:
    evidence = Evidence(
        inspire_themes=("http://inspire.ec.europa.eu/theme/hy/",),
        eu_data_themes=("TRAN",),
        keywords=("Orthofoto",),
    )
    assert category_of(evidence) == "water"
    assert category_of(Evidence(inspire_themes=("el",))) == "elevation"


def test_several_values_of_one_kind_give_the_highest_category_of_the_list() -> None:
    assert category_of(Evidence(inspire_themes=("hy", "el"))) == "elevation"


def test_an_inspire_theme_of_other_gives_way_to_the_next_kind() -> None:
    assert category_of(Evidence(inspire_themes=("rs",), eu_data_themes=("TRAN",))) == "infrastructure"


def test_a_precise_eu_data_theme_comes_before_terms() -> None:
    evidence = Evidence(
        eu_data_themes=("http://publications.europa.eu/resource/authority/data-theme/TRAN",), keywords=("Hochwasser",)
    )
    assert category_of(evidence) == "infrastructure"


def test_a_coarse_eu_data_theme_gives_way_to_a_term() -> None:
    assert category_of(Evidence(eu_data_themes=("ENVI",), keywords=("Hochwasser",))) == "water"
    assert category_of(Evidence(eu_data_themes=("ENVI",))) == "nature"


def test_a_group_comes_before_a_keyword() -> None:
    assert category_of(Evidence(groups=("Verkehr",), keywords=("Höhenmodell",))) == "infrastructure"


def test_a_term_counts_as_whole_words_only() -> None:
    # "SAR" is a term of radar; "Saarland" is no match for it.
    assert category_of(Evidence(keywords=("Saarland",))) == OTHER
    assert category_of(Evidence(keywords=("SAR data",))) == "radar"
    assert category_of(Evidence(keywords=("Digitales Geländemodell 1 m",))) == "elevation"


def test_case_and_accents_do_not_matter() -> None:
    assert category_of(Evidence(keywords=("GEBAUDE",))) == "infrastructure"


def test_nothing_that_matches_is_other() -> None:
    assert category_of(Evidence()) == OTHER
    assert category_of(Evidence(inspire_themes=("zz",), eu_data_themes=("NOPE",), keywords=("Haushalt",))) == OTHER


# --- broken files -----------------------------------------------------------------------------------------------------


def _write(tmp_path: Path, change) -> Path:
    data = yaml.safe_load(CATEGORIES_FILE.read_text(encoding="utf-8"))
    change(data)
    path = tmp_path / "categories.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def _swap_last(data: dict) -> None:
    data["categories"][-1], data["categories"][0] = data["categories"][0], data["categories"][-1]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.pop("terms"), "holds exactly"),
        (lambda d: d.update(extra=1), "holds exactly"),
        (lambda d: d["categories"].append(dict(d["categories"][0])), "stands twice"),
        (lambda d: d["categories"][0].update(id="Optical"), "lower-case"),
        (lambda d: d["categories"][0].update(title=" "), "title"),
        (lambda d: d["categories"][0].update(colour="red"), "holds exactly"),
        (_swap_last, "other is the last"),
        (lambda d: d["inspire"]["water"].append("el"), "el stands twice"),
        (lambda d: d["inspire"]["water"].append("xx"), "no code of the vocabulary"),
        (lambda d: d["inspire"].update(volcanoes=["gg"]), "no category of the list"),
        (lambda d: d["eu_data_themes"]["other"].append("FOOD"), "no code of the vocabulary"),
        (lambda d: d["coarse_eu_data_themes"].append("XXXX"), "codes of eu_data_themes"),
        (lambda d: d["terms"]["water"].append("Höhenmodell"), "stands twice"),
        (
            lambda d: d["terms"]["water"].append("HOEHENMODELL") or d["terms"]["water"].append("hoehenmodell"),
            "stands twice",
        ),
        (lambda d: d["terms"]["water"].append("--"), "no term"),
        (lambda d: d["terms"].update(other=["Haushalt"]), "other than other"),
        (lambda d: d["terms"].update(water=[]), "at least one term"),
    ],
)
def test_a_broken_file_names_the_place(tmp_path: Path, change, message: str) -> None:
    with pytest.raises(EntryFileError, match=message):
        read_categories(_write(tmp_path, change))


def test_the_real_file_reads_like_its_copy(tmp_path: Path) -> None:
    assert read_categories(_write(tmp_path, lambda d: None)) == CATEGORIES
