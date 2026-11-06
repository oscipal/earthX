# ADR 0029 — Leseweg NetCDF/HDF5 für die Meteorologie

- **Status:** **Angenommen** von Otto am 2026-11-06: F1–F7 jeweils Option 1 (Empfehlung), Antworten in §9.
  - F1 schließt die Zustimmung zu `h5py` ein, unter einer Bedingung: Die Lizenzen der mitgelieferten Bibliotheken (HDF5, `libaec`) werden beim Eintrag in die Lock-Datei geprüft und im PR genannt.
  - Vor der Annahme ergänzt nach Ottos Review (§8a).
  - **Offen** bleibt, als Frage an `adr/0025`: ob `jobs` bei `source_changed` selbst einen Harvest-Lauf anstößt (§10 Punkt 5).
- **Datum:** 2026-11-06 (Entwurf, Review und Annahme)
- **Aufgabe:** M5-06 laut `docs/plans/m5/m5-discovery-und-suche.md` §6.1 (Antwort F3 zu `adr/0023`). Die Nummer 0029 ist dort vergeben und war beim Start frei.
- **Autonomiestufe:** C. Kein Produktivcode.
  - Geändert werden nur dieses ADR und eine Zeile im Entscheidungslog.
  - Unverändert bleiben `backend/`, `frontend/`, `scripts/`, Registry, Lock-Dateien, Fixtures, `.importlinter`, Backlog, M5-Plan, `.github/`, `.claude/` und `CLAUDE.md`.
  - Die Messskripte liefen im Kratzverzeichnis der Sitzung und stehen nicht im Repo, weil sie über den Proxy der Sitzung statt über `gateway` abrufen (§Methode).
- **Vorab fest:**
  - Prinzip 1: keine dauerhafte Rohdatenhaltung; Abgeleitetes nur flüchtig mit Ablaufdatum (`projektuebersicht.md` §2).
  - Ausgehende Requests nur über `gateway`; GDAL ist geduldet, wenn die URL vorher `check_url` passiert hat; die Durchsetzung kommt mit der Netzwerk-Policy in M6 (`KLAERUNGEN` B8).
  - Worker-Kern zustandslos, ohne Datenbank, Queue, Objektspeicher oder interne API (`KLAERUNGEN` B9).
  - Lesen im Worker über eine eigene Blockschleife in `readers`, ohne Dask (`adr/0014` F10).
  - Zunächst nur Raster; Meteorologie der DACH-Behörden ist ausdrücklich gewollt (M5-Plan §2 Punkt 2, §5 Antwort 2).
  - Lizenz-Einstufung jedes Datensatzes durch Otto.
- **Grundlage:**
  - `adr/0023` §3.1, §4.1, §5.1, §7.1, F3; `adr/0027` §6.5 (ARCO-ERA5 als Vergleichsfall).
  - `adr/0007` (Zarr-Leseweg über `GatewayStore`), `adr/0009` §3.4 (ARCO-ERA5), `adr/0014` F10/F11, `adr/0015` (Objektspeicher).
  - `architekturplan.md` 3.1 (Modulgrenzen), 6.2 (Rang 3 „virtualisiertes Altformat“), 6.3 (Tiler).
- **Betroffen (erst mit einer Entscheidung):** `readers` (neuer Leseweg), `discovery` (Erzeugen der Verweise), Registry (Zeitachse, Verweise), Lock-Datei (`h5py`), M5-11 (erste Meteorologie-Quelle).

---

## Methode und Belegstufen

Belegstufen wie in `adr/0022` und `adr/0023`:

- **M:** in dieser Sitzung gemessen; Verfahren unten.
- **P:** am Primärdokument selbst gelesen (Quelltext, README, Doku-Repository).
- **P\*:** Primärdokument über das Abrufwerkzeug eines Hilfsagenten gelesen, sinngemäß.
- **S:** Suchtreffer oder Zusammenfassung, Wortlaut nicht geprüft.
- **A:** eigene Ableitung.

**Messung vom 06.11.2026 [M].** Die Hosts `data.geo.admin.ch` und `opendata.dwd.de` sind seit M5-01b freigegeben (`adr/0023` F4), `storage.googleapis.com` war erreichbar.

- **Weg:** wie M5-01b (`adr/0023` §9.3) aus der Sitzung über ihren Proxy, nicht über `gateway`. `gateway` verbindet die geprüfte Adresse ohne den Proxy und meldet in der Sitzung `AddressRejected` (`adr/0023` §9.2).
- **Werkzeuge:**
  - `curl` für Kopfzeilen, Range, bedingte Anfragen;
  - GDAL 3.12.2 aus dem Rasterio-Wheel der Lock-Datei (`rasterio` 1.5.2) über `/vsicurl/`, mit `CPL_VSIL_SHOW_NETWORK_STATS`, je Fall ein frischer Prozess (kalter Cache);
  - `h5py` 3.16 (HDF5 2.0) und `kerchunk` 0.2.10 auf einem eigenen Dateiobjekt, das jeden `read` als Range-GET ausführt und mitzählt; mit Seiten zu 64 KiB, wie sie ein Leser über `gateway` puffern würde.
  - Diese Pakete standen nur im Kratzverzeichnis, nicht im venv des Repos.
- **Gelesen:** Collection, Items und Kopfzeilen; Kopf und Chunk-Index der Dateien; einzelne Chunks zur Gegenprobe; je Fall die Zeitreihe an einem Punkt über ein Jahr (liest eine ganze MeteoSchweiz-Jahresdatei, rund 130 MB).
- **Lesefälle** (Raster 1 km, Mitte des Gitters):
  - **Kachel:** ein Zeitschritt, 80 × 80 Pixel (eine Web-Kachel bei Zoom 9);
  - **Land:** ein Zeitschritt, ganzes Gitter (Übersicht Schweiz bzw. Deutschland);
  - **Punkt:** Zeitreihe eines Pixels über alle Zeitschritte der Datei;
  - **AOI-Jahr:** 50 × 50 km über alle Zeitschritte (z. B. Jahresmittel als Processing).
- Adressen, Item-IDs und Prüfsummen stehen nicht in diesem Dokument. Dateinamen nur als Muster.

---

## 0. Kurzfassung

1. **Beide NetCDF-Messfälle sind NetCDF-4, also HDF5** [M]. MeteoSchweiz unkomprimiert, ein Chunk je Tag über das ganze Gitter; DWD HYRAS mit zlib Stufe 9 und Chunks über 40 Tage × 178 × 133 Pixel. Beide erlauben Range (`206`), tragen ETag und beachten `If-None-Match` (`304`) und `If-Match` (`412`).
2. **Byte-Ranges reichen; ein Kopieren der Dateien ist für keinen Lesefall nötig** [M]. Ein Zeitschritt kostet bei virtuellen Verweisen genau die Chunks, die er berührt: MeteoSchweiz 1 Abruf mit 355 KB, DWD für ganz Deutschland 25 Abrufe mit 7,5 MB, für eine Kachel 1 Abruf mit 0,5 MB (§4).
3. **GDAL über `/vsicurl/` liest dieselben Dateien ohne neue Abhängigkeit** [M]: Der netCDF-Treiber im Wheel erkennt EPSG:2056 und EPSG:3035 und liefert dieselben Werte wie der Weg über die Verweise (bitgleich). Er braucht etwas mehr Abrufe und Bytes je Zeitschritt (§4), liest über `userfaultfd` unter einem globalen Mutex und prüft keine ETags (§7).
4. **Die Verweise entstehen mit `h5py` allein** [M], gleich denen von `kerchunk`, in 5–8 Abrufen zu 64 KiB je Datei. VirtualiZarr lädt beim Import `obstore` [M], einen HTTP-Client, den die Importregeln außerhalb von `gateway` verbieten.
5. **Die Zeitachse kommt nicht aus dem STAC der Quelle** [M]. MeteoSchweiz setzt `datetime` der Items auf die letzte Aktualisierung; die Zeit steht nur im Dateinamen und in der Datei. Das Archiv ist ein einziges Item mit 3257 Assets.
6. **Empfehlung (F1):** virtuelle Verweise, erzeugt und gelesen mit eigenem Code über `gateway` (Option A2, §6); je Zeitschritt ein Item, das die Verweise auf seine Chunks selbst trägt (F2, F3). Kein flüchtiger COG-Cache in M5 (F1, Option C nur als spätere Ergänzung).
7. **ARCO-ERA5** taugt als Vergleich, nicht als Quelle für M5: ein Chunk ist eine Stunde × ganze Erde (2,3 MB), eine Zeitreihe an einem Punkt über ein Jahr hieße rund 20 GB (F4).
8. **Nach Ottos Review (§8a):** Der bestehende Lesepfad `xarray` → rio-tiler liest die Verweise über einen zweiten Store neben `GatewayStore`, bitgleich zu GDAL [M]. Je Datensatz entstehen 20 000 bis 35 000 Items (F6). Eine geänderte Quelle wird zur eigenen Fehlerart `source_changed` statt `source_4xx` (F7). `h5py` kostet 18 MB im gemeinsamen Image und im Runner-Image. Der Runner liest dieselben Verweise und ist bitgleich oder scheitert ausdrücklich.

