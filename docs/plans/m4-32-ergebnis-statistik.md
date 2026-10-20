# M4-32 — Statistik je Ergebnis als Vorgabe für die Farbskala

**Stand:** 20.10.2026, beauftragt von Otto. Die Aufgabe kommt vor der M4-Abnahme.
**Stufe B:** Erst kommt der Plan im Draft-PR, Otto gibt ihn frei, dann folgt der Code. Der Grund: Die Aufgabe ändert Ergebnis-Bytes, betrifft also die Version, und sie berührt Rechenzeit und Bitgleichheit.
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** Nach dem Merge von M4-13c-5 (#166).
**Startsatz:** „Führe Aufgabe M4-32 aus `docs/plans/m4-32-ergebnis-statistik.md` aus.“

## 1. Anlass

M4-13c-5 zeigt Job-Ergebnisse als Layer. Jedes Gleitkomma-Ergebnis wird dabei mit dem Wertebereich des Panels gezeichnet (−1 bis 1, `rdylgn`). Für NDVI passt das. Ein DEM nach Reproject erscheint dagegen einfarbig, eine Reflexion dunkel.

**Otto (20.10.2026):** Das soll vor der M4-Abnahme behoben sein.

## 2. Ziel

- Jedes Raster-Ergebnis trägt eine kleine Statistik je Band: min, max, Mittelwert, 2- und 98-Perzentil, Anteil gültiger Pixel.
- Karte und Panel nehmen sie als Vorgabe für die Farbskala (2–98 %). Der Nutzer kann sie wie bisher von Hand ändern.

## 3. Im Plan mit Optionen, Empfehlung und Quellen klären

1. **Berechnung:**
   - Im Kern während der Blockschleife, ohne zweiten Lesedurchgang.
   - Min, max und Mittelwert sind exakt.
   - Perzentile über ein festes Histogramm oder einen anderen deterministischen Weg. Stand der Technik mit Quellen: GDAL `ComputeStatistics` und `GetHistogram`, rio-tiler `statistics`, übliche Verfahren für Perzentile auf Datenströmen.
   - Das Ergebnis muss bitgleich sein: zweimal gerechnet und Cloud gegen Runner (`adr/0014` §6.3).
2. **Ablage:**
   - (a) als Metadaten in `result.tif` (GDAL-Tags `STATISTICS_*`, dazu Perzentile), lesbar für den `tiler` ohne Datenbank, oder
   - (b) im Ergebnisdokument bzw. im STAC-Item des Ergebnisses (`raster:bands` `statistics`), oder
   - beides.

   Der Plan klärt auch, wie Frontend und `tiler` an die Werte kommen.
3. **Kosten:** Messung der Zusatzzeit und des Spitzenspeichers bei 4096² (Grenze 500 MB, `VmHWM`). Der Faktor in der Schätzung ändert sich nur, wenn die Messung es verlangt.
4. **Version:** Ändern sich die Bytes von `result.tif` durch die Tags, muss der Cache-Schlüssel das abbilden (`earthx.__version__`, wie bei M4-26). Bestehende gecachte Ergebnisse ohne Statistik: Das Frontend fällt auf den heutigen Bereich zurück.
5. **Vorgabe im Frontend:**
   - 2–98 % für Gleitkomma.
   - Ganzzahl unverändert.
   - Colormap-Vorgabe je Ergebnis: einfarbig-graue Skala oder `viridis` für unbekannte Größen, `rdylgn` nur bei NDVI-artigen Ausdrücken. Der Plan schlägt die Regel vor.
   - Die T1-Vorschau (Band math) bleibt bei ihrem bisherigen Verhalten, außer der Plan begründet etwas anderes.
6. **Runner:** Der Runner schreibt dieselbe Statistik, denn derselbe Kern liefert dieselben Bytes.

## 4. Grenzen

- Der Worker-Kern bleibt zustandslos. Es gibt keine Datenbank, keinen Objektspeicher und kein `gateway` im Kern.
- Keine neue Abhängigkeit ohne Frage an Otto.
- Oberflächentexte nur auf Englisch.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- **Tests:**
  - Statistik gegen eine unabhängige Rechnung auf synthetischen Rastern: Gleitkomma mit NaN, Ganzzahl mit nodata, DEM-artig, NDVI-artig.
  - Zweimal gerechnet bitgleich.
  - Runner gleich Kern.
  - Speichertest unter 500 MB.
  - Das Frontend nimmt die Vorgabe aus der Statistik und fällt ohne Statistik zurück.
  - Gegenprobe: Mit dem alten Code scheitern die neuen Tests.
- **Prüfanleitung für Otto:**
  - DEM-Reproject-Job: Das Ergebnis erscheint auf der Karte mit sichtbarem Relief.
  - NDVI-Job: Das Ergebnis erscheint wie bisher.
- Alle vier Pflicht-Checks der CI sind grün.
- **Doku:**
  - Nachtrag in `adr/0014`, falls die Bytes des Ergebnisses oder §6.3 berührt sind.
  - Log-Zeilen.
  - Zeile M4-32 in `docs/plans/m4-processing-kern.md` §3.
- Vor „fertig“ ist main geholt.
