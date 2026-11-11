# M5-28 — Ein nodata für Ergebnisse, das nie ein echter Wert ist

**Stand:** 11.11.2026, freigegeben von Otto (Antworten in §9a), in Umsetzung.
**Stufe B.** Erst Plan mit Fragen, Code nach Freigabe; ein Draft-PR.
**Anlass:** Log 2026-10-12 („Festes nodata je Ganzzahltyp“, offen), `adr/0014` §15h und §15k („Kollision mit `nodata`“).
**Vorgabe Otto (09.11.2026):** Der nodata-Wert muss nicht für alle Datensätze gleich sein; er darf je Datensatz oder Band abweichen. Er fällt nie mit einem echten Wert zusammen und funktioniert in allen Wegen.

## 1. Anlass

Schreibt der Kern in einen Ganzzahltyp, kann ein gültiger Wert nach Runden und Klemmen (§15h) auf den nodata-Wert fallen, zum Beispiel 0,3 in `uint16` mit nodata 0. In der Datei gilt er dann als fehlend; die Statistik zählt ihn deshalb nicht (§15k), `valid_pixels` schon. Gesucht ist eine Regel für alle Wege, die Dateien schreiben: Job, Zuschnitt, Export, Mosaik.

Echte Werte, die nie nodata sein dürfen: 0 °C und 0 mm (Meteorologie), 0 m (Höhe), Klasse 0 nur dort, wo die Legende sie als „keine Daten“ führt.

## 2. Befund im Code (Stand `main`, 4440257)

Gelesen, wo nicht anders gesagt; [L] = in dieser Sitzung laufen lassen.

| Weg | Stelle | Datentyp der Datei | nodata heute | Problem |
|---|---|---|---|---|
| Job, Raster (auch Mosaik eines Überflugs, auch Statistik der AOI ohne Job) | `processing/core.py` `_nodata_for`, `_cast`, `write_pass` | `output.dtype` des Rezepts | Gleitkomma: NaN. Ganzzahl: das gemeinsame nodata der Bänder aus der Kette (`RasterMeta`), sonst `UnsupportedRecipe` | siehe A–E |
| Export-Job (`crop`) | `processing/export.py` `write` | Typ der Quelle | nodata der Quelle; ohne: kein Tag, Lücken mit **0** gefüllt | F |
| Zuschnitt, synchron | `access/download.py` (`_crop_*`, `_masked_array_to_cog_bytes`) | Typ der Quelle | wie Export | F |
| Bänder-Download (NM4-75) | `access/band_export.py` `StackReader`, `file_profile`, `write_blocks` | `numpy.result_type` der Bänder | gemeinsames nodata der Bänder; weichen sie ab: **kein Tag**, jedes Band mit seinem eigenen nodata gefüllt, sonst 0 | F, G |
| Kacheln, Vorschau | `api/tiler.py`, Leser | PNG mit Alpha | keins nötig | keins; nicht Teil der Aufgabe |

**A. Kollision nach Runden und Klemmen** (§15h, §15k). `_cast` rundet und klemmt auf `[min, max]` des Typs; danach wird nicht geprüft, ob ein gültiger Wert dem nodata gleicht. [L]: `0,3`, `−2,0`, `0,05` nach `uint16` geben je 0. Fälle mit heutigen Datensätzen:
- Sentinel-1 GRD (`uint16`, nodata 0) mit `reproject` `cubic` oder `lanczos` und Ausgabe `uint16`: Überschwinger an Kanten mit kleinen DN können unter 0,5 fallen und werden 0.
- Ein Wert über dem Typbereich wird auf `max` geklemmt; ist `max` das nodata, kollidiert er ebenso.

**B. nodata der Rohwerte nach Skalierung.** Skaliert der Kern (`applied_by_core`), setzt `_source_meta` den Typ auf `float32`, lässt aber das nodata der Rohwerte stehen. Sentinel-2 C1 L2A (`uint16`, nodata 0, Skalierung 0,0001 / −0,1) mit Ausgabe `uint16` bekommt nodata 0, und jede Reflexion unter 0,5 wird 0 — fast das ganze Bild. Das Panel bietet hier keinen Ganzzahltyp an (`processingDefaults.ts`, `scaled`), die API nimmt das Rezept aber an.

