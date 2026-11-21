-- The municipalities of Switzerland for the place texts of harvested finds (M5-20 plan §13b, F9 = 1).
--
-- Written by `catalog-load` from `backend/catalog/municipalities.json` (swissBOUNDARIES3D, © swisstopo), read by the
-- report of the harvest: the footprint of a find whose place text names a municipality is its outline. A
-- municipality is no region (`earthx_region`): an entry it names carries the regions of its canton and state.
CREATE TABLE public.earthx_municipality (
    code    text                            PRIMARY KEY CHECK (code ~ '^[A-Z]{2}-[A-Z]{2}-[0-9]{4}$'),
    canton  text                            NOT NULL REFERENCES public.earthx_region (code),
    name    text                            NOT NULL,
    outline geometry(MultiPolygon, 4326)    NOT NULL,
    CHECK (code LIKE canton || '-%')
);

CREATE INDEX earthx_municipality_outline_idx ON public.earthx_municipality USING gist (outline);
