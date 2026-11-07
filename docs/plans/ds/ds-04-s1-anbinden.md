# DS-04 — Sentinel-1 GRD anbinden: Plan-Schritt

**Status (07.11.2026):** Plan angenommen (Otto, 07.11.2026; Antworten in §9a). Umsetzung von Teil 1 (TPS, DS-04a) im selben Draft-PR nach dem Merge von M5-13. Ersetzt die frühere Datei, die den Text von DS-00 enthielt (`adr/0030` §9, Nebenbefund).
**Aufgabe:** DS-04 aus `docs/plans/m5/m5-discovery-und-suche.md` §6.2. **Stufe B** (`adr/0030` §11; vorher A laut DS-00). Der Plan darf sofort entstehen; die Umsetzung beginnt erst, wenn M5-13 (YAML-Lader) gemergt ist. Dann wird `main` geholt, und der Eintrag entsteht als YAML (M5-Plan §6.3).
**Modell:** Opus, Effort hoch.
**Grundlagen:** `adr/0018` Teil A (§3.1, §4, F1–F3) mit Nachtrag M5-12 (§9.4); `adr/0030` §5.2, §8, §9, §11; `adr/0021` (Suchfilter); `adr/0022` und M5-07 (`data_region`); `adr/0024` (`legal_status`); `adr/0025` §7 (YAML unter `backend/catalog/`); `adr/0027` §6.1 (`access.account`); `adr/0014` §3.1, §4.6, §6.3 (Fassung, Bitgleichheit); `architekturplan.md` 3.1, 5.1, 6.4, 7.3; `projektuebersicht.md` §5 (Checkliste); `KLAERUNGEN.md` B8–B12.

Belegstufen wie in `adr/0018`: **M** in dieser Sitzung gemessen (07.11.2026, nur Metadaten mit `curl` über den Proxy der Sitzung, ein synthetischer Datensatz im Kratzverzeichnis), **P** am Quelltext gelesen (Stand `main` d6c0e39), **A** eigene Ableitung. Item-IDs, `href` und Flächen stehen nicht in diesem Dokument.

---

## 1. Ziel

Sentinel-1 GRD von Earth Search v1 (`sentinel-1-grd`) wird ein föderierter Level-1-Datensatz, weltweit, ohne Konto (`adr/0018` Teil A, Otto 26.10.2026):

1. **Eine Lage überall:** Georeferenz aus den GCPs per Thin-Plate-Spline (TPS) in Kachel, Zuschnitt, Job und lokalem Runner, als allgemeine Reader-Fähigkeit, die die Registry je Datensatz einschaltet (`adr/0018` F1).
2. **Zwei Hinweise:** „Approximate geolocation“ und „Uncalibrated (DN)“, kurz mit Tooltip, dazu in Rezept, Provenienz und Download-Text (`adr/0018` F2).
3. **Operatoren nach `adr/0018` §4.4** (F3): Zuschnitt, Band-Math innerhalb der Szene, Normalisierung, Reprojektion, Mosaik je Durchgang. Keine festen Schwellen, keine Index-Knöpfe, kein Vergleich über Bahnen.
4. **Originale** als Link-Liste direkt vom Bucket: Abbildung `s3://sentinel-s1-l1c/` → `https://sentinel-s1-l1c.s3.eu-central-1.amazonaws.com/` (`adr/0018` §4.3).
5. **Fassung je Asset** über die CRC64NVME-Prüfsumme des Buckets, eine `HEAD`-Anfrage je Asset (`adr/0018` §3.1, §4.3).
6. **Live-Smoke** mit eigener Prüfung von Requester Pays (Range-`GET` `206`, `?requestPayment` = `BucketOwner`), weil die STAC-Angabe nicht stimmt.
7. **Onboarding vollständig** nach `projektuebersicht.md` §5, mit Coverage Map, Suchfiltern (DS-02), `data_region` (M5-07), `legal_status` und `access.account` (M5-13).

**Nicht Teil von DS-04:** die Quick processings „VV dB“, „VH dB“ und „Dual-pol RGB“ (Nachtrag M5-12). Sie kommen mit DS-05a (`sar_db`, Capability `sar_backscatter`) und DS-05c (Komposit). Bis dahin hat Sentinel-1 keinen Abschnitt „Quick processing“ (leere Presets, `adr/0030` §8 „Leere Felder“).

