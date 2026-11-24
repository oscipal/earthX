"""The check of a listed entry's link (M5-67 plan §4): what passes, what fails, what cannot be checked, and how the run
goes through the gateway. No network: a transport stands in for every host."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from earthx.catalog.entry_files import EntryFileError
from earthx.catalog.hosts import HostLimit
from earthx.catalog.link_checks import DueLink
from earthx.discovery import linkcheck
from earthx.discovery.linkcheck import (
    LINKCHECK_FILE,
    check_links,
    judge_page,
    link_pattern,
    link_policy,
    load_link_rules,
    read_link_rules,
)
from earthx.gateway import Gateway, Policy

RULES = load_link_rules()
LINK = "https://amt.example.org/daten/bodenkarte"
TITLE = "Bodenkarte des Kantons Zug"
HTML = "text/html; charset=utf-8"


def judge(body: str, *, link: str = LINK, final: str = LINK, status: int = 200, kind: str = HTML,
          title: str = TITLE, identifiers: tuple[str, ...] = ()) -> tuple[str, str]:
    return judge_page(link, final, status, kind, body.encode("utf-8"), title=title, identifiers=identifiers, rules=RULES)


# --- One page ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        f"<html><body><h1>{TITLE}</h1></body></html>",
        f"<html><head><title>{TITLE} | Amt</title></head><body><div id=app></div></body></html>",
        f'<html><head><meta property="og:title" content="{TITLE}"></head><body></body></html>',
        '<html><head><script type="application/ld+json">{"@type": "Dataset", "name": "'
        + TITLE
        + '"}</script></head><body></body></html>',
        # Accents and punctuation as the search compares them.
        "<html><body><p>BODENKARTE – des Kantons Zug!</p></body></html>",
        # A long title: 80 % of its words of four letters or more.
        "<html><body>Bodenkarte Kanton Zug Messung Grundwasser Nitrat Stand</body></html>",
    ],
)
def test_the_title_counts_in_the_text_and_wherever_a_portal_names_itself(body: str) -> None:
    title = "Bodenkarte Kanton Zug: Messung Grundwasser Nitrat 2020" if "Nitrat" in body else TITLE
    assert judge(body, title=title) == ("passed", "ok")


def test_an_identifier_counts_and_a_short_one_does_not() -> None:
    page = '<html><head><link rel="canonical" href="https://portal.example.org/dataset/ch.bafu.boden"></head></html>'
    assert judge(page, title="Anders", identifiers=("ch.bafu.boden",)) == ("passed", "ok")
    assert judge("<html><body>Seite xy12</body></html>", title="Anders", identifiers=("xy12",)) == ("failed", "no_title")


def test_script_text_is_no_text() -> None:
    page = f"<html><body><script>var t = '{TITLE}';</script><div id=app></div></body></html>"
    assert judge(page) == ("failed", "no_title")


def test_a_page_landing_on_the_start_page_fails_even_if_it_names_the_dataset() -> None:
    # GENESIS: "Tabelle zu groß für nicht registrierte Nutzer" and back to the start page (Otto, 24.11.2026).
    body = f"<html><body>Tabelle zu groß für nicht registrierte Nutzer. {TITLE}</body></html>"
    assert judge(body, final="https://amt.example.org/de/") == ("failed", "start_page")


def test_error_and_login_pages_fail() -> None:
    error = f"<html><head><title>404 – Seite nicht gefunden</title></head><body>{TITLE}</body></html>"
    assert judge(error) == ("failed", "error_page")
    assert judge(f"<html><body>{TITLE}</body></html>", final="https://amt.example.org/login?next=/daten") == (
        "failed",
        "login_page",
    )
    form = "<html><head><title>Anmelden</title></head><body><input type=password name=pw></body></html>"
    assert judge(form) == ("failed", "login_page")


def test_a_dataset_named_like_an_error_word_still_passes() -> None:
    title = "Fehler der Höhenmessung"
    assert judge(f"<html><head><title>{title}</title></head><body></body></html>", title=title) == ("passed", "ok")


def test_a_page_for_an_order_or_an_account_passes_when_it_names_the_dataset() -> None:
    # Ordering, an account, a fee and "on request" stay listed (Otto, 14.11.2026).
    body = f"<html><body><h1>{TITLE}</h1><a href=/login>Anmelden</a> <button>Bestellen</button></body></html>"
    assert judge(body) == ("passed", "ok")


@pytest.mark.parametrize(
    ("status", "kind", "body", "expected"),
    [
        (204, HTML, "", ("failed", "http_204")),
        (200, "application/pdf", "%PDF-1.7", ("failed", "not_a_page")),
        (200, "application/json", '{"title": "' + TITLE + '"}', ("passed", "ok")),
        (200, HTML, "<html><body>...</body></html>", ("failed", "no_title")),
    ],
)
def test_status_and_kind(status: int, kind: str, body: str, expected: tuple[str, str]) -> None:
    assert judge(body, status=status, kind=kind) == expected


def test_misuse_an_empty_title_or_one_of_punctuation_names_nothing() -> None:
    assert judge("<html><body>– – –</body></html>", title=" – ") == ("failed", "no_title")
    assert judge("<html><body></body></html>", title="") == ("failed", "no_title")


def test_latin_1_is_read_as_declared() -> None:
    body = f"<html><body>{TITLE} – Gewässer</body></html>".replace("–", "-").encode("latin-1")
    result = judge_page(LINK, LINK, 200, "text/html; charset=ISO-8859-1", body, title="Gewässer", identifiers=(),
                        rules=RULES)
    assert result == ("passed", "ok")


@pytest.mark.parametrize(
    ("url", "identifiers", "pattern"),
    [
        ("https://www.govdata.de/suche/daten/3d-meshes-brandenburg", (), "www.govdata.de/suche/daten/{x}"),
        ("https://www.govdata.de/suche/daten/bodenkarte", ("bodenkarte",), "www.govdata.de/suche/daten/{id}"),
        (
            "https://www.geoportal.rlp.de/map?LAYER%5Bzoom%5D=1&LAYER%5Bid%5D=50381",
            (),
            "www.geoportal.rlp.de/map?LAYER%5Bid%5D&LAYER%5Bzoom%5D",
        ),
        (
            "https://data.geo.admin.ch/browser/index.html#/collections/ch.bafu.boden",
            ("ch.bafu.boden",),
            "data.geo.admin.ch/browser/index.html#/collections/{id}",
        ),
        ("http://amt.example.org/x", (), "invalid"),
    ],
)
def test_link_patterns(url: str, identifiers: tuple[str, ...], pattern: str) -> None:
    assert link_pattern(url, identifiers) == pattern


# --- The rules file ---------------------------------------------------------------------------------------------------


def test_the_shipped_rules_load_with_the_proposed_guard() -> None:
    rules = read_link_rules(LINKCHECK_FILE)
    assert (rules.guard_min_checked, rules.guard_failed_share, rules.recheck_days) == (20, 0.25, 30)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"guard_failed_share": 0}, "guard_failed_share lies between"),
        ({"recheck_days": 1.5}, "recheck_days is a whole number"),
        ({"error_words": []}, "error_words is a list of words"),
        ({"surprise": 1}, "holds exactly"),
    ],
)
def test_a_wrong_rules_file(tmp_path: Path, change: dict[str, object], message: str) -> None:
    import yaml

    data = yaml.safe_load(LINKCHECK_FILE.read_text(encoding="utf-8"))
    data.update(change)
    path = tmp_path / "linkcheck.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(EntryFileError, match=message):
        read_link_rules(path)


# --- Through the gateway ----------------------------------------------------------------------------------------------


def due(key: str, url: str, title: str = TITLE) -> DueLink:
    return DueLink(f"t.{key}", "t", "in_review", url, title, (key,), 0)


def public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def opener(handler: Callable[[httpx.Request], httpx.Response], policies: list[Policy]):  # type: ignore[no-untyped-def]
    async def nosleep(_: float) -> None:
        return None

    @asynccontextmanager
    async def open_gateway(policy: Policy) -> AsyncIterator[Gateway]:
        policies.append(policy)
        async with Gateway(policy, transport=httpx.MockTransport(handler), resolve=public, sleep=nosleep) as gateway:
            yield gateway

    return open_gateway


def site(pages: dict[str, httpx.Response], robots: str = "") -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots) if robots else httpx.Response(404)
        # The gateway connects to the address it resolved and names the host in the header.
        return pages.get(f"{request.headers['host']}{request.url.raw_path.decode()}", httpx.Response(404))

    return handler


def page(title: str = TITLE) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": HTML}, text=f"<html><body><h1>{title}</h1></body></html>")


pytestmark_anyio = pytest.mark.anyio  # only the tests through the gateway are async


@pytestmark_anyio
async def test_a_run_checks_each_link_through_the_gateway_and_learns_where_a_redirect_leads() -> None:
    pages = {
        "amt.example.org/ok": page(),
        "amt.example.org/weg": httpx.Response(410),
        "amt.example.org/kaputt": httpx.Response(503),
        "doi.example.org/10.1/x": httpx.Response(302, headers={"location": "https://anbieter.example.org/x"}),
        "anbieter.example.org/x": page(),
    }
    policies: list[Policy] = []
    results = await check_links(
        [
            due("ok", "https://amt.example.org/ok"),
            due("weg", "https://amt.example.org/weg"),
            due("kaputt", "https://amt.example.org/kaputt"),
            due("doi", "https://doi.example.org/10.1/x"),
            due("http", "http://amt.example.org/ok"),
        ],
        rules=RULES,
        hosts={},
        open_gateway=opener(site(pages), policies),
        deadline=float("inf"),
    )
    found = {r.dataset_id: (r.outcome, r.reason, r.final_host) for r in results}
    assert found == {
        "t.ok": ("passed", "ok", "amt.example.org"),
        "t.weg": ("failed", "http_410", None),
        "t.kaputt": ("unchecked", "http_503", None),
        "t.doi": ("passed", "ok", "anbieter.example.org"),
        "t.http": ("failed", "bad_address", None),
    }
    # The first round allows exactly the hosts of the links, the second adds the host the redirect led to.
    assert [sorted(p.allowed_hosts) for p in policies] == [
        ["amt.example.org", "doi.example.org"],
        ["amt.example.org", "anbieter.example.org", "doi.example.org"],
    ]


@pytestmark_anyio
async def test_robots_makes_a_link_uncheckable_without_asking_for_it() -> None:
    asked: list[str] = []
    handler = site({"amt.example.org/daten/x": page()}, robots="User-agent: *\nDisallow: /daten/\n")

    def counting(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        return handler(request)

    results = await check_links(
        [due("x", "https://amt.example.org/daten/x")],
        rules=RULES,
        hosts={},
        open_gateway=opener(counting, []),
        deadline=float("inf"),
    )
    assert [(r.outcome, r.reason) for r in results] == [("unchecked", "robots")]
    assert asked == ["/robots.txt"]


@pytestmark_anyio
async def test_the_budget_leaves_the_rest_for_the_next_run() -> None:
    ticks = iter([0.0, 10.0, 10.0])
    results = await check_links(
        [due("a", "https://amt.example.org/a"), due("b", "https://amt.example.org/b")],
        rules=RULES,
        hosts={},
        open_gateway=opener(site({"amt.example.org/a": page(), "amt.example.org/b": page()}), []),
        deadline=5.0,
        clock=lambda: next(ticks),
    )
    assert [r.dataset_id for r in results] == ["t.a"]


def test_the_policy_keeps_the_limits_of_hosts_yaml_and_is_slow_elsewhere() -> None:
    hosts = {"data.geo.admin.ch": HostLimit(connections=6, interval_s=2.0, reason="test")}
    policy = link_policy(frozenset({"data.geo.admin.ch", "amt.example.org"}), hosts, RULES)
    assert policy.obey_robots and not policy.robots_exceptions and not policy.retry_rate_limited
    assert policy.interval_for("data.geo.admin.ch") == 2.0 and policy.interval_for("amt.example.org") == 1.0
    assert policy.connections_for("amt.example.org") == 1 and policy.connections_for("data.geo.admin.ch") == 6


def test_misuse_minutes_out_of_range_is_refused(capsys: pytest.CaptureFixture[str], monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(linkcheck, "load_link_rules", lambda: replace(RULES))
    assert linkcheck.main(["--minutes", "0"]) == 1
    assert "--minutes" in capsys.readouterr().err
