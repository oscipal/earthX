"""T-D: is Earth Search's Sentinel-1 GRD still the source the entry describes? (DS-04 plan §4.7)

Runs on the schedule of the live smokes in GitHub Actions, never in a pull request and never in a cloud session. Small
on purpose (adr/0005 §3.6): a few metadata requests, two `HEAD`s and one range of 16 bytes, over windows long closed.

It checks what the entry assumes and what the source's own metadata gets wrong (adr/0018 §3.1, Auslegung A4): the
items say `storage:requester_pays: true` and write `s3://` addresses, while the bucket serves the objects anonymously
over https. Objects written since early 2025 carry a CRC64NVME checksum over the whole file; older ones carry none,
and their version is the ETag (DS-04 plan §4.3, measured 10.11.2026). Everything goes through the adapter and the
gateway, as on the platform.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from earthx.adapters import ADAPTER_SPECS, SearchParams, get_item, search_items
from earthx.catalog.datasets import registry
from earthx.gateway import Policy
from earthx.gateway.client import Gateway

SENTINEL_1_GRD = registry().get("sentinel-1-grd")

pytestmark = [pytest.mark.anyio, pytest.mark.live_dataset("sentinel-1-grd")]

BBOX = (9.0, 48.0, 10.0, 49.0)
WINDOW = (datetime(2024, 6, 1, tzinfo=timezone.utc), datetime(2024, 6, 15, tzinfo=timezone.utc))
# Written after the bucket began to keep CRC64NVME (between February and March 2025).
RECENT = (datetime(2026, 6, 1, tzinfo=timezone.utc), datetime(2026, 6, 15, tzinfo=timezone.utc))
CHECKSUM_MODE = {"x-amz-checksum-mode": "ENABLED"}
STRONG_ETAG = re.compile(r'"[0-9a-f]{32}(-[0-9]+)?"')
ASSET_HOST = SENTINEL_1_GRD.source.asset_hosts[0]


@asynccontextmanager
async def open_gateway() -> AsyncIterator[Gateway]:
    """The real gateway against Earth Search and the bucket, with the allowlist from the registry."""
    hosts = {httpx.URL(SENTINEL_1_GRD.source.endpoint).host, *SENTINEL_1_GRD.source.asset_hosts}
    async with Gateway(Policy(allowed_hosts=frozenset(hosts))) as gateway:
        yield gateway


@pytest.fixture
async def gateway() -> AsyncIterator[Gateway]:
    async with open_gateway() as gateway:
        yield gateway


async def _first_item(gateway: Gateway, window: tuple[datetime, datetime] = WINDOW) -> dict[str, Any]:
    page = await search_items(
        SENTINEL_1_GRD,
        SearchParams(bbox=BBOX, start=window[0], end=window[1], limit=1),
        adapters=ADAPTER_SPECS,
        gateway=gateway,
    )
    assert page.items, "no Sentinel-1 scene in a window that held several"
    return page.items[0]


async def test_the_collection_and_an_item_answer_with_https_addresses(gateway: Gateway) -> None:
    collection = await gateway.get(
        f"{SENTINEL_1_GRD.source.endpoint}/collections/{SENTINEL_1_GRD.source.source_collection_id}"
    )
    assert collection.status_code == 200
    found = await _first_item(gateway)
    item = await get_item(SENTINEL_1_GRD, found["id"], adapters=ADAPTER_SPECS, gateway=gateway)
    pairs = {key for key in ("vv", "vh", "hh", "hv") if key in item["assets"]}
    assert pairs in ({"vv", "vh"}, {"hh", "hv"}, {"vv"}, {"vh"}, {"hh"}, {"hv"}), sorted(pairs)
    for key in pairs:
        assert item["assets"][key]["href"].startswith(f"https://{ASSET_HOST}/"), "the s3:// rewrite no longer applies"
    for name in ("s1:datatake_id", "sat:orbit_state", "sat:relative_orbit", "sar:pixel_spacing_range"):
        assert name in item["properties"], name


def _band_href(item: dict[str, Any]) -> str:
    return next(item["assets"][key]["href"] for key in ("vv", "hh", "vh", "hv") if key in item["assets"])


async def test_the_bucket_is_read_anonymously_and_paid_by_its_owner(gateway: Gateway) -> None:
    """A range of a data band is 206, and the bucket's owner pays."""
    part = await gateway.get(_band_href(await _first_item(gateway)), headers={"Range": "bytes=0-15"})
    assert part.status_code == 206
    assert len(part.content) == 16
    payment = await gateway.get(f"https://{ASSET_HOST}/?requestPayment")
    assert b"<Payer>BucketOwner</Payer>" in payment.content, "the bucket is no longer paid for by its owner"


async def test_a_recent_object_versions_by_its_full_object_crc64nvme(gateway: Gateway) -> None:
    head = await gateway.head(_band_href(await _first_item(gateway, RECENT)), headers=CHECKSUM_MODE)
    assert head.headers.get("x-amz-checksum-type") == "FULL_OBJECT"
    assert head.headers.get("x-amz-checksum-crc64nvme")


async def test_an_older_object_without_a_checksum_still_has_a_strong_etag(gateway: Gateway) -> None:
    """The version falls back to the ETag where an object predates the checksum (DS-04 plan §4.3)."""
    head = await gateway.head(_band_href(await _first_item(gateway)), headers=CHECKSUM_MODE)
    assert head.headers.get("x-amz-checksum-type") in (None, "FULL_OBJECT")
    assert STRONG_ETAG.fullmatch(head.headers.get("etag", "")), "an older object has no version"


async def test_in_on_the_polarizations_means_holds_one_of_them(gateway: Gateway) -> None:
    """DS-04 plan §2: the filter `in ["VH"]` finds as many scenes as `eq "VH"`."""

    async def matched(condition: dict[str, Any]) -> int:
        body = {
            "collections": [SENTINEL_1_GRD.source.source_collection_id],
            "bbox": list(BBOX),
            "datetime": f"{WINDOW[0].isoformat()}/{WINDOW[1].isoformat()}",
            "limit": 1,
            "query": {"sar:polarizations": condition},
        }
        answer = (await gateway.post_json(f"{SENTINEL_1_GRD.source.endpoint}/search", json=body, retry=True)).json()
        return int(answer["numberMatched"])

    contains = await matched({"in": ["VH"]})
    assert contains > 0
    assert contains == await matched({"eq": "VH"})
