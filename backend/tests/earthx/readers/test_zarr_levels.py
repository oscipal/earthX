"""Level choice from `multiscales` (M2-09b-2, adr/0007 §12.11 point 2, §12.10).

Two stores are in play: `mini_zarr.py`'s (no `multiscales` anywhere — the
fallback case) and `mini_zarr_multiscales.py`'s (a `multiscales` layout with
three levels — the case this module is for). Both are synthetic, per
ENTSCHEIDUNGEN §4 and KLAERUNGEN B2: nothing here reaches a network, and
`tests/conftest.py` forbids a socket throughout.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import zarr

from earthx.readers.zarr_reader import MalformedMultiscales, ZarrReader, zarr_asset
from tests.earthx.readers import mini_zarr, mini_zarr_multiscales
from tests.earthx.readers.mini_zarr_multiscales import (
    BASE_URL,
    GROUPS,
    ITEM_CRS,
    PARENT_GROUP,
    POLICY,
    from_memory,
    group_size,
)

DATASET = "synthetic-zarr-multiscales"
ITEM = "SYNTH_LEVELS_20260102T100000"


@pytest.fixture(scope="module")
def store_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return mini_zarr_multiscales.build_mini_zarr_multiscales(tmp_path_factory.mktemp("zarr-levels") / "mini.zarr")


@pytest.fixture
def requests(store_root: Path, monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    return mini_zarr_multiscales.serve_store(store_root, monkeypatch)


def asset(target_gsd: float | None, *, anchor: str = "r10m"):
    """The asset an item would advertise: the finest level's own group, plus the
    resolution the caller wants — exactly what `api.tiler._target_gsd` computes."""
    return zarr_asset(
        f"{BASE_URL}/{PARENT_GROUP}/{anchor}",
        POLICY,
        dataset_id=DATASET,
        item_id=ITEM,
        asset="SR_10m:b04",
        crs=ITEM_CRS,
        resolve=from_memory,
        variable="b04",
        target_gsd=target_gsd,
    )


class TestLevelIsPickedFromMultiscales:
    def test_the_coarsest_level_still_fine_enough_is_picked(self, requests: list[httpx.Request]) -> None:
        """25 m is finer than r60m (60 m) and coarser than r20m (20 m): r20m wins."""
        with ZarrReader(asset(25.0)) as reader:
            assert reader.input.sizes["x"] == group_size(GROUPS["r20m"])

    def test_overzoom_picks_the_finest_level(self, requests: list[httpx.Request]) -> None:
        """Nothing is as fine as 1 m: the finest level available is read instead,
        exactly the case adr/0007 §12.10 says costs less, not more."""
        with ZarrReader(asset(1.0)) as reader:
            assert reader.input.sizes["x"] == group_size(GROUPS["r10m"])

    def test_a_target_at_a_levels_own_resolution_picks_that_level(self, requests: list[httpx.Request]) -> None:
        with ZarrReader(asset(20.0)) as reader:
            assert reader.input.sizes["x"] == group_size(GROUPS["r20m"])

    def test_the_coarsest_level_of_all_is_picked_for_an_unbounded_target(
        self, requests: list[httpx.Request]
    ) -> None:
        """`/statistics`'s own request: adr/0007 §12.11 point 8."""
        with ZarrReader(asset(float("inf"))) as reader:
            assert reader.input.sizes["x"] == group_size(GROUPS["r60m"])

    def test_without_a_target_the_anchor_group_is_read_unchanged(self, requests: list[httpx.Request]) -> None:
        """`target_gsd=None` is M2-09a's whole contract: nothing about level choice
        applies, whatever `multiscales` says (the crop path, the download route)."""
        with ZarrReader(asset(None, anchor="r60m")) as reader:
            assert reader.input.sizes["x"] == group_size(GROUPS["r60m"])


class TestNoMultiscalesFallsBackToTheAssetsOwnGroup:
    """The store `mini_zarr.py` builds has no `multiscales` anywhere — M2-09a's shape,
    and the fallback adr/0007 §12.11 point 2 asks for when it is missing."""

    @classmethod
    @pytest.fixture(scope="class")
    def plain_store_root(cls, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return mini_zarr.build_mini_zarr(tmp_path_factory.mktemp("zarr-plain") / "mini.zarr")

    @pytest.fixture
    def plain_requests(self, plain_store_root: Path, monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
        return mini_zarr.serve_store(plain_store_root, monkeypatch)

    def test_a_target_gsd_changes_nothing_without_multiscales(self, plain_requests: list[httpx.Request]) -> None:
        reader_asset = zarr_asset(
            f"{mini_zarr.BASE_URL}/r20m/b04",
            mini_zarr.POLICY,
            dataset_id=DATASET,
            item_id=ITEM,
            crs=mini_zarr.ITEM_CRS,
            asset="b04",
            resolve=mini_zarr.from_memory,
            target_gsd=1.0,
        )
        with ZarrReader(reader_asset) as reader:
            assert reader.width == int(mini_zarr.FINEST_SIZE * 10.0 / mini_zarr.GROUPS["r20m"])


class TestMalformedMultiscalesIsADefinedError:
    """Its own, disposable store per test: the `multiscales` attribute is rewritten
    in place, and the module-scoped ``store_root`` other tests share must not see
    that (a v0.1 pilot convention is allowed to break, adr/0007 §12.11 point 2 —
    but breaking it here must not break an unrelated test three lines down)."""

    def _broken_store(self, tmp_path: Path, layout: list[object]) -> Path:
        root = mini_zarr_multiscales.build_mini_zarr_multiscales(tmp_path / "mini.zarr")
        zarr.open_group(store=str(root), path=PARENT_GROUP, mode="a", zarr_format=3).attrs["multiscales"] = {
            "layout": layout
        }
        zarr.consolidate_metadata(str(root))
        return root

    def test_a_layout_entry_without_a_transform_is_refused_not_guessed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._broken_store(tmp_path, [{"asset": "r10m"}])
        mini_zarr_multiscales.serve_store(root, monkeypatch)
        with pytest.raises(MalformedMultiscales, match="spatial:transform"):
            ZarrReader(asset(25.0))

    def test_an_empty_layout_is_refused_not_guessed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = self._broken_store(tmp_path, [])
        mini_zarr_multiscales.serve_store(root, monkeypatch)
        with pytest.raises(MalformedMultiscales, match="empty"):
            ZarrReader(asset(25.0))
