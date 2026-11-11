"""What the swissALTI3D entry promises beyond its start checks (M5-08 plan §4.5, F2, §13).

* F2: the COG of 2 m is offered like a band beside the one of 0.5 m; the XYZ files in a ZIP are originals, never a band.
* ``viewer.min_zoom``: no tile at that level meets more files than a mosaic tile reads (its budget, adr/0032 §6.2).
"""

from __future__ import annotations

import random

from pyproj import Transformer
from rio_tiler.constants import WEB_MERCATOR_TMS
from shapely.geometry import Polygon, box

from earthx.access.band_export import band_table
from earthx.adapters.stac_api import dialect_of, normalize_for
from earthx.api.intake import band_sources
from earthx.api.mosaic_tiles import TILE_FILE_BUDGET
from tests.catalog.entries import SWISSALTI3D
from tests.catalog.synthetic_chain import fsdi_feature

TILE_M = 1000


def _item() -> dict:
    return normalize_for(dialect_of(SWISSALTI3D), SWISSALTI3D, fsdi_feature(SWISSALTI3D))


def test_both_cogs_are_bands_and_the_zips_are_not() -> None:
    assert [key for key, _ in band_sources(_item(), SWISSALTI3D)] == ["dtm", "dtm_2m"]


def test_the_download_dialog_offers_both_cogs_in_metres() -> None:
    table = band_table(
        [_item()], auxiliary=SWISSALTI3D.auxiliary_assets, mask_asset=None, unit_of=SWISSALTI3D.band_unit
    )
    assert [(meta.name, meta.unit) for meta, _ in table] == [("dtm", "m"), ("dtm_2m", "m")]
    # An elevation model has no spectral band to prefer: every band starts ticked.
    assert all(ticked for _, ticked in table)


def _tiles_met(zoom: int, lon: float, lat: float, to_lv95: Transformer, to_wgs84: Transformer) -> int:
    bounds = WEB_MERCATOR_TMS.bounds(WEB_MERCATOR_TMS.tile(lon, lat, zoom))
    area = box(bounds.left, bounds.bottom, bounds.right, bounds.top)
    xs, ys = to_lv95.transform(
        [bounds.left, bounds.right, bounds.left, bounds.right], [bounds.bottom, bounds.bottom, bounds.top, bounds.top]
    )
    met = 0
    for east in range(int(min(xs)) // TILE_M * TILE_M - TILE_M, int(max(xs)) + 2 * TILE_M, TILE_M):
        for north in range(int(min(ys)) // TILE_M * TILE_M - TILE_M, int(max(ys)) + 2 * TILE_M, TILE_M):
            corners = [(east, north), (east + TILE_M, north), (east + TILE_M, north + TILE_M), (east, north + TILE_M)]
            if Polygon([to_wgs84.transform(x, y) for x, y in corners]).intersects(area):
                met += 1
    return met


def test_no_tile_at_min_zoom_meets_more_scenes_than_a_mosaic_reads() -> None:
    """At ``min_zoom`` every mosaic tile reads all its files within the budget (M5-08 plan §13, adr/0032 §9)."""
    to_lv95 = Transformer.from_crs("EPSG:4326", "EPSG:2056", always_xy=True)
    to_wgs84 = Transformer.from_crs("EPSG:2056", "EPSG:4326", always_xy=True)
    west, south, east, north = SWISSALTI3D.spatial_extent.bbox
    places = random.Random(20261109)
    samples = [(places.uniform(west, east), places.uniform(south, north)) for _ in range(60)]
    zoom = SWISSALTI3D.viewer.min_zoom
    assert max(_tiles_met(zoom, lon, lat, to_lv95, to_wgs84) for lon, lat in samples) <= TILE_FILE_BUDGET
    # One level lower would not hold: min_zoom is the lowest level that does.
    assert max(_tiles_met(zoom - 1, lon, lat, to_lv95, to_wgs84) for lon, lat in samples) > TILE_FILE_BUDGET
