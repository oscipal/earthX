"""The shape of a band export: which files, named how, read how, and described how (NM4-75).

The crop of the download dialog and the export job write the same layout, so the rules live here and
nothing else decides them (like :mod:`earthx.access.crop_rules` for the crop itself): the bands of an
asset as the item describes them (:class:`BandMeta`), the files of the three forms
(:func:`plan_files`), the pixel size and the resampling of a common resolution (:func:`resampling_for`),
the block reader that lays every band of a file on one grid (:class:`StackReader`), and
``exports/BANDS.txt`` (:func:`bands_text`).

**Classes** (M5-62): a band whose values are classes carries them from the registry (:attr:`BandMeta.classes`). A file of
one such band of ``uint8`` or ``uint16`` holds their colour table; GDAL keeps the names and the attribute table of a
GeoTIFF only beside it, in ``<file>.aux.xml`` (:func:`class_files`), which GDAL and QGIS read with the file; and
``BANDS.txt`` lists them. Crop and export only pass the source's values on, so a band keeps its classes here.

**Three forms.** ``per_band``: one file per band in its own resolution, nothing converted.
``per_resolution``: one file per resolution that occurs, its bands stacked, nothing converted.
``multi_band``: one file at a common resolution; a band of another resolution is converted by
the kind of band (finer: ``nearest``, the values stay; coarser: ``average`` for measurements, ``mode`` for a
classification layer).

**The grid is the source's** (Otto, 03.11.2026): the CRS of the scenes, their pixel size and pixel lattice
(:func:`~earthx.access.crop_rules.source_crop_grid`), so a band of the source's own resolution is a plain copy of
its pixels. The files of one resolution lie on exactly the grid the per-band files of that resolution have; a common
resolution is the same lattice with larger or smaller pixels (``pixel_scale``). Only scenes in another CRS than the
group's (the one most of them share) are warped onto it.

Values are the source's own (integers, nodata, scale and offset as tags), never rescaled here.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, replace
from html import escape
from typing import Any

import numpy
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_geom
from rasterio.windows import Window
from rasterio.windows import transform as window_transform
from rio_tiler.constants import WGS84_CRS
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from earthx.access.crop_rules import asset_gsd, merge_first_valid, rasterize_aoi
from earthx.catalog.registry import ClassRow, Look
from earthx.readers.reference_store import REFS_KEY

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
    "AUX_SUFFIX",
    "PALETTE_TYPES",
    "aoi_on_grid",
    "apply_band_tags",
    "band_count",
    "band_meta_of_items",
    "band_rows",
    "band_table",
    "holds_one_array",
    "is_geotiff",
    "band_meta",
    "bands_text",
    "class_colour_table",
    "class_files",
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
#: What GDAL appends to the name of a file for the one beside it that keeps what the file itself cannot (PAM).
AUX_SUFFIX = ".aux.xml"
#: The data types a GeoTIFF holds a colour table for.
PALETTE_TYPES = ("uint8", "uint16")

_FORM_TEXT = {
    FORM_PER_BAND: "one file per band",
    FORM_PER_RESOLUTION: "one file per resolution",
    FORM_MULTI_BAND: "one multi-band file",
}

#: Two resolutions within this (relative) are the same one.
_SAME = 1e-6


class ExportPlanError(ValueError):
    """The bands and the form asked for do not make a plan; the text names no address and no area."""


class NoFreeNodata(ExportPlanError):
    """An integer source without nodata: every value may be real, so none may mark a pixel without data (M5-28, F2)."""


def kept_nodata(dtype: str, nodata: float | None) -> float:
    """The nodata of a file that keeps the source's values: crop, export and band download (M5-28 R1, R6).

    The source's own where it states one; NaN for a float type without one, so that a gap is never 0 m or 0 °C;
    :class:`NoFreeNodata` for an integer type without one, until the registry names a value that is never real.
    """
    if nodata is not None:
        return float(nodata)
    if numpy.issubdtype(numpy.dtype(dtype), numpy.floating):
        return math.nan
    raise NoFreeNodata(
        f"the source states no nodata for its {dtype} values, so no value is free to mark a pixel without data"
    )


def _nodata_key(value: float) -> float | str:
    return "nan" if math.isnan(value) else value


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
    #: A classification layer (the registry's mask layer or a band of classes): converted by ``mode``, never averaged.
    categorical: bool
    #: The classes of a band whose values are classes (M5-62), ``None`` for any other.
    classes: tuple[ClassRow, ...] | None = None
    #: The look of the band in the collection (M5-60), for its QGIS style (M5-64); ``None`` where it has none.
    look: Look | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "asset": self.asset, "name": self.name, "common_name": self.common_name,
            "wavelength_um": self.wavelength_um, "resolution_m": self.resolution_m, "data_type": self.data_type,
            "scale": self.scale, "offset": self.offset, "nodata": self.nodata, "unit": self.unit,
            "categorical": self.categorical,
            "classes": None if self.classes is None else [
                {"value": row.value, "name": row.name, "colour": row.colour} for row in self.classes
            ],
            **({} if self.look is None else {"look": self.look.annotation()}),
        }  # fmt: skip

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> BandMeta:
        """The band from the JSON of :meth:`to_json`; a field of the wrong type is a :class:`ValueError`, not a crash later.

        JSON written before M5-62 has no ``classes``, before M5-64 no ``look``: the band then has none.
        """
        fields = {name: data[name] for name in cls.__slots__ if name not in ("classes", "look")}
        meta = cls(**fields, classes=_classes_from_json(data.get("classes")), look=_look_from_json(data.get("look")))
        for name in ("asset", "name"):
            if not isinstance(getattr(meta, name), str):
                raise ValueError(f"{name} is text")
        for name in ("common_name", "data_type", "unit"):
            if getattr(meta, name) is not None and not isinstance(getattr(meta, name), str):
                raise ValueError(f"{name} is text or null")
        for name in ("wavelength_um", "resolution_m", "scale", "offset", "nodata"):
            value = getattr(meta, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise ValueError(f"{name} is a number or null")
        if not isinstance(meta.categorical, bool):
            raise ValueError("categorical is true or false")
        return meta


def _classes_from_json(data: Any) -> tuple[ClassRow, ...] | None:
    if data is None:
        return None
    if not isinstance(data, list) or not data:
        raise ValueError("classes is a list of classes or null")
    rows = []
    for entry in data:
        if not isinstance(entry, Mapping) or set(entry) != {"value", "name", "colour"}:
            raise ValueError("a class has a value, a name and a colour")
        value, name, colour = entry["value"], entry["name"], entry["colour"]
        if isinstance(value, bool) or not isinstance(value, int) or not isinstance(name, str):
            raise ValueError("a class has a whole number as value and a text as name")
        if not isinstance(colour, str) or not re.fullmatch(r"#[0-9a-f]{6}", colour):
            raise ValueError("a colour is written #rrggbb")
        rows.append(ClassRow(value, name, colour))
    return tuple(rows)


def _look_from_json(data: Any) -> Look | None:
    if data is None:
        return None
    if not isinstance(data, Mapping) or not {"colormap", "scale"} <= set(data) <= {"colormap", "scale", "low", "high"}:
        raise ValueError("a look has a colormap, a scale and maybe its ends")
    colormap, scale, low, high = data["colormap"], data["scale"], data.get("low"), data.get("high")
    if not isinstance(colormap, str) or scale not in ("measured", "percentiles", "fixed"):
        raise ValueError("a look has a colormap and one of the scales measured, percentiles, fixed")
    for end in (low, high):
        if end is not None and (isinstance(end, bool) or not isinstance(end, (int, float)) or not math.isfinite(end)):
            raise ValueError("the ends of a look are numbers")
    return Look(colormap, scale, low, high)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def band_meta(
    item: Mapping[str, Any],
    asset: str,
    *,
    unit: str | None = None,
    categorical: bool = False,
    classes: tuple[ClassRow, ...] | None = None,
    look: Look | None = None,
) -> BandMeta:
    """:class:`BandMeta` of ``asset`` from the item's own asset entry; ``unit``, ``classes`` and ``look`` are the
    registry's, the unit used where the item names none. A band of classes is categorical."""
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
        categorical=categorical or classes is not None,
        classes=classes,
        look=look,
    )


