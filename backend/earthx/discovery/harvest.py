"""The run command of the harvest (M5-19; docs/plans/m5/m5-19-harvest-kern.md).

    python -m earthx.discovery.harvest <source_id> [--full] [--reextract]

One run fetches the listing of one source of ``backend/catalog/sources/`` through the gateway, keeps the raw answer
and its hash per find, and extracts each new or changed find into its intermediate form (plan §5). Nothing becomes
visible: listing, licence and approval are M5-20. Like ``materialize`` it runs by hand, under the compose profile
``harvest``, never with a plain ``docker compose up``, and never from CI or a cloud session (adr/0025 §8, adr/0002).

Every request goes through :func:`~earthx.discovery.source_gateway.open_source_gateway`: turns, places and breaker per
host are shared with every other run and instance (M5-37), ``robots.txt`` is obeyed (adr/0025 §6.2). A run holds its
source through its row with a lease it renews after every page (plan A1). :func:`run_harvest` is the whole run against
an open connection and an open gateway; :func:`main` builds them.

``--reextract`` derives the intermediate form anew from the kept raw answers, without a request (plan A4). ``--full``
asks for the whole listing where a source knows an incremental one (CKAN, PR 2); a STAC listing is always whole.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import psycopg

from earthx.catalog.datasets import registry
from earthx.catalog.harvest_store import (
    MAX_RAW_BYTES,
    HarvestBusy,
    Previous,
    RunCounts,
    canonical,
    count_finds,
    finish_run,
    list_validators,
    mark_gone,
    previous,
    raw_records,
    renew_run,
    save_list_validators,
    seen,
    start_run,
    write_find,
)
from earthx.catalog.hosts import HostLimit
from earthx.catalog.registry import ConfigError
from earthx.catalog.sources import SourceConfig, SourceProtocol, read_sources
from earthx.discovery.extract import Invalid, ShapeError, extracted_sha256
from earthx.discovery.source_gateway import open_source_gateway
from earthx.discovery.stac import StacListing, extract_collection, stac_pages
from earthx.gateway import (
    Gateway,
    GatewayError,
    GatewayResponse,
    HostResting,
    Policy,
    RobotsDisallowed,
    UrlRejected,
    user_agent_from_env,
)
from earthx.logging import configure_logging

__all__ = ["HarvestResult", "main", "run_harvest"]


class _BudgetSpent(Exception):
    pass


@dataclass(frozen=True, slots=True)
class HarvestResult:
    run_id: int
    status: str
    stop_reason: str | None
    counts: RunCounts


class _Fetcher:
    """Every request of a run: counted, and refused once the source's budget per run is spent."""

    def __init__(self, gateway: Gateway, counts: RunCounts, budget: int) -> None:
        self._gateway, self._counts, self._budget = gateway, counts, budget

    async def __call__(self, url: str, *, headers: Mapping[str, str] | None = None) -> GatewayResponse:
        if self._counts.requests >= self._budget:
            raise _BudgetSpent
        self._counts.requests += 1
        response = await self._gateway.get(url, headers=headers)
        self._counts.bytes += len(response.content)
        if response.status_code == 304:
            self._counts.not_modified += 1
        return response


def _record(
    cur: psycopg.Cursor,
    source: SourceConfig,
    run_id: int,
    counts: RunCounts,
    key: str,
    document: Any,
    before: Previous | None,
    *,
    raw: bytes | None,
    raw_sha256: str,
) -> None:
    """Extract one new or changed find and write it."""
    state, reason, extracted, digest, extent = "extracted", None, None, None, None
    try:
        if raw is not None and len(raw) > MAX_RAW_BYTES:
            raise Invalid("too_large")
        if not isinstance(document, dict):
            raise Invalid("shape")
        found = extract_collection(key, document, source)
        extracted, digest, extent = found.to_document(), extracted_sha256(found), found.extent_known
    except Invalid as invalid:
        state, reason = "invalid", invalid.reason
    if before is None or before.state == "gone":
        counts.found_new += 1
    elif before.state == state and before.extracted_sha256 == digest:
        counts.found_unchanged += 1
    else:
        counts.found_changed += 1
    if state == "invalid":
        counts.invalid += 1
    write_find(
        cur,
        run_id=run_id,
        source_id=source.source_id,
        key=key,
        raw=raw,
        raw_sha256=raw_sha256,
        state=state,
        reason=reason,
        extracted=extracted,
        extracted_sha256=digest,
        extent_known=extent,
        before=None if before is None else before.state,
    )


