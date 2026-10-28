"""``POST /processing/bundles`` and ``GET /processing/bundles/{id}``: "Download all (ZIP)" of a batch (UI-01e; plan §6.12).

The store is a `moto` bucket, the queue database a real one; everything is synthetic and offline. The ZIP of
a bundle holds, per part, what ``result.zip`` of that job holds, so these tests compare with the job's own
ZIP and links rather than restate their content.
"""

from __future__ import annotations

import io
import json
import logging
import random
import zipfile
from typing import Any

import pytest

from earthx.api.processing_route import MAX_BODY_BYTES, MAX_BUNDLE_BYTES, MAX_BUNDLE_DOWNLOADS
from earthx.jobs import bundles
from earthx.jobs.cleanup import cleanup
from earthx.objectstore.results import Store
from tests.conftest import own_log_text
from tests.earthx.api.conftest import Rig
from tests.earthx.api.test_intake import order
from tests.earthx.api.test_processing_route import EXPORT_RESULT, export_order, finish, placed, problem
from tests.earthx.api.test_result_zip_route import put, zipped

from ..objectstore.conftest import store  # noqa: F401 - fixture

pytestmark = pytest.mark.anyio

PATH = "/processing/bundles"
DAY = "20260601"


@pytest.fixture
def mocked(store: Store) -> Store:  # noqa: F811
    """The moto bucket first, so that the rig's store is built inside it and reads the same objects."""
    return store


def scaled(factor: float) -> dict[str, Any]:
    """An order of its own: another factor is another recipe, so another run and another result."""
    return order(steps=[{"op": "scale", "op_version": 1, "params": {"factor": factor}}])


def raster(n: int) -> bytes:
    return random.Random(n).randbytes(400 + 10 * n)


async def part(rig: Rig, n: int, **kwargs: Any) -> str:
    """A finished raster job whose files lie in the bucket and differ from those of every other ``n``."""
    job_id, _, _ = await zipped(rig, raster=raster(n), mask=raster(n + 100), document=scaled(2.0 + n), **kwargs)
    return job_id


async def make(rig: Rig, *job_ids: str) -> str:
    """The address of a bundle of ``job_ids``."""
    response = await rig.client.post(PATH, json={"jobs": list(job_ids)})
    assert response.status_code == 201, response.text
    return response.json()["href"]


def rows(rig: Rig) -> int:
    row = rig.db.execute("SELECT count(*) FROM public.earthx_bundle").fetchone()
    assert row is not None
    return row[0]


def opened(content: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(content))


class TestCreate:
    async def test_the_answer_is_an_address_and_an_expiry_and_nothing_of_the_jobs(self, mocked: Store, rig: Rig) -> None:
        one, two = await part(rig, 1), await part(rig, 2)
        response = await rig.client.post(PATH, json={"jobs": [one, two]})
        assert response.status_code == 201 and response.headers["cache-control"] == "no-store"
        document = response.json()
        assert set(document) == {"href", "expires"}
        prefix = f"{PATH}/"
        assert document["href"].startswith(prefix) and bundles.is_bundle_id(document["href"].removeprefix(prefix))
        assert response.headers["location"] == document["href"]
        assert one not in response.text and two not in response.text

    async def test_two_posts_of_one_list_are_two_identifiers_and_the_same_zip(self, mocked: Store, rig: Rig) -> None:
        one, two = await part(rig, 1), await part(rig, 2)
        first, second = await make(rig, one, two), await make(rig, one, two)
        assert first != second
        a, b = await rig.client.get(first), await rig.client.get(second)
        assert a.content == b.content and a.headers["etag"] == b.headers["etag"]

    async def test_the_term_is_the_earliest_end_of_the_parts_that_went_in(self, mocked: Store, rig: Rig) -> None:
        early, late = await part(rig, 1, expires="2 days"), await part(rig, 2, expires="5 days")
        failed = await placed(rig, scaled(9.0))
        finish(rig.db, failed, status="failed", kind="source_5xx", expires="1 day")
        await make(rig, late, early, failed)
        stored, ends = rig.db.execute(
            "SELECT expires_at, (SELECT min(expires_at) FROM public.earthx_run WHERE status = 'successful') "
            "FROM public.earthx_bundle"
        ).fetchone() or (None, None)
        assert stored == ends, "the failed job, which ends sooner, does not shorten it"

    async def test_the_row_holds_the_ids_and_the_times_and_nothing_else(self, mocked: Store, rig: Rig) -> None:
        one, two = await part(rig, 1), await part(rig, 2)
        await make(rig, one, two)
        columns = [c[0] for c in rig.db.execute("SELECT * FROM public.earthx_bundle LIMIT 0").description or []]
        assert columns == ["bundle_id", "job_ids", "created_at", "expires_at"]
        row = rig.db.execute("SELECT job_ids FROM public.earthx_bundle").fetchone()
        assert row is not None and row[0] == [one, two]

    async def test_the_identifier_is_random_and_not_derived_from_the_jobs(self, mocked: Store, rig: Rig) -> None:
        one = await part(rig, 1)
        ids = {(await make(rig, one)).removeprefix(f"{PATH}/") for _ in range(10)}
        assert len(ids) == 10 and not ids & {one}

    async def test_a_list_of_one_is_a_bundle(self, mocked: Store, rig: Rig) -> None:
        job_id = await part(rig, 1)
        response = await rig.client.get(await make(rig, job_id))
        single = await rig.client.get(f"/processing/jobs/{job_id}/results/result.zip")
        assert response.status_code == 200
        assert len(opened(response.content).namelist()) == len(opened(single.content).namelist())


