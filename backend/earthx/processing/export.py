"""The export job: the output ``crop`` computed in the core, block by block on disk (M4-11a).

The same files as the synchronous crop (P19, P20, P21; M4-11 F1): per touched group and
asset one data COG and one mask, on the grid of :func:`~earthx.access.crop_rules.native_crop_grid`
(EPSG:4326 at the native resolution, ``nearest``), extent ``bbox(AOI ∩ footprints of the
group)``, the mask ``1`` inside the original AOI, the source's own values and nodata kept.
Unlike the crop it never holds more than one block per item: the crop builds its ZIP in
memory (3.1 GB at 500 MB raw, M3-18 §10.3), the export writes to the work directory and
packs ``export.zip`` there for `jobs` to upload.

**Several items, one after the other (Otto, 08.10.2026).** A group of several items is a
mosaic: per block the items are read in the order of the order, and the first valid
element per band and pixel wins — `rio-tiler`'s ``FirstMethod``, which the crop uses
through ``mosaic_reader``. An item is read with the same warp the crop's reader uses: one
item alone as the crop's windowed path reads it, several as ``Reader.part`` reads each of
them (nodata from the value, otherwise from an alpha band). Every item stays one open
dataset; memory follows the block, not the number of items.

**What `api` hands in** (:class:`Attachments`, M4-11 K3, F4): ``ATTRIBUTION.txt``,
``citation.bib`` and ``aoi.geojson``, finished, because only `api` reads the registry and
sees the origin of a place-search AOI; and the attribution for the provenance.
``recipe.json`` is written here, from the job's own recipe (F3).

Nothing here logs an AOI, an address or a hash (adr/0014 §4.7).
"""

from __future__ import annotations

import json
import logging
import time
import zipfile
import zlib
from collections.abc import Callable, Iterator, Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy
import rasterio
from rasterio.errors import RasterioError
from rasterio.windows import Window
from rasterio.windows import transform as window_transform
from rio_cogeo.cogeo import cog_translate
from rio_tiler.constants import WGS84_CRS
from shapely.geometry import shape as shapely_shape
from shapely.geometry.base import BaseGeometry

from earthx.access.crop_rules import (
    AOI_FILENAME,
    BLOCK_SIZE,
    CITATION_FILENAME,
    COG_PROFILE,
    NOTICE_FILENAME,
    RECIPE_FILENAME,
    AoiOutsideItems,
    compute_crop_region,
    crop_filename,
    group_dirname,
    mask_filename,
    mask_profile,
    merge_first_valid,
    native_crop_grid,
    rasterize_aoi,
)
from earthx.access.resolve import open_asset_ref
from earthx.processing.errors import AoiOutsideInputs, ProcessingError, UnsupportedRecipe
from earthx.processing.operators import REGISTRY
from earthx.processing.plan import estimate
from earthx.processing.recipe import CropOutput, Recipe, ResolvedInput, engine_versions, job_recipe_document
from earthx.processing.warped import WarpedItem
from earthx.processing.workfile import open_workfile, workfile_path
from earthx.readers import process_gdal_options, read_access_for
from earthx.readers.cog import AssetPath, CogReader

__all__ = [
    "ATTACHMENTS_NAME",
    "ATTACHMENT_LIMITS",
    "EXPORT_NAME",
    "Attachments",
    "AttachmentsInvalid",
    "ExportResult",
    "OutputUnreadable",
    "check_export",
    "export",
    "read_attachments",
]

LOGGER = logging.getLogger("earthx.processing")

#: The one file an export leaves for upload (`objectstore.RESULT_NAMES`).
EXPORT_NAME = "export.zip"

#: Where `jobs` puts what `api` handed in, next to ``recipe.json``.
ATTACHMENTS_NAME = "attachments.json"

