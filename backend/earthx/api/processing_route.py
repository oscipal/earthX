"""The job API: place a job, follow it, dismiss it, fetch its result (M4-08b; adr/0014 §9, adr/0015 §6).

It follows the *form* of OGC API – Processes 1.0 — paths, words, status values, the status
and results documents — and **claims no conformance** (Otto, F4; adr/0014 §15d): an input
given by reference is a fetch of an address the caller names, which B8 closes, so a link
input is a ``400`` and ``/processing/conformance`` lists no class. See :mod:`processing_docs`
for the documents that need no job.

What each route turns away, and how (all errors are ``application/problem+json`` with
``type``, ``title``, ``status``, ``detail``; no text names an address, an AOI or a hash):

* **Every route with a ``{jobID}``** answers ``404`` for an identifier that is malformed,
  unknown, dismissed or **expired** — one fixed text, so nobody can tell "never existed"
  from "has expired" or "was dismissed". The links under ``/results`` are the one
  exception: they answer ``410`` from the end of the job's life (or 60 s before it) until
  the rows are gone (adr/0015 §6.2).
* **Placing a job** is asynchronous only (``201`` and ``Location``); an input by reference,
  a qualified value, a ``response`` other than ``document`` and anything else outside the
  envelope is ``400``. The order itself goes through :func:`earthx.api.intake.accept_order`.
* **A result link** answers ``303`` with a URL signed just now for 15 minutes and never past
  the result's expiry, ``Cache-Control: no-store``. ``recipe.json`` is built here from the
  job's own recipe; it does not lie in the object store.

Every answer under ``/jobs/`` and the placing of a job carry ``Cache-Control: no-store``.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from http import HTTPStatus
from typing import Annotated, Any, Literal, TypeVar

import psycopg
from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.sse import EventSourceResponse, ServerSentEvent
from psycopg_pool import ConnectionPool, PoolTimeout
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from earthx.api import processing_docs as docs
from earthx.api.intake import OrderRefused, accept_order, check_recipe_hosts, job_recipe_json
from earthx.api.item_source import ItemSource
from earthx.api.job_events import TERMINAL, JobEvents, Subscription, TooManyFollowers
from earthx.catalog.registry import DatasetRegistry, UnknownDatasetError
from earthx.gateway import Gateway
from earthx.jobs.submit import JobStatus, RecipeIdTaken, dismiss, job_recipe, job_status, submit
from earthx.objectstore.errors import ObjectStoreError, ResultExpiring
from earthx.objectstore.results import MIN_REMAINING, RESULT_NAMES, Store, signed_download
from earthx.processing import check_scope
from earthx.processing.errors import RecipeInvalid, UnsupportedRecipe
from earthx.processing.operators import OperatorRegistry
from earthx.processing.recipe import RECIPE_VERSION, loads_i_json

LOGGER = logging.getLogger("earthx.api.processing")

__all__ = ["MAX_BODY_BYTES", "JobApi", "Problem", "router"]

#: The largest body of a job request (M4-08b K2): the size of an AOI file (`access.aoi_upload`).
MAX_BODY_BYTES = 1_048_576

_TYPE_BASE = "http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/"
NO_SUCH_JOB = f"{_TYPE_BASE}no-such-job"
NO_SUCH_PROCESS = f"{_TYPE_BASE}no-such-process"
RESULT_NOT_READY = f"{_TYPE_BASE}result-not-ready"
_FAILED_TYPE = "urn:earthx:job-failed:"
_ORDER_TYPE = "urn:earthx:order-refused:"

#: What a link under ``/results`` may name. `result.tif` and `mask.tif` lie in the store, `recipe.json` is built.
LINK_NAMES = ("result.tif", "mask.tif", "recipe.json")

_ENVELOPE_KEYS = frozenset({"inputs", "outputs", "response"})
_TRANSMISSION = "reference"

#: ``error_kind`` of a failed run → (status of the result, fixed title) (M4-08b F5).
#: What is not listed — a kind a later version adds included — is a ``500`` named ``unknown``.
_FAILURES: dict[str, tuple[int, str]] = {
    "recipe_invalid": (422, "The recipe is not valid"),
    "unsupported_recipe": (422, "The recipe asks for what the platform does not run yet"),
    "scaling_mismatch": (422, "The scaling of the items disagrees with the recipe"),
    "grid_mismatch": (422, "The assets do not share one grid"),
    "aoi_outside_inputs": (422, "The area of interest lies outside the inputs"),
    "source_4xx": (502, "The source refused a read"),
    "source_429": (502, "The source asked for fewer requests"),
    "source_5xx": (502, "The source failed"),
    "source_unreachable": (502, "The source could not be reached"),
    "rejected": (502, "The platform refused an address of the source"),
    "source_timeout": (504, "The source did not answer in time"),
    "out_of_memory": (500, "The job ran out of memory"),
    "child_crashed": (500, "The job's process ended unexpectedly"),
    "runtime_exceeded": (500, "The job took longer than allowed"),
    "upload_failed": (500, "The result could not be stored"),
    "lease_lost": (500, "The worker of the job was lost"),
    "cancelled": (500, "The job was cancelled"),
    "unknown": (500, "The job failed"),
}

_MESSAGES = {
    "accepted": "The job is waiting for a worker.",
    "running": "The job is running.",
    "successful": "The job has finished.",
    "dismissed": "The job was dismissed.",
}


# --- what a route needs ------------------------------------------------------


@dataclass(frozen=True)
class JobApi:
    """What the job routes need besides the request; set on ``app.state.earthx_job_api`` by the lifespan."""

    registry: DatasetRegistry
    operators: OperatorRegistry
    item_source: ItemSource
    gateway: Gateway
    store: Store
    pool: ConnectionPool
    events: JobEvents


class Problem(Exception):
    """An answer that is an error, raised anywhere in a route and written by :class:`_JobRoute`."""

    def __init__(
        self,
        status: int,
        detail: str,
        *,
        type_: str = "about:blank",
        title: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.type = type_
        self.title = title or HTTPStatus(status).phrase
        self.headers = headers or {}

    def response(self) -> JSONResponse:
        return JSONResponse(
            {"type": self.type, "title": self.title, "status": self.status, "detail": self.detail},
            status_code=self.status,
            headers=self.headers,
            media_type="application/problem+json",
        )


def _no_such_job() -> Problem:
    return Problem(404, "there is no such job", type_=NO_SUCH_JOB, title="No such job")


class _JobRoute(APIRoute):
    """Errors as problem documents, and ``no-store`` on what belongs to one person's job."""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                response = await original(request)
            except Problem as problem:
                response = problem.response()
            except RequestValidationError as error:
                # Where and what kind, never the value (adr/0014 §4.7).
                reasons = "; ".join(
                    f"{'.'.join(str(part) for part in entry['loc'])}: {entry['type']}" for entry in error.errors()[:5]
                )
                response = Problem(400, f"the request does not match the interface: {reasons}").response()
            path = request.url.path
            if "/jobs/" in path or path.endswith("/execution"):
                response.headers["Cache-Control"] = "no-store"
            return response

        return handler


