"""The registry of this process, read from the curated YAML entries (KLAERUNGEN B13 stage 2, adr/0025 §7).

Each dataset is one file under ``backend/catalog/datasets/``, the datasets that left the registry are
``backend/catalog/retired.yaml`` (adr/0017). ``catalog.entry_files`` turns a file into the same
:class:`~earthx.catalog.registry.DatasetConfig` the entries were in Python up to M4, with every check of the
dataclasses; callers notice nothing. :func:`registry` builds the registry once per process, the one place every
process asks (docs/plans/m5/m5-13-yaml-lader.md §3.2).

Prototype entries (adr/0024) lie in a directory of their own that is never in an image; they are read only when
``EARTHX_PROTOTYPE_SOURCES`` names it, ``EARTHX_PROFILE`` is ``local`` and ``CI`` is not set (R5). Any other setting
with the path is an error at the start, not a quiet omission (:func:`prototype_dir_from_env`).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from functools import cache
from pathlib import Path

import earthx
from earthx.catalog.entry_files import EntryFileError, load_entry, load_retired
from earthx.catalog.registry import ConfigError, DatasetConfig, DatasetRegistry, LegalStatus

__all__ = [
    "CATALOG_DIR",
    "PROFILES",
    "InstanceSettingError",
    "prototype_dir_from_env",
    "read_registry",
    "registry",
]

LOGGER = logging.getLogger(__name__)

# Where the curated entries lie (adr/0025 §7.1): `backend/catalog` in the repo, `/app/catalog` in the image. A constant
# of the package, never a variable of the environment.
CATALOG_DIR = Path(earthx.__file__).resolve().parents[1] / "catalog"
_README = "README.md"


def _entry_files(directory: Path) -> list[Path]:
    """The ``*.yaml`` files of ``directory``; anything else but a README is an error, so a stray file is noticed."""
    files = []
    for path in sorted(directory.iterdir()):
        if path.name == _README:
            continue
        if not path.is_file() or path.suffix != ".yaml":
            raise EntryFileError(f"{directory.name}/{path.name}: only <dataset_id>.yaml files and a README belong here")
        files.append(path)
    return files


#: The variables of the start check (adr/0024 R5, adr/0025 §7.4).
PROFILE_VARIABLE = "EARTHX_PROFILE"
PROTOTYPE_VARIABLE = "EARTHX_PROTOTYPE_SOURCES"
#: The profiles an instance may name (adr/0025 §7.4); in M5 only `local` changes anything.
PROFILES = ("local", "ci", "cloud")


class InstanceSettingError(ConfigError):
    """A setting of the instance that keeps a process from starting; the text names variables, never their values."""


def prototype_dir_from_env(environ: Mapping[str, str] = os.environ) -> Path | None:
    """The directory of the prototype entries, or None where the instance reads none (adr/0024 R5, plan §3.5).

    ``EARTHX_PROFILE`` is free without the path (A5) but never an unknown value. ``CI`` counts as set with any
    value that is not empty, ``false`` included (A6).
    """
    profile = environ.get(PROFILE_VARIABLE, "").strip()
    if profile and profile not in PROFILES:
        raise InstanceSettingError(f"{PROFILE_VARIABLE} is set to a profile other than {', '.join(PROFILES)}")
    path = environ.get(PROTOTYPE_VARIABLE, "").strip()
    if not path:
        return None
    if profile != "local":
        raise InstanceSettingError(f"{PROTOTYPE_VARIABLE} is set, but {PROFILE_VARIABLE} is not local (adr/0024 R5)")
    if environ.get("CI", "").strip():
        raise InstanceSettingError(f"{PROTOTYPE_VARIABLE} is set in CI (adr/0024 R5)")
    directory = Path(path)
    if not directory.is_dir():
        raise InstanceSettingError(f"{PROTOTYPE_VARIABLE} names no directory")
    return directory


def _entries(directory: Path, status: LegalStatus) -> tuple[DatasetConfig, ...]:
    """The entries of ``directory``, each with ``status``: released ones are cleared, prototypes unclear (R3)."""
    entries = tuple(load_entry(path) for path in _entry_files(directory))
    for entry in entries:
        if entry.legal_status is not status:
            raise EntryFileError(
                f"{directory.name}/{entry.dataset_id}.yaml: an entry here has legal_status {status.value}"
            )
    return entries


def read_registry(catalog_dir: Path = CATALOG_DIR, prototype_dir: Path | None = None) -> DatasetRegistry:
    """The registry from ``catalog_dir/datasets`` and ``catalog_dir/retired.yaml``, plus the prototype entries of
    ``prototype_dir`` where one is given."""
    entries = _entries(catalog_dir / "datasets", LegalStatus.CLEARED)
    if prototype_dir is not None:
        entries += _entries(prototype_dir, LegalStatus.UNCLEAR)
    return DatasetRegistry(entries, retired=load_retired(catalog_dir / "retired.yaml"))


@cache
def registry(*, prototype: bool = True) -> DatasetRegistry:
    """The registry of this process, read once, with the start check of adr/0024 R5.

    The runner asks with ``prototype=False``: it is built to be handed on (adr/0016), so it never reads the
    prototype directory and only warns where the variable is set (A7); a recipe of a prototype dataset is unknown
    there.
    """
    if not prototype:
        if os.environ.get(PROTOTYPE_VARIABLE, "").strip():
            LOGGER.warning("%s is set and ignored: this process never reads prototype entries", PROTOTYPE_VARIABLE)
        return read_registry()
    return read_registry(prototype_dir=prototype_dir_from_env())
