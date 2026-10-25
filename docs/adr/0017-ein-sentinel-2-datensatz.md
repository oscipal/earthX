# ADR 0017 — Ein Sentinel-2-L2A-Datensatz

- **Status:** **Entwurf**, Entscheidung bei Otto. Die Fragen stehen in §9.
- **Datum:** 2026-10-25
- **Aufgabe:** NM4-15 laut `docs/plans/querschnitt/nm4-15-ein-sentinel-2-datensatz.md`
  (Backlog-Punkt 15 in `docs/plans/nach-m4-backlog.md`).
- **Autonomiestufe:** C. Kein Produktivcode, keine Änderung an `backend/`,
  `frontend/`, Fixtures, `.github/`, `.claude/`, `CLAUDE.md` oder den
  Lock-Dateien. Die Umsetzung bekommt nach Ottos Entscheidung eine eigene
  Aufgabe.
- **Vorab fest:**
  - Otto will nicht mehrere Datensätze anbieten, die dasselbe zeigen, und den
    Zarr-Datensatz loswerden (Backlog-Punkt 15, 22.10.2026).
  - „Zarr im Viewer generell durch COG ersetzen (Daten umwandeln)“ ist
    verworfen; jeder Datensatz bleibt bei seiner Quelle (Backlog, „Verworfen“).
  - Die M2-Abnahme hängt nicht am Fortbestand der EOPF-Quelle; für das
    Kriterium „zweites Format“ genügt der Lesepfad gegen das synthetische
    Mini-Zarr aus M2-09a (Log 2026-09-20, `adr/0007` §12.13 F8 Auflage 2).
  - M4 ist abgenommen (Log 2026-10-24). Die Belege gelten als Stand von M4.
- **Grundlage:**
  - `ENTSCHEIDUNGEN_2026-09-18.md` §2, §4, §5; `KLAERUNGEN.md` B8, B9, B10,
    B12, B13.
  - `projektuebersicht.md` §2 (Prinzipien 3, 8, 9, 11), §5 (Checkliste,
    Punkte 5, 9, 10).
  - `architekturplan.md` 3.1, 5.2, 6.2.
  - `adr/0003` §10, §11; `adr/0005` §5 (Regeln I–III, Nachtrag M3-13);
    `adr/0007` §12; `adr/0014` §3.1, §4.6, §5.4, §15a (F7a), §15d (der erste der
    beiden Abschnitte mit dieser Nummer, M4-09);
    `adr/0015` §14d; `adr/0016` §12 (F4).
  - Pläne M2-09b, M2-10, M4-15, M4-18, M4-19, M4-20; Entscheidungslog bis
    25.10.2026.
- **Betroffen:** `backend/earthx/catalog/datasets.py` (Registry), Adapter
  `eopf_stac` und `eopf_sample_coverage`, Tests und Fixtures in Backend und
  Frontend, `backend/tests_live/test_eopf_smoke.py`, pgstac (Collection),
  `README.md`, `docs/cloud-umgebung.md`, `docs/projektuebersicht.md` §5,
  Backlog-Punkte 14 und 24.

---

## Methode und Belegstufen

Gelesen am 25.10.2026 auf dem Stand von `main` nach PR #188. Belegstufen wie
in `adr/0016`:

- **M:** in dieser Sitzung gemessen, die Anfrage steht im Text.
- **P:** am Primärdokument gelesen, mit Datei und Stelle; im Repo mit
  Pfad und Zeile.
- **P\*:** Primärdokument abgerufen, aber über das Abrufwerkzeug eines
  Hilfsagenten, das Seiten zusammenfasst. Zitate sind sinngemäß.
- **S:** Suchtreffer oder Zusammenfassung, Wortlaut nicht geprüft.
- **A:** eigene Ableitung, ein Argument und kein Beleg.

**Anfragen an Datenquellen:** nur STAC-Metadaten, keine Assets, keine AOI.
Diese Sitzung hat je Quelle die Collection und eine Suchseite mit einem Item
abgerufen (`curl`, §11), dazu die v2-Collection und die zwei Seiten von
Element84. Ein Hilfsagent hat Projektseiten und die FAQ des EOPF-Dienstes
abgerufen; die FAQ ist danach hier am PDF selbst gelesen.

---

## 0. Kurzfassung

1. **Empfehlung: Option 1.** `sentinel-2-l2a-zarr3` verlässt Registry und
   Katalog. Alles Formatgenerische bleibt: Zarr-Reader, `ZarrInfo`,
   CF-Skalierung (`store-cf`), die Zarr-Toleranz T1 ↔ T2 und die Tests auf dem
   synthetischen Mini-Zarr. Was nur dieser Quelle dient, geht mit (F2).
2. **Warum nicht Option 2 (zwei Quellen hinter einem Eintrag):** Die beiden
   Quellen haben verschiedene Item-IDs, Asset-Schlüssel, Skalierungswege,
   Zoomspannen und Fassungen. Ein Rezept gegen die eine lässt sich nicht gegen
   die andere rechnen, ohne dass sich Hash und Ergebnis ändern. Der „Rückfall“
   deckt nur Europa und den Nordatlantik und wenige Monate ab. Dazu fehlt jede
   Grundlage im Code: `adr/0005` föderiert je Collection, `SourceInfo` kennt
   genau eine Quelle (§3.9).
3. **Warum nicht Option 3 (Earth Search entfernen):** Die EOPF-Quelle nennt sich
   selbst „staging“, ist regional und kurz, hat keine Prüfsumme und keinen
   Quicklook (§3). Fast alle Tests, Prüfanleitungen und die M4-Belege stehen
   auf dem COG-Datensatz.
4. **Preis von Option 1:** Die Formatachse (Prinzip 3) und Checklisten-Punkt 5
   („Zarr > COG“) werden nur noch synthetisch belegt, bis eine operative,
   token-freie Zarr-Quelle kommt. Das ist eine bewusste Lücke mit
   Wiedervorlage (F4), keine stille.
5. **Alte Permalinks und `recipe.json`:** abweisen mit Grund, nicht umleiten
   (§8, F3). Eine Umleitung würde stillschweigend etwas anderes rechnen.
6. **Earth Search v2** bleibt ein eigener Punkt (Backlog 24) und ist von
   dieser Entscheidung unabhängig (§3.2).

