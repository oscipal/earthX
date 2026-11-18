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

``--reextract`` derives the intermediate form anew from the kept raw answers, without a request (plan A4). A CKAN source
is read incrementally (packages changed since the last done run, less an hour) unless ``--full`` is given or its last
full run lies ``full_every_days`` back; only a full run marks finds ``gone`` (A3). A STAC listing is always whole.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import psycopg

from earthx.catalog.datasets import registry
from earthx.catalog.harvest_store import (
    MAX_RAW_BYTES,
    HarvestBusy,
    Previous,
    RunCounts,
    SourceSummary,
    canonical,
    finish_run,
    last_runs,
    list_validators,
    mark_gone,
    previous,
    raw_records,
    renew_run,
    save_list_validators,
    seen,
    source_summary,
    start_run,
    write_find,
)
from earthx.catalog.hosts import HostLimit
from earthx.catalog.registry import ConfigError
from earthx.catalog.sources import SourceConfig, SourceProtocol, read_sources
from earthx.discovery.ckan import INCREMENTAL_OVERLAP, CkanListing, ckan_pages, extract_package
from earthx.discovery.extract import Extracted, Invalid, ShapeError, extracted_sha256, extractor_version
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


class _ListingMoved(Exception):
    """An incremental listing shifted while it was read: the run must not count as the last one."""


class _LeaseLost(Exception):
    """Another run closed this one after its term ran out; it writes nothing more."""


def _renew(conn: psycopg.Connection, run_id: int) -> None:
    if not renew_run(conn, run_id):
        raise _LeaseLost


_EXTRACTORS: Mapping[SourceProtocol, Callable[[str, Any, SourceConfig], Extracted]] = {
    SourceProtocol.STAC_API: extract_collection,
    SourceProtocol.CKAN: extract_package,
}


@dataclass(frozen=True, slots=True)
class HarvestResult:
    run_id: int
    #: ``full``, ``incremental`` or ``reextract``.
    kind: str
    status: str
    stop_reason: str | None
    counts: RunCounts
    #: The state of the source's finds after the run (Otto, 17.11.2026: the report says the state, not only this run).
    summary: SourceSummary
    #: Finds without a usable id: counted, never stored, since they have no key.
    without_key: int = 0
    #: Why a run that ended ``done`` did not look for finds that are gone: ``incremental``; ``listing_moved`` where a
    #: full CKAN listing shifted while it was read (a package may have been skipped); ``listing_empty`` where it named
    #: no package at all (a rebuilt index, a filter that no longer matches), which is no evidence that all are gone.
    gone_unchecked: str | None = None
    #: Whether the run read a path robots.txt disallows, under the exception of the source's file (Otto, 18.11.2026).
    robots_waived: bool = False


@dataclass(slots=True)
class _Run:
    conn: psycopg.Connection
    source: SourceConfig
    run_id: int
    kind: str
    #: The lower bound of ``metadata_modified`` of an incremental CKAN run.
    since: datetime | None
    counts: RunCounts
    version: str
    without_key: int = 0
    gone_unchecked: str | None = None


class _Fetcher:
    """Every request of a run: counted, and refused once the source's budget per run is spent."""

    def __init__(self, gateway: Gateway, counts: RunCounts, budget: int) -> None:
        self._gateway, self._counts, self._budget = gateway, counts, budget

    async def __call__(
        self, url: str, *, params: Mapping[str, str | int] | None = None, headers: Mapping[str, str] | None = None
    ) -> GatewayResponse:
        if self._counts.requests >= self._budget:
            raise _BudgetSpent
        self._counts.requests += 1
        response = await self._gateway.get(url, params=params, headers=headers)
        self._counts.bytes += len(response.content)
        if response.status_code == 304:
            self._counts.not_modified += 1
        return response


