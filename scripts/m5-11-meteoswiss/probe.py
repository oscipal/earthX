#!/usr/bin/env python3
"""The archive of the MeteoSwiss climate grids and the layout of its files (M5-11 plan §2.2, §7 step 1).

One-time network step on Otto's machine (adr/0002), never in a cloud session or CI: every request goes through
`earthx.gateway`, one second apart per host. From the repository root, in the image of the backend (service
`meteoswiss-probe` of `docker-compose.yml`, which mounts this directory; the same line in PowerShell and bash):

    docker compose run --build --rm meteoswiss-probe --assets      # the items, the archive's assets by kind
    docker compose run --rm meteoswiss-probe --layout              # and the layout of every daily annual file

``--assets`` reads the item list of the collection (one or two requests). ``--layout`` also reads the header of every
daily annual file of the grids in ``--grids`` up to the last completed year, 5–8 requests each (about 40 minutes for
both grids); ``--limit N`` stops after N files. No byte of data is read.

The output names kinds, counts, years, types and layouts. It never prints a URL, an item id or an ETag, so it can be
pasted into the pull request as it is.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

from earthx.discovery.netcdf_refs import FileReferences, UnsupportedLayout, reference_file
from earthx.gateway import Gateway, Policy
from earthx.gateway.errors import GatewayError, UpstreamError

COLLECTION = "https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-surface-derived-grid"
HOST = "data.geo.admin.ch"
INTERVAL_S = 1.0
PAGES = 10
# The asset names `adr/0029` §3.1 measured: `…<quantity>_<grid>.swiss.lv95_<start>_<end>.nc`.
ASSET = re.compile(
    r"(?:^|_)(?P<quantity>[a-z0-9]+)_(?P<grid>ch\d\d[a-z])\.swiss\.lv95_(?P<start>\d{6,8})_(?P<end>\d{6,8})\.nc$"
)


def say(key: str, value: object) -> None:
    print(f"{key:44} {value}")


def form(text: str) -> str:
    """``text`` with every digit as ``#``: a shape to read, never a value."""
    return re.sub(r"\d", "#", text)


async def items(gateway: Gateway) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    url: str | None = f"{COLLECTION}/items?limit=100"
    for _ in range(PAGES):
        if url is None:
            break
        page = (await gateway.get(url)).json()
        found.extend(page.get("features", []))
        url = next((link["href"] for link in page.get("links", []) if link.get("rel") == "next"), None)
    return found


def classify(assets: dict[str, Any]) -> tuple[list[tuple[dict[str, str], dict[str, Any]]], Counter[str]]:
    matched: list[tuple[dict[str, str], dict[str, Any]]] = []
    other: Counter[str] = Counter()
    for key, asset in assets.items():
        match = ASSET.search(key.lower())
        if match is None:
            other[form(key)] += 1
            continue
        matched.append((match.groupdict(), asset))
    return matched, other


def cadence(name: dict[str, str]) -> str:
    start, end = name["start"], name["end"]
    if len(start) == 8 and start.endswith("0101") and end.endswith("1231") and start[:4] == end[:4]:
        return "daily, one year"
    if len(start) == 6 and start[:4] == end[:4]:
        return "monthly, one year"
    return f"other ({form(start)}_{form(end)})"


def report_assets(features: list[dict[str, Any]]) -> list[tuple[dict[str, str], dict[str, Any]]]:
    say("items", len(features))
    archive = max(features, key=lambda feature: len(feature.get("assets", {})), default=None)
    if archive is None:
        return []
    say("assets of the largest item", len(archive["assets"]))
    matched, other = classify(archive["assets"])
    groups: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for name, _ in matched:
        groups[(name["quantity"], name["grid"], cadence(name))].append(int(name["start"][:4]))
    for (quantity, grid, kind), years in sorted(groups.items()):
        say(f"  {quantity} {grid} {kind}", f"{len(years)} files, {min(years)}–{max(years)}")
    for shape, count in other.most_common(10):
        say("  other asset name", f"{shape} × {count}")
    fields: Counter[str] = Counter()
    for _, asset in matched:
        fields.update(key for key in ("file:checksum", "updated", "file:size", "type") if key in asset)
    say("asset fields (of matched)", dict(fields))
    say("media types (of matched)", dict(Counter(str(asset.get("type")) for _, asset in matched)))
    return matched


