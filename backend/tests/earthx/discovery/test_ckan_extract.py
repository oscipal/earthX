"""A CKAN package becomes the intermediate form of a find (M5-19 plan §5, §6). Synthetic packages only (A5): one in the
shape of DCAT-AP.de with its fields among the extras, one with texts per language and a place name as extent."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from earthx.catalog.registry import Maturity
from earthx.catalog.sources import CkanFilter, SourceConfig, SourceProtocol
from earthx.discovery.ckan import CkanListing, ckan_pages, extract_package, package_key
from earthx.discovery.extract import Invalid, ShapeError, extracted_sha256, extractor_version
from earthx.discovery.links import LinkRank
from earthx.gateway import GatewayResponse

SOURCE = SourceConfig(
    source_id="example-ckan",
    protocol=SourceProtocol.CKAN,
    endpoint="https://ckan.example.org/api/3/action",
    catalog_page="https://portal.example.org/dataset/{name}",
    filter=CkanFilter(None, "publisher_name"),
    max_requests_per_run=20,
    max_pages_per_run=None,
    full_every_days=7,
    robots_exception=None,
    maturity=Maturity.STABLE,
    enabled=True,
)
BY_ORGANIZATION = replace(SOURCE, filter=CkanFilter(None, "organization"))

GEOMETRY = {"type": "Polygon", "coordinates": [[[8.9, 53.3], [11.3, 53.3], [11.3, 55.1], [8.9, 55.1], [8.9, 53.3]]]}

PACKAGE: dict[str, Any] = {
    "id": "0b8c6c1e-0000-4000-8000-000000000001",
    "name": "example-dgm1",
    "title": "Digitales Geländemodell 1 m",
    "notes": "Ein synthetisches Geländemodell.",
    "url": "https://geodaten.example.org/datensaetze/dgm1",
    "author": "Erika Mustermann",
    "author_email": "erika@example.org",
    "maintainer": "Max Mustermann",
    "maintainer_email": "max@example.org",
    "license_id": "dl-by-de/2.0",
    "license_url": "https://www.govdata.example/dl-de/by-2-0",
    "organization": {"name": "gdi-example", "title": "GDI Example (Lieferweg)"},
    "groups": [{"name": "envi", "title": "Umwelt"}],
    "tags": [{"name": "dgm", "display_name": "DGM"}, {"name": "opendata", "display_name": "opendata"}],
    "extras": [
        {"key": "publisher_name", "value": "Landesamt für Vermessung Example"},
        {"key": "spatial", "value": json.dumps(GEOMETRY)},
        {"key": "temporal_start", "value": "2020-01-01"},
        {"key": "temporal_end", "value": "2023-12-31"},
        {"key": "contact_name", "value": "Erika Mustermann"},
        {"key": "contact_email", "value": "erika@example.org"},
        {"key": "theme", "value": json.dumps(["http://inspire.ec.europa.eu/theme/el"])},
        {"key": "access_rights", "value": "http://publications.europa.eu/resource/authority/access-right/PUBLIC"},
    ],
    "resources": [
        {
            "url": "https://geodaten.example.org/download/dgm1.tif",
            "format": "http://publications.europa.eu/resource/authority/file-type/GEOTIFF",
            "name": "DGM1 GeoTIFF",
            "license": "http://dcat-ap.de/def/licenses/dl-by-de/2.0",
        },
        {
            "url": "https://geodaten.example.org/wms?SERVICE=WMS&REQUEST=GetCapabilities",
            "format": "WMS",
            "name": "Darstellungsdienst",
        },
        {
            "url": "https://geodaten.example.org/viewer/dgm1",
            "format": "HTML",
            "name": "Kartenviewer mit Download",
        },
        {
            "url": "https://geodaten.example.org/doku/dgm1.html",
            "format": "HTML",
            "name": "Dokumentation DGM1",
        },
    ],
}

MULTILINGUAL: dict[str, Any] = {
    "id": "c0ffee00-0000-4000-8000-000000000002",
    "name": "beispiel-gewaesser",
    "title": {"de": "Gewässernetz", "fr": "Réseau hydrographique", "it": "", "en": "River network"},
    "description": {"de": "Synthetisch.", "fr": "Synthétique.", "it": "", "en": ""},
    "url": "",
    "organization": {"name": "bafu", "title": '{"de": "Bundesamt für Beispiele", "fr": "Office fédéral des exemples"}'},
    "keywords": {"de": ["Gewässer", "Fluss"], "fr": ["eau"], "en": [], "it": []},
    "groups": [{"name": "geography", "title": {"de": "Raum", "fr": "Espace"}}],
    "spatial": "Schweiz",
    "temporals": [{"start_date": "2015-01-01T00:00:00", "end_date": None}],
    "contact_points": [{"name": "Jean Exemple", "email": "jean@example.org"}],
    "resources": [
        {
            "download_url": "https://data.example.org/gewaesser.gpkg",
            "url": "https://data.example.org/gewaesser",
            "format": "GPKG",
            "media_type": "application/geopackage+sqlite3",
            "title": {"de": "Gewässernetz GeoPackage", "fr": "Réseau GeoPackage"},
            "rights": "NonCommercialAllowed-CommercialAllowed-ReferenceRequired",
            "license": "https://opendata.example/terms_by",
        }
    ],
}


def _with(base: dict[str, Any], **changes: Any) -> dict[str, Any]:
    package = copy.deepcopy(base)
    package.update(changes)
    return package


def _resources(*resources: dict[str, Any], **changes: Any) -> dict[str, Any]:
    return _with(PACKAGE, resources=list(resources), **changes)


def test_the_fields_of_a_package_with_its_fields_among_the_extras() -> None:
    found = extract_package(PACKAGE["id"], PACKAGE, SOURCE)
    assert found.source_key == PACKAGE["id"]
    assert (found.title, found.description) == ("Digitales Geländemodell 1 m", "Ein synthetisches Geländemodell.")
    assert found.publisher == "Landesamt für Vermessung Example"
    assert found.licence_statements == (
        "dl-by-de/2.0",
        "https://www.govdata.example/dl-de/by-2-0",
        "http://dcat-ap.de/def/licenses/dl-by-de/2.0",
    )
    assert found.bbox == (8.9, 53.3, 11.3, 55.1) and found.geometry == GEOMETRY
    assert found.extent_known and found.spatial_text is None
    assert found.temporal == ("2020-01-01", "2023-12-31")
    assert (found.data_kind, found.delivery, found.account) == ("raster", "download", "none")
    assert found.category == "elevation"
    assert "dgm" in found.keywords and "opendata" not in found.keywords
    assert (found.source_url, found.source_rank) == ("https://geodaten.example.org/viewer/dgm1", 1)
    assert found.landing_url == "https://geodaten.example.org/datensaetze/dgm1"
    assert [(d.format, d.title) for d in found.distributions][0] == (
        "http://publications.europa.eu/resource/authority/file-type/GEOTIFF",
        "DGM1 GeoTIFF",
    )
    assert len(found.distributions) == 4


def test_a_package_with_texts_per_language_and_a_place_name() -> None:
    found = extract_package(MULTILINGUAL["id"], MULTILINGUAL, BY_ORGANIZATION)
    assert (found.title, found.description) == ("Gewässernetz", "Synthetisch.")
    assert found.publisher == "Bundesamt für Beispiele"
    assert found.keywords[:2] == ("gewässer", "fluss") and "eau" not in found.keywords
    assert (found.bbox, found.geometry, found.spatial_text, found.extent_known) == (None, None, "Schweiz", True)
    assert found.temporal == ("2015-01-01T00:00:00", None)
    assert (found.data_kind, found.delivery, found.account) == ("vector", "download", "none")
    assert found.licence_statements == (
        "https://opendata.example/terms_by",
        "NonCommercialAllowed-CommercialAllowed-ReferenceRequired",
    )
    # No viewer, no page at the provider (`url` empty): the page in the catalogue.
    assert (found.source_url, found.source_rank) == ("https://portal.example.org/dataset/beispiel-gewaesser", 3)
    assert found.distributions[0].href == "https://data.example.org/gewaesser.gpkg"


def test_no_person_reaches_the_intermediate_form() -> None:
    for package, source in ((PACKAGE, SOURCE), (MULTILINGUAL, BY_ORGANIZATION)):
        text = json.dumps(extract_package(package["id"], package, source).to_document(), ensure_ascii=False)
        assert not any(name in text for name in ("Mustermann", "Exemple", "@example.org"))


def test_the_publisher_field_is_a_setting_of_the_source() -> None:
    assert extract_package(PACKAGE["id"], PACKAGE, BY_ORGANIZATION).publisher == "GDI Example (Lieferweg)"
    on_package = _with(PACKAGE, publisher_name="Amt auf dem Paket")
    assert extract_package(PACKAGE["id"], on_package, SOURCE).publisher == "Amt auf dem Paket"
    assert extract_package(PACKAGE["id"], _with(PACKAGE, extras=[]), SOURCE).publisher is None
    assert extract_package(PACKAGE["id"], _with(PACKAGE, organization=None), BY_ORGANIZATION).publisher is None


def test_without_a_spatial_statement_the_find_stays_with_extent_unknown() -> None:
    # Otto, 17.11.2026: kept, marked; listing and filtering are M5-20's.
    found = extract_package(PACKAGE["id"], _with(PACKAGE, extras=[]), SOURCE)
    assert (found.bbox, found.spatial_text, found.extent_known) == (None, None, False)


@pytest.mark.parametrize(
    "spatial",
    [
        '{"type": "Polygon", "coordinates": [[[500, 0]]]}',
        '{"type": "Point", "coordinates": [1' + "0" * 400 + ', 1]}',
        '{"type": ["Point"], "coordinates": [7, 47]}',
        '{"type": {"a": 1}, "coordinates": [7, 47]}',
        "{broken",
        '{"type": "Point"}',
        "   ",
        "",
    ],
)
def test_a_broken_geometry_is_no_extent(spatial: str) -> None:
    package = _with(PACKAGE, extras=[{"key": "spatial", "value": spatial}])
    found = extract_package(PACKAGE["id"], package, SOURCE)
    assert (found.bbox, found.spatial_text, found.extent_known) == (None, None, False)


def test_a_geometry_wins_over_a_place_name() -> None:
    package = _with(PACKAGE, spatial="Schleswig-Holstein")
    found = extract_package(PACKAGE["id"], package, SOURCE)
    assert found.bbox is not None and found.spatial_text is None


@pytest.mark.parametrize("title", [None, "", "  ", {"de": "", "fr": None}, ["Titel"], 7])
def test_without_a_title_the_find_is_invalid(title: object) -> None:
    with pytest.raises(Invalid) as raised:
        extract_package(PACKAGE["id"], _with(PACKAGE, title=title), SOURCE)
    assert raised.value.reason == "no_title"


VIEWER = {"url": "https://geodaten.example.org/viewer/dgm1", "format": "HTML", "name": "Viewer"}
FILE = {"url": "https://geodaten.example.org/download/dgm1.tif", "format": "GeoTIFF", "name": "Datei"}
SERVICE = {"url": "https://geodaten.example.org/wms", "format": "WMS", "name": "WMS"}


@pytest.mark.parametrize(
    ("package", "expected"),
    [
        (_resources(VIEWER, FILE), ("https://geodaten.example.org/viewer/dgm1", LinkRank.VIEWER_OR_DOWNLOAD_PAGE)),
        (
            _resources({**VIEWER, "format": "", "mimetype": "text/html"}),
            ("https://geodaten.example.org/viewer/dgm1", LinkRank.VIEWER_OR_DOWNLOAD_PAGE),
        ),
        (
            _resources({**VIEWER, "access_url": "https://geodaten.example.org/viewer/dgm1?layer=a", "url": "x"}),
            ("https://geodaten.example.org/viewer/dgm1?layer=a", LinkRank.VIEWER_OR_DOWNLOAD_PAGE),
        ),
        # A page with a download address is a file in DCAT terms: no viewer.
        (
            _resources({**VIEWER, "download_url": "https://geodaten.example.org/dgm1.zip"}),
            ("https://geodaten.example.org/datensaetze/dgm1", LinkRank.DATASET_PAGE),
        ),
        (
            _resources({**VIEWER, "resource_type": "documentation"}),
            ("https://geodaten.example.org/datensaetze/dgm1", LinkRank.DATASET_PAGE),
        ),
        (
            _resources({**VIEWER, "name": "Metadaten zum Datensatz"}),
            ("https://geodaten.example.org/datensaetze/dgm1", LinkRank.DATASET_PAGE),
        ),
        (
            _resources({**VIEWER, "name": "Beschreibung"}),
            ("https://geodaten.example.org/datensaetze/dgm1", LinkRank.DATASET_PAGE),
        ),
        # A capabilities address given as HTML is still a service.
        (
            _resources({**VIEWER, "url": "https://geodaten.example.org/ows?service=WMS&request=GetCapabilities"}),
            ("https://geodaten.example.org/datensaetze/dgm1", LinkRank.DATASET_PAGE),
        ),
        (
            _resources({**VIEWER, "url": "http://geodaten.example.org/viewer/dgm1"}),
            ("https://geodaten.example.org/datensaetze/dgm1", LinkRank.DATASET_PAGE),
        ),
        (
            _resources(FILE, SERVICE, url="https://geodaten.example.org/de/"),
            ("https://portal.example.org/dataset/example-dgm1", LinkRank.CATALOGUE_PAGE),
        ),
        (
            _resources(FILE, SERVICE, url="https://192.0.2.1/datensatz"),
            ("https://portal.example.org/dataset/example-dgm1", LinkRank.CATALOGUE_PAGE),
        ),
        (
            _resources(url="javascript:alert(1)"),
            ("https://portal.example.org/dataset/example-dgm1", LinkRank.CATALOGUE_PAGE),
        ),
        # The page field of the package is no page when it names a file or a service.
        (
            _resources(url="https://geodaten.example.org/daten/dgm1.zip"),
            ("https://portal.example.org/dataset/example-dgm1", LinkRank.CATALOGUE_PAGE),
        ),
        (
            _resources(url="https://geodaten.example.org/wms?SERVICE=WMS&REQUEST=GetCapabilities"),
            ("https://portal.example.org/dataset/example-dgm1", LinkRank.CATALOGUE_PAGE),
        ),
        (
            _resources(url="https://geodaten.example.org/daten/dgm1.html"),
            ("https://geodaten.example.org/daten/dgm1.html", LinkRank.DATASET_PAGE),
        ),
        # An `http` access_url does not hide an `https` url of the same resource.
        (
            _resources({**VIEWER, "access_url": "http://geodaten.example.org/viewer/dgm1"}),
            ("https://geodaten.example.org/viewer/dgm1", LinkRank.VIEWER_OR_DOWNLOAD_PAGE),
        ),
    ],
)
def test_the_link_source_by_rank(package: dict[str, Any], expected: tuple[str, LinkRank]) -> None:
    found = extract_package(package["id"], package, SOURCE)
    assert (found.source_url, found.source_rank) == (expected[0], int(expected[1]))


@pytest.mark.parametrize("name", [None, "", "A", "Großbuchstaben", "../etc", "x" * 101, 5])
def test_without_a_usable_link_the_find_is_invalid(name: object) -> None:
    # Files and services are never the link "Source" (F1 = 1), and the catalogue page needs a proper name.
    package = _resources(FILE, SERVICE, url=None, name=name)
    with pytest.raises(Invalid) as raised:
        extract_package(package["id"], package, SOURCE)
    assert raised.value.reason == "no_link"


def test_without_a_catalogue_page_and_a_page_of_the_provider_the_find_is_invalid() -> None:
    package = _resources(FILE, url=None)
    with pytest.raises(Invalid):
        extract_package(package["id"], package, replace(SOURCE, catalog_page=None))


@pytest.mark.parametrize(
    ("resources", "kind", "delivery"),
    [
        ([FILE, SERVICE], "raster", "download"),
        ([SERVICE, {**FILE, "format": "PDF"}], "service", "download"),
        ([SERVICE], "service", "service"),
        ([{**FILE, "format": "CSV"}], "table", "download"),
        ([{**FILE, "format": "ZIP"}], "other", "download"),
        ([{**FILE, "format": "", "download_url": "https://geodaten.example.org/x"}], "other", "download"),
        ([{**FILE, "format": "Unknown"}], "other", None),
        ([VIEWER], "other", None),
        ([], "other", None),
    ],
)
def test_data_kind_and_delivery(resources: list[dict[str, Any]], kind: str, delivery: str | None) -> None:
    found = extract_package(PACKAGE["id"], _resources(*resources, extras=[]), SOURCE)
    assert (found.data_kind, found.delivery) == (kind, delivery)


@pytest.mark.parametrize(
    ("access_rights", "resources", "account"),
    [
        ("http://publications.europa.eu/resource/authority/access-right/PUBLIC", [], "none"),
        ("public", [FILE], "none"),
        ("http://publications.europa.eu/resource/authority/access-right/RESTRICTED", [FILE], None),
        ("NON_PUBLIC", [FILE], None),
        ("nur nach Vereinbarung", [FILE], None),
        (None, [FILE], "none"),
        (None, [SERVICE], "none"),
        (None, [VIEWER], None),
    ],
)
def test_the_account(access_rights: str | None, resources: list[dict[str, Any]], account: str | None) -> None:
    extras = [] if access_rights is None else [{"key": "access_rights", "value": access_rights}]
    found = extract_package(PACKAGE["id"], _resources(*resources, extras=extras), SOURCE)
    assert found.account == account


@pytest.mark.parametrize(
    ("doi", "expected"),
    [
        ("10.5281/zenodo.123", "10.5281/zenodo.123"),
        ("https://doi.org/10.5281/zenodo.123", "10.5281/zenodo.123"),
        ("doi:10.1594/PANGAEA.1", "10.1594/PANGAEA.1"),
        ("not a doi", None),
        ("http://doi.org/10.5281/x", None),
    ],
)
def test_a_doi(doi: str, expected: str | None) -> None:
    assert extract_package(PACKAGE["id"], _with(PACKAGE, doi=doi), SOURCE).doi == expected


def test_a_group_named_after_an_eu_data_theme_counts_as_that_theme() -> None:
    package = _with(PACKAGE, extras=[], tags=[], groups=[{"name": "tran", "title": "Verkehr"}])
    assert extract_package(PACKAGE["id"], package, SOURCE).category == "infrastructure"


def test_licence_statements_are_kept_verbatim_and_once() -> None:
    package = _resources(
        {**FILE, "license": "dl-by-de/2.0"}, {**SERVICE, "license": "Nutzung nur mit Quellenvermerk"}, extras=[]
    )
    assert extract_package(PACKAGE["id"], package, SOURCE).licence_statements == (
        "dl-by-de/2.0",
        "https://www.govdata.example/dl-de/by-2-0",
        "Nutzung nur mit Quellenvermerk",
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"extras": "not a list"},
        {"extras": [{"value": "no key"}, "text", {"key": 5}]},
        {"resources": "not a list"},
        {"resources": ["text", 5, None]},
        {"tags": [5, None, {"name": 7}]},
        {"groups": "envi"},
        {"keywords": {"de": "not a list"}},
        {"temporals": ["2020"]},
        {"organization": "text"},
        {"title": "T\x00itel\ud800"},
    ],
)
def test_parts_of_a_foreign_shape_are_left_out(changes: dict[str, Any]) -> None:
    found = extract_package(PACKAGE["id"], _with(PACKAGE, **changes), SOURCE)
    assert found.title and extracted_sha256(found)


def test_a_package_key() -> None:
    assert package_key(PACKAGE) == PACKAGE["id"]
    assert package_key({"id": "../x"}) is None
    assert package_key({"id": 5}) is None
    assert package_key("text") is None


def test_the_extractor_version_follows_the_settings_of_the_source() -> None:
    assert extractor_version(SOURCE) == extractor_version(SOURCE)
    assert extractor_version(SOURCE) != extractor_version(BY_ORGANIZATION)
    assert extractor_version(SOURCE) != extractor_version(replace(SOURCE, catalog_page=None))
    stac = replace(SOURCE, protocol=SourceProtocol.STAC_API, catalog_page=None)
    assert extractor_version(stac) != extractor_version(replace(SOURCE, catalog_page=None))


@pytest.mark.anyio
async def test_an_incremental_query_is_asked_in_utc() -> None:
    asked: list[Mapping[str, Any]] = []

    async def fetch(url: str, *, params: Mapping[str, Any], headers: None = None) -> GatewayResponse:
        asked.append(params)
        body = {"success": True, "result": {"count": 0, "results": []}}
        return GatewayResponse(200, {}, json.dumps(body).encode())

    since = datetime(2026, 11, 17, 10, 30, tzinfo=timezone(timedelta(hours=1)))
    listing = CkanListing(full=False)
    assert [page async for page in ckan_pages(fetch, SOURCE, since, listing)] == [[]]
    assert asked == [{"rows": 100, "start": 0, "sort": "id asc", "fq": "metadata_modified:[2026-11-17T09:30:00Z TO *]"}]
    assert not listing.complete and not listing.moved


@pytest.mark.anyio
@pytest.mark.parametrize("status", [204, 304])
async def test_a_listing_without_a_page_fails(status: int) -> None:
    async def fetch(url: str, *, params: Mapping[str, Any], headers: None = None) -> GatewayResponse:
        return GatewayResponse(status, {}, b"")

    with pytest.raises(ShapeError):
        [page async for page in ckan_pages(fetch, SOURCE, None, CkanListing(full=True))]
