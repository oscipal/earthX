"""The runner stage of the image is defined the way adr/0016 F1, F10 and F11 decided (M4-16b).

The build itself runs in the `compose-topology` job; these checks hold the
definition in place where Docker is not available. A compose service that
builds without naming its stage would get the last stage of the `Dockerfile`,
and with it the runner's ENTRYPOINT.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
DOCKERFILE = (REPO / "backend" / "Dockerfile").read_text()
FROM_LINES = re.findall(r"^FROM\s+(\S+)(?:\s+AS\s+(\S+))?\s*$", DOCKERFILE, flags=re.MULTILINE)


def _stage(name: str) -> str:
    """The text of the stage ``name``, up to the next ``FROM``."""
    match = re.search(rf"^FROM\s+\S+\s+AS\s+{name}\s*$(.*?)(?=^FROM\s|\Z)", DOCKERFILE, flags=re.MULTILINE | re.DOTALL)
    assert match, f"stage {name!r} is missing"
    return match.group(1)


def test_base_image_is_pinned_by_digest() -> None:
    base, name = FROM_LINES[0]
    assert name == "app"
    assert re.fullmatch(r"python:3\.12-slim@sha256:[0-9a-f]{64}", base), base


def test_runner_builds_on_app_and_is_the_last_stage() -> None:
    assert [name for _, name in FROM_LINES] == ["app", "model-files", "search", "runner"]
    assert dict((name, base) for base, name in FROM_LINES)["runner"] == "app"


def test_only_the_search_stage_carries_the_model() -> None:
    """adr/0026 F2 a: the model files go into the stage of `api` and `catalog-load`, never into the runner (M5-23)."""
    assert dict((name, base) for base, name in FROM_LINES)["search"] == "app"
    assert FROM_LINES[1][0] == FROM_LINES[0][0], "the model stage builds on the same pinned base image"
    copies = re.findall(r"^COPY\s+--from=(\S+)", DOCKERFILE, flags=re.MULTILINE)
    assert copies == ["model-files"]
    assert "--from=model-files" in _stage("search")
    assert "model" not in _stage("runner").lower()


def test_the_model_stage_pins_the_revision_and_checks_each_file() -> None:
    from earthx.catalog.embedding import MODEL_NAME

    body = _stage("model-files")
    revision = re.search(r"^ARG MODEL_REVISION=([0-9a-f]{40})$", body, flags=re.MULTILINE)
    repository = re.search(r"^ARG MODEL_REPOSITORY=(\S+)$", body, flags=re.MULTILINE)
    assert revision and repository
    assert MODEL_NAME == f"{repository.group(1)}@{revision.group(1)}"
    assert len(re.findall(r"^ARG \w+_SHA256=[0-9a-f]{64}$", body, flags=re.MULTILINE)) == 2
    assert "hashlib.sha256" in body and "raise SystemExit" in body


def test_app_stage_sets_no_entrypoint_or_user() -> None:
    body = _stage("app")
    assert not re.search(r"^(ENTRYPOINT|CMD|USER)\b", body, flags=re.MULTILINE)


def test_runner_stage_is_unprivileged_and_enters_the_runner() -> None:
    body = _stage("runner")
    assert re.search(r"^USER\s+10001:10001\s*$", body, flags=re.MULTILINE)
    assert re.search(r'^ENTRYPOINT\s+\["python", "-m", "earthx\.runner"\]\s*$', body, flags=re.MULTILINE)
    assert re.search(r"^ENV\s+EARTHX_COMMIT=\$\{EARTHX_COMMIT\}\s*$", body, flags=re.MULTILINE)


def test_every_compose_build_of_the_backend_names_its_stage() -> None:
    services = yaml.safe_load((REPO / "docker-compose.yml").read_text())["services"]
    builds = {name: s["build"] for name, s in services.items() if "build" in s}
    backend = {name: b for name, b in builds.items() if b["context"] == "./backend"}
    # with `measure-tiles` (M5-30b), `bev-probe` (M5-09), `harvest` (M5-19), `meteoswiss-probe` (M5-11) and
    # `harvest-report`, `harvest-grants` and `harvest-propose` (M5-20), `harvest-linkcheck`, `harvest-spellings` and
    # `harvest-cycle` (M5-67), one-offs under a profile like `materialize`
    assert len(backend) == 19
    # `api` and `catalog-load` build the stage with the embedding model (M5-23), every other one the app without it.
    with_model = {"api", "catalog-load"}
    assert {name: b.get("target") for name, b in backend.items()} == {
        name: "search" if name in with_model else "app" for name in backend
    }
