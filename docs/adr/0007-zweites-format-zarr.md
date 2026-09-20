# ADR 0007 — Zweites Format: Zarr

- **Status:** **Angenommen** von Otto am 2026-09-20. Die sieben Fragen aus §8
  sind dort beantwortet: **F1** `data.eodc.eu` wird freigegeben,
  `download.user.eopf.eodc.eu` nicht; **F2** M2-09 wird geteilt; **F3**
  Lizenzeinstufung wie beim ersten Datensatz, förmlich bestätigt; **F4** im
  Adapter normalisieren; **F5** Python bleibt 3.11, `zarr` auf 3.1.x; **F6**
  Mini-Zarr per Skript im Test; **F7** mit F1 gegenstandslos, bleibt als
  Rückfallweg stehen. §6 gibt den entschiedenen Stand wieder.
  **Nachgemessen am 2026-09-20 (M2-03b):** Die in §9.1 offen gebliebenen
  Aussagen über die bisher gesperrten Collections stehen jetzt in **§12**. Wo §12
  einer Aussage aus §3 bis §7 widerspricht, gilt §12 — §3 misst das
  Zarr-**v2**-Tutorial-Produkt, §12 den **v3**-Bestand. Drei Fragen an Otto
  (F8–F10) stehen in §12.13.
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
nicht: Der Objektspeicher, auf dem die aktuellen EOPF-Produkte liegen, war aus
dieser Umgebung gesperrt (§3.1). Dieser Teil wurde deshalb, wie der Aufgabentext
verlangt, **angehalten** und Otto als F1 vorgelegt. Er hat freigegeben — die
Messungen dazu holt aber eine neue Sitzung nach, weil eine Freigabe hier nicht
mehr wirkt (§9.1).

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
> Dieser ADR behauptet dazu nichts.
>
> **Nachtrag 2026-09-20 (F1):** Otto hat `data.eodc.eu` freigegeben;
> `download.user.eopf.eodc.eu` bleibt bewusst gesperrt, weil ganze gezippte
> Produkte nie gebraucht werden. Die Freigabe wirkt erst in einer **neu
> gestarteten** Sitzung (`adr/0003` §11.3) — die Tabelle oben bleibt damit der
> gemessene Stand dieser Sitzung, und §9.1 sagt, was die Nachmess-Sitzung zu
> klären hat.
>
> **Nachtrag 2026-09-20 (M2-03b):** Die Freigabe wirkt, `data.eodc.eu` ist
> gemessen erreichbar — **§12.1**. Dort steht auch, dass `zipped_product`
> inzwischen auf diesem Host liegt und die Sperre des anderen es nicht mehr
> fernhält.

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

> **Überholt für den v3-Bestand (M2-03b, §12.3):** Die `…-zarr3`-Produkte
> führen sehr wohl `multiscales` (Pilotkonvention v0.1) **und** eine CRS im
> Store, dazu sechs Auflösungsstufen und 1024er Innenchunks über Sharding. Der
> folgende Absatz beschreibt weiterhin richtig das Zarr-**v2**-Tutorial-Produkt.

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

**Nachtrag M2-03b (§12.7):** In `sentinel-2-l2a-zarr3` gibt es nicht einmal ein
`TCI_10m` — über 20 geprüfte Items führt die Collection kein Asset mit einer
Vorschau-Rolle. Dass `TCI_10m` der Collection `sentinel-2-l2a` nicht auflöst, ist
auf beiden Hosts und in altem wie neuem Bestand bestätigt.

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

> **Für den v3-Bestand korrigiert (M2-03b, §12.4):** Dort kostet dieselbe
> Kachel **0,9–6,3 MB je Band (Median rund 1,5–2,2 MB), Echtfarbe rund 3,7 MB**,
> weil Sharding 1024er Innenchunks statt 1830er Chunks liest. Die folgende Zahl
> gilt für das v2-Tutorial-Produkt.

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
  nicht selbst lesen. **Das gilt für `objects.eodc.eu`; `data.eodc.eu` sendet
  CORS vollständig, einschließlich `Range` — M2-03b, §12.8.** Für uns ändert das nichts — wir kacheln serverseitig —,
  aber der Spike „Rendering im Browser" aus `architekturplan.md` 15.1
  Inkrement 7 ist gegen diese Quelle nicht durchführbar.

### 3.10 `https` reicht — `gateway` braucht kein `s3` — **[M]**

M1-03 F4 hat entschieden: „In M1 nur `https`; `s3` erst, wenn der erste Leser
es braucht (M2)." Der erste Leser ist dieser hier, und er braucht es **nicht**:

- **Lesen:** Alle Zugriffe in §3.6 und §3.7 waren gewöhnliche anonyme
  `GET`-Anfragen über `https`, ohne Signatur und ohne einen einzigen
  Kopfzeilen-Zusatz; `Range` beantwortet der Speicher mit `206` (§3.1). Ein
  Zarr-Chunk ist ein Objekt unter einer Adresse — mehr braucht der Reader nicht.
- **Auflisten:** Auch das geht anonym über `https`. `objects.eodc.eu` beantwortet
  `?list-type=2&prefix=…` mit einem `ListBucketResult` (200), **ohne Signatur**.
  Ein `s3`-Client wäre selbst dafür nicht nötig.
- **Und gebraucht wird Auflisten ohnehin kaum:** Die gemessenen Stores führen
  konsolidierte Metadaten (`.zmetadata` bzw. `zarr.json`), und die STAC-Items
  benennen Gruppe und Variablen (`bands`, `cube:variables`). Der Store in §3.7
  läuft deshalb mit `supports_listing = False` und öffnet über
  `zarr.open_array(path=…)`. Ein Produkt **ohne** konsolidierte Metadaten
  (gemessen: die `product`-Gruppe der S1-SLC-Collection trägt
  `zarr:consolidated: false`) bliebe damit trotzdem lesbar, weil die Namen aus
  dem Katalog kommen statt aus dem Speicher.

**Folge:** `gateway` bleibt `https`-only. Das hält die Allowlist, den
SSRF-Schutz und die Redirect-Kontrolle aus M1-03 unverändert gültig und erspart
einen zweiten Client-Typ. Für die anderen Kandidaten aus §4.2 gilt dasselbe:
`storage.googleapis.com` und die AWS-Open-Data-Buckets antworten in dieser
Sitzung ebenfalls anonym über `https` **[M]**.

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

Gesucht wurde ausdrücklich breiter als EOPF. Die Spalten sind die Punkte, die
der Aufgabentext je Kandidat verlangt; `Dauer.` ist die Dauerhaftigkeit nach K9.

| Kandidat | Metadaten-Host | Daten-Host | Token | Lizenz | STAC | Zeitachse | Dauer. | Quicklook | Zugang | Ratengrenze | CORS | Beleg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **EOPF Zarr Samples** (EODC) | `stac.core.eopf.eodc.eu` | `objects.eodc.eu` / **`data.eodc.eu` gesperrt** | nein **[M]** | Sentinel Data Legal Notice, wie Datensatz 1 **[P]** `adr/0003` §11.2 | **ja**, Items 1.1.0 an 1.0.0-API **[M]** | ja, aber ~2 Monate **[M]** | Betreiber nennt die Buckets „unofficial", Zukunft „unknown" **[P]** §10.3 | **nein**, das ausgewiesene löst 404 auf **[M]** | `https`, anonym **[M]** | keine dokumentiert, keine beobachtet **[M]** | API `*`, Speicher **keine** **[M]** | [M]/[P] |
| **ARCO-ERA5** (Google Research / ECMWF) | `github.com/google-research/arco-era5` | `storage.googleapis.com/gcp-public-data-arco-era5` | nein **[M]** | Code Apache-2.0 **[P]**; Daten CC-BY seit 07/2025 **[S]**, für diese Kopie nicht bestätigt | **nein** | 1940-01-01 bis 2026-06-30, `last_updated` **heute** **[M]** | Google Public Dataset, keine Selbsteinschränkung gefunden | entfällt (Klimagitter) | `https`, anonym **[M]** | unbelegt | unbelegt | [P]/[S]/[M] |
| **CMIP6-PDS** (ESGF/Pangeo, AWS ODR) | `registry.opendata.aws` | `cmip6-pds.s3.us-west-2.amazonaws.com` | nein **[P]** | Lizenzseite nicht abrufbar, **unbelegt** | nein (Intake-ESM) | lang | AWS-Sponsorship, laufend | entfällt | `https`, anonym **[M]** | unbelegt | unbelegt | [P]/unbelegt |
| **MUR SST** (PO.DAAC / Farallon, AWS ODR) | `registry.opendata.aws` | `mur-sst.s3.us-west-2.amazonaws.com` | nein **[P]** | „no restrictions" **[P]** | nein | 2002–2020, Fortführung unbelegt **[P]** | AWS-Sponsorship | entfällt | `https`, anonym **[M]** | unbelegt | unbelegt | [P]/[M] |
| **NOAA NWM Retrospective** | `registry.opendata.aws` | `noaa-nwm-retrospective-2-1-zarr-pds` | nein **[S]** | „no restrictions" **[S]** | nein | lang, stündlich | NODD-Programm | entfällt | unbelegt | unbelegt | unbelegt | [S] |
| **Earthmover ERA5** | `registry.opendata.aws` | `earthmover-icechunk-era5` | nein **[P]** | CC-BY 4.0 **[P]** | nein | 1940–2025 | kostenlose Variante neben kostenpflichtiger **[P]** | entfällt | Icechunk-Client nötig, **kein reines Zarr** **[P]** | unbelegt | unbelegt | [P] |
| **VEDA (NASA)** | `openveda.cloud` — **gesperrt** | S3 us-west-2, Host unbelegt | **gemischt**, geschützte Buckets verlangen IAM **[S]** | unbelegt | ja, STAC 1.0.0 **[S]** | je Collection unbelegt | unbelegt | unbelegt | unbelegt | unbelegt | unbelegt | [S] |
| **Planetary Computer** | gesperrt | — | **ja**, SAS-Signatur je Zugriff **[S]** | je Collection verschieden | ja | ja | — | — | — | — | — | **scheidet aus** (`adr/0003` §6) |
| **NEX-GDDP-CMIP6** | `registry.opendata.aws` | `nex-gddp-cmip6.s3…` | nein **[M]** | — | — | — | — | — | — | — | — | **scheidet aus:** nativ NetCDF/COG, Zarr nur virtuell **[S]** |