**C. nodata außerhalb des Typbereichs.** swissALTI3D (`float32`, nodata −9999) mit Ausgabe `uint16`: `_nodata_for` gibt −9999, rasterio weist das Profil ab ([L]: `ValueError: Given nodata value, -9999, is beyond the valid range of its data type, uint16`). Der Job scheitert erst beim Schreiben und nicht als `UnsupportedRecipe` mit Grund. Das Panel zeigt dazu keinen Hinweis (`integerNote` sieht ein gemeinsames nodata und schweigt).

**D. Ganzzahl nach kleinerer Ganzzahl läuft über.** `_cast` lässt Ganzzahl nach Ganzzahl unverändert (`astype(..., casting="unsafe")`, §15h „ändern sich nicht“). [L]: `uint16` → `uint8` gibt `256 → 0` (= nodata 0, Kollision), `300 → 44`, `65535 → 255`. Das ist ein Fehler über nodata hinaus: Werte springen. Das passiert, wenn die Kette nur auswählt oder maskiert (`select`, `mask`, `mask_values`, `reproject` `nearest`/`mode`) und der Ausgabetyp kleiner ist als der der Quelle.

**E. Abweisung ohne Not.** Ein Ganzzahltyp geht nur, wenn alle Bänder der Kette ein gemeinsames, endliches nodata tragen. Nach `band_math` und `normalize` (NaN) ist er deshalb immer verboten; ebenso für das Copernicus-DEM (kein nodata) und für Bänder mit unterschiedlichem nodata.

**F. Lücken ohne nodata.** Export, Zuschnitt und Bänder-Download behalten den Typ der Quelle und füllen Pixel, die kein Item deckt, mit dem nodata der Quelle, sonst mit 0 ohne Tag. Copernicus-DEM (`float32`, kein nodata, `readers/mini_dem.py`): eine Lücke im Mosaik (fehlende Kachel, Rand der Abdeckung) wird 0 m und ist von Meereshöhe nicht zu unterscheiden. Für Ganzzahl-Quellen ohne nodata gilt dasselbe; heute hat keiner der sechs Datensätze eine.

**G. Gestapelte Bänder mit verschiedenem nodata.** `band_export` schreibt dann keinen Tag (GeoTIFF kennt nur ein nodata je Datei, §4), füllt aber je Band dessen eigenes nodata. Die Datei sagt nicht, welche Werte fehlen. Dazu hebt `numpy.result_type` den Typ an (`uint8` + `uint16` → `uint16`), das nodata eines Bandes bleibt dabei gültig.

**Statistik:** `_written` vergleicht mit dem nodata der Datei und folgt ihr, wie §15k beschreibt. Mit der Regel unten gibt es keine Kollision mehr, und `valid_pixels` und Statistik zählen wieder dieselben Pixel.

## 3. Datensätze heute

Aus Fixtures und Plänen; nicht live geprüft.

| Datensatz | Typ | nodata der Datei | Skalierung | echte Werte, die nicht nodata sein dürfen |
|---|---|---|---|---|
| `sentinel-2-c1-l2a` | `uint16` | 0 | 0,0001 / −0,1 | DN ≥ 1; nach Skalierung auch Werte um 0 |
| `sentinel-1-grd` | `uint16` | 0 (`adr/0018` §3.1) | keine | DN ≥ 1 |
| `cop-dem-glo-30` | `float32` | **keins** (`mini_dem.py`, M3-11b) | keine | 0 m |
| `esa-worldcover-2020`, `-2021` | `uint8` | 0 (Legende: „No data“) | keine | Klassen 10–100 |
| `swissalti3d` | `float32` | −9999 (`mini_lv95.py`) | keine | Höhen der Schweiz |

