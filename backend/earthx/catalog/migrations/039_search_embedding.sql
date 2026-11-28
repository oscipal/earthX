-- The vector arm of the dataset search (adr/0026 §14; docs/plans/m5/m5-23-vektorsuche.md §4.1).
--
-- `embedding` is the vector of the parts A and B of a row's search text, `embedding_model` the model and revision that
-- computed it; both are set or both are empty. A row that `catalog-load` writes with a new text loses its vector, and
-- the next step of the same run embeds it again, in batches after the main transaction (M5-42 F6): a row without a
-- vector is no hit of the vector arm until then. 384 dimensions are those of the chosen model; another dimension is a
-- new migration. `halfvec` keeps the row inside the page, HNSW with the defaults of pgvector (m 16, ef_construction 64).
--
-- pgvector is not a trusted extension: like every migration, this one runs as the owner of the database, a superuser
-- in compose and CI (M5-43).
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE public.earthx_dataset_search
    ADD COLUMN embedding halfvec(384),
    ADD COLUMN embedding_model text,
    ADD CONSTRAINT earthx_dataset_search_embedding_with_model CHECK ((embedding IS NULL) = (embedding_model IS NULL));

CREATE INDEX earthx_dataset_search_embedding_idx ON public.earthx_dataset_search
    USING hnsw (embedding halfvec_cosine_ops) WITH (m = 16, ef_construction = 64);