def reason(error: Exception) -> str:
    """Why a file was not read, without what the source wrote: an answer can quote a path or a key."""
    if isinstance(error, UpstreamError):
        return f"{type(error).__name__} {error.status_code}"
    if isinstance(error, GatewayError):
        return type(error).__name__
    return f"{type(error).__name__}: {form(str(error))}"


def signature(refs: FileReferences) -> tuple[Any, ...]:
    layout = refs.layout
    a, _, c, _, e, f = layout.transform
    bounds = None
    if refs.time_bounds:
        start, end = refs.time_bounds[0]
        bounds = f"from {start.time()} to {end.time()} ({(end - start).total_seconds() / 3600:g} h)"
    return (
        layout.variable, layout.dtype, layout.shape[1:], layout.chunks, layout.filters, layout.fill_value,
        layout.crs, (a, e, c, f), layout.units, f"steps at {refs.times[0].time()}", bounds,
    )


async def report_layout(gateway: Gateway, matched: list[tuple[dict[str, str], dict[str, Any]]], grids: set[str], limit: int | None) -> None:
    last_year = datetime.now(UTC).year - 1
    files = [
        (name, asset)
        for name, asset in matched
        if name["grid"] in grids and cadence(name) == "daily, one year" and int(name["start"][:4]) <= last_year
    ]
    files.sort(key=lambda pair: (pair[0]["grid"], pair[0]["quantity"], pair[0]["start"]))
    say("daily annual files to read", f"{len(files)} (grids {sorted(grids)}, up to {last_year})")
    layouts: Counter[tuple[Any, ...]] = Counter()
    refused: Counter[str] = Counter()
    steps: Counter[str] = Counter()
    for number, (name, asset) in enumerate(files[:limit] if limit else files, start=1):
        try:
            refs = await reference_file(gateway, asset["href"], None)
        except (UnsupportedLayout, GatewayError) as error:
            refused[f"{name['quantity']} {name['grid']}: {reason(error)}"] += 1
            continue
        layouts[(name["grid"], *signature(refs))] += 1
        days = (refs.times[-1] - refs.times[0]).days + 1
        steps[f"{name['quantity']} {name['grid']}: {'complete' if days == len(refs.times) else 'gaps'}"] += 1
        if number % 25 == 0:
            print(f"... {number} files", file=sys.stderr)
    print()
    for layout, count in layouts.most_common():
        say(f"layout × {count}", "")
        for label, value in zip(
            ("grid", "variable", "dtype", "grid shape", "chunks", "filters", "fill value", "crs", "a, e, c, f", "units",
             "time of the steps", "time bounds"),
            layout,
            strict=True,
        ):
            say(f"  {label}", value)
    for line, count in sorted(steps.items()):
        say("  days", f"{line} × {count}")
    for line, count in refused.most_common():
        say("refused", f"{line} × {count}")


async def main(layout: bool, grids: set[str], limit: int | None) -> int:
    policy = Policy(allowed_hosts=frozenset({HOST}), host_intervals={HOST: INTERVAL_S})
    async with Gateway(policy) as gateway:
        matched = report_assets(await items(gateway))
        if layout:
            await report_layout(gateway, matched, grids, limit)
    return 0


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--assets", action="store_true", help="the items and the archive's assets by kind (default)")
    parser.add_argument("--layout", action="store_true", help="also the layout of every daily annual file")
    parser.add_argument("--grids", default="ch01r,ch01h", help="the grids whose files --layout reads")
    parser.add_argument("--limit", type=int, default=None, help="with --layout: stop after this many files")
    args = parser.parse_args(argv)
    return asyncio.run(main(args.layout, {grid.strip() for grid in args.grids.split(",") if grid.strip()}, args.limit))


if __name__ == "__main__":
    sys.exit(run())
