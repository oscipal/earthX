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
import gzip
import hashlib
import json
import logging
import sys
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import psycopg

from earthx.catalog.datasets import registry
from earthx.catalog.harvest_store import (
    MAX_RAW_BYTES,
    HarvestBusy,
    Pass,
    Previous,
    RunCounts,
    SourceSummary,
    begin_pass,
    canonical,
    end_pass,
    finish_run,
    harvest_state,
    list_validators,
    mark_gone,
    previous,
    raw_records,
    renew_run,
    rest,
    save_list_validators,
    save_pass,
    seen,
    source_summary,
    start_run,
    write_find,
)
from earthx.catalog.hosts import HostLimit
from earthx.catalog.registry import ConfigError
from earthx.catalog.sources import SourceConfig, SourceProtocol, read_sources
from earthx.discovery.ckan import INCREMENTAL_OVERLAP, CkanListing, ckan_pages, extract_package, stable_package
from earthx.discovery.ckan_measure import measure_page
from earthx.discovery.extract import (
    Extracted,
    Invalid,
    ShapeError,
    changed_fields,
    comparable,
    extracted_sha256,
    extractor_version,
)
from earthx.discovery.source_gateway import open_source_gateway
from earthx.discovery.stac import StacListing, extract_collection, stac_pages
from earthx.gateway import (
    Gateway,
    GatewayError,
    GatewayResponse,
    HostResting,
    Policy,
    RobotsDisallowed,
    UpstreamError,
    UrlRejected,
    user_agent_from_env,
)
from earthx.logging import configure_logging

__all__ = ["HarvestResult", "SourceResting", "main", "run_harvest"]


LOGGER = logging.getLogger(__name__)

#: The first wait after a 429 that names no Retry-After; each next one in a row twice as long, at most
#: :data:`BACKOFF_MAX_S` (Otto, 18.11.2026: minutes, doubling, not a few tries in the crawl-delay beat).
BACKOFF_FIRST_S = 120.0
BACKOFF_MAX_S = 1800.0
#: The longest a run waits on a source that asks it to slow down, all waits together; then it stops and keeps its
#: place, and the next run goes on from there.
BACKOFF_BUDGET_S = 3600.0
#: The run's hold on its source is renewed at least this often while it waits (its term is 5 min, A1).
HEARTBEAT_S = 60.0
#: The pages ``--measure`` reads: the first page as a run asks it, the second twice by offset and twice by key, and the
#: first with ``fl``.
MEASURE_PAGES = 6


class _BudgetSpent(Exception):
    pass


class _RateLimited(Exception):
    """The source asked the run to slow down for longer than its budget of waiting."""


class _PageBudget(Exception):
    """The run read the pages its source allows a run; the pass goes on in the next one."""


class SourceResting(Exception):
    """The source refused the harvest (429) and rests until ``until``: no run starts before (Otto, 18.11.2026)."""

    def __init__(self, source_id: str, until: datetime) -> None:
        super().__init__(f"{source_id} rests until {until:%Y-%m-%d %H:%M} UTC")
        self.source_id, self.until = source_id, until


class _LeaseLost(Exception):
    """Another run closed this one after its term ran out; it writes nothing more."""


def _renew(conn: psycopg.Connection, run_id: int) -> None:
    if not renew_run(conn, run_id):
        raise _LeaseLost


