"""The methods text: a paragraph for a paper's methods section, from a ``recipe.json`` (M4-19a).

One pure function over the document every download already carries — the recipe with its
``provenance`` — so that the crop's ZIP, the export's, the job's and the local runner's folder
write the same text for the same run (plan ``m4-19-teilen-und-beschreiben.md`` §3.1). The text is
English, deterministic and built from what the document says; the title and DOI of the dataset
come in as :class:`DatasetFacts` because the worker core reads no registry.

Never in the text: the recipe's hash, an address, an identifier of a recipe or job, a coordinate
of the area. The area is a size and the target CRS (Otto, 20.10.2026, question 6).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from pyproj import Geod
from shapely.geometry import shape as shapely_shape

from earthx.access.crop_rules import METHODS_FILENAME
from earthx.catalog.registry import DatasetConfig, doi_name
from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators import REGISTRY
from earthx.processing.operators.registry import OperatorRegistry
from earthx.processing.recipe import (
    CropOutput,
    Provenance,
    Recipe,
    loads_i_json,
    recipe_from_data,
)

__all__ = ["METHODS_FILENAME", "DatasetFacts", "methods_text"]

_GEOD = Geod(ellps="WGS84")

_SCALING = {
    "item": "the scale and offset given in the item metadata",
    "store-cf": "the scale and offset stored with the data (CF conventions)",
}


@dataclass(frozen=True, slots=True)
class DatasetFacts:
    """What the text says of a dataset beside its identifier: the title and the DOI name, if any."""

    title: str
    doi: str | None = None

    @classmethod
    def of(cls, config: DatasetConfig) -> DatasetFacts:
        # The registry keeps the address of the DOI; the text names the DOI itself, as citation.bib does.
        return cls(config.title, doi_name(config.doi))

    def to_json(self) -> dict[str, Any]:
        return {"title": self.title, "doi": self.doi}

    @classmethod
    def from_json(cls, data: Any) -> DatasetFacts:
        if not isinstance(data, Mapping) or set(data) != {"title", "doi"}:
            raise ValueError("the dataset facts hold a title and a doi")
        title, doi = data["title"], data["doi"]
        if not isinstance(title, str) or not (doi is None or isinstance(doi, str)):
            raise ValueError("the dataset facts hold a title and a doi")
        return cls(title, doi)


def methods_text(
    document: bytes | str | Mapping[str, Any],
    *,
    dataset: DatasetFacts | None = None,
    acquired_on: date | None = None,
    operators: OperatorRegistry = REGISTRY,
) -> str:
    """The paragraph for ``document``, a ``recipe.json`` with its ``provenance``.

    ``acquired_on`` is the UTC day of the overpass, as `api` found it for the file names too
    (``catalog.registry.acquisition_day``); the sentence is left out where there is none — a
    dataset without a single day, a source that does not know it — and the day of the run is never
    put in its place (Otto, 22.10.2026).

    :class:`~earthx.processing.errors.RecipeInvalid` for a document that is not one; the text
    names no value of it.
    """
    data = loads_i_json(document) if isinstance(document, bytes | str) else dict(document)
    if not isinstance(data, dict) or "provenance" not in data:
        raise RecipeInvalid("a recipe.json holds a recipe and its provenance")
    provenance_data = data.pop("provenance")
    recipe = recipe_from_data(data, operators)
    try:
        provenance = Provenance.model_validate_json(json.dumps(provenance_data, allow_nan=False))
    except ValueError:
        raise RecipeInvalid("the provenance of the recipe is not valid") from None
    sentences = [
        *_data_sentences(recipe, dataset),
        _acquired_sentence(acquired_on),
        *_scaling_sentences(provenance),
        *_step_sentences(recipe, operators),
        _output_sentence(recipe),
        _area_sentence(recipe),
        _software_sentence(provenance),
        *provenance.attribution,
    ]
    return " ".join(sentence for sentence in sentences if sentence) + "\n"


def _data_sentences(recipe: Recipe, dataset: DatasetFacts | None) -> list[str]:
    sentences = []
    for entry in recipe.inputs:
        scenes = sum(len(group) for group in entry.groups)
        name = entry.dataset
        if dataset is not None:
            name = f"{dataset.title} ({entry.dataset}" + (f", doi:{dataset.doi}" if dataset.doi else "") + ")"
        sentences.append(f"The dataset {name} was used: {_count(scenes, 'scene')}, {_list(entry.assets, 'asset')}.")
        if any(len(group) > 1 for group in entry.groups):
            sentences.append(
                "Scenes of one overpass were mosaicked; where they overlap, the first valid pixel of a fixed order wins."
            )
    return sentences


def _acquired_sentence(acquired_on: date | None) -> str:
    return f"The scenes were acquired on {acquired_on.isoformat()} (UTC)." if acquired_on is not None else ""


def _scaling_sentences(provenance: Provenance) -> list[str]:
    """One sentence per way of scaling the run reports: where the physical values came from."""
    used = []
    for entry in provenance.scaling:
        if entry.source in _SCALING and entry.source not in used:
            used.append(entry.source)
    return [f"The raw values were converted to physical values with {_SCALING[source]}." for source in used]


def _step_sentences(recipe: Recipe, operators: OperatorRegistry) -> list[str]:
    sentences = []
    for step in recipe.steps:
        operator = operators.operator(step.op, step.op_version)
        sentences.append(
            operator.method(operator.params.model_validate_json(json.dumps(step.params, allow_nan=False), strict=True))
        )
    return sentences


def _output_sentence(recipe: Recipe) -> str:
    output = recipe.output
    if isinstance(output, CropOutput):
        resolution = (
            "at the native resolution"
            if output.resolution_factor == 1
            else f"at {output.resolution_factor}x coarser than the native resolution"
        )
        return (
            "The scenes were cropped to the bounding box of the area of interest and the scene footprints, "
            f"{resolution}, without changing a pixel value; a mask file marks the pixels inside the area."
        )
    return f"The result was written as a cloud-optimised GeoTIFF with {output.dtype} values."


def _area_sentence(recipe: Recipe) -> str:
    """The size of the area, no coordinate; the target CRS where a step names one."""
    try:
        square_km = abs(_GEOD.geometry_area_perimeter(shapely_shape(recipe.aoi.model_dump(mode="json")))[0]) / 1e6
    except (ValueError, TypeError, AttributeError):
        return ""
    size = f"{square_km:,.0f}" if square_km >= 10 else f"{square_km:.1f}"
    return f"The processed area covers about {size} km²."


def _software_sentence(provenance: Provenance) -> str:
    engine = provenance.engine
    names = (
        ("earthx", "EarthX"),
        ("gdal", "GDAL"),
        ("rasterio", "rasterio"),
        ("numexpr", "numexpr"),
        ("numpy", "numpy"),
    )
    software = ", ".join(f"{label} {engine[key]}" for key, label in names if key in engine)
    when = _day(provenance.finished or provenance.started)
    if provenance.execution == "local":
        where = f"It was recomputed on the user's own machine with the EarthX runner {provenance.runner_version}"
        where += f" (self-attested{when})"
    elif provenance.kind == "sync-download":
        where = f"It was cut on the EarthX platform{when}"
    else:
        where = f"It was processed on the EarthX platform{when}"
    return f"{where}. Software: {software}." if software else f"{where}."


def _day(moment: datetime | None) -> str:
    return f" on {moment.date().isoformat()}" if moment is not None else ""


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" + ("" if number == 1 else "s")


def _list(names: Sequence[str], noun: str) -> str:
    return f"{_count(len(names), noun)} ({', '.join(names)})"
