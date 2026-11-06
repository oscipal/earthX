"""A map of classes is drawn in the colours of its source, without a stretch (M5-07 plan F4).

The tile route of the real app over the synthetic WorldCover tile of `synthetic_chain`, with the entry's own
``default_render``: every opaque pixel has a colour of the class table, and a request that adds a stretch draws other
colours, which is why the viewer offers none for such an entry (`drawsClasses` in the frontend).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import numpy
import pytest
from fastapi.testclient import TestClient
from rasterio.io import MemoryFile

from earthx.access.colormaps import COLORMAPS
from earthx.api.tiler import build_app
from earthx.catalog.datasets import ESA_WORLDCOVER_2020, ESA_WORLDCOVER_2021
from tests.catalog import synthetic_chain
from tests.catalog.synthetic_chain import Chain


@pytest.fixture(params=[ESA_WORLDCOVER_2020, ESA_WORLDCOVER_2021], ids=lambda entry: entry.dataset_id)
def chain(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Chain:
    return synthetic_chain.build(request.param, tmp_path, monkeypatch)


@pytest.fixture
def client(chain: Chain) -> Iterator[TestClient]:
    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        return chain.item

    @asynccontextmanager
    async def lifespan(app):
        app.state.earthx_item_source = item_source
        yield

    app = build_app(chain.registry, lifespan=lifespan)
    app.state.earthx_resolver = synthetic_chain.mini_zarr.from_memory
    with TestClient(app) as test_client:
        yield test_client


def _colours(client: TestClient, chain: Chain, **extra: str) -> set[tuple[int, ...]]:
    render = chain.config.default_render
    assert render is not None and render.rescale is None
    zoom, x, y = chain.tile
    response = client.get(
        f"/collections/{chain.dataset_id}/items/{chain.item['id']}/tiles/WebMercatorQuad/{zoom}/{x}/{y}.png",
        params={"asset": chain.render_asset, "colormap_name": render.colormap_name, **extra},
    )
    assert response.status_code == 200, response.text
    with MemoryFile(response.content) as memory, memory.open() as image:
        rgba = image.read()
    opaque = rgba[3] > 0
    return {tuple(int(v) for v in rgba[:3, row, col]) for row, col in zip(*numpy.nonzero(opaque), strict=True)}


def test_every_opaque_pixel_has_a_colour_of_the_class_table(client: TestClient, chain: Chain) -> None:
    table = COLORMAPS.get(chain.config.default_render.colormap_name)
    allowed = {tuple(int(v) for v in rgba[:3]) for value, rgba in table.items() if value != 0}
    colours = _colours(client, chain)
    assert colours, "the tile shows nothing of the map"
    assert colours <= allowed


def test_a_stretch_would_move_the_classes_off_their_colours(client: TestClient, chain: Chain) -> None:
    """The counter-check: the reason the viewer offers no range for a map of classes. Stretched, the class codes land
    on values the table has no colour for, and the map changes colour or vanishes."""
    assert _colours(client, chain) != _colours(client, chain, rescale="0,100")
