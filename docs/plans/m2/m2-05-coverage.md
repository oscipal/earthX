# M2-05 — Coverage-Anbieter und Route: Umsetzungsplan

**Status:** **Von Otto am 20.09.2026 angenommen, F1–F7 alle wie empfohlen (§10).**
Stufe B laut `projektplan.md` 1.2: zuerst dieser Plan als Draft-PR, Umsetzung
nach Ottos OK. **M2-05a** — Nahtstelle in `catalog`, Aggregation in `adapters`,
Einheitstests — ist umgesetzt (§9, Schritte 1 bis 3). **M2-05b** — Route in
`api`, Einmal-Produkt-Weg, Integrationstest, Latenzbeleg — folgt als eigener PR.

**Umfang von M2-05b, von Otto am 20.09.2026 gesetzt:** klein halten — nur die
Route, ihre Fehlerabbildung und die Tests. Dazu drei benannte Punkte:
der Antwortkörper der Quelle erreicht weder Antwort noch Log (§3.5, ohne
Eingriff in `gateway`); die Stützpunkte von `intersects` werden gegen ±90/±180
geprüft (§3.6); und die Antwort führt die Auflösung des Histogramms mit, weil
die Quelle sie vorgibt (§3.1, monatlich).
Drei Nachträge kamen mit der Annahme dazu und sind in diesem PR erledigt: die
beiden Ergänzungen in `adr/0004` (§3.3 und §5) und die Log-Zeile zu §7.1.
**Aufgabe:** M2-05 aus `docs/plans/m2-format-und-viewer.md` §4.
**Grundlage:** `adr/0004` (Coverage Map, alle Abschnitte, besonders §3.2, §3.3,
§3.4, §5 Regel V); `adr/0005` Regel I, II, V (Katalog entscheidet, zwei Fristen,
eigener Deckel); `architekturplan.md` 3.1 (Modulgrenzen), 5.2 (zweistufiger
Katalog), 6.1 (Aggregation als vierte, optionale Adapter-Fähigkeit);
`KLAERUNGEN.md` B8 (alles Ausgehende über `gateway`), B10 (jede Fähigkeit
ausdrücklich freigeschaltet), E4/E5 (`m1-fundament.md` §1);
`ENTSCHEIDUNGSLOG.md` 2026-09-19 (Zählweise, Schwelle 500, Latenzziel, Fristen)
und 2026-09-20 (D6: keine Ratenbegrenzung in M2).
**Voraussetzungen:** alle erfüllt. M1-03 (`gateway` kann GET mit langer
Abfragezeichenfolge und deckelt die URL-Länge), M1-04 (`CoverageInfo` steht im
Registry-Eintrag), M1-06 (`adapters`, Cache-Protokoll), M1-07 (`api` läuft mit
Gateway und Cache-Pool am `app.state`).
**Hängt an nichts** — M2-05 läuft parallel zu M2-04 und berührt keine Datei,
die M2-04 anfasst (§8).

---

## 1. Ziel in einem Satz

Eine Route beantwortet „wie dicht ist Datensatz X unter Filter F auf
Gitterstufe z" mit gezählten Zellen, Zeit-Histogramm und einer **geprüften**
Vollständigkeitsangabe — föderiert über die Aggregation von Earth Search, ohne
dass der Aufrufer merkt, woher die Zahlen kommen.

## 2. Ausgangslage

- `earthx/catalog/registry.py` hat `CoverageInfo` mit `provider`,
  `typical_footprint_km` und `max_geotile_level` und prüft den Deckel schon
  gegen die Footprint-Breite (`max_geotile_level_for`). Für
  `sentinel-2-c1-l2a` steht dort `UPSTREAM_AGGREGATION` und z8.
- `CoverageProvider` kennt bereits die drei Werte `upstream-aggregation`,
  `local-sql`, `sample`; `Capabilities.single_coverage_product` existiert, und
  die Registry verbietet die Kombination „Einmal-Produkt + Upstream-Aggregation".
- `earthx/gateway/client.py` hat `get(url, params=…)` mit einem Docstring, der
  genau auf diesen Fall verweist; `Policy.max_url_bytes = 8192` steht mit
  Verweis auf `adr/0004` §3.4 im Code. Der Query-String wird nur als Hash
  geloggt (`_query_digest`) — die AOI kommt also schon heute in kein Log.
- `earthx/adapters/earth_search.py` bringt Katalog-Auflösung (`_resolve`),
  Endpunkt, STAC-Zeitfenster, die beiden Fristen und die beiden
  Cache-Hilfsfunktionen mit — alles, was die Aggregation ebenfalls braucht.
