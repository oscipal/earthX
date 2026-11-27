# One image for all four earthx processes (architekturplan.md 3.2, 12.1), plus
# the local runner as a second stage on top of it (adr/0016 F1), and the stage
# `search` with the embedding model for `api` and `catalog-load` (M5-23).
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

# License texts the wheels of the lock file do not carry themselves, though they bundle the library (M5-11, Otto
# 17.11.2026): `libaec`, BSD-2-Clause, in `h5py.libs` and `rasterio.libs`; its clause 2 asks for the text with every
# binary. In both images, the runner's included (`FROM app`). backend/THIRD_PARTY_NOTICES.md names each file.
COPY licenses ./licenses

# The curated registry entries (M5-13, adr/0025 §7.1), each released directory or file by name: never the whole
# `catalog/`, so the candidates of the harvest and the prototype entries of adr/0024 R4 stay out of every image, the
# runner's included. `.dockerignore` keeps both out of the build context as a second guard.
COPY catalog/datasets ./catalog/datasets
COPY catalog/retired.yaml ./catalog/retired.yaml
# The limits per host for the whole platform (M5-36): read with the registry, which checks them against its hosts.
COPY catalog/hosts.yaml ./catalog/hosts.yaml
# What the search text needs besides the entries (M5-22b): country outlines from Natural Earth, the glossary of the
# lexical arm and the terms per capability.
COPY catalog/places.json ./catalog/places.json
COPY catalog/glossary.yaml ./catalog/glossary.yaml
COPY catalog/search_background.yaml ./catalog/search_background.yaml
COPY catalog/capability_terms.yaml ./catalog/capability_terms.yaml
# The categories of the Data catalogue (M5-40 G4): read by every process with the registry, which checks them.
COPY catalog/categories.yaml ./catalog/categories.yaml
# Read by `catalog-load` only (M5-40, adr/0025 §7.1 as of adr/0033): the hand entries of the listed path, the blocklist
# and the outlines the regions of a listed entry are derived from. No other process reads them.
COPY catalog/listed ./catalog/listed
COPY catalog/blocked.yaml ./catalog/blocked.yaml
COPY catalog/regions.json ./catalog/regions.json
COPY catalog/catalog_tags.yaml ./catalog/catalog_tags.yaml
# The seed of the harvest (M5-19, adr/0025 §5.2): read by `discovery`; the registry reads only its hosts.
COPY catalog/sources ./catalog/sources
# The approval of harvested listed entries (M5-20, adr/0033 §6, §8): the licence catalogue and the grants per source,
# the approval files `catalog-load` publishes, and the rules of the report (places, geodata).
COPY catalog/licenses ./catalog/licenses
COPY catalog/approvals ./catalog/approvals
COPY catalog/place_names.yaml ./catalog/place_names.yaml
COPY catalog/geodata.yaml ./catalog/geodata.yaml
COPY catalog/municipalities.json ./catalog/municipalities.json

# The embedding model of the dataset search (M5-23, adr/0026 F2; docs/plans/m5/m5-23-vektorsuche.md §4.2), fetched
# while the image is built, never at run time: one revision of the model repository, each file checked against its
# SHA-256, so a changed file stops the build. Python's own `urllib`, so the stage needs no package. A stage of its own,
# so that only `search` copies from it and the runner never carries the model (F2 a). Raising the model is a change of
# MODEL_REVISION and both hashes together, and of `MODEL_NAME` in earthx/catalog/embedding.py.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS model-files
ARG MODEL_REPOSITORY=ibm-granite/granite-embedding-97m-multilingual-r2
ARG MODEL_REVISION=835ad14087e140460703cf0fae09f97d469d65c2
ARG MODEL_ONNX_SHA256=68e592b160673d30250824c1116bc6ab33f70efb22b97c9e1d7ce1e69c1c9d70
ARG TOKENIZER_SHA256=4f2842d568e2724370aec203652a42ac783c7937f8347a1a2cc7506d71f1582f
RUN python - <<'FETCH'
import hashlib, os, pathlib, urllib.request
base = f"https://huggingface.co/{os.environ['MODEL_REPOSITORY']}/resolve/{os.environ['MODEL_REVISION']}/"
target = pathlib.Path("/models/granite-embedding-97m-multilingual-r2")
target.mkdir(parents=True)
for source, name, expected in (("onnx/model.onnx", "model.onnx", os.environ["MODEL_ONNX_SHA256"]),
                               ("tokenizer.json", "tokenizer.json", os.environ["TOKENIZER_SHA256"])):
    path = target / name
    urllib.request.urlretrieve(base + source, path)
    found = hashlib.sha256(path.read_bytes()).hexdigest()
    if found != expected:
        raise SystemExit(f"{name}: SHA-256 {found}, expected {expected}")
FETCH

# `api` and `catalog-load` (docker-compose.yml): the app with the model. HF_HUB_OFFLINE is a second guard behind
# reading the tokenizer from its file: nothing in this image may ask Hugging Face.
FROM app AS search
COPY --from=model-files /models /app/models
ENV EARTHX_EMBEDDING_MODEL=/app/models/granite-embedding-97m-multilingual-r2 \
    HF_HUB_OFFLINE=1

# The local runner (adr/0016 F1, F10): the same code and the same locked
# dependencies as the services, run as an unprivileged user. EARTHX_COMMIT ends
# up in `runner_version` (earthx.runner.output).
FROM app AS runner
ARG EARTHX_COMMIT=unknown
ENV EARTHX_COMMIT=${EARTHX_COMMIT}
USER 10001:10001
ENTRYPOINT ["python", "-m", "earthx.runner"]
