"""``GET /catalogue/categories`` and ``GET /catalogue/regions``: what the filters of the Data catalogue offer (M5-40, H3,
H4).

Both answer from files of the image, read once per process: the categories in the order of the groups from
``backend/catalog/categories.yaml``, the regions from ``backend/catalog/regions.json`` without their outlines. Outside
``/stac`` like ``/geocode``: neither is a STAC object. No request reads the database or reaches a source.
"""

from __future__ import annotations

from functools import cache

from fastapi import APIRouter, Response

from earthx.catalog.categories import load_categories
from earthx.catalog.listed import load_regions

router = APIRouter()

#: The files change only with a new image; a browser may keep the answer for an hour.
_CACHE_CONTROL = "public, max-age=3600"


@cache
def _categories() -> dict[str, object]:
    categories = load_categories()
    return {"categories": [{"id": c, "title": categories.titles[c]} for c in categories.ids]}


@cache
def _regions() -> dict[str, object]:
    """States by name; after each state with subdivisions, its subdivisions by name, each naming its state."""
    regions = load_regions()
    states = sorted((r for r in regions if r.level == "state"), key=lambda r: (r.name.casefold(), r.code))
    by_state: dict[str, list] = {}
    for region in regions:
        if region.level == "subdivision":
            by_state.setdefault(region.code.split("-", 1)[0], []).append(region)
    listed: list[dict[str, object]] = []
    for state in states:
        listed.append({"code": state.code, "name": state.name, "level": "state"})
        for sub in sorted(by_state.get(state.code, []), key=lambda r: (r.name.casefold(), r.code)):
            listed.append({"code": sub.code, "name": sub.name, "level": "subdivision", "state": state.code})
    return {"regions": listed}


@router.get("/catalogue/categories")
async def catalogue_categories(response: Response) -> dict[str, object]:
    """The categories of the Data catalogue, in the order of its groups, ``other`` last."""
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return _categories()


@router.get("/catalogue/regions")
async def catalogue_regions(response: Response) -> dict[str, object]:
    """The regions a listed entry can be filtered by: states, and the subdivisions of DE, AT, CH and LI after theirs."""
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return _regions()
