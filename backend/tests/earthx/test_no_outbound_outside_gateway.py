"""No outgoing request outside the gateway (M1 acceptance, KLAERUNGEN B8).

B8 splits this criterion in two: (a) a static rule that HTTP and S3 clients are
imported only in `gateway`, and (b) tests that every URL handed to rasterio or
GDAL passed `gateway` first. This file carries (a), and carries it twice: once
as the `lint-imports` contract that gates every pull request, and once here as
a walk over the syntax tree, which also sees an import hidden inside a function
and covers modules the contract does not list.

Part (b) needs a caller, and `readers` does not exist yet. What M1-03 can do
for it is make the wrong call impossible to write: `vsicurl_path` accepts a
`CheckedUrl` and nothing else. The rest belongs to the first reader and to the
acceptance report in M1-10.
"""

from __future__ import annotations

import ast
import configparser
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
PACKAGE = REPO / "backend" / "earthx"
CONTRACT = "importlinter:contract:http-only-in-gateway"

# The contract may grow, but never below this: these are the packages that can
# open a connection of their own.
CORE = frozenset({"httpx", "requests", "urllib", "aiohttp", "pystac_client", "boto3"})


def forbidden_modules() -> frozenset[str]:
    """The forbidden list of the contract that CI enforces, read from the file itself."""
    parser = configparser.ConfigParser(allow_no_value=True)
    parser.read(REPO / ".importlinter")
    return frozenset(parser[CONTRACT]["forbidden_modules"].split())


def imported_roots(source: str) -> set[str]:
    """Every top-level package the source imports, including inside a function."""
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def modules_outside_gateway() -> list[Path]:
    return sorted(path for path in PACKAGE.rglob("*.py") if "gateway" not in path.relative_to(PACKAGE).parts)


def test_the_contract_that_ci_enforces_still_names_every_client() -> None:
    assert CORE <= forbidden_modules()


@pytest.mark.parametrize("path", modules_outside_gateway(), ids=lambda path: str(path.relative_to(PACKAGE)))
def test_no_module_outside_the_gateway_imports_a_client(path: Path) -> None:
    assert not imported_roots(path.read_text(encoding="utf-8")) & forbidden_modules()


def test_the_gateway_itself_does_import_one() -> None:
    """Otherwise the rule above would be satisfied by a package that fetches nothing."""
    assert "httpx" in imported_roots((PACKAGE / "gateway" / "client.py").read_text(encoding="utf-8"))


def test_the_walk_sees_an_import_hidden_inside_a_function() -> None:
    """The check is only worth having if it catches what the eye would miss."""
    source = "def fetch(url):\n    import httpx\n    return httpx.get(url)\n"
    assert imported_roots(source) & forbidden_modules() == {"httpx"}
