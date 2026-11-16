#!/usr/bin/env python3
"""Shape of the BEV ATOM service "ALS EL Höhendaten" and its files (M5-09 plan §2, §6).

One-time network step on Otto's machine (adr/0002), never in a cloud session or CI: every request goes through
`earthx.gateway`, one second apart per host. From the repository root, in the image of the backend (service
`bev-probe` of `docker-compose.yml`, which mounts this directory; the same line in PowerShell and bash):

    docker compose run --build --rm bev-probe                     # feeds, one dataset feed, one file
    docker compose run --build --rm bev-probe --all               # all dataset feeds of the newest DTM date
    docker compose run --build --rm bev-probe --all --headers     # and the COG header of every file

``--all`` reads 55 dataset feeds and sends 55 HEAD requests (about two minutes); ``--headers`` opens the 55 files
through GDAL and reads only their headers.

The output names element names, counts, dates and whether a header is there. It never prints a URL, a tile name, an
identifier or a header value that identifies a file (ETag, DOI), so it can be pasted into the pull request as it is.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections import Counter
from datetime import date
from urllib.parse import urlsplit

from defusedxml import ElementTree as DefusedET

from earthx.gateway import Gateway, Policy, check_url
from earthx.gateway.errors import GatewayError, UpstreamError
from earthx.gateway.gdal import gdal_options, vsicurl_path

# The service feed the BEV metadata names for the dataset records (`gmd:distributionInfo`, read 16.11.2026).
SERVICE_FEED = "https://data.bev.gv.at/geonetwork/srv/atom/describe/service?uuid=208cff7a-c8aa-42fe-bf4f-2b8156e37528"
HOST = "data.bev.gv.at"
INTERVAL_S = 1.0
ORIGIN = "https://example.org"

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "georss": "http://www.georss.org/georss",
    "inspire_dls": "http://inspire.ec.europa.eu/schemas/inspire_dls/1.0",
}
PREFIX = {uri: prefix for prefix, uri in NS.items()}

# The titles of the dataset records (read 16.11.2026): "ALS DTM CRS3035RES50000mN2650000E4800000 Höhenraster 1m
# Stichtag 15.09.2022".
TITLE = re.compile(
    r"^ALS (?P<model>DTM|DSM) (?P<tile>CRS3035RES50000mN\d+E\d+) Höhenraster 1m Stichtag "
    r"(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{4})$"
)
# The file path a search hit showed: /download/ALS/DTM/<YYYYMMDD>/<tile>.tif.
FILE_PATH = re.compile(r"^/download/ALS/(?P<model>DTM|DSM)/(?P<date>\d{8})/(?P<tile>CRS3035RES50000mN\d+E\d+)\.tif$")


def say(key: str, value: object) -> None:
    print(f"{key:44} {value}")


def tag(element) -> str:
    """``prefix:local`` for an element, with the prefixes of :data:`NS`; unknown namespaces as ``{uri}``."""
    uri, _, local = element.tag[1:].partition("}") if element.tag.startswith("{") else ("", "", element.tag)
    return f"{PREFIX.get(uri, '{' + uri + '}')}:{local}" if uri else local


def shape_of_entries(entries: list) -> None:
    """Which children the entries carry, and which link relations and types, as counts."""
    children: Counter[str] = Counter()
    links: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    for entry in entries:
        children.update({tag(child) for child in entry})
        for link in entry.findall("atom:link", NS):
            links[
                f"rel={link.get('rel', '-')} type={link.get('type', '-')} length={'yes' if link.get('length') else 'no'}"
            ] += 1
        for category in entry.findall("atom:category", NS):
            categories[category.get("term", "-")] += 1
    for name, count in sorted(children.items()):
        say(f"  entry child {name}", count)
    for name, count in sorted(links.items()):
        say(f"  link {name}", count)
    for term, count in sorted(categories.items()):
        say(f"  category term {term}", count)


def headers_of(response) -> dict[str, str]:
    return {k.lower(): v for k, v in response.headers.items()}


def say_caching(name: str, headers: dict[str, str]) -> None:
    say(f"{name} content-type", headers.get("content-type", "-"))
    say(f"{name} etag", "yes" if "etag" in headers else "no")
    say(f"{name} last-modified", "yes" if "last-modified" in headers else "no")
    say(f"{name} cache-control", headers.get("cache-control", "-"))


async def conditional(gateway: Gateway, name: str, url: str, headers: dict[str, str]) -> None:
    """The status of a second request that names the first answer's ETag or date."""
    for header, condition in (("etag", "If-None-Match"), ("last-modified", "If-Modified-Since")):
        if header in headers:
            try:
                answer = await gateway.get(url, headers={condition: headers[header]})
                say(f"{name} {condition}", answer.status_code)
            except UpstreamError as error:
                say(f"{name} {condition}", error.status_code)


