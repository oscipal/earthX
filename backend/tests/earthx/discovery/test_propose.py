"""Candidates of the full way without a database (M5-20 plan §14.1): the pure rules, Verify of a file through the
gateway with a transport stand-in, and the probe. No source is asked (adr/0002)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import replace

import httpx
import numpy as np
import pytest
import yaml
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from earthx.catalog.registry import Maturity
from earthx.catalog.sources import CkanFilter, SourceConfig, SourceProtocol, StacFilter
from earthx.discovery.propose import (
    MAX_PROBE_BYTES,
    ORIGIN,
    ProposeRun,
    Row,
    _Pending,
    _verify,
    check_file,
    data_region,
    declared_files,
    file_policy,
    probe_document,
    proposed_id,
    readable_declared,
    takeover_of,
)
from earthx.gateway import Gateway, Policy


def _source(protocol: SourceProtocol = SourceProtocol.CKAN) -> SourceConfig:
    source = SourceConfig(
        source_id="portal",
        protocol=SourceProtocol.CKAN,
        endpoint="https://ckan.example.org/api/3/action",
        catalog_page=None,
        filter=CkanFilter(None, "organization"),
        max_requests_per_run=20,
        max_pages_per_run=None,
        rows_per_page=None,
        full_every_days=7,
        robots_exception=None,
        maturity=Maturity.STABLE,
        enabled=True,
        country="CH",
        dedupe_rank=2,
    )
    if protocol is SourceProtocol.STAC_API:
        source = replace(source, protocol=protocol, endpoint="https://stac.example.org/v1", filter=StacFilter(()))
    return source


def _cog() -> bytes:
    with MemoryFile() as memory:
        with memory.open(
            driver="COG", width=512, height=512, count=1, dtype="uint8", crs="EPSG:2056",
            transform=from_origin(2_600_000, 1_200_000, 2, 2), blocksize=256,
        ) as dataset:
            dataset.write(np.zeros((1, 512, 512), dtype="uint8"))
        return memory.read()


COG = _cog()


class TestDeclaredFormat:
    @pytest.mark.parametrize(
        ("format_", "media_type", "readable"),
        [
            ("GeoTIFF", None, True),
            ("COG", None, True),
            ("tif", None, True),
            ("NetCDF", None, True),
            ("HDF5", None, True),
            ("ZARR", None, True),
            (None, "image/tiff; application=geotiff; profile=cloud-optimized", True),
            (None, "application/x-netcdf", True),
            ("JPEG2000", "image/jp2", False),
            ("ASCII Grid", None, False),
            ("WMS", None, False),
            ("CSV", "text/csv", False),
            (None, None, False),
        ],
    )
    def test_formats(self, format_: str | None, media_type: str | None, readable: bool) -> None:
        assert readable_declared(format_, media_type) is readable

    def test_files_https_only_at_most_three_each_once(self) -> None:
        found = {
            "distributions": [
                {"href": "http://amt.example.org/a.tif", "format": "TIFF"},
                {"href": "https://amt.example.org/b.tif", "format": "TIFF"},
                {"href": "https://amt.example.org/b.tif", "format": "GeoTIFF"},
                {"href": "https://amt.example.org/c.csv", "format": "CSV"},
                {"href": "https://amt.example.org/d.nc", "format": "NetCDF"},
                {"href": "https://amt.example.org/e.tif", "media_type": "image/tiff"},
                {"href": "https://amt.example.org/f.tif", "format": "COG"},
                "not a distribution",
                {"href": None, "format": "TIFF"},
            ]
        }
        assert declared_files(found) == [
            "https://amt.example.org/b.tif",
            "https://amt.example.org/d.nc",
            "https://amt.example.org/e.tif",
        ]

    def test_no_distributions(self) -> None:
        assert declared_files({}) == [] and declared_files({"distributions": None}) == []


class TestTakeover:
    def test_a_stac_collection_first(self) -> None:
        found = takeover_of("fsdi", ["doi:10.1/x", "coll:data.example.org/ch.a.b", "id:x"], ())
        assert found is not None and (found.via, found.key) == ("coll", "coll:data.example.org/ch.a.b")

    def test_an_identifier_unique_in_its_source_gives_also_listed_as(self) -> None:
        found = takeover_of("opendata-swiss", ["id:691cb471@swisstopo", "doi:10.1/x"], ())
        assert found is not None and found.via == "also_listed_as"
        assert found.also_listed_as == ("opendata-swiss:691cb471@swisstopo",)
        assert found.key == "also:opendata-swiss:691cb471@swisstopo"

    def test_a_repeated_identifier_falls_back_to_the_doi(self) -> None:
        found = takeover_of("portal", ["id:1", "doi:10.1/x"], ["id:1"])
        assert found is not None and (found.via, found.key) == ("doi", "doi:10.1/x")

    def test_nothing_unique_is_no_candidate(self) -> None:
        assert takeover_of("portal", ["id:1", "doi:10.1/x"], ["id:1", "doi:10.1/x"]) is None
        assert takeover_of("portal", [], ()) is None

    @pytest.mark.parametrize("identifier", ["with blank", "tab\there", "x" * 301])
    def test_an_identifier_the_registry_could_not_hold(self, identifier: str) -> None:
        assert takeover_of("portal", [f"id:{identifier}"], ()) is None


class TestProposedId:
    def test_a_stac_collection_keeps_its_id(self) -> None:
        found = {"source_key": "ch.swisstopo.swissimage-dop10", "title": "SWISSIMAGE 10 cm"}
        assert proposed_id(_source(SourceProtocol.STAC_API), found, ()) == "ch.swisstopo.swissimage-dop10"

    def test_a_ckan_find_by_its_title(self) -> None:
        found = {"source_key": "6c1f-uuid", "title": "Höhenmodell Zürich – Ausgabe 2024 (Rasterdaten)"}
        assert proposed_id(_source(), found, ()) == "hoehenmodell-zuerich-ausgabe-2024-rasterdaten"

    def test_a_taken_id_gets_the_source_in_front_and_then_a_number(self) -> None:
        found = {"source_key": "k", "title": "Relief"}
        assert proposed_id(_source(), found, {"relief"}) == "portal-relief"
        assert proposed_id(_source(), found, {"relief", "portal-relief"}) == "portal-relief-2"

    def test_a_long_title_is_cut_at_a_word(self) -> None:
        found = {"source_key": "k", "title": " ".join(["Bodenbedeckung"] * 10)}
        made = proposed_id(_source(), found, ())
        assert len(made) <= 60 and not made.endswith("-")

    @pytest.mark.parametrize("title", ["", "—", "東京"])
    def test_a_title_without_letters_falls_back_to_the_key(self, title: str) -> None:
        assert proposed_id(_source(), {"source_key": "Ab-12", "title": title}, ()) == "portal-ab-12"


@pytest.mark.parametrize(
    ("hosts", "region"),
    [
        (["sentinel-cogs.s3.us-west-2.amazonaws.com"], "aws:us-west-2"),
        (["a.s3.us-west-2.amazonaws.com", "b.s3.eu-central-1.amazonaws.com"], None),
        (["data.geo.admin.ch"], None),
        ([], None),
    ],
)
def test_data_region_only_for_one_aws_region(hosts: list[str], region: str | None) -> None:
    assert data_region(hosts) == region


# --- Through the gateway ----------------------------------------------------------------------------------------------


def _public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def _files(answers: dict[str, Callable[[httpx.Request], httpx.Response]]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        answer = answers.get(f"{request.headers['host']}{request.url.raw_path.decode()}")
        return answer(request) if answer else httpx.Response(404)

    return handler


def _ranged(body: bytes, *, cors: str | None = "*") -> Callable[[httpx.Request], httpx.Response]:
    def answer(request: httpx.Request) -> httpx.Response:
        headers = {"content-type": "image/tiff", "accept-ranges": "bytes"}
        if cors:
            headers["access-control-allow-origin"] = cors
        if request.method == "HEAD":
            return httpx.Response(200, headers={**headers, "content-length": str(len(body))})
        start, end = (int(v) for v in request.headers["range"].removeprefix("bytes=").split("-"))
        part = body[start : end + 1]
        headers["content-range"] = f"bytes {start}-{start + len(part) - 1}/{len(body)}"
        return httpx.Response(206, headers=headers, content=part)

    return answer


def _opener(handler: Callable[[httpx.Request], httpx.Response], policies: list[Policy], seen: list[httpx.Request]):  # type: ignore[no-untyped-def]
    async def nosleep(_: float) -> None:
        return None

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    @asynccontextmanager
    async def open_gateway(policy: Policy) -> AsyncIterator[Gateway]:
        policies.append(policy)
        async with Gateway(policy, transport=httpx.MockTransport(recording), resolve=_public, sleep=nosleep) as gateway:
            yield gateway

    return open_gateway


async def _check(answers: dict[str, Callable[[httpx.Request], httpx.Response]], href: str, seen: list[httpx.Request] | None = None):  # type: ignore[no-untyped-def]
    seen = [] if seen is None else seen
    async with _opener(_files(answers), [], seen)(file_policy(frozenset({"files.example.org", "other.example.org"}), {})) as gateway:
        return await check_file(gateway, href)


pytestmark_anyio = pytest.mark.anyio


@pytestmark_anyio
async def test_a_cog_with_ranges_passes_and_says_its_header() -> None:
    seen: list[httpx.Request] = []
    found = await _check({"files.example.org/a.tif": _ranged(COG)}, "https://files.example.org/a.tif", seen)
    assert (found.outcome, found.status, found.partial, found.cors, found.accept_ranges) == ("passed", 206, True, "any", "bytes")
    assert found.length == len(COG) and found.format is not None and found.format["format"] == "cog"
    assert [r.method for r in seen] == ["HEAD", "GET"]
    assert seen[1].headers["range"] == "bytes=0-16383" and seen[1].headers["origin"] == ORIGIN


@pytestmark_anyio
async def test_cors_for_the_origin_and_none() -> None:
    echoed = await _check({"files.example.org/a.tif": _ranged(COG, cors=ORIGIN)}, "https://files.example.org/a.tif")
    closed = await _check({"files.example.org/a.tif": _ranged(COG, cors=None)}, "https://files.example.org/a.tif")
    assert (echoed.cors, closed.cors) == ("origin", "none")


@pytestmark_anyio
@pytest.mark.parametrize(("status", "outcome"), [(401, "account"), (403, "account"), (404, "failed"), (500, "unchecked")])
async def test_what_a_refusal_means(status: int, outcome: str) -> None:
    found = await _check({"files.example.org/a.tif": lambda r: httpx.Response(status)}, "https://files.example.org/a.tif")
    assert (found.outcome, found.status, found.reason) == (outcome, status, f"http_{status}")


@pytestmark_anyio
async def test_a_head_refused_with_405_still_gets_its_bytes() -> None:
    ranged = _ranged(COG)
    found = await _check(
        {"files.example.org/a.tif": lambda r: httpx.Response(405) if r.method == "HEAD" else ranged(r)},
        "https://files.example.org/a.tif",
    )
    assert found.outcome == "passed"


@pytestmark_anyio
async def test_a_host_ignoring_range_is_no_candidate() -> None:
    whole = COG + b"\x00" * 100_000
    found = await _check(
        {"files.example.org/a.tif": lambda r: httpx.Response(200, headers={"content-type": "image/tiff"}, content=whole)},
        "https://files.example.org/a.tif",
    )
    assert (found.outcome, found.reason, found.partial) == ("failed", "no_range", False)


@pytestmark_anyio
async def test_an_error_page_with_200_fails() -> None:
    page = b"<!DOCTYPE html><html><title>Anmeldung</title></html>"
    found = await _check(
        {"files.example.org/a.tif": lambda r: httpx.Response(200, headers={"content-type": "text/html"}, content=page)},
        "https://files.example.org/a.tif",
    )
    assert (found.outcome, found.reason) == ("failed", "format_html")


@pytestmark_anyio
async def test_a_redirect_to_another_host_is_unchecked() -> None:
    found = await _check(
        {"files.example.org/a.tif": lambda r: httpx.Response(302, headers={"location": "https://elsewhere.example.net/a.tif"})},
        "https://files.example.org/a.tif",
    )
    assert (found.outcome, found.reason) == ("unchecked", "redirect_host")


@pytestmark_anyio
async def test_a_redirect_within_the_allowed_hosts_is_followed() -> None:
    found = await _check(
        {
            "files.example.org/a.tif": lambda r: httpx.Response(302, headers={"location": "https://other.example.org/a.tif"}),
            "other.example.org/a.tif": _ranged(COG),
        },
        "https://files.example.org/a.tif",
    )
    assert found.outcome == "passed" and found.final_host == "other.example.org"


def _row(key: str, files: list[str]) -> Row:
    found = {"source_key": key, "title": key, "distributions": [{"href": h, "format": "COG"} for h in files]}
    return Row(f"portal.{key}", key, "published", {"id": f"portal.{key}"}, (), None, None, found)


@pytestmark_anyio
async def test_new_hosts_stop_at_the_limit_and_files_are_asked_without_robots(monkeypatch: pytest.MonkeyPatch) -> None:
    from earthx.discovery import propose

    monkeypatch.setattr(propose, "MAX_NEW_HOSTS", 2)
    hrefs = [f"https://h{n}.example.org/a.tif" for n in range(3)]
    pending = [_Pending(_row(f"k{n}", [href]), {}, None, True, [href]) for n, href in enumerate(hrefs)]  # type: ignore[arg-type]
    policies: list[Policy] = []
    seen: list[httpx.Request] = []
    answers = {f"h{n}.example.org/a.tif": _ranged(COG) for n in range(3)}
    run = ProposeRun(trial=False)
    await _verify(pending, _source(), hosts={}, open_gateway=_opener(_files(answers), policies, seen), run=run)
    assert [p.checks[0].outcome for p in pending] == ["passed", "passed", "unchecked"]
    assert pending[2].checks[0].reason == "host_limit"
    assert policies[0].allowed_hosts == frozenset({"h0.example.org", "h1.example.org"})
    assert not policies[0].obey_robots and not any(r.url.path == "/robots.txt" for r in seen)


@pytestmark_anyio
async def test_a_stac_source_takes_one_data_asset_of_each_of_three_items() -> None:
    items = {
        "type": "FeatureCollection",
        "features": [
            {"id": f"i{n}", "assets": {
                "thumbnail": {"href": f"https://files.example.org/{n}.png", "type": "image/png", "roles": ["thumbnail"]},
                "data": {"href": f"https://files.example.org/{n}.tif", "type": "image/tiff; profile=cloud-optimized"},
            }}
            for n in range(5)
        ],
    }
    answers = {f"files.example.org/{n}.tif": _ranged(COG) for n in range(5)}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.headers["host"] == "stac.example.org":
            assert request.url.path == "/v1/collections/ch.a.b/items" and request.url.params["limit"] == "3"
            return httpx.Response(200, json=items)
        return _files(answers)(request)

    source = _source(SourceProtocol.STAC_API)
    pending = [_Pending(_row("ch.a.b", []), {}, None, True)]  # type: ignore[arg-type]
    policies: list[Policy] = []
    seen: list[httpx.Request] = []
    from earthx.catalog.hosts import HostLimit

    hosts = {"stac.example.org": HostLimit(connections=1, interval_s=1.0, reason="test")}
    await _verify(pending, source, hosts=hosts, open_gateway=_opener(handler, policies, seen), run=ProposeRun(False))
    assert len(pending[0].items) == 3
    assert pending[0].files == [f"https://files.example.org/{n}.tif" for n in range(3)]
    assert [c.outcome for c in pending[0].checks] == ["passed"] * 3
    # The items through the source's own policy (robots.txt obeyed), the files through their own.
    assert policies[0].obey_robots and policies[0].allowed_hosts == frozenset({"stac.example.org"})


def test_the_probe_stays_under_50_kb() -> None:
    row = _row("big", [])
    row = replace(row, content={"id": "x", "description": "d" * 80_000, "keywords": ["k"] * 10})
    items = [{"id": f"i{n}", "properties": {"note": "x" * 20_000}} for n in range(3)]
    text = probe_document(row, items, {"files": []})
    assert len(text.encode("utf-8")) <= MAX_PROBE_BYTES
    document = json.loads(text)
    assert set(document) == {"collection", "items", "verify"} and len(document["items"]) < 3


def test_the_probe_holds_no_signed_address() -> None:
    row = _row("signed", [])
    items = [{"id": "i", "assets": {"data": {"href": "https://b.example.org/a.tif?X-Amz-Signature=abc&x=1"}}}]
    text = probe_document(row, items, {"files": []})
    assert "abc" not in text and "X-Amz-Signature=[entfernt]" in text


# --- Review M5-20 PR 2: foreign data never stops the step -------------------------------------------------------------


@pytest.mark.parametrize(
    "asset",
    [
        {"href": "https://files.example.org/a.tif", "type": ["image/tiff"]},
        {"href": "https://files.example.org/a.tif", "roles": 5},
        {"href": "https://files.example.org/a.tif", "roles": "metadata"},
        {"href": 7, "type": "image/tiff"},
        "not an asset",
    ],
)
def test_an_asset_of_a_foreign_shape_is_no_data_file(asset: object) -> None:
    from earthx.discovery.propose import _data_assets

    assert _data_assets({"assets": {"data": asset}}) == []


@pytest.mark.parametrize(
    ("headers", "length"),
    [
        ({"content-range": "bytes 0-1/²"}, None),
        ({"content-range": "bytes 0-1/*", "content-length": "²"}, None),
        ({"content-range": "bytes 0-1/123"}, 123),
        ({"content-length": "456"}, 456),
        ({"content-length": "9" * 40}, None),
    ],
)
def test_lengths_only_from_ascii_digits(headers: dict[str, str], length: int | None) -> None:
    from earthx.discovery.propose import _length

    assert _length(headers) == length


@pytestmark_anyio
async def test_an_answer_no_rule_foresaw_is_unchecked_not_an_error() -> None:
    # A header the gateway passes on raw (a false Content-Encoding) or anything else: the file is unchecked.
    class Broken:
        async def head(self, *args: object, **kwargs: object) -> object:
            raise RuntimeError("decoding")

    found = await check_file(Broken(), "https://files.example.org/a.tif")  # type: ignore[arg-type]
    assert (found.outcome, found.reason) == ("unchecked", "error_runtimeerror")


@pytestmark_anyio
async def test_a_large_error_page_is_no_range_without_a_status() -> None:
    found = await _check(
        {"files.example.org/a.tif": lambda r: httpx.Response(405) if r.method == "HEAD" else httpx.Response(
            403, content=b"x" * 200_000)},
        "https://files.example.org/a.tif",
    )
    assert (found.outcome, found.reason, found.status) == ("failed", "no_range", None)


def test_a_key_clean_would_change_is_no_takeover() -> None:
    assert takeover_of("portal", ["id:amt@stadt.example.org"], ()) is None
    assert takeover_of("portal", ["id:" + "a" * 64, "doi:10.1/x"], ()).via == "doi"  # type: ignore[union-attr]


def test_the_probe_keeps_the_head_of_a_collection_too_large_otherwise() -> None:
    row = replace(_row("big", []), content={"id": "x", "title": "T", "summaries": {"s": "x" * 80_000}})
    text = probe_document(row, [], {"files": []})
    assert len(text.encode("utf-8")) <= MAX_PROBE_BYTES and json.loads(text)["collection"]["id"] == "x"


def test_a_candidate_file_has_its_own_head_and_keeps_binding_keys_verbatim() -> None:
    from earthx.discovery.propose import _comparable, dump_candidate

    document = {
        "source_id": "portal", "source_key": "k", "listed_id": "portal.k", "proposed_id": "relief",
        "takeover": {"via": "doi", "key": "doi:10.1/x?token=abc"},
        "harvested": {"title": "Relief\x85 Schweiz", "description": "Fragen an hans@amt.example.org"},
    }
    text = dump_candidate(document)
    assert text.startswith("# A candidate for a full entry") and "Approval" not in text
    assert "doi:10.1/x?token=abc" in text and "hans@" not in text
    # What YAML reads differently (U+0085) is compared as the file holds it: no change every run.
    assert _comparable(yaml.safe_load(text)) == _comparable(document)
