# DS-04d — Sentinel-1 GRD bleibt in Radargeometrie: Plan-Schritt

**Stand:** 14.11.2026, Stufe B. Beauftragt von Otto am 11.11.2026. Fragen F1–F8 beantwortet (§9a); umgesetzt nach dem
Merge von #335 und #341 im selben Draft-PR (§12).

Bezug: `adr/0018` §4.1, §4.3, §4.4 (Nachtrag DS-04d), `plans/ds/ds-04-s1-anbinden.md`, `plans/m5/m5-28-nodata-ergebnisse.md`,
`adr/0028` (Raster der Quelle), M3-18 (Maske statt nodata, `access/download.py`).

Belegstufen wie in `adr/0018`: [M] gemessen in dieser Sitzung, [P] im Code oder in Quellen gelesen, [A] Ableitung.

## 1. Entscheidung Otto (11.11.2026)

Sentinel-1 GRD wird ohne richtige Bearbeitung (σ⁰ und Geländekorrektur) nie georeferenziert ausgeliefert.

1. Download und Ergebnisse (Zuschnitt, Operatoren) bleiben in Radargeometrie: kein CRS, kein Geotransform, keine
   Spiegelung. Die GCPs der Quelle bleiben in der Datei, umgerechnet auf das ausgeschnittene Fenster.
2. Zuschnitt: umschließendes Pixel-Fenster der AOI über die GCPs/TPS, dazu eine Maske aus der ungefähr übertragenen
   AOI-Form; außerhalb nodata nach den Regeln aus M5-28. *Präzisiert durch F1 = 2 (§9a): kein nodata außerhalb
   der Form, die Form steht nur in `mask.tif` (M3-18).*
3. Mosaik je Durchgang (aufeinanderfolgende Slices einer Bahn) bleibt, aber in Radargeometrie aneinandergehängt.
   Vorher prüfen, ob das sauber geht; wenn nicht, Frage statt Annahme.
4. Reprojektion entfällt für Sentinel-1 in Download und Processing. Was nicht geht, erscheint nicht
   (Registry-Angabe, kein Code je Datensatz; Bezug `georeferencing: gcp_tps`).
5. Die Karte zeigt weiter über TPS („approximate geolocation“), unverändert. F11 und M5-30b laufen parallel:
   dieselben Dateien → zuerst fragen.
6. Die Textdatei des Downloads nennt Radargeometrie, Szene und Pixel-Fenster (Zeile/Spalte). Im Frontend keine
   Hinweise, Erklärungen höchstens im Tooltip.
7. Nachtrag zu `adr/0018` §4.3/§4.4 und eine Zeile im Entscheidungslog (beides mit diesem Plan-Schritt).

## 2. Messung: Geht das Mosaik in Radargeometrie sauber? [M]

Zwei Paare aufeinanderfolgender IW-Slices desselben Datatakes (eine absteigende Bahn über Hügel- und Bergland, eine
aufsteigende über überwiegend flachem Land, Oktober 2026), gelesen aus der Produkt-Annotation
(`annotation/iw-vv.xml`) und den GCPs der Messdatei (`measurement/iw-vv.tiff`, Kopf und je vier Zeilen an der Naht).
Skripte nur im Kratzverzeichnis der Sitzung.

| Prüfung | absteigend | aufsteigend | Folgerung |
|---|---|---|---|
| Erste Zeile von B nach letzter Zeile von A | 1,500 ms = 1,000 Zeilenabstand | 1,490 ms = 0,995 Zeilenabstand (Zeitauflösung 1 µs) | lückenlos, keine Überlappung |
| Versatz von B in Zeilen (Zeitdifferenz ÷ Zeilenabstand) | 16 665,000 = Höhe von A | 16 689,00 = Höhe von A | ganzzahlig, Zeilen fluchten |
| Zeilenabstand A ↔ B relativ | 1,7·10⁻¹¹ | 1,6·10⁻⁸ | über eine Szene < 0,001 Zeilen |
| Beginn der Bodenentfernung (`slantRangeTime`, `sr0`, `gr0` = 0) | gleich bis 10⁻¹² | gleich | Spalte 0 ist in beiden dieselbe Entfernung |
| Pixelabstand Spalten | 10 m / 10 m | 10 m / 10 m | Spalten fluchten |
| Breite A / B | 26 414 / 26 393 | 26 696 / 26 706 | verschieden; schmalere Szene rechts mit nodata auffüllen |
| Gültige Spalten in der Nahtzeile A / B | 300–25 432 / 300–25 432 | 627–25 778 / 627–25 778 | gleich |
| Korrelation der Werte: Naht ↔ Nachbarzeilen in A und B | 0,88 ↔ 0,86 / 0,92 | 0,83 ↔ 0,84 / 0,85 | keine radiometrische Naht |
| GCP Zeile 0 von B ↔ letzte GCP-Zeile von A, Spalte 0 | 10,19 m | 10,11 m | genau eine Zeile weiter |
| GCPs der TIFF ↔ Geolocation-Grid der Annotation | gleich (< 10⁻¹³°) | gleich | GCPs = Gitter der Annotation (10 × 21 Punkte) |
| STAC `start_datetime`/`end_datetime` ↔ erste/letzte Zeile der Annotation | gleich (µs) | gleich | Versatz aus den Item-Zeiten ableitbar |

**Lage der TPS im Mosaik** (60 × 60 Punkte je Slice, TPS je Slice ↔ TPS aus der Vereinigung beider GCP-Sätze, Zeilen
von B um die Höhe von A verschoben):

