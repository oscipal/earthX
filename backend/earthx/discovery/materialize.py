"""The one-off materialize command (M3-11b).

    python -m earthx.discovery.materialize <dataset_id> [--force]

Loads — or confirms unchanged — the items of one *materialized* registry entry
into pgstac: the adapter builds them from the source's own listing
(:func:`earthx.adapters.materialize_items`), ``catalog`` writes them
(:func:`~earthx.catalog.pgstac.upsert_items`,
:func:`~earthx.catalog.pgstac.delete_items_except`). One transaction end to
end — either the database ends up matching the source, or it is left exactly
as it was (the posture :mod:`earthx.catalog.load` already takes).

:func:`run_materialize` is the whole run against an already-open connection
and an already-open gateway; :func:`main` is the thin CLI wrapper that builds
real infrastructure for it. The split exists so a test can exercise the run
against a synthetic, mocked bucket without going anywhere near a real network
call (CLAUDE.md: external sources only through ``tests/fixtures``).

Not one of the four processes of architekturplan.md 3.2 — like ``catalog.load``,
it is a step that prepares the catalogue, run by hand or through the compose
profile ``materialize`` (``docker compose run --rm materialize <dataset_id>``),
never by a plain ``docker compose up`` (M3-11b plan §3.7, F8): the source this
command reaches (e.g. ``copernicus-dem-30m.s3.amazonaws.com``) must never be
asked by CI or by an ordinary local start.

Connection details come from the environment (``PGHOST`` and friends), like
``catalog.load``. ``--force`` skips the "unchanged" check and reloads
regardless of the last recorded source version.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

import psycopg

from earthx.adapters import (
    MaterializeOutcome,
    UnsupportedSource,
    UpstreamShapeError,
    materialize_items,
)
from earthx.catalog.datasets import REGISTRY
from earthx.catalog.pgstac import (
    MaterializeRunRecord,
    PgstacError,
    check_pgstac_version,
    delete_items_except,
    last_source_version,
    record_materialize_run,
    upsert_items,
    use_pgstac_search_path,
)
from earthx.catalog.registry import DatasetConfig, ItemHolding, UnknownDatasetError
from earthx.gateway import Gateway, GatewayError, Policy, host_of


@dataclass(frozen=True, slots=True)
class MaterializeResult:
    """What one run did — :attr:`outcome` is the adapter's own report (M3-11b
    plan §3.1); :attr:`items_written`/:attr:`items_deleted` are what actually
    changed in pgstac, which for an "unchanged" run is always zero and zero.
    """

    outcome: MaterializeOutcome
    items_written: int
    items_deleted: int


async def run_materialize(
    conn: psycopg.Connection, config: DatasetConfig, *, gateway: Gateway, force: bool
) -> MaterializeResult:
    """The whole run: check the schema, ask the source, write what changed, log
    the run. Nothing here commits — that is the caller's, exactly like
    :func:`earthx.catalog.pgstac.load_registry` leaves it to
    :func:`earthx.catalog.load.main`.
    """
    check_pgstac_version(conn)
    use_pgstac_search_path(conn)
    known_version = None if force else last_source_version(conn, config.dataset_id)

    started_at = datetime.now(timezone.utc)
    outcome = await materialize_items(config, gateway=gateway, known_version=known_version)
    finished_at = datetime.now(timezone.utc)

    if outcome.status == "unchanged":
        record_materialize_run(
            conn,
            MaterializeRunRecord(
                dataset_id=config.dataset_id,
                started_at=started_at,
                finished_at=finished_at,
                status="unchanged",
                source_version=outcome.source_version,
                items_written=0,
                items_deleted=0,
                listed=0,
                missing=0,
                withheld=0,
            ),
        )
        return MaterializeResult(outcome=outcome, items_written=0, items_deleted=0)

    written = upsert_items(conn, config, outcome.items)
    deleted = delete_items_except(conn, config, (item["id"] for item in outcome.items))
    record_materialize_run(
        conn,
        MaterializeRunRecord(
            dataset_id=config.dataset_id,
            started_at=started_at,
            finished_at=finished_at,
            status="loaded",
            source_version=outcome.source_version,
            items_written=written,
            items_deleted=deleted,
            listed=outcome.listed,
            missing=outcome.missing,
            withheld=outcome.withheld,
        ),
    )
    return MaterializeResult(outcome=outcome, items_written=written, items_deleted=deleted)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize one dataset's items into pgstac (M3-11b).")
    parser.add_argument("dataset_id", help="the registry entry to materialize, e.g. cop-dem-glo-30")
    parser.add_argument(
        "--force",
        action="store_true",
        help="reload even if the source's own version has not changed since the last recorded run",
    )
    return parser.parse_args(argv)


def _policy_for(config: DatasetConfig) -> Policy:
    """The endpoint's host plus the asset hosts — nothing wider (M3-11b plan §3.4),
    the same allowlist shape :func:`earthx.api.dependencies.policy_from_registry`
    builds for a whole registry, narrowed here to the one dataset this run touches.
    """
    return Policy(allowed_hosts=frozenset({host_of(config.source.endpoint), *config.source.asset_hosts}))


async def _main_async(config: DatasetConfig, *, force: bool) -> MaterializeResult:
    with psycopg.connect(autocommit=False) as conn:
        async with Gateway(_policy_for(config)) as gateway:
            result = await run_materialize(conn, config, gateway=gateway, force=force)
        conn.commit()
    return result


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    try:
        config = REGISTRY.get(args.dataset_id)
    except UnknownDatasetError:
        print(f"materialize failed: no dataset {args.dataset_id!r} in the registry", file=sys.stderr)
        return 1
    if config.source.item_holding is not ItemHolding.MATERIALIZED:
        print(f"materialize failed: {args.dataset_id!r} is not a materialized dataset", file=sys.stderr)
        return 1

    try:
        result = asyncio.run(_main_async(config, force=args.force))
    except (PgstacError, psycopg.Error, GatewayError, UpstreamShapeError, UnsupportedSource) as error:
        print(f"materialize failed: {error}", file=sys.stderr)
        return 1

    outcome = result.outcome
    if outcome.status == "unchanged":
        print(f"{config.dataset_id}: unchanged (source version {outcome.source_version})")
    else:
        print(
            f"{config.dataset_id}: loaded (source version {outcome.source_version}); "
            f"{result.items_written} items written, {result.items_deleted} deleted; "
            f"{outcome.listed} listed, {outcome.missing} missing, {outcome.withheld} withheld, "
            f"{outcome.unknown} unknown prefixes in the bucket"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