- `public.earthx_search_cache` ist ein generischer Schlüssel-Wert-Speicher mit
  `dataset_id`, `payload` (jsonb) und `expires_at`; der Schlüssel ist ein
  undurchsichtiger Hash.
- `earthx/api/main.py` hängt `/health` direkt an die Basis-App, neben dem
  STAC-Baum unter `/stac`. Gateway und Cache-Pool liegen am `app.state`.

**Es fehlt:** die Nahtstelle, die Aggregations-Fähigkeit, die Route.

## 3. Was in dieser Sitzung gegen die echte Quelle gemessen wurde

Rund 20 Metadaten-Anfragen an `earth-search.aws.element84.com` am 20.09.2026,
keine Pixel, keine Dateien. Belegstufen wie in `adr/0004`: **[M]** gemessen.

**3.1 Die Parameterform ist bestätigt [M].** `GET /v1/aggregate` mit
`collections`, `bbox` oder `intersects`, `datetime`, `query`,
`aggregations=total_count,grid_geotile_frequency,datetime_frequency` und
`grid_geotile_frequency_precision=<z>`. Die Antwort trägt eine Liste
`aggregations`; `total_count` führt ein `value`, die beiden
`frequency_distribution`-Aggregationen führen `buckets`:

```json
{"name": "total_count", "data_type": "integer", "value": 22619}
{"name": "grid_geotile_frequency", "overflow": 0,
 "buckets": [{"key": "8/133/84", "data_type": "string", "frequency": 399}]}
{"name": "datetime_frequency", "overflow": 0,
 "buckets": [{"key": "2024-01-01T00:00:00.000Z", "data_type": "datetime", "frequency": 1759}]}
```

Der Gitterschlüssel ist wörtlich `z/x/y` — er muss nicht übersetzt werden. Die
Histogramm-Schlüssel sind Instants mit `Z` und drei Nachkommastellen.

**Nachgetragen am 20.09.2026 nach dem Review [M]: `datetime_frequency_interval`
wirkt nicht.** Über ein Fenster von zwei Jahren liefert die Quelle **24
Monatsstufen — bei `day`, bei `month`, bei `year` und selbst bei `week`**. Der
Parameter wird angenommen und ignoriert; die Aggregation bint immer monatlich.
Der Umsetzungsstand sendet ihn deshalb nicht und bietet dem Aufrufer auch keine
Wahl an, die nicht eingehalten würde (`HISTOGRAM_INTERVAL = "month"`). Ein
feineres Histogramm ist damit keine Parameterfrage, sondern eine eigene Messung
und eine eigene Entscheidung.

**3.2 Die Zahlen aus `adr/0004` §3.3 reproduzieren sich exakt [M].**
bbox `5,45,15,55`, Jahr 2024: `total_count` = 22 619, Summe der Geotile-Zellen
= 22 619, Summe der Monatswerte = 22 619. Mit
`query={"eo:cloud_cover":{"lt":20}}`: 3848 und 3848 über 117 Zellen. Die
Vollständigkeitsprobe (Regel V) greift also über beide Aggregationen.

| Anfrage | Zellen | Zeit | Nutzlast |
|---|---|---|---|
| bbox + Jahr, z8, `total_count` + Gitter + Histogramm (3 Läufe) | 117 | 0,44–0,83 s | 7,9 kB |
| dieselbe mit `eo:cloud_cover < 20` | 117 | 0,33 s | 6,8 kB |
| `intersects` (Fünfeck) + ein Monat, z8 | 4 | 0,61 s | 0,6 kB |

**3.3 Neu: der ungefilterte Weltüberblick ist über Geotile bis z6 vollständig
[M].** Das ist der Fall, für den `adr/0004` §5 die materialisierte Sicht
(Option 2) vorsieht — für eine föderierte Quelle trägt der Upstream ihn selbst:

| z | Zellen | Zeit | Nutzlast | Summe == `total_count` |
|---|---|---|---|---|
| 0 | 1 | 0,77 s | 0,4 kB | ja |
| 2 | 16 | 1,11 s | 1,3 kB | ja |
| 3 | 64 | 0,60 s | 3,9 kB | ja |
| 4 | 242 | 0,75 s | 13,9 kB | ja |
| 5 | 821 | 0,83 s | 46,3 kB | ja |
| 6 | 2863 | 0,88 s | 160,4 kB | ja |
| **7** | **10 000** | 1,38 s | 559,8 kB | **nein** (30 373 709 von 30 375 554) |
| **8** | **10 000** | 2,13 s | 571,9 kB | **nein** (21 091 846 von 30 375 556) |