Zwei Spalten fallen auf. **Ratengrenze und CORS sind bei praktisch jedem
Kandidaten unbelegt** — nicht, weil niemand nachgesehen hätte, sondern weil kein
Anbieter sie dokumentiert. Und **Quicklook** ist außerhalb von EOPF gar keine
sinnvolle Frage: Klimagitter haben keine Szenen, für die sich eine Vorschau
lohnte.

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
*Gegen:* In dieser Sitzung **nicht messbar** (die Freigabe aus F1 wirkt erst in
der nächsten, §9.1). Bestand gut zwei Monate. Kein Quicklook. Keine Aggregation
und kein `numberMatched`. Der Betreiber bezeichnet die Buckets selbst als
„unofficial" mit „unknown" Zukunft (`adr/0003` §10.3) — **K9 bleibt verletzt,
und daran ändert die Freigabe nichts.** Das ist der Preis dieser Option, und er
ist mit ihrer Wahl bewusst in Kauf genommen.

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

**D sofort, A danach.** Otto hat F1 mit „freigeben" beantwortet; A ist damit der
Weg, und D ist der Teil davon, der sofort gehen kann.

1. **M2-09 in zwei Teile schneiden** (F2 angenommen). **M2-09a** baut den
   Lesepfad gegen ein synthetisches Mini-Zarr und ist von der Quellenwahl
   unabhängig; es kann sofort starten. **M2-09b** nimmt den realen Datensatz auf
   und setzt die Nachmessung aus §9.1 voraus. Entsprechend hängt **M2-10** an
   09b, nicht an 09a.

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
     Release). `adr/0006` §7 Punkt 6 hat `obstore` unabhängig davon auf die
     Verbotsliste von `http-only-in-gateway` gesetzt — damit ist der Ausschluss
     nicht mehr nur eine Empfehlung dieses ADR, sondern eine Importregel.
   - **Python bleibt 3.11, `zarr` wird auf `3.1.x` gepinnt** (F5). Der Pfad in
     §3.7 ist genau darauf gemessen. Ein Wechsel auf 3.12 ist eine eigene
     Aufgabe (CI-Matrix, Images) und steht als offene Log-Zeile.
   - **CRS aus dem STAC-Item** (`proj:code`), nicht aus dem Store; `proj:bbox`
     nur benutzen, wenn es zur CRS passt (§3.4). *Nachtrag M2-03b: Im
     v3-Bestand liegt die CRS im Store und stimmt mit `proj:code` überein; das
     Item bleibt der Rückfall (§12.11 Punkt 3).*
   - **Stufenwahl aus `gsd`/`raster:spatial_resolution`** der Assets, nicht aus
     `multiscales` — die Konvention ist Pilot v0.1 und in den gemessenen
     Produkten nicht vorhanden. *Nachtrag M2-03b: Für `sentinel-2-l2a-zarr3`
     umgekehrt — nur `multiscales` im Store kennt die drei gröbsten Stufen, das
     Item weist sie nicht aus (§12.11 Punkt 2).*
   - **Einbauort wie bei COG:** `adr/0006` §7 Punkt 5 legt den Prozess-Einstieg
     des `tiler` nach `earthx/api/tiler.py` und lässt Fabrik und Renderlogik in
     `access`, weil `access` `gateway` nach 3.1 nicht importieren darf. Der
     Zarr-Reader fügt sich dort ein, ohne eine zweite Anordnung zu erfinden.

3. **Coverage dieses Datensatzes ist `CoverageProvider.SAMPLE`.** Ohne
   Aggregation und ohne `numberMatched` bleibt nur die ausgewiesene Stichprobe
   (`adr/0004` Option 6). Sie muss in M2 gebaut werden, nicht später; M2-05
   hatte sie auf „falls M2-09 sie braucht" gestellt, und M2-09 braucht sie. Der
   Umschaltpunkt Dichte → Footprints braucht eine Ersatzregel, weil
   `numberMatched < 500` hier nicht auswertbar ist (Vorschlag: die Stichprobe
   selbst meldet, ob sie unter ihrem Deckel geblieben ist).

4. **STAC 1.1 an unserer 1.0-API: im Adapter normalisieren** (F4 angenommen).
   Unsere API weist `stac_version: "1.0.0"` aus, und der Lizenzwert wird daraus
   abgeleitet (Log vom 2026-09-19). `federating_client.py` reicht Items heute
   bis auf die Links unverändert durch — ein EOPF-Item ginge also mit
   `stac_version: "1.1.0"` aus einer 1.0-API heraus. Die **Collection** ist
   davon nicht betroffen: Sie kommt aus unserer Registry über pgstac, trägt
   also ohnehin unseren Lizenzwert. Zu normalisieren sind nur die **Items**,
   und zwar diese Felder — alles [M] am echten Item gemessen:

   | Feld | EOPF liefert (1.1) | wir geben aus (1.0) |
   |---|---|---|
   | `stac_version` | `"1.1.0"` | `"1.0.0"` |
   | `stac_extensions` | `eo` v2.0.0, `projection` v2.0.0, `raster` v2.0.0 | die 1.0-tauglichen Fassungen (`eo` v1.1.0, `projection` v1.1.0, `raster` v1.1.0) |
   | Asset-`bands` | `bands: [{name, description, eo:common_name, eo:center_wavelength, eo:full_width_half_max}]` | `eo:bands: [{name, description, common_name, center_wavelength, full_width_half_max}]` — die `eo:`-Präfixe **innerhalb** der Bandobjekte fallen weg |
   | `proj:code` | `"EPSG:32626"` | `proj:epsg: 32626` — nur bei `EPSG:`-Präfix; ein anderer Code bleibt stehen, statt still zu verschwinden |
   | Asset-`nodata`, `data_type`, `raster:spatial_resolution` | direkt am Asset (raster v2.0.0) | als `raster:bands`-Eintrag (raster v1.1.0) |

   Nicht umbenannt, sondern **geprüft** gehört `proj:bbox`: Im älteren Bestand
   steht dort eine Box in **Grad**, obwohl `proj:code` UTM sagt (§3.4). Der
   Adapter soll sie verwerfen, wenn sie nicht zur CRS passt — umbenennen würde
   den Fehler nur weiterreichen.

   Grundsatz für alles Übrige: Was nicht abbildbar ist, bleibt stehen, statt
   still verfälscht zu werden. Die `zarr`-Extension v1.1.0 hat keine
   1.0-Entsprechung und bleibt deshalb unverändert.

