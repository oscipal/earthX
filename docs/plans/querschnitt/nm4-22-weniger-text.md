# NM4-22 — Weniger Text in der Oberfläche

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 22 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort mittel.
**Start:** nach dem Merge von UI-01 (ordnet Leisten und Panels neu). Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig. Kann mit NM4-20 zusammen laufen, wenn beide nicht dieselben Dateien ändern; sonst nacheinander.
**Startsatz:** „Führe Aufgabe NM4-22 aus `docs/plans/querschnitt/nm4-22-weniger-text.md` aus.“

## 1. Anlass

Otto möchte generell weniger Text in der Web-App (24.10.2026).

## 2. Soll

- Erklärungen, Hinweise und Gründe stehen im Tooltip (Hover und Tastaturfokus, für Screenreader erreichbar), nicht als Absatz unter Knöpfen oder Feldern – wie bei „Share processing“ (M4-19e).
- Sichtbar bleiben nur Beschriftungen, Werte, Fehlermeldungen mit Handlungsbedarf und Pflichtangaben (Attribution, Lizenz, Datenschutzhinweis).

## 3. Umfang

- Durchgang durch Panel, Suchergebnisse, Layer-Manager, Control-Panel, Dialoge; Liste der gekürzten bzw. verschobenen Texte im PR.
- Gesperrte Knöpfe: Tooltip muss trotzdem erscheinen (gesperrte Elemente lösen oft kein Hover aus).

## 4. Grenzen

- Nur Frontend.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: verschobene Texte sind im Tooltip erreichbar (Rolle/aria); Screenshots vorher/nachher.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n) mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat, siehe Kopf des Backlogs).
- Vor „fertig“ ist main geholt.
