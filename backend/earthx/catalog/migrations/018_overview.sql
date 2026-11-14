-- The overview pyramid as a job (M5-30b part 8b, adr/0032 §5.2, §5.3; plan docs/plans/m5/m5-30-bild-bei-jedem-zoom.md §4.8).
--
-- Two tables, both written by SQL only: `earthx_overview_request` by `catalog` (`materialize` asks for a pyramid after a
-- run that loaded a new source version; `discovery` may import `catalog`, not `jobs`), `earthx_overview` by `jobs` (the
-- worker builds, and records where a build stands). They sit here, as the queue of 006 does, because `jobs` may not
-- import `catalog` and the bookkeeping of the runner is one. No foreign keys: a request outlives its pyramid, a pyramid
-- outlives its request.
--
-- `version` is the name of a source version in the object key (`overviews/{dataset_id}/{version}/{z}/{x}/{y}.tif`): the
-- first 16 hex digits of the SHA-256 of `source_version`, never the version itself (an ETag has quotes and slashes). One
-- function computes it, for the generated column of the request and for the one statement in `jobs` that asks for
-- what is missing, so the two cannot drift apart.
CREATE OR REPLACE FUNCTION public.earthx_overview_version(source_version text) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    AS $$ SELECT left(encode(sha256(convert_to(source_version, 'UTF8')), 'hex'), 16) $$;

-- A wish for a pyramid: "this dataset has this source version now". Idempotent per dataset and version; a second
-- materialize run of the same version only moves `requested_at`. The worker builds for the latest request of a dataset
-- and ignores older ones.
CREATE TABLE public.earthx_overview_request (
    dataset_id     text        NOT NULL,
    source_version text        NOT NULL,
    version        text        GENERATED ALWAYS AS (public.earthx_overview_version(source_version)) STORED,
    requested_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_id, source_version)
);

CREATE INDEX earthx_overview_request_latest_idx ON public.earthx_overview_request (dataset_id, requested_at DESC);

-- One row per dataset and version of a pyramid.
--
-- `building` holds a lease like a run does (`worker`, `lease_until`, and `attempts` as the number of the attempt that
-- owns the row, so a worker that woke up late changes nothing); `hosts` are the hosts the build reads from, of which
-- at most one build runs at a time. `failed` names its kind (`failure_kind`, a short name, never an address). `ready`
-- has `checked_at`, the oldest time any of its objects was read at the source, and the term of 30 days counts from it
-- (adr/0032 §5.2). `confirmed_at` is the time a check at the source last found this version unchanged; the worker
-- extends the term (`checked_at` := `confirmed_at`) when it is later than `checked_at` (§5.3), so the worker itself
-- never asks the source. `base_hashes` maps a base tile (`x/y`) to the hash of the items it read, where the dataset's items allow one.
CREATE TABLE public.earthx_overview (
    dataset_id   text        NOT NULL,
    version      text        NOT NULL CHECK (version ~ '^[0-9a-f]{16}$'),
    status       text        NOT NULL CHECK (status IN ('building', 'ready', 'failed')),
    failure_kind text,
    attempts     integer     NOT NULL DEFAULT 1 CHECK (attempts >= 1),
    hosts        text[]      NOT NULL DEFAULT '{}',
    worker       text,
    lease_until  timestamptz,
    progress     integer     NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    base_hashes  jsonb       NOT NULL DEFAULT '{}',
    checked_at   timestamptz,
    confirmed_at timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_id, version),
    CONSTRAINT earthx_overview_failure_kind CHECK ((status = 'failed') = (failure_kind IS NOT NULL)),
    CONSTRAINT earthx_overview_ready_checked CHECK (status <> 'ready' OR checked_at IS NOT NULL),
    CONSTRAINT earthx_overview_lease CHECK ((status = 'building') = (lease_until IS NOT NULL))
);

CREATE INDEX earthx_overview_checked_at_idx ON public.earthx_overview (checked_at) WHERE status = 'ready';
