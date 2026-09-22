"""Partial Zarr reads on rio-tiler, behind the gateway (adr/0007 §3.7, §6 point 2).

`cog.py` hands an address to GDAL and lets GDAL fetch. A Zarr store has no such
driver here: every chunk is an object under its own address, and something has to
ask for it. That something is this module, and adr/0007 §6 point 2 says exactly
what it may be — an own :class:`zarr.abc.store.Store` whose every ``get`` is one
:class:`~earthx.gateway.Gateway` request. No ``fsspec``, no ``obstore``, no second
HTTP library. That is the one shape which does not merely claim KLAERUNGEN B8 but
enforces it: outside `gateway` no HTTP package is imported at all, which is what
`.importlinter` checks.

On top of the store sits the path adr/0007 §3.7 measured end to end, and nothing
else: ``zarr`` → ``xarray`` → :class:`rio_tiler.io.xarray.XarrayReader`. rio-tiler
is already a dependency and its ``XarrayReader`` does no I/O of its own, so
``tile()``, ``statistics()`` and ``feature()`` — tile, statistic and AOI crop —
come from the same library `cog.py` stands on.

Three properties are deliberate and each has a reason in the ADR:

* **The store never lists.** ``supports_listing`` is ``False``: the names come from
  the catalogue, the store answers with consolidated metadata (§3.10). A store
  without them is refused with :class:`StoreNotReadable` rather than crawled.
* **Byte ranges are mandatory**, not an optimisation (M2-09b's implementation
  conditions, adr/0007 §12.11): a sharded store otherwise hands out the whole
  shard for one tile.
* **Bands are never stacked.** ``to_dataarray``/``to_array`` materialise every
  variable of a group — 1.5 GB in the measurement — so one variable is selected
  and windowed on its own.

The georeferencing comes from the STAC item (``proj:code``) where the store has
none, which is the seam §3.4 describes: the reader hangs on the catalogue, and the
caller says which CRS it read there. Where the store does carry a CRS (the v3
products of §12.3) it is used as it stands.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import attr
import rioxarray  # noqa: F401  — registers the `.rio` accessor this module writes the CRS through
import xarray
import zarr
from rasterio.errors import CRSError
from rio_tiler.io.xarray import XarrayReader
from zarr.abc.store import (
    ByteRequest,
    OffsetByteRequest,
    RangeByteRequest,
    Store,
    SuffixByteRequest,
)
from zarr.core.buffer import Buffer, BufferPrototype, default_buffer_prototype

from earthx.gateway import (
    Gateway,
    Policy,
    Resolver,
    UpstreamError,
    UrlRejected,
    check_url,
    resolve_host,
)

LOGGER = logging.getLogger("earthx.readers.zarr")

__all__ = [
    "GatewayStore",
    "MalformedMultiscales",
    "MissingCrs",
    "StoreNotReadable",
    "UnknownGroup",
    "UnknownVariable",
    "ZarrAsset",
    "ZarrAssetError",
    "ZarrReader",
    "open_gateway",
    "split_asset_href",
    "split_asset_key",
    "zarr_asset",
]

# Set at every open, not left to be probed: a v2 fallback costs a round of requests
# per node (11 instead of 5 in the measurement, adr/0007 §12.11) and the products
# this reader is for are v3.
ZARR_FORMAT = 3

# How an asset address is read: the store is the path segment that ends in this,
# everything after it is the group, the last segment is the variable.
STORE_SUFFIX = ".zarr"

# How long `close` waits for the gateway of a store to shut down on the loop it was
# built on. Generous: it only has to outlast connections that are already idle.
CLOSE_TIMEOUT_S = 5.0


class ZarrAssetError(Exception):
    """This asset cannot be opened, and the reason is known rather than a traceback.

    One base for the four cases the caller can tell apart, because every one of them
    is the source's inconsistency rather than the caller's mistake: an item that
    names a group the store does not have (adr/0007 §3.5 measured exactly that), a
    group without the variable, a store that cannot be read without listing it, and
    data nothing says how to georeference.
    """


class UnknownGroup(ZarrAssetError):
    """The store has no group at the address the item points at."""


class UnknownVariable(ZarrAssetError):
    """The group opened, but it carries no variable under that name."""


class StoreNotReadable(ZarrAssetError):
    """The store carries no consolidated metadata, and this reader does not list."""


class MissingCrs(ZarrAssetError):
    """Neither the item nor the store says which coordinate reference system this is."""


class MalformedMultiscales(ZarrAssetError):
    """`multiscales` is there, but its `layout` is not the shape §12.3 measured.

    A broken pilot convention (adr/0007 §12.11 point 2 — v0.1, breaking changes
    announced) must not turn into a guess at which level is meant: this is a
    defined failure of the *level choice*, not of the read path underneath it.
    """


def open_gateway(policy: Policy, resolve: Resolver) -> Gateway:
    """The gateway a store fetches through. The seam tests take the network out at.

    A function rather than a constructor argument of the store, because the store is
    built deep inside :class:`ZarrReader` from a :class:`ZarrAsset` and nothing in
    between would carry a transport through — the same reason `cog.py` leaves
    ``check_url`` patchable.
    """
    return Gateway(policy, resolve=resolve)


class GatewayStore(Store):
    """A read-only Zarr store in which one key is one gateway request.

    Read-only in every sense the base class offers: ``set`` and ``delete`` raise, and
    so does every listing method — ``supports_listing`` is ``False`` and the metadata
    has to be consolidated (adr/0007 §3.10). A key the source does not have comes
    back as ``None``, because zarr probes for keys that need not exist.
    """

    def __init__(self, base_url: str, policy: Policy, *, resolve: Resolver = resolve_host) -> None:
        super().__init__(read_only=True)
        self._base_url = base_url.rstrip("/")
        self._policy = policy
        self._resolve = resolve
        self._gateway: Gateway | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        #: Every request this store has made. Read by the tests that show that the
        #: bytes arrive through `gateway` and by nothing else.
        self.request_count = 0

    def __repr__(self) -> str:
        # Without the address: an error or a log line that quotes it would carry the
        # source's URL into places projektplan.md 7 keeps it out of.
        return f"{type(self).__name__}(requests={self.request_count})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, GatewayStore) and other._base_url == self._base_url

    def __hash__(self) -> int:
        return hash((type(self), self._base_url))

    @property
    def supports_writes(self) -> bool:
        return False

    @property
    def supports_deletes(self) -> bool:
        return False

    @property
    def supports_listing(self) -> bool:
        return False

    async def get(
        self,
        key: str,
        prototype: BufferPrototype,
        byte_range: ByteRequest | None = None,
    ) -> Buffer | None:
        """One key, one gateway request — and the gateway checks the address again.

        The check is not done once at the store and then trusted: ``Gateway.get``
        runs ``check_url`` on every call, so a redirect or a key that escapes the
        prefix is refused where it is fetched, not where it was planned.
        """
        gateway = await self._gateway_for_this_loop()
        self.request_count += 1
        try:
            response = await gateway.get(f"{self._base_url}/{key}", headers=_range_header(byte_range))
        except UpstreamError as error:
            if error.status_code == 404:
                return None
            raise
        return prototype.buffer.from_bytes(response.content)

    async def get_partial_values(
        self,
        prototype: BufferPrototype,
        key_ranges: Iterable[tuple[str, ByteRequest | None]],
    ) -> list[Buffer | None]:
        """The ranges of a sharded read, concurrently — the gateway caps the host itself."""
        return list(
            await asyncio.gather(*(self.get(key, prototype, byte_range) for key, byte_range in key_ranges))
        )

    async def exists(self, key: str) -> bool:
        """Ask for the first byte rather than the object: existence is not a download."""
        try:
            return await self.get(key, default_buffer_prototype(), RangeByteRequest(0, 1)) is not None
        except UpstreamError as error:
            # 416 means the object is there and shorter than the range asked for.
            if error.status_code == 416:
                return True
            raise

    async def set(self, key: str, value: Buffer) -> None:
        raise NotImplementedError("a gateway store reads; the platform never writes to a source")

    async def delete(self, key: str) -> None:
        raise NotImplementedError("a gateway store reads; the platform never writes to a source")

    def list(self) -> Any:
        raise NotImplementedError(_NO_LISTING)

    def list_prefix(self, prefix: str) -> Any:
        raise NotImplementedError(_NO_LISTING)

    def list_dir(self, prefix: str) -> Any:
        raise NotImplementedError(_NO_LISTING)

    def close(self) -> None:
        """Shut the HTTP client down, on whichever loop it was built on."""
        gateway, loop = self._gateway, self._loop
        self._gateway, self._loop = None, None
        if gateway is not None and loop is not None and not loop.is_closed():
            _close_gateway_on(loop, gateway)
        super().close()

    async def _gateway_for_this_loop(self) -> Gateway:
        """One client for the life of the store, built where it will be used.

        zarr drives every store call on an event loop of its own, in a thread of its
        own (``zarr.core.sync``), and an ``httpx`` client belongs to the loop it first
        ran on. So it is built here, at the first read, rather than by the caller —
        and rebuilt in the unlikely case that a second loop ever uses this store.
        """
        loop = asyncio.get_running_loop()
        if self._gateway is not None and self._loop is loop:
            return self._gateway
        if self._gateway is not None and self._loop is not None:
            _close_gateway_on(self._loop, self._gateway)
        self._gateway = open_gateway(self._policy, self._resolve)
        self._loop = loop
        return self._gateway


_NO_LISTING = (
    "this store does not list: the names come from the catalogue and the store answers "
    "with consolidated metadata (adr/0007 §3.10)"
)


def _range_header(byte_range: ByteRequest | None) -> dict[str, str] | None:
    """zarr's three range requests as the one HTTP header that carries them."""
    if byte_range is None:
        return None
    if isinstance(byte_range, RangeByteRequest):
        # zarr's end is exclusive, HTTP's last byte position is inclusive.
        return {"Range": f"bytes={byte_range.start}-{byte_range.end - 1}"}
    if isinstance(byte_range, OffsetByteRequest):
        return {"Range": f"bytes={byte_range.offset}-"}
    if isinstance(byte_range, SuffixByteRequest):
        return {"Range": f"bytes=-{byte_range.suffix}"}
    raise TypeError(f"zarr asked for a byte range this store does not know: {type(byte_range).__name__}")


