"""``GET /processing/jobs/{jobID}/results/result.zip``: the ZIP of a raster result, whole or by range (M4-11b-1).

The store is a `moto` bucket (the objects are real, the rest is the job API tests' rig). Everything is
synthetic and offline. The rule of F2 (Otto): the 60-second rule of the single links holds for every
request, a resumed download after the end of the result's life included.
"""

from __future__ import annotations

import asyncio
import io
import logging
import random
import threading
import time
import zipfile
import zlib
from typing import Any

import httpx
import pytest
import uvicorn

from earthx.api.processing_route import BUNDLE_BLOCK, MAX_BUNDLE_DOWNLOADS, DownloadSlots
from earthx.objectstore.errors import StoreUnavailable
from earthx.objectstore.results import Store, open_result_range
from tests.conftest import own_log_text
from tests.earthx.api.conftest import Rig
from tests.earthx.api.test_intake import dem_item, order
from tests.earthx.api.test_processing_route import (
    EXPORT_RESULT,
    RESULT,
    export_order,
    finish,
    placed,
    problem,
)
from tests.earthx.objectstore.conftest import BUCKET, store  # noqa: F401 - fixture

pytestmark = pytest.mark.anyio

FOLDER = "sentinel-2-c1-l2a_scale_20260601"
RASTER = random.Random(11).randbytes(5_000)
MASK = random.Random(12).randbytes(700)


@pytest.fixture
def mocked(store: Store) -> Store:  # noqa: F811
    """The moto bucket first, so that the rig's store is built inside it and reads the same objects."""
    return store


def facts(content: bytes) -> dict[str, int]:
    return {"bytes": len(content), "crc32": zlib.crc32(content)}


def put(rig: Rig, result_id: str, name: str, content: bytes) -> None:
    rig.store.s3._internal.put_object(Bucket=BUCKET, Key=f"results/{result_id}/{name}", Body=content)


async def zipped(
    rig: Rig,
    *,
    raster: bytes = RASTER,
    mask: bytes = MASK,
    meta: bool = True,
    expires: str = "7 days",
    reported: dict[str, dict[str, int]] | None = None,
    document: dict[str, Any] | None = None,
) -> tuple[str, str, str]:
    """A finished raster job whose result lies in the bucket; returns ``(job_id, result_id, url)``."""
    job_id = await placed(rig, document)
    result = dict(RESULT)
    if meta:
        result["files_meta"] = (
            reported if reported is not None else {"result.tif": facts(raster), "mask.tif": facts(mask)}
        )
    result_id = finish(rig.db, job_id, result=result, expires=expires)
    put(rig, result_id, "result.tif", raster)
    put(rig, result_id, "mask.tif", mask)
    return job_id, result_id, f"/processing/jobs/{job_id}/results/result.zip"


def opened(content: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(content))


