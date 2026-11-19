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

A run that loaded a new source version of a dataset with ``viewer.overview: pyramid`` also asks for its overview
pyramid (:func:`~earthx.catalog.pgstac.request_overview`), in the same transaction. An unchanged run asks for nothing but
confirms the pyramid of that version (:func:`~earthx.catalog.pgstac.confirm_overview`): the worker then extends its term.
Until the `harvester` takes over the schedule (M5-24) the command runs by hand; a pyramid whose version nobody confirms
expires (adr/0032 §5.3). Any successful run, unchanged or loaded (``--force`` included), also makes a pyramid of that
version that failed for good or expired buildable again (:func:`~earthx.catalog.pgstac.rearm_overview`): "the next
successful run builds anew" (adr/0032 §5).

Connection details come from the environment (``PGHOST`` and friends), like
``catalog.load``. ``--force`` skips the "unchanged" check and reloads
regardless of the last recorded source version.

An entry with ``updates.detect: units`` (M5-58, adr/0038) takes another way: :mod:`earthx.discovery.materialize_units`
judges each unit of the source on its own and writes only the items whose assets change; ``--force`` does not apply.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone

import psycopg

from earthx.adapters import (
    ADAPTER_SPECS,
    AdapterSpecs,
    MaterializeOutcome,
    UnsupportedSource,
    UpstreamShapeError,
    materialize_items,
)
from earthx.adapters.spec import UnitsMaterializer, spec_table
from earthx.catalog.datasets import registry
from earthx.catalog.hosts import HostLimit
from earthx.catalog.pgstac import (
    MaterializeRunRecord,
    PgstacError,
    check_pgstac_version,
    confirm_overview,
    delete_items_except,
    last_loaded_count,
    last_source_version,
    rearm_overview,
    record_materialize_run,
    request_overview,
    upsert_items,
    use_pgstac_search_path,
)
from earthx.catalog.registry import (
    AdapterKind,
    ChangeDetection,
    ConfigError,
    DatasetConfig,
    ItemHolding,
    OverviewMode,
    UnknownDatasetError,
)
from earthx.discovery import meteoswiss_grid
from earthx.discovery.materialize_units import UnitsOutcome, run_units
from earthx.discovery.source_gateway import open_source_gateway
from earthx.gateway import Gateway, GatewayError, Policy, host_of, user_agent_from_env
from earthx.logging import configure_logging

#: The adapter table with what only `discovery` can materialize: the MeteoSwiss grids, whose files `h5py` reads (M5-11),
#: per unit of the source (M5-58 PR 2).
MATERIALIZE_SPECS: AdapterSpecs = spec_table(
    *(spec for kind, spec in ADAPTER_SPECS.items() if kind is not AdapterKind.METEOSWISS_GRID),
    replace(
        ADAPTER_SPECS[AdapterKind.METEOSWISS_GRID],
        units=UnitsMaterializer(list_units=meteoswiss_grid.list_units, build=meteoswiss_grid.build_units),
    ),
)


@dataclass(frozen=True, slots=True)
class MaterializeResult:
    """What one run did — :attr:`outcome` is the adapter's own report (M3-11b
    plan §3.1); :attr:`items_written`/:attr:`items_deleted` are what actually
    changed in pgstac, which for an "unchanged" run is always zero and zero.
    """

    outcome: MaterializeOutcome
    items_written: int
    items_deleted: int
    #: What the run did to the overview pyramid of the version it saw, for a dataset that has one; printed by ``main``.
    pyramid: str | None = None
    #: What a run of ``updates.detect: units`` did per unit (M5-58); printed by ``main``.
    units: UnitsOutcome | None = None