---

## 1. Kontext und Frage

Die Meteorologie der DACH-Behörden liegt vollständig in Formatgruppe D: NetCDF, HDF5, GRIB2 oder hinter einer Abfrage-API (`adr/0023` §7.1). Die Plattform liest heute COG (`readers/cog.py`, GDAL über `/vsicurl/`) und Zarr v3 (`readers/zarr_reader.py`, ein eigener `GatewayStore`, in dem jeder Schlüssel genau ein `gateway`-Abruf ist; `adr/0007`).

Frage: Wie liest die Plattform NetCDF/HDF5 für Anzeige (`tiler`) und Processing (Worker), ohne Rohdaten zu halten und ohne `gateway` zu umgehen? Zur Wahl stehen laut `adr/0023` §7.1:

- **(a)** virtueller Zarr-Speicher (Kerchunk/VirtualiZarr, `architekturplan.md` 6.2 Rang 3);
- **(b)** GDAL-Treiber über `/vsicurl/`;
- **(c)** flüchtiger COG-Cache mit Ablaufdatum.

Nicht Teil dieser Frage: GRIB2 auf dem Ikosaedergitter (ICON) und Abfrage-APIs wie die Dataset API von GeoSphere (`adr/0023` §4.1, §7.1 Punkt 3).

---

## 2. Kriterien

| | Kriterium | Woher |
|---|---|---|
| K1 | Keine dauerhaften Rohdaten | Prinzip 1 |
| K2 | Jeder Abruf über `gateway` bzw. mit vorher geprüfter URL | B8, CLAUDE.md |
| K3 | Worker ohne Plattformdienste | B9 |
| K4 | Zahl und Größe der Abrufe je Kachel und je AOI | M5-Plan §6.1 |
| K5 | Reprojektion aus LV95, EPSG:3034 und EPSG:3035 | M5-Plan §6.1 |
| K6 | Zeitachse in Registry und Ansicht | M5-Plan §6.1 |
| K7 | Erkennen von Änderungen an der Quelle | Prinzip 1, Abnahme M5 (bedingte Requests) |
| K8 | Neue Abhängigkeiten und Aufwand | `adr/0014` K9 |

---

## 3. Messfälle [M]

### 3.1 MeteoSchweiz, räumliche Klimaanalysen (`ch.meteoschweiz.ogd-surface-derived-grid`)

**Collection und Items:**

- `license: CC-BY` an der Collection, ohne Versionsnummer; `adr/0023` §3.1 belegt CC BY 4.0 am Primärtext [P].
- ETag an der Collection, `Cache-Control: max-age=600`.
- 78 Items. Je Tag der letzten rund zwei Monate ein Item mit 5 Assets (vorläufige Tageswerte), je Monat eines mit 16–25 Assets, dazu ein Item `archive-ch` mit **3257 Assets** (Jahresdateien ab 1961 bzw. Rekonstruktionen ab 1864).
- **`datetime` ist bei allen Items der Zeitpunkt der letzten Aktualisierung**, nicht der Zeitraum der Daten (alle Items tragen Zeiten vom 31.10. bis 06.11.2026). Der Zeitraum steht nur im Assetnamen (`…tabsd_ch01r.swiss.lv95_<start>_<ende>.nc`) und in der Datei. Die Tages-Items tragen `expires`.
- `file:size` fehlt an den Assets; `file:checksum` ist gesetzt.

**Dateien** (Jahresdatei Tagesmittel Temperatur 2024, Jahresdatei Niederschlag 2024, Jahresdatei Monatsmittel 2024, eine Tagesdatei vom Oktober 2026):

| Datei | Größe | Aufbau |
|---|---|---|
| Tagesmittel 2024 | 130,8 MB | 366 × 240 × 370, Float32, **unkomprimiert**, Chunk 1 × 240 × 370 (355 KB) |
| Niederschlag 2024 | 144,4 MB | 366 × 265 × 370 (anderes Gitter `ch01h`), sonst gleich |
| Monatsmittel 2024 | 5,0 MB | 12 × 240 × 370, gleich |
| eine Tagesdatei | 1,1 MB | 1 × 240 × 370; dazu je ein 2-D-Feld `lat` und `lon` |

- Format: NetCDF-4 (HDF5-Signatur), geschrieben mit netCDF 4.4.1.1 und HDF5 1.14.4, CF-1.8.
- Lage: `grid_mapping` `oblique_mercator` mit den Parametern von LV95 und ein `esri_pe_string`; die Zeilen liegen von Süd nach Nord.
- Zeit: Achse `time`, `days since <Jahresanfang>` bzw. `months since …`.
- `_FillValue` −999,99; Attribut `least_significant_digit` 7.
- Abruf: über den Host der API aus S3 hinter CloudFront; `Accept-Ranges: bytes`, ETag (Multipart-Form `"…-1"`), Last-Modified, `Cache-Control: max-age=7200`, `Access-Control-Allow-Origin: *`.

### 3.2 DWD HYRAS-DE (`grids_germany/daily/hyras_de`)

- Verzeichnis je Größe (Niederschlag, Mittel-, Minimum-, Maximumtemperatur, Feuchte, Globalstrahlung), je Jahr eine Datei, Fassungen `v6-0` und `v6-1` nebeneinander. Niederschlag ab 1931.
- **Die Datei des laufenden Jahres wird täglich ersetzt:** Die Fassung `v6-1` für 2026 trug am Messtag Last-Modified vom selben Morgen und ein neues ETag.

| Datei | Größe | Aufbau |
|---|---|---|
| Niederschlag 2024 (`v6-1`) | 59,1 MB | 366 × 890 × 665, Float32, **zlib Stufe 9**, Chunk 40 × 178 × 133 (250 Chunks, im Mittel 236 KB komprimiert, 3,8 MB entpackt) |
| Mitteltemperatur 2025 (`v6-1`) | 68,8 MB | 365 × 890 × 665, gleich |

- Format: NetCDF-4, CF-1.11; `crs` als `lambert_azimuthal_equal_area` mit den Parametern von EPSG:3035 (dazu `proj4` mit `+towgs84=0` bzw. `crs_wkt`); Zeilen von Süd nach Nord.
- Zeit: `hours since 1931-01-01` bzw. `1881-01-01`, mit `time_bnds`.
- Lizenz im globalen Attribut `license`: CC BY 4.0 [M].
- `_FillValue` −999 als CF-Attribut; der HDF5-Füllwert des Datensatzes ist dagegen 0. Ein Leser muss das CF-Attribut nehmen.
- Abruf: nginx; `Accept-Ranges: bytes`, ETag, Last-Modified; **kein** CORS.

### 3.3 Vergleichsfall ARCO-ERA5 (`gcp-public-data-arco-era5`, Store `ar/full_37-1h-0p25deg-chunk-1.zarr-v3`)

Gemessen und gelesen am 06.11.2026; ergänzt `adr/0009` §3.4 und klärt zwei offene Punkte aus `adr/0027` §6.5.

- Zarr **v2** mit konsolidierten Metadaten (133 KB), 277 Variablen [M].
- `2m_temperature`: 1 323 648 × 721 × 1440, Chunk **1 Stunde × ganze Erde**, Blosc/LZ4, ein Chunk 2,3 MB [M].
- Keine CRS-Angabe, Längen 0 bis 359,75 [M] (wie `adr/0009`).
- Beschrieben: ERA5 bis 30.06.2026, ERA5T bis 30.10.2026, `last_updated` am Vortag [M]. README: stabile Fassung monatlich mit drei Monaten Verzug, ERA5T rund eine Woche [P].
- Ort `us-central1` laut README [P].
- **Requester Pays: nein.** Ein anonymer `GET` ohne Abrechnungsprojekt liefert `200`, Range `206` [M].
- **Lizenz:** Das README verweist auf die „Copernicus license“ und nennt den Pflichthinweis „Contains modified Copernicus Climate Change Service information“ [P]. Ob die CC BY 4.0 des Climate Data Store seit Juli 2025 auch für diese Kopie gilt, sagt das README nicht. Die Einstufung gibt Otto.

