"""Talk to the chatbot, or run one read tool, from the command line (plan m7a §5).

    python -m earthx.chatbot --stac-url https://example.org/stac search "sentinel"
    python -m earthx.chatbot collection sentinel-2-l2a
    python -m earthx.chatbot availability sentinel-2-l2a --bbox 0 40 10 50 --datetime 2024-06-01/2024-06-30
    python -m earthx.chatbot chat "Which radar data covers the Alps in 2024?"
    python -m earthx.chatbot chat

The STAC root comes from ``--stac-url`` or ``EARTHX_CHATBOT_STAC_URL``. Its host is
the only one the gateway lets through; the gateway's rules stay as they are, so the
address must be https and publicly routable (plan m7a F5).

``chat`` also needs ``EARTHX_CHATBOT_MODEL`` and ``ANTHROPIC_API_KEY`` in the
environment. Without a question it asks for one line after another until an empty
line; the transcript lives in this process only and is gone when it ends.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

from earthx.chatbot.dialogue import reply
from earthx.chatbot.llm import MESSAGES_URL, AnthropicMessages, ModelError
from earthx.chatbot.tools import CatalogTools, call_tool
from earthx.gateway import Gateway, GatewayError, Policy, host_of

STAC_URL_ENV = "EARTHX_CHATBOT_STAC_URL"
MODEL_ENV = "EARTHX_CHATBOT_MODEL"
API_KEY_ENV = "ANTHROPIC_API_KEY"
# A model answer with several tool rounds takes longer than a STAC page.
MODEL_READ_TIMEOUT_S = 120.0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m earthx.chatbot", description=__doc__.split("\n")[0])
    parser.add_argument("--stac-url", default=os.environ.get(STAC_URL_ENV), help=f"STAC root (or {STAC_URL_ENV})")
    commands = parser.add_subparsers(dest="command", required=True)

    search = commands.add_parser("search", help="search_collections")
    search.add_argument("query", nargs="?", default=None)
    search.add_argument("--bbox", type=float, nargs=4, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    search.add_argument("--datetime")
    search.add_argument("--limit", type=int)

    collection = commands.add_parser("collection", help="get_collection")
    collection.add_argument("collection_id")

    availability = commands.add_parser("availability", help="check_availability")
    availability.add_argument("collection_id")
    availability.add_argument("--bbox", type=float, nargs=4, metavar=("WEST", "SOUTH", "EAST", "NORTH"), required=True)
    availability.add_argument("--datetime", required=True)

    chat = commands.add_parser("chat", help="ask the chatbot; without a question, a dialogue on stdin")
    chat.add_argument("question", nargs="?", default=None)
    return parser


def _call(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    if args.command == "search":
        arguments = {"query": args.query, "bbox": args.bbox, "datetime": args.datetime, "limit": args.limit}
        return "search_collections", {key: value for key, value in arguments.items() if value is not None}
    if args.command == "collection":
        return "get_collection", {"collection_id": args.collection_id}
    return "check_availability", {"collection_id": args.collection_id, "bbox": args.bbox, "datetime": args.datetime}


async def _run(stac_url: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    async with Gateway(Policy(allowed_hosts=frozenset({host_of(stac_url)}))) as gateway:
        return await call_tool(CatalogTools(gateway, stac_url), name, arguments)


async def _chat(stac_url: str, model: str, api_key: str, question: str | None) -> int:
    llm_policy = Policy(allowed_hosts=frozenset({host_of(MESSAGES_URL)}), read_timeout_s=MODEL_READ_TIMEOUT_S)
    async with (
        Gateway(Policy(allowed_hosts=frozenset({host_of(stac_url)}))) as stac_gateway,
        Gateway(llm_policy) as llm_gateway,
    ):
        tools = CatalogTools(stac_gateway, stac_url)
        llm = AnthropicMessages(llm_gateway, api_key=api_key, model=model)
        transcript: list[dict[str, Any]] = []
        while True:
            text = question if question is not None else _ask()
            if not text:
                return 0
            try:
                answer = await reply(llm, tools, [*transcript, {"role": "user", "content": text}])
            except ModelError as error:
                print(f"model error: {error}", file=sys.stderr)
                if question is not None:
                    return 1
                continue
            transcript = answer.transcript
            print(answer.text, flush=True)
            if question is not None:
                return 0


def _ask() -> str:
    try:
        return input("> ").strip()
    except EOFError:
        return ""


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.stac_url:
        print(f"no STAC root: pass --stac-url or set {STAC_URL_ENV}", file=sys.stderr)
        return 2
    if args.command == "chat":
        model, api_key = os.environ.get(MODEL_ENV), os.environ.get(API_KEY_ENV)
        missing = [name for name, value in ((MODEL_ENV, model), (API_KEY_ENV, api_key)) if not value]
        if missing:
            print(f"chat needs {' and '.join(missing)} in the environment", file=sys.stderr)
            return 2
        try:
            return asyncio.run(_chat(args.stac_url, model, api_key, args.question))
        except GatewayError as error:
            print(f"refused: {error}", file=sys.stderr)
            return 2
    try:
        result = asyncio.run(_run(args.stac_url, *_call(args)))
    except GatewayError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    raise SystemExit(main())