class TestTheWholeZip:
    async def test_it_is_a_zip_with_a_folder_and_the_six_files(self, mocked: Store, rig: Rig) -> None:
        job_id, _, url = await zipped(rig)
        response = await rig.client.get(url)
        assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
        archive = opened(response.content)
        assert archive.testzip() is None
        assert archive.namelist() == [
            f"{FOLDER}/{n}"
            for n in ("result.tif", "mask.tif", "aoi.geojson", "recipe.json", "citation.bib", "ATTRIBUTION.txt")
        ]
        assert archive.read(f"{FOLDER}/result.tif") == RASTER and archive.read(f"{FOLDER}/mask.tif") == MASK
        assert all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist())
        recipe = await rig.client.get(f"/processing/jobs/{job_id}/results/recipe.json")
        assert archive.read(f"{FOLDER}/recipe.json") == recipe.content, "the file in the ZIP is the file of its link"
        assert archive.read(f"{FOLDER}/citation.bib").startswith(b"@misc{")

    async def test_the_headers_say_what_a_download_manager_needs(self, mocked: Store, rig: Rig) -> None:
        _, _, url = await zipped(rig)
        response = await rig.client.get(url)
        headers = response.headers
        assert headers["accept-ranges"] == "bytes" and headers["cache-control"] == "no-store"
        assert int(headers["content-length"]) == len(response.content)
        assert headers["content-disposition"] == f'attachment; filename="{FOLDER}.zip"'
        assert headers["etag"].startswith('"') and headers["last-modified"] == "Thu, 05 Mar 2026 10:00:00 GMT"

    async def test_the_name_of_the_file_and_of_its_entries_carry_no_area_hash_or_job(self, mocked: Store, rig: Rig) -> None:
        job_id, result_id, url = await zipped(rig)
        response = await rig.client.get(url)
        text = response.headers["content-disposition"] + "".join(opened(response.content).namelist())
        for forbidden in (job_id, result_id, "9.01", "47.01"):
            assert forbidden not in text

    async def test_the_etag_is_the_same_each_time_and_another_job_has_another(self, mocked: Store, rig: Rig) -> None:
        _, _, url = await zipped(rig)
        _, _, other = await zipped(rig)
        first = await rig.client.get(url)
        again = await rig.client.get(url)
        different = await rig.client.get(other)
        assert first.headers["etag"] == again.headers["etag"] and first.content == again.content
        assert first.headers["etag"] != different.headers["etag"], "its recipe.json is its own"

    async def test_the_results_document_names_the_zip_only_where_it_can_be_made(self, mocked: Store, rig: Rig) -> None:
        job_id, _, _ = await zipped(rig)
        document = (await rig.client.get(f"/processing/jobs/{job_id}/results")).json()
        assert list(document) == ["result", "mask", "recipe", "bundle"]
        assert document["bundle"]["href"] == f"/processing/jobs/{job_id}/results/result.zip"
        assert document["bundle"]["type"] == "application/zip"
        old, _, _ = await zipped(rig, meta=False)
        assert "bundle" not in (await rig.client.get(f"/processing/jobs/{old}/results")).json()

    async def test_the_single_links_are_still_there_and_still_redirects(self, mocked: Store, rig: Rig) -> None:
        job_id, _, _ = await zipped(rig)
        for name in ("result.tif", "mask.tif"):
            assert (await rig.client.get(f"/processing/jobs/{job_id}/results/{name}")).status_code == 303


class TestTheNameOfTheZip:
    """Otto, 14.10.2026: the day of the scenes, else the day of the run marked ``run``; the folder has the same stem."""

    async def test_a_sentinel_zip_carries_the_day_of_its_scene_in_its_name_and_in_its_folder(
        self, mocked: Store, rig: Rig
    ) -> None:
        _, _, url = await zipped(rig)  # the run ended on 2026-03-05, the scene is of 2026-06-01
        response = await rig.client.get(url)
        assert response.headers["content-disposition"] == 'attachment; filename="sentinel-2-c1-l2a_scale_20260601.zip"'
        assert {name.split("/")[0] for name in opened(response.content).namelist()} == {
            "sentinel-2-c1-l2a_scale_20260601"
        }

    async def test_a_dem_zip_is_named_by_the_day_of_its_run_marked_run(self, mocked: Store, rig: Rig) -> None:
        rig.source.items[("cop-dem-glo-30", "DEM_N47_E009")] = dem_item()
        job_id = await placed(rig, order("cop-dem-glo-30", (("DEM_N47_E009",),), ("data",)))
        result = {**RESULT, "files_meta": {"result.tif": facts(RASTER), "mask.tif": facts(MASK)}}
        result_id = finish(rig.db, job_id, result=result)
        put(rig, result_id, "result.tif", RASTER)
        put(rig, result_id, "mask.tif", MASK)
        response = await rig.client.get(f"/processing/jobs/{job_id}/results/result.zip")
        assert response.headers["content-disposition"] == 'attachment; filename="cop-dem-glo-30_scale_run20260305.zip"'
        names = opened(response.content).namelist()
        assert names[0] == "cop-dem-glo-30_scale_run20260305/result.tif" and len(names) == 6

    async def test_the_zip_and_the_single_links_of_a_job_carry_the_same_day(self, mocked: Store, rig: Rig) -> None:
        job_id, _, url = await zipped(rig)
        zip_name = (await rig.client.get(url)).headers["content-disposition"]
        recipe_name = (await rig.client.get(url.replace("result.zip", "recipe.json"))).headers["content-disposition"]
        assert "_20260601.zip" in zip_name and "_20260601_recipe.json" in recipe_name


