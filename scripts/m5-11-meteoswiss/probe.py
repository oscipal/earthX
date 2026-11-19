#!/usr/bin/env python3
"""The archive of the MeteoSwiss climate grids and the layout of its files (M5-11 plan §2.2, §7 step 1).

One-time network step on Otto's machine (adr/0002), never in a cloud session or CI: every request goes through
`earthx.gateway`, one second apart per host. From the repository root, in the image of the backend (service
`meteoswiss-probe` of `docker-compose.yml`, which mounts this directory; the same line in PowerShell and bash):

    docker compose run --build --rm meteoswiss-probe --assets      # the items, the archive's assets by kind
    docker compose run --rm meteoswiss-probe --layout              # and the layout of every daily annual file
    docker compose run --rm meteoswiss-probe --current             # the items outside the archive (M5-58 plan §2.3)

``--assets`` reads the item list of the collection (one or two requests) and prints every pattern of the asset names
over all items, with digits as ``#``, how often and in how many items it occurs, and its years. ``--layout`` also reads the header of every
daily annual file of the grids in ``--grids`` up to the last completed year, 5–8 requests each (about 40 minutes for
both grids); ``--limit N`` stops after N files. No byte of data is read.

``--current`` (M5-58 plan §2.3) reads only the items outside the archive: by kind (an item of one day, of one month),
their properties and the patterns of their asset names, whether an item answers ``If-None-Match`` with ``304`` (two
requests per item), and the header of one file per kind, grid and quantity, 5–8 requests each (about 3 minutes).

The output names kinds, counts, years, types and layouts. It never prints a URL, an item id or an ETag, so it can be
pasted into the pull request as it is.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import sys
import warnings
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

from pyproj import CRS
from pyproj.exceptions import CRSError

from earthx.discovery.netcdf_refs import FileReferences, UnsupportedLayout, reference_file
from earthx.gateway import Gateway, Policy
from earthx.gateway.errors import GatewayError, UpstreamError

COLLECTION = "https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-surface-derived-grid"
HOST = "data.geo.admin.ch"
# What a grid_mapping that names no EPSG code exactly is compared with: LV95, the grid of both measured files.
REFERENCE_EPSG = 2056
# Attributes in which a file may carry its CRS as text beside the CF parameters.
WKT_ATTRIBUTES = ("crs_wkt", "spatial_ref", "esri_pe_string")
INTERVAL_S = 1.0
PAGES = 10
# The names of the annual archive, as Otto's second run showed them (17.11.2026):
# `ogd-surface-derived-grid-archive.<quantity>_<grid>.swiss.lv95_<start>_<end>.nc`, grid `ch01r` or `ch01h`, each stamp
# 14 digits (`YYYYMMDDhhmmss`). Only the archive: the files of `-last` and the preliminary daily files change after
# publication, the archive holds the consolidated years (adr/0029 F5, Otto 17.11.2026). The last letter of the quantity
# is its cadence (MeteoSwiss product codes: `TabsD` daily, `TabsM` monthly, `…Y` yearly).
ASSET = re.compile(
    r"^ogd-surface-derived-grid-archive\.(?P<quantity>[a-z0-9]+)_(?P<grid>ch01[rh])\.swiss\.lv95_"
    r"(?P<start>\d{14})_(?P<end>\d{14})\.nc$"
)
CADENCE = {"d": "daily values", "m": "monthly values", "y": "yearly values"}
# The first year in a name: the first stamp of four digits or more before the extension.
FIRST_YEAR = re.compile(r"_(\d{4})\d*_\d+\.[a-z0-9]+$")


def say(key: str, value: object) -> None:
    print(f"{key:44} {value}")


def form(text: str) -> str:
    """``text`` with every digit as ``#``: a shape to read, never a value."""
    return re.sub(r"\d", "#", text)


