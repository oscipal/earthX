# ADR 0009 — Dritte Quelle: erste Nicht-STAC-Quelle mit materialisierten Items

- **Status:** **Angenommen** von Otto am 2026-09-23. Die sechs Fragen aus §9
  sind dort beantwortet: **F1** Copernicus DEM GLO-30 direkt aus dem Bucket;
  **F2** dritter Datensatz und zugleich Nicht-STAC-Quelle; **F3** Items in
  pgstac, erzeugt von einem Einmal-Befehl in `discovery`; **F4** entfällt, die
  Lizenz des DEM ist eingestuft (`adr/0003` §11.1); **F5** Coverage aus den
  Kachel-Umrissen, als Fläche, `completeness = complete` (Lesart in §6);
  **F6** Zenodo für M5 vorgemerkt, nur als Discovery- bzw. Metadatenquelle.
  §8 gibt den entschiedenen Stand wieder; §10 nennt, was M3-11 noch klären muss.
- **Datum:** 2026-09-23
- **Aufgabe:** M3-01 laut `docs/plans/m3-dritte-quelle-und-interface.md` §4.
- **Autonomiestufe:** C — nur gemessen, gelesen und berichtet. Kein Produktivcode
  geändert, keine Registry, keine Allowlist der Plattform, keine Daten ins Repo.
- **Grundlage:** `ENTSCHEIDUNGEN_2026-09-18.md` §2, §5; `KLAERUNGEN.md` B8, B9,
  B11, B13; `architekturplan.md` 3.1, 3.2, 5.1, 5.2, 6.1, 6.2, 15.1;
  `adr/0003` §10, §11.1 (Copernicus DEM); `adr/0004` §5 (Coverage-Wege,
  Einmal-Produkte); `adr/0005` Regel I; `adr/0007` §3.10, §4.2 (ARCO-ERA5,
  Kandidatenfeld); Plan M3 P1, P2, P4; Entscheidungslog vom 23.09.2026.
- **Betroffen:** Zuschnitt von M3-11 in Fassung 2 des
  M3-Plans; `catalog/registry.py` (`SourceInfo`, `CoverageInfo`);
  `api/federating_client.py`, `api/tiler.py` (Item-Quelle); M3-14.

---

## Methode und Belegstufen

Gemessen in einer Cloud-Sitzung am 23.09.2026, rund 17:30–18:30 UTC.
Belegstufen wie in `adr/0004` und `adr/0007`:

- **M** — in dieser Sitzung selbst gemessen; Befehl bzw. Adresse im Text oder im
  Messanhang §12.
- **P** — am Primärdokument gelesen (Lizenzseite, README, Konfigurationsdatei,
  Record-Metadaten, Quelltext im Repo).
- **S** — Suchtreffer mit Link, Primärdokument nicht gelesen.
- **A** — eigene Ableitung aus M/P/S; ein Argument, kein Beleg.

Wo ein Beleg fehlt, steht „unbelegt“.

**Umfang der Abrufe.** Rund 110 Anfragen über etwa eine Stunde, zusammen rund
95 MB, davon 82 MB für zwei Hansen-Kacheln (§3.2) und 2,4 MB für einen
ARCO-ERA5-Chunk. Kein Produkt vollständig heruntergeladen. Gelesen wurde über
`curl` und kleine Skripte im Kratzverzeichnis der Sitzung, mit dem Python des
Projekt-venv (rasterio 1.4.4, rio-tiler 9.4.6 — dieselben Versionen, auf denen
`readers/cog.py` läuft), aber **ohne** `earthx`-Code: `gateway` erreicht die
Quellen aus einer Sitzung nicht (M2-13). Die Kachelmessungen zeigen deshalb, was
die Bibliothek unter `readers` kann, nicht den vollen Pfad durch `gateway`.

**Allowlist (§1.3 des M3-Plans).** Alle vier Kandidaten-Hosts antworten:
`zenodo.org` (neu freigegeben), `storage.googleapis.com`,
`copernicus-dem-30m.s3.amazonaws.com` **[M]**. Kein Kandidat leitet auf einen
anderen Host um; die einzige beobachtete Weiterleitung ist Zenodo-intern
(`/api/records/<alt>` → `/api/records/<neu>`, relativer `location`) **[M]**.
**Gesperrt** blieben die Dokumentations-Hosts `developers.zenodo.org`,
`blog.zenodo.org`, `about.zenodo.org`, `help.zenodo.org`, `forum.ecmwf.int`,
`cds.climate.copernicus.eu`, `developmentseed.org` — dort beruhende Aussagen
tragen **[S]** oder sind über GitHub am Quelltext belegt **[P]**.

---

## 1. Kontext und Frage

`architekturplan.md` 15.1 führt als Inkrement 3 die erste Nicht-STAC-Quelle mit
materialisierten Items: Sie beweist die Adapter-Nahtstellen, und erst danach
folgt die Interface-Reflexion (M3-14). 6.1 begründet, warum es eine
Nicht-STAC-Quelle sein muss: sonst wird das Interface STAC-förmig. 5.2 nennt die
Ausnahme vom föderierten Item-Weg: Quellen ohne Such-API — „statische Buckets,
Zenodo-Dateien, Tile-adressierte Quellen“ — bekommen einmalig erzeugte Items im
eigenen pgstac, für große statische Bestände alternativ stac-geoparquet.

Otto entscheidet nach diesem ADR drei Dinge (P1, P2, P4):

1. **Welche Quelle** — aus Hansen GFC, Copernicus DEM direkt aus dem Bucket,
   einem Zenodo-Record, ARCO-ERA5.
2. **Welche Rolle Copernicus DEM** spielt — Nicht-STAC-Quelle oder vierter
   Datensatz.
3. **Wie materialisiert wird** — Ablage (pgstac oder stac-geoparquet) und
   ausführender Ort (Loader in `catalog` oder Prozess `harvester`).

Dazu gehört eine Lizenz-Einstufung nach B11, die immer Otto trifft.

## 2. Kriterien

Aus P1, ergänzt um die Betriebsfragen, die die Messung aufgeworfen hat:

| # | Kriterium | Herkunft |
|---|---|---|
| K1 | Keine Such-API — die Quelle zwingt zur Materialisierung | P1; architekturplan 5.2 |
| K2 | Token-frei, anonymer Zugriff über `https` | ENTSCHEIDUNGEN §1; adr/0007 §3.10 |
| K3 | Lizenz nach B11 einstufbar, am Primärdokument | P1; B11 |
| K4 | `readers` unverändert: echte COGs bzw. vorhandener Zarr-Pfad | P1; M3-Abnahme Punkt 1 |
| K5 | Art der Coverage passt auf einen vorhandenen Weg aus `adr/0004` | P1 |
| K6 | Trägt die Last eines Kachel-Viewers ohne Drosselung durch die Quelle | neu, aus §3.3 |
| K7 | Strukturell anders als die beiden STAC-Quellen — Wert für M3-14 | architekturplan 6.1 |

