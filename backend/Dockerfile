# One image for all four earthx processes (architekturplan.md 3.2, 12.1), plus
# the local runner as a second stage on top of it (adr/0016 F1).
#
# Stage `app` sets no CMD/ENTRYPOINT on purpose ("ein Image, vier Startbefehle"):
# each docker-compose service picks its own `command:`, and docker-compose.yml
# builds `target: app`. Stage `runner` adds only the entrypoint and a non-root
# user; the last stage is what a plain `docker build` produces, so every build
# for the services names its target.
#
# python:3.12-slim matches the Python that CI and the cloud session run on
# (M3-03); as there, the pip wheels for rasterio/rio-tiler bring their own GDAL
# (docs/cloud-umgebung.md §3). The digest is the multi-arch index, so an ARM
# machine builds natively (adr/0016 F9, F11); it is renewed in a PR of its own,
# like the lock file.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS app

WORKDIR /app

# Two system packages, and each for one stated reason:
#
# * `curl` only for the compose healthchecks (docker-compose.yml); nothing in
#   the application itself uses it.
# * `libexpat1` because the bundled GDAL is not as self-contained as the note
#   above suggests. A manylinux wheel bundles its dependencies *except* the
#   libraries on the manylinux whitelist, which the system is expected to
#   provide — and `libgdal…so` in the rasterio wheel declares exactly one of
#   them that a slim Debian does not carry: `NEEDED libexpat.so.1` (every other
#   entry is either bundled with a hash in its name or part of the base
#   runtime). `python:3.11-slim`, the base until M3-03, built CPython with its
#   own expat and installed no shared one, so the library was simply absent.
#   Naming the package here means no base image has to happen to carry it.
#
# Until M2-04 no process in this image imported rasterio — `tiler` was a stub —
# so the gap never showed. It is a property of the image, not of the new
# entrypoint: any service that reads a COG would have hit it.
RUN apt-get update \
    && apt-get install --no-install-recommends -y curl libexpat1 \
    && rm -rf /var/lib/apt/lists/*

# The runtime lock file, hash-checked (M4-00b): the same versions CI tests, not
# whatever is newest on the day of the build. scripts/lock-backend.sh writes it
# from requirements.txt and explains the options and their order.
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes \
      --only-binary :all: --no-binary version-parser -r requirements.lock

# Second guard behind `botocore` alone (adr/0015 §5, F3): no AWS library in this
# image may ask the instance metadata service for credentials. The object store
# client gets its keys only from S3_* (earthx/objectstore/config.py).
ENV AWS_EC2_METADATA_DISABLED=true

COPY earthx ./earthx

# The local runner (adr/0016 F1, F10): the same code and the same locked
# dependencies as the services, run as an unprivileged user. EARTHX_COMMIT ends
# up in `runner_version` (earthx.runner.output).
FROM app AS runner
ARG EARTHX_COMMIT=unknown
ENV EARTHX_COMMIT=${EARTHX_COMMIT}
USER 10001:10001
ENTRYPOINT ["python", "-m", "earthx.runner"]
