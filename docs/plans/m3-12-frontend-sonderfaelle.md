# M3-12 — Frontend-Sonderfälle in die Registry: Plan-Schritt

**Status (26.09.2026):** Plan-Schritt, wartet auf Ottos Freigabe (§9).
**Aufgabe:** M3-12 aus `docs/plans/m3-dritte-quelle-und-interface.md` §4 (P10,
M3-Abnahme 1), mit den Nachträgen vom 26.09.2026 (M3-11b F11) und Ottos
Änderungen vom 26.09.2026 zu Beginn dieser Session. **Stufe B.** Hängt an
M3-11b (gemergt); läuft **vor** M3-10 (Otto, 26.09.2026).
**Grundlagen:** `plans/m3-02-konformitaetsbericht.md` §5 (F-01 bis F-16),
K-16, K-23; `plans/m3-09-zuschnitt-ansicht.md`; `plans/m3-11b-dem-adapter.md`
§2.5, F1, F7; `plans/m3-11c-coverage-eigene-items.md` §4.3;
`plans/m3-17-download-folgt-ansicht.md`; `architekturplan.md` 5.1;
`KLAERUNGEN.md` B10; `ENTSCHEIDUNGEN_2026-09-18.md` §2 (Coverage Map).

Belegstufen: **M** gemessen in dieser Sitzung, **P** am Quelltext gelesen
(Stand `main` cf152a3), **A** eigene Ableitung.

---

## 1. Ziel

Das Frontend kennt keinen Datensatz und keine quellenspezifische Eigenschaft
mehr. Was sich zwischen Datensätzen unterscheidet, steht in der Registry und
kommt über `/stac/collections`. Der DEM ist im Viewer suchbar (bei jedem
Zeitraum), als Fläche in der Coverage sichtbar, erscheint nach der Suche direkt
in voller Auflösung auf die AOI zugeschnitten, bleibt beim Herauszoomen
sichtbar und ist als Zuschnitt ladbar. Beide Sentinel-2-Datensätze verhalten
sich unverändert.

Ottos Änderungen vom 26.09.2026, hier umgesetzt:

| # | Änderung | Abschnitt |
|---|---|---|
| O1 | M3-12 läuft vor M3-10; die Abhängigkeit von M3-10 entfällt | §8 |
| O2 | Suche ohne Datumsfilter für `time_range=False`, auch kein ±90-Tage-Fallback; Antwort nennt `ignored_filters`; Oberfläche zeigt den Aufnahmezeitraum. Backend-Änderung an der Suche ausdrücklich erlaubt | §4.2, §4.3 |
| O3 | Ohne im Browser darstellbaren Quicklook: nach der Suche direkt Vollauflösung, zugeschnitten auf die AOI (Mechanismus M3-09) | §4.4 |
| O4 | Herauszoomen ohne „Zoom in“-Hinweis; kleinste Zoomstufe des DEM gemessen senken | §3, §4.5 |
| O5 | Mit Quicklook: unterhalb der kleinsten Zoomstufe zeigt die Vollauflösung den Quicklook, zugeschnitten auf die AOI | §4.6 |

---

## 2. Befund am Code — **[P]**

### 2.1 Stellen aus M3-02 und ihr Stand heute

