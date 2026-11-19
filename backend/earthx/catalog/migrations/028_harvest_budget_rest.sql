-- A budget of pages per run and a rest after a source refused the harvest (M5-19 PR 2, Otto 18.11.2026).
--
-- opendata.swiss answered 429 from page 103 on and kept doing so for hours: a quota, not a pace. A source's file now
-- caps the pages of a run, so a pass spreads over days, and incremental listings become passes too (`pass_since`, the
-- lower bound of `metadata_modified` they ask from; NULL for a full pass), so that a budget never keeps one from
-- getting through. After a run ended `rate_limited`, `rest_until` holds the source: no run starts before it.
ALTER TABLE public.earthx_harvest_source
    ADD COLUMN pass_since timestamptz,
    ADD COLUMN rest_until timestamptz,
    ADD CONSTRAINT earthx_harvest_source_pass_since_check CHECK (pass_run_id IS NOT NULL OR pass_since IS NULL);

ALTER TABLE public.earthx_harvest_run DROP CONSTRAINT earthx_harvest_run_stop_reason_check;
ALTER TABLE public.earthx_harvest_run ADD CONSTRAINT earthx_harvest_run_stop_reason_check CHECK (stop_reason IN
    ('host_resting', 'robots', 'request_budget', 'upstream', 'shape', 'lease_expired', 'error', 'listing_moved',
     'rate_limited', 'page_budget'));
