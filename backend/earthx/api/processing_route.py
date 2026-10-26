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
* **An estimate** (M4-13a, outside OGC) is the order's first six stages and the cost the plan
  computes from it: no ``HEAD``, no row in the queue, no ``recipe_id``. It sees what an order
  placed a moment later sees, except what only the version of an input shows (an asset the
  source no longer has): that is refused when the job is placed. ``no-store``.
* **A result link** answers ``303`` with a URL signed just now for 15 minutes and never past
  the result's expiry, ``Cache-Control: no-store``. ``recipe.json`` is built here from the
  job's own recipe; it does not lie in the object store.
* **``result.zip``** (M4-11b-1) is the exception to the redirect: ``api`` lays out one ZIP of result,
  mask, recipe and citation and streams it from the store, ``200``, or ``206`` for one range
  (``416`` behind the end), ``409`` for a result made before the files were measured, ``500`` if the
  stored files are not what the job reported, ``503`` if the store does not answer or four downloads
  are already running. The checks of the other
  links (``404``, ``410``) run on every request, a resumed one included.

``/crs/{code}`` (M4-13c-3, outside OGC) gives the unit of a target CRS from the EPSG database that ships
with ``pyproj``, so the panel can say what a cell size means: ``422`` for a code that is no EPSG code, is
unknown, or names no unit. It reads nothing from the network (:mod:`crs_info`).

``/bundles`` (UI-01e, outside OGC) is "Download all (ZIP)" of a batch. ``POST`` takes the ``jobID``s in the body (never in
the URL) and keeps them under an identifier of its own until the earliest of the jobs expires; ``GET`` lays out one ZIP
of the results of those jobs, ``NN_<stem>/`` per part with what its ``result.zip`` holds, resumable with ``Range`` and
``If-Range`` like that one. A part that has expired, failed or is not finished is listed in ``MISSING.txt``. An unknown,
a malformed and an expired identifier are one ``404``. The jobs and their ids are never logged.

``/permalinks`` (M4-19e, outside OGC) keeps an order and a small view under an identifier of its own, 30 days
from its creation. Creating answers ``201`` with the identifier, the expiry and a key that deletes it, once;
reading answers ``404`` for an identifier that is malformed, unknown or expired, and deleting answers the same
``404`` for a wrong key, so nobody can tell the cases apart. The order carries the area and is never logged.

Every answer under ``/jobs/``, ``/bundles`` and ``/permalinks`` and the placing of a job carry ``Cache-Control: no-store``.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import logging
import unicodedata
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import format_datetime
from functools import lru_cache
from http import HTTPStatus
from typing import Annotated, Any, Literal, TypeVar

import psycopg
from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute
from fastapi.sse import EventSourceResponse, ServerSentEvent
from psycopg_pool import ConnectionPool, PoolTimeout
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from starlette.concurrency import run_in_threadpool

from earthx.access.crop_rules import RECIPE_FILENAME, TEXT_FILES
from earthx.access.download import attribution_names_year
from earthx.api import processing_docs as docs
from earthx.api import result_zip
from earthx.api.crs_info import CrsRefused, crs_description
from earthx.api.intake import (
    OrderRefused,
    accept_order,
    check_recipe_hosts,
    estimate_order,
    job_recipe_json,
    job_side_files,
    recipe_json_with_methods,
)
from earthx.api.item_source import ItemSource, fetch_item_or_refuse
from earthx.api.job_events import TERMINAL, JobEvents, Subscription, TooManyFollowers
from earthx.api.result_zip import FileFacts, Layout, Member, RangeNotSatisfiable, byte_range, reported_files
from earthx.catalog.registry import (
    AcquisitionYearMissing,
    AcquisitionYears,
    Attributable,
    DatasetRegistry,
    RetiredDatasetError,
    UnknownDatasetError,
    acquisition_years,
)
from earthx.gateway import Gateway
from earthx.jobs import bundles, permalinks
from earthx.jobs.submit import JobStatus, RecipeIdTaken, dismiss, is_job_id, job_recipe, job_status, submit
from earthx.objectstore.errors import ObjectStoreError, ResultExpiring, ResultNotFound, StoreUnavailable
from earthx.objectstore.results import MIN_REMAINING, Store, open_result_range, result_size, signed_download
from earthx.processing import check_scope
from earthx.processing.errors import AoiOutsideInputs, JobTooLarge, RecipeInvalid, UnsupportedRecipe
from earthx.processing.methods import methods_of
from earthx.processing.operators import OperatorRegistry
from earthx.processing.plan import estimate
from earthx.processing.recipe import RECIPE_VERSION, job_recipe_document, loads_i_json, parse_request

LOGGER = logging.getLogger("earthx.api.processing")

__all__ = ["MAX_BODY_BYTES", "JobApi", "Problem", "router"]

#: The largest body of a job request (M4-08b K2): the size of an AOI file (`access.aoi_upload`).
MAX_BODY_BYTES = 1_048_576

_TYPE_BASE = "http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/"
NO_SUCH_JOB = f"{_TYPE_BASE}no-such-job"
NO_SUCH_PROCESS = f"{_TYPE_BASE}no-such-process"
RESULT_NOT_READY = f"{_TYPE_BASE}result-not-ready"
GONE = "urn:earthx:gone"
NO_BUNDLE = "urn:earthx:no-bundle"
NO_ACQUISITION_YEARS = "urn:earthx:no-acquisition-years"
_FAILED_TYPE = "urn:earthx:job-failed:"
_ORDER_TYPE = "urn:earthx:order-refused:"

#: The link ``methods``: the text of ``provenance.methods``, served as a file for clients of the API (NM4-08).
#: No download holds a file of this name.
METHODS_LINK = "methods.txt"
#: What a link under ``/results`` may name. `result.tif`, `mask.tif` and `export.zip` lie in the store,
#: `recipe.json` and `methods.txt` are built, `result.zip` is laid out from the stored files and the documents
#: `api` builds (M4-11b-1). A job has the names of its own output only (:func:`_names_of`).
LINK_NAMES = ("result.tif", "mask.tif", "export.zip", "result.zip", "recipe.json", METHODS_LINK)

