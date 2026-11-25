# UI-12 — gesammelter UI-Lauf

**Stand:** 25.11.2026, Auftrag Otto (Stufe B, Opus, mittel); **Antworten Otto vom 25.11.2026 in §7 eingearbeitet**. Grundlage: `docs/ui/leitfaden.md`, `docs/plans/m5/m5-discovery-und-suche.md` (Zeile UI-12), Legende und Histogramm aus #391 und #410, Entscheidungslog bis 25.11.2026.
**Regeln:** Oberflächentexte nur Englisch, keine Hinweistexte, Panels scrollen nie.
**Vorgehen:** Plan mit Fragen F1–F7, dann Umsetzung nach den Empfehlungen in zwei Draft-PRs. Wo eine Antwort anders ausfällt, ändert dieselbe Session nach. Teile, die nicht entschieden sind, sind als *angehalten* markiert und bleiben, wie sie sind.

## 1. Punkte und Aufteilung

| # | Punkt | PR | Umsetzung |
|---|---|---|---|
| 1 | Zeile „Keywords“ in den Details des Data catalogue entfällt | 1 | `catalogueRows` ohne die Zeile; Schlagworte bleiben in Registry, API und Suchtext |
| 2 | schmale Fenster (360×740, 1280×360) | 2 | Befunde §3, behoben mit F1 und F3 |
| 3 | Statusbox fest an einem Ort, den kein Panel verdeckt | 2 | F1 |
| 4 | Quick processing mit Seiten | 2 | wie „Datasets“: drei Knöpfe je Reihe, so viele Reihen, wie ohne Scrollen passen, „‹ 1 / n ›“ klein rechts neben der Überschrift |
| 5 | Rechteck-Werkzeug nach der Ortssuche | 1 | A1 |
| 6 | AOI „Point“ ist ein echter Punkt | 1 | Werkzeug, Hochladen, Anzeige und Suche; F4, F5 |
| 7 | „Add dataset“ öffnet den Data catalogue mit Filter „nur hinzufügbare Einträge“ | 1 | F6; die API kennt `entry=full` schon |
| 8 | Datumsfelder unabhängig von der Browsersprache | 1 | F7 |
| 9 | Scrollleiste im Data catalogue dunkel wie im Processing-Panel | 1 | dieselbe Regel für beide |
| 10 | „(your choice)“ neben dem Datentyp entfällt | 1 | |
| 11 | „+ Add dataset“ als Aktion erkennbar | 1 | gestrichelter Rand, Text in `--muted` |
| 12 | rechte Einstellungsleiste scrollt bei 1280×360 und 360×740 | 2 | F3 |

## 2. Auslegungen

- **A1 (Punkt 5):** Laut Log vom 18.11.2026 soll das Werkzeug verschwinden. Heute bleibt „Rectangle“ nach der Wahl eines Orts gedrückt, und der nächste Klick auf die Karte beginnt ein Rechteck, das den Ort ersetzt. Künftig beendet jede AOI, die nicht gezeichnet wird (Ort, Hochladen, „Last AOI“), das gewählte Werkzeug. „Last AOI“ tut das schon.
- **A2 (Punkt 6):** Der Punkt erscheint auf der Karte als Punkt und nicht mehr als Quadrat. Gesucht wird mit dem Punkt. Der Tooltip des Werkzeugs nennt kein Quadrat mehr. Wo heute intern das Quadrat gilt (Filter, die die Fläche messen, und Zuschnitt), bleibt es bis zur Antwort auf F4 und F5.
- **A3 (Punkt 4):** Die Seitengröße wird gemessen wie bei „Datasets“ (`datasetPages.ts`), mindestens eine Reihe. „Enhance contrast“ zählt wie ein Index.

## 3. Befunde in schmalen Fenstern (vor der Umsetzung, im Browser)

