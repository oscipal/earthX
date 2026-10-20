"""The files of the ZIP of a raster result beside its rasters: the area and the attribution (M4-30).

The ZIP of a processing job holds what the crop's ZIP holds beside its data files, plus ``result.tif``
and ``mask.tif``. Everything is synthetic and offline; the store is a `moto` bucket, as in
`test_result_zip_route.py`, whose helpers these tests use.
"""

from __future__ import annotations

import json
import logging
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

import pytest
from shapely.geometry import shape
from shapely.ops import unary_union

from earthx.access import download as dl
from earthx.access.crop_rules import TEXT_FILES
from earthx.api.citation import citation_bib
from earthx.api.intake import SCENE_AOI_PROPERTIES
from earthx.api.result_zip import Layout, Member
from earthx.catalog.datasets import REGISTRY
from earthx.catalog.registry import DatasetRegistry, doi_name
from earthx.objectstore.results import Store
from earthx.processing.methods import DatasetFacts, methods_text
from tests.earthx.access.test_download import GOOD_AOI, FakeReader, path
from tests.earthx.api.conftest import Rig
from tests.earthx.api.test_intake import NEAR, PLACE, S2, SQUARE, Source, accept, export_order, order, visual_item
from tests.earthx.api.test_processing_route import (
    EXECUTION,
    EXPORT_RESULT,
    RESULT,
    TestAMosaic,
    client_for,
    finish,
    placed,
    replace_api,
)
from tests.earthx.api.test_processing_route import (
    export_order as job_export_order,
)
from tests.earthx.api.test_result_zip_route import (
    FOLDER,
    MASK,
    RASTER,
    facts,
    mocked,  # noqa: F401 - fixture
    opened,
    put,
    zipped,
)
from tests.earthx.objectstore.conftest import store  # noqa: F401 - fixture

pytestmark = pytest.mark.anyio

C1 = REGISTRY.get("sentinel-2-c1-l2a")
RASTERS = ("result.tif", "mask.tif")
FINISHED = datetime(2026, 3, 5, 10, 0, tzinfo=UTC)


def crop_files() -> list[str]:
    """The names in the crop's ZIP beside its data and mask files: what `build_download_zip` writes, not a list of ours."""
    archive = zipfile.ZipFile(
        BytesIO(
            dl.build_download_zip(
                config=C1,
                open_reader=FakeReader,
                crops=[dl.AssetCrop(asset="visual", paths=(path(asset="visual"),))],
                aoi_geometry=GOOD_AOI,
                item_ids=["ITEM1"],
                recipe_json=b"{}",
                citation_bib=b"@misc{x}\n",
                methods_text=b"A paragraph.\n",
            )
        )
    )
    own = {dl.crop_filename("visual"), dl.mask_filename("visual")}
    return [name for name in archive.namelist() if name not in own]


async def zip_of(rig: Rig, job_id: str) -> zipfile.ZipFile:
    response = await rig.client.get(f"/processing/jobs/{job_id}/results/result.zip")
    assert response.status_code == 200, response.text
    return opened(response.content)


def inside(name: str) -> str:
    return f"{FOLDER}/{name}"


def member(archive: zipfile.ZipFile, name: str) -> bytes:
    """The file ``name`` in the one folder of the archive, whatever the folder is called."""
    (path,) = [entry for entry in archive.namelist() if entry.endswith(f"/{name}")]
    return archive.read(path)


async def finished_overpass(rig: Rig, *ids: str) -> tuple[str, dict[str, Any]]:
    """A finished job for the whole scenes of one overpass, no area; returns its id and the recipe it was placed with."""
    TestAMosaic.overpass(rig, *ids)
    job_id, _, _ = await zipped(rig, document=TestAMosaic.whole(*ids))
    return job_id, stored_recipe(rig, job_id)


def stored_recipe(rig: Rig, job_id: str) -> dict[str, Any]:
    row = rig.db.execute(
        "SELECT r.body FROM public.earthx_job j JOIN public.earthx_recipe r USING (recipe_id) WHERE j.job_id = %s",
        (job_id,),
    ).fetchone()
    assert row is not None
    return row[0]


