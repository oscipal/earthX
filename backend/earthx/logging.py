"""Structured JSON logging for the target architecture (architekturplan.md 12.4).

Every process logs one JSON object per line, tagged with the request ID of
whatever request is currently being handled. Geometries never reach a log
line with their exact coordinates (projektplan.md 7 Punkt 6): callers pass
them through :func:`summarize_geometry` first, which reduces even a
malformed geometry to a coarse bounding box, never the raw points.

Every HTTP process wires :func:`configure_logging` and :class:`RequestIdMiddleware`
in at startup (M3-16, `plans/m3/m3-02-konformitaetsbericht.md` K-01/K-02) and starts
uvicorn with ``--no-access-log``: uvicorn's own access log writes the raw query
string, the one place an AOI (``bbox``/``intersects``) would otherwise reach a log
line untouched. :class:`RequestIdMiddleware` is this process's access log instead —
one line per request, method/path/status/duration, never the query string.
"""

from __future__ import annotations

import json
import logging
import math
import re
import sys
import time
import uuid
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "x-request-id"

# An incoming request ID is only trusted if it looks like one of ours or a
# reasonable caller's — short and free of characters that could break a log
# line or a downstream header. Anything else is replaced, not rejected.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")

# M4-08b F6: the `jobID` in `/processing/jobs/{jobID}/…` is the way to a job's result (Q9: 128 bits,
# no account), so the access log names the route, not the job — the worker's logs never carry it
# either. Whatever stands in that segment, a valid identifier or not, is replaced.
# Anywhere in the path, so a prefix such as a `root_path` does not hide it, and through any
# number of slashes in front of the segment.
_JOB_PATH = re.compile(r"(/processing/jobs/)/*[^/]+")

# M4-19e: the identifier of a permalink is the way to an order with its area (Q8), kept out of the log
# like the `jobID`. Creating one has no segment after `permalinks`, so nothing is replaced there.
_PERMALINK_PATH = re.compile(r"(/processing/permalinks/)/*[^/]+")

# UI-01e: the identifier of a bundle is the way to the results of several jobs, kept out of the log like the `jobID`.
# Creating one has no segment after `bundles`, so nothing is replaced there.
_BUNDLE_PATH = re.compile(r"(/processing/bundles/)/*[^/]+")

# M4-13c-5: the `result_id` in `/results/{result_id}/…` of the tiler is the way to a result's tiles, as
# the `jobID` is the way to its files, and is kept out of the log the same way. The `results` segment
# after a job (`/processing/jobs/{jobID}/results/result.tif`) is the name of a file, not an identifier.
_RESULT_PATH = re.compile(r"(/results/)/*[^/]+")


def _hide_result_id(match: re.Match[str]) -> str:
    if match.string[: match.start()].endswith("{jobID}"):
        return match.group(0)
    return f"{match.group(1)}{{resultID}}"


def loggable_path(path: str | None) -> str | None:
    """``path`` as the access log writes it: a job's identifier replaced by ``{jobID}``, a result's by ``{resultID}``,
    a permalink's by ``{permalinkID}``, a bundle's by ``{bundleID}``."""
    if not path:
        return path
    path = _BUNDLE_PATH.sub(r"\1{bundleID}", _PERMALINK_PATH.sub(r"\1{permalinkID}", path))
    return _RESULT_PATH.sub(_hide_result_id, _JOB_PATH.sub(r"\1{jobID}", path))


# Coarse on purpose: a populated grid cell this size hides where inside it a
# point, polygon vertex, or bbox edge actually was.
_COORDINATE_PRECISION = 0

_REQUEST_ID: ContextVar[str | None] = ContextVar("earthx_request_id", default=None)
_RESERVED_LOG_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message"}


def get_request_id() -> str | None:
    """The request ID of the request currently being handled, if any."""
    return _REQUEST_ID.get()


def bind_request_id(request_id: str) -> Token[str | None]:
    """Bind a request ID to the current context; returns a token for reset."""
    return _REQUEST_ID.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    _REQUEST_ID.reset(token)


def new_request_id() -> str:
    return uuid.uuid4().hex


