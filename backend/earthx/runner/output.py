"""The folder of one local run and its ``provenance.json`` (adr/0016 F5, §12b).

::

    <out>/<run_id>/       run_id random, the folder new, never overwritten
      result.tif          from processing.run
      mask.tif            from processing.run
      recipe.json         the bytes of the input, unchanged
      provenance.json     written last
      .work/              the work directory of processing.run, removed at the end

A run that stopped leaves a folder without ``provenance.json``. There is no
``citation.bib``: `api` builds it from the registry, and it comes with the download
(adr/0016 §12b). Nothing here holds a hash, a ``recipe_id`` or a mark of the machine.
"""

from __future__ import annotations

import os
import platform
import re
import secrets
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import earthx
from earthx.processing import RunResult
from earthx.processing.recipe import Provenance, document_bytes

__all__ = ["PROVENANCE_NAME", "RECIPE_NAME", "RunFolder", "numpy_dispatch", "platform_info", "runner_version"]

RECIPE_NAME = "recipe.json"
PROVENANCE_NAME = "provenance.json"
_WORK_NAME = ".work"
_RESULT_FILES = ("result.tif", "mask.tif")
_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")

#: numpy's dispatch levels, highest first (adr/0016 §3.3, K3).
_DISPATCH_LEVELS = ("X86_V4", "X86_V3", "X86_V2", "ASIMD")


def runner_version() -> str:
    """``<version>+g<commit>`` from ``EARTHX_COMMIT`` (F10), ``<version>+unknown`` without a valid commit (K4)."""
    commit = os.environ.get("EARTHX_COMMIT", "").strip().lower()
    return f"{earthx.__version__}+g{commit}" if _COMMIT.match(commit) else f"{earthx.__version__}+unknown"


def numpy_dispatch() -> str:
    """The highest dispatch level numpy uses on this CPU, ``"unknown"`` where numpy does not say (K3)."""
    try:
        from numpy._core._multiarray_umath import __cpu_features__ as features
    except ImportError:
        return "unknown"
    return next((level for level in _DISPATCH_LEVELS if features.get(level)), "unknown")


def platform_info() -> dict[str, str]:
    """What explains a difference of a few ULP between machines (adr/0016 §3.3); identifies no machine."""
    return {"machine": platform.machine() or "unknown", "numpy_dispatch": numpy_dispatch()}


@dataclass(frozen=True, slots=True)
class RunFolder:
    """A new folder under ``out``; :class:`FileExistsError` rather than ever touching an existing one."""

    path: Path

    @classmethod
    def create(cls, out: Path) -> RunFolder:
        path = out / secrets.token_urlsafe(16)
        path.mkdir()
        (path / _WORK_NAME).mkdir()
        return cls(path)

    @property
    def workdir(self) -> Path:
        return self.path / _WORK_NAME

    def remove_workdir(self) -> None:
        shutil.rmtree(self.workdir, ignore_errors=True)

    def finish(
        self,
        result: RunResult,
        *,
        recipe_raw: bytes,
        source: Provenance,
        started: datetime,
        finished: datetime,
    ) -> None:
        """Move the result up, write the recipe as given, then the provenance; then drop the work directory."""
        for name in _RESULT_FILES:
            (self.workdir / name).replace(self.path / name)
        (self.path / RECIPE_NAME).write_bytes(recipe_raw)
        provenance = provenance_document(result, source=source, started=started, finished=finished)
        (self.path / PROVENANCE_NAME).write_bytes(document_bytes(provenance))
        self.remove_workdir()


def provenance_document(
    result: RunResult, *, source: Provenance, started: datetime, finished: datetime
) -> dict[str, Any]:
    """``provenance.json``: the model of adr/0014 §4.1 for a local run, the platform, the result's properties.

    ``attribution`` is the one of the cloud run, which `api` built from the registry;
    ``source_engine`` the versions that run reported (K1).
    """
    local = Provenance(
        execution="local",
        kind="job",
        runner_version=runner_version(),
        self_attested=True,
        engine=dict(result.engine),
        scaling=list(result.scaling),
        started=started,
        finished=finished,
        attribution=list(source.attribution),
    )
    return {
        **local.model_dump(mode="json"),
        "platform": platform_info(),
        "properties": dict(result.properties),
        "source_engine": dict(source.engine),
    }
