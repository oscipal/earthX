"""The inside of a container of the harvest, rebuilt here from ``backend/Dockerfile`` and ``docker-compose.yml``.

Docker never runs in a cloud session or in the unit job (adr/0002), and the Python tests of the harvest ran on the
checkout, where every file is where the code looks for it. Otto's second trial run (M5-67 fix 2, 24.11.2026) stopped at
``flags.yaml: cannot be read as UTF-8 text (FileNotFoundError)``: the file was in the checkout, in no ``COPY`` of the
Dockerfile and in no ``volumes:`` of the service. This module makes the difference visible. It builds the tree a service
sees under ``/app`` — the package ``earthx``, every ``COPY`` of the stage ``app`` and every mount of the service whose
target lies under ``/app`` — and runs the entry point of the service there, as a process of its own, so that
``earthx.catalog.datasets.CATALOG_DIR`` is the ``catalog`` of the tree and nothing else. Other mounts (``/out``,
``/approvals``, ``/harvest``, ``-v <folder>:/run``) become folders of the test and are named in the arguments as the
service names them.

Read as text, like ``test_image_catalog_entries.py``: ``COPY`` and ``ADD`` lines, ``volumes:`` of one service in the
short form. Anything else raises, so that a new form is noticed here and not trusted blindly.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
COMPOSE = REPO / "docker-compose.yml"
APP = "/app"
HARVEST_PROFILE = "harvest"

__all__ = ["BACKEND", "COMPOSE", "REPO", "Container", "build_container", "harvest_services"]


def copy_instructions(dockerfile: str, stage: str = "app") -> list[tuple[str, str]]:
    """``(source, destination)`` of every ``COPY`` and ``ADD`` of one stage, one pair for each source, flags dropped."""
    found = []
    current = None
    for line in re.sub(r"\\\n", " ", dockerfile).splitlines():
        stage_line = re.match(r"\s*FROM\s+.*?(?:\s+AS\s+(\S+))?\s*$", line, flags=re.IGNORECASE)
        if stage_line:
            current = (stage_line.group(1) or "").lower()
            continue
        match = re.match(r"\s*(COPY|ADD)\s+(.*)$", line, flags=re.IGNORECASE)
        if not match or current != stage:
            continue
        rest = match.group(2).strip()
        words = json.loads(rest) if rest.startswith("[") else rest.split()
        words = [word for word in words if not word.startswith("--")]
        found += [(source, words[-1]) for source in words[:-1]]
    return found


def harvest_services() -> dict[str, dict]:  # type: ignore[type-arg]
    """The services of the profile ``harvest`` that start a module of ``earthx``, by name."""
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    return {
        name: service
        for name, service in services.items()
        if HARVEST_PROFILE in service.get("profiles", ())
        and service.get("entrypoint", [])[:2] == ["python", "-m"]
        and "build" in service
    }


def _short_volume(text: str) -> tuple[Path, str, bool]:
    parts = text.split(":")
    if len(parts) not in (2, 3) or (len(parts) == 3 and parts[2] not in ("ro", "rw")):
        raise ValueError(f"volume {text!r}: only SOURCE:TARGET[:ro|rw] is read here")
    return REPO / parts[0], parts[1], len(parts) == 3 and parts[2] == "ro"


def _put(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    else:
        shutil.copy2(source, target)


@dataclass
class Container:
    """One service of the harvest, as its container sees it."""

    service: str
    root: Path
    entrypoint: list[str]
    #: Container path of a mount outside ``/app`` -> the folder of the test that stands for it.
    mounts: dict[str, Path] = field(default_factory=dict)

    @property
    def app(self) -> Path:
        return self.root / "app"

    @property
    def catalog(self) -> Path:
        return self.app / "catalog"

    def mount(self, target: str) -> Path:
        """The folder of a mount that only the command line names (``-v <folder>:/run``), made on first use."""
        folder = self.mounts.setdefault(target, self.root / "mounts" / target.strip("/").replace("/", "_"))
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _here(self, argument: str) -> str:
        for target, folder in sorted(self.mounts.items(), key=lambda item: -len(item[0])):
            if argument == target or argument.startswith(target + "/"):
                return str(folder / argument.removeprefix(target).lstrip("/"))
        return argument

    def run(self, *arguments: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        """The entry point with ``arguments``, in the tree, as a process of its own. Container paths are replaced by the
        folders of the test; the environment is the one of the test (the database), plus ``env``."""
        return self._process([sys.executable, *(self._here(a) for a in [*self.entrypoint[1:], *arguments])], env)

    def python(self, code: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        """``python -c code`` in the tree, for what a test asks of the code there."""
        return self._process([sys.executable, "-c", code, *arguments], None)

    def _process(self, command: list[str], env: dict[str, str] | None) -> subprocess.CompletedProcess[str]:
        process_env = {**os.environ, "PYTHONPATH": str(self.app), "HOME": str(self.root), **(env or {})}
        return subprocess.run(
            command, cwd=self.app, env=process_env, capture_output=True, text=True, check=False, timeout=300
        )


def build_container(service: str, root: Path) -> Container:
    """The tree of ``service`` under ``root``: the package, the ``COPY`` lines of the stage ``app``, the mounts."""
    definition = harvest_services()[service]
    app = root / "app"
    _put(BACKEND / "earthx", app / "earthx")
    ignored = {
        line.strip().rstrip("/")
        for line in (BACKEND / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    for source, destination in copy_instructions((BACKEND / "Dockerfile").read_text(encoding="utf-8")):
        if source == "earthx" or source.rstrip("/") in ignored or source == "requirements.lock":
            continue
        # WORKDIR is /app: a relative destination is under it; a source into a folder keeps its name.
        target = app / destination
        _put(BACKEND / source, target / Path(source).name if destination.endswith("/") else target)
    container = Container(service, root, list(definition["entrypoint"]))
    for text in definition.get("volumes", []):
        source, target, _ = _short_volume(text)
        if not source.exists():
            raise FileNotFoundError(f"{service}: the mount {text!r} has no source in the checkout")
        if target == APP or target.startswith(APP + "/"):
            _put(source, app / target.removeprefix(APP + "/"))
        else:
            folder = root / "mounts" / target.strip("/").replace("/", "_")
            _put(source, folder)
            container.mounts[target] = folder
    return container