class TestTheFilesOfTheZip:
    async def test_it_holds_the_files_of_the_crops_zip_and_the_two_rasters_and_no_other(
        self, mocked: Store, rig: Rig  # noqa: F811
    ) -> None:
        job_id, _, _ = await zipped(rig)
        names = (await zip_of(rig, job_id)).namelist()
        beside = crop_files()
        assert [name.removeprefix(f"{FOLDER}/") for name in names] == [*RASTERS, *beside]

    async def test_the_attribution_is_the_text_of_the_registry_with_the_year_of_the_run(
        self, mocked: Store, rig: Rig  # noqa: F811
    ) -> None:
        job_id, _, _ = await zipped(rig)
        notice = (await zip_of(rig, job_id)).read(inside(dl.NOTICE_FILENAME)).decode("utf-8")
        assert dl.attribution_text(C1, year=2026) in notice
        assert dl.attribution_text(C1, year=2026) == "Contains modified Copernicus Sentinel data 2026"
        assert C1.title in notice and C1.license.terms is not None and C1.license.terms.url in notice
        assert "Items: S2_A" in notice and "Generated: 2026-03-05T10:00:00Z" in notice

    async def test_the_notice_describes_no_crop_file_the_zip_does_not_hold(self, mocked: Store, rig: Rig) -> None:  # noqa: F811
        job_id, _, _ = await zipped(rig)
        notice = (await zip_of(rig, job_id)).read(inside(dl.NOTICE_FILENAME)).decode("utf-8")
        assert "Mask: aoi.geojson carries the area; mask.tif is 1 inside it, 0 outside." in notice
        for crop_only in ("Assets:", "Resolution:", "each asset's own mask"):
            assert crop_only not in notice

    async def test_the_area_is_valid_geojson_and_the_area_of_the_recipe(
        self, mocked: Store, rig: Rig  # noqa: F811
    ) -> None:
        job_id, _, _ = await zipped(rig)
        archive = await zip_of(rig, job_id)
        area = json.loads(archive.read(inside(dl.AOI_FILENAME)))
        assert area == SQUARE, "no mark where the order had an area of its own"
        assert shape(area).is_valid and area["type"] == "Polygon"
        recipe = json.loads(archive.read(inside(dl.RECIPE_FILENAME)))
        assert recipe["aoi"] == area

    async def test_the_area_file_is_written_the_way_the_crop_writes_it(self, mocked: Store, rig: Rig) -> None:  # noqa: F811
        job_id, _, _ = await zipped(rig)
        crop = zipfile.ZipFile(
            BytesIO(
                dl.build_download_zip(
                    config=C1,
                    open_reader=FakeReader,
                    crops=[dl.AssetCrop(asset="visual", paths=(path(asset="visual"),))],
                    aoi_geometry=GOOD_AOI,
                    item_ids=["ITEM1"],
                )
            )
        )
        assert crop.read(dl.AOI_FILENAME).decode("utf-8") == json.dumps(GOOD_AOI)
        archive = await zip_of(rig, job_id)
        assert archive.read(inside(dl.AOI_FILENAME)).decode("utf-8") == json.dumps(SQUARE), "the same form"

    async def test_a_zip_is_the_same_bytes_each_time_so_that_its_etag_holds(
        self, mocked: Store, rig: Rig  # noqa: F811
    ) -> None:
        _, _, url = await zipped(rig)
        first, again = await rig.client.get(url), await rig.client.get(url)
        assert first.content == again.content and first.headers["etag"] == again.headers["etag"]


