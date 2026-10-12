"""Text files in the repo end their lines with LF, and `.gitattributes` knows every binary type (M4-21).

`.gitattributes` makes git normalise line endings, but it cannot stop a session from
writing a CRLF file or from adding a binary type the file does not list. This test
reads the tracked files and nothing else — no network.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CRLF_SUFFIXES = {".bat", ".cmd"}


def _tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, check=True, capture_output=True).stdout
    return [REPO / name for name in out.decode().split("\0") if name]


def _is_binary(data: bytes) -> bool:
    return b"\0" in data


def _declared_binary_suffixes(text: str) -> set[str]:
    suffixes: set[str] = set()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("*.") and "binary" in parts[1:]:
            suffixes.add(parts[0][1:].lower())
    return suffixes


def _crlf_text_files(files: list[Path]) -> list[str]:
    bad = []
    for path in files:
        if path.suffix.lower() in CRLF_SUFFIXES or not path.is_file():
            continue
        data = path.read_bytes()
        if not _is_binary(data) and b"\r\n" in data:
            bad.append(path.as_posix())
    return bad


def _undeclared_binary_suffixes(files: list[Path], declared: set[str]) -> set[str]:
    found = {path.suffix.lower() for path in files if path.is_file() and path.suffix and _is_binary(path.read_bytes())}
    return found - declared


def test_gitattributes_sets_lf_for_text_and_crlf_for_windows_scripts():
    text = (REPO / ".gitattributes").read_text(encoding="utf-8")
    assert "* text=auto eol=lf" in text
    assert "*.bat text eol=crlf" in text
    assert "*.cmd text eol=crlf" in text


def test_no_tracked_text_file_carries_crlf():
    assert _crlf_text_files(_tracked_files()) == []


def test_every_binary_suffix_in_the_repo_is_declared():
    declared = _declared_binary_suffixes((REPO / ".gitattributes").read_text(encoding="utf-8"))
    assert declared, "no binary suffixes parsed from .gitattributes"
    assert _undeclared_binary_suffixes(_tracked_files(), declared) == set()


def test_the_check_catches_a_crlf_text_file(tmp_path):
    bad = tmp_path / "notes.md"
    bad.write_bytes(b"one\r\ntwo\r\n")
    assert _crlf_text_files([bad]) != []


def test_the_check_lets_a_crlf_batch_file_and_a_binary_file_pass(tmp_path):
    bat = tmp_path / "run.bat"
    bat.write_bytes(b"echo hi\r\n")
    blob = tmp_path / "pic.png"
    blob.write_bytes(b"\x89PNG\r\n\x1a\n\0\0")
    assert _crlf_text_files([bat, blob]) == []


def test_the_check_catches_an_undeclared_binary_suffix(tmp_path):
    blob = tmp_path / "chunk.zst"
    blob.write_bytes(b"\x28\xb5\x2f\xfd\0\0")
    assert _undeclared_binary_suffixes([blob], {".png"}) == {".zst"}


def test_declared_suffixes_ignore_comments_and_text_rules():
    text = "# *.foo binary\n* text=auto eol=lf\n*.bat text eol=crlf\n*.png binary\n"
    assert _declared_binary_suffixes(text) == {".png"}
