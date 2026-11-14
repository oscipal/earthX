"""The build of a pyramid in the work directory, on synthetic files (M5-30b part 8b-2, adr/0032 §5.2).

The sources are GeoTIFFs written to tmp and served through the two seams of `sources.serve`; everything else (the
registry entry, `check_hrefs`, the policy, the reader, the core) runs as in the child.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import morecantile
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from earthx.catalog.datasets import registry
from earthx.catalog.registry import OverviewMode, OverviewResampling
from earthx.processing import overview, overview_build
from earthx.processing.overview_build import (
    ITEMS_NAME,
    JOB_NAME,
    MANIFEST_NAME,
    PLAN_NAME,
    build_pyramid,
    plan_pyramid,
    pyramid_hosts,
    tile_hash,
    tile_path,
)
from earthx.readers.errors import AssetRejected
from tests.earthx.processing import sources

pytestmark = pytest.mark.filterwarnings("ignore:The dataset has no Overviews")

HOST = sources.HOST
BASE = 6  # cop-dem-glo-30: min_zoom 7 in the registry, so the base level is z6
TMS = morecantile.tms.get("WebMercatorQuad")


def _file(path: Path, west: float, south: float, east: float, north: float, value: float) -> Path:
    profile = {
        "driver": "GTiff", "width": 60, "height": 60, "count": 1, "dtype": "float32", "crs": "EPSG:4326",
        "transform": from_bounds(west, south, east, north, 60, 60), "nodata": -9999.0,
    }  # fmt: skip
    with rasterio.open(path, "w", **profile) as target:
        target.write(np.full((60, 60), value, dtype="float32"), 1)
    return path


def _item(name: str, bbox: tuple[float, float, float, float], *, updated: str | None = "2026-01-01T00:00:00Z") -> dict:
    properties = {} if updated is None else {"updated": updated}
    return {
        "id": name, "bbox": list(bbox), "properties": properties,
        "assets": {"data": {"href": f"https://{HOST}/{name}.tif"}},
    }  # fmt: skip


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Two neighbouring 1° items in the tile (33, 22) at z6 and one in the next tile to the east."""
    items = [_item("a", (8, 46, 9, 47)), _item("b", (9, 46, 10, 47)), _item("c", (12, 46, 13, 47))]
    served = {
        f"https://{HOST}/{item['id']}.tif": _file(tmp_path / f"{item['id']}.tif", *item["bbox"], value=value)
        for item, value in zip(items, (100.0, 200.0, 300.0), strict=True)
    }
    sources.serve(served, monkeypatch)
    work = tmp_path / "work"
    work.mkdir()
    (work / ITEMS_NAME).write_text("".join(json.dumps(item) + "\n" for item in items))
    _job(work)
    return work


def _job(work: Path, **extra: Any) -> None:
    (work / JOB_NAME).write_text(json.dumps({"dataset_id": "cop-dem-glo-30", "hosts": [HOST], **extra}))


def _build(work: Path) -> tuple[dict, list[tuple[int, int]]]:
    seen: list[tuple[int, int]] = []
    manifest = build_pyramid(work, lambda done, total: seen.append((done, total)))
    return manifest, seen


class TestLevels:
    def test_the_registry_names_the_first_level_and_the_base_is_one_below(self) -> None:
        """Part 9 moved the levels from a constant of this module into the YAML: GLO-30 z0-z6, WorldCover z0-z4."""
        released = registry()
        assert overview.base_zoom(released.get("cop-dem-glo-30").viewer.min_zoom) == 6
        for dataset_id in ("esa-worldcover-2020", "esa-worldcover-2021"):
            assert overview.base_zoom(released.get(dataset_id).viewer.min_zoom) == 4

    def test_there_is_no_constant_left_that_names_a_level(self) -> None:
        import earthx.processing.overview_build as module

        assert not hasattr(module, "PYRAMID_MIN_ZOOM") and not hasattr(module, "first_zoom")

    def test_every_dataset_with_a_pyramid_in_the_registry_can_be_built(self) -> None:
        hosts = pyramid_hosts()
        assert set(hosts) == {"cop-dem-glo-30", "esa-worldcover-2020", "esa-worldcover-2021"}
        assert all(value for value in hosts.values())
        for dataset_id in hosts:
            assert registry().get(dataset_id).viewer.overview is OverviewMode.PYRAMID

    def test_an_entry_with_no_level_to_build_from_stops_the_listing(self) -> None:
        cfg = registry().get("cop-dem-glo-30")
        viewer = replace(cfg.viewer, min_zoom=1)
        object.__setattr__(viewer, "min_zoom", 0)  # what no registry would let in: the worker does not rely on it alone
        odd = replace(cfg, dataset_id="odd-dem", viewer=viewer)
        with pytest.raises(ValueError, match="odd-dem"):
            pyramid_hosts([odd])  # type: ignore[arg-type]