---

## 1. Kontext und Frage

Seit M2 bietet die Plattform zwei Sentinel-2-L2A-Datensätze an:

| | `sentinel-2-c1-l2a` | `sentinel-2-l2a-zarr3` |
|---|---|---|
| Quelle | Element84 Earth Search v1 | ESA EOPF Sentinel Zarr Samples Service (EODC) |
| Format | COG je Band | Zarr v3, ein Store je Auflösungsgruppe |
| Seit | M1 (`adr/0003`) | M2 (`adr/0007`, F8) |
| Reifegrad im Eintrag | `stable` | `staging` |

Der Zarr-Datensatz kam als **Beweis für die Formatachse** („Quelle ≠ Format“,
`architekturplan.md` Grundsatz 3, M2-Ziel). Inhaltlich zeigt er dasselbe
Produkt wie der erste. Otto will ihn loswerden. Am Zarr-Datensatz hängen
Belege und Entscheidungen: `adr/0007` (zweites Format), die Zarr-Toleranz
T1 ↔ T2 in `adr/0014` §15d (Kriterium 1 der M4-Abnahme), Tests, Fixtures,
Prüfanleitungen und die Maske `SCL_20m:scl` (M4-18).

**Frage:** Wie kommt die Plattform zu genau einem sichtbaren
Sentinel-2-L2A-Datensatz, ohne Belege zu entwerten, Grenzen zu lockern oder
bestehende Links stillschweigend umzudeuten?

---

## 2. Kriterien

| # | Kriterium | Woher |
|---|---|---|
| K1 | Genau ein sichtbarer Eintrag für Sentinel-2 L2A | NM4-15 §1 |
| K2 | Die Quelle ist dauerhaft betrieben, nicht ausdrücklich vorläufig | Prinzip 11; `adr/0007` K9 |
| K3 | Abdeckung global, Archiv tief genug für Zeitreihen | `adr/0003` §4 (Kriterienmatrix) |
| K4 | Neue Szenen kommen zeitnah | `adr/0005` Regel II |
| K5 | Inhaltsbasierte Fassung je Asset, damit der Cache greift | `adr/0014` §3.1, §4.6; M4 Q11 |
| K6 | Ein Rezept, eine Rechnung: Bandnamen, Skalierung und Maske eindeutig | `adr/0014` F7, F7a; Prinzip 8 |
| K7 | Die Formatachse bleibt belegt | Prinzip 3; Checkliste Punkt 5 |
| K8 | Umbau klein und prüfbar, kein neues Konzept ohne Not | `CLAUDE.md` (PR-Richtwert) |
| K9 | Bestehende Permalinks und `recipe.json` werden ehrlich behandelt | Prinzip 9; `adr/0015` §14d |
| K10 | Grenzen unverändert: B8, B9, Modulgrenzen, keine neue Abhängigkeit | `CLAUDE.md`; `architekturplan.md` 3.1 |

---

## 3. Befunde

Die Anfragen aus §3.1 bis §3.7 stehen in §11 als Prüfanleitung; dort
lassen sie sich wiederholen.

### 3.1 Betriebsstatus des EOPF-Zarr-Dienstes — [M] und [P]

- **Die Collection nennt sich weiter „staging“ [M].** Titel
  `Sentinel-2 Level-2A (Zarr3 staging)`, STAC 1.1.0 (Abruf 25.10.2026, Q5).
- **Der Dienst ist ein Musterdienst, kein operativer [P].** FAQ des Betreibers,
  Stand 16.12.2025 (Q3): Zweck sei, „to provide sample data and support early
  users in exploring and testing the Zarr format for EO workflows. It is not a
  computing service.“
- **Operative Zarr-Produkte sind angekündigt, ohne Termin [P].** Dieselbe FAQ:
  „Operational generation of Zarr products is expected by late 2026 or early
  2027.“ Eine neuere Aussage mit Termin wurde nicht gefunden. Die CDSE-Meldung
  zum EOPF Zarr Explorer vom 25.06.2026 nennt das Format „upcoming“, ohne
  Termin [P\*] (Q4).
- **Keine Verfügbarkeitszusage [P].** Weder FAQ noch Projektseite nennen eine
  SLA; die S3-Buckets in us-west-2 sind „unofficial, and their future is
  unknown“ (Q3).
- **Archiv rollierend [M][P].** Die FAQ nennt „~three months backward from the
  current date“ und an anderer Stelle „a rolling one-year archive“ (Q3) —
  widersprüchlich. Gemessen reicht `extent.temporal` von 2026-07-16 bis
  2026-10-23, also gut drei Monate (Q5).
- **Laufzeit des Projekts unklar [S].** Projektseiten der Partner nennen
  verschiedene Enden (06/2026 und 12/2027); nicht am Primärdokument geprüft
  (Q8, Q9).

**Folgerung [A]:** Kommen operative Zarr-Produkte, kommen sie voraussichtlich
über das Copernicus Data Space Ecosystem und eine andere API als die heutige
Muster-STAC. Der Adapter `eopf_stac` wäre dann nicht der Zugang.

### 3.2 Earth Search v2 — [P] und [M]

- **v2 ist weiter Beta [P].** README von `Element84/earth-search` (Q1): „Earth
  Search STAC API v2 is currently in beta and may change before general
  release.“ Dazu allgemein: „This public API does not come with any guaranteed
  service.“
- **Kein Termin für das Ende von v1 [P].** Weder README noch die Seite der
  Collection (Q2) nennen einen. Stand unverändert gegenüber dem Log vom
  10.10.2026.
- **v2 ist noch nicht vollständig [P].** Die Collection-Seite nennt rund
  26,2 Mio. Items in v2 gegen rund 30,6 Mio. in v1 `sentinel-2-c1-l2a` (Q2).
- **Die Item-ID bleibt beim Wechsel gleich [P]** (Q2), die Collection heißt
  dann `sentinel-2-l2a`. Gemessen: v2 führt `sentinel-2-l2a` mit STAC 1.1.0,
  globaler Ausdehnung und Beginn 2015-06-27; `license` steht dort auf `other`
  statt `proprietary` (Q7) [M].

**Folgerung [A]:** Der Wechsel auf v2 ist ein Umbau des COG-Datensatzes
(Collection-ID, STAC 1.1, Lizenzwert), unabhängig davon, ob der Zarr-Datensatz
bleibt. Er ändert keine der Optionen hier.