## 3. Was gemessen wurde

### 3.1 Copernicus DEM GLO-30, direkt aus dem Bucket — **[M]**

**Zugriff.** `https://copernicus-dem-30m.s3.amazonaws.com/` antwortet anonym mit
`200`; `?list-type=2` liefert ein `ListBucketResult` ohne Signatur; Region laut
Kopfzeile `eu-central-1` **[M]**. Range-Read auf eine Kachel: `206 Partial
Content` **[M]**.

**Echte COGs.** Geprüft an `Copernicus_DSM_COG_10_N00_00_E006_00_DEM.tif`
(3,7 MB) und `…_S11_00_W056_00_DEM.tif`: GDAL-Strukturmetadaten
`LAYOUT=IFDS_BEFORE_DATA`, erstes IFD bei Byte 192, `LAYOUT=COG`, Blöcke
1024 × 1024, DEFLATE, Overviews 2/4/8, `float32`, EPSG:4326, 3600 × 3600 px auf
1° × 1° **[M]**. Das deckt sich mit `readme.html` im Bucket (Blockgröße, drei
Overview-Stufen, schmalere Kacheln polwärts) **[P]**. **Kein `nodata`** gesetzt
**[M]**; Meere haben laut `readme.html` gar keine Kacheln („one can assume
height values equal to zero“) **[P]**.

**Kachel über rio-tiler, unverändert.** z8: 1,05 s, 0,59 MB; z10: 1,36 s,
2,2 MB; z11: 0,56 s (jeweils kalt, ohne Header-Cache) **[M]**.

**Bestand.** `tileList.txt` im Bucket: **26 450** Kacheln, eine je Zeile, 1,1 MB,
`Last-Modified` 2022-05-09 **[M]**. Je Kachel ein Präfix
`Copernicus_DSM_COG_10_<N|S>dd_00_<E|W>ddd_00_DEM/` mit dem DEM-COG und
Nebendateien (`AUXFILES/…EDM|FLM|HEM|WBM.tif`, `PREVIEW/…QL.tif`, eine
Metadaten-XML, `INFO/eula_F.pdf`); Zeitstempel der Stichprobe 2022-05-09 **[M]**.
Die Lage einer Kachel folgt vollständig aus ihrem Namen (`readme.html`,
Abschnitt „Data structure“) **[P]**. Eine Zeitachse gibt es nicht: ein Produkt,
eine Fassung.

**Zu P2: kein STAC im Bucket, aber STAC anderswo.** `catalog.json`,
`collection.json`, `stac/catalog.json` im Bucket: `404` **[M]**. Der Bucket hat
also weder einen statischen Katalog noch eine Such-API; maschinenlesbar ist nur
`tileList.txt` plus Namensschema. **Aber:** Earth Search v1 — die Quelle des
ersten Datensatzes — führt dieselben Daten als Collection **`cop-dem-glo-30`**
mit `numberMatched` **26 450**, ein Item je Kachel, `datetime`
2021-04-22 für alle **[M]**. Die Asset-`href` dort ist **`s3://copernicus-dem-30m/…`**,
nicht `https` **[M]** — `gateway` weist `s3` ab (`gateway/policy.py`,
`https`-only, adr/0007 §3.10) **[P]**. Der Lizenz-Link dieser Collection zeigt
auf ein **anderes** Dokument (`CSCDA_ESA_Mission-specific+Annex.pdf` auf
`spacedata.copernicus.eu`) als die in `adr/0003` §11.1 geprüfte GLO-30-F-Lizenz
**[M]**.

**CORS.** Kein `Access-Control-Allow-Origin` auf `GET`, `OPTIONS`-Preflight `403`
**[M]**. Für serverseitiges Kacheln ohne Belang.

**Ratengrenzen.** Keine beobachtet. S3 dokumentiert mindestens 5 500
`GET`/`HEAD` je Sekunde und Präfix **[S]** ([AWS S3 Performance](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html)).
Jede DEM-Kachel liegt unter einem eigenen Präfix.

**Lizenz.** Am Primärdokument geprüft in `adr/0003` §11.1, B11-Stufe
*Processing* **angenommen am 18.09.2026** **[P]**. Neu ist nur der abweichende
Lizenz-Link in der Earth-Search-Collection (oben).

### 3.2 Hansen Global Forest Change — **[M]**

**Zugriff.** `storage.googleapis.com/earthenginepartners-hansen/` listet anonym;
aktuelle Fassung **`GFC-2025-v1.13/`** neben allen älteren (`GFC-2015-v1.3` …
`GFC-2024-v1.12`), dazu fremde Produkte desselben Labors im selben Bucket
**[M]**. Range-Read `206`, `access-control-allow-origin: *`, `cache-control:
public, max-age=3600` **[M]**.

**Bestand v1.13.** 2 599 Objekte, 1,68 TB: je 504 Granulen (10° × 10°) für
`treecover2000`, `gain`, `datamask`, `first`, dazu je **280** für `lossyear` und
`last` (Land) **[M]**. Je Ebene eine URL-Liste `<ebene>.txt`. **`last.txt` führt
504 URLs, von denen 224 im Bucket fehlen** (`404`, gemessen an
`…last_80N_180W.tif`) **[M]** — die Liste ist nicht verlässlich; eine
Materialisierung müsste das Listing nehmen, nicht die Textdatei. v1.12 hat
denselben Aufbau **[M]**. Jede Jahresfassung liegt unter einem neuen Präfix
(Aktualisierung = neuer Bestand, nicht Nachlieferung). Eine Zeitachse steckt nur
**im Pixelwert** (`lossyear` 1–25 = Verlustjahr 2001–2025), nicht in Dateien
**[P]** (`download.html` im Bucket).

**Keine COGs.** `lossyear_00N_000E` und `treecover2000_10S_060W`: 40 000 ×
40 000 px, **Streifen** (Block 1 × 40 000), nicht gekachelt, LZW,
**keine Overviews**, erstes IFD bei Byte 8, keine GDAL-Strukturmetadaten, kein
`nodata` **[M]**. rio-tiler öffnet die Dateien und warnt `NoOverviewWarning`
**[M]**. Kosten je Kachel über Amazonien (`treecover2000_10S_060W`, 646 MB):