| | Median | 99 % | max |
|---|---|---|---|
| absteigend (Relief), Slice A / B | 0,1 / 0,4 m | 37 / 225 m | 169 / 421 m |
| aufsteigend (flach), Slice A / B | 0,03 / 0,08 m | 7 / 30 m | 20 / 54 m |

Die großen Werte liegen an der Naht. Die TPS je Slice ist dort selbst nicht stetig: Die letzte Zeile von A und die
erste von B liegen nach den beiden TPS 8 bis 308 m (absteigend) bzw. 9 bis 34 m (aufsteigend) auseinander statt
rund 10 m. Die TPS der Vereinigung schließt die Naht.

**TPS und Fenster [M]:** Die inverse TPS (GDAL, `GCPTransformer(tps=True).rowcol`) trifft die Vorwärts-TPS auf
2000 Zufallspunkten bis 3·10⁻⁸ Pixel. Werden alle GCPs um ein Fenster (Zeile 5000, Spalte 7000) verschoben, liegt die
TPS der verschobenen GCPs bis 3·10⁻¹² ° auf der Quelle: Verschieben aller GCPs ändert die Lage nicht. Ein Fenster von
3000 × 3000 Pixeln enthält nur 2 der 210 GCPs; eine TPS braucht mindestens 3.

**Ergebnis:** Das Aneinanderhängen ist sauber: lückenlos, ganzzahliger Zeilenversatz, gleiche Spalten, keine
Überlappung, keine radiometrische Naht. Offen sind nur die Quelle des Zeilenversatzes (F2), die GCPs des Mosaiks
(F3) und Fälle, die nicht gemessen sind (fehlende Slices, F4). Zwei Paare sind eine Stichprobe; die Umsetzung prüft
jede Naht (§4.6) statt es anzunehmen.

**Nebenbefund [M], gehört zu DS-05d (Otto, 11.11.2026):** Die Assets `schema-product-vv`/`-vh` der Items zeigen auf
`annotation/rfi/rfi-iw-*.xml`, nicht auf die Produkt-Annotation `annotation/iw-*.xml`. DS-05d (σ⁰) muss das beim Lesen
der Annotation berücksichtigen; diese Aufgabe braucht sie nicht (F2 = 1).

## 3. Ausgangslage im Code [P]

- **Lesen:** `readers/cog.py` öffnet eine `gcp_tps`-Datei immer als `WarpedVRT` in das CRS der GCPs (EPSG:4326).
  Kachel, Zuschnitt, Export, Mosaik, Job und Runner sehen damit dasselbe georeferenzierte Raster (DS-04a).
- **Zuschnitt (Download):** `access/download.py` `_laid_out_crop_bytes` über `crop_rules.source_crop_grid` (CRS der
  Quelle, hier das der TPS) und `StackReader` (`access/band_export.py`); Datei = Rechteck um die AOI, Werte
  unverändert, `mask.tif` daneben (M3-18). `source_crop_grid` wirft ohne CRS.
- **Export-Job:** `processing/export.py` über `WarpedItem` (`processing/warped.py`), EPSG:4326 oder Layout im CRS der
  Quelle; Prüfung vergleicht `crs`.
- **Job:** `processing/core.py`, `plan.py` (`crop_window` über `transform_geom` ins CRS der Quelle), `source.py`
  (gleiches Gitter über `crs`), `mosaic.py` (nur nordorientierte Gitter, `WarpedVRT(crs=…)`), `workfile.py`
  (`<SRS>`, `<GeoTransform>`). STAC des Ergebnisses: `proj:code` bzw. `proj:wkt2`. Kein Weg liest oder schreibt GCPs.
- **Ergebnis auf der Karte:** `api/result_tiles.py` öffnet `result.tif` mit `georeferencing` = `geotransform`; eine
  Datei mit GCPs gibt dort `GeoreferenceMismatch` (502).
- **Mosaik verlangt Reprojektion:** `api/intake.py:891` und `api/tiler.py:859` weisen ein Mosaik ab, wenn der
  Datensatz `reprojection` nicht erlaubt.
- **Registry:** `sentinel-1-grd.yaml` hat `reprojection: true`, `interpolation: true`; `results_group_by` ist
  `[datetime, s1:datatake_id]`.
- **Runner:** derselbe Kern (`processing.run`); was im Kern gilt, gilt dort.
- **Frontend:** blendet Operatoren nach den Capabilities der Prozessbeschreibung aus; mit `reprojection: false`
  erscheint „Reproject“ für Sentinel-1 nicht. Keine Stelle zeigt das CRS eines Ergebnisses als Text.

## 4. Umsetzung (Vorschlag)

Allgemein über `georeferencing: gcp_tps`, ohne Code je Datensatz. Für `geotransform` ändert sich nichts.

### 4.1 Lesen in Radargeometrie

`readers/cog.py` bekommt einen zweiten Weg für `gcp_tps`: die Datei **ohne** Warp, im eigenen Pixelraster, mit
ihren GCPs. Die Kachel nutzt weiter den TPS-Warp (Punkt 5). Wer welchen Weg nimmt, steht an einer Stelle:
Kachel und Statistik der Ansicht → TPS; Zuschnitt, Export, Bänder-Download, Job, Runner → Radargeometrie.
Die Prüfung „Registry ↔ Datei“ (`GeoreferenceMismatch`) bleibt für beide Wege.

### 4.2 Pixel-Fenster und Maske