class TestTheHashOfATile:
    """Review 8b-2 finding 6: the hash decides reuse, so it carries the level, the resampling and the assets too."""

    ITEMS = [_item("a", (8, 46, 9, 47)), _item("b", (9, 46, 10, 47))]

    def test_the_same_items_level_resampling_and_assets_give_the_same_hash_in_any_order(self) -> None:
        config = registry().get("cop-dem-glo-30")
        one = tile_hash(self.ITEMS, zoom=6, config=config)
        assert one is not None and one == tile_hash(self.ITEMS[::-1], zoom=6, config=config)

    def test_another_level_gives_another_hash(self) -> None:
        config = registry().get("cop-dem-glo-30")
        assert tile_hash(self.ITEMS, zoom=6, config=config) != tile_hash(self.ITEMS, zoom=8, config=config)

    def test_another_resampling_gives_another_hash(self) -> None:
        config = registry().get("cop-dem-glo-30")
        other = replace(config, viewer=replace(config.viewer, overview_resampling=OverviewResampling.NEAREST))
        assert config.viewer.overview_resampling is not OverviewResampling.NEAREST
        assert tile_hash(self.ITEMS, zoom=6, config=config) != tile_hash(self.ITEMS, zoom=6, config=other)  # type: ignore[arg-type]

    def test_other_assets_give_another_hash(self) -> None:
        config = registry().get("cop-dem-glo-30")
        other = SimpleNamespace(viewer=config.viewer, default_render=SimpleNamespace(assets=("other",)))  # the registry refuses such an entry
        assert tile_hash(self.ITEMS, zoom=6, config=config) != tile_hash(self.ITEMS, zoom=6, config=other)  # type: ignore[arg-type]

    def test_items_without_updated_still_have_none(self) -> None:
        config = registry().get("cop-dem-glo-30")
        assert tile_hash([_item("a", (8, 46, 9, 47), updated=None)], zoom=6, config=config) is None

    def test_a_changed_item_gives_another_hash(self) -> None:
        config = registry().get("cop-dem-glo-30")
        changed = [self.ITEMS[0], _item("b", (9, 46, 10, 47), updated="2026-02-01T00:00:00Z")]
        assert tile_hash(self.ITEMS, zoom=6, config=config) != tile_hash(changed, zoom=6, config=config)

    def test_a_plan_at_another_level_gives_other_hashes_for_the_same_items(self, workdir: Path) -> None:
        base = plan_pyramid(workdir)
        cfg = registry().get("cop-dem-glo-30")
        deeper = replace(cfg, viewer=replace(cfg.viewer, min_zoom=8))
        from earthx.catalog.registry import DatasetRegistry

        again = plan_pyramid(workdir, registry=DatasetRegistry((deeper,)))
        assert again["base_zoom"] == 7 and set(again["tiles"].values()).isdisjoint(base["tiles"].values())


