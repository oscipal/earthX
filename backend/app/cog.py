"""Cloud-Optimized-GeoTIFF reading: on-the-fly tiles + AOI crops.

Everything reads the remote COG over HTTP range requests (GDAL /vsicurl),
injecting the MAAP Bearer token via GDAL_HTTP_HEADERS. Only the requested
window is fetched, never the whole (multi-GB) scene.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Optional

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles
from rio_tiler.colormap import cmap as CMAPS
from rio_tiler.errors import TileOutsideBounds
from rio_tiler.io import Reader

from . import auth, store
from .config import get_settings

# 1x1 transparent PNG returned for tiles outside the data footprint.
_EMPTY_TILE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _gdal_env(token: Optional[str]) -> rasterio.Env:
    opts = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff,.TIF,.TIFF",
        "GDAL_HTTP_MULTIRANGE": "YES",
        "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
        "GDAL_HTTP_VERSION": "2",
        "VSI_CACHE": "TRUE",
        "VSI_CACHE_SIZE": str(64 * 1024 * 1024),
    }
    if token:
        opts["GDAL_HTTP_HEADERS"] = f"Authorization: Bearer {token}"
    return rasterio.Env(**opts)


class NoCogAssetError(Exception):
    """The item has no Cloud-Optimized-GeoTIFF asset that can be cropped/tiled."""


_NO_COG_MSG = (
    "This scene has no Cloud-Optimized-GeoTIFF to crop. Some BIOMASS products "
    "(e.g. Level-1 SCS) ship their full data only as a zip archive, so on-demand "
    "cropping/tiling isn't available — the quicklook preview still works. Products "
    "with COG assets (e.g. Level-2 forest products) can be downloaded."
)


def _resolve_cog_key(item_id: str, asset_key: Optional[str]) -> str:
    """Pick a COG asset key that actually exists on the item, else raise."""
    item = store.get_item(item_id)
    if not item:
        raise FileNotFoundError(f"Item '{item_id}' is unknown — run a search first.")
    assets = item.get("assets", {})
    for candidate in (asset_key, item.get("cog_key"), get_settings().default_cog_asset):
        if candidate and candidate in assets:
            return candidate
    raise NoCogAssetError(_NO_COG_MSG)


def _resolve_source(item_id: str, asset_key: Optional[str], aoi_h: Optional[str]) -> tuple[str, bool]:
    """Return (source, is_local). Prefer a cached AOI crop when available."""
    # Decomposition (decomp.py) and stitched mosaics are pre-computed local COGs.
    if asset_key and (asset_key.startswith("decomp_") or asset_key == "stitch") and aoi_h:
        p = store.crop_path(item_id, aoi_h, asset_key)
        if p.exists():
            store.touch(p)
            return str(p), True
        raise NoCogAssetError("This decomposition hasn't been computed yet.")
    key = _resolve_cog_key(item_id, asset_key)
    if aoi_h:
        p = store.crop_path(item_id, aoi_h, key)
        if p.exists():
            store.touch(p)
            return str(p), True
    href = store.asset_href(item_id, key, role="cog")
    if not href:
        raise NoCogAssetError(_NO_COG_MSG)
    return href, False


def _colormap(name: str):
    try:
        return CMAPS.get(name)
    except (KeyError, Exception):  # noqa: BLE001
        return CMAPS.get("viridis")


# Per-band 2–98% stretch cached per (item, band-selection) so the same window is
# used for every tile (no seams) and only computed once.
_RESCALE_CACHE: dict[str, list[list[float]]] = {}


def _stats_rescale(
    source: str,
    is_local: bool,
    token: Optional[str],
    indexes: Optional[tuple[int, ...]],
    expression: Optional[str],
) -> list[list[float]]:
    """One [lo, hi] pair per output band from the 2nd–98th percentiles."""
    env = _gdal_env(None if is_local else token)
    with env, Reader(source) as cog:
        stats = cog.statistics(expression=expression) if expression else cog.statistics(indexes=indexes)
    out: list[list[float]] = []
    for band in stats.values():
        lo = float(band.percentile_2)
        hi = float(band.percentile_98)
        if hi <= lo:
            lo, hi = float(band.min), float(band.max)
        out.append([lo, hi if hi > lo else lo + 1.0])
    return out


def render_tile(
    item_id: str,
    z: int,
    x: int,
    y: int,
    asset_key: Optional[str] = None,
    aoi_h: Optional[str] = None,
    rescale: Optional[list[list[float]]] = None,
    colormap: Optional[str] = None,
    indexes: Optional[tuple[int, ...]] = None,
    expression: Optional[str] = None,
) -> bytes:
    """Render a PNG tile.

    - single band  → grayscale run through ``colormap``
    - >1 band      → rendered directly as an RGB(A) composite
    ``indexes`` selects bands; ``expression`` (rio-tiler band math, e.g.
    ``"abs(b1-b4);b2;abs(b1+b4)"``) overrides it. ``rescale`` is a list of
    [lo, hi] pairs (one, broadcast to all bands, or one per band); omit for an
    automatic per-band 2–98% stretch.
    """
    settings = get_settings()
    source, is_local = _resolve_source(item_id, asset_key, aoi_h)
    token = None if is_local else auth.get_access_token()
    idx = tuple(indexes) if indexes else (1,)
    cache_key = expression or ("idx:" + ",".join(map(str, idx)))

    try:
        env = _gdal_env(None if is_local else token)
        with env, Reader(source) as cog:
            if expression:
                img = cog.tile(x, y, z, expression=expression, tilesize=256)
            else:
                img = cog.tile(x, y, z, indexes=idx, tilesize=256)
    except TileOutsideBounds:
        return _EMPTY_TILE

    nbands = img.data.shape[0]
    if rescale:
        pairs = rescale if len(rescale) == nbands else [rescale[0]] * nbands
    else:
        ck = f"{item_id}|{cache_key}"
        pairs = _RESCALE_CACHE.get(ck)
        if pairs is None:
            try:
                pairs = _stats_rescale(source, is_local, token, idx, expression)
            except Exception:  # noqa: BLE001 - never let stats break tiling
                pairs = [[0.0, 1.0]]
            if len(pairs) != nbands:
                pairs = [pairs[0] if pairs else [0.0, 1.0]] * nbands
            _RESCALE_CACHE[ck] = pairs

    img.rescale(in_range=tuple(tuple(p) for p in pairs))
    if nbands == 1:
        cmap = _colormap(colormap or settings.tile_default_colormap)
        return img.render(img_format="PNG", colormap=cmap)
    return img.render(img_format="PNG")


def crop_to_aoi(
    item_id: str,
    geometry: dict,
    bbox: tuple[float, float, float, float],
    asset_key: Optional[str] = None,
    max_size: int = 4096,
) -> dict:
    """Read the AOI window from the remote COG and write a small cached COG.

    Returns metadata incl. output bounds and the local path.
    """
    key = _resolve_cog_key(item_id, asset_key)
    aoi_h = store.aoi_hash(geometry)
    out_path = store.crop_path(item_id, aoi_h, key)

    if out_path.exists():
        store.touch(out_path)
        with rasterio.open(out_path) as ds:
            b = ds.bounds
        return {
            "item_id": item_id,
            "aoi_hash": aoi_h,
            "asset": key,
            "cached": True,
            "bounds": [b.left, b.bottom, b.right, b.top],
            "path": str(out_path),
        }

    href = store.asset_href(item_id, key, role="cog")
    if not href:
        raise NoCogAssetError(_NO_COG_MSG)

    token = auth.get_access_token()
    env = _gdal_env(token)
    with env, Reader(href) as cog:
        # part() reprojects the requested WGS84 bbox to the COG's CRS internally.
        img = cog.part(
            list(bbox),
            bounds_crs="EPSG:4326",
            dst_crs="EPSG:4326",
            max_size=max_size,
        )

    data = img.data  # (bands, h, w)
    mask = img.mask  # (h, w), 255 = valid
    count, height, width = data.shape
    transform = from_bounds(*img.bounds, width, height)

    dtype = data.dtype
    nodata: Optional[float]
    if np.issubdtype(dtype, np.floating):
        nodata = float("nan")
        data = np.where(mask[np.newaxis, :, :] > 0, data, np.nan).astype(dtype)
    else:
        nodata = 0
        data = np.where(mask[np.newaxis, :, :] > 0, data, 0).astype(dtype)

    src_profile = {
        "driver": "GTiff",
        "dtype": dtype,
        "count": count,
        "height": height,
        "width": width,
        "crs": "EPSG:4326",
        "transform": transform,
        "nodata": nodata,
    }

    dst_profile = cog_profiles.get("deflate")
    dst_profile.update({"blockxsize": 256, "blockysize": 256})

    store.evict_if_needed()
    with MemoryFile() as memfile:
        with memfile.open(**src_profile) as mem_ds:
            mem_ds.write(data)
        cog_translate(
            memfile.name,
            str(out_path),
            dst_profile,
            in_memory=False,
            quiet=True,
            web_optimized=False,
            overview_resampling="average",
        )
    store.touch(out_path)
    store.evict_if_needed()

    with rasterio.open(out_path) as ds:
        b = ds.bounds
    return {
        "item_id": item_id,
        "aoi_hash": aoi_h,
        "asset": key,
        "cached": False,
        "bounds": [b.left, b.bottom, b.right, b.top],
        "path": str(out_path),
    }


def stitch_to_aoi(
    item_ids: list[str],
    geometry: dict,
    bbox: tuple[float, float, float, float],
    asset_key: Optional[str] = None,
    max_size: int = 4096,
) -> dict:
    """Mosaic several adjacent scenes' AOI windows onto one common grid and write
    a single COG. Each scene is read into the same bbox grid (only its footprint
    is valid); overlaps keep the first valid pixel."""
    aoi_h = store.aoi_hash(geometry)
    set_hash = hashlib.md5(",".join(sorted(item_ids)).encode()).hexdigest()[:12]
    synthetic = f"stitch_{set_hash}"
    out_path = store.crop_path(synthetic, aoi_h, "stitch")

    def _meta(cached: bool) -> dict:
        with rasterio.open(out_path) as ds:
            b = ds.bounds
        return {
            "item_id": synthetic, "aoi_hash": aoi_h, "asset": "stitch", "cached": cached,
            "bounds": [b.left, b.bottom, b.right, b.top], "path": str(out_path),
        }

    if out_path.exists():
        store.touch(out_path)
        return _meta(True)

    minx, miny, maxx, maxy = bbox
    aspect = (maxx - minx) / (maxy - miny)
    if aspect >= 1:
        width, height = max_size, max(1, round(max_size / aspect))
    else:
        height, width = max_size, max(1, round(max_size * aspect))

    token = auth.get_access_token()
    env = _gdal_env(token)
    combined: Optional[np.ndarray] = None
    cmask: Optional[np.ndarray] = None
    dtype = None
    for item_id in item_ids:
        key = _resolve_cog_key(item_id, asset_key)
        href = store.asset_href(item_id, key, role="cog")
        if not href:
            continue
        try:
            with env, Reader(href) as cog:
                img = cog.part(
                    list(bbox), bounds_crs="EPSG:4326", dst_crs="EPSG:4326",
                    width=width, height=height,
                )
        except TileOutsideBounds:
            continue
        if combined is None:
            combined = np.zeros_like(img.data)
            cmask = np.zeros((height, width), dtype=bool)
            dtype = img.data.dtype
        valid = img.mask > 0
        fill = valid & (~cmask)
        for band in range(combined.shape[0]):
            combined[band][fill] = img.data[band][fill]
        cmask |= valid

    if combined is None:
        raise NoCogAssetError(_NO_COG_MSG)

    count = combined.shape[0]
    if np.issubdtype(dtype, np.floating):
        nodata: Optional[float] = float("nan")
        combined = np.where(cmask[np.newaxis, :, :], combined, np.nan).astype(dtype)
    else:
        nodata = 0
        combined = np.where(cmask[np.newaxis, :, :], combined, 0).astype(dtype)

    transform = from_bounds(minx, miny, maxx, maxy, width, height)
    src_profile = {
        "driver": "GTiff", "dtype": dtype, "count": count, "height": height, "width": width,
        "crs": "EPSG:4326", "transform": transform, "nodata": nodata,
    }
    dst_profile = cog_profiles.get("deflate")
    dst_profile.update({"blockxsize": 256, "blockysize": 256})

    store.evict_if_needed()
    with MemoryFile() as memfile:
        with memfile.open(**src_profile) as mem_ds:
            mem_ds.write(combined)
        cog_translate(memfile.name, str(out_path), dst_profile, in_memory=False, quiet=True, overview_resampling="average")
    store.touch(out_path)
    store.evict_if_needed()
    return _meta(False)
