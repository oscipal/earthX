"""The check script of DS-02c (`scripts/checks/ds-02-filters.ps1`).

The script is for Windows PowerShell 5.1 on Otto's machine and asks the running platform, which asks the real source.
Neither exists here, so it is read for what 5.1 cannot take, as the script of NM4-19 is. It has not been run by this
test; what only a run shows is named in the PR.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "checks" / "ds-02-filters.ps1"


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
    assert "$_.Exception.Response" in text and "UseBasicParsing = $true" in text


def test_it_sends_only_the_box_of_one_degree_that_has_no_owner() -> None:
    """No one's AOI in a script that is public: the box of the measurement, and nothing else."""
    text = SCRIPT.read_text(encoding="ascii")
    assert "$Box                   = '[10, 47, 11, 48]'" in text
    assert not re.search(r"\b(?:Centre|Lon|Lat)\w*\s*=", text)


def test_it_names_no_secret_or_address_but_the_local_platform() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert re.findall(r"https?://[^\s'\"]+", text) == ["http://localhost:8000"]
