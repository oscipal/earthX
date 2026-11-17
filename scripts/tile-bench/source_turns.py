#!/usr/bin/env python3
"""Runs like `materialize` through the gateway against the synthetic source, alone or sharing turns (M5-37 plan §7).

    python scripts/tile-bench/source_turns.py --port 9100 --processes 2 --requests 30 --interval 1.0 \\
        [--shared] [--seconds 30] --out runs.jsonl

Each process opens one gateway and asks ``/page.json`` one request after another, as `materialize` pages a listing.
``--shared`` gives the gateway the Postgres coordinator of M5-37 (`open_source_gateway`); without it the gateway keeps
spacing in its own object, as on `main`, so the same command measures both. With ``--seconds`` a process asks until the
time is up and goes on after a failed request, as instances that each retry for themselves; a host that rests ends the
process, as it ends a run. Before the processes start, ``--shared`` deletes the rows of the synthetic host.

Two seams, the ones the tests replace too: the resolver answers with a public address, and the transport sends the
gateway's request to the source on 127.0.0.1 over plain HTTP. One JSON line per request goes to ``--out``: process,
start, end and outcome. Connection details for Postgres come from the environment (``PGHOST`` and friends), the
backend to measure from ``PYTHONPATH`` (``backend`` of a checkout of `main` or of the branch).
"""

import argparse
import asyncio
import json
import multiprocessing
import sys
import time

import httpx

HOST = "bench-source.example.org"
URL = f"https://{HOST}/page.json"


class ToLocal(httpx.AsyncBaseTransport):
    """Send what the gateway asked of the public address to the synthetic source instead."""

    def __init__(self, port: int) -> None:
        self._port = port
        self._inner = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        request.url = request.url.copy_with(scheme="http", host="127.0.0.1", port=self._port)
        request.extensions.pop("sni_hostname", None)
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


def public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


async def run(number: int, args: argparse.Namespace) -> list[dict]:
    from earthx.gateway import Gateway, GatewayError, HostResting, Policy

    policy = Policy(allowed_hosts=frozenset({HOST}), host_intervals={HOST: args.interval}, user_agent="EarthX-bench/0")
    options = {"transport": ToLocal(args.port), "resolve": public}
    if args.shared:
        from earthx.discovery.source_gateway import open_source_gateway

        opened = open_source_gateway(policy, **options)
    else:
        opened = Gateway(policy, **options)
    records: list[dict] = []
    began = time.monotonic()
    async with opened as gateway:
        while len(records) < args.requests and (not args.seconds or time.monotonic() - began < args.seconds):
            start = time.monotonic()
            outcome = "ok"
            try:
                await gateway.get(URL)
            except HostResting:
                outcome = "rest"
            except GatewayError as error:
                outcome = type(error).__name__
            records.append({"process": number, "start": start, "end": time.monotonic(), "outcome": outcome})
            if outcome == "rest" or (outcome != "ok" and not args.seconds):
                break
    return records


def child(number: int, args: argparse.Namespace, queue: multiprocessing.Queue) -> None:
    queue.put(asyncio.run(run(number, args)))


def reset() -> None:
    import psycopg

    with psycopg.connect(autocommit=True) as conn:
        conn.execute("DELETE FROM public.earthx_source_lease WHERE host = %s", (HOST,))
        conn.execute("DELETE FROM public.earthx_source_host WHERE host = %s", (HOST,))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9100)
    parser.add_argument("--processes", type=int, default=1)
    parser.add_argument("--requests", type=int, default=30)
    parser.add_argument("--interval", type=float, default=0.0)
    parser.add_argument("--seconds", type=float, default=0.0)
    parser.add_argument("--shared", action="store_true")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.shared:
        reset()
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    processes = [context.Process(target=child, args=(n, args, queue)) for n in range(args.processes)]
    for process in processes:
        process.start()
    records = [record for _ in processes for record in queue.get()]
    for process in processes:
        process.join()
    with open(args.out, "a", encoding="utf-8") as out:
        for record in records:
            out.write(json.dumps(record) + "\n")
    print(f"{len(records)} requests by {args.processes} processes", file=sys.stderr)


if __name__ == "__main__":
    main()
