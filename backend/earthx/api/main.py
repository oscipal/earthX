"""Process entrypoint for `api` (architekturplan.md 3.2): the outward STAC API.

Collections come from pgstac; items are federated per collection through
``FederatingCoreCrudClient`` (adr/0005, docs/plans/m1-07-stac-api.md). Two things are
hard-set here rather than left to the environment, because both are safety
properties, not preferences:

* **The extension set.** ``ENABLED_EXTENSIONS`` would otherwise let a misconfigured
  ``.env`` re-enable ``filter``/CQL2 (adr/0005 rule VI) or ``sort`` (plan §6, F2) —
  a constructor keyword wins over the environment in ``pydantic-settings``, so
  passing it here is what actually keeps the promise, not a comment asking an
  operator to leave the variable alone.
* **The route prefix**, ``/stac`` — the prototype under ``backend/app`` already
  answers under ``/api`` and ``/`` (plan §9); this API must never shadow it.

``/health`` is added directly on the base app, not through the prefixed STAC router,
so the existing compose healthcheck (``docker-compose.yml``, ``curl .../health``)
keeps working unchanged.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from stac_fastapi.pgstac.app import instantiate_api
from stac_fastapi.pgstac.config import Settings
from stac_fastapi.pgstac.db import close_db_connection, connect_to_db
from stac_fastapi.pgstac.models.extensions import Extensions

from earthx.api.aoi_upload_route import router as aoi_upload_router
from earthx.api.coverage_route import router as coverage_router
from earthx.api.dependencies import build_gateway, build_geocoder, cache_pool
from earthx.api.federating_client import FederatingCoreCrudClient
from earthx.api.geocode_route import router as geocode_router
from earthx.catalog.datasets import REGISTRY
from earthx.logging import RequestIdMiddleware, configure_logging

# adr/0005 rule VI, plan §6 F2: query/fields/pagination describe our own collection
# and paging; filter (CQL2) and sort are the two extensions the federated path cannot
# yet honour, so neither is ever enabled, whatever ENABLED_EXTENSIONS says.
_ENABLED_EXTENSIONS = ["query", "fields", "pagination"]
_PREFIX_PATH = "/stac"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Providing a custom lifespan to `instantiate_api` replaces its default one
    # entirely (its own docstring: "the caller is responsible for managing db
    # connections") — pgstac's own asyncpg pool is opened and closed here too.
    await connect_to_db(app, add_write_connection_pool=False)
    try:
        async with cache_pool() as pool:
            app.state.earthx_cache_pool = pool
            app.state.earthx_gateway = build_gateway(REGISTRY)
            # M3-07a: a second, separate gateway that can reach only the geocoder's
            # host — never a dataset's asset host, and no dataset route can reach it
            # either. None of the three attributes below are set at all when place
            # search is off; the route treats their absence as "not available".
            geocoder = build_geocoder()
            if geocoder is not None:
                geocoder_gateway, geocoder_config = geocoder
                app.state.earthx_geocoder_gateway = geocoder_gateway
                app.state.earthx_geocoder_url = geocoder_config.base_url
                app.state.earthx_geocoder_user_agent = geocoder_config.user_agent
            try:
                yield
            finally:
                if geocoder is not None:
                    await geocoder_gateway.aclose()
    finally:
        await close_db_connection(app)


def _build_app() -> FastAPI:
    # M3-16: this process's own JSON logging, before anything can log a line
    # (K-01/K-02) — the compose command starts it with `--no-access-log`, so
    # `RequestIdMiddleware` below is this process's only access log.
    configure_logging()
    settings = Settings(enabled_extensions=_ENABLED_EXTENSIONS, prefix_path=_PREFIX_PATH)
    # `Extensions()` on its own would build a *second*, default-constructed
    # `Settings()` that never sees `_ENABLED_EXTENSIONS` — passing `settings` here
    # explicitly is what makes the hard-set extension list actually reach the
    # routes `instantiate_api` builds, not just the object this function holds.
    extensions = Extensions(settings=settings)
    api = instantiate_api(client=FederatingCoreCrudClient, settings=settings, extensions=extensions, lifespan=_lifespan)
    app = api.app
    app.add_middleware(RequestIdMiddleware)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "api"}

    # Outside `/stac` on purpose (M2-05b, plan §6.6 F1 a): the answer is not a STAC
    # object, and `/stac` stays the namespace of the standard.
    app.include_router(coverage_router)
    # M3-06a: an uploaded AOI file has nothing to do with STAC either, and needs
    # neither a dataset nor `gateway` — no reason to live on `tiler`.
    app.include_router(aoi_upload_router)
    # M3-07a: place search, also outside `/stac` and also not a dataset route.
    app.include_router(geocode_router)

    return app


app = _build_app()
