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
from typing import Any

from earthx.catalog.registry import UNSCALED, DatasetConfig, FilterKind, LicenseInfo, class_key, doi_name

# STAC 1.0 for now, because that is what pgstac and Earth Search speak. The licence
# value below is tied to it: STAC 1.1 dropped "proprietary" in favour of "other",
# so the two must move together. Which version we serve follows from the
# stac-fastapi-pgstac release M1-07 pins — see _stac_license.
STAC_VERSION = "1.0.0"

# DOI and citation are not an earthx: field but the scientific extension, which
# architekturplan.md 5.1 lists among the extensions we use.
SCIENTIFIC_EXTENSION = "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"
#: The classes of a band (M5-62, plan §3.3): ``value``, a machine ``name``, the ``title`` people read, ``color_hint``.
CLASSIFICATION_EXTENSION = "https://stac-extensions.github.io/classification/v2.0.0/schema.json"


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
        "reprojection": caps.reprojection,
        "masking": caps.masking,
        "value_masking": caps.value_masking,
        "normalization": caps.normalization,
        "ml_processing": caps.ml_processing,
        "quad_pol": caps.quad_pol,
        "terrain": caps.terrain,
        "single_coverage_product": caps.single_coverage_product,
    }


def _earthx_mask(config: DatasetConfig) -> dict[str, object] | None:
    """The layer ``mask`` reads, for the panel's list of classes; ``None`` where there is none (M4-18).

    ``cloud_classes`` (ascending) and ``cloud_note`` tell the panel what counts as cloud in the AOI (DS-03 plan §6.10).
    """
    mask = config.mask
    if mask is None:
        return None
    return {
        "asset": mask.asset,
        "band": mask.band,
        "classes": [{"value": entry.value, "label": entry.label} for entry in mask.classes],
        "suggested": sorted(mask.suggested),
        "reference": mask.reference,
        "note": mask.note,
        "cloud_classes": sorted(mask.cloud_classes),
        "cloud_note": mask.cloud_note,
        # DS-03c: the classes of the other shares measured in the AOI, by the property the search sends the range under.
        "share_classes": {entry.measure.value: sorted(entry.classes) for entry in mask.share_classes},
    }


def _earthx_band_units(config: DatasetConfig) -> dict[str, str | None]:
    """The unit of each asset the entry names, ``None`` where it says the unit is unknown (M4-19b)."""
    return dict(config.band_units)


def _earthx_bands(config: DatasetConfig) -> list[dict[str, Any]]:
    """The bands as STAC names them, ``name`` and ``description``, in the order of the entry (M5-59), and a band of
    classes with its classes as the classification extension writes them (M5-62). Every other band with the look it starts
    with and where that came from (M5-60): the form of ``x-earthx-looks`` (adr/0035), its numbers in the unit of the band;
a scaled band its ``band_scaling`` as ``earthx:scaling``, for a picture drawn without an item (M5-68).

    A list, because the collection travels through JSONB, which does not keep the order of the keys of an object, and
    the Data catalogue shows the bands in the order the entry lists them.
    """
    bands: list[dict[str, Any]] = []
    for key, text in config.band_descriptions.items():
        band: dict[str, Any] = {"name": key, "description": text}
        if (rows := config.class_rows(key)) is not None:
            band["classification:classes"] = [
                {"value": row.value, "name": class_key(row.name), "title": row.name, "color_hint": row.colour[1:].upper()}
                for row in rows
            ]
        if (look := config.look_of(key)) is not None:
            band["earthx:look"] = look.look.annotation()
            band["earthx:look_origin"] = look.origin.value
        if (scaling := config.scaling_of(key)) != UNSCALED:
            band["earthx:scaling"] = {"scale": scaling.scale, "offset": scaling.offset}
        bands.append(band)
    return bands


def _earthx_auxiliary_assets(config: DatasetConfig) -> list[str]:
    """The assets of the dataset that are no band of its data, so the panel leaves them out of "Select all"."""
    return list(config.auxiliary_assets)


def _earthx_index_presets(config: DatasetConfig) -> list[dict[str, object]]:
    """The indices the panel offers as one click each (NM4-14), ``rescale`` as the render extension writes it."""
    return [
        {
            "name": preset.name,
            "title": preset.title,
            "expression": preset.expression,
            "rescale": [list(preset.rescale)],
            "colormap_name": preset.colormap_name,
            "formula": preset.formula,
            "reference": preset.reference,
        }
        for preset in config.index_presets
    ]


def _earthx_composite_presets(config: DatasetConfig) -> list[dict[str, object]]:
    """The pictures of three expressions "Quick processing" offers (adr/0030 F7), red, green, blue in this order."""
    return [
        {
            "name": preset.name,
            "title": preset.title,
            "expressions": list(preset.channels),
            "rescale": [list(pair) for pair in preset.rescale],
            "reference": preset.reference,
        }
        for preset in config.composite_presets
    ]


