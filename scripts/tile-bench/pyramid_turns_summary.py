#!/usr/bin/env python3
"""Summary of M4 of the M5-37 bench (plan §7): a pyramid build alone, and with a run on the same host.

    python scripts/tile-bench/pyramid_turns_summary.py <bench-dir>

Reads ``marks.jsonl``, ``source.jsonl`` of the synthetic source, ``m4-alone-<side>-<rep>.jsonl`` and
``m4-both-<side>-<rep>.jsonl`` of `pyramid_turns.py` and ``m4-runs-<side>-<rep>.jsonl`` of `source_turns.py`.

*Turns* at the source are the starts that take a turn: a ``GET`` of ``page.json`` (the run) and the first request for a
file of the build (its ``HEAD``; GDAL's ``GET`` of the same file follows within the turn and is not counted by the core).
With an interval of 0.25 s per host, the turns of build and run together stay at about 4 per second when they share.
"""

import json
import statistics
import sys
from pathlib import Path


def lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]


def main() -> None:
    bench = Path(sys.argv[1])
    source = lines(bench / "source.jsonl")
    reps = sorted({path.stem.rsplit("-", 1)[1] for path in bench.glob("m4-alone-main-*.jsonl")})
    for side in ("main", "branch"):
        walls = [r["end"] - r["start"] for rep in reps for r in lines(bench / f"m4-alone-{side}-{rep}.jsonl")]
        print(f"alone {side:6} n={len(walls)} build wall median {statistics.median(walls):.2f} s, p95 {p95(walls):.2f} s")
    for side in ("main", "branch"):
        requests, turns, builds = [], [], []
        for rep in reps:
            run = lines(bench / f"m4-runs-{side}-{rep}.jsonl")
            build = lines(bench / f"m4-both-{side}-{rep}.jsonl")[0]
            low, high = max(min(r["start"] for r in run), build["start"]), min(max(r["end"] for r in run), build["end"])
            seen = [r for r in source if low <= r["t0"] <= high]
            took = [r for r in seen if r["url"].endswith("page.json") or (r["method"] == "HEAD" and r["url"].endswith(".tif"))]
            requests.append(len(seen) / (high - low))
            turns.append(len(took) / (high - low))
            builds.append(build["end"] - build["start"])
        print(
            f"both  {side:6} n={len(turns)} while both ran: requests/s median {statistics.median(requests):.2f}, "
            f"turns/s median {statistics.median(turns):.2f} (max {max(turns):.2f}); build wall median "
            f"{statistics.median(builds):.1f} s"
        )


if __name__ == "__main__":
    main()