5. **Quicklook-Ersatz: serverseitig gerendert.** Eine Vorschau aus der gröbsten
   Auflösungsstufe über denselben Kachelpfad, im Statistik- bzw.
   Anwendungs-Cache abgelegt. Ein fertiges Bild gibt es nicht, auch nicht dort,
   wo der Katalog eines ausweist (§3.5).
   **Das ist der erste Datensatz, für den `adr/0006` §7 Punkt 4 nicht greift.**
   Dort ist der Quicklook-Proxy ersatzlos entfallen, weil der Browser das
   Thumbnail direkt lädt — ausdrücklich unter der Bedingung, dass der Asset-Host
   CORS sendet (`AccessInfo.cors`). Der EOPF-Objektspeicher sendet keinen
   CORS-Header und beantwortet den Preflight mit 403 (§3.9). Für diesen
   Datensatz steht `AccessInfo.cors = False`, und die Vorschau muss über unseren
   eigenen Prozess laufen.
   **Nachtrag M2-03b (§12.8, §12.11 Punkt 4):** Für `data.eodc.eu` stimmt die
   Begründung nicht — der Host sendet CORS vollständig, `AccessInfo.cors` ist
   **`True`**. Die serverseitig gerenderte Vorschau bleibt trotzdem, aber aus
   dem anderen Grund: Es gibt überhaupt kein Vorschaubild (§12.7).

6. **Das synthetische Mini-Zarr** (F6) wird **im Test per Skript erzeugt**,
   keine Binärdatei im Repo. Es bildet nach, woran der Reader sich bewähren
   muss, und zwar genau an den Stellen, an denen die echte Quelle vom Lehrbuch
   abweicht:

   - **Auflösungsgruppen statt `multiscales`** — mehrere Stufen desselben
     Ausschnitts als Geschwistergruppen, wie `r10m`/`r20m`/`r60m` (§3.4).
   - **Keine CRS im Store** — die Georeferenzierung kommt aus `proj:code` des
     Items; `x`- und `y`-Koordinatenarrays liegen bei, ohne Bezugssystem.
   - **Mehrere Variablen** in einer Gruppe, damit die Bandwahl etwas zu wählen
     hat.
   - **Eine Zeitachse**, damit der Fall „Dimension statt Item-Eigenschaft"
     einmal vorkommt.
   - **Kleine Chunks**, damit ein Fenster mehrere davon schneidet, ohne dass der
     Test Megabyte bewegt.
   - **Ein Fehlerfall: eine fehlende Gruppe**, die das Item ausweist und der
     Store nicht hat — genau der Fall, an dem `TCI_10m` in der echten Quelle
     scheitert (§3.5). M2-09 verlangt dafür einen definierten Fehler.

**Was das für die Abnahme von M2 bedeutet.** Mit der Freigabe aus F1 ist
Abnahmekriterium 1 erreichbar. Sollte die Nachmessung (§9.1) A dennoch
verwerfen, bliebe der Rückfallweg aus §8 F7; er ist beschrieben, aber nicht
beschlossen. M2a ist davon in jedem Fall unberührt und eigenständig abnehmbar.

---

## 7. Folgen

1. `architekturplan.md` 6.2 nennt „Bausteine aus titiler-xarray bzw. TiTiler-EOPF
   prüfen" — geprüft, Ergebnis negativ für TiTiler-EOPF (§3.8). Die Zeile ist
   nachzuziehen.