class TestTheMethodsText:
    """M4-19a: ``methods.txt`` beside ``recipe.json``, in the ZIP and as a link, the same text."""

    async def test_the_zip_lays_the_text_files_out_in_the_order_of_the_definition(
        self, mocked: Store, rig: Rig  # noqa: F811
    ) -> None:
        job_id, _, _ = await zipped(rig)
        names = [name.removeprefix(f"{FOLDER}/") for name in (await zip_of(rig, job_id)).namelist()]
        assert [name for name in names if name in TEXT_FILES] == list(TEXT_FILES)

    async def test_the_link_serves_the_text_of_the_zip_as_text(self, mocked: Store, rig: Rig) -> None:  # noqa: F811
        job_id, _, _ = await zipped(rig)
        response = await rig.client.get(f"/processing/jobs/{job_id}/results/methods.txt")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert response.headers["content-disposition"].endswith('_methods.txt"')
        assert response.content == (await zip_of(rig, job_id)).read(inside(dl.METHODS_FILENAME))

    async def test_it_is_written_from_the_recipe_the_job_serves(self, mocked: Store, rig: Rig) -> None:  # noqa: F811
        job_id, _, _ = await zipped(rig)
        recipe = await rig.client.get(f"/processing/jobs/{job_id}/results/recipe.json")
        text = (await rig.client.get(f"/processing/jobs/{job_id}/results/methods.txt")).text
        assert text == methods_text(recipe.content, dataset=DatasetFacts.of(C1), operators=rig.api.operators)
        assert text.startswith(f"The dataset {C1.title} (sentinel-2-c1-l2a, doi:{doi_name(C1.doi)})")
        assert "Contains modified Copernicus Sentinel data 2026" in text

    async def test_it_names_no_job_result_recipe_hash_address_or_coordinate(
        self, mocked: Store, rig: Rig  # noqa: F811
    ) -> None:
        job_id, result_id, _ = await zipped(rig)
        stored = stored_recipe(rig, job_id)
        text = (await rig.client.get(f"/processing/jobs/{job_id}/results/methods.txt")).text
        header = (await rig.client.get(f"/processing/jobs/{job_id}/results/methods.txt")).headers["content-disposition"]
        for forbidden in (job_id, result_id, stored["recipe_id"], "9.01", "47.01", "https://", "c1:"):
            assert forbidden not in text + header

    async def test_two_requests_give_the_same_bytes(self, mocked: Store, rig: Rig) -> None:  # noqa: F811
        job_id, _, _ = await zipped(rig)
        url = f"/processing/jobs/{job_id}/results/methods.txt"
        assert (await rig.client.get(url)).content == (await rig.client.get(url)).content

    async def test_a_dataset_the_registry_no_longer_knows_is_named_by_its_identifier(
        self, mocked: Store, rig: Rig  # noqa: F811
    ) -> None:
        job_id, _, _ = await zipped(rig)
        api = replace_api(rig.api, registry=DatasetRegistry((REGISTRY.get("cop-dem-glo-30"),)))
        async with client_for(api) as client:
            response = await client.get(f"/processing/jobs/{job_id}/results/methods.txt")
        assert response.status_code == 200 and response.text.startswith("The dataset sentinel-2-c1-l2a was used:")

    async def test_an_export_has_it_too(self, rig: Rig) -> None:
        job_id = await placed(rig, job_export_order())
        finish(rig.db, job_id, result=EXPORT_RESULT)
        response = await rig.client.get(f"/processing/jobs/{job_id}/results/methods.txt")
        assert response.status_code == 200
        assert "cropped to the bounding box" in response.text

    async def test_an_expired_result_is_a_410_and_a_dismissed_job_a_404(self, mocked: Store, rig: Rig) -> None:  # noqa: F811
        job_id, _, _ = await zipped(rig, expires="30 seconds")
        assert (await rig.client.get(f"/processing/jobs/{job_id}/results/methods.txt")).status_code == 410
        other, _, _ = await zipped(rig)
        assert (await rig.client.delete(f"/processing/jobs/{other}")).status_code in (200, 204)
        assert (await rig.client.get(f"/processing/jobs/{other}/results/methods.txt")).status_code == 404

    async def test_a_job_that_does_not_exist_is_a_404(self, rig: Rig) -> None:
        assert (await rig.client.get(f"/processing/jobs/{'x' * 22}/results/methods.txt")).status_code == 404

    async def test_the_attachments_of_an_export_hold_the_facts_of_its_dataset(self, rig: Rig) -> None:
        await placed(rig, job_export_order())
        (attachments,) = rig.db.execute("SELECT attachments FROM public.earthx_run").fetchone()  # type: ignore[misc]
        assert attachments["dataset"] == {"title": C1.title, "doi": doi_name(C1.doi)}
        assert set(attachments["files"]) == {dl.NOTICE_FILENAME, dl.CITATION_FILENAME, dl.AOI_FILENAME}, (
            "the text is written by the worker, not stored"
        )