class TestByteRanges:
    async def test_a_range_is_that_slice_of_the_whole(self, mocked: Store, rig: Rig) -> None:
        _, _, url = await zipped(rig)
        whole = (await rig.client.get(url)).content
        total = len(whole)
        for header, (first, last) in {
            "bytes=0-0": (0, 0),
            "bytes=100-4999": (100, 4999),
            "bytes=4900-5800": (4900, 5800),
            f"bytes={total - 10}-": (total - 10, total - 1),
            "bytes=-300": (total - 300, total - 1),
            f"bytes=0-{total + 500}": (0, total - 1),
        }.items():
            response = await rig.client.get(url, headers={"Range": header})
            assert response.status_code == 206, header
            assert response.content == whole[first : last + 1], header
            assert response.headers["content-range"] == f"bytes {first}-{last}/{total}"
            assert int(response.headers["content-length"]) == last - first + 1

    async def test_two_parts_make_the_whole_the_way_a_resumed_download_does(self, mocked: Store, rig: Rig) -> None:
        _, _, url = await zipped(rig)
        whole = (await rig.client.get(url)).content
        etag = (await rig.client.get(url)).headers["etag"]
        head = await rig.client.get(url, headers={"Range": "bytes=0-2999"})
        tail = await rig.client.get(url, headers={"Range": "bytes=3000-", "If-Range": etag})
        assert (head.status_code, tail.status_code) == (206, 206)
        assert head.content + tail.content == whole and opened(head.content + tail.content).testzip() is None

    async def test_a_range_behind_the_end_is_a_416_that_says_how_long_the_zip_is(self, mocked: Store, rig: Rig) -> None:
        _, _, url = await zipped(rig)
        total = len((await rig.client.get(url)).content)
        for header in (f"bytes={total}-", f"bytes={total + 9}-{total + 99}", "bytes=-0"):
            response = await rig.client.get(url, headers={"Range": header})
            problem(response, 416)
            assert response.headers["content-range"] == f"bytes */{total}"

    @pytest.mark.parametrize(
        "header", ["bytes=0-1,5-9", "bytes=abc", "bytes=9-3", "pages=1-2", "bytes=", "bytes=-", "0-5", "bytes=1-2-3"]
    )
    async def test_a_range_that_cannot_be_used_is_overheard(self, mocked: Store, rig: Rig, header: str) -> None:
        _, _, url = await zipped(rig)
        response = await rig.client.get(url, headers={"Range": header})
        assert response.status_code == 200 and "content-range" not in response.headers
        assert opened(response.content).testzip() is None

    async def test_if_range_with_the_etag_keeps_the_range_and_anything_else_even_the_date_drops_it(
        self, mocked: Store, rig: Rig
    ) -> None:
        _, _, url = await zipped(rig)
        base = await rig.client.get(url)
        etag, date = base.headers["etag"], base.headers["last-modified"]
        # The date of the run does not move when the registry's attribution or citation does, and with
        # them recipe.json and citation.bib: it is no validator for these exact bytes (review of M4-11b-1).
        for condition, status in {
            etag: 206,
            date: 200,
            '"0123456789abcdef0123456789abcdef"': 200,
            f"W/{etag}": 200,
            "Wed, 04 Mar 2026 10:00:00 GMT": 200,
            "": 200,
        }.items():
            response = await rig.client.get(url, headers={"Range": "bytes=0-9", "If-Range": condition})
            assert response.status_code == status, condition
            assert len(response.content) == (10 if status == 206 else len(base.content))

    async def test_if_range_alone_without_a_range_is_the_whole(self, mocked: Store, rig: Rig) -> None:
        _, _, url = await zipped(rig)
        etag = (await rig.client.get(url)).headers["etag"]
        response = await rig.client.get(url, headers={"If-Range": etag})
        assert response.status_code == 200 and opened(response.content).testzip() is None

    async def test_a_large_raster_goes_through_in_several_blocks_and_is_read_whole(
        self, mocked: Store, rig: Rig
    ) -> None:
        big = random.Random(5).randbytes(2 * BUNDLE_BLOCK + 123)
        _, _, url = await zipped(rig, raster=big)
        response = await rig.client.get(url)
        assert opened(response.content).read(f"{FOLDER}/result.tif") == big
        part = await rig.client.get(url, headers={"Range": f"bytes={BUNDLE_BLOCK - 5}-{BUNDLE_BLOCK + 99}"})
        assert part.content == response.content[BUNDLE_BLOCK - 5 : BUNDLE_BLOCK + 100]


