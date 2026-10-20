# M4-17 — Mosaik im Kachel-Pfad: Plan

**Stand:** 20.10.2026, Plan freigegeben (§11); M4-17a umgesetzt (§12), M4-17b umgesetzt (§14), M4-17c folgt in einer neuen Session (§13).
**Stufe B:** Bis zur Freigabe ist kein Produktivcode geändert. Nach der Freigabe
setzt dieselbe Session um (oder die Sessions aus Frage 6).
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Startsatz:** „Führe Aufgabe M4-17 aus `docs/plans/m4-processing-kern.md` aus.“
**Grundlage:**
- `plans/m4-processing-kern.md` M4-17, S5 (§1.1c), §1.2, Abnahme 7 (§5).
- `adr/0006` §2 (K1–K8), §3.4, §3.5, §4.2 (M1–M4), §5 „Zu Frage 4“, §6 Folge 1.
- `adr/0001` Z4; E4/E5 (`plans/m1-fundament.md` §1); `architekturplan.md` 6.3,
  12.1, 12.3.
- `plans/m4-12-mosaik-ueberflug.md` §8 F3/F4, §11, §12 (Mosaikregel, Reihenfolge).
- `plans/m3-dritte-quelle-und-interface.md` P11.

Belegstufen wie in `adr/0009`: [M] gemessen, [P] am Primärdokument oder im
Code gelesen, [S] Zusammenfassung oder Suchtreffer, [A] eigene Ableitung.

**Kurzfassung.**

- Der `tiler` bekommt eine Mosaik-Kachel: Kachel und TileJSON wie heute für
  eine Szene, aber über die Szenen **eines Überflugs**, die als Item-Liste in
  der URL stehen (`adr/0006` §4.2, M1). Keine Such-ID, keine neue Tabelle,
  kein neues Paket (§3, §4).
- Die Reihenfolge ist die des Mosaik-Jobs (`mosaic_order`), die Regel
  `FirstMethod` bzw. `merge_first_valid` — unverändert (S5). Der Server
  sortiert; die Reihenfolge in der URL zählt nicht.
- Grenzen: höchstens 64 Szenen je URL, höchstens 12 gelesene Szenen je Kachel,
  Mosaik-Kacheln ab z8 (§5). Gemessen: Ein Überflug über einer landesgroßen
  Fläche hat bis 60 Szenen, eine z8-Kachel berührt davon höchstens 9 (§2.2).
- Neu gegenüber `adr/0006`: Jede Mosaik-Kachel braucht die Metadaten **aller**
  Items der URL (Vorfilter, Reihenfolge), und die Suche füllt den Item-Cache
  nicht (§2.8). Ohne Gegenmittel holt ein kalter Kartenausschnitt dieselben
  Items vielfach von der Quelle. Vorschlag in §4.3, Frage 8.
- Befund: Die Karte mosaikiert schon heute — als Stapel einzelner Layer in der
  **Auswahlreihenfolge**, der Regel des Zuschnitts, nicht der des Mosaik-Jobs
  (§2.1). Daraus folgt Frage 2.
- Acht Fragen an Otto (§7); `adr/0017` halte ich nicht für nötig, weil
  `adr/0006` die Grundsatzfrage schon entschieden hat (Frage 1).

---

## 1. Was schon entschieden ist

| Quelle | Inhalt | Folge hier |
|---|---|---|
| `adr/0006` §5 „Zu Frage 4“ | Mosaik im Kachel-Pfad, wenn es kommt, „als Item-Liste in der URL (M1), nie als Such-ID“; höchstens 25 Items je URL; Vorfilter über die Item-`bbox` | Option O1 (§3); die 25 werden mit Messung neu begründet (§5) |
| `adr/0006` §6 Folge 1 | Der Satz zur Such-ID in `architekturplan.md` 6.3 „kehrt seine eigene Begründung um und ist zu ersetzen“ | nie nachgezogen: 6.3 nennt die Such-ID heute noch (§2.6) |
| `adr/0006` §7 Frage 1, P11, Q7 | Mosaik im Kachel-Pfad erst in M4b | diese Aufgabe |
| S5 | dieselbe Mosaikregel (Reihenfolge, Überlappung) wie Export-Job und Mosaik-Job; M4-17 ändert sie nicht | §4.4, Frage 2 |
| M4-12 F3, F4 | erstes gültiges Pixel in der Reihenfolge der Liste; `api` sortiert die Liste eines Mosaik-Jobs: zuerst die Szenen im Ziel-CRS, dann die übrigen, je nach Item-ID; Ziel-CRS = das der meisten Szenen, bei Gleichstand die kleinere EPSG-Zahl | §4.4 |
| `adr/0001` Z4; `adr/0006` K3 | die Kachel-URL bestimmt das Bild vollständig | §4.1 |
| E4, E5 | Anwendungs-Cache in Postgres; ein Ausfall macht nur langsamer | Option O2 (§3); Frage 8 |
| Q8, §1.2 | keine AOI und kein Rezept-Hash nach außen, nicht in URLs, nicht in Logs | §4.7 |
| KLAERUNGEN B8 | jede Adresse passiert `check_url`, bevor GDAL sie sieht | §4.2: dieselbe Auflösung wie die Einzelkachel |
| KLAERUNGEN B11 | Anzeige ab Lizenzstufe `display` | §4.2: dieselbe Prüfung wie die Einzelkachel |

---

## 2. Befunde

### 2.1 Die Karte mosaikiert heute im Browser, in der Auswahlreihenfolge [P]

- Jede Szene ist eine eigene MapLibre-Quelle mit eigener Kachel-URL
  (`frontend/src/mapLayers.ts` `syncFocusRaster`, `addTiles`; Vorlage
  `api.ts` `buildTileTemplate`). Je Kartenkachel fragt der Browser so viele
  Kacheln an, wie Szenen sie berühren; der `tiler` liest jede für sich.
- Die Stapelung ist „zuerst gewählte Szene oben“ (`syncFocusRaster`, seit dem
  Befund aus M3-09), also erstes gültiges Pixel **in der Auswahlreihenfolge**.
  Das ist die Reihenfolge des synchronen Zuschnitts und des Export-Jobs: Beide
  nehmen die Liste, wie der Client sie schickt (`access/download.py`
  `crop_asset`, `processing/export.py`). Der Mosaik-Job sortiert dagegen in
  `api` (`api/intake.py` `_one_overpass` → `mosaic_order`). Heute stimmen
  Karte und Zuschnitt an Überlappungen überein, Karte und Mosaik-Job nicht.
- Die Vorschau eines Operators (`processingPreview.ts`) stapelt ebenso je
  Szene, in der Reihenfolge der Auswahl; der Job, dessen Vorschau sie ist,
  rechnet als Mosaik in der sortierten Reihenfolge. Wo sich zwei Szenen mit
  verschiedenen Werten überlappen, zeigen Vorschau und Job heute verschiedene
  Szenen.
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
gespeicherten Antworten, offline (§10.1).

### 2.3 Was eine Mosaik-Kachel an Pixeln kostet [M aus `adr/0006`, A]

`adr/0006` §3.4 und §3.5 (gemessen gegen dieselbe Quelle):

| Zoom | gelesen je Szene, kalt | Zeit je Szene, kalt | warm, je Kachel |
|---|---|---|---|
| z8 | 96 kB (+ 32 kB Kopf) | ~1,0 s | — |
| z10 | 160 kB | ~0,7 s | 115–193 ms |
| z12 | 1164 kB | ~1,2 s | — |
| z14–z18 | 2016 kB | ~1,0–1,2 s | 54 ms |

Eine Mosaik-Kachel an einer Naht (2 Szenen, z11): 2,7 MB, 1,1–1,9 s.

**[A]** Der Browser fragt heute je Kartenkachel jede berührende Szene einzeln
an (§2.1). Die Mosaik-Kachel liest dieselben Szenen — höchstens; mit
`FirstMethod` und Lesen in Portionen hört sie auf, sobald jedes Pixel gefüllt
ist (§4.5). An Pixeln wird es für die Quelle also nicht teurer, eher billiger;
für den Browser sind es N-mal weniger Anfragen. Die 2,7 MB von `adr/0006` sind
kein Aufschlag des Mosaiks, sondern zweimal der Preis einer Szene ab z12. Was
neu dazukommt, sind die Item-Abrufe (§2.8).

### 2.4 Die Mosaikregel liegt an zwei Stellen, die `access` nicht beide erreicht [P]

- `access/crop_rules.py` `merge_first_valid` und rio-tilers `FirstMethod`
  (im Zuschnitt über `mosaic_reader`) sind dieselbe Regel; die Docstrings
  sagen es, `tests/earthx/processing/test_export.py` belegt es (Zuschnitt
  gegen Export bitgleich, M4-11a), `test_mosaic.py` den Vergleich Mosaik-Job
  gegen Export (M4-12a).
- Die **Reihenfolge** des Mosaik-Jobs liegt in `processing/mosaic.py`
  (`target_crs`, `mosaic_order`). `access` darf `processing` nicht importieren
  (`.importlinter`, Vertrag `access`); `api` darf es und tut es schon
  (`api/intake.py`).