---

## 4. Was ein Lesefall kostet [M]

Je Zeile ein frischer Prozess. „Verweise“ heißt: Abrufe genau der Chunks, die der Fall berührt, mit Größe aus den Verweisen (Gegenprobe an einzelnen Chunks). GDAL: Zählung von GDAL selbst, einschließlich Öffnen.

**MeteoSchweiz, Tagesmittel 2024 (130,8 MB, 366 Chunks zu 355 KB, unkomprimiert):**

| Fall | GDAL `/vsicurl/` | Verweise |
|---|---|---|
| Öffnen | 1 HEAD, 2 GET, 64 KB, 1,2 s | Verweise erzeugen: 8 GET, 512 KB, 0,4 s; mit `h5py` allein 7 GET, 448 KB |
| Kachel | 8 GET, 608 KB, 2,9 s | 1 GET, 355 KB |
| Land | 8 GET, 608 KB, 4,0 s | 1 GET, 355 KB |
| Punkt (366 Tage) | 133 GET, 130,7 MB, 56 s | 366 GET, 130,0 MB |
| AOI-Jahr | 133 GET, 130,7 MB, 58 s | 366 GET, 130,0 MB |

**DWD, Niederschlag 2024 (59,1 MB, 250 Chunks, zlib 9):**

| Fall | GDAL `/vsicurl/` | Verweise |
|---|---|---|
| Öffnen | 1 HEAD, 3 GET, 96 KB, 3,6 s | Verweise erzeugen: 7 GET, 418 KB, 1,6 s; mit `h5py` allein 5 GET, 320 KB |
| Kachel | 9 GET, 1,1 MB, 3,3 s | 1 GET, 477 KB |
| Land | 43 GET, 7,8 MB, 9,2 s | 25 GET, 7,5 MB |
| Punkt (366 Tage) | 46 GET, 5,7 MB, 9,0 s | 10 GET, 3,7 MB |
| AOI-Jahr | 46 GET, 5,7 MB, 8,7 s | 10 GET, 3,7 MB |

**Weitere Dateien (nur Verweise):**

- DWD Mitteltemperatur 2025: erzeugen 7 GET, 444 KB; Kachel 1 GET, 502 KB; Land 25 GET, 6,1 MB; Punkt 10 GET, 5,1 MB.
- MeteoSchweiz Niederschlag 2024: erzeugen 8 GET, 512 KB; Kachel und Land je 1 GET, 392 KB.
- MeteoSchweiz Tagesdatei: erzeugen 2 GET, 128 KB; jeder Fall 1 GET, 355 KB.

**Ohne Seitenpuffer** liest `h5py` beim Öffnen und Durchgehen der Metadaten in vielen kleinen Stücken: 42–93 Abrufe mit zusammen 23–68 KB je Datei. Mit Seiten zu 64 KiB sind es 5–8. Das ist der Befund „viele kleine Lesezugriffe“ aus `adr/0023` §7.1; er betrifft das Öffnen, nicht das Lesen der Daten.

**Gegenproben:**

- Ein Zeitschritt, über die Verweise gelesen und entpackt, ist **bitgleich** zu dem, was GDAL liefert, nach Umkehren der Zeilen (beide Quellen speichern von Süd nach Nord) [M].
- Ein DWD-Chunk entpackt in 14 ms (3,8 MB); das Rechnen fällt neben dem Abruf nicht ins Gewicht.
- Zeiten sind Messungen über den Proxy der Sitzung und nur als Größenordnung brauchbar. Die Zahl der Abrufe und die Bytes hängen nicht vom Netz ab.

**Ein Tag als COG** (für Option C): MeteoSchweiz 195 KB, DWD-Niederschlag 973 KB, Deflate mit Prädiktor 3, Schreiben unter 0,1 s.

**Folgerungen [A]:**

1. Für Anzeige und Processing eines Zeitschritts sind die Dateien gut lesbar: Bei MeteoSchweiz ist ein Zeitschritt genau ein Abruf. Bei DWD berührt ein Tag die Chunks von 40 Tagen: Ganz Deutschland kostet 7,5 MB Abruf für einen Tag, der entpackt 2,4 MB und als COG 973 KB groß ist.
2. Ein Kachel-Cache im `tiler` (`TILER_CURL_CACHE_BYTES`, 256 MiB) bzw. ein Chunk-Cache hält alle Chunks eines Zeitschritts; die Kacheln einer Ansicht holen sie nur einmal.
3. Zeitreihen an einem Punkt sind bei MeteoSchweiz teuer (eine ganze Jahresdatei je Jahr), bei DWD billig (10 Abrufe je Jahr). Das liegt am Chunking der Quelle und an keinem Leseweg.
4. Overviews gibt es in keiner Datei. Bei 1 km und Gittern bis 890 × 665 Pixel ist das kein Problem: Ein Zeitschritt des ganzen Landes ist höchstens ein paar MB.

---

## 5. Querschnitt [M]

### 5.1 `gateway`

- **Verweise:** Jeder Abruf eines Chunks ist ein Range-GET auf eine bekannte Datei mit bekanntem Offset und bekannter Länge. Das ist das Muster von `GatewayStore` (`adr/0007` §6 Punkt 2): ein Schlüssel, ein `gateway`-Abruf. Für das Erzeugen reicht ein Dateiobjekt, dessen `read` über `gateway` geht; `h5py` liest daraus.
- **GDAL:** wie bei COG heute. Die URL passiert `check_url`, GDAL ruft selbst ab; durchgesetzt wird erst mit der Netzwerk-Policy in M6 (B8).
- **Bibliotheken:**
  - `virtualizarr` 2.8.0 lädt beim Import `obstore` und `obspec_utils`; seine Parser verlangen eine `ObjectStoreRegistry` [M]. Die Registry nimmt jedes Objekt mit der obspec-Methode `get` an [P\*, §7]; ein Store über `gateway` wäre also möglich, ist aber nicht erprobt.
  - `obstore` steht in der Verbotsliste des Vertrags `http-only-in-gateway`. Ob `lint-imports` den Umweg über ein fremdes Paket sieht, ist fraglich, denn import-linter schaut nicht in fremde Pakete hinein [A]. Geladen wäre der Client im Prozess trotzdem, gegen den Sinn von B8. Das entscheidet Otto (Lockerung von Importgrenzen).
  - `kerchunk.hdf` importiert `fsspec`, `h5py`, `numcodecs` und `ujson`, aber keinen HTTP-Client [M]. Mit einem eigenen Dateiobjekt liest es über `gateway`.
  - `h5py` allein liefert dieselben Verweise wie `kerchunk` (Offset und Länge aller 616 geprüften Chunks gleich) über `get_chunk_info` [M]. Damit ist `kerchunk` für das Erzeugen nicht nötig.
- **Bedingte Abrufe:** Beide Quellen und GCS antworten auf `If-Match` mit falschem ETag mit `412` [M]. Ein Range-GET mit dem ETag aus der Zeit der Verweise liest also nie Bytes aus einer geänderten Datei. **Vorsicht:** `If-Range` mit falschem ETag liefert die **ganze** Datei mit `200` [M]; der Leser darf `If-Range` nicht verwenden.

### 5.2 Worker (B9)

- Der Worker darf Verweise weder aus der Datenbank noch aus dem Objektspeicher holen.
- **Verweise im Item** (F3, Option 1): Das Rezept trägt die Items, die Items tragen die Verweise auf ihre Chunks. Der Worker braucht nichts weiter.
- Andernfalls muss der Worker die Verweise selbst erzeugen (5–8 Abrufe je Datei über `gateway`).
- GDAL braucht im Worker nichts weiter als heute bei COG.

### 5.3 Reprojektion (K5)

- GDAL erkennt aus den CF-Angaben **EPSG:2056** (MeteoSchweiz) und **EPSG:3035** (DWD) und liefert die Geotransformation (Ursprung, 1000 m) [M].
- `pyproj.CRS.from_cf` auf die `grid_mapping`-Attribute aus den Verweisen liefert ebenfalls 2056 bzw. 3035 [M].
- Die Zeilen liegen von Süd nach Nord. GDAL dreht sie um; ein Leser über Verweise muss die Achse aus den Koordinaten `N` bzw. `y` ablesen und umdrehen (§4, Gegenprobe) [M].
- EPSG:3034 (DWD HOSTRADA) ist nicht gemessen. Dieselben Wege sollten gelten, wenn das `grid_mapping` vollständig ist [A].
- Danach geht die Reprojektion wie bei swissALTI3D und BEV (LV95, EPSG:3035) über die bestehenden Wege [A].

