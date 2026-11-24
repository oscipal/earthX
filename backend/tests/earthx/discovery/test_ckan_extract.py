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
from earthx.discovery.ckan import (
    CkanListing,
    ckan_pages,
    extract_package,
    link_reasons,
    package_key,
    search_params,
    stable_package,
)
from earthx.discovery.extract import Invalid, ShapeError, extracted_sha256, extractor_version, theme_codes
from earthx.discovery.links import LinkRank, address_key
from earthx.gateway import GatewayResponse

SOURCE = SourceConfig(
    source_id="example-ckan",
    protocol=SourceProtocol.CKAN,
    endpoint="https://ckan.example.org/api/3/action",
    catalog_page="https://portal.example.org/dataset/{name}",
    filter=CkanFilter(None, "publisher_name"),
    max_requests_per_run=20,
    max_pages_per_run=None,
    rows_per_page=None,
    full_every_days=7,
    robots_exception=None,
    maturity=Maturity.STABLE,
    enabled=True,
    country=None,
    dedupe_rank=1,
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
        # Only pages or unknown formats at an https address: through the provider's page (F12 = 2, Otto 20.11.2026).
        ([{**FILE, "format": "Unknown"}], "other", "page"),
        ([{**FILE, "format": "SERVICE"}], "other", "page"),
        ([{**FILE, "format": "API"}], "other", "page"),
        ([{**FILE, "format": "onLine"}], "other", "page"),
        ([VIEWER], "other", "page"),
        # A plain http address is none, nor is documentation alone.
        ([{**VIEWER, "url": "http://geodaten.example.org/viewer"}], "other", None),
        ([{**VIEWER, "resource_type": "documentation"}], "other", None),
        ([], "other", None),
    ],
)
def test_data_kind_and_delivery(resources: list[dict[str, Any]], kind: str, delivery: str | None) -> None:
    found = extract_package(PACKAGE["id"], _resources(*resources, extras=[]), SOURCE)
    assert (found.data_kind, found.delivery) == (kind, delivery)