2. `architekturplan.md` 14 Punkt 5 („Sendet der EOPF-Zarr-Dienst CORS-Header?")
   ist beantwortet: STAC-API ja, Objektspeicher nein (§3.9).
3. **Erledigt mit M2-03b.** `cloud-umgebung.md` §6 ist mit der Freigabe aus F1 erneut nachzuziehen: PR #34
   hat `objects.eodc.eu` als erreichbar und `data.eodc.eu` als gesperrt
   eingetragen; nach der Freigabe stimmt der zweite Eintrag nicht mehr. Es fehlt
   dort außerdem `stac.core.eopf.eodc.eu` (erreichbar, §3.1). Beides gehört in
   die Nachmess-Sitzung aus §9.1, weil erst sie die Freigabe belegen kann.
4. Die **ausgewiesene Stichprobe** gehört zu **M2-09b**, nicht zu M2-05: Sie
   wird erst gebraucht, wenn der Datensatz da ist, dessen Quelle keine
   Aggregation hat (§6 Punkt 3).
5. **M2-07c braucht eine Ersatzregel für den Umschaltpunkt**, weil
   `numberMatched` bei dieser Quelle fehlt und `numberMatched < 500` damit nicht
   auswertbar ist (§3.2).
6. M2-09 wird in 09a und 09b geteilt; M2-10 hängt an 09b.
7. Der Registry-Eintrag des zweiten Datensatzes braucht ein Feld, aus dem der
   Reader die CRS-Herkunft liest, und eines für die Auflösungsstufen. Beides
   gibt es heute nicht; `DataFormat.ZARR` und `CoverageProvider.SAMPLE` gibt es
   schon. Für die Asset-Hosts gibt es seit `adr/0006` §7 Punkt 2 bereits
   `SourceInfo.asset_hosts` — dort stünde für diesen Datensatz `data.eodc.eu`
   (und, solange die älteren Items mitlaufen, `objects.eodc.eu`).
8. Die offene Log-Zeile „Ratengrenzen der Anbieter" bleibt für EOPF offen: keine
   Drosselung beobachtet, keine Grenze dokumentiert (§3.9).
9. **M1-03 F4 ist beantwortet:** Der erste Zarr-Leser braucht kein `s3`;
   `gateway` bleibt `https`-only (§3.10). Die Log-Zeile „`s3` erst, wenn der
   erste Leser es braucht (M2)" kann damit geschlossen werden.

---

## 8. Fragen an Otto — beantwortet am 2026-09-20

**F1 — `data.eodc.eu` freigeben?** **Beantwortet, abweichend von der
Empfehlung:** `data.eodc.eu` **wird freigegeben**,
`download.user.eopf.eodc.eu` **bleibt gesperrt** — ganze gezippte Produkte
braucht die Plattform nie, der Lesepfad holt Chunks. Damit entfällt das Asset
`zipped_product` für uns ersatzlos; der Registry-Eintrag führt es nicht.

Die Freigabe wirkt erst in einer **neu gestarteten** Sitzung. Die Nachmessung
gegen `sentinel-2-l2a-zarr3` macht deshalb eine eigene Sitzung, nicht diese;
was sie zu klären hat, steht in §9.1.

**F2 — M2-09 teilen?** **Angenommen (a):** **M2-09a** baut den Reader gegen ein
synthetisches Mini-Zarr und ist quellenunabhängig; **M2-09b** nimmt den realen
Datensatz auf. **M2-10** hängt an 09b.

**F3 — Lizenzeinstufung des EOPF-Bestands nach B11.** **Angenommen (a), und von
Otto förmlich bestätigt:** Einstufung wie beim ersten Datensatz, auf Grundlage
**desselben** Sentinel Data Legal Notice, das `adr/0003` §11.2 am Primärdokument
geprüft hat. Lizenzfelder und `terms_notice` des bestehenden
Sentinel-2-Eintrags werden wiederverwendet. Der ADR trägt das damit als
bestätigten Vorschlag, nicht als eigene Einstufung.

**F4 — Normalisierung von STAC 1.1 nach 1.0.** **Angenommen (a):** Im Adapter
normalisieren. Begründung von Otto: Unsere API weist 1.0.0 aus, Items
unverändert durchzureichen widerspricht dem. Die betroffenen Felder stehen
einzeln in §6 Punkt 4, damit M2-09b sie umsetzen kann.

**F5 — Python 3.11 oder 3.12?** **Angenommen (a):** Python bleibt **3.11**,
`zarr` wird auf **3.1.x** gepinnt. `titiler-eopf` ist ohnehin ausgeschieden, und
der in §3.7 gemessene Pfad läuft auf genau dieser Kombination. Ein Wechsel auf
3.12 wäre eine eigene Aufgabe (CI-Matrix, Images) und steht als **offene
Log-Zeile**.

**F6 — Zuschnitt des synthetischen Mini-Zarr.** **Beantwortet, konkreter als die
Vorlage:** Es wird **im Test per Skript erzeugt**, keine Binärdatei im Repo, und
bildet nach, was der Reader können muss — Auflösungsgruppen statt
`multiscales`, keine CRS im Store (Georeferenzierung aus `proj:code`), mehrere
Variablen, eine Zeitachse, kleine Chunks, dazu ein Fehlerfall mit fehlender
Gruppe. Ausformuliert in §6 Punkt 6.

**F7 — Was, wenn kein Kandidat trägt?** **Mit F1 gegenstandslos.** Der Weg
bleibt als **Rückfallweg** beschrieben, nicht als Beschluss: Trüge am Ende kein
Kandidat, würde die Abnahme von M2 auf „Sentinel-2 plus belegter
Zarr-Lesepfad" zurückgenommen und der zweite Datensatz nach M3 geschoben. Die
beiden anderen Wege aus der Vorlage — eine Nicht-STAC-Quelle vorziehen oder
Copernicus DEM statt eines zweiten Formats — sind damit nicht gewählt.

---

## 9. Was offen blieb

### 9.1 Die gesperrten Collections — und woher die Antworten kommen

> **Erledigt.** Die Nachmessung hat am 2026-09-20 als Aufgabe M2-03b
> stattgefunden; alle sechs Punkte sind in **§12** beantwortet, einzeln
> gegenübergestellt in §12.12. Der Abschnitt bleibt als Beleg dafür stehen, was
> zum Zeitpunkt der Annahme offen war.

Dieser ADR ist **angenommen, ohne dass der empfohlene Datensatz gemessen wäre.**
Das ist kein Versehen, sondern die Lage: `data.eodc.eu` war während der Messung
gesperrt (§3.1), und die Freigabe aus F1 wirkt erst in einer **neu gestarteten**
Sitzung. Alles Folgende ist deshalb **unbelegt**, und der ADR behauptet dazu
nichts:

- **Chunk-Zuschnitt** der `…-zarr3`-Collections — ob die Zarr-v3-Produkte
  ähnlich grob geschnitten sind wie die v2-Tutorial-Produkte (1830²,
  §3.6) oder feiner.
- **Georeferenzierung** — ob im Store eine CRS liegt oder auch dort nur
  `proj:code` aus dem Item trägt (§3.4).
- **Übersichtsstufen** — ob `sentinel-2-l2a-zarr3` dieselben drei
  Auflösungsgruppen führt wie die v2-Produkte, oder `multiscales`.
- **Lesekosten je Kachel** — die Zahlen in §3.6 stammen vom v2-Tutorial-Produkt
  und sind auf die v3-Produkte **nicht** übertragbar.
- **Existenz der Objekte** überhaupt, auch für die älteren Items von
  `sentinel-2-l2a`, deren Assets auf `data.eodc.eu` zeigen (§3.3).
- **Ob die 2017er Item-Metadaten** von `sentinel-2-l2a` auf existierende Objekte
  zeigen — außerhalb der Tutorial-Produkte nicht prüfbar.

**Woher die Antworten kommen sollen:** aus einer eigenen, nach der Freigabe neu
gestarteten Cloud-Sitzung, vor oder zu Beginn von **M2-09b**. Sie misst dieselben
Punkte wie §3.4 und §3.6, an einem Item aus `sentinel-2-l2a-zarr3`, und trägt
das Ergebnis als Nachtrag in diesen ADR ein. Zum selben Anlass gehört die
Korrektur von `cloud-umgebung.md` §6 (§7 Punkt 3) — erst diese Sitzung kann die
Freigabe belegen. **M2-09a** braucht davon nichts und kann vorher laufen.

### 9.2 Das Übrige

1. **Ratengrenzen von EODC** — keine dokumentierte Grenze gefunden, keine
   Drosselung bei 10 parallelen Anfragen beobachtet. Das ist kein Beleg für
   „keine Grenze".
2. **Lizenz der CMIP6-PDS-Kopie** — Lizenzseite nicht abrufbar.
3. **Ob ARCO-ERA5 für die konkrete Google-Kopie CC-BY ausweist** — nur die
   Code-Lizenz (Apache-2.0) ist am Primärdokument belegt.
4. **Ob `titiler.xarray` einen eigenen Store annimmt** statt ihn intern zu
   bauen — Quelltext über den Proxy nicht lesbar. Für die Empfehlung ohne
   Belang, weil §3.7 den Weg ohne titiler misst.
5. **VEDA (NASA)** als STAC-Quelle mit Zarr-Assets — Host gesperrt, deshalb
   weder aufgenommen noch verworfen.
6. **Der Latenzsockel von ~0,5 s je Objekt** ist durch den Sitzungs-Proxy
   gemessen und damit eine Obergrenze; der Betriebswert ist unbekannt.

---

## 10. Quellen

**Gemessen (M), Nachmess-Sitzung M2-03b vom 20.09.2026, rund 450 Anfragen** —
Einzelheiten und Befehle in §12.14:

- `https://data.eodc.eu` — Wurzel, `zarr.json` der konsolidierten Metadaten,
  Knoten-`zarr.json`, Shard-`HEAD`s und Sharding-Indizes, Innenchunk-Reads über
  `Range`, `OPTIONS`-Preflight und `GET` mit `Origin`, `HEAD` auf
  `zipped_product`
- `https://stac.core.eopf.eodc.eu` — `/collections/sentinel-2-l2a-zarr3`,
  `/search` mit Zeitfenstern, `bbox` und Paging über 40 Seiten, 20 parallele
  Suchen
- Erreichbarkeitsproben: `data.eodc.eu`, `stac.core.eopf.eodc.eu`,
  `objects.eodc.eu`, `download.user.eopf.eodc.eu`, `stac.eopf.copernicus.eu`,
  `stac.browser.user.eopf.eodc.eu`
- Lesepfad-Messung §12.9 im Wegwerf-venv: `zarr` 3.1.6, `xarray` 2026.7.0,
  `rioxarray` 0.19.0, `rio-tiler` 9.4.6, `numpy` 2.4.6, `morecantile` 7.1.0

**Gemessen (M), Sitzung vom 20.09.2026, rund 270 Anfragen:**

- `https://stac.core.eopf.eodc.eu` — `/`, `/collections`, `/queryables`,
  `/search` (je Collection, mit `datetime`-Fenstern, `limit`, Paging-Marke),
  `/aggregations`, `/aggregate`
- `https://objects.eodc.eu` — `.zmetadata` und `zarr.json` zweier Stores,
  einzelne Chunks von `b04` in `r10m` und `r60m`, `HEAD`/`Range`-Verhalten,
  CORS mit `Origin` und `OPTIONS`, anonymes `?list-type=2`-Listing (§3.10)
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

### 11.4 Zugangsschema (§3.10)

```
curl -sS -H "Authorization;" "<store>/.zmetadata"                      # 200
curl -sS "https://objects.eodc.eu/<tenant>:notebook-data\
?list-type=2&max-keys=3"                                               # 200, ListBucketResult
curl -sS "https://objects.eodc.eu/<tenant>:notebook-data/\
?list-type=2&max-keys=3&prefix=tutorial_data/"                         # 200, ListBucketResult
```

Beide Listings ohne Signatur, über gewöhnliches `https`.

### 11.5 Lesepfad (§3.7)

Wegwerf-venv im Kratzverzeichnis, `probe_store.py` und `probe_tile.py`. Der
`Store` implementiert `zarr.abc.store.Store` mit `get`, `get_partial_values`,
`exists` und zählt Requests und Bytes; `list*` bleibt bewusst unimplementiert
(`supports_listing = False`), deshalb wird mit `zarr.open_array(path=…)`
geöffnet statt über `open_group().arrays()`. Die Kachel ist
`WebMercatorQuad` z11/1087/686, ermittelt über `morecantile.tms.tile(11.2, 50.9, 11)`.
Beide Skripte sind nicht Teil des Repos.

---

## 12. Nachmessung nach der Freigabe (M2-03b, 2026-09-20)

**Was das ist.** Die in §9.1 angekündigte Nachmessung aus einer eigenen, neu
gestarteten Cloud-Sitzung. Sie beantwortet die sechs dort offen gebliebenen
Punkte an der Collection `sentinel-2-l2a-zarr3` und zieht die Stellen nach, an
denen §3 vom v2-Tutorial-Produkt auf die v3-Produkte geschlossen hatte. **Stufe C:
nur gemessen; kein Produktivcode, keine Datei außerhalb von `docs/`, keine
Abhängigkeit des Projekts verändert.** Belegstufen wie oben.

> **Vorrang.** Wo §12 einer Aussage aus §3 bis §7 widerspricht, gilt §12: §3
> misst das Zarr-**v2**-Tutorial-Produkt, §12 den **v3**-Bestand, um den es
> geht. Die Unterschiede sind groß und fallen überwiegend zugunsten der Quelle
> aus.

**Umfang der Abrufe — und ein Ausreißer, der zugleich ein Befund ist.** Rund 450
Anfragen über etwa 75 Minuten. Metadaten: rund 4 000 Items über 40 Suchseiten
(§12.6, rund 50 MB JSON). Pixel: die Kachel-, Statistik- und Zuschnittmessungen
der §§12.4/12.5 zusammen rund 130 MB. **Dazu rund 1,5 GB, die nicht geplant
waren:** Zwei Sondenläufe stapelten drei Bänder mit
`Dataset.to_dataarray()`, und das materialisiert die Arrays vollständig — je
Lauf drei volle `r10m`-Shards zu je 158 MB statt drei Fenstern (§12.9). Das ist
offen auszuweisen, weil es gegen „Umfang klein halten" verstößt, und es ist
zugleich die wichtigste Warnung für die Umsetzung (§12.11 Punkt 7). Kein Produkt
wurde heruntergeladen. Für §12.9 lief `zarr`, `xarray` und `rio-tiler[xarray]`
wieder in einem **Wegwerf-venv im Kratzverzeichnis**; `backend/requirements.txt`
und das Projekt-venv blieben unberührt.

### 12.1 Die Freigabe wirkt — **[M]**

| Host | Ergebnis | gegen §3.1 |
|---|---|---|
| `data.eodc.eu` | **200**, Server `APISIX/3.13.0` | **war gesperrt, jetzt offen** |
| `stac.core.eopf.eodc.eu` | 200 | unverändert offen |
| `objects.eodc.eu` | 200 | unverändert offen |
| `download.user.eopf.eodc.eu` | `CONNECT` 403 | **bleibt gesperrt, wie F1 es wollte** |
| `stac.eopf.copernicus.eu` | `CONNECT` 403 | unverändert gesperrt |
| `stac.browser.user.eopf.eodc.eu` | `CONNECT` 403 | unverändert gesperrt |

`data.eodc.eu` ist kein blanker Objektspeicher, sondern der „EODC Data Access
Service" hinter APISIX; die Wurzel liefert eine Liste von 65 Collections, die
EOPF-Produkte liegen unter `/collections/EOPF_ZARR/products/`.

**Ein Nebenbefund, der F1 teilweise unterläuft:** Das Asset `zipped_product`
liegt bei diesen Items **nicht mehr** auf dem gesperrten
`download.user.eopf.eodc.eu`, sondern auf `data.eodc.eu` selbst — `HEAD` 200 mit
**1 200 781 250 B (1,2 GB)**. Die Sperre des anderen Hosts hält gezippte
Produkte also nicht mehr fern; das muss der Registry-Eintrag tun (§12.11
Punkt 10).

### 12.2 Die Messszenen

| | Szene A | Szene B |
|---|---|---|
| Item | `S2C_MSIL2A_20260919T141841_N0512_R096_T26WME_20260919T161612` | `S2A_MSIL2A_20260919T102041_N0512_R065_T32TPS_20260919T170225` |
| Kachel / CRS | MGRS-26WME, `EPSG:32626` | MGRS-32TPS, `EPSG:32632` |
| Mitte | 28,3° W / **71,6° N** | 11,0° O / **46,4° N** |

Zwei Breiten, weil der Bestand von 34° N bis 72° N reicht und die Bodenauflösung
einer Web-Mercator-Kachel mit `cos(Breite)` skaliert — zwischen beiden Enden um
den Faktor 2,7. Eine feste Tabelle „Zoomstufe → Auflösungsgruppe" kann es
deshalb nicht geben (§12.10).

### 12.3 Der v3-Store ist anders gebaut als das v2-Produkt — **[M]**

Gemessen an der konsolidierten Wurzel von Szene A (`zarr.json`, 500 563 B,
221 Knoten, 1,35 s — gegen 4,55 MB beim S1-SLC-Store aus §3.4):

| | §3.4 sagte (v2-Tutorial) | §12 misst (v3, `…-zarr3`) |
|---|---|---|
| `multiscales` | 0 Treffer | **vorhanden**, an `measurements/reflectance` |
| Übersichtsstufen | drei Auflösungsgruppen, ohne Konvention | **sechs**: `r10m`, `r20m`, `r60m`, `r120m`, `r360m`, `r720m` |
| CRS im Store | keine — weder `grid_mapping` noch `crs_wkt` | **vorhanden**: `spatial_ref`-Array je Stufe mit `crs_wkt`, `grid_mapping` an jedem Band |
| Chunks | 1830 × 1830, roh 6,70 MB | Shard 11264², **Innenchunk 1024 × 1024** (`sharding_indexed`, blosc/zstd) |

**Die Pyramide ist erklärt, aber nach einer Pilot-Konvention.** Der Knoten
`measurements/reflectance` trägt `multiscales` mit einer `layout`-Liste über die
sechs Stufen, je mit `spatial:shape` und `spatial:transform`, dazu
`resampling_method: average`. Der Store deklariert dafür ausdrücklich
`zarr-conventions/multiscales` in **v0.1** — genau die Fassung, die §3.4 als
„Pilot mit angekündigten Breaking Changes bis v1" eingestuft hat. Die Einstufung
bleibt richtig; sie trifft jetzt nur nicht mehr ins Leere. Daneben deklariert der
Store `zarr-conventions/spatial` und `zarr-conventions/proj`, beide an einen
Commit-Stand gepinnt, nicht an eine Version.

**Das Item weist weniger aus als der Store hat.** Die zehn Assets sind `SR_10m`,
`SR_20m`, `SR_60m`, `ATM_10m/20m/60m`, `SCL_20m/60m`, `product`,
`zipped_product`. **`r120m`, `r360m` und `r720m` kommen im STAC-Item nicht vor** —
sie stehen nur im Store. Wer die Stufenwahl aus `gsd` /
`raster:spatial_resolution` der Assets trifft, wie §6 Punkt 2 es vorsah, verliert
die drei billigsten Stufen (§12.11 Punkt 2).

**Sharding ist der Grund, warum das trotzdem bezahlbar ist.** Ein Shard ist das
ganze Band einer Stufe, ein einziges Objekt:

| Stufe | Form | Shard (ein Objekt) | Innenchunk komprimiert: min / Median / max | belegt |
|---|---|---|---|---|
| `r10m` | 10980² | **158 253 910 B** | 62 638 / 1 356 805 / 1 861 780 | 118 von 121 |
| `r20m` | 5490² | 41 502 672 B | 17 999 / 1 400 599 / 1 802 357 | 35 von 36 |
| `r60m` | 1830² | 4 850 898 B | 759 280 / 1 225 011 / 1 663 919 | 4 von 4 |
| `r120m` | 915² | 1 250 462 B | ein Chunk | 1 von 1 |
| `r360m` | 305² | 146 594 B | ein Chunk | 1 von 1 |
| `r720m` | 152² | 38 333 B | ein Chunk | 1 von 1 |

Der Shard-Index liegt am Ende (`index_location: end`, 1 940 B bei `r10m`) und
kostet einen Range-Read von rund 0,5 s. `data.eodc.eu` beantwortet `Range` mit
`206` **[M]**. **Ohne Byte-Ranges im Store holt ein Kachelabruf den ganzen
158-MB-Shard** — das ist die schärfste Bedingung an die Umsetzung (§12.11
Punkt 1).

### 12.4 Was eine Kachel wirklich kostet — **[M]**

Ein Band (`b04`), 256 × 256, `XarrayReader.tile()`, je sechs bzw. fünf Kacheln
quer über die Szene; Zeiten durch den Sitzungs-Proxy, also Obergrenzen.

**Szene A (71,6° N):**

| z | Stufe | Requests | MB min–max (Median) | s |
|---|---|---|---|---|
| 6 | `r720m` | 1 | 0,038 | 0,6 |
| 7 | `r360m` | 1 | 0,147 | 0,8–1,6 |
| 8 | `r360m` | 1 | 0,147 | 0,8 |
| 9 | `r120m` | 1 | 1,250 | 1,2 |
| 10 | `r60m` | 2–3 | 0,76–1,98 (1,66) | 1,6–2,8 |
| 11 | `r20m` | 2 | 0,99–1,80 (1,45) | 1,7–1,9 |
| 12 | `r10m` | 2–5 | 1,23–**6,26** (2,17) | 1,8–5,3 |
| 13 | `r10m` | 2–3 | 1,11–2,62 (1,49) | 1,7–3,1 |

**Szene B (46,4° N):**

| z | Stufe | Requests | MB min–max (Median) | s |
|---|---|---|---|---|
| 8 | `r720m` | 1 | 0,031 | 0,6 |
| 9 | `r360m` | 1 | 0,121 | 0,8 |
| 10 | `r120m` | 1 | 1,040 | 1,2 |
| 11 | `r60m` | 2–3 | 0,52–2,61 (1,45) | 1,6–2,8 |
| 13 | `r20m` | 2–3 | 1,12–1,37 (1,34) | 1,7–2,6 |
| 14 | `r10m` | 2 | 0,91–1,32 (1,31) | 1,6–1,9 |

**Echtfarbe** (`b04`/`b03`/`b02`, jedes Band einzeln gefenstert, danach
gestapelt), Szene B:

| z | Stufe | Requests | MB | s |
|---|---|---|---|---|
| 9 | `r360m` | 3 | 0,361 | 2,6 |
| 11 | `r60m` | 6 | 4,294 | 5,3 |
| 12 | `r20m` | 6 | 4,104 | 5,3 |
| 13 | `r10m` | 6 | 3,746 | 5,1 |
| 14 | `r10m` | 6 | 3,746 | 5,1 |

**Die Zahl aus §3.6 ist zu korrigieren.** Dort stand: „eine einzige
Web-Mercator-Kachel in nativer Auflösung kostet hier 3–16 MB von der Quelle".
Gemessen am v3-Bestand kostet sie **ein Band 0,9–6,3 MB (Median rund 1,5–2,2 MB),
Echtfarbe rund 3,7 MB**. Der Grund ist das Sharding: Gelesen werden 1024er
Innenchunks statt 1830er Chunks, also ein bis vier Stück je Kachel statt des
Fünfzigfachen einer Kachelfläche. Teurer als COG (`adr/0003` §10.1: 32 KiB
Header-Read) bleibt es deutlich, aber es ist kein Ausschlussgrund mehr.

**Die groben Stufen sind Einzelchunk-Stufen.** `r120m`, `r360m` und `r720m`
bestehen aus genau einem Chunk; jede Kachel daraus zieht die ganze Stufe. Das
ist bei `r360m` (147 kB) und `r720m` (38 kB) billig und bei `r120m` (1,25 MB)
spürbar — dafür deckt ein einziger Abruf dann alle Kacheln dieser Stufe ab, wenn
der Item-Cache greift.

**Öffnen kostet mehr, als es müsste** — Szene A, `r60m`:

| | Requests | Zeit |
|---|---|---|
| ohne Formatangabe | **11** | 5,6 s |
| mit `zarr_format=3` | **5** | 2,5 s |

Ohne Angabe probiert `zarr` je Knoten `zarr.json`, `.zarray` und `.zattrs` durch;
sechs dieser elf Anfragen laufen ins Leere. Ein dritter Weg: die Gruppe über die
konsolidierte Wurzel öffnen (`xr.open_zarr(…, consolidated=True,
decode_coords="all")`) — **3 Requests, 512 718 B, 2,1 s**, und liefert dafür alle
zwölf Bänder **samt CRS**.

### 12.5 Statistik und AOI-Zuschnitt — **[M]**

`XarrayReader.statistics()` auf `b04`, Szene A:

| Stufe | s | Requests | MB | p2 | p98 |
|---|---|---|---|---|---|
| `r720m` | 0,62 | 1 | 0,038 | 0 | 11 770 |
| `r360m` | 0,84 | 1 | 0,147 | 0 | 11 955 |
| `r120m` | 1,46 | 1 | 1,250 | 0 | 12 192 |
| `r60m` | 2,82 | 1 | 4,851 | 0 | 12 407 |

Die Statistik auf der gröbsten Stufe weicht im `p98` um rund 5 % von der auf
`r60m` ab. Für den Streckbereich nach Z4 ist das unerheblich — **die Statistik
gehört auf `r720m` oder `r360m`**, nicht auf eine feine Stufe (§12.11 Punkt 8).

`XarrayReader.feature()` auf `r10m`, Szene A:

| AOI | Requests | MB | s | Ergebnis |
|---|---|---|---|---|
| rund 16 × 8 km | 7 | 9,178 | 7,7 | 1593 × 1514 px |
| rund 3 × 4 km | 2 | 1,241 | 1,6 | 452 × 319 px |

Der Zuschnitt skaliert also mit der Zahl geschnittener Innenchunks, nicht mit der
Produktgröße — genau das, was M2-06 braucht.

### 12.6 Bestand, Aktualität, Ausdehnung — **[M]**

| Befund | Messung |
|---|---|
| Titel der Collection | **„Sentinel-2 Level-2A (Zarr3 **staging**)"** |
| `extent.temporal` | 2026-07-16T10:06:01Z bis 2026-09-19T14:18:41Z — gut zwei Monate |
| `extent.spatial` | Länge −33,00 … 179,58; **Breite 34,21 … 72,10** |
| `license` | `proprietary` bei `stac_version: 1.1.0` — die Inkonsistenz aus §3.2 besteht fort |
| Lizenz-Link | dasselbe Sentinel Data Legal Notice wie beim ersten Datensatz (§3.9, F3) |
| `numberMatched` | **fehlt weiterhin** in jeder Antwort |
| Monatsfenster | Mai, Juni, 1.–15. Juli leer; ab 16. Juli belegt |
| Stichprobe 4 000 Items (40 Seiten, `limit=100`, 92 s) | **nur drei Tage** (17.–19.09.), **1 150 / 1 431 / 1 419** Items je Tag, **1 802** verschiedene MGRS-Kacheln, alle drei Plattformen (2A/2B/2C); Paging nach 40 Seiten noch nicht am Ende |

Daraus folgt zweierlei. **Der Bestand ist groß genug**: rund 1 300 Items je Tag
über gut zwei Monate sind grob 80 000 Items — die Zeitleiste und die Gruppierung
haben etwas zu tun. **Und er ist nicht global**: keine Südhalbkugel, keine
Tropen, Schwerpunkt Europa und Nordatlantik. Für den Viewer heißt das, dass die
Coverage-Heatmap dieses Datensatzes außerhalb 34°–72° N leer ist — kein Fehler,
aber erklärungsbedürftig.

**„staging" ist die eigentliche Nachricht dieses Abschnitts.** §5 Option A hatte
K9 schon als verletzt geführt, weil der Betreiber die Buckets „unofficial" nennt.
Die Collection sagt es jetzt in ihrem eigenen Titel. Das ändert die Sachlage
nicht, aber es schärft sie: Wer diesen Datensatz nimmt, nimmt einen ausdrücklich
vorläufigen.

### 12.7 Quicklook: schlechter als §3.5, dafür eindeutig — **[M]**

Über 20 geprüfte Items führt `sentinel-2-l2a-zarr3` **kein einziges Asset** mit
einer Rolle `thumbnail`, `preview`, `overview` oder `visual`; die vorkommenden
Rollen sind nur `data`, `metadata`, `archive`, `atmosphere`, `mask`,
`reflectance`. **Ein `TCI_10m` gibt es hier gar nicht.**

Der Sonderfall aus §3.5 ließ sich zusätzlich abschließen: In der Collection
`sentinel-2-l2a` existiert `TCI_10m` als Asset, löst aber **auf beiden Hosts und
in altem wie neuem Bestand** nicht auf (404 auf `zarr.json`, `.zgroup`,
`.zarray` und `.zmetadata`). §3.5 gilt damit unverändert, und für
`sentinel-2-l2a-zarr3` stellt sich die Frage nicht einmal: Der Ersatz muss aus
dem Kachelpfad kommen. Er ist billig — eine Vorschau aus `r720m` kostet 38 kB und
0,6 s (§12.4).

### 12.8 CORS, Zwischenspeicher, Ratengrenzen — **[M]**

**Die CORS-Aussage aus §3.9 gilt für `data.eodc.eu` nicht.** Gemessen sendet der
Host auf `GET`, `HEAD` und im `OPTIONS`-Preflight (204):

```
access-control-allow-origin: *
access-control-allow-methods: GET, HEAD, OPTIONS
access-control-allow-headers: Range, Content-Type
access-control-expose-headers: Content-Length, Content-Range, Accept-Ranges
```

Das ist genau der Satz, den ein Zarr-Leser im Browser braucht — einschließlich
`Range` und der freigegebenen `Content-Range`. §3.9 hatte für `objects.eodc.eu`
gemessen: kein Header, Preflight 403. Beide Messungen stehen; sie betreffen
verschiedene Hosts. **Folge:** `AccessInfo.cors` ist für diesen Datensatz
**`True`**, und der Spike „Rendering im Browser" (`architekturplan.md` 15.1
Inkrement 7) ist gegen diese Quelle doch durchführbar (§12.11 Punkt 4).

