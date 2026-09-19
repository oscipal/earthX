# Single image for all four earthx processes (architekturplan.md 3.2, 12.1).
# Each docker-compose service picks its own `command:`; this file sets no
# CMD/ENTRYPOINT on purpose ("ein Image, vier Startbefehle").
#
# python:3.11-slim matches environment.yml's pinned Python 3.11 and what
# already works in CI and the cloud session without a system GDAL — the pip
# wheels for rasterio/rio-tiler bundle their own (docs/cloud-umgebung.md §3).
FROM python:3.11-slim

WORKDIR /app

# curl only for the compose healthchecks (docker-compose.yml); nothing in the
# application itself uses it.
RUN apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY earthx ./earthx
COPY app ./app
