"""The steps of one harvest run start in the container, on the files the container has (M5-67 fix 2, 24.11.2026).

``test_cycle_run.py`` runs the steps in order on the checkout. This one runs the entry point of every service of the
harvest in the tree its Dockerfile and compose file make (``tests/container_tree.py``) as a process of its own, against
the database of the test: what a step reads when it starts must be there, with the arguments ``scripts/harvest-cycle.ps1``
gives it. Nothing is asked of a source (adr/0002): ``harvest`` is started with a source that does not exist, which is
refused after the files it reads at its start; the others find no entry in the database and write nothing but their
own folders. Since fix 2 the report reads the warning signs at its start, with or without an entry to report, so this
also holds for a database without finds.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.container_tree import Container, build_container

DAY = "2026-11-24"
SOURCE = "fsdi-stac"


@pytest.fixture
def _environment(catalogue_loaded: None, monkeypatch: pytest.MonkeyPatch) -> None:
    # `catalogue_loaded` is what the compose service `catalog-load` does before every service of the harvest starts.
    monkeypatch.setenv("EARTHX_USER_AGENT", "earthx-test/0 (+https://example.org/contact)")


def _container(service: str, tmp_path: Path) -> Container:
    return build_container(service, tmp_path / service)


def _ok(done: object, step: str) -> str:
    code, out, err = done.returncode, done.stdout, done.stderr  # type: ignore[attr-defined]
    # The line that says why is the last one that is no JSON log line (what `Reason` in the script picks).
    why = [line for line in (out + err).splitlines() if line and not line.startswith("{")][-3:]
    assert code == 0, f"{step} exited with {code}: {why}"
    return out


@pytest.mark.usefixtures("_environment")
def test_the_steps_of_a_run_start_in_their_containers(tmp_path: Path) -> None:
    cycle = _container("harvest-cycle", tmp_path)
    run = cycle.mount("/run")
    harvest_dir = cycle.mounts["/harvest"]
    assert (harvest_dir / "befunde.md").is_file()

    assert SOURCE in _ok(cycle.run("sources"), "sources").split()

    spellings = _container("harvest-spellings", tmp_path)
    spellings.mount("/run")
    _ok(spellings.run("--json", "/run/spellings.json"), "spellings")
    assert (spellings.mounts["/out"] / "spellings.yaml").is_file()

    grants = _container("harvest-grants", tmp_path)
    _ok(grants.run(SOURCE), "grants")

    report = _container("harvest-report", tmp_path)
    report.mount("/run")
    _ok(report.run(SOURCE, "--json", "/run/report.json"), "report")
    _ok(report.run(SOURCE, "--classify"), "classify")

    linkcheck = _container("harvest-linkcheck", tmp_path)
    linkcheck.mount("/run")
    _ok(linkcheck.run("--dry-run", "--json", "/run/linkcheck.json"), "linkcheck")

    cycle.mounts["/run"] = run
    _ok(cycle.run("decide", "--run", "/run", "--approvals", "/approvals", "--day", DAY, "--trial"), "decide")
    _ok(
        cycle.run("summary", "--run", "/run", "--harvest", "/harvest", "--approvals", "/approvals", "--day", DAY, "--trial"),
        "summary",
    )
    assert (run / "pr-body.md").is_file() and (run / "ergebnis.txt").is_file()
    assert (harvest_dir / "laeufe" / DAY / "README.md").is_file()


@pytest.mark.usefixtures("_environment")
def test_the_harvest_reads_its_files_before_it_refuses_an_unknown_source(tmp_path: Path) -> None:
    done = _container("harvest", tmp_path).run("no-such-source")
    assert done.returncode == 1
    assert "no source 'no-such-source'" in done.stderr and "file not found" not in done.stderr


@pytest.mark.usefixtures("_environment")
@pytest.mark.parametrize(
    ("service", "arguments", "missing"),
    [
        ("harvest-report", (SOURCE,), "flags.yaml"),
        ("harvest-linkcheck", ("--dry-run",), "linkcheck.yaml"),
        ("harvest-cycle", ("decide", "--run", "/run", "--day", DAY, "--trial"), "approval_rules.yaml"),
    ],
)
def test_a_rule_file_missing_from_the_container_stops_the_step_and_names_the_file(
    service: str, arguments: tuple[str, ...], missing: str, tmp_path: Path
) -> None:
    # The error of 24.11.2026, made on purpose: the step must say which file, so that the window of the script does.
    container = _container(service, tmp_path)
    container.mount("/run")
    (container.catalog / missing).unlink()
    done = container.run(*arguments)
    assert done.returncode == 1
    assert f"{missing}: file not found" in done.stderr
