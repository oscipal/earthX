"""A materialize run that sees changes per unit of the source (M5-58, adr/0038 §3.3–§3.5).

For an entry with ``updates.detect: units``. The adapter lists the groups of the source, each asked conditionally,
and the units of every group that changed (:class:`~earthx.adapters.spec.ListUnits`); this module decides per unit
whether it changed, has the adapter build the contributions of the new and changed ones, and writes only the items
whose assets change. The rest of :mod:`earthx.discovery.materialize` stays the way of ``detect: whole``.

**A unit changed** when its state or address differs, or by the first of these that both the listing and the stored
state name: ``file:checksum``, ETag, Last-Modified. Otherwise the source is asked: a ``HEAD`` with ``If-None-Match`` on
the stored ETag, else with ``If-Modified-Since``, else the SHA-256 of the unit itself (up to the size limit of
``gateway``). A group answered "unchanged" keeps its units as stored, without a request for any of them.

**The rule per (item, asset)** over every unit that contributes to it (adr/0038 §3.4): the higher state holds; of two
equal states the younger Last-Modified; a lower state never replaces a higher one. When the unit that holds goes, the
next one left holds and is built anew; when none is left the asset goes, and an item without assets is deleted.

Nothing commits here: the run is one transaction, the caller's (``discovery.materialize``).
"""

from __future__ import annotations

import copy
import hashlib
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

import psycopg

from earthx.adapters import UnsupportedSource, UpstreamShapeError
from earthx.adapters.spec import AdapterSpecs
from earthx.catalog.pgstac import upsert_items
from earthx.catalog.registry import ChangeDetection, DatasetConfig, ItemState
from earthx.catalog.source_units import (
    BuiltUnit,
    Contribution,
    Pair,
    SourceUnit,
    StoredUnit,
    Validators,
    delete_items,
    read_groups,
    read_items,
    read_units,
    write_state,
)
from earthx.gateway import Gateway, host_of

_EARLIEST = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class UnitsOutcome:
    """What one run did, for the run log and the line ``main`` prints."""

    status: str
    source_version: str
    listed: int
    units_new: int
    units_changed: int
    units_unchanged: int
    units_gone: int
    items_written: int
    items_deleted: int
    items_replaced: int


def _rank(unit: StoredUnit) -> tuple[int, datetime, str]:
    """The order of adr/0038 §3.4: state first, then the younger Last-Modified; the key only makes it total."""
    return (unit.state.rank, unit.validators.modified_at or _EARLIEST, unit.key)


def holder(pair: Pair, units: Iterable[StoredUnit]) -> StoredUnit | None:
    """The unit whose contribution the asset ``pair`` carries, or ``None`` where no unit contributes to it."""
    candidates = [unit for unit in units if pair in unit.contributes]
    return max(candidates, key=_rank, default=None)


async def unchanged(gateway: Gateway, unit: SourceUnit, stored: StoredUnit) -> tuple[bool, Validators]:
    """Whether ``unit`` is still what ``stored`` was, and the validators to keep (adr/0038 §3.3)."""
    if unit.state is not stored.state or unit.href != stored.href:
        return False, unit.validators
    listed, known = unit.validators, stored.validators
    kept = Validators(
        etag=listed.etag or known.etag,
        last_modified=listed.last_modified or known.last_modified,
        checksum=listed.checksum or known.checksum,
        content_sha256=known.content_sha256,
    )
    for field in ("checksum", "etag", "last_modified"):
        now, before = getattr(listed, field), getattr(known, field)
        if now and before:
            return now == before, kept
    if known.etag or known.last_modified:
        condition = {"if-none-match": known.etag} if known.etag else {"if-modified-since": str(known.last_modified)}
        response = await gateway.head(unit.href, headers=condition)
        etag, modified = response.headers.get("etag"), response.headers.get("last-modified")
        # A server that overhears the condition and answers 200 still tells by the validator it names.
        same = response.status_code == 304 or (
            (etag == known.etag) if known.etag and etag else bool(known.last_modified and modified == known.last_modified)
        )
        return same, replace(kept, etag=kept.etag or etag, last_modified=kept.last_modified or modified)
    body = (await gateway.get(unit.href)).content
    digest = hashlib.sha256(body).hexdigest()
    return digest == known.content_sha256, replace(kept, content_sha256=digest)