router = APIRouter(prefix=docs.PREFIX, route_class=_JobRoute, tags=["Processing"])


def _job_api(request: Request) -> JobApi:
    api = getattr(request.app.state, "earthx_job_api", None)
    if api is None:
        raise Problem(503, "the job API is not available")
    return api


def _root(request: Request) -> str:
    return request.scope.get("root_path", "").rstrip("/")


Api = Annotated[JobApi, Depends(_job_api)]
T = TypeVar("T")


async def _db(api: JobApi, call: Callable[..., T], *args: Any) -> T:
    """``call(connection, *args)`` on a pooled connection, off the event loop (the queue is synchronous)."""

    def run() -> T:
        with api.pool.connection() as conn:
            return call(conn, *args)

    try:
        return await run_in_threadpool(run)
    except (PoolTimeout, psycopg.OperationalError):
        # Never the driver's text: it can name the host and the user.
        LOGGER.warning("the queue database is not reachable")
        raise Problem(503, "the job queue is not reachable; try again", headers={"Retry-After": "5"}) from None


# --- answers -----------------------------------------------------------------


class Link(BaseModel):
    href: str
    rel: str
    type: str | None = None
    title: str | None = None


class StatusInfo(BaseModel):
    """The status document (OGC ``statusInfo``), thin on purpose: version 2 renames ``jobID`` to ``id`` (adr/0014 §9)."""

    model_config = ConfigDict(populate_by_name=True)

    process_id: str = Field(docs.PROCESS_ID, alias="processID")
    type: Literal["process"] = "process"
    job_id: str = Field(alias="jobID")
    status: Literal["accepted", "running", "successful", "failed", "dismissed"]
    message: str
    created: datetime
    started: datetime | None = None
    finished: datetime | None = None
    progress: int = Field(ge=0, le=100)
    #: When the job's rows and result go (Q10).
    expires: datetime
    #: The identifier of the recipe this job was placed with (Q15); never a hash.
    recipe_id: str = Field(alias="recipeID")
    links: list[Link]


