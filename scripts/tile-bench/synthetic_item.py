"""The Earth Search item of the synthetic scene, shared by ``run_tiler.py`` and ``job_bench.py`` (NM4-26, NM4-62).

Written by hand for the COGs of ``make_cogs.py``; no value comes from a real item.
"""

import hashlib

ASSET_HOST = "https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com"
FOOTPRINT = [10.3119, 46.8326, 11.8028, 47.8459]


def synthetic_item(item_id: str, version: str | None = None) -> dict:
    """An Earth Search item as the adapter reads it.

    ``version`` gives every asset a ``file:checksum`` made from it: a job then has a version without a ``HEAD`` at
    the source, and a new ``version`` is a new cache key.
    """
    grid = {"gsd": 10, "proj:shape": [10980, 10980], "proj:transform": [10, 0, 600000, 0, -10, 5300040]}
    cog_type = "image/tiff; application=geotiff; profile=cloud-optimized"
    reflectance = {"nodata": 0, "data_type": "uint16", "spatial_resolution": 10, "scale": 0.0001, "offset": -0.1}

    def band(name: str, common: str) -> dict:
        return {"name": name, "common_name": common}

    def checksum(asset: str) -> dict:
        if version is None:
            return {}
        return {"file:checksum": "1220" + hashlib.sha256(f"{version}/{item_id}/{asset}".encode()).hexdigest()}

    west, south, east, north = FOOTPRINT
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": item_id,
        "collection": "sentinel-2-c1-l2a",
        "bbox": FOOTPRINT,
        "geometry": {"type": "Polygon",
                     "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]},
        # One overpass for every scene, so that they make one mosaic (NM4-29): its key is day and MGRS tile, the
        # overpass is `s2:datatake_id`.
        "properties": {"datetime": "2026-08-01T10:20:39Z", "grid:code": "MGRS-32TPT",
                       "s2:datatake_id": "SYNTH_20260801T102039", "proj:code": "EPSG:32632", "eo:cloud_cover": 1.0},
        "links": [],
        "assets": {
            "red": {"href": f"{ASSET_HOST}/synth/{item_id}/B04.tif", "type": cog_type, "roles": ["data", "reflectance"],
                    "eo:bands": [band("B04", "red")], "raster:bands": [reflectance], **grid, **checksum("red")},
            "nir": {"href": f"{ASSET_HOST}/synth/{item_id}/B08.tif", "type": cog_type, "roles": ["data", "reflectance"],
                    "eo:bands": [band("B08", "nir")], "raster:bands": [reflectance], **grid, **checksum("nir")},
            "visual": {"href": f"{ASSET_HOST}/synth/{item_id}/TCI.tif", "type": cog_type, "roles": ["visual"],
                       "eo:bands": [band("B04", "red"), band("B03", "green"), band("B02", "blue")],
                       "raster:bands": [{"nodata": 0, "data_type": "uint8", "spatial_resolution": 10}] * 3, **grid,
                       **checksum("visual")},
            # The 20 m scene classification the `mask` step reads (NM4-62).
            "scl": {"href": f"{ASSET_HOST}/synth/{item_id}/SCL.tif", "type": cog_type, "roles": ["data"],
                    "raster:bands": [{"nodata": 0, "data_type": "uint8", "spatial_resolution": 20}], "gsd": 20,
                    "proj:shape": [5490, 5490], "proj:transform": [20, 0, 600000, 0, -20, 5300040], **checksum("scl")},
        },
    }
