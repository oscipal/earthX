# M4-17 — Mosaik im Kachel-Pfad: Plan

**Stand:** 20.10.2026, Plan zur Freigabe durch Otto.
**Stufe B:** Bis zur Freigabe ist kein Produktivcode geändert. Nach der Freigabe
setzt dieselbe Session um (oder die Sessions aus Frage 6).
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Startsatz:** „Führe Aufgabe M4-17 aus `docs/plans/m4-processing-kern.md` aus.“
**Grundlage:**
- `plans/m4-processing-kern.md` M4-17, S5 (§1.1c), §1.2, Abnahme 7 (§5).
- `adr/0006` §2 (K1–K8), §3.4, §3.5, §4.2 (M1–M4), §5 „Zu Frage 4“, §6 Folge 1.
- `adr/0001` Z4, E4/E5 (`plans/m1-fundament.md` §1), `architekturplan.md` 6.3,
  12.1, 12.3.
- `plans/m4-12-mosaik-ueberflug.md` §8 F3/F4, §11, §12 (Mosaikregel, Reihenfolge).
- `plans/m3-dritte-quelle-und-interface.md` P11.

Belegstufen wie in `adr/0009`: [M] gemessen, [P] am Primärdokument oder im
Code gelesen, [S] Zusammenfassung oder Suchtreffer, [A] eigene Ableitung.

**Kurzfassung.**

- Der `tiler` bekommt eine Mosaik-Kachel: dieselben Routen wie heute für eine
  Szene (Kachel und TileJSON), aber über die Szenen **eines Überflugs**, die
  als Item-Liste in der URL stehen (`adr/0006` §4.2, M1). Keine Such-ID, kein
  neuer Zustand, keine neue Tabelle, keine neue Abhängigkeit (§3, §4).
- Die Reihenfolge ist die des Mosaik-Jobs (`processing.mosaic.mosaic_order`),
  die Regel `FirstMethod` bzw. `merge_first_valid` — unverändert (S5). Der
  Server sortiert, die Reihenfolge in der URL zählt nicht.
- Grenzen: höchstens 64 Szenen je URL, höchstens 12 gelesene Szenen je Kachel
  (nach dem Vorfilter über den Footprint), Mosaik-Kacheln ab z8 (§5). Gemessen:
  ein Überflug über Mitteleuropa hat bis 60 Szenen, eine z8-Kachel berührt
  davon höchstens 9 (§2.2).
- Befund: Die Karte mosaikiert schon heute — als Stapel einzelner Layer in der
  **Auswahlreihenfolge**. Das ist die Regel des Zuschnitts, nicht die des
  Mosaik-Jobs (§2.1). Daraus folgt Frage 2.
- Sieben Fragen an Otto (§7); `adr/0017` halte ich nicht für nötig, weil
  `adr/0006` die Grundsatzfrage schon entschieden hat (Frage 1).

---

## 1. Was schon entschieden ist

| Quelle | Inhalt | Folge hier |
|---|---|---|
| `adr/0006` §5 „Zu Frage 4“ | Mosaik im Kachel-Pfad, wenn es kommt, „als Item-Liste in der URL (M1), nie als Such-ID“; höchstens 25 Items je URL; Vorfilter über die Item-`bbox` | Option O1 (§3); die 25 werden mit Messung neu begründet (§5) |
| `adr/0006` §6 Folge 1 | Der Satz zur Such-ID in `architekturplan.md` 6.3 „kehrt seine eigene Begründung um und ist zu ersetzen“ | nie nachgezogen: 6.3 nennt die Such-ID heute noch (§2.6) |
| `adr/0006` §7 Frage 1, P11, Q7 | Mosaik im Kachel-Pfad erst in M4b | diese Aufgabe |
| S5 | dieselbe Mosaikregel (Reihenfolge, Überlappung) wie Export-Job und Mosaik-Job; M4-17 ändert sie nicht | §4.3 |
| M4-12 F3, F4 | erstes gültiges Pixel in der Reihenfolge der Liste; `api` sortiert die Liste eines Mosaik-Jobs: zuerst die Szenen im Ziel-CRS, dann die übrigen, je nach Item-ID; Ziel-CRS = das der meisten Szenen, bei Gleichstand die kleinere EPSG-Zahl | §4.3 |
| `adr/0001` Z4, K3 | die Kachel-URL bestimmt das Bild vollständig | §4.1 |
| E4, E5 | Anwendungs-Cache in Postgres; ein Ausfall macht nur langsamer | Option O2 (§3) |
| Q8, §1.2 | keine AOI und kein Rezept-Hash nach außen, nicht in URLs, nicht in Logs | §4.6 |
| KLAERUNGEN B8 | jede Adresse passiert `check_url`, bevor GDAL sie sieht | §4.2: dieselbe Auflösung wie die Einzelkachel |
| KLAERUNGEN B11 | Anzeige ab Lizenzstufe `display` | §4.2: dieselbe Prüfung wie die Einzelkachel |

---

## 2. Befunde

### 2.1 Die Karte mosaikiert heute im Browser, in der Auswahlreihenfolge [P]

- Jede Szene ist eine eigene MapLibre-Quelle mit eigener Kachel-URL
  (`frontend/src/mapLayers.ts` `syncFocusRaster`, `addTiles`; Vorlage
  `api.ts` `buildTileTemplate`). Je Kartenkachel fragt der Browser so viele
  Kacheln an, wie Szenen sie berühren; der `tiler` liest jede für sich.
- Die Stapelung ist „zuerst gewählte Szene oben“ (Kommentar in
  `syncFocusRaster`), also erstes gültiges Pixel **in der Auswahlreihenfolge**.
  Das ist die Reihenfolge des synchronen Zuschnitts und des Export-Jobs (beide
  nehmen die Liste, wie der Client sie schickt; `access/download.py`
  `crop_asset`, `processing/export.py`). Der Mosaik-Job sortiert dagegen in
  `api` (`api/intake.py` `_one_overpass` → `mosaic_order`).
