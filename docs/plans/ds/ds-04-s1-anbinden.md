# DS-04 — Sentinel-1 GRD anbinden: Plan-Schritt

**Status (09.11.2026):** Plan angenommen (Otto, 07.11.2026; Antworten in §9a). DS-04a (TPS) umgesetzt (§11, [#312](https://github.com/oscipal/earthX/pull/312)); DS-04b umgesetzt ([#318](https://github.com/oscipal/earthX/pull/318), §12), F7–F10 beantwortet (§12.4a); DS-04c umgesetzt im Draft-PR (§13), mit dem Fehler aus Ottos Browserprüfung vom 09.11.2026; F11 und F12 offen (§13.5). Ersetzt die frühere Datei, die den Text von DS-00 enthielt (`adr/0030` §9, Nebenbefund).
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
| **DS-04b** | §4.2–§4.5, §4.7, §4.8: Abbildung, Prüfsumme, Hinweise, YAML-Eintrag, Live-Smoke; Prüfauftrag Zwischenspeicher der TPS (§11) | rund 350–450 Zeilen |
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

---

## 11. Umsetzung DS-04a (07.11.2026)

Nach dem Merge von M5-13 (#311) auf `main` 309f0ec, im selben Draft-PR.

**Was gebaut ist:**

- **Registry:** `Georeferencing` (`geotransform`, `gcp_tps`) als Pflichtfeld `georeferencing` jedes Eintrags, ohne Vorgabe (B10); Startprüfung: `gcp_tps` nur bei `format: cog`. Die vier YAML-Einträge nennen `geotransform`. Veröffentlicht als `earthx:georeferencing` (`architekturplan.md` 5.1).
- **Eine Stelle für die Lage:** `CogReader` öffnet die Datei selbst. Bei `gcp_tps` legt er ein `WarpedVRT` mit `SRC_METHOD=GCP_TPS` im CRS der GCPs darüber und gibt es rio-tiler als `dataset`; rio-tilers affiner Zweig wird nicht mehr betreten. Kachel, Zuschnitt, Export, Mosaik und Job lesen alle über `CogReader.dataset`, sehen also dasselbe Raster. `readers` hält die Werte als `Literal`, weil es `catalog` nicht importieren darf (3.1).
- **Weg der Angabe:** `resolve_asset` nimmt sie aus der Registry in `ResolvedAsset.georeferencing`; `open_asset_ref` gibt sie an `asset_path`, der `AssetPath` trägt sie zum `CogReader`. Im Rezept steht sie in `asset` (A8).
- **Widerspruch Registry ↔ Datei (A3):** `GeoreferenceMismatch` in `readers`, Fehlerart `source_georeference`: im Job `502` „The source file is not placed the way the platform expects“, kein zweiter Versuch (nicht in `RETRYABLE`, im Frontend „fails again“), im Runner Exit-Code „Quelle“; in der Kachelroute `502` „the asset is not placed the way the platform expects“. Keine Meldung nennt Datensatz, Adresse oder Pfad.

**Abweichung vom Plan (Auslegung zu A8), bestätigt von Otto am 07.11.2026:** `geotransform` ist die Bedeutung eines fehlenden Schlüssels und wird im Rezept nicht geschrieben (`exclude_if`). So bleiben jedes bisherige `recipe.json` und jeder bisherige Hash und Cache-Schlüssel gleich; die festen Hashes in `test_recipe.py` sind unverändert. `gcp_tps` steht im Rezept und geht in Hash und Cache-Schlüssel ein (Test). Nachtrag in `adr/0014` §4.

**Bitgleichheit:** Der Job liest das TPS-Raster des Readers mit exakten Fenstern; seine Pixel sind die der Kachel auf der nativen Ebene (Test). Zwei Läufe desselben Rezepts geben dieselben Bytes; der Runner rechnet mit demselben Kern. Kachel, Zuschnitt und Job warpen das TPS-Raster jeweils auf ihr eigenes Raster: zweimal `nearest` statt einmal, die Lage bleibt die der TPS bis auf ein Quellpixel.

**Tests (synthetisch, `tests/earthx/readers/mini_gcp.py`):** `uint16`-Datei nur mit GCPs, Biegung von 12 Pixeln, jedes Pixel ein eigener Wert. Jeder der 39 GCPs liegt in Reader und Kachel auf seinem Pixel (höchstens 1 Pixel daneben); eine affine Näherung durch dieselben GCPs verfehlt sie (bis 4 Pixel, 9 ganz). Gegenprobe: Ohne `SRC_METHOD=GCP_TPS` schlagen die Lage-Tests fehl. Dazu: Job gleich Reader, zwei Läufe bytegleich, beide Widersprüche, Fehlerart, Werte des Felds in `AssetPath`, `ResolvedAsset`, Rezept und Registry, Collection, Kachelroute `200` und `502`.

**Kosten je Kachel [M]:** eine IW-Szene (VV, 26 526 × 16 678 Pixel, Übersichten 2 bis 64, 210 GCPs) im Hügelland, über `/vsicurl` direkt im Kratzverzeichnis der Sitzung (nicht über `gateway`, wie `adr/0018` §4.1); Median aus drei Läufen, Kachel 256 × 256 über der Mitte der GCPs, HTTP-Antworten ab dem zweiten Lauf zum Teil aus GDALs Zwischenspeicher:

| Zoom | affin (rio-tiler) | TPS (`CogReader`) |
|---|---|---|
| Öffnen | < 0,01 s | 0,02 s |
| z7 | 0,04 s | 0,24 s |
| z9 | 0,09 s | 0,34 s |
| z11 | 0,06 s | 0,19 s |
| z13 | 1,99 s | 2,04 s |

TPS kostet bei groben und mittleren Zoomstufen rund 0,1 bis 0,25 s Rechenzeit mehr je Kachel; bei z13 überwiegt das Netz. Bytes je Kachel sind nicht gemessen. Ob sich die Rechenzeit drücken lässt, prüft DS-04b an mehreren Szenen (Prüfauftrag unten).

**Prüfauftrag für DS-04b (Otto, 07.11.2026):** Kann die TPS-Transformation je Szene im Prozess `tiler` zwischengespeichert werden, statt sie je Kachel neu aus den GCPs zu bilden? Mit Messung vorher und nachher, an mehreren Szenen und denselben Zoomstufen wie oben. Dabei zu klären: was genau GDAL je `WarpedVRT` neu rechnet (Lösung des TPS-Gleichungssystems, vorgeschlagenes Ausgaberaster, Übersichten), wo der Speicher dafür liegt (je Prozess, begrenzt, Schlüssel aus Datensatz, Item, Asset und Fassung) und dass Kachel, Zuschnitt und Job weiter dasselbe Raster sehen.

**Noch nicht gebaut** (DS-04b, DS-04c): Eintrag `sentinel-1-grd`, Abbildung `s3://` → `https://`, Prüfsumme CRC64NVME, `notices`, Live-Smoke, Frontend.

---

## 12. Umsetzung DS-04b (08.11.2026)

Auf `main` aae2196 (nach M5-08a #314 und M5-13 #311), eigener Draft-PR. Belegstufen wie oben; gemessen am 08.11.2026 nur Metadaten und, für §12.2, vier Szenen im Kratzverzeichnis der Sitzung (nicht im Repo, keine IDs hier).

### 12.1 Was gebaut ist

- **Registry, allgemein (B10, ohne Vorgabe):** `source.asset_href_rewrites` (Präfix-Paare; Startprüfung: beide enden auf `/`, alt ist kein `https`, neu ist `https` auf einem Host aus `asset_hosts` ohne Port und ohne `..`, kein Präfix liegt in einem anderen), `source.asset_checksum` (`crc64nvme` oder `null`), `notices` (`code` in `lower_snake_case`, `label` bis 32, `tooltip` bis 200 Zeichen, je eine Zeile, jeder Code einmal; auch an ausgeschiedenen Einträgen, weil der Hinweistext alter Jobs daraus entsteht), `default_render.asset_selection` (`all`/`first_present`, F2). Die vier bisherigen Einträge setzen das bisherige Verhalten (`[]`, `null`, `[]`, `all`). Alles veröffentlicht (`architekturplan.md` 5.1).
- **Abbildung (§4.2):** im STAC-Modul aus M5-08a, für Suche und Item-Abruf. Nach dem Merge von M5-08b (#317) in `normalize_for`, an derselben Stelle wie die festen Asset-Schlüssel: vor dem Cache, der damit die `https`-Adressen hält; eine geänderte Abbildung gilt nach Ablauf der Cache-Frist. Nur `href` ändert sich (A4). Ein Eintrag ohne Abbildung bekommt seine Items unverändert zurück; der Golden-Test von Earth Search bleibt bitgleich.
- **Fassung (§4.3):** `HEAD` mit `x-amz-checksum-mode: ENABLED`, wo die Registry `crc64nvme` nennt; Fassung `crc64nvme` nur bei `x-amz-checksum-type: FULL_OBJECT` und einem Wert in der Form von 8 Byte Base64, sonst ETag wie bisher. Der Wert steht in keinem Log (Test).
- **Hinweise (§4.4):** in `recipe.json` unter `provenance.notices` (Job, Export, Zuschnitt, lokaler Runner); das Feld fehlt, wo ein Datensatz keine hat, sodass jede bisherige Datei bytegleich bleibt; nie im Hash (A1). In `ATTRIBUTION.txt` je Hinweis ein Absatz nach der Zitierangabe. Nachtrag in `adr/0014` §4.
- **Eintrag `sentinel-1-grd`** (`backend/catalog/datasets/sentinel-1-grd.yaml`) nach §4.5 und F2–F6, mit den Abweichungen in §12.3.
- **Live-Smoke** `backend/tests_live/test_sentinel_1_grd_smoke.py`: Collection `200`; ein Item, Datenbänder unter `https://sentinel-s1-l1c…/`; Range-`GET` `206` über `gateway`; `?requestPayment` → `BucketOwner`; `HEAD` mit Prüfsummen-Modus → `FULL_OBJECT`; `in` auf `sar:polarizations` zählt wie `eq`. Der Trockenlauf (`tests/test_live_smoke_dry_run.py`) spielt ihn gegen ein synthetisches Double. Der Filter-Smoke (DS-02) prüft jetzt auch die vier Filter von Sentinel-1 und liest eine Listen-Eigenschaft als „enthält eines davon“.
- **Onboarding Punkt 9:** Die Kette läuft für `sentinel-1-grd` End-to-End auf einer synthetischen GCP-Datei (Suche, Kachel, Zuschnitt, Auftrag, Reprojektion des TPS-Rasters, `recipe.json`).

### 12.2 Prüfauftrag: TPS je Szene im `tiler` halten [M]

**Was GDAL je Kachel neu rechnet.** `CogReader` baut je Kachel ein `WarpedVRT` mit `SRC_METHOD=GCP_TPS`. GDAL löst dabei das TPS-Gleichungssystem (210 GCPs, vorwärts und rückwärts) und schlägt das Ausgaberaster vor (`GDALSuggestedWarpOutput2`): rund 8–10 ms. Für jede Übersichtsstufe, die eine Kachel liest, legt GDAL ein implizites Übersichts-VRT mit einem eigenen TPS-Transformer an (GCPs skaliert, System neu gelöst). Danach warpt GDAL die Blöcke des Zwischenrasters (512 × 128); dabei wertet der Näherungs-Transformer (Fehlergrenze 0,125 Pixel) die TPS je Zeile mehrfach aus. Ein Block kostet so 45–55 ms. Exakt ausgewertet (Fehlergrenze 0) kostet ein Fenster von 512² 6,4 s statt 0,25 s; die Näherung ist also schon in Gebrauch.

**Falle:** Ein `WarpedVRT` mit vorgegebenem Raster (`transform`, `width`, `height`) nimmt in rasterio 1.5.2 `GDALCreateGenImgProjTransformer3` mit der Geotransformation der Datei und lässt die GCPs ganz weg (Fall 1 in `rasterio/_warp.pyx`); die Pixel liegen dann falsch, ohne Warnung. Das gespeicherte Raster lässt sich so nicht wiederverwenden.

**Messung.** Vier IW-Szenen (VV, rund 25 500 × 16 700 Pixel, Übersichten 2–64, je 210 GCPs) als lokale Dateien, damit das Netz nicht mitmisst; je Zoomstufe 2 bis 9 verschiedene Kacheln 256 × 256 um die Mitte der GCPs; Median je Kachel; vor jeder Messung einmal mit einem frischen Reader gelesen (Seiten-Cache warm, Blöcke des gemessenen VRT nicht). „Gehalten“: `CogReader` je Szene einmal gebaut (22–36 ms) und für alle Kacheln wiederverwendet.

| Zoom | affin (rio-tiler) | TPS heute (neu je Kachel) | TPS je Szene gehalten |
|---|---|---|---|
| z7 | 20 ms | 100 ms | 75 ms |
| z9 | 26 ms | 137 ms | 111 ms |
| z11 | 33 ms | 100 ms | 63 ms |
| z13 | 32 ms | 83 ms | 39 ms |

Die Pixel sind in allen 34 Fällen bitgleich. Das Halten spart 25–45 ms je Kachel (25 bis 55 %). Der Rest über affin (40 bis 80 ms) ist die TPS im Warp selbst; den nimmt kein Speicher des Transformers weg, nur eine gröbere Fehlergrenze (andere Pixel) oder ein Speicher gewarpter Blöcke.

**Wo der Speicher läge.** Der `tiler` liest Kacheln im Threadpool von Starlette; ein GDAL-Datensatz darf nicht von zwei Threads zugleich gelesen werden. Darum nicht gebaut, sondern F7. Kachel, Zuschnitt und Job sehen weiter dasselbe Raster: Ein gehaltener Reader entsteht auf demselben Weg (`asset_path` → `CogReader`). Ein Schlüssel aus Datensatz, Item, Asset und Adresse ist da; die Fassung kennt der `tiler` nicht (kein `HEAD` je Kachel), also begrenzt eine Lebensdauer das Risiko, dass eine Datei unter derselben Adresse wechselt.

### 12.3 Abweichungen und neue Auslegungen

- **Coverage z7 statt z8 (zu A6):** Die Startprüfung aus `adr/0004` §5 lässt bei 250 km Breite höchstens z7 zu. F8.
- **A9 — Pixelgröße aus dem Item:** Ein GRD-Item nennt weder `gsd` noch `spatial_resolution`, nur `sar:pixel_spacing_range`. Ohne Pixelgröße weist der Intake jeden Auftrag und Zuschnitt ab (`422`). `asset_gsd` nimmt den Pixelabstand jetzt als letzte Stufe (allgemein über die SAR-Erweiterung, wie A5 für die Collection). F9.
- **Stretch je Asset bei `first_present`:** gemessen p2/p98 der DN an je 8 Szenen (IW und EW, März bis Oktober 2026, Übersicht 1:64): VV im Median 87/249, HH 69/755. Ein gemeinsamer Stretch hätte eine der beiden Familien verfälscht; darum ein Paar je Asset, das des gezeichneten Bandes gilt.
- **`band_units: DN`** wie im Plan; kein UCUM-Zeichen (UCUM schriebe `{DN}`).
- **Zitierangabe:** keine DOI und kein `cite-as`-Link an der Collection [M]; die Angabe nennt ESA, das Produkt und die Collection bei Earth Search.
- **Nicht gebaut:** Bytes je Kachel (DS-04a offen); der Live-Smoke ist nicht in `.github/workflows/live-smoke.yml` eingetragen (`.github/` bleibt unverändert, §10).
- **Bis DS-04c** kennt das Frontend `first_present` nicht: Es zeichnet das erste Asset der Liste (`vv`), eine HH-Szene zeigt dann kein Bild. Die Marken der Hinweise fehlen ebenso bis DS-04c.
- **Vorschau bis DS-04c:** `quicklookPlan` (`frontend/src/datasets.ts`) nimmt das `thumbnail` eines Items vor jeder `browse`-Angabe. Sentinel-1-Items tragen eines (in Radargeometrie, ohne `proj:code`), also wählt das Frontend nie den Kachelplan, und die Browse-Ansicht zeigt für Sentinel-1 keine Vorschau. Gefunden im Review; die Lösung (ein Thumbnail nicht nehmen, wo `browse` es ausschließt, oder ein Registry-Feld dafür) gehört zu DS-04c.

### 12.4 Fragen an Otto

**F7 — TPS je Szene im `tiler` halten?**
1. Ein kleiner Pool je Szene im Prozess: ein Thread leiht einen Reader und gibt ihn zurück; Obergrenzen je Szene und gesamt, Lebensdauer rund 10 min; Schlüssel aus Datensatz, Item, Asset, Adresse und Georeferenz. Eigener PR nach DS-04c, mit der Messung oben als Vorher **(Empfehlung)**
2. Ein Reader je Szene und Thread (einfacher, aber jeder Thread baut erneut)
3. Nicht bauen; 25–45 ms je Kachel sind die Mühe nicht wert

**F8 — Coverage-Stufe?**
1. z7, wie die Startprüfung es bei 250 km zulässt **(Empfehlung)**
2. z8 wie Sentinel-2; dafür müsste die Breite unter 156 km eingetragen oder die Prüfung geändert werden

**F9 — Pixelgröße aus `sar:pixel_spacing_range` (A9)?**
1. Bestätigen **(Empfehlung)**
2. Stattdessen aus der Datei lesen (eine Leseanfrage je Auftrag im Intake)

**F10 — Tooltip-Texte der Hinweise?**
1. Wie im Eintrag: „Placed by the scene's own ground control points without terrain correction; positions can be off by tens of metres, more in steep terrain.“ und „Values are the digital numbers of the GRD product, not calibrated backscatter, so dB thresholds from the literature do not apply.“ **(Empfehlung)**
2. Anderer Wortlaut (bitte angeben)

### 12.4a Antworten Otto (08.11.2026)

- **F7:** Option 3 vorerst, der Speicher wird nicht gebaut. **Wiedervorlage nach DS-04c:** Ist Sentinel-1 im Browser spürbar langsam, folgt Option 1 (Pool je Szene im Prozess) als eigener PR, mit der Messung aus §12.2 als Vorher.
- **F8:** Option 1, Coverage z7.
- **F9:** Option 1, `sar:pixel_spacing_range` als letzte Stufe von `asset_gsd` (Auslegung A9 bestätigt).
- **F10:** Option 1, die Tooltip-Texte wie im Eintrag.
- **Workflow:** eine Zeile in `.github/workflows/live-smoke.yml` im Schritt mit `test_earth_search_smoke.py` für den Sentinel-1-Smoke freigegeben, sonst nichts in `.github/`.
- **Ablauf:** M5-08b (#317) wird vor diesem PR gemergt; danach holt die Session `main` und löst die Überschneidungen (YAML nach `data_region`, `normalize_for`).

### 12.5 Prüfanleitung für Otto

**Browser:** lokal `npm run dev` und das Backend starten, im Data catalogue „Sentinel-1 GRD“ wählen: Gruppe „Radar“, Provider ESA, AWS, Element 84; Suchfilter „Orbit direction“, „Relative orbit“, „Acquisition mode“, „Polarization“; kein Abschnitt „Quick processing“. Eine Suche über Mitteleuropa liefert Szenen mit einem Zeitschritt je Durchgang. Die Browse-Vorschau fehlt bis DS-04c (§12.3); die Kacheln der Ansicht in Graustufen ab Zoom 7 gibt es für VV-Szenen, für HH erst mit DS-04c. In der Sitzung nicht im Browser geprüft.

**PowerShell 5.1** (nur Metadaten, eine Datei per `HEAD`):

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$es = 'https://earth-search.aws.element84.com/v1'
$body = '{"collections":["sentinel-1-grd"],"limit":1}'
$i = (Invoke-RestMethod -Method Post -Uri "$es/search" -Body $body -ContentType 'application/json').features[0]
$i.assets.vv.href                       # s3://sentinel-s1-l1c/… (die Quelle; die Plattform liest https)
$u = $i.assets.vv.href -replace '^s3://sentinel-s1-l1c/', 'https://sentinel-s1-l1c.s3.eu-central-1.amazonaws.com/'
$r = [Net.HttpWebRequest]::Create($u); $r.Method = 'HEAD'; $r.Headers.Add('x-amz-checksum-mode', 'ENABLED')
$x = $r.GetResponse(); $x.Headers['x-amz-checksum-type']; $x.Close()     # FULL_OBJECT
(Invoke-WebRequest 'https://sentinel-s1-l1c.s3.eu-central-1.amazonaws.com/?requestPayment' -UseBasicParsing).Content
#   … <Payer>BucketOwner</Payer> …
```

**Live-Smoke lokal** (geht ins Netz), aus der Repo-Wurzel:

```powershell
$env:PYTHONPATH = 'backend'; pytest backend/tests_live/test_sentinel_1_grd_smoke.py backend/tests_live/test_search_filters_live.py
```

Der tägliche Lauf nimmt `backend/tests_live/test_sentinel_1_grd_smoke.py` im Schritt mit `test_earth_search_smoke.py` mit (`.github/workflows/live-smoke.yml`, eine Zeile, von Otto am 08.11.2026 freigegeben).

---

## 13. Umsetzung DS-04c (09.11.2026)

Auf `main` 05a3b1c (nach DS-04b #318), eigener Draft-PR, nur Frontend. Belegstufen wie oben; gemessen am 09.11.2026 nur Metadaten von Earth Search und das Vorschaubild einer Szene (im Kratzverzeichnis der Sitzung, nicht im Repo, keine IDs hier).

### 13.1 Was gebaut ist

- **`first_present` in der Darstellung (F2):** `defaultRenderOf(collection, item)` nimmt das erste Asset der Liste, das das Item trägt, mit dem Stretch-Paar an derselben Stelle; ein Item ohne eines davon hat keine Standarddarstellung. Ohne Item steht das erste der Liste für den Datensatz. Ansicht („View whole scene“, „Crop to AOI“), Vorschau-Kacheln, georeferenziertes Asset eines Quicklooks und Mosaik-Job nehmen das Band je Szene; Standard-Look, Bezugspunkt von „Temporary“ und Standardband im Band-Menü kommen von der ersten Szene des gezeigten Bildes (die Szenen eines Bildes sind ein Überflug); eine Szene ohne eines der Bänder fällt mit Meldung aus der Ansicht. „Originals“ bietet alle Assets der Liste an, jede Szene liefert das, das sie trägt. `all` und ein Backend ohne das Feld bleiben wie bisher.
- **Vorschau nach der Suche (§12.3):** `quicklookPlan` nimmt das Thumbnail eines Items nur noch, wenn die Karte es platzieren kann (`quicklookCoords`: CRS und georeferenziertes Asset). Sentinel-1 bekommt damit die Kacheln, die `browse: preview_tiles` nennt (ab z7, Band je Szene); die Trefferliste zeigt das Thumbnail weiter neben der Szene. Allgemein, kein Zweig auf den Datensatz.
- **Marken (§4.4, §4.6):** `earthx:notices` als je eine Marke (`.badge`), englisch, Erklärung im Tooltip, kein Text daneben: im Data catalogue neben „Prototype“, unter dem Kasten der Suchergebnisse und in einer eigenen Zeile unter dem Kopf einer Ansicht bzw. eines Layers. Der Tooltip erscheint in beiden Tooltip-Stufen, weil er erklärt, was die Marke bedeutet (wie ein (i), `tipLevel.ts`). Ein Eintrag, der kein ganzer Hinweis ist, wird ausgelassen.
- **Browser-Skript** `frontend/e2e/s1-pass.cjs` (synthetisch, ohne Backend): Vorschau mit dem Band je Szene, kein Thumbnail in Radargeometrie auf der Karte, Marken mit Tooltip an allen drei Stellen, Kontur eines zusammengeführten Überflugs aus zwei Slices (Sentinel-1) und aus zwei Kacheln (Sentinel-2). Hell/Dunkel, breit und 360 px.

### 13.2 Fehler aus Ottos Browserprüfung: Szenengrenzen im zusammengeführten Layer

**Befund (Otto, 09.11.2026):** Bei „Crop and merge to AOI“ zeichnet die Karte innerhalb der AOI die Umrisse der einzelnen Szenen über das Mosaik; bei zwei Szenen eines Sentinel-1-Überflugs eine doppelte Linie quer durchs Bild.

**Ursache, bestätigt [M]:** Die gelbe Kontur der zugeschnittenen Ansicht ist je Gruppe die Vereinigung der Footprints, geschnitten mit der AOI (`groupOutline.ts`, M3-09 §10). Zwei aufeinanderfolgende Slices eines Datatakes teilen bei Earth Search keine exakte Kante: Die Ecken der gemeinsamen Kante liegen 0,003 bis 0,0075° auseinander, mal überlappend, mal mit Lücke, und eine Seite hat dort teils eine Ecke mehr. Die Vereinigung zerfällt dann in zwei Ringe, in einen Ring mit Loch oder (nach dem Schnitt mit der AOI) in einen Ring mit einem langen schmalen Schlitz; alle drei werden als Doppellinie gezeichnet. Gemessen an 921 Paaren aufeinanderfolgender Slices (Europa, Amerika, Asien, Polargebiete, September/Oktober 2026): 387 (42 %) zerfallen. Andere Ebenen scheiden aus: Die Coverage-Footprints sind in der Ansicht aus, die Vorschau-Quicklooks liegen unter der Ansicht und zeichnen keine Linien. Sentinel-2-Kacheln eines Überflugs überlappen breit, ihre Vereinigung war in der Stichprobe (4 Überflüge, 200 Kacheln) je ein Stück.

**Behebung (allgemein):** Vor der Vereinigung werden die Footprints einer Gruppe aneinander eingerastet (`snapFootprints`): Eine Ecke in höchstens 0,01° Abstand zu einer Ecke eines früheren Footprints übernimmt deren Lage, und eine Kante bekommt die Ecken anderer Footprints eingefügt, die in diesem Abstand an ihr liegen. Danach teilen beide Slices dieselben Punkte entlang der gemeinsamen Kante. Ergebnis an den 921 Paaren: 0 zerfallen (0,008° war die kleinste Toleranz, die alle schloss); bei Sentinel-2 ändert sich die Fläche der Kontur um höchstens 0,06 %. Die Toleranz verschiebt eine Kontur höchstens um rund 1 km, und nur dort, wo Szenen tatsächlich aneinanderstoßen; eine echte Lücke über 0,01° bleibt sichtbar (Test). Ein Fehler der Geometrie-Bibliothek fällt wie bisher auf die Footprints einzeln zurück. Nach dem Review: Eine Ecke genau auf einer früheren Ecke bleibt, wo sie ist; verglichen werden nur Footprints, deren Rahmen sich auf die Toleranz nahekommen (40 Footprints mit je 300 Ecken: 0,2 s statt 3,2 s); offene oder zu kurze Ringe und Footprints schmaler als drei Toleranzen bleiben unverändert, weil sonst Ecken eines Nachbarn auf beiden Längskanten landen und sie kreuzen.

**Tests:** synthetische Slices in der Form von Earth Search: ohne Einrasten zerfällt die Vereinigung (Vorbedingung), mit Einrasten ein Ring, in der AOI keine Ecke außer ihrem Rand, unabhängig von der Reihenfolge; echte Lücke bleibt; zwei überlappende Kacheln unverändert; Randfälle (eine Fläche, leer, Toleranz 0, MultiPolygon, NaN fällt zurück). Gegenprobe: ohne Einrasten vier Tests rot; im Browser meldet `s1-pass.cjs` dann „1 rings and 4 corners inside the AOI“, mit Einrasten grün.

### 13.3 Quicklook für Sentinel-1 [M]

- Das Item trägt `thumbnail` (Rolle `thumbnail`, `image/png`) → `…/preview/quick-look.png` der SAFE-Struktur, nach der Abbildung aus §4.2 unter dem Asset-Host. **Anonym abrufbar:** `GET` 200, rund 340 kB, 532 × 341 Pixel, `Access-Control-Allow-Origin: *` (auch auf `OPTIONS`), also im Browser in ein Canvas ladbar.
- Inhalt: RGB-Komposit (rot Ko-, grün Kreuzpolarisation, blau ihr Verhältnis), nicht das Graustufenbild der Kacheln (VV bzw. HH). Lage in Radargeometrie: bei der gemessenen aufsteigenden Szene liegt der Norden unten (erste Zeile = früheste Zeit = Süden), Westen links; bei absteigender Bahn ist es umgekehrt gespiegelt.
- Neben dem Bild liegt `preview/map-overlay.kml` (rund 1 kB) mit einem `gx:LatLonQuad`: die vier Ecken des Vorschaubilds in der Reihenfolge unten links, unten rechts, oben rechts, oben links des Bildes, also mit der Spiegelung schon darin. Die Datei ist **kein Asset** des Items; ihre Adresse entstünde nur aus der Ordnerkonvention. Ihre Ecken weichen von den Ecken der Item-Geometrie um bis zu rund 0,1° ab.
- Die Item-Geometrie hat 6 bis 10 Punkte: die vier Ecken der Szene und Zwischenpunkte an den Slice-Grenzen. Für eine Einpassung müssten die vier Ecken daraus bestimmt werden (z. B. über die Winkel) und je Bahnrichtung den Bildecken zugeordnet werden.
- Nicht gebaut, Frage F11.

### 13.4 Abweichungen und Auslegungen

- **Marken „an der Ergebnisgruppe“** stehen unter dem Kasten des Datensatzes in den Suchergebnissen, nicht an jeder Zeitgruppe: Alle Gruppen eines Datensatzes haben dieselben Hinweise, zwei Marken je Gruppe würden die Liste verdoppeln. Im Kasten selbst gehen sie nicht, weil er bei einem Datensatz ein gesperrter Knopf ist, über dem kein Tooltip erscheint.
- **Marken „am Layer“** stehen in einer eigenen Zeile unter dem Kopf der Einstellungen der Ansicht und eines daraus gehefteten Layers, nicht in der Layerzeile (deren elf Plätze sind fest, UI-03).
- **Tooltip-Stufe:** Die Marken der Hinweise zeigen ihren Tooltip auch in der Stufe „simple“; die übrigen Marken bleiben „advanced“.
- **Zuschnitt-Downloads** nehmen die Bänder aus der Bandtabelle des Dialogs (NM4-75) und sind nicht geändert; nur der Fall ohne Bandtabelle nennt weiter das erste Asset der Liste.
- **Nicht gebaut:** die Beschriftung der Originale als COG-Fassung des Bucket-Betreibers (§4.6), weil es dafür keine Registry-Angabe gibt und ein Text je Datensatz im Code gegen §10 verstieße; Frage F12.
- **F7 (Wiedervorlage):** Die Kachelkosten der TPS sind in diesem PR nicht neu gemessen; ob Sentinel-1 im Browser spürbar langsam ist, sieht Otto bei der Prüfung (§13.6).

### 13.5 Fragen an Otto

**F11 — Quicklook für Sentinel-1 auf der Karte?**
1. Das `thumbnail` über die vier Ecken der Item-Geometrie auf die Karte einpassen, Zuordnung der Bildecken je Bahnrichtung (`sat:orbit_state`) gespiegelt, mit der Marke „Approximate geolocation“; sichtbar auch unter z7, Kacheln ab z7 darüber. Allgemein über eine neue Registry-Angabe (z. B. `viewer.quicklook_placement: footprint_corners`), kein Zweig auf den Datensatz. Lage auf rund einen Kilometer, Farben als RGB-Komposit **(Empfehlung)**
2. Wie 1, aber die Ecken aus `preview/map-overlay.kml` (Lage des Herstellers, Spiegelung schon darin); dafür eine zweite Anfrage je Szene an eine Datei, die kein Asset ist
3. Vorschau aus dem `tiler` mit TPS, wie jetzt gebaut (exakte Lage, Graustufen wie die Ansicht, erst ab z7, je Kachel 0,1–0,3 s)
4. Das Vorschaubild nur in der Trefferliste (heute schon so), auf der Karte die Kacheln aus 3

**F12 — Beschriftung der Originale (§4.6)?**
1. Neue allgemeine Registry-Angabe `source.originals_note` (englisch, ein Satz, ohne Vorgabe; bei den vier bisherigen Einträgen `null`), als Tooltip an „Originals“; Sentinel-1: „Cloud-optimized GeoTIFFs as the bucket operator converted them, not the ESA SAFE product.“ Kleiner eigener PR mit Backend **(Empfehlung)**
2. Den Satz als dritten Hinweis in `notices` (erscheint dann auch als Marke)
3. Weglassen

### 13.6 Prüfanleitung für Otto

**Browser:** `main` mit diesem PR, lokal `npm run dev` und das Backend starten.

1. Data catalogue: „Sentinel-1 GRD“ zeigt die Marken „Approximate geolocation“ und „Uncalibrated (DN)“; beim Überfahren steht der Satz aus F10 im Tooltip, auch mit Tooltips auf „simple“.
2. Suche über Mitteleuropa: unter „Showing dataset“ dieselben zwei Marken. Ab Zoom 7 zeigt die Karte die Vorschau-Kacheln der Szenen in Graustufen (VV); eine Suche im Nordpolarmeer (EW, HH) zeigt sie ebenfalls (HH).
3. Zwei Szenen eines Überflugs ankreuzen, AOI über ihre Grenze, „Crop and merge to AOI“: eine gelbe Kontur um das Mosaik, **keine Linie quer durchs Bild**; die Marken stehen unter dem Kopf der Ansicht. Dasselbe mit Sentinel-2 (zwei Kacheln eines Überflugs).
4. „Download full scene“ → „Originals“: je Szene das Band der Ko-Polarisation (`vv` bzw. `hh`).
5. Ob die Kacheln spürbar langsam laden (Wiedervorlage F7).

**Browser-Skript** (ohne Backend, braucht Playwright mit Chromium, das keine Abhängigkeit des Projekts ist), aus `frontend/`:

```powershell
npm run dev   # in einem zweiten Fenster
node e2e/s1-pass.cjs
```

