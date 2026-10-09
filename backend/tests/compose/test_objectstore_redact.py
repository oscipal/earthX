"""Tests for compose/objectstore/redact.py (M3-23).

Kept dependency-free on purpose (see its docstring), so this can run
anywhere `pytest` does, unlike `smoke.py` itself, which needs `boto3` and
`rasterio` — packages that are not backend dependencies and are installed
only for the CI step that runs it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
REDACT_PATH = REPO / "compose" / "objectstore" / "redact.py"


def _load_redact():
    spec = importlib.util.spec_from_file_location("objectstore_redact", REDACT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


redact_module = _load_redact()
redact = redact_module.redact


def test_redact_replaces_a_single_secret():
    assert redact("token is abc123", "abc123") == "token is <redacted>"


def test_redact_replaces_every_occurrence():
    assert redact("abc123 and abc123 again", "abc123") == "<redacted> and <redacted> again"


def test_redact_replaces_several_secrets():
    text = "key=access-key-1 secret=super-secret-2"
    assert redact(text, "access-key-1", "super-secret-2") == "key=<redacted> secret=<redacted>"


def test_redact_leaves_text_without_any_secret_unchanged():
    assert redact("nothing sensitive here", "some-secret") == "nothing sensitive here"


def test_redact_ignores_empty_secret_values():
    # An empty string would otherwise match everywhere and mangle the text
    # (str.replace("", "<redacted>", text) inserts it between every character).
    assert redact("plain text", "") == "plain text"


def test_redact_with_no_secrets_given_is_a_no_op():
    assert redact("plain text") == "plain text"