Zwei Befunde daraus:

1. Die Kappung bei 10 000 Zellen (`adr/0004` §3.3, Falle 1) trifft Geotile
   erst ab z7 — deutlich später als Geohash p4, weil Sentinel-2 nur Land
   abdeckt. Bis z6 ist der Weltüberblick **vollständig und unter 1,1 s**.
   `overflow` meldet auch hier durchweg `0`, obwohl bei z8 ein Drittel aller
   Aufnahmen fehlt: Die Probe aus Regel V ist das einzige, was das aufdeckt.
2. z7 und z8 ungefiltert liegen mit 560 bzw. 572 kB **über der
   Umkehrschwelle von etwa 500 kB**, ab der `adr/0004` §5 Vektorkacheln neu
   erwägen will. Der Plan hält diese Stufen ohne räumlichen Filter deshalb
   von vornherein zurück (§6.3) — damit bleibt die Schwelle unberührt.

**3.4 Fehlerfälle antworten sauber [M].** Ein unbekannter Aggregationsname und
eine Präzision außerhalb 0–29 ergeben je `400 BadRequest` mit einer klaren
Beschreibung. Beides wird abgefangen, bevor es hinausgeht (§6.3), und der
Upstream-`400` wird zusätzlich als definierter Fehler behandelt (§6.6).

**3.5 Ein Fehler der Quelle zitiert die AOI nicht — in sechs Stichproben [M].**
Gemessen am 20.09.2026, weil `UpstreamError` 500 Zeichen des Antwortkörpers
trägt und damit exakte AOI-Koordinaten in unsere Logs tragen könnte, was
`projektplan.md` 7 Punkt 6 ausschließt:

| Anfrage | Antwort |
|---|---|
| Ring mit drei Punkten | `500` „invalid number of points in LinearRing (found [3] - must be >= [4])" |
| Präzision 40 | `400` „Invalid precision value for grid_geotile_frequency_precision, must be a number between 0 and 29 inclusive" |
| `intersects` kein JSON | `400` „Invalid GeoJSON geometry" |
| unbekannter Geometrietyp | `500` „x_content_parse_exception … [1:177] [bool] failed to parse field [filter]" |
| bbox verkehrt herum | `400` „Invalid bbox, SW latitude must be less than NE latitude" |

**In keinem Fall steht ein Koordinatenwert aus der Anfrage in der
Beschreibung.** Die Meldungen sind allgemein oder zitieren
Elasticsearch-Interna mit einem Zeichen-Offset (`[1:177]`) — also eine
*Position* in der Anfrage, nicht ihren Inhalt.

Sechs Stichproben sind kein Beweis, und der Offset zeigt, dass der Parser den
Wert in der Hand hat. **Otto hat am 20.09.2026 entschieden:** der Auszug bleibt
am `UpstreamError` — im Test und im Traceback ist „Invalid GeoJSON geometry"
genau das, was gebraucht wird —, aber **die Route schreibt ihn weder in ihre
Antwort noch in eine Logzeile**; ausgeliefert und geloggt werden der Statuscode
und unser eigener Text. **`gateway` wird dafür nicht angefasst**, die Lösung
bleibt damit auf die Coverage begrenzt. Ein Test in M2-05b hält es fest.

**3.6 Eine Geometrie außerhalb des Gültigen wird stillschweigend angenommen
[M].** Ein Polygon mit Länge 999 und Breite 888 beantwortet die Quelle mit
`200` und einer plausibel aussehenden Zahl (256 183) — dasselbe Muster, das
`adr/0005` §3.5 für die bbox beschreibt und das M1-06 zum Anlass genommen hat,
die bbox selbst zu prüfen. `CoverageQuery` prüft heute nur die bbox gegen
±90/±180, nicht die Stützpunkte von `intersects`. **Otto hat die Prüfung am
20.09.2026 in den Umfang von M2-05b aufgenommen.**

## 4. Aufbau und Modulgrenzen

```
api        GET /coverage/{dataset_id}        Parameter lesen, Fehler abbilden
  |
catalog    coverage.py                       Nahtstelle, Geotile-Mathematik,
  |                                          Stufenwahl, Regel V, Extent-Weg
  |  <- strukturelles Protokoll (kein Import von adapters)
adapters   earth_search_coverage.py          /aggregate: Protokoll der Quelle
  |
gateway    get(url, params=…)                das einzige, was fetcht
```