def alternate(entry, media_type: str) -> str | None:
    for link in entry.findall("atom:link", NS):
        if link.get("rel", "alternate") == "alternate" and link.get("type", "").startswith(media_type):
            return link.get("href")
    return None


async def probe_file(gateway: Gateway, url: str) -> int | None:
    """HEAD with an Origin, then 16 bytes by range; the size in bytes, or ``None``."""
    try:
        head = await gateway.head(url, headers={"Origin": ORIGIN})
    except UpstreamError as error:
        say("file HEAD", error.status_code)
        return None
    headers = headers_of(head)
    say("file HEAD", head.status_code)
    say("file accept-ranges", headers.get("accept-ranges", "-"))
    say("file cors allow-origin", headers.get("access-control-allow-origin", "-"))
    say_caching("file", headers)
    try:
        ranged = await gateway.get(url, headers={"Range": "bytes=0-15"})
        say("file GET range 0-15", f"{ranged.status_code} ({len(ranged.content)} bytes)")
    except UpstreamError as error:
        say("file GET range 0-15", error.status_code)
    length = headers.get("content-length")
    return int(length) if length and length.isdigit() else None


def cog_header(url: str, policy: Policy) -> tuple:
    """What GDAL reads from the header of one file: the properties the registry entry assumes."""
    import rasterio

    path = vsicurl_path(check_url(url, policy))
    with rasterio.Env(**gdal_options(policy)), rasterio.open(path) as dataset:
        crs = dataset.crs.to_string() if dataset.crs else "-"
        return (
            crs,
            dataset.width,
            dataset.height,
            dataset.count,
            dataset.dtypes[0],
            dataset.nodata,
            tuple(round(v, 6) for v in dataset.res),
            dataset.block_shapes[0],
            tuple(dataset.overviews(1)),
            dataset.tags(ns="IMAGE_STRUCTURE").get("LAYOUT", "-"),
            dataset.tags(ns="IMAGE_STRUCTURE").get("COMPRESSION", "-"),
            dataset.tags(1).get("AREA_OR_POINT", dataset.tags().get("AREA_OR_POINT", "-")),
        )


