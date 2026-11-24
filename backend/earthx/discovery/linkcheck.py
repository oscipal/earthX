"""The automatic check of the link of every harvested listed entry (M5-67; docs/plans/m5/m5-67-harvest-automatisch.md
§4-§4c; adr/0033 §8.5, Otto 24.11.2026).

    python -m earthx.discovery.linkcheck [--dry-run] [--minutes N]

An entry becomes visible only once its own link passed. Passed: ``200`` after the redirects; the page is no start page
of its host, no error page and no login page; the title or an identifier of the dataset stands on the page, in its
text, its ``<title>``, a ``<meta>`` value, JSON-LD or the canonical link (portals that load their text by script
still name the dataset there). ``robots.txt``, no answer, ``429`` and ``5xx`` make a link ``unchecked``: a new entry
stays invisible, and so does a published one (Otto, 24.11.2026). A link to a catalogue's own page of a dataset can be
checked through the catalogue's API instead, where its seed file says so (``catalog_page_check``, F12 = 2).

Every request goes through ``gateway`` (KLAERUNGEN B8) with the spacing of ``hosts.yaml`` (else one connection and
1 s per host) and ``robots.txt``; the allowlist is exactly the hosts of the links due. A redirect to another host is
allowed (``doi.org`` → the provider): such hosts are learned in a first round and their links checked again in a
second, with those hosts added. The rules and thresholds live in ``backend/catalog/linkcheck.yaml``; the results in
``earthx_link_check`` (``catalog.link_checks``). Nothing of a page is kept or logged, only codes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cache
from html.parser import HTMLParser
from pathlib import Path

import psycopg

from earthx.catalog.datasets import CATALOG_DIR, registry
from earthx.catalog.entry_files import EntryFileError, read_yaml
from earthx.catalog.glossary import normalize
from earthx.catalog.hosts import HostLimit
from earthx.catalog.link_checks import (
    Applied,
    DueLink,
    GroupCount,
    LinkResult,
    apply_results,
    due_links,
    guard_results,
    record_results,
)
from earthx.catalog.registry import ConfigError
from earthx.catalog.sources import SourceConfig, SourceProtocol, read_sources
from earthx.discovery.harvest import source_policy
from earthx.discovery.links import is_start_page, url_parts
from earthx.discovery.source_gateway import open_source_gateway
from earthx.gateway import (
    AddressRejected,
    Gateway,
    GatewayError,
    HostResting,
    Policy,
    ResponseTooLarge,
    RobotsDisallowed,
    TooManyRedirects,
    UpstreamError,
    UpstreamUnreachable,
    UrlRejected,
    UrlTooLong,
    normalize_host,
    user_agent_from_env,
)
from earthx.logging import configure_logging

__all__ = [
    "LINKCHECK_FILE",
    "LinkRules",
    "LinkRun",
    "catalogue_name",
    "check_links",
    "judge_page",
    "link_pattern",
    "link_policy",
    "load_link_rules",
    "read_link_rules",
    "run_linkcheck",
    "summary_text",
]

LINKCHECK_FILE = CATALOG_DIR / "linkcheck.yaml"
#: Names of datasets asked in one ``package_search`` of a catalogue's API: well below the gateway's URL limit.
API_BATCH = 40
#: A CKAN name, as the extract fills ``{name}`` of ``catalog_page`` (``discovery.ckan``).
_CKAN_NAME = re.compile(r"[a-z0-9_-]{2,100}")
#: A STAC collection id as ``{id}`` of ``catalog_page`` (letters, digits, '.', '_', '-'; nothing that leaves the path).
_STAC_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")
#: The reason a gateway gives when a redirect leads to a host outside the allowlist (``policy.inspect_url``).
_NOT_ALLOWED = "host is not on the allowlist"
_TEXT_TYPES = ("html", "xml", "json", "text/plain")
#: Without a rule for its host, a host is asked with one connection and this spacing (M5-20 A6).
_DEFAULT_INTERVAL_S = 1.0
_KEYS = frozenset(
    {
        "budget_minutes",
        "recheck_days",
        "guard_min_checked",
        "guard_failed_share",
        "parallel_hosts",
        "max_redirect_hosts",
        "max_page_bytes",
        "min_identifier_chars",
        "title_word_share",
        "error_words",
        "login_path_parts",
        "login_words",
    }
)


@dataclass(frozen=True, slots=True)
class LinkRules:
    budget_minutes: float
    recheck_days: int
    guard_min_checked: int
    guard_failed_share: float
    parallel_hosts: int
    max_redirect_hosts: int
    max_page_bytes: int
    min_identifier_chars: int
    title_word_share: float
    #: Each phrase as its normal form.
    error_words: tuple[str, ...]
    login_path_parts: frozenset[str]
    login_words: tuple[str, ...]


def _number(path: Path, data: Mapping[str, object], key: str, low: float, high: float, *, whole: bool) -> float:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (whole and not isinstance(value, int)):
        raise EntryFileError(f"{path.name}: {key} is a {'whole ' if whole else ''}number")
    if not low <= value <= high:
        raise EntryFileError(f"{path.name}: {key} lies between {low:g} and {high:g}")
    return value


def _words(path: Path, data: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = data[key]
    if not isinstance(value, list) or not value or not all(isinstance(v, (str, int)) for v in value):
        raise EntryFileError(f"{path.name}: {key} is a list of words")
    found = tuple(normalize(str(v)) for v in value)
    if not all(found):
        raise EntryFileError(f"{path.name}: {key} holds a word without letters or digits")
    return found


def read_link_rules(path: Path) -> LinkRules:
    data = read_yaml(path)
    if not isinstance(data, dict) or set(data) != _KEYS:
        raise EntryFileError(f"{path.name}: holds exactly {', '.join(sorted(_KEYS))}")
    return LinkRules(
        budget_minutes=_number(path, data, "budget_minutes", 1, 24 * 60, whole=False),
        recheck_days=int(_number(path, data, "recheck_days", 1, 365, whole=True)),
        guard_min_checked=int(_number(path, data, "guard_min_checked", 2, 10_000, whole=True)),
        guard_failed_share=_number(path, data, "guard_failed_share", 0.01, 1, whole=False),
        parallel_hosts=int(_number(path, data, "parallel_hosts", 1, 256, whole=True)),
        max_redirect_hosts=int(_number(path, data, "max_redirect_hosts", 0, 10_000, whole=True)),
        max_page_bytes=int(_number(path, data, "max_page_bytes", 16_384, 64 * 1024 * 1024, whole=True)),
        min_identifier_chars=int(_number(path, data, "min_identifier_chars", 3, 64, whole=True)),
        title_word_share=_number(path, data, "title_word_share", 0.5, 1, whole=False),
        error_words=_words(path, data, "error_words"),
        login_path_parts=frozenset(w.replace(" ", "-") for w in _words(path, data, "login_path_parts")),
        login_words=_words(path, data, "login_words"),
    )


@cache
def load_link_rules() -> LinkRules:
    return read_link_rules(LINKCHECK_FILE)


# --- One page ---------------------------------------------------------------------------------------------------------


class _Page(HTMLParser):
    """What a page says about itself: its text, ``<title>``, first heading, ``<meta>`` values, the canonical link and
    JSON-LD, and whether it asks for a password. Scripts and styles are no text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: list[str] = []
        self.heading: list[str] = []
        self.text: list[str] = []
        self.meta: list[str] = []
        self.json_ld: list[str] = []
        self.password = False
        self._mode: str | None = None
        self._headings = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value or "" for name, value in attrs}
        if tag == "title":
            self._mode = "title"
        elif tag == "h1" and self._headings == 0:
            self._mode = "h1"
        elif tag == "script":
            self._mode = "json_ld" if values.get("type", "").lower() == "application/ld+json" else "skip"
        elif tag in ("style", "template"):
            self._mode = "skip"
        elif tag == "meta" and values.get("content"):
            self.meta.append(values["content"])
        elif tag == "link" and "canonical" in values.get("rel", "").lower().split() and values.get("href"):
            self.meta.append(values["href"])
        elif tag == "input" and values.get("type", "").lower() == "password":
            self.password = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1" and self._mode == "h1":
            self._headings += 1
        if tag in ("title", "h1", "script", "style", "template"):
            self._mode = None

    def handle_data(self, data: str) -> None:
        if self._mode == "skip":
            return
        if self._mode == "title":
            self.title.append(data)
        elif self._mode == "json_ld":
            self.json_ld.append(data)
        else:
            if self._mode == "h1":
                self.heading.append(data)
            self.text.append(data)


