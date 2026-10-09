"""Root package of the target architecture (architekturplan.md 3.1, E1).

Lives next to the prototype package `app` (strangler pattern, E2). Import
boundaries between the submodules below are enforced by `.importlinter`.
"""

#: The one version of the backend, SemVer 0.x (adr/0016 §9, F10). It goes into the
#: cache key and the provenance of every processing result (adr/0014 §4.5), and the
#: local runner builds its tag and ``runner_version`` from it. A change that can
#: change a result raises it.
__version__ = "0.4.0"
