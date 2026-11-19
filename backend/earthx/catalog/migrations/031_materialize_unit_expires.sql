-- When the source deletes what a unit comes from (M5-58 PR 2, plan §11.3): the `expires` of its source item, which the
-- assets built from the unit carry. Kept with the unit, because a unit that holds an asset again after another one went
-- is built anew from its stored state alone, without the listing it came from (adr/0038 §3.4 point 4).
-- Information only; nothing is decided by it. NULL where the source names none.

ALTER TABLE public.earthx_materialize_unit ADD COLUMN expires text;
