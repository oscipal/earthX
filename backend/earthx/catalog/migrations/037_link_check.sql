-- The automatic check of the link of every harvested listed entry (M5-67; docs/plans/m5/m5-67-harvest-automatisch.md
-- §4, §4a, §4c; adr/0033 §8.5, Otto 24.11.2026).
--
-- An entry becomes visible only once its own link passed the check: `publish` requires a row here with the entry's
-- current link, `passed` and not `guarded`. A published entry whose link failed becomes `link_failed`: hidden like
-- every state but `published`, never deleted, its content and approval kept; a later pass with the same link brings it
-- back. `unchecked` (robots.txt, no answer, 429, 5xx, too large) changes nothing.
--
-- One row per entry, the latest check. A result holds only for the link it was made with (`url`); a changed link makes
-- the entry unchecked again. `guarded`: the host or the pattern of the link failed for a large share in that run
-- (plan §4c), so the result neither hides nor publishes.
ALTER TABLE public.earthx_listed_entry
    DROP CONSTRAINT earthx_listed_entry_state_check,
    ADD CONSTRAINT earthx_listed_entry_state_check CHECK (state IN (
        'published', 'in_review', 'needs_rule', 'blocked', 'tombstone', 'superseded', 'not_geodata', 'duplicate',
        'link_failed'));

CREATE TABLE public.earthx_link_check (
    dataset_id   text        COLLATE "C" PRIMARY KEY
                             REFERENCES public.earthx_listed_entry (dataset_id) ON DELETE CASCADE,
    url          text        NOT NULL CHECK (url ~ '^https?://'),
    host         text        NOT NULL,
    pattern      text        NOT NULL,
    outcome      text        NOT NULL CHECK (outcome IN ('passed', 'failed', 'unchecked')),
    -- `ok`, or why not: `http_<code>`, `start_page`, `error_page`, `login_page`, `no_title`, `robots`, `unreachable`,
    -- `too_large`, `bad_address`, `redirect_host` and the like; codes, never page text.
    reason       text        NOT NULL CHECK (reason ~ '^[a-z0-9_]{2,40}$'),
    status       integer     CHECK (status BETWEEN 100 AND 599),
    final_host   text,
    guarded      boolean     NOT NULL DEFAULT false,
    checked_at   timestamptz NOT NULL,
    CHECK ((outcome = 'passed') = (reason = 'ok'))
);

-- The rotation (plan §4a) takes the oldest checks first.
CREATE INDEX earthx_link_check_checked_idx ON public.earthx_link_check (checked_at);
