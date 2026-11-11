#!/usr/bin/env bash
# Runs one part of the backend tests (one job of the "Backend tests" matrix in ci.yml).
#
# Usage: scripts/ci-backend-shard.sh <1|2|3|4> [extra pytest arguments]
#
# Run from the repository root. Parts 1 to 3 name what they run; part 4 is everything
# else, built as "backend/tests minus what parts 1 to 3 run". A new test file therefore
# lands in part 4 and is never left out, and no file runs in two parts as long as the
# three named parts do not overlap (backend/tests/test_ci_backend_shards.py checks both).
#
# The split follows the durations of a full run (11.11.2026, 10358 tests, 4 cores): the
# sum of the test times was about 3050 s, and each part carries about a quarter of it.
#   1  integration                     779 s
#   2  earthx/api                      769 s
#   3  earthx/processing memory tests + earthx/runner   737 s
#   4  the rest (processing without memory tests, jobs, access, catalog, ...)   767 s
# Move a directory or file between parts when a part runs clearly longer than the others
# (the 50 slowest tests and the time of each part are in the log of each job);
# backend/tests/test_ci_backend_shards.py keeps the rules.
#
# With CI_SHARD_PRINT_ARGS=1 the script prints the pytest arguments, one per line, and
# runs nothing (used by that test).
set -euo pipefail

shard="${1:-}"
if [ $# -gt 0 ]; then shift; fi

shard_1=(backend/tests/integration)
shard_2=(backend/tests/earthx/api)
# The memory tests measure peaks per process and need most of the time of this part; the
# glob is expanded here, so a new test_memory_*.py file joins this part.
shard_3=(backend/tests/earthx/runner backend/tests/earthx/processing/test_memory_*.py)

case "$shard" in
  1) args=("${shard_1[@]}") ;;
  2) args=("${shard_2[@]}") ;;
  3) args=("${shard_3[@]}") ;;
  4)
    args=(backend/tests)
    for path in "${shard_1[@]}" "${shard_2[@]}" "${shard_3[@]}"; do
      args+=("--ignore=$path")
    done
    ;;
  *)
    echo "usage: $0 <1|2|3|4> [pytest arguments]" >&2
    exit 2
    ;;
esac

if [ "${CI_SHARD_PRINT_ARGS:-}" = "1" ]; then
  printf '%s\n' "${args[@]}"
  exit 0
fi

echo "Backend tests, part $shard: ${args[*]}"
exec pytest "${args[@]}" "$@"