def _close_gateway_on(loop: asyncio.AbstractEventLoop, gateway: Gateway) -> None:
    """Close a client that lives on another thread's loop, from this thread."""
    try:
        running: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is loop:
        loop.create_task(gateway.aclose())
        return
    try:
        asyncio.run_coroutine_threadsafe(gateway.aclose(), loop).result(timeout=CLOSE_TIMEOUT_S)
    except (RuntimeError, TimeoutError):
        # The answer is already in hand; a client that will not shut down costs
        # sockets until the process ends, and is not worth failing a request over.
        LOGGER.warning("the zarr store's gateway did not close", exc_info=True)


@dataclass(frozen=True, slots=True)
class ZarrAsset:
    """One variable of one Zarr group, at an address the gateway has cleared.

    The counterpart of :class:`~earthx.readers.cog.AssetPath`, and it carries more
    than a path because the reader fetches for itself: ``policy`` and ``resolve``
    are what every later chunk request is checked against, so there is no way to
    open this asset that bypasses them.

    ``group`` is the path of the group inside the store, empty for the store's own
    root group. It is separate from ``store_url`` because consolidated metadata sits
    at the root of a store, not at each group (measured: that is where ``zarr``
    writes it, and where the EOPF products carry their 4.55 MB of it, §3.4).

    ``crs`` is the CRS the *catalogue* read off the item (``proj:code``). ``None``
    means the store is expected to carry its own; if neither does, opening raises
    :class:`MissingCrs` instead of guessing (adr/0007 §3.4).

    ``target_gsd`` is the ground sample distance, in the units of the store's own
    CRS, a read would like to see — ``None`` leaves ``group`` exactly as given
    (M2-09a, and every caller that does not compute one); a number picks the
    coarsest ``multiscales`` level whose resolution is still at least that fine,
    or the finest level there is if none is (adr/0007 §12.10, §12.11 point 2).
    Read by the reader, not by this module — see ``readers.zarr_reader._open_group``.
    """

    store_url: str
    group: str
    variable: str
    crs: str | None
    policy: Policy
    resolve: Resolver
    dataset_id: str
    item_id: str
    asset: str
    target_gsd: float | None = None