class TestTheSameRulesAsTheOtherLinks:
    @pytest.mark.parametrize("expires", ["59 seconds", "10 seconds", "0 seconds", "-1 second", "-6 days"])
    async def test_a_result_with_less_than_a_minute_left_is_a_410_whole_or_by_range(
        self, mocked: Store, rig: Rig, expires: str
    ) -> None:
        _, _, url = await zipped(rig, expires=expires)
        for headers in ({}, {"Range": "bytes=0-9"}, {"Range": "bytes=100-", "If-Range": '"x"'}):
            response = await rig.client.get(url, headers=headers)
            body = problem(response, 410)
            assert body["type"] == "urn:earthx:gone" and response.headers["cache-control"] == "no-store"

    async def test_a_download_resumed_after_the_end_of_the_result_is_a_410(self, mocked: Store, rig: Rig) -> None:
        job_id, _, url = await zipped(rig, expires="5 minutes")
        first = await rig.client.get(url, headers={"Range": "bytes=0-99"})
        assert first.status_code == 206
        rig.db.execute(
            "UPDATE public.earthx_run SET expires_at = clock_timestamp() - interval '1 second' "
            "WHERE run_id = (SELECT run_id FROM public.earthx_job WHERE job_id = %s)",
            (job_id,),
        )
        problem(await rig.client.get(url, headers={"Range": "bytes=100-", "If-Range": first.headers["etag"]}), 410)

    async def test_the_zip_of_an_export_is_a_404_its_zip_is_export_zip(self, mocked: Store, rig: Rig) -> None:
        export = await placed(rig, export_order())
        finish(rig.db, export, result=EXPORT_RESULT)
        response = await rig.client.get(f"/processing/jobs/{export}/results/result.zip")
        assert problem(response, 404)["type"] == "urn:earthx:no-such-result"

    async def test_a_job_that_has_not_finished_or_failed_or_is_unknown_answers_as_the_other_links_do(
        self, mocked: Store, rig: Rig
    ) -> None:
        waiting = await placed(rig)
        failed = await placed(rig)
        finish(rig.db, failed, status="failed", kind="source_5xx")
        for job_id in (waiting, failed, "A" * 22):
            zipped_answer = await rig.client.get(f"/processing/jobs/{job_id}/results/result.zip")
            tif_answer = await rig.client.get(f"/processing/jobs/{job_id}/results/result.tif")
            assert (zipped_answer.status_code, zipped_answer.json()["type"]) == (
                tif_answer.status_code,
                tif_answer.json()["type"],
            )

    async def test_a_dismissed_job_is_gone_like_the_others(self, mocked: Store, rig: Rig) -> None:
        job_id, _, url = await zipped(rig)
        assert (await rig.client.delete(f"/processing/jobs/{job_id}")).status_code == 200
        assert problem(await rig.client.get(url), 404)["type"].endswith("no-such-job")

    async def test_the_zip_is_not_a_name_for_a_post(self, mocked: Store, rig: Rig) -> None:
        _, _, url = await zipped(rig)
        assert (await rig.client.post(url)).status_code == 405


