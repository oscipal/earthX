#!/bin/sh
# Runs upgrade.sql in every database that takes connections; stops at the first error.
set -eu
for db in $(psql -U "$POSTGRES_USER" -d postgres -Atc "SELECT datname FROM pg_database WHERE datallowconn ORDER BY datname"); do
  echo "== $db"
  psql -U "$POSTGRES_USER" -d "$db" -q -f /tmp/upgrade.sql
done
