# M5-07 — ESA WorldCover 2020 und 2021, Registry-Feld `data_region`: Plan-Schritt

**Status (06.11.2026):** Plan angenommen (Otto, 06.11.2026; Antworten in §8), Umsetzung im selben PR.
**Aufgabe:** M5-07 aus `docs/plans/m5/m5-discovery-und-suche.md` §6.1. **Stufe B.** Hängt von nichts ab; M5-08 und DS-04 warten auf den Merge.
**Grundlagen:** `adr/0023` §6.1, §7.2, §7.3, §8.3, §10 (F2, F6, F7); `adr/0022` §7.2 und F3; `adr/0009` (Weg des DEM); `plans/m3/m3-11b-dem-adapter.md`; `adr/0014` F6; `adr/0021` §2; `KLAERUNGEN.md` B8, B10, B11, B12, B13; `projektuebersicht.md` §5.

Belegstufen wie in `adr/0023`: **M** in dieser Sitzung gemessen, **P** am Primärdokument oder Quelltext gelesen (Stand `main` 5f43cc3), **S** Suchtreffer, **A** eigene Ableitung.

---

## 1. Ziel

1. `esa-worldcover-2020` und `esa-worldcover-2021` stehen als zwei statische Datensätze in der Registry. Ein Einmal-Befehl in `discovery` erzeugt je Stand die Items aus dem Kachelraster im Bucket und schreibt sie nach pgstac (Weg des DEM). Beide bestehen die Onboarding-Checkliste.
2. Jeder Datensatz der Registry trägt `data_region`. Ein Startcheck vergleicht den Wert mit `asset_hosts`, wo ein AWS-Host die Region nennt.

---

## 2. Messungen an der Quelle (06.11.2026) [M]

Aus der Sitzung mit `curl` und GDAL (`/vsicurl/`), nur Listings, Kopf einer Datei und die `readme.html` des Buckets. Kein Pixelblock gelesen.

- **Bucket-Wurzel:** `esa_worldcover_grid.geojson` (544 KB), `esa_worldcover_grid.fgb`, `esa_worldcover_grid_composites.fgb`, `readme.html`, Präfixe `v100/` und `v200/`.
- **Kachelraster:** 2651 Kacheln zu 3° × 3°, je Feature nur die Eigenschaft `ll_tile` (z. B. `S54E168`), Geometrie `Polygon`.
- **Dateien:** `v100/2020/map/` und `v200/2021/map/` halten je **2651** Dateien `ESA_WorldCover_10m_<jahr>_<version>_<ll_tile>_Map.tif`; das passt zum Raster. Daneben `docs/`, bei v200 auch `inputquality/` und `macrotiles/` (nicht Teil dieser Aufgabe).
- **Kopf einer Datei (v200):** `time_start` 2021-01-01, `time_end` 2021-12-31T23:59:59Z; `license` „CC-BY 4.0“; `copyright` „ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium“; Legende mit den elf Klassen; Farbtabelle in der Datei (0 transparent, 10 `#006400`, 20 `#ffbb22`, 30 `#ffff4c`, 40 `#f096ff`, 50 `#fa0000`, 60 `#b4b4b4`, 70 `#f0f0f0`, 80 `#0064c8`, 90 `#0096a0`, 95 `#00cf75`, 100 `#fae6a0`).
- **`readme.html` (v100):** Attribution „© ESA WorldCover project 2020 / Contains modified Copernicus Sentinel data (2020) processed by ESA WorldCover consortium“; Zitat mit DOI `10.5281/zenodo.5571936` (2020 v100). Für 2021 v200 nennt die Readme keine DOI; Kandidat `10.5281/zenodo.7254221` [S], prüfe ich vor dem Eintrag.
- **Region:** `esa-worldcover.s3.eu-central-1.amazonaws.com` (Region im Host); `copernicus-dem-30m.s3.amazonaws.com` antwortet mit `x-amz-bucket-region: eu-central-1` (Region nicht im Host); der Asset-Host von Sentinel-2 mit `us-west-2` (Region im Host).
- Unverändert seit `adr/0023` §6.1: Range `206`, ETag, bedingte Anfrage `304`, kein CORS.

