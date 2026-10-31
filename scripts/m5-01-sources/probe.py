#!/usr/bin/env python3
"""Open questions of the source catalogue (adr/0023 §9): anonymous access, range reads, ETag, CORS, region.

One-time network step, metadata and the first kilobyte of one file per source; no AOI, no search area. Every request
goes through `earthx.gateway`, which connects to the checked address without the HTTPS proxy of a cloud session, so
the script runs on Otto's machine (adr/0002), not in a cloud session. From the repository root, with the backend venv:

    PYTHONPATH=backend python scripts/m5-01-sources/probe.py            # all sources
    PYTHONPATH=backend python scripts/m5-01-sources/probe.py fsdi-alti  # one source

PowerShell: ``$env:PYTHONPATH = 'backend'`` first. The output names the source and the property, never a URL, an item
ID or a header value that identifies a file (ETag, signature): only whether it is there.

A STAC source is probed in three steps: the collection (licence, providers, media types of `item_assets`), the first
item of the collection (`items?limit=1`, no area), and the first data asset of that item (HEAD with an `Origin` header,
then GET with `Range: bytes=0-1023`). A file source is the last step alone, on a fixed public file.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass

from earthx.gateway import Gateway, Policy
from earthx.gateway.errors import GatewayError, UpstreamError

ORIGIN = "https://example.org"
DATA_TYPES = ("image/tiff", "application/x-hdf5", "application/x-netcdf", "application/netcdf", "application/zip")


@dataclass(frozen=True)
class Source:
    name: str
    hosts: tuple[str, ...]
    collection: str | None = None  # a STAC collection URL
    file: str | None = None  # a fixed public file, for sources without STAC


SOURCES = (
    Source(
        "fsdi-alti",
        ("data.geo.admin.ch",),
        collection="https://data.geo.admin.ch/api/stac/v1/collections/ch.swisstopo.swissalti3d",
    ),
    Source(
        "fsdi-swissimage",
        ("data.geo.admin.ch",),
        collection="https://data.geo.admin.ch/api/stac/v1/collections/ch.swisstopo.swissimage-dop10",
    ),
    Source(
        "fsdi-meteo-grid",
        ("data.geo.admin.ch",),
        collection="https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-surface-derived-grid",
    ),
    Source("geosphere-api", ("dataset.api.hub.geosphere.at",), file="https://dataset.api.hub.geosphere.at/v1/datasets"),
    Source("dwd-opendata", ("opendata.dwd.de",), file="https://opendata.dwd.de/README.txt"),
    Source(
        "lgln-index",
        ("single-datasets.s3.eu-de.cloud-object-storage.appdomain.cloud",),
        file="https://single-datasets.s3.eu-de.cloud-object-storage.appdomain.cloud/pro-download-indices/dop/"
        "lgln-opengeodata-dop20.geojson",
    ),
    Source(
        "worldcover",
        ("esa-worldcover.s3.eu-central-1.amazonaws.com",),
        file="https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
        "ESA_WorldCover_10m_2021_v200_N45E009_Map.tif",
    ),
)


def say(source: str, key: str, value: object) -> None:
    print(f"{source:16} {key:26} {value}")


def present(headers: dict[str, str], name: str) -> str:
    return "yes" if name in headers else "no"


async def probe_file(gateway: Gateway, source: Source, url: str) -> None:
    try:
        head = await gateway.head(url, headers={"Origin": ORIGIN})
    except UpstreamError as error:
        say(source.name, "HEAD", error.status_code)
        return
    headers = {k.lower(): v for k, v in head.headers.items()}
    say(source.name, "HEAD", head.status_code)
    say(source.name, "content-type", headers.get("content-type", "-"))
    say(source.name, "accept-ranges", headers.get("accept-ranges", "-"))
    say(source.name, "etag", present(headers, "etag"))
    say(source.name, "last-modified", present(headers, "last-modified"))
    say(source.name, "cors allow-origin", headers.get("access-control-allow-origin", "-"))
    say(source.name, "x-amz-bucket-region", headers.get("x-amz-bucket-region", "-"))
    say(source.name, "cdn", headers.get("x-cache", headers.get("via", "-")))
    say(source.name, "rate limit (hour)", headers.get("x-ratelimit-limit-hour", "-"))
    try:
        ranged = await gateway.get(url, headers={"Range": "bytes=0-1023"})
        say(source.name, "GET range 0-1023", f"{ranged.status_code} ({len(ranged.content)} bytes)")
    except UpstreamError as error:
        say(source.name, "GET range 0-1023", error.status_code)


def first_data_asset(item: dict) -> str | None:
    assets = item.get("assets", {}).values()
    for asset in assets:
        if "data" in asset.get("roles", ()) or str(asset.get("type", "")).startswith(DATA_TYPES):
            return asset.get("href")
    return None


async def probe_stac(gateway: Gateway, source: Source, url: str) -> None:
    try:
        collection = (await gateway.get(url)).json()
    except UpstreamError as error:
        say(source.name, "collection", error.status_code)
        return
    say(source.name, "license", collection.get("license", "-"))
    say(source.name, "license links", sum(1 for link in collection.get("links", ()) if link.get("rel") == "license"))
    say(source.name, "providers", ", ".join(p.get("name", "?") for p in collection.get("providers", ())) or "-")
    types = sorted({str(a.get("type", "-")) for a in collection.get("item_assets", {}).values()})
    say(source.name, "item_assets types", ", ".join(types) or "-")
    try:
        items = (await gateway.get(f"{url}/items", params={"limit": 1})).json()
    except UpstreamError as error:
        say(source.name, "items", error.status_code)
        return
    features = items.get("features", ())
    if not features:
        say(source.name, "items", "none")
        return
    item = features[0]
    say(source.name, "item proj:epsg", item.get("properties", {}).get("proj:epsg", "-"))
    say(source.name, "item asset types", ", ".join(sorted({str(a.get("type", "-")) for a in item["assets"].values()})))
    href = first_data_asset(item)
    if href is None:
        say(source.name, "data asset", "none")
        return
    await probe_file(gateway, source, href)


async def main(names: list[str]) -> int:
    chosen = [s for s in SOURCES if not names or s.name in names]
    unknown = set(names) - {s.name for s in SOURCES}
    if unknown:
        print(f"unknown source(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    for source in chosen:
        async with Gateway(Policy(allowed_hosts=frozenset(source.hosts))) as gateway:
            try:
                if source.collection:
                    await probe_stac(gateway, source, source.collection)
                elif source.file:
                    await probe_file(gateway, source, source.file)
            except GatewayError as error:
                say(source.name, "gateway", type(error).__name__)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("sources", nargs="*", help="names from SOURCES; all if none")
    sys.exit(asyncio.run(main(parser.parse_args().sources)))