---

## 2. Messungen an der Quelle (07.11.2026) [M]

Ergänzt `adr/0018` §3.1 (26.10.2026). Nur Metadaten; keine Datenpixel.

| Was | Ergebnis |
|---|---|
| Collection | `license: proprietary`; Ausdehnung global, ab 2014-10-10; Provider ESA (producer, processor, licensor), AWS (host), Element 84 (processor); `keywords` ESA, Copernicus, Sentinel, C-Band, SAR, GRD; Links `aggregate`, `queryables` |
| `summaries` | kein `gsd`; `sar:pixel_spacing_range` 3,5 / 10 / 25 / 40 m; `platform` nennt nur S1A und S1B, die Items aber auch neuere Plattformen (die Summaries sind veraltet) |
| Items gesamt | rund 3,81 Mio. |
| Filter `query` auf `sar:polarizations` mit `in` | wirkt als „enthält eines davon“: `in ["VH"]` und `eq "VH"` liefern dieselbe Zahl (2,73 Mio.) |
| Anteile nach Polarisation | enthält VV 2,83 Mio., VH 2,73 Mio., HH 0,99 Mio., HV 0,70 Mio.; im Modus IW enthält VV 2,78 Mio., HH 0,33 Mio. |
| `in` auf `sat:orbit_state`, `sar:instrument_mode`; Bereich auf `sat:relative_orbit` | `200`, Zahlen plausibel |
| Asset-Schlüssel eines Items | je Polarisation das Datenband (`vv`, `vh` bzw. `hh`, `hv`), dazu `safe-manifest`, `schema-product-<pol>`, `schema-calibration-<pol>`, `schema-noise-<pol>`, `thumbnail`; alle `s3://sentinel-s1-l1c/…` |
| Kalibrier-XML | **ist ein Asset** (`schema-calibration-<pol>` → `annotation/calibration/calibration-<mode>-<pol>.xml`). Das beantwortet den offenen Punkt aus `adr/0030` §5.2.1 und §12 für DS-05d |
| Item-Felder | u. a. `s1:datatake_id`, `s1:slice_number`, `s1:total_slices`, `sat:relative_orbit`, `sat:orbit_state`, `storage:requester_pays` (weiter `true`) |
| CORS | Earth Search und Bucket antworten `Access-Control-Allow-Origin: *` |

**TPS über `WarpedVRT` [M]:** synthetisches GeoTIFF (200 × 200, `uint16`, Nodata 0, 25 GCPs mit nichtlinearer Lage, EPSG:4326), rasterio 1.5.2, GDAL 3.12.2, rio-tiler 9.4.6:

- `WarpedVRT(src, crs=…)` ohne Option und mit `SRC_METHOD=GCP_POLYNOMIAL` ergeben dasselbe Raster: Die Vorgabe ist das Polynom (bestätigt `adr/0018` §4.1).
- Mit `SRC_METHOD=GCP_TPS` ergibt sich ein anderes Raster (andere Ausdehnung und Größe). rasterio reicht die Option also an GDAL durch; ohne Warnung.

---

## 3. Ausgangslage im Code [P]

