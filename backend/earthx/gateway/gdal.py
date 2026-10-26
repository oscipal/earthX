"""Central GDAL configuration for remote reads (adr/0001 Z8).

The VSI cache is a read cache over immutable remote objects and may stay; what
moves here is its configuration, out of the prototype's ``cog.py`` and into the
one module that decides about outgoing traffic (KLAERUNGEN B8). No token: token
logic is not part of the gateway and not part of the target architecture at all
(ENTSCHEIDUNGEN §3).

**What this cannot do.** GDAL resolves the name itself and follows redirects
itself, so neither the address pinning nor the redirect loop from
:mod:`earthx.gateway.client` reaches it. B8 says so plainly: the network policy
in M6 is what closes that. Until then the one guarantee here is that a URL has
passed :func:`earthx.gateway.check_url` before GDAL sees it — which is why
:func:`vsicurl_path` takes a :class:`CheckedUrl` and nothing else.
"""

from __future__ import annotations

from earthx.gateway.checks import CheckedUrl
from earthx.gateway.policy import Policy

# Unchanged from the prototype: a read cache over immutable remote objects
# (adr/0001 Z8), 64 MiB per environment.
VSI_CACHE_BYTES = 64 * 1024 * 1024

# The global ``/vsicurl/`` region cache of the tiler (NM4-26 §8–§10, §18). GDAL's default is 16 MB and
# it reads the size once per process, in a static initializer (``port/cpl_vsil_curl.cpp`` of GDAL
# 3.12.2, l. 133–214), so it belongs in both tiler profiles: the first ``/vsicurl/`` access of the
# process may be a crop.
TILER_CURL_CACHE_BYTES = 256 * 1024 * 1024

# Both spellings, because the prototype carried both and GDAL matches the
# extension as written.
ALLOWED_EXTENSIONS = ".tif,.tiff,.TIF,.TIFF"


def gdal_options(policy: Policy) -> dict[str, str]:
    """The GDAL and VSI settings for reading a remote COG.

    Returned as a plain dict rather than a ``rasterio.Env``: the settings are
    checkable without GDAL installed, and `readers` builds the environment.
    """
    return {
        # A range read must not turn into a directory listing of the bucket.
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ALLOWED_EXTENSIONS,
        "GDAL_HTTP_MULTIRANGE": "YES",
        "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
        "GDAL_HTTP_VERSION": "2",
        "VSI_CACHE": "TRUE",
        "VSI_CACHE_SIZE": str(VSI_CACHE_BYTES),
        # The same limits the client keeps, so the numbers live in one place.
        "GDAL_HTTP_CONNECTTIMEOUT": str(int(policy.connect_timeout_s)),
        "GDAL_HTTP_TIMEOUT": str(int(policy.read_timeout_s)),
        "GDAL_HTTP_MAX_RETRY": "2",
        "GDAL_HTTP_RETRY_DELAY": "1",
        # Named rather than left to the default, because switching it on would
        # quietly drop certificate verification.
        "GDAL_HTTP_UNSAFESSL": "NO",
    }


def tile_gdal_options(policy: Policy) -> dict[str, str]:
    """:func:`gdal_options` for the tile routes of `tiler`: serial reads and a cache that holds (NM4-26 §8–§10).

    With ``GDAL_HTTP_MULTIRANGE=YES`` the GeoTIFF driver fetches the blocks of a tile in parallel
    through ``VSICurlHandle::ReadMultiRange`` (GDAL 3.12.2, ``port/cpl_vsil_curl.cpp`` l. 2507–2772),
    which neither reads nor fills the global ``/vsicurl/`` region cache; the bytes it fetched are gone
    when the read ends. The next tile over fetches the same blocks again: 1.72 GB from the source for a
    view of 13 scenes that needs 284 MB. ``SERIAL`` goes through ``VSICurlHandle::Read()`` (l. 2361),
    which reads the cache (l. 2402) and fills it (l. 2350), so each byte is fetched once; the tiles are
    byte-identical (adr/0014 §6.3 is untouched). It only helps with a cache that holds the blocks of a
    view, which is why the size comes with it (:data:`TILER_CURL_CACHE_BYTES`); either alone leaves most of the
    double fetching (measured: 1.75 GB with ``SERIAL`` only, 1.18 GB with the cache only).

    ``rasterio.Env`` sets its options per thread and GDAL reads ``GDAL_HTTP_MULTIRANGE`` at every call, in
    the calling thread (l. 2523). That is what lets the crop of the same process keep ``YES``
    (:func:`crop_gdal_options`). The worker and the runner build on :func:`gdal_options` and are not
    touched by this (``readers.process_gdal_options``).
    """
    return {
        **gdal_options(policy),
        "CPL_VSIL_CURL_CACHE_SIZE": str(TILER_CURL_CACHE_BYTES),
        "GDAL_HTTP_MULTIRANGE": "SERIAL",
    }


def crop_gdal_options(policy: Policy) -> dict[str, str]:
    """:func:`gdal_options` for the AOI crop of `tiler`: the base ``MULTIRANGE`` and the tile cache size.

    A crop reads many blocks at once and gains from fetching them in parallel: measured with
    ``SERIAL`` a 0.3° crop took 17 % longer (NM4-26 §13, §18 point 1). So only the tiles change their
    ``MULTIRANGE`` (:func:`tile_gdal_options`). The cache size is in this profile too, though the crop
    does not use the cache itself: GDAL reads ``CPL_VSIL_CURL_CACHE_SIZE`` once per process (l. 133–214),
    and the first ``/vsicurl/`` access of the process may be a crop, which would fix the 16 MB for the
    tiles after it.
    """
    return {**gdal_options(policy), "CPL_VSIL_CURL_CACHE_SIZE": str(TILER_CURL_CACHE_BYTES)}


def vsicurl_path(checked: CheckedUrl) -> str:
    """Turn a cleared URL into the ``/vsicurl/`` path GDAL reads.

    Takes a :class:`CheckedUrl` on purpose: the only way to hold one is to have
    passed :func:`earthx.gateway.check_url`, so a raw string cannot reach GDAL
    by way of this module. The name stays in the path — GDAL does its own DNS
    and its own TLS, and an address here would break the certificate check.
    """
    if not isinstance(checked, CheckedUrl):
        raise TypeError("a GDAL path is built from a CheckedUrl, not from a plain string")
    return f"/vsicurl/{checked.url}"
