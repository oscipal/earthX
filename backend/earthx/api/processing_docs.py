"""The documents of the job API that need no job: landing page, conformance, process, order schema.

The job API follows the *form* of OGC API – Processes 1.0 (paths, words, status values, the
status and results documents), but it **claims no conformance** (Otto, M4-08b F4, adr/0014
§15d): Requirement 18 (`/req/core/process-execute-inputs`) part B has a server accept inputs by
reference, and a request that names an address to fetch is what B8 closes. So
``/conformance`` lists no class, and the documents say so in words a client can read.

Every ``href`` is built from the root path the proxy mounts the app at (``root``), so a link is
right behind the frontend's proxy as well as on the service's own port (M4-08b K7).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from earthx.api.intake import MAX_ORDER_ASSETS, MAX_ORDER_STEPS
from earthx.catalog.registry import DatasetConfig
from earthx.objectstore.results import RESULT_NAMES
from earthx.processing.operators import JSON_SCHEMA_DIALECT, Operator, OperatorRegistry, Tier, applicable
from earthx.processing.recipe import RECIPE_VERSION, RecipeRequest

__all__ = [
    "AOI_PROVENANCE",
    "AOI_PROVENANCE_FIELDS",
    "AOI_PROVENANCE_MAX_CHARS",
    "EXPORT_OUTPUTS",
    "FORM_NOTE",
    "INLINE_ONLY",
    "OUTPUTS",
    "PREFIX",
    "PROCESS_ID",
    "RASTER_OUTPUTS",
    "conformance",
    "landing_page",
    "order_schema",
    "process_description",
    "process_list",
    "process_summary",
]

PREFIX = "/processing"
PROCESS_ID = "recipe"

#: What the landing page, the API description and the process say about OGC (F4).
FORM_NOTE = "follows the form of OGC API – Processes, no conformance claimed"

#: The text of the ``400`` for an input given by reference (F4, B8).
INLINE_ONLY = (
    "inputs are accepted inline only: an input given by reference (a link with href) is not fetched; "
    "send the order itself as the value of inputs.recipe"
)

_JSON = "application/json"
_OPENAPI = "application/vnd.oai.openapi+json;version=3.1"
_REL = "http://www.opengis.net/def/rel/ogc/1.0/"

#: Output name → (file in the store, title). ``recipe`` is not a file in the store: `api` builds it.
OUTPUTS: dict[str, tuple[str, str]] = {
    "result": ("result.tif", "Result raster (Cloud Optimized GeoTIFF)"),
    "mask": ("mask.tif", "Mask of the area of interest"),
    "export": ("export.zip", "Export: per group and asset the data and its mask, with notice, recipe and citation"),
    "recipe": ("recipe.json", "The recipe the job ran, with its provenance"),
}

#: The outputs of a job with the output ``raster`` and of an export (output ``crop``, M4-11a).
RASTER_OUTPUTS = ("result", "mask", "recipe")
EXPORT_OUTPUTS = ("export", "recipe")

#: The second, optional input (M4-11 F4): where a place-search AOI came from.
AOI_PROVENANCE = "aoiProvenance"
AOI_PROVENANCE_FIELDS = ("attribution", "license", "source")
AOI_PROVENANCE_MAX_CHARS = 200


def _link(root: str, path: str, rel: str, type_: str | None = _JSON, title: str | None = None) -> dict[str, str]:
    link = {"href": f"{root}{PREFIX}{path}", "rel": rel}
    if type_ is not None:
        link["type"] = type_
    if title is not None:
        link["title"] = title
    return link


def landing_page(root: str) -> dict[str, Any]:
    return {
        "title": "EarthX processing",
        "description": f"Processing jobs over the catalogued datasets. It {FORM_NOTE}.",
        "links": [
            _link(root, "/", "self", title="This document"),
            _link(root, "/api", "service-desc", _OPENAPI, "The API description"),
            _link(root, "/conformance", f"{_REL}conformance", title="Conformance classes (none claimed)"),
            _link(root, "/processes", f"{_REL}processes", title="The processes"),
        ],
    }


def conformance() -> dict[str, Any]:
    """No class is declared, not even ``json`` or ``dismiss`` (F4)."""
    return {"conformsTo": []}


def process_summary(root: str) -> dict[str, Any]:
    return {
        "id": PROCESS_ID,
        "version": str(RECIPE_VERSION),
        "title": "Recipe",
        "description": (
            "Computes a recipe — datasets, items, assets, an area of interest, steps and an output — into a "
            f"Cloud Optimized GeoTIFF. Asynchronous only. It {FORM_NOTE}."
        ),
        "jobControlOptions": ["async-execute", "dismiss"],
        "outputTransmission": ["reference"],
        "links": [_link(root, f"/processes/{PROCESS_ID}", "self", title="The process description")],
    }


def process_list(root: str) -> dict[str, Any]:
    return {
        "processes": [process_summary(root)],
        "links": [_link(root, "/processes", "self", title="This document")],
    }


def process_description(root: str, operators: OperatorRegistry, config: DatasetConfig | None = None) -> dict[str, Any]:
    """The process with the schema of the order; with ``config`` only what this dataset allows."""
    return {
        **process_summary(root),
        "inputs": {
            PROCESS_ID: {
                "title": "Order",
                "description": (
                    "The order itself, inline. It carries no address: the platform resolves items and assets. "
                    "An input given by reference is refused."
                ),
                "minOccurs": 1,
                "maxOccurs": 1,
                "schema": order_schema(operators, config),
            },
            AOI_PROVENANCE: {
                "title": "Origin of the area of interest",
                "description": (
                    "For an export (output crop) only: where a place-search AOI came from, written into "
                    "ATTRIBUTION.txt and aoi.geojson of the export. Not part of the recipe. Each field is one "
                    "line of plain text: no leading or trailing space, no control or format characters."
                ),
                "minOccurs": 0,
                "maxOccurs": 1,
                "schema": {
                    "type": "object",
                    "properties": {
                        name: {"type": "string", "minLength": 1, "maxLength": AOI_PROVENANCE_MAX_CHARS}
                        for name in AOI_PROVENANCE_FIELDS
                    },
                    "additionalProperties": False,
                    "minProperties": 1,
                },
            },
        },
        "outputs": {
            name: {
                "title": title,
                "schema": {"type": "string", "contentMediaType": RESULT_NAMES[file]},
            }
            for name, (file, title) in OUTPUTS.items()
        },
        "links": [
            _link(root, f"/processes/{PROCESS_ID}", "self", title="This document"),
            _link(root, f"/processes/{PROCESS_ID}/execution", f"{_REL}execute", title="Place a job"),
        ],
    }


def _jobs_of(operators: OperatorRegistry, config: DatasetConfig | None) -> list[Operator]:
    """The operators a job can run: in tier T2, and for ``config`` those it is applicable to."""
    chosen = [
        operator
        for _, operator in sorted(operators.items())
        if Tier.T2 in operator.tiers and (config is None or not applicable(operator, config))
    ]
    return chosen


def _prefixed(node: Any, prefix: str) -> Any:
    """``node`` with every ``#/$defs/X`` reference renamed to ``#/$defs/{prefix}X``."""
    if isinstance(node, dict):
        return {
            key: (
                f"#/$defs/{prefix}{value[len('#/$defs/') :]}"
                if key == "$ref" and isinstance(value, str)
                else _prefixed(value, prefix)
            )
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_prefixed(entry, prefix) for entry in node]
    return node


