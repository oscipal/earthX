#!/usr/bin/env bash
# Two states of the backend against the synthetic source, in turn, each measurement REPS times (NM4-62).
#
#   COGS=<cog-dir> OUT=<dir> scripts/tile-bench/compare.sh <rev-a> <rev-b>
#
# Per state: a worktree of the revision under $OUT/trees and a database earthx_bench_<sha> with pgstac and the
# state's own migrations (the PG* variables name the server, the role creates databases). Per repetition and state,
# from fresh processes: the cold and the warm mosaic tile (cold_warm.py: 4 scenes, NDVI, z10, 512 px), the crop of
# red and nir over 0.05° (crop.py), the jobs reproject and ndvi_mask (job_bench.py). Once per state the job part of
# try-job.ps1, twice in a row (job_bench.py --sequence). The states alternate which goes first. The scripts are this
# checkout's for both. REPS (5) and the source's RTT_MS, CONNECT_MS, MBIT, ITEM_MS as in bench.sh.
# Every result goes to $OUT/results.jsonl; at the end compare_summary.py prints the table.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
: "${COGS:?the directory make_cogs.py wrote}" "${OUT:?a directory for worktrees and logs}"
[ $# -eq 2 ] || { echo "usage: compare.sh <rev-a> <rev-b>" >&2; exit 2; }
reps="${REPS:-5}"
mkdir -p "$OUT/trees"
results="$OUT/results.jsonl"
: >"$results"

states=()
for rev in "$1" "$2"; do
  sha="$(git -C "$repo" rev-parse --short=7 "$rev^{commit}")"
  tree="$OUT/trees/$sha"
  [ -d "$tree" ] || git -C "$repo" worktree add --detach "$tree" "$sha" >/dev/null
  db="earthx_bench_$sha"
  psql -qc "drop database if exists $db" >/dev/null
  psql -qc "create database $db template template0" >/dev/null
  PGDATABASE="$db" psql -qc "create extension if not exists postgis" >/dev/null
  PGDATABASE="$db" pypgstac migrate >/dev/null
  PGDATABASE="$db" PYTHONPATH="$tree/backend" python -m earthx.catalog.load >/dev/null
  states+=("$sha")
done

# Each JSON line of stdin as one result, with the state and the kind of measurement.
tag() {
  python -c 'import json, sys
for line in sys.stdin:
    if line.startswith("{"):
        print(json.dumps({"state": sys.argv[1], "kind": sys.argv[2], **json.loads(line)}))' "$1" "$2" >>"$results"
}

measure() {
  local sha="$1" tree="$OUT/trees/$1" log="$OUT/logs/$1"
  mkdir -p "$log"
  export PGDATABASE="earthx_bench_$sha" BACKEND="$tree/backend"
  CLIENT=cold_warm.py "$here/bench.sh" "tile_$sha" 2>>"$log/bench.err" | sed -n 1p | tag "$sha" tile
  CLIENT=crop.py "$here/bench.sh" "crop_$sha" --size 0.05 2>>"$log/bench.err" | sed -n 1p | tag "$sha" crop
  python -I "$here/slow_source.py" "$COGS" --rtt-ms "${RTT_MS:-170}" --connect-ms "${CONNECT_MS:-350}" \
    --mbit "${MBIT:-0}" --log "$log/source_jobs.jsonl" >/dev/null 2>&1 &
  local source_pid=$!
  for case in reproject ndvi_mask; do
    rm -f "$log/job.jsonl"
    PYTHONPATH="$tree/backend" python "$here/job_bench.py" --case "$case" --reps 1 --out "$log/job.jsonl" \
      >>"$log/job.out" 2>&1
    tag "$sha" job <"$log/job.jsonl"
  done
  kill "$source_pid"; wait "$source_pid" 2>/dev/null || true
}

for rep in $(seq "$reps"); do
  if [ $((rep % 2)) -eq 1 ]; then order=("${states[0]}" "${states[1]}"); else order=("${states[1]}" "${states[0]}"); fi
  for sha in "${order[@]}"; do
    echo "repetition $rep/$reps: $sha" >&2
    measure "$sha"
  done
done

# The job part of try-job.ps1, twice with the same order: whether the second round is a cache hit.
for sha in "${states[@]}"; do
  python -I "$here/slow_source.py" "$COGS" --rtt-ms "${RTT_MS:-170}" --connect-ms "${CONNECT_MS:-350}" \
    --mbit "${MBIT:-0}" --log "$OUT/logs/$sha/source_sequence.jsonl" >/dev/null 2>&1 &
  source_pid=$!
  rm -f "$OUT/logs/$sha/sequence.jsonl"
  PGDATABASE="earthx_bench_$sha" PYTHONPATH="$OUT/trees/$sha/backend" python "$here/job_bench.py" --sequence \
    --out "$OUT/logs/$sha/sequence.jsonl" >>"$OUT/logs/$sha/job.out" 2>&1
  tag "$sha" sequence <"$OUT/logs/$sha/sequence.jsonl"
  kill "$source_pid"; wait "$source_pid" 2>/dev/null || true
done

python "$here/compare_summary.py" "$results" "${states[0]}" "${states[1]}"