def _earthx_step_presets(config: DatasetConfig) -> list[dict[str, object]]:
    """The steps "Quick processing" offers (adr/0030 F7), each with the parameters of the step as a recipe names them."""
    return [
        {
            "name": preset.name,
            "title": preset.title,
            "op": preset.op,
            "op_version": preset.op_version,
            "params": {**preset.params, "name": preset.name},
            "adjustable": list(preset.adjustable),
        }
        for preset in config.step_presets
    ]


def _earthx_true_color(config: DatasetConfig) -> list[str]:
    """The three bands of a true-colour picture (red, green, blue), or an empty list where the data has none (NM4-64)."""
    return list(config.true_color)


def _earthx_search_filters(config: DatasetConfig) -> list[dict[str, object]]:
    """The filters the search offers, in the words of STAC queryables (JSON Schema) where they have one (DS-02).

    ``kind``, ``unit``, ``group`` and ``within_aoi`` are ours: a queryable describes a property, the panel also needs how it
    narrows it and under which property its range is sent to be applied inside the AOI instead (DS-03 plan §6.10), or
    ``None`` where the filter has no area.
    """
    published: list[dict[str, object]] = []
    for entry in config.search_filters:
        fields: dict[str, object] = {
            "property": entry.property,
            "kind": entry.kind.value,
            "title": entry.title,
            "description": entry.description,
            "unit": entry.unit,
            "within_aoi": None if entry.within_aoi is None else entry.within_aoi.value,
            "area_based": entry.area_based,
            "group": entry.group,
        }
        if entry.kind is FilterKind.RANGE:
            fields.update(
                type="integer" if entry.integer else "number", minimum=entry.minimum, maximum=entry.maximum
            )
        else:
            fields.update(type="string", oneOf=[{"const": value.value, "title": value.label} for value in entry.values])
        published.append(fields)
    return published


def _earthx_search_capabilities(config: DatasetConfig) -> dict[str, bool]:
    """What the search can do besides filtering (DS-03c): judge per overpass, and the coverage of the AOI."""
    capabilities = config.search_capabilities
    return {"evaluate": capabilities.evaluate, "aoi_coverage": capabilities.aoi_coverage}


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
    name = doi_name(config.doi)
    if name:
        # The DOI name, as the extension defines the field (adr/0014 §10.2); the
        # registry keeps the URL the source's own `cite-as` link gave.
        fields["sci:doi"] = name
    if config.citation:
        fields["sci:citation"] = config.citation
    return fields


def _providers(config: DatasetConfig) -> list[dict[str, object]]:
    """STAC `providers`, without `url` where the entry names none (UI-05 plan §5)."""
    published: list[dict[str, object]] = []
    for provider in config.providers:
        fields: dict[str, object] = {"name": provider.name, "roles": [role.value for role in provider.roles]}
        if provider.url is not None:
            fields["url"] = provider.url
        published.append(fields)
    return published


def _links(config: DatasetConfig) -> list[dict[str, str]]:
    links = [{"rel": "license", "href": config.license.url, "title": config.license.name}]
    name = doi_name(config.doi)
    if name:
        links.append({"rel": "cite-as", "href": f"https://doi.org/{name}"})
    return links