- **Registry** (`catalog/registry.py`, `catalog/datasets.py`): vier Einträge als Python; nach M5-13 als YAML unter `backend/catalog/`. Es gibt die Kategorie `radar`, `BrowseMode.PREVIEW_TILES`, `search_filters` mit `range` und `values`, `search_capabilities` (`evaluate`, `aoi_coverage`). Es gibt **kein** Feld für die Georeferenz-Methode, für Hinweise je Datensatz oder für eine Abbildung von `s3://`-Adressen.
- **Adapter** `adapters/earth_search.py` sucht über `query`; `values` wird zu `{"in": [...]}` (Z. 182). `check_adapter_specs` prüft, dass der Adapter `query` kann (`adapters/spec.py`).
- **Kacheln:** `readers/cog.py` `CogReader` ist rio-tilers `Reader`. Für eine Datei mit GCPs baut rio-tiler ein `WarpedVRT` mit `transform.from_gcps` (affin) (`rio_tiler/io/rasterio.py` Z. 99–103). Nimmt der Reader ein schon geöffnetes `dataset` an, öffnet er nichts selbst.
- **Zuschnitt, Job, Export, Mosaik, Reprojektion:** `access/download.py:559`, `access/band_export.py:368`, `processing/warped.py:73/94`, `processing/mosaic.py`, `processing/operators/reproject.py:189` öffnen `WarpedVRT` ohne `SRC_METHOD`; bei GCP-Dateien nimmt GDAL also das Polynom.
- **Adressen:** `readers/cog.py` lässt nur `https` zu, `gateway.inspect_url` weist `s3://` ab. Das Frontend zeigt nur `https`-Adressen auf `asset_hosts` als Original (`frontend/src/download.ts`, `isDirectDownloadHref`).
- **Fassung:** `processing/recipe.py:691` `input_version`: `file:checksum`, sonst ETag aus einem `HEAD` über `gateway`, sonst `updated` (`api/intake.py`, Stufe 7). Die Arten sind `file:checksum`, `etag`, `updated`.
- **Wertmaske** `mask_values` kennt nur feste Werte in physikalischen Einheiten (`lt`, `gt`, `between`, `eq`), keine Perzentile.
- **Marken** im Data catalogue gibt es schon („Prototype“, „Account“, `.badge`).
- **Live-Smokes** in `backend/tests_live/` mit Marker `live_dataset("<id>")`, z. B. `test_earth_search_smoke.py` für Sentinel-2.
- **Veröffentlichung:** jedes `earthx:`-Feld steht in `architekturplan.md` 5.1 (`catalog/collection.py`, Kopf).

---

## 4. Umsetzung

Erst nach dem Merge von M5-13. Namen der Felder in YAML und Python folgen dem, was M5-13 festlegt; unten stehen die Inhalte.

### 4.1 Georeferenz aus GCPs per TPS (allgemein)

- **Registry-Feld** `georeferencing` am Datensatz, ohne Vorgabe (B10): `geotransform` (alle bisherigen Einträge) oder `gcp_tps`. Veröffentlicht als `earthx:georeferencing`. Startprüfung: `gcp_tps` nur bei `format: cog`.
- **Eine Stelle** in `readers` baut die Optionen: `warp_options(config)` gibt für `gcp_tps` `{"SRC_METHOD": "GCP_TPS"}` zurück, sonst nichts. Jede Stelle aus §3, die ein `WarpedVRT` öffnet, nimmt die Optionen von dort. Kein Zweig auf `dataset_id`.
- **Kachel:** Für `gcp_tps` öffnet `CogReader` die Datei und reicht rio-tiler ein `WarpedVRT(src, crs=GCP-CRS, SRC_METHOD=GCP_TPS, src_nodata=…)` als `dataset`; rio-tilers affiner Zweig wird damit nicht mehr betreten. Prüfung, dass `asset_path` (B8) dabei unverändert der einzige Weg zur Datei bleibt.
- **Datei ohne GCPs** bei `gcp_tps` oder GCPs bei `geotransform`: ein benannter Lesefehler (Auslegung A3), nie eine stille Näherung.
- **Rezept:** Die Methode steht je Eingabe im Rezept und damit im Cache-Schlüssel, weil sie die Pixel bestimmt; Job, Worker und lokaler Runner nehmen sie von dort (Auslegung A8).
- **Kosten je Kachel messen** (`adr/0018` F1): z7, z9, z11, z13 an einer echten Szene, affin gegen TPS (Zeit, Bytes). Messung im Kratzverzeichnis der Sitzung wie in `adr/0018` §4.1; Zahlen in den PR, keine IDs.
- **Bitgleichheit:** Job ↔ lokaler Runner bitgleich (`adr/0014` §6.3); Kachel ↔ Job auf der nativen Ebene derselben Lage, Prüfung mit einem synthetischen GCP-COG.

### 4.2 Abbildung `s3://` → `https://` (allgemein)

- **Registry-Feld** `source.asset_href_rewrites`: Liste von Paaren (Präfix alt → Präfix neu), ohne Vorgabe, leer bei allen bisherigen Einträgen. Startprüfung: neues Präfix ist `https://`, sein Host steht in `asset_hosts`.
- **Wo:** im Adapter beim Lesen der Items (Suche und Item-Abruf), einmal, bevor irgendwer die Adressen sieht. Damit sehen `readers`, `intake`, Rezept, Frontend und Originale dieselbe `https`-Adresse; `isDirectDownloadHref` bleibt unverändert.
- Nur `href` wird umgeschrieben; `storage:requester_pays` und die übrigen Felder bleiben, wie die Quelle sie liefert (Auslegung A4).

