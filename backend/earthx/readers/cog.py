"""Partial COG reads on rio-tiler, behind the gateway (adr/0006 §5.1).

This module is the place where an asset address becomes something GDAL may open,
and it is the only one: `access` renders and `api` resolves, but neither of them
builds a path. KLAERUNGEN B8 asks for exactly that — one place that decides
whether an address may be fetched — and adr/0006 §3.3 names the two properties
that make the promise checkable rather than merely stated:

* **Every address passes ``check_url``.** :func:`asset_path` is the only way to
  build an :class:`AssetPath`, and it has no branch that skips the check.
* **A plain string cannot become a dataset.** :class:`CogReader` refuses anything
  but an :class:`AssetPath`, so even a factory whose path dependency was replaced
  by a free ``url`` parameter would open nothing.

Only ``https``: ``gateway.inspect_url`` refuses every other scheme, so ``s3://``
never gets here (adr/0006 §5 "Zu Frage 6"). What this module cannot do is take
the socket away from GDAL; B8 says so, and the network policy of M6 is what
closes it.
"""

from __future__ import annotations

from rio_tiler.io.rasterio import Reader

from earthx.gateway import Policy, check_url
from earthx.gateway.gdal import vsicurl_path

__all__ = ["AssetPath", "CogReader", "asset_path"]


class AssetPath(str):
    """A ``/vsicurl/`` path that remembers which asset of which item it is.

    A ``str`` subclass rather than a wrapper, because rio-tiler takes the path as
    a string and passes it on to GDAL; carrying the identity along costs nothing
    and saves `access` from parsing a URL to find out what it is rendering — the
    statistics cache is keyed on these three values (adr/0006 §5 "Zu Frage 3").
    """

    __slots__ = ("asset", "dataset_id", "item_id")

    def __new__(cls, path: str, *, dataset_id: str, item_id: str, asset: str) -> AssetPath:
        self = super().__new__(cls, path)
        self.dataset_id = dataset_id
        self.item_id = item_id
        self.asset = asset
        return self


def asset_path(href: str, policy: Policy, *, dataset_id: str, item_id: str, asset: str) -> AssetPath:
    """Clear an asset address and return the path GDAL reads, or raise the reason why not.

    Raises whatever :func:`earthx.gateway.check_url` raises — an address on a host
    the registry does not name is a ``UrlRejected``, and that is the intended end
    of the road, not an accident (adr/0006 §3.3).
    """
    return AssetPath(
        vsicurl_path(check_url(href, policy)),
        dataset_id=dataset_id,
        item_id=item_id,
        asset=asset,
    )


class CogReader(Reader):
    """rio-tiler's rasterio reader, narrowed to paths that passed the gateway.

    Everything it can do — ``tile``, ``part``, ``feature``, ``preview``,
    ``statistics`` — is rio-tiler's partial read over HTTP range requests. The
    only thing added here is the refusal.
    """

    def __attrs_post_init__(self) -> None:
        if not isinstance(self.input, AssetPath):
            raise TypeError(
                "a COG is opened from an AssetPath built by earthx.readers.cog.asset_path, "
                "not from a plain string (KLAERUNGEN B8)"
            )
        super().__attrs_post_init__()