Die Richtung stimmt mit `architekturplan.md` 3.1: `adapters` darf `catalog`
importieren, `catalog` nicht `adapters`. Die Nahtstelle (Werttypen und
`Protocol`) liegt deshalb in `catalog` und wird von `adapters` **strukturell**
erfüllt — anders als beim `SearchCache` aus M1-06, wo die Richtung umgekehrt
ist und das Protokoll darum in `adapters` steht. Zusammengesteckt werden beide
in `api`, wie schon beim föderierten Suchpfad.

Quellenspezifisches Protokollwissen — dass `/aggregate` nur GET annimmt, wie
die Parameter heißen, wo gekappt wird — bleibt vollständig in `adapters`
(`adr/0004` §5, „Wo welcher Teil liegt").

## 5. Was neu entsteht

| Datei | Inhalt | ~Zeilen |
|---|---|---|
| `backend/earthx/catalog/coverage.py` | `CoverageQuery`, `CoverageCell`, `CoverageResult`, `Completeness`, `CoverageSource` (Protocol), `check_completeness`, `level_for_viewport`, `cell_bbox`, Extent-Weg für Einmal-Produkte, `CoverageNotAvailable` | 190 |
| `backend/earthx/adapters/earth_search_coverage.py` | `aggregate_coverage()` — Anfrage bauen, Antwort lesen, Cache, Probe füttern | 180 |
| `backend/earthx/api/coverage_route.py` | Route, Parameter, Fehlerabbildung | 90 |
| Tests (§7) | Einheits- und Integrationstests, `tests_live`-Messung | 330 |

Dazu sechs bis acht Zeilen Änderung in `earth_search.py` (§6.4) und `api/main.py`
(Route einhängen). Zusammen rund 800 Zeilen — darum §10 Frage 5.

## 6. Die Entscheidungen im Einzelnen

### 6.1 Die Nahtstelle

```python
class Completeness(Enum):
    COMPLETE = "complete"      # sum(cells) == total_count
    TRUNCATED = "truncated"    # gekappt, oder AOI vereinfacht
    SAMPLE = "sample"          # Weg über adr/0004 Option 6

@dataclass(frozen=True, slots=True)
class CoverageQuery:
    dataset_id: str
    level: int
    bbox: tuple[float, float, float, float] | None = None
    intersects: Mapping[str, Any] | None = None
    start: datetime | None = None
    end: datetime | None = None
    max_cloud_cover: float | None = None
    interval: str = "month"

@dataclass(frozen=True, slots=True)
class CoverageResult:
    dataset_id: str
    grid: str                       # "geotile"
    level: int
    counting: str                   # "centroid"
    cells: tuple[CoverageCell, ...] # key "z/x/y", count n
    counted: int                    # Summe über cells
    total_count: int | None
    completeness: Completeness
    max_count: int
    histogram: tuple[HistogramBucket, ...]
    footprints_advised: bool
    from_cache: bool
```

Die Prüfungen liegen wie bei `SearchParams` in `__post_init__`: eine
`CoverageQuery`, die nie geprüft wurde, kann niemand in der Hand halten.
`bbox` und `intersects` schließen einander aus. `level` wird gegen
`config.coverage.max_geotile_level` **und** gegen §6.3 geprüft.

`max_cloud_cover` ist der einzige inhaltliche Filter in M2, und er ist
ausdrücklich aufgelistet statt frei durchgereicht: ein freier `query`-Parameter
wäre wieder eine offene Tür nach außen, und CQL2 bleibt laut `adr/0005` Regel VI
ohnehin aus. Ein Datensatz ohne die `eo`-Erweiterung lehnt ihn ab.

### 6.2 Regel V ist eine Funktion, kein Vorsatz

```python
def check_completeness(counted, total_count, *, simplified_aoi, sampled) -> Completeness
```

Rein, ohne Netz, ohne Datenbank — und damit der Test, der die Falle aus
`adr/0004` §3.3 nicht durchrutschen lässt. `total_count is None` ergibt
`TRUNCATED`, nicht `COMPLETE`: eine Quelle, die keine Gesamtzahl führt, kann
Vollständigkeit nicht belegen. Der Weg über eine ausgewiesene Stichprobe
(M2-09b) setzt `sampled=True` und bekommt `SAMPLE`, ohne dass hier schon Code
dafür steht.

### 6.3 Stufenwahl und die beiden Deckel

`level_for_viewport(zoom, config, *, has_spatial_filter)`:

1. Ausgangswert ist die Zoomstufe des Kartenausschnitts, auf 0 geklemmt.
2. **Deckel 1, je Datensatz:** `config.coverage.max_geotile_level`
   (Sentinel-2: z8, `adr/0004` §5 und Ottos Zusatz vom 19.09.2026).
3. **Deckel 2, ohne räumlichen Filter:** z6. Begründung ist die Messung in
   §3.3 — ab z7 kappt der Upstream weltweit, und die Antwort überschreitet die
   Umkehrschwelle von 500 kB. Eine Weltansicht fragt in der Praxis z0–z3; der
   Deckel verhindert nur, dass jemand z8 ohne bbox verlangt.

Der Deckel wird **geklemmt, nicht abgelehnt**: eine zu feine Stufe liefert die
gröbere Karte mit ausgewiesenem `level`, nicht einen Fehler. Das ist die
Entsprechung zu E5 auf der Anfrageseite — die Karte wird gröber, nie leer.

### 6.4 Die Aggregations-Fähigkeit in `adapters`

Eigene Datei neben `earth_search.py`, weil dieses Modul mit 422 Zeilen schon
groß ist und die Aggregation ein anderes Protokoll spricht als die Suche. Sie
braucht aus `earth_search.py` fünf Hilfen, die heute privat sind: Auflösung
über die Registry, Endpunkt, STAC-Zeitfenster, `_cache_get`/`_cache_set`. Die
werden öffentlich gemacht (`resolve_dataset`, `endpoint_of`, `stac_interval`,
`cache_get`, `cache_set`) und an den alten Stellen durchgereicht — eine rein
mechanische Umbenennung ohne Verhaltensänderung, in einem eigenen Commit.

Die Anfrage geht als **ein** `gateway.get` hinaus, mit
`aggregations=total_count,grid_geotile_frequency,datetime_frequency`: Zellen,
Gesamtzahl und Histogramm kommen aus derselben Antwort, und nur so stammen
Zellsumme und `total_count` nachweislich aus demselben Stand (`adr/0004` §3.1).

Die URL wird **vor** dem Senden auf `Policy.max_url_bytes` geprüft — das tut
`inspect_url` bereits. Kommt `UrlTooLong` zurück, fällt der Anbieter auf die
Bounding-Box der AOI zurück und setzt `simplified_aoi=True`, was über Regel V
zu `TRUNCATED` führt. Damit ist §3.4 von `adr/0004` erfüllt, ohne dass die
Antwort je ein `414` wird. Ein AOI-Polygon wird vorher auf eine feste
Stützpunktzahl (200, `adr/0004` §3.4) verdünnt; auch das Verdünnen setzt das
Flag.

Antworten, die nicht die erwartete Form haben, werden wie in M1-06 mit einem
eigenen Fehler abgewiesen, nicht halb gelesen.

### 6.5 Cache

Derselbe Speicher wie die Suche, mit dem Schlüsselpräfix `coverage:` über einen
Hash aus Datensatz, normalisiertem Filter, Gitterstufe und Intervall. Die
Tabelle ist generisch, führt `dataset_id` mit und die Fristen sind dieselben,
die Otto am 19.09.2026 für die Coverage ausdrücklich aus `adr/0005` F1
übernommen hat: 24 h bei geschlossenem Zeitfenster (Ende mehr als 7 Tage
zurück), sonst 5 min. `_search_ttl` wird dafür wiederverwendet.

**Eine Ausnahme schlägt der Plan vor** (§10 Frage 3): die vollständig
ungefilterte Weltansicht — kein `datetime`, kein Raum, kein Wolkenfilter —
bekommt 24 h statt 5 min. Bei 30 Millionen Items ändert ein Tag Zugang an der
Dichtekarte nichts Sichtbares, und es ist genau die Ansicht, die jeder Nutzer
als erstes sieht.

Ein Ausfall des Caches macht langsamer, nie falsch (E5): die vorhandenen
`cache_get`/`cache_set` fangen jede Ausnahme und loggen sie als Warnung.

### 6.6 Route und Fehler

`GET /coverage/{dataset_id}` an der Basis-App von `api`, neben `/health` und
damit außerhalb von `/stac`. Begründung: die Antwort ist kein STAC-Objekt,
und unter `/stac` stünde sie im Namensraum, in dem eines Tages die echte
STAC-Aggregation-Extension liegen könnte. Parameter: `zoom`, `bbox` **oder**
`intersects`, `datetime`, `max_cloud_cover`, `interval`.

| Fall | Antwort |
|---|---|
| unbekannter Datensatz | `404` |
| `bbox` und `intersects` zusammen, kaputte Geometrie, `zoom` < 0, unbekanntes `interval` | `400` |
| Datensatz ohne freigeschalteten Coverage-Weg (`local-sql`, `sample`) | `501` mit Verweis auf M2-09b |
| Upstream antwortet `4xx`/`5xx` | `502` |
| Upstream antwortet nicht rechtzeitig | `504` |
| Einmal-Produkt (`single_coverage_product`) | `200`, Ausdehnung aus dem Collection-`extent` statt Dichte |

Kein Log enthält bbox, `intersects` oder `max_cloud_cover` — geloggt wird
`dataset_id`, `level`, `completeness`, Dauer. Ein Test liest die Logzeilen
einer Anfrage mit einer AOI und lässt durchfallen, was Koordinaten enthält.

### 6.7 Einmal-Produkte

`capabilities.single_coverage_product=True` wird **vor** der Anbieterwahl
behandelt: Die Antwort trägt eine Zelle über die Ausdehnung aus
`extent.spatial.bbox` der Collection im eigenen pgstac, `completeness=COMPLETE`
und ein leeres Histogramm. In M2 gibt es keinen solchen Datensatz — der Weg
wird deshalb nur gegen einen synthetischen Registry-Eintrag getestet, wie der
Aufgabentext es verlangt.

### 6.8 Umschaltpunkt

`footprints_advised = total_count is not None and total_count < 500`. Die
Schwelle steht als Konstante mit Verweis auf Ottos Antwort vom 19.09.2026 an
**einer** Stelle, serverseitig, und ist damit in pytest prüfbar. Der Zoom
bleibt die zusätzliche Bremse und liegt im Frontend (M2-07c), das die
Vitest-Tests dafür mitbringt. `total_count is None` — also eine Stichprobe —
lässt die Dichte stehen, wie die Ersatzregel in `m2-format-und-viewer.md`
(M2-07c) es fordert.

## 7. Tests

Alles gegen synthetische Fixtures und ein gefälschtes Gateway; nichts im
Standardlauf geht ins Netz (`tests/test_no_network.py` wacht darüber).

**Abnahmekriterien aus dem Aufgabentext, je ein Test:**

1. **Kappungsfalle** (`adr/0004` §3.3): eine Antwort mit `overflow: 0`, deren
   Zellsumme kleiner ist als `total_count`, ergibt `TRUNCATED` — nicht
   `COMPLETE`. Gegenprobe mit gleicher Summe ergibt `COMPLETE`.
2. **Vereinfachte AOI** (§3.4): ein Polygon, dessen URL über
   `max_url_bytes` läge, wird zur Bounding-Box, die Antwort ist `TRUNCATED`,
   und es geht genau eine Anfrage hinaus.
3. **Upstream-Fehler**: `400`, `503` und ein Timeout ergeben `502`/`504`, und
   nichts davon wird in den Cache geschrieben.
4. **Geleerter Cache** (E5): dieselbe Anfrage mit einem Cache, der bei `get`
   und bei `set` wirft, liefert dieselbe Antwort — nur ohne `from_cache`.
5. **Umschaltpunkt**: 499 ergibt `footprints_advised=True`, 500 nicht,
   `total_count=None` nicht.

**Dazu:**

6. Stufenwahl: beide Deckel, das Klemmen statt Ablehnen, `zoom` unter 0.
7. Geotile-Mathematik: `cell_bbox("0/0/0")` ist die Welt; `8/133/84` liegt in
   Mitteleuropa; ein Schlüssel mit x oder y außerhalb `2**z` fällt durch.
8. Zweckfremde Nutzung: `bbox` und `intersects` zusammen; eine Geometrie, die
   kein GeoJSON ist; `interval=drop table`; ein `dataset_id` mit `../`;
   `max_cloud_cover` außerhalb 0–100.
9. Keine AOI im Log (§6.6).
10. Kein Request an `gateway` vorbei — der vorhandene
    `test_no_outbound_outside_gateway.py` sieht die neuen Module automatisch.
11. Einmal-Produkt gegen einen synthetischen Registry-Eintrag (§6.7).
12. `lint-imports` bleibt grün; die neue Datei in `adapters` importiert
    `catalog` und `gateway`, sonst nichts.

**Live, außerhalb des Standardlaufs** (`backend/tests_live/`, nach dem Muster
von `test_earth_search_smoke.py`): eine gefilterte Anfrage gegen Earth Search,
mit gemessener Latenz. Ziel unter 1 s, typisch unter 0,5 s (K6). Die Messungen
in §3 sind der Vorabbeleg, dass das Ziel erreichbar ist — **und der Ersatz für
die geforderte Messung im PR, solange §7.1 gilt.**

### 7.1 Beobachtung: `gateway` erreicht die Quelle aus einer Cloud-Sitzung nicht

`backend/tests_live/test_earth_search_smoke.py` fällt in dieser Sitzung mit
`UpstreamUnreachable: earth-search.aws.element84.com could not be reached`
durch; darunter liegt ein `httpx.ProxyError: 403 Forbidden`. Der Proxy der
Umgebung protokolliert dazu
`connect_rejected … gateway answered 403 to CONNECT … host 13.226.251.39:443`
— also ein CONNECT auf die **Adresse**, nicht auf den Namen.

Das passt genau zum Entwurf von `earthx/gateway/client.py`: Der Client
verbindet sich absichtlich zu der Adresse, die `check_url` freigegeben hat,
„so the name is not resolved a second time". Die Egress-Freigabe der Umgebung
arbeitet dagegen namensbasiert — deshalb kommt `curl` (Name) durch und
`gateway` (Adresse) nicht. Dieselben Anfragen, die §3 mit `curl` misst, sind
über `gateway` in dieser Sitzung nicht wiederholbar.

**Erledigt für M2-05b:** Ausgehend ist der Weg dicht — die Abfragezeichenfolge
wird nur als Hash geloggt, keine Fehlermeldung nennt eine Koordinate, der
Cache-Schlüssel ist ein Hash hinter dem Präfix. Offen war die Gegenrichtung:
`UpstreamError` trägt 500 Zeichen des Antwortkörpers, und ob Earth Search den
`intersects`-Wert darin **zurückgibt**, war nicht gemessen. Siehe §3.5.

Das ist **kein Fehler in `gateway`** und wird hier auch nicht geändert: Die
Adress-Pinnung ist eine Sicherheitseigenschaft aus M1-03 (nichts darf sich
zwischen Prüfung und Verbindung bewegen). Es heißt nur, dass die Abnahme
„Latenz gegen die Quelle im PR gemessen" aus einer Cloud-Sitzung **nicht über
den Produktivpfad** belegbar ist. Der Punkt betrifft M2-04, M2-09a und M2-09b
genauso und gehört deshalb Otto vorgelegt, nicht in dieser Aufgabe gelöst —
siehe F7.

## 8. Was nicht angefasst wird

`backend/app/` (Prototyp); `frontend/` (das macht M2-07c); der Suchpfad und
die STAC-Routen; `.github/`; `.importlinter`; die Registry-Felder selbst — die
drei Coverage-Felder stehen bereits. **Keine Berührung mit M2-04:** M2-04
arbeitet in `readers/`, `access/`, `docker-compose.yml`, `.importlinter` und
an `SourceInfo.asset_hosts`; M2-05 in `catalog/coverage.py`,
`adapters/earth_search_coverage.py` und `api/`. Einzige gemeinsame Datei wäre
`api/main.py`, und dort auch nur eine eingehängte Route gegen einen verlegten
Prozess-Einstieg — beides in verschiedenen Funktionen.

Keine Ratenbegrenzung (D6). Keine Vektorkacheln (`adr/0004` §7 Frage 2). Keine
ausgewiesene Stichprobe — die baut M2-09b; hier entsteht nur der Platz dafür.
Kein `local-sql`-Anbieter: kein Datensatz in M2 hat eigene Items im pgstac, und
Code ohne Aufrufer ist Code ohne Test.

## 9. Reihenfolge der Umsetzung

1. Hilfen in `earth_search.py` öffentlich machen (eigener Commit, kein
   Verhalten geändert).
2. `catalog/coverage.py` mit Werttypen, Regel V, Stufenwahl, Geotile-Mathematik
   — samt Tests 1, 5, 6, 7.
3. `adapters/earth_search_coverage.py` samt Tests 2, 3, 4, 12.
4. Einmal-Produkt-Weg samt Test 11.
5. Route in `api` samt Tests 8, 9.
6. `tests_live`-Messung, Latenztabelle in den PR.

Nach Frage 5 in §10 endet Schritt 3 oder 4 den ersten PR.

## 10. Fragen an Otto

Jede mit Empfehlung; (a) ist jeweils die Empfehlung.
**Alle sieben am 20.09.2026 von Otto mit (a) beantwortet.**

**F1 — Pfad der Route.**
(a) `GET /coverage/{dataset_id}` an der Basis-App von `api`, außerhalb von
`/stac`. Die Antwort ist kein STAC-Objekt, und `/stac` bleibt der Namensraum
des Standards.
(b) `GET /stac/collections/{id}/coverage` — beim Katalogobjekt, aber ein
nicht-standardisierter Pfad im Standard-Namensraum.
(c) `/stac/aggregate` nach der STAC-Aggregation-Extension. Dann müsste die
Antwortform der Extension folgen, und Regel V, Stufenwahl und Umschaltpunkt
hätten dort keinen Platz.

**F2 — Wortlaut des Pflichtfelds.** `adr/0004` §5 nennt die drei Werte deutsch,
`CLAUDE.md` verlangt englische Bezeichner im Code.
(a) Auf der Leitung `complete` / `truncated` / `sample`, mit der Zuordnung zu
`vollstaendig` / `gekappt` / `stichprobe` im Docstring und in der Oberfläche.
(b) Die deutschen Werte wörtlich auch im Code und in der JSON-Antwort.

**F3 — Ungefilterter Weltüberblick.** `adr/0004` §5 sieht dafür Option 2 vor,
eine materialisierte Sicht — die für eine föderierte Quelle nichts zu
materialisieren hätte.
(a) Keine Vorberechnung. Dieselbe Route, derselbe Cache, dazu **24 h Frist für
die vollständig ungefilterte Anfrage** und der Stufendeckel z6 ohne räumlichen
Filter (§6.3). Beleg: §3.3 — bis z6 vollständig in unter 1,1 s.
(b) Doch eine Vorberechnung, geplant angestoßen. Setzt einen Prozess voraus,
der etwas anstößt; den gibt es in M2 nicht.

**F4 — Form der Zellen in der Antwort.**
(a) Kompakt: `[{"k":"8/133/84","n":399}]` plus `grid` und `level`; das Polygon
rechnet der Client (acht Zeilen, und `catalog/coverage.py` hat dieselbe
Funktion für Tests und den späteren SQL-Weg). Der Weltüberblick auf z6 bleibt
damit bei rund 160 kB.
(b) Fertiges GeoJSON vom Server. Bequemer für M2-07c, aber z6 weltweit läge
dann bei rund 570 kB und damit über der Umkehrschwelle aus `adr/0004` §5.

**F5 — Ein PR oder zwei?** Geschätzt rund 800 Zeilen, Richtwert sind 400.
(a) Zwei PRs, wie bei M2-07 und M2-09: **M2-05a** Nahtstelle in `catalog` und
Aggregation in `adapters` mit allen Einheitstests; **M2-05b** Route in `api`,
Einmal-Produkt-Weg, Integrationstest und die Latenzmessung.
(b) Ein PR über dem Richtwert.

**F6 — Wohin mit dem Coverage-Cache?**
(a) In `public.earthx_search_cache` mit dem Schlüsselpräfix `coverage:`. Die
Tabelle ist generisch, die Fristen sind dieselben wie bei der Suche, keine
Migration nötig.
(b) Eigene Tabelle per Migration, wie M2-04 sie für die Statistik anlegt (dort
mit 30 Tagen eine andere Frist und ein anderer Prozess).

**F7 — Wie wird die Latenz belegt?** Siehe §7.1: `gateway` kommt aus einer
Cloud-Sitzung nicht an die Quelle, weil es die geprüfte Adresse verbindet und
die Umgebung nur Namen freigibt.
(a) Für M2-05 die `curl`-Messungen aus §3 als Beleg nehmen und den
`tests_live`-Test schreiben, aber nur im geplanten T-D-Lauf ausführen lassen.
(b) Die Freigabe der Umgebung so erweitern, dass auch CONNECT auf die Adresse
durchgeht. Nur Otto kann das; es lockert die Egress-Regel der Umgebung.
(c) `gateway` aus der Adress-Pinnung nehmen — **nicht empfohlen**, das gibt
eine Sicherheitseigenschaft aus M1-03 auf.

## 11. Nachtrag, der aus §3.3 folgt

`adr/0004` §3.3 belegt die Kappung an Geohash p4/p5. Für **Geotile** — das
gewählte Gitter — liegt sie nach dieser Messung bei z7. **Erledigt:** Otto hat
den Nachtrag mit der Annahme beauftragt; er steht in `adr/0004` §3.3, zusammen
mit dem zweiten Stufendeckel z6. Der Wortlaut des Pflichtfelds (F2) ist als
zweiter Nachtrag bei Regel V in §5 vermerkt.
