# ADR 0023 — Quellenkatalog DACH und Satellit

- **Status:** Entwurf. Die Nummer 0023 ist im M5-Plan fest vergeben (`plans/m5/m5-discovery-und-suche.md` §5a). Am 31.10.2026 belegte weder `main` noch ein offener PR diese Nummer.
- **Datum:** 2026-10-31
- **Aufgabe:** M5-01 laut `docs/plans/m5/m5-discovery-und-suche.md` §5a (Entscheidungsvorlage A, §4).
- **Autonomiestufe:** C. Kein Produktivcode.
  - Geändert sind nur dieses ADR, eine Zeile im Entscheidungslog und das Messskript `scripts/m5-01-sources/probe.py`.
  - Das Skript ruft nur über `gateway` ab und läuft auf Ottos Rechner (§9).
  - Unverändert bleiben `backend/`, `frontend/`, Registry, Fixtures, Backlog, `.github/`, `.claude/` und `CLAUDE.md`.
- **Vorab fest (Otto, 31.10.2026, Plan §2 und §5):**
  - Satellitendaten immer.
  - DACH-Behörden zuerst.
  - Nur frei und ohne Schlüssel: Ein anonymes Token zählt als „ohne Schlüssel“, ein kostenloses Konto nicht.
  - Lizenz nach B11 eingestuft. Die Freigabe jeder Lizenz gibt immer Otto.
  - Zunächst nur Raster.
  - Zuerst dieses ADR und zwei bis drei Quellen von Hand, dann die Pipeline (ADR B, `adr/0025`).
  - Jeder Datensatz legt beim Onboarding drei Eigenheiten fest: Processing, erweiterte Suche und Schnellrechnungen. Sie stehen in der Registry, nicht im Frontend.
- **Grundlage:**
  - `ENTSCHEIDUNGEN_2026-09-18.md` §1 und §5.
  - `KLAERUNGEN.md` B8, B10, B11, B12 und B13.
  - `projektuebersicht.md` §2 (Prinzipien 1, 2, 3, 5, 10) und §5 (Onboarding-Checkliste).
  - `architekturplan.md` 3.1, 4.2, 5.1, 6.1 und 6.2.
  - `adr/0018` (Sentinel-1, anonymes Token), `adr/0021` (Suchfilter), `adr/0022` (Datennähe, `data_region`).
- **Betroffen (erst mit einer Entscheidung):**
  - welche Quellen M5 von Hand anbindet;
  - die Seed-Liste der Harvest-Pipeline (`adr/0025`);
  - das Bewertungs-Set der Suche (`adr/0026`);
  - die Liste der Prototyp-Quellen (`adr/0024`) und der Quellen mit Konto (`adr/0027`).

---

## Methode und Belegstufen

Belegstufen wie in `adr/0022`:

- **M:** in dieser Sitzung gemessen.
- **P:** am Primärdokument selbst gelesen. Gemeint ist der Quelltext der Doku oder des Dienstes im öffentlichen Repository der Stelle, geklont in das Kratzverzeichnis.
- **P\*:** Primärdokument über das Abrufwerkzeug eines Hilfsagenten gelesen, sinngemäß.
- **S:** Suchtreffer oder Zusammenfassung, Wortlaut nicht geprüft.
- **A:** eigene Ableitung, ein Argument und kein Beleg.

Die meisten Aussagen dieses ADR stehen auf **S**. Grund ist der folgende Befund.

**Was in dieser Sitzung erreichbar war [M]:**

- Der Proxy der Sitzung antwortet mit `403` auf CONNECT zu fast allen Quell- und Doku-Hosts. Darunter sind:
  - die Datenhosts `opendata.dwd.de`, `data.geo.admin.ch`, `dataset.api.hub.geosphere.at` und `data.hub.geosphere.at`;
  - die Behördenseiten `gdz.bkg.bund.de`, `data.bev.gv.at` und `www.basemap.at`;
  - die Kataloge `www.govdata.de`, `www.data.gv.at`, `opendata.swiss` und `stacindex.org`;
  - die Satellitenquellen `data.earth.jaxa.jp`, `cmr.earthdata.nasa.gov`, `stac.dataspace.copernicus.eu`, `planetarycomputer.microsoft.com`, `geoservice.dlr.de` und `land.copernicus.eu`;
  - die Länderportale `www.opengeodata.nrw.de`, `geodaten.bayern.de` und `geodaten.llv.li`.
- Erreichbar waren `earth-search.aws.element84.com`, `github.com` (auch per `git clone`) und `raw.githubusercontent.com`.
- Die Abrufwerkzeuge der Hilfsagenten scheiterten an denselben Behördenhosts mit einem DNS-Fehler. Ausnahmen waren `zenodo.org` und GitHub.
- **Ausweg:** Drei Stellen veröffentlichen ihre Doku bzw. ihren Dienst als Quelltext auf GitHub. Diese Quellen sind hier **P**:
  - MeteoSchweiz: Repository `MeteoSwiss/opendata`, die Quelle von `opendatadocs.meteoswiss.ch`;
  - GeoSphere Austria: `Geosphere-Austria/dataset-api-docs`, die Quelle der Doku der Dataset API;
  - die Bundes-Geodaten-Infrastruktur der Schweiz (FSDI/BGDI): `geoadmin/service-stac`, der Dienst hinter `data.geo.admin.ch/api/stac`.
- Die SPDX-Liste ist aus `spdx/license-list-data` gelesen (Stand 28.10.2026) [P].

**Anfragen an Datenquellen:** keine. Gelesen wurden nur öffentliche Doku-Seiten, Quelltexte und Suchtreffer. Item-IDs, `href`, Tokens und genaue Flächen stehen nicht in diesem Dokument.

**Folge:** Vor einer Annahme müssen die Kernaussagen zu den empfohlenen Quellen an der Quelle selbst geprüft werden. Dazu gehören anonymer Zugriff, Format, Range-Requests, ETag, CORS und Region. Weg dafür: §9, das Skript auf Ottos Rechner oder eine neue Sitzung mit freigegebenen Hosts.

---

## 0. Kurzfassung

1. **Es gibt viel ohne Schlüssel, aber wenig in einem Format, das die Plattform heute liest** [A, aus §3–§6]:
   - In COG liegen ESA WorldCover [M], swissALTI3D [S], die Geländemodelle und Orthofotos des BEV [S] und Niedersachsens [S] sowie der Copernicus DEM.
   - Die Meteorologie aller drei Länder (DWD, MeteoSchweiz, GeoSphere) liegt nur als NetCDF, HDF5 oder GRIB2 vor oder hinter einer Abfrage-API. Lizenzen und Zugang wären in Ordnung (CC BY 4.0, ohne Konto; bei MeteoSchweiz und GeoSphere am Primärtext belegt [P]).
2. **Lizenzen sind fast überall offen** (§7.2):
   - CC BY 4.0: MeteoSchweiz [P], GeoSphere [P], WorldCover [M], BEV [S], DWD [S].
   - dl-de/by-2-0 und dl-de/zero-2-0: die meisten deutschen Länder [S].
   - swisstopo-OGD ohne SPDX-Kennung [S].
   - Daraus folgt der Vorschlag „Processing“ für alle empfohlenen Quellen. Die Einstufung gibt Otto.
3. **Lage der Daten** (§7.3):
   - Die Schweizer Bundes-Geodaten liegen nach der Vorgabe im Code des Dienstes in AWS `eu-central-1` [P]; ICON liegt bei CSCS.
   - WorldCover liegt in `eu-central-1` [M], Niedersachsen in IBM `eu-de` [P].
   - DWD, BEV und GeoSphere: unbekannt, vermutlich eigene Rechenzentren in DE bzw. AT.
4. **Empfehlung für die Handarbeit vor der Pipeline (§8, F1):** ESA WorldCover, dann swissALTI3D, dann BEV ALS-DGM 1 m.
   - Alle drei kommen ohne neuen Reader aus.
   - Sie stressen die Achsen aus Prinzip 3 und 4: Bucket mit Kachelraster, eine zweite STAC-API, ATOM; dazu LV95 und LAEA.
   - Die Meteorologie folgt als nächster Block, sobald ein Leseweg für NetCDF entschieden ist (F3).
5. **Eigenheiten je Datensatz (§8.3):** Für die drei Quellen sind Processing, Suche und Schnellrechnungen in Feldern der Registry vorgeschlagen.
   - Neu wären nur `data_region` (beschlossen) und eine Capability `terrain` für einen Geländeoperator (F5).
   - Suchfilter bleiben bei allen dreien vorerst leer. Die FSDI-Suche kennt weder Query noch CQL2 [P], und materialisierte Datensätze haben nach `adr/0021` noch keine Filter.
6. **Offen:** Die meisten Behördenseiten waren aus der Sitzung gesperrt. Vor dem Onboarding prüft Ottos Lauf von `scripts/m5-01-sources/probe.py` oder eine Sitzung mit freigegebenen Hosts die Kernpunkte (§9).
7. **Nicht gefunden:** komplexe Quad-Pol-Daten ohne Konto (§6.3). `decomp` ruht weiter.

---

## 1. Kontext und Frage

