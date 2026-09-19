#!/usr/bin/env bash
# EarthX — SessionStart hook for Claude Code cloud sessions.
#
# Registered in .claude/settings.json (matcher "startup|resume") per
# https://code.claude.com/docs/en/cloud-environments, "Install dependencies
# with a SessionStart hook". PostGIS itself is installed by the cloud
# environment's own setup field (apt); this script only starts Postgres and
# creates the role/database/extension, plus the venv and frontend deps.
#
# Ohne Secrets, ohne Netzzugriff auf EO-Quellen, ohne BIOMASS. Idempotent und
# meldet Fehler nur, statt die Sitzung damit zu blockieren (deshalb kein
# `set -e`, und das Skript endet immer mit Exit 0).

set -uo pipefail

log() { printf '\n== %s\n' "$*"; }
warn() { printf '\n!! %s\n' "$*" >&2; }

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

if [ -z "${CLAUDE_PROJECT_DIR:-}" ]; then
  warn "CLAUDE_PROJECT_DIR ist nicht gesetzt, breche ab"
  exit 0
fi
REPO_ROOT="${CLAUDE_PROJECT_DIR}"
VENV="${REPO_ROOT}/.venv"

# Running as root in the sandbox is normal; sudo is neither present nor
# needed there. as_postgres/as_root abstract the two cases identically.
if [ "$(id -u)" -eq 0 ]; then
  as_root() { "$@"; }
  as_postgres() { runuser -u postgres -- "$@"; }
else
  as_root() { sudo "$@"; }
  as_postgres() { sudo -u postgres "$@"; }
fi

# --- Python -------------------------------------------------------------
if [ -x "${VENV}/bin/python" ]; then
  log "Python-venv existiert bereits (${VENV})"
else
  log "Python-venv anlegen (${VENV})"
  if python3 -m venv "${VENV}"; then
    "${VENV}/bin/pip" install --upgrade --quiet pip \
      && "${VENV}/bin/pip" install --quiet -r "${REPO_ROOT}/backend/requirements-dev.txt" \
      || warn "pip-Installation fehlgeschlagen"
  else
    warn "Anlegen des venv fehlgeschlagen"
  fi
fi

# --- Node -----------------------------------------------------------------
if [ -d "${REPO_ROOT}/frontend/node_modules" ]; then
  log "Frontend-Abhängigkeiten existieren bereits"
else
  log "Frontend-Abhängigkeiten installieren"
  (cd "${REPO_ROOT}/frontend" && npm ci --no-audit --no-fund) || warn "npm ci fehlgeschlagen"
fi

# --- Postgres + PostGIS -----------------------------------------------------
log "Postgres starten"
as_root service postgresql start || warn "Postgres-Start fehlgeschlagen"

log "Rolle, Datenbank und PostGIS-Extension einrichten"
as_postgres psql -qc \
  "DO \$\$ BEGIN
     IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'earthx') THEN
       CREATE ROLE earthx LOGIN PASSWORD 'earthx' SUPERUSER;
     END IF;
   END \$\$;" || warn "Anlegen der Rolle 'earthx' fehlgeschlagen"

if as_postgres psql -qtc "SELECT 1 FROM pg_database WHERE datname = 'earthx'" | grep -q 1; then
  :
else
  as_postgres createdb -O earthx earthx || warn "Anlegen der Datenbank 'earthx' fehlgeschlagen"
fi

as_postgres psql -q -d earthx -c "CREATE EXTENSION IF NOT EXISTS postgis;" \
  || warn "Anlegen der PostGIS-Extension fehlgeschlagen (Paket installiert?)"

# Local development credentials only — this database never leaves the sandbox
# and holds no real data. Not a secret in the sense of CLAUDE.md.
cat > "${REPO_ROOT}/.env.test" <<'ENVEOF'
PGHOST=127.0.0.1
PGPORT=5432
PGUSER=earthx
PGPASSWORD=earthx
PGDATABASE=earthx
ENVEOF

# --- Zusammenfassung --------------------------------------------------------
# Der Endzustand wird noch einmal unabhängig von den Schritten oben geprüft.
# Genau hier fehlte die Sichtbarkeit: schlug ein Schritt fehl, stand das nur als
# stderr-Warnung im Protokoll, waehrend der Hook mit Exit 0 endete und die
# Sitzung scheinbar sauber startete. Die Zusammenfassung geht deshalb auf
# stdout, und der Hook endet weiterhin mit Exit 0.

have_venv() { [ -x "${VENV}/bin/python" ] && "${VENV}/bin/python" -c ''; }
have_frontend() { [ -d "${REPO_ROOT}/frontend/node_modules" ]; }
have_postgres() { as_postgres psql -d earthx -tAc 'SELECT 1'; }
have_postgis() {
  as_postgres psql -d earthx -tAc \
    "SELECT 1 FROM pg_extension WHERE extname = 'postgis'" | grep -q 1
}

missing=""
report() { # report <Label> <Prüffunktion>
  if "$2" >/dev/null 2>&1; then
    printf '  %-9s ok\n' "$1"
  else
    printf '  %-9s FEHLT\n' "$1"
    missing="${missing}${missing:+, }$1"
  fi
}

log "Zusammenfassung"
report venv have_venv
report Frontend have_frontend
report Postgres have_postgres
report PostGIS have_postgis

if [ -n "${missing}" ]; then
  printf '\nNicht einsatzbereit: %s\n' "${missing}"
  case "${missing}" in
    *PostGIS*)
      printf 'PostGIS installiert das setup-Feld der Cloud-Umgebung per apt,\n'
      printf 'nicht dieser Hook. Protokoll: /var/log/earthx-setup.log\n'
      ;;
  esac
else
  log "Setup abgeschlossen"
fi

exit 0
