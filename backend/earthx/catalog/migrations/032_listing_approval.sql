-- The approval of harvested listed entries (M5-20; docs/plans/m5/m5-20-freigabe-geernteter-eintraege.md §5, §6, §12;
-- adr/0033 §7, §8, §11).
--
-- `earthx_listed_entry` now also holds every harvested find that is not blocked, in a state that is not visible:
-- `in_review` (in the stack of a run, waiting for Otto's approval file), `needs_rule` (no licence rule, with
-- `waiting_reason`), `not_geodata` (hidden by the rule of `backend/catalog/geodata.yaml`, F3 = 1; no tombstone, a
-- changed rule brings it back) and `duplicate` (another row is the main entry of the same dataset, `duplicate_of`,
-- F4 = 1). Only `published` is visible, as before.
--
-- `verdict` is what the report derived for a harvested find before dedupe: `ok` (a licence rule matches),
-- `needs_rule` (it waits, `waiting_reason`: no licence, an unknown one, one not granted, or no known way to get the
-- data) or `not_geodata`. The state follows from it: a duplicate hides whatever its verdict; `ok` is `in_review` until
-- an approval publishes it, and stays `published` while only describing fields change (adr/0033 §11, U1). Account and
-- delivery are required only of what can be seen or approved; a find whose source names neither waits (M5-19 §5.2).
--
-- A footprint is no longer required (F1 = 1): an extent derived from a publisher or from the state of a catalogue
-- carries regions only, so that an area finds it only where its footprint is known. `extent_basis` says where the
-- extent comes from; NULL for a hand entry, whose extent is always its own box.
--
-- `earthx_listing_batch` is the stack of one report of one source: the sorted manifest (id, hash of the content,
-- licence rule) in `earthx_listing_batch_entry` and its SHA-256 as fingerprint. An approval file in the image with
-- `decision: approved` and the same fingerprint publishes it. At most one open stack per source; a later report
-- takes over what an open one held and lets it expire (adr/0033 §8.3).
DO $$
DECLARE
    found text;
BEGIN
    -- The check of migration 021 that every non-tombstone row has a footprint; found by its text, not its name.
    SELECT conname INTO found FROM pg_constraint
    WHERE conrelid = 'public.earthx_listed_entry'::regclass AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%num_nulls(content, content_sha256, sort_title, footprint, regions%';
    IF found IS NULL THEN
        RAISE EXCEPTION 'the footprint check of migration 021 is missing';
    END IF;
    EXECUTE format('ALTER TABLE public.earthx_listed_entry DROP CONSTRAINT %I', found);
END
$$;

ALTER TABLE public.earthx_listed_entry
    DROP CONSTRAINT earthx_listed_entry_state_check,
    ADD CONSTRAINT earthx_listed_entry_state_check CHECK (state IN (
        'published', 'in_review', 'needs_rule', 'blocked', 'tombstone', 'superseded', 'not_geodata', 'duplicate')),
    ADD CONSTRAINT earthx_listed_entry_content_check CHECK (
        state = 'tombstone' OR num_nulls(content, content_sha256, sort_title, regions, keywords, data_kind, category,
                                         link_host) = 0),
    ADD CONSTRAINT earthx_listed_entry_access_check CHECK (
        state NOT IN ('published', 'in_review') OR num_nulls(account, delivery) = 0),
    ADD COLUMN extent_basis text CHECK (extent_basis IN ('source', 'place', 'publisher', 'catalog', 'none')),
    ADD CONSTRAINT earthx_listed_entry_footprint_check CHECK (
        CASE WHEN footprint IS NULL
             THEN state = 'tombstone' OR coalesce(extent_basis, '') IN ('publisher', 'catalog', 'none')
             ELSE coalesce(extent_basis, 'source') IN ('source', 'place') END),
    ADD COLUMN duplicate_of text COLLATE "C",
    ADD CONSTRAINT earthx_listed_entry_duplicate_check CHECK ((state = 'duplicate') = (duplicate_of IS NOT NULL)),
    ADD COLUMN verdict text CHECK (verdict IN ('ok', 'needs_rule', 'not_geodata')),
    ADD COLUMN waiting_reason text CHECK (waiting_reason IN ('no_licence', 'unknown_licence', 'not_granted', 'no_access')),
    ADD CONSTRAINT earthx_listed_entry_waiting_check CHECK ((verdict = 'needs_rule') = (waiting_reason IS NOT NULL)),
    ADD CONSTRAINT earthx_listed_entry_verdict_state_check CHECK (
        (state <> 'needs_rule' OR verdict = 'needs_rule') AND (state <> 'not_geodata' OR verdict = 'not_geodata')
        AND (state <> 'in_review' OR verdict = 'ok')),
    -- When a full pass of the source first did not name a published find; a later full pass without it makes it a
    -- tombstone `source_removed` (adr/0033 §9, plan A4).
    ADD COLUMN missing_since timestamptz,
    -- The keys dedupe compares (DOI, identifier, collection id; plan §8, §13b), each with its kind as a prefix.
    ADD COLUMN dedupe_keys text[],
    -- The hash of what the row was derived from: the intermediate form and the rule files (plan §5). Equal: the
    -- report leaves the row alone.
    ADD COLUMN derived_sha256 text CHECK (derived_sha256 ~ '^[0-9a-f]{64}$');

CREATE INDEX earthx_listed_entry_source_state_idx ON public.earthx_listed_entry (source_id, state);
-- The duplicates of an entry, read when it is served (`earthx:also_at`, plan §8).
CREATE INDEX earthx_listed_entry_duplicate_idx ON public.earthx_listed_entry (duplicate_of) WHERE state = 'duplicate';

CREATE TABLE public.earthx_listing_batch (
    batch_id          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id         text        NOT NULL,
    fingerprint       text        NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    entries           integer     NOT NULL CHECK (entries > 0),
    created_at        timestamptz NOT NULL DEFAULT clock_timestamp(),
    state             text        NOT NULL CHECK (state IN ('open', 'expired', 'published', 'revoked')),
    approval_file     text,
    approval_sha256   text        CHECK (approval_sha256 ~ '^[0-9a-f]{64}$'),
    published_at      timestamptz,
    CHECK ((state IN ('published', 'revoked')) = (approval_file IS NOT NULL AND published_at IS NOT NULL))
);

CREATE UNIQUE INDEX earthx_listing_batch_open_idx ON public.earthx_listing_batch (source_id) WHERE state = 'open';
CREATE INDEX earthx_listing_batch_fingerprint_idx ON public.earthx_listing_batch (fingerprint);

CREATE TABLE public.earthx_listing_batch_entry (
    batch_id          bigint      NOT NULL REFERENCES public.earthx_listing_batch (batch_id) ON DELETE CASCADE,
    dataset_id        text        COLLATE "C" NOT NULL,
    content_sha256    text        NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    license_rule      text        NOT NULL,
    PRIMARY KEY (batch_id, dataset_id)
);
