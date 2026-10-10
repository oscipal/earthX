"""Order intake: from an order to the recipe a worker runs (adr/0014 §4.1, M4-07b).

`api` is the one place that sees items, the registry and the network at once, so it
is where an *order* — datasets, items, asset keys, AOI, steps, output, no address —
becomes a :class:`~earthx.processing.recipe.Recipe`. The routes that call this
(M4-08b, M4-14) come later; nothing here is a route.

:func:`accept_order` goes in stages, and each stage turns an order away before the
next one costs anything (the status in brackets):

1. the order parses and validates (422); it carries no address and no ``recipe_id``
   (400, F1), a job wants a raster output or a crop — an export, without steps and at
   native resolution (422, M4-11a);
2. its size is within the caps (413, 422) — no network yet;
3. the dataset exists (422), its licence reaches *processing* (403, B11), every step
   is an operator this platform runs as a job and ``applicable`` to this dataset
   (422) — still no network;
4. the items are fetched through the item source (422 for one the source lacks,
   502/503/504 for the source's own failures);
5. a group the AOI does not touch drops out, as in the crop (M3-17); none left is
   422;
6. each asset is resolved (:func:`~earthx.access.resolve.resolve_asset`), its host
   checked against the ``asset_hosts`` of **its own dataset** (502, adr/0014 §8), its
   bands, scaling source and ground sample distance read off the item (adr/0014
   §5.4, F7);
7. each input gets its version (adr/0014 §4.6, F4): the checksum, else — for a COG —
   the ETag of a ``HEAD`` through `gateway`, else the item's ``updated``. A source
   that cannot say leaves the version empty, and with it the cache (Q11);
8. an export (M4-11a) carries the footprints of its items, is refused above 5 GB by
   the cost estimate (413, F5) and for a Zarr dataset (422, F6), and gets the side
   files of its ZIP (:func:`export_attachments`).

:func:`estimate_order` stops after stage 6: the cost estimate needs the recipe, not the
versions, so it makes no ``HEAD`` and gives the recipe no ``recipe_id`` (M4-13a). What only
stage 7 finds — an asset the source no longer has — is therefore not found by an estimate.

Nothing here logs an AOI, an address or a hash (adr/0014 §4.7); the texts of
:class:`OrderRefused` name fields, datasets, items and operators only.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import secrets
from collections.abc import Awaitable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from earthx.access.download import (
    AOI_FILENAME,
    CITATION_FILENAME,
    NOTICE_FILENAME,
    AoiOutsideItems,
    InvalidAoi,
    asset_gsd,
    attribution_text,
    build_notice_text,
    compute_crop_region,
    filter_items_intersecting_aoi,
    parse_aoi_geometry,
)
from earthx.access.resolve import (
    AssetNotOnItem,
    InvalidAssetKey,
    MalformedItem,
    NoReader,
    ResolvedAsset,
    resolve_asset,
)
from earthx.adapters import UnknownCollection, dataset_config
from earthx.api.citation import citation_bib
from earthx.api.item_source import ItemSource, OrderRefused, fetch_item_or_refuse, malformed_item_detail
from earthx.catalog.registry import DatasetConfig, DatasetRegistry, LicenseTier, UnknownDatasetError
from earthx.gateway import Gateway, GatewayError, Policy, UpstreamError, UrlRejected, UrlTooLong, inspect_url
from earthx.processing.errors import AoiOutsideInputs, ExportTooLarge, RecipeInvalid, UnknownOperator
from earthx.processing.export import Attachments
from earthx.processing.operators import OperatorRegistry, Tier, applicable
from earthx.processing.plan import check_bands, estimate
from earthx.processing.recipe import (
    Band,
    CropOutput,
    InputRequest,
    InputVersion,
    Provenance,
    RasterOutput,
    Recipe,
    RecipeRequest,
    cache_key,
    document_bytes,
    engine_versions,
    input_version,
    job_recipe_document,
    parse_request,
    recipe_from_data,
)
from earthx.readers.zarr_reader import split_asset_key

LOGGER = logging.getLogger("earthx.api.intake")

__all__ = [
    "MAX_ORDER_ASSETS",
    "MAX_ORDER_ITEMS",
    "MAX_ORDER_STEPS",
    "AcceptedOrder",
    "EstimatedOrder",
    "OrderRefused",
    "accept_order",
    "check_recipe_hosts",
    "crop_recipe_json",
    "describe_bands",
    "estimate_order",
    "export_attachments",
    "footprint_of",
    "job_recipe_json",
]

# The starting values of an order's size (Otto, M4-07b F5). One input per order until
# the licence of a combination is decided (architekturplan 7.1). M4-12 may raise the
# item cap, with its own reason: whole scenes per overpass are more than a crop's 25.
MAX_ORDER_ITEMS = 25
MAX_ORDER_ASSETS = 16
MAX_ORDER_STEPS = 16

# What a version may hold (`processing.recipe.Text`).
_ETAG_MAX_CHARS = 256

# The source says the object is not there (any more): the job would fail later.
_GONE = frozenset({404, 410})


@dataclass(frozen=True, slots=True)
class AcceptedOrder:
    """What an order became.

    ``skipped_items`` are the items of the order that the recipe leaves out because
    the AOI does not touch them (F4) — the answer must say so, or the recipe would
    hold fewer scenes than the person asked for without a word.
    """

    recipe: Recipe
    cacheable: bool
    skipped_items: tuple[str, ...]
    #: For an export only (M4-11a): the side files of its ZIP, built here because only `api`
    #: reads the registry and sees the origin of the AOI.
    attachments: Attachments | None = None


@dataclass(frozen=True, slots=True)
class EstimatedOrder:
    """An order as far as the estimate needs it: a recipe with no versions and no ``recipe_id``."""

    recipe: Recipe
    skipped_items: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Prepared:
    """Stages 1 to 6: the checked order, its dataset and one target per item and asset."""

    request: RecipeRequest
    entry: InputRequest
    config: DatasetConfig
    groups: list[list[str]]
    skipped: tuple[str, ...]
    targets: list[_Target]


async def accept_order(
    raw: bytes | str,
    *,
    registry: DatasetRegistry,
    operators: OperatorRegistry,
    item_source: ItemSource,
    gateway: Gateway,
    aoi_provenance: Mapping[str, str] | None = None,
) -> AcceptedOrder:
    """The order as a recipe with a ``recipe_id`` — or an :class:`OrderRefused` (module docstring).

    ``aoi_provenance`` (M4-11 F4) is where a place-search AOI came from (``attribution``,
    ``license``, ``source``), checked by the caller; it only goes into the side files of
    an export, never into the recipe or its hash.
    """
    try:
        accepted = await _accept(raw, registry, operators, item_source, gateway, aoi_provenance)
    except OrderRefused as refused:
        _log_refused(refused)
        raise
    recipe = accepted.recipe
    LOGGER.info(
        "order accepted",
        extra={
            "order_recipe_id": recipe.recipe_id,
            "order_dataset": recipe.inputs[0].dataset,
            "order_items": sum(len(group) for group in recipe.inputs[0].groups),
            "order_assets": len(recipe.inputs[0].assets),
            "order_operators": [step.op for step in recipe.steps],
            "order_cacheable": accepted.cacheable,
        },
    )
    return accepted


def _log_refused(refused: OrderRefused) -> None:
    LOGGER.info(
        "order refused",
        extra={"order_stage": refused.stage, "order_status": refused.status_code, "order_reason": refused.detail},
    )


async def estimate_order(
    raw: bytes | str,
    *,
    registry: DatasetRegistry,
    operators: OperatorRegistry,
    item_source: ItemSource,
    aoi_provenance: Mapping[str, str] | None = None,
) -> EstimatedOrder:
    """The order as a recipe for the cost estimate — or an :class:`OrderRefused` (module docstring).

    Stages 1 to 6 of :func:`accept_order`, then the same checks of hosts and band names
    on a recipe without versions. No request to an asset is made. ``aoi_provenance`` is
    only checked (an export's alone, M4-11 F4); an estimate builds no side files.
    """
    try:
        prepared = await _prepare(raw, registry, operators, item_source, aoi_provenance)
        recipe = _recipe_of(prepared, [None] * len(prepared.targets), None, registry, operators)
    except OrderRefused as refused:
        _log_refused(refused)
        raise
    LOGGER.info(
        "order estimated",
        extra={
            "order_dataset": recipe.inputs[0].dataset,
            "order_items": sum(len(group) for group in recipe.inputs[0].groups),
            "order_assets": len(recipe.inputs[0].assets),
            "order_operators": [step.op for step in recipe.steps],
        },
    )
    return EstimatedOrder(recipe, prepared.skipped)


async def _prepare(
    raw: bytes | str,
    registry: DatasetRegistry,
    operators: OperatorRegistry,
    item_source: ItemSource,
    aoi_provenance: Mapping[str, str] | None = None,
) -> _Prepared:
    _refuse_a_recipe(raw)
    try:
        request = parse_request(raw, operators)
    except RecipeInvalid as error:
        raise OrderRefused(422, str(error), "order") from None
    entry = _check_scope(request)
    export = isinstance(request.output, CropOutput)
    if aoi_provenance is not None and not export:
        raise OrderRefused(400, "aoiProvenance belongs to an export (the output crop) only", "order")

    try:
        config = dataset_config(registry, entry.dataset)
    except UnknownCollection:
        raise OrderRefused(422, f"no dataset {entry.dataset!r}", "dataset") from None
    if config.license.tier is not LicenseTier.PROCESSING:
        raise OrderRefused(
            403, f"the licence of {config.dataset_id!r} does not permit processing (KLAERUNGEN B11)", "license"
        )
    if export and config.zarr is not None:
        raise OrderRefused(422, "export jobs read COG assets only for now; this dataset is a Zarr store", "applicable")
    _check_steps(request, config, operators)

    ids = [item for group in entry.groups for item in group]
    fetched = await _gather(fetch_item_or_refuse(item_source, entry.dataset, item, not_found=422) for item in ids)
    items = dict(zip(ids, fetched, strict=True))
    groups, skipped = _groups_the_aoi_touches(entry.groups, items, request)

    policy = Policy(allowed_hosts=frozenset(config.source.asset_hosts))
    separator = config.zarr.variable_separator if config.zarr is not None else None
    targets = [
        _Target(items[item_id], _resolve_checked(items[item_id], config, asset, policy), separator, policy)
        for group in groups
        for item_id in group
        for asset in entry.assets
    ]
    return _Prepared(request, entry, config, groups, skipped, targets)


async def _accept(
    raw: bytes | str,
    registry: DatasetRegistry,
    operators: OperatorRegistry,
    item_source: ItemSource,
    gateway: Gateway,
    aoi_provenance: Mapping[str, str] | None = None,
) -> AcceptedOrder:
    prepared = await _prepare(raw, registry, operators, item_source, aoi_provenance)
    versions = await _gather(_version_of(target, gateway) for target in prepared.targets)
    recipe = _recipe_of(prepared, versions, secrets.token_urlsafe(16), registry, operators)
    if not isinstance(recipe.output, CropOutput):
        return AcceptedOrder(recipe, cache_key(recipe) is not None, prepared.skipped)
    try:
        estimate(recipe, operators)
    except ExportTooLarge as error:
        raise OrderRefused(413, str(error), "size") from None
    except AoiOutsideInputs as error:
        raise OrderRefused(422, str(error), "aoi") from None
    kept = {item_id for group in prepared.groups for item_id in group}
    attachments = export_attachments(
        prepared.config,
        recipe,
        dropped=[item_id for group in prepared.entry.groups if kept.isdisjoint(group) for item_id in group],
        aoi_provenance=aoi_provenance,
        accepted_at=datetime.now(UTC),
    )
    return AcceptedOrder(recipe, False, prepared.skipped, attachments)


def _recipe_of(
    prepared: _Prepared,
    versions: Sequence[InputVersion | None],
    recipe_id: str | None,
    registry: DatasetRegistry,
    operators: OperatorRegistry,
) -> Recipe:
    """The recipe of a prepared order, with its hosts and band names checked."""
    request, entry = prepared.request, prepared.entry
    data = {
        "recipe_version": request.recipe_version,
        "inputs": [
            {
                "name": entry.name,
                "dataset": entry.dataset,
                "groups": prepared.groups,
                "assets": entry.assets,
                "resolved": [
                    _resolved_json(target, version) for target, version in zip(prepared.targets, versions, strict=True)
                ],
                **(
                    {"footprints": {target.item["id"]: footprint_of(target.item) for target in prepared.targets}}
                    if isinstance(request.output, CropOutput)
                    else {}
                ),
            }
        ],
        "aoi": request.aoi.model_dump(mode="json"),
        "steps": [step.model_dump(mode="json") for step in request.steps],
        "output": request.output.model_dump(mode="json"),
    }
    if recipe_id is not None:
        data["recipe_id"] = recipe_id
    try:
        recipe = recipe_from_data(data, operators)
    except RecipeInvalid as error:
        # Only reachable when an item breaks a rule the recipe models state (a CRS
        # field of the wrong kind, say) — the source's mistake, not the caller's.
        raise OrderRefused(
            502, f"the items of {prepared.config.dataset_id!r} do not make a valid recipe: {error}", "recipe"
        ) from None
    check_recipe_hosts(recipe, registry)
    try:
        check_bands(recipe, operators)
    except RecipeInvalid as error:
        raise OrderRefused(422, str(error), "applicable") from None
    return recipe


def export_attachments(
    config: DatasetConfig,
    recipe: Recipe,
    *,
    dropped: Sequence[str],
    aoi_provenance: Mapping[str, str] | None,
    accepted_at: datetime,
) -> Attachments:
    """The side files of an export's ZIP, as the synchronous crop writes them (M4-11 F3, F4, K3).

    ``ATTRIBUTION.txt`` with the groups the recipe reads, the items of groups the AOI did
    not touch at all (the crop names only those, not single items left out of a group) and
    the origin of a place-search AOI; ``citation.bib`` dated the day of acceptance;
    ``aoi.geojson`` the AOI with that origin as ``properties``, like the crop's. And the
    attribution for the provenance of ``recipe.json``.
    """
    entry = recipe.inputs[0]
    aoi = recipe.aoi.model_dump(mode="json")
    if aoi_provenance:
        aoi = {**aoi, "properties": dict(aoi_provenance)}
    groups = [list(group) for group in entry.groups]
    notice = build_notice_text(
        config,
        item_ids=[item_id for group in groups for item_id in group],
        assets=list(entry.assets),
        group_item_ids=groups if len(groups) > 1 else None,
        skipped_item_ids=list(dropped),
        aoi_geometry=aoi,
    )
    attribution = attribution_text(config, year=accepted_at.year)
    return Attachments(
        files={
            NOTICE_FILENAME: notice,
            CITATION_FILENAME: citation_bib(config, downloaded=accepted_at.date()).decode("utf-8"),
            AOI_FILENAME: json.dumps(aoi),
        },
        attribution=(attribution,) if attribution else (),
    )


def _refuse_a_recipe(raw: bytes | str) -> None:
    """F1: an order carries no address. A recipe — resolved, with a ``recipe_id`` — is not one.

    Not re-resolved, not trusted: the person sends the order, and `api` makes the
    recipe. Plain ``json.loads`` is enough here; a document it cannot read goes on
    to :func:`parse_request`, which says why.
    """
    try:
        document = json.loads(raw)
    except (ValueError, TypeError):
        return
    if not isinstance(document, dict):
        return
    inputs = document.get("inputs")
    resolved = isinstance(inputs, list) and any(isinstance(entry, dict) and "resolved" in entry for entry in inputs)
    if resolved or "recipe_id" in document:
        raise OrderRefused(
            400,
            "send the order without addresses: no `resolved` and no `recipe_id`; the platform resolves it",
            "order",
        )


def _check_scope(request: RecipeRequest) -> InputRequest:
    """What an order may ask for, judged before anything is fetched (F5)."""
    if len(request.inputs) != 1:
        raise OrderRefused(422, "an order has exactly one input", "order")
    if isinstance(request.output, CropOutput):
        # An export (M4-11a): the source's own values at native resolution (K1).
        if request.steps:
            raise OrderRefused(422, "an export has no steps; it delivers the source's own values", "order")
        if request.output.resolution_factor != 1:
            raise OrderRefused(422, "an export job reads at native resolution only (resolution_factor 1)", "order")
    elif not isinstance(request.output, RasterOutput):
        raise OrderRefused(422, "an order for a job asks for a raster or a crop output", "order")
    if len(request.steps) > MAX_ORDER_STEPS:
        raise OrderRefused(422, f"an order has at most {MAX_ORDER_STEPS} steps", "size")
    entry = request.inputs[0]
    if len(entry.assets) > MAX_ORDER_ASSETS:
        raise OrderRefused(422, f"an order names at most {MAX_ORDER_ASSETS} assets", "size")
    count = sum(len(group) for group in entry.groups)
    if count > MAX_ORDER_ITEMS:
        raise OrderRefused(413, f"this order names {count} items; at most {MAX_ORDER_ITEMS} fit in one order", "size")
    return entry


def _check_steps(request: RecipeRequest, config: DatasetConfig, operators: OperatorRegistry) -> None:
    for index, step in enumerate(request.steps):
        try:
            operator = operators.operator(step.op, step.op_version)
        except UnknownOperator as error:
            raise OrderRefused(422, str(error), "applicable") from None
        if Tier.T2 not in operator.tiers:
            raise OrderRefused(422, f"step {index}: {step.op!r} does not run as a job", "applicable")
        params = operator.params.model_validate_json(json.dumps(step.params), strict=True)
        reasons = applicable(operator, config, params)
        if reasons:
            raise OrderRefused(422, f"step {index}: {step.op!r} cannot run here: {'; '.join(reasons)}", "applicable")


async def _gather[T](awaitables: Iterable[Awaitable[T]]) -> list[T]:
    """All of them, concurrently; the first failure *in order* is raised, so the answer is stable."""
    results = await asyncio.gather(*awaitables, return_exceptions=True)
    for result in results:
        if isinstance(result, BaseException):
            raise result
    return results  # type: ignore[return-value]


def _groups_the_aoi_touches(
    groups: Sequence[Sequence[str]], items: Mapping[str, dict[str, Any]], request: RecipeRequest
) -> tuple[list[list[str]], tuple[str, ...]]:
    """As the crop does (M3-17, F4): items the AOI does not touch drop out, a group with none drops entirely.

    Both the bbox of the item and, for the group as a whole, its real footprints
    count — a rotated scene whose bbox reaches the AOI but whose footprint does not
    is the case ``compute_crop_region`` exists for (M3-18 §13). An export judges by
    the footprints its recipe will carry (:func:`footprint_of`), so that the core
    never finds a group the AOI misses (review of M4-11a).
    """
    export = isinstance(request.output, CropOutput)
    try:
        aoi = parse_aoi_geometry(request.aoi.model_dump(mode="json"))
    except InvalidAoi as error:
        raise OrderRefused(422, str(error), "aoi") from None
    kept: list[list[str]] = []
    skipped: list[str] = []
    for group in groups:
        try:
            matched = filter_items_intersecting_aoi([items[item_id] for item_id in group], aoi)
        except (ValueError, TypeError):
            raise OrderRefused(502, "an item of the order carries a bbox that is not four numbers", "items") from None
        if matched:
            judged = [{"geometry": footprint_of(item)} for item in matched] if export else matched
            try:
                compute_crop_region(judged, aoi)
            except AoiOutsideItems:
                matched = []
        touched = {item["id"] for item in matched}
        skipped.extend(item_id for item_id in group if item_id not in touched)
        if touched:
            kept.append([item_id for item_id in group if item_id in touched])
    if not kept:
        raise OrderRefused(422, "the AOI does not touch any of the given items", "aoi")
    return kept, tuple(skipped)


@dataclass(frozen=True, slots=True)
class _Target:
    item: Mapping[str, Any]
    ref: ResolvedAsset
    separator: str | None
    policy: Policy

    @property
    def item_asset(self) -> str:
        """The key the item itself carries — the group side of a Zarr key."""
        return split_asset_key(self.ref.asset, self.separator)[0]


def _resolve_checked(item: Mapping[str, Any], config: DatasetConfig, asset: str, policy: Policy) -> ResolvedAsset:
    """:func:`resolve_asset`, then the address against this dataset's ``asset_hosts`` (adr/0014 §8)."""
    try:
        ref = resolve_asset(item, config, asset)
    except NoReader as error:
        raise OrderRefused(501, str(error), "resolve") from None
    except (InvalidAssetKey, AssetNotOnItem) as error:
        raise OrderRefused(422, str(error), "resolve") from None
    except MalformedItem as error:
        raise OrderRefused(502, str(error), "resolve") from None
    try:
        inspect_url(ref.href, policy)
    except (UrlRejected, UrlTooLong):
        raise OrderRefused(
            502, "the item points at a host this dataset does not declare (asset_hosts)", "hosts"
        ) from None
    return ref


def check_recipe_hosts(recipe: Recipe, registry: DatasetRegistry) -> None:
    """Every address of a recipe lies on the ``asset_hosts`` of its own dataset, or it is refused (adr/0014 §8).

    The intake calls it on what it just built; whoever takes a recipe from
    anywhere else — a queue row, a stored permalink — calls it before the recipe is
    run. A recipe is never passed on with an address nobody declared.
    """
    for entry in recipe.inputs:
        try:
            config = registry.get(entry.dataset)
        except UnknownDatasetError:
            raise OrderRefused(400, f"no dataset {entry.dataset!r}", "dataset") from None
        _check_hosts_of(recipe, config)


def _check_hosts_of(recipe: Recipe, config: DatasetConfig) -> None:
    """The addresses of the inputs of ``config``'s dataset, against its ``asset_hosts``."""
    policy = Policy(allowed_hosts=frozenset(config.source.asset_hosts))
    for entry in recipe.inputs:
        if entry.dataset != config.dataset_id:
            continue
        for resolved in entry.resolved:
            try:
                inspect_url(resolved.asset.href, policy)
            except (UrlRejected, UrlTooLong):
                raise OrderRefused(400, "the recipe names an address its dataset does not declare", "hosts") from None


# --- bands, scaling source, version ------------------------------------------


def _number(value: Any, what: str, item: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise OrderRefused(502, malformed_item_detail(item) + f" ({what} is not a finite number)", "bands")
    return float(value)


def _entries(asset_entry: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The band descriptions of an item asset: ``raster:bands`` (raster v1), else ``bands`` (STAC 1.1)."""
    for key in ("raster:bands", "bands"):
        found = asset_entry.get(key)
        if found is None:
            continue
        # A description that is not a list of objects is not skipped past: dropping an
        # entry shifts the bands behind it, and that is a silent change of numbers (K7).
        if not isinstance(found, list) or not all(isinstance(entry, Mapping) for entry in found):
            raise OrderRefused(
                502, f"the item describes its bands in a form this platform does not read ({key})", "bands"
            )
        if found:
            return list(found)
    return []


def _band(entry: Mapping[str, Any], item: str) -> Band:
    nodata = entry.get("nodata")
    if not isinstance(nodata, str):  # a string is "nan", "inf" or "-inf", or the model refuses it
        nodata = _number(nodata, "nodata", item)
    try:
        return Band(
            data_type=entry.get("data_type"),
            nodata=nodata,
            scale=_number(entry.get("scale", entry.get("raster:scale")), "scale", item),
            offset=_number(entry.get("offset", entry.get("raster:offset")), "offset", item),
        )
    except ValidationError:
        raise OrderRefused(502, malformed_item_detail(item) + " (a band is not described correctly)", "bands") from None


_NO_BAND = Band(data_type=None, nodata=None, scale=None, offset=None)


def _bands_of(target: _Target) -> list[Band]:
    """The bands of one resolved asset, as the item describes them (adr/0014 §5.4, F7, M4-07b F3).

    A COG asset keeps its list as it is. A Zarr asset is addressed per variable
    (``SR_10m:b04,b08``): by name where the entries have names; one entry without
    names describes the whole asset and holds for every variable (that is how the EOPF
    adapter normalises); anything else is an empty description, and the store's own
    CF attributes decide the scaling. The item says nothing it does not say.
    """
    item_id = str(target.item.get("id"))
    entry = target.item["assets"][target.item_asset]
    entries = _entries(entry)
    if target.ref.reader == "cog":
        return [_band(raw, item_id) for raw in entries]
    names = [raw["name"] for raw in entries if isinstance(raw.get("name"), str)]
    if len(set(names)) != len(names):
        raise OrderRefused(502, malformed_item_detail(item_id) + " (two bands share a name)", "bands")
    named = {raw["name"]: raw for raw in entries if isinstance(raw.get("name"), str)}
    bands = []
    for name in target.ref.variable.split(",") if target.ref.variable else [None]:
        if named:
            raw = named.get(name) if name is not None else None
        else:
            raw = entries[0] if len(entries) == 1 else None
        bands.append(_band(raw, item_id) if raw is not None else _NO_BAND)
    return bands


def _scaling_of(target: _Target, bands: Sequence[Band]) -> str:
    if any(band.scaled for band in bands):
        return "item"
    return "store-cf" if target.ref.reader == "zarr" else "none"


def describe_bands(item: Mapping[str, Any], config: DatasetConfig, ref: ResolvedAsset) -> tuple[list[Band], str]:
    """The bands the item describes for ``ref`` and where their scaling comes from (``item``, ``store-cf``, ``none``).

    The one reading of ``raster:bands`` the job and the tile share (adr/0014 §5.4,
    F7): a tile that scaled differently from a job would break their agreement.
    Raises :class:`OrderRefused` (502) for a description it cannot read.
    """
    separator = config.zarr.variable_separator if config.zarr is not None else None
    target = _Target(item, ref, separator, Policy(allowed_hosts=frozenset(config.source.asset_hosts)))
    bands = _bands_of(target)
    return bands, _scaling_of(target, bands)


def _usable_etag(value: str | None) -> str | None:
    """A strong ETag that fits; a weak one says "equivalent", not "identical" (RFC 9110 §8.8.1)."""
    if not value or value.startswith("W/") or len(value) > _ETAG_MAX_CHARS:
        return None
    return value


def _version(item: Mapping[str, Any], key: str, *, etag: str | None = None) -> InputVersion | None:
    """:func:`input_version`, where a value the model refuses (over 256 characters) is the source's mistake."""
    try:
        return input_version(item, key, etag=etag)
    except ValidationError:
        raise OrderRefused(
            502, malformed_item_detail(str(item.get("id"))) + " (a version is not usable)", "version"
        ) from None


async def _version_of(target: _Target, gateway: Gateway) -> InputVersion | None:
    """The version of one input (adr/0014 §4.6, F4; M4-07b F2, F6).

    A ``HEAD`` is asked only of a COG with no ``file:checksum``: a Zarr address is a
    group of many objects, and an ETag on it would not describe the data. A source
    that says the object is gone (404, 410) refuses the order — the job would fail
    later anyway. Any other failure leaves the version empty: no cache hit, a
    warning without the address, the order goes on.
    """
    key = target.item_asset
    own = _version(target.item, key)
    if (own is not None and own.kind == "file:checksum") or target.ref.reader != "cog":
        return own
    try:
        response = await gateway.head(target.ref.href, within=target.policy)
    except UpstreamError as error:
        if error.status_code in _GONE:
            raise OrderRefused(
                502,
                f"an input of the order is no longer at its source ({target.ref.dataset_id}/{target.ref.item_id})",
                "version",
            ) from None
        _warn_no_version(target, error)
        return None
    except GatewayError as error:
        _warn_no_version(target, error)
        return None
    return _version(target.item, key, etag=_usable_etag(response.headers.get("etag")))


def _warn_no_version(target: _Target, error: GatewayError) -> None:
    LOGGER.warning(
        "no version for an input; the result will not be cached",
        extra={
            "order_dataset": target.ref.dataset_id,
            "order_item": target.ref.item_id,
            "order_asset": target.ref.asset,
            "order_error": type(error).__name__,
            "order_upstream_status": getattr(error, "status_code", None),
        },
    )


def _resolved_json(target: _Target, version: InputVersion | None) -> dict[str, Any]:
    bands = _bands_of(target)
    return {
        "asset": target.ref.to_json(),
        "version": None if version is None else version.model_dump(mode="json"),
        "bands": [band.model_dump(mode="json") for band in bands],
        "scaling": _scaling_of(target, bands),
        "gsd": asset_gsd(target.item, target.item_asset),
    }


# --- recipe.json of the synchronous crop (adr/0014 §10.1) --------------------


def footprint_of(item: Mapping[str, Any]) -> dict[str, Any] | None:
    """The item's ``geometry`` for the recipe of a crop, or ``None`` where it is no polygon (M4-11a).

    The crop's extent takes a footprint it cannot read as none (``compute_crop_region``);
    a geometry of another type is no footprint either, so the recipe says ``null``.
    """
    geometry = item.get("geometry")
    if isinstance(geometry, Mapping) and geometry.get("type") in ("Polygon", "MultiPolygon"):
        return {"type": geometry["type"], "coordinates": geometry.get("coordinates")}
    return None


def crop_recipe_json(
    config: DatasetConfig,
    *,
    groups: Sequence[Sequence[Mapping[str, Any]]],
    assets: Sequence[str],
    aoi: Mapping[str, Any],
    resolution_factor: int,
    accepted_at: datetime,
) -> bytes:
    """``recipe.json`` for the ZIP of a crop, as bytes (M4-14 puts it in).

    The same schema as a job's recipe, ``steps: []``, the output described as the
    crop it is (§10.1). ``groups`` are the items the crop actually reads, already
    filtered by the AOI; each is resolved and its address checked like an order's.
    Versions are those that need no request — the checksum, ``updated`` — so a DEM
    tile carries ``null``: a ``HEAD`` per tile for a side file is not worth it, and
    Q11 concerns the cache, which a crop has none of. No ``recipe_id`` (a crop is
    not stored, D3), no hash; ``provenance`` says how it came about.

    Bytes, so that `access.download` can write the file without importing
    `processing`; it is the person's own file, so the AOI is in it, like in
    ``aoi.geojson``.
    """
    policy = Policy(allowed_hosts=frozenset(config.source.asset_hosts))
    separator = config.zarr.variable_separator if config.zarr is not None else None
    targets = [
        _Target(item, _resolve_checked(item, config, asset, policy), separator, policy)
        for group in groups
        for item in group
        for asset in assets
    ]
    data = {
        "recipe_version": 1,
        "inputs": [
            {
                "name": "input",
                "dataset": config.dataset_id,
                "groups": [[item["id"] for item in group] for group in groups],
                "assets": list(assets),
                "resolved": [_resolved_json(target, _version(target.item, target.item_asset)) for target in targets],
                "footprints": {item["id"]: footprint_of(item) for group in groups for item in group},
            }
        ],
        # The geometry alone: a place-search AOI carries `properties` for the notice and
        # `aoi.geojson`, and the recipe model forbids them (M4-07b review).
        "aoi": {key: aoi[key] for key in ("type", "coordinates") if key in aoi},
        "steps": [],
        "output": {
            "kind": "crop",
            "format": "cog",
            "resolution_factor": resolution_factor,
            "extent": "bbox(aoi ∩ footprints)",
            "mask": "file",
        },
    }
    try:
        recipe = recipe_from_data(data, OperatorRegistry())
    except RecipeInvalid as error:
        raise OrderRefused(
            502, f"the items of {config.dataset_id!r} do not make a valid recipe: {error}", "recipe"
        ) from None
    _check_hosts_of(recipe, config)
    attribution = attribution_text(config, year=accepted_at.year)
    provenance = Provenance(
        execution="cloud",
        kind="sync-download",
        runner_version=None,
        self_attested=False,
        engine=engine_versions(),
        scaling=[],
        started=accepted_at,
        finished=None,
        attribution=[attribution] if attribution else [],
    )
    document = {
        **recipe.model_dump(mode="json", exclude={"recipe_id"}),
        "provenance": provenance.model_dump(mode="json"),
    }
    return document_bytes(document)


def job_recipe_json(
    body: Mapping[str, Any],
    *,
    config: DatasetConfig | None,
    result: Mapping[str, Any],
    started: datetime | None,
    finished: datetime | None,
) -> bytes:
    """``recipe.json`` of a job, from the job's **own** recipe and what the run reported (adr/0014 §10.1).

    ``body`` is the recipe stored for this job, with its own ``recipe_id``: two equal orders share
    a run but never a recipe, so this file never shows another order's identifier (M4-08a F4). No
    hash. ``provenance`` is the cloud run: the versions and the scaling the core reported
    (``result``), the times of the run that computed it — for a cache hit those of the first
    order — and the attribution of the dataset, if the registry still knows it. The document
    itself is :func:`~earthx.processing.recipe.job_recipe_document`, which the export job also
    writes into its ZIP.
    """
    attribution = attribution_text(config, year=(finished or started or datetime.now(UTC)).year) if config else None
    return job_recipe_document(
        body, attribution=[attribution] if attribution else [], result=result, started=started, finished=finished
    )
