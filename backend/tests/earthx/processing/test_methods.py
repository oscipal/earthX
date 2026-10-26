"""The methods text (M4-19a): one paragraph from a ``recipe.json``, the same for every download.

Everything is synthetic. The text names the dataset, the scenes, the scaling, each step, the
output, the size of the area and the software, and never a hash, an identifier or a coordinate.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from typing import Any

import pytest

from earthx.processing.errors import RecipeInvalid
from earthx.processing.methods import DatasetFacts, methods_of, methods_text, recipe_with_methods
from earthx.processing.operators import REGISTRY
from earthx.processing.recipe import Provenance, job_recipe_document, loads_i_json, recipe_from_data, recipe_hash
from tests.earthx.processing import recipes
from tests.earthx.processing.testops import OPERATORS

ENGINE = {"earthx": "0.4.1", "gdal": "3.12.2", "rasterio": "1.5.0", "numexpr": "2.14.1", "numpy": "2.3.0"}
FACTS = DatasetFacts("Sentinel-2 L2A", "10.5270/S2_-742ikth")
ATTRIBUTION = "Contains modified Copernicus Sentinel data 2026"
RECIPE_ID = "A" * 22
SCALING = [{"input": "s2", "asset": "red", "source": "item", "scales": [0.0001], "offsets": [-0.1]}]


def document(data: dict[str, Any], *, scaling: list[dict[str, Any]] | None = None, finished: bool = True) -> bytes:
    return job_recipe_document(
        data,
        attribution=[ATTRIBUTION],
        result={"engine": ENGINE, "scaling": scaling or []},
        started=datetime(2026, 10, 20, 8, 0, tzinfo=UTC),
        finished=datetime(2026, 10, 20, 8, 1, tzinfo=UTC) if finished else None,
    )


def band_math(expression: str = "(nir - red) / (nir + red)") -> dict[str, Any]:
    return recipes.recipe_data(
        steps=[{"op": "band_math", "op_version": 1, "params": {"expression": expression}}], recipe_id=RECIPE_ID
    )


class TestTheParagraph:
    def test_it_names_the_data_the_scaling_the_step_the_output_the_area_and_the_software(self) -> None:
        text = methods_text(document(band_math(), scaling=SCALING), dataset=FACTS)
        assert text == (
            "The dataset Sentinel-2 L2A (synthetic, doi:10.5270/S2_-742ikth) was used: 1 scene, 2 assets (red, nir). "
            "The raw values were converted to physical values with the scale and offset given in the item metadata. "
            "One band was computed per pixel from the expression '(nir - red) / (nir + red)' on physical values, "
            "in 32-bit floating point. "
            "The result was written as a cloud-optimised GeoTIFF with float32 values. "
            "The processed area covers about 0.8 km². "
            "It was processed on the EarthX platform on 2026-10-20. "
            "Software: EarthX 0.4.1, GDAL 3.12.2, rasterio 1.5.0, numexpr 2.14.1, numpy 2.3.0. "
            f"{ATTRIBUTION}\n"
        )

    def test_it_says_what_reproject_did_with_its_resampling(self) -> None:
        params = {"crs": "EPSG:3035", "resolution": 10.0, "resampling": "bilinear"}
        data = recipes.recipe_data(steps=[{"op": "reproject", "op_version": 3, "params": params}])
        text = methods_text(document(data), dataset=None)
        assert "reprojected to EPSG:3035 with a pixel size of 10 in the units of the target CRS" in text
        assert "using bilinear resampling (distance-weighted mean" in text
        assert "snapped" not in text

    def test_an_aligned_grid_is_said(self) -> None:
        params = {"crs": "EPSG:3035", "resolution": 10.0, "resampling": "nearest", "align": True}
        data = recipes.recipe_data(steps=[{"op": "reproject", "op_version": 3, "params": params}])
        assert "snapped to whole multiples of the pixel size" in methods_text(document(data))

    def test_the_steps_come_in_the_order_of_the_recipe(self) -> None:
        steps = [
            {"op": "scale", "op_version": 1, "params": {"factor": 2.0}},
            {"op": "coarsen", "op_version": 1, "params": {"factor": 2}},
        ]
        text = methods_text(document(recipes.recipe_data(steps=steps)), operators=OPERATORS)
        assert text.index("multiplied by 2.0") < text.index("coarsened by 2")

    def test_scenes_of_one_overpass_are_said_to_be_mosaicked(self) -> None:
        data = band_math()
        data["inputs"][0]["groups"] = [["ITEM_A", "ITEM_B"]]
        data["inputs"][0]["resolved"] += [recipes.resolved("ITEM_B", "red"), recipes.resolved("ITEM_B", "nir")]
        text = methods_text(document(data))
        assert "2 scenes" in text and "mosaicked" in text and "first valid pixel" in text
        assert "mosaicked" not in methods_text(document(band_math()))

    def test_the_scaling_of_the_store_is_told_apart_from_the_items(self) -> None:
        scaling = [{**SCALING[0], "source": "store-cf"}]
        text = methods_text(document(band_math(), scaling=scaling))
        assert "stored with the data (CF conventions)" in text and "item metadata" not in text

    def test_data_without_a_scaling_says_nothing_about_one(self) -> None:
        none = [{**SCALING[0], "source": "none", "scales": [], "offsets": []}]
        assert "physical values with" not in methods_text(document(band_math(), scaling=none))

    def test_a_crop_is_said_to_change_no_pixel_value(self) -> None:
        text = methods_text(document(recipes.crop_data()), operators=OPERATORS)
        assert "cropped to the bounding box" in text and "without changing a pixel value" in text
        assert "at the native resolution" in text and "mask file" in text

    def test_a_coarser_crop_names_its_factor(self) -> None:
        data = recipes.crop_data()
        data["output"] = {**recipes.CROP, "resolution_factor": 4}
        assert "at 4x coarser than the native resolution" in methods_text(document(data))

    def test_a_dataset_without_facts_is_named_by_its_identifier(self) -> None:
        assert methods_text(document(band_math())).startswith("The dataset synthetic was used:")

    def test_without_a_finish_the_text_names_no_day(self) -> None:
        # The start stands in for a missing finish; a document with neither names no day.
        assert "on 2026-10-20" in methods_text(document(band_math(), finished=False))
        data = json.loads(document(band_math()))
        data["provenance"]["started"] = data["provenance"]["finished"] = None
        assert "It was processed on the EarthX platform. Software" in methods_text(data)

    def test_a_download_of_the_crop_is_cut_not_processed(self) -> None:
        data = json.loads(document(recipes.crop_data()))
        data["provenance"]["kind"] = "sync-download"
        assert "It was cut on the EarthX platform" in methods_text(data)

    def test_a_local_run_says_so(self) -> None:
        data = json.loads(document(band_math()))
        data["provenance"].update(execution="local", self_attested=True, runner_version="0.4.1+gabcdef0")
        text = methods_text(data)
        assert "recomputed on the user's own machine with the EarthX runner 0.4.1+gabcdef0 (self-attested on" in text

    def test_it_is_the_same_text_from_bytes_text_and_data(self) -> None:
        raw = document(band_math())
        assert methods_text(raw) == methods_text(raw.decode("utf-8")) == methods_text(json.loads(raw))

    def test_it_is_deterministic(self) -> None:
        assert methods_text(document(band_math())) == methods_text(document(band_math()))


class TestTheDayOfAcquisition:
    """Otto, 22.10.2026: the day of the overpass as `api` found it, else no sentence; never the day of the run."""

    def test_the_day_stands_after_the_data_and_before_the_steps(self) -> None:
        text = methods_text(document(band_math()), acquired_on=date(2026, 6, 1))
        assert "The scenes were acquired on 2026-06-01 (UTC)." in text
        assert text.index("was used") < text.index("acquired on") < text.index("One band was computed")

    def test_without_a_day_there_is_no_sentence_and_the_day_of_the_run_is_not_put_in_its_place(self) -> None:
        text = methods_text(document(band_math()))
        assert "acquired" not in text
        assert "processed on the EarthX platform on 2026-10-20" in text, "the run keeps its own day"

    def test_the_day_of_the_overpass_is_not_the_day_of_the_run(self) -> None:
        text = methods_text(document(band_math()), acquired_on=date(2026, 6, 1))
        assert "acquired on 2026-10-20" not in text and "processed on the EarthX platform on 2026-10-20" in text

    def test_a_local_run_without_the_source_has_no_sentence(self) -> None:
        data = json.loads(document(band_math()))
        data["provenance"].update(execution="local", self_attested=True, runner_version="0.4.1+gabcdef0")
        assert "acquired" not in methods_text(data)


class TestWhatIsNeverInTheText:
    def test_no_identifier_hash_address_or_coordinate(self) -> None:
        data = band_math()
        text = methods_text(document(data), dataset=FACTS)
        assert RECIPE_ID not in text
        assert "https://" not in text and recipes.HOST not in text
        assert "c1:" not in text and "ITEM_A" not in text
        assert "47.0" not in text and "9.01" not in text and "47.01" not in text

    def test_the_area_is_a_size_only(self) -> None:
        assert "covers about 0.8 km²" in methods_text(document(band_math()))
        big = band_math()
        big["aoi"] = {
            "type": "Polygon",
            "coordinates": [[[9.0, 47.0], [10.0, 47.0], [10.0, 48.0], [9.0, 48.0], [9.0, 47.0]]],
        }
        assert re.search(r"covers about 8,\d{3} km²", methods_text(document(big)))


class TestADocumentThatIsNotARecipe:
    @pytest.mark.parametrize("raw", [b"", b"not json", b"[]", b"{}", b'{"recipe_version": 1}', b'{"a": 1, "a": 2}'])
    def test_it_is_refused_without_naming_a_value(self, raw: bytes) -> None:
        with pytest.raises(RecipeInvalid):
            methods_text(raw)

    def test_a_provenance_that_is_not_one_is_refused(self) -> None:
        data = json.loads(document(band_math()))
        data["provenance"] = {"execution": "cloud"}
        with pytest.raises(RecipeInvalid):
            methods_text(data)

    def test_an_operator_the_registry_does_not_know_is_refused(self) -> None:
        data = recipes.recipe_data(steps=[{"op": "scale", "op_version": 1, "params": {"factor": 2.0}}])
        with pytest.raises(RecipeInvalid):
            methods_text(document(data), operators=REGISTRY)

    def test_a_parameter_that_does_not_validate_is_refused(self) -> None:
        data = json.loads(document(band_math()))
        data["steps"][0]["params"] = {"expression": "import os"}
        with pytest.raises(RecipeInvalid):
            methods_text(data)


class TestEveryOperatorSaysItsStep:
    """The guard for the next operator (M4-18): a registered operator without a sentence fails here."""

    SAMPLES = {
        "band_math": {"expression": "nir - red"},
        "mask": {"source": "scl", "classes": [3, 8, 9, 10]},
        "normalize": {"in_min": 0.0, "in_max": 0.5, "out_min": 0.0, "out_max": 255.0, "clip": True},
        "reproject": {"crs": "EPSG:3035", "resolution": 10.0, "resampling": "bilinear"},
    }

    @pytest.mark.parametrize(("op", "version"), sorted(REGISTRY))
    def test_the_sentence_is_text_without_a_placeholder(self, op: str, version: int) -> None:
        assert op in self.SAMPLES, f"{op}: give the guard sample parameters"
        operator = REGISTRY.operator(op, version)
        sentence = operator.method(operator.params.model_validate(self.SAMPLES[op]))
        assert sentence.strip() and sentence.endswith(".")
        assert "{" not in sentence and "None" not in sentence


class TestTheTextLiesInTheRecipe:
    """NM4-08: ``provenance.methods`` of ``recipe.json``, no file of its own; outside the hash."""

    def test_the_provenance_carries_the_text_the_function_writes(self) -> None:
        raw = recipe_with_methods(document(band_math()), dataset=FACTS, acquired_on=date(2026, 6, 1))
        written = json.loads(raw)["provenance"]["methods"]
        assert written + "\n" == methods_text(document(band_math()), dataset=FACTS, acquired_on=date(2026, 6, 1))
        assert written.startswith("The dataset Sentinel-2 L2A (synthetic, doi:10.5270/S2_-742ikth) was used")
        assert methods_of(raw) == written

    def test_the_rest_of_the_document_stays_as_it_was(self) -> None:
        before = json.loads(document(band_math()))
        after = json.loads(recipe_with_methods(document(band_math())))
        assert before["provenance"].pop("methods") is None
        assert {key: value for key, value in after["provenance"].items() if key != "methods"} == before["provenance"]
        assert {key: value for key, value in after.items() if key != "provenance"} == {
            key: value for key, value in before.items() if key != "provenance"
        }

    def test_the_form_is_the_one_of_every_recipe_json(self) -> None:
        raw = recipe_with_methods(document(band_math()))
        assert raw.endswith(b"\n") and raw.startswith(b'{\n  "aoi"')
        assert recipe_with_methods(raw) == raw, "a second call changes nothing"

    def test_the_hash_does_not_change(self) -> None:
        plain = loads_i_json(document(band_math()))
        embedded = loads_i_json(recipe_with_methods(document(band_math())))
        hashes = []
        for data in (plain, embedded):
            data.pop("provenance")
            hashes.append(recipe_hash(recipe_from_data(data, OPERATORS)))
        assert hashes[0] == hashes[1]

    def test_a_text_that_is_already_there_is_replaced_by_the_one_that_fits(self) -> None:
        data = json.loads(document(band_math()))
        data["provenance"]["methods"] = "Stale."
        assert methods_of(recipe_with_methods(data)) == methods_text(document(band_math())).removesuffix("\n")

    def test_a_document_from_before_has_no_text(self) -> None:
        assert methods_of(document(band_math())) is None
        old = json.loads(document(band_math()))
        del old["provenance"]["methods"]
        assert methods_of(old) is None
        assert Provenance.model_validate_json(json.dumps(old["provenance"])).methods is None
        assert methods_text(document(band_math())), "and the text is still written from it"

    def test_the_text_names_no_identifier_hash_address_or_coordinate_in_the_document_either(self) -> None:
        raw = recipe_with_methods(document(band_math()), dataset=FACTS).decode("utf-8")
        text = json.loads(raw)["provenance"]["methods"]
        assert RECIPE_ID not in text and "c1:" not in text and "https://" not in text and "47.0" not in text

    @pytest.mark.parametrize("methods", ["", 3, ["a"], {"a": 1}, True])
    def test_a_text_of_the_wrong_kind_is_refused(self, methods: Any) -> None:
        data = json.loads(document(band_math()))
        data["provenance"]["methods"] = methods
        with pytest.raises(RecipeInvalid):
            methods_text(data)
        with pytest.raises(RecipeInvalid):
            recipe_with_methods(data)

    @pytest.mark.parametrize("raw", [b"", b"[]", b"{}", b'{"recipe_version": 1}', b'{"a": 1, "a": 2}'])
    def test_a_document_that_is_not_a_recipe_json_is_refused_by_both(self, raw: bytes) -> None:
        with pytest.raises(RecipeInvalid):
            recipe_with_methods(raw)
        if raw not in (b"{}", b'{"recipe_version": 1}'):
            with pytest.raises(RecipeInvalid):
                methods_of(raw)

    def test_a_provenance_that_is_no_object_has_no_text(self) -> None:
        data = json.loads(document(band_math()))
        data["provenance"] = "x"
        with pytest.raises(RecipeInvalid):
            methods_of(data)


class TestDatasetFacts:
    def test_they_survive_json(self) -> None:
        assert DatasetFacts.from_json(FACTS.to_json()) == FACTS
        assert DatasetFacts.from_json(DatasetFacts("T", None).to_json()) == DatasetFacts("T")

    @pytest.mark.parametrize(
        "data", [None, [], {}, {"title": "T"}, {"title": 1, "doi": None}, {"title": "T", "doi": 3}]
    )
    def test_anything_else_is_refused(self, data: Any) -> None:
        with pytest.raises(ValueError):
            DatasetFacts.from_json(data)
