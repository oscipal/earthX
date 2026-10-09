"""The one refusal `readers` raises about an asset address (adr/0011 §6.4).

`access` and `processing` must not import `gateway`, not even as a type
(architekturplan.md 3.1, `.importlinter`), yet both have to tell a refused
address from any other failure. So `readers` — which may import `gateway` —
raises only this class for an address it will not open: a key, an href it cannot
split, or anything ``check_url`` refuses. It is a :class:`UrlRejected`, so every
caller that already catches ``UrlRejected`` or ``GatewayError`` catches it
unchanged.
"""

from __future__ import annotations

from earthx.gateway import UrlRejected

__all__ = ["AssetRejected"]


class AssetRejected(UrlRejected):
    """This asset address is not opened; the text names the reason, never the address."""
