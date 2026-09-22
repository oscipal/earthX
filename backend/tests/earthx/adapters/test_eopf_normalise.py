"""``normalize_item``: STAC 1.1 in, STAC 1.0 out (adr/0007 §6 point 4, §12.11
point 11; M2-09b plan §4.2).

Items are written out in place, the same way ``test_group_key.py`` does it: a
fixture would hide the very fields this module maps, unmaps or leaves alone.
"""

from __future__ import annotations

from earthx.adapters.eopf_stac import normalize_item


def item(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "type": "Feature",
        "id": "S2A_MSIL2A_TEST",
        "stac_version": "1.1.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/eo/v2.0.0/schema.json",
            "https://stac-extensions.github.io/projection/v2.0.0/schema.json",
            "https://stac-extensions.github.io/raster/v2.0.0/schema.json",
            "https://stac-extensions.github.io/zarr/v1.1.0/schema.json",
        ],
        "properties": {"datetime": "2026-09-21T14:18:21Z", "grid:code": "MGRS-26WME", "proj:code": "EPSG:32626"},
        "assets": {},
    }
    base.update(overrides)
    return base


def test_the_stac_version_becomes_1_0() -> None:
    assert normalize_item(item())["stac_version"] == "1.0.0"


def test_the_1_1_extension_versions_become_1_1_0() -> None:
    extensions = normalize_item(item())["stac_extensions"]
    assert "https://stac-extensions.github.io/eo/v1.1.0/schema.json" in extensions
    assert "https://stac-extensions.github.io/projection/v1.1.0/schema.json" in extensions
    assert "https://stac-extensions.github.io/raster/v1.1.0/schema.json" in extensions


def test_an_unmapped_extension_passes_through_unchanged() -> None:
    """The `zarr` extension has no 1.0 counterpart (adr/0007 §6 point 4) — left as is."""
    extensions = normalize_item(item())["stac_extensions"]
    assert "https://stac-extensions.github.io/zarr/v1.1.0/schema.json" in extensions


def test_proj_code_with_an_epsg_prefix_becomes_proj_epsg() -> None:
    properties = normalize_item(item())["properties"]
    assert "proj:code" not in properties
    assert properties["proj:epsg"] == 32626


def test_a_non_epsg_proj_code_is_left_alone() -> None:
    """Not abbildbar — stays as it is rather than being dropped or guessed at."""
    properties = normalize_item(item(properties={"proj:code": "IAU_2015:30100"}))["properties"]
    assert properties["proj:code"] == "IAU_2015:30100"
    assert "proj:epsg" not in properties


def test_proj_bbox_in_meters_under_a_utm_crs_is_kept() -> None:
    """The measured, correct case: adr/0007 §12.3, EPSG:32626, meters."""
    properties = normalize_item(
        item(properties={"proj:code": "EPSG:32626", "proj:bbox": [399960.0, 7890240.0, 509760.0, 8000040.0]})
    )["properties"]
    assert properties["proj:bbox"] == [399960.0, 7890240.0, 509760.0, 8000040.0]


def test_proj_bbox_in_degrees_under_a_utm_crs_is_dropped() -> None:
    """The broken case §3.4 measured in the older bestand: degrees under a UTM code."""
    properties = normalize_item(
        item(properties={"proj:code": "EPSG:32632", "proj:bbox": [8.6, 45.8, 9.9, 46.9]})
    )["properties"]
    assert "proj:bbox" not in properties


def test_proj_bbox_is_kept_when_the_crs_is_not_utm() -> None:
    """The plausibility check is scoped to UTM zones (EPSG:326xx/327xx); anything
    else is left to whoever reads `proj:bbox` next."""
    properties = normalize_item(
        item(properties={"proj:code": "EPSG:4326", "proj:bbox": [8.6, 45.8, 9.9, 46.9]})
    )["properties"]
    assert properties["proj:bbox"] == [8.6, 45.8, 9.9, 46.9]


def test_asset_bands_becomes_eo_bands_with_the_eo_prefix_stripped() -> None:
    asset = {
        "href": "https://data.eodc.eu/.../r10m",
        "bands": [
            {
                "name": "b04",
                "description": "Red (band 4)",
                "eo:common_name": "red",
                "eo:center_wavelength": 0.665,
                "eo:full_width_half_max": 0.038,
            }
        ],
    }
    normalized = normalize_item(item(assets={"SR_10m": asset}))["assets"]["SR_10m"]
    assert "bands" not in normalized
    assert normalized["eo:bands"] == [
        {"name": "b04", "description": "Red (band 4)", "common_name": "red", "center_wavelength": 0.665, "full_width_half_max": 0.038}
    ]


def test_asset_raster_fields_move_into_raster_bands() -> None:
    asset = {
        "href": "https://data.eodc.eu/.../r10m",
        "nodata": 0,
        "data_type": "uint16",
        "raster:spatial_resolution": 10,
    }
    normalized = normalize_item(item(assets={"SR_10m": asset}))["assets"]["SR_10m"]
    assert "nodata" not in normalized
    assert "data_type" not in normalized
    assert "raster:spatial_resolution" not in normalized
    assert normalized["raster:bands"] == [{"nodata": 0, "data_type": "uint16", "spatial_resolution": 10}]


def test_an_asset_without_raster_fields_gets_no_raster_bands_entry() -> None:
    asset = {"href": "https://data.eodc.eu/.../product", "description": "the product group"}
    normalized = normalize_item(item(assets={"product": asset}))["assets"]["product"]
    assert "raster:bands" not in normalized


def test_an_asset_field_with_no_1_0_mapping_passes_through() -> None:
    asset = {"href": "https://data.eodc.eu/.../r10m", "zarr:node_type": "group"}
    normalized = normalize_item(item(assets={"SR_10m": asset}))["assets"]["SR_10m"]
    assert normalized["zarr:node_type"] == "group"


def test_the_input_is_not_mutated() -> None:
    """Same rule as the collection mapping (test_collection.py): a caller must not
    reach back into its own item through what this function handed out."""
    original = item(properties={"proj:code": "EPSG:32626"}, assets={"SR_10m": {"bands": [{"name": "b04"}]}})
    normalize_item(original)
    assert original["properties"] == {"proj:code": "EPSG:32626"}
    assert original["assets"]["SR_10m"] == {"bands": [{"name": "b04"}]}