# Any daily or monthly file of the collection, in or outside the archive: the prefix tells which (M5-58 plan §2.3).
ANY_FILE = re.compile(
    r"^(?P<prefix>ogd-surface-derived-grid[a-z-]*)\.(?P<quantity>[a-z0-9]+)_(?P<grid>ch\d\d[a-z])\.swiss\.lv\d\d_"
    r"(?P<start>\d{4,14})_(?P<end>\d{4,14})\.nc$"
)
ITEM_PROPERTIES = ("datetime", "start_datetime", "end_datetime", "created", "updated", "expires")


async def items(gateway: Gateway, pages: list[dict[str, str | None]] | None = None) -> list[dict[str, Any]]:
    """Every item of the collection; ``pages`` collects, per page, the validators the page answered with."""
    found: list[dict[str, Any]] = []
    url: str | None = f"{COLLECTION}/items?limit=100"
    for _ in range(PAGES):
        if url is None:
            break
        response = await gateway.get(url)
        if pages is not None:
            pages.append({"etag": response.headers.get("etag"), "last-modified": response.headers.get("last-modified"), "url": url})
        page = response.json()
        found.extend(page.get("features", []))
        url = next((link["href"] for link in page.get("links", []) if link.get("rel") == "next"), None)
    return found


def span(name: dict[str, str]) -> str:
    """What one file covers, from its two stamps: a year, a month, a day, one time step or something else.

    Two equal stamps are one time step, whatever its length: a file of yearly values stamped with the first instant
    of its year is no file of one day (third run, 18.11.2026).
    """
    start, end = name["start"], name["end"]
    if start == end:
        return "one time step"
    first_instant = start[4:8] == "0101" and set(start[8:]) <= {"0"}
    if first_instant and end == f"{int(start[:4]) + 1}0101".ljust(len(end), "0"):
        return "one year"  # the end stamp is the first instant of the next year
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
        layout.crs or "no exact EPSG code (see grid_mapping below)", (a, e, c, f), layout.units, f"steps at {refs.times[0].time()}", bounds,
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
    mappings: dict[str, dict[str, Any]] = {}
    mapping_files: dict[str, Counter[str]] = defaultdict(Counter)
    steps: Counter[str] = Counter()
    for number, (name, asset) in enumerate(files[:limit] if limit else files, start=1):
        try:
            # Not strict: a grid_mapping without an exact EPSG code is recorded and the rest of the layout still read
            # (type, chunks, time), which the platform would refuse (third run, 18.11.2026).
            refs = await reference_file(gateway, asset["href"], None, strict_crs=False)
        except (UnsupportedLayout, GatewayError) as error:
            refused[f"{name['quantity']} {name['grid']}: {reason(error)}"] += 1
            continue
        if refs.layout.crs is None:
            key = json.dumps(dict(refs.layout.grid_mapping), sort_keys=True, default=str)
            mappings[key] = dict(refs.layout.grid_mapping)
            mapping_files[key][f"{name['quantity']} {name['grid']}"] += 1
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
    for number, (key, attributes) in enumerate(sorted(mappings.items()), start=1):
        print()
        say(f"grid_mapping {number} of {len(mappings)} without an exact EPSG code", dict(mapping_files[key]))
        report_mapping(attributes)


def kind_of(feature: dict[str, Any]) -> str:
    """What an item holds, from the names of its files: the archive, one day, one month, or something else."""
    names = [ANY_FILE.match(key.lower()) for key in feature.get("assets", {})]
    names = [name for name in names if name is not None]
    if any(name["prefix"].endswith("-archive") for name in names):
        return "archive"
    spans = Counter(span(name.groupdict()) for name in names if name["quantity"].endswith("d"))
    if not spans:
        return "without daily files"
    kind = spans.most_common(1)[0][0]
    return {"one time step": "item of one day", "one day": "item of one day", "one month": "item of one month"}.get(kind, f"item of {kind}")