Meteorologie gibt es noch nicht. Typische Fälle sind `float32` (dann NaN) oder `int16` mit Skalierung (CF-Packung); 0 °C und 0 mm sind dann skalierte Werte und fallen unter Regel R2.

## 4. Stand der Technik [P]

Gelesen am 10.11.2026 am Tag `v3.12.2` von GDAL (`https://raw.githubusercontent.com/OSGeo/gdal/v3.12.2/...`):

- **Ein nodata je GeoTIFF:** `doc/source/drivers/raster/gtiff.rst` Z. 464–471: „Note that all bands must use the same nodata value.“ Ein nodata je Band geht also nur mit einer Datei je Band oder über eine Maske.
- **Kollision vermeiden beim Warpen:** `alg/gdalwarpkernel.cpp` Z. 1476–1530, `AvoidNoData`: Trifft ein geschriebener gültiger Wert das Ziel-nodata, setzt GDAL ihn bei Ganzzahl um eins herunter, an der Untergrenze des Typs um eins hinauf; bei Gleitkomma auf die nächste darstellbare Zahl (`nextafter`). Einmal je Lauf kommt eine Warnung „Value … has been changed to … to avoid being treated as NoData“.
- **Feste nodata je Typ:** `swig/python/gdal-utils/osgeo_utils/gdal_calc.py` Z. 49–63, `DefaultNDVLookup`, genommen, wenn weder Aufruf noch Quelle eins nennen: `Byte` 255, `UInt16` 65535, `Int16` −32768, `UInt32` 4294967293, `Int32` −2147483647, `Float32` 3,402823466e38. Also ein Randwert des Typs, oben für vorzeichenlose, unten für vorzeichenbehaftete Typen.

## 5. Vorschlag: die Regel

Eine Funktion entscheidet das nodata einer Ausgabedatei (`processing/nodata.py`, rein, ohne I/O); Job, Export, Zuschnitt und Bänder-Download rufen sie auf.

- **R1 Gleitkomma:** NaN, in allen Wegen. Ein echter Messwert ist nie NaN. Neu ist das für Export, Zuschnitt und Bänder-Download einer Gleitkomma-Quelle **ohne** nodata (Copernicus-DEM): Lücken werden NaN statt 0. Eine Gleitkomma-Quelle **mit** nodata (swissALTI3D −9999) behält ihres, weil diese Wege die Werte der Quelle unverändert weitergeben.
- **R2 Ganzzahl im Job, nodata der Quelle:** Es gilt, wenn
  1. alle Bänder des Ergebnisses dasselbe endliche nodata der Quelle tragen,
  2. es im Wertebereich des Ausgabetyps liegt, und
  3. die Quelle ganzzahlig ist, und
  4. die Kette nur Werte der Quelle weitergibt: keine Skalierung durch den Kern, kein `band_math`, kein `normalize`, `reproject` nur mit `nearest` oder `mode`.

  Dann kann kein gültiger Wert gleich dem nodata sein, denn solche Pixel sind beim Lesen schon maskiert. Damit bleiben WorldCover 0 und Sentinel-1 0 bei reinem Auswählen, wie heute.
