# NM4-23 — Backend-Tests schneller

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 23 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für Messung und Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** sofort möglich; höchstens zwei Stufe-B-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-23 aus `docs/plans/querschnitt/nm4-23-backend-tests-schneller.md` aus.“

## 1. Anlass

CI-Lauf auf `main` (24.10.2026): Job „Backend — lint and tests“ 14,2 min, davon `pytest` 13,2 min; Installation 0,5 min. Frontend 0,7 min, Modulgrenzen 0,7 min, compose-topology 1,9 min.

## 2. Soll

- Die Backend-Tests laufen deutlich schneller, ohne an Aussage zu verlieren.

## 3. Umfang

- **Schritt 1 – messen:** `pytest --durations=30` in der Session; Tabelle der langsamsten Tests im PR.
- **Abhilfe ohne Verlust:** kleinere synthetische Raster, wo die Größe nicht der Prüfgegenstand ist; teure Fixtures mit Geltungsbereich `module`/`session`; doppelte Prüfungen zusammenlegen. Speicher- und Bitgleich-Tests bleiben in voller Größe.

## 4. Im Plan klären (mit Optionen und Empfehlung)

- **Schritt 2 – parallel (nur nach Ottos Freigabe):** `pytest-xdist` ist eine neue Abhängigkeit. Mit Quellen klären: Verträglichkeit mit `spawn`-Kindprozessen und Speichermessung (`VmHWM` je Prozess), eigene Datenbank je xdist-Worker, Zahl der Kerne der GitHub-Runner für öffentliche Repos. Einstellung über die pytest-Konfiguration.

## 5. Grenzen

- Keine Tests streichen oder überspringen, um Zeit zu sparen.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 6. Abnahme

- Laufzeit vorher/nachher (Session und CI) im PR; Zahl der Tests unverändert oder höher.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.