class PlacedJob(StatusInfo):
    #: Items of the order the area of interest does not touch; the recipe leaves them out (M4-07b F4).
    skipped_items: list[str] = Field(default_factory=list, alias="skippedItems")


class ProblemDocument(BaseModel):
    type: str
    title: str
    status: int
    detail: str


_PROBLEMS: dict[int | str, dict[str, Any]] = {
    code: {"model": ProblemDocument, "description": HTTPStatus(code).phrase} for code in (400, 404, 410, 413, 422, 503)
}


def _job_links(root: str, status: JobStatus) -> list[Link]:
    base = f"{root}{docs.PREFIX}/jobs/{status.job_id}"
    links = [Link(href=base, rel="self", type="application/json", title="This job")]
    if status.status == "successful":
        links.append(
            Link(
                href=f"{base}/results",
                rel="http://www.opengis.net/def/rel/ogc/1.0/results",
                type="application/json",
                title="The results",
            )
        )
    if status.status not in TERMINAL:
        links.append(Link(href=f"{base}/events", rel="monitor", type="text/event-stream", title="Progress events"))
    return links


def _message(status: JobStatus) -> str:
    if status.status == "failed":
        return _failure(status.error_kind)[1]
    return _MESSAGES[status.status]


def _status_info(root: str, status: JobStatus, *, skipped: tuple[str, ...] | None = None) -> StatusInfo:
    fields: dict[str, Any] = {
        "job_id": status.job_id,
        "status": status.status,
        "message": _message(status),
        "created": status.created_at,
        "started": status.started_at,
        "finished": status.finished_at,
        "progress": status.progress,
        "expires": status.expires_at,
        "recipe_id": status.recipe_id,
        "links": _job_links(root, status),
    }
    if skipped is not None:
        return PlacedJob(**fields, skipped_items=list(skipped))
    return StatusInfo(**fields)


def _dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json", by_alias=True, exclude_none=True)


def _failure(kind: str | None) -> tuple[int, str]:
    return _FAILURES.get(kind or "unknown", _FAILURES["unknown"])


def _failed(status: JobStatus) -> Problem:
    kind = status.error_kind if status.error_kind in _FAILURES else "unknown"
    code, title = _failure(kind)
    return Problem(code, "the job failed; no result exists", type_=f"{_FAILED_TYPE}{kind}", title=title)


# --- documents that need no job ----------------------------------------------


def _operators(request: Request) -> OperatorRegistry:
    return request.app.state.earthx_operators


@router.get("/", summary="Landing page", responses=_PROBLEMS)
async def landing_page(request: Request) -> dict[str, Any]:
    return docs.landing_page(_root(request))


