"""Structured JSON logging for the target architecture (architekturplan.md 12.4).

Every process logs one JSON object per line, tagged with the request ID of
whatever request is currently being handled. Geometries never reach a log
line with their exact coordinates (projektplan.md 7 Punkt 6): callers pass
them through :func:`summarize_geometry` first, which reduces even a
malformed geometry to a coarse bounding box, never the raw points.
"""

from __future__ import annotations

import json
import logging
import math
import re
import sys
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


class JsonFormatter(logging.Formatter):
    """Renders each log record as one JSON object, one per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_ATTRS and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Configure the root logger to emit one JSON object per line to stdout.

    Idempotent: safe to call once per process startup even if a process
    type calls it more than once (no duplicated handlers).
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]


class RequestIdMiddleware:
    """ASGI middleware: binds a request ID for the lifetime of each request.

    Takes the ``X-Request-ID`` of an incoming request if present, otherwise
    generates one, makes it available to every log line written while
    handling the request (via :func:`get_request_id`), and echoes it back
    in the response header.
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

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        self._logger.info("request started", extra={"path": scope.get("path")})
        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            self._logger.info("request finished", extra={"path": scope.get("path")})
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


# M3-08 F7a: uvicorn's own access logger writes the request's raw query string
# verbatim (``uvicorn.protocols.utils.get_path_with_query_string``) — the one place
# a ``GET /stac/search?intersects=…`` or ``GET /coverage/{id}?bbox=…`` AOI would
# otherwise reach a log line untouched, coordinates and all, bypassing the redaction
# every other log line in this process already gets through :func:`summarize_geometry`
# or this module's own ``HTTPException`` texts. Only the query string is touched — a
# `POST` body never reaches this logger at all.
_REDACTED_QUERY_KEYS = ("bbox", "intersects")
_QUERY_VALUE_PATTERN = re.compile(r"(?P<prefix>[?&](?:" + "|".join(_REDACTED_QUERY_KEYS) + r")=)(?P<value>[^&\s\"]*)")


def redact_query_string(text: str) -> str:
    """Blanks the values of ``bbox``/``intersects`` in a URL's query string,
    leaving the path and every other parameter as they were."""
    return _QUERY_VALUE_PATTERN.sub(lambda match: match.group("prefix") + "…", text)


class AccessLogRedactionFilter(logging.Filter):
    """Attached to ``uvicorn.access`` by :func:`redact_access_log_coordinates`.

    Uvicorn logs one line per request as
    ``'%s - "%s %s HTTP/%s" %d'`` with ``(client_addr, method, path_with_query,
    http_version, status)`` as the record's ``args``
    (``uvicorn/protocols/http/h11_impl.py``) — a plain :class:`logging.Filter` is
    the one hook that runs before that tuple is formatted into text, so this
    rewrites just the one argument that can carry an AOI, in place.
    """

    _PATH_ARG_INDEX = 2

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) > self._PATH_ARG_INDEX and isinstance(args[self._PATH_ARG_INDEX], str):
            patched = list(args)
            patched[self._PATH_ARG_INDEX] = redact_query_string(patched[self._PATH_ARG_INDEX])
            record.args = tuple(patched)
        return True


def redact_access_log_coordinates() -> None:
    """Attaches :class:`AccessLogRedactionFilter` to ``uvicorn.access``, once.

    Called from ``earthx.api.main`` at process start-up, after uvicorn's own
    ``Config.configure_logging`` has already run (it runs in ``Config.__init__``,
    before the ASGI app is imported) — so this adds to what uvicorn set up rather
    than racing it. Idempotent, in case a process ever calls it twice.
    """
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(existing, AccessLogRedactionFilter) for existing in logger.filters):
        logger.addFilter(AccessLogRedactionFilter())
