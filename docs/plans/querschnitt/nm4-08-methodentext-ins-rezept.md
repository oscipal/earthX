# NM4-08 — Methodentext ins Rezept, `methods.txt` entfällt

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 8 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort hoch.
**Start:** sofort möglich (Backend und Runner); nicht gleichzeitig mit NM4-10 (beide ändern `recipe.json`/Runner).
**Startsatz:** „Führe Aufgabe NM4-08 aus `docs/plans/querschnitt/nm4-08-methodentext-ins-rezept.md` aus.“

## 1. Anlass

Seit M4-19a liegt der Methodentext als eigene Datei `methods.txt` im ZIP. Otto möchte ihn im Rezept haben und keine eigene Datei. Einen Knopf zum Kopieren gibt es nirgends (Otto, 22.10.2026; UI-01 §1 Punkt 12).

## 2. Soll

- `recipe.json` trägt den Methodentext im Block `provenance` als Feld `methods`. Dieser Block geht nicht in den Hash ein; der Runner trennt ihn beim Einlesen ab (M4-16 F3).
- Die Datei `methods.txt` entfällt im Job-ZIP, im Bündel (UI-01) und im Runner.
- Der Runner schreibt den Text ebenfalls in die `recipe.json` seines Laufordners bzw. in `provenance.json` (Vorschlag im PR).

## 3. Umfang

- Die eine Definition der Download-Inhalte (M4-30, `TEXT_FILES` aus M4-19a) anpassen.
- Modell `Provenance` erweitern; ältere `recipe.json` ohne `methods` bleiben gültig (Runner, „Load recipe…“ aus M4-19d).

## 4. Offene Punkte (bei Unklarheit Frage an Otto)

- Link und Ausgang `methods` der API: bleiben oder entfallen? Vorschlag: bleiben (API-Clients), Text aus derselben Funktion.

## 5. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 6. Abnahme

- Tests: `recipe.json` mit `provenance.methods`; ZIP ohne `methods.txt`; Hash unverändert; Runner liest alte und neue Dateien; ein älterer Runner liest die neue Datei (oder klare Meldung).
- Gegenprobe: Mit dem alten Code scheitern die neuen Tests.
- Nachtrag in `adr/0014` und `adr/0016`.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.
