"""The keywords of a listed entry: those of the source, normalized, or the words of its category (M5-40, Otto 15.11.2026).

``listed_keywords`` is pure; the harvest calls it with the tags and keywords of the source (M5-19), ``catalog-load`` with
those of a hand entry. Technical keywords are told by their form only (plan A11).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from earthx.catalog.categories import load_categories
from earthx.catalog.entry_files import EntryFileError
from earthx.catalog.listed import MAX_KEYWORD_CHARS, listed_keywords, load_catalog_tags, read_catalog_tags
from earthx.catalog.registry import ConfigError


def test_lower_case_one_space_each_once_in_the_order_of_the_source() -> None:
    assert listed_keywords(["Orthofoto", "  DOP 20 ", "orthofoto", "ORTHOFOTO", "dop\t20"], "optical") == (
        "orthofoto",
        "dop 20",
    )


def test_accents_and_other_letters_stay() -> None:
    assert listed_keywords(["Höhenmodell", "Gewässer", "Île-de-France"], "elevation") == (
        "höhenmodell",
        "gewässer",
        "île-de-france",
    )


@pytest.mark.parametrize(
    "technical",
    [
        "",
        "   ",
        "2024",
        "12.5",
        "---",
        "https://example.org/dataset/1",
        "http://inspire.ec.europa.eu/theme/hy",
        "www.example.org",
        "office@example.org",
        "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
        "3f2504e04f8911d39a0c0305e82c3301",
        "a" * (MAX_KEYWORD_CHARS + 1),
    ],
)
def test_a_technical_keyword_is_dropped(technical: str) -> None:
    assert listed_keywords([technical, "Hochwasser"], "water") == ("hochwasser",)


def test_a_keyword_with_letters_and_digits_stays() -> None:
    assert listed_keywords(["Sentinel-2", "DGM1", "x" * MAX_KEYWORD_CHARS], "optical") == (
        "sentinel-2",
        "dgm1",
        "x" * MAX_KEYWORD_CHARS,
    )


def test_what_is_no_text_is_dropped() -> None:
    assert listed_keywords([None, 3, ["x"], "Wald"], "agriculture") == ("wald",)


@pytest.mark.parametrize("category", load_categories().ids)
def test_without_keywords_of_the_source_every_category_gives_some(category: str) -> None:
    keywords = listed_keywords([], category)
    assert keywords and all(keyword and keyword == keyword.lower() and "and" != keyword for keyword in keywords)


def test_the_words_of_a_category_are_those_of_its_title() -> None:
    assert listed_keywords([], "water") == ("water", "sea")
    assert listed_keywords(["2024", "https://example.org"], "boundaries") == ("boundaries", "addresses", "cadastre")
    assert listed_keywords([], "other") == ("other",)


def test_an_unknown_category_is_an_error_only_where_its_words_are_needed() -> None:
    assert listed_keywords(["Wald"], "volcanoes") == ("wald",)
    with pytest.raises(ConfigError, match="volcanoes"):
        listed_keywords([], "volcanoes")


def test_a_string_is_not_read_as_a_list_of_letters() -> None:
    # One keyword given as a string is one keyword, never "w", "a", "l", "d".
    assert listed_keywords("Wald", "agriculture") == ("wald",)


# --- catalogue tags (catalog_tags.yaml, Otto 15.11.2026) --------------------------------------------------------------


def test_the_file_holds_the_three_tags_of_the_start() -> None:
    assert load_catalog_tags() == {"opendata", "govdata", "inspire"}


def test_a_catalogue_tag_is_dropped_as_a_whole_keyword_only() -> None:
    assert listed_keywords(["OpenData", "GovData", "INSPIRE", "inspireidentifiziert", "Wald"], "agriculture") == (
        "inspireidentifiziert",
        "wald",
    )


def test_only_catalogue_tags_give_the_words_of_the_category() -> None:
    assert listed_keywords(["opendata", "inspire"], "water") == ("water", "sea")


def test_the_tags_compare_after_the_same_normalization() -> None:
    assert listed_keywords(["Open  Data", "open data x"], "water", catalog_tags=frozenset({"open data"})) == (
        "open data x",
    )


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("opendata: yes\n", "are a list"),
        ("- opendata\n- OpenData\n", "stands twice"),
        ("- open  data\n- open data\n", "stands twice"),
        ("- ''\n", "non-blank"),
        ("- 3\n", "non-blank"),
    ],
)
def test_a_broken_tag_file_names_the_problem(tmp_path: Path, text: str, message: str) -> None:
    path = tmp_path / "catalog_tags.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(EntryFileError, match=message):
        read_catalog_tags(path)


@pytest.mark.parametrize("text", ["", "[]\n", "# nothing yet\n"])
def test_an_empty_tag_file_drops_nothing(tmp_path: Path, text: str) -> None:
    path = tmp_path / "catalog_tags.yaml"
    path.write_text(text, encoding="utf-8")
    assert read_catalog_tags(path) == frozenset()
