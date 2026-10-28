# ADR 0021 — Suchfilter je Datensatz

- **Status:** Entwurf (Nummer 0021, weil 0020 durch NM4-43 belegt ist; Otto, 28.10.2026). Die Entscheidungen hat Otto am 28.10.2026 mit dem Plan von DS-02 getroffen (`docs/plans/ds/ds-02-advanced-search.md` §6, freigegeben zu #217). Dieses ADR hält sie als Architekturentscheidung fest; Begründung, Optionen und Messungen stehen im Plan.
- **Datum:** 2026-10-28
- **Aufgabe:** DS-02a (Backend Suche, umgesetzt), DS-02b (Backend Coverage, §5) und DS-02c (Oberfläche) als eigene PRs.

## 1. Anlass

Otto möchte unter „Advanced search“ die Filter sehen, die zum gewählten Datensatz passen. Bis DS-02 gab es nur `max_cloud_cover` an `/coverage`, fest auf `eo:cloud_cover` verdrahtet, und die Suche wies `query` ab, weil die Quelle es auf dem alten Weg still verworfen hätte (M3-13 F5).

## 2. Entscheidungen

1. **Registry (Plan §6.3, Frage 1):** `DatasetConfig.search_filters`, ein Tupel von `SearchFilter` (Eigenschaft, Art `RANGE`/`VALUES`, Titel, Tooltip, Einheit, Bereich mit Ganzzahl-Schalter bzw. Werte mit Beschriftung), ohne Vorgabewert. Veröffentlicht als `earthx:search_filters` in den Wörtern von STAC-Queryables (`architekturplan.md` 5.1). Filter gibt es vorerst nur für föderierte Datensätze, deren Quelle `query` kann; beides prüft der Start.
2. **Registry ist die Wahrheit (§6.6):** Die Queryables der Quelle sind unvollständig (Sentinel-2: nur `eo:cloud_cover`, ohne Bereich; Sentinel-1: nur `sar:polarizations`) und die `summaries` veraltet (ohne `sentinel-2c`). Ein Live-Test unter `backend/tests_live/` gleicht ab (Otto, D).
3. **Internes Modell (Otto, B):** Bedingungen (`RangeCondition`, `ValuesCondition` in `catalog/search_filters.py`) sind unabhängig vom Leitungsformat. `api` liest die Anfrage hinein und prüft sie gegen die Registry; der Adapter übersetzt (Earth Search: Query-Extension). `FilterSupport.query` sagt, ob eine Quelle das kann (`adr/0011` §11a).
4. **Eigene Schnittstelle (§6.4, Frage 2):** `POST /stac/search` nimmt `query` (STAC-Query-Extension) nur mit den Eigenschaften und Operatoren der Registry (`gte`/`lte`, `in`). Ein `query` gilt für jede gesuchte Collection, die die Eigenschaft anbietet; den übrigen fehlt es, und `ignored_filters_by_collection` nennt das. Für Werte je Datensatz (Otto, A) nimmt der Body `query_by_collection` (Auslegung, gilt bis Otto widerspricht); beides zusammen ist `400`. `GET` weist beides ab. Keine Konformitätsklasse `#query` (Nachtrag zu `adr/0005` Regel VI).
5. **Fehler (Otto, C):** Eigene Texte nennen Eigenschaft und Regel, nie einen Wert der Anfrage. Ein Fehler der Quelle geht als Status mit eigenem Text weiter; ihr Auszug erscheint weder in der Antwort noch im Log.
6. **Seitenmarken und Cache:** Die Bedingungen gehen in die Fingerabdrücke der Suche (je Quelle und gemischt) ein, aber nur, wenn welche gesetzt sind. Suchen ohne Filter behalten Marken und Cache-Einträge; `TOKEN_VERSION` bleibt 2.
7. **Reserviert für DS-03:** Eigenschaften mit `earthx:` sind Filtern vorbehalten, die die Plattform selbst rechnet; bis DS-03 sind sie `400`.

## 3. Messung (28.10.2026, Earth Search v1, Plan §6.2, §6.2a)

- `query` wirkt in `/search` und `/aggregate` (Wolken, No-Data-Anteil, Satellit).
- Unbekannte Eigenschaft: still 0 Treffer. Unbekannter Operator und CQL2-`filter`: still übergangen. Falscher Typ: `400` mit Interna der Suchmaschine.
- Sentinel-2-Items tragen weder `sat:orbit_state` noch `sat:relative_orbit`; beide Filter gibt es erst mit Sentinel-1 (DS-04).

## 4. Folgen

- Sentinel-2 bietet Cloud cover, No data und Satellite an; der DEM keine.
- DS-02b ersetzt `max_cloud_cover` an `/coverage` durch dieselben Bedingungen (§5). DS-02c baut die Oberfläche mit Umschalter je Datensatz.
- Ein materialisierter Datensatz mit Filtern braucht vorher eine Übersetzung für pgstac (CQL2) bzw. die SQL-Coverage: eigene Aufgabe.

## 5. Coverage (DS-02b, 28.10.2026)

1. **Parameter:** `GET /coverage/{dataset_id}` nimmt `query` als JSON in der Form der STAC-Query-Extension (Plan §6.4, Regel 7). `max_cloud_cover` entfällt (Otto, Frage 3).
2. **Gleiche Prüfung wie die Suche:** Die Route liest `query` mit `api.search_filters.read_search_conditions`, mit dem Datensatz als einziger Collection. Was die Registry des Datensatzes nicht nennt (Eigenschaft, Operator, Typ, Bereich, `earthx:`), ist `400` ohne Wert im Text. Ein Filter, den der Datensatz nicht kennt, ist hier auch `400` und kein Eintrag in `ignored_filters`, weil die Route genau einen Datensatz fragt. Ein Datensatz ohne Filter, auch der Flächenweg des DEM, weist jedes `query` ab; `area_coverage` verweigert Bedingungen zusätzlich selbst, weil sein Cache-Schlüssel sie nicht kennt.
3. **Modell:** `CoverageQuery.conditions` (`catalog.search_filters`) ersetzt `max_cloud_cover`; `is_unfiltered` ist nur ohne Bedingungen wahr, ein gefilterter Weltblick bekommt also nicht die Lebensdauer von einem Tag (Otto, F3 vom 20.09.2026).
4. **Quelle:** `/aggregate` bekommt `query` als JSON-Parameter, geschrieben von `earth_search.query_extension`, derselben Funktion wie die Suche. Die URL-Grenze der Quelle (adr/0004 §3.4) gilt weiter; ein gekürzter Umriss behält die Filter.
5. **Cache:** Der Schlüssel nimmt `conditions_key` nur auf, wenn Bedingungen gesetzt sind; anders gefilterte Karten sind andere Einträge, dieselben Bedingungen in anderer Reihenfolge ein Eintrag. Der Wegfall des festen Feldes `cloud` ändert die Hashes aller bisherigen Einträge einmal; sie laufen aus (E5, kein Fehler).
6. **Fehler der Quelle (Otto, C):** unverändert `502`/`504` mit eigenem Text; Auszug und Filterwerte erscheinen weder in der Antwort noch im Log. Das Log der Route nennt höchstens die Namen der gesetzten Filter.
7. **Live-Abgleich:** `backend/tests_live/test_search_filters_live.py` prüft zusätzlich, dass die Aggregation mit jedem Filter genau so viele Szenen zählt, wie die Suche findet (Plan §6.2: 42/7/21/24).
