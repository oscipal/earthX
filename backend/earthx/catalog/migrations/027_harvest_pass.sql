-- The open full pass of a CKAN source and the times the next runs ask from (M5-19 PR 2, Otto 18.11.2026).
--
-- A full listing of a large catalogue takes many runs when the source asks the harvest to slow down: a run that stops
-- keeps where it stood (`pass_start`, the offset of the next page; `pass_last_key`, the package that page must start
-- with), and the next run goes on from there instead of from the start. `pass_run_id` is the run that began the pass:
-- a find no run of the pass has seen is gone once the pass is through (A3, A8). `pass_total`, `pass_read` and
-- `pass_moved` carry the check that the listing held still across the runs.
--
-- `full_started_at` is when the last full pass that went through began; `changes_since` is the time up to which every
-- change is in: the start of the last done incremental run, or of the last full pass. An incremental run asks for
-- packages modified after it, less an hour. Both were read from the run rows before; they are carried over here.
ALTER TABLE public.earthx_harvest_source
    ADD COLUMN pass_run_id      bigint      REFERENCES public.earthx_harvest_run (run_id),
    ADD COLUMN pass_started_at  timestamptz,
    ADD COLUMN pass_start       integer     CHECK (pass_start >= 0),
    ADD COLUMN pass_last_key    text,
    ADD COLUMN pass_total       integer     CHECK (pass_total >= 0),
    ADD COLUMN pass_read        integer     CHECK (pass_read >= 0),
    ADD COLUMN pass_moved       boolean,
    ADD COLUMN full_started_at  timestamptz,
    ADD COLUMN changes_since    timestamptz,
    ADD CONSTRAINT earthx_harvest_source_pass_check CHECK (
        (pass_run_id IS NULL) = (pass_started_at IS NULL)
        AND (pass_run_id IS NULL) = (pass_start IS NULL)
        AND (pass_run_id IS NULL) = (pass_read IS NULL)
        AND (pass_run_id IS NULL) = (pass_moved IS NULL)
        AND (pass_run_id IS NOT NULL OR (pass_last_key IS NULL AND pass_total IS NULL))
    );

CREATE INDEX earthx_harvest_source_pass_idx ON public.earthx_harvest_source (pass_run_id);

INSERT INTO public.earthx_harvest_source (source_id, full_started_at, changes_since)
SELECT source_id,
       max(started_at) FILTER (WHERE kind = 'full'),
       max(started_at) FILTER (WHERE kind IN ('full', 'incremental'))
FROM public.earthx_harvest_run
WHERE status = 'done'
GROUP BY source_id
ON CONFLICT (source_id) DO UPDATE SET full_started_at = EXCLUDED.full_started_at,
                                      changes_since = EXCLUDED.changes_since;

-- A full pass that stopped before this migration kept no place. Where a source has finds but no done full run, the
-- pass of its last full run is taken over: the listing is sorted by id, so it stood at the package with the largest
-- key (in byte order, as the search index sorts), and the next page begins at the offset of that package. If the
-- listing moved meanwhile, the overlap shows it and the pass marks nothing gone (A8). Finds without a key were never
-- stored, so `pass_read` may fall short of the count; that, too, only keeps the pass from marking anything gone.
INSERT INTO public.earthx_harvest_source AS h
    (source_id, pass_run_id, pass_started_at, pass_start, pass_last_key, pass_total, pass_read, pass_moved)
SELECT r.source_id, r.run_id, r.started_at, f.found - 1, f.last_key, NULL, f.found, false
FROM (
    SELECT DISTINCT ON (source_id) source_id, run_id, started_at
    FROM public.earthx_harvest_run
    WHERE kind = 'full'
    ORDER BY source_id, run_id DESC
) r
JOIN (
    SELECT source_id, count(*)::integer AS found, max(source_key COLLATE "C") AS last_key
    FROM public.earthx_record_state
    GROUP BY source_id
) f USING (source_id)
WHERE NOT EXISTS (
    SELECT 1 FROM public.earthx_harvest_run d WHERE d.source_id = r.source_id AND d.kind = 'full' AND d.status = 'done'
)
ON CONFLICT (source_id) DO UPDATE SET pass_run_id = EXCLUDED.pass_run_id, pass_started_at = EXCLUDED.pass_started_at,
    pass_start = EXCLUDED.pass_start, pass_last_key = EXCLUDED.pass_last_key, pass_total = NULL,
    pass_read = EXCLUDED.pass_read, pass_moved = false
WHERE h.pass_run_id IS NULL;

ALTER TABLE public.earthx_harvest_run DROP CONSTRAINT earthx_harvest_run_stop_reason_check;
ALTER TABLE public.earthx_harvest_run ADD CONSTRAINT earthx_harvest_run_stop_reason_check CHECK (stop_reason IN
    ('host_resting', 'robots', 'request_budget', 'upstream', 'shape', 'lease_expired', 'error', 'listing_moved',
     'rate_limited'));
