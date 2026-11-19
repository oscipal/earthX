"""The state of `logging` as a run found it, put back after each test (M5-61 §3.1 point 3, F5).

Loggers are process-wide. A test that turns a level, a handler or ``propagate`` and leaves it
changes what every later test of the same worker sees: #336 lost a GDAL warning that way, and
importing ``earthx.jobs.main`` while collecting gives the root logger a stdout handler and INFO
for the rest of the worker (M5-61 §2.7). The guard keeps the state from before collection for the
root logger and every logger that existed then, and the state at the first test that sees it for
every logger made later (a module imported on the way). Before each test it puts that state back,
which undoes what an import changed while collecting, and again after it, noting which test had
changed what; the run names them at its end. A test marked ``changes_logging`` sets up logging on
purpose (it checks ``configure_logging``); it is put back too, without a note.

pytest's own capture handlers come and go around each phase and are left alone.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass


@dataclass(frozen=True)
class LoggerState:
    level: int
    propagate: bool
    disabled: bool
    handlers: tuple[logging.Handler, ...]


def _own(handlers: list[logging.Handler]) -> tuple[logging.Handler, ...]:
    """The handlers that are not pytest's capture handlers."""
    return tuple(h for h in handlers if not type(h).__module__.startswith("_pytest"))


def _state(logger: logging.Logger) -> LoggerState:
    return LoggerState(logger.level, logger.propagate, logger.disabled, _own(logger.handlers))


def _loggers() -> dict[str, logging.Logger]:
    return {name: obj for name, obj in logging.root.manager.loggerDict.items() if isinstance(obj, logging.Logger)}


class LoggingGuard:
    def __init__(self) -> None:
        self.disable = logging.root.manager.disable
        self.root = _state(logging.getLogger())
        self.known = {name: _state(logger) for name, logger in _loggers().items()}
        self.changed: list[tuple[str, list[str]]] = []

    def learn(self) -> None:
        """Take the loggers made since the last test as they are now."""
        for name, logger in _loggers().items():
            self.known.setdefault(name, _state(logger))

    def restore(self, test: str, *, note: bool = True) -> list[str]:
        """Put everything back; what had changed, by logger name, is noted for ``test``."""
        changes = []
        if logging.root.manager.disable != self.disable:
            logging.disable(self.disable)
            changes.append("logging.disable")
        if _put_back(logging.getLogger(), self.root):
            changes.append("root")
        loggers = _loggers()
        for name, state in self.known.items():
            logger = loggers.get(name)
            if logger is not None and _put_back(logger, state):
                changes.append(name)
        if changes and note:
            self.changed.append((test, changes))
        return changes


def _put_back(logger: logging.Logger, state: LoggerState) -> bool:
    if _state(logger) == state:
        return False
    capture = [h for h in logger.handlers if type(h).__module__.startswith("_pytest")]
    logger.setLevel(state.level)
    logger.propagate = state.propagate
    logger.disabled = state.disabled
    logger.handlers = [*state.handlers, *capture]
    return True


#: What :meth:`LoggingGuard.restore` notes when an import changed `logging` before any test ran.
COLLECTING = "while collecting (an import at module level)"


def summary(changed: list[tuple[str, list[str]]]) -> list[str]:
    """One line per test that left `logging` changed, each line once (every xdist worker collects)."""
    return sorted({f"{test}: {', '.join(sorted(names))}" for test, names in changed})