def _decode(body: bytes, content_type: str) -> str:
    charset = "utf-8"
    for part in content_type.split(";")[1:]:
        name, _, value = part.strip().partition("=")
        if name.lower() == "charset" and value:
            charset = value.strip('"').lower()
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _json_text(raw: str) -> str:
    """The strings of a JSON-LD block (names, identifiers), or the block as it is where it is no JSON."""
    try:
        document = json.loads(raw)
    except ValueError:
        return raw
    found: list[str] = []

    def walk(value: object) -> None:
        if isinstance(value, str):
            found.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(document)
    return " ".join(found)


def _has(haystack: str, phrase: str) -> bool:
    return bool(phrase) and f" {phrase} " in f" {haystack} "


def _title_on(title: str, haystack: str, share: float) -> bool:
    wanted = normalize(title)
    if not wanted:
        return False
    if _has(haystack, wanted):
        return True
    long_words = [w for w in wanted.split() if len(w) >= 4]
    if len(long_words) < 4:
        return False
    words = set(haystack.split())
    return sum(w in words for w in long_words) >= share * len(long_words)


def judge_page(
    link: str,
    final_url: str,
    status: int,
    content_type: str,
    body: bytes,
    *,
    title: str,
    identifiers: Sequence[str],
    rules: LinkRules,
) -> tuple[str, str]:
    """``(outcome, reason)`` for a page the gateway fetched without an error (plan §4)."""
    if status != 200:
        return "failed", f"http_{status}"
    kind = content_type.split(";")[0].strip().lower()
    if not any(t in kind for t in _TEXT_TYPES):
        return "failed", "not_a_page"
    text = _decode(body, content_type)
    page = _Page()
    if "html" in kind:
        page.feed(text)
        page.close()
    else:
        page.text.append(text)
    final = url_parts(final_url)
    if final_url != link and is_start_page(final_url) and not is_start_page(link):
        return "failed", "start_page"
    if final is not None and rules.login_path_parts & {p.lower() for p in final[1].split("/") if p}:
        return "failed", "login_page"
    page_title = normalize(" ".join(page.title))
    own = normalize(" ".join([*page.text, *page.title, *(_json_text(j) for j in page.json_ld)]))
    haystack = f"{own} {normalize(' '.join(page.meta))}"
    # An identifier that stands in the link itself counts only in what the page says of itself: an app that answers
    # every path with 200 echoes the address it was asked for in its canonical link and og:url (review, 24.11.2026).
    echoed = normalize(link)
    named = _title_on(title, haystack, rules.title_word_share) or any(
        _has(own if _has(echoed, normalize(i)) else haystack, normalize(i))
        for i in identifiers
        if len(i) >= rules.min_identifier_chars
    )
    if any(_has(page_title, w) for w in rules.error_words) and not _title_on(title, page_title, rules.title_word_share):
        return "failed", "error_page"
    if named:
        return "passed", "ok"
    heading = normalize(" ".join([*page.title, *page.heading]))
    if page.password or any(_has(heading, w) for w in rules.login_words):
        return "failed", "login_page"
    return "failed", "no_title"


