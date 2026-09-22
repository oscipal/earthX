"""Pauli and Freeman-Durden decompositions for complex quad-pol SCS data.

A resting operator (ENTSCHEIDUNGEN_2026-09-18.md §3): the compute core and the
warp rule moved here unchanged from the BIOMASS prototype's `app/decomp.py`
when the prototype was removed (adr/0008 §6, §9 Frage 3). What did **not**
move is `decompose_crop`, the platform-facing half that read the item
registry and the token-secured MAAP asset store (`app.store`, `app.auth`) —
both excluded from the target architecture (KLAERUNGEN B9, ENTSCHEIDUNGEN §3).

So this module has, on purpose, no caller and no registry entry: `quad_pol`
stays `False` for every dataset (`catalog/registry.py`), and the
`datasets-isolated` contract in `.importlinter` keeps it that way. It stays
isolated under `earthx/datasets/quad_pol_reference/` — named after the
capability, not a dataset, because it is open whether a token-free source for
*complex* quad-pol data exists at all (Sentinel-1 is dual-pol; ENTSCHEIDUNGEN
§3, open point in `docs/ENTSCHEIDUNGSLOG.md`). It is a placeholder for the day
a real dataset supplies that capability, at which point this directory is
renamed to that dataset's id and gets a registry entry.

Only two things changed against the prototype (adr/0008 §11 point 5): the
`token` parameter of `_warp_complex` is gone (no token in the target
architecture), and its GDAL environment now comes from
`earthx.gateway.gdal.gdal_options`, the one place that owns that
configuration (KLAERUNGEN B8). Everything else — the math, the warp rule, the
line order — is unchanged on purpose (CLAUDE.md: "`decomp.py` nie
generalisieren").

SCS ships the *complex* quad-pol data as two 4-band GeoTIFFs (amplitude
``i_abs`` + ``i_phase``) in **slant-range** geometry, geolocated only by GCPs.
So we warp both to a geographic grid with nearest-neighbour resampling (which
keeps each amplitude/phase pair co-located = a valid single-look complex
sample), reconstruct the complex scattering vector, and run the decomposition.

Implemented:
  - pauli            R=|HH-VV|, G=|HV|, B=|HH+VV|   (coherent, uses phase)
  - freeman-durden   R=double-bounce, G=volume, B=surface  (model-based)
"""

from __future__ import annotations

import numpy as np
import rasterio
from affine import Affine
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject

from earthx.gateway import Policy
from earthx.gateway.gdal import gdal_options

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
    policy: Policy,
    max_size: int = 2048,
):
    dst = "EPSG:4326"
    with rasterio.Env(**gdal_options(policy)):
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
