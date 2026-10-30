#!/usr/bin/env python3
"""The table of ``compare.sh`` (NM4-62): per measure the median and the range of both states, and their ratio.

    python scripts/tile-bench/compare_summary.py <results.jsonl> <state-a> <state-b>

Times in s. The job's parts come from ``job_bench.py``: ``Warten`` is accepted to running (the queue), ``Laufzeit``
running to finished. Inside it ``Start`` is the child process up to its run (spawn and imports), ``Lesen`` opening the
COGs and reading their blocks, ``Rechnen`` the pixel steps and the ``reproject`` pass, ``Schreiben`` the work files,
the mask, the COG of the result and the upload.
"""

import json
import statistics
import sys


def job_parts(row: dict) -> dict:
    phase = {name: row.get(f"child_{name}_ms", 0.0) for name in
             ("open", "read", "kernels", "mask", "pass_pixel", "pass_grid", "cog", "run")}
    return {
        "Warten": row["queue_ms"],
        "Laufzeit": row["run_ms"],
        "Start": row.get("spawn_ms", 0.0) + row.get("import_ms", 0.0),
        "Lesen": phase["open"] + phase["read"],
        "Rechnen": phase["kernels"] + phase["pass_grid"],
        "Schreiben": phase["pass_pixel"] - phase["read"] - phase["kernels"] + phase["mask"] + phase["cog"]
        + row.get("upload_ms", 0.0),
    }


def values(rows: list[dict]) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}

    def put(name: str, value: float) -> None:
        out.setdefault(name, []).append(value)

    for row in rows:
        if row["kind"] == "tile":
            put("Mosaik-Kachel kalt (4 Szenen, NDVI, z10, 512 px)", row["cold_s"])
            put("Mosaik-Kachel warm", row["warm_s"])
        elif row["kind"] == "crop":
            put("Zuschnitt red+nir, 0,05°", row["s"])
        elif row["kind"] == "job":
            for part, ms in job_parts(row).items():
                put(f"Job {row['case']}: {part}", ms / 1000)
        elif row["kind"] == "sequence":
            put(f"try-job-Ablauf Runde {row['round']} (Abfrage alle {row['poll_s']:g} s)", row["wall_ms"] / 1000)
            put(f"try-job-Ablauf Runde {row['round']}: Cache-Treffer", float(row["first_hit"]))
    return out


def cell(numbers: list[float] | None) -> str:
    if not numbers:
        return "–"
    median = statistics.median(numbers)
    if len(numbers) == 1:
        return f"{median:.2f}"
    return f"{median:.2f} ({min(numbers):.2f}–{max(numbers):.2f})"


def main() -> None:
    path, a, b = sys.argv[1:4]
    rows = [json.loads(line) for line in open(path)]
    by_state = {state: values([row for row in rows if row["state"] == state]) for state in (a, b)}
    names = list(dict.fromkeys(list(by_state[a]) + list(by_state[b])))
    reps = max((len(v) for v in by_state[a].values()), default=0)
    print(f"| Messgröße (s, Median und Spanne, n = {reps}) | {a} | {b} | {b}/{a} |")
    print("|---|---|---|---|")
    for name in names:
        left, right = by_state[a].get(name), by_state[b].get(name)
        if name.endswith("Cache-Treffer"):
            print(f"| {name} | {'ja' if left and all(left) else 'nein'} | {'ja' if right and all(right) else 'nein'} | |")
            continue
        ratio = ""
        if left and right and statistics.median(left) > 0:
            ratio = f"{statistics.median(right) / statistics.median(left):.2f}"
        print(f"| {name} | {cell(left)} | {cell(right)} | {ratio} |")


if __name__ == "__main__":
    main()