---

## 3. Ausgangslage im Code [P]

- `DatasetConfig` hat kein `data_region`. `SourceInfo` trägt `adapter`, `endpoint`, `source_collection_id`, `asset_hosts`, `item_holding`. `DatasetConfig.__post_init__` reiht die Startchecks (`_check_source` u. a.).
- `AdapterKind` kennt `earth-search-v1` und `cop-dem-bucket`. Der DEM-Adapter (`adapters/cop_dem_bucket.py`) ist ein reiner Materialisierer: Liste aus der Quelle, Abgleich mit dem Bucket-Listing, Abbruch über 1 % Fehlstellen, bedingte Anfrage für „unverändert“. `discovery/materialize.py` schreibt in einer Transaktion.
- `DefaultRender` kennt nur `colormap_name` aus `access/colormaps.py`; eine Farbtabelle aus der Datei gibt es nicht. Der Viewer überschreibt `rescale` mit `/statistics` (F18).
- `.github/workflows/live-smoke.yml` nennt jede Live-Smoke-Datei einzeln (Zeile 59 und 82).

---

## 4. Umsetzung

### 4.1 `data_region` für alle Datensätze (eigene Commits, zuerst)

- **Feld** (Ort nach F1): Zeichenkette `<betreiber>:<ort>` oder `unknown` (`adr/0023` F7). Form geprüft: Kleinbuchstaben, Ziffern, Bindestrich, genau ein Doppelpunkt; sonst `ConfigError`.
- **Startcheck** (Umfang nach F2): Ein Asset-Host der Form `<bucket>.s3.<region>.amazonaws.com` verlangt `data_region == "aws:<region>"`. Zwei Asset-Hosts mit verschiedenen Regionen sind ein Fehler. Andere Hosts prüft der Check nicht (`adr/0023` §7.3).
- **Werte:**

| Datensatz | `data_region` | Beleg |
|---|---|---|
| `sentinel-2-c1-l2a` | `aws:us-west-2` | Host [P], Header [M] |
| `cop-dem-glo-30` | `aws:eu-central-1` | `x-amz-bucket-region` [M]; Host ohne Region |
| `esa-worldcover-2020`, `-2021` | `aws:eu-central-1` | Host [M] |

- **Ausgabe:** `earthx:data_region` an der Collection (`catalog/collection.py`), damit UI-05 es anzeigen kann. Keine Anzeige im Frontend in dieser Aufgabe.
- **Tests:** Form (leer, Großbuchstaben, zwei Doppelpunkte, ohne Doppelpunkt), Widerspruch zum Host, zwei Regionen, Host ohne Region, `unknown` mit AWS-Host (nach F2), jeder Registry-Eintrag hat einen gültigen Wert.

### 4.2 Adapter `esa-worldcover-bucket`

- Neues `AdapterKind.ESA_WORLDCOVER_BUCKET`, Modul `adapters/esa_worldcover_bucket.py`, `AdapterSpec` nur mit `materialize` (wie `cop-dem-bucket`).
- `source_collection_id` ist das Präfix des Stands (`v100/2020`, `v200/2021`); der Bucket hat keine STAC-Collection. Mehr unterscheidet die beiden Einträge im Adapter nicht.
- **Lauf** (Quelle der Liste nach F3): Kachelraster lesen, jeden `ll_tile` gegen das Muster `^[NS]\d{2}[EW]\d{3}$` prüfen (sonst Abbruch), Polygon gegen die 3°-Zelle aus dem Namen prüfen, Listing von `<präfix>/map/` abgleichen. Fehlstellen über 1 % brechen ab wie beim DEM. Bedingte Anfrage auf die ETag des Kachelrasters für „unverändert“.
- **Item:** ID aus dem Dateinamen ohne `_Map.tif`; `bbox` die nominale 3°-Zelle; `start_datetime`/`end_datetime` aus dem Jahr (1.1. bis 31.12.), `datetime` null; ein Asset `map` (COG, Rolle `data`). `inputquality` bleibt draußen.
- Alles über `gateway`; kein Asset wird geöffnet.
- **Tests** gegen einen synthetischen Bucket (Raster mit drei Kacheln, Listing als XML-Fixture): Normalfall, `304`, falscher Kachelname, Polygon passt nicht zum Namen, fehlende Datei unter und über 1 %, Datei ohne Rasterzelle, kaputtes GeoJSON, Präfix ohne Dateien, falscher `item_holding`.

