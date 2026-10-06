"""Access resolution: from an item, its registry entry and an asset key to what a
reader opens (adr/0011 §6.4, architekturplan.md 3.1).

It used to live in ``api/tiler.py``. It moved here because `processing` needs the
same step in M4 and may import `access`, but not `api`. Two halves, on purpose:

* :func:`resolve_asset` is pure — no network, no policy. It picks the reader by the
  registry's ``format``, splits a Zarr key at the registry's variable separator and
  reads the href and the CRS off the item. Its answer, :class:`ResolvedAsset`, is
  plain data that survives a JSON round trip, so a recipe can carry it to a worker
  or a local runner (architekturplan.md 7.1, 7.7).
* :func:`open_asset_ref` turns that data into an :class:`~earthx.readers.cog.AssetPath`
  or a :class:`~earthx.readers.zarr_reader.ZarrAsset`. It hands ``policy`` and
  ``resolve`` on to `readers`, where ``check_url`` runs; a refused address comes
  back as :class:`~earthx.readers.errors.AssetRejected`.

This module imports nothing from `gateway`, not even as a type, and from `catalog`
only ``catalog.registry``: whatever `processing` reaches through here must stay free
of a database (`.importlinter`, ``no-database-in-worker-core``).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from typing import TYPE_CHECKING, Any, Literal, get_args

import morecantile
from rasterio.warp import transform_bounds

from earthx.catalog.registry import DataFormat, DatasetConfig
from earthx.readers import AssetRejected, Policy, Resolver
from earthx.readers.cog import AssetPath, asset_path
from earthx.readers.zarr_reader import ZarrAsset, split_asset_key, zarr_asset

if TYPE_CHECKING:
    from starlette.requests import Request

LOGGER = logging.getLogger("earthx.access.resolve")

__all__ = [
    "AssetNotOnItem",
    "AssetResolutionError",
    "InvalidAssetKey",
    "MalformedItem",
    "NoReader",
    "ReaderKind",
    "ResolvedAsset",
    "open_asset_ref",
    "resolve_asset",
    "target_gsd_for",
]

ReaderKind = Literal["cog", "zarr"]

# The formats a reader exists for. `LEGACY` is the prototype's shape and has none
# in the target path, so it is refused rather than read as a COG (adr/0007 §6 point 2).
_READERS: dict[DataFormat, ReaderKind] = {DataFormat.COG: "cog", DataFormat.ZARR: "zarr"}

# Forced onto the coarsest `multiscales` level there is: adr/0007 §12.11 point 8
# measured the difference against a fine level at ~5% in `p98`, and the read stays
# cheap regardless of where on the extent the item sits.
_COARSEST_LEVEL = float("inf")


class AssetResolutionError(Exception):
    """This asset cannot be resolved; the text names dataset or key, never an address."""


class NoReader(AssetResolutionError):
    """The registry stores this dataset in a format no reader opens."""


class InvalidAssetKey(AssetResolutionError):
    """The asset key is shaped wrong for this dataset — the caller's mistake."""


class AssetNotOnItem(AssetResolutionError):
    """The item carries no asset under this key."""


class MalformedItem(AssetResolutionError):
    """The item has no id — the source's mistake, not the caller's."""


@dataclass(frozen=True, slots=True)
class ResolvedAsset:
    """One asset of one item, resolved but not yet cleared through a policy.

    ``asset`` is the key as it was asked for — for a Zarr dataset with a variable
    separator that is ``"<item asset><separator><variable>"``, the same value the
    statistics cache keys on. ``href`` is the item asset's address as the item names
    it; whether it may be fetched is decided only when it is opened.
    """

    dataset_id: str
    item_id: str
    asset: str
    reader: ReaderKind
    href: str
    variable: str | None
    crs: str | None

    def __post_init__(self) -> None:
        for name in ("dataset_id", "item_id", "asset", "href"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"ResolvedAsset.{name} must be a non-empty string")
        if self.reader not in get_args(ReaderKind):
            raise ValueError(f"ResolvedAsset.reader must be one of {get_args(ReaderKind)}")
        for name in ("variable", "crs"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"ResolvedAsset.{name} must be a non-empty string or null")
        if self.reader == "cog" and self.variable is not None:
            raise ValueError("ResolvedAsset.variable is only for a Zarr asset")

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> ResolvedAsset:
        """The asset back from :meth:`to_json`; every field is required, no other is allowed."""
        if not isinstance(data, Mapping):
            raise ValueError("a ResolvedAsset is a JSON object")
        expected = {field.name for field in fields(cls)}
        if set(data) != expected:
            missing = sorted(expected - set(data))
            unknown = sorted(str(key) for key in set(data) - expected)
            raise ValueError(f"a ResolvedAsset needs exactly its fields (missing {missing}, unknown {unknown})")
        return cls(**data)