class TestAResultFromBeforeBundlesExisted:
    """Otto, 14.10.2026: a result without ``files_meta`` is told so (``409``), not turned away as unknown."""

    REASON = "created before bundles existed; use the single links"

    @staticmethod
    def stored_result(rig: Rig, job_id: str) -> Any:
        return rig.db.execute(
            "SELECT result FROM public.earthx_run WHERE run_id = (SELECT run_id FROM public.earthx_job WHERE job_id = %s)",
            (job_id,),
        ).fetchone()[0]

    async def test_it_is_a_409_with_the_reason_and_the_single_links_still_work(self, mocked: Store, rig: Rig) -> None:
        job_id, _, url = await zipped(rig, meta=False)
        response = await rig.client.get(url)
        body = problem(response, 409)
        assert body["type"] == "urn:earthx:no-bundle" and body["title"] == "No bundle"
        assert self.REASON in body["detail"] and "result.tif" in body["detail"]
        assert response.headers["cache-control"] == "no-store" and "location" not in response.headers
        base = f"/processing/jobs/{job_id}/results"
        assert "bundle" not in (await rig.client.get(base)).json()
        for name in ("result.tif", "mask.tif"):
            assert (await rig.client.get(f"{base}/{name}")).status_code == 303
        assert (await rig.client.get(f"{base}/recipe.json")).status_code == 200

    async def test_a_range_request_gets_the_same_answer_and_nothing_is_taken_or_written(
        self, mocked: Store, rig: Rig
    ) -> None:
        job_id, _, url = await zipped(rig, meta=False)
        before = self.stored_result(rig, job_id)
        for headers in ({}, {"Range": "bytes=0-9"}, {"Range": "bytes=10-", "If-Range": '"x"'}):
            assert problem(await rig.client.get(url, headers=headers), 409)["type"] == "urn:earthx:no-bundle"
        assert rig.api.bundles.busy == 0
        assert self.stored_result(rig, job_id) == before, "api reads the report, it never writes it"
        assert "files_meta" not in self.stored_result(rig, job_id)

    @pytest.mark.parametrize(
        "meta",
        [
            {"result.tif": facts(RASTER)},
            {"result.tif": facts(RASTER), "mask.tif": {"bytes": "700", "crc32": 1}},
            {"result.tif": facts(RASTER), "mask.tif": {"bytes": -1, "crc32": 1}},
            {"result.tif": facts(RASTER), "mask.tif": {"bytes": 1, "crc32": 2**32}},
            {},
        ],
    )
    async def test_a_report_that_cannot_be_read_as_both_files_is_the_same_409(
        self, mocked: Store, rig: Rig, meta: dict[str, Any]
    ) -> None:
        _, _, url = await zipped(rig, reported=meta)
        assert problem(await rig.client.get(url), 409)["type"] == "urn:earthx:no-bundle"

    async def test_a_result_that_is_nearly_over_is_a_410_first(self, mocked: Store, rig: Rig) -> None:
        _, _, url = await zipped(rig, meta=False, expires="30 seconds")
        assert problem(await rig.client.get(url), 410)["type"] == "urn:earthx:gone"

    async def test_a_job_that_is_not_finished_or_failed_is_not_told_about_bundles(self, mocked: Store, rig: Rig) -> None:
        waiting = await placed(rig)
        failed = await placed(rig)
        finish(rig.db, failed, status="failed", kind="source_5xx")
        for job_id in (waiting, failed):
            response = await rig.client.get(f"/processing/jobs/{job_id}/results/result.zip")
            assert response.status_code != 409 and "bundles existed" not in response.text

    async def test_the_reason_names_no_job_no_result_and_no_area(self, mocked: Store, rig: Rig) -> None:
        job_id, result_id, url = await zipped(rig, meta=False)
        text = (await rig.client.get(url)).text
        for forbidden in (job_id, result_id, "9.01", "47.01", "objectstore", "earthx/results"):
            assert forbidden not in text