@lru_cache(maxsize=1)
def _api_description() -> dict[str, Any]:
    """The OpenAPI document of this router alone, built on an app of its own (the routes are fixed)."""
    own = FastAPI(
        title="EarthX processing",
        version=str(RECIPE_VERSION),
        description=f"Processing jobs over the catalogued datasets. It {docs.FORM_NOTE}.",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    own.include_router(router)
    return own.openapi()


@router.get("/api", include_in_schema=False)
async def api_description() -> JSONResponse:
    return JSONResponse(_api_description(), media_type="application/vnd.oai.openapi+json;version=3.1")


@router.get("/conformance", summary="Conformance classes (none claimed)")
async def conformance() -> dict[str, Any]:
    return docs.conformance()


@router.get("/processes", summary="The processes")
async def processes(request: Request, limit: str | None = None) -> dict[str, Any]:
    # Parsed here, not declared as an int: a bad value is a 400 of this API's own form.
    if limit is not None:
        try:
            wanted = int(limit)
        except ValueError:
            wanted = 0
        if not 1 <= wanted <= 10000:
            raise Problem(400, "limit is a whole number from 1 to 10000")
    return docs.process_list(_root(request))


@router.get("/processes/{process_id}", summary="One process, with the schema of the order")
async def process(request: Request, process_id: str, dataset: str | None = None) -> dict[str, Any]:
    if process_id != docs.PROCESS_ID:
        raise Problem(404, "there is no such process", type_=NO_SUCH_PROCESS, title="No such process")
    config = None
    if dataset is not None:
        registry: DatasetRegistry = request.app.state.earthx_registry
        try:
            config = registry.get(dataset)
        except UnknownDatasetError:
            raise Problem(400, f"no dataset {dataset[:64]!r}") from None
    return docs.process_description(_root(request), _operators(request), config)


# --- placing a job -----------------------------------------------------------


async def _read_body(request: Request) -> bytes:
    media = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if media != "application/json":
        raise Problem(415, "send the job request as application/json")
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise Problem(413, f"the request is over the {MAX_BODY_BYTES} byte cap")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise Problem(413, f"the request is over the {MAX_BODY_BYTES} byte cap")
        chunks.append(chunk)
    if not size:
        raise Problem(400, "the request has no body")
    return b"".join(chunks)


def _unwrap(raw: bytes) -> bytes:
    """The order inside the envelope ``{"inputs": {"recipe": {…}}}``, as JSON text; or the ``400`` that says why not.

    Only the part of the envelope the platform can honour is taken. An input given by
    reference is the part it cannot (F4, B8): nothing is fetched for it.
    """
    try:
        document = loads_i_json(raw)
    except RecipeInvalid as error:
        raise Problem(400, str(error)) from None
    if not isinstance(document, dict):
        raise Problem(400, "the request is a JSON object with an inputs member")
    unknown = sorted(set(document) - _ENVELOPE_KEYS)
    if unknown:
        raise Problem(
            400, f"the request has members this API does not take: {', '.join(repr(k[:32]) for k in unknown[:5])}"
        )
    inputs = document.get("inputs")
    if not isinstance(inputs, dict) or set(inputs) != {docs.PROCESS_ID}:
        raise Problem(400, f"inputs holds exactly one input, {docs.PROCESS_ID!r}")
    order = inputs[docs.PROCESS_ID]
    if (isinstance(order, dict) and "href" in order) or isinstance(order, str):
        raise Problem(400, docs.INLINE_ONLY)
    if isinstance(order, dict) and "value" in order:
        raise Problem(400, f"a qualified value is not taken; {docs.INLINE_ONLY}")
    if not isinstance(order, dict):
        raise Problem(400, f"the input {docs.PROCESS_ID!r} is the order itself, a JSON object")
    if document.get("response", "document") != "document":
        raise Problem(400, "response is document: a job's results are links, never the bytes")
    _check_outputs(document.get("outputs"))
    try:
        return json.dumps(order, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except UnicodeEncodeError:
        # A lone surrogate (`"\ud800"`) is valid JSON text and not a string anyone can store.
        raise Problem(400, "not a JSON document: a string holds a character that has no UTF-8 form") from None


def _check_outputs(outputs: Any) -> None:
    if outputs is None:
        return
    if not isinstance(outputs, dict) or set(outputs) - set(docs.OUTPUTS):
        raise Problem(400, f"outputs names some of {', '.join(docs.OUTPUTS)}")
    for entry in outputs.values():
        if not isinstance(entry, dict) or set(entry) - {"transmissionMode"}:
            raise Problem(400, "an output takes only transmissionMode")
        if entry.get("transmissionMode", _TRANSMISSION) != _TRANSMISSION:
            raise Problem(400, "a job's outputs are given by reference")


def _refused(error: OrderRefused) -> Problem:
    return Problem(error.status_code, error.detail, type_=f"{_ORDER_TYPE}{error.stage}")


@router.post(
    "/processes/{process_id}/execution",
    summary="Place a job (asynchronous only)",
    status_code=201,
    response_model=PlacedJob,
    response_model_by_alias=True,
    responses=_PROBLEMS,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "description": '{"inputs": {"recipe": <the order>}}; the order\'s schema is in the process.',
                    }
                }
            },
        }
    },
)
async def execute(request: Request, process_id: str, api: Api) -> Response:
    if process_id != docs.PROCESS_ID:
        raise Problem(404, "there is no such process", type_=NO_SUCH_PROCESS, title="No such process")
    order = _unwrap(await _read_body(request))
    try:
        accepted = await accept_order(
            order,
            registry=api.registry,
            operators=api.operators,
            item_source=api.item_source,
            gateway=api.gateway,
        )
        check_recipe_hosts(accepted.recipe, api.registry)
    except OrderRefused as error:
        raise _refused(error) from None
    try:
        check_scope(accepted.recipe)
    except UnsupportedRecipe as error:
        raise Problem(422, str(error), type_=f"{_ORDER_TYPE}scope") from None
    try:
        job_id = await _db(api, lambda conn, recipe: submit(conn, recipe, operators=api.operators), accepted.recipe)
    except RecipeIdTaken:
        # Cannot happen (a recipe_id is new for every order); if it does, it is ours, and the text names no value.
        raise Problem(500, "the job could not be placed") from None
    except RuntimeError:
        LOGGER.warning("the queue could not place an order")
        raise Problem(503, "the job queue could not place the job; try again", headers={"Retry-After": "5"}) from None
    status = await _db(api, job_status, job_id)
    if status is None:  # placed a moment ago, so only a deletion in between explains it
        raise Problem(503, "the job queue could not place the job; try again", headers={"Retry-After": "5"})
    LOGGER.info(
        "job placed",
        extra={"order_recipe_id": accepted.recipe.recipe_id, "job_status": status.status},
    )
    headers = {"Location": f"{_root(request)}{docs.PREFIX}/jobs/{job_id}"}
    if "respond-async" in request.headers.get("prefer", "").lower():
        headers["Preference-Applied"] = "respond-async"
    body = _status_info(_root(request), status, skipped=accepted.skipped_items)
    return JSONResponse(_dump(body), status_code=201, headers=headers)