### 4.3 Fassung per CRC64NVME (allgemein)

- **Registry-Feld** `source.asset_checksum`: `crc64nvme` oder leer, ohne Vorgabe.
- `intake` schickt beim `HEAD` über `gateway` dann `x-amz-checksum-mode: ENABLED` und nimmt `x-amz-checksum-crc64nvme`, wenn `x-amz-checksum-type` `FULL_OBJECT` ist. Neue Art `crc64nvme` in `InputVersion`. Fehlt die Prüfsumme, gilt die bisherige Reihenfolge (ETag, dann `updated`).
- Logs nennen nie den Wert (`adr/0014` §4.7).

### 4.4 Hinweise je Datensatz (allgemein)

- **Registry-Feld** `notices`: Liste aus `code`, `label` (englisch, kurz), `tooltip` (englisch, ein Satz), ohne Vorgabe, leer bei allen bisherigen Einträgen. Veröffentlicht als `earthx:notices`.
- **Sentinel-1:** `approximate_geolocation` („Approximate geolocation“) und `uncalibrated_dn` („Uncalibrated (DN)“). Tooltip-Texte im PR zur Bestätigung durch Otto.
- **Wo sie erscheinen:** als Marke (`.badge`) wie „Prototype“ im Data catalogue, an der Ergebnisgruppe und am Layer; im Rezept (`notices` als Teil der Provenienz, ändert den Cache-Schlüssel nicht) und als Absatz in `ATTRIBUTION.txt` bzw. der Textdatei des Downloads und des Exports.

### 4.5 Registry-Eintrag `sentinel-1-grd` (YAML)

| Feld | Wert | Herkunft |
|---|---|---|
| `dataset_id` | `sentinel-1-grd` (wie die Upstream-Collection, Regel wie bei Sentinel-2) | A |
| `title` | „Sentinel-1 GRD“ | A |
| `keywords` | deutsch und englisch (`adr/0026` F7): sentinel-1, radar, SAR, C-band, backscatter, Rückstreuung, GRD, copernicus | A |
| `category` | `radar` | P |
| `providers` | ESA (producer, processor, licensor), AWS (host), Element 84 (processor), wie die Collection | M |
| `gsd` | 3,5 / 10 / 25 / 40 aus `sar:pixel_spacing_range` (die Collection nennt kein `gsd`; Auslegung A5) | M |
| `doi`, `citation` | keine DOI gefunden; Zitierangabe: Landing Page der Collection bei Earth Search (Checkliste Punkt 3) | A, in der Umsetzung prüfen |
| `data_class`, `format` | Raster-Zeitreihe, COG | M |
| Ausdehnung | global, ab 2014-10-10, Ende offen | M |
| `georeferencing` | `gcp_tps` | F1 `adr/0018` |
| `capabilities` | `roi`, `time_range`, `band_math`, `interpolation`, `reprojection`, `normalization` an; `masking` aus (keine Klassenschicht); `value_masking` nach F4 dieses Plans; `ml_processing`, `quad_pol` aus; `single_coverage_product` aus | `adr/0018` §4.4 |
| `license` | Sentinel Data Legal Notice, Stufe und Attribution wie Sentinel-2 — **Einstufung durch Otto** (F6) | `adr/0003` §11.2 |
| `legal_status`, `access.account` | `cleared`, `none` | `adr/0024`, `adr/0027` |
| `access` | anonym HTTPS, `cors: true`, geprüft am Tag der Umsetzung | M |
| `source` | `earth_search_v1`, Endpunkt v1, `sentinel-1-grd`; `asset_hosts` `sentinel-s1-l1c.s3.eu-central-1.amazonaws.com`; föderiert; `data_region` `aws:eu-central-1`; Abbildung aus §4.2; `asset_checksum` `crc64nvme` | M, `adr/0018` |
| `coverage` | Upstream-Aggregation; Breite einer Szene rund 250 km (IW); `max_geotile_level` wie Sentinel-2 (z8) bis zu Ottos Wort (Auslegung A6) | `adr/0018` §3.1 |
| `default_render` | nach F2 | — |
| `viewer` | nach F3; `browse: preview_tiles` (der Quicklook liegt in Radargeometrie, `adr/0018` §4.2); Zoomgrenzen in der Umsetzung gemessen | A |
| `maturity` | `stable` (wie Sentinel-2: dieselbe Quelle ohne Betriebszusage, Auslegung A7) | A |
| `mask` | keiner | — |
| `band_units` | `vv`, `vh`, `hh`, `hv`: `DN` | `adr/0018` §3.1 |
| `auxiliary_assets` | `thumbnail`, `safe-manifest`, `schema-*` | M |
| `search_filters`, `search_capabilities` | nach F5 | `adr/0021` |
| `index_presets`, `true_color` | leer | `adr/0018` F3 |
| `notices` | §4.4 | F2 `adr/0018` |

