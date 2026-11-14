"""The build of one overview pyramid in the child: items in, tiles out, in the work directory (M5-30b part 8b-2, adr/0032 §5.2).

The work directory is the whole interface (KLAERUNGEN B9: no database, no queue, no object store here). `jobs` writes
into it what it read from the database and the store, starts a child, and uploads what the child leaves:

* ``items.jsonl`` and ``job.json`` (``dataset_id``, the asset ``hosts`` the registry names, ``reuse``) come in;
* ``plan.json`` is what the first step (:func:`plan_pyramid`) leaves: the base tiles and the hash of the items each one
  reads, without a single read at the source, so `jobs` can fetch the tiles of the last version that are still good;
* ``tiles/{z}/{x}/{y}.tif`` is what the second step (:func:`build_pyramid`) leaves, with ``manifest.json``. A base
  tile that `jobs` put there beforehand (its key is in ``reuse``) is neither read nor written again, only decoded for the
  levels above.

**Levels.** The base level is one below the first level the tiles are drawn from (:func:`first_zoom`: the registry's
``viewer.min_zoom``, and for the datasets whose registry value is still 0, the constant of :data:`PYRAMID_MIN_ZOOM`, so
that the part that sets the registry only changes the YAML). Every level above is made from four tiles below it.

**Which files.** A base tile reads the items whose bounding box meets it, in the order of their ids, the first valid
pixel winning (the datasets of a pyramid tile the globe without overlap). The first asset of the default render that an
item carries is the one read, cleared through the policy of `readers` against the hosts the registry names.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any

import morecantile
import numpy as np

from earthx.access.resolve import open_asset_ref, resolve_asset
from earthx.catalog.datasets import registry as default_registry
from earthx.catalog.registry import DatasetConfig, DatasetRegistry, OverviewMode
from earthx.processing import overview
from earthx.readers.access import check_hrefs, host_pacer, read_access_for
from earthx.readers.cog import AssetPath

__all__ = [
    "ITEMS_NAME",
    "JOB_NAME",
    "MANIFEST_NAME",
    "PLAN_NAME",
    "PYRAMID_MIN_ZOOM",
    "TILES_DIR",
    "build_pyramid",
    "first_zoom",
    "plan_pyramid",
    "pyramid_hosts",
    "tile_path",
]

ITEMS_NAME = "items.jsonl"
JOB_NAME = "job.json"
PLAN_NAME = "plan.json"
MANIFEST_NAME = "manifest.json"
TILES_DIR = "tiles"

#: Where the tiles are drawn from the files, for the datasets whose ``viewer.min_zoom`` is still 0 in the registry
#: (adr/0032 §5.2, plan M5-30b §8.10). A registry value of 1 or more wins, so the part that sets 7 and 5 changes YAML only.
PYRAMID_MIN_ZOOM: Mapping[str, int] = MappingProxyType(
    {"cop-dem-glo-30": 7, "esa-worldcover-2020": 5, "esa-worldcover-2021": 5}
)

_TMS = morecantile.tms.get("WebMercatorQuad")
Progress = Callable[[int, int], None]


def first_zoom(dataset_id: str, min_zoom: int) -> int:
    """The level the tiles are drawn from the files at: the registry's ``min_zoom``, else the constant; ``ValueError`` if neither."""
    if min_zoom >= 1:
        return min_zoom
    known = PYRAMID_MIN_ZOOM.get(dataset_id)
    if known is None:
        raise ValueError(f"{dataset_id}: a pyramid needs a viewer.min_zoom of 1 or more, or an entry in PYRAMID_MIN_ZOOM")
    return known


def pyramid_hosts(registry: DatasetRegistry | None = None) -> dict[str, tuple[str, ...]]:
    """The datasets with ``viewer.overview: pyramid`` and the hosts each reads from: plain data for the supervisor.

    A dataset with no level to build from raises ``ValueError``, so the worker does not start with an entry it could
    never build (the same loudness as the other checks of its start).
    """
    found: dict[str, tuple[str, ...]] = {}
    for config in registry if registry is not None else default_registry():
        if config.viewer is not None and config.viewer.overview is OverviewMode.PYRAMID:
            first_zoom(config.dataset_id, config.viewer.min_zoom)
            found[config.dataset_id] = tuple(config.source.asset_hosts)
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
    return config, overview.base_zoom(first_zoom(dataset_id, config.viewer.min_zoom))


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


def plan_pyramid(workdir: Path, *, registry: DatasetRegistry | None = None) -> dict[str, Any]:
    """Write ``plan.json``: the base level and, per base tile ``x/y``, the hash of its items (``null`` without ``updated``)."""
    job = _job(workdir)
    _, base = _config(job["dataset_id"], registry)
    tiles = {
        f"{tile.x}/{tile.y}": overview.base_hash(members)
        for tile, members in base_tiles(_items(workdir), base).items()
    }
    plan = {"base_zoom": base, "tiles": tiles}
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


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _parents(children: Sequence[morecantile.Tile]) -> list[morecantile.Tile]:
    return sorted({morecantile.Tile(c.x // 2, c.y // 2, c.z - 1) for c in children}, key=lambda t: (t.y, t.x))


def build_pyramid(
    workdir: Path, progress: Progress, *, registry: DatasetRegistry | None = None, gdal_config: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Read the base tiles, make the levels above, write the tiles and ``manifest.json``; the manifest's content.

    ``progress(done, total)`` is called after every tile, a tile in ``reuse`` included. The manifest holds ``tiles``
    (``z/x/y`` of every file written or reused) and ``base_hashes`` (``x/y`` to hash, for the base tiles that exist and
    have one).
    """
    job = _job(workdir)
    config, base = _config(job["dataset_id"], registry)
    assert config.viewer is not None and config.viewer.overview_resampling is not None
    resampling = config.viewer.overview_resampling
    items = _items(workdir)
    planned = base_tiles(items, base)
    reuse = {key for key in job.get("reuse", [])}
    scenes = _scenes(config, job.get("hosts") or [], items)
    pacer = host_pacer()
    total = len(planned) + _count_levels(list(planned), base)
    done = 0
    written: list[str] = []
    hashes: dict[str, str] = {}
    for tile, members in planned.items():
        key = f"{tile.x}/{tile.y}"
        path = tile_path(workdir, tile.z, tile.x, tile.y)
        if not (key in reuse and path.is_file()):
            image = overview.base_tile(
                [scenes[str(member["id"])] for member in members],
                tile,
                resampling=resampling,
                pacer=pacer,
                gdal_config=gdal_config or {},
            )
            if image is not None:
                _write(path, overview.encode_tile(image))
        if path.is_file():
            written.append(f"{tile.z}/{tile.x}/{tile.y}")
            if (digest := overview.base_hash(members)) is not None:
                hashes[key] = digest
        done += 1
        progress(done, total)
    level = [t for t in planned if tile_path(workdir, t.z, t.x, t.y).is_file()]
    for _ in range(base):
        parents = _parents(level)
        for parent in parents:
            children = [_decode(workdir, child) for child in overview.children_of(parent)]
            made = overview.parent_tile([array for array, _ in children], resampling)
            if made is not None:
                nodata = next(value for array, value in children if array is not None)
                image = overview.tile_image(made, parent, nodata=nodata)
                _write(tile_path(workdir, parent.z, parent.x, parent.y), overview.encode_tile(image))
                written.append(f"{parent.z}/{parent.x}/{parent.y}")
            done += 1
            progress(done, total)
        level = [p for p in parents if tile_path(workdir, p.z, p.x, p.y).is_file()]
    manifest = {"base_zoom": base, "tiles": written, "base_hashes": hashes}
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
