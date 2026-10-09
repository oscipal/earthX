#!/usr/bin/env bash
# Frontend dependency freshness check for scripts/setup-cloud-session.sh (M3-24).
#
# node_modules is current for a given package-lock.json when a hash of that
# lockfile, written right after the last successful `npm ci`, matches the
# lockfile's current hash. Split into its own file (no CLAUDE_CODE_REMOTE
# check, no early `exit`) so it can be sourced and unit-tested on its own,
# without running the rest of the SessionStart hook.

frontend_lock_hash() {
  # $1: path to package-lock.json
  sha256sum "$1" 2>/dev/null | awk '{print $1}'
}

frontend_deps_current() {
  # $1: package-lock.json  $2: node_modules dir  $3: stored-hash file
  local lockfile="$1" node_modules="$2" hash_file="$3"
  [ -f "$lockfile" ] || return 1
  [ -d "$node_modules" ] || return 1
  [ -f "$hash_file" ] || return 1
  [ "$(frontend_lock_hash "$lockfile")" = "$(cat "$hash_file")" ]
}
