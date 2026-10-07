"""The hub behind the progress stream: one `LISTEN` connection, many clients (adr/0013 §5.4, F7; §8 points 6 and 12).

Against the real queue database. The messages are the ones the worker sends
(`earthx.jobs.queue.notify_progress`), sent from a second connection like the worker's.
"""

from __future__ import annotations

import asyncio
import logging
import time

import psycopg
import pytest

from earthx.api import job_events
from earthx.api.job_events import APPLICATION_NAME, JobEvents, TooManyFollowers, _run_of
from earthx.jobs import queue
from earthx.jobs.submit import dismiss, submit
from tests.earthx.api.conftest import Rig
from tests.earthx.jobs.support import add_run, make_recipe

pytestmark = pytest.mark.anyio


async def settle(sub: job_events.Subscription, timeout: float = 5.0):
    return await asyncio.wait_for(sub.next(), timeout)


async def nothing_comes(sub: job_events.Subscription, wait: float = 0.5) -> None:
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(sub.next(), wait)


def set_progress(db: psycopg.Connection, run_id: int, progress: int, status: str = "running", *, tell: bool = True):
    db.execute("UPDATE public.earthx_run SET progress = %s, status = %s WHERE run_id = %s", (progress, status, run_id))
    if tell:
        queue.notify_progress(db, run_id, progress, status)


def listen_connections(db: psycopg.Connection) -> list[int]:
    rows = db.execute(
        "SELECT pid FROM pg_stat_activity WHERE application_name = %s AND datname = current_database()",
        (APPLICATION_NAME,),
    ).fetchall()
    return [row[0] for row in rows]


