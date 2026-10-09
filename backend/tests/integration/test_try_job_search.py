"""The search `scripts/try-job.ps1` makes, against the real api app and a source that answers in the real shape.

Real Postgres/pgstac and the real `api` app; the source (Earth Search) is a mocked transport that
answers with `fixtures/earth_search/search_real_shape.json` — invented values in the shape and the
header of a real answer (README there). The first class pins what the script relies on in the
platform's answer; the second runs the script itself, if PowerShell is installed (CI's Ubuntu image
has `pwsh`; a plain cloud session may not, and then that class is skipped with its reason).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import threading
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
import uvicorn

from earthx.api.main import app
from earthx.catalog.load import main as load_catalog
from earthx.gateway import Gateway, Policy

pytestmark = pytest.mark.anyio

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "earth_search"
SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "try-job.ps1"
HOST = "earth-search.aws.element84.com"
DATASET = "sentinel-2-c1-l2a"
# Zürich: the area the report came from (Otto, 07.10.2026); public place, a box of about 0.8 km.
ZURICH = "8.535,47.365,8.545,47.372"
SUMMER = "2025-06-01/2025-08-31"


def real_shape() -> dict[str, Any]:
    return json.loads((FIXTURES / "search_real_shape.json").read_text(encoding="utf-8"))


def geo_json(body: dict[str, Any]) -> httpx.Response:
    """As Earth Search answers: `application/geo+json; charset=utf-8`, not `application/json`."""
    return httpx.Response(
        200, content=json.dumps(body).encode(), headers={"content-type": "application/geo+json; charset=utf-8"}
    )


@pytest.fixture
def require_catalog_loaded(require_postgres_env: None) -> None:
    assert load_catalog() == 0
    with psycopg.connect(autocommit=True) as conn:
        conn.execute("DELETE FROM public.earthx_search_cache")


@asynccontextmanager
async def platform(answer: httpx.Response) -> AsyncIterator[tuple[str, list[httpx.Request]]]:
    """The api app on a local port, its gateway answering as the source does; yields the base URL and what the source saw."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return answer

    async def no_wait(seconds: float) -> None:
        return None

    async with app.router.lifespan_context(app):
        app.state.earthx_gateway = Gateway(
            Policy(allowed_hosts=frozenset({HOST})),
            transport=httpx.MockTransport(handler),
            resolve=lambda host, port: ("93.184.216.34",),
            sleep=no_wait,
        )
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="off", access_log=False)
        )
        task = asyncio.create_task(server.serve())
        while not server.started:
            await asyncio.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        try:
            yield f"http://127.0.0.1:{port}", seen
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, 15)


def search_body(bbox: str = ZURICH, datetime: str = "2025-06-01T00:00:00Z/2025-08-31T23:59:59Z") -> dict[str, Any]:
    return {"collections": [DATASET], "bbox": [float(x) for x in bbox.split(",")], "datetime": datetime, "limit": 1}


class TestWhatTheScriptRelaysOn:
    async def test_the_viewers_search_finds_the_scene_and_answers_geo_json(self, require_catalog_loaded: None) -> None:
        async with platform(geo_json(real_shape())) as (base, seen):
            async with httpx.AsyncClient() as client:
                response = await client.post(f"{base}/stac/search", json=search_body())
        assert response.status_code == 200
        # The script reads the answer as bytes because of this type (Windows PowerShell 5.1 hands such a
        # type back as bytes, not text).
        assert response.headers["content-type"].split(";")[0] == "application/geo+json"
        body = response.json()
        assert [feature["id"] for feature in body["features"]] == [real_shape()["features"][0]["id"]]
        assert body["numberReturned"] == 1

    async def test_the_source_is_asked_for_exactly_what_the_script_sent(self, require_catalog_loaded: None) -> None:
        async with platform(geo_json(real_shape())) as (base, seen):
            async with httpx.AsyncClient() as client:
                await client.post(f"{base}/stac/search", json=search_body())
        (request,) = seen
        sent = json.loads(request.content)
        assert request.method == "POST" and request.url.path.endswith("/search")
        assert sent["collections"] == [DATASET]
        assert sent["bbox"] == [8.535, 47.365, 8.545, 47.372], "west, south, east, north"
        assert sent["datetime"] == "2025-06-01T00:00:00Z/2025-08-31T23:59:59Z"
        assert sent["limit"] == 1

    async def test_the_item_has_what_the_order_is_built_from(self, require_catalog_loaded: None) -> None:
        async with platform(geo_json(real_shape())) as (base, _):
            async with httpx.AsyncClient() as client:
                feature = (await client.post(f"{base}/stac/search", json=search_body())).json()["features"][0]
        assert feature["id"] and feature["properties"]["datetime"]
        assert {"red", "nir"} <= set(feature["assets"]), "the script reprojects `red`"

    async def test_the_fixture_has_the_shape_of_the_real_answer(self) -> None:
        shape = real_shape()
        assert sorted(shape) == sorted(
            [
                "context",
                "features",
                "links",
                "numberMatched",
                "numberReturned",
                "stac_extensions",
                "stac_version",
                "type",
            ]
        )
        feature = shape["features"][0]
        assert sorted(feature) == sorted(
            [
                "type",
                "stac_version",
                "id",
                "properties",
                "geometry",
                "links",
                "assets",
                "bbox",
                "stac_extensions",
                "collection",
            ]
        )
        assert len(feature["assets"]) == 23 and feature["id"].startswith("SYNTH_")
        assert [link["rel"] for link in shape["links"]] == ["next", "root"]

    async def test_the_old_search_by_get_gives_the_same_scene(self, require_catalog_loaded: None) -> None:
        """The first version of the script searched `GET /stac/collections/{id}/items?bbox=&datetime=`."""
        async with platform(geo_json(real_shape())) as (base, _):
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{base}/stac/collections/{DATASET}/items",
                    params={"limit": 1, "bbox": ZURICH, "datetime": "2025-06-01T00:00:00Z/2025-08-31T23:59:59Z"},
                )
        assert response.status_code == 200
        assert [feature["id"] for feature in response.json()["features"]] == [real_shape()["features"][0]["id"]]


