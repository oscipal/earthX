"""The keywords of a listed entry: those of the source, normalized, or the words of its category (M5-40, Otto 15.11.2026).

``listed_keywords`` is pure; the harvest calls it with the tags and keywords of the source (M5-19), ``catalog-load`` with
those of a hand entry. Technical keywords are told by their form only (plan A11).
"""

from __future__ import annotations

import pytest

from earthx.catalog.categories import load_categories
from earthx.catalog.listed import MAX_KEYWORD_CHARS, listed_keywords
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
