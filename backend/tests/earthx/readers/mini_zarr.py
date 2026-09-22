"""A synthetic Zarr store, built by this script and served over a gateway (adr/0007 §6 point 6).

No binary fixture: the store is written into a ``tmp_path`` by the test that needs
it, which keeps the repository free of data whose licence would have to be argued
(ENTSCHEIDUNGEN §4) and keeps what the reader is measured against readable.

It is not a tidy textbook store. It copies the four places where the real EOPF
products differ from one, because those are the places a reader gets wrong:

* **resolution groups instead of ``multiscales``** — ``r10m``/``r20m``/``r60m`` as
  sibling groups of the same extent (§3.4), so picking a level means picking a
  group rather than reading a convention;
* **no CRS in the store** — ``x``/``y`` coordinate arrays in UTM metres and nothing
  that says which UTM, so the georeferencing has to come from the item's
  ``proj:code``;
* **several variables per group**, so selecting a band is a real choice;
* **a time axis**, so "a dimension rather than an item property" happens once;
* **small chunks**, so a window crosses several of them without the test moving
  megabytes.

The missing group is not written at all: :data:`MISSING_GROUP` is what an item
advertises and the store does not have, which is exactly how ``TCI_10m`` fails in
the real source (§3.5).

:func:`serve_store` is the other half: it puts the store on disk behind the one
seam the reader has, :func:`earthx.readers.zarr_reader.open_gateway`. Nothing here
reaches a network, and that is the point rather than a convenience — the only way
bytes get into the reader is the transport inside the gateway, so a read that found
another way would find nothing at all, and the request log is complete.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from pathlib import Path

import httpx
import numpy
import pytest
import xarray

from earthx.gateway import Gateway, Policy

#: Where the served store lives. The last segment ends in `.zarr`, which is how
#: `split_asset_href` tells the store from the group inside it.
HOST = "store.example.invalid"
STORE_PATH = "/products/mini.zarr"
BASE_URL = f"https://{HOST}{STORE_PATH}"
POLICY = Policy(allowed_hosts=frozenset({HOST}))

#: The resolution groups, with the ground sample distance each one stands for.
GROUPS = {"r10m": 10.0, "r20m": 20.0, "r60m": 60.0}

#: The variables every group carries.
VARIABLES = ("b02", "b04", "b08")

#: Advertised by the item in the tests, absent from the store — the error case.
MISSING_GROUP = "r120m"

#: The two acquisitions on the time axis.
TIMES = ("2026-01-02T10:00:00", "2026-01-07T10:00:00")

#: Upper left corner in UTM 32N metres, and the CRS the *item* names for it.
ORIGIN_X, ORIGIN_Y = 600000.0, 5700000.0
ITEM_CRS = "EPSG:32632"

#: Pixels per side of the finest group. Every coarser group covers the same ground,
#: so this has to divide evenly by every ratio in :data:`GROUPS` (72, 36, 12 pixels).
FINEST_SIZE = 72

#: Small enough that a 256×256 tile request crosses several of them.
CHUNK = (1, 16, 16)


def build_mini_zarr(root: Path) -> Path:
    """Write the store under ``root`` and return the path it was written to.

    Zarr v3 with consolidated metadata, because that is what the reader requires and
    what the measured products carry (§3.10) — a store it would have to list is a
    separate, deliberate test case.
    """
    for name, resolution in GROUPS.items():
        dataset = resolution_group(resolution)
        with warnings.catch_warnings():
            # Consolidated metadata is not part of the v3 specification yet and zarr
            # says so on every write. The reader depends on it either way (§3.10), so
            # the warning is noise here rather than news.
            warnings.simplefilter("ignore")
            dataset.to_zarr(
                root,
                group=name,
                mode="a",
                zarr_format=3,
                consolidated=True,
                encoding={variable: {"chunks": CHUNK} for variable in dataset.data_vars},
            )
    return root


def resolution_group(resolution: float) -> xarray.Dataset:
    """One resolution group: the same ground, at the pixel size of this level."""
    size = int(FINEST_SIZE * GROUPS["r10m"] / resolution)
    generator = numpy.random.default_rng(seed=int(resolution))
    return xarray.Dataset(
        {
            name: (
                ("time", "y", "x"),
                generator.integers(1, 10_000, (len(TIMES), size, size)).astype("uint16"),
            )
            for name in VARIABLES
        },
        coords={
            "time": numpy.array(TIMES, dtype="datetime64[ns]"),
            # Cell centres, which is what a coordinate array holds: half a pixel in
            # from the corner, so the reader's bounds come out at the corner again.
            "y": ORIGIN_Y - (numpy.arange(size) + 0.5) * resolution,
            "x": ORIGIN_X + (numpy.arange(size) + 0.5) * resolution,
        },
    )


def store_bounds() -> tuple[float, float, float, float]:
    """The extent every group covers, in its own (unnamed) metres: left, bottom, right, top."""
    side = FINEST_SIZE * GROUPS["r10m"]
    return (ORIGIN_X, ORIGIN_Y - side, ORIGIN_X + side, ORIGIN_Y)


def from_memory(host: str, port: int) -> tuple[str, ...]:
    """What the system resolver would have said. ``tests/conftest.py`` forbids asking it."""
    return ("93.184.216.34",)


def serve_store(root: Path, monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Serve ``root`` to the reader, and hand back the log of what it fetched.

    Everything about the gateway put in place here is the real thing except the
    socket: the allowlist, the redirect rule, the size cap and ``check_url`` on every
    single key all run as they do in the tiler.
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _respond(root, request)

    def open_gateway(policy: Policy, resolve: Callable[[str, int], tuple[str, ...]]) -> Gateway:
        return Gateway(policy, transport=httpx.MockTransport(handler), resolve=resolve)

    monkeypatch.setattr("earthx.readers.zarr_reader.open_gateway", open_gateway)
    return seen


def _respond(root: Path, request: httpx.Request) -> httpx.Response:
    """A static file server for the store, with the one header that matters: ``Range``."""
    relative = request.url.path.removeprefix(STORE_PATH).lstrip("/")
    path = root / relative
    # `is_file` and not `exists`: a group is a directory here, and a store that
    # answered 200 with nothing for one would hide the very error case being tested.
    if not relative or ".." in relative.split("/") or not path.is_file():
        return httpx.Response(404)
    body = path.read_bytes()
    header = request.headers.get("range")
    if header is None:
        return httpx.Response(200, content=body)
    first, last = _byte_positions(header, len(body))
    if first >= len(body):
        return httpx.Response(416)
    return httpx.Response(206, content=body[first : last + 1])


def _byte_positions(header: str, size: int) -> tuple[int, int]:
    """``bytes=a-b``, ``bytes=a-`` and ``bytes=-n`` as inclusive positions."""
    specification = header.split("=", 1)[1].strip()
    if specification.startswith("-"):
        return max(0, size - int(specification[1:])), size - 1
    first, _, last = specification.partition("-")
    return int(first), (int(last) if last else size - 1)
