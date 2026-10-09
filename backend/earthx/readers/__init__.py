"""Formats: `cog.py`, `zarr_reader.py`, later virtual stores.

``Policy`` and ``Resolver`` are re-exported for `access` and `processing`, which
take them as arguments but may not import `gateway` (adr/0011 §6.4). The factory
of `access.py` builds them for a worker run (adr/0014 §8); `failures.py` names how a read
of a source failed (adr/0013 §5.6).
"""

from earthx.gateway import Policy, Resolver
from earthx.readers.access import ReadAccess, hosts_for, process_gdal_options, read_access_for
from earthx.readers.errors import AssetRejected
from earthx.readers.failures import source_failure_kind

__all__ = [
    "AssetRejected",
    "Policy",
    "ReadAccess",
    "Resolver",
    "hosts_for",
    "process_gdal_options",
    "read_access_for",
    "source_failure_kind",
]