def to_stac_collection(config: DatasetConfig) -> dict[str, object]:
    """Build the STAC Collection for a registry entry.

    Returns a plain dictionary, freshly built on every call: no caller can reach
    back into the frozen entry through a shared list.
    """
    scientific = _scientific(config)
    collection: dict[str, object] = {
        "type": "Collection",
        "stac_version": STAC_VERSION,
        "stac_extensions": [
            *([SCIENTIFIC_EXTENSION] if scientific else []),
            *([CLASSIFICATION_EXTENSION] if config.band_classes else []),
        ],
        "id": config.dataset_id,
        "title": config.title,
        "description": config.description,
        "keywords": list(config.keywords),
        "license": _stac_license(config.license),
        # UI-05 plan §5 (F2): who stands behind the data and its resolution, in the fields of the STAC core.
        "providers": _providers(config),
        "summaries": {"gsd": list(config.gsd)},
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
        "links": _links(config),
        # M5-40: a full entry, as against a listed one (`catalog.listed`), which has no display and no processing.
        "earthx:entry": "full",
        "earthx:data_class": config.data_class.value,
        # UI-05 plan §5 (F1): the group of the Data catalogue.
        "earthx:category": config.category,
        # architekturplan.md 6.2's reader dispatch (`cog`, `zarr`, `legacy`) —
        # published so the frontend can tell a whole scene it may link straight
        # to the source (a COG) from one it may not (a Zarr store has no single
        # file to link, M3-17) without a dataset-specific branch anywhere.
        "earthx:format": config.format.value,
        # adr/0018 F1 (DS-04a): `gcp_tps` tells that the position comes from ground control points, approximately.
        "earthx:georeferencing": config.georeferencing.value,
        "earthx:capabilities": _earthx_capabilities(config),
        "earthx:mask": _earthx_mask(config),
        "earthx:band_units": _earthx_band_units(config),
        "earthx:bands": _earthx_bands(config),
        "earthx:auxiliary_assets": _earthx_auxiliary_assets(config),
        "earthx:search_filters": _earthx_search_filters(config),
        "earthx:search_capabilities": _earthx_search_capabilities(config),
        "earthx:index_presets": _earthx_index_presets(config),
        "earthx:true_color": _earthx_true_color(config),
        "earthx:composite_presets": _earthx_composite_presets(config),
        "earthx:step_presets": _earthx_step_presets(config),
        "earthx:license_flags": _earthx_license_flags(config),
        # adr/0024 R3: `unclear` marks a prototype source, `legal_note` says what is unclear (null when cleared, A4).
        "earthx:legal_status": config.legal_status.value,
        "earthx:legal_note": config.legal_note,
        "earthx:access": {
            "token_free_checked_at": (
                None if config.access.token_free_checked_at is None else config.access.token_free_checked_at.isoformat()
            ),
            "method": config.access.method,
            "cors": config.access.cors,
            # adr/0027 §6.1: what reading the assets needs; anything but `none` makes it a catalogue entry with a link.
            "account": config.access.account.value,
            "account_provider": config.access.account_provider,
            "account_paths": [path.value for path in config.access.account_paths],
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
                # DS-04 plan F2: our own field beside those of the extension.
                "asset_selection": config.default_render.asset_selection.value,
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
        # `overview`, `overview_resampling` and `overview_substitute` (M5-30b, adr/0032 §9) say what is
        # shown below `min_zoom`; the viewer reads them through and decides nothing, except that it draws
        # the substitute's tiles (`/collections/{id}/overview/tiles/…`) where the dataset names one.
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
                "overview": config.viewer.overview.value,
                "overview_resampling": (
                    None if config.viewer.overview_resampling is None else config.viewer.overview_resampling.value
                ),
                "overview_substitute": config.viewer.overview_substitute,
            }
        ),
        "earthx:source": {
            "adapter": config.source.adapter.value,
            "endpoint": config.source.endpoint,
            "source_collection_id": config.source.source_collection_id,
            # M5-55: the link "Source" of the Data catalogue, a page for people (the endpoint is the API).
            "page_url": config.source.page_url,
            "asset_hosts": list(config.source.asset_hosts),
            # M3-11a (K-05): federated or materialized — what `FederatingCoreCrudClient`
            # branches search and item-fetch on, read back off this very document
            # (`api/federating_client.py::_holding_of`).
            "item_holding": config.source.item_holding.value,
            # M5-07: where the storage of the assets lies (adr/0022 §7.2), for the description of the dataset.
            "data_region": config.source.data_region,
            # M5-08: the fixed asset keys and which state of a tile is loaded (architekturplan.md 5.1).
            "asset_keys": [
                {"key": rule.key, "media_type": rule.media_type, "gsd": rule.gsd} for rule in config.source.asset_keys
            ],
            "item_states": (
                None
                if config.source.item_states is None
                else {"rule": config.source.item_states.rule.value, "tile_pattern": config.source.item_states.tile_pattern}
            ),
            # DS-04 plan §4.2, §4.3: the prefixes the adapter rewrites, and the checksum that versions an input.
            "asset_href_rewrites": [
                {"from_prefix": rewrite.from_prefix, "to_prefix": rewrite.to_prefix}
                for rewrite in config.source.asset_href_rewrites
            ],
            "asset_checksum": None if config.source.asset_checksum is None else config.source.asset_checksum.value,
        },
        # DS-04 plan §4.4: what the recipe and ATTRIBUTION.txt say about the data (the viewer shows no mark for it, adr/0018
        # F2, Nachtrag DS-04c), and the sentences of the row "Limitations" of the Data catalogue.
        "earthx:notices": [
            {"code": notice.code, "label": notice.label, "tooltip": notice.tooltip} for notice in config.notices
        ],
        "earthx:limitations": list(config.limitations),
        # architekturplan.md 5.1, tenth row (adr/0007 §12.11 point 14): how settled
        # the source itself is, not a measurement like earthx:health. No default on
        # the entry (KLAERUNGEN B10), so this is always one of the three values.
        "earthx:maturity": config.maturity.value,
    }
    collection.update(scientific)
    return collection
