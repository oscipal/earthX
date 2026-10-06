"""Who reaches the object store, over the syntax tree (adr/0015 §4.3).

`.importlinter` carries the same rules for every pull request. This walk sees
what the contract is not asked about: an import inside a function, `from earthx
import objectstore`, a relative import, and the lock file the image installs.
No network, no import of the modules it reads.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
PACKAGE = REPO / "backend" / "earthx"
RUNTIME_LOCK = REPO / "backend" / "requirements.lock"
CLIENT = PACKAGE / "objectstore" / "client.py"

STORE = "earthx.objectstore"
# 3.1 with the row of adr/0015 §4.2: `jobs` and `api` use the store, and the
# package itself.
MAY_USE_THE_STORE = ("jobs", "api", "objectstore")
# Clients other than `botocore` that the store must not bring along (§4.3 point 3).
OTHER_CLIENTS = frozenset(
    {"httpx", "httpx2", "requests", "urllib", "urllib3", "aiohttp", "pystac_client", "boto3", "obstore",
     "s3transfer", "aiobotocore", "aioboto3", "minio"}
)  # fmt: skip


def _package_of(path: Path) -> list[str]:
    parts = ["earthx", *path.relative_to(PACKAGE).with_suffix("").parts]
    return parts[:-1]  # a module's package; for `__init__` the package itself


def imported_modules(source: str, package: list[str]) -> set[str]:
    """Every module the source names in an import, relative ones resolved against `package`.

    `from a import b` yields both `a` and `a.b`, because `b` may be a submodule
    (`from earthx import objectstore`).
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - (node.level - 1)] if node.level > 1 else list(package)
                module = ".".join([*base, node.module] if node.module else base)
            else:
                module = node.module or ""
            found.add(module)
            found.update(f"{module}.{alias.name}" for alias in node.names)
    return found


def _names(path: Path) -> set[str]:
    return imported_modules(path.read_text(encoding="utf-8"), _package_of(path))


def _modules() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


def _is(name: str, root: str) -> bool:
    return name == root or name.startswith(f"{root}.")


def _top_module(path: Path) -> str:
    return path.relative_to(PACKAGE).parts[0].removesuffix(".py")


@pytest.mark.parametrize("path", _modules(), ids=lambda path: str(path.relative_to(PACKAGE)))
def test_only_jobs_and_api_use_the_object_store(path: Path) -> None:
    if _top_module(path) in MAY_USE_THE_STORE:
        return
    assert not [name for name in _names(path) if _is(name, STORE)]


@pytest.mark.parametrize("path", _modules(), ids=lambda path: str(path.relative_to(PACKAGE)))
def test_botocore_only_in_the_store_client(path: Path) -> None:
    """Stricter than before for `gateway` too, which may otherwise import any client."""
    if path == CLIENT:
        return
    assert not [name for name in _names(path) if _is(name, "botocore")]


def test_the_store_client_does_import_botocore() -> None:
    """Otherwise the rule above would hold for a package that reaches nothing."""
    assert "botocore.session" in _names(CLIENT)


@pytest.mark.parametrize(
    "path", sorted((PACKAGE / "objectstore").glob("*.py")), ids=lambda path: path.name
)  # fmt: skip
def test_the_store_brings_no_other_client(path: Path) -> None:
    assert not {name.split(".")[0] for name in _names(path)} & OTHER_CLIENTS


def _locked_names() -> set[str]:
    pattern = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==", re.MULTILINE)
    return {name.lower().replace("_", "-") for name in pattern.findall(RUNTIME_LOCK.read_text(encoding="utf-8"))}


def test_boto3_never_reaches_the_image() -> None:
    """adr/0015 §3.1, F3: as soon as `boto3` is importable, rasterio opens an
    `AWSSession` for every path with `amazonaws.com` in it and asks the metadata
    service at 169.254.169.254 — a connection past `gateway`, in all four processes
    of the one image. `botocore` alone leaves rasterio as it is."""
    locked = _locked_names()
    assert "botocore" in locked
    assert not locked & {"boto3", "s3transfer"}


# --- counter-checks: each rule notices what it forbids ---------------------------


@pytest.mark.parametrize(
    ("source", "package"),
    [
        ("import earthx.objectstore.results", ["earthx", "access"]),
        ("from earthx import objectstore", ["earthx", "access"]),
        ("from earthx.objectstore.results import upload_result", ["earthx", "access"]),
        ("def later():\n    from earthx.objectstore import results\n", ["earthx", "access"]),
        ("from ..objectstore import results", ["earthx", "access"]),
        ("from ... import objectstore", ["earthx", "access", "sub"]),
    ],
)
def test_every_spelling_of_a_store_import_is_seen(source: str, package: list[str]) -> None:
    assert [name for name in imported_modules(source, package) if _is(name, STORE)]


def test_a_relative_import_inside_the_package_is_not_mistaken_for_one() -> None:
    names = imported_modules("from .resolve import x\nfrom . import tiles\n", ["earthx", "access"])
    assert not [name for name in names if _is(name, STORE)]


@pytest.mark.parametrize(
    "source",
    ["import botocore", "from botocore.config import Config", "def f():\n    import botocore.session\n"],
)
def test_a_botocore_import_is_seen(source: str) -> None:
    assert [name for name in imported_modules(source, ["earthx", "objectstore"]) if _is(name, "botocore")]


def test_another_client_in_the_store_is_seen() -> None:
    names = imported_modules("import urllib3\nfrom boto3 import client\n", ["earthx", "objectstore"])
    assert {name.split(".")[0] for name in names} & OTHER_CLIENTS == {"urllib3", "boto3"}


def test_boto3_in_a_lock_file_would_be_seen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text("boto3==1.43.108 \\\n    --hash=sha256:00\nbotocore==1.43.108 \\\n    --hash=sha256:00\n")
    monkeypatch.setattr(sys.modules[__name__], "RUNTIME_LOCK", lock)
    with pytest.raises(AssertionError):
        test_boto3_never_reaches_the_image()