| # | Stelle heute | trifft den DEM? | Vorschlag hier |
|---|---|---|---|
| F-01 | `grouping.ts:86` `DATATAKE_PROPERTY = 's2:datatake_id'`, `displayGroupBy` | nein direkt; die Konstante ist aber genau ein quellenspezifischer Name | Registry-Feld `results_group_by` (§4.1) |
| F-02 | `mapLayers.ts:41` `NODATA_THRESHOLD = 16` | nein (kein Quicklook) | Registry-Feld `quicklook_nodata_max` (§4.1) |
| F-03 | `geoUtils.ts:99` `utmProj4Def` nur EPSG:326xx/327xx | nein (kein Quicklook) | EPSG:4326 zulassen, kein Feld |
| F-04 | `geoUtils.ts:138` `assets.visual` als Literal | nein | Asset aus `earthx:default_render.assets[0]`, für Sentinel-2 COG ohnehin `visual` |
| F-05 | `datasets.ts::quicklookPlan`, Vorschau-Kachel auf `min_zoom` | **ja**, wenn der DEM `min_zoom` senkt | entfällt für den DEM durch `browse = full_resolution` (§4.1) |
| F-06 | `ControlPanel.tsx:327`, Datum immer Teil der Suche; `time_range` ungelesen | **ja** | §4.2, §4.3 |
| F-07 | Coverage-Fläche (`area`, M3-11c) wird nicht gezeichnet (`api.ts:273` typisiert, kein Aufrufer) | **ja** | §4.7 |
| F-11 | `earthx:access.cors` ungelesen | nein (kein Quicklook) | Registry-Regel `quicklook` ⇒ `cors = true` |
| F-12 | `datasets.ts:28` `MAX_TILE_ZOOM = 22` spiegelt das Backend | – | Test vergleicht beide |
| F-13 | `coverage.ts:130` `FOOTPRINT_FETCH_LIMIT = 500` spiegelt `FOOTPRINT_THRESHOLD` | – | durch `total_count` der Antwort ersetzen |
| K-16 | `language` im Download-Body, vom Backend verworfen | – | entfernen |
| K-23 | Kommentar „same-origin proxied image“ in `mapLayers.ts` | – | berichtigen |

F-08, F-09 und F-10 (Platzhalter des Szenennamens, Fehlertext „the two
catalogues“, feste Knopfreihe) bleiben bei M3-10, wie im M3-02-Bericht
zugeordnet. Der Knopfreihe kommt ein dritter Knopf für den DEM hinzu, das
reicht bis M3-10.

### 2.2 Was der DEM heute im Viewer tut

- **Suche mit Zeitraum 2026:** Die Items tragen `datetime: null` und den
  Zeitraum 2010-12-01 bis 2015-01-31 (M3-11b F1). pgstac filtert sie weg, das
  Frontend läuft in den Fallback (`store.ts:1187`) und meldet „No results in
  the chosen time range, nor within ±90 days.“ Die Coverage verwirft den
  Zeitfilter schon (M3-11c), die Suche nicht.
- **Trefferliste:** `quicklookPlan` findet kein Bild-Asset und nimmt eine
  Vorschau-Kachel auf `min_zoom` (z8). Das ist der Weg, den heute nur der
  Zarr-Datensatz geht.
- **Unter z8** fordert MapLibre keine Kachel an (Raster-Quellen haben kein
  Underzoom); die Karte ist leer, `zoomFloorHint` sagt „Zoom in to level 8“.
- **Gruppierung:** `group_by = ("start_datetime",)`, eine Gruppe für alle
  Kacheln (M3-11b F7). `displayGroupBy` fällt darauf zurück, weil kein
  DEM-Item `s2:datatake_id` trägt.

### 2.3 Befund am Rande: EOPF trägt `eopf:datatake_id` — **[M]**

Ein Item der EOPF-Quelle (1 Anfrage an `stac.core.eopf.eodc.eu`) trägt
`eopf:datatake_id`, nicht `s2:datatake_id`. Die Trefferliste des
Zarr-Datensatzes gruppiert deshalb heute nach Tag und MGRS-Kachel (Rückfall
auf `group_by`), nicht nach Überflug wie die des COG-Datensatzes. Das bleibt
im Vorschlag so (Abnahme „unverändert“); die Umstellung ist Option F3 (2).

---

## 3. Messung: DEM beim Herauszoomen — **[M]**

**Frage (O4):** Wie weit lässt sich die kleinste freigegebene Zoomstufe des
DEM senken, wenn jede Kachel-Ebene auf die Ausdehnung ihrer Szene begrenzt
ist? Das ist sie heute schon: `mapLayers.ts::placeRaster` setzt je Item
`bounds = item.bbox`, und die Kachel-URL ist je Item
(`/collections/{c}/items/{id}/tiles/…`). Eine Kachel zeigt also nie mehrere
Szenen, auch nicht auf z0; MapLibre fordert je Szene nur die Kacheln an, die
ihre `bbox` schneiden.