@pytest.mark.parametrize(
    ("access_rights", "resources", "account"),
    [
        # Public, but nothing to get the data from: no way to it.
        ("http://publications.europa.eu/resource/authority/access-right/PUBLIC", [], None),
        ("public", [FILE], "none"),
        ("http://publications.europa.eu/resource/authority/access-right/RESTRICTED", [FILE], None),
        ("NON_PUBLIC", [FILE], None),
        ("http://publications.europa.eu/resource/authority/access-right/NON_PUBLIC", [VIEWER], None),
        # F12 = 1 (Otto, 20.11.2026): only a statement that the data are not public holds a find back; a missing or
        # other one does not (a free text is not read).
        ("nur nach Vereinbarung", [FILE], "none"),
        ("http://inspire.ec.europa.eu/metadata-codelist/LimitationsOnPublicAccess/noLimitations", [FILE], "none"),
        (None, [FILE], "none"),
        (None, [SERVICE], "none"),
        (None, [VIEWER], "none"),
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


@pytest.mark.parametrize("text", ["null", "NULL", " Null "])
def test_a_place_text_null_is_no_place(text: str) -> None:
    # Otto, 19.11.2026: the 24 place texts of GovData are the string "null".
    found = extract_package(PACKAGE["id"], _with(PACKAGE, extras=[{"key": "spatial", "value": text}]), SOURCE)
    assert (found.spatial_text, found.extent_known) == (None, False)


def test_themes_are_kept_as_codes_for_the_geodata_rule() -> None:
    # M5-20 A12: INSPIRE and EU data themes, from theme URIs and from groups named after an EU theme.
    package = _with(PACKAGE, groups=[{"name": "gove", "title": "Regierung"}])
    assert extract_package(PACKAGE["id"], package, SOURCE).themes == ("eu:GOVE", "inspire:el")
    econ = "http://publications.europa.eu/resource/authority/data-theme/ECON"
    package = _with(PACKAGE, groups=[], extras=[{"key": "theme", "value": econ}])
    assert extract_package(PACKAGE["id"], package, SOURCE).themes == ("eu:ECON",)


def test_theme_codes_drop_what_is_no_code() -> None:
    assert theme_codes(["EL", "x1"], ["http://x/data-theme/ENVI/", "Umwelt und Natur", "TRAN"]) == (
        "eu:ENVI",
        "eu:TRAN",
        "inspire:el",
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [("https://registry.example.org/ds/42", "https://registry.example.org/ds/42"), ("   ", None), ("x" * 301, None)],
)
def test_the_identifier(value: str, expected: str | None) -> None:
    package = _with(PACKAGE, identifier=value)
    assert extract_package(PACKAGE["id"], package, SOURCE).identifier == expected


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
    assert not listing.complete and listing.empty


@pytest.mark.anyio
@pytest.mark.parametrize("status", [204, 304])
async def test_a_listing_without_a_page_fails(status: int) -> None:
    async def fetch(url: str, *, params: Mapping[str, Any], headers: None = None) -> GatewayResponse:
        return GatewayResponse(status, {}, b"")

    with pytest.raises(ShapeError):
        [page async for page in ckan_pages(fetch, SOURCE, None, CkanListing(full=True))]


def _listing_page(keys: list[str | None], count: int) -> GatewayResponse:
    results = [{"id": key, "title": "x"} if key is not None else {"title": "no id"} for key in keys]
    return GatewayResponse(200, {}, json.dumps({"success": True, "result": {"count": count, "results": results}}).encode())


@pytest.mark.anyio
async def test_each_page_is_asked_from_the_start_after_the_last_key() -> None:
    # Keyset paging (Otto, 19.11.2026): opendata.swiss answers 429 to deep offsets, so no offset grows.
    answers = [_listing_page(["a-1", "b-2"], 3), _listing_page(["c-3"], 1)]
    asked: list[Mapping[str, Any]] = []

    async def fetch(url: str, *, params: Mapping[str, Any], headers: None = None) -> GatewayResponse:
        asked.append(params)
        return answers.pop(0)

    listing = CkanListing(full=True)
    pages = [page async for page in ckan_pages(fetch, SOURCE, None, listing)]
    assert [len(page) for page in pages] == [2, 1]
    assert [(p["start"], p.get("fq")) for p in asked] == [(0, None), (0, 'id:{"b-2" TO *]')]
    assert (listing.last_key, listing.read, listing.complete, listing.empty) == ("c-3", 3, True, False)


@pytest.mark.anyio
async def test_a_resumed_listing_asks_after_its_key_with_the_filters_of_the_source() -> None:
    asked: list[Mapping[str, Any]] = []

    async def fetch(url: str, *, params: Mapping[str, Any], headers: None = None) -> GatewayResponse:
        asked.append(params)
        return _listing_page([], 0)

    filtered = replace(SOURCE, filter=CkanFilter("res_format:CSV", "publisher_name"))
    since = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
    listing = CkanListing(full=False, last_key="b-2", read=7)
    [page async for page in ckan_pages(fetch, filtered, since, listing)]
    assert asked[0]["fq"] == '(res_format:CSV) AND metadata_modified:[2026-11-18T12:00:00Z TO *] AND id:{"b-2" TO *]'
    # Nothing new after the key: the pass is through, with what it read before.
    assert (listing.read, listing.empty, listing.last_key) == (7, False, "b-2")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("keys", "count", "last_key"),
    [
        (["b-2", "a-1"], 5, None),  # not sorted by id
        (["a-1", "c-3"], 5, "b-2"),  # an id at or before the last key: the filter is ignored
        (["b-2"], 5, "b-2"),
        ([None, None], 5, None),  # nothing to go on from
    ],
)
async def test_a_listing_that_breaks_the_order_by_key_fails(keys: list[str | None], count: int, last_key: str | None) -> None:
    async def fetch(url: str, *, params: Mapping[str, Any], headers: None = None) -> GatewayResponse:
        return _listing_page(keys, count)

    with pytest.raises(ShapeError):
        [page async for page in ckan_pages(fetch, SOURCE, None, CkanListing(full=True, last_key=last_key))]


def test_a_page_asks_the_rows_of_its_source() -> None:
    assert search_params(replace(SOURCE, rows_per_page=50), None, None)["rows"] == 50
    assert search_params(SOURCE, None, None)["rows"] == 100


def test_the_bookkeeping_of_ckan_is_left_out_of_the_stable_package() -> None:
    package = {
        "id": "a",
        "metadata_modified": "2026-11-19T10:00:00",
        "revision_id": "r1",
        "title": "T",
        "resources": [{"url": "u", "metadata_modified": "x", "cache_last_updated": "y", "last_modified": "z"}],
    }
    assert stable_package(package) == {"id": "a", "title": "T", "resources": [{"url": "u", "last_modified": "z"}]}
    assert package["metadata_modified"] and stable_package("text") == "text"


RESOURCE_ID = "6f1c2e4a-1b2c-4d3e-8f90-0123456789ab"


@pytest.mark.parametrize(
    "url",
    [
        f"https://opendata.example.org/de/dataset/example-dgm1/resource/{RESOURCE_ID}",
        f"https://ckan.example.org/dataset/x/resource/{RESOURCE_ID.upper()}?lang=de",
        f"https://geodaten.example.org/viewer?id={RESOURCE_ID}",
    ],
)
def test_a_page_made_of_the_resource_id_is_no_stable_link(url: str) -> None:
    # Otto, 19.11.2026: a portal that re-creates its resources changes their ids, and with them such a page.
    package = _resources({**VIEWER, "id": RESOURCE_ID, "url": url})
    found = extract_package(package["id"], package, SOURCE)
    assert (found.source_url, found.source_rank) == ("https://geodaten.example.org/datensaetze/dgm1", 2)


def test_a_resource_page_of_another_resource_counts_as_made_of_an_id() -> None:
    url = "https://opendata.example.org/dataset/x/resource/0b8c6c1e-0000-4000-8000-000000000001"
    found = extract_package(PACKAGE["id"], _resources({**VIEWER, "url": url}), SOURCE)
    assert found.source_rank == 2


def test_several_viewers_give_the_same_link_in_any_order() -> None:
    first = {**VIEWER, "url": "https://geodaten.example.org/viewer/a"}
    second = {**VIEWER, "url": "https://geodaten.example.org/viewer/b"}
    one = extract_package(PACKAGE["id"], _resources(second, first), SOURCE)
    two = extract_package(PACKAGE["id"], _resources(first, second), SOURCE)
    assert one.source_url == two.source_url == "https://geodaten.example.org/viewer/a"


def test_new_resource_ids_leave_the_link_as_it_is() -> None:
    before = _resources({**VIEWER, "id": "aaaaaaaa-0000-4000-8000-000000000001"}, {**FILE, "id": "x1"})
    after = _resources({**FILE, "id": "x2"}, {**VIEWER, "id": "bbbbbbbb-0000-4000-8000-000000000002"})
    assert extract_package("k", before, SOURCE).source_url == extract_package("k", after, SOURCE).source_url


def test_why_a_package_reaches_only_the_catalogue_page() -> None:
    # Otto, 19.11.2026: GovData reaches rank 3 for 82 % of its finds; --explain-links names the reasons.
    package = {
        "id": "k",
        "name": "x",
        "url": "http://amt.example.org/daten/x",
        "landingPage": "https://amt.example.org/daten/x",
        "maintainer_email": "max@example.org",
        "contact_uri": "https://people.example.org/max",
        "extras": [
            {"key": "dcat_landing_page", "value": "https://amt.example.org/daten/x"},
            {"key": "contact_url", "value": "https://people.example.org/max"},
        ],
        "resources": [
            {"id": "r1", "url": "https://amt.example.org/viewer", "format": "HTML", "download_url": "https://amt.example.org/x.zip"},
            {"id": "r2", "url": "https://amt.example.org/dl/x"},
        ],
    }
    reasons = dict(link_reasons(package, SOURCE))
    assert reasons["url_http"] == "http://amt.example.org/daten/x"
    assert reasons["html_with_download"] == "https://amt.example.org/x.zip"
    assert reasons["resource_without_format"] == "https://amt.example.org/dl/x"
    assert reasons["field:landingPage"] == reasons["extras:dcat_landing_page"] == "https://amt.example.org/daten/x"
    # Person fields are never named, whatever they hold.
    assert not any("people" in (value or "") or "contact" in code or "maintainer" in code for code, value in reasons.items())


@pytest.mark.parametrize(
    ("url", "code"),
    [
        (None, "url_empty"),
        ("https://amt.example.org/", "url_start_page"),
        ("https://amt.example.org/x.zip", "url_file"),
        ("https://amt.example.org/wms?SERVICE=WMS&REQUEST=GetCapabilities", "url_service"),
    ],
)
def test_the_reason_why_the_page_field_is_no_link(url: str | None, code: str) -> None:
    assert code in dict(link_reasons({"id": "k", "url": url, "resources": []}, SOURCE))


def test_a_package_without_resources_and_without_html() -> None:
    assert "no_resources" in dict(link_reasons({"id": "k", "resources": []}, SOURCE))
    only_files = {"id": "k", "resources": [{"url": "https://amt.example.org/x.csv", "format": "CSV"}]}
    assert "no_html_resource" in dict(link_reasons(only_files, SOURCE))


GOVDATA_LIKE = replace(SOURCE, filter=CkanFilter(None, "publisher_name", ("uri", "guid")))


@pytest.mark.parametrize(
    ("extras", "expected"),
    [
        ([{"key": "uri", "value": "https://opendata.example.org/dataset/x"}], "https://opendata.example.org/dataset/x"),
        ([{"key": "guid", "value": "https://mobil.example.org/offers/1"}], "https://mobil.example.org/offers/1"),
        (
            [
                {"key": "uri", "value": "https://metadaten.example.org/csw?REQUEST=GetRecordById&id=1"},
                {"key": "guid", "value": "https://mobil.example.org/offers/1"},
            ],
            "https://mobil.example.org/offers/1",
        ),
    ],
)
def test_the_page_extras_of_the_source_are_rank_two_after_url(extras: list[dict[str, str]], expected: str) -> None:
    # F12 = 1 (Otto, 19.11.2026): GovData keeps the page of the dataset in extras uri, else guid.
    package = _resources(FILE, url=None, extras=extras)
    found = extract_package(package["id"], package, GOVDATA_LIKE)
    assert (found.source_url, found.source_rank) == (expected, 2)


def test_the_field_url_comes_before_the_page_extras() -> None:
    package = _resources(FILE, extras=[{"key": "uri", "value": "https://opendata.example.org/dataset/x"}])
    assert extract_package(package["id"], package, GOVDATA_LIKE).source_url == PACKAGE["url"]


def test_page_extras_are_read_only_where_the_source_names_them() -> None:
    package = _resources(FILE, url=None, extras=[{"key": "uri", "value": "https://opendata.example.org/dataset/x"}])
    assert extract_package(package["id"], package, SOURCE).source_rank == 3


@pytest.mark.parametrize(
    "url",
    [
        "https://metadaten.example.org/csw?service=CSW&request=GetRecordById&id=1",
        "https://metadaten.example.org/csw?request=GetRecordById&outputSchema=http://www.isotc211.org/2005/gmd",
        "https://metadaten.example.org/record/1.xml",
        "https://metadaten.example.org/record/1.rdf",
        "https://metadaten.example.org/record/1.json?lang=de",
        # Otto, 23.11.2026: the metadata APIs of piveau and of CKAN.
        "https://piveau.example.org/api/hub/repo/datasets/abc-1",
        "https://piveau.example.org/api/hub/search/datasets/abc-1?locale=de",
        "https://piveau.example.org/api/hub/repo/catalogues/x/datasets/origin?originalId=1",
        "https://ckan.example.org/api/3/action/package_show?id=x",
        "http://opendata.example.org/dataset/x",
        "https://opendata.example.org/",
    ],
)
def test_a_metadata_record_or_a_start_page_is_no_page_of_the_dataset(url: str) -> None:
    package = _resources(FILE, url=None, extras=[{"key": "uri", "value": url}])
    assert extract_package(package["id"], package, GOVDATA_LIKE).source_rank == 3
    assert any(code.startswith("extras_page_") for code, _ in link_reasons(package, GOVDATA_LIKE))


@pytest.mark.parametrize(
    ("url", "page"),
    [
        ("https://open.bydata.de/api/hub/repo/datasets/abc-1", "https://open.bydata.de/datasets/abc-1"),
        ("https://open.bydata.de/api/hub/search/datasets/abc-1?locale=de", "https://open.bydata.de/datasets/abc-1"),
        ("https://open.bydata.de/api/hub/repo/datasets/abc-1.rdf", "https://open.bydata.de/datasets/abc-1"),
    ],
)
def test_a_piveau_record_stands_for_the_portal_s_page_where_it_is_known(url: str, page: str) -> None:
    package = _resources(FILE, url=None, extras=[{"key": "uri", "value": url}])
    found = extract_package(package["id"], package, GOVDATA_LIKE)
    assert (found.source_url, found.source_rank) == (page, 2)


def test_a_piveau_record_of_an_unknown_portal_is_skipped_for_the_next_candidate() -> None:
    extras = [
        {"key": "uri", "value": "https://piveau.example.org/api/hub/repo/datasets/abc-1"},
        {"key": "guid", "value": "https://opendata.example.org/dataset/x"},
    ]
    package = _resources(FILE, url=None, extras=extras)
    assert extract_package(package["id"], package, GOVDATA_LIKE).source_url == "https://opendata.example.org/dataset/x"


@pytest.mark.parametrize(
    ("url", "page"),
    [
        (
            "https://opendata.example.org/srv/api/records/6b8f1a2c-0000-4000-8000-00000000000a/formatters/xml",
            "https://opendata.example.org/srv/eng/catalog.search#/metadata/6b8f1a2c-0000-4000-8000-00000000000a",
        ),
        (
            "https://geo.example.org/geonetwork/srv/api/records/abc-1/formatters/xml?approved=true",
            "https://geo.example.org/geonetwork/srv/eng/catalog.search#/metadata/abc-1",
        ),
        (
            "https://geo.example.org/srv/api/0.1/records/abc-1",
            "https://geo.example.org/srv/eng/catalog.search#/metadata/abc-1",
        ),
        (
            "https://metadaten.example.org/geonetwork/srv/api/records/1/formatters/xml_iso19139",
            "https://metadaten.example.org/geonetwork/srv/eng/catalog.search#/metadata/1",
        ),
    ],
)
def test_a_geonetwork_record_stands_for_its_page_for_people_on_the_same_host(url: str, page: str) -> None:
    # Otto, 23.11.2026 (opendata.herne.de): the page of the dataset, never the interface.
    package = _resources(FILE, url=None, extras=[{"key": "uri", "value": url}])
    found = extract_package(package["id"], package, GOVDATA_LIKE)
    assert (found.source_url, found.source_rank) == (page, 2)
    assert url not in [address for _, address in link_reasons(package, GOVDATA_LIKE)]


def test_a_geonetwork_record_in_the_field_url_stands_for_its_page_too() -> None:
    record = "https://opendata.example.org/srv/api/records/abc-1/formatters/xml"
    package = _resources(FILE, url=record)
    found = extract_package(package["id"], package, SOURCE)
    assert found.source_url == "https://opendata.example.org/srv/eng/catalog.search#/metadata/abc-1"


def test_an_html_resource_at_a_geonetwork_record_is_its_page_for_people() -> None:
    viewer = {**VIEWER, "url": "https://opendata.example.org/srv/api/records/abc-1/formatters/xml"}
    found = extract_package(PACKAGE["id"], _resources(viewer), SOURCE)
    assert (found.source_url, found.source_rank) == ("https://opendata.example.org/srv/eng/catalog.search#/metadata/abc-1", 1)


@pytest.mark.parametrize(
    "url",
    [
        "https://metaver.example.org/opensearch/query?format=rdf&q=x",
        "https://gis.example.org/arcgis/rest/services/boden/MapServer",
        "https://geo.example.org/geoserver/wfs",
        "https://data.example.org/api/v1/datasets/x",
        "https://data.example.org/rest/x",
    ],
)
def test_an_interface_is_never_the_link_and_the_next_rank_counts(url: str) -> None:
    # Otto, 23.11.2026: every pattern `--classify` counts among the interfaces.
    package = _resources(FILE, url=url, extras=[{"key": "uri", "value": "https://opendata.example.org/dataset/x"}])
    found = extract_package(package["id"], package, GOVDATA_LIKE)
    assert (found.source_url, found.source_rank) == ("https://opendata.example.org/dataset/x", 2)
    assert ("url_api", url) in link_reasons(package, GOVDATA_LIKE)


def test_an_interface_without_a_next_page_leaves_the_page_in_the_catalogue() -> None:
    package = _resources(FILE, url="https://data.example.org/api/v1/datasets/x")
    found = extract_package(package["id"], package, SOURCE)
    assert found.source_rank == 3


def test_an_html_resource_at_an_interface_is_no_viewer() -> None:
    viewer = {**VIEWER, "url": "https://gis.example.org/arcgis/rest/services/boden/MapServer"}
    assert ("html_api", viewer["url"]) in link_reasons(_resources(viewer), SOURCE)
    assert extract_package(PACKAGE["id"], _resources(viewer), SOURCE).source_rank == 2


def test_an_html_resource_at_a_metadata_api_is_no_viewer() -> None:
    viewer = {**VIEWER, "url": "https://open.bydata.de/api/hub/repo/datasets/abc-1"}
    assert ("html_metadata", viewer["url"]) in link_reasons(_resources(viewer), SOURCE)


def test_an_html_resource_whose_download_address_is_a_page_is_a_viewer() -> None:
    # F12 = 1: the STAC Browser of the FSDI comes as HTML with the same address as download.
    browser = "https://data.example.org/browser/index.html#/collections/ch.example.dem"
    viewer = {**VIEWER, "url": browser, "download_url": browser}
    found = extract_package(PACKAGE["id"], _resources(viewer), SOURCE)
    assert (found.source_url, found.source_rank) == (browser, 1)
    page = {**VIEWER, "url": "https://data.example.org/karte/x", "download_url": "https://data.example.org/karte/x"}
    assert extract_package(PACKAGE["id"], _resources(page), SOURCE).source_rank == 1


def test_an_html_resource_whose_download_address_is_a_file_is_no_viewer() -> None:
    viewer = {**VIEWER, "download_url": "https://data.example.org/x.zip"}
    found = extract_package(PACKAGE["id"], _resources(viewer), SOURCE)
    assert found.source_rank == 2 and "html_with_download" in dict(link_reasons(_resources(viewer), SOURCE))


def test_the_page_extras_are_part_of_the_extractor_version() -> None:
    assert extractor_version(SOURCE) != extractor_version(GOVDATA_LIKE)


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Point", "coordinates": [[8.4, 47.1], [8.5, 47.2]]},
        {"type": "Polygon", "coordinates": [[8.4, 47.1], [8.6, 47.2], [8.4, 47.2]]},
        {"type": "MultiPolygon", "coordinates": [[[8.4, 47.1], [8.6, 47.2], [8.4, 47.1]]]},
    ],
)
def test_a_geometry_whose_nesting_does_not_fit_its_type_is_no_extent(geometry: dict[str, Any]) -> None:
    # Review M5-20 PR 1: PostGIS reads such a Point as POINT(0 0) and refuses such a Polygon.
    package = _with(PACKAGE, extras=[{"key": "spatial", "value": json.dumps(geometry)}])
    assert extract_package(PACKAGE["id"], package, SOURCE).extent_known is False


