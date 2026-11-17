"""T-C: a harvest run of a STAC API against a real Postgres (M5-19 plan §3, §4, §11).

The source is synthetic (``httpx.MockTransport``, plan A5); nothing here reaches a real catalogue. The run commits as
it goes (its lease must be seen by other runs), so every test harvests a source of its own and deletes its rows after.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator
from dataclasses import replace
from typing import Any

import httpx
import psycopg
import pytest

from earthx.catalog.harvest_store import HarvestBusy, start_run
from earthx.catalog.registry import ConfigError, Maturity
from earthx.catalog.sources import CkanFilter, SourceConfig, SourceProtocol, StacFilter
from earthx.discovery.harvest import report, run_harvest
from earthx.gateway import Gateway, HostResting, Policy

pytestmark = pytest.mark.anyio

HOST = "stac.example.org"
ROOT = f"https://{HOST}/api/v1"


def _collection(key: str, **changes: Any) -> dict[str, Any]:
    collection = {
        "type": "Collection",
        "id": key,
        "title": f"Collection {key}",
        "description": "Synthetic.",
        "license": "CC-BY-4.0",
        "providers": [{"name": "Example Office", "roles": ["licensor"]}],
        "contacts": [{"name": "Jane Doe", "emails": [{"value": "jane@example.org"}]}],
        "extent": {"spatial": {"bbox": [[6.0, 46.0, 7.0, 47.0]]}, "temporal": {"interval": [[None, None]]}},
        "links": [],
    }
    collection.update(changes)
    return collection


class Catalogue:
    """A STAC API of collections on pages of ``size``; counts what it is asked."""

    def __init__(self, collections: list[dict[str, Any]], *, size: int = 2, etag: str | None = None) -> None:
        self.collections, self.size, self.etag = collections, size, etag
        self.asked: list[httpx.Request] = []
        self.robots = "User-agent: *\nAllow: /\n"
        self.status = 200
        self.next_of: Callable[[int], str | None] | None = None

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=self.robots)
        self.asked.append(request)
        if self.status != 200:
            return httpx.Response(self.status, text="broken")
        if self.etag is not None and request.headers.get("if-none-match") == self.etag:
            return httpx.Response(304)
        page = int(request.url.params.get("page", "0"))
        chunk = self.collections[page * self.size : (page + 1) * self.size]
        links = []
        following = (
            self.next_of(page)
            if self.next_of
            else (
                f"{ROOT}/collections?limit=100&page={page + 1}"
                if (page + 1) * self.size < len(self.collections)
                else None
            )
        )
        if following:
            links.append({"rel": "next", "href": following, "type": "application/json"})
        headers = {"etag": self.etag} if self.etag else {}
        return httpx.Response(200, content=json.dumps({"collections": chunk, "links": links}), headers=headers)


def _gateway(catalogue: Catalogue) -> Gateway:
    async def sleep(seconds: float) -> None:
        return None

    policy = Policy(allowed_hosts=frozenset({HOST}), obey_robots=True)
    return Gateway(
        policy,
        transport=httpx.MockTransport(catalogue.handle),
        resolve=lambda host, port: ("93.184.216.34",),
        sleep=sleep,
    )


@pytest.fixture
def source() -> SourceConfig:
    return SourceConfig(
        source_id=f"t-{uuid.uuid4().hex[:12]}",
        protocol=SourceProtocol.STAC_API,
        endpoint=ROOT,
        catalog_page="https://stac.example.org/browser/#/collections/{id}",
        filter=StacFilter(()),
        max_requests_per_run=20,
        full_every_days=1,
        maturity=Maturity.STABLE,
        enabled=True,
    )


@pytest.fixture
def db(require_postgres_env: None, source: SourceConfig) -> Iterator[psycopg.Connection]:
    """A connection in autocommit, as the command opens it; the rows of the test's source go afterwards."""
    connection = psycopg.connect(autocommit=True)
    try:
        yield connection
    finally:
        for table in (
            "earthx_state_transition",
            "earthx_record_state",
            "earthx_raw_record",
            "earthx_harvest_source",
            "earthx_harvest_run",
        ):
            connection.execute(f"DELETE FROM public.{table} WHERE source_id = %s", (source.source_id,))
        connection.close()


