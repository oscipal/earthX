# M4-25 — Kostenschätzung für Raster in geografischem CRS

**Stand:** 12.10.2026, beauftragt von Otto.
**Stufe A.** Direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort hoch.
**Start:** Nach dem Merge von M4-12a (#136) und M4-21. Die Aufgabe läuft neben Stufe-B-Sessions; sie berührt weder Frontend noch `reproject` selbst.
**Startsatz:** „Führe Aufgabe M4-25 aus `docs/plans/m4-25-schaetzung-geografisch.md` aus.“

## 1. Anlass

Den Fehler hat M4-12a gefunden (`plans/m4-12-mosaik-ueberflug.md` §12 Punkt 12, Log „Kostenschätzung für DEM mit reproject“ vom 12.10.2026, offen). Er besteht schon auf `main`.

- **Ursache:** `processing.plan._input_meta` stellt das Raster des ersten Durchgangs als `Affine(gsd, 0, 0, 0, -gsd, 0)` im CRS des Assets dar, wobei `gsd` in Metern angegeben ist. In einem geografischen CRS wie EPSG:4326 (`cop-dem-glo-30`) werden diese Meter als Grad gelesen. `reproject` bemisst daraus ein riesiges Zielraster und wirft `UnsupportedRecipe` (Seitenlänge über 32 768 px), oder es schätzt um Größenordnungen falsch.
- **Wo der Fehler auftritt:**
  - in `plan.estimate`, also in `jobs.submit`; dort wird eine Ausnahme zu einer `500`-Antwort,
  - in der Schätzroute `POST /processing/processes/recipe/estimate` (`500`),
  - bei der Annahme. Hier fängt `_accept` den Fehler seit M4-12a nur für die Deckelprüfung ab.
- **Im Lauf selbst tritt er nicht auf.** Der Kern ruft die Schätzung für einen Raster-Job nicht auf.
- **Auch in metrischen CRS ist die Box ungenau.** Sie hat die richtige Größe, liegt aber am falschen Ort. Die Genauigkeit liegt bei etwa 10 %.

## 2. Ziel

Die Schätzung bemisst das Eingaberaster in jedem CRS aus echter Lage und echter Pixelgröße. Ein Fehler in der Schätzung wird nie zu einer `500`-Antwort.

## 3. Umfang

1. **Eingaberaster aus der Lage:** `_input_meta` baut das Raster aus der AOI im CRS des Assets (die Bounds der transformierten AOI) und aus der Pixelgröße im CRS des Assets.
   - Quelle der Pixelgröße der Reihe nach: `proj:transform` am Asset oder Item, sonst `gsd` in Einheiten des CRS umgerechnet.
   - Für ein geografisches CRS gilt die Umrechnung an der Breite der AOI-Mitte. Für die Breite in Ost-West-Richtung wird das ausdrücklich so umgerechnet.
   - Welche Felder die drei Datensätze tatsächlich tragen, steht im PR, belegt mit den synthetischen Fixtures und den Adaptern.
2. **Wenn keine verlässliche Pixelgröße vorhanden ist:** Kein Raten. Gibt es weder `proj:transform` noch ein `gsd`, das sich umrechnen lässt, sagt die Schätzung das mit Grund. Annahme und Schätzroute antworten dann mit `422` und Grund, nicht mit `500`.
3. **Fehlerpfad:** Jede Ausnahme aus `plan.estimate` wird in `jobs.submit`, in der Schätzroute und bei der Annahme zu einer bestimmten Antwort:
   - `UnsupportedRecipe` wird `422`,
   - `JobTooLarge` wird `413`.

   Ein Test belegt: Keine Schätzung gibt eine `500`-Antwort.
4. **Metrische CRS:** Die Box liegt jetzt am richtigen Ort. Bestehende Schätzwerte für Sentinel-2 dürfen sich nur innerhalb der bisherigen Toleranz ändern. Der Test `test_a_metric_asset_is_estimated_within_a_fifth` bleibt grün oder wird enger.

## 4. Tests

- Die `strict`-`xfail`-Tests aus M4-12a werden grün. Ihre Markierung wird entfernt:
  - `test_plan.py::TestTheEstimateOnAGeographicGrid`
  - `test_processing_route.py::TestAnOrderOnAGeographicGrid`
- DEM-Kachel synthetisch (EPSG:4326, 1″) mit `reproject` nach EPSG:3035 und 30 m: Die geschätzte Zielgröße weicht höchstens 20 % vom tatsächlichen Lauf auf derselben synthetischen Datei ab. Das gilt für AOIs von 0,01° bis 1,0°.
- Die Grenze von 32 768 px greift nur, wenn das echte Zielraster sie überschreitet.
- Ein Asset ohne verlässliche Pixelgröße ergibt `422` mit Grund, sowohl in der Schätzroute als auch bei der Annahme.
- Gegenprobe: Mit der alten `_input_meta` scheitern die neuen Tests.

## 5. Grenzen

- Keine Änderung an `reproject`, am Blockplan oder an der `op_version`.
- Keine neue Abhängigkeit. `pyproj` und `shapely` sind schon vorhanden; ist das nicht der Fall, ist das eine Frage an Otto.
- Modulgrenzen bleiben unverändert.
- Keine Anfragen an echte Quellen. Nur synthetische Fixtures.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 6. Doku

- Log-Zeile vom 12.10.2026 „Kostenschätzung für DEM mit reproject“: Status auf „erledigt mit M4-25“ setzen und eine Zeile zur Umsetzung ergänzen.
- `docs/plans/m4-processing-kern.md` §3: Zeile M4-25 ergänzen. Die Zeilenenden so lassen, wie die Datei sie dann hat.
- `adr/0014` §5.5: datierter Nachtrag, falls sich die Rechnung der Schätzung in der Sache ändert.

## 7. Abnahme

- Die Tests aus §4 sind grün.
- Alle vier Pflicht-Checks der CI sind grün.
- Die Prüfanleitung für Otto (PowerShell, `${…}` in Zeichenketten) im PR zeigt:
  - eine Schätzung für `cop-dem-glo-30` mit `reproject` nach EPSG:3035 und 30 m, mit plausibler Pixelzahl,
  - einen danach erfolgreichen Job.
- Vor „fertig“ ist main geholt.