| Zoom | Dauer | übertragen |
|---|---|---|
| z10 | 2,48 s | **17,8 MB** |
| z8 | 7,95 s | **64,1 MB** |
| zum Vergleich DEM z8, gleiche Stelle | 1,05 s | 0,59 MB |

**[M]** (GDAL-Netzstatistik, `CPL_VSIL_SHOW_NETWORK_STATS`). Unter z8 wächst
der Aufwand weiter, bis ganze Dateien gelesen werden **[A]**. Eine token-freie
COG-Fassung von GFC wurde nicht gefunden **(unbelegt)**; `tiles/gfc_v1.13/` im
selben Bucket enthält fertig gerenderte JPEG-/PNG-Kacheln, keine Daten **[M]**.

**Lizenz.** `download.html` im Bucket: „This work is licensed under a Creative
Commons Attribution 4.0 International License … even commercially“; Anzeige-
Hinweis „Source: Hansen/UMD/Google/USGS/NASA“, Zitat Hansen et al. 2013
**[P]**. Außerdem der Hinweis des Labors, Flächen nicht aus Pixelzählungen zu
schätzen **[P]** — relevant für spätere Operatoren, nicht für die Anzeige.

### 3.3 Zenodo — **[M]**

**Auswahl des Records.** Gesucht über die Zenodo-API (`"cloud optimized
geotiff"`, Typ Datensatz, 314 Treffer) **[M]**. Ausgeschieden sind Records, deren
Dateien großteils **nicht auf Zenodo** liegen — etwa die Global-Pasture-Watch-
Records, die je drei Jahre auf Zenodo und den Rest per CSV auf
`s3.opengeohub.org` führen **[M]** (fremder Host, nicht gemessen). Zwei Records
blieben, beide mit allen Daten auf `zenodo.org` und beide echte COGs:

| | **Z1: MODIS MCD12Q1 Landbedeckung** | Z2: GEDTM30 v1.2 |
|---|---|---|
| Record, DOI | 8367523, `10.5281/zenodo.8367523` (Konzept `…8338927`) | 18887460, `10.5281/zenodo.18887460` (Konzept `…14900180`) |
| Lizenz laut Record | **CC-BY-SA-4.0** **[P]** | **CC-BY-4.0** **[P]** |
| Inhalt | 168 COGs = 8 Klassifikationen × 21 Jahre (2001–2021), 500 m, global **[M]** | 3 COGs (Höhe, Streuung, Maske), 240 m, global, statisch **[M]** |
| Größe | 35 GB | 21,5 GB |
| Aufbau | BigTIFF, `LAYOUT=COG`, Blöcke 1024², Overviews bis 1/128 **[M]** | BigTIFF, `LAYOUT=COG`, Blöcke 2048², Overviews bis 1/513 **[M]** |
| Zeitachse | ja, ein Jahr je Datei | keine |
| Auffällig | Titel sagt „2001–2022“, Dateien enden 2021 **[M]** | Record-Text: „Use for testing purposes only“; die 30-m-Fassung liegt extern **[P]** |

**Empfohlen als Zenodo-Vertreter ist Z1**, weil er mit 21 Zeitschritten und 168
Dateien die Materialisierung wirklich fordert (Items mit `datetime`, Assets je
Klassifikation) und der Record kein Testvorbehalt trägt. Die SA-Lizenz ist dabei
eine eigene Frage an Otto (§9 F4).

**Zugriff.** Dateien unter `https://zenodo.org/records/<id>/files/<name>` und
`/api/records/<id>/files/<name>/content`: Range-Read `206`, `accept-ranges:
bytes`, **keine** Weiterleitung auf einen Speicher-Host **[M]**. CORS `*` am
API-Pfad **[M]**. rio-tiler rendert Z1 unverändert: z3 2,2 s, z8 1,5 s, je
**2 `HEAD` + 2–3 `GET`** und 180–230 kB **[M]**.

