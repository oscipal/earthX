"""docker-compose.yml starts `postgres` from the image of M5-43 with the memory settings of M5-66 F7.

Read as YAML; the CI job `compose-topology` starts the real thing and waits for it to report healthy.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
POSTGRES = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))["services"]["postgres"]


def _settings(command: list[str]) -> dict[str, str]:
    """The `-c name=value` pairs of a postgres command line; a dangling `-c` or one without `=` is an error."""
    assert command[0] == "postgres", "the command must start the server, or the entrypoint skips its setup"
    settings: dict[str, str] = {}
    rest = command[1:]
    while rest:
        flag, *rest = rest
        assert flag == "-c" and rest, f"not a -c setting: {flag!r}"
        name, sep, value = rest.pop(0).partition("=")
        assert sep, f"setting without a value: {name!r}"
        settings[name] = value
    return settings


def test_it_is_built_from_the_image_with_pgvector() -> None:
    assert POSTGRES["build"]["context"] == "./compose/postgres"
    assert "image" not in POSTGRES


def test_it_starts_with_the_memory_of_m5_66() -> None:
    settings = _settings([str(part) for part in POSTGRES["command"]])
    assert settings == {"shared_buffers": "512MB", "work_mem": "16MB"}


@pytest.mark.parametrize(
    "broken",
    [["postgres", "-c"], ["postgres", "-c", "work_mem"], ["postgres", "shared_buffers=512MB"], ["sh", "-c", "x=1"]],
)
def test_a_command_that_is_not_a_list_of_settings_is_refused(broken: list[str]) -> None:
    with pytest.raises(AssertionError):
        _settings(broken)