# --- Collective pages (Otto, 21.11.2026) ---------------------------------------------------------------------------

OFFICE = "https://www.sz.ch/agi"
THEME = "https://oereb.bs.ch/theme/oereb_proj"
CATALOGUE_PAGE = "https://portal.example.org/dataset/example-dgm1"


def test_the_start_page_of_an_office_is_no_link_source() -> None:
    found = extract_package(PACKAGE["id"], _resources(FILE, url=OFFICE), SOURCE)
    assert (found.source_url, found.source_rank) == (CATALOGUE_PAGE, 3)
    assert (found.skipped_url, found.skipped_rank) == (OFFICE, 2)
    assert found.landing_url == CATALOGUE_PAGE


def test_a_leading_language_does_not_make_the_page_of_an_office_a_dataset() -> None:
    # Otto, 21.11.2026: /de/agi is a collective page like /agi.
    found = extract_package(PACKAGE["id"], _resources(FILE, url="https://www.sz.ch/de/agi"), SOURCE)
    assert (found.source_url, found.source_rank, found.skipped_url) == (CATALOGUE_PAGE, 3, "https://www.sz.ch/de/agi")


def test_a_page_the_source_shares_between_finds_is_no_link_source() -> None:
    package = _resources(FILE, url=THEME)
    assert extract_package(PACKAGE["id"], package, SOURCE).source_url == THEME
    found = extract_package(PACKAGE["id"], package, SOURCE, frozenset({address_key(THEME)}))
    assert (found.source_url, found.source_rank, found.landing_url) == (CATALOGUE_PAGE, 3, CATALOGUE_PAGE)
    assert (found.skipped_url, found.skipped_rank) == (THEME, 2)


