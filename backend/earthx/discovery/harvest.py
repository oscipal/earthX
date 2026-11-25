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

Exit codes: 0 when the run is done, :data:`EXIT_PAUSED` when it paused on purpose (a budget of pages or requests reached,
the source asked for a rest) and keeps its place, 1 for everything else. ``scripts/harvest-cycle.ps1`` reads only these.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import logging
import sys
import time
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
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
    raw_of_catalogue_links,
    raw_of_keys,
    raw_records,
    renew_run,
    rest,
    save_list_validators,
    save_pass,
    seen,
    source_summary,
    start_run,
    stored_links,
    write_find,
)
from earthx.catalog.hosts import HostLimit
from earthx.catalog.registry import ConfigError
from earthx.catalog.sources import SourceConfig, SourceProtocol, read_sources
from earthx.discovery.ckan import (
    INCREMENTAL_OVERLAP,
    CkanListing,
    ckan_pages,
    extract_package,
    link_reasons,
    stable_package,
)
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
from earthx.discovery.links import LinkIndex
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
    UpstreamUnreachable,
    UrlRejected,
    user_agent_from_env,
)
from earthx.logging import configure_logging

__all__ = ["EXIT_PAUSED", "PAUSE_REASONS", "HarvestResult", "SourceResting", "main", "run_harvest"]


LOGGER = logging.getLogger(__name__)

#: The first wait after a 429 that names no Retry-After; each next one in a row twice as long, at most
#: :data:`BACKOFF_MAX_S` (Otto, 18.11.2026: minutes, doubling, not a few tries in the crawl-delay beat).
BACKOFF_FIRST_S = 120.0
BACKOFF_MAX_S = 1800.0
#: The longest a run waits on a source that asks it to slow down, all waits together; then it stops and keeps its
#: place, and the next run goes on from there.
BACKOFF_BUDGET_S = 3600.0
#: The waits after a source that did not answer in time or failed (5xx), each request after the gateway's own tries;
#: the last one repeats. Only while a page came in the last :data:`ALIVE_S`, and at most :data:`FAILURE_BUDGET_S` in all;
#: then the run ends interrupted and keeps its place, without a rest (F11 = 1, Otto 19.11.2026).
FAILURE_BACKOFF_S = (60.0, 120.0, 240.0, 480.0)
ALIVE_S = 1800.0
FAILURE_BUDGET_S = 3600.0
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

