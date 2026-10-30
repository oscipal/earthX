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