M5 baut den „Datacrawler“ (Projektplan §4 M5). Bevor die Pipeline entsteht, will Otto wissen, welche Quellen es überhaupt gibt (Plan §5, Antwort 1). Die Pipeline soll erst kommen, wenn zwei bis drei davon von Hand angebunden sind und ihre Eigenheiten zeigen.

**Fragen dieses ADR:**

1. Welche Stellen in DACH und welche Raumfahrtagenturen bieten Rasterdaten ohne Schlüssel an?
2. Über welche Schnittstelle, unter welcher Lizenz, in welchem Format und wo liegen die Daten?
3. Welche zwei bis drei Quellen kommen zuerst, und welche Eigenheiten legen sie in der Registry fest?

Nicht Teil dieses ADR:

- die Pipeline selbst (`adr/0025`);
- die Suche (`adr/0026`);
- Quellen mit unklarer Rechtslage (`adr/0024`);
- Quellen mit Konto (`adr/0027`);
- Sentinel-1 (DS-04, `adr/0018`).

Kandidaten für diese ADRs sind in §7.5 nur genannt.

**Ausgangslage im Code [P]:**

- Die Registry kennt zwei Adapter: `earth-search-v1` und `cop-dem-bucket` (`catalog/registry.py`, `AdapterKind`).
- `readers` liest nur COG und Zarr. `DataFormat.LEGACY` gibt es als Wert, aber ohne Reader.
- Operatoren gibt es sechs: `band_math`, `mask`, `mask_values`, `normalize`, `reproject` und `select`. Gelände- oder Zeitoperatoren (Hangneigung, Summe über die Zeit) fehlen.
- Prinzip 1 (`projektuebersicht.md` §2) schließt die dauerhafte Haltung von Rohdaten aus. Eine Quelle in NetCDF, HDF5 oder GRIB2 lässt sich deshalb nicht einfach einmal nach COG umwandeln und behalten. Sie braucht einen Leseweg vom Original oder einen flüchtigen Cache [A].

---

## 2. Kriterien

| # | Kriterium | Woher |
|---|---|---|
| K1 | Lesen ohne Konto und ohne eigenen Schlüssel; ein anonym ausgegebenes Token ist erlaubt | Plan §2 Punkt 3; `ENTSCHEIDUNGEN` §1 |
| K2 | Lizenz erlaubt Weitergabe und Bearbeitung (B11 Anzeige/Processing), sonst nur Katalogeintrag | B11; Plan §2 Punkt 4 |
| K3 | Raster | Plan §5 Antwort 2 |
| K4 | Format: Zarr > COG > Rest. Lesbar ohne neuen Reader zählt doppelt | Checkliste Punkt 5; `architekturplan.md` 6.2 |
| K5 | Schnittstelle: STAC zuerst, dann maschinenlesbare Listen (ATOM, Bucket-Liste), dann Abfrage-APIs | Prinzip 5; `architekturplan.md` 4.2 |
| K6 | Lage der Daten: EU/CH vor Übersee | `adr/0022` F3 |
| K7 | Betrieb: Fair-Use und Limits, Aufbewahrung, ETag/Last-Modified für bedingte Requests | Prinzip 11; Abnahme M5 |
| K8 | Nutzen für DACH, gemessen an dem, was es schon gibt (Sentinel-2, Copernicus DEM, Sentinel-1 in Arbeit) | Plan §2 Punkt 2 |
| K9 | Aufwand im Code: neuer Adapter, Reader oder Operator | Prinzip 3 und 4 |
| K10 | Coverage Map und Health-Check machbar | Checkliste Punkte 2 und 10 |

---

## 3. Schweiz und Liechtenstein

### 3.1 Bundes-Geodaten-Infrastruktur: STAC-API `data.geo.admin.ch` (swisstopo, MeteoSchweiz, BAFU)

**Die Schnittstelle:**

- `data.geo.admin.ch/api/stac/v1` ist eine STAC-API nach OGC-Standard (MeteoSwiss-Doku `docs/general/download.md` [P]; swisstopo-Doku [S]).
- Jeder Datensatz ist eine eigene Collection. Darin liegen auch die Datensätze von MeteoSchweiz und BAFU [P].
- v0.9 ist abgekündigt und läuft laut Suchtreffer mindestens bis Ende 2026 [S].
- **Ohne Konto:** Die Nutzungsbedingungen der FSDI verlangen keine Registrierung; es gilt Fair Use [S].
  - Die Limits wurden zum 05.01.2025 geändert. Zahlen sind nicht belegt [S].
  - MeteoSchweiz verbietet „excessive use … in particular the high-frequency downloading of the same content“ und verweist auf die FSDI-Bedingungen [P].
- **ETag und bedingte Requests [P]:**
  - Die Doku empfiehlt ausdrücklich `If-None-Match` mit dem ETag; der Server antwortet dann `304 Not Modified`.
  - Assets werden 2 Stunden gecacht, 10-Minuten-Collections 10 Sekunden.
  - Das passt genau zur Abnahme von M5: Ein Lauf ohne Änderung kostet nur bedingte Requests.
- **CORS:** Die API setzt `Access-Control-Allow-Origin: *` (`service-stac`, `app/middleware/cors.py`) [P]. Für die Asset-Dateien ist das nicht belegt.
- **Lage der Daten:**
  - Der Dienst schreibt verwaltete Assets in einen S3-Bucket. Seine Vorgabe ist die Region `eu-central-1`; ältere Bestände liegen nach der Vorgabe in `eu-west-1` (`service-stac`, `app/config/settings_prod.py`) [P].
  - Die Produktion kann die Vorgaben über Umgebungsvariablen ändern. Gesichert ist nur „AWS“ (AWS-Fallstudie [S]).
  - **Vorschlag für `data_region`:** `aws:eu-central-1`, zu bestätigen mit §9 (Kopfzeile `x-amz-bucket-region` bzw. Host) [A].
- **Lizenz swisstopo:** Seit 01.03.2021 sind die Geodaten von swisstopo Open Government Data [S].
  - Erlaubt sind Nutzung, Weitergabe, Bearbeitung und kommerzielle Nutzung. Einzige Pflicht ist die Quellenangabe [S].
  - Es gibt keine SPDX-Kennung (SPDX-Liste [P]). Die Collections tragen laut Suchtreffer `license: proprietary` [S].
  - **Vorschlag:** `spdx_id = None`, Name und URL der swisstopo-Bedingungen, `attribution_required = true`, alle anderen Flags `true`, Stufe Processing. **Einstufung durch Otto.**

**Datensätze von swisstopo (alle [S], Collection-IDs aus Suchtreffern):**

| Collection | Inhalt | Auflösung, Kachel | Format | Zeit |
|---|---|---|---|---|
| `ch.swisstopo.swissalti3d` | Geländemodell (DTM), Schweiz und Liechtenstein | 0,5 m und 2 m, Kacheln 1 km | COG laut Forum und Swiss Data Cube, Float32, Nodata −9999, EPSG:2056, Höhen LN02 | Nachführung im 6-Jahres-Zyklus, Jahr je Kachel |
| `ch.swisstopo.swissimage-dop10` | Orthofoto RGB | 10 cm im Mittelland und in den Alpentälern, 25 cm in den Alpen | GeoTIFF; COG für dieses Produkt nicht belegt | Zyklus 3 Jahre (Angaben widersprechen sich) |
| `ch.swisstopo.swisssurface3d-raster` | Oberflächenmodell (DOM) | 0,5 m, Kacheln 1 km | GeoTIFF; COG nicht belegt | wie swissALTI3D |
| `…pixelkarte-farbe-pk50/100/200.noscale` | Landeskarten als Bild | — | GeoTIFF LZW | — |

Der Bestand von swissALTI3D liegt laut Forum bei rund 770 GB (0,5 m) bzw. 44 GB (2 m) [S]. Die Plattform spiegelt ihn nicht (Prinzip 1), sie liest live.

**Datensätze von MeteoSchweiz (alle [P] aus `MeteoSwiss/opendata`, Stand 31.10.2026):**

- **Lizenz [P]:**
  - Veröffentlicht unter **CC BY 4.0** (`CC-BY-4.0`).
  - Teilen und Bearbeiten ist „for any purpose, even commercially“ erlaubt.
  - Quellenangabe Pflicht: „Source: MeteoSwiss“, ohne den Anschein einer Unterstützung durch MeteoSchweiz.
  - Warnungen dürfen nur zeitnah und unverändert weitergegeben werden.
  - Rechtsgrundlage ist Art. 10 EMOTA (Bundesgesetz über Meteorologie und Klimatologie).

