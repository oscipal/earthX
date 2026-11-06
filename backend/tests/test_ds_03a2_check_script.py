"""The check script of DS-03a2 (`scripts/checks/ds-03a2-aoi-clouds.ps1`, plan section 6.18).

The script is for Windows PowerShell 5.1 on Otto's machine and needs the real stack and the real source, so it
cannot run in a test. What can be checked here is what 5.1 cannot take, read off the text; the run itself is Otto's
(the PR says so).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "checks" / "ds-03a2-aoi-clouds.ps1"


def test_the_script_is_ascii_so_5_1_reads_it_the_same_without_a_bom() -> None:
    assert SCRIPT.read_bytes().isascii()


@pytest.mark.parametrize(
    "pattern",
    [
        r"-SkipHttpErrorCheck",
        r"-StatusCodeVariable",
        r"-ResponseHeadersVariable",
        r"-AsHashtable",
        r"ConvertFrom-Json\s+-Depth",
        r"Join-String",
        r"ForEach-Object\s+-Parallel",
        r"\?\?",
        r"\?\.",
        r"&&",
        r"\|\|",
        r"\$IsWindows",
        r"-Form\b",
    ],
)
def test_no_syntax_or_parameter_of_powershell_7(pattern: str) -> None:
    assert not re.search(pattern, SCRIPT.read_text(encoding="ascii"))


def test_bodies_go_as_bytes_and_errors_are_caught() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "[System.Text.Encoding]::UTF8.GetBytes($Body)" in text
    assert "$problem.Exception.Response" in text and "UseBasicParsing = $true" in text


def test_braces_and_brackets_balance_outside_strings_and_comments() -> None:
    """A missing brace would only show on Otto's machine; the count is a cheap guard."""
    text = SCRIPT.read_text(encoding="ascii")
    text = re.sub(r"<#.*?#>", "", text, flags=re.DOTALL)
    text = re.sub(r"'[^']*'", "''", text)
    text = re.sub(r'"[^"]*"', '""', text)
    text = re.sub(r"#.*", "", text)
    for opening, closing in ("{}", "()", "[]"):
        assert text.count(opening) == text.count(closing), f"{opening}{closing} do not balance"


def test_the_script_names_the_filter_and_prints_no_value_of_the_request() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "earthx:aoi_cloud_cover" in text and "aoi cloud filter" in text
    assert "Write-Host $body" not in text.lower() and "Write-Host $token" not in text.lower()


def test_a_refusal_is_read_from_error_details_first_because_5_1_has_consumed_the_stream() -> None:
    """Otto's run of 30.10.2026: six refusals were 400 but their text came back empty (the stream was read already)."""
    text = SCRIPT.read_text(encoding="ascii")
    assert "$problem.ErrorDetails.Message" in text
    assert text.index("$problem.ErrorDetails.Message") < text.index("GetResponseStream()")


def test_a_failed_refusal_prints_what_came_with_numbers_of_the_request_hidden() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "Body leer" in text and "<zahl>" in text and "Substring(0, 300)" in text


def test_the_refusals_name_the_filter_that_was_asked_not_always_the_cloud_share() -> None:
    """Otto, 31.10.2026: the texts of the route name the filter within the AOI; the script expects exactly those."""
    text = SCRIPT.read_text(encoding="ascii")
    for expected in (
        "earthx:aoi_cloud_cover needs a date range",
        "earthx:aoi_nodata needs a date range",
        "earthx:aoi_nodata needs an area",
        "goes with a filter measured in the AOI",
        "the coverage map cannot apply earthx:aoi_cloud_cover",
        "the coverage map cannot apply earthx:aoi_nodata",
    ):
        assert expected in text, expected
    assert "'cloud share'" not in text
