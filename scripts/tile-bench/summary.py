#!/usr/bin/env python3
"""Summary of one run (NM4-26): the tiler's phases per tile, and what the source served.

    python scripts/tile-bench/summary.py <tiler.jsonl> <source.jsonl>

Phases as ``median/mean`` in ms. ``source_MB`` is every byte the source sent, ``needed_MB`` the union of the byte
ranges per URL: what the view needs at least. Their ratio is the share GDAL fetched more than once.
"""

import collections
import json
import statistics
import sys

PHASES = ("total", "item", "dependency", "syncdeps_wait", "endpoint_wait", "open", "read", "compute", "encode",
          "endpoint_run")


def union_bytes(ranges: list[tuple[int, int]]) -> int:
    total, current = 0, None
    for start, end in sorted(ranges):
        if current is None or start > current[1]:
            if current is not None:
                total += current[1] - current[0]
            current = [start, end]
        else:
            current[1] = max(current[1], end)
    return total + (current[1] - current[0] if current else 0)


def main() -> None:
    rows = [json.loads(line) for line in open(sys.argv[1])]
    fetches = [row for row in rows if "source_item_fetch" in row]
    tiles = [row for row in rows if row.get("path", [""])[0] == "WebMercatorQuad"]
    out: dict = {"tiles": len(tiles), "item_fetches": len(fetches),
                 "distinct_items": len({row["source_item_fetch"] for row in fetches})}
    for name in PHASES:
        values = sorted(row.get(name, 0.0) for row in tiles) or [0.0]
        out[name] = f"{values[len(values) // 2]:.0f}/{statistics.mean(values):.0f}"
    source = [json.loads(line) for line in open(sys.argv[2])]
    by_url = collections.defaultdict(list)
    for row in source:
        if row["method"] == "GET":
            by_url[row["url"]].append((row["start"], row["start"] + row["bytes"]))
    out.update(source_requests=len(source), source_heads=sum(row["method"] == "HEAD" for row in source),
               source_connections=len({row["conn"] for row in source}),
               source_MB=round(sum(row["bytes"] for row in source) / 1e6, 1),
               needed_MB=round(sum(union_bytes(ranges) for ranges in by_url.values()) / 1e6, 1))
    print(json.dumps(out))


if __name__ == "__main__":
    main()