Rein, ohne I/O, in `access/crop_rules.py` (von `processing` mitbenutzt wie heute):

- `radar_window(gcps, aoi, width, height)`: AOI verdichtet (Kantenpunkte höchstens alle 100 m), jeder Punkt über die
  inverse TPS nach (Zeile, Spalte); Fenster = `floor(min)` bis `ceil(max)`, geschnitten mit der Szene. Leer →
  `AoiOutsideItems` wie heute.
- `radar_mask(gcps, aoi, window)`: dasselbe Polygon in Pixelkoordinaten des Fensters, gerastert mit der Regel von
  `mask.tif` (`all_touched`). „Ungefähr übertragen“: Die Form folgt der TPS an den verdichteten Punkten, dazwischen
  gerade.
- Außerhalb der Maske bleiben die Werte unverändert (F1 = 2, M3-18); die Form steht nur in `mask.tif`.

### 4.3 GCPs der Ausgabe

Alle GCPs der Quelle, um (Zeile, Spalte) des Fensters verschoben, auch die außerhalb des Fensters (§2: ein Fenster
enthält oft weniger als drei; nur mit allen bleibt die TPS gleich). Bei gröberer Auflösung (F5) geteilt durch den
Faktor; die TPS ist dagegen invariant [A]. CRS der GCPs wie in der Quelle (EPSG:4326). Kein CRS und kein
Geotransform des Rasters, keine Spiegelung: Zeile 0 bleibt die erste Zeile der Szene, auch bei aufsteigender Bahn.

### 4.4 Zuschnitt, Bänder-Download, Export-Job

- Ein Fenster je Szene bzw. je Mosaik (§4.6), Werte unverändert (M5-28 R6), nodata der Quelle (0).
- `mask.tif` auf dem Fenster mit denselben GCPs (Auslegung A2), `aoi.geojson` unverändert.
- Bänder-Download: VV und VH einer Szene liegen auf demselben Raster; `StackReader` liest ohne Warp.
- Die Größenschätzung (`plan_outputs`) rechnet aus dem Fenster, nicht aus `gsd` und AOI-Fläche, sobald die GCPs
  gelesen sind; vorher bleibt die heutige Schätzung als obere Grenze.

### 4.5 Job und Operatoren, Runner

- Das Raster eines Jobs („Gitter“) kennt eine dritte Art neben CRS-Gitter und Zarr: Radargitter = Breite, Höhe,
  GCPs. `plan.crop_window`, `source.py`, `core.py`, `workfile.py` lesen es; Pixel-Operatoren (`select`, `band_math`,
  `normalize`, `sar_db`, Fokal-Operatoren aus DS-05) laufen unverändert, weil sie nur Pixel sehen.
- `result.tif` und `mask.tif` tragen die GCPs (§4.3) statt `crs`/`transform`; STAC des Ergebnisses ohne `proj:code`
  und `gsd`, mit `earthx:georeferencing: gcp_tps`.
- Operatoren der Art `grid` (heute nur `reproject`) gibt es für `gcp_tps` nicht (§4.7).
- Runner: derselbe Kern, keine eigene Änderung; der Hash-Vergleich Plattform ↔ Runner gilt weiter.

### 4.6 Mosaik je Durchgang in Radargeometrie

- Reihenfolge nach der Zeit der ersten Zeile; Versatz von Slice B = (Zeit erste Zeile B − Zeit erste Zeile A) ÷
  Zeilenabstand, Zeilenabstand = (letzte − erste) ÷ (Höhe − 1), nach F2 aus den Item-Zeiten.
- **Geprüft an jeder Naht**, sonst kein Mosaik (F4): Versatz ganzzahlig (± 0,05 Zeilen), Zeilenabstand gleich
  (relativ 10⁻⁶), Versatz = Höhe des Vorgängers (lückenlos), GCP (letzte Zeile, Spalte 0) von A und GCP (Zeile 0,
  Spalte 0) von B höchstens zwei Pixelabstände auseinander (Spalten fluchten; gemessen 10,1–10,2 m).
- Breite des Mosaiks = größte Breite; schmalere Slices rechts nodata. Fenster und Maske wie §4.2 über die GCPs des
  Mosaiks; gelesen werden nur die Slices, die das Fenster berührt.
- GCPs des Mosaiks nach F3.
- Die Mosaik-Sperre ohne `reprojection` (`api/intake.py`, `api/tiler.py`) gilt nur für `geotransform`; ein
  Radar-Mosaik warpt nichts.

### 4.7 Reprojektion erscheint nicht

- `sentinel-1-grd.yaml`: `reprojection: false`. `interpolation` bleibt `true`, falls F5 = 1 (gröbere Auflösung mit
  Mittelung); sonst ebenfalls `false`.
- Startprüfung der Registry: `georeferencing: gcp_tps` mit `reprojection: true` ist ein `ConfigError` (Bezug zu
  Punkt 4, F6). Damit erscheint „Reproject“ im Panel nicht (Operator-Registry über die Capability), ohne Code im
  Frontend.
- Ein altes Rezept mit `reproject` auf Sentinel-1 wird beim erneuten Start mit `422` und Grund abgewiesen, wie jede
  nicht freigegebene Fähigkeit.

### 4.8 Ergebnis auf der Karte

`api/result_tiles.py` öffnet ein Ergebnis mit der Georeferenz seines Datensatzes aus dem Rezept
(`ResolvedAsset.georeferencing`); ein Radar-Ergebnis wird wie eine Szene über die TPS seiner GCPs gezeichnet
(Punkt 5, Auslegung A3). Die Ansicht der Szenen bleibt unverändert.