# NM4-57: GDAL writes the address of the file it could not read into its own message ("HTTP response code
# on <url>", "'/vsicurl/<url>' not recognized"), and rasterio passes that on to the logging module, as it
# puts the same text into the exception that carries it to a traceback. For a source with signed URLs
# (Planetary Computer) the address holds the token; for a job result (M4-13c-5) the `result_id`, the id of
# the tiler's key and a signature good for 15 minutes. So every address leaves a log line, wherever it
# stands: a URL with any scheme, and a GDAL path such as `/vsicurl/…` or `/vsis3/…` (but not `/vsimem/`, a
# name in memory). The formatter does this for the whole process, not a filter for one logger or thread.
ADDRESS_PLACEHOLDER = "<address>"
# The last character of an address is none of the marks that end a sentence or close a quotation.
_ADDRESS = re.compile(
    r"(?:/vsi(?!mem/)[A-Za-z0-9_]*/|[A-Za-z][A-Za-z0-9+.-]*://)[^\s'\"<>]*[^\s'\"<>.,;:)\]]|/vsi(?!mem/)[A-Za-z0-9_]*/"
)
# What stays after the addresses: a query that stands without its URL, and the `result_id` in a path.
_SIGNED_QUERY = re.compile(r"((?:X-Amz|X-Goog)-[A-Za-z0-9-]+|sig|access_token)=[A-Za-z0-9%._~+/=-]*")
_RESULT_ID_IN_TEXT = re.compile(r"(/results/)[A-Za-z0-9_-]{22}(?![A-Za-z0-9_-])")


def hide_addresses(text: str) -> str:
    """``text`` with every address replaced by ``<address>``, and the parts of a signed query that open a file."""
    if "/" not in text and "=" not in text:
        return text
    text = _ADDRESS.sub(ADDRESS_PLACEHOLDER, text)
    return _RESULT_ID_IN_TEXT.sub(r"\1{resultID}", _SIGNED_QUERY.sub(r"\1=<hidden>", text))


class JsonFormatter(logging.Formatter):
    """Renders each log record as one JSON object, one per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": hide_addresses(record.getMessage()),
            "request_id": get_request_id(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_ATTRS and key not in payload:
                payload[key] = hide_addresses(value) if isinstance(value, str) else value
        if record.exc_info:
            payload["exc_info"] = hide_addresses(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


# M3-16: both HTTP client libraries `gateway` may use (`architekturplan.md` Nachtrag
# 19.09.2026 to B8) log their own "HTTP Request: <method> <url> ..." line at INFO —
# the *full* URL, query string included, which is exactly where an AOI travels
# (`bbox`/`intersects`) on a coverage or federated-search call `gateway` makes
# upstream. Turning the root logger to INFO (below) would otherwise make that line
# start reaching stdout on its own, bypassing `gateway.client`'s own careful line
# (a query-string hash, never the string itself). Raised to WARNING, not silenced
# outright, so a real connection error from either still surfaces.
# M4-06 (adr/0015 §9.2): `botocore` and `urllib3`, the object store's client, write
# the access key id, the canonical request and the signature of a signed URL at
# DEBUG (measured, §3.2) — the same treatment.
_URL_LOGGING_LIBRARIES = ("httpx", "httpx2", "botocore", "urllib3")


def configure_logging(level: int = logging.INFO) -> None:
    """Configure the root logger to emit one JSON object per line to stdout.

    Idempotent: safe to call once per process startup even if a process
    type calls it more than once (no duplicated handlers). Every line it
    writes leaves the addresses GDAL and its libraries name out
    (:func:`hide_addresses`); the worker's child process, which starts without
    the supervisor's configuration, calls it too.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]
    for name in _URL_LOGGING_LIBRARIES:
        logging.getLogger(name).setLevel(max(level, logging.WARNING))
    _disable_uvicorn_access_log()
    _hide_addresses_in_uvicorn()


def _disable_uvicorn_access_log() -> None:
    """The same two lines uvicorn's own ``--no-access-log`` (``access_log=False``)
    runs (``uvicorn.config.Config.configure_logging``) — done here too, in code,
    so the guarantee holds whether or not a process is actually started with that
    flag (review of M3-16, PR #85: a local run following the README must be just
    as safe). ``uvicorn.access`` writes the full request line, query string
    included; it never reaches the root logger's own handler either way, because
    uvicorn gives it its own handler and turns ``propagate`` off — before this
    module is even imported (``Config.__init__`` runs uvicorn's own
    ``configure_logging()`` first; ``Config.load()`` only imports the ASGI app,
    and this call, afterwards), so this has to touch the same logger object
    uvicorn's own flag would, not the root logger.
    """
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers = []
    access_logger.propagate = False


