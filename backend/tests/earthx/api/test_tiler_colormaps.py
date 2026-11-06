"""``GET /colormaps`` and ``colormap_name`` at the tile routes (UI-03d): the list is the one the tiles take, and a name
outside it is refused before anything is read. The item of `test_tiler_band`."""

# ruff: noqa: F811

from __future__ import annotations

import numpy

from earthx.access.colormaps import COLORMAPS
from tests.earthx.api.test_tiler_band import NDVI, Rig, _url, files, rig  # noqa: F401 - fixtures
from tests.earthx.api.test_tiler_chain import _decode


def _png(rig: Rig, colormap: str) -> object:
    url = _url([("band_math", NDVI)], band="NDVI").replace(".tif?", ".png?")
    return rig.get(url + f"&rescale=-1,1&colormap_name={colormap}")


class TestTheList:
    def test_it_names_every_colormap_the_tiles_take_and_is_cached_for_a_day(self, rig: Rig) -> None:
        response = rig.get("/colormaps")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "public, max-age=86400"
        listed = {name for group in response.json()["groups"] for entry in group["colormaps"] for name in (entry["name"], entry["reversed"])}
        assert listed == set(COLORMAPS.list())


class TestTheTiles:
    def test_an_added_colormap_and_its_reverse_draw(self, rig: Rig) -> None:
        forward, back = _png(rig, "rocket"), _png(rig, "rocket_r")
        assert forward.status_code == 200 and back.status_code == 200, forward.text
        a, b = _decode(forward.content), _decode(back.content)
        # Counter-check: the reversed colormap paints the same values in other colours.
        assert not numpy.array_equal(a.data, b.data)

    def test_a_reversed_one_that_rio_tiler_lacks_draws(self, rig: Rig) -> None:
        assert _png(rig, "cfastie_r").status_code == 200

    def test_a_name_that_is_none_is_refused(self, rig: Rig) -> None:
        response = _png(rig, "batlow")
        assert response.status_code in (400, 422), response.text