### 4.9 Textdatei

`build_notice_text` bekommt für `gcp_tps` zwei Zeilen statt `Resolution: native` (Auslegung A4), etwa:

```
Grid: radar geometry of the source scene, not map-projected; the file keeps the scene's ground control points, shifted to the window.
Scene S1…_009D5A: rows 12034–15210, columns 4120–9876 (0-based, inclusive).
```

Beim Mosaik eine Zeile je Slice mit seinem Teil des Fensters. Frontend: keine Hinweise; ein Tooltip nur, wo heute
ein Feld „Reproject“ oder eine Auflösung erklärt wird und für Sentinel-1 wegfällt (A5).

### 4.10 Version

Sentinel-1-Jobs schreiben andere Bytes (kein CRS, GCPs, anderes Raster). `earthx.__version__` 0.5.1 → 0.5.2 (F7);
`recipe_version` bleibt, weil `georeferencing` schon im Rezept steht. Neues Runner-Image für Ottos Hash-Vergleich.

## 5. Auslegungen (Vorschlag)

- **A1** Punkt 1 gilt auch für Bänder-Download und Export-Job, nicht nur für den synchronen Zuschnitt.
- **A2** `mask.tif` trägt dieselben GCPs wie die Datendatei (gleiches Raster, Prüfung `_verify_asset_crop` vergleicht
  Größe und GCPs statt `transform`/`crs`).
- **A3** „Die Karte zeigt weiter über TPS“ heißt auch: Ergebnis-Layer von Sentinel-1 werden über die TPS ihrer GCPs
  gezeichnet; ohne das ergäbe jede Ergebnis-Kachel 502.
- **A4** Pixel-Fenster 0-basiert, erste und letzte Zeile/Spalte eingeschlossen; Szene mit ihrer Item-ID.
- **A5** Der Tooltip „Approximate geolocation“ (Registry `limitations`/`notices`) bleibt der Ort der Erklärung; kein
  neuer Text im Frontend, sofern nach der Umsetzung keine Stelle leer oder unklar wird.
- **A6** Die Kachel-Mosaik-Ansicht (`access/mosaic_tiles.py`) bleibt, wie sie ist (Punkt 5).

## 6. Tests (synthetisch, `tests/fixtures`)

Erweitert `readers/mini_gcp.py` um zwei aneinanderhängende Slices mit Zeitangaben und eine aufsteigende Szene.

- **Fenster:** AOI ganz innen, am Rand, über die Naht, ganz außerhalb (`AoiOutsideItems`), Punkt-AOI, Polygon mit
  Loch, Multipolygon; Fenster umschließt alle Eckpunkte über die inverse TPS; aufsteigende Szene nicht gespiegelt.
- **Maske:** `mask.tif` innen 1, außen 0; die Datendatei behält außerhalb der Form die Werte der Quelle (F1 = 2); Form folgt der TPS an verdichteten Kanten (Gegenprobe ohne Verdichtung weicht ab).
- **GCP-Verschiebung:** alle GCPs vorhanden, um das Fenster verschoben; TPS der Ausgabe an (z, s) = TPS der Quelle an
  (z + Zeile₀, s + Spalte₀) bis 10⁻⁹ °; bei gröberer Auflösung (F5) geteilt; Fenster ohne eigene GCPs bleibt
  platzierbar.
- **Fehlendes CRS:** Datendatei, `mask.tif`, Export-Job, Job-Ergebnis und Runner-Ergebnis haben `crs is None`,
  Identitäts-Transform, GCPs gesetzt; STAC ohne `proj:code`; ein `geotransform`-Datensatz behält sein CRS (Gegenprobe).
- **Mosaik:** lückenlos → eine Datei, Werte an der Naht = Werte der Slices; Lücke, Überlappung, ungleicher
  Zeilenabstand, versetzte Spalten, nicht ganzzahliger Versatz → Verhalten nach F4 mit Grund; schmalere Slice rechts
  nodata.
- **Reprojektion:** Startprüfung `gcp_tps` + `reprojection: true` → `ConfigError`; `reproject` im Rezept auf
  Sentinel-1 → `422`; Mosaik ohne `reprojection` bei `gcp_tps` erlaubt, bei `geotransform` weiter abgewiesen.
- **Ergebnis-Kachel:** Radar-Ergebnis → `200` über TPS; Ergebnis mit GCPs bei `geotransform`-Datensatz → `502` wie heute.
- **Textdatei:** Zeilen nach §4.9, keine Koordinaten der AOI.
- **Zweckfremd:** GCPs ohne CRS, weniger als drei GCPs, GCPs außerhalb der Szene, AOI über den Datumssprung,
  Fenster größer als die Grenze (`422` vor dem Lesen).

## 7. Parallele Arbeiten: dieselben Dateien [P]