def _check_listing(
    config: DatasetConfig,
    known_groups: Mapping[str, str | None],
    groups: Mapping[str, str | None],
    unchanged_groups: frozenset[str],
    units: tuple[SourceUnit, ...],
) -> None:
    if not unchanged_groups <= set(groups):
        raise UpstreamShapeError(f"{config.dataset_id}: a group answered unchanged that the source no longer lists")
    if not unchanged_groups <= set(known_groups):
        # Its units would never be built: "unchanged" needs a stored state to stay as it is.
        raise UpstreamShapeError(f"{config.dataset_id}: a group answered unchanged that a run has never seen")
    keys = [unit.key for unit in units]
    if len(set(keys)) != len(keys):
        raise UpstreamShapeError(f"{config.dataset_id}: the source lists a unit twice")
    for unit in units:
        if unit.group not in groups or unit.group in unchanged_groups:
            raise UpstreamShapeError(f"{config.dataset_id}: a unit of a group that is not listed as changed")
        if unit.state not in config.updates.states:
            raise UpstreamShapeError(f"{config.dataset_id}: a unit in state {unit.state.value}, which the entry does not name")
        if not unit.href.startswith("https://") or host_of(unit.href) not in config.source.asset_hosts:
            raise UpstreamShapeError(f"{config.dataset_id}: a unit lies outside the asset hosts of the entry")


def _check_built(config: DatasetConfig, wanted: list[SourceUnit], built: tuple[BuiltUnit, ...]) -> None:
    if [unit.key for unit in built] != [unit.key for unit in wanted]:
        raise UpstreamShapeError(f"{config.dataset_id}: the adapter built other units than it was asked for")
    for unit in built:
        pairs = [contribution.pair for contribution in unit.contributions]
        if len(set(pairs)) != len(pairs):
            raise UpstreamShapeError(f"{config.dataset_id}: a unit contributes twice to one asset")
        for contribution in unit.contributions:
            item = contribution.item
            if not contribution.item_id or not contribution.asset_key or "assets" in item:
                raise UpstreamShapeError(f"{config.dataset_id}: a contribution without item id or asset key")
            if item.get("id") != contribution.item_id or item.get("collection") != config.dataset_id:
                raise UpstreamShapeError(f"{config.dataset_id}: a contribution names another item or collection")


def _item_state(item: Mapping[str, Any]) -> ItemState | None:
    value = item.get("properties", {}).get("earthx:state")
    return ItemState(value) if value in {state.value for state in ItemState} else None


def _assemble(
    config: DatasetConfig,
    stored: dict[str, Any] | None,
    changes: Mapping[str, tuple[Contribution, ItemState] | None],
) -> dict[str, Any] | None:
    """The item after ``changes`` (asset key → the contribution that holds now, or ``None`` for "gone")."""
    item = copy.deepcopy(stored) if stored is not None else None
    for asset_key, change in sorted(changes.items()):
        if change is None:
            if item is not None:
                item.get("assets", {}).pop(asset_key, None)
            continue
        contribution, state = change
        frame = copy.deepcopy(dict(contribution.item))
        if item is None:
            item = {**frame, "assets": {}}
        else:
            properties = {**item.get("properties", {}), **frame.pop("properties", {})}
            item.update(frame)
            item["properties"] = properties
        asset = copy.deepcopy(dict(contribution.asset))
        if len(config.updates.states) > 1:
            asset["earthx:state"] = state.value
        item.setdefault("assets", {})[asset_key] = asset
    if item is None or not item.get("assets"):
        return None
    properties = item.setdefault("properties", {})
    if len(config.updates.states) > 1:
        states = [ItemState(asset["earthx:state"]) for asset in item["assets"].values() if "earthx:state" in asset]
        properties["earthx:state"] = min(states, key=lambda state: state.rank).value if states else ItemState.FINAL.value
    updated = [str(asset["updated"]) for asset in item["assets"].values() if asset.get("updated")]
    if updated:
        properties["updated"] = max(updated)
    return item


