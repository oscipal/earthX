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

from earthx.catalog.registry import ConfigError, Maturity
from earthx.catalog.sources import CkanFilter, RobotsException, SourceConfig, SourceProtocol
from earthx.discovery.harvest import SourceResting, measure, report, run_harvest
from earthx.gateway import Gateway, Policy

pytestmark = pytest.mark.anyio

HOST = "ckan.example.org"
ENDPOINT = f"https://{HOST}/api/3/action"
_SINCE = re.compile(r"metadata_modified:\[(\S+) TO \*\]")
_AFTER = re.compile(r'id:\{"([^"]+)" TO \*\]')


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
    """``package_search`` by key over ``packages``: sorted by id, the ids after the one in ``fq``
    (``id:{"<key>" TO *]``), at most ``size`` rows a page whatever is asked (like ``rows_max``). Every page must be asked
    with ``start=0`` (keyset paging, plan §12.7).

    An incremental query gets the packages of ``changed`` instead of all.
    """

    def __init__(self, packages: list[dict[str, Any]], *, size: int = 2) -> None:
        self.packages, self.size = packages, size
        self.changed: list[dict[str, Any]] = []
        self.asked: list[httpx.QueryParams] = []
        self.answer: Any = None
        #: Called after each page is served, to change the catalogue while it is read.
        self.after_page: Callable[[int], None] | None = None
        #: A catalogue that ignores the filter by key and answers the first page again.
        self.ignore_key = False
        self.robots = "User-agent: *\nAllow: /\n"
        #: From this page on (0 the first one), pages are answered with this status (429: slow down; 503: down).
        self.refuse_from: int | None = None
        self.refuse_status = 429
        self.retry_after: str | None = None
        self.pages_served = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=self.robots)
        assert request.url.path == "/api/3/action/package_search"
        assert request.url.params["start"] == "0"
        self.asked.append(request.url.params)
        if self.answer is not None:
            return httpx.Response(200, content=json.dumps(self.answer))
        if self.refuse_from is not None and self.pages_served >= self.refuse_from:
            headers = {} if self.retry_after is None else {"retry-after": self.retry_after}
            return httpx.Response(self.refuse_status, text="slow down", headers=headers)
        fq = request.url.params.get("fq", "")
        incremental = "metadata_modified" in fq
        after = _AFTER.search(fq)
        matching = sorted(
            self.changed if incremental else self.packages, key=lambda p: str(p.get("id") if isinstance(p, dict) else p)
        )
        if after is not None and not self.ignore_key:
            matching = [p for p in matching if str(p.get("id") if isinstance(p, dict) else p) > after[1]]
        rows = min(int(request.url.params["rows"]), self.size)
        body = {"success": True, "result": {"count": len(matching), "results": matching[:rows]}}
        self.pages_served += 1
        if self.after_page is not None:
            self.after_page(self.pages_served)
        return httpx.Response(200, content=json.dumps(body))