**Kein `ETag`, kein `Cache-Control`, kein `Last-Modified`** auf den Objekten.
Unser Cache kann also nicht revalidieren, sondern nur nach Frist arbeiten — wie
der Statistik-Cache aus D13 es ohnehin tut.

**Ratengrenzen:** 12 parallele Chunk-Abrufe (alle 200, 0,98–1,11 s) und 20
parallele STAC-Suchen (alle 200). Kein `429`, kein `Retry-After`, kein
`X-RateLimit-*`. Die offene Log-Zeile „Ratengrenzen der Anbieter" bleibt für EOPF
**sachlich unbeantwortet**; der Deckel von sechs parallelen Verbindungen je Host
aus `gateway` trägt weiter.

### 12.9 Der Lesepfad, end-to-end gegen die echte Quelle — **[M]**

Der Aufbau aus §6 Punkt 2, unverändert, gegen Szene B: eigener
`zarr.abc.store.Store` mit `get`, `get_partial_values` und `exists` → `zarr`
3.1.6 → `xarray` 2026.7.0 → `rioxarray` 0.19.0 → `rio_tiler.io.xarray.XarrayReader`
9.4.6, auf Python 3.11.15. Der Store prüft Schema und Host an genau einer Stelle;
im Produktivcode stünde dort `gateway`.