_EXTRACTORS: Mapping[SourceProtocol, Callable[[str, Any, SourceConfig, frozenset[str]], Extracted]] = {
    SourceProtocol.STAC_API: extract_collection,
    SourceProtocol.CKAN: extract_package,
}
#: What a find of a foreign shape raises while it is read; it is no find, not the end of the run.
_SHAPE_ERRORS = (TypeError, ValueError, AttributeError, KeyError, IndexError, ArithmeticError, RecursionError)


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
    #: How often a request failed (timeout, unreachable, 5xx) and was asked again, and how long the run waited for it.
    failures: int = 0
    failure_waited_s: float = 0.0
    #: How many finds the run derived again at its end because a collective page changed their link (Otto, 21.11.2026).
    links_settled: int = 0
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
    #: The links every find of the source could take, and the collective pages among them (Otto, 21.11.2026): read from
    #: the intermediate forms when the run starts, kept up to date with every find the run extracts.
    index: LinkIndex = field(default_factory=LinkIndex)
    shared: frozenset[str] = frozenset()
    #: The finds this run derived, so that a second derivation at its end (:func:`_settle`) is not counted twice.
    touched: set[str] = field(default_factory=set)
    #: How many finds :func:`_settle` derived again because a collective page changed their link.
    links_settled: int = 0


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
    source asks for it.

    A 429 is waited for by its ``Retry-After``, else from :data:`BACKOFF_FIRST_S` on, doubling (Otto, 18.11.2026); more
    than :data:`BACKOFF_BUDGET_S` of such waiting ends the run ``rate_limited``. A request that timed out, could not
    reach the source or got a 5xx after the gateway's own tries is asked again after the waits of
    :data:`FAILURE_BACKOFF_S`, as long as a page came in the last :data:`ALIVE_S` (the source answers at all) and at
    most :data:`FAILURE_BUDGET_S` in all; then its error ends the run (F11 = 1, Otto 19.11.2026). A host the breaker
    paused after either is waited for the same way. Every wait renews the run's hold on its source."""

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
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._gateway, self._host, self._counts, self._budget = gateway, host, counts, budget
        self._renew, self._sleep, self._now, self._clock = renew, sleep, now, clock
        self.rate_limited = 0
        self.waited_s = 0.0
        #: The last Retry-After of a 429 in seconds, ``None`` where the source named none.
        self.retry_after_s: float | None = None
        #: Requests that failed (timeout, unreachable, 5xx) and were asked again, and the time waited for them.
        self.failures = 0
        self.failure_waited_s = 0.0
        # The run's start counts as the last answer: a source down from the start is waited for as long.
        self._last_answer = clock()

    async def __call__(
        self, url: str, *, params: Mapping[str, str | int] | None = None, headers: Mapping[str, str] | None = None
    ) -> GatewayResponse:
        backoff, limited, failing = BACKOFF_FIRST_S, False, 0
        while True:
            if self._counts.requests >= self._budget:
                raise _BudgetSpent
            try:
                response = await self._gateway.get(url, params=params, headers=headers)
            except UpstreamError as error:
                self._counts.requests += 1
                if error.status_code == 429:
                    self.rate_limited += 1
                    limited = True
                    wait = self.retry_after_s = _retry_after_s(error.retry_after, self._now())
                    await self._wait_limited(backoff if wait is None else wait)
                    backoff = min(backoff * 2, BACKOFF_MAX_S)
                    continue
                if error.status_code < 500:
                    raise
                await self._wait_failing(error, failing)
                failing += 1
                continue
            except UpstreamUnreachable as error:
                self._counts.requests += 1
                await self._wait_failing(error, failing)
                failing += 1
                continue
            except HostResting as error:
                # Paused by the breaker after the 429s or the failures: wait on. Resting for any other reason ends it.
                if limited:
                    await self._wait_limited(backoff)
                    backoff = min(backoff * 2, BACKOFF_MAX_S)
                    continue
                if failing:
                    await self._wait_failing(error, failing)
                    failing += 1
                    continue
                raise
            self._counts.requests += 1
            self._counts.bytes += len(response.content)
            if response.status_code == 304:
                self._counts.not_modified += 1
            self._last_answer = self._clock()
            return response

    async def _wait_limited(self, wait: float) -> None:
        if self.waited_s + wait > BACKOFF_BUDGET_S:
            raise _RateLimited
        LOGGER.warning("source asks to slow down", extra={"host": self._host, "wait_s": round(wait)})
        await self._wait(wait)
        self.waited_s += wait

    async def _wait_failing(self, error: Exception, failing: int) -> None:
        """Wait before asking a failed request again, or re-raise ``error`` when the source seems gone."""
        wait = FAILURE_BACKOFF_S[min(failing, len(FAILURE_BACKOFF_S) - 1)]
        if self._clock() - self._last_answer > ALIVE_S or self.failure_waited_s + wait > FAILURE_BUDGET_S:
            raise error
        self.failures += 1
        LOGGER.warning(
            "source failed, asking again", extra={"host": self._host, "kind": type(error).__name__, "wait_s": wait}
        )
        await self._wait(wait)
        self.failure_waited_s += wait

    async def _wait(self, seconds: float) -> None:
        """Sleep, renewing the run's hold on its source at every heartbeat."""
        left = seconds
        while left > 0:
            step = min(left, HEARTBEAT_S)
            await self._sleep(step)
            left -= step
            self._renew()


