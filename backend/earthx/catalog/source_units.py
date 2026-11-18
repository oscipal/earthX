"""The units of a source and their state in Postgres (M5-58, adr/0038 §3.3–§3.5).

A **unit** is the smallest thing at which a source shows a change (a file, an entry of a listing), a **group** the
listing document that names it (a source item, a page). An adapter of ``updates.detect: units`` lists them and builds
the **contributions** of the new and changed ones; ``discovery.materialize_units`` decides what changed and which
contribution holds. This module holds the shapes all three share and the tables of migration 029. Nothing here commits:
the transaction is the run's, like :func:`earthx.catalog.pgstac.upsert_items`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import psycopg

from earthx.catalog.registry import DatasetConfig, ItemState

Pair = tuple[str, str]


@dataclass(frozen=True, slots=True)
class Validators:
    """What tells one state of a unit from another: as a listing names them, as reading the unit showed them, or both."""

    etag: str | None
    last_modified: str | None
    checksum: str | None
    content_sha256: str | None

    @property
    def modified_at(self) -> datetime | None:
        """``last_modified`` as a time, for the rule "the younger of two equal states" (adr/0038 §3.4)."""
        if not self.last_modified:
            return None
        try:
            return parsedate_to_datetime(self.last_modified)
        except (TypeError, ValueError):
            pass
        # A listing may name the time as ISO 8601 (STAC `updated`) rather than as an HTTP date.
        try:
            moment = datetime.fromisoformat(self.last_modified.replace("Z", "+00:00"))
        except ValueError:
            return None
        return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


NO_VALIDATORS = Validators(etag=None, last_modified=None, checksum=None, content_sha256=None)


@dataclass(frozen=True, slots=True)
class SourceUnit:
    """One unit as the source lists it now."""

    key: str
    group: str
    # Where the core asks about the unit (HEAD), and where the adapter reads it: https on an asset host of the entry.
    href: str
    state: ItemState
    validators: Validators


@dataclass(frozen=True, slots=True)
class UnitListing:
    """What :class:`ListUnits` found: every group the source lists now with the validator to keep for it, the groups
    that answered "unchanged" (their units are as stored), and the units of all other groups."""

    groups: Mapping[str, str | None]
    unchanged_groups: frozenset[str]
    units: tuple[SourceUnit, ...]


@dataclass(frozen=True, slots=True)
class Contribution:
    """What one unit gives to one asset of one item. ``item`` is the item without ``assets``: id, collection,
    geometry, bbox, properties, links. An asset may carry ``updated``; the item's ``updated`` is the latest of them."""

    item_id: str
    asset_key: str
    asset: Mapping[str, Any]
    item: Mapping[str, Any]

    @property
    def pair(self) -> Pair:
        return (self.item_id, self.asset_key)


@dataclass(frozen=True, slots=True)
class BuiltUnit:
    """The contributions of one unit, and what reading it showed of its validators (an ETag, a Last-Modified)."""

    key: str
    contributions: tuple[Contribution, ...]
    validators: Validators


@dataclass(frozen=True, slots=True)
class StoredUnit:
    """One row of ``earthx_materialize_unit``."""

    key: str
    group: str
    href: str
    state: ItemState
    validators: Validators
    contributes: frozenset[Pair]
    changed_at: datetime

    def as_listed(self) -> SourceUnit:
        return SourceUnit(key=self.key, group=self.group, href=self.href, state=self.state, validators=self.validators)


def read_groups(conn: psycopg.Connection, dataset_id: str) -> dict[str, str | None]:
    with conn.cursor() as cur:
        cur.execute("SELECT group_key, validator FROM public.earthx_materialize_group WHERE dataset_id = %s", (dataset_id,))
        return {key: validator for key, validator in cur.fetchall()}


