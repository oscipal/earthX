# DS-03 — Wolkenanteil in der AOI

**Stand:** 26.10.2026, beauftragt von Otto. Paket „Datensatzabhängige Suche und Prozessierung“ (DS), nach VP3 und vor M5; Übersicht in `docs/plans/ds/ds-00-paket.md`.
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für Messung, Recherche und Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach DS-02. Höchstens zwei Stufe-B-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe DS-03 aus `docs/plans/ds/ds-03-wolken-in-aoi.md` aus.“

## 1. Anlass

Die Wolkenangabe der Quelle (`eo:cloud_cover`) gilt für die ganze Szene (rund 110 × 110 km). Otto möchte nach dem Wolkenanteil **in seiner AOI** filtern und sortieren.

## 2. Soll

- Für die Treffer einer Suche (nach der groben Vorauswahl über die Szene) berechnet die Plattform den Anteil bewölkter Pixel in der AOI aus der Klassifizierung (`SCL`, Klassen wie bei `mask`), auf einer groben Übersichtsstufe.
- Ergebnis je Szene, etwa „Clouds in AOI: 3 %“; Filter und Sortierung danach in „Advanced search“ bzw. der Trefferliste.
- Nur für Datensätze mit Klassifizierungsschicht (Registry, wie `earthx:mask`); sonst erscheint die Möglichkeit nicht.

## 3. Im Plan klären (mit Optionen und Empfehlung)

- **Messung und Recherche (Pflicht, rechenrelevant):** Zeit und Bytes je Szene bei verschiedenen Übersichtsstufen; Genauigkeit gegen volle Auflösung; Stand der Technik (etwa übliche AOI-Wolkenstatistik aus SCL bzw. Cloud-Masken) mit Quellen.
- Schnittstelle: AOI nur im Body (POST), nie in URL oder Log; Cache je Szene und AOI-Hash (Hash nicht geloggt); Obergrenze der Szenen je Anfrage; schrittweise Anzeige.
- Welche Klassen zählen als Wolke (Vorschlag wie die Vorgabe von `mask`: 3, 8, 9, 10) und wie mit „no data“ in der AOI umgegangen wird.
- Grenzen der Klassifizierung (Zirren, Schnee) im Tooltip benennen.

## 4. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip. Nicht anwendbare Möglichkeiten werden ausgeblendet, nicht ausgegraut (Otto, 26.10.2026).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Ausgehende Requests nur über `gateway`; keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Kein datensatzspezifischer Code: Unterschiede je Datensatz stehen als Daten in der Registry.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: Anteil gegen eine unabhängige Rechnung auf synthetischen Rastern; AOI nie im Log/URL; Obergrenze; Datensatz ohne Klassifizierung zeigt die Möglichkeit nicht.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), Hell/Dunkel, schmales Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n).
- Vor „fertig“ ist main geholt.

## 6. Plan (28.10.2026, überarbeitet 29.10.2026; Stufe B, kein Produktivcode)

