#!/usr/bin/env bash
# One measured view (NM4-26): starts the slow source and the tiler afresh, asks for the view, prints the summary.
#
#   COGS=<cog-dir> OUT=<dir> scripts/tile-bench/bench.sh <tag> [view.py arguments]
#
# CLIENT=crop.py or CLIENT=hashes.py asks that script instead of view.py, with the same arguments.
# Source and tiler from the environment: RTT_MS (170), CONNECT_MS (350), MBIT (0 = unlimited), ITEM_MS (300),
# WORKERS (1), EXTRA_GDAL (none), BACKEND (the backend the tiler runs from; this checkout's, compare.sh names another).
# The item cache and the statistics cache in Postgres are emptied first, so every run starts cold; the PG* variables
# name the database (the cloud session's setup writes them to .env.test).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
tag="$1"; shift
: "${COGS:?the directory make_cogs.py wrote}" "${OUT:?a directory for the logs}"
mkdir -p "$OUT"
psql -qc "delete from earthx_search_cache; delete from earthx_stats_cache" >/dev/null
rm -f "$OUT/source_$tag.jsonl" "$OUT/tiler_$tag.jsonl"
cleanup() { kill "$source_pid" "$tiler_pid" 2>/dev/null || true; wait 2>/dev/null || true; }
trap cleanup EXIT
python -I "$here/slow_source.py" "$COGS" --rtt-ms "${RTT_MS:-170}" --connect-ms "${CONNECT_MS:-350}" \
  --mbit "${MBIT:-0}" --log "$OUT/source_$tag.jsonl" >"$OUT/source_$tag.out" 2>&1 &
source_pid=$!
PYTHONPATH="${BACKEND:-$repo/backend}" python "$here/run_tiler.py" --source http://127.0.0.1:9100 --item-ms "${ITEM_MS:-300}" \
  --workers "${WORKERS:-1}" --log "$OUT/tiler_$tag.jsonl" >"$OUT/tiler_$tag.out" 2>&1 &
tiler_pid=$!
for _ in $(seq 60); do curl -sf http://127.0.0.1:8101/health >/dev/null && break; sleep 0.5; done
if [ -n "${CLIENT:-}" ]; then
  python "$here/$CLIENT" "$@"
else
  python "$here/view.py" --out "$OUT/view_$tag.jsonl" "$@"
fi
rss=$(ps -o rss= --ppid "$tiler_pid" -p "$tiler_pid" | awk '{kb += $1} END {print int(kb / 1024)}')
# Both processes end before the logs are read, so that no line is still being written.
cleanup
python "$here/summary.py" "$OUT/tiler_$tag.jsonl" "$OUT/source_$tag.jsonl"
echo "{\"tiler_rss_MB\": $rss}"
