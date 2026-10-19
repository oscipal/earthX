# M4-30 — ZIP eines Processing-Jobs: AOI und Attribution ergänzen

**Stand:** 19.10.2026, beauftragt von Otto.
**Stufe A.** Direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort mittel.
**Start:** Sofort. Die Aufgabe ist nur Backend und läuft neben den Frontend-Sessions.
**Startsatz:** „Führe Aufgabe M4-30 aus `docs/plans/m4-30-job-zip-vollstaendig.md` aus.“

## 1. Befund (Otto, lokal, 19.10.2026)

Das ZIP eines Processing-Jobs, etwa NDVI aus M4-11b-1, enthält nur `result.tif`, `mask.tif`, `recipe.json` und `citation.bib`.

Der Zuschnitt-ZIP (M3-18, M4-14) und das ZIP des Export-Jobs (M4-11a) enthalten dagegen auch die Hinweisdateien, darunter die Attribution und die AOI. Im Job-ZIP fehlen also:
- **Attribution.** Die Lizenz verlangt sie, etwa „Contains modified Copernicus Sentinel data …“. Ohne sie gibt die Plattform Daten ohne die geforderte Angabe weiter.
- **AOI als eigene Datei.** Sie steht zwar in `recipe.json`, als GeoJSON lässt sie sich aber direkt in GIS-Programmen öffnen.

**Ursache:** Der Zusatz `m4-zusaetze-2026-10-12.md` §1 hat nur vier Dateien genannt. Das war ein Fehler im Zusatz, nicht in der Umsetzung.

## 2. Umfang

1. **Gleiche Dateien wie beim Zuschnitt.** Das Job-ZIP enthält dieselben Hinweisdateien wie das Zuschnitt- und das Export-ZIP: Attribution und AOI, mit denselben Dateinamen und demselben Inhalt.
   - Erzeugt werden sie an genau einer Stelle, von der Funktion, die schon Zuschnitt und Export verwenden. Es gibt keine zweite Fassung.
   - Am Code prüfen und im PR nennen, wie die Dateien heute heißen und wer sie baut.
2. **Bei „Whole scene“ ohne `aoi`** ist die AOI-Datei die Vereinigung der Footprints aus dem Rezept (M4-12a). Im PR ist das als solches gekennzeichnet, etwa über eine Eigenschaft im GeoJSON.
3. **Erzeugt beim Download.** Wie `recipe.json` erzeugt `api` beide Dateien je Job beim Download (M4-08b F4, M4-11b-1). Sie werden nicht im Objektspeicher abgelegt, weil ein Ergebnis zwischen Aufträgen geteilt wird.
4. **Fortsetzen und ETag.** Der Inhalt des ZIP ändert sich, deshalb ändert sich auch der ETag (M4-11b-1). Ein vor dem Update begonnener Download wird nicht fortgesetzt, sondern startet neu. Im PR mit Test belegen.
5. **Einzellinks:** Ob es für die zwei Dateien eigene Einzellinks wie bei `recipe.json` gibt, entscheidet die Session nach dem bestehenden Muster und nennt es im PR.

## 3. Tests und Abnahme

- Test: Das Job-ZIP enthält genau die Dateien des Zuschnitt-ZIP plus `result.tif` und `mask.tif`. Der Test vergleicht gegen die Liste, die der Zuschnitt verwendet, nicht gegen eine zweite feste Liste.
- Test: Der Attributionstext stimmt mit der Registry überein; die AOI-Datei ist gültiges GeoJSON und gleich der AOI im Rezept.
- Test für „Whole scene“ (Vereinigung der Footprints) und für einen Download, der nach dem Update fortgesetzt werden soll.
- **Gegenprobe:** Ohne die Ergänzung scheitern die neuen Tests.
- Die Prüfanleitung für Otto (PowerShell) im PR: NDVI-Job, ZIP laden, entpacken, sechs Dateien sehen.
- Alle vier Pflicht-Checks der CI sind grün.
- **Doku:**
  - Log-Zeile mit dem Befund, Verweis auf `m4-zusaetze-2026-10-12.md` §1. Dort wird ein Satz ergänzt: „ergänzt durch M4-30: Attribution und AOI“.
  - Zeile M4-30 in `docs/plans/m4-processing-kern.md` §3.
- Vor „fertig“ ist main geholt.

## 4. Grenzen

- Nur Backend und Doku.
- Keine Änderung am Zuschnitt- oder Export-ZIP, außer die gemeinsame Funktion muss dafür herausgezogen werden. Deren Ergebnis bleibt bytegleich, belegt mit einem Test.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.
