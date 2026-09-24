"""Process entrypoint for `harvester` (architekturplan.md 3.2).

M1 stub: starts, reports healthy, does nothing. Real harvesting logic lands
on this module from M5 (architekturplan.md 3.1: "Harvester, Normalisierung,
Verifikation, Review").
"""

from __future__ import annotations

from fastapi import FastAPI

from earthx.logging import RequestIdMiddleware, configure_logging

# M3-16: this process's own JSON logging, before anything can log a line
# (K-01/K-02) — the compose command starts it with `--no-access-log`, so
# `RequestIdMiddleware` below is this process's only access log.
configure_logging()

app = FastAPI(title="earthx-harvester")
app.add_middleware(RequestIdMiddleware)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "harvester"}