def _record(
    cur: psycopg.Cursor,
    run: _Run,
    key: str,
    document: Any,
    before: Previous | None,
    *,
    raw: bytes | None,
    raw_sha256: str,
) -> None:
    """Extract one find that is new, changed or outdated (another extractor version) and write it."""
    state, reason, extracted, digest, extent = "extracted", None, None, None, None
    try:
        if raw is not None and len(raw) > MAX_RAW_BYTES:
            raise Invalid("too_large")
        if not isinstance(document, dict):
            raise Invalid("shape")
        try:
            found = _EXTRACTORS[run.source.protocol](key, document, run.source)
        except (TypeError, ValueError, AttributeError, KeyError, IndexError, ArithmeticError, RecursionError):
            # One find of a foreign shape must not end the run for every other one (review of PR 1).
            raise Invalid("shape") from None
        extracted, digest, extent = found.to_document(), extracted_sha256(found), found.extent_known
    except Invalid as invalid:
        state, reason = "invalid", invalid.reason
    counts = run.counts
    if before is None or before.state == "gone":
        counts.found_new += 1
    elif (before.state, before.reason, before.extracted_sha256) == (state, reason, digest):
        counts.found_unchanged += 1
    else:
        counts.found_changed += 1
    write_find(
        cur,
        run_id=run.run_id,
        source_id=run.source.source_id,
        key=key,
        raw=raw,
        raw_sha256=raw_sha256,
        state=state,
        reason=reason,
        extracted=extracted,
        extracted_sha256=digest,
        extent_known=extent,
        extractor_version=run.version,
        before=None if before is None else (before.state, before.reason),
    )


def _listing(
    run: _Run, fetch: _Fetcher
) -> tuple[StacListing | CkanListing, AsyncIterator[list[tuple[str | None, Any]]]]:
    conn, source = run.conn, run.source
    if source.protocol is SourceProtocol.STAC_API:
        stac = StacListing()
        return stac, stac_pages(fetch, source, list_validators(conn, source.source_id), stac)
    ckan = CkanListing(full=run.kind == "full")
    return ckan, ckan_pages(fetch, source, run.since, ckan)


async def _fetch_and_extract(run: _Run, fetch: _Fetcher) -> None:
    conn, source = run.conn, run.source
    listing, pages = _listing(run, fetch)
    # A find that moves between pages while the listing is read comes twice; only its first answer counts.
    taken: set[str] = set()
    async for page in pages:
        finds = []
        for key, document in page:
            if key is None:
                run.without_key += 1
            elif key not in taken:
                taken.add(key)
                finds.append((key, document))
        known = previous(conn, source.source_id, [key for key, _ in finds])
        _renew(conn, run.run_id)
        with conn.transaction(), conn.cursor() as cur:
            for key, document in finds:
                raw = canonical(document)
                digest = hashlib.sha256(raw).hexdigest()
                before = known.get(key)
                if (
                    before is not None
                    and before.raw_sha256 == digest
                    and before.state != "gone"
                    and before.extractor_version == run.version
                ):
                    seen(cur, run_id=run.run_id, source_id=source.source_id, key=key)
                    run.counts.found_unchanged += 1
                else:
                    _record(cur, run, key, document, before, raw=raw, raw_sha256=digest)
    _renew(conn, run.run_id)
    if listing.not_modified:
        # The listing is unchanged as a whole, but finds an older extractor judged are judged again from their kept
        # raw answers (Otto, 17.11.2026); the others stay as they are.
        evaluated = _reextract(run, outdated_only=True)
        summary = source_summary(conn, source.source_id)
        run.counts.found_unchanged += summary.extracted + sum(summary.invalid.values()) - evaluated
        return
    if listing.complete:
        run.counts.gone = mark_gone(conn, run_id=run.run_id, source_id=source.source_id)
        if listing.validators is not None:
            save_list_validators(conn, source.source_id, listing.validators)
        return
    if not isinstance(listing, CkanListing):
        return
    if not listing.full:
        if listing.moved:
            # A package may be skipped; the next run must ask from the run before this one (A8).
            raise _ListingMoved
        # Finds the listing did not name are judged again if an older extractor judged them, from their kept raw
        # answers; a full run sees them all anyway.
        _reextract(run, outdated_only=True)
        run.gone_unchecked = "incremental"
    else:
        run.gone_unchecked = "listing_moved" if listing.moved else "listing_empty"


def _reextract(run: _Run, *, outdated_only: bool) -> int:
    """Extract again from the kept raw answers, without a request; returns how many finds it evaluated."""
    conn, source = run.conn, run.source
    batch: list[tuple[str, bytes]] = []
    evaluated = 0

    def flush() -> None:
        known = previous(conn, source.source_id, [key for key, _ in batch])
        _renew(conn, run.run_id)
        with conn.transaction(), conn.cursor() as cur:
            for key, raw in batch:
                before = known[key]
                _record(cur, run, key, json.loads(raw), before, raw=None, raw_sha256=before.raw_sha256)
        batch.clear()

    for key, raw, _ in raw_records(conn, source.source_id, outdated_for=run.version if outdated_only else None):
        batch.append((key, raw))
        evaluated += 1
        if len(batch) >= 500:
            flush()
    if batch:
        flush()
    return evaluated


