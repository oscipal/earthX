"""T-A: the pure pieces of the mixed search (M3-13) — no Postgres, no network.

Everything that needs a running app (dispatch across real sources, fan-out,
partial failure) is in ``tests/integration/test_api_mixed_search.py`` instead.
"""

from __future__ import annotations

import pytest

from earthx.adapters.federated_search import InvalidQuery
from earthx.api.mixed_search import (
    compute_shares,
    decode_mixed_token,
    encode_mixed_token,
    mixed_fingerprint,
)


class TestComputeShares:
    def test_splits_evenly_when_it_divides(self) -> None:
        assert compute_shares(9, 3) == [3, 3, 3]

    def test_the_remainder_goes_to_the_first_sources(self) -> None:
        """100 over three sources: 34/33/33 (plan §3, §4.2 step 3)."""
        assert compute_shares(100, 3) == [34, 33, 33]

    def test_limit_below_source_count_leaves_the_later_ones_at_zero(self) -> None:
        assert compute_shares(2, 3) == [1, 1, 0]

    def test_zero_sources_is_an_empty_list(self) -> None:
        assert compute_shares(10, 0) == []

    def test_one_source_gets_everything(self) -> None:
        assert compute_shares(10, 1) == [10]

    def test_shares_always_sum_to_the_limit(self) -> None:
        for limit in (0, 1, 7, 10, 100):
            for n in (1, 2, 3, 5):
                assert sum(compute_shares(limit, n)) == limit


class TestMixedFingerprint:
    def test_collection_order_does_not_change_it(self) -> None:
        a = mixed_fingerprint(["a", "b"], None, None, None, None)
        b = mixed_fingerprint(["b", "a"], None, None, None, None)
        assert a == b

    def test_limit_plays_no_part(self) -> None:
        """Unlike the single-adapter fingerprint before M3-13, this one never took
        `limit` in the first place — a mixed search's own fan-out changes the
        share handed to each source on every page."""
        first = mixed_fingerprint(["a"], None, None, None, "2024-06-01T00:00:00Z/..")
        again = mixed_fingerprint(["a"], None, None, None, "2024-06-01T00:00:00Z/..")
        assert first == again

    def test_a_different_collection_set_changes_it(self) -> None:
        a = mixed_fingerprint(["a"], None, None, None, None)
        b = mixed_fingerprint(["a", "b"], None, None, None, None)
        assert a != b

    def test_bbox_changes_it(self) -> None:
        a = mixed_fingerprint(["a"], None, None, None, None)
        b = mixed_fingerprint(["a"], (8.0, 47.0, 12.0, 51.0), None, None, None)
        assert a != b

    def test_datetime_changes_it(self) -> None:
        a = mixed_fingerprint(["a"], None, None, None, None)
        b = mixed_fingerprint(["a"], None, None, None, "2024-06-01T00:00:00Z/..")
        assert a != b

    def test_intersects_and_bbox_are_different_searches(self) -> None:
        as_bbox = mixed_fingerprint(["a"], (8.0, 47.0, 12.0, 51.0), None, None, None)
        as_polygon = mixed_fingerprint(
            ["a"],
            None,
            {"type": "Polygon", "coordinates": [[[8.0, 47.0], [12.0, 47.0], [12.0, 51.0], [8.0, 47.0]]]},
            None,
            None,
        )
        assert as_bbox != as_polygon

    def test_ids_order_and_duplicates_do_not_change_it(self) -> None:
        a = mixed_fingerprint(["a"], None, None, ["x", "y"], None)
        b = mixed_fingerprint(["a"], None, None, ["y", "x", "x"], None)
        assert a == b


class TestMixedToken:
    def test_round_trips(self) -> None:
        fingerprint = mixed_fingerprint(["a", "b"], None, None, None, None)
        token = encode_mixed_token(fingerprint, {"a": "m1", "b": None}, {})
        source_markers, failed = decode_mixed_token(token, fingerprint, {"a", "b"}, {"a", "b"})
        assert source_markers == {"a": "m1", "b": None}
        assert failed == {}

    def test_carries_failed_sources_too(self) -> None:
        fingerprint = mixed_fingerprint(["a", "b"], None, None, None, None)
        token = encode_mixed_token(fingerprint, {"a": "m1"}, {"b": "timeout"})
        source_markers, failed = decode_mixed_token(token, fingerprint, {"a", "b"}, {"a", "b"})
        assert source_markers == {"a": "m1"}
        assert failed == {"b": "timeout"}

    def test_unreadable_base64_is_refused(self) -> None:
        with pytest.raises(InvalidQuery, match="not readable"):
            decode_mixed_token("not base64 at all!!", "fp", set(), set())

    def test_an_adapter_token_is_not_a_mixed_one(self) -> None:
        """The single-collection adapter's own token shape (`{v, d, h, m}`, no
        `k`) must not be misread as a mixed one, and vice versa
        (`federated_search.decode_page_token`'s own symmetric check)."""
        import base64
        import json

        adapter_shaped = base64.urlsafe_b64encode(
            json.dumps({"v": 2, "d": "ds", "h": "fp", "m": "marker"}).encode()
        ).decode("ascii").rstrip("=")
        with pytest.raises(InvalidQuery, match="not a mixed-search token"):
            decode_mixed_token(adapter_shaped, "fp", {"ds"}, {"ds"})

    def test_a_foreign_fingerprint_is_refused(self) -> None:
        fingerprint = mixed_fingerprint(["a"], None, None, None, None)
        token = encode_mixed_token(fingerprint, {"a": None}, {})
        with pytest.raises(InvalidQuery, match="belongs to a different search"):
            decode_mixed_token(token, "a-different-fingerprint", {"a"}, {"a"})

    def test_an_unknown_source_key_is_refused(self) -> None:
        """A tampered or stale token naming a source outside the current search
        (plan §5: "eine Quelle in `s`, die zu dieser Suche nicht gehört")."""
        fingerprint = mixed_fingerprint(["a"], None, None, None, None)
        token = encode_mixed_token(fingerprint, {"a": None, "gone": "m"}, {})
        with pytest.raises(InvalidQuery, match="does not belong to this search"):
            decode_mixed_token(token, fingerprint, {"a"}, {"a"})

    def test_an_unknown_failed_collection_is_refused(self) -> None:
        fingerprint = mixed_fingerprint(["a"], None, None, None, None)
        token = encode_mixed_token(fingerprint, {}, {"not-in-this-search": "timeout"})
        with pytest.raises(InvalidQuery, match="does not belong to this search"):
            decode_mixed_token(token, fingerprint, {"a"}, {"a"})

    def test_a_token_naming_nothing_to_continue_is_refused(self) -> None:
        fingerprint = mixed_fingerprint(["a"], None, None, None, None)
        token = encode_mixed_token(fingerprint, {}, {})
        with pytest.raises(InvalidQuery, match="no source to continue"):
            decode_mixed_token(token, fingerprint, {"a"}, {"a"})

    def test_a_malformed_source_map_is_refused(self) -> None:
        import base64
        import json

        payload = {"v": 1, "k": "mixed", "h": "fp", "s": {"a": 3}, "f": {}}
        token = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode("ascii").rstrip("=")
        with pytest.raises(InvalidQuery, match="malformed"):
            decode_mixed_token(token, "fp", {"a"}, set())