def test_a_viewer_that_is_a_collective_page_gives_way_to_the_page_of_the_dataset() -> None:
    viewer = {**VIEWER, "url": "https://geo.example.ch/geoportal"}
    found = extract_package(PACKAGE["id"], _resources(viewer), SOURCE)
    assert (found.source_url, found.source_rank) == (PACKAGE["url"], 2)
    assert (found.skipped_url, found.skipped_rank) == ("https://geo.example.ch/geoportal", 1)


@pytest.mark.parametrize("url", [THEME, "https://www.sz.ch/agi?filter=dgm1", "https://www.sz.ch/agi#/produkt/dgm1"])
def test_a_specific_page_stays_the_link_source(url: str) -> None:
    found = extract_package(PACKAGE["id"], _resources(FILE, url=url), SOURCE)
    assert (found.source_url, found.source_rank, found.skipped_url, found.skipped_rank) == (url, 2, None, None)


def test_a_rank_that_did_not_change_is_no_skipped_link() -> None:
    # Two viewers, the first a collective page: the second is a viewer too, so the link stays at rank 1.
    first = {**VIEWER, "url": "https://geo.example.ch/aa"}
    second = {**VIEWER, "url": "https://geo.example.ch/viewer/dgm1"}
    found = extract_package(PACKAGE["id"], _resources(first, second), SOURCE)
    assert (found.source_url, found.source_rank, found.skipped_url) == (second["url"], 1, None)


