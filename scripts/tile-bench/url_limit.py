#!/usr/bin/env python3
"""The longest request target uvicorn takes (NM4-04 §7.7), for ``httptools`` and ``h11``.

    python scripts/tile-bench/url_limit.py

Starts uvicorn with an empty ASGI app (this module's ``app``) once per HTTP implementation, sends one GET per length
over a raw socket and halves the step between the longest target answered with ``200`` and the shortest that is not.
``--http auto`` takes ``httptools`` when it is installed, as in the image.
"""

import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


async def app(scope, receive, send) -> None:
    if scope["type"] != "http":
        return
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
    await send({"type": "http.response.body", "body": b"ok"})


def answered(port: int, size: int) -> bool:
    target = "/x?" + "a" * (size - 3)
    request = f"GET {target} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode()
    with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
        connection.sendall(request)
        try:
            line = connection.recv(200).split(b"\r\n")[0]
        except OSError:
            return False
    return b" 200 " in line


def largest(port: int, low: int = 1000, high: int = 200_000) -> int | None:
    if answered(port, high):
        return None
    while high - low > 1:
        middle = (low + high) // 2
        low, high = (middle, high) if answered(port, middle) else (low, middle)
    return low


def main() -> None:
    for port, implementation in ((8713, "auto"), (8714, "h11")):
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "url_limit:app", "--port", str(port), "--http", implementation,
             "--no-access-log", "--log-level", "warning"],
            cwd=HERE,
        )  # fmt: skip
        try:
            time.sleep(2)
            found = largest(port)
            print(f"--http {implementation}: " + ("no limit up to 200000 bytes" if found is None else f"largest target {found} bytes"))
        finally:
            server.terminate()
            server.wait()


if __name__ == "__main__":
    main()