class TestPlan:
    def test_it_names_the_base_tiles_and_the_hash_of_their_items_without_reading_a_source(
        self, workdir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(overview, "base_tile", lambda *a, **k: pytest.fail("the plan reads no source"))
        plan = plan_pyramid(workdir)
        assert plan["base_zoom"] == BASE
        assert set(plan["tiles"]) == {"33/22", "34/22"}
        assert json.loads((workdir / PLAN_NAME).read_text()) == plan
        items = [json.loads(line) for line in (workdir / ITEMS_NAME).read_text().splitlines()]
        config = registry().get("cop-dem-glo-30")
        assert plan["tiles"]["33/22"] == tile_hash(items[:2], zoom=BASE, config=config)
        assert plan["tiles"]["34/22"] == tile_hash(items[2:], zoom=BASE, config=config)

    def test_items_without_updated_have_no_hash_so_every_tile_is_read_again(self, workdir: Path) -> None:
        items = [_item("a", (8, 46, 9, 47), updated=None), _item("c", (12, 46, 13, 47))]
        (workdir / ITEMS_NAME).write_text("".join(json.dumps(item) + "\n" for item in items))
        plan = plan_pyramid(workdir)
        assert plan["tiles"]["33/22"] is None
        assert plan["tiles"]["34/22"] is not None

    @pytest.mark.parametrize("bbox", [None, [1, 2, 3], "x", [0, 1, 2, "3"]])
    def test_an_item_without_a_usable_bbox_is_refused(self, workdir: Path, bbox: object) -> None:
        item = _item("a", (8, 46, 9, 47)) | {"bbox": bbox}
        (workdir / ITEMS_NAME).write_text(json.dumps(item) + "\n")
        with pytest.raises(ValueError, match="bbox"):
            plan_pyramid(workdir)

    def test_no_items_is_refused(self, workdir: Path) -> None:
        (workdir / ITEMS_NAME).write_text("\n")
        with pytest.raises(ValueError, match="at least one item"):
            plan_pyramid(workdir)

    @pytest.mark.parametrize("dataset_id", ["sentinel-2-c1-l2a", "swissalti3d", "nothing-like-it"])
    def test_a_dataset_without_a_pyramid_is_refused(self, workdir: Path, dataset_id: str) -> None:
        (workdir / JOB_NAME).write_text(json.dumps({"dataset_id": dataset_id, "hosts": [HOST]}))
        with pytest.raises(Exception):  # noqa: B017 - ValueError or UnknownDatasetError: either way nothing is built
            plan_pyramid(workdir)

    def test_a_job_without_a_dataset_is_refused(self, workdir: Path) -> None:
        (workdir / JOB_NAME).write_text("[]")
        with pytest.raises(ValueError, match="names a dataset"):
            plan_pyramid(workdir)


class TestBuild:
    def test_it_writes_the_base_tiles_and_every_level_up_to_z0(self, workdir: Path) -> None:
        manifest, seen = _build(workdir)
        assert manifest["base_zoom"] == BASE
        expected = {"6/33/22", "6/34/22"} | {f"{z}/{33 >> (6 - z)}/{22 >> (6 - z)}" for z in range(6)}
        expected |= {f"{z}/{34 >> (6 - z)}/{22 >> (6 - z)}" for z in range(6)}
        assert set(manifest["tiles"]) == expected
        for name in manifest["tiles"]:
            z, x, y = (int(part) for part in name.split("/"))
            assert tile_path(workdir, z, x, y).is_file()
        assert json.loads((workdir / MANIFEST_NAME).read_text()) == manifest

    def test_the_base_tile_holds_the_values_of_its_files_and_the_level_above_their_mean(self, workdir: Path) -> None:
        _build(workdir)
        base, nodata = overview.decode_tile(tile_path(workdir, 6, 33, 22).read_bytes())
        assert nodata == -9999.0
        assert set(np.unique(base.compressed()).round(3)) == {100.0, 200.0}
        parent, _ = overview.decode_tile(tile_path(workdir, 5, 16, 11).read_bytes())
        assert 100.0 <= parent.min() and parent.max() <= 300.0

    def test_the_base_hashes_are_those_of_the_plan(self, workdir: Path) -> None:
        plan = plan_pyramid(workdir)
        manifest, _ = _build(workdir)
        assert manifest["base_hashes"] == plan["tiles"]

    def test_progress_counts_every_tile_up_to_the_total(self, workdir: Path) -> None:
        manifest, seen = _build(workdir)
        assert [done for done, _ in seen] == list(range(1, len(seen) + 1))
        assert {total for _, total in seen} == {len(seen)}
        assert len(seen) >= len(manifest["tiles"])

    def test_a_reused_base_tile_is_neither_read_nor_written_again_but_makes_the_levels_above(
        self, workdir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _build(workdir)
        kept = tile_path(workdir, 6, 34, 22).read_bytes()
        for path in sorted((workdir / "tiles").rglob("*.tif")):
            path.unlink()
        tile_path(workdir, 6, 34, 22).parent.mkdir(parents=True, exist_ok=True)
        tile_path(workdir, 6, 34, 22).write_bytes(kept)
        _job(workdir, reuse=["34/22"])
        read: list[str] = []
        original = overview.base_tile

        def spy(scenes: list, tile: morecantile.Tile, **kwargs: Any) -> Any:
            read.append(f"{tile.x}/{tile.y}")
            return original(scenes, tile, **kwargs)

        monkeypatch.setattr(overview, "base_tile", spy)
        manifest, _ = _build(workdir)
        assert read == ["33/22"]
        assert tile_path(workdir, 6, 34, 22).read_bytes() == kept
        assert "6/34/22" in manifest["tiles"] and "0/0/0" in manifest["tiles"]
        assert manifest["base_hashes"].keys() == {"33/22", "34/22"}

    def test_a_reuse_key_without_a_file_is_read_like_any_other_tile(
        self, workdir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _job(workdir, reuse=["34/22"])
        manifest, _ = _build(workdir)
        assert "6/34/22" in manifest["tiles"]

    def test_items_without_updated_leave_no_hash_in_the_manifest(self, workdir: Path) -> None:
        items = [json.loads(line) for line in (workdir / ITEMS_NAME).read_text().splitlines()]
        items[0]["properties"].pop("updated")
        (workdir / ITEMS_NAME).write_text("".join(json.dumps(item) + "\n" for item in items))
        manifest, _ = _build(workdir)
        assert set(manifest["base_hashes"]) == {"34/22"}

    def test_a_tile_without_a_valid_pixel_is_not_stored(self, workdir: Path, tmp_path: Path) -> None:
        empty = tmp_path / "a.tif"
        with rasterio.open(empty, "r+") as target:
            target.write(np.full((60, 60), -9999.0, dtype="float32"), 1)
        manifest, _ = _build(workdir)
        assert "6/33/22" in manifest["tiles"], "item b still fills it"
        (workdir / ITEMS_NAME).write_text(json.dumps(_item("a", (8, 46, 9, 47))) + "\n")
        shutil.rmtree(workdir / "tiles", ignore_errors=True)
        manifest, _ = _build(workdir)
        assert manifest["tiles"] == [] and manifest["base_hashes"] == {}

    def test_an_address_on_a_host_the_registry_does_not_name_is_refused_before_anything_is_read(
        self, workdir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _job(workdir, hosts=["other.example.invalid"])
        monkeypatch.setattr(overview, "base_tile", lambda *a, **k: pytest.fail("nothing is read"))
        with pytest.raises(AssetRejected):
            _build(workdir)

    def test_an_item_with_none_of_the_assets_of_the_default_render_fails_the_build(self, workdir: Path) -> None:
        item = _item("a", (8, 46, 9, 47)) | {"assets": {"other": {"href": f"https://{HOST}/a.tif"}}}
        (workdir / ITEMS_NAME).write_text(json.dumps(item) + "\n")
        with pytest.raises(ValueError, match="assets of the default render"):
            _build(workdir)

    def test_one_pacer_serves_the_whole_build(self, workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        made: list[object] = []
        monkeypatch.setattr(overview_build, "host_pacer", lambda: made.append(object()) or made[-1])
        _build(workdir)
        assert len(made) == 1


class TestPacerFactory:
    def test_it_makes_a_host_pacer_with_the_interval_of_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from earthx.gateway import HostPacer
        from earthx.readers.access import host_pacer

        monkeypatch.setenv("EARTHX_OVERVIEW_HOST_INTERVAL_S", "0.5")
        pacer = host_pacer()
        assert isinstance(pacer, HostPacer) and pacer.interval_for("data.example.org") == 0.5

    @pytest.mark.parametrize("value", ["fast", "-1", "nan"])
    def test_a_bad_interval_stops_it_and_names_only_the_variable(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        from earthx.readers.access import host_pacer

        monkeypatch.setenv("EARTHX_OVERVIEW_HOST_INTERVAL_S", value)
        with pytest.raises(ValueError, match="EARTHX_OVERVIEW_HOST_INTERVAL_S") as caught:
            host_pacer()
        assert "fast" not in str(caught.value)


class TestDecode:
    def test_it_is_the_inverse_of_encode(self, tmp_path: Path) -> None:
        values = np.arange(overview.TILE_SIZE**2, dtype="int16").reshape(overview.TILE_SIZE, -1) % 900
        array = np.ma.array(values, mask=values == 0)
        tile = morecantile.Tile(8, 5, 4)
        decoded, nodata = overview.decode_tile(overview.encode_tile(overview.tile_image(array, tile, nodata=-1)))
        assert nodata == -1
        np.testing.assert_array_equal(decoded.filled(0), values * (values != 0))
        assert decoded.mask.sum() == (values == 0).sum()

    def test_floats_without_a_nodata_come_back_masked_where_they_are_nan(self) -> None:
        values = np.ones((overview.TILE_SIZE, overview.TILE_SIZE), dtype="float32")
        values[:10] = np.nan
        tile = morecantile.Tile(1, 1, 2)
        data = overview.encode_tile(overview.tile_image(np.ma.masked_invalid(values), tile, nodata=None))
        decoded, nodata = overview.decode_tile(data)
        assert np.isnan(nodata) and decoded.mask[:10].all() and not decoded.mask[10:].any()

    @pytest.mark.parametrize("data", [b"", b"not a tiff", b"II*\x00" + b"\x00" * 20])
    def test_bytes_that_are_no_geotiff_are_refused(self, data: bytes) -> None:
        with pytest.raises(ValueError, match="stored tile"):
            overview.decode_tile(data)

    def test_a_geotiff_of_another_size_or_crs_is_not_a_stored_tile(self, tmp_path: Path) -> None:
        from rasterio.io import MemoryFile

        def tiff(width: int, crs: str) -> bytes:
            with MemoryFile() as memory:
                with memory.open(
                    driver="GTiff", width=width, height=width, count=1, dtype="uint8", crs=crs,
                    transform=from_bounds(0, 0, 1, 1, width, width),
                ) as target:  # fmt: skip
                    target.write(np.ones((width, width), dtype="uint8"), 1)
                return memory.read()

        with pytest.raises(ValueError, match="512 px"):
            overview.decode_tile(tiff(256, "EPSG:3857"))
        with pytest.raises(ValueError, match="EPSG:3857"):
            overview.decode_tile(tiff(512, "EPSG:4326"))
