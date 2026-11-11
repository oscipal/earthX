"""DS-04 plan §4.3: the version of an input is the host's CRC64NVME over the whole object, where the registry names it.

Synthetic and offline, on the helpers of ``test_intake`` and the Sentinel-1 item of the Earth Search fixtures.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest

from earthx.api.intake import accept_order
from earthx.catalog.registry import rewrite_href
from earthx.gateway import Gateway, Policy
from tests.catalog.entries import SENTINEL_1_GRD
from tests.earthx.adapters.conftest import load
from tests.earthx.api.test_intake import DEM, INTAKE_REGISTRY, Heads, Source, dem_item, order
from tests.earthx.processing.testops import OPERATORS

pytestmark = pytest.mark.anyio

CRC = "AAECAwQFBgc="
INSIDE = {"type": "Polygon", "coordinates": [[[8.4, 46.4], [8.6, 46.4], [8.6, 46.6], [8.4, 46.6], [8.4, 46.4]]]}


def s1_item() -> dict[str, Any]:
    """The VV/VH item as the adapter hands it on: its addresses already rewritten onto the asset host."""
    item = load("sentinel_1_search")["features"][0]
    for asset in item["assets"].values():
        asset["href"] = rewrite_href(asset["href"], SENTINEL_1_GRD.source.asset_href_rewrites)
    return item


def answer(**headers: str) -> Heads:
    return Heads(lambda request: httpx.Response(200, headers={"ETag": '"e"', **headers}))


async def accept(document: dict[str, Any], source: Source, heads: Heads):
    async def no_wait(seconds: float) -> None:
        return None

    hosts = frozenset({*SENTINEL_1_GRD.source.asset_hosts, *DEM.source.asset_hosts})
    gateway = Gateway(
        Policy(allowed_hosts=hosts),
        transport=httpx.MockTransport(heads),
        resolve=lambda host, port: ("93.184.216.34",),
        sleep=no_wait,
    )
    async with gateway:
        return await accept_order(
            json.dumps(document),
            registry=INTAKE_REGISTRY,
            operators=OPERATORS,
            item_source=source,
            gateway=gateway,
        )


def s1_order() -> dict[str, Any]:
    return order("sentinel-1-grd", (("S1_VVVH",),), ("vv", "vh"), aoi=INSIDE)


async def test_a_full_object_checksum_is_the_version_and_was_asked_for() -> None:
    heads = answer(**{"x-amz-checksum-type": "FULL_OBJECT", "x-amz-checksum-crc64nvme": CRC})
    accepted = await accept(s1_order(), Source((SENTINEL_1_GRD, s1_item())), heads)
    versions = [entry.version for entry in accepted.recipe.inputs[0].resolved]
    assert [(version.kind, version.value) for version in versions] == [("crc64nvme", CRC)] * 2  # type: ignore[union-attr]
    assert [request.headers.get("x-amz-checksum-mode") for request in heads.requests] == ["ENABLED"] * 2
    assert accepted.cacheable


@pytest.mark.parametrize(
    "headers",
    [
        {"x-amz-checksum-type": "COMPOSITE", "x-amz-checksum-crc64nvme": CRC},
        {"x-amz-checksum-crc64nvme": CRC},
        {"x-amz-checksum-type": "FULL_OBJECT"},
        {"x-amz-checksum-type": "FULL_OBJECT", "x-amz-checksum-crc64nvme": "not base64 of eight bytes"},
        {"x-amz-checksum-type": "FULL_OBJECT", "x-amz-checksum-crc64nvme": CRC + "\n"},
        {},
    ],
    ids=["composite", "no type", "no value", "malformed value", "trailing newline", "object older than the checksum"],
)
async def test_without_a_usable_full_object_checksum_the_etag_holds(headers: dict[str, str]) -> None:
    accepted = await accept(s1_order(), Source((SENTINEL_1_GRD, s1_item())), answer(**headers))
    assert {entry.version.kind for entry in accepted.recipe.inputs[0].resolved} == {"etag"}  # type: ignore[union-attr]


async def test_the_checksum_is_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    heads = answer(**{"x-amz-checksum-type": "FULL_OBJECT", "x-amz-checksum-crc64nvme": CRC})
    with caplog.at_level(logging.DEBUG):
        await accept(s1_order(), Source((SENTINEL_1_GRD, s1_item())), heads)
    assert not any(CRC in record.getMessage() or CRC in str(record.__dict__) for record in caplog.records)


async def test_an_entry_without_a_checksum_does_not_ask_for_one() -> None:
    """The DEM names none: its `HEAD` stays as it was, and a checksum the host volunteers is not taken."""
    heads = answer(**{"x-amz-checksum-type": "FULL_OBJECT", "x-amz-checksum-crc64nvme": CRC})
    accepted = await accept(order("cop-dem-glo-30", (("DEM_N47_E009",),), ("data",)), Source((DEM, dem_item())), heads)
    assert accepted.recipe.inputs[0].resolved[0].version.kind == "etag"  # type: ignore[union-attr]
    assert [request.headers.get("x-amz-checksum-mode") for request in heads.requests] == [None]
