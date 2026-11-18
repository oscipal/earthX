"""License texts the wheels bundle a library without (M5-11, Otto 17.11.2026).

`h5py` and `rasterio` ship `libaec` inside their wheels but not its BSD-2-Clause text, whose clause 2 asks for it
with every binary. The text lies in `backend/licenses/` and the image copies the directory; these tests keep the
three in step: a bundled `libaec` in the installed packages needs the file, and the file needs the `COPY`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
LIBAEC = BACKEND / "licenses" / "libaec-LICENSE.txt"


def bundled_libaec(package: str) -> list[Path]:
    spec = importlib.util.find_spec(package)
    assert spec is not None and spec.origin is not None, package
    libs = Path(spec.origin).parent.parent / f"{package}.libs"
    return sorted(libs.glob("libaec-*.so*"))


@pytest.mark.parametrize("package", ["h5py", "rasterio"])
def test_a_bundled_libaec_has_its_license_text_beside_the_backend(package: str) -> None:
    if not bundled_libaec(package):
        pytest.skip(f"{package} bundles no libaec in this installation")
    text = LIBAEC.read_text(encoding="utf-8")
    assert text.startswith("Copyright ") and "Luis Kornblueh" in text
    assert "2. Redistributions in binary form must reproduce the above copyright" in text


def test_the_image_carries_the_license_texts() -> None:
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    app = dockerfile.split(" AS app", 1)[1].split("\nFROM ", 1)[0]
    assert "\nCOPY licenses ./licenses\n" in app
    assert "licenses" not in (BACKEND / ".dockerignore").read_text(encoding="utf-8")