| Collection | Inhalt | Format, Gitter | Aufbewahrung |
|---|---|---|---|
| `ch.meteoschweiz.ogd-surface-derived-grid` | Räumliche Klimaanalysen 1 km: Niederschlag (RhiresD/M), Temperatur (TabsD/M, Anomalien), relative Sonnenscheindauer | NetCDF, LV95 (EPSG:2056); Rekonstruktionen bis 1864 in EPSG:4326 | vorläufig 41 Tage, konsolidiert 14 Monate, Jahresarchiv `CH archive` dauerhaft |
| `ch.meteoschweiz.ogd-satellite-derived-grid` | Strahlung, Bewölkung aus Meteosat und Boden | NetCDF, EPSG:4326 | wie oben |
| `ch.meteoschweiz.ogd-climate-normals-grid` | Normwerte (z. B. 1991–2020) | NetCDF (und GeoTIFF laut Suchtreffer [S]), LV95 bzw. EPSG:4326 | statisch |
| `ch.meteoschweiz.ogd-radar-derived-grid` | Hagelklimatologie | NetCDF | Monat und Jahr, Archiv |
| `ch.meteoschweiz.ogd-radar-precip` | Radar-Niederschlag und CombiPrecip (5/60 min, Reanalyse nach 8 Tagen) | ODIM-HDF5, LV95, unter 1 MB je Datei | **14 Tage rollierend**, Archiv auf Anfrage |
| `ch.meteoschweiz.ogd-forecasting-icon-ch1` / `-ch2` | ICON-CH1/CH2-EPS (1 km / 2,1 km, 11 / 21 Mitglieder) | GRIB2 auf dem nativen Ikosaedergitter; Koordinaten in eigenen Konstantendateien | **24 Stunden**, abgelegt bei CSCS (ETH Zürich), Assets als vorsignierte URL |
| Nowcasting (INCA-CH) | Niederschlag, Wind, Bewölkung, 10 min, 1 km | NetCDF, LV95 | kurz; neues System 2027–2028 mit neuem Gitter |

**BAFU, WSL/SLF, opendata.swiss [S]:**

- BAFU-Raster (z. B. die Gefährdungskarte Oberflächenabfluss) liegen ebenfalls auf der FSDI. Ihr Format ist nicht belegt.
- Die Schneedaten von WSL/SLF (EnviDat) stehen unter „Other (siehe Beschreibung)“. Ob sie ohne Konto abrufbar sind, ist offen.
- opendata.swiss ist ein CKAN-Katalog (`ckan.opendata.swiss/api/3/action/`, Handbuch) [S].
  - Die Lizenz ist je Datensatz als einer von vier Begriffen hinterlegt: `terms_open`, `terms_by`, `terms_ask`, `terms_by_ask`.
  - `*_ask` heißt: Kommerzielle Nutzung braucht eine Bewilligung [S]. Das schließt die Stufe Processing ohne Einzelprüfung aus [A].

### 3.2 Liechtenstein [S]

- swissALTI3D deckt Liechtenstein mit ab (Produktinfo swisstopo [S]). Das ist der einfachste Weg zu einem Geländemodell für FL.
- Das Amt für Geoinformation (AGI) bietet Orthofotos 2003–2025 und ein DTM 0,5 m (Befliegung 2015) über WMS, ATOM und WCS an.
- Auf opendata.swiss trägt das Orthofoto `terms_by_ask` [S]. Für das DTM ist die Lizenz nicht belegt; eine Gebührenverordnung (GDI-GebV 2011) wird erwähnt.
- Bis zur Klärung ist das ein Kandidat für einen Katalogeintrag oder für `adr/0024`, nicht für Anzeige oder Processing [A].

---

## 4. Österreich

### 4.1 GeoSphere Austria: Dataset API (alle [P] aus `Geosphere-Austria/dataset-api-docs`, Changelog bis 24.08.2026)

- **Zugang [P]:** „Currently, no authentication is required to access data via the API.“
- **Lizenz [P]:** „All data that requires no authentication is licensed under the Creative Commons Attribution 4.0“ (`CC-BY-4.0`).
  - Eine Drittquelle sprach von „nicht kommerziell“ [S]. Das widerspricht dem Primärtext und gilt hier nicht.
- **Limits [P]:**
  - 5 Anfragen je Sekunde und 240 je Stunde, sonst `429`. Die Kopfzeilen `x-ratelimit-*` nennen den Stand.
  - Größe je Anfrage: höchstens 1 000 000 Werte als JSON/CSV und 10 000 000 als NetCDF. Gezählt wird Parameter × Zeitschritte × Orte.
- **Art der Schnittstelle [P]:** Es ist eine Abfrage-API, kein Dateikatalog.
  - Typ `grid` liefert ein Raster zu einer `bbox` in EPSG:4326, Typ `timeseries` den nächsten Gitterpunkt.
  - Die Modi heißen `historical`, `current` und `forecast`; `forecast` ist ausdrücklich „prerelease“.
- **Ressourcen (Auswahl) [P]:**
  - SPARTACUS v3: Tag, Monat, Saison, Jahr; 1 km; Temperatur und Niederschlag ab 1961.
  - WINFORE v2 (Trockenheitsindex, 1 km).
  - APOLIS v2 (Globalstrahlung, 100 m).
  - Snowgrid CL v2 (Schnee, 1 km).
  - INCA (1 h, 1 km), Nowcast (15 min, 1 km).
  - Modelle `nwp-v2` (1 km und 2,5 km) und `ensemble-v2`.
  - Luftqualität (`chem-*`) und HISTALP.
- **Folge für die Plattform [A]:**
  - Eine Kachel aus dieser API hieße eine Abfrage je Kachel. Mit 240 Anfragen je Stunde reicht das nicht einmal für eine einzige Kartenansicht.
  - Anzeige und Processing gehen daher nur mit Dateien. Die gibt es laut Suchtreffern im Data Hub (`data.hub.geosphere.at`) als NetCDF-Dateien je Jahr [S], nicht belegt.
  - Discovery und Katalog gehen über die API: `/datasets` listet alle Ressourcen samt Metadaten [P].

### 4.2 BEV (Bundesamt für Eich- und Vermessungswesen) [S]

- **ALS-DGM 1 m (Höhenraster) und ALS-DOM 1 m:**
  - ganz Österreich in 55 Kacheln zu 50 km, EPSG:3035;
  - Download über einen ATOM-Dienst (`data.bev.gv.at`), Zugriff „unrestricted“;
  - Formate in den Metadaten: GeoTIFF und COG.
- **Orthofoto DOP 20 cm:** 57 Kacheln, Zyklus 3 Jahre, gleiche Wege und Formate.
- **Lizenz:** CC BY 4.0 laut BEV-Metadaten.
- **Unklar:**
  - Ein WMS-Metadatensatz nennt „Anmeldung erforderlich“; das betrifft den Darstellungsdienst, nicht den Download.
  - Ob jede Kachel wirklich ein COG ist, ist offen. Eine 50-km-Kachel zu 1 m hat 50 000² Pixel; ohne Overviews wäre sie für Kacheln unbrauchbar [A].
  - Range-Requests, CORS, ETag und Lage der Daten sind nicht belegt.
- **basemap.at:** WMTS mit Karten und Orthofoto, CC BY 4.0 laut Sekundärquellen. Das sind Bildkacheln, keine Messwerte. Es ist ein Kandidat für eine Basiskarte (UI-02), keine Datenquelle [A].

### 4.3 Bundesländer, EODC, data.gv.at [S]

- Die Länder bieten Geländemodelle und Orthofotos meist unter CC BY 4.0 an. Formate und Wege sind uneinheitlich:

| Land | DGM | Orthofoto | Lizenz | Format, Weg |
|---|---|---|---|---|
| Burgenland | ja (DGM, DOM 50 cm) | ja | CC BY 4.0 AT | Download-Portal |
| Kärnten | ja | offen | CC BY 4.0 | ASCII-Grid 1:5 000, XYZ |
| Steiermark | ja, 1 m | ja | CC BY 4.0 (Stand 2020) | GeoTIFF/ZIP, WCS (höchstens 10 000² px) |
| Oberösterreich | ja (10 m belegt) | offen | CC BY 4.0 (älter 3.0) | `data.ooe.gv.at` |
| Tirol | bis 50 cm, WCS 1 m/5 m | 20 cm | CC BY 4.0 nur aus Drittquelle | Download nach Blatt, WCS |
| Wien | nur DOM belegt | offen | CC BY 4.0 | offen |
| NÖ, Vorarlberg, Salzburg | offen | offen | nicht belegt bzw. nur CC BY 3.0 AT von 2013/2017 | WMS, Portale |

- Für ganz Österreich deckt das BEV dieselben Inhalte einheitlich ab. Die Länder sind deshalb erst ein Thema, wenn eine höhere Auflösung gebraucht wird [A].
- **EODC (Wien)** betreibt einen STAC-Katalog. Darin liegen u. a. `SENTINEL1_SIG0_20M` und die EOPF-Zarr-Samples (`adr/0007`, `adr/0017`). Anonymer Zugriff und Lizenz der übrigen Collections sind nicht belegt.
- **data.gv.at** ist CKAN-basiert. Pfade, DCAT-AP-Endpunkt und ein Zugang ohne Schlüssel sind nicht belegt. Offene Raster vom Umweltbundesamt wurden keine gefunden.

---

## 5. Deutschland

### 5.1 Deutscher Wetterdienst (DWD), Open Data [S]

- **Zugang und Lizenz:**
  - Ein HTTPS-Dateiserver (`opendata.dwd.de`); laut README „without registration“.
  - Die IP wird höchstens 7 Tage gespeichert.
  - Laut den Nutzungsbedingungen (Stand Mai 2024) gilt CC BY 4.0. Ältere Quellen nennen noch die GeoNutzV.
  - Ein Rate-Limit ist nicht belegt.