- Der `tiler` lädt `processing` erst bei Bedarf (`_operator_support`); der Test
  `tests/earthx/api/test_tiler_start_is_light.py` hält das fest. Ein Import von
  `earthx.processing.mosaic` lädt über `processing/__init__.py` den ganzen
  Worker-Kern.
- Die beiden Funktionen der Reihenfolge sind rein (Zählen, Sortieren, EPSG aus
  `rasterio.crs`). Folge: Kleinentscheidung KE4 (§7).

### 2.5 `mosaic_reader` hält die Reihenfolge, auch mit Threads [P]

`rio_tiler` 9.4.6 im venv, `mosaic/reader.py` und `tasks.py`: Die Liste wird in
Portionen (`chunk_size`, Vorgabe = `threads`) gelesen; innerhalb einer Portion
parallel und vollständig (der `ThreadPoolExecutor` wartet auf alle), das
Ergebnis aber in der Reihenfolge der Liste gemischt (`filter_tasks` iteriert
die Futures der Reihe nach). Nach jeder Portion prüft er
`pixel_selection.is_done` und hört auf. Mit `threads=1` liest er Szene für
Szene und hört nach der ersten auf, die alles füllt (so der synchrone Zuschnitt,
M3-18 F4). `allowed_exceptions` lässt `TileOutsideBounds` durch, ohne
abzubrechen.

### 2.6 Widerspruch in den Dokumenten [P]

`architekturplan.md` 6.3 sagt weiter: „Suchergebnis wird unter einer Such-ID
kurz gecacht, damit Tile-URLs stabil und CDN-fähig sind“; die Aufgabe M4-17
nennt diese Option deshalb ausdrücklich. `adr/0006` (angenommen) hat sie am
20.09.2026 verworfen und die Berichtigung von 6.3 als Folge 1 genannt; sie ist
nie geschehen. Nach der Rangfolge gilt das ADR. Die Abwägung in §3 holt sie
trotzdem nach, weil die Aufgabe sie verlangt. Ebenso überholt wäre nach dieser
Aufgabe der Docstring von `ViewerInfo` („every tile URL is per-item, never a
mosaic“, `catalog/registry.py`).

### 2.7 Stand der Technik

Recherche vom 20.10.2026. Erreichbar waren GitHub-Rohdateien und
Suchmaschinen, die Doku-Seiten von Development Seed, Planetary Computer, AWS,
Sentinel Hub und Earth Engine nicht. **[P]** steht nur, wo ich die Datei selbst
gelesen habe (rio-tiler im venv; fünf Rohdateien per `curl`, §10.2); was ein
Subagent über die Zusammenfassung seines Abrufwerkzeugs gelesen hat, steht auf
**[S]**.

