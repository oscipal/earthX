-- One pointer, one breaker and the places per host for materialize, the harvester and the pyramid build, across all
-- instances (M5-37; docs/plans/m5/m5-37-zeiger-je-host.md §3, the pattern of `earthx_rate_slots` in 005).
--
-- `earthx_source_host`: `next_start` is the earliest start of the next request to the host; every caller moves it on by
-- its own interval and waits for its turn without holding a connection. `failures` counts failed attempts in a row over
-- all callers; at the threshold the breaker pauses the host by moving `next_start` forward (J3). `pauses` counts pauses
-- in a row for the doubling, `paused_at` and `paused_until` say when the current one began and ends. No row is seeded:
-- the first reservation of a host writes it. The row names a host, never a dataset, an address or an AOI.
--
-- `earthx_source_lease`: one row per request in flight, numbered 1 up to the host's cap, so there are never more live
-- places than the cap. A place lasts `until`; its holder renews it with a heartbeat, and a place past `until` counts no
-- more and is taken over by the next caller (an instance that died gives its places back by itself).
CREATE TABLE public.earthx_source_host (
    host          text        PRIMARY KEY,
    next_start    timestamptz NOT NULL,
    failures      integer     NOT NULL DEFAULT 0 CHECK (failures >= 0),
    pauses        integer     NOT NULL DEFAULT 0 CHECK (pauses >= 0),
    paused_at     timestamptz,
    paused_until  timestamptz,
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.earthx_source_lease (
    host    text        NOT NULL,
    slot    integer     NOT NULL CHECK (slot >= 1),
    holder  uuid        NOT NULL,
    until   timestamptz NOT NULL,
    PRIMARY KEY (host, slot)
);