### 4.3 Registry-Einträge (nach `adr/0023` §8.3)

Gemeinsamer Kern als Hilfsfunktion in `datasets.py`, zwei Aufrufe mit Jahr, Version und DOI.

- `data_class` statisch, `format` COG, Ausdehnung `(-180, -60, 180, 84)` aus dem Kachelraster [M], `temporal_extent` das Jahr.
- **Capabilities:** `roi` true; `time_range` false; `band_math` false; `reprojection` true; `interpolation` false (nur `nearest`, `adr/0014` F6); `masking` true; `value_masking` true; `normalization` false; `ml_processing` false (offen in M5-12); `quad_pol` false; `single_coverage_product` true.
- **Maske:** `MaskSource` mit Asset `map`, die elf Klassen mit den Namen aus dem Kopf der Datei, `suggested` leer, `cloud_classes` leer, `share_classes` leer. Ob der Operator `mask` eine Ebene mit sich selbst maskieren kann, prüft ein Test; falls nicht, kommt das als Frage zurück, nicht als Umbau.
- **Lizenz:** `CC-BY-4.0`, alle Flags wie `adr/0023` §7.2, Stufe Processing. Attribution unverändert und verändert nach F5.
- **Zugang:** `token_free_checked_at` 06.11.2026, `cors` false. `source.endpoint` `https://esa-worldcover.s3.eu-central-1.amazonaws.com`, `asset_hosts` derselbe Host, `item_holding` materialisiert.
- **Coverage:** `LOCAL_SQL`, `typical_footprint_km` 333.
- **Darstellung:** nach F4. `viewer` wie beim DEM (`group_by` `start_datetime`, `browse` volle Auflösung, `min_zoom` nach Messung der Kachelzeit, `max_zoom` 15).
- `band_units` `{"map": "class"}` oder leer (beim Bau gegen die Prüfung von `band_units` klären), `search_filters`, `index_presets`, `true_color` leer, `search_capabilities` `evaluate` false, `aoi_coverage` true.
- **Beschreibung:** Inhalt, Auflösung, Kachelung, Stand, und in beiden: „The 2020 and 2021 maps were made with different algorithm versions and are not directly comparable.“
- `maturity` stabil, `health` OK.

### 4.4 Onboarding-Checkliste (`projektuebersicht.md` §5)

| Punkt | Wie |
|---|---|
| 1 Beschreibung | §4.3 |
| 2 Coverage | `LOCAL_SQL` aus den materialisierten Items; Test, dass die Vollständigkeitsprobe `vollstaendig` liefert |
| 3 DOI | 2020 aus der Readme [M], 2021 vor dem Eintrag belegen |
| 4 Lizenz | Felder nach §4.3; Wortlaut bestätigt Otto (F5) |
| 5 Format | COG |
| 6 Anonymer Zugriff | §2 [M] |
| 7 Klasse, Flags | §4.3 |
| 8 Darstellung | F4 |
| 9 End-to-End | Operator-Lauf `mask` gegen eine synthetische Kachel (Fassung v2) |
| 10 Geprüft | Live-Smoke mit Marker `live_dataset` je Datensatz (F6) |

### 4.5 Live-Smoke und Materialisierung

