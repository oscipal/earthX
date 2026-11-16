"""T-C: the shared turn, places and breaker per host of M5-37 against a real Postgres (plan §3, §4, §9a).

What a mocked connection cannot show: that two connections really share one turn and one breaker, that a place past
its term is taken over and a heartbeat keeps it, that the numbered places never exceed the cap, and that the rows do
not wait for the commit of a run's transaction.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator

import psycopg
import pytest

from earthx.catalog import source_hosts
from earthx.catalog.source_hosts import MAX_PAUSE_S, PAUSE_S, PostgresHostCoordinator

pytestmark = pytest.mark.anyio


@pytest.fixture
def host() -> str:
    """A host of this test alone, so that the committed rows of one test never meet another's."""
    return f"h{uuid.uuid4().hex[:12]}.example.org"


async def _connect() -> psycopg.AsyncConnection:
    try:
        return await psycopg.AsyncConnection.connect(autocommit=True)
    except psycopg.OperationalError as error:
        pytest.fail(f"Postgres is configured but not reachable: {error}", pytrace=False)


@pytest.fixture
async def conns(require_postgres_env: None, host: str) -> AsyncIterator[list[psycopg.AsyncConnection]]:
    """Two connections in autocommit, as two instances would have; the host's rows are deleted afterwards."""
    opened = [await _connect(), await _connect()]
    try:
        yield opened
    finally:
        for conn in opened:
            if not conn.closed:
                await conn.close()
        async with await _connect() as conn:
            await conn.execute("DELETE FROM public.earthx_source_lease WHERE host = %s", (host,))
            await conn.execute("DELETE FROM public.earthx_source_host WHERE host = %s", (host,))


async def _row(conn: psycopg.AsyncConnection, host: str) -> tuple:
    cur = await conn.execute(
        "SELECT failures, pauses, extract(epoch FROM paused_until - clock_timestamp())::float8,"
        " extract(epoch FROM next_start - clock_timestamp())::float8 FROM public.earthx_source_host WHERE host = %s",
        (host,),
    )
    row = await cur.fetchone()
    assert row is not None
    return row


async def _end_pause(conn: psycopg.AsyncConnection, host: str) -> None:
    """Let the pause run out at once, as if its time had passed."""
    await conn.execute(
        "UPDATE public.earthx_source_host SET paused_until = clock_timestamp() - interval '1 second',"
        " next_start = clock_timestamp() WHERE host = %s",
        (host,),
    )


class TestTheSetUp:
    async def test_a_connection_inside_a_transaction_is_refused(self, require_postgres_env: None) -> None:
        conn = await psycopg.AsyncConnection.connect(autocommit=False)
        try:
            with pytest.raises(ValueError, match="autocommit"):
                PostgresHostCoordinator(conn)
        finally:
            await conn.close()

    @pytest.mark.parametrize(("term", "beat"), [(30.0, 30.0), (30.0, 0.0), (30.0, 45.0)])
    async def test_a_heartbeat_comes_more_often_than_a_place_runs_out(self, conns, term: float, beat: float) -> None:
        with pytest.raises(ValueError, match="heartbeat"):
            PostgresHostCoordinator(conns[0], lease_term_s=term, heartbeat_s=beat)

    @pytest.mark.parametrize("cap", [0, -1, True, 1.5])
    async def test_a_cap_below_one_or_not_whole_is_refused(self, conns, host: str, cap: object) -> None:
        with pytest.raises(ValueError, match="cap"):
            async with PostgresHostCoordinator(conns[0]).place(host, cap):  # type: ignore[arg-type]
                pass

    async def test_the_rows_name_a_host_and_nothing_else(self, conns) -> None:
        cur = await conns[0].execute(
            "SELECT table_name, column_name FROM information_schema.columns"
            " WHERE table_schema = 'public' AND table_name IN ('earthx_source_host', 'earthx_source_lease')"
        )
        columns = {column for _, column in await cur.fetchall()}
        assert not columns & {"dataset_id", "url", "address", "path", "aoi", "bbox"}


