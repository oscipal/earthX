"""The error vocabulary every adapter and the dispatch share (adr/0011 B9, F1).

Before M4-01b these lived in ``federated_search.py``, so ``cop_dem_bucket`` — which
federates nothing — imported them from there. They are about a source and its
dispatch, not about federated search, so they live here, next to the adapters and
the dispatch that raise them. ``nominatim`` keeps its own classes of the same names:
place search is not a dataset source and is not dispatched here (M4-01b F3).
"""

from __future__ import annotations


class InvalidQuery(ValueError):
    """The request breaks one of our own rules, before anything is sent upstream."""


class UnknownCollection(LookupError):
    """No such collection in our catalogue (adr/0005 rule I) — the caller's 404."""


class UnsupportedSource(LookupError):
    """The collection exists, but another adapter serves it. A dispatch mistake."""


class NotMaterialized(UnsupportedSource):
    """This dataset's items are not materialized here (M3-11a K-05)."""


class UnsupportedFilter(LookupError):
    """The collection's own source cannot honour `intersects` or `ids` (M3-08 F4a).

    A dispatch fact, not a caller mistake — the parameter itself is valid, this
    particular source just cannot filter by it (yet). Kept apart from
    :class:`InvalidQuery` so the two map to different, honest `400` texts.
    """


class UpstreamShapeError(RuntimeError):
    """The source answered something that is not what its protocol promises."""


class AdapterSpecMismatch(RuntimeError):
    """The registry names a capability the adapter table has no answer for (M4-01b).

    Raised when an app is built, not per request: the mistake is in how the
    platform is put together, and it is the same for every request.
    """
