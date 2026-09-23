# ADR 0006 — Kachel-Pfad: Kacheln, Statistik und Quicklooks

- **Status:** **Angenommen.** Von Otto am 20.09.2026 entschieden; die sieben
  Fragen aus §7 sind dort beantwortet. Die Umsetzung liegt bei M2-04 und M2-06.
- **Datum:** 2026-09-20
- **Aufgabe:** M2-02 laut `docs/plans/m2-format-und-viewer.md` §4.
- **Autonomiestufe:** C — nur recherchiert, gemessen und berichtet. Kein
  Produktivcode geändert, keine Datei außerhalb von `docs/` angefasst, nichts
  installiert, was im Repo landet.
- **Grundlage:** `ENTSCHEIDUNGEN_2026-09-18.md` §2 (F9, F10, F11, Layer-Manager,
  Darstellungssteuerung), §3; `KLAERUNGEN.md` B8, B9, B10, B13;
  `architekturplan.md` 3.1, 3.2, 6.2, **6.3**, 6.4, 6.5, 12.3, 13, 15.2;
  `adr/0001` Z4, Z8, FZ4, FZ7; `adr/0003` §10.1; `adr/0004` (Belegstufen, §3.4);
  `adr/0005` Regel IV; `prototyp-inventar.md` F6, F9, F10, F11, F14, F15, F18;
  `projektuebersicht.md` Prinzip 10; Entscheidungslog-Zeile „Rahmen des
  TiTiler-Spikes" vom 2026-09-20 (D5).
- **Betroffen:** `architekturplan.md` 6.3, 6.5, 12.3; `cloud-umgebung.md` §6
  (Berichtigung, §3.7); `.importlinter`; `backend/requirements.txt`;
  `docker-compose.yml`; Registry (`earthx/catalog/registry.py`, `datasets.py`);
  Planung M2-04, M2-06, M2-07b, M2-09.

---

## Methode und Belegstufen

Gearbeitet wurde in einer Cloud-Sitzung vom 20.09.2026. Erreichbar waren
`earth-search.aws.element84.com`, **beide** infrage kommenden Asset-Buckets
(§3.7) und `pypi.org`.

Jede Aussage trägt eine Belegstufe, wie in `adr/0004`:

- **M** — in dieser Sitzung selbst gemessen; der Befehl steht in §10.
- **P** — am Primärdokument gelesen (Quelltext des Pakets, Paketmetadaten).
- **S** — Suchtreffer mit Link, Primärdokument nicht gelesen.
- **A** — eigene Ableitung aus M/P/S; als Argument gekennzeichnet, nicht als Beleg.

Wo ein Beleg fehlt, steht „unbelegt" statt einer Zahl. §8 listet, was offen blieb.

**Umfang der Live-Zugriffe.** Rund 15 STAC-Metadaten-Anfragen und rund 40
Kachel- bzw. Zuschnitt-Lesevorgänge gegen einzelne, öffentlich lesbare COGs
derselben Szene — zusammen unter 60 MB, über etwa 40 Minuten. Das entspricht
dem für Spikes vorgesehenen kleinen Umfang (`m1-fundament.md` §6,
`m2-format-und-viewer.md` §4 M2-02). Nichts wurde auf Platte geschrieben;
`titiler.core` wurde für §3.1 in ein Wegwerfverzeichnis außerhalb des Repos
installiert, nicht in das venv des Projekts und nicht in `requirements.txt`.

---

## 1. Kontext und Problem

`ENTSCHEIDUNGEN` §2 will drei Funktionen des Prototyps auf token-freie Daten
übertragen: die zweistufige Anzeige (F10), den AOI-Zuschnitt über partielle
COG-Reads (F9) und das Stitching mehrerer Szenen (F11); dazu die Quicklooks
(F6) und die Darstellungssteuerung mit „Apply" (F18). `architekturplan.md` 6.3
gibt die Richtung vor: Die neuen Endpunkte sollen auf den **TiTiler-Fabriken**
entstehen statt selbst gebaut zu werden, Kachel-URLs sollen alle Parameter
tragen und damit CDN-fähig sein, und die GDAL-Konfiguration für Fernzugriffe
soll zentral gesetzt werden.

Vier Dinge stehen dem im Weg, und sie sind der Grund für diesen Spike:

1. **TiTiler ist als offener Tiler gebaut.** Seine Fabriken nehmen von außen
   eine freie Dataset-URL entgegen. Genau das darf es bei uns nicht geben:
   `KLAERUNGEN.md` B8 macht `gateway` zur einzigen Stelle, die entscheidet, ob
   eine Adresse abgerufen werden darf, und ein offener `url`-Parameter wäre ein
   SSRF-Loch mit Ansage.
2. **GDAL holt selbst.** `gateway` kann rasterio/GDAL keinen Socket abnehmen
   (B8 sagt das ausdrücklich, die netzseitige Durchsetzung kommt erst mit M6).
   Was bleibt, ist die Zusage: jede Adresse hat vorher `check_url` passiert.
   Diese Zusage muss der Kachel-Pfad einlösen, nicht bloß versprechen.
3. **Der Streckbereich (Z4) ist heute Zustand im Prozess.** `adr/0001` hat ihn
   als den Zustand benannt, der zuerst in die URL gehört: sonst liefert dieselbe
   Kachel-URL hinter zwei Instanzen zwei verschiedene Bilder, und ein CDN friert
   die Mischung ein.
