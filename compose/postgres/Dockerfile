# Postgres of EarthX: PostGIS plus pgvector (M5-43; adr/0026 §14 points 4 and 5).
# One image for docker-compose.yml and CI. postgis/postgis:16-3.4 is no longer
# built (last push 14.10.2024); 16-3.7 runs on Debian trixie with PGDG listed.
FROM postgis/postgis:16-3.7

# pgvector from PGDG at a fixed package version (G4 = 1). PGDG lists only its
# newest build, so once this version is replaced the install fails: raise it here
# on purpose. The policy line in the build log shows what PGDG offers.
ARG PGVECTOR_VERSION=0.8.6-1.pgdg13+2

RUN apt-get update \
    && apt-cache policy "postgresql-$PG_MAJOR-pgvector" \
    && apt-get install -y --no-install-recommends \
         "postgresql-$PG_MAJOR-pgvector=$PGVECTOR_VERSION" \
    && rm -rf /var/lib/apt/lists/*

# 0.8.4 is the floor: its fixes to HNSW vacuuming matter for a catalogue the
# harvester keeps writing to and deleting from (plans/m5/m5-41-pgvector.md §3.1).
RUN version="$(sed -n "s/^default_version = '\(.*\)'$/\1/p" \
         "/usr/share/postgresql/$PG_MAJOR/extension/vector.control")" \
    && echo "pgvector $version" \
    && dpkg --compare-versions "$version" ge 0.8.4
