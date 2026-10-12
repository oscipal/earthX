# M4-24 — Weitere Resampling-Methoden für `reproject`

**Stand:** 12.10.2026, beauftragt von Otto.
**Stufe B:** Erst kommt der Plan mit Messung in den Draft-PR, Otto gibt ihn frei, dann folgt der Code.
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** Erst nach dem Merge von M4-21. Die Aufgabe zählt als Stufe-B-Session; gleichzeitig laufen höchstens zwei.
**Startsatz:** „Führe Aufgabe M4-24 aus `docs/plans/m4-24-resampling-methoden.md` aus.“

## 1. Anlass und Grundlage

- **M4-10, Entscheidung Otto vom 07.10.2026 (Log):** Resampling gibt es bisher nur mit `nearest`, `bilinear` und `cubic`, weil nur diese gemessen und gegen `adr/0014` §6.3 belegt sind.
- **Log vom 07.10.2026, Status „offen“:** Die Methoden `cubicspline`, `lanczos` und `average` folgen jeweils mit eigener Messung gegen §6.3. Weil sie das Ergebnis ändern, bekommen sie eine neue `op_version`.
- **Otto, 12.10.2026:** Er will die zusätzlichen Methoden. Neu dazu kommt `mode` für Klassendaten.
- **Weitere Grundlagen:**
  - `adr/0014`: §3.4 (Messaufbau Reprojektion), §5.2 (Parameter), §5.3 (Capabilities `reprojection` und `interpolation`), §5.5 (Faktoren der Schätzung), §6.3 (Toleranzen), §7.2 und §7.3 (Speicher).
  - Plan `m4-processing-kern.md`: M4-10 und M4-10b.

**Ziel:** Der Operator `reproject` bietet zusätzlich `average`, `mode`, `cubicspline` und `lanczos` an. Jede Methode ist gemessen und gegen eine Toleranz belegt, und jede hat einen Faktor in der Schätzung.

## 2. Plan im PR (vor jedem Produktivcode)

### 2.1 Stand der Technik, mit Quellen

- **GDAL-Dokumentation zu `gdalwarp -r`:** Wie behandeln `average` und `mode` Nodata, wie gewichten sie Pixelanteile, wie verhält sich `mode` bei float-Daten? Maßgeblich ist die GDAL-Version im Image.
- **Namen der Methoden:** in openEO `resample_spatial` und im rasterio-Enum `Resampling`. Die Parameter bleiben bei den Namen wie in openEO (`adr/0014` §5.2).
- **Bekannte Unterschiede zwischen ganzem `reproject` und blockweisem `WarpedVRT`:** Das betrifft besonders `average` und `mode`, die viele Quellpixel je Zielpixel lesen.

### 2.2 Messung [M], Aufbau wie `adr/0014` §3.4 und M4-10b

- **Daten:**
  - synthetisches DEM (float32),
  - synthetisches NDVI (float32),
  - für `mode` zusätzlich ein synthetisches Klassenraster (uint8, wenige Klassen, mit Nodata).
- **Was je neuer Methode gemessen wird:**
  - Vergleich ganz gegen blockweise: Anteil identischer Pixel, p99 und max |Δ|.
  - Vergleich 1 gegen 4 Threads, ob bitgleich.
  - Zeit je Megapixel, daraus der Faktor für §5.5.
  - Spitzenspeicher (`VmHWM`) im Aufbau von `test_memory_reproject.py`, bei 2048² und 4096², gegen die Grenze von 500 MB.
- **Zwei Fälle getrennt:** Ziel gröber als die Quelle (Vergröbern) und Ziel feiner als die Quelle.
- **Blockplan:** Er bleibt fest (`tolerance` 0,125, `warp_mem_limit` 64 MB, Blöcke 1024 px). Wenn eine Methode ihn ändern müsste, ist das eine Frage an Otto und keine Änderung im Alleingang.

### 2.3 Vorschlag für die Toleranzen