def read_units(conn: psycopg.Connection, dataset_id: str) -> dict[str, StoredUnit]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT unit_key, group_key, href, state, etag, last_modified, checksum, content_sha256, contributes, changed_at
            FROM public.earthx_materialize_unit WHERE dataset_id = %s
            """,
            (dataset_id,),
        )
        rows = cur.fetchall()
    return {
        key: StoredUnit(
            key=key,
            group=group,
            href=href,
            state=ItemState(state),
            validators=Validators(etag=etag, last_modified=modified, checksum=checksum, content_sha256=sha),
            contributes=frozenset((str(item_id), str(asset_key)) for item_id, asset_key in contributes),
            changed_at=changed_at,
        )
        for key, group, href, state, etag, modified, checksum, sha, contributes, changed_at in rows
    }


def write_state(
    conn: psycopg.Connection,
    dataset_id: str,
    *,
    groups: Mapping[str, str | None],
    units: Iterable[StoredUnit],
    seen_at: datetime,
) -> None:
    """Replace the state of ``dataset_id`` by ``groups`` and ``units``: what the source no longer lists goes."""
    units = list(units)
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM public.earthx_materialize_group WHERE dataset_id = %s AND NOT (group_key = ANY(%s))",
            (dataset_id, list(groups)),
        )
        cur.executemany(
            """
            INSERT INTO public.earthx_materialize_group (dataset_id, group_key, validator, seen_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (dataset_id, group_key) DO UPDATE SET validator = EXCLUDED.validator, seen_at = EXCLUDED.seen_at
            """,
            [(dataset_id, key, validator, seen_at) for key, validator in groups.items()],
        )
        cur.execute(
            "DELETE FROM public.earthx_materialize_unit WHERE dataset_id = %s AND NOT (unit_key = ANY(%s))",
            (dataset_id, [unit.key for unit in units]),
        )
        cur.executemany(
            """
            INSERT INTO public.earthx_materialize_unit
                (dataset_id, unit_key, group_key, href, state, etag, last_modified, checksum, content_sha256,
                 contributes, seen_at, changed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            ON CONFLICT (dataset_id, unit_key) DO UPDATE SET
                group_key = EXCLUDED.group_key, href = EXCLUDED.href, state = EXCLUDED.state, etag = EXCLUDED.etag,
                last_modified = EXCLUDED.last_modified, checksum = EXCLUDED.checksum,
                content_sha256 = EXCLUDED.content_sha256, contributes = EXCLUDED.contributes,
                seen_at = EXCLUDED.seen_at, changed_at = EXCLUDED.changed_at
            """,
            [
                (
                    dataset_id,
                    unit.key,
                    unit.group,
                    unit.href,
                    unit.state.value,
                    unit.validators.etag,
                    unit.validators.last_modified,
                    unit.validators.checksum,
                    unit.validators.content_sha256,
                    json.dumps(sorted(unit.contributes)),
                    seen_at,
                    unit.changed_at,
                )
                for unit in units
            ],
        )


def read_items(conn: psycopg.Connection, config: DatasetConfig, item_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """The stored items of ``config`` among ``item_ids``, whole (hydrated by pgstac), by id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.id, pgstac.get_item(i.id, i.collection) FROM pgstac.items i
            WHERE i.collection = %s AND i.id = ANY(%s)
            """,
            (config.dataset_id, sorted(set(item_ids))),
        )
        return {item_id: dict(item) for item_id, item in cur.fetchall()}


def delete_items(conn: psycopg.Connection, config: DatasetConfig, item_ids: Iterable[str]) -> int:
    """Delete these items of ``config``; the run's other half of writing only what changed (adr/0038 §3.4)."""
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM pgstac.items WHERE collection = %s AND id = ANY(%s)", (config.dataset_id, sorted(set(item_ids)))
        )
        return cur.rowcount


__all__ = [
    "NO_VALIDATORS",
    "BuiltUnit",
    "Contribution",
    "Pair",
    "SourceUnit",
    "StoredUnit",
    "UnitListing",
    "Validators",
    "delete_items",
    "read_groups",
    "read_items",
    "read_units",
    "write_state",
]
