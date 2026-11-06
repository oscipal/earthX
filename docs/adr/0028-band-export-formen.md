# ADR 0028 — Bandauswahl und Form beim Download eines Bildes

- **Status:** **Entwurf** (Claude, 2026-11-03, Aufgabe NM4-75, Stufe A).
  Otto hat am 2026-11-03 zu [#284](https://github.com/oscipal/earthX/pull/284)
  geantwortet: Form-Frage nur bei gemischten Auflösungen (§1), Ausgabe in der
  Projektion der Quelle (§2, ändert das Verhalten des bisherigen Zuschnitts),
  Masken wie umgesetzt, die übrigen Auslegungen in §3 ok. Die Nummer 0023 bis
  0027 ist für M5 reserviert; dieser ADR trägt deshalb 0028.
- **Aufgabe:** NM4-75 (Otto, 2026-11-03): „Download eines Bildes mit Wahl der
  Bänder und der Form“. Kein Plan-Dokument, der Auftragstext steht im
  Draft-PR.
- **Betrifft:** `backend/earthx/access/band_export.py` (neu),
  `access/download.py`, `access/crop_rules.py`, `api/tiler.py`,
  `api/intake.py`, `processing/recipe.py`, `processing/plan.py`,
  `processing/export.py`; Frontend `DownloadDialog` und die Download-Module.

## 1. Entscheidung

Der Download einer Szene oder eines Zuschnitts nimmt eine Bandauswahl und eine
Form entgegen. **Die Form wird nur gefragt, wenn die gewählten Bänder
verschiedene Auflösungen haben** (Otto, 03.11.2026): Haben alle dieselbe
Auflösung (auch ein einzelnes Band), kommen sie als ein mehrbandiges GeoTIFF
(`per_resolution`, `bands_<res>m.tif`, Bandbeschreibungen gesetzt). Bei gemischten
Auflösungen gibt es drei Formen:

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
- **Gitter (Otto, 03.11.2026): die Projektion der Quelle, nicht EPSG:4326.**
  `crop_rules.source_crop_grid` legt das Gitter in das CRS der Szenen (UTM), in
  deren Pixelgröße und auf deren Pixelraster; die Ausdehnung ist die Hüllbox
  von AOI ∩ Footprints in diesem CRS, nach außen auf das Raster gerundet. Ein
  Band in der Auflösung der Quelle ist damit eine reine Kopie ihrer Pixel
  (getestet). Die Dateien einer Auflösung liegen auf genau dem Gitter der
  `per_band`-Dateien dieser Auflösung; eine gemeinsame Auflösung ist dasselbe
  Raster mit größeren oder kleineren Pixeln (`pixel_scale`, vom Ursprung der
  Quelle aus). Nur Szenen in einem anderen CRS als dem der Gruppe (dem, in dem
  die meisten liegen; `mosaic_order` legt diese zuerst) werden mit `nearest`
  auf das Gitter umgerechnet; die Warnung wie in NM4-65 Teil 7 und ein Vermerk
  in `BANDS.txt` nennen das. **Das ändert das bisherige Verhalten des
  Zuschnitts** (bisher EPSG:4326 in der nativen Pixelgröße, `native_crop_grid`):
  Dateien, Masken und `recipe.json` liegen jetzt im CRS der Quelle. Unverändert
  in EPSG:4326 bleiben der Export-Job ohne `layout` (gespeicherte Rezepte, Hash
  und Bytes bleiben) und Quellen ohne Raster-Datensatz (Zarr).
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
2. **Ausgabe-CRS:** entschieden (Otto, 03.11.2026), siehe §2 „Gitter“; hier
   stand zuerst die Auslegung EPSG:4326.
3. **Masken** (Otto: so lassen): zu jeder Datendatei gehört wie bisher eine
   Maskendatei (`<Name>_mask.tif`), auch bei der ganzen Szene (Maske = Footprint).
4. **Kein Auflösungsfaktor mehr** (Otto, Review 03.11.2026; ersetzt die Auslegung,
   der Faktor 1/2/4/10 bleibe bei „per band“): Der Dialog fragt nie nach einer
   gröberen Auflösung. Ein Export ist immer in der Auflösung der Quelle, bei
   „One multi-band file“ in der gewählten gemeinsamen Auflösung. Der Auftrag
   `POST …/download` trägt kein `resolution` mehr als Wahl: das Feld nimmt nur
   noch `1` an und lehnt jeden anderen Wert mit 422 ab (statt ihn still zu
   ignorieren). Die Größenprüfung rät bei einem zu großen Zuschnitt nicht mehr zu
   einem Faktor, sondern zu kleinerer Fläche, weniger Bändern oder einer
   gröberen gemeinsamen Auflösung. Entfallen sind der Dateiname mit `_2x` und die
   Zeile „Nx coarser than native“ in `ATTRIBUTION.txt`. Das Rezeptfeld
   `CropOutput.resolution_factor` bleibt (immer 1 in neuen Rezepten), alte Rezepte
   mit Faktor bleiben lesbar; der Export-Job lehnt einen Faktor ≠ 1 wie zuvor ab.
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
- **EPSG:4326 als Ausgabe** (die erste Auslegung): verworfen von Otto am
  03.11.2026; eine Umprojektion von UTM nach 4326 ändert die Pixel auch dort,
  wo „keine Umrechnung“ versprochen ist.

## 5. Grenzen

- Dateien einer Szene größer als 5 GB (`MAX_JOB_BYTES`) lehnt der Job ab, auch
  wo der Browser sie bei `per_band` streamen könnte (Otto: ok).
- Ein Zuschnitt über die Datumsgrenze oder mit einer Quelle, die gedreht
  (nicht nach Norden ausgerichtet) ist, wird abgelehnt (`source_crop_grid`).
