# M5-69 — Punkt als echter Punkt: Filter und Zuschnitt am Punkt

**Stand:** 25.11.2026, Plan mit Fragen an Otto (§6). Umsetzung nach den Empfehlungen in zwei Draft-PRs (§7); wo eine Antwort anders ausfällt, ändert dieselbe Session nach.
**Stufe B.** Höchstens zwei PRs (M5-Plan §2 Punkt 11).
**Grundlagen:** `docs/plans/vp3/ui-12-sammellauf.md` (F4, F5, §7), `docs/adr/0028-band-export-formen.md`, `backend/earthx/access/crop_rules.py`, M5-Plan §2 Punkt 9 („AOI ‚Point‘ ist immer ein echter Punkt“) und §6.2 (Zeile M5-69), Entscheidungslog bis 25.11.2026.
**Regeln:** Oberflächentexte nur Englisch, keine Hinweistexte, Panels scrollen nie (`docs/ui/leitfaden.md`).

Belegstufen: **P** am Quelltext gelesen (Stand `main` nach #418), **M** in dieser Session gemessen, **A** eigene Ableitung.

---

## 1. Auftrag (Otto, 25.11.2026)

1. **Filter am Punkt (F4 = 1):** „AOI coverage“ zählt, ob die Szene den Punkt enthält (0 oder 100 %). „Filter within AOI only“ und Wolken nehmen die Klasse des Pixels am Punkt.
2. **Zuschnitt am Punkt (F5 = 2):** „Crop to AOI“, „Download crop“ und der Zuschnitt im Processing ergeben nur das Pixel, auf dem der Punkt liegt: je Band in dessen nativer Auflösung, bei „One multi-band file“ in der gemeinsamen Auflösung. Auch die Ansicht auf der Karte (Crop and merge) zeigt nur dieses eine Pixel.
3. **Processing auf einem Pixel** funktioniert (Schritte, Statistik, Export). Wo ein Schritt bei 1×1 keinen Sinn hat, legt dieser Plan fest, was passiert, ohne Hinweistexte in der Oberfläche.
4. **Das unsichtbare Quadrat entfällt überall.** Alte Rezepte mit Punkt-AOI bleiben lesbar; dieser Plan klärt, ob sie ihr Ergebnis ändern dürfen.

## 2. Ausgangslage [P]

Das Quadrat lebt nur im Frontend: `bufferPointToPolygon` (0,05°) macht aus dem Punkt des Werkzeugs und einer hochgeladenen Punktdatei ein Polygon `aoi`; der Punkt selbst liegt daneben in `aoiPoint` und wird nur für die Anzeige und für die Suche ohne Flächenfilter gelesen. Alles andere bekommt das Quadrat.

| Stelle | Heute mit einem Punkt |
|---|---|
| `access/download.py` `parse_aoi_geometry` (Download, Job-Annahme) | nur Polygon/MultiPolygon, ein Punkt ist 400/422 |
| `processing/recipe.py` `Aoi` | nur Polygon/MultiPolygon |
| `api/aoi_cloud_filter.py` `_area`, `_polygonal` | „needs an area“ |
| `access/outlines.py` `AoiOutlines` | Anteil = Fläche ∩ / Fläche der AOI; ein Punkt hätte Fläche 0 |
| `access/aoi_clouds.py` (Wolken je Szene und je Durchgang) | verlangt Fläche > 0 |
| `processing/plan.py` `crop_window` (Processing, Statistik der Fläche) | verlangt Fläche > 0 |
| `crop_rules.source_crop_grid` (alle Formen des Downloads) | ergibt für einen Punkt schon genau ein Pixel |
| `crop_rules.native_crop_grid` (alter flacher Export, Zarr-Weg) | Transform mit Pixelgröße 0, bricht ab [M] |
| Ansicht „Crop and merge“ | Zuschnitt nur im Browser (`aoiClip.ts`), die AOI geht nie über das Netz |
| `catalog/coverage.py` (Coverage Map mit AOI) | „intersects needs a Polygon or MultiPolygon“ |

## 3. Regeln am Punkt

### 3.1 Welches Pixel [A]

Das Pixel, auf dem der Punkt liegt, ist das Pixel des Rasters der Quelle (Projektion, Pixelgröße und Raster der Szene, `source_crop_grid`), das den Punkt enthält. Liegt der Punkt genau auf einer Pixelkante, gilt das Pixel rechts bzw. unterhalb, wie heute `source_crop_grid` (Rundung mit `_LATTICE_SLACK`) und `rasterize` es halten. Bei „One multi-band file“ ist es das Pixel der gemeinsamen Auflösung, vom selben Ursprung aus (`pixel_scale`, ADR 0028 §2). Ein Mosaik nimmt das Pixel aus dem Raster der Gruppe (dem CRS, in dem die meisten Szenen liegen, `mosaic_order`).

### 3.2 Filter

- **AOI coverage:** 100 %, wenn der Umriss der Szene (bzw. die Vereinigung der Umrisse eines Durchgangs) den Punkt enthält, sonst 0 %. „Enthält“ heißt `covers`: ein Punkt auf dem Rand zählt. Eine Szene, deren Umriss den Punkt nicht enthält, berührt die AOI nicht.
- **Filter within AOI only, Wolken, Klassenanteile:** gemessen am einen Pixel der Klassenschicht am Punkt in voller Auflösung (keine Übersichtsstufe). Wolken sind damit 0 oder 100 %, jede Klasse 0 oder 100 %. Ist das Pixel nodata oder liegt der Punkt außerhalb des Rasters, gilt die vorhandene Regel für eine AOI ohne gültige Pixel (nodata 100 %, kein Wolkenwert).
- **Coverage Map** mit „Filter within AOI only“: dieselbe Regel, ein Punkt ist als `intersects` erlaubt.

### 3.3 Zuschnitt

- **Download crop** (synchron und als Export-Job): ein Pixel je Datei, `per_band` je Band in nativer Auflösung, `per_resolution` je Auflösung, `multi_band` in der gemeinsamen. Maske 1×1 mit Wert 1. `aoi.geojson` enthält den Punkt. Ist das Pixel in keiner Szene gültig, kommt wie heute „AOI outside items“.
- **Alter flacher Export und Zarr-Weg** (`native_crop_grid`): ebenfalls ein Pixel in der nativen Pixelgröße um den Punkt.
- **Crop and merge:** Die Karte zeigt nur das Pixel. Der Browser beschneidet weiter selbst; den Umriss des Pixels liefert ein neuer Endpunkt `POST /collections/{dataset}/pixel` (Punkt und Szenen im Body, nie in der URL, nie im Log), weil nur der Server das Raster der Quelle kennt (P10: das Frontend liest keine Quelleigenschaft wie `proj:transform`). Je Szene (bzw. Mosaik) gilt das Pixel ihres gezeigten Assets (F2).
- **Processing:** Das Raster eines Jobs ist wie bisher das des feinsten Bands; ein Punkt ergibt dort ein Pixel. Andere Bänder werden wie bisher auf dieses Raster gelegt.

### 3.4 Processing auf einem Pixel

| Schritt | Bei 1×1 |
|---|---|
| Auswahl, Band math, Masken, Klassenmaske | wie überall, je Pixel |
| Normalisieren | wie bei jeder Fläche ohne Spannweite: Min/Max, Perzentil, z-Score und robust ergeben 0 (vorhandene Regel `_divisor`: Spannweite 0 teilt durch 1) |
| Gelände (Neigung, Exposition, Schummerung) | lesen ihren Rand aus den Nachbarn der Quelle wie an jedem Rand eines Zuschnitts; am Rand der Szene oder neben nodata wird das Pixel nodata (gdaldem-Regel) |
| **Reprojektion** | Ergebnis ist das eine Pixel des Zielrasters, das den Punkt enthält; sein Wert ist der des Quellpixels, welche Methode auch gewählt ist (eine Interpolation zwischen Nachbarn gibt es bei einem Pixel nicht). Das Rezept behält die gewählte Methode, Hash unverändert (F4) |
| Statistik der Fläche | ein Pixel: Anzahl 1, Mittel = Wert, Streuung 0, Histogramm mit einer Klasse |
| Export, Ergebnis-ZIP, QGIS-Stil | 1×1-GeoTIFF mit Maske; ein Stil mit Min = Max bekommt eine Spanne um den Wert |
| Methodentext | statt „covers about 0.0 km²“: „The area of interest is one pixel at a point.“ (keine Koordinate) |

## 4. Das Quadrat entfällt

- Frontend: `aoi` ist der Punkt selbst; `aoiPoint`, `lastAoiPoint` und `bufferPointToPolygon` entfallen. Suche, Filter, Download, Processing und Ansicht bekommen den Punkt.
- Alles, was heute nur Flächen kennt (`isArea`, `orderAoi`, `Order.aoi`, Prüfung von `recipe.json` beim Laden), nimmt den Punkt ebenso.
- Der Umriss einer Gruppe in der Trefferliste (AOI ∩ Footprints) ist bei einem Punkt der ganze Footprint, wie heute ohne Schnittfläche (F5).
- **Alte Rezepte [P]:** Kein gespeichertes Rezept enthält einen Punkt; das Schema hat ihn bisher abgelehnt. Ein Rezept, das mit dem Werkzeug „Point“ entstand, trägt das Quadrat als Polygon und nichts, was es als Punkt kennzeichnet (auch nicht die Herkunft der AOI). Es bleibt lesbar, behält Hash und Ergebnis und wird beim Öffnen als Polygon-AOI übernommen (F1).

## 5. Umfang der Änderungen

**PR 1 (Backend und Plan):** `parse_aoi_geometry`, `recipe.Aoi` (+ `Point`), `aoi_cloud_filter`, `aoi_clouds`, `outlines`, `pass_filter`, `catalog/coverage`, `crop_rules.native_crop_grid`, `plan.crop_window`, Reprojektion im Kern, `methods`, QGIS-Stil bei Min = Max, Endpunkt `…/pixel`. Tests je Stelle: Punkt innen, auf der Kante, außerhalb, auf nodata; fehlerhafte Punkte (ohne Koordinaten, außerhalb von ±180/±90, nicht endlich, mit Höhe); ein altes Polygon-Rezept mit unverändertem Hash.

**PR 2 (Frontend):** Punkt als `aoi`, Wegfall des Quadrats, Pixelumriss für Crop and merge und Vorschau des Processing, Tests, Browser-Checks (§8).

## 6. Fragen an Otto

**F1 – Alte Rezepte und Aufträge mit dem Quadrat**
1. Bleiben, wie sie sind: lesbar, gleicher Hash, gleiches Ergebnis; geöffnet ergeben sie eine Polygon-AOI (das Quadrat). Es gibt nichts, woran sie als Punkt zu erkennen wären. **Empfehlung.**
2. Ein Rezept, dessen AOI genau ein Quadrat von 0,1° ist, wird beim Öffnen als Punkt in seiner Mitte gelesen (ändert das Ergebnis; ein absichtlich so gezeichnetes Rechteck würde mitgeändert).

**F2 – Welches Pixel zeigt Crop and merge**
1. Je Szene das Pixel im Raster ihres gezeigten Assets; bei einem Mosaik das Pixel der ersten Szene der Mosaikreihenfolge, die den Punkt enthält; zeigt eine Ansicht mehrere Bänder verschiedener Auflösung, das Pixel des feinsten. **Empfehlung.**
2. Wie 1, aber bei verschiedenen Auflösungen das Pixel des gröbsten.

**F3 – Kamera bei Crop and merge mit einem Punkt**
1. Die Karte fliegt auf das Pixel, so nah, wie der Datensatz Kacheln hat (ein Pixel von 10 m ist bei Zoom 14 kaum ein Bildschirmpixel). **Empfehlung.**
2. Die Kamera bleibt, wo sie ist.

**F4 – Reprojektion auf einem Pixel**
1. Ein Pixel des Zielrasters (das den Punkt enthält) mit dem Wert des Quellpixels, unabhängig von der Methode (§3.4). **Empfehlung.**
2. Die Reprojektion rechnet wie bei einer Fläche mit der gewählten Methode; es entstehen bis zu 2×2 Zielpixel, davon nur eines in der Maske, Randpixel teils leer.

**F5 – Umriss der Gruppe in der Trefferliste**
1. Ganzer Footprint, wie heute ohne Schnittfläche. **Empfehlung.**
2. Kein Umriss, nur der Punkt.

## 7. Aufteilung

- **PR 1** (Branch `claude/adoring-pasteur-px0etv`, gegen `main`): Plan, Backend, Entscheidungslog.
- **PR 2** (Branch `claude/adoring-pasteur-px0etv-frontend`, auf PR 1 gestapelt): Frontend, Browser-Checks, Leitfaden und Plan nachgeführt.

## 8. Prüfungen

- PR 1: `pytest` der geänderten Module (`tests/earthx/access`, `tests/earthx/api`, `tests/earthx/processing`, `tests/catalog/test_coverage.py`), `ruff check backend`, `lint-imports`.
- PR 2: Unit-Tests der geänderten Module, `npx tsc -b`, `npm run lint`.
- Browser-Checks mit Punkt-AOI bei 1280×800 und 360×740: Suche, AOI coverage, Crop and merge (ein Pixel), Download crop, Processing mit einem Schritt (`frontend/e2e/m5-69-point.cjs`); dazu die vorhandenen, die einen Punkt setzen (`ui-12-search-panel.cjs`, `within-aoi.cjs`, `evaluate-coverage.cjs`).
