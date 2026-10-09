"""What one worker container is configured with (adr/0013 §5.7; plan M4-08a §3.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from earthx.jobs.config import DEFAULT_WORKDIR, WorkerConfig, WorkerConfigError


def test_the_defaults_are_the_start_values_of_adr_0013() -> None:
    config = WorkerConfig.from_environ({})
    assert (config.slots, config.lease_seconds, config.heartbeat_seconds, config.poll_seconds) == (2, 60.0, 15.0, 5.0)
    assert (config.cancel_grace_seconds, config.cleanup_seconds, config.backoff_seconds) == (30.0, 3600.0, 30.0)
    assert config.workdir == DEFAULT_WORKDIR


def test_the_environment_sets_each_value() -> None:
    config = WorkerConfig.from_environ(
        {
            "WORKER_SLOTS": "3",
            "WORKER_LEASE_SECONDS": "90",
            "WORKER_HEARTBEAT_SECONDS": "20",
            "WORKER_POLL_SECONDS": "2.5",
            "WORKER_WORKDIR": "/scratch/runs",
        }
    )
    assert (config.slots, config.lease_seconds, config.heartbeat_seconds, config.poll_seconds) == (3, 90.0, 20.0, 2.5)
    assert config.workdir == Path("/scratch/runs")


def test_an_empty_value_means_not_set() -> None:
    assert WorkerConfig.from_environ({"WORKER_SLOTS": "", "WORKER_WORKDIR": ""}) == WorkerConfig()


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({"WORKER_SLOTS": "0"}, "WORKER_SLOTS must be at least 1"),
        ({"WORKER_SLOTS": "-2"}, "WORKER_SLOTS must be at least 1"),
        ({"WORKER_SLOTS": "2.5"}, "WORKER_SLOTS is not a number"),
        ({"WORKER_SLOTS": "two"}, "WORKER_SLOTS is not a number"),
        ({"WORKER_LEASE_SECONDS": "0"}, "WORKER_LEASE_SECONDS must be a finite number greater than 0"),
        ({"WORKER_HEARTBEAT_SECONDS": "-1"}, "WORKER_HEARTBEAT_SECONDS must be a finite number greater than 0"),
        ({"WORKER_POLL_SECONDS": "0"}, "WORKER_POLL_SECONDS must be a finite number greater than 0"),
        ({"WORKER_POLL_SECONDS": "soon"}, "WORKER_POLL_SECONDS is not a number"),
        (
            {"WORKER_LEASE_SECONDS": "20", "WORKER_HEARTBEAT_SECONDS": "15"},
            "WORKER_HEARTBEAT_SECONDS must be at most half of WORKER_LEASE_SECONDS",
        ),
    ],
)
def test_a_bad_value_is_refused_and_the_text_names_the_variable_not_the_value(
    environment: dict[str, str], message: str
) -> None:
    with pytest.raises(WorkerConfigError) as caught:
        WorkerConfig.from_environ(environment)
    assert str(caught.value) == message
    for value in environment.values():
        if not value.isdigit():
            assert value not in str(caught.value)


def test_nan_and_infinity_are_no_usable_interval() -> None:
    for value in ("nan", "inf", "-inf"):
        with pytest.raises(WorkerConfigError):
            WorkerConfig.from_environ({"WORKER_POLL_SECONDS": value})
