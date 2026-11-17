#!/usr/bin/env python3
"""A range-serving HTTP/1.1 file server that answers like a distant object store (NM4-26).

    python -I scripts/tile-bench/slow_source.py <cog-dir> [--port 9100] [--rtt-ms 170] [--connect-ms 350] [--mbit 100]
        [--fail-file PATH]

``--rtt-ms`` is added before the first byte of every answer, ``--connect-ms`` once per new connection (TCP and TLS
to a distant host), ``--mbit`` is one link shared by all connections (0: unlimited). Any path is answered from the
file of the same name in ``<cog-dir>``, so ``/<scene>/B04.tif`` is a URL of its own for GDAL but the same bytes.
One JSON line per request goes to ``--log``: connection, method, path, first byte and length of the range, status, and
whether the client broke it off.
While the file ``--fail-file`` exists, every answer is ``503`` after the round trip, as a source in trouble (M5-37).
"""

import argparse
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RANGE = re.compile(r"bytes=(\d+)-(\d*)$")
CHUNK = 256 * 1024


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("--port", type=int, default=9100)
    parser.add_argument("--rtt-ms", type=float, default=0)
    parser.add_argument("--connect-ms", type=float, default=0)
    parser.add_argument("--mbit", type=float, default=0)
    parser.add_argument("--log", default="source.jsonl")
    parser.add_argument("--fail-file", default="")
    args = parser.parse_args()
    log = open(args.log, "a", buffering=1)
    lock = threading.Lock()
    state = {"connections": 0, "link_free": 0.0}

    def take_link(size: int) -> None:
        """Wait until ``size`` bytes have passed the shared link, in the order they asked for it."""
        if not args.mbit:
            return
        with lock:
            begin = max(time.monotonic(), state["link_free"])
            state["link_free"] = begin + size * 8 / (args.mbit * 1e6)
            done = state["link_free"]
        time.sleep(max(0.0, done - time.monotonic()))

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def setup(self) -> None:
            super().setup()
            with lock:
                state["connections"] += 1
                self.connection_id = state["connections"]
            time.sleep(args.connect_ms / 1000)

        def log_message(self, *_: object) -> None:
            pass

        def answer(self, body: bool) -> None:
            began = time.monotonic()
            path = os.path.join(args.root, os.path.basename(self.path.split("?")[0]))
            if args.fail_file and os.path.exists(args.fail_file):
                time.sleep(args.rtt_ms / 1000)
                self.send_response(503)
                self.send_header("Content-Length", "0")
                self.end_headers()
                log.write(json.dumps({"conn": self.connection_id, "method": self.command, "url": self.path,
                                      "status": 503, "t0": began, "t1": time.monotonic()}) + "\n")
                return
            if not os.path.isfile(path):
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                log.write(json.dumps({"conn": self.connection_id, "method": self.command, "url": self.path,
                                      "status": 404, "t0": began, "t1": time.monotonic()}) + "\n")
                return
            size = os.path.getsize(path)
            start, end, status = 0, size - 1, 200
            match = RANGE.match(self.headers.get("Range", ""))
            if match:
                start = int(match.group(1))
                end = min(int(match.group(2)) if match.group(2) else size - 1, size - 1)
                status = 206
            time.sleep(args.rtt_ms / 1000)
            length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Type", "image/tiff")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            sent, aborted = 0, False
            try:
                if body:
                    with open(path, "rb") as source:
                        source.seek(start)
                        while sent < length:
                            data = source.read(min(CHUNK, length - sent))
                            take_link(len(data))
                            self.wfile.write(data)
                            sent += len(data)
            except (BrokenPipeError, ConnectionResetError):
                aborted = True  # the client closed the connection before the body was through (M5-37)
            finally:
                # `t0`/`t1`: when the answer began and ended, for the requests in flight at once (M5-36). A request the
                # client broke off is a request at the source too, and is written with `aborted` (M5-37).
                record = {"conn": self.connection_id, "method": self.command, "url": self.path, "start": start,
                          "range": bool(match), "bytes": sent, "status": status, "aborted": aborted, "t0": began,
                          "t1": time.monotonic()}
                log.write(json.dumps(record) + "\n")
            if aborted:
                self.close_connection = True

        def do_GET(self) -> None:
            self.answer(True)

        def do_HEAD(self) -> None:
            self.answer(False)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()
