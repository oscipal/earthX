"""A recipe of version 1, rewritten as version 2, gives the values version 1 gave (adr/0020 §11, NM4-43c).

The hashes are those of the core before the stock of named bands (``main`` at the merge of NM4-43b), run on the very
recipes of :mod:`version_1_cases`; none of these chains has a ``reproject``, so the values are the same to the last
bit. ``normalize-then-mask`` is the chain in which the upgrade lists the layer of the mask in ``normalize.bands`` and
the planner then drops it. The core writes the bands of ``output.bands`` in that order: the layer of a mask is not among them, as it was not
in version 1.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import rasterio

from earthx.processing import run
from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators import REGISTRY
from earthx.processing.recipe import recipe_from_data
from earthx.processing.upgrade import recipe_of_any_version
from tests.earthx.processing import sources, version_1_cases

#: Case → hash of the values of ``result.tif``, hash of its mask, number of bands, names of the bands.
RECORDED = {
    "mask-then-ndvi": (
        "1635f977c88c80602dc0503796ef07c76572dec412c4cfb3be7699429e0cb45b",
        "a17e00f21a2c734e56c7153471f866772771875ab178b6613b0f34e9b575a7b3",
        1,
        ["band_math"],
    ),
    "mask-then-normalize": (
        "cb5bed47777e1c756c424f37713301757da90037be65fd99e334d60ea7e80b8e",
        "3767302fb69a7c5094164d0c8d41ba6d93ee0e84dd9dbf61a46f8d73e9a1ffa5",
        2,
        ["red", "nir"],
    ),
    "normalize-then-two-expressions": (
        "29abb6bd1d491d9392a111f8b6ee9f9e765be298f83f06d44e5d86f073e2669b",
        "b64e6bac5dd7881e6c869496c65a1e81fbe2544491fe4d5ee27aaedbc9748b5d",
        1,
        ["band_math"],
    ),
    "ndvi-alone": (
        "808e64e168ce31e3d88e710c254388316995dd3e9b3e2955a05d10991449a5a9",
        "b64e6bac5dd7881e6c869496c65a1e81fbe2544491fe4d5ee27aaedbc9748b5d",
        1,
        ["band_math"],
    ),
    "mask-alone": (
        "473ebb8ecdc2741018b1c159212084ae71737f8b9078c133ac6febf4be815d05",
        "3767302fb69a7c5094164d0c8d41ba6d93ee0e84dd9dbf61a46f8d73e9a1ffa5",
        2,
        ["red", "nir"],
    ),
    "no-step": (
        "a7002a20d0faaa4845649bdab5b7c635f2ea827e1bb84af0beac88743b55b82a",
        "dcdecadf40adc3952ad037a19a157c68f5ce29bb2ba909a8e11d8dd8c2785d5b",
        3,
        ["red", "nir", "scl"],
    ),
    "ndvi-then-normalize": (
        "f852e04ad4b650da066438743326b488669df72e2f798b15ed7756645938bd1d",
        "b64e6bac5dd7881e6c869496c65a1e81fbe2544491fe4d5ee27aaedbc9748b5d",
        1,
        ["band_math"],
    ),
    "normalize-then-mask": (
        "4fa0216ed340dfc31c3a35c400049ecb46969c78bb64ace737aa191bbd95ae4f",
        "0bf2be63f5e2d328e79b55b3c40390d6d07f1b63f73f342be59cd411334efa01",
        2,
        ["red", "nir"],
    ),
    "mask-ndvi-normalize": (
        "afedb2e7f36344e04fc8a8219f764b7409e257253d952ebe81974d35e63e77ba",
        "a17e00f21a2c734e56c7153471f866772771875ab178b6613b0f34e9b575a7b3",
        1,
        ["band_math"],
    ),
}


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    return version_1_cases.build(tmp_path_factory.mktemp("version-1"))


@pytest.fixture
def served(files: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    sources.serve({sources.url(name): path for name, path in files.items()}, monkeypatch)


def test_every_case_is_recorded() -> None:
    assert set(RECORDED) == set(version_1_cases.CASES)


@pytest.mark.usefixtures("served")
@pytest.mark.parametrize("case", sorted(RECORDED))
def test_the_values_are_those_of_version_1_to_the_last_bit(case: str, tmp_path: Path) -> None:
    recipe = recipe_of_any_version(json.dumps(version_1_cases.recipe_of_version_1(case)), REGISTRY)
    result = run(recipe, workdir=tmp_path, progress=lambda done, total: None)
    values, mask, count, names = RECORDED[case]
    with rasterio.open(result.path) as dataset:
        data = dataset.read(masked=True)
        assert hashlib.sha256(data.data.tobytes()).hexdigest() == values
        assert hashlib.sha256(data.mask.tobytes()).hexdigest() == mask
        assert dataset.count == count
        assert list(dataset.descriptions) == names
    assert [band.name for band in result.meta.bands] == names


def test_a_recipe_of_version_1_is_not_read_as_it_stands() -> None:
    """The models read recipe version 2 only: a recipe of version 1 has to be rewritten first."""
    with pytest.raises(RecipeInvalid, match="invalid recipe"):
        recipe_from_data(version_1_cases.recipe_of_version_1("ndvi-alone"), REGISTRY)
