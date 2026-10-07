"""The progress stream over HTTP, against a real server in the test's own loop (adr/0013 §5.4, §8 points 6 and 12).

``httpx.ASGITransport`` hands a body over only when the app has finished it, which a stream never
does; so these tests start ``uvicorn`` on a free local port, in the same event loop as the hub, and read
the stream as a browser would. The worker's messages are sent from a second connection.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import psycopg
import pytest
import uvicorn

from earthx.api.job_events import APPLICATION_NAME
from earthx.jobs import queue
from tests.earthx.api.conftest import Rig
from tests.earthx.api.test_intake import order
from tests.earthx.api.test_processing_route import finish, place, placed

pytestmark = pytest.mark.anyio


@pytest.fixture
async def live(rig: Rig) -> AsyncIterator[str]:
    config = uvicorn.Config(rig.app, host="127.0.0.1", port=0, log_level="warning", lifespan="off", access_log=False)
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        await rig.events.stop()  # ends every open stream, so the server may shut down
        server.should_exit = True
        await asyncio.wait_for(task, 15)


class Stream:
    """One open ``text/event-stream``, read by a task into a queue, so a test can wait with a timeout."""

    def __init__(self, client: httpx.AsyncClient, url: str) -> None:
        self._cm = client.stream("GET", url)
        self.response: httpx.Response
        self.queue: asyncio.Queue[tuple[str | None, dict[str, Any]] | None] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    async def open(self) -> Stream:
        self.response = await self._cm.__aenter__()
        self._task = asyncio.create_task(self._pump())
        return self

    async def _pump(self) -> None:
        event: str | None = None
        data: list[str] = []
        try:
            async for line in self.response.aiter_lines():
                if line.startswith(":"):
                    continue  # a keep-alive comment
                if line.startswith("event:"):
                    event = line.removeprefix("event:").strip()
                elif line.startswith("data:"):
                    data.append(line.removeprefix("data:").strip())
                elif line == "" and (event or data):
                    await self.queue.put((event, json.loads("\n".join(data))))
                    event, data = None, []
        except (httpx.ReadError, httpx.RemoteProtocolError, asyncio.CancelledError):
            pass
        finally:
            await self.queue.put(None)

    async def next(self, timeout: float = 10.0) -> tuple[str | None, dict[str, Any]] | None:
        """The next event, ``None`` when the stream has ended."""
        return await asyncio.wait_for(self.queue.get(), timeout)

    async def nothing(self, wait: float = 0.5) -> None:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(self.queue.get(), wait)

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
        await self._cm.__aexit__(None, None, None)


async def follow(live: str, job_id: str, client: httpx.AsyncClient | None = None) -> Stream:
    client = client or httpx.AsyncClient(timeout=30)
    return await Stream(client, f"{live}/processing/jobs/{job_id}/events").open()


def set_state(db: psycopg.Connection, run_id: int, progress: int, status: str = "running") -> None:
    db.execute("UPDATE public.earthx_run SET progress = %s, status = %s WHERE run_id = %s", (progress, status, run_id))
    queue.notify_progress(db, run_id, progress, status)


def run_of(db: psycopg.Connection) -> int:
    row = db.execute("SELECT run_id FROM public.earthx_run").fetchone()
    assert row is not None
    return row[0]


async def until(condition: Callable[[], bool], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("not true in time")


class TestOneStream:
    async def test_the_row_comes_first_then_every_change_then_the_end(self, rig: Rig, live: str) -> None:
        job_id = await placed(rig)
        run_id = run_of(rig.db)
        set_state(rig.db, run_id, 10)
        stream = await follow(live, job_id)
        try:
            assert stream.response.status_code == 200
            assert stream.response.headers["content-type"].startswith("text/event-stream")
            assert stream.response.headers["cache-control"] == "no-store"
            first = await stream.next()
            assert first is not None and first[0] == "status"
            assert (first[1]["status"], first[1]["progress"], first[1]["jobID"]) == ("running", 10, job_id)
            set_state(rig.db, run_id, 55)
            second = await stream.next()
            assert second is not None and second[1]["progress"] == 55
            finish(rig.db, job_id)
            queue.notify_progress(rig.db, run_id, 100, "successful")
            last = await stream.next()
            assert last is not None and last[1]["status"] == "successful"
            assert "http://www.opengis.net/def/rel/ogc/1.0/results" in {link["rel"] for link in last[1]["links"]}
            assert await stream.next() is None, "the server ends the stream with the job"
        finally:
            await stream.close()

    async def test_an_event_is_the_same_document_the_status_route_gives(self, rig: Rig, live: str) -> None:
        job_id = await placed(rig)
        stream = await follow(live, job_id)
        try:
            event = await stream.next()
            assert event is not None
            assert event[1] == (await rig.client.get(f"/processing/jobs/{job_id}")).json()
        finally:
            await stream.close()

    async def test_a_job_that_is_over_gives_its_state_once_and_the_stream_ends(self, rig: Rig, live: str) -> None:
        job_id = await placed(rig)
        finish(rig.db, job_id, status="failed", kind="source_5xx")
        stream = await follow(live, job_id)
        try:
            event = await stream.next()
            assert event is not None and (event[1]["status"], event[1]["message"]) == ("failed", "The source failed")
            assert await stream.next() is None
        finally:
            await stream.close()

    async def test_a_message_that_changes_nothing_is_not_sent_again(self, rig: Rig, live: str) -> None:
        job_id = await placed(rig)
        run_id = run_of(rig.db)
        stream = await follow(live, job_id)
        try:
            assert await stream.next() is not None
            queue.notify_progress(rig.db, run_id, 0, "accepted")
            await stream.nothing()
        finally:
            await stream.close()

    async def test_the_job_being_dismissed_while_followed_ends_the_stream_with_that(self, rig: Rig, live: str) -> None:
        first, second = await placed(rig), await placed(rig)
        stream = await follow(live, first)
        try:
            assert await stream.next() is not None
            assert (await rig.client.delete(f"/processing/jobs/{first}")).status_code == 200
            event = await stream.next()
            assert event is not None and event[1]["status"] == "dismissed"
            assert await stream.next() is None
            assert (await rig.client.get(f"/processing/jobs/{second}")).json()["status"] == "accepted"
        finally:
            await stream.close()

    async def test_a_client_that_leaves_is_forgotten(self, rig: Rig, live: str) -> None:
        job_id = await placed(rig)
        stream = await follow(live, job_id)
        assert await stream.next() is not None
        assert rig.events.followers == 1
        await stream.close()
        await until(lambda: rig.events.followers == 0)

    async def test_stopping_the_process_ends_the_stream(self, rig: Rig, live: str) -> None:
        job_id = await placed(rig)
        stream = await follow(live, job_id)
        try:
            assert await stream.next() is not None
            await rig.events.stop()
            assert await stream.next() is None
        finally:
            await stream.close()


class TestWhoIsTurnedAway:
    """The decision is made before the stream starts, as a plain answer."""

    @pytest.mark.parametrize("bad", ["A" * 22, "short", "A" * 23, "%2e%2e"])
    async def test_a_job_that_is_not_there_is_a_404_and_no_stream(self, rig: Rig, live: str, bad: str) -> None:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{live}/processing/jobs/{bad}/events")
        assert response.status_code == 404
        assert response.headers["content-type"] == "application/problem+json"
        assert rig.events.followers == 0

    async def test_a_dismissed_and_an_expired_job_are_a_404_too(self, rig: Rig, live: str) -> None:
        dismissed, expired = await placed(rig, None), await placed(rig)
        await rig.client.delete(f"/processing/jobs/{dismissed}")
        finish(rig.db, expired, expires="-1 hour")
        async with httpx.AsyncClient() as client:
            for job_id in (dismissed, expired):
                assert (await client.get(f"{live}/processing/jobs/{job_id}/events")).status_code == 404

    async def test_a_full_process_says_so_and_keeps_those_it_has(
        self, rig: Rig, live: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(rig.events, "_max", 1)
        first, second = await placed(rig), await placed(rig)
        run_id = run_of(rig.db)
        stream = await follow(live, first)
        try:
            assert await stream.next() is not None
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{live}/processing/jobs/{second}/events")
            assert response.status_code == 503 and response.headers["retry-after"] == "5"
            assert response.headers["content-type"] == "application/problem+json"
            assert rig.events.followers == 1
            set_state(rig.db, run_id, 30)
            event = await stream.next()
            assert event is not None and event[1]["progress"] == 30
        finally:
            await stream.close()


class TestManyClients:
    async def test_fifty_streams_are_one_connection_of_this_process(self, rig: Rig, live: str) -> None:
        jobs: list[str] = []
        # Five different orders, ten equal ones of each: five runs, ten jobs on every one.
        variants = [
            order(assets=("red",)),
            order(assets=("nir",)),
            order(assets=("red", "nir")),
            order(assets=("red",), steps=[]),
            order(assets=("nir",), steps=[]),
        ]
        for document in variants:
            for _ in range(10):
                response = await place(rig, document)
                assert response.status_code == 201, response.text
                jobs.append(response.json()["jobID"])
        run_ids = [row[0] for row in rig.db.execute("SELECT run_id FROM public.earthx_run").fetchall()]
        assert len(jobs) == 50 and len(run_ids) == 5
        async with httpx.AsyncClient(limits=httpx.Limits(max_connections=60), timeout=30) as client:
            streams = [await follow(live, job_id, client) for job_id in jobs]
            try:
                firsts = [await stream.next() for stream in streams]
                assert all(first is not None and first[1]["status"] == "accepted" for first in firsts)
                assert rig.events.followers == 50
                connections = rig.db.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE application_name = %s AND datname = current_database()",
                    (APPLICATION_NAME,),
                ).fetchone()
                assert connections == (1,)
                for run_id in run_ids:
                    set_state(rig.db, run_id, 25)
                seconds = [await stream.next() for stream in streams]
                assert all(second is not None and second[1]["progress"] == 25 for second in seconds)
            finally:
                for stream in streams:
                    await stream.close()
        await until(lambda: rig.events.followers == 0)

    async def test_after_the_connection_breaks_every_client_gets_the_state_of_its_row(
        self, rig: Rig, live: str
    ) -> None:
        jobs = [await placed(rig) for _ in range(3)]
        run_id = run_of(rig.db)
        async with httpx.AsyncClient(timeout=30) as client:
            streams = [await follow(live, job_id, client) for job_id in jobs]
            try:
                for stream in streams:
                    assert await stream.next() is not None
                (pid,) = [
                    row[0]
                    for row in rig.db.execute(
                        "SELECT pid FROM pg_stat_activity WHERE application_name = %s AND datname = current_database()",
                        (APPLICATION_NAME,),
                    ).fetchall()
                ]
                rig.db.execute("SELECT pg_terminate_backend(%s)", (pid,))
                await until(lambda: not rig.events.listening)
                rig.db.execute(
                    "UPDATE public.earthx_run SET progress = 66, status = 'running' WHERE run_id = %s", (run_id,)
                )
                assert await rig.events.wait_listening(20)
                for stream in streams:
                    event = await stream.next(15)
                    assert event is not None and event[1]["progress"] == 66
            finally:
                for stream in streams:
                    await stream.close()


class TestWhatTheStreamLeavesInTheLog:
    async def test_the_access_log_names_the_route_not_the_job(
        self, rig: Rig, live: str, access_log_lines: list[str]
    ) -> None:
        job_id = await placed(rig)
        stream = await follow(live, job_id)
        try:
            assert await stream.next() is not None
        finally:
            await stream.close()
        await until(lambda: rig.events.followers == 0)
        await until(lambda: any("/events" in line for line in access_log_lines))
        assert not [line for line in access_log_lines if job_id in line]
        assert any(json.loads(line)["path"] == "/processing/jobs/{jobID}/events" for line in access_log_lines)
