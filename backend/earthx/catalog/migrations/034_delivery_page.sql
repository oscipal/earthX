-- A new way of delivery for listed entries: `page`, "through the provider's page" (M5-20 plan §13e, F12 = 2; Otto,
-- 20.11.2026). A harvested find whose resources at an https address are only pages or formats the format table does not
-- know ("SERVICE", "API", "onLine") gets it, rather than waiting without a known way to its data.
ALTER TABLE public.earthx_listed_entry
    DROP CONSTRAINT earthx_listed_entry_delivery_check,
    ADD CONSTRAINT earthx_listed_entry_delivery_check
        CHECK (delivery IN ('download', 'service', 'order', 'on_request', 'page'));
