"""Writes the reference styles of ``test_qgis_style.py`` (M5-64): each style the platform writes, as QGIS reads and writes it back.

Not part of the test run: it needs PyQGIS (checked with QGIS 3.34.4 LTR). First the platform's styles, then QGIS::

    cd backend && python -m tests.earthx.access.test_qgis_style <directory>
    python3 tests/fixtures/qgis/make_reference.py <directory> tests/fixtures/qgis

For every ``<case>.qml`` in the directory QGIS opens a synthetic GeoTIFF (three bands, ``uint16``, scale 0.0001 and offset
-0.1, as Sentinel-2 states them), loads the style, and saves it with the category "Symbology" as ``<case>.qml`` here.
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy  # noqa: E402
from osgeo import gdal, osr  # noqa: E402
from qgis.core import QgsApplication, QgsMapLayer, QgsRasterLayer  # noqa: E402


def synthetic_tiff(path: str) -> None:
    dataset = gdal.GetDriverByName("GTiff").Create(path, 16, 16, 3, gdal.GDT_UInt16)
    dataset.SetGeoTransform((500000.0, 10.0, 0.0, 5200000.0, 0.0, -10.0))
    crs = osr.SpatialReference()
    crs.ImportFromEPSG(32632)
    dataset.SetProjection(crs.ExportToWkt())
    for index in range(1, 4):
        band = dataset.GetRasterBand(index)
        band.WriteArray(numpy.arange(256, dtype=numpy.uint16).reshape(16, 16) * 10 * index)
        band.SetNoDataValue(0)
        band.SetScale(0.0001)
        band.SetOffset(-0.1)
    dataset.FlushCache()


def main(source: Path, target: Path) -> None:
    app = QgsApplication([], False)
    app.initQgis()
    with tempfile.TemporaryDirectory() as work:
        tiff = str(Path(work) / "data.tif")
        synthetic_tiff(tiff)
        for style in sorted(source.glob("*.qml")):
            layer = QgsRasterLayer(tiff, style.stem)
            message, loaded = layer.loadNamedStyle(str(style.resolve()))
            if not loaded:
                raise SystemExit(f"{style.name}: {message}")
            layer.saveNamedStyle(str((target / style.name).resolve()), categories=QgsMapLayer.Symbology)
    app.exitQgis()


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