```
Stufe r720m oeffnen (Statistik)          2,52 s    5 Req    0,004 MB
statistics() fuer den Streckbereich      0,57 s    1 Req    0,031 MB   p2 0, p98 6470
Stufe r10m oeffnen (Kachel)              2,72 s    5 Req    0,091 MB
tile z14/8693/5799                       1,66 s    2 Req    1,241 MB   PNG 60 816 B
feature() AOI rund 3 x 4 km bei 10 m     1,62 s    2 Req    1,241 MB   452 x 319 px
GESAMT                                   9,1  s   15 Req    2,609 MB
```

Kachel, Statistik und Zuschnitt — die drei Aufgaben aus M2-09 — laufen damit
gegen die echte Quelle, mit **15 Anfragen und 2,6 MB**, und jeder Byte-Read ging
durch die eine geprüfte Stelle. Die Prüfung greift auch: ein fremder Host und
ein `http`-Schema werden abgewiesen.

**Die Fehlerfälle sind sauber unterscheidbar** und taugen als Vorlage für die
definierten Fehler aus M2-09a:

| Fall | Ausnahme aus `zarr` 3.1.6 |
|---|---|
| unbekanntes Band (`…/r10m/b99`) | `ArrayNotFoundError` |
| fehlende Gruppe (`quality/l2a_quicklook/r10m/tci`) | `ArrayNotFoundError` |
| Gruppe statt Array (`…/r10m`) | `NodeTypeValidationError` |

