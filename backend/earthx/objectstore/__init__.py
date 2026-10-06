"""The platform's own object store (adr/0015).

One store, known only from the process environment (`config.py`), reached
through `botocore` in `client.py` and nowhere else. The public functions in
`results.py` take a :class:`~earthx.objectstore.results.Store` and identifiers
— never an endpoint, host, bucket or URL (adr/0015 §4.1, Auflage F2). Only
`jobs` and `api` may import this package (architekturplan.md 3.1).

Nothing is re-exported here, so importing a submodule such as `errors` does not
load `botocore`.
"""