Dazu `docs/cloud-umgebung.md`: Asset-Host in die Tabelle der freigegebenen Hosts (heute aus der Sitzung erreichbar, §2).

### 4.6 Frontend

- Marken aus `earthx:notices` (§4.4), englisch, Erklärung im Tooltip, kein Zusatztext im Panel (M5-Plan §2 Punkt 8).
- Kein Abschnitt „Quick processing“ für Sentinel-1 (leere Presets).
- Originale: Link-Liste wie bei Sentinel-2; Beschriftung, dass die Dateien die COG-Fassung des Bucket-Betreibers sind, kein ESA-SAFE (`adr/0018` §4.3), als Tooltip.
- Was nicht geht, erscheint nicht (DS-00): Index-Knöpfe, Klassenmaske, ggf. Wertmaske (F4).

### 4.7 Fehlerfälle und Tests

Alle ohne Netz, mit synthetischen Fixtures unter `backend/tests/fixtures/` (CLAUDE.md):

- **Fixture:** synthetisches GCP-COG (`uint16`, Nodata 0, nichtlineare Lage, mit Übersichten), synthetisches Item und Collection in der Form von Earth Search (`s3://`-Adressen, `storage:requester_pays: true`, Paare VV+VH und HH+HV).
- **TPS:** Kachel, Zuschnitt, Job und Runner liegen gleich (Pixel an bekannter GCP-Stelle); `geotransform`-Einträge unverändert (alle bestehenden Tests grün); Datei ohne GCPs bei `gcp_tps` → benannter Fehler; GCPs bei `geotransform` → benannter Fehler.
- **Abbildung:** Präfix trifft → `https` auf `asset_hosts`; Präfix trifft nicht → Adresse bleibt und wird von `readers` abgewiesen; Abbildung auf fremden Host oder auf `http` → Startfehler; `href` mit `..` oder Query bleibt abgewiesen.
- **Fassung:** `FULL_OBJECT` → `crc64nvme`; `COMPOSITE` oder fehlend → ETag; Wert nie im Log.
- **Hinweise:** fehlendes Feld → Startfehler (B10); leerer `code`, doppelter `code`, zu langes Label → Startfehler; Hinweise in Rezept und `ATTRIBUTION.txt`.
- **Operatoren:** `band_math` auf VV/VH einer Szene geht; Index-Knöpfe, `mask`, ggf. `mask_values` → `422`; Mosaik nur innerhalb eines Durchgangs (über die Gruppierung, F3).
- **Suche:** Filter landen als `query` beim Adapter; unbekannter Wert → `400`.
- **Onboarding Punkt 9:** ein Operator-Lauf gegen Fixtures (Reprojektion mit TPS) End-to-End.
- **Live-Smoke** `tests_live/test_sentinel_1_grd_smoke.py`, Marker `live_dataset("sentinel-1-grd")`: Collection `200`; ein Item; Range-`GET` auf ein Datenband über `gateway` `206`; `?requestPayment` → `BucketOwner`; `HEAD` mit Prüfsummen-Modus → `FULL_OBJECT`; `in` auf `sar:polarizations` liefert so viele Treffer wie `eq`. Läuft in der CI ohne Proxy, nicht aus der Cloud-Sitzung (M5-Plan §6.5).
- **Browser:** Chromium/Playwright der Sitzung mit Fixtures, Hell/Dunkel, schmales Fenster; Bilder nicht ins Repo.

### 4.8 Doku mit der Umsetzung

