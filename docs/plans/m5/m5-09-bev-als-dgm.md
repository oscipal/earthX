# M5-09 — BEV ALS-DGM 1 m über ATOM

**Stand:** 16.11.2026, Plan angenommen (Otto, 16.11.2026: F1–F8 jeweils Option 1, §8a), umgesetzt im selben Draft-PR (§9); offen sind Ottos lokale Schritte 2–6 (§6).
**Stufe B.** Höchstens zwei PRs (F7).
**Aufgabe:** M5-09 aus `docs/plans/m5/m5-discovery-und-suche.md` §6.2 (Opus, mittel). Abhängigkeit M5-30b Teil 7 ist gemergt; M5-10 (PR A #350, PR B #357) ebenso.
**Grundlagen:** `adr/0023` §4.2, §7.2, §7.3, §8.3, §9.1, F1, F2, F5, F7; `adr/0032` §9 und Nachträge vom 14. und 15.11.2026 (Ersatz, Pyramide, Suchtreffer); `adr/0011` F6; `adr/0026` F7; `adr/0027` §6.1; `adr/0024`; `KLAERUNGEN.md` B8, B10–B13; Pläne M5-07 (WorldCover), M5-08 (swissALTI3D), M5-10, M5-30.
**Vorgaben Otto zu dieser Aufgabe (16.11.2026):**
- Unter `min_zoom` Ersatz durch GLO-30 wie bei swissALTI3D, unter z7 aus der GLO-30-Pyramide; nie verschwindet ein Bild, in keiner Ansicht.
- `category` aus `backend/catalog/categories.yaml`; Schlagworte deutsch und englisch.
- Host in `backend/catalog/hosts.yaml`, falls M5-36 gemergt ist, sonst als Frage (F3).
- Capability `terrain` wie GLO-30 und swissALTI3D.
- `limitations` nach Bedarf, keine Marken.
- Download im Originalformat.
- Lizenz-Einstufung und Attribution bestätigt Otto im PR (F2).
- Live-Abrufe macht Otto lokal; die Session nennt die Befehle (§6).

Belegstufen wie in `adr/0023`: **M** gemessen (06.11.2026, M5-01b), **P** am Primärtext oder Quelltext gelesen (BEV-Metadaten am 16.11.2026, Code auf `main` 4f7ffd4), **S** Suchtreffer, **A** eigene Ableitung. Kachelnamen, Adressen von Dateien und DOIs stehen nicht in diesem Dokument; die Adresse des Dienstes steht in den öffentlichen Metadaten und im Messskript.

---

## 1. Ziel

1. **BEV ALS-DGM 1 m** (`bev-als-dgm`, Kennung fest seit dem Bewertungs-Set von `adr/0026`) als fünfter materialisierter Datensatz, als YAML unter `backend/catalog/datasets/`, mit vollständiger Onboarding-Checkliste (`projektuebersicht.md` §5, alle elf Punkte).
2. **Ein Materialisierer für den ATOM-Dienst** des BEV: Dienst-Feed → Dataset-Feed je Kachel → eine Datei `image/tiff`. Er öffnet keine Datei und geht nur über `gateway`.
3. **Ein Bild bei jedem Zoom** ohne neue Mechanik: `overview: substitute` → `cop-dem-glo-30`, unter z7 aus dessen Pyramide, in allen Ansichten (Crop and merge, angeheftete Ebene, Suchtreffer, eine Szene, Vorschau von `terrain`).

**Nicht Teil:** ALS-DOM (Oberflächenmodell im selben Feed), Orthofotos DOP, ein allgemeiner INSPIRE-ATOM-Extraktor für den Harvest (M5-21), ältere Stichtage, falls F1 = 1.

---

## 2. Die Quelle

### 2.1 Was belegt ist

| Was | Stand | Beleg |
|---|---|---|
| ATOM-Dienst „AT.BEV ATOM Downloaddienst ALS EL Höhendaten“ ohne Anmeldung | lesbar | M (06.11.), Dienst-Metadatensatz P (16.11.) |
| Adresse des Dienst-Feeds | GeoNetwork-ATOM: `https://data.bev.gv.at/geonetwork/srv/atom/describe/service?uuid=208cff7a-…` (vollständig im Messskript) | P: `gmd:distributionInfo` je Kachel-Metadatensatz und im Dienst-Metadatensatz |
| Inhalt | DTM und DSM, Stichtage 15.09.2019 und 15.09.2021 bis 15.09.2025, je Stichtag und Modell 55 Kacheln zu 50 km | M (06.11.) |
| Kachel | eigener Metadatensatz und eigener DOI je Kachel und Stichtag; Titel „ALS DTM CRS3035RES50000mN…E… Höhenraster 1m Stichtag TT.MM.JJJJ“ | P |
| Kachelname | INSPIRE-Gitter: Auflösung 50 000 m, Nord- und Ostwert der Ecke in EPSG:3035 | P (Titel), A (Ecke unten links nach INSPIRE-Gitter, prüft das Messskript) |
| Datei | `…/download/ALS/DTM/<JJJJMMTT>/<Kachel>.tif` auf demselben Host | S |
| Datei (eine Randkachel, 2025) | COG (`LAYOUT=COG`), LZW mit Prädiktor 3, Blöcke 512², Overviews 2 bis 256, 50 001² Pixel zu 1 m, EPSG:3035, Float32, nodata −9999 | M |
| HTTP der Datei | `206` auf Range, ETag und Last-Modified, `304` bedingt, `no-cache,must-revalidate`, **kein CORS** | M |
| Lizenz | „Für dieses Produkt gilt die Standardlizenz CC-BY-4.0“ mit Link; „Der öffentliche Zugang zu diesem Produkt unterliegt keinen Einschränkungen.“ | P, an einem Kachel-Metadatensatz des DTM (Stichtag 2022); Übersichtsseite „Unentgeltliche Produkte“ ebenso |
| Höhengenauigkeit | „grundsätzlich ± 0,50 m“, im Hochgebirge größere Abweichungen | P (Produktseite, Metadatensatz) |
| Stichtag | Stand der Daten an diesem Tag, nicht Datum der Befliegung; Aktualisierung je Gebiet bis zu 10 Jahre | P (Metadaten), S |
| Höhenbezug | österreichische Gebrauchshöhen, Adria (Triest) | P (Produktseite); EPSG des Höhenbezugs prüft das Messskript am Dateikopf |

### 2.2 Befund zu `adr/0023` §4.2

- Der dort unter „Suchtreffer“ verlinkte INSPIRE-Datensatz ist eine **Orthofoto**-Kachel (DOP), kein ALS-DGM. Die Lizenz des DGM ist trotzdem belegt, an einem eigenen Kachel-Metadatensatz des DTM [P].
- Einen Metadatensatz der **Serie** gibt es im GeoNetwork nicht sichtbar; belegt sind Kachel-Metadatensätze. Ob alle 330 Kacheln dieselbe Lizenz nennen, ist nicht geprüft.
- Folge: Nachtrag in `adr/0023` §4.2 mit der Umsetzung (Lizenz am Kachel-Metadatensatz, Link korrigiert).

### 2.3 Was offen ist und Otto lokal misst (§6 Schritt 1)

- Aufbau des Dienst-Feeds und eines Dataset-Feeds: Kinder der Einträge, Link-Typen, `georss`, `inspire_dls`-Kennungen, Kategorien (CRS), `updated`; ETag oder Last-Modified am Feed; `304` auf bedingte Anfragen.
- Aufbau aller 55 Dateien des jüngsten Stichtags über ihre Kopfzeilen (offen seit `adr/0023` §9.1): CRS, Größe, Typ, nodata, Blöcke, Overviews, `AREA_OR_POINT`; Größe der Dateien.
- Betreiber und Ort des Speichers bleiben unbelegt: `data_region: unknown` (`adr/0023` F7).

### 2.4 Ottos Messlauf 1 (16.11.2026, `bev-probe --all --headers`) [M]

| Was | Ergebnis |
|---|---|
| Dienst-Feed | `200`, `application/atom+xml`, rund 1,97 MB (unter der Grenze von 8 MiB je Antwort in `gateway`); **kein ETag, kein Last-Modified, kein `Cache-Control`** |
| Einträge | 672: 660 im bekannten Titelmuster (DTM und DSM, je sechs Stichtage 2019, 2021–2025 zu 55 Kacheln), 12 anderer Form |
| Kinder je Eintrag | `author`, `category` (EPSG:3035), `id`, `link` (`alternate` Dataset-Feed, `describedby` Metadaten), `rights`, `summary`, `title`, `updated`, `georss:polygon`, `inspire_dls:spatial_dataset_identifier_code`/`_namespace` |
| Dataset-Feed | `200`, ohne ETag; genau ein Eintrag mit genau einem Link `image/tiff` (alle 55), dazu `georss:polygon` und die Kennung |
| Dateipfad | weicht vom Suchtreffer ab (alle 55); Form misst Lauf 2 |
| Datei | `HEAD` `200`, Range `206`, ETag und Last-Modified, `no-cache,must-revalidate`; **`Access-Control-Allow-Origin: *`** (am 06.11. ohne CORS gemessen) |
| Größen | 0,09 bis 8,15 GB, zusammen 263,8 GB |
| Kopf aller 55 | EPSG:3035, 50 001², 1 Band, Float32, nodata −9999, 1 m, Blöcke 512², COG, LZW, `Area`; Overviews 2–256 (50 Dateien) bzw. 2–128 (5 Dateien) |

Folgen:
- **A1:** Die Fassung eines Laufs ist der Hash über den Inhalt (Kachel, Stichtag, Adresse, `updated`); eine bedingte Anfrage gibt es am Feed nicht.
- **CORS:** `access.cors: true`; „Download full scene(s)“ nimmt damit den Weg der Plattform für Quellen mit CORS (ZIP bzw. Dateien) statt `navigate`.
- **Kleinste Overview** 1:128 bei 5 Kacheln: Bei z7 (rund 830 m je Pixel) liest eine solche Datei rund das Doppelte; ändert an F5 nichts, die Messung in §6 Schritt 4 zeigt es.

### 2.5 Ottos Messlauf 2 (16.11.2026, `bev-probe --shape`) [M]

| Was | Ergebnis |
|---|---|
| Dienst-Feed zweimal | bytegleich, `<updated>` gleich (Form `…T##:##:##.######ZZ`) |
| 12 andere Titel | je sechs „Serie ALS DTM/DSM Höhenraster 1m Stichtag TT.MM.JJJJ“ |
| `rights` | Feed und alle 660 Kacheln: „Der öffentliche Zugang zu diesem Produkt unterliegt keinen Einschränkungen.“ — nur der Zugang, keine Lizenz |
| Kennung | `inspire_dls:spatial_dataset_identifier_code` ist der DOI der Kachel (`https://doi.org/10.48677/<uuid>`), alle 660; kein Namensraum |
| Polygon | Ecke des Kachelnamens unten links (0,068° gegen 0,49° bei oben links); das Polygon weicht aber bis 0,07° von der Zelle ab |
| `updated` | 55 verschiedene Werte für die 55 Kacheln des jüngsten Stichtags |
| Datei | derselbe Host, Pfad `/download/ALS/DTM/<JJJJMMTT>/ALS_DTM_<Kachel>.tif`, ohne Query, alle 55 |

Folgen (Otto, 16.11.2026): Lizenz im Eintrag aus den Kachel-Metadaten belegen, nicht aus `rights`; Footprint ist die 50-km-Zelle aus dem Kachelnamen; der Host steht in `hosts.yaml` (#360 gemergt).

---

## 3. Ausgangslage im Code [P]

- **Adapter:** `AdapterKind` in `catalog/registry.py:92` (`earth-search-v1`, `cop-dem-bucket`, `esa-worldcover-bucket`, `fsdi-stac-v1`); je Art eine `AdapterSpec` in `adapters/spec.py`. Die Bucket-Adapter bieten nur `materialize`. Vorlage ist `adapters/esa_worldcover_bucket.py`: Fassung aus einer Datei mit `If-None-Match`, Items von Hand gebaut, Abbruch über 1 % fehlend, XML mit `defusedxml`.
- **Materialisieren:** `python -m earthx.discovery.materialize <id> [--force]`; Abstand je Host nur für `fsdi-stac-v1` (`ENDPOINT_INTERVALS_S`, 1 s).
- **Stände:** `source.item_states` ist nur für den STAC-Adapter erlaubt (`spec.py:158`).
- **Ersatz:** `overview: substitute` ist allgemein (`api/tiler.py` `overview_scenes`, `frontend/src/overviewSubstitute.ts`). Die Ausdehnung des Ersatzes ist das Rechteck `spatial_extent.bbox` des Datensatzes; unter z7 liest die Route die GLO-30-Pyramide, zugeschnitten auf dieses Rechteck, und fällt auf die Dateien zurück, wenn sie nicht lesbar ist. Die Quellenzeile nennt `attribution_modified` von GLO-30.
- **Suchtreffer und eine Szene unter `min_zoom`:** Footprint-Auswahl (`adr/0032` Nachtrag 15.11.), für jeden Datensatz mit Ersatz und materialisierten Items.
- **`terrain` unter `min_zoom`:** rechnet auf den Pixeln des Ersatzes (#357).
- **CRS:** nirgends fest verdrahtet; das Item trägt `proj:code`, das Mosaik nimmt die Mehrheits-CRS, der Zuschnitt das Gitter der Quelle. EPSG:3035 → WGS 84 braucht keine Gitterdatei.
- **Fassung einer Eingabe:** ohne `file:checksum` der starke ETag der Datei über `HEAD` (`api/intake.py` `_version_of`).
- **Originale:** „Download full scene(s)“ lädt die Datei direkt von der Quelle; ohne CORS als `navigate` (der Browser lädt jede Datei selbst, unter ihrem Namen). Nichts wird umkodiert.
- **Hosts:** `backend/catalog/hosts.yaml` gibt es nicht; M5-36 ist nicht gemergt. Die Allowlist kommt aus `endpoint` und `asset_hosts` der Einträge.
- **Tests, die ein neuer Eintrag berührt:** Bewertungs-Set (`provisional` fällt weg), `test_onboarding_processing.py` (Operator je Datensatz, Aufbau je Adapter), `synthetic_chain.py`, Live-Smoke-Pflicht und Doppel in `test_live_smoke_dry_run.py`, `test_terrain.py` (Menge mit `terrain`), Prozess-Fixture `frontend/src/fixtures/processes/bev-als-dgm.json`, `test_api_listed.py` (regionale Einträge).

---

## 4. Umsetzung

### 4.1 Adapter `bev-atom` (nur Materialisieren)

- Neues Modul `adapters/bev_atom.py`, `AdapterKind.BEV_ATOM = "bev-atom"`, `AdapterSpec` wie die Bucket-Adapter (`materialize` allein). Ein allgemeiner ATOM-Adapter entsteht erst mit der nächsten ATOM-Quelle (`adr/0011` F6) bzw. als Extraktor in M5-21.
- **Ablauf:**
  1. `GET` des Dienst-Feeds (`source.endpoint`). Einträge nach dem Titelmuster in Modell, Kachel und Stichtag zerlegen; nur `DTM`. Ein Eintrag, dessen Titel nicht passt, zählt als `unknown`.
  2. Stichtag nach F1 wählen (Vorschlag: den jüngsten).
  3. Je Kachel des Stichtags den Dataset-Feed lesen (55 Anfragen, 1 s Abstand) und genau einen Link `image/tiff` erwarten, auf `asset_hosts`, mit Kachel und Stichtag im Pfad. Abweichung → `unknown`.
  4. Mehr als 1 % nicht ladbar → Abbruch (`MAX_NOT_LOADABLE_FRACTION`, wie DEM und WorldCover).
- **Fassung des Laufs:** SHA-256 über die sortierte Liste (Kachel, Stichtag, Adresse, `updated` des Eintrags), weil ein dynamischer GeoNetwork-Feed vermutlich kein brauchbares ETag hat. Liefert Ottos Messung ETag und `304` am Dienst-Feed, wird es wie bei WorldCover die bedingte Anfrage (Auslegung A1). Gleiche Fassung → `unchanged`, sonst `loaded`.
- **Neuer Stichtag:** Liegt der jüngste Stichtag nach `temporal_extent.end` des Eintrags, bricht der Lauf mit einem benannten Fehler ab („neuer Stichtag, Eintrag nachführen“). So bleibt der Eintrag in Git die eine Wahrheit; der Live-Smoke meldet den neuen Stichtag vorher (§4.6). Auslegung A2.
- **Rücksicht:** 1 s Abstand je Host (F3), höchstens 57 Anfragen je Lauf.

### 4.2 Items

| Feld | Wert | Herkunft |
|---|---|---|
| `id` | Kachelname mit Stichtag, `bev-als-dgm_<JJJJMMTT>_<Kachel>` | A |
| `geometry`, `bbox` | Zelle aus dem Kachelnamen in EPSG:3035, je Kante verdichtet nach WGS 84 umgerechnet; gegen `georss` des Feeds geprüft, falls vorhanden (wie WorldCover gegen sein Gitter) | A |
| `datetime` | Stichtag, 00:00 UTC | P (Titel) |
| `gsd`, `proj:code` | 1, `EPSG:3035` | M |
| Asset `dtm` | `href` der Datei, `type` COG, `roles: [data]` | M |
| `earthx:tile` | Kachelname | A |
| `sci:doi` | DOI der Kachel, wenn der Feed ihn trägt (F6) | P (Metadatensatz) |

### 4.3 Registry-Eintrag `bev-als-dgm`

| Feld | Vorschlag |
|---|---|
| `title` | `BEV ALS-DGM 1 m` |
| `description` | Digitales Geländemodell (DTM) Österreichs aus Airborne Laserscanning, 1 m, COG in Kacheln zu 50 km in ETRS89-LAEA (EPSG:3035), Höhen über Adria (Gebrauchshöhen), Stand zum Stichtag; Kacheln aus Befliegungen verschiedener Jahre |
| `keywords` | en: BEV, ALS, airborne laser scanning, lidar, digital terrain model, DTM, elevation, elevation model, terrain, Austria; de: Höhenraster, Geländemodell, Höhenmodell, Höhe, DGM, Laserscanning, Österreich |
| `category` | `elevation` |
| `providers` | BEV – Bundesamt für Eich- und Vermessungswesen, Rollen `producer`, `licensor`, `host` |
| `gsd` | `[1.0]` |
| `doi`, `citation` | `null`; Zitierangabe mit Herausgeber, Produkt, Stichtag und Produktseite (F6) |
| `data_class`, `format`, `georeferencing` | `raster-static`, `cog`, `geotransform` |
| `spatial_extent.bbox` | Vereinigung der 55 Zellen in WGS 84 (aus Ottos Lauf, §6) |
| `temporal_extent` | Stichtag 00:00 bis 23:59:59 UTC (F1 = 1) |
| `capabilities` | wie swissALTI3D: `terrain`, `value_masking`, `roi`, `band_math`, `interpolation`, `reprojection`, `normalization`, `ml_processing` true; `time_range`, `masking`, `quad_pol` false; `single_coverage_product` true |
| `license` | F2 |
| `legal_status` | `cleared` nach Ottos Bestätigung |
| `access` | anonym, `cors: false`, `account: none`, `token_free_checked_at` aus Ottos Lauf |
| `source` | `adapter: bev-atom`, `endpoint` = Dienst-Feed, `source_collection_id` = `ALS DTM` (Modell im Feed), `asset_hosts: [data.bev.gv.at]`, `item_holding: materialized`, `data_region: unknown`, `asset_keys: []`, `item_states: null`, `asset_checksum: null` |
| `coverage` | `local-sql`, `typical_footprint_km: 50`, `max_geotile_level` aus `max_geotile_level_for(50)` |
| `default_render` | wie swissALTI3D: `dtm`, 0–4 000 m (höchster Gipfel 3 798 m), `terrain`, `nearest` |
| `viewer` | `group_by` und `results_group_by` `[datetime]` (ein Stichtag, ein Mosaik), `min_zoom` F5, `max_zoom` 19 (z17 ≈ 0,8 m bei 47° N, zwei Stufen darüber wie swissALTI3D), `browse: full_resolution`, `overview: substitute`, `overview_substitute: cop-dem-glo-30` |
| `band_units` | `dtm: m` |
| `auxiliary_assets`, `search_filters`, `index_presets`, `true_color`, `notices` | leer |
| `search_capabilities` | `evaluate: false`, `aoi_coverage: true` |
| `limitations` | „The reference date is the state of the data on that day; a tile can combine surveys of different years.“ und „Heights are accurate to about ±0.5 m, less in high mountains.“ (Auslegung A3) |
| `maturity`, `health.status` | `stable`, `ok` |

Das Glossar kennt DGM/DTM schon (`glossary.yaml:19`); neu kommen „Höhenraster“ und „ALS / airborne laser scanning / Laserscanning“ in die passenden Gruppen.

### 4.4 Ein Bild bei jedem Zoom

- `min_zoom` nach F5; darunter zeichnet die Route der Übersicht GLO-30: von z7 bis `min_zoom` − 1 aus dessen Dateien (Budget 32 Dateien, 4 s), unter z7 aus dessen Pyramide, zugeschnitten auf die Ausdehnung von BEV (F4).
- Ob es von z7 an genügt: Eine Kachel z7 berührt höchstens 5 × 5 = 25 BEV-Kacheln, also innerhalb des Budgets; die kleinste Overview (rund 256 m, ein Block je Datei) liegt nahe am Pixel von z7 (rund 830 m bei 47° N) [A]. Bei z6 berührt eine Kachel bis zu rund 40 Dateien, über dem Budget. Daher Vorschlag `min_zoom` 7; Ottos Messung entscheidet (§6 Schritt 4).
- Alle Ansichten nutzen die vorhandene Mechanik ohne Änderung: Crop and merge und angeheftete Ebene über die Route ohne Auswahl, Suchtreffer und eine Szene über die Footprint-Auswahl, `terrain` auf den Pixeln des Ersatzes. Ein Test je Ansicht prüft, dass BEV unter `min_zoom` ein Bild bekommt (Registry-Werte und Route mit synthetischen Items).
- Statistik, Zuschnitt, Download und Jobs lesen nie den Ersatz (vorhandene Tests, BEV kommt in deren Parametrisierung).

### 4.5 Download im Originalformat

- „Download full scene(s)“ lädt die Original-COGs direkt vom BEV (kein CORS → der Browser lädt jede Datei selbst). Eine Datei wiegt nach der Messung einige GB (§6 Schritt 1 liefert die Größen); es gibt keine Umkodierung und keinen Umweg über die Plattform.
- Der AOI-Zuschnitt bleibt wie bei allen Datensätzen ein COG im Gitter der Quelle (EPSG:3035, Float32, 1 m), mit `ATTRIBUTION.txt`.

### 4.6 Live-Smoke

`backend/tests_live/test_bev_als_dgm_smoke.py`, Muster swissALTI3D: Dienst-Feed lesbar, jüngster DTM-Stichtag nicht nach `temporal_extent.end` (meldet einen neuen Stichtag), 55 Kacheln, ein Dataset-Feed mit genau einer Datei, eine Datei per Range `206` mit ETag. Etwa fünf Anfragen und 16 Bytes. Doppel in `test_live_smoke_dry_run.py`.

### 4.7 Tests (alle ohne Netz, Fixtures synthetisch)

- `tests/fixtures/bev_atom/`: synthetischer Dienst-Feed und Dataset-Feeds nach dem Aufbau aus Ottos Messung (Namen und Werte erfunden, Form wie gemessen).
- Adapter: Normalfall; Titel anderer Form, DSM, zweiter Stichtag; Dataset-Feed ohne, mit zwei oder mit fremdem `image/tiff`-Link; fremder Host; Kachelname außerhalb der Ausdehnung; 1 % → Abbruch; gleiche Fassung → `unchanged`; neuer Stichtag nach `temporal_extent.end` → Abbruch; kaputtes XML und XML mit Entitäten (`defusedxml`); `geometry` aus EPSG:3035 gegen bekannte Eckpunkte.
- Registry: Eintrag lädt streng; Ersatz geprüft; `terrain` angeboten.
- Kette Suche → Anzeige → Zuschnitt → `terrain` gegen eine synthetische COG in EPSG:3035 (neuer Zweig in `test_onboarding_processing.py` und `synthetic_chain.py`, wie `mini_lv95.py`).
- Übersicht unter `min_zoom` für BEV in Route und Footprint-Auswahl.
- Bewertungs-Set: `provisional` fällt weg; Q06, Q09–Q12, Q23, Q26 und die Gelände-Fragen werten BEV.

---

## 5. Schnitt (F7)

Vorschlag: **ein PR** (dieser), in Commits getrennt: Messskript und Plan, Adapter mit Tests, Eintrag mit Glossar und Bewertungs-Set, Live-Smoke, Nachträge in `adr/0023` und im Log. Wird er über rund 400 Zeilen ohne Fixtures, kommt der Eintrag in einen zweiten, gestapelten PR.

---

## 6. Was Otto lokal ausführt

Otto hat lokal kein Python; alles läuft über `docker compose` aus der Repo-Wurzel, in PowerShell wie in bash mit derselben Zeile. `--build` baut das Image des Backends neu, damit es den Stand des Branches hat.

**Schritt 1 — jetzt (Feed und Dateien messen):** Dienst `bev-probe` (Profil `measure`). Er nimmt das Image des Backends und bindet `scripts/m5-09-bev/` nur lesend ein; das Skript kommt nicht ins Image, braucht keine Datenbank und liest nur über `gateway`.

```powershell
docker compose run --build --rm bev-probe --all --headers
```

Rund zwei bis drei Minuten. Die Ausgabe nennt keine Adresse, keinen Kachelnamen und keinen DOI und kann so in den PR. Sie entscheidet A1 und die Form der Fixtures.

**Schritt 2 — nach der Umsetzung (Collection anlegen, Items laden):** `materialize` startet `catalog-load` selbst vorher.

```powershell
docker compose run --build --rm materialize bev-als-dgm
```

Danach die genaue Ausdehnung der 55 Kacheln (für `spatial_extent.bbox`, §9 A9), auch in PowerShell:

```powershell
"select st_extent(geometry) from pgstac.items where collection = 'bev-als-dgm';" | docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At'
```

**Schritt 3 — zweiter Lauf ohne Änderung (erwartet `unchanged`):**

```powershell
docker compose run --rm materialize bev-als-dgm
```

**Schritt 4 — `min_zoom` messen (Mitte Österreichs, ohne Ort im Repo):**

```powershell
docker compose run --build --rm measure-tiles bev-als-dgm --bbox 13.5,47.2,14.5,47.8 --zooms 5-10 --threads 4
```

**Schritt 5 — Live-Smoke:** läuft in GitHub Actions, nicht lokal (`.github/workflows/live-smoke.yml`, täglich und von Hand). Die Datei steht nach F8 in der Zeile der materialisierten Datensätze. Otto lässt ihn **nach dem Merge auf `main`** laufen (GitHub → Actions → „Live smoke“ → „Run workflow“), weil sich der Branch bei „Run workflow“ bei ihm nicht wählen lässt.

**Schritt 6 — im Browser:** Stack wie gewohnt starten (`docker compose up -d --build`), BEV wählen, von z3 bis z17 zoomen in Crop and merge, angehefteter Ebene, Suchtreffern und einer Szene; Hillshade unter und über `min_zoom`; „Download full scene(s)“ für eine Kachel.

---

## 7. Risiken

- **R1 Feed-Aufbau:** Der Adapter beruht auf dem Aufbau, den Schritt 1 misst. Weicht der Feed später ab, bricht der Lauf mit `UpstreamShapeError` ab, und der Live-Smoke meldet es.
- **R2 Rechteck des Ersatzes:** Österreich füllt sein Rechteck nur zu rund der Hälfte; unter `min_zoom` zeigt GLO-30 auch Teile der Nachbarländer, ab `min_zoom` nur noch Österreich (F4).
- **R3 Behördenserver:** Kein CDN, `no-cache`. Kacheln kalt über Apache sind langsamer als S3; das misst Schritt 4. Mit mehreren Instanzen gilt M5-35 F1 (M5-36, M5-37).
- **R4 Höhenbezug:** Die Messung am Übergang zu GLO-30 (Geoid EGM2008, Oberflächenmodell) zeigt bei swissALTI3D im Mittel +3 m; bei BEV ähnlich zu erwarten, im Standardbereich nicht sichtbar.

---

## 8. Fragen an Otto

**F1 — Welche Stichtage?** Jeder Stichtag ist ein vollständiger Stand für ganz Österreich (§2.1).
1. Nur den jüngsten (heute 15.09.2025); ein neuer Stichtag kommt mit einer Nachführung des Eintrags. Wie swissALTI3D F1 **(Empfehlung)**
2. Alle sechs in einem Datensatz, je Stichtag ein Mosaik, `time_range` an
3. Je Stichtag ein eigener Datensatz (wie WorldCover 2020/2021)

**F2 — Lizenz und Quellenangabe (Bestätigung durch Otto)?** Vorschlag: `CC-BY-4.0`, alle Erlaubnisse an, `attribution_required`, Stufe Processing; `attribution_unmodified` „© BEV, 2025“, `attribution_modified` „© BEV, 2025 (modified)“ (Form nach den BEV-Nutzungsbedingungen 2022, Punkt 2.3.3 „© BEV, JJJJ“, und `adr/0023` §7.2), dazu Lizenzname und Link wie bei den anderen Einträgen. Restzweifel [P]: Die Nutzungsbedingungen 2022 verbieten an anderer Stelle die Weitergabe von Originaldaten (2.3.7); 2.2.2 e) nimmt unentgeltliche Produkte davon aus. Eine neuere Fassung (AGB 01.02.2025) war nicht abrufbar.
1. Wie vorgeschlagen **(Empfehlung)**
2. Wie 1, Quellenangabe „Datenquelle: BEV – Bundesamt für Eich- und Vermessungswesen“
3. Vorerst nur Katalogeintrag mit Link, bis die AGB 2025 gelesen sind

**F3 — Host, solange M5-36 nicht gemergt ist?**
1. `data.bev.gv.at` wie heute über `endpoint` und `asset_hosts`, dazu 1 s Abstand im Materialisieren wie bei der FSDI; M5-36 übernimmt den Host in `hosts.yaml` **(Empfehlung)**
2. Auf M5-36 warten

**F4 — Ausdehnung des Ersatzes unter `min_zoom`?**
1. Das Rechteck `spatial_extent.bbox` wie bei swissALTI3D, ohne neuen Code **(Empfehlung)**
2. Auf die Vereinigung der Kachelumrisse zuschneiden (eigene kleine Aufgabe, gilt dann auch für swissALTI3D)

**F5 — `min_zoom`?**
1. Vorläufig 7 (Ersatz nur aus der GLO-30-Pyramide), endgültig nach Ottos Messung (§6 Schritt 4): 7, wenn eine kalte Kachel z7 unter 4 s bleibt, sonst 8 **(Empfehlung)**
2. Fest 8 (wie `adr/0032` §5.1 aus der Overview 1:256 abgeleitet)

**F6 — DOI je Kachel?** Jede Kachel hat einen eigenen DOI, die Serie keinen [P].
1. `sci:doi` am Item, wenn der Feed ihn trägt; der Datensatz ohne DOI, Zitierangabe mit Produktseite **(Empfehlung)**
2. Nur die Zitierangabe

**F7 — Schnitt?**
1. Ein PR, bei über 400 Zeilen der Eintrag in einen zweiten gestapelten (§5) **(Empfehlung)**
2. Von Anfang an zwei: Adapter, dann Eintrag

**Auslegungen (gelten bis Widerspruch):**
- **A1** Fassung des Laufs aus dem Inhalt der Feeds; bedingte Anfrage nur, wenn Schritt 1 sie am Dienst-Feed belegt.
- **A2** Neuer Stichtag nach `temporal_extent.end` → Lauf bricht ab, Eintrag wird nachgeführt.
- **A3** Zwei `limitations` (Stichtag, Genauigkeit), als Sätze ohne Marke.
- **A4** Nur DTM; das DSM im selben Feed bleibt draußen.

## 8a. Antworten von Otto (16.11.2026)

- **F1–F7: jeweils Option 1.**
- **F2, Einstufung durch Otto:** `CC-BY-4.0`, Stufe Processing. Beleg: BEV-Metadaten „Für dieses Produkt gilt die Standardlizenz CC-BY-4.0“; Einstufung als High-Value Dataset (Höhe). Quellenangabe „© BEV, 2025“ bzw. „© BEV, 2025 (modified)“.
- **F3:** M5-36 steht inzwischen vor M5-09 in der Reihenfolge (M5-Plan §6.3), ist aber nicht gemergt; der Host bleibt bis dahin bei `endpoint` und `asset_hosts`.
- **Messskript:** Otto hat lokal kein Python und nutzt PowerShell. Das Skript läuft deshalb als Compose-Dienst `bev-probe` (§6 Schritt 1); alle Befehle in §6 sind für Docker und PowerShell gefasst.

**F8 — neu, Live-Smoke in `.github/` (Erlaubnis nötig):** Der Live-Smoke läuft nur, wenn seine Datei in `.github/workflows/live-smoke.yml` steht (Liste der Dateien im Job der materialisierten Datensätze). `.github/` ändere ich nur mit Erlaubnis.
1. Ich trage `backend/tests_live/test_bev_als_dgm_smoke.py` in diesem PR in die bestehende Zeile ein (eine Zeile, sonst nichts) **(Empfehlung)**
2. Otto trägt die Datei selbst ein

**Antwort F8 (Otto, 16.11.2026): 1.** Erlaubnis für genau diese Änderung: `backend/tests_live/test_bev_als_dgm_smoke.py` in die bestehende Zeile von `.github/workflows/live-smoke.yml`, sonst nichts. Sie kommt im selben Commit wie die Datei des Smokes.

## 9. Umsetzung (16.11.2026)

Gebaut nach §4 mit den Antworten aus §8a und den Messläufen §2.4, §2.5. Wo die Umsetzung von §4 abweicht, gilt dieser Abschnitt.

- **Adapter** `adapters/bev_atom.py`, `AdapterKind.BEV_ATOM` (`bev-atom`), `AdapterSpec` nur mit `materialize`. Öffentlich für den Live-Smoke: `tiles_by_date`, `dataset_feed_of`, `doi_of`, `file_of`, `tile_item`, `cell_footprint`. Keine eigene Rücksicht im Adapter: Verbindungen und Abstand kommen aus `hosts.yaml` über `materialize` (M5-36).
- **`hosts.yaml`:** `data.bev.gv.at` mit 6 Verbindungen und 1 s Abstand wie die FSDI; Kacheln und Suche ohne Abstand (G3 von M5-36).
- **Eintrag** `backend/catalog/datasets/bev-als-dgm.yaml` nach §4.3; `cors: true` (§2.4).
- **Glossar:** zwei neue Gruppen „Laserscanning / ALS / airborne laser scanning / lidar“ und „Höhenraster / elevation raster“, getrennt vom Höhenmodell, damit Q06 BEV vor swissALTI3D findet.
- **Bewertungs-Set:** `provisional` an BEV entfällt; die Fragen mit BEV werten jetzt.
- **Tests:** Adapter (33, nachgebaute Feeds in der gemessenen Form), Kette Suche → Anzeige → Zuschnitt → Operator mit einer synthetischen COG in EPSG:3035 (`tests/earthx/readers/mini_laea.py`), Live-Smoke mit Doppel und drei Fehlerfällen, Messskript über seine Kommandozeile.
- **Live-Smoke** `tests_live/test_bev_als_dgm_smoke.py` in der Zeile der materialisierten Datensätze von `live-smoke.yml` (F8); er läuft nach dem Merge auf `main`.

**Auslegungen (gelten bis Widerspruch):**
- **A5 Item-ID** `ALS_DTM_<JJJJMMTT>_<Kachel>`: Modell, Stichtag und Kachel wie im Dateinamen, der den Stichtag nur im Pfad trägt.
- **A6 Footprint:** die Zelle aus dem Kachelnamen, 16 Punkte je Kante nach WGS 84 umgerechnet; das Polygon des Feeds wird nicht verwendet.
- **A7 Fassung des Laufs:** SHA-256 über Kachel, Stichtag, `updated`, Link des Dataset-Feeds und DOI der Einträge des gewählten Stichtags. Gleiche Fassung → `unchanged` nach einer Anfrage. Änderungen an älteren Stichtagen oder am DSM ändern sie nicht.
- **A8 Nicht ladbar:** eine Kachel ohne DOI der bekannten Form, ohne genau einen Dataset-Feed, ein Dataset-Feed ohne genau eine Datei auf dem Host unter dem Pfad ihres Modells, Stichtags und ihrer Kachel, oder eine Zelle, deren Mitte außerhalb der Ausdehnung liegt. `404`/`410` eines Dataset-Feeds zählt als fehlend; jeder andere Fehler bricht den Lauf ab. Über 1 % nicht ladbar (bei 55 Kacheln: schon eine) bricht ab.
- **A9 Ausdehnung:** vorläufig das Rechteck aller Zellen, die Österreich (Natural Earth) samt 2 km Rand berührt (`[9.05, 45.95, 17.85, 49.17]`); nach Ottos erstem Laden wird es die Vereinigung der 55 geladenen Kacheln (§6 Schritt 2).
- **A10 Neuer Stichtag:** ändert `temporal_extent` und das Jahr der Quellenangabe; der Live-Smoke meldet ihn, der Lauf hält bis dahin an (A2).
