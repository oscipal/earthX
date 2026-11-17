#!/usr/bin/env python3
"""Summary of the M5-37 bench (plan §7): M1 spacing over instances, M2 cost per request, M3 breaker.

    python scripts/tile-bench/source_turns_summary.py <bench-dir>

Reads ``marks.jsonl`` (begin and end of each run, on the monotonic clock all processes share), ``source.jsonl`` of the
synthetic source and ``m<case>-<side>-<rep>.jsonl`` of `source_turns.py`. Prints one line per case and side: medians
over the repetitions, and for M2 the median and p95 over all requests.
"""

import collections
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
    marks = {mark["mark"]: mark["t"] for mark in lines(bench / "marks.jsonl")}
    source = lines(bench / "source.jsonl")
    runs = collections.defaultdict(list)
    for name in marks:
        if name.endswith("-begin"):
            case, side, rep, _ = name.split("-")
            runs[(case, side)].append(rep)

    def served(case: str, side: str, rep: str) -> list[dict]:
        begin, end = marks[f"{case}-{side}-{rep}-begin"], marks[f"{case}-{side}-{rep}-end"]
        return sorted((r for r in source if begin <= r["t0"] <= end), key=lambda r: r["t0"])

    for side in ("main", "branch"):
        gaps_min, gaps_median, walls = [], [], []
        for rep in runs[("m1", side)]:
            starts = [r["t0"] for r in served("m1", side, rep)]
            gaps = [b - a for a, b in zip(starts, starts[1:], strict=False)]
            gaps_min.append(min(gaps))
            gaps_median.append(statistics.median(gaps))
            walls.append(starts[-1] - starts[0])
        print(
            f"M1 {side:6} n={len(walls)} gap min {statistics.median(gaps_min):.3f} s, "
            f"gap median {statistics.median(gaps_median):.3f} s, wall {statistics.median(walls):.1f} s"
        )

    for side in ("main", "branch"):
        durations, walls = [], []
        for rep in runs[("m2", side)]:
            records = lines(bench / f"m2-{side}-{rep}.jsonl")
            durations += [r["end"] - r["start"] for r in records if r["outcome"] == "ok"]
            walls.append(max(r["end"] for r in records) - min(r["start"] for r in records))
        print(
            f"M2 {side:6} n={len(durations)} per request median {statistics.median(durations) * 1000:.1f} ms, "
            f"p95 {p95(durations) * 1000:.1f} ms, wall median {statistics.median(walls):.2f} s, p95 {p95(walls):.2f} s"
        )

    for side in ("main", "branch"):
        failed_at_source, outcomes = [], collections.Counter()
        for rep in runs[("m3", side)]:
            failed_at_source.append(sum(1 for r in served("m3", side, rep) if r.get("status") == 503))
            outcomes.update(r["outcome"] for r in lines(bench / f"m3-{side}-{rep}.jsonl"))
        print(
            f"M3 {side:6} n={len(failed_at_source)} 503 answered at the source per run: median "
            f"{statistics.median(failed_at_source)}, min {min(failed_at_source)}, max {max(failed_at_source)}; "
            f"outcomes {dict(outcomes)}"
        )


if __name__ == "__main__":
    main()
