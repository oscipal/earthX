"""Orders and recipes of version 1, written as version 2 (adr/0020 §11, NM4-43c).

The core runs recipe version 2 only: a stock of named bands that ``band_math`` adds to, and ``output.bands`` that says
what the result holds. Version 1 had no stock. ``band_math`` replaced all bands by one, ``mask`` removed its layer,
``normalize`` took every band, and what was left at the end was the output. The rewrite follows the bands through the
steps and writes down what version 1 did implicitly:

1. Every ``band_math`` gets a name: the last one ``band_math`` as before, the earlier ones ``band_math_<n>``. An
   expression that names ``band_math`` meant the result of the step before, and now names it.
2. ``normalize`` gets as ``bands`` the bands it saw. ``mask`` keeps its parameters; the layer is no longer removed
   by the step, ``output.bands`` leaves it out as the end of version 1 did.
3. ``output.bands`` is the stock at the end of the chain.
4. An order for a raster loses ``assets`` (`api` derives them); a recipe keeps them, they are what it reads.

The values are those of version 1, bit for bit, with one exception: ``reproject`` in version 2 or 3 warps all bands
of the stock in one go, and the planner now drops the bands nobody needs before it (adr/0020 §3.4), so the number of
bands the warp sees can change, and with it the values of that warp. :func:`reproject_changes_values` says whether a
document has such a step; the runner tells the person (F14).

A pure function over JSON data: it reads no registry and no file, and it names no value of the document in a refusal.
`api` calls it for orders until the day it stops accepting version 1, the worker for the recipes its queue still
holds, the runner for good, so that a ``recipe.json`` someone downloaded stays readable (adr/0016).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators.band_math import replace_name
from earthx.processing.recipe import (
    RECIPE_VERSION,
    OperatorLookup,
    Recipe,
    ResolvedInput,
    loads_i_json,
    recipe_from_data,
)
from earthx.processing.source import expected_band_names
from earthx.readers.zarr_reader import VARIABLE_LIST_SEPARATOR

__all__ = [
    "NamesOf",
    "is_version_1",
    "key_names",
    "recipe_of_any_version",
    "reproject_changes_values",
    "upgrade_order",
    "upgrade_recipe",
]

#: The names of the bands of one asset key, as far as the caller knows them.
NamesOf = Callable[[str], Sequence[str]]

_NOT_VERSION_1 = "not a document of recipe version 1"

#: The operators that exist in version 1 and in version 2; version 1 knows their first version only.
_BANDS_STEPS = ("band_math", "mask", "normalize")

#: The versions of ``reproject`` that warp all bands of the stock at once (version 4 warps each for itself).
_ALL_BANDS_WARPS = (2, 3)


def is_version_1(document: object) -> bool:
    """Whether ``document`` says ``recipe_version`` 1 (an ``int``, as the models read it)."""
    version = document.get("recipe_version") if isinstance(document, Mapping) else None
    return type(version) is int and version == 1


def key_names(separator: str | None) -> NamesOf:
    """The names an asset key carries when nothing else is known: itself, or the variables of a Zarr key.

    A COG asset is one band named like the key, a Zarr key ``<asset><separator><variables>`` names its variables.
    An asset with several bands is told apart by the item alone, which an order does not carry.
    """

    def names(key: str) -> list[str]:
        if separator is not None and separator in key:
            _, _, variables = key.partition(separator)
            return [variable for variable in variables.split(VARIABLE_LIST_SEPARATOR) if variable] or [key]
        return [key]

    return names


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RecipeInvalid(_NOT_VERSION_1)
    return value


def _entries(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    inputs = document.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise RecipeInvalid(_NOT_VERSION_1)
    return [_mapping(entry) for entry in inputs]


def _chain(document: Mapping[str, Any], stock: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """The steps of version 2 and the stock after them; ``stock`` is the bands of the data, in the order read."""
    steps = document.get("steps")
    if not isinstance(steps, list):
        raise RecipeInvalid(_NOT_VERSION_1)
    total = sum(1 for step in steps if isinstance(step, Mapping) and step.get("op") == "band_math")
    seen = 0
    previous: str | None = None
    rewritten: list[dict[str, Any]] = []
    for raw in steps:
        step = dict(_mapping(raw))
        op, version = step.get("op"), step.get("op_version")
        params = step.get("params")
        if op in _BANDS_STEPS and (version != 1 or not isinstance(params, Mapping)):
            # A step of version 2 belongs to a document of version 2: this one would run without the checks of either.
            raise RecipeInvalid(_NOT_VERSION_1)
        if version != 1 or not isinstance(params, Mapping):
            rewritten.append(step)
            continue
        if op == "band_math":
            seen += 1
            name = "band_math" if seen == total else f"band_math_{seen}"
            expression = params.get("expression")
            if previous is not None and isinstance(expression, str):
                expression = replace_name(expression, "band_math", previous)
            step.update(op_version=2, params={"expression": expression, "name": name})
            stock, previous = [name], name
        elif op == "mask":
            stock = [name for name in stock if name != params.get("source")]
            step["op_version"] = 2
        elif op == "normalize":
            step.update(op_version=2, params={**params, "bands": list(stock)})
        rewritten.append(step)
    return rewritten, stock


def _upgraded(document: Mapping[str, Any], stock: list[str]) -> dict[str, Any]:
    steps, stock = _chain(document, stock)
    output = {**_mapping(document.get("output")), "bands": stock}
    return {**document, "recipe_version": RECIPE_VERSION, "steps": steps, "output": output}


def upgrade_order(document: Mapping[str, Any], names_of: NamesOf | None = None) -> dict[str, Any]:
    """An order of version 1 as an order of version 2.

    ``names_of`` gives the band names of an asset key; without it every asset is one band named like its key,
    which holds for the datasets of the platform. An order for a crop has no stock and only changes its version.
    """
    if not is_version_1(document):
        raise RecipeInvalid(_NOT_VERSION_1)
    names = names_of or key_names(None)
    entries = _entries(document)
    output = _mapping(document.get("output"))
    if output.get("kind") != "raster":
        return {**document, "recipe_version": RECIPE_VERSION}
    stock: list[str] = []
    for entry in entries:
        assets = entry.get("assets")
        if not isinstance(assets, list) or not all(isinstance(asset, str) for asset in assets):
            raise RecipeInvalid(_NOT_VERSION_1)
        for asset in assets:
            stock.extend(name for name in names(asset) if name not in stock)
    upgraded = _upgraded(document, stock)
    upgraded["inputs"] = [{key: value for key, value in entry.items() if key != "assets"} for entry in entries]
    return upgraded


def upgrade_recipe(document: Mapping[str, Any]) -> dict[str, Any]:
    """A recipe of version 1 as a recipe of version 2: the names of the bands come from the resolved assets.

    ``assets`` and ``resolved`` stay as they are, the core reads what the recipe says; what the planner finds
    nobody needs is dropped after reading, and for ``reproject`` before it.
    """
    if not is_version_1(document):
        raise RecipeInvalid(_NOT_VERSION_1)
    output = _mapping(document.get("output"))
    if output.get("kind") != "raster":
        return {**document, "recipe_version": RECIPE_VERSION}
    stock: list[str] = []
    for entry in _entries(document):
        assets, resolved = entry.get("assets"), entry.get("resolved")
        if not isinstance(assets, list) or not isinstance(resolved, list):
            raise RecipeInvalid(_NOT_VERSION_1)
        for asset in assets:
            stock.extend(name for name in _names_of_resolved(asset, resolved) if name not in stock)
    return _upgraded(document, stock)


def _names_of_resolved(asset: object, resolved: list[Any]) -> list[str]:
    """The names the core gives the bands of ``asset``: from the first resolved entry of it, else the key."""
    for raw in resolved:
        entry = raw.get("asset") if isinstance(raw, Mapping) else None
        if isinstance(entry, Mapping) and entry.get("asset") == asset:
            try:
                names = expected_band_names(ResolvedInput.model_validate(raw, strict=False))
            except ValueError:
                names = None
            return list(names) if names else [str(asset)]
    return [str(asset)]


def reproject_changes_values(document: Mapping[str, Any]) -> bool:
    """Whether a recipe of version 1 has a ``reproject`` whose values may differ after the rewrite (F14)."""
    steps = document.get("steps")
    return isinstance(steps, list) and any(
        isinstance(step, Mapping) and step.get("op") == "reproject" and step.get("op_version") in _ALL_BANDS_WARPS
        for step in steps
    )


def recipe_of_any_version(raw: bytes | str, operators: OperatorLookup) -> Recipe:
    """A recipe from JSON text of version 1 or 2 (I-JSON checked); version 1 is rewritten first."""
    data = loads_i_json(raw)
    if is_version_1(data):
        data = upgrade_recipe(data)
    if not isinstance(data, dict):
        raise RecipeInvalid("a recipe is a JSON object")
    return recipe_from_data(data, operators)