#: The files `api` builds, and the most each may hold in UTF-8 bytes (M4-11 K3). The AOI
#: may be as large as the body of an order (1 MiB) and a little more as GeoJSON text.
ATTACHMENT_LIMITS: Mapping[str, int] = {
    NOTICE_FILENAME: 64 * 1024,
    CITATION_FILENAME: 64 * 1024,
    AOI_FILENAME: 2 * 1024 * 1024,
}
_ATTRIBUTION_ENTRIES = 8

#: The least read cache an open item keeps (:func:`_cache_per_item`): a COG block of
#: 1024² ``uint16`` is 2 MB uncompressed, deflated about half of that.
_MIN_CACHE_PER_ITEM = 1024 * 1024
_ATTRIBUTION_CHARS = 1024

Progress = Callable[[int, int], None]


class AttachmentsInvalid(ProcessingError, ValueError):
    """What `api` hands an export is not the fixed set of files; the text names no content."""


class OutputUnreadable(ProcessingError):
    """A file the export just wrote did not read back completely (M3-22)."""


@dataclass(frozen=True, slots=True)
class Attachments:
    """The finished side files of an export, built by `api` (module docstring)."""

    files: Mapping[str, str]
    attribution: tuple[str, ...]

    def __post_init__(self) -> None:
        if set(self.files) != set(ATTACHMENT_LIMITS):
            raise AttachmentsInvalid(f"an export takes exactly {', '.join(sorted(ATTACHMENT_LIMITS))}")
        for name, text in self.files.items():
            try:
                size = len(text.encode("utf-8")) if isinstance(text, str) else None
            except UnicodeEncodeError:
                size = None  # a lone surrogate: no UTF-8 form, no file
            if size is None or size > ATTACHMENT_LIMITS[name]:
                raise AttachmentsInvalid(f"{name} is UTF-8 text of at most {ATTACHMENT_LIMITS[name]} bytes")
        if len(self.attribution) > _ATTRIBUTION_ENTRIES or not all(
            isinstance(entry, str) and len(entry) <= _ATTRIBUTION_CHARS for entry in self.attribution
        ):
            raise AttachmentsInvalid("the attribution is a short list of short texts")

    def to_json(self) -> dict[str, Any]:
        return {"files": dict(self.files), "attribution": list(self.attribution)}

    @classmethod
    def from_json(cls, data: Any) -> Attachments:
        if not isinstance(data, Mapping) or set(data) != {"files", "attribution"}:
            raise AttachmentsInvalid("the attachments hold files and attribution")
        files, attribution = data["files"], data["attribution"]
        if not isinstance(files, Mapping) or not isinstance(attribution, list):
            raise AttachmentsInvalid("the attachments hold files and attribution")
        return cls(dict(files), tuple(attribution))


@dataclass(frozen=True, slots=True)
class ExportResult:
    """What an export leaves in the work directory, and what it says about it."""

    path: Path
    #: The members of the ZIP, in order.
    members: tuple[str, ...]
    groups: int
    assets: int
    blocks: int
    engine: dict[str, str]
    started: datetime
    finished: datetime
    #: The attribution its ``recipe.json`` carries, for the copy `api` serves (K4).
    attribution: tuple[str, ...]


def check_export(recipe: Recipe) -> CropOutput:
    """The crop output of a recipe the export runs, or :class:`UnsupportedRecipe` (M4-11 K1, F5, F6).

    No steps, native resolution, one input of COG assets, and a size under the cap — the
    estimate raises :class:`~earthx.processing.errors.ExportTooLarge` above it.
    """
    output = recipe.output
    if not isinstance(output, CropOutput):
        raise UnsupportedRecipe("an export has the output crop")
    if recipe.steps:
        raise UnsupportedRecipe("an export has no steps; it delivers the source's own values")
    if output.resolution_factor != 1:
        raise UnsupportedRecipe("an export job reads at native resolution only (resolution_factor 1)")
    if len(recipe.inputs) != 1:
        raise UnsupportedRecipe("an export has exactly one input")
    if any(entry.asset.reader != "cog" for entry in recipe.inputs[0].resolved):
        raise UnsupportedRecipe("export jobs read COG assets only for now")
    names = [crop_filename(asset) for asset in recipe.inputs[0].assets]
    if len(set(names)) != len(names):
        raise UnsupportedRecipe("two assets of the export would get the same file name in the ZIP")
    estimate(recipe, REGISTRY)
    return output


