# ADR 0020 — Suchfilter je Datensatz

- **Status:** Entwurf. Die Entscheidungen hat Otto am 28.10.2026 mit dem Plan von DS-02 getroffen (`docs/plans/ds/ds-02-advanced-search.md` §6, freigegeben zu #217). Dieses ADR hält sie als Architekturentscheidung fest; Begründung, Optionen und Messungen stehen im Plan.
- **Datum:** 2026-10-28
- **Aufgabe:** DS-02a (Backend Suche). DS-02b (Coverage) und DS-02c (Oberfläche) folgen als eigene PRs.

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
- DS-02b ersetzt `max_cloud_cover` an `/coverage` durch dieselben Bedingungen. DS-02c baut die Oberfläche mit Umschalter je Datensatz.
- Ein materialisierter Datensatz mit Filtern braucht vorher eine Übersetzung für pgstac (CQL2) bzw. die SQL-Coverage: eigene Aufgabe.
