-- The bundle of UI-01e (docs/plans/vp3/ui-01-app-rahmen.md §6.12, Otto 24.10.2026): the list of jobs
-- behind "Download all (ZIP)", put there by `POST /processing/bundles` under an identifier of its own so
-- that `GET /processing/bundles/{id}` can be resumed with `Range` and `If-Range`.
--
-- It holds the `jobID`s and the times and nothing else: no area, no title, no byte. A `jobID` is the way to
-- a result (Q9), so the row is personal data: it is never logged, the identifier is random
-- (`secrets.token_urlsafe(16)`), never derived from the jobs, and nothing refers to it. The ZIP is built when it
-- is read, from the state of the jobs.
--
-- The term is the earliest `expires_at` of the jobs that went in, fixed at creation: looking at a bundle never
-- moves it. The hourly cleanup of `jobs` deletes what has expired, the row whole.
CREATE TABLE public.earthx_bundle (
    bundle_id  text        PRIMARY KEY,
    job_ids    jsonb       NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);

CREATE INDEX earthx_bundle_expires_at_idx ON public.earthx_bundle (expires_at);
