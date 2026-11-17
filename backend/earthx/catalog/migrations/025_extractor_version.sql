-- The version of the extractor that derived a find's state (M5-19, Otto 17.11.2026, plan §12.2).
--
-- A find whose raw answer is unchanged is evaluated anew when the extractor or the extraction rules of its source
-- changed since: else a find once invalid would stay invalid for good, also behind a `304` of the whole listing.
-- `discovery` writes a fingerprint of the extractor's code, its tables and the source's link settings; NULL is a state
-- from before this column and counts as outdated.
ALTER TABLE public.earthx_record_state ADD COLUMN extractor_version text;