def resolve_asset(item: Mapping[str, Any], config: DatasetConfig, asset: str) -> ResolvedAsset:
    """What ``asset`` of ``item`` is, for a reader — without fetching or checking anything.

    **The registry's ``format`` picks the reader**, here and nowhere else: the client
    sends the same tile URL either way (M2-09a). A format without a reader is
    :class:`NoReader` rather than read as a COG — a silent fallback would turn a
    registry mistake into a wrong picture.

    For a Zarr dataset, ``asset`` may carry a variable after the registry's
    ``ZarrInfo.variable_separator`` (adr/0007 §12.11, plan §10 F2) — split off
    *before* the href is looked up, because the item only ever advertises the group
    side of that key. A key shaped wrong for this is :class:`InvalidAssetKey`, the
    caller's mistake; an item without that asset is :class:`AssetNotOnItem`, and an
    item without an id is :class:`MalformedItem`.
    """
    reader = _READERS.get(config.format)
    if reader is None:
        raise NoReader(f"{config.dataset_id!r} is stored as {config.format.value}, which no reader opens")
    item_asset, variable = asset, None
    if reader == "zarr":
        separator = config.zarr.variable_separator if config.zarr is not None else None
        try:
            item_asset, variable = split_asset_key(asset, separator)
        except AssetRejected as error:
            raise InvalidAssetKey(str(error)) from None
    item_id = item.get("id")
    if not isinstance(item_id, str) or not item_id:
        raise MalformedItem(f"an item of {config.dataset_id!r} carries no id")
    return ResolvedAsset(
        dataset_id=config.dataset_id,
        item_id=item_id,
        asset=asset,
        reader=reader,
        href=_asset_href(item, item_asset),
        variable=variable,
        crs=_proj_code(item),
    )


def open_asset_ref(
    ref: ResolvedAsset,
    policy: Policy,
    resolve: Resolver,
    *,
    target_gsd: float | None = None,
    decode_cf: bool = True,
) -> AssetPath | ZarrAsset:
    """What a reader may open for ``ref``, cleared through ``policy`` — or :class:`AssetRejected`.

    ``target_gsd`` and ``decode_cf`` only mean something to a Zarr read (see
    :class:`~earthx.readers.zarr_reader.ZarrAsset`); a COG picks its overview itself
    and is always read as stored.
    """
    if ref.reader == "zarr":
        return zarr_asset(
            ref.href,
            policy,
            dataset_id=ref.dataset_id,
            item_id=ref.item_id,
            asset=ref.asset,
            crs=ref.crs,
            resolve=resolve,
            variable=ref.variable,
            target_gsd=target_gsd,
            decode_cf=decode_cf,
        )
    return asset_path(
        ref.href,
        policy,
        dataset_id=ref.dataset_id,
        item_id=ref.item_id,
        asset=ref.asset,
        resolve=resolve,
    )


def target_gsd_for(request: Request, stac_item: Mapping[str, Any]) -> float | None:
    """The ground sample distance a Zarr read should aim for, or ``None`` to leave
    the level exactly as the asset names it.

    Three cases, and only three — everything else reads the level the item's asset
    already points at, unchanged since M2-09a:

    * **``/statistics``** is answered on the coarsest level there is (§12.11 point 8).
    * **a tile request** names ``z``/``x``/``y``/``tileMatrixSetId`` in its own route
      (TiTiler's own path, matched here through ``request.path_params`` rather than
      a parameter of this function, so nothing here has to repeat TiTiler's route
      shape). The real ground resolution of that tile is computed from its own
      bounds, reprojected into the item's CRS — not read off a fixed zoom table,
      because a Web Mercator tile's real resolution scales with ``cos(latitude)``
      (adr/0007 §12.10) and a table would pick the wrong level near either end of
      this dataset's 34°–72° N extent.
    * **anything else** (a preview, the AOI crop) computes nothing and returns
      ``None`` — a crop wants the resolution its asset names, not the coarsest
      level statistics settles for.
    """
    if request.url.path.endswith("/statistics"):
        return _COARSEST_LEVEL
    path_params = request.path_params
    if not {"z", "x", "y", "tileMatrixSetId"} <= path_params.keys():
        return None
    crs = _proj_code(stac_item)
    if crs is None:
        return None
    try:
        tms = morecantile.tms.get(str(path_params["tileMatrixSetId"]))
        z = int(path_params["z"])
        west, south, east, north = tms.bounds(int(path_params["x"]), int(path_params["y"]), z)
        item_west, _, item_east, _ = transform_bounds("EPSG:4326", crs, west, south, east, north)
        tile_size = tms.matrix(z).tileWidth
    except Exception:
        # A resolution this cannot compute (an unknown TMS id, a CRS transform
        # that fails) is not worth failing the tile over — it reads the level the
        # asset names instead, the same as before this feature existed.
        LOGGER.warning("could not compute a target resolution for the tile", exc_info=True)
        return None
    return abs(item_east - item_west) / tile_size


def _asset_href(item: Mapping[str, Any], asset: str) -> str:
    assets = item.get("assets")
    entry = assets.get(asset) if isinstance(assets, Mapping) else None
    href = entry.get("href") if isinstance(entry, Mapping) else None
    if not isinstance(href, str) or not href:
        raise AssetNotOnItem(f"the item carries no asset {asset!r}")
    return href


def _proj_code(stac_item: Mapping[str, Any]) -> str | None:
    """The item's own CRS, in either spelling STAC has for it.

    ``proj:code`` is the projection extension v2, ``proj:epsg`` the v1 field our own
    API still emits (adr/0007 §6 point 4). A Zarr store may carry no CRS at all
    (§3.4), and then this is the only place it can come from; where the store does
    carry one, this stays the fallback.
    """
    properties = stac_item.get("properties")
    if not isinstance(properties, Mapping):
        return None
    code = properties.get("proj:code")
    if isinstance(code, str) and code:
        return code
    epsg = properties.get("proj:epsg")
    return f"EPSG:{epsg}" if isinstance(epsg, int) else None
