-- The calendar years (UTC) the scenes of an order were acquired in (NM4-01, Otto 25.10.2026): the year
-- in "Contains modified Copernicus Sentinel data [Year]" is the year of acquisition, a span when the
-- scenes lie in several years. `api` finds them from the items at acceptance and hands them to
-- `jobs.submit`; `jobs` stores them without reading them. The attribution of the job's recipe.json,
-- ATTRIBUTION.txt and citation.bib is built from them at every download, never from the clock.
--
-- They belong to the job, not the run: equal orders share a run, but each has the scenes it named.
-- Both are set or both are NULL. NULL for a dataset whose attribution names no year (the DEM) and for
-- jobs from before this column whose scenes did not share one day; a job whose scenes did share one
-- gets that day's year here.
ALTER TABLE public.earthx_job
    ADD COLUMN acquired_first_year smallint,
    ADD COLUMN acquired_last_year smallint,
    ADD CONSTRAINT earthx_job_acquired_years CHECK (
        (acquired_first_year IS NULL) = (acquired_last_year IS NULL)
        AND (acquired_first_year IS NULL OR acquired_first_year <= acquired_last_year)
    );

UPDATE public.earthx_job
SET acquired_first_year = EXTRACT(YEAR FROM acquired_on), acquired_last_year = EXTRACT(YEAR FROM acquired_on)
WHERE acquired_on IS NOT NULL;
