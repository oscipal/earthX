"""A synthetic COG, written by this script — the COG counterpart of `mini_zarr.py`.

No binary fixture in the repository, for the same reason as there: a checked-in
raster is data whose licence would have to be argued (ENTSCHEIDUNGEN §4), and a
generated one says in code what it contains.

It sits on **the same ground as the Zarr store**, in the same UTM zone and with
the same bounds, so one AOI and one tile serve both formats and the end-to-end
chain of onboarding checklist point 9 does not need a case distinction for its
geometry.

Three things are deliberate rather than incidental:

* **real overviews**, written by ``rio_cogeo`` rather than a plain ``GTiff``, so
  a tile request at a low zoom reads a pyramid level and not the full raster —
  the property the whole tile path of adr/0006 rests on;
* **three uint8 bands**, which is the shape of Sentinel-2's ``visual`` asset, so
  the default visualisation of the real entry (an identity stretch over
  0..255) applies unchanged;
* **a nodata value**, because a crop at the edge of an AOI hits it and a reader
  that ignores it returns a black border instead of a mask.

:func:`serve_cog` is the other half. It cannot do what ``mini_zarr.serve_store``
does — route the bytes through ``Gateway`` — because GDAL fetches them itself and
``readers/cog.py`` says so in its own docstring ("What this module cannot do is
take the socket away from GDAL"). What it does instead is swap the last step,
``vsicurl_path``, for a local file, so everything before it runs for real:
``inspect_url``, the allowlist, the address check, and the refusal to build a
path from anything but a :class:`~earthx.gateway.CheckedUrl`.
"""

from __future__ import annotations

from pathlib import Path

import numpy
import pytest
import rasterio
from rasterio.transform import from_origin
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

from tests.earthx.readers.mini_zarr import FINEST_SIZE, HOST, ITEM_CRS, ORIGIN_X, ORIGIN_Y

#: Where the served COG lives. Same host as the Zarr store, so one synthetic
#: ``asset_hosts`` entry covers both formats.
ASSET_PATH = "/products/mini.tif"
ASSET_URL = f"https://{HOST}{ASSET_PATH}"

#: Three bands like Sentinel-2's ``visual``, so the entry's identity stretch fits.
BANDS = 3

#: Ground sample distance and size, matching the finest Zarr group exactly.
RESOLUTION = 10.0
SIZE = FINEST_SIZE

#: Reserved for "no data here", never produced by the generator below.
NODATA = 0

#: Small enough that a 72×72 raster still has more than one tile per level.
BLOCKSIZE = 16


def build_mini_cog(path: Path) -> Path:
    """Write a tiled, overviewed COG to ``path`` and return it.

    Two steps rather than one, because that is what ``rio_cogeo`` is for: a plain
    ``GTiff`` first, then the translation that adds the tiling, the overviews and
    the header layout a COG is defined by.
    """
    generator = numpy.random.default_rng(seed=20260922)
    # 1..255: NODATA stays reserved, so a masked pixel means "outside", never "dark".
    data = generator.integers(1, 256, (BANDS, SIZE, SIZE)).astype("uint8")

    profile = {
        "driver": "GTiff",
        "dtype": "uint8",
        "count": BANDS,
        "height": SIZE,
        "width": SIZE,
        "crs": ITEM_CRS,
        "transform": from_origin(ORIGIN_X, ORIGIN_Y, RESOLUTION, RESOLUTION),
        "nodata": NODATA,
    }
    plain = path.with_suffix(".plain.tif")
    with rasterio.open(plain, "w", **profile) as destination:
        destination.write(data)

    cog_profile = cog_profiles.get("deflate")
    cog_profile.update({"blockxsize": BLOCKSIZE, "blockysize": BLOCKSIZE})
    cog_translate(plain, path, cog_profile, overview_resampling="nearest", quiet=True)
    plain.unlink()
    return path


def serve_cog(local: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Let the reader open ``local`` instead of fetching, and log what it cleared.

    The log holds the URL of every asset that made it through ``check_url``, in
    order. Because :func:`earthx.readers.cog.asset_path` has no branch that skips
    the check, an entry in this list *is* the proof that the address was cleared
    before anything opened it — which is the half of the gateway promise a test
    without a socket can make (adr/0006 §3.3).
    """
    cleared: list[str] = []

    def vsicurl_path(checked: object) -> str:
        cleared.append(getattr(checked, "url", str(checked)))
        return str(local)

    monkeypatch.setattr("earthx.readers.cog.vsicurl_path", vsicurl_path)
    return cleared