- **Rasterprodukte:**

| Produkt | Inhalt | Format | Gitter | Zeit |
|---|---|---|---|---|
| HYRAS-DE | Niederschlag 1 km, andere Größen 5 km, täglich | NetCDF | EPSG:3035 bzw. 3034 | ab 1931, täglich erweitert |
| HOSTRADA | stündliche Bodenparameter, 1 km | NetCDF | EPSG:3034 | ab 1995 |
| DUETT | Globalstrahlung, Sonnenschein aus Satellit und Boden | NetCDF | 3034/3035 (Angaben widersprechen sich) | stündlich |
| `grids_germany` monatlich/jährlich | Temperatur, Niederschlag, Sonnenschein, 1 km | ASCII-Grid | Gauß-Krüger 3 (EPSG:31467) | ab 1881/1901 |
| RADOLAN, RADKLIM | Radar-Niederschlag | RADOLAN-Binär, HDF5, ASCII, teils NetCDF | polarstereographisch, 900×900 bzw. 1100×900 | RADKLIM 2001 bis 2025 |
| ICON-D2, ICON-EU | Vorhersagemodelle | GRIB2 (bz2) | rotiert/regulär bzw. Ikosaeder | nur die letzten rund 24 h |

- **Befund [A]:** Der DWD hat den breitesten Bestand in DACH, aber kein einziges Produkt in COG oder Zarr. Jedes braucht einen neuen Reader.
  - Dazu kommen vier Projektionen: 3034, 3035, 31467 und die polarstereographische Projektion von RADOLAN.
  - Skalierung und Einheit stehen je Produkt in einer Beschreibung als PDF, nicht einheitlich in der Datei [S].

### 5.2 BKG [S]

- Offen sind DGM200 (dl-de/by-2-0, GeoTIFF/ASCII), TopPlusOpen und basemap.de. TopPlusOpen und basemap.de sind WMS/WMTS, also Bildkacheln.
- DGM1 und DOP20 des BKG für ganz Deutschland sind **nicht** als offen belegt. Die DOP-Bedingungen (Stand 12.01.2026) nennen gebührenpflichtige Teile.
- Die offenen Länderprodukte sind deshalb der Weg zu hochaufgelösten Daten.

### 5.3 Länder (Geländemodell DGM1 und Orthofoto DOP) [S, LGLN teils P]

- Alle 16 Länder bieten DOP und DGM1 in irgendeiner Form offen an.
- Lizenzen: meist dl-de/by-2-0; dl-de/zero-2-0 in NRW und Hessen; CC BY 4.0 in Bayern, Bremen und Schleswig-Holstein.
- Formate: überwiegend GeoTIFF-Kacheln, daneben JPEG2000 (NRW-DOP) und ASCII-XYZ (Rheinland-Pfalz, Sachsen).
- **COG und STAC sind nur für Niedersachsen (LGLN) belegt:**
  - DOP20 (RGB, RGBI) und DGM1/DOM1 als COG [S].
  - Eine STAC-API wurde auf der FOSSGIS 2024 vorgestellt [S]. Ihre Adresse wurde nicht gefunden.
  - Ein Notebook eines LGLN-Mitarbeiters auf GitHub lädt die DOP20 über einen Kachelindex im IBM-Cloud-Objektspeicher, Region `eu-de` (Frankfurt). Dort ist die Lizenz „dl-de/by-2-0“ angegeben [P, aber keine amtliche Seite].
  - Für DGM1/DOM1 nennt nur ein Dritt-Wiki CC BY 4.0 seit Mai 2024 [S].
- In Bayern gibt es auch CC-BY-ND-Produkte [S]. ND ist nach B11 nur Katalogeintrag; Bayern muss deshalb je Produkt geprüft werden.
- Die vollständige Ländertabelle liegt im Bericht des Hilfsagenten. Hier steht sie nur verdichtet, weil fast alle Zeilen [S] sind.

### 5.4 Bundesforschung, DLR, GovData [S, Thünen P\*]

- **Thünen-Institut:**
  - Die Anbauartenkarte Deutschland (jährlich ab 2017) liegt als COG (0,6–0,8 GB) auf Zenodo unter CC BY 4.0 [P\*].
  - Zenodo ist kein Behördenserver; Range-Requests dort sind ungeprüft.
  - Zenodo ist seit `adr/0009` F6 als Discovery-Quelle für M5 vorgemerkt.
- **DLR:**
  - Der World Settlement Footprint (WSF 2019, WSF Evolution) steht unter CC BY 4.0, als GeoTIFF in 2°-Kacheln. Ob er ohne Konto abrufbar ist, ist nicht belegt.
  - TanDEM-X 90 m braucht eine Registrierung und gilt nur für die Wissenschaft. Er scheidet aus.
  - DLR betreibt eine EOC-STAC-API. Der Download braucht dort möglicherweise ein Login.
- **CODE-DE:** nur mit Registrierung.
- **GovData:** CKAN-API (`/ckan/api/3`) und DCAT-AP.de, Lizenzen als URIs maschinenlesbar. Die Zahl der Rasterdatensätze ist unbekannt.
- **UBA, BfG, BGR:** keine offenen Raster ohne Konto gefunden (BGR uneinheitlich).

---

## 6. Satellitendaten

### 6.1 ESA WorldCover (ESA/VITO) — gemessen [M]

- **Ablage:** Der Bucket `esa-worldcover` liegt in AWS `eu-central-1`, ohne Requester Pays (Registry-YAML [P]).
- **Messung (31.10.2026, eine 3°-Kachel in Mitteleuropa, nur Kopf und erste KB) [M]:**
  - Das Listing ist anonym lesbar; ein Range-GET auf die ersten 1024 Bytes ergibt `206`.
  - `Accept-Ranges: bytes`, ETag und Last-Modified sind gesetzt.
  - Mit einem `Origin`-Header kommt **kein** `Access-Control-Allow-Origin` zurück.
- **Datei [M]:**
  - `LAYOUT=COG`, DEFLATE, Blöcke 1024², Overviews 2 bis 64;
  - EPSG:4326, 36 000² Pixel zu 1/12 000° (rund 10 m);
  - `uint8`, Nodata 0, Farbtabelle in der Datei.
- **Klassen** laut Kopf der Datei: 10 Baumbestand, 20 Gebüsch, 30 Grasland, 40 Acker, 50 bebaut, 60 kahl/spärlich, 70 Schnee und Eis, 80 Wasser, 90 krautige Feuchtgebiete, 95 Mangroven, 100 Moos und Flechten [M].
- **Lizenz:** CC BY 4.0. Der Kopf der Datei sagt `license: CC-BY 4.0` und „Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium“ [M]. Die Registry sagt dasselbe [P].
- **Kachelraster:** Das Raster liegt als `esa_worldcover_grid.geojson` bzw. `.fgb` im Bucket [M]. Daraus lassen sich die Items erzeugen wie beim DEM (`adr/0009`, Einmal-Befehl in `discovery`) [A].
- **Zwei Stände:** 2020 (v100) und 2021 (v200). Wegen eines Algorithmuswechsels sind sie „nur mit Vorsicht vergleichbar“ (Registry [P\*]). Weitere Jahre wurden nicht gefunden.

### 6.2 Earth Search v1 und AWS Open Data (Stand der bekannten Quellen)

- **Collections [M]:** Earth Search v1 listet am 31.10.2026 neun Collections, alle mit `license: proprietary`:
  - `sentinel-2-c1-l2a`, `sentinel-2-l2a`, `sentinel-2-pre-c1-l2a`, `sentinel-2-l1c`;
  - `sentinel-1-grd`;
  - `cop-dem-glo-30`, `cop-dem-glo-90`;
  - `landsat-c2-l2`;
  - `naip`.
- **Earth Search v2 (Backlog 36) [P]:** Laut README des Repos `Element84/earth-search` „currently in beta and may change before general release“, ohne öffentlichen Endpunkt. Der Dienst bleibt „best effort“ ohne Zusage. Für M5 heißt das: keine Änderung.
- **Ohne Requester Pays in `eu-central-1` (Registry-YAMLs [P]):** `sentinel-s2-l2a` (JP2), `sentinel-s1-l1c` (Sentinel-1), `copernicus-dem-30m`/`-90m` und `esa-worldcover`.
- **Mit Requester Pays (also nicht ohne Konto):** `sentinel-s2-l1c` (Registry [P]) und Landsat C2 in `us-west-2` (Registry und Earth Search [P\*]).
- **Copernicus DEM GLO-90** ist ein zweiter DEM-Datensatz auf demselben Weg wie GLO-30 [P\*]. Der Nutzen neben GLO-30 ist gering [A].

### 6.3 Weitere Satellitenquellen [P\* bzw. S]

