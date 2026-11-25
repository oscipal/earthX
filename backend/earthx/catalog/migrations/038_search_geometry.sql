-- The area filter of the dataset search through spatial indexes (M5-65; docs/plans/m5/m5-65-suche-mit-flaeche.md).
--
-- A listed row is matched against the footprint in `earthx_listed_entry`, whose GiST index (migration 021) serves a
-- small area before any text is read. For that the search starts from the entries the area keeps and looks each one up
-- here by `dataset_id`. `earthx_listed_entry.dataset_id` is `COLLATE "C"`, this table's is not, so the comparison runs
-- in "C" and the primary key of this table cannot serve it: the last index is the same key in that collation.
--
-- A full row has its box as four numbers only, so the filter built the envelope per row. `geometry` is that envelope,
-- computed by Postgres from the box and never written by hand, so no writer can leave it out of step with the box. A
-- listed row has none: its footprint is the one of its entry. The index is partial on full rows: it finds the few of
-- them without reading the listed ones. The area condition of a full row stays one `CASE` (a materialized dataset with
-- items is met by its items, not by its box), so the index does not serve the condition itself.
ALTER TABLE public.earthx_dataset_search
    ADD COLUMN geometry geometry(Polygon, 4326)
        GENERATED ALWAYS AS (CASE WHEN entry = 'full' THEN ST_MakeEnvelope(west, south, east, north, 4326) END) STORED;

CREATE INDEX earthx_dataset_search_geometry_idx ON public.earthx_dataset_search USING gist (geometry)
    WHERE entry = 'full';

CREATE UNIQUE INDEX earthx_dataset_search_id_c_idx ON public.earthx_dataset_search (dataset_id COLLATE "C");
