"""The registry entries by the names the tests know them by (M5-13 plan §3.3, A3).

Up to M4 these were constants of `earthx.catalog.datasets`; since M5-13 the entries are YAML files and the package
keeps no names for them. The tests keep theirs, taken from the registry of the process.
"""

from __future__ import annotations

from earthx.catalog.datasets import registry

REGISTRY = registry()
RETIRED = REGISTRY.retired

SENTINEL_2_L2A = REGISTRY.get("sentinel-2-c1-l2a")
COP_DEM_GLO_30 = REGISTRY.get("cop-dem-glo-30")
ESA_WORLDCOVER_2020 = REGISTRY.get("esa-worldcover-2020")
ESA_WORLDCOVER_2021 = REGISTRY.get("esa-worldcover-2021")

# The acquisition period of the DEM, the same for every tile (M3-11b F1).
DEM_ACQUISITION_START = COP_DEM_GLO_30.temporal_extent.start
DEM_ACQUISITION_END = COP_DEM_GLO_30.temporal_extent.end