def split_asset_href(href: str, *, variable: str | None = None) -> tuple[str, str, str]:
    """An asset address as store, group and variable — the three things opening needs.

    **The store is the path segment that ends in ``.zarr``.** What comes after it is
    the group; which part of that is the group and which the variable depends on
    ``variable``:

    * **without one** (the default), the **last segment is the variable** and
      everything between the store and it is the group — how the M2-09a synthetic
      store and the EOPF v2 tutorial product point at their data: the asset
      ``…/S2A_….zarr/quality/l2a_quicklook/r10m/tci`` names the array ``tci`` in the
      group ``quality/l2a_quicklook/r10m``.
    * **given one**, the whole path after the store is the group and ``variable`` is
      used as it stands — the ``sentinel-2-l2a-zarr3`` shape (§3.2 of the M2-09b
      plan): the asset ``SR_10m`` points at the *group*
      ``measurements/reflectance/r10m``, not at one variable inside it, and the
      catalogue's ``ZarrInfo.variable_separator`` is what splits a tile URL's asset
      key into this asset and this variable (:func:`split_asset_key`).

    None of the three parts can be guessed from another:

    * the **store** is what consolidated metadata belongs to — it sits at the store's
      root, not at each group, so a reader that took the group for the store would
      have to list (§3.4, §3.10);
    * the **group** is what carries the ``x``/``y`` coordinate arrays that
      georeference the variable; they are its siblings, not its children;
    * the **variable** is the one band that gets read, never all of them.
    """
    if variable is not None:
        segments = href.rstrip("/").split("/")
        for index in range(len(segments) - 1, -1, -1):
            if segments[index].endswith(STORE_SUFFIX):
                return "/".join(segments[: index + 1]), "/".join(segments[index + 1 :]), variable
        raise UrlRejected(
            f"a Zarr asset address names its store with a path segment ending in {STORE_SUFFIX!r}"
        )
    head, _, tail_variable = href.rstrip("/").rpartition("/")
    segments = head.split("/")
    for index in range(len(segments) - 1, -1, -1):
        if segments[index].endswith(STORE_SUFFIX):
            return "/".join(segments[: index + 1]), "/".join(segments[index + 1 :]), tail_variable
    raise UrlRejected(
        f"a Zarr asset address names its store with a path segment ending in {STORE_SUFFIX!r}, "
        "and its variable as the last segment"
    )


