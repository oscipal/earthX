"""Process entrypoint for `tiler` (architekturplan.md 3.2).

M1 stub: starts, reports healthy, does nothing. Real tiling logic lands on
this module from M2 (architekturplan.md 3.1: "Tiles, Quicklooks, Statistik").
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="earthx-tiler")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "tiler"}