def band_meta_of_items(
    items: Sequence[Mapping[str, Any]],
    asset: str,
    *,
    unit: str | None = None,
    categorical: bool = False,
    classes: tuple[ClassRow, ...] | None = None,
    look: Look | None = None,
) -> BandMeta:
    """:class:`BandMeta` of ``asset`` over the items of an export: the first item's description, the finest pixel size of them all.

    The one place the crop and the job learn the pixel size of a band, so that they name the same file and lay the same grid.
    """
    holding = [item for item in items if asset in (item.get("assets") or {})]
    if not holding:
        return band_meta({}, asset, unit=unit, categorical=categorical, classes=classes, look=look)
    meta = band_meta(holding[0], asset, unit=unit, categorical=categorical, classes=classes, look=look)
    sizes = [size for item in holding if (size := asset_gsd(item, asset)) is not None]
    return replace(meta, resolution_m=min(sizes) if sizes else None)


def is_geotiff(entry: Any) -> bool:
    """Whether an asset entry of an item is a GeoTIFF that holds data (not a thumbnail)."""
    if not isinstance(entry, Mapping):
        return False
    kind = entry.get("type")
    roles = entry.get("roles")
    return isinstance(kind, str) and kind.lower().startswith("image/tiff") and not (isinstance(roles, list) and "thumbnail" in roles)


