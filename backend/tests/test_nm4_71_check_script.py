"""The check script of NM4-71 (`scripts/checks/nm4-71-normalize.ps1`), read for what Windows PowerShell 5.1 cannot take.

The script is for 5.1 on Otto's machine and needs the whole stack and the source on the net, so it is not run here;
the helpers are those of `nm4-11-normalize.ps1` and `nm4-19-statistics.ps1`; the latter runs in `test_nm4_19_check_script.py` against a local platform.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "checks" / "nm4-71-normalize.ps1"


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


def test_no_function_takes_the_name_of_a_cmdlet() -> None:
    """A function called ``Wait-Job`` would hide the cmdlet for the rest of the session."""
    names = re.findall(r"^function ([A-Za-z]+-[A-Za-z]+)", SCRIPT.read_text(encoding="ascii"), flags=re.MULTILINE)
    assert names and not set(names) & {"Wait-Job", "Get-Job", "Start-Job", "Write-Host", "Invoke-WebRequest", "Get-Content"}


def test_bodies_go_as_bytes_and_errors_are_caught() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "[System.Text.Encoding]::UTF8.GetBytes($Body)" in text
    assert "$_.Exception.Response" in text and "UseBasicParsing = $true" in text


def test_the_script_prints_no_item_id_no_job_id_and_no_hash() -> None:
    """Every ``Write-*`` line is a fixed text; the item is only ever printed through ``Get-Detail``, which masks it."""
    text = SCRIPT.read_text(encoding="ascii")
    assert "$script:ItemId" in text and ".Replace($script:ItemId, '<item>')" in text
    assert not re.search(r"Write-(Host|Info|Pass)[^\n]*\$\(?\$?(job|placed)\.jobID", text)


def test_the_jobs_send_version_4_without_numbers_and_the_gear_version_3_with_them() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "New-Step 4 $percentileV4" in text and "New-Step 4 $zscoreV4" in text and "New-Step 3 $fixed" in text
    assert '"measured"' not in text.split("$percentileV4 = ", 1)[1].split("\n", 1)[0]


def test_the_whole_scene_is_asked_for_without_an_aoi() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "New-Order $script:ItemId '' ''" in text and "if ($Aoi) {" in text