- `architekturplan.md` 5.1: `earthx:georeferencing`, `earthx:notices`; `source` um Abbildung und Prüfsumme.
- `adr/0018` §10: Teil A als umgesetzt, mit PR.
- `docs/cloud-umgebung.md`: Asset-Host.
- Glossar-Begriffe (`adr/0026` F7): §8.
- Log-Zeile(n).
- Prüfanleitung für Otto (Browser und PowerShell 5.1) im PR, dazu der Befehl für den Live-Smoke lokal.

---

## 5. Auslegungen (angenommen von Otto am 07.11.2026)

- **A1 — Hinweise im Rezept ändern den Cache-Schlüssel nicht.** Sie sind Folge des Datensatzes, nicht des Auftrags.
- **A2 — TPS ist eine Eigenschaft des Datensatzes, nicht des Auftrags.** Kein Schalter im Panel.
- **A3 — Widerspruch zwischen Registry und Datei** (GCPs fehlen oder sind da, wo sie nicht sein sollen) ist ein Lesefehler mit eigener Art und `502`, nie eine stille Näherung.
- **A4 — Nur `href` wird umgeschrieben.** Die falsche Angabe `storage:requester_pays: true` bleibt im Item, wie die Quelle sie liefert; der Live-Smoke belegt den wahren Zustand.
- **A5 — `gsd` aus `sar:pixel_spacing_range`,** weil die Collection kein `gsd` nennt. Das ist der Pixelabstand, nicht die Auflösung; im Kommentar so benannt.
- **A6 — Coverage z8 wie Sentinel-2,** bis Otto anders entscheidet (die Stufe ist seine Einstellung, `adr/0004` §5).
- **A7 — `maturity: stable`** wie Sentinel-2 (gleiche Quelle, gleiche fehlende Betriebszusage).
- **A8 — Die Georeferenz-Methode gehört ins Rezept** (je Eingabe, im Cache-Schlüssel), nicht nur in die Registry: Ein Runner, der ein Rezept nachrechnet, braucht sie, und ein Ergebnis mit anderer Methode ist ein anderes Ergebnis (`adr/0014` §6.3).

---

## 6. Nicht Teil dieser Aufgabe

- Quick processings „VV dB“, „VH dB“, „Dual-pol RGB“ (DS-05a, DS-05c), Speckle-Filter (DS-05b), σ⁰ und RVI (DS-05d).
- Planetary Computer RTC (`adr/0018` Teil B; hängt an Ottos Messung) und eigene Geländekorrektur (Teil C, eigener ADR nach DS-04).
- Global Coherence, LiCSAR, EGMS (`adr/0030` F6).
- Neue Abhängigkeiten: keine nötig.

---

## 7. Schnitt und Umfang

Richtwert 400 geänderte Zeilen (CLAUDE.md). Angenommen (F1, §9a):

| PR | Inhalt | Größe (Schätzung) |
|---|---|---|
| **DS-04a** (dieser Draft-PR) | Plan; nach dem Merge von M5-13: §4.1 TPS als Reader-Fähigkeit, Feld `georeferencing`, synthetisches GCP-COG, Messung der Kachelkosten | rund 300–400 Zeilen ohne Fixture |
| **DS-04b** | §4.2–§4.5, §4.7, §4.8: Abbildung, Prüfsumme, Hinweise, YAML-Eintrag, Live-Smoke | rund 350–450 Zeilen |
| **DS-04c** | §4.6 Frontend: Marken, Originale, Browserprüfung | rund 150–250 Zeilen |

DS-05a hängt am Merge von DS-04b (Datensatz) und M5-14.

---

## 8. Begriffe für das Glossar (`adr/0026` F7)

Rückstreuung ↔ backscatter; Radar mit synthetischer Apertur ↔ synthetic aperture radar (SAR); Polarisation ↔ polarization; aufsteigende/absteigende Bahn ↔ ascending/descending orbit; relativer Orbit ↔ relative orbit; GRD ↔ ground range detected.

---

## 9. Fragen an Otto — beantwortet am 07.11.2026 (§9a)

**F1 — Schnitt (§7)?**
1. Drei PRs: TPS (in diesem PR), Datensatz, Frontend **(Empfehlung)**
2. Zwei PRs: TPS, dann Datensatz mit Frontend (über 400 Zeilen)
3. Ein PR für alles