# --- reading ------------------------------------------------------------------


def _blocks(width: int, height: int) -> Iterator[Window]:
    for row in range(0, height, BLOCK_SIZE):
        for col in range(0, width, BLOCK_SIZE):
            yield Window(col, row, min(BLOCK_SIZE, width - col), min(BLOCK_SIZE, height - row))


# --- one output file -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Output:
    group: int
    asset: str
    entries: tuple[ResolvedInput, ...]
    region: BaseGeometry
    transform: Any
    width: int
    height: int

    @property
    def blocks(self) -> int:
        return -(-self.width // BLOCK_SIZE) * -(-self.height // BLOCK_SIZE)


class _Export:
    def __init__(self, recipe: Recipe, workdir: Path, progress: Progress) -> None:
        self.recipe = recipe
        self.workdir = workdir
        self.progress = progress
        self.access = read_access_for(recipe.hrefs())
        self.aoi = shapely_shape(recipe.aoi.model_dump(mode="json"))
        self.written: list[str] = []
        self.done = 0
        self.total = 0

    def tick(self) -> None:
        self.done += 1
        self.progress(self.done, self.total)

    def new_file(self, name: str) -> Path:
        path = workfile_path(self.workdir, name)
        self.written.append(name)
        return path

    def forget(self, name: str) -> None:
        workfile_path(self.workdir, name).unlink(missing_ok=True)
        self.written.remove(name)

    def cleanup(self) -> None:
        for name in self.written:
            workfile_path(self.workdir, name).unlink(missing_ok=True)

    def open_dataset(self, entry: ResolvedInput, stack: ExitStack) -> Any:
        target = open_asset_ref(entry.asset.to_asset(), self.access.policy, self.access.resolve)
        assert isinstance(target, AssetPath)  # `check_export`: COG only
        return stack.enter_context(CogReader(target)).dataset

    def plan(self) -> list[_Output]:
        """Every output file with its grid, before the first block is read: the total for the progress."""
        entry = self.recipe.inputs[0]
        footprints = entry.footprints or {}
        resolved = {(item.asset.item_id, item.asset.asset): item for item in entry.resolved}
        outputs = []
        for index, group in enumerate(entry.groups):
            items = [{"geometry": _geometry(footprints.get(item_id))} for item_id in group]
            try:
                region = compute_crop_region(items, self.aoi)
            except AoiOutsideItems:
                raise AoiOutsideInputs("the AOI does not touch the footprint of a group") from None
            for asset in entry.assets:
                entries = tuple(resolved[(item_id, asset)] for item_id in group)
                with ExitStack() as stack:
                    transform, width, height = native_crop_grid(self.open_dataset(entries[0], stack), region)
                outputs.append(_Output(index, asset, entries, region, transform, width, height))
        return outputs

    def write(self, index: int, output: _Output) -> tuple[str, str]:
        """The data COG and the mask of one group and asset; returns their work file names."""
        stem = f"out-{index}"
        plain_name, data_name, mask_name = f"{stem}-plain.tif", f"{stem}.tif", f"{stem}-mask.tif"
        any_valid = False
        with ExitStack() as stack:
            alone = len(output.entries) == 1
            with rasterio.Env(VSI_CACHE_SIZE=str(_cache_per_item(len(output.entries)))):
                datasets = [self.open_dataset(entry, stack) for entry in output.entries]
            items = [
                WarpedItem(dataset, output.transform, output.width, output.height, alone=alone, stack=stack)
                for dataset in datasets
            ]
            if len({(len(item.indexes), item.dtype) for item in items}) != 1:
                raise UnsupportedRecipe("the items of a group differ in their bands or data type; no mosaic")
            nodata = items[0].nodata
            fill_value = nodata if nodata is not None else 0
            profile = {
                "driver": "GTiff",
                "dtype": items[0].dtype,
                "count": len(items[0].indexes),
                "height": output.height,
                "width": output.width,
                "crs": WGS84_CRS,
                "transform": output.transform,
                "tiled": True,
                "blockxsize": BLOCK_SIZE,
                "blockysize": BLOCK_SIZE,
                "nodata": nodata,
            }
            masks = mask_profile(height=output.height, width=output.width, crs=WGS84_CRS, transform=output.transform)
            self.new_file(plain_name)
            self.new_file(mask_name)
            with (
                open_workfile(self.workdir, plain_name, "w", **profile) as dst,
                open_workfile(self.workdir, mask_name, "w", **masks) as mask_dst,
            ):
                for window in _blocks(output.width, output.height):
                    block = merge_first_valid(item.read(window) for item in items)
                    inside = rasterize_aoi(
                        self.aoi,
                        height=int(window.height),
                        width=int(window.width),
                        transform=window_transform(window, output.transform),
                    )
                    if not any_valid and (inside.astype(bool) & ~block.mask.all(axis=0)).any():
                        any_valid = True
                    dst.write(numpy.ma.filled(block, fill_value), window=window)
                    mask_dst.write(inside, 1, window=window)
                    self.tick()
        if not any_valid:
            raise AoiOutsideInputs("the AOI does not cover any valid pixel of a group")
        data_path = self.new_file(data_name)
        with open_workfile(self.workdir, plain_name) as plain:
            cog_translate(plain, str(data_path), COG_PROFILE, in_memory=False, quiet=True)
        self.forget(plain_name)
        _verify(self.workdir, data_name, mask_name)
        return data_name, mask_name

    def pack(self, files: list[tuple[str, str]], texts: list[tuple[str, bytes]]) -> Path:
        """``export.zip``: the rasters stored as they are, the texts deflated; each file goes once it is in."""
        path = self.new_file(EXPORT_NAME)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for member, name in files:
                archive.write(workfile_path(self.workdir, name), member, compress_type=zipfile.ZIP_STORED)
                self.forget(name)
            for member, content in texts:
                archive.writestr(member, content, compress_type=zipfile.ZIP_DEFLATED)
        try:
            with zipfile.ZipFile(path) as archive:
                broken = archive.testzip()
        except (zipfile.BadZipFile, zlib.error, EOFError) as error:
            raise OutputUnreadable(f"the export ZIP does not read back: {type(error).__name__}") from None
        if broken is not None:
            raise OutputUnreadable("an entry of the export ZIP fails its CRC check")
        return path


def _cache_per_item(items: int) -> int:
    """The share of ``VSI_CACHE_SIZE`` each open item of a group gets, so that a group costs what one item costs.

    GDAL gives every open file a read cache of its own of ``VSI_CACHE_SIZE`` (64 MB for a
    worker, `readers.process_gdal_options`), taken when the file is opened. The crop opens
    the items of a mosaic one after the other; the export keeps them open together, so the
    one item's budget is split between them (Otto, 08.10.2026: the limit holds per item;
    measured +64 MB per further item before this). A cache changes no value read.
    """
    budget = int(process_gdal_options()["VSI_CACHE_SIZE"])
    return max(_MIN_CACHE_PER_ITEM, budget // items)


def _geometry(footprint: Any) -> dict[str, Any] | None:
    return None if footprint is None else footprint.model_dump(mode="json")


def _read_every_block(dataset: Any) -> Any:
    peak = None
    for _, window in dataset.block_windows(1):
        block_peak = dataset.read(window=window).max()
        peak = block_peak if peak is None else max(peak, block_peak)
    return peak


def _verify(workdir: Path, data_name: str, mask_name: str) -> None:
    """Both files read back completely, overviews included, on one grid (as the crop checks, M3-22)."""
    try:
        with open_workfile(workdir, data_name) as data, open_workfile(workdir, mask_name) as mask:
            if (data.width, data.height, data.transform, data.crs) != (
                mask.width, mask.height, mask.transform, mask.crs
            ):
                raise OutputUnreadable("the data file and its mask are not on the same grid")
            if mask.count != 1 or mask.dtypes[0] != "uint8":
                raise OutputUnreadable("the mask file is not a single uint8 band")
            _read_every_block(data)
            if _read_every_block(mask) > 1:
                raise OutputUnreadable("the mask file holds values other than 0 and 1")
            levels = len(data.overviews(1))
        for level in range(levels):
            with open_workfile(workdir, data_name, overview_level=level) as overview:
                _read_every_block(overview)
    except RasterioError as error:
        raise OutputUnreadable(f"a file of the export does not read back: {type(error).__name__}") from None


def export(recipe: Recipe, *, workdir: Path, progress: Progress, attachments: Attachments) -> ExportResult:
    """Compute the crop of ``recipe`` into ``workdir/export.zip``; a pure function of its inputs."""
    check_export(recipe)
    state = _Export(recipe, workdir, progress)
    started = datetime.now(UTC)
    clock = time.monotonic()
    entry = recipe.inputs[0]
    LOGGER.info("export started", extra={"dataset": entry.dataset, "groups": len(entry.groups)})
    try:
        with rasterio.Env(**process_gdal_options()):
            outputs = state.plan()
            state.total = sum(output.blocks for output in outputs) + 1
            group_count = len(entry.groups)
            files: list[tuple[str, str]] = []
            for index, output in enumerate(outputs):
                data_name, mask_name = state.write(index, output)
                folder = group_dirname(output.group, group_count)
                files.append((folder + crop_filename(output.asset), data_name))
                files.append((folder + mask_filename(output.asset), mask_name))
            engine = engine_versions()
            finished = datetime.now(UTC)
            document = job_recipe_document(
                recipe.model_dump(mode="json"),
                attribution=attachments.attribution,
                result={"engine": engine, "scaling": []},
                started=started,
                finished=finished,
            )
            texts = [
                (AOI_FILENAME, attachments.files[AOI_FILENAME].encode("utf-8")),
                (RECIPE_FILENAME, document),
                (CITATION_FILENAME, attachments.files[CITATION_FILENAME].encode("utf-8")),
                (NOTICE_FILENAME, attachments.files[NOTICE_FILENAME].encode("utf-8")),
            ]
            path = state.pack(files, texts)
            state.tick()
    except BaseException:
        state.cleanup()
        LOGGER.warning("export failed", extra={"dataset": entry.dataset, "blocks": state.done})
        raise
    members = tuple(member for member, _ in files) + tuple(member for member, _ in texts)
    LOGGER.info(
        "export finished",
        extra={
            "dataset": entry.dataset,
            "groups": len(entry.groups),
            "assets": len(entry.assets),
            "blocks": state.done,
            "bytes": path.stat().st_size,
            "seconds": round(time.monotonic() - clock, 3),
        },
    )
    return ExportResult(
        path=path,
        members=members,
        groups=len(entry.groups),
        assets=len(entry.assets),
        blocks=state.done,
        engine=engine,
        started=started,
        finished=finished,
        attribution=attachments.attribution,
    )


def read_attachments(workdir: Path) -> Attachments:
    """What `jobs` wrote next to the recipe; :class:`AttachmentsInvalid` if it is not that."""
    try:
        data = json.loads(workfile_path(workdir, ATTACHMENTS_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise AttachmentsInvalid("the attachments of the export cannot be read") from None
    return Attachments.from_json(data)
