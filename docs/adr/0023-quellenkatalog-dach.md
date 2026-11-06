# ADR 0023 — Quellenkatalog DACH und Satellit

- **Status:** Angenommen (fest, Otto, 06.11.2026; Antworten in §10). Offen bleiben die in §10 und §9.1 als **offen** markierten Teile, vor allem der Nachtrag aus Ottos Lauf von `probe.py` und die Stände je Kachel bei swissALTI3D und BEV (§8.3). Die Nummer 0023 ist im M5-Plan fest vergeben (`plans/m5/m5-discovery-und-suche.md` §5a).
- **Datum:** 2026-10-31 (Entwurf, gemergt mit PR #262); fortgeschrieben 2026-11-06 (M5-01b).
- **Aufgabe:** M5-01 laut `docs/plans/m5/m5-discovery-und-suche.md` §5a (Entscheidungsvorlage A, §4); Fortschreibung M5-01b nach Ottos Antworten.
- **Autonomiestufe:** C. Kein Produktivcode.
  - M5-01 änderte dieses ADR, eine Zeile im Entscheidungslog und das Messskript `scripts/m5-01-sources/probe.py`. Das Skript ruft nur über `gateway` ab und läuft auf Ottos Rechner (§9).
  - M5-01b ändert nur dieses ADR und das Entscheidungslog. Die Messung lief mit `curl` aus der Sitzung (§9.3).
  - Unverändert bleiben `backend/`, `frontend/`, Registry, Fixtures, Backlog, M5-Plan, `.github/`, `.claude/` und `CLAUDE.md`.
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

**Messung vom 06.11.2026 (Weg B, M5-01b) [M]:**

- Die Hosts aus §9.3 sind in der Umgebung freigegeben (F4). Zu Beginn der Sitzung standen sie noch nicht in der Allowlist; der Proxy antwortete mit `403`. Nach dem Eintrag mit Ottos Freigabe waren sie erreichbar.
- Gemessen wurden nur Metadaten:
  - STAC-Collection und ein Item (`limit=1`) bzw. der ATOM-Feed;
  - je Datei `HEAD` mit `Origin`-Header, ein Range-GET auf die ersten 16 KB und eine bedingte Anfrage mit `If-None-Match`;
  - der Kopf der Datei über GDAL (`/vsicurl/`, liest nur den TIFF-Kopf und die IFDs).
- Kein Pixelblock wurde gelesen, keine Datei vollständig geladen.
- Adressen, Item-IDs, Kachelnamen und genaue Flächen stehen nicht in diesem Dokument.
- Die Seiten mit den Nutzungsbedingungen von swisstopo und der Metadatensatz des BEV sind seitdem **P**.
- Der Standort der BEV-Server ließ sich nicht prüfen: Eine Namensauflösung aus der Sitzung wurde abgelehnt.

---

## 0. Kurzfassung

1. **Es gibt viel ohne Schlüssel, aber wenig in einem Format, das die Plattform heute liest** [A, aus §3–§6]:
   - In COG liegen ESA WorldCover [M], swissALTI3D [M], das Geländemodell des BEV [M], die Orthofotos des BEV [S], die Daten Niedersachsens [S] sowie der Copernicus DEM.
   - Die Meteorologie aller drei Länder (DWD, MeteoSchweiz, GeoSphere) liegt nur als NetCDF, HDF5 oder GRIB2 vor oder hinter einer Abfrage-API. Lizenzen und Zugang wären in Ordnung (CC BY 4.0, ohne Konto; bei MeteoSchweiz und GeoSphere am Primärtext belegt [P]).
2. **Lizenzen sind fast überall offen** (§7.2):
   - CC BY 4.0: MeteoSchweiz [P], GeoSphere [P], WorldCover [M], BEV [P], DWD [S].
   - dl-de/by-2-0 und dl-de/zero-2-0: die meisten deutschen Länder [S].
   - swisstopo-OGD ohne SPDX-Kennung [P].
   - Daraus folgt der Vorschlag „Processing“ für alle empfohlenen Quellen. Die Einstufung gibt Otto.
3. **Lage der Daten** (§7.3):
   - Die Schweizer Bundes-Geodaten liegen nach der Vorgabe im Code des Dienstes in AWS `eu-central-1` [P]; ICON liegt bei CSCS.
   - WorldCover liegt in `eu-central-1` [M], Niedersachsen in IBM `eu-de` [P].
   - DWD, BEV und GeoSphere: unbekannt, vermutlich eigene Rechenzentren in DE bzw. AT.
4. **Entscheidung für die Handarbeit vor der Pipeline (§8, F1, fest):** ESA WorldCover, dann swissALTI3D, dann BEV ALS-DGM 1 m.
   - Die Bedingung für BEV ist erfüllt [M]: ATOM-Feed ohne Anmeldung, COG mit Overviews bis 1:256, Range-Requests mit `206`.
   - Alle drei kommen ohne neuen Reader aus.
   - Sie stressen die Achsen aus Prinzip 3 und 4: Bucket mit Kachelraster, eine zweite STAC-API, ATOM; dazu LV95 und LAEA.
   - Die Meteorologie folgt als nächster Block, sobald ein Leseweg für NetCDF entschieden ist (F3, eigene Recherche).
5. **Eigenheiten je Datensatz (§8.3):** Für die drei Quellen sind Processing, Suche und Schnellrechnungen in Feldern der Registry vorgeschlagen.
   - Neu sind nur `data_region` (beschlossen) und eine Capability `terrain` für einen Geländeoperator (F5, fest).
   - WorldCover wird zwei Datensätze, je Stand einer (F6 Option 2): Eine Ansicht kann Kacheln beider Jahre zeigen (§10, F6).
   - Suchfilter bleiben bei allen dreien vorerst leer. Die FSDI-Suche kennt weder Query noch CQL2 [P], und materialisierte Datensätze haben nach `adr/0021` noch keine Filter.
6. **Neu aus der Messung [M]:** swissALTI3D und BEV halten mehrere Stände derselben Kachel. Bei swissALTI3D liegen an einem Ort Items von 2019 und 2025, beim BEV sechs Stichtage (2019 sowie 2021 bis 2025) je 55 Kacheln. Wie das in die Registry kommt, ist **offen** (§8.3).
7. **Offen:** der Nachtrag aus Ottos Lauf von `scripts/m5-01-sources/probe.py` (F4), die Wortlaute der Bedingungen (F2, Otto), die Lage der BEV-Server und die STAC-Adresse des LGLN (§9.1).
8. **Nicht gefunden:** komplexe Quad-Pol-Daten ohne Konto (§6.3). `decomp` ruht weiter.

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
- **ETag und bedingte Requests [P, M]:**
  - Die Doku empfiehlt ausdrücklich `If-None-Match` mit dem ETag; der Server antwortet dann `304 Not Modified` [P].
  - Gemessen am 06.11.2026 [M]: Collection und Asset tragen ein ETag, das Asset auch Last-Modified. Eine bedingte Anfrage auf das Asset ergibt `304`.
  - Gemessen ist auch das Caching [M]: `Cache-Control: max-age=7200` am Asset, `max-age=600` an der Collection.
  - Das passt genau zur Abnahme von M5: Ein Lauf ohne Änderung kostet nur bedingte Requests.
- **CORS [P, M]:** Die API setzt `Access-Control-Allow-Origin: *` (`service-stac`, `app/middleware/cors.py`) [P]. Die Asset-Dateien setzen bei einem `Origin`-Header ebenfalls `Access-Control-Allow-Origin: *` mit `GET, HEAD` [M].
- **Lage der Daten:**
  - Der Dienst schreibt verwaltete Assets in einen S3-Bucket. Seine Vorgabe ist die Region `eu-central-1`; ältere Bestände liegen nach der Vorgabe in `eu-west-1` (`service-stac`, `app/config/settings_prod.py`) [P].
  - Gemessen [M]: Die Assets kommen über den Host der API aus S3 hinter CloudFront (`server: AmazonS3`, `via: … cloudfront.net`). Die Kopfzeile `x-amz-bucket-region` fehlt, die Region des Buckets ist also nicht gemessen.
  - **Vorschlag für `data_region`:** `aws:eu-central-1` nach der Code-Vorgabe [P]. Die Region des Buckets bleibt **offen**. Auch Ottos Lauf von `probe.py` dürfte sie nicht zeigen, weil CloudFront sie verdeckt [A].
- **Lizenz swisstopo [P]** (Nutzungsbedingungen für kostenlose Geodaten und Geodienste, Version 1.3.2021, gelesen am 06.11.2026):
  - Seit 01.03.2021 sind die Standardprodukte von swisstopo Open Government Data.
  - Die Daten „dürfen genutzt, verbreitet und zugänglich gemacht werden“, „angereichert, bearbeitet sowie auch kommerziell genutzt werden“.
  - „Eine Quellenangabe ist Pflicht“. Zur Wahl stehen der Name des Amtes in einer der Landessprachen oder Englisch und „©swisstopo“. Für swissALTI Regio und swissEO gilt eine andere Quellenangabe; swissALTI3D gehört nicht dazu.
  - Bei übermäßiger Nutzung kann swisstopo den Zugang einschränken. Ergänzend gelten die allgemeinen Bedingungen der BGDI.
  - Es gibt keine SPDX-Kennung (SPDX-Liste [P]). Die Collection trägt `license: proprietary` und keinen Link mit `rel=license` [M].
  - **Vorschlag:** `spdx_id = None`, Name und URL der swisstopo-Bedingungen, `attribution_required = true`, alle anderen Flags `true`, Stufe Processing. **Einstufung durch Otto** (F2: Otto prüft die Wortlaute vor dem Eintrag).

**Datensätze von swisstopo (swissALTI3D [M] am 06.11.2026, die übrigen [S]):**

| Collection | Inhalt | Auflösung, Kachel | Format | Zeit |
|---|---|---|---|---|
| `ch.swisstopo.swissalti3d` | Geländemodell (DTM), Schweiz und Liechtenstein | 0,5 m (2000² px) und 2 m (500² px) als getrennte Assets eines Items, Kacheln 1 km [M] | COG [M]: Medientyp `profile=cloud-optimized`, LZW, Blöcke 128², Overviews 2/4/8 (0,5 m) bzw. 2 (2 m); Float32, Nodata −9999, EPSG:2056 [M]; Höhen LN02 [S]. Daneben je Auflösung ein Asset als ASCII-XYZ (ZIP) | Item-`datetime` = Jahr im Namen des Assets [M]. Mehrere Stände derselben Kachel als eigene Items, z. B. 2019 und 2025 an einem Ort [M]. Zeitraum der Collection 2019 bis 2026 [M] |
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

### 4.2 BEV (Bundesamt für Eich- und Vermessungswesen) [ALS-DGM M am 06.11.2026, sonst S]

- **ALS-DGM 1 m (Höhenraster) und ALS-DOM 1 m [M]:**
  - Katalog ist ein GeoNetwork auf `data.bev.gv.at`; Suche und Metadaten sind ohne Anmeldung lesbar.
  - Der INSPIRE-ATOM-Downloaddienst „ALS EL Höhendaten“ ist ohne Anmeldung lesbar. Er listet DTM und DSM zu den Stichtagen 15.09.2019 und 15.09.2021 bis 15.09.2025, je Stichtag und Modell 55 Kacheln zu 50 km, EPSG:3035.
  - Der Feed sagt: „Der öffentliche Zugang zu diesem Produkt unterliegt keinen Einschränkungen.“
  - Je Kachel führt ein Dataset-Feed auf genau eine Datei `image/tiff` auf demselben Host. Jede Kachel hat einen eigenen DOI.
- **Datei (eine Randkachel, Stichtag 2025) [M]:**
  - `LAYOUT=COG`, LZW mit Prädiktor 3, Blöcke 512², **Overviews 2 bis 256**;
  - 50 001² Pixel zu 1 m, EPSG:3035, Float32, Nodata −9999;
  - `HEAD` und Range-GET ohne Anmeldung: `Accept-Ranges: bytes`, Range ergibt `206`;
  - ETag und Last-Modified sind gesetzt; bedingte Anfragen mit `If-None-Match` und `If-Modified-Since` ergeben `304`;
  - `Cache-Control: no-cache,must-revalidate`, Server Apache.
  - Mit einem `Origin`-Header kommt **kein** `Access-Control-Allow-Origin` zurück (wie bei WorldCover).
- **Orthofoto DOP 20 cm [S]:** 57 Kacheln, Zyklus 3 Jahre, gleiche Wege und Formate laut Suchtreffern; nicht gemessen.
- **Lizenz [P]:** Der Metadatensatz der Serie sagt „Für dieses Produkt gilt die Standardlizenz CC-BY-4.0“ mit Link auf die Lizenz.
- **Unklar:**
  - Ein WMS-Metadatensatz nennt „Anmeldung erforderlich“ [S]; das betrifft den Darstellungsdienst, nicht den Download.
  - Gemessen ist nur eine Kachel. Dass alle 55 gleich aufgebaut sind, ist eine Annahme [A]; das Onboarding prüft es über die Kopfzeilen aller Kacheln.
  - Wer den Speicher betreibt und wo er steht, ist nicht belegt (F7: `unknown`).
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
  - Nachgesehen am 06.11.2026 [M]: Das Skript des Portals auf `opengeodata.lgln.niedersachsen.de` hat einen Bereich STAC mit Baustellen-Symbol und Link auf die STAC-Spezifikation, aber ohne Adresse einer API. Sonst verweist es nur auf statische STAC-Beispiele auf Hosts außerhalb der Freigabe aus §9.3. Eine STAC-API ist dort **nicht belegt**.
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
- **Nachmessung 06.11.2026 [M]:** je eine Kachel beider Stände an derselben Stelle in den Alpen.
  - Beide Stände: anonymes Listing, `x-amz-bucket-region: eu-central-1`, Range `206`, ETag und Last-Modified, bedingte Anfrage `304`.
  - Beide Dateien sind gleich aufgebaut: `LAYOUT=COG`, DEFLATE, Blöcke 1024², Overviews 2 bis 64, 36 000² Pixel, EPSG:4326, `uint8`, Nodata 0.
  - Weiterhin kein `Access-Control-Allow-Origin` auf einen `Origin`-Header.

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
| A | COG | ja | ESA WorldCover [M], Copernicus DEM (im Code), swissALTI3D [M], BEV DGM [M], BEV DOP [S], LGLN DOP/DGM [S], Thünen [P\*], JAXA Earth API [S] |
| B | Zarr | ja | EOPF (Samples, `adr/0017`), Source Cooperative FTW (Zarr v3 ohne Multiscales) [S] |
| C | GeoTIFF ohne Overviews, JPEG2000, ASCII-Grid | nein, bzw. nur langsam | die meisten Länder, DWD `grids_germany` |
| D | NetCDF, HDF5, GRIB2 | nein | DWD, MeteoSchweiz, GeoSphere-Dateien |

Folgerungen [A]:

1. Die erste Runde von Hand kann nur aus Gruppe A und B kommen, ohne neuen Reader.
2. Meteorologie, die Otto ausdrücklich will (Plan §2 Punkt 2), liegt in DACH vollständig in Gruppe D. Sie braucht eine eigene Entscheidung zum Leseweg. Drei Wege stehen zur Wahl:
   - **(a)** NetCDF/HDF5 über einen virtuellen Zarr-Speicher lesen (Kerchunk/VirtualiZarr, `architekturplan.md` 6.2 „später virtuelle Stores“). Das Original bleibt bei der Quelle; das passt zu Prinzip 1.
   - **(b)** Den Schritt in GDAL über `/vsicurl/` mit dem NetCDF- bzw. HDF5-Treiber machen. Das ist einfach, aber oft langsam, weil NetCDF-4/HDF5 viele kleine Lesezugriffe braucht.
   - **(c)** Ein flüchtiger Cache als COG mit Ablaufdatum (Prinzip 1 erlaubt abgeleitete Produkte nur flüchtig).
   
   Das ist rechenrelevant und gehört in eine eigene Recherche bzw. einen Spike (Frage F3; nach Ottos Antwort eine eigene Aufgabe der Stufe C, §11).
3. GRIB2 auf dem Ikosaedergitter (ICON) braucht ein Umrechnen auf ein reguläres Gitter. Das ist Processing, kein Lesen. Bis auf Weiteres scheidet es aus.

### 7.2 Lizenzen und Vorschlag zur B11-Einstufung

Alle Einträge sind **Vorschlag**; die Einstufung entscheidet Otto (`CLAUDE.md`). Gegen die SPDX-Liste vom 28.10.2026 geprüft [P]: `CC-BY-4.0`, `DL-DE-BY-2.0`, `DL-DE-ZERO-2.0` und `CC-BY-3.0-AT` gibt es. Für die swisstopo-OGD gibt es keine Kennung.

| Lizenz | Quellen | Flags (Vorschlag) | Stufe (Vorschlag) |
|---|---|---|---|
| `CC-BY-4.0` | MeteoSchweiz [P], GeoSphere [P], ESA WorldCover [M], BEV [P], DWD [S], die meisten AT-Länder [S], Thünen [P\*] | `commercial_use`, `distribution`, `derivatives` = true; `share_alike` = false; `attribution_required` = true | Processing |
| `DL-DE-BY-2.0` | BKG, die meisten DE-Länder, LGLN-DOP [S] | wie CC BY 4.0; der Quellenvermerk verlangt den Hinweis „Daten verändert“ bei Bearbeitung (BKG-Muster [S]) | Processing |
| `DL-DE-ZERO-2.0` | NRW, Hessen [S] | alles true, `attribution_required` = false | Processing |
| swisstopo-OGD (keine SPDX-Kennung) | swisstopo [P] | wie CC BY 4.0; `spdx_id = None`, Bedingungen als URL | Processing |
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
| FSDI (swisstopo, MeteoSchweiz außer ICON) | `aws:eu-central-1` | Code-Vorgabe [P]; S3 hinter CloudFront gemessen [M], Region des Buckets offen |
| MeteoSchweiz ICON | `cscs:lugano` | „CSCS public cloud object storage“ [P]; Standort Lugano [A] |
| LGLN | `ibm:eu-de` | Host des Kachelindex [P] |
| BEV | `unknown` (F7) | eigener Host, Server Apache [M]; Betreiber des Speichers und Ort nicht belegt |
| GeoSphere, DWD, Länder | `unknown` (F7); vermutlich eigene Rechenzentren in AT bzw. DE | — |
| ESA WorldCover | `aws:eu-central-1` | Registry [P], Host und `x-amz-bucket-region` [M] |
| EOPF, EODC | `eodc:vienna` | `adr/0022` |
| JAXA Earth API | unbekannt | — |

Für eigene Rechenzentren gilt die Form `<betreiber>:<ort>`, etwa `dwd:offenbach` (F7, fest). **Betreiber ist der Betreiber des Speichers, nicht die Behörde** (Otto, 06.11.2026): Liegen die Daten einer Behörde bei einem Cloud-Anbieter, steht dieser vorn. Solange Betreiber oder Ort nicht belegt sind, steht `unknown`. Ein Startcheck gegen `asset_hosts` geht für diese Form nicht; er bleibt AWS-Hosts vorbehalten (`adr/0022` §7.2).

### 7.4 Kataloge für die Discovery (Eingabe für `adr/0025`)

| Katalog | Protokoll | ohne Schlüssel | Lizenz maschinenlesbar | Beleg |
|---|---|---|---|---|
| FSDI STAC (CH) | STAC API v1 | ja [M] | `license` meist `proprietary` (swissALTI3D [M]); Link auf Bedingungen | P/M |
| GeoSphere `/v1/datasets` | eigene REST-API mit Metadaten | ja | eine Lizenz für alles | P |
| opendata.swiss | CKAN v3, DCAT-AP CH | vermutlich | `terms_*` je Datensatz | S |
| data.gv.at | CKAN, DCAT-AP | nicht belegt | je Datensatz | S |
| GovData | CKAN v3, DCAT-AP.de | ja (Leitfaden) | Lizenz-URIs aus DCAT-AP.de | S |
| LGLN STAC | STAC API | vermutlich | offen | S; Adresse am 06.11.2026 nicht belegt [M] |
| STAC Index | eigene API | nicht prüfbar (gesperrt) | — | — |
| BEV GeoNetwork | CSW, INSPIRE-ATOM, Suche über die GeoNetwork-API | ja [M] | Lizenz als Text mit Link im Metadatensatz | M |
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

Bewertet sind nur Kandidaten, die K1 bis K3 nach heutigem Stand erfüllen. ✓ = erfüllt, ~ = teilweise oder nur [S], ✗ = nicht erfüllt. Die Zeilen von WorldCover, swissALTI3D, BEV ALS-DGM und LGLN sind am 06.11.2026 nachgezogen (Messung unter „Methode und Belegstufen“).

| Kandidat | K1 anonym | K2 Lizenz | K4 Format | K5 Schnittstelle | K6 Region | K7 Betrieb | K8 Nutzen DACH | K9 Aufwand | Belege |
|---|---|---|---|---|---|---|---|---|---|
| **ESA WorldCover 10 m** | ✓ [M] | ✓ CC BY 4.0 [M] | ✓ COG, Overviews bis 64 [M] | ~ Bucket mit Kachelraster, kein STAC [M] | ✓ `eu-central-1` [M] | ✓ ETag, `304` [M] | mittel: Landbedeckung, neu | klein: Weg des DEM | M |
| **swisstopo swissALTI3D** | ✓ [M] | ✓ OGD [P] | ✓ COG, Overviews bis 8 [M] | ✓ STAC API [M] | ~ AWS hinter CloudFront [M], `eu-central-1` nur Code-Vorgabe [P] | ✓ ETag, `304` [M] | hoch: DTM 0,5 m CH + FL | mittel: STAC-Adapter für eine zweite STAC-Quelle, LV95, mehrere Stände je Kachel [M] | M/P |
| swisstopo SWISSIMAGE 10 cm | ✓ [S] | ✓ OGD [S] | ~ COG offen | ✓ STAC API | ✓ wie oben | ✓ | hoch: Orthofoto | klein nach swissALTI3D (gleicher Adapter) | S |
| **BEV ALS-DGM 1 m** (DOP 20 cm nicht gemessen) | ✓ [M] | ✓ CC BY 4.0 [P] | ✓ COG, Overviews bis 256 [M] | ~ ATOM [M] | unbekannt (AT), `unknown` | ✓ ETag, `304` [M] | hoch: DTM für AT | mittel: neue Nicht-STAC-Quelle, EPSG:3035, 50-km-Kacheln, sechs Stichtage [M] | M/P |
| LGLN DOP20/DGM1 (Niedersachsen) | ✓ [S] | ✓ dl-de/by-2-0 [P] | ✓ COG [S] | ~ STAC-API nicht belegt [M] | ✓ `ibm:eu-de` [P] | unbekannt | mittel: ein Land | klein nach swissALTI3D, falls es eine STAC-API gibt | P/S |
| MeteoSchweiz Klimagitter 1 km | ✓ [P] | ✓ CC BY 4.0 [P] | ✗ NetCDF | ✓ STAC API (dieselbe wie swisstopo) | ✓ wie swisstopo | ✓ ETag [P] | hoch: Meteorologie | groß: Reader für Gruppe D | P |
| GeoSphere SPARTACUS/WINFORE | ✓ [P] | ✓ CC BY 4.0 [P] | ✗ Abfrage-API / NetCDF | ~ eigene API, 240/h | unbekannt (AT) | ~ Limit [P] | hoch: Meteorologie AT | groß | P |
| DWD HYRAS/HOSTRADA | ✓ [S] | ✓ CC BY 4.0 [S] | ✗ NetCDF | ~ Dateiserver | unbekannt (DE) | unbekannt | hoch: Meteorologie DE | groß | S |
| JAXA Earth API | ~ [S] | ~ je Collection [S] | ✓ COG [S] | ✓ STAC [S] | ✗ vermutlich Japan | unbekannt | mittel | mittel | S |

### 8.2 Entscheidung: drei Quellen von Hand

**Gewählt (F1, Otto, 06.11.2026):** Option 1 mit Ottos Bedingung. Die Bedingung für BEV ist am 06.11.2026 erfüllt (§4.2) [M]. Damit gelten drei Quellen: WorldCover, swissALTI3D, BEV ALS-DGM 1 m. LGLN rückt nicht nach.

**Option 1 (Empfehlung, gewählt):** ESA WorldCover, dann swissALTI3D, dann BEV ALS-DGM 1 m.

- **Warum diese drei [A]:**
  - Alle drei liegen in Gruppe A (§7.1). Es braucht keinen neuen Reader.
  - Sie stressen die beiden Achsen aus Prinzip 3 und 4 dort, wo der Code heute dünn ist:
    - WorldCover ist eine Bucket-Quelle mit Kachelraster wie der DEM, aber eine Klassifikation. Damit wird `adr/0009` erstmals wiederverwendet statt neu gebaut.
    - swissALTI3D ist die zweite STAC-API nach Earth Search. Daraus wird der Earth-Search-Adapter zu einem allgemeinen STAC-Adapter. Den brauchen danach SWISSIMAGE, MeteoSchweiz und LGLN.
    - BEV ist eine Nicht-STAC-Quelle mit ATOM-Feed. Das ist ein Muster, das viele Behörden in DACH nutzen (INSPIRE-Downloaddienste).
  - Die Projektionen LV95 und LAEA (EPSG:3035) testen die Reprojektion außerhalb von UTM und WGS84.
  - Zusammen mit dem Copernicus DEM ergeben sie Geländedaten in drei Stufen für die Alpen: 30 m weltweit, 1 m für AT, 0,5 m für CH und FL.
- **Reihenfolge:** WorldCover zuerst. Es ist als einziger Kandidat schon gemessen, und der Weg ist bekannt. BEV zuletzt, weil COG und Zugang dort erst zu bestätigen sind (§9).
- **Bedingung:** Die Prüfung in §9 bestätigt anonymen Zugriff, COG mit Overviews und Range-Requests. Fällt BEV durch, rückt LGLN nach (Option 3), falls die STAC-Adresse belegt ist; sonst bleibt es vorerst bei zwei Quellen (Ottos Antwort zu F1).
  - Ergebnis 06.11.2026 [M]: ATOM ohne Anmeldung, `LAYOUT=COG` mit Overviews 2 bis 256, Range `206`. **Erfüllt.**

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

**ESA WorldCover (`esa-worldcover-2020`, `esa-worldcover-2021`):**

- **Zwei Datensätze, je Stand einer (F6 Option 2, Begründung in §10).** Sie teilen Adapter, Kachelraster und alle Eigenheiten; sie unterscheiden sich nur im Präfix des Buckets und in der Version (v100, v200).
- **Processing:**
  - `data_class` = statisches Raster, `time_range` = false, wie beim DEM.
  - `masking` = true mit `earthx:mask`: Asset `map`, Band 1, die elf Klassen; `cloud_classes` leer.
  - `value_masking` = true.
  - `band_math` = false (Rechnen mit Klassencodes ergibt keinen Sinn).
  - `reprojection` = true, aber `interpolation` = **false**: Klassen nur mit `nearest`. Das setzt `adr/0014` F6 schon so um.
  - `normalization` = false.
  - Eigener Operator: keiner.
- **Erweiterte Suche:** `search_filters` leer. Filter gibt es nach `adr/0021` §2 Punkt 1 vorerst nur für föderierte Datensätze. Der Stand wird über den Datensatz gewählt.
- **Schnellrechnungen:** `index_presets` leer.
- **Darstellung:** `default_render` mit der Farbtabelle aus der Datei (die Klassenfarben von ESA).
- **Hinweis in beiden Beschreibungen:** 2020 und 2021 sind nicht direkt vergleichbar.
- **Coverage:** aus dem Kachelraster (`LOCAL_SQL`), Einmal-Befehl wie beim DEM.

**swisstopo swissALTI3D (`swissalti3d`):**

- **Processing:**
  - `data_class` = statisches Raster. `time_range` = false, wie beim DEM; das Befliegungsjahr je Kachel ist eine Eigenschaft, keine Zeitachse.
  - **Offen nach der Messung [M]:** Die Collection hält mehrere Stände derselben Kachel als eigene Items (an einem Ort 2019 und 2025). Mit der Gruppierung des DEM (ein Schlüssel für alle Items) mischte ein Mosaik alte und neue Stände derselben Kachel; es gewänne das erste gültige Pixel (`registry.group_key`, `api/mosaic_tiles.py`) [P]. Mit dem Jahr im Schlüssel zerfiele eine AOI über Kacheln verschiedener Befliegungsjahre in mehrere Überflüge [A]. Wie die Registry das abbildet (etwa nur der jüngste Stand je Kachel), entscheidet das Onboarding mit einer Frage an Otto.
  - `band_math`, `reprojection`, `interpolation` und `normalization` = true. `masking` = false.
  - `value_masking`: nach Wunsch Ottos, bei Höhen meist sinnlos.
  - Eigener Operator: Hangneigung, Exposition und Schummerung. Das ist ein **neuer generischer Geländeoperator**, gebunden an eine **neue Capability** (Vorschlag `terrain`), die nur Höhenmodelle setzen (B10, F5). Dasselbe gilt dann für BEV und den Copernicus DEM.
- **Erweiterte Suche:**
  - Auflösung 0,5 m oder 2 m. Das ist eine Wahl des Assets, kein Filter. Die Registry braucht dafür eine Angabe, welches Asset die Plattform liest; heute gibt es dafür `default_render.assets`. Ob das reicht, klärt das Onboarding.
  - Befliegungsjahr: Die Suche der FSDI kennt `bbox`, `intersects`, `datetime`, `ids`, `collections`, Sortierung und die `forecast:*`-Felder, aber weder die Query-Extension noch CQL2 (`service-stac`, `app/stac_api/managers.py`, Konformitätsklassen in den Migrationen) [P]. Ein Filter nach `adr/0021` geht also nicht an die Quelle.
    - Das Jahr lässt sich nur über `datetime` wählen. Das Item-Datum ist der 1. Januar des Jahres, das auch im Namen der Assets steht [M]; dass dies das Befliegungsjahr ist, ist naheliegend, aber nicht am Primärtext belegt [A].
    - `search_filters` bleibt deshalb vorerst leer.
- **Schnellrechnungen:** `index_presets` leer. Gelände kommt über den Operator.
- **Darstellung:** Graustufen oder `terrain`-Colormap mit festem Bereich.
- **`band_units`:** `m` (LN02).
- **Attribution:** „©swisstopo“ oder der Name des Amtes; beides lassen die Nutzungsbedingungen zu [P]. Die Seite zur Quellenangabe war am 06.11.2026 nicht erreichbar (`500`). Den Wortlaut prüft Otto vor dem Eintrag (F2).
- **Coverage:** Die FSDI kennt keine Aggregation (nicht belegt). Deshalb `LOCAL_SQL` aus materialisierten Items, rund 45 000 Kacheln zu 1 km² [A]. Ob die Items trotzdem föderiert gesucht werden, entscheidet die Umsetzung (`architekturplan.md` 5.2).

**BEV ALS-DGM 1 m (`bev-als-dgm`):**

- **Processing, Suche und Schnellrechnungen:** wie swissALTI3D. Projektion EPSG:3035.
- **Unterschied:** 55 Kacheln zu 50 km statt rund 45 000 zu 1 km. Die Items kommen aus dem ATOM-Feed. Die Coverage ist eine Fläche (`complete`).
- **Stände [M]:** Der Feed listet sechs Stichtage (2019, 2021 bis 2025), je Stichtag alle 55 Kacheln. Anders als bei swissALTI3D ist jeder Stichtag ein vollständiger Stand für ganz Österreich. Ob nur der jüngste Stichtag kommt oder alle, ist **offen** und geht mit derselben Frage wie bei swissALTI3D ans Onboarding. Kommen mehrere, gilt dieselbe Überlegung wie bei WorldCover (F6): je Stichtag ein Datensatz oder ein Schlüssel, der die Stichtage trennt.
- **Prüfpunkt Overviews: erledigt [M].** Die gemessene Kachel hat Overviews 2 bis 256. Die Karte kann den Datensatz also auch bei kleinem Maßstab zeigen; `viewer.min_zoom` (M2-10) legt das Onboarding nach einer Messung der Kachelzeit fest.
- **Kein CORS [M]:** wie WorldCover; ein Quicklook im Browser direkt von der Quelle geht nicht, die Kacheln kommen über den `tiler`.

**Neu in der Registry, für alle drei:**

- `data_region` (`adr/0022` F3, beschlossen; Werte §7.3).
- Die Capability `terrain` (F5 = 1, fest) für swissALTI3D, BEV und den Copernicus DEM, nicht für WorldCover.

---

## 9. Offene Prüfungen und Prüfanleitung

### 9.1 Was vor dem Onboarding zu prüfen ist

Stand nach der Messung vom 06.11.2026 (Weg B). „offen“ heißt: weder gemessen noch am Primärtext gelesen.

| Quelle | Prüfpunkt | Stand 06.11.2026 |
|---|---|---|
| ESA WorldCover | anonym; COG; Range; ETag; CORS; Region; beide Stände | alles [M]: anonym, COG mit Overviews, `206`, ETag und `304`, **kein CORS**, `eu-central-1`, v100 und v200 gleich aufgebaut |
| swissALTI3D | anonym; `license` der Collection; Medientyp der Assets (COG?); Region (`x-amz-bucket-region` bzw. Host); Range `206`; ETag; CORS der Assets; Bedeutung von `datetime` am Item | [M]: anonym, `license: proprietary`, COG (Medientyp und Kopf), `206`, ETag und `304`, CORS `*` an den Assets; `datetime` = Jahr im Namen des Assets; mehrere Stände je Kachel. **Offen:** Region des Buckets (CloudFront verdeckt sie), Befliegungsjahr am Primärtext |
| SWISSIMAGE | wie swissALTI3D | offen (nicht Teil von F1) |
| MeteoSchweiz Klimagitter | wie oben; Größe und Aufbau einer NetCDF-Datei (für F3) | offen; gehört zur Recherche F3 (§11) |
| BEV ALS-DGM | ATOM-Feed ohne Anmeldung; COG mit Overviews; Range; ETag; Lage der Server | [M]: ATOM anonym, COG mit Overviews 2 bis 256, `206`, ETag und `304`, kein CORS; Lizenz [P]. **Offen:** Betreiber und Ort des Speichers; Aufbau der übrigen 54 Kacheln |
| BEV DOP | wie ALS-DGM | offen (nicht Teil von F1) |
| LGLN | Adresse der STAC-API; Lizenz DGM1/DOM1 | STAC-API auf dem freigegebenen Host nicht belegt [M]; Lizenz DGM1/DOM1 offen. Nicht mehr nötig, weil BEV die Bedingung erfüllt |
| GeoSphere | Kopfzeilen `x-ratelimit-*`; Dateidownload im Data Hub ohne Konto | offen; Ottos Lauf von `probe.py` (F4) bzw. Recherche F3 |
| DWD | Range und ETag auf dem Dateiserver | offen; wie GeoSphere |
| JAXA Earth API, EODC STAC | Schlüssel nötig? Lizenz je Collection; Region | offen |
| swisstopo, BEV, DWD, BKG | Wortlaut der Nutzungsbedingungen und des Quellenvermerks (für Otto) | swisstopo-Bedingungen und BEV-Metadaten gelesen [P]; den Wortlaut für den Registry-Eintrag prüft Otto (F2) |

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

**Stand (F4):** Otto lässt `probe.py` lokal laufen. Das Ergebnis kommt später als Nachtrag in dieses ADR; bis dahin sind die Punkte aus §9.1, die nur das Skript prüft, **offen**.

BEV, JAXA und EODC stehen nicht im Skript, weil ihre Adressen nur aus Suchtreffern bekannt sind. Sie werden in Weg B oder beim Onboarding geprüft.

### 9.3 Weg B: neue Sitzung mit freigegebenen Hosts

Otto gibt diese Hosts in der Umgebung frei (F4, 06.11.2026). Eine Sitzung misst dann mit `curl` wie in `adr/0009` und liest die Doku als P statt S:

- **Schweiz:** `data.geo.admin.ch`, `www.swisstopo.admin.ch`, `www.geo.admin.ch`, `opendatadocs.meteoswiss.ch`, `ckan.opendata.swiss`
- **Österreich:** `dataset.api.hub.geosphere.at`, `data.hub.geosphere.at`, `data.bev.gv.at`, `www.bev.gv.at`, `stac.eodc.eu`
- **Deutschland:** `opendata.dwd.de`, `gdz.bkg.bund.de`, `sg.geodatenzentrum.de`, `opengeodata.lgln.niedersachsen.de`, `www.govdata.de`
- **Satellit und Kataloge:** `data.earth.jaxa.jp`, `stacindex.org`

`esa-worldcover.s3.eu-central-1.amazonaws.com` ist schon erreichbar [M].

**Ausgeführt am 06.11.2026 (M5-01b):** für WorldCover, swissALTI3D, BEV und LGLN; Ergebnis in §9.1. Die Hosts standen zu Beginn der Sitzung nicht in der Allowlist der Umgebung und wurden mit Ottos Freigabe eingetragen; sie wirkten danach ohne Neustart. Nur die Hosts dieser Liste wurden eingetragen.

---

## 10. Fragen an Otto und Antworten

Otto hat am 06.11.2026 alle sieben Fragen beantwortet, jeweils mit Option 1 und Zusätzen. Die Antworten stehen unter der jeweiligen Frage. Was danach offen bleibt, ist als **offen** markiert.

**F1 — Welche Quellen bindet M5 zuerst von Hand an (§8.2)?**
1. ESA WorldCover, swissALTI3D, BEV ALS-DGM 1 m, in dieser Reihenfolge, je nach Prüfung in §9 **(Empfehlung)**
2. ESA WorldCover, swissALTI3D, MeteoSchweiz-Klimagitter (mit Leseweg NetCDF vorab, F3)
3. ESA WorldCover, swissALTI3D, LGLN DOP20/DGM1
4. Zuerst nur WorldCover und swissALTI3D, die dritte nach §9

**Antwort F1 (Otto, 06.11.2026): 1, fest.** WorldCover, dann swissALTI3D. BEV ALS-DGM 1 m als dritte Quelle nur, wenn die Messung anonymen ATOM-Zugang, COG mit Overviews und Range-Requests bestätigt. Sonst LGLN, falls die STAC-Adresse belegt ist, sonst vorerst nur zwei Quellen.
- **Ergebnis:** Die Messung vom 06.11.2026 bestätigt alle drei Punkte für BEV [M] (§4.2). Damit sind es **drei Quellen: WorldCover, swissALTI3D, BEV ALS-DGM 1 m.**
- Die STAC-Adresse des LGLN ist nicht belegt (§5.3); das spielt nach dem Ergebnis keine Rolle mehr.

**F2 — Lizenz-Einstufung der gewählten Quellen (§7.2)?**
1. Die Vorschläge aus §7.2 für die Quellen aus F1 annehmen. Die Wortlaute der Bedingungen prüfst du vor dem Eintrag selbst **(Empfehlung)**
2. Jede Quelle einzeln beim Onboarding vorlegen
3. swisstopo-OGD erst nach Rechtsberatung; bis dahin nur Katalogeintrag

**Antwort F2 (Otto, 06.11.2026): 1, fest.** Die Vorschläge aus §7.2 gelten für die Quellen aus F1. Otto prüft die Wortlaute von ESA WorldCover, swisstopo (Bedingungen und Quellenangabe) und BEV vor dem jeweiligen Registry-Eintrag.
- **Offen** bis zu Ottos Prüfung: der Wortlaut je Quelle. Gelesen sind bisher die swisstopo-Bedingungen und der BEV-Metadatensatz [P] sowie der Kopf der WorldCover-Dateien [M]. Die Seite zur Quellenangabe von swisstopo war am 06.11.2026 nicht erreichbar.

**F3 — Leseweg für NetCDF/HDF5 (Meteorologie, §7.1)?**
1. Eigene Recherche mit Messung (Stufe C) zu virtuellem Zarr, GDAL-Treiber über `/vsicurl/` und flüchtigem COG-Cache, an MeteoSchweiz-Klimagittern und DWD HYRAS; danach erste Meteorologie-Quelle **(Empfehlung)**
2. Meteorologie vorerst nur als Katalogeintrag mit Link (B11 Stufe 1), ohne Anzeige
3. Meteorologie nach M5

**Antwort F3 (Otto, 06.11.2026): 1, fest.** Recherche mit Messung als eigene Aufgabe der Stufe C, parallel zum Onboarding (§11).

**F4 — Wie werden die offenen Punkte aus §9 geprüft?**
1. Du führst `probe.py` aus (Weg A) und gibst die Hosts aus §9.3 für die Onboarding-Sitzungen frei **(Empfehlung)**
2. Nur Weg A
3. Nur Weg B

**Antwort F4 (Otto, 06.11.2026): 1, fest.** Die Hosts aus §9.3 sind freigegeben. Weg B führt die Sitzung selbst aus; `probe.py` lässt Otto lokal laufen, das Ergebnis kommt später als Nachtrag.
- **Weg B:** ausgeführt am 06.11.2026 (§9.3, §9.1).
- **Weg A:** **offen** bis zu Ottos Nachtrag.

**F5 — Geländeoperator (Hangneigung, Exposition, Schummerung)?**
1. Eigene Aufgabe nach dem ersten hochaufgelösten DGM: ein generischer Operator, gebunden an eine neue Capability `terrain`, die nur Höhenmodelle setzen (B10) **(Empfehlung)**
2. Nicht in M5
3. Nur als Darstellung im `tiler` (Algorithmus), kein Operator

**Antwort F5 (Otto, 06.11.2026): 1, fest.** Ein generischer Geländeoperator, gebunden an die neue Capability `terrain`. Der Plan dieser Aufgabe muss ausdrücklich zwei Punkte behandeln:
- die Nachbarpixel am Blockrand beim blockweisen Lesen (`adr/0014` F10): Hangneigung, Exposition und Schummerung brauchen ein Fenster von 3 × 3 Pixeln, eine Blockschleife also einen Rand von einem Pixel je Block;
- die Schummerung zur Anzeige als Algorithmus im `tiler` als Ergänzung. Heute weist der `tiler` TiTilers freie Parameter `algorithm` und `algorithm_params` ab (`api/tiler.py`, Plan M4-09 F3); eine Schummerung zur Anzeige müsste also ein eigener, benannter Weg sein.

**F6 — WorldCover 2020 und 2021: ein Datensatz oder zwei?**
1. Ein Datensatz mit Zeitachse (`time_range` = true, zwei Stände), Hinweis auf eingeschränkte Vergleichbarkeit in der Beschreibung **(Empfehlung)**
2. Zwei Datensätze (`esa-worldcover-2020`, `-2021`), je statisch
3. Nur 2021 (v200)

**Antwort F6 (Otto, 06.11.2026):** Option 1, wenn eine Ansicht nie Kacheln beider Jahre mischt; mischt sie, gilt Option 2. **Ergebnis der Prüfung im Code: Option 2 gilt, zwei Datensätze** (`esa-worldcover-2020`, `esa-worldcover-2021`).

Begründung (gelesen im Code von `main`, Stand DS-03c) [P]:
- Ein einzelnes Mosaik mischt nie zwei Überflüge. Der Schlüssel ist `results_group_by` (`registry.overpass_key`, `group_by_overpass`). Kachel, TileJSON (`api/tiler.py`, `check_one_overpass`), Mosaik-Kachel (`api/mosaic_tiles.py`) und Mosaik-Job (`api/intake.py`) lehnen verschiedene Schlüssel mit `422` ab.
- **Die Ansicht aber zeigt mehr als einen Überflug:**
  - `itemsForMap` (`frontend/src/grouping.ts`) gibt die aufgeklappte Gruppe **plus alle ausgewählten Items anderer Gruppen** zurück (V-3: ein ausgewählter Quicklook bleibt beim Wechsel der Gruppe stehen).
  - `mapLayers.ts` zeichnet alle heruntergeladenen Überflüge zugleich, jeden als eigenes Mosaik übereinander (`passesOf`).
- Die Kacheln von 2020 und 2021 haben denselben Umriss. Wird eine Kachel von 2020 ausgewählt und danach zur Gruppe 2021 gewechselt, oder werden beide heruntergeladen, zeigt eine Ansicht beide Jahre am selben Ort übereinander. Das ist ein Mischen im Sinne der Bedingung.
- Mit dem Schlüssel des DEM (`start_datetime`, gleich für alle Items) wäre es noch schlimmer: Dann wären beide Jahre ein Überflug, und schon ein einzelnes Mosaik mischte sie stillschweigend nach dem ersten gültigen Pixel [A, aus `group_key`].
- Mit zwei Datensätzen ist jede Ansicht eines Datensatzes auf ein Jahr festgelegt; der Hinweis auf die eingeschränkte Vergleichbarkeit steht in beiden Beschreibungen (§8.3).

**F7 — `data_region` für Quellen ohne Cloud-Region (§7.3)?**
1. Form `<betreiber>:<ort>` wie `dwd:offenbach`, ohne Startcheck; `unknown`, solange der Ort nicht belegt ist **(Empfehlung)**
2. Nur Länderkennung (`de`, `at`, `ch`)
3. Feld leer lassen, bis gemessen

**Antwort F7 (Otto, 06.11.2026): 1, fest.** Form `<betreiber>:<ort>` ohne Startcheck, `unknown`, solange der Ort nicht belegt ist. **Betreiber heißt der Betreiber des Speichers, nicht die Behörde.** Umgesetzt in §7.3; BEV steht danach auf `unknown`.

---

## 11. Folgen

Eingabe für Fassung 2 des M5-Plans. Diese Liste legt keine Plan-Dateien an und ändert weder Backlog noch M5-Plan; Zuschnitt, Nummern und Stufen der Aufgaben legt die Fassung 2 fest.

1. **Onboarding ESA WorldCover** als zwei Datensätze (`esa-worldcover-2020`, `-2021`, F6).
   - Weg des DEM: Items aus dem Kachelraster im Bucket, Einmal-Befehl in `discovery`, Coverage `LOCAL_SQL` (`adr/0009`).
   - Eigenheiten nach §8.3; `data_region` = `aws:eu-central-1`.
   - Vor dem Registry-Eintrag: Otto prüft den Wortlaut der Lizenz (F2).
2. **Allgemeiner STAC-Adapter mit swissALTI3D.**
   - Aus dem Earth-Search-Adapter wird ein Adapter für beliebige STAC-APIs; swissALTI3D ist nach Earth Search die erste Quelle darüber (FSDI, LV95).
   - Vorab zu klären (Frage an Otto im Plan der Aufgabe): mehrere Stände derselben Kachel (§8.3) und die Wahl des Assets 0,5 m bzw. 2 m.
   - Vor dem Registry-Eintrag: Otto prüft Bedingungen und Quellenangabe von swisstopo (F2).
3. **BEV ALS-DGM 1 m** als Quelle mit ATOM-Feed (EPSG:3035, 55 Kacheln).
   - Die Bedingung aus F1 ist erfüllt; ein Ersatz (LGLN) ist nicht nötig.
   - Vorab zu klären: welche Stichtage (§8.3); Aufbau aller Kacheln über ihre Kopfzeilen prüfen; `data_region` = `unknown`, bis Betreiber und Ort des Speichers belegt sind (F7).
   - Vor dem Registry-Eintrag: Otto prüft den Wortlaut der Lizenz (F2).
4. **Recherche zum Leseweg für NetCDF** (F3, Stufe C, parallel zum Onboarding).
   - Virtuelles Zarr, GDAL über `/vsicurl/` und flüchtiger COG-Cache, gemessen an MeteoSchweiz-Klimagittern und DWD HYRAS (§7.1).
   - Danach die erste Meteorologie-Quelle (§8.2).
5. **Geländeoperator mit Capability `terrain`** (F5).
   - Hangneigung, Exposition und Schummerung als ein generischer Operator, nur für Datensätze mit `terrain` (B10): swissALTI3D, BEV, Copernicus DEM.
   - Der Plan behandelt ausdrücklich die Nachbarpixel am Blockrand beim blockweisen Lesen (`adr/0014` F10) und prüft die Schummerung zur Anzeige als Algorithmus im `tiler` als Ergänzung.
   - Nach dem ersten hochaufgelösten DGM (Punkt 2 oder 3 dieser Liste).

Außerdem ohne eigene Aufgabe: Ottos Nachtrag aus `probe.py` (F4) wird in dieses ADR eingetragen, sobald er vorliegt.

---

## 12. Quellen

Abgerufen bzw. gesucht am 31.10.2026, die Messung von M5-01b am 06.11.2026. Die Belegstufe steht in Klammern.

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
- am 06.11.2026 (M5-01b), ohne Adressen und Item-IDs:
  - `esa-worldcover`: je eine Kachel von v100 und v200 (Listing, `HEAD`, Range-GET, bedingte Anfrage, Kopf über GDAL);
  - FSDI-STAC: Konformität, Collection `ch.swisstopo.swissalti3d`, ein Item, eine Suche mit `datetime`, eine Suche über eine kleine Fläche; je ein Asset 0,5 m und 2 m (`HEAD`, Range-GET, bedingte Anfrage, Kopf über GDAL);
  - BEV: GeoNetwork-Suche, ATOM-Dienst „ALS EL Höhendaten“, ein Dataset-Feed und dessen Datei (`HEAD`, Range-GET, bedingte Anfragen, Kopf über GDAL);
  - LGLN: Startseite und Skript des Portals.

**Am Primärdokument gelesen am 06.11.2026 (P):**

- swisstopo, Nutzungsbedingungen für kostenlose Geodaten und Geodienste (OGD), Version 1.3.2021, und die Seite „Conditions for Geodata“ auf `www.swisstopo.admin.ch`
- BEV, Metadatensatz der Serie ALS DTM Höhenraster 1 m (Lizenz, Zugang, Koordinatensystem) im GeoNetwork auf `data.bev.gv.at`

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