async def conditional(gateway: Gateway, url: str) -> str:
    """How an item answers a second request with its own ETag: ``304``, ``200`` again, or no ETag to ask with; a
    refusal by its status only, never with what the source wrote."""
    try:
        first = await gateway.get(url)
        etag = first.headers.get("etag")
        if not etag:
            return "no ETag"
        second = await gateway.get(url, headers={"if-none-match": etag})
    except GatewayError as error:
        return f"refused: {reason(error)}"
    return f"{'weak' if etag.startswith('W/') else 'strong'} ETag, {second.status_code} on If-None-Match"


async def report_current(gateway: Gateway) -> None:
    """The items outside the archive by kind, how they answer a conditional request, and one file header per quantity."""
    pages: list[dict[str, str | None]] = []
    features = [feature for feature in await items(gateway, pages) if kind_of(feature) != "archive"]
    say("pages of the item list", len(pages))
    for number, page in enumerate(pages, start=1):
        answer = "no ETag"
        if page["etag"]:
            try:
                again = await gateway.get(str(page["url"]), headers={"if-none-match": str(page["etag"])})
            except GatewayError as error:
                answer = f"ETag, refused on If-None-Match: {reason(error)}"
            else:
                answer = f"ETag, {again.status_code} on If-None-Match"
        say(f"  page {number}", f"{answer}; Last-Modified {'given' if page['last-modified'] else 'none'}")
    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for feature in features:
        by_kind[kind_of(feature)].append(feature)
    say("items outside the archive", len(features))
    files: dict[tuple[str, str, str], dict[str, Any]] = {}
    for kind, members in sorted(by_kind.items()):
        print()
        say(kind, f"{len(members)} items")
        properties: Counter[str] = Counter()
        forms: Counter[str] = Counter()
        fields: Counter[str] = Counter()
        quantities: Counter[str] = Counter()
        answers: Counter[str] = Counter()
        for feature in members:
            properties.update(key for key in ITEM_PROPERTIES if feature.get("properties", {}).get(key) is not None)
            for key, asset in feature.get("assets", {}).items():
                forms[form(key)] += 1
                fields.update(field for field in ("file:checksum", "updated", "file:size", "expires") if field in asset)
                name = ANY_FILE.match(key.lower())
                if name is not None:
                    quantities[f"{name['prefix']} {name['quantity']} {name['grid']} ({span(name.groupdict())})"] += 1
                    if name["quantity"].endswith("d") and name["grid"] in ("ch01r", "ch01h"):
                        files.setdefault((kind, name["grid"], name["quantity"]), asset)
            answers[await conditional(gateway, f"{COLLECTION}/items/{feature['id']}")] += 1
        say("  item properties (of items)", dict(properties))
        expiries = sorted(str(f["properties"]["expires"]) for f in members if f.get("properties", {}).get("expires"))
        say("  expires, earliest and latest", f"{expiries[0]} | {expiries[-1]}" if expiries else "none")
        say("  asset fields (of assets)", dict(fields))
        say("  conditional request per item", dict(answers))
        for line, count in sorted(quantities.items()):
            say(f"  {line}", f"× {count}")
        for shape, count in sorted(forms.items()):
            say(f"  pattern {shape}", f"× {count}")
    print()
    say("file headers to read", len(files))
    for (kind, grid, quantity), asset in sorted(files.items()):
        try:
            refs = await reference_file(gateway, asset["href"], None, strict_crs=False)
        except (UnsupportedLayout, GatewayError) as error:
            say(f"{kind} {quantity} {grid}", f"refused: {reason(error)}")
            continue
        say(f"{kind} {quantity} {grid}", "")
        for label, value in zip(
            ("variable", "dtype", "grid shape", "chunks", "filters", "fill value", "crs", "a, e, c, f", "units",
             "time of the steps", "time bounds"),
            signature(refs),
            strict=True,
        ):
            say(f"  {label}", value)
        say("  time steps", f"{len(refs.times)}, {refs.times[0].date()} to {refs.times[-1].date()}")
        say("  Last-Modified given", refs.last_modified is not None)