async def until(condition, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("not true in time")


class TestFollowing:
    async def test_a_job_that_is_not_there_cannot_be_followed(self, rig: Rig) -> None:
        for job_id in ("A" * 22, "short", "", "../" * 8):
            with pytest.raises(LookupError):
                await rig.events.subscribe(job_id)
        assert rig.events.followers == 0

    async def test_what_a_client_gets_first_is_the_state_of_the_row(self, rig: Rig) -> None:
        run_id, (job_id,) = add_run(rig.db, status="running")
        set_progress(rig.db, run_id, 35, tell=False)
        sub = await rig.events.subscribe(job_id)
        state = await rig.events.current(sub)
        assert state is not None and (state.status, state.progress) == ("running", 35)

    async def test_a_message_brings_the_new_state(self, rig: Rig) -> None:
        run_id, (job_id,) = add_run(rig.db, status="running")
        sub = await rig.events.subscribe(job_id)
        set_progress(rig.db, run_id, 40)
        state = await settle(sub)
        assert state is not None and (state.status, state.progress) == ("running", 40)

    async def test_every_client_of_the_run_gets_it_and_a_client_of_another_run_does_not(self, rig: Rig) -> None:
        run_a, (first, second) = add_run(rig.db, status="running", jobs=2)
        _, (other,) = add_run(rig.db, status="running")
        subs = [await rig.events.subscribe(job_id) for job_id in (first, second, other)]
        set_progress(rig.db, run_a, 60)
        got = [await settle(sub) for sub in subs[:2]]
        assert [state.progress for state in got] == [60, 60] and {state.job_id for state in got} == {first, second}
        await nothing_comes(subs[2])

    async def test_one_read_serves_all_clients_of_a_run(self, rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
        run_id, jobs = add_run(rig.db, status="running", jobs=5)
        subs = [await rig.events.subscribe(job_id) for job_id in jobs]
        reads: list[tuple[int, list[str]]] = []
        original = rig.events._read

        def counting(run: int, ids: list[str]):
            reads.append((run, list(ids)))
            return original(run, ids)

        monkeypatch.setattr(rig.events, "_read", counting)
        set_progress(rig.db, run_id, 10)
        for sub in subs:
            await settle(sub)
        assert len(reads) == 1 and sorted(reads[0][1]) == sorted(jobs)

    async def test_a_run_nobody_follows_costs_no_read(self, rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
        run_id, _ = add_run(rig.db, status="running")
        _, (followed,) = add_run(rig.db, status="running")
        sub = await rig.events.subscribe(followed)
        reads: list[int] = []
        original = rig.events._read
        monkeypatch.setattr(rig.events, "_read", lambda run, ids: (reads.append(run), original(run, ids))[1])
        set_progress(rig.db, run_id, 10)
        await nothing_comes(sub)
        assert reads == []

    async def test_a_slot_holds_the_newest_state_only(self, rig: Rig) -> None:
        run_id, (job_id,) = add_run(rig.db, status="running")
        sub = await rig.events.subscribe(job_id)
        older = await rig.events.current(sub)
        set_progress(rig.db, run_id, 20, tell=False)
        newer = await rig.events.current(sub)
        assert older is not None and newer is not None
        sub.put(older)
        sub.put(newer)
        assert await settle(sub) == newer
        await nothing_comes(sub, 0.2)

    async def test_a_slow_client_delays_nobody(self, rig: Rig) -> None:
        run_id, (slow, fast) = add_run(rig.db, status="running", jobs=2)
        await rig.events.subscribe(slow)  # never reads
        sub = await rig.events.subscribe(fast)
        for progress in (10, 20, 30):
            set_progress(rig.db, run_id, progress)
            await settle(sub)
        assert rig.events.followers == 2

    async def test_a_rolled_back_message_is_never_sent(self, rig: Rig) -> None:
        run_id, (job_id,) = add_run(rig.db, status="running")
        sub = await rig.events.subscribe(job_id)
        with psycopg.connect(autocommit=False) as other:
            queue.notify_progress(other, run_id, 50, "running")
            other.rollback()
        await nothing_comes(sub)

    async def test_the_dismissal_of_a_followed_job_reaches_its_client_while_the_run_goes_on(self, rig: Rig) -> None:
        first = submit(rig.db, make_recipe())
        second = submit(rig.db, make_recipe())
        sub = await rig.events.subscribe(first)
        dismiss(rig.db, first)
        state = await settle(sub)
        assert state.status == "dismissed"
        assert rig.db.execute("SELECT status FROM public.earthx_run").fetchone() == ("accepted",)
        assert second


class TestRoom:
    async def test_the_process_serves_as_many_clients_as_it_will(self, rig: Rig) -> None:
        small = JobEvents(rig.pool, max_followers=2)
        _, jobs = add_run(rig.db, status="running", jobs=3)
        first = await small.subscribe(jobs[0])
        await small.subscribe(jobs[1])
        with pytest.raises(TooManyFollowers):
            await small.subscribe(jobs[2])
        small.unsubscribe(first)
        small.unsubscribe(first)  # a second time changes nothing
        assert small.followers == 1
        await small.subscribe(jobs[2])
        assert small.followers == 2

    async def test_stopping_ends_every_stream(self, rig: Rig) -> None:
        _, (job_id,) = add_run(rig.db, status="running")
        sub = await rig.events.subscribe(job_id)
        waiting = asyncio.create_task(sub.next())
        await asyncio.sleep(0.1)
        await rig.events.stop()
        assert await asyncio.wait_for(waiting, 2) is None


class TestOneConnection:
    """§8 point 12: however many clients follow, the database sees one connection of this process."""

    async def test_fifty_clients_are_one_connection(self, rig: Rig) -> None:
        runs = [add_run(rig.db, status="running", jobs=5) for _ in range(10)]
        subs = [await rig.events.subscribe(job_id) for _, jobs in runs for job_id in jobs]
        assert len(subs) == 50 and rig.events.followers == 50
        assert len(listen_connections(rig.db)) == 1

    async def test_it_connects_again_and_every_client_gets_the_state_of_its_row(
        self, rig: Rig, caplog: pytest.LogCaptureFixture
    ) -> None:
        run_a, jobs_a = add_run(rig.db, status="running", jobs=3)
        run_b, jobs_b = add_run(rig.db, status="running", jobs=2)
        subs = [await rig.events.subscribe(job_id) for job_id in (*jobs_a, *jobs_b)]
        (pid,) = listen_connections(rig.db)
        with caplog.at_level(logging.WARNING, logger="earthx.api.job_events"):
            rig.db.execute("SELECT pg_terminate_backend(%s)", (pid,))
            await until(lambda: not rig.events.listening)
            # What happens while it is down is not sent; the row has it all the same.
            set_progress(rig.db, run_a, 77, tell=False)
            set_progress(rig.db, run_b, 88, tell=False)
            assert await rig.events.wait_listening(20)
        got = [await settle(sub, 10) for sub in subs]
        assert sorted(state.progress for state in got) == [77, 77, 77, 88, 88]
        assert len(listen_connections(rig.db)) == 1 and listen_connections(rig.db) != [pid]
        # and what is sent afterwards arrives again
        set_progress(rig.db, run_a, 90)
        assert (await settle(subs[0])).progress == 90
        # The log names the class of the failure and nothing the driver wrote (host, user).
        down = [record.getMessage() for record in caplog.records if "is down" in record.getMessage()]
        assert down and all(message.split(": ", 1)[1].isidentifier() for message in down)

    async def test_noise_on_the_channel_is_ignored(self, rig: Rig) -> None:
        run_id, (job_id,) = add_run(rig.db, status="running")
        sub = await rig.events.subscribe(job_id)
        for junk in ("", "x", "[]", '{"run": "7"}', '{"run": true}', '{"run": null}', '{"p": 1}', "\u0000"[:0] + "{"):
            rig.db.execute("SELECT pg_notify(%s, %s)", (queue.PROGRESS_CHANNEL, junk))
        await nothing_comes(sub, 0.3)
        set_progress(rig.db, run_id, 5)
        assert (await settle(sub)).progress == 5


@pytest.mark.parametrize(
    ("payload", "expected"),
    [('{"run":7,"p":1,"s":"running"}', 7), ('{"run":0}', 0), ("", None), ("[1]", None), ('{"run":1.5}', None),
     ('{"run":"7"}', None), ('{"run":true}', None), ("nope", None)],
)  # fmt: skip
def test_the_run_a_message_names_is_read_strictly(payload: str, expected: int | None) -> None:
    assert _run_of(payload) == expected