- **R3 Ganzzahl im Job, sonst ein Randwert:** vorzeichenlose Typen `max` (`uint8` 255, `uint16` 65535, `uint32` 4294967295), vorzeichenbehaftete `min` (`int16` −32768, `int32` −2147483648). Das ist die Seite von `gdal_calc.py`; 0 bleibt damit immer ein gültiger Wert (0 °C, 0 mm, 0 m). `uint32` und `int32` nehmen den echten Randwert und nicht die Werte von `gdal_calc.py`, weil der Tag als Text gespeichert wird und beide exakt lesbar sind.
- **R4 Schutz gegen Kollision, immer:** Nach Runden und Klemmen wird jeder gültige Wert, der das nodata trifft, um eins zur Mitte des Typs verschoben, wie GDAL `AvoidNoData` es tut (bei `max` → `max − 1`, bei `min` → `min + 1`, sonst −1). Bei einem Randwert als nodata heißt das: auf `[min, max − 1]` bzw. `[min + 1, max]` klemmen. Der Bericht des Laufs nennt die Zahl verschobener Pixel je Band (Frage 4). Danach sind `valid_pixels` und Statistik wieder gleich.
- **R5 Ganzzahl nach kleinerer Ganzzahl wird geklemmt, nicht übergelaufen** (Befund D; Frage 3). Damit ändert sich die Aussage „Ganzzahl nach Ganzzahl ändert sich nicht“ aus §15h.
- **R6 Export, Zuschnitt, Bänder-Download behalten die Werte der Quelle.** Sie bekommen das nodata der Quelle oder, nach R1, NaN. Für Ganzzahl-Quellen ohne nodata und für gestapelte Bänder mit verschiedenem nodata (Befund F, G) gibt es keinen freien Wert, ohne Werte der Quelle zu ändern; dafür Frage 2.
- **R7 Registry-Feld nur bei Bedarf** (Frage 5): Heute reicht die Regel für alle sechs Datensätze. Ein Feld je Datensatz oder Band kommt erst, wenn eine Quelle es braucht, etwa eine Ganzzahl-Quelle ohne nodata, die einen Wert als „fehlt“ dokumentiert.

**Was R2–R4 an den Fällen aus §2 ändern:**

| Fall | heute | mit der Regel |
|---|---|---|
| S1 GRD, `cubic`, `uint16` | nodata 0, Überschwinger werden 0 = fehlend | nodata 65535 (R3, weil `cubic` interpoliert), 0 bleibt gültig |
| S2 L2A skaliert, `uint16` | nodata 0, fast alles fehlend | nodata 65535 (R3); die Werte selbst werden 0 oder 1, das bleibt eine schlechte Wahl, die das Panel nicht anbietet |
| swissALTI3D, `uint16` | `ValueError` beim Schreiben | nodata 65535 (R3; R2 greift nicht, −9999 liegt außerhalb von `uint16` und die Quelle ist `float32`), negative Höhen werden 0 |
| WorldCover, `select`, `uint8` | nodata 0 | nodata 0 (R2), unverändert |
| `band_math`, `int16` | `UnsupportedRecipe` | nodata −32768 (R3); 0 bleibt gültig |
| DEM, Export | Lücke = 0 m, kein Tag | Lücke NaN, Tag NaN (R1) |

## 6. Was sich ändert, Version

- **Bytes:** Ein Job mit Ganzzahl-Ausgabe, bei dem R2 nicht greift, bekommt ein anderes nodata, also andere Bytes und andere Statistik. Jobs mit Gleitkomma-Ausgabe bleiben Byte für Byte gleich. Export und Zuschnitt einer Gleitkomma-Quelle ohne nodata tragen jetzt den Tag NaN, auch wo es keine Lücke gibt.
- **Version, wie bei M4-26 (§15h):** `earthx.__version__` im Block `engine` des Cache-Schlüssels (§4.5, K5) **0.5.0 → 0.5.1**. `recipe_version` und `op_version` bleiben, solange kein Feld ins Rezept kommt; ein Registry-Feld (R7), dessen Wert ins Rezept geht, bräuchte nach §4.3 eine neue `recipe_version` und einen eigenen Plan. Ergebnisse unter 0.5.0 bleiben unter ihrem alten Schlüssel stehen und werden nicht mehr getroffen. Weil Cloud und Runner dieselbe Version tragen müssen, braucht Ottos lokaler Hash-Vergleich ein neues Runner-Image `earthx-runner:0.5.1`.
- **Fragen statt Annahmen:** Passt 0.5.1 nicht (Frage 6), wird vor dem Code gefragt.

## 7. Umsetzung nach Freigabe

Ein Draft-PR, Richtwert unter 400 Zeilen ohne Tests. Reihenfolge der Commits:

1. `processing/nodata.py`: `output_nodata(dtype, bands, picks_only)` (R1–R3) und `avoid_nodata(values, valid, nodata)` (R4); Tests.
2. `processing/core.py`: `_nodata_for` ruft `output_nodata`, `_cast` klemmt Ganzzahl nach Ganzzahl (R5) und verschiebt Kollisionen (R4); `_written` bleibt. Ob die Kette „nur weitergibt“, sagt ein neues Klassenattribut am Operator (`keeps_values`, Vorgabe `False`; `select`, `mask`, `mask_values` `True`, `reproject` je Methode). Kein neues Feld im Rezept, kein neuer `op_version`.
3. `processing/export.py`, `access/download.py`, `access/band_export.py`: R1 und R6 (Antwort auf Frage 2).
4. Bericht des Laufs: Zahl verschobener Pixel (Antwort auf Frage 4).
5. Frontend `processingDefaults.ts`: Ganzzahltypen nach `band_math`/`normalize` anbieten, aber nicht empfehlen; `integerNote` sagt, welches nodata kommt (Antwort auf Frage 7).
6. Version 0.5.1, `adr/0014` Nachtrag §15 „M5-28“, Log-Zeilen.

## 8. Tests

- Je Typ `uint8`, `uint16`, `int16`, `uint32`, `int32`: R3 ergibt den Randwert; 0 bleibt gültig und wird gezählt.
- R2 greift für WorldCover-artige Fixtures (`select`, `nearest`) und **nicht** bei Skalierung, `bilinear`, `cubic`, `band_math`, `normalize`.
- Kollision: Werte, die auf das nodata runden oder klemmen (0,3 bei nodata 0 aus R2; 1e9 bei nodata 65535), landen auf dem Nachbarwert; `valid_pixels` und Statistik zählen gleich.
- swissALTI3D-artig (`float32`, −9999) nach `uint16`: läuft, nodata 65535, kein `ValueError`.
- `uint16` → `uint8` mit `select`: 256 und 300 werden beide 255 (geklemmt, R5; nodata 0 aus R2), nicht 0 und 44. Mit nodata 255 (R3) werden sie 254 (R4).
- Meteorologie und Höhe: 0,0 °C, 0 mm, 0 m in `float32` und `int16` bleiben gültig, in Job, Export und Zuschnitt.
- Export und Zuschnitt eines DEM-artigen Mosaiks mit Lücke: Lücke NaN, Tag NaN; ohne Lücke gleiche Werte wie vorher.
- Gleitkomma-Jobs: bestehende feste Bytes bzw. Hashes bleiben unverändert.
- Gegenprobe: Mit der alten Regel scheitern die Kollisions- und Überlauf-Tests.
- Fehlerfälle: unbekannter Typ, leere Bandliste, NaN als Quell-nodata bei Ganzzahl.

## 9. Fragen an Otto

**Frage 1 — Randwert bei Ganzzahl (R3).**
1. Vorzeichenlos `max`, vorzeichenbehaftet `min`, wie `gdal_calc.py`. **(Empfehlung)** 0 bleibt immer gültig.
2. Immer `max`, auch bei vorzeichenbehafteten Typen.
3. Immer 0, wo die Quelle keins hat. Widerspricht 0 °C, 0 mm, 0 m.

**Frage 2 — Ganzzahl-Quelle ohne nodata und gestapelte Bänder mit verschiedenem nodata in Export, Zuschnitt, Bänder-Download (Befund F, G).** Heute betrifft das keinen Datensatz.
1. Abweisen mit Grund (`422`), bis die Registry ein nodata nennt (R7); beim Bänder-Download stattdessen eine Datei je nodata. **(Empfehlung)** Keine Werte der Quelle ändern sich, und nichts Neues am Dateiformat.
2. Interne Maske der Datei (GDAL-Maskenband) statt nodata. Werte bleiben, braucht aber ZSTD statt DEFLATE (Nebenfund M3-18, Log 2026-09-24) und eine zweite Art Gültigkeit in Lesern und Viewer.
3. Randwert des Typs mit Verschiebung (R3, R4) wie im Job. Ändert im seltenen Fall einen Wert der Quelle um eins.

