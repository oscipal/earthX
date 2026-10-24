-- The permalink of M4-19e (docs/plans/m4/m4-19-teilen-und-beschreiben.md §3.5, Otto 20.10.2026):
-- an order and a small view, put there when someone presses "Share", under an identifier of its own.
--
-- It is personal data: `body` holds the order with its area (Q8). It is no recipe and no job, it
-- shares no row with either, and nothing refers to it. The identifier is random (`secrets.token_urlsafe(16)`),
-- never a hash of the order. `delete_key_hash` is the SHA-256 of the key that `api` hands out once, on
-- creation; the key itself is stored nowhere.
--
-- The term is fixed at 30 days from creation (adr/0015 §13): looking at a permalink never moves
-- `expires_at`. The hourly cleanup of `jobs` deletes what has expired, the row whole.
CREATE TABLE public.earthx_permalink (
    permalink_id    text        PRIMARY KEY,
    body            jsonb       NOT NULL,
    delete_key_hash text        NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    expires_at      timestamptz NOT NULL
);

CREATE INDEX earthx_permalink_expires_at_idx ON public.earthx_permalink (expires_at);
