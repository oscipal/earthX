-- The index of the dataset search (M5-22b; docs/plans/m5/m5-22-suche-lexikalisch.md §3.4, adr/0026 §4.6).
--
-- One row per dataset of the registry, written by `catalog-load` from the search text (`catalog/search_text.py`) and
-- read by the lexical arm (`catalog/search.py`). It lives next to pgstac, not in it: pgstac searches `q` in English
-- only and without an index (adr/0026 §3.3). `architekturplan.md` 10 calls it `dataset_embedding`; M5-23 adds the
-- embedding columns in a migration of its own (plan A2).
--
-- `document` holds the four parts of the text with their weights, each in the configurations `simple`, `german` and
-- `english` over `unaccent`; computed by `catalog-load`, not as a generated column, because `unaccent` is not
-- IMMUTABLE. `trigram_text` is id, title and keywords in lower case without accents, for typing errors. The box
-- (`west` to `north`, degrees in WGS 84), `time_start`, `time_end` (open is NULL), `has_time_axis` and `item_holding`
-- serve the hard filters of space and time. The box is four numbers, not a geometry: the queue's own databases in the
-- tests carry no PostGIS, and the filter builds the envelope where it needs one.
-- `text_hash` lets `catalog-load` skip a row that has not changed and lets `api` refuse an index older than its text.
--
-- Both extensions are trusted from Postgres 13 on: a role with CREATE on the database may install them.
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE public.earthx_dataset_search (
    dataset_id    text                     PRIMARY KEY,
    title         text                     NOT NULL,
    text_a        text                     NOT NULL,
    text_b        text                     NOT NULL,
    text_c        text                     NOT NULL,
    text_d        text                     NOT NULL,
    text_hash     text                     NOT NULL,
    document      tsvector                 NOT NULL,
    trigram_text  text                     NOT NULL,
    west          double precision         NOT NULL,
    south         double precision         NOT NULL,
    east          double precision         NOT NULL,
    north         double precision         NOT NULL,
    time_start    timestamptz,
    time_end      timestamptz,
    has_time_axis boolean                  NOT NULL,
    item_holding  text                     NOT NULL CHECK (item_holding IN ('federated', 'materialized'))
);

CREATE INDEX earthx_dataset_search_document_idx ON public.earthx_dataset_search USING gin (document);
CREATE INDEX earthx_dataset_search_trigram_idx ON public.earthx_dataset_search USING gin (trigram_text gin_trgm_ops);
