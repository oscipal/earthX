# ADR 0014 — Rezept und Operator-Registry

- **Status:** **Angenommen** von Otto am 2026-10-02.
  - Alle fünfzehn Fragen aus §15 sind nach Empfehlung beantwortet (F1–F15:
    Option 1).
  - Dazu Auflagen zu F2, F3, F7 und F9. Sie stehen in §15a und sind in §4.4,
    §4.5, §5.4 und §6.3 eingearbeitet.
  - **F7a** (Skalierung, wenn das Item keine trägt) hat Otto am selben Tag mit
    Option 1 entschieden (§15a, §5.4).
- **Datum:** 2026-10-02
- **Aufgabe:** M4-03 laut `docs/plans/m4-processing-kern.md` §4.
- **Autonomiestufe:** C. Es gibt keinen Produktivcode, keine Änderung an
  `.importlinter`, an der Registry, an `gateway` oder an `decomp.py`. Gemessen
  wurde mit Skripten im Kratzverzeichnis der Sitzung. Der Messanhang (§17) nennt
  die Befehle.
- **Vorab fest:**
  - Q6, Q8, Q11, Q13 und Q14 aus dem M4-Plan §1.1.
  - Aus `adr/0011` §6.4: `ResolvedAsset` steht im Rezept. Der Worker-Kern sieht
    weder Adapter noch pgstac.
  - Q4 und Q12 gelten mittelbar: `processing` bleibt ohne psycopg, lokale
    Ergebnisse sind `self_attested` und kommen nie in den Cache.
- **Grundlage:**
  - `ENTSCHEIDUNGEN_2026-09-18.md` §3, §5; `KLAERUNGEN.md` B8, B9, B10, B11, B12.
  - `architekturplan.md` 3.1, 6.4, 6.5, 7.1–7.7, 12.3.
  - `adr/0001` Z4; `adr/0006` §3.3, §3.4, §5; `adr/0007` §12.8; `adr/0011` §6,
    §8.1; `adr/0012` F3, F5.
  - `plans/m3-18-download-deckel-maske.md` §10.3.
  - `projektuebersicht.md` §2 (Prinzipien 8, 9), §5 (Punkt 9).
  - Entscheidungslog bis 02.10.2026.
- **Betroffen:**
  - M4-07 (Rezept, Hash, Registry, Kern), M4-08 (Cache-Schlüssel, Job-API),
    M4-09 und M4-10 (Operatoren).
  - M4-13 (Panel aus Schemas), M4-14 (`recipe.json`, `citation.bib`), M4-15
    (Checkliste v2), M4-05 (`adr/0016`, Toleranz).
  - `access/resolve.py` aus M4-01a (Ergänzungen im Rezept, nicht in
    `ResolvedAsset`), `readers` (Fabrik für den Worker),
    `catalog/registry.py` (je nach F6).
  - `catalog/collection.py` (`sci:doi`, Nebenfund §3.10).

---

## Methode und Belegstufen

Gelesen und gemessen in einer Cloud-Sitzung am 02.10.2026 auf dem Stand von
`main` nach PR #110. Die Belegstufen folgen `adr/0009`:

- **M:** in dieser Sitzung gemessen; Befehl im Messanhang §17.
- **P:** am Primärdokument gelesen, mit Datei und Zeile (Quelltext im Repo, im
  venv oder in einem GitHub-Repo des Herausgebers).
- **S:** Zusammenfassung einer Quelle, deren Wortlaut nicht geprüft ist.
- **A:** eigene Ableitung, ein Argument und kein Beleg.

**Werkzeuge.** Gemessen wurde mit dem Python des Projekt-venv: Python 3.12.3,
rasterio 1.5.2 mit GDAL 3.12.2, rio-tiler 9.4.6, titiler.core 2.3.0,
numexpr 2.14.2, numpy 2.5.3, xarray 2026.9.0, zarr 3.1.6, pydantic 2.13.5. Das
sind dieselben Versionen, auf denen `readers` und `access` heute laufen.
Bibliotheken, die das Projekt nicht hat (odc-stac, dask, jsonschema, rfc8785),
lagen nur in einer eigenen venv im Kratzverzeichnis, nie im Projekt-venv.
Recherche und Messung teilten sich die Hauptsitzung und drei Hilfsagenten. Deren
Berichte mit wörtlichen Zitaten liegen nur im Kratzverzeichnis der Sitzung, nicht
im Repo. Was sie am Primärtext gelesen haben, trägt hier **[P]** mit Datei und
Zeile; das lässt sich aus dem Repo heraus nachprüfen (Wheel von PyPI laden bzw.
Datei im Repo des Herausgebers öffnen). Was sie selbst gemessen haben, trägt
**[M, Hilfsagent]**; das Skript dazu steht nicht im Messanhang.

**Gesperrte Hosts.** Gesperrt waren `www.rfc-editor.org`, `datatracker.ietf.org`,
`docs.ogc.org`, `api.openeo.org`, `gdal.org`, `*.readthedocs.io`,
`docs.dask.org`, `docs.pydantic.dev`, `doi.org`, `api.datacite.org` und
`github.com` (HTML). Primärtexte kamen deshalb über `raw.githubusercontent.com`
bzw. `git clone` aus den Repos der Herausgeber und über `pypi.org`. Der Text von
RFC 8785 stammt aus dem Repo der Autoren (`cyberphone/ietf-json-canon`,
`index.html`).

**Anfragen an Datenquellen: 14,** gedrosselt mit mindestens 1,2 s Abstand.
Ausnahme sind die zwei Anfragen, die GDAL beim Öffnen eines COG-Kopfes selbst
kurz hintereinander stellt (§17.1).

| Host | Anfragen | wofür |
|---|---|---|
| `earth-search.aws.element84.com` | 1 | ein Item suchen |
| `e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com` | 4 | `HEAD`, ein Range-`GET`, COG-Kopf per GDAL (2) |
| `stac.core.eopf.eodc.eu` | 2 | ein Item suchen; die erste Suche ging an die falsche Collection |
| `data.eodc.eu` | 6 | Kopfzeilen und konsolidierte Metadaten; 3 davon `404`, weil das Produkt der falschen Collection gehörte |
| `copernicus-dem-30m.s3.amazonaws.com` | 1 | `HEAD` auf eine Kachel |

Keine exakte AOI kommt vor. Die Suchen nutzten ein grobes Rechteck über den
Alpen bzw. gar keins. Die Zahlenbeispiele in diesem ADR sind synthetisch.

---

## 0. Kurzfassung

Jede Empfehlung hat eine Frage in §15.

1. **Rezept in drei Schichten (F1).**
   - Ein **Auftrag** kommt vom Panel, von der API oder vom Chatbot. Er enthält
     Datensatz, Items, Assets, AOI, Schritte und Ausgabe, aber keine Adresse.
   - `api` macht daraus das **Rezept**: jede Eingabe mit `ResolvedAsset`, ihrer
     Fassung und den Bandangaben.
   - Mit dem Ergebnis kommt die **Provenienz** (Ausführung, Versionen,
     Attribution).
   - Die Schritte sind eine lineare Folge, kein Graph. Eine Übersetzung nach
     openEO bleibt möglich.
2. **Kanonisierung und Hash (F2, F3).**
   - Das validierte Rezept wird kanonisch serialisiert, dann gehashed (SHA-256),
     mit Verfahrenskennung.
   - Der Hash bleibt intern (Q8). Deshalb reicht `json.dumps` mit festen Regeln
     über das validierte Modell. RFC 8785 wäre die standardkonforme Alternative
     mit einer kleinen Abhängigkeit (§4.4).
   - In den Cache-Schlüssel gehen Rezept, Fassungen, Operator-Versionen und die
     Versionen von GDAL, rasterio, numexpr und numpy (Auflage F3). Gemessen
     hängt das Ergebnis davon ab (§3.4).
3. **Fassung der Eingaben (F4).**
   - Earth Search liefert je Asset eine Prüfsumme `file:checksum` ohne
     zusätzliche Anfrage [M]. EOPF hat nur `updated` am Item, `data.eodc.eu`
     sendet weder ETag noch `Last-Modified` [M]. Beim DEM gibt es nur ein ETag
     per `HEAD` [M].
   - Vorschlag: Prüfsumme vor ETag vor `updated`. Ohne Fassung gibt es keinen
     Cache-Treffer (Q11).
4. **Operator-Registry aus pydantic-Modellen (F5).**
   - Parameter sind strikte Modelle, daraus entsteht JSON Schema 2020-12 [P].
   - Jeder Operator trägt Kennung, Version, Kategorie, Anwendbarkeit,
     Ausführungsstufen, Kostenmodell, Metadaten-Transformation und Kern.
   - Keine neue Abhängigkeit.
5. **Anwendbarkeit (F6) und Skalierung (F7).**
   - Für die Reprojektion gibt es ein eigenes Capability-Flag, nach B10
     „jede Fähigkeit ausdrücklich“. Methoden außer `nearest` brauchen
     zusätzlich `interpolation`.
   - Band-Math rechnet auf physikalischen Werten. Gemessen liefert der Zarr-Pfad
     schon Reflexion (CF-Dekodierung), der COG-Pfad Rohwerte [M]. Ohne Regel
     ergäbe dasselbe Rezept für die zwei Sentinel-2-Datensätze verschiedene
     Zahlen.
   - Auflage F7: Skalierung aus `raster:bands` des Items. F7a (1): Trägt das
     Item keine, gilt die generische CF-Dekodierung des Readers; das betrifft
     `sentinel-2-l2a-zarr3` (§5.4, §15a).
6. **Kostenschätzung (F8):** aus AOI, `gsd` und Datentyp, wie `plan_outputs`
   heute, mit gemessenen Durchsatzwerten. Einheiten sind Megapixel mal
   Operatorfaktor.
7. **Toleranz (F9).**
   - T2 gegen T2L: **bitgleich**.
   - T1 gegen T2 bei Band-Math: **bitgleich** auf einer Zoomstufe, die die
     native Ebene liest, mit `nearest`. Gemessen: 100 % von 2,6 Mio. Pixeln.
   - Bitgleich heißt: auf der nativen Ebene und auf derselben
     CPU-Architektur (Auflage F9).
   - Übersichtsstufen sind eine Annäherung, werden nicht verglichen und in der
     Oberfläche als „Preview“ gekennzeichnet.
   - Die Reprojektion ist planabhängig: Blockung und Näherung ändern Werte,
     die Thread-Zahl nicht [M]. Der Blockplan gehört deshalb zur
     Operator-Version.
8. **Lesen im Worker (F10).**
   - Eine eigene Blockschleife über die vorhandenen `readers`, ohne Dask und
     ohne odc-stac.
   - Blockweise braucht 110–150 MB statt 3,2 GB für eine 8192²-Szene, bei
     bitgleichem Ergebnis [M].
   - Dask und rioxarray verlieren die GDAL-Optionen außerhalb des Hauptthreads
     [M][P]. odc-loader liest Zarr über `fsspec` an `gateway` vorbei [P].
9. **Policy und GDAL im Worker (F11).**
   - Eine Fabrik in `readers` baut aus den Adressen des Rezepts Policy,
     GDAL-Optionen und Resolver.
   - Die Optionen gelten prozessweit (Hauptthread) und zusätzlich je Lesethread.
   - Ohne die Optionen aus `gateway` stellt GDAL 13 statt 3 Anfragen für
     dasselbe Fenster: zusätzlich ein Verzeichnis-Listing und 9 Sidecar-Proben
     [M].
10. **Job-Schnittstelle (F12).**
    - Form und Vokabular von OGC API Processes 1.0, mit einem Prozess `recipe`.
    - Nur asynchron, mit Status, Ergebnis und Abbruch. Keine Job-Liste ohne
      Konten.
    - Zufällige Kennungen mit 128 Bit: `jobID` und eine eigene `recipe_id`,
      die Grundlage für Permalink und Bug-Report (Q15, F15).
11. **`recipe.json` und `citation.bib` (F13).**
    - `recipe.json` hat dasselbe Schema mit `steps: []`.
    - `citation.bib` ist `@misc` je Datensatz aus den Registry-Feldern.
    - Nebenfund: `sci:doi` trägt heute eine URL statt des DOI-Namens [P].
12. **Checkliste Punkt 9 v2 (F14):** ein parametrisierter Test je
    Registry-Eintrag auf dem Gerüst von `synthetic_chain.py`. Die Zuordnung
    Datensatz → Operator steht im Test, dazu ein Wächtertest.
13. **`decomp.py` (§12):** wird nur beschrieben. Eine Lücke für später: Der
    Worker-Einstieg liegt in `jobs`, und `jobs` darf `datasets` nicht
    importieren.

---

## 1. Kontext und Frage

Der M4-Plan setzt das Ziel so: Ein Rezept beschreibt eine Verarbeitung so
vollständig, dass dieselbe Operator-Implementierung es als Vorschau im `tiler`,
als Job im `worker` und offline im lokalen Runner mit übereinstimmendem Ergebnis
ausführt. Ein zweiter identischer Auftrag kommt aus dem Cache.
`architekturplan.md` 7.1–7.3 gibt Rezept, Registry und Ausführungsstufen nur in
Umrissen vor. Dieses ADR legt die Form vor, bevor Code entsteht (M4-07). Die
neun Punkte des Auftrags stehen in §4 bis §12.

## 2. Kriterien

| # | Kriterium | Quelle |
|---|---|---|
| K1 | Das Rezept beschreibt die Verarbeitung vollständig: Eingaben mit Fassung, Schritte, Ausgabe, Versionen | architekturplan 7.1; Prinzip 2.8 |
| K2 | Der Worker-Kern bleibt rein: keine Datenbank, Queue, Objektspeicher, interne API, kein Import aus `gateway` | B9; 3.1; Q4; `adr/0011` §6.2 |
| K3 | Jede Adresse läuft durch `check_url`, und die GDAL-Konfiguration aus `gateway` gilt in jedem Lesethread | B8; M4-Plan §1.2 |
| K4 | Dieselbe Implementierung bedient T1, T2 und T2L; die Übereinstimmung ist als Zahl prüfbar | architekturplan 7.3; M4-Abnahme 1 |
| K5 | Nach außen gibt es keinen Rezept-Hash und keine AOI, nur zufällige Kennungen | Q8, Q9; M3-16 |
| K6 | Ein Cache-Treffer gibt es nur mit der Fassung aller Eingaben, lokale Ergebnisse kommen nie in den Cache | Q11, Q12 |
| K7 | Nichts gilt still: Fähigkeiten werden ausdrücklich freigeschaltet, Unbekanntes wird abgewiesen | B10; `adr/0005` Regel I |
| K8 | Ein neuer Operator ist eine Registrierung, ohne Frontend-Code und ohne neue Route | architekturplan 7.2 |
| K9 | Wenige bewegliche Teile und neue Abhängigkeiten nur mit Grund (Lock-Datei, M4-00b) | architekturplan 1.1 Ziel 6; M4-Plan §1.2 |
| K10 | „Standards raus“: OGC API Processes und openEO bleiben anschlussfähig | Prinzip 2.6; architekturplan 7.1, 7.6 |