def _states(db: psycopg.Connection, source: SourceConfig) -> dict[str, tuple[str, str | None, bool | None]]:
    rows = db.execute(
        "SELECT source_key, state, reason, extent_known FROM public.earthx_record_state WHERE source_id = %s",
        (source.source_id,),
    ).fetchall()
    return {key: (state, reason, extent) for key, state, reason, extent in rows}


def _transitions(db: psycopg.Connection, source: SourceConfig) -> int:
    return db.execute(
        "SELECT count(*) FROM public.earthx_state_transition WHERE source_id = %s", (source.source_id,)
    ).fetchone()[0]


THREE = [_collection("a"), _collection("b", extent=None), _collection("c", title=None)]


async def test_a_first_run_keeps_every_find_and_drops_none(db: psycopg.Connection, source: SourceConfig) -> None:
    catalogue = Catalogue(THREE)
    result = await run_harvest(db, source, gateway=_gateway(catalogue))
    assert (result.status, result.stop_reason) == ("done", None)
    c = result.counts
    assert (c.requests, c.found_new, c.found_changed, c.found_unchanged, c.invalid) == (2, 3, 0, 0, 1)
    # Otto, 17.11.2026: a find without an extent stays, marked; only the one without a title is invalid.
    assert _states(db, source) == {
        "a": ("extracted", None, True),
        "b": ("extracted", None, False),
        "c": ("invalid", "no_title", None),
    }
    assert c.extent_unknown == 1
    assert _transitions(db, source) == 3


async def test_no_person_is_kept_in_the_intermediate_form(db: psycopg.Connection, source: SourceConfig) -> None:
    await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    stored = db.execute(
        "SELECT extracted::text FROM public.earthx_record_state WHERE source_id = %s AND state = 'extracted'",
        (source.source_id,),
    ).fetchall()
    assert stored and not any("Jane" in text or "jane@" in text for (text,) in stored)


async def test_a_second_run_without_change_does_no_work(db: psycopg.Connection, source: SourceConfig) -> None:
    # Acceptance M5 §7 point 3 for a listing without ETag: the list once, decided by the hash.
    await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    before = _transitions(db, source)
    result = await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    c = result.counts
    assert (c.found_new, c.found_changed, c.found_unchanged, c.gone) == (0, 0, 3, 0)
    assert _transitions(db, source) == before


async def test_a_changed_and_a_removed_find(db: psycopg.Connection, source: SourceConfig) -> None:
    await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    result = await run_harvest(db, source, gateway=_gateway(Catalogue([_collection("a", title="New"), THREE[1]])))
    c = result.counts
    assert (c.found_new, c.found_changed, c.found_unchanged, c.gone) == (0, 1, 1, 1)
    assert _states(db, source)["c"] == ("gone", None, None)
    again = await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    assert again.counts.found_new == 1 and _states(db, source)["c"] == ("invalid", "no_title", None)


async def test_a_one_page_listing_is_asked_with_its_etag(db: psycopg.Connection, source: SourceConfig) -> None:
    catalogue = Catalogue(THREE, size=10, etag='W/"v1"')
    await run_harvest(db, source, gateway=_gateway(catalogue))
    result = await run_harvest(db, source, gateway=_gateway(catalogue))
    assert catalogue.asked[-1].headers["if-none-match"] == 'W/"v1"'
    c = result.counts
    assert (c.requests, c.not_modified, c.found_unchanged, c.found_new, c.gone) == (1, 1, 3, 0, 0)


async def test_a_longer_listing_is_never_asked_conditionally(db: psycopg.Connection, source: SourceConfig) -> None:
    # A 304 on its first page would not say that the later pages are unchanged.
    catalogue = Catalogue(THREE, size=2, etag='W/"v1"')
    await run_harvest(db, source, gateway=_gateway(catalogue))
    await run_harvest(db, source, gateway=_gateway(catalogue))
    assert not any("if-none-match" in request.headers for request in catalogue.asked)


async def test_robots_txt_stops_the_run(db: psycopg.Connection, source: SourceConfig) -> None:
    catalogue = Catalogue(THREE)
    catalogue.robots = "User-agent: *\nDisallow: /api/\n"
    result = await run_harvest(db, source, gateway=_gateway(catalogue))
    assert (result.status, result.stop_reason, result.counts.requests) == ("interrupted", "robots", 1)
    assert not catalogue.asked and _states(db, source) == {}