- Die Vorschau eines Operators (`processingPreview.ts`) stapelt ebenso je
  Szene, in der Reihenfolge der Auswahl; der Job, dessen Vorschau sie ist,
  rechnet in der sortierten Reihenfolge. Wo sich zwei Szenen mit
  verschiedenen Werten überlappen, zeigen Vorschau und Job heute verschiedene
  Szenen — genau das, was S5 ausschließen will.
- Obergrenzen im Frontend: `MAX_MOSAIC_LAYERS = 40`, `MAX_PREVIEW_SCENES = 40`;
  darüber werden Szenen ohne Hinweis weggelassen.
- Die AOI erreicht nie eine Kachel-URL: Der Zuschnitt auf der Karte maskiert
  im Browser (`aoiClip.ts`, Protokoll `earthx-clip://`, Schlüssel ist ein
  Zähler, keine Geometrie). Das bleibt so.

### 2.2 Wie viele Szenen eine Kachel berührt [M]

Zwei Suchen bei Earth Search (`sentinel-2-c1-l2a`, Messrechteck 5–16° O,
45–55° N, je ein Tag; **2 Anfragen**, im Abstand von 2 s, nur Metadaten), gruppiert
nach `s2:datatake_id` wie `results_group_by`; je Zoomstufe die Zahl der Szenen,
deren Footprint (`geometry`) eine Kachel von `WebMercatorQuad` schneidet:

| Tag | Szenen im Überflug | CRS | z6 | z7 | z8 | z9 | z10 | z12 |
|---|---|---|---|---|---|---|---|---|
| 14.08.2026 | 53 | 26 × 32631, 27 × 32632 | 22 | 13 | 9 | 6 | 6 | 6 |
| 14.08.2026 | 32 | 4 × 32632, 28 × 32633 | 22 | 12 | 9 | 4 | 4 | 4 |
| 14.08.2026 | 8 | 32633 | 8 | 6 | 5 | 4 | 4 | 4 |
| 03.09.2026 | 60 | 29 × 32631, 31 × 32632 | 27 | 12 | 9 | 8 | 8 | 8 |
| 03.09.2026 | 32 | 4 × 32632, 28 × 32633 | 22 | 12 | 9 | 4 | 4 | 4 |
| 03.09.2026 | 8 | 32633 | 8 | 6 | 5 | 4 | 4 | 4 |

Maximum je Kachel; das 95. Perzentil liegt ab z9 bei 2–6. Mit der `bbox` statt
des Footprints ändert sich das Maximum um höchstens eins.

Zwei Dinge daraus:

1. **Ein Überflug ist größer als 25 Szenen**, sobald die Suchfläche
   landesgroß ist (53 und 60). Die 25 aus `adr/0006` §5 beruhten auf „höchstens
   22 Szenen an einem Tag“ in einem kleineren Rechteck.
2. **Ab z10 sind es bis zu 8, nicht 4.** Grund: Derselbe MGRS-Kachelname kommt
   in einem Überflug zweimal vor (3 bzw. 10 Paare, z. B. `T31TFL` um 10:45 und
   10:48, vermutlich je ein Teil der Kachel aus zwei Datenstreifen [A]), und an der Grenze
   zweier UTM-Zonen überlappen die Kacheln beider Zonen breit. Gerade dort ist
   ein Mosaik am nützlichsten.

Rechenweg: `scratchpad`-Skript mit `morecantile` und `shapely` über die
gespeicherten Antworten, offline (§10).

### 2.3 Was eine Mosaik-Kachel kostet [M aus `adr/0006`, A]

`adr/0006` §3.4 und §3.5 (gemessen gegen dieselbe Quelle):

| Zoom | gelesen je Szene, kalt | Zeit je Szene, kalt | warm |
|---|---|---|---|
| z8 | 96 kB (+ 32 kB Kopf) | ~1,0 s | — |
| z10 | 160 kB | ~0,7 s | 115–193 ms |
| z12 | 1164 kB | ~1,2 s | |
| z14–z18 | 2016 kB | ~1,0–1,2 s | 54 ms |

Eine Mosaik-Kachel an einer Naht (2 Szenen, z11): 2,7 MB, 1,1–1,9 s.

**[A]** Der Browser fragt heute je Kartenkachel jede berührende Szene einzeln
an (§2.1). Die Mosaik-Kachel liest dieselben Szenen — höchstens; mit
`FirstMethod` und Lesen in Portionen hört sie auf, sobald jedes Pixel gefüllt
ist (§4.4). Für die Quelle wird es also nicht teurer, eher billiger; für den
Browser sind es N-mal weniger Anfragen. Die 2,7 MB von `adr/0006` sind kein
Aufschlag des Mosaiks, sondern zweimal der Preis einer Szene ab z12.

### 2.4 Die Mosaikregel liegt an zwei Stellen, die `access` nicht beide erreicht [P]

- `access/crop_rules.py` `merge_first_valid` und rio-tilers `FirstMethod`
  (im Zuschnitt über `mosaic_reader`) sind dieselbe Regel; die Docstrings
  sagen es, ein Test von M4-12a belegt es.
- Die **Reihenfolge** des Mosaik-Jobs liegt in `processing/mosaic.py`
  (`target_crs`, `mosaic_order`). `access` darf `processing` nicht importieren
  (`.importlinter`, Vertrag `access`); `api` darf es und tut es schon
  (`api/intake.py`). Der `tiler` lädt `processing` erst bei Bedarf
  (`_operator_support`, Test `test_tiler_start_is_light`).
- Folge: Das Sortieren gehört in `api/tiler.py` (Pfad-Abhängigkeit, verzögerter
  Import), das Lesen und Mischen in `access` (§4.2). Die Regel wandert nicht.