---

## 3. Befunde

### 3.1 Fassung der Eingaben je Datensatz — [M]

| Datensatz | am Item | am Asset ohne Anfrage | Kopfzeilen der Datei | Folge |
|---|---|---|---|---|
| `sentinel-2-c1-l2a` (Earth Search) | `updated` (= `created`) | **`file:checksum`** (Multihash SHA2-256, `1220…`) und `file:size` je Asset | `ETag` (S3-Multipart, `"…-12"`) und `Last-Modified`, auch auf einen Range-`GET` (`206`) | eine inhaltsbasierte Fassung ohne eigene Anfrage |
| `sentinel-2-l2a-zarr3` (EOPF) | `updated`, `published`, `deprecated` (version-Extension); die Item-ID enthält Baseline und Verarbeitungszeit | keine Prüfsumme | **kein** `ETag`, kein `Last-Modified`, weder auf `HEAD` noch auf Range-`GET` | nur `updated` |
| `cop-dem-glo-30` (eigene Items) | weder `updated` noch Prüfsumme (`cop_dem_bucket._item`, Z. 205–239 [P]) | — | `ETag` (32 Hex-Zeichen), `Last-Modified` 09.05.2022 | nur ein ETag per `HEAD`, eine Anfrage je Asset |

- Die EOPF-Messung bestätigt `adr/0007` §12.8 („Kein `ETag`, kein
  `Cache-Control`, kein `Last-Modified`“) für Produkte vom 01.10.2026.
- Das Lauf-Protokoll des DEM (`source_version`, ETag von `tileList.txt`) gibt
  die Fassung der *Liste* an, nicht der Kachel.

### 3.2 Band-Math in rio-tiler — [P] und [M]

**Wie es gerechnet wird [P].**
- `rio_tiler/expression.py` Z. 98–139 wertet jeden Block mit
  `numexpr.evaluate` aus und ersetzt das Ergebnis mit `numpy.nan_to_num`.
- `models.py` Z. 689–710 ruft das auf und legt die Maske als ODER aller
  Bandmasken an (Z. 710).
- `io/rasterio.py` Z. 354–375: Erst wird gelesen, also auf das Kachelraster
  gewarpt, dann kommt die Expression.
- Dieselbe Funktion `ImageData.apply_expression` nutzt auch `ZarrReader._merged`
  (`readers/zarr_reader.py`).

**Datentypen und Grenzfälle [M]** (§17.3):

| Fall | Ergebnis |
|---|---|
| `(n-r)/(n+r)` mit `uint16` in numpy, `r=3000`, `n=2000` | **12.9072**, weil `n-r` überläuft |
| dasselbe in numexpr | −0.2, weil auf float64 erweitert wird |
| `0/0` | NaN, nach `nan_to_num` **0.0**, also ein gültiger Wert und keine Lücke |
| float32 gegen float64 als Eingabe | bis 1,45·10⁻⁷ Unterschied |
| numexpr mit 1 oder 8 Threads, blockweise oder ganz | bitgleich |

**Folge [A].** „Dieselbe Implementierung“ muss buchstäblich dieselbe Funktion
sein: dieselbe Rechenmaschine (numexpr), derselbe Eingabetyp und dieselbe
Regel für `0/0`. Eine zweite Implementierung in numpy wiche ab.

### 3.3 T1 gegen T2 bei Band-Math — [M]

**Aufbau** (§17.4):
- Synthetisches COG, 4096² px, 10 m, EPSG:32632, zwei Bänder `uint16` mit
  `scale=0.0001` und `offset=-0.1` wie bei Sentinel-2 C1, Übersichten 2/4/8.
- NDVI `(b2-b1)/(b2+b1)` über rio-tiler mit `unscale=True`.
- T2: einmal auf dem nativen Raster gerechnet, dann mit derselben
  Resampling-Methode auf das Kachelraster gewarpt.
- T1: `Reader.tile(…, expression=…)`.

| Resampling | Zoom | Kacheln | Pixel | identisch | p99 \|Δ\| | max \|Δ\| |
|---|---|---|---|---|---|---|
| nearest | z14 | 40 | 2 621 440 | **100 %** | 0 | 0 |
| nearest | z13 | 40 | 2 621 440 | **100 %** | 0 | 0 |
| nearest | z12 (Übersicht ×2) | 25 | 1 638 400 | 0,005 % | 0,37 | 64,7 |
| nearest | z11 (Übersicht ×4) | 9 | 471 501 | 0,004 % | 0,39 | 4,6 |
| bilinear | z14 | 40 | 2 621 440 | 0 % | 0,0054 | 0,033 |
| bilinear | z13 | 40 | 2 621 440 | 0 % | 0,018 | 0,26 |

- Z13 liest bei 13 m Kachelauflösung noch die native Ebene. Die nächste
  Übersicht (20 m) wäre zu grob.
- Die großen Maxima stammen von Pixeln mit Nenner nahe null.
- Das synthetische Rauschen ist stark (60 bzw. 90 DN). Die Zahlen an
  Übersichtsstufen zeigen deshalb das Prinzip, keine Toleranz für echte Daten.

### 3.4 Reprojektion: Plan und Threads — [M]

**NDVI-Ergebnis** aus §3.5 (8192², float32) nach EPSG:4326 (§17.5). Verglichen
wird jeweils der Hash des ganzen Ergebnisses:

| Vergleich | nearest | bilinear | cubic |
|---|---|---|---|
| `reproject` mit 1 gegen 4 Threads | bitgleich | bitgleich | bitgleich |
| `WarpedVRT` blockweise mit 1 gegen 4 Threads | bitgleich | bitgleich | bitgleich |
| ganz (`reproject`) gegen blockweise (`WarpedVRT`, 1024 px) | 98,0 % identisch, p99 0,046 | 0,007 % identisch, p99 0,0066 | 0,002 % identisch, p99 0,0083 |
| ganz gegen blockweise, beide `reproject` mit `tolerance=0` | — | 0,2 % identisch, p99 0,0029 | — |
| ganz `tolerance=0` gegen ganz `tolerance=0.125` | — | 0,3 % identisch, p99 0,012 | — |

**Synthetisches DEM**, 3600² float32, EPSG:4326, 1″, nach EPSG:32632 mit 30 m
(§17.6):

| Methode | ganz gegen blockweise (1024 px) | 4 Threads gegen 1 |
|---|---|---|
| nearest | 97,7 % identisch, p99 2,4 m, max 13,1 m | bitgleich |
| bilinear | 0,15 % identisch, p99 **0,20 m**, max **0,70 m** | bitgleich |
| cubic | 0,12 % identisch, p99 0,24 m, max 0,83 m | bitgleich |

**Zeiten** für die 64 MP Ausgabe, 1 Thread: `reproject` ganz 6,5 s (nearest),
11,1 s (bilinear), 11,6 s (cubic); `WarpedVRT` blockweise 3,4 s, 9,0 s, 10,6 s.
Mit 4 Threads ganz 3,1 s, 4,1 s, 5,1 s. Mit `tolerance=0` dauert `reproject`
bilinear ganz 20,6 s statt 9,2 s.

**Folge [A].**
- Das Ergebnis einer Reprojektion hängt vom Ausführungsplan ab: Blockung,
  Fehlerschwelle der Näherung und `warp_mem_limit` (es steuert die interne
  Teilung).
- Die Zahl der Threads ändert nichts.
- `WarpedVRT` lässt `tolerance=0` nicht zu (`ObjectNullError` beim Anlegen,
  §17.5).
- Der Plan ist deshalb Teil der Operator-Implementierung und wird mit
  `op_version` versioniert, nicht pro Maschine gewählt.

### 3.5 Speicher und Zeit eines T2-Laufs — [M]

**Aufbau** (§17.7): synthetisches COG, 8192² px, zwei Bänder `uint16`. Band-Math
wie in §3.2, Ausgabe float32 als gekacheltes GeoTIFF auf lokaler Platte,
1 Lesethread.

| Weg | `GDAL_CACHEMAX` | Spitze RSS | Zeit | Ergebnis |
|---|---|---|---|---|
| ganzes Array | 64 MB | 3168 MB | 23,9 s | Hash `0e5bdc12…` |
| ganzes Array | Standard (5 % RAM) | 3425 MB | 22,1 s | gleich |
| Blöcke 512 px | 64 MB | **110 MB** | 8,8 s | gleich |
| Blöcke 1024 px | 64 MB | **148 MB** | 9,8 s | gleich |
| Blöcke 2048 px | 64 MB | 303 MB | 11,4 s | gleich |
| Blöcke 1024 px | Standard | 400 MB | 8,3 s | gleich |

- Der Prozess allein (Python, rasterio, numexpr) belegt 70 MB.
- Die Blockgröße ändert bei punktweisen Operatoren das Ergebnis nicht.
- Der Standard-Cache von GDAL (5 % des RAM) kostet in einem Worker mehrere
  hundert MB, wenn er nicht gesetzt ist.
- Der synchrone Zuschnitt brauchte für eine ganze Kachel 2,3 GB, weil die COG
  nach D3 im Speicher entstehen muss (`plans/m3-18-…` §10.3). Ein Job darf
  dagegen auf lokale Platte schreiben.

### 3.6 GDAL-Optionen in Threads — [M] und [P]

**Gemessen** (§17.8), Option gesetzt mit `rasterio.Env(GDAL_HTTP_TIMEOUT="15")`:

| Wo `Env` betreten wurde | sieht ein Thread, der danach startet, die Option? | sieht ein anderer Thread sie? |
|---|---|---|
| Hauptthread | ja, auch ein Thread, der vorher gestartet wurde | ja (prozessweit) |
| anderer Thread | **nein** (`ThreadPoolExecutor`, `threading.Thread`) | nein |
| rio-tiler `create_tasks(threads=2)` aus dem Hauptthread | ja | — |
| zwei Threads mit eigenen `Env` (11 und 22) | jeder sieht seinen Wert | — |

**Gelesen.**
- Das Verhalten ist so gebaut [P]: `rasterio/_env.pyx` Z. 185–188 ruft im
  Hauptthread `CPLSetConfigOption` (prozessweit), sonst
  `CPLSetThreadLocalConfigOption`.
- Weitere Stellen:
  - **dask 2026.8.0:** Der Thread-Scheduler gibt nur `contextvars` weiter, kein
    `threading.local` (`threaded.py` Z. 39–59) [P]. Aus einem
    Nicht-Hauptthread kamen 16 von 16 Aufgaben ohne Option an [M, Hilfsagent,
    Skript nur im Kratzverzeichnis].
  - **rioxarray 0.23:** ruft nirgends `rasterio.Env` auf [P].
  - **rio-tiler:** `create_tasks` und `mosaic_reader` geben kein `Env` weiter;
    `MultiBaseReader` dagegen schon, über `@inherit_rasterio_env`
    (`utils.py` Z. 906–935) [P].
  - **GDAL-eigene Worker-Threads** (`GDAL_NUM_THREADS` für GTiff): Sie nutzen
    eine Momentaufnahme der HTTP-Optionen vom Öffnen
    (`cpl_vsil_curl.cpp` v3.12.2 Z. 479). `GDAL_HTTP_UNSAFESSL` und der
    User-Agent werden dagegen zur Anfragezeit im ausführenden Thread gelesen
    (`cpl_http.cpp` Z. 505–541) [P].
- **Der heutige `tiler` ist nicht betroffen [M][P]:** Kachel, Statistik und
  Download lesen auf demselben Thread, der vorher das `Env` mit den Optionen
  aus `gateway` betreten hat.
  - Belegstellen [P]:
    - Kachel: `titiler/core/factory.py` Z. 913, im synchronen Endpunkt
      `def tile` (Z. 866), der im Thread-Pool läuft.
    - Statistik: `access/tiles.py` Z. 403, in `once()` unter
      `run_in_threadpool`.
    - TileJSON: `access/tiles.py` Z. 297, synchroner Endpunkt.
    - Download: `access/download.py` Z. 1397, mit `mosaic_reader(threads=1)`
      (Z. 667–668); `create_tasks` ruft bei `threads ≤ 1` im aufrufenden
      Thread auf (`rio_tiler/tasks.py` Z. 52–61).
  - Gemessen (§17.11): Eine Sonde in `DatasetReader.read` und
    `WarpedVRT.read` lief über die echten Routen mit dem Gerüst aus
    `synthetic_chain.py`, je drei Routen für drei Datensätze. Alle 15
    GDAL-Lesezugriffe liefen auf einem Nicht-Hauptthread, und in allen galten
    `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`, die erlaubten Endungen und die
    Zeitlimits aus `gateway`.
  - Zarr-Kacheln und -Statistik lesen gar nicht über GDAL, sondern über
    `GatewayStore`. Die drei GDAL-Lesezugriffe beim Zarr-Download sind die
    Prüflesungen der geschriebenen COG.
  - Einschränkung: `TestClient` hält die Ereignisschleife in einem eigenen
    Thread, uvicorn im Hauptthread. Synchrone Endpunkte laufen in beiden
    Fällen im Thread-Pool. Ein lesender `async`-Endpunkt existiert nicht.

### 3.7 Welche Adressen GDAL abruft — [M]

Gemessen gegen einen lokalen Range-Server mit derselben synthetischen COG
(§17.9), jeder Fall in einem frischen Prozess (der VSI-Cache von GDAL gilt
prozessweit). Gelesen wurde ein Fenster von 512² px.

