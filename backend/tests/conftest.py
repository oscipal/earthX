"""Shared fixtures.

Every test in this suite relies on this: no test may open a network
connection. Tests run in CI and in cloud sessions, where external data
sources are not reachable (docs/adr/0002-testaufteilung.md). A test that
tries anyway must fail loudly instead of hanging until a timeout.
"""

from __future__ import annotations

import json
import logging
import shutil
import socket
import tempfile
from collections.abc import Iterator
from typing import Any

import pytest
import rasterio.session

from earthx.logging import JsonFormatter
from earthx.readers.limits import limit_reads
from tests.logging_guard import COLLECTING, LoggingGuard, summary
from tests.worker_database import TestRun, drop_worker_database, load_session_env, start_run, use_run_database

# rasterio in the test process as in the image: without an AWS session (NM4-23).
#
# `boto3` is only in the dev lock, through `moto`; the image never has it
# (test_objectstore_boundary.py). rasterio checks for it once, at import, and keeps
# the result in `rasterio.session.boto3`. While that name holds the module, every
# `rasterio.Env()` builds an `AWSSession`: about 100 ms of CPU each (NM4-26 B9), and
# whatever `AWS_*` it finds goes on to GDAL (adr/0015 §3.1). Clearing the name sends
# rasterio down its own path for a missing boto3, `DummySession`, as in the image.
# `boto3` and `botocore` themselves stay where they are: `moto` patches botocore,
# and the store's client uses botocore alone, so the object store tests check what
# they checked before (tests/earthx/objectstore/test_rasterio_session.py).
rasterio.session.boto3 = None

_RUN = pytest.StashKey[TestRun]()
_LOGGING = pytest.StashKey[LoggingGuard]()
_DATABASE = pytest.StashKey[tuple[str, str]]()


def pytest_configure(config: pytest.Config) -> None:
    """The run's databases (tests/worker_database.py): here, before anything is collected.

    The controller of an xdist run, or the one process of a serial run, takes the run's id and
    migrates its template; each worker, and a serial run itself, then points `PGDATABASE` at a copy
    of it, so every fixture and every spawned child reads that one.
    """
    config.stash[_LOGGING] = LoggingGuard()
    load_session_env()
    workerinput = getattr(config, "workerinput", None)
    if workerinput is None:
        made = start_run()
        if made is None:
            return
        config.stash[_RUN] = made
        if not config.getoption("numprocesses", None) and not config.getoption("collectonly"):
            used = use_run_database(made.run, made.configured, "main")
            if used is not None:
                config.stash[_DATABASE] = used
        return
    run = workerinput.get("earthx_run")
    if run is not None:
        used = use_run_database(run, workerinput["earthx_configured"], workerinput["workerid"])
        if used is not None:
            config.stash[_DATABASE] = used


@pytest.hookimpl(optionalhook=True)
def pytest_configure_node(node: Any) -> None:
    """Hands the run's id to each xdist worker (`pytest-xdist` hook, run by the controller)."""
    made = node.config.stash.get(_RUN, None)
    if made is not None:
        node.workerinput["earthx_run"] = made.run
        node.workerinput["earthx_configured"] = made.configured


@pytest.fixture(autouse=True)
def logging_as_found(request: pytest.FixtureRequest) -> Iterator[None]:
    """Puts `logging` back as the run found it after each test (tests/logging_guard.py)."""
    guard = request.config.stash[_LOGGING]
    guard.learn()
    guard.restore(COLLECTING)
    yield
    guard.restore(request.node.nodeid, note=request.node.get_closest_marker("changes_logging") is None)


def pytest_sessionfinish(session: pytest.Session) -> None:
    workeroutput = getattr(session.config, "workeroutput", None)
    if workeroutput is not None:
        workeroutput["earthx_logging_changed"] = session.config.stash[_LOGGING].changed


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node: Any, error: object) -> None:
    """Collects what each xdist worker's tests left changed in `logging` (`pytest-xdist` hook)."""
    changed = getattr(node, "workeroutput", {}).get("earthx_logging_changed", [])
    node.config.stash[_LOGGING].changed.extend((test, names) for test, names in changed)


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter, config: pytest.Config) -> None:
    guard = config.stash.get(_LOGGING, None)
    changed = guard.changed if guard is not None else []
    if changed:
        terminalreporter.section("logging changed by a test and put back (M5-61)")
        for line in summary(changed):
            terminalreporter.line(line)


def pytest_unconfigure(config: pytest.Config) -> None:
    used = config.stash.get(_DATABASE, None)
    if used is not None:
        drop_worker_database(*used)
    made = config.stash.get(_RUN, None)
    if made is not None:
        made.end()


