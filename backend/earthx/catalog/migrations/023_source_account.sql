-- The requests of one file read, charged to the host's shared turn (M5-37 PR 2; docs/plans/m5/m5-37-zeiger-je-host.md
-- §5.4). The pyramid build takes one turn before it opens a file, as `earthx_source_reserve` (022) hands out; GDAL then
-- makes as many requests as the file needs. They are charged afterwards, as the build's own pacer did per process
-- (`gateway.HostPacer.account`): the next turn moves on by (requests - 1) intervals from where it stands, so the time the
-- read took counts towards the spacing. A read that made no request (GDAL's cache) gives nothing back: a turn handed
-- out to another caller in the meantime must not move earlier. A change of a rule of 022 or of this one comes as a new
-- migration (Otto, 16.11.2026).
CREATE OR REPLACE FUNCTION public.earthx_source_account(p_host text, p_interval float8, p_requests integer)
RETURNS void LANGUAGE sql AS $$
    UPDATE public.earthx_source_host
    SET next_start = next_start + make_interval(secs => p_interval * (p_requests - 1)), updated_at = clock_timestamp()
    WHERE host = p_host AND p_requests > 1
$$;
