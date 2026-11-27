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
            assert path in {
                "backend/catalog/licenses", "backend/catalog/approvals", "backend/catalog/candidates", "docs/harvest"
            }, path
    assert ".github" not in CODE and "CLAUDE.md" not in CODE


def test_every_service_it_runs_exists_under_the_profile_harvest() -> None:
    services = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
    named = set(re.findall(r"'(harvest(?:-[a-z]+)?)'", CODE))
    assert named == {"harvest", "harvest-report", "harvest-grants", "harvest-linkcheck", "harvest-propose",
                     "harvest-spellings", "harvest-cycle"}
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
    assert "skipping" not in state.split("#")[0] and "elseif ($check.bucket -ne 'pass') { $script:RedChecks += $name }" in state
    assert "if ($script:RedChecks.Count) { return 'fail' }" in state
    assert "$view[0] -notmatch '^[0-9]+$'" in CODE


def test_a_failed_link_check_does_not_stop_the_run_and_the_summary_runs_once() -> None:
    link = CODE[CODE.index("$Step = 'Linkpruefung'") : CODE.index("$Step = 'Freigabe'")]
    assert "throw" not in link and "linkpruefung-fehler.txt" in link
    assert "if ($Summary -and -not $SummaryDone)" in CODE


def test_the_candidates_run_after_the_link_check_for_the_harvested_sources_and_never_stop_the_run() -> None:
    # M5-20 plan §14.1.6: a step of its own, its files in a commit of their own and in the draft PR of a failed run.
    step = CODE[CODE.index("$Step = 'Kandidaten'") : CODE.index("$Step = 'Freigabe'")]
    assert CODE.index("$Step = 'Linkpruefung'") < CODE.index("$Step = 'Kandidaten'")
    assert "throw" not in step and "kandidaten-fehler.txt" in step
    assert "'harvest-propose', '--json', '/run/propose.json'" in step and "$propose + $Harvested" in step
    assert "if ($Trial) { $propose += '--trial' }" in step and "$Harvested.Count -and" in step
    assert 'Commit "Add candidates for full entries, harvest run $day" @(\'backend/catalog/candidates\')' in CODE
    catch = CODE[CODE.index("} catch {\n    $ExitCode = 1") :]
    assert "'backend/catalog/candidates'" in catch
    services = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
    assert "./backend/catalog/candidates:/app/catalog/candidates" in services["harvest-propose"]["volumes"]
    assert (REPO / "backend" / "catalog" / "candidates").is_dir()


def test_the_lock_is_taken_atomically() -> None:
    assert "[System.IO.FileMode]::CreateNew" in CODE and "Get-Process -Id" in CODE


# --- M5-67 fix 1 (24.11.2026): the first trial run of Otto ---------------------------------------------------------------


def _between(start: str, end: str) -> str:
    return CODE[CODE.index(start) : CODE.index(end)]


def test_only_exit_codes_decide_and_standard_error_is_never_an_error() -> None:
    # Windows PowerShell 5.1 shows standard error of a native command as System.Management.Automation.RemoteException.
    assert "$?" not in CODE and "$Error[" not in CODE and "$error[" not in CODE
    assert CODE.count("2>&1") == 1 and "2>&1" in _between("function Native", "function Lines")
    assert "function Text-Of" in CODE
    text_of = _between("function Text-Of", "function Native")
    assert "System.Management.Automation.RemoteException" in text_of and "return ''" in text_of
    # Both functions that run a command take its text through Text-Of and its success from the exit code alone.
    for name, following in (("function Native", "function Lines"), ("function Lines", "function Reason")):
        body = _between(name, following)
        assert "Text-Of $_" in body and "$LASTEXITCODE" in body and "= 'Continue'" in body, name
    # No decision on what a command printed: the output is matched only by Reason, to name a line in a message.
    for line in CODE.splitlines():
        if "-match" in line and "$script:LastOutput" not in line:
            assert "$out" not in line and "$Sources" not in line, line


