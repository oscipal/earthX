"""The turns per host of a pyramid build, kept by its supervisor in Postgres (M5-37 PR 2, plan §5.4).

Two layers here: :class:`TurnKeeper` against a recording stand-in and a clock of its own; :class:`SourceHosts` against
the functions of migrations 022 and 023 in a real Postgres, next to its twin in `catalog`. The supervisor with spawned
children that ask for turns as the real child does is in `test_overview_builder.py`.
"""

from __future__ import annotations

import logging
import uuid

import psycopg
import pytest

from earthx.catalog import source_hosts as catalog_hosts
from earthx.jobs import source_hosts as jobs_hosts
from earthx.jobs.source_hosts import HEARTBEAT_S, HostTurns, SourceHosts, TurnKeeper

HOST = "bucket.example.org"


class FakeHosts:
    """Answers like the database, from what the test sets; records every call."""

    def __init__(self) -> None:
        self.wait = 0.0
        self.paused = 0.0
        self.free = True
        self.renewed = True
        self.reported: tuple[bool, bool, float] = (False, False, 0.0)
        self.calls: list[tuple] = []

    def reserve(self, host: str, interval_s: float, max_wait_s: float) -> float:
        self.calls.append(("reserve", host, interval_s, max_wait_s))
        return self.wait

    def pause_left(self, host: str) -> float:
        self.calls.append(("pause_left", host))
        return self.paused

    def acquire(self, host: str, cap: int, holder: uuid.UUID) -> int | None:
        self.calls.append(("acquire", host, cap))
        return 1 if self.free else None

    def renew(self, host: str, slot: int, holder: uuid.UUID) -> bool:
        self.calls.append(("renew", host, slot))
        return self.renewed

    def release(self, host: str, slot: int, holder: uuid.UUID) -> None:
        self.calls.append(("release", host, slot))

    def account(self, host: str, interval_s: float, requests: int) -> None:
        self.calls.append(("account", host, interval_s, requests))

    def report(self, host: str, *, failed: bool, retry_after_s: float | None = None) -> tuple[bool, bool, float]:
        self.calls.append(("report", host, failed, retry_after_s))
        return self.reported

    def names(self) -> list[str]:
        return [call[0] for call in self.calls]


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def keeper(hosts: FakeHosts, clock: Clock) -> TurnKeeper:
    return TurnKeeper(hosts, {HOST: HostTurns(4, 0.25)}, clock=clock, draw=lambda low, high: 0.5)  # type: ignore[arg-type]


class TestTheKeeper:
    def test_a_turn_is_taken_with_the_hosts_spacing_and_a_build_waits_out_any_pause(self) -> None:
        hosts = FakeHosts()
        keeper(hosts, Clock()).ask(HOST)
        assert hosts.calls == [("reserve", HOST, 0.25, jobs_hosts.BUILD_MAX_WAIT_S)]
        assert jobs_hosts.BUILD_MAX_WAIT_S >= jobs_hosts.MAX_PAUSE_S

    def test_a_host_the_build_does_not_read_is_refused_without_a_turn(self) -> None:
        hosts = FakeHosts()
        with pytest.raises(ValueError):
            keeper(hosts, Clock()).ask("elsewhere.example.org")
        assert hosts.calls == []

    def test_the_child_goes_once_the_turn_is_due_and_a_place_is_held(self) -> None:
        hosts, clock = FakeHosts(), Clock()
        hosts.wait = 2.0
        turns = keeper(hosts, clock)
        turns.ask(HOST)
        assert turns.due_in() == 2.0
        assert turns.step() is False
        clock.now += 2.0
        assert turns.step() is True
        assert hosts.names() == ["reserve", "pause_left", "acquire"]
        assert turns.busy

    def test_a_pause_found_when_the_turn_is_due_is_waited_out_first(self) -> None:
        hosts, clock = FakeHosts(), Clock()
        hosts.paused = 30.0
        turns = keeper(hosts, clock)
        turns.ask(HOST)
        assert turns.step() is False
        assert turns.due_in() == 30.0
        assert "acquire" not in hosts.names()
        hosts.paused = 0.0
        clock.now += 30.0
        assert turns.step() is True

    def test_while_every_place_is_held_it_asks_again_after_a_while(self) -> None:
        hosts, clock = FakeHosts(), Clock()
        hosts.free = False
        turns = keeper(hosts, clock)
        turns.ask(HOST)
        assert turns.step() is False
        assert turns.due_in() == 0.5
        hosts.free = True
        clock.now += 0.5
        assert turns.step() is True

    def test_a_held_place_is_renewed_and_a_lost_one_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        hosts, clock = FakeHosts(), Clock()
        turns = keeper(hosts, clock)
        turns.ask(HOST)
        turns.step()
        assert turns.due_in() == HEARTBEAT_S
        clock.now += HEARTBEAT_S
        hosts.renewed = False
        caplog.set_level(logging.WARNING, logger="earthx.jobs")
        assert turns.step() is False
        assert hosts.names()[-1] == "renew"
        assert [record.getMessage() for record in caplog.records] == ["source place lost"]

    def test_an_account_charges_the_requests_reports_and_gives_the_place_back(self) -> None:
        hosts, clock = FakeHosts(), Clock()
        turns = keeper(hosts, clock)
        turns.ask(HOST)
        turns.step()
        turns.account(HOST, 5, True, 7.0)
        assert hosts.calls[-3:] == [("account", HOST, 0.25, 5), ("report", HOST, True, 7.0), ("release", HOST, 1)]
        assert not turns.busy
        assert turns.due_in() is None

    @pytest.mark.parametrize("held", [False, True])
    def test_an_account_for_a_turn_not_given_is_refused(self, held: bool) -> None:
        hosts = FakeHosts()
        turns = keeper(hosts, Clock())
        if held:
            turns.ask(HOST)
            turns.step()
            with pytest.raises(ValueError):
                turns.account("elsewhere.example.org", 1, False, None)
        else:
            with pytest.raises(ValueError):
                turns.account(HOST, 1, False, None)

    def test_a_pause_it_opened_and_a_host_that_answers_again_are_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO, logger="earthx.jobs")
        hosts = FakeHosts()
        turns = keeper(hosts, Clock())
        for reported in ((True, False, 300.0), (False, True, 0.0)):
            hosts.reported = reported
            turns.ask(HOST)
            turns.step()
            turns.account(HOST, 1, reported[0], None)
        assert [record.getMessage() for record in caplog.records] == ["source host paused", "source host answers again"]

    def test_close_gives_back_a_held_place_and_nothing_else(self) -> None:
        hosts = FakeHosts()
        turns = keeper(hosts, Clock())
        turns.close()
        turns.ask(HOST)
        turns.close()
        assert "release" not in hosts.names()
        turns.ask(HOST)
        turns.step()
        turns.close()
        assert hosts.names()[-1] == "release"

    @pytest.mark.parametrize(
        ("connections", "interval"), [(0, 0.25), (True, 0.25), (4, -1.0), (4, float("nan")), (4, 301.0)]
    )
    def test_wrong_limits_are_refused(self, connections: int, interval: float) -> None:
        with pytest.raises(ValueError):
            HostTurns(connections, interval)


