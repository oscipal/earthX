"""Mapping a registry entry onto a STAC Collection.

A mapping, not an interpretation: every ``earthx:`` field of architekturplan.md 5.1
appears, including ``distributions``, which stays empty until the harvester fills it
from M5. The shape is complete from the start so that M2 fills values in rather than
adding fields.

The coverage fields of adr/0004 §6 are deliberately *not* here. They belong to the
registry entry, which is what decides the coverage path (adr/0004 §5); putting them
in the collection as well would add another ``earthx:`` field to 5.1 — a change to
the architecture, not a consequence of this task.
"""

from __future__ import annotations

from datetime import datetime, timezone

from earthx.catalog.registry import DatasetConfig, LicenseInfo

# STAC 1.0 for now, because that is what pgstac and Earth Search speak. The licence
# value below is tied to it: STAC 1.1 dropped "proprietary" in favour of "other",
# so the two must move together. Which version we serve follows from the
# stac-fastapi-pgstac release M1-07 pins — see _stac_license.
STAC_VERSION = "1.0.0"

# DOI and citation are not an earthx: field but the scientific extension, which
# architekturplan.md 5.1 lists among the extensions we use.
SCIENTIFIC_EXTENSION = "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"


def _stac_license(license_info: LicenseInfo, stac_version: str = STAC_VERSION) -> str:
    """The licence value in the spelling the given STAC version uses.

    An SPDX identifier is written as it stands in both versions. Without one, STAC
    1.0 says ``proprietary`` and STAC 1.1 says ``other``; emitting 1.0's word under
    1.1 is what a reader would silently correct, and then our stored value and the
    served one disagree.
    """
    if license_info.spdx_id:
        return license_info.spdx_id
    return "proprietary" if stac_version.startswith("1.0") else "other"


def _isoformat(value: datetime | None) -> str | None:
    """An instant as STAC writes it: UTC, with a trailing Z rather than +00:00."""
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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
        "distribution": lic.distribution,
        "derivatives": lic.derivatives,
        "share_alike": lic.share_alike,
        "attribution_required": lic.attribution_required,
        "tier": lic.tier.value,
        "attribution_modified": lic.attribution_modified,
        "attribution_unmodified": lic.attribution_unmodified,
        "terms_url": None if lic.terms is None else lic.terms.url,
        "terms_notice": None if lic.terms is None else dict(lic.terms.notice),
    }


def _scientific(config: DatasetConfig) -> dict[str, object]:
    """DOI and citation, left out entirely where the dataset has neither."""
    fields: dict[str, object] = {}
    if config.doi:
        fields["sci:doi"] = config.doi
    if config.citation:
        fields["sci:citation"] = config.citation
    return fields


def to_stac_collection(config: DatasetConfig) -> dict[str, object]:
    """Build the STAC Collection for a registry entry.

    Returns a plain dictionary, freshly built on every call: no caller can reach
    back into the frozen entry through a shared list.
    """
    scientific = _scientific(config)
    collection: dict[str, object] = {
        "type": "Collection",
        "stac_version": STAC_VERSION,
        "stac_extensions": [SCIENTIFIC_EXTENSION] if scientific else [],
        "id": config.dataset_id,
        "title": config.title,
        "description": config.description,
        "license": _stac_license(config.license),
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
        # architekturplan.md 6.2's reader dispatch (`cog`, `zarr`, `legacy`) —
        # published so the frontend can tell a whole scene it may link straight
        # to the source (a COG) from one it may not (a Zarr store has no single
        # file to link, M3-17) without a dataset-specific branch anywhere.
        "earthx:format": config.format.value,
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
        },
        # The field names of the STAC `render` extension (adr/0006 §5): what stands
        # here is what a tile URL carries, so it can be published as `renders` later
        # without a translation.
        "earthx:default_render": (
            None
            if config.default_render is None
            else {
                "title": config.default_render.title,
                "assets": list(config.default_render.assets),
                "rescale": (
                    None
                    if config.default_render.rescale is None
                    else [list(pair) for pair in config.default_render.rescale]
                ),
                "colormap_name": config.default_render.colormap_name,
                "expression": config.default_render.expression,
                "resampling": config.default_render.resampling,
            }
        ),
        # architekturplan.md 5.1, ninth row: what the viewer decides from the
        # catalogue. `group_by` names item properties in key order; a property
        # holding an instant enters the key as its UTC date (registry.ViewerInfo).
        # `min_zoom`/`max_zoom` are the tile levels this dataset is released for
        # (M2-10) — read by the viewer and enforced by the tile route, so a client
        # that ignores them gets a 400 rather than an expensive read. `browse`,
        # `quicklook_nodata_max` and `results_group_by` are M3-12's addition
        # (registry.ViewerInfo, registry.BrowseMode): what the browse view shows
        # right after a search, its quicklook freistellung threshold if any, and
        # the key the results list and the download route group by (P19) —
        # separate from `group_by` because a dataset may head its results
        # display by a property `group_by` deliberately does not use (M3-02 F-01).
        "earthx:viewer": (
            None
            if config.viewer is None
            else {
                "group_by": list(config.viewer.group_by),
                "min_zoom": config.viewer.min_zoom,
                "max_zoom": config.viewer.max_zoom,
                "browse": config.viewer.browse.value,
                "quicklook_nodata_max": config.viewer.quicklook_nodata_max,
                "results_group_by": list(config.viewer.results_group_by),
            }
        ),
        "earthx:source": {
            "adapter": config.source.adapter.value,
            "endpoint": config.source.endpoint,
            "source_collection_id": config.source.source_collection_id,
            "asset_hosts": list(config.source.asset_hosts),
            "harvest_run": config.source.harvest_run,
            # M3-11a (K-05): federated or materialized — what `FederatingCoreCrudClient`
            # branches search and item-fetch on, read back off this very document
            # (`api/federating_client.py::_holding_of`).
            "item_holding": config.source.item_holding.value,
        },
        # architekturplan.md 5.1, tenth row (adr/0007 §12.11 point 14): how settled
        # the source itself is, not a measurement like earthx:health. No default on
        # the entry (KLAERUNGEN B10), so this is always one of the three values.
        "earthx:maturity": config.maturity.value,
    }
    collection.update(scientific)
    return collection