| Quelle | Inhalt | Zugang | Lizenz | Format | Region | Einschätzung |
|---|---|---|---|---|---|---|
| EOPF Sentinel Zarr Samples (EODC) | S1/S2/S3 als Zarr v2/v3 | anonym laut `adr/0007`/`0017` | Copernicus Legal Notice | Zarr, ohne Overviews | `eodc:vienna` | Wiedervorlage `adr/0017`/`0022` F5; laut FAQ operativ „Ende 2026 oder Anfang 2027“ [S] |
| EODC Data Access (`stac.eodc.eu`) | über 100 Collections, u. a. S1 Sigma0 20 m, Bodenfeuchte, `s1-alps-wetsnow`, `AUT_DEM`, GHS | unbekannt | unbekannt | unbekannt | `eodc:vienna` | Prüfen (§9): EU-Hosting, alpin relevant |
| ESA CCI Open Data Portal (CEDA) | Landbedeckung, Bodenfeuchte, Schnee, Gletscher | Konto nicht belegt | „any purpose“ mit Quellenangabe [S] | NetCDF | vermutlich UK | erst mit einem Leseweg für Gruppe D (§7.1, F3) |
| CLMS (EEA) | HRL, CORINE, Vegetationsindizes | **EU Login** [S] | frei mit Quellenangabe | — | — | `adr/0027` |
| C3S, CAMS, CEMS (CDS/ADS), Copernicus Marine, EUMETSAT | Klima, Atmosphäre, Hochwasser, Meer | **Konto** [S] | je Datensatz | GRIB/NetCDF | — | `adr/0027` |
| JAXA Earth API | AW3D30-DSM, PALSAR-2-Wald/Nichtwald 25 m, GCOM-C SGLI (LST, NDVI), GSMaP | Schlüssel nicht belegt [S] | JAXA-Bedingungen je Collection, kommerziell laut Suchtreffer erlaubt [S] | COG mit STAC [S] | unbekannt (vermutlich Japan) | prüfen (§9); globaler Nutzen, Region ungünstig |
| ALOS/PALSAR-Mosaike (Digital Earth Africa) | L-Band HH/HV 25 m, 2007–2010 und 2015–2020 | anonym [P\*] | JAXA-Bedingungen | COG | `aws:af-south-1` | Region ungünstig |
| Sentinel-1 Global Coherence (Earth Big Data) | Kohärenz und Rückstreuung, 2019/2020 | anonym [P\*] | `CC-BY-4.0` | COG-Mosaike | `aws:us-west-2` | ein Jahr, Übersee |
| NASA (HLS, NISAR, UAVSAR, MODIS über LP DAAC/ASF) | — | **Earthdata Login** [S] | frei | COG/HDF5 | AWS `us-west-2` | `adr/0027` |
| NASA GIBS | Bildkacheln (Worldview) | ohne Schlüssel [S] | Danksagung | Bildkacheln | — | höchstens Basiskarte |
| Planetary Computer | S1 RTC, S2, Landsat, HLS, MODIS, ALOS-DEM, WorldCover u. a. | anonymes SAS-Token [P\*] | je Collection | COG, teils Zarr | `azure:westeurope` | nach `adr/0022` F6 nur S1 RTC (`adr/0018` Teil B) |

**Quad-Pol (`ENTSCHEIDUNGEN` §3):** Eine Quelle mit komplexen Quad-Pol-Daten ohne Konto wurde nicht gefunden.

- Kandidaten mit Konto sind NISAR (seit 20.07.2026 öffentlich), UAVSAR und SAOCOM, alle über Earthdata Login oder Antrag [S].
- Offen sind:
  - die Beispielprodukte von ALOS-2 bei JAXA (Bedingungen, Modus und Konto nicht belegt) [S];
  - die bei EODC gelisteten `NISAR_L1_RSLC_PROVISIONAL_V1` (Zugang unbekannt) [P\*].
- Der Operator `decomp` ruht deshalb weiter mit synthetischen Tests.

---

## 7. Querschnitt

### 7.1 Formate: der eigentliche Engpass

| Gruppe | Format | Lesbar heute | Beispiele |
|---|---|---|---|
| A | COG | ja | ESA WorldCover [M], Copernicus DEM (im Code), swissALTI3D [S], BEV DGM/DOP [S], LGLN DOP/DGM [S], Thünen [P\*], JAXA Earth API [S] |
| B | Zarr | ja | EOPF (Samples, `adr/0017`), Source Cooperative FTW (Zarr v3 ohne Multiscales) [S] |
| C | GeoTIFF ohne Overviews, JPEG2000, ASCII-Grid | nein, bzw. nur langsam | die meisten Länder, DWD `grids_germany` |
| D | NetCDF, HDF5, GRIB2 | nein | DWD, MeteoSchweiz, GeoSphere-Dateien |

Folgerungen [A]:

1. Die erste Runde von Hand kann nur aus Gruppe A und B kommen, ohne neuen Reader.
2. Meteorologie, die Otto ausdrücklich will (Plan §2 Punkt 2), liegt in DACH vollständig in Gruppe D. Sie braucht eine eigene Entscheidung zum Leseweg. Drei Wege stehen zur Wahl:
   - **(a)** NetCDF/HDF5 über einen virtuellen Zarr-Speicher lesen (Kerchunk/VirtualiZarr, `architekturplan.md` 6.2 „später virtuelle Stores“). Das Original bleibt bei der Quelle; das passt zu Prinzip 1.
   - **(b)** Den Schritt in GDAL über `/vsicurl/` mit dem NetCDF- bzw. HDF5-Treiber machen. Das ist einfach, aber oft langsam, weil NetCDF-4/HDF5 viele kleine Lesezugriffe braucht.
   - **(c)** Ein flüchtiger Cache als COG mit Ablaufdatum (Prinzip 1 erlaubt abgeleitete Produkte nur flüchtig).
   
   Das ist rechenrelevant und gehört in eine eigene Recherche bzw. einen Spike (Frage F4).
3. GRIB2 auf dem Ikosaedergitter (ICON) braucht ein Umrechnen auf ein reguläres Gitter. Das ist Processing, kein Lesen. Bis auf Weiteres scheidet es aus.

### 7.2 Lizenzen und Vorschlag zur B11-Einstufung

Alle Einträge sind **Vorschlag**; die Einstufung entscheidet Otto (`CLAUDE.md`). Gegen die SPDX-Liste vom 28.10.2026 geprüft [P]: `CC-BY-4.0`, `DL-DE-BY-2.0`, `DL-DE-ZERO-2.0` und `CC-BY-3.0-AT` gibt es. Für die swisstopo-OGD gibt es keine Kennung.

| Lizenz | Quellen | Flags (Vorschlag) | Stufe (Vorschlag) |
|---|---|---|---|
| `CC-BY-4.0` | MeteoSchweiz [P], GeoSphere [P], ESA WorldCover [M], BEV [S], DWD [S], die meisten AT-Länder [S], Thünen [P\*] | `commercial_use`, `distribution`, `derivatives` = true; `share_alike` = false; `attribution_required` = true | Processing |
| `DL-DE-BY-2.0` | BKG, die meisten DE-Länder, LGLN-DOP [S] | wie CC BY 4.0; der Quellenvermerk verlangt den Hinweis „Daten verändert“ bei Bearbeitung (BKG-Muster [S]) | Processing |
| `DL-DE-ZERO-2.0` | NRW, Hessen [S] | alles true, `attribution_required` = false | Processing |
| swisstopo-OGD (keine SPDX-Kennung) | swisstopo [S] | wie CC BY 4.0; `spdx_id = None`, Bedingungen als URL | Processing |
| opendata.swiss `terms_*_ask` | z. B. Orthofoto Liechtenstein [S] | `commercial_use` = false | Processing nur im Gratis-Tier (B11), sonst Katalog |
| CC BY-ND | einzelne Bayern-Produkte [S] | `derivatives` = false | nur Katalogeintrag |
| ungeklärt | Vorarlberg, Salzburg, NÖ, Liechtenstein-DTM, WSL/SLF | — | Katalogeintrag mit Link oder `adr/0024` |

Das Feld `attribution_modified` der Registry trägt bei dl-de/by-2-0 und swisstopo-OGD den Zusatz „(Daten verändert)“ bzw. „(modified)“. Das ist schon heute die Form der Registry für den DEM [A].

Zwei Punkte gehen über B11 hinaus und gehören an Otto, aber in kein neues Feld:

- **MeteoSchweiz, Warnungen:** Warnungen dürfen nur unverändert weitergegeben werden [P]. Warnungen sind keine Raster dieser Runde; der Punkt kommt in die Bedingungen, falls je eine Warnkarte dazukommt.
- **MeteoSchweiz, kein Anschein einer Unterstützung:** Die Quellenangabe darf nicht so aussehen, als unterstütze MeteoSchweiz die Plattform [P]. Das betrifft den Text der Attribution, nicht die Flags.

### 7.3 `data_region` (Vorschlag nach `adr/0022` §7.2)

| Quelle | Wert (Vorschlag) | Beleg |
|---|---|---|
| FSDI (swisstopo, MeteoSchweiz außer ICON) | `aws:eu-central-1` | Code-Vorgabe [P], Produktion zu messen |
| MeteoSchweiz ICON | `cscs:lugano` | „CSCS public cloud object storage“ [P]; Standort Lugano [A] |
| LGLN | `ibm:eu-de` | Host des Kachelindex [P] |
| GeoSphere, BEV, DWD, Länder | unbekannt; vermutlich eigene Rechenzentren in AT bzw. DE | — |
| ESA WorldCover | `aws:eu-central-1` | Registry [P], Host [M] |
| EOPF, EODC | `eodc:vienna` | `adr/0022` |
| JAXA Earth API | unbekannt | — |

