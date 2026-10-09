# M3-11c — Coverage über eigene Items (`local-sql`): Plan-Schritt

**Status (26.09.2026):** Plan-Schritt, wartet auf Ottos Freigabe (§8).
**Aufgabe:** M3-11c aus `docs/plans/m3-dritte-quelle-und-interface.md` §4
(P24, K-06). **Stufe B.** Hängt an M3-11a (gemergt, #95); läuft parallel zu
M3-11b.
**Grundlagen:** `adr/0004` §3.5, §3.6, §5 (Regel V, Einmal-Produkte, 500 kB);
`adr/0009` §6 (F5), §8 Punkt 5, §10.3; `plans/m3-02-konformitaetsbericht.md`
K-06, K-08, F-07; `plans/m3-19-weltueberblick-ausschnitt.md`;
`plans/m3-11a-materialisierte-quellen.md`; `KLAERUNGEN.md` B10, B13;
`ENTSCHEIDUNGEN_2026-09-18.md` §2 (Coverage Map).

Belegstufen wie in `adr/0009`: **M** gemessen in dieser Sitzung, **P** am
Quelltext gelesen (Stand `main` 1b66759), **A** eigene Ableitung.

---

## 1. Ziel

Die Coverage einer materialisierten Collection kommt aus ihren eigenen Items in
pgstac. Für ein Einmal-Produkt wie den DEM ist das die **Vereinigung der
Footprints als Fläche** mit `completeness = complete` (Otto, 23.09.2026,
`adr/0009` §6 F5). Die Coverage-Route wählt ihren Weg aus dem Registry-Eintrag
und ist nicht mehr fest auf Earth Search und EOPF verdrahtet (K-06).

---

## 2. Befund am Code — **[P]**

- **`local-sql` antwortet `501`.** `api/coverage_route.py` Z. 56:
  `IMPLEMENTED_PROVIDERS` enthält nur `upstream-aggregation` und `sample`;
  Z. 89–98 weist alles andere mit `501` ab.
- **Einmal-Produkte antworten heute mit der `bbox` der Collection.**
  Z. 86–87 prüft `single_coverage_product` vor dem Provider und gibt
  `extent_result(config.spatial_extent.bbox)` zurück
  (`catalog/coverage.py` Z. 335). Ein DEM-Eintrag aus M3-11b
  (`single_coverage_product = True`, `local-sql`) bekäme damit ohne diese
  Aufgabe die globale `bbox`: Meere und die Lücke über dem Südkaukasus
  erschienen als abgedeckt. Genau das schließt F5 aus.
- **K-06:** Z. 116–117 wählt die Funktion nur nach Provider:
  `aggregate_coverage if is_upstream else sample_coverage`.
  `upstream-aggregation` heißt damit immer Earth Search, `sample` immer EOPF.
  Die Suche wählt den Adapter dagegen über `AdapterKind`
  (`adapters/__init__.py`, `_ADAPTERS`).
- **Registry:** Seit M3-11a gilt `materialized` ⇔ `local-sql`
  (`catalog/registry.py`, `_check_item_holding`). `single_coverage_product`
  mit `upstream-aggregation` ist verboten (`_check_coverage`).
- **Datenbank im Prozess `api`:** Der kleine `psycopg`-Pool
  `app.state.earthx_cache_pool` (`api/dependencies.py`, höchstens
  5 Verbindungen) trägt heute den Such-Cache. Sein Kommentar sagt „never
  pgstac's own item storage“; im `tiler` liest M3-11a darüber aber schon Items
  (`catalog.pgstac.fetch_item`).
- **pgstac-Tabelle:** `pgstac.items` ist nach Collection partitioniert und hat
  je Partition einen GiST-Index auf `geometry` und einen B-Tree auf
  `(datetime DESC, end_datetime)` **[M]** (in der Sitzungsdatenbank gelesen).
  pgstac selbst aggregiert nicht (`adr/0004` §3.5).
- **Onboarding-Punkt 2** (`tests/catalog/test_onboarding_checklist.py`
  Z. 149–169) überspringt Einmal-Produkte und liest sonst
  `IMPLEMENTED_PROVIDERS`.
- **Frontend:** `api.ts` spiegelt `_serialise` Feld für Feld
  (`CoverageResponse`). `extent` wird nirgends gezeichnet (F-07, M3-12).
- **`CoverageQuery`** lässt eine `bbox` mit `west > east` durch
  (`_check_area` prüft nur Wertebereiche und `south < north`). Der föderierte
  Weg reicht sie an die Quelle weiter.

---

## 3. Messung — **[M]**

Aufbau: die echte Kachelliste des DEM (`tileList.txt`, **eine** Anfrage an
`copernicus-dem-30m.s3.amazonaws.com`, 26 450 Zeilen, `Last-Modified`
unverändert 2022-05-09), daraus je Kachel ein 1° × 1°-Footprint aus dem Namen.
Lokales Postgres 16 mit PostGIS der Sitzung. Die Footprints wurden einmal in
eine Messtabelle und einmal als 26 450 synthetische Items (ohne Assets) in eine
Mess-Collection in pgstac geladen und danach wieder gelöscht. Keine Pixel,
keine weiteren Anfragen nach außen.

Zwei Footprint-Formen, weil M3-11b die Geometrie erst festlegt:

- **exakt:** Ecken auf ganzen Grad.
- **verschoben:** um einen halben Pixel verschoben, mit der
  breitenabhängigen Pixelbreite des DEM (3600 bis 360 Spalten je Grad). Das
  ist der ungünstigste plausible Fall: Die Ecken sind keine ganzen Zahlen mehr,
  und an den Grenzen der Breitenzonen entstehen kleine Stufen.

**Antwortgröße (ganze Welt, GeoJSON):**

| Footprints | Vereinigung | Rohgröße | 6 Nachkommastellen | + kollineare Punkte entfernt | + Toleranz 0,001° |
|---|---|---|---|---|---|
| exakt | 225 Polygone, 83 Löcher, 6 540 Punkte | 61 kB | — (ganze Zahlen) | **35 kB** (3 781 Punkte) | — |
| verschoben | 225 Polygone, 6 589 Punkte | 193 kB | 154 kB | **89 kB** | 87 kB |

Die Fläche liegt in jedem Fall weit unter 500 kB (`adr/0004` §5). Eine
Vereinfachung mit Toleranz bringt fast nichts (89 → 87 kB) und würde Kanten
verschieben. **Folge:** keine Vereinfachung mit Toleranz. Verlustfrei
genügen sechs Nachkommastellen (rund 0,1 m, feiner als ein halber Pixel des DEM)
und das Entfernen kollinearer Punkte (`ST_Simplify(g, 0)`). Die Fläche von
26 450 Quadratgrad bleibt dabei exakt erhalten (Gegenprobe `ST_Area`).

**Laufzeit** (`ST_Union` samt Zuschnitt und Ausgabe, lokale VM, warm):

| Ausschnitt | Items | pro Anfrage | aus vorberechneter Fläche | Antwort |
|---|---|---|---|---|
| ganze Welt, aus `pgstac.items` | 26 450 | **0,95–1,0 s** (2 Läufe) | 1 ms | 35 kB |
| ganze Welt, verschobene Footprints (Messtabelle) | 26 450 | 1,3 s | — | 89 kB |
| westliche Halbkugel | 10 688 | 374 ms | — | 20 kB |
| Europa (70° × 38°) | 1 737 | 61 ms | 2 ms | 2,6 kB |
| Alpenraum (12° × 6°) | 111 | 4,5 ms | 1 ms | 0,1 kB |

Die Ausschnitte entsprechen dem, was der Viewer seit M3-19 schickt: Ohne AOI ist
die `bbox` der sichtbare Ausschnitt, gerundet. Teuer ist nur die Weltansicht bei
Zoom 0–2. Sie liegt mit rund 1 s am Rand des Latenzziels K6 (unter 1 s, typisch
unter 0,5 s; `adr/0004` §7 Frage 4).

**Nebenbefunde:**

- `pgstac.partition_stats.last_updated` bleibt nach `create_items` leer
  **[M]**. Als Ladezeitstempel für einen Cache-Schlüssel taugt es nicht.
- `pgstac.create_items` mit allen 26 450 Items in **einem** Aufruf brauchte
  3 min 5 s **[M]**. `catalog.pgstac.upsert_items` schreibt in Blöcken zu
  1000 (M3-11a). Die Zahl ist nur ein Hinweis für M3-11b.

---

## 4. Vorgeschlagene Umsetzung

### 4.1 Dispatch nach Registry-Eintrag (K-06)

Die Route fragt zwei Angaben des Eintrags ab, nie die Kennung des Datensatzes:

| `coverage.provider` | `single_coverage_product` | Weg |
|---|---|---|
| `local-sql` | ja | **neu:** Fläche aus eigenen Items (§4.2) |
| `local-sql` | nein | Dichte aus eigenen Items — **nicht gebaut**, `501` (→ F4) |
| `upstream-aggregation` / `sample` | ja | unverändert: `bbox` der Collection |
| `upstream-aggregation` / `sample` | nein | unverändert, aber über den Adapter-Dispatch (unten) |

Für die beiden föderierten Wege kommt eine Funktion `adapters.coverage(query,
config, *, gateway, registry, cache)` neben `search_items`/`get_item`. Sie wählt
über eine Tabelle `(AdapterKind, CoverageProvider) → Funktion`:
`(earth-search-v1, upstream-aggregation) → aggregate_coverage`,
`(eopf-stac-v1, sample) → sample_coverage`. Ein Paar, das die Tabelle nicht
kennt, ist `CoverageProviderMismatch` (heute schon `501` in der Route). Ein
dritter föderierter Weg ist dann eine Zeile in `adapters`, keine Änderung der
Route. `local-sql` geht nicht über `adapters`: Die Fläche ist SQL in `catalog`
(`adr/0004` §5, „Wo welcher Teil liegt“), und `adapters` hat keine
Datenbankverbindung.

`IMPLEMENTED_PROVIDERS` bleibt für Onboarding-Punkt 2 unverändert. Punkt 2
überspringt Einmal-Produkte schon, der DEM fällt also nicht auf. Für `local-sql`
ohne `single_coverage_product` meldet Punkt 2 weiter „nothing answers“ (→ F4).

### 4.2 Die Fläche: SQL in `catalog`

Neues Modul `catalog/local_coverage.py` mit
`async def area_coverage(query, config, *, conn, cache=None) -> CoverageResult`.
Die Verbindung kommt aus dem vorhandenen `earthx_cache_pool` (→ F2). Der
Kommentar in `api/dependencies.py` wird angepasst. Ohne Pool antwortet die
Route `503` wie der `tiler` bei einem materialisierten Item (M3-11a).

Eine Abfrage, alle Werte als Parameter, nichts in den SQL-Text eingesetzt:

```sql
SELECT ST_AsGeoJSON(
         ST_ForcePolygonCCW(ST_Multi(ST_CollectionExtract(
           ST_Simplify(ST_Intersection(ST_Union(geometry), :clip), 0), 3))), 6),
       ST_Extent(geometry)                      -- nur für extent, siehe §4.3
FROM pgstac.items
WHERE collection = :dataset_id
  AND geometry && :clip
  AND datetime <= :end AND end_datetime >= :start;   -- nur mit Zeitfilter
```

- **Zuschnitt `:clip`:** die `bbox` als Rechteck; mit `west > east` (über die
  Datumsgrenze, STAC-Lesart) als zwei Rechtecke. Oder `intersects` als
  Geometrie. Ohne räumlichen Filter entfällt der Zuschnitt. Der Viewer schickt
  seit M3-19 immer eine `bbox` (AOI oder Ausschnitt). Die Antwort zeigt also die
  abgedeckte Fläche **innerhalb** der Anfrage.
- **Zeit:** dieselbe Überlappungsregel wie die STAC-Suche in pgstac
  (`datetime`/`end_datetime` des Items überschneidet das Anfragefenster). Die
  Fläche reagiert damit auf den Zeitfilter wie die Suche. Was das für den DEM
  heißt, hängt an der Zeitangabe der Items, die Otto in M3-11b entscheidet.
- **`ST_CollectionExtract(…, 3)`**, weil ein Zuschnitt an einer Kachelkante
  Linien oder Punkte erzeugen kann. **`ST_ForcePolygonCCW`**, weil RFC 7946
  äußere Ringe gegen den Uhrzeigersinn verlangt.
- **Keine Toleranz** (§3). Die Fläche deckt genau die Footprints; Lücken und
  Löcher bleiben erhalten.

Direkt auf `pgstac.items` statt über `pgstac.search()`: Die Suche liefert Item-
JSON, die Vereinigung braucht nur die Geometrie. Die Tabelle gehört zur gepinnten
pgstac-Fassung; `catalog.pgstac.check_pgstac_version` sichert das schon ab.

### 4.3 Antwortform (→ F1)

Vorschlag: ein neues Feld **`area`** in der bestehenden Antwort. Alles andere
bleibt wie bei der heutigen Antwort für Einmal-Produkte (`extent_result`):

```json
{
  "dataset_id": "…", "grid": "geotile", "level": 0, "counting": "centroid",
  "cells": [], "counted": 0, "total_count": null, "max_count": 0,
  "completeness": "complete",
  "histogram": [], "histogram_interval": "month",
  "footprints_advised": false, "from_cache": false,
  "extent": [west, south, east, north],
  "area": {"type": "MultiPolygon", "coordinates": [...]}
}
```

- `area` ist `null` bei allen anderen Wegen. Das ist für die bestehenden
  Antworten die einzige Änderung auf der Leitung, ein zusätzliches Feld.
- Leere Fläche (Meer, Zeitfilter ohne Treffer) ist
  `{"type": "MultiPolygon", "coordinates": []}` mit `extent: null`. So bleibt
  „Fläche, aber leer“ von „keine Flächenantwort“ unterscheidbar.
- `extent` ist die `bbox` der Fläche, nicht mehr die der Collection. Damit
  kann M3-12 auf die Fläche zoomen, ohne sie selbst zu vermessen.
- `completeness = complete` ohne Zählprobe, wie bei `extent_result`: Die
  Plattform besitzt alle Items (`adr/0009` §6). `total_count` bleibt `null`.
  Damit bleibt `footprints_advised` `false`: Die Fläche **ist** schon die
  Vereinigung der Footprints.
- `CoverageResult` bekommt ein Feld `area: Mapping | None`, `_serialise` gibt es
  aus. Im Frontend kommt nur die Zeile im Typ `CoverageResponse` dazu, damit der
  Spiegel stimmt. Gezeichnet wird in M3-12 (F-07).

### 4.4 Eingaben, die nicht passen

- **`max_cloud_cover`** auf dem Flächenweg → `400` (→ F5). Ein Einmal-Produkt
  hat keine Wolkenbedeckung. Sonst fiele jedes Item still heraus und die Karte
  wäre leer (K-08).
- **Ungültige `intersects`-Geometrie** (etwa ein Polygon mit Selbstschnitt):
  `ST_IsValid` vorab, sonst `400` mit festem Text. GEOS-Fehlermeldungen nennen
  die Koordinate des Fehlers („Self-intersection at or near point …“). Sie
  dürfen weder in die Antwort noch ins Log. Datenbankfehler werden deshalb nur
  mit ihrem Typ geloggt, nie mit Text oder Parametern.
- `bbox` und `intersects` prüft `CoverageQuery` wie bisher (Wertebereich,
  Ringe, beides zugleich → `400`).

### 4.5 Wo gerechnet wird (→ F2) und Cache (→ F3)

**Empfehlung: SQL bei jeder Anfrage, Ergebnis im vorhandenen Cache (E4).**

- Keine Kopplung an M3-11b: Der Einmal-Befehl muss nichts vorberechnen. Die
  beiden Aufgaben laufen parallel und berühren keine gemeinsame Funktion.
- Der Zeitfilter wirkt. Eine vorberechnete Fläche kennt nur „alle Items“.
- Teuer ist nur die Weltansicht (rund 1 s, §3). Die Ausschnitte des Viewers sind
  gerundet, dieselbe Weltansicht ist also ein Cache-Schlüssel für alle Nutzer.
- Vorberechnung bleibt der nächste Schritt, falls die echten 26 450 Items bei
  Otto lokal messbar zu langsam sind. Das ist kein Bau auf Vorrat
  (Log 26.09.2026 zum Zählwürfel).

Cache: `PostgresSearchCache` im Pool, Schlüssel `coverage:` + Hash der
normalisierten Anfrage, wie im föderierten Weg. Kein Koordinatenwert im
Schlüssel. Frist nach F3. Ein Ausfall des Cache macht die Antwort nur langsamer
(E5).

### 4.6 Log

Die Route schreibt wie bisher genau eine Zeile „coverage answered“ mit
`dataset`, `level`, `completeness`, `from_cache`. Neu kommt `answer: "area"`
dazu. Keine `bbox`, kein `intersects`, keine Fläche.

### 4.7 Doku

- `adr/0004` §5: Nachtrag, dass `local-sql` für Einmal-Produkte als Fläche
  gebaut ist (Antwortform, keine Toleranz, Messung aus §3).
- `architekturplan.md`: nur falls dort die Coverage-Antwort beschrieben ist.
  Das prüft die Umsetzung; der Plan-Schritt hat keine Stelle gefunden.
- Zeile in `ENTSCHEIDUNGSLOG.md` mit Ottos Antworten.

---

## 5. Tests

Alle Fixtures synthetisch. Eine materialisierte Test-Collection mit
`single_coverage_product = True` und wenigen 1°-Kacheln aus erfundenen
Positionen: ein Block aus 2 × 2 Kacheln, eine einzelne Insel, ein Ring aus acht
Kacheln mit Loch in der Mitte, eine Kachel an der Datumsgrenze.

**Einheit (ohne Datenbank):**
- Dispatch-Tabelle: jedes Paar aus §4.1 landet beim richtigen Weg. Ein
  unbekanntes Paar → `501`.
- `max_cloud_cover` auf dem Flächenweg → `400`.
- `local-sql` ohne Pool → `503`.
- `local-sql` ohne `single_coverage_product` → `501` (nach F4).
- Earth Search und EOPF: die bestehenden Tests in `test_coverage_route.py`
  bleiben ohne inhaltliche Änderung grün, jetzt über `adapters.coverage`.
- Die föderierte Einmal-Antwort (`TestSingleCoverageProduct`) bleibt die
  `bbox` der Collection, mit `area: null`.
- `_serialise`: `area` ist bei allen bisherigen Wegen `null`.

**Integration (echtes pgstac):**
- Fläche = Vereinigung: `ST_Equals` gegen die erwartete Geometrie. Das Loch
  im Ring bleibt ein Loch, die Insel bleibt getrennt. Ein Punkt zwischen zwei
  Kacheln ohne Item liegt nicht in der Fläche.
- Zuschnitt: eine `bbox` halb über dem Block liefert genau die halbe Fläche. Eine
  `bbox` über Meer liefert die leere `MultiPolygon` und `extent: null`.
- `bbox` über die Datumsgrenze (`west > east`) trifft die Kachel dort.
- `intersects` mit Dreieck schneidet genau. Ein Polygon mit Selbstschnitt →
  `400`, und die Koordinate aus der GEOS-Meldung steht weder in der Antwort
  noch im Log.
- Zeitfilter außerhalb der Item-Zeit → leere Fläche; innerhalb → volle Fläche.
- Zweiter Aufruf kommt aus dem Cache (`from_cache: true`). Ein Cache, der beim
  Schreiben fehlschlägt, ändert die Antwort nicht.
- Antwortgröße: Der Ausgabeteil der Abfrage (Vereinigung, Zuschnitt, Ausgabe)
  läuft über 26 450 in SQL erzeugte 1°-Kacheln mit unregelmäßigem Rand
  (Kreisscheiben aus festem Seed, mit Löchern) und bleibt unter 500 kB. Die
  Kacheln werden dafür nicht in pgstac geladen; das dauerte in der Messung
  Minuten. Der Test prüft die Obergrenze aus `adr/0004`, nicht die Laufzeit.
- Keine Koordinate der Anfrage im Log (wie `TestNoAoiReachesAnswerOrLog`).
- Kein Request an den Gateway-Transport auf dem Flächenweg.

**Checkliste und Grenzen:** Onboarding-Checkliste für beide bestehenden
Datensätze grün, Punkt 2 mit dem neuen Weg; `lint-imports` grün
(`catalog/local_coverage.py` importiert nur `psycopg` und `catalog`).

**Umfang geschätzt [A]:** rund 200 Zeilen Code und Doku, rund 300 Zeilen Tests.
Das liegt über dem Richtwert von 400 Zeilen (→ F6).

---

## 6. Nicht in dieser Aufgabe

- Zeichnen der Fläche im Frontend, Legende, Zoom auf die Fläche (M3-12, F-07).
  Im Frontend ändert sich nur der Typ `CoverageResponse`.
- DEM-Eintrag, Adapter, Einmal-Befehl, Zeitangabe der Items (M3-11b). Die Route
  bedient den DEM automatisch, sobald sein Eintrag
  `single_coverage_product = True` und `local-sql` trägt.
- Dichte aus eigenen Items für materialisierte Zeitreihen (→ F4).
- Vorberechnete Fläche beim Laden (→ F2 Option 2).
- `readers`, Suche, `tiler`.

---

## 7. Hinweis an M3-11b

Nur zur Abstimmung, keine Änderung an M3-11b durch diese Aufgabe:

- Der DEM-Eintrag braucht `single_coverage_product = True` und
  `coverage.provider = local-sql` (seit M3-11a Pflicht für `materialized`).
- Die Footprint-Form ist frei; beide gemessenen Formen passen unter die 500 kB.

---

## 8. Fragen an Otto

**F1 — Antwortform der Fläche (§4.3)**
1. Neues Feld `area` (GeoJSON `MultiPolygon`, leer statt `null`, wenn nichts
   abgedeckt ist). `extent` wird die `bbox` der Fläche. Alles andere wie die
   heutige Einmal-Antwort. **(Empfehlung)**
2. Wie 1, dazu ein Feld `answer` mit `density`, `extent` oder `area`, damit
   das Frontend nicht aus leeren Feldern schließen muss.
3. Die Fläche als Gitterzellen mit `n = 1` (Anwesenheit). Passt zur Heatmap,
   widerspricht aber F5 („Fläche, nicht Dichte“) und wäre an den Rändern grob.

**F2 — Wo die Vereinigung berechnet wird (§4.5)**
1. SQL bei jeder Anfrage, Ergebnis im Cache. Weltansicht rund 1 s beim ersten
   Aufruf, Ausschnitte 5–400 ms, keine Kopplung an M3-11b. **(Empfehlung)**
2. Vorberechnet beim Laden: M3-11b ruft nach dem `upsert` eine Funktion aus
   `catalog`, die die Fläche in eine eigene Tabelle schreibt (Migration). Jede
   Anfrage etwa 1–2 ms. Der Zeitfilter kann dann nicht wirken, und M3-11b muss
   die Funktion aufrufen.
3. Beides: vorberechnet ohne Zeitfilter, SQL mit Zeitfilter. Am schnellsten,
   aber zwei Wege für eine Antwort.

**F3 — Cache-Frist der Fläche**
1. Fest 5 min. Nach einem neuen Laden des DEM ist die Karte höchstens 5 min
   alt; die Weltansicht kostet höchstens alle 5 min rund 1 s. **(Empfehlung)**
2. 24 h wie ein geschlossenes Zeitfenster (`adr/0005` F1). Nach einem neuen
   Laden bis zu einem Tag veraltet, es sei denn, M3-11b löscht die
   Cache-Zeilen des Datensatzes (die Tabelle führt `dataset_id`).
3. Kein Cache.

**F4 — `local-sql` ohne `single_coverage_product` (materialisierte Zeitreihe)**
1. Nicht bauen; die Route antwortet `501`, Onboarding-Punkt 2 bleibt für
   einen solchen Eintrag rot. Kein Datensatz braucht es in M3. **(Empfehlung)**
2. Jetzt mitbauen: Zentroid-Zählung im Geotile-Gitter und Monats-Histogramm per
   SQL (`adr/0004` §3.6, B2/C). Rund 150 Zeilen mehr samt Tests.

**F5 — `max_cloud_cover` auf dem Flächenweg (§4.4)**
1. `400` mit Text „max_cloud_cover does not apply to a single coverage
   product“. **(Empfehlung)**
2. Stillschweigend ignorieren.
3. Auf `eo:cloud_cover` der Items filtern. Beim DEM wäre die Fläche dann
   immer leer.

**F6 — PR-Größe**
1. Ein PR, obwohl er mit Tests über 400 Zeilen liegt. Dispatch und Fläche
   sind nur zusammen prüfbar. **(Empfehlung)**
2. K-06 (Dispatch über `adapters.coverage`, rund 120 Zeilen mit Tests) als
   eigener PR vorab.
