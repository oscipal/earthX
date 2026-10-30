"""A preset is an ordinary ``band_math`` step: the intake takes it like a typed one (NM4-14 plan §10 point 3).

The panel builds the step from ``earthx:index_presets`` of the collection; nothing in the order or the recipe says
that it came from a preset (KE1).
"""

from __future__ import annotations

import pytest

from earthx.catalog.collection import to_stac_collection
from earthx.processing.recipe import recipe_hash
from tests.earthx.api.test_intake import S2, Source, accept, band_math, order, s2_item

pytestmark = pytest.mark.anyio

PUBLISHED = to_stac_collection(S2)["earthx:index_presets"]

#: The expressions as a user types them into the panel, with the name of the button.
TYPED = {
    "NDVI": "(nir - red) / (nir + red)",
    "NDWI": "(green - nir) / (green + nir)",
    "NDSI": "(green - swir16) / (green + swir16)",
    "NBR": "(nir - swir22) / (nir + swir22)",
    "EVI": "2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)",
}


@pytest.fixture
def source() -> Source:
    item = s2_item()
    extra = {"blue": "B02", "green": "B03", "swir16": "B11", "swir22": "B12"}
    for asset, band in extra.items():
        item["assets"][asset] = {**item["assets"]["red"], "href": item["assets"]["red"]["href"].replace("B04", band)}
        item["assets"][asset]["file:checksum"] = f"1220S2_A{band}"
    return Source((S2, item))


@pytest.mark.parametrize("preset", PUBLISHED, ids=[entry["name"] for entry in PUBLISHED])
async def test_the_step_of_a_preset_is_the_step_typed_by_hand(preset: dict, source: Source) -> None:
    from_preset = await accept(order(steps=[band_math(preset["expression"], preset["name"])], bands=[preset["name"]]), source)
    by_hand = await accept(order(steps=[band_math(TYPED[preset["name"]], preset["name"])], bands=[preset["name"]]), source)
    assert recipe_hash(from_preset.recipe) == recipe_hash(by_hand.recipe)
    # Every accepted order gets an id of its own; the rest of the recipe is the same.
    assert from_preset.recipe.model_dump(mode="json", exclude={"recipe_id"}) == by_hand.recipe.model_dump(
        mode="json", exclude={"recipe_id"}
    )


async def test_the_intake_reads_only_the_assets_the_preset_names(source: Source) -> None:
    evi = next(entry for entry in PUBLISHED if entry["name"] == "EVI")
    accepted = await accept(order(steps=[band_math(evi["expression"], "EVI")], bands=["EVI"]), source)
    assert sorted(accepted.recipe.inputs[0].assets) == ["blue", "nir", "red"]


async def test_two_presets_give_two_bands(source: Source) -> None:
    steps = [band_math(TYPED["NDVI"], "NDVI"), band_math(TYPED["NDWI"], "NDWI")]
    accepted = await accept(order(steps=steps, bands=["NDVI", "NDWI"]), source)
    assert accepted.recipe.output.bands == ["NDVI", "NDWI"]
    assert sorted(accepted.recipe.inputs[0].assets) == ["green", "nir", "red"]
