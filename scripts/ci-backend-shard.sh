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
# The split follows the durations of a full run on 11.11.2026 (10358 tests, 4 cores), then
# the first CI run of the four parts (pytest step: 390 s, 209 s, 291 s, 267 s) moved two
# integration files from part 1 to the other two, so that no part runs far behind:
#   1  integration (without the two files below)
#   2  earthx/api and integration/test_api_federating.py
#   3  earthx/processing memory tests and earthx/runner
#   4  the rest: processing without memory tests, jobs, access, catalog, ...
#      and integration/test_api_mixed_search.py
# Move a directory or file between parts when a part runs clearly longer than the others
# (the 50 slowest tests and the time of each part are in the log of each job);
# backend/tests/test_ci_backend_shards.py keeps the rules.
#
# With CI_SHARD_PRINT_ARGS=1 the script prints the pytest arguments, one per line, and
# runs nothing (used by that test).
set -euo pipefail

shard="${1:-}"
if [ $# -gt 0 ]; then shift; fi

# Integration tests wait on Postgres and ran longest per test in CI; two of its files
# go to the parts that finished early (4 gets mixed_search without being told: it is
# not named anywhere).
integration=backend/tests/integration
moved_to_2=("$integration/test_api_federating.py")
moved_to_4=("$integration/test_api_mixed_search.py")
shard_1=()
for file in "$integration"/test_*.py; do
  case " ${moved_to_2[*]} ${moved_to_4[*]} " in
    *" $file "*) ;;
    *) shard_1+=("$file") ;;
  esac
done
shard_2=(backend/tests/earthx/api "${moved_to_2[@]}")
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