BUNDLE = "result.zip"
#: The files of a raster result the ZIP carries from the store, in the order of the archive.
BUNDLE_FILES = ("result.tif", "mask.tif")
#: How many ZIP downloads one process serves at once (M4-11b K4): each holds a connection to the store
#: and one block of memory for as long as the download lasts. The next one is a ``503``.
MAX_BUNDLE_DOWNLOADS = 4
#: What is read from the store, and sent, at a time.
BUNDLE_BLOCK = 1024 * 1024

_ENVELOPE_KEYS = frozenset({"inputs", "outputs", "response"})

#: Unicode categories a field of ``aoiProvenance`` may not hold: control, format, surrogate,
#: private use, unassigned, line and paragraph separators.
_NOT_PLAIN_TEXT = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
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
    "disk_space": (
        500,
        "The worker has too little disk space for this job; choose a smaller area or fewer assets, or try later",
    ),
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


class DownloadSlots:
    """The places for ZIP downloads of one process: taken before the answer starts, freed when it ends."""

    def __init__(self, limit: int = MAX_BUNDLE_DOWNLOADS) -> None:
        self.limit = limit
        self.busy = 0

    def take(self) -> bool:
        if self.busy >= self.limit:
            return False
        self.busy += 1
        return True

    def free(self) -> None:
        self.busy = max(self.busy - 1, 0)


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
    bundles: DownloadSlots = field(default_factory=DownloadSlots)
    #: Public base URL of the tiler (``EARTHX_TILER_URL``); the only source of the absolute ``tiles`` link.
    tiler_base: str | None = None


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
            if "/jobs/" in path or "/permalinks" in path or "/bundles" in path or path.endswith(("/execution", "/estimate")):
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


class Estimate(BaseModel):
    """What a job is expected to cost; ``size`` and ``duration`` are named as in openEO's ``estimate`` (F2)."""

    model_config = ConfigDict(populate_by_name=True)

    #: Bytes of the result.
    size: int = Field(ge=0)
    #: ISO 8601 duration in seconds. An "about", from measurements on local files (adr/0014 §5.5).
    duration: str = Field(pattern=r"^PT[0-9]+(\.[0-9])?S$")
    output_pixels: int = Field(ge=0, alias="outputPixels")
    input_pixels: int = Field(ge=0, alias="inputPixels")
    input_bytes: int = Field(ge=0, alias="inputBytes")
    assets: int = Field(ge=0)
    #: Megapixels of the output times the factors of the steps (adr/0014 §5.5).
    units: float = Field(ge=0)


class EstimateDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    estimate: Estimate
    #: As for a placed job: items of the order the area of interest does not touch.
    skipped_items: list[str] = Field(default_factory=list, alias="skippedItems")


class ProblemDocument(BaseModel):
    type: str
    title: str
    status: int
    detail: str


