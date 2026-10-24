-- The application cache of E4: Postgres, because pgstac needs it anyway
-- (docs/plans/m1-fundament.md §1, E4; architekturplan.md 15.3 keeps Redis for a
-- measured need). Used by the federated item search of M1-06.
--
-- public. on purpose: pgstac puts `pgstac, public` on the search_path of its own
-- roles, so an unqualified CREATE would land this table inside the pgstac schema,
-- where a schema rebuild would take it along.
--
-- The key is an opaque hash of the normalised search (earthx/adapters/earth_search.py);
-- dataset_id is carried beside it so rows can be attributed, and later dropped, per
-- dataset without decoding anything. No coordinates are stored outside the payload,
-- and nothing here is ever logged (projektplan.md 7, point 6).
CREATE TABLE public.earthx_search_cache (
    cache_key   text        PRIMARY KEY,
    dataset_id  text        NOT NULL,
    payload     jsonb       NOT NULL,
    expires_at  timestamptz NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- For the sweep that will remove expired rows once the cache carries real load.
-- M1 has one collection and reads past the expiry instead (adr/0005 rule II).
CREATE INDEX earthx_search_cache_expires_at_idx ON public.earthx_search_cache (expires_at);
