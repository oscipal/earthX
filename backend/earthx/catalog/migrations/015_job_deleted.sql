-- Deleting a finished job with a day to take it back (NM4-27; docs/plans/querschnitt/nm4-27-job-loeschen-mit-frist.md,
-- Otto 27.10.2026).
--
-- `deleted_until` is the end of the term in which a deleted job can be restored. While it runs the job answers like a
-- dismissed one (`404` on every route) and serves no cache hit; `restore` empties the column and the run's own
-- `expires_at`, which a deletion never touches, applies again. The hourly cleanup of `jobs` removes the job once the term
-- is over, and the result with it if no other job hangs on the run.
--
-- The term is `least(now + 1 day, run.expires_at)`, fixed at deletion: looking at a job never moves it. The column holds
-- a time and nothing else, so it adds no personal data to the row.
ALTER TABLE public.earthx_job ADD COLUMN deleted_until timestamptz;

CREATE INDEX earthx_job_deleted_until_idx ON public.earthx_job (deleted_until) WHERE deleted_until IS NOT NULL;
