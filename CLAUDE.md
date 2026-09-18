# EarthX

Web-Plattform für Geo- und Satellitendaten. Die Planung liegt in `docs/`.

**Zuerst lesen:** `docs/ENTSCHEIDUNGEN_2026-09-18.md`, dann `docs/KLAERUNGEN.md`,
dann für die Aufgabe relevante Abschnitte von `docs/architekturplan.md`
(0, 3.1, 7.3) und `docs/projektuebersicht.md` (Prinzipien).

## Rangfolge bei Widerspruch

`docs/ENTSCHEIDUNGEN_2026-09-18.md` > `docs/KLAERUNGEN.md` > Plandokumente
(`architekturplan.md`, `projektplan.md`, `projektuebersicht.md`) > diese Datei.

Die sieben Hard Constraints in `docs/ADDING_ESA_DATASETS.md` sind **aufgehoben**.
Die Datei ist nur noch Beschreibung des Code-Stands vom 13.08.2026.

## Unverrückbar

- Modulgrenzen laut `docs/architekturplan.md` 3.1; Importregeln nie lockern.
- Ausgehende Requests nur über `gateway` (KLAERUNGEN B8).
- Worker-Kern zustandslos und ohne Plattformdienste — keine Datenbank, Queue,
  Objektspeicher oder interne API (KLAERUNGEN B9). Lesen der Datenquellen über
  `gateway` ist erlaubt.
- `decomp.py` nie generalisieren: nur als Operator mit Quad-Pol-Capability.
- Keine Secrets, Tokens, `.env`-Werte, internen URLs oder exakten AOIs in Code,
  Commits, Logs, Issues oder PRs.
- BIOMASS und MAAP kommen in CI, Cloud-Sitzungen und Fixtures nicht vor.
  Fixtures nur synthetisch oder mit eindeutig offener Lizenz.

## Arbeitsweise

- Pro Aufgabe ein Branch von `main` und ein **Draft-PR**. Nie mergen, nie force-pushen.
- Autonomiestufen A/B/C laut `docs/projektplan.md` 1.2. Stufe C heißt: nur lesen
  und berichten, kein Produktivcode.
- Arbeitsstände oft committen und pushen.
- Vor "fertig": Tests und Lint ausführen, sofern vorhanden, und das Ergebnis
  zusammenfassen.
- Tests decken Fehlerfälle, fehlerhafte Eingaben und zweckfremde Nutzung ab.
  Externe Quellen nur über `tests/fixtures`.
- Commits mit Skill `atomic-commits`; vor dem PR `code-cleanup` auf die
  geänderten Dateien.
- Richtwert für PRs: unter etwa 400 geänderten Zeilen ohne generierte Dateien.

## Ohne Rückfrage nicht ändern

`.github/`, `.claude/`, `CLAUDE.md`, `CODEOWNERS`, Branch-Schutz.
Ausnahme: was die jeweilige Aufgabe ausdrücklich verlangt.

Ebenfalls nie ohne Otto: Merge in `main`, Löschen von Daten, History-Rewrites,
Deployment, Secrets, kostenpflichtige Dienste, Lockerung von Sicherheitsregeln
oder Importgrenzen, Lizenz-Einstufung eines Datensatzes.

## Fragen und offene Punkte

- Was nicht in `docs/` steht, ist **nicht entschieden**. Nicht raten: fragen und
  diesen Teil der Aufgabe anhalten.
- Fragen so stellen, dass sie am Handy kurz beantwortbar sind: nummerierte
  Optionen mit einer Empfehlung.
- Fehlt der Zugang zu etwas, genau benennen, was fehlt, und stoppen.
  Nichts mocken, nichts ersetzen.

## Entscheidungen festhalten

- Jede neue Entscheidung als eine Zeile in `docs/ENTSCHEIDUNGSLOG.md`
  (Datum, Kurzfassung, Status, betroffene Dokumente).
- Architekturentscheidungen zusätzlich als ADR-Entwurf unter `docs/adr/`.

## Sprache

Dokumente und Kommunikation auf **Deutsch**. Code, Bezeichner, Commit-Nachrichten,
Branch-Namen und PR-Titel auf **Englisch**.

## Befehle

Noch nicht eingerichtet (M0). Bis dahin: Umgebung nach `environment.yml`;
Frontend über `frontend/package.json`. Sobald Test-, Lint- und Start-Befehle
stehen, gehören sie hierher.

## Delegation

Subagenten liegen in `.claude/agents/` und sind in `docs/projektplan.md` 3.3
beschrieben. Standardmodell für nicht zugeordnete Subagenten ist Sonnet
(`.claude/settings.json`).

| Subagent | wofür |
|---|---|
| `explorer` | Fundstellen und Zusammenfassungen, hält den Hauptkontext klein |
| `implementer` | abgegrenzte Teilaufgabe umsetzen |
| `test-writer` | Tests und Fixtures |
| `reviewer` | Diff vor dem menschlichen Review prüfen |
| `architect` | ADR-Entwürfe mit Optionen, Kriterien, Empfehlung |
| `researcher` | Stand der Technik mit Quellen, keine Codeänderung |
| `docs-writer` | README, Docstrings, Changelog |
| `license-checker` | Lizenz → SPDX + Flags, immer nur Vorschlag |
| `bug-triager` | Bug-Report einordnen und reproduzieren |