_PROBLEMS: dict[int | str, dict[str, Any]] = {
    code: {"model": ProblemDocument, "description": HTTPStatus(code).phrase} for code in (400, 404, 410, 413, 422, 503)
}
#: What only the ZIP of a result adds: no ZIP for an old result, a range behind its end, and files that are not what was reported.
_ZIP_PROBLEMS: dict[int | str, dict[str, Any]] = {
    code: {"model": ProblemDocument, "description": HTTPStatus(code).phrase} for code in (409, 416, 500)
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
        except RetiredDatasetError as error:
            raise Problem(410, error.retired.message, type_=GONE, title="Gone") from None
        except UnknownDatasetError:
            raise Problem(400, f"no dataset {dataset[:64]!r}") from None
    return docs.process_description(_root(request), _operators(request), config)


@router.get("/crs/{code}", summary="The unit of a target CRS", responses=_PROBLEMS)
def crs_unit(code: str) -> JSONResponse:
    """What ``reproject``'s ``resolution`` is measured in for this target CRS (M4-13c-3); asks no one."""
    try:
        description = crs_description(code)
    except CrsRefused as error:
        raise Problem(422, str(error)) from None
    return JSONResponse(description, headers={"Cache-Control": "public, max-age=86400"})


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


def _unwrap(raw: bytes) -> tuple[bytes, dict[str, str] | None]:
    """The order inside the envelope ``{"inputs": {"recipe": {…}}}``, as JSON text; or the ``400`` that says why not.

    Only the part of the envelope the platform can honour is taken. An input given by
    reference is the part it cannot (F4, B8): nothing is fetched for it. Beside the order,
    an export or a raster job with an area may carry ``aoiProvenance`` (M4-11 F4, M4-30), returned
    checked as the second value.
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
    if not isinstance(inputs, dict) or docs.PROCESS_ID not in inputs or set(inputs) - {
        docs.PROCESS_ID,
        docs.AOI_PROVENANCE,
    }:
        raise Problem(
            400, f"inputs holds the input {docs.PROCESS_ID!r} and, for an order with an area, {docs.AOI_PROVENANCE!r}"
        )
    provenance = _aoi_provenance(inputs[docs.AOI_PROVENANCE]) if docs.AOI_PROVENANCE in inputs else None
    order = inputs[docs.PROCESS_ID]
    if (isinstance(order, dict) and "href" in order) or isinstance(order, str):
        raise Problem(400, docs.INLINE_ONLY)
    if isinstance(order, dict) and "value" in order:
        raise Problem(400, f"a qualified value is not taken; {docs.INLINE_ONLY}")
    if not isinstance(order, dict):
        raise Problem(400, f"the input {docs.PROCESS_ID!r} is the order itself, a JSON object")
    if document.get("response", "document") != "document":
        raise Problem(400, "response is document: a job's results are links, never the bytes")
    output = order.get("output")
    export = isinstance(output, dict) and output.get("kind") == "crop"
    _check_outputs(document.get("outputs"), docs.EXPORT_OUTPUTS if export else docs.RASTER_OUTPUTS)
    try:
        return json.dumps(order, ensure_ascii=False, allow_nan=False).encode("utf-8"), provenance
    except UnicodeEncodeError:
        # A lone surrogate (`"\ud800"`) is valid JSON text and not a string anyone can store.
        raise Problem(400, "not a JSON document: a string holds a character that has no UTF-8 form") from None


def _aoi_provenance(value: Any) -> dict[str, str]:
    """``aoiProvenance``: inline, some of the three fields, each one line of plain text (M4-11 F4).

    Stricter than the crop, which flattens such a value: here a value that would need it
    is refused, so what lands in ``ATTRIBUTION.txt`` is what was sent. Refused besides:
    control and format characters (bidirectional overrides, zero-width marks), lone
    surrogates and line or paragraph separators (:data:`_NOT_PLAIN_TEXT`).
    """
    if (isinstance(value, dict) and ("href" in value or "value" in value)) or isinstance(value, str):
        raise Problem(400, docs.INLINE_ONLY)
    fields = docs.AOI_PROVENANCE_FIELDS
    if not isinstance(value, dict) or not value or set(value) - set(fields):
        raise Problem(400, f"{docs.AOI_PROVENANCE} names some of {', '.join(fields)}")
    for text in value.values():
        if (
            not isinstance(text, str)
            or not 0 < len(text) <= docs.AOI_PROVENANCE_MAX_CHARS
            or text != text.strip()
            or any(unicodedata.category(char) in _NOT_PLAIN_TEXT for char in text)
        ):
            raise Problem(
                400,
                f"each field of {docs.AOI_PROVENANCE} is one line of 1 to {docs.AOI_PROVENANCE_MAX_CHARS} characters",
            )
    return dict(value)


def _check_outputs(outputs: Any, names: tuple[str, ...]) -> None:
    """``outputs`` names only outputs a job of this kind has: a raster job's or an export's (M4-11a)."""
    if outputs is None:
        return
    if not isinstance(outputs, dict) or set(outputs) - set(names):
        raise Problem(400, f"outputs names some of {', '.join(names)}")
    for entry in outputs.values():
        if not isinstance(entry, dict) or set(entry) - {"transmissionMode"}:
            raise Problem(400, "an output takes only transmissionMode")
        if entry.get("transmissionMode", _TRANSMISSION) != _TRANSMISSION:
            raise Problem(400, "a job's outputs are given by reference")


def _refused(error: OrderRefused) -> Problem:
    return Problem(error.status_code, error.detail, type_=f"{_ORDER_TYPE}{error.stage}")


_ORDER_BODY = {
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
}


@router.post(
    "/processes/{process_id}/execution",
    summary="Place a job (asynchronous only)",
    status_code=201,
    response_model=PlacedJob,
    response_model_by_alias=True,
    responses=_PROBLEMS,
    openapi_extra=_ORDER_BODY,
)
async def execute(request: Request, process_id: str, api: Api) -> Response:
    if process_id != docs.PROCESS_ID:
        raise Problem(404, "there is no such process", type_=NO_SUCH_PROCESS, title="No such process")
    order, provenance = _unwrap(await _read_body(request))
    try:
        accepted = await accept_order(
            order,
            registry=api.registry,
            operators=api.operators,
            item_source=api.item_source,
            gateway=api.gateway,
            aoi_provenance=provenance,
        )
        check_recipe_hosts(accepted.recipe, api.registry)
    except OrderRefused as error:
        raise _refused(error) from None
    try:
        check_scope(accepted.recipe)
    except UnsupportedRecipe as error:
        raise Problem(422, str(error), type_=f"{_ORDER_TYPE}scope") from None
    try:
        job_id = await _db(
            api,
            lambda conn, recipe: submit(
                conn,
                recipe,
                operators=api.operators,
                attachments=accepted.attachments,
                acquired_on=accepted.acquired_on,
                acquired_years=None
                if accepted.acquired_years is None
                else (accepted.acquired_years.first, accepted.acquired_years.last),
                scene_aoi=accepted.scene_aoi,
                aoi_provenance=accepted.aoi_provenance,
            ),
            accepted.recipe,
        )
    except JobTooLarge as error:
        raise Problem(413, str(error), type_=f"{_ORDER_TYPE}size") from None
    except AoiOutsideInputs as error:
        raise Problem(422, str(error), type_=f"{_ORDER_TYPE}aoi") from None
    except UnsupportedRecipe as error:
        # What the estimate cannot size (no pixel size, a target grid over the core's side): never a 500 (M4-25).
        raise Problem(422, str(error), type_=f"{_ORDER_TYPE}scope") from None
    except RecipeInvalid as error:
        # `submit` estimates the run to set its time limit, and that is the first place a band name the
        # item does not describe can fail: the check at acceptance could not tell (the same as the estimate).
        raise Problem(422, str(error), type_=f"{_ORDER_TYPE}applicable") from None
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


def _duration(seconds: float) -> str:
    return f"PT{seconds:.1f}S"


@router.post(
    "/processes/{process_id}/estimate",
    summary="Estimate the cost of an order before placing it (outside OGC API – Processes)",
    response_model=EstimateDocument,
    response_model_by_alias=True,
    responses=_PROBLEMS,
    openapi_extra=_ORDER_BODY,
)
async def estimate_order_cost(request: Request, process_id: str, api: Api) -> Response:
    if process_id != docs.PROCESS_ID:
        raise Problem(404, "there is no such process", type_=NO_SUCH_PROCESS, title="No such process")
    order, provenance = _unwrap(await _read_body(request))
    try:
        estimated = await estimate_order(
            order,
            registry=api.registry,
            operators=api.operators,
            item_source=api.item_source,
            aoi_provenance=provenance,
        )
    except OrderRefused as error:
        raise _refused(error) from None
    try:
        check_scope(estimated.recipe)
    except JobTooLarge as error:
        # As placing the job would answer (M4-11 F5, M4-12 F7): over the cap is a 413, not a 422.
        raise Problem(413, str(error), type_=f"{_ORDER_TYPE}size") from None
    except AoiOutsideInputs as error:
        raise Problem(422, str(error), type_=f"{_ORDER_TYPE}aoi") from None
    except UnsupportedRecipe as error:
        raise Problem(422, str(error), type_=f"{_ORDER_TYPE}scope") from None
    try:
        cost = estimate(estimated.recipe, api.operators)
    except JobTooLarge as error:
        raise Problem(413, str(error), type_=f"{_ORDER_TYPE}size") from None
    except AoiOutsideInputs as error:
        raise Problem(422, str(error), type_=f"{_ORDER_TYPE}aoi") from None
    except UnsupportedRecipe as error:
        raise Problem(422, str(error), type_=f"{_ORDER_TYPE}scope") from None
    except RecipeInvalid as error:
        # A band name the item does not describe is found here where the check before could not tell.
        raise Problem(422, str(error), type_=f"{_ORDER_TYPE}applicable") from None
    body = EstimateDocument(
        estimate=Estimate(
            size=cost.output_bytes,
            duration=_duration(cost.seconds),
            output_pixels=cost.output_pixels,
            input_pixels=cost.input_pixels,
            input_bytes=cost.input_bytes,
            assets=cost.assets,
            units=cost.units,
        ),
        skipped_items=list(estimated.skipped_items),
    )
    return JSONResponse(_dump(body))


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


def _is_export(status: JobStatus) -> bool:
    return (status.result or {}).get("files") == ["export.zip"]


def _bundle_possible(status: JobStatus) -> bool:
    """Whether the supervisor reported size and CRC of both rasters: only then is there a ZIP (M4-11b K5)."""
    return not _is_export(status) and reported_files(status.result, BUNDLE_FILES) is not None


def _outputs_of(status: JobStatus) -> tuple[str, ...]:
    """The outputs this job has: those of its kind, and the ZIP only where it can be laid out."""
    if _is_export(status):
        return docs.EXPORT_OUTPUTS
    return tuple(name for name in docs.RASTER_OUTPUTS if name != "bundle" or _bundle_possible(status))


def _names_of(status: JobStatus) -> tuple[str, ...]:
    """The files under ``/results`` of this job: those of its own output, and ``recipe.json``.

    The output ``tiles`` is a link to the tiler, not a file here.
    """
    return tuple(docs.OUTPUTS[name][0] for name in _outputs_of(status) if name != "tiles")


def _results_document(root: str, status: JobStatus, tiler_base: str | None) -> dict[str, Any]:
    base = f"{root}{docs.PREFIX}/jobs/{status.job_id}/results"
    result = status.result or {}
    document: dict[str, Any] = {}
    for name in _outputs_of(status):
        file, title = docs.OUTPUTS[name]
        href = docs.tiles_href(tiler_base, status.result_id) if name == "tiles" else f"{base}/{file}"
        link: dict[str, Any] = {"href": href, "type": docs.MEDIA_TYPES[file], "title": title}
        if name == "result":
            for key, member in (("bytes", "length"), ("width", "width"), ("height", "height"), ("bands", "bands")):
                if key in result:
                    link[member] = result[key]
            if "properties" in result:
                link["properties"] = result["properties"]
        if name == "export" and "bytes" in result:
            link["length"] = result["bytes"]
        document[name] = link
    return document


@router.get("/jobs/{jobID}/results", summary="The results of a finished job", responses=_PROBLEMS)
async def job_results(request: Request, jobID: str, api: Api) -> dict[str, Any]:
    status = _ready(await _live_job(api, jobID))
    return _results_document(_root(request), status, api.tiler_base)


def _day_of_name(status: JobStatus) -> str:
    """The date in the name of every download of a job: the one place of the rule (Otto, 14.10.2026).

    The UTC day the scene was acquired, ``YYYYMMDD``, where the job's scenes share one (the overpass,
    found at acceptance, ``catalog.registry.acquisition_day``). Where they do not — a dataset without a
    single day such as the DEM, scenes on several days, a job from before the day was kept — the UTC
    day the run ended (else the job was placed), ``run`` in front: ``run20261014``. Before 14.10.2026
    this was always the day of the run, without the prefix.
    """
    if status.acquired_on is not None:
        return status.acquired_on.strftime("%Y%m%d")
    return "run" + (status.finished_at or status.created_at).astimezone(UTC).strftime("%Y%m%d")


def _download_name(body: dict[str, Any] | None, status: JobStatus, suffix: str) -> str:
    """Dataset, operators and day (:func:`_day_of_name`) — never an AOI, a hash, a ``jobID`` (adr/0015 §6.5, M4-08b K6)."""
    try:
        dataset = str(body["inputs"][0]["dataset"])  # type: ignore[index]
        operators = [str(step["op"]) for step in body["steps"]]  # type: ignore[index]
    except (KeyError, IndexError, TypeError):
        dataset, operators = "result", []
    clean = _ascii(dataset)[:64] or "result"
    steps = "-".join(_ascii(op) for op in operators) or "export"
    if len(steps) > 40:
        steps = f"{len(operators)}-steps"
    return f"{clean}_{steps}_{_day_of_name(status)}{suffix}"


def _ascii(text: str) -> str:
    """Letters and digits of ASCII, ``-`` and ``_``; anything else becomes ``-`` (the store refuses the rest)."""
    return "".join(c if c.isascii() and (c.isalnum() or c in "-_") else "-" for c in text)


_SUFFIXES = {
    "result.tif": ".tif",
    "mask.tif": "_mask.tif",
    "export.zip": ".zip",
    BUNDLE: ".zip",
    "recipe.json": "_recipe.json",
    METHODS_LINK: "_methods.txt",
}


@router.get(
    "/jobs/{jobID}/results/{name}",
    summary="A result file: a redirect to a signed URL, recipe.json, or the ZIP of the result",
    responses={
        **_PROBLEMS,
        **_ZIP_PROBLEMS,
        200: {"description": "recipe.json, or all of result.zip", "content": {"application/zip": {}}},
        206: {"description": "Partial Content: one range of result.zip"},
        303: {"description": "See Other: the signed URL, valid for 15 minutes"},
    },
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
        raise Problem(410, "the result has expired", type_=GONE, title="Gone")
    status = _ready(status)
    if name == BUNDLE and not _is_export(status) and not _bundle_possible(status):
        # A result made before the supervisor measured its files (up to 7 days old, a cache hit
        # included): not computed afterwards, which would read gigabytes in a request and write to the
        # queue from `api`. It says so, and the single links still work (M4-11b-1, plan §3.1.2).
        raise Problem(
            409,
            "this result was created before bundles existed; use the single links (result.tif, mask.tif, recipe.json)",
            type_=NO_BUNDLE,
            title="No bundle",
        )
    if name not in _names_of(status):
        raise Problem(404, "there is no such result", type_="urn:earthx:no-such-result", title="No such result")
    body = await _db(api, job_recipe, jobID)
    status = await _with_derived_years(api, body, status)
    filename = _download_name(body, status, _SUFFIXES[name])
    if name == "recipe.json":
        return _recipe_document(api, body, status, filename)
    if name == METHODS_LINK:
        return _methods_document(api, body, status, filename)
    assert status.result_id is not None
    if name == BUNDLE:
        return await _bundle_response(request, api, body, status, filename)
    try:
        url = signed_download(api.store, status.result_id, name, not_after=status.expires_at, filename=filename)
    except ResultExpiring:
        raise Problem(410, "the result expires in less than a minute", type_=GONE, title="Gone") from None
    except ObjectStoreError:
        LOGGER.warning("a result link could not be signed")
        raise Problem(503, "the result store is not available; try again", headers={"Retry-After": "5"}) from None
    return Response(status_code=303, headers={"Location": url})


def _config_of(api: JobApi, body: dict[str, Any]) -> Attributable | None:
    """The registry entry of the job's dataset, or the retired dataset's record, which keeps its attribution
    and citation (adr/0017); ``None`` if the registry has never known it."""
    dataset = (body.get("inputs") or [{}])[0].get("dataset")
    return api.registry.attributable(dataset) if isinstance(dataset, str) else None


def _years_of(config: Attributable | None, status: JobStatus) -> AcquisitionYears | None:
    """The years the job's scenes were acquired in, which its attribution names (NM4-01).

    A job from before they were kept is given them first (:func:`_with_derived_years`). One whose
    attribution needs a year and who still has none has no honest one to give: the clock would put the
    year of the download there. It answers ``409`` and the order is to be placed again.
    """
    if status.acquired_years is not None:
        return AcquisitionYears(*status.acquired_years)
    if config is not None and attribution_names_year(config):
        raise Problem(
            409,
            "this job was placed before the years of acquisition were kept, and the dates of its scenes can no longer "
            "be read from the source; place the order again",
            type_=NO_ACQUISITION_YEARS,
            title="No acquisition years",
        )
    return None


async def _with_derived_years(api: JobApi, body: dict[str, Any] | None, status: JobStatus) -> JobStatus:
    """``status`` with the years of the scenes, read from the stored recipe's items if the job kept none (NM4-01).

    A job placed before the years were kept has the ids of its scenes in its recipe and no dates; the
    dates are the items' own, so they are asked of the item source again, as the intake asked them.
    Nothing is written back. Where that fails (an item gone, undated, or the source down) the status
    stays as it was and :func:`_years_of` answers ``409`` if the attribution needs a year.
    """
    config = _config_of(api, body or {})
    if body is None or status.acquired_years is not None or config is None or not attribution_names_year(config):
        return status
    try:
        entry = body["inputs"][0]
        ids = [item for group in entry["groups"] for item in group]
        items = await asyncio.gather(*(fetch_item_or_refuse(api.item_source, entry["dataset"], item) for item in ids))
        years = acquisition_years(items)
    except (OrderRefused, AcquisitionYearMissing, LookupError, TypeError):
        return status
    return dataclasses.replace(status, acquired_years=(years.first, years.last))


def _recipe_bytes(api: JobApi, body: dict[str, Any], status: JobStatus) -> bytes:
    """``recipe.json`` of the job: the file of its link, and the entry of its ZIP, with its methods text (NM4-08)."""
    config = _config_of(api, body)
    result = status.result or {}
    if _is_export(status) and isinstance(result.get("attribution"), list):
        # The times, the attribution and the methods text the export wrote into its own recipe.json, so that
        # both copies are one file (M4-11 K4) — also across a new year or a changed registry. An export from
        # before NM4-08 reported no text; it gets one from the registry as it is now.
        stored = result.get("methods")
        document = job_recipe_document(
            body,
            attribution=[str(entry) for entry in result["attribution"]],
            result=result,
            started=_instant(result.get("started")) or status.started_at,
            finished=_instant(result.get("finished")) or status.finished_at,
            methods=stored if isinstance(stored, str) and stored else None,
        )
        if methods_of(document) is not None:
            return document
    else:
        document = job_recipe_json(
            body,
            config=config,
            result=result,
            started=status.started_at,
            finished=status.finished_at,
            years=_years_of(config, status),
        )
    return recipe_json_with_methods(document, config, api.operators, acquired_on=status.acquired_on)


def _recipe_document(api: JobApi, body: dict[str, Any] | None, status: JobStatus, filename: str) -> Response:
    if body is None:
        raise _no_such_job()
    return Response(
        _recipe_bytes(api, body, status),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _methods_document(api: JobApi, body: dict[str, Any] | None, status: JobStatus, filename: str) -> Response:
    if body is None:
        raise _no_such_job()
    return Response(
        _methods_bytes(api, body, status),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _methods_bytes(api: JobApi, body: dict[str, Any], status: JobStatus) -> bytes:
    """The link ``methods`` of the job: the ``provenance.methods`` of the ``recipe.json`` it would serve, so the two never disagree."""
    text = methods_of(_recipe_bytes(api, body, status))
    assert text is not None
    return f"{text}\n".encode()


def _instant(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


# --- the ZIP of a raster result ----------------------------------------------


class _SlotResponse(StreamingResponse):
    """A streamed answer that gives its place back when it ends, however it ends.

    ``__call__`` is the one place that sees a client leaving, an error in the stream and a normal
    end alike; a generator that was never started has no ``finally`` to run.
    """

    def __init__(self, content: AsyncIterator[bytes], slots: DownloadSlots, **kwargs: Any) -> None:
        super().__init__(content, **kwargs)
        self._slots = slots

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._slots.free()
            # Not left to the garbage collector: the stream to the store is closed now, whether the
            # client left, the stream failed or it ended. A generator still running (it is being
            # cancelled) closes its own stream.
            with contextlib.suppress(Exception):
                await self.body_iterator.aclose()  # type: ignore[attr-defined]


async def _archive_bytes(api: JobApi, layout: Layout, first: int, last: int) -> AsyncIterator[bytes]:
    """Bytes ``first`` to ``last`` (both included) of the archive: documents from memory, rasters from the store.

    A raster is read in blocks of :data:`BUNDLE_BLOCK` in a thread; the stream to the store is closed when this
    generator ends or is dropped, so a client that leaves frees the connection. If the store answers with less
    than the report promised, the error ends the response before it is complete: the client sees a broken
    download, never a shorter archive that looks whole.
    """
    for segment in layout.segments(first, last + 1):
        if isinstance(segment, result_zip.Literal):
            yield segment.data
            continue
        remaining = segment.end - segment.begin
        assert segment.result_id is not None
        try:
            stream = await run_in_threadpool(
                open_result_range, api.store, segment.result_id, segment.source, segment.begin, segment.end - 1
            )
        except ObjectStoreError:
            LOGGER.warning("a result file could not be opened while the ZIP was sent")
            raise
        try:
            while remaining:
                block = await run_in_threadpool(stream.read, min(BUNDLE_BLOCK, remaining))
                if not block:
                    LOGGER.warning("the store ended a result file before the end of its report")
                    raise StoreUnavailable("the store ended a result file early")
                remaining -= len(block)
                yield block
        except ObjectStoreError:
            LOGGER.warning("a result file could not be read while the ZIP was sent")
            raise
        finally:
            with contextlib.suppress(Exception):
                stream.close()


async def _check_stored(api: JobApi, result_id: str, sizes: dict[str, int]) -> None:
    """Both rasters lie in the store with the size the supervisor reported, or the answer is an error."""
    try:
        for name, expected in sizes.items():
            if await run_in_threadpool(result_size, api.store, result_id, name) != expected:
                LOGGER.warning("a result file differs in size from its report", extra={"result_file": name})
                raise Problem(500, "the stored result is not what the job reported")
    except ResultNotFound:
        LOGGER.warning("a result file of a finished job is not in the store")
        raise Problem(500, "the stored result is not what the job reported") from None
    except ObjectStoreError:
        LOGGER.warning("the result store could not be asked for a size")
        raise Problem(503, "the result store is not available; try again", headers={"Retry-After": "5"}) from None


def _requested_range(request: Request, layout: Layout) -> tuple[int, int] | None:
    """The one range to send, or ``None`` for the whole archive; ``416`` if the range lies behind the end.

    ``If-Range`` makes the range depend on the archive still being the one the client began with.
    Only the strong validator of the layout counts: the date of the run does not change when the
    registry's attribution or citation does, and with them ``recipe.json`` and ``citation.bib``
    (RFC 9110 §13.1.5 wants a date to stand for the exact bytes). A date, or anything else, is the whole.
    """
    condition = request.headers.get("if-range")
    if condition is not None and condition.strip() != layout.etag:
        return None
    try:
        return byte_range(request.headers.get("range"), layout.total)
    except RangeNotSatisfiable:
        raise Problem(
            416, "the range begins behind the end of the ZIP", headers={"Content-Range": f"bytes */{layout.total}"}
        ) from None


def _finished_at(status: JobStatus) -> datetime:
    return (status.finished_at or status.created_at).astimezone(UTC).replace(microsecond=0)


def _job_members(api: JobApi, body: dict[str, Any], status: JobStatus, facts: dict[str, FileFacts], folder: str) -> list[Member]:
    """The files of a raster job's ZIP below ``folder``: the one place of its content (M4-11b-1, M4-30).

    The rasters from the store, then the files of the crop's ZIP beside them in its order (`TEXT_FILES`, the one
    definition); the registry no longer knowing the dataset leaves out the citation and the notice, as it left out
    the citation before. ``result.zip`` of the job and every part of a bundle are laid out by this function.
    """
    members = [
        Member.stored(f"{folder}/{name}", name, facts[name], result_id=status.result_id) for name in BUNDLE_FILES
    ]
    config = _config_of(api, body)
    documents = {
        name: text.encode("utf-8")
        for name, text in job_side_files(
            config,
            body,
            finished=_finished_at(status),
            years=_years_of(config, status),
            scene_aoi=status.scene_aoi,
            aoi_provenance=status.aoi_provenance,
        ).items()
    }
    documents[RECIPE_FILENAME] = _recipe_bytes(api, body, status)
    members.extend(Member.of_bytes(f"{folder}/{name}", documents[name]) for name in TEXT_FILES if name in documents)
    return members


async def _zip_response(request: Request, api: JobApi, layout: Layout, filename: str) -> Response:
    """``layout`` as the answer: all of it or the one range asked for, with the validators a resumed download needs."""
    last_modified = format_datetime(layout.modified, usegmt=True)
    chosen = _requested_range(request, layout)
    first, last = chosen if chosen is not None else (0, layout.total - 1)
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(last - first + 1),
        "Content-Disposition": f'attachment; filename="{filename}"',
        "ETag": layout.etag,
        "Last-Modified": last_modified,
    }
    if chosen is not None:
        headers["Content-Range"] = f"bytes {first}-{last}/{layout.total}"
    if not api.bundles.take():
        raise Problem(503, "this server sends as many ZIP files as it can; try again", headers={"Retry-After": "5"})
    return _SlotResponse(
        _archive_bytes(api, layout, first, last),
        api.bundles,
        status_code=206 if chosen is not None else 200,
        media_type=docs.MEDIA_TYPES[BUNDLE],
        headers=headers,
    )


async def _bundle_response(
    request: Request, api: JobApi, body: dict[str, Any] | None, status: JobStatus, filename: str
) -> Response:
    """``result.zip`` (M4-11b-1): a folder with result, mask, recipe and citation, one range of it or all.

    Answered by `api` itself, not by a redirect: ``recipe.json`` belongs to this job, the rasters to a run
    that other orders share. The same checks as for every link run before (``404``, ``410`` from 60 s
    before the end of the result's life), so a resumed download after the end is a ``410`` too.
    """
    facts = reported_files(status.result, BUNDLE_FILES)
    if body is None or facts is None or status.result_id is None:
        raise _no_such_job()
    members = _job_members(api, body, status, facts, filename.removesuffix(".zip"))
    layout = Layout(members, modified=_finished_at(status))
    await _check_stored(api, status.result_id, {name: facts[name].bytes for name in BUNDLE_FILES})
    return await _zip_response(request, api, layout, filename)


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


# --- permalinks ----------------------------------------------------------------

NO_SUCH_PERMALINK = "urn:earthx:no-such-permalink"
DELETE_KEY_HEADER = "X-Delete-Key"


def _no_such_permalink() -> Problem:
    return Problem(404, "there is no such permalink", type_=NO_SUCH_PERMALINK, title="No such permalink")


class PermalinkRange(BaseModel):
    """The range and colormap of the preview as it was on screen; ``colormap`` empty for none."""

    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)

    vmin: float
    vmax: float
    colormap: str = Field(max_length=32, pattern=r"^[A-Za-z0-9_]*$")


class PermalinkView(BaseModel):
    """What a permalink restores besides the order: the map's centre and zoom and the preview's range."""

    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)

    center: list[float] = Field(min_length=2, max_length=2)
    zoom: float = Field(ge=0, le=24)
    range: PermalinkRange | None = None

    @model_validator(mode="after")
    def _in_the_world(self) -> PermalinkView:
        lon, lat = self.center
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError("center is a longitude and a latitude")
        return self


def _permalink_body(raw: bytes, operators: OperatorRegistry) -> dict[str, Any]:
    """``{"order": …, "view": …}`` checked: the order as an order is (strictly, no ``resolved``), the view by its model."""
    try:
        document = loads_i_json(raw)
    except RecipeInvalid as error:
        raise Problem(400, str(error)) from None
    if not isinstance(document, dict) or set(document) != {"order", "view"}:
        raise Problem(400, "the request is a JSON object with the members order and view")
    try:
        order_text = json.dumps(document["order"], ensure_ascii=False, allow_nan=False)
        order = parse_request(order_text, operators)
    except (RecipeInvalid, UnicodeEncodeError) as error:
        raise Problem(422, str(error) if isinstance(error, RecipeInvalid) else "the order is not valid text") from None
    try:
        view = PermalinkView.model_validate(document["view"])
    except ValidationError as error:
        # Where and what kind, never the value.
        reasons = "; ".join(f"{'.'.join(str(part) for part in e['loc'])}: {e['type']}" for e in error.errors()[:5])
        raise Problem(422, f"invalid view: {reasons}") from None
    return {
        "order": json.loads(order_text),
        "view": view.model_dump(mode="json"),
        "dataset": order.inputs[0].dataset,
    }


@router.post("/permalinks", summary="Keep an order and a view under a link", status_code=201, responses=_PROBLEMS)
async def create_permalink(request: Request, api: Api) -> Response:
    body = _permalink_body(await _read_body(request), api.operators)
    dataset = body.pop("dataset")
    try:
        api.registry.get(dataset)
    except RetiredDatasetError as error:
        # Reading a stored link stays a 200 (the order is the user's); a new one for a gone dataset is not made.
        raise Problem(410, error.retired.message, type_=GONE, title="Gone") from None
    except UnknownDatasetError:
        pass
    created = await _db(api, permalinks.create, body)
    LOGGER.info("permalink created", extra={"order_dataset": dataset})
    return JSONResponse(
        {"id": created.permalink_id, "expires_at": created.expires_at.isoformat(), "delete_key": created.delete_key},
        status_code=201,
    )


@router.get("/permalinks/{permalink_id}", summary="The order and view of a permalink", responses=_PROBLEMS)
async def read_permalink(permalink_id: str, api: Api) -> Response:
    found = await _db(api, permalinks.read, permalink_id) if permalinks.is_permalink_id(permalink_id) else None
    if found is None:
        raise _no_such_permalink()
    body, expires_at = found
    LOGGER.info("permalink read")
    return JSONResponse({**body, "expires_at": expires_at.isoformat()})


@router.delete("/permalinks/{permalink_id}", summary="Delete a permalink with its key", status_code=204, responses=_PROBLEMS)
async def delete_permalink(request: Request, permalink_id: str, api: Api) -> Response:
    key = request.headers.get(DELETE_KEY_HEADER)
    if key is None:
        raise Problem(400, f"send the key you were given as {DELETE_KEY_HEADER}")
    if not permalinks.is_permalink_id(permalink_id) or not await _db(api, permalinks.delete, permalink_id, key):
        raise _no_such_permalink()
    LOGGER.info("permalink deleted")
    return Response(status_code=204)


# --- bundles -------------------------------------------------------------------

NO_SUCH_BUNDLE = "urn:earthx:no-such-bundle"
#: What a bundle may hold in rasters, the sum of ``result.tif`` and ``mask.tif`` of its parts (UI-01 §6.12, question 7).
MAX_BUNDLE_BYTES = 25_000_000_000
MISSING = "MISSING.txt"

_EXPIRED = "expired"
_FAILED = "failed"
_UNFINISHED = "not finished"
_UNAVAILABLE = "no longer available"
_UNSUPPORTED = "not a raster result"
_NO_YEARS = "year of acquisition unknown"


@dataclass(frozen=True)
class _Part:
    """One job of a bundle as it is now: its place in the list (from 1), its rows, and why it is not in the ZIP."""

    number: int
    status: JobStatus | None
    body: dict[str, Any] | None
    #: ``None`` if the job has a raster result that can be laid out.
    reason: str | None

    @property
    def stem(self) -> str | None:
        """The name of the part inside the ZIP, as the name of its own download without the suffix."""
        return None if self.status is None or self.body is None else _download_name(self.body, self.status, "")

    def without(self, reason: str) -> _Part:
        return dataclasses.replace(self, reason=reason)


def _no_such_bundle() -> Problem:
    return Problem(404, "there is no such bundle", type_=NO_SUCH_BUNDLE, title="No such bundle")


def _why_not(status: JobStatus | None) -> str | None:
    """Why a job cannot go into a bundle (the words of ``MISSING.txt``), else ``None``."""
    if status is None or status.status == "dismissed":
        return _UNAVAILABLE
    if status.expires_at - datetime.now(UTC) < MIN_REMAINING:
        return _EXPIRED
    if status.status == "failed":
        return _FAILED
    if status.status != "successful" or status.result_id is None:
        return _UNFINISHED
    return None if _bundle_possible(status) else _UNSUPPORTED


def _read_parts(conn: psycopg.Connection, job_ids: list[str]) -> list[_Part]:
    """The jobs of a list as they are now, in its order; a job whose rows are gone has neither status nor recipe."""
    rows = [(job_status(conn, job_id), job_recipe(conn, job_id)) for job_id in job_ids]
    return [_Part(number, status, body, _why_not(status)) for number, (status, body) in enumerate(rows, start=1)]


def _raster_bytes(part: _Part) -> int:
    facts = reported_files(part.status.result, BUNDLE_FILES) if part.status else None
    return sum(fact.bytes for fact in (facts or {}).values())


def _jobs_of(raw: bytes) -> list[str]:
    """The ``jobID``s of the body ``{"jobs": […]}``: 1 to 25, each in the form of one, none twice."""
    try:
        document = loads_i_json(raw)
    except RecipeInvalid as error:
        raise Problem(400, str(error)) from None
    if not isinstance(document, dict) or set(document) != {"jobs"}:
        raise Problem(400, "the request is a JSON object with the member jobs")
    jobs = document["jobs"]
    if not isinstance(jobs, list) or not 1 <= len(jobs) <= bundles.MAX_PARTS:
        raise Problem(422, f"jobs is a list of 1 to {bundles.MAX_PARTS} job identifiers")
    if not all(is_job_id(job) for job in jobs):
        raise Problem(422, "every entry of jobs is a job identifier")
    if len(set(jobs)) != len(jobs):
        raise Problem(422, "no job is named twice")
    return jobs


@router.post("/bundles", summary="Keep a list of jobs for one ZIP", status_code=201, responses=_PROBLEMS)
async def create_bundle(request: Request, api: Api) -> Response:
    job_ids = _jobs_of(await _read_body(request))
    parts = await _db(api, _read_parts, job_ids)
    if any(part.reason == _UNSUPPORTED for part in parts):
        raise Problem(422, "an export or a result without measured files cannot go into a bundle")
    kept = [part for part in parts if part.reason is None]
    if not kept:
        if all(part.reason in (_EXPIRED, _UNAVAILABLE) for part in parts):
            raise Problem(410, "no job of the list has a result any more", type_=GONE, title="Gone")
        raise Problem(409, "no job of the list has finished", type_=NO_BUNDLE, title="Nothing to bundle")
    total = sum(_raster_bytes(part) for part in kept)
    if total > MAX_BUNDLE_BYTES:
        raise Problem(413, f"the rasters add up to {total} bytes; a bundle holds at most {MAX_BUNDLE_BYTES}")
    expires = min(part.status.expires_at for part in kept if part.status)
    bundle_id = await _db(api, bundles.create, job_ids, expires)
    LOGGER.info("bundle created", extra={"parts": len(parts), "bundled": len(kept)})
    href = f"{_root(request)}{docs.PREFIX}/bundles/{bundle_id}"
    return JSONResponse({"href": href, "expires": expires.isoformat()}, status_code=201, headers={"Location": href})


async def _lay_out_parts(api: JobApi, parts: list[_Part], folder: str) -> tuple[list[Member], list[_Part], list[_Part]]:
    """The members of every part that can be laid out, those parts, and the parts left out with their reason."""
    members: list[Member] = []
    included: list[_Part] = []
    left_out: list[_Part] = []
    for part in parts:
        status, body, stem = part.status, part.body, part.stem
        facts = reported_files(status.result, BUNDLE_FILES) if status else None
        if part.reason is not None or status is None or body is None or stem is None or facts is None:
            left_out.append(part if part.reason is not None else part.without(_UNAVAILABLE))
            continue
        status = await _with_derived_years(api, body, status)
        try:
            members += _job_members(api, body, status, facts, f"{folder}/{part.number:02d}_{stem}")
        except Problem as problem:
            if problem.type != NO_ACQUISITION_YEARS:
                raise
            left_out.append(part.without(_NO_YEARS))
        else:
            included.append(part)
    return members, included, left_out


def _missing_text(left_out: list[_Part]) -> bytes:
    """One line per part left out: its number, its name if its rows are still there, and why."""
    lines = [
        f"{part.number:02d}: {part.reason}" if part.stem is None else f"{part.number:02d} {part.stem}: {part.reason}"
        for part in left_out
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


@router.get(
    "/bundles/{bundle_id}",
    summary="The results of a list of jobs as one ZIP, whole or by range",
    responses={
        **_PROBLEMS,
        **_ZIP_PROBLEMS,
        200: {"description": "all of the ZIP", "content": {"application/zip": {}}},
        206: {"description": "Partial Content: one range of the ZIP"},
    },
)
async def read_bundle(request: Request, bundle_id: str, api: Api) -> Response:
    found = await _db(api, bundles.read, bundle_id) if bundles.is_bundle_id(bundle_id) else None
    if found is None:
        raise _no_such_bundle()
    parts = await _db(api, _read_parts, found[0])
    first = next((part.stem for part in parts if part.reason is None), None)
    if first is None:
        raise Problem(410, "no part of this bundle has a result any more", type_=GONE, title="Gone")
    filename = f"{first}_batch-{len(parts)}.zip"
    folder = filename.removesuffix(".zip")
    members, included, left_out = await _lay_out_parts(api, parts, folder)
    if not included:
        raise Problem(410, "no part of this bundle has a result any more", type_=GONE, title="Gone")
    if left_out:
        members.append(Member.of_bytes(f"{folder}/{MISSING}", _missing_text(left_out)))
    layout = Layout(members, modified=max(_finished_at(part.status) for part in included if part.status))
    await asyncio.gather(
        *(
            _check_stored(api, part.status.result_id, {name: fact.bytes for name, fact in facts.items()})
            for part in included
            if part.status and part.status.result_id and (facts := reported_files(part.status.result, BUNDLE_FILES))
        )
    )
    LOGGER.info("bundle read", extra={"parts": len(parts), "missing": len(left_out)})
    return await _zip_response(request, api, layout, filename)


@router.api_route("/jobs/{rest:path}", methods=["GET", "DELETE"], include_in_schema=False)
async def no_such_path(rest: str) -> Response:
    """What is under ``/jobs/`` and is no route of this API (``a/b``, ``..``): the same ``404`` as a job that is not there."""
    raise _no_such_job()