Für eigene Rechenzentren schlägt dieses ADR die Form `<betreiber>:<ort>` vor, etwa `dwd:offenbach` [A]. Ein Startcheck gegen `asset_hosts` geht dann nicht; er bleibt AWS-Hosts vorbehalten (`adr/0022` §7.2).

### 7.4 Kataloge für die Discovery (Eingabe für `adr/0025`)

| Katalog | Protokoll | ohne Schlüssel | Lizenz maschinenlesbar | Beleg |
|---|---|---|---|---|
| FSDI STAC (CH) | STAC API v1 | ja | `license` meist `proprietary`; Link auf Bedingungen | P/S |
| GeoSphere `/v1/datasets` | eigene REST-API mit Metadaten | ja | eine Lizenz für alles | P |
| opendata.swiss | CKAN v3, DCAT-AP CH | vermutlich | `terms_*` je Datensatz | S |
| data.gv.at | CKAN, DCAT-AP | nicht belegt | je Datensatz | S |
| GovData | CKAN v3, DCAT-AP.de | ja (Leitfaden) | Lizenz-URIs aus DCAT-AP.de | S |
| LGLN STAC | STAC API | vermutlich | offen | S |
| STAC Index | eigene API | nicht prüfbar (gesperrt) | — | — |
| AWS Open Data Registry | YAML im Repo `awslabs/open-data-registry` | ja | Freitext im Feld `License` | P |
| EODC STAC | STAC API | unbekannt | unbekannt | P\* |
| CEOS FedEO (u. a. ESA CCI) | OpenSearch, STAC | unbekannt | je Datensatz | S |

### 7.5 Weitergabe an die anderen Vorlagen

- **An `adr/0024` (Prototyp-Quellen):** Kandidaten mit unklarer Rechtslage sind:
  - Liechtenstein (DTM, Orthofoto `terms_by_ask`);
  - die Länder ohne belegte Lizenz (Vorarlberg, Salzburg, NÖ);
  - die Weiterverarbeitung von basemap.at- und TopPlusOpen-Kacheln als Raster.
  
  Dieses ADR stuft sie nicht ein.
- **An `adr/0027` (Konten):**
  - CDSE (Download), NASA Earthdata Login, CODE-DE, EUMETSAT/CM SAF und TanDEM-X 90 m;
  - Copernicus CDS/ADS (C3S, CAMS, CEMS), Copernicus Marine und CLMS (EU Login);
  - Landsat und `sentinel-s2-l1c` (Requester Pays).
- **An `adr/0026` (Suche):** Die Begriffe der Quellen sind mehrsprachig (de/fr/it/en bei der FSDI). Das Bewertungs-Set sollte deutsche und englische Fragen enthalten.

---

## 8. Rangliste und Empfehlung

### 8.1 Bewertung der Kandidaten

Bewertet sind nur Kandidaten, die K1 bis K3 nach heutigem Stand erfüllen. ✓ = erfüllt, ~ = teilweise oder nur [S], ✗ = nicht erfüllt.

| Kandidat | K1 anonym | K2 Lizenz | K4 Format | K5 Schnittstelle | K6 Region | K7 Betrieb | K8 Nutzen DACH | K9 Aufwand | Belege |
|---|---|---|---|---|---|---|---|---|---|
| **ESA WorldCover 10 m** | ✓ [M] | ✓ CC BY 4.0 [M] | ✓ COG [M] | ~ Bucket mit Kachelraster, kein STAC | ✓ `eu-central-1` | ✓ ETag [M] | mittel: Landbedeckung, neu | klein: Weg des DEM | M/P |
| **swisstopo swissALTI3D** | ✓ [S] | ✓ OGD [S] | ✓ COG [S] | ✓ STAC API | ✓ vermutlich `eu-central-1` [P] | ✓ ETag empfohlen [P] | hoch: DTM 0,5 m CH + FL | mittel: STAC-Adapter für eine zweite STAC-Quelle, LV95 | P/S |
| swisstopo SWISSIMAGE 10 cm | ✓ [S] | ✓ OGD [S] | ~ COG offen | ✓ STAC API | ✓ wie oben | ✓ | hoch: Orthofoto | klein nach swissALTI3D (gleicher Adapter) | S |
| **BEV ALS-DGM 1 m** (auch DOP 20 cm) | ✓ [S] | ✓ CC BY 4.0 [S] | ~ COG laut Metadaten | ~ ATOM | unbekannt (AT) | unbekannt | hoch: DTM für AT | mittel: neue Nicht-STAC-Quelle, EPSG:3035, 50-km-Kacheln | S |
| LGLN DOP20/DGM1 (Niedersachsen) | ✓ [S] | ✓ dl-de/by-2-0 [P] | ✓ COG [S] | ✓ STAC (Adresse offen) | ✓ `ibm:eu-de` [P] | unbekannt | mittel: ein Land | klein nach swissALTI3D | P/S |
| MeteoSchweiz Klimagitter 1 km | ✓ [P] | ✓ CC BY 4.0 [P] | ✗ NetCDF | ✓ STAC API (dieselbe wie swisstopo) | ✓ wie swisstopo | ✓ ETag [P] | hoch: Meteorologie | groß: Reader für Gruppe D | P |
| GeoSphere SPARTACUS/WINFORE | ✓ [P] | ✓ CC BY 4.0 [P] | ✗ Abfrage-API / NetCDF | ~ eigene API, 240/h | unbekannt (AT) | ~ Limit [P] | hoch: Meteorologie AT | groß | P |
| DWD HYRAS/HOSTRADA | ✓ [S] | ✓ CC BY 4.0 [S] | ✗ NetCDF | ~ Dateiserver | unbekannt (DE) | unbekannt | hoch: Meteorologie DE | groß | S |
| JAXA Earth API | ~ [S] | ~ je Collection [S] | ✓ COG [S] | ✓ STAC [S] | ✗ vermutlich Japan | unbekannt | mittel | mittel | S |

### 8.2 Empfehlung: drei Quellen von Hand

**Option 1 (Empfehlung):** ESA WorldCover, dann swissALTI3D, dann BEV ALS-DGM 1 m.

- **Warum diese drei [A]:**
  - Alle drei liegen in Gruppe A (§7.1). Es braucht keinen neuen Reader.
  - Sie stressen die beiden Achsen aus Prinzip 3 und 4 dort, wo der Code heute dünn ist:
    - WorldCover ist eine Bucket-Quelle mit Kachelraster wie der DEM, aber eine Klassifikation. Damit wird `adr/0009` erstmals wiederverwendet statt neu gebaut.
    - swissALTI3D ist die zweite STAC-API nach Earth Search. Daraus wird der Earth-Search-Adapter zu einem allgemeinen STAC-Adapter. Den brauchen danach SWISSIMAGE, MeteoSchweiz und LGLN.
    - BEV ist eine Nicht-STAC-Quelle mit ATOM-Feed. Das ist ein Muster, das viele Behörden in DACH nutzen (INSPIRE-Downloaddienste).
  - Die Projektionen LV95 und LAEA (EPSG:3035) testen die Reprojektion außerhalb von UTM und WGS84.
  - Zusammen mit dem Copernicus DEM ergeben sie Geländedaten in drei Stufen für die Alpen: 30 m weltweit, 1 m für AT, 0,5 m für CH und FL.
- **Reihenfolge:** WorldCover zuerst. Es ist als einziger Kandidat schon gemessen, und der Weg ist bekannt. BEV zuletzt, weil COG und Zugang dort erst zu bestätigen sind (§9).
- **Bedingung:** Die Prüfung in §9 bestätigt anonymen Zugriff, COG mit Overviews und Range-Requests. Fällt BEV durch, rückt LGLN nach (Option 3).

**Option 2:** WorldCover, swissALTI3D und MeteoSchweiz-Klimagitter.

- Meteorologie käme früher, wie Otto sie will.
- Dafür muss zuerst ein Leseweg für NetCDF entschieden und gebaut werden (§7.1, F3). Das ist ein rechenrelevanter Schritt mit eigener Recherche, und die Handarbeit vor der Pipeline wird deutlich größer.

**Option 3:** WorldCover, swissALTI3D und LGLN DOP20/DGM1.

- Wenig Aufwand, weil der STAC-Adapter derselbe ist.
- Deckt aber nur ein Bundesland. Die STAC-Adresse ist noch nicht gefunden.

**Option 4:** Nur zwei Quellen (WorldCover, swissALTI3D). Die dritte folgt nach der Prüfung in §9.

**Meteorologie** folgt in jedem Fall als nächster Block nach der Entscheidung zum Leseweg (F3). Erster Kandidat ist dann MeteoSchweiz `ogd-surface-derived-grid` [A], aus drei Gründen:

- gleicher STAC-Adapter wie swissALTI3D;
- Lizenz und ETag am Primärtext belegt;
- kleine Dateien (1–13 MB) und ein dauerhaftes Jahresarchiv.

Danach kommen DWD HYRAS und GeoSphere-Dateien.

### 8.3 Eigenheiten der empfohlenen Datensätze (Plan §2 Punkt 7)