def holds_one_array(entry: Any) -> bool:
    """Whether an asset entry carries chunk references (``earthx:refs``, M5-11): one array of a day, one band."""
    return isinstance(entry, Mapping) and REFS_KEY in entry


def band_table(
    items: Sequence[Mapping[str, Any]],
    *,
    auxiliary: Iterable[str],
    mask_asset: str | None,
    unit_of: Callable[[str], str | None],
    classes_of: Callable[[str], tuple[ClassRow, ...] | None],
) -> list[tuple[BandMeta, bool]]:
    """The bands the download dialog offers for ``items``, in the first item's order, each with whether it starts ticked.

    The GeoTIFF assets of the first item, and its assets with chunk references (M5-11), without the pictures the registry
    calls auxiliary; the layer of the mask is one of them. Ticked from the start: the spectral bands (the item names a centre wavelength) and the mask layer; where a dataset has
    neither (an elevation model) every band.
    """
    if not items:
        return []
    skip = set(auxiliary)
    assets = items[0].get("assets") or {}
    metas = [
        band_meta_of_items(items, key, unit=unit_of(key), categorical=key == mask_asset, classes=classes_of(key))
        for key, entry in assets.items()
        if key not in skip and (is_geotiff(entry) or holds_one_array(entry))
    ]
    ticked = [meta.wavelength_um is not None or meta.categorical for meta in metas]
    if not any(ticked):
        ticked = [True] * len(metas)
    return list(zip(metas, ticked, strict=True))


def band_rows(
    items: Sequence[Mapping[str, Any]],
    *,
    auxiliary: Iterable[str],
    mask_asset: str | None,
    unit_of: Callable[[str], str | None],
    classes_of: Callable[[str], tuple[ClassRow, ...] | None],
) -> list[dict[str, Any]]:
    """The answer of ``POST /collections/{dataset}/bands``: :func:`band_table` with whether each band starts ticked and
    whether it can be stacked with others into one file. A band read through chunk references (M5-11) cannot: the stacked
    forms read GeoTIFFs, so it goes into a file of its own."""
    first = (items[0].get("assets") or {}) if items else {}
    return [
        {**meta.to_json(), "preselected": ticked, "stackable": not holds_one_array(first.get(meta.asset))}
        for meta, ticked in band_table(
            items, auxiliary=auxiliary, mask_asset=mask_asset, unit_of=unit_of, classes_of=classes_of
        )
    ]


def band_count(item: Mapping[str, Any], asset: str) -> int | None:
    """How many bands the item says ``asset`` has (``raster:bands`` or ``bands``); ``None`` where it says nothing."""
    assets = item.get("assets")
    entry = assets.get(asset) if isinstance(assets, Mapping) else None
    bands = (entry.get("raster:bands") or entry.get("bands")) if isinstance(entry, Mapping) else None
    return len(bands) if isinstance(bands, list) and bands else None


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


_DIFFERENT_NODATA = (
    "the bands of one file differ in their nodata, and a GeoTIFF has one for all its bands; choose one file per band"
)


