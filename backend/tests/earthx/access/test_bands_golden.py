"""NM4-75: the text of ``exports/BANDS.txt`` is the same in the browser and on the server.

The frontend writes it for the whole scene in one file per band (``frontend/src/originals.ts``), the backend for
everything else. Both read the same synthetic item (``tests/fixtures/bands/golden_input.json``) and must give
``golden_per_band.txt`` byte for byte; ``frontend/src/bandChoice.test.ts`` holds the other half of the pair.
"""

from __future__ import annotations

import json
from pathlib import Path

from earthx.access.band_export import BandsFile, band_meta, bands_text, plan_files

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "bands"


def test_the_server_writes_the_golden_text_for_one_file_per_band() -> None:
    given = json.loads((FIXTURES / "golden_input.json").read_text(encoding="utf-8"))
    collection, item = given["collection"], given["item"]
    auxiliary = set(collection["earthx:auxiliary_assets"])
    mask = collection["earthx:mask"]["asset"]
    metas = [
        band_meta(item, asset, unit=collection["earthx:band_units"].get(asset), categorical=asset == mask)
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