def _variable(segment: str, identifiers: frozenset[str]) -> str:
    if segment.lower() in identifiers:
        return "{id}"
    if any(c.isdigit() for c in segment) or len(segment) > 40:
        return "{x}"
    if len(segment) >= 12 and any(c in segment for c in "-_."):
        return "{x}"
    return segment


def link_pattern(url: str, identifiers: Sequence[str] = ()) -> str:
    """Host and path of ``url`` with the dataset's identifiers as ``{id}`` and parts that vary per dataset as ``{x}``;
    of a query only the names of its parameters; a fragment as a path (plan §4). ``invalid`` for no address."""
    parts = url_parts(url)
    if parts is None:
        return "invalid"
    host, path, query, fragment = parts
    ids = frozenset(i.lower() for i in identifiers if i)
    pattern = host + "/".join(_variable(s, ids) if s else "" for s in path.split("/"))
    if query:
        pattern += "?" + "&".join(sorted({kv.split("=", 1)[0] for kv in query[1:].split("&") if kv}))
    if fragment:
        pattern += "#" + "/".join(_variable(s, ids) if s else "" for s in fragment[1:].split("/"))
    return pattern[:300]


# --- Many links -------------------------------------------------------------------------------------------------------


def link_policy(allowed: frozenset[str], hosts: Mapping[str, HostLimit], rules: LinkRules) -> Policy:
    """Exactly the hosts in ``allowed``; those of ``hosts.yaml`` with their limits, the others one connection and 1 s
    apart; ``robots.txt`` obeyed, no exception; a ``429`` not tried again here (the next run comes)."""
    known = {host: hosts[host] for host in allowed if host in hosts}
    return Policy(
        allowed_hosts=allowed,
        max_connections_per_host=1,
        host_connections={host: limit.connections for host, limit in known.items()},
        host_intervals={host: limit.interval_s for host, limit in known.items() if limit.interval_s is not None},
        host_read_timeouts={host: limit.timeout_s for host, limit in known.items() if limit.timeout_s is not None},
        min_interval_s=_DEFAULT_INTERVAL_S,
        obey_robots=True,
        max_redirects=5,
        max_response_bytes=rules.max_page_bytes,
        read_timeout_s=20.0,
        retry_rate_limited=False,
    )


