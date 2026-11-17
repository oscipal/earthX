#!/usr/bin/env python3
"""Summary of M4 of the M5-37 bench (plan §7): a pyramid build alone, and with a run on the same host.

    python scripts/tile-bench/pyramid_turns_summary.py <bench-dir>

Reads ``marks.jsonl``, ``source.jsonl`` of the synthetic source, ``m4-alone-<side>-<rep>.jsonl`` and
``m4-both-<side>-<rep>.jsonl`` of `pyramid_turns.py` and ``m4-runs-<side>-<rep>.jsonl`` of `source_turns.py`.

Since the count of a build's requests takes every request GDAL makes (the ``HEAD`` of a file and the retries too,
M5-37), every request at the source is charged to the host's turn: with 0.25 s per host the requests of build and run
together stay at about 4 per second when they share, on average.
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
        runs = [r for rep in reps for r in lines(bench / f"m4-alone-{side}-{rep}.jsonl")]
        walls = [r["end"] - r["start"] for r in runs]
        seen = [len([s for s in source if r["start"] <= s["t0"] <= r["end"]]) for r in runs]
        counted = [r["requests"] for r in runs]
        print(
            f"alone {side:6} n={len(walls)} build wall median {statistics.median(walls):.2f} s, p95 {p95(walls):.2f} s; "
            f"requests at the source {statistics.median(seen)}, charged {statistics.median(counted)}"
        )
    for side in ("main", "branch"):
        requests, builds = [], []
        for rep in reps:
            run = lines(bench / f"m4-runs-{side}-{rep}.jsonl")
            build = lines(bench / f"m4-both-{side}-{rep}.jsonl")[0]
            low, high = max(min(r["start"] for r in run), build["start"]), min(max(r["end"] for r in run), build["end"])
            seen = [r for r in source if low <= r["t0"] <= high]
            requests.append(len(seen) / (high - low))
            builds.append(build["end"] - build["start"])
        print(
            f"both  {side:6} n={len(requests)} while both ran: requests/s at the source median "
            f"{statistics.median(requests):.2f} (max {max(requests):.2f}); build wall median {statistics.median(builds):.1f} s"
        )


if __name__ == "__main__":
    main()
