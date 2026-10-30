#!/usr/bin/env python3
"""Which properties of Earth Search's Sentinel-2 L2A items a search can filter by, and whether the source does (DS-02c).

One-time network step, metadata only. The script makes no request of its own (adr/0002, "Nachtrag 2026-09-20": the
platform's `gateway` connects to the checked address, which a cloud session's egress proxy refuses, so the answers
are saved with ``curl`` first). From the repository root:

1. The sample, 7 regions of one degree (no one's AOI) in two seasons, and the queryables of the collection:

    mkdir -p <dir>/searches <dir>/probes <dir>/years
    U=https://earth-search.aws.element84.com/v1
    curl -sS $U/collections/sentinel-2-c1-l2a/queryables -o <dir>/queryables.json
    search() {  # name, bbox, datetime, file
      curl -sS -X POST $U/search -H 'Content-Type: application/json' \\
        -d "{\\"collections\\":[\\"sentinel-2-c1-l2a\\"],\\"bbox\\":[$2],\\"datetime\\":\\"$3\\",\\"limit\\":100}" -o "$4"
    }
    A=2024-06-01T00:00:00Z/2024-06-30T23:59:59Z; B=2024-12-01T00:00:00Z/2024-12-31T23:59:59Z
    for r in "alps 10,47,11,48" "amazon -60,-10,-59,-9" "sahara 5,25,6,26" "norway 10,61,11,62" \\
             "coast -9.5,38,-8.5,39" "ganges 85,25,86,26" "outback 145,-25,146,-24"; do
      set -- $r; search $1-jun "$2" $A <dir>/searches/$1-jun.json; search $1-dec "$2" $B <dir>/searches/$1-dec.json
    done
    for y in 2016-07 2018-07 2020-07 2022-07 2023-07 2025-07 2026-07; do   # which values the choice filters see over the years
      search $y 10,47,10.5,47.5 $y-01T00:00:00Z/$y-31T23:59:59Z <dir>/years/$y.json
    done

2. ``python scripts/ds-02-filters/measure.py inventory <dir>`` lists every property of the sample.
3. ``python scripts/ds-02-filters/measure.py commands <dir>`` writes ``<dir>/probe.sh``: for each candidate and box one
   search with a filter (``query`` of the STAC extension), saved under ``<dir>/probes``. Run it with ``bash <dir>/probe.sh``.
4. ``python scripts/ds-02-filters/measure.py analyze <dir>`` compares each answer with what the unfiltered sample says it
   must hold (same box, same time) and prints the table: a property **acts** only when every answer has exactly the
   expected scenes. ``--markdown`` prints it for the PR.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import statistics
import sys
from collections import Counter

# The boxes the probes use, from the sample: spread over the world and the seasons.
# `y2026-02` is the month the processing baseline changed in: the only box with two baselines in it.
PROBE_BOXES = ("alps-jun", "norway-jun", "ganges-dec", "outback-dec", "y2026-02")
CHOICE_MAX_VALUES = 40  # a property with more values is not a list to tick
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T")

# Properties no user filters by, with the reason: identifiers, timestamps, objects and constants are found by the
# rules in `classify`, this names the rest.
TECHNICAL = {
    "proj:epsg": "technical (UTM zone of the tile)",
    "mgrs:utm_zone": "technical (part of the tile)",
    "mgrs:latitude_band": "technical (part of the tile)",
    "mgrs:grid_square": "technical (part of the tile)",
    "s2:reflectance_conversion_factor": "technical (Earth–Sun distance factor)",
    "view:azimuth": "technical (viewing geometry, near-nadir)",
    "view:incidence_angle": "technical (viewing geometry, near-nadir)",
}


def load_sample(directory: str) -> dict[str, list[dict]]:
    """Every saved search of the sample by name (``alps-jun``), the features only."""
    sample = {}
    for path in sorted(glob.glob(os.path.join(directory, "searches", "*.json"))):
        with open(path, encoding="utf-8") as handle:
            sample[os.path.basename(path)[:-5]] = json.load(handle)["features"]
    return sample


def probe_features(directory: str) -> dict[str, list[dict]]:
    """The unfiltered answers the probes are compared with: the sample, and the month of the baseline change."""
    features = load_sample(directory)
    with open(os.path.join(directory, "years", "2026-02.json"), encoding="utf-8") as handle:
        features["y2026-02"] = json.load(handle)["features"]
    return features


def properties_of(sample: dict[str, list[dict]]) -> dict[str, list]:
    found: dict[str, list] = {}
    for features in sample.values():
        for item in features:
            for name, value in item["properties"].items():
                found.setdefault(name, []).append(value)
    return found


def classify(name: str, values: list, items: int) -> tuple[str, str]:
    """(kind, reason): ``range``, ``values`` or ``skip`` for a property of the sample."""
    if name in TECHNICAL:
        return "skip", TECHNICAL[name]
    if any(isinstance(v, (dict, list)) for v in values):
        return "skip", "object or list"
    if any(isinstance(v, bool) for v in values):
        return "skip", "technical flag"
    texts = [v for v in values if isinstance(v, str)]
    if texts and any(TIMESTAMP.match(v) for v in texts):
        return "skip", "timestamp"
    distinct = set(map(str, values))
    if len(distinct) == 1:
        return "skip", "one value in every item"
    numbers = [v for v in values if isinstance(v, (int, float))]
    if len(numbers) == len(values):
        return "range", "number"
    if len(distinct) == len(values) and len(values) > 1:
        return "skip", "identifier (one per item)"
    if len(distinct) <= CHOICE_MAX_VALUES:
        return "values", "text with few values"
    return "skip", f"text with {len(distinct)} values"


def inventory(directory: str) -> None:
    sample = load_sample(directory)
    items = sum(len(f) for f in sample.values())
    found = properties_of(sample)
    print(f"{items} items from {len(sample)} searches\n")
    print(f"{'property':44} {'kind':7} {'present':>8}  range or values / reason")
    for name in sorted(found):
        values = found[name]
        kind, reason = classify(name, values, items)
        if kind == "range":
            detail = f"{min(values):.4g} … {max(values):.4g}  ({reason})"
        elif kind == "values":
            detail = ", ".join(f"{k} ×{n}" for k, n in Counter(map(str, values)).most_common(6))
        else:
            detail = reason
        print(f"{name:44} {kind:7} {len(values):>5}/{items:<4} {detail}")
    queryables = os.path.join(directory, "queryables.json")
    if os.path.exists(queryables):
        with open(queryables, encoding="utf-8") as handle:
            print("\nqueryables of the source:", sorted(json.load(handle).get("properties", {})))
    years = {}
    for path in sorted(glob.glob(os.path.join(directory, "years", "*.json"))):
        with open(path, encoding="utf-8") as handle:
            for item in json.load(handle)["features"]:
                years.setdefault(os.path.basename(path)[:-5], []).append(item["properties"])
    for key in ("platform", "s2:processing_baseline"):
        print(f"\n{key} by year:")
        for year, props in years.items():
            print(f"  {year}: {dict(Counter(str(p.get(key)) for p in props))}")
    print("\nhas s2:dark_features_percentage, by year:", {y: f"{sum('s2:dark_features_percentage' in p for p in ps)}/{len(ps)}" for y, ps in years.items()})


def candidates(directory: str) -> list[tuple[str, str]]:
    sample = load_sample(directory)
    items = sum(len(f) for f in sample.values())
    out = []
    for name, values in sorted(properties_of(sample).items()):
        kind, _ = classify(name, values, items)
        if kind != "skip":
            out.append((name, kind))
    return out


def probe_queries(name: str, kind: str, features: list[dict]) -> list[dict]:
    """The filters tried on one box: a range by its quartiles, a choice by each value present."""
    values = [f["properties"][name] for f in features if name in f["properties"]]
    if not values:
        return []
    if kind == "range":
        low, mid, high = (round(q, 3) for q in statistics.quantiles(values, n=4)) if len(values) > 3 else (min(values),) * 3
        return [{name: {"gte": mid}}, {name: {"lte": mid}}, {name: {"gte": low, "lte": high}}]
    return [{name: {"in": [v]}} for v, _ in Counter(values).most_common(4)]


def holds(properties: dict, query: dict) -> bool:
    for name, operators in query.items():
        if name not in properties:
            return False
        value = properties[name]
        for op, bound in operators.items():
            if op == "gte" and not value >= bound:
                return False
            if op == "lte" and not value <= bound:
                return False
            if op == "in" and value not in bound:
                return False
    return True


def commands(directory: str) -> None:
    sample = probe_features(directory)
    plan = []
    lines = ["#!/bin/bash", "# written by measure.py commands: one search per probe, saved for `analyze`; no secret, no AOI of anyone",
             "U=https://earth-search.aws.element84.com/v1", "n=0"]
    for name, kind in candidates(directory):
        for box in PROBE_BOXES:
            features = sample[box]
            for query in probe_queries(name, kind, features):
                index = len(plan)
                expected = sorted(f["id"] for f in features if holds(f["properties"], query))
                plan.append({"file": f"probes/{index}.json", "box": box, "property": name, "query": query, "expected": expected, "of": len(features)})
    for entry in plan:
        start, end, bbox = BOX_BODIES[entry["box"]]
        body = json.dumps({"collections": ["sentinel-2-c1-l2a"], "bbox": bbox, "datetime": f"{start}/{end}", "limit": 100, "query": entry["query"]}, separators=(",", ":"))
        lines.append(f"curl -sS -X POST $U/search -H 'Content-Type: application/json' -d '{body}' -o {directory}/{entry['file']} &")
        lines.append("n=$((n+1)); if [ $((n % 6)) -eq 0 ]; then wait; fi")
    lines.append("wait")
    with open(os.path.join(directory, "plan.json"), "w", encoding="utf-8") as handle:
        json.dump(plan, handle)
    script = os.path.join(directory, "probe.sh")
    with open(script, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    print(f"{len(plan)} probes for {len(candidates(directory))} candidates -> {script}")


# The four boxes of the sample as the searches of the docstring asked them.
JUNE = ("2024-06-01T00:00:00Z", "2024-06-30T23:59:59Z")
DECEMBER = ("2024-12-01T00:00:00Z", "2024-12-31T23:59:59Z")
BOX_BODIES = {
    "alps-jun": (*JUNE, [10, 47, 11, 48]),
    "norway-jun": (*JUNE, [10, 61, 11, 62]),
    "ganges-dec": (*DECEMBER, [85, 25, 86, 26]),
    "outback-dec": (*DECEMBER, [145, -25, 146, -24]),
    "y2026-02": ("2026-02-01T00:00:00Z", "2026-02-28T23:59:59Z", [10, 47, 10.5, 47.5]),
}


def analyze(directory: str, markdown: bool) -> None:
    with open(os.path.join(directory, "plan.json"), encoding="utf-8") as handle:
        plan = json.load(handle)
    sample = load_sample(directory)
    found = properties_of(sample)
    items = sum(len(f) for f in sample.values())
    kinds = dict(candidates(directory))
    rows = []
    for name, kind in kinds.items():
        mine = [p for p in plan if p["property"] == name]
        right = wrong = narrowed = 0
        problems = []
        for probe in mine:
            path = os.path.join(directory, probe["file"])
            if not os.path.exists(path):
                problems.append("no answer saved")
                continue
            with open(path, encoding="utf-8") as handle:
                answer = json.load(handle)
            if "features" not in answer:
                problems.append(f"error answer ({answer.get('code', answer.get('status', '?'))})")
                continue
            got = sorted(f["id"] for f in answer["features"])
            if got == probe["expected"]:
                right += 1
                narrowed += len(got) < probe["of"]
            else:
                wrong += 1
                problems.append(f"{probe['box']} {probe['query']}: {len(got)} found, {len(probe['expected'])} expected")
        values = found[name]
        present = len(values)
        detail = (f"{min(values):.4g} … {max(values):.4g}" if kind == "range" else ", ".join(sorted(set(map(str, values)))[:6]))
        acts = bool(mine) and wrong == 0 and not problems and narrowed > 0
        rows.append((name, kind, type(values[0]).__name__, detail, f"{present}/{items}", f"{right}/{len(mine)}", narrowed, "yes" if acts else "NO", "; ".join(problems[:2])))
    header = ("property", "kind", "type", "range or values", "present", "answers as expected", "narrowed", "acts", "problems")
    if markdown:
        print("| " + " | ".join(header) + " |\n|" + "---|" * len(header))
        for row in rows:
            print("| " + " | ".join(str(c) for c in row) + " |")
    else:
        for row in rows:
            print(" | ".join(str(c) for c in row))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=("inventory", "commands", "analyze"))
    parser.add_argument("directory")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "inventory":
        inventory(args.directory)
    elif args.command == "commands":
        commands(args.directory)
    else:
        analyze(args.directory, args.markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
