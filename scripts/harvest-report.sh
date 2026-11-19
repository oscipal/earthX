#!/usr/bin/env bash
# Reports one harvested source and commits its approval file on a branch of its own (M5-20); the bash twin of
# scripts/harvest-report.ps1. Run it from the repository root while `docker compose up -d` is running:
#
#   scripts/harvest-report.sh govdata             # report, branch harvest/<day>-govdata, commit
#   scripts/harvest-report.sh govdata --classify  # show the classification only, write nothing
#
# It never pushes: push the branch and open the draft PR with your own access (adr/0025 §6.5, P1).
set -euo pipefail

# The report writes into backend/catalog/approvals of this checkout as the user who owns it, never as root: the
# approval file must stay editable without sudo (Otto, 19.11.2026; the service's image runs as root otherwise).
as_owner=(--user "$(id -u):$(id -g)")

fail() {
    echo "FEHLER: $1"
    exit 1
}

source_id="${1:-}"
[[ "$source_id" =~ ^[a-z][a-z0-9-]{1,62}$ ]] || fail "Aufruf: scripts/harvest-report.sh <source_id> [--classify]"

if [[ "${2:-}" == "--classify" ]]; then
    exec docker compose run --build --rm "${as_owner[@]}" harvest-report "$source_id" --classify
fi

[[ -z "$(git status --porcelain)" ]] || fail "Der Checkout ist nicht sauber; erst committen oder aufräumen."
branch="$(git rev-parse --abbrev-ref HEAD)"
[[ "$branch" == "main" ]] || fail "Der Checkout steht auf '$branch', nicht auf main."

day="$(date +%F)"
target="harvest/$day-$source_id"
git switch -c "$target" || fail "Der Branch $target lässt sich nicht anlegen."

if ! docker compose run --build --rm "${as_owner[@]}" harvest-report "$source_id"; then
    git switch main
    git branch -D "$target"
    fail "Der Bericht ist gescheitert; der Branch ist gelöscht."
fi

if [[ -z "$(git status --porcelain -- backend/catalog/approvals)" ]]; then
    git switch main
    git branch -D "$target"
    echo "OK: kein neuer Stapel, keine Freigabedatei; nichts zu committen."
    exit 0
fi

git add -- backend/catalog/approvals
git commit -m "Add the approval file of the harvest of $source_id, $day" || fail "Der Commit ist gescheitert."

echo "OK: Branch $target mit Bericht und Freigabedatei."
echo "Weiter mit deinem Zugang: git push -u origin $target"
echo "Dann den Draft-PR öffnen, die Stichprobe in der .yaml abhaken, decision und decided_on setzen, mergen."