- `backend/tests_live/test_worldcover_smoke.py`: bedingte Anfrage auf das Kachelraster gegen die gemessene ETag (`304`), eine Seite Listing je Präfix, ein Range-Read auf eine Kachel je Stand. Marker für beide IDs.
- Aufnahme in `.github/workflows/live-smoke.yml` braucht Ottos Erlaubnis (F6).
- Den Materialize-Lauf gegen die echte Quelle führe ich in der Sitzung einmal aus (lokale pgstac der Sitzung) und berichte Zahlen und Laufzeit im PR.

---

## 5. Nicht Teil dieser Aufgabe

- Anzeige von `data_region` und Legende der Klassen in der Oberfläche (UI-05).
- `inputquality`, `macrotiles`, weitere Jahre.
- Operatoren und Schnellrechnungen für WorldCover (M5-12).
- `access.account`, `legal_status` (erst mit dem YAML-Lader).

---

## 6. Schnitt und Umfang

Commits: (1) Feld `data_region` mit Startcheck und Werten; (2) Ausgabe an der Collection; (3) Adapter mit Tests; (4) Einträge; (5) Darstellung; (6) Live-Smoke; (7) Log und Doku.

Schätzung ohne Tests und Fixtures: rund 450 Zeilen (Adapter 200, Einträge 150, `data_region` 60, Rest 40). Das liegt über dem Richtwert; deshalb F7.

---

## 7. Risiken

- **Gleichzeitige Arbeit:** UI-05 fügt der Registry ein Feld hinzu und ändert das Frontend; F4 Option 1 berührt den Viewer. Wer später holt, löst Konflikte (Plan §6.2).
- **Stretch auf Klassen:** Ein Stretch aus `/statistics` verfälscht die Farben von Klassen. Ohne Lösung nach F4 ist Punkt 8 nicht erfüllt.
- **Maske auf sich selbst:** siehe §4.3.

---

## 8. Fragen an Otto — beantwortet am 06.11.2026

**Antworten Otto:** F1–F5 und F7 jeweils Option 1.
- **F5:** Der genaue Wortlaut je Jahr steht in der PR-Beschreibung; Otto bestätigt ihn vor dem Merge (`adr/0023` F2). DOI 2021 an der Quelle prüfen.
- **F6:** erlaubt, genau eine Zeile in `.github/workflows/live-smoke.yml` für WorldCover, sonst nichts in `.github/`.
- **Zusatz Onboarding:** Schlagworte deutsch und englisch (`adr/0026` F7, ab M5-07).


**F1 — Wo steht `data_region`?**
1. In `SourceInfo`, neben `asset_hosts`, gegen die der Check prüft **(Empfehlung)**
2. Direkt in `DatasetConfig` (Eigenschaft des Datensatzes, `architekturplan.md` §2)

**F2 — Startcheck bei AWS-Hosts ohne Region im Namen (DEM: `copernicus-dem-30m.s3.amazonaws.com`)?**
1. Nur Hosts mit Region werden geprüft; bei AWS-Hosts ohne Region muss der Wert mit `aws:` beginnen, die Region steht mit Messung im Kommentar **(Empfehlung)**
2. DEM auf den regionalen Host umstellen (Items neu materialisieren, alle `href` ändern sich)
3. Nur Hosts mit Region prüfen, sonst nichts

**F3 — Woher kommt die Liste der Kacheln?**
1. Kachelraster `esa_worldcover_grid.geojson`, geprüft gegen das Listing (wie `tileList.txt` beim DEM) **(Empfehlung)**
2. Nur das Listing, Zelle aus dem Dateinamen

**F4 — Darstellung der Klassen?**
1. Feste Farbtabelle aus der Datei als Colormap `esa-worldcover` in `access/colormaps.py`, ohne Stretch; der Viewer bietet bei Datensätzen ohne `rescale` keinen Stretch an (kleine Frontend-Änderung) **(Empfehlung)**
2. Der `tiler` nimmt die Farbtabelle zur Laufzeit aus der Datei (neues Feld, Eingriff in die Kachelroute)
3. Vorerst Graustufen, Farben mit UI-05

