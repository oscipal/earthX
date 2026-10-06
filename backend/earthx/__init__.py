"""Root package of the target architecture (architekturplan.md 3.1, E1).

Lives next to the prototype package `app` (strangler pattern, E2). Import
boundaries between the submodules below are enforced by `.importlinter`.
"""

#: The one version of the backend (PEP 440). It goes into the cache key and the
#: provenance of every processing result, and the local runner reports the same
#: value (adr/0014 §4.5, adr/0016; Otto 06.10.2026, M4-07a). A change to the
#: processing core that changes results raises it.
__version__ = "0.4.0.dev0"