**Ratengrenze — der entscheidende Befund.** Jede Antwort, auch jeder Range-Read
einer Datei, trägt `x-ratelimit-limit: 133` mit Rücksetzung nach unter einer
Minute; die Suche trägt `x-ratelimit-limit: 30` **[M]**. Die Konfiguration von
Zenodo im Quelltext sagt dasselbe: `RATELIMIT_GUEST_USER = "8000 per hour;133
per minute"`, `records.search` und OAI-PMH je `30 per minute` **[P]**
([`zenodo-rdm/invenio.cfg`](https://github.com/zenodo/zenodo-rdm/blob/master/invenio.cfg)).
Die Grenze gilt je anonymer Gegenstelle — für die Plattform ist das **eine IP
für alle Nutzer** **[A]**. Bei 4–5 Anfragen je kalter Kachel sind das rund
**30 Kacheln pro Minute für die ganze Plattform**, mit einem künftigen
Header-Cache (Log, offen) vielleicht 60–130 **[A]**. Eine Kartenansicht braucht
15–30 Kacheln **[A]**. Zenodo trägt damit eine Anzeige für einen Nutzer zur
Zeit, keinen Viewer.

**Robustheit.** 2 von rund 30 Anfragen an `zenodo.org` brachen mit
`SSL_ERROR_SYSCALL` ab und liefen beim Wiederholen durch **[M]** — ob das an
Zenodo oder am Proxy der Sitzung lag, ist **unbelegt**.

**Aktualisierung.** Neue Fassungen sind neue Records unter demselben
Konzept-DOI; `links.versions` führt sie **[M]**. Nachlieferung heißt also:
Konzept-DOI abfragen, neuen Record materialisieren, alten ersetzen **[A]**.

### 3.4 ARCO-ERA5 — **[M]**

**Zugriff.** `storage.googleapis.com/gcp-public-data-arco-era5/` anonym; der im
README empfohlene Store ist `ar/full_37-1h-0p25deg-chunk-1.zarr-v3` **[P]**
([README](https://github.com/google-research/arco-era5)). Das „v3“ im Namen ist
die Fassung des Datensatzes, **nicht** das Zarr-Format: `zarr.json` fehlt
(`404`), `.zmetadata` (133 kB, `zarr_consolidated_format: 1`), `.zgroup`,
`.zattrs` sind da — **Zarr v2** **[M]**. Kein CORS-Kopf auf `GET` **[M]**.

**Aufbau.** 277 Variablen; z. B. `2m_temperature` mit Form 1 323 648 × 721 ×
1440, Chunk **eine Stunde × ganze Erde** (2,35 MB je Chunk), Dimensionen
`time`/`latitude`/`longitude`, Längen **0 bis 359,75**, Breiten 90 bis −90
**[M]**. Keine CRS-Angabe, kein `spatial_ref` **[M]**. Die Zeitachse beginnt 1900
und reicht bis 2051; beschrieben ist nur 1940-01-01 bis 2026-06-30 (ERA5) bzw.
2026-09-17 (ERA5T), `last_updated` **heute** **[M]**; unbeschriebene Chunks
antworten `404` **[M]**.

**Gegen `readers`.** `zarr_reader.py` öffnet fest mit `zarr_format=3` (`ZARR_FORMAT
= 3`, Z. 91, 601) und verlangt eine CRS aus Item oder Store (`MissingCrs`,
Z. 723–730) **[P]**. ARCO-ERA5 bräche also schon beim Öffnen; dazu kämen die
Zeitdimension als dritte Achse und die 0–360-Längen **[A]**. **K4 ist verletzt,
ohne Spielraum.**

**Lizenz.** README: Nutzung „according to the terms of the Copernicus license“,
Pflichthinweis „Contains modified Copernicus Climate Change Service information“
**[P]**. Seit 02.07.2025 ersetzt CC-BY 4.0 die Copernicus-Lizenz im Climate Data
Store **[S]** ([ECMWF-Forum](https://forum.ecmwf.int/t/cc-by-licence-to-replace-licence-to-use-copernicus-products-on-02-july-2025/13464));
ob das für diese Kopie gilt, ist **unbelegt** (wie schon `adr/0007` §4.2).

### 3.5 Was der Code heute für eine materialisierte Quelle mitbringt — **[P]**

Am Code von `main` (Stand #74) gelesen:

- **Suche geht schon.** `api/federating_client.py::_dispatch_search` gibt jede
  Collection **ohne** `earthx:source.adapter` an `super()` weiter, also an
  stac-fastapi-pgstac. Items im eigenen pgstac wären damit ohne neuen Suchcode
  über `/stac/search` findbar, samt Paging und CQL2 (Z. 277–316).
- **Aber `earthx:source` vermischt zwei Fragen.** `SourceInfo.adapter` ist
  Pflicht (`catalog/registry.py`, Z. 199–214), und genau dieses Feld entscheidet,
  ob föderiert wird. Eine materialisierte Quelle hat einen Adapter (für die
  Erzeugung der Items), wird aber nicht föderiert.
- **Die Kachel- und Download-Route holt Items nur über den Adapter**
  (`api/tiler.py::build_item_source` → `adapters.get_item`, Z. 495–511). Für
  Items in pgstac fehlt dieser Weg.
- **Coverage.** `CoverageProvider.LOCAL_SQL` ist definiert, aber nicht gebaut
  (`api/coverage_route.py`, Z. 56, 88–95: `501`). Der Weg für Einmal-Produkte
  (`single_coverage_product` → Ausdehnung aus der Collection) besteht
  (Z. 82–87).
- **`catalog/load.py` lädt nur Collections**, nie Items (`catalog/pgstac.py`,
  Z. 95–100). `pypgstac` 0.9.12 ist gepinnt und kann Items laden
  (`insert`, `ignore`, `upsert`, `delsert`, `insert_ignore`) **[M]**.
- **Importregeln:** `catalog` darf `adapters` nicht importieren; `discovery`
  darf `adapters`, `catalog` und `gateway` (`.importlinter`) **[P]**.

## 4. Kriterienmatrix

| | K1 keine Such-API | K2 token-frei | K3 Lizenz | K4 `readers` unverändert | K5 Coverage | K6 Last | K7 Wert für M3-14 |
|---|---|---|---|---|---|---|---|
| **DEM-Bucket** | ja, nur `tileList.txt` **[M]**; dieselben Daten aber auch als STAC bei Earth Search **[M]** | ja **[M]** | *Processing*, **angenommen** **[P]** | **ja**, echte COGs, Kachel gerendert **[M]** | Einmal-Produkt mit Lücken (§6) | S3, keine Grenze beobachtet **[M]/[S]** | mittel: Liste + Namensschema, kein Katalog, keine Zeit |
| **Hansen GFC** | ja **[M]** | ja **[M]** | CC-BY-4.0 **[P]** | **nein**: keine COGs, 64 MB je z8-Kachel **[M]** | Einmal-Produkt je Fassung | GCS trägt, aber jede Kachel ist teuer **[M]** | hoch: Jahresfassungen als neue Präfixe, Zeit im Pixel |
| **Zenodo Z1** | ja für Dateien; Record-API ist Suche über Records, nicht über Szenen **[M]** | ja **[M]** | CC-BY-SA-4.0 **[P]** | **ja**, echte COGs, Kachel gerendert **[M]** | 21 Jahreskarten, je global: Einmal-Produkt je Zeitschritt | **nein**: 133/min, 8000/h je IP **[M]/[P]** | **hoch**: Record/DOI/Versionen, Dateien statt Szenen |
| **ARCO-ERA5** | ja **[M]** | ja **[M]** | Copernicus bzw. CC-BY, für die Kopie **unbelegt** | **nein**: Zarr v2, keine CRS, Zeitachse **[M]/[P]** | Datenwürfel, keine Footprints | GCS trägt | sehr hoch, aber als Würfel, nicht als Items |

**Zusammengefasst:** K4 schließt Hansen und ARCO-ERA5 für M3 aus. K6 macht
Zenodo als **Kachelquelle** untauglich, solange es keinen Kachel-Cache vor der
Quelle gibt (CDN, M6). Übrig bleibt der DEM-Bucket — mit dem Makel, dass es
dieselben Daten auch als STAC gibt.

## 5. Zu P2: Zählt der DEM-Bucket als Nicht-STAC-Quelle?

**Ja, der Bucket selbst ist eine „Tile-adressierte Quelle“ im Sinne von
`architekturplan.md` 5.2**: kein Katalog, keine Such-API, nur eine Liste und ein
Namensschema, aus dem Lage und Ausdehnung folgen **[M]/[P]**. Ein Adapter muss
Items selbst erzeugen; nichts davon ist STAC-förmig vorgegeben.

**Aber** es gibt einen zweiten, STAC-förmigen Weg zu denselben Pixeln: Earth
Search `cop-dem-glo-30`. Daraus folgen zwei ehrliche Lesarten:

- **DEM als dritter Datensatz und Nicht-STAC-Quelle** (P2 „wenn ja“): Die
  Plattform materialisiert selbst, was Earth Search auch anbietet. Für den
  Architekturbeweis ist das richtig — die Nahtstellen werden an einer Quelle
  ohne API gebaut —, fachlich ist es Doppelarbeit, die man begründen muss. Die
  Begründung wäre: unabhängig von Earth Search, `https`-Hrefs statt `s3`, die
  in `adr/0003` geprüfte Lizenz statt des abweichenden Links.
- **DEM als vierter, föderierter Datensatz über Earth Search** (P2 „wenn
  nein“): billig, weil der Adapter besteht, aber mit zwei Nahtstellen-Befunden —
  `s3://`-Hrefs müssen auf `https` übersetzt werden (Zugriffsauflösung, §3.1),
  und die Lizenz-Angabe der Quelle weicht vom geprüften Dokument ab. Der Beweis
  „Nicht-STAC“ fehlte dann in M3 ganz.

**Entschieden (Otto, 23.09.2026, F2):** die erste Lesart — DEM aus dem Bucket
als dritter Datensatz und zugleich Nicht-STAC-Quelle.

## 6. Coverage je Kandidat (`adr/0004`)

`adr/0004` §5 kennt drei Wege: Upstream-Aggregation, eigenes SQL über
materialisierte Items (`local-sql`, noch nicht gebaut), ausgewiesene Stichprobe;
dazu für Einmal-Produkte die Ausdehnung aus der Collection
(`single_coverage_product`).

- **DEM:** Ein Zeitpunkt, 26 450 Kacheln. Eine Dichte wäre überall 1 oder 0 —
  also eine Anwesenheitskarte. Die Collection-`bbox` (global) wäre falsch, weil
  sie die nicht freigegebenen Länder **und** die Meere als abgedeckt zeigt
  (`readme.html`: „limited worldwide coverage“) **[P]/[A]**. Ehrlich ist die
  **Vereinigung der Item-Footprints**. Das ist technisch `local-sql` über eigene
  Items, fachlich aber „Ausdehnung allein“ nach ENTSCHEIDUNGEN §2 — eine Frage
  der Auslegung an Otto (§9 F5).

  > **Entschieden (Otto, 23.09.2026, F5): Lesart von ENTSCHEIDUNGEN §2.**
  > „Ausdehnung“ ist bei einem Einmal-Produkt die **Vereinigung der
  > Kachel-Umrisse**, nicht die `bbox` der Collection. Dargestellt wird sie als
  > **Fläche, nicht als Dichte-Heatmap**, weil jede Zelle genau eine Abdeckung
  > hätte. `completeness` ist `complete`: Die Plattform besitzt alle Items, es
  > gibt nichts, das gekappt oder nur als Stichprobe gezählt wäre. Die Lesart
  > gilt für das DEM; für weitere Einmal-Produkte ist sie die Vorgabe, bis Otto
  > anders entscheidet.
- **Zenodo Z1:** 21 globale Jahreskarten. Räumlich identisch, zeitlich ein
  Histogramm mit 21 Balken. Ausdehnung plus Zeit-Histogramm aus eigenen Items.
- **Hansen:** Einmal-Produkt je Fassung; Ausdehnung aus den tatsächlich
  vorhandenen Granulen (nicht aus `last.txt`, §3.2).
- **ARCO-ERA5:** Würfel ohne Footprints; Coverage wäre die Würfel-Ausdehnung
  aus den Metadaten (`valid_time_start/stop`).

In jedem Fall gilt `completeness` aus `adr/0004` Regel V: Bei eigenen Items ist
die Antwort vollständig (`complete`), weil die Plattform alle Items besitzt
**[A]**.

## 7. Materialisierung (P4)

### 7.1 Ablage: pgstac oder stac-geoparquet

| | pgstac | stac-geoparquet |
|---|---|---|
| Stand der Technik | Katalogkern der Plattform seit M1-04; `pypgstac load items` mit `upsert`/`delsert` **[P]**; in neueren pgstac-Fassungen ein Rust-Lader, der auch stac-geoparquet liest und dorthin exportiert **[P]** ([pgstac-Doku](https://github.com/stac-utils/pgstac/blob/main/docs/src/pypgstac.md)) | Spezifikation und Bibliothek `stac-geoparquet` 0.8.2 **[M]** ([Repo](https://github.com/stac-utils/stac-geoparquet)); abgefragt z. B. über `rustac`/DuckDB **[S]**; Development Seed sieht es als günstige Alternative für kleine bis mittlere, statische Kataloge **[S]** ([Blog](https://developmentseed.org/blog/2025-05-07-stac-geoparquet/)) |
| Suche über `/stac/search` | **schon da** (§3.5, `super()`-Pfad) | braucht ein zweites Such-Backend neben pgstac |
| Gemischte Suche (M3-13) | eigene Items liegen in derselben Datenbank wie die Collections | zwei Speicher zusammenführen |
| Menge | 26 450 bzw. 168 Items sind für pgstac klein **[A]** | Stärke erst bei Millionen Items |
| Neue Abhängigkeit | keine | `stac-geoparquet`, `pyarrow`, Abfrage-Engine |

**Empfehlung: pgstac.** stac-geoparquet lohnt sich erst bei Beständen, die
pgstac nicht mehr bequem trägt; das trifft auf keinen der vier Kandidaten zu.
Als Austauschformat (Export, Sicherung) bleibt es eine spätere Option.

### 7.2 Ort: Loader in `catalog` oder Prozess `harvester`

Der Plan nennt als Kandidat einen Loader in `catalog` „wie `python -m
earthx.catalog.load`“. **Das geht mit den Importregeln nicht ganz:** Das Wissen,
wie aus `tileList.txt` oder einem Zenodo-Record Items werden, ist
Protokollwissen der Quelle und gehört nach `adapters` (architekturplan 6.1,
Discovery/Suche); `catalog` darf `adapters` aber nicht importieren
(`.importlinter`) **[P]**. Drei Wege:

1. **Einmal-Befehl in `discovery`** (z. B. `python -m earthx.discovery.materialize
   <dataset>`): Der Adapter erzeugt die Items (liest über `gateway`),
   `catalog` schreibt sie nach pgstac (`upsert`). `discovery` darf beides
   importieren. Das ist der Ort, an dem in M5 der Harvester läuft; der Befehl
   ist dessen erste Stufe, ohne Zeitplan und ohne Review-Queue.
2. **Loader in `catalog`, der fertige Item-Dateien liest:** Ein Adapter schreibt
   NDJSON, `catalog` lädt. Hält die Regeln ein, aber legt eine Zwischendatei an
   — ein zweiter Stand neben der Quelle.
3. **Prozess `harvester` jetzt bauen** (geplant, mit Fortschritt in Postgres):
   vorgezogene M5-Arbeit, für eine Quelle ohne Änderungen nicht nötig.

**Empfehlung: Weg 1.** Er hält die Importregeln ohne Ausnahme ein, legt nichts
auf Platte und wächst in M5 zum Harvester, statt ersetzt zu werden.

### 7.3 Aktualisierung, wenn die Quelle nachliefert

- **DEM:** `tileList.txt` hat seit 2022-05-09 dieselbe `ETag` **[M]**. Neu laden,
  wenn sich `ETag` ändert; `upsert` genügt, weil Kachel-IDs stabil sind; entfallene
  Kacheln bräuchten `delsert` oder ein Löschen je Collection **[A]**.
- **Zenodo:** neue Fassung = neuer Record unter dem Konzept-DOI (§3.3). Die
  Collection zeigt auf **eine** Fassung; ein Wechsel ist ein bewusster Schritt,
  kein stilles Nachladen **[A]**.
- **Hansen:** neue Fassung = neues Präfix, jährlich **[M]**; wie Zenodo.

Den Lauf protokolliert das bestehende Feld `SourceInfo.harvest_run` (heute
ungenutzt) **[P]**.

### 7.4 Folgen für B13

Die Registry bleibt bis M5 Python (`DatasetConfig` in `catalog/datasets.py`) und
bleibt die einzige Quelle der **Collection**. Items sind keine Registry-Daten,
sondern aus der Quelle abgeleitet und jederzeit neu erzeugbar; es entsteht also
keine zweite gepflegte Wahrheit (B13 Punkt 3) **[A]**. Der Registry-Eintrag
braucht aber eine neue Angabe, ob Items föderiert oder materialisiert sind
(§3.5, `SourceInfo.adapter` trägt heute beides). Neue Felder ohne Vorgabewert
(B10); die Form schlägt M3-11 im Plan-Schritt vor.

## 8. Empfehlung und Entscheidung

Otto ist der Empfehlung am 23.09.2026 in allen Punkten gefolgt (§9); Punkt 2
ist dabei auf M5 und auf Metadaten eingegrenzt, Punkt 5 um die Darstellung als
Fläche ergänzt. Die Liste gibt den entschiedenen Stand wieder.

1. **Quelle: Copernicus DEM GLO-30 direkt aus dem Bucket**, zugleich dritter
   Datensatz und erste Nicht-STAC-Quelle (P2: ja). Er ist der einzige Kandidat,
   der K4 (gemessen) und K6 zugleich erfüllt, und die Lizenz ist schon
   entschieden. Der Preis: K7 ist nur „mittel“ — keine Zeitachse, und die Daten
   gäbe es auch als STAC.
2. **Zenodo nicht als Kachelquelle in M3.** Es ist die strukturell
   interessanteste Quelle, aber die Ratengrenze (133/min, 8000/h je IP) trägt
   keinen Viewer. **Entschieden:** für M5 vorgemerkt, **nur als Discovery- bzw.
   Metadatenquelle** (Record-Metadaten, OAI-PMH), nicht als Quelle für Kacheln.
3. **Hansen und ARCO-ERA5 nicht in M3**, beide wegen K4. ARCO-ERA5 ist ein
   Kandidat für die virtuellen Zarr-Stores bzw. Datenwürfel (Inkrement 7), Hansen
   für einen späteren Weg mit COG-Umwandlung — beides eigene Entscheidungen.
4. **Materialisierung:** Items in **pgstac**, erzeugt von einem Einmal-Befehl in
   **`discovery`** (Adapter erzeugt, `catalog` lädt per `upsert`).
5. **Coverage DEM:** Vereinigung der Kachel-Umrisse über eigenes SQL, nicht die
   globale `bbox`; als Fläche dargestellt, nicht als Dichte;
   `completeness = complete` (§6).
6. **Lizenz DEM:** wie eingestuft in `adr/0003` §11.1 — B11-Stufe *Processing*,
   Attribution mit vorgeschriebenem Wortlaut. Nichts neu einzustufen.

## 9. Fragen an Otto — beantwortet am 2026-09-23

**F1 — Quelle.**
1. Copernicus DEM direkt aus dem Bucket (Empfehlung)
2. Zenodo Z1, trotz Ratengrenze
3. Hansen GFC, mit Verstoß gegen K4 (Abnahme anpassen)
4. ARCO-ERA5, mit Umbau von `readers` (Abnahme anpassen)

**Antwort F1: (1)** Copernicus DEM GLO-30 direkt aus dem Bucket.

**F2 — Rolle von DEM (P2).**
1. DEM ist dritter Datensatz **und** Nicht-STAC-Quelle, aus dem Bucket (Empfehlung)
2. DEM wird vierter Datensatz, föderiert über Earth Search; die Nicht-STAC-Quelle
   ist dann Zenodo oder Hansen

**Antwort F2: (1)** dritter Datensatz und zugleich Nicht-STAC-Quelle.

**F3 — Materialisierung (P4).**
1. pgstac, Einmal-Befehl in `discovery` (Empfehlung)
2. pgstac, Loader in `catalog` über eine Item-Datei
3. stac-geoparquet

**Antwort F3: (1)** Items in pgstac, erzeugt von einem Einmal-Befehl in
`discovery`.

**F4 — Lizenz (B11, nur falls Zenodo Z1 gewählt oder vorgemerkt wird).**
CC-BY-SA-4.0 verlangt, Bearbeitungen unter derselben Lizenz weiterzugeben. Ist
das mit Kacheln und Zuschnitt-Download der Plattform vereinbar?
1. Stufe *Processing* mit `share_alike = true` und SA-Hinweis im Download
2. nur *Katalogeintrag*
3. stattdessen Z2 (GEDTM30, CC-BY-4.0, mit Testvorbehalt)

Für DEM ist nichts neu einzustufen (angenommen am 18.09.2026). Offen bleibt nur
der abweichende Lizenz-Link bei Earth Search (§3.1), der bei Weg F2.2 zählt.

**Antwort F4: entfällt**, weil Zenodo nicht gewählt ist. Die Lizenz des DEM
ist schon eingestuft: `adr/0003` §11.1, B11-Stufe *Processing*, Attribution
mit vorgeschriebenem Wortlaut.

**F5 — Coverage des DEM.**
1. Vereinigung der Item-Footprints über eigenes SQL (Empfehlung)
2. Ausdehnung aus der Collection-`bbox`, mit dem Hinweis, dass Lücken nicht
   sichtbar sind

**Antwort F5: (1)** aus den Kachel-Umrissen, mit der Lesart von ENTSCHEIDUNGEN
§2 aus §6: „Ausdehnung“ ist bei einem Einmal-Produkt die Vereinigung der
Kachel-Umrisse; dargestellt als Fläche, nicht als Dichte-Heatmap;
`completeness = complete`.

**F6 — Zenodo vormerken?**
1. Als Kandidat für M5 (Discovery über Record-Metadaten) vormerken (Empfehlung)
2. Nicht weiter verfolgen

**Antwort F6: (1)** ja, aber nur als Discovery- bzw. Metadatenquelle, nicht als
Quelle für Kacheln (Ratengrenze 133 Anfragen pro Minute je IP).

## 10. Offen für M3-11

Drei Fragen hat Otto mit der Annahme gestellt. Der Spike beantwortet sie so
weit, wie er gemessen hat; entschieden werden sie im Plan-Schritt von M3-11.
Nachgemessen am 23.09.2026 mit sechs weiteren Anfragen (eine Metadaten-XML,
zwei Range-Reads, die Kachelliste von GLO-90).

### 10.1 Welche Zeitangabe tragen die Items?

**Was pgstac verlangt.** pgstac 0.9.12 legt für jedes Item einen Zeitraum ab;
`datetime` und `end_datetime` sind in der Item-Tabelle `NOT NULL`
**[P]** ([`003a_items.sql` zu v0.9.12](https://github.com/stac-utils/pgstac/blob/v0.9.12/src/pgstac/sql/003a_items.sql)).
Die Funktion `pgstac.stac_daterange` nimmt `start_datetime`/`end_datetime`,
wenn beide gesetzt sind, sonst `datetime` **[P]** (Funktionstext aus der
lokal migrierten pgstac-Datenbank der Sitzung gelesen). STAC erlaubt
`datetime: null`, dann sind `start_datetime` und `end_datetime` Pflicht **[P]**
([Common Metadata](https://github.com/radiantearth/stac-spec/blob/master/commons/common-metadata.md)).
Ein Item ganz ohne Zeitangabe geht also nicht.

**Was die Quelle hergibt.** Der Kachelname enthält keine Zeit **[P]**
(`readme.html`). Die Metadaten-XML je Kachel (44 kB) enthält einen
Aufnahmezeitraum: für `N00_00_E006_00` `tsxx_startTime` 2011-07-30,
`tsxx_stopTime` 2013-09-20; dazu Erzeugung der Kachel 2015-02-28, Ausgabe
2020-01-10, Metadaten-Erstellung 2020-11-11 **[M]**. Gemessen ist das an
**einer** Kachel; wie stark der Zeitraum zwischen Kacheln schwankt, ist
**unbelegt**. Earth Search setzt für alle 26 450 Items `datetime`
2021-04-22 (§3.1); woher dieses Datum stammt, ist **unbelegt**. Einen für das
ganze Produkt belegten Aufnahmezeitraum hat der Spike nicht gefunden
(**unbelegt**); die Lizenz nennt nur Urheberjahre (© DLR 2010–2014, © Airbus
2014–2018, `adr/0003` §11.1) **[P]**, keinen Aufnahmezeitraum.

**Optionen für den Plan-Schritt** **[A]**:

1. `datetime: null` und `start_/end_datetime` je Kachel aus ihrer XML. Genau,
   kostet aber 26 450 zusätzliche Anfragen (rund 1,2 GB) bei jedem Laden.
2. `datetime: null` und ein Zeitraum für alle Kacheln. Braucht einen belegten
   Produktzeitraum, den es noch nicht gibt.
3. Ein fester `datetime` für alle Kacheln, wie bei Earth Search. Einfach, aber
   ohne belegte Bedeutung.

**Folge für den Viewer** **[A]**: Jede Wahl entscheidet, ob das DEM bei einer
Suche mit Zeitraum überhaupt erscheint — ein Zeitraum 2011–2013 fiele bei einer
Suche nach 2024 heraus. Außerdem setzt `earthx:viewer.group_by` heute ein
`datetime` voraus (architekturplan 5.1); das berührt M3-12.

### 10.2 Welcher Host kommt in `asset_hosts`?

**Gemessen:** Beide Namen desselben Buckets antworten auf einen Range-Read mit
`206` und ohne Weiterleitung — der globale
`copernicus-dem-30m.s3.amazonaws.com` (0,67 s) und der regionale
`copernicus-dem-30m.s3.eu-central-1.amazonaws.com` (0,49 s) **[M]**. Das sind
Einzelwerte, kein Vergleich der Latenz. Der globale Name antwortet mit
`x-amz-bucket-region: eu-central-1` (§3.1) **[M]**.

**Was dafür spricht:** Der globale Name ist schon in der Allowlist der
Cloud-Umgebung (M3-Plan §1.3) und in `adr/0003` §10.1 gemessen; der regionale
ist dort nicht eingetragen, antwortete in dieser Sitzung aber auch **[M]**. Da
die Items von der Plattform selbst erzeugt werden, bestimmt der Adapter den
Host in der `href`; es genügt **ein** Name, und er muss mit dem in
`asset_hosts` übereinstimmen **[A]**. Ob AWS den globalen Namen für Buckets
außerhalb von `us-east-1` dauerhaft ohne Weiterleitung bedient, ist
**unbelegt** — gemessen ist nur „heute ohne“.

**Grenze:** `gateway` lässt einen Host und seine echten Subdomains zu
(`gateway/policy.py`, `allows_host`) **[P]**. `s3.amazonaws.com` oder
`amazonaws.com` darf deshalb nie in `asset_hosts` stehen — das gäbe jeden
Bucket frei **[A]**.

**Vorschlag für den Plan-Schritt:** der globale Name
`copernicus-dem-30m.s3.amazonaws.com`.

### 10.3 Welche Länder fehlen, und wo gehört das hin?

**Gemessen:** Abgleich der Kachellisten von GLO-30 (26 450) und GLO-90
(`copernicus-dem-90m.s3.amazonaws.com/tileList.txt`, 26 475, ebenfalls
`Last-Modified` 2022-05-09) nach Kachelposition: **25 1°-Kacheln fehlen in
GLO-30**, alle zwischen 38° und 42° N sowie 43° und 51° O; umgekehrt fehlt
keine **[M]**. Diese Lage trifft Armenien und Aserbaidschan **[A]** — der
Kachelname nennt kein Land, einige Randkacheln dürften auch Nachbarländer
schneiden (**unbelegt**). `readme.html` sagt nur „specific countries“ **[P]**.
Suchtreffer nennen Armenien und Aserbaidschan **[S]**
([ASF HyP3](https://hyp3-docs.asf.alaska.edu/dems/)), einer spricht von 40
Kacheln **[S]** ([WindPRO-Wiki](https://help.emd.dk/mediawiki/index.php/Copernicus_DEM))
— gemessen sind im AWS-Bucket 25. Laut OpenTopography sind Armenien,
Aserbaidschan und Moldau seit einer Fassung vom Juli 2024 freigegeben **[S]**
([OpenTopography](https://opentopography.org/news/updated-copernicus-30m-DEM-available));
der AWS-Bucket ist auf dem Stand vom 09.05.2022 **[M]** und enthält diese
Freigabe nicht. Um Moldau fehlt im Bucket keine Kachel **[M]**.

**Wohin damit** **[A]**:

- **Coverage:** Die Lücke folgt ohne Zusatzdaten aus der Entscheidung zu F5 —
  die Vereinigung der Kachel-Umrisse zeigt sie, ebenso die Meere ohne Kacheln.
  Kein eigenes Feld nötig.
- **Beschreibung der Collection:** ein Satz, dass es die öffentliche Fassung
  GLO-30 im Stand des AWS-Buckets ist und Kacheln über dem Südkaukasus
  (Armenien, Aserbaidschan) fehlen. Die Länder dort zu nennen ist eine
  Ableitung aus Koordinaten und Suchtreffern; der Plan-Schritt entscheidet, ob
  die Beschreibung sie nennt oder nur die Lage.
- **Kein neues Registry-Feld** für ausgeschlossene Länder: Es gäbe nur diesen
  einen Anwendungsfall, und die Coverage zeigt die Lücke ohnehin.

## 11. Beobachtungen für M3-14 (noch kein Interface-Vorschlag)

- **Zwei Fragen in einem Feld.** Welcher Adapter eine Quelle spricht und ob ihre
  Items föderiert oder materialisiert sind, trennt der Code heute nicht
  (`SourceInfo.adapter` entscheidet die Föderation, §3.5).
- **Item-Erzeugung ist eine eigene Fähigkeit.** Keine der vier in 6.1 genannten
  (Discovery, Suche, Zugriffsauflösung, Aggregation) beschreibt „aus einer Liste
  und einem Namensschema Items bauen“. Bei STAC-Quellen fällt sie weg, bei allen
  vier Kandidaten ist sie der Kern.
- **Zugriffsauflösung ist mehr als „href lesen“.** Earth Search liefert für DEM
  `s3://`-Hrefs; `gateway` kann nur `https`. Die Übersetzung gehört zur
  Zugriffsauflösung, nicht zum Reader.
- **Item-Abruf für Kacheln hängt am Adapter.** Materialisierte Items kämen aus
  pgstac; die Kachelroute braucht dafür einen zweiten Weg (§3.5).
- **Quell-Listen lügen.** `last.txt` bei Hansen führt 224 nicht vorhandene
  Dateien (§3.2). Ein Adapter sollte das Listing des Speichers prüfen, nicht der
  Beschreibung glauben.
- **Ratengrenzen sind je Quelle verschieden und teils hart** (Zenodo 133/min
  auch für Range-Reads). Das betrifft `gateway` (Token-Bucket je Host,
  architekturplan 6.5) und die Frage, ob eine Quelle überhaupt kachelbar ist.
- **Zeit kann in Dateien, in Pixeln oder in einer Würfel-Dimension stecken**
  (Zenodo Z1, Hansen `lossyear`, ARCO-ERA5). Nur der erste Fall passt auf
  `datetime` je Item.
- **Fassungen:** Hansen und Zenodo liefern nicht nach, sondern veröffentlichen
  neu (Präfix bzw. Record). Eine Collection braucht dann eine Aussage, welche
  Fassung sie meint.

## 12. Messanhang

Befehle gekürzt; `$CA` ist das CA-Bündel der Sitzung.

| Messung | Befehl bzw. Adresse | Ergebnis |
|---|---|---|
| Erreichbarkeit | `curl -o /dev/null -w "%{http_code}"` auf die drei Hosts | 301 (Zenodo, API-Pfad ohne Schrägstrich), 400 (GCS-Wurzel), 200 (S3) |
| DEM-Listing | `GET /?list-type=2&delimiter=/&max-keys=5` | 200, `ListBucketResult` |
| DEM-Liste | `GET /tileList.txt` | 26 450 Zeilen, `Last-Modified` 2022-05-09 |
| DEM-STAC | `GET /catalog.json`, `/collection.json`, `/stac/catalog.json` | je 404 |
| Earth Search | `GET /v1/search?collections=cop-dem-glo-30&limit=1` | `matched` 26 450; Asset-href `s3://…` |
| COG-Struktur | Range `bytes=0-65535`, TIFF-Kopf gelesen; `rasterio.open("/vsicurl/…")` | §3.1–§3.3 |
| Kachelkosten | `rio_tiler.io.Reader(url).tile(x, y, z)` mit `CPL_VSIL_SHOW_NETWORK_STATS=YES` | §3.1–§3.3 |
| Hansen-Bestand | GCS-JSON-API `storage/v1/b/earthenginepartners-hansen/o?prefix=GFC-2025-v1.13/` | 3 Seiten, 2 599 Objekte |
| Hansen-Liste | Abgleich `last.txt` gegen Listing | 224 fehlen |
| Zenodo-Suche | `GET /api/records?q="cloud optimized geotiff" AND resource_type.type:dataset` | 314 Treffer; `x-ratelimit-limit: 30` |
| Zenodo-Datei | Range auf `/records/<id>/files/<name>` | 206; `x-ratelimit-limit: 133` |
| ARCO-ERA5 | `GET …zarr-v3/zarr.json`, `/.zmetadata`; Chunks `longitude/0`, `time/0`, `2m_temperature/700000.0.0` | 404; 200; Zarr v2, Werte §3.4 |
| CORS | `GET` mit `Origin`, `OPTIONS`-Preflight mit `Range` | §3.1–§3.4 |
| DEM-Zeitangaben | `GET …N00_00_E006_00_DEM/Copernicus_DSM_10_N00_00_E006_00.xml` | Aufnahme 2011-07-30 bis 2013-09-20 (§10.1) |
| pgstac-Zeitregel | `pg_get_functiondef` für `pgstac.stac_daterange`, lokale Datenbank | `start_/end_datetime` vor `datetime` (§10.1) |
| DEM-Endpunkte | Range `bytes=0-1023` über den globalen und den regionalen Namen | je 206, keine Weiterleitung (§10.2) |
| Fehlende Kacheln | `GET copernicus-dem-90m…/tileList.txt`, Abgleich mit GLO-30 nach Position | 25 fehlen in GLO-30 (§10.3) |
