"""The shapes of a unit of the source (M5-58, adr/0038 §3.3)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from earthx.catalog.source_units import Validators


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Wed, 12 Feb 2025 08:00:00 GMT", datetime(2025, 2, 12, 8, tzinfo=UTC)),
        # STAC `updated` of a listing (review of PR 1): the rule "the younger of two" must still see it.
        ("2025-02-12T08:00:00Z", datetime(2025, 2, 12, 8, tzinfo=UTC)),
        ("2025-02-12T08:00:00", datetime(2025, 2, 12, 8, tzinfo=UTC)),
        ("not a date", None),
        (None, None),
    ],
)
def test_the_time_of_a_last_modified(text: str | None, expected: datetime | None) -> None:
    assert Validators(etag=None, last_modified=text, checksum=None, content_sha256=None).modified_at == expected
