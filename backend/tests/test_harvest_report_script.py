"""The scripts of Otto's local report run (M5-20 plan §16; adr/0025 §8 step 5): checked as text, never run here."""

from __future__ import annotations

import os
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


FAKE_DOCKER = """#!/usr/bin/env bash
# Records its call; as the report, writes an approval file unless FAKE_STACK is empty.
echo "$*" >> "$FAKE_LOG"
[[ " $* " == *" --user $(id -u):$(id -g) "* ]] || { echo "not run as the owner of the checkout" >&2; exit 3; }
if [[ -n "${FAKE_STACK:-}" && " $* " != *" --classify "* ]]; then
    printf 'decision: pending\\n' > backend/catalog/approvals/2026-11-19-govdata.yaml
fi
"""


def _repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    repo = tmp_path / "repo"
    (repo / "backend" / "catalog" / "approvals").mkdir(parents=True)
    (repo / "backend" / "catalog" / "approvals" / "README.md").write_text("x\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "docker"
    fake.write_text(FAKE_DOCKER, encoding="utf-8")
    fake.chmod(0o755)
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "FAKE_LOG": str(tmp_path / "docker.log"),
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.org",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.org",
        "HOME": str(tmp_path),
    }
    for command in (["git", "init", "-q", "-b", "main"], ["git", "add", "-A"], ["git", "commit", "-q", "-m", "init"]):
        subprocess.run(command, cwd=repo, env=env, check=True)
    return repo, env


def _run(repo: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SH), *args], cwd=repo, env=env, capture_output=True, text=True)


def test_on_linux_the_report_writes_as_the_owner_of_the_checkout_and_the_file_is_committed(tmp_path: Path) -> None:
    # Otto, 19.11.2026: the approval must not hang on the rights of a folder; the image itself runs as root.
    repo, env = _repo(tmp_path)
    done = _run(repo, {**env, "FAKE_STACK": "1"}, "govdata")
    assert done.returncode == 0, done.stdout + done.stderr
    written = repo / "backend" / "catalog" / "approvals" / "2026-11-19-govdata.yaml"
    assert written.stat().st_uid == os.getuid()
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=repo, capture_output=True, text=True).stdout
    assert branch.strip().startswith("harvest/") and branch.strip().endswith("-govdata")
    log = subprocess.run(["git", "log", "--oneline", "-1", "--name-only"], cwd=repo, capture_output=True, text=True)
    assert "backend/catalog/approvals/2026-11-19-govdata.yaml" in log.stdout
    assert f"--user {os.getuid()}:{os.getgid()}" in (tmp_path / "docker.log").read_text(encoding="utf-8")


def test_without_a_new_stack_it_goes_back_to_main(tmp_path: Path) -> None:
    repo, env = _repo(tmp_path)
    done = _run(repo, env, "govdata")
    assert done.returncode == 0 and "kein neuer Stapel" in done.stdout
    branches = subprocess.run(["git", "branch"], cwd=repo, capture_output=True, text=True).stdout
    assert branches.split() == ["*", "main"]


def test_it_refuses_a_checkout_off_main_or_unclean(tmp_path: Path) -> None:
    repo, env = _repo(tmp_path)
    (repo / "stray.txt").write_text("x", encoding="utf-8")
    assert "nicht sauber" in _run(repo, env, "govdata").stdout
    (repo / "stray.txt").unlink()
    subprocess.run(["git", "switch", "-q", "-c", "other"], cwd=repo, env=env, check=True)
    assert "nicht auf main" in _run(repo, env, "govdata").stdout
    assert not (tmp_path / "docker.log").exists()


def test_classify_runs_as_the_owner_too_and_needs_no_main(tmp_path: Path) -> None:
    repo, env = _repo(tmp_path)
    subprocess.run(["git", "switch", "-q", "-c", "pr-branch"], cwd=repo, env=env, check=True)
    assert _run(repo, env, "govdata", "--classify").returncode == 0
    assert "--classify" in (tmp_path / "docker.log").read_text(encoding="utf-8")


def test_the_powershell_script_runs_the_report_as_the_owner_on_linux() -> None:
    text = PS1.read_text(encoding="utf-8")
    assert "if ($IsLinux) { $asOwner = @('--user'" in text
    assert text.count("@asOwner harvest-report") == 2



def test_the_powershell_script_reads_the_report_as_utf8() -> None:
    # Otto, 20.11.2026: umlauts arrived as "├ñ" in Windows PowerShell 5.1.
    text = PS1.read_text(encoding="utf-8")
    assert "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8" in text
    assert "$OutputEncoding = [System.Text.Encoding]::UTF8" in text
    assert text.index("[Console]::OutputEncoding") < text.index("docker compose run --build --rm @asOwner")