class TestTheSharedTurn:
    async def test_two_instances_take_turns_an_interval_apart(self, conns, host: str) -> None:
        first, second = (PostgresHostCoordinator(conn) for conn in conns)
        assert await first.reserve(host, 1.0) < 0.1
        assert 0.9 < await second.reserve(host, 1.0) <= 1.0
        assert 1.9 < await first.reserve(host, 1.0) <= 2.0

    async def test_turns_taken_at_once_from_two_connections_are_all_different(self, conns, host: str) -> None:
        first, second = (PostgresHostCoordinator(conn) for conn in conns)
        waits = await asyncio.gather(*(c.reserve(host, 0.5) for c in (first, second) * 5))
        ordered = sorted(waits)
        assert all(later - earlier > 0.45 for earlier, later in zip(ordered, ordered[1:], strict=False))

    async def test_a_caller_without_an_interval_waits_for_the_turn_but_does_not_move_it(self, conns, host: str) -> None:
        coordinator = PostgresHostCoordinator(conns[0])
        await coordinator.reserve(host, 2.0)
        assert 1.9 < await coordinator.reserve(host, 0.0) <= 2.0
        assert 1.9 < await coordinator.reserve(host, 0.0) <= 2.0

    async def test_a_turn_long_past_costs_no_wait(self, conns, host: str) -> None:
        coordinator = PostgresHostCoordinator(conns[0])
        await coordinator.reserve(host, 1.0)
        await conns[1].execute(
            "UPDATE public.earthx_source_host SET next_start = clock_timestamp() - interval '1 hour' WHERE host = %s",
            (host,),
        )
        assert await coordinator.reserve(host, 1.0) == 0.0