def _host(url: str) -> str | None:
    parts = url_parts(url)
    if parts is None:
        return None
    try:
        return normalize_host(parts[0])
    except UrlRejected:
        return None


def _error(error: GatewayError) -> tuple[str, str, int | None]:
    """``(outcome, reason, status)`` of what the gateway refused or could not deliver."""
    if isinstance(error, UpstreamError):
        code = error.status_code
        return ("unchecked" if code == 429 or code >= 500 else "failed"), f"http_{code}", code
    if isinstance(error, RobotsDisallowed):
        return "unchecked", "robots", None
    if isinstance(error, UrlRejected) and error.reason == _NOT_ALLOWED:
        return "unchecked", "redirect_host", None
    if isinstance(error, (UrlRejected, UrlTooLong, AddressRejected)):
        return "failed", "bad_address", None
    if isinstance(error, TooManyRedirects):
        return "failed", "too_many_redirects", None
    if isinstance(error, HostResting):
        return "unchecked", "host_resting", None
    if isinstance(error, ResponseTooLarge):
        return "unchecked", "too_large", None
    if isinstance(error, UpstreamUnreachable):
        return "unchecked", "unreachable", None
    return "unchecked", "gateway", None


OpenGateway = Callable[[Policy], AbstractAsyncContextManager[Gateway]]


async def _check_one(gateway: Gateway, due: DueLink, host: str, rules: LinkRules) -> tuple[LinkResult, str | None]:
    """The result for one link, and the host a redirect wanted to leave for (to learn it)."""
    pattern = link_pattern(due.url, due.identifiers)
    try:
        response = await gateway.get(due.url, retry=True)
    except GatewayError as error:
        outcome, reason, status = _error(error)
        learned = getattr(error, "host", None) if reason == "redirect_host" else None
        return LinkResult(due.dataset_id, due.url, host, pattern, outcome, reason, status, None), learned
    outcome, reason = judge_page(
        due.url,
        response.url or due.url,
        response.status_code,
        response.headers.get("content-type", ""),
        response.content,
        title=due.title,
        identifiers=due.identifiers,
        rules=rules,
    )
    final_host = _host(response.url) if response.url else host
    return LinkResult(due.dataset_id, due.url, host, pattern, outcome, reason, response.status_code, final_host), None


async def _round(
    groups: Mapping[str, Sequence[DueLink]],
    allowed: frozenset[str],
    *,
    rules: LinkRules,
    hosts: Mapping[str, HostLimit],
    open_gateway: OpenGateway,
    deadline: float,
    clock: Callable[[], float],
) -> list[tuple[LinkResult, str | None]]:
    found: list[tuple[LinkResult, str | None]] = []
    places = asyncio.Semaphore(rules.parallel_hosts)

    async def one_host(host: str, links: Sequence[DueLink], gateway: Gateway) -> None:
        async with places:
            for due in links:
                if clock() >= deadline:
                    return
                found.append(await _check_one(gateway, due, host, rules))

    async with open_gateway(link_policy(allowed, hosts, rules)) as gateway:
        await asyncio.gather(*(one_host(host, links, gateway) for host, links in sorted(groups.items())))
    return found


