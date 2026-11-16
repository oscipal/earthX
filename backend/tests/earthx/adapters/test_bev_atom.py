"""T-A/T-B: `adapters.bev_atom` against mocked ATOM feeds (M5-09 plan §4.1, §4.7).

The feeds are synthetic, built in the shape Otto's probe measured (plan §2.4): a service feed with one entry per model,
tile and reference date plus series entries, and one dataset feed per tile with exactly one file. Tile names, DOIs
and dates are made up. Everything goes through `gateway` with a mock transport.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from pyproj import Transformer

from earthx.adapters import (
    ADAPTER_SPECS,
    NotMaterialized,
    UnsupportedSource,
    UpstreamShapeError,
    bev_atom,
    materialize_items,
)
from earthx.adapters.cop_dem_bucket import COG_MEDIA_TYPE
from earthx.catalog.registry import ItemHolding, SpatialExtent
from earthx.gateway import Policy
from earthx.gateway.client import Gateway
from earthx.gateway.errors import UpstreamError
from tests.catalog.entries import REGISTRY

pytestmark = pytest.mark.anyio

BEV = REGISTRY.get("bev-als-dgm")
HOST = "data.bev.gv.at"
POLICY = Policy(allowed_hosts=frozenset({HOST}))
SERVICE_PATH = "/geonetwork/srv/atom/describe/service"
ATOM = (
    'xmlns="http://www.w3.org/2005/Atom" xmlns:georss="http://www.georss.org/georss" '
    'xmlns:inspire_dls="http://inspire.ec.europa.eu/schemas/inspire_dls/1.0"'
)
#: Made-up cells of the 50 km grid in EPSG:3035 inside the extent of the entry: (northing, easting) of the lower left.
CELLS = [(2650000, 4800000), (2700000, 4700000), (2600000, 4650000)]
NEWEST, OLDER = (15, 9, 2025), (15, 9, 2024)


def tile(cell: tuple[int, int]) -> str:
    return f"CRS3035RES50000mN{cell[0]}E{cell[1]}"


def stamp(day: tuple[int, int, int]) -> str:
    return f"{day[2]}{day[1]:02d}{day[0]:02d}"


def code(cell: tuple[int, int], day: tuple[int, int, int], model: str = "DTM") -> str:
    """A made-up DOI in the measured form, one per model, tile and date."""
    north, east, number = cell[0] // 50000, cell[1] // 50000, 1 if model == "DTM" else 2
    return f"https://doi.org/10.48677/{north:08x}-{east:04x}-4{day[2] % 4096:03x}-8{number:03x}-000000000000"


def file_url(cell: tuple[int, int], day: tuple[int, int, int], model: str = "DTM") -> str:
    return f"https://{HOST}/download/ALS/{model}/{stamp(day)}/ALS_{model}_{tile(cell)}.tif"


def feed_url(cell: tuple[int, int], day: tuple[int, int, int], model: str = "DTM") -> str:
    return f"https://{HOST}/geonetwork/srv/atom/describe/dataset?model={model}&tile={tile(cell)}&day={stamp(day)}"


def entry(
    cell: tuple[int, int],
    day: tuple[int, int, int],
    model: str = "DTM",
    *,
    title: str | None = None,
    doi: str | None = None,
    updated: str = "2025-10-01T08:00:00.000000ZZ",
) -> str:
    title = title or f"ALS {model} {tile(cell)} Höhenraster 1m Stichtag {day[0]:02d}.{day[1]:02d}.{day[2]}"
    link = feed_url(cell, day, model).replace("&", "&amp;")
    return (
        f"<entry><title>{title}</title><author><name>BEV</name></author><id>{link}</id>"
        "<rights>Der öffentliche Zugang zu diesem Produkt unterliegt keinen Einschränkungen.</rights>"
        f"<summary>s</summary><updated>{updated}</updated>"
        '<category term="http://www.opengis.net/def/crs/EPSG/0/3035"/>'
        "<inspire_dls:spatial_dataset_identifier_code>"
        f"{doi if doi is not None else code(cell, day, model)}"
        "</inspire_dls:spatial_dataset_identifier_code>"
        f'<link rel="alternate" type="application/atom+xml" href="{link}"/>'
        f'<link rel="describedby" type="application/xml" href="https://{HOST}/geonetwork/records/x"/>'
        "<georss:polygon>47 13 47 14 48 14 48 13 47 13</georss:polygon></entry>"
    )


SERIES = "".join(
    f"<entry><title>Serie ALS {model} Höhenraster 1m Stichtag 15.09.{year}</title></entry>"
    for model in ("DTM", "DSM")
    for year in (2024, 2025)
)


def service(*entries: str) -> bytes:
    return f"<feed {ATOM}><title>t</title><updated>x</updated>{SERIES}{''.join(entries)}</feed>".encode()


def standard(cells=CELLS) -> bytes:
    """Both models at two dates, as the source lists them."""
    return service(*(entry(c, d, m) for m in ("DTM", "DSM") for d in (OLDER, NEWEST) for c in cells))


def dataset_feed(*hrefs: str, entries: int = 1) -> bytes:
    links = "".join(f'<link rel="alternate" type="image/tiff" href="{h}"/>' for h in hrefs)
    body = "".join(f"<entry><title>f</title>{links}</entry>" for _ in range(entries))
    return f"<feed {ATOM}>{body}</feed>".encode()


def source(service_body: bytes, files: dict[str, bytes | int] | None = None):
    """A gateway answering the service feed and dataset feeds; ``files`` overrides the feed of a tile URL."""
    seen: list[httpx.Request] = []
    files = files or {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == SERVICE_PATH:
            return httpx.Response(200, content=service_body)
        if request.url.path == "/geonetwork/srv/atom/describe/dataset":
            # The gateway connects to the checked address, so the URL of the request names it, not the host.
            key = f"https://{HOST}{request.url.raw_path.decode()}"
            if key in files:
                answer = files[key]
                return httpx.Response(answer) if isinstance(answer, int) else httpx.Response(200, content=answer)
            params = request.url.params
            model, name, day = params["model"], params["tile"], params["day"]
            return httpx.Response(
                200, content=dataset_feed(f"https://{HOST}/download/ALS/{model}/{day}/ALS_{model}_{name}.tif")
            )
        return httpx.Response(404)

    async def sleep(seconds: float) -> None:
        return None

    return Gateway(POLICY, transport=httpx.MockTransport(handler), resolve=_public, sleep=sleep), seen


def _public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


async def _run(gateway, config=BEV, known_version=None):
    return await materialize_items(config, adapters=ADAPTER_SPECS, gateway=gateway, known_version=known_version)


class TestNormalRun:
    async def test_every_tile_of_the_newest_date_becomes_an_item(self) -> None:
        gateway, seen = source(standard())
        outcome = await _run(gateway)
        assert outcome.status == "loaded"
        assert outcome.source_version.startswith("sha256:")
        # Three tiles of 2025; the three of 2024 are withheld; DSM and series entries are not counted.
        assert (outcome.listed, outcome.in_bucket, outcome.missing, outcome.withheld, outcome.unknown) == (
            3,
            3,
            0,
            3,
            0,
        )
        item = next(i for i in outcome.items if i["id"] == f"ALS_DTM_20250915_{tile(CELLS[0])}")
        assert item["collection"] == "bev-als-dgm"
        assert item["properties"] == {
            "datetime": "2025-09-15T00:00:00Z",
            "gsd": 1.0,
            "proj:code": "EPSG:3035",
            "sci:doi": code(CELLS[0], NEWEST).removeprefix("https://doi.org/"),
        }
        assert item["assets"] == {
            "dtm": {"href": file_url(CELLS[0], NEWEST), "type": COG_MEDIA_TYPE, "roles": ["data"]}
        }
        # The service feed, then one dataset feed per tile of the newest date, nothing else; no file is opened.
        assert len(seen) == 1 + len(CELLS)
        assert all("download" not in r.url.path for r in seen)

    async def test_the_footprint_is_the_cell_of_the_name_not_the_polygon_of_the_feed(self) -> None:
        gateway, _ = source(standard())
        item = next(i for i in (await _run(gateway)).items if i["id"].endswith(tile(CELLS[0])))
        to_wgs84 = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True)
        north, east = CELLS[0]
        for x, y in ((east, north), (east + 50000, north), (east + 50000, north + 50000), (east, north + 50000)):
            lon, lat = to_wgs84.transform(x, y)
            assert [round(lon, 7), round(lat, 7)] in item["geometry"]["coordinates"][0]
        ring = item["geometry"]["coordinates"][0]
        assert ring[0] == ring[-1]
        assert len(ring) == 4 * bev_atom.EDGE_POINTS + 1
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        assert item["bbox"] == [min(xs), min(ys), max(xs), max(ys)]

    async def test_an_unchanged_feed_builds_nothing_after_one_request(self) -> None:
        first, _ = source(standard())
        version = (await _run(first)).source_version
        gateway, seen = source(standard())
        outcome = await _run(gateway, known_version=version)
        assert (outcome.status, outcome.items, outcome.source_version) == ("unchanged", (), version)
        assert len(seen) == 1

    @pytest.mark.parametrize(
        "changed",
        [
            entry(CELLS[0], NEWEST, updated="2026-01-01T00:00:00.000000ZZ"),
            entry(CELLS[0], NEWEST, doi=code(CELLS[1], OLDER)),
        ],
    )
    async def test_a_changed_entry_of_the_newest_date_changes_the_version(self, changed: str) -> None:
        first, _ = source(standard())
        version = (await _run(first)).source_version
        others = [entry(c, NEWEST) for c in CELLS[1:]]
        gateway, _ = source(service(changed, *others))
        outcome = await _run(gateway, known_version=version)
        assert outcome.status == "loaded"
        assert outcome.source_version != version

    async def test_a_change_at_an_older_date_or_the_dsm_keeps_the_version(self) -> None:
        first, _ = source(standard())
        version = (await _run(first)).source_version
        body = service(
            *(entry(c, NEWEST) for c in CELLS),
            entry(CELLS[0], OLDER, updated="2026-01-01T00:00:00.000000ZZ"),
            entry(CELLS[0], NEWEST, "DSM", updated="2026-01-01T00:00:00.000000ZZ"),
        )
        gateway, _ = source(body)
        assert (await _run(gateway, known_version=version)).status == "unchanged"


class TestWhatIsNotLoaded:
    async def test_a_title_of_another_form_is_unknown(self) -> None:
        odd = entry(CELLS[0], NEWEST, title="ALS DTM Kachel neu").encode()
        gateway, _ = source(standard().replace(b"</feed>", odd + b"</feed>"))
        outcome = await _run(gateway)
        assert (outcome.unknown, len(outcome.items)) == (1, 3)

    async def test_a_newest_date_after_the_entry_stops_the_run(self) -> None:
        gateway, _ = source(service(*(entry(c, d) for d in (NEWEST, (15, 9, 2026)) for c in CELLS)))
        with pytest.raises(UnsupportedSource, match="newest reference date 2026-09-15"):
            await _run(gateway)

    async def test_a_newest_date_before_the_entry_stops_the_run(self) -> None:
        gateway, _ = source(service(*(entry(c, OLDER) for c in CELLS)))
        with pytest.raises(UnsupportedSource, match="outside temporal_extent"):
            await _run(gateway)

    async def test_a_tile_listed_twice_for_one_date_fails_the_run(self) -> None:
        gateway, _ = source(service(*(entry(c, NEWEST) for c in CELLS), entry(CELLS[0], NEWEST)))
        with pytest.raises(UpstreamShapeError, match="twice"):
            await _run(gateway)

    async def test_a_feed_without_a_tile_of_the_model_fails_the_run(self) -> None:
        gateway, _ = source(service(*(entry(c, NEWEST, "DSM") for c in CELLS)))
        with pytest.raises(UpstreamShapeError, match="no tile of ALS DTM"):
            await _run(gateway)

    @pytest.mark.parametrize(
        "answer",
        [
            dataset_feed(),
            dataset_feed(file_url(CELLS[0], NEWEST), file_url(CELLS[0], NEWEST)),
            dataset_feed(file_url(CELLS[0], NEWEST), entries=2),
            dataset_feed(file_url(CELLS[0], NEWEST).replace(HOST, "elsewhere.example.org")),
            dataset_feed(file_url(CELLS[0], NEWEST).replace("https://", "http://")),
            dataset_feed(file_url(CELLS[0], NEWEST) + "?x=1"),
            dataset_feed(file_url(CELLS[1], NEWEST)),
            dataset_feed(file_url(CELLS[0], OLDER)),
            dataset_feed(file_url(CELLS[0], NEWEST, "DSM")),
            404,
        ],
        ids=[
            "no file",
            "two files",
            "two entries",
            "other host",
            "http",
            "query",
            "other tile",
            "other date",
            "dsm",
            "404",
        ],
    )
    async def test_one_tile_without_its_one_file_aborts_a_small_run(self, answer: bytes | int) -> None:
        gateway, _ = source(standard(), {feed_url(CELLS[0], NEWEST): answer})
        with pytest.raises(UpstreamShapeError, match="1 of 3 tiles of 2025-09-15 are not loadable"):
            await _run(gateway)

    async def test_a_tile_without_its_file_is_counted_below_the_threshold(self) -> None:
        cells = [(2_000_000 + 50_000 * row, 4_000_000 + 50_000 * column) for row in range(11) for column in range(11)]
        wide = replace(BEV, spatial_extent=SpatialExtent(bbox=(-10.0, 30.0, 40.0, 70.0)))
        gateway, _ = source(service(*(entry(c, NEWEST) for c in cells)), {feed_url(cells[0], NEWEST): 404})
        outcome = await _run(gateway, wide)
        assert (outcome.listed, outcome.in_bucket, outcome.missing) == (121, 120, 1)

    async def test_a_tile_outside_the_extent_is_unknown(self) -> None:
        outside = (2_000_000, 3_000_000)
        cells = [*CELLS, outside]
        gateway, _ = source(service(*(entry(c, NEWEST) for c in cells)))
        with pytest.raises(UpstreamShapeError, match="1 of 4 tiles"):
            await _run(gateway)

    @pytest.mark.parametrize("doi", ["", "10.48677/abc", "https://doi.org/10.48677/NOT-A-UUID"])
    async def test_an_entry_without_a_doi_of_the_known_form_is_not_loadable(self, doi: str) -> None:
        body = service(entry(CELLS[0], NEWEST, doi=doi), *(entry(c, NEWEST) for c in CELLS[1:]))
        gateway, _ = source(body)
        with pytest.raises(UpstreamShapeError, match="not loadable"):
            await _run(gateway)

    async def test_a_server_error_of_a_dataset_feed_is_not_counted_as_missing(self) -> None:
        gateway, _ = source(standard(), {feed_url(CELLS[0], NEWEST): 503})
        with pytest.raises(UpstreamError) as caught:
            await _run(gateway)
        assert caught.value.status_code == 503


class TestBrokenFeeds:
    @pytest.mark.parametrize(
        "body",
        [
            b"not xml",
            b'<?xml version="1.0"?><!DOCTYPE f [<!ENTITY e "x">]><feed>&e;</feed>',
        ],
        ids=["not xml", "entity"],
    )
    async def test_a_service_feed_that_is_no_safe_xml_fails_the_run(self, body: bytes) -> None:
        gateway, _ = source(body)
        with pytest.raises(UpstreamShapeError, match="service feed is not valid XML"):
            await _run(gateway)

    async def test_a_dataset_feed_that_is_no_xml_fails_the_run(self) -> None:
        gateway, _ = source(standard(), {feed_url(CELLS[0], NEWEST): b"<feed"})
        with pytest.raises(UpstreamShapeError, match="dataset feed is not valid XML"):
            await _run(gateway)


class TestRegistryErrors:
    async def test_a_federated_entry_is_refused_before_any_request(self) -> None:
        """The registry forbids the pairing itself; the adapter refuses it all the same."""
        config = SimpleNamespace(dataset_id="x", source=SimpleNamespace(item_holding=ItemHolding.FEDERATED))
        gateway, seen = source(standard())
        with pytest.raises(NotMaterialized):
            await bev_atom.materialize_items(config, gateway=gateway, known_version=None)
        assert seen == []

    async def test_an_unknown_model_is_refused(self) -> None:
        other = replace(BEV, source=replace(BEV.source, source_collection_id="ALS DOP"))
        with pytest.raises(UnsupportedSource, match="ALS DTM"):
            await _run(source(standard())[0], other)

    async def test_the_dsm_reads_its_own_tiles(self) -> None:
        dsm = replace(BEV, source=replace(BEV.source, source_collection_id="ALS DSM"))
        outcome = await _run(source(standard())[0], dsm)
        assert {i["id"] for i in outcome.items} == {f"ALS_DSM_20250915_{tile(c)}" for c in CELLS}
