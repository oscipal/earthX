"""The scripts of Otto's local report run (M5-20 plan §16; adr/0025 §8 step 5): checked as text, never run here."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
PS1 = SCRIPTS / "harvest-report.ps1"
SH = SCRIPTS / "harvest-report.sh"


@pytest.mark.parametrize("path", [PS1, SH])
def test_the_script_never_pushes(path: Path) -> None:
    # A push only as a hint to Otto, never as a command (adr/0025 §8: "Es pusht nie selbst").
    for line in path.read_text(encoding="utf-8").splitlines():
        if "git push" in line:
            assert re.match(r"\s*(echo|Write-Host|#)", line), line


@pytest.mark.parametrize("path", [PS1, SH])
def test_the_script_wants_a_clean_checkout_on_main(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "git status --porcelain" in text and "main" in text
    assert "harvest/" in text and "harvest-report" in text


@pytest.mark.parametrize("path", [PS1, SH])
def test_without_a_new_stack_the_branch_goes(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count("git branch -D") == 2


def test_the_powershell_script_is_ascii_for_windows_powershell_5() -> None:
    # Windows PowerShell 5.1 reads a file without BOM in the ANSI code page: no umlauts.
    assert PS1.read_bytes().isascii()


def test_the_bash_script_parses() -> None:
    subprocess.run(["bash", "-n", str(SH)], check=True)
