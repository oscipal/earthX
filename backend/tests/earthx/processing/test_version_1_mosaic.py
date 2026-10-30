"""A recipe of version 1 over a mosaic or with integer output, rewritten as version 2, gives the values version 1 gave.

The hashes are those of the core before the stock of named bands (``main`` at the merge of NM4-43b), run on the very
recipes of :mod:`version_1_mosaic_cases`: scenes in two UTM zones, so that one of them is warped, and ``uint16`` data
written as ``uint16`` (nodata ``0``). Complements :mod:`test_version_1_values`; ``reproject`` version 3 is not
bit-equal by design (adr/0020 §11, F14).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import rasterio

from earthx.processing import run
from earthx.processing.operators import REGISTRY
from earthx.processing.upgrade import recipe_of_any_version
from tests.earthx.processing import sources
from tests.earthx.processing import version_1_mosaic_cases as cases

#: Case → hash of the values of ``result.tif``, hash of its mask, number of bands, data type, names of the bands.
RECORDED = {
    "mosaic-scaled": (
        "064f7e52b83a111d6275b49450e3ec59f87a0bf0329267649d46f423c2a1311c",
        "39a17802f24cb94f8685cfaea6f0890537a58978cac8ffebed55076611376a3c",
        1,
        "float32",
        ["red"],
    ),
    "mosaic-band-math": (
        "6a51dda2161cc8f1aa2310020eed5cfb3afd26753f427bf008dd153be5999269",
        "39a17802f24cb94f8685cfaea6f0890537a58978cac8ffebed55076611376a3c",
        1,
        "float32",
        ["band_math"],
    ),
    "mosaic-uint16": (
        "e2343304b93c474c13a8c6f8873684f8a24127e717de547f3189d4c355eaee16",
        "39a17802f24cb94f8685cfaea6f0890537a58978cac8ffebed55076611376a3c",
        1,
        "uint16",
        ["red"],
    ),
    "scene-uint16": (
        "7424a766fe76594934ce77b360b28394810f81ca807eb7c720ba147df292a909",
        "9a413b131ecf0ccfb02a837ddb33766d8604cc00da7937b79bd363b53c8d7d86",
        1,
        "uint16",
        ["red"],
    ),
}


def test_every_case_is_recorded() -> None:
    assert set(RECORDED) == set(cases.CASES)


@pytest.mark.parametrize("case", sorted(RECORDED))
def test_the_values_are_those_of_version_1_to_the_last_bit(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "scenes").mkdir()
    scenes = cases.build_scenes(tmp_path / "scenes", scaled=cases.CASES[case][2])
    sources.serve({sources.url(f"{item}_red"): path for item, path in scenes.items()}, monkeypatch)
    recipe = recipe_of_any_version(json.dumps(cases.recipe_of_version_1(case)), REGISTRY)
    (tmp_path / "run").mkdir()
    result = run(recipe, workdir=tmp_path / "run", progress=lambda done, total: None)
    values, mask, count, dtype, names = RECORDED[case]
    with rasterio.open(result.path) as dataset:
        data = dataset.read(masked=True)
        assert hashlib.sha256(data.data.tobytes()).hexdigest() == values
        assert hashlib.sha256(data.mask.tobytes()).hexdigest() == mask
        assert (dataset.count, dataset.dtypes[0]) == (count, dtype)
    assert [band.name for band in result.meta.bands] == names
