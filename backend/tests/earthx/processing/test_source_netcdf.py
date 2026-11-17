"""A job reads a NetCDF time step through its chunk references (M5-11 plan §4.3; KLAERUNGEN B9).

The worker core opens the references the recipe carries through `access` and `processing.source`, with nothing but
the gateway: the same values as the tile, the band named like the asset.
"""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path

import numpy
import pytest
from rasterio.windows import Window

from earthx.access.resolve import open_asset_ref
from earthx.discovery.netcdf_refs import step_references
from earthx.processing.recipe import ResolvedInput
from earthx.processing.source import Source as WorkerSource
from tests.earthx.readers import mini_netcdf
from tests.earthx.readers.mini_netcdf import POLICY, URL, from_memory
from tests.earthx.readers.test_reference_store import ITEM, expected, made


def test_a_job_reads_the_day_named_like_the_asset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, source, refs = made(tmp_path)
    source.serve_readers(monkeypatch)
    entry = ResolvedInput.model_validate(
        {
            "asset": {
                "dataset_id": mini_netcdf.DATASET, "item_id": ITEM, "asset": "TabsD", "reader": "zarr",
                "href": URL, "variable": None, "crs": "EPSG:2056", "refs": step_references(refs, 3),
            },
            "version": {"kind": "etag", "value": source.etag},
            "bands": [{"data_type": "float32", "nodata": "nan", "scale": None, "offset": None}],
            "scaling": "store-cf",
            "gsd": 1000.0,
        }
    )
    with ExitStack() as stack:
        target = open_asset_ref(entry.asset.to_asset(), POLICY, from_memory)
        worker = WorkerSource.open(entry, target, stack)
        image = worker.read(Window(0, 0, mini_netcdf.COLUMNS, mini_netcdf.ROWS))
    assert worker.names == ["TabsD"] and worker.data_types == ["float32"]
    assert image.band_names == ["TabsD"]
    assert numpy.array_equal(image.array.filled(numpy.nan)[0], expected(3), equal_nan=True)
