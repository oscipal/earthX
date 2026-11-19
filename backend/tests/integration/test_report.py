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
from earthx.catalog.listing_store import withdraw
from earthx.catalog.municipalities import Municipality, write_municipalities
from earthx.catalog.registry import Maturity
from earthx.catalog.sources import CkanFilter, SourceConfig, SourceProtocol, StacFilter
from earthx.discovery.enrich import PLACE_NAMES_FILE, read_place_directory
from earthx.discovery.report import classify_text, run_report, write_files

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

    def publish(self):  # type: ignore[no-untyped-def]
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
        _find("publisher", spatial_text="Winterthur"),
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
        _find("a", spatial_text="Winterthur"),
        _find("statistics", data_kind="table", category="population", publisher="Statistisches Amt", spatial_text=None),
    )
    result = world.report(classify_only=True)
    assert world.conn.execute(
        "SELECT count(*) FROM public.earthx_listed_entry WHERE source_id = %s", (world.ckan.source_id,)
    ).fetchone() == (0,)
    text = classify_text(world.ckan, result)
    assert "Winterthur" in text and "not_geodata 1" in text


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
    terms.write_text(terms.read_text(encoding="utf-8").replace("commercial_use: true", "commercial_use: false"))
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
    write_municipalities(world.conn, [winterthur])
    try:
        directory = read_place_directory(
            PLACE_NAMES_FILE, {r.code: r.level for r in load_regions()}, [winterthur]
        )
        world.put(world.ckan, _find("w", spatial_text="Winterthur"))
        world.report(directory=directory)
        row = world.row("w")
        assert (row["extent_basis"], row["footprint"], row["regions"]) == ("place", True, ["CH", "CH-ZH"])
        assert row["content"]["extent"]["spatial"]["bbox"] == [[8.65, 47.45, 8.8, 47.55]]
    finally:
        write_municipalities(world.conn, [])


def test_classify_counts_the_geonames_ids_it_cannot_place(world: World) -> None:
    # F10 = 1: the ids are shown, the session proposes their places.
    world.put(world.ckan, _find("g", spatial_text="https://sws.geonames.org/2658434/"))
    text = classify_text(world.ckan, world.report(classify_only=True))
    assert "1  https://sws.geonames.org/2658434/" in text