def catalogue_name(source: SourceConfig, url: str) -> str | None:
    """The CKAN name or the STAC collection id in ``url`` where it has the form of the source's ``catalog_page``, else
    ``None``."""
    if source.catalog_page is None:
        return None
    stac = source.protocol is SourceProtocol.STAC_API
    prefix, _, suffix = source.catalog_page.partition("{id}" if stac else "{name}")
    if not url.startswith(prefix) or not url.endswith(suffix) or len(url) <= len(prefix) + len(suffix):
        return None
    name = url[len(prefix) : len(url) - len(suffix)]
    return name if (_STAC_ID if stac else _CKAN_NAME).fullmatch(name) else None


async def _collection_round(
    source: SourceConfig,
    items: Sequence[tuple[DueLink, str]],
    *,
    hosts: Mapping[str, HostLimit],
    open_gateway: OpenGateway,
    deadline: float,
    clock: Callable[[], float],
) -> list[LinkResult]:
    """The links to a STAC browser's page of a collection (``#/collections/<id>``: the part after ``#`` never reaches
    the server), checked through the collection the browser shows (M5-67 F13 = 1): passed where
    ``<endpoint>/collections/<id>`` answers with that id, under the source's own policy."""
    found: list[LinkResult] = []
    async with open_gateway(source_policy(source, hosts)) as gateway:
        for item, collection in items:
            if clock() >= deadline:
                break
            pattern = link_pattern(item.url, item.identifiers)
            host = _host(item.url) or "invalid"
            try:
                response = await gateway.get(f"{source.endpoint}/collections/{collection}")
                body = response.json()
                same = isinstance(body, dict) and body.get("id") == collection
            except GatewayError as error:
                outcome, reason, status = _error(error)
                found.append(LinkResult(item.dataset_id, item.url, host, pattern, outcome, reason, status, source.host))
                continue
            except ValueError:
                same = None
            if same is None:
                outcome, reason = "unchecked", "api_shape"
            else:
                outcome, reason = ("passed", "ok") if same else ("failed", "not_in_catalogue")
            found.append(
                LinkResult(item.dataset_id, item.url, host, pattern, outcome, reason, response.status_code, source.host)
            )
    return found


async def _catalogue_round(
    source: SourceConfig,
    items: Sequence[tuple[DueLink, str]],
    *,
    hosts: Mapping[str, HostLimit],
    open_gateway: OpenGateway,
    deadline: float,
    clock: Callable[[], float],
) -> list[LinkResult]:
    """The links to the catalogue's own page of a dataset, checked through its CKAN API (M5-67 F12 = 2): passed where a
    dataset of exactly the name in the link exists. ``package_search`` with up to :data:`API_BATCH` names a request,
    under the source's own policy (its host, its limits, its robots exception)."""
    found: list[LinkResult] = []

    def result(item: DueLink, outcome: str, reason: str, status: int | None) -> LinkResult:
        pattern = link_pattern(item.url, item.identifiers)
        host = _host(item.url) or "invalid"
        return LinkResult(item.dataset_id, item.url, host, pattern, outcome, reason, status, source.host)

    async with open_gateway(source_policy(source, hosts)) as gateway:
        for start in range(0, len(items), API_BATCH):
            if clock() >= deadline:
                break
            chunk = items[start : start + API_BATCH]
            names = sorted({name for _, name in chunk})
            query = "name:(" + " OR ".join(f'"{name}"' for name in names) + ")"
            try:
                response = await gateway.get(
                    f"{source.endpoint}/package_search", params={"fq": query, "rows": len(names), "fl": "name"}
                )
                body = response.json()
                present = {row.get("name") for row in body["result"]["results"]} if body.get("success") else None
            except GatewayError as error:
                outcome, reason, status = _error(error)
                found += [result(item, outcome, reason, status) for item, _ in chunk]
                continue
            except (ValueError, KeyError, TypeError, AttributeError):
                present = None
            if present is None:
                found += [result(item, "unchecked", "api_shape", response.status_code) for item, _ in chunk]
                continue
            for item, name in chunk:
                passed = name in present
                found.append(
                    result(item, "passed" if passed else "failed", "ok" if passed else "not_in_catalogue", 200)
                )
    return found