- 360×740: Die Statusbox liegt über dem Kompass, über dem Kopf des offenen Panels (Feld „Scene name“, Ortssuche) und über dem Sheet der Einstellungen.
- 360×740: Die Legende liegt über der Attribution und bei einer Ansicht mit Zeitleiste über dem Kompass; die Zeitleiste liegt über der Knopfgruppe.
- 360×740: Das Sheet der Einstellungen scrollt (Punkt 12).
- 1280×360: Die Einstellungsleiste scrollt; „Actions“ ist nicht zu sehen (Punkt 12).
- 1280×800 und 1280×360 mit Ansicht: Die Zeitleiste reicht unter die Spalte der Kartenknöpfe (Kompass, Zoom).
- 360×740: Die Attribution läuft unter die Leiste; mit Processing-Sheet liegt die Legende über den Knöpfen oben.
- 1280×360 mit Panel der Leiste und Ansicht: Die Karte ist zu niedrig für Legende und Zeitleiste; die Legende reicht in die Knöpfe oben.

## 4. Fragen an Otto

**F1 – Ort der Statusbox (Punkt 3)**
1. Eine Statuszeile am unteren Fensterrand, rechts der Leiste, über die ganze Breite und immer da (eine Steuerhöhe). Panels, Sheet, Legende, Zeitleiste und Kartenknöpfe enden darüber, nur der Data catalogue darf sie decken. Spinner, Text, „Stop“ und das rote x stehen in einer Reihe, wie die Statusleiste in QGIS. **Empfehlung.**
2. Wie 1, aber am oberen Rand.
3. In der Leiste links ein Symbol (Spinner bzw. Warnung), der Text im Tooltip.

**F2 – Mehrere und lange Meldungen in der Zeile (zu F1 = 1)**
1. Eine Reihe: der Spinner, solange etwas lädt, davor der Text in der Rangfolge Fehler, laufender Vorgang, Hinweis. Ein zu langer Text wird mit „…“ gekürzt, der volle Text steht im Tooltip (wie bei einem gekürzten Jobtitel, §8a (c)). **Empfehlung.**
2. Die Zeile wächst bei langem Text auf höchstens drei Reihen, und alle Panels werden für diese Zeit kürzer.

**F3 – Einstellungsleiste scrollt nie (Punkt 12)**
1. Ein breites Fenster (ab 900 px) mit zu wenig Höhe bekommt eine zweite Spalte (2 × 320 px). Der Inhalt fließt in die zweite Spalte, wo die erste voll ist, und ein Abschnitt kann dabei an einer Zeilengrenze umbrechen. Unter 900 px wird das Sheet so hoch wie nötig, bis unter die Knöpfe oben. Reicht das nicht, klappen die Abschnitte von unten her ein, wie die Legenden im Layer-Manager (Otto, 24.11.2026). Ihr Kopf öffnet sie wieder, und der zuletzt geöffnete klappt zuletzt. **Empfehlung.**
2. Wenn der Platz fehlt, stehen „Display“, „Quick processing“ und „Actions“ als Segment-Knöpfe im Kopf, und es ist immer nur ein Abschnitt zu sehen.
3. Ausnahme vom Scrollverbot unterhalb einer Mindesthöhe (z. B. 500 px).

**F4 – Filter, die die Fläche messen, bei einem Punkt (Punkt 6, *angehalten*)**
„AOI coverage“ und „Filter within AOI only“ messen heute im Quadrat um den Punkt („a point is an area as well“, Otto, 06.11.2026).
1. Der Server misst am Punkt: Bei „AOI coverage“ zählt, ob die Szene den Punkt enthält (0 oder 100 %), bei Wolken die Klasse des Pixels am Punkt. Das braucht eine eigene Aufgabe im Backend. **Empfehlung.**
2. Das Quadrat bleibt intern für diese Filter, und auf der Karte ist nur der Punkt zu sehen.

**F5 – Zuschnitt mit einem Punkt (Punkt 6, *angehalten*)**
1. „Download crop“ und der Zuschnitt im Processing sind gesperrt und nennen den Grund „A point has no area to crop: draw a rectangle or polygon“. Ganze Szenen gehen weiter. **Empfehlung.**
2. Zuschnitt auf das Pixel am Punkt.
3. Wie heute das unsichtbare Quadrat um den Punkt.

**F6 – Name des Filters „nur hinzufügbare Einträge“ (Punkt 7)**
1. „Addable only“: ein Schalter im Popup „Filters“ wie „Filter by search panel“. Ist er an, entfernt ihn sein „×“. Er zählt am Knopf („Filters · 1“). **Empfehlung.**
2. „Full entries only“.
3. „Can be added“.