**F2 — Standarddarstellung bis DS-05a (dB)?** Earth Search liefert je Item entweder `vv`/`vh` oder `hh`/`hv` (§2: rund 74 % mit VV, 26 % mit HH).
1. Graustufen der Ko-Polarisation, erstes vorhandene Band aus der Liste `vv`, `hh` (neue allgemeine Angabe in `default_render`); fester Stretch auf DN aus einer Messung an Szenen, je Szene über `/statistics` **(Empfehlung)**
2. Nur Szenen mit VV anbieten (feste Suchbedingung in der Registry); HH-Szenen (Polargebiete, Meereis) fehlen
3. Zwei Datensätze, VV-Familie und HH-Familie

**F3 — Zeitleiste und Ergebnisgruppen?**
1. Ein Schritt je Durchgang über `s1:datatake_id` (die Slices einer Bahn bilden ein Mosaik, wie `adr/0018` F3 es erlaubt); Ergebnisgruppen nach Zeitpunkt und `s1:datatake_id` **(Empfehlung)**
2. Je Tag und relativem Orbit
3. Jede Szene einzeln

**F4 — Wertmaske (DS-06) auf GRD?** `mask_values` kennt nur feste Werte; `adr/0018` §4.4 erlaubt auf DN nur relative Masken.
1. Aus, bis DS-05d (σ⁰) **(Empfehlung)**
2. An, mit Hinweis „Uncalibrated (DN)“
3. An, und `mask_values` bekommt Perzentile (eigene Aufgabe)

**F5 — Suchfilter (`adr/0021`)?**
1. Orbitrichtung, relativer Orbit (1–175), Aufnahmemodus (IW, EW, SM), Polarisation (enthält); dazu `aoi_coverage` aus den Umrissen und „Evaluate per pass“ **(Empfehlung)**
2. Wie 1, zusätzlich Auflösung (`s1:resolution`) und Aktualität (`s1:product_timeliness`)
3. Nur Orbitrichtung und Polarisation, ohne `aoi_coverage` und „Evaluate“

**F6 — Lizenz-Einstufung (B11, immer Otto)?**
1. Wie Sentinel-2: Sentinel Data Legal Notice, Stufe Processing, Attribution „Contains modified Copernicus Sentinel data {year}“ / „Copernicus Sentinel data {year}“, dieselben Nutzungsbedingungen **(Empfehlung)**
2. Otto prüft den Wortlaut im PR gesondert

Die Auslegungen A1–A8 (§5) gelten, wenn Otto nicht widerspricht.

## 9a. Antworten Otto (07.11.2026)

F1–F6 jeweils Option 1 (Empfehlung); die Auslegungen A1–A8 (§5) sind angenommen.

- **F1:** drei PRs. DS-04a (TPS, §4.1) in diesem Draft-PR, danach DS-04b (Datensatz) und DS-04c (Frontend).
- **F2:** Graustufen des ersten vorhandenen Bandes aus `vv`, `hh` (neue allgemeine Angabe in `default_render`); fester Stretch auf DN aus einer Messung an Szenen, je Szene über `/statistics`.
- **F3:** ein Schritt je Durchgang über `s1:datatake_id`; Ergebnisgruppen nach Zeitpunkt und `s1:datatake_id`.
- **F4:** `value_masking` aus bis DS-05d (σ⁰).
- **F5:** Orbitrichtung, relativer Orbit (1–175), Aufnahmemodus, Polarisation (enthält); dazu `aoi_coverage` und „Evaluate per pass“.
- **F6:** Lizenz wie Sentinel-2: Sentinel Data Legal Notice, Stufe Processing, dieselbe Attribution und dieselben Nutzungsbedingungen.

Ablauf: Nach dem Merge von M5-13 holt die Session `main` und setzt DS-04a im selben PR um.

---

## 10. Grenzen

- Modulgrenzen laut `architekturplan.md` 3.1 (Import-Linter); ausgehende Requests nur über `gateway`; Worker-Kern zustandslos; `decomp.py` unberührt (`quad_pol` aus).
- Kein Code je Datensatz: TPS, Abbildung, Prüfsumme und Hinweise sind Registry-Angaben.
- Keine AOI, Item-IDs, Hashes, `href` oder Prüfsummen in Logs, URLs, Issues oder PRs.
- Fixtures nur synthetisch.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.
- Vor „fertig“: `main` geholt, Lint, Typprüfung, Tests und Importregeln grün; alle Pflicht-Checks der CI grün.
