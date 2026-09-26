"""Static checks on compose/objectstore/smoke.py's GDAL setup (M3-23).

`smoke.py` needs `boto3`/`rasterio`, which are not backend dependencies and
are installed only for the CI step that runs it (compose/objectstore/
requirements-smoke.txt) — so it cannot be imported here. These checks read
its source with `ast` instead, which is enough to catch the mistake that
only showed up once in CI (26.09.2026): rasterio 1.5.1 refuses
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` in `rasterio.Env` outright
("AWS credentials are handled exclusively by boto3"), so a `/vsis3/` read
next to a boto3 client for the same object can never carry credentials that
way. `smoke.py` reads over `/vsicurl/` with a presigned URL instead — no
GDAL AWS configuration at all, and the same path M4 uses in the platform
itself (adr/0012 F3).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SMOKE_PATH = REPO / "compose" / "objectstore" / "smoke.py"

# rasterio 1.5.1's own refusal (rasterio/env.py); kept here as a named set in
# case a later rasterio also rejects the sibling S3 secret-access-key spelling.
FORBIDDEN_ENV_OPTIONS = frozenset({"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"})


def _env_calls(tree: ast.AST) -> list[ast.Call]:
    """Every call in the file that looks like `rasterio.Env(...)` or `Env(...)`."""
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_env = (isinstance(func, ast.Attribute) and func.attr == "Env") or (
            isinstance(func, ast.Name) and func.id == "Env"
        )
        if is_env:
            calls.append(node)
    return calls


def test_no_rasterio_env_call_carries_a_forbidden_aws_credential_option():
    tree = ast.parse(SMOKE_PATH.read_text())
    for call in _env_calls(tree):
        kwargs = {kw.arg for kw in call.keywords if kw.arg is not None}
        forbidden = kwargs & FORBIDDEN_ENV_OPTIONS
        assert not forbidden, (
            f"rasterio.Env(...) at line {call.lineno} in {SMOKE_PATH.name} passes "
            f"{forbidden}, which rasterio refuses (\"AWS credentials are handled "
            "exclusively by boto3\")."
        )


def test_the_cog_is_read_over_vsicurl_with_a_presigned_url_not_vsis3():
    source = SMOKE_PATH.read_text()
    assert "/vsicurl/" in source, "expected a /vsicurl/ read with a presigned URL"
    assert "/vsis3/" not in source, (
        "a /vsis3/ read needs GDAL-level AWS credentials next to the boto3 client "
        "for the same object, which is exactly what failed in CI (see this file's docstring)"
    )