**Freigabe (Otto, 29.10.2026, zu #235):** Fragen 1, 3, 4, 5 und 6 nach Option 1; Frage 2 abweichend nach **Option 2**. Eingearbeitet in §6.0 und §6.4–§6.15:
- **Zu 3:** Klassen 8, 9, 10 wie `eo:cloud_cover`. Die Bezeichnung macht klar, dass Schatten nicht mitzählen (Tooltip).
- **Zu 2:** Der AOI-Filter sitzt in der Suche.
  - In „Advanced search“ gibt es am Wolkenfilter einen Schalter „Within AOI“. Ist er an, gilt der Grenzwert für die Wolken in der AOI (Klassen 8, 9, 10) statt für die ganze Szene.
  - Der Server holt die Treffer der Quelle seitenweise (der Szenenfilter wirkt weiter vorab), misst je Szene und gibt nur passende zurück. Der Wert in der AOI steht zusätzlich bei jedem Treffer.
  - „Within AOI“ ist nur bedienbar, wenn eine AOI und ein Zeitraum (Acquisition date, von–bis) gesetzt sind; sonst ist er gesperrt, mit dem Grund im Tooltip. Die Route weist eine Anfrage ohne Zeitraum ebenfalls ab.
  - Im Plan zu klären: Obergrenze geprüfter Szenen je Suche (Vorschlag 500) mit Hinweis; Höchstlänge des Zeitraums; Fortschritt „found / checked“; Seitenmarken und „Load more“; Cache je Szene und AOI (höchstens 7 Tage, Schlüssel nie in Log oder URL); mehrere Datensätze; Last auf die Quelle.
  - Weil das Schnittstelle und Kosten ändert, wird der überarbeitete Plan vor dem Code noch einmal vorgelegt (§6.15).
- **Zu 6:** In dieser Session nur DS-03a (Backend), nach erneuter Freigabe. DS-03b (Frontend, nach DS-02c) bekommt einen eigenen Abschnitt (§6.17).
- **Messskripte** liegen unter `scripts/ds-03-clouds/` (§6.16). **ADR:** `adr/0021` „§6 Nachtrag DS-03“.

**Zweite Freigabe (Otto, 29.10.2026, zu #235):** Fragen F2a, F2b, F2d, F2e nach Option 1, F2f angenommen, F2c nach Option 1 mit Zusatz für DS-03b, F7 nach **Option 3**. KE2–KE6 angenommen, KE1 geändert. Eingearbeitet in §6.5, §6.9, §6.14, §6.15, §6.17 und §6.18:
- **F2c, Zusatz für DS-03b:** Bei aktivem „Within AOI“ fragt das Frontend selbst mit der Seitenmarke weiter, bis die Seite gefüllt oder die Obergrenze erreicht ist. Dabei zeigt es „found / checked“, und der Vorgang ist abbrechbar. Eine leere Seite mit nur „Load more“ kommt nicht vor.
- **KE1 geändert:** Bei einer AOI mit mehr als 1 000 Punkten bleibt „Within AOI“ bedienbar. Die Messung nutzt das echte Polygon aus dem Body, falls nötig vereinfacht mit einer Toleranz unter der Auflösung der gelesenen Stufe, auch wenn die Suche selbst das umgebende Rechteck schickt. Bei einer Punkt-AOI bleibt der Filter gesperrt, mit Grund im Tooltip.
- **F7, Option 3:** Diese Session setzt DS-03a1 (Grundlagen) um. DS-03a2 (Filter in der Suche) ist nach dem Merge eine neue Session (§6.18).
- Frage 2 steht im Log damit auf „entschieden“.

Belegstufen wie in DS-02: [P] Code oder Primärquelle gelesen, [M] in der Sitzung gemessen, [A] eigene Ableitung, [S] nur aus Suchtreffern oder Foren belegt (die meisten Primärquellen waren aus der Sitzung nicht erreichbar).

### 6.0 Kurzfassung

- **Entschieden (Otto, 29.10.2026):**
  - **Rechenstufe:** gröbste Übersicht mit mindestens 10 000 Pixeln in der AOI, sonst 20 m (§6.4).
  - **Klassen und Nenner:** 8, 9, 10 über die gültigen Pixel, wie `eo:cloud_cover` (§6.6, §6.7). Ohne gültiges Pixel gibt es keinen Wert.
  - **Überflug:** Der Wert einer Gruppe kommt aus den Zählungen ihrer Szenen (§6.8).
  - **Schnitt:** DS-03a Backend in dieser Session, DS-03b Frontend nach DS-02c (§6.14, §6.17).
- **Neu vorgelegt (Frage 2, Option 2):** Der Filter `earthx:aoi_cloud_cover` steht in `query_by_collection` der Suche (die Reservierung aus DS-02). `api` nimmt ihn heraus und fragt die Quelle mit den übrigen Filtern seitenweise. Dann misst `api` jede Szene in der AOI und gibt nur passende zurück, jede mit ihrem Wert.
  - Eine Antwort prüft höchstens 100 Szenen oder 8 s lang und meldet „found / checked“.
  - Die Seitenmarke setzt dort fort; nach 500 geprüften Szenen endet die Suche mit Hinweis.
  - Gemessen kostet das mit 6 Lesern je Prozess rund 6–9 s je 100 Szenen, für 500 Szenen also rund 30–45 s ohne Cache [M, A].
- **Empfehlungen zu den neuen Punkten** (Fragen in §6.15):
  - Obergrenze 500 je Suche, über „Load more“ hinweg (F2a).
  - Keine Höchstlänge des Zeitraums, weil schon ein Jahr bei mittleren AOIs 300–600 Szenen hat [M] (F2b).
  - Fortschritt über kurze Antworten mit Seitenmarke statt einer langen Anfrage (F2c).
  - Lesen im `api`-Prozess mit höchstens 6 gleichzeitigen Lesern je Host und Prozess, der Grenze von `gateway` (F2d).
  - DS-03a in zwei PRs (F7).

### 6.1 Stand im Code [P]

- **Klassifizierung:** `DatasetConfig.mask` (`MaskSource`, M4-18) nennt Asset `scl`, alle Klassen mit Namen, die Vorauswahl für `mask` ({3, 8, 9, 10}) und Quelle; veröffentlicht als `earthx:mask`. Der DEM hat `mask=None`.
- **Suchfilter (DS-02a/b):** `search_filters` je Datensatz, `query`/`query_by_collection` nur mit Eigenschaften der Registry, internes Modell `FilterConditions`, Earth Search übersetzt in die Query-Extension. `earthx:`-Eigenschaften sind für Filter reserviert, die die Plattform rechnet, und heute `400` (`adr/0021` §2.7, DS-02 §6.9). Die Fingerabdrücke nehmen Bedingungen nur auf, wenn welche gesetzt sind. Die Coverage nimmt dieselben Bedingungen (DS-02b); die Oberfläche „Advanced search“ (DS-02c) gibt es noch nicht.
- **Seiten:** höchstens 100 Items je Seite (`MAX_LIMIT`). Die Seitenmarke ist unsere eigene (`TOKEN_VERSION` 2: Datensatz, Fingerabdruck, Marke der Quelle). Earth Search blättert über den Sortierschlüssel des letzten Items (`next`). Seiten der Quelle liegen im Such-Cache: 24 h für abgeschlossene Zeiträume, 5 min am offenen Rand.
- **Gemischte Suche (M3-13):** Mehrere Datensätze gehen in einer Anfrage an alle Quellen parallel, je mit einem Anteil des `limit`. Jede föderierte Quelle hat je Seite höchstens `SOURCE_TIMEOUT_S` = 10 s.
- **Frontend:** `runSearch` sucht alle gewählten Datensätze in einer Anfrage und läuft die Seiten (zu 100) bis 300 Treffer durch (`searchAllPages`, `MAX_SEARCH_ITEMS`); „Load more“ setzt mit der Marke fort. Ohne Treffer sucht der Datums-Fallback (±90 Tage) mit derselben Anfrage. Eine AOI mit mehr als 1 000 Positionen geht als `bbox` statt `intersects` (M3-08 F2a).
- **Vorbild NM4-19:** `POST /collections/{dataset}/statistics` liest Raster im `tiler`. Die AOI steht nur im Body. Gespeichert wird im Statistik-Cache (`earthx_stats_cache`, Schlüssel SHA-256, nie geloggt, 7 Tage, abgeräumt von `jobs/cleanup.py`). Die Route schreibt eine Logzeile ohne AOI, Item oder Schlüssel; einen Fehler von GDAL loggt sie nur mit seiner Art.
- **`gateway`:** höchstens 6 Verbindungen je Host (`Policy.max_connections_per_host`, `adr/0005` §6), aber nur für den eigenen HTTP-Client. Für GDAL prüft `gateway` die Adresse (`check_url`, `vsicurl_path`) und setzt die Optionen; gleichzeitige GDAL-Leser begrenzt heute nur der Thread-Pool des Prozesses.
- **Prozesse:** `/stac/search` läuft im Prozess `api`, Raster liest bisher nur `tiler` (und `worker`). Ein Image, also GDAL und rasterio auch im `api`.

### 6.2 Messungen [M]

Earth Search v1, `sentinel-2-c1-l2a`, 48 Szenen aus sechs Regionen und Jahreszeiten (Alpen Sommer, Amazonas Regenzeit, Sahara, Norwegen Schnee, Küste Portugal Herbst, Ganges Monsun), je Region über den Wolkenanteil der Szene von 0 bis 100 % verteilt. GDAL wie `gateway.gdal_options` (HTTP/2, Multirange); Bytes und Anfragen aus dem GDAL-Debug-Log. Die Messung lief aus der Cloud-Sitzung über einen Proxy; aus einem Rechenzentrum in Europa sind die Zeiten eher kürzer.

**6.2.1 Aufbau der SCL-Datei:** 0,13–4,85 MB je Szene (Median 1,2 MB), COG, `uint8`, 5490 × 5490 Pixel zu 20 m, Blöcke 512², Deflate mit Prädiktor, `nodata` 0, Übersichten 2, 4, 8, 16, Tag `OVR_RESAMPLING_ALG=MODE` (je Block die häufigste Klasse). Die Recherche fand dazu keine Dokumentation von Element 84 [S]; gemessen am Objekt.

**6.2.2 Zeit und Bytes je Szene, kalt, nacheinander** (16 Szenen, kreisförmige AOI in der Mitte der Kachel; Median, in Klammern 90. Perzentil bzw. Maximum; Lauf vom 29.10.2026 mit `scripts/ds-03-clouds/measure.py`):

| AOI-Durchmesser | Stufe | Zeit | Bytes | Anfragen | Pixel in der AOI |
|---|---|---|---|---|---|
| 1 km | 20 m | 0,50 s (0,59) | 64 KB (64) | 4 | 1 968 |
| 10 km | 20 m | 0,46 s (0,63) | 59 KB (126) | 5 | 196 060 |
| 10 km | 80 m | 0,42 s (0,46) | 48 KB (96) | 4 | 12 281 |
| 30 km | 20 m | 0,79 s (0,92) | 144 KB (448) | 7 | 1 764 344 |
| 30 km | 160 m | 0,45 s (0,47) | 49 KB (84) | 5 | 27 621 |
| 110 km (ganze Kachel) | 20 m | 0,72 s (0,88) | 907 KB (2 708) | 4 | 23 633 820 |
| 110 km | 320 m | 0,33 s (0,35) | 32 KB (32) | 3 | 92 776 |

Öffnen allein (Größe und Kopf): 0,32 s im Median. Die vollständige Tabelle (vier Größen × fünf Stufen) liegt im Messanhang §6.16. Ein Lauf am Vortag mit demselben Verfahren ergab dieselben Bytes und Zeiten im selben Bereich, bis auf die ganze Kachel bei 20 m (1,62 s statt 0,72 s); die Zeiten schwanken mit dem Netz.

**6.2.3 Viele Szenen** (48 Szenen, Leser parallel in Threads, Lauf vom 29.10.2026):

| AOI | Stufe | parallel | Dauer | Bytes gesamt | je 100 Szenen [A] |
|---|---|---|---|---|---|
| 10 km | 20 m | 1 | 25,6 s | 3,2 MB | 53 s |
| 10 km | 20 m | 6 | 5,1 s | 3,2 MB | 11 s |
| 10 km | 20 m | 8 | 3,9 s | 3,2 MB | 8 s |
| 10 km | 20 m | 16 | 2,6 s | 3,2 MB | 5 s |
| 10 km | 80 m (Frage 1) | 6 | 3,8 s | 2,5 MB | 8 s |
| 30 km | 20 m | 6 | 5,3 s | 8,4 MB | 11 s |
| 30 km | 160 m (Frage 1) | 6 | 4,3 s | 2,4 MB | 9 s |
| 110 km | 20 m | 6 | 7,1 s | 47,7 MB | 15 s |
| 110 km | 320 m (Frage 1) | 6 | 3,1 s | 1,6 MB | 6 s |

Mit der Stufe nach Frage 1 und 6 Lesern kosten 100 Szenen also 6–9 s, 500 Szenen 30–45 s, ohne Cache und ohne die Seitenabrufe der Quelle (eine Seite je 100 Items).

**6.2.4 Genauigkeit gegen volle Auflösung:** 1 440 AOIs (Kreise mit 1, 3, 10, 30, 100 km Durchmesser, je Szene sechs zufällig gelegt, mindestens 10 % gültige Pixel), Anteil der Klassen 8, 9, 10 an den gültigen Pixeln, Maske über Pixelmitten. Fehler in Prozentpunkten gegen 20 m; nur die 516 AOIs mit gemischtem Himmel (Bezug zwischen 1 und 99 %), denn ganz klare oder ganz bedeckte AOIs treffen jede Stufe genau. Median / 95. Perzentil / Maximum:

| AOI | 40 m | 80 m | 160 m | 320 m |
|---|---|---|---|---|
| 1 km | 0,4 / 1,1 / 1,7 | 1,0 / 3,9 / 6,1 | 2,6 / 8,1 / 13,3 | 7,1 / 21,6 / 26,0 |
| 3 km | 0,1 / 0,3 / 0,4 | 0,2 / 1,1 / 2,0 | 0,7 / 3,4 / 5,3 | 2,2 / 8,2 / 12,0 |
| 10 km | 0,0 / 0,1 / 0,2 | 0,2 / 0,8 / 1,1 | 0,4 / 1,4 / 2,6 | 0,8 / 2,9 / 4,8 |
| 30 km | 0,0 / 0,1 / 0,1 | 0,1 / 0,5 / 0,7 | 0,2 / 1,3 / 1,8 | 0,6 / 2,8 / 3,7 |
| 100 km | 0,0 / 0,1 / 0,1 | 0,1 / 0,4 / 0,5 | 0,2 / 0,8 / 1,1 | 0,2 / 1,7 / 1,9 |

Nach der Zahl der Pixel, die die AOI auf der gelesenen Stufe hat (alle Stufen zusammen, gemischter Himmel):

| Pixel in der AOI | Fälle | `MODE`-Übersicht | zum Vergleich: jedes k-te Pixel |
|---|---|---|---|
| unter 100 | 164 | 3,2 / 15,4 / 26,0 | 3,0 / 14,2 / 33,5 |
| 100–1 000 | 266 | 0,7 / 3,1 / 6,1 | 0,7 / 3,2 / 6,6 |
| 1 000–10 000 | 368 | 0,3 / 1,8 / 3,7 | 0,2 / 0,9 / 2,0 |
| 10 000–100 000 | 500 | 0,1 / 1,1 / 1,9 | 0,1 / 0,3 / 0,5 |
| über 100 000 | 766 | 0,0 / 0,5 / 1,1 | 0,0 / 0,1 / 0,2 |

- `MODE` verzerrt im Mittel kaum (+0,01 bis +0,22 Prozentpunkte, bei 320 m −0,26), streut aber je AOI mehr als jedes k-te Pixel, weil kleine Wolken und Lücken in der Mehrheit ihres Blocks verschwinden [M, A]. Jedes k-te Pixel wäre genauer, spart aber keine Bytes: GDAL muss dafür die Blöcke der vollen Auflösung laden [A].
- Mit den Klassen 3, 8, 9, 10 (mit Schatten) sind die Fehler fast gleich.

**6.2.5 Szene und AOI:**
- Anteil der Klassen 8, 9, 10 an den Pixeln mit SCL ≠ 0 über die ganze Datei = `eo:cloud_cover` des Items, bei 48 von 48 Szenen auf drei Nachkommastellen. Mit Schatten (3) wären es im Median 0,2, höchstens 13,2 Prozentpunkte mehr. Klasse 1 (gesättigt oder defekt) kam in keiner der 48 Szenen vor.
- Abstand zwischen AOI und Szene, Klassen 8, 9, 10: AOI 1 km im Median 4,2 Prozentpunkte, bei 28 % der AOIs über 20; 10 km 4,1 bzw. 22 %; 30 km 3,0 bzw. 19 %.

**6.2.6 Maske einer langen AOI** (offline, `measure.py rasterize`): Welliger Kreis von 30 km, Maske über Pixelmitten, je Aufruf:

| Positionen | 20 m (2,7 Mi Pixel) | 160 m (43 000 Pixel) |
|---|---|---|
| 64 | 22 ms | 10 ms |
| 1 000 | 15 ms | 11 ms |
| 20 000 | 49 ms | 19 ms |

### 6.3 Stand der Technik

- **Rechenweg:** Sentinel Hub und Copernicus Data Space rechnen den Wolkenanteil einer AOI mit der Statistical API: SCL je Pixel auf 0/1 abbilden, `dataMask` auf SCL ≠ 0, Mittelwert über die AOI, auf 20 m [S: [CDSE-Forum](https://forum.dataspace.copernicus.eu/t/cloud-percentage/438), [Planet-Community](https://community.planet.com/analysis-apis-81/statistical-api-creating-a-cloud-free-datamask-5760)]. Das ist der hier vorgeschlagene Weg. Bei Sentinel Hubs Wolkenmaske mit 160 m gibt es bei kleinen AOIs nur 0 oder 100 % ([Forum](https://community.planet.com/sentinel-hub-81/cloud-coverage-is-always-100-4218), [S]); das deckt sich mit §6.2.4.
- **Klassen:** kein Konsens. Häufig 3, 8, 9, 10 [S]; Sentinel Hubs Skript „cloud statistics“ nennt 1, 3, 8, 9, 10 [S: [custom-scripts](https://custom-scripts.sentinel-hub.com/sentinel-2/cloud_statistics)]. `eo:cloud_cover` zählt 8, 9, 10 ohne Schatten (§6.2.5 [M]); die STAC-EO-Extension verlangt für `eo:cloud_cover` eine Schätzung in Prozent ohne No-Data ([P: stac-extensions/eo](https://github.com/stac-extensions/eo)).
- **Andere Werkzeuge:** Google Earth Engine empfiehlt für Wolken die eigenen Masken (s2cloudless, Cloud Score+) statt SCL [S]; odc-stac und Planetary Computer zeigen SCL nur an, ohne AOI-Statistik [S]. Eine STAC-Erweiterung für „Wolken in der AOI“ wurde nicht gefunden [S].
- **Grenzen von SCL** (alle [S]): Baetens et al. 2019 ([Remote Sensing 11(4) 433](https://www.mdpi.com/2072-4292/11/4/433)): Gesamtgenauigkeit Sen2Cor 84 % (MAJA 91 %, Fmask 90 %), helle Flächen und Gebäude werden zu Wolken, im Gebirge bei trockener Luft wird Cirrus gemeldet. ESA-Validierung der Collection 1: 94 % ohne, 78 % mit Schnee; Cirrus über Schnee wird oft Schnee, Schatten auf Schnee oft klar. Zekoll et al. 2021 ([Remote Sensing 13(1) 137](https://www.mdpi.com/2072-4292/13/1/137)): Cirrus und Schatten mit hoher Präzision, aber geringer Trefferquote, also eher unterschätzt. CMIX (Skakun et al. 2022, RSE 274): Sentinel-2-Masken 80–89 % je Referenz, dünne Wolken am unsichersten.
- **Folgen für den Tooltip** [A]: dünne Zirren können fehlen, Schnee und helle Flächen als Wolke zählen; Schatten zählen nicht mit (bei K1, §6.6).

### 6.4 Rechenstufe (Frage 1, entschieden: Option 1)

Je Szene die gröbste Übersicht, auf der die AOI noch mindestens 10 000 Pixel hat, sonst 20 m. Die Stufe ergibt sich aus der Fläche der AOI im Raster der Szene, vor dem Lesen; die Rechnung folgt `processing.core.area_factor`, gerundet auf die vorhandenen Übersichten. Das ergibt bei AOIs von 1–3 km 20 m, ab etwa 10 km 80 m und bei ganzen Kacheln 320 m. Fehler bei gemischtem Himmel im 95. Perzentil höchstens 1,1, im Maximum 1,9 Prozentpunkte (§6.2.4). Jede Szene meldet ihre Stufe (`resolution` in m); der Tooltip nennt sie nicht.

### 6.5 Schnittstelle (Frage 2, entschieden: Option 2, Ausgestaltung neu vorgelegt)

**Form auf der Leitung [A]:** Der Filter ist die Eigenschaft `earthx:aoi_cloud_cover` mit `gte`/`lte` in Prozent (0–100), in derselben Form wie die übrigen Filter (DS-02 §6.4).
- Er steht in `query_by_collection` (das sendet das Frontend) oder in `query` (STAC-Clients); dort gilt er nur für Collections, die ihn kennen, die übrigen nennt `ignored_filters_by_collection`.
- „Within AOI“ in der Oberfläche heißt: Das Frontend sendet den Bereich des Wolkenfilters unter `earthx:aoi_cloud_cover` statt unter `eo:cloud_cover`. Beide zugleich bleiben für STAC-Clients erlaubt (Szene vorab, dann AOI).
- Wie heute nur `POST`; `GET` weist `query` ab.

**Bedingungen, sonst `400` mit eigenem Text ohne Werte:**
1. Ein Zeitraum mit beiden Enden (`datetime` „von/bis“, kein offenes Ende), wie von Otto verlangt.
2. Eine Fläche für die Messung (KE1, geändert am 29.10.2026):
   - `intersects` als `Polygon` oder `MultiPolygon`, oder `bbox`.
   - Schickt die Suche das umgebende Rechteck, weil die AOI mehr als 1 000 Positionen hat (M3-08), dann trägt der Body die AOI zusätzlich als `earthx:aoi`. Erlaubt ist `Polygon` oder `MultiPolygon` mit höchstens 20 000 Positionen, wie beim Hochladen; der ganze Body ist höchstens 1 MB groß.
   - `earthx:aoi` dient nur der Messung, geht nie an die Quelle und erscheint nie im Log. Sie muss innerhalb von `bbox` liegen.
   - Ohne Fläche, oder mit Punkt bzw. Linie: `400` („the cloud share in the AOI needs an area“).
3. Die Collection hat den Filter in der Registry (§6.10); sonst `400` in `query_by_collection`, wie jede unbekannte Eigenschaft (DS-02 §6.4 Regel 3a).
4. Grenzen wie bei jedem `RANGE`-Filter: Zahl, 0 ≤ `gte` ≤ `lte` ≤ 100.

**Ablauf je Quelle [A]:**
1. `api` nimmt `earthx:aoi_cloud_cover` aus den Bedingungen (DS-02 §6.9). Die übrigen Filter, AOI und Zeitraum gehen wie bisher an die Quelle (der Szenenfilter wirkt vorab).
2. `api` holt Seiten der Quelle zu 100 Items, mit dem bestehenden Such-Cache.
3. Für jedes Item in der Reihenfolge der Quelle: Wert aus dem Cache (§6.9 F2e), sonst messen (§6.4). Gemessen werden höchstens 6 Szenen gleichzeitig je Prozess (§6.9 F2d). Ein Item passt, wenn es einen Wert hat und der Wert im Bereich liegt.
4. Die Antwort endet, sobald eines eintritt: `limit` passende Items; 100 geprüfte Szenen in dieser Antwort; 8 s Messzeit in dieser Antwort; 500 geprüfte Szenen in der ganzen Suche (F2a); die Quelle hat nichts mehr.
   - Die 8 s liegen unter dem Budget der gemischten Suche von 10 s je Quelle (§6.1).
   - Eine Antwort kann daher weniger als `limit` Items und sogar keines tragen; STAC erlaubt das.
5. Die Seitenmarke zeigt auf die Stelle in der Seite der Quelle, an der die nächste Antwort weiterprüft (F2c).

**Antwort:**
- **Je Item** in `properties`:
  - `earthx:aoi_cloud_cover`: Anteil in Prozent, eine Nachkommastelle, gleich gebaut wie `eo:cloud_cover`.
  - `earthx:aoi_measure`: `{"data_percent", "cloud_pixels", "data_pixels", "resolution"}`. Die Pixelzahlen braucht der Gruppenwert (§6.8), `data_percent` der Tooltip (§6.7).
- **Je Antwort** `earthx:aoi_filter` (bei gemischter Suche `earthx:aoi_filter_by_collection`):
  - `checked` und `found`: Zählungen über die ganze Suche bis hierher.
  - `unreadable`: Szenen, die sich nicht lesen ließen.
  - `limit_reached`: `true`, wenn die Obergrenze erreicht ist.
- Keine AOI, kein Schlüssel; Fehlertexte von GDAL und Quelle weder in der Antwort noch im Log (DS-02 C).

**Ausgeschlossen:**
- Szenen ohne gültiges Pixel in der AOI (§6.7).
- Szenen, die sich nicht lesen lassen: gezählt in `unreadable`, Hinweis „2 scenes could not be checked“ (KE5).

**Coverage-Karte:** Sie kann den Filter nicht anwenden (sie zählt bei der Quelle, ohne Raster). Mit „Within AOI“ bekommt die Coverage den Wolkenfilter deshalb nicht mehr, nur die übrigen Filter (KE6).

### 6.6 Wolkenklassen (Frage 3, entschieden: Option 1)

Klassen 8, 9, 10 als `MaskSource.cloud_classes` (§6.10), dieselbe Definition wie `eo:cloud_cover` (§6.2.5). Schatten zählen nicht mit; das sagt der Tooltip ausdrücklich (§6.11).

### 6.7 No data (Frage 4, entschieden: Option 1)

- **Nenner:** gültige Pixel in der AOI (SCL ≠ 0, der `nodata`-Wert der Datei). Klasse 1 zählt im Nenner und nicht als Wolke, wie bei `eo:cloud_cover`.
- **Datenanteil:** `data_percent` = gültige Pixel / Pixel der AOI. Teile der AOI außerhalb der Kachel zählen als ohne Daten.
- **Ohne gültiges Pixel** gibt es keinen Wert. Mit gesetztem Filter fällt eine solche Szene heraus, sie zeigt die AOI nicht.

### 6.8 Szene und Überflug (Frage 5, entschieden: Option 1)

Gruppenwert = Summe der Wolkenpixel / Summe der gültigen Pixel der Szenen einer Gruppe, aus `earthx:aoi_measure`. Die Überlappung benachbarter Kacheln zählt doppelt; beide stammen aus demselben Überflug. Die Sortierung „Clouds in AOI“ ordnet Gruppen; innerhalb einer Gruppe bleibt die Reihenfolge. Der Filter wirkt auf Szenen (Server), eine Gruppe ohne passende Szene erscheint nicht.

### 6.9 Obergrenze, Zeitraum, Fortschritt, Seitenmarken, Cache, mehrere Datensätze, Last

**F2a Obergrenze geprüfter Szenen:**

| | Grenze | Für / Gegen |
|---|---|---|
| **1** | 500 je Suche, über „Load more“ hinweg | feste Kosten je Suche (~30–45 s ohne Cache [M, A]); danach keine Marke mehr, Hinweis „Checked 500 scenes. Narrow the date range to search further.“ |
| 2 | 500 je Schritt: jedes „Load more“ prüft weitere 500 | mehr erreichbar; Kosten je Suche offen |
| 3 | 200 je Suche | schneller (~12–18 s), reicht bei kleinen AOIs für 1–3 Jahre, bei mittleren für 4–8 Monate |

**Empfehlung 1.** Erreicht die Suche die Grenze, bleibt „Load more“ aus (ausgeblendet, nicht ausgegraut).

**F2b Höchstlänge des Zeitraums [M]:** Szenen im Jahr 2024 bei Earth Search:
- kleine AOI (2 × 2 km), sieben Orte: 74–201;
- mittlere AOI (30–45 km) über mehrere Kacheln: 298–612;
- große AOI (rund 100 km): 531.

| | Regel | Für / Gegen |
|---|---|---|
| **1** | keine Höchstlänge; die Obergrenze begrenzt die Kosten | bei kleinen AOIs reichen 500 Szenen für 2,5–7 Jahre; ein Jahr läge bei mittleren AOIs schon über der Grenze, eine Höchstlänge begrenzt die Kosten also nicht |
| 2 | höchstens ein Jahr | einfache Regel; bei mittleren AOIs trotzdem an der Grenze, bei kleinen AOIs unnötig eng |

**Empfehlung 1.** Die Quelle sortiert nach Datum absteigend (`SORTBY`); bei Erreichen der Grenze sind also die jüngsten 500 Szenen geprüft, und der Hinweis nennt, wie weit die Suche zurückreicht („Checked 500 scenes back to 12 Mar 2025“).

**F2c Fortschritt und Seitenmarken:**

| | Weg | Für / Gegen |
|---|---|---|
| **1** | kurze Antworten (höchstens 100 geprüfte Szenen oder 8 s); die Marke trägt die Stelle in der Seite der Quelle und die Zähler; das Frontend fragt weiter und zeigt nach jeder Antwort „found / checked“ | kein neuer Übertragungsweg; passt in das Budget der gemischten Suche; „Load more“ bleibt die Marke |
| 2 | eine Anfrage bis `limit` oder Grenze, Fortschritt über SSE oder eine zweite Route | eine Anfrage bis rund 40 s, länger als das Budget der gemischten Suche; Zustand der Messung zwischen zwei Routen im Server |
| 3 | gestreamte Antwort (NDJSON) | kein STAC-Format; Proxy und Client müssen streamen |

**Empfehlung 1.** Einzelheiten:
- **Marke:** Bei gesetztem AOI-Filter trägt sie zusätzlich die Stelle in der Seite der Quelle (`i`) und die Zähler (`c` geprüft, `f` gefunden, `u` unlesbar). Ohne AOI-Filter bleibt sie wie heute; `TOKEN_VERSION` bleibt 2.
  - Die Seite der Quelle wird beim Fortsetzen erneut geholt, aus dem Such-Cache, und ab `i` geprüft.
  - Der Fingerabdruck nimmt den AOI-Filter auf (DS-02: Bedingungen gehen ein, wenn gesetzt).
- **Gemischte Suche:** Die Marke je Quelle trägt dasselbe.
- **Frontend:** Es läuft wie heute Seite für Seite (`searchAllPages`) bis 300 gefundene Szenen, bis zur Grenze oder bis die Quelle leer ist. Nach jeder Antwort steht im Kopf der Trefferliste „12 found / 180 checked“. „Load more“ setzt fort; der Zähler läuft über die ganze Suche weiter.
- **Datums-Fallback:** Mit „Within AOI“ sucht der Fallback (±90 Tage) nicht. Ohne Treffer steht „No scenes within the AOI limit in this date range“ (KE4).

**F2d Last auf die Quelle und Ort der Messung:**
- **Ort:** Gemessen wird im Prozess `api`, der die Suche beantwortet, über `access` (Zugriffsauflösung, von `gateway` geprüfte Adresse, GDAL-Optionen aus `gateway`).
  - Ein Aufruf des `tiler` aus `api` wäre eine interne API mit eigener Last und Fehlern.
  - Die CPU-Last ist klein: Nach der Stufenwahl aus Frage 1 liest eine Szene meist unter 100 KB und höchstens rund 100 000 Pixel [M, A].

| | Grenze gleichzeitiger Leser | Für / Gegen |
|---|---|---|
| **1** | je Prozess und Host höchstens 6 (= `Policy.max_connections_per_host`), geteilt von allen Suchen des Prozesses; neu in `gateway` als Zähler für GDAL-Leser (`gateway.read_slot(host)`) | dieselbe Grenze wie für den eigenen Client (`adr/0005` §6); Last auf den Bucket bleibt je Prozess fest, egal wie viele Nutzer suchen |
| 2 | je Anfrage 6 | einfacher; bei n gleichzeitigen Suchen n × 6 Leser |
| 3 | über alle Prozesse (Datenbank oder Proxy) | erst mit dem Egress-Proxy in M6 sinnvoll |

**Empfehlung 1.** Gemessen [M]: Eine Szene sind 3–7 Bereichsanfragen an den Bucket der Quelle, 500 Szenen also rund 2 000. Die STAC-API der Quelle sieht dazu 5 Seitenabrufe; volle Seiten kommen bei der Fortsetzung aus dem Such-Cache.
- 48 Szenen, 10-km-AOI, 20 m: 1 Leser 25,6 s, 6 Leser 5,1 s, 8 Leser 3,9 s, 16 Leser 2,6 s.
- Mit der Stufe nach Frage 1 (80 m bei 10 km) und 6 Lesern: 3,8 s.
- Wartet eine Suche auf einen freien Platz, zählt die Wartezeit in die 8 s der Antwort; eine volle Last macht Antworten kürzer, nicht länger.

**F2e Cache der Messung:** je Szene und AOI im Statistik-Cache, wie NM4-19.
- **Schlüssel:** SHA-256 über `{"kind": "aoi-clouds/v1", "earthx": <Version>, "dataset", "item", "asset", "classes", "aoi"}`, AOI kanonisch; `bbox` als Polygon.
- **Inhalt:** nur die Zahlen aus `earthx:aoi_measure`.
- **Lebensdauer:** höchstens 7 Tage, weil der Schlüssel aus der AOI rückrechenbar und damit personenbezogen ist. Abgeräumt vom bestehenden Aufräumer (`jobs/cleanup.py`).
- **Nie** in Log, URL oder Antwort.
- Gefilterte Antwortseiten werden **nicht** im Such-Cache gespeichert, nur die Messungen je Szene. Die Seiten der Quelle bleiben dort wie heute.
- Eine Wiederholung derselben Suche kostet damit je Szene eine Datenbankabfrage statt einer Messung.

**F2f Mehrere Datensätze:**
- Filter je Datensatz wie in DS-02: `earthx:aoi_cloud_cover` steht in `query_by_collection` nur bei Datensätzen, deren Registry ihn anbietet; bei anderen ist er `400`.
- In der gemischten Suche misst nur die Quelle mit dem Filter; die anderen antworten wie bisher. Die Quelle mit Filter liefert je Seite weniger Items, bleibt aber offen, bis ihre Marke endet.
- Die Obergrenze gilt je Datensatz, der Fortschritt steht je Datensatz in `earthx:aoi_filter_by_collection`.
- Der DEM hat keinen Wolkenfilter, also kein „Within AOI“.

**Kleinentscheidungen** (gelten, sofern Otto nicht widerspricht):
- **KE1 Lange AOI (geändert, Otto 29.10.2026):** Eine AOI mit mehr als 1 000 Positionen geht an die Quelle weiter als `bbox` (§6.1).
  - Gemessen wird trotzdem das echte Polygon; es steht als `earthx:aoi` im Body (§6.5).
  - Vereinfachen ist bis 20 000 Positionen nicht nötig: Die Maske kostet auch dann höchstens 50 ms bei 2,7 Mi Pixeln zu 20 m und 19 ms bei 160 m [M, §6.2.6].
  - Darüber nimmt der Body nichts an. Sollte die Grenze steigen, wird mit einer Toleranz unter einem halben Pixel der gelesenen Stufe vereinfacht.
  - Eine Punkt-AOI sperrt den Schalter („Draw an area to use this filter“).
- **KE2 Grenzen im Code:** 100 Szenen und 8 s je Antwort, 500 je Suche, 6 Leser je Host und Prozess. Konstanten mit Verweis auf diesen Plan, keine Konfiguration.
- **KE3 Log:** eine Zeile je Antwort „aoi cloud filter“ mit Datensatz, geprüft, gefunden, aus dem Cache, unlesbar, Grenze erreicht, Stufen, Sekunden. Keine AOI, Kennung, Grenzwerte, kein Schlüssel und keine Adresse. Das Zugriffslog nennt wie bisher nur Methode, Pfad und Status.
- **KE4 Datums-Fallback:** aus bei „Within AOI“ (F2c).
- **KE5 Unlesbare Szene:** fällt heraus, wird gezählt und im Hinweis genannt. Ein Fehler der Quelle beim Seitenabruf bricht die Antwort ab wie heute.
- **KE6 Coverage:** ohne den AOI-Filter (§6.5). Der Tooltip von „Within AOI“ sagt „The coverage map shows the scene filter only.“

### 6.10 Registry

- **`MaskSource`** bekommt zwei Felder, ohne Vorgabewert (B10):
  - `cloud_classes: frozenset[int]`: Klassen, die als Wolke zählen; leer heißt kein Wert in der AOI.
  - `cloud_note: str`: Satz zu den Grenzen der Klassifizierung, englisch, für den Tooltip.
- **`SearchFilter`** bekommt `within_aoi: bool`. Er ist an genau dem Filter `True`, dessen Bereich auch für die AOI gelten kann; bei Sentinel-2 an `eo:cloud_cover`.
- **Prüfungen beim Start (`ConfigError`):**
  - `cloud_classes` ⊆ `classes`, ohne den `nodata`-Wert. Ist es nicht leer, ist `cloud_note` nicht leer.
  - `within_aoi` an höchstens einem Filter je Datensatz, nur an einem `RANGE` 0–100 mit Einheit `%`, und nur, wenn `cloud_classes` nicht leer ist.
- **Sentinel-2:**
  - `cloud_classes={8, 9, 10}`.
  - `cloud_note` „Sen2Cor's classification can miss thin cirrus and can take snow or bright ground for clouds.“
  - `within_aoi=True` an „Cloud cover“.
- **Veröffentlicht:**
  - in `earthx:mask` als `cloud_classes` (aufsteigend) und `cloud_note`;
  - in `earthx:search_filters` als `within_aoi` am Filter.
- **Frontend:** Es zeigt den Schalter nur dort, wo `within_aoi` gesetzt ist; beim DEM erscheint er nicht.
- Ein neuer Datensatz mit Klassifizierung braucht keinen Code, nur diese Daten.

### 6.11 Oberfläche (englisch; Umsetzung DS-03b, §6.17)

- **Schalter:** In „Advanced search“ unter dem Filter „Cloud cover“ ein Schalter „Within AOI“. Der Bereich darüber bleibt derselbe.
  - **Tooltip:** „Limit applies to clouds inside the AOI (classes 8, 9, 10; cloud shadows do not count), measured on each scene. Slower: checks up to 500 scenes.“, dazu `cloud_note`.
  - **Gesperrt** mit Grund im Tooltip:
    - ohne AOI oder ohne Zeitraum: „Draw an AOI and set a date range first“;
    - bei Punkt-AOI und zu vielen Positionen: KE1.
- **Fortschritt:** Im Kopf der Trefferliste des Datensatzes steht während der Suche „12 found / 180 checked“, danach „12 found / 500 checked“.
  - Hinweis bei der Grenze, wie die übrigen Hinweise des Abschnitts: „Checked 500 scenes back to 12 Mar 2025. Narrow the date range to search further.“
  - „Load more“ erscheint nur, solange es weitergeht.
- **Zeile:** neben der Uhrzeit „☁ 3 %“ (ganze Prozent, „<1 %“ unter 1).
  - **Tooltip:** „Clouds in AOI: 3 % of the AOI's valid pixels (classes 8, 9, 10; shadows not counted). Measured on 64 % of the AOI.“
- **Gruppe:** derselbe Wert im Kopf (§6.8).
- **Sortierung:** „Sort: Date | Clouds in AOI“ in der Trefferliste, nur bei aktivem „Within AOI“.
- Hell/Dunkel über die vorhandenen Farbtoken; schmales Fenster wie die übrige Trefferliste.

### 6.12 Module und Prozesse [P, A]

- **`access/aoi_clouds.py` (neu):**
  - öffnet ein Klassifizierungs-Asset über die bestehende Zugriffsauflösung;
  - wählt die Stufe (§6.4);
  - zählt Wolken- und gültige Pixel in der AOI (Pixelmitten, wie die Maske des Jobs).
  - `access` darf `readers` und `catalog`; kein neuer Import.
- **`gateway`:** `read_slot(host)`, ein Zähler je Host für GDAL-Leser mit der Grenze aus `Policy` (F2d). Nichts Fachliches.
- **`api`:**
  - liest `earthx:aoi_cloud_cover` in `search_filters.py`;
  - führt die Prüfschleife, Marke und Zähler in `federating_client.py` bzw. einem neuen `api/aoi_cloud_filter.py`;
  - Cache, Log.
  - `api` darf alles außer `datasets`.
- **`adapters`:** unverändert bis auf die Marke, falls sie dort gebaut wird (Entscheidung bei der Umsetzung, ohne neue Importregel).
- Der Worker-Kern (`processing`) bleibt unberührt.
- `.importlinter` bleibt unverändert; `lint-imports` muss ohne Lockerung grün sein. Bräuchte es eine Lockerung, wäre das zuerst eine Frage an Otto.

### 6.13 Tests und Abnahme DS-03a

- **Rechnung gegen unabhängige Rechnung:**
  - synthetische COGs, im Test erzeugt, mit `MODE`-Übersichten und Klassen in bekannten Mustern;
  - der Anteil gegen eine Zählung mit `numpy` direkt aus dem Muster, für 20 m und eine Übersicht;
  - Sonderfälle: AOI teilweise außerhalb der Kachel, `MultiPolygon`, `bbox`, AOI ganz ohne Daten (kein Wert, fällt heraus), Klasse 1 im Nenner.
- **Stufenwahl:** Grenzfälle um 10 000 Pixel.
- **Suche** (Quelle über `tests/fixtures`, Raster synthetisch):
  - nur passende Items, jedes mit `earthx:aoi_cloud_cover`;
  - übrige Filter gehen an die Quelle, `earthx:` nie;
  - Fortsetzen mit der Marke in der Mitte einer Seite der Quelle, ohne Lücke und ohne Doppel;
  - Zähler über mehrere Antworten;
  - Ende bei 100 Szenen, bei 8 s (Uhr im Test), bei 500 je Suche (dann keine Marke) und am Ende der Quelle;
  - gemischte Suche mit DEM: nur Sentinel-2 wird gemessen, Budget eingehalten;
  - Fingerabdruck ohne AOI-Filter unverändert.
- **Fehlbedienung → `400` ohne Werte im Text:**
  - ohne Zeitraum, mit offenem Ende;
  - ohne Fläche, mit Punkt;
  - Bereich verletzt;
  - Datensatz ohne Filter;
  - `GET` mit `query`;
  - `/coverage` mit `earthx:`.
- **AOI nie in Log oder URL:**
  - Logzeilen und Zugriffslog nach Koordinaten, Kennungen und Schlüssel durchsucht (wie NM4-19);
  - ein Cache, der mit dem Schlüssel im Text wirft;
  - die Marke enthält keine AOI.
- **Teilfehler:** eine unlesbare Szene (gezählt, nicht zurückgegeben); ein Fehlertext der Quelle mit Interna erscheint weder in Antwort noch Log.
- **Last:** nie mehr als 6 gleichzeitige Leser je Host, auch bei zwei Suchen zugleich.
- **Registry:** jede Prüfung aus §6.10; Collection trägt `cloud_classes`, `cloud_note`, `within_aoi`.
- **Cache:** gleiche Szene und AOI aus dem Cache; Lebensdauer 7 Tage; Aufräumer löscht.
- **Live (`backend/tests_live/`, lokal):** eine echte Szene, Anteil der ganzen Datei gleich `eo:cloud_cover` (§6.2.5). `.github/` bleibt unverändert.
- **Je PR:**
  - Prüfanleitung für Otto (PowerShell 5.1, wie `scripts/checks/nm4-19-statistics.ps1`);
  - Log-Zeile;
  - vier Pflicht-Checks grün;
  - `main` geholt.
- **Doku:** `adr/0021` „§6 Nachtrag DS-03“ ergänzen; Zeile in `architekturplan.md` 5.1 (`earthx:mask.cloud_classes`, `within_aoi`).

### 6.14 Schnitt (Frage 6 entschieden: Option 1; Frage 7 entschieden: Option 3)

**Entschieden (Otto, 29.10.2026):**
- DS-03a1 (Grundlagen) in dieser Session.
- DS-03a2 (Filter in der Suche) nach dem Merge in neuer Session (§6.18).
- DS-03b (Frontend) nach DS-02c und DS-03a2 (§6.17).

Begründung der Teilung: Mit dem Filter in der Suche wächst DS-03a auf geschätzt ~450 Zeilen Code, ~600 Tests und Doku ~60, über dem Richtwert von 400 Zeilen. Vorgelegte Optionen (Frage 7):

1. **Zwei PRs in dieser Session** **(Empfehlung)**:
   - DS-03a1: Registry, Zählung in `access`, `gateway.read_slot`, Cache-Schlüssel (~180 Code, ~250 Tests).
   - DS-03a2: Filter in der Suche, Marke, Zähler, Log (~270 Code, ~350 Tests), auf a1 gestapelt.
2. Ein PR mit rund 1 100 Zeilen.
3. DS-03a1 in dieser Session, DS-03a2 nach dem Merge in neuer Session.

### 6.15 Fragen an Otto (erneute Vorlage, beantwortet am 29.10.2026)

1. **F2a Obergrenze:** (1) 500 je Suche über „Load more“ hinweg, danach Hinweis **(Empfehlung)**; (2) 500 je „Load more“; (3) 200 je Suche.
2. **F2b Zeitraum:** (1) keine Höchstlänge, die Obergrenze genügt **(Empfehlung)**; (2) höchstens ein Jahr.
3. **F2c Fortschritt:** (1) kurze Antworten (100 Szenen oder 8 s) mit Seitenmarke, „found / checked“ nach jeder **(Empfehlung)**; (2) eine lange Anfrage mit SSE; (3) gestreamte Antwort.
4. **F2d Last:** (1) Messung im `api`, höchstens 6 Leser je Host und Prozess über `gateway` **(Empfehlung)**; (2) 6 je Anfrage; (3) über alle Prozesse (erst M6).
5. **F2e Cache:** (1) Messung je Szene und AOI im Statistik-Cache, 7 Tage, gefilterte Seiten nicht gecacht **(Empfehlung)**; (2) zusätzlich gefilterte Seiten im Such-Cache.
6. **F2f Mehrere Datensätze:** (1) Filter je Datensatz, nur wo die Registry `within_aoi` setzt, Grenze und Fortschritt je Datensatz **(Empfehlung)**.
7. **F7 Schnitt DS-03a:** (1) zwei PRs (a1 Grundlagen, a2 Suche) in dieser Session **(Empfehlung)**; (2) ein PR; (3) a2 in neuer Session.

KE1–KE6 (§6.9) und die Registry-Form (§6.10) gelten, sofern Otto nicht widerspricht.

**Antworten (Otto, 29.10.2026):** 1 Option 1; 2 Option 1; 3 Option 1 mit Zusatz für DS-03b (§6.17); 4 Option 1; 5 Option 1; 6 angenommen; 7 Option 3. KE2–KE6 angenommen; KE1 geändert (§6.9). Die Registry-Form gilt.

### 6.16 Messanhang und Skript [M]

**Skript:** `scripts/ds-03-clouds/measure.py`.
- Der Netzschritt für die Metadaten (sechs Suchen über je eine Saison, elf Zählungen über 2024) ist ein dokumentierter Einmal-Schritt mit `curl` im Kopf des Skripts. Das Skript selbst stellt keine HTTP-Anfrage.
- Jede Rasteradresse geht durch `gateway.check_url` gegen die `asset_hosts` des Registry-Eintrags und wird mit `gateway.vsicurl_path` und `gateway.gdal_options` gelesen, auf dem Weg der Plattform.
- Unterbefehle: `prepare`, `accuracy`, `timing`, `parallel`, `summary`. Ausgaben bleiben im angegebenen Ordner. Das Skript gibt keine Koordinaten, Adressen oder Fehlertexte von GDAL aus.
- Der Lauf vom 29.10.2026 gab für die Genauigkeit dieselben Zahlen wie die erste Messung vom 28.10.2026, Stelle für Stelle.

Zeit je Szene, kalt, nacheinander, 16 Szenen, Lauf vom 29.10.2026 (Median / 90. Perzentil in s; Bytes Median in KB):

| AOI | 20 m | 40 m | 80 m | 160 m | 320 m |
|---|---|---|---|---|---|
| 1 km | 0,50 / 0,59; 64 | 0,45 / 0,46; 48 | 0,42 / 0,45; 48 | 0,39 / 0,47; 64 | 0,31 / 0,35; 32 |
| 10 km | 0,46 / 0,63; 59 | 0,44 / 0,58; 41 | 0,42 / 0,46; 48 | 0,41 / 0,45; 64 | 0,33 / 0,36; 32 |
| 30 km | 0,79 / 0,92; 144 | 0,46 / 0,60; 72 | 0,45 / 0,50; 65 | 0,45 / 0,47; 49 | 0,31 / 0,34; 32 |
| 110 km | 0,72 / 0,88; 907 | 0,46 / 0,51; 352 | 0,45 / 0,46; 144 | 0,41 / 0,45; 96 | 0,33 / 0,35; 32 |

**Szenen:** je Region acht, gewählt über den Wolkenanteil der Szene (0–100 %), mit einem No-Data-Anteil unter 60 %. Kacheln u. a.:
- 32TNT/32TPT/32UNU/32UPU (Alpen)
- 20LRQ/21LTJ (Amazonas)
- 31RGH/31RHH (Sahara)
- 32VNP/32VNN (Norwegen)
- 29SMD/29SND (Portugal)
- 45RTH/45RUH (Ganges)

Daten unter der offenen Copernicus-Lizenz; nichts davon liegt im Repo.

### 6.17 DS-03b — Frontend „Within AOI“ (Folgeaufgabe, neue Session)

**Stufe A**, nur Frontend. Die Entscheidungen stehen in diesem Plan (§6.0, §6.4–§6.11, Freigaben Ottos vom 29.10.2026) und in `adr/0021` „§6 Nachtrag DS-03“; dieser Abschnitt ist ohne das Gespräch zu DS-03 verständlich.
**Modell:** Sonnet, Effort hoch.
**Start:** nach dem Merge von DS-02c („Advanced search“ im Frontend) und von DS-03a2 (Backend: Filter `earthx:aoi_cloud_cover` in `POST /stac/search`, §6.18). Branch von `main`, ein Draft-PR.
**Startsatz:** „Führe Aufgabe DS-03b aus `docs/plans/ds/ds-03-wolken-in-aoi.md` §6.17 aus.“

**Ausgangslage:**
- Das Backend filtert Sentinel-2-Szenen nach dem Wolkenanteil in der AOI, wenn die Suche `earthx:aoi_cloud_cover` mit `gte`/`lte` in `query_by_collection` trägt.
- Es prüft je Antwort höchstens 100 Szenen oder 8 s lang und je Suche höchstens 500 Szenen.
- Es meldet `earthx:aoi_filter` bzw. `earthx:aoi_filter_by_collection` (`checked`, `found`, `unreadable`, `limit_reached`). Jeder Treffer trägt `earthx:aoi_cloud_cover` und `earthx:aoi_measure` (`data_percent`, `cloud_pixels`, `data_pixels`, `resolution`).
- Ohne Zeitraum mit beiden Enden, ohne Fläche oder für einen Datensatz ohne Filter antwortet es `400`.
- Welche Datensätze den Schalter bekommen, sagt die Collection: `earthx:search_filters[].within_aoi`. Den Text zu den Grenzen liefert `earthx:mask.cloud_note`.

**Umfang** (Texte englisch, wenig Text, Erklärungen im Tooltip; nicht Anwendbares ausgeblendet, nicht ausgegraut, außer dem Schalter selbst, den Otto ausdrücklich gesperrt mit Grund will):
1. **Schalter „Within AOI“** in „Advanced search“ unter dem Filter, an dem `within_aoi` gesetzt ist. Er ist je Datensatz gespeichert, wie die Filterwerte aus DS-02c.
   - Ist er an, sendet `buildSearchBody` den Bereich unter `earthx:aoi_cloud_cover` statt unter dem Filter der Szene.
   - **Tooltip** nach §6.11, mit `cloud_note`.
   - **Gesperrt** mit Grund im Tooltip:
     - ohne AOI oder ohne Zeitraum mit beiden Enden: „Draw an AOI and set a date range first“;
     - bei einer Punkt-AOI: „Draw an area to use this filter“.
   - Eine AOI mit mehr als 1 000 Positionen sperrt den Schalter nicht. Die Suche schickt dann `bbox` und die AOI zusätzlich als `earthx:aoi` (§6.5, KE1).
2. **Suche (Otto, 29.10.2026):**
   - Bei aktivem „Within AOI“ fragt das Frontend selbst mit der Seitenmarke weiter, bis die Seite gefüllt ist (wie heute bis 300 Treffer), die Obergrenze erreicht ist oder die Quelle nichts mehr hat.
   - Eine Antwort mit wenigen oder keinen Treffern ist für das Frontend kein Ende. **Eine leere Seite mit nur „Load more“ kommt nicht vor.**
   - Nach jeder Antwort steht der Stand im Kopf des Abschnitts: „12 found / 180 checked“, während und nach der Suche.
   - **Gemischte Suche (Otto, 30.10.2026):** Die Oberfläche behält den letzten Stand der Zähler je Quelle (`earthx:aoi_filter_by_collection`), wenn spätere Seiten ihn nicht mehr liefern; die Antwort nennt eine Quelle, die fertig ist oder die Grenze erreicht hat, nicht mehr.
   - Ein Knopf „Stop“ neben dem Stand bricht das Weiterfragen ab. Was gefunden ist, bleibt; „Load more“ setzt danach mit der Marke fort.
   - „Load more“ füllt die nächste Seite auf dieselbe Weise.
   - Bei `limit_reached` steht der Hinweis „Checked 500 scenes back to <Datum der ältesten geprüften Szene>. Narrow the date range to search further.“ und „Load more“ verschwindet.
   - Bei `unreadable` > 0 steht „<n> scenes could not be checked“.
   - Der Datums-Fallback (±90 Tage) sucht bei „Within AOI“ nicht; ohne Treffer steht „No scenes within the AOI limit in this date range“.
3. **Coverage:** Mit „Within AOI“ bekommt `/coverage` den Wolkenfilter nicht; die übrigen Filter wirken weiter.
4. **Zeile und Gruppe:**
   - „☁ 3 %“ (ganze Prozent, „<1 %“ unter 1) mit Tooltip nach §6.11.
   - Der Gruppenwert ist Summe `cloud_pixels` / Summe `data_pixels` der Szenen der Gruppe.
5. **Sortierung:** „Sort: Date | Clouds in AOI“ in der Trefferliste, nur bei aktivem „Within AOI“. Sie ordnet Gruppen nach ihrem Wert; innerhalb einer Gruppe bleibt die Reihenfolge.
6. Abbruch laufender Seiten, wenn AOI, Zeitraum, Datensätze oder Filter sich ändern (wie heute bei neuer Suche).

**Abnahme:**
- **vitest:**
  - Schalter nur mit `within_aoi`; gesperrt ohne AOI, ohne Zeitraum und bei einer Punkt-AOI.
  - Werte je Datensatz getrennt; Anfrage trägt `earthx:aoi_cloud_cover` statt `eo:cloud_cover`.
  - Weiterfragen, bis die Seite gefüllt ist; Antworten ohne Treffer führen nie zu einer leeren Seite mit nur „Load more“.
  - „Stop“ bricht ab und lässt das Gefundene stehen.
  - „found / checked“ nach jeder Antwort; Hinweis bei `limit_reached` und `unreadable`; „Load more“ weg bei Grenze.
  - Eine AOI mit mehr als 1 000 Positionen sendet `bbox` und `earthx:aoi`.
  - kein Datums-Fallback; Coverage ohne den Wolkenfilter.
  - Gruppenwert aus den Pixelzahlen; Sortierung.
  - DEM ohne Schalter.
- **Browser** (Chromium/Playwright der Sitzung, Antworten der Suche gemockt):
  - Klickweg Sentinel-2: AOI zeichnen, Zeitraum setzen, „Within AOI“ an, Grenze setzen, Suche mit Fortschritt über mehrere Antworten, „Stop“, Sortierung, Tooltip.
  - Sperre ohne AOI.
  - Hell/Dunkel, schmales Fenster.
  - Im PR beschrieben.
- Prüfanleitung für Otto (Browser), Log-Zeile, vier Pflicht-Checks grün, `main` geholt vor „fertig“.
- **Grenzen:**
  - Keine neue Abhängigkeit ohne Frage an Otto.
  - Keine AOI, Kennungen oder Hashes in URLs oder Logs.
  - Kein datensatzspezifischer Code: Alles kommt aus `within_aoi`, `cloud_classes`, `cloud_note`.
  - `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

**Umgesetzt am 31.10.2026** (Draft-PR, Log-Zeile, `adr/0021` §6 Nachtrag DS-03). Gegenüber dem Umfang oben:
- **Schalter:** siehe die Review Ottos unten. Er ist die Wahl eines Datensatzes (`searchWithin`), nicht Teil eines Filters; als Filter zählt er nicht („Advanced search · N“ zählt ihn nicht), „Reset filters“ nimmt ihn zurück.
- **Gesperrt = aus:** Ohne AOI, Zeitraum mit beiden Enden oder bei einer Punkt-AOI zeigt der Schalter „aus“, die Suche fragt den Bereich der Szene (`eo:cloud_cover`), und die Coverage bekommt ihn ebenfalls. Fällt die Bedingung weg, solange der Schalter an ist, geht er aus und kommt mit der nächsten AOI nicht von selbst zurück.
- **Suche:** `walkAoiSearch` fragt mit der Marke weiter, zeigt nach jeder Antwort die Liste (ohne Treffer erscheint sie mit den ersten) und endet bei 300 Treffern, ohne Marke, bei „Stop“ oder wenn AOI, Zeitraum oder Filter sich ändern (`dropPageToken` und `forgetSearch` brechen die Anfrage ab). Eine Anfrage, die „Stop“ abbricht, wird bei „Load more“ mit derselben Marke noch einmal gestellt. Ein Fehler nach den ersten Treffern lässt sie stehen, nimmt die Marke weg und sagt „Could not load more results — search again.“; ein Fehler vor der ersten Antwort ist wie bisher „Search failed“.
- **Fortschritt:** „n found / m checked“ im Kopf der Liste mit „Stop“; solange keine Liste da ist (nichts im Bereich gefunden), steht beides in der Meldung der Suche. „Load more“ fehlt, solange die Suche selbst weiterfragt. Die Hinweise zur Grenze und zu unlesbaren Szenen stehen im Kopf des Datensatzes; bei einem Datensatz ohne Liste in der Meldung.
- **Antworten Ottos (31.10.2026, zu #265):**
  - Der Hinweis zur Grenze nennt kein Datum („Checked 500 scenes. Narrow the date range to search further.“), weil keine Antwort das Datum der ältesten geprüften Szene trägt: so lassen.
  - Eine AOI mit mehr als 20 000 Positionen sperrt den Schalter mit Grund im Tooltip („The area has too many points for this filter“, `MAX_AOI_POSITIONS`); das `400` des Servers bleibt als Sicherung. Bis 20 000 Positionen bleibt er frei (KE1).
  - Fallen AOI oder Zeitraum weg, geht der Schalter aus und ist danach gesperrt mit Grund.
  - Datums-Fallback: nur für den gemessenen Datensatz aus, die anderen behalten ihn.
  - „Stop“ ohne Treffer: Die Liste erscheint mit „0 found / m checked“ und „Load more“ (`ResultSection.keepList`).
  - „cloud shadows do not count“ steht nur im Tooltip (der Wert „0 %“/„<1 %“ in Zeile und Gruppe entfällt mit der Review unten).
  - Die Statusmeldung bei schmalem Fenster bleibt unberührt (geht an NM4-56).
- **Review Ottos (31.10.2026, zu #265), umgesetzt im selben PR:**
  - **Entfernt:** „Sort: Date | Clouds in AOI“ und die Anzeige „☁ n %“ in Szenenzeile und Gruppenkopf. Die Ergebnisliste zeigt davon nichts mehr; „n found / m checked“, „Stop“ und die Hinweise bleiben.
  - **Schalter „Filter within AOI only“:** ganz oben im Popup, über den Feldern, je Datensatz; er gilt für alle flächenabhängigen Filter des Datensatzes. Ist er an (und frei), sendet das Frontend den Bereich jedes Filters, an dem die Registry `within_aoi` setzt, unter dem dort genannten Namen (`earthx:aoi_cloud_cover`, `earthx:aoi_nodata`) statt unter dem der Szene; Filter ohne Flächenbezug (Satellite) bleiben. Der Tooltip nennt die betroffenen Filter („Cloud cover (classes 8, 9, 10; cloud shadows do not count), No data. Others are unchanged.“), den Satz zu den Grenzen der Klassifizierung, die Kosten und die Coverage. Die Coverage lässt alle diese Filter weg. Sperrregeln, Aus-bei-Wegfall und „Stop“ ohne Treffer gelten wie oben.
  - **Registry (Backend):** `SearchFilter.within_aoi` ist `AoiMeasure | None` und wird als Eigenschaftsname (oder `null`) veröffentlicht; je Messung höchstens ein Filter. Neu `earthx:aoi_nodata`: Anteil der AOI-Pixel ohne gültiges Pixel = `100 − data_percent` derselben Lesung (Teile der AOI außerhalb der Kachel zählen als ohne Daten; eine Szene ohne gültiges Pixel hat 100), ohne zusätzliches Lesen und ohne Änderung des Cache-Schlüssels. Mehrere Bedingungen gelten zugleich (UND).
  - **Mehraufwand:** gemessen 0,41 µs je Szene für die Ableitung und rund 0,6 µs mehr für die Prüfung der zweiten Bedingung, gegen rund 20 ms für eine Lesung mit Zählung; Lesungen bei 300 Szenen: nur Cloud 300, Cloud plus No data 300, nur No data 300.
  - **Antworten Ottos (31.10.2026, zweite Runde zu #265):** Die `400`-Texte der Route sind neutral: Sie nennen den Filter, der gefragt wurde (`earthx:aoi_nodata needs a date range …`, bei beiden `earthx:aoi_cloud_cover and earthx:aoi_nodata`), ohne Wert; wo es keinen Filter zu nennen gibt, „a filter measured in the AOI“. Das Prüfskript `ds-03a2-aoi-clouds.ps1` erwartet die neuen Texte (dazu No-data-Fälle). Weitere Klassenanteile (Snow and ice, Water, Vegetation …): nicht jetzt, Backlog 67. Der Live-Test schlägt ohne Netz fehl wie die übrigen. Der Name bleibt „Filter within AOI only“. Gemergt wird mit Squash.
- **Browser:** `frontend/e2e/within-aoi.cjs` (Chromium, Antworten gemockt), hell/dunkel × breit/schmal/sehr schmal grün. Bei schmalem Fenster ragt die Meldung der Suche (`.status`) über den Rand, sobald ein Panel offen ist; das tut sie nach jeder Suche, auch ohne den Schalter (beobachtet, nicht geändert).

### 6.18 DS-03a2 — Filter „Within AOI“ in der Suche (Folgeaufgabe, neue Session)

**Stufe A**, nur Backend. Die Entscheidungen stehen in diesem Plan (Freigaben Ottos vom 29.10.2026, §6.4–§6.10, §6.14–§6.15) und in `adr/0021` „§6 Nachtrag DS-03“; dieser Abschnitt ist ohne das Gespräch zu DS-03 verständlich.
**Modell:** Sonnet, Effort hoch.
**Start:** nach dem Merge von DS-03a1 (§6.19). Branch von `main`, ein Draft-PR.
**Startsatz:** „Führe Aufgabe DS-03a2 aus `docs/plans/ds/ds-03-wolken-in-aoi.md` §6.18 aus.“

**Ausgangslage (aus DS-03a1):**
- **Registry:** Die Registry kennt `MaskSource.cloud_classes`, `MaskSource.cloud_note` und `SearchFilter.within_aoi`. Sentinel-2 setzt sie: Klassen 8, 9, 10; `within_aoi` an „Cloud cover“. Die Collection veröffentlicht sie.
- **`access.aoi_clouds`:** zählt Wolken- und gültige Pixel einer Szene in einer AOI auf der Stufe aus Frage 1. Dazu gehören der Cache-Schlüssel je Szene und AOI und die Zahlen für `earthx:aoi_measure`.
- **`gateway.ReadSlots`:** begrenzt gleichzeitige GDAL-Leser je Host auf `Policy.max_connections_per_host`.
- Keine Route nutzt das bisher.

**Umfang:**
1. **Lesen der Anfrage** (`api/search_filters.py`): `earthx:aoi_cloud_cover` mit `gte`/`lte` (0–100) in `query_by_collection` und `query`, nur für Collections mit `within_aoi`. Die Bedingungen aus §6.5 gelten, sonst `400` ohne Werte im Text:
   - ein Zeitraum mit beiden Enden;
   - eine Fläche: `intersects` als `Polygon`/`MultiPolygon` oder `bbox`; dazu optional `earthx:aoi` mit höchstens 20 000 Positionen, innerhalb `bbox`;
   - kein Punkt, keine Linie;
   - Body höchstens 1 MB.
   Andere `earthx:`-Eigenschaften bleiben `400`. `GET` weist `query` weiter ab; `/coverage` weist `earthx:` weiter ab.
2. **Prüfschleife je Quelle** (`api`, §6.5 „Ablauf“):
   - Seiten der Quelle zu 100 mit den übrigen Filtern holen, mit dem Such-Cache.
   - Je Item den Wert aus dem Statistik-Cache nehmen oder messen, über `access.aoi_clouds`. Gemessen wird im Prozess `api`, in Threads, mit `gateway.ReadSlots` und den GDAL-Optionen aus `gateway`.
   - Nur passende Items zurückgeben, mit `earthx:aoi_cloud_cover` und `earthx:aoi_measure` in `properties`.
   - Ende einer Antwort bei: `limit` Treffern, 100 geprüften Szenen, 8 s Messzeit, 500 geprüften Szenen je Suche oder Ende der Quelle.
3. **Seitenmarke:** Mit AOI-Filter trägt sie die Stelle in der Seite der Quelle (`i`) und die Zähler (`c`, `f`, `u`); ohne AOI-Filter bleibt sie unverändert (`TOKEN_VERSION` 2). Der Fingerabdruck nimmt den AOI-Filter und `earthx:aoi` auf. Bei 500 geprüften Szenen gibt es keine Marke mehr.
4. **Antwort:**
   - `earthx:aoi_filter` (`checked`, `found`, `unreadable`, `limit_reached`), bei gemischter Suche `earthx:aoi_filter_by_collection`.
   - In der gemischten Suche misst nur die Quelle mit dem Filter, innerhalb des Budgets von 10 s.
5. **Cache:**
   - Messung je Szene und AOI im Statistik-Cache, 7 Tage, Schlüssel aus `access.aoi_clouds`.
   - Gefilterte Seiten kommen nicht in den Such-Cache.
   - Ein Fehler des Caches macht nur langsamer; geloggt wird nur die Art der Ausnahme.
6. **Log** (KE3): eine Zeile je Antwort „aoi cloud filter“ mit Datensatz, geprüft, gefunden, aus dem Cache, unlesbar, Grenze erreicht, Stufen, Sekunden. Keine AOI, Kennung, Grenzwerte, kein Schlüssel und keine Adresse.
7. **Unlesbare Szene** (KE5): fällt heraus, wird gezählt.
8. **Live-Test** (`backend/tests_live/`, lokal; `.github/` bleibt unverändert): eine echte Szene, deren Anteil über die ganze Datei gleich `eo:cloud_cover` ist (§6.2.5); eine Suche mit Filter über `gateway`.
9. **Doku:** `adr/0021` §6 Nachtrag DS-03 (Umsetzung a2), Zeilen in `architekturplan.md` 5.1 für `earthx:aoi_cloud_cover`, `earthx:aoi_measure`, `earthx:aoi_filter`; Nachtrag zu `adr/0005` Regel VI (Filter, den die Plattform rechnet).

**Abnahme:** die Tests aus §6.13 außer denen, die DS-03a1 schon abdeckt (Rechnung, Stufenwahl, Registry, Leser je Host). Außerdem:
- Prüfanleitung für Otto (PowerShell 5.1, Skript unter `scripts/checks/`, wie `nm4-19-statistics.ps1`).
- Log-Zeile, vier Pflicht-Checks grün, `main` geholt vor „fertig“.
- `lint-imports` ohne Lockerung. Bräuchte es eine Lockerung, ist das zuerst eine Frage an Otto.

**Umgesetzt am 30.10.2026** (Draft-PR, Log-Zeile, `adr/0021` §6 Nachtrag DS-03, `adr/0005` Nachtrag zu Regel VI, `architekturplan.md` 5.1). Gegenüber dem Umfang oben:
- **Messungen, die beim Ende einer Antwort noch laufen,** werden nicht abgebrochen, sondern lesen zu Ende und speichern ihren Wert. Ein Abbruch mitten in der Datenbankabfrage hinterließ kaputte Verbindungen des Pools (psycopg-Warnungen). Die nächste Antwort fragt genau diese Szenen zuerst und bekommt sie aus dem Cache, sobald sie fertig sind (fragt das Frontend sofort weiter, kann eine noch laufende Szene doppelt gemessen werden). Die Antwort wartet nicht auf sie; `settle()` wartet darauf, im Lifespan bis zu 10 s und in Tests.
- **Wert und Filter:** Der Bereich gilt für den Anteil mit einer Nachkommastelle, wie ihn die Antwort zeigt, damit Liste und Filter übereinstimmen.
- **Weitere `400`:** `earthx:aoi` ohne den Filter, zusammen mit `intersects` oder ohne `bbox`; der Filter an einer Collection mit eigenen Items; eine AOI, die kein gültiges Polygon auf dem Globus ist. Ein Zeitpunkt statt eines Zeitraums zählt als offenes Ende.
- **Weitere Folgen aus dem Review (Subagent `reviewer`):** Die Marke ist an die Suche der Quelle gebunden, auch auf der ersten Seite. Eine Antwort holt mit weniger als 2 s Rest keine neue Seite der Quelle (Budget der gemischten Suche). Die Messung liest in einem eigenen `CapacityLimiter`, nicht im gemeinsamen Threadpool. GDAL-Zeilen mit `curl error` und `gdal signalled` verwirft der Logfilter ebenfalls. Er wirkt nur in einem Thread, der gerade eine Szene misst (`without_gdal_addresses`); ein prozessweiter Filter nahm den Tests anderer Routen die Warnung von GDAL, die sie sehen wollen.
- **Antworten Ottos (30.10.2026, zu #240):** (1) Der `next`-Link, den `stac-fastapi` baut, wiederholt den ganzen POST-Body (auch `intersects` und `earthx:aoi`): so lassen; die AOI steht nur im Body, nie in URL oder Log. (2) Adressen von GDAL im Log: wird mit NM4-57 für alle Prozesse (`api`, `tiler`, `worker`) gelöst, hier nichts weiter ändern; der Filter dieser Aufgabe bleibt bis dahin auf die Messung beschränkt. (3) In der gemischten Suche fehlen die Zähler einer Quelle, die fertig ist oder die Grenze erreicht hat, auf späteren Seiten; die Oberfläche behält den letzten Stand (§6.17 Punkt 2). Marken sind nicht signiert; `c` lässt sich auf 0 setzen und so die Grenze von 500 umgehen, wie bei den bestehenden Marken nur eine Kostenbremse.
- **Lauf des Prüfskripts (Otto, 30.10.2026, PowerShell 5.1):** 11 PASS, 6 FAIL, alle in Schritt 4 und 5: Status 400 wie erwartet, aber der Text kam leer an. Ursache im Skript, nicht in der Route: Bei einem `400` wirft `Invoke-WebRequest`, und 5.1 hat den Strom der Antwort dann schon gelesen; der Body steht in `ErrorDetails.Message`. Das Skript liest jetzt zuerst dort, danach den Strom, und gibt bei einem FAIL den erhaltenen Text aus (gekürzt, Zahlen mit vier und mehr Nachkommastellen verdeckt). Die Texte der Route sind unverändert und stimmen mit den Erwartungen überein (`date range`, `needs an area`, `cloud share`, `POST`, `coverage map`).
- **Ausdrückliche Ausnahme für `.github/` (Otto, 30.10.2026):** In `.github/workflows/live-smoke.yml`, Job `earth-search`, steht `backend/tests_live/test_aoi_cloud_filter_live.py` in der `run:`-Zeile, der Schrittname ist nachgezogen; sonst bleibt `.github/` unverändert.
- **Marke:** eine Hülle um die Marke der Quelle (`{"v": 1, "k": "aoi", ...}`); die Marke der Quelle bleibt `TOKEN_VERSION` 2 (§6.9 F2c: „bleibt 2“ gilt für sie). Gefilterte Antworten tragen kein `numberMatched`.
- **Adressen im Log:** GDAL nennt bei einem Lesefehler die Adresse der Datei in einer Warnung, die `rasterio` an das Logging gibt (gemessen). Die Messung hängt einen Filter an diese Logger (`hide_gdal_addresses`). Der `tiler` und der `worker` lesen ohne ihn; das löst NM4-57 für alle Prozesse (Otto, 30.10.2026).
- **`access.aoi_clouds.canonical_aoi`** ist jetzt öffentlich (die Marke braucht dieselbe Schreibweise wie der Cache-Schlüssel).
- **`api`** setzt beim Bau `earthx_policy`, `earthx_resolver`, `earthx_gdal_options` und `earthx_read_slots` wie der `tiler` seine; `gateway` ist unverändert.
- **Nicht gelaufen in der Sitzung:** das Skript `scripts/checks/ds-03a2-aoi-clouds.ps1` (PowerShell 5.1; `pwsh` ist hier nicht installiert, ein Download ist verweigert worden) und die Live-Tests (`backend/tests_live/test_aoi_cloud_filter_live.py`; der `gateway`-Client erreicht die Quelle in dieser Sitzung nicht, nur ein Proxy). Statt dessen einmal von Hand mit denselben Klassen gegen die echte Quelle: ganze Datei 43,332 % gegen `eo:cloud_cover` 43,33207 (§6.2.5 bestätigt), 42 Szenen in 5 s.

**Grenzen:**
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Kein datensatzspezifischer Code.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

### 6.19 DS-03a1 — Grundlagen (diese Session)

**Umfang:**
1. **Registry** (`catalog/registry.py`, `catalog/datasets.py`):
   - `MaskSource.cloud_classes: frozenset[int]` und `cloud_note: str`, ohne Vorgabewert.
   - `SearchFilter.within_aoi: bool`, ohne Vorgabewert.
   - **Prüfungen beim Start:**
     - `cloud_classes` ⊆ den Werten von `classes`;
     - nicht leer heißt: `cloud_note` nicht leer, und der Datensatz liegt als COG vor (gelesen wird über die Übersichten der Datei);
     - `within_aoi` an höchstens einem Filter, nur `RANGE` 0–100 mit Einheit `%`, nur mit nicht leeren `cloud_classes`.
   - **Sentinel-2:** {8, 9, 10}, `cloud_note` nach §6.10, `within_aoi` an „Cloud cover“.
   - **Andere Einträge:** Der synthetische Zarr-Eintrag der Tests hat leere `cloud_classes`; alle anderen Filter haben `within_aoi=False`.
2. **Collection** (`catalog/collection.py`): `earthx:mask` mit `cloud_classes` (aufsteigend) und `cloud_note`; `earthx:search_filters[]` mit `within_aoi`.
3. **`access/aoi_clouds.py` (neu):**
   - Stufenwahl nach Frage 1: die gröbste Übersicht der Datei, auf der die AOI noch mindestens 10 000 Pixel hat, sonst die volle Auflösung. Grundlage ist die Fläche der AOI im Raster der Szene.
   - Zählung der Wolken- und gültigen Pixel in der AOI: Pixelmitten, `nodata` der Datei als „ohne Daten“, Pixel der AOI außerhalb der Datei als „ohne Daten“.
   - Ergebnis: `cloud_pixels`, `data_pixels`, `aoi_pixels`, `resolution`. Daraus folgen `cloud_percent` (`None` ohne gültiges Pixel) und `data_percent`.
   - Cache-Schlüssel je Szene und AOI (§6.9 F2e).
   - Ohne Log, ohne eigenes GDAL-Env: Die Hülle setzt das Env, wie bei `processing.core.area_statistics`.
4. **`gateway`:** `ReadSlots`, ein Zähler je Host für gleichzeitige GDAL-Leser mit der Grenze `Policy.max_connections_per_host`. Nichts Fachliches.
5. **Doku:**
   - `adr/0021` „§6 Nachtrag DS-03“ ergänzt;
   - Zeile in `architekturplan.md` 5.1;
   - Log-Zeile.

**Abnahme DS-03a1:**
- **Tests** (synthetische COGs im Test erzeugt, mit `MODE`-Übersichten):
  - Anteil gegen eine unabhängige Zählung mit `numpy` auf 20 m und auf einer Übersicht;
  - Stufenwahl an der Grenze von 10 000 Pixeln;
  - AOI teilweise außerhalb;
  - `MultiPolygon`;
  - Rechteck als Polygon;
  - AOI ganz ohne Daten;
  - Klasse 1 im Nenner;
  - Punkt und Linie abgewiesen;
  - eine AOI mit 20 000 Positionen;
  - Cache-Schlüssel gleich bei gleicher AOI in anderer Schreibweise und verschieden bei anderer AOI, Szene oder anderen Klassen; der Schlüssel enthält keine Koordinaten;
  - `ReadSlots` lässt nie mehr als die Grenze gleichzeitig lesen;
  - Registry-Prüfungen;
  - Collection-Felder.
- `ruff check backend`, `lint-imports` (ohne Lockerung) und `pytest` grün; vier Pflicht-Checks grün; `main` geholt.
- **Keine Prüfanleitung im Browser:** DS-03a1 hat keine Route. Die Prüfanleitung kommt mit DS-03a2.

**Umgesetzt am 29.10.2026** (Draft-PR #235, Log-Zeile, `adr/0021` §6 Nachtrag DS-03). Gegenüber dem Umfang oben:
- **Lange und große AOI:** Nur der Teil der AOI, der auf der Kachel liegt, wählt die Stufe und wird Pixel für Pixel maskiert. Der Teil außerhalb hat keine Daten und geht über seine Fläche in `aoi_pixels` ein.
  - So kostet eine AOI, die viel größer ist als die Kachel (ein Land gegen 110 km), nicht mehr Speicher als die Kachel.
  - Ein kleiner Anschnitt wird fein genug gelesen.
  - `aoi_pixels` weicht dadurch am Rand um höchstens eine Pixelreihe von einer Zählung über Pixelmitten ab. `cloud_pixels` und `data_pixels` bleiben exakt.
- **Cache-Schlüssel:** nimmt von der AOI nur `type` und `coordinates` (Zahlen als Gleitkommazahlen, `-0.0` als `0.0`). Weitere GeoJSON-Glieder wie `bbox` ändern ihn nicht.
- **`nodata` nicht in der Registry:** Die Prüfung „`cloud_classes` ohne den `nodata`-Wert“ (§6.10) entfällt, weil die Registry den `nodata`-Wert der Datei nicht kennt. Die Zählung nimmt ihn aus der Datei; ein Pixel mit diesem Wert zählt nie als Wolke.
- **Weitere `ValueError` ohne Koordinaten:** ein Polygon, das sich nicht auf das Raster legen lässt, keine Fläche hat oder ungültig ist (selbstschneidender Ring, überlappende Teile), und ein Raster ohne CRS. GEOS nennt bei solchen Fehlern eine Position; deshalb liegt auch die Verschneidung mit der Kachel im abgefangenen Teil.
- **Nur Blöcke unter der AOI:** Gelesen und maskiert werden nur die Blöcke der Datei, die die AOI berühren. So kosten zwei weit auseinander liegende Ecken oder ein schmaler Streifen quer über die Kachel nur die Blöcke, die sie bedecken, nicht das Rechteck um sie. Die Stufenregel aus Frage 1 bleibt unverändert.
- **Nur geprüfte Pfade:** `measure_aoi_clouds` nimmt nur einen `AssetPath`, also einen vom `gateway` geprüften Pfad (KLAERUNGEN B8, wie `access.mosaic_tiles`). Ein einfacher String ist ein `TypeError`.
- **`min_pixels` nicht frei wählbar:** Die Grenze ist die Konstante `MIN_AOI_PIXELS` (KE2), damit ein Eintrag im Cache immer dieselbe Stufe meint.
- **`ReadSlots`:** gibt einem Host, den die Policy nicht erlaubt, keinen Platz (`UrlRejected`). Ein Platz ist nicht wiedereintrittsfähig: Wer einen hält, fragt nicht noch einmal für denselben Host.
- **Tests:** Einträge, die Tests aus Sentinel-2 ableiten (Zarr, Legacy, ohne Schicht), setzen den Wolkenanteil mit `tests.catalog.synthetic_zarr.without_cloud_share` ab. Der Start weist diese Kombinationen sonst zu Recht ab.
- **Für DS-03a2:** `ReadSlots` liegt in `gateway`. `api` darf es direkt importieren, `access` nicht; die Messung in `api` nimmt also den Platz und ruft dann `access.aoi_clouds`.
- **Review:** Der Subagent `reviewer` prüfte den Diff vor dem PR. Seine Befunde (Koordinaten im Fehlertext bei ungültiger AOI, ungeprüfter Pfad, Lesefenster bei verstreuten AOIs, `OverflowError` im Schlüssel, Strukturprüfung der Koordinaten, `min_pixels` im Schlüssel, Typ von `cloud_note`, Allowlist in `ReadSlots`, schwache Tests, echte Ortskoordinaten in Tests) sind behoben. Offen bleibt nur die Verzerrung der Fläche außerhalb der UTM-Zone der Szene; sie betrifft nur `data_percent` und steht im Docstring.
- **Umfang:** rund 390 Zeilen Code (mit Docstrings) und 890 Zeilen Tests, über dem Richtwert von 400 Zeilen. Der größte Teil sind die geforderten Fehler- und Randfälle.