async def _fetch_and_extract(
    conn: psycopg.Connection, source: SourceConfig, run_id: int, fetch: _Fetcher, counts: RunCounts
) -> None:
    listing = StacListing()
    async for page in stac_pages(fetch, source, list_validators(conn, source.source_id), listing):
        keys = [key for key, _ in page if key is not None]
        counts.invalid += len(page) - len(keys)
        if len(set(keys)) != len(keys):
            raise ShapeError("a page names a collection twice")
        known = previous(conn, source.source_id, keys)
        with conn.transaction(), conn.cursor() as cur:
            for key, document in page:
                if key is None:
                    continue
                raw = canonical(document)
                digest = hashlib.sha256(raw).hexdigest()
                before = known.get(key)
                if before is not None and before.raw_sha256 == digest and before.state != "gone":
                    seen(cur, run_id=run_id, source_id=source.source_id, key=key)
                    counts.found_unchanged += 1
                else:
                    _record(cur, source, run_id, counts, key, document, before, raw=raw, raw_sha256=digest)
        renew_run(conn, run_id)
    if listing.not_modified:
        counts.found_unchanged = count_finds(conn, source.source_id)[0]
        return
    if listing.complete:
        counts.gone = mark_gone(conn, run_id=run_id, source_id=source.source_id)
        if listing.validators is not None:
            save_list_validators(conn, source.source_id, listing.validators)


def _reextract(conn: psycopg.Connection, source: SourceConfig, run_id: int, counts: RunCounts) -> None:
    batch: list[tuple[str, bytes]] = []

    def flush() -> None:
        known = previous(conn, source.source_id, [key for key, _ in batch])
        with conn.transaction(), conn.cursor() as cur:
            for key, raw in batch:
                before = known[key]
                _record(
                    cur, source, run_id, counts, key, json.loads(raw), before, raw=None, raw_sha256=before.raw_sha256
                )
        renew_run(conn, run_id)
        batch.clear()

    for key, raw, _ in raw_records(conn, source.source_id):
        batch.append((key, raw))
        if len(batch) >= 500:
            flush()
    if batch:
        flush()


async def run_harvest(
    conn: psycopg.Connection, source: SourceConfig, *, gateway: Gateway | None, reextract: bool = False
) -> HarvestResult:
    """One run of ``source``; ``conn`` in autocommit. :class:`HarvestBusy` while another run holds the source."""
    if source.protocol is not SourceProtocol.STAC_API:
        raise ConfigError(f"{source.source_id}: the protocol {source.protocol.value} comes with M5-19 PR 2")
    run_id = start_run(conn, source.source_id, "reextract" if reextract else "full")
    counts = RunCounts()
    status, stop_reason = "done", None
    try:
        if reextract:
            _reextract(conn, source, run_id, counts)
        else:
            assert gateway is not None
            await _fetch_and_extract(
                conn, source, run_id, _Fetcher(gateway, counts, source.max_requests_per_run), counts
            )
    except HostResting:
        status, stop_reason = "interrupted", "host_resting"
    except RobotsDisallowed:
        status, stop_reason = "interrupted", "robots"
    except UrlRejected:
        # A next page off the source's host or otherwise refused before it was sent: the listing is not readable.
        status, stop_reason = "failed", "shape"
    except _BudgetSpent:
        status, stop_reason = "interrupted", "request_budget"
    except ShapeError:
        status, stop_reason = "failed", "shape"
    except GatewayError:
        status, stop_reason = "failed", "upstream"
    except BaseException:
        finish_run(conn, run_id, status="failed", stop_reason="error", counts=counts)
        raise
    counts.extent_unknown = count_finds(conn, source.source_id)[1]
    finish_run(conn, run_id, status=status, stop_reason=stop_reason, counts=counts)
    return HarvestResult(run_id, status, stop_reason, counts)