async def test_the_budget_of_requests_stops_the_run_without_marking_anything_gone(
    db: psycopg.Connection, source: SourceConfig
) -> None:
    await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    result = await run_harvest(db, replace(source, max_requests_per_run=1), gateway=_gateway(Catalogue(THREE)))
    assert (result.status, result.stop_reason) == ("interrupted", "request_budget")
    assert result.counts.gone == 0 and _states(db, source)["c"][0] == "invalid"


async def test_a_resting_host_interrupts_the_run(db: psycopg.Connection, source: SourceConfig) -> None:
    gateway = _gateway(Catalogue(THREE))

    async def resting(*args: object, **kwargs: object) -> None:
        raise HostResting("paused", host=HOST)

    gateway.get = resting  # type: ignore[method-assign]
    result = await run_harvest(db, source, gateway=gateway)
    assert (result.status, result.stop_reason) == ("interrupted", "host_resting")


@pytest.mark.parametrize(
    ("next_of", "reason"),
    [
        (
            lambda page: (
                f"{ROOT}/collections?limit=100&page=0" if page == 1 else f"{ROOT}/collections?limit=100&page=1"
            ),
            "shape",
        ),
        (lambda page: "https://elsewhere.example.org/collections", "shape"),
    ],
)
async def test_a_listing_that_loops_or_leaves_the_host_fails(
    db: psycopg.Connection, source: SourceConfig, next_of: Callable[[int], str], reason: str
) -> None:
    catalogue = Catalogue(THREE * 3)
    catalogue.next_of = next_of
    result = await run_harvest(db, source, gateway=_gateway(catalogue))
    assert (result.status, result.stop_reason) == ("failed", reason)


async def test_a_broken_source_fails_the_run(db: psycopg.Connection, source: SourceConfig) -> None:
    catalogue = Catalogue(THREE)
    catalogue.status = 503
    result = await run_harvest(db, source, gateway=_gateway(catalogue))
    assert (result.status, result.stop_reason) == ("failed", "upstream")


async def test_an_answer_that_is_no_listing_fails_the_run(db: psycopg.Connection, source: SourceConfig) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=b"<html>not json</html>")

    gateway = Gateway(
        Policy(allowed_hosts=frozenset({HOST}), obey_robots=True),
        transport=httpx.MockTransport(handle),
        resolve=lambda host, port: ("93.184.216.34",),
    )
    result = await run_harvest(db, source, gateway=gateway)
    assert (result.status, result.stop_reason) == ("failed", "shape")


async def test_a_second_run_of_the_same_source_waits_for_the_first(
    db: psycopg.Connection, source: SourceConfig
) -> None:
    start_run(db, source.source_id, "full")
    with pytest.raises(HarvestBusy):
        await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))


async def test_a_run_whose_lease_ran_out_is_taken_over(db: psycopg.Connection, source: SourceConfig) -> None:
    stale = start_run(db, source.source_id, "full")
    db.execute("UPDATE public.earthx_harvest_run SET lease_until = now() - interval '1 s' WHERE run_id = %s", (stale,))
    result = await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    assert result.status == "done"
    row = db.execute("SELECT status, stop_reason FROM public.earthx_harvest_run WHERE run_id = %s", (stale,)).fetchone()
    assert row == ("interrupted", "lease_expired")


async def test_a_reextract_asks_nothing_and_finds_no_change(db: psycopg.Connection, source: SourceConfig) -> None:
    await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    result = await run_harvest(db, source, gateway=None, reextract=True)
    c = result.counts
    assert (result.status, c.requests, c.found_unchanged, c.found_changed) == ("done", 0, 3, 0)


async def test_a_ckan_source_waits_for_pr_2(db: psycopg.Connection, source: SourceConfig) -> None:
    ckan = replace(source, protocol=SourceProtocol.CKAN, filter=CkanFilter(None, "organization"))
    with pytest.raises(ConfigError, match="PR 2"):
        await run_harvest(db, ckan, gateway=_gateway(Catalogue(THREE)))


async def test_the_report_names_numbers_never_an_address(db: psycopg.Connection, source: SourceConfig) -> None:
    result = await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    text = report(source.source_id, result)
    assert "Funde neu 3" in text and "Ausdehnung unbekannt" in text
    assert "https://" not in text and HOST not in text


def test_listed_entries_point_to_their_run(require_postgres_env: None) -> None:
    with psycopg.connect() as connection:
        row = connection.execute(
            "SELECT confrelid::regclass::text FROM pg_constraint WHERE conname = 'earthx_listed_entry_run_fk'"
        ).fetchone()
    assert row == ("earthx_harvest_run",)