class TestTheDatabaseCalls:
    def test_the_supervisor_calls_the_same_functions_with_the_same_numbers_as_catalog(self) -> None:
        """One set of rules for `materialize` and the pyramid build; `jobs` may not import `catalog`."""
        for name in ("BREAKER_THRESHOLD", "PAUSE_S", "MAX_PAUSE_S", "MAX_RETRY_AFTER_S", "LEASE_TERM_S", "HEARTBEAT_S"):
            assert getattr(jobs_hosts, name) == getattr(catalog_hosts, name), name
        for name in ("_RESERVE", "_PAUSE_LEFT", "_REPORT", "_ACQUIRE", "_RENEW", "_RELEASE"):
            assert getattr(jobs_hosts, name) == getattr(catalog_hosts, name), name

    def test_a_connection_inside_a_transaction_is_refused(self, db: psycopg.Connection) -> None:
        with psycopg.connect(autocommit=False) as conn, pytest.raises(ValueError, match="autocommit"):
            SourceHosts(conn)

    @pytest.mark.parametrize(("requests", "moved"), [(0, 0.0), (1, 0.0), (3, 1.0)])
    def test_the_requests_of_a_file_move_the_turn_on_but_none_gives_nothing_back(
        self, db: psycopg.Connection, requests: int, moved: float
    ) -> None:
        hosts = SourceHosts(db)
        hosts.reserve(HOST, 0.5, 60.0)
        before = self._next(db)
        hosts.account(HOST, 0.5, requests)
        assert abs(self._next(db) - before - moved) < 0.01

    def test_turns_breaker_and_places_round_trip(self, db: psycopg.Connection) -> None:
        hosts = SourceHosts(db)
        assert hosts.reserve(HOST, 1.0, 60.0) < 0.1
        assert 0.9 < hosts.reserve(HOST, 1.0, 60.0) <= 1.0
        assert [hosts.report(HOST, failed=True)[0] for _ in range(3)] == [False, False, True]
        assert 299 < hosts.pause_left(HOST) <= 300
        assert hosts.report(HOST, failed=False) == (False, True, 0.0)
        holder = uuid.uuid4()
        slot = hosts.acquire(HOST, 1, holder)
        assert slot == 1 and hosts.acquire(HOST, 1, uuid.uuid4()) is None
        assert hosts.renew(HOST, 1, holder) and not hosts.renew(HOST, 1, uuid.uuid4())
        hosts.release(HOST, 1, holder)
        assert hosts.acquire(HOST, 1, uuid.uuid4()) == 1

    @staticmethod
    def _next(db: psycopg.Connection) -> float:
        row = db.execute(
            "SELECT extract(epoch FROM next_start)::float8 FROM public.earthx_source_host WHERE host = %s", (HOST,)
        ).fetchone()
        assert row is not None
        return row[0]