### 3.3 Abdeckung und Aktualität — [M]

| | `sentinel-2-c1-l2a` (Q6) | `sentinel-2-l2a-zarr3` (Q5) |
|---|---|---|
| `extent.spatial` | `[-180, -90, 180, 90]` | `[-33.0, 34.2, 179.6, 72.1]` |
| `extent.temporal` | ab 2015-06-27, offen | 2026-07-16 bis 2026-10-23 |
| Neuestes Item, Aufnahme → `created` | 25.10.2026 08:08 → 10:45 UTC (rund 2,6 h) | 24.10.2026 14:32 → 25.10.2026 03:57 UTC (rund 13,4 h) |

Die Latenz ist je eine Stichprobe, keine Zusage; offizielle Angaben gibt es bei
keinem der beiden Betreiber. Die Ausdehnung des Zarr-Datensatzes deckt sich
mit `adr/0007` §12.6: keine Südhalbkugel, keine Tropen.

### 3.4 Skalierung — [M]

- **Earth Search:** Jedes Reflexionsband trägt `raster:bands` mit
  `scale 0.0001`, `offset -0.1`; `aot` und `wvp` `0.001`/`0`; `scl`, `cloud`,
  `snow` und `visual` ohne Skalierung (Item vom 25.10.2026, Q6).
- **EOPF Zarr3:** kein Asset trägt `raster:bands`, `raster:scale` oder
  `raster:offset` (Item vom 24.10.2026, Q5). Bestätigt den Befund vom
  02.10.2026; die Werte stehen nur als CF-Attribute im Store, deshalb die
  Ausnahme `store-cf` aus F7a.

Beide Wege ergeben Reflexion. Bleibt nur Earth Search, gilt für Sentinel-2
nur noch der Weg `item`; `store-cf` bleibt als generische Fähigkeit für künftige
Zarr-Quellen.

### 3.5 Bandnamen — [M]

| Band | Earth Search (Asset) | EOPF Zarr3 (Asset : Variable) |
|---|---|---|
| Rot, NIR | `red`, `nir` | `SR_10m:b04`, `SR_10m:b08` |
| NIR schmal | `nir08` | `SR_20m:b8a` |
| Szenenklassen | `scl` | `SCL_20m:scl`, `SCL_60m:scl` |
| Echtfarbe | `visual` (8 bit, fertig) | keines; zusammengesetzt aus `SR_10m:b04,b03,b02` |
| Quicklook | `thumbnail`, `preview` | keiner (`adr/0007` §12.7) |
| Atmosphäre | `aot`, `wvp` | `ATM_10m:aot`, `ATM_10m:wvp` |

Die Bandnamen im EOPF-Item stehen heute klein (`b04`); das Log vom 12.10.2026
notiert für die damaligen Items `B04`. Die Form hat sich also schon einmal
geändert [M].

### 3.6 Prüfsummen — [M]

- **Earth Search:** `file:checksum` (Multihash, Präfix `1220` = SHA2-256) an
  allen 23 Assets des Items, auch an `preview`, `thumbnail` und den
  `*_metadata` (Q6). Bestätigt `adr/0014` §3.1.
- **EOPF Zarr3:** an keinem Asset (Q5). Fassung bleibt `updated` am Item
  (`adr/0014` §4.6, Stufe 3).

### 3.7 Lizenz — [M]

Beide Collections tragen `license: proprietary` und den Link auf die Sentinel
Data Legal Notice (Q5, Q6). Keine neue Einstufung nötig; die Einstufung bleibt
ohnehin bei Otto.

### 3.8 Was im Repo am Datensatz hängt — [P]

**Produktivcode, datensatzspezifisch:** nur der Registry-Eintrag
`SENTINEL_2_L2A_ZARR3` (`backend/earthx/catalog/datasets.py:300–482`) und seine
Zeile in `REGISTRY` (`:668`). Er trägt Endpunkt und Collection, `asset_hosts`
(`data.eodc.eu`), Zoom 8–14, `maturity=STAGING`, `ZarrInfo`, die Maske
`SCL_20m:scl`, `band_units` und `results_group_by` mit `eopf:datatake_id`.

**Produktivcode, nur von dieser Quelle genutzt, aber ohne ihre ID:**

| Teil | Datei | Bemerkung |
|---|---|---|
| Adapter `EOPF_STAC_V1` | `adapters/eopf_stac.py` (281 Zeilen), `adapters/spec.py:120–124`, `catalog/registry.py:65` | konfigurationsgesteuert, aber nur ein Eintrag nutzt ihn |
| Coverage als Stichprobe | `adapters/eopf_sample_coverage.py` (206 Zeilen), `CoverageProvider.SAMPLE`, `api/coverage_route.py:69` | der einzige Anbieter dieser Art (`adr/0004` §5 Option 6) |

**Produktivcode, formatgenerisch (bleibt in jeder Option):**
`readers/zarr_reader.py` (793 Zeilen), `access/resolve.py`, `access/tiles.py`,
`catalog/registry.py` (`DataFormat.ZARR`, `ZarrInfo`, `_check_zarr`),
`processing/scaling.py` (`store-cf`), `api/processing_docs.py`
(`x-earthx-variable-separator`). Die ID steht dort nur in Kommentaren.

**Frontend:** kennt keine Datensatz-ID im Produktivcode; das prüft
`backend/tests/test_frontend_no_dataset_literals.py` gegen die Registry.
Formatbezogen sind `types.ts` (`DatasetFormat`), `processingOrder.ts` und
`download.ts`; sie bleiben.

**Tests, datensatzspezifisch** (Backend): `catalog/test_sentinel_2_l2a_zarr3.py`,
`api/test_tiler_zarr.py`, `api/test_tiler_zarr_group_addressing.py`,
`access/test_download_zarr.py`, `adapters/test_eopf_stac.py`,
`test_eopf_normalise.py`, `test_eopf_sample_coverage.py`, Teile von
`adapters/test_dispatch.py`, `test_spec.py`, `test_asset_bands.py`,
`catalog/test_mask_source.py`, `test_band_units.py`,
`test_onboarding_processing.py`, `integration/test_api_federating.py`,
`api/test_tiler_operator.py` (baut `ZARR_DATASET` als Kopie des Eintrags).
Fixtures: `backend/tests/fixtures/eopf_stac/` (synthetisch, von Hand).
Live: `backend/tests_live/test_eopf_smoke.py`.

