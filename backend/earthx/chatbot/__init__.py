"""Read tools for the catalogue chatbot (architekturplan.md 8.3, plan m7a).

The chatbot has no special rights (projektuebersicht.md, principle 7): it reads the
platform only through the public STAC API, over HTTP and through `gateway`, exactly
as any outside client would. It may import `gateway` and nothing else.

This package holds the three read tools and nothing that talks to a language model
yet (plan m7a §7, F2 option 2). The tools recommend nothing and start no jobs.
"""

from earthx.chatbot.tools import TOOL_SPECS, CatalogTools, UnknownCollection, call_tool
from earthx.chatbot.validation import InvalidArgument

__all__ = ["TOOL_SPECS", "CatalogTools", "InvalidArgument", "UnknownCollection", "call_tool"]
