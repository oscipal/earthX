"""Read a ``recipe.json`` of a platform result and check it before anything is read (adr/0016 F3, F4).

**The file (F3).** Exactly what lies next to every result: the recipe (adr/0014 §4.2) and
one ``provenance`` block of the cloud run (adr/0014 §10.1). The block is split off and
checked with :class:`~earthx.processing.recipe.Provenance`; it must say ``cloud``
(adr/0016 §12b). The rest goes through the same strict models as in `api`, the
expressions of band math through the parameter model of R5 before numexpr sees them.

**The hosts (F4).** Every host an input reads lies on the ``asset_hosts`` of its dataset
in the registry of this image, the check `api` makes at acceptance. A recipe from a third
party cannot send the runner to an arbitrary server, whose files GDAL would then parse on
the user's machine (architekturplan 11).

No text here names an address, a coordinate or a value of the file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from earthx.catalog.datasets import REGISTRY as DATASETS
from earthx.catalog.registry import DatasetRegistry, UnknownDatasetError
from earthx.processing import failure_kind
from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators import REGISTRY as OPERATORS
from earthx.processing.recipe import Provenance, Recipe, input_hosts, loads_i_json, recipe_from_data

__all__ = ["MAX_RECIPE_BYTES", "HostRefused", "RecipeFile", "check_hosts", "load_recipe", "read_recipe_file"]

#: The body of an order is at most 1 MiB; ``resolved`` and the footprints add to it (K6).
MAX_RECIPE_BYTES = 4 * 1024 * 1024


class HostRefused(Exception):
    """A dataset of the recipe is not in this image, or an input reads a host its dataset does not declare."""


@dataclass(frozen=True, slots=True)
class RecipeFile:
    """A checked ``recipe.json``: its bytes as given, the recipe, and the provenance of the cloud run."""

    raw: bytes
    recipe: Recipe
    provenance: Provenance


def read_recipe_file(path: Path) -> RecipeFile:
    """The file at ``path``, checked; :class:`RecipeInvalid` for anything that is not a recipe of a result."""
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_RECIPE_BYTES + 1)
    except OSError:
        raise RecipeInvalid("the recipe file cannot be read") from None
    return load_recipe(raw)


def load_recipe(raw: bytes) -> RecipeFile:
    """``raw`` as a recipe with its cloud provenance, or :class:`RecipeInvalid`."""
    if len(raw) > MAX_RECIPE_BYTES:
        raise RecipeInvalid(f"a recipe file is at most {MAX_RECIPE_BYTES} bytes")
    document = loads_i_json(raw)
    if not isinstance(document, dict):
        raise RecipeInvalid("a recipe file is a JSON object")
    if "provenance" not in document:
        raise RecipeInvalid("a recipe file of a result carries its provenance block")
    rest = dict(document)
    provenance = _cloud_provenance(rest.pop("provenance"))
    return RecipeFile(raw=raw, recipe=recipe_from_data(rest, OPERATORS), provenance=provenance)


def _cloud_provenance(block: Any) -> Provenance:
    try:
        provenance = Provenance.model_validate_json(json.dumps(block, allow_nan=False), strict=True)
    except (ValidationError, ValueError, TypeError):
        raise RecipeInvalid("the provenance block of the recipe file is not valid") from None
    if provenance.execution != "cloud":
        raise RecipeInvalid("the recipe file comes from a local run; run the recipe of a platform result")
    return provenance


def check_hosts(recipe: Recipe, registry: DatasetRegistry = DATASETS) -> tuple[str, ...]:
    """The hosts the recipe reads, sorted, once each lies on its dataset's ``asset_hosts``; else :class:`HostRefused`."""
    hosts: set[str] = set()
    for entry in recipe.inputs:
        try:
            config = registry.get(entry.dataset)
        except UnknownDatasetError:
            raise HostRefused(f"dataset {entry.dataset!r} is not known to this runner") from None
        try:
            named = input_hosts(entry)
        except Exception as error:
            if failure_kind(error) != "rejected":
                raise
            raise HostRefused(f"an address of dataset {entry.dataset!r} names no valid host") from None
        if not set(named) <= set(config.source.asset_hosts):
            raise HostRefused(f"the recipe reads a host dataset {entry.dataset!r} does not declare")
        hosts.update(named)
    return tuple(sorted(hosts))
