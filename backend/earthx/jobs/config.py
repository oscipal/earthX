"""What one worker container is configured with (adr/0013 §5.7).

Slots, lease, heartbeat and polling interval are per container and come from the
environment: a container that differs from its neighbours changes nothing for the
others. The cap on concurrent runs and the limit per host are not here; they are a
row in the database that every supervisor reads (`earthx_job_limits`), so more
containers or a different environment never raise them quietly.

A bad value stops the start and names the variable, never the value.
"""

from __future__ import annotations

import math
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["WorkerConfig", "WorkerConfigError"]

DEFAULT_WORKDIR = Path(tempfile.gettempdir()) / "earthx-runs"


class WorkerConfigError(ValueError):
    """A ``WORKER_*`` variable is not a usable value; the text names the variable only."""


@dataclass(frozen=True)
class WorkerConfig:
    #: Runs one container holds at the same time (adr/0013 F4).
    slots: int = 2
    #: How long a run belongs to its worker without a heartbeat, and how often the supervisor renews it.
    lease_seconds: float = 60.0
    heartbeat_seconds: float = 15.0
    #: Picking up without a wake-up call, as often as this.
    poll_seconds: float = 5.0
    #: How often the sweeper looks for runs whose lease ran out.
    sweep_seconds: float = 15.0
    #: A child that was asked to cancel and still runs after this long is killed (adr/0013 §5.5).
    cancel_grace_seconds: float = 30.0
    #: A child that was terminated and still runs after this long is killed.
    terminate_grace_seconds: float = 5.0
    #: At most one progress write per run and this many seconds, except at the end (adr/0013 §5.4).
    progress_seconds: float = 1.0
    #: Cleaning up hourly; the first time a little after the start (adr/0013 §5.8).
    cleanup_seconds: float = 3600.0
    cleanup_first_seconds: float = 300.0
    #: The first retry waits this long, then twice as long, with ±20 % jitter (adr/0013 §5.6).
    backoff_seconds: float = 30.0
    #: `/health` answers 200 if the database was reached within this long.
    health_seconds: float = 30.0
    workdir: Path = field(default=DEFAULT_WORKDIR)

    def __post_init__(self) -> None:
        if self.slots < 1:
            raise WorkerConfigError("WORKER_SLOTS must be at least 1")
        for name, value in (
            ("WORKER_LEASE_SECONDS", self.lease_seconds),
            ("WORKER_HEARTBEAT_SECONDS", self.heartbeat_seconds),
            ("WORKER_POLL_SECONDS", self.poll_seconds),
        ):
            if not (math.isfinite(value) and value > 0):
                raise WorkerConfigError(f"{name} must be a finite number greater than 0")
        if self.heartbeat_seconds * 2 > self.lease_seconds:
            raise WorkerConfigError("WORKER_HEARTBEAT_SECONDS must be at most half of WORKER_LEASE_SECONDS")

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] | None = None) -> WorkerConfig:
        environ = os.environ if environ is None else environ
        values: dict[str, object] = {}
        for variable, name, kind in (
            ("WORKER_SLOTS", "slots", int),
            ("WORKER_LEASE_SECONDS", "lease_seconds", float),
            ("WORKER_HEARTBEAT_SECONDS", "heartbeat_seconds", float),
            ("WORKER_POLL_SECONDS", "poll_seconds", float),
        ):
            raw = environ.get(variable)
            if raw is None or raw == "":
                continue
            try:
                values[name] = kind(raw)
            except ValueError:
                raise WorkerConfigError(f"{variable} is not a number") from None
        if environ.get("WORKER_WORKDIR"):
            values["workdir"] = Path(environ["WORKER_WORKDIR"])
        return cls(**values)  # type: ignore[arg-type]
