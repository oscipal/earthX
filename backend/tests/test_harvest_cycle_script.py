"""The script of a harvest run by double click (M5-67 plan §3, §10, §11): checked as text, never run here.

The session has no PowerShell; the script runs only on Otto's computer, against the real sources (adr/0002). What a
text can show is checked: that it merges only after the required checks and only with a merge commit, never forces,
writes outside the repository except through its commits, and hands every decision to the container.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "harvest-cycle.ps1"
TEXT = SCRIPT.read_text(encoding="utf-8")
CODE = "\n".join(line for line in TEXT.splitlines() if not line.lstrip().startswith("#"))


def test_it_is_ascii_for_windows_powershell_5() -> None:
    # Windows PowerShell 5.1 reads a file without BOM in the ANSI code page: no umlauts, no dash.
    assert SCRIPT.read_bytes().isascii()


def test_it_waits_for_the_four_required_checks_by_their_names_in_ci() -> None:
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    names = {"Backend — lint and tests", "Frontend — lint, types and tests",
             "Module boundaries (import-linter)", "Compose topology"}
    for name in names:
        assert f"name: {name}" in ci, name
    built = {n.replace("—", "$Dash") for n in names}
    for name in built:
        assert name in TEXT, name
    assert "$Dash = [char]0x2014" in TEXT


def test_it_merges_only_with_a_merge_commit_after_green_checks_and_never_forces() -> None:
    assert "'gh', 'pr', 'merge', $Pr, '--merge', '--delete-branch'" in CODE
    for forbidden in ("--admin", "--squash", "--rebase", "--force", "push -f", "reset --hard", "--auto"):
        assert forbidden not in CODE, forbidden
    merge = CODE.index("'pr', 'merge'")
    assert CODE.index("Get-CheckState $Pr") < merge
    assert "if ($state -ne 'pass') { throw" in CODE


def test_a_failure_merges_nothing_and_leaves_a_draft_pr_with_the_error() -> None:
    catch = CODE[CODE.index("} catch {\n    $ExitCode = 1") :]
    assert "'merge'" not in catch and "'--draft'" in catch
    assert "lauf-fehler.txt" in catch


def test_it_wants_a_clean_checkout_on_main_and_pulls() -> None:
    assert "@('git', 'status', '--porcelain')" in CODE
    assert "@('git', 'switch', 'main')" in CODE and "@('git', 'pull', '--ff-only')" in CODE


def test_it_writes_into_the_repository_only_through_its_commits() -> None:
    # Files are written only into the run's folder outside the repository (and the lock beside it).
    for call in re.findall(r"\[System\.IO\.File\]::(?:Write|Append)All(?:Text|Lines)\(([^,]+),", CODE):
        assert call.strip().startswith(("$script:Log", "(Join-Path $RunDir", "$Capture")), call
    assert "Set-Content" not in CODE and "Out-File" not in CODE
    assert "$OutRoot = Join-Path (Split-Path -Parent $Repo) 'earthx-ausgaben'" in CODE
    # It commits only the files of the run.
    for paths in re.findall(r"Commit \"[^\"]+\" @\(([^)]*)\)", CODE):
        for path in re.findall(r"'([^']+)'", paths):
            assert path in {"backend/catalog/licenses", "backend/catalog/approvals", "docs/harvest"}, path
    assert ".github" not in CODE and "CLAUDE.md" not in CODE


def test_every_service_it_runs_exists_under_the_profile_harvest() -> None:
    services = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
    named = set(re.findall(r"'(harvest(?:-[a-z]+)?)'", CODE))
    assert named == {"harvest", "harvest-report", "harvest-grants", "harvest-linkcheck", "harvest-spellings",
                     "harvest-cycle"}
    for name in named:
        assert services[name]["profiles"] == ["harvest"], name


def test_the_first_run_is_a_trial() -> None:
    # F7 = 1: no run folder yet, so nothing hidden and nothing approved.
    assert "$Trial = -not (Get-ChildItem (Join-Path $Repo 'docs\\harvest\\laeufe') -Directory" in CODE
    assert "if ($Trial) { $check += '--dry-run' }" in CODE
    assert "if ($Trial) { $decide += '--trial' }" in CODE and "if ($Trial) { $Summary += '--trial' }" in CODE


def test_install_makes_the_desktop_shortcut() -> None:
    assert "'EarthX Harvest.lnk'" in CODE and "-ExecutionPolicy Bypass -File" in CODE
    assert "gh auth login" in CODE and "'.env'" in CODE


def test_every_error_names_its_step() -> None:
    for message in re.findall(r'throw ["\']([^"\']+)', CODE):
        assert re.match(r"[A-Z][A-Za-z]+: ", message), message


def test_no_second_run_at_the_same_time_and_the_lock_goes() -> None:
    assert "lauf.lock" in CODE and "Remove-Item $Lock" in CODE[CODE.index("} finally {") :]


def test_lines_never_unrolls_its_array() -> None:
    # Review, 24.11.2026: an empty result became $null (every clean checkout failed), one PR number "412" became "4".
    lines = CODE[CODE.index("function Lines") : CODE.index("function Compose")]
    assert "return ,$out" in lines and "2>$null" in lines


def test_the_steps_in_the_container_read_and_write_the_mounted_approvals() -> None:
    # Review, 24.11.2026: without it they read the image's copy, made before the report.
    assert "'decide', '--run', '/run', '--approvals', '/approvals'" in CODE
    assert "'summary', '--run', '/run', '--harvest', '/harvest', '--approvals', '/approvals'" in CODE


def test_only_a_pass_counts_and_the_pr_number_is_checked() -> None:
    state = CODE[CODE.index("function Get-CheckState") : CODE.index("function Commit")]
    assert "skipping" not in state.split("#")[0] and "elseif ($check.bucket -ne 'pass') { return 'fail' }" in state
    assert "$view[0] -notmatch '^[0-9]+$'" in CODE


def test_a_failed_link_check_does_not_stop_the_run_and_the_summary_runs_once() -> None:
    link = CODE[CODE.index("$Step = 'Linkpruefung'") : CODE.index("$Step = 'Freigabe'")]
    assert "throw" not in link and "linkpruefung-fehler.txt" in link
    assert "if ($Summary -and -not $SummaryDone)" in CODE


def test_the_lock_is_taken_atomically() -> None:
    assert "[System.IO.FileMode]::CreateNew" in CODE and "Get-Process -Id" in CODE