def report_mapping(attributes: dict[str, Any]) -> None:
    """A grid_mapping that names no EPSG code exactly: its attributes, and how it differs from EPSG:2056 (LV95)."""
    for name in sorted(attributes):
        say(f"  attribute {name}", attributes[name])
    reference = CRS.from_epsg(REFERENCE_EPSG)
    try:
        ours = CRS.from_cf(attributes)
    except CRSError as error:
        say("  pyproj from_cf", f"no CRS: {form(str(error))}")
    else:
        compare("from_cf", ours, reference)
    for name in WKT_ATTRIBUTES:
        text = attributes.get(name)
        if not isinstance(text, str) or not text.strip():
            continue
        try:
            compare(name, CRS.from_user_input(text), reference)
        except CRSError as error:
            say(f"  pyproj {name}", f"no CRS: {form(str(error))}")


def compare(label: str, ours: CRS, reference: CRS) -> None:
    """Where ``ours`` differs from ``reference``: matches by confidence, method, every parameter, ellipsoid, datum, axes."""
    matches = [f"{m.auth_name}:{m.code} {m.confidence}%" for m in ours.list_authority(min_confidence=1)[:5]]
    say(f"  {label}: pyproj matches", matches or "none")
    say(f"  {label}: name", f"{ours.name!r} | EPSG:{REFERENCE_EPSG} {reference.name!r}")
    a, b = ours.coordinate_operation, reference.coordinate_operation
    if a is None or b is None:
        say(f"  {label}: projection", f"{'none' if a is None else a.method_name} | {b.method_name if b else 'none'}")
    else:
        same = "same" if a.method_name == b.method_name else "DIFFERS"
        say(f"  {label}: method", f"{same}: {a.method_name!r} | {b.method_name!r}")
        theirs = {p.name: p for p in b.params}
        for parameter in a.params:
            other = theirs.pop(parameter.name, None)
            if other is None:
                say(f"  {label}: parameter only here", f"{parameter.name} = {parameter.value} {parameter.unit_name}")
                continue
            equal = math.isclose(parameter.value, other.value, rel_tol=1e-9, abs_tol=1e-9)
            same_unit = parameter.unit_name.lower() == other.unit_name.lower()
            units = "" if same_unit else f" (units {parameter.unit_name} | {other.unit_name})"
            say(
                f"  {label}: {parameter.name}",
                f"{'same' if equal and not units else 'DIFFERS'}: {parameter.value} | {other.value}{units}",
            )
        for parameter in theirs.values():
            say(f"  {label}: parameter only in EPSG", f"{parameter.name} = {parameter.value} {parameter.unit_name}")
    for side, crs in (("here", ours), ("EPSG", reference)):
        ellipsoid = crs.ellipsoid
        say(
            f"  {label}: ellipsoid ({side})",
            f"{ellipsoid.name if ellipsoid else None}: {ellipsoid.semi_major_metre if ellipsoid else None}, "
            f"1/f {ellipsoid.inverse_flattening if ellipsoid else None}",
        )
        say(f"  {label}: datum ({side})", crs.datum.name if crs.datum else None)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # "you will likely lose important projection information": only towgs84 is read
            towgs84 = crs.to_dict().get("towgs84") if crs.is_projected else None
        say(f"  {label}: towgs84 ({side})", towgs84)
        say(f"  {label}: axes ({side})", [f"{axis.abbrev} {axis.direction} {axis.unit_name}" for axis in crs.axis_info])


async def main(layout: bool, grids: set[str], limit: int | None, current: bool = False) -> int:
    policy = Policy(allowed_hosts=frozenset({HOST}), host_intervals={HOST: INTERVAL_S})
    async with Gateway(policy) as gateway:
        if current:
            await report_current(gateway)
            return 0
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
    parser.add_argument("--current", action="store_true", help="only the items outside the archive (M5-58)")
    args = parser.parse_args(argv)
    grids = {grid.strip() for grid in args.grids.split(",") if grid.strip()}
    return asyncio.run(main(args.layout, grids, args.limit, args.current))


if __name__ == "__main__":
    sys.exit(run())