def _step_schemas(operators: OperatorRegistry, chosen: Iterable[Operator]) -> tuple[dict[str, Any], list[str]]:
    """One definition per operator in one version, and its parameter definitions under their own names."""
    defs: dict[str, Any] = {}
    names: list[str] = []
    for operator in chosen:
        name = f"step_{operator.op}_v{operator.op_version}"
        params = operators.params_schema(operator.op, operator.op_version)
        params.pop("$schema", None)
        inner = params.pop("$defs", {})
        prefix = f"{name}__"
        for key, value in inner.items():
            defs[f"{prefix}{key}"] = _prefixed(value, prefix)
        defs[name] = {
            "type": "object",
            "title": operator.title,
            "description": operator.description,
            "additionalProperties": False,
            "required": ["op", "op_version", "params"],
            # Annotations for the panel (M4-13 K1): the planner cuts the steps that can be a tile
            # (`adr/0014` §6.1) at the first one that is not a T1 pixel step. Unknown keywords are
            # annotations in JSON Schema 2020-12, and `additionalProperties` guards the step.
            "x-earthx-tiers": sorted(tier.value for tier in operator.tiers),
            "x-earthx-kind": operator.kind,
            "properties": {
                "op": {"const": operator.op},
                "op_version": {"const": operator.op_version},
                "params": _prefixed(params, prefix),
            },
        }
        names.append(name)
    return defs, names


def order_schema(operators: OperatorRegistry, config: DatasetConfig | None = None) -> dict[str, Any]:
    """The order as JSON Schema 2020-12, with the steps as a union over the operators (K8, adr/0014 §9).

    Built from the models the order is validated with, so the schema cannot promise what
    ``parse_request`` refuses. ``steps`` takes one definition per registered operator in one
    version, ``op`` and ``op_version`` fixed, ``params`` the operator's own schema; with
    ``config`` only the operators applicable to that dataset, and the dataset fixed.
    """
    schema = RecipeRequest.model_json_schema()
    defs: dict[str, Any] = schema.setdefault("$defs", {})
    # What only the order's own models use: the step with free parameters, and the crop, which
    # is described for the synchronous download and never run as a job (api/intake.py, 422).
    for unused in ("Step", "JsonValue", "CropOutput"):
        defs.pop(unused, None)
    schema["properties"]["output"] = {"$ref": "#/$defs/RasterOutput"}
    step_defs, names = _step_schemas(operators, _jobs_of(operators, config))
    defs.update(step_defs)
    if names:
        items: dict[str, Any] = {"oneOf": [{"$ref": f"#/$defs/{name}"} for name in names]}
        # An OpenAPI discriminator needs one schema per value of `op`.
        if len({name.rsplit("_v", 1)[0] for name in names}) == len(names):
            items["discriminator"] = {"propertyName": "op"}
        schema["properties"]["steps"] = {"type": "array", "title": "Steps", "maxItems": MAX_ORDER_STEPS, "items": items}
    else:
        schema["properties"]["steps"] = {"type": "array", "title": "Steps", "maxItems": 0}
    # One input per order, a few assets (api/intake.py): what the schema can say about the size.
    schema["properties"]["inputs"]["maxItems"] = 1
    entry = defs.get("InputRequest")
    if entry is not None:
        entry["properties"]["assets"]["maxItems"] = MAX_ORDER_ASSETS
        if config is not None:
            entry["properties"]["dataset"] = {"const": config.dataset_id, "title": "Dataset"}
            # A Zarr asset is addressed per variable, `<asset><separator><variable>`; the panel
            # needs the separator to name the bands (M4-13 F9). Absent where there is none.
            if config.zarr is not None and config.zarr.variable_separator is not None:
                entry["properties"]["assets"]["x-earthx-variable-separator"] = config.zarr.variable_separator
    return {"$schema": JSON_SCHEMA_DIALECT, **schema}
