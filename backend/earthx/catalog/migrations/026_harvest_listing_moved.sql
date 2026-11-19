-- A stop reason for a run whose listing moved while it was read (M5-19 PR 2, plan A8).
--
-- An incremental CKAN run reads its listing page by page with an offset; when packages come or go meanwhile, one can
-- be skipped. Such a run must not count as the last done run, from which the next incremental one asks: it ends
-- `interrupted` with `listing_moved`, and the next run asks from the run before.
ALTER TABLE public.earthx_harvest_run DROP CONSTRAINT earthx_harvest_run_stop_reason_check;
ALTER TABLE public.earthx_harvest_run ADD CONSTRAINT earthx_harvest_run_stop_reason_check CHECK (stop_reason IN
    ('host_resting', 'robots', 'request_budget', 'upstream', 'shape', 'lease_expired', 'error', 'listing_moved'));