def test_a_harvest_that_paused_on_purpose_is_a_success_with_a_note() -> None:
    from earthx.discovery.harvest import EXIT_PAUSED

    assert f"$PauseCode = {EXIT_PAUSED}\n" in CODE
    loop = _between("foreach ($source in $Sources)", "$Step = 'Lizenzen'")
    assert "$code = Compose" in loop and "-eq $PauseCode" in loop
    # The pause is harvested like a done run (its report goes on), noted for the summary, and never written as an error.
    paused = loop[loop.index("-eq $PauseCode") : loop.index("} else {")]
    assert "$Harvested += $source" in paused and "quellen-pause.txt" in paused and "quellen-fehler.txt" not in paused
    failed = loop[loop.index("} else {") :]
    assert "quellen-fehler.txt" in failed and "$Harvested" not in failed


def test_every_failing_step_names_the_line_that_says_why() -> None:
    assert "function Reason" in CODE and "$script:LastOutput = $out" in CODE
    for line in CODE.splitlines():
        if "throw" in line and ("Compose " in line or "Native " in line) and "-ne 0" in line:
            assert "$(Reason)" in line, line
    for message in ("Lizenzen: Schreibweisen gescheitert.", "Bericht: Der Bericht von $source ist gescheitert.",
                    "Freigabe: Die Freigabe nach Regeln ist gescheitert.", "Git: Push gescheitert",
                    "PR: gh pr create gescheitert", "Merge: abgelehnt"):
        assert message in CODE and "$(Reason)" in CODE[CODE.index(message) :].split("\n", 1)[0], message
    # The window gets the whole message of the step, and fehler.log and the pull request get the same from lauf-fehler.txt.
    catch = CODE[CODE.index("} catch {\n    $ExitCode = 1") :]
    assert '$Message = "FEHLER in $text Details: $RunDir"' in catch
    assert "WriteAllText((Join-Path $RunDir 'lauf-fehler.txt'), $text" in catch
    # An error without a message of its own says where it happened, not only the type of standard error.
    assert "unerwarteter Fehler in Zeile" in catch


def test_every_run_takes_a_branch_named_by_its_time_and_closes_the_old_failed_drafts() -> None:
    branch = _between("$Step = 'Branch'", "$Trial = ")
    # Otto, 25.11.2026: always harvest/<day>-<HHmm>, also where harvest/<day> is free.
    assert '$Branch = "harvest/$day-" + (Get-Date -Format \'HHmm\')' in branch
    assert 'harvest/$day"' not in branch and '$Label = "$day " + (Get-Date -Format \'HH:mm\')' in branch
    assert 'while (Branch-Taken $Branch)' in branch  # even a second run in the same minute
    taken = _between("function Branch-Taken", "if ($Install)")
    assert "'rev-parse', '--verify', '--quiet', $Name" in taken and "'ls-remote', '--exit-code', '--heads', 'origin', $Name" in taken
    assert '"Harvest run $Label (failed)"' in CODE and '"Harvest run $Label"' in CODE
    # The old failed drafts: only drafts, only runs of this script (title and branch), a comment, the branch goes.
    closing = _between("function Close-EarlierRuns", "function Branch-Taken")
    assert "'--state', 'open'" in closing and "'--author', '@me'" in closing
    assert "'^harvest/[0-9]{4}-[0-9]{2}-[0-9]{2}(-[0-9]+)*$'" in closing and "'^Harvest run '" in closing
    assert "$pr.isDraft -and $pr.title -match '\\(failed\\)$'" in closing
    assert "'gh', 'pr', 'close'" in closing and "'--comment'" in closing and "'--delete-branch'" in closing
    assert "throw" not in closing  # a pull request that cannot be closed never stops the run
    # It happens after the checks and before the new branch, and it is the only place that closes or deletes anything.
    assert CODE.index("$Closed = Close-EarlierRuns") < CODE.index("$Step = 'Branch'")
    assert CODE.count("'pr', 'close'") == 1 and CODE.count("'branch', '-D'") == 2  # 2: here, and the empty run's own branch