**F7 – Datumsfelder (Punkt 8)**
1. Ein Textfeld im Format „2026-12-03“ (wie `formatDay`, §2 des Leitfadens) mit eigenem englischem Kalender (Monat, Wochentage Mo–Su, nur die erlaubten Tage). **Empfehlung.**
2. Ein Textfeld „2026-12-03“, dazu der Kalender des Browsers. Dessen Monatsnamen kommen dann in der Sprache des Browsers.
3. Format „3 Dec 2026“.

## 5. Prüfungen

- Unit-Tests der geänderten Module, `npx tsc -b`, `npm run lint`.
- Browser-Checks je Punkt bei 1280×800, 1280×360 und 360×740, hell und dunkel: `frontend/e2e/ui-12-*.cjs`, dazu die betroffenen vorhandenen Checks (`status-box.cjs`, `narrow-windows.cjs`, `data-catalogue.cjs`, `dataset-pages.cjs`, `quick-processing.cjs`, `map-legend.cjs`).

## 6. Stand der Umsetzung (25.11.2026)

- **PR 1** ([#417](https://github.com/oscipal/earthX/pull/417)): Punkte 1, 5–11 nach F6 = 1 und F7 = 1. Bei Punkt 6 gilt für Filter und Zuschnitt bis M5-69 das unsichtbare Quadrat (F4, F5).
- **PR 2** ([#418](https://github.com/oscipal/earthX/pull/418)): Punkte 2, 3, 4 und 12 nach F1 = 1, F2 = 1 und F3 neu (§7).
- Die Befunde aus §3 sind behoben und werden von `frontend/e2e/ui-12-layout.cjs` geprüft. `frontend/e2e/status-box.cjs` prüfte die alte Regel und entfällt.

## 7. Antworten Otto (25.11.2026)

- **F1 = 1, F2 = 1:** Statuszeile unten wie in QGIS, ein langer Text gekürzt und ganz im Tooltip. Umgesetzt.
- **F3 neu:** Die rechte Einstellungsleiste darf scrollen: eine Spalte, keine weiteren Spalten, kein automatisches Einklappen, die Karte behält ihren Platz. „Quick processing“ behält die Seiten; eine Seite verliert eine Reihe, solange die Leiste überläuft, bis eine. Für alle anderen Panels und die Legende gilt weiter „scrollt nie“. Die Abweichung „bis zu drei Spalten“ entfällt. Angenommen bleiben: Histogramme unter 900 px niedriger. „Display“ klappt nicht von selbst ein (es klappt nichts mehr ein).
  - **Vorschlag Sheet unter 900 px (umgesetzt):** höchstens 55 % der Karte, darüber bleibt die Karte frei, der Rest scrollt; der Griff klappt es weiter ein. Der Wert ist der bisherige vor UI-12.
- **F4 = 1** als Folgeaufgabe **M5-69** („Punkt als echter Punkt: Filter und Zuschnitt am Punkt“): Der Server misst „AOI coverage“ (enthält die Szene den Punkt) und Wolken (Klasse des Pixels) am Punkt. Bis dahin Option 2: intern das Quadrat, auf der Karte nur der Punkt.
- **F5 = 2**, ebenfalls in M5-69 (Backend): Zuschnitt mit einem Punkt ergibt das Pixel am Punkt, je Band in dessen nativer Auflösung, bei „One multi-band file“ in der gemeinsamen Auflösung, für „Download crop“ und den Zuschnitt im Processing. Bis dahin bleibt der Zuschnitt beim unsichtbaren Quadrat.
- **F6 = 1** („Addable only“), **F7 = 1** (Format „2026-12-03“ mit eigenem englischem Kalender).
- **Legende verschwindet nie:** Wo der Platz fehlt, bleibt sie eingeklappt mit dem Titel „Legend“ an ihrem Ort sichtbar und lässt sich aufklappen.
  - **Vorschlag Ort (umgesetzt):** Wo ein Panel ihren Ort decken würde (unter 900 px mit offenem Panel der Leiste oder Processing-Sheet) oder nicht einmal der Titel auf die Karte passt, steht der eingeklappte Titel am **linken Ende der Statuszeile**. Dort deckt ihn nichts, und er deckt nichts; die Box klappt von dort nach oben auf. Direkt über der Statuszeile läge der Titel sonst auf dem Panel und deckte dessen Fuß (etwa „Search“ im Search panel).