class TestWholeScenes:
    async def test_without_an_area_the_file_is_the_union_of_the_footprints_and_says_so(
        self, mocked: Store, rig: Rig  # noqa: F811
    ) -> None:
        job_id, recipe = await finished_overpass(rig, "S2_A", "S2_B", "S2_C")
        archive = await zip_of(rig, job_id)
        area = json.loads(member(archive, dl.AOI_FILENAME))
        assert area["properties"] == SCENE_AOI_PROPERTIES
        assert {key: area[key] for key in ("type", "coordinates")} == recipe["aoi"], "the area of the recipe"
        footprints = [
            shape(rig.source.items[("sentinel-2-c1-l2a", item)]["geometry"]) for item in ("S2_A", "S2_B", "S2_C")
        ]
        assert shape(area).equals(unary_union(footprints))

    async def test_the_notice_names_all_the_scenes_and_the_recipe_has_no_mark(
        self, mocked: Store, rig: Rig  # noqa: F811
    ) -> None:
        job_id, recipe = await finished_overpass(rig, "S2_A", "S2_B", "S2_C")
        archive = await zip_of(rig, job_id)
        notice = member(archive, dl.NOTICE_FILENAME).decode("utf-8")
        assert "Items: S2_A, S2_B, S2_C" in notice
        assert "properties" not in json.loads(member(archive, dl.RECIPE_FILENAME))["aoi"]
        assert "properties" not in recipe["aoi"], "the recipe, and with it the hash, is not changed by the mark"

    async def test_an_order_with_an_area_of_its_own_is_not_marked_even_when_it_covers_a_whole_scene(
        self, mocked: Store, rig: Rig  # noqa: F811
    ) -> None:
        TestAMosaic.overpass(rig, "S2_A")
        job_id, _, _ = await zipped(rig, document=order(groups=(("S2_A",),), aoi=_box(NEAR)))
        area = json.loads(member(await zip_of(rig, job_id), dl.AOI_FILENAME))
        assert "properties" not in area and area == _box(NEAR)

    async def test_a_job_from_before_the_mark_has_the_area_and_no_mark(self, mocked: Store, rig: Rig) -> None:  # noqa: F811
        job_id, _ = await finished_overpass(rig, "S2_A", "S2_B", "S2_C")
        rig.db.execute("UPDATE public.earthx_job SET scene_aoi = false WHERE job_id = %s", (job_id,))
        area = json.loads(member(await zip_of(rig, job_id), dl.AOI_FILENAME))
        assert "properties" not in area and area["type"] == "Polygon"


def _box(bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    west, south, east, north = bbox
    return {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]}


