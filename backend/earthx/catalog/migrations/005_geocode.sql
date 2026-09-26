-- The place-search cache and the shared rate slot of M3-07a
-- (docs/plans/m3-07a-ortssuche-backend.md §8, §9; earthx/catalog/geocode_cache.py).
--
-- public. on purpose, same reason as 002_search_cache.sql: pgstac's own roles set
-- `search_path = pgstac, public`, so an unqualified CREATE would land inside pgstac.
--
-- No search text anywhere, and no dataset_id: a place search is not tied to a
-- dataset, and the cache key is a hash of the normalised text and the fixed
-- request parameters (earthx/adapters/nominatim.py), never the text itself.
CREATE TABLE public.earthx_geocode_cache (
    cache_key   text        PRIMARY KEY,
    payload     jsonb       NOT NULL,
    expires_at  timestamptz NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX earthx_geocode_cache_expires_at_idx ON public.earthx_geocode_cache (expires_at);

-- One row per named upstream; M3-07a uses only 'nominatim'. `next_slot` is the
-- earliest instant the next caller — across every `api` process — may send at.
-- No row is seeded here: `earthx.catalog.geocode_cache` upserts it on first use,
-- so a name that is never asked for never has a row either.
CREATE TABLE public.earthx_rate_slots (
    name        text        PRIMARY KEY,
    next_slot   timestamptz NOT NULL
);
