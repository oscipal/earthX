"""The registry of this process, read from the curated YAML entries (KLAERUNGEN B13 stage 2, adr/0025 §7).

Each dataset is one file under ``backend/catalog/datasets/``, the datasets that left the registry are
``backend/catalog/retired.yaml`` (adr/0017). ``catalog.entry_files`` turns a file into the same
:class:`~earthx.catalog.registry.DatasetConfig` the entries were in Python up to M4, with every check of the
dataclasses; callers notice nothing. :func:`registry` builds the registry once per process, the one place every
process asks (docs/plans/m5/m5-13-yaml-lader.md §3.2).
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import earthx
from earthx.catalog.entry_files import EntryFileError, load_entry, load_retired
from earthx.catalog.registry import DatasetRegistry

__all__ = ["CATALOG_DIR", "read_registry", "registry"]

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


def read_registry(catalog_dir: Path = CATALOG_DIR) -> DatasetRegistry:
    """The registry from the entries under ``catalog_dir/datasets`` and ``catalog_dir/retired.yaml``."""
    entries = tuple(load_entry(path) for path in _entry_files(catalog_dir / "datasets"))
    return DatasetRegistry(entries, retired=load_retired(catalog_dir / "retired.yaml"))


@cache
def registry() -> DatasetRegistry:
    """The registry of this process, read once."""
    return read_registry()
