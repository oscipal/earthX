"""Placing, reading and dismissing jobs against a real Postgres (adr/0013 §5.1, §5.5; plan M4-08a §3.3).

The queue tables are real and committed, in a database of the session's own
(`conftest.py`); the several connections of the concurrency tests are real too.
"""

from __future__ import annotations

import dataclasses
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from earthx.jobs.submit import (
    MIN_RUNTIME_SECONDS,
    JobStatus,
    RecipeIdTaken,
    dismiss,
    job_recipe,
    job_run,
    job_status,
    run_jobs,
    submit,
)
from earthx.processing.recipe import cache_key, run_key
from tests.earthx.jobs.support import HOST, add_run, make_recipe, run_row, status_of

ID = re.compile(r"^[A-Za-z0-9_-]{22}$")


def _run_of(conn: psycopg.Connection) -> int:
    row = conn.execute("SELECT run_id FROM public.earthx_run").fetchone()
    assert row is not None
    return row[0]


def _count(conn: psycopg.Connection, table: str) -> int:
    row = conn.execute(f"SELECT count(*) FROM public.{table}").fetchone()
    assert row is not None
    return row[0]


class TestSubmit:
    def test_an_order_becomes_a_recipe_a_run_and_a_job(self, db: psycopg.Connection) -> None:
        recipe = make_recipe()
        job_id = submit(db, recipe)
        assert ID.match(job_id)
        assert (_count(db, "earthx_recipe"), _count(db, "earthx_run"), _count(db, "earthx_job")) == (1, 1, 1)
        row = db.execute(
            "SELECT status, hosts, cacheable, cache_key, max_seconds, attempt, expires_at > now() + interval '6 days' "
            "FROM public.earthx_run"
        ).fetchone()
        assert row is not None
        status, hosts, cacheable, key, max_seconds, attempt, expires = row
        assert (status, hosts, cacheable, attempt, expires) == ("accepted", [HOST], True, 0, True)
        assert key == cache_key(recipe) == run_key(recipe)
        assert max_seconds >= MIN_RUNTIME_SECONDS

    def test_every_order_gets_a_recipe_id_of_its_own(self, db: psycopg.Connection) -> None:
        first = submit(db, make_recipe())
        second = submit(db, make_recipe())
        ids = {job_status(db, job).recipe_id for job in (first, second)}  # type: ignore[union-attr]
        assert len(ids) == 2 and all(ID.match(recipe_id) for recipe_id in ids)

    def test_the_recipe_id_the_caller_gave_is_kept(self, db: psycopg.Connection) -> None:
        job_id = submit(db, make_recipe(recipe_id="A" * 22))
        status = job_status(db, job_id)
        assert status is not None and status.recipe_id == "A" * 22
        body = db.execute("SELECT body FROM public.earthx_recipe").fetchone()
        assert body is not None and body[0]["recipe_id"] == "A" * 22

    def test_the_stored_recipe_reads_back_as_the_recipe_that_was_given(self, db: psycopg.Connection) -> None:
        from earthx.processing.operators import REGISTRY
        from earthx.processing.recipe import recipe_from_data

        recipe = make_recipe()
        submit(db, recipe)
        body = db.execute("SELECT body FROM public.earthx_recipe").fetchone()
        assert body is not None
        again = recipe_from_data(body[0], REGISTRY)
        assert run_key(again) == run_key(recipe)

    def test_a_recipe_id_that_exists_is_refused_without_naming_it_and_leaves_nothing_behind(
        self, db: psycopg.Connection
    ) -> None:
        submit(db, make_recipe(recipe_id="B" * 22))
        with pytest.raises(RecipeIdTaken) as caught:
            submit(db, make_recipe("ITEM_OTHER", recipe_id="B" * 22))
        assert "B" * 22 not in str(caught.value) and caught.value.__cause__ is None
        assert (_count(db, "earthx_recipe"), _count(db, "earthx_run"), _count(db, "earthx_job")) == (1, 1, 1)

    def test_equal_orders_placed_one_after_the_other_share_the_active_run(self, db: psycopg.Connection) -> None:
        first, second = submit(db, make_recipe()), submit(db, make_recipe())
        assert first != second
        assert (_count(db, "earthx_recipe"), _count(db, "earthx_run"), _count(db, "earthx_job")) == (2, 1, 2)

    def test_different_orders_get_runs_of_their_own(self, db: psycopg.Connection) -> None:
        submit(db, make_recipe("ITEM_A"))
        submit(db, make_recipe("ITEM_B"))
        assert _count(db, "earthx_run") == 2

    def test_eight_orders_at_the_same_time_make_one_run(self, db: psycopg.Connection) -> None:
        barrier = threading.Barrier(8)

        def place(_: int) -> str:
            with psycopg.connect(autocommit=True) as conn:
                barrier.wait()
                return submit(conn, make_recipe())

        with ThreadPoolExecutor(8) as pool:
            jobs = list(pool.map(place, range(8)))
        assert len(set(jobs)) == 8
        assert (_count(db, "earthx_recipe"), _count(db, "earthx_run"), _count(db, "earthx_job")) == (8, 1, 8)

    def test_an_order_without_versions_attaches_to_the_active_run_but_is_not_cacheable(
        self, db: psycopg.Connection
    ) -> None:
        recipe = make_recipe(versioned=False)
        assert cache_key(recipe) is None
        submit(db, recipe)
        submit(db, recipe)
        row = db.execute("SELECT count(*), bool_or(cacheable) FROM public.earthx_run").fetchone()
        assert row == (1, False)

    def test_the_run_names_the_hosts_it_reads(self, db: psycopg.Connection) -> None:
        submit(db, make_recipe(host="data.example.invalid"))
        row = db.execute("SELECT hosts FROM public.earthx_run").fetchone()
        assert row == (["data.example.invalid"],)

    def test_an_order_is_announced_to_the_workers_only_when_it_made_a_run(self, db: psycopg.Connection) -> None:
        with psycopg.connect(autocommit=True) as listener:
            listener.execute("LISTEN earthx_jobs_wake")
            submit(db, make_recipe())
            first = list(listener.notifies(timeout=0.3, stop_after=1))
            submit(db, make_recipe())
            second = list(listener.notifies(timeout=0.3, stop_after=1))
        assert len(first) == 1 and second == []

    def test_a_failed_order_leaves_no_rows_behind(
        self, db: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("earthx.jobs.submit._run_for", lambda *args: (_ for _ in ()).throw(RuntimeError("x")))
        with pytest.raises(RuntimeError):
            submit(db, make_recipe())
        assert (_count(db, "earthx_recipe"), _count(db, "earthx_run"), _count(db, "earthx_job")) == (0, 0, 0)


class TestCacheHit:
    """A finished, cacheable run serves later equal orders with at least 24 hours of life left (Q11, F9)."""

    def _finished(self, db: psycopg.Connection, recipe, *, expires_in: str, status: str = "successful", cacheable=True):
        key = cache_key(recipe) or run_key(recipe)
        return add_run(db, status=status, key=key, cacheable=cacheable, expires_in=expires_in, result_id="R" * 22)[0]

    def test_a_hit_hangs_the_new_job_on_the_finished_run(self, db: psycopg.Connection) -> None:
        recipe = make_recipe()
        run_id = self._finished(db, recipe, expires_in="25 hours")
        job_id = submit(db, recipe)
        row = db.execute("SELECT run_id FROM public.earthx_job WHERE job_id = %s", (job_id,)).fetchone()
        assert row == (run_id,)
        assert _count(db, "earthx_run") == 1
        assert _count(db, "earthx_recipe") == 2  # the new order has a recipe of its own

    def test_with_less_than_24_hours_left_it_is_computed_again(self, db: psycopg.Connection) -> None:
        recipe = make_recipe()
        run_id = self._finished(db, recipe, expires_in="23 hours")
        job_id = submit(db, recipe)
        row = db.execute("SELECT run_id FROM public.earthx_job WHERE job_id = %s", (job_id,)).fetchone()
        assert row is not None and row[0] != run_id
        assert _count(db, "earthx_run") == 2

    @pytest.mark.parametrize("status", ["failed", "dismissed"])
    def test_a_run_that_did_not_succeed_is_no_hit(self, db: psycopg.Connection, status: str) -> None:
        recipe = make_recipe()
        self._finished(db, recipe, expires_in="6 days", status=status)
        submit(db, recipe)
        assert _count(db, "earthx_run") == 2

    def test_a_result_without_versions_is_no_hit(self, db: psycopg.Connection) -> None:
        recipe = make_recipe(versioned=False)
        self._finished(db, recipe, expires_in="6 days", cacheable=False)
        submit(db, recipe)
        assert _count(db, "earthx_run") == 2

    def test_a_changed_input_version_is_no_hit(self, db: psycopg.Connection) -> None:
        old = make_recipe()
        self._finished(db, old, expires_in="6 days")
        data = old.model_dump(mode="json")
        data["inputs"][0]["resolved"][0]["version"] = {"kind": "etag", "value": "newer"}
        from earthx.processing.operators import REGISTRY
        from earthx.processing.recipe import recipe_from_data

        submit(db, recipe_from_data(data, REGISTRY))
        assert _count(db, "earthx_run") == 2


class TestStatus:
    def test_a_waiting_job_is_accepted_with_no_progress(self, db: psycopg.Connection) -> None:
        status = job_status(db, submit(db, make_recipe()))
        assert status is not None
        assert (status.status, status.progress, status.started_at, status.finished_at) == ("accepted", 0, None, None)
        assert status.error_kind is None and status.result_id is None and status.result is None

    def test_a_running_job_shows_its_progress(self, db: psycopg.Connection) -> None:
        run_id, (job_id,) = add_run(db, status="running")
        db.execute("UPDATE public.earthx_run SET progress = 42 WHERE run_id = %s", (run_id,))
        status = job_status(db, job_id)
        assert status is not None and (status.status, status.progress) == ("running", 42)

    def test_a_successful_job_carries_where_its_result_lies(self, db: psycopg.Connection) -> None:
        run_id, (job_id,) = add_run(db, status="successful", result_id="R" * 22)
        db.execute(
            "UPDATE public.earthx_run SET result = '{\"blocks\": 3}', progress = 100 WHERE run_id = %s", (run_id,)
        )
        status = job_status(db, job_id)
        assert status is not None
        assert (status.status, status.progress, status.result_id, status.result) == (
            "successful",
            100,
            "R" * 22,
            {"blocks": 3},
        )

    def test_a_successful_job_shows_a_result_that_names_no_address_and_no_run(self, db: psycopg.Connection) -> None:
        job_id = submit(db, make_recipe())
        db.execute(
            "UPDATE public.earthx_run SET status = 'successful', result_id = %s, progress = 100, result = %s",
            ("R" * 22, json.dumps({"blocks": 3, "width": 4, "properties": {"gsd": 10.0}})),
        )
        status = job_status(db, job_id)
        assert status is not None
        assert status.result == {"blocks": 3, "width": 4, "properties": {"gsd": 10.0}}
        text = repr(status)
        assert "c1:" not in text and HOST not in text and "run_id" not in text

    def test_a_failed_job_names_its_error_kind_and_nothing_else(self, db: psycopg.Connection) -> None:
        run_id, (job_id,) = add_run(db, status="failed")
        db.execute("UPDATE public.earthx_run SET error_kind = 'source_4xx' WHERE run_id = %s", (run_id,))
        status = job_status(db, job_id)
        assert status is not None and (status.status, status.error_kind) == ("failed", "source_4xx")

    def test_the_error_of_a_run_that_will_be_tried_again_is_not_shown(self, db: psycopg.Connection) -> None:
        run_id, (job_id,) = add_run(db, status="accepted")
        db.execute("UPDATE public.earthx_run SET error_kind = 'source_5xx' WHERE run_id = %s", (run_id,))
        status = job_status(db, job_id)
        assert status is not None and status.error_kind is None

    def test_a_dismissed_job_hides_a_result_that_is_there(self, db: psycopg.Connection) -> None:
        _, (job_id,) = add_run(db, status="successful", result_id="R" * 22)
        db.execute("UPDATE public.earthx_job SET dismissed = true")
        status = job_status(db, job_id)
        assert status is not None
        assert (status.status, status.result_id, status.result) == ("dismissed", None, None)

    @pytest.mark.parametrize(
        "job_id",
        ["", "x", "A" * 21, "A" * 23, "A" * 22, "../" + "A" * 19, "A" * 21 + " ", "A" * 21 + "\n", "ä" * 22, None, 5],
    )
    def test_an_identifier_that_is_foreign_or_malformed_is_unknown(self, db: psycopg.Connection, job_id) -> None:
        add_run(db)
        assert job_status(db, job_id) is None
        assert dismiss(db, job_id) is None

    def test_a_malformed_identifier_never_reaches_the_database(self) -> None:
        class Refuses:
            def execute(self, *args: object, **kwargs: object) -> None:
                raise AssertionError("the database was asked")

            transaction = execute

        assert job_status(Refuses(), "not-an-id") is None  # type: ignore[arg-type]
        assert dismiss(Refuses(), "not-an-id") is None  # type: ignore[arg-type]

    def test_what_is_returned_names_no_run_hash_or_address(self, db: psycopg.Connection) -> None:
        recipe = make_recipe()
        status = job_status(db, submit(db, recipe))
        assert status is not None
        assert {field.name for field in dataclasses.fields(JobStatus)} == {
            "job_id",
            "recipe_id",
            "status",
            "progress",
            "created_at",
            "started_at",
            "finished_at",
            "expires_at",
            "error_kind",
            "result_id",
            "result",
        }
        text = repr(status)
        assert "c1:" not in text and HOST not in text and "run_id" not in text

    def test_looking_at_a_job_writes_nothing(self, db: psycopg.Connection) -> None:
        """Adr/0015 F13: only a run or a hit lengthens a recipe's life, looking never does."""
        job_id = submit(db, make_recipe())
        add_run(db, status="successful", result_id="R" * 22)

        def snapshot() -> list[tuple]:
            return db.execute(
                """
                SELECT 'recipe', xmin::text, recipe_id FROM public.earthx_recipe
                UNION ALL SELECT 'run', xmin::text, run_id::text FROM public.earthx_run
                UNION ALL SELECT 'job', xmin::text, job_id FROM public.earthx_job
                ORDER BY 1, 3
                """
            ).fetchall()

        before = snapshot()
        for _ in range(3):
            assert job_status(db, job_id) is not None
        assert job_status(db, "A" * 22) is None
        assert snapshot() == before


class TestReadingForTheJobApi:
    """What M4-08b reads besides the status: the job's own recipe, its run, the jobs of one run."""

    def test_two_equal_orders_share_a_run_but_each_job_reads_its_own_recipe(self, db: psycopg.Connection) -> None:
        first = submit(db, make_recipe())
        second = submit(db, make_recipe())
        assert _count(db, "earthx_run") == 1
        bodies = [job_recipe(db, job) for job in (first, second)]
        assert all(body is not None for body in bodies)
        ids = {body["recipe_id"] for body in bodies if body is not None}
        assert ids == {job_status(db, first).recipe_id, job_status(db, second).recipe_id}  # type: ignore[union-attr]
        assert len(ids) == 2

    def test_the_run_of_a_job_is_the_run_the_progress_messages_name(self, db: psycopg.Connection) -> None:
        first = submit(db, make_recipe())
        second = submit(db, make_recipe())
        assert job_run(db, first) == job_run(db, second) == _run_of(db)

    def test_run_jobs_gives_the_state_of_the_named_jobs_of_that_run_only(self, db: psycopg.Connection) -> None:
        first = submit(db, make_recipe())
        second = submit(db, make_recipe())
        other = submit(db, make_recipe("ITEM_B"))
        run = job_run(db, first)
        assert run is not None
        states = run_jobs(db, run, [first, second, other])
        assert sorted(state.job_id for state in states) == sorted([first, second])
        assert run_jobs(db, run, [second])[0].job_id == second

    @pytest.mark.parametrize("bad", ["", "short", "A" * 21, "A" * 23, "A" * 21 + "/", "../" * 8])
    def test_a_malformed_identifier_finds_nothing(self, db: psycopg.Connection, bad: str) -> None:
        submit(db, make_recipe())
        assert job_recipe(db, bad) is None
        assert job_run(db, bad) is None
        assert run_jobs(db, 1, [bad]) == []

    def test_an_unknown_identifier_finds_nothing(self, db: psycopg.Connection) -> None:
        assert job_recipe(db, "A" * 22) is None
        assert job_run(db, "A" * 22) is None
        assert run_jobs(db, 1, ["A" * 22]) == []

    def test_none_of_them_writes(self, db: psycopg.Connection) -> None:
        job_id = submit(db, make_recipe())
        before = db.execute("SELECT xmin::text, job_id FROM public.earthx_job").fetchall()
        before_run = db.execute("SELECT xmin::text FROM public.earthx_run").fetchall()
        run = job_run(db, job_id)
        assert run is not None
        job_recipe(db, job_id)
        run_jobs(db, run, [job_id])
        assert db.execute("SELECT xmin::text, job_id FROM public.earthx_job").fetchall() == before
        assert db.execute("SELECT xmin::text FROM public.earthx_run").fetchall() == before_run


class TestDismiss:
    def test_a_waiting_run_is_dismissed_at_once_and_frees_its_key(self, db: psycopg.Connection) -> None:
        recipe = make_recipe()
        job_id = submit(db, recipe)
        status = dismiss(db, job_id)
        assert status is not None and status.status == "dismissed"
        assert db.execute("SELECT status FROM public.earthx_run").fetchone() == ("dismissed",)
        submit(db, recipe)  # the same order again starts a new run
        assert _count(db, "earthx_run") == 2

    def test_dismissing_a_waiting_run_tells_those_who_listen_to_its_progress(self, db: psycopg.Connection) -> None:
        job_id = submit(db, make_recipe())
        with psycopg.connect(autocommit=True) as listener:
            listener.execute("LISTEN earthx_job_progress")
            dismiss(db, job_id)
            messages = [json.loads(n.payload) for n in listener.notifies(timeout=0.3)]
        assert messages == [{"run": _run_of(db), "p": 0, "s": "dismissed"}]

    def test_a_running_run_is_asked_to_cancel_and_the_workers_are_woken(self, db: psycopg.Connection) -> None:
        run_id, (job_id,) = add_run(db, status="running")
        with psycopg.connect(autocommit=True) as listener:
            listener.execute("LISTEN earthx_jobs_wake")
            dismiss(db, job_id)
            woken = list(listener.notifies(timeout=0.3, stop_after=1))
        assert run_row(db, run_id, "status", "cancel_requested") == ("running", True)
        assert len(woken) == 1

    def test_another_live_job_keeps_the_run_going(self, db: psycopg.Connection) -> None:
        run_id, (first, second) = add_run(db, status="running", jobs=2)
        status = dismiss(db, first)
        assert status is not None and status.status == "dismissed"
        assert run_row(db, run_id, "cancel_requested") == (False,)
        other = job_status(db, second)
        assert other is not None and other.status == "running"

    def test_a_dismissal_that_leaves_the_run_going_still_tells_those_who_follow_the_job(
        self, db: psycopg.Connection
    ) -> None:
        run_id, (first, _second) = add_run(db, status="running", jobs=2)
        with psycopg.connect(autocommit=True) as listener:
            listener.execute("LISTEN earthx_job_progress")
            dismiss(db, first)
            messages = [json.loads(n.payload) for n in listener.notifies(timeout=0.3)]
        assert messages == [{"run": run_id, "p": 0, "s": "running"}]

    def test_the_last_dismissal_cancels_the_run(self, db: psycopg.Connection) -> None:
        run_id, (first, second) = add_run(db, status="running", jobs=2)
        dismiss(db, first)
        dismiss(db, second)
        assert run_row(db, run_id, "cancel_requested") == (True,)

    def test_two_jobs_dismissed_at_the_same_time_still_cancel_the_run_once(self, db: psycopg.Connection) -> None:
        run_id, jobs = add_run(db, status="running", jobs=2)
        barrier = threading.Barrier(2)

        def work(job_id: str) -> None:
            with psycopg.connect(autocommit=True) as conn:
                barrier.wait()
                dismiss(conn, job_id)

        with ThreadPoolExecutor(2) as pool:
            list(pool.map(work, jobs))
        assert run_row(db, run_id, "cancel_requested") == (True,)

    def test_a_job_dismissed_twice_stays_dismissed(self, db: psycopg.Connection) -> None:
        _, (job_id,) = add_run(db, status="running")
        assert dismiss(db, job_id) is not None
        again = dismiss(db, job_id)
        assert again is not None and again.status == "dismissed"

    def test_a_finished_job_counts_as_dismissed_and_its_result_stays(self, db: psycopg.Connection) -> None:
        run_id, (job_id,) = add_run(db, status="successful", result_id="R" * 22)
        status = dismiss(db, job_id)
        assert status is not None and status.status == "dismissed" and status.result_id is None
        assert run_row(db, run_id, "status", "result_id", "cancel_requested") == ("successful", "R" * 22, False)

    def test_a_finished_run_serves_a_later_order_although_one_job_was_dismissed(self, db: psycopg.Connection) -> None:
        recipe = make_recipe()
        key = cache_key(recipe)
        run_id, (job_id,) = add_run(db, status="successful", key=key, result_id="R" * 22, expires_in="6 days")
        dismiss(db, job_id)
        new = submit(db, recipe)
        status = job_status(db, new)
        assert status is not None and status.status == "successful" and status.result_id == "R" * 22
        assert _count(db, "earthx_run") == 1
        assert run_id

    def test_someone_who_knows_the_recipe_cannot_cancel_anothers_job(self, db: psycopg.Connection) -> None:
        recipe = make_recipe()
        mine, theirs = submit(db, recipe), submit(db, recipe)
        dismiss(db, mine)
        assert status_of(db, run_row(db, 1, "run_id")[0]) == "accepted"
        other = job_status(db, theirs)
        assert other is not None and other.status == "accepted"

    def test_a_new_equal_order_revives_a_run_that_was_being_cancelled(self, db: psycopg.Connection) -> None:
        recipe = make_recipe()
        run_id, (job_id,) = add_run(db, status="running", key=cache_key(recipe))
        dismiss(db, job_id)
        assert run_row(db, run_id, "cancel_requested") == (True,)
        submit(db, recipe)
        assert run_row(db, run_id, "cancel_requested") == (False,)
