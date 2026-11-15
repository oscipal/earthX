-- The base tiles a pyramid was built without, and why (M5-30b, adr/0032 Nachtrag 15.11.2026, plan §8.11).
--
-- One file that stays unreadable after the reads were repeated omits only the base tile that needs it; the pyramid ends
-- `ready` with a gap, and the hourly round of the worker reads the omitted tiles again (and the tiles above them). A row per
-- omitted tile of a pyramid: `tile` is `x/y` at the base level (the world grid, no AOI), `kind` the name of the failure
-- (`source_5xx`, `unreadable`, ...), `error` the class of the exception and `reason` a short text with no URL, path or item
-- id (at most 160 characters), `attempts` the number of reads of the tile so far and `tried_at` the time of the last. A
-- row leaves when the tile reads; the rows of a pyramid that is no longer ready mean nothing and the worker deletes them.
-- No foreign key, as for the other tables of the pyramids. Written by `jobs` with SQL only.
CREATE TABLE public.earthx_overview_omitted (
    dataset_id text        NOT NULL,
    version    text        NOT NULL CHECK (version ~ '^[0-9a-f]{16}$'),
    tile       text        NOT NULL CHECK (tile ~ '^[0-9]{1,8}/[0-9]{1,8}$'),
    kind       text        NOT NULL CHECK (kind ~ '^[a-z][a-z0-9_]{0,39}$'),
    error      text        NOT NULL CHECK (char_length(error) BETWEEN 1 AND 80),
    reason     text        NOT NULL DEFAULT '' CHECK (char_length(reason) <= 160),
    omitted_at timestamptz NOT NULL DEFAULT now(),
    attempts   integer     NOT NULL DEFAULT 1 CHECK (attempts >= 1),
    tried_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_id, version, tile)
);

-- The retry of the omitted tiles takes turns like the extension and the sweep (019): one worker at a time, and a round
-- done by one worker counts for all (`next_at`). The row is made here, free from now on; a turn updates it.
ALTER TABLE public.earthx_overview_upkeep DROP CONSTRAINT earthx_overview_upkeep_task_check;
ALTER TABLE public.earthx_overview_upkeep
    ADD CONSTRAINT earthx_overview_upkeep_task_check CHECK (task IN ('extend', 'sweep', 'retry'));
INSERT INTO public.earthx_overview_upkeep (task, next_at) VALUES ('retry', now()) ON CONFLICT (task) DO NOTHING;

-- Who reads from a host of the sources, among all workers (M5-30b, adr/0032 Nachtrag 15.11.2026). A build and the retry of
-- the omitted tiles must not read from the same host at once (the host's rate limit is for one reader). A build already
-- holds its hosts through its own row in `earthx_overview` (`hosts`, `lease_until`); the retry takes a row here, one per host
-- it reads from, for as long as it reads. `claim` leaves a host that has a live row here alone, and `take_hosts` leaves a
-- host a live build has alone; both decide under the same advisory lock (`jobs.overviews.OVERVIEW_LOCK_KEY`), so the
-- two cannot both pass. The row is a lease like the one of a turn (019): `worker`, `lease_until`, renewed while the retry
-- goes on; `turn` counts the takes, so a worker that woke up late cannot renew or release a newer one. A lease that ran out
-- is taken over. Written by `jobs` with SQL only.
CREATE TABLE public.earthx_overview_host (
    host        text   PRIMARY KEY CHECK (char_length(host) BETWEEN 1 AND 253),
    turn        bigint NOT NULL DEFAULT 1 CHECK (turn >= 1),
    worker      text,
    lease_until timestamptz,
    CONSTRAINT earthx_overview_host_lease CHECK ((worker IS NULL) = (lease_until IS NULL))
);