4. **Ein Mosaik ist im Prototyp ein geschriebener COG.** In der Zielarchitektur
   darf der Tiler nichts schreiben (3.2: „keiner" Zustand). Ob ein Mosaik ohne
   Schreiben überhaupt trägt, ist offen — und D5 hängt die Entscheidung über
   das Stitching in M2 ausdrücklich an diesen Spike.

## 2. Kriterien

| # | Kriterium | Herkunft |
|---|---|---|
| K1 | Kein Endpunkt nimmt eine freie Adresse entgegen | B8; D5 Punkt 1 |
| K2 | Jede Adresse passiert `check_url`, bevor GDAL sie sieht | B8; `gateway/gdal.py` |
| K3 | Die Kachel-URL bestimmt das Bild vollständig | `adr/0001` Z4, FZ4; D5 Punkt 2 |
| K4 | Modulgrenzen aus 3.1 bleiben unverletzt | `architekturplan.md` 3.1 |
| K5 | Kein Zustand im Tiler-Prozess; Cache-Ausfall macht nur langsamer | 3.2; E5 |
| K6 | Wenig Egress, Rücksicht auf die Quelle | Prinzip 10; 6.5 |
| K7 | Wenige bewegliche Teile; vorhandene Bausteine statt Eigenbau | 1.1 Ziel 6; 6.3 |
| K8 | Format bleibt austauschbar (Zarr kommt mit M2-09) | 6.2; „Quelle ≠ Format" |

---

## 3. Was gemessen wurde

### 3.1 Die TiTiler-Fabrik lässt den `url`-Parameter fallen — **[M]/[P]**

`titiler.core` 2.3.0 (veröffentlicht am 15.09.2026) definiert in
`titiler/core/factory.py` die Fabrik so, dass der Pfad zum Datensatz über eine
**austauschbare Abhängigkeit** hereinkommt: **[P]**

```python
class TilerFactory(BaseFactory):
    reader: type[BaseReader] = Reader
    path_dependency: Callable[..., Any] = DatasetPathParams
    environment_dependency: Callable[..., dict] = field(default=lambda: {})
```

und jeder Endpunkt schreibt `src_path=Depends(self.path_dependency)` sowie
`env=Depends(self.environment_dependency)`. `DatasetPathParams` ist die
Voreinstellung, die den freien Parameter erzeugt — und sonst nichts: **[P]**

```python
def DatasetPathParams(url: Annotated[str, Query(description="Dataset URL")]) -> str:
    return url
```

Wird sie ersetzt, verschwindet `url` **auch aus dem OpenAPI-Schema**, ist also
nicht bloß unbenutzt, sondern nach außen nicht vorhanden. Gemessen mit einer
Fabrik, deren `path_dependency` `dataset` und `item` als Pfadsegmente und
`asset` als Abfrageparameter nimmt (§10.1): **[M]**

```
routes: 18
has a free 'url' query parameter: False
path parameters: dataset, item, format, height, lat, lon, maxx, maxy, minx, miny,
                 tileMatrixSetId, width, x, y, z
```

Die 18 Routen decken den gesamten Bedarf von M2 ab, ohne dass eine davon selbst
geschrieben werden müsste: **[M]**

| Route | wofür in M2 |
|---|---|
| `…/tiles/{tileMatrixSetId}/{z}/{x}/{y}` | F10 Stufe 2, M2-04 |
| `…/{tileMatrixSetId}/tilejson.json` | Kachelvorlage für MapLibre, M2-07b |
| `…/statistics` | Streckbereich (Z4), M2-04 |
| `…/info`, `…/info.geojson` | Bounds und Bänder für den Layer-Manager |
| `…/preview`, `…/preview/{w}x{h}.{format}` | Quicklook-Ersatz, §3.6 |
| `…/bbox/{minx},{miny},{maxx},{maxy}.{format}` | AOI-Zuschnitt, M2-06 |
| `…/feature` | AOI-Zuschnitt mit Polygon (GeoJSON im Rumpf), M2-06 |
| `…/point/{lon},{lat}` | Punktabfrage (6.3), nicht in M2 nötig |
| `…/{tileMatrixSetId}/map.html` | **abschalten**: `add_viewer=False` |

`add_viewer`, `add_preview`, `add_part` und `add_ogc_maps` sind Schalter an der
Fabrik. **[P]**

### 3.2 Welche HTTP-Clients die Pakete mitbringen — **[M]/[P]**

Die eigentliche Frage aus D5 Punkt 1 ist nicht der `url`-Parameter, sondern ob
ein Paket **hintenherum** selbst holt. Gemessen als Auflösung gegen den
gepinnten Stand des Repos (§10.2): **[M]**

| Paket | was zusätzlich installiert würde | eigener HTTP-Client? |
|---|---|---|
| `titiler.core==2.3.0` | `geojson-pydantic`, `Jinja2`, `MarkupSafe`, `simplejson` | **nein** |
| `titiler.mosaic==2.3.0` | dazu `titiler-mosaic` | **nein** |
| `titiler.mosaic[mosaicjson]` | dazu `cogeo-mosaic 9.2.0`, `supermorecado` | **ja** (`httpx2`, optional `boto3`) |
| `titiler.xarray==2.3.0` | dazu `obstore`, `zarr`, `xarray`, `rioxarray`, `pandas`, `numcodecs`, … | **ja** (`obstore`, Rust-Kern) |

`titiler.core` selbst importiert **keinen** HTTP-Client; die einzigen
`urllib`-Importe sind `urllib.parse.urlencode` zum *Bauen* von URLs in
`factory.py`, `middleware.py` und `utils.py`. **[P]**

**Der Fund, der zählt:** Der Client steckt nicht in TiTiler, sondern in
`rio-tiler` — und er ist **schon heute im venv des Projekts**. `rio-tiler`
9.4.6 hängt hart von `httpx2` ab **[P]**, weil `rio_tiler/io/stac.py`
`import httpx2 as httpx` schreibt, um STAC-Items selbst zu holen. **[P]**
Und weil `rio_tiler/io/__init__.py` `STACReader` mitimportiert, ist `httpx2`
auch dann geladen, wenn nur der rasterio-Reader geholt wird: **[M]**

```
from rio_tiler.io.rasterio import Reader   ->  httpx2 loaded: True
```

Daraus folgt eine unangenehme, aber ehrliche Einsicht (**[A]**): Die Zusage
„kein Request außerhalb des Gateways" kann im Tiler-Prozess **nicht** heißen
„es gibt keinen HTTP-Client im Prozess". Sie kann nur heißen, was B8 ohnehin
sagt — kein Modul von uns importiert einen, und die netzseitige Durchsetzung
kommt mit M6. Die statische Regel muss dafür aber den Namen kennen:
`.importlinter` verbietet heute `httpx`, `requests`, `urllib`,
`pystac_client`, `aiohttp`, `boto3` — **`httpx2` und `obstore` stehen nicht
darin**, und `earthx.readers.cog` dürfte sie heute ohne Widerspruch der CI
importieren. **[M]** (gelesen in `.importlinter` und
`backend/tests/earthx/test_no_outbound_outside_gateway.py::CORE`)

### 3.3 Wo die Adresse `gateway` passiert — und die Lücke davor — **[M]/[P]**

Die beiden Einhängepunkte aus §3.1 sind genau die zwei Stellen, die B8
braucht: **[A]**

- `path_dependency` → gibt `vsicurl_path(check_url(href, policy))` zurück.
  `vsicurl_path` nimmt ausschließlich ein `CheckedUrl` und wirft sonst einen
  `TypeError` (`gateway/gdal.py`) **[P]** — ein roher String kann GDAL über
  diesen Weg nicht erreichen.
- `environment_dependency` → gibt `gdal_options(policy)` zurück, also genau die
  zentrale GDAL-Konfiguration aus M1-03. Die Fabrik wickelt jeden Endpunkt in
  `with rasterio.Env(**env)`. **[P]**

**Die Lücke:** Der Allowlist fehlt der Host, auf dem die Assets liegen.
`policy_from_registry` baut sie allein aus `config.source.endpoint`: **[M]**

```
allowlist from the registry: ['earth-search.aws.element84.com']
refused : e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com -> UrlRejected
refused : sentinel-cogs.s3.us-west-2.amazonaws.com               -> UrlRejected
```

Das ist kein Schönheitsfehler, sondern der erste Fehlschlag, den M2-04 sehen
wird: Der Suchpfad läuft, der Lesepfad ist zu. Die Registry kennt den
Asset-Host bisher an keiner Stelle.

Zwei kleinere Befunde am selben Pfad:

- `CPL_VSIL_CURL_ALLOWED_EXTENSIONS` steht auf `.tif,.tiff,.TIF,.TIFF`
  (`gateway/gdal.py`) **[P]**. Ein `.jpg`-Quicklook ließe sich über
  `/vsicurl/` also gar nicht lesen — für §3.6 ist das kein Problem, für einen
  späteren Datensatz mit JPEG-Assets schon.
- Der Asset-Bucket antwortet **direkt** mit `206 Partial Content`, ohne
  Weiterleitung **[M]**. Die bekannte Schwäche „GDAL folgt Redirects selbst"
  (B8) greift im Sentinel-2-Pfad heute also nicht; sie bleibt ein Risiko für
  andere Quellen und wird erst mit M6 geschlossen.

### 3.4 Was eine Kachel kostet — **[M]**

Gemessen gegen eine reale Szene (`S2B_T37SGB_20260920T080008_L2A`, MGRS 37/S/GB)
mit `rio-tiler` 9.4.6 und der GDAL-Konfiguration aus `gateway/gdal.py`; die
Bytes sind die Summe der Byte-Ranges, die GDAL mit `CPL_DEBUG=ON` meldet (§10.3).
„Kalt" heißt: ein frischer Prozess je Zeile, der VSI-Cache ist leer und der
Header wird mitgelesen.

**Eine einzelne Kachel, kalt:**

| Fall | Zeit | Range-Reads | von der Quelle | PNG |
|---|---|---|---|---|
| `visual` (TCI, 3 Bänder) z8 | 1018 ms | 2 | 96 kB | 4,8 kB |
| `visual` z10 | 742 ms | 2 | 160 kB | 49 kB |
| `visual` z12 | 1164 ms | 3 | 1164 kB | 80 kB |
| `visual` z14 | 1139 ms | 2 | 2016 kB | 96 kB |
| `visual` z16 | 1249 ms | 2 | 2016 kB | 3,9 kB |
| `visual` z18 | 994 ms | 2 | 2016 kB | 0,3 kB |
| `red` (B04, 10 m, 1 Band) z12 | 1044 ms | 3 | 762 kB | 54 kB |
| `red` z14 | 1004 ms | 2 | 1328 kB | 71 kB |

**Ein ganzer Kartenausschnitt, warm** (ein Prozess, 4×4 Kacheln um dieselbe
Mitte, nach dem einmaligen Header-Read von 32 kB):

| Ausschnitt | Kacheln | je Kachel | Range-Reads | von der Quelle | je Kachel |
|---|---|---|---|---|---|
| z11 `visual` | 12 | **193 ms** | 22 | 2916 kB | 243 kB |
| z13 `visual` | 16 | **115 ms** | 5 | 7360 kB | 460 kB |
| z16 `visual` | 16 | **54 ms** | 2 | 2000 kB | 125 kB |

Drei Dinge stehen darin (**[A]**):

1. **Der Header dominiert die erste Kachel.** Kalt kostet jede Kachel rund eine
   Sekunde, warm 54 bis 193 ms. Der Unterschied ist im Wesentlichen der eine
   32-kB-Read auf den COG-Header plus Verbindungsaufbau. `architekturplan.md`
   12.3 führt „Header-Infos von COGs" bereits als Inhalt des Anwendungs-Caches —
   dieser Messwert ist die Begründung dafür.
2. **Die gelesenen Bytes hängen am Block, nicht an der Kachel.** Ab z14 liest
   GDAL rund 2 MB, egal wie klein das gelieferte PNG ist: Es holt den
   Block-Bereich der vollen Auflösung. Warm teilen sich 16 Kacheln bei z16
   dieselben 2 MB (125 kB je Kachel).
3. **Der Sprung liegt zwischen z10 und z12.** Bis z10 bedient eine
   Übersichtsstufe die Kachel mit 160 kB; ab z12 kostet sie das Sieben- bis
   Zwölffache. Für Prinzip 10 ist das die Stelle, an der ein HTTP-Cache vor dem
   Tiler den größten Unterschied macht.

**Statistik und Zuschnitt, kalt:**

| Fall | Zeit | Range-Reads | von der Quelle | Ergebnis |
|---|---|---|---|---|
| `statistics()` auf `visual` | 998 ms | 2 | 336 kB | p2/p98 je Band: 43–255, 39–255, 25–255 |
| `statistics()` auf `red` | 905 ms | 2 | 224 kB | p2/p98: 1422–7301 |
| `part()` ~0,4° AOI, max 1024 px | 887 ms | 3 | 891 kB | 3×1024×1024 |
| `part()` ~0,1° AOI, max 1024 px | 1104 ms | 3 | 4386 kB | 3×986×986 |

Bemerkenswert und gegen die Intuition: Die **kleinere** AOI liest **mehr**
Bytes (4,4 MB gegen 0,9 MB), weil sie auf voller Auflösung landet, während die
größere aus einer Übersichtsstufe bedient wird. Für den Größendeckel in M2-06
heißt das: Ein Deckel auf der AOI-**Fläche** allein misst die Kosten nicht; die
Zielpixelzahl tut es.

### 3.5 Mosaik ohne Zustand trägt — mit Vorfilter — **[M]/[P]**

`rio_tiler.mosaic.mosaic_reader(mosaic_assets, reader, …)` nimmt eine Liste von
Quellen und eine Auswahlregel (Voreinstellung `FirstMethod`, also „erster
gültiger Wert gewinnt" — dieselbe Regel wie F11) und liefert ein Bild plus die
Liste der tatsächlich beteiligten Quellen. **[P]** Es schreibt nichts.
`titiler.mosaic`'s `MosaicTilerFactory` hat `backend: type[BaseBackend]` **ohne**
Voreinstellung **[P]** — ein eigenes Backend ist also vorgesehen, MosaicJSON
und `cogeo-mosaic` sind nicht erzwungen.

Gemessen an einem Aufnahmetag über einem landesgroßen Rechteck, Kachel z11 an
einer Nahtstelle zwischen zwei MGRS-Kacheln (§10.4): **[M]**

| Aufruf | Zeit (2 Läufe) | Range-Reads | von der Quelle | beteiligt |
|---|---|---|---|---|
| 10 Szenen unvorgefiltert | 1571 / 1922 ms | 13 | 2938 kB | 2 |
| auf die 2 überlappenden vorgefiltert | 1143 / 1162 ms | 5 | 2682 kB | 2 |

Ohne Vorfilter öffnet `mosaic_reader` **alle** Kandidaten parallel und liest
deren Header, auch wenn sie die Kachel gar nicht berühren: 13 statt 5 Reads.
Der Vorfilter über die `bbox` der Items — die der Tiler ohnehin in der Hand hat
— ist billig und spart ein Viertel der Zeit und acht Anfragen an die Quelle.
**[A]**

**Passt die Item-Liste in die URL?** Gemessen an realen Suchen: **[M]**

| Suche | `numberMatched` |
|---|---|
| stadtgroßes Rechteck, ein Monat | 19 |
| dasselbe Rechteck, ein Jahr | 210 |
| landesgroßes Rechteck, ein Monat | 404 |
| landesgroßes Rechteck, **ein Aufnahmetag** | 15, davon höchstens 22 an einem Tag im Monat |

Item-IDs von `sentinel-2-c1-l2a` sind durchweg **30 Zeichen** lang **[M]**
(`S2B_T37SGB_20260920T080008_L2A`). Ein Mosaik ist fachlich immer *ein*
Zeitschritt (F5, F11), also höchstens rund 22 Szenen: **682 Zeichen** in einer
`items=`-Liste. Das liegt weit unter der praktischen Browser- und CDN-Grenze
von etwa 2 kB und unter dem Gateway-Deckel von 8192 Bytes (`Policy`,
`adr/0004` §3.4). **[A]** Eine Liste über ein ganzes Jahr (210 Items, 6,5 kB)
oder über einen Monat (404 Items, 12,5 kB) passt dagegen nicht — aber sie wäre
auch kein Mosaik, sondern eine Zeitreihe.

**Was die Item-Liste kostet, bevor gerendert wird:** Jede ID muss zu einer
Adresse aufgelöst werden. Ein Item-GET bei Earth Search dauert **0,42–0,47 s**
bei 17,7 kB. **[M]** Der Adapter hält Items bereits 24 h im Postgres-Cache
(`TTL_ITEM_S`, `adapters/earth_search.py`) **[P]**, und die vorangegangene
Suche hat die Items ohnehin schon geliefert — die Auflösung ist damit in der
Praxis ein Cache-Treffer, nicht ein Upstream-Aufruf. **[A]**

### 3.6 Quicklooks brauchen keinen Proxy — **[M]**

Der Prototyp hat den Asset-Proxy nur, weil MAAP einen Token verlangt (F15);
`architekturplan.md` 6.4 will Rohdaten ohnehin per Link direkt von der Quelle.
Offen war allein, ob der Browser das Bild dann auch **auswerten** darf — F6
zeichnet den Quicklook in ein Canvas und setzt schwarze Ränder auf
durchsichtig, und das geht nur mit CORS-Freigabe.

Gemessen am Asset-Bucket, sowohl mit `Origin`-Kopfzeile als auch als
OPTIONS-Vorabanfrage, für das JPEG **und** für das GeoTIFF: **[M]**

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: HEAD, GET
Vary: Origin, Access-Control-Request-Headers, Access-Control-Request-Method
```

`earth-search.aws.element84.com` sendet ebenfalls `access-control-allow-origin: *`.
**[M]** Damit ist F6 ohne jeden Proxy machbar: Der Browser lädt
`assets.thumbnail.href` direkt (6,4 kB JPEG **[M]**), und das Canvas-Keying
funktioniert. Keine Modulgrenze wird berührt, weil kein Byte durch das Backend
läuft.

Für eine Quelle ohne Thumbnail oder ohne CORS — bei EOPF ist „kein Quicklook"
bereits belegt (`adr/0003` §10.3) — gibt es den Ersatz aus derselben Fabrik:
`/preview` auf einem COG-Asset. Gemessen am `preview`-Asset (`L2A_PVI.tif`,
343×343 px, 3 Bänder, EPSG:32637): **767 ms kalt, 1 Range-Read, 24,8 kB von der
Quelle, 24,3 kB PNG.** **[M]** Dieser Weg liegt in `access` und liest über
`readers` — die Frage „wo liegt der Proxy, ohne 3.1 zu verletzen" stellt sich
damit gar nicht mehr, weil es keinen Proxy gibt.

### 3.7 Der Asset-Host: `cloud-umgebung.md` §6 nennt den falschen — **[M]**

Der Prüfpunkt aus D5 Punkt 5 ist eindeutig entschieden. An echten Items
gemessen:

| Collection | Host der Assets |
|---|---|
| **`sentinel-2-c1-l2a`** (unser Datensatz) | **`e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com`** |
| `sentinel-2-l2a` (die ältere Collection) | `sentinel-cogs.s3.us-west-2.amazonaws.com` |

**Alle 22 Assets** des geprüften Items — `visual`, die 13 Bänder, `scl`, `aot`,
`wvp`, `preview`, `thumbnail` und die drei Metadatendateien — liegen auf dem
ersten Host. **[M]** `sentinel-cogs…` gehört zur Collection `sentinel-2-l2a`,
die Collection 1 ablöst (`adr/0003` §3, Option B). `adr/0003` §10.1 hat also
richtig gemessen; die Zeile in `cloud-umgebung.md` §6, die
`sentinel-cogs…amazonaws.com` mit „(Assets des ersten Datensatzes)" beschriftet,
ist **falsch beschriftet** — nicht falsch in der Erreichbarkeit: Beide Hosts
antworten in dieser Sitzung mit `206` auf einen Range-Read. **[M]**

Damit ist der Widerspruch, den M2-00 stehen lässt und dessen Klärung dieser
Spike übernehmen soll, aufgelöst. Er ist eine Beschriftungsfrage, keine
Freigabefrage.

Nebenbefund zur Registry: Die Collection meldet oben `extent.spatial`
`[-180,-90,180,90]` — der Platzhalter im Registry-Eintrag trifft also zu —, und
`extent.temporal` beginnt am **2015-06-27T10:25:31.456Z** mit offenem Ende.
**[M]** Ein `renders`-Feld führt die Collection **nicht**; die
Standard-Visualisierung muss aus unserer Registry kommen, wie M2-04 es vorsieht.
**[M]**

---

## 4. Optionen

### 4.1 Aufbau der Endpunkte

| | Option | Dafür | Dagegen |
|---|---|---|---|
| **A** | Eigene Routen auf `rio-tiler`, wie im Prototyp | nichts Neues im Abhängigkeitsbaum | 18 Routen selbst schreiben und pflegen; widerspricht 6.3 und K7 |
| **B** | `titiler.core` mit ersetzter `path_dependency` | alle Routen fertig; kein neuer HTTP-Client (§3.2); `url` nachweislich weg (§3.1) | ein Paket mehr, das eigenem Takt folgt |
| **C** | `titiler.application` (das fertige Programm) | am wenigsten Arbeit | zieht `titiler.xarray` → `obstore` und `titiler.extensions[stac]` mit; freie `url` an mehreren Stellen |

### 4.2 Mosaik

| | Option | Dafür | Dagegen |
|---|---|---|---|
| **M1** | Item-Liste in der URL, `mosaic_reader` | zustandslos; URL bestimmt das Bild (K3); passt (§3.5) | je Kachel N Header-Reads ohne Vorfilter |
| **M2** | Such-ID, Liste im Postgres-Cache | kurze URL | die URL bestimmt das Bild **nicht** mehr: fällt der Eintrag aus, ändert sich die Antwort — verletzt K3 und E5 gleichzeitig |
| **M3** | MosaicJSON über `cogeo-mosaic` | Standardformat | holt die MosaicJSON selbst über `httpx2`/`boto3` (§3.2) — B8-Verstoß |
| **M4** | Kein Mosaik im Kachel-Pfad in M2 | billigste Variante; der Zuschnitt (M2-06) mosaikt trotzdem einmal je Anfrage | F11 bleibt im Viewer länger aus |

### 4.3 Statistik-Cache

| | Option | Dafür | Dagegen |
|---|---|---|---|
| **S1** | Eigene Tabelle `earthx_stats_cache`, Form wie `earthx_search_cache` | ehrlicher Name; eigene Frist und eigener Kehraus | eine Migration mehr |
| **S2** | `earthx_search_cache` mitbenutzen | keine Migration | Name und Kommentar sagen „Suche"; zwei Bedeutungen in einer Tabelle |
| **S3** | Kein Cache, jedes Mal rechnen | nichts zu bauen | rund 0,9–1,0 s je Ansicht (§3.4) vor der ersten Kachel |

---

## 5. Empfehlung

**Option B, M1 (aber nur für den Zuschnitt in M2), S1.** Im Einzelnen, je Frage
aus dem Aufgabenschnitt:

**Zu Frage 1 — Fabriken ohne freien `url`-Parameter.** Ja, und nachweisbar.
`titiler.core==2.3.0` **exakt gepinnt**, wie `pypgstac` und `stac-fastapi.pgstac`
schon gepinnt sind; `rio-tiler` ebenfalls exakt pinnen statt `>=6.4`, weil es
den einzigen HTTP-Client im Kachel-Pfad mitbringt. Weder `titiler.application`
noch `titiler.mosaic[mosaicjson]` noch `titiler.xarray` aufnehmen. Die
Standard-`DatasetPathParams` wird durch eine eigene Abhängigkeit ersetzt, die
`dataset` und `item` aus dem Pfad und `asset` aus der Abfrage nimmt; ein Test
prüft das OpenAPI-Schema darauf, dass **kein** Endpunkt einen Parameter namens
`url` führt (so, wie §10.1 es misst). `add_viewer=False`.

Dazu die Regel nachziehen, die den eigentlichen Fund von §3.2 festhält:
`httpx2` und `obstore` gehören in die `forbidden_modules` von
`http-only-in-gateway` und in das `CORE`-Set von
`test_no_outbound_outside_gateway.py`.
*Das ist eine Änderung an den Importregeln und liegt deshalb bei Otto (Frage 6).*

**Was diese Liste nicht leistet, und was sie deshalb braucht.** Der Vertrag
`http-only-in-gateway` trägt seit jeher `allow_indirect_imports = True` (seit
M2-01 tun das auch die neun Modulverträge, Log vom 2026-09-20), zählt also nur
**direkte** Importe — und genau das ist hier richtig: `earthx.readers` *wird*
`rio_tiler` importieren, und `rio_tiler` zieht `httpx2` nach. Zählte der Vertrag
Ketten, wäre jeder Reader ein Verstoß und die Regel damit unbrauchbar. Die Liste
fängt also den Fall „ein Modul von uns importiert selbst einen Client" — und nur
den. Was sie nicht sieht, ist der eigentliche Weg, auf dem `rio-tiler`
tatsächlich selbst holt: `rio_tiler.io.stac.STACReader`.

Dafür gehört ein zweiter, schmaler Test dazu, der auf derselben Ebene arbeitet
wie der vorhandene Syntaxbaum-Lauf, aber auf das **Untermodul** statt auf das
Wurzelpaket schaut:

```python
def test_no_module_imports_the_stac_reader_of_rio_tiler(path: Path) -> None:
    """rio_tiler.io.stac fetches items over httpx2 (adr/0006 §3.2).
    Items come from `adapters`, through `gateway`, and from nowhere else."""
    source = path.read_text(encoding="utf-8")
    assert "rio_tiler.io.stac" not in source
    assert "STACReader" not in source
```

Der Namensvergleich genügt hier, weil `STACReader` nur über einen dieser beiden
Namen in den Code kommt — `rio_tiler/io/__init__.py` exportiert ihn ausdrücklich
**[P]**, `from rio_tiler.io import STACReader` ist also der wahrscheinlichere
Weg als der Import des Untermoduls. Der Vergleich ist bewusst gröber als der
AST-Lauf, weil er beide Schreibweisen und auch einen Import im Funktionsrumpf
erwischt.

`import-linter` kann diesen Fall **nicht** übernehmen, und zwar nicht aus
Nachlässigkeit, sondern grundsätzlich. Gemessen an einem Wegwerf-Vertrag mit
`forbidden_modules = rio_tiler.io.stac`: **[M]**

```
Invalid forbidden module rio_tiler.io.stac: subpackages of external packages are
not valid.
```

Das Werkzeug lehnt den Vertrag ab, statt ihn stillschweigend leerlaufen zu
lassen — gut so, aber es heißt, dass der Test oben kein Komfort ist, sondern die
einzige Stelle, an der diese Regel geprüft werden kann.

**Zu Frage 2 — der Weg über `gateway`.** Die ersetzte `path_dependency` ist der
einzige Ort, an dem eine Adresse entsteht, und sie gibt
`vsicurl_path(check_url(href, policy))` zurück; `vsicurl_path` nimmt nichts
anderes an als ein `CheckedUrl`. `environment_dependency` gibt
`gdal_options(policy)` zurück — damit greift die zentrale GDAL-Konfiguration aus
M1-03 an jedem Endpunkt, ohne dass ein Aufrufer sie setzen müsste.

Die Lücke aus §3.3 wird geschlossen, indem die Registry den Asset-Host kennt:
ein Feld an `SourceInfo`, etwa

```python
asset_hosts: tuple[str, ...]   # KLAERUNGEN B10: bewusst gesetzt, kein Vorgabewert
```

mit derselben `https`-Prüfung wie `endpoint`, und `policy_from_registry` bildet
die Vereinigung aus Endpunkt-Hosts und Asset-Hosts. Für `sentinel-2-c1-l2a`
steht dort `e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com` (§3.7).
Ein Test prüft, dass die Adressen echter Items (aus einer Fixture) gegen die so
gebaute Policy bestehen — sonst wiederholt sich der Fehlschlag später still bei
jedem neuen Datensatz.

**Zu Frage 3 — Streckbereich in der URL.** Nichts Eigenes erfinden: Die
Parameter der Fabrik reichen genau aus. `rescale=lo,hi` (je Ausgabeband
wiederholbar), `colormap_name` bzw. `colormap`, `bidx` bzw. `expression` für die
Bandwahl. Der Ablauf im Viewer ist der aus F18, nur mit dem Zustand an der
richtigen Stelle:

1. Der Client fragt `…/statistics` **einmal** für die gewählte Bandauswahl ab
   (`p=2&p=98` ist die Voreinstellung der Fabrik **[P]**).
2. Er schreibt das Ergebnis als `rescale=` in die Kachelvorlage.
3. Jede Kachel-URL trägt damit alles, was das Bild bestimmt (K3, Z4). Zwei
   Instanzen liefern dieselben Bytes, und ein CDN darf sie beliebig lange
   halten.

Der Statistik-Cache wird eine **eigene** Tabelle `earthx_stats_cache` in der
Form von `earthx_search_cache` (Schlüssel als opaker Hash, `jsonb`,
`expires_at`, Migration `003_stats_cache.sql`), Schlüssel über
`(dataset, item, asset, bidx/expression, Perzentile)`. **Frist: 30 Tage.**
Anders als eine Suche ändert sich die Statistik einer unveränderlichen Datei
nie; die Frist ist reine Platzpflege, kein Frischeproblem. Ein Fehlschlag kostet
die gemessenen 0,9–1,0 s und sonst nichts (E5).

**Der COG-Header bekommt in M2 keinen Cache** (Otto, 20.09.2026). §3.4 zeigt
ihn als teuersten Einzelposten einer kalten Ansicht — 32 kB und der Löwenanteil
der ersten Sekunde —, und `architekturplan.md` 12.3 führt „Header-Infos von
COGs" bereits als Inhalt des Anwendungs-Caches. Gebaut wird er trotzdem nicht in
M2: Der Statistik-Cache ist der Posten, der die erste Kachel spürbar macht, und
zwei Caches auf einmal einzuführen wäre mehr Fläche, als M2 braucht. Der Punkt
steht als **offene** Zeile im Entscheidungslog, mit Verweis auf 12.3.

Die Standard-Visualisierung (Checklistenpunkt 8, FZ7) gehört als Feld in die
Registry — `DefaultRender` existiert bereits mit `bands`, `stretch`, `colormap`.
Empfehlung: die Feldnamen an der STAC-`render`-Extension ausrichten
(`assets`, `rescale`, `colormap_name`, `expression`, `resampling`, `title`),
damit die Werte später ohne Übersetzung als `renders` an der eigenen Collection
veröffentlicht werden können. Die Quelle führt selbst keine (§3.7), also muss
der Wert in M2-04 aus einer Messung an echten Assets kommen — die Zahlen aus
§3.4 (`visual`: 43–255 / 39–255 / 25–255) sind ein Anhaltspunkt einer einzigen
Szene, keine Vorgabe.

**Zu Frage 4 — Mosaik und Stitching.** Zustandsloses Mosaik ist machbar (§3.5),
und wenn es kommt, dann als **Item-Liste in der URL** (M1), nie als Such-ID: Eine
Such-ID nähme der URL genau die Eigenschaft, um derentwillen Z4 in die URL
wandert. Gedeckelt auf höchstens 25 Items je URL, mit Vorfilter über die
Item-`bbox` vor dem Öffnen.

**Für M2 empfehle ich dennoch M4 für den Kachel-Pfad und M1 nur für den
Zuschnitt.** Begründung: Eine Mosaik-**Kachel** kostet 2,7 MB von der Quelle und
über eine Sekunde (§3.5), und sie kostet das bei *jeder* Kachel neu, solange
kein CDN davor steht — das kommt erst mit M6 (12.1). Ein **Zuschnitt** mosaikt
einmal je Anfrage und trägt dieselben Kosten genau einmal. Damit bekommt F11 in
M2 die Funktion zurück, die der Nutzer tatsächlich braucht (eine Datei über die
AOI, D3), ohne dass der Kachel-Pfad eine Größenordnung teurer wird. Mosaik-
Kacheln wandern nach M3, zusammen mit dem CDN.

**Nachtrag M3-00 (2026-09-23):** Entschieden ist **M4**, nicht M3 (D11, P11 in
`plans/m3-dritte-quelle-und-interface.md`); der Satz oben bleibt als
ursprüngliche Einschätzung stehen.

**Zu Frage 5 — Quicklook-Proxy.** **Es gibt keinen.** Der Browser lädt das
Thumbnail direkt von der Quelle; CORS ist offen (§3.6), 6.4 verlangt es so, und
F15 fällt mit dem Token weg. Die Registry bekommt dafür zwei Felder: den
Asset-Schlüssel des Quicklooks und die Nodata-Schwelle für das Canvas-Keying
(F6 nennt beide ausdrücklich als „gehört an den Datensatz statt in den Code");
die Geometrie-Drehung aus F6 Punkt 3 ist BIOMASS-spezifisch und entfällt
ersatzlos. Fehlt einer Quelle das Thumbnail oder die CORS-Freigabe, rendert
`…/preview` aus einem COG-Asset den Ersatz (767 ms, 25 kB, §3.6) — derselbe
Pfad, dieselbe Fabrik, keine neue Naht. Ein Byte-Reader in `readers` wird nicht
gebraucht, eine Proxy-Route in `api` widerspricht 6.4.

Zwei Einschränkungen gehören ausdrücklich dazu, weil der Satz „es gibt keinen
Proxy" sonst weiter trägt, als er darf:

**Das weicht von `ENTSCHEIDUNGEN` §2 ab.** Dort steht der „Asset-Proxy mit
Host-Allowlist als Vorläufer von `gateway`" unter dem, was vom Prototyp
**erhalten** bleiben soll. Otto hebt diesen Punkt am 20.09.2026 ausdrücklich
auf: Der Allowlist-Gedanke ist längst gerettet — er ist `gateway` geworden
(6.5, B8) —, und der Proxy selbst hatte nur einen Grund, nämlich den Token
(F15). Mit einer token-freien Quelle, die CORS sendet, bliebe von ihm eine
Umleitung ohne Zweck, die 6.4 („kein Byte läuft durch das eigene Backend")
zuwiderläuft. Die Entscheidungslog-Zeile hält das als Aufhebung fest, nicht als
stillschweigende Auslegung.

**Und es gilt nur, wo der Asset-Host CORS sendet.** Gemessen habe ich das für
den Asset-Bucket von Sentinel-2 (§3.6) — und für sonst nichts. Der
EOPF-Objektspeicher sendet laut `adr/0007` (M2-03, parallel; nicht meine
Messung) **keinen** CORS-Header und beantwortet die Vorabanfrage mit `403`.
Für eine solche Quelle käme ein Proxy zurück, und dann als Route in `api` über
`gateway` oder als Byte-Reader in `readers` — die Optionen, die dieser Spike
untersucht und für Sentinel-2 verworfen hat. Die Bedingung gehört deshalb an
den **Datensatz**, nicht in eine allgemeine Regel: Das CORS-Feld steht schon
heute in der Registry (`AccessInfo.cors`, für Sentinel-2 bisher `None` —
§3.6 füllt es mit `True`), und der Viewer entscheidet daran, ob er direkt lädt
oder den Ersatz anfordert. Der Ersatz `…/preview` bleibt ohnehin der Weg für
jede Quelle ohne Thumbnail; ob er für eine Quelle ohne CORS ausreicht oder ob
es doch einen Proxy braucht, entscheidet `adr/0007` für Zarr, nicht dieses ADR.

**Zu Frage 6 — nur `https`, kein `s3`.** **Bestätigt.** Drei Gründe, jeder für
sich ausreichend: `inspect_url` lässt nur `https` durch, und das ist eine
bewusste Setzung, keine Lücke (`gateway/policy.py`) **[P]**; `/vsis3/` bräuchte
AWS-Konfiguration und praktisch `boto3`, das auf der Verbotsliste steht; und der
Bucket liefert anonym über `https` dieselben Bytes mit `206` (§3.3, §3.7). Ein
`s3`-Pfad kaufte nichts und kostete die Prüfbarkeit.

**Zu Frage 7 — Asset-Host.** `e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com`
(§3.7). `cloud-umgebung.md` §6 ist entsprechend zu berichtigen: Die Zeile
`sentinel-cogs…` ist erreichbar, aber nicht der Host unseres Datensatzes. Beide
gehören **nicht** in die Registry-Allowlist — nur der erste, und zwar über das
Feld aus Frage 2.

**Zu Frage 8 — Rendering-Kosten.** §3.4. Für Prinzip 10 die drei Sätze, die
bleiben: warm kostet eine Kachel 54–193 ms; ab z12 liest der Tiler je
Block-Bereich rund 2 MB von der Quelle, unabhängig von der Kachelgröße; und der
COG-Header (32 kB) ist der teuerste Einzelposten einer kalten Ansicht und gehört
deshalb in den Anwendungs-Cache (12.3).

### 5.1 Wo der Kachel-Pfad liegt — eine Modulgrenze, die auffällt

Die Zusammensetzung passt **nicht** in `access`. `access` darf `gateway` nach
3.1 nicht importieren (`.importlinter`, Vertrag `access`) **[P]**, braucht aber
`Policy`, `check_url` und `gdal_options`, um die beiden Abhängigkeiten der
Fabrik zu bauen. Heute startet der `tiler`-Prozess aber genau dort:
`docker-compose.yml` ruft `earthx.access.main:app`. **[P]**

Die saubere Auflösung folgt 3.1 selbst — `api` ist das Modul, das „alles
zusammensetzt":

| Modul | was dort liegt |
|---|---|
| `readers/cog.py` | partielle COG-Reads; importiert `gateway`, ruft `check_url` und `vsicurl_path` |
| `access` | die `TilerFactory`-Unterklasse, die Render- und Zuschnittlogik; kennt `readers` und `catalog`, kein `gateway` |
| `api/tiler.py` (neu) | Prozess-Einstieg des `tiler`: baut `Policy` aus der Registry, hängt die Fabrik mit `path_dependency` und `environment_dependency` ein |

`docker-compose.yml` zeigt dann auf `earthx.api.tiler:app`, und `tiler` bekommt
die `PG*`-Variablen für den Statistik-Cache — den Fall, dass ein Dienst ohne sie
nicht startet, nennt M2-04 aus M1-07 bereits ausdrücklich. Dass der Tiler
Postgres anfasst, widerspricht B9 nicht: B9 gilt dem **Worker-Kern**, und ein
Cache ist kein Zustand — sein Ausfall macht langsamer, nie falsch (E5, K5).

---

## 6. Folgen

1. **`architekturplan.md` 6.3** wird präziser: TiTiler-Basis heißt
   `titiler.core` mit ersetzter Pfad-Abhängigkeit; Mosaike laufen über eine
   Item-Liste in der URL, nicht über eine Such-ID — der Satz „Suchergebnis wird
   unter einer Such-ID kurz gecacht, damit Tile-URLs stabil und CDN-fähig sind"
   kehrt seine eigene Begründung um und ist zu ersetzen.
2. **Die Registry wächst um drei Felder:** `asset_hosts` an `SourceInfo`
   (Allowlist), Quicklook-Asset samt Nodata-Schwelle, und `DefaultRender` wird
   gefüllt. Alle drei ohne Vorgabewert, wie B10 es verlangt. Dazu wird
   `AccessInfo.cors` für Sentinel-2 von `None` auf `True` gesetzt (§3.6) — der
   Viewer entscheidet daran, ob er den Quicklook direkt lädt.
3. **`.importlinter` und der AST-Test** nennen `httpx2` und `obstore`, und ein
   zusätzlicher Test verbietet `rio_tiler.io.stac` bzw. `STACReader` beim
   Namen, weil `import-linter` Unterpakete externer Pakete gar nicht annimmt
   (§5, „Zu Frage 1"). Lockerung ist das keine — es ist eine Verschärfung.
4. **`backend/requirements.txt`** bekommt `titiler.core==2.3.0` und einen exakten
   Pin für `rio-tiler`.
5. **`docker-compose.yml`:** `tiler` startet `earthx.api.tiler:app` und bekommt
   die `PG*`-Variablen; `compose-topology` prüft es.
6. **`cloud-umgebung.md` §6 ist berichtigt** (§3.7) — nachgezogen auf `main`,
   noch während dieser Entwurf offen war. Eine Freigabe war dafür nicht nötig:
   Beide Hosts antworten heute.
7. **M2-06 bekommt vom Spike die Empfehlung, zu mosaiken** (ein Mosaik je
   Anfrage), und den Hinweis, den Größendeckel an der **Zielpixelzahl**
   festzumachen, nicht an der AOI-Fläche (§3.4).
8. **M2-09 erbt eine Warnung:** `titiler.xarray` bringt `obstore` mit, also
   einen eigenen HTTP-Client. `adr/0007` muss dafür denselben Nachweis führen
   wie §3.1 hier, oder den Zarr-Lesepfad ohne dieses Paket bauen.
9. **`ENTSCHEIDUNGEN` §2 verliert einen Punkt:** Der „Asset-Proxy mit
   Host-Allowlist" steht dort unter dem, was erhalten bleiben soll; Otto hebt
   ihn am 20.09.2026 auf (§5, „Zu Frage 5"). Der Allowlist-Gedanke lebt in
   `gateway` weiter, der Proxy selbst nicht.
10. **Der COG-Header-Cache bleibt offen.** Nicht in M2 (§5, „Zu Frage 3"); als
    offene Zeile im Entscheidungslog geführt, mit Verweis auf
    `architekturplan.md` 12.3.

---

## 7. Fragen an Otto — beantwortet am 2026-09-20

Otto hat alle sieben Fragen entschieden; jede Antwort folgt der Empfehlung.
Die Optionen bleiben stehen, damit nachvollziehbar ist, wogegen entschieden
wurde.

**1. Mosaik in M2.** §3.5 zeigt: zustandslos machbar, aber je Kachel teuer.

1. **Nur der AOI-Zuschnitt mosaikt (M2-06), Kacheln nicht** — *Empfehlung*.
2. Auch der Kachel-Pfad mosaikt (M2-04 wird größer und teurer).
3. Gar kein Mosaik in M2; F11 kommt mit M3.

> **Antwort: 1.** Mosaik in M2 nur im Zuschnitt, nicht im Kachel-Pfad.

**2. Asset-Hosts in der Registry.** Ohne sie steht der Lesepfad still (§3.3).

1. **Neues Feld `asset_hosts` an `SourceInfo`, ohne Vorgabewert, fließt in die
   Allowlist** — *Empfehlung*.
2. Eine Umgebungsvariable neben der Registry (wie vor M1-04).

> **Antwort: 1.** Feld `asset_hosts` an `SourceInfo`, ohne Vorgabewert (B10),
> fließt in die Allowlist ein. **Die Umsetzung macht M2-04**, nicht dieses ADR.

**3. Statistik-Cache.**

1. **Eigene Tabelle `earthx_stats_cache`, Frist 30 Tage** — *Empfehlung*.
2. `earthx_search_cache` mitbenutzen, keine Migration.

> **Antwort: 1.** Eigene Tabelle, 30 Tage. Ergänzend: **Ein Cache für den
> COG-Header kommt nicht in M2**; er wird als offene Zeile im Entscheidungslog
> geführt, mit Verweis auf `architekturplan.md` 12.3.

**4. Quicklook.** CORS am Asset-Bucket ist offen (§3.6).

1. **Browser lädt direkt von der Quelle; `…/preview` nur als Ersatz für Quellen
   ohne Thumbnail** — *Empfehlung*.
2. Immer über `…/preview` rendern, auch wenn ein Thumbnail da ist (gleiches Bild
   für alle Datensätze, aber Kosten und Latenz bei jedem Quicklook).

> **Antwort: 1.** Der Proxy entfällt, der Browser lädt das Thumbnail direkt.
> Mit zwei Festlegungen, die §5 („Zu Frage 5") ausführt: Das **hebt den
> Asset-Proxy aus `ENTSCHEIDUNGEN` §2 ausdrücklich auf** — die
> Entscheidungslog-Zeile sagt das —, und es **gilt nur für Quellen, deren
> Asset-Host CORS sendet**. Für den EOPF-Objektspeicher (kein Header, Preflight
> `403`, `adr/0007`) käme ein Proxy zurück; das ist eine Bedingung am Datensatz,
> keine allgemeine Regel.

**5. Einstieg des `tiler`-Prozesses.** `access` darf `gateway` nicht
importieren, startet aber heute den Prozess (§5.1).

1. **Einstieg nach `earthx/api/tiler.py` verschieben; `access` behält Fabrik und
   Renderlogik** — *Empfehlung*.
2. Den Vertrag `access` so lockern, dass `access` `gateway` importieren darf
   (*davon rate ich ab*: es hebt genau die Grenze auf, die 3.1 zieht).

> **Antwort: 1.** Der Einstieg wandert nach `api`.

**6. Importregeln verschärfen.** `httpx2` und `obstore` in die
`forbidden_modules` von `http-only-in-gateway` und in `CORE` des AST-Tests
aufnehmen (§3.2)?

1. **Ja** — *Empfehlung*.
2. Nein, beim heutigen Stand bleiben.

> **Antwort: 1.** Beide aufnehmen. Ergänzend festgehalten: **Die Liste erfasst
> nur direkte Importe**, und das ist richtig so, weil `readers` `rio_tiler`
> importieren wird. Dazu kommt ein eigener Test, der sicherstellt, dass kein
> Modul `rio_tiler.io.stac` bzw. `STACReader` importiert — §5 („Zu Frage 1")
> nennt ihn samt dem Grund, warum `import-linter` das nicht kann.

**7. Status dieses ADR.**

> **Antwort: angenommen**, mit den Antworten 1–6. Die Zeile im
> Entscheidungslog steht damit auf **fest**.

---

## 8. Was offen blieb

1. **Latenz aus einer EU-Region.** Alle Zeiten in §3.4 sind aus dieser
   Cloud-Sitzung heraus gegen `us-west-2` gemessen. Wie viel davon Laufzeit und
   wie viel Entfernung ist, sagt diese Messung **nicht** — `architekturplan.md`
   12.2 („Compute folgt den Daten") bleibt davon unberührt, bekommt hier aber
   keine Zahl.
2. **Nebenläufigkeit.** Gemessen wurde ein Prozess ohne Last. Wie sich
   `max_connections_per_host = 6` (`Policy`) auf gleichzeitige Kachelanfragen
   auswirkt, ist ungemessen — GDAL läuft ohnehin an diesem Deckel vorbei, was
   B8 bereits festhält.
3. **HTTP-Cache-Kopfzeilen.** Welche `Cache-Control`-Werte die Kachelantworten
   tragen sollen (der Prototyp setzt `max-age=86400`), ist hier nicht
   entschieden; es gehört zu M2-04 und hängt am CDN, das erst mit M6 kommt.
4. **`GDAL_HTTP_MERGE_CONSECUTIVE_RANGES`.** Die Wirkung ist in den Messungen
   enthalten, aber nicht gegen ein Ausschalten verglichen. Ohne Vergleich ist
   nicht belegt, wie viel die Einstellung trägt.
5. **Blockgröße der Quelle.** Dass ab z14 rund 2 MB gelesen werden, ist
   gemessen; die innere Kachelung der Sentinel-2-COGs, aus der sich das ergibt,
   wurde nicht ausgelesen.
6. **`titiler.core` 2.3.0 ist fünf Tage alt.** Der Pin ist deshalb kein Komfort,
   sondern nötig. Ob die Fabrik-Schnittstelle in 2.x stabil bleibt, ist
   unbelegt.
7. **Nur eine Szene.** Alle Pixelmessungen stammen aus einer einzigen Szene
   (37/S/GB, Ende September). Wolkenanteil und Kompressionsgrad anderer Szenen
   verschieben die Byte-Zahlen; die Größenordnungen sollten bleiben (**[A]**).
8. **Der COG-Header-Cache ist vertagt, nicht verworfen.** §3.4 belegt, dass er
   der größte Hebel für die erste Kachel einer Ansicht wäre; `architekturplan.md`
   12.3 sieht ihn vor. Otto nimmt ihn am 20.09.2026 aus M2 heraus (§7 Frage 3);
   er steht als **offene** Zeile im Entscheidungslog. Ungemessen bleibt, wie viel
   er im Betrieb tatsächlich spart — 629 ms in einem kalten Prozess sind eine
   Obergrenze, keine Ersparnis pro Anfrage.
9. **CORS nur für eine Quelle gemessen.** §3.6 gilt dem Asset-Bucket von
   Sentinel-2. Dass der EOPF-Objektspeicher keinen CORS-Header sendet und die
   Vorabanfrage mit `403` beantwortet, stammt aus `adr/0007` (M2-03) und ist
   **nicht** meine Messung. Für jede weitere Quelle ist CORS neu zu prüfen,
   bevor der Viewer direkt lädt; das Feld dafür (`AccessInfo.cors`) gibt es
   bereits.

---

## 9. Quellen

**Primärquellen [P] — Quelltext und Paketmetadaten**

- `titiler.core` 2.3.0: `titiler/core/factory.py` (`TilerFactory`,
  `BaseFactory`, `register_routes`, die Schalter `add_viewer`, `add_preview`,
  `add_part`, `add_ogc_maps`), `titiler/core/dependencies.py`
  (`DatasetPathParams`, `StatisticsParams`, `ImageRenderingParams`) —
  aus dem Wheel von PyPI gelesen.
- `titiler.mosaic` 2.3.0: `titiler/mosaic/factory.py` (`backend` ohne
  Voreinstellung).
- `rio-tiler` 9.4.6: `rio_tiler/io/__init__.py`, `rio_tiler/io/stac.py`
  (`import httpx2 as httpx`), `rio_tiler/mosaic/__init__.py` (`mosaic_reader`).
- PyPI-Metadaten (`requires_dist`) von `titiler.core`, `titiler.mosaic`,
  `titiler.application`, `titiler.xarray`, `rio-tiler`, `cogeo-mosaic`.
- Eigener Code: `backend/earthx/gateway/{policy,checks,gdal}.py`,
  `backend/earthx/api/dependencies.py`, `backend/earthx/adapters/earth_search.py`,
  `backend/earthx/catalog/{registry,datasets,search_cache}.py`,
  `.importlinter`, `backend/tests/earthx/test_no_outbound_outside_gateway.py`,
  `docker-compose.yml`.

**Gemessene Quellen [M]**

- Earth Search v1, `https://earth-search.aws.element84.com/v1` —
  `/collections`, `/collections/sentinel-2-c1-l2a`, `POST /search`,
  `/collections/sentinel-2-c1-l2a/items/{id}`.
- `https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com` —
  Range-Reads, CORS, `HEAD`.
- `https://sentinel-cogs.s3.us-west-2.amazonaws.com` — Range-Read zur
  Abgrenzung (§3.7).
- `import-linter` 2.x selbst: ein Wegwerf-Vertrag über `rio_tiler.io.stac`,
  der mit „subpackages of external packages are not valid" abgelehnt wird
  (§5, „Zu Frage 1").

**Übernommen, nicht selbst gemessen**

- `adr/0007` (M2-03, parallel): CORS-Verhalten des EOPF-Objektspeichers — kein
  Header, Vorabanfrage `403`. Grundlage der Einschränkung in §5 („Zu Frage 5")
  und in §8 Punkt 9.

**Dokumente des Projekts**

`ENTSCHEIDUNGEN_2026-09-18.md` §2, §3; `KLAERUNGEN.md` B8, B9, B10, B13;
`architekturplan.md` 3.1, 3.2, 6.2–6.5, 12.1–12.3, 13, 15.2;
`adr/0001` Z4, Z8, FZ4, FZ7 und §9.3; `adr/0003` §3, §10.1, §10.3;
`adr/0004` §3.4, §5; `adr/0005` Regel II–V;
`prototyp-inventar.md` F5, F6, F9–F11, F14, F15, F18, F19;
`projektuebersicht.md` Prinzip 10, §5; `cloud-umgebung.md` §6;
`ENTSCHEIDUNGSLOG.md`, Zeilen vom 2026-09-20 (D3, D5).

---

## 10. Messanhang

Alle Skripte lagen außerhalb des Repos und sind mit der Sitzung verworfen.
Sie stehen hier vollständig, damit die Zahlen nachvollziehbar bleiben.

### 10.1 Keine freie Adresse an der Fabrik (§3.1)

`titiler.core==2.3.0` in ein Wegwerfverzeichnis installiert, dann:

```python
from typing import Annotated
from fastapi import FastAPI, Path, Query
from titiler.core.factory import TilerFactory

def DatasetItemAssetParams(
    dataset: Annotated[str, Path(description="dataset id from the registry")],
    item: Annotated[str, Path(description="item id at the source")],
    asset: Annotated[str, Query(description="asset key of the item")] = "visual",
) -> str:
    # stands in for: registry -> adapter -> gateway.check_url -> vsicurl_path
    return "/vsicurl/https://asset.example.org/x.tif"

cog = TilerFactory(path_dependency=DatasetItemAssetParams,
                   router_prefix="/tiles/{dataset}/{item}")
app = FastAPI()
app.include_router(cog.router, prefix="/tiles/{dataset}/{item}")

params = {(p["in"], p["name"])
          for ops in app.openapi()["paths"].values()
          for op in ops.values()
          for p in op.get("parameters", [])}
assert ("query", "url") not in params
```

### 10.2 Was die Pakete mitbringen (§3.2)

```bash
pip install --dry-run --report - 'titiler.core==2.3.0'
pip install --dry-run --report - 'titiler.mosaic==2.3.0'
pip install --dry-run --report - 'titiler.mosaic[mosaicjson]==2.3.0'
pip install --dry-run --report - 'titiler.xarray==2.3.0'
```

gegen das venv des Projekts (fastapi 0.141.1, starlette 1.6.0, pydantic 2.13.5,
rasterio 1.4.4, rio-tiler 9.4.6, morecantile 7.1.0, numpy 2.4.6). Und:

```bash
python -c "import sys; from rio_tiler.io.rasterio import Reader; print('httpx2' in sys.modules)"
# True
```

### 10.3 Kosten einer Kachel (§3.4)

Die Bytes sind die Summe der Byte-Ranges aus GDALs eigener Meldung. Kernstück:

```python
RANGE = re.compile(r"Downloading (\d+)-(\d+) ")

class Count(logging.Handler):
    def emit(self, record):
        for a, z in RANGE.findall(record.getMessage()):
            self.n += 1; self.b += int(z) - int(a) + 1

policy = Policy(allowed_hosts=frozenset({"e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com"}))
src = vsicurl_path(check_url(item["assets"]["visual"]["href"], policy))
with rasterio.Env(**gdal_options(policy), CPL_DEBUG="ON"):
    with Reader(src) as r:
        img = r.tile(t.x, t.y, t.z)
        png = img.render(img_format="PNG")
```

Kalte Zeilen: ein frischer Prozess je Messung. Warme Zeilen: ein Prozess, ein
`Reader`, 4×4 Kacheln um dieselbe Mitte; Kacheln außerhalb des Footprints
(`TileOutsideBounds`) zählen nicht mit. `statistics()` und `part()` laufen im
selben Gerüst.

### 10.4 Mosaik (§3.5)

```python
from rio_tiler.mosaic import mosaic_reader
from rio_tiler.errors import TileOutsideBounds

def read(src, x, y, z):
    with Reader(src) as r:
        return r.tile(x, y, z)

img, used = mosaic_reader(paths, read, t.x, t.y, t.z,
                          allowed_exceptions=(TileOutsideBounds,))
```

`paths` einmal über alle zehn Szenen des Aufnahmetags, einmal vorgefiltert:

```python
w, s, e, n = tms.bounds(t)
kept = [f for f in features
        if not (f["bbox"][2] < w or f["bbox"][0] > e
                or f["bbox"][3] < s or f["bbox"][1] > n)]
```

Die Suchen für die Item-Zahlen (die Rechtecke sind Messflächen, keine AOI eines
Nutzers):

```bash
curl -sS -X POST https://earth-search.aws.element84.com/v1/search \
  -H 'content-type: application/json' \
  -d '{"collections":["sentinel-2-c1-l2a"],
       "bbox":[8.4,47.3,8.6,47.5],
       "datetime":"2026-08-01T00:00:00Z/2026-09-01T00:00:00Z","limit":1}'
# numberMatched 19 ; dasselbe Rechteck über ein Jahr: 210
#                    bbox [5.9,45.8,10.5,47.8] über einen Monat: 404
```

### 10.5 CORS und Asset-Host (§3.6, §3.7)

```bash
BASE=https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com/sentinel-2-c1-l2a/37/S/GB/2026/9/S2B_T37SGB_20260920T080008_L2A

curl -sS -D - -o /dev/null -H 'Origin: https://example.org' -r 0-99 "$BASE/L2A_PVI.jpg"
curl -sS -D - -o /dev/null -X OPTIONS -H 'Origin: https://example.org' \
     -H 'Access-Control-Request-Method: GET' "$BASE/L2A_PVI.jpg"
curl -sS -D - -o /dev/null -H 'Origin: https://example.org' -r 0-99 "$BASE/TCI.tif"
# jeweils: Access-Control-Allow-Origin: *   Access-Control-Allow-Methods: HEAD, GET

curl -sS -D - -o /dev/null -H 'Origin: https://example.org' \
     https://earth-search.aws.element84.com/v1/
# access-control-allow-origin: *
```

Und die Zuordnung der Hosts, an echten Items:

```bash
for C in sentinel-2-c1-l2a sentinel-2-l2a; do
  curl -sS -X POST https://earth-search.aws.element84.com/v1/search \
    -H 'content-type: application/json' \
    -d "{\"collections\":[\"$C\"],\"limit\":1}" \
  | python3 -c "import json,sys; f=json.load(sys.stdin)['features'][0]; \
      print(f['id'], f['assets']['visual']['href'].split('/')[2])"
done
# sentinel-2-c1-l2a -> e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com
# sentinel-2-l2a    -> sentinel-cogs.s3.us-west-2.amazonaws.com
```
