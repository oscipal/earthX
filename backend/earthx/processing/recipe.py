"""Order, recipe and provenance; canonical form and hash (adr/0014 §4).

Three layers (F1):

* :class:`RecipeRequest` — the **order** as a panel, an API client or a chatbot
  sends it: datasets, items, assets, AOI, steps, output. No address.
* :class:`Recipe` — the order after `api` accepted it: every input carries its
  :class:`ResolvedInput` entries (the ``ResolvedAsset`` of adr/0011 §6.4, the
  version, the bands and the scaling source). This is what the core runs and what
  is hashed.
* :class:`Provenance` — what happened when it ran. Never hashed.

**One way in.** Every model is strict, forbids unknown fields and is frozen.
:func:`parse_request` and :func:`parse_recipe` take JSON text only, because the
I-JSON checks of §4.4 step 1 (duplicate keys, ``NaN``, ``Infinity``, numbers
outside float64) are invisible once ``json.loads`` has silently collapsed them.
A caller holding Python data goes through :func:`recipe_from_data`, which
serialises it first.

**Hash ``c1``** (§4.4, approved with condition F2): the validated model as
``model_dump(mode="json")``, ``-0.0`` turned into ``0.0``, ``json.dumps`` with
sorted keys, no whitespace, ``ensure_ascii=False`` and ``allow_nan=False``,
SHA-256 over the UTF-8 bytes, prefixed ``c1:``. It is an internal key only (Q8):
it never leaves the platform, never appears in a log, and no browser or runner
computes it.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import datetime
from importlib import metadata
from typing import Annotated, Any, Literal, Protocol

import numpy
import rasterio
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, model_serializer, model_validator
from shapely.errors import ShapelyError
from shapely.geometry import shape as shapely_shape

import earthx
from earthx.access.crop_rules import RESOLUTION_FACTORS
from earthx.access.resolve import ReaderKind, ResolvedAsset
from earthx.processing.errors import RecipeInvalid, UnknownOperator
from earthx.readers import hosts_for

__all__ = [
    "HASH_METHOD",
    "RECIPE_VERSION",
    "Band",
    "CropOutput",
    "Footprint",
    "Input",
    "InputRequest",
    "InputVersion",
    "MultiPolygon",
    "Polygon",
    "Provenance",
    "RasterOutput",
    "Recipe",
    "RecipeRequest",
    "ResolvedAssetModel",
    "ResolvedInput",
    "Step",
    "cache_key",
    "canonical_bytes",
    "document_bytes",
    "engine_versions",
    "input_version",
    "job_recipe_document",
    "loads_i_json",
    "parse_recipe",
    "parse_request",
    "recipe_from_data",
    "recipe_hash",
    "recipe_hosts",
    "run_key",
]

#: The one recipe version this core runs (§4.3). An incompatible change raises it.
RECIPE_VERSION = 1

#: Prefix of every hash, so a later change of method never silently hits old keys (§4.4).
HASH_METHOD = "c1"

#: I-JSON (RFC 7493): integers beyond this lose precision as a double.
_MAX_SAFE_INTEGER = 2**53 - 1

# STAC raster extension `data_type` values.
DataType = Literal[
    "int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64",
    "float16", "float32", "float64", "cint16", "cint32", "cfloat32", "cfloat64", "other",
]  # fmt: skip

Name = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")]
Text = Annotated[str, Field(min_length=1, max_length=256)]
Position = tuple[float, float]


class _Model(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)


class OperatorLookup(Protocol):
    """What :func:`parse_recipe` needs from a registry: the parameter model of one version."""

    def params_model(self, op: str, op_version: int) -> type[BaseModel]: ...


# --- AOI -------------------------------------------------------------------


def _check_ring(ring: Sequence[Position]) -> None:
    if len(ring) < 4 or ring[0] != ring[-1]:
        raise ValueError("a linear ring has at least four positions and is closed")
    for lon, lat in ring:
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            raise ValueError("a position lies outside longitude/latitude bounds")


class _Geometry(_Model):
    def _check_shape(self) -> None:
        try:
            geometry = shapely_shape(self.model_dump(mode="json"))
        except (ShapelyError, ValueError, TypeError):
            raise ValueError("the AOI is not a readable geometry") from None
        if geometry.is_empty or not geometry.is_valid:
            raise ValueError("the AOI is empty or not a valid geometry")


class Polygon(_Geometry):
    type: Literal["Polygon"]
    coordinates: list[list[Position]] = Field(min_length=1)

    @model_validator(mode="after")
    def _valid(self) -> Polygon:
        for ring in self.coordinates:
            _check_ring(ring)
        self._check_shape()
        return self


class MultiPolygon(_Geometry):
    type: Literal["MultiPolygon"]
    coordinates: list[list[list[Position]]] = Field(min_length=1)

    @model_validator(mode="after")
    def _valid(self) -> MultiPolygon:
        for polygon in self.coordinates:
            if not polygon:
                raise ValueError("a polygon has at least one ring")
            for ring in polygon:
                _check_ring(ring)
        self._check_shape()
        return self


Aoi = Annotated[Polygon | MultiPolygon, Field(discriminator="type")]


# --- steps and output --------------------------------------------------------


class Step(_Model):
    """One operator call. ``params`` are normalised by the operator's own model in parsing."""

    op: Name
    op_version: int = Field(ge=1)
    params: dict[str, JsonValue]


