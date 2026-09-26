-- The run log of the one-off materialize command (M3-11b plan §3.5, F5).
--
-- Not a second meaning inside 002 or 003: those are read-through caches (a row
-- can vanish at any time without changing what the platform answers); this
-- table is the *only* record of a materialize run's outcome, and the command
-- reads its own last successful `source_version` (an ETag) from here before
-- deciding whether the source changed at all (`adr/0009` §7.3).
--
-- public. on purpose, for the same reason as 002 and 003: pgstac puts
-- `pgstac, public` on the search_path of its own roles, so an unqualified
-- CREATE would land this table inside the pgstac schema, where a schema
-- rebuild would take it along.
--
-- One row per run, never updated after it is written: `started_at`/
-- `finished_at` bracket the run, and only a run that completed (loaded or
-- found unchanged) is ever inserted — a failed run rolls its whole
-- transaction back (`discovery.materialize`) and leaves no row, reporting
-- itself on stderr with a non-zero exit code instead.
CREATE TABLE public.earthx_materialize_runs (
    id             bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id     text        NOT NULL,
    started_at     timestamptz NOT NULL,
    finished_at    timestamptz NOT NULL,
    status         text        NOT NULL CHECK (status IN ('loaded', 'unchanged')),
    source_version text        NOT NULL,
    items_written  integer     NOT NULL,
    items_deleted  integer     NOT NULL,
    listed         integer     NOT NULL,
    missing        integer     NOT NULL,
    withheld       integer     NOT NULL
);

-- `last_source_version` (earthx/catalog/pgstac.py) reads the most recent row
-- for a dataset; this index is exactly that access path.
CREATE INDEX earthx_materialize_runs_dataset_started_idx
    ON public.earthx_materialize_runs (dataset_id, started_at DESC);