### 5.4 Zeitachse (K6)

- **Quelle:** Weder die Items von MeteoSchweiz noch das Verzeichnis des DWD sagen über `datetime` etwas über den Zeitraum der Daten (§3.1). Die Zeit steht verlässlich nur in der Achse `time` der Datei, zusätzlich im Dateinamen.
- **Plattform heute:** Die Zeitachse der Ansicht und der Suche sind Items mit `datetime`, gruppiert nach `results_group_by`; die Registry kennt `time_range` und `temporal_extent` [P].
- **Folge [A]:** Ein Zeitschritt muss ein Item werden (F2, Option 1), mit Asset auf die Datei, Index in der Zeitachse und den Verweisen auf seine Chunks. Die Items entstehen materialisiert in `discovery` wie beim DEM (Coverage `LOCAL_SQL`, `adr/0009`).
  - Menge: MeteoSchweiz Tageswerte ab 1961 rund 23 000 Items je Größe, DWD Niederschlag ab 1931 rund 35 000.
  - Ein Item trägt bei MeteoSchweiz einen Verweis, bei DWD 25, dazu einmal je Datei Typ, Chunkform, Filter, Füllwert, CRS und Geotransformation.
- **Änderungen (K7):** Das ETag gehört zu den Verweisen. Ein Lauf ohne Änderung kostet je Datei einen bedingten Abruf (`304`); bei `200` werden die Verweise der Datei neu erzeugt. Beim Lesen sichert `If-Match` (§5.1).
- **Laufendes Jahr:** Die DWD-Datei des laufenden Jahres und die vorläufigen Tagesdateien von MeteoSchweiz (mit `expires`) ändern sich täglich. Sie verlangen einen täglichen Lauf (F5).

---

## 6. Optionen

### Option A — virtueller Zarr-Speicher

Verweise (Datei, Offset, Länge je Chunk) statt Kopie; gelesen über einen Zarr-Store.

- **A1 — mit VirtualiZarr/Kerchunk und deren Laufzeit** (`fsspec` bzw. `obstore`, optional Icechunk):
  - Standardwerkzeug, Manifest als Kerchunk-JSON/Parquet oder Icechunk.
  - K2: `obstore` wird mitgeladen (§5.1); `fsspec` ruft über `aiohttp` ab. Ein eigener obspec-Store über `gateway` ginge, der Client läge trotzdem im Prozess. Nur mit Ottos Zustimmung zur Importgrenze.
  - Icechunk kann ETag und Änderungszeit virtueller Chunks prüfen, liest die Chunks aber in seinem Rust-Kern selbst, also an `gateway` vorbei, und braucht einen eigenen Speicher für das Repository [P\*, §7].
- **A2 — eigener Code über `gateway` (empfohlen):**
  - Erzeugen in `discovery`: `h5py` auf einem Dateiobjekt über `gateway`, Seiten zu 64 KiB; je Datei 5–8 Abrufe [M].
  - Ablegen: die Verweise je Zeitschritt im Item (F3).
  - Lesen in `readers`: ein Store nach dem Muster von `GatewayStore`, dessen `get` ein Range-GET mit `If-Match` ist; Entpacken mit `numcodecs` (zlib; schon in der Lock-Datei); Achsenrichtung und CRS aus den Verweisen.
  - Neue Abhängigkeit: `h5py` (BSD-3-Clause) nur für `discovery`. `kerchunk` und VirtualiZarr bleiben draußen.
  - Neuer Code: Store, Erzeugen der Verweise, Zeitindex im Leser (heute nur 2-D-Variablen); der Store liefert Zarr-v3-Metadaten aus den Verweisen, der Leser bleibt bei `zarr_format=3` (§8a.1).
- **A3 — GDAL-Zarr-Treiber auf Kerchunk-Verweisen** (seit GDAL 3.11): liest die Verweise über `/vsisubfile/` und `/vsicurl/`, prüft aber weder ETag noch Änderungszeit [P\*]. K2 wie B. In der Bewertung unten wie B mit den Abrufzahlen von A.

### Option B — GDAL-Treiber über `/vsicurl/`

- netCDF-Treiber mit `netCDF:"/vsicurl/…":<variable>`, Band = Zeitschritt.
- Geht heute ohne neue Abhängigkeit und ohne root [M]; CRS und Geotransformation kommen mit [M].
- Kosten etwas höher als A2, aber gleiche Größenordnung (§4); jedes Öffnen liest die Metadaten neu (2–3 Abrufe).
- K2 wie COG: geduldet nach B8, Durchsetzung erst in M6.
- K7: kein Schutz gegen eine Datei, die sich zwischen zwei Abrufen ändert; GDAL kennt kein `If-Match`.
- Die Zeitachse muss die Plattform trotzdem selbst aufbauen (§5.4); GDAL nimmt nur das Lesen ab.
- Der Treiber liest `/vsi*` über `userfaultfd` und hält einen **globalen Mutex** über alle netCDF-Dateien [P\*, §7]. Im `tiler` hieße das: Kacheln aus NetCDF laufen je Prozess nacheinander. Gemessen ohne root und mit `vm.unprivileged_userfaultfd=0` [M]; in Containern mit strengem Seccomp-Profil kann der Systemaufruf gesperrt sein [P\*].

### Option C — flüchtiger COG-Cache mit Ablaufdatum

- Ein Job liest den Zeitschritt (über A oder B), schreibt ihn als COG in den eigenen Objektspeicher (`adr/0015`) und der `tiler` liest von dort.
- Ein Tag als COG ist klein (195 KB bzw. 973 KB) [M].
- Ist kein eigener Leseweg: Das Lesen der Quelle bleibt A oder B. Dazu kommen Job, Ablaufregel, Lizenzfrage der Kopie (Weitergabe) und der Objektspeicher im Lesepfad des `tiler`.
- Lohnt sich erst, wenn eine Quelle je Zeitschritt sehr viel mehr liest als sie zeigt. Bei DWD ist das knapp Faktor 8 (7,5 MB Abruf gegen 973 KB COG für ganz Deutschland); bei MeteoSchweiz gibt es kaum etwas zu gewinnen (355 KB gegen 195 KB).

### Bewertung

| | A1 | A2 | B | C |
|---|---|---|---|---|
| K1 keine Rohdaten | ✓ | ✓ | ✓ | ✓ (flüchtig) |
| K2 `gateway` | ✗ ohne Lockerung | ✓ voll | ~ wie COG | wie A bzw. B |
| K3 Worker | ~ Manifest muss mit | ✓ Verweise im Item | ✓ | ✗ Objektspeicher |
| K4 Abrufe je Kachel/AOI | am wenigsten | am wenigsten | etwas mehr | am wenigsten nach dem Füllen |
| K5 Reprojektion | ✓ | ✓ (`from_cf`) | ✓ (GDAL) | ✓ |
| K6 Zeitachse | eigener Aufbau | eigener Aufbau | eigener Aufbau | eigener Aufbau |
| K7 Änderungen | nur mit Icechunk | ✓ ETag und `If-Match` | ✗ | wie A bzw. B |
| K8 Aufwand | mittel, neue Pakete | mittel, nur `h5py` | gering | hoch |

---

## 7. Stand der Technik

Recherche eines Hilfsagenten am 06.11.2026 (P\* bzw. S). `gdal.org`, `readthedocs.io` und `icechunk.io` waren nicht erreichbar; gelesen wurden deshalb Doku und Quelltext aus den GitHub-Repositories (Stand `main`/`master`, teils neuer als GDAL 3.12.2).

**GDAL netCDF- und HDF5-Treiber auf `/vsi*`:**

- Der netCDF-Treiber legt per `userfaultfd` eine Speicherregion in Dateigröße an, füllt Seitenfehler über `VSIFReadL` und öffnet mit `nc_open_mem` [P\*]. Nur Linux, Kernel ab 4.3, libnetcdf ab 4.5; in Containern kann der Systemaufruf gesperrt sein [P\*].
- Der Code versucht zuerst `UFFD_USER_MODE_ONLY`, das auch ohne Privileg erlaubt ist [P\*; Kernelversion S]. Das erklärt, warum die Messung ohne root ging.
- Abschalten mit `CPL_ENABLE_USERFAULTFD`, begrenzen mit `GDAL_UFFD_LIMIT`; ohne `userfaultfd` scheitert der Treiber an `/vsi`-Pfaden [P\*].
- **Globaler Mutex `hNCMutex`** im netCDF-Treiber, weil die netCDF-Bibliothek nicht threadsicher ist [P\*].
- Der HDF5-Treiber liest über ein eigenes VFD (`vsil`), ohne Seitenpuffer und ohne CF-Georeferenz [P\*]; passt zur Messung (keine Geotransformation).

