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
# The image's Ubuntu package, by absolute path (M3-03, F1): `python3` in the cloud
# image points at 3.11, and a `python3.12` found on PATH may be another build (a
# `uv python install` puts one in ~/.local/bin, ahead of /usr/bin).
# backend/tests/test_python_version.py checks this against CI and the Dockerfile.
PYTHON=/usr/bin/python3.12
PYTHON_MINOR="${PYTHON##*python}"

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
# Das venv wird nur einmal angelegt, aber `pip install` läuft bei jedem Start:
# ein bestehendes venv kann aus einer Zeit stammen, in der
# backend/requirements.txt weniger Pakete listete (z. B. vor `titiler.core`
# in M2-04), und pip überspringt bereits erfüllte Anforderungen ohnehin
# schnell (M2-13, mehrere Sessions mussten sonst von Hand nachinstallieren).
venv_minor() { "${VENV}/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null; }

# Ein venv mit anderer Version oder ohne pip wird ersetzt, nicht weiterbenutzt:
# sein `bin/python` kann auf einen umgestellten Interpreter zeigen, während die
# Pakete noch unter der alten Version liegen, und ein abgebrochenes Anlegen
# hinterlässt `bin/python` ohne `bin/pip`. `.venv/` enthält nur Installiertes.
# Gelöscht wird nur, wenn der Interpreter für ein neues da ist.
if [ -x "${PYTHON}" ] && [ -d "${VENV}" ] \
  && { [ "$(venv_minor)" != "${PYTHON_MINOR}" ] || [ ! -x "${VENV}/bin/pip" ]; }; then
  log "Python-venv hat nicht Python ${PYTHON_MINOR} oder kein pip, wird neu angelegt (${VENV})"
  rm -rf "${VENV}"
fi

if [ -x "${VENV}/bin/python" ] && [ "$(venv_minor)" = "${PYTHON_MINOR}" ]; then
  log "Python-venv existiert bereits (${VENV})"
elif [ -x "${PYTHON}" ]; then
  log "Python-venv anlegen (${VENV}, ${PYTHON})"
  "${PYTHON}" -m venv "${VENV}" || { warn "Anlegen des venv fehlgeschlagen"; rm -rf "${VENV}"; }
else
  # Kein Ausweichen auf eine andere Version: CI und Image laufen auf derselben.
  warn "${PYTHON} fehlt im Image; kein venv mit Python ${PYTHON_MINOR}"
fi

if [ -x "${VENV}/bin/python" ] && [ "$(venv_minor)" = "${PYTHON_MINOR}" ]; then
  log "Backend-Abhängigkeiten installieren (backend/requirements-dev.txt)"
  "${VENV}/bin/pip" install --upgrade --quiet pip \
    && "${VENV}/bin/pip" install --quiet -r "${REPO_ROOT}/backend/requirements-dev.txt" \
    || warn "pip-Installation fehlgeschlagen"

  # Damit ein nacktes `pytest` in der Sitzung das des venv ist und nicht das
  # gleichnamige Werkzeug des Images ohne Backend-Pakete (M3-03, F4). Claude Code
  # übergibt einem SessionStart-Hook dafür CLAUDE_ENV_FILE; die Zeilen darin gelten
  # für alle folgenden Bash-Befehle der Sitzung.
  if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
    log "venv in den Pfad der Sitzung eintragen"
    {
      printf 'export VIRTUAL_ENV=%q\n' "${VENV}"
      printf 'export PATH=%q:"$PATH"\n' "${VENV}/bin"
    } >> "${CLAUDE_ENV_FILE}" || warn "Schreiben nach CLAUDE_ENV_FILE fehlgeschlagen"
  else
    warn "CLAUDE_ENV_FILE ist nicht gesetzt; in der Sitzung .venv/bin/pytest benutzen"
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
# Local development credentials only — this database never leaves the sandbox and
# holds no real data. Not a secret in the sense of CLAUDE.md. Set once here; the
# migration below and .env.test further down both use these.
PG_HOST=127.0.0.1
PG_PORT=5432
PG_USER=earthx
PG_PASSWORD=earthx
PG_DATABASE=earthx

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

# pgstac-Schema. Die Version steckt im Pin in backend/requirements.txt, nicht hier
# (M1-08 setzt ihn; compose fährt denselben Befehl im Dienst `pgstac-migrate`).
# `migrate` ist idempotent: beim zweiten Lauf passiert nichts.
log "pgstac-Schema migrieren"
if [ -x "${VENV}/bin/pypgstac" ]; then
  PGHOST="${PG_HOST}" PGPORT="${PG_PORT}" PGUSER="${PG_USER}" \
  PGPASSWORD="${PG_PASSWORD}" PGDATABASE="${PG_DATABASE}" \
    "${VENV}/bin/pypgstac" migrate >/dev/null \
    || warn "pypgstac migrate fehlgeschlagen"
else
  warn "pypgstac fehlt im venv (steht in backend/requirements.txt)"
fi

# Read by backend/tests/integration/conftest.py, so that a bare `pytest` finds the
# database in a session the same way CI finds it from the job environment.
cat > "${REPO_ROOT}/.env.test" <<ENVEOF
PGHOST=${PG_HOST}
PGPORT=${PG_PORT}
PGUSER=${PG_USER}
PGPASSWORD=${PG_PASSWORD}
PGDATABASE=${PG_DATABASE}
ENVEOF

# --- Zusammenfassung --------------------------------------------------------
# Der Endzustand wird noch einmal unabhängig von den Schritten oben geprüft.
# Genau hier fehlte die Sichtbarkeit: schlug ein Schritt fehl, stand das nur als
# stderr-Warnung im Protokoll, waehrend der Hook mit Exit 0 endete und die
# Sitzung scheinbar sauber startete. Die Zusammenfassung geht deshalb auf
# stdout, und der Hook endet weiterhin mit Exit 0.

have_venv() {
  [ -x "${VENV}/bin/python" ] && [ "$(venv_minor)" = "${PYTHON_MINOR}" ] \
    && "${VENV}/bin/python" -c 'import psycopg, stac_fastapi.pgstac, titiler.core'
}
have_frontend() { [ -d "${REPO_ROOT}/frontend/node_modules" ]; }
have_postgres() { as_postgres psql -d earthx -tAc 'SELECT 1'; }
have_postgis() {
  as_postgres psql -d earthx -tAc \
    "SELECT 1 FROM pg_extension WHERE extname = 'postgis'" | grep -q 1
}
# Ohne pgstac scheitern die T-C-Tests aus M1-04 (adr/0002 §2), und zwar laut.
have_pgstac() {
  as_postgres psql -d earthx -tAc \
    "SELECT 1 FROM pg_namespace WHERE nspname = 'pgstac'" | grep -q 1
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
report pgstac have_pgstac

if [ -n "${missing}" ]; then
  printf '\nNicht einsatzbereit: %s\n' "${missing}"
  case "${missing}" in
    *PostGIS*)
      printf 'PostGIS installiert das setup-Feld der Cloud-Umgebung per apt,\n'
      printf 'nicht dieser Hook. Protokoll: /var/log/earthx-setup.log\n'
      ;;
  esac
  case "${missing}" in
    *pgstac*)
      printf 'Ohne pgstac schlagen die T-C-Tests fehl (backend/tests/integration).\n'
      printf 'Nachholen: PGHOST=127.0.0.1 PGUSER=earthx PGPASSWORD=earthx \\\n'
      printf '  PGDATABASE=earthx .venv/bin/pypgstac migrate\n'
      ;;
  esac
else
  log "Setup abgeschlossen"
fi

exit 0