| Einstellung | Anfragen | was |
|---|---|---|
| `gateway.gdal.gdal_options` | **3** | `HEAD` der Datei, Range-`GET` auf den Kopf (32 kB), Range-`GET` auf die Daten |
| GDAL-Standard | 13 | dieselben 3 (Kopf in 16 kB), dazu `GET /` (Verzeichnis-Listing) und 9 `HEAD` auf Sidecars (`.tif.aux.xml`, `.aux`, `.AUX`, `.tif.aux`, `.tif.AUX`, `.xml`, `.XML`, `.tif.msk`, `.tif.MSK`) |
| `gdal_options`, Adresse leitet per `302` auf einen anderen Host um | 6 | jede der 3 Anfragen erst an die geprüfte Adresse (`302`), dann an den fremden Host (`200`/`206`) |

- Der dritte Fall ist die Lücke, die `gateway/gdal.py` schon beschreibt:
  GDAL folgt bis zu 10 Weiterleitungen selbst (`cpl_http.cpp` Z. 2376, 2386)
  [P].
- Eine Option, die das für `/vsicurl/` abschaltet, wurde nicht gefunden. Die
  Lücke schließt erst der Egress-Proxy aus M6 (B8, Stufe 2).

### 3.8 Bausteine für das Lesen — [P], Zeilen in den Wheels von PyPI

| Baustein | Version, Lizenz | liest wie | GDAL-Optionen je Thread | jede URL durch `check_url` | Zarr | neue Abhängigkeiten |
|---|---|---|---|---|---|---|
| eigene Blockschleife über `readers` | — | `CogReader` bzw. `ZarrReader`, je Block `part()` | so gut wie die Regel in §7.3 | ja: `AssetPath`/`ZarrAsset` entstehen nur über `check_url` (`readers/cog.py`, `zarr_reader.py`) | ja, jeder Chunk über `gateway` | keine |
| odc-stac | 0.5.3 (30.07.2026), Apache-2.0 | `rasterio.open(uri)` je Chunk (`odc/loader/_rio.py` Z. 601) | ja: im Aufrufer erfasst, je Aufgabe neu gesetzt (`_stac_load.py` Z. 507; `_builder.py` Z. 473, 496, 930) | über `patch_url`, läuft im aufrufenden Thread je Band (`_stac_load.py` Z. 426–427) | **über `fsspec`, an `gateway` vorbei** (`_zarr.py` Z. 167); nur Zarr-v2-Spezifikationen (Z. 595–609) | dask, pandas, pystac, odc-geo, odc-loader (importiert `fsspec` beim Laden, `_zarr.py` Z. 14) |
| rioxarray + dask | 0.23 / 2026.8.0, Apache-2.0 / BSD-3-Clause | `open_rasterio(chunks=…)` | nein, außerhalb des Hauptthreads [M] | nur, wenn vorher geprüft und als `/vsicurl/`-Pfad übergeben | nicht über diesen Weg | dask (mit `fsspec` als Kernabhängigkeit) |

### 3.9 Kanonisierung — [P] und [M]

- **RFC 8785** (JCS) ist *Informational* und eine *Independent Submission*
  vom Juni 2020 [P].
  - Er setzt I-JSON (RFC 7493) voraus.
  - Zahlen werden wie in ECMAScript ausgegeben.
  - Schlüssel werden nach UTF-16-Codeeinheiten sortiert.
  - NaN und Infinity sind Fehler.
  - Unicode-Normalisierung liegt ausdrücklich außerhalb des RFC.
- **Python** [P][M]:
  - `rfc8785` 0.1.4 (Trail of Bits): Apache-2.0, ohne Abhängigkeiten, Beta,
    letzte Version vom 27.09.2024. Es stimmte in allen Fällen und in 500 000
    Zufallszahlen mit dem Referenz-Kanonisierer überein. Ganzzahlen außerhalb
    ±(2⁵³−1) weist es ab.
  - Naives `json.dumps(sort_keys=True, separators=(",", ":"))` weicht ab bei
    `100.0`, `-0.0`, `1e16`, `1e-7` und bei Schlüsseln außerhalb der BMP.
    Gleich ist es bei `0.1`, `1e21`, `5e-324`, `8.123456789` und bei
    ASCII-Schlüsseln.
  - `pydantic.model_dump_json` ist keines von beiden.
  - `json.loads` und pydantic verwerfen doppelte Schlüssel still; `1e400` wird
    still zu `inf`.

### 3.10 JSON Schema, OGC, openEO, STAC — [P]

- **pydantic 2.13** erzeugt JSON Schema Draft 2020-12 (`json_schema.py` Z. 267),
  ohne `$schema` auszugeben [P].
  - Eine Discriminated Union wird zu `oneOf` mit OpenAPI-`discriminator`; das
    ist in 2020-12 nur eine Annotation.
  - Der Lax-Modus nimmt `"20"` als float an, `jsonschema` nicht [M].
  - `pattern` prüft pydantic mit Rust-`regex`, JSON Schema verlangt
    ECMA-262 [M].
- **OGC API Processes 1.0** (Commit `7a6bad0` vom 07.01.2022, der Stand mit dem
  Link auf das angenommene Dokument) [P]:
  - Core verlangt: Landing Page, API-Definition, `/conformance`, `/processes`,
    `/processes/{id}`, `POST /processes/{id}/execution`, `/jobs/{jobID}` und
    `/jobs/{jobID}/results`.
  - `GET /jobs` gehört zur Klasse *job-list*, `DELETE /jobs/{jobID}` zu
    *dismiss*.
  - Die Kennung `jobID` hat kein Format, nur „local identifier“.
  - Statuswerte: `accepted`, `running`, `successful`, `failed`, `dismissed`.
  - Asynchron mit `Prefer: respond-async` antwortet der Dienst mit 201 und
    `Location`.
  - Der Text nennt JSON Schema 2020-12 für Eingaben. Das normative
    `schema.yaml` ist aber eine Teilmenge des OpenAPI-3.0-Schemas
    (`exclusiveMinimum` als boolean). Das ist ein Widerspruch in der
    Spezifikation.
  - Version 2 (18-062r3) ist ein Entwurf und nennt `id` statt `jobID`; die
    öffentliche Kommentierung lief 08–09/2026 [S].
- **openEO** [P]:
  - API 1.3.0, Apache-2.0. Der Prozessgraph besteht aus Knoten mit
    `process_id`, `arguments`, `from_node` und `result: true` und hat
    Parameter-Schemas nach draft-07.
  - `resample_spatial` kennt die Methoden von gdalwarp, Vorgabe `near`.
  - Batch-Status: `created`, `queued`, `running`, `canceled`, `finished`,
    `error`. Das ist ein anderes Vokabular als bei OGC.
- **STAC-Extensions** [P]:
  - *processing* v1.2.0: `processing:lineage`, `processing:software` und
    `processing:expression` (`format` u. a. `rio-calc`), dazu der Link
    `derived_from`.
  - *file* v2.1.0: `file:checksum` als Multihash.
  - *scientific* v1.0.0: `sci:doi` ist der DOI-Name und „MUST NOT be a DOIs
    link“; der Link gehört als `cite-as` dazu.
  - *raster* v2.0.0: Skalierung als `raster:scale`/`raster:offset` in `bands`
    (STAC 1.1).
- **Nebenfund im Code [P]:**
  - Die Registry trägt `doi` als URL (`catalog/datasets.py` Z. 68, 255, 450).
  - `catalog/collection.py` Z. 87 schreibt sie unverändert nach `sci:doi`. Das
    verletzt die scientific-Extension (§10).
- **BibTeX** [P]:
  - DataCite schreibt Datensätze als `@misc` (bolognese `utils.rb` Z. 482).
  - `@dataset` kennt nur biblatex ab 3.13. `plain.bst` fällt auf `@misc`
    zurück.
  - `doi.org` und `api.datacite.org` sind aus der Sitzung gesperrt.

### 3.11 Was der Code heute mitbringt — [P]

- **Skalierung im COG [M]:** Der Earth-Search-COG trägt `scale 0.0001` und
  `offset −0.1` selbst als GDAL-Tags, mit Blockgröße 1024 und Übersichten
  2–16. `rio-tiler unscale=True` greift also.
- **Skalierung im EOPF-Store [M]:** Die Variablen sind `uint16` mit
  `scale_factor 0.0001`, `add_offset −0.1` und `_FillValue 0`.
  `readers/zarr_reader.py` Z. 634 öffnet mit `xarray.open_zarr` und
  Standard-Dekodierung. Gemessen wird daraus float64-Reflexion, der Füllwert
  wird NaN (§17.10).
