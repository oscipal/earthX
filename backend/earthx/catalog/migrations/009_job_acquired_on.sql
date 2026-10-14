-- The UTC day of acquisition of the scenes an order reads (M4-11b-1, Otto 14.10.2026): the date in the
-- file name of a download (ZIP and single links). `api` finds it from the items at acceptance (the
-- overpass key of the registry, `catalog.registry.acquisition_day`) and hands it to `jobs.submit`; `jobs`
-- stores it without reading it. It belongs to the job, not the run: equal orders share a run, but each
-- has the scenes it named.
--
-- NULL where the dataset has no single day of acquisition (the DEM), where the order's scenes do not
-- share one, and for jobs from before this column; their downloads carry the day of the run with the
-- prefix "run".
ALTER TABLE public.earthx_job ADD COLUMN acquired_on date;
