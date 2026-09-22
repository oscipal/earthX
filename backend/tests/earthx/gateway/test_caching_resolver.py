"""What the resolver cache remembers, for how long, and what it never remembers.

The point of M2-14 is that a batch of tiles resolves the asset host once instead
of once per tile. The point of these tests is that nothing else moved with it:
the verdict on an address is still passed on every single request, and an entry
that has run out is a resolution, not a hand-out.
"""

from __future__ import annotations

import pytest

from earthx.gateway import CachingResolver, Policy, check_url
from earthx.gateway.errors import AddressRejected, UrlRejected

HOST = "earth-search.aws.element84.com"
POLICY = Policy(allowed_hosts=frozenset({HOST}))


class Clock:
    """A hand-wound ``time.monotonic``."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Answers:
    """A resolver that counts, and that can be told to answer differently."""

    def __init__(self, *answers: tuple[str, ...]) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, int]] = []

    def __call__(self, host: str, port: int) -> tuple[str, ...]:
        self.calls.append((host, port))
        return self.answers[min(len(self.calls), len(self.answers)) - 1]


def test_a_second_ask_within_the_frist_does_not_resolve_again() -> None:
    answers = Answers(("93.184.216.34",))
    resolve = CachingResolver(resolve=answers, now=Clock())
    assert [resolve(HOST) for _ in range(40)] == [("93.184.216.34",)] * 40
    assert len(answers.calls) == 1


def test_an_expired_entry_is_resolved_again() -> None:
    answers = Answers(("93.184.216.34",), ("8.8.8.8",))
    clock = Clock()
    resolve = CachingResolver(ttl_s=5.0, resolve=answers, now=clock)
    assert resolve(HOST) == ("93.184.216.34",)
    clock.now += 4.9
    assert resolve(HOST) == ("93.184.216.34",)
    clock.now += 0.2
    assert resolve(HOST) == ("8.8.8.8",)
    assert len(answers.calls) == 2


def test_a_fresh_answer_replaces_the_old_one_and_is_not_merged_with_it() -> None:
    # A round-robin host answers with other addresses every time. Keeping the old
    # ones alongside the new would keep an address the name no longer names.
    answers = Answers(("93.184.216.34", "8.8.8.8"), ("1.1.1.1",))
    clock = Clock()
    resolve = CachingResolver(ttl_s=5.0, resolve=answers, now=clock)
    resolve(HOST)
    clock.now += 6.0
    assert resolve(HOST) == ("1.1.1.1",)


def test_the_port_belongs_to_the_key() -> None:
    answers = Answers(("93.184.216.34",))
    resolve = CachingResolver(resolve=answers, now=Clock())
    resolve(HOST, 443)
    resolve(HOST, 8443)
    assert answers.calls == [(HOST, 443), (HOST, 8443)]


def test_a_failed_resolution_is_not_remembered() -> None:
    calls: list[str] = []

    def failing(host: str, port: int) -> tuple[str, ...]:
        calls.append(host)
        raise AddressRejected("host does not resolve", host=host)

    resolve = CachingResolver(resolve=failing, now=Clock())
    for _ in range(3):
        with pytest.raises(AddressRejected):
            resolve(HOST)
    assert len(calls) == 3


def test_a_failure_does_not_hand_out_an_expired_answer() -> None:
    state = {"fail": False}
    calls: list[str] = []

    def sometimes(host: str, port: int) -> tuple[str, ...]:
        calls.append(host)
        if state["fail"]:
            raise AddressRejected("host does not resolve", host=host)
        return ("93.184.216.34",)

    clock = Clock()
    resolve = CachingResolver(ttl_s=5.0, resolve=sometimes, now=clock)
    assert resolve(HOST) == ("93.184.216.34",)
    clock.now += 6.0
    state["fail"] = True
    with pytest.raises(AddressRejected):
        resolve(HOST)
    # And the entry is gone rather than resurrected by the failure.
    with pytest.raises(AddressRejected):
        resolve(HOST)
    assert len(calls) == 3


def test_the_cache_does_not_grow_past_its_cap() -> None:
    answers = Answers(("93.184.216.34",))
    resolve = CachingResolver(max_entries=2, resolve=answers, now=Clock())
    for host in ("a.example.com", "b.example.com", "c.example.com"):
        resolve(host)
    # `a` was the oldest and is gone, so asking for it resolves a fourth time,
    # while `c` is still remembered.
    resolve("c.example.com")
    resolve("a.example.com")
    assert [host for host, _ in answers.calls] == [
        "a.example.com",
        "b.example.com",
        "c.example.com",
        "a.example.com",
    ]


@pytest.mark.parametrize("kwargs", [{"ttl_s": 0}, {"ttl_s": -1.0}, {"max_entries": 0}])
def test_a_cache_that_could_never_hold_anything_is_refused(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        CachingResolver(**kwargs)


def test_a_cached_address_is_still_judged_on_every_request() -> None:
    """The cache holds what the resolver answered, never the verdict on it.

    A name that answers publicly once and with a loopback address afterwards is
    the trick `resolver.py` exists to stop; a cache that skipped the check on a
    hit would let the second answer through for as long as the entry lives.
    """
    answers = Answers(("93.184.216.34",), ("93.184.216.34", "127.0.0.1"))
    clock = Clock()
    resolve = CachingResolver(ttl_s=5.0, resolve=answers, now=clock)
    assert check_url(f"https://{HOST}/v1", POLICY, resolve=resolve).address == "93.184.216.34"
    clock.now += 6.0
    with pytest.raises(AddressRejected) as raised:
        check_url(f"https://{HOST}/v1", POLICY, resolve=resolve)
    assert raised.value.address == "127.0.0.1"


def test_a_host_off_the_allowlist_is_refused_before_it_is_ever_resolved() -> None:
    """The cache sits behind the allowlist, not in front of it."""
    answers = Answers(("93.184.216.34",))
    resolve = CachingResolver(resolve=answers, now=Clock())
    with pytest.raises(UrlRejected):
        check_url("https://evil.tld/v1", POLICY, resolve=resolve)
    assert answers.calls == []
