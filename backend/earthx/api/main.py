"""Process entrypoint for `api` (architekturplan.md 3.2).

M1 stub: only a health endpoint. The STAC-API content lands here with M1-07.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="earthx-api")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "api"}
