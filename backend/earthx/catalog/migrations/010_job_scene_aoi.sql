-- Whether an order named whole scenes and no area (M4-30, Otto 19.10.2026): its recipe then carries the
-- union of the scenes' footprints as AOI (M4-12), which the recipe cannot tell from an area somebody drew.
-- `aoi.geojson` in the ZIP of the job says so. `api` finds it at acceptance and hands it to `jobs.submit`;
-- `jobs` stores it without reading it. It belongs to the job, not the run, like the day of acquisition.
--
-- false for every job from before this column and for every order with an area of its own.
ALTER TABLE public.earthx_job ADD COLUMN scene_aoi boolean NOT NULL DEFAULT false;
