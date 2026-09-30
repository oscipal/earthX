"""Read tools for the catalogue chatbot (architekturplan.md 8.3, plan m7a).

The chatbot has no special rights (projektuebersicht.md, principle 7): it reads the
platform only through the public STAC API, over HTTP and through `gateway`, exactly
as any outside client would. It may import `gateway` and nothing else.

It holds the three read tools, a narrow client for the Anthropic Messages API and
the tool loop of one dialogue turn (plan m7a §4, F2 option 1 from 30.09.2026). The
chatbot recommends; no tool starts a job.
"""

from earthx.chatbot.dialogue import Reply, reply
from earthx.chatbot.llm import AnthropicMessages, ChatModel, ModelError
from earthx.chatbot.tools import TOOL_SPECS, CatalogTools, UnknownCollection, call_tool
from earthx.chatbot.validation import InvalidArgument

__all__ = [
    "TOOL_SPECS",
    "AnthropicMessages",
    "CatalogTools",
    "ChatModel",
    "InvalidArgument",
    "ModelError",
    "Reply",
    "UnknownCollection",
    "call_tool",
    "reply",
]
