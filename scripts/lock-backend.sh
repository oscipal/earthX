#!/usr/bin/env bash
# Writes the backend lock files from the requirement files (M4-00b,
# docs/plans/m4-00b-lock-datei.md).
#
#   backend/requirements.txt      -> backend/requirements.lock      (image)
#   backend/requirements-dev.txt  -> backend/requirements-dev.lock  (CI, session)
#
# The .txt files stay the input; the .lock files are what CI, backend/Dockerfile
# and scripts/setup-cloud-session.sh install, with `pip install --require-hashes`.
# Only renewing a lock needs `uv`; installing needs nothing but pip.
#
#   scripts/lock-backend.sh            keep the locked versions, add what the
#                                      .txt files now ask for
#   scripts/lock-backend.sh --upgrade  move everything to the newest versions the
#                                      .txt files allow (a PR of its own)
#
# Any further arguments go to both `uv pip compile` calls.
#
# * --universal: one file for every platform (Otto, F2). Linux x86_64 is what CI,
#   the image and the session run; Linux aarch64 comes along. Packages only some
#   platform needs carry an environment marker and are skipped elsewhere.
# * The dev lock is compiled against the runtime lock as a constraint, so every
#   package the image installs is locked to the same version in CI.
# * --only-binary :all: --no-binary version-parser: wheels only, so that nothing
#   is built from source with build dependencies no hash covers. The one
#   exception is `version-parser`, a dependency of `pypgstac` that is published
#   as an sdist only (version 1.0.1 has no wheel on PyPI). Compiling with the
#   same options makes a new sdist-only package fail here, while renewing, and
#   not later in CI.
#
#   The installers pass these two options on the command line, in this order:
#   pip lets a later `--only-binary :all:` cancel an earlier per-package
#   `--no-binary`. That is also why they are not written into the lock files
#   (`uv --emit-build-options` emits them the other way round).
#   backend/tests/test_backend_lock.py checks every install site for them.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found; install it first (e.g. 'pip install uv')" >&2
  exit 1
fi

compile() { # compile <input> <output> [extra uv arguments...]
  local input="$1" output="$2"
  shift 2
  uv pip compile "${input}" \
    --universal \
    --python-version 3.12 \
    --generate-hashes \
    --only-binary :all: \
    --no-binary version-parser \
    --custom-compile-command scripts/lock-backend.sh \
    --output-file "${output}" \
    "$@"
}

compile backend/requirements.txt backend/requirements.lock "$@"
compile backend/requirements-dev.txt backend/requirements-dev.lock \
  --constraint backend/requirements.lock "$@"