**GDAL und Kerchunk:** Kerchunk-JSON und -Parquet seit GDAL 3.11; Zarr-v2-Kompressoren u. a. zlib, gzip, blosc, lz4; Verweise als `/vsisubfile/`; **keine Prüfung von ETag oder Änderungszeit** der referenzierten Dateien [P\*]. Ein Icechunk-Treiber ist für GDAL 3.14 dokumentiert, noch nicht veröffentlicht [P\*].

**VirtualiZarr** 2.8.0 (14.10.2026): verlangt zarr ≥ 3.1.6, `obstore` ≥ 0.7.0, `obspec_utils` [P\*]. `HDFParser` mit `reader_factory` seit 2.4.0; die Registry nimmt jeden obspec-Store [P\*]. Ausgabe als Kerchunk (JSON, Parquet) oder Icechunk [P\*].

**Kerchunk** 0.2.10 (30.03.2026, „Alpha“): `SingleHdf5ToZarr` nimmt ein Dateiobjekt; zlib, Blosc, Zstd, Shuffle ja, lz4/szip/lzf nein; kein ETag [P\*]. VirtualiZarr hat einen eigenen HDF5-Parser [P\*].

**Icechunk** 2.3.1 (27.10.2026): virtuelle Chunks mit optionaler Prüfsumme aus ETag bzw. Änderungszeit; geänderte Quellen werden nicht ausgeliefert [P\*]. HTTP-Quellen sind erlaubt; ob die Prüfung dort greift, ist offen. Gelesen wird im Rust-Kern, also an `gateway` vorbei [A].

**TiTiler** (`titiler.xarray` 2.4.0, 21.09.2026): liest über `obstore`, NetCDF über `fsspec` mit `h5netcdf`; Zeitachse über `sel=` [P\*]. Beide Wege umgehen `gateway`; als Bibliothek für den Leseweg scheidet es aus, wie schon `adr/0007` für Zarr festhielt.

**zarr-python 3:** liest ohne Sharding immer ganze Chunks, auch unkomprimierte [P\*]. Bei MeteoSchweiz ist das ohne Belang, weil ein Chunk ein Zeitschritt ist.

**Erfahrungen [S]:** Kerchunk-Verweise verkürzen das Öffnen um Faktor 4 bis 20 gegenüber direktem Lesen über HTTP (NCAR CESM2, NOAA National Water Model); der erste Lauf bleibt teuer. Ein Blockcache passend zum Chunk-Layout bringt beim direkten Lesen viel. Das deckt sich mit §4: ohne Seitenpuffer 42–93 Abrufe beim Öffnen, mit Seiten zu 64 KiB 5–8.

**Quellen selbst [P\*]:**

- MeteoSchweiz: vorläufige Tageswerte 41 Tage, konsolidierte 14 Monate; Veröffentlichung am 10. und 26. des Folgemonats, die Fassung vom 26. **überschreibt** die vom 10.; Endbearbeitung Anfang Februar; Jahresdateien bis rund 200 MB. Dateien werden also an Ort und Stelle ersetzt.
- DWD HYRAS v6-1: Die Datei des laufenden Jahres wird täglich verlängert; am Monatsanfang und zur Monatsmitte wird der Vormonat qualitätsgeprüft neu gerechnet. Abgeschlossene Jahre in v6-1 tragen den Stand vom 12.09.2025; v6-0 wird nicht mehr fortgeschrieben [A aus der Auflistung].

**Folge für die Optionen [A]:** Keine fertige Bibliothek liest virtuelle Verweise über einen eigenen HTTP-Client **und** prüft das ETag. Icechunk prüft, umgeht aber `gateway`; GDAL und Kerchunk prüfen nicht. A2 schließt genau diese Lücke mit wenig eigenem Code. Weil beide Quellen Dateien an Ort und Stelle ersetzen, ist K7 kein Randfall.

---

## 8. Empfehlung

**Option A2: virtuelle Verweise, erzeugt und gelesen mit eigenem Code über `gateway`.**

Begründung:

1. **K2 ohne Abstrich.** Jeder Chunk ist ein `gateway`-Abruf, wie bei Zarr heute. B, der einzige Weg ohne neuen Code, bliebe bis M6 auf die Duldung aus B8 angewiesen; für COG ist das hingenommen, für einen neuen Leseweg muss es nicht sein. Dazu kommt bei B der globale Mutex des netCDF-Treibers im `tiler` (§7).
2. **K4 am günstigsten** und genau vorhersagbar: Die Verweise nennen jeden Abruf mit seiner Größe, bevor er stattfindet. Das passt zum Kostenmodell des Processing.
3. **K7:** ETag zu den Verweisen, `If-Match` beim Lesen. Beide Quellen ersetzen Dateien an Ort und Stelle (§7); ohne diese Prüfung läse ein Leser nach einer Neuberechnung Bytes an falschen Offsets. Ein erneuter Lauf ohne Änderung kostet je Datei einen bedingten Abruf; das ist die Abnahme von M5.
4. **K3:** Die Verweise liegen im Item; Worker und lokaler Runner bekommen sie mit dem Rezept.
5. **Architektur:** Das ist Rang 3 aus `architekturplan.md` 6.2, nur ohne Icechunk und ohne fremde I/O-Schicht.
6. **Aufwand begrenzt:** `h5py` als einzige neue Abhängigkeit, nur in `discovery`; der Lesepfad baut auf `GatewayStore` und `numcodecs` auf.

Nicht empfohlen:

- **A1**, solange VirtualiZarr `obstore` mitlädt; Icechunk liest an `gateway` vorbei. Eine Lockerung der Importgrenze brächte keinen Vorteil, den A2 nicht auch hat.
- **A3**, weil GDAL die Verweise ohne ETag-Prüfung liest.
- **B** als Dauerlösung; als Gegenprobe in Tests ist GDAL nützlich (bitgleich, §4).
- **C** in M5. Wiedervorlage, falls eine Quelle mit großen Chunks über die Zeit (Muster DWD) im Betrieb zu langsame Kacheln liefert.

---

## 8a. Ergänzungen nach Ottos Review (06.11.2026)

### 8a.1 Reader: bestehender Zarr-Leser oder neuer Leser?

**Befund [M]:** Der Lesepfad hinter `ZarrReader` bleibt, nur der Store ist neu. Geprüft mit einem Prototyp im Kratzverzeichnis (nicht im Repo; Abrufe über den Proxy statt über `gateway`):

- Ein schreibgeschützter Store (`zarr.abc.store.Store`, wie `GatewayStore`) liefert:
  - `zarr.json` mit konsolidierten Zarr-**v3**-Metadaten, erzeugt aus den Verweisen: Form, Typ, Chunkform, Codecs `bytes` und `numcodecs.zlib` (in zarr 3.1.6 als `zarr.codecs.Zlib` vorhanden), Füllwert, `dimension_names`;
  - die Achsen `x` und `y` als kleine Felder aus der Geotransformation;
  - je Chunk-Schlüssel einen Range-GET mit `If-Match` auf die Quelldatei.
- Darüber unverändert `xarray.open_zarr(store, consolidated=True, zarr_format=3, decode_coords="all", chunks=None)`, wie in `_open_group`, dann ein Zeitschritt mit `isel(time=…)` und rio-tilers `XarrayReader`.
- **Ergebnis:**
  - Ein Tag ist **bitgleich** zu GDAL, bei MeteoSchweiz und bei DWD.
  - Er kostet genau die Chunks aus §4: MeteoSchweiz 1 Abruf mit 355 KB, DWD ganz Deutschland 25 Abrufe mit 7,5 MB.
  - Eine Kachel über `XarrayReader.tile` holte danach keinen weiteren Chunk.
- **Zwei Stellen fehlten im Prototyp** und gehören in M5-11:
  - Der Füllwert kam nur als `fill_value` des Arrays an. `xarray` hat damit nicht maskiert; die Werte waren erst nach Gleichsetzen der Füllwerte bitgleich. Der Store muss `_FillValue` so liefern, wie `xarray` es für v3 liest.
  - Die Zeilen liegen von Süd nach Nord; der Prototyp drehte sie mit `isel(y=slice(None, None, -1))` um.

**Was neu ist [P, A]:**

