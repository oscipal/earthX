-- Listed entries in the index of the dataset search (adr/0026 §14 point 1: full and listed entries in one search table).
--
-- `entry` says which kind of entry a row is: `full` rows come from the registry (`write_search_index`), `listed` rows
-- from the published rows of `earthx_listed_entry` (`write_listed_search_index`), both written by `catalog-load`. A
-- listed row has no item holding; its box is the envelope of its footprint, its time axis is its period. The search
-- reads the footprint and the state of a listed row from `earthx_listed_entry` itself, so a row the harvest took back
-- since the last load is never a hit.
ALTER TABLE public.earthx_dataset_search
    ADD COLUMN entry text NOT NULL DEFAULT 'full' CHECK (entry IN ('full', 'listed')),
    ALTER COLUMN item_holding DROP NOT NULL,
    ADD CONSTRAINT earthx_dataset_search_item_holding_of_full CHECK ((entry = 'full') = (item_holding IS NOT NULL));

ALTER TABLE public.earthx_dataset_search ALTER COLUMN entry DROP DEFAULT;
