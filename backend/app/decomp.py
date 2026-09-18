"""Polarimetric decompositions for the L1A SCS product.

SCS ships the *complex* quad-pol data as two 4-band GeoTIFFs (amplitude
``i_abs`` + ``i_phase``) in **slant-range** geometry, geolocated only by GCPs.
So we warp both to a geographic grid with nearest-neighbour resampling (which
keeps each amplitude/phase pair co-located = a valid single-look complex
sample), reconstruct the complex scattering vector, run the decomposition, and
write a 3-band RGB-encoded COG that the normal /tiles path can serve.

Implemented:
  - pauli            R=|HH-VV|, G=|HV|, B=|HH+VV|   (coherent, uses phase)
  - freeman-durden   R=double-bounce, G=volume, B=surface  (model-based)
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import rasterio
from affine import Affine
from rasterio.io import MemoryFile
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

from . import auth, store
from .cog import _gdal_env

METHODS = ("pauli", "freeman")


class DecompError(RuntimeError):
    pass


# --- numpy-only boxcar mean (multi-look), integral-image based ------------
def _boxcar(a: np.ndarray, w: int) -> np.ndarray:
    if w <= 1:
        return a
    ap = np.pad(a.astype("float64"), w // 2, mode="edge")
    s = np.zeros((ap.shape[0] + 1, ap.shape[1] + 1), dtype="float64")
    s[1:, 1:] = np.cumsum(np.cumsum(ap, axis=0), axis=1)
    h, wd = a.shape
    total = s[w : w + h, w : w + wd] - s[0:h, w : w + wd] - s[w : w + h, 0:wd] + s[0:h, 0:wd]
    return total / (w * w)


def _boxcar_c(a: np.ndarray, w: int) -> np.ndarray:
    if w <= 1:
        return a
    return _boxcar(a.real, w) + 1j * _boxcar(a.imag, w)


# --- warp complex quad-pol to a geographic grid clipped to the AOI --------
def _warp_complex(
    abs_href: str,
    phase_href: str,
    bbox: tuple[float, float, float, float],
    token: Optional[str],
    max_size: int = 2048,
):
    dst = "EPSG:4326"
    with _gdal_env(token):
        with rasterio.open(abs_href) as asrc, rasterio.open(phase_href) as psrc:
            gcps, gcp_crs = asrc.get_gcps()
            if not gcps:
                raise DecompError("SCS scene has no GCPs — cannot geocode.")
            full, fw, fh = calculate_default_transform(
                gcp_crs, dst, asrc.width, asrc.height, gcps=gcps
            )
            res = abs(full.a)
            sminx, sminy, smaxx, smaxy = array_bounds(fh, fw, full)
            minx = max(bbox[0], sminx)
            miny = max(bbox[1], sminy)
            maxx = min(bbox[2], smaxx)
            maxy = min(bbox[3], smaxy)
            if maxx <= minx or maxy <= miny:
                raise DecompError("AOI does not overlap this scene.")
            w2 = int(np.ceil((maxx - minx) / res))
            h2 = int(np.ceil((maxy - miny) / res))
            scale = max(max(w2, h2) / max_size, 1.0)
            w2 = max(int(w2 / scale), 1)
            h2 = max(int(h2 / scale), 1)
            dtr = Affine(res * scale, 0, minx, 0, -res * scale, maxy)

            def warp(src, band):
                out = np.zeros((h2, w2), "float32")
                reproject(
                    source=rasterio.band(src, band),
                    destination=out,
                    src_crs=gcp_crs,
                    gcps=gcps,
                    dst_crs=dst,
                    dst_transform=dtr,
                    resampling=Resampling.nearest,
                    src_nodata=0,
                    dst_nodata=0,
                )
                return out

            a = [warp(asrc, b) for b in range(1, 5)]
            p = [warp(psrc, b) for b in range(1, 5)]

    # bands order: HH, HV, VH, VV
    s = [a[i] * np.exp(1j * p[i]) for i in range(4)]
    valid = a[0] > 0
    return s, dtr, valid


# --- decompositions -> (R, G, B) float32 ----------------------------------
def _pauli(s, valid):
    hh, hv, vh, vv = s
    r = np.abs(hh - vv) / np.sqrt(2.0)
    g = np.abs(hv) * np.sqrt(2.0)
    b = np.abs(hh + vv) / np.sqrt(2.0)
    return r, g, b


def _freeman(s, valid, w=5):
    hh, hv, vh, vv = s
    shv = 0.5 * (hv + vh)
    c11 = _boxcar(np.abs(hh) ** 2, w)
    c33 = _boxcar(np.abs(vv) ** 2, w)
    ehv = _boxcar(np.abs(shv) ** 2, w)
    c13 = _boxcar_c(hh * np.conj(vv), w)

    fv = 3.0 * ehv
    c11r = c11 - fv
    c33r = c33 - fv
    c13r = c13 - fv / 3.0
    reC = np.real(c13r)
    imC = np.imag(c13r)

    fs = np.zeros_like(c11)
    fd = np.zeros_like(c11)

    surf = reC >= 0  # surface dominant → double-bounce α = -1
    # surface-dominant branch
    denom_s = c11r + c33r + 2.0 * reC
    with np.errstate(divide="ignore", invalid="ignore"):
        fs_s = ((reC + c33r) ** 2 + imC**2) / denom_s
    fd_s = c33r - fs_s
    # double-bounce-dominant branch (β = +1)
    denom_d = c11r + c33r - 2.0 * reC
    with np.errstate(divide="ignore", invalid="ignore"):
        fd_d = ((reC - c33r) ** 2 + imC**2) / denom_d
    fs_d = c33r - fd_d

    fs = np.where(surf, fs_s, fs_d)
    fd = np.where(surf, fd_s, fd_d)
    fs = np.nan_to_num(fs, nan=0.0, posinf=0.0, neginf=0.0)
    fd = np.nan_to_num(fd, nan=0.0, posinf=0.0, neginf=0.0)

    # component powers (span contributions); clamp negatives (model mismatch)
    ps = np.clip(2.0 * fs, 0, None)  # ~fs(1+|β|²)
    pd = np.clip(2.0 * fd, 0, None)  # fd(1+|α|²)
    pv = np.clip((8.0 / 3.0) * fv, 0, None)
    # RGB: R=double-bounce, G=volume, B=surface
    return pd, pv, ps


_DECOMP = {"pauli": _pauli, "freeman": _freeman}


def decompose_crop(
    item_id: str,
    geometry: dict,
    bbox: tuple[float, float, float, float],
    method: str,
) -> dict:
    if method not in _DECOMP:
        raise DecompError(f"Unknown decomposition '{method}'.")
    item = store.get_item(item_id)
    if not item:
        raise FileNotFoundError(f"Item '{item_id}' is unknown — search first.")
    assets = item.get("assets", {})
    abs_a = assets.get("enclosure_i_abs_tiff")
    pha_a = assets.get("enclosure_i_phase_tiff")
    if not abs_a or not pha_a:
        raise DecompError("This scene has no SCS complex (abs+phase) TIFFs to decompose.")

    aoi_h = store.aoi_hash(geometry)
    key = f"decomp_{method}"
    out_path = store.crop_path(item_id, aoi_h, key)
    if out_path.exists():
        store.touch(out_path)
        with rasterio.open(out_path) as ds:
            b = ds.bounds
        return {
            "item_id": item_id, "aoi_hash": aoi_h, "asset": key, "cached": True,
            "bounds": [b.left, b.bottom, b.right, b.top], "path": str(out_path),
        }

    token = auth.get_access_token()
    s, dtr, valid = _warp_complex(abs_a["href"], pha_a["href"], bbox, token)
    r, g, b = _DECOMP[method](s, valid)
    data = np.stack([r, g, b]).astype("float32")
    data[:, ~valid] = np.nan  # transparent nodata outside the swath
    h2, w2 = valid.shape

    src_profile = {
        "driver": "GTiff", "dtype": "float32", "count": 3,
        "height": h2, "width": w2, "crs": "EPSG:4326",
        "transform": dtr, "nodata": float("nan"),
    }
    dst_profile = cog_profiles.get("deflate")
    dst_profile.update({"blockxsize": 256, "blockysize": 256})

    store.evict_if_needed()
    with MemoryFile() as memfile:
        with memfile.open(**src_profile) as mem_ds:
            mem_ds.write(data)
        cog_translate(memfile.name, str(out_path), dst_profile, in_memory=False, quiet=True)
    store.touch(out_path)
    store.evict_if_needed()

    with rasterio.open(out_path) as ds:
        bb = ds.bounds
    return {
        "item_id": item_id, "aoi_hash": aoi_h, "asset": key, "cached": False,
        "bounds": [bb.left, bb.bottom, bb.right, bb.top], "path": str(out_path),
    }