def test_the_branch_names_the_script_makes_are_the_ones_it_closes() -> None:
    # harvest/<day>, harvest/<day>-<HHmm>, harvest/<day>-<HHmm>-<n> and the older harvest/<day>-<n>, nothing else.
    pattern = re.compile(r"^harvest/[0-9]{4}-[0-9]{2}-[0-9]{2}(-[0-9]+)*$")
    for name in ("harvest/2026-11-24", "harvest/2026-11-24-1432", "harvest/2026-11-24-1432-2", "harvest/2026-11-24-2"):
        assert pattern.match(name), name
    for name in ("harvest/", "harvest/main", "harvest/2026-11-24-fix", "feature/2026-11-24", "harvest/2026-11-24/x",
                 "xharvest/2026-11-24", "harvest/2026-11-24\nmain"):
        assert not pattern.match(name), name


# --- M5-67 fix 4 (27.11.2026): the second run of 25.11. ------------------------------------------------------------------


def test_a_source_whose_harvest_failed_says_so_when_its_report_is_left_out() -> None:
    # The run of 25.11. 15:43: the harvest of govdata stopped (robots), the window showed no "Bericht govdata" line, and
    # nothing said why. Plan §3 step 5: no harvest, no report in this run; the window says it, with the reason, twice.
    harvest = _between("foreach ($source in $Sources)", "$Step = 'Lizenzen'")
    assert 'Say "Ernte $source gescheitert: $failure"' in harvest and "$(Reason)" in harvest
    reports = _between("$Step = 'Bericht'", "$Step = 'Linkpruefung'")
    assert "foreach ($source in $Sources)" in reports and "$Harvested -notcontains $source" in reports
    skipped = reports[reports.index("-notcontains") : reports.index('Say "Bericht $source ..."')]
    assert 'Say "Bericht $source uebersprungen: Ernte gescheitert' in skipped and "continue" in skipped
    assert "throw" not in skipped  # a failed source never stops the others


def test_a_pull_request_with_a_red_required_check_is_closed_by_the_next_run_with_its_reason() -> None:
    closing = _between("function Close-EarlierRuns", "function Branch-Taken")
    # Only red: one that waits for its checks, or is green and not merged, stays and is a finding.
    assert "(Get-CheckState \"$($pr.number)\") -eq 'fail'" in closing
    assert "if (-not $why) { continue }" in closing and "$script:RedChecks" in closing
    # Never someone else's pull request, a fork's, or one that is not a run of this script.
    assert "'--author', '@me'" in closing and "if ($pr.isCrossRepository) { continue }" in closing
    assert "-notmatch '^Harvest run '" in closing
    # The comment says why, and the line in the window says which were closed.
    assert '$why = "Pflicht-Check rot: $red."' in closing and "$why Ein neuer Lauf" in closing
    assert "PRs frueherer Laeufe geschlossen" in CODE and "Native \"close PR" in closing
    assert "'--delete-branch'" in closing


def test_the_state_of_the_checks_comes_from_the_list_and_not_from_the_exit_code_of_gh() -> None:
    # `gh pr checks` ends with 1 on a red check and 8 on a pending one and prints its list all the same; read only on 0,
    # a red check looked pending and the run waited the 90 minutes (plan §22a.6).
    state = _between("function Get-CheckState", "function Commit")
    assert "'--json', 'name,bucket') @(0, 1, 8)" in state
    assert "if ($null -eq $json -or -not $json.Count) { return 'pending' }" in state
    assert "[int[]]$Accept = @(0)" in _between("function Lines", "function Reason")
    assert "if ($Accept -notcontains $code) { return $null }" in _between("function Lines", "function Reason")
    # Every other call keeps the exit code 0 as the only success.
    assert len(re.findall(r"\) @\(0, 1, 8\)", CODE)) == 1
