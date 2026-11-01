"""The check script of NM4-71 (`scripts/checks/nm4-71-normalize.ps1`), read for what Windows PowerShell 5.1 cannot take.

The script is for 5.1 on Otto's machine and needs the whole stack and the source on the net, so it is not run here;
the helpers are those of `nm4-11-normalize.ps1` and `nm4-19-statistics.ps1`; the latter runs in `test_nm4_19_check_script.py` against a local platform.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "checks" / "nm4-71-normalize.ps1"


BOM = b"\xef\xbb\xbf"


def _text() -> str:
    """The script without its byte order mark."""
    return SCRIPT.read_bytes().removeprefix(BOM).decode("ascii")


def test_the_script_is_utf_8_with_a_bom_and_ascii_after_it() -> None:
    """Windows PowerShell 5.1 reads a file without a BOM in the ANSI code page; with it, as UTF-8 (Otto, zu #273)."""
    raw = SCRIPT.read_bytes()
    assert raw.startswith(BOM) and raw[len(BOM) :].isascii()


def test_no_variable_is_followed_by_a_colon_in_a_string() -> None:
    """``"$Text: ..."`` is a drive-qualified reference to 5.1 and fails to parse; ``"${Text}: ..."`` is meant (Otto, zu #273).

    The scope modifiers (``$script:``, ``$env:`` ...) are the only names a colon may follow.
    """
    found = [
        match.group(0)
        for match in re.finditer(r"\$([A-Za-z_][A-Za-z0-9_]*):", _text())
        if match.group(1).lower() not in {"script", "global", "local", "private", "env", "using"}
    ]
    assert found == []


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
    assert not re.search(pattern, _text())


def test_no_function_takes_the_name_of_a_cmdlet() -> None:
    """A function called ``Wait-Job`` would hide the cmdlet for the rest of the session."""
    names = re.findall(r"^function ([A-Za-z]+-[A-Za-z]+)", _text(), flags=re.MULTILINE)
    assert names and not set(names) & {
        "Wait-Job",
        "Get-Job",
        "Start-Job",
        "Write-Host",
        "Invoke-WebRequest",
        "Get-Content",
    }


def test_bodies_go_as_bytes_and_errors_are_caught() -> None:
    text = _text()
    assert "[System.Text.Encoding]::UTF8.GetBytes($Body)" in text
    assert "$_.Exception.Response" in text and "UseBasicParsing = $true" in text


def test_the_script_prints_no_item_id_no_job_id_and_no_hash() -> None:
    """Every ``Write-*`` line is a fixed text; the item is only ever printed through ``Get-Detail``, which masks it."""
    text = _text()
    assert "$script:ItemId" in text and ".Replace($script:ItemId, '<item>')" in text
    assert not re.search(r"Write-(Host|Info|Pass)[^\n]*\$\(?\$?(job|placed)\.jobID", text)


def test_the_jobs_send_version_4_without_numbers_and_the_gear_version_3_with_them() -> None:
    text = _text()
    assert "New-Step 4 $percentileV4" in text and "New-Step 4 $zscoreV4" in text and "New-Step 3 $fixed" in text
    assert '"measured"' not in text.split("$percentileV4 = ", 1)[1].split("\n", 1)[0]


def test_the_whole_scene_is_asked_for_without_an_aoi() -> None:
    text = _text()
    assert "New-Order $script:ItemId '' ''" in text and "if ($Aoi) {" in text

