# NM4-04 — Mosaik mit Operator im Kachel-Pfad

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 4 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** sofort möglich; nicht gleichzeitig mit NM4-19 (beide ändern `tiler`-Routen).
**Startsatz:** „Führe Aufgabe NM4-04 aus `docs/plans/querschnitt/nm4-04-mosaik-mit-operator.md` aus.“

## 1. Anlass

M4-17 zeigt das Mosaik eines Überflugs als Kachel, M4-18b erlaubt Operator-Ketten in der Kachel – aber nur für ein einzelnes Item. Eine Vorschau des Mosaik-Jobs mit Band math (etwa NDVI über einen ganzen Überflug) fehlt (M4-17, Frage 4).

## 2. Soll

- Die Mosaik-Kachel nimmt dieselben Parameter `op`, `op_version`, `params` (wiederholbar, höchstens 4) wie die Item-Kachel.
- Tile ↔ Job bitgleich auf der nativen Ebene wie in `adr/0014` §6.3, für ein Mosaik-Rezept mit Band math.
- Das Panel zeigt die Vorschau für Mosaik-Aufträge („One job“ über einen Überflug).

## 3. Im Plan klären (mit Optionen und Empfehlung)

- Reihenfolge: erst Mosaik, dann Operator je Pixel, oder Operator je Szene und dann Mosaik? Der Job macht es auf eine bestimmte Weise – die Kachel muss genau dasselbe tun (Beleg am Code).
- Kosten je Kachel: bis 12 Items je Kachel (M4-17) mal Operator; Messung mit Quellen und Zahlen, Grenzen (Zoom, Items).
- Statistik für die Farbskala der Mosaik-Vorschau (M4-19c) – gleiche Route oder Grenze.
- URL-Länge bei vielen Items plus Parametern (414/431); keine AOI in der URL.

## 4. Grenzen

- Kein Zustand im `tiler` außer dem bestehenden Item-Cache (`adr/0001`).
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: Mosaik-Kachel mit Band math gleich Mosaik-Job (nativ, bitgleich); Kette mit `mask`; Abweisungen (zu viele Schritte, unbekanntes Band, Zoom zu klein) vor dem Abruf.
- Gegenprobe: Mit dem alten Code scheitern die neuen Tests.
- Nachtrag in `adr/0014` bzw. `adr/0006`.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.