- **Ein Asset je Kachel:** Die Kachelroute nimmt genau einen Asset-Schlüssel
  (`api/tiler.py` Z. 427 auf dem Stand nach PR #110, nach M4-01a Z. 327).
  - Zarr kann mehrere Variablen einer Gruppe kombinieren (`"SR_10m:b04,b08"`).
  - Bei Earth Search liegen Rot und NIR in zwei Dateien (`B04.tif`,
    `B08.tif`). Band-Math über zwei COG-Assets braucht in T1 also einen
    Mehr-Asset-Weg (Aufgabe für M4-09, §6.2).
- **Haken in TiTiler:** `TilerFactory.process_dependency` (`factory.py` Z. 317)
  bekommt in der Kachelroute (`def tile` Z. 853, angewandt Z. 929–930) das
  fertige `ImageData` jeder Kachel. Dort kann
  ein Operator-Kern als „Algorithmus“ hängen. `access` darf `processing` nicht
  importieren. Den Haken reicht deshalb `api/tiler.py` herein, so wie heute
  die Pfad-Abhängigkeit.
- **Wer den Registry-Eintrag in den Worker bringt:**
  - `jobs` darf nur `processing` importieren (`.importlinter`, Vertrag `jobs`).
  - `processing` erreicht aus `catalog` nur `catalog.registry` (M4-Plan §1.2).
  - Der Worker-Kern bekommt deshalb alles, was er vom Datensatz braucht, im
    Rezept, nicht aus der Registry.

---

## 4. Rezept (Punkt 1)

### 4.1 Drei Schichten

| | Wer erzeugt | Inhalt | gehashed | nach außen |
|---|---|---|---|---|
| **Auftrag** | Panel, API-Client, Chatbot (`propose_recipe`) | `recipe_version`, Eingaben als Datensatz, Item-Gruppen und Assets, `aoi`, `steps`, `output` | nein | ja (Eingabe) |
| **Rezept** | `api` bei der Annahme: Items holen (Item-Quelle aus M4-01a), `resolve_asset`, Fassung, Bandangaben, Anwendbarkeit, Lizenz | Auftrag plus `resolved` je Eingabe; `op_version` je Schritt | ja (Kern, §4.5) | als `recipe.json` beim Ergebnis, ohne Hash |
| **Provenienz** | `jobs` bzw. der lokale Runner nach dem Lauf | `execution` (`cloud`/`local`), `runner_version`, `self_attested`, Software-Versionen, Zeiten, Attribution, Zitierangabe | nein | ja, beim Ergebnis |

**Optionen:**

| | R1 drei Schichten, lineare Schritte | R2 ein Dokument mit optionalen Feldern | R3 openEO-Prozessgraph als Rezept |
|---|---|---|---|
| K1 vollständig | ✓ | ✓ | ✓ |
| K2 Kern rein (alles Nötige im Rezept) | ✓ | ~ (welche Felder sind bei Ausführung gesetzt?) | ✓ |
| K5 kein Hash/keine AOI nach außen | ✓ | ✓ | ✓ |
| K7 Unbekanntes abweisen | ✓ (Modell je Schicht, `extra="forbid"`) | ~ | ~ (Graph erlaubt beliebige `process_id`, Prüfung dazu nötig) |
| K8 neuer Operator = Registrierung | ✓ | ✓ | ✓ |
| K9 überschaubar | ✓ | ✓ | ✗ (DAG, `from_node`, Parameter-Referenzen) |
| K10 anschlussfähig | ~ (Übersetzung nach openEO: Kette → Graph ist mechanisch [A]) | ~ | ✓ |

**Empfehlung: R1.** M4 braucht keine Verzweigung: Q6 nennt Band-Math und
Reprojektion, Q7 Export und Mosaik. Eine lineare Kette lässt sich später
mechanisch in einen openEO-Graphen übersetzen, umgekehrt nicht [A].

### 4.2 Skizze des Rezepts (Vorschlag, nicht gebaut)

```json
{
  "recipe_version": 1,
  "inputs": [
    {
      "name": "s2",
      "dataset": "sentinel-2-c1-l2a",
      "groups": [["<item-id>"]],
      "assets": ["red", "nir"],
      "resolved": [
        {
          "asset": {"dataset_id": "sentinel-2-c1-l2a", "item_id": "<item-id>", "asset": "red",
                    "reader": "cog", "href": "https://…/B04.tif", "variable": null, "crs": "EPSG:32632"},
          "version": {"kind": "file:checksum", "value": "1220…"},
          "bands": [{"data_type": "uint16", "nodata": 0, "scale": 0.0001, "offset": -0.1}]
        }
      ]
    }
  ],
  "aoi": {"type": "Polygon", "coordinates": ["…"]},
  "steps": [
    {"op": "band_math", "op_version": 1, "params": {"expression": "(nir-red)/(nir+red)"}},
    {"op": "reproject", "op_version": 1, "params": {"crs": "EPSG:3035", "resolution": 10, "resampling": "bilinear"}}
  ],
  "output": {"kind": "raster", "format": "cog", "dtype": "float32"}
}
```

- **`asset` ist `ResolvedAsset` aus `adr/0011` §6.4, unverändert.** `version`
  und `bands` stehen daneben, nicht darin.
  - `version` braucht für das DEM eine Anfrage über `gateway`, und
    `resolve_asset` ist rein (kein Netz).
  - `bands` kommt aus dem Item (`raster:bands` bzw. `bands`). Der Worker
    vergleicht es mit der Datei (§5.4).
- `groups` übernimmt die Gruppierung des Downloads (P19, M3-17). So beschreibt
  dasselbe Schema auch Export und Mosaik je Überflug (Q7). Die Suche dafür
  läuft in `api`, nie im Worker (`adr/0011` §8.1).
- Eingaben heißen (`name`). Band-Math adressiert sie über ihre Asset-Schlüssel.
  Die Übersetzung in rio-tilers `b1…bn` ist Sache des Operators (M4-09).
- Mehrere Datensätze in einem Rezept sind im Schema möglich. M4 braucht sie
  nicht. Die Lizenzkombination (architekturplan 7.1, letzte Zeile) prüft `api`
  bei der Annahme.

### 4.3 Versionierung

- **`recipe_version`** ist eine ganze Zahl. Eine inkompatible Änderung erhöht
  sie.
  - Der Kern nimmt genau die Versionen an, die er kennt.
  - Eine Migration auf Vorrat gibt es nicht: Rezepte laufen nach 7 Tagen ab
    (Q10), und der Runner reproduziert mit festem Tag (Q12) [A].
- **`op_version`** je Schritt steigt, sobald derselbe Eingang ein anderes
  Ergebnis gäbe: neue Formel, neuer Blockplan (§3.4), neue Regel für `0/0`.
  - Ein Auftrag mit einer Version, die die Plattform nicht mehr führt, wird mit
    `422` abgewiesen, nicht still hochgestuft (K7).
- **Schema der Auftragsseite:** Felder kommen nur mit Version hinzu. Jedes
  Modell ist `extra="forbid"`.

### 4.4 Kanonisierung und Hash

Der Hash dient nur intern als Cache- und Idempotenz-Schlüssel (Q8). Weder ein
Browser noch der Runner berechnet ihn: Lokale Ergebnisse kommen nie in den Cache
(Q12). Das senkt die Anforderung an Interoperabilität.

**Verfahren:**

1. Den Auftrag parsen: doppelte Schlüssel abweisen (`object_pairs_hook`),
   `NaN`, `Infinity` und Zahlen außerhalb von float64 abweisen (I-JSON, §3.9).
2. Mit den pydantic-Modellen validieren. `strict=True` ist nötig, sonst gilt
   `"20"` als float (§3.10).
3. Den Kern des Rezepts (§4.5) als Python-Daten ausgeben
   (`model_dump(mode="json")`).
4. Kanonisch serialisieren und SHA-256 bilden. Das Ergebnis trägt eine
   Verfahrenskennung, etwa `c1:<hex>`, damit ein späterer Wechsel des
   Verfahrens alte Schlüssel nicht still trifft.

**Optionen für Schritt 4:**

| | H1 RFC 8785 mit `rfc8785` | H2 eigene JCS-Implementierung | H3 `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)` |
|---|---|---|---|
| deterministisch für validierte Rezepte | ✓ | ✓ | ✓: Schlüssel sind feste ASCII-Namen, float-Felder sind immer float [A] |
| bytegleich mit RFC 8785 | ✓ [M] | ✓, wenn gegen die Testvektoren des RFC geprüft | ✗ bei `100.0`, `-0.0`, `1e-7`, Nicht-BMP-Schlüsseln [M] |
| Abhängigkeit (K9) | neu: klein, ohne eigene Abhängigkeiten, Apache-2.0, Beta, letzte Version 09/2024 | keine; rund 60 Zeilen mit Zahlenformat nach ECMA-262 | keine |
| Risiko | Pflege beim Herausgeber ruhig | Zahlenformat fehleranfällig | einziger Unterschied: `-0.0` und `0.0` geben zwei Schlüssel, also nur einen Cache-Fehlschuss |

**Empfehlung: H3, solange der Hash nur intern ist.** Wird er je außerhalb von
Python gebraucht (Abgleich in einem anderen Werkzeug), dann H1 mit neuer
Verfahrenskennung. Das ist eine Zeile und ein Lock-Eintrag.

**Kanonisierungsregeln, Verfahren `c1` (angenommen mit F2, Auflage F2):**

1. Eingabe ist das validierte Modell (`strict=True`, `extra="forbid"`),
   ausgegeben mit `model_dump(mode="json")`.
2. **Schlüsselreihenfolge:** `sort_keys=True`, also nach den Codepunkten der
   Python-Zeichenkette, rekursiv. Die Modelle haben nur ASCII-Schlüssel; dort
   gleicht das der UTF-16-Ordnung aus RFC 8785.
3. **Trennzeichen:** `separators=(",", ":")`, kein Leerraum.
4. **`ensure_ascii=False`:** Nicht-ASCII-Zeichen in Werten bleiben als Zeichen
   stehen; die Bytes sind UTF-8. Keine Unicode-Normalisierung (wie RFC 8785).
5. **`allow_nan=False`:** NaN und ±Infinity sind ein Fehler (I-JSON).
6. **Zahlen:**
   - Ein float-Feld ist immer float. `1` und `1.0` werden beide zu `1.0` [M].
   - Ein int-Feld nimmt nur Ganzzahlen; `1.0` und `true` werden abgewiesen
     [M].
   - `-0.0` wird vor dem Serialisieren zu `0.0`. pydantic selbst lässt es als
     `-0.0` stehen [M].
   - Floats stehen in der kürzesten Form, die Python ausgibt (`repr`): `1e-07`,
     `1e+20` [M]. RFC 8785 schriebe `1e-7` und `100000000000000000000`; das
     ist der Grund für die eigene Kennung `c1`.
7. **Arrays** behalten ihre Reihenfolge. Koordinaten werden nicht gerundet
   (unten).
8. **Hash:** SHA-256 über die UTF-8-Bytes, Hex in Kleinbuchstaben, Präfix
   `c1:`.
9. **Test (M4-07, Auflage F2):** feste erwartete Hashwerte für einige
   synthetische Rezepte. Abgedeckt sind die Grenzfälle `1`/`1.0`, `-0.0`,
   `1e-7`, Nicht-ASCII in einem Wert und eine andere Schlüsselreihenfolge in
   der Eingabe, die denselben Hash geben muss.

**Was nicht normalisiert wird:**
- AOI-Koordinaten werden nicht gerundet. Zwei gezeichnete AOIs, die sich in der
  achten Nachkommastelle unterscheiden, sind zwei Aufträge. Ehrlich neu rechnen
  ist billiger, als still zu runden (K7) [A].
- Die Reihenfolge von Arrays bleibt, denn sie trägt Bedeutung (Schritte,
  Gruppen).

### 4.5 Was in den Cache-Schlüssel geht

Kern = `recipe_version`, `inputs` (mit `resolved`, `version`, `bands`), `aoi`,
`steps` (mit `op_version`), `output`. Dazu kommt ein Block `engine`:

| Variante | Inhalt von `engine` | Folge |
|---|---|---|
| E1 | nichts | ein GDAL-Update, das den Warp ändert, liefert alte Ergebnisse unter neuem Code |
| **E2** | Version von `earthx.processing` (Kernpaket), GDAL, rasterio, numexpr und numpy (numpy: Auflage F3) | gemessen ändern Plan und Näherung das Ergebnis (§3.4); ein Wechsel von GDAL kann das auch |
| E3 | die ganze Image-Version | jedes Deployment leert den Cache; bei 7 Tagen Frist vertretbar, aber unnötig grob |

**Empfehlung: E2.** Nie im Schlüssel: Kennungen nach außen, Zeitpunkte, die
Provenienz, Attributionstexte (das `{year}` ändert sich zum Jahreswechsel).

**Treffer nur, wenn jede Eingabe ein `version` trägt (Q11).** Fehlt eines, wird
gerechnet und das Ergebnis nicht als Treffer für Spätere abgelegt. Ob es
trotzdem für den Auftraggeber im Speicher liegt, ist Sache von `adr/0015`.

### 4.6 Fassung der Eingaben (Q11)

**Vorschlag je Asset, in dieser Reihenfolge:**

1. **`file:checksum`** am Asset. Inhaltsbasiert, ohne Anfrage. Gilt für Earth
   Search (§3.1).
2. **ETag** per `HEAD` über `gateway`, bei der Annahme in `api`. Eine Anfrage je
   Asset. Gilt für das DEM.
3. **`updated`** am Item. Gilt für EOPF. Die Item-ID enthält dort die
   Verarbeitungszeit; ein neu prozessiertes Produkt ist also ein neues Item
   [M].
4. Sonst: `null`, und es gibt keinen Treffer.

**Restrisiko [A].**
- Ändert sich eine Quelle zwischen Annahme und Lesen, trägt das Ergebnis die
  ältere Fassung. Bei Zarr ließe sich das je Chunk prüfen, bei GDAL nicht: Es
  sendet kein `If-Match`.
- Bei Archivdaten mit festen Pfaden ist das selten. Es steht in der Provenienz
  als „Fassung bei Annahme“.

**Je Datensatz:**

| Datensatz | Fassung | Kosten |
|---|---|---|
| `sentinel-2-c1-l2a` | `file:checksum` | keine Anfrage |
| `sentinel-2-l2a-zarr3` | `updated` | keine Anfrage |
| `cop-dem-glo-30` | ETag per `HEAD` | 1 Anfrage je Kachel und Job |

`file:checksum` ist eine Ergänzung zu Q11, das nur „ETag oder `updated`“
nennt (F4).

### 4.7 AOI und Datenschutz

- Ein Rezept mit AOI ist personenbezogen (Q8) und läuft nach 7 Tagen ab (Q10).
- Der Hash ist aus der AOI zurückrechenbar und bleibt intern.
- Logs nennen Kennung, Datensatz, Operator und Zahlen, nie `aoi`, `href` oder
  den Hash (projektplan 7 Punkt 6; die Fehlerklassen in `gateway/errors.py`
  wiederholen schon keine URL).
- `recipe.json` enthält die AOI, wie es `aoi.geojson` im Zuschnitt-ZIP heute
  schon tut. Es ist die eigene Datei des Nutzers.

---

## 5. Operator-Registry (Punkt 2)

### 5.1 Form

| | O1 pydantic-Modelle | O2 handgeschriebene JSON Schemas + `jsonschema` | O3 openEO-Prozessdefinitionen (JSON) |
|---|---|---|---|
| K7 strikt | ✓ mit `strict=True`, `extra="forbid"` | ✓ | ✓ |
| K8 Panel aus Schemas | ✓ `model_json_schema()`, Draft 2020-12 [P] | ✓ | ✓ (draft-07 + `subtype`) |
| Validierung = Ausführungstypen | ✓ ein Modell für beides | ✗ zwei Quellen der Wahrheit | ✗ dazu Python-Typen nötig |
| K9 Abhängigkeiten | keine (pydantic ist da) | neu: `jsonschema` 4.26 mit `rpds-py` (Rust) | keine, aber eigener Lader |
| K10 OGC/openEO | ~: OGC 1.0 verlangt eigentlich eine OpenAPI-3.0-Teilmenge (§3.10), openEO draft-07 | ~ | ✓ openEO |

**Empfehlung: O1.**
- Zwei Vorsichtsregeln aus der Messung: `strict=True`, und in
  Parameterschemas kein `pattern`, das Rust-`regex` und ECMA-262
  unterschiedlich lesen (§3.10). Für Ausdrücke prüft der Operator selbst (§5.2).
- `jsonschema` kann als reine Testabhängigkeit prüfen, dass das ausgelieferte
  Schema gültig ist.

### 5.2 Skizze (Vorschlag, nicht gebaut)

```python
# processing/operators/base.py
class Tier(Enum):
    T1 = "T1"   # tiler, per tile
    T2 = "T2"   # worker and local runner, the same core

@dataclass(frozen=True, slots=True)
class Requirement:
    capabilities: frozenset[str]          # fields of catalog.registry.Capabilities, all must be True
    data_classes: frozenset[DataClass]    # empty means any
    licence_tier: LicenseTier             # PROCESSING (B11)

@dataclass(frozen=True, slots=True)
class Operator:
    op: str                               # "band_math"
    op_version: int
    category: str                         # tab in the processing panel
    title: str                            # UI text, English
    description: str
    citation: str | None
    params: type[BaseModel]               # strict, extra="forbid" → JSON Schema
    requires: Requirement
    tiers: frozenset[Tier]
    kind: Literal["pixel", "grid"]        # pixel: per block/tile; grid: own plan (reprojection)
    estimate: Callable[[GridPlan, BaseModel], CostEstimate]
    transform: Callable[[RasterMeta, BaseModel], RasterMeta]
    run: Callable[..., Any]               # core; for "pixel": ImageData -> ImageData

def applicable(operator: Operator, config: DatasetConfig) -> list[str]:
    """Empty means applicable, otherwise the reasons. Called by api, never in the worker core."""
```

- Die Registry ist ein unveränderliches Mapping `op → Operator` in
  `processing`.
- **Band-Math** (M4-09):
  - `kind="pixel"`, `tiers={T1, T2}`.
  - Der Kern ist `ImageData.apply_expression` aus rio-tiler, also dieselbe
    Funktion, die die Kachel heute rechnet (§3.2).
  - Der Ausdruck wird vor der Ausführung geprüft: nur Namen der Eingaben,
    Zahlen, `+ - * /`, Klammern und eine kleine Liste von numexpr-Funktionen.
    Eine Länge bis 256 Zeichen ist ein Vorschlag [A].
- **Reprojektion/Resampling** (M4-10):
  - `kind="grid"`, `tiers={T2}`.
  - Parameter: `crs`, `resolution`, `resampling` (Enum wie openEO
    `resample_spatial`, Vorgabe nicht gesetzt, B10) und `align`.
  - Der Blockplan (Größe 1024 px, `tolerance`, `warp_mem_limit`) steht fest im
    Operator, nicht in den Parametern (§3.4).

### 5.3 Anwendbarkeit

- `processing` prüft nur gegen die übergebene `DatasetConfig`, nie gegen
  `catalog.datasets` (Kettenregel, `adr/0011` §6.2).
  - `api` ruft `applicable` bei der Annahme auf und für das Panel
    (`/processes`, gefiltert je Datensatz).
  - Der Worker-Kern prüft nur noch, dass Operator und `op_version` bekannt und
    die Parameter gültig sind.
  - Eine Rezeptdatei im lokalen Runner kann der Nutzer ohnehin ändern
    (`self_attested`, Q12).
- **Band-Math:** `capabilities.band_math`, alle drei Einträge setzen es
  (`datasets.py` Z. 87, 270, 467).
- **Reprojektion:** Die Registry hat kein passendes Flag (`registry.py`
  Z. 163–169). B10 verlangt, dass jeder Datensatz „jede Fähigkeit ausdrücklich
  freischaltet“. Deshalb (F6):
  1. Neues Flag `reprojection`. Methoden außer `nearest` verlangen zusätzlich
     `interpolation` **(Empfehlung)**. Das ist ein neues Registry-Feld ohne
     Vorgabe; alle drei Einträge setzen es bewusst.
  2. Kein eigenes Flag, nur Lizenzstufe *Processing*. Methoden außer
     `nearest` verlangen `interpolation`.
  3. Alles unter `interpolation`.
- **Lizenz:** Stufe *Processing* (B11). `commercial_use=false` bleibt im
  Gratis-Tier. Das wirkt erst mit Konten (M6) und wird bis dahin nur
  vermerkt.

### 5.4 Skalierung bei Band-Math (F7)

Gemessen (§3.11): Derselbe Sentinel-2-Wert kommt aus dem Zarr-Pfad als
Reflexion (CF-Dekodierung im Reader), aus dem COG-Pfad als Rohwert, solange
`unscale` nicht gesetzt ist. Ein Beispiel mit DN Rot 1200 und NIR 3400 [A]:

- NDVI aus Rohwerten: 0,478.
- NDVI aus Reflexion (×0,0001 − 0,1): 0,846.

**Empfehlung, angenommen (F7): Band-Math rechnet immer auf physikalischen
Werten.**

**Auflage F7:** Skalierung und Offset kommen aus `raster:bands` des Items, nie
aus datensatzspezifischem Code.
- STAC 1.0 mit raster v1: `raster:bands[].scale`/`offset`.
- STAC 1.1 mit raster v2: `bands[].raster:scale`/`raster:offset` (§3.10).
- Für die Umsetzung vorgesehen (M4-09): ein Test mit einem synthetischen Item
  mit Offset und Nodata.

**Befund zur Auflage [M]:**
- Das Item von `sentinel-2-l2a-zarr3` trägt keine Skalierung. Die Assets haben
  nur `nodata` und `data_type`, die `bands` nur Namen und eo-Angaben. Kein
  `raster:scale`/`raster:offset` kommt im Item vor, obwohl es raster v2
  deklariert (§17.10).
- Skalierung und Offset stehen nur im Store, als CF-Attribute, die der Reader
  heute selbst dekodiert (§3.11).

**Entschieden mit F7a (1), Otto 2026-10-02:**
- **Item mit Skalierung:** Die Werte aus `raster:bands` gelten. Der Kern wendet
  sie auf die Rohwerte an; der Reader liest roh.
  - Für Zarr heißt das: öffnen ohne CF-Dekodierung (`mask_and_scale=False`).
    Das ist eine generische Option in `readers`, nicht je Datensatz.
- **Item ohne Skalierung:** Es gilt die generische CF-Dekodierung des Readers
  (xarray-Standard). Das ist kein datensatzspezifischer Code. Heute betrifft
  das `sentinel-2-l2a-zarr3`.
- **Quelle im Rezept:** Das Rezept vermerkt je Eingabe die angewandte
  Skalierung und ihre Quelle, `item` oder `store-cf`.
- **Vergleich:** Tragen Item und Datei bzw. Store beide eine Skalierung, prüft
  der Worker beim Öffnen, dass sie gleich sind. Verglichen werden die
  COG-Tags `scales`/`offsets` bzw. die CF-Attribute. Eine Abweichung lässt den
  Job mit einem benannten Fehler scheitern, statt still zu rechnen (K7).
- **Auslegung [A], Vorschlag, gilt bis Otto widerspricht:** Trägt weder das
  Item noch der Store eine Skalierung, wird nicht skaliert. Trägt dann aber die
  COG-Datei selbst Tags ungleich 1/0, scheitert der Job ebenso. Das betrifft
  heute die eigenen DEM-Items, die kein `raster:bands` tragen
  (`cop_dem_bucket._item`); Q14 braucht dort nur die Reprojektion.
- **T1:** Dieselbe Regel gilt in der Kachel, denn der Kern ist derselbe
  (§6.2). Die Standard-Visualisierung rechnet weiter auf DN; das ist für
  `visual` (uint8) richtig und kein Band-Math.

### 5.5 Kostenmodell und Schätzung (F8)

**`CostEstimate`:**
- Eingabe: Pixel, Bytes, Assets.
- Ausgabe: Pixel und Bytes.
- Dauer in Sekunden.
- Einheiten.

Gerechnet wird vor jedem Lesen, aus AOI, `gsd` und Datentyp. Das ist derselbe
Weg wie `access.download.estimate_output_dims` und `plan_outputs`
(`download.py` Z. 464, 512); `processing` darf `access` importieren.

**Dauer [A] aus [M]:**
- Lokal gemessen 0,034 s je MB roh für Band-Math (§3.5) und 0,041–0,046 s je MB
  für den Zuschnitt (`plans/m3-18-…` §10.3).
- Dazu rund 1 s je Asset für das erste Öffnen über das Netz (`adr/0006` §3.4).
- Die Zahl ist eine Schranke für die Anzeige („etwa“), keine Zusage.

**Einheiten [A]:** Megapixel der Ausgabe × Summe der Operatorfaktoren. Die
Faktoren sind Startwerte, abgeleitet aus lokalen Zeiten je Megapixel Ausgabe,
1 Thread, relativ zu Band-Math (0,146 s/MP, §3.5, Blöcke 1024):

| Operator | gemessen | Faktor |
|---|---|---|
| Band-Math | 9,8 s für 67,1 MP (§3.5) | 1,0 |
| Reprojektion `nearest` | 3,4 s für 64,0 MP, blockweise (§3.4) | 0,4 |
| Reprojektion `bilinear` | 9,0 s für 64,0 MP, blockweise (§3.4) | 1,0 |
| Reprojektion `cubic` | 10,6 s für 64,0 MP, blockweise (§3.4) | 1,1 |
| Export ohne Operator | 15,0 s für 120,6 MP, Zuschnitt mit Maske (`plans/m3-18-…` §10.3) | 0,9 |

Die Messungen lesen lokale Dateien; das Netz fehlt darin. Die Reprojektion las
ein schon gerechnetes Band, Band-Math zwei Bänder mit Schreiben. Die Faktoren
sind deshalb grob. Eine Kalibrierung gegen echte Läufe folgt mit M4-08.

**Wer ablehnt:** Der globale Deckel für gleichzeitige Jobs (Q9) und ein
Pixeldeckel je Job sind Sache von `adr/0013` und M4-08. Die Schätzung liefert
nur die Zahl.

### 5.6 Metadaten-Transformation

- Jeder Operator bildet ein kleines `RasterMeta` auf ein neues ab: CRS,
  Transform, Größe und Bänder mit Name, Datentyp, `nodata`, Einheit und
  Skalierung.
- Daraus entsteht das STAC-Item des Ergebnisses:
  - `proj:code`, `gsd`, `bands` (STAC 1.1).
  - `processing:software` (`earthx`, GDAL, rasterio, numexpr).
  - `processing:expression` mit `format: "rio-calc"` bei Band-Math.
  - `processing:lineage` als kurzer Text je Schritt (der Methodentext in
    voller Länge ist M4-19).
  - Links `derived_from` auf die Quell-Items.
- **Ehrlichkeit (Prinzip 2.9):** Ein Schritt, der resampelt oder reprojiziert,
  setzt ein Feld, das Panel und Download sichtbar machen.

### 5.7 Ausführungsstufen

`tiers` je Operator: Band-Math `{T1, T2}`, Reprojektion `{T2}` (Q6). T2L ist
kein eigener Wert: Der Runner führt denselben T2-Kern aus (7.7, Q12). T0, T3 und
T4 kommen in M4 nicht vor.

---

## 6. Planer T1/T2 und Toleranz (Punkt 3)

### 6.1 Planer

**Regel:** Der längste Anfang der Schrittfolge, in dem jeder Operator `T1` in
`tiers` hat und `kind="pixel"` ist, wird Kachelparameter. Alles danach wird ein
Job.

- Steht ein T2-Schritt vorn (etwa Reprojektion vor Band-Math), gibt es keine
  Vorschau des Ergebnisses, nur die Eingabe.
- Eine Vorschau einer Reprojektion nach EPSG:3035 auf einer
  Web-Mercator-Karte wäre ohnehin wieder reprojiziert [A].

### 6.2 Wie T1 dieselbe Implementierung nutzt

- `api/tiler.py` reicht der Fabrik einen `process_dependency` herein (§3.11).
  Er baut aus `op`, `op_version` und `params` in der Kachel-URL denselben
  Operator-Kern, den der Worker aufruft. `access` importiert nichts aus
  `processing`.
- **Die Kachel-URL trägt die Parameter selbst** (`adr/0001` Z4, `adr/0006`
  §5):
  - keine Rezept-Kennung, denn die bräuchte Zustand im `tiler`;
  - keinen Hash (Q8).
  - Eine Kachel braucht keine AOI, also steht auch keine in der URL.
- **Mehr-Asset-Lücke:** Band-Math über zwei COG-Assets braucht eine
  Pfad-Abhängigkeit, die mehrere `ResolvedAsset` desselben Items öffnet (§3.11).
  - rio-tilers `MultiBaseReader` gibt das `Env` dabei selbst weiter
    (`@inherit_rasterio_env`, §3.6).
  - Gehört in M4-09. Zarr deckt der vorhandene Variablen-Trenner ab.

### 6.3 Toleranzwerte

| Vergleich | Operator | Bedingung | Toleranz | gemessen |
|---|---|---|---|---|
| **T2 ↔ T2L** | alle | gleiches Image (Q12), Blockplan fest in `op_version`, dieselbe CPU-Architektur (CI, x86_64; Auflage F9) | **bitgleich** in allen Pixeln; Metadaten gleich außer `execution`, `runner_version`, `self_attested`, Zeiten | Band-Math: Blöcke 512/1024/2048 und ganz bitgleich; numexpr 1/8 Threads gleich; Warp 1/4 Threads gleich (§3.2, §3.4, §3.5) |
| **T1 ↔ T2** | Band-Math | Kachelraster einer Zoomstufe, die die native Ebene liest; Resampling `nearest`; dieselbe Skalierung (§5.4); dieselbe CPU-Architektur | **bitgleich**, Anteil identischer gültiger Pixel = 1, Maske gleich | z13 und z14: 100 % von je 2,6 Mio. Pixeln (§3.3) |
| T1 ↔ T2 | Band-Math | Übersichtsstufe | kein Vergleich; eine Annäherung, in der Oberfläche als „Preview“ gekennzeichnet (Auflage F9) | z11/z12: 0,004–0,005 % identisch, p99 0,37–0,39 (§3.3) |
| T2 ↔ unabhängige Referenz (ganzes `reproject`) | Reprojektion | gleiche Parameter, anderer Plan | `nearest` ≥ 97 % identisch; `bilinear`/`cubic` auf Höhen: p99 ≤ 0,3 m, max ≤ 1 m; auf NDVI: p99 ≤ 0,01 | DEM: 97,7 %; p99 0,20/0,24 m, max 0,70/0,83 m; NDVI p99 0,0029–0,0083 (§3.4) |

- **Auflage F9:** Bitgleichheit gilt auf der nativen Ebene und auf derselben
  CPU-Architektur. Der Vergleich Cloud gegen Runner läuft deshalb auf
  derselben Architektur (CI, x86_64). Andere Architekturen liegen außerhalb
  dieser Zusage; gemessen ist hier nur x86_64.
- Die erste und die zweite Zeile tragen die M4-Abnahme 1. Die vierte ist eine
  Plausibilitätsprüfung für M4-10. Ihre Grenzen sind aus synthetischen Daten
  abgeleitet [A].
- `bilinear` als T1-Vergleich (p99 0,005–0,018, §3.3) ist eine Alternative in
  F9. Ich empfehle sie nicht: Sie prüft die Resampling-Reihenfolge, nicht den
  Operator.

### 6.4 Der Vergleichstest

- **Er läuft gegen synthetische Fixtures in der CI:** ein kleines COG mit
  `scale`/`offset` und ein Zarr mit CF-Attributen.
- **T1 ↔ T2:**
  - Die Kachel kommt über die echte Route des `tiler` mit dem Operator als
    `process_dependency`.
  - Das T2-Ergebnis wird mit `nearest` auf dasselbe Kachelraster gebracht.
  - Prüfung: `numpy.array_equal` über gültige Pixel und gleiche Masken.
- **T2 ↔ T2L:** Der Kern läuft zweimal, einmal in der Hülle `jobs` und einmal
  im Runner-Einstieg. Verglichen werden die Bytes der Pixel und das
  Metadaten-Item ohne Provenienzfelder. Die CI-Form gehört zu `adr/0016`.

---

## 7. Lesen im Worker (Punkt 4)

### 7.1 Optionen

| | L1 eigene Blockschleife über `readers` | L2 rioxarray + Dask lokal | L3 odc-stac (Dask oder Pool) | L4 Dask mit eigener Hülle um `readers` |
|---|---|---|---|---|
| K2 Kern rein | ✓ | ✓ | ✓ | ✓ |
| K3 jede URL durch `check_url` | ✓ nur `AssetPath`/`ZarrAsset` [P] | ~ nur, wenn vorher geprüft | ~ `patch_url` für COG ✓; Zarr über `fsspec` ✗ [P] | ✓ |
| K3 GDAL-Optionen je Thread | ✓ mit Regel §7.3 | ✗ außerhalb des Hauptthreads verloren [M][P] | ✓ je Aufgabe neu gesetzt [P] | ✓ mit Hülle |
| K4 gleiche Implementierung wie T1 | ✓ dieselben Reader und Kerne | ~ anderer Leseweg | ✗ eigener Leseweg (`rasterio.open` je Chunk) | ✓ |
| K9 neue Abhängigkeiten | keine | dask (+`fsspec`) | dask, pandas, pystac, odc-geo, odc-loader | dask (+`fsspec`) |
| Speicher | O(Block): 110–150 MB gemessen (§3.5) | O(Chunks × Threads) | dito | dito |
| Zarr v3 über `gateway` | ✓ `GatewayStore` | ~ | ✗ nur v2-Spezifikationen erkannt [P] | ✓ |

**Empfehlung: L1 in M4.** Dask (L4) erst, wenn ein einzelner Job einen Worker
sprengt. Das ist die Regel aus 7.3 („verteiltes Dask erst, wenn …“), hier auf
lokales Dask vorgezogen, weil es heute nichts kauft [A].

### 7.2 Wie L1 liest

- **Ausgaberaster und Blöcke:** Das Ausgaberaster ergibt sich aus Eingaben und
  Schritten. Es wird in Blöcken von 1024 px abgearbeitet; das ist die
  Blockgröße der Sentinel-2-COGs (§3.11) und die Größe aus `plans/m3-18-…`
  §10.3.
- **Lesen:**
  - `processing` öffnet jede Eingabe einmal je Job über
    `access.open_asset_ref` (M4-01a) → `CogReader` bzw. `ZarrReader`.
  - Je Block liest es `part()` im Raster der Eingabe, ohne Warp.
  - Ein `grid`-Schritt (Reprojektion) liest mit seinem eigenen Plan.
- **Schreiben:** blockweise in ein gekacheltes GeoTIFF im Arbeitsordner des
  Jobs. Am Ende macht `rio-cogeo` daraus eine COG. Hochladen ist Sache der
  Hülle `jobs` (`adr/0015`).
- **Threads:** ein Lesethread je Job. Parallel arbeiten mehrere Jobs bzw.
  Worker, gesteuert durch `adr/0013`. `GDAL_NUM_THREADS` bleibt ungesetzt.
- **Speicher:** `GDAL_CACHEMAX` wird ausdrücklich gesetzt, Vorschlag 256 MB.
  Der Standard wäre 5 % des RAM.
- **Fortschritt und Abbruch:** ein Rückruf je Block. Die Hülle kann darin
  abbrechen.

### 7.3 Nachweis für B8

1. **Jede URL:**
   - Der Kern öffnet nur über `readers`. Ein `AssetPath` entsteht nur über
     `check_url` (`readers/cog.py`, `asset_path`), ein `ZarrAsset` ebenso.
     Jeder Chunk geht als eigene Anfrage über `gateway` (`GatewayStore.get`)
     [P].
   - Ein AST-Test nach dem Muster von `test_no_outbound_outside_gateway.py`
     verbietet in `processing` Aufrufe von `rasterio.open`,
     `xarray.open_*`, `rioxarray.open_rasterio` und `rio_tiler.io.Reader` mit
     einer Zeichenkette (Vorschlag für M4-07).
2. **GDAL-Optionen in jedem Lesethread:**
   - Der Einstieg des Worker-Prozesses (heute `jobs/main.py`; `jobs` darf
     `processing` importieren) und der Einstieg des Runners rufen beim Start
     im Hauptthread `processing.worker_environment()` auf und halten es offen.
     Das ist ein Kontext um `rasterio.Env(**readers.process_gdal_options())`.
     Es gilt dann prozessweit, auch für spätere Threads (§3.6).
   - Das geht ohne die Adressen eines Jobs: `gateway.gdal.gdal_options` hängt
     nur von den Zeitlimits der `Policy` ab, nicht von der Allowlist
     (`gateway/gdal.py` Z. 31–54) [P]. `readers.process_gdal_options()`
     übergibt dafür die Vorgaben von `Policy` und ergänzt `GDAL_CACHEMAX`.
   - Zusätzlich betritt jede Lesefunktion das `Env` auf ihrem eigenen Thread,
     wie `download.py` es heute tut.
   - Ein Test startet Lesefunktionen aus einem Thread-Pool und prüft die
     Option mit `rasterio._env.get_gdal_config`, wie in §17.8.
3. **Nicht geschlossen:** Weiterleitungen (§3.7). Das gilt für Kachel und
   Zuschnitt heute genauso und endet mit dem Egress-Proxy aus M6.

---

## 8. `Policy` und GDAL-Optionen im Worker (Punkt 5)

**Vorschlag (F11), eine Fabrik in `readers`:**

```python
# readers/access.py — readers may import gateway
def process_gdal_options() -> Mapping[str, str]:
    """gateway.gdal.gdal_options(Policy defaults) + GDAL_CACHEMAX; host-independent."""

@dataclass(frozen=True, slots=True)
class ReadAccess:
    policy: Policy                    # allowlist = hosts of the recipe's assets
    gdal_options: Mapping[str, str]   # the same as process_gdal_options()
    resolve: Resolver                 # one CachingResolver per job

def read_access_for(hrefs: Iterable[str]) -> ReadAccess: ...
```

Zwei Zeitpunkte, eine Quelle der Optionen:
- **Beim Start des Prozesses** setzt `processing.worker_environment()` die
  GDAL-Optionen prozessweit (§7.3 Punkt 2).
- **Je Job** baut `processing.run` mit `read_access_for` die Allowlist und den
  Resolver. Die GDAL-Optionen sind dieselben; jede Lesefunktion betritt sie
  noch einmal auf ihrem Thread.

- **Eingabe sind Adressen, nicht Hosts.** `processing` darf `urllib` nicht
  importieren (Vertrag `http-only-in-gateway`). Den Host zieht `gateway.host_of`.
- **Allowlist = Hosts der `ResolvedAsset` des Rezepts.** So steht es in B9
  wörtlich.
  - In der Cloud stellt `api` bei der Annahme sicher, dass jeder Host in
    `asset_hosts` seines Datensatzes liegt. Ein Rezept, das ein Nutzer mit
    fremden Adressen einreicht, wird dort neu aufgelöst oder abgewiesen, nie
    durchgereicht.
  - Diese Prüfung gehört nach M4-07/M4-08 in die Annahme. `resolve_asset`
    selbst prüft nach M4-01a ausdrücklich nichts: „without fetching or
    checking anything“ (`access/resolve.py` Z. 135–136) [P]. Die Skizze in
    `adr/0011` §6.4 hatte das noch als Kommentar am `href`.
  - Im lokalen Runner gilt, was in der Rezeptdatei steht (umgekehrtes
    Vertrauen, architekturplan 11). Der Runner nennt die Hosts vor dem Start
    (`adr/0016`).
- Die Grenzen der Policy (Zeitlimits, Verbindungen je Host) bleiben die
  Vorgaben aus `gateway.policy` und gelten wie im `tiler`.
- Wer die Fabrik aufruft: `processing.run(recipe, …)` selbst, ganz am Anfang.
  `jobs` und der Runner rufen beim Start `processing.worker_environment()` auf
  und geben je Job nur Rezept, Arbeitsordner und Fortschrittsrückruf herein.
  Damit beantwortet sich die offene Frage aus `adr/0011` §6.5.

---

## 9. Job-Schnittstelle nach außen (Punkt 6)

**Vorschlag (F12):**

| Teil von OGC API Processes 1.0 | in M4 | Begründung |
|---|---|---|
| Landing Page, API-Definition, `/conformance` | ja, unter eigenem Präfix | Core [P]; getrennt von der STAC-Landing-Page |
| `GET /processes`, `GET /processes/{id}` | ja: **ein** Prozess `recipe`; die Operator-Schemas stehen als `$defs` in seiner Eingabe (Discriminated Union über `op`) | das Panel liest genau dieses Schema (K8) |
| `POST /processes/recipe/execution` | nur asynchron (`Prefer: respond-async` → 201 + `Location`; ohne `Prefer` ebenfalls asynchron, `jobControlOptions: ["async-execute", "dismiss"]`) | Jobs dauern Sekunden bis Minuten (§3.5); bietet ein Prozess nur `async-execute`, „SHALL [the server] respond asynchronously“, mit oder ohne `Prefer` (`REQ_process-execute-default-execution-mode`, `…-auto-execution-mode`) [P] |
| `GET /jobs/{jobID}`, `/results` | ja; Ergebnisse als Links mit signierten URLs (`adr/0012` F3, `adr/0015`) | Q9 |
| `DELETE /jobs/{jobID}` (dismiss) | ja, als Abbruch | Abbruch gehört zu 7.5 und `adr/0013` |
| `GET /jobs` (job-list) | **nein** | ohne Konten zeigte sie fremde Jobs (Q9) |
| Callback, HTML | nein | nicht gebraucht |
| Konformität erklärt | `core`, `json`, `dismiss` | `ogc-process-description` nicht, wegen des Widerspruchs OpenAPI 3.0 / 2020-12 (§3.10) |

- **Kennungen (F15):**
  - `jobID` ist `secrets.token_urlsafe(16)`, also 128 Bit Zufall. Er ist nicht
    zu erraten (Q9) und nicht aus dem Rezept abgeleitet (Q8).
  - Das angenommene Rezept bekommt eine eigene `recipe_id` derselben Art. Sie
    bleibt gleich, wenn derselbe Nutzer dasselbe Rezept erneut startet oder ein
    Cache-Treffer antwortet; ein Job ist dagegen ein Lauf.
  - `recipe_id` ist die Rezept-ID aus Q15: Grundlage für Permalink (M4-19) und
    für Bug-Report Stufe 3. Sie läuft mit dem Rezept nach 7 Tagen ab (Q10).
  - Den Hash sieht nach außen niemand; er bleibt der interne Schlüssel.
- **Fortschritt** per SSE ist kein Teil von OGC. Die Form schlägt `adr/0013`
  vor (7.4). `progress` (0–100) steht zusätzlich im Statusdokument.
- **Statuswerte** wie OGC. Version 2 heißt `id` statt `jobID` (§3.10). Das
  Antwortmodell bleibt deshalb dünn, damit der Wechsel eine Zeile ist [A].
- **Alternativen in F12:**
  - zusätzlich jeder Operator als eigener Prozess, für fremde OGC-Clients;
  - eigene Routen ohne OGC-Form.

---

## 10. `recipe.json` und `citation.bib` im Zuschnitt-ZIP (Punkt 7)

### 10.1 `recipe.json`

- **Schema:** dasselbe wie in §4.2. Für den synchronen Zuschnitt gilt
  `steps: []` und `output: {"kind": "crop", "format": "cog",
  "resolution_factor": n, "extent": "bbox(aoi ∩ footprints)", "mask": "file"}`.
  Damit sind die Regeln aus M3-18 §3 und §13 benannt.
- **`version` je Eingabe:**
  - Die Fassung steht drin, wo sie ohne Anfrage vorliegt (`file:checksum`,
    `updated`).
  - Für das DEM bleibt `version` beim Zuschnitt `null`. Ein `HEAD` je Kachel
    für eine Begleitdatei lohnt nicht [A].
  - Q11 betrifft nur den Cache.
- **Provenienz:** Block `provenance` mit `execution: "cloud"`,
  `kind: "sync-download"`, den Versionen aus §4.5 und dem Zeitpunkt.
- **Weggelassen:** kein Hash. Beim synchronen Zuschnitt auch keine
  `recipe_id`: Er wird nicht gespeichert (D3) und braucht deshalb keine. Das
  `recipe.json` eines Jobs trägt dagegen seine `recipe_id` (§9, F15).
- **Wer baut:** `api`, denn dort liegen Items, Fassungen und Registry. Die
  Datei geht als Bytes an `access.download.build_download_zip`, das
  `processing` nicht importieren darf.

### 10.2 `citation.bib`

Je Datensatz ein Eintrag `@misc` aus den Registry-Feldern:

```bibtex
@misc{sentinel-2-c1-l2a,
  title        = {Sentinel-2 L2A},
  doi          = {10.5270/S2_-742ikth},
  url          = {https://doi.org/10.5270/S2_-742ikth},
  note         = {Contains modified Copernicus Sentinel data 2026},
  urldate      = {2026-10-02}
}
```

- `@misc` ist der portable Typ: DataCite schreibt so, und `plain.bst` kennt
  `@dataset` nicht (§3.10).
- Der Schlüssel ist die Datensatz-ID.
- `note` ist der Attributionstext, wie er auch in der Hinweisdatei steht.
- `urldate` ist der Tag des Downloads.
- Gibt es kein `doi`, steht `citation` als `note`. Eine Zitierangabe muss es
  nach Checklistenpunkt 3 ohnehin geben.
- **Lücke:** Autor bzw. Herausgeber und Jahr der Veröffentlichung fehlen,
  weil die Registry sie nicht führt. DataCite liefert sie, ist aber aus der
  Sitzung gesperrt. Ein späteres kuratiertes Feld je Datensatz ist Option 2 in
  F13.
- **Nebenfund, mit F13 zu lösen:** `sci:doi` trägt heute die URL. Vorschlag für
  M4-14:
  - Die Registry behält die URL (sie kommt aus dem `cite-as`-Link der Quelle).
  - `collection.py` schreibt `sci:doi` als DOI-Namen und dazu einen Link
    `rel: cite-as`.
  - `citation.bib` nutzt denselben Namen.

---

## 11. Checkliste Punkt 9, Fassung v2 (Punkt 8)

**Form (F14):**

- **Wo:** ein neues Testmodul neben `tests/catalog/test_onboarding_endtoend.py`,
  parametrisiert über `REGISTRY`. Es nutzt das Gerüst von
  `synthetic_chain.py`: Adapter mit `httpx.MockTransport`, synthetische Stores
  aus `mini_cog`, `mini_dem` und `mini_zarr_composite`.
- **Kette je Eintrag:**
  1. Suche über den eigenen Adapter.
  2. `access.resolve_asset`.
  3. Auftrag und Rezept, validiert und gehashed.
  4. Lauf des Kerns (T2) in `tmp_path`.
  5. Ergebnis-COG lesbar, Metadaten transformiert, `recipe.json` und
     `citation.bib` vorhanden.
  6. Bei Band-Math zusätzlich: Kachel = T2 nach §6.4 (Toleranz 0).
- **Zuordnung nach Q14** als Konstante im Testmodul: Band-Math (NDVI) für die
  zwei Sentinel-2-Einträge, Reprojektion für `cop-dem-glo-30`.
  - Ein Wächtertest fällt, wenn ein Registry-Eintrag keine Zuordnung hat. Das
    ist das Muster der Live-Smoke-Marker in `test_onboarding_checklist.py`.
  - Kein Registry-Feld dafür: Welcher Operator den Punkt belegt, ist eine
    Testentscheidung, keine Eigenschaft des Datensatzes [A].
- **Synthetische Daten:** Die Fixtures tragen `scale`/`offset` bzw.
  CF-Attribute wie die echten Quellen (§3.11). Sonst prüfte der Test die
  Skalierungsregel aus §5.4 nicht.
- **Umstellung:** `CHECKLIST` in `test_onboarding_checklist.py` zeigt für
  Punkt 9 ab dem Merge von M4-15 auf das neue Modul (Q14). Die Kette aus v1
  bleibt als eigener Test bestehen, sie prüft den Zuschnitt.

---

## 12. `decomp.py` (Punkt 9) — nur beschrieben

**Wie ein Quad-Pol-Operator später registriert würde** [A]:

- Kennung `quad_pol_decomposition`, `kind="grid"`, `tiers={T2}`.
  - Der Warp mit `nearest` je Amplituden- und Phasenpaar gehört zur Mathematik
    (Docstring in `decomp.py`).
  - Er ist nicht kachelweise zu rechnen.
- Parameter `method` (`pauli`, `freeman`) und Fenstergröße.
  `requires.capabilities = {"quad_pol"}` (B10, ENTSCHEIDUNGEN §3).
- **Der Code bleibt in `datasets/<id>/`.** `processing` darf `datasets` nicht
  importieren (Vertrag `datasets-isolated`). Registriert wird deshalb durch
  Komposition am Prozess-Einstieg: Ein Modul, das `datasets` importieren darf,
  übergibt den Operator der Registry.
- **Lücke für später:**
  - Der Worker-Prozess startet heute aus `jobs/main.py`, und `jobs` darf
    `datasets` nicht importieren.
  - Das betrifft M4 nicht, weil der Operator ruht.
  - `adr/0013` sollte den Einstieg des Workers trotzdem so legen, dass das
    später ohne Lockerung geht, etwa als Kompositionswurzel in `api` wie
    `api/tiler.py`.
- **Lesen:** `_warp_complex` öffnet heute Zeichenketten mit `rasterio.open`
  (`decomp.py` Z. 76–85). Registriert würde es über `AssetPath` aus `readers`
  lesen. Das ist eine Änderung am Lesen, nicht an der Mathematik, und wäre eine
  eigene Entscheidung („nie generalisieren“ bleibt).

---

## 13. Wo was liegt (Vorschlag)

| Modul | neu | darf weiter importieren |
|---|---|---|
| `processing/recipe.py` | Modelle für Auftrag, Rezept und Provenienz; Kanonisierung; Hash | unverändert (3.1) |
| `processing/operators/` | Registry, `band_math`, `reproject`, `applicable` | `access`, `readers`, `catalog.registry` |
| `processing/plan.py` | T1/T2-Planer, Ausgaberaster, Kostenschätzung | dito |
| `processing/core.py` | `run(recipe, *, workdir, progress) -> RunResult`, eine reine Funktion; `worker_environment()` für den Prozessstart | dito |
| `readers/access.py` | `process_gdal_options()`, `read_access_for(hrefs)` | `gateway` |
| `api` | Annahme (Items, `resolve_asset`, Fassung per `gateway`), Job-Routen, `process_dependency` für den `tiler`, `recipe.json`/`citation.bib` | alle |
| `jobs` | Hülle: Queue, Upload, Fortschritt (`adr/0013`, `adr/0015`) | nur `processing` |

Keine Importregel ändert sich. `.importlinter` bleibt, wie es ist.

---

## 14. Was dieses ADR nicht entscheidet

- Queue, Deckel, SSE und den Ort des Worker-Einstiegs: `adr/0013`.
- Objektspeicher, signierte URLs, Ablauf, und ob ein Ergebnis ohne Fassung für
  den Auftraggeber gespeichert wird: `adr/0015`.
- Aufbau des Runners und die CI-Form des Vergleichs T2 ↔ T2L: `adr/0016`.
- Masking, Normalisierung, Methodentext, Permalinks, „Parameter übernehmen“:
  M4-18 und M4-19.
- Ob die Plattform je eine volle openEO-API anbietet: architekturplan 15.3.

---

## 15. Fragen an Otto — beantwortet am 2026-10-02

Otto hat alle fünfzehn Fragen mit Option 1 beantwortet. Die Fragen stehen mit
ihrem ursprünglichen Wortlaut da. Die Auflagen und die Rückfrage F7a, ebenfalls
mit Option 1 beantwortet, stehen in §15a.

**F1 — Aufbau des Rezepts (§4.1)**
1. Drei Schichten (Auftrag, Rezept, Provenienz), lineare Schrittfolge
   **(Empfehlung)**
2. Ein Dokument mit optionalen Feldern
3. openEO-Prozessgraph als Rezept

**Antwort F1: (1)** drei Schichten, lineare Schrittfolge.

**F2 — Kanonisierung (§4.4)**
1. `json.dumps` mit festen Regeln über das validierte Modell, SHA-256 mit
   Verfahrenskennung; RFC 8785 erst, wenn der Hash Python verlässt
   **(Empfehlung)**
2. RFC 8785 sofort, mit `rfc8785` (Apache-2.0, ohne Abhängigkeiten)
3. RFC 8785 als eigene Implementierung im Repo

**Antwort F2: (1)** `json.dumps` mit festen Regeln, SHA-256 mit Verfahrenskennung; Auflage F2 (§15a).

**F3 — Was in den Cache-Schlüssel geht (§4.5)**
1. Rezept-Kern mit Fassungen und `op_version`, dazu die Versionen von
   `earthx.processing`, GDAL, rasterio, numexpr **(Empfehlung)**
2. Ohne Bibliotheksversionen
3. Die ganze Image-Version

**Antwort F3: (1)**, mit Auflage F3: numpy zusätzlich im Schlüssel (§15a).

**F4 — Fassung je Eingabe, Ergänzung zu Q11 (§4.6)**
1. `file:checksum` vor ETag (`HEAD` über `gateway` bei der Annahme) vor
   `updated`; ohne alles kein Treffer **(Empfehlung)**
2. Nur wie Q11: ETag per `HEAD` oder `updated`
3. Nur `updated`

**Antwort F4: (1)** `file:checksum` vor ETag vor `updated`.

**F5 — Form der Operator-Registry (§5.1)**
1. pydantic-Modelle, strikt, JSON Schema 2020-12, keine neue Abhängigkeit
   **(Empfehlung)**
2. Handgeschriebene JSON Schemas mit `jsonschema`
3. openEO-Prozessdefinitionen

**Antwort F5: (1)** pydantic-Modelle.

**F6 — Anwendbarkeit der Reprojektion (§5.3)**
1. Neues Flag `reprojection` je Datensatz (B10), Methoden außer `nearest`
   brauchen zusätzlich `interpolation` **(Empfehlung)**
2. Kein Flag, nur Lizenzstufe; `interpolation` für Methoden außer `nearest`
3. Alles unter `interpolation`

**Antwort F6: (1)** neues Flag `reprojection`; Methoden außer `nearest` brauchen zusätzlich `interpolation`.

**F7 — Skalierung bei Band-Math (§5.4)**
1. Immer physikalische Werte; Skalierung im Rezept vermerkt, Abweichung von der
   Datei bricht ab **(Empfehlung)**
2. Parameter `unscale` ohne Vorgabe, der Nutzer wählt
3. Rohwerte

**Antwort F7: (1)** physikalische Werte; Auflage F7 und Rückfrage F7a, beantwortet mit (1) (§15a).

**F8 — Kostenschätzung (§5.5)**
1. Aus AOI, `gsd` und Datentyp wie `plan_outputs`, Dauer aus gemessenem
   Durchsatz, Einheiten = Megapixel × Operatorfaktor **(Empfehlung)**
2. Nur Pixel und Bytes, keine Dauer und keine Einheiten bis M6

**Antwort F8: (1)** Schätzung wie `plan_outputs`, Dauer aus Durchsatz, Einheiten aus Operatorfaktoren.

**F9 — Toleranz (§6.3)**
1. T2 = T2L bitgleich; T1 = T2 bitgleich bei nativer Ebene und `nearest`;
   Übersichtsstufen sind Vorschau ohne Vergleich **(Empfehlung)**
2. T1 = T2 statistisch bei `bilinear` (p99 ≤ 0,02) auf jeder Stufe ohne
   Übersicht
3. T2 = T2L mit kleiner Toleranz statt bitgleich

**Antwort F9: (1)**, mit Auflage F9 (§15a).

**F10 — Lesen im Worker (§7)**
1. Eigene Blockschleife über `readers`, 1024 px, ohne Dask, Ausgabe blockweise
   auf lokale Platte **(Empfehlung)**
2. odc-stac mit `patch_url` für COG, eigener Weg für Zarr
3. rioxarray/xarray mit Dask lokal

**Antwort F10: (1)** eigene Blockschleife über `readers`, ohne Dask.

**F11 — `Policy` und GDAL im Worker (§8)**
1. Fabrik `readers.read_access_for(hrefs)`, Allowlist = Hosts des Rezepts;
   `api` stellt bei der Annahme sicher, dass sie in `asset_hosts` liegen;
   GDAL-Optionen prozessweit und je Lesethread **(Empfehlung)**
2. Wie 1, aber die Allowlist kommt im Worker aus einem Registry-Auszug im
   Rezept
3. Der Worker bekommt Policy und GDAL-Optionen fertig aus `api` über die Queue

**Antwort F11: (1)** Fabrik in `readers`, Allowlist aus dem Rezept, Prüfung gegen `asset_hosts` in `api`.

**F12 — Job-Schnittstelle in M4 (§9)**
1. OGC API Processes 1.0 in Form und Vokabular: ein Prozess `recipe`, nur
   asynchron, Status, Ergebnis, Abbruch; keine Job-Liste; erklärt `core`,
   `json`, `dismiss` **(Empfehlung)**
2. Wie 1, zusätzlich jeder Operator als eigener Prozess
3. Eigene Routen ohne OGC-Form

**Antwort F12: (1)** OGC-Form mit einem Prozess `recipe`, nur asynchron, ohne Job-Liste.

**F13 — `recipe.json` und `citation.bib` (§10)**
1. `recipe.json` im Schema aus §4.2 mit `steps: []`, ohne Hash und Kennung;
   `citation.bib` als `@misc` aus den Registry-Feldern; `sci:doi` wird in
   M4-14 zum DOI-Namen mit `cite-as`-Link **(Empfehlung)**
2. Wie 1, aber `citation.bib` aus einem neuen kuratierten Registry-Feld mit
   fertigem BibTeX je Datensatz (Herausgeber, Jahr)
3. Wie 1, `sci:doi` bleibt vorerst URL

**Antwort F13: (1)** `recipe.json` mit `steps: []`, `citation.bib` als `@misc`, `sci:doi` wird in M4-14 zum DOI-Namen mit `cite-as`-Link.

**F14 — Form der Checkliste v2 (§11)**
1. Parametrisierter Test je Registry-Eintrag auf `synthetic_chain.py`,
   Zuordnung Datensatz → Operator im Test mit Wächtertest **(Empfehlung)**
2. Zuordnung als neues Registry-Feld

**Antwort F14: (1)** parametrisierter Test auf `synthetic_chain.py`, Zuordnung im Test mit Wächtertest.

**F15 — Rezept-ID nach Q15 (§9)**
1. Eigene zufällige `recipe_id` je angenommenem Rezept, getrennt von `jobID`;
   Grundlage für Permalink und Bug-Report; Ablauf nach 7 Tagen
   **(Empfehlung)**
2. `jobID` dient zugleich als Rezept-ID

**Antwort F15: (1)** eigene zufällige `recipe_id`, getrennt von `jobID`.

---

## 15a. Auflagen (Otto, 2026-10-02) und Rückfrage F7a

**Auflagen, eingearbeitet:**

- **F2:** Die Kanonisierungsregeln (Schlüsselreihenfolge, Trennzeichen,
  `ensure_ascii`, Fließkommazahlen wie `1` gegen `1.0` und `-0.0`) stehen im
  ADR, in §4.4. Für die Umsetzung ist ein Test mit festen erwarteten
  Hashwerten vorgesehen.
- **F3:** numpy kommt zusätzlich in den Cache-Schlüssel (§4.5).
- **F7:** Skalierung und Offset kommen aus `raster:bands` des Items, nie aus
  datensatzspezifischem Code. Für die Umsetzung ist ein Test mit einem
  synthetischen Item vorgesehen, mit Offset und Nodata (§5.4).
- **F9:** Bitgleichheit gilt auf der nativen Ebene und auf derselben
  CPU-Architektur. Eine Vorschau auf gröberen Zoomstufen ist eine Annäherung
  und wird in der Oberfläche als „Preview“ gekennzeichnet. Für den Vergleich
  Cloud gegen Runner gilt dieselbe Architektur (CI, x86_64) (§6.3).

**Geklärt mit Beleg (Ottos Zusatzfrage):** Der Verlust der GDAL-Optionen
außerhalb des Hauptthreads betrifft den heutigen Kachel- und Download-Pfad im
`tiler` nicht. Belege in §3.6, Messung in §17.11. Kein Befund, nichts
anzuhalten.

**F7a — Skalierung, wenn das Item keine trägt (§5.4), entschieden am 2026-10-02**

Befund [M]:
- `sentinel-2-l2a-zarr3` trägt im Item weder `raster:scale` noch
  `raster:offset`.
- Die Werte stehen nur als CF-Attribute im Store (`scale_factor 0.0001`,
  `add_offset −0.1`), und `readers/zarr_reader.py` dekodiert sie heute
  generisch (xarray-Standard).
- Streng nach Auflage F7 hätte Band-Math für diesen Datensatz keine
  Skalierung. Q14 verlangt aber Band-Math für ihn in der Checkliste v2.
- Auch die eigenen DEM-Items tragen kein `raster:bands`
  (`cop_dem_bucket._item`). Dort braucht Q14 nur die Reprojektion; die ist von
  der Skalierung unabhängig.

1. Trägt das Item `raster:bands` mit Skalierung, gilt sie, und der Reader liest
   roh. Trägt es keine, gilt die generische CF-Dekodierung des Readers. Das ist
   kein datensatzspezifischer Code.
   - Das Rezept vermerkt die Quelle (`item` oder `store-cf`).
   - Haben Item und Store beide eine Skalierung, werden sie verglichen; eine
     Abweichung bricht ab.
   - **(Empfehlung)**
2. Streng nach Auflage: ohne Skalierung im Item kein Band-Math.
   `sentinel-2-l2a-zarr3` fällt für Band-Math aus. Q14 braucht für ihn dann
   einen anderen Operator in der Checkliste v2 (etwa die Reprojektion).
3. Der EOPF-Adapter ergänzt `bands[].raster:scale/offset` beim Normalisieren
   aus den CF-Attributen des Stores. Das ist eine generische Abbildung CF →
   STAC im Adapter. Es kostet je Item einen Abruf der konsolidierten
   Metadaten (gemessen 496 kB) in Suche und Einzelabruf.

**Antwort F7a: (1)** Skalierung aus dem Item, wo vorhanden. Sonst gilt die
generische CF-Dekodierung des Readers, mit Quelle im Rezept und Vergleich, wo
beide vorhanden sind. Umgesetzt in §5.4.

---

## 16. Quellen

**Im Repo [P]**
- `backend/earthx/gateway/`: `checks.py`, `gdal.py`, `policy.py`, `resolver.py`,
  `errors.py`
- `backend/earthx/readers/cog.py`, `backend/earthx/readers/zarr_reader.py`
- `backend/earthx/access/download.py`, `backend/earthx/access/tiles.py`
- `backend/earthx/api/tiler.py`, `backend/earthx/api/dependencies.py`
- `backend/earthx/catalog/registry.py`, `datasets.py`, `collection.py`
- `backend/earthx/adapters/cop_dem_bucket.py`
- `backend/earthx/jobs/main.py`, `backend/earthx/datasets/quad_pol_reference/decomp.py`
- `.importlinter`
- `backend/tests/catalog/test_onboarding_endtoend.py`, `synthetic_chain.py`,
  `test_onboarding_checklist.py`

**Bibliotheken im Projekt-venv [P]**
- `rio_tiler/expression.py` Z. 98–139, `models.py` Z. 689–710,
  `io/rasterio.py` Z. 354–375, `tasks.py` Z. 48–61, `utils.py` Z. 906–935
- `titiler/core/factory.py` Z. 317, 853, 929–930; `titiler/core/algorithm/base.py`
- `rasterio/env.py` Z. 26, 56; `rasterio/_env.pyx` Z. 185–188
  (= `https://raw.githubusercontent.com/rasterio/rasterio/main/rasterio/_env.pyx`)
- `rioxarray/_io.py` (kein `rasterio.Env`; `RASTERIO_LOCK` Z. 44)

**GDAL [P]**, `https://raw.githubusercontent.com/OSGeo/gdal/`
- `master/doc/source/user/configoptions.rst` Z. 60–66
- `v3.12.2/port/cpl_vsil_curl.cpp` Z. 479
- `master/port/cpl_http.cpp` Z. 505–541, 2376, 2386
- `master/gcore/gdalthreadsafedataset.cpp` Z. 534, 748
- `master/alg/gdalwarper.cpp` Z. 1420–1422

**Weitere Bibliotheken [P]**
- odc-stac 0.5.3, odc-loader 0.6.4, odc-geo 0.5.3, pystac 1.15.2: Wheels von
  PyPI. Die Zeilenangaben stehen in §3.8.
- dask 2026.8.0: Wheel; `docs/source/scheduling.rst` Z. 48–60
  (`https://raw.githubusercontent.com/dask/dask/main/docs/source/scheduling.rst`)
- `rfc8785`, `jcs`, `canonicaljson`, `jsonschema`, `pydantic`: PyPI-JSON
  (`https://pypi.org/pypi/<name>/json`)
- pydantic: `docs/concepts/json_schema.md` Z. 5–8 (Repo `pydantic/pydantic`,
  `main`); `pydantic/json_schema.py` Z. 267, 443–445, 1351–1359

**Standards [P]**
- RFC 8785:
  `https://raw.githubusercontent.com/cyberphone/ietf-json-canon/master/index.html`
- OGC API Processes 1.0:
  `https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/7a6bad04eaf6accaebc7c03712547fca28f96d89/core/`
  - `sections/clause_2_conformance.adoc`
  - `sections/clause_7_core.adoc` Z. 59–183, 924–926
  - `openapi/schemas/statusCode.yaml`, `openapi/parameters/jobId.yaml`
  - `requirements/job-list/REQ_op.adoc`,
    `requirements/dismiss/REQ_job-dismiss-op.adoc`
- OGC API Processes v2 (Entwurf), Part 2 und Part 3: derselbe Repo, `master`
  (`core/`, `extensions/deploy_replace_undeploy/`, `extensions/workflows/`).
  Der Stand der Kommentierung ist nur [S].
- openEO:
  - `https://raw.githubusercontent.com/Open-EO/openeo-api/master/openapi.yaml`
    Z. 298–366, 5064–5147
  - `https://raw.githubusercontent.com/Open-EO/openeo-processes/master/`
    `resample_spatial.json`, `normalized_difference.json`,
    `load_collection.json`, `save_result.json`
- STAC-Extensions, je `https://raw.githubusercontent.com/stac-extensions/<name>/main/README.md`
  für `processing`, `file`, `scientific`, `version`, `projection`, `raster`
  und `render`
- STAC 1.1:
  `https://raw.githubusercontent.com/radiantearth/stac-spec/v1.1.0/commons/common-metadata.md`
- JSON Schema 2020-12: `https://json-schema.org/draft/2020-12/json-schema-core`

**Zitation [P]**
- `crosscite/content-negotiation`: `config/initializers/mime_types.rb` Z. 19
- `datacite/bolognese`: `lib/bolognese/utils.rb` Z. 482,
  `lib/bolognese/writers/bibtex_writer.rb` Z. 12
- biblatex: `doc/latex/biblatex/biblatex.tex` Z. 561, 15225; TeX Live
  `plain.bst` Z. 839

**Datenquellen [M]:** siehe „Methode und Belegstufen“ und §17.1.

---

## 17. Messanhang

Alle Skripte liefen mit `/home/user/earthX/.venv/bin/python` im
Kratzverzeichnis der Sitzung. Synthetische Daten entstanden per Skript, nichts
davon liegt im Repo.

### 17.1 Quellen (§3.1, §3.11)

```bash
# Earth Search: ein Item, grobes Rechteck (keine Nutzer-AOI)
curl -sS -X POST https://earth-search.aws.element84.com/v1/search -H 'Content-Type: application/json' \
  -d '{"collections":["sentinel-2-c1-l2a"],"bbox":[6,46,10,48],"datetime":"2026-09-01T00:00:00Z/2026-09-20T00:00:00Z","limit":1}'
#   properties.updated == created; assets.red["file:checksum"] = "1220ed8d…"; file:size 94363519;
#   raster:bands [{"nodata":0,"data_type":"uint16","scale":0.0001,"offset":-0.1}]
curl -sSI  <B04.tif>                 # ETag "72b6…-12", Last-Modified, Content-Length 94363519
curl -sS -D - -o /dev/null -r 0-15 <B04.tif>   # 206, dieselbe ETag
# GDAL öffnet den Kopf: HEAD + 1 GET; scales (0.0001,), offsets (-0.1,), Blöcke 1024, Übersichten 2–16

# EOPF: ein Item der Collection sentinel-2-l2a-zarr3
curl -sS -X POST https://stac.core.eopf.eodc.eu/search -H 'Content-Type: application/json' \
  -d '{"collections":["sentinel-2-l2a-zarr3"],"limit":1}'
#   updated, published, deprecated:false; keine file:checksum
curl -sSI <store>/zarr.json          # 200, kein ETag, kein Last-Modified
curl -sS -D - -o /dev/null -r 0-15 <store>/zarr.json   # 206, kein ETag
curl -sS <store>/zarr.json           # 496 202 B; b04/b08: uint16, scale_factor 0.0001, add_offset -0.1, _FillValue 0

# DEM
curl -sSI https://copernicus-dem-30m.s3.amazonaws.com/<Kachel>/<Kachel>.tif
#   ETag "0e70…0a7b", Last-Modified Mon, 09 May 2022
```

### 17.2 Synthetische COGs

`make_synth.py <out> <n>`:
- Zwei Bänder `uint16`, EPSG:32632, 10 m, glatte Felder mit Rauschen (σ 60
  bzw. 90 DN).
- Ein Block mit Rot = NIR = 1000 DN, das ergibt Reflexion 0, also `0/0`.
- Ein Nodata-Streifen.
- `scales (0.0001, 0.0001)`, `offsets (-0.1, -0.1)`.
- COG mit Deflate, 512er Blöcke, Übersichten mit `average`.
- Erzeugt mit `n=4096` (`s2like.tif`) und `n=8192` (`big.tif`).

### 17.3 Datentypen (§3.2)

`dtype_check.py`: numpy gegen numexpr auf `uint16`, `nan_to_num`, float32
gegen float64 (4 Mio. Werte), numexpr mit 1 gegen 8 Threads, blockweise gegen
ganz.

### 17.4 T1 gegen T2 (§3.3)

`t1_vs_t2.py s2like.tif`:
- T2 = `Reader.read(expression, unscale=True)` auf dem nativen Raster, dann
  `rasterio.warp.reproject` auf das Raster jeder Kachel mit derselben
  Resampling-Methode.
- T1 = `Reader.tile(x, y, z, expression, unscale=True, resampling_method,
  reproject_method)`.
- Je Zoomstufe höchstens 40 Kacheln innerhalb eines Innenrechtecks
  (6 km Rand).
- Verglichen werden gültige Pixel beider Seiten.

### 17.5 Reprojektion NDVI (§3.4)

- `warp_job.py <ndvi.tif> whole|block <resampling> <threads> EPSG:4326`:
  `reproject` ganz gegen `WarpedVRT` mit 1024er Fenstern.
- `warp_block2.py <ndvi.tif> whole|block bilinear <tolerance> <block>`:
  `reproject` je Ausgabeblock (`rasterio.band` als Quelle) mit `tolerance` 0
  bzw. 0.125.
- `WarpedVRT(…, tolerance=0)` scheitert mit
  `ObjectNullError: Pointer 'hDS' is NULL in 'GDALSetProjection'`.
- Ausgaberaster 6665 × 9604 px.

### 17.6 Reprojektion DEM (§3.4)

`dem_warp.py`:
- 3600² float32, EPSG:4326, 1″, Gelände rund −100 bis 3100 m mit Rauschen σ 2 m.
- Ziel EPSG:32632 mit 30 m, Ausgabe 3721 × 2581 px.
- Ganz gegen 1024er Blöcke; ganz mit `num_threads=4` gegen 1.

### 17.7 Speicher (§3.5)

`mem_job.py big.tif whole|block <out> <block>`:
- Mit `CACHEMAX=64` bzw. ohne.
- RSS als `ru_maxrss`, gemessen vor dem Prüflesen des Ergebnisses.
- Pixel-Hash über das geschriebene float32-Band.

### 17.8 GDAL-Optionen in Threads (§3.6)

- `env_threads.py`: `Env` im Hauptthread, Abfrage aus `ThreadPoolExecutor`,
  `threading.Thread` und rio-tiler `create_tasks(threads=2)`.
- `env_race.py`: zwei Threads mit eigenem `Env` (11 und 22); ein Thread ohne
  `Env`, während ein anderer eines hält.
- `env_main.py`: ein vorher gestarteter Thread gegen ein `Env` im Hauptthread;
  Kinder eines `Env` in einem Nicht-Hauptthread.
- Abfrage jeweils mit `rasterio._env.get_gdal_config("GDAL_HTTP_TIMEOUT")`.

### 17.9 Abrufe von GDAL (§3.7)

- `rangeserver.py synth <port> <log>`: ein Range-fähiger HTTP-Server, der jede
  Anfrage mit Methode, Pfad und `Range` protokolliert. `/redirect/<pfad>`
  antwortet `302` auf `127.0.0.2:<port>`.
- `gdal_urls_sep.py <log> <port> opts|default|redirect`: liest ein
  512²-Fenster mit `earthx.gateway.gdal.gdal_options(Policy(...))` bzw. mit
  GDAL-Standard, **jeder Fall in einem eigenen Prozess**. Ein erster Lauf mit
  allen Fällen in einem Prozess zählte für den Standardfall 10 Anfragen ohne
  die Datei selbst, weil sie aus dem prozessweiten VSI-Cache kam.

### 17.10 CF-Dekodierung im Zarr-Pfad (§3.11) und Bandangaben im EOPF-Item (§5.4)

**Mini-Store:** `zarr_format=3` mit `uint16` und `scale_factor`/`add_offset`/
`_FillValue` als Attribute, geöffnet mit denselben Argumenten wie
`readers/zarr_reader.py` Z. 634. Ergebnis: float64
`[[0.02, 0.24], [nan, 0.0]]`.

**EOPF-Item** aus der Suche in §17.1, rekursiv durchsucht:
- Kein Feld `raster:scale`, `raster:offset`, `scale` oder `offset` im ganzen
  Item, obwohl `stac_extensions` raster v2.0.0 nennt.
- `SR_10m` trägt `nodata: 0`, `data_type: uint16` und
  `raster:spatial_resolution: 10`. Seine `bands` tragen nur Name und eo-Felder.
- Zum Vergleich trägt das Earth-Search-Item an `nir`
  `raster:bands [{"nodata": 0, "data_type": "uint16", "scale": 0.0001, "offset": -0.1}]`.
- Keine zusätzliche Anfrage: Ausgewertet wurde die schon geladene Antwort.

### 17.11 GDAL-Optionen im heutigen `tiler` (§3.6)

`probe/test_tiler_env_probe.py`:
- Die Datei lag für den Lauf kurz unter `backend/tests/catalog/` und wurde
  danach wieder entfernt.
- Sie nutzt die Fixtures `chain` und `client` aus `test_onboarding_endtoend.py`
  und ersetzt `rasterio.io.DatasetReader.read` und `rasterio.vrt.WarpedVRT.read`
  durch eine Sonde.
- Die Sonde hält je Lesezugriff fest: Threadname, Hauptthread ja/nein und
  `get_gdal_config` für `GDAL_DISABLE_READDIR_ON_OPEN`,
  `CPL_VSIL_CURL_ALLOWED_EXTENSIONS`, `GDAL_HTTP_TIMEOUT` und
  `VSI_CACHE_SIZE`.

Ergebnis, 9 von 9 Fällen bestanden. Zweimal gemessen, mit gleichem Ergebnis:
einmal auf dem Stand nach PR #113 und einmal nach dem Merge von M4-01a (#112),
das den Weg von Item und Asset im `tiler` umgebaut hat.

| Datensatz | Kachel | Statistik | Download |
|---|---|---|---|
| `sentinel-2-c1-l2a` | 1 Lesezugriff, Nicht-Hauptthread, Optionen aktiv | 1, dito | 4, dito |
| `sentinel-2-l2a-zarr3` | 0 (Zarr über `GatewayStore`) | 0 | 3 (Prüflesung der COG), dito |
| `cop-dem-glo-30` | 1, dito | 1, dito | 4, dito |
