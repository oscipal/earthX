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

**One position for a file with ground control points (adr/0018 F1, DS-04a).** rio-tiler places such a
file with an affine fit through its GCPs, a plain ``WarpedVRT`` with GDAL's polynomial; the two lie up to
kilometres apart (adr/0018 §4.1). :class:`CogReader` therefore opens a GCP file itself, as a ``WarpedVRT``
with a thin-plate spline through the GCPs, and hands that to rio-tiler as its ``dataset``. Tile, crop,
export, mosaic and job all read through ``CogReader.dataset``, so all of them see the same grid. The path
carries the method the registry names; a file that disagrees with it is not read.
"""

from __future__ import annotations

from typing import Literal, get_args

import rasterio
from rasterio.vrt import WarpedVRT
from rio_tiler.io.rasterio import Reader
from rio_tiler.utils import has_alpha_band

from earthx.gateway import GatewayError, Policy, Resolver, check_url, host_of, resolve_host
from earthx.gateway.gdal import vsicurl_path
from earthx.readers.errors import AssetRejected, GeoreferenceMismatch

__all__ = ["AssetPath", "CogReader", "Georeferencing", "asset_host", "asset_path", "warp_options"]

#: How a file is placed; the values of ``earthx.catalog.registry.Georeferencing``, which this module may not import.
Georeferencing = Literal["geotransform", "gcp_tps"]


def warp_options(georeferencing: Georeferencing) -> dict[str, str]:
    """The GDAL transformer options of ``georeferencing`` for a ``WarpedVRT`` over the source file itself."""
    if georeferencing not in get_args(Georeferencing):
        raise ValueError(f"georeferencing is one of {get_args(Georeferencing)}")
    return {"SRC_METHOD": "GCP_TPS"} if georeferencing == "gcp_tps" else {}


class AssetPath(str):
    """A ``/vsicurl/`` path that remembers which asset of which item it is.

    A ``str`` subclass rather than a wrapper, because rio-tiler takes the path as
    a string and passes it on to GDAL; carrying the identity along costs nothing
    and saves `access` from parsing a URL to find out what it is rendering — the
    statistics cache is keyed on these three values (adr/0006 §5 "Zu Frage 3").
    """

    __slots__ = ("asset", "dataset_id", "georeferencing", "item_id")

    def __new__(
        cls,
        path: str,
        *,
        dataset_id: str,
        item_id: str,
        asset: str,
        georeferencing: Georeferencing = "geotransform",
    ) -> AssetPath:
        if georeferencing not in get_args(Georeferencing):
            raise ValueError(f"georeferencing is one of {get_args(Georeferencing)}")
        self = super().__new__(cls, path)
        self.dataset_id = dataset_id
        self.item_id = item_id
        self.asset = asset
        self.georeferencing = georeferencing
        return self


def asset_host(path: AssetPath) -> str | None:
    """The host GDAL asks when it reads ``path``, in the gateway's spelling; ``None`` for a file on disk."""
    if not isinstance(path, AssetPath):
        raise TypeError("the host of a path is read from an AssetPath, not from a plain string")
    prefix = "/vsicurl/"
    return host_of(path[len(prefix) :]) if path.startswith(prefix) else None


def asset_path(
    href: str,
    policy: Policy,
    *,
    dataset_id: str,
    item_id: str,
    asset: str,
    georeferencing: Georeferencing = "geotransform",
    resolve: Resolver = resolve_host,
) -> AssetPath:
    """Clear an asset address and return the path GDAL reads, or raise the reason why not.

    Raises :class:`~earthx.readers.errors.AssetRejected` for whatever
    :func:`earthx.gateway.check_url` refuses — an address on a host the registry
    does not name is the intended end of the road, not an accident (adr/0006 §3.3).
    The refusal of ``check_url`` stays attached as ``__cause__``.

    ``resolve`` is handed on to ``check_url`` unchanged. The tiler passes its
    :class:`~earthx.gateway.CachingResolver` here, because every tile of one item
    otherwise resolves the same asset host again (M2-14); every check around the
    resolution stays exactly where it was.

    ``georeferencing`` is what the registry names for the asset's dataset; it travels with the path to
    :class:`CogReader`.
    """
    try:
        checked = check_url(href, policy, resolve=resolve)
    except GatewayError as error:
        raise AssetRejected(str(error)) from error
    return AssetPath(
        vsicurl_path(checked),
        dataset_id=dataset_id,
        item_id=item_id,
        asset=asset,
        georeferencing=georeferencing,
    )


class CogReader(Reader):
    """rio-tiler's rasterio reader, narrowed to paths that passed the gateway.

    Everything it can do — ``tile``, ``part``, ``feature``, ``preview``,
    ``statistics`` — is rio-tiler's partial read over HTTP range requests. The
    only thing added here is the refusal.

    One exception to "every path comes from ``asset_path``", agreed in adr/0015 §14c:
    ``api/result_tiles.py`` builds the path of a job result from a URL that
    ``earthx.objectstore`` signed. A test lists the places that build an ``AssetPath``.

    The file is opened here rather than by rio-tiler, to check it against ``input.georeferencing``: a
    ``gcp_tps`` file must carry GCPs and is read through a thin-plate spline (module docstring), a
    ``geotransform`` file must not carry them. Either mismatch is :class:`GeoreferenceMismatch`, never a
    silent approximation.
    """

    def __attrs_post_init__(self) -> None:
        if not isinstance(self.input, AssetPath):
            raise TypeError(
                "a COG is opened from an AssetPath built by earthx.readers.cog.asset_path, "
                "not from a plain string (KLAERUNGEN B8)"
            )
        if not self.dataset:
            self.dataset = self._ctx_stack.enter_context(rasterio.open(self.input))
        gcps, gcp_crs = self.dataset.gcps
        if self.input.georeferencing == "gcp_tps":
            if not gcps or gcp_crs is None:
                self._ctx_stack.close()
                raise GeoreferenceMismatch("the registry places this asset by its GCPs, but it carries none")
            self.dataset = self._ctx_stack.enter_context(
                WarpedVRT(self.dataset, crs=gcp_crs, **_gcp_vrt_options(self.dataset))
            )
        elif gcps:
            self._ctx_stack.close()
            raise GeoreferenceMismatch("this asset carries GCPs, but the registry places it by its geotransform")
        super().__attrs_post_init__()


def _gcp_vrt_options(dataset: rasterio.DatasetReader) -> dict[str, object]:
    """rio-tiler's own options for a GCP file (nodata, or an alpha band), with the thin-plate spline."""
    options: dict[str, object] = {"add_alpha": True, **warp_options("gcp_tps")}
    if dataset.nodata is not None:
        options.update(nodata=dataset.nodata, src_nodata=dataset.nodata, add_alpha=False)
    if has_alpha_band(dataset):
        options["add_alpha"] = False
    return options