**Tests, datensatzspezifisch** (Frontend): rund zwanzig Testdateien nutzen die
ID oder `SR_10m:…` als Beispiel, dazu die Fixtures
`fixtures/processes/sentinel-2-l2a-zarr3.json`,
`fixtures/orders/band-math-on-zarr-variables.json` und `fixtures/viewScenes.ts`.
Sie prüfen Frontend-Logik für Zarr-Variablen, nicht die Quelle.

**Tests, formatgenerisch:** `readers/test_zarr_reader.py`, `test_zarr_levels.py`,
`test_zarr_composite.py`, `test_zarr_decode_cf.py` auf den synthetischen
Mini-Zarrs (`tests/earthx/readers/mini_zarr*.py`, M2-09a).

**Wo die M4-Belege stehen:**

- **T2 ↔ T2L** (`runner/test_compare.py`, Beleg 1 von Kriterium 1): nutzt eine
  Kopie von `SENTINEL_2_L2A` mit der ID `synthetic` und das CF-Mini-Zarr.
  Hängt **nicht** am Zarr-Datensatz.
- **T1 ↔ T2 für Zarr** (`adr/0014` §15d):
  `catalog/test_onboarding_processing.py::test_the_tile_equals_the_job_on_the_native_level`
  läuft je Registry-Eintrag; der Zarr-Fall entsteht dort, weil
  `sentinel-2-l2a-zarr3` mit `format=ZARR` in der Registry steht (`:66`,
  `:139–140`), gerechnet wird auf `mini_zarr_cf`. **Fällt der Eintrag weg,
  fällt dieser Zarr-Fall still weg** (`ENTRIES = list(REGISTRY)`, `:70`),
  obwohl die Daten synthetisch sind. Dazu `api/test_tiler_operator.py`: Er hat
  schon eine eigene Test-Registry (`:61`), nimmt den Eintrag aber als Vorlage
  (`ZARR_DATASET = replace(SENTINEL_2_L2A_ZARR3, …)`, `:29`, `:50–51`); ohne ihn
  scheitert der Test laut beim Import. Beide brauchen einen Testeintrag mit
  `format=ZARR` (Regel II).

**Verhalten bei einer unbekannten `dataset_id` heute:**

| Stelle | Antwort |
|---|---|
| Kachel, Statistik, Info (`api/tiler.py:165–176`) | `404`, `no dataset '<id>'` |
| Coverage (`api/coverage_route.py:103–104`) | `404`, derselbe Text |
| Prozessbeschreibung (`api/processing_route.py:476–486`) | `400`, `no dataset '<id>'` |
| Auftrag und Schätzung (`api/intake.py:299–302`) | `422`, `no dataset '<id>'` |
| Rezept aus Queue oder Permalink (`api/intake.py:827–838`, `check_recipe_hosts`) | `400`, `no dataset '<id>'` |
| Fertiger Job: `recipe.json`, ZIP, Seitendateien (`api/processing_route.py:955–961`, `api/intake.py:543–544`) | kein Fehler; ohne Eintrag fehlen Attribution, Nutzungsbedingungen und `citation.bib`, im ZIP bleibt nur `aoi.geojson` |
| Permalink öffnen (`api/processing_route.py:1294–1301`) | `200` mit dem gespeicherten Auftrag; die ID wird nicht geprüft. Erst der Start scheitert mit `422` |
| Runner (`runner/recipe_file.py:87–98`) | Abbruch, „a dataset of the recipe is not known to this runner“ |
| pgstac (`catalog/load.py`, `catalog/pgstac.py:110–121`) | `load_registry` schreibt nur; eine Collection, die aus der Registry fällt, **bleibt** in pgstac stehen |

### 3.9 Was `adr/0005` für „zwei Quellen“ hergibt — [P]

`adr/0005` föderiert **je Collection**: Der `FederatingCoreCrudClient`
verzweigt an `earthx:source` einer Collection (Regel I). Eine Suche über
mehrere Collections fächert sich auf (Nachtrag M3-13); scheitert eine Quelle,
kommen die übrigen mit `incomplete_collections`. Einen Rückfall von einer
Quelle auf eine andere **für dieselbe Collection** gibt es weder im ADR noch im
Code: `SourceInfo` hat genau einen `adapter`, einen `endpoint` und eine
`source_collection_id` (`catalog/registry.py`, `datasets.py:389–400`). Option 2
wäre ein neues Konzept, keine Anwendung von `adr/0005`.

---

## 4. Optionen

### Option 1 — EOPF-Datensatz entfernen, Zarr bleibt generisch

`sentinel-2-l2a-zarr3` verlässt Registry, pgstac und Oberfläche. Der
Zarr-Lesepfad bleibt als Fähigkeit für künftige Zarr-Quellen und wird auf den
synthetischen Mini-Zarrs getestet. Varianten zum Rest (F2):

- **1a:** Adapter `eopf_stac` und Coverage-Stichprobe bleiben mit ihren
  synthetischen Fixtures, ohne Registry-Eintrag.
- **1b:** Was nur dieser Quelle dient (Adapter, Stichprobe, Fixtures,
  Live-Smoke), geht mit; die Git-Historie hält es.

*Für:* K1 bis K6 erfüllt, weil der verbleibende Datensatz der stärkere ist
(§5). Kleinster Umbau ohne neues Konzept (K8). Grenzen unverändert (K10).
*Gegen:* K7 nur noch synthetisch belegt. Der Zarr-Pfad sieht keine echte Quelle
mehr; Abweichungen einer künftigen Quelle (Konventionen, Sharding,
`multiscales`) zeigen sich erst mit ihr.

### Option 2 — Ein Eintrag „Sentinel-2 L2A“, zwei Quellen dahinter

Der Nutzer sieht einen Datensatz. Earth Search ist primär, EOPF Rückfall (oder
umgekehrt). Fällt die primäre Quelle aus, sucht und liest die Plattform aus der
zweiten.

