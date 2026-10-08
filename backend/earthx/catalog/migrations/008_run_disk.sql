-- The bytes a run needs in its work directory (M4-11a, Otto 08.10.2026): estimated by
-- `jobs.submit` from the recipe (`processing.plan.disk_needed`), compared by the
-- supervisor with the free space before the child starts. 0 for rows from before.
ALTER TABLE public.earthx_run ADD COLUMN disk_bytes bigint NOT NULL DEFAULT 0 CHECK (disk_bytes >= 0);
