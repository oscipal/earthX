# NM4-17 — „Clear all“ wird „Clear search results“

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 17 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort mittel.
**Start:** nach dem Merge von UI-01 (ordnet Leisten und Panels neu). Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-17 aus `docs/plans/querschnitt/nm4-17-clear-search-results.md` aus.“

## 1. Anlass

Der Knopf „Clear all“ in den Suchergebnissen löscht heute mehr als nur die Ergebnisse.

## 2. Soll

- Der Knopf heißt „Clear search results“ und löscht nur die Ergebnisliste. Danach öffnet sich wieder das Control-Panel.
- Alle Sucheinstellungen bleiben: AOI, Zeitraum, Datensatzwahl, Filter (etwa Wolkenbedeckung). Ein neuer Klick auf „Search“ sucht mit denselben Einstellungen.

## 3. Offene Punkte (bei Unklarheit Frage an Otto)

- Angeheftete Layer, offene Ansicht (Mosaik, M4-17) und Jobs: Vorschlag – Layer und Jobs bleiben, die offene Ansicht schließt.
- Wo setzt man AOI und Einstellungen künftig zurück? Eigener Knopf im Control-Panel, falls es keinen gibt.

## 4. Grenzen

- Nur Frontend.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Test: Nach dem Löschen sind alle Einstellungen erhalten, die Liste ist leer, das Control-Panel offen.
- Gegenprobe: Mit dem alten Code scheitert der Test.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.
