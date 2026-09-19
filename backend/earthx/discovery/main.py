"""Process entrypoint for `harvester` (architekturplan.md 3.2).

M1 stub: starts, reports healthy, does nothing. Real harvesting logic lands
on this module from M5 (architekturplan.md 3.1: "Harvester, Normalisierung,
Verifikation, Review").
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="earthx-harvester")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "harvester"}
