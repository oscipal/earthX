# NM4-34 — Job neu starten („Retry“) und Umbenennen im Processing-Fenster

**Stand:** 26.10.2026, beauftragt von Otto (Backlog-Punkt 34 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort hoch.
**Start:** nach UI-01f; nicht gleichzeitig mit NM4-27 (beide ändern Processing-Manager und Ablage). Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-34 aus `docs/plans/querschnitt/nm4-34-job-neu-starten.md` aus.“

## 1. Anlass

Otto (26.10.2026): Bricht ein Job ab oder läuft er aus irgendeinem Grund nicht durch, will er ihn neu starten können – auch abgelaufene Jobs. Heute gibt es nur „Open in panel“ für abgelaufene Jobs (UI-01c, aus der Auftragskopie in der Ablage). Außerdem will er einen Job direkt im Processing-Fenster (Details des Jobs) umbenennen können; heute geht das nur im Processing-Manager (UI-01c).

## 2. Soll

- **„Retry“ als kleines Symbol** (etwa ↻, Tooltip „Run again“) an gescheiterten (`failed`), abgebrochenen (`dismissed`) **und abgelaufenen** Jobs, in der Zeile des Processing-Managers und in den Details: ein Klick sendet denselben Auftrag erneut (Auftragskopie aus der Ablage, UI-01b) und legt einen neuen Job an; kein Umweg über das Panel.
- Der neue Job erscheint an der Stelle des alten (gleicher Titel, gleiche Gruppe); der alte wird als „Superseded“ markiert und archiviert, nicht gelöscht.
- **Batch:** „Retry failed parts“ an der Batch-Zeile startet nur die gescheiterten bzw. abgebrochenen Teile neu; die Teile bleiben im selben Batch.
- **Nicht möglich** (keine Auftragskopie mehr, Datensatz ausgeschieden mit `410`): Retry erscheint nicht (Regel 26.10.2026); „Open in panel“ bleibt, wo möglich.
- **Kein Tastenkürzel** (Otto, 26.10.2026).
- **Umbenennen im Processing-Fenster:** Der Titel in den Details eines Jobs ist direkt bearbeitbar (Klick auf den Titel oder kleines Stift-Symbol, Enter speichert, Esc verwirft); dieselbe Ablage wie das Umbenennen im Manager, beide Stellen zeigen sofort den neuen Titel.

## 3. Umfang

- Nur Frontend: Der Auftrag wird über die bestehende Annahme (`POST …/execution`) gesendet; ein Cache-Treffer ist willkommen.

## 4. Offene Punkte (bei Unklarheit Frage an Otto)

- **Fehlerarten:** Lohnt Retry bei jedem Grund? Vorschlag: anbieten bei vorübergehenden Gründen (Quelle nicht erreichbar, Zeitüberschreitung, `out_of_memory`, `unknown`, Abbruch durch den Nutzer); bei Gründen, die sicher wieder scheitern (ungültiger Ausdruck, `scaling_mismatch`, `grid_mismatch`, `aoi_outside_inputs`), stattdessen „Open in panel“ zum Ändern. Liste am Code (`processing.failure_kind`) im PR.
- Wiederholte Fehlschläge: Zähler „Retry (2)“ oder Grenze? Vorschlag: kein Limit, aber der Grund des letzten Fehlschlags steht im ⚠.

## 5. Grenzen

- Nur Frontend.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 6. Abnahme

- Tests: Umbenennen im Processing-Fenster (Enter/Esc, Anzeige im Manager); Retry sendet genau den gespeicherten Auftrag, auch bei abgelaufenen Jobs; neuer Job ersetzt den alten in der Zeile, alter archiviert; Batch nur gescheiterte Teile; ohne Auftragskopie kein Retry; Doppelklick eine Anfrage.
- Gegenprobe: Mit dem alten Code scheitern die neuen Tests.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n) mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat, siehe Kopf des Backlogs).
- Vor „fertig“ ist main geholt.
