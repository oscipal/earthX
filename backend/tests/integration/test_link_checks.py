"""T-C: the results of the automatic link check and what they publish, hide and bring back (M5-67 plan §4a, §4c).

Built on the synthetic world of ``test_report``: finds written straight into ``earthx_record_state``, no catalogue
and no page is asked.
"""

# The fixtures of test_report are imported, so every test's parameter `world` shadows the import.
# ruff: noqa: F811

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from earthx.catalog.link_checks import LinkResult, apply_results, due_links, guard_results, record_results
from earthx.catalog.listing_store import withdraw
from tests.integration.test_report import World, _find, _regions, world  # noqa: F401  (fixtures)

NOW = datetime(2026, 11, 24, 12, tzinfo=UTC)


def _id(world: World, key: str) -> str:
    return f"{world.ckan.source_id}.{key}"


def _result(world: World, key: str, outcome: str = "passed", *, url: str | None = None, pattern: str = "p") -> LinkResult:
    return LinkResult(
        dataset_id=_id(world, key),
        url=url or f"https://amt.example.org/daten/{key}",
        host="amt.example.org",
        pattern=pattern,
        outcome=outcome,
        reason={"passed": "ok", "failed": "no_title", "unchecked": "robots"}[outcome],
        status=200 if outcome != "unchecked" else None,
        final_host="amt.example.org",
    )


def _published(world: World, *keys: str) -> None:
    world.put(world.ckan, *(_find(k) for k in keys))
    world.approve(world.report().files[0])
    world.publish()
    for key in keys:
        assert world.row(key)["state"] == "published"


def test_an_approved_entry_is_published_only_with_a_pass_of_its_own_current_link(world: World) -> None:
    world.put(world.ckan, _find("a"), _find("b"), _find("c"), _find("d"))
    approval = world.report().files[0]
    world.approve(approval)
    record_results(
        world.conn,
        [
            _result(world, "a"),
            _result(world, "b", "failed"),
            _result(world, "c", url="https://amt.example.org/daten/alt"),  # an older link of the entry
            _result(world, "d", "unchecked"),
        ],
        NOW,
    )
    assert world.publish(links_pass=False).published == {f"approvals/{approval.name}": 1}
    assert [world.row(k)["state"] for k in "abcd"] == ["published", "in_review", "in_review", "in_review"]


def test_a_guarded_pass_publishes_nothing(world: World) -> None:
    world.put(world.ckan, _find("a"))
    world.approve(world.report().files[0])
    record_results(world.conn, [_result(world, "a")], NOW)
    world.conn.execute("UPDATE public.earthx_link_check SET guarded = true WHERE dataset_id = %s", (_id(world, "a"),))
    world.publish(links_pass=False)
    assert world.row("a")["state"] == "in_review"


def test_a_failed_link_hides_a_published_entry_without_deleting_it_and_a_pass_brings_it_back(world: World) -> None:
    _published(world, "a", "b")
    record_results(world.conn, [_result(world, "a", "failed"), _result(world, "b", "unchecked")], NOW)
    # The trial run only counts.
    assert apply_results(world.conn, dry_run=True).hidden == 1
    assert world.row("a")["state"] == "published"
    assert apply_results(world.conn, dry_run=False).hidden == 1
    hidden = world.row("a")
    assert hidden["state"] == "link_failed" and hidden["content"]["title"] == "Bodenkarte a"
    # Unchecked hides nothing.
    assert world.row("b")["state"] == "published"
    record_results(world.conn, [_result(world, "a")], NOW + timedelta(days=1))
    applied = apply_results(world.conn, dry_run=False)
    assert (applied.hidden, applied.restored) == (0, 1)
    assert world.row("a")["state"] == "published"


def test_a_hidden_entry_keeps_its_state_on_a_describing_change_and_goes_into_review_on_a_deciding_one(
    world: World,
) -> None:
    _published(world, "a")
    record_results(world.conn, [_result(world, "a", "failed")], NOW)
    apply_results(world.conn, dry_run=False)
    world.put(world.ckan, _find("a", description="Neu beschrieben."))
    world.report()
    assert world.row("a")["state"] == "link_failed"
    world.put(world.ckan, _find("a", account="free_account"))
    world.report()
    assert world.row("a")["state"] == "in_review"


def test_a_hidden_entry_loses_its_grant_like_a_published_one(world: World) -> None:
    _published(world, "a")
    record_results(world.conn, [_result(world, "a", "failed")], NOW)
    apply_results(world.conn, dry_run=False)
    world.grant()
    assert withdraw(world.conn, world.licences.granted) == 1
    assert world.row("a")["state"] == "needs_rule"


