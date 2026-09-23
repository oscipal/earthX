# Single image for all four earthx processes (architekturplan.md 3.2, 12.1).
# Each docker-compose service picks its own `command:`; this file sets no
# CMD/ENTRYPOINT on purpose ("ein Image, vier Startbefehle").
#
# python:3.12-slim matches the Python CI and the cloud session run on (M3-03)
# and works there without a system GDAL — the pip wheels for rasterio/rio-tiler
# bundle their own (docs/cloud-umgebung.md §3).
FROM python:3.12-slim

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

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY earthx ./earthx