| Modul | Änderung | Importregel |
|---|---|---|
| `readers` | `ReferenceStore` neben `GatewayStore` (`get` → `Gateway.get` mit `Range` und `If-Match`, `412` → eigene Fehlerart, §8a.3); `ZarrAsset` bekommt Verweise und Zeitindex statt `store_url`; `ZarrReader` wählt den Store, wählt den Zeitschritt, dreht `y` bei Bedarf; `failures.py` bekommt `source_changed` | `readers` → `gateway` erlaubt; kein neues Paket (`zarr`, `numcodecs`, `xarray` stehen schon in der Lock-Datei) |
| `access` | Auflösung Asset → Leser auch für das neue Format | unverändert |
| `catalog` | Registry: Format (z. B. eigener Wert in `DataFormat` für Rang 3) und Felder für Verweise, Zeitindex, ETag | unverändert |
| `discovery` | Verweise mit `h5py` über ein Dateiobjekt auf `gateway` erzeugen; Items je Zeitschritt materialisieren (Muster `materialize.py`) | `discovery` → `gateway`, `adapters`, `catalog` erlaubt; `h5py` ist kein HTTP-Client. Neuer Vertrag „`h5py` nur in `discovery`“ (§8a.4), eine Verschärfung |
| `adapters` | Liste der Dateien je Quelle (FSDI-STAC aus M5-08, DWD-Verzeichnis) | unverändert |
| `api`, `processing`, `jobs` | Fehlerart `source_changed` in `processing_route._FAILURES`; sonst nichts, weil das Item die Verweise trägt | unverändert |

- Keine Lockerung einer Importregel. `GatewayStore` und echte Zarr-Stores bleiben, wie sie sind.
- **Aufwand [A]:** zwei Pakete in M5-11, je unter etwa 400 Zeilen ohne Tests:
  - (a) `readers`: Store, Zeitindex, Fehlerart, Tests mit synthetischen NetCDF-4-Dateien;
  - (b) `discovery`, `adapters`, Registry: Verweise, Items, erster Datensatz.

### 8a.2 Mengen: Items, Variablen, pgstac, Coverage, Harvest

**Items je Datensatz** bei einem Item je Zeitschritt, abgeschlossene Jahre bis 2025 (F5) [M aus den Assetnamen bzw. der Verzeichnisliste]:

| Quelle | Größen | ab | Items (Tage) |
|---|---|---|---|
| MeteoSchweiz, Gitter `ch01r` | `TabsD` | 1961 | 23 741 |
| | `TminD`, `TmaxD`, `SrelD` | 1971 | 20 089 |
| MeteoSchweiz, Gitter `ch01h` | `RhiresD` | 1961 | 23 741 |
| DWD HYRAS-DE | `pr` | 1931 | 34 699 |
| | `tas`, `tasmin`, `tasmax`, `hurs` | 1951 | 27 394 |

Monatswerte sind je Größe 780 bzw. 660 Items.

**Variablen: Assets eines Items oder eigene Items? (F6)**

- **Assets eines Items** (Empfehlung):
  - Ein Datensatz je Quelle, Gitter und Takt, z. B. „MeteoSchweiz täglich, `ch01r`“ mit den Assets `TabsD`, `TminD`, `TmaxD`, `SrelD`.
  - Das ist das Modell der Plattform: Bänder eines Datensatzes sind Assets eines Items, `band_units` je Band, Band-Math über Assets eines Items (etwa `TmaxD − TminD`).
  - Größen ohne Daten an einem Tag (vor 1971) fehlen als Asset.
- **Nicht mischbar** sind Gitter: `RhiresD` liegt auf `ch01h` (265 statt 240 Zeilen, §3.1) und wird ein eigener Datensatz.
- **Eigene Items je Größe** hieße 4–5-mal so viele Items und kein Band-Math zwischen Größen.

**pgstac [A]:**

- Ein Item mit vier bzw. fünf Assets und je Asset den Verweisen der eigenen Chunks: bei MeteoSchweiz ein Paar (Offset, Länge) je Asset, bei DWD 25. Das sind geschätzt 2–3 KB bzw. 4–5 KB JSON je Item.
- Je Datensatz also etwa 50–150 MB JSON vor der Kompression in Postgres. Der DEM hat heute 26 450 Items (`adr/0009` §3.1); die Größenordnung kennt pgstac also schon.
- Laden über `pypgstac` mit `upsert`, wie `materialize.py`; die Suche nach `datetime` bleibt die bestehende.

**Coverage [P]:**

- Der Weg `LOCAL_SQL` für Datensätze mit Zeitachse (Dichte) ist **nicht gebaut**; gebaut ist nur der Flächenweg für Einmal-Produkte (`api/coverage_route.py`, `_area_path`, „the density path that is not built (F4)“).
- Bei einem festen Gitter ist die Dichte überall gleich: jedes Item hat dieselbe Fläche.
- **Vorschlag [A]:** ein einfacher Weg „festes Gitter“ in M5-11: Fläche aus der Ausdehnung der Collection, Zahl der Zeitschritte aus dem Zeitraum, ohne Abfrage je Item. Er gehört zur Checkliste Punkt 2 und ist im Plan von M5-11 zu entscheiden.

**Harvest [M, A]:**

- **Erster Lauf:**
  - MeteoSchweiz rund 300 Jahresdateien, DWD rund 400.
  - Je Datei 5–8 Abrufe zu 64 KiB (§4), zusammen je Quelle rund 2 500 Abrufe und 150 MB.
  - Einmalig, als Befehl in `discovery` wie `materialize`.
