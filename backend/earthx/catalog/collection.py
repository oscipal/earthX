"""Mapping a registry entry onto a STAC Collection.

A mapping, not an interpretation: every ``earthx:`` field of architekturplan.md 5.1
appears, including the two that stay empty in M1 (``distributions``, and ``health``
where nothing has been measured). The shape is complete from the start so that M2
fills values in rather than adding fields.
"""

from __future__ import annotations

from datetime import date

from earthx.catalog.registry import DatasetConfig

STAC_VERSION = "1.0.0"


def _isoformat(value: date | None) -> str | None:
    """A date as STAC writes an instant: UTC, no local offset."""
    return None if value is None else f"{value.isoformat()}T00:00:00Z"


def _earthx_capabilities(config: DatasetConfig) -> dict[str, bool]:
    caps = config.capabilities
    return {
        "roi": caps.roi,
        "time_range": caps.time_range,
        "band_math": caps.band_math,
        "interpolation": caps.interpolation,
        "ml_processing": caps.ml_processing,
        "quad_pol": caps.quad_pol,
        "single_coverage_product": caps.single_coverage_product,
    }


def _earthx_license_flags(config: DatasetConfig) -> dict[str, object]:
    lic = config.license
    return {
        "spdx_id": lic.spdx_id,
        "name": lic.name,
        "url": lic.url,
        "commercial_use": lic.commercial_use,
        "derivatives": lic.derivatives,
        "share_alike": lic.share_alike,
        "attribution_required": lic.attribution_required,
        "tier": lic.tier.value,
        "attribution_modified": lic.attribution_modified,
        "attribution_unmodified": lic.attribution_unmodified,
        "liability_notice": lic.liability_notice,
    }


def _earthx_coverage(config: DatasetConfig) -> dict[str, object]:
    """Not one of the eight fields of 5.1 — added by adr/0004 §6, and read in M2."""
    cov = config.coverage
    return {
        "provider": cov.provider.value,
        "typical_footprint_km": cov.typical_footprint_km,
        "max_geotile_level": cov.max_geotile_level,
    }


def to_stac_collection(config: DatasetConfig) -> dict[str, object]:
    """Build the STAC Collection for a registry entry.

    Returns a plain dictionary, freshly built on every call: no caller can reach
    back into the frozen entry through a shared list.
    """
    return {
        "type": "Collection",
        "stac_version": STAC_VERSION,
        "id": config.dataset_id,
        "title": config.title,
        "description": config.description,
        "license": config.license.stac_license,
        "extent": {
            "spatial": {"bbox": [list(config.spatial_extent.bbox)]},
            "temporal": {
                "interval": [
                    [
                        _isoformat(config.temporal_extent.start),
                        _isoformat(config.temporal_extent.end),
                    ]
                ]
            },
        },
        # The licence link is the primary source of the texts above (adr/0003 §11.2).
        "links": [{"rel": "license", "href": config.license.url, "title": config.license.name}],
        "earthx:data_class": config.data_class.value,
        "earthx:capabilities": _earthx_capabilities(config),
        "earthx:license_flags": _earthx_license_flags(config),
        "earthx:access": {
            "token_free_checked_at": config.access.token_free_checked_at.isoformat(),
            "method": config.access.method,
            "cors": config.access.cors,
        },
        # Mirrors and alternative formats are harvested from M5 on (architekturplan.md 7).
        "earthx:distributions": [],
        "earthx:health": {
            "status": config.health.status.value,
            "last_checked_ok": (
                None if config.health.last_checked_ok is None else config.health.last_checked_ok.isoformat()
            ),
        },
        "earthx:default_render": {
            "bands": list(config.default_render.bands),
            "stretch": list(config.default_render.stretch),
            "colormap": config.default_render.colormap,
        },
        "earthx:source": {
            "adapter": config.source.adapter.value,
            "endpoint": config.source.endpoint,
            "source_collection_id": config.source.source_collection_id,
            "harvest_run": config.source.harvest_run,
        },
        "earthx:coverage": _earthx_coverage(config),
    }
