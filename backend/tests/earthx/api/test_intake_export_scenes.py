"""F4 = 2 (plan M5-30b §6): the limit of the notice in an export's ZIP grows with the scenes of the order.

Synthetic and offline."""

from __future__ import annotations

import json

import pytest

from earthx.api.intake import MAX_ORDER_ITEMS
from earthx.processing.export import (
    ATTACHMENT_LIMITS,
    MAX_ATTACHMENT_SCENES,
    NOTICE_BYTES_PER_SCENE,
    Attachments,
    AttachmentsInvalid,
    attachment_limits,
)
from tests.earthx.api.test_intake import S2, Source, accept, export_order, refused, visual_item

NOTICE = "ATTRIBUTION.txt"
FILES = ("aoi.geojson", "citation.bib", NOTICE)


def long_ids(count: int) -> list[str]:
    """Ids of the full length `ITEM_ID` allows (255 characters), each its own."""
    return [f"S2_{index:04d}".ljust(255, "x") for index in range(count)]


def files_with(notice: str) -> dict[str, str]:
    return {**{name: "x" for name in FILES}, NOTICE: notice}


class TestTheLimitGrowsWithTheScenes:
    def test_a_small_order_keeps_the_old_64_kib(self) -> None:
        assert attachment_limits(1)[NOTICE] == 64 * 1024 + NOTICE_BYTES_PER_SCENE
        assert attachment_limits(0) == dict(ATTACHMENT_LIMITS)
        assert ATTACHMENT_LIMITS[NOTICE] == 64 * 1024
        Attachments(files_with("x" * 64 * 1024), ())
        with pytest.raises(AttachmentsInvalid):
            Attachments(files_with("x" * (64 * 1024 + 1)), ())

    def test_only_the_notice_grows(self) -> None:
        grown, base = attachment_limits(MAX_ATTACHMENT_SCENES), dict(ATTACHMENT_LIMITS)
        assert {name for name in base if grown[name] != base[name]} == {NOTICE}

    def test_the_guard_is_that_of_the_order(self) -> None:
        assert MAX_ATTACHMENT_SCENES == MAX_ORDER_ITEMS

    def test_a_text_above_the_grown_limit_is_still_refused(self) -> None:
        limit = attachment_limits(10)[NOTICE]
        Attachments(files_with("x" * limit), (), scenes=10)
        with pytest.raises(AttachmentsInvalid, match=str(limit)):
            Attachments(files_with("x" * (limit + 1)), (), scenes=10)

    def test_the_grown_limit_counts_bytes_not_characters(self) -> None:
        limit = attachment_limits(10)[NOTICE]
        with pytest.raises(AttachmentsInvalid):
            Attachments(files_with("ä" * (limit // 2 + 1)), (), scenes=10)

    def test_the_other_files_do_not_take_the_notice_s_allowance(self) -> None:
        files = {**files_with("x"), "citation.bib": "x" * (64 * 1024 + 1)}
        with pytest.raises(AttachmentsInvalid):
            Attachments(files, (), scenes=MAX_ATTACHMENT_SCENES)

    @pytest.mark.parametrize("scenes", [-1, MAX_ATTACHMENT_SCENES + 1, True, 1.5, "2000", None])
    def test_a_count_outside_the_guard_is_refused(self, scenes: object) -> None:
        with pytest.raises(AttachmentsInvalid):
            Attachments(files_with("x"), (), scenes=scenes)  # type: ignore[arg-type]

    @pytest.mark.parametrize("scenes", [-1, MAX_ATTACHMENT_SCENES + 1, True, "5", 2.0])
    def test_the_worker_refuses_a_count_it_does_not_accept(self, scenes: object) -> None:
        data = {"files": files_with("x"), "attribution": [], "scenes": scenes}
        with pytest.raises(AttachmentsInvalid):
            Attachments.from_json(data)

    def test_the_worker_cannot_be_given_more_room_than_the_guard(self) -> None:
        most = attachment_limits(MAX_ATTACHMENT_SCENES)[NOTICE]
        data = {"files": files_with("x" * most), "attribution": [], "scenes": MAX_ATTACHMENT_SCENES}
        Attachments.from_json(data)
        with pytest.raises(AttachmentsInvalid):
            Attachments.from_json({**data, "files": files_with("x" * (most + 1))})

    def test_attachments_without_a_count_read_with_the_base_limit(self) -> None:
        """What was queued before F4 = 2 carries no ``scenes``."""
        attachments = Attachments.from_json({"files": files_with("x"), "attribution": []})
        assert attachments.scenes == 0 and "scenes" not in attachments.to_json()
        with pytest.raises(AttachmentsInvalid):
            Attachments.from_json({"files": files_with("x" * (64 * 1024 + 1)), "attribution": []})


@pytest.mark.anyio
class TestAnExportOfManyScenes:
    async def test_2000_scenes_with_ids_of_full_length_are_accepted_and_read_back(self) -> None:
        ids = long_ids(MAX_ORDER_ITEMS)
        source = Source(*((S2, visual_item(item_id)) for item_id in ids))
        accepted = await accept(export_order(groups=tuple((item_id,) for item_id in ids)), source)
        attachments = accepted.attachments
        assert attachments is not None and attachments.scenes == MAX_ORDER_ITEMS
        notice = attachments.files[NOTICE]
        assert all(item_id in notice for item_id in ids)
        size = len(notice.encode("utf-8"))
        assert 64 * 1024 < size <= attachment_limits(MAX_ORDER_ITEMS)[NOTICE]
        # What the queue stores and the worker reads (`jobs`: json.dumps into attachments.json, `from_json`).
        assert Attachments.from_json(json.loads(json.dumps(attachments.to_json()))) == attachments

    async def test_2000_scenes_in_one_group_are_accepted_too(self) -> None:
        ids = long_ids(MAX_ORDER_ITEMS)
        source = Source(*((S2, visual_item(item_id)) for item_id in ids))
        accepted = await accept(export_order(groups=(tuple(ids),)), source)
        assert accepted.attachments is not None and accepted.attachments.scenes == MAX_ORDER_ITEMS

    async def test_the_scenes_a_group_left_out_count_too(self) -> None:
        far = (170.0, -40.0, 170.1, -39.9)
        source = Source((S2, visual_item("S2_A")), (S2, visual_item("S2_B", far)), (S2, visual_item("S2_C", far)))
        accepted = await accept(export_order(groups=(("S2_A",), ("S2_B", "S2_C"))), source)
        assert accepted.attachments is not None and accepted.attachments.scenes == 3
        assert "S2_B, S2_C" in accepted.attachments.files[NOTICE]

    async def test_a_small_order_counts_its_scenes(self) -> None:
        accepted = await accept(export_order(), Source((S2, visual_item("S2_A"))))
        assert accepted.attachments is not None and accepted.attachments.scenes == 1

    async def test_an_order_above_the_guard_is_still_a_413(self) -> None:
        ids = [f"S2_{index}" for index in range(MAX_ORDER_ITEMS + 1)]
        error = await refused(export_order(groups=tuple((item_id,) for item_id in ids)), Source())
        assert error.status_code == 413
