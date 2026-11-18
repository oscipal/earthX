"""A STAC collection becomes the intermediate form of a find (M5-19 plan §5, §6). Synthetic collections only (A5)."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from earthx.catalog.registry import Maturity
from earthx.catalog.sources import SourceConfig, SourceProtocol, StacFilter
from earthx.discovery.extract import Invalid, extracted_sha256, extractor_version
from earthx.discovery.links import LinkRank
from earthx.discovery.stac import collection_key, extract_collection

SOURCE = SourceConfig(
    source_id="example-stac",
    protocol=SourceProtocol.STAC_API,
    endpoint="https://stac.example.org/api/v1",
    catalog_page="https://stac.example.org/browser/#/collections/{id}",
    filter=StacFilter(()),
    max_requests_per_run=20,
    max_pages_per_run=None,
    full_every_days=1,
    robots_exception=None,
    maturity=Maturity.STABLE,
    enabled=True,
)

COLLECTION: dict[str, Any] = {
    "type": "Collection",
    "id": "ch.example.dem",
    "title": "Example elevation model",
    "description": "A synthetic elevation model.",
    "license": "proprietary",
    "keywords": ["Elevation", "DEM", "opendata"],
    "providers": [
        {"name": "Jane Doe", "roles": ["processor"], "email": "jane@example.org"},
        {"name": "Example Office of Topography", "roles": ["licensor", "producer"]},
    ],
    "contacts": [{"name": "Jane Doe", "emails": [{"value": "jane@example.org"}]}],
    "extent": {
        "spatial": {"bbox": [[5.9, 45.8, 10.5, 47.8]]},
        "temporal": {"interval": [["2019-01-01T00:00:00Z", None]]},
    },
    "item_assets": {"dem": {"type": "image/tiff; application=geotiff; profile=cloud-optimized", "roles": ["data"]}},
    "assets": {
        "legend": {"href": "https://stac.example.org/legend.pdf", "type": "application/pdf", "roles": ["metadata"]}
    },
    "links": [
        {"rel": "self", "href": "https://stac.example.org/api/v1/collections/ch.example.dem"},
        {"rel": "license", "href": "https://www.example.org/terms"},
        {"rel": "describedby", "href": "https://metadata.example.org/record/1", "type": "text/html"},
    ],
}


def _with(**changes: Any) -> dict[str, Any]:
    collection = copy.deepcopy(COLLECTION)
    collection.update(changes)
    return collection


def test_the_fields_of_the_intermediate_form() -> None:
    found = extract_collection("ch.example.dem", COLLECTION, SOURCE)
    assert found.title == "Example elevation model"
    assert found.publisher == "Example Office of Topography"
    assert found.licence_statements == ("proprietary", "https://www.example.org/terms")
    assert found.bbox == (5.9, 45.8, 10.5, 47.8)
    assert found.extent_known
    assert found.temporal == ("2019-01-01T00:00:00Z", None)
    assert (found.data_kind, found.delivery, found.account) == ("raster", "download", "none")
    assert "opendata" not in found.keywords and "elevation" in found.keywords
    assert [d.href for d in found.distributions] == ["https://stac.example.org/legend.pdf"]


@pytest.mark.parametrize(
    "providers",
    [
        [{"name": "Jane Doe", "roles": ["processor"]}],
        [{"name": "Jane Doe"}],
        [{"name": "Jane Doe", "roles": "licensor"}],
        [{"name": "Example host", "roles": ["host"]}],
    ],
)
def test_only_a_licensor_or_producer_is_the_publisher(providers: list[dict[str, Any]]) -> None:
    # Plan §5.1, §5.3: another provider may be a person.
    assert extract_collection("k", _with(providers=providers), SOURCE).publisher is None


def test_nul_and_lone_surrogates_are_dropped_from_texts() -> None:
    # Postgres refuses both in jsonb; one such find would fail every run of the source (review of PR 1).
    found = extract_collection(
        "k", _with(title="Ti\x00tle\ud800", description="\x00", keywords=["a\x00b", "\ud800"]), SOURCE
    )
    assert (found.title, found.description) == ("Title", "")
    assert "\x00" not in repr(found.to_document()) and "\ud800" not in found.to_document()["keywords"]


def test_no_person_reaches_the_intermediate_form() -> None:
    document = extract_collection("ch.example.dem", COLLECTION, SOURCE).to_document()
    assert "Jane Doe" not in repr(document) and "jane@example.org" not in repr(document)


def test_without_a_page_of_the_provider_the_catalogue_page_is_the_source() -> None:
    found = extract_collection("ch.example.dem", COLLECTION, SOURCE)
    assert found.source_url == "https://stac.example.org/browser/#/collections/ch.example.dem"
    assert found.source_rank == LinkRank.CATALOGUE_PAGE
    assert found.landing_url == found.source_url


def test_a_viewer_page_comes_before_the_dataset_page() -> None:
    links = [
        *COLLECTION["links"],
        {"rel": "about", "href": "https://www.example.org/products/dem", "type": "text/html"},
        {"rel": "via", "href": "https://viewer.example.org/?layer=dem", "type": "text/html; charset=utf-8"},
    ]
    found = extract_collection("ch.example.dem", _with(links=links), SOURCE)
    assert (found.source_url, found.source_rank) == ("https://viewer.example.org/?layer=dem", 1)
    assert found.landing_url == "https://www.example.org/products/dem"


def test_a_file_or_a_service_is_never_the_source() -> None:
    links = [
        {"rel": "via", "href": "https://data.example.org/dem.tif", "type": "image/tiff"},
        {"rel": "alternate", "href": "https://wms.example.org/wms?request=GetCapabilities", "type": "application/xml"},
    ]
    found = extract_collection("ch.example.dem", _with(links=links), SOURCE)
    assert found.source_rank == LinkRank.CATALOGUE_PAGE


def test_without_any_valid_link_the_find_is_invalid() -> None:
    source = SourceConfig(**{**{f: getattr(SOURCE, f) for f in SOURCE.__slots__}, "catalog_page": None})
    with pytest.raises(Invalid) as raised:
        extract_collection("ch.example.dem", COLLECTION, source)
    assert raised.value.reason == "no_link"


@pytest.mark.parametrize("title", [None, "", "   ", 7])
def test_without_a_title_the_find_is_invalid(title: object) -> None:
    with pytest.raises(Invalid) as raised:
        extract_collection("ch.example.dem", _with(title=title), SOURCE)
    assert raised.value.reason == "no_title"


@pytest.mark.parametrize(
    "extent",
    [
        None,
        {},
        {"spatial": {}},
        {"spatial": {"bbox": []}},
        {"spatial": {"bbox": [[0, 0, 1]]}},
        {"spatial": {"bbox": [[0, 95, 1, 96]]}},
        {"spatial": {"bbox": [["a", 0, 1, 1]]}},
    ],
)
def test_without_a_usable_extent_the_find_is_kept_as_extent_unknown(extent: object) -> None:
    # Otto, 17.11.2026: never dropped; M5-20 decides how it is listed.
    found = extract_collection("ch.example.dem", _with(extent=extent), SOURCE)
    assert found.bbox is None and not found.extent_known
    assert found.temporal is None


@pytest.mark.parametrize(
    ("media_type", "kind"),
    [
        ("application/geo+json", "vector"),
        ("text/csv", "table"),
        ("application/pdf", "document"),
        ("application/x-netcdf", "raster"),
        ("application/octet-stream", "raster"),
    ],
)
def test_the_data_kind_follows_the_data_assets(media_type: str, kind: str) -> None:
    found = extract_collection("k", _with(item_assets={"data": {"type": media_type, "roles": ["data"]}}), SOURCE)
    assert found.data_kind == kind


def test_a_thumbnail_does_not_make_a_table_raster() -> None:
    assets = {
        "thumbnail": {"type": "image/tiff", "roles": ["thumbnail"]},
        "table": {"type": "text/csv", "roles": ["data"]},
    }
    assert extract_collection("k", _with(item_assets=assets), SOURCE).data_kind == "table"


@pytest.mark.parametrize(
    "changes",
    [
        {"storage:requester_pays": True},
        {"item_assets": {"dem": {"type": "image/tiff", "roles": ["data"], "storage:requester_pays": True}}},
        {"summaries": {"storage:requester_pays": [True]}},
        {"storage:schemes": {"aws": {"platform": "s3", "storage:requester_pays": True}}},
    ],
)
def test_requester_pays_is_read_from_the_storage_extension(changes: dict[str, Any]) -> None:
    assert extract_collection("k", _with(**changes), SOURCE).account == "requester_pays"


@pytest.mark.parametrize(
    "changes",
    [
        {"providers": "x"},
        {"providers": [{"name": "A", "roles": 3}]},
        {"links": "x"},
        {"links": 3},
        {"item_assets": [1]},
        {"summaries": [1]},
        {"keywords": "x"},
        {"keywords": 3},
        {"assets": None},
        {"extent": {"temporal": {"interval": [[3, {"a": 1}]]}}},
    ],
)
def test_odd_shapes_do_not_break_the_extract(changes: dict[str, Any]) -> None:
    extract_collection("k", _with(**changes), SOURCE)


def test_the_hash_follows_the_content() -> None:
    first = extract_collection("k", COLLECTION, SOURCE)
    assert extracted_sha256(first) == extracted_sha256(extract_collection("k", copy.deepcopy(COLLECTION), SOURCE))
    assert extracted_sha256(first) != extracted_sha256(extract_collection("k", _with(title="Other"), SOURCE))


@pytest.mark.parametrize(
    ("value", "key"),
    [({"id": "ok.1"}, "ok.1"), ({"id": ""}, None), ({"id": 3}, None), ({"id": "a b"}, None), ({}, None), ("x", None)],
)
def test_the_key_of_a_collection(value: object, key: str | None) -> None:
    assert collection_key(value) == key


def test_the_extractor_version_follows_the_link_setting_of_the_source() -> None:
    # A new catalogue page changes the link "Source" of every find: they are judged again (Otto, 17.11.2026).
    other = SourceConfig(**{**{f: getattr(SOURCE, f) for f in SOURCE.__slots__}, "catalog_page": None})
    assert extractor_version(SOURCE) == extractor_version(SOURCE)
    assert extractor_version(SOURCE) != extractor_version(other)