class TestWhatIsRefused:
    @pytest.mark.parametrize("payload", [[], "text", {}, {"jobs": ["A" * 22], "other": 1}, {"job": ["A" * 22]}])
    async def test_a_body_that_is_not_a_list_of_jobs_is_a_400(self, rig: Rig, payload: Any) -> None:
        response = await rig.client.post(PATH, json=payload)
        assert response.status_code == 400 and rows(rig) == 0

    async def test_text_that_is_not_json_or_has_a_duplicate_key_is_a_400(self, rig: Rig) -> None:
        headers = {"content-type": "application/json"}
        for raw in (b"{", b'{"jobs": [], "jobs": []}', b'{"jobs": NaN}'):
            assert (await rig.client.post(PATH, content=raw, headers=headers)).status_code == 400
        assert rows(rig) == 0

    async def test_another_media_type_is_a_415_and_a_body_over_the_cap_a_413(self, rig: Rig) -> None:
        assert (await rig.client.post(PATH, content=b"{}", headers={"content-type": "text/plain"})).status_code == 415
        big = b'{"jobs": "' + b"x" * MAX_BODY_BYTES + b'"}'
        assert (await rig.client.post(PATH, content=big, headers={"content-type": "application/json"})).status_code == 413

    @pytest.mark.parametrize(
        "jobs",
        [
            None,
            "A" * 22,
            [],
            ["A" * 21],
            ["A" * 23],
            ["A" * 21 + "%"],
            ["https://example.test/processing/jobs/" + "A" * 22],
            ["A" * 22, "A" * 22],
            [1],
            [None],
            [["A" * 22]],
            ["A" * 22 + "\n"],
            [f"{i:022d}" for i in range(26)],
        ],
    )
    async def test_a_list_that_is_not_1_to_25_distinct_job_identifiers_is_a_422(self, rig: Rig, jobs: Any) -> None:
        response = await rig.client.post(PATH, json={"jobs": jobs})
        assert response.status_code == 422 and rows(rig) == 0
        problem(response)

    async def test_twenty_five_is_the_most(self, mocked: Store, rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
        assert bundles.MAX_PARTS == 25 and MAX_BUNDLE_BYTES == 25_000_000_000
        monkeypatch.setattr(bundles, "MAX_PARTS", 2)
        one, two, three = await part(rig, 1), await part(rig, 2), await part(rig, 3)
        assert (await rig.client.post(PATH, json={"jobs": [one, two, three]})).status_code == 422
        assert (await rig.client.post(PATH, json={"jobs": [one, two]})).status_code == 201

    async def test_an_export_cannot_go_into_a_bundle(self, mocked: Store, rig: Rig) -> None:
        one = await part(rig, 1)
        export = await placed(rig, export_order())
        finish(rig.db, export, result=EXPORT_RESULT)
        response = await rig.client.post(PATH, json={"jobs": [one, export]})
        assert response.status_code == 422 and rows(rig) == 0

    async def test_a_result_without_measured_files_cannot_go_into_a_bundle(self, mocked: Store, rig: Rig) -> None:
        old, _, _ = await zipped(rig, meta=False, document=scaled(7.0))
        assert (await rig.client.post(PATH, json={"jobs": [old]})).status_code == 422

    async def test_jobs_that_have_expired_or_are_not_there_are_a_410_and_nothing_is_made(
        self, mocked: Store, rig: Rig
    ) -> None:
        job_id, _, _ = await zipped(rig, document=scaled(2.0), expires="30 seconds")  # inside the last minute
        response = await rig.client.post(PATH, json={"jobs": [job_id, "A" * 22]})
        assert problem(response, 410)["type"] == "urn:earthx:gone" and rows(rig) == 0

    async def test_jobs_that_have_not_finished_or_have_failed_are_a_409(self, mocked: Store, rig: Rig) -> None:
        running = await placed(rig, scaled(3.0))
        failed = await placed(rig, scaled(4.0))
        finish(rig.db, failed, status="failed", kind="source_5xx")
        response = await rig.client.post(PATH, json={"jobs": [running, failed, "A" * 22]})
        assert problem(response, 409)["type"] == "urn:earthx:no-bundle" and rows(rig) == 0

    async def test_rasters_over_the_limit_are_a_413_with_the_sum(self, mocked: Store, rig: Rig) -> None:
        big = {"result.tif": {"bytes": MAX_BUNDLE_BYTES // 2, "crc32": 0}, "mask.tif": {"bytes": 1000, "crc32": 0}}
        one, _, _ = await zipped(rig, reported=big, document=scaled(2.0))
        two, _, _ = await zipped(rig, reported=big, document=scaled(3.0))
        response = await rig.client.post(PATH, json={"jobs": [one, two]})
        assert problem(response, 413)["detail"].count(str(MAX_BUNDLE_BYTES + 2000)) == 1 and rows(rig) == 0
        assert (await rig.client.post(PATH, json={"jobs": [one]})).status_code == 201

    async def test_the_queue_database_missing_is_a_503(self, rig: Rig) -> None:
        rig.app.state.earthx_job_api = None
        assert (await rig.client.post(PATH, json={"jobs": ["A" * 22]})).status_code == 503


class TestTheZip:
    async def test_it_holds_per_part_what_the_result_zip_of_the_job_holds(self, mocked: Store, rig: Rig) -> None:
        one, two = await part(rig, 1), await part(rig, 2)
        response = await rig.client.get(await make(rig, one, two))
        assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
        archive = opened(response.content)
        assert archive.testzip() is None
        name = "sentinel-2-c1-l2a_scale_" + DAY
        folder = f"{name}_batch-2"
        assert response.headers["content-disposition"] == f'attachment; filename="{folder}.zip"'
        for number, job_id in ((1, one), (2, two)):
            single = opened((await rig.client.get(f"/processing/jobs/{job_id}/results/result.zip")).content)
            inside = f"{folder}/{number:02d}_{name}/"
            assert archive.namelist().count(inside + "result.tif") == 1
            for entry in single.infolist():
                member = entry.filename.split("/", 1)[1]
                assert archive.read(inside + member) == single.read(entry.filename), member
        assert not any(n.endswith("MISSING.txt") for n in archive.namelist()), "nothing is missing"
        assert archive.read(f"{folder}/01_{name}/result.tif") == raster(1)
        assert archive.read(f"{folder}/02_{name}/mask.tif") == raster(102)

    async def test_two_parts_with_one_stem_have_two_folders(self, mocked: Store, rig: Rig) -> None:
        one, two = await part(rig, 1), await part(rig, 2)
        names = opened((await rig.client.get(await make(rig, one, two))).content).namelist()
        assert len({n.split("/")[1] for n in names}) == 2 and {n.split("/")[1][:3] for n in names} == {"01_", "02_"}

    async def test_the_headers_say_what_a_download_manager_needs(self, mocked: Store, rig: Rig) -> None:
        response = await rig.client.get(await make(rig, await part(rig, 1), await part(rig, 2)))
        headers = response.headers
        assert headers["accept-ranges"] == "bytes" and headers["cache-control"] == "no-store"
        assert int(headers["content-length"]) == len(response.content)
        assert headers["etag"].startswith('"') and headers["last-modified"] == "Thu, 05 Mar 2026 10:00:00 GMT"

    async def test_the_order_of_the_list_is_the_order_of_the_zip_and_changes_the_etag(
        self, mocked: Store, rig: Rig
    ) -> None:
        one, two = await part(rig, 1), await part(rig, 2)
        forward = await rig.client.get(await make(rig, one, two))
        backward = await rig.client.get(await make(rig, two, one))
        assert forward.headers["etag"] != backward.headers["etag"]
        name = f"sentinel-2-c1-l2a_scale_{DAY}"
        assert opened(backward.content).read(f"{name}_batch-2/01_{name}/result.tif") == raster(2)

    async def test_the_name_and_the_entries_carry_no_job_result_or_area(self, mocked: Store, rig: Rig) -> None:
        one, two = await part(rig, 1), await part(rig, 2)
        results = [r[0] for r in rig.db.execute("SELECT result_id FROM public.earthx_run")]
        href = await make(rig, one, two)
        response = await rig.client.get(href)
        text = response.headers["content-disposition"] + "".join(opened(response.content).namelist())
        for forbidden in (one, two, href.removeprefix(f"{PATH}/"), "9.01", "47.01", *results):
            assert forbidden not in text


class TestWhatIsMissing:
    """A part that has expired, failed or is not finished is not in the ZIP; ``MISSING.txt`` says which."""

    async def lines(self, rig: Rig, href: str) -> list[str]:
        response = await rig.client.get(href)
        assert response.status_code == 200, response.text
        archive = opened(response.content)
        assert archive.testzip() is None
        (name,) = [n for n in archive.namelist() if n.endswith("/MISSING.txt")]
        assert name.count("/") == 1, "beside the folders of the parts"
        return archive.read(name).decode().splitlines()

    async def test_each_missing_part_is_one_line_with_its_number_and_the_reason(self, mocked: Store, rig: Rig) -> None:
        good, expiring, failing, running, gone = [await part(rig, n) for n in (1, 2, 3, 4, 5)]
        href = await make(rig, good, expiring, failing, running, gone)
        rig.db.execute(
            "UPDATE public.earthx_run SET expires_at = clock_timestamp() + interval '30 seconds' "
            "WHERE run_id = (SELECT run_id FROM public.earthx_job WHERE job_id = %s)",
            (expiring,),
        )
        for job_id, status in ((failing, "failed"), (running, "running")):
            rig.db.execute(
                "UPDATE public.earthx_run SET status = %s WHERE run_id = (SELECT run_id FROM public.earthx_job WHERE job_id = %s)",
                (status, job_id),
            )
        rig.db.execute("DELETE FROM public.earthx_job WHERE job_id = %s", (gone,))
        name = f"sentinel-2-c1-l2a_scale_{DAY}"
        assert await self.lines(rig, href) == [
            f"02 {name}: expired",
            f"03 {name}: failed",
            f"04 {name}: not finished",
            "05: no longer available",
        ]
        archive = opened((await rig.client.get(href)).content)
        assert {n.split("/")[1] for n in archive.namelist() if n.count("/") == 2} == {f"01_{name}"}

    async def test_a_part_that_went_away_after_the_post_changes_the_etag_so_a_resume_starts_again(
        self, mocked: Store, rig: Rig
    ) -> None:
        one, two = await part(rig, 1), await part(rig, 2)
        href = await make(rig, one, two)
        before = await rig.client.get(href)
        rig.db.execute(
            "UPDATE public.earthx_run SET status = 'failed', error_kind = 'source_5xx' "
            "WHERE run_id = (SELECT run_id FROM public.earthx_job WHERE job_id = %s)",
            (two,),
        )
        after = await rig.client.get(href, headers={"Range": "bytes=10-99", "If-Range": before.headers["etag"]})
        assert after.status_code == 200, "the validator no longer fits: the whole ZIP, not a piece of the old one"
        assert after.headers["etag"] != before.headers["etag"] and b"MISSING.txt" in after.content

    async def test_a_part_with_a_dismissed_job_is_no_longer_available(self, mocked: Store, rig: Rig) -> None:
        one, two = await part(rig, 1), await part(rig, 2)
        href = await make(rig, one, two)
        rig.db.execute("UPDATE public.earthx_job SET dismissed = true WHERE job_id = %s", (two,))
        assert await self.lines(rig, href) == [f"02 sentinel-2-c1-l2a_scale_{DAY}: no longer available"]

    async def test_a_part_that_was_deleted_is_no_longer_available_and_comes_back_when_restored(
        self, mocked: Store, rig: Rig
    ) -> None:
        one, two = await part(rig, 1), await part(rig, 2)
        href = await make(rig, one, two)
        await rig.client.delete(f"/processing/jobs/{two}")
        assert await self.lines(rig, href) == [f"02 sentinel-2-c1-l2a_scale_{DAY}: no longer available"]
        await rig.client.post(f"/processing/jobs/{two}/restore")
        response = await rig.client.get(href)
        assert response.status_code == 200 and b"MISSING.txt" not in response.content

    async def test_a_bundle_none_of_whose_parts_is_left_is_a_410(self, mocked: Store, rig: Rig) -> None:
        one = await part(rig, 1)
        href = await make(rig, one)
        rig.db.execute("UPDATE public.earthx_run SET status = 'failed'")
        assert problem(await rig.client.get(href), 410)["type"] == "urn:earthx:gone"

    async def test_a_stored_file_that_is_not_what_the_job_reported_is_a_500_for_the_whole_download(
        self, mocked: Store, rig: Rig
    ) -> None:
        one, two = await part(rig, 1), await part(rig, 2)
        href = await make(rig, one, two)
        result_id = rig.db.execute(
            "SELECT result_id FROM public.earthx_run WHERE run_id = (SELECT run_id FROM public.earthx_job WHERE job_id = %s)",
            (two,),
        ).fetchone()
        assert result_id is not None
        put(rig, result_id[0], "mask.tif", b"short")
        assert (await rig.client.get(href)).status_code == 500

    async def test_a_job_placed_before_the_years_were_kept_is_left_out_with_its_reason(
        self, mocked: Store, rig: Rig
    ) -> None:
        one, two = await part(rig, 1), await part(rig, 2)
        href = await make(rig, one, two)
        rig.db.execute(
            "UPDATE public.earthx_job SET acquired_first_year = NULL, acquired_last_year = NULL WHERE job_id = %s", (two,)
        )
        rig.source.items.clear()  # the dates of its scenes can no longer be read
        assert await self.lines(rig, href) == [f"02 sentinel-2-c1-l2a_scale_{DAY}: year of acquisition unknown"]


class TestByteRanges:
    async def test_a_range_is_that_slice_of_the_whole(self, mocked: Store, rig: Rig) -> None:
        href = await make(rig, await part(rig, 1), await part(rig, 2), await part(rig, 3))
        whole = (await rig.client.get(href)).content
        total = len(whole)
        for header, (first, last) in {
            "bytes=0-0": (0, 0),
            "bytes=100-2999": (100, 2999),
            f"bytes={total - 10}-": (total - 10, total - 1),
            "bytes=-300": (total - 300, total - 1),
            f"bytes=0-{total + 500}": (0, total - 1),
        }.items():
            response = await rig.client.get(href, headers={"Range": header})
            assert response.status_code == 206, header
            assert response.content == whole[first : last + 1], header
            assert response.headers["content-range"] == f"bytes {first}-{last}/{total}"

    async def test_two_parts_make_the_whole_the_way_a_resumed_download_does(self, mocked: Store, rig: Rig) -> None:
        href = await make(rig, await part(rig, 1), await part(rig, 2))
        whole = await rig.client.get(href)
        head = await rig.client.get(href, headers={"Range": "bytes=0-1499"})
        tail = await rig.client.get(
            href, headers={"Range": "bytes=1500-", "If-Range": head.headers["etag"]}
        )
        assert tail.status_code == 206 and head.content + tail.content == whole.content
        assert opened(head.content + tail.content).testzip() is None

    async def test_a_validator_that_does_not_fit_gives_the_whole_and_a_range_behind_the_end_a_416(
        self, mocked: Store, rig: Rig
    ) -> None:
        href = await make(rig, await part(rig, 1))
        whole = await rig.client.get(href)
        other = await rig.client.get(href, headers={"Range": "bytes=0-9", "If-Range": '"other"'})
        assert other.status_code == 200 and other.content == whole.content
        behind = await rig.client.get(href, headers={"Range": f"bytes={len(whole.content)}-"})
        assert problem(behind, 416) and behind.headers["content-range"] == f"bytes */{len(whole.content)}"

    async def test_a_download_takes_a_place_and_the_next_one_waits_when_all_are_taken(
        self, mocked: Store, rig: Rig
    ) -> None:
        href = await make(rig, await part(rig, 1))
        for _ in range(MAX_BUNDLE_DOWNLOADS):
            assert rig.api.bundles.take()
        busy = await rig.client.get(href)
        assert problem(busy, 503) and busy.headers["retry-after"] == "5"
        rig.api.bundles.free()
        assert (await rig.client.get(href)).status_code == 200
        assert rig.api.bundles.busy == MAX_BUNDLE_DOWNLOADS - 1, "the place is given back when the answer ends"


class TestWhoCanReadIt:
    @pytest.mark.parametrize("bundle_id", ["A" * 22, "short", "x" * 23, "a b", "A" * 21 + "%"])
    async def test_an_unknown_or_malformed_identifier_is_a_404(self, rig: Rig, bundle_id: str) -> None:
        response = await rig.client.get(f"{PATH}/{bundle_id}")
        assert problem(response, 404)["type"] == "urn:earthx:no-such-bundle"
        assert response.headers["cache-control"] == "no-store"

    async def test_an_expired_bundle_is_the_same_404_before_the_cleanup_came_and_looking_does_not_lengthen(
        self, mocked: Store, rig: Rig
    ) -> None:
        href = await make(rig, await part(rig, 1))
        before = rig.db.execute("SELECT expires_at FROM public.earthx_bundle").fetchone()
        for _ in range(2):
            assert (await rig.client.get(href)).status_code == 200
        assert rig.db.execute("SELECT expires_at FROM public.earthx_bundle").fetchone() == before
        unknown = await rig.client.get(f"{PATH}/{'A' * 22}")
        rig.db.execute("UPDATE public.earthx_bundle SET expires_at = clock_timestamp() - interval '1 second'")
        expired = await rig.client.get(href)
        assert expired.status_code == 404 and expired.json() == unknown.json() and rows(rig) == 1

    async def test_the_cleanup_takes_what_has_expired_and_leaves_the_rest(self, mocked: Store, rig: Rig) -> None:
        old, young = await make(rig, await part(rig, 1)), await make(rig, await part(rig, 2))
        rig.db.execute(
            "UPDATE public.earthx_bundle SET expires_at = clock_timestamp() - interval '1 second' WHERE bundle_id = %s",
            (old.removeprefix(f"{PATH}/"),),
        )
        assert cleanup(rig.db, rig.store).bundles == 1 and rows(rig) == 1
        assert (await rig.client.get(young)).status_code == 200


class TestNothingPersonalInTheLogs:
    async def test_the_access_log_names_the_route_and_never_the_bundle_or_a_job(
        self, mocked: Store, rig: Rig, access_log_lines: list[str]
    ) -> None:
        one = await part(rig, 1)
        href = await make(rig, one)
        await rig.client.get(href)
        await rig.client.get(f"{PATH}/not-an-identifier-but-secret")
        assert not [line for line in access_log_lines if href.removeprefix(f"{PATH}/") in line or "secret" in line]
        assert not [line for line in access_log_lines if one in line]
        paths = {json.loads(line)["path"] for line in access_log_lines}
        assert {PATH, f"{PATH}/{{bundleID}}"} <= paths

    async def test_no_log_line_holds_a_bundle_a_job_or_the_list_not_even_when_it_goes_wrong(
        self, mocked: Store, rig: Rig, caplog: pytest.LogCaptureFixture
    ) -> None:
        one, two = await part(rig, 1), await part(rig, 2)
        results = [r[0] for r in rig.db.execute("SELECT result_id FROM public.earthx_run")]
        with caplog.at_level(logging.DEBUG, logger="earthx"):
            href = await make(rig, one, two)
            await rig.client.get(href)
            await rig.client.post(PATH, json={"jobs": [one, one]})
            await rig.client.post(PATH, json={"jobs": ["A" * 22]})
            put(rig, results[0], "mask.tif", b"short")
            assert (await rig.client.get(href)).status_code == 500
            await rig.client.get(f"{PATH}/{'A' * 22}")
        text = "\n".join(own_log_text(record) for record in caplog.records)
        assert caplog.records
        for forbidden in (href.removeprefix(f"{PATH}/"), one, two, "A" * 22, *results, "9.01", "47.01"):
            assert forbidden not in text, forbidden

    async def test_both_routes_say_no_store(self, mocked: Store, rig: Rig) -> None:
        made = await rig.client.post(PATH, json={"jobs": [await part(rig, 1)]})
        assert made.headers["cache-control"] == "no-store"
        assert (await rig.client.get(made.json()["href"])).headers["cache-control"] == "no-store"
        assert (await rig.client.post(PATH, json={"jobs": []})).headers["cache-control"] == "no-store"
