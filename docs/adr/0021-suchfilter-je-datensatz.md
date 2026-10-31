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
- **Nicht abgebrochen, sondern zu Ende gelesen:** Messungen, die beim Ende einer Antwort noch laufen, werden nicht abgebrochen (ein Abbruch mitten in der Datenbankabfrage hinterließ kaputte Verbindungen, gemessen als psycopg-Warnungen). Sie lesen zu Ende und speichern ihren Wert; die nächste Antwort fragt genau diese Szenen zuerst und bekommt sie aus dem Cache, sobald sie fertig sind. Fragt das Frontend sofort weiter, kann eine noch laufende Szene ein zweites Mal gemessen werden (offen, kostet nur Zeit). Beim Ende des Prozesses wartet der Lifespan bis zu 10 s darauf (`settle()`), bevor er den Pool schließt.
- **Marke und Suche:** Der Schlüssel der Marke nimmt den Fingerabdruck der Suche der Quelle (Zeitraum, Fläche, `ids`, übrige Filter) auf. Ohne das erkennt erst die Marke der Quelle ab der zweiten Seite, dass die Suche eine andere ist.
- **Budget:** Mit weniger als 2 s Rest holt eine Antwort keine neue Seite der Quelle mehr, damit eine kalte Seite die 10 s der gemischten Suche nicht sprengt.
- **Leser:** Die Threads, die Raster lesen, laufen in einem eigenen `CapacityLimiter` (so groß wie die Leser je Host); wer auf einen Leser wartet, wartet in der Ereignisschleife und belegt keinen Thread des gemeinsamen Pools.
- **Wert und Filter stimmen überein:** Der Bereich gilt für den Anteil mit einer Nachkommastelle, wie ihn die Antwort zeigt.
- **Log (KE3):** eine Zeile „aoi cloud filter“ je Antwort mit Datensatz, geprüft, gefunden, aus dem Cache, unlesbar, Grenze erreicht, Stufen (Zahl der Szenen je Auflösung) und Sekunden.
- **Adressen im Log (neu):** GDAL schreibt bei einem Lesefehler die ganze Adresse der Datei in eine Warnung, und `rasterio` gibt sie an das Logging weiter (gemessen). Die Messung filtert sie deshalb aus dem Log, nur in dem Thread, der gerade misst. Der `tiler` und der `worker` lesen ohne Filter; das löst NM4-57 für alle Prozesse (Otto, 30.10.2026), hier ist nichts weiter geändert.
  **Nachtrag NM4-57:** Der Thread-Filter ist entfernt. An seiner Stelle ersetzt der JSON-Formatter jeder Zeile (`earthx.logging.hide_addresses`) jede URL und jeden GDAL-Pfad (`/vsicurl/…`, `/vsis3/…`) in Meldung, Traceback und Textfeldern durch `<address>`; der Handler von uvicorn bekommt denselben Filter, und das Kind des `worker`, das ohne die Einrichtung des Supervisors startet, richtet das Logging selbst ein. Nicht verdeckt bleiben Host und Port in der Meldung `CURL error: Failed to connect to … port …`.
- **`next`-Link:** Er wiederholt den POST-Body, auch `intersects` und `earthx:aoi`. Otto, 30.10.2026: so lassen, die AOI steht nur im Body, nie in URL oder Log.
- **Live-Smoke:** `backend/tests_live/test_aoi_cloud_filter_live.py` läuft im Job `earth-search` von `.github/workflows/live-smoke.yml` (ausdrückliche Ausnahme Ottos für `.github/`, 30.10.2026).
- **Coverage:** `/coverage` weist den Filter mit `400` ab (KE6).
- **Prüfung an der echten Quelle (einmalig, von Hand, 30.10.2026):** an einer Szene mit 43 % Wolken liegt der Anteil über die ganze Datei bei 43,332 %, `eo:cloud_cover` ist 43,33207; auf der gröbsten Stufe (320 m) über den Fußabdruck 43,3 %. Eine Suche über 42 Szenen (Alpen, Juni 2024, 10-km-AOI) prüfte alle in 5 s mit sechs Lesern und fand sieben mit höchstens 50 %.

