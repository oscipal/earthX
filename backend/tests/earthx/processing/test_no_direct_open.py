"""`processing` opens no source itself (adr/0014 §7.3 point 1, plan M4-07a §8, F4).

Every source is opened through `readers`, where an address becomes a path only by
passing ``check_url``. So the syntax tree of every module of `processing` must not
name ``rasterio.open``, ``xarray.open_*``, ``rioxarray.open_rasterio`` or
rio-tiler's ``Reader``/``XarrayReader`` — called, passed on or imported under
another name. The one exception is ``rasterio.open`` in ``workfile.py``, which
opens only a plain file name below the work directory.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[3] / "earthx" / "processing"

FORBIDDEN = frozenset(
    {
        "rasterio.open",
        "rioxarray.open_rasterio",
        "rio_tiler.io.Reader",
        "rio_tiler.io.rasterio.Reader",
        "rio_tiler.io.XarrayReader",
        "rio_tiler.io.xarray.XarrayReader",
    }
)
FORBIDDEN_PREFIXES = ("xarray.open_",)
ALLOWED = {"workfile.py": frozenset({"rasterio.open"})}


def _aliases(tree: ast.AST) -> dict[str, str]:
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    names[alias.asname] = alias.name
                else:
                    root = alias.name.split(".")[0]
                    names[root] = root
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                names[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return names


def _dotted(node: ast.AST) -> list[str] | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return list(reversed(parts))


def openers(source: str) -> set[str]:
    """Every forbidden opener the source names, resolved through its own imports."""
    tree = ast.parse(source)
    aliases = _aliases(tree)
    found = set()
    for name in aliases.values():
        if name in FORBIDDEN or name.startswith(FORBIDDEN_PREFIXES):
            found.add(name)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Attribute, ast.Name)):
            continue
        parts = _dotted(node)
        if not parts or parts[0] not in aliases:
            continue
        qualified = ".".join([aliases[parts[0]], *parts[1:]])
        if qualified in FORBIDDEN or qualified.startswith(FORBIDDEN_PREFIXES):
            found.add(qualified)
    return found


def modules() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


@pytest.mark.parametrize("path", modules(), ids=lambda path: str(path.relative_to(PACKAGE)))
def test_no_module_of_processing_opens_a_source_itself(path: Path) -> None:
    allowed = ALLOWED.get(str(path.relative_to(PACKAGE)), frozenset())
    assert openers(path.read_text(encoding="utf-8")) <= allowed


def test_the_work_file_module_is_where_the_one_open_is() -> None:
    """Otherwise the rule above could pass on a package that never writes a file."""
    assert openers((PACKAGE / "workfile.py").read_text(encoding="utf-8")) == {"rasterio.open"}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import rasterio\nrasterio.open('https://x/a.tif')", "rasterio.open"),
        ("import rasterio as r\nr.open(path)", "rasterio.open"),
        ("from rasterio import open as o\no(path)", "rasterio.open"),
        ("import rasterio\nopener = rasterio.open", "rasterio.open"),
        ("import xarray as xr\nxr.open_zarr(store)", "xarray.open_zarr"),
        ("from xarray import open_dataset", "xarray.open_dataset"),
        ("import rioxarray\nrioxarray.open_rasterio(p)", "rioxarray.open_rasterio"),
        ("from rio_tiler.io import Reader", "rio_tiler.io.Reader"),
        ("from rio_tiler.io.rasterio import Reader as R\nR('a')", "rio_tiler.io.rasterio.Reader"),
        ("import rio_tiler.io\nrio_tiler.io.Reader('a')", "rio_tiler.io.Reader"),
        ("def f():\n    import rasterio\n    return rasterio.open(p)", "rasterio.open"),
    ],
)
def test_the_walk_finds_every_spelling(source: str, expected: str) -> None:
    assert expected in openers(source)


def test_the_walk_leaves_what_is_allowed_alone() -> None:
    source = (
        "import rasterio\nfrom rasterio.vrt import WarpedVRT\nfrom earthx.readers.cog import CogReader\n"
        "with rasterio.Env():\n    WarpedVRT(dataset)\n"
    )
    assert openers(source) == set()
