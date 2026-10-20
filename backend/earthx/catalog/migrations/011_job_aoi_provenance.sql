-- Where a place-search AOI of a raster order came from (M4-30, Otto 20.10.2026): the attribution, the
-- licence and the source of the geometry, as `api` checked them. The ZIP of the job names them in
-- ATTRIBUTION.txt and aoi.geojson, as the export's ZIP does (M4-11 F4).
--
-- It belongs to the job, not the run: equal orders share a run, and one of them may carry an origin
-- and the other not. It is no part of the recipe, its hash or the cache key. `jobs` stores it without
-- reading it. An export keeps its origin in `earthx_run.attachments` and leaves this NULL.
--
-- NULL for every job from before this column and for every order whose area is not from a place search.
ALTER TABLE public.earthx_job ADD COLUMN aoi_provenance jsonb;