**Umsetzung DS-03b (31.10.2026, Plan §6.17):**
- **Frontend:** Der Schalter „Within AOI“ steht in „Advanced search“ unter dem Filter, an dem `within_aoi` gesetzt ist; ohne AOI, Zeitraum mit beiden Enden oder bei einer Punkt-AOI ist er gesperrt, mit dem Grund im Tooltip. Sonst kennt kein Frontend-Code einen Datensatz: Klassen und Satz zu den Grenzen kommen aus `earthx:mask.cloud_classes` und `cloud_note`.
- **Anfrage:** Bei aktivem Schalter steht der Bereich unter `earthx:aoi_cloud_cover` statt unter dem Filter der Szene; bei einer AOI mit mehr als 1 000 Positionen geht `bbox` und die AOI als `earthx:aoi` im Body. Der Datums-Fallback läuft dann nicht, die Coverage bekommt den Bereich nicht.
- **Ablauf:** Das Frontend fragt mit der Marke weiter, zeigt „n found / m checked“ nach jeder Antwort, kann mit „Stop“ abbrechen und lässt Gefundenes und Marke stehen. Zeile und Gruppe zeigen „☁ n %“, die Sortierung „Clouds in AOI“ ordnet nur die Anzeige.
- **Entschieden (Otto, 31.10.2026, zu #265):** Der Hinweis zur Grenze nennt kein Datum. Eine AOI mit mehr als 20 000 Positionen sperrt den Schalter mit Grund im Tooltip (das `400` des Servers bleibt als Sicherung). Ein Lauf, den „Stop“ vor dem ersten Treffer beendet, zeigt die Liste mit „0 found / m checked“ und „Load more“.
- **Review Otto (31.10.2026, zu #265), ersetzt für diese Punkte die Zeilen davor:**
  - Entfernt: Sortierung „Clouds in AOI“ und „☁ n %“ in Zeile und Gruppe.
  - Der Schalter heißt „Filter within AOI only“, steht ganz oben im Popup und gilt je Datensatz für alle flächenabhängigen Filter. Die Registry nennt je Filter die Messung (`SearchFilter.within_aoi`: `AoiMeasure | None`, veröffentlicht als Eigenschaftsname oder `null`); das Frontend sendet den Bereich unter diesem Namen und kennt keinen Datensatz.
  - Neue Messung `earthx:aoi_nodata`: Anteil der AOI ohne gültiges Pixel aus SCL-Klasse 0 (`nodata` der Datei) derselben Lesung, `100 − data_percent`; Teile der AOI außerhalb der Kachel zählen als ohne Daten, eine Szene ohne gültiges Pixel hat 100. Kein zusätzliches Lesen, Cache-Schlüssel unverändert. Mehrere Bedingungen zugleich gelten als UND; die Seitenmarke nimmt alle Bereiche in ihren Hash (Marken von vorher werden mit `400` abgelehnt). `/coverage` weist beide Eigenschaften weiter ab, die Coverage-Karte zeigt mit dem Schalter nur die Filter ohne Flächenbezug.
  - Gemessen: 0,41 µs je Szene für die Ableitung, rund 0,6 µs mehr je Szene für die zweite Bedingung, gleiche Zahl Lesungen (300 bei 300 Szenen, mit einem, beiden oder nur dem No-data-Filter) gegen rund 20 ms je Lesung mit Zählung.
  - Gleich streng wie der Wolkenanteil: Beide Messungen verlangen eine Klassifizierung mit nicht leeren `cloud_classes` (COG). Eine Lockerung wäre eine eigene Entscheidung.

## 7. Oberfläche (DS-02c, 30.10.2026)

Plan: `docs/plans/ds/ds-02-advanced-search.md` §6.7, §6.8, §6.11. Keine neue Entscheidung, die der Plan nicht trägt; die Abweichungen stehen in §6.11.

1. **Quelle der Filter:** allein `earthx:search_filters` der Collection (`frontend/src/searchFilters.ts`). Ein Eintrag, dem eine Angabe fehlt, wird ausgelassen, nicht ergänzt. Kein Code kennt eine Eigenschaft oder einen Datensatz.
2. **Sucheinstellung je Datensatz:** `searchFilters[datasetId][property]` im Store, mit dem Text der Felder. Wirkt nur für gewählte Datensätze, bleibt bei Abwahl und bei „Clear search results“ stehen, wird nicht im Browser gemerkt und geht nicht in den Permalink.
3. **Auf der Leitung:** Suche, „Load more“, Datums-Fallback und die Footprints der Coverage senden `query_by_collection` (§2.4), jeder Datensatz nur seine Filter; die Coverage sendet `query` (§5). Ein Filter mit falschem Feld wird nicht gesendet.
4. **Coverage-Speicher:** der Schlüssel der gemerkten Antworten für einen Ausschnitt enthält die Filter; eine andere Filterung ist eine andere Karte.
5. **Umschalter:** `DatasetSelect` wird von „Showing dataset“ (Results) und „Advanced search“ geteilt.
6. **Änderung nach dem Review (Otto, 30.10.2026, zu #239):** Nicht mehr ein Aufklapper im scrollenden Menü, sondern ein Knopf über „Search“ („Advanced search · N“, N = gesetzte Filter) und ein Popup mit Umschalter, den Filtern unter den Überschriften der Registry, „Reset filters“ und „Done“ (`components/AdvancedSearch.tsx`, `Popover` mit `form`). Die Werte gehören dem Store, nicht dem Popup; alles andere in diesem Abschnitt gilt unverändert. Die Gliederung kommt aus `SearchFilter.group` (§8).

## 8. Nachtrag DS-02c: alle filterbaren Felder von Earth Search (Sentinel-2 L2A, 30.10.2026)

Anlass: Otto (Review zu #239, 30.10.2026): alle Felder erfassen, die die Quelle filtern kann, und aufnehmen, was wirkt und Nutzern etwas nützt. Messskript: `scripts/ds-02-filters/measure.py`.

**Verfahren (Einmal-Schritt nach `adr/0002`).** Das Skript macht keinen eigenen Aufruf: Die Antworten sind vorher mit `curl` gespeichert (Befehle im Kopf des Skripts), danach liest `inventory` sie, `commands` schreibt die Probe-Befehle, `analyze` vergleicht. Stichprobe: 756 Items aus 7 Gebieten zu einem Grad Kantenlänge (Alpen, Amazonas, Sahara, Norwegen, Portugal-Küste, Ganges, Australien) in zwei Jahreszeiten (Juni und Dezember 2024), dazu Probemonate 2017–2026 für die Werte der Baseline und die Queryables der Collection. Je Kandidat und Gebiet drei Filter (ab Median, bis Median, zwischen den Quartilen) bzw. je Wert einer; **252 Suchen**. Ein Feld **wirkt**, wenn jede Antwort genau die Szenen enthält, die die ungefilterte Stichprobe für diesen Filter vorhersagt, und mindestens ein Filter die Trefferzahl senkt.

**Befunde.**
- Die Queryables der Quelle nennen weiter nur `eo:cloud_cover`; die Items tragen 44 Eigenschaften.
- Alle 18 Kandidaten wirken. Eine Eigenschaft, die ein Item nicht trägt, schließt es aus (so bei `s2:dark_features_percentage`).
- `eo:cloud_cover` ist exakt `s2:medium_proba_clouds_percentage + s2:high_proba_clouds_percentage + s2:thin_cirrus_percentage` (größte Abweichung 1·10⁻⁵ bei 756 Items); die Wolkenschatten zählen nicht mit.
- **Baselines** der Items nach Zeit: 05.00 (2018–2021), 05.09 (2023), 05.10 (bis 06/2024), 05.11 (ab 09/2024), 05.12 (ab 02/2026), 05.13 (10/2026). Neue Versionen kommen alle paar Monate: Die Liste der Registry braucht dann eine Zeile, der Live-Test nennt den Wert.
- `s2:dark_features_percentage` tragen nur Items bis Baseline 05.10 (364 von 756; ab 09/2024 keines).

| Eigenschaft | Typ | Bereich in der Stichprobe | wirkt | Entscheidung | Beschriftung · Einheit · Gruppe |
|---|---|---|---|---|---|
| `eo:cloud_cover` | Zahl | 0 … 100 | ja | **aufgenommen** | Cloud cover · % · Clouds |
| `s2:thin_cirrus_percentage` | Zahl | 0 … 71,9 | ja | **aufgenommen** (Otto: dünne Zirren) | Thin cirrus · % · Clouds |
| `s2:cloud_shadow_percentage` | Zahl | 0 … 27,3 | ja | **aufgenommen** (Otto: Wolkenschatten) | Cloud shadow · % · Clouds |
| `s2:nodata_pixel_percentage` | Zahl | 0 … 99,9 | ja | **aufgenommen** (DS-02a) | No data · % · Scene |
| `s2:snow_ice_percentage` | Zahl | 0 … 53,9 | ja | **aufgenommen** (Otto: Schnee/Eis) | Snow and ice · % · Scene |
| `s2:water_percentage` | Zahl | 0 … 89,1 | ja | **aufgenommen** (Otto: Wasser) | Water · % · Scene |
| `s2:vegetation_percentage` | Zahl | 0 … 99,9 | ja | **aufgenommen** (Otto: Vegetation) | Vegetation · % · Scene |
| `s2:not_vegetated_percentage` | Zahl | 0 … 100 | ja | **aufgenommen** (Gegenstück zur Vegetation: Boden, Bebauung) | Not vegetated · % · Scene |
| `s2:degraded_msi_data_percentage` | Zahl | 0 … 14,8 (83 % der Items > 0) | ja | **aufgenommen** (Qualitätsfilter, `projektuebersicht.md` §7) | Degraded data · % · Scene |
| `platform` | Wert | `sentinel-2a`, `-2b`, `-2c` | ja | **aufgenommen** (DS-02a) | Satellite · Acquisition |
| `view:sun_elevation` | Zahl | 4,6 … 75,1 (Skala 0 … 90) | ja | **aufgenommen** (Otto: Sonnenhöhe) | Sun elevation · ° · Acquisition |
| `view:sun_azimuth` | Zahl | 29,7 … 177,7 (Skala 0 … 360) | ja | **aufgenommen** (Otto: Sonnenazimut) | Sun azimuth · ° · Acquisition |
| `s2:processing_baseline` | Wert | 05.00 … 05.13 (6 Werte) | ja | **aufgenommen** (Otto: Verarbeitungs-Baseline) | Processing baseline · Acquisition |
| `s2:dark_features_percentage` | Zahl | 0 … 1,8 | ja, nur für Items, die es tragen | **nicht aufgenommen:** fehlt in allen Items ab Baseline 05.11; ein Filter schlösse jede neuere Szene ohne Hinweis aus | |
| `s2:medium_proba_clouds_percentage`, `s2:high_proba_clouds_percentage` | Zahl | 0 … 100 | ja | **nicht aufgenommen:** Teile von „Cloud cover“, ohne eigenen Nutzen neben diesem und „Thin cirrus“ | |
| `s2:unclassified_percentage` | Zahl | 0 … 18,9 | ja | **nicht aufgenommen:** Rest der Klassifizierung, ohne Frage, die ein Nutzer damit stellt | |
| `grid:code` (MGRS-Kachel) | Text | 36 Werte in der Stichprobe, weltweit Tausende | ja | **nicht aufgenommen:** wirkt, braucht aber ein Textfeld statt einer Liste (neue Art `FilterKind`); Frage an Otto | |
| `mgrs:utm_zone`, `mgrs:latitude_band`, `mgrs:grid_square`, `proj:epsg` | Zahl/Text | | – | **nicht aufgenommen:** Teile der Kachel, technisch | |
| `view:azimuth`, `view:incidence_angle` | Zahl | 97,5 … 300,3 · 2,7 … 11,8 | – | **nicht aufgenommen:** Blickgeometrie, bei Sentinel-2 nahezu senkrecht | |
| `s2:reflectance_conversion_factor` | Zahl | 0,968 … 1,034 | – | **nicht aufgenommen:** technischer Faktor | |
| `s2:saturated_defective_pixel_percentage`, `constellation`, `instruments`, `s2:datatake_type`, `s2:product_type`, `storage:*` | | ein Wert in jedem Item | – | **nicht aufgenommen:** Konstanten | |
| `created`, `updated`, `datetime`, `s2:generation_time` | Zeitstempel | | – | **nicht aufgenommen:** Zeitstempel (`datetime` hat sein eigenes Feld) | |
| `earthsearch:payload_id`, `s2:product_uri`, `s2:tile_id`, `s2:datastrip_id`, `s2:datatake_id` | Text | je Item eigener Wert | – | **nicht aufgenommen:** Kennungen | |
| `processing:software`, `proj:centroid` | Objekt | | – | **nicht aufgenommen:** Objekte, nicht filterbar als Wert oder Bereich | |

**Folgen.**
1. `SearchFilter` bekommt `group` (ohne Vorgabewert, beim Start geprüft: kurzer nicht leerer Text, die Filter einer Gruppe stehen beieinander). Die Collection veröffentlicht es als `group`; die Oberfläche gliedert danach und zeigt Überschriften nur bei mehr als einer Gruppe. Die Reihenfolge der Registry ist die Reihenfolge der Anzeige.
2. Sentinel-2 L2A bietet 13 Filter in den Gruppen „Clouds“ (3), „Scene“ (6), „Acquisition“ (4); Wolken zuerst.
3. Der Live-Test prüft jetzt für jeden Filter, dass die Quelle genau so viele Szenen findet, wie die Stichprobe sagt (beide Hälften eines Bereichs am Median, bei einer Auswahl der häufigste Wert und ein nicht vorhandener), und meldet für Auswahlfilter jeden Wert der letzten 30 Tage, den die Registry nicht kennt. Die Offline-Wiedergabe prüft beides auch mit einer Quelle, die ein Filter überhört bzw. einen neuen Wert liefert.
4. Die Zeitgrenze der Stichprobe bleibt ein geschlossenes Fenster (`adr/0005` K5); nur die Prüfung auf neue Werte schaut auf die letzten 30 Tage.
5. **Filter nach MGRS-Kachel: nicht jetzt** (Otto, 30.10.2026, Option 1). Wer eine Kachel will, nimmt den Szenennamen; eine Art `TEXT` kommt erst bei belegtem Bedarf (Backlog Nr. 58).

## 9. Nachtrag NM4-57: Coverage ohne AOI in der URL (30.10.2026)

- `POST /coverage/{id}` nimmt `query` als Objekt im Body; im `GET` bleibt es JSON-Text (§5 Nr. 1). Dieselbe Prüfung (§5 Nr. 2), ein Fehler im Body ist `400` ohne Wert im Text, nie das `422` von FastAPI, dessen Detail die Eingabe wiederholt.
- Die Begründung und die Regel für das `GET` (nur der Kartenausschnitt) stehen in `adr/0004`, „Nachtrag NM4-57“.
- `POST /aoi/upload?filename=…`: Die Oberfläche sendet nur `aoi.<Endung>` (Otto, 30.10.2026); der Dateiname enthält oft Personenbezug und stünde im Zugriffslog. Host und Port in `CURL error: Failed to connect to …` bleiben im Log (Otto, 30.10.2026).