**Methode:** rio-tiler 9.4.6 / GDAL 3.12.4 aus der Sitzung, mit denselben
GDAL-Einstellungen wie `gateway/gdal.py` (Multirange, HTTP/2, VSI-Cache), je
Kachel ein neuer Prozess (kalt), 256 px, `rescale 0,5000`, `terrain`, PNG — wie
die Kachelroute. Anfragen gezählt über `CPL_CURL_VERBOSE`. Gedrosselt: Kacheln
nacheinander, danach mindestens so viele Sekunden Pause wie die Kachel
Anfragen gestellt hat; innerhalb einer Kachel folgen HEAD und GETs direkt
aufeinander (wie in M3-11b §2.5). **50 Anfragen** an
`copernicus-dem-30m.s3.amazonaws.com` (2 für den Aufbau, 30 für z4–z8 an zwei
Zellen, 6 für die Wiederholung mit Bytezählung, 12 für z0–z3), dazu 1 Anfrage
an die EOPF-Quelle (§2.3).

**Aufbau einer DEM-Datei:** 3600 × 3600 px, `float32`, DEFLATE, Blöcke
1024 × 1024, Overviews 2, 4, 8 (gröbste 450 × 450 px, passt in einen Block).

**Kosten je Kachel, kalt:**

| Zoom | Zelle N46 E010 | Zelle N27 E086 | Anfragen | übertragen |
|---|---|---|---|---|
| z0 | 1,57 s | – | 1 HEAD + 2 GET | 0,62 MB |
| z1 | 1,15 s | – | 1 HEAD + 2 GET | 0,62 MB |
| z2 | 1,13 s | – | 1 HEAD + 2 GET | 0,62 MB |
| z3 | 1,12 s | – | 1 HEAD + 2 GET | 0,62 MB |
| z4 | 1,80 s / 1,43 s | 1,31 s | 1 HEAD + 2 GET | 0,62 MB |
| z5 | 1,14 s | 1,24 s | 1 HEAD + 2 GET | 0,62 MB |
| z6 | 1,15 s | 1,23 s | 1 HEAD + 2 GET | 0,62 MB |
| z7 | 1,21 s | 1,22 s | 1 HEAD + 2 GET | 0,62 MB |
| z8 | 1,28 s / 1,17 s | 1,13 s | 1 HEAD + 2 GET | 0,62 MB |

Jede Stufe von z0 bis z8 liest dieselben Bytes: den Header (0–32 KB) und den
Block der gröbsten Overview (32 KB–608 KB). Die Kosten je Kachel hängen also
nicht vom Zoom ab. Warm (Block im VSI-Cache, 64 MB je `tiler`-Prozess, reicht
für rund 100 Szenen) fällt die Anfrage an die Quelle weg.

**Kacheln je Szene** (1°-Zelle, WebMercatorQuad, ohne Netz gerechnet, fünf
Zellen von 34° S bis 64° N):

| Zoom | z0–z5 | z6 | z7 | z8 |
|---|---|---|---|---|
| Kacheln je Szene | 1 | 1–2 | 1–4 | 1–6 |

**Folgerung [A]:** Beim Herauszoomen sinkt die Zahl der Kachel-Anfragen, sie
steigt nicht: Die Menge der Szenen steht mit der Suche fest (höchstens
`MAX_SEARCH_ITEMS = 300`), und ab z5 abwärts braucht jede Szene genau eine
Kachel zu gleichen Kosten wie auf z8. Teurer wird nur, dass mehr Szenen
**zugleich** auf dem Bildschirm sind. Schlimmster Fall: eine AOI mit 300
DEM-Zellen (rund 17° × 17°), ganz im Bild → 300 Kacheln, kalt rund 186 MB von
der Quelle; über den Vite-Proxy mit sechs Verbindungen grob 300 / 6 × 1,3 s ≈
65 s, bis alles sichtbar ist. Auf z8 ist dieselbe AOI nicht ganz im Bild, beim
Verschieben entstehen aber 2–6 Kacheln je Szene. Eine übliche AOI (Stadt bis
Region, 1–10 Zellen) kostet auf jeder Stufe unter z6 höchstens 10 Kacheln,
rund 1–2 s.

**Vorschlag:** `min_zoom` des DEM von 8 auf **0** (F4). Dann bleibt der
Zuschnitt sichtbar, solange die AOI auf dem Bildschirm ist, ohne Hinweis. Auf
z0–z3 ist eine 1°-Zelle nur 0,7–5,7 px breit; sie bleibt als Fleck erkennbar,
kostet aber so viel wie auf z8. Alternativen in F4.

