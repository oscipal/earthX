# ADR 0029 — Leseweg NetCDF/HDF5 für die Meteorologie

- **Status:** **Entwurf** (offen). Fragen F1–F5 in §9.
- **Datum:** 2026-11-06
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

1. **Alle drei Messfälle sind NetCDF-4, also HDF5** [M]. MeteoSchweiz unkomprimiert, ein Chunk je Tag über das ganze Gitter; DWD HYRAS mit zlib Stufe 9 und Chunks über 40 Tage × 178 × 133 Pixel. Beide erlauben Range (`206`), tragen ETag und beachten `If-None-Match` (`304`) und `If-Match` (`412`).
2. **Byte-Ranges reichen; ein Kopieren der Dateien ist für keinen Lesefall nötig** [M]. Ein Zeitschritt kostet bei virtuellen Verweisen genau die Chunks, die er berührt: MeteoSchweiz 1 Abruf mit 355 KB, DWD für ganz Deutschland 25 Abrufe mit 7,5 MB, für eine Kachel 1 Abruf mit 0,5 MB (§4).
3. **GDAL über `/vsicurl/` liest dieselben Dateien ohne neue Abhängigkeit** [M]: Der netCDF-Treiber im Wheel erkennt EPSG:2056 und EPSG:3035 und liefert dieselben Werte wie der Weg über die Verweise (bitgleich). Er braucht etwas mehr Abrufe und Bytes je Zeitschritt (§4).
4. **Die Verweise entstehen mit `h5py` allein** [M], gleich denen von `kerchunk`, in 5–8 Abrufen zu 64 KiB je Datei. VirtualiZarr importiert beim Laden `obstore` [M], das die Importregeln außerhalb von `gateway` verbieten.
5. **Die Zeitachse kommt nicht aus dem STAC der Quelle** [M]. MeteoSchweiz setzt `datetime` der Items auf die letzte Aktualisierung; die Zeit steht nur im Dateinamen und in der Datei. Das Archiv ist ein einziges Item mit 3257 Assets.
6. **Empfehlung (F1):** virtuelle Verweise, erzeugt und gelesen mit eigenem Code über `gateway` (Option A2, §6); je Zeitschritt ein Item, das die Verweise auf seine Chunks selbst trägt (F2, F3). Kein flüchtiger COG-Cache in M5 (F1, Option C nur als spätere Ergänzung).
7. **ARCO-ERA5** taugt als Vergleich, nicht als Quelle für M5: ein Chunk ist eine Stunde × ganze Erde (2,3 MB), eine Zeitreihe an einem Punkt über ein Jahr hieße rund 20 GB (F4).

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
  - `virtualizarr` 2.8.0 importiert beim Laden `obstore` (und `obspec_utils`), und seine Parser verlangen eine `ObjectStoreRegistry` [M]. `obstore` steht in der Verbotsliste des Vertrags `http-only-in-gateway`. VirtualiZarr in `readers` oder `discovery` hieße also, die Importregel zu lockern; das entscheidet nur Otto.
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
  - Verletzt K2: `obstore` ist außerhalb von `gateway` verboten (§5.1); `fsspec` ruft über `aiohttp` ab. Nur mit Lockerung der Importregeln durch Otto.
  - Icechunk bräuchte einen eigenen Speicher für Repository und Manifeste.
- **A2 — eigener Code über `gateway` (empfohlen):**
  - Erzeugen in `discovery`: `h5py` auf einem Dateiobjekt über `gateway`, Seiten zu 64 KiB; je Datei 5–8 Abrufe [M].
  - Ablegen: die Verweise je Zeitschritt im Item (F3).
  - Lesen in `readers`: ein Store nach dem Muster von `GatewayStore`, dessen `get` ein Range-GET mit `If-Match` ist; Entpacken mit `numcodecs` (zlib; schon in der Lock-Datei); Achsenrichtung und CRS aus den Verweisen.
  - Neue Abhängigkeit: `h5py` (BSD-3-Clause) nur für `discovery`. `kerchunk` und VirtualiZarr bleiben draußen.
  - Neuer Code: Store, Erzeugen der Verweise, Zeitindex im Leser (heute nur 2-D-Variablen), Zarr-v2-Filter bzw. Übersetzen der Metadaten (der Leser öffnet heute fest `zarr_format=3`) [P].

### Option B — GDAL-Treiber über `/vsicurl/`

- netCDF-Treiber mit `netCDF:"/vsicurl/…":<variable>`, Band = Zeitschritt.
- Geht heute ohne neue Abhängigkeit und ohne root [M]; CRS und Geotransformation kommen mit [M].
- Kosten etwas höher als A2, aber gleiche Größenordnung (§4); jedes Öffnen liest die Metadaten neu (2–3 Abrufe).
- K2 wie COG: geduldet nach B8, Durchsetzung erst in M6.
- K7: kein Schutz gegen eine Datei, die sich zwischen zwei Abrufen ändert; GDAL kennt kein `If-Match`.
- Die Zeitachse muss die Plattform trotzdem selbst aufbauen (§5.4); GDAL nimmt nur das Lesen ab.
- **Stand der Technik:** siehe §7 (Mechanismus, Sperren im Treiber).

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
| K7 Änderungen | ETag in Icechunk [§7] | ✓ ETag und `If-Match` | ✗ | wie A bzw. B |
| K8 Aufwand | mittel, neue Pakete | mittel, nur `h5py` | gering | hoch |

---

## 7. Stand der Technik

*Wird aus der Recherche ergänzt.*

---

## 8. Empfehlung

*Folgt.*

---

## 9. Fragen an Otto

*Folgt.*

---

## 10. Folgen

*Folgt.*

---

## 11. Quellen

*Folgt.*