def _count_find(run: _Run, before: Previous | None, now: tuple[str, str | None], old: Any, new: Any) -> None:
    """What a find that this run derived counts as: new, unchanged or changed, and which fields changed."""
    counts = run.counts
    if before is None or before.state == "gone":
        counts.found_new += 1
    elif (before.state, before.reason, old) == (*now, new):
        # Equal after sorting the lists whose order says nothing: no change, whatever the hash of an older rule said.
        counts.found_unchanged += 1
    else:
        counts.found_changed += 1
        run.changed_fields.update(changed_fields(old, new) if (before.state, before.reason) == now else ["(Zustand)"])


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
            found = _EXTRACTORS[run.source.protocol](key, document, run.source, run.shared)
        except _SHAPE_ERRORS:
            # One find of a foreign shape must not end the run for every other one (review of PR 1).
            raise Invalid("shape") from None
        extracted, digest, extent = found.to_document(), extracted_sha256(found), found.extent_known
        run.index.set(key, found.link_candidates, stored=found.source_url if found.source_rank < 3 else None)
    except Invalid as invalid:
        state, reason = "invalid", invalid.reason
        # A find without a free link keeps the links it could have, to be derived again when one is free.
        extracted = {"link_candidates": invalid.link_candidates} if invalid.link_candidates else None
        run.index.set(key, invalid.link_candidates, invalid=True)
    if key not in run.touched:
        old = None if before is None else comparable(before.extracted)
        _count_find(run, before, (state, reason), old, comparable(extracted))
        run.touched.add(key)
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
            _gone(run, mark_gone(conn, run_id=run.run_id, source_id=source.source_id))
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
        _gone(run, mark_gone(conn, run_id=run.run_id, source_id=source.source_id, seen_since_run=run.pass_.run_id))
    else:
        run.gone_unchecked = "listing_empty"
    end_pass(conn, source.source_id)


def _gone(run: _Run, keys: Sequence[str]) -> None:
    """Finds the source no longer names: counted, and out of the index of collective pages."""
    run.counts.gone = len(keys)
    for key in keys:
        run.index.discard(key)


def _reextract(run: _Run, *, outdated_only: bool, keys: Sequence[str] | None = None) -> int:
    """Extract again from the kept raw answers, without a request; returns how many finds it evaluated. ``keys`` limits
    it to those finds."""
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

    stored = (
        raw_records(conn, source.source_id, outdated_for=run.version if outdated_only else None)
        if keys is None
        else raw_of_keys(conn, source.source_id, keys)
    )
    for key, raw, _ in stored:
        batch.append((key, raw))
        evaluated += 1
        if len(batch) >= 500:
            flush()
    if batch:
        flush()
    return evaluated


def _build_index(run: _Run) -> None:
    """Read the links of every find of the source from the intermediate forms the earlier runs left (no raw answer)
    and settle the collective pages among them."""
    for key, state, candidates, stored in stored_links(run.conn, run.source.source_id):
        run.index.set(key, candidates, stored=stored, invalid=state == "invalid")
    run.shared = run.index.shared()


