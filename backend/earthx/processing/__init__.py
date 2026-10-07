"""Recipes, operator registry, cost model, provenance — the worker core (KLAERUNGEN B9, adr/0014).

``run`` computes a recipe into a work directory; ``worker_environment`` sets the GDAL
options for the process that reads. Nothing here reaches a database, a queue, the
object store or an internal API; `jobs` and the local runner wrap it.
"""

from earthx.processing.core import RunResult, check_scope, run, worker_environment
from earthx.processing.errors import ProcessingError, RunCancelled
from earthx.processing.failures import failure_kind

__all__ = ["ProcessingError", "RunCancelled", "RunResult", "check_scope", "failure_kind", "run", "worker_environment"]
