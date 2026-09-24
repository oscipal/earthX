"""Run one read tool from the command line, for local development (plan m7a §5).

    python -m earthx.chatbot --stac-url https://example.org/stac search "sentinel"
    python -m earthx.chatbot collection sentinel-2-l2a
    python -m earthx.chatbot availability sentinel-2-l2a --bbox 0 40 10 50 --datetime 2024-06-01/2024-06-30

The STAC root comes from ``--stac-url`` or ``EARTHX_CHATBOT_STAC_URL``. Its host is
the only one the gateway lets through; the gateway's rules stay as they are, so the
address must be https and publicly routable (plan m7a F5).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

from earthx.chatbot.tools import CatalogTools, call_tool
from earthx.gateway import Gateway, GatewayError, Policy, host_of

STAC_URL_ENV = "EARTHX_CHATBOT_STAC_URL"


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


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.stac_url:
        print(f"no STAC root: pass --stac-url or set {STAC_URL_ENV}", file=sys.stderr)
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
