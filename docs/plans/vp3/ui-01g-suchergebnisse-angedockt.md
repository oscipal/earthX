# UI-01g — Suchergebnisse links angedockt

**Stand:** 26.10.2026, beauftragt von Otto. Ergänzt UI-01 (`docs/plans/vp3/ui-01-app-rahmen.md`); §6 dort gilt weiter.
**Stufe A:** direkt umsetzen, ein Draft-PR, nur Frontend.
**Modell:** Sonnet, Effort hoch.
**Start:** nach dem Merge von UI-01f. Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe UI-01g aus `docs/plans/vp3/ui-01g-suchergebnisse-angedockt.md` aus.“

## 1. Wunsch (Otto, 26.10.2026)

Die Suchergebnisse liegen wie Control-Menü, Layer-Manager und Processing-Manager **links angedockt** neben der Leiste aus UI-01c, nicht mehr frei bzw. an anderer Stelle.

## 2. Soll

- Viertes Symbol in der Leiste („Results“, mit Anzahl), gleiches Verhalten wie die anderen Panels: eines zur Zeit, angedockt, Tastatur und Screenreader wie in UI-01c.
- Nach einer Suche öffnet sich das Ergebnis-Panel von selbst.
- Alles, was die Ergebnisliste heute kann, bleibt erreichbar (Gruppen nach Überflug, „Select all“, „loaded (of N)“, Nachladen, Ansicht öffnen, Download-Dialog); der PR listet jede Funktion mit ihrem neuen Ort.

## 3. Offene Punkte (bei Unklarheit Frage an Otto)

- Breite des Panels (die Liste ist breiter als die Manager) und Verhalten auf schmalen Bildschirmen.
- Was geschieht mit dem Control-Menü nach der Suche (Panel wechselt zu „Results“)?
- Abstimmung mit NM4-09 (feste Gruppenköpfe) und NM4-17 („Clear search results“ öffnet wieder das Control-Menü): Die Struktur so bauen, dass beide danach einfach passen.

## 4. Grenzen

- Nur Frontend. Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: Symbol mit Anzahl, Panel öffnet nach der Suche, alle bisherigen Funktionen der Liste erreichbar, eines zur Zeit.
- Prüfung im echten Browser (Playwright), Hell/Dunkel, schmales Fenster; Prüfanleitung für Otto im PR.
- Alle vier Pflicht-Checks grün; Log-Zeile.
- Vor „fertig“ ist main geholt.