*Für:* K1 an der Oberfläche erfüllt; K7 bliebe an einer echten Quelle belegt;
Robustheit gegen den Ausfall einer Quelle (Prinzip 11), soweit die zweite
dieselbe Szene führt.
*Gegen:*
- **Keine gemeinsame Identität [M][P].** Item-IDs (`S2C_T38TMK_20261025T080222_L2A`
  gegen `S2A_MSIL2A_20261024T143211_N0513_R139_T26WME_20261024T204702`, Q5, Q6),
  Asset-Schlüssel (`red`
  gegen `SR_10m:b04`), Maske (`scl` gegen `SCL_20m:scl`), Gruppierung
  (`s2:datatake_id` gegen `eopf:datatake_id`) und Zoomspanne (0–19 gegen 8–14)
  unterscheiden sich. Ein Rezept nennt Datensatz, Items und Assets (`adr/0014`
  §4.1); gegen die zweite Quelle gerechnet, ist es ein anderes Rezept mit
  anderem Hash. Ein stiller Wechsel verletzt Prinzip 8 und 9.
- **Ungleiche Rechnung [P].** Skalierung aus dem Item (`item`) gegen
  CF-Dekodierung des Stores (`store-cf`, F7a); Toleranz T1 ↔ T2 bitgleich (COG)
  gegen „bis 0,125 Quellpixel an der Grenze“ (Zarr, §15d); Fassung aus
  Prüfsumme gegen `updated` (§3.6).
- **Der Rückfall deckt wenig [M/P].** Die EOPF-Collection reicht nur von
  34° bis 72° N und wenige Monate zurück (§3.3); für den Rest der Welt und das
  Archiv gibt es keinen Rückfall.
- **Neues Konzept [P].** Doppelte Szenen beider Quellen müssten zu einer
  zusammengeführt werden (über Kachel, Datum und Plattform), die Seitenmarke
  müsste zwei Quellen tragen, Health-Checks fehlen bis M5. Das ist eine eigene
  Architekturentscheidung, kein Aufräumen (K8). Index-Knöpfe (Backlog 14)
  bräuchten Presets je Quelle innerhalb eines Eintrags.

### Option 3 — Earth Search entfernen, EOPF behalten

*Für:* K7 bliebe an einer echten Quelle; Checklisten-Punkt 5 wörtlich erfüllt.
*Gegen:* K2 bis K5 verletzt (§3.1, §3.3, §3.6): „staging“, regional, wenige
Monate, keine Prüfsumme, kein Quicklook (`adr/0007` §12.7). Fast alle Tests,
Fixtures, Prüfanleitungen und die M4-Belege stehen auf dem COG-Datensatz;
der Umbau wäre der größte. Widerspricht Ottos Wunsch, den Zarr-Datensatz
loszuwerden.

### Verworfen ohne eigene Option

**Nur ausblenden** (Eintrag bleibt in Registry und pgstac, die Datensatzwahl
zeigt ihn nicht): Die STAC-API zeigte ihn weiter (Prinzip 7, API-first), Pflege,
Live-Smoke und Tests blieben. Das ist der Aufwand von heute ohne den Nutzen.

---

## 5. Bewertung

| Kriterium | Option 1 | Option 2 | Option 3 |
|---|---|---|---|
| K1 ein Eintrag | ja | ja (nur an der Oberfläche) | ja |
| K2 Betrieb | Earth Search v1, ohne Zusage, aber kein Musterdienst (§3.2) | gemischt | Musterdienst, „staging“ (§3.1) |
| K3 Abdeckung, Archiv | global, seit 2015 | global über die primäre Quelle | 34°–72° N, gut drei Monate |
| K4 Aktualität (eine Probe) | rund 2,6 h | wie primär | rund 13,4 h |
| K5 Fassung | Prüfsumme je Asset | je Quelle verschieden | nur `updated` |
| K6 eine Rechnung | ja | nein | ja |
| K7 Formatachse | nur synthetisch | echt | echt |
| K8 Umbau | klein | groß, neues Konzept | groß |
| K9 Altbestand | abweisen mit Grund | Umleitung unmöglich ohne andere Rechnung | abweisen mit Grund, aber für den Hauptdatensatz |
| K10 Grenzen | unverändert | unverändert, aber zweiter Pfad je Datensatz | unverändert |

---

## 6. Empfehlung

**Option 1, Variante 1b**, mit fünf Regeln.

**Regel I — Generisch bleibt, quellgebunden geht.** Es bleiben: Zarr-Reader,
`DataFormat.ZARR`, `ZarrInfo`, `store-cf`-Skalierung, Variablen-Trenner im
Schema, die Zarr-Zweige im Frontend und alle Tests auf den Mini-Zarrs. Es
gehen: Registry-Eintrag, Adapter `eopf_stac` samt `AdapterKind.EOPF_STAC_V1`,
`eopf_sample_coverage`, die Fixtures `eopf_stac/`, der Live-Smoke. Grund für 1b:
Ein Adapter ohne Datensatz hat keinen Live-Smoke mehr und veraltet unbemerkt;
eine operative EOPF-Quelle käme über eine andere API (§3.1). Mit
`eopf_sample_coverage` verschwindet der einzige Anbieter einer ausgewiesenen
Stichprobe; `CoverageProvider.SAMPLE` und sein Platz in `IMPLEMENTED_PROVIDERS`
gehen mit und kommen mit der nächsten Quelle ohne Aggregation zurück
(`adr/0004` §5 Option 6 bleibt der Weg dafür; F2).

**Regel II — Der Zarr-Fall der Vergleichstests zieht um, statt zu entfallen.**
`test_onboarding_processing.py` und `test_tiler_operator.py` rechnen den
Zarr-Fall künftig auf einem **Testeintrag** mit `format=ZARR` und eigenem
`ZarrInfo`, nicht auf einem Eintrag der Registry. Vorbild ist `synthetic` in
`tests/earthx/runner/support.py:29–34`, dort für COG. Die Zarr-Toleranz aus
`adr/0014` §15d bleibt damit in der CI belegt. Ein
Wächtertest stellt sicher, dass der Zarr-Zweig ausgeführt wird, auch wenn die
Registry keinen Zarr-Eintrag hat.