def split_asset_key(asset_key: str, separator: str | None) -> tuple[str, str | None]:
    """The item's own asset key, and the variable inside it, from a tile URL's asset key.

    **Without a separator** (``ZarrInfo.variable_separator`` is ``None``), ``asset_key``
    is the item's own asset key, unchanged, and there is nothing to read separately —
    the href's own last path segment names the variable, exactly as
    :func:`split_asset_href` reads it without one (M2-09a).

    **With one**, ``asset_key`` is ``"<item asset key><separator><variable>"`` —
    measured for ``sentinel-2-l2a-zarr3`` (plan §10 F2): a key ``"SR_10m:b04"`` with
    separator ``":"`` names the item asset ``SR_10m`` and, inside the group its href
    points at, the variable ``b04``.
    """
    if separator is None:
        return asset_key, None
    item_asset, sep, variable = asset_key.partition(separator)
    if not sep or not item_asset or not variable:
        raise UrlRejected(
            f"asset {asset_key!r} does not name a variable; this dataset addresses a group "
            f"asset as '<asset>{separator}<variable>'"
        )
    return item_asset, variable


def zarr_asset(
    href: str,
    policy: Policy,
    *,
    dataset_id: str,
    item_id: str,
    asset: str,
    crs: str | None = None,
    resolve: Resolver = resolve_host,
    variable: str | None = None,
    target_gsd: float | None = None,
) -> ZarrAsset:
    """Clear an asset address and return what the reader opens, or raise the reason why not.

    Raises whatever :func:`earthx.gateway.check_url` raises, and
    :class:`~earthx.gateway.UrlRejected` for an address
    :func:`split_asset_href` cannot read. The refusal happens here and not at the
    first chunk, so an address on a host the registry does not name costs no request
    at all.

    ``variable`` and ``target_gsd`` pass straight through to :func:`split_asset_href`
    and :class:`ZarrAsset` — see there for what each one changes.
    """
    store_url, group, resolved_variable = split_asset_href(href, variable=variable)
    if not resolved_variable:
        raise UrlRejected("a Zarr asset address ends in the name of the variable to read")
    check_url(store_url, policy, resolve=resolve)
    return ZarrAsset(
        store_url=store_url,
        group=group,
        variable=resolved_variable,
        crs=crs,
        policy=policy,
        resolve=resolve,
        dataset_id=dataset_id,
        item_id=item_id,
        asset=asset,
        target_gsd=target_gsd,
    )