class TestWhenTheStoreDisagrees:
    async def test_a_raster_of_another_size_than_reported_is_a_500_that_names_nothing(
        self, mocked: Store, rig: Rig, caplog: pytest.LogCaptureFixture
    ) -> None:
        wrong = {"result.tif": facts(RASTER), "mask.tif": {**facts(MASK), "bytes": len(MASK) + 1}}
        job_id, result_id, url = await zipped(rig, reported=wrong)
        with caplog.at_level(logging.DEBUG, logger="earthx"):
            response = await rig.client.get(url)
        body = problem(response, 500)
        assert rig.api.bundles.busy == 0, "nothing was streamed, no place was taken"
        text = "\n".join(own_log_text(record) for record in caplog.records)
        assert caplog.records and "differs in size" in text
        for forbidden in (
            job_id,
            result_id,
            f"results/{result_id}",
            "earthx/results",
            "objectstore",
            "GKtest",
            "secret",
        ):
            assert forbidden not in text and forbidden not in response.text, forbidden
        assert "stored result" in body["detail"]

    async def test_a_raster_that_is_not_in_the_store_is_a_500(self, mocked: Store, rig: Rig) -> None:
        _, result_id, url = await zipped(rig)
        rig.store.s3.delete_objects([f"results/{result_id}/mask.tif"])
        problem(await rig.client.get(url), 500)

    async def test_a_store_that_does_not_answer_is_a_503_to_try_again(
        self, mocked: Store, rig: Rig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, _, url = await zipped(rig)

        def down(*args: Any) -> int:
            raise StoreUnavailable("http://objectstore:3900 GKtestaccesskey0001 refused")

        monkeypatch.setattr("earthx.api.processing_route.result_size", down)
        response = await rig.client.get(url)
        problem(response, 503)
        assert response.headers["retry-after"] == "5"
        assert "objectstore" not in response.text and "GKtest" not in response.text

    async def test_a_store_that_ends_a_file_early_breaks_the_download_and_frees_the_place(
        self, mocked: Store, rig: Rig, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _, _, url = await zipped(rig)

        class Short:
            def __init__(self, inner: Any) -> None:
                self.inner, self.sent = inner, False

            def read(self, size: int) -> bytes:
                if self.sent:
                    return b""
                self.sent = True
                return self.inner.read(min(size, 100))

            def close(self) -> None:
                self.inner.close()

        monkeypatch.setattr(
            "earthx.api.processing_route.open_result_range",
            lambda *args: Short(open_result_range(*args)),
        )
        with caplog.at_level(logging.WARNING, logger="earthx"), pytest.raises(StoreUnavailable):
            await rig.client.get(url)
        assert rig.api.bundles.busy == 0
        assert any("before the end of its report" in own_log_text(r) for r in caplog.records)


class TestThePlaces:
    async def test_the_limit_is_four_and_the_next_download_is_a_503(self, mocked: Store, rig: Rig) -> None:
        assert MAX_BUNDLE_DOWNLOADS == 4 and rig.api.bundles.limit == 4
        _, _, url = await zipped(rig)
        assert all(rig.api.bundles.take() for _ in range(4))
        response = await rig.client.get(url)
        problem(response, 503)
        assert response.headers["retry-after"] == "5" and rig.api.bundles.busy == 4, "a refusal frees nothing"
        rig.api.bundles.free()
        assert (await rig.client.get(url)).status_code == 200
        assert rig.api.bundles.busy == 3, "the place of a finished download is free again"

    async def test_places_never_go_below_none(self) -> None:
        slots = DownloadSlots(1)
        slots.free()
        assert slots.busy == 0 and slots.take() and not slots.take()

    async def test_a_client_that_leaves_frees_its_place_and_closes_the_stream(
        self, mocked: Store, rig: Rig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        big = random.Random(6).randbytes(4 * BUNDLE_BLOCK)
        _, _, url = await zipped(rig, raster=big)
        streams: list[Any] = []

        class Spy:
            def __init__(self, inner: Any) -> None:
                self.inner, self.closed = inner, False

            def read(self, size: int) -> bytes:
                return self.inner.read(size)

            def close(self) -> None:
                self.closed = True
                self.inner.close()

        def spy(*args: Any) -> Spy:
            streams.append(Spy(open_result_range(*args)))
            return streams[-1]

        monkeypatch.setattr("earthx.api.processing_route.open_result_range", spy)
        sent: list[dict[str, Any]] = []
        gone = asyncio.Event()

        async def receive() -> dict[str, Any]:
            await gone.wait()
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)
            if (
                message["type"] == "http.response.body"
                and len([m for m in sent if m["type"] == "http.response.body"]) == 3
            ):
                gone.set()
                raise OSError("the client is gone")

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": url,
            "raw_path": url.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", b"test")],
            "server": ("test", 80),
            "client": ("test", 1),
        }
        try:
            await asyncio.wait_for(rig.app(scope, receive, send), 30)
        except OSError:
            pass
        assert streams and all(stream.closed for stream in streams)
        assert rig.api.bundles.busy == 0
        assert sent[0]["type"] == "http.response.start" and sent[0]["status"] == 200


class TestWhatIsLogged:
    async def test_a_download_logs_nothing_that_names_the_job_the_area_or_the_store(
        self, mocked: Store, rig: Rig, caplog: pytest.LogCaptureFixture
    ) -> None:
        job_id, result_id, url = await zipped(rig)
        with caplog.at_level(logging.DEBUG, logger="earthx"):
            await rig.client.get(url)
            await rig.client.get(url, headers={"Range": "bytes=0-9"})
            await rig.client.get(url, headers={"Range": "bytes=99999999-"})
        assert caplog.records, "the requests are logged at all"
        text = "\n".join(own_log_text(record) for record in caplog.records)
        for forbidden in (result_id, "9.01", "47.01", "objectstore", "earthx/results", "secret", "GKtest"):
            assert forbidden not in text, forbidden


class TestUnderARealServer:
    """What an ASGI test client cannot show: `uvicorn` holds the answer to the length it was promised."""

    @staticmethod
    def serve(rig: Rig) -> tuple[uvicorn.Server, threading.Thread, str]:
        server = uvicorn.Server(uvicorn.Config(rig.app, host="127.0.0.1", port=0, log_level="warning", lifespan="off"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 15
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started, "the server did not start"
        port = server.servers[0].sockets[0].getsockname()[1]
        return server, thread, f"http://127.0.0.1:{port}"

    async def test_the_length_promised_is_the_length_sent_and_a_range_resumes_it(self, mocked: Store, rig: Rig) -> None:
        big = random.Random(8).randbytes(3 * BUNDLE_BLOCK + 17)
        _, _, path = await zipped(rig, raster=big)
        server, thread, base = self.serve(rig)
        try:
            async with httpx.AsyncClient(base_url=base, timeout=30) as client:
                async with client.stream("GET", path) as response:
                    body = b"".join([chunk async for chunk in response.aiter_raw()])
                assert response.status_code == 200 and int(response.headers["content-length"]) == len(body)
                assert "transfer-encoding" not in response.headers
                assert opened(body).testzip() is None
                cut = len(body) // 2
                part = await client.get(path, headers={"Range": f"bytes={cut}-", "If-Range": response.headers["etag"]})
                assert part.status_code == 206 and body[:cut] + part.content == body
        finally:
            server.should_exit = True
            thread.join(timeout=15)
        assert rig.api.bundles.busy == 0

    async def test_a_store_that_ends_early_never_leaves_a_shorter_zip_that_looks_whole(
        self, mocked: Store, rig: Rig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, _, path = await zipped(rig)

        class Short:
            def __init__(self, inner: Any) -> None:
                self.inner, self.left = inner, 100

            def read(self, size: int) -> bytes:
                data = self.inner.read(min(size, self.left))
                self.left -= len(data)
                return data

            def close(self) -> None:
                self.inner.close()

        monkeypatch.setattr(
            "earthx.api.processing_route.open_result_range", lambda *args: Short(open_result_range(*args))
        )
        server, thread, base = self.serve(rig)
        try:
            async with httpx.AsyncClient(base_url=base, timeout=30) as client:
                with pytest.raises(httpx.RemoteProtocolError):
                    await client.get(path)
        finally:
            server.should_exit = True
            thread.join(timeout=15)
        assert rig.api.bundles.busy == 0
