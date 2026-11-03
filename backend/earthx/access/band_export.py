"""The shape of a band export: which files, named how, read how, and described how (NM4-75).

The crop of the download dialog and the export job write the same layout, so the rules live here and
nothing else decides them (like :mod:`earthx.access.crop_rules` for the crop itself): the bands of an
asset as the item describes them (:class:`BandMeta`), the files of the three forms
(:func:`plan_files`), the pixel size and the resampling of a common resolution (:func:`resampling_for`),
the block reader that lays every band of a file on one grid (:class:`StackReader`), and
``exports/BANDS.txt`` (:func:`bands_text`).

**Three forms.** ``per_band``: one file per band in its own resolution, nothing converted.
``per_resolution``: one file per resolution that occurs, its bands stacked, nothing converted.
``multi_band``: one file at a common resolution; a band of another resolution is converted by
the kind of band (finer: ``nearest``, the values stay; coarser: ``average`` for measurements, ``mode`` for a
classification layer).

**The grid is the crop's grid** (EPSG:4326 at the native pixel size, :func:`~earthx.access.crop_rules.native_crop_grid`),
so the files of one resolution lie on exactly the grid the per-band files of that resolution have; a
common resolution is the same grid with larger or smaller pixels (``pixel_scale``).

Values are the source's own (integers, nodata, scale and offset as tags), never rescaled here.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any

import numpy
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window
from rasterio.windows import transform as window_transform
from rio_tiler.constants import WGS84_CRS
from shapely.geometry.base import BaseGeometry

from earthx.access.crop_rules import asset_gsd, merge_first_valid, rasterize_aoi

__all__ = [
    "BANDS_FILENAME",
    "EXPORTS_DIR",
    "FORMS",
    "FORM_PER_BAND",
    "FORM_PER_RESOLUTION",
    "FORM_MULTI_BAND",
    "BandMeta",
    "BandsFile",
    "ExportPlanError",
    "FilePlan",
    "StackReader",
    "apply_band_tags",
    "band_meta",
    "bands_text",
    "file_profile",
    "format_resolution",
    "plan_files",
    "resampling_for",
    "write_blocks",
]

FORM_PER_BAND = "per_band"
FORM_PER_RESOLUTION = "per_resolution"
FORM_MULTI_BAND = "multi_band"
FORMS = (FORM_PER_BAND, FORM_PER_RESOLUTION, FORM_MULTI_BAND)

#: The folder of the data files in a ZIP, and the description of its bands beside them.
EXPORTS_DIR = "exports/"
BANDS_FILENAME = "BANDS.txt"

_FORM_TEXT = {
    FORM_PER_BAND: "one file per band",
    FORM_PER_RESOLUTION: "one file per resolution",
    FORM_MULTI_BAND: "one multi-band file",
}

#: Two resolutions within this (relative) are the same one.
_SAME = 1e-6


class ExportPlanError(ValueError):
    """The bands and the form asked for do not make a plan; the text names no address and no area."""


@dataclass(frozen=True, slots=True)
class BandMeta:
    """One asset as a band of the data: what the item says about it, and what the registry says of its kind."""

    asset: str
    name: str
    common_name: str | None
    wavelength_um: float | None
    resolution_m: float | None
    data_type: str | None
    scale: float | None
    offset: float | None
    nodata: float | None
    unit: str | None
    #: A classification layer (the registry's mask layer): converted by ``mode``, never averaged.
    categorical: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "asset": self.asset, "name": self.name, "common_name": self.common_name,
            "wavelength_um": self.wavelength_um, "resolution_m": self.resolution_m, "data_type": self.data_type,
            "scale": self.scale, "offset": self.offset, "nodata": self.nodata, "unit": self.unit,
            "categorical": self.categorical,
        }  # fmt: skip

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> BandMeta:
        return cls(**{name: data[name] for name in cls.__slots__})


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def band_meta(item: Mapping[str, Any], asset: str, *, unit: str | None = None, categorical: bool = False) -> BandMeta:
    """:class:`BandMeta` of ``asset`` from the item's own asset entry; ``unit`` is the registry's, used where the item names none."""
    assets = item.get("assets")
    entry = assets.get(asset) if isinstance(assets, Mapping) else None
    entry = entry if isinstance(entry, Mapping) else {}
    eo = entry.get("eo:bands")
    eo_first = eo[0] if isinstance(eo, list) and eo and isinstance(eo[0], Mapping) else {}
    raster = entry.get("raster:bands") or entry.get("bands")
    first = raster[0] if isinstance(raster, list) and raster and isinstance(raster[0], Mapping) else {}
    return BandMeta(
        asset=asset,
        name=_text(eo_first.get("name")) or asset,
        common_name=_text(eo_first.get("common_name")),
        wavelength_um=_number(eo_first.get("center_wavelength")),
        resolution_m=asset_gsd(item, asset),
        data_type=_text(first.get("data_type")),
        scale=_number(first.get("scale")),
        offset=_number(first.get("offset")),
        nodata=_number(first.get("nodata")),
        unit=_text(first.get("unit")) or unit,
        categorical=categorical,
    )


def format_resolution(resolution: float | None) -> str | None:
    """``10`` for 10.0, ``12.5`` for 12.5; ``None`` where the resolution is not known."""
    if resolution is None:
        return None
    return f"{round(resolution, 6):g}"


_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _clean(text: str) -> str:
    return _SAFE.sub("_", text).strip("._")


def _band_stem(meta: BandMeta) -> str:
    parts = [meta.name]
    if meta.common_name and meta.common_name.casefold() != meta.name.casefold():
        parts.append(meta.common_name)
    res = format_resolution(meta.resolution_m)
    if res is not None:
        parts.append(f"{res}m")
    return _clean("_".join(parts)) or "asset"


@dataclass(frozen=True, slots=True)
class FilePlan:
    """One data file of the export: its name (inside ``exports/``), its bands in order, its pixel size."""

    name: str
    assets: tuple[str, ...]
    #: The pixel size of the file in metres; ``None`` where a band does not say its own (per band / per resolution only).
    resolution_m: float | None

    @property
    def mask_name(self) -> str:
        return f"{self.name[:-4]}_mask.tif"


def _same(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and math.isclose(a, b, rel_tol=_SAME)


def plan_files(form: str, metas: Sequence[BandMeta], common_resolution: float | None = None) -> list[FilePlan]:
    """The files of ``form`` for ``metas`` (in the order of the bands asked for), or :class:`ExportPlanError`."""
    if form not in FORMS:
        raise ExportPlanError(f"form is one of {', '.join(FORMS)}")
    if not metas:
        raise ExportPlanError("an export needs at least one band")
    if len({meta.asset for meta in metas}) != len(metas):
        raise ExportPlanError("a band is named twice")
    if (form == FORM_MULTI_BAND) != (common_resolution is not None):
        raise ExportPlanError("a common resolution goes with the form one multi-band file, and with no other")
    if form == FORM_PER_BAND:
        names: dict[str, int] = {}
        stems = [_band_stem(meta) for meta in metas]
        for stem in stems:
            names[stem] = names.get(stem, 0) + 1
        return [
            FilePlan(
                f"{stem if names[stem] == 1 else _clean(f'{stem}_{meta.asset}')}.tif",
                (meta.asset,),
                meta.resolution_m,
            )
            for stem, meta in zip(stems, metas, strict=True)
        ]
    if form == FORM_MULTI_BAND:
        assert common_resolution is not None
        if not math.isfinite(common_resolution) or common_resolution <= 0:
            raise ExportPlanError("the common resolution is a positive number of metres")
        if any(meta.resolution_m is None for meta in metas):
            raise ExportPlanError("a band without a known pixel size cannot be brought to a common resolution")
        return [FilePlan(f"bands_{format_resolution(common_resolution)}m.tif", tuple(m.asset for m in metas), common_resolution)]
    groups: list[tuple[float | None, list[str]]] = []
    for meta in metas:
        for resolution, assets in groups:
            if resolution is None and meta.resolution_m is None or _same(resolution, meta.resolution_m):
                assets.append(meta.asset)
                break
        else:
            groups.append((meta.resolution_m, [meta.asset]))
    return [
        FilePlan(
            f"bands_{format_resolution(resolution)}m.tif" if resolution is not None else "bands.tif",
            tuple(assets),
            resolution,
        )
        for resolution, assets in sorted(groups, key=lambda group: (group[0] is None, group[0] or 0.0))
    ]


def resampling_for(meta: BandMeta, target_m: float | None) -> str:
    """How a band is brought to ``target_m``: ``none`` (already there), ``nearest`` (finer), ``average`` / ``mode`` (coarser)."""
    if target_m is None or meta.resolution_m is None or _same(meta.resolution_m, target_m):
        return "none"
    if meta.resolution_m > target_m:
        return "nearest"
    return "mode" if meta.categorical else "average"


_WARP = {"none": Resampling.nearest, "nearest": Resampling.nearest, "average": Resampling.average, "mode": Resampling.mode}


class StackReader:
    """The bands of one output file, read block by block on one grid, the items of a mosaic merged first-valid.

    ``bands`` holds, per band of the file, the opened datasets of the items in the order of the mosaic;
    ``methods`` the resampling of each band (:func:`resampling_for`). Every band is a view of its dataset
    warped onto ``transform``/``width``/``height`` in EPSG:4326, so a band that already has the grid's
    pixel size is the crop's own ``nearest`` warp, bit for bit. The views live as long as ``stack``.
    """

    def __init__(
        self,
        bands: Sequence[Sequence[Any]],
        methods: Sequence[str],
        transform: Any,
        width: int,
        height: int,
        stack: ExitStack,
    ):
        self.height = height
        self.width = width
        self.transform = transform
        self._vrts: list[list[Any]] = []
        for datasets, method in zip(bands, methods, strict=True):
            if any(dataset.count != 1 for dataset in datasets):
                raise ExportPlanError("a band of a stacked file has exactly one band in its source")
            self._vrts.append(
                [
                    stack.enter_context(
                        WarpedVRT(
                            dataset, crs=WGS84_CRS, transform=transform, width=width, height=height,
                            resampling=_WARP[method],
                        )  # fmt: skip
                    )
                    for dataset in datasets
                ]
            )
        first = [vrts[0] for vrts in self._vrts]
        self.dtype = numpy.result_type(*[numpy.dtype(vrt.dtypes[0]) for vrt in first]).name
        nodata = {vrt.nodata for vrt in first}
        #: One value for the file where the bands agree on it; a GeoTIFF has no nodata per band.
        self.nodata: float | None = nodata.pop() if len(nodata) == 1 else None
        self.band_nodata = [vrt.nodata for vrt in first]

    def read(self, window: Window) -> numpy.ma.MaskedArray:
        """The block of every band, masked where no item has a value."""
        planes = [
            merge_first_valid(vrt.read(1, window=window, masked=True) for vrt in vrts).astype(self.dtype)
            for vrts in self._vrts
        ]
        return numpy.ma.stack(planes)


def file_profile(reader: StackReader, metas: Sequence[BandMeta], *, block_size: int) -> dict[str, Any]:
    """The plain GeoTIFF profile of a file: the grid of ``reader``, one band per entry of ``metas``."""
    return {
        "driver": "GTiff",
        "dtype": reader.dtype,
        "count": len(metas),
        "height": reader.height,
        "width": reader.width,
        "crs": WGS84_CRS,
        "transform": reader.transform,
        "tiled": True,
        "blockxsize": block_size,
        "blockysize": block_size,
        "nodata": reader.nodata,
    }


def _blocks(width: int, height: int, size: int) -> Iterator[Window]:
    for row in range(0, height, size):
        for col in range(0, width, size):
            yield Window(col, row, min(size, width - col), min(size, height - row))


def write_blocks(
    reader: StackReader,
    dst: Any,
    mask_dst: Any,
    aoi: BaseGeometry,
    *,
    block_size: int,
    on_block: Callable[[], None] | None = None,
) -> bool:
    """Writes every block of ``reader`` to ``dst`` and the mask of ``aoi`` (1 inside) to ``mask_dst``; whether any pixel in the AOI had a value.

    A pixel no item has a value for gets its band's own nodata, else 0. The mask never changes the data (M3-18 §3).
    """
    fills = [0 if nodata is None else nodata for nodata in reader.band_nodata]
    any_valid = False
    for window in _blocks(reader.width, reader.height, block_size):
        block = reader.read(window)
        inside = rasterize_aoi(
            aoi, height=int(window.height), width=int(window.width), transform=window_transform(window, reader.transform)
        )
        empty = numpy.ma.getmaskarray(block).all(axis=0)
        any_valid = any_valid or bool((inside.astype(bool) & ~empty).any())
        dst.write(numpy.stack([numpy.ma.filled(block[i], fills[i]) for i in range(len(fills))]), window=window)
        mask_dst.write(inside, 1, window=window)
        if on_block is not None:
            on_block()
    return any_valid


def apply_band_tags(dst: Any, metas: Sequence[BandMeta]) -> None:
    """The name of every band as its description, and the item's scale and offset as the file's (kept by ``cog_translate``)."""
    for index, meta in enumerate(metas, start=1):
        dst.set_band_description(index, meta.name)
    dst.scales = tuple(1.0 if meta.scale is None else meta.scale for meta in metas)
    dst.offsets = tuple(0.0 if meta.offset is None else meta.offset for meta in metas)


def _cell(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


@dataclass(frozen=True, slots=True)
class BandsFile:
    """One data file as BANDS.txt lists it: its path in the ZIP, its bands, what was done to each, and its data type."""

    path: str
    bands: Sequence[BandMeta]
    #: ``none``, ``nearest``, ``average`` or ``mode`` per band (:func:`resampling_for`).
    methods: Sequence[str]
    #: The pixel size of each band in the file, in metres.
    export_resolutions: Sequence[float | None]
    #: The data type the file is written in; ``None`` where each band keeps the item's.
    data_type: str | None = None


_HEADER = (
    "Band | Name | Common name | Wavelength (um) | Source resolution (m) | Export resolution (m) | Resampling | "
    "Data type | Scale | Offset | Nodata | Unit"
)


def bands_text(
    *,
    title: str,
    form: str,
    files: Iterable[BandsFile],
    common_resolution: float | None = None,
    notes: Sequence[str] = (),
) -> str:
    """``exports/BANDS.txt``: every file and, by band number, what the band is and what was done to it.

    ``files`` are in the order of the ZIP; ``notes`` are lines for the head, such as the one that scenes
    of several coordinate systems were combined.
    """
    lines = ["EarthX band list", f"Dataset: {title}", f"Layout: {_FORM_TEXT[form]}"]
    if common_resolution is not None:
        lines.append(f"Common resolution: {format_resolution(common_resolution)} m")
    lines.extend(notes)
    for entry in files:
        lines += ["", f"File: {entry.path}", _HEADER]
        for index, (meta, method, export) in enumerate(
            zip(entry.bands, entry.methods, entry.export_resolutions, strict=True), start=1
        ):
            lines.append(
                " | ".join(
                    [
                        str(index),
                        meta.name,
                        _cell(meta.common_name),
                        _cell(meta.wavelength_um),
                        _cell(format_resolution(meta.resolution_m)),
                        _cell(format_resolution(export)),
                        method,
                        _cell(entry.data_type or meta.data_type),
                        _cell(1.0 if meta.scale is None else meta.scale),
                        _cell(0.0 if meta.offset is None else meta.offset),
                        _cell(meta.nodata),
                        _cell(meta.unit),
                    ]
                )
            )
    return "\n".join(lines) + "\n"