class TestTheOriginOfAPlaceSearchArea:
    """M4-30 (Otto, 20.10.2026): the line and the properties of the export, from the one function, only with an origin."""

    LINE = "AOI geometry: © OpenStreetMap contributors, ODbL-1.0 (via Nominatim)"

    @staticmethod
    async def job(rig: Rig, *, origin: bool) -> str:
        """A job placed with or without the origin of its area; the run behind it is finished and in the bucket."""
        inputs: dict[str, Any] = {"recipe": order()}
        if origin:
            inputs["aoiProvenance"] = PLACE
        response = await rig.client.post(EXECUTION, json={"inputs": inputs})
        assert response.status_code == 201, response.text
        job_id = response.json()["jobID"]
        result = {**RESULT, "files_meta": {"result.tif": facts(RASTER), "mask.tif": facts(MASK)}}
        result_id = finish(rig.db, job_id, result=result)
        put(rig, result_id, "result.tif", RASTER)
        put(rig, result_id, "mask.tif", MASK)
        return job_id

    async def test_with_an_origin_the_notice_names_it_and_the_area_carries_it(
        self, mocked: Store, rig: Rig  # noqa: F811
    ) -> None:
        archive = await zip_of(rig, await self.job(rig, origin=True))
        assert self.LINE in member(archive, dl.NOTICE_FILENAME).decode("utf-8")
        area = json.loads(member(archive, dl.AOI_FILENAME))
        assert area["properties"] == PLACE
        assert {key: area[key] for key in ("type", "coordinates")} == SQUARE
        assert "properties" not in json.loads(member(archive, dl.RECIPE_FILENAME))["aoi"]

    async def test_it_is_the_line_and_the_properties_an_export_writes(self, mocked: Store, rig: Rig) -> None:  # noqa: F811
        source = Source((S2, visual_item("S2_A")))
        exported = await accept(export_order(), source, aoi_provenance=PLACE)
        assert exported.attachments is not None
        archive = await zip_of(rig, await self.job(rig, origin=True))
        export_notice = exported.attachments.files[dl.NOTICE_FILENAME]
        job_notice = member(archive, dl.NOTICE_FILENAME).decode("utf-8")
        line = next(line for line in export_notice.split("\n\n") if line.startswith("AOI geometry:"))
        assert line in job_notice.split("\n\n")
        assert json.loads(exported.attachments.files[dl.AOI_FILENAME])["properties"] == json.loads(
            member(archive, dl.AOI_FILENAME)
        )["properties"]

    async def test_without_an_origin_neither_the_line_nor_the_properties_are_there(
        self, mocked: Store, rig: Rig  # noqa: F811
    ) -> None:
        archive = await zip_of(rig, await self.job(rig, origin=False))
        assert "AOI geometry" not in member(archive, dl.NOTICE_FILENAME).decode("utf-8")
        assert member(archive, dl.AOI_FILENAME).decode("utf-8") == json.dumps(SQUARE)

    async def test_two_jobs_on_one_run_each_get_their_own_attribution(self, mocked: Store, rig: Rig) -> None:  # noqa: F811
        with_origin = await self.job(rig, origin=True)
        # The same order without the origin attaches to the finished run of the first; nothing is put again.
        response = await rig.client.post(EXECUTION, json={"inputs": {"recipe": order()}})
        without = response.json()["jobID"]
        assert rig.db.execute("SELECT count(*) FROM public.earthx_run").fetchone() == (1,)
        first, second = await zip_of(rig, with_origin), await zip_of(rig, without)
        assert self.LINE in member(first, dl.NOTICE_FILENAME).decode("utf-8")
        assert "AOI geometry" not in member(second, dl.NOTICE_FILENAME).decode("utf-8")
        assert "properties" in json.loads(member(first, dl.AOI_FILENAME))
        assert "properties" not in json.loads(member(second, dl.AOI_FILENAME))

    async def test_the_etag_differs_with_and_without_the_origin_and_holds_for_each(
        self, mocked: Store, rig: Rig  # noqa: F811
    ) -> None:
        with_origin = await self.job(rig, origin=True)
        without = (await rig.client.post(EXECUTION, json={"inputs": {"recipe": order()}})).json()["jobID"]
        etags = {}
        for name, job_id in (("with", with_origin), ("without", without)):
            url = f"/processing/jobs/{job_id}/results/result.zip"
            first, again = await rig.client.get(url), await rig.client.get(url)
            assert first.headers["etag"] == again.headers["etag"] and first.content == again.content
            etags[name] = first.headers["etag"]
        assert etags["with"] != etags["without"]


class TestAnUnfinishedDownload:
    """The content changed, so the ETag did: a download begun before M4-30 starts again (RFC 9110 §13.1.5)."""

    async def test_a_range_resumed_with_the_etag_of_the_old_four_files_is_the_whole_new_zip(
        self, mocked: Store, rig: Rig  # noqa: F811
    ) -> None:
        job_id, _, url = await zipped(rig)
        new = await rig.client.get(url)
        archive = opened(new.content)
        before = [
            Member.of_bytes(inside(name), archive.read(inside(name))) for name in ("recipe.json", "citation.bib")
        ]
        old = Layout(
            [
                Member.of_bytes(inside("result.tif"), RASTER),
                Member.of_bytes(inside("mask.tif"), MASK),
                *before,
            ],
            modified=FINISHED,
        )
        assert old.etag != new.headers["etag"], "another content, another validator"
        resumed = await rig.client.get(url, headers={"Range": "bytes=100-", "If-Range": old.etag})
        assert resumed.status_code == 200 and "content-range" not in resumed.headers
        assert resumed.content == new.content and resumed.headers["etag"] == new.headers["etag"]
        assert opened(resumed.content).testzip() is None

    async def test_the_new_etag_still_resumes(self, mocked: Store, rig: Rig) -> None:  # noqa: F811
        _, _, url = await zipped(rig)
        whole = await rig.client.get(url)
        resumed = await rig.client.get(url, headers={"Range": "bytes=100-", "If-Range": whole.headers["etag"]})
        assert resumed.status_code == 206 and resumed.content == whole.content[100:]