#: What the hash of a raw answer is taken over: the answer without the bookkeeping the extract never reads (CKAN).
_STABLE: Mapping[SourceProtocol, Callable[[Any], Any]] = {
    SourceProtocol.STAC_API: lambda document: document,
    SourceProtocol.CKAN: stable_package,
}
#: How many changed fields a report names.
_REPORT_FIELDS = 8

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
    #: Why a run that ended ``done`` did not look for finds that are gone: ``incremental``, or ``listing_empty`` where a
    #: full CKAN pass named no package at all (a rebuilt index, a filter that no longer matches), which is no evidence
    #: that all are gone.
    gone_unchecked: str | None = None
    #: Whether the run read a path robots.txt disallows, under the exception of the source's file (Otto, 18.11.2026).
    robots_waived: bool = False
    #: How often the source answered 429, and how long the run waited for it in all.
    rate_limited: int = 0
    waited_s: float = 0.0
    #: A CKAN pass over several runs (Otto, 18./19.11.2026): how many packages it had read when this run went on with
    #: it, and how many when this one stopped before the pass was through (the next run goes on after the last key).
    resumed_at: int | None = None
    resume_at: int | None = None
    #: Until when the source rests after this run ended ``rate_limited``.
    rest_until: datetime | None = None
    #: In which fields the changed finds differ: their intermediate form, and their raw answer where it changed beyond
    #: the bookkeeping left out of its hash (Otto, 19.11.2026). Names and counts only.
    changed_fields: tuple[tuple[str, int], ...] = ()
    raw_fields: tuple[tuple[str, int], ...] = ()


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
    #: The open pass of a CKAN source this run reads on.
    pass_: Pass | None = None
    pages: int = 0
    changed_fields: Counter[str] = field(default_factory=Counter)
    raw_fields: Counter[str] = field(default_factory=Counter)


def _retry_after_s(value: str | None, now: datetime) -> float | None:
    """A ``Retry-After`` as seconds from ``now``: whole seconds or an HTTP date; ``None`` where it is neither."""
    text = (value or "").strip()
    if text.isascii() and text.isdigit():
        return float(text)
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if when.tzinfo is None:
        return None
    return max((when - now).total_seconds(), 0.0)