**Regel III — Abweisen mit Grund, nicht umleiten** (§8). Die ID
`sentinel-2-l2a-zarr3` kommt in eine kleine Liste ausgeschiedener Datensätze
neben der Registry (ID, Datum, Hinweis auf den verbleibenden Datensatz, dazu
Lizenzblock und Zitat des alten Eintrags). Wer sie nennt, bekommt `410 Gone`
mit diesem Grund statt `404`/`422`/`400` „no dataset“. Lizenzblock und Zitat
halten die Seitendateien fertiger Jobs vollständig: Ohne sie fehlen nach dem
Umbau bis zu 7 Tage lang Attribution, Nutzungsbedingungen und `citation.bib`
im ZIP (§3.8), und die Attribution gehört zu jedem Download (§5 der
Projektübersicht).
Die Liste ist Daten, kein datensatzspezifischer Code; `REGISTRY` und die
ausgeschiedenen IDs dürfen sich nie überschneiden (Test).

**Regel IV — pgstac folgt der Registry.** Die Collection
`sentinel-2-l2a-zarr3` wird aus pgstac entfernt, sonst gäbe es zwei Wahrheiten
(B13 Punkt 3) und die STAC-API listete den Datensatz weiter. Weil das Daten
löscht, entscheidet Otto den Weg (F5).

**Regel V — Die Lücke bei der Formatachse ist benannt.** Checklisten-Punkt 5
und Prinzip 3 bekommen einen Nachtrag: Die Formatachse ist bis zur nächsten
operativen, token-freien Zarr-Quelle nur synthetisch belegt. Wiedervorlage:
sobald eine solche Quelle für irgendeinen Datensatz erreichbar ist (F4).

---

## 7. Folgen

### 7.1 Folgen von Option 1 (empfohlen)

| Bereich | Was | Größe [A] |
|---|---|---|
| Registry | Eintrag und Zeile in `REGISTRY` entfernen; Liste ausgeschiedener IDs mit Lizenzblock und Zitat neu (Regel III); `_config_of` und die Seitendateien fertiger Jobs lesen sie | klein |
| Adapter (1b) | `eopf_stac.py`, `eopf_sample_coverage.py`, Bindung in `spec.py`, `AdapterKind.EOPF_STAC_V1`, `CoverageProvider.SAMPLE` mit `IMPLEMENTED_PROVIDERS` (`api/coverage_route.py:69`) entfernen | rund 500 Zeilen weniger |
| API | `410` mit Grund an den Stellen aus §3.8 (Kachel, Coverage, Prozessbeschreibung, Auftrag); ein Permalink öffnet weiter mit `200` (§8) | klein |
| Frontend | ein `410` der Vorschau oder des Starts zeigt „Dataset retired“, der Grund aus dem Problem-Dokument steht im Tooltip; keine Datensatz-ID im Frontend | klein |
| Runner | eigene Meldung für eine ausgeschiedene ID statt „not known to this runner“ | klein |
| pgstac | Collection entfernen (Regel IV, F5) | klein |
| Backend-Tests | quellgebundene Tests und Fixtures entfernen; Zarr-Fall in `test_onboarding_processing.py` und `test_tiler_operator.py` auf Testeintrag (Regel II); Tests für `410`; `test_frontend_no_dataset_literals.py` unverändert | mittel, überwiegend Löschungen |
| Frontend-Tests | Beispiele mit der ID durch eine neutrale Test-ID ersetzen (etwa `synthetic-zarr`), Zarr-Logik bleibt geprüft; Fixtures `processes/sentinel-2-l2a-zarr3.json` und `orders/band-math-on-zarr-variables.json` umbenennen | mittel, mechanisch |
| Live | `tests_live/test_eopf_smoke.py` entfernen | klein |
| Doku | `README.md` (Datensatzliste, Beispiele, Attribution), `cloud-umgebung.md` §6 (EOPF-Hosts als Historie), `projektuebersicht.md` §5 Punkte 2 (Stichprobe ohne Anbieter), 5 und 9, Backlog 14 („COG gegen EOPF-Zarr“ entfällt) | klein |
| ADRs | Nachtrag in `adr/0007` und `adr/0014` (§15d bleibt gültig, Beleg jetzt synthetisch); M4-Belege bleiben als Stand von M4 | klein |
| Prüfanleitungen | M2-10, M4-17, M4-18 nennen den Zarr-Datensatz; sie bleiben als Stand ihres Meilensteins, neue Läufe nehmen `sentinel-2-c1-l2a` | keine Änderung |

**PR-Schnitt [A].** Das Löschen allein liegt über dem Richtwert von rund
400 Zeilen: Adapter rund 490, quellgebundene Tests rund 1600, Fixtures 135,
Registry-Eintrag rund 185 Zeilen. Vorschlag in drei PRs: (a) Liste
ausgeschiedener IDs, `410`, Seitendateien fertiger Jobs, pgstac und der Umzug
des Zarr-Falls auf den Testeintrag (klein, Verhalten); (b) Registry-Eintrag,
Adapter, Tests, Fixtures und Live-Smoke löschen (groß, fast nur Löschungen,
als benannte Ausnahme vom Richtwert); (c) Frontend-Tests und Doku.

### 7.2 Folgen von Option 2

Neues Registry-Konzept „Datensatz mit mehreren Quellen“, Zusammenführen
doppelter Szenen in Suche, Coverage und Zeitleiste, Seitenmarke über zwei
Quellen, Auswahl der Quelle je Rezept (im Rezept vermerkt, im Hash), Presets
und Maske je Quelle, Health-Check vor M5, Tests für jede Kombination. Eigener
ADR nötig. Altbestand wie in §8, weil eine Umleitung auch hier die Rechnung
ändert.

### 7.3 Folgen von Option 3

Wie §7.1 spiegelbildlich, aber für den Hauptdatensatz: Fixtures
`earth_search/`, Live-Smoke, Quicklook-Pfad (`BrowseMode.QUICKLOOK`),
`file:checksum` als Fassung, Coverage über `/aggregate`, die meisten
Prüfanleitungen und Frontend-Fixtures. Der Viewer verliert alles außerhalb
von 34°–72° N und das Archiv vor dem rollierenden Fenster.

### 7.4 In jeder Option

- **M4-Belege bleiben gültig.** Sie belegen den Stand von M4
  (`plans/m4/m4-20-abnahme.md`); ein späterer Umbau ändert sie nicht. Ein
  Nachtrag in `m4-20-abnahme.md` ist nicht nötig, der Log-Eintrag genügt.
