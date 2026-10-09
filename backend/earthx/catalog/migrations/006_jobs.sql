-- The job queue of M4-08a (adr/0013 §5.1, §6.3).
--
-- These tables belong to `jobs`: only `earthx.jobs` reads and writes them, with
-- SQL. They sit in `catalog/migrations/` because the runner in `catalog/schema.py`
-- is the one bookkeeping for every migration (adr/0013 §6.3, F11) and `jobs` may
-- not import `catalog`.
--
-- public. on purpose, as in 002 to 005: pgstac puts `pgstac, public` on the
-- search_path of its own roles, so an unqualified CREATE would land here inside
-- the pgstac schema, where a schema rebuild would take it along.
--
-- A job is the public order, a run is the internal computation (F6): equal orders
-- placed at the same time share one run, and every order has a `recipe_id` of its
-- own. Nothing here is ever shown outside: `run_id` and `cache_key` stay inside the
-- database (Q8), `job_id` and `recipe_id` are random (adr/0014 F15).
--
-- Every foreign key is RESTRICT and has an index. RESTRICT makes a deletion in the
-- wrong order fail loudly instead of taking valid rows along; the index is what
-- keeps that check fast (50 000 expired recipes: 232 s without, 0.38 s with, M5).

-- A recipe holds the AOI and so counts as personal data (Q8). It lives as long as a
-- job or a run refers to it (adr/0013 §5.8, adr/0015 F13).
CREATE TABLE public.earthx_recipe (
    recipe_id   text        PRIMARY KEY,
    body        jsonb       NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- The cap and the limit per host as a row, so that every supervisor reads the same
-- value (adr/0013 §5.7). Change it with SQL, no restart needed.
CREATE TABLE public.earthx_job_limits (
    only_row    boolean     PRIMARY KEY DEFAULT true CHECK (only_row),
    global_cap  integer     NOT NULL CHECK (global_cap > 0),
    host_cap    integer     NOT NULL CHECK (host_cap > 0)
);

INSERT INTO public.earthx_job_limits (only_row, global_cap, host_cap) VALUES (true, 4, 2);

CREATE TABLE public.earthx_run (
    run_id            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cache_key         text        NOT NULL,
    cacheable         boolean     NOT NULL,
    recipe_id         text        NOT NULL REFERENCES public.earthx_recipe ON DELETE RESTRICT,
    status            text        NOT NULL
                      CHECK (status IN ('accepted', 'running', 'successful', 'failed', 'dismissed')),
    pool              text        NOT NULL DEFAULT 'default',
    priority          smallint    NOT NULL DEFAULT 0,
    hosts             text[]      NOT NULL,
    attempt           integer     NOT NULL DEFAULT 0,
    max_attempts      integer     NOT NULL DEFAULT 3,
    not_before        timestamptz NOT NULL DEFAULT now(),
    max_seconds       integer     NOT NULL CHECK (max_seconds > 0),
    progress          smallint    NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    cancel_requested  boolean     NOT NULL DEFAULT false,
    worker            text,
    lease_until       timestamptz,
    error_kind        text,
    result_id         text,
    result            jsonb,
    created_at        timestamptz NOT NULL DEFAULT now(),
    started_at        timestamptz,
    finished_at       timestamptz,
    expires_at        timestamptz NOT NULL
);

CREATE INDEX earthx_run_accepted_idx
    ON public.earthx_run (pool, priority DESC, created_at) WHERE status = 'accepted';
CREATE INDEX earthx_run_lease_idx
    ON public.earthx_run (lease_until) WHERE status = 'running';
CREATE INDEX earthx_run_recipe_idx
    ON public.earthx_run (recipe_id);
CREATE INDEX earthx_run_expires_idx
    ON public.earthx_run (expires_at);
-- At most one active run per cache key: the second equal order attaches to it.
CREATE UNIQUE INDEX earthx_run_active_key_idx
    ON public.earthx_run (cache_key) WHERE status IN ('accepted', 'running');
-- The cache lookup: the newest finished, cacheable run of a key.
CREATE INDEX earthx_run_cache_idx
    ON public.earthx_run (cache_key, finished_at) WHERE status = 'successful' AND cacheable;

CREATE TABLE public.earthx_job (
    job_id      text        PRIMARY KEY,
    run_id      bigint      NOT NULL REFERENCES public.earthx_run ON DELETE RESTRICT,
    recipe_id   text        NOT NULL REFERENCES public.earthx_recipe ON DELETE RESTRICT,
    dismissed   boolean     NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX earthx_job_run_idx ON public.earthx_job (run_id);
CREATE INDEX earthx_job_recipe_idx ON public.earthx_job (recipe_id);
