#!/usr/bin/env bash
# EarthX — proposed setup script for the Claude Code cloud environment.
#
# Vorschlag zu M0 Schritt 2. Otto trägt das Skript selbst in den Einstellungen
# der Cloud-Umgebung ein; siehe docs/cloud-umgebung.md für die Messwerte, auf
# denen es beruht, und docs/adr/0002-testaufteilung.md für die Testaufteilung.
#
# Ohne Secrets, ohne Netzzugriff auf EO-Quellen, ohne BIOMASS. Idempotent.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${REPO_ROOT}/.venv"

log() { printf '\n== %s\n' "$*"; }

# --- Python -----------------------------------------------------------------
# No conda in the image, so environment.yml is not usable here. The pip wheels
# of rasterio/rio-tiler ship their own GDAL (3.10.x), which is enough for
# everything CI and a cloud session run.
log "Python environment (${VENV})"
python3 -m venv "${VENV}"
"${VENV}/bin/pip" install --upgrade --quiet pip
"${VENV}/bin/pip" install --quiet -r "${REPO_ROOT}/backend/requirements-dev.txt"

# --- Node -------------------------------------------------------------------
log "Frontend dependencies"
(cd "${REPO_ROOT}/frontend" && npm ci --no-audit --no-fund)

# --- Postgres + PostGIS -----------------------------------------------------
# Postgres 16 is installed but not running; PostGIS has to be added. Both come
# from the Ubuntu archive, which is reachable. Only needed for integration
# tests; comment the block out if a session does not run them.
log "Postgres and PostGIS"
if ! dpkg -s postgresql-16-postgis-3 >/dev/null 2>&1; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postgresql-16-postgis-3
fi
sudo pg_ctlcluster 16 main start || true   # already running is fine
sudo -u postgres psql -qc \
  "DO \$\$ BEGIN
     IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'earthx') THEN
       CREATE ROLE earthx LOGIN PASSWORD 'earthx' SUPERUSER;
     END IF;
   END \$\$;"
sudo -u postgres psql -qtc "SELECT 1 FROM pg_database WHERE datname = 'earthx'" | grep -q 1 \
  || sudo -u postgres createdb -O earthx earthx
sudo -u postgres psql -q -d earthx -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# Local development credentials only — this database never leaves the sandbox
# and holds no real data. Not a secret in the sense of CLAUDE.md.
cat > "${REPO_ROOT}/.env.test" <<'ENVEOF'
PGHOST=127.0.0.1
PGPORT=5432
PGUSER=earthx
PGPASSWORD=earthx
PGDATABASE=earthx
ENVEOF

log "Done. Activate with: source .venv/bin/activate"