# --- one job -------------------------------------------------------------------


async def _live_job(api: JobApi, job_id: str) -> JobStatus:
    """The job, or the one ``404`` for a job that is unknown, malformed, dismissed or expired (K8)."""
    status = await _db(api, job_status, job_id)
    if status is None or status.status == "dismissed" or status.expires_at <= datetime.now(UTC):
        raise _no_such_job()
    return status


@router.get(
    "/jobs/{jobID}",
    summary="The state of a job",
    response_model=StatusInfo,
    response_model_by_alias=True,
    responses=_PROBLEMS,
)
async def job(request: Request, jobID: str, api: Api) -> Response:
    status = await _live_job(api, jobID)
    return JSONResponse(_dump(_status_info(_root(request), status)))


@router.delete(
    "/jobs/{jobID}",
    summary="Dismiss a job",
    response_model=StatusInfo,
    response_model_by_alias=True,
    responses=_PROBLEMS,
)
async def dismiss_job(request: Request, jobID: str, api: Api) -> Response:
    await _live_job(api, jobID)
    status = await _db(api, dismiss, jobID)
    if status is None:
        raise _no_such_job()
    return JSONResponse(_dump(_status_info(_root(request), status)))


def _ready(status: JobStatus) -> JobStatus:
    """``status`` if the job has a result; else the ``404`` of a job that has none yet, or the error it failed with."""
    if status.status == "failed":
        raise _failed(status)
    if status.status != "successful" or status.result_id is None:
        raise Problem(404, "the job has not finished", type_=RESULT_NOT_READY, title="Result not ready")
    return status


def _results_document(root: str, status: JobStatus) -> dict[str, Any]:
    base = f"{root}{docs.PREFIX}/jobs/{status.job_id}/results"
    result = status.result or {}
    document: dict[str, Any] = {}
    for name, (file, title) in docs.OUTPUTS.items():
        link: dict[str, Any] = {"href": f"{base}/{file}", "type": RESULT_NAMES[file], "title": title}
        if name == "result":
            for key, member in (("bytes", "length"), ("width", "width"), ("height", "height"), ("bands", "bands")):
                if key in result:
                    link[member] = result[key]
            if "properties" in result:
                link["properties"] = result["properties"]
        document[name] = link
    return document


@router.get("/jobs/{jobID}/results", summary="The results of a finished job", responses=_PROBLEMS)
async def job_results(request: Request, jobID: str, api: Api) -> dict[str, Any]:
    status = _ready(await _live_job(api, jobID))
    return _results_document(_root(request), status)


def _download_name(body: dict[str, Any] | None, status: JobStatus, suffix: str) -> str:
    """Dataset, operators and date of the run — never an AOI, a hash, a ``jobID`` (adr/0015 §6.5, M4-08b K6)."""
    try:
        dataset = str(body["inputs"][0]["dataset"])  # type: ignore[index]
        operators = [str(step["op"]) for step in body["steps"]]  # type: ignore[index]
    except (KeyError, IndexError, TypeError):
        dataset, operators = "result", []
    day = (status.finished_at or status.created_at).astimezone(UTC).strftime("%Y%m%d")
    clean = _ascii(dataset)[:64] or "result"
    steps = "-".join(_ascii(op) for op in operators) or "export"
    if len(steps) > 40:
        steps = f"{len(operators)}-steps"
    return f"{clean}_{steps}_{day}{suffix}"


