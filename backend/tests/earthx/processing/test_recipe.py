"""Order and recipe models, canonical form ``c1`` and hash (adr/0014 §4, condition F2)."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import fields

import pytest

import earthx
from earthx.access.resolve import ResolvedAsset
from earthx.processing.errors import RecipeInvalid, UnknownOperator
from earthx.processing.recipe import (
    Provenance,
    ResolvedAssetModel,
    cache_key,
    canonical_bytes,
    engine_versions,
    input_version,
    loads_i_json,
    parse_recipe,
    parse_request,
    recipe_from_data,
    recipe_hash,
    recipe_hosts,
    run_key,
)
from tests.earthx.processing.recipes import recipe_data, request_data, resolved
from tests.earthx.processing.testops import OPERATORS

#: Fixed on purpose (condition F2): a change here is a change of method `c1`, and
#: every cache key computed before it would silently stop matching.
#:
#: Renewed on purpose by M4-19b (adr/0014 §15n): ``Band.unit`` and ``ResolvedInput.unit`` entered the core, so
#: every recipe carries two more keys (``"unit":null``) and every key computed before misses once. The method
#: itself did not change: ``OLD`` below are the values before, and ``test_only_the_two_unit_keys_changed_them``
#: derives them from the new core by taking those keys out.
#:
#: Renewed on purpose again by NM4-43c (adr/0014 Nachtrag NM4-43c): ``recipe_version`` is 2 and the output carries
#: ``bands``, so every key computed before misses once. The method did not change: the test derives ``OLD`` from the new
#: core by setting the version back to 1 and taking ``bands`` out.
EXPECTED = {
    "base": "c1:20a37ee4aa8a77c4551d618b4b817b17f9a95dc072d6bec0a0350cfca6620580",
    "non_ascii": "c1:dd15544153ae28ea7e705d35c349d4f8522fa1a880600910b9118f818d6f0b1a",
    "small_float": "c1:32c72e7d488a480547556f67446b6945d380fcc4507a5abf1ca3f0f095a5b536",
    "zarr": "c1:8adb17e3139f7c6f82dc065e2ce6dfc6a9f4d1a05d8887730b65a75afaff8681",
}
OLD = {
    "base": "c1:db05e56f9323422467188e8899b4d4c69772794d785e9c7ecf27041b3666467d",
    "non_ascii": "c1:86c3092e8705c6a45438c1b61e290572f297ae02d5102833c6423674431e938b",
    "small_float": "c1:63f87919039f7b2dd54b24362e08ae343d947aec2f504c18ba86f15e443bfeab",
    "zarr": "c1:95973cb5a56e652a266976e74df9e945ff92bd304c42f6d4bc444b59609d9c36",
}


def _with_params(params: dict) -> dict:
    return recipe_data(steps=[{"op": "scale", "op_version": 1, "params": params}])


def _zarr_recipe() -> dict:
    entry = resolved(
        "ITEM_Z",
        "r10m:b04,b08",
        reader="zarr",
        scale=None,
        offset=None,
        version={"kind": "updated", "value": "2026-10-01T00:00:00Z"},
        href="https://store.example.invalid/p.zarr/r10m",
        variable="b04,b08",
    )
    return recipe_data(
        inputs=[
            {
                "name": "z",
                "dataset": "synthetic",
                "groups": [["ITEM_Z"]],
                "assets": ["r10m:b04,b08"],
                "resolved": [entry],
            }
        ],
        output={**recipe_data()["output"], "bands": ["b04", "b08"]},
    )


def _hash(data: dict) -> str:
    return recipe_hash(recipe_from_data(data, OPERATORS))


class TestFixedHashes:
    @pytest.mark.parametrize(
        ("case", "data"),
        [
            ("base", recipe_data()),
            ("non_ascii", _with_params({"factor": 2.0, "label": "Größe ≥ 1"})),
            ("small_float", _with_params({"factor": 1e-7})),
            ("zarr", _zarr_recipe()),
        ],
    )
    def test_the_hash_is_the_recorded_one(self, case: str, data: dict) -> None:
        assert _hash(data) == EXPECTED[case]

    @pytest.mark.parametrize(
        ("case", "data"),
        [
            ("base", recipe_data()),
            ("non_ascii", _with_params({"factor": 2.0, "label": "Größe ≥ 1"})),
            ("small_float", _with_params({"factor": 1e-7})),
            ("zarr", _zarr_recipe()),
        ],
    )
    def test_only_the_unit_keys_and_the_bands_of_version_2_changed_them(self, case: str, data: dict) -> None:
        core = recipe_from_data(data, OPERATORS).model_dump(mode="json", exclude={"recipe_id"})
        core["recipe_version"] = 1
        assert core["output"].pop("bands")
        for entry in core["inputs"]:
            for asset in entry["resolved"]:
                assert asset.pop("unit") is None
                for band in asset["bands"]:
                    assert band.pop("unit") is None
        assert "c1:" + hashlib.sha256(canonical_bytes(core)).hexdigest() == OLD[case]

    def test_the_canonical_bytes_follow_the_rules_of_4_4(self) -> None:
        data = {"b": 1.0, "a": -0.0, "c": "ä", "d": 1e-7, "e": [3, 1], "f": {"z": None, "y": True}}
        assert canonical_bytes(data) == '{"a":0.0,"b":1.0,"c":"ä","d":1e-07,"e":[3,1],"f":{"y":true,"z":null}}'.encode()

    def test_the_hash_is_sha256_over_those_bytes(self) -> None:
        recipe = recipe_from_data(recipe_data(), OPERATORS)
        core = recipe.model_dump(mode="json", exclude={"recipe_id"})
        assert recipe_hash(recipe) == "c1:" + hashlib.sha256(canonical_bytes(core)).hexdigest()


class TestWhatTheHashIgnoresAndWhatItSees:
    def test_an_int_for_a_float_parameter_gives_the_same_hash(self) -> None:
        assert _hash(_with_params({"factor": 2})) == _hash(_with_params({"factor": 2.0})) == EXPECTED["base"]

    def test_minus_zero_and_zero_give_the_same_hash(self) -> None:
        assert _hash(_with_params({"factor": -0.0})) == _hash(_with_params({"factor": 0.0}))

    def test_key_order_in_the_input_does_not_matter(self) -> None:
        data = recipe_data()
        reordered = dict(reversed(list(data.items())))
        reordered["inputs"] = [dict(reversed(list(entry.items()))) for entry in data["inputs"]]
        assert json.dumps(reordered) != json.dumps(data)
        assert _hash(reordered) == EXPECTED["base"]

    def test_the_recipe_id_is_not_part_of_the_hash(self) -> None:
        assert _hash(recipe_data(recipe_id="A" * 22)) == EXPECTED["base"]

    def test_an_eighth_decimal_of_the_aoi_is_another_order(self) -> None:
        data = recipe_data()
        data["aoi"]["coordinates"][0][1][0] = 9.01000001
        assert _hash(data) != EXPECTED["base"]

    def test_the_order_of_steps_matters(self) -> None:
        steps = [
            {"op": "scale", "op_version": 1, "params": {"factor": 2.0}},
            {"op": "scale", "op_version": 1, "params": {"factor": 3.0}},
        ]
        assert _hash(recipe_data(steps=steps)) != _hash(recipe_data(steps=list(reversed(steps))))

    def test_the_unit_of_a_band_is_part_of_the_hash(self) -> None:
        data = recipe_data()
        data["inputs"][0]["resolved"][0]["bands"][0]["unit"] = "1"
        assert _hash(data) != EXPECTED["base"]

    def test_the_unit_of_an_input_is_part_of_the_hash(self) -> None:
        data = recipe_data()
        entry = data["inputs"][0]["resolved"][0]
        entry.update(bands=[], scaling="none", unit="m")
        other = recipe_data()
        other["inputs"][0]["resolved"][0].update(bands=[], scaling="none")
        assert _hash(data) != _hash(other)

    def test_the_version_of_an_input_is_part_of_the_hash(self) -> None:
        data = recipe_data()
        data["inputs"][0]["resolved"][0]["version"]["value"] = "1220other"
        assert _hash(data) != EXPECTED["base"]


class TestRefusals:
    """Everything that would otherwise be accepted silently or differently (§4.3, §4.4, K7)."""

    @pytest.mark.parametrize(
        "raw",
        [
            '{"recipe_version": 1, "recipe_version": 1}',
            '{"a": NaN}',
            '{"a": Infinity}',
            '{"a": -Infinity}',
            '{"a": 1e400}',
            '{"a": 9007199254740993}',
            "not json",
            "",
        ],
    )
    def test_text_that_is_not_i_json(self, raw: str) -> None:
        with pytest.raises(RecipeInvalid):
            parse_recipe(raw, OPERATORS)

    @pytest.mark.parametrize(
        ("path", "value"),
        [
            (("recipe_version",), 1),
            (("recipe_version",), 3),
            (("recipe_version",), 1.0),
            (("recipe_version",), True),
            (("recipe_version",), "1"),
            (("steps", 0, "op_version"), 1.0),
            (("steps", 0, "op_version"), 0),
            (("inputs", 0, "resolved", 0, "gsd"), "10"),
            (("inputs", 0, "resolved", 0, "gsd"), -10.0),
            (("inputs", 0, "resolved", 0, "asset", "reader"), "netcdf"),
            (("inputs", 0, "name"), "1st"),
            (("inputs", 0, "assets"), ["red", "red"]),
            (("inputs", 0, "groups"), [["ITEM_A"], ["ITEM_A"]]),
            (("output", "kind"), "vector"),
            (("output", "dtype"), "complex64"),
            (("output", "bands"), []),
            (("output", "bands"), ["red", "RED"]),
            (("output", "bands"), ["red", "red"]),
            (("output", "bands"), "red"),
            (("output", "bands"), [1]),
            (("output", "bands"), ["1st"]),
            (("output", "bands"), ["red band"]),
            (("output", "bands"), [""]),
            (("aoi", "type"), "Point"),
            (("aoi", "coordinates"), [[[9.0, 47.0], [9.01, 47.0], [9.0, 47.0]]]),
            (("aoi", "coordinates"), [[[9.0, 47.0], [9.01, 47.0], [9.01, 47.01], [9.0, 47.01]]]),
            (("aoi", "coordinates"), [[[0.0, 0.0], [1.0, 1.0], [1.0, 0.0], [0.0, 1.0], [0.0, 0.0]]]),
            (("aoi", "coordinates"), [[[190.0, 47.0], [191.0, 47.0], [191.0, 48.0], [190.0, 47.0]]]),
            (("aoi", "coordinates"), [[[9.0, 47.0, 500.0], [9.01, 47.0, 1.0], [9.0, 47.01, 1.0], [9.0, 47.0, 1.0]]]),
        ],
    )
    def test_a_field_with_the_wrong_value_or_type(self, path: tuple, value: object) -> None:
        data = recipe_data()
        target = data
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = value
        with pytest.raises(RecipeInvalid):
            recipe_from_data(data, OPERATORS)

    def test_an_unknown_field_anywhere(self) -> None:
        for target in ("top", "input", "resolved", "asset", "band", "step"):
            data = recipe_data()
            node = {
                "top": data,
                "input": data["inputs"][0],
                "resolved": data["inputs"][0]["resolved"][0],
                "asset": data["inputs"][0]["resolved"][0]["asset"],
                "band": data["inputs"][0]["resolved"][0]["bands"][0],
                "step": data["steps"][0],
            }[target]
            node["unexpected"] = 1
            with pytest.raises(RecipeInvalid):
                recipe_from_data(data, OPERATORS)

    def test_an_unknown_operator_or_version(self) -> None:
        for step in ({"op": "nope", "op_version": 1, "params": {}}, {"op": "scale", "op_version": 2, "params": {}}):
            with pytest.raises(UnknownOperator):
                recipe_from_data(recipe_data(steps=[step]), OPERATORS)

    @pytest.mark.parametrize("params", [{}, {"factor": "2"}, {"factor": True}, {"factor": 2.0, "extra": 1}])
    def test_parameters_the_operator_does_not_accept(self, params: dict) -> None:
        with pytest.raises(RecipeInvalid):
            recipe_from_data(_with_params(params), OPERATORS)

    def test_a_resolved_list_that_does_not_match_items_and_assets(self) -> None:
        for change in ("missing", "extra", "foreign_dataset"):
            data = recipe_data()
            entries = data["inputs"][0]["resolved"]
            if change == "missing":
                entries.pop()
            elif change == "extra":
                entries.append(resolved("ITEM_B", "red"))
            else:
                entries[0]["asset"]["dataset_id"] = "other"
            with pytest.raises(RecipeInvalid):
                recipe_from_data(data, OPERATORS)

    @pytest.mark.parametrize(
        ("reader", "scaled", "scaling"),
        [
            ("cog", True, "none"),
            ("cog", False, "item"),
            ("cog", False, "store-cf"),
            ("zarr", False, "none"),
            ("zarr", True, "store-cf"),
        ],
    )
    def test_a_scaling_source_that_contradicts_the_bands(self, reader: str, scaled: bool, scaling: str) -> None:
        data = recipe_data()
        entry = data["inputs"][0]["resolved"][0]
        entry["asset"]["reader"] = reader
        entry["bands"][0]["scale"] = 0.0001 if scaled else None
        entry["bands"][0]["offset"] = None
        entry["scaling"] = scaling
        with pytest.raises(RecipeInvalid):
            recipe_from_data(data, OPERATORS)

    @pytest.mark.parametrize("unit", ["", 5, ["m"], {"symbol": "m"}, "x" * 257, True])
    @pytest.mark.parametrize("where", ["band", "input"])
    def test_a_unit_that_is_no_usable_text(self, where: str, unit) -> None:
        data = recipe_data()
        entry = data["inputs"][0]["resolved"][0]
        if where == "band":
            entry["bands"][0]["unit"] = unit
        else:
            entry.update(bands=[], scaling="none", unit=unit)
        with pytest.raises(RecipeInvalid):
            recipe_from_data(data, OPERATORS)

    def test_a_recipe_written_before_units_still_reads(self) -> None:
        """A ``recipe.json`` in a ZIP from earlier carries no ``unit`` anywhere; the runner has to run it."""
        data = recipe_data()
        assert "unit" not in data["inputs"][0]["resolved"][0]
        assert "unit" not in data["inputs"][0]["resolved"][0]["bands"][0]
        recipe = recipe_from_data(data, OPERATORS)
        resolved_input = recipe.inputs[0].resolved[0]
        assert (resolved_input.unit, resolved_input.bands[0].unit) == (None, None)

    def test_the_error_text_names_fields_never_values(self) -> None:
        data = recipe_data()
        data["inputs"][0]["resolved"][0]["asset"]["href"] = 12345
        data["aoi"]["coordinates"][0][0] = [9.123456, "x"]
        with pytest.raises(RecipeInvalid) as caught:
            recipe_from_data(data, OPERATORS)
        text = str(caught.value)
        assert "12345" not in text
        assert "9.123456" not in text
        assert "store.example.invalid" not in text

    def test_a_request_carries_no_resolved_entries(self) -> None:
        assert parse_request(json.dumps(request_data()), OPERATORS).output.bands == ["red", "nir"]
        with pytest.raises(RecipeInvalid):
            parse_request(json.dumps(recipe_data()), OPERATORS)

    def test_an_order_for_a_raster_names_no_assets_a_recipe_always_does(self) -> None:
        assert parse_request(json.dumps(request_data()), OPERATORS).inputs[0].assets is None
        named = request_data()
        named["inputs"][0]["assets"] = ["red"]
        with pytest.raises(RecipeInvalid, match="value_error"):
            parse_request(json.dumps(named), OPERATORS)
        recipe = recipe_data()
        del recipe["inputs"][0]["assets"]
        with pytest.raises(RecipeInvalid, match="assets: missing"):
            parse_recipe(json.dumps(recipe), OPERATORS)

    def test_an_order_for_a_crop_names_its_assets(self) -> None:
        crop = request_data()
        crop["output"] = {
            "kind": "crop",
            "format": "cog",
            "resolution_factor": 1,
            "extent": "bbox(aoi ∩ footprints)",
            "mask": "file",
        }
        with pytest.raises(RecipeInvalid, match="value_error"):
            parse_request(json.dumps(crop), OPERATORS)
        crop["inputs"][0]["assets"] = ["visual"]
        assert parse_request(json.dumps(crop), OPERATORS).inputs[0].assets == ["visual"]


class TestCacheKey:
    ENGINE = {"earthx": "1", "gdal": "1", "rasterio": "1", "numexpr": "1", "numpy": "1"}

    def test_no_key_without_the_version_of_every_input(self) -> None:
        data = recipe_data()
        data["inputs"][0]["resolved"][1]["version"] = None
        assert cache_key(recipe_from_data(data, OPERATORS), self.ENGINE) is None

    @pytest.mark.parametrize("library", ["earthx", "gdal", "rasterio", "numexpr", "numpy"])
    def test_every_engine_version_changes_the_key(self, library: str) -> None:
        recipe = recipe_from_data(recipe_data(), OPERATORS)
        assert cache_key(recipe, self.ENGINE) != cache_key(recipe, {**self.ENGINE, library: "2"})

    def test_the_key_is_not_the_recipe_hash_and_ignores_the_recipe_id(self) -> None:
        recipe = recipe_from_data(recipe_data(), OPERATORS)
        with_id = recipe_from_data(recipe_data(recipe_id="B" * 22), OPERATORS)
        assert cache_key(recipe, self.ENGINE) == cache_key(with_id, self.ENGINE) != recipe_hash(recipe)

    def test_the_engine_names_the_installed_versions(self) -> None:
        engine = engine_versions()
        assert set(engine) == {"earthx", "gdal", "rasterio", "numexpr", "numpy"}
        assert engine["earthx"] == earthx.__version__
        assert all(engine.values())


class TestRunKey:
    """Equal orders share one active run, versions or not (adr/0013 §5.1, plan M4-08a K2)."""

    ENGINE = TestCacheKey.ENGINE

    def test_an_input_without_a_version_still_has_a_run_key_but_no_cache_key(self) -> None:
        data = recipe_data()
        data["inputs"][0]["resolved"][1]["version"] = None
        recipe = recipe_from_data(data, OPERATORS)
        assert cache_key(recipe, self.ENGINE) is None
        key = run_key(recipe, self.ENGINE)
        assert key.startswith("c1:") and len(key) == 3 + 64

    def test_with_every_version_it_is_the_cache_key(self) -> None:
        recipe = recipe_from_data(recipe_data(), OPERATORS)
        assert run_key(recipe, self.ENGINE) == cache_key(recipe, self.ENGINE)

    def test_it_ignores_the_recipe_id_and_follows_the_order(self) -> None:
        plain = recipe_from_data(recipe_data(), OPERATORS)
        with_id = recipe_from_data(recipe_data(recipe_id="B" * 22), OPERATORS)
        other = recipe_from_data(recipe_data(steps=[]), OPERATORS)
        assert run_key(plain, self.ENGINE) == run_key(with_id, self.ENGINE)
        assert run_key(plain, self.ENGINE) != run_key(other, self.ENGINE)

    def test_the_key_names_no_coordinate_and_no_address(self) -> None:
        key = run_key(recipe_from_data(recipe_data(), OPERATORS), self.ENGINE)
        assert re.fullmatch(r"c1:[0-9a-f]{64}", key)


class TestRecipeHosts:
    def test_sorted_and_each_host_once(self) -> None:
        data = recipe_data()
        data["inputs"][0]["resolved"][0]["asset"]["href"] = "https://b.example.invalid/x/red.tif"
        data["inputs"][0]["resolved"][1]["asset"]["href"] = "https://A.example.invalid/x/nir.tif"
        assert recipe_hosts(recipe_from_data(data, OPERATORS)) == ("a.example.invalid", "b.example.invalid")
        same = recipe_from_data(recipe_data(), OPERATORS)
        assert recipe_hosts(same) == ("store.example.invalid",)


class TestInputVersion:
    ITEM = {
        "properties": {"updated": "2026-10-01T00:00:00Z"},
        "assets": {"red": {"href": "x", "file:checksum": "1220abc"}, "nir": {"href": "y"}},
    }

    def test_the_checksum_comes_first(self) -> None:
        assert input_version(self.ITEM, "red", etag='"e"').model_dump() == {"kind": "file:checksum", "value": "1220abc"}

    def test_then_the_etag(self) -> None:
        assert input_version(self.ITEM, "nir", etag='"e"').model_dump() == {"kind": "etag", "value": '"e"'}

    def test_then_the_update_time_of_the_item(self) -> None:
        assert input_version(self.ITEM, "nir").model_dump() == {"kind": "updated", "value": "2026-10-01T00:00:00Z"}

    def test_otherwise_none(self) -> None:
        assert input_version({"assets": {}}, "red") is None
        assert input_version({"assets": [], "properties": None}, "red") is None


class TestProvenance:
    BASE = {
        "kind": "job",
        "runner_version": None,
        "engine": {},
        "scaling": [],
        "started": None,
        "finished": None,
        "attribution": [],
    }

    def test_a_local_result_is_self_attested_and_a_cloud_result_is_not(self) -> None:
        Provenance.model_validate_json(json.dumps({**self.BASE, "execution": "local", "self_attested": True}))
        for execution, attested in (("local", False), ("cloud", True)):
            with pytest.raises(ValueError):
                Provenance.model_validate_json(
                    json.dumps({**self.BASE, "execution": execution, "self_attested": attested})
                )


def test_the_asset_model_matches_the_dataclass_field_for_field() -> None:
    assert {field.name for field in fields(ResolvedAsset)} == set(ResolvedAssetModel.model_fields)
    entry = copy.deepcopy(recipe_data()["inputs"][0]["resolved"][0]["asset"])
    assert ResolvedAssetModel.model_validate_json(json.dumps(entry)).to_asset() == ResolvedAsset(**entry)


def test_the_package_version_is_semver_0_x() -> None:
    # adr/0016 §9, F10: plain MAJOR.MINOR.PATCH, so `runner_version` can append `+g<commit>`.
    assert re.fullmatch(r"0\.\d+\.\d+", earthx.__version__)


class TestLoadsIJson:
    """`loads_i_json` is the check of §4.4 step 1 for a caller that has to look inside a document."""

    def test_a_plain_document_is_read(self) -> None:
        assert loads_i_json('{"a": [1, 2.5, "x"]}') == {"a": [1, 2.5, "x"]}
        assert loads_i_json(b'{"a": 1}') == {"a": 1}

    @pytest.mark.parametrize(
        "raw",
        [
            '{"a": 1, "a": 2}',
            '{"a": NaN}',
            '{"a": Infinity}',
            '{"a": 1e999}',
            '{"a": 9007199254740993}',
            "{",
            "",
            "nope",
        ],
    )
    def test_what_json_would_collapse_or_accept_silently_is_refused(self, raw: str) -> None:
        with pytest.raises(RecipeInvalid):
            loads_i_json(raw)

    def test_a_refusal_does_not_repeat_the_value(self) -> None:
        with pytest.raises(RecipeInvalid) as raised:
            loads_i_json('{"secret-coordinate-47.123456": 1, "secret-coordinate-47.123456": 2}')
        assert str(raised.value) == "duplicate key 'secret-coordinate-47.123456'"  # the key, never a value

    def test_it_is_the_check_the_parsers_use(self) -> None:
        with pytest.raises(RecipeInvalid, match="duplicate key"):
            parse_request('{"recipe_version": 1, "recipe_version": 1}', OPERATORS)
