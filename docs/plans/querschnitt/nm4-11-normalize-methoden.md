# NM4-11 — Normalize klarer und mit mehreren Methoden

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 11 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für Plan und Recherche, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach NM4-10 (Bandnamen); höchstens zwei Stufe-B-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-11 aus `docs/plans/querschnitt/nm4-11-normalize-methoden.md` aus.“

## 1. Anlass

`normalize` v1 kennt nur „linear von [a, b] nach [c, d]“; im Panel ist schwer zu verstehen, was der Schritt tut.

## 2. Soll

- **Klarer:** Das Panel zeigt kurz, was der Schritt tut, mit Beispiel (NDVI −1…1 → 0…1) und der Formel der gewählten Methode (im Tooltip). Felder mit verständlichen Namen.
- **Methoden (Vorschlag):** linear (wie heute), Z-Score, über Perzentile (etwa 2–98 %) auf einen Zielbereich mit Clip, eventuell robust (Median/Interquartilsabstand).

## 3. Im Plan klären (mit Optionen und Empfehlung)

- **Recherche mit Quellen (Pflicht):** Stand der Technik (GDAL/rio-tiler-Statistik, scikit-learn-Skalierer, Verfahren in der Fernerkundung).
- Z-Score und Perzentile brauchen Statistik über die ganze Eingabe: zwei Durchgänge oder Statistik vorab; Rechenzeit, Speicher (500 MB) und Bitgleichheit (zweimal, Cloud gegen Runner) müssen halten.
- Vorschau: keine Statistik je Kachel (Kacheln passten nicht zusammen). Optionen: Statistik einmal je Auftrag vorab (Route wie M4-19c), oder Vorschau nur für die lineare Methode.
- Stehen die Werte (Mittelwert, Perzentile) im Rezept, damit Rezept und Ergebnis eindeutig sind, oder entstehen sie im Lauf?
- Perzentile deterministisch wie M4-32 (festes Histogramm), Weg wiederverwenden. Je Band oder ein Bereich für alle Bänder.
- Neue `op_version` bzw. Parameter `method`; Kostenfaktor messen; Nachtrag `adr/0014`.

## 4. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests je Methode gegen eine unabhängige Rechnung; zweimal bitgleich; Runner gleich Kern; Speichertest unter 500 MB.
- Gegenprobe: Mit dem alten Code scheitern die neuen Tests.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.
