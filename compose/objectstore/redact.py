"""A single, dependency-free place to strip credentials out of text before it
can reach stdout, stderr, or an exception message (M3-23).

Both `bootstrap.py` (imports boto3/rasterio only inside `smoke.py`, not here)
and `smoke.py` use this. Kept in its own module, with no third-party import,
so it can be tested directly wherever Python runs — `smoke.py` itself needs
`boto3`/`rasterio`, which are not backend dependencies and are not installed
outside the CI step that runs it.
"""

from __future__ import annotations


def redact(text: str, *secrets: str) -> str:
    """Replace every occurrence of each non-empty value in `secrets` with a
    placeholder. Safe to call with values that never occur in `text`."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "<redacted>")
    return text