def _same_nodata(plans: list[FilePlan], metas: Sequence[BandMeta]) -> list[FilePlan]:
    """``plans``, or :class:`ExportPlanError` where the bands of one stacked file differ in the nodata the items state."""
    nodata = {meta.asset: meta.nodata for meta in metas}
    for plan in plans:
        if len({"nan" if v is not None and math.isnan(v) else v for v in (nodata[a] for a in plan.assets)}) > 1:
            raise ExportPlanError(_DIFFERENT_NODATA)
    return plans


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
        plan = FilePlan(f"bands_{format_resolution(common_resolution)}m.tif", tuple(m.asset for m in metas), common_resolution)
        return _same_nodata([plan], metas)
    groups: list[tuple[float | None, list[str]]] = []
    for meta in metas:
        for resolution, assets in groups:
            if resolution is None and meta.resolution_m is None or _same(resolution, meta.resolution_m):
                assets.append(meta.asset)
                break
        else:
            groups.append((meta.resolution_m, [meta.asset]))
    plans = [
        FilePlan(
            f"bands_{format_resolution(resolution)}m.tif" if resolution is not None else "bands.tif",
            tuple(assets),
            resolution,
        )
        for resolution, assets in sorted(groups, key=lambda group: (group[0] is None, group[0] or 0.0))
    ]
    return _same_nodata(plans, metas)


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

    ``assets`` holds, per asset of the file, the opened datasets of the items in the order of the mosaic;
    ``methods`` the resampling of each asset (:func:`resampling_for`). An asset contributes its bands, one for the
    bands the export stacks and every band an asset has for the file of one asset. Every asset is a view of its
    dataset warped onto ``crs``/``transform``/``width``/``height``; where the dataset already has that grid (the CRS of
    the source and its pixel lattice, :func:`~earthx.access.crop_rules.source_crop_grid`) the view is a plain copy of
    its pixels. A scene in another CRS is warped onto the grid. The views live as long as ``stack``.
    """

    def __init__(
        self,
        assets: Sequence[Sequence[Any]],
        methods: Sequence[str],
        crs: Any,
        transform: Any,
        width: int,
        height: int,
        stack: ExitStack,
    ):
        self.height = height
        self.width = width
        self.crs = crs
        self.transform = transform
        self._vrts: list[list[Any]] = []
        for datasets, method in zip(assets, methods, strict=True):
            if len({dataset.count for dataset in datasets}) != 1:
                raise ExportPlanError("the scenes of a mosaic differ in their bands")
            self._vrts.append(
                [
                    stack.enter_context(
                        WarpedVRT(
                            dataset, crs=crs, transform=transform, width=width, height=height,
                            resampling=_WARP[method],
                        )  # fmt: skip
                    )
                    for dataset in datasets
                ]
            )
        first = [vrts[0] for vrts in self._vrts]
        self.dtype = numpy.result_type(*[numpy.dtype(vrt.dtypes[0]) for vrt in first]).name
        self.band_nodata = [kept_nodata(self.dtype, vrt.nodata) for vrt in first for _ in range(vrt.count)]
        self.count = len(self.band_nodata)
        if len({_nodata_key(value) for value in self.band_nodata}) > 1:
            # A GeoTIFF has one nodata for all its bands (M5-28, F2).
            raise ExportPlanError(_DIFFERENT_NODATA)
        self.nodata = self.band_nodata[0]

    def read(self, window: Window) -> numpy.ma.MaskedArray:
        """The block of every band, masked where no item has a value."""
        planes = [
            merge_first_valid(vrt.read(window=window, masked=True) for vrt in vrts).astype(self.dtype)
            for vrts in self._vrts
        ]
        return numpy.ma.concatenate(planes, axis=0)


def file_profile(reader: StackReader, *, block_size: int) -> dict[str, Any]:
    """The plain GeoTIFF profile of a file: the grid of ``reader`` and all its bands."""
    return {
        "driver": "GTiff",
        "dtype": reader.dtype,
        "count": reader.count,
        "height": reader.height,
        "width": reader.width,
        "crs": reader.crs,
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

    ``aoi`` is in the CRS of the grid (:func:`aoi_on_grid`).

    A pixel no item has a value for gets the file's nodata (:func:`kept_nodata`). The mask never changes the data (M3-18 §3).
    """
    fills = reader.band_nodata
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


def aoi_on_grid(aoi: Mapping[str, Any] | BaseGeometry, crs: Any) -> BaseGeometry:
    """The AOI (WGS84) in the CRS of an output grid, for its mask."""
    geometry = aoi if isinstance(aoi, Mapping) else mapping(aoi)
    return shape(transform_geom(WGS84_CRS, crs, dict(geometry)))


