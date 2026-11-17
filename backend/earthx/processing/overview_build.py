"""The build of one overview pyramid in the child: items in, tiles out, in the work directory (M5-30b part 8b-2, adr/0032 §5.2).

The work directory is the whole interface (KLAERUNGEN B9: no database, no queue, no object store here). `jobs` writes
into it what it read from the database and the store, starts a child, and uploads what the child leaves:

* ``items.jsonl`` and ``job.json`` (``dataset_id``, the asset ``hosts`` the registry names, ``reuse``) come in;
* ``plan.json`` is what the first step (:func:`plan_pyramid`) leaves: the base tiles and the hash of the items each one
  reads, without a single read at the source, so `jobs` can fetch the tiles of the last version that are still good;
* ``tiles/{z}/{x}/{y}.tif`` is what the second step (:func:`build_pyramid`) leaves, with ``manifest.json``. A base
  tile that `jobs` put there beforehand (its key is in ``reuse``) is neither read nor written again, only decoded for the
  levels above.

**Levels.** The base level is one below the first level the tiles are drawn from: the registry's ``viewer.min_zoom``
(GLO-30 7, WorldCover 5; part 9 of plan M5-30b moved them there from a constant of this module). Every level above is
made from four tiles below it.

**Which files.** A base tile reads the items whose bounding box meets it, in the order of their ids, the first valid
pixel winning (the datasets of a pyramid tile the globe without overlap). The first asset of the default render that an
item carries is the one read, cleared through the policy of `readers` against the hosts the registry names.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import morecantile
import numpy as np
from rasterio.errors import CRSError, RasterioError
from rio_tiler.errors import RioTilerError

from earthx.access.resolve import open_asset_ref, resolve_asset
from earthx.catalog.datasets import registry as default_registry
from earthx.catalog.registry import DatasetConfig, DatasetRegistry, OverviewMode
from earthx.processing import overview
from earthx.readers import source_failure_kind
from earthx.readers.access import check_hrefs, host_pacer, overview_host_interval, read_access_for
from earthx.readers.cog import AssetPath

__all__ = [
    "ITEMS_NAME",
    "JOB_NAME",
    "MANIFEST_NAME",
    "PLAN_NAME",
    "TILES_DIR",
    "MAX_OMITTED",
    "MAX_OMITTED_FRACTION",
    "TILE_ATTRIBUTE",
    "describe",
    "patch_pyramid",
    "build_pyramid",
    "plan_patch",
    "plan_pyramid",
    "pyramid_hosts",
    "tile_hash",
    "tile_path",
]

ITEMS_NAME = "items.jsonl"
JOB_NAME = "job.json"
PLAN_NAME = "plan.json"
MANIFEST_NAME = "manifest.json"
TILES_DIR = "tiles"

_TMS = morecantile.tms.get("WebMercatorQuad")
Progress = Callable[[int, int], None]


def pyramid_hosts(registry: DatasetRegistry | None = None) -> dict[str, tuple[str, ...]]:
    """The datasets with ``viewer.overview: pyramid`` and the hosts each reads from: plain data for the supervisor.

    A dataset with no level to build from (a ``min_zoom`` below 1) raises ``ValueError``, so the worker does not start with an
    entry it could never build (the same loudness as the other checks of its start).
    """
    found: dict[str, tuple[str, ...]] = {}
    for config in registry if registry is not None else default_registry():
        if config.viewer is not None and config.viewer.overview is OverviewMode.PYRAMID:
            try:
                overview.base_zoom(config.viewer.min_zoom)
            except ValueError:
                raise ValueError(f"{config.dataset_id}: a pyramid needs a viewer.min_zoom of 1 or more") from None
            found[config.dataset_id] = tuple(config.source.asset_hosts)
    return found


def pyramid_source_limits(registry: DatasetRegistry | None = None) -> dict[str, tuple[int, float]]:
    """Each host a pyramid reads, with its cap and the spacing of a build: plain data for the supervisor (M5-37).

    Cap and spacing come from ``hosts.yaml``; a host without a spacing there gets the build's own,
    ``EARTHX_OVERVIEW_HOST_INTERVAL_S`` (0.25 s, adr/0032 F4). A bad value of that variable raises ``ValueError`` naming it.
    """
    datasets = registry if registry is not None else default_registry()
    default = overview_host_interval()
    limits = datasets.host_limits
    found: dict[str, tuple[int, float]] = {}
    for hosts in pyramid_hosts(datasets).values():
        for host in hosts:
            limit = limits.get(host)
            if limit is None:
                raise ValueError(f"{host}: a host a pyramid reads needs an entry in hosts.yaml")
            found[host] = (limit.connections, default if limit.interval_s is None else limit.interval_s)
    return found


def tile_path(workdir: Path, z: int, x: int, y: int) -> Path:
    return workdir / TILES_DIR / str(z) / str(x) / f"{y}.tif"


def _job(workdir: Path) -> dict[str, Any]:
    job = json.loads((workdir / JOB_NAME).read_text(encoding="utf-8"))
    if not isinstance(job, dict) or not isinstance(job.get("dataset_id"), str):
        raise ValueError("job.json names a dataset")
    return job


def _items(workdir: Path) -> list[dict[str, Any]]:
    with (workdir / ITEMS_NAME).open(encoding="utf-8") as lines:
        items = [json.loads(line) for line in lines if line.strip()]
    if not items:
        raise ValueError("a pyramid is built from at least one item")
    return sorted(items, key=lambda item: str(item.get("id")))


def _config(dataset_id: str, registry: DatasetRegistry | None) -> tuple[DatasetConfig, int]:
    config = (registry if registry is not None else default_registry()).get(dataset_id)
    if config.viewer is None or config.viewer.overview is not OverviewMode.PYRAMID or config.viewer.overview_resampling is None:
        raise ValueError(f"{dataset_id}: no overview pyramid in the registry")
    return config, overview.base_zoom(config.viewer.min_zoom)


def _bbox(item: Mapping[str, Any]) -> tuple[float, float, float, float]:
    box = item.get("bbox")
    if not isinstance(box, list) or len(box) != 4 or not all(isinstance(n, int | float) for n in box):
        raise ValueError("an item of a pyramid carries a bbox of four numbers")
    return float(box[0]), float(box[1]), float(box[2]), float(box[3])


def base_tiles(items: Sequence[Mapping[str, Any]], zoom: int) -> dict[morecantile.Tile, list[Mapping[str, Any]]]:
    """The tiles at ``zoom`` that items touch, each with its items in the order given, tiles in grid order."""
    found: dict[morecantile.Tile, list[Mapping[str, Any]]] = {}
    for item in items:
        west, south, east, north = _bbox(item)
        for tile in _TMS.tiles(west, south, east, north, [zoom], truncate=True):
            found.setdefault(tile, []).append(item)
    return dict(sorted(found.items(), key=lambda pair: (pair[0].y, pair[0].x)))


def tile_hash(
    items: Sequence[Mapping[str, Any]], *, zoom: int, config: DatasetConfig
) -> str | None:
    """What decides that a stored base tile may be reused: the hash of its items (:func:`overview.base_hash`), the level
    it lies at, the resampling and the assets read.

    A tile of another level, made with another resampling or from another asset is never the same tile, whatever its
    items say: a change of ``min_zoom`` (part 9) or of ``overview_resampling`` in the registry must not let an old tile
    through. ``None`` where the items give no hash.
    """
    digest = overview.base_hash(items)
    if digest is None:
        return None
    assert config.viewer is not None and config.viewer.overview_resampling is not None
    assert config.default_render is not None
    salt = f"{digest}|z{zoom}|{config.viewer.overview_resampling.value}|{','.join(config.default_render.assets)}"
    return hashlib.sha256(salt.encode()).hexdigest()


def plan_pyramid(workdir: Path, *, registry: DatasetRegistry | None = None) -> dict[str, Any]:
    """Write ``plan.json``: the base level and, per base tile ``x/y``, the hash of its items (``null`` without ``updated``)."""
    job = _job(workdir)
    config, base = _config(job["dataset_id"], registry)
    tiles = {
        f"{tile.x}/{tile.y}": tile_hash(members, zoom=base, config=config)
        for tile, members in base_tiles(_items(workdir), base).items()
    }
    plan = {"base_zoom": base, "tiles": tiles}
    (workdir / PLAN_NAME).write_text(json.dumps(plan), encoding="utf-8")
    return plan


def plan_patch(workdir: Path, *, registry: DatasetRegistry | None = None) -> dict[str, Any]:
    """Write ``plan.json`` for a retry: the base level and ``fetch``, the ``z/x/y`` of the stored tiles the levels above the
    omitted base tiles (``only`` in ``job.json``, ``x/y``) are made from: the siblings of each tile on the way up to z0.

    No source is read. The tiles on the way themselves are made again, so they are not fetched (unless they are the sibling
    of another tile of the retry, which is made again after them).
    """
    job = _job(workdir)
    _, base = _config(job["dataset_id"], registry)
    fetch: dict[str, None] = {}
    for key in job.get("only", []):
        x, y = (int(part) for part in str(key).split("/"))
        for z in range(base, 0, -1):
            px, py = x // 2, y // 2
            for child in overview.children_of(morecantile.Tile(px, py, z - 1)):
                if (child.x, child.y) != (x, y):
                    fetch[f"{child.z}/{child.x}/{child.y}"] = None
            x, y = px, py
    plan = {"base_zoom": base, "fetch": list(fetch)}
    (workdir / PLAN_NAME).write_text(json.dumps(plan), encoding="utf-8")
    return plan


def _scenes(
    config: DatasetConfig, hosts: Sequence[str], items: Sequence[Mapping[str, Any]]
) -> dict[str, AssetPath]:
    """Every item as a cleared path, by id; one item without a readable asset fails the build, as a file left out would."""
    assert config.default_render is not None
    keys = config.default_render.assets
    chosen: dict[str, tuple[Mapping[str, Any], str]] = {}
    for item in items:
        assets = item.get("assets") or {}
        key = next((key for key in keys if key in assets), None)
        if key is None:
            raise ValueError("an item of a pyramid carries none of the assets of the default render")
        chosen[str(item["id"])] = (item, key)
    hrefs = [str(item["assets"][key]["href"]) for item, key in chosen.values()]
    check_hrefs(hrefs, hosts)
    access = read_access_for(hrefs)
    return {
        item_id: open_asset_ref(resolve_asset(item, config, key), access.policy, access.resolve)  # type: ignore[misc]
        for item_id, (item, key) in chosen.items()
    }


#: The attribute a failure carries to say which tile it happened at (``z/x/y``, never an address or an item); `jobs` logs it.
TILE_ATTRIBUTE = "earthx_tile"


@contextlib.contextmanager
def _at(tile: morecantile.Tile) -> Iterator[None]:
    """Whatever is raised inside names the tile it happened at, as ``earthx_tile``, and goes on."""
    try:
        yield
    except Exception as error:
        if not hasattr(error, TILE_ATTRIBUTE):
            with contextlib.suppress(AttributeError):  # an exception class without a ``__dict__`` keeps no note
                setattr(error, TILE_ATTRIBUTE, f"{tile.z}/{tile.x}/{tile.y}")
        raise


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _parents(children: Sequence[morecantile.Tile]) -> list[morecantile.Tile]:
    return sorted({morecantile.Tile(c.x // 2, c.y // 2, c.z - 1) for c in children}, key=lambda t: (t.y, t.x))


#: A build whose omitted base tiles exceed both this share of all base tiles and :data:`MAX_OMITTED` is no pyramid with a gap but
#: an outage (the source down, a bad address): it fails with the kind of the last failure instead of ending ``ready`` empty.
MAX_OMITTED_FRACTION = 0.05
MAX_OMITTED = 3
#: What the table keeps of a reason, in characters.
REASON_LENGTH = 160
# A URL (with the GDAL prefix it may be read through), then any other absolute path, then a bare host or file name; in this
# order, or a ``/vsicurl/`` is cut at the colon and leaves the host behind.
_URL = re.compile(r"(?:/vsi\w+/)?[A-Za-z][A-Za-z0-9+.\-]*://\S+")
_PATH = re.compile(r"(?<![\w.])/[\w.\-%~/]+")
_HOST = re.compile(r"\b[A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_\-]+)*\.[A-Za-z]{2,}\b")


def describe(error: BaseException) -> dict[str, str]:
    """What is kept of a failure: its class, and a short reason with every URL, path and host name taken out.

    A lookup error has no reason: its message is the key that was missing, which can be an item's id. The tile it
    happened at (:data:`TILE_ATTRIBUTE`) is added where the failure carries one.
    """
    reason = "" if isinstance(error, LookupError) else " ".join(_HOST.sub("<address>", _PATH.sub("<address>", _URL.sub("<address>", str(error)))).split())
    detail = {"error": type(error).__name__, "reason": reason[:REASON_LENGTH]}
    tile = getattr(error, TILE_ATTRIBUTE, None)
    if isinstance(tile, str):
        detail["tile"] = tile
    return detail


def _one_file_failed(error: Exception) -> bool:
    """Whether ``error`` is the failure of reading one source file (after the reads were repeated): that base tile is omitted.

    That is what rasterio and rio-tiler raise for a file (a read that failed, a file that is no raster, a warp that could not
    be done, a bounds error) and what `readers` names a source failure. Anything else (a full disk, a bug of ours, memory)
    is not about a file and fails the build.
    """
    return isinstance(error, (RasterioError, CRSError, RioTilerError)) or source_failure_kind(error) is not None


def _omission(error: Exception) -> dict[str, str]:
    return {"kind": source_failure_kind(error) or "unreadable", **describe(error)}


def _too_many(omitted: Mapping[str, Any], planned: int) -> bool:
    return len(omitted) > MAX_OMITTED and len(omitted) > MAX_OMITTED_FRACTION * planned


def _climb(
    workdir: Path,
    level: list[morecantile.Tile],
    base: int,
    resampling: Any,
    written: list[str],
    tick: Callable[[], None],
) -> None:
    """Make the levels above ``level`` (tiles of the base level that exist), from four children each, down to z0."""
    for _ in range(base):
        parents = _parents(level)
        for parent in parents:
            with _at(parent):
                children = [_decode(workdir, child) for child in overview.children_of(parent)]
                made = overview.parent_tile([array for array, _ in children], resampling)
                if made is not None:
                    nodata = next(value for array, value in children if array is not None)
                    image = overview.tile_image(made, parent, nodata=nodata)
                    _write(tile_path(workdir, parent.z, parent.x, parent.y), overview.encode_tile(image))
                    written.append(f"{parent.z}/{parent.x}/{parent.y}")
            tick()
        level = [p for p in parents if tile_path(workdir, p.z, p.x, p.y).is_file()]


def build_pyramid(
    workdir: Path,
    progress: Progress,
    *,
    registry: DatasetRegistry | None = None,
    gdal_config: Mapping[str, str] | None = None,
    pacer: overview.Pacer | None = None,
) -> dict[str, Any]:
    """Read the base tiles, make the levels above, write the tiles and ``manifest.json``; the manifest's content.

    ``progress(done, total)`` is called after every tile, a tile in ``reuse`` included. The manifest holds ``tiles``
    (``z/x/y`` of every file written or reused), ``base_hashes`` (``x/y`` to hash, for the base tiles that exist and
    have one) and ``omitted``: the base tiles that could not be made because one of their files stayed unreadable after
    the reads were repeated (``x/y`` to kind, class and reason). Such a tile is left out and the build goes on: a pyramid with a
    gap is better than none, the levels above are made from what exists, and `jobs` tries the tile again later. More than
    :data:`MAX_OMITTED_FRACTION` of the base tiles (and more than :data:`MAX_OMITTED`) is an outage, not a gap: the failure
    of the last one is raised then.

    ``pacer`` spaces the reads per host. The child of `jobs` hands in one that takes the host's turns shared by all
    instances (M5-37); without one the build spaces its own reads (:func:`~earthx.readers.access.host_pacer`).
    """
    job = _job(workdir)
    config, base = _config(job["dataset_id"], registry)
    assert config.viewer is not None and config.viewer.overview_resampling is not None
    resampling = config.viewer.overview_resampling
    items = _items(workdir)
    planned = base_tiles(items, base)
    reuse = {key for key in job.get("reuse", [])}
    scenes = _scenes(config, job.get("hosts") or [], items)
    pacer = pacer if pacer is not None else host_pacer()
    total = len(planned) + _count_levels(list(planned), base)
    done = 0
    written: list[str] = []
    hashes: dict[str, str] = {}
    omitted: dict[str, dict[str, str]] = {}
    for tile, members in planned.items():
        key = f"{tile.x}/{tile.y}"
        path = tile_path(workdir, tile.z, tile.x, tile.y)
        if not (key in reuse and path.is_file()):
            try:
                with _at(tile):
                    image = overview.base_tile(
                        [scenes[str(member["id"])] for member in members],
                        tile,
                        resampling=resampling,
                        pacer=pacer,
                        gdal_config=gdal_config or {},
                    )
                    if image is not None:
                        _write(path, overview.encode_tile(image))
            except Exception as error:
                if not _one_file_failed(error):
                    raise
                omitted[key] = _omission(error)
                if _too_many(omitted, len(planned)):
                    raise
        if path.is_file():
            written.append(f"{tile.z}/{tile.x}/{tile.y}")
            if (digest := tile_hash(members, zoom=base, config=config)) is not None:
                hashes[key] = digest
        done += 1
        progress(done, total)
    level = [t for t in planned if tile_path(workdir, t.z, t.x, t.y).is_file()]

    def tick() -> None:
        nonlocal done
        done += 1
        progress(done, total)

    _climb(workdir, level, base, resampling, written, tick)
    manifest = {"base_zoom": base, "tiles": written, "base_hashes": hashes, "omitted": omitted}
    (workdir / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def patch_pyramid(
    workdir: Path,
    progress: Progress,
    *,
    registry: DatasetRegistry | None = None,
    gdal_config: Mapping[str, str] | None = None,
    pacer: overview.Pacer | None = None,
) -> dict[str, Any]:
    """Read again the base tiles named in ``job.json`` (``only``, ``x/y``) and make the tiles above them; the manifest's content.

    The other tiles the levels above need (the siblings of each tile on the way up) are in ``tiles/`` already, put there by
    `jobs` from the store. A tile that reads now is ``recovered`` (with its hash, if it has one); one that fails again
    stays ``omitted`` with the new reason; one whose files hold no valid pixel is recovered too and has no object. The
    manifest's ``tiles`` are the files this step made, the base tiles and the tiles above them.
    """
    job = _job(workdir)
    config, base = _config(job["dataset_id"], registry)
    assert config.viewer is not None and config.viewer.overview_resampling is not None
    resampling = config.viewer.overview_resampling
    items = _items(workdir)
    only = {str(key) for key in job.get("only", [])}
    planned = {tile: members for tile, members in base_tiles(items, base).items() if f"{tile.x}/{tile.y}" in only}
    scenes = _scenes(config, job.get("hosts") or [], items)
    pacer = pacer if pacer is not None else host_pacer()
    written: list[str] = []
    recovered: list[str] = []
    hashes: dict[str, str] = {}
    omitted: dict[str, dict[str, str]] = {}
    done = 0
    for tile, members in planned.items():
        key = f"{tile.x}/{tile.y}"
        path = tile_path(workdir, tile.z, tile.x, tile.y)
        try:
            with _at(tile):
                image = overview.base_tile(
                    [scenes[str(member["id"])] for member in members],
                    tile,
                    resampling=resampling,
                    pacer=pacer,
                    gdal_config=gdal_config or {},
                )
                if image is not None:
                    _write(path, overview.encode_tile(image))
        except Exception as error:
            if not _one_file_failed(error):
                raise
            omitted[key] = _omission(error)
        else:
            recovered.append(key)
            if path.is_file():
                written.append(f"{tile.z}/{tile.x}/{tile.y}")
                if (digest := tile_hash(members, zoom=base, config=config)) is not None:
                    hashes[key] = digest
        done += 1
        progress(done, len(planned))
    level = [t for t in planned if tile_path(workdir, t.z, t.x, t.y).is_file()]
    _climb(workdir, level, base, resampling, written, lambda: None)
    manifest = {
        "base_zoom": base,
        "tiles": written,
        "base_hashes": hashes,
        "omitted": omitted,
        "recovered": recovered,
    }
    (workdir / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def _count_levels(base: Sequence[morecantile.Tile], base_level: int) -> int:
    """How many tiles the levels above the base hold, at most (the ones that turn out empty are counted too)."""
    count, level = 0, list(base)
    for _ in range(base_level):
        level = _parents(level)
        count += len(level)
    return count


def _decode(workdir: Path, tile: morecantile.Tile) -> tuple[np.ma.MaskedArray | None, float | None]:
    path = tile_path(workdir, tile.z, tile.x, tile.y)
    if not path.is_file():
        return None, None
    return overview.decode_tile(path.read_bytes())
