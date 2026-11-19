-- CKAN read by key instead of by offset (M5-19 PR 2, Otto 19.11.2026; plan §12.7).
--
-- opendata.swiss answers 429 to every page from offset ~10 100 on, also a day later: a limit on deep offsets, not a
-- quota. The harvest now asks each page with `start=0` and a filter for the ids after the last one read, so an open
-- pass needs only that key (`pass_last_key`, which already is the last package read) and how many it has read
-- (`pass_read`). The offset, the count of the first page and the flag of a shifted listing go: with keys, packages that
-- come or go while a pass reads move no page. A pass that had seen its listing shift under offsets starts anew.
--
-- Every rest so far came from that limit (the 429s of opendata.swiss past offset 10 100): it is lifted, so the next
-- run reads on by key at once.
UPDATE public.earthx_harvest_source SET pass_last_key = NULL, pass_read = 0 WHERE pass_moved;

ALTER TABLE public.earthx_harvest_source
    DROP CONSTRAINT earthx_harvest_source_pass_check,
    DROP COLUMN pass_start,
    DROP COLUMN pass_total,
    DROP COLUMN pass_moved,
    ADD CONSTRAINT earthx_harvest_source_pass_check CHECK (
        (pass_run_id IS NULL) = (pass_started_at IS NULL)
        AND (pass_run_id IS NULL) = (pass_read IS NULL)
        AND (pass_run_id IS NOT NULL OR pass_last_key IS NULL)
    );

UPDATE public.earthx_harvest_source SET rest_until = NULL WHERE rest_until IS NOT NULL;