Die Eigenheiten werden in den Feldern der Registry festgelegt, die es schon gibt. Was kein Feld hat, ist als neu markiert. Alle Werte sind Vorschlag [A]; sie werden beim Onboarding gegen die Quelle geprüft.

**ESA WorldCover (`esa-worldcover`):**

- **Processing:**
  - `data_class` = statisches Raster mit zwei Ständen. `time_range` = true, damit 2020 und 2021 wählbar sind. Alternativ zwei Datensätze, siehe F6.
  - `masking` = true mit `earthx:mask`: Asset `map`, Band 1, die elf Klassen; `cloud_classes` leer.
  - `value_masking` = true.
  - `band_math` = false (Rechnen mit Klassencodes ergibt keinen Sinn).
  - `reprojection` = true, aber `interpolation` = **false**: Klassen nur mit `nearest`. Das setzt `adr/0014` F6 schon so um.
  - `normalization` = false.
  - Eigener Operator: keiner.
- **Erweiterte Suche:** `search_filters` leer. Filter gibt es nach `adr/0021` §2 Punkt 1 vorerst nur für föderierte Datensätze; der Stand wird über den Zeitraum gewählt.
- **Schnellrechnungen:** `index_presets` leer.
- **Darstellung:** `default_render` mit der Farbtabelle aus der Datei (die Klassenfarben von ESA).
- **Hinweis in der Beschreibung:** 2020 und 2021 sind nicht direkt vergleichbar.
- **Coverage:** aus dem Kachelraster (`LOCAL_SQL`), Einmal-Befehl wie beim DEM.

**swisstopo swissALTI3D (`swissalti3d`):**

- **Processing:**
  - `data_class` = statisches Raster. `time_range` = false, wie beim DEM; das Befliegungsjahr je Kachel ist eine Eigenschaft, keine Zeitachse.
  - `band_math`, `reprojection`, `interpolation` und `normalization` = true. `masking` = false.
  - `value_masking`: nach Wunsch Ottos, bei Höhen meist sinnlos.
  - Eigener Operator: Hangneigung, Exposition und Schummerung. Das ist ein **neuer generischer Geländeoperator**, gebunden an eine **neue Capability** (Vorschlag `terrain`), die nur Höhenmodelle setzen (B10, F5). Dasselbe gilt dann für BEV und den Copernicus DEM.
- **Erweiterte Suche:**
  - Auflösung 0,5 m oder 2 m. Das ist eine Wahl des Assets, kein Filter. Die Registry braucht dafür eine Angabe, welches Asset die Plattform liest; heute gibt es dafür `default_render.assets`. Ob das reicht, klärt das Onboarding.
  - Befliegungsjahr: Die Suche der FSDI kennt `bbox`, `intersects`, `datetime`, `ids`, `collections`, Sortierung und die `forecast:*`-Felder, aber weder die Query-Extension noch CQL2 (`service-stac`, `app/stac_api/managers.py`, Konformitätsklassen in den Migrationen) [P]. Ein Filter nach `adr/0021` geht also nicht an die Quelle.
    - Das Jahr lässt sich nur über `datetime` wählen. Das hilft nur, wenn das Item-Datum das Befliegungsjahr ist; zu prüfen in §9.
    - `search_filters` bleibt deshalb vorerst leer.
- **Schnellrechnungen:** `index_presets` leer. Gelände kommt über den Operator.
- **Darstellung:** Graustufen oder `terrain`-Colormap mit festem Bereich.
- **`band_units`:** `m` (LN02).
- **Attribution:** „© swisstopo“. Der genaue Wortlaut steht auf der Seite zur Quellenangabe von swisstopo und ist vor dem Eintrag zu lesen.
- **Coverage:** Die FSDI kennt keine Aggregation (nicht belegt). Deshalb `LOCAL_SQL` aus materialisierten Items, rund 45 000 Kacheln zu 1 km² [A]. Ob die Items trotzdem föderiert gesucht werden, entscheidet die Umsetzung (`architekturplan.md` 5.2).

**BEV ALS-DGM 1 m (`bev-als-dgm`):**

- **Processing, Suche und Schnellrechnungen:** wie swissALTI3D. Projektion EPSG:3035, ein Stand.
- **Unterschied:** 55 Kacheln zu 50 km statt 45 000 zu 1 km. Die Items kommen aus dem ATOM-Feed. Die Coverage ist eine Fläche (`complete`).
- **Prüfpunkt:** Ohne Overviews ist eine 50-km-Kachel bei kleinem Maßstab zu langsam [A].
  - Dann zeigt die Karte den Datensatz erst ab einer hohen Zoomstufe (`viewer.min_zoom`, M2-10).
  - Zuschnitt und Processing über die AOI bleiben möglich, weil sie nur die Blöcke der AOI lesen.

**Neu in der Registry, für alle drei:**

- `data_region` (`adr/0022` F3, beschlossen; Werte §7.3).
- Die Capability `terrain`, falls F5 = 1.

---

## 9. Offene Prüfungen und Prüfanleitung

### 9.1 Was vor dem Onboarding zu prüfen ist

| Quelle | Prüfpunkt |
|---|---|
| swissALTI3D, SWISSIMAGE | anonym; `license` der Collection; Medientyp der Assets (COG?); Region (`x-amz-bucket-region` bzw. Host); Range `206`; ETag; CORS der Assets; Bedeutung von `datetime` am Item |
| MeteoSchweiz Klimagitter | wie oben; Größe und Aufbau einer NetCDF-Datei (für F3) |
| BEV ALS-DGM, DOP | ATOM-Feed ohne Anmeldung; COG mit Overviews; Range; ETag; Lage der Server |
| LGLN | Adresse der STAC-API; Lizenz DGM1/DOM1 |
| GeoSphere | Kopfzeilen `x-ratelimit-*`; Dateidownload im Data Hub ohne Konto |
| DWD | Range und ETag auf dem Dateiserver |
| JAXA Earth API, EODC STAC | Schlüssel nötig? Lizenz je Collection; Region |
| swisstopo, BEV, DWD, BKG | Wortlaut der Nutzungsbedingungen und des Quellenvermerks (für Otto) |

### 9.2 Weg A: Skript auf Ottos Rechner (empfohlen)

`scripts/m5-01-sources/probe.py` prüft sieben Quellen:

- die drei FSDI-Collections (swissALTI3D, SWISSIMAGE, MeteoSchweiz-Klimagitter);
- die GeoSphere-API;
- den DWD-Server;
- den LGLN-Kachelindex;
- eine WorldCover-Kachel.

**Wie es prüft:**

- Jeder Abruf läuft über `gateway`, mit einer Allowlist genau aus den Hosts der jeweiligen Quelle.
- Je STAC-Quelle: Collection, das erste Item (`limit=1`, keine Fläche) und dessen erstes Daten-Asset.
- Je Datei: `HEAD` mit `Origin` und ein `GET` auf die ersten 1024 Bytes.
- Ausgegeben werden Statuscodes und Kopfzeilen. Bei ETag und Last-Modified steht nur „yes/no“. Es erscheinen nie eine Adresse, eine Item-ID oder eine Signatur.

```powershell
$env:PYTHONPATH = 'backend'
python scripts/m5-01-sources/probe.py
#   je Zeile: Quelle, Eigenschaft, Wert, z. B. "fsdi-alti  GET range 0-1023  206 (1024 bytes)"
python scripts/m5-01-sources/probe.py fsdi-alti worldcover   # nur diese beiden
```

Aus der Cloud-Sitzung geht das Skript nicht [M]. `gateway` verbindet die geprüfte Adresse ohne den Proxy der Sitzung und meldet `AddressRejected` (`adr/0002`). Ottos Ausgabe genügt als Beleg [M] für die Nachträge.

BEV, JAXA und EODC stehen nicht im Skript, weil ihre Adressen nur aus Suchtreffern bekannt sind. Sie werden in Weg B oder beim Onboarding geprüft.

### 9.3 Weg B: neue Sitzung mit freigegebenen Hosts

Otto gibt diese Hosts in der Umgebung frei. Die Freigabe wirkt erst in einer neu gestarteten Sitzung (`cloud-umgebung.md`, Regel zur Allowlist). Danach misst eine Sitzung mit `curl` wie in `adr/0009` und liest die Doku als P statt S:

- **Schweiz:** `data.geo.admin.ch`, `www.swisstopo.admin.ch`, `www.geo.admin.ch`, `opendatadocs.meteoswiss.ch`, `ckan.opendata.swiss`
- **Österreich:** `dataset.api.hub.geosphere.at`, `data.hub.geosphere.at`, `data.bev.gv.at`, `www.bev.gv.at`, `stac.eodc.eu`
- **Deutschland:** `opendata.dwd.de`, `gdz.bkg.bund.de`, `sg.geodatenzentrum.de`, `opengeodata.lgln.niedersachsen.de`, `www.govdata.de`
- **Satellit und Kataloge:** `data.earth.jaxa.jp`, `stacindex.org`

`esa-worldcover.s3.eu-central-1.amazonaws.com` ist schon erreichbar [M].

---

## 10. Fragen an Otto

