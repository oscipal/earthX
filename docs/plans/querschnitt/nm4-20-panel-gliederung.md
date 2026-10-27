# NM4-20 — Processing-Panel klarer gegliedert

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 20 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort mittel.
**Start:** nach dem Merge von UI-01 (ordnet Leisten und Panels neu). Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig. Nicht gleichzeitig mit NM4-07, NM4-10 oder NM4-14.
**Startsatz:** „Führe Aufgabe NM4-20 aus `docs/plans/querschnitt/nm4-20-panel-gliederung.md` aus.“

## 1. Anlass

Im Processing-Panel sind „Bands“, „Processing steps“, „Output“ und „Preview“ schwer auseinanderzuhalten.

## 2. Soll

- Die vier Bereiche sind deutlich voneinander abgesetzt (eigene Abschnitte mit Überschrift, Abstand, Trennung; ggf. einklappbar).
- Wenig Text: Erklärungen im Tooltip (NM4-22, UI-01 §4).

## 3. Offene Punkte (bei Unklarheit Frage an Otto)

- Gestaltung in Hell- und Dunkelmodus, Reihenfolge der Bereiche, schmale Fenster; Abstimmung mit UI-01 (größeres Fenster) und NM4-07/10/14.

## 4. Grenzen

- Nur Frontend.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Screenshots (Playwright) vorher/nachher im PR.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n) mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat, siehe Kopf des Backlogs).
- Vor „fertig“ ist main geholt.
