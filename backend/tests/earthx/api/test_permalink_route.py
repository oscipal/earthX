"""The permalink API: keep an order and a view, read it, delete it (M4-19e; plan §3.5, §9).

A real queue database and a bare app with the job router; everything is synthetic and offline.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from earthx.api.processing_route import MAX_BODY_BYTES
from earthx.jobs import permalinks
from tests.conftest import own_log_text
from tests.earthx.api.conftest import Rig
from tests.earthx.api.test_intake import order

pytestmark = pytest.mark.anyio

PATH = "/processing/permalinks"
VIEW = {"center": [9.5, 47.25], "zoom": 9.5, "range": {"vmin": -1.0, "vmax": 1.0, "colormap": "rdylgn"}, "title": "Lake"}
KEY_HEADER = "X-Delete-Key"


def body(document: dict[str, Any] | None = None, view: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"order": order() if document is None else document, "view": VIEW if view is None else view}


async def create(rig: Rig, payload: Any = None) -> dict[str, Any]:
    response = await rig.client.post(PATH, json=body() if payload is None else payload)
    assert response.status_code == 201, response.text
    return response.json()


def rows(rig: Rig) -> int:
    row = rig.db.execute("SELECT count(*) FROM public.earthx_permalink").fetchone()
    assert row is not None
    return row[0]


class TestCreateReadDelete:
    async def test_what_is_kept_comes_back_with_its_expiry(self, rig: Rig) -> None:
        made = await create(rig)
        assert permalinks.is_permalink_id(made["id"]) and made["delete_key"] != made["id"]
        response = await rig.client.get(f"{PATH}/{made['id']}")
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        document = response.json()
        assert document["order"] == order() and document["view"] == {**VIEW, "center": [9.5, 47.25]}
        expires = datetime.fromisoformat(document["expires_at"])
        assert expires == datetime.fromisoformat(made["expires_at"])
        assert timedelta(days=29, hours=23) < expires - datetime.now(UTC) <= permalinks.TTL

    async def test_the_view_is_optional_in_its_range_and_title(self, rig: Rig) -> None:
        made = await create(rig, body(view={"center": [0, 0], "zoom": 2}))
        stored = (await rig.client.get(f"{PATH}/{made['id']}")).json()["view"]
        assert stored["range"] is None and stored["title"] is None

    async def test_two_links_for_one_order_are_two_identifiers_and_two_keys(self, rig: Rig) -> None:
        one, two = await create(rig), await create(rig)
        assert one["id"] != two["id"] and one["delete_key"] != two["delete_key"]

    async def test_the_key_is_stored_as_a_hash_only(self, rig: Rig) -> None:
        made = await create(rig)
        row = rig.db.execute("SELECT delete_key_hash, body::text FROM public.earthx_permalink").fetchone()
        assert row is not None and made["delete_key"] not in row[0] + row[1] and len(row[0]) == 64

    async def test_the_right_key_deletes_and_the_link_is_gone(self, rig: Rig) -> None:
        made = await create(rig)
        response = await rig.client.delete(f"{PATH}/{made['id']}", headers={KEY_HEADER: made["delete_key"]})
        assert response.status_code == 204 and rows(rig) == 0
        assert (await rig.client.get(f"{PATH}/{made['id']}")).status_code == 404

    async def test_a_wrong_key_answers_what_an_unknown_link_answers(self, rig: Rig) -> None:
        made = await create(rig)
        wrong = await rig.client.delete(f"{PATH}/{made['id']}", headers={KEY_HEADER: "x" * 22})
        unknown = await rig.client.delete(f"{PATH}/{'A' * 22}", headers={KEY_HEADER: made["delete_key"]})
        assert wrong.status_code == unknown.status_code == 404 and wrong.json() == unknown.json()
        assert rows(rig) == 1

    async def test_a_delete_without_a_key_is_a_400_for_every_identifier(self, rig: Rig) -> None:
        made = await create(rig)
        for permalink_id in (made["id"], "A" * 22):
            assert (await rig.client.delete(f"{PATH}/{permalink_id}")).status_code == 400
        assert rows(rig) == 1

    @pytest.mark.parametrize("permalink_id", ["A" * 22, "short", "x" * 23, "a b", "A" * 21 + "%"])
    async def test_an_unknown_or_malformed_identifier_is_a_404(self, rig: Rig, permalink_id: str) -> None:
        response = await rig.client.get(f"{PATH}/{permalink_id}")
        assert response.status_code == 404
        assert response.headers["content-type"] == "application/problem+json"

    async def test_an_expired_link_is_a_404_before_the_cleanup_came_and_looking_does_not_lengthen(
        self, rig: Rig
    ) -> None:
        made = await create(rig)
        before = rig.db.execute("SELECT expires_at FROM public.earthx_permalink").fetchone()
        for _ in range(2):
            assert (await rig.client.get(f"{PATH}/{made['id']}")).status_code == 200
        assert rig.db.execute("SELECT expires_at FROM public.earthx_permalink").fetchone() == before
        rig.db.execute("UPDATE public.earthx_permalink SET expires_at = clock_timestamp() - interval '1 second'")
        assert (await rig.client.get(f"{PATH}/{made['id']}")).status_code == 404
        gone = await rig.client.delete(f"{PATH}/{made['id']}", headers={KEY_HEADER: made["delete_key"]})
        assert gone.status_code == 404 and rows(rig) == 1


class TestWhatIsRefused:
    async def test_an_invalid_order_is_a_422_and_nothing_is_stored(self, rig: Rig) -> None:
        bad = order()
        bad["steps"] = [{"op": "no_such_operator", "op_version": 1, "params": {}}]
        response = await rig.client.post(PATH, json=body(bad))
        assert response.status_code == 422 and rows(rig) == 0

    async def test_a_recipe_with_resolved_entries_is_not_an_order(self, rig: Rig) -> None:
        recipe = order()
        recipe["inputs"][0]["resolved"] = []
        assert (await rig.client.post(PATH, json=body(recipe))).status_code == 422

    @pytest.mark.parametrize(
        "view",
        [
            {"center": [9.5, 47.25]},
            {"center": [9.5, 47.25], "zoom": 5, "other": 1},
            {"center": [200, 47.25], "zoom": 5},
            {"center": [9.5, 91], "zoom": 5},
            {"center": [9.5], "zoom": 5},
            {"center": [9.5, 47], "zoom": 25},
            {"center": [9.5, 47], "zoom": "5"},
            {"center": [9.5, 47], "zoom": 5, "title": ""},
            {"center": [9.5, 47], "zoom": 5, "title": "a\nb"},
            {"center": [9.5, 47], "zoom": 5, "title": "x" * 101},
            {"center": [9.5, 47], "zoom": 5, "range": {"vmin": 0, "vmax": 1}},
            {"center": [9.5, 47], "zoom": 5, "range": {"vmin": 0, "vmax": 1, "colormap": "../x"}},
            {"center": [9.5, 47], "zoom": 5, "range": {"vmin": 0, "vmax": 1, "colormap": "a", "extra": 1}},
            "text",
            None,
        ],
    )
    async def test_a_view_outside_its_model_is_a_422(self, rig: Rig, view: Any) -> None:
        response = await rig.client.post(PATH, json={"order": order(), "view": view})
        assert response.status_code == 422 and rows(rig) == 0

    @pytest.mark.parametrize(
        "payload", [[], "text", {"order": order()}, {"view": VIEW}, {"order": order(), "view": VIEW, "job": "x"}]
    )
    async def test_a_body_that_is_not_order_and_view_is_a_400(self, rig: Rig, payload: Any) -> None:
        assert (await rig.client.post(PATH, json=payload)).status_code == 400

    async def test_text_that_is_not_json_or_has_a_duplicate_key_is_a_400(self, rig: Rig) -> None:
        headers = {"content-type": "application/json"}
        for raw in (b"{", b'{"order": {}, "order": {}, "view": {}}', b'{"order": NaN, "view": {}}'):
            assert (await rig.client.post(PATH, content=raw, headers=headers)).status_code == 400

    async def test_another_media_type_is_a_415_and_a_body_over_the_cap_a_413(self, rig: Rig) -> None:
        assert (await rig.client.post(PATH, content=b"{}", headers={"content-type": "text/plain"})).status_code == 415
        big = b'{"order": "' + b"x" * MAX_BODY_BYTES + b'"}'
        assert (await rig.client.post(PATH, content=big, headers={"content-type": "application/json"})).status_code == 413
        assert rows(rig) == 0

    async def test_the_queue_database_missing_is_a_503(self, rig: Rig) -> None:
        rig.app.state.earthx_job_api = None
        assert (await rig.client.post(PATH, json=body())).status_code == 503


class TestNothingPersonalInTheLogs:
    async def test_the_access_log_names_the_route_and_never_the_link(
        self, rig: Rig, access_log_lines: list[str]
    ) -> None:
        made = await create(rig)
        await rig.client.get(f"{PATH}/{made['id']}")
        await rig.client.delete(f"{PATH}/{made['id']}", headers={KEY_HEADER: made["delete_key"]})
        await rig.client.get(f"{PATH}/not-an-identifier-but-secret")
        assert not [line for line in access_log_lines if made["id"] in line or "secret" in line]
        paths = {json.loads(line)["path"] for line in access_log_lines}
        assert {PATH, f"{PATH}/{{permalinkID}}"} <= paths

    async def test_no_log_line_holds_the_area_the_key_the_link_or_the_title(
        self, rig: Rig, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG, logger="earthx"):
            made = await create(rig)
            await rig.client.get(f"{PATH}/{made['id']}")
            await rig.client.post(PATH, json=body(view={"center": [1, 1], "zoom": 99, "title": "Lake"}))
            await rig.client.delete(f"{PATH}/{made['id']}", headers={KEY_HEADER: made["delete_key"]})
        text = "\n".join(own_log_text(record) for record in caplog.records)
        assert caplog.records
        for forbidden in (made["id"], made["delete_key"], "9.01", "47.01", "9.5", "Lake", "S2_A"):
            assert forbidden not in text, forbidden
        assert "permalink created" in text and "sentinel-2-c1-l2a" in text