class _HideAddresses(logging.Filter):
    """Takes the addresses out of the traceback of a record on its way to a handler whose formatter is not ours.

    Only the traceback: uvicorn's own message carries the address it listens on, which is meant to be read.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info:
            # `Formatter.format` keeps the text it finds here instead of formatting the exception again.
            record.exc_text = hide_addresses(logging.Formatter().formatException(record.exc_info))
        return True


def _hide_addresses_in_uvicorn() -> None:
    """Put :class:`_HideAddresses` on the handler uvicorn writes its own lines with.

    That handler prints plain text to stderr, past the formatter of :func:`configure_logging`; an unhandled
    error from a read ("Exception in ASGI application") would carry the address GDAL names in its message
    out of the process untouched (NM4-57). Uvicorn sets the handler up before it imports the app, so it is
    there when this runs.
    """
    for name in ("uvicorn", "uvicorn.error"):
        for handler in logging.getLogger(name).handlers:
            if not any(isinstance(entry, _HideAddresses) for entry in handler.filters):
                handler.addFilter(_HideAddresses())


class RequestIdMiddleware:
    """ASGI middleware: binds a request ID and writes the process's access log.

    Takes the ``X-Request-ID`` of an incoming request if present, otherwise
    generates one, makes it available to every log line written while
    handling the request (via :func:`get_request_id`), and echoes it back in
    the response header. Once the request is done, it writes exactly one
    access-log line — method, path, status, duration — and never the query
    string (K-01/K-02, `CLAUDE.md` "Unverrückbar"): ``scope["path"]`` never
    carries one (ASGI keeps it in the separate ``scope["query_string"]``,
    which this never reads), so an AOI travelling as ``bbox``/``intersects``
    never reaches this line whether or not it also reaches this process's own
    log lines through :func:`summarize_geometry`.

    Each HTTP process is expected to disable its own server's built-in access
    log (uvicorn's ``--no-access-log``) and rely on this line instead — that
    one already writes the full request line, query string included.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._logger = logging.getLogger("earthx.request")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER)
        request_id = incoming if incoming and _VALID_REQUEST_ID.match(incoming) else new_request_id()
        token = bind_request_id(request_id)
        status_code: int | None = None
        started_at = time.monotonic()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            self._logger.info(
                "request handled",
                extra={
                    "method": scope.get("method"),
                    "path": loggable_path(scope.get("path")),
                    "status": status_code,
                    "duration_ms": round((time.monotonic() - started_at) * 1000, 1),
                },
            )
            reset_request_id(token)


def summarize_geometry(geometry: Any) -> dict[str, Any]:
    """Reduce a GeoJSON geometry to a coarse bounding box, safe to log.

    Never returns exact coordinates, whether ``geometry`` is a valid GeoJSON
    geometry, malformed, or not a geometry at all — this never raises.
    """
    try:
        lons: list[float] = []
        lats: list[float] = []
        _collect_lon_lat(geometry, lons, lats)
    except Exception:
        return {"geometry": "invalid"}
    if not lons or not lats:
        return {"geometry": "invalid"}
    return {
        "geometry_type": geometry.get("type") if isinstance(geometry, dict) else None,
        "geometry_bbox": [
            _floor(min(lons)),
            _floor(min(lats)),
            _ceil(max(lons)),
            _ceil(max(lats)),
        ],
    }


def _floor(value: float) -> float:
    factor = 10**_COORDINATE_PRECISION
    return math.floor(value * factor) / factor


def _ceil(value: float) -> float:
    factor = 10**_COORDINATE_PRECISION
    return math.ceil(value * factor) / factor


def _collect_lon_lat(node: Any, lons: list[float], lats: list[float]) -> None:
    """Walk a GeoJSON geometry (or GeometryCollection) for coordinate pairs."""
    if isinstance(node, dict):
        if "geometries" in node:  # GeometryCollection
            for sub in node["geometries"]:
                _collect_lon_lat(sub, lons, lats)
            return
        _collect_lon_lat(node.get("coordinates"), lons, lats)
        return
    if not isinstance(node, (list, tuple)):
        return
    if len(node) >= 2 and all(_is_number(v) for v in node[:2]):
        lons.append(float(node[0]))
        lats.append(float(node[1]))
        return
    for item in node:
        _collect_lon_lat(item, lons, lats)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
