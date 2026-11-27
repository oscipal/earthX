"""T-C: the report of a harvested source and the publication of its stack (M5-20 plan §5-§9, §12, §13b).

The finds are synthetic intermediate forms written straight into ``earthx_record_state`` (no catalogue is asked, plan
A5). Each test uses sources of its own and deletes their rows after, since the report commits as it goes.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
import pytest
import yaml
from psycopg.types.json import Jsonb

from earthx.catalog.approvals import load_approvals, publish
from earthx.catalog.licences import LicenceCatalogue, load_licences
from earthx.catalog.listed import BlockReason, BlockRule, BlockScope, load_regions
from earthx.catalog.listed_search import listed_entry
from earthx.catalog.listed_store import apply_blocklist, write_regions
from earthx.catalog.listing_store import mark_listings, withdraw
from earthx.catalog.municipalities import Municipality, load_municipalities, write_municipalities
from earthx.catalog.registry import ConfigError, Maturity
from earthx.catalog.sources import CkanFilter, SourceConfig, SourceProtocol, StacFilter, read_sources
from earthx.discovery import report as report_module
from earthx.discovery.dedupe import find_keys
from earthx.discovery.enrich import PLACE_NAMES_FILE, read_place_directory
from earthx.discovery.grants import GrantToAll, build_grants, dump_grants, publishers_of
from earthx.discovery.report import _full_collections, _full_members, classify_text, run_report, write_files

DAY = date(2026, 11, 19)
PUBLISHER = "Kanton Zug"


def _ckan(source_id: str) -> SourceConfig:
    return SourceConfig(
        source_id=source_id,
        protocol=SourceProtocol.CKAN,
        endpoint="https://ckan.example.org/api/3/action",
        catalog_page="https://portal.example.org/dataset/{name}",
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


def _stac(source_id: str) -> SourceConfig:
    return replace(
        _ckan(source_id),
        protocol=SourceProtocol.STAC_API,
        endpoint="https://stac.example.org/api/stac/v1",
        catalog_page=None,
        filter=StacFilter(()),
        dedupe_rank=1,
    )


def _find(key: str, **changes: Any) -> dict[str, Any]:
    found: dict[str, Any] = {
        "source_key": key,
        "title": f"Bodenkarte {key}",
        "description": "Synthetisch.",
        "publisher": PUBLISHER,
        "doi": None,
        "licence_statements": ["CC-BY-4.0"],
        "bbox": None,
        "geometry": None,
        "spatial_text": "Kanton Bern",
        "extent_known": True,
        "temporal": ["2019", "2023"],
        "data_kind": "vector",
        "delivery": "download",
        "account": "none",
        "category": "geology_soil",
        "keywords": ["boden"],
        "themes": [],
        "identifier": None,
        "source_url": f"https://amt.example.org/daten/{key}",
        "source_rank": 2,
        "landing_url": f"https://amt.example.org/daten/{key}",
        "distributions": [],
        "skipped_url": None,
        "skipped_rank": None,
    }
    found.update(changes)
    return found


class World:
    """Two sources, their finds in ``earthx_record_state`` and a licence catalogue granting CC BY 4.0 to Kanton Zug."""

    def __init__(self, conn: psycopg.Connection, tmp_path: Path) -> None:
        suffix = uuid.uuid4().hex[:10]
        self.conn = conn
        self.ckan, self.stac = _ckan(f"t-{suffix}"), _stac(f"s-{suffix}")
        self.sources = {self.ckan.source_id: self.ckan, self.stac.source_id: self.stac}
        self.out = tmp_path / "approvals"
        self.licence_dir = tmp_path / "licenses"
        self.grant(PUBLISHER)
        self.runs: dict[str, int] = {}

    def grant(self, *publishers: str) -> None:
        (self.licence_dir / "grants").mkdir(parents=True, exist_ok=True)
        (self.licence_dir / "terms.yaml").write_text(
            """\
- license_ref: cc-by-4.0
  licence_class: K2
  matches: [CC-BY-4.0]
  license: {spdx_id: CC-BY-4.0, name: CC BY 4.0, url: "https://creativecommons.org/licenses/by/4.0/",
            commercial_use: true, distribution: true, derivatives: true, share_alike: false,
            attribution_required: true, tier: processing, attribution_modified: "{publisher} (modified)",
            attribution_unmodified: "{publisher}", terms: null}
  approved_on: 2026-11-19