class _Fetcher:
    """Every request of a run: counted, refused once the source's budget per run is spent, and waited for when the
    source answers 429 (Otto, 18.11.2026): by its ``Retry-After``, else from :data:`BACKOFF_FIRST_S` on, doubling. A
    host the breaker paused after those 429s is waited for the same way. More than :data:`BACKOFF_BUDGET_S` of waiting
    in all ends the run, which keeps its place."""

    def __init__(
        self,
        gateway: Gateway,
        host: str,
        counts: RunCounts,
        budget: int,
        *,
        renew: Callable[[], None],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._gateway, self._host, self._counts, self._budget = gateway, host, counts, budget
        self._renew, self._sleep, self._now = renew, sleep, now
        self.rate_limited = 0
        self.waited_s = 0.0
        #: The last Retry-After of a 429 in seconds, ``None`` where the source named none.
        self.retry_after_s: float | None = None

    async def __call__(
        self, url: str, *, params: Mapping[str, str | int] | None = None, headers: Mapping[str, str] | None = None
    ) -> GatewayResponse:
        backoff, limited = BACKOFF_FIRST_S, False
        while True:
            if self._counts.requests >= self._budget:
                raise _BudgetSpent
            try:
                response = await self._gateway.get(url, params=params, headers=headers)
            except UpstreamError as error:
                self._counts.requests += 1
                if error.status_code != 429:
                    raise
                self.rate_limited += 1
                limited = True
                wait = self.retry_after_s = _retry_after_s(error.retry_after, self._now())
                wait = backoff if wait is None else wait
            except HostResting:
                # Paused by the breaker after the 429s: wait on. A host resting for any other reason ends the run.
                if not limited:
                    raise
                wait = backoff
            else:
                self._counts.requests += 1
                self._counts.bytes += len(response.content)
                if response.status_code == 304:
                    self._counts.not_modified += 1
                return response
            if self.waited_s + wait > BACKOFF_BUDGET_S:
                raise _RateLimited
            LOGGER.warning("source asks to slow down", extra={"host": self._host, "wait_s": round(wait)})
            await self._wait(wait)
            backoff = min(backoff * 2, BACKOFF_MAX_S)

    async def _wait(self, seconds: float) -> None:
        """Sleep, renewing the run's hold on its source at every heartbeat."""
        left = seconds
        while left > 0:
            step = min(left, HEARTBEAT_S)
            await self._sleep(step)
            left -= step
            self.waited_s += step
            self._renew()


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
    new, old = comparable(extracted), None if before is None else comparable(before.extracted)
    if before is None or before.state == "gone":
        counts.found_new += 1
    elif (before.state, before.reason, old) == (state, reason, new):
        # Equal after sorting the lists whose order says nothing: no change, whatever the hash of an older rule said.
        counts.found_unchanged += 1
    else:
        counts.found_changed += 1
        run.changed_fields.update(
            changed_fields(old, new) if (before.state, before.reason) == (state, reason) else ["(Zustand)"]
        )
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
    if run.pass_ is not None:
        # Where the open pass stands: a run that stopped before keeps its place (Otto, 18.11.2026).
        p = run.pass_
        ckan.last_key, ckan.read = p.last_key, p.read
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
                digest = hashlib.sha256(canonical(_STABLE[source.protocol](document))).hexdigest()
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
                    if before is not None and before.raw_sha256 != digest and before.raw_gzip is not None:
                        run.raw_fields.update(changed_fields(json.loads(gzip.decompress(before.raw_gzip)), document))
                    _record(cur, run, key, document, before, raw=raw, raw_sha256=digest)
        if run.pass_ is not None and isinstance(listing, CkanListing):
            save_pass(conn, source.source_id, last_key=listing.last_key, read=listing.read)
        run.pages += 1
        budget = source.max_pages_per_run
        if budget is not None and run.pages >= budget and isinstance(listing, CkanListing) and not listing.exhausted:
            raise _PageBudget
    _renew(conn, run.run_id)
    if listing.not_modified:
        # The listing is unchanged as a whole, but finds an older extractor judged are judged again from their kept
        # raw answers (Otto, 17.11.2026); the others stay as they are.
        evaluated = _reextract(run, outdated_only=True)
        summary = source_summary(conn, source.source_id)
        run.counts.found_unchanged += summary.extracted + sum(summary.invalid.values()) - evaluated
        return
    if not isinstance(listing, CkanListing):
        if listing.complete:
            run.counts.gone = mark_gone(conn, run_id=run.run_id, source_id=source.source_id)
            if listing.validators is not None:
                save_list_validators(conn, source.source_id, listing.validators)
        return
    assert run.pass_ is not None
    if not listing.full:
        # Finds the listing did not name are judged again if an older extractor judged them, from their kept raw
        # answers; a full run sees them all anyway.
        _reextract(run, outdated_only=True)
        run.gone_unchecked = "incremental"
    elif listing.complete:
        # Gone is what no run of the pass saw, whichever of its runs read which page (A3).
        run.counts.gone = mark_gone(
            conn, run_id=run.run_id, source_id=source.source_id, seen_since_run=run.pass_.run_id
        )
    else:
        run.gone_unchecked = "listing_empty"
    end_pass(conn, source.source_id)


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
) -> tuple[str, datetime | None, Pass | None]:
    """The kind of the run; for an incremental one its lower bound of ``metadata_modified``; the open pass a CKAN run
    goes on with.

    ``full`` for a STAC source. For a CKAN source a full pass is due with ``--full``, without a full pass that went
    through, or when the last one began ``full_every_days`` ago or earlier. An open full pass goes on (also with
    ``--full``); an open incremental pass goes on unless a full pass is due, which takes its place and reads all it
    would have (Otto, 19.11.2026). Else ``incremental`` from the time every change is in (:func:`end_pass`) less an
    hour."""
    if reextract:
        return "reextract", None, None
    if source.protocol is not SourceProtocol.CKAN:
        return "full", None, None
    state = harvest_state(conn, source.source_id)
    opened = state.open_pass
    if opened is not None and opened.full:
        return "full", None, opened
    due = (
        full
        or state.full_started_at is None
        or state.changes_since is None
        or state.now >= state.full_started_at + timedelta(days=source.full_every_days)
    )
    if due:
        return "full", None, None
    if opened is not None:
        return "incremental", opened.since, opened
    return "incremental", state.changes_since - INCREMENTAL_OVERLAP, None


