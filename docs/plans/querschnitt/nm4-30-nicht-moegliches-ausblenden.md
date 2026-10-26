# NM4-30 — Nicht Mögliches ausblenden statt ausgrauen

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 30 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort mittel.
**Start:** nach dem Merge von UI-01 (ordnet Leisten und Panels neu). Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-30 aus `docs/plans/querschnitt/nm4-30-nicht-moegliches-ausblenden.md` aus.“

## 1. Anlass

Otto (26.10.2026): Ist eine Processing-Möglichkeit für einen Datensatz oder Layer nicht möglich, soll ihr Knopf gar nicht erscheinen, nicht nur ausgegraut sein. Heute zeigt das Panel etwa „Mask: this dataset has no classification layer to read.“ beim DEM.

## 2. Soll

- **Ausblenden**, wenn etwas für den Datensatz bzw. Layer grundsätzlich nicht geht (Fähigkeit fehlt laut Registry/`applicable`): etwa `mask` beim DEM, Processing auf Ergebnis-Layern (bis NM4-05), SAR-Operatoren bei optischen Daten.
- **Gesperrt mit Grund im Tooltip** bleibt, was nur im Moment nicht geht und gleich wieder gehen kann: etwa „Download“ eines abgelaufenen Ergebnisses, „Share“ bei einem Batch, „Start job“ bei ungültigen Eingaben.
- Die Regel gilt ab sofort für alles Neue (DS-Paket, UI-01-Teile) und wird hier im Bestand nachgezogen.

## 3. Umfang

- Durchgang durch Processing-Panel, Layer-Manager, Processing-Manager, Download-Dialog; Liste „ausgeblendet / gesperrt mit Grund“ im PR.
- Die Entscheidung kommt aus derselben Stelle wie heute (`applicable`, Registry), nicht aus neuen Listen im Frontend.

## 4. Offene Punkte (bei Unklarheit Frage an Otto)

- Grenzfälle, bei denen „grundsätzlich“ vs. „im Moment“ unklar ist: Liste mit Vorschlag im PR.

## 5. Grenzen

- Nur Frontend.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 6. Abnahme

- Tests: nicht anwendbare Möglichkeiten erscheinen nicht (DEM ohne `mask`), zeitweise gesperrte zeigen den Grund.
- Gegenprobe: Mit dem alten Code scheitern die neuen Tests.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.
