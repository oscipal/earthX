"""Async tests in this tree run on asyncio, through the plugin `anyio` ships.

`anyio` comes with `httpx` and `starlette`, so this needs no new dependency.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
