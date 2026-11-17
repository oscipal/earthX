#!/usr/bin/env python3
"""The archive of the MeteoSwiss climate grids and the layout of its files (M5-11 plan §2.2, §7 step 1).

One-time network step on Otto's machine (adr/0002), never in a cloud session or CI: every request goes through
`earthx.gateway`, one second apart per host. From the repository root, in the image of the backend (service
`meteoswiss-probe` of `docker-compose.yml`, which mounts this directory; the same line in PowerShell and bash):

    docker compose run --build --rm meteoswiss-probe --assets      # the items, the archive's assets by kind
    docker compose run --rm meteoswiss-probe --layout              # and the layout of every daily annual file

``--assets`` reads the item list of the collection (one or two requests) and prints every pattern of the asset names
over all items, with digits as ``#``, how often and in how many items it occurs, and its years. ``--layout`` also reads the header of every
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
# The asset names `adr/0029` §3.1 measured: `…<quantity>_<grid>.swiss.lv95_<start>_<end>.nc`. How many digits the two
# stamps carry was not written down there (`YYYYMMDD`, `YYYYMMDDhhmm`, …), so any from a year to a minute is taken; the
# 17.11.2026 run with 6–8 digits matched no name at all. The last letter of the quantity is its cadence (MeteoSwiss
# product codes: `TabsD` daily, `TabsM` monthly, `…Y` yearly).
ASSET = re.compile(
    r"(?:^|_)(?P<quantity>[a-z0-9]+)_(?P<grid>ch\d\d[a-z])(?:\.[a-z0-9]+)*_(?P<start>\d{4,14})_(?P<end>\d{4,14})\.nc$"
)
CADENCE = {"d": "daily values", "m": "monthly values", "y": "yearly values"}
# The first year in a name: the first stamp of four digits or more before the extension.
FIRST_YEAR = re.compile(r"_(\d{4})\d*_\d+\.[a-z0-9]+$")


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


def span(name: dict[str, str]) -> str:
    """What one file covers, from its two stamps: a year, a month, a day or something else."""
    start, end = name["start"], name["end"]
    if start[:4] != end[:4]:
        return "several years"
    if len(start) == 4 or (start[4:8] == "0101" and end[4:8] == "1231") or (start[4:6] == "01" and end[4:6] == "12"):
        return "one year"
    if start[:6] == end[:6] and len(start) >= 8 and start[:8] == end[:8]:
        return "one day"
    if start[:6] == end[:6]:
        return "one month"
    return f"other ({form(start)}_{form(end)})"


def cadence(name: dict[str, str]) -> str:
    return f"{CADENCE.get(name['quantity'][-1], 'unknown cadence')}, file of {span(name)}"


def report_assets(features: list[dict[str, Any]]) -> list[tuple[dict[str, str], dict[str, Any]]]:
    """Every name pattern over every item, with counts and years; then the names this task reads, by kind."""
    say("items", len(features))
    say("assets per item (assets × items)", dict(sorted(Counter(len(f.get("assets", {})) for f in features).items())))
    forms: Counter[str] = Counter()
    holders: dict[str, int] = Counter()
    years: dict[str, list[int]] = defaultdict(list)
    matched: dict[str, tuple[dict[str, str], dict[str, Any]]] = {}
    for feature in features:
        seen: set[str] = set()
        for key, asset in feature.get("assets", {}).items():
            shape = form(key)
            forms[shape] += 1
            seen.add(shape)
            year = FIRST_YEAR.search(key.lower())
            if year:
                years[shape].append(int(year[1]))
            match = ASSET.search(key.lower())
            if match is not None:
                matched.setdefault(key, (match.groupdict(), asset))
        for shape in seen:
            holders[shape] += 1
    say("name patterns", len(forms))
    for shape in sorted(forms):
        found = years.get(shape)
        span_of_years = f", years {min(found)}–{max(found)}" if found else ""
        say(f"  {shape}", f"× {forms[shape]} in {holders[shape]} items{span_of_years}")
    groups: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for name, _ in matched.values():
        groups[(name["quantity"], name["grid"], cadence(name))].append(int(name["start"][:4]))
    say("names this task reads (distinct)", len(matched))
    for (quantity, grid, kind), found_years in sorted(groups.items()):
        say(f"  {quantity} {grid} {kind}", f"{len(found_years)} files, {min(found_years)}–{max(found_years)}")
    fields: Counter[str] = Counter()
    for _, asset in matched.values():
        fields.update(key for key in ("file:checksum", "updated", "file:size", "type") if key in asset)
    say("asset fields (of those)", dict(fields))
    say("media types (of those)", dict(Counter(str(asset.get("type")) for _, asset in matched.values())))
    return list(matched.values())


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
        if name["grid"] in grids
        and name["quantity"].endswith("d")
        and span(name) == "one year"
        and int(name["start"][:4]) <= last_year
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