| Befund | Beleg | Stufe | Folge hier |
|---|---|---|---|
| pgstac speichert eine registrierte Suche in `searches` mit `hash text PRIMARY KEY` (SHA-256 über WHERE-Klausel und Metadaten), dazu `lastused`, `usecount`; im SQL gibt es kein Löschen | [`004_search.sql`](https://raw.githubusercontent.com/stac-utils/pgstac/main/src/pgstac/sql/004_search.sql) | P | das Muster von O2/O3: eine inhaltsadressierte ID, die ohne Eintrag nichts bedeutet |
| „retention-driven GC“ für `searches` steht im Changelog erst unter „Unreleased“ | [pgstac `CHANGELOG.md`](https://raw.githubusercontent.com/stac-utils/pgstac/main/CHANGELOG.md) | S | eine *kurzlebige* Such-ID ist dort nicht gelöst |
| titiler-pgstac: Kachel-Grenzen `scan_limit` 10000, `items_limit` 100, `time_limit` 5 s, `exitwhenfull` und `skipcovered` an | [`titiler/pgstac/settings.py`](https://raw.githubusercontent.com/stac-utils/titiler-pgstac/main/titiler/pgstac/settings.py) | P | „aufhören, sobald voll“ ist Praxis (§4.5) |
| Planetary Computer: **höchstens 10 Items je Kachel** als Vorgabe (`default_max_items_per_tile`) | [`pctiler/config.py`](https://raw.githubusercontent.com/microsoft/planetary-computer-apis/main/pctiler/pctiler/config.py) | P | Größenordnung der Grenze in §5 (dort 12, gemessen begründet) |
| Planetary Computer: `minzoom` und `max_items_per_tile` je Collection; Beispiel-Mosaik Sentinel-2 mit `minZoom: 9` | [`pctiler/reader.py`](https://raw.githubusercontent.com/microsoft/planetary-computer-apis/main/pctiler/pctiler/reader.py), [Quickstart-Notebook](https://raw.githubusercontent.com/microsoft/PlanetaryComputerExamples/main/quickstarts/using-the-data-api.ipynb) | S | Mindestzoom wie in §5 |
| `mosaic_reader`, `FirstMethod` (`exit_when_filled`), Portionen | rio-tiler 9.4.6 im venv (§2.5) | P | §4.5, Frage 5 |
| Ein eigenes Mosaik-Backend ist vorgesehen: `rio_tiler.mosaic.backend.BaseBackend` mit `assets_for_tile`, `assets_for_point`, `assets_for_bbox` und `tile()` | rio-tiler 9.4.6 im venv | P | O1 geht ohne neues Paket |
| `titiler.mosaic`s `MosaicTilerFactory` nimmt ein solches Backend; Threads über `MOSAIC_CONCURRENCY` | [`titiler/mosaic/factory.py`](https://raw.githubusercontent.com/developmentseed/titiler/main/src/titiler/mosaic/titiler/mosaic/factory.py) | S | nicht installiert, wäre ein neues Paket (§4.1) |
| titiler, Diskussion zu Mosaiken bei niedrigem Zoom (rund 950 COGs): z8 8–16 s, z7 35–60 s, z6 Timeout; Rat der Maintainer: Mosaik erst ab einem Mindestzoom | [titiler Discussion #287](https://github.com/developmentseed/titiler/discussions/287) | S | Mindestzoom in §5 |
| titiler-stacapi sucht je Kachel bei der STAC-API; die Doku warnt, dass jede Kachel eine Suche kostet | [`titiler/stacapi/backend.py`](https://raw.githubusercontent.com/developmentseed/titiler-stacapi/main/titiler/stacapi/backend.py) | S | O4 verworfen |
| MosaicJSON: Quadkey → Asset-URLs; `cogeo-mosaic` liest die Datei über `httpx2` bzw. `boto3` | [`backends/web.py`](https://raw.githubusercontent.com/developmentseed/cogeo-mosaic/main/cogeo_mosaic/backends/web.py), [`backends/s3.py`](https://raw.githubusercontent.com/developmentseed/cogeo-mosaic/main/cogeo_mosaic/backends/s3.py) | S | O5 verworfen (B8), wie `adr/0006` §3.2 |
| Reihenfolge anderswo: pgstac ohne `sortby` `datetime DESC, id DESC`; Sentinel Hub `mostRecent`/`leastCC`; Earth Engine „letztes oben“ | [`002d_keyset.sql`](https://raw.githubusercontent.com/stac-utils/pgstac/main/src/pgstac/sql/002d_keyset.sql); Forum, Earth-Engine-Guide | S | keine allgemeine Regel; S5 legt sie fest |
| uvicorn mit `h11`: 16 384 Byte für ein unvollständiges Ereignis (Anfragezeile und Kopfzeilen) | [uvicorn `docs/settings.md`](https://raw.githubusercontent.com/encode/uvicorn/master/docs/settings.md) | P | weit über der URL von O1 |
| Im Image ist auch `httptools` installiert (`requirements.lock`), das uvicorn dann vorzieht; seine Grenze ist nicht dokumentiert | Lock-Datei | P | ein Test mit einer 64-Item-URL gegen den echten Server (§4.8 Test 10) |
| nginx `large_client_header_buffers` Vorgabe `4 8k`, Anfragezeile über 8 kB → `414` | [`ngx_http_core_module.xml`](https://raw.githubusercontent.com/nginx/nginx.org/master/xml/en/docs/http/ngx_http_core_module.xml) | P | engste Grenze für einen späteren Proxy |
| CloudFront und Fastly 8 kB je URL, Cloudflare 16–32 kB, AWS ALB 16 kB; Browser weit darüber | Quotas-Seiten der Anbieter | S | engste Grenze 8 kB; 64 IDs ≈ 2,4 bzw. 4,3 kB (§5) |

Für Sentinel-2-COGs über HTTP gibt es keine veröffentlichten Kosten je
Mosaik-Kachel; die Zahlen dazu sind die eigenen aus `adr/0006` (§2.3).

### 2.8 Jede Mosaik-Kachel braucht alle Items — und die Suche füllt deren Cache nicht [P, A]

- Der Item-Cache (24 h, Postgres) wird nur von `get_item` gefüllt
  (`adapters/earth_search.py`, `adapters/eopf_stac.py`), **nicht** von der
  Suche. Der Satz in `adr/0006` §3.5 „die vorangegangene Suche hat die Items
  ohnehin schon geliefert“ trifft für den Cache nicht zu.
- Für Vorfilter und Reihenfolge braucht jede Mosaik-Kachel Footprint und CRS
  **aller** Items der URL, nicht nur der berührten.
- `item_source` hält während eines Abrufs bei der Quelle eine Verbindung aus
  dem Pool (`api/item_source.py`); der Pool hat höchstens 5
  (`api/dependencies.py`), `gateway` höchstens 6 Verbindungen je Host
  (`gateway/policy.py`). Gleichzeitige Abrufe desselben Items werden nicht
  zusammengelegt.
- Ohne Postgres-Pool gibt es keinen Item-Cache: jede Kachel holt jedes Item
  von der Quelle.

**[A] Folge ohne Gegenmittel:** Ein kalter Kartenausschnitt mit sechs
gleichzeitigen Kachelanfragen (Annahme: sechs Verbindungen je Host im Browser) über einen Überflug aus 60 Szenen holt bis zu
6 × 60 = 360 Items von der Quelle, bis der Cache warm ist; heute (eine Quelle
je Szene) ist es höchstens eine Anfrage je Szene und Kachel, die die Szene
berührt. Ohne Pool wäre es 60 Anfragen **je Kachel**. Eine einzige Anfrage mit
64 gültigen IDs verstärkt die Last auf die Quelle um das 64-Fache — das ist
auch eine zweckfremde Nutzung, gegen die der Entwurf etwas braucht (§4.3).

**[A] Mit Gegenmittel (§4.3):** einmal je Item und 24 h, also so viele Anfragen
an die Quelle wie heute. Zeit für das erste Bild eines kalten Überflugs aus 60
Szenen: 60 × 0,42–0,47 s (Item-GET, `adr/0006` §3.5 [M]) bei 6 Verbindungen
≈ 5 s; danach Cache-Treffer.

---

## 3. Optionen

Kriterien aus `adr/0006` §2 (K1–K8), dazu **K9** dieselbe Mosaikregel wie
Mosaik-Job und Export (S5) und **K10** keine exakte AOI in URL oder Log (Q8).

| | Option | K3 URL bestimmt Bild | K5 kein Zustand | K6 Quelle | K7 Teile | K9 | K10 | Bewertung |
|---|---|---|---|---|---|---|---|---|
| **O1** | **Item-Liste in der URL**, Server sortiert und mischt | ja | ja, nur die vorhandenen Caches | Pixel wie heute oder weniger (§2.3); Items einmal je 24 h nur mit dem Gegenmittel aus §4.3 | eine Route mehr, keine Tabelle, kein Paket | ja | ja (Item-IDs, keine Fläche) | **Empfehlung** |
| O2 | Such-ID: `POST` registriert die Liste, Postgres-Tabelle mit kurzer Frist, Kachel-URL trägt nur die ID (6.3, E4; Muster von titiler-pgstac) | nein: ist der Eintrag weg, ist die URL tot oder zeigt nach erneuter Registrierung anderes | Zustand in Postgres, den der Tiler zum Rendern **braucht** — ein Ausfall macht leer, nicht langsamer (verletzt E5) | wie O1; die Liste der Items läge schon beim Registrieren vor | Tabelle, Migration, Kehraus, Registrier-Route, Wiederholung im Client | ja | ja | verworfen wie in `adr/0006` |
| O3 | Inhaltsadresse: ID = Hash der sortierten Liste, Liste im Cache; fehlt der Eintrag, `404` und der Client registriert neu | ja, solange der Eintrag lebt | wie O2 | wie O2 | wie O2 | ja | ja | kürzere URL als einziger Vorteil; die URL von O1 passt (§5) |
| O4 | Überflug-Schlüssel in der URL (`datatake`), der Tiler sucht die Szenen je Kachel selbst | nein: hängt am Stand der Quelle | Suche je Kachel oder Cache je Überflug | **schlecht**: eine föderierte Suche je neuer Kachelfläche (titiler-stacapi warnt selbst) | Suche im Tiler, Filter nach Property in jedem Adapter | ja | ja | verworfen (Prinzip 10, „Suche läuft in `api`“) |
| O5 | MosaicJSON (`cogeo-mosaic`) | ja | Datei je Mosaik nötig | gleich | neues Paket, liest die Datei selbst über eigenen HTTP-Client | ja | ja | verworfen (B8, `adr/0006` §4.2 M3) |

**Warum O1 trotz längerer URL:** 64 Item-IDs von Sentinel-2 (30 Zeichen) sind
mit `item=` rund 2,4 kB, von `sentinel-2-l2a-zarr3` (rund 60 Zeichen) rund
4,3 kB (§5). Das liegt unter der engsten belegten Grenze von 8 kB (§2.7). Ein
CDN steht erst mit M6 vor dem Tiler; bis dahin zählt die URL-Länge nur für
Browser und Server.

---

## 4. Entwurf (Option O1)

### 4.1 Routen

Im `tiler` (`earthx.api.tiler`), neben dem Router je Item:

```
GET /collections/{dataset}/mosaic/tiles/{tileMatrixSetId}/{z}/{x}/{y}[@{scale}x][.{format}]
    ?item=<id>&item=<id>…&asset=<key>[&rescale=…][&colormap_name=…][&bidx=…]
GET /collections/{dataset}/mosaic/{tileMatrixSetId}/tilejson.json?item=…&asset=…
```

- `item` wiederholt (wie `asset` bei den Operator-Kacheln), 2 bis 64
  verschiedene IDs; `asset` genau eines.
- Dieselben Darstellungsparameter wie die Einzelkachel (`rescale`,
  `colormap_name`, `bidx`, Format).
- **Ausdrücklich mit `400` abgewiesen:** `expression`, `algorithm`,
  `algorithm_params` (wie heute), dazu `op`, `op_version`, `params` (Frage 4)
  und jeder Parameter, der eine Fläche tragen könnte: `bbox`, `aoi`,
  `geometry`, `intersects`, `url`. Ein Test prüft außerdem das OpenAPI-Schema
  wie heute.
- Die Reihenfolge der `item` in der URL ändert das Bild nicht (§4.4). Der
  Client schickt sie nach ID sortiert, damit dieselbe Auswahl dieselbe URL hat.
- **TileJSON:** `bounds` = Vereinigung der Item-`bbox`, `minzoom` =
  max(`viewer.min_zoom`, 8), `maxzoom` = `viewer.max_zoom` (§5), dazu
  `earthx:order` — die Item-IDs in der Reihenfolge, in der die Kachel sie
  liest. Der Client lädt das TileJSON zuerst (§4.3) und stapelt mit
  `earthx:order` auch den Rückfall unter z8 gleich (§4.6).

**Wie gebaut:** eine schlanke Fabrik in `access/tiles.py` (nur `tile` und
`tilejson`) auf `titiler.core`'s `BaseFactory` und `rio_tiler.mosaic`, wahlweise
über rio-tilers `BaseBackend` (im venv vorhanden). **Nicht** `titiler.mosaic`:
es ist nicht installiert und wäre ein neues Paket samt Lock-Datei. Welche der
beiden Formen weniger Code ist, entscheidet die Umsetzung; das Verhalten ist
dasselbe.

### 4.2 Pfad-Abhängigkeit (`api/tiler.py`)

Wie `dataset_asset_path`, nur für eine Liste:

1. `_dataset_config`, `_check_display_allowed`, `_check_zoom_released` wie
   heute; ein Datensatz ohne `viewer` ist `501` wie heute. **Dazu:** Eine
   Mosaik-Kachel unter z8 ist `400` („mosaic tiles start at z8“). Alles vor
   dem ersten Item-Abruf.
2. Freie und flächenhafte Parameter (§4.1) → `400`.
3. Zahl der Items (2–64), Doppelte, und jede ID gegen dieselbe Zeichenregel
   wie föderierte Items (`ITEM_ID` in `adapters/federated_search.py`), für alle
   Datensätze, auch materialisierte → `400`.
4. Alle Items holen, wie in §4.3 beschrieben; ein fehlendes Item ist `404` wie
   heute.
5. **Ein Überflug:** Schlüssel `results_group_by` je Item mit `group_key`
   (`catalog/registry.py`), wie `_one_overpass`; verschiedene Überflüge → `422`
   mit derselben Begründung wie der Job. Bei `cop-dem-glo-30` ist der Schlüssel
   `start_datetime` und damit für alle Kacheln gleich: Ein DEM-Mosaik ist das
   nahtlose Höhenmodell über bis zu 64 Kacheln — gewollt.
6. **CRS je Item** über `resolve_asset(...).crs` (`access/resolve.py`), wie
   `_one_overpass`, für **alle** Items der URL (das Ziel-CRS kommt aus der
   ganzen Liste, §4.4).
7. **Vorfilter:** nur die Items, deren Footprint (`geometry`) die Kachel
   schneidet (Grenzen aus der TMS). Keine → `404` „the tile does not touch
   these items“, wie heute `TileOutsideBounds`. Mehr als 12 → `422` mit „zoom
   in“ (§5).
8. **Reihenfolge** `mosaic_order` (§4.4).
9. Jede verbliebene Szene über `_resolve_asset_path` (Registry, `check_url`,
   `target_gsd_for`) — dieselbe Auflösung wie die Einzelkachel, keine Adresse
   ohne `check_url`.

Ergebnis ist eine geordnete Liste von `AssetPath`/`ZarrAsset`; `access` liest
sie über `open_asset`.

Ohne Capability-Prüfung `reprojection`: Die Einzelkachel prüft sie auch nicht,
jede Kachel wird nach `WebMercatorQuad` gewarpt, und Anzeige mit Reprojektion
ist durch Lizenzstufe `display` gedeckt (B11). Der Job prüft sie, weil er ein
neues Raster schreibt (KE7).

### 4.3 Item-Abrufe (Gegenmittel zu §2.8)

1. **Zusammenlegen im Prozess:** Gleichzeitige Abrufe desselben Items teilen
   sich einen Abruf (ein `dict` laufender Futures, Eintrag fällt mit dem Ende
   des Abrufs weg). Kein Zustand über die Anfrage hinaus.
2. **Gedrosselt je Anfrage:** höchstens 4 Item-Abrufe einer Kachel oder eines
   TileJSON gleichzeitig (Pool 5, `gateway` 6 je Host).
3. **Vorwärmen über das TileJSON:** Der Client lädt für jeden Mosaik-Layer
   zuerst das TileJSON (MapLibre tut das für eine Quelle mit `url` ohnehin);
   es holt alle Items einmal und füllt den 24-h-Cache. Die Kacheln danach sind
   Cache-Treffer.
4. **Ohne Postgres-Pool:** Für föderierte Datensätze antwortet die Mosaik-Route
   `503` („mosaic tiles need the item cache“); die Einzelkachel bleibt wie
   heute. Das weicht von E5 ab (Ausfall macht hier nicht nur langsamer, sondern
   die Mosaik-Kachel fällt aus) — deshalb Frage 8.
5. **Kosten der Cache-Lookups:** 64 Lookups je Kachel misst die Umsetzung
   lokal; liegen sie über 50 ms je Kachel, kommt eine gebündelte Abfrage
   (`get_many` am Such-Cache in `catalog`, eine Verbindung je Kachel).

### 4.4 Reihenfolge und Regel (S5)

- Die Szenen werden **wie im Mosaik-Job** sortiert: zuerst die im Ziel-CRS
  (dem CRS der meisten Szenen **der ganzen URL**, nicht nur der Kachel), dann
  die übrigen, je Teil nach Item-ID (`mosaic_order`, F3/F4 von M4-12). Weil das
  Ziel-CRS aus der ganzen Liste kommt, wählt jede Kachel an einer Überlappung
  dieselbe Szene wie ein Mosaik-Job **über dieselbe Liste** — auch eine Kachel,
  die nur Szenen der anderen Zone berührt. Eine andere Liste (etwa ein Job über
  einen Teil der Szenen) kann ein anderes Ziel-CRS ergeben.
- Die Regel ist `FirstMethod` (`mosaic_reader`), dieselbe wie
  `merge_first_valid` (§2.4). Kein zweiter Code für die Regel.
- Ein Test belegt S5 (§4.8 Test 2).

Frage 2 klärt, ob das so bleibt, obwohl Zuschnitt und Export die
Auswahlreihenfolge nehmen (§2.1).

### 4.5 Lesen (`access`)

- `mosaic_reader(paths, read_tile, x, y, z, threads=T, chunk_size=T,
  allowed_exceptions=(TileOutsideBounds,))`, je Szene `open_asset(...).tile(...)`.
- `T = 4` (Frage 5): je Portion höchstens vier Szenen parallel, danach prüft
  `FirstMethod`, ob die Kachel voll ist. Zwölf Szenen werden so in höchstens
  drei Portionen gelesen; eine voll gedeckte Kachel meist in einer.
- Das Ergebnis geht durch dieselbe Darstellung wie die Einzelkachel
  (`rescale`, `colormap_name`, Format; nodata wie in `crop_asset`).
- Zarr-Szenen: Die Kachel warpt jede Szene ohnehin nach `WebMercatorQuad`,
  also geht hier auch ein Zarr-Mosaik über zwei CRS. Der Job lehnt das ab
  (M4-12 F8); für die Anzeige gibt es keinen Grund dazu (KE1).

### 4.6 Frontend

- Ein Überflug in voller Auflösung wird **ein** Layer mit der Mosaik-URL statt
  eines je Szene (`syncFocusRaster`, `searchLayers.ts` `fullResolutionLayers`),
  als MapLibre-Quelle mit `url` auf das TileJSON (§4.3); `bounds` aus dem
  TileJSON. Eine einzelne Szene bleibt bei der heutigen URL.
- Unter z8 zeigt die Karte die Einzelszenen, gestapelt nach `earthx:order` aus
  dem TileJSON, also ebenfalls in der Reihenfolge des Mosaiks (Frage 3). So
  wechselt die sichtbare Szene an einer Überlappung beim Zoomen über z8 nicht.
- Mehr als 64 Szenen in einer Gruppe: Einzelszenen wie heute (Auswahlreihenfolge,
  höchstens 40, `MAX_MOSAIC_LAYERS`), dazu ein **neuer** Hinweis, dass die
  Gruppe zu groß für ein Mosaik ist und wie viele Szenen nicht gezeigt werden.
- Der Zuschnitt auf der Karte (`aoiClip.ts`) umhüllt die Mosaik-URL wie jede
  andere.
- Die Vorschau eines Operators bleibt in dieser Aufgabe je Szene (Frage 4).

### 4.7 Logs, URLs, Datenschutz

- Die URL trägt Datensatz, Item-IDs, Asset und Darstellung — dieselben Angaben,
  die die Einzelkacheln heute einzeln tragen. Item-IDs nennen Szenen von rund
  110 km, keine AOI.
- Fehlermeldungen nennen höchstens die Zahl der Items und die ersten IDs, nie
  eine Adresse (wie heute).
- Kein neuer Logeintrag mit Geometrie; ein Logtest prüft, dass weder
  Kachelgrenzen noch Footprints als Koordinaten im Log stehen (§1.2: zuerst
  prüfen, dass Zeilen geloggt wurden).

### 4.8 Tests

Backend (`pytest`, synthetische COGs, kein Netz):

1. Zwei Szenen über eine Szenengrenze (Abnahme): Eine Kachel über der Naht ist
   eine Fläche; links die Werte der einen, rechts die der anderen Szene.
2. Überlappung, zwei UTM-Zonen, verschiedene Konstanten: die gewählte Szene ist
   die des Mosaik-Jobs über dieselbe Liste (`processing.mosaic`), für beide
   Reihenfolgen in der URL; Bytes beider Antworten gleich (S5).
3. Vorfilter: eine dritte Szene weit weg wird nicht geöffnet (Zähler am Reader).
4. Frühes Ende: Eine voll gedeckte Kachel öffnet die zweite Portion nicht.
5. Item-Abrufe: Sechs gleichzeitige Kacheln über dieselben 10 Items holen jedes
   Item genau einmal von der (gedoubelten) Quelle; nie mehr als 4 Abrufe einer
   Anfrage gleichzeitig; ohne Pool `503` für föderierte Datensätze, Einzelkachel
   unverändert `200`.
6. Fehlerfälle: 1 oder 65 Items, doppelte ID (`400`); fehlendes Item (`404`);
   Items zweier Überflüge (`422`); mehr als 12 Szenen in der Kachel (`422`);
   Kachel ohne Szene (`404`); z7 (`400`, ohne Item-Abruf); Zoom außerhalb des
   freigegebenen Bereichs (`400`); Datensatz ohne `viewer` (`501`); unter
   Lizenzstufe `display` (`403`); Asset fehlt in einer Szene (`404`).
7. Zweckfremd: `item` mit Pfadzeichen, Leerzeichen oder einer URL als Wert
   (`400`, auch für einen materialisierten Datensatz, keine Anfrage nach außen);
   `bbox`, `aoi`, `geometry`, `intersects`, `url`, `expression`, `op` (`400`);
   eine Item-ID eines anderen Datensatzes (`404`).
8. Zustandslos: Zwei frisch gebaute Apps liefern für dieselbe URL dieselben
   Bytes.
9. OpenAPI: kein Parameter `url`, `aoi`, `bbox`, `geometry`, `intersects`;
   `test_tiler_start_is_light` bleibt grün (KE4).
10. URL-Länge: eine Mosaik-URL mit 64 IDs zu je 60 Zeichen geht durch den
    `tiler` unter uvicorn (wie im compose-Befehl) ohne `414`/`431`.
11. Logtest wie §4.7.

Frontend (`vitest`): Überflug → ein Layer mit TileJSON-URL und sortierten
`item`; eine Szene → alte URL; unter z8 Einzelszenen in `earthx:order`; über 64
→ Einzelszenen mit Hinweis; AOI-Clip umhüllt die Mosaik-URL.

---

## 5. Grenzen je Kachel, mit Begründung

| Grenze | Wert | Begründung |
|---|---|---|
| Items je URL | **64** | §2.2: Überflüge bis 60 Szenen über einer landesgroßen Fläche [M]; URL bei 64 IDs ≈ 2,4 kB (Sentinel-2) bzw. ≈ 4,3 kB (Zarr), unter 8 kB (§2.7). Kosten an der Quelle: einmal je Item und 24 h mit §4.3 [A]; ≈ 5 s bis zum ersten Bild bei kaltem Cache (§2.8) |
| Szenen je Kachel nach dem Vorfilter | **12** | §2.2: höchstens 9 bei z8 in sechs Überflügen [M]; Reserve für niedrigere Breiten, wo eine z8-Kachel bis 157 km misst und bis zu drei MGRS-Reihen und -Spalten plus Zonenüberlappung fasst [A]; Planetary Computer setzt 10 [P]. Bytes: ≤ 12 × (96 + 32) kB ≈ 1,5 MB bei z8; ab z12 ≤ 8 Szenen [M] × 2 MB = 16 MB im ungünstigsten Fall, mit frühem Ende meist 1–2 Szenen |
| Mindestzoom der Mosaik-Kachel | **8** | Unter z8 berührt eine Kachel bis 13 (z7) bzw. 27 (z6) Szenen [M]; das ist Übersicht, die Aufgabe der Quicklooks und der Coverage Map (`ViewerInfo`: „below `min_zoom` one tile shows several scenes“). Praxis: Mindestzoom je Collection beim Planetary Computer, Rat in titiler #287 [S]. `sentinel-2-l2a-zarr3` beginnt ohnehin bei z8 |
| Parallel gelesene Szenen | **4** je Portion | Frage 5 |
| Gleichzeitige Item-Abrufe je Anfrage | **4** | §4.3: unter Pool (5) und `gateway` (6 je Host) |

Alle fünf als Konstanten im Code, nicht als Registry-Feld (KE6): Sie hängen am
Kachelschema und an der Quelle, nicht am Datensatz; ein Datensatz mit anderen
Szenengrößen bekommt sie, wenn es ihn gibt.

**Gelesene Bytes** lassen sich vor dem Lesen nicht deckeln: GDAL holt die
Bereiche selbst, `gateway` sieht nur die Adresse (B8). Die Byte-Grenze ergibt
sich aus Szenenzahl × Bytes je Szene (§2.3), also aus den Grenzen oben. Ein
eigener Byte-Zähler je Kachel wäre ein GDAL-Logging-Hook im Lesepfad; das
schlage ich nicht vor.

---

## 6. Nicht in dieser Aufgabe

- Zuschnitt und Export sortieren weiter in Auswahlreihenfolge (Frage 2).
- Mosaik mit Operator (`op`) im Kachel-Pfad (Frage 4).
- Die Suche füllt den Item-Cache nicht (§2.8); das zu ändern beträfe jede Suche
  in `adapters` und gehört nicht hierher (Frage 8, Option 3).
- Statistik über ein Mosaik: Der Client misst den Streckbereich wie heute an
  der ersten Szene (`autoStretch`); die Mosaik-Kachel nimmt `rescale` an.
- CDN, `Cache-Control` (M6, `adr/0006` §8 Punkt 3); COG-Header-Cache (Log offen).
- Mosaik über mehrere Tage oder Überflüge (Zeitreihe, nicht Mosaik).

---

## 7. Fragen an Otto

**Frage 1 — Verfahren und ADR**
1. **O1, Item-Liste in der URL, wie `adr/0006` §5 schon entschieden; kein
   `adr/0017`, sondern ein Nachtrag in `adr/0006` (Grenzen aus §5, Reihenfolge
   aus §4.4, Item-Abrufe aus §4.3) und die seit dem 20.09.2026 fällige
   Berichtigung von `architekturplan.md` 6.3 (Empfehlung).**
2. O2, Such-ID mit Postgres-Cache nach 6.3; dann schreibe ich `adr/0017`
   (Stufe C) und halte an, weil es `adr/0006` umkehrt.
3. O3, Hash der Liste als ID mit Cache und Neu-Registrieren im Client.

**Frage 2 — Reihenfolge der Szenen (S5)**

S5 verlangt dieselbe Regel wie Export-Job **und** Mosaik-Job; heute sortieren
die beiden verschieden (§2.1). Keine Option erfüllt S5 ganz, ohne den
Zuschnitt zu ändern.
1. **Wie der Mosaik-Job: Der Server sortiert nach `mosaic_order`, die
   Reihenfolge in der URL zählt nicht (Empfehlung).** Folgen: Die Karte stimmt
   an Überlappungen mit dem Mosaik-Job überein, aber nicht mehr mit Zuschnitt
   und Export — der Abgleich aus M3-09 („Ansicht = Download“) geht für
   Überlappungen verloren. Dass alle vier gleich sortieren, schlage ich als
   eigene kleine Aufgabe vor (offene Log-Zeile).
2. Wie Zuschnitt und Export: Die Reihenfolge der URL gilt (Auswahl). Die Karte
   bleibt gleich wie der Zuschnitt, aber verschieden vom Mosaik-Job; zwei
   Reihenfolgen derselben Szenen sind zwei Bilder und zwei Cache-Einträge.
3. Wie 1, und Zuschnitt und Export sortieren in dieser Aufgabe mit. Erfüllt S5
   ganz; größerer PR, ändert das Ergebnis des Zuschnitts an Überlappungen.

**Frage 3 — Was die Karte jenseits der Grenzen zeigt**
1. **Unter z8 die Einzelszenen, gestapelt nach `earthx:order` (gleiche Szene
   oben wie im Mosaik); über 64 Szenen die Einzelszenen wie heute mit neuem
   Hinweis (Empfehlung).**
2. Unter z8 nichts (die Quicklooks der Trefferansicht bleiben), über 64 die
   ersten 64 in Mosaik-Reihenfolge mit Hinweis.
3. Grenzen anders setzen (bitte Werte nennen).

**Frage 4 — Mosaik mit Operator (Vorschau eines Mosaik-Jobs)**
1. **Nicht in M4-17. Die Vorschau bleibt je Szene; dass sie an Überlappungen
   anders wählen kann als der Job (§2.1), kommt als offene Log-Zeile und eigene
   Aufgabe nach M4-17 (Empfehlung).** Grund: Der Job mischt zuerst die Bänder
   und rechnet dann; eine Kachel müsste das genauso tun (Mosaik je Asset, dann
   der Operator), das ist ein Umbau von `processing/tile.py` und etwa
   300 Zeilen mehr. `op` auf der Mosaik-Route ist bis dahin `400`.
2. In M4-17, als weiterer PR.

**Frage 5 — Parallel gelesene Szenen je Portion**
1. **4: höchstens vier Szenen gleichzeitig, danach Prüfung auf „voll“
   (Empfehlung).**
2. 1 wie der Zuschnitt: am wenigsten Bytes, aber bei 9 Szenen kalt rund 9 s.
3. Alle Szenen der Kachel gleichzeitig (rio-tiler-Vorgabe): am schnellsten,
   liest immer alle.

**Frage 6 — Schnitt (Richtwert 400 Zeilen)**
Schätzung: `access` etwa 120 Zeilen und 160 Tests; `api` etwa 220 und 260
Tests; Frontend etwa 150 und 120 Tests; Doku etwa 80.
1. **Drei PRs: M4-17a `access` (Fabrik, Lesen, Verschieben der Reihenfolge,
   KE4; etwa 300) in dieser Session; M4-17b `api` (Routen, Prüfungen,
   Item-Abrufe, Doku; etwa 560, darüber wegen der Fehlerfälle); M4-17c Frontend
   (etwa 270). b und c je in einer neuen Session nach dem Merge des
   Vorgängers (Empfehlung).**
2. Zwei PRs: Backend (etwa 840) und Frontend (etwa 270).
3. Ein PR mit etwa 1100 Zeilen.

**Frage 7 — Grenzen aus §5**
1. **64 Items je URL, 12 Szenen je Kachel, ab z8 (Empfehlung).**
2. 25 Items je URL wie `adr/0006`; die gemessenen Überflüge über landesgroßen
   Flächen fallen dann auf Einzelszenen zurück.
3. 10 Szenen je Kachel wie der Planetary Computer; an Zonengrenzen bei z8 dann
   selten `422`.

**Frage 8 — Item-Abrufe und Ausfall des Caches (§2.8, §4.3)**
1. **Zusammenlegen, Drosseln auf 4, Vorwärmen über das TileJSON; ohne Pool
   `503` für föderierte Mosaike, Einzelkacheln unverändert (Empfehlung).**
2. Wie 1, aber ohne Pool rendern wie sonst auch (E5 wörtlich): dann holt jede
   Mosaik-Kachel bis zu 64 Items von der Quelle.
3. Wie 1, und zusätzlich schreibt jede Suche in `adapters` ihre Items in den
   Item-Cache (warm, bevor der Nutzer die Karte öffnet; ändert alle Suchen und
   den Speicherbedarf in Postgres, etwa 17 kB je gefundenem Item für 24 h).

**Kleinentscheidungen** (gelten, sofern du nicht widersprichst):
- **KE1:** Zarr-Szenen in zwei CRS sind in der Mosaik-Kachel erlaubt (§4.5).
- **KE2:** Der Vorfilter nimmt den Footprint (`geometry`), nicht nur die `bbox`.
- **KE3:** Mehr als 12 Szenen in einer Kachel ist `422` mit „zoom in“, kein
  Teilbild.
- **KE4:** `target_crs` und `mosaic_order` ziehen unverändert von
  `processing/mosaic.py` nach `access/crop_rules.py`, neben `merge_first_valid`;
  `processing.mosaic` und `api.intake` importieren sie von dort. Die Regel
  liegt dann an einer Stelle, und der `tiler` muss für eine Mosaik-Kachel den
  Worker-Kern nicht laden (§2.4). Gegenvorschlag: verzögerter Import aus
  `processing` wie `_operator_support`; dann lädt die erste Mosaik-Kachel den
  ganzen Kern.
- **KE5:** Der Client sortiert die `item` nach ID (Cache); der Server nimmt
  jede Reihenfolge an.
- **KE6:** Routenform `/collections/{dataset}/mosaic/…`, `item` wiederholt
  (nicht `items=` mit Kommas wie in `adr/0006` §3.5, damit es zu `asset`
  passt), Grenzen als Konstanten im Code.
- **KE7:** Keine Prüfung der Capability `reprojection` an der Mosaik-Kachel
  (§4.2).
- **KE8:** Der Docstring von `ViewerInfo` und `architekturplan.md` 6.3 werden
  nachgezogen (§2.6).

---

## 8. Umsetzung nach Freigabe

Annahme: die Empfehlungen. Bei anderen Antworten passe ich den Plan vor dem
Code an.

**M4-17a (`access`):** KE4 als eigener Commit (reines Verschieben, Tests von
M4-12 grün); dann die Mosaik-Fabrik mit Lesen in Portionen, Tests 1, 3, 4, 8
auf einer nackten App.

**M4-17b (`api`):** Pfad-Abhängigkeit (Prüfungen, Überflug, Vorfilter,
Reihenfolge), Item-Abrufe (§4.3), Routen, TileJSON mit `earthx:order`; Tests 2,
5–7, 9–11; Doku (Docstring `ViewerInfo`, §3 des M4-Plans, Log). Nachtrag
`adr/0006` und `architekturplan.md` 6.3 kommen nach Auflage 1 (§11) schon mit
M4-17a.

**M4-17c (Frontend):** Layer je Überflug über das TileJSON, Rückfall, Hinweis,
`vitest`; Prüfanleitung B.

---

## 9. Prüfanleitung für Otto (PowerShell 5.1)

Entwurf; die Antwortform ist in M4-17b nur zum Teil gegen einen laufenden
`tiler` geprüft (Stand in §14, „Prüfanleitung A“).

**A — Backend (nach M4-17b).** Sucht einen Überflug über zwei Zonen
(Zonengrenze bei 12° O), wählt zwei Szenen verschiedener Zonen, deren Rahmen
sich überlappen, und holt eine Kachel in der Mitte der Überlappung — einmal mit
den Items in der einen, einmal in der umgekehrten Reihenfolge. Das
Suchrechteck ist eine Messfläche, keine AOI.

```powershell
docker compose up -d --build
$api = 'http://localhost:8000'; $tiler = 'http://localhost:8001'

$search = @{ collections = @('sentinel-2-c1-l2a'); bbox = @(10.5, 47.0, 13.5, 48.5)
             datetime = '2025-07-01T00:00:00Z/2025-07-31T23:59:59Z'; limit = 100 } | ConvertTo-Json -Depth 10
$items = (Invoke-RestMethod -Method Post -Uri "${api}/stac/search" `
          -ContentType application/json -Body $search).features
function Get-Epsg($feature) {
    $p = $feature.properties
    if ($p.'proj:epsg') { return [int]$p.'proj:epsg' }
    return [int](([string]$p.'proj:code') -replace 'EPSG:', '')
}
$pass = $items | Group-Object { $_.properties.'s2:datatake_id' } |
        Where-Object { @($_.Group | ForEach-Object { Get-Epsg $_ } | Select-Object -Unique).Count -ge 2 } |
        Select-Object -First 1
$scenes = @($pass.Group)
'{0} Szenen im Überflug' -f $scenes.Count

# zwei Szenen verschiedener Zonen mit überlappendem Rahmen; Mitte der Überlappung
$pair = $null
foreach ($a in $scenes) { foreach ($b in $scenes) {
    if ($pair -or (Get-Epsg $a) -ge (Get-Epsg $b)) { continue }
    $west = [Math]::Max($a.bbox[0], $b.bbox[0]); $south = [Math]::Max($a.bbox[1], $b.bbox[1])
    $east = [Math]::Min($a.bbox[2], $b.bbox[2]); $north = [Math]::Min($a.bbox[3], $b.bbox[3])
    if ($west -lt $east -and $south -lt $north) { $pair = @($a, $b); $lon = ($west + $east) / 2; $lat = ($south + $north) / 2 }
} }
$ids = @($scenes | ForEach-Object { $_.id } | Sort-Object)

function Get-TileXY($lon, $lat, $z) {
    $n = [Math]::Pow(2, $z); $r = $lat * [Math]::PI / 180
    @([Math]::Floor(($lon + 180) / 360 * $n),
      [Math]::Floor((1 - [Math]::Log([Math]::Tan($r) + 1 / [Math]::Cos($r)) / [Math]::PI) / 2 * $n))
}
function Get-MosaicTile($list, $z, $extra, $file) {
    $xy = Get-TileXY $lon $lat $z
    $q = (($list | ForEach-Object { 'item=' + $_ }) -join '&') + '&asset=visual' + $extra
    $uri = "${tiler}/collections/sentinel-2-c1-l2a/mosaic/tiles/WebMercatorQuad/${z}/$($xy[0])/$($xy[1]).png?${q}"
    try { Invoke-WebRequest -UseBasicParsing -OutFile $file -Uri $uri | Out-Null; 200 }
    catch { $_.Exception.Response.StatusCode.value__ }
}

Get-MosaicTile $ids 10 '' 'mosaic.png'                          # 200
$reversed = @($ids); [Array]::Reverse($reversed)
Get-MosaicTile $reversed 10 '' 'mosaic-reverse.png'             # 200
(Get-FileHash mosaic.png).Hash -eq (Get-FileHash mosaic-reverse.png).Hash   # True: Reihenfolge egal
Start-Process mosaic.png                                        # eine Fläche über der Naht

# Gegenproben
Get-MosaicTile $ids 7 '' 'z7.png'                               # 400: Mosaik erst ab z8
Get-MosaicTile $ids 10 '&bbox=1,2,3,4' 'bbox.png'               # 400: keine Fläche in der URL
$other = ($items | Where-Object { $_.properties.'s2:datatake_id' -ne $pass.Name } | Select-Object -First 1).id
Get-MosaicTile ($ids + $other) 10 '' 'two-passes.png'           # 422: zwei Überflüge
```

**B — im Viewer (nach M4-17c).** Einen Überflug über zwei Kacheln in voller
Auflösung öffnen: Die Szenen erscheinen als eine Fläche, im Layer-Manager ein
Eintrag; die Netzwerkansicht des Browsers zeigt je Kartenkachel **eine**
Anfrage an `…/mosaic/tiles/…` statt einer je Szene, und keine URL enthält
Koordinaten der AOI. Beim Herauszoomen unter z8 bleibt an Überlappungen
dieselbe Szene oben.

---

## 10. Messanhang

### 10.1 Szenen je Kachel (§2.2)
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

### 10.2 Selbst gelesene Quellen (§2.7)

Je eine Anfrage per `curl`, 1,2 s Abstand:

```bash
curl -sS https://raw.githubusercontent.com/microsoft/planetary-computer-apis/main/pctiler/pctiler/config.py
#   default_max_items_per_tile: int = Field(default=10, …)
curl -sS https://raw.githubusercontent.com/stac-utils/titiler-pgstac/main/titiler/pgstac/settings.py
#   scan_limit: int = 10000 / items_limit: int = 100 / time_limit: int = 5
#   exitwhenfull: bool = True / skipcovered: bool = True
curl -sS https://raw.githubusercontent.com/stac-utils/pgstac/main/src/pgstac/sql/004_search.sql
#   CREATE TABLE IF NOT EXISTS searches(hash text PRIMARY KEY, search jsonb NOT NULL, …,
#     lastused timestamptz DEFAULT now(), usecount bigint DEFAULT 0, …)
#   pgstac_hash: encode(sha256(…), 'hex'); kein DELETE FROM searches
curl -sS https://raw.githubusercontent.com/encode/uvicorn/master/docs/settings.md
#   --h11-max-incomplete-event-size … Default: 16384 (16 KB)
curl -sS https://raw.githubusercontent.com/nginx/nginx.org/master/xml/en/docs/http/ngx_http_core_module.xml
#   large_client_header_buffers … default 4 8k; 414 Request-URI Too Large
```

---

## 11. Freigabe (Otto, 20.10.2026)

Fragen 1–8 je Option 1, KE1–KE8 angenommen. Auflagen:

1. Die Berichtigung von `architekturplan.md` 6.3 (Item-Liste in der URL statt
   Such-ID) und der Nachtrag in `adr/0006` kommen im **ersten** PR (M4-17a),
   nicht erst mit den Routen.
2. **KE4:** Die Sortierfunktionen ziehen unverändert um; ein Test zeigt, dass
   Mosaik-Job und Export danach bytegleich rechnen.
3. **Frage 8:** Ohne Item-Cache antwortet die Mosaik-Kachel mit klarer Meldung
   und Grund, **nie mit `500`**; die Abrufe bei der Quelle bleiben in den
   Grenzen je Host aus `gateway`, mit Test. Gilt für M4-17b.

Frage 2 (Zuschnitt und Export sortieren wie der Mosaik-Job) und Frage 4
(Mosaik mit Operator) sind als offene Punkte nach M4 vorgemerkt, je eine
Log-Zeile „offen, nach M4“.

---

## 12. Umsetzung M4-17a (20.10.2026)

**Umfang wie §8, Frage 6 Option 1:** nur `access` und die Doku-Auflage; noch
keine Route im `tiler`, das Frontend unverändert.

- **Vergleichstest vor dem Umzug** (Auflage 2):
  `TestTheRuleOfTheExport.test_both_compute_the_same_bytes_as_before_the_order_moved`
  in `tests/earthx/processing/test_mosaic.py`. SHA-256 über CRS, Transformation,
  Werte und Maske des Mosaik-Jobs und des Exports, die Liste aus `mosaic_order`
  für beide Reihenfolgen der Eingabe; die Werte sind auf dem Code **vor** dem
  Umzug aufgenommen (eigener Commit) und gelten danach unverändert [M].
  Bytegleich heißt hier: gleiche Daten und Maske je Ausgabe; die Datei selbst
  wird nicht verglichen, weil ihre Metadaten mit der GDAL-Version wechseln
  können [A].
- **KE4:** `target_crs`, `mosaic_order` (samt `_epsg`, `_NO_EPSG`) Zeile für
  Zeile nach `access/crop_rules.py`; `processing/mosaic.py` und `api/intake.py`
  verweisen dorthin. `test_tiler_start_is_light` bleibt grün.
- **`access/mosaic_tiles.py` (neu):**
  - `MosaicScenes` — die Szenen einer Kachel in Lesereihenfolge und die Lage
    aller Szenen der URL; nimmt nur `AssetPath`/`ZarrAsset` (B8).
  - `MosaicTileReader` — `tile` über `mosaic_reader` mit `FirstMethod`, in
    Portionen von `MOSAIC_THREADS = 4` (Frage 5), `TileOutsideBounds` je Szene
    erlaubt, keine Szene in der Kachel → `TileOutsideBounds` (`404` im
    `tiler`); `get_geographic_bounds` aus `MosaicScenes.bounds`; `info` der
    ersten Szene.
  - `EarthxMosaicTilerFactory` — nur `tile` und `tilejson` von
    `EarthxTilerFactory` (dieselbe Zoomprüfung des TileJSON).
- **Befund bei der Umsetzung [M], berichtigt nach dem Review:** Die Lese-Threads
  von `mosaic_reader` sehen die Konfiguration der Route nicht. Die Route läuft im
  Threadpool von Starlette, und dort setzt rasterio 1.5.2 die Optionen nur für
  den eigenen Thread (`CPLSetThreadLocalConfigOption`, `rasterio/_env.pyx`);
  ohne erneutes `rasterio.Env` fehlten in den Lese-Threads also auch die
  GDAL-Optionen aus `gateway.gdal_options` (Timeouts, erlaubte Endungen u. a.,
  B8). Die Umgebung des Threads zu kopieren scheitert, sobald sie AWS-Optionen
  enthält („GDAL's AWS config options can not be directly set“). Deshalb reicht
  die Fabrik dem Reader genau die `environment_dependency` der Route weiter
  (`MosaicReaderParams`), und jede Szene wird unter `rasterio.Env(**gdal_config)`
  gelesen. Ein Test prüft in den Lese-Threads beides: rasterios Env und GDAL
  selbst (`get_gdal_config`). Eine übergebene `reader_dependency` lehnt die
  Fabrik ab, weil sie diese Weitergabe ersetzen würde.
- **Tests** (`tests/earthx/access/test_mosaic_tiles.py`, synthetische Szenen
  von Zone 32, kein Netz): Naht ohne Lücke (§4.8 Test 1); Überlappung nach
  Listenreihenfolge; Szene außerhalb der Kachel stört nicht, keine Szene →
  `404`; frühes Ende nach der ersten Portion und Füllen aus der zweiten
  (Test 4); GDAL-Konfiguration in jedem Lese-Thread; nur zwei Routen, kein
  Parameter `url`/`aoi`/`bbox`/`geometry`/`intersects` (Test 9, Teil);
  TileJSON mit Lage aller Szenen und freigegebenen Stufen; zwei frische Apps,
  gleiche Bytes (Test 8); `MosaicScenes` und Reader weisen anderes ab. Nach
  dem Review dazu: Eine unlesbare Szene lässt die Kachel scheitern, statt eine
  andere gewinnen zu lassen; ein Mosaik aus zwei Zarr-Szenen (KE1); der
  Leichtstart-Test prüft, dass `access.mosaic_tiles` und `access.crop_rules`
  den Worker-Kern nicht laden (KE4).
- **Grenzen des Vergleichstests:** Er vergleicht Daten und Maske, nicht die
  Datei, und beide Reihenfolgen der Eingabe liegen in Zone 32; die
  CRS-Vorrangregel von `target_crs` decken die Einheitstests in
  `test_mosaic.py` (`TestTheOrderOfAnOverpass`) ab. Ein Wechsel von GDAL oder
  PROJ kann die Prüfsummen ändern, ohne dass sich fachlich etwas ändert; dann
  sind sie neu aufzunehmen, mit Begründung im PR.
  Test 3 (Vorfilter) gehört zur Pfad-Abhängigkeit und kommt mit M4-17b.
- **Doku:** `architekturplan.md` 6.3 berichtigt, Nachtrag in `adr/0006` §5
  („Zu Frage 4“), Folge 1 dort als erledigt markiert; Log-Zeilen (Freigabe,
  zwei offene Punkte nach M4, Umsetzung).

---

## 13. Folgesessions

**M4-17b — `api`: Routen, Prüfungen, Item-Abrufe.** Neue Session nach dem
Merge von M4-17a. *Umgesetzt, siehe §14.*
**Startsatz:** „Führe Aufgabe M4-17b aus `docs/plans/m4-processing-kern.md`
aus.“ Grundlage ist dieser Plan: §4.1–§4.4, §4.7, §4.8 (Tests 2, 3, 5–7, 9–11),
§5, §11 Auflage 3, KE5–KE8.
- Pfad-Abhängigkeit in `api/tiler.py` nach §4.2 (z8 vor jedem Item-Abruf,
  abgewiesene Parameter, `ITEM_ID`-Regel, ein Überflug, CRS aller Items,
  Vorfilter über den Footprint, `mosaic_order` aus `access/crop_rules.py`),
  liefert `MosaicScenes` an die Fabrik aus M4-17a; Routen unter
  `/collections/{dataset}/mosaic`.
- Item-Abrufe nach §4.3: zusammengelegt im Prozess, höchstens 4 je Anfrage,
  TileJSON wärmt vor und trägt `earthx:order`; ohne Item-Cache für föderierte
  Datensätze eine klare Meldung mit Grund (`503`), **nie `500`**, mit Test;
  ein Test zeigt, dass gleichzeitige Kacheln die Grenze je Host aus `gateway`
  (`max_connections_per_host`) bei der Quelle nicht überschreiten.
- Gebündelte Cache-Abfrage nur, wenn 64 Lookups je Kachel lokal über 50 ms
  liegen (§4.3 Punkt 5); Messung im PR.
- Docstring von `ViewerInfo` nachziehen (KE8); Prüfanleitung A (§9) gegen den
  laufenden `tiler` prüfen und eintragen.
- Aus dem Review von M4-17a, für die Fabrik im `tiler`: eine eigene
  `path_dependency` setzen (die Vorgabe von TiTiler führt `url`); als
  `layer_dependency` `BidxParams` wie die Einzelkachel, damit `expression` nicht
  durchgeht (§4.8 Test 7); verschiedene Bandzahlen der Szenen enden in
  rio-tiler mit `AssertionError` — vorher prüfen und mit Grund ablehnen, nie
  `500`; eine eingebettete Farbtabelle einer Szene trägt der Mosaik-Reader
  nicht (`colormap`), heute folgenlos, weil die Registry nur `colormap_name`
  setzt.

**M4-17c — Frontend.** Neue Session nach dem Merge von M4-17b.
**Startsatz:** „Führe Aufgabe M4-17c aus `docs/plans/m4-processing-kern.md`
aus.“ Grundlage: §4.6, §4.8 (Frontend), §7 Frage 3, §9 B.
- Ein Layer je Überflug als MapLibre-Quelle mit `url` auf das Mosaik-TileJSON,
  `item` nach ID sortiert (KE5); eine Szene bleibt bei der heutigen URL.
- Unter z8 die Einzelszenen in `earthx:order`; über 64 Szenen Einzelszenen wie
  heute mit neuem Hinweis; AOI-Clip unverändert.
- `vitest`, `npm run lint`, `npm run build`; Prüfanleitung B.

---

## 14. Umsetzung M4-17b (20.10.2026)

**Umfang wie §13:** die Mosaik-Routen im `tiler` mit Pfad-Abhängigkeit, Item-Abrufen und TileJSON;
das Frontend bleibt unverändert (M4-17c).

- **Aufbau.** `api/mosaic_tiles.py` hält, was weder die Anfrage noch die HTTP-Abbildung braucht:
  die Grenzen aus §5 als Konstanten, die Form der Abfrage (`check_query`), die Kachel (`mosaic_tile`,
  z8 vor jedem Abruf), die Item-Abrufe (`ItemFetches`, `fetch_items`), den Überflug
  (`check_one_overpass`) und die Footprints (`footprints_of`, `scenes_touching`). `api/tiler.py`
  verdrahtet das in `mosaic_scenes` (Reihenfolge der Schritte wie §4.2) und bildet jede Abweisung auf
  ihren Status ab. In `access` kamen der Haken `tilejson_extras` (für `earthx:order`) und die
  Fehlerklasse `MosaicBandsDiffer` dazu.
- **Item-Abrufe.** Gleichzeitige Abrufe desselben Items teilen sich einen Abruf; der Eintrag fällt mit
  dem Ende des Abrufs weg. Eine Anfrage, die aufgibt, bricht den Abruf der anderen nicht ab
  (`asyncio.shield`). Der TileJSON-Abruf holt alle Items einmal und füllt damit den 24-h-Cache.
- **Aus dem Review von M4-17a erledigt.** Eigene `path_dependency` ohne `url`; `BidxParams` als
  `layer_dependency`, `process_dependency` leer (sonst stünden `algorithm` und `algorithm_params` im
  Schema); verschiedene Bandzahlen der Szenen enden mit `422` und Grund statt im `assert` von
  rio-tiler.

**Abweichungen vom Plan und Auslegungen** (gelten, sofern Otto nicht widerspricht; Log vom 20.10.2026):

1. **Die Grenze von 4 Abrufen gilt im ganzen Prozess, nicht je Anfrage.** Je Anfrage hätten sechs
   Kacheln mit verschiedenen Items bis zu 24 Abrufe gestartet, mehr als der Pool (5) fasst; „höchstens
   4 je Anfrage“ folgt aus der Prozessgrenze. Der Preis: Zwei kalte Überflüge warten aufeinander.
2. **Ohne Pool `503` für jeden Datensatz**, auch den materialisierten (§4.3 Punkt 4 nannte nur die
   föderierten): Dessen Item-Quelle ist ohnehin der Pool. Ein Pool, der Fehler gibt
   (auch ein Pool-Timeout), ist ebenfalls `503`, Meldung „mosaic
   tiles need the item cache, and it is not reachable“. Jeder andere Fehler bleibt sichtbar.
3. **Datensatz mit `max_zoom` unter z8:** `400` vor jedem Abruf. Heute trifft das keinen Eintrag (S2
   0–19, Zarr 8–14, DEM 0–15).
4. **Bandzahl:** Die Prüfung vergleicht die Szenen, die die Kachel liest. Füllt die erste Portion die
   Kachel, werden die übrigen weder gelesen noch verglichen.
5. **Erlaubt sind nur die Parameter, die die Route erklärt** (Positivliste aus ihrer Abhängigkeit),
   nicht eine Sperrliste: Jeder andere Name ist `400`, auch `filter`, `bbox ` oder `URL`. Sonst hätte
   das TileJSON einen Flächenparameter in die Kachel-URLs kopiert.
6. **Das TileJSON-`bounds` kommt aus den Footprints** (bei fehlender `geometry` aus der `bbox`), nicht
   aus der `bbox` allein wie in §4.1; fachlich gleich. Ein Item mit leerer oder nicht endlicher
   Geometrie ist `502`.
7. **Jeder Fehler der Datenbank** (`psycopg.Error`, auch eine fehlende Cache-Tabelle) ist `503`; das Log
   nennt nur die Art des Fehlers, nie den Text des Treibers.
8. **Fehlermeldungen** nennen nie den Wert, der abgewiesen wurde (eine ungültige Item-ID kommt nicht
   zurück); nur die Zahl der Items und die ersten IDs eines Überflug-Konflikts.

**Gebündelte Cache-Abfrage (§4.3 Punkt 5): nicht gebaut.** Gemessen [M]: lokale Postgres 16, Pool
mit 5 Verbindungen, 64 Treffer von rund 16,8 kB, alle über `ItemFetches` (4 gleichzeitig), acht
Durchläufe: Median **42 ms** je Kachel, größter Wert 56 ms, der erste Durchlauf mit kaltem Pool
88 ms. Die Schwelle von 50 ms (§4.3) wird im Mittel nicht erreicht. Die Messung gilt für eine
Datenbank im selben Rechner; mit der Datenbank im Netz wächst jeder der 64 Abrufe um die Umlaufzeit,
dann ist die Frage neu zu stellen (M6).

**Tests** (`tests/earthx/api/test_tiler_mosaic.py`, `test_mosaic_item_fetches.py`; kein Netz):

- Plan-Test 1 und 8 auf der echten App: Naht ohne Lücke, gleiche Bytes bei umgekehrter URL-Reihenfolge,
  zwei frische Apps.
- Plan-Test 2: Die gewählte Szene an fünf Stellen über zwei UTM-Zonen ist die des Mosaik-Jobs
  (`processing.run` über dieselbe Liste, dieselben Szenen wie `test_mosaic.py`), für beide
  Reihenfolgen der URL; dazu ein Test, in dem die Szene der Nachbarzone die kleinste ID hat und
  trotzdem nicht gewinnt. Gegenprobe: Mit `sorted(ids)` statt `mosaic_order` scheitern dieser Test und der der TileJSON-Reihenfolge.
- Plan-Test 3 und 4: Szene weit weg wird weder freigegeben noch geöffnet; eine Kachel, die die erste
  Portion füllt, öffnet genau vier Szenen.
- Plan-Test 5: Sechs gleichzeitige Kacheln über dieselben zehn Items holen jedes Item genau einmal,
  nie mehr als vier gleichzeitig; mit dem echten `Gateway` auf einem Transport-Double halten sechs
  Kacheln über 48 verschiedene Items die Verbindungen bei höchstens vier (Grenze des `gateway`: 6).
  Ohne Pool `503`, die Einzelkachel bleibt `200`; ein Pool-Fehler ist `503`.
- Plan-Test 6 und 7: alle Fehlerfälle der Liste in §4.8, dazu jeder abgewiesene Parameter einzeln
  (auch in Großschreibung), ungültige Item-IDs für einen föderierten und einen materialisierten
  Datensatz.
- Plan-Test 9: Das Schema der Mosaik-Routen kennt weder `url` noch `aoi`, `bbox`, `geometry`,
  `intersects`, `expression`, `algorithm`, `op`, `params`; es gibt genau drei Pfade.
- Plan-Test 10: Eine Anfrage mit 64 IDs zu je 60 Zeichen (über 4 kB) geht unter uvicorn mit
  Vorgaben — wie `docker-compose.yml` ihn startet — mit `200` durch. Gesendet per Socket, weil die
  Sperre der Testsuite jede Namensauflösung verbietet, auch die von `127.0.0.1`.
- Plan-Test 11: Das Log nennt die Zahl der gelesenen Szenen und keine Koordinate der Footprints oder
  der Kachel (zuerst geprüft, dass Zeilen geloggt wurden).

**Prüfanleitung A: nur zum Teil geprüft.** PowerShell fehlt in der Sitzung, deshalb habe ich den
Ablauf in Python nachgebaut und gegen einen lokalen `tiler` (uvicorn, lokale Postgres) laufen
lassen; die Suche ging direkt an Earth Search, weil der `api`-Prozess ohne Objektspeicher
(`S3_ENDPOINT`) nicht startet.

- Beobachtet [M]: z7 → `400`; `bbox` in der URL → `400`; Item nicht abrufbar → `502`, nicht `500`.
- **Nicht belegt:** `200` mit einer Fläche über der Naht, gleiche Datei bei umgekehrter
  Reihenfolge, `422` bei zwei Überflügen, das TileJSON gegen die echte Quelle. Grund: Der Abruf der
  Items scheitert im `gateway` der Sitzung. Er verbindet sich mit der aufgelösten IP, und der
  Egress-Proxy der Sitzung lehnt `CONNECT` auf eine IP mit `403` ab (`connect_rejected`); ein einfacher `httpx`-Abruf derselben Adresse über den Namen ist `200`.
  Das liegt an der Sitzung, nicht an M4-17b. Was fehlt: ein Lauf von `tiler` und Prüfskript dort, wo
  das `gateway` die Quelle erreicht (Ottos Rechner mit `docker compose`, wie in §9 beschrieben).

