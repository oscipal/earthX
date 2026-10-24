# NM4-09 — Feste Gruppenköpfe in den Suchergebnissen

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 9 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort mittel.
**Start:** nach dem Merge von UI-01 (ordnet Leisten und Panels neu). Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-09 aus `docs/plans/querschnitt/nm4-09-feste-gruppenkoepfe.md` aus.“

## 1. Anlass

Bei mehreren Ergebnissen je Gruppe scrollt der Gruppenkopf aus dem Bild; man verliert, zu welchem Überflug die Einträge gehören.

## 2. Soll

- Beim Scrollen bleibt der Kopf der aktuellen Gruppe oben stehen, solange Einträge dieser Gruppe sichtbar sind; der Kopf der nächsten Gruppe schiebt ihn hinaus („sticky header“).
- Gilt mit allem, was im Kopf steht: Name/Datum der Gruppe, Anzahl („loaded (of N)“), „Select all“ der Gruppe (M4-29), Auf- und Zuklappen.

## 3. Offene Punkte (bei Unklarheit Frage an Otto)

- Der Kopf verdeckt keinen Eintrag; das Nachladen weiterer Treffer am Listenende greift weiter; Tastatur und Screenreader.

## 4. Grenzen

- Nur Frontend.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Test: Kopf bleibt stehen und wird vom nächsten abgelöst (Playwright mit Scrollen).
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.