async def check_links(
    due: Sequence[DueLink],
    *,
    rules: LinkRules,
    hosts: Mapping[str, HostLimit],
    open_gateway: OpenGateway,
    deadline: float,
    clock: Callable[[], float] = time.monotonic,
    sources: Mapping[str, SourceConfig] | None = None,
) -> list[LinkResult]:
    """Check ``due`` host by host until ``deadline`` (``clock`` seconds); what is left stays due. A link that is no
    ``https`` address fails without a request. A link to the catalogue page of a source whose ``catalog_page_check``
    says ``api`` is checked through the source's API, and stays unchecked until Otto confirmed the form of the page."""
    results: dict[str, LinkResult] = {}
    groups: dict[str, list[DueLink]] = defaultdict(list)
    catalogue: dict[str, list[tuple[DueLink, str]]] = defaultdict(list)
    for item in due:
        host = _host(item.url)
        source = (sources or {}).get(item.source_id)
        name = None if source is None or source.catalog_page_check.via != "api" else catalogue_name(source, item.url)
        if host is None:
            pattern = link_pattern(item.url, item.identifiers)
            results[item.dataset_id] = LinkResult(
                item.dataset_id, item.url, "invalid", pattern, "failed", "bad_address", None, None
            )
        elif name is not None and source is not None and source.catalog_page_check.form_confirmed_on is None:
            pattern = link_pattern(item.url, item.identifiers)
            results[item.dataset_id] = LinkResult(
                item.dataset_id, item.url, host, pattern, "unchecked", "form_unconfirmed", None, None
            )
        elif name is not None:
            catalogue[item.source_id].append((item, name))
        else:
            groups[host].append(item)
    options = {"hosts": hosts, "open_gateway": open_gateway, "deadline": deadline, "clock": clock}

    async def pages() -> list[LinkResult]:
        if not groups:
            return []
        found: dict[str, LinkResult] = {}
        allowed = frozenset(groups)
        learned: dict[str, str] = {}
        for result, target in await _round(groups, allowed, rules=rules, **options):
            found[result.dataset_id] = result
            if target is not None:
                learned[result.dataset_id] = target
        new_hosts = sorted({h for h in learned.values() if h not in allowed})[: rules.max_redirect_hosts]
        if new_hosts:
            by_id = {item.dataset_id: item for item in due}
            again: dict[str, list[DueLink]] = defaultdict(list)
            for dataset_id, target in learned.items():
                if target in new_hosts:
                    again[found[dataset_id].host].append(by_id[dataset_id])
            for result, _ in await _round(again, allowed | frozenset(new_hosts), rules=rules, **options):
                found[result.dataset_id] = result
        return list(found.values())

    rounds = [pages()] + [
        (
            _collection_round
            if (sources or {})[source_id].protocol is SourceProtocol.STAC_API
            else _catalogue_round
        )((sources or {})[source_id], items, **options)
        for source_id, items in sorted(catalogue.items())
    ]
    for done in await asyncio.gather(*rounds):
        results.update((r.dataset_id, r) for r in done)
    return list(results.values())


# --- One run ----------------------------------------------------------------------------------------------------------


@dataclass(slots=True)
class LinkRun:
    """What one run of the check did; ``dry_run``: the trial run, which counts but neither hides nor brings back."""

    dry_run: bool
    due: int
    due_by_host: Counter[str] = field(default_factory=Counter)
    results: list[LinkResult] = field(default_factory=list)
    groups: list[GroupCount] = field(default_factory=list)
    applied: Applied = field(default_factory=lambda: Applied(0, 0, 0))


def run_linkcheck(
    conn: psycopg.Connection,
    *,
    rules: LinkRules,
    hosts: Mapping[str, HostLimit],
    dry_run: bool,
    minutes: float | None = None,
    open_gateway: OpenGateway = open_source_gateway,
    clock: Callable[[], float] = time.monotonic,
    sources: Mapping[str, SourceConfig] | None = None,
    only: Sequence[str] | None = None,
) -> LinkRun:
    """Check what is due within the budget, keep the results, guard hosts and patterns that failed for a large share,
    then hide and bring back (plan §4a, §4c); with ``dry_run`` the last step only counts. ``only`` keeps the run to
    these sources (every source where ``None``)."""
    started = datetime.now(UTC)
    due = due_links(conn, recheck_days=rules.recheck_days, only=only)
    run = LinkRun(dry_run=dry_run, due=len(due), due_by_host=Counter(_host(d.url) or "invalid" for d in due))
    deadline = clock() + 60 * (rules.budget_minutes if minutes is None else minutes)
    run.results = asyncio.run(
        check_links(
            due, rules=rules, hosts=hosts, open_gateway=open_gateway, deadline=deadline, clock=clock, sources=sources
        )
    )
    # One transaction: a result is never seen unguarded, and a run that breaks off leaves none behind (review).
    with conn.transaction():
        record_results(conn, run.results, datetime.now(UTC))
        run.groups = guard_results(
            conn, started, min_checked=rules.guard_min_checked, failed_share=rules.guard_failed_share
        )
        run.applied = apply_results(conn, dry_run=dry_run, only=only)
    return run


