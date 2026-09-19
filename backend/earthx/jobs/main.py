"""Process entrypoint for `worker` (architekturplan.md 3.2).

M1 stub: starts, reports healthy, does nothing. Real job execution lands on
this module from M4 (architekturplan.md 3.1: "Queue, Worker, Fortschritt,
Ergebnisse").
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="earthx-worker")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "worker"}