@attr.s
class ZarrReader(XarrayReader):
    """rio-tiler's Xarray reader, over a Zarr asset it opens through the gateway.

    Takes a :class:`ZarrAsset` where ``XarrayReader`` takes a ``DataArray``: it
    opens the group, selects the one variable and hands the parent what it expects.
    Everything the reader can then do — ``tile``, ``part``, ``feature``,
    ``preview``, ``statistics`` — is rio-tiler's, over windows that pull only the
    chunks they touch.

    Refuses a plain string for the same reason :class:`~earthx.readers.cog.CogReader`
    does: a reader that can be handed an address is a reader that can be pointed
    anywhere (KLAERUNGEN B8).
    """

    _store: GatewayStore | None = attr.ib(init=False, default=None)
    _dataset: xarray.Dataset | None = attr.ib(init=False, default=None)

    def __attrs_post_init__(self) -> None:
        asset = self.input
        if not isinstance(asset, ZarrAsset):
            raise TypeError(
                "a Zarr asset is opened from a ZarrAsset built by "
                "earthx.readers.zarr_reader.zarr_asset, not from a plain string (KLAERUNGEN B8)"
            )
        store = GatewayStore(asset.store_url, asset.policy, resolve=asset.resolve)
        try:
            dataset = _open_group(store, asset)
        except BaseException:
            store.close()
            raise
        try:
            self.input = _select_variable(dataset, asset)
        except BaseException:
            dataset.close()
            store.close()
            raise
        self._store = store
        self._dataset = dataset
        super().__attrs_post_init__()

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def close(self) -> None:
        """Let the dataset and the HTTP client go. Safe to call twice."""
        if self._dataset is not None:
            self._dataset.close()
            self._dataset = None
        if self._store is not None:
            self._store.close()
            self._store = None


def _open_group(store: GatewayStore, asset: ZarrAsset) -> xarray.Dataset:
    """The group ``_resolved_group`` picks, or the defined reason it cannot be opened.

    ``chunks=None`` keeps xarray's own lazy indexing rather than bringing dask in:
    a window then reads the chunks it overlaps and nothing else, which is the whole
    point of a partial read.
    """
    group = _resolved_group(store, asset)
    try:
        return xarray.open_zarr(
            store,
            group=group or None,
            consolidated=True,
            zarr_format=ZARR_FORMAT,
            decode_coords="all",
            chunks=None,
        )
    except (KeyError, FileNotFoundError):
        raise UnknownGroup(
            f"{asset.dataset_id}/{asset.item_id}: asset {asset.asset!r} points at a group "
            "the store does not have"
        ) from None
    except ValueError as error:
        raise StoreNotReadable(
            f"{asset.dataset_id}/{asset.item_id}: the store behind asset {asset.asset!r} "
            f"cannot be opened without listing it ({error})"
        ) from None


def _resolved_group(store: GatewayStore, asset: ZarrAsset) -> str:
    """The group to open: a level ``multiscales`` picks for ``asset.target_gsd``,
    or the group the item's asset names when there is nothing to pick from.

    ``multiscales`` sits on the *parent* of the resolution groups, not on a group
    itself (measured at ``measurements/reflectance``, adr/0007 §12.3) — read there,
    against ``asset.group``'s own parent. Its absence is not a failure: the store
    the item names (§6 point 2) or the M2-09a synthetic Mini-Zarr have none, and
    the group the asset already names is exactly what a v3 layout without a level
    to pick would read anyway (adr/0007 §12.11 point 2's fallback).
    """
    if asset.target_gsd is None:
        return asset.group
    layout = _multiscales_layout(store, asset.group)
    if layout is None:
        return asset.group
    level = _select_level(
        layout, asset.target_gsd, dataset_id=asset.dataset_id, item_id=asset.item_id, asset=asset.asset
    )
    parent, _, _ = asset.group.rpartition("/")
    return f"{parent}/{level}" if parent else level