def test_without_a_page_left_the_find_is_invalid() -> None:
    source = replace(SOURCE, catalog_page=None)
    with pytest.raises(Invalid) as raised:
        extract_package(PACKAGE["id"], _resources(FILE, url=OFFICE), source)
    assert raised.value.reason == "no_link"


def test_the_links_a_package_could_take_are_kept_for_the_index_of_the_source() -> None:
    package = _resources(VIEWER, FILE, url=THEME)
    found = extract_package(PACKAGE["id"], package, SOURCE)
    assert found.link_candidates == ((1, VIEWER["url"]), (2, THEME))
    # What the rule skipped stays among them: the index decides on every candidate.
    skipped = extract_package(PACKAGE["id"], package, SOURCE, frozenset({address_key(THEME)}))
    assert skipped.link_candidates == found.link_candidates
    assert extract_package(PACKAGE["id"], _resources(FILE, url=OFFICE), SOURCE).link_candidates == ()


def test_a_find_without_a_free_link_keeps_the_links_it_could_have_taken() -> None:
    source = replace(SOURCE, catalog_page=None)
    package = _resources(FILE, url=THEME)
    with pytest.raises(Invalid) as raised:
        extract_package(PACKAGE["id"], package, source, frozenset({address_key(THEME)}))
    assert (raised.value.reason, raised.value.link_candidates) == ("no_link", ((2, THEME),))


def test_the_reason_why_a_page_is_a_collective_page() -> None:
    package = _resources({**VIEWER, "url": "https://geo.example.ch/geoportal"}, url=OFFICE)
    reasons = dict(link_reasons(package, SOURCE))
    assert reasons["url_collection_page"] == OFFICE
    assert reasons["html_collection_page"] == "https://geo.example.ch/geoportal"