### 2.5 `mosaic_reader` hält die Reihenfolge, auch mit Threads [P]

`rio_tiler` 9.4.6, `mosaic/reader.py` und `tasks.py`: Die Liste wird in
Portionen (`chunk_size`, Vorgabe = `threads`) gelesen; innerhalb einer Portion
parallel, das Ergebnis aber in der Reihenfolge der Liste gemischt
(`filter_tasks` iteriert die Futures der Reihe nach). Nach jeder Portion prüft
er `pixel_selection.is_done` und hört auf. Mit `threads=1` liest er Szene für
Szene und hört nach der ersten auf, die alles füllt (so der synchrone Zuschnitt,
M3-18 F4). `allowed_exceptions` lässt `TileOutsideBounds` durch, ohne
abzubrechen.

### 2.6 Widerspruch in den Dokumenten [P]

`architekturplan.md` 6.3 sagt weiter: „Suchergebnis wird unter einer Such-ID
kurz gecacht, damit Tile-URLs stabil und CDN-fähig sind“; die Aufgabe M4-17
nennt diese Option deshalb ausdrücklich. `adr/0006` (angenommen) hat sie am
20.09.2026 verworfen und die Berichtigung von 6.3 als Folge 1 genannt; sie ist
nie geschehen. Nach der Rangfolge gilt das ADR. Die Abwägung in §3 holt sie
trotzdem nach, weil die Aufgabe sie verlangt.

### 2.7 Stand der Technik

Recherche vom 20.10.2026 über einen Subagenten. Erreichbar waren GitHub (Rohdateien)
und Suchmaschinen; die Doku-Seiten von Development Seed, Planetary Computer, AWS,
nginx, Sentinel Hub und Earth Engine nicht. [P] heißt hier: Rohdatei aus dem
Repository gelesen, über die Zusammenfassung des Abrufwerkzeugs, nicht Zeile für
Zeile geprüft.

