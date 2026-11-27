# Postgres of EarthX: PostGIS plus pgvector (M5-43; adr/0026 §14 points 4 and 5).
# One image for docker-compose.yml and CI. postgis/postgis:16-3.4 is no longer
# built (last push 14.10.2024); 16-3.7 runs on Debian trixie with PGDG listed.

# pgvector is built from its GitHub tag, like the setup of the cloud environment,
# so all three places run the same version (M5-43 F1 = 3). Raising it is a change
# of both lines on purpose; the build stops if the tag no longer names the commit.
ARG PGVECTOR_TAG=v0.8.7
ARG PGVECTOR_COMMIT=f37c13f68b57d2c3472b2214fbcff699d6d34876

FROM postgis/postgis:16-3.7 AS build
ARG PGVECTOR_TAG
ARG PGVECTOR_COMMIT

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
         build-essential git "postgresql-server-dev-$PG_MAJOR" \
    && rm -rf /var/lib/apt/lists/*

# OPTFLAGS="" leaves out -march=native, so the image runs on any x86-64 host.
RUN git clone --quiet --depth 1 --branch "$PGVECTOR_TAG" https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && test "$(git -C /tmp/pgvector rev-parse HEAD)" = "$PGVECTOR_COMMIT" \
    && make -C /tmp/pgvector OPTFLAGS="" \
    && make -C /tmp/pgvector install DESTDIR=/out \
    && rm -rf /out/usr/include

FROM postgis/postgis:16-3.7
COPY --from=build /out/usr/ /usr/

# 0.8.4 is the floor: its fixes to HNSW vacuuming matter for a catalogue the
# harvester keeps writing to and deleting from (plans/m5/m5-41-pgvector.md §3.1).
RUN version="$(sed -n "s/^default_version = '\(.*\)'$/\1/p" \
         "/usr/share/postgresql/$PG_MAJOR/extension/vector.control")" \
    && echo "pgvector $version" \
    && dpkg --compare-versions "$version" ge 0.8.4