- **`adr/0007` bleibt angenommen.** Sein Ergebnis (Zarr-Lesepfad an `gateway`)
  bleibt gebaut; nur die Wahl des Datensatzes (F8) wird abgelöst.
- **Lizenz unverändert.** Beide Quellen tragen dieselbe Sentinel Data Legal
  Notice (`datasets.py`, D18); keine neue Einstufung nötig.

---

## 8. Alte Permalinks und `recipe.json`

**Was es gibt:**

- **Permalinks** (M4-19e): Tabelle `earthx_permalink`, Frist **30 Tage**,
  Öffnen verlängert nie (`adr/0015` §14d). Der Auftrag liegt als JSON im
  Feld `body`; die Datensatz-ID wird beim Öffnen nicht geprüft (§3.8).
- **Rezepte und Ergebnisse:** Frist **7 Tage** (M4 Q10). Danach gibt es keinen
  Lauf mehr, auf den ein Link zeigen könnte.
- **`recipe.json`** im ZIP des Nutzers: ohne Frist, die eigene Datei des
  Nutzers. Der Runner prüft die Datensatz-ID gegen die Registry im Image
  (`adr/0016` F4); ein Image von vor dem Umbau rechnet weiter, solange die
  EOPF-Quelle antwortet.

**Umleiten scheidet aus [A].** Eine Umleitung auf `sentinel-2-c1-l2a` müsste
Item-IDs (über Kachel, Datum, Plattform), Asset-Schlüssel (`SR_10m:b04` →
`red`), Bandnamen im Ausdruck (`b04` → `red`, `b08` → `nir`), Maske und
Skalierungsweg übersetzen. Das Ergebnis wäre ein anderes Rezept mit anderem
Hash und anderen Pixeln (Prozessierungsstand, Resampling, Toleranz). Unter
einem Link, der das Original verspricht, verletzt das Prinzip 8 und 9.

**Abweisen mit Grund (Empfehlung):**

| Stelle | Verhalten nach dem Umbau |
|---|---|
| Permalink öffnen | `200` wie heute (der Auftrag gehört dem Nutzer). Vorschau und Start antworten mit `410`; die Oberfläche zeigt „Dataset retired“, der Grund aus dem Problem-Dokument steht im Tooltip. Das Frontend kennt dafür keine Datensatz-ID |
| Auftrag, Kachel, Coverage, Prozessbeschreibung | `410 Gone`, Problem-Dokument mit Grund und dem verbleibenden Datensatz |
| Fertige Jobs (bis 7 Tage nach dem Umbau) | Ergebnis, `recipe.json` und ZIP bleiben abrufbar; Attribution, Bedingungen und `citation.bib` kommen aus der Liste ausgeschiedener IDs |
| Laufende Jobs zum Zeitpunkt des Umbaus | laufen zu Ende; der Umbau wird in einem Fenster ohne laufende Jobs ausgerollt oder sie scheitern mit Grund (in der Umsetzung festzulegen) |
| Runner (neues Image) | Abbruch vor jeder Anfrage, Meldung „dataset retired on …“ statt „not known“ |
| STAC-API | Collection fehlt (`404`), wie jede unbekannte Collection (`adr/0005` Regel I) |

Weil Permalinks nach 30 Tagen ablaufen, gibt es 30 Tage nach dem Umbau keinen
gespeicherten Auftrag mit der alten ID mehr. Die Liste ausgeschiedener IDs
bleibt trotzdem, weil `recipe.json`-Dateien keine Frist haben.

Oberflächentext nur Englisch und kurz, Erklärung im Tooltip (UI-01 §4).

---

## 9. Fragen an Otto

**F1 — Welche Option?**
1. Option 1: EOPF-Datensatz entfernen, Zarr bleibt generisch mit synthetischen Tests **(Empfehlung)**
2. Option 2: ein Eintrag, zwei Quellen (eigener ADR, großer Umbau)
3. Option 3: Earth Search entfernen, EOPF behalten

**F2 — Was geht mit dem Datensatz (nur bei F1 = 1)?**
1. Variante 1b: Adapter `eopf_stac`, Coverage-Stichprobe samt `CoverageProvider.SAMPLE`, Fixtures und Live-Smoke gehen mit; Zarr-Reader und alles Formatgenerische bleibt **(Empfehlung)**
2. Variante 1a: Adapter und Stichprobe bleiben mit synthetischen Fixtures, ohne Registry-Eintrag; `SAMPLE` bleibt damit gebaut
3. Nur der Registry-Eintrag geht; alles andere bleibt, auch der Live-Smoke ohne Eintrag

**F3 — Alte Permalinks und `recipe.json`?**
1. Abweisen mit Grund: `410` und Liste ausgeschiedener IDs mit Lizenzblock und Zitat, Hinweis im Viewer (§8) **(Empfehlung)**
2. Abweisen wie jede unbekannte ID (`404`/`422`/`400`, „no dataset“), keine Liste; ZIPs fertiger Jobs verlieren bis zu 7 Tage lang Attribution und Zitat
3. Umleiten auf `sentinel-2-c1-l2a` mit Übersetzung (ändert die Rechnung, §8)

**F4 — Lücke bei der Formatachse (Prinzip 3, Checkliste Punkt 5)?**
1. Nachtrag in `projektuebersicht.md` §5: bis zur nächsten operativen, token-freien Zarr-Quelle nur synthetisch belegt; Wiedervorlage als Backlog-Zeile, ausgelöst durch eine solche Quelle (§3.1) **(Empfehlung)**
2. Wie 1, dazu ein Live-Smoke nur für den Zarr-Lesepfad gegen eine öffentliche Zarr-Quelle ohne Registry-Eintrag
3. Keine Änderung; Punkt 5 gilt je Datensatz, nicht für die Plattform

**F5 — Collection in pgstac entfernen?**
1. `load_registry` entfernt Collections föderierter Datensätze, die nicht mehr in der Registry stehen, im selben Lauf; Test dazu **(Empfehlung)**
2. Einmaliges Entfernen in einer Migration, `load_registry` bleibt nur schreibend
3. Stehen lassen (die STAC-API listet den Datensatz dann weiter)