def summary_text(run: LinkRun, hosts: Mapping[str, HostLimit], *, top: int = 20) -> str:
    """The run in German for the window and the files of the run: what was due per host with the time it takes at its
    spacing, the results per reason, the guarded hosts and patterns first, and what was or would be hidden."""
    outcomes = Counter(r.outcome for r in run.results)
    reasons = Counter(r.reason for r in run.results if r.outcome != "passed")
    lines = [
        "Linkprüfung" + (" (Probelauf: nichts verborgen, nichts freigegeben)" if run.dry_run else ""),
        f"  fällig {run.due}, geprüft {len(run.results)}: bestanden {outcomes['passed']}, durchgefallen"
        f" {outcomes['failed']}, nicht prüfbar {outcomes['unchecked']}; übrig für den nächsten Lauf"
        f" {run.due - len(run.results)}",
        "  Gründe: " + (", ".join(f"{k} {n}" for k, n in reasons.most_common()) or "keine"),
        f"  {'würde verbergen' if run.dry_run else 'verborgen'} {run.applied.hidden},"
        f" {'würde zurückholen' if run.dry_run else 'zurückgeholt'} {run.applied.restored},"
        f" mit einer Freigabe sichtbar {run.applied.publishable}",
        "  Fällig je Host (Links × Abstand, ohne Crawl-delay; Katalogseiten mit Prüfung über die API brauchen eine"
        f" Anfrage je {API_BATCH}):",
    ]
    for host, count in run.due_by_host.most_common(top):
        limit = hosts.get(host)
        interval = limit.interval_s if limit is not None and limit.interval_s is not None else _DEFAULT_INTERVAL_S
        lines.append(f"    {host}: {count} Links, rund {count * interval / 3600:.1f} h")
    guarded = [g for g in run.groups if g.guarded]
    lines.append("  Geschützt (nichts verborgen, nichts freigegeben): " + ("keine" if not guarded else ""))
    for group in guarded:
        lines.append(
            f"    {group.kind} {group.key}: geprüft {group.checked}, durchgefallen {group.failed}"
            f" ({group.failed / group.checked:.0%}), nicht prüfbar {group.unchecked}"
        )
    patterns = [g for g in run.groups if g.kind == "pattern" and not g.guarded and g.failed + g.unchecked]
    lines.append("  Muster mit Fehlschlägen:")
    for group in sorted(patterns, key=lambda g: -(g.failed + g.unchecked))[:top]:
        lines.append(
            f"    {group.key}: bestanden {group.passed}, durchgefallen {group.failed}, nicht prüfbar {group.unchecked}"
        )
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m earthx.discovery.linkcheck", description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="check and count, but hide and bring back nothing")
    parser.add_argument("--minutes", type=float, default=None, help="budget of this run (else linkcheck.yaml)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    configure_logging()
    try:
        user_agent_from_env()
        rules = load_link_rules()
        hosts = registry().host_limits
        sources = read_sources()
    except (ValueError, ConfigError, EntryFileError) as error:
        print(f"linkcheck failed: {error}", file=sys.stderr)
        return 1
    if args.minutes is not None and not 0 < args.minutes <= 24 * 60:
        print("linkcheck failed: --minutes lies above 0 and at most 1440", file=sys.stderr)
        return 1
    try:
        with psycopg.connect(autocommit=True) as conn:
            run = run_linkcheck(
                conn, rules=rules, hosts=hosts, dry_run=args.dry_run, minutes=args.minutes, sources=sources
            )
    except psycopg.Error as error:
        # Only the kind: the text of a database error can quote a row of foreign content.
        print(f"linkcheck failed: database error {type(error).__name__}", file=sys.stderr)
        return 1
    print(summary_text(run, hosts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