async def run_harvest(
    conn: psycopg.Connection,
    source: SourceConfig,
    *,
    gateway: Gateway | None,
    reextract: bool = False,
    full: bool = False,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> HarvestResult:
    """One run of ``source``; ``conn`` in autocommit. :class:`HarvestBusy` while another run holds the source.
    ``sleep`` is how the run waits on a source that asks it to slow down (a seam for tests)."""
    if not reextract:
        state = harvest_state(conn, source.source_id)
        if state.resting:
            assert state.rest_until is not None
            raise SourceResting(source.source_id, state.rest_until)
    kind, since, open_pass = _kind(conn, source, full=full, reextract=reextract)
    run = _Run(
        conn, source, start_run(conn, source.source_id, kind), kind, since, RunCounts(), extractor_version(source)
    )
    resumed_at = None
    if kind != "reextract" and source.protocol is SourceProtocol.CKAN:
        run.pass_ = open_pass if open_pass is not None else begin_pass(conn, source.source_id, run.run_id, since)
        resumed_at = None if open_pass is None else open_pass.read
    fetch = None
    status, stop_reason = "done", None
    try:
        if reextract:
            _reextract(run, outdated_only=False)
        else:
            assert gateway is not None
            fetch = _Fetcher(
                gateway,
                source.host,
                run.counts,
                source.max_requests_per_run,
                renew=lambda: _renew(conn, run.run_id),
                sleep=sleep,
            )
            await _fetch_and_extract(run, fetch)
    except HostResting:
        status, stop_reason = "interrupted", "host_resting"
    except RobotsDisallowed:
        status, stop_reason = "interrupted", "robots"
    except UrlRejected:
        # A next page off the source's host or otherwise refused before it was sent: the listing is not readable.
        status, stop_reason = "failed", "shape"
    except _BudgetSpent:
        status, stop_reason = "interrupted", "request_budget"
    except _PageBudget:
        status, stop_reason = "interrupted", "page_budget"
    except _RateLimited:
        status, stop_reason = "interrupted", "rate_limited"
    except _LeaseLost:
        # The row is closed already, as `interrupted` with `lease_expired`; finish_run leaves it so.
        status, stop_reason = "interrupted", "lease_expired"
    except ShapeError:
        status, stop_reason = "failed", "shape"
    except GatewayError:
        # A full pass keeps its place, so a source that fails on the way is a pause of the pass, not its end.
        status, stop_reason = ("interrupted" if run.pass_ is not None else "failed"), "upstream"
    except BaseException:
        finish_run(conn, run.run_id, status="failed", stop_reason="error", counts=run.counts)
        raise
    summary = source_summary(conn, source.source_id)
    run.counts.invalid = sum(summary.invalid.values())
    run.counts.extent_unknown = summary.extent_unknown
    finish_run(conn, run.run_id, status=status, stop_reason=stop_reason, counts=run.counts)
    still_open = None if run.pass_ is None else harvest_state(conn, source.source_id).open_pass
    rest_until = None
    if stop_reason == "rate_limited":
        assert fetch is not None
        rest_until = rest(conn, source.source_id, fetch.retry_after_s)
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
        0 if fetch is None else fetch.rate_limited,
        0.0 if fetch is None else fetch.waited_s,
        resumed_at,
        None if still_open is None else still_open.read,
        rest_until,
        tuple(run.changed_fields.most_common(_REPORT_FIELDS)),
        tuple(run.raw_fields.most_common(_REPORT_FIELDS)),
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
        host_read_timeouts={} if limit.timeout_s is None else {source.host: limit.timeout_s},
        obey_robots=True,
        robots_exceptions={} if exception is None else {source.host: (exception.path,)},
        retry_rate_limited=False,
    )


_STOP_TEXT = {
    "host_resting": "der Host ruht (Unterbrecher oder Platz zu weit weg)",
    "robots": "robots.txt verbietet den Abruf; eine Ausnahme braucht robots_exception in der Quell-Datei",
    "request_budget": "Obergrenze der Anfragen je Lauf erreicht",
    "shape": "Antwort der Quelle nicht lesbar",
    "upstream": "Quelle antwortet mit Fehler oder nicht",
    "lease_expired": "Frist abgelaufen, ein anderer Lauf hat die Quelle übernommen",
    "rate_limited": "die Quelle bittet länger um Pause, als ein Lauf wartet",
    "page_budget": "Seiten je Lauf erreicht (max_pages_per_run); der nächste Lauf setzt fort",
}


_PASS_TEXT = {"full": ("Voller", "vollen"), "incremental": ("Inkrementeller", "inkrementellen")}

_KIND_TEXT = {"full": "voll", "incremental": "inkrementell", "reextract": "neu abgeleitet"}

