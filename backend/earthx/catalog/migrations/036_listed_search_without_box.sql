-- A listed entry without a footprint in the index of the dataset search (M5-42; Otto, 23.11.2026).
--
-- A published listed entry may have no footprint: its extent is known only from its regions, or not at all
-- (`extent_basis` `publisher`, `catalog` or `none`, migration 032; M5-20 F1, F11, A19). Its row in the index has no
-- box then: the area filter never meets it, the filters of category and region still do. A full row always has a box,
-- and a box is all four edges or none.
ALTER TABLE public.earthx_dataset_search
    ALTER COLUMN west DROP NOT NULL,
    ALTER COLUMN south DROP NOT NULL,
    ALTER COLUMN east DROP NOT NULL,
    ALTER COLUMN north DROP NOT NULL,
    ADD CONSTRAINT earthx_dataset_search_box_check CHECK (
        num_nulls(west, south, east, north) IN (0, 4) AND (entry = 'listed' OR west IS NOT NULL));
