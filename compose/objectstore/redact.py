"""A single, dependency-free place to strip credentials out of text before it
can reach stdout, stderr, or an exception message (M3-23).

Both `bootstrap.py` and `smoke.py` use this. Kept in its own module, with no
third-party import, so `bootstrap.py` stays standard-library only and this can
be tested directly wherever Python runs. `earthx/objectstore/errors.py` carries
a copy, because `compose/` is outside the package (adr/0015 §9.2).
"""

from __future__ import annotations


def redact(text: str, *secrets: str) -> str:
    """Replace every occurrence of each non-empty value in `secrets` with a
    placeholder. Safe to call with values that never occur in `text`."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "<redacted>")
    return text
