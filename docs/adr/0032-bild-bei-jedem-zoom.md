# ADR 0032 — Bild bei jedem Zoom

- **Status:** **Angenommen** von Otto am 2026-11-11: F1–F14 jeweils Option 1 (Empfehlung), außer und mit diesen Ergänzungen (§14):
  - **F1 = 2:** Die Pyramide entsteht gleich nach der Materialisierung und nach einem Wechsel der Quelle, nicht erst bei der ersten Anfrage.
  - **F3 ergänzt:** Nach 30 Tagen prüft eine bedingte Anfrage die Fassung der Quelle (`ETag`/`updated`). Ist sie unverändert, wird die Frist verlängert, ohne neu zu lesen. Die Auslegung von Prinzip 1 dazu ist Ottos Entscheidung (§5.3).
  - **F4:** 0,25 s Mindestabstand je Host, einstellbar, mit Verweis auf die Fair-Use-Regeln der FSDI (`adr/0023` §3.1).
  - **F11 ergänzt:** Das Messskript läuft per `docker compose run`; auf Ottos Rechner gibt es kein Python.
  - **Teilkacheln bei Szenen:** keine sichtbare Marke, höchstens ein Tooltip (Leitfaden, kein Zusatztext).
- **Datum:** 2026-11-10 (Entwurf, Draft-PR [#326](https://github.com/oscipal/earthX/pull/326)); 2026-11-11 angenommen.
- **Aufgabe:** M5-30, Auftrag von Otto vom 10.11.2026. Die Nummer 0032 war beim Start frei: Auf `main` endet die Reihe mit 0031, die offenen PRs #319 und #322 legen kein ADR an.
- **Autonomiestufe:** C. Kein Produktivcode.
  - Geändert sind nur dieses ADR und eine Zeile im Entscheidungslog.
  - Unverändert bleiben `backend/`, `frontend/`, `scripts/`, Registry, Fixtures, Backlog, M5-Plan, `.importlinter`, `.github/`, `.claude/`, `CODEOWNERS` und `CLAUDE.md`.
- **Vorgabe (Otto, 10.11.2026):** Bei keinem Datensatz darf das Bild beim Herauszoomen verschwinden. Heute zeigt Sentinel-1 erst ab Zoom 7 ein Bild, swissALTI3D erst ab Zoom 14 (bis zu 12 Szenen je Mosaik-Kachel), darunter nur die Coverage. Die feste Grenze von 64 Items je Mosaik und die Grenzen beim Zusammenführen sollen weg.
- **Vorab fest:**
  - Ausgehende Requests nur über `gateway` (B8); der eigene Objektspeicher über `objectstore` (B8, Nachtrag 2026-10-05).
  - Worker-Kern ohne Plattformdienste (B9).
  - Keine Secrets, keine internen URLs, keine exakten AOIs.
  - `.github/` nur mit Ottos Erlaubnis.
- **Grundlage:**
  - `ENTSCHEIDUNGEN_2026-09-18.md` §2 (zweistufige Anzeige aus COG-Overviews, Stitching), §4; `KLAERUNGEN.md` B8, B9, B10, B11, B13.
  - `projektuebersicht.md` §2, Prinzipien 1, 8, 9, 10, 11, 16; `architekturplan.md` 3.1, 6.3, 7.3, 12.3.
  - `adr/0006` §3.4, §3.5, §5; `adr/0012` §9; `adr/0014` §5.5, §15i; `adr/0015` §7; `adr/0018` F1; `adr/0023` §3.1, §8.3, §9.3; `adr/0024` R6, R7, R10; `adr/0025` §6.2; `adr/0029` F1.
  - `plans/m4/m4-17-mosaik-kachel-pfad.md` §5; `plans/m5/m5-08-stac-adapter-swissalti3d.md` §13; `plans/ds/ds-04-s1-anbinden.md` §11, §14.6, §14.7a (im offenen PR #319).
- **Betroffen (erst mit einer Entscheidung):** `api` (Kachel- und Mosaik-Route, Grenzen), `access` (Lesen über Budget), `jobs` (neue Job-Art „Übersicht“), `objectstore` (Präfix `overviews/` mit Ablaufregel), Registry (`viewer`), Frontend (Mosaik-Weg, Hinweise), `architekturplan.md` 6.3 und 12.3.

---

## Methode und Belegstufen

Belegstufen wie in `adr/0025`, `adr/0030` und `adr/0031`:

- **M:** in dieser Sitzung gemessen; Verfahren im Text oder im Anhang.
- **P:** am Primärdokument selbst gelesen. Im Repo mit Pfad.
- **S:** Suchtreffer, Zusammenfassung oder Vorwissen, Wortlaut nicht geprüft.
- **A:** eigene Ableitung, ein Argument und kein Beleg.

**Gemessen am 10.11.2026 [M]** (Verfahren im Anhang): Kopf und gröbste Übersicht je einer echten Datei, direkt über `/vsicurl/` im Kratzverzeichnis der Sitzung wie in `adr/0018` §4.1, nicht über `gateway`. Insgesamt rund 40 Anfragen an drei Hosts; keine AOI, keine IDs in diesem Text außer der Kachelnummer einer öffentlichen Beispieldatei. Der Standort der Sitzung ist nicht Europa (unbelegt), die Zeiten sind deshalb eine obere Schranke.

| Datei | Größe | Raster | Blöcke | Übersichten | Öffnen + gröbste Übersicht, kalt |
|---|---|---|---|---|---|
| swissALTI3D, 0,5 m | 2,7 MB | 2000², Float32, EPSG:2056, LZW | 128² | 2, 4, 8 (bis 4 m) | 0,44 s |
| swissALTI3D, 2 m | 177 kB | 500², Float32, LZW | 128² | 2 (bis 4 m) | 0,12 s |
| Sentinel-1 GRD IW, VV | 717 MB | 26 608 × 16 690, UInt16, nur GCPs, DEFLATE | 1024² | 2 bis 64 | 0,79 s + 0,35 s |
| Copernicus DEM GLO-30, 1° | 41,8 MB | 3600², Float32, EPSG:4326, DEFLATE | 1024² | 2, 4, 8 | nicht gemessen |

**Zwölf Dateien von swissALTI3D (2 m)** um eine Stadt, je Öffnen und gröbste Übersicht lesen, ohne Zwischenspeicher [M]:

- nacheinander: 5,5 s, je Datei Median 0,32 s (0,28–0,82 s);
- mit 6 Threads (die Grenze je Host in `gateway`, `policy.py:124`): 0,87 s, also rund **0,07 s je Datei**.

Die Dateien antworten mit `Cache-Control: public, max-age=7200`, `ETag` und `Last-Modified` [M]; vor ihnen steht ein CDN (`adr/0023` §3.1).

---

## 0. Kurzfassung

1. **Warum das Bild verschwindet:** Die Kosten einer Kachel hängen an der Zahl der Dateien, die sie öffnet, nicht an ihrer Pixelzahl (`adr/0006` §3.4). Beim Herauszoomen wächst diese Zahl mit dem Quadrat: swissALTI3D (Kacheln von 1 km) hat bei z13 bis 25, bei z10 rund 770 und bei z8 rund 11 500 Dateien je Kachel (§4). Die heutigen Grenzen (12 Szenen je Kachel, Mosaik ab z8, `min_zoom`) schneiden das Bild deshalb ab.
2. **Zwei Fälle, zwei Wege.**
   - **Kachel-Datensätze aus vielen Dateien** (swissALTI3D, BEV, WorldCover, DEM): unter einer Basisstufe eine **Übersichtspyramide** als flüchtiges Zwischenprodukt im eigenen Objektspeicher. Ein Job baut sie gleich nach der Materialisierung und nach einem Wechsel der Fassung (F1 = 2). Die Fassung steht im Pfad. Nach 30 Tagen verlängert eine Prüfung der Fassung die Frist, wenn die Quelle unverändert ist (F3, §5.3).
   - **Szenen-Datensätze** (Sentinel-1, Sentinel-2): die gewählten Szenen über ihre eigenen Übersichten bei jedem Zoom. Statt „12 Szenen ab z8“ gilt ein **Budget je Kachel** (Dateien und Zeit). Über dem Budget kommt eine Teilkachel; erklärt wird sie höchstens im Tooltip des Layers (§6).
3. **Grobe Gitter und Einzeldateien** brauchen keine Pyramide, solange das ganze Feld in das Budget passt (§7).
4. **Kosten [A]:** Die Pyramide für swissALTI3D braucht rund 0,4–0,9 GB je Fassung und einen Bau mit 45 000–90 000 Anfragen an die Quelle. Mit dem Mindestabstand von 0,25 s je Host (F4) dauert das 3,1–6,3 h. Danach wird nur bei geänderter Fassung neu gelesen, und dann nur die geänderten Kacheln. WorldCover und DEM brauchen nur kleine globale Pyramiden. Für Sentinel-1 entsteht kein Speicher; bei kleinem Zoom liest eine Kachel mehr Szenen (§8).
5. **`min_zoom`** bleibt und heißt dann „ab hier aus den Originalen“. Darunter gilt ein neues Pflichtfeld `viewer.overview` (`own`, `pyramid`, `scenes`). Eine Registry-Prüfung verlangt für jeden angezeigten Datensatz ein Bild bei z0 (§9).
6. **Grenzen nach Kosten statt nach Anzahl (§10):**
   - Kachel: Budget je Kachel.
   - Zuschnitt und Job: die bestehende Schätzung nach `adr/0014` §5.5 (Dauer, Bytes, Speicher) entscheidet.
   - Die Item-Liste in der URL weicht einer **Auswahl-ID aus dem Hash ihres Inhalts**, die die URL weiterhin vollständig bestimmt. Damit entfallen die 64.
   - Der Rückfall „Szene für Szene“ mit höchstens 40 Ebenen bleibt nur für Gruppen, die kein Mosaik sein können.
   - Der Befund #319 F13 hängt nach meiner Vermutung an genau diesem Rückfall und an `min_zoom` 14. Er ist nicht belegt; ein Test vor der Behebung (F13).

---

## 1. Kontext und Frage

Die Plattform zeigt Raster als dynamische Kacheln aus COGs (`architekturplan.md` 6.3). Ein Bild entsteht je Kachel aus den Dateien, die sie berührt. Bei kleinem Zoom berührt eine Kachel viele Dateien, und jede Datei kostet mindestens ein Öffnen: Kopf lesen, dann einen Block der passenden Übersicht. Heute begrenzen fünf Stellen diese Zahl. Unter der Grenze zeigt die Karte nur die Coverage (`zoomHint.ts`, Tooltip „Nothing shown at this zoom“, #319 §14.3).

Otto verlangt ein Bild bei jedem Zoom und bei jedem Datensatz. Gefragt sind sechs Punkte (Auftrag 1–6): Pyramiden für Kachel-Datensätze, Szenen bei jedem Zoom, grobe Gitter, Kosten und Recht, `min_zoom`, Grenzen nach Kosten.

---

## 2. Befund am Code [P]

| Grenze | Wert | Stelle | Folge |
|---|---|---|---|
| Zoom-Freigabe je Datensatz | `viewer.min_zoom` | `api/tiler.py:218-267`, `400` „not released“ | Sentinel-1 ab z7, swissALTI3D ab z14; DEM, WorldCover, Sentinel-2 ab z0 |
| Mosaik-Kachel erst ab | `MIN_MOSAIC_ZOOM = 8` | `api/mosaic_tiles.py:74`, `400`; Spiegel `frontend/src/mosaic.ts:21` | darunter Einzelszenen |
| Szenen je Mosaik-Kachel | `MAX_SCENES_PER_TILE = 12` | `api/mosaic_tiles.py:72`, `422` „zoom in“ | Grund für `min_zoom` 14 bei swissALTI3D (`swissalti3d.yaml:169-171`) |
| Items je Mosaik-URL | `MAX_MOSAIC_ITEMS = 64` | `api/mosaic_tiles.py:70`, `400`; Spiegel `mosaic.ts:23` | darüber Einzelszenen mit Hinweis (`mosaic.ts:171-172`) |
| Einzeln gezeichnete Szenen | `MAX_MOSAIC_LAYERS = 40` | `frontend/src/mapLayers.ts:34`, `:1167` | über 40 bleibt ein Teil der AOI leer (#319 §14.6) |
| Szenen je Download (Zusammenführen) | `MAX_DOWNLOAD_ITEMS = 25` | `access/download.py:255`, `413` | |
| Items je Auftrag (Job) | `MAX_ORDER_ITEMS = 25` | `api/intake.py:165`, `413`; Spiegel `frontend/src/download.ts:51` | |
| Bytes, Seiten, Speicher | 500 MB je Download, 5 GB je Job, 4096 px je Seite, 1,5 GB Speicher je Job | `download.py:239`, `crop_rules.py:78, 123`, `processing/plan.py:124` | schon kostenbasiert |
| Laufzeit je Job | aus der Schätzung × Faktor | `jobs/submit.py:112` | schon kostenbasiert |

Weitere Befunde:

- **„Crop and merge to AOI“ in der Ansicht** ist der Mosaik-Weg der Karte, also die 64 und die 40. Das Zusammenführen im Download- bzw. Job-Weg ist die 25.
- **Zwischenspeicher für Kacheln:** Es gibt keinen. Kachelantworten tragen kein `Cache-Control` (`adr/0024` §3). Der Objektspeicher kennt nur `results/` mit 7 Tagen (`objectstore/results.py:28-31`); `jobs/cleanup.py` räumt stündlich auf.
- **Lesen:** Die Wahl der Übersicht macht rio-tiler. Der `tiler` liest 512er-Kacheln (`access/mosaic_tiles.py:198`), die Karte fragt Stufe L ab Kartenzoom L − 0,5 an (`tileSize.ts:25-35`).
- **Registry-Text zu `min_zoom`** (`catalog/registry.py:714-775`): „Below `min_zoom` one tile shows several scenes, which is the coverage map's job“. Für einzelne Items sagt derselbe Text schon, dass eine Kachel bei jedem Zoom gleich viel kostet. Beim DEM ist `min_zoom` deshalb „a cost floor on how many tiles a viewport can ask for at once“.
- **Meteorologie:** kein Eintrag in der Registry. NetCDF liest `adr/0029` über virtuelle Verweise, ausdrücklich ohne flüchtigen COG-Cache in M5 (F1, Option C „später“).

---

## 3. Stand der Technik

Gelesen am 10.11.2026. Viele Doku-Hosts waren aus der Sitzung gesperrt (gdal.org, Planetary Computer, Sentinel Hub, Earth Engine, AWS). Ein Recherche-Agent hat deshalb Code und Doku über `raw.githubusercontent.com` gelesen. Solche Stellen tragen **[P\*]**: Primärquelle, aber nicht von mir selbst geprüft. Quellen in §16.

**Grundsatz: Kein Stack löst das allein mit Mosaik-Logik.** Alle untersuchten Systeme tun eines von zwei Dingen:

- Sie sperren kleine Zooms (Planetary Computer).
- Oder sie lesen aus vorab gebauten Pyramiden (Earth Engine).

Das frühe Ende eines Mosaiks („Kachel voll“) hilft nur, wo Dateien sich überlappen. Bei überlappungsfreien Kacheln wie swissALTI3D trägt jede Datei etwas bei; das Ende kommt erst mit der letzten [A].

| System | Wie kleine Zooms gehen | Zahlen |
|---|---|---|
| **pgstac / titiler-pgstac** [P\*] | Suche je Kachel mit Grenzen; Abbruch, wenn die Footprints die Kachel decken (`exitwhenfull`) oder ein Item nichts Neues deckt (`skipcovered`) | Vorgaben: 100 Items, 10 000 gescannt, **5 s** je Kachel. Die Deckung wird an Footprints geprüft, nicht an gültigen Pixeln. Kacheln über der Grenze bleiben teilweise leer |
| **rio-tiler `mosaic_reader`** [P\*] | liest in Portionen von `threads`; `FirstMethod` endet, sobald keine Lücke bleibt | nur `FirstMethod` endet früh, Mittel und Median lesen alles. Threads `cpu_count() × 5` als Vorgabe |
| **cogeo-mosaic / MosaicJSON** [P\*] | Asset-Listen je Quadkey auf `quadkey_zoom`; unter dieser Stufe vereinigt es die Listen aller Kinder | bis 4^Δz Listen; `maximum_items_per_tile` ohne Vorgabe. Löst das Problem nicht |
| **Planetary Computer** [P\*, Konfiguration je Collection] | harte Grenze `minzoom`; keine vorab gerechneten Übersichten gefunden | `sentinel-1-grd` und `-rtc` ab **z8**, `sentinel-2` ab **z9**, `esa-worldcover` ab **z6** mit höchstens 20 Items je Kachel. Pro-Doku: `minZoom` soll verhindern, dass bei kleinem Zoom viele Dateien gelesen werden [S] |
| **Sentinel Hub** [S] | Process API höchstens 2500 × 2500 px; je Collection eine Grenze der Auflösung (genannt 1500 m/px für Sentinel-2 L2A), abhängig von `previewMode` | Wortlaut und Grenzen nicht belastbar geklärt |
| **Earth Engine** [S] | Pyramide je Asset schon beim Einlesen; Stufe aus 2 × 2 Pixeln der darunter, Regel `MEAN`, `SAMPLE` oder `MODE`; die Skala folgt aus der Ausgabe, Kacheln entstehen beim Anzeigen | die Pyramide liegt **je Asset**. Über viele Assets hinweg rechnet EE erst beim Anzeigen |
| **GDAL** [P\*] | VRT nutzt die Übersichten der Quellen. Ab „zehntausenden“ Kacheln empfiehlt die Doku GTI (ab 3.9) mit eigenen Übersichtsstufen (`OVERVIEW_<i>_DATASET`). `gdaladdo --partial-refresh-from-source-timestamp` (ab 3.8) rechnet nur die Bereiche neu, deren Quellen neuer sind | das ist dasselbe Muster wie P1 mit Kopie unveränderter Kacheln (§5.2), nur als Datei statt als Kacheln |
| **GeoZarr-Multiskalen** [S] | Konvention seit Oktober 2025 veröffentlicht, Reifegrad „Proposal“ | — |
| **Netz** [S] | S3: erstes Byte rund 100–200 ms bei kleinen Objekten. tilebench: 1 HEAD und 1–2 GETs je Datei, also 3–4 Anfragen je Datei mit Übersicht [A] | gemessen hier: 0,07 s je Datei mit 6 Threads, 0,32 s nacheinander (Methode) |

**Folgerung [A]:**

- Für Kachel-Datensätze ist die Praxis eine Pyramide über die Dateien hinweg. Earth Engine hat sie je Asset; GDAL bietet sie mit GTI und `gdaladdo`.
- Für Szenen ist die Praxis ein Budget je Kachel (pgstac: 100 Items, 5 s) oder eine harte Grenze (Planetary Computer: z8 bzw. z9).
- Eine **Invalidierung von Pyramiden** nach `ETag` oder Frist fand der Recherche-Agent nirgends als veröffentlichte Standardpraxis beschrieben. Belegt sind nur Bausteine: `updated` und `file:checksum` je Asset bei der FSDI, das teilweise Neurechnen von `gdaladdo`, TTL-Caches für Asset-Listen in cogeo-mosaic.

---

## 4. Rechnung: Dateien je Kachel [A]

Eine 512er-Kachel der Stufe z misst bei 47° N rund 27 330 km / 2^z Kantenlänge. Höchstzahl der Dateien je Kachel bei ungünstiger Lage, gerechnet aus der Kachelgröße der Quelle:

| Stufe | Kante | Pixel | swissALTI3D (1 km) | DEM GLO-30 (1°) | WorldCover (3°) | BEV DGM (≈ 40 km, [S]) |
|---|---|---|---|---|---|---|
| z14 | 1,7 km | 3,3 m | 9 [M, `swissalti3d.yaml:170`] | 1 | 1 | 1 |
| z13 | 3,3 km | 6,5 m | 25 [M, ebd.] | 1 | 1 | 1 |
| z12 | 6,7 km | 13 m | ≈ 60 | 1–2 | 1 | 1–2 |
| z11 | 13 km | 26 m | ≈ 200 | 1–2 | 1 | 2 |
| z10 | 27 km | 52 m | ≈ 770 | 2–4 | 1–2 | 2–4 |
| z8 | 107 km | 209 m | ≈ 11 500 | ≈ 5 | 2–4 | ≈ 9 |
| z6 | 427 km | 840 m | alle ≈ 45 000 | ≈ 32 | ≈ 7 | alle 55 |
| z4 | 1 700 km | 3,3 km | alle | ≈ 300 (Land) | ≈ 50 | alle |
| z2 | 6 800 km | 13 km | alle | ≈ 3 000 | ≈ 500 | alle |

Und die Auflösung der gröbsten Übersicht je Datei, also bis zu welcher Stufe eine Datei noch sinnvoll aus sich selbst liest:

| Quelle | gröbste Übersicht | entspricht etwa |
|---|---|---|
| swissALTI3D | 4 m [M] | z14 |
| DEM GLO-30 | 1:8, rund 240 m [M] | z8 |
| WorldCover | 1:64, rund 600 m [M, `adr/0023` §6.1] | z6–z7 |
| BEV DGM 1 m | 1:256, rund 256 m [M, `adr/0023` §0 Punkt 4] | z8 |
| Sentinel-1 GRD | 1:64, rund 640 m [M] | z6–z7 |
| Sentinel-2 (TCI) | Übersichten bis z8 lesbar mit einem Block [M, `adr/0006` §3.4] | z8 |

**Folgerung:** Unter der Stufe der gröbsten Übersicht liest GDAL zwar immer noch nur einen Block je Datei. Die Zahl der Dateien wächst aber weiter (§3, Faustregel der Praxis). Entscheidend ist die Zahl der Dateien je Kachel, nicht die Auflösung.

---

## 5. Punkt 1: Kachel-Datensätze aus vielen Dateien — Übersichtspyramide

### 5.1 Optionen

| | Weg | Bild bei jedem Zoom | Last an der Quelle | Speicher | Bewertung |
|---|---|---|---|---|---|
| **P1** | Pyramide als Job, Kacheln je Stufe im Objektspeicher, Fassung im Pfad, Frist je Präfix | ja, nach dem Bau | einmal je Fassung und Frist | ja, flüchtig | **Empfehlung** |
| P2 | Pyramide synchron bei der ersten Anfrage, Stufe für Stufe aus den Kindern | ja, aber die erste Kachel bei z8 über der Schweiz bräuchte rund 11 500 Dateien, etwa 13 min bei 6 parallelen Abrufen [A] | wie P1 | ja | scheitert an der ersten Anfrage |
| P3 | Budget je Kachel wie bei Szenen, darüber Teilkachel | nein, bei swissALTI3D unter z12 fast leer | hoch, bei jeder kalten Kachel | nein | nur für DEM, WorldCover, BEV bis z6 tragfähig |
| P4 | fremde Pyramide der Quelle (z. B. WMTS-Dienst des Amts) | ja | gering | nein | anderer Host, nur fertig gefärbte Bilder statt Werte, eigener Stil, eigene Lizenzfrage; widerspricht „Darstellung mit Apply“ (ENTSCHEIDUNGEN §2) |
| P5 | nichts ändern, Coverage unter `min_zoom` | nein | keine | nein | verfehlt die Vorgabe |

### 5.2 Empfehlung P1 im Einzelnen

**Was in der Pyramide liegt.** Werte, nicht Bilder: das erste Band bzw. die Bänder der Standardansicht im Datentyp der Quelle, Nodata wie die Quelle. Farbe, Stretch, Colormap und Band-Math (T1) rechnet der `tiler` wie heute auf der Kachel. So gilt die Pyramide für jede Darstellung.

**Wann sie entsteht (F1 = 2, Otto 11.11.2026).** Als Job, nie synchron in der Kachelanfrage:

- **Nach der Materialisierung:** Jede Materialisierung eines Datensatzes mit `overview: pyramid` stößt den Bau an, auch ohne Nutzung. Der Job ist eindeutig je Datensatz und Fassung; ein zweiter Anstoß stellt keinen zweiten ein.
- **Fassungswechsel:** Eine Materialisierung mit neuer Fassung (`ETag` und `updated` der Collection, M5-08b, Antwort Otto zu #320 Frage 1) baut neu, mit Kopie unveränderter Kacheln (Verfall unten).
- **Wie der Anstoß technisch läuft, klärt V6:** Entweder stellt der Befehl `materialize` den Job ein, oder `jobs` findet eine Fassung ohne Pyramide.
- **Solange keine Pyramide da ist** (erster Bau läuft, Bau gescheitert): Die Kachel antwortet `404` mit dem Kopf `X-EarthX-Overview: building` bzw. `failed`. Die Karte zeigt die Coverage; der Grund steht nur im Tooltip des Layers (`note`, Leitfaden §4), kein Zusatztext über der Karte (Auslegung nach Ottos Antwort zu den Teilkacheln).
- Ursprünglich empfohlen war Option 1 (Bau bei der ersten Anfrage, ungenutzte Datensätze kosten nichts). Otto hat Option 2 gewählt: Das erste Bild soll nicht auf einen Bau warten (§13).

**Wo sie liegt (F2).** Im eigenen Objektspeicher unter einem neuen Präfix:

```
overviews/{dataset_id}/{fassung}/{z}/{x}/{y}.tif
```

- Je Web-Mercator-Kachel ein kleines GeoTIFF, 512², gekachelt und komprimiert. Kacheln ohne Daten fehlen; das ist bei der Schweiz rund die Hälfte des Rahmens [A].
- `fassung` ist ein kurzer Hash aus `ETag` und `updated` der Collection.
- Der `tiler` liest wie bei Ergebnissen über `objectstore` mit seinem Leseschlüssel (`architekturplan.md` 3.1, Nachtrag M4-13c-5); die Adresse kommt aus `objectstore`, nicht aus einer Quelle. Keine neue Importregel.
- **Warum Kacheln statt einer Datei:** Sie lassen sich einzeln ersetzen und kopieren (siehe Verfall), und eine Kachel ist genau ein Objekt-GET.
- Alternativen sind ein COG je Datensatz und Fassung im Raster von WebMercatorQuad (rio-cogeo `--web-optimized`) oder GeoZarr-Multiskalen. Beide lassen sich nicht teilweise erneuern.

**Wer baut.** `jobs` mit einer neuen Job-Art „Übersicht“ (keine Rezept-Art, kein Nutzer):

- Der Kern liest je Basiskachel die betroffenen Dateien über `gateway` in der gröbsten passenden Übersicht. Er projiziert sie in eine Kachel und gibt ein Array zurück. Er kennt keinen Objektspeicher (B9).
- Die Hülle lädt hoch und baut die Stufen darüber aus je vier Kindern.
- Die Items kommen aus pgstac; materialisierte Datensätze haben sie dort (M5-08).

**Stufen (F5).** Die Basis ist die höchste Stufe, bei der eine Kachel aus den Dateien das Budget je Kachel aus §6.2 überschreitet; darunter liegt alles bis z0:

| Datensatz | ab hier aus Dateien (`min_zoom`) | Pyramide | Basis-Pixel |
|---|---|---|---|
| swissALTI3D | z13 (≤ 25 Dateien) | z0–z12 | 13 m |
| BEV DGM (sobald angebunden) | z7 | z0–z6 | 840 m |
| WorldCover | z5 | z0–z4 | 3,3 km |
| DEM GLO-30 | z7 | z0–z6 | 840 m |

**Resampling.** Eine Pflichtangabe je Datensatz ohne Vorgabe (B10): `average` für Höhen, `mode` für Klassen (WorldCover), `nearest` als Notweg. So handhabt es auch die Pyramiden-Regel von Earth Engine (§3).

**Verfall (F3).**

- Eine **neue Fassung ist ein neuer Pfad**; die alte wird nie mehr gelesen. Beim Neubau kopiert die Hülle Basiskacheln, deren Items gleich geblieben sind, serverseitig aus der alten Fassung (S3 `CopyObject`, kein Abruf an der Quelle). „Gleich geblieben“ heißt: gleicher Hash über ID und `updated` der beteiligten Items. Neu gelesen wird nur, wo sich Items geändert haben.
- **Frist:** 30 Tage ab der letzten Bestätigung der Fassung, als Metadatum `checked-at` je Objekt; beim Bau ist das der Zeitpunkt des Lesens an der Quelle. `jobs/cleanup.py` löscht nach `checked-at`. Eine Kopie beim Fassungswechsel übernimmt `checked-at` der alten Kachel, sie verlängert also nicht.
- **Verlängerung nach 30 Tagen (F3, Ergänzung Otto 11.11.2026):** Vor Ablauf fragt eine Prüfung die Fassung der Quelle ab, wie die Materialisierung: Collection über `gateway`, `ETag` und `updated` verglichen. Bei der FSDI geschieht das ohne `If-None-Match` (Antwort Otto zu #320 Frage 1); bei Quellen mit `304` ist es eine bedingte Anfrage.
  - **Unverändert:** Die Hülle setzt `checked-at` neu, ohne an der Quelle zu lesen (S3 `CopyObject` auf sich selbst mit neuen Metadaten; Kosten nur im eigenen Speicher).
  - **Geändert:** Materialisierung und Neubau mit Kopie unveränderter Kacheln.
  - **Nicht erreichbar oder Formfehler:** keine Verlängerung; die Pyramide läuft ab (Auslegung: Ohne bestätigte Fassung gibt es keine Verlängerung). Der nächste erfolgreiche Lauf baut neu.
  - Wo die Prüfung geplant läuft, klärt V6.
- Als Sicherung dient eine Lebenszyklus-Regel auf `overviews/` mit 31 Tagen, gesetzt wie die von `results/` (`adr/0015` §7.3, W1; Garage filtert nur nach Präfix und Größe). Die Verlängerung setzt das Änderungsdatum des Objekts neu, die Regel greift also erst nach einer ausgebliebenen Verlängerung.
- Begründung der 30 Tage: Ein Bau kostet die Quelle einige zehntausend Anfragen (§8). Mit 7 Tagen hieße das bei einem genutzten Datensatz viermal im Monat.

**Ehrlichkeit (F12).**

- Kacheln aus der Pyramide tragen den Kopf `X-EarthX-Source: overview`. Die Karte zeigt die Marke „Overview“ am Layer mit dem Tooltip „Resampled from the original files; zoom in to level n for the originals.“
- Statistik, Zuschnitt, Download und Jobs lesen nie aus der Pyramide, sondern immer aus den Originalen (Prinzip 8: Rezept aus Quell-Items).
- Die Quellenangabe der Pyramide ist die für bearbeitete Daten („©swisstopo (modified)“, M5-08c F2).

### 5.3 Auslegung von Prinzip 1 (Entscheidung Otto, 11.11.2026)

Prinzip 1 (`projektuebersicht.md` §2): „Abgeleitete Produkte (…) werden nur flüchtig mit Ablaufdatum gespeichert.“ Für Übersichtspyramiden gilt:

- **Jedes Objekt hat ein Ablaufdatum** (30 Tage ab der letzten Bestätigung der Fassung).
- **Eine Verlängerung ist zulässig, wenn eine Prüfung an der Quelle die Fassung bestätigt hat.** Die Pyramide bildet dann nachweislich den aktuellen Stand der Quelle ab; sie ist kein eigener Bestand neben der Quelle.
- **Ohne Bestätigung läuft sie ab.** Eine Quelle, die verschwindet oder sich nicht mehr prüfen lässt, hinterlässt nach spätestens 31 Tagen nichts.
- Die Auslegung gilt nur für Übersichtspyramiden. Job-Ergebnisse bleiben bei 7 Tagen ohne Verlängerung (`architekturplan.md` 12.3, Q10).

---

## 6. Punkt 2: Szenen-Datensätze

### 6.1 Was heute schon geht

Eine **Einzel-Item-Kachel** kostet bei jedem Zoom dasselbe, solange sie nur ihr eigenes Item liest (Registry-Text, `registry.py:764-775`): eine Datei, ein Block der gröbsten Übersicht. Bei Sentinel-1 sind das kalt rund 1,1 s [M] und warm 0,04 s affin bzw. 0,24 s mit TPS bei z7 [M, DS-04 §11]. `min_zoom` 7 schützt also nicht die einzelne Kachel. Er schützt die Zahl der Kacheln eines Ausschnitts und hält die Regel „Übersicht ist Sache der Coverage“ (`sentinel-1-grd.yaml:140-145`).

### 6.2 Budget je Kachel statt „12 ab z8“ (F6)

Die Mosaik-Kachel liest die Szenen der Auswahl in der Reihenfolge des Mosaiks (`mosaic_order`, unverändert). Sie hört auf, sobald die Kachel voll ist (`FirstMethod`, schon heute) oder das Budget erschöpft ist:

| Budget | Vorschlag | Begründung |
|---|---|---|
| Dateien je Kachel | **32** | pgstac nimmt 100 Items, der Planetary Computer 20 für WorldCover (§3). swissALTI3D z13 braucht bis 25 (§4). Sentinel-1 und -2 bei z4–z6 je Überflug meist unter 32 [A]. 32 × 0,07 s ≈ 2,2 s kalt bei 6 parallelen Abrufen [A aus M] |
| Zeit je Kachel | **4 s** | unter der Vorgabe von pgstac (5 s, §3), weil die Karte viele Kacheln zugleich fragt [A] |
| Gleichzeitig je Kachel | 4 (wie heute `MAX_ITEM_FETCHES` und Portion) | unter 6 je Host in `gateway` |

**Was über dem Budget passiert:**

- **Dateien erschöpft:** Die Kachel enthält die ersten 32 Dateien in Mosaik-Reihenfolge. Das ist deterministisch und damit cachebar; die Kachel trägt den Kopf `X-EarthX-Partial: n`. **Keine sichtbare Marke** (Otto, 11.11.2026, Leitfaden „wenig Text“). Höchstens ergänzt der Tooltip des Layers (`note`) den Satzteil „not all scenes at this zoom“, solange eine sichtbare Kachel so antwortet.
- **Zeit erschöpft:** Die Kachel ist nicht deterministisch. Sie geht mit `Cache-Control: no-store` hinaus, damit kein Zufallsbild im CDN landet.
- **Alle Grenzen** sind Konstanten wie heute (m4-17 §5, KE6) und keine Registry-Felder. Sie werden mit dem Messskript (F11) kalibriert.

`MIN_MOSAIC_ZOOM` und `MAX_SCENES_PER_TILE` entfallen; an ihre Stelle tritt das Budget.

### 6.3 Sehr viele Szenen

Eine Auswahl über ein Land oder einen ganzen Überflug von Sentinel-2 hat bei z4 leicht über 100 Szenen in einer Kachel [A]. Drei Wege:

| | Weg | Bewertung |
|---|---|---|
| **S1** | Teilkachel mit Marke (§6.2), sonst nichts | einfach, ehrlich, deterministisch. **Empfehlung** für den Anfang |
| S2 | Übersicht der Auswahl als Job: ein Mosaik der gewählten Szenen in grober Auflösung (z. B. 500 m) über den bestehenden Mosaik-Job (M4-12), gespeichert wie ein Ergebnis (7 Tage, `results/`) und gelesen über `/results/{id}` | nutzt Vorhandenes. Kostet je Auswahl einen Job (300 Szenen ≈ 1 min [A]); sinnvoll, wenn die Messung oft Teilkacheln zeigt (F7) |
| S3 | Quicklooks der Quelle unter einer Stufe (Sentinel-2 hat sie, `browse: quicklook`) | Sentinel-1 erst mit F11 aus #319; Quicklooks sind 8-Bit-Bilder, keine Werte |

### 6.4 `min_zoom` für Szenen

- Sentinel-1 geht auf **0**, Sentinel-2 bleibt bei 0.
- Die Einzelszenen der Karte hängen dann nicht mehr an `MIN_MOSAIC_ZOOM` (`mosaic.ts:92`). Unter z8 zeichnet die Karte die Auswahl als eine Mosaik-Ebene statt als bis zu 40 Einzelszenen.

---

## 7. Punkt 3: grobe Gitter und Datensätze mit einer Datei

| Fall | Beispiel | Regel |
|---|---|---|
| eine Datei mit Übersichten | ein landesweites COG | `overview: own`, `min_zoom` 0. Eine Datei ist bei jedem Zoom ein Block; kein Budget berührt |
| eine Datei ohne Übersichten, kleines Feld | Meteo-Gitter 1 km über der Schweiz (≈ 350 × 250 Zellen [A]) | `own`, `min_zoom` 0: das ganze Feld ist weniger als ein MB und passt in jedes Budget. Bei Zarr bzw. virtuellen Verweisen (`adr/0029`) liest die Kachel alle Chunks einer Zeitscheibe |
| eine Datei ohne Übersichten, großes Feld | globales Gitter über rund 16 MP je Zeitschritt [A] | `pyramid` je Zeitschritt wie §5, aber nur bei Bedarf und nur für den gewählten Zeitschritt. Bis es so einen Datensatz gibt: offen, mit `adr/0029` F1 Option C („flüchtiger COG-Cache später“) zusammen zu entscheiden |
| Nativgitter ohne Raster (ICON) | — | außerhalb dieses ADR (`adr/0029` §1) |

Für das Budget zählt bei Gittern statt der Zahl der Dateien die Zahl der Chunks (Anfragen) und ihre Bytes. Vorschlag: höchstens 32 Anfragen und 32 MB je Kachel, sonst `pyramid`.

---

## 8. Punkt 4: Kosten, Lizenz, Prototyp-Quellen, Messung

### 8.1 Kosten [A, Zeiten aus M]

**swissALTI3D, eine Pyramide z0–z12 je Fassung:**

- **Rahmen:** 26 505 × 17 873 px bei z12 (474 MP), davon etwa 51 % Land der Schweiz; Float32 also rund 1 GB roh.
- **Speicher:** komprimiert und mit allen Stufen darüber 0,4–0,9 GB. Annahme ist Kompression 2:1 bis 3:1 bei Höhen mit Prädiktor; nicht gemessen.
- **Lesen:** 45 000 Dateien (2-m-Asset, Übersicht 1:2 = 4 m), je 1–2 Anfragen, also 45 000–90 000 GETs mit 3–7 GB.
- **Zeit:** ohne Mindestabstand bei 6 parallelen Abrufen rund 45 000 × 0,07 s ≈ 55 min [A aus M]. Mit dem Mindestabstand von **0,25 s je Host** (F4) bestimmt der Abstand die Dauer: 45 000–90 000 × 0,25 s ≈ **3,1–6,3 h**.
- **Rechnen:** Umprojektion von 474 MP mit `average` ≈ 1,0 × 0,146 s/MP ≈ 70 s auf einem Kern (Faktoren aus `adr/0014` §5.5). Das ist neben dem Lesen vernachlässigbar.
- **Neubau bei neuer Fassung:** nur die geänderten Basiskacheln. Ein neuer Stand betrifft nach M5-08 §2 jeweils eine Befliegungsregion, also einen Teil.

**WorldCover:** 2 651 Dateien lesen [P, Registry], die gröbste Übersicht je Datei; ≈ 3 min bei 6 parallelen Abrufen, Speicher unter 50 MB (UInt8).

**DEM GLO-30:** rund 26 000 Dateien weltweit [S], z0–z6. ≈ 30 min Bau, Speicher unter 1 GB.

**Sentinel-1 und -2:** kein Speicher. Eine Kachel bei kleinem Zoom liest bis zu 32 Dateien statt bis zu 12. Kalt kostet Sentinel-1 je Datei rund 1,1 s [M]; bei 4 parallelen Abrufen dauert eine volle Kachel also bis rund 9 s und läuft damit in die Zeitgrenze von 4 s. Warm (Kopf im Cache von GDAL) ist es ein Bruchteil. Das muss die Messung zeigen (F11).

**Objektspeicher:** Cent-Beträge je Monat bei den Größen oben [S, übliche Preise je GB und Monat].

### 8.2 Rücksicht auf die Quellen (`adr/0025` §6.2, F4)

- Der Bau läuft über `gateway`: 6 Verbindungen je Host, `User-Agent` der Plattform, Unterbrecher nach 3 Fehlern in Folge (der Job pausiert und versucht es später; Fehlerart wie `source_timeout`).
- **Mindestabstand (F4, Otto 11.11.2026):** **0,25 s je Host**, also höchstens 4 Anfragen je Sekunde, einstellbar über `host_intervals` (M5-18) auch für den Bau. Grund sind die Fair-Use-Regeln der FSDI: swisstopo kann den Zugang bei übermäßiger Nutzung einschränken (`adr/0023` §3.1, Quelle dort: geo.admin.ch „change limits, fair use“). Das CDN vor den Dateien nimmt einen Teil der Last [A].
- Höchstens ein Bau je Host gleichzeitig.

### 8.3 Lizenz (B11)

- Die Pyramide ist eine **Bearbeitung** (Resampling, Umprojektion) und eine Speicherung. Die Stufe „Anzeige“ verlangt schon heute Weitergabe und Bearbeitung (B11). Ein Datensatz mit Stufe „Anzeige“ darf also eine Pyramide haben; einer mit Stufe „Katalogeintrag“ hat ohnehin keine Kacheln.
- **Quellenangabe:** bei Pyramiden-Kacheln die für bearbeitete Daten, wo die Quelle eine kennt (swisstopo: „©swisstopo (modified)“). Bei CC BY 4.0 (WorldCover) zusätzlich „modified“ (Hinweis auf Änderungen, CC BY 4.0 §3(a)(1)(B) [S]).
- Neue Lizenz-Einstufungen braucht es nicht.

### 8.4 Prototyp-Quellen (`adr/0024`, F10)

Eine Pyramide ist eine gespeicherte Bearbeitung einer Quelle mit unklarem Recht. Vorschlag:

- nur in der Prototyp-Instanz, mit 7 Tagen Frist wie Ergebnisse;
- jede Antwort `private, no-store` (R7);
- keine Verlängerung nach §5.3 (Auslegung bei der Übernahme, §14);
- `catalog-load` ohne Schalter löscht `overviews/proto-*` mit (R6).

### 8.5 Messung (F11)

Gemessen ist bisher nur, was oben steht (eine Datei je Quelle, zwölf Dateien von swissALTI3D). Für eine Entscheidung über die Budgets fehlt:

1. **Kachelzeiten** je Zoomstufe z0–z14 für swissALTI3D (Dateien, nur bis z13) und Sentinel-1 (ein Überflug, 10–30 Slices), kalt und warm, über den echten `tiler` und `gateway`: Zeit, Range-Reads, Bytes und Dateien je Kachel.
2. **Bau einer Basiskachel** von swissALTI3D bei z10: ≈ 770 Dateien; Zeit und Bytes.
3. **Kompression** der Pyramide (eine Basiskachel).

Ein Messskript dafür über `gateway` gehört in den ersten Umsetzungs-PR (V1, §12) und läuft bei Otto lokal **per `docker compose run`**, weil es auf seinem Rechner kein Python gibt (F11, Otto 11.11.2026). Es liegt deshalb im Image, wie der Befehl `materialize` (`docker compose run --rm materialize swissalti3d`, README). Ein Ordner `scripts/` außerhalb des Images genügt nicht (`backend/Dockerfile:52` kopiert nur `earthx/`). Die Ausgabe enthält keine AOI, Adresse oder Item-ID. Der Weg über `curl` aus `adr/0023` §9.3 misst nur Köpfe und Bytes, nicht, was GDAL tatsächlich liest. Die Hosts sind in dieser Umgebung schon frei [M].

---

## 9. Punkt 5: `min_zoom` in der Registry (F9)

| | Weg | Bewertung |
|---|---|---|
| **Z1** | `min_zoom` bleibt mit neuer Bedeutung „ab hier aus den Originaldateien“. Neues Pflichtfeld `viewer.overview` ohne Vorgabe (B10) mit `own`, `pyramid` oder `scenes`, dazu `viewer.overview_resampling` bei `pyramid` | erklärt, was unter `min_zoom` geschieht, statt es abzuschneiden. **Empfehlung** |
| Z2 | `min_zoom` entfällt; der `tiler` entscheidet allein nach Budget | weniger Felder; aber dann steht nirgends, ab wann Originale gezeigt werden (Prinzip 9) |
| Z3 | nur `min_zoom` senken | erfüllt die Vorgabe für Sentinel-1, nicht für swissALTI3D |

Bei Z1:

- TileJSON nennt `minzoom: 0` für jeden angezeigten Datensatz. Die Kachelroute bedient z < `min_zoom` aus dem Weg, den `overview` nennt; `400` „not released“ gibt es dann nur noch über `max_zoom`.
- **Registry-Prüfung (Test):** Jeder Eintrag mit Lizenzstufe „Anzeige“ oder höher hat ein `overview`, und bei `own` ist `min_zoom` 0. So bleibt die Vorgabe „Bild bei jedem Zoom“ für künftige Datensätze automatisch geprüft, auch im automatischen Onboarding (`adr/0031` §10.2).
- Der Docstring von `ViewerInfo` (`registry.py:714-775`) wird neu geschrieben.

Werte nach dieser Empfehlung:

| Datensatz | `min_zoom` heute → neu | `overview` |
|---|---|---|
| Sentinel-1 GRD | 7 → 0 | `scenes` |
| Sentinel-2 C1 L2A | 0 → 0 | `scenes` |
| swissALTI3D | 14 → 13 | `pyramid`, `average` |
| DEM GLO-30 | 0 → 7 | `pyramid`, `average` |
| WorldCover 2020, 2021 | 0 → 5 | `pyramid`, `mode` |

DEM und WorldCover zeigen heute schon ab z0 ein Bild, aber nur je Item. Das ist eine Ebene je Kachel der Quelle, höchstens 40 (§2). Mit der Pyramide kommt unter z7 bzw. z5 ein Bild des ganzen Datensatzes statt eines Teils.

---

## 10. Punkt 6: Grenzen nach Kosten

### 10.1 Kachel

Budget je Kachel nach §6.2. Die Zahl der Items einer Auswahl spielt für die Kachel keine Rolle mehr, nur die Dateien, die eine Kachel tatsächlich liest.

### 10.2 Die 64 in der URL (F8)

Die 64 kommen nicht aus den Kosten, sondern aus der Länge der URL (m4-17 §5: 64 IDs ≈ 2,4–4,3 kB, Grenze 8 kB vor CDNs). `adr/0006` hat eine Such-ID verworfen, weil eine ablaufende ID die URL nicht mehr vollständig bestimmt.

| | Weg | Bestimmt die URL das Bild? | Grenze |
|---|---|---|---|
| **U1** | **Auswahl-ID = Hash der kanonischen Item-Liste** (sortiert, mit Datensatz und Darstellung). `POST /collections/{dataset}/mosaic` legt die Liste ab und gibt die ID zurück; die Kachel-URL trägt nur die ID. Läuft der Eintrag ab, antwortet die Kachel `410`, und die Karte legt dieselbe Liste neu an: gleiche Liste, gleiche ID | ja: Der Inhalt bestimmt die ID, und dieselbe ID kann nie ein anderes Bild bedeuten. Damit fällt der Einwand aus `adr/0006` weg | Schutzgrenze für die Ablage, z. B. 2 000 Items bzw. 128 kB; keine Anzeigegrenze. **Empfehlung** |
| U2 | Liste komprimiert in der URL (deflate + base64url) | ja | ≈ 3× mehr, also rund 190 Sentinel-2-IDs [A]; verschiebt die Grenze nur |
| U3 | 64 bleiben, darüber Szene für Szene | ja | heutige Lücke |

Bei U1 liegt die Liste in Postgres (Anwendungs-Cache, `architekturplan.md` 12.3) mit Frist 7 Tage. Ein Ausfall macht nur langsamer: Die Karte legt neu an.

So arbeitet titiler-pgstac mit dem Hash einer registrierten Suche [S, §3]. Der Unterschied: Hier wird eine feste Liste abgelegt, keine Suche, die sich mit dem Katalog ändern kann.

### 10.3 Zuschnitt und Job (F13)

Die Zahl 25 (`MAX_DOWNLOAD_ITEMS`, `MAX_ORDER_ITEMS`) begrenzt die Laufzeit, nicht den Speicher (Kommentar `download.py:249-254`). Die Schätzung nach `adr/0014` §5.5 kennt die Laufzeit schon: rund 1 s je Asset für das erste Öffnen plus Zeit je MB. Vorschlag:

| Weg | Heute | Neu |
|---|---|---|
| Zuschnitt (synchron) | ≤ 25 Szenen, ≤ 500 MB | geschätzte Dauer ≤ 60 s und ≤ 500 MB; darüber der Hinweis „As a job“ |
| Job | ≤ 25 Items, ≤ 5 GB, ≤ 1,5 GB Speicher, Laufzeit aus Schätzung | ≤ 5 GB, ≤ 1,5 GB, Laufzeit aus Schätzung; dazu eine Schutzgrenze von 2 000 Items gegen Missbrauch, keine fachliche Grenze |

- Die Schätzung muss dafür die Öffnungen ehrlich zählen: Dateien, die die AOI berühren, nicht alle Items der Auswahl. Bei swissALTI3D mit 0,07–0,3 s je Datei [M] ergibt ein Job über 2 000 Kacheln (≈ 45 × 45 km) 2–10 min [A].
- **Zusammenhang mit Punkt 1:** Zuschnitt und Job lesen nie aus der Pyramide. Für sie bleibt die Grenze die Dauer. Eine AOI über die ganze Schweiz in voller Auflösung bleibt deshalb ein Fall für „zu groß“ mit Begründung.

### 10.4 Frontend: 40 Ebenen und #319 F13 (F14)

- Mit U1 und dem Budget zeichnet die Karte jede Gruppe, die ein Mosaik sein kann (gleiches Asset, Szenen eines Datensatzes), als **eine** Ebene bei jedem Zoom.
- Der Rückfall „Szene für Szene“ bleibt nur für Gruppen, die kein Mosaik sein können. Dort bleibt die Grenze von 40 Ebenen, aber die Szenen werden nach Lage gewählt: zuerst die im sichtbaren Ausschnitt (#319 F14 Option 2), neu bei jeder Bewegung.
- **#319 F13** („Karte nach Crop and merge leer bis zur Bewegung“, swissALTI3D, über 64 Kacheln) ist nicht nachgestellt (#319 §14.6). Meine Vermutung [A], nicht geprüft:
  - Über 64 Szenen fällt die Karte auf „Szene für Szene“ zurück.
  - Jede Szene hat `min_zoom` 14, wird also erst ab Kartenzoom 13,5 gezeichnet (`firstZoomOf`).
  - Eine AOI über rund 8 × 8 km passt die Karte bei etwa z12 ein. Erst das Hineinzoomen zeigt das Bild.
  - Mit U1, `pyramid` und `min_zoom` 13 fallen alle drei Bedingungen weg.
- Vorschlag: vor der Behebung ein Browser-Test aus `frontend/e2e/many-scenes.cjs` mit über 64 Kacheln und einer AOI, die unter z13,5 eingepasst wird. Er ist vorher rot, sonst ist die Vermutung falsch.

---

## 11. Widersprüche zu bestehenden Regeln

| Stelle | Heute | Mit Annahme |
|---|---|---|
| `adr/0006` §5, `architekturplan.md` 6.3 | Item-Liste in der URL, höchstens 64, keine Such-ID | Auswahl-ID aus dem Inhalt (U1); der Grundsatz „URL bestimmt das Bild“ bleibt |
| `plans/m4/m4-17-mosaik-kachel-pfad.md` §5 | 12 Szenen je Kachel, Mosaik ab z8 | Budget je Kachel |
| `catalog/registry.py:714-775` | unter `min_zoom` ist Übersicht Sache der Coverage | unter `min_zoom` der Weg aus `overview` |
| `architekturplan.md` 12.3 | Caching-Ebene „Ergebnis“ nur für Job-Ergebnisse | neue Zeile „Übersicht“ (Objektspeicher, Fassung im Pfad, 30 Tage, verlängert bei bestätigter Fassung) |
| `projektuebersicht.md` §2, Prinzip 1 | „flüchtig mit Ablaufdatum“ | Auslegung für Pyramiden (§5.3): Verlängerung nur nach bestätigter Fassung; Entscheidung Otto |
| `adr/0015` §7.3 | eine Ablaufregel für `results/` | zweite für `overviews/` |
| `adr/0029` F1 | kein flüchtiger COG-Cache in M5 | gilt weiter für NetCDF; Pyramiden sind etwas anderes (Anzeige, nicht Lesen) |
| `adr/0024` R6, R7 | Aufräumen und `no-store` für `proto-` | gilt auch für `overviews/proto-*` |
| `download.py:249-255`, `intake.py:165` | 25 Szenen bzw. Items | Dauer aus der Schätzung, Schutzgrenze 2 000 |

---

## 12. Schnitt (Vorschlag)

Je unter dem Richtwert. Keine davon ist Teil dieses PR; Backlog und M5-Plan bleiben unverändert.

| | Inhalt | Stufe | Hängt ab von |
|---|---|---|---|
| **V1** | Messskript (§8.5) im Image, Aufruf per `docker compose run`; Lauf bei Otto; Zahlen in den PR | B | — |
| **V2** | Budget je Kachel statt `MIN_MOSAIC_ZOOM`/`MAX_SCENES_PER_TILE`, Teilkachel mit Kopf, `no-store` nach Zeitabbruch; Sentinel-1 `min_zoom` 0 | B | V1 |
| **V3** | Auswahl-ID (U1): Route, Ablage, `410`, Frontend legt neu an; 64 entfällt; Rückfall nur für Gruppen ohne Mosaik, 40 nach Lage | B | V2 |
| **V4** | Test zu #319 F13 (vorher rot), Behebung, falls nicht schon durch V3 | A | V3 |
| **V5** | Registry: `viewer.overview`, `overview_resampling`, Prüfung „Bild bei z0“; Docstring | B | V2 |
| **V6** | Job-Art „Übersicht“: Kern (über `gateway`), Hülle (Upload, Stufen, Kopie unveränderter Kacheln), `objectstore` mit Präfix `overviews/` und Regel, Aufräumen nach `checked-at`; Anstoß nach der Materialisierung; Prüfung der Fassung nach 30 Tagen mit Verlängerung (§5.2, §5.3); Mindestabstand 0,25 s | B | V5 |
| **V7** | Kachelroute unter `min_zoom` aus der Pyramide, `404` mit `building`/`failed`; Marke „Overview“ (F12), Teilkacheln und Bau nur im Tooltip des Layers; Quellenangabe „modified“ | B | V6 |
| **V8** | Grenzen von Zuschnitt und Job nach der Schätzung (§10.3) | B | — |
| **V9** | Nachträge in `architekturplan.md` 6.3, 12.3, `projektuebersicht.md` §2 (Auslegung von Prinzip 1, §5.3), `adr/0006`, `adr/0015`, m4-17 | A | mit V3, V6 |

---

## 13. Risiken und Grenzen

- **Erstes Bild:** Mit F1 = 2 entsteht die Pyramide nach der Materialisierung. Nur während des ersten Baus (swissALTI3D: 3,1–6,3 h bei 0,25 s je Host) oder nach einem gescheiterten Bau zeigt die Karte unter `min_zoom` die Coverage. Der Preis: Auch ungenutzte Datensätze kosten Speicher und eine Prüfung je 30 Tage.
- **Last an der Quelle:** 45 000–90 000 Anfragen je Bau bei swissALTI3D. Falls swisstopo drosselt, wird der Bau langsamer, nicht falsch (Unterbrecher).
- **Prinzip 1:** Pyramiden haben ein Ablaufdatum. Sie leben so lange, wie die Quelle ihre Fassung bestätigt (Auslegung §5.3, Entscheidung Otto). Bei einer Quelle, die sich selten ändert, ist das praktisch ein langlebiger Bestand. Abgesichert ist das durch die Prüfung je 30 Tage und die Sicherungsregel von 31 Tagen.
- **Teilkacheln:** Bei sehr großen Auswahlen ist das Bild unter einem Zoom unvollständig; erklärt wird das nur im Tooltip des Layers. Ob das oft vorkommt, zeigt V1.
- **Schätzungen:** Speicher, Kompression, Bauzeit und Dateien je Kachel für BEV, WorldCover und DEM sind abgeleitet [A], nicht gemessen.
- **Stufe C:** Kein Code. Die Zahlen in §6.2 und §8.1 sind Startwerte für V1.

---

## 14. Fragen an Otto — beantwortet am 2026-11-11

**Antworten (Otto, 11.11.2026):** F1–F14 jeweils **Option 1** (Empfehlung), außer F1. Dazu diese Ergänzungen:

1. **F1 = 2:** Die Pyramide wird gleich nach der Materialisierung gebaut und nach einem Wechsel der Quelle, nicht erst bei der ersten Anfrage. Eingetragen in §0, §5.2, §12 (V6), §13.
2. **F3 ergänzt:** Nach 30 Tagen prüft eine bedingte Anfrage (`ETag`/`updated`) die Fassung der Quelle. Ist sie unverändert, wird die Frist verlängert, ohne neu zu lesen. Die Auslegung von Prinzip 1 ist als Entscheidung Ottos festgehalten. Eingetragen in §0, §5.2, §5.3, §13.
3. **F4:** Abstand 0,25 s je Host, einstellbar, mit Verweis auf die Fair-Use-Regeln der FSDI (`adr/0023` §3.1), statt der empfohlenen 0,1 s. Eingetragen in §0, §8.1, §8.2, §12.
4. **F11 ergänzt:** Das Messskript muss per `docker compose run` laufen; auf Ottos Rechner gibt es kein Python. Eingetragen in §8.5, §12 (V1).
5. **Teilkacheln bei Szenen (zu F6):** keine sichtbare Marke, höchstens ein Tooltip (Leitfaden, kein Zusatztext). Eingetragen in §0, §6.2, §12 (V7), §13.

**Auslegungen bei der Übernahme (gelten, bis Otto widerspricht):**

- Auch der Zustand „Pyramide wird gebaut“ bzw. „Bau gescheitert“ steht nur im Tooltip des Layers, nicht über der Karte (nach Ergänzung 5; §5.2).
- Ohne bestätigte Fassung (Quelle nicht erreichbar, Formfehler) wird nicht verlängert; die Pyramide läuft ab (§5.2, §5.3).
- Die Marke „Overview“ aus F12 Option 1 bleibt; Ergänzung 5 nennt nur Teilkacheln.
- Pyramiden von Prototyp-Quellen (F10) werden nicht verlängert, sie laufen nach 7 Tagen ab (§8.4).


**F1 — Wann entsteht die Pyramide (§5.2)?**
1. Als Job bei der ersten Anfrage unter `min_zoom` und nach einem Fassungswechsel, sofern in der Frist gelesen **(Empfehlung)**
2. Als Job für jeden Datensatz mit `pyramid` gleich nach jeder Materialisierung, auch ohne Nutzung
3. Synchron bei der ersten Anfrage

**Antwort F1 (Otto, 2026-11-11): 2 (Bau gleich nach der Materialisierung und nach einem Wechsel der Quelle).**

**F2 — Form und Ort (§5.2)?**
1. Je Web-Mercator-Kachel ein Objekt unter `overviews/{dataset}/{fassung}/{z}/{x}/{y}.tif` **(Empfehlung)**
2. Ein COG oder ein GDAL-GTI je Datensatz und Fassung
3. GeoZarr-Multiskalen

**Antwort F2 (Otto, 2026-11-11): 1.**

**F3 — Frist (§5.2)?**
1. 30 Tage ab dem Lesen an der Quelle (`read-at`), Kopien verlängern nicht; Sicherungsregel 31 Tage auf `overviews/` **(Empfehlung)**
2. 7 Tage wie Ergebnisse
3. 90 Tage

**Antwort F3 (Otto, 2026-11-11): 1, ergänzt: nach 30 Tagen Prüfung der Fassung, bei unveränderter Quelle Verlängerung ohne neues Lesen (§5.3).**

**F4 — Rücksicht beim Bau (§8.2)?**
1. Mindestabstand je Host aus `host_intervals`, für `data.geo.admin.ch` 0,1 s; ein Bau je Host gleichzeitig **(Empfehlung)**
2. 1 s je Host wie beim Harvest (swissALTI3D 12–25 h)
3. Ohne Mindestabstand, nur 6 Verbindungen je Host

**Antwort F4 (Otto, 2026-11-11): 0,25 s je Host, einstellbar, Verweis auf die Fair-Use-Regeln der FSDI; sonst wie Option 1 (ein Bau je Host gleichzeitig).**

**F5 — Stufen der Pyramide (§5.2)?**
1. Basis = höchste Stufe über dem Budget, je Datensatz aus dem Kachelraster der Quelle berechnet (swissALTI3D z12, DEM z6, WorldCover z4) **(Empfehlung)**
2. Fest z0–z8 für alle

**Antwort F5 (Otto, 2026-11-11): 1.**

**F6 — Budget je Kachel (§6.2)?**
1. 32 Dateien und 4 s; über der Dateigrenze eine Teilkachel mit Marke, nach Zeitabbruch `no-store`; Werte mit V1 kalibriert **(Empfehlung)**
2. Nur eine Zeitgrenze
3. 12 Szenen ab z8 bleiben

**Antwort F6 (Otto, 2026-11-11): 1, aber Teilkacheln ohne sichtbare Marke, höchstens Tooltip.**

**F7 — Sehr viele Szenen (§6.3)?**
1. Teilkachel mit Marke; über eine Auswahl-Übersicht als Job entscheiden wir nach V1 **(Empfehlung)**
2. Gleich die Auswahl-Übersicht als Job (S2)
3. Quicklooks unter einer Stufe (S3)

**Antwort F7 (Otto, 2026-11-11): 1, Teilkachel ohne sichtbare Marke (zu F6).**

**F8 — Die 64 in der URL (§10.2)?**
1. Auswahl-ID aus dem Hash der Liste, abgelegt 7 Tage, `410` und neu anlegen; Schutzgrenze 2 000 Items **(Empfehlung)**
2. Komprimierte Liste in der URL
3. 64 bleiben

**Antwort F8 (Otto, 2026-11-11): 1.**

**F9 — `min_zoom` (§9)?**
1. Bleibt als „ab hier aus den Originalen“; neues Pflichtfeld `viewer.overview` (`own`/`pyramid`/`scenes`) und Prüfung „Bild bei z0“ **(Empfehlung)**
2. Entfällt; nur das Budget entscheidet
3. Nur senken

**Antwort F9 (Otto, 2026-11-11): 1.**

**F10 — Prototyp-Quellen (§8.4)?**
1. Pyramide nur in der Prototyp-Instanz, 7 Tage, `no-store`, Aufräumen nach R6 **(Empfehlung)**
2. Keine Pyramide; unter `min_zoom` die Coverage

**Antwort F10 (Otto, 2026-11-11): 1.**

**F11 — Messung (§8.5)?**
1. Messskript über `gateway` im ersten Umsetzungs-PR (V1), Lauf bei dir lokal **(Empfehlung)**
2. Eine Sitzung misst mit `curl` wie `adr/0023` §9.3 (nur Köpfe und Bytes)
3. Beides

**Antwort F11 (Otto, 2026-11-11): 1, das Skript läuft per `docker compose run`.**

**F12 — Ehrlichkeit (§5.2)?**
1. Marke „Overview“ am Layer, Statistik, Zuschnitt und Jobs nur aus Originalen **(Empfehlung)**
2. Statistik bei kleinem Zoom aus der Pyramide, gekennzeichnet

**Antwort F12 (Otto, 2026-11-11): 1.**

**F13 — Zuschnitt und Job (§10.3)?**
1. Die 25 fallen; Dauer ≤ 60 s für den Zuschnitt, sonst als Job; Schutzgrenze 2 000 Items **(Empfehlung)**
2. Die 25 nur anheben (z. B. auf 200)
3. Bleibt

**Antwort F13 (Otto, 2026-11-11): 1.**

**F14 — #319 F13 und die 40 Ebenen (§10.4)?**
1. Test aus `many-scenes.cjs` mit über 64 Kacheln und AOI unter z13,5, vorher rot, in V4; die 40 bleiben nur im Rückfall, gewählt nach Lage **(Empfehlung)**
2. Erst deine Laufdaten wie #319 F13 Option 1
3. Die 40 ganz streichen

**Antwort F14 (Otto, 2026-11-11): 1.**

---

## 15. Folgen

- Umsetzung nach §12, Stufe B je PR; keiner dieser PRs ist Teil dieses ADR. Backlog und M5-Plan bleiben hier unverändert.
- Nachträge in `architekturplan.md` 6.3 und 12.3, `projektuebersicht.md` §2 (Auslegung von Prinzip 1, §5.3), `adr/0006` §5, `adr/0015` §7.3 und `plans/m4/m4-17-mosaik-kachel-pfad.md` §5, je mit Verweis auf dieses ADR.
- Das Onboarding nach `adr/0031` setzt `viewer.overview` je Eintrag; die Pflichttests (§10.2 dort) prüfen „Bild bei z0“.

---

## 16. Quellen

**Im Repo [P]:**

- `CLAUDE.md`; `docs/ENTSCHEIDUNGEN_2026-09-18.md` §2; `docs/KLAERUNGEN.md` B8–B13; `docs/projektuebersicht.md` §2; `docs/architekturplan.md` 3.1, 6.3, 7.3, 12.2, 12.3.
- `adr/0006` §3.4, §3.5; `adr/0014` §5.5, §15i; `adr/0015` §7; `adr/0023` §3.1, §6.1, §9.3; `adr/0024` §2, §6; `adr/0025` §5.3, §6.2, §9; `adr/0029` §0, §1; `adr/0031` §10–§14.
- `docs/plans/m4/m4-17-mosaik-kachel-pfad.md` §1, §5; `docs/plans/m5/m5-08-stac-adapter-swissalti3d.md` §2; `docs/plans/ds/ds-04-s1-anbinden.md` §11 (auf `main`), §14.6–§14.7a (PR #319, offen).
- Code: `backend/earthx/api/mosaic_tiles.py:60-90, 133-136`, `api/tiler.py:218-267`, `api/intake.py:165`, `access/download.py:239-255`, `access/crop_rules.py:78, 123`, `access/mosaic_tiles.py:142-219`, `processing/plan.py:124`, `jobs/submit.py:112-115`, `objectstore/results.py:28-36`, `gateway/policy.py:122-133`, `catalog/registry.py:699-780`; `backend/catalog/datasets/*.yaml`; `frontend/src/mapLayers.ts:34, 1160-1170`, `mosaic.ts:18-27, 91-92, 148, 171-172`, `tileSize.ts:25-40`, `download.ts:49-51`.

**Gemessen am 10.11.2026 [M]:** siehe „Methode“ und Anhang.

**Stand der Technik, gelesen von einem Recherche-Agenten am 10.11.2026 über `raw.githubusercontent.com` [P\*]:**

- pgstac: `src/pgstac/sql/006_tilesearch.sql`; titiler-pgstac: `titiler/pgstac/settings.py`, `CHANGES.md`, `docs/src/endpoints/searches_endpoints.md`.
- rio-tiler: `rio_tiler/mosaic/reader.py`, `mosaic/methods/base.py`, `mosaic/methods/defaults.py`, `constants.py`.
- cogeo-mosaic: `cogeo_mosaic/mosaic.py`, `cogeo_mosaic/backends/base.py`, `docs/src/intro.md`, `docs/src/advanced/dynamic.md`.
- titiler: `docs/src/advanced/performance_tuning.md`; tilebench: `README.md`.
- Planetary Computer: `microsoft/planetary-computer-tasks`, `datasets/{sentinel-1-rtc,sentinel-1-grd,sentinel-2,esa-worldcover}/collection/config.json`.
- GDAL: `doc/source/programs/gdaladdo.rst`, `gdalbuildvrt.rst`, `drivers/raster/vrt.rst`, `gti.rst`, `cog.rst`, `user/virtual_file_systems.rst`.
- swisstopo: Nutzungsbedingungen für kostenlose Geodaten (Bearbeitung und Weitergabe erlaubt, Quellenangabe Pflicht, Einschränkung bei übermäßiger Last); Produktinfo swissALTI3D (März 2022: 800 GB bei 0,5 m, 50,5 GB bei 2 m).

**Nur über Suchtreffer [S], vor dem Bau zu prüfen:** Earth Engine „Scale“ und „Deferred execution“; Sentinel Hub FAQ und Forum (2500 px, `previewMode`); Planetary Computer Pro „tile settings“; AWS „S3 performance guidelines“ (100–200 ms erstes Byte); pgstac „item size analysis“; GeoZarr-Spezifikation; Copernicus Sentinel Data Legal Notice („Contains modified Copernicus Sentinel data [Jahr]“); CC BY 4.0 §3(a)(1)(B).

**Nicht geklärt:** die Übersichten der Sentinel-2-COGs von Earth Search (außer `adr/0006` §3.4), Live-Werte aus `mosaic/info` des Planetary Computer, Minzoom für `cop-dem-glo-30` dort, Tile-Cache von Earth Engine.

---

## Anhang: Messverfahren

Verfahren, ohne AOI und ohne IDs:

- **Köpfe:** `curl -sI` auf die Asset-Adresse (`Content-Length`, `ETag`, `Last-Modified`, `Cache-Control`).
- **Raster:** rasterio 1.5 aus dem venv des Repos über `/vsicurl/` mit `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`. Gelesen wurden Größe, Datentyp, CRS, Blöcke, Übersichten und Kompression.
- **Zeit:** Öffnen und Lesen der gröbsten Übersicht (`read(1, out_shape=…)`), `VSI_CACHE` aus, `CPL_VSIL_CURL_NON_CACHED` für `/vsicurl/`. Einmal nacheinander, einmal mit 6 Threads.
- **Auswahl:**
  - swissALTI3D: die ersten zwei Items der Collection, dann zwölf Items um eine Stadt (eine Suchseite).
  - Sentinel-1: ein Item aus einer Suche über Earth Search (ein Monat, ein Rechteck in der Schweiz, `limit` 1), Adresse nach der Umschreibung aus `sentinel-1-grd.yaml:114-116`.
  - DEM: die Kachel N46 E007.
- Die Skripte lagen im Kratzverzeichnis der Sitzung und sind nicht Teil des PR.
