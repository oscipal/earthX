-- The state of the harvest (M5-19; docs/plans/m5/m5-19-harvest-kern.md §3, adr/0025 §5.3).
--
-- `earthx_harvest_run`: one row per run of one source. A run holds its source while its row is `running` and its
-- `lease_until` lies ahead; it renews the term after every page (A1, the form of the places of 022). The partial unique
-- index lets at most one `running` row per source exist; a run whose term ran out is closed as `interrupted` by the next
-- run of the same source before it starts. Counts only, never an address, a key of a find or an extent.
--
-- `earthx_harvest_source`: per source the validators of its listing, for a listing that fits on one page: a `304` on
-- it means the whole listing is unchanged (plan §4.2).
--
-- `earthx_raw_record`: the last raw answer per find, gzip, at most 1 MB; the history lives in the transitions and in
-- Git, not here (adr/0025 §5.3). `earthx_record_state`: the state per find and its intermediate form (plan §5.1);
-- what M5-20 adds (`needs_rule`, `in_review`, ...) comes with its own migration. `earthx_state_transition`: from, to,
-- when, run, reason.
CREATE TABLE public.earthx_harvest_run (
    run_id            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id         text        NOT NULL,
    kind              text        NOT NULL CHECK (kind IN ('full', 'incremental', 'reextract')),
    status            text        NOT NULL CHECK (status IN ('running', 'done', 'interrupted', 'failed')),
    started_at        timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at       timestamptz,
    lease_until       timestamptz NOT NULL,
    requests          integer     NOT NULL DEFAULT 0 CHECK (requests >= 0),
    not_modified      integer     NOT NULL DEFAULT 0 CHECK (not_modified >= 0),
    bytes             bigint      NOT NULL DEFAULT 0 CHECK (bytes >= 0),
    found_new         integer     NOT NULL DEFAULT 0 CHECK (found_new >= 0),
    found_changed     integer     NOT NULL DEFAULT 0 CHECK (found_changed >= 0),
    found_unchanged   integer     NOT NULL DEFAULT 0 CHECK (found_unchanged >= 0),
    invalid           integer     NOT NULL DEFAULT 0 CHECK (invalid >= 0),
    gone              integer     NOT NULL DEFAULT 0 CHECK (gone >= 0),
    extent_unknown    integer     NOT NULL DEFAULT 0 CHECK (extent_unknown >= 0),
    stop_reason       text        CHECK (stop_reason IN
                                         ('host_resting', 'robots', 'request_budget', 'upstream', 'shape', 'lease_expired', 'error')),
    CHECK ((status = 'running') = (finished_at IS NULL)),
    CHECK ((status IN ('running', 'done')) = (stop_reason IS NULL))
);

CREATE UNIQUE INDEX earthx_harvest_run_running_idx ON public.earthx_harvest_run (source_id) WHERE status = 'running';
CREATE INDEX earthx_harvest_run_source_idx ON public.earthx_harvest_run (source_id, run_id);

CREATE TABLE public.earthx_harvest_source (
    source_id         text        PRIMARY KEY,
    list_etag         text,
    list_last_modified text,
    updated_at        timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE public.earthx_raw_record (
    source_id         text        NOT NULL,
    source_key        text        NOT NULL,
    raw_gzip          bytea       CHECK (octet_length(raw_gzip) <= 1048576),
    raw_sha256        text        NOT NULL CHECK (raw_sha256 ~ '^[0-9a-f]{64}$'),
    fetched_at        timestamptz NOT NULL DEFAULT clock_timestamp(),
    run_id            bigint      NOT NULL REFERENCES public.earthx_harvest_run (run_id),
    PRIMARY KEY (source_id, source_key)
);

CREATE INDEX earthx_raw_record_run_idx ON public.earthx_raw_record (run_id);

CREATE TABLE public.earthx_record_state (
    source_id         text        NOT NULL,
    source_key        text        NOT NULL,
    state             text        NOT NULL CHECK (state IN ('extracted', 'invalid', 'gone')),
    reason            text        CHECK (reason IN ('too_large', 'no_title', 'no_link', 'shape')),
    extracted         jsonb,
    extracted_sha256  text        CHECK (extracted_sha256 ~ '^[0-9a-f]{64}$'),
    extent_known      boolean,
    last_seen_run     bigint      NOT NULL REFERENCES public.earthx_harvest_run (run_id),
    updated_at        timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (source_id, source_key),
    CHECK ((state = 'invalid') = (reason IS NOT NULL)),
    CHECK ((state = 'extracted') = (extracted IS NOT NULL AND extracted_sha256 IS NOT NULL AND extent_known IS NOT NULL))
);

CREATE INDEX earthx_record_state_seen_idx ON public.earthx_record_state (source_id, last_seen_run);

CREATE TABLE public.earthx_state_transition (
    transition_id     bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id         text        NOT NULL,
    source_key        text        NOT NULL,
    from_state        text,
    to_state          text        NOT NULL,
    reason            text,
    run_id            bigint      NOT NULL REFERENCES public.earthx_harvest_run (run_id),
    at                timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX earthx_state_transition_record_idx ON public.earthx_state_transition (source_id, source_key);
CREATE INDEX earthx_state_transition_run_idx ON public.earthx_state_transition (run_id);

-- The foreign key 021 left for this migration (`run_id` of a harvested listed entry).
ALTER TABLE public.earthx_listed_entry
    ADD CONSTRAINT earthx_listed_entry_run_fk FOREIGN KEY (run_id) REFERENCES public.earthx_harvest_run (run_id);
CREATE INDEX earthx_listed_entry_run_idx ON public.earthx_listed_entry (run_id);