class RasterOutput(_Model):
    """A job's result: one COG."""

    kind: Literal["raster"]
    format: Literal["cog"]
    dtype: Literal["uint8", "uint16", "int16", "uint32", "int32", "float32", "float64"]


class CropOutput(_Model):
    """The crop (§10.1): described by the synchronous download, computed by the export job (M4-11a)."""

    kind: Literal["crop"]
    format: Literal["cog"]
    resolution_factor: int
    extent: Literal["bbox(aoi ∩ footprints)"]
    mask: Literal["file"]

    @model_validator(mode="after")
    def _known_factor(self) -> CropOutput:
        if self.resolution_factor not in RESOLUTION_FACTORS:
            raise ValueError(f"resolution_factor is one of {list(RESOLUTION_FACTORS)}")
        return self


Output = Annotated[RasterOutput | CropOutput, Field(discriminator="kind")]


# --- inputs ----------------------------------------------------------------


class InputVersion(_Model):
    """The version of one input at acceptance (§4.6): content checksum, ETag or item update time."""

    kind: Literal["file:checksum", "etag", "updated"]
    value: Text


class Band(_Model):
    """One band as the item describes it (``raster:bands`` or ``bands``)."""

    data_type: DataType | None
    nodata: float | Literal["nan", "inf", "-inf"] | None
    scale: float | None
    offset: float | None

    @property
    def scaled(self) -> bool:
        return self.scale is not None or self.offset is not None


class ResolvedAssetModel(_Model):
    """:class:`earthx.access.resolve.ResolvedAsset` as a strict model, field for field."""

    dataset_id: Text
    item_id: Text
    asset: Text
    reader: ReaderKind
    href: Annotated[str, Field(min_length=1, max_length=8192)]
    variable: Text | None
    crs: Text | None

    def to_asset(self) -> ResolvedAsset:
        """The dataclass the readers take; its own checks run again here."""
        return ResolvedAsset(**self.model_dump())


class ResolvedInput(_Model):
    """One asset of one item, resolved: where, which version, which bands, which scaling.

    ``scaling`` names the source of the physical values (F7a): ``item`` when the
    item's bands carry a scale or offset, otherwise ``store-cf`` for Zarr (the
    reader's generic CF decoding) and ``none`` for a COG.
    """

    asset: ResolvedAssetModel
    version: InputVersion | None
    bands: list[Band]
    scaling: Literal["item", "store-cf", "none"]
    gsd: Annotated[float, Field(gt=0)] | None

    @model_validator(mode="after")
    def _scaling_matches(self) -> ResolvedInput:
        item_scaled = any(band.scaled for band in self.bands)
        if item_scaled:
            expected = "item"
        else:
            expected = "store-cf" if self.asset.reader == "zarr" else "none"
        if self.scaling != expected:
            raise ValueError(f"scaling is {expected!r} for this input (adr/0014 §5.4)")
        return self


class InputRequest(_Model):
    """One input of an order: a dataset, its items in groups, and the asset keys to read."""

    name: Name
    dataset: Text
    groups: list[Annotated[list[Text], Field(min_length=1)]] = Field(min_length=1)
    assets: list[Text] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> InputRequest:
        items = [item for group in self.groups for item in group]
        if len(set(items)) != len(items):
            raise ValueError("an item appears more than once")
        if len(set(self.assets)) != len(self.assets):
            raise ValueError("an asset appears more than once")
        return self