def apply_band_tags(dst: Any, metas: Sequence[BandMeta]) -> None:
    """The name of every band as its description, and the item's scale and offset as the file's; for a file of one
    band of classes in a type that can hold one, their colour table (all kept by ``cog_translate``; M5-62)."""
    for index, meta in enumerate(metas, start=1):
        dst.set_band_description(index, meta.name)
    dst.scales = tuple(1.0 if meta.scale is None else meta.scale for meta in metas)
    dst.offsets = tuple(0.0 if meta.offset is None else meta.offset for meta in metas)
    if len(metas) == 1 and metas[0].classes is not None and dst.dtypes[0] in PALETTE_TYPES:
        dst.write_colormap(1, colour_table(metas[0]))


def colour_table(meta: BandMeta) -> dict[int, tuple[int, int, int, int]]:
    """The colour of every class of ``meta`` as a GeoTIFF holds it, and its nodata. A TIFF keeps no alpha: a reader
    such as GDAL shows the entry of the file's own nodata see-through, which crop and export keep from the source."""
    assert meta.classes is not None
    return class_colour_table(meta.classes, meta.nodata)


def class_colour_table(classes: Sequence[ClassRow], nodata: float | None) -> dict[int, tuple[int, int, int, int]]:
    """The colour table of a band of ``classes`` with ``nodata`` see-through; also the one of a job's result (F9)."""
    table = {row.value: (*_rgb(row.colour), 255) for row in classes}
    if nodata is not None and math.isfinite(nodata) and float(nodata).is_integer():
        table[int(nodata)] = (0, 0, 0, 0)
    return table


def _rgb(colour: str) -> tuple[int, int, int]:
    return int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)


#: The largest value a list of names by index is written for (``uint16``); the attribute table names any value.
_MAX_CATEGORY = 65535

#: The columns of the attribute table of a band of classes: GDAL's type (0 integer, 2 text) and usage (5 the value,
#: 2 the name, 6-8 the colour), as GDAL writes them into a PAM file.
_RAT_FIELDS = (("Value", 0, 5), ("Class", 2, 2), ("Red", 0, 6), ("Green", 0, 7), ("Blue", 0, 8))


def class_aux_xml(bands: Sequence[BandMeta]) -> str | None:
    """``<file>.aux.xml`` of a file of ``bands``: the names (``CategoryNames``, the index is the value) and the attribute
    table of each band of classes, as GDAL writes them for a GeoTIFF; ``None`` where no band has classes."""
    parts = []
    for index, meta in enumerate(bands, start=1):
        if meta.classes is None:
            continue
        names = {row.value: row.name for row in meta.classes}
        categories = "".join(
            f"      <Category>{escape(names.get(value, ''))}</Category>\n" for value in range(max(names) + 1)
        ) if 0 <= min(names) and max(names) <= _MAX_CATEGORY else ""
        fields = "".join(
            f'      <FieldDefn index="{number}">\n        <Name>{name}</Name>\n        <Type>{kind}</Type>\n'
            f"        <Usage>{usage}</Usage>\n      </FieldDefn>\n"
            for number, (name, kind, usage) in enumerate(_RAT_FIELDS)
        )
        rows = "".join(
            f'      <Row index="{number}">\n'
            + "".join(f"        <F>{escape(str(cell))}</F>\n" for cell in (row.value, row.name, *_rgb(row.colour)))
            + "      </Row>\n"
            for number, row in enumerate(meta.classes)
        )
        parts.append(
            f'  <PAMRasterBand band="{index}">\n'
            + (f"    <CategoryNames>\n{categories}    </CategoryNames>\n" if categories else "")
            + f'    <GDALRasterAttributeTable tableType="thematic">\n{fields}{rows}    </GDALRasterAttributeTable>\n'
            + "  </PAMRasterBand>\n"
        )
    if not parts:
        return None
    return "<PAMDataset>\n" + "".join(parts) + "</PAMDataset>\n"


def class_files(files: Iterable[BandsFile]) -> list[tuple[str, str]]:
    """The ``.aux.xml`` beside each data file that holds a band of classes, as path in the ZIP and text."""
    return [(entry.path + AUX_SUFFIX, text) for entry in files if (text := class_aux_xml(entry.bands)) is not None]


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
        for index, meta in enumerate(entry.bands, start=1):
            if meta.classes is not None:
                lines += ["", f"Classes of band {index} ({meta.name})", "Value | Class | Colour"]
                lines += [f"{row.value} | {row.name} | {row.colour}" for row in meta.classes]
    return "\n".join(lines) + "\n"