def test_guard_per_host_and_pattern_at_its_edges(world: World) -> None:
    keys = [f"k{i:02d}" for i in range(40)]
    world.put(world.ckan, *(_find(k) for k in keys))
    world.report()
    since = NOW - timedelta(minutes=1)
    # Pattern "x": 20 checked, 5 failed (25 %): guarded. Pattern "y": 19 checked, 19 failed: too few to judge.
    # Both share the host, so the host (39 checked, 24 failed) is guarded too.
    results = [_result(world, k, "failed" if i < 5 else "passed", pattern="x") for i, k in enumerate(keys[:20])]
    results += [_result(world, k, "failed", pattern="y") for k in keys[20:39]]
    results.append(_result(world, keys[39], "unchecked", pattern="z"))
    record_results(world.conn, results, NOW)
    groups = {(g.kind, g.key): g for g in guard_results(world.conn, since, min_checked=20, failed_share=0.25)}
    assert groups[("pattern", "x")].guarded and not groups[("pattern", "y")].guarded
    assert groups[("host", "amt.example.org")].guarded
    assert groups[("pattern", "z")].unchecked == 1
    guarded = world.conn.execute(
        "SELECT count(*) FROM public.earthx_link_check WHERE guarded AND dataset_id LIKE %s",
        (f"{world.ckan.source_id}.%",),
    ).fetchone()
    assert guarded == (40,)


def test_a_share_just_below_the_threshold_guards_nothing(world: World) -> None:
    keys = [f"k{i:02d}" for i in range(20)]
    world.put(world.ckan, *(_find(k) for k in keys))
    world.report()
    record_results(world.conn, [_result(world, k, "failed" if i < 4 else "passed") for i, k in enumerate(keys)], NOW)
    groups = guard_results(world.conn, NOW - timedelta(minutes=1), min_checked=20, failed_share=0.25)
    assert not any(g.guarded for g in groups)


def test_due_links_come_most_urgent_first(world: World) -> None:
    _published(world, "fresh", "old", "never", "unchecked", "moved")
    world.put(world.ckan, _find("new"))
    world.report()
    record_results(world.conn, [_result(world, "fresh")], NOW - timedelta(days=2))
    record_results(world.conn, [_result(world, "old")], NOW - timedelta(days=40))
    record_results(world.conn, [_result(world, "unchecked", "unchecked")], NOW - timedelta(days=1))
    record_results(world.conn, [_result(world, "moved", url="https://amt.example.org/frueher")], NOW)
    world.conn.execute("DELETE FROM public.earthx_link_check WHERE dataset_id = %s", (_id(world, "never"),))
    due = [d for d in due_links(world.conn, recheck_days=30, now=NOW) if d.source_id == world.ckan.source_id]
    assert [(d.dataset_id.rsplit(".", 1)[1], d.priority) for d in due] == [
        ("new", 0),
        ("never", 1),
        ("moved", 1),
        ("unchecked", 2),
        ("old", 3),
    ]
    new = due[0]
    assert new.title == "Bodenkarte new" and "new" in new.identifiers and new.url.endswith("/daten/new")


def test_a_result_for_an_entry_that_is_gone_is_passed_over(world: World) -> None:
    assert record_results(world.conn, [_result(world, "nowhere")], NOW) == 1
    assert world.conn.execute(
        "SELECT count(*) FROM public.earthx_link_check WHERE dataset_id = %s", (_id(world, "nowhere"),)
    ).fetchone() == (0,)


def test_a_whole_run_checks_hides_and_the_trial_run_only_counts(world: World) -> None:
    import httpx

    from earthx.discovery.linkcheck import load_link_rules, run_linkcheck, summary_text
    from tests.earthx.discovery.test_linkcheck import opener, page, site

    _published(world, "gut", "tot")
    pages = {"amt.example.org/daten/gut": page("Bodenkarte gut"), "amt.example.org/daten/tot": httpx.Response(404)}
    rules = load_link_rules()
    for dry_run, state in ((True, "published"), (False, "link_failed")):
        # The published Bestand, never checked (the helper of test_report passed them).
        world.conn.execute("DELETE FROM public.earthx_link_check WHERE dataset_id LIKE %s", (f"{world.ckan.source_id}.%",))
        run = run_linkcheck(
            world.conn, rules=rules, hosts={}, dry_run=dry_run, open_gateway=opener(site(pages), []), minutes=5
        )
        ours = {r.dataset_id: r.outcome for r in run.results if r.dataset_id.startswith(world.ckan.source_id)}
        assert ours == {_id(world, "gut"): "passed", _id(world, "tot"): "failed"}
        assert (world.row("gut")["state"], world.row("tot")["state"]) == ("published", state)
        assert ("Probelauf" in summary_text(run, {})) is dry_run


def test_an_excluded_entry_stays_in_review(world: World) -> None:
    import yaml

    world.put(world.ckan, _find("a"), _find("b"))
    approval = world.report().files[0]
    world.approve(approval)
    document = yaml.safe_load(approval.read_text(encoding="utf-8"))
    document["excluded_entries"] = [_id(world, "b")]
    approval.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
    assert world.publish().published == {f"approvals/{approval.name}": 1}
    assert (world.row("a")["state"], world.row("b")["state"]) == ("published", "in_review")
