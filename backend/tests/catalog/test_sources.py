"""The seed of the harvest, ``backend/catalog/sources/`` (M5-19 plan §4.1, F7)."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from earthx.catalog.datasets import CATALOG_DIR
from earthx.catalog.entry_files import EntryFileError
from earthx.catalog.listed import load_regions
from earthx.catalog.sources import (
    CkanFilter,
    RobotsException,
    SourceProtocol,
    StacFilter,
    read_source,
    read_sources,
)
from earthx.discovery.links import checked_link

STAC = """\
source_id: example-stac
protocol: stac-api
endpoint: https://stac.example.org/api/v1
catalog_page: https://stac.example.org/browser/#/collections/{id}
filter:
  collection_prefixes: []
max_requests_per_run: 20
max_pages_per_run: null
rows_per_page: null
full_every_days: 1
robots_exception: null
maturity: stable
enabled: true
country: null
dedupe_rank: 1
"""


def _write(tmp_path: Path, text: str, name: str = "example-stac.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


class TestTheReleasedSeed:
    def test_the_five_sources_otto_released(self) -> None:
        sources = read_sources()
        assert set(sources) == {"fsdi-stac", "earth-search", "govdata", "opendata-swiss", "data-gv-at"}
        assert {s.source_id for s in sources.values() if s.protocol is SourceProtocol.STAC_API} == {
            "fsdi-stac",
            "earth-search",
        }

    def test_data_gv_at_is_held_until_ottos_first_run(self) -> None:
        # F7 = 1: the endpoint is not confirmed from a session.
        sources = read_sources()
        assert not sources["data-gv-at"].enabled
        assert all(source.enabled for key, source in sources.items() if key != "data-gv-at")

    def test_no_ckan_source_filters_on_the_spatial_field(self) -> None:
        # Otto, 17.11.2026: finds without an extent are kept, so no source drops them on the server either.
        for source in read_sources().values():
            if isinstance(source.filter, CkanFilter):
                assert source.filter.fq is None or "spatial" not in source.filter.fq

    def test_earth_search_links_to_the_stac_browser(self) -> None:
        # F9 = 1: its collections carry no page for people, so the source names one; a valid link "Source".
        page = read_sources()["earth-search"].catalog_page
        assert page is not None and page.startswith("https://radiantearth.github.io/stac-browser/#/external/")
        assert checked_link(page.replace("{id}", "sentinel-2-l2a")) is not None

    def test_robots_txt_is_strict_but_for_the_metadata_apis_of_the_ckan_sources(self) -> None:
        # Otto, 18.11.2026: an exception only in the file of a source, for its metadata API, with the provider's docs.
        sources = read_sources()
        assert sources["opendata-swiss"].robots_exception == RobotsException(
            "/api/3/action/", "https://handbook.opendata.swiss/de/content/nutzen/api-nutzen.html"
        )
        assert sources["govdata"].robots_exception == RobotsException(
            "/api/3/action/", "https://www.govdata.de/daten/-/details/govdata-metadatenkatalog"
        )
        assert all(s.robots_exception is None for key, s in sources.items() if key not in ("opendata-swiss", "govdata"))

    def test_the_pages_a_run_of_the_ckan_sources(self) -> None:
        # Otto, 18.11.2026: opendata.swiss refused for hours after some 100 pages; GovData's value comes after its run.
        sources = read_sources()
        # 19.11.2026: by key, a full pass of opendata.swiss fits one run; GovData reads 400 pages a run too.
        assert sources["opendata-swiss"].max_pages_per_run == sources["govdata"].max_pages_per_run == 400
        assert all(s.max_pages_per_run is None for key, s in sources.items() if key not in ("opendata-swiss", "govdata"))

    def test_govdata_reads_its_page_from_uri_else_guid(self) -> None:
        # F12 = 1 (Otto, 19.11.2026).
        sources = read_sources()
        assert sources["govdata"].filter == CkanFilter(None, "publisher_name", ("uri", "guid"))
        assert sources["opendata-swiss"].filter == CkanFilter(None, "organization", ())

    def test_govdata_is_asked_on_its_api_host(self) -> None:
        # Otto, 18.11.2026: www.govdata.de disallows all but the large search engines; the API lives on its own host.
        govdata = read_sources()["govdata"]
        assert (govdata.host, govdata.endpoint) == ("ckan.govdata.de", "https://ckan.govdata.de/api/3/action")

    def test_a_full_govdata_run_fits_its_budget(self) -> None:
        # 165 427 datasets at 100 per page (plan §4.3).
        govdata = read_sources()["govdata"]
        assert govdata.max_requests_per_run >= govdata.max_pages_per_run


class TestReading:
    def test_a_valid_file(self, tmp_path: Path) -> None:
        source = read_source(_write(tmp_path, STAC))
        assert source.host == "stac.example.org"
        assert source.filter == StacFilter(())

    def test_a_missing_directory_has_no_sources(self, tmp_path: Path) -> None:
        assert read_sources(tmp_path / "none") == {}

    def test_a_readme_is_allowed_a_stray_file_not(self, tmp_path: Path) -> None:
        shutil.copy(CATALOG_DIR / "sources" / "README.md", tmp_path / "README.md")
        _write(tmp_path, STAC)
        assert set(read_sources(tmp_path)) == {"example-stac"}
        (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
        with pytest.raises(EntryFileError, match="only <source_id>.yaml"):
            read_sources(tmp_path)

    @pytest.mark.parametrize(
        ("old", "new", "message"),
        [
            ("enabled: true\n", "", "exactly the fields"),
            ("enabled: true\n", "enabled: true\nextra: 1\n", "exactly the fields"),
            ("protocol: stac-api", "protocol: oai-pmh", "protocol is one of"),
            ("https://stac.example.org/api/v1\n", "http://stac.example.org/api/v1\n", "endpoint is an https"),
            ("https://stac.example.org/api/v1\n", "https://stac.example.org/api/v1/\n", "endpoint is an https"),
            ("https://stac.example.org/api/v1\n", "https://192.0.2.1/api\n", "not a host name"),
            ("{id}", "{name}", "names {id} once"),
            ("{id}", "{id}/{id}", "names {id} once"),
            ("https://stac.example.org/browser", "ftp://stac.example.org/browser", "catalog_page is null or an https"),
            ("collection_prefixes: []", "fq: null", "collection_prefixes, nothing else"),
            ("collection_prefixes: []", "collection_prefixes: ['a b']", "list of collection id prefixes"),
            ("max_requests_per_run: 20", "max_requests_per_run: 0", "max_requests_per_run is a whole number"),
            ("max_requests_per_run: 20", "max_requests_per_run: true", "max_requests_per_run is a whole number"),
            ("full_every_days: 1", "full_every_days: 400", "full_every_days is a whole number"),
            ("maturity: stable", "maturity: great", "maturity is a maturity"),
            ("enabled: true", "enabled: yes", "enabled is true or false"),
        ],
    )
    def test_a_wrong_field_is_named_never_its_value(self, tmp_path: Path, old: str, new: str, message: str) -> None:
        assert old in STAC
        with pytest.raises(EntryFileError, match=message):
            read_source(_write(tmp_path, STAC.replace(old, new)))

    def test_the_file_is_named_after_its_source(self, tmp_path: Path) -> None:
        with pytest.raises(EntryFileError, match="named after it"):
            read_source(_write(tmp_path, STAC, name="other.yaml"))

    @pytest.mark.parametrize("source_id", ["listed", "proto-stac"])
    def test_reserved_ids(self, tmp_path: Path, source_id: str) -> None:
        # M5-40 A10: `listed` belongs to the hand entries; `proto-` to adr/0024.
        text = STAC.replace("source_id: example-stac", f"source_id: {source_id}")
        with pytest.raises(EntryFileError, match="reserved"):
            read_source(_write(tmp_path, text, name=f"{source_id}.yaml"))

    def test_a_ckan_filter(self, tmp_path: Path) -> None:
        text = (
            STAC.replace("protocol: stac-api", "protocol: ckan")
            .replace("{id}", "{name}")
            .replace("  collection_prefixes: []", "  fq: 'res_format:CSV'\n  publisher_field: organization\n  page_extras: []")
        )
        assert read_source(_write(tmp_path, text)).filter == CkanFilter("res_format:CSV", "organization")

    @pytest.mark.parametrize(
        "body",
        [
            "  fq: ''\n  publisher_field: organization\n  page_extras: []",
            "  fq: null\n  publisher_field: author\n  page_extras: []",
            "  fq: null\n  publisher_field: organization\n  page_extras: uri",
            "  fq: null\n  publisher_field: organization\n  page_extras: [uri, uri]",
            "  fq: null\n  publisher_field: organization\n  page_extras: ['a b']",
            "  fq: null\n  publisher_field: organization",
        ],
    )
    def test_a_wrong_ckan_filter(self, tmp_path: Path, body: str) -> None:
        text = (
            STAC.replace("protocol: stac-api", "protocol: ckan")
            .replace("{id}", "{name}")
            .replace("  collection_prefixes: []", body)
        )
        with pytest.raises(EntryFileError, match="fq is null|publisher_field is|page_extras|nothing else"):
            read_source(_write(tmp_path, text))


EXCEPTION = "robots_exception:\n  path: /api/v1/\n  evidence: https://docs.example.org/api\n"


class TestRobotsException:
    def test_the_path_of_the_endpoint_with_its_documentation(self, tmp_path: Path) -> None:
        source = read_source(_write(tmp_path, STAC.replace("robots_exception: null\n", EXCEPTION)))
        assert source.robots_exception == RobotsException("/api/v1/", "https://docs.example.org/api")

    @pytest.mark.parametrize(
        ("exception", "message"),
        [
            ("robots_exception: true\n", "null or has path and evidence"),
            ("robots_exception:\n  path: /api/v1/\n", "null or has path and evidence"),
            (EXCEPTION + "  note: x\n", "null or has path and evidence"),
            (EXCEPTION.replace("/api/v1/", "/"), "plain segments"),
            (EXCEPTION.replace("/api/v1/", "/api/../v1/"), "plain segments"),
            (EXCEPTION.replace("/api/v1/", "/api/v1"), "plain segments"),
            # Only the metadata API the harvest reads, never more of the host.
            (EXCEPTION.replace("/api/v1/", "/api/"), "path of endpoint"),
            (EXCEPTION.replace("/api/v1/", "/api/v1/collections/"), "path of endpoint"),
            (EXCEPTION.replace("https://docs", "http://docs"), "evidence is the https address"),
            (EXCEPTION.replace("https://docs.example.org/api", "''"), "evidence is the https address"),
        ],
    )
    def test_a_wrong_exception(self, tmp_path: Path, exception: str, message: str) -> None:
        with pytest.raises(EntryFileError, match=message):
            read_source(_write(tmp_path, STAC.replace("robots_exception: null\n", exception)))

    def test_the_field_is_required(self, tmp_path: Path) -> None:
        with pytest.raises(EntryFileError, match="exactly the fields"):
            read_source(_write(tmp_path, STAC.replace("robots_exception: null\n", "")))


CKAN = (
    STAC.replace("protocol: stac-api", "protocol: ckan")
    .replace("{id}", "{name}")
    .replace("  collection_prefixes: []", "  fq: null\n  publisher_field: organization\n  page_extras: []")
)


class TestPagesPerRun:
    def test_a_ckan_source_may_cap_its_pages(self, tmp_path: Path) -> None:
        text = CKAN.replace("max_pages_per_run: null", "max_pages_per_run: 40")
        assert read_source(_write(tmp_path, text)).max_pages_per_run == 40

    @pytest.mark.parametrize("value", ["0", "-1", "true", "'40'", "1.5", "10001"])
    def test_a_wrong_cap(self, tmp_path: Path, value: str) -> None:
        with pytest.raises(EntryFileError, match="max_pages_per_run is null or a whole number"):
            read_source(_write(tmp_path, CKAN.replace("max_pages_per_run: null", f"max_pages_per_run: {value}")))

    def test_a_stac_source_has_no_cap(self, tmp_path: Path) -> None:
        with pytest.raises(EntryFileError, match="max_pages_per_run is for a ckan source"):
            read_source(_write(tmp_path, STAC.replace("max_pages_per_run: null", "max_pages_per_run: 5")))


class TestRowsPerPage:
    def test_opendata_swiss_asks_fifty_rows_a_page(self) -> None:
        # Otto, 19.11.2026: keyset pages of 100 took 4-14 s.
        sources = read_sources()
        assert sources["opendata-swiss"].rows_per_page == 50
        assert sources["govdata"].rows_per_page == 50
        assert all(s.rows_per_page is None for key, s in sources.items() if key not in ("opendata-swiss", "govdata"))

    def test_a_ckan_source_may_set_its_rows(self, tmp_path: Path) -> None:
        assert read_source(_write(tmp_path, CKAN.replace("rows_per_page: null", "rows_per_page: 50"))).rows_per_page == 50

    @pytest.mark.parametrize("value", ["0", "1001", "true", "'50'", "2.5"])
    def test_wrong_rows(self, tmp_path: Path, value: str) -> None:
        with pytest.raises(EntryFileError, match="rows_per_page is null or a whole number"):
            read_source(_write(tmp_path, CKAN.replace("rows_per_page: null", f"rows_per_page: {value}")))

    def test_a_stac_source_has_no_rows(self, tmp_path: Path) -> None:
        with pytest.raises(EntryFileError, match="rows_per_page is for a ckan source"):
            read_source(_write(tmp_path, STAC.replace("rows_per_page: null", "rows_per_page: 50")))


class TestCountryAndDedupeRank:
    def test_the_released_seed(self) -> None:
        # M5-20 F1 = 1, F4 = 1: the state of a national catalogue, the provider's catalogue before the portals.
        sources = read_sources()
        assert {key: (s.country, s.dedupe_rank) for key, s in sources.items()} == {
            "fsdi-stac": ("CH", 1),
            "earth-search": (None, 1),
            "opendata-swiss": ("CH", 2),
            "data-gv-at": ("AT", 2),
            "govdata": ("DE", 3),
        }

    def test_every_country_is_a_state_of_the_region_outlines(self) -> None:
        states = {region.code for region in load_regions() if region.level == "state"}
        assert {s.country for s in read_sources().values() if s.country is not None} <= states

    @pytest.mark.parametrize("value", ["ch", "CHE", "'C1'", "1", "true"])
    def test_a_wrong_country(self, tmp_path: Path, value: str) -> None:
        with pytest.raises(EntryFileError, match="country is null or an ISO 3166-1 code"):
            read_source(_write(tmp_path, STAC.replace("country: null", f"country: {value}")))

    @pytest.mark.parametrize("value", ["0", "10", "null", "'1'", "true"])
    def test_a_wrong_dedupe_rank(self, tmp_path: Path, value: str) -> None:
        with pytest.raises(EntryFileError, match="dedupe_rank is a whole number from 1 to 9"):
            read_source(_write(tmp_path, STAC.replace("dedupe_rank: 1", f"dedupe_rank: {value}")))

    def test_only_opendata_swiss_reads_collection_links(self) -> None:
        # Otto, 24.11.2026: the narrow rule for the viewer links of the FSDI.
        sources = read_sources()
        assert {key for key, s in sources.items() if s.dedupe_collection_links} == {"opendata-swiss"}

    def test_the_switch_is_optional_and_off_without_it(self, tmp_path: Path) -> None:
        assert read_source(_write(tmp_path, STAC)).dedupe_collection_links is False

    def test_the_switch_can_be_set(self, tmp_path: Path) -> None:
        assert read_source(_write(tmp_path, STAC + "dedupe_collection_links: true\n")).dedupe_collection_links is True

    @pytest.mark.parametrize("value", ["1", "'true'", "null", "yes please"])
    def test_a_wrong_switch(self, tmp_path: Path, value: str) -> None:
        with pytest.raises(EntryFileError, match="dedupe_collection_links is true or false"):
            read_source(_write(tmp_path, STAC + f"dedupe_collection_links: {value}\n"))

    def test_both_are_required(self, tmp_path: Path) -> None:
        with pytest.raises(EntryFileError, match="needs exactly the fields"):
            read_source(_write(tmp_path, STAC.replace("dedupe_rank: 1\n", "")))


CKAN = (
    STAC.replace("protocol: stac-api", "protocol: ckan")
    .replace("https://stac.example.org/browser/#/collections/{id}", "https://portal.example.org/dataset/{name}")
    .replace("  collection_prefixes: []", "  fq: null\n  publisher_field: organization\n  page_extras: []")
)


class TestCatalogPageCheck:
    """M5-67 F12 = 2 (Otto, 24.11.2026): how the link check verifies a link to the catalogue's own page."""

    def test_govdata_asks_its_api_and_waits_for_ottos_confirmation_of_the_form(self) -> None:
        sources = read_sources()
        check = sources["govdata"].catalog_page_check
        assert (check.via, check.form_confirmed_on) == ("api", None)
        assert {key for key, s in sources.items() if s.catalog_page_check.via == "api"} == {"govdata", "fsdi-stac"}

    def test_the_fsdi_asks_its_collections_with_the_form_otto_opened(self) -> None:
        # F13 = 1: the 30 links of stack 1, all in order (Otto, 21.11.2026).
        check = read_sources()["fsdi-stac"].catalog_page_check
        assert (check.via, check.form_confirmed_on) == ("api", date(2026, 11, 21))

    def test_without_it_the_page_itself_is_checked(self, tmp_path: Path) -> None:
        check = read_source(_write(tmp_path, CKAN)).catalog_page_check
        assert (check.via, check.form_confirmed_on) == ("page", None)

    def test_a_confirmed_form(self, tmp_path: Path) -> None:
        text = CKAN + "catalog_page_check:\n  via: api\n  form_confirmed_on: 2026-11-24\n"
        assert read_source(_write(tmp_path, text)).catalog_page_check.form_confirmed_on == date(2026, 11, 24)

    @pytest.mark.parametrize(
        ("text", "message"),
        [
            (CKAN + "catalog_page_check:\n  via: browser\n  form_confirmed_on: null\n", "via is page or api"),
            (CKAN + "catalog_page_check:\n  via: api\n", "has via and form_confirmed_on"),
            (CKAN + "catalog_page_check:\n  via: api\n  form_confirmed_on: 2999-01-01\n", "not in the future"),
            (CKAN + "catalog_page_check:\n  via: api\n  form_confirmed_on: gestern\n", "null or a day"),
            (
                CKAN.replace("https://portal.example.org/dataset/{name}", "null")
                + "catalog_page_check:\n  via: api\n  form_confirmed_on: null\n",
                "needs a catalog_page",
            ),
        ],
    )
    def test_a_wrong_setting(self, tmp_path: Path, text: str, message: str) -> None:
        with pytest.raises(EntryFileError, match=message):
            read_source(_write(tmp_path, text))

    def test_a_stac_source_may_ask_its_collections(self, tmp_path: Path) -> None:
        text = STAC + "catalog_page_check:\n  via: api\n  form_confirmed_on: 2026-11-21\n"
        assert read_source(_write(tmp_path, text)).catalog_page_check.via == "api"