PWSH = shutil.which("pwsh")


@pytest.mark.skipif(PWSH is None, reason="PowerShell (pwsh) is not installed; the CI image has it")
class TestTheScriptItself:
    async def run_script(self, base: str, *arguments: str) -> tuple[int, str]:
        environment = {**os.environ, "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT": "1", "NO_COLOR": "1"}
        process = await asyncio.create_subprocess_exec(
            PWSH or "pwsh",
            "-NoProfile",
            "-File",
            str(SCRIPT),
            "-BaseUrl",
            base,
            "-SearchOnly",
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=environment,
        )
        output, _ = await asyncio.wait_for(process.communicate(), 120)
        return process.returncode or 0, output.decode("utf-8", errors="replace")

    async def test_it_finds_a_scene_over_zurich_like_the_viewer(self, require_catalog_loaded: None) -> None:
        async with platform(geo_json(real_shape())) as (base, seen):
            code, output = await self.run_script(base, "-Verbose", "-Bbox", ZURICH, "-Datetime", SUMMER)
        assert code == 0, output
        assert "[OK    ] Item gefunden" in output and real_shape()["features"][0]["id"] in output
        (request,) = seen
        assert json.loads(request.content)["bbox"] == [8.535, 47.365, 8.545, 47.372]
        # -Verbose: the request that was sent and the size of the answer
        assert "-> Post " in output and "/stac/search" in output
        assert '"bbox": [8.535,47.365,8.545,47.372]' in output
        assert "Bytes, Content-Type: application/geo+json" in output

    async def test_without_verbose_the_area_is_not_printed(self, require_catalog_loaded: None) -> None:
        async with platform(geo_json(real_shape())) as (base, _):
            code, output = await self.run_script(base, "-Bbox", ZURICH, "-Datetime", SUMMER)
        assert code == 0, output
        assert "8.535" not in output and "47.365" not in output

    async def test_an_empty_answer_is_no_item_not_an_unreadable_answer(self, require_catalog_loaded: None) -> None:
        empty = json.loads((FIXTURES / "search_empty.json").read_text(encoding="utf-8"))
        async with platform(geo_json(empty)) as (base, _):
            code, output = await self.run_script(base)
        assert code == 1
        assert "kein Item gefunden" in output and "kein lesbares JSON" not in output

    @contextmanager
    def source_answering(self, content_type: str, body: bytes) -> Iterator[str]:
        """A tiny local platform whose search answers `body` with `content_type`, whatever it is asked."""

        class Page(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: Any) -> None:
                return None

        server = ThreadingHTTPServer(("127.0.0.1", 0), Page)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}"
        finally:
            server.shutdown()
            server.server_close()

    async def test_an_answer_that_is_not_json_is_named_as_such(self) -> None:
        with self.source_answering("text/html", b"<html>not stac</html>") as base:
            code, output = await self.run_script(base)
        assert code == 1 and "kein lesbares JSON" in output and "kein Item gefunden" not in output

    @pytest.mark.parametrize(
        "content_type", ["application/octet-stream", "application/geo+json; charset=utf-8", "application/x-unknown"]
    )
    async def test_the_answer_is_read_from_its_bytes_whatever_type_it_carries(self, content_type: str) -> None:
        """PowerShell hands `.Content` of a type it does not know as text back as bytes (5.1 does so for
        application/geo+json, where the platform's search lives); the script reads the bytes itself."""
        with self.source_answering(content_type, json.dumps(real_shape()).encode()) as base:
            code, output = await self.run_script(base)
        assert code == 0, output
        assert "[OK    ] Item gefunden" in output and real_shape()["features"][0]["id"] in output

    async def test_an_answer_with_non_ascii_text_is_read_as_utf_8(self) -> None:
        shape = real_shape()
        shape["features"][0]["id"] = "SYNTH_ÄÖÜ_é"
        with self.source_answering("application/geo+json", json.dumps(shape, ensure_ascii=False).encode()) as base:
            code, output = await self.run_script(base)
        assert code == 0, output
        assert "SYNTH_ÄÖÜ_é" in output
