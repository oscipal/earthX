#!/usr/bin/env python3
"""The reference of the terrain operator (M5-10): a synthetic alpine model of heights and what ``gdaldem`` makes of it.

Writes ``backend/tests/fixtures/terrain/gdaldem_reference.npz``, which ``test_terrain.py`` compares the operator with in
CI, where no ``gdaldem`` is installed. The model is synthetic (Fixtures nur synthetisch, CLAUDE.md): fractal relief by
spectral synthesis, 1 800 to 1 960 m on 160 × 160 m, 2 m pixels like swissALTI3D, slopes from 2° to 83° and a gap of nodata. Needs ``gdaldem``
on the path (Ubuntu: ``apt-get install gdal-bin``). From the repository root, with the backend venv:

    python scripts/m5-10/gdaldem_reference.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy
import rasterio
from rasterio.transform import from_origin

SIZE = 80
PIXEL = 2.0
NODATA = -9999.0
OUT = Path(__file__).resolve().parents[2] / "backend" / "tests" / "fixtures" / "terrain" / "gdaldem_reference.npz"

#: Name in the file → gdaldem arguments. Hillshade is 8 bits in gdaldem (1 to 255, 0 is nodata).
VARIANTS = {
    "slope_horn_degrees": ["slope"],
    "slope_zt_percent": ["slope", "-p", "-alg", "ZevenbergenThorne"],
    "aspect_horn": ["aspect"],
    "aspect_zt": ["aspect", "-alg", "ZevenbergenThorne"],
    "hillshade_horn": ["hillshade", "-az", "315", "-alt", "45", "-z", "1"],
    "hillshade_zt": ["hillshade", "-alg", "ZevenbergenThorne", "-az", "30", "-alt", "60", "-z", "2.5"],
    "hillshade_multidirectional": ["hillshade", "-multidirectional", "-alt", "45", "-z", "1"],
}


def heights() -> numpy.ndarray:
    """Fractal relief (power spectrum ~ k^-4), stretched to 1 800–1 960 m, with a gap of 5 × 7 pixels."""
    generator = numpy.random.default_rng(1050)
    ky = numpy.fft.fftfreq(SIZE)[:, None]
    kx = numpy.fft.rfftfreq(SIZE)[None, :]
    k = numpy.hypot(kx, ky)
    k[0, 0] = 1.0
    spectrum = (generator.normal(size=k.shape) + 1j * generator.normal(size=k.shape)) / k**2
    spectrum[0, 0] = 0
    relief = numpy.fft.irfft2(spectrum, s=(SIZE, SIZE))
    relief = (relief - relief.min()) / (relief.max() - relief.min())
    model = (1800 + 160 * relief).astype("float32")
    model[30:35, 50:57] = NODATA
    return model


def main() -> int:
    model = heights()
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "width": SIZE,
        "height": SIZE,
        "crs": "EPSG:2056",
        "transform": from_origin(2600000.0, 1200000.0, PIXEL, PIXEL),
        "nodata": NODATA,
    }
    # `gdaldem --version` prints the version and exits with 1 for want of a mode.
    version = subprocess.run(["gdaldem", "--version"], capture_output=True, text=True).stdout.strip().splitlines()[-1]
    results: dict[str, numpy.ndarray] = {"heights": model}
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / "dem.tif"
        with rasterio.open(source, "w", **profile) as destination:
            destination.write(model, 1)
        for name, arguments in VARIANTS.items():
            target = Path(folder) / f"{name}.tif"
            command = ["gdaldem", arguments[0], str(source), str(target), "-q", *arguments[1:]]
            subprocess.run(command, check=True)
            with rasterio.open(target) as result:
                results[name] = result.read(1, masked=True).astype("float32").filled(numpy.nan)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    numpy.savez_compressed(OUT, version=numpy.array(version), pixel=numpy.array(PIXEL), **results)
    print(f"{OUT.name}: {version}, {len(VARIANTS)} variants")
    return 0


if __name__ == "__main__":
    sys.exit(main())
