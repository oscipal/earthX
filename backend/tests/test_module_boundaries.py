"""The prepared import-linter contracts still match architekturplan.md 3.1.

The contracts in `.importlinter` are not enforced yet — the target modules do
not exist (docs/adr/0002-testaufteilung.md). This test keeps the file honest in
the meantime: it parses `.importlinter` and compares the allowed imports it
implies against the table in the architecture plan, which is restated here.
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


def _modules(parser: configparser.ConfigParser, section: str, option: str) -> set[str]:
    raw = parser.get(section, option, fallback="")
    return {line.strip().removeprefix("app.") for line in raw.splitlines() if line.strip()}


def test_contracts_are_dormant_in_pull_requests() -> None:
    """CI must not gate on the contracts yet — the target modules do not exist."""
    workflow = (CONFIG.parent / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "lint-imports" in workflow, "the manual job should still exist"
    assert "workflow_dispatch" in workflow


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
    assert _modules(config, section, "source_modules") == ALL_MODULES - {"gateway"}
    assert "httpx" in _modules(config, section, "forbidden_modules")