def _policy_for(source: SourceConfig, hosts: Mapping[str, HostLimit]) -> Policy:
    """The source's host alone, with its limits from hosts.yaml (M5-36), and robots.txt obeyed (adr/0025 §6.2)."""
    limit = hosts[source.host]
    return Policy(
        allowed_hosts=frozenset({source.host}),
        host_connections={source.host: limit.connections},
        host_intervals={} if limit.interval_s is None else {source.host: limit.interval_s},
        obey_robots=True,
    )


_STOP_TEXT = {
    "host_resting": "der Host ruht (Unterbrecher oder Platz zu weit weg)",
    "robots": "robots.txt verbietet den Abruf",
    "request_budget": "Obergrenze der Anfragen je Lauf erreicht",
    "shape": "Antwort der Quelle nicht lesbar",
    "upstream": "Quelle antwortet mit Fehler oder nicht",
}


def report(source_id: str, result: HarvestResult) -> str:
    """The run report on the console: German, numbers only, no address, no key of a find (plan A6)."""
    c = result.counts
    lines = [
        f"{source_id}: Lauf {result.run_id} {result.status}"
        + (f" ({_STOP_TEXT[result.stop_reason]})" if result.stop_reason else ""),
        f"  Anfragen {c.requests}, davon 304: {c.not_modified}; {c.bytes / 1e6:.1f} MB",
        f"  Funde neu {c.found_new}, geändert {c.found_changed}, unverändert {c.found_unchanged},"
        f" ungültig {c.invalid}, weg {c.gone}",
        f"  Ausdehnung unbekannt (alle Funde der Quelle): {c.extent_unknown}",
    ]
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harvest one source of the seed (M5-19).")
    parser.add_argument("source_id", help="a source of backend/catalog/sources/, e.g. fsdi-stac")
    parser.add_argument("--full", action="store_true", help="the whole listing where the source has an incremental one")
    parser.add_argument("--reextract", action="store_true", help="extract again from the kept raw answers, no request")
    return parser.parse_args(argv)


async def _main_async(source: SourceConfig, hosts: Mapping[str, HostLimit], *, reextract: bool) -> HarvestResult:
    with psycopg.connect(autocommit=True) as conn:
        if reextract:
            return await run_harvest(conn, source, gateway=None, reextract=True)
        async with open_source_gateway(_policy_for(source, hosts)) as gateway:
            return await run_harvest(conn, source, gateway=gateway)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    configure_logging()
    try:
        user_agent_from_env()
        sources = read_sources()
        hosts = registry().host_limits
    except (ValueError, ConfigError) as error:
        print(f"harvest failed: {error}", file=sys.stderr)
        return 1
    source = sources.get(args.source_id)
    if source is None:
        print(f"harvest failed: no source {args.source_id!r} in backend/catalog/sources/", file=sys.stderr)
        return 1
    if not source.enabled:
        print(f"harvest failed: the source {args.source_id!r} is held (enabled: false)", file=sys.stderr)
        return 1
    try:
        result = asyncio.run(_main_async(source, hosts, reextract=args.reextract))
    except (HarvestBusy, ConfigError, psycopg.Error) as error:
        print(f"harvest failed: {error}", file=sys.stderr)
        return 1
    print(report(source.source_id, result))
    return 0 if result.status == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