async def main(read_all: bool, read_headers: bool) -> int:
    policy = Policy(allowed_hosts=frozenset({HOST}), host_intervals={HOST: INTERVAL_S})
    async with Gateway(policy) as gateway:
        try:
            service = await gateway.get(SERVICE_FEED)
        except (UpstreamError, GatewayError) as error:
            say("service feed", getattr(error, "status_code", type(error).__name__))
            return 1
        headers = headers_of(service)
        say("service feed status", service.status_code)
        say("service feed bytes", len(service.content))
        say_caching("service feed", headers)
        await conditional(gateway, "service feed", SERVICE_FEED, headers)

        root = DefusedET.fromstring(service.content)
        say("service feed root", tag(root))
        say("service feed children", ", ".join(sorted({tag(child) for child in root if tag(child) != "atom:entry"})))
        entries = root.findall("atom:entry", NS)
        say("service feed entries", len(entries))
        shape_of_entries(entries)

        states: Counter[tuple[str, date]] = Counter()
        unmatched = 0
        dtm: dict[date, list] = {}
        for entry in entries:
            match = TITLE.match((entry.findtext("atom:title", "", NS) or "").strip())
            if match is None:
                unmatched += 1
                continue
            day = date(int(match["year"]), int(match["month"]), int(match["day"]))
            states[(match["model"], day)] += 1
            if match["model"] == "DTM":
                dtm.setdefault(day, []).append(entry)
        say("titles not of the known form", unmatched)
        for (model, day), count in sorted(states.items()):
            say(f"  {model} {day.isoformat()}", f"{count} tiles")
        if not dtm:
            return 1
        newest = max(dtm)
        tiles = dtm[newest]
        say("newest DTM date", newest.isoformat())

        chosen = tiles if read_all else tiles[:1]
        files: list[str] = []
        feed_shapes: Counter[str] = Counter()
        for number, entry in enumerate(chosen):
            feed_url = alternate(entry, "application/atom+xml")
            if feed_url is None:
                feed_shapes["no dataset feed link"] += 1
                continue
            try:
                feed = await gateway.get(feed_url)
            except (UpstreamError, GatewayError) as error:
                feed_shapes[f"dataset feed {getattr(error, 'status_code', type(error).__name__)}"] += 1
                continue
            feed_root = DefusedET.fromstring(feed.content)
            feed_entries = feed_root.findall("atom:entry", NS)
            if number == 0:
                say("dataset feed status", feed.status_code)
                say_caching("dataset feed", headers_of(feed))
                say("dataset feed entries", len(feed_entries))
                shape_of_entries(feed_entries)
            hrefs = [href for e in feed_entries if (href := alternate(e, "image/tiff"))]
            feed_shapes[f"{len(hrefs)} image/tiff link(s)"] += 1
            for href in hrefs:
                parts = urlsplit(href)
                fits = parts.hostname == HOST and FILE_PATH.match(parts.path) is not None
                feed_shapes[f"file path of the known form: {'yes' if fits else 'no'}"] += 1
                files.append(href)
        for shape, count in sorted(feed_shapes.items()):
            say(f"  dataset feeds: {shape}", count)

        if not files:
            return 1
        sizes = []
        for number, url in enumerate(files):
            if number == 0:
                sizes.append(await probe_file(gateway, url))
                continue
            try:
                head = await gateway.head(url)
                length = headers_of(head).get("content-length", "")
                sizes.append(int(length) if length.isdigit() else None)
            except (UpstreamError, GatewayError):
                sizes.append(None)
        known = [size for size in sizes if size is not None]
        say("files with a size", f"{len(known)} of {len(files)}")
        if known:
            say(
                "file size min / max / sum [GB]",
                f"{min(known) / 1e9:.2f} / {max(known) / 1e9:.2f} / {sum(known) / 1e9:.1f}",
            )

    if read_headers:
        shapes: Counter[tuple] = Counter()
        for url in files:
            try:
                shapes[cog_header(url, policy)] += 1
            except Exception as error:  # noqa: BLE001 - a one-off measurement names the failure and goes on
                shapes[("failed", type(error).__name__)] += 1
            await asyncio.sleep(INTERVAL_S)
        names = "crs, width, height, bands, dtype, nodata, res, block, overviews, layout, compression, area_or_point"
        say("COG headers", names)
        for shape, count in shapes.most_common():
            say(f"  {count} file(s)", shape)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--all", action="store_true", help="read every dataset feed of the newest DTM date")
    parser.add_argument("--headers", action="store_true", help="with --all: read the COG header of every file")
    arguments = parser.parse_args()
    sys.exit(asyncio.run(main(arguments.all, arguments.headers)))
