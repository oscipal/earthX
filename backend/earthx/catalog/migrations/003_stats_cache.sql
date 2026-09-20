-- The statistics cache of the tile path (adr/0006 §5 "Zu Frage 3", Otto's answer 3).
-- Its own table rather than a second meaning inside earthx_search_cache: it has its
-- own lifetime (30 days against 5 minutes / 24 hours) and its own sweep, and a table
-- whose name says "search" would answer questions about tiles.
--
-- Why 30 days is not a freshness question: the statistics of an immutable COG never
-- change, so the expiry is housekeeping, not correctness. A miss costs the ~1 s
-- adr/0006 §3.4 measured and nothing else (E5) — an empty table makes the first view
-- slower, never wrong.
--
-- public. on purpose, for the same reason as 002: pgstac puts `pgstac, public` on the
-- search_path of its own roles, so an unqualified CREATE would land this table inside
-- the pgstac schema, where a schema rebuild would take it along.
--
-- The key is an opaque hash of dataset, item, asset and the rendering parameters
-- (earthx/catalog/stats_cache.py); dataset_id is carried beside it so rows can be
-- attributed, and later dropped, per dataset without decoding anything. No AOI is
-- stored: statistics are read per asset, not per area of interest.
CREATE TABLE public.earthx_stats_cache (
    cache_key   text        PRIMARY KEY,
    dataset_id  text        NOT NULL,
    payload     jsonb       NOT NULL,
    expires_at  timestamptz NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- For the sweep that will remove expired rows once the cache carries real load, the
-- same way 002 prepares it for the search cache.
CREATE INDEX earthx_stats_cache_expires_at_idx ON public.earthx_stats_cache (expires_at);