class TestWithoutTheRegistry:
    async def test_a_dataset_the_registry_no_longer_knows_leaves_out_the_citation_and_the_notice_only(
        self, mocked: Store, rig: Rig  # noqa: F811
    ) -> None:
        job_id, _, _ = await zipped(rig)
        api = replace_api(rig.api, registry=DatasetRegistry((REGISTRY.get("cop-dem-glo-30"),)))
        async with client_for(api) as client:
            response = await client.get(f"/processing/jobs/{job_id}/results/result.zip")
        assert response.status_code == 200
        names = [name.removeprefix(f"{FOLDER}/") for name in opened(response.content).namelist()]
        assert names == [*RASTERS, dl.AOI_FILENAME, dl.RECIPE_FILENAME, dl.METHODS_FILENAME]


class TestNothingNamesWhatItShouldNot:
    async def test_the_download_logs_no_area_and_no_attribution(
        self, mocked: Store, rig: Rig, caplog: pytest.LogCaptureFixture  # noqa: F811
    ) -> None:
        _, _, url = await zipped(rig)
        with caplog.at_level(logging.DEBUG):
            await rig.client.get(url)
        text = "".join(record.getMessage() for record in caplog.records)
        for forbidden in ("9.01", "47.01", "Copernicus", "aoi.geojson"):
            assert forbidden not in text


class TestNoSecondVersion:
    """The synchronous crop and the export keep their bytes (M4-30 §4): the shared parts only gained optional arguments."""

    class Frozen(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return FINISHED.astimezone(tz) if tz else FINISHED.replace(tzinfo=None)

    def test_a_notice_without_the_new_arguments_is_the_one_it_always_was(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(dl, "datetime", self.Frozen)
        plain = dl.build_notice_text(C1, item_ids=["A"], assets=["red"])
        assert plain == dl.build_notice_text(C1, item_ids=["A"], assets=["red"], at=FINISHED, raster_result=False)
        assert "Assets: red (" in plain and "Resolution: native" in plain and "each asset's own mask" in plain
        assert plain.endswith("Generated: 2026-03-05T10:00:00Z\n")

    async def test_the_attachments_of_an_export_are_what_they_were_before_the_files_were_shared(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Built here the way ``export_attachments`` did before M4-30: the notice, the citation and the area."""
        monkeypatch.setattr(dl, "datetime", self.Frozen)
        source = Source((S2, visual_item("S2_A")), (S2, visual_item("S2_B")), (S2, visual_item("S2_C")))
        accepted = await accept(export_order((("S2_A", "S2_B"), ("S2_C",))), source, aoi_provenance=PLACE)
        assert accepted.attachments is not None
        aoi = {**SQUARE, "properties": PLACE}
        expected = {
            dl.NOTICE_FILENAME: dl.build_notice_text(
                C1,
                item_ids=["S2_A", "S2_B", "S2_C"],
                assets=["visual"],
                group_item_ids=[["S2_A", "S2_B"], ["S2_C"]],
                skipped_item_ids=[],
                aoi_geometry=aoi,
            ),
            dl.CITATION_FILENAME: citation_bib(C1, downloaded=datetime.now(UTC).date()).decode("utf-8"),
            dl.AOI_FILENAME: json.dumps(aoi),
        }
        got = accepted.attachments.files
        assert got[dl.NOTICE_FILENAME] == expected[dl.NOTICE_FILENAME]
        assert got[dl.AOI_FILENAME] == expected[dl.AOI_FILENAME]
        assert got[dl.CITATION_FILENAME].startswith("@misc{sentinel-2-c1-l2a,")
        assert set(got) == set(expected)