_GONE_TEXT = {
    "incremental": "weg nicht geprüft (inkrementell)",
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
    if result.changed_fields:
        named = ", ".join(f"{name} {count}" for name, count in result.changed_fields)
        lines.append(f"  geändert in (Zwischenform): {named}")
    if result.raw_fields:
        named = ", ".join(f"{name} {count}" for name, count in result.raw_fields)
        lines.append(f"  Rohantwort geändert in: {named}")
    if result.rate_limited:
        lines.append(f"  Quelle bat um Pause: {result.rate_limited}-mal 429, gewartet {result.waited_s / 60:.0f} min")
    if result.rest_until is not None:
        lines.append(f"  Quelle ruht bis {result.rest_until.astimezone(UTC):%Y-%m-%d %H:%M} UTC; vorher startet kein Lauf")
    if result.resumed_at is not None:
        lines.append(f"  {_PASS_TEXT[result.kind][0]} Durchgang fortgesetzt nach {result.resumed_at} Paketen")
    if result.resume_at is not None:
        lines.append(
            f"  Stand gespeichert: der nächste Lauf setzt den {_PASS_TEXT[result.kind][1]} Durchgang"
            f" nach {result.resume_at} Paketen fort"
        )
    robots = _robots_line(source, result)
    return "\n".join(lines if robots is None else [*lines, robots])


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harvest one source of the seed (M5-19).")
    parser.add_argument("source_id", help="a source of backend/catalog/sources/, e.g. fsdi-stac")
    parser.add_argument("--full", action="store_true", help="the whole listing of a CKAN source, not only its changes")
    parser.add_argument("--reextract", action="store_true", help="extract again from the kept raw answers, no request")
    parser.add_argument(
        "--measure", action="store_true", help="a CKAN source: size of one page with and without fl, nothing written"
    )
    return parser.parse_args(argv)


async def measure(conn: psycopg.Connection, source: SourceConfig, gateway: Gateway) -> str:
    """``--measure`` under the rules of a run (Otto, 18.11.2026): not while the source rests, not beyond its pages per
    run, and a 429 lets it rest as after a run."""
    state = harvest_state(conn, source.source_id)
    if state.resting:
        assert state.rest_until is not None
        raise SourceResting(source.source_id, state.rest_until)
    if source.max_pages_per_run is not None and source.max_pages_per_run < MEASURE_PAGES:
        raise ConfigError(f"{source.source_id}: --measure reads {MEASURE_PAGES} pages, more than max_pages_per_run")
    try:
        return await measure_page(gateway.get, source)
    except UpstreamError as error:
        if error.status_code != 429:
            raise
        until = rest(conn, source.source_id, _retry_after_s(error.retry_after, datetime.now(UTC)))
        raise SourceResting(source.source_id, until) from None


async def _measure(source: SourceConfig, hosts: Mapping[str, HostLimit]) -> str:
    with psycopg.connect(autocommit=True) as conn:
        async with open_source_gateway(_policy_for(source, hosts)) as gateway:
            return await measure(conn, source, gateway)


def resting_text(error: SourceResting) -> str:
    return (
        f"{error.source_id}: kein Lauf gestartet – die Quelle bat mit 429 um Pause und ruht bis"
        f" {error.until.astimezone(UTC):%Y-%m-%d %H:%M} UTC"
    )


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
    if args.measure:
        if source.protocol is not SourceProtocol.CKAN:
            print(f"harvest failed: --measure is for a ckan source, {args.source_id!r} is not one", file=sys.stderr)
            return 1
        try:
            print(asyncio.run(_measure(source, hosts)))
        except SourceResting as error:
            print(resting_text(error))
            return 1
        except (HarvestBusy, ConfigError) as error:
            print(f"harvest failed: {error}", file=sys.stderr)
            return 1
        except psycopg.Error as error:
            print(f"harvest failed: database error {type(error).__name__}", file=sys.stderr)
            return 1
        except (GatewayError, ShapeError) as error:
            # Only the kind: the text of an upstream error can quote the answer.
            print(f"harvest failed: measurement stopped ({type(error).__name__})", file=sys.stderr)
            return 1
        return 0
    try:
        result = asyncio.run(_main_async(source, hosts, reextract=args.reextract, full=args.full))
    except SourceResting as error:
        print(resting_text(error))
        return 1
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