def _settle(run: _Run) -> None:
    """The end of a run: finds whose link does not fit the collective pages of the source as they stand now are derived
    again from their raw answers, only those. A find another one made a collective page of is one, also if it did not
    change; so is one whose page stopped being collective. Comparing the stored links with what the index holds, not
    with what this run did, also mends a run that ended early (Otto, 21.11.2026). Reads no raw answer but the stale
    ones."""
    shared = run.index.shared()
    stale = run.index.stale(shared)
    run.shared = shared
    if stale:
        run.links_settled = _reextract(run, outdated_only=False, keys=stale)


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
        _build_index(run)
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
    if stop_reason != "lease_expired":
        try:
            _settle(run)
        except _LeaseLost:
            status, stop_reason = "interrupted", "lease_expired"
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
        run_id=run.run_id,
        kind=kind,
        status=status,
        stop_reason=stop_reason,
        counts=run.counts,
        summary=summary,
        without_key=run.without_key,
        gone_unchecked=run.gone_unchecked if status == "done" else None,
        robots_waived=gateway is not None and source.host in gateway.robots_waived,
        rate_limited=0 if fetch is None else fetch.rate_limited,
        waited_s=0.0 if fetch is None else fetch.waited_s,
        failures=0 if fetch is None else fetch.failures,
        failure_waited_s=0.0 if fetch is None else fetch.failure_waited_s,
        links_settled=run.links_settled,
        resumed_at=resumed_at,
        resume_at=None if still_open is None else still_open.read,
        rest_until=rest_until,
        changed_fields=tuple(run.changed_fields.most_common(_REPORT_FIELDS)),
        raw_fields=tuple(run.raw_fields.most_common(_REPORT_FIELDS)),
    )


def source_policy(source: SourceConfig, hosts: Mapping[str, HostLimit]) -> Policy:
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


