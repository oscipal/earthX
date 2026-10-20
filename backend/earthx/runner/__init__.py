"""The local runner, offline with a recipe file: the third shell around the worker core (adr/0016).

``python -m earthx.runner run <recipe.json>`` computes the ``recipe.json`` of a platform
result on the user's own machine with the same core `jobs` runs (``processing.run``),
reading the sources directly through the readers and `gateway`, and writes the result
into a new folder, marked ``self_attested`` (Q12). It reaches no database, no queue, no
object store and no internal API (KLAERUNGEN B9); nothing it computes goes back to the
platform or into its cache (Q11).

It imports only `processing` and `catalog.datasets` (adr/0016 F2, `.importlinter`); this
file imports nothing, so that importing the package loads nothing else.
"""
