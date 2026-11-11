-- The selection behind a mosaic tile URL (M5-30b part 3, docs/adr/0032-bild-bei-jedem-zoom.md §10.2, option U1).
--
-- A mosaic URL names a selection of scenes by an id that is the hash of its content (dataset, assets, item ids;
-- earthx/catalog/mosaic_selection.py). The same content has the same id, and one id never means another picture,
-- which is what keeps the URL the whole description of the image (adr/0006 §5). `content` holds that content and,
-- with it, what the tiles need so as not to fetch every item again: the order the scenes are read in, the outline
-- of each scene and the extent.
--
-- The term is seven days. Creating a selection that exists moves `expires_at` to seven days from now; an expired row
-- is gone for the tiler (it answers 410 and the map creates the selection again) and is deleted by the hourly
-- cleanup of `jobs`. No AOI is stored: a selection names scenes, not an area.
--
-- public. on purpose, for the same reason as 002: an unqualified CREATE would land inside the pgstac schema.
CREATE TABLE public.earthx_mosaic_selection (
    selection_id text        PRIMARY KEY,
    dataset_id   text        NOT NULL,
    content      jsonb       NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz NOT NULL
);

CREATE INDEX earthx_mosaic_selection_expires_at_idx ON public.earthx_mosaic_selection (expires_at);
