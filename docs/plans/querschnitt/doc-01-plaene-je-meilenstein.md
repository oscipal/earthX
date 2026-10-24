# DOC-01 — `docs/plans/` je Meilenstein ordnen

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 13; Reihenfolge laut Log vom 24.10.2026: zuerst diese Aufgabe, dann UI-01, UI-02).
**Stufe A:** direkt umsetzen, ein Draft-PR. Nur Doku und Verweise, kein Verhalten ändert sich.
**Modell:** Sonnet, Effort mittel.
**Start:** nach dem Merge von M4-20 (#181), wenn **keine andere Session läuft**. Bis zum Merge dieser Aufgabe startet keine neue Session (auch nicht Backlog-Punkt 1 und 2), weil sich alle Pfade der Startsätze ändern.
**Startsatz:** „Führe Aufgabe DOC-01 aus `docs/plans/doc-01-plaene-je-meilenstein.md` aus.“

## 1. Ziel

Alle Plan-Dateien liegen in einem Unterordner je Meilenstein. Dateinamen bleiben gleich. Jeder Verweis im Repo zeigt auf den neuen Pfad.

## 2. Zielordner

| Ordner | Inhalt |
|---|---|
| `docs/plans/m0/` … `docs/plans/m4/` | Pläne des jeweiligen Meilensteins, auch Zusätze und Unteraufgaben (etwa `m4-zusaetze-2026-10-12.md`, `m4-2x-*`, `m4-3x-*`, `m4-20-abnahme.md`) |
| `docs/plans/vp3/` | `ui-01-app-rahmen.md`, `ui-02-basemap-projektion.md`, sobald im Repo |
| `docs/plans/querschnitt/` | Pläne ohne Meilenstein, darunter diese Datei |
| `docs/plans/` (Wurzel) | nur `nach-m4-backlog.md` (lebende Liste) und `README.md` |
| `docs/plans/README.md` | neu: eine kurze Übersicht (ein Satz je Ordner, Hinweis auf die Rangfolge der Dokumente) |

- **Zuordnung:** nach dem Präfix des Dateinamens (`m1-`, `m2-`, …, `ui-` → `vp3`). Dateien ohne eindeutiges Präfix listet die Session im PR mit Vorschlag; bei Unklarheit fragt sie Otto, statt zu raten.
- **Diese Datei** liegt beim Start in `docs/plans/` und wird mit verschoben; der Startsatz oben nennt den Pfad beim Start.

## 3. Umfang

1. **Bestandsaufnahme:** Liste aller Dateien unter `docs/plans/` mit Zielordner (Tabelle im PR).
2. **Verschieben** nur mit `git mv`, damit die Historie erhalten bleibt (`git log --follow`).
3. **Verweise nachziehen** im ganzen Repo: Pläne untereinander, `docs/adr/`, `ENTSCHEIDUNGSLOG.md`, `KLAERUNGEN.md`, `projektplan.md`, `architekturplan.md`, `README.md`, Kommentare und Docstrings in Code und Tests, Fixtures.
   - Auch relative Verweise wie `plans/m4-processing-kern.md` oder `../plans/…` und Verweise ohne Pfad im Fließtext, die eindeutig eine Plan-Datei meinen.
   - **Alte Log-Zeilen** im `ENTSCHEIDUNGSLOG.md` bekommen die neuen Pfade (das Log ist ein Nachschlagewerk; die Spalte „betroffene Dokumente“ soll auffindbar bleiben). Der Wortlaut der Entscheidungen bleibt sonst unverändert.
4. **Geschützte Dateien:** `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert, außer Otto erlaubt es ausdrücklich. Die Session listet im PR jeden Verweis dort, der auf einen alten Pfad zeigt.
5. **Prüfung:** ein kleiner Test (oder Skript in `scripts/`, im PR begründet), der fehlschlägt, wenn
   - eine Datei direkt in `docs/plans/` liegt außer `README.md` und `nach-m4-backlog.md`,
   - irgendwo im Repo ein Verweis auf `docs/plans/<datei>.md` oder `plans/<datei>.md` ohne Unterordner steht, dessen Datei es nicht gibt (Ausnahmen: die geschützten Dateien aus Punkt 4, solange Otto nichts anderes sagt).
   Gegenprobe im PR: ein absichtlich alter Verweis lässt den Test scheitern.
6. **Startsätze:** Alle Startsätze in Plan-Dateien nennen den neuen Pfad, etwa „Führe Aufgabe UI-01 aus `docs/plans/vp3/ui-01-app-rahmen.md` aus.“

## 4. Grenzen

- Kein Inhalt einer Plan-Datei ändert sich außer Pfaden und Startsätzen.
- Keine Datei wird umbenannt oder gelöscht.
- Kein Produktivcode ändert sich außer Kommentaren und Docstrings mit Pfaden.

## 5. Abnahme

- Tabelle der Verschiebungen im PR; `git log --follow` an zwei Beispielen gezeigt.
- Test aus §3 Punkt 5 grün, Gegenprobe im PR.
- Liste der Verweise in geschützten Dateien (Punkt 4) im PR.
- Alle vier Pflicht-Checks der CI grün.
- Log-Zeile; Zeile in `projektplan.md` oder dem passenden Übersichtsdokument, falls dort Pfade stehen.
- Vor „fertig“ ist main geholt.