#: The exit code of a run that paused on purpose and keeps its place (M5-67 fix 1, 24.11.2026): the next run goes on, so
#: for ``scripts/harvest-cycle.ps1`` it is a success with a note, not a failure. 75 is ``EX_TEMPFAIL`` of ``sysexits.h``.
EXIT_PAUSED = 75
#: The stop reasons that are such a pause: a budget of the run reached, and the source asking for a rest. Everything else
#: that ends a run early (robots, an unreachable source, a resting host, a lost lease) stays a failure with exit code 1.
PAUSE_REASONS = frozenset({"page_budget", "request_budget", "rate_limited"})

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
    if result.links_settled:
        lines.append(
            f"  Link „Source“ neu abgeleitet wegen einer Sammelseite (gleiche Adresse bei mehreren Funden):"
            f" {result.links_settled}"
        )
    if result.failures:
        lines.append(
            f"  Quelle antwortete nicht oder mit Fehler: {result.failures}-mal erneut gefragt,"
            f" gewartet {result.failure_waited_s / 60:.0f} min"
        )
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
    parser.add_argument(
        "--explain-links",
        action="store_true",
        help="a CKAN source: why finds reach only the catalogue page, from the kept raw answers, no request",
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


_LINK_GROUPS = (
    (("url_", "extras_page_"), "Feld url und page_extras des Pakets (Rang 2: Seite des Datensatzes beim Anbieter)"),
    (("no_resources", "no_html_resource", "html_", "resource_without_format"), "Ressourcen (Rang 1: Viewer- oder Download-Seite)"),
    (("field:", "extras:"), "Andere Felder mit einer Adresse (liest der Extract nicht)"),
)
_LINK_TEXT = {
    "url_empty": "leer",
    "url_http": "nur http",
    "url_file": "zeigt auf eine Datei",
    "url_service": "zeigt auf einen Dienst",
    "url_start_page": "nur Startseite",
    "url_host": "Host keine Adresse (IP o. ä.)",
    "url_scheme": "anderes Schema",
    "url_invalid": "nicht lesbar",
    "url_metadata": "Metadaten-Endpunkt",
    "url_collection_page": "Sammelseite (Host und höchstens ein Pfadteil)",
    "extras_page_collection_page": "Feld aus page_extras: Sammelseite (Host und höchstens ein Pfadteil)",
    "html_collection_page": "HTML-Ressource: Sammelseite (Host und höchstens ein Pfadteil)",
    "extras_page_empty": "Feld aus page_extras leer",
    "extras_page_http": "Feld aus page_extras nur http",
    "extras_page_file": "Feld aus page_extras zeigt auf eine Datei",
    "extras_page_service": "Feld aus page_extras zeigt auf einen Dienst",
    "extras_page_metadata": "Feld aus page_extras ist ein Metadaten-Endpunkt",
    "extras_page_start_page": "Feld aus page_extras nur Startseite",
    "url_long": "zu lang",
    "url_control": "Steuerzeichen",
    "url_port": "fremder Port",
    "no_resources": "keine Ressourcen",
    "no_html_resource": "keine Ressource mit Format HTML",
    "resource_without_format": "Ressource mit Adresse, ohne Format",
    "html_with_download": "HTML-Ressource, Download-Adresse ist eine Datei",
    "html_metadata": "HTML-Ressource ist ein Metadaten-Endpunkt",
    "html_file": "HTML-Ressource zeigt auf eine Datei",
    "html_documentation": "HTML-Ressource ist Doku",
    "html_by_id": "HTML-Ressource, Adresse aus der Ressourcen-ID",
    "html_service": "HTML-Ressource ist ein Dienst",
    "html_http": "HTML-Ressource nur http",
    "html_start_page": "HTML-Ressource nur Startseite",
    "html_empty": "HTML-Ressource ohne Adresse",
}
_EXAMPLES = 3
_MAX_OTHER_FIELDS = 15


def explain_links(conn: psycopg.Connection, source: SourceConfig) -> str:
    """Why the finds of a CKAN source reach only the catalogue page or no link (Otto, 19.11.2026): per reason how many
    finds and three examples (the package's name and the address concerned), from the kept raw answers, without a
    request. A find counts once per reason; one find has several reasons. Person fields are never named."""
    counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}
    total = unreadable = 0
    for key, raw in raw_of_catalogue_links(conn, source.source_id):
        total += 1
        try:
            package = json.loads(raw)
        except (ValueError, RecursionError):
            unreadable += 1
            continue
        if not isinstance(package, dict):
            unreadable += 1
            continue
        name = package.get("name") if isinstance(package.get("name"), str) else key
        for code, value in dict(link_reasons(package, source)).items():
            counts[code] += 1
            listed = examples.setdefault(code, [])
            if len(listed) < _EXAMPLES:
                listed.append(f"{name[:60]}: {(value or '—')[:120]}")
    lines = [
        f"{source.source_id}: {total} Funde nur mit Katalogseite (Rang 3) oder ohne Link, ausgewertet ohne Anfrage"
        + (f"; {unreadable} Rohantworten nicht lesbar" if unreadable else "")
    ]
    for prefixes, title in _LINK_GROUPS:
        codes = [code for code in counts if code.startswith(prefixes)]
        if not codes:
            continue
        lines.append(f"  {title}:")
        codes.sort(key=lambda code: -counts[code])
        for code in codes[: _MAX_OTHER_FIELDS if title.startswith("Andere") else None]:
            share = 100 * counts[code] / max(total, 1)
            lines.append(f"    {_LINK_TEXT.get(code, code)}: {counts[code]} ({share:.0f} %)")
            lines += [f"      {example}" for example in examples[code]]
    return "\n".join(lines)


async def _measure(source: SourceConfig, hosts: Mapping[str, HostLimit]) -> str:
    with psycopg.connect(autocommit=True) as conn:
        async with open_source_gateway(source_policy(source, hosts)) as gateway:
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
        async with open_source_gateway(source_policy(source, hosts)) as gateway:
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
    if args.explain_links:
        if source.protocol is not SourceProtocol.CKAN:
            print(f"harvest failed: --explain-links is for a ckan source, {args.source_id!r} is not one", file=sys.stderr)
            return 1
        try:
            with psycopg.connect(autocommit=True) as conn:
                print(explain_links(conn, source))
        except psycopg.Error as error:
            print(f"harvest failed: database error {type(error).__name__}", file=sys.stderr)
            return 1
        return 0
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
        # A rest the source asked for earlier: no run starts, the finds read so far stay as they are.
        print(resting_text(error))
        return EXIT_PAUSED
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
    if result.status == "done":
        return 0
    return EXIT_PAUSED if result.status == "interrupted" and result.stop_reason in PAUSE_REASONS else 1


if __name__ == "__main__":
    raise SystemExit(main())