| PR | betrifft auch diese Aufgabe |
|---|---|
| [#340](https://github.com/oscipal/earthX/pull/340) F11 (Quicklook aus Kacheln) | nein: `frontend/src/datasets.ts`, `types.ts`; diese Aufgabe ändert das Frontend nicht (A5) |
| [#335](https://github.com/oscipal/earthX/pull/335) M5-30b Teil 3a | ja: `api/tiler.py` (Mosaik-Sperre, Download-Route), `processing/tile.py` am Rand |
| [#341](https://github.com/oscipal/earthX/pull/341) M5-30b Teil 7 | ja: `api/tiler.py`, `catalog/registry.py` (Startprüfung), `sentinel-1-grd.yaml` (eine Zeile) |
| M5-30b Teil 6 (Zuschnitt/Job, noch kein PR) | ja: `access/download.py`, `api/intake.py`, `processing/export.py` (Grenzen je Szene) |

Frage dazu: F8 (beantwortet: erst nach #335 und #341).

## 8. Umfang und Commits

Ein Draft-PR, wie beauftragt. Schätzung ohne Tests rund 500–650 Zeilen, über dem Richtwert von 400; die Commits
trennen die Teile: (1) Lesen in Radargeometrie und `radar_window`/`radar_mask`/GCP-Verschiebung, (2) Zuschnitt,
Bänder-Download, Export-Job, Textdatei, (3) Job-Kern und Ergebnis-Kachel, (4) Mosaik je Durchgang, (5) Registry
(`reprojection`, Startprüfung, Mosaik-Sperre), (6) Version, Doku-Nachträge, Log.

## 9. Fragen an Otto — beantwortet am 11.11.2026 (§9a)

**F1 — Außerhalb der AOI-Form (Punkt 2 ↔ M3-18 „Maske statt nodata“).** M3-18 lässt in der Datendatei jeden Wert
des Rechtecks stehen und gibt die Form nur als `mask.tif` mit; Punkt 2 sagt „außerhalb nodata“.
1. Für `gcp_tps` außerhalb der übertragenen Form nodata (Quelle: 0, Job: Regel M5-28), in Zuschnitt und Job;
   `mask.tif` bleibt zusätzlich, damit der ZIP-Aufbau gleich bleibt. Andere Datensätze unverändert. **(Empfehlung)**
2. Wie alle anderen (M3-18): Werte bleiben, die Form steht nur in `mask.tif`.
3. Wie 1, aber ohne `mask.tif`.

**F2 — Woher der Zeilenversatz der Slices kommt (Punkt 3).**
1. Aus `start_datetime`/`end_datetime` der Items und der Zeilenzahl, mit den Prüfungen aus §4.6; neue allgemeine
   Registry-Angabe, welche Item-Felder die Zeit der ersten und letzten Zeile tragen (z. B. `line_times`), nur mit
   `gcp_tps` zulässig. Gemessen auf die µs gleich mit der Annotation. **(Empfehlung)**
2. Aus der Produkt-Annotation (XML): genau, auch für die Spalten, aber eine Anfrage mehr je Slice, Lesen eines
   Formats je Datensatz, und die Items verweisen auf die falsche Datei (Nebenbefund §2).
3. Nur aus den GCPs (inverse TPS): an der Naht bis rund 300 m = 30 Zeilen ungenau, nicht verlässlich.

**F3 — GCPs eines Mosaiks.**
1. Vereinigung der GCPs aller Slices, Zeilen verschoben. Die Naht wird stetig; die Lage weicht von der Ansicht je
   Szene im Median unter 1 m, an der Naht im Relief bis rund 200–400 m ab (§2). **(Empfehlung)**
2. Kein Mosaik in einer Datei: je Slice ein eigenes Fenster und eine eigene Datei (ZIP: eine Datei je Slice; Job:
   eine Szene je Auftrag).

**F4 — Wenn eine Naht die Prüfung nicht besteht (fehlender Slice, Versatz, Überlappung).** Nicht gemessen, aber
möglich.
1. Download: je zusammenhängendem Stück eine Gruppe (`group-NN/`), Textdatei nennt den Grund; Job: `422` mit Grund
   („the slices of this pass do not join“). **(Empfehlung)**
2. Lücke mit nodata-Zeilen füllen, Überlappung „erster gültiger Wert“; ein fehlender Slice kostet bis rund 16 700
   leere Zeilen.
3. Immer `422`.

**F5 — Gröbere Auflösung im Zuschnitt (F10c, ganzzahliger Faktor) in Radargeometrie.**
1. Bleibt: Zeilen und Spalten um den Faktor zusammengefasst mit der Methode des Zuschnitts, GCPs geteilt; kein
   Warp. **(Empfehlung)**
2. Für `gcp_tps` nur native Auflösung; die Wahl erscheint nicht.

**F6 — Reprojektion ausblenden (Punkt 4).**
1. `reprojection: false` im Eintrag und Startprüfung „`gcp_tps` ⇒ keine Reprojektion“; die Mosaik-Sperre ohne
   Reprojektion gilt nur noch für `geotransform`. **(Empfehlung)**
2. Nur `reprojection: false` im Eintrag, keine Startprüfung.

**F7 — Version.**
1. `earthx.__version__` 0.5.1 → 0.5.2, wie M5-28. **(Empfehlung)**
2. 0.5.1 → 0.6.0, weil Sentinel-1-Ergebnisse kein CRS mehr tragen.

**F8 — Reihenfolge zu M5-30b und F11 (Punkt 5).**
1. Umsetzung erst, wenn #335 und #341 auf `main` sind; dann `main` holen und bauen. M5-30b Teil 6 wartet umgekehrt
   auf diesen PR oder baut zuerst, wie Otto es lieber hat. F11 (#340) läuft unberührt. **(Empfehlung)**
2. Sofort bauen; Konflikte in `tiler.py`, `registry.py`, `sentinel-1-grd.yaml` löse ich beim Holen von `main`.
3. Erst nach ganz M5-30b.

## 9a. Antworten Otto (11.11.2026)

- **F1 = 2:** wie M3-18, kein nodata außerhalb der AOI-Form. Die Datendatei ist das Pixel-Fenster mit den Werten der
  Quelle; die übertragene Form steht nur in `mask.tif`. Das präzisiert Punkt 2 der Entscheidung.
- **F2 = 1, F3 = 1, F4 = 1, F5 = 1, F6 = 1, F7 = 1** jeweils nach Empfehlung: Zeilenversatz aus den Item-Zeiten über
  eine neue allgemeine Registry-Angabe; GCPs des Mosaiks als Vereinigung; Naht, die nicht passt: im Download eine
  Gruppe je Stück, im Job `422` mit Grund; gröbere Auflösung bleibt ohne Warp; `reprojection: false` mit Startprüfung;
  Version 0.5.2.
- **F8 = 1:** gebaut wird erst, wenn #335 und #341 auf `main` sind; dann `main` holen und umsetzen.
- **Auslegungen A1–A6 angenommen**, auch A3: Ergebnis-Layer von Sentinel-1 über die TPS (der 502 wird behoben).
- **Umfang:** ein PR mit Commits nach Teilen (§8) ist in Ordnung.
- **Nebenbefund** (§2, Annotation-Verweis auf die RFI-Annotation) gehört zu DS-05d; als eigener Punkt im PR und im
  Log festgehalten.

## 10. Nicht Teil dieser Aufgabe

- Kachel, Ansicht, Quicklook und Kachel-Mosaik (Punkt 5, F11, M5-30b).
- σ⁰-Kalibrierung und Geländekorrektur (DS-05d, `adr/0018` Teil C); erst danach georeferenzierte Ausgabe.
- Originale ganzer Szenen (unverändert, Link-Liste/ZIP).
- Andere Datensätze: für `geotransform` ändert sich nichts.

## 11. Grenzen und Abnahme

- Nur synthetische Fixtures, keine Anfrage an echte Quellen in Tests, keine neue Abhängigkeit.
- `CLAUDE.md`, `.github/`, `.claude/`, `CODEOWNERS` und das Backlog bleiben unverändert.
- Abnahme: Tests aus §6 grün; `ruff check backend`, `pytest`, `lint-imports` grün; Frontend-Lint und `tsc` grün,
  falls das Frontend berührt wird; vor „fertig“ `main` geholt.

## 12. Umsetzung (14.11.2026)

`main` mit #335, #340 und #341 geholt; keine Konflikte. Commits nach Teilen wie §8.

### 12.1 Was gebaut ist

- **Lesen und Raster** (`readers/cog.py`, `access/radar.py`): `CogReader.raw` ist die Datei im eigenen Pixelraster neben
  dem TPS-Warp; `RadarGrid` bildet die AOI (verdichtet auf höchstens 0,001°) über die inverse TPS in Pixel ab, gibt das
  umschließende Fenster und die Maske (`all_touched`) und verschiebt alle GCPs auf ein Fenster; `join_slices` hängt
  Slices am Versatz ihrer Zeilenzeiten untereinander und prüft jede Naht wie §4.6.
- **Registry** (`catalog/registry.py`, YAML): neues Pflichtfeld `line_times` (`first`/`last`, Namen von Item-Feldern,
  nur mit `gcp_tps`; Sentinel-1 `start_datetime`/`end_datetime`, alle anderen `null`); Startprüfung „`gcp_tps` ⇒
  `reprojection: false`“; Sentinel-1 `reprojection: false`. Die Prozessbeschreibung für das Panel verliert „Reproject“.
- **Zuschnitt und Export-Job** (`access/download.py`, `processing/export.py`): Pixel-Fenster je zusammenhängendem Lauf
  von Slices, Werte der Quelle unverändert, Form nur in `mask.tif` (F1 = 2), GCPs verschoben, kein CRS, COG über GDALs
  COG-Treiber; eine Gruppe, deren Slices nicht passen, wird zu einer Gruppe je Lauf (F4); Export bitgleich mit dem
  Zuschnitt. Textdatei: Zeile „Grid: radar geometry …“ statt „Resolution: native“, je Szene „Scene <id>: rows a-b,
  columns c-d (0-based, inclusive)“, je Teilung „Not joined into one file: <Grund>.“
- **Job, Runner, Statistik** (`processing/source.py`, `mosaic.py`, `core.py`): `RadarSource` liest im Pixelraster,
  das Mosaik eines Durchgangs hängt die Slices an; `result.tif`/`mask.tif` mit verschobenen GCPs, ohne CRS;
  `earthx:georeferencing: gcp_tps` statt `proj:code`/`gsd`; Flächenstatistik im selben Raster.
- **Rezept** (`processing/recipe.py`, `api/intake.py`): `inputs[].line_times` je Item, nur wo die Registry
  `line_times` nennt (A9).
- **Karte** (`api/result_tiles.py`): Ergebnisse werden gelesen, wie sie geschrieben sind (`as_written`): mit GCPs über
  die TPS, sonst über die Geotransformation; Ergebnis-Statistik im Pixelraster der Datei. Der 502 entfällt (A3).
- **Version:** `earthx.__version__` 0.5.2 (F7); `adr/0014` §15 Nachtrag DS-04d.

### 12.2 Auslegungen und Abweichungen (A7–A14 angenommen von Otto am 14.11.2026, A15 korrigiert, siehe §12.6)

- **A7 – F4 im Job:** Die Annahme öffnet keine Dateien; ob Slices passen, zeigen erst GCPs und Zeilenzahl der Dateien.
  Der Lauf schlägt deshalb mit `grid_mismatch` und dem Grund fehl („the slices of this pass do not join: a slice of
  the pass is missing“), nicht die Annahme mit `422`.
- **A8 – F5:** Die Frage ging von einem gröberen Faktor im Zuschnitt aus (F10c); den gibt es seit 03.11.2026 nicht
  mehr. Es bleibt die gemeinsame Auflösung einer Mehrband-Datei: in Radargeometrie nur die eigene Pixelgröße der
  Bänder, alles andere `422` vor dem Lesen. VV und VH einer Szene haben dieselbe, also ist bei Sentinel-1 nichts zu
  vergröbern.
- **A9 – Rezeptfeld:** `line_times` steht wie `footprints` (M4-11a) und `georeferencing` (DS-04a) auf der aufgelösten
  Seite und fehlt, wo es nicht gesetzt ist; `recipe_version` bleibt 2 (`adr/0014` §15 Nachtrag DS-04d).
- **A10 – Speicher:** GDALs COG-Treiber braucht beim Schreiben flächenabhängig mehr Speicher als `cog_translate`
  (gemessen in NM4-43c: +44/+59/+94 MB bei 2048²/4096²/8192² × 4 Bänder). Er gilt nur für Dateien in Radargeometrie;
  die Speichertests (Sentinel-2-artig) sind nicht betroffen.
- **A11 – Textdatei des Export-Jobs:** `api` schreibt sie bei der Annahme mit der Zeile „Grid: …“; die Fenster setzt
  der Lauf dahinter. Ein Lauf, den die AOI nicht erreicht, steht dort als eigene Zeile „Not covered by the AOI, left
  out“, im Zuschnitt in der Zeile der ausgelassenen Szenen.
- **A12 – Flächenstatistik auf gröberem Raster:** in Radargeometrie das Pixel in der Mitte jeder Zelle (nearest),
  Zeile für Zeile gelesen, damit ein grober Block nicht seine volle Auflösung im Speicher hält.
- **A13 – Mosaik-Kachel mit Operator:** bleibt für `gcp_tps` erlaubt (die Karte zeigt über TPS, Punkt 5); die Sperre
  ohne `reprojection` gilt nur für Datensätze mit Geotransformation.
- **A14 – Szene ohne Zeilenzeiten:** wird im Zuschnitt allein ein Lauf; im Job eines Durchgangs `grid_mismatch`.

- ~~**A15 – Export-Job, geteilte Gruppe:** Gruppenzeilen nach den Gruppen des Rezepts, die Aufteilung nur in den
  Szenenzeilen.~~ Korrigiert von Otto am 14.11.2026, siehe §12.6.

### 12.3 Review vor dem Fertigmelden

Ein Review des Diffs (Subagent `reviewer`) fand zwei Fehler, beide behoben und mit Test:

- Kachel, Vorschau und Statistik mit Operator auf Sentinel-1 gaben `500` (`processing/tile.py` nahm das CRS der
  Quelle, das es in Radargeometrie nicht gibt); die Kachel liest weiter über die TPS des Readers.
- Eine AOI links oder oberhalb des Rasters bekam ein Fenster von einer Pixelreihe statt `AoiOutsideItems`; damit
  hätte ein Job daneben ein leeres Ergebnis geliefert und ein geteilter Download den Teil ohne AOI nicht ausgelassen.

Dazu: Bänder, Typ, nodata und Skalierung einer `RadarSource` kommen aus der Datei, nicht aus dem Warp (der ohne nodata
einen Alpha-Kanal anhängt); gleiche Gitter vergleichen auch die GCPs; eine Textdatei ohne Zeile „Grid“ (Export, vor
DS-04d angenommen) bekommt sie angehängt statt eines Fehlers; eine Mehrband-Datei mit anderer gemeinsamer Auflösung
weist auch die Annahme des Export-Jobs mit `422` ab, nicht erst der Lauf.

### 12.4 Tests

Neu: `tests/earthx/access/test_radar.py` (Fenster, Maske, GCP-Verschiebung, Lesen, Nähte),
`tests/earthx/api/test_download_radar.py` (Route: ein Mosaik über die Naht, Werte außerhalb der Form bleiben,
Textdatei, Teilung bei fehlendem Slice, Abweisungen, kein CRS), `tests/earthx/processing/test_export_radar.py` (Export
bitgleich mit dem Zuschnitt, Teilung, Rezeptfeld und Hash, ungültige Zeilenzeiten),
`tests/earthx/processing/test_radar_job.py` (Mosaik-Job ohne CRS, gleiche Bytes zweier Läufe, Nähte, die nicht passen,
Pixel-Schritt, Flächenstatistik, Ergebnis-Kachel über TPS); dazu Registry, Annahme und Onboarding-Kette angepasst.
Fixture `tests/earthx/readers/mini_pass.py`: zwei synthetische Slices wie gemessen (§2).

**Prüfungen (14.11.2026):** voller `pytest`-Lauf aus der Repo-Wurzel 10904 bestanden, 25 übersprungen, 0
fehlgeschlagen; `ruff check backend` grün; `lint-imports` 16 Verträge eingehalten; Frontend `npm run lint`, `tsc -b`
und `vitest` (6643 Tests) grün; `main` geholt, nichts Neues seit dem Merge von #335 und #341.

### 12.6 Antworten Otto (14.11.2026) und Korrektur A15

A7–A14 angenommen. **A15 korrigiert:** Die Gruppenzeilen der Textdatei des Export-Jobs nennen die tatsächliche
Aufteilung nach dem Lauf, nicht die Gruppen des Rezepts. Umgesetzt: Der Lauf schreibt die Zeilen „Items: …“ bzw.
„Group N (exports/group-NN/): …“ an ihrer Stelle neu, nach denselben Regeln wie der Zuschnitt (eine Funktion
`crop_rules.group_lines` für beide); teilt sich ein Durchgang, stimmen sie mit dem Zuschnitt überein (Test
`test_a_missing_slice_splits_the_export_as_it_splits_the_crop`), sonst bleibt die eine Zeile „Items: …“.

### 12.7 Prüfanleitung für Otto (Windows, PowerShell, ohne Python)

Im Wurzelverzeichnis des Repos, Branch `claude/dreamy-shannon-uqn7ql`. In der Sitzung nicht geprüft: Image-Bau und
Browser (der Bau scheitert dort an der TLS-Kette des Proxys, `plans/m4/m4-16-lokaler-runner.md` §10).

**1. Stand holen und starten.** Neue Images, weil sich der Code geändert hat; `catalog-load` läuft mit und liest die
Registry neu.

```powershell
git fetch origin
git switch claude/dreamy-shannon-uqn7ql
git pull
docker compose up --build
```

In einem zweiten Fenster das Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Dann `http://localhost:5173` öffnen. Das Runner-Image (Schritt 3 und 6) einmal bauen, im Wurzelverzeichnis:

```powershell
docker build --target runner --build-arg "EARTHX_COMMIT=$(git rev-parse --short HEAD)" -t earthx-runner:0.5.2 backend
```

**2. „Reproject“ fehlt bei Sentinel-1.** Data catalogue → „Sentinel-1 GRD“, eine AOI zeichnen, suchen, eine Szene
wählen, im Panel „Processing“ die Knöpfe unter „Add step:“ ansehen: kein „Reproject and resample“. Gegenprobe mit
Sentinel-2 L2A: dort ist er da.

**3. Zuschnitt einer Szene.** Eine kleine AOI (einige km) in einer Szene, „Download“. Erwartet im ZIP:
`exports/vv_10m.tif` (der Name nennt Band und Pixelgröße, bei HH `hh_…`), die Maskendatei daneben, `ATTRIBUTION.txt` mit der Zeile „Grid: radar geometry of
the source scenes, not map-projected …“ und „Scene <id>: rows …, columns … (0-based, inclusive)“, keine Zeile
„Resolution: native“. Die Datei prüfen (das Runner-Image bringt `rio` mit; ZIP vorher nach `.\zip`
entpacken):

```powershell
docker run --rm --entrypoint rio -v "${PWD}\zip:/data:ro" earthx-runner:0.5.2 info /data/exports/vv_10m.tif
```

Erwartet: `"crs": null`, `"transform": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, …]` und ein Eintrag `"gcps"`. In der
Maskendatei dieselben GCPs; die Werte der Datendatei außerhalb der AOI-Form sind nicht 0 (F1 = 2).

**4. Mosaik aus zwei Slices eines Durchgangs.** Eine AOI über die Grenze zweier aufeinanderfolgender Szenen
derselben Bahn (ein Schritt der Zeitleiste), beide wählen, „Download“. Erwartet: **eine** Datendatei, in
`ATTRIBUTION.txt` zwei Zeilen „Scene …“, die zweite beginnt bei „rows 0-“. Im Bild keine Naht und kein Versatz an der
Grenze.

**5. Export-Job.** Dieselben zwei Slices mit einer größeren AOI (einige zehn km), bis der Dialog „Export as job“
anbietet; Job starten, ZIP herunterladen. Erwartet: dieselbe Form wie Schritt 4 (eine Datei, GCPs, kein CRS), in
`ATTRIBUTION.txt` die Zeile „Items: <beide Szenen>“ und die beiden Zeilen „Scene …“.

**6. Hash-Vergleich mit dem Runner.** Ein Raster-Job über die beiden Slices: im Panel „Processing“ unter „Add step:“
„Normalize“ auf VV, „Review“, „Start job“; fertig → „Download (ZIP)“. `recipe.json` aus dem ZIP des Jobs nach `.\in` legen, `result.tif` und `mask.tif` des Jobs nach `.\cloud`:

```powershell
docker run --rm --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges -v "${PWD}\in:/in:ro" -v "${PWD}\out:/out" earthx-runner:0.5.2 run /in/recipe.json
```

```powershell
$run = Get-ChildItem .\out -Directory | Sort-Object LastWriteTime | Select-Object -Last 1
Get-FileHash .\cloud\result.tif, "$($run.FullName)\result.tif", .\cloud\mask.tif, "$($run.FullName)\mask.tif"
```

Erwartet: je zwei gleiche SHA-256 für `result.tif` und für `mask.tif`; `provenance.json` im Ordner nennt
`0.5.2+<commit>`. `rio info` (wie in Schritt 3) auf `result.tif`: `"crs": null` und `"gcps"`.

**7. Ergebnis-Layer auf der Karte.** Der Job aus Schritt 6 erscheint im Layer-Manager. Erwartet: Er liegt auf der Karte
über den beiden Szenen, ohne Versatz an der Grenze der Slices; keine Fehlermeldung (früher `502`); Histogramm und
Bereich im Layer-Manager gefüllt.
