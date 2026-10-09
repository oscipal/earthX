"""``POST /geocode``: resolve a place name to an outline and a bounding box (M3-07a).

Serves the place-search AOI path (`prototyp-inventar.md` F2,
`docs/plans/m3-07a-ortssuche-backend.md`). Talks only to the geocoder's own gateway
(`api.dependencies.build_geocoder`, built from ``EARTHX_GEOCODER_URL``) — never the
registry's, so no dataset route can reach the geocoder and this route can never
reach a dataset source. Cache and rate slot are the small ``psycopg`` pool `api`
already opens for the search cache (`api.dependencies.cache_pool`).

**Never in a log line:** the search text or a result's name — only counts and
outcomes. `earthx.adapters.nominatim` raises typed exceptions instead of logging
anything itself, so the text never has to pass through a logger to get here.
"""

from __future__ import annotations

import logging
import math
import time

import psycopg
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from earthx.adapters.nominatim import InvalidQuery, RateLimited, UpstreamShapeError, geocode
from earthx.catalog.geocode_cache import PostgresGeocodeCache, PostgresRateSlot
from earthx.gateway import GatewayError, UpstreamTimeout

LOGGER = logging.getLogger("earthx.api.geocode")

router = APIRouter()

# Postgres itself did not answer — no slot could be reserved either way, so the
# request never reaches the source (plan §9). Not the rate slot's own retry-after
# values (2s wait budget, 30s after a `429`): this is "try again shortly", not a
# promise about when the shared pointer will next be free.
_DB_UNAVAILABLE_RETRY_AFTER_S = 5


class GeocodeRequest(BaseModel):
    q: str


@router.post("/geocode")
async def search_place(request: Request, body: GeocodeRequest) -> dict:
    gateway = getattr(request.app.state, "earthx_geocoder_gateway", None)
    if gateway is None:
        raise HTTPException(status_code=503, detail="place search is not available")
    pool = getattr(request.app.state, "earthx_cache_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="place search is not available")
    base_url = request.app.state.earthx_geocoder_url
    user_agent = request.app.state.earthx_geocoder_user_agent

    started = time.monotonic()
    try:
        async with pool.connection() as conn:
            response = await geocode(
                body.q,
                gateway=gateway,
                base_url=base_url,
                user_agent=user_agent,
                cache=PostgresGeocodeCache(conn),
                rate_slot=PostgresRateSlot(conn),
            )
    except InvalidQuery as error:
        LOGGER.info("geocode rejected", extra={"reason": "invalid_query"})
        raise HTTPException(status_code=422, detail=str(error)) from None
    except RateLimited as error:
        LOGGER.info(
            "geocode rate limited",
            extra={"retry_after_s": error.retry_after_s, "duration_s": time.monotonic() - started},
        )
        raise HTTPException(
            status_code=503,
            detail="place search is rate-limited, try again shortly",
            headers={"Retry-After": str(math.ceil(error.retry_after_s))},
        ) from None
    except psycopg.Error:
        # The rate slot could not be reserved (E5 does not apply here, unlike the
        # cache: a caller that cannot reserve a slot must not send either, plan §9).
        LOGGER.warning("geocode rate slot unavailable", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="place search is not available",
            headers={"Retry-After": str(_DB_UNAVAILABLE_RETRY_AFTER_S)},
        ) from None
    except UpstreamTimeout:
        LOGGER.warning("geocode upstream timed out", extra={"duration_s": time.monotonic() - started})
        raise HTTPException(status_code=504, detail="the source did not answer in time") from None
    except GatewayError:
        # Neither the status nor the source's own body travels on, same as
        # `coverage_route.py` — a `429` never reaches here, `geocode` turns it into
        # `RateLimited` above.
        LOGGER.warning("geocode upstream failed", extra={"duration_s": time.monotonic() - started})
        raise HTTPException(status_code=502, detail="the source did not deliver an answer") from None
    except UpstreamShapeError:
        LOGGER.warning("geocode answer could not be read", extra={"duration_s": time.monotonic() - started})
        raise HTTPException(status_code=502, detail="the source answered something place search could not read") from None

    LOGGER.info(
        "geocode answered",
        extra={
            "result_count": len(response.results),
            "from_cache": response.from_cache,
            "duration_s": time.monotonic() - started,
        },
    )
    return response.to_payload()


__all__ = ["router", "search_place"]
