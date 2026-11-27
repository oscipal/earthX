"""Write the QGIS styles the tests of M5-64 compare ours with, by QGIS itself (plan ``m5-64-qgis-stil.md`` §6).

QGIS has no schema of its style files; the reference is what QGIS writes. This script builds the three kinds of style
through the QGIS API from the same inputs as ``backend/tests/earthx/access/test_qgis_style.py`` (a ramp of 256 colours,
three stretched channels, two classes) and saves them with the category "Symbology". It needs QGIS (3.34 measured,
``python3-qgis`` on Ubuntu 24.04) and the colour table of the tiles, read from the JSON beside the styles, so that it
runs with the system Python of QGIS:

    PYTHONPATH=backend python -c "import json; from earthx.access.colormap_tables import ramp_colours; \\
        print(json.dumps(ramp_colours('viridis')))" > backend/tests/fixtures/qgis/viridis.json
    QT_QPA_PLATFORM=offscreen python3.12 scripts/write-qgis-reference-styles.py backend/tests/fixtures/qgis

The files are committed; CI compares with them and does not need QGIS.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import (  # noqa: E402
    QgsApplication,
    QgsColorRampShader,
    QgsContrastEnhancement,
    QgsGradientColorRamp,
    QgsGradientStop,
    QgsMapLayer,
    QgsMultiBandColorRenderer,
    QgsPalettedRasterRenderer,
    QgsRasterLayer,
    QgsRasterShader,
    QgsSingleBandPseudoColorRenderer,
)
from qgis.PyQt.QtGui import QColor  # noqa: E402

LOW, HIGH = 0.0, 0.3
RANGES = ((0.0, 0.25), (0.01, 0.26), (0.02, 0.27))
CLASSES = ((10, "#006400", "Tree cover"), (20, "#ffbb22", "Shrub & <land>"))


def _raster(path: Path, bands: int) -> QgsRasterLayer:
    """A small raster for the layer the renderer belongs to; written with GDAL, which QGIS brings."""
    from osgeo import gdal

    gdal.UseExceptions()
    dataset = gdal.GetDriverByName("GTiff").Create(str(path), 4, 4, bands, gdal.GDT_UInt16)
    dataset.SetGeoTransform([500000, 10, 0, 5200000, 0, -10])
    for band in range(1, bands + 1):
        dataset.GetRasterBand(band).WriteArray(__import__("numpy").arange(16, dtype="uint16").reshape(4, 4))
    dataset = None
    return QgsRasterLayer(str(path), path.stem)


def _save(layer: QgsRasterLayer, path: Path) -> None:
    message, ok = layer.saveNamedStyle(str(path), QgsMapLayer.StyleCategory.Symbology)
    if not ok:
        raise SystemExit(f"QGIS did not save {path.name}: {message}")


def main(folder: Path) -> None:
    colours = [QColor(r, g, b) for r, g, b, _ in json.loads((folder / "viridis.json").read_text(encoding="utf-8"))]
    app = QgsApplication([], False)
    app.initQgis()
    with tempfile.TemporaryDirectory() as work:
        scratch = Path(work)
        layer = _raster(scratch / "one.tif", 1)
        last = len(colours) - 1
        ramp = QgsGradientColorRamp(
            colours[0], colours[-1], False, [QgsGradientStop(i / last, colours[i]) for i in range(1, last)]
        )
        shader = QgsColorRampShader(LOW, HIGH)
        shader.setSourceColorRamp(ramp)
        shader.setColorRampType(QgsColorRampShader.Interpolated)
        shader.setColorRampItemList(
            [QgsColorRampShader.ColorRampItem(LOW + (HIGH - LOW) * i / last, colours[i], f"{LOW + (HIGH - LOW) * i / last:.6g}") for i in range(len(colours))]
        )
        raster_shader = QgsRasterShader()
        raster_shader.setRasterShaderFunction(shader)
        renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, raster_shader)
        renderer.setClassificationMin(LOW)
        renderer.setClassificationMax(HIGH)
        layer.setRenderer(renderer)
        _save(layer, folder / "pseudocolor.qml")

        layer = _raster(scratch / "three.tif", 3)
        rgb = QgsMultiBandColorRenderer(layer.dataProvider(), 1, 2, 3)
        for band, (low, high), setter in zip(
            (1, 2, 3), RANGES, (rgb.setRedContrastEnhancement, rgb.setGreenContrastEnhancement, rgb.setBlueContrastEnhancement)
        ):
            enhancement = QgsContrastEnhancement(layer.dataProvider().dataType(band))
            enhancement.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum)
            enhancement.setMinimumValue(low)
            enhancement.setMaximumValue(high)
            setter(enhancement)
        layer.setRenderer(rgb)
        _save(layer, folder / "rgb.qml")

        layer = _raster(scratch / "classes.tif", 1)
        entries = [QgsPalettedRasterRenderer.Class(value, QColor(colour), name) for value, colour, name in CLASSES]
        layer.setRenderer(QgsPalettedRasterRenderer(layer.dataProvider(), 1, entries))
        _save(layer, folder / "paletted.qml")
    app.exitQgis()


if __name__ == "__main__":
    main(Path(sys.argv[1]))
