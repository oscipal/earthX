"""What an adapter needs from the application cache — and nothing else.

The cache of E4 lives in Postgres, and the implementation therefore lives in
``catalog`` (``earthx/catalog/search_cache.py``), next to the rest of the code that
talks to that database. An adapter only ever reads and writes by key, so that is all
this protocol says. Nothing here imports a database driver: ``adapters`` speaks to
sources, not to platform services.

The direction matters for the module boundaries of architekturplan.md 3.1: ``catalog``
must not import ``adapters``, so the shared shape is declared here and the concrete
cache is handed in by whoever assembles the two — the tests in M1-06, the
``FederatingCoreCrudClient`` in ``api`` from M1-07 on.
"""

from __future__ import annotations

from typing import Any, Protocol

# One cached entry: a JSON object, because that is what both ends already speak —
# the source answers JSON and the cache column is jsonb.
CacheValue = dict[str, Any]


class SearchCache(Protocol):
    """A key-value store with an expiry. Missing is normal; failing is survivable."""

    async def get(self, key: str) -> CacheValue | None:
        """The stored value, or None if it is absent or expired."""
        ...

    async def set(self, key: str, value: CacheValue, *, ttl_s: float, dataset_id: str) -> None:
        """Store a value for ``ttl_s`` seconds.

        ``dataset_id`` is carried so a stored row can be attributed to a dataset
        without decoding the key, which is an opaque hash.
        """
        ...
