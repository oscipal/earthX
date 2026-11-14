"""The tag that draws a result in radar geometry slice by slice as its scenes (DS-04d, Otto 14.11.2026)."""

from __future__ import annotations

from pathlib import Path

import pytest
import rasterio

from earthx.readers.cog import AS_WRITTEN, AssetPath, CogReader
from earthx.readers.radar_slices import SLICES_TAG, slice_document, slices_of, slices_tag
from tests.earthx.readers import mini_pass

PIECE = {
    "width": 80, "height": 64, "row": -10, "col": -20, "gcp_crs": "EPSG:4326",
    "gcps": [[0.5, 0.5, 11.0, 46.5, 0.0], [0.5, 79.5, 11.01, 46.5, 0.0], [63.5, 0.5, 11.0, 46.49, 0.0]],
}  # fmt: skip


@pytest.fixture(scope="module")
def plain(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return mini_pass.build_slice(tmp_path_factory.mktemp("slices") / "a.tif", 0)


def test_the_tag_reads_back_exactly() -> None:
    assert slices_of({SLICES_TAG: slices_tag([PIECE])}) == [PIECE]


def test_a_file_without_the_tag_names_no_slices() -> None:
    assert slices_of({}) is None


@pytest.mark.parametrize("text", ['{"version": 2, "slices": []}', '{"slices": {}}', "[]"])
def test_a_tag_of_another_shape_is_refused(text: str) -> None:
    with pytest.raises(ValueError):
        slices_of({SLICES_TAG: text})


def test_a_slice_the_result_does_not_reach_has_no_view(plain: Path) -> None:
    with rasterio.open(plain) as dataset:
        beside = {**PIECE, "row": dataset.height + 5}
        assert slice_document(str(plain), dataset, beside) is None


def test_the_view_has_the_size_and_gcps_of_the_scene_and_the_rows_at_their_place(plain: Path) -> None:
    with rasterio.open(plain) as dataset:
        document = slice_document(str(plain), dataset, PIECE)
        source = dataset.read(1)
    assert document is not None
    with rasterio.open(document) as view:
        assert (view.width, view.height) == (PIECE["width"], PIECE["height"])
        assert [[p.row, p.col, p.x, p.y, p.z] for p in view.gcps[0]] == PIECE["gcps"]
        values = view.read(1)
    # The result's row 0 is the slice's row 10, its column 0 the slice's column 20.
    assert values[10, 20] == source[0, 0]
    assert (values[:10] == 0).all() and (values[:, :20] == 0).all()


def test_a_file_with_a_geotransform_is_drawn_as_before(tmp_path: Path) -> None:
    from tests.earthx.readers.mini_cog import build_mini_cog

    path = AssetPath(str(build_mini_cog(tmp_path / "plain.tif")), dataset_id="", item_id="", asset="r", georeferencing=AS_WRITTEN)
    with CogReader(path) as reader:
        assert reader.tile_by_slices(0, 0, 0) is None