def _multiscales_layout(store: GatewayStore, group: str) -> list[Any] | None:
    """The ``layout`` of the parent's ``multiscales`` attribute, or ``None`` for none.

    A group that cannot even be opened is read the same as one without the
    attribute: both mean there is nothing here to pick a level from, and the
    caller falls back to the group the asset names either way.
    """
    parent, _, _ = group.rpartition("/")
    try:
        node = zarr.open_group(store=store, mode="r", path=parent or None, zarr_format=ZARR_FORMAT)
    except (KeyError, FileNotFoundError, ValueError):
        return None
    multiscales = node.attrs.get("multiscales")
    if not isinstance(multiscales, dict):
        return None
    layout = multiscales.get("layout")
    return layout if isinstance(layout, list) else None


def _select_level(
    layout: list[Any], target_gsd: float, *, dataset_id: str, item_id: str, asset: str
) -> str:
    """The coarsest ``multiscales`` level whose resolution is still at least
    ``target_gsd``-fine, or the finest level there is if none is that fine
    (adr/0007 §12.10: computed from the requested resolution, never looked up in a
    fixed zoom table — a Web Mercator tile's real ground resolution depends on
    latitude, so a table would read the wrong level near either end of the extent).

    The resolution of a level is the first element of its ``spatial:transform``
    (§12.3, measured: the affine's pixel width, in the store's own CRS units).
    """
    levels: list[tuple[float, str]] = []
    for entry in layout:
        name = entry.get("asset") if isinstance(entry, dict) else None
        transform = entry.get("spatial:transform") if isinstance(entry, dict) else None
        if not isinstance(name, str) or not name or not isinstance(transform, list) or not transform:
            raise MalformedMultiscales(
                f"{dataset_id}/{item_id}: asset {asset!r}'s multiscales layout has an entry "
                "without both 'asset' and a non-empty 'spatial:transform'"
            )
        try:
            gsd = abs(float(transform[0]))
        except (TypeError, ValueError):
            raise MalformedMultiscales(
                f"{dataset_id}/{item_id}: asset {asset!r} names a multiscales level "
                f"{name!r} whose 'spatial:transform' does not start with a number"
            ) from None
        levels.append((gsd, name))
    if not levels:
        raise MalformedMultiscales(f"{dataset_id}/{item_id}: asset {asset!r} has an empty multiscales layout")
    levels.sort(key=lambda pair: pair[0])
    fine_enough = [name for gsd, name in levels if gsd <= target_gsd]
    return fine_enough[-1] if fine_enough else levels[0][1]


def _select_variable(dataset: xarray.Dataset, asset: ZarrAsset) -> xarray.DataArray:
    """One variable, georeferenced — never every variable of the group stacked.

    ``to_dataarray``/``to_array`` would read all of them (1.5 GB in the measurement
    of adr/0007 §12.11); the tile path wants one band at a time and says so.
    """
    if asset.variable not in dataset.data_vars:
        raise UnknownVariable(
            f"{asset.dataset_id}/{asset.item_id}: asset {asset.asset!r} names the variable "
            f"{asset.variable!r}, which this group does not carry"
        )
    array = dataset[asset.variable]
    # The store wins where it carries one, the item is the fallback: adr/0007 §12.11
    # point 3 measured the two agreeing in the v3 products, and §3.4 measured a store
    # with no CRS at all. Writing the item's over a store's would make the catalogue
    # able to move data that says where it is.
    if array.rio.crs is None and asset.crs is not None:
        try:
            array = array.rio.write_crs(asset.crs)
        except (CRSError, ValueError):
            raise MissingCrs(
                f"{asset.dataset_id}/{asset.item_id}: {asset.crs!r} is not a usable "
                "coordinate reference system"
            ) from None
    if array.rio.crs is None:
        raise MissingCrs(
            f"{asset.dataset_id}/{asset.item_id}: neither the item (proj:code) nor the store "
            "says which coordinate reference system this asset is in (adr/0007 §3.4)"
        )
    return array
