"""The enforced import-linter contracts still match architekturplan.md 3.1.

`.importlinter` gates every pull request since M1-02 (docs/adr/0002-testaufteilung.md).
This test keeps the file honest: it parses `.importlinter` and compares the
allowed imports it implies against the table in the architecture plan, which
is restated here.
"""

from __future__ import annotations

import configparser
from pathlib import Path

import pytest

CONFIG = Path(__file__).resolve().parents[2] / ".importlinter"

# architekturplan.md 3.1, column "Darf importieren". `api` may import everything,
# `datasets` is isolated; both are checked separately below.
ALLOWED_IMPORTS = {
    "gateway": set(),
    "catalog": {"gateway"},
    "adapters": {"gateway", "catalog"},
    "readers": {"gateway"},
    "access": {"readers", "catalog"},
    "processing": {"access", "readers", "catalog"},
    "jobs": {"processing"},
    "discovery": {"adapters", "catalog", "gateway"},
    "identity": set(),
}
ALL_MODULES = set(ALLOWED_IMPORTS) | {"api", "datasets"}


@pytest.fixture(scope="module")
def config() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    assert parser.read(CONFIG, encoding="utf-8"), f"{CONFIG} is missing or unreadable"
    return parser


def _root_modules() -> set[str]:
    """Modules living directly in `backend/earthx/`, outside the eleven of 3.1.

    They carry no contract of their own — there is no column for them in the
    table — but they are code that must not open a connection, so the client
    contract has to cover them. Read from disk rather than listed, so a new one
    fails this suite until `.importlinter` names it.
    """
    root = CONFIG.parent / "backend" / "earthx"
    return {path.stem for path in root.glob("*.py") if path.stem != "__init__"}


def _modules(parser: configparser.ConfigParser, section: str, option: str) -> set[str]:
    raw = parser.get(section, option, fallback="")
    return {line.strip().removeprefix("earthx.") for line in raw.splitlines() if line.strip()}


def test_contracts_are_enforced_in_pull_requests(config: configparser.ConfigParser) -> None:
    """CI must gate on the contracts now that backend/earthx/ exists (M1-02)."""
    assert config.get("importlinter", "root_package") == "earthx"
    workflow = (CONFIG.parent / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "lint-imports" in workflow
    # workflow_dispatch is still the trigger that lets it be run manually too,
    # but it must no longer be the *only* way the job runs.
    assert workflow.count("workflow_dispatch") == 1


@pytest.mark.parametrize("module", sorted(ALLOWED_IMPORTS))
def test_every_module_has_a_contract(config: configparser.ConfigParser, module: str) -> None:
    assert config.has_section(f"importlinter:contract:{module}")


@pytest.mark.parametrize("module", sorted(ALLOWED_IMPORTS))
def test_forbidden_modules_are_the_complement_of_the_allowed_ones(
    config: configparser.ConfigParser, module: str
) -> None:
    forbidden = _modules(config, f"importlinter:contract:{module}", "forbidden_modules")
    expected = ALL_MODULES - ALLOWED_IMPORTS[module] - {module}
    assert forbidden == expected


def test_datasets_stay_isolated(config: configparser.ConfigParser) -> None:
    section = "importlinter:contract:datasets-isolated"
    assert _modules(config, section, "forbidden_modules") == {"datasets"}
    assert _modules(config, section, "source_modules") == ALL_MODULES - {"datasets", "api"}


def test_http_clients_are_confined_to_gateway(config: configparser.ConfigParser) -> None:
    section = "importlinter:contract:http-only-in-gateway"
    assert _modules(config, section, "source_modules") == (ALL_MODULES - {"gateway"}) | _root_modules()
    forbidden = _modules(config, section, "forbidden_modules")
    for client in {"httpx", "requests", "urllib", "pystac_client", "aiohttp"}:
        assert client in forbidden


def test_the_worker_core_reaches_no_database(config: configparser.ConfigParser) -> None:
    """KLAERUNGEN B9: no database, queue, object store or internal API in the core.

    Guarded rather than only stated since M1-04b, which is when psycopg became a real
    dependency. Reading the data sources through `gateway` stays allowed.
    """
    section = "importlinter:contract:no-database-in-worker-core"
    assert _modules(config, section, "source_modules") == {"jobs", "processing"}
    assert "psycopg" in _modules(config, section, "forbidden_modules")


def test_every_module_exists_as_a_package() -> None:
    """architekturplan.md 3.1: all eleven modules exist, today as empty packages."""
    earthx_root = CONFIG.parent / "backend" / "earthx"
    for module in ALL_MODULES:
        assert (earthx_root / module / "__init__.py").is_file(), module
