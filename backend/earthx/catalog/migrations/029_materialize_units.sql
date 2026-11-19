-- The state of a source per unit, for `materialize` with `updates.detect: units` (M5-58, adr/0038 §3.5).
--
-- A unit is the smallest thing at which the source shows a change (a file, an entry of a listing); a group is the
-- listing document that names it (a source item, a page). A run asks each group conditionally with its stored
-- validator, judges each unit of a changed group by its validators (listing first, then a conditional HEAD, then a
-- hash) and writes only the items whose assets change. Written in the transaction of the run: a failed run leaves the
-- state as it was, like the items. Nothing here is a cache: without it the next run reads every unit again.
--
-- public., like 004: an unqualified CREATE would land in the pgstac schema (see 004).

CREATE TABLE public.earthx_materialize_group (
    dataset_id text NOT NULL,
    group_key  text NOT NULL,
    -- The ETag the group answered with, or a hash of its body where it gives none; NULL where neither is known.
    validator  text,
    seen_at    timestamptz NOT NULL,
    PRIMARY KEY (dataset_id, group_key)
);

CREATE TABLE public.earthx_materialize_unit (
    dataset_id     text        NOT NULL,
    unit_key       text        NOT NULL,
    group_key      text        NOT NULL,
    -- Where a HEAD asks about the unit: an https address on a host of the entry's `source.asset_hosts`.
    href           text        NOT NULL,
    state          text        NOT NULL CHECK (state IN ('provisional', 'final')),
    etag           text,
    last_modified  text,
    checksum       text,
    content_sha256 text,
    -- Every (item id, asset key) the unit contributes to, also those where a unit of higher state wins:
    -- a JSON array of two-element arrays.
    contributes    jsonb       NOT NULL CHECK (jsonb_typeof(contributes) = 'array'),
    seen_at        timestamptz NOT NULL,
    changed_at     timestamptz NOT NULL,
    PRIMARY KEY (dataset_id, unit_key)
);

-- What a run of the kind did per unit, beside what it wrote; 0 on every run of `detect: whole` and every older row.
ALTER TABLE public.earthx_materialize_runs
    ADD COLUMN units_new       integer NOT NULL DEFAULT 0,
    ADD COLUMN units_changed   integer NOT NULL DEFAULT 0,
    ADD COLUMN units_unchanged integer NOT NULL DEFAULT 0,
    ADD COLUMN units_gone      integer NOT NULL DEFAULT 0,
    ADD COLUMN items_replaced  integer NOT NULL DEFAULT 0;