**F5 — Wortlaut der Attribution (vor dem Merge)?**
1. Wie die Quelle selbst, je Jahr: unverändert „© ESA WorldCover project {jahr} / Contains modified Copernicus Sentinel data ({jahr}) processed by ESA WorldCover consortium“, verändert derselbe Text mit Zusatz „(modified)“ **(Empfehlung)**
2. Anderer Wortlaut (bitte angeben)

**F6 — Live-Smoke in der CI?**
1. Ja, ich darf `.github/workflows/live-smoke.yml` um die neue Datei ergänzen (eine Zeile) **(Empfehlung)**
2. Nein, du trägst sie selbst ein; Punkt 10 bleibt bis dahin offen

**F7 — Ein PR oder zwei?**
1. Ein PR (dieser), Commits wie §6; Richtwert bewusst überschritten **(Empfehlung)**
2. Zwei PRs: erst `data_region` (M5-07a), dann WorldCover (M5-07b)

---

## 9. Umsetzung (06.11.2026)

Umgesetzt nach §4 mit den Antworten aus §8. Abweichungen und Befunde:

- **DOI 2021 [M]:** an Zenodo geprüft, `10.5281/zenodo.7254221` ist „ESA WorldCover 10 m 2021 v200“ (CC BY 4.0); `10.5281/zenodo.5571936` ist „ESA WorldCover 10 m 2020 v100“.
- **`data_region`** steht in `SourceInfo` (F1) und erscheint in der Collection unter `earthx:source.data_region`, nicht als neues `earthx:`-Feld (`architekturplan.md` 5.1, Zeile `earthx:source` ergänzt).
- **Maske:** Version 1 von `mask` nimmt die Ebene aus dem Ergebnis und ließe bei WorldCover nichts übrig. Version 2 (NM4-43c) behält sie; nur sie bietet das Panel an. Punkt 9 läuft deshalb mit `mask` v2 und Rezept-Version 2. Kein Umbau nötig.
- **Darstellung (F4):** Farbtabelle `esa-worldcover` im `tiler` (`access/colormaps.py`, Klassentabelle ohne Umkehrung, nicht in der Liste der Farbverläufe). Der Viewer zeigt bei einem Datensatz mit Farbtabelle und ohne `rescale` weder Bereich noch Farbverlauf-Auswahl (`drawsClasses`). Test: jedes deckende Pixel hat eine Farbe der Tabelle; mit Stretch nicht mehr.
- **Reprojektion:** Ohne `interpolation` listet die Prozessbeschreibung nur `nearest` und `mode` (Plan §6.4: was nicht geht, erscheint nicht). Vorher hätte erst die Annahme `bilinear` abgewiesen.
- **Registry-weite Tests:** Sie nahmen an, dass jeder Eintrag Band-Math, Interpolation und Normalisierung hat. Jetzt folgen sie den Flags des Eintrags.
- **Materialize-Lauf (§4.5):** über `gateway` aus der Sitzung nicht möglich (Proxy `403`, `gateway` pinnt die Adresse; derselbe Grund wie beim DEM-Smoke). Stattdessen lief der echte Adapter über einen Mock-Transport, der jede Anfrage per `curl` an die Quelle weiterreicht: je Stand **2651 Items, 0 fehlend, 0 unbekannt**, rund 3,5 s. In pgstac geschrieben ist nichts; der Lauf mit `python -m earthx.discovery.materialize esa-worldcover-2020` bzw. `-2021` steht bei Otto bzw. im Deployment aus.
- **Live-Smoke:** `backend/tests_live/test_worldcover_smoke.py` mit Ersatz im Trockenlauf; eine Zeile in `live-smoke.yml` (Job des Buckets). In der Sitzung scheitert er wie der DEM-Smoke am Proxy; er läuft in der CI.
- **Attribution bestätigt (Otto, 06.11.2026, `adr/0023` F2):** Wortlaut 2020 und 2021 wie in der PR-Beschreibung, also der Text der Quelle je Jahr, mit „(modified)“ für bearbeitete Daten; `CC-BY-4.0`, Stufe Processing.
