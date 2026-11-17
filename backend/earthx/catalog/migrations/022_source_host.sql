-- One pointer, one breaker and the places per host for materialize, the harvester and the pyramid build, across all
-- instances (M5-37; docs/plans/m5/m5-37-zeiger-je-host.md §3, the pattern of `earthx_rate_slots` in 005).
--
-- `earthx_source_host`: `next_start` is the earliest start of the next request to the host; every caller moves it on by
-- its own interval and waits for its turn without holding a connection. `failures` counts failed attempts in a row over
-- all callers; at the threshold the breaker pauses the host by moving `next_start` forward (J3). `pauses` counts pauses
-- in a row for the doubling, `paused_at` and `paused_until` say when the current one began and ends. No row is seeded:
-- the first call for a host writes it. The row names a host, never a dataset, an address or an AOI.
--
-- `earthx_source_lease`: one row per request in flight, numbered 1 up to the host's cap, so there are never more live
-- places than the cap. A place lasts `until`; its holder renews it with a heartbeat, and a place past `until` counts no
-- more and is taken over by the next caller (an instance that died gives its places back by itself).
--
-- The rules live in the functions below, once for every caller: `catalog` and `jobs` may not import a common module
-- (plan §5.2), so they call these instead of carrying the SQL twice. Each function reads the clock once, after it holds
-- the row, and runs as one statement: the row lock ends with it.
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

-- The host's next turn, moved on by `p_interval`; returns the seconds until it. A turn further off than `p_max_wait` is
-- not taken, so a caller that will not wait for it does not lengthen a pause or a queue.
CREATE OR REPLACE FUNCTION public.earthx_source_reserve(p_host text, p_interval float8, p_max_wait float8)
RETURNS float8 LANGUAGE plpgsql AS $$
DECLARE
    taken   timestamptz;
    now_ts  timestamptz;
    turn    timestamptz;
BEGIN
    INSERT INTO public.earthx_source_host (host, next_start) VALUES (p_host, clock_timestamp())
    ON CONFLICT (host) DO NOTHING;
    SELECT next_start INTO taken FROM public.earthx_source_host WHERE host = p_host FOR UPDATE;
    now_ts := clock_timestamp();
    turn := greatest(taken, now_ts);
    IF turn <= now_ts + make_interval(secs => p_max_wait) THEN
        UPDATE public.earthx_source_host
        SET next_start = turn + make_interval(secs => p_interval), updated_at = now_ts
        WHERE host = p_host;
    END IF;
    RETURN extract(epoch FROM turn - now_ts);
END
$$;

-- Seconds left of the host's pause, 0 if none: asked by a caller that slept until its turn, before it sends.
CREATE OR REPLACE FUNCTION public.earthx_source_pause_left(p_host text)
RETURNS float8 LANGUAGE sql STABLE AS $$
    SELECT coalesce(
        (SELECT greatest(extract(epoch FROM paused_until - clock_timestamp()), 0)
         FROM public.earthx_source_host WHERE host = p_host),
        0)::float8
$$;

-- How one attempt ended. A success resets the breaker (`recovered` if the host had been paused). A failure counts; at
-- `p_threshold` in a row it pauses the host for `p_pause`, twice as long for each pause right after the one before, at
-- most `p_max_pause` (`opened`, `pause_s`). No new pause while one runs: attempts already under way fail too. "Right
-- after" means within the length of the last pause after its end; later, count and doubling start again. A `Retry-After`
-- moves the turn on by `p_retry_after` seconds, threshold or not.
CREATE OR REPLACE FUNCTION public.earthx_source_report(
    p_host text, p_failed boolean, p_retry_after float8, p_threshold integer, p_pause float8, p_max_pause float8
)
RETURNS TABLE (opened boolean, recovered boolean, pause_s float8) LANGUAGE plpgsql AS $$
DECLARE
    r       public.earthx_source_host%ROWTYPE;
    now_ts  timestamptz;
    pause_len  float8;