**Frage 3 — Ganzzahl nach kleinerer Ganzzahl (Befund D).**
1. Im selben PR klemmen statt überlaufen (R5). **(Empfehlung)** Es ist ein Fehler, und er trifft das nodata.
2. Eigene Aufgabe; hier nur R4.

**Frage 4 — Verschobene Pixel melden (R4).**
1. Zahl je Band im Bericht des Laufs und in `provenance.json`; keine Warnung im Log. **(Empfehlung)**
2. Nur zählen, nicht zeigen.
3. Ab einem Anteil (z. B. 1 %) den Job abweisen.

**Frage 5 — Registry-Feld (R7).**
1. Jetzt nicht; das Feld kommt mit dem ersten Datensatz, der es braucht. Die Onboarding-Prüfung (`adr/0031`) meldet eine Ganzzahl-Quelle ohne nodata als Punkt für Otto. **(Empfehlung)**
2. Jetzt ein optionales Feld `nodata` je Asset-Band, nur für Quellen ohne eigenes, mit Beleg; neue `recipe_version`.

**Frage 6 — Version.**
1. `earthx.__version__` 0.5.0 → 0.5.1, wie M4-26. **(Empfehlung)**
2. 0.5.0 → 0.6.0, weil Ganzzahl-Ergebnisse ein anderes nodata tragen.

**Frage 7 — Panel.**
1. Im selben PR: Ganzzahltypen nach `band_math`/`normalize` anbieten, nicht empfehlen; Hinweis nennt das kommende nodata. **(Empfehlung)**
2. Panel bleibt, wie es ist; nur die API nimmt mehr an.

## 9a. Antworten von Otto (11.11.2026)

Fragen 1–7 jeweils Option 1. Dazu:

- **F3:** Ein Überlauf wird auf den Wertebereich des Zieltyps geklemmt, wie M4-26 es für Gleitkomma tut.
- **F7:** Panel und Annahme weisen eine Ausgabe vorher mit Grund ab, wenn ihr nodata nicht in den Typ passt, zum Beispiel swissALTI3D −9999 nach `uint16`.

**Auslegung von F7 (Claude, gilt bis Otto widerspricht):** Trägt ein Band des Ergebnisses ein endliches nodata der Quelle, das außerhalb des Ganzzahl-Ausgabetyps liegt, weist der Kern das Rezept mit `UnsupportedRecipe` ab. Das gilt vor R2 und R3, auch wenn die Quelle Gleitkomma ist. Die Annahme antwortet dann `422`, bevor der Job in die Warteschlange geht, und das Panel bietet den Typ nicht an. Der Fall „swissALTI3D, `uint16`“ in der Tabelle von §5 wird damit eine Abweisung statt nodata 65535. NaN als nodata (nach `band_math`, `normalize`) gilt nicht als „passt nicht“; dafür greift R3.

**Auslegung von F2 beim Bänder-Download (Claude):** Die Form „Bänder nach Auflösung“ bekommt eine Datei je Auflösung **und** nodata. Die Form „eine Datei mit allen Bändern“ verspricht genau eine Datei; dort weist der Download Bänder mit verschiedenem nodata mit Grund ab.

**Voller `pytest`-Lauf zum Plan-Schritt (10.11.2026):** 9984 bestanden, 25 übersprungen (darunter `pwsh` nicht installiert), 0 fehlgeschlagen; `ruff check backend` grün.

## 10. Grenzen und Abnahme

- Nur synthetische Fixtures, keine Anfragen an echte Quellen, keine neue Abhängigkeit.
- `CLAUDE.md`, `.github/`, `.claude/`, `CODEOWNERS` bleiben unverändert. Das Backlog bleibt unverändert.
- Abnahme: Tests aus §8 grün; `ruff check backend`, `pytest`, `lint-imports` grün; Frontend-Lint und `tsc` grün, falls Frage 7 Option 1; vor „fertig“ `main` geholt.
