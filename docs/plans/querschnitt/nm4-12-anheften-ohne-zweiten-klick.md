# NM4-12 — Anheften ohne zweiten Klick

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 12 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort mittel.
**Start:** Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-12 aus `docs/plans/querschnitt/nm4-12-anheften-ohne-zweiten-klick.md` aus.“

## 1. Anlass

Seit M4-17c weist „Add to layers“ eine Teilauswahl ab, deren Mosaik noch lädt („The mosaic of this time step is still loading — add it to the layers in a moment.“); erst ein zweiter Klick heftet an.

## 2. Soll

- Der Knopf zeigt „Loading…“ und heftet den Layer automatisch an, sobald das TileJSON da ist.
- Bei einem Fehler bleibt die bestehende Meldung; ein späterer Erfolg räumt sie weg.
- Ein zweiter Klick während des Ladens erzeugt keinen zweiten Layer.

## 3. Offene Punkte (bei Unklarheit Frage an Otto)

- Was passiert, wenn der Nutzer die Ansicht schließt oder die Auswahl ändert, während das Mosaik lädt? Vorschlag: Anheften verwerfen, ohne Meldung.

## 4. Grenzen

- Nur Frontend.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Test mit verzögertem TileJSON, der am heutigen Code scheitert; Doppelklick ergibt einen Layer.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n) mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat, siehe Kopf des Backlogs).
- Vor „fertig“ ist main geholt.
