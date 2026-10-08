-- The side files of an export job (M4-11a, plan m4-11 §3.6): ATTRIBUTION.txt,
-- citation.bib and aoi.geojson, built by `api` from the registry and the order,
-- and the attribution for the provenance. `jobs` hands them to the run untouched;
-- an export always has a run of its own (F3), so they belong to exactly one order.
-- NULL for every other run. They expire with the run (Q10).
ALTER TABLE public.earthx_run ADD COLUMN attachments jsonb;
