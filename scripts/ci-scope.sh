#!/usr/bin/env bash
# Decides whether a CI run is for a docs-only pull request.
#
# Writes `docs_only=true|false` to $GITHUB_OUTPUT. `true` only for a pull request whose
# own changes (merge base of the base branch and the head, three dots) all lie under
# docs/. Everything else - push to main, manual run, no changes, a failing git call -
# is `false`, so a doubt always means the full run.
#
# Environment: EVENT_NAME, BASE_REF, HEAD_SHA, GITHUB_OUTPUT (see .github/workflows/ci.yml).
# Needs a checkout with full history, or the merge base is not found.
set -euo pipefail

emit() {
  echo "docs_only=$1" >> "${GITHUB_OUTPUT:-/dev/stdout}"
  echo "docs_only=$1"
}

if [ "${EVENT_NAME:-}" != "pull_request" ]; then
  echo "Event '${EVENT_NAME:-}' is not a pull request: full run."
  emit false
  exit 0
fi

# The tip of the base branch as it is now, not the one the event recorded: after
# `main` was merged into the PR, the merge base is that tip and the diff shows
# only what the PR itself changes.
if ! git fetch --quiet --no-tags origin "+refs/heads/${BASE_REF}:refs/remotes/origin/${BASE_REF}" \
  || ! files="$(git diff --name-only --no-renames -z "origin/${BASE_REF}...${HEAD_SHA}" | tr '\0' '\n')"; then
  echo "::warning::Could not list the files of this pull request: full run."
  emit false
  exit 0
fi

if [ -z "$files" ]; then
  echo "The pull request changes no files: full run."
  emit false
  exit 0
fi

echo "Files changed by this pull request:"
echo "$files" | sed 's/^/  /'

if echo "$files" | grep -qv '^docs/'; then
  echo "Files outside docs/: full run."
  emit false
else
  echo "Only files under docs/: docs-only run."
  emit true
fi
