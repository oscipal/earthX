# NM4-01 — Jahr in der Copernicus-Attribution

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 1; Reihenfolge laut Log vom 24.10.2026: Stufe A neben UI-01).
**Stufe A:** direkt umsetzen, ein Draft-PR. Hält die Session nach der Recherche (§3 Punkt 1) eine Auslegung für unsicher, legt sie sie Otto als Frage vor, bevor sie Code ändert.
**Modell:** Sonnet, Effort mittel.
**Start:** nach dem Merge von DOC-01. Läuft neben UI-01 (Schwerpunkt Backend). Wer als Zweiter fertig wird, holt main.
**Startsatz:** „Führe Aufgabe NM4-01 aus `docs/plans/querschnitt/nm4-01-attribution-jahr.md` aus.“

## 1. Befund

- Am 20.10.2026 stand in `provenance.json` des Runners „Contains modified Copernicus Sentinel data 2026“; die Szene ist vom 29.07.2025.
- Vermutung: Das Jahr kommt aus dem aktuellen Datum statt aus den Eingaben. Die Session prüft das am Code und nennt die Stelle(n).

## 2. Wortlaut laut Lizenz [P]

Die Copernicus Sentinel data licence (rev. 1) verlangt bei veränderten Daten den Hinweis „Contains modified Copernicus Sentinel data [Year]“, bei unveränderten „Copernicus Sentinel data [Year]“. Was „[Year]“ meint, sagt die Seite nicht.
Quelle: https://ewds.climate.copernicus.eu/licences/ec-sentinel

## 3. Umfang

1. **Recherche mit Quellen** (Primärdokumente: Sentinel Data Legal Notice der ESA, Copernicus-Lizenz, ggf. Leitfäden von ESA/EU zur Attribution): Ist „[Year]“ das Jahr der Aufnahme, der Prozessierung oder der Veröffentlichung? Wie schreibt man mehrere Jahre? Ergebnis mit Zitat im PR. Ohne klare Quelle: Frage an Otto mit Empfehlung (Vorschlag: Jahr der Aufnahme, bei mehreren Jahren als Spanne „2024–2025“).
2. **Eine Stelle:** Der Text entsteht an genau einer Stelle aus einer Vorlage je Datensatz in der Registry (Platzhalter für das Jahr), nie aus datensatzspezifischem Code. Datensätze ohne Jahr im Text (etwa das Copernicus DEM mit festem Wortlaut) bleiben unverändert; die Session prüft deren Wortlaut gegen die jeweilige Lizenz und nennt ihn im PR.
3. **Jahr aus den Eingaben:** aus dem Aufnahmedatum der Items des Auftrags (`datetime` bzw. `start_datetime`/`end_datetime`), nie aus der Uhr. Bei einem Mosaik oder Batch die Spanne über alle Eingaben.
4. **Alle Ausgänge**, mit Test je Ausgang:
   - Zuschnitt (synchron) und Export-Job: `ATTRIBUTION.txt`, `citation.bib`;
   - Raster-Job: `provenance.attribution` in `recipe.json` und im Job-ZIP (Sollliste M4-30);
   - Runner: übernimmt die Attribution aus der Eingabe (M4-16, §3.4) – Test, dass das Jahr dort richtig ankommt;
   - Linkliste der Originale (M4-11b-2);
   - Ergebnisdokument der API, falls es die Attribution trägt.
5. **Hash und Cache:** Die Attribution steht in `provenance`, nicht im gehashten Kern (`adr/0014` §4.5). Die Session belegt, dass sich kein Rezept-Hash ändert, und klärt, ob gecachte Ergebnisse beim Abruf die neue Attribution bekommen (sie wird beim Abruf gebaut) oder die alte behalten.

## 4. Grenzen

- Keine neue Abhängigkeit. Keine Koordinaten, IDs oder Hashes in Logs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: Szene von 2025 ergibt „2025“; Eingaben aus 2024 und 2025 ergeben die Spanne; ein Lauf am 1. Januar ändert nichts (Uhr injiziert); Datensatz ohne Jahr unverändert. Gegenprobe: Mit dem alten Code scheitern die Tests.
- Recherche mit Zitat im PR.
- Prüfanleitung für Otto (PowerShell): Zuschnitt und Job-ZIP einer Szene aus 2025 herunterladen, Jahr in `ATTRIBUTION.txt`, `citation.bib` und `recipe.json` prüfen.
- Alle vier Pflicht-Checks grün; Log-Zeile; Nachtrag in `adr/0014`, falls `provenance` berührt ist.
- Vor „fertig“ ist main geholt.