**F1 — Welche Quellen bindet M5 zuerst von Hand an (§8.2)?**
1. ESA WorldCover, swissALTI3D, BEV ALS-DGM 1 m, in dieser Reihenfolge, je nach Prüfung in §9 **(Empfehlung)**
2. ESA WorldCover, swissALTI3D, MeteoSchweiz-Klimagitter (mit Leseweg NetCDF vorab, F3)
3. ESA WorldCover, swissALTI3D, LGLN DOP20/DGM1
4. Zuerst nur WorldCover und swissALTI3D, die dritte nach §9

**F2 — Lizenz-Einstufung der gewählten Quellen (§7.2)?**
1. Die Vorschläge aus §7.2 für die Quellen aus F1 annehmen. Die Wortlaute der Bedingungen prüfst du vor dem Eintrag selbst **(Empfehlung)**
2. Jede Quelle einzeln beim Onboarding vorlegen
3. swisstopo-OGD erst nach Rechtsberatung; bis dahin nur Katalogeintrag

**F3 — Leseweg für NetCDF/HDF5 (Meteorologie, §7.1)?**
1. Eigene Recherche mit Messung (Stufe C) zu virtuellem Zarr, GDAL-Treiber über `/vsicurl/` und flüchtigem COG-Cache, an MeteoSchweiz-Klimagittern und DWD HYRAS; danach erste Meteorologie-Quelle **(Empfehlung)**
2. Meteorologie vorerst nur als Katalogeintrag mit Link (B11 Stufe 1), ohne Anzeige
3. Meteorologie nach M5

**F4 — Wie werden die offenen Punkte aus §9 geprüft?**
1. Du führst `probe.py` aus (Weg A) und gibst die Hosts aus §9.3 für die Onboarding-Sitzungen frei **(Empfehlung)**
2. Nur Weg A
3. Nur Weg B

**F5 — Geländeoperator (Hangneigung, Exposition, Schummerung)?**
1. Eigene Aufgabe nach dem ersten hochaufgelösten DGM: ein generischer Operator, gebunden an eine neue Capability `terrain`, die nur Höhenmodelle setzen (B10) **(Empfehlung)**
2. Nicht in M5
3. Nur als Darstellung im `tiler` (Algorithmus), kein Operator

**F6 — WorldCover 2020 und 2021: ein Datensatz oder zwei?**
1. Ein Datensatz mit Zeitachse (`time_range` = true, zwei Stände), Hinweis auf eingeschränkte Vergleichbarkeit in der Beschreibung **(Empfehlung)**
2. Zwei Datensätze (`esa-worldcover-2020`, `-2021`), je statisch
3. Nur 2021 (v200)

**F7 — `data_region` für Quellen ohne Cloud-Region (§7.3)?**
1. Form `<betreiber>:<ort>` wie `dwd:offenbach`, ohne Startcheck; `unknown`, solange der Ort nicht belegt ist **(Empfehlung)**
2. Nur Länderkennung (`de`, `at`, `ch`)
3. Feld leer lassen, bis gemessen

---

## 11. Quellen

Abgerufen bzw. gesucht am 31.10.2026. Die Belegstufe steht in Klammern.

**Quelltexte auf GitHub (P), geklont in das Kratzverzeichnis:**

- MeteoSchweiz, Doku `opendatadocs.meteoswiss.ch`: https://github.com/MeteoSwiss/opendata
  - `docs/general/terms-of-use.md`, `docs/general/download.md`
  - `docs/c-climate-data/c3-…`, `c4-…`, `c5-…`, `c7-…`
  - `docs/d-radar-data/d1-…`
  - `docs/e-forecast-data/e1-…`, `e2-e3-…`
- MeteoSchweiz, ICON: https://github.com/MeteoSwiss/opendata-forecast-data (README)
- GeoSphere Austria, Doku der Dataset API: https://github.com/Geosphere-Austria/dataset-api-docs
  - `src/user-guide/authentication.md`, `license.md`, `request-limit.md`, `type.md`, `mode.md`, `resource.md`
  - `src/conf.py`, `src/changelog.md`
- FSDI, STAC-Dienst: https://github.com/geoadmin/service-stac
  - `app/config/settings_prod.py` (S3-Regionen)
  - `app/middleware/cors.py`
  - `app/stac_api/managers.py` (Suchparameter)
  - `app/stac_api/migrations/0067_…`, `0083_…` (Konformitätsklassen)
- Niedersachsen, Notebook eines LGLN-Mitarbeiters (keine amtliche Seite): https://github.com/BostelmannLGLN/LGLN-OpenData-Notebooks (`DOP.ipynb`)
- AWS Open Data Registry: https://github.com/awslabs/open-data-registry
  - `datasets/esa-worldcover-vito.yaml`, `sentinel-1.yaml`, `sentinel-2.yaml`, `copernicus-dem.yaml`
- Earth Search: https://github.com/Element84/earth-search (README, v2 beta)
- SPDX-Liste: https://github.com/spdx/license-list-data (`json/licenses.json`, Stand 28.10.2026)

**Gemessen (M):**

- `https://earth-search.aws.element84.com/v1/collections`
- der Bucket `esa-worldcover` in `eu-central-1`: Listing, `HEAD` und Range-GET auf eine Kachel, Kopf der Datei über GDAL

**Über das Abrufwerkzeug gelesen (P\*):**

- Thünen, Anbauartenkarte: https://zenodo.org/records/15309479, /15055561, /17181503
- Earth Search Collections: `sentinel-2-c1-l2a`, `sentinel-1-grd`, `cop-dem-glo-30`/`-90`, `landsat-c2-l2`
- AWS Registry, Seiten: https://registry.opendata.aws/esa-worldcover-vito/, /deafrica-alos-jers/, /ebd-sentinel-1-global-coherence-backscatter/, /modis/
- EOPF: https://stac.core.eopf.eodc.eu/collections
- EODC: https://data.eodc.eu/ (Liste der Collections)
- Planetary Computer, anonyme Tokens: https://github.com/microsoft/PlanetaryComputer/discussions/351

**Suchtreffer (S), Auswahl:**

- **swisstopo/FSDI:**
  - https://docs.geo.admin.ch/download-data/stac-api/overview.html
  - https://www.geo.admin.ch/en/general-terms-of-use-fsdi
  - https://www.geo.admin.ch/en/change-limits-fair-use
  - https://www.swisstopo.admin.ch/en/conditions-geodata
  - https://www.swisstopo.admin.ch/en/source-reference-ogd-swisstopo
  - Produktinfos swissALTI3D und SWISSIMAGE 10 cm (swisstopo, PDF)
  - https://discuss.graphhopper.com/t/adding-support-for-swissalti3d-elevation-opendata/7774
- **opendata.swiss:**
  - https://handbook.opendata.swiss/fr/content/nutzen/api-nutzen.html
  - https://opendata.swiss/en/terms-of-use
  - https://ckan.opendata.swiss/dataset/orthophoto-liechtenstein-2025
- **BEV und INSPIRE-Metadaten:**
  - https://www.bev.gv.at/Services/Produkte/Digitales-Gelaendehoehenmodell/ALS-Hoehenraster.html
  - https://inspire-geoportal.ec.europa.eu/srv/api/records/3c5ff5da-12cd-4e11-8a9c-a221d6e68ff2
- **basemap.at:** https://cdn.basemap.at/basemapat-fact-sheet.pdf
- **Österreichische Länder:**
  - https://geodaten.bgld.gv.at/de/downloads/hoehenmodelle-orthofotos.html
  - https://tirol.gv.at/sicherheit/geoinformationen-karten/freie-laserscandaten-und-orthofotos
  - https://www.landesentwicklung.steiermark.at/cms/beitrag/12803182/142970647/
- **EODC:** https://docs.eodc.eu/services/stac.html
- **DWD:**
  - https://opendata.dwd.de/README.txt
  - https://opendata.dwd.de/climate_environment/CDC/Nutzungsbedingungen_German.pdf
  - die Beschreibungen zu HYRAS, HOSTRADA, DUETT und RADKLIM unter `opendata.dwd.de/climate_environment/CDC/`
- **BKG:**
  - https://sg.geodatenzentrum.de/public/gdz/dokumentation/deu/dgm200.pdf
  - https://sg.geodatenzentrum.de/web_public/gdz/lizenz/deu/nutzungsbedingungen_dop.pdf
- **Länder DE:**
  - https://pretalx.com/fossgis2024/talk/HPLTPQ/ (LGLN STAC)
  - https://pretalx.com/fossgis2025/talk/UAG3YL/
  - https://ckan-open-nrw.nrw.de/en/dataset/0c6796e5-9eca-4ae6-8b32-1fcc5ae5c481
- **DLR:**
  - https://download.geoservice.dlr.de/WSF_EVO/
  - https://geoservice.dlr.de/web/dataguide/tdm90/
- **JAXA:**
  - https://data.earth.jaxa.jp/en
  - https://www.eorc.jaxa.jp/ALOS-2/en/doc/sam_index.htm
- **ESA CCI:** https://climate.esa.int/en/data/
- **CLMS:** https://land.copernicus.eu/en/faq/general-questions
- **NISAR:** https://asf.alaska.edu/notices/nisar-l-band-data-now-publicly-available/