def _kind(
    conn: psycopg.Connection, source: SourceConfig, *, full: bool, reextract: bool
) -> tuple[str, datetime | None]:
    """The kind of the run and, for an incremental one, its lower bound of ``metadata_modified``: ``full`` for a STAC
    source, for ``--full``, and for a CKAN source without a done full run or whose last one started
    ``full_every_days`` ago or earlier; else ``incremental`` from the start of the last done run less an hour."""
    if reextract:
        return "reextract", None
    if full or source.protocol is not SourceProtocol.CKAN:
        return "full", None
    last = last_runs(conn, source.source_id)
    if last.last_started is None or last.last_full_started is None:
        return "full", None
    if last.now >= last.last_full_started + timedelta(days=source.full_every_days):
        return "full", None
    return "incremental", last.last_started - INCREMENTAL_OVERLAP


async def run_harvest(
    conn: psycopg.Connection,
    source: SourceConfig,
    *,
    gateway: Gateway | None,
    reextract: bool = False,
    full: bool = False,
) -> HarvestResult:
    """One run of ``source``; ``conn`` in autocommit. :class:`HarvestBusy` while another run holds the source."""
    kind, since = _kind(conn, source, full=full, reextract=reextract)
    run = _Run(
        conn, source, start_run(conn, source.source_id, kind), kind, since, RunCounts(), extractor_version(source)
    )
    status, stop_reason = "done", None
    try:
        if reextract:
            _reextract(run, outdated_only=False)
        else:
            assert gateway is not None
            await _fetch_and_extract(run, _Fetcher(gateway, run.counts, source.max_requests_per_run))
    except HostResting:
        status, stop_reason = "interrupted", "host_resting"
    except RobotsDisallowed:
        status, stop_reason = "interrupted", "robots"
    except UrlRejected:
        # A next page off the source's host or otherwise refused before it was sent: the listing is not readable.
        status, stop_reason = "failed", "shape"
    except _BudgetSpent:
        status, stop_reason = "interrupted", "request_budget"
    except _ListingMoved:
        status, stop_reason = "interrupted", "listing_moved"
    except _LeaseLost:
        # The row is closed already, as `interrupted` with `lease_expired`; finish_run leaves it so.
        status, stop_reason = "interrupted", "lease_expired"
    except ShapeError:
        status, stop_reason = "failed", "shape"
    except GatewayError:
        status, stop_reason = "failed", "upstream"
    except BaseException:
        finish_run(conn, run.run_id, status="failed", stop_reason="error", counts=run.counts)
        raise
    summary = source_summary(conn, source.source_id)
    run.counts.invalid = sum(summary.invalid.values())
    run.counts.extent_unknown = summary.extent_unknown
    finish_run(conn, run.run_id, status=status, stop_reason=stop_reason, counts=run.counts)
    return HarvestResult(
        run.run_id,
        kind,
        status,
        stop_reason,
        run.counts,
        summary,
        run.without_key,
        run.gone_unchecked if status == "done" else None,
        gateway is not None and source.host in gateway.robots_waived,
    )


def _policy_for(source: SourceConfig, hosts: Mapping[str, HostLimit]) -> Policy:
    """The source's host alone, with its limits from hosts.yaml (M5-36), and robots.txt obeyed (adr/0025 §6.2) but for
    the path of the source's robots exception, if its file names one (Otto, 18.11.2026)."""
    limit = hosts[source.host]
    exception = source.robots_exception
    return Policy(
        allowed_hosts=frozenset({source.host}),
        host_connections={source.host: limit.connections},
        host_intervals={} if limit.interval_s is None else {source.host: limit.interval_s},
        obey_robots=True,
        robots_exceptions={} if exception is None else {source.host: (exception.path,)},
    )