Die Begründung im Docstring von `ViewerInfo` („below `min_zoom` one tile
shows several scenes“) stimmt für den Kachelpfad je Item nicht; `min_zoom` ist
die Kostengrenze. Docstring und `architekturplan.md` 5.1 werden angepasst.

---

## 4. Vorgeschlagene Umsetzung

### 4.1 Neue Registry-Felder in `ViewerInfo` (→ F1, F2, F3)

Alle ohne Vorgabewert (B10), in `earthx:viewer` veröffentlicht, Zeile in
`architekturplan.md` 5.1 nachgezogen.

| Feld | Form | Sentinel-2 COG | Sentinel-2 Zarr | DEM |
|---|---|---|---|---|
| `browse` | `quicklook` \| `preview_tiles` \| `full_resolution` | `quicklook` | `preview_tiles` | `full_resolution` |
| `quicklook_nodata_max` | `int` 0–255 oder `None` | `16` | `None` | `None` |
| `results_group_by` | Tupel von Eigenschaftsnamen | `("datetime", "s2:datatake_id")` | `("datetime", "grid:code")` | `("start_datetime",)` |
| `min_zoom` (bestehend) | – | 0 | 8 | **0** statt 8 (F4) |

- **`browse`** sagt, was nach der Suche erscheint: der Quicklook der Quelle
  (`quicklook`), eine Vorschau-Kachel auf `min_zoom` je Szene
  (`preview_tiles`, der heutige Zarr-Weg) oder direkt die Vollauflösung
  (`full_resolution`, O3). Ob ein Datensatz Quicklooks hat, steht damit in der
  Registry, nicht im Frontend (fest, Nachtrag M3-11b F11).
- **`quicklook_nodata_max`:** Quicklook-Pixel mit R, G und B ≤ diesem Wert
  werden durchsichtig; `None` heißt ohne Freistellung.
- **`results_group_by`:** Gruppierung der Trefferliste (D30) und damit der
  Download-Gruppen (P19, M3-17). Trägt ein Item des Ergebnisses eine der
  Eigenschaften nicht, gilt wie heute `group_by` für das ganze Ergebnis.

Neue Konstruktionsregeln (je ein benannter Test):

1. `browse = quicklook` ⇔ `quicklook_nodata_max` darf eine Zahl sein; bei den
   beiden anderen Werten muss es `None` sein.
2. `browse = quicklook` verlangt `access.cors = True` (F-11): ohne CORS kann
   der Browser den Quicklook nicht freistellen und nicht zuschneiden, er ist
   dann nicht „im Browser darstellbar“.
3. `results_group_by`: dieselben Prüfungen wie `group_by` (nicht leer, keine
   Doppel, kein `properties.`-Präfix).

**`earthx:data_class` genügt nicht** (Auftrag: „prüfen, ob `data_class` es
schon trägt“): Die Klasse sagt statisch/Zeitreihe, nicht, ob die Quelle
Quicklooks liefert oder ob die Zeitachse filterbar ist. Für die Zeitachse gibt
es schon `capabilities.time_range` (O2), dafür entsteht kein neues Feld.

### 4.2 Suche im Backend ohne Zeitfilter bei `time_range=False` (O2, → F5)

In `api/federating_client.py`, für `GET`/`POST /search` und
`GET /collections/{id}/items`, vor der Verzweigung nach föderiert oder
materialisiert:

- Die Collection-Dokumente, die `_holding_of` ohnehin liest, liefern
  `earthx:capabilities.time_range`. Haben **alle** Ziel-Collections keine
  Zeitachse und nennt die Anfrage `datetime`, wird der Filter verworfen und
  die Antwort trägt `"ignored_filters": ["datetime"]`.
- Ein **ungültiger** `datetime`-Wert bleibt `400`, auch bei einer Collection
  ohne Zeitachse: erst prüfen, dann verwerfen.
- Eine Suche über mehrere Collections, von denen nur manche eine Zeitachse
  haben, wird mit `400` abgewiesen („…not supported yet, M3-13“). Heute nicht
  erreichbar (föderiert + materialisiert ist schon `400`), aber nicht still
  falsch. M3-13 löst es mit der gemischten Suche.
