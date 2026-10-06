"""Formats: `cog.py`, `zarr_reader.py`, later virtual stores.

``Policy`` and ``Resolver`` are re-exported for `access` and `processing`, which
take them as arguments but may not import `gateway` (adr/0011 §6.4). The factory
of `access.py` builds them for a worker run (adr/0014 §8).
"""

from earthx.gateway import Policy, Resolver
from earthx.readers.access import ReadAccess, process_gdal_options, read_access_for
from earthx.readers.errors import AssetRejected

__all__ = ["AssetRejected", "Policy", "ReadAccess", "Resolver", "process_gdal_options", "read_access_for"]