- **Folgeläufe:**
  - MeteoSchweiz: ein bedingter Abruf des Archiv-Items (1,5 MB, ETag, `304` gemessen). Jedes Asset trägt `updated` und `file:checksum`; neu verwiesen werden nur geänderte Dateien.
  - DWD: Die Verzeichnisliste trägt **kein** ETag (gemessen: bedingte Anfrage ergibt `200`). Sie zeigt aber Datum und Größe je Datei. Also ganze Liste holen, dann bedingte Abrufe nur für Dateien mit neuem Datum. Das ist der Fall „Liste ohne ETag, Entscheidung über den Inhalt“ aus dem Entwurf von `adr/0025` (PR #300, F7).

### 8a.3 ETag passt nicht mehr

**Heute [P]:**

- `412` kommt aus `gateway` als `UpstreamError` und wird in `readers/failures.py` zu `source_4xx`.
- `source_4xx` ist nicht wiederholbar (`jobs/queue.py`, `RETRYABLE`). Die Oberfläche bietet „Run again“ nicht an (`frontend/src/jobState.ts`, `FAILS_AGAIN`). Der Titel lautet „The source refused a read“ (`api/processing_route.py`).
- Das wäre bei einer neu gerechneten Datei falsch: Die Quelle lehnt nichts ab, nur die Verweise sind veraltet.

**Vorschlag (F7, Option 1):**

- **Fehlerart `source_changed`** in `failures.py`: `UpstreamError` mit Status `412`, sonst nichts.
  - Nicht in `RETRYABLE`: Ein sofortiger zweiter Versuch mit demselben Rezept trüge dieselben Verweise und scheiterte gleich.
  - Nicht in `FAILS_AGAIN`: „Run again“ schickt den Auftrag neu, und `api` holt die Items dabei frisch aus dem Katalog (`processing_route.py`, `fetch_item_or_refuse` bei der Annahme) [P]. Nach dem nächsten Lauf von `discovery` trägt das Item neue Verweise, der zweite Versuch geht.
  - Titel in `_FAILURES`, z. B. „The source has updated this file; it is being catalogued again“, Status `502`.
- **Anzeige im `tiler`:** dieselbe Fehlerart als `502` mit festem Titel; die Ebene zeigt ihren Fehler wie heute. Kein Ausweichen auf alte oder neue Bytes.
- **Neues Harvesten:**
  - Der nächste geplante Lauf findet die Änderung selbst: bedingter Abruf, `200`, Verweise der Datei neu, Items per `upsert`. MeteoSchweiz veröffentlicht am 10. und 26., DWD täglich (§7).
  - Ein Anstoß aus dem Lesepfad ist nicht nötig. Worker und `tiler` schreiben ohnehin in keine Tabelle (B9).
  - Ob `jobs` einen Fund `source_changed` als Hinweis an `discovery` weitergibt, gehört zu den Zuständen in `adr/0025` (Entwurf, PR #300, §5.4 und §6.6) und wird dort entschieden, nicht hier.
- **Kachel-Caches [A]:** Eine Kachel-URL bestimmt das Bild vollständig (`architekturplan.md` 6.3). Ersetzt die Quelle eine Datei, ändert sich das Bild bei gleicher Item-ID. Die URL muss deshalb den Stand des Items tragen, z. B. das ETag der Datei oder `updated`. Das betrifft auch Browser- und CDN-Caches; der Plan von M5-11 legt das Feld fest.
- **Provenienz:** Das ETag gehört in die Provenienz des Ergebnisses. So bleibt nachvollziehbar, welcher Stand der Datei gerechnet wurde.

### 8a.4 `h5py`: Größe, Lizenz, Importregel

- **Größe [M]:**
  - Wheel `h5py` 3.16.0 für `manylinux_2_28_x86_64`: 5,4 MB.
  - Installiert 18 MB: 12 MB Paket und 6,2 MB eigene Bibliotheken (`libhdf5` 2.0.0, `libhdf5_hl`, `libaec`, `libsz`).
  - Zum Vergleich: `rasterio.libs` 67 MB.
  - Ein Wheel für `aarch64` gibt es auch [M]; die Lock-Datei trägt die aarch64-Hashes mit (`adr/0016`).
- **Images [P]:**
  - Es gibt ein Image für `api`, `tiler`, `worker` und `harvester` (`backend/Dockerfile`, Stufe `app`). Das Runner-Image ist `FROM app AS runner`.
  - Mit einer Lock-Datei landet `h5py` also in beiden Images, je +18 MB, auch wo es nie geladen wird.
  - Ein eigenes Image nur für `harvester` spart das, kostet aber eine zweite Lock-Datei bzw. Stufe. Empfehlung: hinnehmen.
- **Zwei HDF5 in einem Prozess [M]:** GDAL bringt im Rasterio-Wheel sein eigenes `libhdf5` 2.2.0 mit, `h5py` sein `libhdf5` 2.0.0. In einem Prozess geladen, lesen beide dieselbe Datei bitgleich. Weil `h5py` nur in `discovery` geladen wird, treffen sie im Betrieb ohnehin nicht zusammen.
- **Lizenz:**
  - `h5py`: BSD-3-Clause [M, Paketmetadaten].
  - Die mitgelieferten Bibliotheken (HDF5 unter der eigenen BSD-artigen HDF5-Lizenz, `libaec` BSD-2-Clause) sind beim Eintrag in die Lock-Datei zu prüfen [S].
- **Importregel:**
  - `h5py` ist kein HTTP-Client und steht nicht auf der Verbotsliste.
  - Ein neuer Vertrag in `.importlinter`, „`h5py` nur in `discovery`“ (Typ `forbidden`, alle anderen Module), hält es aus `readers`, `processing`, `runner` und `api` heraus. Das ist eine Verschärfung, keine Lockerung, und kommt mit M5-11.
- **Zustimmung:** steht ausdrücklich in F1, Option 1.

### 8a.5 Runner und Bitgleichheit (`adr/0014` F9)

- Der Runner führt den Kern `processing` mit `readers` und `gateway` aus (B9; `adr/0016`). Das Rezept trägt die Items und damit die Verweise (F3). Der Runner liest über denselben `ReferenceStore` dieselben Byte-Ranges, nur von der IP des Nutzers. `h5py` braucht er nicht.
- **Bitgleichheit T2 = T2L** (`adr/0014` F9, gleiches Image, gleiche CPU-Architektur):
  - Die Eingabe ist dieselbe Folge von Bytes, gesichert durch `If-Match`.
  - Das Entpacken mit zlib ist deterministisch, danach läuft dieselbe Blockschleife.
  - Gemessen: Verweise aus `h5py` und `kerchunk` gleich [M]; der Weg über die Verweise gleich GDAL [M].
- **Stärker als bei GDAL:** Hat die Quelle die Datei zwischen dem Lauf auf der Plattform und dem im Runner ersetzt, liefert der Runner `source_changed` statt anderer Zahlen. Das Ergebnis ist also bitgleich oder scheitert ausdrücklich, nie still verschieden.
- Mit Option B (GDAL) ginge das nicht: GDAL liest die neue Datei ohne Prüfung.
- **Provenienz:** ETag je Datei im Ergebnis (§8a.3). Der Vergleich in der CI (`adr/0016`) kann es mitprüfen.

---

## 9. Fragen an Otto und Antworten

Otto hat am 06.11.2026 alle sieben Fragen mit Option 1 beantwortet. Die Antwort steht unter der jeweiligen Frage.

**F1 — Leseweg für NetCDF/HDF5?**
1. A2: virtuelle Verweise mit eigenem Code über `gateway`, gelesen über einen zweiten Store im bestehenden Zarr-Lesepfad (§8a.1). **Dazu deine Zustimmung zur neuen Abhängigkeit `h5py` 3.16 (BSD-3-Clause, +18 MB im gemeinsamen Image und im Runner-Image)**, geladen nur in `discovery` und dort durch einen neuen Importvertrag festgehalten (§8a.4) **(Empfehlung)**
2. B: GDAL-netCDF-Treiber über `/vsicurl/`, ohne neue Abhängigkeit, Durchsetzung von `gateway` erst in M6
3. B jetzt für M5-11, A2 danach als eigene Aufgabe
4. A1 mit VirtualiZarr über einen eigenen obspec-Store; `obstore` wird mitgeladen, verlangt deine Zustimmung zur Importgrenze

**Antwort F1 (Otto, 06.11.2026): 1, fest.** Option A2. Zustimmung zu `h5py` unter der Bedingung, dass die Lizenzen der mitgelieferten Bibliotheken (HDF5, `libaec`) beim Eintrag in die Lock-Datei geprüft und im PR genannt werden.

**F2 — Zeitachse?**
1. Ein Item je Zeitschritt, materialisiert in `discovery`, `datetime` aus der Achse `time` der Datei **(Empfehlung)**
2. Ein Item je Datei mit Zeitachse im Item (STAC-Datacube); die Ansicht bekommt einen eigenen Zeitregler
3. Ein Item je Datei, nur der erste Zeitschritt sichtbar, bis die Ansicht Zeitachsen kann

**Antwort F2 (Otto, 06.11.2026): 1, fest.** Ein Item je Zeitschritt, `datetime` aus der Achse `time` der Datei.

**F3 — Wo liegen die Verweise?**
1. Im Item selbst, je Zeitschritt nur die eigenen Chunks; Typ, Chunkform, Filter, CRS einmal je Datensatz bzw. Datei **(Empfehlung)**
2. Als Manifest je Datei im eigenen Objektspeicher; der Worker erzeugt sie selbst neu
3. Nirgends; jeder Leser erzeugt sie beim Öffnen (5–8 Abrufe je Datei)

**Antwort F3 (Otto, 06.11.2026): 1, fest.** Die Verweise liegen im Item selbst.

**F4 — ARCO-ERA5?**
1. Nicht in M5; bleibt Vergleichsfall, Lizenz und Ort (`us-central1`) wie in §3.3 festgehalten **(Empfehlung)**
2. Katalogeintrag mit Link, ohne Anzeige
3. Als globaler Kontext anbinden (Zarr v2, Zeitachse, Längen 0–360 im Leser nachziehen)

**Antwort F4 (Otto, 06.11.2026): 1, fest.** ARCO-ERA5 nicht in M5; Vergleichsfall.

**F5 — Laufende und vorläufige Daten in M5-11?**
1. Nur abgeschlossene Jahresdateien (Archiv); laufendes Jahr später mit täglichem Lauf **(Empfehlung)**
2. Auch das laufende Jahr, täglich neu verwiesen
3. Auch die vorläufigen Tageswerte mit `expires`

**Antwort F5 (Otto, 06.11.2026): 1, fest.** In M5-11 nur abgeschlossene Jahresdateien; das laufende Jahr später mit täglichem Lauf.

**F6 — Variablen und Datensätze (§8a.2)?**
1. Ein Datensatz je Quelle, Gitter und Takt; die Größen sind Assets eines Items je Zeitschritt (z. B. MeteoSchweiz täglich `ch01r` mit `TabsD`, `TminD`, `TmaxD`, `SrelD`; `RhiresD` auf `ch01h` eigener Datensatz) **(Empfehlung)**
2. Ein Datensatz je Größe, ein Item je Zeitschritt mit einem Asset
3. Ein Datensatz je Quelle mit allen Gittern; Assets unterschiedlicher Gitter in einem Item

**Antwort F6 (Otto, 06.11.2026): 1, fest.** Ein Datensatz je Quelle, Gitter und Takt; die Größen sind Assets eines Items.

**F7 — Die Quelle hat die Datei ersetzt (ETag passt nicht, §8a.3)?**
1. Neue Fehlerart `source_changed` (nicht sofort wiederholt, „Run again“ angeboten); der nächste geplante Lauf verweist neu; die Kachel-URL trägt den Stand des Items **(Empfehlung)**
2. Wie 1, dazu ein sofortiger Anstoß von `discovery` aus `jobs` (Regel in `adr/0025`)
3. Der Leser erzeugt bei `412` die Verweise selbst neu und liest weiter (braucht `h5py` in `readers`, Ergebnis weicht vom Katalog ab)

**Antwort F7 (Otto, 06.11.2026): 1, fest.** Fehlerart `source_changed`, Neuverweis im nächsten geplanten Lauf, Stand des Items in der Kachel-URL. Ob `jobs` zusätzlich selbst einen Lauf anstößt (Option 2), bleibt als Frage an `adr/0025` **offen** (§10 Punkt 5).

---

## 10. Folgen

Nach Ottos Antworten vom 06.11.2026 (F1–F7, Option 1). Diese Liste legt keine Plan-Dateien an und ändert weder Backlog noch M5-Plan.

1. **M5-11** (erste Meteorologie-Quelle, Stufe B) setzt A2 um.
   - **Zwei Pakete, je unter etwa 400 Zeilen ohne Tests** (§8a.1): zuerst `readers` (Store, Zeitindex, `source_changed`), dann `discovery`, `adapters` und Registry (Verweise, Items je Zeitschritt, erster Datensatz).
   - **Kachel-URL trägt den Stand des Items** (z. B. ETag der Datei oder `updated`), damit Browser- und CDN-Caches nach dem Austausch einer Datei kein altes Bild liefern (§8a.3).
   - **Coverage „festes Gitter“:** Fläche aus der Ausdehnung der Collection, Zahl der Zeitschritte aus dem Zeitraum, ohne Abfrage je Item (§8a.2; Checkliste Punkt 2).
   - **Füllwert und Zeilenumkehr:** Der Store liefert `_FillValue` so, dass `xarray` maskiert; der Leser dreht die Zeilen um, wo die Achse `y` aufsteigt (beide Quellen speichern von Süd nach Nord) (§8a.1).
   - Kandidat bleibt MeteoSchweiz `ogd-surface-derived-grid`: unkomprimiert, ein Chunk je Tag, also der einfachste Fall. DWD HYRAS danach (zlib, Chunks über 40 Tage).
   - Plan klärt: die Namen der Registry-Felder für Verweise, Zeitindex und ETag; den Coverage-Weg; das Feld für den Stand in der Kachel-URL. Datensätze nach F6.
   - Tests mit synthetischen NetCDF-4-Dateien (unkomprimiert und zlib, Zeilen von Süd nach Nord) unter `tests/fixtures`; GDAL als Gegenprobe (bitgleich).
2. **Lock-Datei:** `h5py` neu (BSD-3-Clause). **Bedingung aus F1:** Die Lizenzen der mitgelieferten Bibliotheken (HDF5, `libaec`) werden beim Eintrag geprüft und im PR genannt. `kerchunk`, `virtualizarr`, `fsspec`-HTTP und `obstore` kommen nicht dazu. **`.importlinter`:** neuer Vertrag „`h5py` nur in `discovery`“.
3. **`readers`:** `ReferenceStore` neben `GatewayStore`; der Leser lernt einen Zeitindex und die Achsenrichtung; `ZARR_FORMAT = 3` bleibt. `failures.py`, `processing_route._FAILURES` und `frontend/src/jobState.ts` kennen `source_changed` (F7).
4. **Registry:** Format für Rang 3, Zeitachse, Verweise und ETag je Item; `time_range = true`. Die Felder benennt der Plan von M5-11.
5. **Offene Frage an `adr/0025`** (Entwurf, PR #300): Stößt `jobs` bei `source_changed` selbst einen Harvest-Lauf an, oder reicht der nächste geplante Lauf (F7 hier: der geplante Lauf genügt für M5-11)? Außerdem: Listen ohne ETag (DWD) werden über ihren Inhalt entschieden; das passt zu dessen F7.
6. **`adr/0023` §7.1 und §9.1** sowie **`adr/0027` §6.5**: ARCO-ERA5 ist gemessen (Zarr v2, Chunk 1 h × Erde, kein Requester Pays, Lizenz laut README Copernicus) — Nachtrag dort bei Gelegenheit, nicht in diesem PR.
7. **`architekturplan.md` 6.2 Rang 3:** Nachtrag bei Gelegenheit, nicht in diesem PR: „virtuelle Verweise ohne Icechunk, erzeugt mit `h5py` über `gateway`“.

---

## 11. Quellen

**Gemessen (M), 06.11.2026, ohne Adressen von Dateien:**

- FSDI-STAC: Collection `ch.meteoschweiz.ogd-surface-derived-grid`, ihre Items; je eine Jahresdatei Tagesmittel, Niederschlag und Monatsmittel 2024 und eine Tagesdatei (Kopfzeilen, Range, `If-Match`, Chunk-Index, ein Chunk, Lesefälle §4).
- `opendata.dwd.de`, Verzeichnisse von HYRAS-DE; Niederschlag 2024 und Mitteltemperatur 2025 (wie oben), Kopfzeilen der Datei 2026.
- `storage.googleapis.com/gcp-public-data-arco-era5`: `.zmetadata` und ein Chunk von `2m_temperature` (Kopfzeilen, Range, `If-Match`).
- Im Repo: GDAL 3.12.2 aus `rasterio` 1.5.2 (Lock-Datei); im Kratzverzeichnis `h5py` 3.16.0, `kerchunk` 0.2.10, `virtualizarr` 2.8.0 (Importe, Signaturen).

**Am Primärdokument gelesen (P):**

- ARCO-ERA5, README: https://github.com/google-research/arco-era5 (Ort, Aktualisierung, Lizenzabschnitt, Zitierweise)
- Im Repo: `readers/zarr_reader.py`, `gateway/gdal.py`, `catalog/registry.py`, `.importlinter`, `KLAERUNGEN.md` B8/B9, `architekturplan.md` 3.1, 6.2.

**Über das Abrufwerkzeug eines Hilfsagenten gelesen (P\*):**

- GDAL: `frmts/netcdf/netcdfdataset.cpp`, `port/cpl_userfaultfd.cpp`, `doc/source/drivers/raster/netcdf.rst`, `frmts/hdf5/hdf5vfl.h`, `hdf5dataset.cpp`, `doc/source/drivers/raster/zarr.rst`, `frmts/zarr/vsikerchunk_json_ref.cpp`, `doc/source/drivers/raster/icechunk.rst`, `NEWS.md` — https://github.com/OSGeo/gdal
- VirtualiZarr: `virtualizarr/parsers/hdf/hdf.py`, `virtualizarr/accessor.py`, `docs/about/releases.md` — https://github.com/zarr-developers/VirtualiZarr; PyPI https://pypi.org/project/virtualizarr/
- obspec-utils: `src/obspec_utils/registry.py` — https://github.com/virtual-zarr/obspec-utils
- Kerchunk: `kerchunk/hdf.py` — https://github.com/fsspec/kerchunk; PyPI https://pypi.org/project/kerchunk/
- Icechunk: `icechunk-python/python/icechunk/_icechunk_python.pyi`, `storage.py` — https://github.com/earth-mover/icechunk; PyPI https://pypi.org/project/icechunk/
- TiTiler: `src/titiler/xarray/titiler/xarray/io.py` — https://github.com/developmentseed/titiler; PyPI https://pypi.org/project/titiler.xarray/
- zarr-python: `src/zarr/core/codec_pipeline.py`, `src/zarr/codecs/bytes.py` — https://github.com/zarr-developers/zarr-python
- MeteoSchweiz: https://opendatadocs.meteoswiss.ch/c-climate-data/c3-ground-based-climate-data, https://opendatadocs.meteoswiss.ch/general/download
- DWD: https://opendata.dwd.de/climate_environment/CDC/grids_germany/daily/hyras_de/precipitation/ (Auflistung, `DESCRIPTION_HYRAS-DE-PR_V6-1_en.pdf`)

**Suchtreffer (S):**

- Kernel, `UFFD_USER_MODE_ONLY`: https://lore.kernel.org/lkml/20200507131503.02aba5a6@lwn.net/T/
- https://ncar-esds.readthedocs.io/en/latest/posts/2023/cesm2-le-timeseries-kerchunk.html
- https://element84.com/software-engineering/using-kerchunk-to-make-noaas-national-water-model-dataset-more-accessible/
- https://earthaccess.readthedocs.io/en/stable/user/howto/fsspec/