#: A full run writes about 10 GB of `tmp_path` (M5-61 §2.5); below this a session disk can fill up during a run.
LOW_DISK_BYTES = 12 * 1024**3


def low_disk_warning(directory: str, free_bytes: int) -> str | None:
    if free_bytes >= LOW_DISK_BYTES:
        return None
    return (
        f"WARNING: only {free_bytes / 1024**3:.1f} GB free under {directory}; a full run needs about 10 GB "
        "for its temporary files. Remove old /tmp/pytest-of-* directories first."
    )


def pytest_report_header(config: pytest.Config) -> str | None:
    directory = tempfile.gettempdir()
    return low_disk_warning(directory, shutil.disk_usage(directory).free)


_ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", ""})


def _without_measured_time(fields: dict[str, object]) -> dict[str, object]:
    """`fields` minus the access log's `duration_ms`, once it is checked to be a number.

    `RequestIdMiddleware` measures it (`earthx/logging.py`), so nothing a request carries can
    be in it, but a digit-string marker can match inside it by chance: "9.5" in 59.5 (NM4-23).
    """
    rest = dict(fields)
    duration = rest.pop("duration_ms", None)
    assert duration is None or isinstance(duration, int | float), duration
    return rest


def log_line_without_timestamp(line: str) -> str:
    """A JSON log line minus its `timestamp`.

    The timestamp carries microseconds, so a digit-string marker (a coordinate such as
    "9.0") can match inside it by chance. What a log may leak is in the message and the
    fields, never in the time.
    """
    payload = json.loads(line)
    del payload["timestamp"]
    return json.dumps(payload)


_STANDARD_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}


def own_log_fields(record: logging.LogRecord) -> dict[str, object]:
    """The fields a caller added with `extra=`: no `logging.LogRecord` standard attribute, no time."""
    return {key: value for key, value in record.__dict__.items() if key not in _STANDARD_RECORD_ATTRS}


def own_log_text(record: logging.LogRecord) -> str:
    """The message and the caller's own fields of a record, as one string for a "never logged" search.

    `str(record.__dict__)` also holds `created`, `relativeCreated`, `msecs`, `thread` and `process`;
    a digit-string marker such as "9.01" matches inside them by chance (`relativeCreated` 25239.017...).
    The measured `duration_ms` of the access log is left out for the same reason.
    """
    return record.getMessage() + " " + json.dumps(_without_measured_time(own_log_fields(record)), default=str)


def format_without_timestamp(record: logging.LogRecord) -> str:
    return log_line_without_timestamp(JsonFormatter().format(record))


class NetworkAccessError(RuntimeError):
    """Raised when a test tries to reach the network."""


def _host_of(address: object) -> str:
    if isinstance(address, tuple) and address:
        return str(address[0])
    return str(address)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail any attempt to open a non-local socket or resolve a hostname."""
    real_connect = socket.socket.connect

    def guarded_connect(self: socket.socket, address: object) -> None:
        host = _host_of(address)
        if host not in _ALLOWED_HOSTS:
            raise NetworkAccessError(f"network access to {host!r} is not allowed in tests")
        real_connect(self, address)

    def guarded_getaddrinfo(host: object, *args: object, **kwargs: object) -> None:
        raise NetworkAccessError(f"DNS lookup for {host!r} is not allowed in tests")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    yield


@pytest.fixture(autouse=True)
def no_read_limit_left_over() -> Iterator[None]:
    """Take the counter per host a tiler app set for its process away after each test (M5-36 §5.2).

    `build_app` sets it for the whole process, as the tiler does once at start; a later test in the same worker would
    otherwise read its files under the caps of an app it never built.
    """
    yield
    limit_reads(None)


class _JsonLineCapture(logging.Handler):
    """Formats each record immediately, the way the real `StreamHandler` from
    `earthx.logging.configure_logging` does — unlike `caplog`, which stores the raw
    `LogRecord` and only formats it when a test inspects it later. `RequestIdMiddleware`
    unbinds the request ID right after it logs (M3-16), so a record formatted late would
    read `get_request_id()` back as `None` instead of the value that was actually bound
    while the request was being handled.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@pytest.fixture
def access_log_lines() -> Iterator[list[str]]:
    """Every line `earthx.request` (`RequestIdMiddleware`'s access log) writes during
    the test, rendered through the real `JsonFormatter` at emit time."""
    handler = _JsonLineCapture()
    logger = logging.getLogger("earthx.request")
    logger.addHandler(handler)
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        yield handler.lines
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