class TestTheBreaker:
    async def test_three_failures_in_a_row_pause_the_host_for_every_instance(
        self, conns, host: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        first, second = (PostgresHostCoordinator(conn) for conn in conns)
        await first.reserve(host, 0.0)
        caplog.set_level(logging.WARNING, logger="earthx.catalog")
        await first.report(host, failed=True)
        await second.report(host, failed=True)
        assert await second.reserve(host, 0.0) < 0.1
        await first.report(host, failed=True)
        assert PAUSE_S - 2 < await second.reserve(host, 0.0) <= PAUSE_S
        paused = [record for record in caplog.records if record.getMessage() == "source host paused"]
        assert len(paused) == 1
        assert paused[0].host == host

    async def test_a_success_resets_the_count(self, conns, host: str) -> None:
        coordinator = PostgresHostCoordinator(conns[0])
        for failed in (True, True, False, True, True):
            await coordinator.report(host, failed=failed)
        assert await coordinator.reserve(host, 0.0) < 0.1
        assert (await _row(conns[0], host))[:2] == (2, 0)

    async def test_attempts_that_fail_during_a_pause_do_not_lengthen_it(self, conns, host: str) -> None:
        coordinator = PostgresHostCoordinator(conns[0])
        for _ in range(3):
            await coordinator.report(host, failed=True)
        before = await _row(conns[0], host)
        for _ in range(3):
            await coordinator.report(host, failed=True)
        after = await _row(conns[0], host)
        assert after[1] == before[1] == 1
        assert abs(after[2] - before[2]) < 2

    async def test_a_failed_probe_after_the_pause_pauses_twice_as_long(self, conns, host: str) -> None:
        coordinator = PostgresHostCoordinator(conns[0])
        for _ in range(3):
            await coordinator.report(host, failed=True)
        await _end_pause(conns[1], host)
        assert await coordinator.reserve(host, 0.0) < 0.1
        await coordinator.report(host, failed=True)
        assert 2 * PAUSE_S - 2 < await coordinator.reserve(host, 0.0) <= 2 * PAUSE_S

    async def test_a_successful_probe_closes_the_breaker(self, conns, host: str) -> None:
        coordinator = PostgresHostCoordinator(conns[0])
        for _ in range(3):
            await coordinator.report(host, failed=True)
        await _end_pause(conns[1], host)
        await coordinator.report(host, failed=False)
        assert (await _row(conns[0], host))[:3] == (0, 0, None)
        for _ in range(3):
            await coordinator.report(host, failed=True)
        assert PAUSE_S - 2 < (await _row(conns[0], host))[2] <= PAUSE_S

    async def test_the_pause_doubles_at_most_to_an_hour(self, conns, host: str) -> None:
        coordinator = PostgresHostCoordinator(conns[0])
        await coordinator.report(host, failed=True)
        await conns[1].execute("UPDATE public.earthx_source_host SET failures = 2, pauses = 9 WHERE host = %s", (host,))
        await coordinator.report(host, failed=True)
        assert MAX_PAUSE_S - 2 < (await _row(conns[0], host))[2] <= MAX_PAUSE_S

    async def test_a_retry_after_moves_the_turn_without_waiting_for_the_threshold(self, conns, host: str) -> None:
        coordinator = PostgresHostCoordinator(conns[0])
        await coordinator.report(host, failed=True, retry_after_s=40)
        assert 38 < await coordinator.reserve(host, 0.0) <= 40
        assert (await _row(conns[0], host))[1] == 0

    @pytest.mark.parametrize(("asked", "moved"), [(10_000.0, source_hosts.MAX_RETRY_AFTER_S), (-5.0, 0.0), (None, 0.0)])
    async def test_a_retry_after_is_capped_and_never_negative(
        self, conns, host: str, asked: float | None, moved: float
    ) -> None:
        coordinator = PostgresHostCoordinator(conns[0])
        await coordinator.report(host, failed=True, retry_after_s=asked)
        assert moved - 2 <= await coordinator.reserve(host, 0.0) <= moved

    async def test_a_success_on_a_host_never_asked_writes_nothing(self, conns, host: str) -> None:
        await PostgresHostCoordinator(conns[0]).report(host, failed=False)
        cur = await conns[0].execute("SELECT count(*) FROM public.earthx_source_host WHERE host = %s", (host,))
        assert (await cur.fetchone())[0] == 0


class TestThePlaces:
    async def _live(self, conn: psycopg.AsyncConnection, host: str) -> list[int]:
        cur = await conn.execute(
            "SELECT slot FROM public.earthx_source_lease WHERE host = %s AND until > clock_timestamp() ORDER BY slot",
            (host,),
        )
        return [row[0] for row in await cur.fetchall()]

    async def test_never_more_places_than_the_cap_and_a_freed_one_goes_to_the_waiter(self, conns, host: str) -> None:
        first, second = (PostgresHostCoordinator(conn, draw=lambda a, b: 0.01) for conn in conns)
        entered = asyncio.Event()
        async with first.place(host, 2), second.place(host, 2):
            assert await self._live(conns[0], host) == [1, 2]

            async def third() -> None:
                async with first.place(host, 2):
                    entered.set()

            waiting = asyncio.create_task(third())
            await asyncio.sleep(0.2)
            assert not entered.is_set()
        await asyncio.wait_for(waiting, 5)
        assert entered.is_set()
        assert await self._live(conns[0], host) == []

    async def test_places_taken_at_once_never_exceed_the_cap(self, conns, host: str) -> None:
        coordinators = [PostgresHostCoordinator(conn, draw=lambda a, b: 0.01) for conn in conns]
        inside = 0
        most = 0

        async def hold(coordinator: PostgresHostCoordinator) -> None:
            nonlocal inside, most
            async with coordinator.place(host, 3):
                inside += 1
                most = max(most, inside)
                await asyncio.sleep(0.05)
                inside -= 1

        await asyncio.gather(*(hold(c) for c in coordinators * 6))
        assert most == 3

    async def test_a_place_of_an_instance_that_died_is_free_once_its_term_ran_out(self, conns, host: str) -> None:
        """Otto, 16.11.2026: a crashed instance must not hold a place for good. Its row stays; its term ends."""
        await conns[1].execute(
            "INSERT INTO public.earthx_source_lease (host, slot, holder, until)"
            " VALUES (%s, 1, gen_random_uuid(), clock_timestamp() + interval '0.5 second')",
            (host,),
        )
        coordinator = PostgresHostCoordinator(conns[0], draw=lambda a, b: 0.05)
        loop = asyncio.get_running_loop()
        started = loop.time()
        async with coordinator.place(host, 1) as slot:
            waited = loop.time() - started
        assert slot == 1
        assert 0.3 < waited < 3

    async def test_a_heartbeat_keeps_a_place_past_its_term(self, conns, host: str) -> None:
        holder = PostgresHostCoordinator(conns[0], lease_term_s=0.6, heartbeat_s=0.15)
        other = PostgresHostCoordinator(conns[1], lease_term_s=0.6, heartbeat_s=0.15, draw=lambda a, b: 0.05)
        async with holder.place(host, 1):
            await asyncio.sleep(1.5)
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.5):
                    async with other.place(host, 1):
                        pass
        async with asyncio.timeout(2):
            async with other.place(host, 1):
                pass

    async def test_a_place_taken_over_after_its_term_is_reported_lost(
        self, conns, host: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING, logger="earthx.catalog")
        holder = PostgresHostCoordinator(conns[0], lease_term_s=0.6, heartbeat_s=0.2)
        async with holder.place(host, 1):
            await conns[1].execute("DELETE FROM public.earthx_source_lease WHERE host = %s", (host,))
            await asyncio.sleep(0.5)
        assert any(record.getMessage() == "source place lost" for record in caplog.records)

    async def test_the_place_goes_back_after_an_error_in_the_block(self, conns, host: str) -> None:
        coordinator = PostgresHostCoordinator(conns[0])
        with pytest.raises(RuntimeError):
            async with coordinator.place(host, 1):
                raise RuntimeError("the request failed")
        assert await self._live(conns[1], host) == []

    async def test_a_place_that_cannot_be_given_back_does_not_hide_what_went_wrong(
        self, conns, host: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING, logger="earthx.catalog")
        coordinator = PostgresHostCoordinator(conns[0])
        with pytest.raises(RuntimeError, match="the request failed"):
            async with coordinator.place(host, 1):
                await conns[0].close()
                raise RuntimeError("the request failed")
        assert any(record.getMessage() == "source place not given back" for record in caplog.records)
