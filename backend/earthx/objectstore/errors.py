"""Errors of the object store module (adr/0015 §9.2).

No message carries a configuration value, a key or the text of a response:
Garage names the access key id in `AccessDenied` (§3.2), and a `botocore`
exception names the endpoint. `client.py` translates every `botocore`
exception into one of these classes and keeps only the operation, the S3 error
code and the HTTP status, run through :func:`redact` once more.
"""

from __future__ import annotations


class ObjectStoreError(RuntimeError):
    """Base class for everything this module raises."""


class StoreConfigError(ObjectStoreError):
    """The S3_* environment is missing or invalid. Names the variable, never its value."""


class StoreUnavailable(ObjectStoreError):
    """The store could not be reached or answered with an error."""


class StoreDenied(ObjectStoreError):
    """The store refused the key for this operation."""


class ResultNotFound(ObjectStoreError):
    """There is no object under that key."""


class ResultExpiring(ObjectStoreError):
    """The result expires too soon to hand out a signed URL for it."""


class LifecycleMissing(ObjectStoreError):
    """The bucket carries no rule that expires `results/` as adr/0015 §7.3 requires."""


def redact(text: str, *secrets: str) -> str:
    """Replace every non-empty value of `secrets` in `text` with a placeholder.

    A copy of `compose/objectstore/redact.py` (M3-23): `compose/` lies outside the
    package and cannot be imported from `earthx` (adr/0015 §9.2).
    """
    for secret in secrets:
        if secret:
            text = text.replace(secret, "<redacted>")
    return text
