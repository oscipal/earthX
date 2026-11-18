# M5-11 — MeteoSchweiz-Klimagitter über virtuelle Verweise

**Stand:** 18.11.2026, Plan **angenommen** (Otto, 17.11.2026: F1–F7 = 1, F8 mit Vorgabe, F9 = nein; §9.2). PR 1 gemergt (#377, §10). PR 2 umgesetzt im eigenen Draft-PR (§11), Fragen dazu in §11.5.
**Stufe B.** Zwei PRs (Vorgabe Otto, M5-Plan §2 Punkt 11): **PR 1** Verweise und Lesen, **PR 2** Datensatz MeteoSchweiz.
**Aufgabe:** M5-11 aus `docs/plans/m5/m5-discovery-und-suche.md` §6.2 (Opus, hoch).
**Grundlagen:** `adr/0029` (Leseweg NetCDF, F1–F7 = 1, §8a, §10 Punkt 1–4), `adr/0030` §5.6 und F10, `adr/0032` §7 und Backlog 29 (Prüfpunkt Mosaik-Zoom), `adr/0023` §3.1 (Lizenz MeteoSchweiz), `adr/0026` (Bewertungs-Set, Kürzel MCH), `adr/0002` (keine Live-Abrufe aus der Session), `KLAERUNGEN.md` B8, B9, B10–B13, Entscheidungslog 11.11.2026 (Ausgabetyp, Wiedervorlage `float64`).
**Vorgaben Otto zu dieser Aufgabe (17.11.2026):**
- Zwei PRs: (1) Verweise und Lesen, (2) Datensatz MeteoSchweiz.
- Wiedervorlage `float64` (M5-Plan §2 Punkt 9) und Prüfpunkt Mosaik-Zoom bei groben Rastern (`adr/0032`) gehören dazu.
- Keine Live-Abrufe gegen echte Quellen aus der Session (`adr/0002`). Laden der Items macht Otto lokal; die Session nennt die Befehle (PowerShell, `docker compose`), §7.
- Lizenz-Einstufung durch Otto (§9 F8).

Belegstufen wie in `adr/0029`: **M** gemessen (dort, 06.11.2026), **P** am Quelltext gelesen (Code auf `main` 0b72a59), **S** Suchtreffer, **A** eigene Ableitung. Adressen von Dateien, Item-IDs und Prüfsummen der Quelle stehen nicht in diesem Dokument.

---

## 1. Ziel

1. **PR 1 — Verweise und Lesen** (`adr/0029` §8a.1 Paket a, dazu das Erzeugen der Verweise):
   - `discovery` erzeugt virtuelle Verweise aus einer NetCDF-4/HDF5-Datei mit `h5py` über ein Dateiobjekt auf `gateway` (Seiten zu 64 KiB).
   - `readers` liest sie über einen `ReferenceStore` neben `GatewayStore`: jeder Chunk ein Range-GET mit `If-Match`, darüber unverändert `xarray` → rio-tiler.
   - Neue Fehlerart `source_changed` (F7 des ADR) in `readers`, `jobs`, `api`, Frontend.
   - Neues Format in der Registry, Auflösung in `access`, `h5py` in der Lock-Datei, neuer Importvertrag „`h5py` nur in `discovery`“.
   - Alles mit synthetischen NetCDF-4-Dateien getestet, GDAL als Gegenprobe (bitgleich).
2. **PR 2 — Datensatz MeteoSchweiz** (`adr/0029` §8a.1 Paket b):
   - Materialisierer für das Archiv-Item der Collection `ch.meteoschweiz.ogd-surface-derived-grid`: je Tag ein Item, die Größen als Assets (F6 des ADR), die Verweise im Item (F3).
   - Registry-Eintrag bzw. -Einträge (§9 F1) mit vollständiger Onboarding-Checkliste (`projektuebersicht.md` §5, alle Punkte), Eigenheiten nach `adr/0030` §5.6.
   - Coverage „festes Gitter“ (`adr/0029` §8a.2), Stand des Items in der Kachel-URL (§8a.3).
   - Abschluss der Wiedervorlage `float64` (§5.7) und des Prüfpunkts Mosaik-Zoom (§5.6).

**Nicht Teil:** laufendes Jahr und vorläufige Tageswerte (`adr/0029` F5 = 1), Monatswerte und Anomalien (P2 in `adr/0030` §5.6), DWD HYRAS (eigene Aufgabe danach), zeitliche Aggregation über mehrere Tage (eigener ADR nach M5-11, `adr/0030` F10), Rekonstruktionen ab 1864 in EPSG:4326, ein Anstoß von `discovery` aus `jobs` bei `source_changed` (offen an `adr/0025`).

---

## 2. Die Quelle

### 2.1 Was belegt ist (`adr/0029` §3.1, §4, §8a.2)

| Was | Stand | Beleg |
|---|---|---|
| Collection auf der STAC-API der FSDI, derselbe Host wie swissALTI3D | `data.geo.admin.ch`, in `backend/catalog/hosts.yaml` mit 6 Verbindungen und 1 s Abstand für `materialize` | M, P |
| Archiv | ein Item `archive-ch` mit 3257 Assets (Jahresdateien ab 1961, Rekonstruktionen ab 1864) | M |
| `datetime` der Items | Zeitpunkt der letzten Aktualisierung, nicht Zeitraum der Daten; der Zeitraum steht im Assetnamen und in der Achse `time` | M |
| Assets | `file:checksum` und `updated` je Asset, kein `file:size` | M |
| Archiv-Item | ETag, `304` auf `If-None-Match` (1,5 MB) | M |
| Datei | NetCDF-4 (HDF5), CF-1.8, `grid_mapping` `oblique_mercator` mit LV95-Parametern; Zeilen Süd → Nord | M |
| Aufbau Tageswerte | Float32, **unkomprimiert**, Chunk 1 × 240 × 370 (Gitter `ch01r`) bzw. 1 × 265 × 370 (`ch01h`, Niederschlag), ein Chunk je Tag (355 KB) | M (vier Dateien) |
| Füllwert | `_FillValue` −999,99 | M |
| HTTP | `206` auf Range, ETag, Last-Modified, `412` auf falsches `If-Match`, `Access-Control-Allow-Origin: *`; `If-Range` mit falschem ETag liefert die **ganze** Datei | M |
| Kosten | Verweise erzeugen 7–8 GET zu 64 KiB je Jahresdatei; ein Tag 1 GET, 355 KB | M |
| Größen und Beginn (Gitter `ch01r`) | `TabsD` ab 1961; `TminD`, `TmaxD`, `SrelD` ab 1971 | M aus Assetnamen |
| Größen (Gitter `ch01h`) | `RhiresD` ab 1961 | M aus Assetnamen |
| Lizenz | CC BY 4.0; Quellenangabe „Source: MeteoSwiss“, ohne Anschein einer Unterstützung | P (`adr/0023` §3.1) |
| Nutzung | MeteoSchweiz untersagt „excessive use … high-frequency downloading of the same content“ | P (`adr/0023` §3.1) |

Items bis einschließlich 2025: rund 23 700 Tage je Datensatz (`adr/0029` §8a.2). Dateien: `ch01r` 65 (`TabsD`) + 3 × 55 = 230, `ch01h` 65.

### 2.2 Was offen ist und Otto lokal misst (§7 Schritt 1)

- Ob **alle** Jahresdateien den Aufbau der vier gemessenen haben: Typ (Float32 oder `float64`, §5.7), Chunkform, Filter (keine, `shuffle`, `deflate`, andere), Füllwert, Speicherlayout (chunked oder contiguous), Richtung der Zeilen, Einheit, `grid_mapping`.
- Die Achse `time`: Einheit, Kalender, `time_bnds`. **Vermutung [S]:** `RhiresD` ist eine Tagessumme von 06 UTC bis 06 UTC des Folgetags, die Temperaturen gelten für den Kalendertag. Das entscheidet `start_datetime`/`end_datetime` der Items (§5.2).
- Das Muster der Assetnamen für Größe, Gitter, Takt und Jahr (Muster laut `adr/0029` §3.1: `…<größe>_<gitter>.swiss.lv95_<start>_<ende>.nc`).

Dafür kommt mit PR 1 ein Messskript `scripts/m5-11-meteoswiss/probe.py` (Muster `bev-probe`, M5-09): nur `gateway`, keine Datenbank, Ausgabe ohne Adressen. Es braucht `h5py` im Image und läuft deshalb auf dem Branch von PR 1.

---

## 3. Ausgangslage im Code [P]

| Stelle | Heute | Für M5-11 |
|---|---|---|
| `readers/zarr_reader.py` | `GatewayStore` (ein Schlüssel = ein `gateway`-Abruf), `ZarrAsset`, `ZarrReader` über `xarray.open_zarr(…, zarr_format=3, consolidated=True, chunks=None)` und rio-tilers `XarrayReader`; CRS aus `proj:code`, wenn der Store keines trägt | zweiter Store, Zeitschritt, Zeilenumkehr |
| `readers/failures.py` | `412` wird `source_4xx` | `412` wird `source_changed` |
| `jobs/queue.py:64` | `RETRYABLE` = Timeout, 5xx, Lease | unverändert (F7: nicht sofort wiederholen) |
| `api/processing_route.py:201` | Titel je Fehlerart | Titel für `source_changed` |
| `frontend/src/jobState.ts` | `FAILS_AGAIN` ohne „Run again“ | `source_changed` nicht darin (Run again angeboten) |
| `catalog/registry.py:54` | `DataFormat`: `zarr`, `cog`, `legacy` | neuer Wert für Rang 3 |
| `access/resolve.py:61` | `_READERS` nur COG und Zarr; anderes → `NoReader` | neuer Eintrag |
| `catalog/registry.py:97` | `AdapterKind` bis `bev-atom` | neuer Materialisierer |
| `discovery/materialize.py` | Befehl `python -m earthx.discovery.materialize <id> [--force]`, Fassung je Lauf, `upsert_items`, `unchanged` | unverändert genutzt |
| `api/coverage_route.py:222` | `local-sql` ohne `single_coverage_product` → `501`; nur Flächenweg gebaut, ohne Histogramm | Weg „festes Gitter“ (§5.4) |
| `frontend/src/api.ts:488` | Kachel-URL trägt nur `asset` (dazu Darstellung); keine Fassung | Stand des Items (§5.5) |
| `frontend/src/processingDefaults.ts:57` | Ausgabetyp aus `raster:bands[].data_type` des Items (`processingOrder.ts:213`) | Items tragen `raster:bands` (§5.7) |
| `frontend/src/processingPreview.ts:536` | Mosaik erst ab zwei Szenen derselben Gruppe | §5.6 |
| `api/mosaic_tiles.py:128` | Budget je Kachel 32 **Dateien**, 4 s; das Budget für Gitter (32 Anfragen, 32 MB, `adr/0032` §7) ist nicht gebaut | §5.6 |
| `gateway/policy.py:156` | höchstens 8 MiB je Antwort | ein Chunk 355 KB, das Archiv-Item 1,5 MB |
| Lock-Datei | `zarr` 3.1.6, `xarray`, `numcodecs` 0.17.0 vorhanden; kein `h5py` | `h5py` neu (F1 des ADR) |

---

## 4. PR 1 — Verweise und Lesen

### 4.1 Form der Verweise im Item (§9 F2)

Vorschlag: **alles, was der Leser braucht, steht je Asset im Item** (`adr/0029` F3 = 1). Ein Item ist damit für `tiler`, Worker und Runner vollständig (B9), ohne Nachschlagen in der Registry.

```yaml
assets:
  TabsD:
    href: <Jahresdatei>                 # die Datei der Quelle, Download des Originals
    type: application/x-netcdf
    roles: [data]
    earthx:refs:
      etag: '"…-1"'                     # ETag der Datei beim Erzeugen; Lesen mit If-Match
      variable: TabsD
      dtype: <f4                         # HDF5-Typ als NumPy-String, mit Bytereihenfolge
      shape: [1, 240, 370]               # die Chunk-Zeile dieses Zeitschritts: (Zeit, y, x)
      chunks: [1, 240, 370]
      time_offset: 0                     # Lage des Zeitschritts in der Chunk-Zeile (DWD: 0..39)
      filters: []                        # Reihenfolge wie in HDF5: shuffle, deflate
      fill_value: -999.99
      y_ascending: true                  # Zeilen von Süd nach Nord → der Leser dreht um
      transform: [1000.0, 0.0, x0, 0.0, 1000.0, y0]   # Mitte bzw. Ecke laut CF-Koordinaten, siehe A3
      chunk_refs: [[[0, 0, 0], offset, length]]       # je Chunk der Zeile: Index, Offset, Länge
properties:
  proj:code: EPSG:2056
```

- **Name `earthx:refs`**: eigene Erweiterung; ein STAC-Standard für virtuelle Verweise existiert nicht [S].
- **Nur die Chunk-Zeile des Tages**, nicht die ganze Zeitachse der Datei: Der Store bietet `xarray` ein Feld der Form `shape` an, der Leser wählt `time_offset`. Bei MeteoSchweiz ist die Zeile ein Chunk (1 Verweis), bei DWD wären es 25 mit `time_offset` 0–39. Der Leser braucht damit keine Kenntnis der übrigen Tage.
- Größe: rund 0,4 KB je Asset, bei vier Assets rund 2 KB je Item, passend zu `adr/0029` §8a.2.

### 4.2 Erzeugen (`discovery/netcdf_refs.py`)

- `GatewayFile`: schreibgeschütztes Dateiobjekt (`read`, `seek`, `tell`) über `Gateway.get` mit `Range` und `If-Match`, Seiten zu 64 KiB mit kleinem Seitenpuffer. Die Dateigröße kommt aus `Content-Range` der ersten Antwort (die Quelle nennt kein `file:size`).
- `h5py.File(GatewayFile, "r")` liest Kopf und Chunk-Index; `dataset.id.get_chunk_info` je Chunk liefert Offset und Länge (gemessen gleich `kerchunk`, `adr/0029` §5.1). Contiguous gespeicherte Felder werden ein Chunk über das ganze Feld (`get_offset`, `get_storage_size`).
- Ausgabe je Datei: Kopf (Typ, Chunkform, Filter, Füllwert, Achsen, CRS, Geotransformation, ETag, Last-Modified) und je Zeitschritt die Verweise seiner Chunk-Zeile.
- **Unterstützte Filter:** keine, `shuffle`, `deflate` (zlib). Alles andere (szip, Fletcher32, lzf, Blosc als HDF5-Plugin) → `UnsupportedLayout` mit Name des Filters; die Datei wird nicht verwiesen und der Lauf scheitert ausdrücklich, statt still Fehlwerte zu lesen.
- **CRS:** `pyproj.CRS.from_cf` auf die Attribute des `grid_mapping`, dann `to_epsg()`; ohne EPSG-Code scheitert die Datei (`adr/0029` §5.3). Die Geotransformation kommt aus den Koordinaten `x`/`y` (bzw. `E`/`N`) und muss gleichmäßig sein.
- **Zeit:** aus der Achse `time` mit `units` und `calendar` (CF), bei vorhandenen `time_bnds` deren Grenzen.
- **Füllwert:** das CF-Attribut `_FillValue` (DWD: das HDF5-Füllattribut weicht ab, `adr/0029` §3.2).
- Jede Datei kostet 5–8 Abrufe (`adr/0029` §4); `h5py` liest nichts über die Metadaten hinaus.

### 4.3 Lesen (`readers/reference_store.py`, `readers/zarr_reader.py`)

- **`ReferenceStore(zarr.abc.store.Store)`**, schreibgeschützt und ohne Listing wie `GatewayStore`. Er liefert:
  - `zarr.json` mit konsolidierten Zarr-v3-Metadaten aus `earthx:refs`: Form, Typ, Chunkform, Codecs (`bytes` mit Bytereihenfolge, `numcodecs.shuffle`, `numcodecs.zlib`), `fill_value`, `dimension_names` = `time`, `y`, `x`; dazu die Attribute `_FillValue`, damit `xarray` maskiert (Lücke des Prototyps, `adr/0029` §8a.1);
  - kleine Felder `x` und `y` aus der Geotransformation;
  - je Chunk-Schlüssel einen `Gateway.get` mit `Range: bytes=o-(o+l-1)` und `If-Match: <etag>`.
- **Prüfungen beim Lesen:** Antwort `206` mit genau `l` Bytes, sonst `ReferenceMismatch` (eine Quelle, die `Range` überhört und `200` mit der ganzen Datei schickt, endet spätestens an der Grenze von 8 MiB in `gateway`). Kein `If-Range` (`adr/0029` §5.1).
- **`ZarrAsset`** bekommt ein Feld `refs` (die geprüfte Form von `earthx:refs`) statt `store_url`/`group`; `ZarrReader` wählt danach den Store, nimmt `isel(time=time_offset)` und dreht `y` um, wo `y_ascending`. Der Rest (`tile`, `part`, `feature`, `preview`, `statistics`, mehrere Variablen, CRS aus `proj:code`) bleibt.
- **Chunk-Cache (§9 F6):** Ein Tag ist ein Chunk von 355 KB; jede Kachel einer Ansicht bräuchte ihn neu, und MeteoSchweiz untersagt das wiederholte Laden desselben Inhalts. Vorschlag: ein LRU je Prozess in `readers`, Schlüssel (URL, ETag, Offset, Länge), Größe aus der Umgebung, nur im `tiler` eingeschaltet (64 MiB, wie `TILER_CURL_CACHE_BYTES` dort für GDAL); Worker und Runner ohne Cache (B9: kein Zustand zwischen Aufrufen).
- `h5py` wird in `readers` nicht gebraucht und nicht importiert.

### 4.4 Fehlerart `source_changed` (`adr/0029` F7 = 1)

- `readers/failures.py`: `UpstreamError` mit `412` → `source_changed` (vor der Regel für 4xx), in `SOURCE_KINDS`.
- `jobs/queue.py`: **nicht** in `RETRYABLE`.
- `api/processing_route.py`: `"source_changed": (502, "The source has updated this file; it is being catalogued again")` (Wortlaut aus dem ADR).
- `frontend/src/jobState.ts`: nicht in `FAILS_AGAIN`, also „Run again“; Anzeige des Titels wie bei den übrigen Fehlerarten.
- `tiler`: dieselbe Art als `502` mit festem Titel; kein Ausweichen auf alte oder neue Bytes.

### 4.5 Registry, `access`, Abhängigkeit, Importregel

- `DataFormat.NETCDF_REFS = "netcdf-refs"` (Auslegung A1); `access/resolve.py` liest `earthx:refs` des Assets und baut den `ZarrAsset` mit `refs`; ein Asset ohne `earthx:refs` → `NoReader` mit Grund.
- Registry-Prüfung: `netcdf-refs` verlangt `zarr: null`, `georeferencing: geotransform`, `source.item_holding: materialized`.
- `h5py` 3.16 in `backend/requirements.txt` und `requirements.lock` (mit Hashes für x86_64 und aarch64, `adr/0016`). **Bedingung aus F1 des ADR:** Lizenzen der mitgelieferten Bibliotheken prüfen und im PR nennen (`h5py` BSD-3-Clause; HDF5 eigene BSD-artige Lizenz; `libaec` mit `libsz` BSD-2-Clause) und in `backend/THIRD_PARTY_NOTICES.md` eintragen.
- `.importlinter`: neuer Vertrag `h5py-only-in-discovery` (Typ `forbidden`, alle anderen Module); `test_module_boundaries.py` und `test_import_linter_catches_violations.py` nachziehen. Eine Verschärfung, keine Lockerung.
- Messskript `scripts/m5-11-meteoswiss/probe.py` und Dienst `meteoswiss-probe` (Profil `measure`) in `docker-compose.yml`, wie `bev-probe`.

### 4.6 Tests (alle ohne Netz)

Fixtures sind **synthetisch**: kleine NetCDF-4-Dateien, die ein Test mit `h5py` erzeugt (CF-Attribute, Dimension Scales), ausgeliefert von einem lokalen HTTP-Server mit `Range`, `ETag` und `If-Match` (Muster der lokalen Server in `test_failures.py`).

| Fall | Erwartung |
|---|---|
| unkomprimiert, Chunk = 1 Tag, Zeilen Süd → Nord | Verweise wie `get_chunk_info`; Tag bitgleich zu GDAL (`netCDF:` auf die lokale Datei) nach Umkehr |
| `shuffle` + `deflate`, Chunk über 4 Tage (Muster DWD) | richtiger Tag aus `time_offset`; bitgleich |
| contiguous | ein Chunk über das Feld |
| Füllwert | maskiert → NaN, Typ bleibt Float32 |
| Datei nach dem Erzeugen ersetzt (anderes ETag) | `412` → `source_changed`; Job nicht wiederholt |
| Server überhört `Range` (`200`) bzw. liefert falsche Länge | `ReferenceMismatch`, nie Fehlwerte |
| Filter szip/Fletcher32, CRS ohne EPSG, ungleichmäßige Achse | `UnsupportedLayout` beim Erzeugen |
| `earthx:refs` fehlt oder ist kaputt | `NoReader` bzw. abgelehnt mit Grund |
| Abrufe zählen | Erzeugen höchstens 8 Abrufe je Datei; ein Tag ein Abruf; zweite Kachel aus dem Cache ohne Abruf; Worker ohne Cache |
| Adresse außerhalb der Allowlist im Item | abgelehnt vor dem ersten Abruf |
| Runner | liest dasselbe Item bitgleich (Test über `runner` wie bei COG) |
| Importvertrag | `h5py` außerhalb `discovery` wird gemeldet |

---

## 5. PR 2 — Datensatz MeteoSchweiz

### 5.1 Materialisierer `meteoswiss-grid`

- Neuer `AdapterKind.METEOSWISS_GRID = "meteoswiss-grid"`, nur `materialize` (Muster `bev-atom`, `cop-dem-bucket`).
- **Fassung des Laufs:** bedingter Abruf des Archiv-Items mit `If-None-Match` → `304` = `unchanged` (Abnahme M5 Punkt 3). Bei `200` ist die Fassung ein Hash über (Assetname, `file:checksum`) der gewählten Assets.
- **Auswahl der Assets:** Größen und Gitter aus der Registry (`source.asset_keys` bzw. ein Muster, Auslegung A2), Takt täglich, nur abgeschlossene Jahre bis zum Vorjahr des Laufs (`adr/0029` F5 = 1).
- **Bei Änderung** werden in M5-11 alle gewählten Dateien neu verwiesen (230 + 65 Dateien, rund 2 400 Abrufe, mit 1 s Abstand rund 40 min). Nur geänderte Dateien neu zu verweisen braucht den Stand je Datei aus pgstac; das bringt M5-24 mit dem Takt (Auslegung A4).
- Die Jahresdateien eines Gitters werden je Tag zu einem Item zusammengeführt; eine Größe ohne Daten an dem Tag fehlt als Asset (`TminD` usw. vor 1971).

### 5.2 Items

- `id`: `<dataset_id>-<JJJJMMTT>`.
- `datetime`, `start_datetime`, `end_datetime` aus der Achse `time` bzw. `time_bnds` (§2.2); `updated` = jüngstes Last-Modified der Dateien des Items (§5.5).
- `geometry`: Rahmen des Gitters (LV95, verdichtet nach WGS 84), bei allen Items gleich.
- `proj:code: EPSG:2056`, `gsd: 1000`.
- Je Asset `raster:bands: [{data_type: float32, nodata: nan, unit: …}]` aus dem Kopf der Datei (§5.7).

### 5.3 Registry-Einträge (§9 F1, Auslegung A5)

Vorschlag für die Kennungen: `meteoswiss-daily-1km` (Gitter `ch01r`: `TabsD`, `TminD`, `TmaxD`, `SrelD`) und `meteoswiss-daily-precip-1km` (Gitter `ch01h`: `RhiresD`).

| Feld | Vorschlag | Grund |
|---|---|---|
| `format` | `netcdf-refs` | §4.5 |
| `data_class` | `raster-time-series` | ein Feld je Tag |
| `capabilities` | `roi`, `time_range`, `band_math`, `interpolation`, `reprojection`, `value_masking`, `normalization` an; `masking`, `quad_pol`, `terrain`, `single_coverage_product` aus; `ml_processing` an | `adr/0030` §5.6 (B0, P1) |
| `band_units` | `TabsD`, `TminD`, `TmaxD`: `°C`; `SrelD`: `%`; `RhiresD`: `mm` | Einheiten der Dateien, Otto prüft im Messlauf |
| `viewer` | `group_by` und `results_group_by` `[datetime]`, `min_zoom` 0, `max_zoom` 12, `overview: own`, `browse: full_resolution` | §5.6 |
| `default_render` | `TabsD` mit Farbskala für Temperatur (`rescale` −20…30 °C), `RhiresD` mit Skala für Niederschlag (0…50 mm); `resampling: nearest` | Auslegung A6 |
| `index_presets`, `composite_presets`, `step_presets` | leer | `adr/0030` §5.6: zunächst keine Quick processings |
| `search_filters` | leer | die Quelle hat keine Eigenschaften zum Filtern außer Zeit |
| `coverage` | Weg „festes Gitter“ (§5.4) | |
| `access` | `account: none`, `cors: true` | M |
| `source.data_region` | `aws:eu-central-1` | wie swissALTI3D (`adr/0023` §7.3) |
| `keywords` | deutsch und englisch (Temperatur, Niederschlag, Sonnenscheindauer, Klima, Schweiz, 1 km …) | `adr/0026` F7 |
| `license` | Vorschlag in §9 F8, Einstufung durch Otto | |
| `limitations` | z. B. „Values of the latest year are final only from February of the following year.“ nach Bedarf | Otto bestätigt im PR |

Der Host `data.geo.admin.ch` steht schon in `hosts.yaml`; nichts Neues.

### 5.4 Coverage „festes Gitter“ (`adr/0029` §8a.2, §9 F4)

- Neuer Wert `coverage.provider: fixed-grid`: Fläche = Rahmen des Gitters (aus `spatial_extent`), Zahl = Zahl der Zeitschritte im gewählten Zeitraum, Histogramm je Monat aus dem Zeitraum gerechnet; keine Abfrage je Item.
- Die Heatmap ist dann über der Fläche überall gleich (jeder Tag deckt alles); die Zeitleiste zeigt die Monate.
- Checkliste Punkt 2 ist damit erfüllt, ohne den nicht gebauten Dichteweg (F4 von `adr/0004`).

### 5.5 Stand des Items in der Kachel-URL (`adr/0029` F7, §9 F3)

- Vorschlag: Parameter `v=<updated>` an Kachel- und Vorschau-URLs von Items mit `earthx:refs` (Frontend `api.ts::buildTileTemplate`), Wert = `properties.updated` des Items, ohne Kennung oder Hash der Quelle (M5-Plan §10).
- Der `tiler` liest den Parameter nicht; er unterscheidet nur die Caches (Browser, später CDN). Ein Austausch der Datei ändert `updated` beim nächsten Lauf und damit die URL.
- Job-Provenienz: das ETag je Datei als `input_version` der Art `etag` (die Art gibt es schon, `processing/recipe.py:745`).

### 5.6 Prüfpunkt Mosaik-Zoom bei groben Rastern (`adr/0032` §7, Backlog 29)

Befund [P, A]:

- Ein Tag ist **ein** Item über das ganze Gitter. Mehrere Szenen derselben Gruppe gibt es nicht; die Karte zeigt die Szene des Tages einzeln (`processingPreview.ts:536`: Mosaik erst ab zwei Szenen). Die Sorge aus Backlog 29 („grobe Daten bekommen ab Stufe 8 keine Mosaik-Vorschau“) betrifft diesen Datensatz nicht; einen eigenen `MIN_MOSAIC_ZOOM` gibt es nicht mehr.
- Eine Kachel liest bei jedem Zoom genau den einen Chunk des Tages (355 KB) je Größe; das liegt weit unter dem Budget für Gitter aus `adr/0032` §7 (32 Anfragen, 32 MB). Ein eigenes Budget für Gitter ist für M5-11 nicht nötig; es bleibt für DWD (25 Chunks je Tag) und globale Gitter vorgemerkt.
- Also `overview: own`, `min_zoom: 0` (Regel `adr/0032` §7, Zeile „eine Datei ohne Übersichten, kleines Feld“). Mit dem Chunk-Cache (§4.3) holt eine Ansicht den Chunk einmal.
- **Beleg** durch Ottos Messung mit `measure-tiles` (§7 Schritt 5): Abrufe und Zeit je Kachel z0–z12. Ergebnis kommt als Nachtrag in diesen Plan und als Zeile ins Entscheidungslog, damit Backlog 29 geschlossen werden kann.

### 5.7 Wiedervorlage `float64` (M5-Plan §2 Punkt 9, Log 11.11.2026)

- Wortlaut: „Wiedervorlage mit M5-11, falls eine float64-Quelle kommt.“
- Befund: Die vier gemessenen Dateien sind **Float32** [M]. Ist das für alle Dateien so (§7 Schritt 1), ist M5-11 keine float64-Quelle; die Regel bleibt unverändert und die Wiedervorlage wird mit „kein Anlass“ geschlossen. Das Panel bietet dann wie bei jeder Float32-Quelle Float32 an.
- Damit das Panel den Typ überhaupt kennt, tragen die Items `raster:bands[].data_type` (§5.2); ohne Angabe fiele es auf „nur float32“ zurück (`processingDefaults.ts`).
- Findet der Messlauf doch `float64`, legt die Session das Otto im PR mit den Optionen aus dem Log vom 11.11.2026 vor, bevor PR 2 weitergeht.

### 5.8 Download

Siehe §9 F5. Der Zuschnitt (AOI) als GeoTIFF geht über den bestehenden Weg wie bei jedem Datensatz.

### 5.9 Bewertungs-Set (§9 F7)

Das Set kennt ein Kürzel `MCH` mit `id: null` (`backend/tests/fixtures/search/evaluation_set.yaml:20`), erwartet für „Niederschlag“, „precipitation grid“, „daily air temperature“ und „Sonnenscheindauer“. Mit zwei Datensätzen (F1 = 1) braucht es zwei Kürzel; das Set ist von Otto freigegeben (`adr/0026` F4), daher die Frage.

### 5.10 Live-Smoke und Tests

- Live-Smoke: die Datei in die Zeile der materialisierten Datensätze (wie M5-09 F8); er läuft in GitHub Actions nach dem Merge, nicht aus der Session.
- Tests ohne Netz: Materialisierer gegen ein synthetisches Archiv-Item und synthetische Jahresdateien (lokaler Server); `304` → `unchanged`; laufendes Jahr ausgelassen; Größen ab verschiedenen Jahren; Registry-Eintrag streng geladen; Coverage „festes Gitter“ mit Zeitfilter, ohne Zeitfilter, außerhalb des Zeitraums, Fläche außerhalb des Gitters; Kachel-URL mit `v=`; Ausgabetyp Float32 aus `raster:bands`; Collection Search findet die Einträge.

---

## 6. Schnitt

| PR | Inhalt | geschätzt (ohne Tests, Fixtures, Lock) |
|---|---|---|
| 1 | `netcdf_refs.py`, `ReferenceStore`, Änderungen in `ZarrReader`/`access`/`failures`/`jobs`/`api`/Frontend (`source_changed`), `DataFormat`, Importvertrag, Messskript | rund 450 Zeilen |
| 2 | Adapter `meteoswiss-grid`, Coverage „festes Gitter“, `v=` im Frontend, Registry-Einträge (YAML), Nachträge | rund 350 Zeilen ohne YAML |

PR 1 liegt knapp über dem Richtwert von 400 Zeilen; das Messskript (rund 80 Zeilen) ließe sich in PR 2 verschieben, braucht aber `h5py` und soll vor PR 2 laufen. Ich lasse es in PR 1.

**Branches:** PR 1 auf `claude/epic-euler-hgc05c` (dieser Draft-PR, Plan und Umsetzung). PR 2 nicht gestapelt: eine neue Session nach dem Merge von PR 1, Branch von `main` (Otto, F9).

---

## 7. Was Otto lokal ausführt

Wie bei M5-09: alles über `docker compose` aus der Repo-Wurzel, in PowerShell wie in bash dieselbe Zeile. `--build` baut das Image des Backends mit dem Stand des Branches.

**Schritt 0 — Branch holen** (PR 1 ist umgesetzt, §10):

```powershell
git fetch origin claude/epic-euler-hgc05c
```

```powershell
git checkout claude/epic-euler-hgc05c
```

**Schritt 1 — Assets und Aufbau der Dateien messen** (vor PR 2; nur `gateway`, keine Datenbank, Ausgabe ohne Adressen und darf in den PR):

```powershell
docker compose run --build --rm meteoswiss-probe --assets
```

Ein Abruf: Zahl der Assets je Größe, Gitter, Takt und Jahr.

```powershell
docker compose run --rm meteoswiss-probe --layout
```

Alle rund 295 Jahresdateien der beiden Gitter, je 5–8 Abrufe; mit 1 s Abstand je Host rund 40 min. Ergebnis: Typ, Chunkform, Filter, Füllwert, Layout, Zeitachse, Einheiten, CRS je Gruppe gleicher Dateien. Entscheidet §5.7 und `start_datetime`/`end_datetime`.

**Schritt 2 — Items laden** (erst mit PR 2, auf dessen Branch; die Session von PR 2 nennt die Befehle neu, hier der Stand dieses Plans; `materialize` startet `catalog-load` selbst):

```powershell
docker compose run --build --rm materialize meteoswiss-daily-1km
```

```powershell
docker compose run --rm materialize meteoswiss-daily-precip-1km
```

Je rund 30 bzw. 10 min, rund 23 700 Items je Datensatz.

**Schritt 3 — zweiter Lauf ohne Änderung** (erwartet `unchanged`, ein bedingter Abruf):

```powershell
docker compose run --rm materialize meteoswiss-daily-1km
```

**Schritt 4 — Zahl und Zeitraum der Items:**

```powershell
"select collection, count(*), min(datetime), max(datetime) from pgstac.items where collection like 'meteoswiss-%' group by collection;" | docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At'
```

**Schritt 5 — Prüfpunkt Mosaik-Zoom (§5.6), ein Sommertag, ohne Ort im Repo:**

```powershell
docker compose run --build --rm measure-tiles meteoswiss-daily-1km --bbox 6.0,46.0,10.4,47.7 --datetime 2024-07-01/2024-07-01 --zooms 0-12 --threads 4
```

**Schritt 6 — im Browser:** `docker compose up -d --build`, Datensatz wählen, Zeitleiste, von z3 bis z12 zoomen (Crop and merge, angeheftete Ebene, Suchtreffer); Band math `TmaxD - TminD`; ein Job mit Zuschnitt; Coverage mit Zeitfilter.

**Schritt 7 — Live-Smoke** nach dem Merge auf `main` in GitHub Actions („Live smoke“ → „Run workflow“).

---

## 8. Risiken

- **GDAL als Gegenprobe:** Der netCDF-Treiber muss die von `h5py` geschriebenen Testdateien als NetCDF-4 erkennen (Dimension Scales, `_Netcdf4Dimid`). Gelingt das nicht, prüfen die Tests gegen den HDF5-Treiber von GDAL bzw. gegen `numpy` aus `h5py`; im PR genannt.
- **Zwei HDF5 im Prozess** (GDAL und `h5py`): nur in `discovery` und in Tests; gemessen bitgleich (`adr/0029` §8a.4).
- **Item-Menge:** rund 47 000 Items mit Verweisen, rund 100–150 MB JSON in pgstac; Größenordnung wie der DEM.
- **Lauf bei Änderung des Archivs:** alle Dateien neu (40 min), weil der Stand je Datei erst mit M5-24 kommt (A4).
- **Zeitzone der Tageswerte:** falsch gesetzte Grenzen verschieben die Zeitleiste um einen Tag; der Messlauf klärt es.

---

## 9. Fragen an Otto

Antwort am Handy reicht als „F1 1, F2 1, …“.

**F1 — Welche Datensätze in M5-11?**
1. Zwei: täglich `ch01r` (`TabsD`, `TminD`, `TmaxD`, `SrelD`) und täglich `ch01h` (`RhiresD`); gleicher Code, nur ein zweiter Eintrag, und das Bewertungs-Set erwartet Niederschlag **(Empfehlung)**
2. Nur `ch01r` (Temperatur, Sonnenschein); Niederschlag als kleine Folgeaufgabe
3. Wie 1, dazu die Monatswerte beider Gitter

**F2 — Wo stehen Kopf und Verweise?**
1. Alles je Asset im Item (`earthx:refs`: ETag, Typ, Chunkform, Filter, Füllwert, Achsen, Verweise der Chunk-Zeile), §4.1 **(Empfehlung)**
2. Kopf (Typ, Chunkform, Filter, CRS) in der Registry, im Item nur ETag und Verweise; kleinere Items, aber der Leser braucht die Registry

**F3 — Stand des Items in der Kachel-URL?**
1. `v=<updated>` des Items; der `tiler` liest ihn nicht, er trennt nur die Caches **(Empfehlung)**
2. Wie 1, und der `tiler` lehnt ein abweichendes `v` mit `409` ab
3. Kurzer Hash der ETags statt `updated`

**F4 — Coverage?**
1. Weg „festes Gitter“ in PR 2 (Fläche aus der Ausdehnung, Zahl der Tage, Histogramm je Monat) **(Empfehlung)**
2. Nur Fläche wie bei Einmal-Produkten, ohne Zeit; Dichte später

**F5 — „Download full scene(s)“ für einen Tag?**
1. Die Originale: je Größe die Jahresdatei der Quelle (rund 130 MB, unter der Grenze von 500 MB), direkt beim Anbieter (CORS vorhanden) **(Empfehlung, Regel „Download im Originalformat“)**
2. Kein Download ganzer Szenen bei diesem Datensatz, nur der Zuschnitt des Tages als GeoTIFF
3. Beides

**F6 — Chunk-Cache?**
1. LRU je Prozess nur im `tiler`, 64 MiB; Worker und Runner ohne (B9) **(Empfehlung)**
2. Kein Cache in M5-11; jede Kachel holt den Chunk neu

**F7 — Bewertungs-Set bei zwei Datensätzen?**
1. `MCH` wird zwei Kürzel: `MCH` = `meteoswiss-daily-1km` (Q08, Q21, Q22), `MCHP` = `meteoswiss-daily-precip-1km` (Q08, Q19, Q20); beide in den Negativfragen „nie“ **(Empfehlung)**
2. `MCH` nur für Temperatur; Q19 und Q20 bleiben ohne MeteoSchweiz
3. Erst entscheiden, wenn M5-23 das Set ohnehin anfasst

**F8 — Lizenz (Einstufung durch dich, Vorschlag aus `adr/0023` §3.1 [P]):**
1. `CC-BY-4.0`, alle Rechte an, Stufe `processing`, `attribution_unmodified` „Source: MeteoSwiss“, `attribution_modified` „Source: MeteoSwiss (modified)“, `legal_status: cleared` **(Empfehlung)**
2. Wie 1, anderer Wortlaut der Attribution (bitte nennen)
3. Erst nach eigener Prüfung des Primärtexts

**F9 — Zweiter Branch für PR 2?**
1. Ja, `claude/m5-11-meteoswiss-dataset`, gestapelt auf PR 1, eigener Draft-PR **(Empfehlung)**
2. PR 2 erst nach dem Merge von PR 1, dann von `main`

### 9.1 Auslegungen (gelten, wenn du nicht widersprichst)

- **A1:** Formatname `netcdf-refs`, Erweiterung `earthx:refs`, Adapter `meteoswiss-grid`, Fehlerart `source_changed`.
- **A2:** Größen und Gitter je Eintrag als `source.asset_keys` mit festem Schlüssel je Größe (`TabsD` usw., wie die Quelle sie nennt).
- **A3:** Geotransformation aus den CF-Koordinaten (Zellmitten), Ecke = Mitte − halbe Zelle; GDAL-Gegenprobe im Test.
- **A4:** Bei einer Änderung des Archivs werden in M5-11 alle Dateien neu verwiesen; nur geänderte Dateien kommen mit M5-24.
- **A5:** Kennungen und Titel: `meteoswiss-daily-1km` „MeteoSwiss daily climate grids 1 km“, `meteoswiss-daily-precip-1km` „MeteoSwiss daily precipitation 1 km“; `category: weather_climate`.
- **A6:** Darstellung `nearest` (die 1-km-Zellen bleiben sichtbar), Temperatur mit einer divergierenden Farbskala, Niederschlag mit einer sequenziellen; genaue Skala im PR zur Ansicht.
- **A7:** Das Messskript liegt unter `scripts/m5-11-meteoswiss/` und kommt nicht ins Image (wie `bev-probe`).

### 9.2 Antworten von Otto (17.11.2026)

| Frage | Antwort |
|---|---|
| F1 | 1: zwei Datensätze, `ch01r` und `ch01h` |
| F2 | 1: alles je Asset im Item (`earthx:refs`) |
| F3 | 1: `v=<updated>`; ein Zeitstempel, kein Hash, also ok nach M5-Plan §10 |
| F4 | 1: Coverage „festes Gitter“ in PR 2 |
| F5 | 1: die Jahresdateien der Quelle als Originale |
| F6 | 1: LRU nur im `tiler`, 64 MiB |
| F7 | 1: `MCH` und `MCHP` |
| F8 | Stufe Processing, Attribution „Source: MeteoSwiss“. Lizenzangabe **nicht** „CC BY 4.0“, sondern die Nutzungsbedingungen von MeteoSchweiz (opendata.swiss „BY“: offene Nutzung, Quellenangabe Pflicht; https://opendatadocs.meteoswiss.ch/general/terms-of-use), sofern der Lizenzkatalog das abbildet, sonst Vorschlag im Plan (§9.3) |
| F9 | Nein: PR 2 kommt nach dem Merge von PR 1 in einer neuen Session; diese Session setzt nur PR 1 um |
| A1–A7 | gelten |
| Zusatz | Nur abgeschlossene, korrigierte Daten (Archiv- bzw. Jahresdateien) nach `adr/0029` F5, keine laufend aktualisierten Tagesdateien des aktuellen Jahres |

### 9.3 Lizenzangabe (F8): wie sie sich abbilden lässt

- **Lizenzkatalog:** `backend/catalog/licenses/terms.yaml` (`adr/0033` §6.2) gibt es noch nicht; er kommt mit M5-20 und gilt für gelistete Einträge. Er bildet die Angabe heute also nicht ab.
- **Voller Eintrag:** Das Feld `license` eines vollen Eintrags bildet sie schon ab, so wie bei swissALTI3D (Nutzungsbedingungen ohne SPDX-Kennung). Vorschlag für PR 2:

```yaml
license:
  spdx_id: null
  name: Terms of use of MeteoSwiss open data
  url: https://opendatadocs.meteoswiss.ch/general/terms-of-use
  commercial_use: true
  distribution: true
  derivatives: true
  share_alike: false
  attribution_required: true
  tier: processing
  attribution_unmodified: "Source: MeteoSwiss"
  attribution_modified: "Source: MeteoSwiss (modified)"   # Otto, 17.11.2026, wie swissALTI3D
  terms:
    url: https://opendatadocs.meteoswiss.ch/general/terms-of-use
    notice: …                                        # Wortlaut aus den Bedingungen, in PR 2 von Otto bestätigt
legal_status: cleared
```

- **Entschieden für PR 2 (Otto, 17.11.2026):** Bearbeitete Daten tragen „Source: MeteoSwiss (modified)“, wie bei swissALTI3D (Form aus `adr/0023` §7.2); unbearbeitete „Source: MeteoSwiss“. Die Bedingungen verlangen, dass die Quellenangabe nicht wie eine Unterstützung durch MeteoSchweiz aussieht (`adr/0023` §3.1).
- Kommt der Lizenzkatalog mit M5-20, erhält er einen Eintrag „opendata.swiss BY / Nutzungsbedingungen MeteoSchweiz“ mit der URL der Bedingungen in `matches`. Das wird dort entschieden.

---

## 10. Umsetzung PR 1 (17.11.2026)

### 10.1 Was gebaut ist

| Stelle | Inhalt |
|---|---|
| `discovery/netcdf_refs.py` | `GatewayFile` (Seiten zu 64 KiB über `gateway`; ab der zweiten Seite `If-Match`); `reference_file` (`h5py` im Thread, Anfragen auf der Schleife des Aufrufers; ohne Variablennamen genau das eine Feld über `time`, y, x); `step_references` schreibt `earthx:refs` je Zeitschritt; abgelehnt mit `UnsupportedLayout`: Filter außer shuffle/zlib, übersprungener Filter an einem Chunk, `scale_factor`/`add_offset`, ungleichmäßige Achsen, CRS ohne exakt passenden EPSG-Code, Kalender außer Standard, Zeit nicht in Tagen/Stunden/Minuten/Sekunden, Chunk über 8 MiB, schwaches oder fehlendes ETag, Quelle ohne `206` |
| `readers/reference_store.py` | `parse_references` (jedes Feld geprüft), `ReferenceStore` (Metadaten von `zarr` selbst im Speicher gebaut, je Chunk ein `Range` mit `If-Match`), `SourceChanged` bei `412`, `ReferenceMismatch` bei fehlendem `206` oder falscher Länge, Chunk-Cache je Prozess (Größe 0 außer im `tiler`) |
| `readers/zarr_reader.py` | `reference_asset`; `ZarrAsset.refs`; der Leser wählt den Store, nimmt `time_offset` und dreht die Zeilen um, wo sie von Süd nach Nord liegen; `InvalidReferences` |
| `readers/failures.py`, `api/processing_route.py`, `frontend/src/jobState.ts` | `source_changed` (502, Titel aus `adr/0029`); nicht in `RETRYABLE`, nicht in `FAILS_AGAIN` |
| `api/tiler.py` | Chunk-Cache 64 MiB; `SourceChanged` und `ReferenceMismatch` als `502` ohne Adresse |
| `catalog/registry.py` | `DataFormat.NETCDF_REFS = "netcdf-refs"`; verlangt `item_holding: materialized` |
| `access/resolve.py` | Leser-Art `zarr` für `netcdf-refs`; `ResolvedAsset.refs` aus `earthx:refs` des Assets; ohne Verweise `MalformedItem` |
| `processing/recipe.py`, `processing/source.py`, `api/intake.py` | `refs` reisen im Rezept mit (Teil des Hashes, bei allen übrigen Assets weggelassen: alte Hashes bleiben); Band heißt wie das Asset; Fassung der Eingabe = ETag der Verweise, ohne `HEAD` |
| `frontend/src/processingOrder.ts`, `types.ts` | Format `netcdf-refs`: ein Band je Asset mit `earthx:refs`, Typ aus `raster:bands` |
| Lock-Datei, `.importlinter` | `h5py` 3.16.0; Vertrag `h5py-only-in-discovery` |
| `scripts/m5-11-meteoswiss/probe.py`, `docker-compose.yml` | Dienst `meteoswiss-probe` (Profil `measure`), `--assets`, `--layout`, `--grids`, `--limit` |

### 10.2 Abweichungen vom Plan (Auslegungen, gelten, wenn du nicht widersprichst)

- **A9:** Die Form von `earthx:refs` ist gegenüber §4.1 vereinfacht. `shape` ist das Gitter (Zeilen, Spalten), `chunks` die Form eines Chunks (Zeit, Zeilen, Spalten). `y_ascending` entfällt, weil die Richtung im Vorzeichen von `transform[4]` steht; zwei Angaben könnten sich widersprechen. Die Filter heißen nur `shuffle` und `zlib`, ohne Stufe, weil das Entpacken sie nicht braucht.
- **A10:** Der Leser bleibt die Art `zarr` (derselbe `ZarrReader`, `adr/0029` §8a.1); es gibt keine eigene Leser-Art. Was ihn umschaltet, sind die Verweise am Asset.
- **A11:** Die Zeitachse liest nur „Tage/Stunden/Minuten/Sekunden seit“ im Standardkalender, also genau den Takt dieser Aufgabe. Monatswerte („months since“) kommen erst mit einer eigenen Aufgabe.
- **A12:** `ReferenceMismatch` (Quelle überhört `Range` oder schneidet ab) bekommt keine eigene Fehlerart. Ein Job endet dann wie bei einem unbekannten Fehler; die Kachel ist `502`.
- **A13:** Der Download der Originale (F5) und alles Datensatzbezogene kommen mit PR 2. In PR 1 gilt `netcdf-refs` im Frontend wie Zarr als „keine einzelne Datei“ (`download.ts`), also nur der Zuschnitt.

### 10.3 Lizenzen der neuen Abhängigkeit (Bedingung aus `adr/0029` F1)

| Teil | Lizenz | Beleg |
|---|---|---|
| `h5py` 3.16.0 | BSD-3-Clause | `License-Expression` in den Paketmetadaten; Text `LICENSE` im Wheel |
| HDF5 2.0.0 (`libhdf5`, `libhdf5_hl`, im Wheel) | HDF5-Lizenz, BSD-artig (Weitergabe mit Hinweis, keine Werbung mit den Namen) | `licenses/hdf5.txt` im Wheel |
| `libaec` 1.x mit `libsz` (im Wheel) | BSD-2-Clause | Projekt `libaec` [S]; **der Text liegt dem Wheel nicht bei** |
| übrige Texte im Wheel (LZF-Filter, PyTables-Teile, `stdint`, Python) | BSD- bzw. PSF-artig | `licenses/` im Wheel |

- Alle sind mit AGPL-3.0-or-later vereinbar [A].
- **Befund und Lösung (Otto, 17.11.2026: in diesem PR, keine Folgeaufgabe):** BSD-2-Clause verlangt den Text bei jeder Weitergabe als Binärdatei; das Wheel von `h5py` bringt `libaec` 1.1.4 (`libaec-*.so.0.1.4`) ohne ihn mit. Das Wheel von `rasterio` tut dasselbe schon länger (`libaec-*.so.0.1.7`). Der Text von `LICENSE.txt` beim Tag `v1.1.4` des Projekts (DKRZ) liegt jetzt unverändert in `backend/licenses/libaec-LICENSE.txt`; das Image kopiert `backend/licenses/` nach `/app/licenses/` (auch das Runner-Image, `FROM app`), `backend/THIRD_PARTY_NOTICES.md` nennt die Datei, `backend/tests/test_bundled_licenses.py` hält Datei, Wheels und `COPY` zusammen. Den Bau des Images prüft Ottos `docker compose run --build`; die Session hat keinen Docker-Dienst.
- `kerchunk`, `virtualizarr`, `fsspec`-HTTP und `obstore` sind nicht dazugekommen. Die Lock-Datei bekommt nur `h5py` (NumPy ist schon da).

### 10.4 Was Otto jetzt lokal ausführen kann

§7 Schritte 0 und 1: Branch holen, dann `meteoswiss-probe --assets` und `--layout`. Die Ausgabe kommt in diesen PR, sie entscheidet §5.7 (`float64`) und die Zeitgrenzen der Items für PR 2.

### 10.5 Antworten von Otto zu PR 1 (17.11.2026)

1. Umfang (rund 1 300 Zeilen ohne Tests): hingenommen.
2. `libaec`: Lizenztext in diesem PR ins Image bzw. zu den mitgelieferten Lizenzen, keine Folgeaufgabe → §10.3.
3. Cache nach einem Austausch der Datei (gecachte Chunks im Stand des Items, übrige `502` bis zum Neuverweis): bestätigt.
4. A9–A13 gelten.
5. Attribution bearbeiteter Daten in PR 2: „Source: MeteoSwiss (modified)“ → §9.3.
6. Otto lässt `meteoswiss-probe --assets` und `--layout` laufen und hängt die Ausgabe an den PR; ausgewertet wird sie in PR 2 (§5.7 `float64`, Zeitgrenzen der Items).

### 10.6 Erster Lauf der Probe (Otto, 17.11.2026) und Anpassung

- **Befund:** 78 Items, das größte mit 3257 Assets. Kein Name passte auf das Suchmuster; gezeigt waren nur die zehn häufigsten Muster des größten Items (Rekorde und Anomalien wie `trecabsm`, `ranomm`). „daily annual files to read 0“.
- **Prüfung, ob sich etwas geändert hat** (ohne Abruf der Quelle, `adr/0002`): Die Doku von MeteoSchweiz (`c3-ground-based-climate-data`, letzte Änderung 22.09.2026) sagt weiter, dass das Item „CH archive“ je Produkt Jahresdateien mit Tageswerten bündelt (bis 200 MB) und die vollständig konsolidierten Daten trägt [P\*]. Ein Hinweis auf geänderte Namen oder eine andere Ablage findet sich dort nicht; ein Namensmuster nennt die Doku nicht.
- **Wahrscheinliche Ursache [A]:** `adr/0029` §3.1 hält die Zeitstempel nur als `<start>_<ende>` fest. Das Suchmuster nahm 6–8 Ziffern an; schreibt die Quelle mehr (z. B. `JJJJMMTThhmm`), passt kein Name. Belegt ist das erst mit dem nächsten Lauf.
- **Anpassung der Probe:**
  - `--assets` gibt jetzt alle Namensmuster über alle Items aus, mit Anzahl, Zahl der Items und Jahren, Ziffern als `#`.
  - Das Suchmuster nimmt Zeitstempel von 4 bis 14 Ziffern und beliebige Namensteile zwischen Gitter und Zeitstempel.
  - Der Takt kommt aus dem letzten Buchstaben der Größe (`…D`, `…M`, `…Y`), die Dauer einer Datei aus den beiden Zeitstempeln (Jahr, Monat, Tag).
  - `--layout` liest die Größen mit `…d` und einer Datei je Jahr bis zum Vorjahr.
- **Bevor PR 2 gebaut wird:** Zeigt auch der neue Lauf keine Jahresdateien mit Tageswerten im Archiv, ist das ein Befund für Otto (`adr/0029` F5 setzt sie voraus), keine Annahme.

### 10.7 Zweiter Lauf der Probe (Otto, 17.11.2026) und Korrektur des Suchmusters

- **Befund:** 78 Items, 50 Namensmuster. Die Jahresdateien mit Tageswerten liegen im Archiv, z. B. `ogd-surface-derived-grid-archive.tabsd_ch##r.swiss.lv##_##############_##############.nc` × 65 (1961–2025), `…rhiresd_ch##h…` × 65 (1961–2025), `tmaxd`, `tmind`, `sreld` je 55 (1971–2025). Das Suchmuster fand trotzdem nichts: Es verlangte `_` vor der Größe, die Quelle schreibt `-archive.`.
- **Korrektur:** Gelesen werden nur Namen der Form `ogd-surface-derived-grid-archive.<größe>_<ch01r|ch01h>.swiss.lv95_<14 Ziffern>_<14 Ziffern>.nc`. Damit fallen weg: alles außerhalb des Archivs, also `-last` und die vorläufigen Tagesdateien (`rprelimd`, 2026), sowie andere Gitter. `--layout` liest daraus die Größen mit Tageswerten (`…d`), eine Datei je Jahr, bis zum Vorjahr (Otto, 17.11.2026; `adr/0029` F5).
- **Endstempel:** Ob er auf den 31.12. oder auf den 1.1. des Folgejahres fällt, zeigt die maskierte Ausgabe nicht. Beide Formen gelten als „eine Datei je Jahr“.
- **Test:** `test_m5_11_meteoswiss_probe.py` mit genau diesen Mustern, die maskierten Ziffern ausgefüllt. Er war rot gegen das alte Suchmuster und ist grün gegen das neue.
- **Für PR 2:** Diese Namensform gilt auch für den Materialisierer (§5.1). Größen und Beginn bestätigt: `TabsD`, `RhiresD` ab 1961, `TmaxD`, `TminD`, `SrelD` ab 1971 (`adr/0029` §8a.2).

### 10.8 Dritter Lauf der Probe (Otto, 18.11.2026): grid_mapping ohne exakten EPSG-Code

**Befund:** Das Suchmuster passt, 295 Jahresdateien mit Tageswerten wurden gelesen. Alle 295 wurden mit „the grid_mapping of the file matches no EPSG code exactly“ abgelehnt (`rhiresd ch01h` × 65, `tabsd` × 65, `sreld`, `tmaxd`, `tmind` je × 55). Damit fehlen noch Datentyp (`float64`?) und Zeitgrenzen der Tage.

**Was die Prüfung verlangt** (`discovery/netcdf_refs.py`, `_crs`):
- `pyproj` bildet aus den CF-Attributen ein CRS und schlägt einen EPSG-Code vor.
- Angenommen wird der Code nur, wenn Ellipsoid, Projektionsmethode und jeder Projektionsparameter des Vorschlags gleich denen der Datei sind.
- Fehlt in den CF-Attributen das Ellipsoid (`semi_major_axis`, `inverse_flattening`), nimmt `pyproj` WGS 84 an. Dann scheitert die Prüfung am Ellipsoid, obwohl Methode und alle Parameter von LV95 stimmen. Im Test nachgestellt: Ein mitgeliefertes `esri_pe_string` erkennt `pyproj` als EPSG:2056 mit 100 %.
- Ob das die Ursache in den echten Dateien ist, zeigt erst der vierte Lauf [A].

**Erweiterung der Probe (für den vierten Lauf):**
- **Jedes abweichende grid_mapping einmal**, mit der Zahl der Dateien je Größe:
  - alle Attribute;
  - die Übereinstimmungen, die `pyproj` meldet (Code und Prozent);
  - Name, Methode, jeder Projektionsparameter (gleich oder abweichend, mit beiden Werten), Ellipsoid, Datum, `towgs84` und Achsen, je für die Datei und für EPSG:2056.
- **Das gleiche für ein mitgeliefertes WKT** (`crs_wkt`, `spatial_ref`, `esri_pe_string`).
- **Der Rest des Aufbaus wird trotzdem gelesen** (Typ, Chunks, Füllwert, Zeitachse und Zeitgrenzen). Dafür hat `reference_file` den Schalter `strict_crs=False`, nur für die Messung; die Plattform bleibt streng (Vorgabe `True`).
- Ausgabe ohne Adressen, IDs und ETags.
- Außerdem gilt eine Datei mit zwei gleichen Zeitstempeln jetzt als „one time step“, nicht mehr als „file of one day“ (Jahreswerte wie `tabsy`).
- Einheiten von Parametern vergleicht die Prüfung jetzt ohne Groß- und Kleinschreibung („Degree“ = „degree“).

**F10 — Wie wird ein grid_mapping ohne exakten EPSG-Code behandelt?** (Entscheidung Otto; die Empfehlung bestätige ich nach dem vierten Lauf an den echten Abweichungen)

1. **EPSG:2056 annehmen, wenn nur Datum bzw. Ellipsoid fehlen oder abweichen** **(Empfehlung)**
   - Annehmen, wenn Projektionsmethode und alle Projektionsparameter mit EPSG:2056 übereinstimmen und die Abweichung nur das Datum betrifft: fehlendes oder anderes Ellipsoid in den CF-Attributen, fehlendes oder anderes `towgs84`, anderer Name.
   - Liefert die Datei ein WKT (`esri_pe_string`, `crs_wkt`), muss `pyproj` es als EPSG:2056 erkennen.
   - Die Koordinaten sind dann LV95-Werte (Ost/Nord in Metern). Die Lage nach WGS 84 rechnet PROJ wie bei swissALTI3D mit der Transformation von EPSG:2056; die genauere Verortung über CHENyx06 kommt mit M5-33 für beide.
   - Das Item trägt `proj:code: EPSG:2056`; in `readers` ändert sich nichts.
   - In PR 2 prüft der Materialisierer zusätzlich gegen den Code, den der Registry-Eintrag nennt. Weicht eine Datei ab, scheitert der Lauf.
   - Abgegrenzt: Weicht ein Projektionsparameter ab (Ursprung, Azimut, Maßstab, falscher Ost- oder Nordwert), bleibt die Datei abgelehnt.
2. **Das CRS der Datei als WKT übernehmen**
   - Das Item trägt dann `proj:wkt2` statt `proj:code`. `readers` liest heute nur `proj:code`/`proj:epsg`; dazu kommt Code in `access` und im Rezept.
   - Fehlt in der Datei das Datum (nur CF-Parameter), kennt PROJ keine Verschiebung nach WGS 84. Die Lage wiche dann um die Datumsverschiebung von CH1903+ ab, je nach Ort in der Größenordnung von 100 m [A, nicht gemessen].
   - Taugt nur, wenn die Datei ein vollständiges WKT mitliefert.
3. **Den Code fest im Registry-Eintrag nennen und in `discovery` nur die Projektionsparameter prüfen**
   - Wie 1, aber nicht automatisch erkannt: Der Eintrag sagt EPSG:2056, die Datei muss nur in Methode und Parametern dazu passen.
   - Strenger gegen eine falsche Erkennung, dafür eine Angabe mehr je Datensatz.

Bis zur Entscheidung bleibt die Plattform streng. Nur die Probe liest über die Abweichung hinweg.

### 10.9 Vierter Lauf der Probe (Otto, 18.11.2026) und Abschluss von PR 1

**Befund** (Ausgabe im PR):

| Was | Ergebnis |
|---|---|
| CRS | alle 295 Dateien EPSG:2056, keine Ablehnung |
| Datentyp | überall `<f4` (Float32) |
| Gitter `ch01r` | 240 × 370 Zellen zu 1 km: `TabsD`, `TmaxD`, `TminD`, `SrelD` |
| Gitter `ch01h` | 265 × 370 Zellen zu 1 km: `RhiresD` |
| Chunk | ein Tag, ohne Filter |
| Füllwert | −999.99 |
| Zeit | Schritte um 00:00, keine `time_bnds` |
| `units` der Temperaturen | „degree“ |
| `SrelD` | ein Jahr mit Lücken |

**Ursache der Ablehnung im dritten Lauf (F10), bestätigt:**
- Zwischen drittem und viertem Lauf hat sich an der Prüfung der Plattform (`_crs`, `_same_projection`) nur eines geändert: Die Einheiten der Projektionsparameter werden ohne Groß- und Kleinschreibung verglichen (§10.8).
- Der Mechanismus ist nachgestellt: Trägt das grid_mapping ein ESRI-WKT in `crs_wkt` oder `spatial_ref`, baut `pyproj.CRS.from_cf` das CRS daraus, mit der Einheit „Degree“; EPSG:2056 hat „degree“.
- `test_lv95_written_as_esri_wkt_is_epsg_2056` ist mit dem alten Vergleich rot und mit dem neuen grün.
- **F10 ist damit erledigt; die Plattform bleibt streng.** Methode, alle Parameter und das Ellipsoid müssen weiter übereinstimmen; `strict_crs=False` bleibt der Probe vorbehalten.

**Wiedervorlage `float64` (M5-Plan §2 Punkt 9): geschlossen, kein Anlass.** Alle Dateien sind Float32. Das Panel bietet wie bei jeder Float32-Quelle Float32 an, sobald die Items in PR 2 `raster:bands[].data_type: float32` tragen (§5.7).

**Für PR 2 festgehalten (Otto, 18.11.2026):**
- **Einheit:** Die Temperaturen tragen in den Dateien `units: degree`; die Plattform führt sie als `°C` (`band_units` und `raster:bands[].unit`). `SrelD` in `%`, `RhiresD` in `mm` (§5.3).
- **Lücken:** Ein Tag, den eine Datei nicht trägt, ist kein Zeitschritt und kein Item. Ein Tag, dessen Werte Füllwerte sind, liest sich als nodata. Beides ist kein Fehler (`test_missing_days_are_missing_time_steps_not_a_failure`).
- **Zeitraum je Tag:** Die Dateien tragen nur Zeitpunkte um 00:00 und keine `time_bnds`. Das Item soll den Zeitraum des Tages tragen (`start_datetime`, `end_datetime`), belegt aus der Dokumentation von MeteoSchweiz (z. B. Niederschlag 06–06 UTC).

**Offen, Zugang fehlt — die Tagesgrenzen sind noch nicht belegt:**
- Die Übersicht `opendatadocs.meteoswiss.ch/c-climate-data/c3-ground-based-climate-data` nennt keine Tagesgrenzen. Sie verweist auf die Produktdokumentationen:
  - `ProdDoc_RhiresD.pdf`: https://www.meteoswiss.admin.ch/dam/jcr:4f51f0f1-0fe3-48b5-9de0-15666327e63c/ProdDoc_RhiresD.pdf
  - `ProdDoc_TabsD.pdf` (Mittel, Minimum, Maximum): https://www.meteoswiss.admin.ch/dam/jcr:818a4d17-cb0c-4e8b-92c6-1a1bdf5348b7/ProdDoc_TabsD.pdf
  - `ProdDoc_SrelD.pdf`: https://www.meteoswiss.admin.ch/dam/jcr:981891db-30d1-47cc-a2e1-50c270bdaf22/ProdDoc_SrelD.pdf
- Der Host `www.meteoswiss.admin.ch` ist aus der Cloud-Session nicht erreichbar (DNS-Auflösung scheitert, 18.11.2026). Die Grenzen sind deshalb **nicht** belegt und nicht angenommen. Die frühere Vermutung (§2.2, Niederschlag 06–06 UTC) bleibt eine Vermutung [S].
- Das betrifft erst PR 2, weil die Items dort entstehen. Wege: Otto gibt den Host für die Umgebung frei, Otto legt die drei PDFs oder die betreffenden Sätze in den PR, oder die Session von PR 2 liest sie dort.

---

## 11. Umsetzung PR 2 (18.11.2026)

### 11.1 Tagesgrenzen (belegt, Otto 18.11.2026)

| Größe | Tag D | Quelle |
|---|---|---|
| `RhiresD` | 06:00 UTC Tag D bis 06:00 UTC Tag D+1 | `ProdDoc_RhiresD` |
| `TabsD`, `TminD`, `TmaxD` | 00:00–24:00 UTC | `ProdDoc_TabsD` |
| `SrelD` | Mitternacht bis Mitternacht, in UTC | `ProdDoc_SrelD`; opendatadocs: alle Referenzzeitstempel in UTC |

Die Dateien stempeln jeden Tag um 00:00 UTC des Tages D (§10.9). Das Item des Tages D trägt danach `start_datetime` = Beginn des Tages (`RhiresD` 06:00 UTC, sonst 00:00 UTC), `end_datetime` = letzte Sekunde vor dem nächsten Tag (A17), `datetime` = `start_datetime`. Die Vermutung aus §2.2 ist damit belegt; §10.9 „Tagesgrenzen offen“ ist erledigt.

### 11.2 Was gebaut ist

| Stelle | Inhalt |
|---|---|
| `discovery/meteoswiss_grid.py` | Materialisierer: bedingter Abruf des Archiv-Items, Auswahl der Jahresdateien (nur `…-archive.<größe>_<ch01r\|ch01h>.swiss.lv95_<14 Ziffern>_<14 Ziffern>.nc`, ein Jahr je Datei, bis zum Ende von `temporal_extent` und höchstens bis zum Vorjahr des Laufs), Verweise je Datei mit `reference_file`, ein Item je Tag, ein Asset je Größe mit `earthx:refs` und `raster:bands` (`float32`, `nodata: nan`, Einheit aus `band_units`), `updated` = jüngstes Last-Modified, Geometrie = Rahmen des Gitters (verdichtet nach WGS 84) |
| `discovery/materialize.py` | `MATERIALIZE_SPECS`: die Adaptertabelle mit dem Materialisierer von `discovery` (A15) |
| `catalog/registry.py`, `adapters/spec.py` | `AdapterKind.METEOSWISS_GRID`, `CoverageProvider.FIXED_GRID`; ein materialisierter Eintrag darf `fixed-grid` wählen, wenn er eine Zeitreihe über einen geschlossenen Zeitraum ist |
| `catalog/fixed_grid_coverage.py`, `api/coverage_route.py` | Coverage „festes Gitter“ (§5.4): Fläche = `spatial_extent` beschnitten auf Box bzw. Fläche, Zahl der Tage im Fenster, Histogramm je Monat; ohne Datenbank und ohne Abruf (A18) |
| `api/intake.py` | Ein Asset mit `earthx:refs` ist ein Band, benannt wie das Asset (A22) |
| `api/measure_tiles.py` | Ein Tag mit Verweisen wird gemessen: Zarr-Leser der Item-Kachel, Abrufe aus den Logzeilen von `gateway`, Chunk-Cache des `tiler` (A21) |
| `catalog/datasets/meteoswiss-daily-1km.yaml`, `…-precip-1km.yaml` | die beiden Einträge (§5.3), Checkliste vollständig |
| `catalog/glossary.yaml` | sechs Gruppen (A20) |
| Frontend `api.ts` | `v=<updated>` an Kachel-, TileJSON- und Statistik-URLs von Items mit `earthx:refs` (F3) |
| Frontend `download.ts` | Originale auch für `netcdf-refs`: die Jahresdatei, je Datei ein Link (F5, A23) |
| `tests_live/test_meteoswiss_grid_smoke.py` | Live-Smoke beider Einträge (§5.10) |
| Bewertungs-Set | `MCH` = `meteoswiss-daily-1km`, `MCHP` = `meteoswiss-daily-precip-1km` (F7) |

### 11.3 Onboarding-Checkliste (`projektuebersicht.md` §5)

Alle Punkte sind belegt, wie bei den übrigen Einträgen durch die Tests über alle Einträge der Registry: Coverage (Punkt 2: `fixed-grid` steht in `IMPLEMENTED_PROVIDERS`), Zitat (3), Lizenz und Attribution (4, Einstufung durch Otto, §11.5 G1), Zugang ohne Token (6), Darstellung (8: `TabsD` mit `rdbu_r` −20…30 °C, `RhiresD` mit `blues` 0…50 mm, `nearest`), Processing (9: Kette v2 mit `reproject` aus LV95 und Kette v1 Suche → Kachel → Zuschnitt, beide gegen ein synthetisches Archiv), „zuletzt geprüft“ (10: Live-Smoke), Schlagworte deutsch und englisch (11) mit Glossar.

### 11.4 Auslegungen (gelten, wenn du nicht widersprichst)

- **A14:** Die Größen eines Eintrags sind die Schlüssel von `band_units` (`TabsD` …), nicht `source.asset_keys`: Diese Regeln ordnen Assets nach Medientyp und gsd zu und gelten nur für den STAC-Adapter (`check_adapter_specs` lehnt sie sonst ab). Gitter und Tagesbeginn je Größe stehen im Code (`PRODUCTS`), weil sie Eigenschaften des Produkts von MeteoSchweiz sind; ein Eintrag mit Größen zweier Gitter scheitert.
- **A15:** Der Materialisierer liegt in `discovery`, weil nur dort `h5py` laden darf. `ADAPTER_SPECS` führt `meteoswiss-grid` ohne `materialize`; `discovery.materialize` nimmt `MATERIALIZE_SPECS`, das sonst gleich ist (Test).
- **A16:** Fassung eines Laufs = ETag des Archiv-Items, Auswahl des Eintrags (Größen, erstes und letztes Jahr) und Hash über Name, Adresse, `file:checksum` und `updated` der gewählten Dateien. `304` ist „unverändert“ nach einem Abruf; bedingt gefragt wird nur bei gleicher Auswahl, damit ein verlängerter Zeitraum oder eine neue Größe geladen wird, obwohl sich das Archiv nicht geändert hat. Ein `200` mit gleichem Hash (z. B. eine andere Datei des Archivs geändert) ist ebenfalls „unverändert“, ohne eine Datei zu lesen.
- **A17:** `end_datetime` ist die letzte Sekunde vor dem nächsten Tag (wie BEV `23:59:59`), damit sich zwei Tage nicht in einem Zeitpunkt überlappen; `datetime` = `start_datetime`. Ein Kalendertag trifft damit genau einen Temperaturtag und zwei Niederschlagstage (06–06 UTC).
- **A18:** Die Coverage „festes Gitter“ zählt die Tage des Fensters im Zeitraum des Eintrags. Ein Tag, den die Quelle in keiner Datei führt, wird mitgezählt; die Items zeigen die Lücke. Gemessen fehlen Tage nur bei `SrelD` in einem Jahr, und `TabsD` trägt jeden Tag des Eintrags `meteoswiss-daily-1km`. Eine Flächenantwort rät nie zu Footprints (`footprints_advised` falsch).
- **A19:** `spatial_extent` ist bis zum ersten Lauf **vorläufig** (eine Box um jedes Gitter innerhalb 2 450 000–2 880 000 E, 1 020 000–1 330 000 N). Der Lauf scheitert, wenn das Gitter darüber hinausreicht. Nach Ottos Lauf ersetzt die Ausdehnung der Items (Schritt 4 in §11.6) den Wert in diesem PR; sie ist dann auch die Fläche der Coverage.
- **A20:** Glossar: `MeteoSchweiz/MeteoSwiss/MétéoSuisse`, `Klimagitter/climate grid`, `Niederschlag/precipitation`, `Lufttemperatur/air temperature`, `Sonnenscheindauer/sunshine duration` und `Wettervorhersage/weather forecast`. Die letzte Gruppe hält die Negativfrage Q50 („hourly weather forecast“) leer: Ohne sie blieb unter `Joining.KNOWN` nur das bekannte Wort „weather“ (aus der Kategorie „Weather and climate“) und traf beide Einträge; die Negativfragen fielen auf 3 von 5. Die Schlagworte „weather“/„Wetter“ stehen deshalb nicht in den Einträgen. Messung mit Postgres (`tests/integration/test_search_evaluation.py`): de Recall@5 0,842, MRR@10 0,816; en 1,000/1,000; Filterfragen 5/5, Negativfragen 4/5 (Q48 trifft wie vorher das DEM).
- **A21:** `measure-tiles` misst einen Tag mit Verweisen über den Leser der Item-Kachel (`ZarrReader`), zählt Abrufe und Bytes aus den Logzeilen von `gateway` (GDAL sieht diese Abrufe nicht) und hält den Chunk-Cache des `tiler`; „warm“ ist damit die zweite Kachel derselben Ansicht. Mehrere Items mit Verweisen in einer Kachel werden nicht gemessen; einen Zarr-Speicher misst es weiter nicht.
- **A22:** Befund aus Checklistenpunkt 9: `api/intake.band_sources` ließ nur GeoTIFF-Assets als Bänder zu, ein Auftrag auf ein NetCDF-Asset scheiterte mit 422. Jetzt ist jedes Asset mit `earthx:refs` ein Band, benannt wie das Asset, wie im Frontend seit PR 1 (`processingOrder.ts`).
- **A23:** „Download originals“ eines Tages verlinkt die Jahresdatei der Quelle (F5). Mehrere Tage eines Jahres teilen sie: Der Dialog lädt und nennt jede Datei einmal, beim ersten ihrer Tage; ein Tag, dessen Dateien alle schon dabei sind, entfällt (`scenesOf`, Linkliste, Zusammenfassung). Sonst lüde eine Woche dieselbe Datei von rund 130 MB siebenmal, was die Bedingungen („high-frequency downloading of the same content“) untersagen.
- **Bekannte Grenze:** `v` kennt nur Items, die die Seite in dieser Sitzung über Suche oder Abruf geholt hat. Eine gespeicherte Ebene behält die Kachel-URL, mit der sie gespeichert wurde (mit `v`); neu gebaute URLs ohne vorherigen Abruf des Items tragen keines.

### 11.5 Fragen an Otto

**G1 — Lizenzangabe (F8).** Die Seite der Nutzungsbedingungen (`opendatadocs.meteoswiss.ch/general/terms-of-use`, gelesen 18.11.2026) sagt wörtlich: „The 'Open Data' of MeteoSwiss are published accordingly under the Creative Commons Licence CC BY 4.0.“ Der Name „opendata.swiss BY“ kommt dort nicht vor. Daneben stehen Pflichten, die über CC BY hinausgehen: Quellenangabe ohne Anschein einer Unterstützung, Verbot übermäßiger Nutzung, kein Gewähr.
1. Wie F8: `spdx_id: null`, Name „Terms of use of MeteoSwiss open data“, Bedingungen als `terms.notice` (so im PR)
2. `spdx_id: CC-BY-4.0` mit Name und URL von CC BY 4.0; die Nutzungsbedingungen bleiben als `terms` mit derselben `notice` **(Empfehlung: die Seite nennt die Lizenz selbst, und eine SPDX-Kennung macht sie maschinenlesbar; die Zusatzpflichten gehen dabei nicht verloren)**
3. Erst nach eigener Prüfung

**G2 — Wortlaut** der Attribution („Source: MeteoSwiss“, bearbeitet „Source: MeteoSwiss (modified)“) und der `notice` in beiden YAML-Dateien: bestätigst du im PR (Auftrag Otto). Die `notice` sind Sätze der Bedingungen im Wortlaut.

### 11.5a Antworten von Otto (18.11.2026)

| Frage | Antwort |
|---|---|
| G1 | 2: `spdx_id: CC-BY-4.0` (Name und URL von CC BY 4.0), die Nutzungsbedingungen von MeteoSchweiz als `terms` mit unveränderter `notice`, auch dem Satz, dass die Quellenangabe nicht wie eine Unterstützung durch MeteoSchweiz aussehen darf. Die Lizenzangabe aus F8 (§9.2, §9.3: Nutzungsbedingungen statt CC BY 4.0) war ein Irrtum und ist damit korrigiert |
| G2 | Attribution „Source: MeteoSwiss“, bearbeitet „Source: MeteoSwiss (modified)“: bestätigt |

### 11.6 Was Otto lokal ausführt (PowerShell, aus der Repo-Wurzel)

Wie bei M5-09: dieselbe Zeile in PowerShell und bash. `materialize` startet `catalog-load` selbst. Der Host `data.geo.admin.ch` hat 6 Verbindungen und 1 s Abstand für `materialize`.

**Schritt 0 — Branch holen:**

```powershell
git fetch origin claude/tender-ramanujan-in3i2r
```

```powershell
git checkout claude/tender-ramanujan-in3i2r
```

**Schritt 1 — Items laden** (230 bzw. 65 Jahresdateien, je 5–8 Abrufe; mit 1 s Abstand rund 30 bzw. 10 min; rund 23 700 Items je Datensatz):

```powershell
docker compose run --build --rm materialize meteoswiss-daily-1km
```

```powershell
docker compose run --rm materialize meteoswiss-daily-precip-1km
```

Erwartet je eine Zeile `loaded (source version …); N items written, 0 deleted; L listed, 0 missing, W withheld, 0 unknown at the source`. `withheld` zählt Jahresdateien außerhalb des Zeitraums (2026 gibt es im Archiv noch nicht).

**Schritt 2 — zweiter Lauf ohne Änderung** (erwartet `unchanged`, ein bedingter Abruf):

```powershell
docker compose run --rm materialize meteoswiss-daily-1km
```

**Schritt 3 — Zahl, Zeitraum und Ausdehnung der Items** (die Ausdehnung ersetzt in diesem PR die vorläufige `spatial_extent`, A19):

```powershell
"select collection, count(*), min(datetime), max(end_datetime), st_extent(geometry) from pgstac.items where collection like 'meteoswiss-%' group by collection;" | docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At'
```

Erwartet: `meteoswiss-daily-1km` von `1961-01-01 00:00` bis `2025-12-31 23:59:59`, `meteoswiss-daily-precip-1km` von `1961-01-01 06:00` bis `2026-01-01 05:59:59` (UTC).

**Schritt 4 — Prüfpunkt Mosaik-Zoom (§5.6, `adr/0032` Backlog 29)**, ein Sommertag je Datensatz, z0–z12:

```powershell
docker compose run --build --rm measure-tiles meteoswiss-daily-1km --bbox 6.0,46.0,10.4,47.7 --datetime 2024-07-01 --zooms 0-12
```

```powershell
docker compose run --rm measure-tiles meteoswiss-daily-precip-1km --bbox 6.0,46.0,10.4,47.7 --datetime 2024-07-01 --zooms 0-12
```

Erwartet je Stufe 1 Datei, Status `ok`, kalt 1 Abruf von rund 0,36 MB (ein Chunk), warm 0 Abrufe (Chunk-Cache). Die Tabelle nennt weder Box noch Adresse noch Item; sie darf in den PR.

**Schritt 5 — im Browser:** `docker compose up -d --build`, Datensatz wählen, Zeitleiste, von z3 bis z12 zoomen (Crop and merge, angeheftete Ebene, Suchtreffer); Band math `TmaxD - TminD`; ein Job mit Zuschnitt; Coverage mit Zeitfilter; „Download originals“ eines Tages (ein Link auf die Jahresdatei).

**Schritt 6 — Live-Smoke** nach dem Merge auf `main` in GitHub Actions („Live smoke“ → „Run workflow“).

