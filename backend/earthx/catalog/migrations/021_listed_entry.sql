-- Listed entries in Postgres (M5-40; docs/plans/m5/m5-40-gelistete-in-postgres.md §5.1, adr/0033 §5, §9, §10).
--
-- `earthx_listed_entry` holds one row per listed entry: a catalogue entry with a link, of any data kind, also without a
-- direct download (adr/0033). Full entries stay YAML in the image and pgstac; a listed entry is never written to pgstac
-- and never read into the registry of a process (M5-35 B5). `api` reads one page per request through the partial
-- indexes below; no process holds the whole list.
--
-- `state`: only `published` is visible. `in_review`, `needs_rule` and `blocked` are the states of the approval of
-- M5-20 (adr/0033 §7, §11), here already so that M5-20 need not change the check. `superseded` is a row whose id a full
-- entry took over (adr/0033 §11). `tombstone` is a removed entry (adr/0033 §9): content and every field of it are gone,
-- id, key at the source, reason and day stay, and `api` answers `410`.
--
-- Provenance per entry (adr/0033 §10): the licence rule, the hash of the rule files, the run, the approval file with
-- its hash and day. Hashes rather than commits, because the image carries no Git history (plan A3). `run_id` gets its
-- foreign key when M5-19 creates `earthx_harvest_run`.
--
-- `earthx_region` holds the outlines `regions` is derived from (`backend/catalog/regions.json`, Natural Earth), and
-- `earthx_region_part` the same cut into small pieces; both written by `catalog-load`.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE public.earthx_region (
    code    text                            PRIMARY KEY CHECK (code ~ '^[A-Z]{2}(-[A-Z0-9]{1,3})?$'),
    level   text                            NOT NULL CHECK (level IN ('state', 'subdivision')),
    name    text                            NOT NULL,
    outline geometry(MultiPolygon, 4326)    NOT NULL
);

-- The outlines cut into pieces of at most 128 points (`ST_Subdivide`): deriving the regions of 10⁶ entries against whole
-- outlines of thousands of points takes far longer than against small pieces (M5-40 plan §5.6). Rewritten by
-- `catalog-load` whenever an outline changes.
CREATE TABLE public.earthx_region_part (
    code    text                        NOT NULL REFERENCES public.earthx_region (code) ON DELETE CASCADE,
    part    geometry(Geometry, 4326)    NOT NULL
);

CREATE INDEX earthx_region_part_part_idx ON public.earthx_region_part USING gist (part);
CREATE INDEX earthx_region_part_code_idx ON public.earthx_region_part (code);

CREATE TABLE public.earthx_listed_entry (
    dataset_id        text        COLLATE "C" PRIMARY KEY
                                  CHECK (dataset_id ~ '^[a-z0-9][a-z0-9._-]{0,127}$' AND dataset_id NOT LIKE 'proto-%'),
    source_id         text        NOT NULL,
    source_key        text        NOT NULL,
    state             text        NOT NULL
                                  CHECK (state IN ('published', 'in_review', 'needs_rule', 'blocked', 'tombstone', 'superseded')),
    content           jsonb,
    content_sha256    text,
    sort_title        text        COLLATE "C",
    footprint         geometry(Geometry, 4326),
    time_span         tstzrange,
    regions           text[],
    data_kind         text        CHECK (data_kind IN ('raster', 'vector', 'table', 'document', 'service', 'other')),
    account           text        CHECK (account IN ('none', 'anonymous_token', 'free_account', 'requester_pays', 'paid')),
    delivery          text        CHECK (delivery IN ('download', 'service', 'order', 'on_request')),
    publisher         text,
    link_host         text,
    license_ref       text,
    license_rule      text,
    rule_files_sha256 text,
    run_id            bigint,
    approval_file     text,
    approval_sha256   text,
    approved_on       date,
    published_at      timestamptz,
    harvested_at      timestamptz,
    checked_at        timestamptz,
    removed_reason    text        CHECK (removed_reason IN
                                         ('provider_request', 'not_geodata', 'quality', 'legal', 'other', 'source_removed')),
    removed_on        date,
    UNIQUE (source_id, source_key),
    -- A tombstone keeps nothing of the entry but its id, its key at the source, the reason and the day.
    CHECK ((state = 'tombstone') = (removed_reason IS NOT NULL AND removed_on IS NOT NULL)),
    CHECK (state <> 'tombstone' OR num_nonnulls(content, content_sha256, sort_title, footprint, time_span, regions,
                                                data_kind, account, delivery, publisher, link_host, license_ref) = 0),
    CHECK (state = 'tombstone' OR num_nulls(content, content_sha256, sort_title, footprint, regions, data_kind, account,
                                            delivery, link_host) = 0)
)
-- The document goes out of the row as soon as the row is larger than 128 bytes, so that the columns the filters and the
-- order read lie close together and a page of matches reads few blocks.
WITH (toast_tuple_target = 128);

-- The read path of `api`: a page in the order of the catalogue, and the filters of area, period and region. The order is
-- that of the bytes (`COLLATE "C"` on `dataset_id` and `sort_title`), the same as Python's order of code points: `api`
-- lays full and listed entries into one page in Python and goes on after the key of its last entry, and under a
-- collation like en_US, which skips spaces and punctuation, a key would sort differently there and in Postgres.
CREATE INDEX earthx_listed_entry_page_idx ON public.earthx_listed_entry (sort_title, dataset_id)
    WHERE state = 'published';
CREATE INDEX earthx_listed_entry_footprint_idx ON public.earthx_listed_entry USING gist (footprint)
    WHERE state = 'published';
CREATE INDEX earthx_listed_entry_time_idx ON public.earthx_listed_entry USING gist (time_span)
    WHERE state = 'published';
CREATE INDEX earthx_listed_entry_regions_idx ON public.earthx_listed_entry USING gin (regions)
    WHERE state = 'published';
-- The blocklist (adr/0033 §9): a publisher of a source, a host.
CREATE INDEX earthx_listed_entry_publisher_idx ON public.earthx_listed_entry (source_id, publisher);
CREATE INDEX earthx_listed_entry_host_idx ON public.earthx_listed_entry (link_host);
