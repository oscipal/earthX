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
