"""The image carries the system libraries the wheels expect from it.

`backend/Dockerfile` builds one image for all four processes
(architekturplan.md 3.2, 12.1) on `python:3.11-slim`, and the note there says the
pip wheels bring their own GDAL. That is true of GDAL and false of everything on
the **manylinux whitelist**: a manylinux wheel bundles its dependencies *except*
those, which the system is expected to provide. `libexpat.so.1` is one of them,
a slim Debian does not carry it, and until M2-04 nothing in the image imported
rasterio — so the gap first showed as a four-minute red `compose-topology` with
`ImportError: libexpat.so.1` in the tiler's log.

This test asks the installed wheel itself what it still needs from the system and
checks the Dockerfile against the answer. It is deliberately derived rather than
listed: the next bump of rasterio may add another whitelisted library, and then
this fails in a second instead of in a container.

The base runtime below is what every Debian image has by virtue of running
anything at all. Everything else the loader wants has to be installed by name.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO / "backend" / "Dockerfile"

# In a Debian base image these come with libc6, libgcc-s1 and libstdc++6, which
# nothing can run without. They are not a matter of the Dockerfile.
BASE_RUNTIME = frozenset(
    {
        "ld-linux-x86-64.so.2",
        "libc.so.6",
        "libdl.so.2",
        "libgcc_s.so.1",
        "libm.so.6",
        "libpthread.so.0",
        "librt.so.1",
        "libstdc++.so.6",
        "libutil.so.1",
        # zlib1g: Priority "required" in Debian, and CPython itself links it.
        "libz.so.1",
    }
)

# Shared library -> the Debian package that provides it. A library that turns up
# without an entry here fails the test rather than being skipped: an unknown name
# is exactly the case this file exists for.
DEBIAN_PACKAGE = {"libexpat.so.1": "libexpat1"}


def dynamic_needed(path: Path) -> set[str]:
    """The ``DT_NEEDED`` entries of a 64-bit little-endian ELF file.

    Read here rather than through ``objdump``/``readelf``, so the test needs no
    binutils in the image that happens to run it.
    """
    data = path.read_bytes()
    if data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
        raise ValueError(f"{path.name} is not a 64-bit little-endian ELF file")

    phoff, phentsize, phnum = (
        struct.unpack_from("<Q", data, 0x20)[0],
        struct.unpack_from("<H", data, 0x36)[0],
        struct.unpack_from("<H", data, 0x38)[0],
    )
    loads: list[tuple[int, int, int]] = []  # vaddr, filesz, offset
    dynamic: tuple[int, int] | None = None  # offset, filesz
    for index in range(phnum):
        base = phoff + index * phentsize
        p_type = struct.unpack_from("<I", data, base)[0]
        p_offset, p_vaddr = struct.unpack_from("<QQ", data, base + 8)
        p_filesz = struct.unpack_from("<Q", data, base + 32)[0]
        if p_type == 1:  # PT_LOAD
            loads.append((p_vaddr, p_filesz, p_offset))
        elif p_type == 2:  # PT_DYNAMIC
            dynamic = (p_offset, p_filesz)
    if dynamic is None:
        return set()

    def file_offset(vaddr: int) -> int:
        for p_vaddr, p_filesz, p_offset in loads:
            if p_vaddr <= vaddr < p_vaddr + p_filesz:
                return p_offset + (vaddr - p_vaddr)
        raise ValueError(f"address {vaddr:#x} lies in no loadable segment of {path.name}")

    offset, size = dynamic
    entries = [
        struct.unpack_from("<QQ", data, offset + step) for step in range(0, size, 16)
    ]
    strtab = next((file_offset(value) for tag, value in entries if tag == 5), None)  # DT_STRTAB
    if strtab is None:
        return set()
    names = set()
    for tag, value in entries:
        if tag == 0:  # DT_NULL ends the table
            break
        if tag == 1:  # DT_NEEDED
            end = data.index(b"\0", strtab + value)
            names.add(data[strtab + value : end].decode("ascii"))
    return names


def bundled_libraries() -> tuple[list[Path], set[str]]:
    """The libraries the rasterio wheel ships, and the names they answer to.

    `auditwheel` renames each bundled library with a hash (``libgdal-c8c9c467.so…``),
    which is what makes "bundled" and "expected from the system" tellable apart at
    all.
    """
    import rasterio

    directory = Path(rasterio.__file__).resolve().parent.parent / "rasterio.libs"
    if not directory.is_dir():
        pytest.skip("rasterio is not installed as a manylinux wheel (no rasterio.libs)")
    files = sorted(directory.glob("*.so*"))
    return files, {path.name for path in files}


def test_the_wheel_really_does_bundle_its_gdal() -> None:
    """Otherwise the check below would pass by having nothing to find."""
    files, _ = bundled_libraries()
    assert [path for path in files if path.name.startswith("libgdal")]


def installed_packages() -> str:
    """The Dockerfile without its comments.

    Without this the check passes on the paragraph that *explains* the package —
    which is exactly how it first passed while the image installed nothing.
    """
    lines = DOCKERFILE.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.lstrip().startswith("#"))


def test_the_comments_of_the_dockerfile_do_not_count_as_an_installation() -> None:
    """The counter-check for the line above, because it is easy to get wrong."""
    assert "manylinux" not in installed_packages()


def test_the_dockerfile_installs_every_system_library_the_wheel_still_expects() -> None:
    files, bundled = bundled_libraries()
    dockerfile = installed_packages()

    needed: set[str] = set()
    for path in files:
        needed |= dynamic_needed(path)
    from_the_system = sorted(needed - bundled - BASE_RUNTIME)

    # The one that bit us is expected to still be in the list — if a future wheel
    # stops needing it, that is a change worth noticing rather than a free pass.
    assert "libexpat.so.1" in from_the_system

    for library in from_the_system:
        package = DEBIAN_PACKAGE.get(library)
        assert package is not None, (
            f"{library} is expected from the system and this test does not know which "
            "Debian package provides it. Add it to DEBIAN_PACKAGE and to the Dockerfile."
        )
        assert f" {package}" in dockerfile or f"\t{package}" in dockerfile, (
            f"the image does not install {package}, which provides {library}; "
            "a process that reads a COG would fail at `import rasterio`"
        )
