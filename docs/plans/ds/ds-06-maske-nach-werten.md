# DS-06 — Maske nach Werten eines Bandes

**Stand:** 26.10.2026, beauftragt von Otto. Paket „Datensatzabhängige Suche und Prozessierung“ (DS), nach VP3 und vor M5; Übersicht in `docs/plans/ds/ds-00-paket.md`.
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach UI-01; nicht gleichzeitig mit NM4-10 (Bandnamen). Höchstens zwei Stufe-B-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe DS-06 aus `docs/plans/ds/ds-06-maske-nach-werten.md` aus.“

## 1. Anlass

`mask` (M4-18) blendet heute nur Klassen einer Klassifizierungsschicht aus (`SCL`). Otto möchte auch Pixel nach Werten eines beliebigen Bandes ausblenden (etwa NDVI < 0,2 oder Höhe > 2000 m). Mit Band math und `where` lässt sich ein Wert ersetzen, aber nicht sauber als „kein Wert“ (nodata) markieren.

## 2. Soll

- Pixel werden ausgeblendet (nodata), wenn ein gewähltes Band eine Bedingung erfüllt: kleiner, größer, zwischen, gleich (für Klassen).
- Das Band kann ein Band des Datensatzes oder das Ergebnis eines früheren Schritts sein (NM4-10).
- Verfügbar für jeden Datensatz; die Maske nach Klassen (`SCL`) bleibt für Datensätze mit Klassifizierung.

## 3. Im Plan klären (mit Optionen und Empfehlung)

- Eigener Operator, neue Version von `mask` (Parameter `by: classes | values`) oder Band-math-Erweiterung (etwa ein `nodata`-Literal)? Empfehlung mit Begründung.
- Bitgleichheit Kachel ↔ Job; Versionierung (`op_version`), Nachtrag `adr/0014`; Kostenfaktor.

## 4. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip. Nicht anwendbare Möglichkeiten werden ausgeblendet, nicht ausgegraut (Otto, 26.10.2026).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Ausgehende Requests nur über `gateway`; keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Kein datensatzspezifischer Code: Unterschiede je Datensatz stehen als Daten in der Registry.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: Bedingungen gegen eine unabhängige Rechnung, Kette mit Band math, Kachel ↔ Job bitgleich.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), Hell/Dunkel, schmales Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n).
- Vor „fertig“ ist main geholt.