_STOP_TEXT = {
    "host_resting": "der Host ruht (Unterbrecher oder Platz zu weit weg)",
    "robots": "robots.txt verbietet den Abruf; eine Ausnahme braucht robots_exception in der Quell-Datei",
    "request_budget": "Obergrenze der Anfragen je Lauf erreicht",
    "shape": "Antwort der Quelle nicht lesbar",
    "upstream": "Quelle antwortet mit Fehler oder nicht",
    "lease_expired": "Frist abgelaufen, ein anderer Lauf hat die Quelle übernommen",
    "listing_moved": "Liste hat sich während des Laufs geändert; der nächste Lauf fragt ab dem Lauf davor",
}


_KIND_TEXT = {"full": "voll", "incremental": "inkrementell", "reextract": "neu abgeleitet"}

_GONE_TEXT = {
    "incremental": "weg nicht geprüft (inkrementell)",
    "listing_moved": "weg nicht geprüft (Liste hat sich während des Laufs geändert)",
    "listing_empty": "weg nicht geprüft (Liste leer)",
}


_REASON_TEXT = {
    "no_link": "ohne gültigen Link",
    "no_title": "ohne Titel",
    "shape": "fremde Form",
    "too_large": "Rohantwort über 1 MB",
}


def _robots_line(source: SourceConfig, result: HarvestResult) -> str | None:
    exception = source.robots_exception
    if exception is None:
        return None
    state = "angewandt" if result.robots_waived else "nicht gebraucht"
    return f"  robots.txt: Ausnahme für {source.host}{exception.path} ({state}; Beleg in der Quell-Datei, Crawl-delay gilt)"


def report(source: SourceConfig, result: HarvestResult) -> str:
    """The run report on the console: German, numbers only, no address, no key of a find (plan A6).

    Two parts, so that neither is read for the other (Otto, 17.11.2026): what this run did, and the state of the
    source's finds afterwards, which also holds the finds a ``304`` or an unchanged hash left as they were.
    """
    c, s = result.counts, result.summary
    invalid = sum(s.invalid.values())
    reasons = ", ".join(f"{_REASON_TEXT.get(reason, reason)} {count}" for reason, count in s.invalid.items())
    skipped = f", ohne Kennung übersprungen {result.without_key}" if result.without_key else ""
    gone = _GONE_TEXT[result.gone_unchecked] if result.gone_unchecked else f"weg {c.gone}"
    lines = [
        f"{source.source_id}: Lauf {result.run_id} ({_KIND_TEXT[result.kind]}) {result.status}"
        + (f" ({_STOP_TEXT[result.stop_reason]})" if result.stop_reason else ""),
        f"  Anfragen {c.requests}, davon 304: {c.not_modified}; {c.bytes / 1e6:.1f} MB",
        f"  Dieser Lauf: neu {c.found_new}, geändert {c.found_changed}, unverändert {c.found_unchanged},"
        f" {gone}{skipped}",
        f"  Stand der Quelle: gültig {s.extracted} (davon Ausdehnung unbekannt {s.extent_unknown}),"
        f" ungültig {invalid}" + (f" ({reasons})" if reasons else ""),
    ]
    robots = _robots_line(source, result)
    return "\n".join(lines if robots is None else [*lines, robots])


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harvest one source of the seed (M5-19).")
    parser.add_argument("source_id", help="a source of backend/catalog/sources/, e.g. fsdi-stac")
    parser.add_argument("--full", action="store_true", help="the whole listing of a CKAN source, not only its changes")
    parser.add_argument("--reextract", action="store_true", help="extract again from the kept raw answers, no request")
    return parser.parse_args(argv)


async def _main_async(
    source: SourceConfig, hosts: Mapping[str, HostLimit], *, reextract: bool, full: bool
) -> HarvestResult:
    with psycopg.connect(autocommit=True) as conn:
        if reextract:
            return await run_harvest(conn, source, gateway=None, reextract=True)
        async with open_source_gateway(_policy_for(source, hosts)) as gateway:
            return await run_harvest(conn, source, gateway=gateway, full=full)


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
        result = asyncio.run(_main_async(source, hosts, reextract=args.reextract, full=args.full))
    except (HarvestBusy, ConfigError) as error:
        print(f"harvest failed: {error}", file=sys.stderr)
        return 1
    except psycopg.Error as error:
        # Only the kind: the text of a database error can quote a row of foreign content or the database host (A6).
        print(
            f"harvest failed: database error {type(error).__name__} ({error.sqlstate or 'no state'})", file=sys.stderr
        )
        return 1
    print(report(source, result))
    return 0 if result.status == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