def _gateway(catalogue: Catalogue, source: SourceConfig | None = None) -> Gateway:
    async def sleep(seconds: float) -> None:
        return None

    exception = None if source is None else source.robots_exception
    return Gateway(
        Policy(
            allowed_hosts=frozenset({HOST}),
            obey_robots=True,
            robots_exceptions={} if exception is None else {HOST: (exception.path,)},
            retry_rate_limited=False,
        ),
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
        max_pages_per_run=None,
        full_every_days=7,
        robots_exception=None,
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
    # Keyset paging (plan §12.7): always from the start, the next page after the last key read.
    assert [(p["start"], p["rows"], p["sort"], p.get("fq")) for p in catalogue.asked] == [
        ("0", "100", "id asc", None),
        ("0", "100", "id asc", 'id:{"00000000-0000-4000-8000-000000000002" TO *]'),
    ]
    c = result.counts
    assert (c.requests, c.found_new, c.invalid, c.extent_unknown) == (2, 3, 1, 1)
    assert _states(db, source) == {
        "1": ("extracted", None, False),
        "2": ("extracted", None, True),
        "3": ("invalid", "no_title", None),
    }
    assert "Lauf" in report(source, result) and "(voll)" in report(source, result)


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
    assert "weg nicht geprüft (inkrementell)" in report(source, result)
    assert "(inkrementell)" in report(source, result).splitlines()[0]


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
        "UPDATE public.earthx_harvest_source SET full_started_at = full_started_at - interval '7 days'"
        " WHERE source_id = %s",
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
    match = _SINCE.search(catalogue.asked[0]["fq"])
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


async def test_packages_that_come_or_go_while_a_pass_reads_move_no_page(
    db: psycopg.Connection, source: SourceConfig
) -> None:
    # Under offsets a package before the offset that goes shifted the rest by one and one was skipped (A8). By key, the
    # next page asks for the ids after the last one read, whatever came or went before it.
    four = [_package(str(i)) for i in range(1, 5)]
    await run_harvest(db, source, gateway=_gateway(Catalogue(four)))
    catalogue = Catalogue(four)

    def shift(pages: int) -> None:
        if pages == 1:
            catalogue.packages = [four[1], four[2], four[3], _package("9")]

    catalogue.after_page = shift
    result = await run_harvest(db, source, full=True, gateway=_gateway(catalogue))
    assert (result.status, result.gone_unchecked, result.counts.found_new) == ("done", None, 1)
    states = _states(db, source)
    assert all(states[k][0] == "extracted" for k in "12349")
    # The package that went is gone after the next full pass.
    again = await run_harvest(db, source, full=True, gateway=_gateway(catalogue))
    assert again.counts.gone == 1 and _states(db, source)["1"][0] == "gone"


async def test_an_empty_full_listing_marks_nothing_gone(db: psycopg.Connection, source: SourceConfig) -> None:
    # A rebuilt index or a filter that no longer matches is no evidence that every find is gone.
    await run_harvest(db, source, gateway=_gateway(Catalogue(THREE)))
    result = await run_harvest(db, source, full=True, gateway=_gateway(Catalogue([])))
    assert (result.status, result.counts.gone, result.gone_unchecked) == ("done", 0, "listing_empty")
    assert "weg nicht geprüft (Liste leer)" in report(source, result)
    assert _states(db, source)["1"] == ("extracted", None, False)


async def test_a_catalogue_that_ignores_the_key_fails_the_run(db: psycopg.Connection, source: SourceConfig) -> None:
    catalogue = Catalogue([_package(str(i)) for i in range(1, 8)], size=3)
    catalogue.ignore_key = True
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


CKAN_ROBOTS = "User-agent: *\nDisallow: /api/\nCrawl-delay: 10\n"


async def test_robots_txt_stops_a_source_without_an_exception(db: psycopg.Connection, source: SourceConfig) -> None:
    catalogue = Catalogue(THREE)
    catalogue.robots = CKAN_ROBOTS
    result = await run_harvest(db, source, gateway=_gateway(catalogue, source))
    assert (result.status, result.stop_reason, result.robots_waived) == ("interrupted", "robots", False)
    assert catalogue.asked == [] and _states(db, source) == {}
    assert "robots_exception in der Quell-Datei" in report(source, result)


async def test_the_exception_of_the_source_file_reads_its_api_and_the_report_says_so(
    db: psycopg.Connection, source: SourceConfig
) -> None:
    # Otto, 18.11.2026: the documented metadata API despite Disallow: /api/, named in the run report.
    excepted = replace(source, robots_exception=RobotsException("/api/3/action/", "https://docs.example.org/api"))
    catalogue = Catalogue(THREE)
    catalogue.robots = CKAN_ROBOTS
    result = await run_harvest(db, excepted, gateway=_gateway(catalogue, excepted))
    assert (result.status, result.counts.found_new, result.robots_waived) == ("done", 3, True)
    assert (
        "robots.txt: Ausnahme für ckan.example.org/api/3/action/ (angewandt; Beleg in der Quell-Datei, Crawl-delay gilt)"
        in report(excepted, result)
    )


async def test_an_exception_robots_txt_does_not_need_is_reported_as_unused(
    db: psycopg.Connection, source: SourceConfig
) -> None:
    excepted = replace(source, robots_exception=RobotsException("/api/3/action/", "https://docs.example.org/api"))
    result = await run_harvest(db, excepted, gateway=_gateway(Catalogue(THREE), excepted))
    assert result.status == "done" and not result.robots_waived
    assert "(nicht gebraucht;" in report(excepted, result)


async def _no_wait(seconds: float) -> None:
    return None


def _next_day(db: psycopg.Connection, source: SourceConfig) -> None:
    """The rest after a run that ended rate_limited is over."""
    db.execute("UPDATE public.earthx_harvest_source SET rest_until = NULL WHERE source_id = %s", (source.source_id,))


FIVE = [_package(str(i)) for i in range(1, 6)]


async def test_a_full_pass_the_source_slows_down_keeps_its_place_and_goes_on(
    db: psycopg.Connection, source: SourceConfig
) -> None:
    # Otto, 18.11.2026: opendata.swiss answered 429 from page 103 on; the run waited, stopped and the next one goes on
    # from that page instead of from the start.
    catalogue = Catalogue(FIVE, size=2)
    catalogue.refuse_from = 1
    first = await run_harvest(db, source, gateway=_gateway(catalogue), sleep=_no_wait)
    assert (first.kind, first.status, first.stop_reason) == ("full", "interrupted", "rate_limited")
    assert first.rate_limited > 1 and first.resume_at == 2 and first.counts.found_new == 2
    text = report(source, first)
    assert "Quelle bat um Pause" in text and "setzt den vollen Durchgang nach 2 Paketen fort" in text
    catalogue.refuse_from = None
    catalogue.asked.clear()
    _next_day(db, source)
    second = await run_harvest(db, source, gateway=_gateway(catalogue), sleep=_no_wait)
    assert (second.kind, second.status, second.resumed_at, second.resume_at) == ("full", "done", 2, None)
    assert catalogue.asked[0]["fq"] == 'id:{"00000000-0000-4000-8000-000000000002" TO *]'
    assert (second.counts.found_new, second.counts.gone, second.gone_unchecked) == (3, 0, None)
    assert "Voller Durchgang fortgesetzt nach 2 Paketen" in report(source, second)


async def test_gone_after_a_pass_over_several_runs_is_what_none_of_them_saw(
    db: psycopg.Connection, source: SourceConfig
) -> None:
    await run_harvest(db, source, gateway=_gateway(Catalogue(FIVE, size=2)))
    db.execute(
        "UPDATE public.earthx_harvest_source SET full_started_at = full_started_at - interval '7 days'"
        " WHERE source_id = %s",
        (source.source_id,),
    )
    four = Catalogue(FIVE[:4], size=2)
    four.refuse_from = 1
    stopped = await run_harvest(db, source, gateway=_gateway(four), sleep=_no_wait)
    assert stopped.status == "interrupted" and stopped.counts.gone == 0
    four.refuse_from = None
    _next_day(db, source)
    done = await run_harvest(db, source, gateway=_gateway(four), sleep=_no_wait)
    # 1 was seen only by the first run of the pass, 5 by none of its runs.
    assert done.counts.gone == 1
    states = _states(db, source)
    assert states["5"][0] == "gone" and states["1"][0] == "extracted"


async def test_a_source_failing_on_the_way_pauses_the_pass(db: psycopg.Connection, source: SourceConfig) -> None:
    catalogue = Catalogue(FIVE, size=2)
    catalogue.refuse_from, catalogue.refuse_status = 1, 503
    result = await run_harvest(db, source, gateway=_gateway(catalogue), sleep=_no_wait)
    assert (result.status, result.stop_reason, result.resume_at, result.rate_limited) == (
        "interrupted",
        "upstream",
        2,
        0,
    )


async def test_after_a_pass_over_several_runs_changes_are_asked_from_its_start(
    db: psycopg.Connection, source: SourceConfig
) -> None:
    catalogue = Catalogue(FIVE, size=2)
    catalogue.refuse_from = 1
    first = await run_harvest(db, source, gateway=_gateway(catalogue), sleep=_no_wait)
    catalogue.refuse_from = None
    _next_day(db, source)
    await run_harvest(db, source, gateway=_gateway(catalogue), sleep=_no_wait)
    nxt = Catalogue([])
    result = await run_harvest(db, source, gateway=_gateway(nxt))
    # Pages the first run read may have changed while the pass stood still: the next run asks from the pass's start.
    assert result.kind == "incremental" and _since(nxt) == _started(db, first.run_id)


async def test_full_goes_on_with_an_open_pass(db: psycopg.Connection, source: SourceConfig) -> None:
    catalogue = Catalogue(FIVE, size=2)
    catalogue.refuse_from = 1
    await run_harvest(db, source, gateway=_gateway(catalogue), sleep=_no_wait)
    catalogue.refuse_from = None
    _next_day(db, source)
    result = await run_harvest(db, source, full=True, gateway=_gateway(catalogue), sleep=_no_wait)
    assert (result.kind, result.resumed_at) == ("full", 2)


async def test_after_rate_limited_the_source_rests_until_the_next_day(
    db: psycopg.Connection, source: SourceConfig
) -> None:
    # Otto, 18.11.2026: opendata.swiss refused for hours; the next run must not ask again before the next day.
    catalogue = Catalogue(FIVE, size=2)
    catalogue.refuse_from = 0
    first = await run_harvest(db, source, gateway=_gateway(catalogue), sleep=_no_wait)
    assert first.stop_reason == "rate_limited" and first.rest_until is not None
    assert first.rest_until.astimezone(UTC).time() == datetime.min.time()
    assert first.rest_until - datetime.now(UTC) <= timedelta(days=1)
    assert "vorher startet kein Lauf" in report(source, first)
    asked = len(catalogue.asked)
    with pytest.raises(SourceResting) as raised:
        await run_harvest(db, source, gateway=_gateway(catalogue), sleep=_no_wait)
    assert raised.value.until == first.rest_until and len(catalogue.asked) == asked
    # A re-extract asks the source nothing and may run.
    assert (await run_harvest(db, source, gateway=None, reextract=True)).status == "done"


async def test_a_retry_after_sets_the_rest(db: psycopg.Connection, source: SourceConfig) -> None:
    catalogue = Catalogue(FIVE, size=2)
    catalogue.refuse_from = 0
    catalogue.retry_after = "7200"
    result = await run_harvest(db, source, gateway=_gateway(catalogue), sleep=_no_wait)
    assert result.stop_reason == "rate_limited"
    left = result.rest_until - datetime.now(UTC)
    assert timedelta(minutes=110) < left <= timedelta(hours=2)


async def test_a_run_reads_at_most_its_pages_and_the_next_goes_on(db: psycopg.Connection, source: SourceConfig) -> None:
    capped = replace(source, max_pages_per_run=2)
    seven = [_package(str(i)) for i in range(1, 8)]
    catalogue = Catalogue(seven, size=2)
    first = await run_harvest(db, capped, gateway=_gateway(catalogue))
    assert (first.status, first.stop_reason, first.counts.requests, first.resume_at) == (
        "interrupted",
        "page_budget",
        2,
        4,
    )
    assert "Seiten je Lauf erreicht" in report(capped, first)
    second = await run_harvest(db, capped, gateway=_gateway(catalogue))
    # 5 and 6, then 7: the last page ends the listing, so the budget does not stop the pass.
    assert (second.status, second.resumed_at, second.resume_at, second.gone_unchecked) == ("done", 4, None, None)
    assert len(_states(db, capped)) == 7


async def test_an_incremental_pass_goes_on_over_runs_under_a_cap(db: psycopg.Connection, source: SourceConfig) -> None:
    capped = replace(source, max_pages_per_run=1)
    first = await run_harvest(db, capped, gateway=_gateway(Catalogue(THREE, size=10)))
    assert first.status == "done"
    changed = Catalogue([], size=2)
    changed.changed = [_package("4"), _package("5"), _package("6")]
    second = await run_harvest(db, capped, gateway=_gateway(changed))
    assert (second.kind, second.status, second.stop_reason) == ("incremental", "interrupted", "page_budget")
    since = _since(changed)
    changed.asked.clear()
    third = await run_harvest(db, capped, gateway=_gateway(changed))
    # The same lower bound, after the last key the pass read.
    assert (third.kind, third.resumed_at, third.status) == ("incremental", 2, "done")
    assert _since(changed) == since and _AFTER.search(changed.asked[0]["fq"])[1] == "00000000-0000-4000-8000-000000000005"
    assert "Inkrementeller Durchgang fortgesetzt nach 2 Paketen" in report(capped, third)
    # After the pass went through, the next one asks from the start of the pass.
    nxt = Catalogue([])
    await run_harvest(db, capped, gateway=_gateway(nxt))
    assert _since(nxt) == _started(db, second.run_id)


async def test_measure_keeps_the_rest_and_the_pages_of_a_run(db: psycopg.Connection, source: SourceConfig) -> None:
    # Otto, 18.11.2026: --measure under the same budget and rest as a run.
    catalogue = Catalogue(THREE, size=10)
    assert "Messung einer Seite mit 3 Paketen" in await measure(db, source, _gateway(catalogue))
    with pytest.raises(ConfigError, match="more than max_pages_per_run"):
        await measure(db, replace(source, max_pages_per_run=1), _gateway(catalogue))
    catalogue.refuse_from = 0
    with pytest.raises(SourceResting) as raised:
        await measure(db, source, _gateway(catalogue))
    asked = len(catalogue.asked)
    with pytest.raises(SourceResting) as again:
        await measure(db, source, _gateway(catalogue))
    assert again.value.until == raised.value.until and len(catalogue.asked) == asked
    with pytest.raises(SourceResting):
        await run_harvest(db, source, gateway=_gateway(catalogue), sleep=_no_wait)
