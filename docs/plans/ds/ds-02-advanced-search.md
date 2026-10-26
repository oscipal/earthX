# DS-02 — „Advanced search“ mit Filtern je Datensatz

**Stand:** 26.10.2026, beauftragt von Otto. Paket „Datensatzabhängige Suche und Prozessierung“ (DS), nach VP3 und vor M5; Übersicht in `docs/plans/ds/ds-00-paket.md`.
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach UI-01g (Suchergebnisse angedockt). Höchstens zwei Stufe-B-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe DS-02 aus `docs/plans/ds/ds-02-advanced-search.md` aus.“

## 1. Anlass

Otto möchte einen Knopf „Advanced search“, der die Filter zeigt, die zum gewählten Datensatz passen. Heute gibt es für Sentinel-2 einen Wolkenfilter; einen allgemeinen Weg für Filter je Datensatz gibt es nicht. `projektuebersicht.md` §7: „Qualitätsfilter, wo sinnvoll“.

## 2. Soll

- „Advanced search“ im Control-Menü öffnet die Filter des gewählten Datensatzes bzw. der gewählten Datensätze.
- Die Filter kommen aus der Registry je Datensatz (Feldname, Typ, Bereich bzw. Werte, Beschriftung, Einheit), nach dem Vorbild des Processing-Panels aus Schemas; wo die Quelle STAC-„queryables“ anbietet, wird das genutzt bzw. abgeglichen.
- Sentinel-2 bekommt seinen bestehenden Wolkenfilter über denselben Weg; nichts geht verloren.
- Filter, die ein Datensatz nicht kennt, erscheinen nicht. Bei mehreren gewählten Datensätzen gilt ein Filter nur für die Datensätze, die ihn kennen (sichtbar gekennzeichnet).
- Zusammenspiel mit `ignored_filters` (architekturplan, `time_range=False`) und mit der Coverage-Karte (Filter wirken auch dort, `adr/0004` K1).

## 3. Im Plan klären (mit Optionen und Empfehlung)

- Registry-Feld (Form, Validierung, Übersetzung in die Suchanfrage je Adapter, `adr/0011`); Kombination mit `query`/`filter` (CQL2) der Quelle.
- Wo „Wolken in der AOI“ (DS-03) später andockt.
- Permalinks (M4-19e) und „Clear search results“ (NM4-17): Filter gehören zu den Sucheinstellungen.

## 4. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip. Nicht anwendbare Möglichkeiten werden ausgeblendet, nicht ausgegraut (Otto, 26.10.2026).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Ausgehende Requests nur über `gateway`; keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Kein datensatzspezifischer Code: Unterschiede je Datensatz stehen als Daten in der Registry.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: Filter aus der Registry, Anfrage an die Quelle, Datensatz ohne Filter, mehrere Datensätze, Coverage reagiert.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), Hell/Dunkel, schmales Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n).
- Vor „fertig“ ist main geholt.
