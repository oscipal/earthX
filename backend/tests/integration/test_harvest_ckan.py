"""T-C: a harvest run of a CKAN catalogue against a real Postgres (M5-19 plan §4.2, §5, §11; A3).

The catalogue is synthetic (``httpx.MockTransport``, plan A5); nothing here reaches a real one. Each test harvests a
source of its own and deletes its rows after, since a run commits as it goes.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import psycopg
import pytest

from earthx.catalog.registry import Maturity
from earthx.catalog.sources import CkanFilter, SourceConfig, SourceProtocol
from earthx.discovery.harvest import report, run_harvest
from earthx.gateway import Gateway, Policy

pytestmark = pytest.mark.anyio

HOST = "ckan.example.org"
ENDPOINT = f"https://{HOST}/api/3/action"
_SINCE = re.compile(r"metadata_modified:\[(\S+) TO \*\]")


def _package(key: str, **changes: Any) -> dict[str, Any]:
    package = {
        "id": f"00000000-0000-4000-8000-{key:0>12}",
        "name": f"dataset-{key}",
        "title": f"Datensatz {key}",
        "notes": "Synthetisch.",
        "url": f"https://amt.example.org/daten/{key}",
        "maintainer": "Max Mustermann",
        "maintainer_email": "max@example.org",
        "license_id": "dl-by-de/2.0",
        "metadata_modified": "2026-01-01T00:00:00",
        "extras": [{"key": "publisher_name", "value": "Amt für Beispiele"}],
        "resources": [{"url": f"https://amt.example.org/daten/{key}.tif", "format": "GeoTIFF"}],
    }
    package.update(changes)
    return package


class Catalogue:
    """``package_search`` over ``packages``, at most ``size`` rows a page whatever is asked (like ``rows_max``).

    An incremental query gets the packages of ``changed`` instead of all. ``count_shift`` adds to the count from the
    second page on, as a catalogue does that grows while it is read.
    """

    def __init__(self, packages: list[dict[str, Any]], *, size: int = 2) -> None:
        self.packages, self.size = packages, size
        self.changed: list[dict[str, Any]] = []
        self.asked: list[httpx.QueryParams] = []
        self.count_shift = 0
        self.answer: Any = None
        #: Called after each page is served, to change the catalogue while it is read.
        self.after_page: Callable[[int], None] | None = None
        self.ignore_start = False

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        assert request.url.path == "/api/3/action/package_search"
        self.asked.append(request.url.params)
        if self.answer is not None:
            return httpx.Response(200, content=json.dumps(self.answer))
        incremental = "metadata_modified" in request.url.params.get("fq", "")
        matching = sorted(
            self.changed if incremental else self.packages, key=lambda p: str(p.get("id") if isinstance(p, dict) else p)
        )
        start = 0 if self.ignore_start else int(request.url.params["start"])
        rows = min(int(request.url.params["rows"]), self.size)
        count = len(matching) + (self.count_shift if start else 0)
        body = {"success": True, "result": {"count": count, "results": matching[start : start + rows]}}
        if self.after_page is not None:
            self.after_page(len(self.asked))
        return httpx.Response(200, content=json.dumps(body))


def _gateway(catalogue: Catalogue) -> Gateway:
    async def sleep(seconds: float) -> None:
        return None

    return Gateway(
        Policy(allowed_hosts=frozenset({HOST}), obey_robots=True),
        transport=httpx.MockTransport(catalogue.handle),
        resolve=lambda host, port: ("93.184.216.34",),
        sleep=sleep,
    )


@pytest.fixture
def source() -> SourceConfig:
    return SourceConfig(
        source_id=f"t-{uuid.uuid4().hex[:12]}",
        protocol=SourceProtocol.CKAN,
        endpoint=ENDPOINT,
        catalog_page="https://portal.example.org/dataset/{name}",
        filter=CkanFilter(None, "publisher_name"),
        max_requests_per_run=20,
        full_every_days=7,
        maturity=Maturity.STABLE,
        enabled=True,
    )


@pytest.fixture
def db(require_postgres_env: None, source: SourceConfig) -> Iterator[psycopg.Connection]:
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
    return {key[-1:]: (state, reason, extent) for key, state, reason, extent in rows}


THREE = [
    _package("1"),
    _package("2", extras=[{"key": "spatial", "value": '{"type": "Point", "coordinates": [9.5, 51.0]}'}]),
    _package("3", title=""),
]


async def test_a_first_run_reads_the_whole_listing_page_by_page(db: psycopg.Connection, source: SourceConfig) -> None:
    catalogue = Catalogue(THREE)
    result = await run_harvest(db, source, gateway=_gateway(catalogue))
    assert (result.kind, result.status, result.gone_unchecked) == ("full", "done", None)
    # Each page starts with the last package of the one before, so that a shift of the listing shows (A8).
    assert [(p["start"], p["rows"], p["sort"], p.get("fq")) for p in catalogue.asked] == [
        ("0", "100", "id asc", None),
        ("1", "100", "id asc", None),
    ]
    c = result.counts
    assert (c.requests, c.found_new, c.invalid, c.extent_unknown) == (2, 3, 1, 1)
    assert _states(db, source) == {
        "1": ("extracted", None, False),
        "2": ("extracted", None, True),
        "3": ("invalid", "no_title", None),
    }
    assert "Lauf" in report(source.source_id, result) and "(voll)" in report(source.source_id, result)


async def test_no_person_is_kept_in_the_intermediate_form(db: psycopg.Connection, source: SourceConfig) -> None:
    await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    stored = db.execute(
        "SELECT extracted::text FROM public.earthx_record_state WHERE source_id = %s AND state = 'extracted'",
        (source.source_id,),
    ).fetchall()
    assert stored and not any("Mustermann" in text or "max@" in text for (text,) in stored)


async def test_the_next_run_asks_only_for_what_changed_since_the_last_one(
    db: psycopg.Connection, source: SourceConfig
) -> None:
    first = await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    started = db.execute(
        "SELECT started_at FROM public.earthx_harvest_run WHERE run_id = %s", (first.run_id,)
    ).fetchone()[0]
    catalogue = Catalogue(THREE[:1])
    catalogue.changed = [_package("1", title="Neuer Titel"), _package("4")]
    result = await run_harvest(db, source, gateway=_gateway(catalogue))
    assert result.kind == "incremental"
    since = _SINCE.fullmatch(catalogue.asked[0]["fq"])
    assert since is not None
    assert datetime.strptime(since[1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC) == (
        started - timedelta(hours=1)
    ).astimezone(UTC).replace(microsecond=0)
    c = result.counts
    assert (c.found_new, c.found_changed, c.gone) == (1, 1, 0)
    # Packages the incremental listing did not name are not gone (A3).
    assert _states(db, source)["2"] == ("extracted", None, True)
    assert result.gone_unchecked == "incremental"
    assert "weg nicht geprüft (inkrementell)" in report(source.source_id, result)
    assert "(inkrementell)" in report(source.source_id, result).splitlines()[0]


async def test_an_unchanged_package_does_no_work(db: psycopg.Connection, source: SourceConfig) -> None:
    # Acceptance M5 §7 point 3 for CKAN: the hash of each package decides.
    await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    catalogue = Catalogue([])
    catalogue.changed = THREE
    result = await run_harvest(db, source, gateway=_gateway(catalogue))
    c = result.counts
    assert (c.found_new, c.found_changed, c.found_unchanged) == (0, 0, 3)


async def test_the_filter_of_the_source_stays_in_an_incremental_query(
    db: psycopg.Connection, source: SourceConfig
) -> None:
    filtered = replace(source, filter=CkanFilter("res_format:GeoTIFF", "publisher_name"))
    first = Catalogue(THREE)
    await run_harvest(db, filtered, gateway=_gateway(first))
    assert first.asked[0]["fq"] == "(res_format:GeoTIFF)"
    second = Catalogue(THREE)
    await run_harvest(db, filtered, gateway=_gateway(second))
    assert re.fullmatch(r"\(res_format:GeoTIFF\) AND metadata_modified:\[\S+Z TO \*\]", second.asked[0]["fq"])


async def test_a_full_run_marks_what_is_missing_gone(db: psycopg.Connection, source: SourceConfig) -> None:
    await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    result = await run_harvest(db, source, full=True, gateway=_gateway(Catalogue(THREE[:2])))
    assert (result.kind, result.counts.gone, result.gone_unchecked) == ("full", 1, None)
    assert _states(db, source)["3"] == ("gone", None, None)


async def test_a_full_run_is_due_after_full_every_days(db: psycopg.Connection, source: SourceConfig) -> None:
    await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    db.execute(
        "UPDATE public.earthx_harvest_run SET started_at = started_at - interval '7 days' WHERE source_id = %s",
        (source.source_id,),
    )
    result = await run_harvest(db, source, gateway=_gateway(Catalogue(THREE[:2])))
    assert (result.kind, result.counts.gone) == ("full", 1)


async def test_an_interrupted_run_does_not_count_as_the_last_one(db: psycopg.Connection, source: SourceConfig) -> None:
    budget = replace(source, max_requests_per_run=1)
    stopped = await run_harvest(db, budget, gateway=_gateway(Catalogue(THREE)))
    assert (stopped.kind, stopped.status, stopped.stop_reason) == ("full", "interrupted", "request_budget")
    assert stopped.counts.gone == 0 and stopped.gone_unchecked is None
    again = await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    assert again.kind == "full"


async def test_a_listing_that_moves_while_it_is_read_marks_nothing_gone(
    db: psycopg.Connection, source: SourceConfig
) -> None:
    await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    catalogue = Catalogue(THREE[:2], size=1)
    catalogue.count_shift = 1
    result = await run_harvest(db, source, full=True, gateway=_gateway(catalogue))
    assert (result.status, result.counts.gone, result.gone_unchecked) == ("done", 0, "listing_moved")
    assert _states(db, source)["3"] == ("invalid", "no_title", None)
    assert "Liste hat sich während des Laufs geändert" in report(source.source_id, result)


@pytest.mark.parametrize(
    "answer",
    [
        {"success": False, "error": {"message": "bad fq"}},
        {"success": True, "result": {"count": "3", "results": []}},
        {"success": True, "result": {"count": -1, "results": []}},
        {"success": True, "result": {"count": 1, "results": {}}},
        {"success": True},
        ["not", "a", "listing"],
    ],
)
async def test_an_answer_that_is_no_listing_fails_the_run(
    db: psycopg.Connection, source: SourceConfig, answer: Any
) -> None:
    catalogue = Catalogue(THREE)
    catalogue.answer = answer
    result = await run_harvest(db, source, gateway=_gateway(catalogue))
    assert (result.status, result.stop_reason) == ("failed", "shape")
    assert _states(db, source) == {}


async def test_a_package_of_foreign_shape_does_not_end_the_run(db: psycopg.Connection, source: SourceConfig) -> None:
    odd = [_package("1"), _package("2", title={"de": 5}), {"id": "../bad", "title": "x"}, "text"]
    result = await run_harvest(db, source, gateway=_gateway(Catalogue(odd, size=10)))
    assert result.status == "done" and result.without_key == 2
    assert _states(db, source) == {"1": ("extracted", None, False), "2": ("invalid", "no_title", None)}


def _since(catalogue: Catalogue) -> datetime:
    match = _SINCE.fullmatch(catalogue.asked[0]["fq"])
    assert match is not None
    return datetime.strptime(match[1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _started(db: psycopg.Connection, run_id: int) -> datetime:
    started = db.execute("SELECT started_at FROM public.earthx_harvest_run WHERE run_id = %s", (run_id,)).fetchone()[0]
    return (started - timedelta(hours=1)).astimezone(UTC).replace(microsecond=0)


async def test_a_reextract_asks_nothing_and_finds_no_change(db: psycopg.Connection, source: SourceConfig) -> None:
    first = await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    result = await run_harvest(db, source, gateway=None, reextract=True)
    c = result.counts
    assert (result.kind, c.requests, c.found_changed, c.found_unchanged) == ("reextract", 0, 0, 3)
    # A re-extract asks the source nothing, so it is no last run for the next incremental one.
    catalogue = Catalogue(THREE)
    nxt = await run_harvest(db, source, gateway=_gateway(catalogue))
    assert nxt.kind == "incremental" and _since(catalogue) == _started(db, first.run_id)


async def test_an_incremental_listing_that_moves_does_not_count_as_the_last_run(
    db: psycopg.Connection, source: SourceConfig
) -> None:
    first = await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    moving = Catalogue([], size=1)
    moving.changed = THREE[:2]
    moving.count_shift = 1
    result = await run_harvest(db, source, gateway=_gateway(moving))
    assert (result.kind, result.status, result.stop_reason) == ("incremental", "interrupted", "listing_moved")
    assert "der nächste Lauf fragt ab dem Lauf davor" in report(source.source_id, result)
    catalogue = Catalogue([])
    await run_harvest(db, source, gateway=_gateway(catalogue))
    assert _since(catalogue) == _started(db, first.run_id)


async def test_a_package_skipped_by_a_shift_under_the_same_count_is_noticed(
    db: psycopg.Connection, source: SourceConfig
) -> None:
    # While the first page is read, a package before the offset goes and one after it comes: the count stays, but the
    # second page no longer starts with the last package of the first, so nothing is marked gone.
    four = [_package(str(i)) for i in range(1, 5)]
    await run_harvest(db, source, gateway=_gateway(Catalogue(four)))
    catalogue = Catalogue(four)

    def shift(pages: int) -> None:
        if pages == 1:
            catalogue.packages = [four[1], four[2], four[3], _package("9")]

    catalogue.after_page = shift
    result = await run_harvest(db, source, full=True, gateway=_gateway(catalogue))
    assert (result.status, result.counts.gone, result.gone_unchecked) == ("done", 0, "listing_moved")


async def test_an_empty_full_listing_marks_nothing_gone(db: psycopg.Connection, source: SourceConfig) -> None:
    # A rebuilt index or a filter that no longer matches is no evidence that every find is gone.
    await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    result = await run_harvest(db, source, full=True, gateway=_gateway(Catalogue([])))
    assert (result.status, result.counts.gone, result.gone_unchecked) == ("done", 0, "listing_empty")
    assert "weg nicht geprüft (Liste leer)" in report(source.source_id, result)
    assert _states(db, source)["1"] == ("extracted", None, False)


async def test_a_catalogue_that_ignores_the_offset_fails_the_run(db: psycopg.Connection, source: SourceConfig) -> None:
    catalogue = Catalogue([_package(str(i)) for i in range(1, 8)], size=3)
    catalogue.ignore_start = True
    result = await run_harvest(db, source, gateway=_gateway(catalogue))
    assert (result.status, result.stop_reason, result.counts.requests) == ("failed", "shape", 2)


async def test_the_publisher_field_of_the_source_is_part_of_the_version(
    db: psycopg.Connection, source: SourceConfig
) -> None:
    await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    by_organization = replace(source, filter=CkanFilter(None, "organization"))
    # An incremental run that names no package still judges the kept finds again from their raw answers: only the one
    # with a publisher changes.
    result = await run_harvest(db, by_organization, gateway=_gateway(Catalogue([])))
    assert result.kind == "incremental"
    assert (result.counts.requests, result.counts.found_changed, result.counts.found_unchanged) == (1, 1, 2)
    again = await run_harvest(db, by_organization, gateway=_gateway(Catalogue([])))
    assert (again.counts.found_changed, again.counts.found_unchanged) == (0, 0)
