"""NM4-75: the text of ``exports/BANDS.txt`` is the same in the browser and on the server.

The frontend writes it for the whole scene in one file per band (``frontend/src/originals.ts``), the backend for
everything else. Both read the same synthetic item (``tests/fixtures/bands/golden_input.json``) and must give
``golden_per_band.txt`` byte for byte; ``frontend/src/bandChoice.test.ts`` holds the other half of the pair.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from earthx.access.band_export import BandsFile, band_meta, band_rows, bands_text, plan_files
from earthx.catalog.registry import ClassRow

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "bands"


def _classes_of(given: dict) -> Callable[[str], tuple[ClassRow, ...] | None]:
    """The classes the synthetic registry names for a band (M5-62): ``scl`` has two, every other band none."""
    classes = {key: tuple(ClassRow(**row) for row in rows) for key, rows in given["classes"].items()}
    return classes.get


def test_the_server_writes_the_golden_text_for_one_file_per_band() -> None:
    given = json.loads((FIXTURES / "golden_input.json").read_text(encoding="utf-8"))
    collection, item = given["collection"], given["item"]
    auxiliary = set(collection["earthx:auxiliary_assets"])
    mask = collection["earthx:mask"]["asset"]
    metas = [
        band_meta(
            item,
            asset,
            unit=collection["earthx:band_units"].get(asset),
            categorical=asset == mask,
            classes=_classes_of(given)(asset),
        )
        for asset in item["assets"]
        if asset not in auxiliary
    ]
    plans = plan_files("per_band", metas)
    files = [
        BandsFile(f"exports/{plan.name}", [meta], ["none"], [meta.resolution_m])
        for plan, meta in zip(plans, metas, strict=True)
    ]
    text = bands_text(title=given["title"], form="per_band", files=files)
    assert text == (FIXTURES / "golden_per_band.txt").read_text(encoding="utf-8")
    assert "visual" not in text  # the picture the registry calls auxiliary is no band
    assert "B04 | red | 0.665 | 10 | 10 | none | uint16 | 0.0001 | -0.1 | 0 | 1" in text
    assert text.endswith("Classes of band 1 (SCL)\nValue | Class | Colour\n4 | Vegetation | #2ca02c\n6 | Water | #1f77b4\n")


def test_the_table_the_dialog_is_given_is_the_golden_response() -> None:
    """The frontend reads this very file as the answer of ``POST /collections/{dataset}/bands`` (`bandChoice.test.ts`)."""
    given = json.loads((FIXTURES / "golden_input.json").read_text(encoding="utf-8"))
    collection, item = given["collection"], given["item"]
    rows = band_rows(
        [item],
        auxiliary=collection["earthx:auxiliary_assets"],
        mask_asset=collection["earthx:mask"]["asset"],
        unit_of=collection["earthx:band_units"].get,
        classes_of=_classes_of(given),
    )
    answer = {"bands": rows}
    assert answer == json.loads((FIXTURES / "golden_bands_response.json").read_text(encoding="utf-8"))
    ticked = {band["asset"] for band in answer["bands"] if band["preselected"]}
    assert ticked == {"blue", "red", "rededge1", "coastal", "scl"}  # the spectral bands and the mask layer, not aot