| Befund | Beleg | Stufe | Folge hier |
|---|---|---|---|
| titiler-pgstac registriert eine Suche per `POST /searches/register`; die ID ist ein Hash über die Suche (`hash text PRIMARY KEY` der Tabelle `searches`), die Kachel-URL trägt nur die ID | [`004_search.sql`](https://raw.githubusercontent.com/stac-utils/pgstac/main/src/pgstac/sql/004_search.sql), [`searches_endpoints.md`](https://raw.githubusercontent.com/stac-utils/titiler-pgstac/main/docs/src/endpoints/searches_endpoints.md) | P | das Muster von O2/O3 |
| Die Einträge in `searches` haben keinen Ablauf (nur `lastused`, `usecount`); „retention-driven GC“ steht erst unter „Unreleased“ | [pgstac `CHANGELOG.md`](https://raw.githubusercontent.com/stac-utils/pgstac/main/CHANGELOG.md) | P | eine „kurzlebige“ Such-ID ist dort gerade nicht gelöst; mit Ablauf entsteht das Problem toter URLs aus §3 O2 |
| Grenzen je Kachel bei titiler-pgstac: `items_limit` 100, `time_limit` 5 s, `exitwhenfull` und `skipcovered` an | [`settings.py`](https://raw.githubusercontent.com/stac-utils/titiler-pgstac/main/titiler/pgstac/settings.py), [`006_tilesearch.sql`](https://raw.githubusercontent.com/stac-utils/pgstac/main/src/pgstac/sql/006_tilesearch.sql) | P | „aufhören, sobald voll“ ist Praxis (§4.4) |
| Planetary Computer: Mosaik über `searchid` (titiler-pgstac), **höchstens 10 Items je Kachel** (`DEFAULT_MAX_ITEMS_PER_TILE`), `minzoom` je Collection, darunter keine Items | [`pctiler/config.py`](https://raw.githubusercontent.com/microsoft/planetary-computer-apis/main/pctiler/pctiler/config.py), [`pctiler/reader.py`](https://raw.githubusercontent.com/microsoft/planetary-computer-apis/main/pctiler/pctiler/reader.py) | P | stützt Szenen- und Zoomgrenze in §5 (dort 12 und z8, gemessen statt übernommen) |
| Beispiel des Planetary Computer für ein Sentinel-2-Mosaik: `minZoom: 9`, ohne Begründung | [Quickstart-Notebook](https://raw.githubusercontent.com/microsoft/PlanetaryComputerExamples/main/quickstarts/using-the-data-api.ipynb) | P | Größenordnung wie z8 |
| `mosaic_reader`: `FirstMethod` mit `exit_when_filled`; Portionen (`chunk_size`) parallel, innerhalb einer Portion läuft alles zu Ende, danach Abbruch, wenn voll | [`rio_tiler/mosaic/reader.py`](https://raw.githubusercontent.com/cogeotiff/rio-tiler/main/rio_tiler/mosaic/reader.py), [`tasks.py`](https://raw.githubusercontent.com/cogeotiff/rio-tiler/main/rio_tiler/tasks.py), [`methods/defaults.py`](https://raw.githubusercontent.com/cogeotiff/rio-tiler/main/rio_tiler/mosaic/methods/defaults.py); im venv nachgelesen (§2.5) | P | Frage 5 |
| Ein eigenes Mosaik-Backend ist vorgesehen: rio-tilers `BaseBackend` verlangt `assets_for_tile`, `assets_for_point`, `assets_for_bbox`; `titiler.mosaic`s `MosaicTilerFactory` nimmt ein solches Backend, Threads über `MOSAIC_CONCURRENCY` | [`rio_tiler/mosaic/backend.py`](https://raw.githubusercontent.com/cogeotiff/rio-tiler/main/rio_tiler/mosaic/backend.py) (im venv vorhanden), [`titiler/mosaic/factory.py`](https://raw.githubusercontent.com/developmentseed/titiler/main/src/titiler/mosaic/titiler/mosaic/factory.py) | P | O1 geht mit `BaseBackend` aus rio-tiler; `titiler.mosaic` ist nicht installiert und wäre ein neues Paket (§4.1) |
| titiler, Diskussion zu Mosaiken bei niedrigem Zoom (rund 950 COGs): z10 4–10 s, z8 8–16 s, z7 35–60 s, z6 Timeout; Rat der Maintainer: Mosaik erst ab einem Mindestzoom | [titiler Discussion #287](https://github.com/developmentseed/titiler/discussions/287) | P | Mindestzoom in §5 |
| titiler-stacapi sucht je Kachel bei der STAC-API und warnt selbst, dass so jede Kachel eine Suche kostet | [`titiler/stacapi/backend.py`](https://raw.githubusercontent.com/developmentseed/titiler-stacapi/main/titiler/stacapi/backend.py) | P | O4 verworfen |
| MosaicJSON: Quadkey → Liste von Asset-URLs; `cogeo-mosaic` liest die Datei über `httpx2` bzw. `boto3` | [`backends/web.py`](https://raw.githubusercontent.com/developmentseed/cogeo-mosaic/main/cogeo_mosaic/backends/web.py), [`backends/s3.py`](https://raw.githubusercontent.com/developmentseed/cogeo-mosaic/main/cogeo_mosaic/backends/s3.py) | P | O5 verworfen (B8), wie `adr/0006` |
| Reihenfolge anderswo: pgstac ohne `sortby` `datetime DESC, id DESC`; Sentinel Hub `mostRecent`/`leastCC`; Earth Engine „letztes oben“ | [`002d_keyset.sql`](https://raw.githubusercontent.com/stac-utils/pgstac/main/src/pgstac/sql/002d_keyset.sql); Forum, Earth-Engine-Guide | P/S | keine allgemeine Regel; S5 legt sie fest |
| URL-Längen: Uvicorn/h11 16 384 Byte bis zum Ende der Kopfzeilen; nginx `large_client_header_buffers` 8 kB für die Anfragezeile; CloudFront und Fastly 8 kB, Cloudflare 16–32 kB, AWS ALB 16 kB; Browser weit darüber | [uvicorn `settings.md`](https://raw.githubusercontent.com/encode/uvicorn/master/docs/settings.md), [nginx `ngx_http_core_module.xml`](https://raw.githubusercontent.com/nginx/nginx.org/master/xml/en/docs/http/ngx_http_core_module.xml) [P]; CloudFront-, Fastly-, Cloudflare-, ALB-Quotas [S] | P/S | engste Grenze 8 kB; 64 IDs ≈ 2,4 bzw. 4,3 kB (§5) |

Für Sentinel-2-COGs über HTTP gibt es keine veröffentlichten Kosten je
Mosaik-Kachel; die Zahlen dazu sind die eigenen aus `adr/0006` (§2.3).

---

## 3. Optionen

Kriterien aus `adr/0006` §2 (K1–K8), dazu **K9** dieselbe Mosaikregel wie
Mosaik-Job und Export (S5) und **K10** keine exakte AOI in URL oder Log (Q8).

| | Option | K3 URL bestimmt Bild | K5 kein Zustand | K6 Quelle | K7 Teile | K9 | K10 | Bewertung |
|---|---|---|---|---|---|---|---|---|
| **O1** | **Item-Liste in der URL**, Server sortiert und mischt | ja | ja, nur die vorhandenen Caches | wie heute, eher weniger (§2.3) | eine Route mehr, keine Tabelle, kein Paket | ja | ja (Item-IDs, keine Fläche) | **Empfehlung** |
| O2 | Such-ID: `POST` registriert die Liste, Postgres-Tabelle mit kurzer Frist, Kachel-URL trägt nur die ID (6.3, E4; Muster von titiler-pgstac) | nein: ist der Eintrag weg, ist die URL tot oder zeigt nach erneuter Registrierung anderes | Zustand in Postgres, den der Tiler zum Rendern **braucht** — ein Ausfall macht falsch bzw. leer, nicht langsamer (verletzt E5) | gleich | Tabelle, Migration, Kehraus, Registrier-Route, Wiederholung im Client | ja | ja | verworfen wie in `adr/0006` |
| O3 | Inhaltsadresse: ID = Hash der sortierten Liste, Liste im Cache; fehlt der Eintrag, `404` und der Client registriert neu | ja, solange der Eintrag lebt | wie O2 | gleich | wie O2 | ja | ja | kürzere URL als einziger Vorteil; die URL von O1 passt (§5) |
| O4 | Überflug-Schlüssel in der URL (`datatake`), der Tiler sucht die Szenen je Kachel selbst | nein: hängt am Stand der Quelle | Suche je Kachel oder Cache je Überflug | **schlecht**: eine föderierte Suche je neuer Kachelfläche | Suche im Tiler, Filter nach Property in jedem Adapter | ja | ja | verworfen (Prinzip 10, „Suche läuft in `api`“) |
| O5 | MosaicJSON (`cogeo-mosaic`) | ja | Datei je Mosaik nötig | gleich | neues Paket, liest die Datei selbst über eigenen HTTP-Client | ja | ja | verworfen (B8, `adr/0006` §4.2 M3) |

**Warum O1 trotz längerer URL:** 64 Item-IDs von Sentinel-2 (30 Zeichen) sind
mit `item=` rund 2,4 kB, von `sentinel-2-l2a-zarr3` (rund 60 Zeichen) rund
4,3 kB (§5). Das liegt unter den belegten Grenzen von Browsern, CDNs und
Uvicorn (§2.7). Ein CDN steht erst mit M6 vor dem Tiler; bis dahin zählt die
URL-Länge nur für Browser und Server.

---

## 4. Entwurf (Option O1)

### 4.1 Routen

Im `tiler` (`earthx.api.tiler`), neben dem Router je Item:

```
GET /collections/{dataset}/mosaic/tiles/{tileMatrixSetId}/{z}/{x}/{y}[@{scale}x][.{format}]
    ?item=<id>&item=<id>…&asset=<key>[&rescale=…][&colormap_name=…][&bidx=…]
GET /collections/{dataset}/mosaic/{tileMatrixSetId}/tilejson.json?item=…&asset=…
```

- `item` wiederholt, 2 bis 64 verschiedene IDs; `asset` genau eines (wie die
  Einzelkachel ohne `op`, Frage 4 zu `op`).
- Dieselben Darstellungsparameter wie die Einzelkachel (`rescale`,
  `colormap_name`, `bidx`, Format), dieselben Verbote (`expression`,
  `algorithm`, kein `url`; ein Test prüft das OpenAPI-Schema wie heute).
- Kein Parameter für Fläche, Box oder Geometrie.
- Die Reihenfolge der `item` in der URL ändert das Bild nicht (§4.3). Der
  Client schickt sie nach ID sortiert, damit dieselbe Auswahl dieselbe URL hat
  (Cache).
- TileJSON: `bounds` = Vereinigung der Item-`bbox`, `minzoom` =
  max(`viewer.min_zoom`, 8), `maxzoom` = `viewer.max_zoom` (§5).

**Wie gebaut:** eigene schlanke Fabrik in `access/tiles.py`
(`EarthxMosaicTilerFactory`, nur `tile` und `tilejson`) auf `titiler.core`'s
`BaseFactory` und `rio_tiler.mosaic.mosaic_reader`. **Nicht** `titiler.mosaic`:
es ist nicht installiert und wäre ein neues Paket samt Lock-Datei; seine
Fabrik bringt Routen mit (`/info`, `/point`, `/bbox`, Assets je Kachel), die
hier wieder abgeschaltet oder geprüft werden müssten. Das `BaseBackend` aus
rio-tiler (im venv vorhanden) kann die Umsetzung nutzen, wenn es den Code
kürzer macht (§2.7). Ob das
Erben von `BaseFactory` oder zwei eigene Routen mit den Abhängigkeiten der
Fabrik weniger Code ist, entscheidet die Umsetzung; das Verhalten ist dasselbe.

### 4.2 Pfad-Abhängigkeit (`api/tiler.py`)

Wie `dataset_asset_path`, nur für eine Liste:

1. `_dataset_config`, `_check_display_allowed`, `_check_zoom_released` — gleich.
2. Zahl der Items, Doppelte, Länge je ID prüfen (`400`).
3. Alle Items über die vorhandene Item-Quelle holen (24-h-Cache, nebenläufig
   mit `asyncio.gather`); ein fehlendes Item ist `404` wie heute.
4. **Ein Überflug:** Schlüssel `results_group_by` je Item, wie `_one_overpass`
   in `api/intake.py` (dieselbe Funktion `group_key`); verschiedene Überflüge
   `422` mit derselben Begründung wie der Job.
5. **Vorfilter:** nur die Items, deren Footprint (`geometry`) die Kachel
   schneidet (Grenzen aus der TMS). Keine → `404` „the tile does not touch
   these items“, wie heute `TileOutsideBounds`. Mehr als 12 → `422` mit „zoom
   in“ (§5).
6. **Reihenfolge:** `mosaic_order` über das CRS je Item (§4.3), verzögert
   importiert wie `_operator_support`.
7. Jede verbliebene Szene über `_resolve_asset_path` (Registry, `check_url`,
   `target_gsd_for`) — dieselbe Auflösung wie die Einzelkachel, keine neue
   Adresse ohne `check_url`.

Ergebnis ist eine geordnete Liste von `AssetPath`/`ZarrAsset`; `access` liest
sie mit `mosaic_reader` über `open_asset`.

### 4.3 Reihenfolge und Regel (S5)

- Die Szenen werden **wie im Mosaik-Job** sortiert: zuerst die im Ziel-CRS
  (dem CRS der meisten Szenen **der ganzen URL**, nicht nur der Kachel), dann
  die übrigen, je Teil nach Item-ID (`processing.mosaic.mosaic_order`, F3/F4
  von M4-12). Weil das Ziel-CRS aus der ganzen Liste kommt, wählt jede Kachel
  an einer Überlappung dieselbe Szene wie der Job — auch eine Kachel, die nur
  Szenen der anderen Zone berührt.
- Die Regel ist `FirstMethod` (`mosaic_reader`), dieselbe wie
  `merge_first_valid` (§2.4). Kein zweiter Code für die Regel.
- Ein Test belegt S5: synthetische Szenen mit verschiedenen Konstanten in der
  Überlappung, zwei Zonen; die Mosaik-Kachel zeigt in der Überlappung den Wert
  derselben Szene, die der Mosaik-Job (`processing.mosaic`) für dieselben Items
  wählt, für jede Reihenfolge der `item` in der URL.

Frage 2 klärt, ob das so bleibt, obwohl Zuschnitt und Export die
Auswahlreihenfolge nehmen (§2.1).

### 4.4 Lesen (`access`)

- `mosaic_reader(paths, read_tile, x, y, z, threads=T, chunk_size=T,
  allowed_exceptions=(TileOutsideBounds,))`, je Szene `open_asset(...).tile(...)`.
- `T = 4` (Frage 5): je Portion höchstens vier Szenen parallel, danach prüft
  `FirstMethod`, ob die Kachel voll ist. Ein Überflug aus 12 Szenen wird so in
  höchstens drei Portionen gelesen; eine voll gedeckte Kachel meist in einer.
- Das Ergebnis geht durch dieselbe Darstellung wie die Einzelkachel
  (`rescale`, `colormap_name`, Format, nodata wie in `crop_asset`).
- Zarr-Szenen: Die Kachel warpt jede Szene ohnehin nach `WebMercatorQuad`, also
  geht hier auch ein Zarr-Mosaik über zwei CRS. Der Job lehnt das ab (M4-12 F8);
  für die Anzeige gibt es keinen Grund dazu (K1).

### 4.5 Frontend

- Ein Überflug in voller Auflösung wird **ein** Overlay mit der Mosaik-URL
  statt eines je Szene (`syncFocusRaster`, `searchLayers.ts`,
  `fullResolutionLayers`); `bounds` = Vereinigung der `bbox`. Eine einzelne
  Szene bleibt bei der heutigen URL.
- Unter z8 (TileJSON-`minzoom`) zeigt der Layer die Einzelszenen wie heute
  (Frage 3).
- Mehr als 64 Szenen in einer Gruppe: wie heute Einzelszenen, mit dem
  vorhandenen Hinweistext über weggelassene Szenen ergänzt (Frage 3).
- Der Zuschnitt auf der Karte (`aoiClip.ts`) umhüllt die Mosaik-URL wie jede
  andere; keine Änderung.
- Die Vorschau eines Operators bleibt in dieser Aufgabe je Szene (Frage 4).

### 4.6 Logs, URLs, Datenschutz

- Die URL trägt Datensatz, Item-IDs, Asset und Darstellung — dieselben Angaben,
  die die Einzelkacheln heute einzeln tragen. Item-IDs nennen Szenen von rund
  110 km, keine AOI.
- Fehlermeldungen nennen höchstens die Zahl der Items und die ersten IDs, nie
  eine Adresse (wie heute).
- Kein neuer Logeintrag mit Geometrie; ein Logtest prüft, dass die Kachel-
  Grenzen nicht als Koordinaten im Log stehen (Regel aus §1.2: erst prüfen,
  dass Zeilen geloggt wurden).

### 4.7 Tests

Backend (`pytest`, synthetische COGs, kein Netz):

1. Zwei Szenen über eine Szenengrenze (Abnahme): Eine Kachel über der Naht ist
   eine Fläche; links die Werte der einen, rechts die der anderen Szene.
2. Überlappung, zwei UTM-Zonen: die gewählte Szene ist die des Mosaik-Jobs
   (S5, §4.3), für beide Reihenfolgen in der URL; Bytes beider Antworten
   gleich.
3. Vorfilter: eine dritte Szene weit weg wird nicht geöffnet (Zähler am Reader).
4. Frühes Ende: Eine voll gedeckte Kachel öffnet die zweite Portion nicht.
5. Fehlerfälle: 1 oder 65 Items, doppelte ID, überlange ID, fehlendes Item
   (`404`), Items zweier Überflüge (`422`), mehr als 12 Szenen in der Kachel
   (`422`), Kachel ohne Szene (`404`), Zoom unter 8 oder außerhalb des
   freigegebenen Bereichs (`400`), Datensatz unter Lizenzstufe `display`
   (`403`), `expression`/`url`/`bbox` als Parameter (`400` bzw. nicht im
   Schema), Asset fehlt in einer Szene (`404`).
6. Zweckfremd: `item` mit Pfadzeichen oder einer URL als Wert (`400`, keine
   Anfrage nach außen); eine Item-ID eines anderen Datensatzes (`404`).
7. Zustandslos: zwei frisch gebaute Apps liefern für dieselbe URL dieselben
   Bytes; ohne Postgres-Pool rendert der Tiler weiter (E5).
8. OpenAPI: kein Parameter `url`, `aoi`, `bbox`, `geometry`, `intersects`.
9. Logtest wie §4.6.

Frontend (`vitest`): Überflug → ein Overlay mit sortierten `item`; eine Szene →
alte URL; über 64 → Einzelszenen mit Hinweis; AOI-Clip umhüllt die
Mosaik-URL.

---

## 5. Grenzen je Kachel, mit Begründung

| Grenze | Wert | Begründung |
|---|---|---|
| Items je URL | **64** | §2.2: Überflüge bis 60 Szenen über einer landesgroßen Fläche [M]; Länge der URL bei 64 IDs ≈ 2,4 kB (Sentinel-2) bzw. ≈ 4,3 kB (Zarr, ≈ 60 Zeichen je ID), unter den Grenzen in §2.7. Die Item-Abfragen je Kachel gehen an den 24-h-Cache, nicht an die Quelle |
| Szenen je Kachel nach dem Vorfilter | **12** | §2.2: höchstens 9 bei z8 in sechs Überflügen [M]; Reserve für niedrigere Breiten, wo eine z8-Kachel bis 157 km misst und bis zu drei MGRS-Reihen und -Spalten plus Zonenüberlappung fasst [A]. Bytes: ≤ 12 × (96 + 32) kB ≈ 1,5 MB bei z8; ab z12 ≤ 8 Szenen [M] × 2 MB = 16 MB im ungünstigsten Fall, mit frühem Ende meist 1–2 Szenen |
| Mindestzoom der Mosaik-Kachel | **8** | Unter z8 berührt eine Kachel bis 13 (z7) bzw. 27 (z6) Szenen [M]; das ist Übersicht, die Aufgabe der Quicklooks und der Coverage Map (`ViewerInfo` „below `min_zoom` one tile shows several scenes“). `sentinel-2-l2a-zarr3` beginnt ohnehin bei z8 |
| Parallel gelesene Szenen | **4** je Portion | Frage 5 |

**Gelesene Bytes** lassen sich vor dem Lesen nicht deckeln: GDAL holt die
Bereiche selbst, `gateway` sieht nur die Adresse (B8). Die Byte-Grenze ergibt
sich deshalb aus Szenenzahl × Bytes je Szene (§2.3), also aus den drei Grenzen
oben. Ein eigener Byte-Zähler je Kachel wäre ein GDAL-Logging-Hook im
Lesepfad; das schlage ich nicht vor.

---

## 6. Nicht in dieser Aufgabe

- Zuschnitt und Export sortieren weiter in Auswahlreihenfolge (Frage 2).
- Mosaik mit Operator (`op`) im Kachel-Pfad (Frage 4).
- Statistik über ein Mosaik: der Client misst den Streckbereich wie heute an
  der ersten Szene (`autoStretch`); die Mosaik-Kachel nimmt `rescale` an.
- CDN, `Cache-Control` (M6, `adr/0006` §8 Punkt 3); COG-Header-Cache (Log offen).
- Mosaik über mehrere Tage oder Überflüge (Zeitreihe, nicht Mosaik).

---

## 7. Fragen an Otto

**Frage 1 — Verfahren und ADR**
1. **O1, Item-Liste in der URL, wie `adr/0006` §5 schon entschieden; kein
   `adr/0017`, sondern ein Nachtrag in `adr/0006` (Grenzen aus §5, Reihenfolge
   aus §4.3) und die seit dem 20.09.2026 fällige Berichtigung von
   `architekturplan.md` 6.3 (Empfehlung).**
2. O2, Such-ID mit Postgres-Cache nach 6.3; dann schreibe ich `adr/0017`
   (Stufe C) und halte an, weil es `adr/0006` umkehrt.
3. O3, Hash der Liste als ID mit Cache und Neu-Registrieren im Client.

**Frage 2 — Reihenfolge der Szenen (S5)**
1. **Wie der Mosaik-Job: Der Server sortiert nach `mosaic_order`, die
   Reihenfolge in der URL zählt nicht. Zuschnitt und Export bleiben in der
   Auswahlreihenfolge; dass alle vier gleich sortieren, schlage ich als eigene
   kleine Aufgabe vor (offene Log-Zeile) (Empfehlung).**
2. Wie Zuschnitt und Export: die Reihenfolge der URL gilt (Auswahl). Die Karte
   bleibt dann gleich wie der Zuschnitt, aber verschieden vom Mosaik-Job, und
   zwei Reihenfolgen derselben Szenen sind zwei Bilder und zwei Cache-Einträge.
3. Wie 1, und Zuschnitt und Export sortieren in dieser Aufgabe mit (größerer PR,
   ändert das Ergebnis des Zuschnitts an Überlappungen).

**Frage 3 — Was die Karte jenseits der Grenzen zeigt**
1. **Unter z8 und bei mehr als 64 Szenen in der Gruppe die Einzelszenen wie
   heute; über 64 zusätzlich ein Hinweis (Empfehlung).**
2. Unter z8 nichts (die Quicklooks der Trefferansicht bleiben), über 64 die
   ersten 64 in Mosaik-Reihenfolge mit Hinweis.
3. Grenzen anders setzen (bitte Werte nennen).

**Frage 4 — Mosaik mit Operator (Vorschau eines Mosaik-Jobs)**
1. **Nicht in M4-17. Die Vorschau bleibt je Szene; dass sie an Überlappungen
   anders wählen kann als der Job (§2.1), kommt als offene Log-Zeile und eigene
   Aufgabe nach M4-17 (Empfehlung).** Grund: Der Job mischt zuerst die Bänder
   und rechnet dann; eine Kachel müsste das genauso tun (Mosaik je Asset, dann
   der Operator), das ist ein Umbau von `processing/tile.py` und etwa
   300 Zeilen mehr.
2. In M4-17, als zweiter PR (M4-17b).

**Frage 5 — Parallel gelesene Szenen je Portion**
1. **4: höchstens vier Szenen gleichzeitig, danach Prüfung auf „voll“
   (Empfehlung).**
2. 1 wie der Zuschnitt: am wenigsten Bytes, aber bei 9 Szenen kalt rund 9 s.
3. alle Szenen der Kachel gleichzeitig (rio-tiler-Vorgabe): am schnellsten,
   liest immer alle.

**Frage 6 — Schnitt**
Schätzung: Backend etwa 250 Zeilen, Backend-Tests etwa 300, Frontend etwa 120,
Frontend-Tests etwa 100, Doku etwa 60.
1. **Zwei PRs: M4-17a Backend mit Tests und Doku (etwa 600) in dieser Session,
   M4-17b Frontend in einer neuen Session nach dem Merge (Empfehlung).**
2. Ein PR mit etwa 830 Zeilen.

**Frage 7 — Grenzen aus §5**
1. **64 Items je URL, 12 Szenen je Kachel, ab z8 (Empfehlung).**
2. 25 Items je URL wie `adr/0006` (dann sind die gemessenen Überflüge über
   landesgroßen Flächen zu groß für eine URL und fallen auf Einzelszenen zurück).

**Kleinentscheidungen** (gelten, sofern du nicht widersprichst):
- **K1:** Zarr-Szenen in zwei CRS sind in der Mosaik-Kachel erlaubt (§4.4).
- **K2:** Der Vorfilter nimmt den Footprint (`geometry`), nicht nur die `bbox`.
- **K3:** Mehr als 12 Szenen in einer Kachel ist `422` mit „zoom in“, kein
  Teilbild.
- **K4:** `mosaic_order` wird verzögert importiert und nicht nach `access`
  verschoben (S5: die Regel bleibt, wo sie ist).
- **K5:** Der Client sortiert die `item` nach ID (Cache); der Server nimmt jede
  Reihenfolge an.

---

## 8. Umsetzung nach Freigabe

Annahme: die Empfehlungen. Bei anderen Antworten passe ich den Plan vor dem
Code an. Commits in dieser Reihenfolge (M4-17a):

1. `access/tiles.py`: Mosaik-Fabrik (Lesen, Mischen, Darstellung) mit Tests auf
   einer nackten App.
2. `api/tiler.py`: Pfad-Abhängigkeit (Prüfungen, Überflug, Vorfilter,
   Reihenfolge), Einhängen der Routen; Tests 1–9.
3. Doku: Nachtrag `adr/0006`, Berichtigung `architekturplan.md` 6.3, Zeile in
   §3 des M4-Plans, Log.

M4-17b (Frontend) nach dem Merge: Overlay je Überflug, Rückfall, Tests;
Prüfanleitung.

---

## 9. Prüfanleitung für Otto (nach M4-17b, PowerShell 5.1)

Entwurf; die Antwortform prüfe ich nach der Umsetzung gegen den laufenden
`tiler`, bevor ich sie als fertig melde.

**A — Backend allein (nach M4-17a).** Sucht einen Überflug über zwei Zonen
(Zonengrenze bei 12° O) und holt eine Kachel über der Naht einmal als Mosaik,
einmal mit umgekehrter Reihenfolge der Items. Das Suchrechteck ist eine
Messfläche, keine AOI.

```powershell
docker compose up -d --build
$api = 'http://localhost:8000'; $tiler = 'http://localhost:8001'

$search = @{ collections = @('sentinel-2-c1-l2a'); bbox = @(10.5, 47.0, 13.5, 48.5)
             datetime = '2025-07-01T00:00:00Z/2025-07-31T23:59:59Z'; limit = 100 } | ConvertTo-Json -Depth 10
$items = (Invoke-RestMethod -Method Post -Uri "${api}/stac/search" `
          -ContentType application/json -Body $search).features
$pass = $items | Group-Object { $_.properties.'s2:datatake_id' } |
        Sort-Object Count -Descending | Select-Object -First 1
$ids = @($pass.Group | ForEach-Object { $_.id } | Sort-Object)
'{0} Szenen im Überflug' -f $ids.Count

# Kachel z10 über der Mitte des Überflugs
$w = ($pass.Group | ForEach-Object { $_.bbox[0] } | Measure-Object -Minimum).Minimum
$e = ($pass.Group | ForEach-Object { $_.bbox[2] } | Measure-Object -Maximum).Maximum
$s = ($pass.Group | ForEach-Object { $_.bbox[1] } | Measure-Object -Minimum).Minimum
$n = ($pass.Group | ForEach-Object { $_.bbox[3] } | Measure-Object -Maximum).Maximum
$lon = ($w + $e) / 2; $lat = ($s + $n) / 2; $z = 10
$x = [Math]::Floor(($lon + 180) / 360 * [Math]::Pow(2, $z))
$r = $lat * [Math]::PI / 180
$y = [Math]::Floor((1 - [Math]::Log([Math]::Tan($r) + 1 / [Math]::Cos($r)) / [Math]::PI) / 2 * [Math]::Pow(2, $z))

function Get-MosaicTile($list, $file) {
    $q = ($list | ForEach-Object { 'item=' + $_ }) -join '&'
    Invoke-WebRequest -UseBasicParsing -OutFile $file `
        -Uri "${tiler}/collections/sentinel-2-c1-l2a/mosaic/tiles/WebMercatorQuad/${z}/${x}/${y}.png?${q}&asset=visual"
}
Get-MosaicTile $ids 'mosaic.png'
[Array]::Reverse($ids); Get-MosaicTile $ids 'mosaic-reverse.png'
(Get-FileHash mosaic.png).Hash -eq (Get-FileHash mosaic-reverse.png).Hash   # True: Reihenfolge egal
Start-Process mosaic.png                                                     # eine Fläche, keine Lücke an der Naht
```

Gegenproben: dieselbe URL mit `z=7` → `400`; mit einer Szene eines anderen
Tages zusätzlich → `422`; mit `&bbox=1,2,3,4` → `400`.

**B — im Viewer (nach M4-17b).** Einen Überflug über zwei Kacheln in voller
Auflösung öffnen: Die Szenen erscheinen als eine Fläche, im Layer-Manager ein
Eintrag; die Netzwerkansicht des Browsers zeigt je Kartenkachel **eine**
Anfrage an `…/mosaic/tiles/…` statt einer je Szene, und keine URL enthält
Koordinaten der AOI.

---

## 10. Messanhang

Zu §2.2. Zwei Anfragen an Earth Search, 2 s Abstand, nur Metadaten; das
Rechteck ist eine Messfläche, keine AOI eines Nutzers:

```bash
for d in 2026-08-14 2026-09-03; do
  curl -sS -X POST https://earth-search.aws.element84.com/v1/search \
    -H 'content-type: application/json' \
    -d "{\"collections\":[\"sentinel-2-c1-l2a\"],\"bbox\":[5.0,45.0,16.0,55.0],
         \"datetime\":\"${d}T00:00:00Z/${d}T23:59:59Z\",\"limit\":200}" -o s2_$d.json
  sleep 2
done
# 93 bzw. 100 Items, je drei Datatakes, Item-IDs je 30 Zeichen
```

Auswertung (offline, `morecantile` 7.1.0, `shapely`):

```python
tms = morecantile.tms.get("WebMercatorQuad")
for items in overpasses:                     # gruppiert nach s2:datatake_id
    for z in (6, 7, 8, 9, 10, 11, 12):
        hits = Counter()
        for item in items:
            footprint = shape(item["geometry"])
            for t in tms.tiles(*item["bbox"], [z]):
                if footprint.intersects(box(*tms.bounds(t))):
                    hits[t] += 1
        print(z, max(hits.values()))
```

Doppelte Kachelnamen je Datatake: `Counter(item["properties"]["grid:code"])`;
14.08.: 3 Paare unter 53 Szenen, 03.09.: 10 Paare unter 60, beide mit
verschiedenen Aufnahmezeiten im Item-ID (`…T104743…`/`…T104037…`).