BEGIN
    IF NOT p_failed THEN
        IF NOT EXISTS (
            SELECT 1 FROM public.earthx_source_host h
            WHERE h.host = p_host AND (h.failures > 0 OR h.pauses > 0 OR h.paused_until IS NOT NULL)
        ) THEN
            RETURN QUERY SELECT false, false, 0::float8;
            RETURN;
        END IF;
        SELECT * INTO r FROM public.earthx_source_host h WHERE h.host = p_host FOR UPDATE;
        UPDATE public.earthx_source_host h
        SET failures = 0, pauses = 0, paused_at = NULL, paused_until = NULL, updated_at = clock_timestamp()
        WHERE h.host = p_host;
        RETURN QUERY SELECT false, r.pauses > 0, 0::float8;
        RETURN;
    END IF;

    INSERT INTO public.earthx_source_host (host, next_start) VALUES (p_host, clock_timestamp())
    ON CONFLICT (host) DO NOTHING;
    SELECT * INTO r FROM public.earthx_source_host h WHERE h.host = p_host FOR UPDATE;
    now_ts := clock_timestamp();
    IF r.pauses > 0 AND r.paused_until IS NOT NULL
       AND r.paused_until + make_interval(secs => least(p_pause * 2 ^ least(r.pauses - 1, 20), p_max_pause)) <= now_ts THEN
        r.failures := 0;
        r.pauses := 0;
    END IF;
    r.failures := r.failures + 1;
    opened := r.failures >= p_threshold AND (r.paused_until IS NULL OR r.paused_until <= now_ts);
    pause_len := 0;
    IF opened THEN
        pause_len := least(p_pause * 2 ^ least(r.pauses, 20), p_max_pause);
        r.pauses := r.pauses + 1;
        r.paused_at := now_ts;
        r.paused_until := now_ts + make_interval(secs => pause_len);
    END IF;
    UPDATE public.earthx_source_host h
    SET failures = r.failures, pauses = r.pauses, paused_at = r.paused_at, paused_until = r.paused_until,
        next_start = greatest(
            r.next_start,
            now_ts + make_interval(secs => p_retry_after),
            CASE WHEN opened THEN r.paused_until END
        ),
        updated_at = now_ts
    WHERE h.host = p_host;
    RETURN QUERY SELECT opened, false, pause_len;
END
$$;

-- The lowest of the host's `p_cap` places that is free or past its term, for `p_term` seconds; NULL when all are held.
-- In rising order, so two callers never wait on each other in a circle; a caller that loses a number to another tries
-- the next one at once.
CREATE OR REPLACE FUNCTION public.earthx_source_acquire(p_host text, p_cap integer, p_holder uuid, p_term float8)
RETURNS integer LANGUAGE plpgsql AS $$
DECLARE
    got integer;
BEGIN
    FOR s IN 1..p_cap LOOP
        INSERT INTO public.earthx_source_lease AS l (host, slot, holder, until)
        VALUES (p_host, s, p_holder, clock_timestamp() + make_interval(secs => p_term))
        ON CONFLICT (host, slot) DO UPDATE
            SET holder = EXCLUDED.holder, until = EXCLUDED.until
            WHERE l.until <= clock_timestamp()
        RETURNING l.slot INTO got;
        IF got IS NOT NULL THEN
            RETURN got;
        END IF;
    END LOOP;
    RETURN NULL;
END
$$;

-- The holder's heartbeat: true while the place is still its own.
CREATE OR REPLACE FUNCTION public.earthx_source_renew(p_host text, p_slot integer, p_holder uuid, p_term float8)
RETURNS boolean LANGUAGE sql AS $$
    WITH renewed AS (
        UPDATE public.earthx_source_lease SET until = clock_timestamp() + make_interval(secs => p_term)
        WHERE host = p_host AND slot = p_slot AND holder = p_holder
        RETURNING 1
    )
    SELECT EXISTS (SELECT 1 FROM renewed)
$$;

-- Give a place back; one that was taken over by another holder stays the other's.
CREATE OR REPLACE FUNCTION public.earthx_source_release(p_host text, p_slot integer, p_holder uuid)
RETURNS void LANGUAGE sql AS $$
    DELETE FROM public.earthx_source_lease WHERE host = p_host AND slot = p_slot AND holder = p_holder
$$;