- `ignored_filters` steht nur in der Antwort, wenn etwas verworfen wurde; die
  Antworten der beiden Sentinel-2-Datensätze bleiben Byte für Byte gleich.
- Die `next`-Links bleiben gültig: jede Folgeseite verwirft den Filter wieder
  gleich.

### 4.3 Suche und Zeitachse im Frontend (O2, → F6)

- `datasets.ts`: `timeAxisOf(collection)` liest
  `earthx:capabilities.time_range`; fehlt es, ist der Datensatz „not
  viewable“ mit Grund (wie ein fehlendes `group_by`). `acquisitionNote`
  bildet aus `extent.temporal.interval[0]` den festen Text **„No time axis –
  acquired Dec 2010 to Jan 2015“** (Monat englisch abgekürzt, UTC).
- `runSearch`: Das Datum geht weiter mit (das Backend entscheidet, O2), aber
  ohne Zeitachse läuft **nie** `findFallback`. Null Treffer heißt dann „No
  scenes found for this area.“ Nennt die Antwort `ignored_filters` mit
  `datetime`, hängt der Hinweis an die Meldung der Suche.
- `ControlPanel`: Der Block „Acquisition date“ bleibt sichtbar, ist für einen
  Datensatz ohne Zeitachse gesperrt, darunter der Hinweis; die Werte bleiben
  für die anderen Datensätze erhalten (F6).

### 4.4 Ohne Quicklook direkt in die Vollauflösung (O3, → F7)

`browse = full_resolution`: Nach einer Suche mit AOI ruft `runSearch` am Ende
`enterFocus(true)` für die aktive Gruppe auf — derselbe Weg wie der Knopf
„Crop & merge to AOI“ (M3-09), mit Zuschnitt im Browser (`aoiClip.ts`), ohne
Quicklook-Stufe (`syncMosaic` überspringt den Datensatz). Wechselt die aktive
Gruppe, folgt die Ansicht. Die Knöpfe der `ViewBar`, der Stretch mit „Apply“
und der Download (M3-17: gemergter Zuschnitt je Gruppe) bleiben unverändert.
Ohne AOI (Suche per Szenenname): F7.

### 4.5 Herauszoomen ohne Hinweis (O4, → F4)

- DEM `min_zoom = 0` (§3). Damit endet der Zuschnitt nie an einer Zoomgrenze.
- `zoomFloorHint` erscheint nur noch für `browse = preview_tiles` (heute der
  Zarr-Datensatz, unverändert). Für `full_resolution` gibt es keinen Hinweis
  „Zoom in“; der Nachtrag „Zoom in to see this dataset“ ist damit ersetzt.

### 4.6 Quicklook unterhalb der kleinsten Zoomstufe (O5)

Für `browse = quicklook` in der Vollauflösung: Unter `min_zoom` legt
`mapLayers.ts` je Szene den Quicklook als Bildquelle mit
`maxzoom = min_zoom`; ab `min_zoom` übernehmen die Kacheln (`minzoom` wie
heute). Beim Zuschnitt schneidet der Browser den Quicklook im selben Canvas,
in dem er ihn freistellt, auf die AOI: die AOI-Eckpunkte werden über den
`proj:transform` des Assets in Bildpixel umgerechnet (genau im Raster der
Quelle). Die AOI verlässt den Browser dabei nicht. Heute trifft das keinen
Datensatz (Sentinel-2 COG ist ab z0 freigegeben); es ist die allgemeine Regel
und bekommt Vitest-Tests mit einem synthetischen Eintrag `min_zoom = 8`.

### 4.7 Coverage-Fläche zeichnen (F-07)

Neuer Anzeigemodus `area` in `mapLayers.ts::setCoverageDisplay`: die
`area`-Antwort (M3-11c) als Füllung mit Umriss, eine Farbe, keine Legende der
Dichte. Ist `area` leer und `extent` gesetzt, wird die Ausdehnung als Rechteck
gezeichnet (ENTSCHEIDUNGEN §2 „durch die Ausdehnung allein“).

### 4.8 Test gegen Kennungen im Frontend