""",
            encoding="utf-8",
        )
        lines = "".join(f"- {{publisher: {p}, licenses: [cc-by-4.0], approved_on: 2026-11-19}}\n" for p in publishers)
        (self.licence_dir / "grants" / f"{self.ckan.source_id}.yaml").write_text(lines or "[]\n", encoding="utf-8")

    @property
    def licences(self) -> LicenceCatalogue:
        return load_licences(self.sources, self.licence_dir)

    def run(self, source: SourceConfig, kind: str = "full") -> int:
        row = self.conn.execute(
            "INSERT INTO public.earthx_harvest_run (source_id, kind, status, lease_until, finished_at)"
            " VALUES (%s, %s, 'done', now(), clock_timestamp()) RETURNING run_id",
            (source.source_id, kind),
        ).fetchone()
        assert row is not None
        self.runs[source.source_id] = row[0]
        return row[0]

    def put(self, source: SourceConfig, *finds: dict[str, Any], state: str = "extracted") -> None:
        run_id = self.runs.get(source.source_id) or self.run(source)
        for found in finds:
            self.conn.execute(
                "INSERT INTO public.earthx_record_state (source_id, source_key, state, extracted, extracted_sha256,"
                " extent_known, last_seen_run) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (source_id, source_key) DO UPDATE SET state = EXCLUDED.state,"
                " extracted = EXCLUDED.extracted, extracted_sha256 = EXCLUDED.extracted_sha256,"
                " extent_known = EXCLUDED.extent_known",
                (
                    source.source_id,
                    found["source_key"],
                    state,
                    None if state != "extracted" else Jsonb(found),
                    None if state != "extracted" else uuid.uuid4().hex * 2,
                    None if state != "extracted" else True,
                    run_id,
                ),
            )

    def report(self, source: SourceConfig | None = None, blocklist: tuple[BlockRule, ...] = (), **kwargs: Any):  # type: ignore[no-untyped-def]
        source = source or self.ckan
        result = run_report(
            self.conn, source, sources=self.sources, licences=self.licences, blocklist=blocklist, **kwargs
        )
        if not kwargs.get("classify_only"):
            result.files = write_files(self.conn, source, result, self.out, DAY)
        return result

    def row(self, key: str, source: SourceConfig | None = None) -> dict[str, Any]:
        source = source or self.ckan
        cur = self.conn.execute(
            "SELECT state, verdict, waiting_reason, extent_basis, footprint IS NOT NULL AS footprint, regions,"
            " duplicate_of, missing_since, removed_reason, content FROM public.earthx_listed_entry"
            " WHERE source_id = %s AND source_key = %s",
            (source.source_id, key),
        )
        found = cur.fetchone()
        assert found is not None, key
        return dict(zip([c.name for c in cur.description or ()], found, strict=True))

    def approve(self, path: Path, *, excluded: tuple[str, ...] = (), revoked: date | None = None) -> None:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for item in document["sample"]:
            item["ok"] = True
        # A day of its own for each field: the same object twice would be written as a YAML anchor, which is refused.
        decided = date(DAY.year, DAY.month, DAY.day)
        document.update(decision="approved", decided_on=decided, excluded_rules=list(excluded), revoked_on=revoked)
        path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")

    def pass_links(self) -> None:
        """Every link of these sources passed the automatic check with its current address (M5-67)."""
        self.conn.execute(
            "INSERT INTO public.earthx_link_check (dataset_id, url, host, pattern, outcome, reason, checked_at)"
            " SELECT dataset_id, content -> 'earthx:listing' ->> 'source_url', link_host, link_host, 'passed', 'ok',"
            " now() FROM public.earthx_listed_entry WHERE source_id = ANY(%s) AND content IS NOT NULL"
            " ON CONFLICT (dataset_id) DO UPDATE SET url = EXCLUDED.url, outcome = 'passed', reason = 'ok',"
            " guarded = false",
            (list(self.sources),),
        )

    def publish(self, *, links_pass: bool = True):  # type: ignore[no-untyped-def]
        if links_pass:
            self.pass_links()
        return publish(self.conn, load_approvals(self.out))

    def clean(self) -> None:
        ids = list(self.sources)
        self.conn.execute(
            "DELETE FROM public.earthx_listing_batch_entry WHERE batch_id IN"
            " (SELECT batch_id FROM public.earthx_listing_batch WHERE source_id = ANY(%s))",
            (ids,),
        )
        for table in ("earthx_listing_batch", "earthx_listed_entry", "earthx_record_state", "earthx_harvest_run"):
            self.conn.execute(f"DELETE FROM public.{table} WHERE source_id = ANY(%s)", (ids,))


@pytest.fixture(scope="module")
def _regions(require_postgres_env: None) -> None:
    with psycopg.connect() as conn:
        write_regions(conn, load_regions())
        # As catalog-load does: the report needs the municipalities of the image in the table (F9).
        write_municipalities(conn, load_municipalities())
        conn.commit()


@pytest.fixture
def world(_regions: None, tmp_path: Path) -> Iterator[World]:
    with psycopg.connect(autocommit=True) as conn:
        made = World(conn, tmp_path)
        try:
            yield made
        finally:
            made.clean()


def test_a_find_with_a_granted_licence_waits_in_a_stack_until_its_approval(world: World) -> None:
    world.put(world.ckan, _find("a"))
    result = world.report()
    assert world.row("a")["state"] == "in_review"
    assert result.stack is not None and result.stack.created and len(result.files) == 2
    approval = result.files[0]
    document = yaml.safe_load(approval.read_text(encoding="utf-8"))
    assert document["decision"] == "pending" and document["sample"][0]["why"] == "all"
    # Pending publishes nothing.
    assert world.publish().published == {}
    assert world.row("a")["state"] == "in_review"
    world.approve(approval)
    assert world.publish().published == {f"approvals/{approval.name}": 1}
    published = world.row("a")
    assert published["state"] == "published" and published["content"]["earthx:listing"]["approved_on"] == "2026-11-19"
    # Twice publishes nothing more; a report without a change forms no stack and writes no file.
    assert world.publish().published == {}
    again = world.report()
    assert again.stack is None and again.files == () and again.written == 0


def test_an_approved_file_without_its_sample_checked_is_refused(world: World, tmp_path: Path) -> None:
    world.put(world.ckan, _find("a"))
    approval = world.report().files[0]
    document = yaml.safe_load(approval.read_text(encoding="utf-8"))
    document.update(decision="approved", decided_on=DAY)
    approval.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(Exception, match="every entry of its sample checked"):
        load_approvals(world.out)


def test_what_waits_and_what_is_hidden(world: World) -> None:
    world.put(
        world.ckan,
        _find("unknown", licence_statements=["Weitere Informationen auf der Seite"]),
        _find("none", licence_statements=[]),
        _find("other", publisher="Stadt Zug"),
        _find("access", account=None),
        _find("statistics", data_kind="table", category="population", title="Zug: Bevölkerung",
              publisher="Statistisches Amt", spatial_text=None),
    )
    result = world.report()
    assert [world.row(k)["waiting_reason"] for k in ("unknown", "none", "other", "access")] == [
        "unknown_licence",
        "no_licence",
        "not_granted",
        "no_access",
    ]
    assert all(world.row(k)["state"] == "needs_rule" for k in ("unknown", "none", "other", "access"))
    assert world.row("statistics")["state"] == "not_geodata"
    # Without a graded licence nothing comes into review (Otto, 19.11.2026).
    assert result.stack is None and result.files == ()


def test_the_extent_steps_give_a_footprint_only_where_it_is_known(world: World) -> None:
    world.put(
        world.ckan,
        _find("place"),
        _find("publisher", spatial_text="Nirgendwo"),
        _find("catalog", spatial_text=None, publisher="Bundesamt"),
        _find("source", spatial_text=None, bbox=[8.4, 47.1, 8.6, 47.2]),
    )
    world.report()
    assert (world.row("place")["extent_basis"], world.row("place")["footprint"]) == ("place", True)
    assert world.row("place")["regions"] == ["CH", "CH-BE"]
    publisher = world.row("publisher")
    assert (publisher["extent_basis"], publisher["footprint"], publisher["regions"]) == ("publisher", False, ["CH", "CH-ZG"])
    assert (world.row("catalog")["extent_basis"], world.row("catalog")["regions"]) == ("catalog", ["CH"])
    source = world.row("source")
    assert source["extent_basis"] == "source" and source["footprint"] and "CH-ZG" in source["regions"]


def test_a_published_entry_takes_describing_changes_and_goes_back_into_review_on_a_new_publisher(
    world: World,
) -> None:
    world.put(world.ckan, _find("a"))
    world.approve(world.report().files[0])
    world.publish()
    world.put(world.ckan, _find("a", description="Neu beschrieben."))
    assert world.report().stack is None
    row = world.row("a")
    assert row["state"] == "published" and row["content"]["description"] == "Neu beschrieben."
    assert row["content"]["earthx:listing"]["approved_on"] == "2026-11-19"
    world.grant(PUBLISHER, "Kanton Uri")
    world.put(world.ckan, _find("a", publisher="Kanton Uri"))
    result = world.report()
    assert world.row("a")["state"] == "in_review" and result.stack is not None and result.stack.created


def test_a_revoked_approval_hides_again_and_excluded_rules_stay_out(world: World) -> None:
    world.put(world.ckan, _find("a"))
    approval = world.report().files[0]
    rule = f"{world.ckan.source_id}/{PUBLISHER}/cc-by-4.0"
    world.approve(approval, excluded=(rule,))
    assert world.publish().published == {f"approvals/{approval.name}": 0}
    assert world.row("a")["state"] == "in_review"
    # The entry stays in review and comes in the next stack.
    again = world.report().files[0]
    world.approve(again)
    world.publish()
    assert world.row("a")["state"] == "published"
    world.approve(again, revoked=DAY)
    assert world.publish().revoked == {f"approvals/{again.name}": 1}
    assert world.row("a")["state"] == "in_review"


def test_a_later_stack_takes_over_and_the_older_file_publishes_nothing(world: World) -> None:
    world.put(world.ckan, _find("a"))
    first = world.report().files[0]
    world.put(world.ckan, _find("b"))
    second = world.report()
    assert second.stack is not None and len(second.stack.entries) == 2 and second.files[0] != first
    world.approve(first)
    outcome = world.publish()
    assert outcome.published == {} and outcome.stale == (f"approvals/{first.name}",)


def test_opendata_finds_naming_a_collection_are_duplicates_of_it(world: World) -> None:
    # Otto's measurement M7: the id as a whole token of an address; the provider's catalogue is the main entry.
    world.put(world.stac, _find("ch.example.boden", source_url="https://stac.example.org/browser/ch.example.boden"))
    world.put(
        world.ckan,
        _find("viewer", source_url="https://map.example.org/?layers=ch.example.boden"),
        _find("longer", source_url="https://map.example.org/?layers=ch.example.boden-relief"),
    )
    world.report(world.stac)
    world.report()
    stac_id = f"{world.stac.source_id}.ch.example.boden"
    assert (world.row("viewer")["state"], world.row("viewer")["duplicate_of"]) == ("duplicate", stac_id)
    assert world.row("longer")["state"] == "needs_rule" or world.row("longer")["state"] == "in_review"
    # The main entry is served with the link and files of its duplicate (F4 = 1).
    world.conn.execute(
        "UPDATE public.earthx_listed_entry SET state = 'published', verdict = 'ok', waiting_reason = NULL,"
        " account = 'none', delivery = 'download' WHERE dataset_id = %s",
        (stac_id,),
    )

    async def served() -> Any:
        async with await psycopg.AsyncConnection.connect() as aconn:
            return await listed_entry(aconn, stac_id)

    also_at = asyncio.run(served())["earthx:also_at"]
    assert also_at == [
        {"source_id": world.ckan.source_id, "source_url": "https://map.example.org/?layers=ch.example.boden", "distributions": []}
    ]
    # The main entry gone, the duplicate is its own entry again.
    world.conn.execute("DELETE FROM public.earthx_listed_entry WHERE dataset_id = %s", (stac_id,))
    world.conn.execute("DELETE FROM public.earthx_record_state WHERE source_id = %s", (world.stac.source_id,))
    world.report()
    assert world.row("viewer")["state"] == "in_review" and world.row("viewer")["duplicate_of"] is None


def test_a_find_gone_at_the_source(world: World) -> None:
    world.put(world.ckan, _find("a"), _find("b"))
    world.approve(world.report().files[0])
    world.publish()
    world.put(world.ckan, _find("a"), state="gone")
    world.put(world.ckan, _find("c"))
    world.report()
    assert world.row("a")["state"] == "published" and world.row("a")["missing_since"] is not None
    # The next full pass that ends without it: a tombstone, without approval (adr/0033 §9).
    world.run(world.ckan)
    world.report()
    assert (world.row("a")["state"], world.row("a")["removed_reason"]) == ("tombstone", "source_removed")
    # A row never published goes without a trace.
    world.put(world.ckan, _find("c"), state="gone")
    world.report()
    assert world.conn.execute(
        "SELECT count(*) FROM public.earthx_listed_entry WHERE source_id = %s AND source_key = 'c'",
        (world.ckan.source_id,),
    ).fetchone() == (0,)


def test_a_blocked_find_is_never_written(world: World) -> None:
    world.put(world.ckan, _find("a"), _find("b"))
    rule = BlockRule(
        BlockScope.ENTRY, BlockReason.NOT_GEODATA, date(2026, 11, 19), source_id=world.ckan.source_id, source_key="a"
    )
    result = world.report(blocklist=(rule,))
    assert result.blocked == 1
    assert world.conn.execute(
        "SELECT count(*) FROM public.earthx_listed_entry WHERE source_id = %s", (world.ckan.source_id,)
    ).fetchone() == (1,)


def test_classify_writes_nothing_and_names_the_unresolved_places(world: World) -> None:
    world.put(
        world.ckan,
        _find("a", spatial_text="Nirgendwo"),
        _find("statistics", data_kind="table", category="population", publisher="Statistisches Amt", spatial_text=None),
    )
    result = world.report(classify_only=True)
    assert world.conn.execute(
        "SELECT count(*) FROM public.earthx_listed_entry WHERE source_id = %s", (world.ckan.source_id,)
    ).fetchone() == (0,)
    text = classify_text(world.ckan, result)
    assert "Nirgendwo" in text and "not_geodata 1" in text


def test_one_foreign_find_never_stops_the_report(world: World) -> None:
    # Review M5-20 PR 1: an INSPIRE theme, an open end in 9999, a DOI that is none, a geometry PostGIS refuses.
    world.put(
        world.ckan,
        _find("inspire", themes=["inspire:so"]),
        _find("open", temporal=["2019", "9999-12-31"]),
        _find("doi", doi="N/A"),
        # The extract keeps only geometries whose nesting fits their type; one that slipped through is refused here.
        _find("geometry", spatial_text=None, bbox=[8.4, 47.1, 8.6, 47.2],
              geometry={"type": "Polygon", "coordinates": [[8.4, 47.1], [8.6, 47.2], [8.4, 47.2]]}),
    )
    result = world.report()
    assert world.row("inspire")["state"] == "in_review"
    assert world.row("open")["content"]["extent"]["temporal"]["interval"] == [["2019-01-01T00:00:00Z", None]]
    assert "sci:doi" not in world.row("doi")["content"]
    assert result.failed == 1 and result.stack is not None


def test_a_blocked_duplicate_becomes_a_tombstone(world: World) -> None:
    # Review M5-20 PR 1: the tombstone drops duplicate_of with everything else.
    world.put(world.stac, _find("ch.example.boden"))
    world.put(world.ckan, _find("viewer", source_url="https://map.example.org/?layers=ch.example.boden"))
    world.report(world.stac)
    world.report()
    assert world.row("viewer")["state"] == "duplicate"
    rule = BlockRule(BlockScope.HOST, BlockReason.QUALITY, date(2026, 11, 19), host="map.example.org")
    apply_blocklist(world.conn, (rule,))
    assert (world.row("viewer")["state"], world.row("viewer")["duplicate_of"]) == ("tombstone", None)


def test_a_row_a_full_entry_took_over_is_left_alone(world: World) -> None:
    world.put(world.ckan, _find("a"))
    world.report()
    world.conn.execute(
        "UPDATE public.earthx_listed_entry SET state = 'superseded' WHERE source_id = %s", (world.ckan.source_id,)
    )
    world.put(world.ckan, _find("a", description="Neu."))
    world.report()
    assert world.row("a")["state"] == "superseded"


@pytest.mark.parametrize(
    "changes",
    [
        {"account": "free_account"},
        {"delivery": "service"},
        {"source_url": "https://anderes.example.org/daten/a"},
    ],
)
def test_a_published_entry_goes_back_into_review_on_each_deciding_field(world: World, changes: dict[str, Any]) -> None:
    # adr/0033 §11, U1: account, delivery, host of the link (and publisher, licence, tested above and below).
    world.put(world.ckan, _find("a"))
    world.approve(world.report().files[0])
    world.publish()
    world.put(world.ckan, _find("a", **changes))
    world.report()
    assert world.row("a")["state"] == "in_review"


def test_a_new_grade_of_the_licence_goes_back_into_review(world: World) -> None:
    # Plan A18: never a licence statement Otto has not seen with the entry.
    world.put(world.ckan, _find("a"))
    world.approve(world.report().files[0])
    world.publish()
    terms = world.licence_dir / "terms.yaml"
    # Non-commercial is class K4, in the catalogue tier (the loader refuses it as K2 above the catalogue).
    regraded = terms.read_text(encoding="utf-8").replace("commercial_use: true", "commercial_use: false")
    terms.write_text(regraded.replace("licence_class: K2", "licence_class: K4").replace("tier: processing", "tier: catalog"))
    world.report()
    assert world.row("a")["state"] == "in_review"


def test_a_published_entry_that_loses_its_grant_or_turns_out_no_geodata_is_hidden(world: World) -> None:
    world.put(world.ckan, _find("a"), _find("b"))
    world.approve(world.report().files[0])
    world.publish()
    world.put(world.ckan, _find("b", data_kind="table", category="population", spatial_text=None,
                                publisher="Statistisches Amt"))
    world.grant(PUBLISHER, "Statistisches Amt")
    world.report()
    assert world.row("b")["state"] == "not_geodata"
    # A grant taken back: catalog-load hides at once, before any report (adr/0033 §9).
    world.grant()
    assert withdraw(world.conn, world.licences.granted) == 1
    assert (world.row("a")["state"], world.row("a")["waiting_reason"]) == ("needs_rule", "not_granted")


def test_an_entry_changed_after_its_stack_is_not_published(world: World) -> None:
    world.put(world.ckan, _find("a"), _find("b"))
    approval = world.report().files[0]
    world.conn.execute(
        "UPDATE public.earthx_listed_entry SET content_sha256 = %s WHERE source_id = %s AND source_key = 'b'",
        ("0" * 64, world.ckan.source_id),
    )
    world.approve(approval)
    assert world.publish().published == {f"approvals/{approval.name}": 1}
    assert world.row("b")["state"] == "in_review"


def test_a_lost_approval_file_is_written_again_for_the_open_stack(world: World) -> None:
    world.put(world.ckan, _find("a"))
    first = world.report().files
    for path in first:
        path.unlink()
    again = world.report()
    assert again.stack is not None and not again.stack.created and len(again.files) == 2
    assert world.report().files == ()


def test_a_wrong_approval_publishes_nothing(world: World) -> None:
    world.put(world.ckan, _find("a"))
    approval = world.report().files[0]
    world.approve(approval)
    document = yaml.safe_load(approval.read_text(encoding="utf-8"))
    for field, value in (("fingerprint", "b" * 64), ("batch_id", 999999), ("source_id", "other")):
        changed = dict(document, **{field: value})
        approval.write_text(yaml.safe_dump(changed, sort_keys=False), encoding="utf-8")
        assert world.publish().published == {}, field
    assert world.row("a")["state"] == "in_review"


def test_a_municipality_in_a_place_text_gives_its_outline_and_the_regions_of_its_canton(world: World) -> None:
    # F9 = 1: swissBOUNDARIES3D for towns and cities (Otto's examples "Stadt Bern", "Winterthur").
    winterthur = Municipality(
        "CH-ZH-0230",
        "Winterthur",
        "CH-ZH",
        {"type": "Polygon", "coordinates": [[[8.65, 47.45], [8.8, 47.45], [8.8, 47.55], [8.65, 47.55], [8.65, 47.45]]]},
    )
    others = [m for m in load_municipalities() if m.code != winterthur.code]
    write_municipalities(world.conn, [*others, winterthur])
    try:
        directory = read_place_directory(PLACE_NAMES_FILE, {r.code: r.level for r in load_regions()}, [*others, winterthur])
        world.put(world.ckan, _find("w", spatial_text="Winterthur"))
        world.report(directory=directory)
        row = world.row("w")
        assert (row["extent_basis"], row["footprint"], row["regions"]) == ("place", True, ["CH", "CH-ZH"])
        assert row["content"]["extent"]["spatial"]["bbox"] == [[8.65, 47.45, 8.8, 47.55]]
    finally:
        write_municipalities(world.conn, load_municipalities())


def test_classify_counts_the_geonames_ids_it_cannot_place(world: World) -> None:
    # F10 = 1: the ids are shown, the session proposes their places.
    world.put(world.ckan, _find("g", spatial_text="https://sws.geonames.org/2658434/"))
    text = classify_text(world.ckan, world.report(classify_only=True))
    assert "1  https://sws.geonames.org/2658434/" in text



def test_the_report_refuses_to_run_before_catalog_load_wrote_the_municipalities(world: World) -> None:
    # A municipality the image knows and the table lacks: here one made up beside the real ones.
    newtown = Municipality(
        "CH-ZH-9999", "Neustadt am Test", "CH-ZH",
        {"type": "Polygon", "coordinates": [[[8.7, 47.5], [8.8, 47.5], [8.8, 47.6], [8.7, 47.5]]]},
    )
    directory = read_place_directory(
        PLACE_NAMES_FILE, {r.code: r.level for r in load_regions()}, [*load_municipalities(), newtown]
    )
    try:
        with pytest.raises(ConfigError, match="run catalog-load first"):
            world.report(directory=directory)
    finally:
        write_municipalities(world.conn, load_municipalities())


def test_classify_explains_no_access_and_lists_the_licence_statements(world: World) -> None:
    # Otto's points 4 and 7 of 20.11.2026.
    world.put(
        world.ckan,
        _find("pages", delivery=None, account=None, distributions=[{"href": "https://amt.example.org/viewer", "format": "HTML", "media_type": None, "title": None, "roles": []}]),
        _find("rights", account=None),
        _find("none", delivery=None, account=None),
    )
    text = classify_text(world.ckan, world.report(classify_only=True))
    for reason in ("nur Seiten (HTML)", "access_rights eingeschränkt oder nicht öffentlich", "keine Ressource mit https-Adresse"):
        assert reason in text
    assert "3  CC-BY-4.0 | Kanton Zug 3" in text
    assert '{"finds": 3, "statement": "CC-BY-4.0"}' in text


def test_grants_built_from_the_publishers_in_the_database_list_their_finds(world: World) -> None:
    # Otto, 20.11.2026: the grants come from the data, one line per publisher (plan §13f).
    world.grant()
    world.put(
        world.ckan,
        _find("zug"),
        _find("b", publisher="Amt B"),
        _find("none", publisher=None),
        _find("blank", publisher=" Amt C"),
    )
    world.put(world.ckan, _find("gone", publisher="Amt D"), state="gone")
    found = publishers_of(world.conn, world.ckan.source_id)
    assert (found.publishers, found.without) == (("Amt B", PUBLISHER), 2)
    lines = build_grants(found.publishers, GrantToAll(("cc-by-4.0",), DAY), (), DAY)
    (world.licence_dir / "grants" / f"{world.ckan.source_id}.yaml").write_text(dump_grants(lines), encoding="utf-8")
    world.report()
    assert world.row("b")["state"] == world.row("zug")["state"] == "in_review"
    assert world.row("none")["waiting_reason"] == world.row("blank")["waiting_reason"] == "not_granted"


def test_classify_counts_the_links_that_fell_to_another_rank_because_of_a_collective_page(world: World) -> None:
    # Otto, 21.11.2026: how many links per source fell to another rank, with ten examples.
    catalogue = "https://portal.example.org/dataset/"
    office, project = "https://www.sz.ch/agi", "https://oereb.bs.ch/theme/oereb_proj"
    world.put(
        world.ckan,
        _find("kept"),
        _find("office", source_rank=3, source_url=catalogue + "office", skipped_url=office, skipped_rank=2),
        _find("project", source_rank=3, source_url=catalogue + "project", skipped_url=project, skipped_rank=2),
        _find(
            "viewer",
            source_rank=2,
            source_url="https://amt.example.org/daten/viewer",
            skipped_url="https://geo.example.ch/portal",
            skipped_rank=1,
        ),
    )
    result = world.report(classify_only=True)
    assert result.link_moves == {"2 → 3": 2, "1 → 2": 1}
    text = classify_text(world.ckan, result)
    assert "auf einen anderen Rang gefallen (3 von 4), nach Rang:" in text
    assert "2  Rang 2 → 3" in text and "1  Rang 1 → 2" in text
    assert f"- Bodenkarte office | <https://www.sz.ch/agi>, 2 | <{catalogue}office>, 3" in text
    assert "Bodenkarte kept |" not in text


def test_classify_shows_at_most_ten_examples_of_fallen_links(world: World) -> None:
    world.put(
        world.ckan,
        *(
            _find(
                f"f{n}",
                source_rank=3,
                source_url=f"https://portal.example.org/dataset/f{n}",
                skipped_url="https://www.sz.ch/agi",
                skipped_rank=2,
            )
            for n in range(25)
        ),
    )
    text = classify_text(world.ckan, world.report(classify_only=True))
    assert "(25 von 25)" in text
    assert sum(1 for line in text.splitlines() if "<https://www.sz.ch/agi>, 2 |" in line) == 10


def test_classify_names_why_a_find_is_not_granted(world: World) -> None:
    # Otto, 23.11.2026: a pair "publisher | granted licence" waited; the list now names what is missing.
    terms = world.licence_dir / "terms.yaml"
    terms.write_text(
        terms.read_text(encoding="utf-8")
        + """\
