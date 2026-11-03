# ADR 0023 — Bandauswahl und Form beim Download eines Bildes

- **Status:** **Entwurf** (Claude, 2026-11-03, Aufgabe NM4-75, Stufe A). Die
  Auslegungen unter §3 gelten, bis Otto widerspricht.
- **Aufgabe:** NM4-75 (Otto, 2026-11-03): „Download eines Bildes mit Wahl der
  Bänder und der Form“. Kein Plan-Dokument, der Auftragstext steht im
  Draft-PR.
- **Betrifft:** `backend/earthx/access/band_export.py` (neu),
  `access/download.py`, `access/crop_rules.py`, `api/tiler.py`,
  `api/intake.py`, `processing/recipe.py`, `processing/plan.py`,
  `processing/export.py`; Frontend `DownloadDialog` und die Download-Module.

## 1. Entscheidung

Der Download einer Szene oder eines Zuschnitts nimmt eine Bandauswahl und eine
Form entgegen. Drei Formen:

| Form | Dateien | Umrechnung |
|---|---|---|
| `per_band` (Vorgabe) | je Band eine Datei, eigene Auflösung | keine |
| `per_resolution` | je vorkommender Auflösung eine mehrbandige Datei | keine |
| `multi_band` | eine mehrbandige Datei, gemeinsame Auflösung | feiner: `nearest`; gröber: Messwerte `average`, Klassenschicht `mode` |

Im ZIP liegen die Dateien in `exports/`, benannt nach Inhalt
(`B04_red_10m.tif`, `bands_20m.tif`), mehrbandige mit Bandbeschreibungen,
Skalierung und Offset als Dateitags. `exports/BANDS.txt` (Englisch) nennt je
Datei und Bandnummer Name, gängigen Namen, Wellenlänge, Auflösung (Quelle und
Export), Umrechnung, Datentyp, Skalierung, Offset, nodata und Einheit.

**Wege (Otto, Auftragstext 4):**

- Zuschnitt, alle Formen: synchron über `POST /collections/{dataset}/download`
  (`form`, `common_resolution`), bei zu großem Zuschnitt als Export-Job.
- Ganze Szene, `per_band`: im Browser aus der Quelle gestreamt (NM4-33), kein
  Byte über die Plattform.
- Ganze Szene, `per_resolution` und `multi_band`: als unsichtbarer Export-Job
  (wie der Index-Download #264), Größe vorher geschätzt.

## 2. Umsetzung

- **Ein Regelwerk, ein Lesemotor:** `access/band_export.py` hält Bandmetadaten
  (`BandMeta`), Dateipläne (`plan_files`), die Umrechnungsregel
  (`resampling_for`), den Blockleser (`StackReader`) und `BANDS.txt`. Der
  synchrone Zuschnitt (im Speicher) und der Export-Job (auf Platte) rufen
  dasselbe auf; ein Test hält ihre Dateien bitgleich.
- **Gitter:** wie bisher das des Zuschnitts (EPSG:4326 in der nativen Pixelgröße,
  `native_crop_grid`). Die Dateien einer Auflösung liegen damit auf genau dem
  Gitter der `per_band`-Dateien dieser Auflösung; eine gemeinsame Auflösung ist
  dasselbe Gitter mit größeren oder kleineren Pixeln (`pixel_scale`).
- **Rezept:** `CropOutput.layout` (`form`, `resolution_m`), bei `None` nicht im
  Dump, der Hash bisheriger Rezepte bleibt. Ein Export ohne Fläche ist erlaubt,
  wenn er ein `layout` trägt: `api` nimmt die Vereinigung der Footprints
  („ganze Szene“). Ohne `layout` bleibt das Verhalten (flache Dateien) wie
  zuvor.
- **Bandtabelle des Dialogs:** `POST /collections/{dataset}/bands` (Szenen im Body)
  liefert Bänder, Vorwahl, Auflösung und Metadaten aus Items und Registry. Das
  Frontend liest keine Quelleigenschaft (`eo:…`, P10, `test_frontend_no_dataset_literals`)
  und hält keine Namensliste.
- **Bandmetadaten:** aus den Items (`eo:bands`, `raster:bands`, `gsd`) und der
  Registry (Einheit, Klassenschicht = `mask.asset`). Der Job bekommt sie als
  Teil der `Attachments` von `api`, weil der Kern keine Items kennt.
- **Schätzung:** `export_outputs` plant je Datei; `resampling` der Schätzung
  nennt bei `multi_band` die umgerechneten Bänder und bei mehreren UTM-Zonen die
  umgerechneten Szenen (Warnung wie NM4-65 Teil 7). `method` kennt dafür
  `average` und `mixed` neben `nearest`.

## 3. Auslegungen (gelten, bis Otto widerspricht)

1. **Vorwahl „alle Spektralbänder und SCL“:** Spektralband = das Item nennt eine
   Mittenwellenlänge (`eo:bands.center_wavelength`); dazu die Klassenschicht der
   Registry. Hat ein Datensatz kein solches Band (DEM), ist alles vorgewählt.
   Nicht vorgewählt, aber wählbar: Bänder ohne Wellenlänge (aot, wvp, cloud,
   snow). Die Hilfsbilder (`visual`, `preview`) bleiben draußen.
2. **Ausgabe-CRS bleibt EPSG:4326** in allen Formen (das Gitter des bisherigen
   Zuschnitts); „keine Umrechnung“ meint die Auflösung und die Werte.
3. **Masken:** zu jeder Datendatei gehört wie bisher eine Maskendatei
   (`<Name>_mask.tif`), auch bei der ganzen Szene (Maske = Footprint).
4. **Auflösungsfaktor (1/2/4/10):** bleibt, gilt aber nur bei `per_band`; bei
   den anderen Formen ersetzt ihn die Wahl der Auflösung (422 sonst).
5. **Mehrbandige Dateien:** Datentyp ist der weiteste der Bänder (z. B. uint16
   neben uint8); nodata nur, wenn alle Bänder denselben Wert haben (sonst steht
   er je Band in `BANDS.txt`); Skalierung und Offset je Band.
6. **Quellen mit mehreren Bändern je Asset** (`visual`) und Zarr-Quellen sind
   nur in `per_band` möglich.
7. **Zuschnitt als Rezept:** `recipe.json` des synchronen Zuschnitts trägt das
   `layout` (`per_band` als Vorgabe); der Hash eines gespeicherten Rezepts ohne
   `layout` ist unverändert.

## 4. Verworfen

- **Raster-Job für die ganze Szene:** rechnet die Skalierung an (float32,
  physikalische Werte) und widerspricht „Werte unverändert, Skalierung in
  `BANDS.txt`“.
- **Eigener Jobtyp:** mehr Rezept-Fläche (Version, Hash, Schema) ohne Gewinn
  gegenüber `CropOutput.layout`.
- **Native UTM-Ausgabe:** würde das Gitter von dem des Zuschnitts trennen; nicht
  Teil dieser Aufgabe.

## 5. Offene Punkte für Otto

1. Soll die ganze Szene bei `per_resolution` und `multi_band` im Gitter der
   Quelle (UTM) statt in EPSG:4326 geschrieben werden? Das wäre ein eigener
   Schreibweg (Empfehlung: erst nach Nutzung entscheiden).
2. Dateien einer Szene größer als 5 GB (`MAX_JOB_BYTES`) werden vom Job
   abgelehnt, auch wenn der Browser sie bei `per_band` streamen kann.