`backend/tests/test_frontend_no_dataset_literals.py` (pytest, läuft in CI mit
dem Backend-Job): liest jede Datei unter `frontend/src` außer `*.test.*`,
entfernt Kommentare und sucht (a) jede `dataset_id` aus `REGISTRY` und (b)
Eigenschaftsnamen mit Präfix `s2:`, `eopf:`, `eo:`, `sat:`, `grid:`, `mgrs:`,
`landsat:` in Zeichenketten. `proj:` bleibt erlaubt (quellenübergreifend,
`geoUtils.ts`). Der Test liest die Kennungen aus der Registry und muss für
einen vierten Datensatz nicht angepasst werden. Dazu Negativtests mit
synthetischen Quelltexten (Kennung im Kommentar erlaubt, im Code rot). Der
Vergleich von `MAX_TILE_ZOOM` (F-12) liegt im selben Test.

### 4.9 Kleinere Punkte

K-16 (`language` aus dem Download-Body), K-23 (Kommentar), F-03 (EPSG:4326 in
`quicklookCoords`), F-04 (`default_render.assets[0]` vor dem ersten
georeferenzierten Asset), F-13 (`FOOTPRINT_FETCH_LIMIT` → `total_count`).

---

## 5. Tests

**Backend (pytest):** Registry-Regeln 1–3 (§4.1) je mit Fehlerfall; die drei
Einträge setzen die Felder wie in der Tabelle; Collection-Dokument enthält sie.
Suche: synthetische materialisierte Collection mit `time_range=False` und
Items 2010–2015 — mit `datetime` 2026 gefunden und `ignored_filters`, ohne
`datetime` ohne `ignored_filters`, ungültiges `datetime` → `400`, `POST` wie
`GET`, `/collections/{id}/items` ebenso, Folgeseite über `next`; eine
Collection mit Zeitachse filtert unverändert; gemischte Zeitachsen → `400`;
kein Datum und keine Koordinate im Log. Test aus §4.8.

**Frontend (Vitest):** neue Felder gelesen, fehlende → „not viewable“;
Aufnahmehinweis (Format, Monatsgrenzen, UTC, fehlendes Intervall); `runSearch`
ohne Zeitachse ohne Fallback und mit Hinweis; `full_resolution` → Fokus mit
Zuschnitt nach der Suche, `quicklook`/`preview_tiles` unverändert;
`results_group_by` aus der Registry mit Rückfall; Freistellung mit
Schwelle aus der Registry und mit `None`; `quicklookCoords` für EPSG:4326;
Quicklook-Ebene unter `min_zoom` samt Zuschnitt; `zoomFloorHint` nur für
`preview_tiles`; Coverage-Modus `area`; kein `language` im Download-Body.

**Nicht automatisiert, Otto lokal:** DEM mit Zeitraum 2026 suchen, Zuschnitt
erscheint direkt, beim Herauszoomen bis z0 sichtbar, Coverage als Fläche,
Download als Zuschnitt; Sentinel-2 COG und Zarr wie vorher.

---

## 6. Umfang und Schnitt (→ F8)

Geschätzt ohne generierte Dateien: Backend rund 250 Zeilen (davon rund 150
Tests), Frontend rund 450 Zeilen (davon rund 200 Tests), Doku rund 40. Das
liegt über dem Richtwert von 400. Commits getrennt nach: Registry-Felder,
Suche ohne Zeitfilter, Test gegen Kennungen, Frontend Zeitachse, Frontend
Vollauflösung/Herauszoomen, Frontend Quicklook unter `min_zoom`, Coverage
`area`, Kleinkram, Doku.

**Nicht anfassen:** `readers`, Coverage-Route (M3-11c fertig), Download-Route,
Suchkachel-Umbau und F-08 bis F-10 (M3-10), gemischte Suche (M3-13).

---

## 7. Risiken

| Risiko | Umgang |
|---|---|
| Große AOI im DEM (bis 300 Szenen) lädt beim Herauszoomen bis ~65 s | Messwert in §3; F4 bietet Alternativen; Otto prüft lokal |
| `enterFocus` direkt nach der Suche stößt `autoStretch` an (`/statistics` der ersten Szene, schreibt nur die noch nicht angewandten Felder) | wie der Knopf heute; die Karte zeigt zuerst die feste Skala 0–5000 m aus der Registry, die Messung bleibt Optimierung (E5) |
| M3-07b (Ortssuche, Frontend) berührt dieselbe Suchkachel | M3-07b ist noch offen; wer später kommt, holt `main` |

