"""``materialize`` per unit of the source against a real pgstac (M5-58, adr/0038 §3.3–§3.5).

The source is synthetic: groups of units in memory, listed and built by a test adapter, with ``HEAD`` and ``GET`` on
the units through a mocked transport behind the real ``gateway`` (CLAUDE.md: external sources only as fixtures). Its
shape is that of the MeteoSwiss grids (plan §4.1): provisional day files, final month files changed in place, an
archive whose files appear later than the month files of the same days.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import httpx
import psycopg
import pytest
from psycopg.types.json import Jsonb

from earthx.adapters import UnsupportedSource, UpstreamShapeError
from earthx.adapters.spec import ADAPTER_SPECS, UnitsMaterializer, spec_table
from earthx.catalog.pgstac import latest_item_end, load_collection, use_pgstac_search_path
from earthx.catalog.registry import (
    AdapterKind,
    ChangeDetection,
    CoverageProvider,
    DatasetConfig,
    ItemHolding,
    ItemState,
    SearchCapabilities,
    UpdateCadence,
    UpdatesInfo,
)
from earthx.catalog.schema import apply_migrations
from earthx.catalog.source_units import (
    NO_VALIDATORS,
    BuiltUnit,
    Contribution,
    SourceUnit,
    UnitListing,
    Validators,
    read_units,
)
from earthx.discovery import materialize as materialize_module
from earthx.discovery.materialize import run_materialize
from earthx.discovery.materialize_units import run_units
from earthx.gateway import Gateway, Policy
from tests.catalog.entries import COP_DEM_GLO_30, SENTINEL_2_L2A

pytestmark = pytest.mark.anyio

HOST = "files.example.invalid"
P, F = ItemState.PROVISIONAL, ItemState.FINAL

ENTRY: DatasetConfig = replace(
    SENTINEL_2_L2A,
    dataset_id="earthx-test-materialize-units",
    source=replace(
        SENTINEL_2_L2A.source,
        adapter=AdapterKind.COP_DEM_BUCKET,
        endpoint=f"https://{HOST}/listing",
        asset_hosts=(HOST,),
        item_holding=ItemHolding.MATERIALIZED,
        source_collection_id="earthx-test-materialize-units",
    ),
    coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL),
    search_filters=(),
    search_capabilities=SearchCapabilities(evaluate=False, aoi_coverage=False),
    temporal_extent=COP_DEM_GLO_30.temporal_extent,
    updates=UpdatesInfo(UpdateCadence.DAILY, (P, F), ChangeDetection.UNITS),
    limitations=("Values of the last weeks are provisional.",),
)


@dataclass
class Unit:
    """One file of the fake source: the days it holds and the asset it gives to each."""

    state: ItemState
    days: tuple[str, ...]
    body: bytes
    last_modified: str = "Wed, 12 Feb 2025 08:00:00 GMT"
    asset_key: str = "precip"
    #: What the listing says of the unit: its checksum, its ETag, or nothing (then the core asks the unit itself).
    listed: str = "checksum"
    #: Whether the unit answers with an ETag and a Last-Modified at all; without them only its hash tells.
    validators: bool = True
    #: Whether the listing names its Last-Modified beside the checksum or the ETag.
    list_modified: bool = False

    @property
    def etag(self) -> str:
        return f'"{hashlib.md5(self.body).hexdigest()}"'  # noqa: S324 — a fake ETag

    @property
    def checksum(self) -> str:
        return "1220" + hashlib.sha256(self.body).hexdigest()


@dataclass
class Source:
    groups: dict[str, dict[str, Unit]]
    requests: list[str] = field(default_factory=list)
    built: list[str] = field(default_factory=list)
    fail_build: bool = False
    #: A server that overhears If-None-Match and answers 200 with the same ETag.
    ignore_conditions: bool = False

    def href(self, key: str) -> str:
        return f"https://{HOST}/files/{key}"

    def unit(self, key: str) -> Unit:
        return next(group[key] for group in self.groups.values() if key in group)

    def group_validator(self, name: str) -> str:
        units = self.groups[name]
        text = "|".join(f"{k}:{units[k].state.value}:{units[k].etag}:{units[k].last_modified}" for k in sorted(units))
        return hashlib.sha256(text.encode()).hexdigest()

    async def list_units(
        self, config: DatasetConfig, *, gateway: Gateway, known_groups: Mapping[str, str | None]
    ) -> UnitListing:
        unchanged = frozenset(name for name in self.groups if known_groups.get(name) == self.group_validator(name))
        units: list[SourceUnit] = []
        for name, group in sorted(self.groups.items()):
            self.requests.append(f"LIST {name}")
            if name in unchanged:
                continue
            for key, unit in sorted(group.items()):
                listed = Validators(
                    etag=unit.etag if unit.listed == "etag" else unit.etag.strip('"') if unit.listed == "bare etag" else None,
                    last_modified=unit.last_modified if unit.list_modified else None,
                    checksum=unit.checksum if unit.listed == "checksum" else None,
                    content_sha256=None,
                )
                units.append(SourceUnit(key=key, group=name, href=self.href(key), state=unit.state, validators=listed))
        groups = {name: self.group_validator(name) for name in self.groups}
        return UnitListing(groups=groups, unchanged_groups=unchanged, units=tuple(units))

    async def build(self, config: DatasetConfig, *, gateway: Gateway, units: Sequence[SourceUnit]) -> tuple[BuiltUnit, ...]:
        if self.fail_build:
            raise UpstreamShapeError("the file is broken")
        made: list[BuiltUnit] = []
        for listed in units:
            unit = self.unit(listed.key)
            self.built.append(listed.key)
            contributions = tuple(
                Contribution(
                    item_id=f"{config.dataset_id}-{day}",
                    asset_key=unit.asset_key,
                    asset={
                        "href": listed.href,
                        "type": "application/x-netcdf",
                        "roles": ["data"],
                        "updated": updated(unit),
                        # Like `earthx:refs` of MeteoSwiss: the asset names the state of its file.
                        "file:checksum": unit.checksum,
                    },
                    item=skeleton(config, day),
                )
                for day in unit.days
            )
            validators = Validators(etag=unit.etag, last_modified=unit.last_modified, checksum=None, content_sha256=None)
            made.append(BuiltUnit(key=listed.key, contributions=contributions, validators=validators if unit.validators else NO_VALIDATORS))
        return tuple(made)

    def handler(self, request: httpx.Request) -> httpx.Response:
        key = request.url.path.rsplit("/", 1)[1]
        self.requests.append(f"{request.method} {key}")
        unit = self.unit(key)
        headers = {"etag": unit.etag, "last-modified": unit.last_modified} if unit.validators else {}
        if unit.validators and not self.ignore_conditions and request.headers.get("if-none-match") == unit.etag:
            return httpx.Response(304, headers=headers)
        return httpx.Response(200, content=unit.body if request.method == "GET" else b"", headers=headers)

    def gateway(self) -> Gateway:
        async def no_wait(seconds: float) -> None:
            return None

        return Gateway(
            Policy(allowed_hosts=frozenset({HOST})),
            transport=httpx.MockTransport(self.handler),
            resolve=lambda host, port: ("93.184.216.34",),
            sleep=no_wait,
        )

    def adapters(self):  # noqa: ANN201 — the table type of `adapters.spec`
        spec = replace(ADAPTER_SPECS[AdapterKind.COP_DEM_BUCKET], units=UnitsMaterializer(self.list_units, self.build))
        return spec_table(spec)


def updated(unit: Unit) -> str:
    from email.utils import parsedate_to_datetime

    return parsedate_to_datetime(unit.last_modified).isoformat().replace("+00:00", "Z")


def skeleton(config: DatasetConfig, day: str) -> dict[str, Any]:
    start = f"{day[:4]}-{day[4:6]}-{day[6:]}T06:00:00Z"
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": f"{config.dataset_id}-{day}",
        "collection": config.dataset_id,
        "bbox": [6.0, 46.0, 10.0, 48.0],
        "geometry": {"type": "Polygon", "coordinates": [[[6, 46], [10, 46], [10, 48], [6, 48], [6, 46]]]},
        "properties": {"datetime": start, "start_datetime": start, "end_datetime": start},
        "links": [],
    }


def items(conn: psycopg.Connection) -> dict[str, dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, pgstac.get_item(id, collection) FROM pgstac.items WHERE collection = %s", (ENTRY.dataset_id,)
        )
        return {item_id.rsplit("-", 1)[1]: item for item_id, item in cur.fetchall()}


def state_of(item: Mapping[str, Any]) -> str:
    return item["properties"]["earthx:state"]


@pytest.fixture
def db(conn: psycopg.Connection) -> psycopg.Connection:
    apply_migrations(conn)
    use_pgstac_search_path(conn)
    load_collection(conn, ENTRY)
    return conn


def source() -> Source:
    return Source(
        groups={
            "day-1": {"prelim-1": Unit(P, ("20261101",), b"p1")},
            "day-2": {"prelim-2": Unit(P, ("20261102",), b"p2")},
            "month-10": {"month-10": Unit(F, ("20261001", "20261002"), b"m10", listed="etag")},
        }
    )


async def run(conn: psycopg.Connection, fake: Source):  # noqa: ANN201
    async with fake.gateway() as gateway:
        return await run_units(conn, ENTRY, adapters=fake.adapters(), gateway=gateway)


class TestAFirstAndASecondRun:
    async def test_a_first_run_writes_every_day_with_its_state(self, db: psycopg.Connection) -> None:
        fake = source()
        outcome = await run(db, fake)
        assert (outcome.status, outcome.units_new, outcome.items_written) == ("loaded", 3, 4)
        stored = items(db)
        assert {day: state_of(item) for day, item in stored.items()} == {
            "20261001": "final", "20261002": "final", "20261101": "provisional", "20261102": "provisional"
        }
        asset = stored["20261101"]["assets"]["precip"]
        assert asset["earthx:state"] == "provisional"
        assert stored["20261101"]["properties"]["updated"] == "2025-02-12T08:00:00Z"
        assert set(read_units(db, ENTRY.dataset_id)) == {"prelim-1", "prelim-2", "month-10"}

    async def test_a_second_run_without_a_change_asks_only_the_groups(self, db: psycopg.Connection) -> None:
        fake = source()
        await run(db, fake)
        before = items(db)
        fake.requests.clear()
        fake.built.clear()
        outcome = await run(db, fake)
        assert outcome.status == "unchanged"
        assert (outcome.units_unchanged, outcome.items_written) == (3, 0)
        # One conditional question per group, and not one request for a unit: the same content is never fetched twice.
        assert fake.requests == ["LIST day-1", "LIST day-2", "LIST month-10"]
        assert fake.built == []
        assert items(db) == before


class TestProvisionalToFinal:
    async def test_the_final_file_replaces_the_provisional_one_under_the_same_item(self, db: psycopg.Connection) -> None:
        fake = source()
        await run(db, fake)
        fake.groups["month-11"] = {"month-11": Unit(F, ("20261101",), b"m11", last_modified="Thu, 26 Nov 2026 08:00:00 GMT")}
        outcome = await run(db, fake)
        assert (outcome.units_new, outcome.items_written, outcome.items_replaced) == (1, 1, 1)
        item = items(db)["20261101"]
        assert state_of(item) == "final"
        assert item["assets"]["precip"]["href"].endswith("/month-11")
        assert item["properties"]["updated"] == "2026-11-26T08:00:00Z"
        assert state_of(items(db)["20261102"]) == "provisional"

    async def test_a_late_provisional_file_replaces_nothing_final(self, db: psycopg.Connection) -> None:
        fake = source()
        await run(db, fake)
        before = items(db)["20261001"]
        fake.groups["day-0"] = {"prelim-0": Unit(P, ("20261001",), b"p0", last_modified="Fri, 27 Nov 2026 08:00:00 GMT")}
        outcome = await run(db, fake)
        assert outcome.units_new == 1
        assert items(db)["20261001"] == before

    async def test_a_provisional_file_that_goes_without_a_final_one_takes_its_day_along(
        self, db: psycopg.Connection
    ) -> None:
        fake = source()
        await run(db, fake)
        del fake.groups["day-2"]
        outcome = await run(db, fake)
        assert (outcome.units_gone, outcome.items_deleted) == (1, 1)
        assert "20261102" not in items(db)
        assert "prelim-2" not in read_units(db, ENTRY.dataset_id)

    async def test_the_provisional_file_that_goes_after_the_final_one_came_changes_nothing(
        self, db: psycopg.Connection
    ) -> None:
        fake = source()
        await run(db, fake)
        fake.groups["month-11"] = {"month-11": Unit(F, ("20261101",), b"m11")}
        await run(db, fake)
        before = items(db)
        del fake.groups["day-1"]
        outcome = await run(db, fake)
        assert (outcome.units_gone, outcome.items_written, outcome.items_deleted) == (1, 0, 0)
        assert items(db) == before


class TestEqualStates:
    async def test_the_younger_of_two_final_files_holds(self, db: psycopg.Connection) -> None:
        fake = source()
        await run(db, fake)
        fake.groups["archive"] = {
            "year-2026": Unit(F, ("20261001",), b"y26", last_modified="Mon, 01 Feb 2027 08:00:00 GMT")
        }
        await run(db, fake)
        assert items(db)["20261001"]["assets"]["precip"]["href"].endswith("/year-2026")
        assert items(db)["20261002"]["assets"]["precip"]["href"].endswith("/month-10")

    async def test_a_file_uploaded_again_with_the_same_content_but_younger_holds_from_then_on(
        self, db: psycopg.Connection
    ) -> None:
        """Review of PR 1: an unchanged unit whose Last-Modified grows can become the holder; its days are written."""
        fake = source()
        fake.groups["month-10"]["month-10"] = Unit(F, ("20261001", "20261002"), b"m10", list_modified=True)
        fake.groups["archive"] = {"year-2026": Unit(F, ("20261001",), b"y26", last_modified="Mon, 01 Feb 2027 08:00:00 GMT")}
        await run(db, fake)
        assert items(db)["20261001"]["assets"]["precip"]["href"].endswith("/year-2026")
        fake.groups["month-10"]["month-10"].last_modified = "Tue, 02 Feb 2027 08:00:00 GMT"
        fake.built.clear()
        outcome = await run(db, fake)
        assert outcome.units_changed == 0 and fake.built == ["month-10"]
        assert items(db)["20261001"]["assets"]["precip"]["href"].endswith("/month-10")
        del fake.groups["archive"]
        await run(db, fake)
        assert items(db)["20261001"]["assets"]["precip"]["href"].endswith("/month-10")

    async def test_when_the_holder_goes_the_next_one_is_built_anew(self, db: psycopg.Connection) -> None:
        fake = source()
        fake.groups["archive"] = {"year-2026": Unit(F, ("20261001",), b"y26", last_modified="Mon, 01 Feb 2027 08:00:00 GMT")}
        await run(db, fake)
        fake.built.clear()
        del fake.groups["archive"]
        outcome = await run(db, fake)
        assert fake.built == ["month-10"]
        assert outcome.items_written == 1
        assert items(db)["20261001"]["assets"]["precip"]["href"].endswith("/month-10")


class TestAFileChangedInPlace:
    async def test_by_its_listed_checksum_only_its_days_are_written(self, db: psycopg.Connection) -> None:
        fake = source()
        await run(db, fake)
        before = items(db)
        fake.groups["day-1"]["prelim-1"] = Unit(P, ("20261101",), b"p1 again", last_modified="Tue, 03 Nov 2026 08:00:00 GMT")
        fake.requests.clear()
        outcome = await run(db, fake)
        assert (outcome.units_changed, outcome.units_unchanged, outcome.items_written) == (1, 2, 1)
        after = items(db)
        assert after["20261101"]["properties"]["updated"] == "2026-11-03T08:00:00Z"
        assert {day: after[day] for day in after if day != "20261101"} == {d: before[d] for d in before if d != "20261101"}
        assert not any(request.startswith(("HEAD", "GET")) for request in fake.requests)

    async def test_by_its_etag_through_a_conditional_head(self, db: psycopg.Connection) -> None:
        fake = source()
        fake.groups["month-10"]["month-10"].listed = "none"
        await run(db, fake)
        # The month of the 10th is overwritten by the one of the 26th, under the same name (plan §2.2).
        fake.groups["month-10"]["month-10"] = Unit(F, ("20261001", "20261002"), b"m10 of the 26th", listed="none")
        fake.requests.clear()
        outcome = await run(db, fake)
        assert "HEAD month-10" in fake.requests
        assert (outcome.units_changed, outcome.items_written) == (1, 2)

    async def test_an_unchanged_file_answers_304_and_is_not_built(self, db: psycopg.Connection) -> None:
        fake = source()
        fake.groups["month-10"]["month-10"].listed = "none"
        await run(db, fake)
        fake.groups["month-10"]["extra"] = Unit(F, ("20261003",), b"x")  # the group changes, its old file does not
        fake.built.clear()
        fake.requests.clear()
        outcome = await run(db, fake)
        assert "HEAD month-10" in fake.requests
        assert fake.built == ["extra"]
        assert (outcome.units_new, outcome.units_changed) == (1, 0)

    async def test_a_server_that_overhears_the_condition_but_names_the_same_etag(self, db: psycopg.Connection) -> None:
        fake = source()
        fake.groups["month-10"]["month-10"].listed = "none"
        await run(db, fake)
        fake.ignore_conditions = True
        fake.groups["month-10"]["extra"] = Unit(F, ("20261003",), b"x")
        fake.built.clear()
        await run(db, fake)
        assert fake.built == ["extra"]

    async def test_an_etag_the_listing_writes_otherwise_than_the_file_is_no_change(self, db: psycopg.Connection) -> None:
        """The listing names the ETag without quotes, the file with: the next run compares listing with listing."""
        fake = source()
        fake.groups["month-10"]["month-10"].listed = "bare etag"
        await run(db, fake)
        fake.groups["month-10"]["extra"] = Unit(F, ("20261003",), b"x")
        fake.built.clear()
        await run(db, fake)
        assert fake.built == ["extra"]

    async def test_without_any_validator_its_hash_decides(self, db: psycopg.Connection) -> None:
        fake = Source(groups={"g": {"plain": Unit(F, ("20261001",), b"one", listed="none", validators=False)}})
        await run(db, fake)
        fake.groups["g"]["other"] = Unit(F, ("20261002",), b"two", listed="none", validators=False)
        fake.built.clear()
        await run(db, fake)  # the first sight of "plain" by hash: changed, its hash is kept
        fake.groups["g"]["third"] = Unit(F, ("20261003",), b"three", listed="none", validators=False)
        fake.built.clear()
        fake.requests.clear()
        outcome = await run(db, fake)
        assert "GET plain" in fake.requests
        assert "plain" not in fake.built
        assert outcome.units_new == 1


class TestRefused:
    async def test_a_group_never_seen_cannot_be_unchanged(self, db: psycopg.Connection) -> None:
        fake = source()

        async def claims_unchanged(config: DatasetConfig, *, gateway: Gateway, known_groups: Mapping[str, str | None]) -> UnitListing:
            return UnitListing(groups={"new": "v"}, unchanged_groups=frozenset({"new"}), units=())

        fake.list_units = claims_unchanged  # type: ignore[method-assign]
        with pytest.raises(UpstreamShapeError, match="never seen"):
            await run(db, fake)

    async def test_a_failed_build_writes_nothing(self, db: psycopg.Connection) -> None:
        fake = source()
        await run(db, fake)
        before, state = items(db), read_units(db, ENTRY.dataset_id)
        fake.groups["month-11"] = {"month-11": Unit(F, ("20261101",), b"m11")}
        fake.fail_build = True
        with pytest.raises(UpstreamShapeError):
            await run(db, fake)
        assert items(db) == before
        assert read_units(db, ENTRY.dataset_id) == state

    async def test_a_unit_outside_the_asset_hosts(self, db: psycopg.Connection) -> None:
        fake = source()
        fake.href = lambda key: f"https://elsewhere.example.invalid/{key}"  # type: ignore[method-assign]
        with pytest.raises(UpstreamShapeError, match="outside the asset hosts"):
            await run(db, fake)

    async def test_a_state_the_entry_does_not_name(self, db: psycopg.Connection) -> None:
        fake = source()
        entry = replace(ENTRY, updates=UpdatesInfo(UpdateCadence.DAILY, (F,), ChangeDetection.UNITS))
        async with fake.gateway() as gateway:
            with pytest.raises(UpstreamShapeError, match="state provisional"):
                await run_units(db, entry, adapters=fake.adapters(), gateway=gateway)

    async def test_an_adapter_without_units(self, db: psycopg.Connection) -> None:
        async with source().gateway() as gateway:
            with pytest.raises(UnsupportedSource, match="lists no units"):
                await run_units(db, ENTRY, adapters=ADAPTER_SPECS, gateway=gateway)

    async def test_an_entry_of_one_version_per_run(self, db: psycopg.Connection) -> None:
        whole = replace(ENTRY, updates=UpdatesInfo(UpdateCadence.NONE, (F,), ChangeDetection.WHOLE), limitations=())
        async with source().gateway() as gateway:
            with pytest.raises(UnsupportedSource, match="per run"):
                await run_units(db, whole, adapters=source().adapters(), gateway=gateway)


class TestTheEndOfTheData:
    """adr/0038 §3.6: the newest item ends the extent of a running source. Written through the async connection
    itself, inside its own transaction, which the fixture rolls back: nothing is committed to the shared database."""

    async def test_the_newest_item_ends_the_extent_of_a_running_source(self, aconn: psycopg.AsyncConnection) -> None:
        collection = {
            "type": "Collection",
            "stac_version": "1.0.0",
            "id": ENTRY.dataset_id,
            "description": "synthetic",
            "license": "other",
            "links": [],
            "extent": {"spatial": {"bbox": [[6, 46, 10, 48]]}, "temporal": {"interval": [[None, None]]}},
        }
        await aconn.execute("SELECT pgstac.create_collection(%s)", (Jsonb(collection),))
        for day in ("20261101", "20261102"):
            item = {**skeleton(ENTRY, day), "assets": {}}
            await aconn.execute("SELECT pgstac.create_item(%s)", (Jsonb(item),))
        end = await latest_item_end(aconn, ENTRY.dataset_id)
        assert end is not None and end.isoformat() == "2026-11-02T06:00:00+00:00"

    async def test_before_the_first_run_there_is_none(self, aconn: psycopg.AsyncConnection) -> None:
        assert await latest_item_end(aconn, "earthx-test-no-such-collection") is None


class TestTheCommand:
    async def test_run_materialize_takes_the_way_of_units_and_logs_the_counts(
        self, db: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = source()
        monkeypatch.setattr(materialize_module, "MATERIALIZE_SPECS", fake.adapters())
        async with fake.gateway() as gateway:
            result = await run_materialize(db, ENTRY, gateway=gateway, force=False)
        assert result.units is not None and result.units.units_new == 3
        with db.cursor() as cur:
            cur.execute(
                "SELECT status, items_written, units_new, units_unchanged FROM public.earthx_materialize_runs "
                "WHERE dataset_id = %s",
                (ENTRY.dataset_id,),
            )
            assert cur.fetchall() == [("loaded", 4, 3, 0)]