async def _run_units(conn: psycopg.Connection, config: DatasetConfig, *, gateway: Gateway) -> MaterializeResult:
    """A run per unit of the source (adr/0038 §3.3); ``--force`` does not apply, the state per unit decides."""
    started_at = datetime.now(timezone.utc)
    units = await run_units(conn, config, adapters=MATERIALIZE_SPECS, gateway=gateway)
    record_materialize_run(
        conn,
        MaterializeRunRecord(
            dataset_id=config.dataset_id,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            status=units.status,
            source_version=units.source_version,
            items_written=units.items_written,
            items_deleted=units.items_deleted,
            listed=units.listed,
            missing=units.units_missing,
            withheld=0,
            units_new=units.units_new,
            units_changed=units.units_changed,
            units_unchanged=units.units_unchanged,
            units_gone=units.units_gone,
            items_replaced=units.items_replaced,
        ),
    )
    outcome = MaterializeOutcome(
        status=units.status,
        source_version=units.source_version,
        listed=units.listed,
        in_bucket=units.listed,
        missing=units.units_missing,
        withheld=0,
        unknown=0,
        items=(),
    )
    return MaterializeResult(
        outcome=outcome, items_written=units.items_written, items_deleted=units.items_deleted, units=units
    )


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
    if config.updates.detect is ChangeDetection.UNITS:
        return await _run_units(conn, config, gateway=gateway)
    known_version = None if force else last_source_version(conn, config.dataset_id)

    started_at = datetime.now(timezone.utc)
    outcome = await materialize_items(
        config,
        adapters=MATERIALIZE_SPECS,
        gateway=gateway,
        known_version=known_version,
        expected_items=last_loaded_count(conn, config.dataset_id),
    )
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
        if config.viewer is not None and config.viewer.overview is OverviewMode.PYRAMID:
            # The source still has the version the pyramid was built from: the worker may extend its term (adr/0032 §5.3).
            confirmed = confirm_overview(conn, config.dataset_id, outcome.source_version)
            rearmed = rearm_overview(conn, config.dataset_id, outcome.source_version)
            pyramid = "rebuild requested" if rearmed else "confirmed" if confirmed else "left as it is"
            return MaterializeResult(outcome=outcome, items_written=0, items_deleted=0, pyramid=pyramid)
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
    if config.viewer is not None and config.viewer.overview is OverviewMode.PYRAMID:
        # A new source version of a dataset with an overview pyramid: ask the worker for one (adr/0032 §5.2, F1).
        rearmed = rearm_overview(conn, config.dataset_id, outcome.source_version)
        request_overview(conn, config.dataset_id, outcome.source_version)
        pyramid = "rebuild requested" if rearmed else "requested"
        return MaterializeResult(outcome=outcome, items_written=written, items_deleted=deleted, pyramid=pyramid)
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


def _policy_for(config: DatasetConfig, hosts: Mapping[str, HostLimit]) -> Policy:
    """The endpoint's host plus the asset hosts — nothing wider (M3-11b plan §3.4),
    the same allowlist shape :func:`earthx.api.dependencies.policy_from_registry`
    builds for a whole registry, narrowed here to the one dataset this run touches.

    Caps and spacing per host come from the registry's hosts.yaml (M5-36): the FSDI pages about a thousand searches
    for swissALTI3D one second apart, about 17 minutes a run (M5-08 plan §4.2); the buckets keep no spacing. All runs
    of all instances share them through Postgres (M5-37, :mod:`earthx.discovery.source_gateway`).
    """
    allowed = frozenset({host_of(config.source.endpoint), *config.source.asset_hosts})
    limits = {host: limit for host, limit in hosts.items() if host in allowed}
    return Policy(
        allowed_hosts=allowed,
        host_connections={host: limit.connections for host, limit in limits.items()},
        host_intervals={host: limit.interval_s for host, limit in limits.items() if limit.interval_s is not None},
        host_read_timeouts={host: limit.timeout_s for host, limit in limits.items() if limit.timeout_s is not None},
    )


async def _main_async(config: DatasetConfig, hosts: Mapping[str, HostLimit], *, force: bool) -> MaterializeResult:
    with psycopg.connect(autocommit=False) as conn:
        async with open_source_gateway(_policy_for(config, hosts)) as gateway:
            result = await run_materialize(conn, config, gateway=gateway, force=force)
        conn.commit()
    return result


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    configure_logging()
    try:
        user_agent_from_env()
    except ValueError as error:
        print(f"materialize failed: {error}", file=sys.stderr)
        return 1

    try:
        datasets = registry()
        config = datasets.get(args.dataset_id)
    except ConfigError as error:
        print(f"materialize failed: {error}", file=sys.stderr)
        return 1
    except UnknownDatasetError:
        print(f"materialize failed: no dataset {args.dataset_id!r} in the registry", file=sys.stderr)
        return 1
    if config.source.item_holding is not ItemHolding.MATERIALIZED:
        print(f"materialize failed: {args.dataset_id!r} is not a materialized dataset", file=sys.stderr)
        return 1

    try:
        result = asyncio.run(_main_async(config, datasets.host_limits, force=args.force))
    except (PgstacError, psycopg.Error, GatewayError, UpstreamShapeError, UnsupportedSource) as error:
        print(f"materialize failed: {error}", file=sys.stderr)
        return 1

    outcome = result.outcome
    if result.units is not None:
        units = result.units
        print(
            f"{config.dataset_id}: {units.status}; {units.units_new} units new, {units.units_changed} changed, "
            f"{units.units_unchanged} unchanged, {units.units_gone} gone, "
            f"{units.units_missing} not served (asked again next run); {units.items_written} items written, "
            f"{units.items_replaced} replaced by a higher state, {units.items_deleted} deleted"
        )
        return 0
    if outcome.status == "unchanged":
        print(f"{config.dataset_id}: unchanged (source version {outcome.source_version})")
    else:
        print(
            f"{config.dataset_id}: loaded (source version {outcome.source_version}); "
            f"{result.items_written} items written, {result.items_deleted} deleted; "
            f"{outcome.listed} listed, {outcome.missing} missing, {outcome.withheld} withheld, "
            f"{outcome.unknown} unknown at the source"
        )
    if result.pyramid is not None:
        print(f"{config.dataset_id}: overview pyramid {result.pyramid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
