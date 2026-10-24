# NM4-19 — Auto stretch der Vorschau über die AOI

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 19 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nicht gleichzeitig mit NM4-04 (`tiler`-Routen); höchstens zwei Stufe-B-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-19 aus `docs/plans/querschnitt/nm4-19-auto-stretch-ueber-aoi.md` aus.“

## 1. Anlass

Seit M4-19c misst die Vorschau ihre Farbskala über die erste Szene, auch bei „AOI only“ über die ganze Szene. Das Job-Ergebnis nimmt die Statistik über die AOI-Maske (M4-32). Vorschau und Ergebnis können sich deshalb unterscheiden.

## 2. Soll

- Bei „AOI only“ misst auch die Vorschau über die AOI; Vorschau und Ergebnis zeigen dieselbe Farbskala.
- **Harte Grenze:** keine AOI in URLs oder Logs. Die AOI geht nur im Body an den `tiler` (etwa `POST /statistics` mit GeoJSON, wie rio-tiler es kennt), nie als Query.

## 3. Im Plan klären (mit Optionen und Empfehlung)

- Schnittstelle: POST-Route, Größen- und Punktgrenze der Geometrie wie bei der Annahme; Cache-Schlüssel ohne AOI im Klartext und ohne Logging.
- Gleiche Methode wie im Job (festes Histogramm, M4-32a), damit die Werte übereinstimmen – mit Test Vorschau-Statistik gleich Job-Statistik.
- Mehrere Szenen bzw. Mosaik eines Überflugs.
- Kosten und Zeitlimit (Höchstwartezeit aus M4-19c bleibt).

## 4. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: Statistik über AOI gleich Job-Statistik; AOI erscheint in keinem Log und keiner URL (Test auf Zugriffslog); Grenzen der Geometrie.
- Nachtrag in `adr/0006` bzw. `adr/0014`.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.