---

## 8. Doku und Log

- `ENTSCHEIDUNGSLOG.md`: je eine Zeile für O1 bis O5 (fest, Otto 26.09.2026),
  in diesem PR schon eingetragen; nach der Freigabe eine Zeile mit den
  Antworten auf F1–F8.
- `plans/m3-dritte-quelle-und-interface.md`: §3 Tabelle (M3-12 hängt nur an
  M3-11b, M3-10 folgt nach M3-12), Wellen, Dateikonflikte, Risiko-Tabelle,
  Nachtrag bei M3-12 — in diesem PR schon eingetragen.
- Nach der Freigabe: `architekturplan.md` 5.1 (`earthx:viewer`,
  `ignored_filters` der Suche), Docstring `ViewerInfo`.

---

## 9. Fragen an Otto

**F1 — Feld für „was nach der Suche erscheint“ (§4.1)**
1. `browse` mit drei Werten: `quicklook`, `preview_tiles`, `full_resolution`.
   Zarr bleibt bei `preview_tiles`, also unverändert. **(Empfehlung)**
2. Zwei Werte (Quicklook ja/nein). Zarr hat keinen im Browser darstellbaren
   Quicklook und ginge dann ebenfalls direkt in die Vollauflösung; unter z8
   wäre die Karte leer, bis die Zoomstufe des Zarr-Datensatzes gemessen ist.

**F2 — Freistellung der Quicklooks (§4.1)**
1. `quicklook_nodata_max` als Zahl oder `None`, nur bei `browse =
   quicklook`. **(Empfehlung)**
2. Verschachtelt: `quicklook: {nodata_max: 16}` oder `null`, `browse` ergibt
   sich daraus (nur mit F1 (2) sinnvoll).

**F3 — Gruppierung der Trefferliste (§4.1, §2.3)**
1. `results_group_by`, Zarr mit `("datetime", "grid:code")` wie heute
   tatsächlich. **(Empfehlung)**
2. Wie 1, aber Zarr mit `("datetime", "eopf:datatake_id")`: gruppiert dann
   nach Überflug wie der COG-Datensatz; ändert auch die Download-Gruppen des
   Zarr-Datensatzes (eine Datei je Überflug statt je Kachel).

**F4 — Kleinste Zoomstufe des DEM (§3)**
1. `min_zoom` 8 → 0. Kosten je Kachel wie auf z8, je Szene nur eine Kachel;
   Zuschnitt sichtbar, solange die AOI im Bild ist. **(Empfehlung)**
2. 8 → 4. Unter z4 ist die 1°-Zelle kleiner als 11 px; darunter leer, ohne
   Hinweis.
3. 8 bleibt; unter z8 zeigt die Karte statt der Kacheln ein einziges Bild des
   Zuschnitts, per `POST` über den Zuschnitt-Pfad erzeugt (wie F10 im
   Prototyp). Ein Browser-Request statt vieler, liest aber dieselben Dateien
   an der Quelle; neuer Endpunkt.

**F5 — Name des Feldes in der Suchantwort (§4.2)**
1. `ignored_filters`, wie in der Coverage-Antwort. **(Empfehlung)**
2. `earthx:ignored_filters`, im Namensraum der eigenen STAC-Felder.

**F6 — Datumsfeld ohne Zeitachse (§4.3)**
1. Sichtbar, gesperrt, Hinweis darunter; Werte bleiben. **(Empfehlung)**
2. Ausgeblendet, Hinweis an seiner Stelle.
3. Sichtbar und bedienbar, nur der Hinweis dazu.

**F7 — `full_resolution` ohne AOI (Suche per Szenenname)**
1. Direkt die ganze Szene in voller Auflösung (wie „View full selection“).
   **(Empfehlung)**
2. Keine Anzeige, Hinweis „Draw an AOI to view this dataset“ (Vorschlag aus
   dem Nachtrag).

**F8 — Schnitt**
1. Ein PR mit getrennten Commits, rund 740 Zeilen. **(Empfehlung)**
2. Zwei PRs: M3-12a Backend (Felder, Suche, Test gegen Kennungen), M3-12b
   Frontend.