- license_ref: other-closed
  licence_class: K6
  matches: [other-closed]
  license: {spdx_id: null, name: Andere geschlossen, url: "https://example.org/closed", commercial_use: false,
            distribution: false, derivatives: false, share_alike: false, attribution_required: true, tier: catalog,
            attribution_modified: null, attribution_unmodified: null, terms: null}
  approved_on: 2026-11-19
""",
        encoding="utf-8",
    )
    world.put(
        world.ckan,
        _find("two", licence_statements=["CC-BY-4.0", "other-closed"]),
        _find("stranger", publisher="Stadt Zug"),
    )
    text = classify_text(world.ckan, world.report(classify_only=True))
    assert "1  Kanton Zug | nicht freigegeben: other-closed" in text
    assert f"1  Stadt Zug | Herausgeber ohne Zeile in grants/{world.ckan.source_id}.yaml (Lizenzen: cc-by-4.0)" in text
    assert "Kanton Zug | CC-BY-4.0" not in text


def test_classify_lists_only_the_statements_the_catalogue_does_not_know(world: World) -> None:
    # Otto, 23.11.2026: 224 finds of one publisher waited with an identifier of the licence beside its address; the pair
    # of the waiting list must name the identifier, not the address that was known.
    world.put(world.ckan, _find("beside", licence_statements=["CC-BY-4.0", "dl-by-zz/9.9"]))
    text = classify_text(world.ckan, world.report(classify_only=True))
    assert "1  Kanton Zug | dl-by-zz/9.9" in text
    assert "Kanton Zug | CC-BY-4.0" not in text


def test_a_viewer_link_of_the_fsdi_makes_a_duplicate_only_for_a_source_that_says_so(world: World) -> None:
    # Otto, 24.11.2026: opendata.swiss names the collections in the viewer links of its resources.
    world.put(world.stac, _find("ch.example.boden", source_url="https://stac.example.org/browser/ch.example.boden"))
    link = {"href": "https://map.example.org/?layers=ch.example.boden", "format": "HTML", "media_type": None}
    world.put(world.ckan, _find("linking", distributions=[link]))
    world.report(world.stac)
    world.report()
    assert world.row("linking")["duplicate_of"] is None
    # The viewer link is that of the FSDI: map.geo.admin.ch with layers=, here at the address of the test portal.
    fsdi = {"href": "https://map.geo.admin.ch/?layers=ch.example.boden", "format": "HTML", "media_type": None}
    world.put(world.ckan, _find("linking", distributions=[fsdi]))
    world.report(replace(world.ckan, dedupe_collection_links=True))
    assert world.row("linking")["duplicate_of"] == f"{world.stac.source_id}.ch.example.boden"
    world.report()
    assert world.row("linking")["duplicate_of"] is None


def _fsdi(world: World) -> SourceConfig:
    """A STAC source at the host of the FSDI, as ``sources/fsdi-stac.yaml``, so that the full entries on it are met."""
    fsdi = replace(_stac(f"f-{world.ckan.source_id}"), endpoint="https://data.geo.admin.ch/api/stac/v1")
    world.sources[fsdi.source_id] = fsdi
    return fsdi


def test_swissalti3d_listed_from_the_fsdi_is_a_duplicate_of_the_full_entry(world: World) -> None:
    # Otto, 24.11.2026: swissALTI3D showed twice in the Data catalogue, as a full and as a listed entry (adr/0033 §11).
    fsdi = _fsdi(world)
    world.put(fsdi, _find("ch.swisstopo.swissalti3d", source_url="https://data.geo.admin.ch/browser/#/collections/x"))
    world.report(fsdi)
    row = world.row("ch.swisstopo.swissalti3d", fsdi)
    assert (row["state"], row["duplicate_of"]) == ("duplicate", "swissalti3d")


def test_swissalti3d_listed_by_opendata_swiss_through_its_viewer_link_is_a_duplicate_of_the_full_entry(
    world: World,
) -> None:
    page = "https://data.geo.admin.ch/browser/index.html#/collections/ch.swisstopo.swissalti3d"
    world.put(
        world.ckan,
        _find("swissalti3d", source_url="https://opendata.swiss/de/dataset/swissalti3d", link_candidates=[[1, page]], skipped_url=page),
    )
    world.report()
    assert world.row("swissalti3d")["duplicate_of"] is None
    world.report(replace(world.ckan, dedupe_collection_links=True))
    assert world.row("swissalti3d")["duplicate_of"] == "swissalti3d"


def test_every_full_entry_on_a_harvested_stac_host_has_the_key_of_its_listed_collection() -> None:
    # The audit of 24.11.2026: a find of a STAC source gets the key of its collection id at the source's host; the
    # full entry on that host must carry the same key, else the full entry does not take over the listed one.
    hosts = {s.host: s for s in read_sources().values() if s.protocol is SourceProtocol.STAC_API}
    full = {m.dataset_id: m.keys for m in _full_members()}
    audited = 0
    for config, host, collection_id in _full_collections():
        source = hosts.get(host)
        if source is None:
            continue
        audited += 1
        keys = find_keys({"source_key": collection_id}, stac_host=source.host, known={})
        assert set(keys) <= set(full[config.dataset_id]), config.dataset_id
    assert audited >= 5


IDENTIFIER = "691cb471-c3b5-48ec-a107-d0ad612fa70b@bundesamt-fur-landestopografie-swisstopo"


def _opendata_swissalti3d(world: World) -> tuple[str, list[dict[str, Any]]]:
    """The finds of opendata.swiss around swissALTI3D (Otto, 24.11.2026): its listing, with a geocat identifier and no
    link to the FSDI, and the two shaded-relief products, which are products of their own."""
    finds = [
        _find("549438da", title="swissALTI3D", identifier=IDENTIFIER, source_url="https://opendata.swiss/de/dataset/a"),
        _find("mono", title="swissALTI3D Reliefschattierung monodirektional", identifier="mono@swisstopo"),
        _find("multi", title="swissALTI3D Reliefschattierung multidirektional", identifier="multi@swisstopo"),
    ]
    return f"{world.ckan.source_id}:{IDENTIFIER}", finds


def test_the_listing_of_swissalti3d_at_opendata_swiss_is_a_duplicate_of_the_full_entry(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    listing, finds = _opendata_swissalti3d(world)
    monkeypatch.setattr(report_module, "_listings", lambda: {listing: "swissalti3d"})
    world.put(world.ckan, *finds)
    world.report()
    assert (world.row("549438da")["state"], world.row("549438da")["duplicate_of"]) == ("duplicate", "swissalti3d")
    for key in ("mono", "multi"):
        assert world.row(key)["duplicate_of"] is None
    # The named listing taken back, the find is its own entry again (in review, as every restored row).
    monkeypatch.setattr(report_module, "_listings", lambda: {})
    world.report()
    assert (world.row("549438da")["state"], world.row("549438da")["duplicate_of"]) == ("in_review", None)


def test_classify_proposes_the_finds_with_the_title_of_a_full_entry(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    listing, finds = _opendata_swissalti3d(world)
    world.put(world.ckan, *finds)
    text = classify_text(world.ckan, world.report(classify_only=True))
    assert "Kandidaten für also_listed_as (1; Titel gleich dem eines vollen Eintrags" in text
    expected = f"swissalti3d „swissALTI3D“ | {world.ckan.source_id}.549438da „swissALTI3D“ | {world.ckan.source_id} | {PUBLISHER} | {listing}"
    assert f"  - {expected}" in text
    assert "Reliefschattierung" not in text.split("Kandidaten für also_listed_as")[1].split("Gleichnamige")[0]
    # Once the listing is named, the find is no candidate any more; the report keeps the list in its file.
    monkeypatch.setattr(report_module, "_listings", lambda: {listing: "swissalti3d"})
    assert "Kandidaten für also_listed_as (0;" in classify_text(world.ckan, world.report(classify_only=True))


def test_the_report_file_lists_the_candidates_for_also_listed_as(world: World) -> None:
    listing, finds = _opendata_swissalti3d(world)
    world.put(world.ckan, *finds)
    result = world.report()
    markdown = next(path for path in result.files if path.suffix == ".md").read_text(encoding="utf-8")
    assert "## Kandidaten für also_listed_as (1; nur ein Vorschlag, nie automatisch eingetragen)" in markdown
    assert f"| {listing}" in markdown
    assert [c.key for c in result.title_candidates] == [listing]


def test_classify_shows_examples_of_the_new_pairs(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    listing, finds = _opendata_swissalti3d(world)
    world.put(world.ckan, *finds)
    world.report()
    monkeypatch.setattr(report_module, "_listings", lambda: {listing: "swissalti3d"})
    result = world.report(classify_only=True)
    assert result.dedupe is not None and [p[0] for p in result.dedupe.new] == [f"{world.ckan.source_id}.549438da"]
    text = classify_text(world.ckan, result)
    assert "10 Beispiele neu (Duplikat | Haupteintrag | Schlüssel):" in text
    assert f"- swissALTI3D <{world.ckan.source_id}.549438da> | " in text.split("10 Beispiele neu")[1]


def test_catalog_load_marks_the_listing_of_a_full_entry_as_its_duplicate(world: World) -> None:
    listing, finds = _opendata_swissalti3d(world)
    world.put(world.ckan, *finds)
    world.report()
    published = f"{world.ckan.source_id}.549438da"
    world.conn.execute("UPDATE public.earthx_listed_entry SET state = 'published' WHERE dataset_id = %s", (published,))
    assert mark_listings(world.conn, {listing: "swissalti3d"}) == (published,)
    assert (world.row("549438da")["state"], world.row("549438da")["duplicate_of"]) == ("duplicate", "swissalti3d")
    assert world.row("mono")["duplicate_of"] is None
    assert mark_listings(world.conn, {listing: "swissalti3d"}) == ()
    assert mark_listings(world.conn, {}) == ()
    # Another source with the same identifier is another find.
    assert mark_listings(world.conn, {f"other-source:{IDENTIFIER}": "swissalti3d"}) == ()


def test_a_collection_in_a_distribution_makes_no_duplicate(world: World) -> None:
    # Otto, 23.11.2026: a find that links to a collection of the FSDI in a file is not that collection.
    world.put(world.stac, _find("ch.example.boden", source_url="https://stac.example.org/browser/ch.example.boden"))
    linked = {"href": "https://map.example.org/?layers=ch.example.boden", "format": "HTML", "media_type": None}
    world.put(world.ckan, _find("linking", distributions=[linked]))
    world.report(world.stac)
    world.report()
    assert world.row("linking")["duplicate_of"] is None


def test_classify_compares_the_pairs_with_the_last_report(world: World) -> None:
    # Otto, 23.11.2026: pairs by kind of key, ten examples, and what the new keys make of the stored ones.
    world.put(world.stac, _find("ch.example.boden", source_url="https://stac.example.org/browser/ch.example.boden"))
    linked = {"href": "https://map.example.org/?layers=ch.example.boden", "format": "HTML", "media_type": None}
    world.put(
        world.ckan,
        _find("viewer", source_url="https://map.example.org/?layers=ch.example.boden"),
        _find("linking", distributions=[linked]),
        _find("same-doi", doi="10.1/zz"),
    )
    world.put(world.stac, _find("other", doi="10.1/zz"))
    world.report(world.stac)
    world.report()
    # The last report was made with the old keys: the distribution named the collection.
    world.conn.execute(
        "UPDATE public.earthx_listed_entry SET state = 'duplicate', duplicate_of = %s,"
        " dedupe_keys = ARRAY[%s] WHERE dataset_id = %s",
        (
            f"{world.stac.source_id}.ch.example.boden",
            "coll:stac.example.org/ch.example.boden",
            f"{world.ckan.source_id}.linking",
        ),
    )
    result = world.report(classify_only=True)
    text = classify_text(world.ckan, result)
    assert result.dedupe is not None
    assert [pair[0] for pair in result.dedupe.lost] == [f"{world.ckan.source_id}.linking"]
    assert "Dubletten (gerechnet mit den Schlüsseln dieser Ableitung; nichts geschrieben):" in text
    assert "Paare jetzt 2 (nach Schlüsselart: DOI 1, Collection-ID 1)" in text
    assert "Paare im Stand der Datenbank 3 (nach Schlüsselart: DOI 1, Collection-ID 2)" in text
    assert "Weggefallen 1 (nach Schlüsselart: Collection-ID 1), neu 0" in text
    assert f"<{world.ckan.source_id}.linking> | " in text
    # Nothing was written: the row is still the duplicate of the last report.
    assert world.row("linking")["state"] == "duplicate"


def test_two_finds_of_one_source_with_one_identifier_stay_apart(world: World) -> None:
    # Otto, 23.11.2026: two GovData finds with one placeholder identifier were made one.
    world.put(world.ckan, _find("a", identifier="statistik"), _find("b", identifier="statistik"))
    world.report()
    assert world.row("a")["duplicate_of"] is None and world.row("b")["duplicate_of"] is None


def test_the_report_names_the_key_of_each_pair(world: World) -> None:
    world.put(world.stac, _find("ch.example.boden", source_url="https://stac.example.org/browser/ch.example.boden"))
    world.put(world.ckan, _find("viewer", source_url="https://map.example.org/?layers=ch.example.boden"), _find("kept"))
    world.report(world.stac)
    result = world.report()
    markdown = next(path for path in result.files if path.suffix == ".md").read_text(encoding="utf-8")
    assert "`coll:stac.example.org/ch.example.boden`" in markdown


def test_classify_counts_links_that_look_like_an_interface(world: World) -> None:
    world.put(
        world.ckan,
        _find("rest", source_url="https://gis.example.org/arcgis/rest/services/boden/MapServer"),
        _find("page"),
    )
    text = classify_text(world.ckan, world.report(classify_only=True))
    assert "Link „Source“ mit Muster einer Schnittstelle (1), nach Muster:" in text
    assert "1  ArcGIS /rest/services" in text


def test_classify_shows_the_hidden_finds_per_publisher_before_and_after(world: World) -> None:
    office = "Statistisches Landesamt Musterland"
    world.put(
        world.ckan,
        _find("table", publisher=office, title="Tourismus: Gäste - Jahr", data_kind="table", category="population",
              keywords=[], spatial_text="Kanton Bern"),
        _find("map", publisher=office, title="Gemeindegrenzen"),
    )
    result = world.report(classify_only=True)
    text = classify_text(world.ckan, result)
    assert result.hidden_before[office] == 0 and result.hidden_after[office] == 1
    assert f"  {office} | 0 | 1" in text
    assert "Schwache Geo-Signale, die diese Funde vorher hielten: extent 1" in text


def test_an_entry_with_a_warning_sign_stays_out_of_the_sample_and_the_approval(world: World) -> None:
    # M5-67 plan §5: W1 for a statistics word in the title of a find the rule keeps (here by its vector data).
    world.put(world.ckan, _find("a"), _find("b", title="Bodenkarte und Bibliothekenstatistik"))
    approval, markdown = world.report().files
    document = yaml.safe_load(approval.read_text(encoding="utf-8"))
    flagged = f"{world.ckan.source_id}.b"
    assert document["excluded_entries"] == [flagged]
    assert [item["dataset_id"] for item in document["sample"]] == [f"{world.ckan.source_id}.a"]
    assert "Warnzeichen (1 Einträge bleiben draußen und warten)" in markdown.read_text(encoding="utf-8")
    world.approve(approval)
    world.publish()
    assert (world.row("a")["state"], world.row("b")["state"]) == ("published", "in_review")


def test_the_statements_of_extracted_finds_are_counted_for_new_spellings(world: World) -> None:
    from earthx.discovery.spellings import waiting_statements

    statement = f"CC BY 4.0 ({world.ckan.source_id})"
    world.put(world.ckan, _find("a", licence_statements=[statement]), _find("b", licence_statements=[statement]))
    world.put(world.ckan, _find("c", licence_statements=[statement]), state="gone")
    assert waiting_statements(world.conn)[statement] == 2


def test_a_statement_that_is_never_a_licence_does_not_wait_for_a_grade(world: World, tmp_path: Path) -> None:
    # M5-67 §23.5: such a find waits silently as no_licence and is not listed as waiting for a grade.
    from datetime import date

    from earthx.catalog.licences import LICENSES_DIR
    from earthx.discovery.spellings import run

    access = "Es gelten keine Zugriffsbeschränkungen"
    other = f"Freitext ohne Einstufung ({world.ckan.source_id})"
    world.put(world.ckan, _find("a", licence_statements=[access]), _find("b", licence_statements=[other]))
    _, waiting = run(world.conn, LICENSES_DIR, tmp_path, date(2026, 11, 25))
    assert access not in waiting and waiting[other] == 1


def test_a_title_with_a_mail_address_never_goes_into_the_report(world: World) -> None:
    world.put(world.ckan, _find("a"), _find("m", title="Bodenkarte, Fragen an hans.muster@amt.example.org"))
    approval, markdown = world.report().files
    text = approval.read_text(encoding="utf-8") + markdown.read_text(encoding="utf-8")
    assert "hans.muster" not in text and "Kontaktangabe" in text


def test_the_spellings_command_writes_its_numbers_as_json(world: World, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import json

    from earthx.discovery import spellings

    def fake_run(conn, catalogue_dir, out, day):  # type: ignore[no-untyped-def]
        return [spellings.Proposal("cc-by-4.0", "CC BY 4.0", "S2")], {"CC BY-NC-SA 4.0": 3}

    monkeypatch.setattr(spellings, "run", fake_run)
    out = tmp_path / "spellings.json"
    assert spellings.main(["--out", str(tmp_path), "--json", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == {
        "added": [{"license_ref": "cc-by-4.0", "statement": "CC BY 4.0", "rule": "S2"}],
        "waiting": [["CC BY-NC-SA 4.0", 3]],
    }