**Und eine Falle, die 1,5 GB gekostet hat.** Drei Bänder über
`Dataset.to_dataarray(dim="band")` zu stapeln sieht aus wie die naheliegende Art,
eine Echtfarb-Kachel zu bauen. Gemessen materialisiert dieser Aufruf die Arrays
**vollständig**: drei Abrufe ohne Byte-Range, je ein ganzer 158-MB-Shard, bevor
überhaupt ein Fenster gewählt ist. Danach kostet die Kachel scheinbar null
Requests — ein Messergebnis, das auf den ersten Blick zu schön aussah und
deshalb nachgeprüft wurde. Richtig ist, **jedes Band einzeln zu fenstern und erst
die Fenster zu stapeln**; so kostet dieselbe Kachel 6 Requests und 3,75 MB
(§12.4).

### 12.10 Welche Zoomstufen der Viewer freigeben sollte

Die Pyramide deckt sechs Stufen von 720 m bis 10 m. Welcher Zoomstufe eine Stufe
entspricht, hängt an der Breite: eine Web-Mercator-Kachel hat bei 34° N eine um
den Faktor 2,7 gröbere Bodenauflösung als bei 72° N. Gemessen:

| | 46,4° N (Szene B) | 71,6° N (Szene A) |
|---|---|---|
| native 10 m | z13–z14 | z12 |
| native 60 m | z11 | z10 |
| native 360 m | z9 | z7 |

**Empfehlung: z8 bis z14 freigeben**, mit `r10m` als feinster Stufe und Überzoom
darüber.

- **Untere Grenze z8, weil dort eine Kachel etwa eine Szene ist.** Bei 46° N
  deckt eine z8-Kachel 108 km, eine Szene ist 110 km breit; bei 34° N sind es
  130 km. Unterhalb von z8 zeigt eine Kachel mehrere Szenen — das ist die
  Aufgabe der Coverage-Heatmap (`adr/0004`), nicht des Kachelpfads.
- **Obere Grenze z14, weil darüber keine Daten mehr kommen.** Überzoom auf
  `r10m` ist dabei ausdrücklich erlaubt und **kostet weniger**, nicht mehr: das
  gelesene Fenster wird kleiner.
- **Die Stufe wird gerechnet, nicht nachgeschlagen.** Aus der Bodenauflösung der
  angefragten Kachel und der Auflösung der Stufen, nicht aus einer festen
  Zuordnung Zoom → Gruppe. Sonst wird am Nordrand des Bestands zwei Stufen zu
  fein gelesen.
- **Kostenband dieser Wahl:** z8–z10 unter 1,3 MB je Band und unter 0,4 MB für
  eine Echtfarb-Kachel; ab z11 rund 1–4,3 MB je Kachel, Echtfarbe rund 3,7–4,3 MB
  und rund 5 s kalt. Ohne HTTP-Cache ist das zu viel für flüssiges Schwenken —
  der Cache ist bei diesem Datensatz keine Feinarbeit, sondern Voraussetzung
  (§3.6 sagte das schon, und es gilt unverändert).

### 12.11 Empfehlung und was für M2-09b daraus folgt

**Zum Datensatz: Ja — `sentinel-2-l2a-zarr3` trägt als zweiter Datensatz.**
Option A ist gemessen und besteht die Kriterien aus §2 bis auf eines. K4
(erreichbar) ist mit der Freigabe erfüllt; K7 (kachelbar) und K8 (Lesekosten) sind
**besser** als §3 befürchtet hat, weil Sharding, sechs Stufen und CRS im Store
dazukommen; K10 (Quicklook) bleibt verletzt, hat aber einen billigen, belegten
Ersatz (§12.7). **K9 (Dauerhaftigkeit) bleibt verletzt und ist schärfer
geworden** — die Collection heißt selbst „staging" (§12.6). Das ist der bewusst
in Kauf genommene Preis aus §5 Option A; er ist jetzt nur genauer beziffert.
Sollte Otto ihn doch nicht zahlen wollen, ändert sich an §4.2 nichts: Keiner der
Nicht-STAC-Kandidaten ersetzt ihn in M2, und es bliebe der Rückfallweg aus §8 F7.

**Für M2-09b, der Reihe nach:**

1. **Der Store muss Byte-Ranges können** — `get` mit `RangeByteRequest`,
   `OffsetByteRequest`, `SuffixByteRequest` und `get_partial_values`. Ohne das
   holt `zarr` je Kachel den ganzen 158-MB-Shard. Das ist die eine Zeile, an der
   der Datensatz steht und fällt.