class Footprint(_Model):
    """An item's footprint, its STAC ``geometry`` as the item gives it (M4-11a).

    Only the type is checked: the crop takes a footprint it cannot read as no footprint
    (``crop_rules.compute_crop_region``), and the export has to do the same.
    """

    type: Literal["Polygon", "MultiPolygon"]
    coordinates: JsonValue


class Input(InputRequest):
    """An input of a recipe: the order's input plus one resolved entry per item and asset.

    ``footprints`` (M4-11a) holds every item's footprint, ``None`` for an item without a
    usable one; the output ``crop`` needs them for its extent ``bbox(aoi ∩ footprints)``,
    any other output carries none. Left out of the dump when unset, so neither the hash
    nor the ``recipe.json`` of a raster recipe changes.
    """

    resolved: list[ResolvedInput] = Field(min_length=1)
    footprints: dict[str, Footprint | None] | None = None

    @model_validator(mode="after")
    def _complete(self) -> Input:
        wanted = [(item, asset) for group in self.groups for item in group for asset in self.assets]
        have = [(entry.asset.item_id, entry.asset.asset) for entry in self.resolved]
        if sorted(have) != sorted(wanted):
            raise ValueError("resolved holds exactly one entry per item and asset")
        if any(entry.asset.dataset_id != self.dataset for entry in self.resolved):
            raise ValueError("a resolved asset belongs to another dataset")
        if self.footprints is not None and set(self.footprints) != {item for group in self.groups for item in group}:
            raise ValueError("footprints holds exactly one entry per item")
        return self

    @model_serializer(mode="wrap")
    def _without_unset_footprints(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        if data.get("footprints") is None:
            data.pop("footprints", None)
        return data


class _Common(_Model):
    # `int`, not `Literal[1]`: a literal compares by equality and takes `1.0` and `true`.
    recipe_version: int
    aoi: Aoi
    steps: list[Step]
    output: Output

    @model_validator(mode="after")
    def _known_version(self) -> _Common:
        if self.recipe_version != RECIPE_VERSION:
            raise ValueError(f"recipe_version {RECIPE_VERSION} is the only one this core runs")
        return self

    def _unique_inputs(self, inputs: Sequence[InputRequest]) -> None:
        names = [entry.name for entry in inputs]
        if len(set(names)) != len(names):
            raise ValueError("input names are unique")


class RecipeRequest(_Common):
    """The order (§4.1): what someone asks for, without any address.

    ``aoi`` may be left out for a raster job: the order then asks for the whole scenes it
    names, and `api` puts the union of their footprints into the recipe (M4-12); an export
    needs the area it cuts out, which `api` checks. The recipe itself always carries an AOI,
    so the core and the hash do not change.
    """

    inputs: list[InputRequest] = Field(min_length=1)
    aoi: Aoi | None = Field(
        default=None,
        description="The area to cut out, a Polygon or MultiPolygon in EPSG:4326. Left out, a raster job covers the "
        "whole scenes it names (the union of their footprints); an export needs it.",
    )

    @model_validator(mode="after")
    def _names(self) -> RecipeRequest:
        self._unique_inputs(self.inputs)
        return self


class Recipe(_Common):
    """The accepted recipe (§4.1, §4.2): what the core runs and what is hashed.

    ``recipe_id`` is the random identifier `api` gives every order (F15,
    adr/0013 §9 point 2). It is never part of the hash.
    """

    inputs: list[Input] = Field(min_length=1)
    recipe_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{22}$")] | None = None

    @model_validator(mode="after")
    def _names(self) -> Recipe:
        self._unique_inputs(self.inputs)
        crop = isinstance(self.output, CropOutput)
        if any((entry.footprints is not None) != crop for entry in self.inputs):
            raise ValueError("a crop carries the footprints of its items, any other output none")
        return self

    def hrefs(self) -> list[str]:
        """Every address the recipe reads, in order; for the read factory, never for a log."""
        return [entry.asset.href for item in self.inputs for entry in item.resolved]


class AppliedScaling(_Model):
    """The scaling the core applied to one input asset, and where it came from (F7a)."""

    input: Name
    asset: Text
    source: Literal["item", "store-cf", "none"]
    scales: list[float]
    offsets: list[float]


class Provenance(_Model):
    """How a result came about (§4.1). Never hashed, never part of a cache key."""

    execution: Literal["cloud", "local"]
    kind: Literal["job", "sync-download"]
    runner_version: Text | None
    self_attested: bool
    engine: dict[str, str]
    scaling: list[AppliedScaling]
    started: datetime | None
    finished: datetime | None
    attribution: list[str]

    @model_validator(mode="after")
    def _local_is_self_attested(self) -> Provenance:
        if self.self_attested != (self.execution == "local"):
            raise ValueError("a local result is self_attested, a cloud result is not (Q12)")
        return self


# --- parsing -----------------------------------------------------------------


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RecipeInvalid(f"duplicate key {key[:64]!r}")
        result[key] = value
    return result


def _reject_constant(name: str) -> Any:
    raise RecipeInvalid(f"{name} is not a JSON number (I-JSON)")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise RecipeInvalid("a number lies outside the range of a double (I-JSON)")
    return value


def _safe_int(text: str) -> int:
    value = int(text)
    if abs(value) > _MAX_SAFE_INTEGER:
        raise RecipeInvalid("an integer lies outside ±(2**53-1) (I-JSON)")
    return value


def _check_i_json(raw: bytes | str) -> None:
    """§4.4 step 1: everything ``json.loads`` would otherwise collapse silently."""
    loads_i_json(raw)


def loads_i_json(raw: bytes | str) -> Any:
    """A JSON document as Python data, with the checks of §4.4 step 1.

    For the caller that has to look inside a document before it hands the order on (`api`
    unwraps the OGC envelope): the same duplicate keys, ``NaN`` and out-of-range numbers
    are refused as :class:`RecipeInvalid`, and no value is named in the text.
    """
    try:
        return json.loads(
            raw,
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
            parse_int=_safe_int,
        )
    except RecipeInvalid:
        raise
    except (ValueError, TypeError):
        raise RecipeInvalid("not a JSON document") from None


def _invalid(error: ValidationError, what: str) -> RecipeInvalid:
    """The validation errors as locations and types only — never the offending values."""
    reasons = "; ".join(
        f"{'.'.join(str(part) for part in entry['loc']) or '(root)'}: {entry['type']}" for entry in error.errors()[:10]
    )
    return RecipeInvalid(f"invalid {what}: {reasons}")


def _validate[M: BaseModel](model: type[M], raw: bytes | str, what: str) -> M:
    _check_i_json(raw)
    try:
        return model.model_validate_json(raw, strict=True)
    except ValidationError as error:
        raise _invalid(error, what) from None


def _normalise_steps[M: _Common](document: M, operators: OperatorLookup) -> M:
    """Each step's ``params`` as its operator's own model dumps them (``1`` → ``1.0`` for a float)."""
    steps = []
    for index, step in enumerate(document.steps):
        try:
            model = operators.params_model(step.op, step.op_version)
        except LookupError:
            raise UnknownOperator(
                f"step {index}: operator {step.op!r} version {step.op_version} is not available"
            ) from None
        try:
            params = model.model_validate_json(json.dumps(step.params, allow_nan=False), strict=True)
        except ValidationError as error:
            raise _invalid(error, f"parameters of step {index} ({step.op})") from None
        steps.append(step.model_copy(update={"params": params.model_dump(mode="json")}))
    return document.model_copy(update={"steps": steps})


def parse_request(raw: bytes | str, operators: OperatorLookup) -> RecipeRequest:
    """An order from JSON text, validated, with normalised step parameters."""
    return _normalise_steps(_validate(RecipeRequest, raw, "order"), operators)


def parse_recipe(raw: bytes | str, operators: OperatorLookup) -> Recipe:
    """A recipe from JSON text, validated, with normalised step parameters."""
    return _normalise_steps(_validate(Recipe, raw, "recipe"), operators)


def recipe_from_data(data: Mapping[str, Any], operators: OperatorLookup) -> Recipe:
    """A recipe from Python data, through the same JSON path as :func:`parse_recipe`."""
    try:
        raw = json.dumps(data, allow_nan=False)
    except (ValueError, TypeError):
        raise RecipeInvalid("the recipe is not JSON data") from None
    return parse_recipe(raw, operators)


# --- canonical form, hash, cache key ----------------------------------------


def _positive_zero(value: Any) -> Any:
    if isinstance(value, float):
        return 0.0 if value == 0.0 else value
    if isinstance(value, dict):
        return {key: _positive_zero(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_positive_zero(item) for item in value]
    return value


def canonical_bytes(data: Any) -> bytes:
    """Method ``c1`` (§4.4 rules 2–7) over JSON data as ``model_dump(mode="json")`` gives it."""
    text = json.dumps(
        _positive_zero(data),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return text.encode("utf-8")


def _digest(data: Any) -> str:
    return f"{HASH_METHOD}:{hashlib.sha256(canonical_bytes(data)).hexdigest()}"


def _core(recipe: Recipe) -> dict[str, Any]:
    return recipe.model_dump(mode="json", exclude={"recipe_id"})


def recipe_hash(recipe: Recipe) -> str:
    """The hash of the recipe's core (§4.5): inputs with versions and bands, AOI, steps, output."""
    return _digest(_core(recipe))


def engine_versions() -> dict[str, str]:
    """What else decides a result besides the recipe (§4.5 variant E2, condition F3)."""
    return {
        "earthx": earthx.__version__,
        "gdal": rasterio.__gdal_version__,
        "rasterio": rasterio.__version__,
        "numexpr": metadata.version("numexpr"),
        "numpy": numpy.__version__,
    }


def run_key(recipe: Recipe, engine: Mapping[str, str] | None = None) -> str:
    """The key under which equal orders share one run (adr/0013 §5.1), versions or not.

    The same digest as :func:`cache_key`, but also for a recipe whose inputs carry no
    version: orders placed at the same time still attach to one active run, they just
    never become a cache hit for a later one (Q11). Internal like the hash (Q8).
    """
    return _digest({"engine": dict(engine if engine is not None else engine_versions()), "recipe": _core(recipe)})


def cache_key(recipe: Recipe, engine: Mapping[str, str] | None = None) -> str | None:
    """The internal cache key, or ``None`` when an input carries no version (Q11)."""
    if any(entry.version is None for item in recipe.inputs for entry in item.resolved):
        return None
    return run_key(recipe, engine)


def recipe_hosts(recipe: Recipe) -> tuple[str, ...]:
    """The hosts the recipe reads, sorted: what the queue counts per source (adr/0013 §5.7).

    :class:`~earthx.readers.errors.AssetRejected` when an address names no host.
    """
    return tuple(sorted(hosts_for(recipe.hrefs())))


def input_version(item: Mapping[str, Any], asset: str, *, etag: str | None = None) -> InputVersion | None:
    """The version of one item asset in the order of F4: checksum, then ETag, then ``updated``.

    Pure: the ETag, where one is needed, is fetched by `api` through `gateway` and
    handed in. ``asset`` is the key on the item, for Zarr the group side of it.
    """
    assets = item.get("assets")
    entry = assets.get(asset) if isinstance(assets, Mapping) else None
    checksum = entry.get("file:checksum") if isinstance(entry, Mapping) else None
    if isinstance(checksum, str) and checksum:
        return InputVersion(kind="file:checksum", value=checksum)
    if etag:
        return InputVersion(kind="etag", value=etag)
    properties = item.get("properties")
    updated = properties.get("updated") if isinstance(properties, Mapping) else None
    if isinstance(updated, str) and updated:
        return InputVersion(kind="updated", value=updated)
    return None


# --- recipe.json of a job ------------------------------------------------------


def document_bytes(document: Mapping[str, Any]) -> bytes:
    """UTF-8, two spaces, keys sorted: ``recipe.json``, the person's own file, no hash input."""
    return (json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def job_recipe_document(
    body: Mapping[str, Any],
    *,
    attribution: Sequence[str],
    result: Mapping[str, Any],
    started: datetime | None,
    finished: datetime | None,
) -> bytes:
    """``recipe.json`` of a job: its own recipe and the provenance of the cloud run (adr/0014 §10.1).

    One function for both copies (M4-11 K4): the link `api` serves and the file the
    export writes into its ZIP. ``body`` is the job's own recipe with its own
    ``recipe_id``; ``result`` is what the run reported (engine versions, scaling).
    """
    provenance = Provenance(
        execution="cloud",
        kind="job",
        runner_version=None,
        self_attested=False,
        engine=dict(result.get("engine") or {}),
        scaling=[AppliedScaling.model_validate(entry) for entry in result.get("scaling") or []],
        started=started,
        finished=finished,
        attribution=list(attribution),
    )
    return document_bytes({**body, "provenance": provenance.model_dump(mode="json")})
