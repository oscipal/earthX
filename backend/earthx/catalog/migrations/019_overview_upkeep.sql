-- Who does the upkeep of the overview pyramids, among all workers (M5-38, plan docs/plans/m5/m5-35-skalierbarkeit.md B2).
--
-- One row per task: `extend` (copy a confirmed pyramid's objects onto themselves) and `sweep` (expire what ran out, delete
-- what nobody owns). Both ran on every worker at once; now a worker takes a turn first and skips the round when another
-- holds it. A turn is a lease like a build's (`worker`, `lease_until`, renewed while the work goes on); `turn` counts the
-- turns, so a worker that woke up late cannot renew or end a newer one. A lease that ran out is taken over. `next_at` is
-- the earliest time of the next turn, so a round done by one worker counts for all. Written by `jobs` with SQL only.
CREATE TABLE public.earthx_overview_upkeep (
    task        text        PRIMARY KEY CHECK (task IN ('extend', 'sweep')),
    turn        bigint      NOT NULL DEFAULT 1 CHECK (turn >= 1),
    worker      text,
    lease_until timestamptz,
    next_at     timestamptz NOT NULL,
    CONSTRAINT earthx_overview_upkeep_lease CHECK ((worker IS NULL) = (lease_until IS NULL))
);
