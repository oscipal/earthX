# ADR 0007 — Zweites Format: Zarr

- **Status:** **Entwurf.** Die sieben Fragen in §8 sind offen; ohne Antwort auf
  F1 steht der zweite Datensatz nicht fest.
- **Datum:** 2026-09-20
- **Aufgabe:** M2-03 laut `docs/plans/m2-format-und-viewer.md` §4.
- **Autonomiestufe:** C — nur recherchiert, gemessen und berichtet. Kein
  Produktivcode geändert, keine Datei außerhalb von `docs/` angefasst, keine
  Abhängigkeit des Projekts verändert.
- **Grundlage:** `ENTSCHEIDUNGEN_2026-09-18.md` §2, §3; `KLAERUNGEN.md` B8, B9,
  B10, B11, B12, B13; `architekturplan.md` 3.1, 6.1, 6.2, 6.3, 6.5, 14 Punkt 5,
  15.1, 15.2; `adr/0003` §6, §10.1, §10.3, §11.2; `adr/0004` §5, §6 (Option 6,
  Regel V); `adr/0005` §3.3, Regeln I–VI; `projektuebersicht.md` §5;
  `cloud-umgebung.md` §6; Entscheidungslog-Zeilen vom 2026-09-19
  („STAC-Version und Lizenzwert sind aneinander gebunden") und vom 2026-09-20
  („M2-Schnitt").
- **Betroffen:** `architekturplan.md` 6.2, 14 Punkt 5; `cloud-umgebung.md` §6;
  Planung M2-05, M2-07c, M2-09, M2-10; Entscheidungslog.

---

## Methode und Belegstufen

Gearbeitet wurde in einer Cloud-Sitzung vom 20.09.2026. Belegstufen wie in
`adr/0004`:

- **M** — in dieser Sitzung selbst gemessen; der Befehl bzw. die Adresse steht
  im Text oder im Messanhang §11.
- **P** — am Primärdokument gelesen (Spezifikation, `pyproject.toml`,
  Quelltext, PyPI-Metadaten).
- **S** — Suchtreffer mit Link, Primärdokument nicht gelesen.
- **A** — eigene Ableitung aus M/P/S; als Argument gekennzeichnet, nicht als
  Beleg.

Wo ein Beleg fehlt, steht „unbelegt" statt einer Zahl. §9 listet, was offen
blieb.

**Umfang der Abrufe.** Rund 270 Anfragen über etwa 70 Minuten: STAC-Metadaten
(`/`, `/collections`, `/search`, `/queryables`) und Lesezugriffe auf **zwei**
Zarr-Stores — Metadatenobjekte und einzelne Chunks, zusammen rund 35 MB, davon
allein 4,55 MB für **ein** konsolidiertes Metadatenobjekt (§3.4). Es wurde kein
Produkt heruntergeladen. Für die Messung in §3.7 wurde `zarr`, `xarray` und
`rio-tiler[xarray]` in ein **Wegwerf-venv im Kratzverzeichnis** installiert;
`backend/requirements.txt` und das Projekt-venv blieben unberührt.

---

## 1. Kontext und Problem

`architekturplan.md` 6.2 stellt Zarr an Rang 1 der Format-Hierarchie und
verlangt einen `readers/zarr_reader.py` neben `cog.py`. `adr/0003` §6 hat
entschieden, COG zuerst zu nehmen und Zarr als **zweiten** Datensatz
nachzuziehen — als einzige ehrliche Probe darauf, ob Registry und Reader-Naht
tragen. Der M2-Schnitt vom 2026-09-20 macht daraus den Strang M2b und stellt das
Kandidatenfeld ausdrücklich wieder **offen**: EOPF Sentinel Zarr Samples ist
Kandidat, nicht gesetzt.

Zu entscheiden ist zweierlei, und beides hängt weniger zusammen, als es aussieht:

1. **Welcher Datensatz.** Token-frei, mit Zeitachse, mit tragfähiger Lizenz, in
   der Cloud-Sitzung erreichbar, und so beschaffen, dass Kacheln, Coverage und
   Zuschnitt daraus wirklich entstehen.
2. **Welcher Lesepfad.** Welche Bausteine `zarr_reader.py` benutzt, ohne die
   Gateway-Pflicht (B8) zu brechen.

Frage 2 ließ sich in dieser Sitzung **abschließend messen** (§3.7). Frage 1
nicht: Der Objektspeicher, auf dem die aktuellen EOPF-Produkte liegen, ist aus
dieser Umgebung gesperrt (§3.1). Dieser Teil ist deshalb, wie der Aufgabentext
verlangt, **angehalten**; §8 F1 legt ihn Otto vor.

---

## 2. Kriterien

| # | Kriterium | Warum |
|---|---|---|
| K1 | Token- und registrierungsfrei, auch für die Pixel | `ENTSCHEIDUNGEN` §1 |
| K2 | Lizenz erlaubt mindestens Anzeige, besser Processing | `KLAERUNGEN` B11 |
| K3 | Echte Zeitachse mit genug Aufnahmen | F5, F7, Coverage; sonst ist der Viewer nicht auszulasten |
| K4 | Metadaten **und** Assets aus der Cloud-Sitzung erreichbar | sonst ist nichts messbar und nichts vorführbar |
| K5 | STAC-API vorhanden | `architekturplan.md` 5.2; eine Nicht-STAC-Quelle ist Inkrement 3, nicht M2 |
| K6 | Jeder Byte-Read durch `gateway` zwingbar | `KLAERUNGEN` B8 |
| K7 | Kachelbar: georeferenziert, mit brauchbarer Übersichtsstufe | F10, Z4 |
| K8 | Lesekosten je Kachel vertretbar | Prinzip 10 der Projektübersicht |
| K9 | Dauerhaftigkeit: kein Dienst, der sich selbst als vorläufig bezeichnet | Onboarding-Checkliste, Punkt 10 |
| K10 | Quicklook oder ein belegter Ersatz | F6 |

---

## 3. Was gemessen wurde

### 3.1 Erreichbarkeit — und der gesperrte Teil — **[M]**

Erreichbar aus dieser Sitzung, HTTP 200:

| Host | Rolle | Ergebnis |
|---|---|---|
| `stac.core.eopf.eodc.eu` | STAC-API der EOPF Zarr Samples | 200, 15 Collections |
| `objects.eodc.eu` | Objektspeicher (Ceph RGW) | 200, Range-Reads (206) bestätigt |
| `zarr.eopf.copernicus.eu` | Projektseite, FAQ | 200 |
| `storage.googleapis.com` | ARCO-ERA5 | 200 |
| `cmip6-pds.s3.us-west-2.amazonaws.com` | CMIP6 Zarr | 200 |
| `mur-sst.s3.us-west-2.amazonaws.com` | MUR SST Zarr | 200 |
| `nex-gddp-cmip6.s3.us-west-2.amazonaws.com` | NEX-GDDP | 200 |
| `registry.opendata.aws` | AWS-Open-Data-Katalog | 200 |

**Gesperrt** (`CONNECT` mit HTTP 403, Proxy-Status `connect_rejected
(organization policy)`):

| Host | Wozu gebraucht |
|---|---|
| **`data.eodc.eu`** | **Der Objektspeicher, auf dem die aktuellen EOPF-Produkte liegen (§3.3). Ohne ihn ist Option A nicht messbar.** |
| `download.user.eopf.eodc.eu` | `zipped_product`-Assets derselben Items |
| `stac.eopf.copernicus.eu` | zweite Adresse derselben STAC-API |
| `stac.browser.user.eopf.eodc.eu` | nur Browser-Oberfläche |
| `cmr.earthdata.nasa.gov`, `zenodo.org`, `developmentseed.org`, `openveda.cloud`, `docs.source.coop` | Recherche weiterer Kandidaten |

> **Der angehaltene Teil.** `data.eodc.eu` ist die Adresse, unter der
> `sentinel-2-l2a-zarr3`, `sentinel-2-l1c-zarr3`, `sentinel-1-l1-grd` und alle
> Sentinel-3-Collections ihre Daten führen. Solange der Host gesperrt ist, sind
> für diese Collections **keine** Aussagen über Chunk-Aufbau, Georeferenzierung,
> Übersichtsstufen, Lesekosten oder auch nur die Existenz der Objekte möglich.
> Dieser ADR behauptet dazu nichts. §8 F1 legt die Freigabe vor; sie wirkt erst
> in einer **neu gestarteten** Sitzung (`adr/0003` §11.3).

**Nebenbefund, klärt `cloud-umgebung.md` §6.** Der dort als Widerspruch notierte
Befund ist keiner: `stac.eopf.copernicus.eu` (gesperrt, heute erneut bestätigt)
und `stac.core.eopf.eodc.eu` (offen) sind **zwei Adressen desselben Dienstes**.
Die Tabelle in §6 ist insoweit richtig und zugleich unvollständig — sie nennt
die gesperrte Adresse und nicht die offene. Vollständig wäre: STAC-API offen
über EODC, gesperrt über Copernicus; Objektspeicher offen für `objects.eodc.eu`,
gesperrt für `data.eodc.eu`.

### 3.2 Die STAC-API: 1.1-Items an einer 1.0-API, kein `numberMatched`, keine Aggregation — **[M]**

| Befund | Messung |
|---|---|
| Landing Page | `"stac_version": "1.0.0"`, `id: eopf-sample-service-stac-api`, Server `APISIX/3.7.0` |
| Collections | **15** (bestätigt die Korrektur aus `adr/0003` §10.3), jede mit `"stac_version": "1.1.0"` |
| Items | `"stac_version": "1.1.0"`, 15 `stac_extensions`, darunter `eo` **v2.0.0**, `projection` **v2.0.0**, `raster` **v2.0.0**, `zarr` **v1.1.0**, `mgrs`, `grid`, `processing`, `product`, `scientific` |
| `numberMatched` | **fehlt in jeder Antwort.** Die Suchantwort trägt nur `type`, `links`, `features`, `numberReturned` |
| Aggregation-Extension | `/aggregations` und `/aggregate` antworten **404**; die Landing Page weist sie nicht aus |
| `/queryables` | 200 |
| Paging | Keyset-Marke `token=next:<collection>:<item-id>` — dieselbe Bauart wie bei Earth Search (`adr/0005` §3.3) |
| Latenz `GET /search`, `limit=1` | 0,43–1,02 s (n≈25) |
| 10 parallele Anfragen | alle 200, 0,78–1,02 s, **kein** `429`, kein `Retry-After`, kein `X-RateLimit-*` |
| CORS | `access-control-allow-origin: *` auf `/collections` |
| Zwischenspeicher | **kein** `Cache-Control`, **kein** `ETag` (anders als Earth Search, `adr/0005` §3.4) |

Drei davon haben unmittelbare Folgen:

**`numberMatched` fehlt.** `adr/0004` Regel V verlangt die Vollständigkeitsprobe
`sum(Zellen) == total_count`; ohne Gesamtzahl ist sie nicht rechenbar. Der
Umschaltpunkt Dichte → Footprints aus dem Log vom 2026-09-19
(`numberMatched < 500`) ist an derselben Zahl aufgehängt und greift hier
ebenfalls nicht.

**Keine Aggregation.** Die Coverage dieses Datensatzes kann nur über die
**ausgewiesene Stichprobe** laufen (`adr/0004` §5, Option 6;
`CoverageProvider.SAMPLE` gibt es in der Registry schon). M2-05 hatte die
Stichprobe ausdrücklich zurückgestellt, „bis M2-09 sie braucht" — sie wird
gebraucht.

**Die Lizenzwerte passen nicht zur eigenen Versionsangabe.** Die Collections
melden `stac_version: 1.1.0` und tragen `license: "proprietary"` (Sentinel-1
und -2) bzw. `"other"` (Sentinel-3). STAC 1.1 kennt `proprietary` nicht mehr
(Log vom 2026-09-19). Die Quelle ist an dieser Stelle also selbst inkonsistent —
und sie ist es uneinheitlich zwischen ihren eigenen Collections.

### 3.3 Zwei Objektspeicher, nur einer offen — **[M]**

Die Asset-Adressen zeigen nicht dorthin, wo `adr/0003` §10.1 gemessen hat:

| Collection | Asset-Host | erreichbar |
|---|---|---|
| `sentinel-2-l2a-zarr3`, `sentinel-2-l1c-zarr3`, `sentinel-1-l1-grd`, alle Sentinel-3 | `data.eodc.eu` | **nein** |
| `sentinel-1-l1-slc-zarr3` | `objects.eodc.eu` | ja |
| `sentinel-2-l2a` (ältere Items, z. B. 2017) | `objects.eodc.eu` | ja |
| `sentinel-2-l2a` (aktuelle Items, z. B. 19.09.2026) | `data.eodc.eu` | **nein** |
| `zipped_product` überall | `download.user.eopf.eodc.eu` | **nein** |

Das ist derselbe Prüfpunkt, den D5 für den COG-Pfad aufgemacht hat, nur für
Zarr: **Der Host in der Allowlist muss der Host aus den echten Items sein**, und
`objects.eodc.eu` aus `adr/0003` §10.1 ist für die interessanten Collections der
falsche.

**Die Collection `sentinel-2-l2a` ist gemischt.** Ihre reichweitenstarken
Items (2017-06 und 2024-06 belegt vorhanden) liegen unter
`objects.eodc.eu/.../notebook-data/tutorial_data/cpm_v262/` — also im
**Tutorial-Bereich**, nicht im Archiv. Die aktuellen Items desselben
Collection-Namens liegen unter `data.eodc.eu/collections/EOPF_ZARR/products/`.
Eine Suche über diese Collection liefert damit Items, deren Assets je nach Datum
auf verschiedenen Speichern liegen, von denen einer gesperrt ist.

**Tatsächliche Belegung, gemessen über Monatsfenster** (`numberReturned` bei
`limit=1`, weil es kein `numberMatched` gibt):

| Collection | 2017-06 | 2024-06 | 2026-03 | 2026-05 | 2026-06 | 2026-07 | 2026-08 | 2026-09 |
|---|---|---|---|---|---|---|---|---|
| `sentinel-2-l2a` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `sentinel-2-l2a-zarr3` | — | — | — | — | — | ✓ | ✓ | ✓ |
| `sentinel-1-l1-slc-zarr3` | — | — | — | — | — | ✓ | — | — |

Das **korrigiert** `adr/0003` §10.3 in eine Richtung und schärft es in der
anderen: Die Aussage „rund drei Monate rollierend" trifft auf
`sentinel-2-l2a-zarr3` zu (Bestand ab 2026-07-16, das sind gut zwei Monate), auf
`sentinel-2-l2a` dagegen nicht — dort reichen die Item-**Metadaten** bis 2017
zurück. Ob die zugehörigen **Objekte** noch existieren, ist für alles außer den
Tutorial-Produkten nicht prüfbar, weil ihr Host gesperrt ist.

### 3.4 Kein `multiscales`, keine CRS im Store — **[M]**

Geprüft an den beiden Stores, die erreichbar sind:

| Store | Format | `multiscales` | CRS im Store | Metadatengröße |
|---|---|---|---|---|
| S2 L2A Tutorial-Produkt (`.zmetadata`) | Zarr **v2**, konsolidiert | **0 Treffer** | **keine** — kein `grid_mapping`, kein `spatial_ref`, kein `crs_wkt` | 286 kB, 312 Schlüssel, 124 Arrays, 1,18 s |
| S1 SLC GeoZarr (`zarr.json`) | Zarr **v3**, konsolidiert | **0 Treffer** | keine | **4,55 MB**, 1027 Knoten, 1,46 s |

Zwei Dinge folgen daraus:

**Die Georeferenzierung kommt aus STAC, nicht aus dem Store.** Der Store führt
`x`- und `y`-Koordinatenarrays (gemessen: `x[0]=600030.0`,
`y[0]=5699970.0` — UTM-Meter), aber nirgends, in welchem Bezugssystem. Das
`proj:code` steht nur im STAC-Item (`EPSG:32632` bzw. `EPSG:32626`). Ein
`zarr_reader.py` muss die CRS also **von außen** gesetzt bekommen. Das ist kein
Schönheitsfehler, sondern eine Naht: Der Reader hängt damit am Katalog, und die
Registry muss sagen, aus welchem Feld sie kommt.

**Es gibt keine Bildpyramide — aber einen Ersatz.** Statt GeoZarr-`multiscales`
führt das EOPF-Produkt die Bänder in **drei Auflösungsgruppen** (`r10m`, `r20m`,
`r60m`) mit gleichem Ausschnitt. Das ist faktisch eine dreistufige Pyramide, nur
ohne die Konvention, die ein generischer Leser dafür lesen würde. Der Reader muss
die Stufenwahl deshalb selbst treffen, aus Zoomstufe und `gsd`/
`raster:spatial_resolution` des Assets (beide im Item vorhanden).

Zur Einordnung: Die `multiscales`-Konvention ist derzeit **Pilot v0.1** mit
angekündigten Breaking Changes bis v1 (Ende 2026 avisiert); die GeoZarr-Spec
selbst ist Entwurf in einer SWG bei `zarr-developers`. **[P]** für das
`multiscales`-README, **[S]** für den OGC-Fahrplan. Auf eine Konvention in
diesem Zustand jetzt eine Kachelstufe zu gründen, wäre verfrüht — dass die
gemessenen Produkte sie ohnehin nicht führen, nimmt die Frage vorerst ab.

**Nebenbefund zur Datenqualität.** Das ältere `sentinel-2-l2a`-Item trägt
`proj:code: EPSG:32632` und dazu ein `proj:bbox` in **Grad**
(`[10.4087, 50.4459, 11.2042, 51.2097]`); das neuere `sentinel-2-l2a-zarr3`-Item
trägt `proj:bbox` korrekt in Metern (`[399960.0, 7890240.0, …]`). Ein Leser, der
`proj:bbox` ungeprüft als projizierte Box nimmt, rechnet beim älteren Bestand
still falsch.

### 3.5 Der Quicklook, den der Katalog ausweist und der Speicher nicht hat — **[M]**

`adr/0003` §10.3 hatte belegt, dass die drei damals geprüften Collections kein
Thumbnail führen. Vollständig über alle 15 Collections geprüft, ist das Bild
etwas anders und im Ergebnis schlechter:

- **12 von 15** Collections führen kein Asset mit `thumbnail`-, `preview`-,
  `overview`- oder `visual`-Rolle. Auch `roles` enthält nirgends `thumbnail` oder
  `overview` — nur `data`, `metadata`, `dataset`, `reflectance`, `mask`,
  `atmosphere`, `archive`.
- `sentinel-2-l2a` und `sentinel-2-l1c` führen `TCI_10m` (True-Colour-Bild),
  `sentinel-3-olci-l2-*` führen `otci`. Das sind Daten-Arrays, keine Bilder.
- **Und `TCI_10m` löst nicht auf.** Das Item zeigt auf
  `…/quality/l2a_quicklook/r10m/tci`; die konsolidierten Metadaten des Stores
  enthalten **keine Gruppe `l2a_quicklook`**, und ein direkter Abruf von
  `…/l2a_quicklook/r10m/tci/.zarray` antwortet **404**.

Für F6 heißt das: Es gibt keinen Quicklook, auch dort nicht, wo der Katalog
einen verspricht. Der Ersatz muss aus dem Kachelpfad kommen — eine kleine
Vorschau aus der gröbsten Auflösungsstufe, gerendert wie eine Kachel (§3.7 zeigt,
dass das geht: 32,8 kB PNG). Das ist teurer als ein fertiges JPEG und muss
zwischengespeichert werden.

### 3.6 Was eine Kachel wirklich kostet — **[M]**

Am erreichbaren S2-Tutorial-Produkt, Band `b04`:

| | `r10m` | `r60m` |
|---|---|---|
| Array | 10980 × 10980, `uint16` | 1830 × 1830, `uint16` |
| Chunk | 1830 × 1830 = **6,70 MB** unkomprimiert | 305 × 305 = **186 kB** unkomprimiert |
| Chunk komprimiert (blosc/zstd), belegt | **3,09–4,09 MB** | 103–133 kB |
| Chunk komprimiert, leer | 1 573 B | 74 B |
| Zeit je Chunk | 1,30–2,48 s | 0,48–0,81 s |

Und derselbe 256×256-Ausschnitt über beide Stufen gelesen:

| Ausschnitt | Chunk-Requests | übertragen | Zeit |
|---|---|---|---|
| 256×256 bei 60 m | 4 | **539 kB** | 4,17 s |
| 256×256 bei 10 m | 3 | **4,09 MB** | 2,99 s |

Zum Vergleich: Ein COG-Overview-Read für dieselbe Kachel liegt bei Zehnern von
Kilobyte (`adr/0003` §10.1 hat den Header-Read mit 32 KiB gemessen).

**Die Zahl, die hängen bleibt: eine einzige Web-Mercator-Kachel in nativer
Auflösung kostet hier 3–16 MB von der Quelle und mehrere Sekunden.** Der Grund
ist nicht das Netz, sondern der Zuschnitt: Ein 1830er Chunk ist rund 50-mal
breiter als eine Kachel, also wird für jede Kachel das Fünfzigfache gelesen und
weggeworfen. Dazu kommt ein Latenzsockel von **rund 0,5 s je Objekt**, auch für
ein 74-Byte-Objekt — der gilt gemessen durch den Sitzungs-Proxy und ist damit
eine Obergrenze, kein Betriebswert **[A]**.

Für Prinzip 10 („Rücksicht auf die Quellen") und für Z4 folgt daraus dreierlei:
Kacheln aus Zarr brauchen einen HTTP-Cache härter als COG-Kacheln; die gröbste
Stufe ist der Normalfall und die feinste die Ausnahme; und die Statistik für den
Streckbereich darf nur **einmal** je Item laufen (§3.7: 0,81 s auf der
60-m-Stufe), nicht je Kachel.

### 3.7 Der Lesepfad trägt — und er lässt sich an `gateway` binden — **[M]**

Das ist der zentrale Befund dieses ADR, und er ist vollständig durchgemessen.

`zarr-python` 3 kennt eine abstrakte Basisklasse `zarr.abc.store.Store` (async:
`get`, `get_partial_values`, `exists`, `list*`). Wer sie implementiert, bekommt
**jeden einzelnen Byte-Read** in eigenen Code. Gemessen wurde eine
Wegwerf-Implementierung, die statt `fsspec` oder `obstore` schlicht `urllib`
benutzt und dabei Requests und Bytes zählt — an genau dieser Stelle stünde im
Produktivcode `gateway`:

```
open_array (r60m/b04)          1,4 s     2 Requests    1,1 kB
256×256-Fenster bei 60 m       4,2 s     4 Chunks    539 kB   Werte 1055–9702
256×256-Fenster bei 10 m       3,0 s     3 Requests  4,09 MB  Werte 1104–4228
```

Darauf aufgesetzt die ganze Kette bis zum Bild:

```
Koordinaten + Array geöffnet   5,2 s     8 Requests   12,5 kB
DataArray (volle 60-m-Stufe)  27,1 s    36 Chunks     1,40 MB
CRS aus STAC proj:code gesetzt (EPSG:32632), nicht aus dem Store
bounds (WGS84)                [10.4087, 50.4263, 12.0170, 51.4424]
Kachel z11/1087/686            0,02 s     0 Requests   256×256, PNG 32 819 B
statistics()                   0,81 s                min 0, max 12201, p2 0, p98 3650
GESAMT                                   44 Requests   1,42 MB
```

Benutzt wurden: eigener `Store` → `zarr` 3.1.6 → `xarray` 2026.7.0 →
`rioxarray` 0.19.0 (nur für `write_crs`) → `rio_tiler.io.xarray.XarrayReader`
9.4.6. **`rio-tiler` ist bereits Abhängigkeit des Projekts**, und sein
`XarrayReader` macht **kein eigenes I/O** — er arbeitet auf einem schon
geöffneten `DataArray` **[P]**. `tile()`, `statistics()` und `feature()` decken
damit genau die drei Aufgaben ab, die M2-09 verlangt: Kachel, Statistik,
AOI-Zuschnitt. Und sie tun es mit derselben Bibliothek, auf der `cog.py` steht —
die Naht zwischen den beiden Readern wird dadurch schmal.

Die 27,1 s für den `DataArray`-Bau sind ein Artefakt der Messung: Sie liest die
**ganze** 60-m-Stufe in 36 nacheinander abgerufenen Chunks. Produktiv wird
fensterweise und nebenläufig gelesen; die belastbaren Zahlen dafür stehen in
§3.6.

### 3.8 Python 3.11 deckelt den Zarr-Stapel — **[M]/[P]**

| Baustein | Stand | Python |
|---|---|---|
| `zarr` 3.1.6 | letzte Version für Python 3.11 | `>=3.11` **[P]** |
| `zarr` 3.2.0 und neuer (bis 3.4.0) | | **`>=3.12`** **[P]** |
| `titiler.eopf` 0.11.0 | nicht auf PyPI, nur `main`, kein Release-Tag | **`>=3.12,<3.14`**, dazu `zarr[cast-value-rs]>=3.2.0` und `obstore` **[P]** |
| `titiler.xarray` 2.3.0 | MIT, Teil des TiTiler-Monorepos | `>=3.11`, benutzt `obstore` bzw. `fsspec` **[P]/[S]** |
| `xarray` 2026.7.0, `rio-tiler` 9.4.6, `rioxarray` 0.19.0 | | `>=3.11` **[P]** |

CI und Live-Smoke pinnen `PYTHON_VERSION: "3.11"`; die Cloud-Sitzung liefert
3.11.15 als `python3` **[M]**. Damit gilt:

- **`titiler-eopf` scheidet für M2 aus** — es ist unter Python 3.11 nicht
  installierbar, es hat keine Release-Version, und es brächte mit `obstore`
  einen zweiten HTTP-Stapel an `gateway` vorbei. Drei Ausschlussgründe, von
  denen jeder einzelne reichen würde.
- `zarr` wäre auf `3.1.x` zu pinnen — eine Version, die keine Fehlerbehebungen
  mehr bekommt, sobald die 3.2er-Reihe läuft.
- Ein Wechsel auf Python 3.12 ist möglich: Ubuntu 24.04 bringt `python3.12`
  mit, in dieser Sitzung als `/usr/bin/python3.12` (3.12.3) vorhanden **[M]** —
  die Sitzung benutzt es nur nicht. Das ist eine eigene Entscheidung mit
  eigenem Risiko (alle Wheels neu, `pypgstac` und `stac-fastapi.pgstac` sind
  gepinnt) und gehört nicht nebenbei in M2-09. §8 F5.

### 3.9 Lizenz, Zitierung, Ratengrenzen, CORS — **[M]**

- **Lizenz.** Collection- und Item-Link `license` zeigen auf
  `https://sentinel.esa.int/documents/247904/690755/Sentinel_Data_Legal_Notice`
  — **dasselbe Legal Notice**, das `adr/0003` §11.2 für Sentinel-2 L2A am
  Primärdokument geprüft hat und das der bestehende Registry-Eintrag samt
  `terms_notice` schon trägt. `providers` nennt die Europäische Kommission als
  `licensor`, ESA als `producer`/`processor`, den EOPF-Dienst als `host`.
- **Zitierung.** `sci:doi` = `10.5270/S2_-znk9xsj`, dazu ein `cite-as`-Link auf
  `doi.org`. Checklistenpunkt 3 ist damit erfüllbar.
- **Ratengrenzen.** 10 parallele Anfragen ohne Drosselung, in rund 90 Anfragen
  kein `429`. Keine dokumentierte Grenze gefunden — die offene Log-Zeile
  „Ratengrenzen der Anbieter" bleibt für EOPF **sachlich unbeantwortet**; der
  Deckel von 6 parallelen Verbindungen je Host aus `gateway` trägt weiter.
- **CORS** (beantwortet `architekturplan.md` 14 Punkt 5): Die **STAC-API**
  sendet `access-control-allow-origin: *`. Der **Objektspeicher** sendet
  **keinen** CORS-Header, auch nicht mit `Origin`-Kopfzeile, und beantwortet
  einen `OPTIONS`-Preflight mit **403**. Ein Browser kann die Zarr-Chunks also
  nicht selbst lesen. Für uns ändert das nichts — wir kacheln serverseitig —,
  aber der Spike „Rendering im Browser" aus `architekturplan.md` 15.1
  Inkrement 7 ist gegen diese Quelle nicht durchführbar.

---

## 4. Kandidatenfeld

### 4.1 Die EOPF-Collections, einzeln beurteilt

| Collection | Format | Asset-Host | Bestand | kachelbar? | Urteil |
|---|---|---|---|---|---|
| `sentinel-2-l2a-zarr3` | Zarr v3 | **gesperrt** | ab 2026-07-16 | **nicht prüfbar** | fachlich der naheliegende Kandidat, heute nicht messbar |
| `sentinel-2-l1c-zarr3` | Zarr v3 | **gesperrt** | ab 2026-07-21 | nicht prüfbar | wie oben, L1C statt L2A |
| `sentinel-2-l2a` | Zarr v2 | **gemischt** | Metadaten ab 2017 | teils | die reichweitenstarken Items sind Tutorial-Produkte (§3.3) |
| `sentinel-1-l1-slc-zarr3` | Zarr v3 | `objects.eodc.eu` ✓ | ein Datentake im Juli 2026 | **nein** | Radargeometrie (`azimuth_time` × `slant_range_time`), `complex64`, keine CRS — ohne Geokodierung keine Karte |
| `sentinel-1-l1-grd`, alle Sentinel-3 | Zarr v2 | **gesperrt** | — | nicht prüfbar | — |

Der bittere Teil dieser Tabelle: **Die einzige Collection, deren Daten heute
erreichbar sind, ist die einzige, die sich grundsätzlich nicht kacheln lässt.**

Zu `sentinel-1-l1-slc-zarr3` noch ein Randbefund zu `ENTSCHEIDUNGEN` §3: Die
Variable `slc` hat `cube:dimensions.polarization.values = ["VV", "VH"]` — also
Dual-Pol, wie dort angenommen. `decomp.py` bleibt ruhender Operator; diese Quelle
ändert daran nichts.

### 4.2 Weitere token-freie Zarr-Quellen

Gesucht wurde ausdrücklich breiter als EOPF. Was sich belegen ließ:

| Kandidat | Daten-Host | erreichbar | Lizenz | STAC | Zeitachse | Belegstufe |
|---|---|---|---|---|---|---|
| **ARCO-ERA5** (Google Research / ECMWF) | `storage.googleapis.com/gcp-public-data-arco-era5` | **ja [M]** | Code Apache-2.0 **[P]**; Daten CC-BY seit 07/2025 **[S]**, für diese Kopie nicht bestätigt | **nein** | 1940-01-01 bis 2026-06-30, `last_updated` **heute** **[M]** | [P]/[S]/[M] |
| **CMIP6-PDS** (ESGF/Pangeo, AWS ODR) | `cmip6-pds.s3.us-west-2.amazonaws.com` | **ja [M]** | Lizenzseite nicht abrufbar, **unbelegt** | nein (Intake-ESM) | lang | [P]/unbelegt |
| **MUR SST** (PO.DAAC / Farallon, AWS ODR) | `mur-sst.s3.us-west-2.amazonaws.com` | **ja [M]** | „no restrictions" **[P]** | nein | 2002–2020 **[P]** | [P]/[M] |
| **NOAA NWM Retrospective** | `noaa-nwm-retrospective-2-1-zarr-pds` | nicht geprüft | „no restrictions" **[S]** | nein | lang, stündlich | [S] |
| **Earthmover ERA5** | `earthmover-icechunk-era5` | nicht geprüft | CC-BY 4.0 **[P]** | nein | 1940–2025 | [P] |
| **VEDA (NASA)** | `openveda.cloud` | **nein**, gesperrt | unbelegt | ja, STAC 1.0.0 **[S]** | je Collection | [S] |
| **Planetary Computer** | — | gesperrt | — | ja | ja | **scheidet aus:** SAS-Signatur je Zugriff **[S]**, `adr/0003` §6 |
| **NEX-GDDP-CMIP6** | `nex-gddp-cmip6.s3…` | ja [M] | — | — | — | **scheidet aus:** nativ NetCDF/COG, Zarr nur virtuell **[S]** |

Der gemeinsame Bruch aller Alternativen: **Keine davon hat eine STAC-API**
(K5 verletzt), und keine ist optische Erdbeobachtung. Sie sind Klima-,
Ozean- und Hydrologie-Gitter — global, in einem Raster, ohne Szenen und ohne
Footprints. Ein solcher Datensatz wäre für die Plattform kein zweites Format
neben Sentinel-2, sondern gleichzeitig die **erste Nicht-STAC-Quelle**, die
`architekturplan.md` 15.1 als Inkrement **3** führt, nach M2. Er brächte einen
Adapter mit Discovery und materialisierten Items, eine Coverage ohne Footprints
und eine Zeitachse, die eine Dimension im Würfel ist statt eine Eigenschaft von
Items. Das ist eine eigene Milestone-Menge Arbeit, keine Variante von M2-09.

Ausgenommen davon ist nichts an ihrer Qualität: ARCO-ERA5 ist die am besten
gepflegte Zarr-Zeitreihe im Feld (Aktualisierung am Messtag), und für Inkrement 3
ist sie ein starker Kandidat. Für M2 ist sie der falsche.

---

## 5. Optionen

**Option A — EOPF `sentinel-2-l2a-zarr3`, nach Freigabe von `data.eodc.eu`.**
*Für:* STAC-API vorhanden, Lizenz dieselbe wie beim ersten Datensatz und schon
geprüft, DOI vorhanden, MGRS-Gruppierungsschlüssel wie bei Sentinel-2, Zarr v3
mit echten Bändern. Der Viewer bekommt dieselbe Bedienung über zwei Formate —
genau die Probe, für die M2b da ist.
*Gegen:* Heute **nicht messbar**. Bestand gut zwei Monate. Kein Quicklook. Keine
Aggregation und kein `numberMatched`. Der Betreiber bezeichnet die Buckets
selbst als „unofficial" mit „unknown" Zukunft (`adr/0003` §10.3) — K9 ist
verletzt, und daran ändert eine Freigabe nichts.

**Option B — EOPF `sentinel-2-l2a` (Zarr v2), ohne Freigabe.**
*Für:* Ein Teil der Items ist heute vollständig lesbar, und an genau diesen
Produkten ist §3.6 und §3.7 gemessen.
*Gegen:* Gemischte Asset-Hosts in **einer** Collection (§3.3). Der erreichbare
Teil sind Tutorial-Produkte unter `notebook-data/tutorial_data/` — ein Pfad, der
keine Zusage trägt. Eine Suche lieferte Items, deren Anzeige je nach Datum
funktioniert oder nicht. Das ist gegenüber dem Nutzer nicht ehrlich darstellbar.

**Option C — Eine Nicht-STAC-Zarr-Quelle (ARCO-ERA5, CMIP6, MUR SST).**
*Für:* Erreichbar, token-frei, sehr lange Zeitachse, teils klare Lizenz.
*Gegen:* Verletzt K5 und zieht Inkrement 3 in M2 vor (§4.2). Lizenz bei CMIP6
unbelegt, bei ARCO-ERA5 für die konkrete Kopie nicht bestätigt.

**Option D — Zarr-Lesepfad in M2, zweiter Datensatz später.**
M2-09 wird geteilt: `zarr_reader.py`, der gateway-gebundene `Store`, der
Format-Dispatch über `DataFormat.ZARR` und die Kachelroute entstehen **gegen ein
synthetisches Mini-Zarr** (Skript erzeugt es, wie M2-09 es ohnehin für Fixtures
vorsieht). Der reale zweite Datensatz kommt, sobald F1 beantwortet ist.
*Für:* Nichts davon hängt an der Quellenwahl — §3.7 hat den ganzen Pfad
gemessen. Die Arbeit ist sofort machbar, prüfbar und nicht verloren, egal wie F1
ausgeht.
*Gegen:* Abnahmekriterium 1 von M2 („zwei Datensätze in zwei Formaten im selben
Viewer") ist damit allein nicht erfüllt.

**Option E — Zarr in M2 fallenlassen, stattdessen Copernicus DEM GLO-30 als
zweiten Datensatz.** Erreichbar, Lizenz nach B11 am Primärdokument geprüft
(`adr/0003` §11.1), COG.
*Gegen:* Kein zweites **Format**. Der Zweck von M2b entfällt; die Format-Naht
bleibt ungeprüft. D wäre als **dritter** Datensatz gedacht, für den Fall
„Einmal-Produkt".

---

## 6. Empfehlung

**D sofort, A danach — und A nur, wenn F1 mit „freigeben" beantwortet wird.**

1. **M2-09 in zwei Teile schneiden.** **M2-09a** baut den Lesepfad gegen ein
   synthetisches Mini-Zarr und ist von der Quellenwahl unabhängig; es kann
   sofort starten. **M2-09b** nimmt den realen Datensatz auf und wartet auf F1.
   Entsprechend hängt **M2-10** an 09b, nicht an 09a.

2. **Der Lesepfad steht fest, unabhängig von F1** (gemessen in §3.7):

   - **Ein eigener `zarr.abc.store.Store` in `readers`, der jeden `get` durch
     `gateway` schickt.** Kein `fsspec`, kein `obstore`, keine zweite
     HTTP-Bibliothek. Das ist die einzige Bauform, die B8 nicht nur behauptet,
     sondern erzwingt, und `.importlinter` kann sie prüfen, weil dann außerhalb
     von `gateway` kein HTTP-Paket mehr importiert wird.
   - `zarr` + `xarray` zum Öffnen, `rio_tiler.io.xarray.XarrayReader` für
     Kachel, Statistik und Zuschnitt. `rio-tiler` ist schon da und macht kein
     eigenes I/O.
   - **`titiler-eopf` nicht** (§3.8: Python 3.12, `zarr>=3.2`, `obstore`, kein
     Release).
   - **CRS aus dem STAC-Item** (`proj:code`), nicht aus dem Store; `proj:bbox`
     nur benutzen, wenn es zur CRS passt (§3.4).
   - **Stufenwahl aus `gsd`/`raster:spatial_resolution`** der Assets, nicht aus
     `multiscales` — die Konvention ist Pilot v0.1 und in den gemessenen
     Produkten nicht vorhanden.

3. **Coverage dieses Datensatzes ist `CoverageProvider.SAMPLE`.** Ohne
   Aggregation und ohne `numberMatched` bleibt nur die ausgewiesene Stichprobe
   (`adr/0004` Option 6). Sie muss in M2 gebaut werden, nicht später; M2-05
   hatte sie auf „falls M2-09 sie braucht" gestellt, und M2-09 braucht sie. Der
   Umschaltpunkt Dichte → Footprints braucht eine Ersatzregel, weil
   `numberMatched < 500` hier nicht auswertbar ist (Vorschlag: die Stichprobe
   selbst meldet, ob sie unter ihrem Deckel geblieben ist).

4. **STAC 1.1 an unserer 1.0-API: im Adapter normalisieren.** Unsere API liefert
   `stac_version: "1.0.0"`, und der Lizenzwert wird daraus abgeleitet (Log vom
   2026-09-19). `federating_client.py` reicht Items heute bis auf die Links
   unverändert durch — ein EOPF-Item ginge also mit `stac_version: "1.1.0"` und
   1.1-Erweiterungen aus einer 1.0-API heraus. Der Adapter soll das
   **geradeziehen**, und zwar minimal und benannt: `stac_version` auf `1.0.0`,
   `license` nach unserer Ableitungsregel, `bands` → `eo:bands`,
   `proj:code` → `proj:epsg` (nur bei `EPSG:`-Präfix), 1.1er
   Erweiterungs-URLs auf die 1.0er Fassungen. Was nicht abbildbar ist, bleibt
   stehen, statt still verfälscht zu werden.

5. **Quicklook-Ersatz** (F6): eine gerenderte Vorschau aus der gröbsten
   Auflösungsstufe über denselben Kachelpfad, im Anwendungs-Cache (E4)
   abgelegt. Ein fertiges Bild gibt es nicht, auch nicht dort, wo der Katalog
   eines ausweist (§3.5).

**Was das für die Abnahme von M2 bedeutet.** Wird F1 abschlägig beantwortet oder
trägt A nach der Nachmessung nicht, ist Abnahmekriterium 1 in M2 nicht
erreichbar; Kriterium 1 wäre dann neu zu fassen (Vorschlag in §8 F7). M2a bleibt
davon vollständig unberührt und ist eigenständig abnehmbar.

---

## 7. Folgen

1. `architekturplan.md` 6.2 nennt „Bausteine aus titiler-xarray bzw. TiTiler-EOPF
   prüfen" — geprüft, Ergebnis negativ für TiTiler-EOPF (§3.8). Die Zeile ist
   nachzuziehen.
2. `architekturplan.md` 14 Punkt 5 („Sendet der EOPF-Zarr-Dienst CORS-Header?")
   ist beantwortet: STAC-API ja, Objektspeicher nein (§3.9).
3. `cloud-umgebung.md` §6 ist um die drei EODC-Hosts zu ergänzen, mit der
   Auflösung aus §3.1. M2-00 nennt den Widerspruch; die Auflösung steht hier.
4. M2-05 bekommt die ausgewiesene Stichprobe zurück in den Umfang (§6 Punkt 3).
5. M2-07c braucht eine Ersatzregel für den Umschaltpunkt.
6. M2-09 wird in 09a und 09b geteilt; M2-10 hängt an 09b.
7. Der Registry-Eintrag des zweiten Datensatzes braucht ein Feld, aus dem der
   Reader die CRS-Herkunft liest, und eines für die Auflösungsstufen. Beides
   gibt es heute nicht; `DataFormat.ZARR` und `CoverageProvider.SAMPLE` gibt es
   schon.
8. Die offene Log-Zeile „Ratengrenzen der Anbieter" bleibt für EOPF offen: keine
   Drosselung beobachtet, keine Grenze dokumentiert (§3.9).

---

## 8. Fragen an Otto

**F1 — `data.eodc.eu` freigeben?** Ohne diesen Host ist der fachlich
naheliegende zweite Datensatz (`sentinel-2-l2a-zarr3`) weder messbar noch
benutzbar (§3.1, §3.3). Mit der Freigabe kämen sinnvollerweise auch
`download.user.eopf.eodc.eu` (`zipped_product`) dazu.
(a) **Beide freigeben**, dann in einer **neuen** Sitzung nachmessen (Chunk-Aufbau,
Georeferenzierung, Lesekosten) und erst danach über A entscheiden. *Empfehlung.*
(b) Nur `data.eodc.eu`.
(c) Nicht freigeben — dann ist A vom Tisch und F7 greift.

**F2 — M2-09 teilen?** (a) **Ja**, 09a (Reader + synthetisches Zarr, sofort) und
09b (realer Datensatz, nach F1). *Empfehlung.* (b) Nein, M2-09 wartet
vollständig auf F1.

**F3 — Lizenzeinstufung des EOPF-Bestands nach B11.** Die Quelle verweist auf
**dasselbe** Sentinel Data Legal Notice wie Sentinel-2 L2A bei Earth Search, das
`adr/0003` §11.2 am Primärdokument geprüft hat und das im bestehenden
Registry-Eintrag samt `terms_notice` liegt. Vorschlag, keine Entscheidung:
(a) **Stufe Processing**, identisch zum ersten Datensatz, Texte wiederverwenden.
*Empfehlung.* (b) Erneut am Primärdokument prüfen. Die Einstufung bleibt
ausdrücklich Otto vorbehalten.

**F4 — Normalisierung von STAC 1.1 nach 1.0 (§6 Punkt 4).**
(a) **Im Adapter normalisieren**, mit der benannten Feldliste. *Empfehlung.*
(b) Unverändert durchreichen und die Uneinheitlichkeit in Kauf nehmen.
(c) Unsere API auf STAC 1.1 heben — eigene Aufgabe, nicht M2.

**F5 — Python 3.11 oder 3.12?** Unter 3.11 ist `zarr` auf `3.1.x` festgenagelt
(§3.8).
(a) **Bei 3.11 bleiben**, `zarr` auf `3.1.x` pinnen, Wechsel als eigene Aufgabe
nach M2 vormerken. *Empfehlung* — ein Interpreterwechsel mitten in M2 riskiert
den ganzen gepinnten Stapel.
(b) Jetzt auf 3.12 heben, als eigener PR vor M2-09a.

**F6 — Größe des synthetischen Mini-Zarr.** Damit es echte Fälle trifft, sollte
es beide Formatversionen und mehrere Auflösungsstufen abdecken.
(a) **Zarr v2 und v3, je drei Stufen, wenige hundert Pixel je Kante, per Skript
erzeugt.** *Empfehlung.* (b) Nur v3. (c) Nur eine Stufe.

**F7 — Was, wenn kein Kandidat trägt?** Falls F1 (c) oder die Nachmessung A
verwirft:
(a) **M2 liefert den Zarr-Lesepfad mit synthetischen Daten**, Abnahmekriterium 1
wird auf „ein Datensatz im Viewer, zweites Format am Reader nachgewiesen"
gefasst; der reale Zweitdatensatz wird ein Punkt für M3. *Empfehlung.*
(b) Eine Nicht-STAC-Quelle (ARCO-ERA5) aufnehmen und damit Inkrement 3 in M2
vorziehen.
(c) Copernicus DEM GLO-30 als zweiten Datensatz nehmen und auf das zweite
Format in M2 verzichten.

---

## 9. Was offen blieb

1. **Alles zu `sentinel-2-l2a-zarr3` jenseits der Metadaten** — Host gesperrt
   (§3.1). Chunk-Zuschnitt, Georeferenzierung, Lesekosten, Existenz der Objekte:
   **unbelegt**, und dieser ADR behauptet dazu nichts.
2. **Ob die 2017er Item-Metadaten von `sentinel-2-l2a` auf existierende Objekte
   zeigen** — außer bei den Tutorial-Produkten nicht prüfbar.
3. **Ratengrenzen von EODC** — keine dokumentierte Grenze gefunden, keine
   Drosselung bei 10 parallelen Anfragen beobachtet. Das ist kein Beleg für
   „keine Grenze".
4. **Lizenz der CMIP6-PDS-Kopie** — Lizenzseite nicht abrufbar.
5. **Ob ARCO-ERA5 für die konkrete Google-Kopie CC-BY ausweist** — nur die
   Code-Lizenz (Apache-2.0) ist am Primärdokument belegt.
6. **Ob `titiler.xarray` einen eigenen Store annimmt** statt ihn intern zu
   bauen — Quelltext über den Proxy nicht lesbar. Für die Empfehlung ohne
   Belang, weil §3.7 den Weg ohne titiler misst.
7. **VEDA (NASA)** als STAC-Quelle mit Zarr-Assets — Host gesperrt, deshalb
   weder aufgenommen noch verworfen.
8. **Der Latenzsockel von ~0,5 s je Objekt** ist durch den Sitzungs-Proxy
   gemessen und damit eine Obergrenze; der Betriebswert ist unbekannt.

---

## 10. Quellen

**Gemessen (M), Sitzung vom 20.09.2026, rund 270 Anfragen:**

- `https://stac.core.eopf.eodc.eu` — `/`, `/collections`, `/queryables`,
  `/search` (je Collection, mit `datetime`-Fenstern, `limit`, Paging-Marke),
  `/aggregations`, `/aggregate`
- `https://objects.eodc.eu` — `.zmetadata` und `zarr.json` zweier Stores,
  einzelne Chunks von `b04` in `r10m` und `r60m`, `HEAD`/`Range`-Verhalten,
  CORS mit `Origin` und `OPTIONS`
- Erreichbarkeitsproben: `data.eodc.eu`, `download.user.eopf.eodc.eu`,
  `stac.eopf.copernicus.eu`, `stac.browser.user.eopf.eodc.eu`,
  `storage.googleapis.com`, `cmip6-pds.s3…`, `mur-sst.s3…`,
  `nex-gddp-cmip6.s3…`, `cmr.earthdata.nasa.gov`, `zenodo.org`,
  `developmentseed.org`
- Lesepfad-Messung §3.7 im Wegwerf-venv: `zarr` 3.1.6, `xarray` 2026.7.0,
  `rioxarray` 0.19.0, `rio-tiler` 9.4.6, `numpy` 2.4.6

**Primärdokumente (P):**

- `EOPF-Explorer/titiler-eopf`, `pyproject.toml` (`main`) — Version 0.11.0,
  `requires-python >=3.12,<3.14`, `zarr[cast-value-rs]>=3.2.0`, `obstore`
- `developmentseed/titiler`, `src/titiler/xarray/pyproject.toml` (`main`)
- `zarr-developers/zarr-python`, `src/zarr/abc/store.py`,
  `src/zarr/storage/_fsspec.py` (`main`)
- `cogeotiff/rio-tiler`, `rio_tiler/io/xarray.py`, `CHANGES.md` (`main`)
- `zarr-conventions/multiscales`, `README.md` (`main`) — Pilot v0.1
- PyPI-Metadaten: `zarr`, `xarray`, `rio-tiler`, `rioxarray`, `odc-geo`,
  `xarray-eopf`, `titiler.xarray`, `kerchunk`, `virtualizarr`
- `registry.opendata.aws` — Einträge `mur`, `cmip6`, `earthmover-era5`
- `google-research/arco-era5`, `README.md`, `LICENSE`

**Suchtreffer (S):** `zarr-developers/geozarr-spec` und `geozarr.org` (Status
der Spezifikation, OGC-Fahrplan); `zarr.readthedocs.io` (konsolidierte Metadaten
in Zarr v3 sind experimentell und nicht Teil der Spezifikation);
CC-BY-Ablösung der „Licence to use Copernicus Products" zum 02.07.2025;
Planetary-Computer-SAS-Dokumentation.

**Im Repo:** `architekturplan.md` 3.1, 6.1, 6.2, 6.3, 6.5, 14, 15.1, 15.2;
`KLAERUNGEN.md` B8–B13; `adr/0003` §6, §10.1, §10.3, §11.2; `adr/0004` §5, §6;
`adr/0005` §3.3, §3.4; `cloud-umgebung.md` §6; `projektuebersicht.md` §5;
`backend/earthx/catalog/registry.py`; `backend/earthx/api/federating_client.py`;
`.github/workflows/ci.yml`.

---

## 11. Messanhang

### 11.1 Erreichbarkeit

```
curl -sS -o /dev/null -w "%{http_code}" --max-time 25 https://<host>/
```

`000` mit `curl: (56) CONNECT tunnel failed, response 403` bedeutet
Egress-Sperre, nicht Abwesenheit des Hosts; der Proxy meldet dazu
`connect_rejected (organization policy)`.

### 11.2 Belegung je Monat (§3.3)

```
curl -sS "https://stac.core.eopf.eodc.eu/search\
?collections=<id>&datetime=<start>%2F<ende>&limit=1"
```

Ausgewertet wird `numberReturned` (0 oder 1), weil die Antwort kein
`numberMatched` führt.

### 11.3 Chunk-Kosten (§3.6)

Store: `objects.eodc.eu/e05ab01a9d56408d82ac32d69a5aae2a:notebook-data/`
`tutorial_data/cpm_v262/S2B_MSIL2A_20170624T103019_N0500_R108_T32UPB_`
`20231016T214045.zarr`

```
curl -sS -o /dev/null -w "%{size_download} %{time_total}" \
  "<store>/measurements/reflectance/r10m/b04/2.<j>"     # j = 0..5
  "<store>/measurements/reflectance/r60m/b04/<i>.<j>"   # i,j = 0..2
```

`r10m/b04/2.{0,1,2}` (belegt): 4 088 191 / 3 979 025 / 3 086 056 Bytes bei
2,48 / 1,50 / 1,30 s. `r10m/b04/2.{3,4,5}` (leer): je 1 573 Bytes bei
0,47–0,57 s. `r60m/b04/2.{0,1,2}`: 132 849 / 133 297 / 103 149 Bytes bei
0,78–0,81 s.

### 11.4 Lesepfad (§3.7)

Wegwerf-venv im Kratzverzeichnis, `probe_store.py` und `probe_tile.py`. Der
`Store` implementiert `zarr.abc.store.Store` mit `get`, `get_partial_values`,
`exists` und zählt Requests und Bytes; `list*` bleibt bewusst unimplementiert
(`supports_listing = False`), deshalb wird mit `zarr.open_array(path=…)`
geöffnet statt über `open_group().arrays()`. Die Kachel ist
`WebMercatorQuad` z11/1087/686, ermittelt über `morecantile.tms.tile(11.2, 50.9, 11)`.
Beide Skripte sind nicht Teil des Repos.
