"""Order intake: from an order to the recipe a worker runs (adr/0014 §4.1, M4-07b).

`api` is the one place that sees items, the registry and the network at once, so it
is where an *order* — datasets, items, asset keys, AOI, steps, output, no address —
becomes a :class:`~earthx.processing.recipe.Recipe`. The routes that call this
(M4-08b, M4-14) come later; nothing here is a route.

This first part is what both the tile routes and the intake need of an item source:
one answer to "the item could not be had", as an :class:`OrderRefused` that carries
the status a caller turns into its own answer.
"""

from __future__ import annotations

from typing import Any

from earthx.adapters import InvalidQuery, UnknownCollection, UnsupportedSource
from earthx.api.item_source import ItemSource, MaterializedCatalogUnavailable, MaterializedItemNotFound
from earthx.gateway import GatewayError, UpstreamError, UpstreamTimeout

__all__ = ["OrderRefused", "fetch_item", "malformed_item_detail"]


class OrderRefused(Exception):
    """An order, or an item it names, is turned away.

    ``detail`` is English, short and redacted: it names datasets, items and fields,
    never an AOI, an address or a hash (adr/0014 §4.7). The caller turns
    ``status_code`` and ``detail`` into its own answer, in one line.
    """

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def malformed_item_detail(item: str) -> str:
    return f"the source did not deliver item {item!r} intact"


async def fetch_item(item_source: ItemSource, dataset: str, item: str, *, not_found: int = 404) -> dict[str, Any]:
    """The item, or the :class:`OrderRefused` its absence or the source's failure maps to.

    The tile routes and the intake turn a ``dataset``/``item`` pair into a STAC item
    through the same ``item_source``, and a source failure means the same thing to
    both. ``not_found`` is the status for a dataset or item that does not exist: the
    tile routes name them in the path and answer ``404``, an order names them in the
    body and answers ``422``.

    An item whose ``id`` is missing or is not the one asked for is the source's
    mistake, the same ``502`` either way (Otto's review of M4-01a): the asset that
    gets opened is named after the item's own id, and a tile must not show another
    scene under the name it asked for.
    """
    try:
        fetched = await item_source(dataset, item)
    except UnknownCollection:
        raise OrderRefused(not_found, f"no dataset {dataset!r}") from None
    except MaterializedItemNotFound:
        # The materialized counterpart of the federated `UpstreamError` 404 below —
        # same message, so a caller cannot tell which path answered it.
        raise OrderRefused(not_found, f"no item {item!r} in {dataset!r}") from None
    except MaterializedCatalogUnavailable:
        raise OrderRefused(503, "the catalogue is not available") from None
    except UnsupportedSource as error:
        raise OrderRefused(501, str(error)) from None
    except InvalidQuery as error:
        raise OrderRefused(400, str(error)) from None
    except UpstreamError as error:
        if error.status_code == 404:
            raise OrderRefused(not_found, f"no item {item!r} in {dataset!r}") from None
        # The source answered something we do not pass on. Its text is not repeated:
        # it can carry the query, and the query can carry an AOI (projektplan.md 7).
        raise OrderRefused(502, "the source did not deliver the item") from None
    except UpstreamTimeout:
        raise OrderRefused(504, "the source did not answer in time") from None
    except GatewayError:
        # Unreachable, too large, too many redirects: the source's side of the line.
        # Broad on purpose — a gateway error that has no branch of its own is still an
        # answer about the source, and a 500 would call it our mistake.
        raise OrderRefused(502, "the item could not be fetched") from None
    if fetched.get("id") != item:
        raise OrderRefused(502, malformed_item_detail(item))
    return fetched
