"""No ``MemoryFile`` over bytes outside a ``with`` (M3-22, Otto F3).

rasterio's ``MemoryFile(bytes)`` lays its ``/vsimem/`` file over the bytes
object without copying or owning it (``VSIFileFromMemBuffer`` with
``bTakeOwnership=0``, rasterio 1.5.1). Once the ``MemoryFile`` is collected
while a dataset opened from it is still in use, that dataset reads freed
memory: "ZIPDecode", "ZSTDDecode: Unknown frame descriptor", "TIFF directory
is missing required ImageLength field" — every "corrupt download" M3-18 saw
was this, in the tests' own read path (plan m3-22 §3). Holding the call
directly in a ``with`` keeps the ``MemoryFile`` alive exactly as long as its
datasets. ``MemoryFile()`` without bytes is exempt: GDAL owns that buffer.

Checks production and test code alike.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
CHECKED_TREES = ("earthx", "tests", "tests_live")


def _over_bytes(call: ast.Call) -> bool:
    func = call.func
    name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
    return name == "MemoryFile" and bool(call.args or any(kw.arg == "file_or_bytes" for kw in call.keywords))


def violations(source: str) -> list[int]:
    """Line numbers of every ``MemoryFile(<bytes>)`` that is not itself a ``with`` item."""
    tree = ast.parse(source)
    with_items = {
        id(item.context_expr)
        for node in ast.walk(tree)
        if isinstance(node, (ast.With, ast.AsyncWith))
        for item in node.items
    }
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _over_bytes(node) and id(node) not in with_items
    )


def test_no_memoryfile_over_bytes_outside_a_with() -> None:
    found = [
        f"{path.relative_to(BACKEND)}:{line}"
        for tree in CHECKED_TREES
        for path in sorted((BACKEND / tree).rglob("*.py"))
        for line in violations(path.read_text(encoding="utf-8"))
    ]
    assert not found, "MemoryFile(<bytes>) must sit directly in a `with` (M3-22): " + ", ".join(found)


@pytest.mark.parametrize(
    "source",
    [
        # The helper that broke the CI of #86, before 5cf8a6d.
        "def f(member):\n    memfile = MemoryFile(member)\n    return memfile.open()\n",
        # Its second call site: nothing holds the MemoryFile at all.
        "with MemoryFile(naive_bytes).open() as naive:\n    pass\n",
        "with rasterio.io.MemoryFile(file_or_bytes=data).open() as ds:\n    pass\n",
        "datasets = [MemoryFile(b).open() for b in blobs]\n",
    ],
)
def test_the_patterns_behind_m3_22_are_caught(source: str) -> None:
    assert violations(source)


@pytest.mark.parametrize(
    "source",
    [
        "with MemoryFile(member) as memfile, memfile.open() as dataset:\n    pass\n",
        "with rasterio.io.MemoryFile(data) as mf:\n    pass\n",
        "async def f():\n    async with MemoryFile(data) as mf:\n        pass\n",
        # Empty: GDAL owns the buffer, nothing can be freed underneath it.
        "mem = MemoryFile()\n",
    ],
)
def test_safe_patterns_pass(source: str) -> None:
    assert not violations(source)