2. **Die Auflösungsstufen kommen aus dem Store, nicht aus dem Item.** Das Item
   weist nur `r10m`/`r20m`/`r60m` aus; `r120m`, `r360m` und `r720m` stehen im
   `multiscales`-Attribut von `measurements/reflectance` (§12.3). §6 Punkt 2
   („Stufenwahl aus `gsd`/`raster:spatial_resolution`") ist insoweit zu
   korrigieren — richtig ist: `multiscales` aus dem Store lesen, das Item als
   Rückfall. Dass dieses `multiscales` einer **v0.1-Pilotkonvention** folgt, ist
   dabei hinzunehmen und im Registry-Eintrag zu vermerken; bricht sie, bricht
   nur die Stufenwahl, nicht der Lesepfad.
3. **Die CRS liegt im Store** und stimmt mit `proj:code` überein (gemessen
   `EPSG:32632` beiderseits). §6 Punkt 2 verlangte sie „aus dem STAC-Item, nicht
   aus dem Store" — das bleibt als **Rückfall** richtig, ist aber nicht mehr der
   Normalfall. Das Registry-Feld aus §7 Punkt 7 wird trotzdem gebraucht, weil der
   Reader beide Fälle können muss: Das synthetische Mini-Zarr aus M2-09a hat
   bewusst keine CRS im Store.
4. **`AccessInfo.cors = True`** für diesen Datensatz (§12.8). Der serverseitig
   gerenderte Quicklook aus §6 Punkt 5 bleibt trotzdem — aber aus dem anderen
   Grund: nicht weil CORS fehlt, sondern weil es überhaupt kein Vorschaubild
   gibt. Die Bedingung aus `adr/0006` §7 Punkt 4 ist damit erfüllt, der Anlass
   entfällt.
5. **`asset_hosts` des Registry-Eintrags: `data.eodc.eu`.** Nur dieser Host; die
   älteren Tutorial-Produkte auf `objects.eodc.eu` gehören zur Collection
   `sentinel-2-l2a`, die nicht aufgenommen wird.
6. **Beim Öffnen `zarr_format=3` setzen** — halbiert die Anfragen (11 → 5,
   §12.4). Für mehrere Bänder lohnt stattdessen die Gruppe über die
   konsolidierte Wurzel (3 Anfragen, 0,5 MB, CRS inbegriffen).
7. **Bänder nie über `to_dataarray`/`to_array` stapeln** (§12.9). Einzeln
   fenstern, dann die Fenster stapeln.
8. **Statistik auf `r720m` oder `r360m`** rechnen, einmal je Item, in den
   Statistik-Cache (D13, 30 Tage). Auf `r60m` kostet dieselbe Statistik 4,85 MB
   statt 0,04 MB, bei rund 5 % Unterschied im `p98`.
9. **Der Cache arbeitet nach Frist, nicht nach Revalidierung** — die Quelle
   sendet weder `ETag` noch `Cache-Control` (§12.8).
10. **`zipped_product` nicht in den Registry-Eintrag.** Es liegt mit 1,2 GB auf
    dem jetzt offenen `data.eodc.eu` (§12.1); die Sperre, auf die F1 sich
    verlassen hat, greift dafür nicht mehr.
11. **Die STAC-1.1-Normalisierung aus §6 Punkt 4 bleibt Wort für Wort gültig.**
    Ergänzung: `proj:bbox` ist in dieser Collection korrekt in Metern; die Prüfung
    „verwerfen, wenn sie nicht zur CRS passt" bleibt trotzdem nötig, weil sie im
    Bestand von `sentinel-2-l2a` in Grad steht (§3.4).
12. **`sentinel-2-l2a` und `sentinel-2-l2a-zarr3` führen für aktuelle Tage
    dieselben Item-IDs** — zwei Sichten auf dasselbe Produkt, v2-Gruppenlayout
    gegen v3-Shard-Store (gemessen an
    `S2C_MSIL2A_20260919T141841_N0512_R096_T26WME_20260919T161612`). Die Registry
    führt nur `…-zarr3`; dann kollidiert nichts. Aufnehmen ließen sich die beiden
    nicht nebeneinander, ohne die ID-Eindeutigkeit der föderierten Suche zu
    verletzen.
13. **Coverage bleibt `CoverageProvider.SAMPLE`** (§6 Punkt 3, unverändert):
    `numberMatched` fehlt weiterhin, `/aggregations` gibt es nicht. Neu ist nur
    die Größenordnung, gegen die die Stichprobe anzutreten hat: rund 1 300 Items
    je Tag, 1 802 MGRS-Kacheln in drei Tagen (§12.6).

### 12.12 Die sechs offenen Punkte aus §9.1, beantwortet

| Punkt aus §9.1 | Antwort |
|---|---|
| Chunk-Zuschnitt der `…-zarr3`-Collections | **Feiner als befürchtet:** Shard 11264², aber Innenchunk 1024² mit Sharding-Index (§12.3) |
| Georeferenzierung | **CRS liegt im Store** (`spatial_ref`, `crs_wkt`) und stimmt mit `proj:code` überein (§12.3) |
| Übersichtsstufen | **Sechs statt drei**, mit `multiscales` v0.1; das Item weist nur drei davon aus (§12.3) |
| Lesekosten je Kachel | **Gemessen** (§12.4); die Zahlen aus §3.6 sind erwartungsgemäß nicht übertragbar — die echten sind niedriger |
| Existenz der Objekte | **Ja**, für `…-zarr3` durchgehend gelesen (§12.3–12.5) |
| Ob die 2017er Items von `sentinel-2-l2a` auf Objekte zeigen | **Ja.** `product/.zgroup` → 200, `.zmetadata` → 292 804 B auf `objects.eodc.eu`. `TCI_10m` löst auch dort nicht auf (§12.7) |

### 12.13 Fragen an Otto

**F8 — Bleibt es bei `sentinel-2-l2a-zarr3`, obwohl die Collection sich selbst
„staging" nennt?**
(a) **Ja, wie in §5 Option A entschieden** *(Empfehlung: der Preis war bekannt,
er ist jetzt nur genauer benannt; alles Technische trägt)*.
(b) Nein — dann greift der Rückfallweg aus §8 F7: M2 wird auf „Sentinel-2 plus
belegter Zarr-Lesepfad" abgenommen, der zweite Datensatz geht nach M3.

**F9 — Welche Zoomstufen gibt der Viewer frei?**
(a) **z8 bis z14, Überzoom darüber erlaubt** *(Empfehlung, §12.10)*.
(b) Enger: z8 bis z12, feinste Stufe `r20m` — höchstens rund 1,5 MB je Kachel,
dafür nie die native Auflösung.
(c) Weiter: z8 bis z16 — kostet nichts zusätzlich, zeigt aber Pixel, die es nicht
gibt.

**F10 — Woher nimmt der Reader die Auflösungsstufen?**
(a) **Aus `multiscales` im Store, Item als Rückfall** *(Empfehlung: nur so
kommen `r120m`, `r360m` und `r720m` überhaupt vor, §12.11 Punkt 2)*.
(b) Fest im Registry-Eintrag — unabhängig von der Pilotkonvention, aber je
Datensatz von Hand gepflegt.

### 12.14 Messanhang

**Erreichbarkeit (§12.1), Bestand (§12.6), Quicklook (§12.7):**

```
curl -sS -o /dev/null -w "%{http_code}" --max-time 25 https://<host>/
curl -sS "https://stac.core.eopf.eodc.eu/search?collections=sentinel-2-l2a-zarr3\
&limit=1&datetime=<start>%2F<ende>"
curl -sS "https://stac.core.eopf.eodc.eu/collections/sentinel-2-l2a-zarr3"
```

Das Durchblättern in §12.6 folgt der `next`-Marke (`token=next:<collection>:<id>`)
über 40 Seiten zu je 100 Items.

**Store, Shards, CORS (§12.3, §12.8).** `<store>` ist der `product`-Asset-Href
des Items, also
`https://data.eodc.eu/collections/EOPF_ZARR/products/cpm_v300/S02MSIL2A/<jjjj>/<mm>/<tt>/<produkt>.zarr`:

```
curl -sS "<store>/zarr.json"                                    # 500 563 B, 221 Knoten
curl -sS -I "<store>/measurements/reflectance/<stufe>/b04/c/0/0"  # Shard-Groesse
curl -sS -r 0-99 "<store>/measurements/reflectance/r10m/b04/c/0/0"  # 206, Range traegt
curl -sS -X OPTIONS -H "Origin: https://example.org" \
     -H "Access-Control-Request-Method: GET" "<store>/zarr.json"    # 204 + CORS-Kopfzeilen
```

Die Innenchunk-Größen in §12.3 stammen aus dem Sharding-Index: die letzten
`n * 16 + 4` Bytes des Shards, gelesen per `Range`, als `uint64`-Paare
(Offset, Länge) in C-Ordnung über das Innenchunk-Gitter, mit `crc32c` am Ende.

**Lesepfad (§12.4, §12.5, §12.9).** Wegwerf-venv im Kratzverzeichnis, `zarr`
3.1.6, `xarray` 2026.7.0, `rioxarray` 0.19.0, `rio-tiler` 9.4.6, `numpy` 2.4.6,
`morecantile` 7.1.0 auf Python 3.11.15 — dieselbe Zusammenstellung wie in §3.7.
Der Store implementiert `get`, `get_partial_values` und `exists`, prüft Schema
und Host und zählt Anfragen und Bytes; `list*` bleibt unimplementiert
(`supports_listing = False`), geöffnet wird mit `zarr.open_array(path=…,
zarr_format=3)`. Die Zähler liegen bewusst im Modul, nicht in der Instanz: Beim
Kopieren der `DataArray` (`rio.write_crs`) wird auch der Store kopiert, und eine
erste Messung zählte deshalb null Anfragen bei echten Bilddaten. Kacheln über
`morecantile` `WebMercatorQuad`. Die Skripte sind nicht Teil des Repos.
