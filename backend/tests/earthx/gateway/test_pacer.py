"""The spacing per host for reads that GDAL performs itself (M5-30b part 8, adr/0032 §8.2, F3 = 1, F4)."""

from __future__ import annotations

import threading

import pytest

from earthx.gateway import OVERVIEW_HOST_INTERVAL_ENV, HostPacer, Policy, overview_interval_from_env

HOST = "data.example.org"
OTHER = "mirror.example.net"


class FakeTime:
    """A clock that moves only when the pacer sleeps (or the test says so); records every sleep."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []
        self.lock = threading.Lock()

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        with self.lock:
            self.slept.append(seconds)
            self.now += seconds

    def pacer(self, interval_s: float = 0.25, **kwargs: object) -> HostPacer:
        return HostPacer(interval_s, clock=self.clock, sleep=self.sleep, **kwargs)  # type: ignore[arg-type]


def read(pacer: HostPacer, time: FakeTime, host: str, requests: int, took_s: float = 0.0) -> float:
    """One file: wait, read for ``took_s``, account; the time of its start."""
    pacer.wait(host)
    started = time.now
    time.now += took_s
    pacer.account(host, requests)
    return started - 1000.0


def test_the_first_file_of_a_host_starts_at_once() -> None:
    time = FakeTime()
    assert read(time.pacer(), time, HOST, 2) == 0.0
    assert time.slept == []


def test_the_next_start_is_delayed_by_the_requests_times_the_interval() -> None:
    time = FakeTime()
    pacer = time.pacer(0.25)
    starts = [read(pacer, time, HOST, requests) for requests in (2, 1, 3, 1)]
    assert starts == pytest.approx([0.0, 0.5, 0.75, 1.5])


def test_the_time_a_file_took_counts_towards_the_spacing() -> None:
    time = FakeTime()
    pacer = time.pacer(0.25)
    assert read(pacer, time, HOST, 2, took_s=0.3) == 0.0
    assert read(pacer, time, HOST, 1) == pytest.approx(0.5)  # 0.3 s read, 0.2 s waited
    assert read(pacer, time, HOST, 1, took_s=2.0) == pytest.approx(0.75)
    assert read(pacer, time, HOST, 1) == pytest.approx(2.75)  # slower than the interval: no wait


def test_a_file_without_a_request_gives_its_slot_back() -> None:
    time = FakeTime()
    pacer = time.pacer(1.0)
    assert [read(pacer, time, HOST, 0) for _ in range(3)] == [0.0, 0.0, 0.0]
    assert time.slept == []


def test_hosts_do_not_wait_for_each_other() -> None:
    time = FakeTime()
    pacer = time.pacer(1.0)
    read(pacer, time, HOST, 5)
    assert read(pacer, time, OTHER, 1) == 0.0
    assert read(pacer, time, HOST, 1) == pytest.approx(5.0)


def test_the_host_is_compared_in_the_gateways_spelling() -> None:
    time = FakeTime()
    pacer = time.pacer(1.0)
    read(pacer, time, "Data.Example.org.", 3)
    assert read(pacer, time, HOST, 1) == pytest.approx(3.0)


def test_the_policy_names_a_host_and_its_subdomains() -> None:
    time = FakeTime()
    policy = Policy(allowed_hosts=frozenset({HOST}), host_intervals={HOST: 2.0})
    pacer = time.pacer(0.25, policy=policy)
    assert pacer.interval_for(HOST) == 2.0
    assert pacer.interval_for("cdn." + HOST) == 2.0
    assert pacer.interval_for(OTHER) == 0.25
    assert [read(pacer, time, "cdn." + HOST, 1) for _ in range(2)] == pytest.approx([0.0, 2.0])


def test_the_policys_general_interval_does_not_replace_the_pacers() -> None:
    policy = Policy(allowed_hosts=frozenset({HOST}), min_interval_s=9.0)
    assert HostPacer(0.25, policy=policy).interval_for(HOST) == 0.25


def test_an_interval_of_zero_never_waits() -> None:
    time = FakeTime()
    pacer = time.pacer(0.0)
    assert [read(pacer, time, HOST, 7) for _ in range(3)] == [0.0, 0.0, 0.0]


def test_readers_in_several_threads_are_spaced_too() -> None:
    time = FakeTime()
    pacer = time.pacer(1.0)
    starts: list[float] = []
    barrier = threading.Barrier(4)

    def one() -> None:
        barrier.wait()
        pacer.wait(HOST)
        starts.append(time.now - 1000.0)
        pacer.account(HOST, 1)

    threads = [threading.Thread(target=one) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(starts) == pytest.approx([0.0, 1.0, 2.0, 3.0])


def test_account_without_wait_is_refused() -> None:
    pacer = FakeTime().pacer()
    with pytest.raises(RuntimeError):
        pacer.account(HOST, 1)
    pacer.wait(HOST)
    pacer.account(HOST, 1)
    with pytest.raises(RuntimeError):
        pacer.account(HOST, 1)


@pytest.mark.parametrize("requests", [-1, 1.5, True, "2", None])
def test_a_request_count_that_is_no_whole_number_is_refused(requests: object) -> None:
    pacer = FakeTime().pacer()
    pacer.wait(HOST)
    with pytest.raises(ValueError):
        pacer.account(HOST, requests)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [-0.1, 300.1, float("nan"), float("inf"), "0.25"])
def test_a_bad_interval_builds_no_pacer(value: object) -> None:
    with pytest.raises(ValueError):
        HostPacer(value)  # type: ignore[arg-type]


# --- EARTHX_OVERVIEW_HOST_INTERVAL_S


@pytest.mark.parametrize(
    ("raw", "expected"), [(None, 0.25), ("", 0.25), ("  ", 0.25), ("1.5", 1.5), ("0", 0.0), ("300", 300.0)]
)
def test_the_interval_comes_from_the_environment(raw: str | None, expected: float) -> None:
    environ = {} if raw is None else {OVERVIEW_HOST_INTERVAL_ENV: raw}
    assert overview_interval_from_env(environ) == expected
    assert HostPacer.from_env(environ=environ).interval_for(HOST) == expected


@pytest.mark.parametrize("raw", ["-1", "300.5", "nan", "inf", "fast", "0,25"])
def test_a_bad_environment_value_is_refused_and_not_repeated(raw: str) -> None:
    with pytest.raises(ValueError) as caught:
        overview_interval_from_env({OVERVIEW_HOST_INTERVAL_ENV: raw})
    assert OVERVIEW_HOST_INTERVAL_ENV in str(caught.value)
    assert raw not in str(caught.value)


def test_the_default_is_a_quarter_of_a_second() -> None:
    assert overview_interval_from_env({}) == 0.25
