"""T-D: does the Copernicus DEM bucket still answer the way M3-11b measured it?

Runs on a schedule in GitHub Actions, never in a pull request and never in a
cloud session (`adr/0002` §2) — the same reasoning `test_coverage_smoke.py`
already documents: `gateway` pins the checked *address*, and a cloud session's
egress allowance is name-based, so it cannot reach a real source through
`gateway` at all. The measurements themselves are `docs/plans/
m3-11b-dem-adapter.md` §2, from 26.09.2026.

Three requests only (adr/0005 §3.6, K5: rücksichtsvoll gegenüber der Quelle):

1. a conditional ``GET`` on ``tileList.txt`` against the ETag §2.1 measured,
   expecting ``304`` — no body, and proof the list itself has not moved;
2. one page of the bucket's own prefix listing, capped small;
3. a small range read on one real tile's COG, the same shape a tile request
   through the real adapter and reader would make.

If the ETag has changed, step 1 fails loudly rather than silently reading
``200`` as "still fine" — a real change here is exactly what M3-11b's F5
(the run log) exists to notice, and what this smoke exists to flag before a
materialize run does.
"""

from __future__ import annotations

import httpx
import pytest

from earthx.catalog.datasets import COP_DEM_GLO_30
from earthx.gateway import Policy
from earthx.gateway.client import Gateway

pytestmark = [pytest.mark.anyio, pytest.mark.live_dataset("cop-dem-glo-30")]

# Measured 26.09.2026 (M3-11b plan §2.1); unchanged since 09.05.2022.
KNOWN_TILE_LIST_ETAG = '"637fe75ddf7615ba853dd83caf05cd82"'

# One real, small tile (measured, plan §2.3) — read a handful of header bytes,
# never the whole 40+ MB file.
KNOWN_TILE = "Copernicus_DSM_COG_10_N00_00_E006_00_DEM"


@pytest.fixture
async def gateway():
    host = httpx.URL(COP_DEM_GLO_30.source.endpoint).host
    async with Gateway(Policy(allowed_hosts=frozenset({host}))) as gateway:
        yield gateway


async def test_the_tile_list_etag_is_unchanged(gateway: Gateway) -> None:
    response = await gateway.get(
        f"{COP_DEM_GLO_30.source.endpoint}/tileList.txt",
        headers={"if-none-match": KNOWN_TILE_LIST_ETAG},
    )
    assert response.status_code == 304, (
        f"tileList.txt answered {response.status_code}, not 304 — the DEM bucket has "
        "changed since M3-11b measured it (plan §2.1); the materialize command's own "
        "run log will pick up a real change, but this smoke should be re-measured too"
    )


async def test_one_page_of_the_bucket_listing_still_answers(gateway: Gateway) -> None:
    response = await gateway.get(
        f"{COP_DEM_GLO_30.source.endpoint}/",
        params={"list-type": "2", "delimiter": "/", "max-keys": "5"},
    )
    assert response.status_code == 200
    assert b"<ListBucketResult" in response.content
    assert b"<Prefix>" in response.content or b"<CommonPrefixes>" in response.content


async def test_a_known_tile_still_answers_a_range_read(gateway: Gateway) -> None:
    response = await gateway.get(
        f"{COP_DEM_GLO_30.source.endpoint}/{KNOWN_TILE}/{KNOWN_TILE}.tif",
        headers={"range": "bytes=0-15"},
    )
    assert response.status_code in (200, 206), f"unexpected status {response.status_code}"
    # A TIFF's byte-order mark, little- or big-endian.
    assert response.content[:2] in (b"II", b"MM")
