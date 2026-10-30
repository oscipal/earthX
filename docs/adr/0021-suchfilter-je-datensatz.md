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

## 6 Nachtrag DS-03 — Wolkenanteil in der AOI (Entwurf, 29.10.2026)

Plan, Messungen und Optionen: `docs/plans/ds/ds-03-wolken-in-aoi.md` §6. Messskript: `scripts/ds-03-clouds/measure.py`.

**Entschieden (Otto, 29.10.2026, zu #235):**
1. **Rechnung:** Anteil der Wolkenklassen an den gültigen Pixeln der Klassifizierung in der AOI.
   - Stufe: die gröbste Übersicht, auf der die AOI noch mindestens 10 000 Pixel hat, sonst die volle Auflösung.
   - Gemessen bei gemischtem Himmel: im 95. Perzentil höchstens 1,1, im Maximum 1,9 Prozentpunkte neben der vollen Auflösung.
2. **Klassen** stehen als Daten in der Registry (`MaskSource.cloud_classes`). Sentinel-2: 8, 9, 10, dieselbe Definition wie `eo:cloud_cover` (gemessen bei 48 von 48 Szenen gleich); Schatten zählen nicht mit.
3. **Nenner:** gültige Pixel (nicht `nodata`). Ohne gültiges Pixel in der AOI gibt es keinen Wert. Der Anteil der AOI mit Daten wird mitgeliefert.
4. **Überflug:** Der Wert einer Gruppe kommt aus den Zählungen ihrer Szenen.
5. **Schnitt:** DS-03a Backend, DS-03b Frontend nach DS-02c.
6. **Ort des Filters (Frage 2, Option 2):** Der Filter wirkt in der Suche, nicht als eigene Route.
   - Er ist ein Schalter „Within AOI“ am Wolkenfilter und braucht AOI und Zeitraum.
   - Der Server prüft die Treffer der Quelle seitenweise und gibt nur passende zurück, jeden mit seinem Wert.

**Entschieden mit der zweiten Freigabe (Otto, 29.10.2026, zu #235; Plan §6.5, §6.9, §6.15):**
7. **Form:** Eigenschaft `earthx:aoi_cloud_cover` (`gte`/`lte`, 0–100) in `query_by_collection` bzw. `query`. In der Registry `SearchFilter.within_aoi` an dem Filter, dessen Bereich für die AOI gelten kann. Gültig nur mit Zeitraum (beide Enden) und Fläche, sonst `400`.
8. **Kurze Antworten:** höchstens 100 geprüfte Szenen oder 8 s je Antwort, darin „found / checked“ (`earthx:aoi_filter`). Die Seitenmarke trägt die Stelle in der Seite der Quelle und die Zähler. Das Frontend fragt selbst weiter, bis die Seite gefüllt oder die Obergrenze erreicht ist, abbrechbar; eine leere Seite mit nur „Load more“ kommt nicht vor.
9. **Obergrenze und Zeitraum:** 500 geprüfte Szenen je Suche, über „Load more“ hinweg, danach Hinweis. Keine Höchstlänge des Zeitraums.
10. **Last:** Messung im Prozess `api`, höchstens 6 gleichzeitige GDAL-Leser je Host und Prozess (`gateway.ReadSlots`, die Grenze von `adr/0005` §6).
11. **Cache:** Messung je Szene und AOI im Statistik-Cache, 7 Tage. Gefilterte Seiten kommen nicht in den Such-Cache. Der Schlüssel steht nie in Log oder URL.
12. **Mehrere Datensätze:** Filter je Datensatz, nur wo die Registry `within_aoi` setzt; Grenze und Fortschritt je Datensatz.
13. **Lange AOI:** Schickt die Suche das umgebende Rechteck (mehr als 1 000 Positionen), misst die Plattform das echte Polygon aus dem Body (`earthx:aoi`, höchstens 20 000 Positionen). Vereinfachen ist bis dahin nicht nötig (gemessen höchstens 50 ms je Maske). Eine Punkt-AOI sperrt den Filter.
14. **Schnitt:** DS-03a1 (Registry, Zählung in `access`, `gateway.ReadSlots`, Cache-Schlüssel), DS-03a2 (Filter in der Suche) in neuer Session, DS-03b (Frontend) nach DS-02c.

**Folgen:**
- Die Reservierung `earthx:` (§2.7) wird für `earthx:aoi_cloud_cover` eingelöst; andere `earthx:`-Eigenschaften bleiben `400`.
- Die Coverage-Karte kann den Filter nicht anwenden und zeigt mit „Within AOI“ nur die übrigen Filter.

**Umsetzung DS-03a1 (29.10.2026, Plan §6.19):**
- **Registry:** `MaskSource.cloud_classes` und `cloud_note`, `SearchFilter.within_aoi`, je ohne Vorgabewert und beim Start geprüft. Wolkenklassen sind nur für eine COG-Schicht erlaubt.
- **Collection:** veröffentlicht `earthx:mask.cloud_classes`, `earthx:mask.cloud_note` und `within_aoi` je Filter.
- **`access.aoi_clouds`:** Stufenwahl und Zählung. Nur der Teil der AOI auf der Kachel wird maskiert, der Rest geht über seine Fläche ein. Dazu der Cache-Schlüssel je Szene und AOI.
- **`gateway.ReadSlots`:** höchstens `max_connections_per_host` gleichzeitige GDAL-Leser je Host.
- Noch nutzt keine Route das; das folgt mit DS-03a2.

**Umsetzung DS-03a2 (30.10.2026, Plan §6.18):**
- **Lesen der Anfrage (`api.search_filters`):** `earthx:aoi_cloud_cover` ist für jede Collection erlaubt, deren Registry `within_aoi` an einem Filter setzt; er nimmt den Bereich dieses Filters. Er steht getrennt von den Bedingungen der Quelle (`SearchConditions.aoi_cloud_cover`) und geht nie an die Quelle. Jede andere `earthx:`-Eigenschaft bleibt `400`. `earthx:aoi` gehört wie `query` nur in den Body von `POST /stac/search`.
- **Bedingungen (`api.aoi_cloud_filter.read_aoi_request`):** Zeitraum mit beiden Enden (ein Zeitpunkt zählt nicht); Fläche als `Polygon`/`MultiPolygon` aus `intersects` oder als `bbox`, bei zu langer AOI das echte Polygon aus `earthx:aoi` (innerhalb von `bbox`, höchstens 20 000 Positionen, gültig, auf dem Globus). `earthx:aoi` ohne den Filter, zusammen mit `intersects` oder ohne `bbox` ist `400`, ebenso eine Collection, deren Items die Plattform selbst hält, und ein Body über 1 MB. Kein Text nennt einen Wert.
- **Prüfschleife (`run_filter`):** Seiten der Quelle zu 100 mit den übrigen Filtern und dem Such-Cache; die Szenen in der Reihenfolge der Quelle, bis zu sechs zugleich gemessen. Die Antwort endet bei `limit` Treffern, 100 geprüften Szenen, 8 s, 500 geprüften Szenen je Suche oder am Ende der Quelle. Die Stelle rückt erst über eine Szene hinweg, wenn sie geprüft ist; die nächste Antwort lässt keine aus und wiederholt keine.
- **Marke:** eine eigene Hülle um die Marke der Quelle, `{"v": 1, "k": "aoi", "h", "p", "i", "c", "f", "u"}`: Hash aus Collection, Bereich und AOI (keine Koordinate), Marke der Seite der Quelle, Stelle in der Seite, Zähler. Die Marke der Quelle bleibt `TOKEN_VERSION` 2 und ohne AOI-Filter unverändert. Eine Marke ohne den Filter ist bei einer Suche mit ihm `400` und umgekehrt, ebenso die Marke einer anderen AOI oder eines anderen Bereichs. Bei 500 geprüften Szenen gibt es keine Marke mehr; stünde die Quelle genau dort am Ende, ist die Grenze nicht erreicht.
- **Gemischte Suche:** Die Marke je Quelle trägt dieselbe Hülle; der Fingerabdruck der gemischten Suche nimmt den Schlüssel des Filters auf (ohne Filter unverändert). Nur die Quelle mit dem Filter misst, im Budget von 10 s je Quelle. Die Zähler stehen unter `earthx:aoi_filter` (eine Quelle) bzw. `earthx:aoi_filter_by_collection`.
- **Messung (`AoiMeasurer`):** Cache zuerst (Statistik-Cache, 7 Tage, nur die vier Zahlen; ein Eintrag, der keiner ist, zählt als Fehlgriff), sonst Lesen im Thread innerhalb eines `ReadSlots`-Platzes und der GDAL-Optionen des `gateway`. Eine Szene ohne Asset, mit verweigerter Adresse oder mit Lesefehler zählt als unlesbar. Ein Fehler des Caches macht nur langsamer, geloggt wird seine Art.
- **Nicht abgebrochen, sondern zu Ende gelesen:** Messungen, die beim Ende einer Antwort noch laufen, werden nicht abgebrochen (ein Abbruch mitten in der Datenbankabfrage hinterließ kaputte Verbindungen, gemessen als psycopg-Warnungen). Sie lesen zu Ende und speichern ihren Wert; die nächste Antwort fragt genau diese Szenen zuerst und bekommt sie aus dem Cache.
- **Wert und Filter stimmen überein:** Der Bereich gilt für den Anteil mit einer Nachkommastelle, wie ihn die Antwort zeigt.
- **Log (KE3):** eine Zeile „aoi cloud filter“ je Antwort mit Datensatz, geprüft, gefunden, aus dem Cache, unlesbar, Grenze erreicht, Stufen (Zahl der Szenen je Auflösung) und Sekunden.
- **Adressen im Log (neu):** GDAL schreibt bei einem Lesefehler die ganze Adresse der Datei in eine Warnung, und `rasterio` gibt sie an das Logging weiter (gemessen). Die Messung hängt deshalb an die Logger von `rasterio` einen Filter, der jede Zeile mit einer Adresse verwirft. Der `tiler` liest ohne diesen Filter; das wurde hier nicht geändert.
- **Coverage:** `/coverage` weist den Filter mit `400` ab (KE6).
- **Prüfung an der echten Quelle (einmalig, von Hand, 30.10.2026):** an einer Szene mit 43 % Wolken liegt der Anteil über die ganze Datei bei 43,332 %, `eo:cloud_cover` ist 43,33207; auf der gröbsten Stufe (320 m) über den Fußabdruck 43,3 %. Eine Suche über 42 Szenen (Alpen, Juni 2024, 10-km-AOI) prüfte alle in 5 s mit sechs Lesern und fand sieben mit höchstens 50 %.