**F6 — Reihenfolge zu Earth Search v2 (Backlog 24)?**
1. Unabhängig: NM4-15 jetzt umsetzen, v2 bleibt offen bis zum Termin **(Empfehlung)**
2. Zusammen mit der Umstellung auf v2 in einem Durchgang

---

## 10. Was offen bleibt

- Die Umsetzung (eigene Aufgabe nach F1–F6), Stufe B, weil sie API-Antworten
  (`410`) und pgstac ändert.
- Earth Search v2 (Backlog 24): Termin offen, siehe §3.2.
- Eine künftige Zarr-Quelle: Kandidaten erst prüfen, wenn F4 auslöst.

---

## 11. Prüfanleitung für Otto

Prüft die Befunde aus §3 an den Quellen selbst. Nur Metadaten, keine AOI,
Windows PowerShell 5.1 oder Browser.

Vorab, nur in Windows PowerShell 5.1 nötig: TLS 1.2 einschalten.

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$es = 'https://earth-search.aws.element84.com'
$eo = 'https://stac.core.eopf.eodc.eu'
```

**A. Collections (§3.1, §3.3, §3.7).** Erwartung in Klammern.

```powershell
$c1 = Invoke-RestMethod "$es/v1/collections/sentinel-2-c1-l2a"
$c1.title; $c1.license; $c1.extent.spatial.bbox; $c1.extent.temporal.interval
#   (Sentinel-2 Collection 1 Level-2A; proprietary; -180 -90 180 90; 2015-06-27…, offen)
$z3 = Invoke-RestMethod "$eo/collections/sentinel-2-l2a-zarr3"
$z3.title; $z3.license; $z3.extent.spatial.bbox; $z3.extent.temporal.interval
#   (… (Zarr3 staging); proprietary; Breite rund 34 bis 72; Beginn 2026-07-16, Ende vor wenigen Tagen)
$v2 = Invoke-RestMethod "$es/v2/collections/sentinel-2-l2a"
$v2.stac_version; $v2.license
#   (1.1.0; other)
```

**B. Ein Item je Quelle (§3.3 bis §3.6).**

```powershell
$i = (Invoke-RestMethod "$es/v1/collections/sentinel-2-c1-l2a/items?limit=1").features[0]
$i.id; $i.properties.datetime; $i.properties.created
$i.assets.red.'raster:bands'                     # (scale 0.0001, offset -0.1)
$i.assets.red.'file:checksum'                    # (beginnt mit 1220)
($i.assets.PSObject.Properties | Where-Object { $_.Value.'file:checksum' }).Count   # (23)

$z = (Invoke-RestMethod "$eo/collections/sentinel-2-l2a-zarr3/items?limit=1").features[0]
$z.id; $z.properties.datetime; $z.properties.created
$z.assets.PSObject.Properties.Name               # (SR_10m … SCL_20m, SCL_60m, product, zipped_product)
$z.assets.SR_10m.bands.name                      # (b02 b03 b04 b08)
$z.assets.SR_10m.'raster:bands'                  # (leer)
($z.assets.PSObject.Properties | Where-Object { $_.Value.'file:checksum' }).Count   # (0)
```

`created` minus `datetime` ist die Latenz der Stichprobe; sie schwankt.

**C. Im Browser (§3.1, §3.2).**

1. README von Earth Search öffnen (Q1), Abschnitt „Earth Search v2 (Beta)“:
   Satz „currently in beta and may change before general release“, kein Datum
   für das Ende von v1.
2. Seite der Collection (Q2), Abschnitt „v1 vs v2“: `sentinel-2-c1-l2a`
   „no longer exists“ in v2, Item-ID unverändert, Zahl der Items.
3. FAQ des EOPF-Dienstes (Q3), Stand 16.12.2025: „Operational generation of
   Zarr products is expected by late 2026 or early 2027“ und „It is not a
   computing service“.

**D. Kein Produktivcode im PR.**

```powershell
git fetch origin
git diff --stat origin/main...origin/claude/intelligent-edison-de5zc6
#   (nur Dateien unter docs/)
```

---

## 12. Quellen

Alle abgerufen am 25.10.2026.

- **Q1** Element84, Earth Search, README:
  https://github.com/Element84/earth-search/blob/main/README.md — [P]
- **Q2** Element84, Sentinel-2 L2A (`sentinel-2-l2a` und `sentinel-2-c1-l2a`):
  https://github.com/Element84/earth-search/blob/main/docs/collections/sentinel-2-l2a.md — [P]
- **Q3** EOPF Sentinel Zarr Samples Service, FAQ, Stand 16.12.2025:
  https://zarr.eopf.copernicus.eu/wp-content/uploads/2025/12/EOPF-Sentinel-Zarr-Samples_FAQ.pdf — [P]
- **Q4** Copernicus Data Space Ecosystem, „Welcome EOPF Zarr Explorer“, 25.06.2026:
  https://dataspace.copernicus.eu/news/2026-6-25-welcome-eopf-zarr-explorer-new-member-has-joined-copernicus-data-space-ecosystem — [P\*]
- **Q5** EOPF-STAC, Collection und erstes Item:
  https://stac.core.eopf.eodc.eu/collections/sentinel-2-l2a-zarr3 und `…/items?limit=1` — [M]
- **Q6** Earth Search v1, Collection und erstes Item:
  https://earth-search.aws.element84.com/v1/collections/sentinel-2-c1-l2a und `…/items?limit=1` — [M]
- **Q7** Earth Search v2, Collection:
  https://earth-search.aws.element84.com/v2/collections/sentinel-2-l2a — [M]
- **Q8** DLR, Projektseite EOPF Sentinel Zarr Samples Service:
  https://www.dlr.de/en/eoc/research-transfer/projects-missions/eopf-sentinel-zarr-samples-service — [S]
- **Q9** Eurac Research, Projektseite EOPF: https://www.eurac.edu/en/projects/eopf — [S]

Im Repo: `adr/0003` §10, §11; `adr/0005` §5; `adr/0007` §12.6, §12.7,
§12.13; `adr/0014` §3.1, §4.6, §15a, §15d; `adr/0015` §14d; `adr/0016` §12;
`plans/m4/m4-20-abnahme.md` §1, §8; Entscheidungslog 2026-09-20, 2026-10-02,
2026-10-10, 2026-10-12, 2026-10-24.