async def run_units(
    conn: psycopg.Connection, config: DatasetConfig, *, adapters: AdapterSpecs, gateway: Gateway
) -> UnitsOutcome:
    """One run of an entry with ``updates.detect: units``."""
    if config.updates.detect is not ChangeDetection.UNITS:
        raise UnsupportedSource(f"{config.dataset_id} is materialized per run, not per unit")
    spec = adapters.get(config.source.adapter)
    if spec is None or spec.units is None:
        raise UnsupportedSource(f"{config.dataset_id}: {config.source.adapter} lists no units of its source")
    now = datetime.now(UTC)
    before = read_units(conn, config.dataset_id)

    known_groups = read_groups(conn, config.dataset_id)
    listing = await spec.units.list_units(config, gateway=gateway, known_groups=known_groups)
    groups, unchanged_groups = dict(listing.groups), frozenset(listing.unchanged_groups)
    _check_listing(config, known_groups, groups, unchanged_groups, listing.units)

    after: dict[str, StoredUnit] = {key: unit for key, unit in before.items() if unit.group in unchanged_groups}
    if any(unit.key in after for unit in listing.units):
        raise UpstreamShapeError(f"{config.dataset_id}: a unit is listed in a changed group and an unchanged one")
    to_build: list[SourceUnit] = []
    kept, new = len(after), 0
    for unit in listing.units:
        stored = before.get(unit.key)
        if stored is None:
            new += 1
            to_build.append(unit)
            continue
        same, validators = await unchanged(gateway, unit, stored)
        if same:
            kept += 1
            after[unit.key] = replace(stored, group=unit.group, validators=validators)
        else:
            to_build.append(replace(unit, validators=validators))
    changed = len(to_build) - new
    gone = set(before) - set(after) - {unit.key for unit in to_build}

    built: dict[str, BuiltUnit] = {}

    async def build(units: list[SourceUnit]) -> None:
        if not units:
            return
        result = await spec.units.build(config, gateway=gateway, units=units)
        _check_built(config, units, result)
        for unit, made in zip(units, result, strict=True):
            built[unit.key] = made
            # The listing's own values first, so that the next run compares listing with listing (one form of ETag,
            # one form of date); what reading showed fills only what the listing does not name.
            validators = Validators(
                etag=unit.validators.etag or made.validators.etag,
                last_modified=unit.validators.last_modified or made.validators.last_modified,
                checksum=unit.validators.checksum or made.validators.checksum,
                content_sha256=unit.validators.content_sha256 or made.validators.content_sha256,
            )
            after[unit.key] = StoredUnit(
                key=unit.key,
                group=unit.group,
                href=unit.href,
                state=unit.state,
                validators=validators,
                contributes=frozenset(contribution.pair for contribution in made.contributions),
                changed_at=now,
            )

    await build(to_build)

    touched: set[Pair] = set()
    for key in gone | set(built):
        if key in before:
            touched |= before[key].contributes
        if key in after:
            touched |= after[key].contributes
    for key, unit in after.items():
        # An unchanged unit whose file grew younger may now hold over another of its state (review of PR 1).
        if key in before and key not in built and unit.validators.modified_at != before[key].validators.modified_at:
            touched |= unit.contributes

    # A unit that holds an asset now but did not before, and was not built in this run, is built anew (§3.4 point 4).
    # Built anew, it may contribute to fewer assets than before; those are touched too, and so on until nothing moves.
    while True:
        fallback: dict[str, SourceUnit] = {}
        for pair in touched:
            now_holder, previous = holder(pair, after.values()), holder(pair, before.values())
            if now_holder is None or now_holder.key in built:
                continue
            if previous is None or previous.key != now_holder.key:
                fallback[now_holder.key] = now_holder.as_listed()
        if not fallback:
            break
        await build(list(fallback.values()))
        for key in fallback:
            touched |= before[key].contributes | after[key].contributes

    changes: dict[str, dict[str, tuple[Contribution, ItemState] | None]] = defaultdict(dict)
    for pair in sorted(touched):
        item_id, asset_key = pair
        now_holder = holder(pair, after.values())
        if now_holder is None:
            changes[item_id][asset_key] = None
        elif now_holder.key in built:
            contribution = next(c for c in built[now_holder.key].contributions if c.pair == pair)
            changes[item_id][asset_key] = (contribution, now_holder.state)

    stored_items = read_items(conn, config, changes)
    written: list[dict[str, Any]] = []
    emptied: list[str] = []
    replaced = 0
    for item_id, item_changes in sorted(changes.items()):
        old = stored_items.get(item_id)
        item = _assemble(config, old, item_changes)
        if item is None:
            if old is not None:
                emptied.append(item_id)
            continue
        if item == old:
            continue
        previous, current = (_item_state(old) if old else None), _item_state(item)
        if previous is not None and current is not None and current.rank > previous.rank:
            replaced += 1
        written.append(item)

    items_written = upsert_items(conn, config, written) if written else 0
    items_deleted = delete_items(conn, config, emptied) if emptied else 0
    write_state(conn, config.dataset_id, groups=groups, units=after.values(), seen_at=now)
    digest = hashlib.sha256(repr(sorted((key, value or "") for key, value in groups.items())).encode()).hexdigest()
    status = "loaded" if (new or changed or gone or written or emptied) else "unchanged"
    return UnitsOutcome(
        status=status,
        source_version=f"units:sha256:{digest}",
        listed=len(after),
        units_new=new,
        units_changed=changed,
        units_unchanged=kept,
        units_gone=len(gone),
        items_written=items_written,
        items_deleted=items_deleted,
        items_replaced=replaced,
    )


__all__ = ["UnitsOutcome", "holder", "run_units", "unchanged"]