- Je Methode eine neue Zeile für `adr/0014` §6.3 (T2 gegen ein ganzes `reproject`), mit den Messwerten.
- Methoden, die keine sinnvolle Toleranz halten oder die Speichergrenze reißen, werden nicht aufgenommen. Das kommt mit Beleg in den Plan.

### 2.4 Fragen an Otto, je mit Optionen und Empfehlung

1. **Versionierung:** Bekommt der Operator die `op_version` 3? Nimmt er die Version 2 danach weiter an (die alten Methoden liefern dasselbe Ergebnis) oder nur noch 3 (K7, `422`)?
2. **Capabilities:** Welche neuen Methoden verlangen `interpolation`? Vorschlag zum Prüfen: alle außer `mode`; `mode` braucht wie `nearest` nur `reprojection`.
3. **`mode` auf float-Daten:** erlauben, abweisen oder nur warnen?
4. **`average` beim Verfeinern** (Ziel feiner als die Quelle): erlauben, abweisen oder warnen?
5. **Panel:** Liest das Frontend die Methoden aus dem Parameterschema von `/processing/processes`? Falls die Liste fest im Frontend steht: im Frontend ergänzen oder auf das Schema umstellen?

## 3. Umsetzung nach Freigabe

- **Operator:** `processing/operators/reproject.py` bekommt die erweiterte Methodenliste, die `op_version` und das Verhalten alter Versionen nach Ottos Antwort zu Frage 1, und die Capability-Regeln nach Frage 2.
- **Schätzung:** Faktoren je Methode aus der Messung.
- **Panel:** Die Methoden sind wählbar. Oberflächentexte nur auf Englisch.
- **Keine Vorbelegung im Panel:** Resampling bleibt im Panel ohne Vorbelegung und ohne Empfehlung (Otto, 12.10.2026, M4-13b zweite Fassung). Die Hilfetexte unter dem Feld erklären jede Methode in einem Satz (Englisch). Ein Beispiel: „average: mean of all source pixels per target pixel; for coarsening continuous data“.
- **Tests:**
  - Plausibilitätstest je neuer Methode gegen ein ganzes `reproject`, mit den Grenzen aus der neuen Zeile in §6.3.
  - T2 zweimal gerechnet ist bitgleich.
  - Speichertest 2048² und 4096² unter 500 MB für die speicherhungrigste neue Methode.
  - Abweisung ohne Capability.
  - Verhalten alter `op_version` nach Ottos Entscheidung.
  - Frontend-Test für die Auswahl.
- **Fixtures:** nur synthetisch.

## 4. Grenzen

- Geändert werden nur `reproject`, die Faktoren der Schätzung, die Tests und, falls nötig, die Methodenauswahl im Panel.
- Kein neuer Operator, keine Änderung an `band_math`.
- Keine neue Abhängigkeit ohne Frage an Otto.
- Die Modulgrenzen bleiben, wie sie sind (Import-Linter grün).
- Keine Anfragen an echte Quellen.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Dokumentation

- **`adr/0014`:** datierter Nachtrag als nächster freier Abschnitt nach §15d, mit den neuen Zeilen für §6.3 und den Faktoren für §5.5. Der Originaltext bleibt unverändert.
- **`docs/plans/m4-processing-kern.md`:** Zeile M4-24 in §3 (nach M4-21, Stufe B). Zeilenenden so lassen, wie die Datei sie dann hat.
- **`docs/ENTSCHEIDUNGSLOG.md`:**
  - Die Zeile vom 07.10.2026 „Weitere Resampling-Methoden für `reproject` nach Messung“ bekommt den Status „aufgenommen als M4-24 (2026-10-12)“.
  - Neue Zeilen für Ottos Antworten zu §2.4 und für die Umsetzung.

## 6. Abnahme

- Jede aufgenommene Methode hat:
  - eine Messung,
  - eine Zeile in §6.3,
  - einen Faktor in §5.5,
  - einen grünen Plausibilitätstest,
  - eine bitgleiche Wiederholung.
- Der Speichertest liegt unter 500 MB.
- Die Methoden sind im Panel wählbar.
- Alle vier Pflicht-Checks der CI sind grün.
- Vor „fertig“ ist main geholt.