def _ascii(text: str) -> str:
    """Letters and digits of ASCII, ``-`` and ``_``; anything else becomes ``-`` (the store refuses the rest)."""
    return "".join(c if c.isascii() and (c.isalnum() or c in "-_") else "-" for c in text)


_SUFFIXES = {"result.tif": ".tif", "mask.tif": "_mask.tif", "recipe.json": "_recipe.json"}


@router.get(
    "/jobs/{jobID}/results/{name}",
    summary="A result file: a redirect to a signed URL, or recipe.json",
    responses={**_PROBLEMS, 303: {"description": "See Other: the signed URL, valid for 15 minutes"}},
)
async def job_result(request: Request, jobID: str, name: str, api: Api) -> Response:
    if name not in LINK_NAMES:
        raise Problem(404, "there is no such result", type_="urn:earthx:no-such-result", title="No such result")
    status = await _db(api, job_status, jobID)
    if status is None or status.status == "dismissed":
        raise _no_such_job()
    # From the end of the job's life, or 60 s before it, until the rows are gone: 410, not 404 (K8),
    # whatever state the job ended in — a failed job past its life does not tell its failure.
    if status.expires_at - datetime.now(UTC) < MIN_REMAINING:
        raise Problem(410, "the result has expired", type_="urn:earthx:gone", title="Gone")
    status = _ready(status)
    body = await _db(api, job_recipe, jobID)
    filename = _download_name(body, status, _SUFFIXES[name])
    if name == "recipe.json":
        return _recipe_document(api, body, status, filename)
    assert status.result_id is not None
    try:
        url = signed_download(api.store, status.result_id, name, not_after=status.expires_at, filename=filename)
    except ResultExpiring:
        raise Problem(410, "the result expires in less than a minute", type_="urn:earthx:gone", title="Gone") from None
    except ObjectStoreError:
        LOGGER.warning("a result link could not be signed")
        raise Problem(503, "the result store is not available; try again", headers={"Retry-After": "5"}) from None
    return Response(status_code=303, headers={"Location": url})


def _recipe_document(api: JobApi, body: dict[str, Any] | None, status: JobStatus, filename: str) -> Response:
    if body is None:
        raise _no_such_job()
    dataset = (body.get("inputs") or [{}])[0].get("dataset")
    try:
        config = api.registry.get(dataset) if isinstance(dataset, str) else None
    except UnknownDatasetError:
        config = None
    content = job_recipe_json(
        body, config=config, result=status.result or {}, started=status.started_at, finished=status.finished_at
    )
    return Response(
        content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- progress ----------------------------------------------------------------


async def _follow(jobID: str, api: Api) -> AsyncIterator[Subscription]:
    """Check the job, register the client, and unregister when the stream ends (also when the client leaves).

    A dependency, not the body of the stream: what turns a client away (``404``, ``503``) must
    be decided before the response starts.
    """
    await _live_job(api, jobID)
    try:
        sub = await api.events.subscribe(jobID)
    except (PoolTimeout, psycopg.OperationalError):
        LOGGER.warning("the queue database is not reachable")
        raise Problem(503, "the job queue is not reachable; try again", headers={"Retry-After": "5"}) from None
    except TooManyFollowers:
        raise Problem(
            503, "this server follows as many jobs as it can; try again", headers={"Retry-After": "5"}
        ) from None
    except LookupError:
        raise _no_such_job() from None
    try:
        yield sub
    finally:
        api.events.unsubscribe(sub)


@router.get(
    "/jobs/{jobID}/events",
    summary="Progress of a job as server-sent events",
    response_class=EventSourceResponse,
    responses=_PROBLEMS,
)
async def job_events(
    request: Request, sub: Annotated[Subscription, Depends(_follow)], api: Api
) -> AsyncIterator[ServerSentEvent]:
    """The state of the row first, then every change, as ``status`` events; the stream ends with the job."""
    root = _root(request)
    previous: JobStatus | None = None
    state = await sub.next()  # the row, read by the hub as soon as the client was registered
    while state is not None:
        if state != previous:
            yield ServerSentEvent(data=_dump(_status_info(root, state)), event="status")
            previous = state
        if state.status in TERMINAL:
            return
        state = await sub.next()


@router.api_route("/jobs/{rest:path}", methods=["GET", "DELETE"], include_in_schema=False)
async def no_such_path(rest: str) -> Response:
    """What is under ``/jobs/`` and is no route of this API (``a/b``, ``..``): the same ``404`` as a job that is not there."""
    raise _no_such_job()
