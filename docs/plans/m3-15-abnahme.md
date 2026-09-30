# M3-15 — Abnahme von M3: Belege je Kriterium

**Ziel:** Otto kann M3 anhand dieses Berichts und des zugehörigen PR abnehmen,
ohne Code zu lesen.
**Ort im Repo:** `docs/plans/m3-15-abnahme.md`
**Grundlage:** `docs/plans/m3-dritte-quelle-und-interface.md` Abschnitt 5
(„Abnahme von M3“, Kriterien 1–9), Stand `main` bei Commit `6a69582`
(Merge von PR #108, 30.09.2026). Alle Aufgaben von M3-00 bis M3-24 außer M3-15
sind gemergt (PR #74 bis #108, Tabelle im Plan §3).
**Muster:** `docs/plans/m2-12-abnahme.md`.

Ergänzungen von Otto (30.09.2026), die dieser Bericht umsetzt: Belege je
Kriterium; wo nur Otto lokal prüfen kann, eine kurze Anleitung (Abschnitt 10);
ein Abschnitt „Nach M3 vorgemerkt“ (Abschnitt 12); keine Codeänderungen.

**Was dieser Bericht nicht ersetzt:** die lokale Prüfung durch Otto (Kriterien
1, 4 und 5 verlangen sie ausdrücklich) und die Prüfung gegen echte Quellen.
`gateway` erreicht die realen Quellen aus einer Cloud-Sitzung nicht (M2-13);
Messwerte gegen echte Quellen stammen aus den jeweiligen Aufgaben-PRs und sind
hier zitiert, nicht neu gemessen.

**Zusammenfassung des Ergebnisses**

| # | Kriterium | Ergebnis |
|---|---|---|
| 1 | Dritte Quelle suchbar, anzeigbar, ladbar; `readers` unverändert; keine Sonderfälle im Frontend | **erfüllt mit einer Abweichung** (`readers` einmal berührt, Abschnitt 1) und **wartet auf Ottos lokale Prüfung** |
| 2 | Onboarding-Checkliste grün je Datensatz | erfüllt |
| 3 | Gemischte Suche; `filter` nur wo es wirkt | erfüllt (`filter` ist nirgends ausgewiesen) |
| 4 | AOI-Upload, Ortssuche, `intersects` | erfüllt; wartet auf Ottos lokale Prüfung |
| 5 | Vollauflösung, Download folgt der Ansicht, native Auflösung, Maske | erfüllt; wartet auf Ottos lokale Prüfung |
| 6 | `adr/0011` von Otto freigegeben | erfüllt (angenommen am 30.09.2026) |
| 7 | Importregeln grün, kein Request außerhalb `gateway`, CI grün auf 3.12 | erfüllt |
| 8 | `adr/0012` liegt Otto zur Entscheidung vor | erfüllt und darüber hinaus umgesetzt (angenommen 26.09.2026, Garage seit M3-23) |
| 9 | Kein Download liefert eine beschädigte Datei | erfüllt |

---

## 1. Dritte Quelle: suchbar, anzeigbar, als Zuschnitt ladbar; `readers` unverändert; keine Sonderfälle im Frontend

**Die Quelle.** Copernicus DEM GLO-30 direkt aus dem AWS-Bucket
(`adr/0009`, angenommen 23.09.2026): zugleich dritter Datensatz und erste Quelle
ohne Such-API.

- Registry-Eintrag `cop-dem-glo-30`: `backend/earthx/catalog/datasets.py`
  (`COP_DEM_GLO_30`, ab Zeile 430; `REGISTRY` mit drei Einträgen).
- Adapter, der aus `tileList.txt` je Kachel ein Item baut:
  `backend/earthx/adapters/cop_dem_bucket.py` (`materialize_items`).
- Einmal-Befehl: `python -m earthx.discovery.materialize <dataset_id>`
  (`backend/earthx/discovery/materialize.py`), in Compose als Dienst
  `materialize` mit `profiles: ["materialize"]`, läuft nicht bei
  `docker compose up` mit.
- Items liegen in pgstac; die Suche geht über den bestehenden pgstac-Pfad
  (`earthx:source.item_holding`, M3-11a).

**Tests der Kette (synthetisch, kein Netz):**

- Laden: `backend/tests/integration/test_materialize_command.py` — u. a.
  `test_a_fresh_run_writes_every_item`,
  `test_a_second_run_with_the_same_version_changes_nothing`,
  `test_running_a_loaded_batch_twice_leaves_the_same_rows` (Idempotenz),
  `test_a_tile_no_longer_listed_is_removed`,
  `test_a_source_error_writes_nothing_and_records_no_run`.
- Adapter: `backend/tests/earthx/adapters/test_cop_dem_bucket.py`.
- Suche, Anzeige, Zuschnitt für den DEM als Kette (synthetischer COG
  `tests/earthx/readers/mini_dem.py`):
  `backend/tests/catalog/test_onboarding_endtoend.py`, Zeilen 84–231:
  `test_search_reaches_the_source_through_its_own_adapter`,
  `test_display_renders_a_tile_from_the_registrys_own_visualisation`,
  `test_the_clipped_download_is_a_zip_of_raster_and_notice`,
  `test_the_whole_chain_runs_for_this_entry`,
  `test_an_asset_on_a_host_the_entry_does_not_name_is_refused`.
- Suche nach Bounding Box und Kennung über pgstac:
  `test_materialize_command.py` (`test_a_bbox_over_one_tile_finds_only_that_tile`,
  `test_the_item_is_reachable_by_id`).
- Coverage als Fläche über die eigenen Items: PR #98 (M3-11c),
  `backend/earthx/api/coverage_route.py`, `backend/earthx/catalog/local_coverage.py`.

**Keine Sonderfälle im Frontend.**
`backend/tests/test_frontend_no_dataset_literals.py` läuft über `frontend/src`
(ohne Tests und Kommentare) und schlägt bei einer Datensatz-Kennung
(`test_no_dataset_id_literal_outside_a_comment`, Zeile 103) oder einem
quellenspezifischen Eigenschaftspräfix wie `s2:` (Zeile 113) an; die Prüfung ist
selbst geprüft (Zeilen 123–149). Die früheren Sonderfälle sind Registry-Felder in
`earthx:viewer`: `browse`, `quicklook_nodata_max`, `results_group_by`
(`plans/m3-12-frontend-sonderfaelle.md`, Log 26.09.2026), dazu `keywords`
(M3-10a) und `earthx:format` (M3-17).

**`readers` unverändert — Abweichung, Otto entscheidet.** Der Diff
`git diff ca379ad~1 HEAD -- backend/earthx/readers` (ab dem Merge-Vorgänger von
M3-00) zeigt **eine** Datei:

```
backend/earthx/readers/zarr_reader.py | 47 +++++++++++++++++++++++++++++++----
```

Herkunft: zwei Commits aus dem Review von PR #86 (M3-18, 24.09.2026): `53fa0c8`
(`part()` im Zarr-Komposit-Reader, weil der Zuschnitt nun über eine Bounding Box
statt über `feature` liest) und `0b507e3` (`nodata` nach `create_from_list`
erhalten). Das betrifft **nur den Zarr-Reader für mehrbandige Kompositen**.
`readers/cog.py` und damit der Pfad des DEM (COG) sind im Diff unverändert; der
DEM hat für seine Anbindung nichts an `readers` gebraucht. Trotzdem: Der
Wortlaut des Kriteriums („`readers` ist in M3 unverändert, Beleg über den Diff“)
trifft nicht buchstäblich zu, und das Log nennt die Abweichung nicht. Ich habe
sie nicht selbst als erlaubt eingestuft; Frage 1 in Abschnitt 11.

**Ergebnis:** Kriterium 1 erfüllt mit der genannten Abweichung; die lokale
Prüfung durch Otto (Abschnitt 10, Punkt A) steht noch aus.

---

## 2. Onboarding-Checkliste als Test grün für jeden Datensatz

`backend/tests/catalog/test_onboarding_checklist.py`:

- Zeile 255: `ENTRIES = list(REGISTRY)` — alle Registry-Einträge, nichts
  hartkodiert.
- `test_every_registry_entry_passes_the_checklist` läuft für alle drei
  Einträge: `[sentinel-2-c1-l2a]`, `[sentinel-2-l2a-zarr3]`, `[cop-dem-glo-30]`
  (Sammlung mit `--collect-only` in dieser Sitzung geprüft).
- Punkt 9 (Suche → Anzeige → Zuschnitt): `tests/catalog/test_onboarding_endtoend.py`
  mit der synthetischen Kette je Format (COG, Zarr, DEM).
- Punkt 10: `test_every_registry_entry_is_covered_by_the_live_smoke` liest die
  Marke `@pytest.mark.live_dataset` aus `backend/tests_live/` (D29). Der
  Live-Lauf selbst gehört in den nicht blockierenden Workflow `live-smoke.yml`
  und lief hier nicht.

**Ergebnis:** Kriterium 2 erfüllt.

---

## 3. Gemischte Suche über eigene und föderierte Collections; `filter` nur, wo es wirkt

`backend/earthx/api/mixed_search.py` (M3-13, PR #105). Tests:
`backend/tests/integration/test_api_mixed_search.py` (Klassen und Zeilen):

- eigene + föderierte Collection in einer Antwort:
  `TestNativePlusFederated` (234), zwei eigene Gruppen `TestTwoNativeGroups` (259);
- Paging über die Quellengrenze: `TestPagingAcrossTheBoundary` (290) —
  `test_the_union_of_every_page_matches_a_single_unbounded_page`,
  `test_a_source_that_runs_out_first_frees_its_share_for_the_other`;
- `open_collections` (M3-10b): `TestOpenCollections` (363);
- Ausfall, Zeitablauf, unlesbare Antwort einer föderierten Quelle →
  `incomplete_collections` statt `500`: `TestSourceFailure` (440);
  Ausfall der eigenen pgstac-Gruppe scheitert die ganze Anfrage (528);
- unbekannte Collection: `TestUnknownCollectionInAMixedList` (562), `404` vor
  jeder Anfrage an eine Quelle;
- Seitenmarke: `TestMixedPageTokenValidation` (618), Marke aus anderer Suche,
  fremde Quelle, Rückwärtsblättern, kaputtes Base64 abgewiesen;
- keine Koordinaten im Log bei fehlgeschlagener gemischter Suche:
  `TestNoCoordinatesInAFailingMixedSearch` (723).

**`filter`:** Die Entscheidung (Log 26.09.2026, M3-13): CQL2 bleibt aus. Damit ist
`filter` **an keiner Collection ausgewiesen**, und es wirkt nirgends
vorgetäuscht:
`TestDisabledExtensionsOnAMixedSearch.test_is_rejected_not_dropped` (575,
parametrisiert über `filter`, `query`, `fields`, `sortby`: abgewiesen, nicht
stillschweigend verworfen); `test_api_federating.py`:
`test_landing_page_never_advertises_filter_or_sort` (113),
`test_a_filter_parameter_is_rejected_not_dropped` (144). `query` und `fields`
waren auf föderierten Collections still weggefallen (K8) und sind seit M3-13
ebenfalls abgeschaltet.

**Ergebnis:** Kriterium 3 erfüllt. Der Wortlaut „nur dort ausgewiesen, wo es
wirkt“ ist damit der Grenzfall „nirgends“; eine CQL2-Unterstützung je Collection
bleibt eine spätere Entscheidung (Abschnitt 12).

---

## 4. AOI aus GeoJSON, KML, Shapefile über das Backend; Ortssuche; `intersects`

**Upload** (`POST /aoi/upload`, M3-06a #89, Frontend M3-06b #96):
`backend/tests/earthx/access/test_aoi_upload.py` — GeoJSON gültig und
fehlerhaft, `test_too_many_points_rejected` (149), `TestKML` (189) mit
`test_external_entity_rejected` (198), Shapefile mit `test_missing_prj_rejected`
(242), `test_reprojects_from_prj` (259), `test_zip_bomb_rejected` (317),
`test_too_many_zip_members_rejected` (329), `test_kml_extension_dispatches` (358);
Route: `backend/tests/earthx/api/test_aoi_upload_route.py`
(`test_valid_geojson_returns_the_geometry`,
`test_valid_shapefile_returns_the_geometry`,
`test_never_spools_to_a_real_temp_file`, Zeile 91: nichts wird auf Platte
geschrieben). Frontend: `frontend/src/aoiFile.ts` ruft die Route auf.

**Ortssuche** (`POST /geocode`, M3-07a #102, Frontend M3-07b #103), standardmäßig
aus (`EARTHX_GEOCODER_URL` leer → `503`):
`backend/tests/earthx/adapters/test_nominatim.py` — Punkt ohne Umriss (134),
kein Treffer (149), Cache-Treffer erreicht weder `gateway` noch Ratenfenster
(223), Ratengrenze (250, 258), Zeitablauf (274), `403` (286);
`backend/tests/earthx/api/test_geocode_route.py` — leere Eingabe `422` (117),
Treffer mit Attribution (94), `429` → `503` (169), Zeitablauf `504` (192),
Ratenfenster nicht erreichbar (209), **kein Suchtext und kein Ortsname im Log**
(`test_no_search_text_or_result_name_reaches_the_log`, 218).
Die OSM-Attribution steht unter den Treffern (`frontend/src/placeSearch.ts`,
„© OpenStreetMap contributors“) und im ZIP (`ATTRIBUTION.txt`, Test
`test_a_place_search_aoi_adds_one_line` in `access/test_download.py`, Zeilen
368–396, sowie `test_download_zarr.py:109`). Die Latenz je `curl` steht im PR
#102 (Messung aus der Aufgabe, hier nicht neu).

**`intersects` und `ids`** (M3-08 #76):
`backend/tests/integration/test_api_federating.py` — `ids` und `intersects` per
GET und POST erreichen die Quelle (174–207), kaputtes JSON in `intersects` ist
`400` (232); in der gemischten Suche `TestIntersectsAndIdsOnAMixedSearch` (589);
Cache-Schlüssel: `backend/tests/earthx/adapters/test_search_params.py`.

**Ergebnis:** Kriterium 4 erfüllt; die lokale Prüfung (je eine Datei jedes
Formats, ein Ort, eine Polygon-Suche) steht aus (Abschnitt 10, Punkt B).

---

## 5. Vollauflösung zeigt den Zuschnitt; keine AOI in Kachel-URLs oder Logs; Download folgt der Ansicht, nativ, mit Maske

**Zuschnitt in der Ansicht** (M3-09 #84): `frontend/src/aoiClip.ts`, Test
`frontend/src/aoiClip.test.ts` — `never puts an AOI coordinate into the wrapped
URL` (Zeile 45): Die Kachel-URL trägt keine Koordinate, die AOI verlässt den
Browser nicht; der Zuschnitt geschieht im Browser je Kachel. Die Kachelroute
nimmt nur `dataset`/`item`/`asset` und keinen freien `url`
(`test_tiler.py::test_no_endpoint_declares_a_url_parameter`, unverändert seit
M2).

**Keine AOI im Log** (M3-16 #85): `backend/tests/test_logging.py` — Zeile 306
(`test_a_request_with_a_query_string_writes_one_line_without_it`), 345 und 368
(gültige und fehlerhafte AOI im Request landet nicht im Log), 89 (auch ein ohne
Flag gestarteter Server), 162–207 (`summarize_geometry`).

**Download folgt der Ansicht** (M3-17 #88): `frontend/src/download.test.ts` deckt
die Fälle aus P19 ab: Zuschnitt aus der Vollauflösung (93), mehrere angeheftete
Szenen ohne doppelte Asset-Einträge (103), „Crop & merge to AOI“ schneidet immer
zu (203), „View full selection“ einer COG lädt die Originale, mit oder ohne AOI
(187, 208), einer Zarr-Quelle ohne AOI ist der Knopf deaktiviert (192, 213); die
Angabe COG/Zarr kommt aus der Registry (239–255, „unbekannt gilt nie als COG“);
Originale nur von Hosts der Registry über https (273–294).

**Native Auflösung, Deckel, Maske** (M3-18 #86, P20, P21):
`backend/tests/earthx/access/test_download.py` (Deckel 136–148, keine
Verkleinerung 213, Faktor 223, Abweisung mit lesbarer Meldung 276),
`backend/tests/earthx/api/test_download_route.py` (Abweisung nennt den kleinsten
passenden Faktor 182, unbekannter Faktor 192, explizite Wahl im Dateinamen 196),
`backend/tests/earthx/access/test_download_mask.py` (schräges Polygon lässt die
Datendatei unverändert 130, Maske innen/außen 174, Rechteck ist pixelgleich 250,
Daten und Maske stimmen überein 269).

**Ergebnis:** Kriterium 5 erfüllt; die Übereinstimmung von Karte und Datei
prüft nur Otto lokal (Abschnitt 10, Punkt C).

---

## 6. `adr/0011` (Adapter-Interface) von Otto freigegeben

`docs/adr/0011-adapter-interface.md` (M3-14, PR #107). Otto hat am 30.09.2026
**F1–F9 je Option 1** angenommen (`ENTSCHEIDUNGSLOG.md`, Zeile
„`adr/0011` angenommen (Otto)“; Status der Entwurfszeile: „angenommen am
2026-09-30“). Der Umbau ist der erste Schritt von M4 (M4-01a, M4-01b), siehe
Abschnitt 12.

**Ergebnis:** Kriterium 6 erfüllt.

---

## 7. Importregeln grün, kein ausgehender Request außerhalb von `gateway`, Pflicht-CI grün auf Python 3.12

- `lint-imports`: **12 von 12 Verträgen KEPT** (Lauf dieser Sitzung, Ausgabe
  siehe Abschnitt 9). Der Befehl braucht `PYTHONPATH=backend`, wie in der CI
  (`.github/workflows/ci.yml`, Job `import-boundaries`); ohne meldet er
  „Could not find package 'earthx'“ — die Befehlszeile in `CLAUDE.md` nennt das
  nicht (Frage 2).
- Kein Request außerhalb `gateway`: `http-only-in-gateway` (Vertrag) und
  `backend/tests/earthx/test_no_outbound_outside_gateway.py` (AST-Prüfung, wie
  in M2). Der DEM-Adapter und die Ortssuche gehen beide über `gateway`
  (`adapters/cop_dem_bucket.py`, `adapters/nominatim.py`).
- Python 3.12: `PYTHON_VERSION: "3.12"` in `ci.yml`,
  `backend/tests/test_python_version.py` (Interpreter und jede Stelle nennen 3.12).
- **Pflicht-CI** auf dem Stand von PR #108 (Kopf `d3c090f`, letzter M3-PR): alle
  vier Checks `success` — Compose topology, Frontend — lint, types and tests,
  Module boundaries (import-linter), Backend — lint and tests. Für den
  Merge-Commit `6a69582` habe ich die CI nicht abgefragt; die CI dieses PR
  läuft neu.

**Ergebnis:** Kriterium 7 erfüllt.

---

## 8. `adr/0012` (Ersatz für MinIO) liegt Otto zur Entscheidung vor

`docs/adr/0012-objektspeicher.md` (M3-20, PR #94/#97). Otto hat am 26.09.2026
entschieden: Garage ersetzt MinIO (Log, Zeile „M3-20: ADR-Entwurf …“, Status
„fest“). Umgesetzt in M3-23 (#100): Dienst `objectstore` mit
`dxflrs/garage:v2.4.1` per Digest in `docker-compose.yml`, `S3_*`-Variablen,
Zugangsdaten beim ersten Start erzeugt (nicht im Repo), Tests
`backend/tests/compose/test_objectstore_bootstrap.py` (Erzeugen der Dateien,
Import des Schlüssels, `..._never_contains_any_credential_...`). Der Job
`Compose topology` war auf PR #108 grün. Den Weg vom eigenen Code zum
Objektspeicher legt M4 fest (`adr/0012` F5).

**Ergebnis:** Kriterium 8 erfüllt (über die Vorlage hinaus entschieden und
umgesetzt).

---

## 9. Kein Download liefert eine beschädigte Datei

M3-22 (#93). Ursache laut Log (26.09.2026): ein Use-after-free im Leseweg der
**Tests** (`MemoryFile(bytes)`), nie eine defekte Datei beim Nutzer; die beiden
Log-Zeilen zur Korruption stehen auf „ersetzt“. Trotzdem prüft der Code jede
erzeugte Datei vor dem Ausliefern (`_verify_asset_crop`,
`backend/earthx/access/download.py`, Zeile 1027), einmal neu schreiben, sonst
`500` mit Request-ID; Kompression wieder DEFLATE.

- `backend/tests/earthx/access/test_download_verification.py`:
  `test_a_freshly_written_crop_passes` (69), `test_a_truncated_data_file` (77),
  `test_a_tile_that_does_not_decode` (82), `test_a_mask_on_another_grid` (114),
  `test_a_mask_with_values_other_than_0_and_1` (124).
- Stresstest `backend/tests/earthx/access/test_download_stress.py`: Vorgabe 50
  Wiederholungen (`EARTHX_DOWNLOAD_STRESS_RUNS`), läuft im Backend-Job der CI
  (Teil von `pytest`).

**Ergebnis:** Kriterium 9 erfüllt.

---

## 10. Von Otto lokal zu prüfen (Windows / PowerShell)

Voraussetzung: Docker Desktop läuft. Im Repo-Wurzelverzeichnis:

```powershell
git fetch origin
git checkout main
git pull origin main
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build --remove-orphans
docker compose ps
```

`docker compose ps`: `postgres`, `objectstore`, `api`, `tiler`, `worker`,
`harvester` sollen `healthy` sein; die Einmal-Dienste (`pgstac-migrate`,
`catalog-load`, `objectstore-secrets`, `objectstore-init`) beenden sich.
Zum Aktualisieren des Katalogs nach M3 hilft ein neuer Lauf von
`catalog-load` (ein normales `up` erledigt das). `--remove-orphans` räumt einen
alten `minio`-Container aus der Zeit vor M3-23 weg.

DEM laden (einmalig, rund 30 Anfragen an den Bucket):

```powershell
docker compose run --rm materialize cop-dem-glo-30
```

Ortssuche einschalten (optional, nur für Punkt B): in `.env` die Zeile
`EARTHX_GEOCODER_URL=https://nominatim.openstreetmap.org` setzen, dann
`docker compose up -d --build api`.

Viewer:

```powershell
cd frontend
npm install
npm run dev
```

danach `http://localhost:5173`. Prüfschritte:

**A. Dritte Quelle (Kriterium 1).** Nur den DEM-Knopf wählen, eine kleine AOI
(Rechteck) über Land zeichnen, suchen: Der DEM erscheint bei jedem Zeitraum mit
dem Hinweis auf den Aufnahmezeitraum, ohne Quicklook direkt als Zuschnitt in
voller Auflösung. Die Coverage-Heatmap zeigt für den DEM eine Fläche. „Download“
liefert ein ZIP mit Datei, Maske, `aoi.geojson`, `ATTRIBUTION.txt`
(Attributionstext des DEM). Danach Sentinel-2 (COG) und Zarr3 wie in M2: beide
verhalten sich unverändert.

**B. AOI-Formate und Ortssuche (Kriterium 4).** Je eine Datei `.geojson`, `.kml`
und Shapefile-`.zip` (mit `.prj`) im AOI-Abschnitt hochladen: AOI erscheint;
ein ZIP ohne `.prj` wird mit einer englischen Meldung abgewiesen. Im Feld „Place“
einen Ort suchen, einen Treffer wählen: AOI erscheint, „© OpenStreetMap
contributors“ steht unter den Treffern. Mit einem Polygon suchen (`intersects`).

**C. Ansicht und Download (Kriterium 5).** Zwei angrenzende Sentinel-2-Szenen
aus einem Überflug wählen, mit einer Polygon-AOI über beide „Crop & merge to
AOI“ und danach „View full selection“: Zuschnitt bzw. ganze Szenen. Bei „Crop &
merge“ herunterladen und die Datei mit der Karte vergleichen (z. B. in QGIS,
Maske: 1 innen, 0 außen). Bei „View full selection“ einer COG lädt der Browser
die Originale; bei Zarr ohne AOI ist der Knopf deaktiviert („Draw an AOI to
download“). Eine sehr große AOI in nativer Auflösung wird mit einem Faktor-
vorschlag abgewiesen, nie still verkleinert.

**D. Garage (Kriterium 8).** `docker compose down` und `docker compose up -d`
erneut: Der zweite Start mit bestehendem Volume läuft ohne Handarbeit.

---

## 11. Testlauf dieser Sitzung (2026-09-30, Stand `main` + Doku dieses PR)

| Prüfung | Befehl | Ergebnis |
|---|---|---|
| Backend-Lint | `ruff check backend` | grün |
| Backend-Tests | `pytest` (aus der Repo-Wurzel, ohne `tests_live`) | **1769 passed**, 1686 Warnungen (u. a. Zarr-Konsolidierung, unschädlich) |
| Importregeln | `PYTHONPATH=backend lint-imports --config .importlinter` | grün, **12 von 12 Verträgen KEPT** |
| Frontend-Lint | `npm run lint` (oxlint) | grün |
| Frontend-Typprüfung | `npx tsc -b --pretty false` | grün, keine Ausgabe |
| Frontend-Tests | `npx vitest run` | grün, **689 passed** (28 Dateien) |

Nicht gelaufen: `tests_live` (echte Quellen; aus der Sitzung nicht erreichbar,
M2-13), Compose-Topologie und Docker (nie in der Cloud-Sitzung, `adr/0002`); beide
laufen in der CI. Dieser PR ändert keinen Code; die Läufe belegen den Stand von
`main`.

**Fragen an Otto** (nummeriert, Empfehlung zuerst):

1. **`readers` wurde in M3 einmal berührt** (`zarr_reader.py`, `part()` und
   `nodata`, PR #86). (1) **Empfehlung:** das Kriterium so lesen, dass es den
   Anschluss der dritten Quelle meint (der DEM hat `readers` nicht angefasst, der
   COG-Pfad ist unverändert), und die Abweichung als Log-Zeile festhalten. (2) den
   Zarr-Eingriff als Verstoß gegen die Abnahme werten und im PR-Text von M3
   ausdrücklich rechtfertigen. (3) andere Auslegung.
2. **`CLAUDE.md` nennt für `lint-imports` keinen `PYTHONPATH`.** Ohne
   `PYTHONPATH=backend` schlägt der Befehl aus der Wurzel fehl (die CI setzt ihn).
   (1) **Empfehlung:** Otto ergänzt den Hinweis in `CLAUDE.md`; ich ändere die
   Datei nicht ohne Freigabe. (2) `lint-imports` in `pyproject.toml` über
   `root_packages` und Pfad lösen.
3. **Lock-Datei für die Backend-Pakete** — siehe Abschnitt 12, Vorschlag.

---

## 12. Nach M3 vorgemerkt

Alle offenen Punkte aus Log und Plan, nach Meilenstein geordnet. „Quelle“ nennt
die Stelle, an der der Punkt entschieden oder vorgemerkt wurde.

### M4

| Punkt | Stand | Quelle |
|---|---|---|
| **M4-01a**: Zugriffsauflösung nach `access`, gemeinsame Stelle für Items (heute `api/tiler.py`, K-04) | angenommen (F2, F4, F7) | `adr/0011`, Log 30.09.2026, `projektplan.md` M4 |
| **M4-01b**: `AdapterSpec`, Signaturen, Fehlerklassen, `harvest_run` entfernen | angenommen (F1, F3, F7) | `adr/0011` |
| Exporte über dem synchronen Deckel (500 MB roh) in voller Auflösung als **Job**, kein Teil-Download | fest | P20, Log 26.09.2026 |
| **Gemergtes Mosaik ganzer Szenen** je Überflug als Processing-Job (in M3 nur Originale einzeln) | fest | P19, Log 26.09.2026 |
| **Mosaik im Kachel-Pfad** | fest, M4 | P11, `adr/0006` §6 |
| Weg vom eigenen Code zum Objektspeicher (Vorschlag im M4-Plan, Otto entscheidet dort) | offen | `adr/0012` F5 |
| **Datacube** (Kombination mehrerer Datensätze mit Lizenzprüfung der Kombination; T2-Stufe) | Vorschlag, M4/M6 | `architekturplan.md` 7 (T2), `projektplan.md` M6 |
| Zugriffsauflösung außerhalb `api/tiler.py` | mit M4-01a | K-04 |
| `decomp.py` nur als Operator mit Quad-Pol-Capability | ruht, offen ob es eine token-freie Quelle gibt | ENTSCHEIDUNGEN §3 |

### M5

| Punkt | Stand | Quelle |
|---|---|---|
| **Health-Status** je Quelle und Prüfdatum | fest, M5 | P14, D29 |
| **Zählwürfel** nur bei gemessenem Bedarf je Datensatz; vorher prüfen, ob die Zählung über eigene Items im Harvester ihn überflüssig macht | fest | Log 26.09.2026, `adr/0010` |
| **Zenodo als Metadatenquelle** (Metadaten, nicht als Datenquelle) | offen, M5 | `adr/0009` |
| **Hybrid-Suche** (Datensatz-Katalog mit semantischer Suche) | fest, M5 | P9 |
| **Datensatz-Browser** (alle Datensätze mit Beschreibung durchsehen, ins Control Center übernehmen; passt zur Hybrid-Suche) | Vorschlag | Log 30.09.2026 |
| Verfügbarkeits-Zeitleiste; **Neubewertung** des Datums-Fallbacks im Frontend | fest | Log 23.09.2026, `architekturplan.md` 5.2 |
| Uvicorn-Worker des `tiler` (Threadpool 40) | offen | Log 20.09.2026 |
| Harvester-Zeitplan und Review-Queue (der DEM-Befehl ist ein Einmal-Befehl) | M5 | M3-11b |
| Cache für COG-Header | offen, aus M2 herausgenommen | Log 20.09.2026, `adr/0006` §3.4 |
| CQL2 je Collection ausweisen (in M3 nirgends ausgewiesen) | offen | M3-13, `adr/0005` Regel VI |

### Vor dem ersten öffentlichen Deployment zu klären

| Punkt | Stand | Quelle |
|---|---|---|
| **AGPL §13:** Link zum Quellcode für Nutzer anbieten | offene Pflicht | ENTSCHEIDUNGEN §4, Log |
| **Nominatim / ODbL:** Nutzungsbedingungen des öffentlichen Dienstes (Rate, Kennung, Attribution, Caching) gegen den realen Betrieb; ODbL-Auswirkung der gecachten Treffer und der AOI im ZIP; Wechsel auf einen eigenen Dienst möglich (`EARTHX_GEOCODER_URL`) | offen | Log 23.09.2026 und `plans/m3-07a-ortssuche-backend.md` |
| **Copernicus:** Attributionstext und Lizenz des DEM (Copernicus DEM, Airbus/DLR, „produced using Copernicus WorldDEM-30“) und Sentinel Legal Notice für die öffentliche Nutzung; B11-Einstufung bleibt bei Otto | offen | `adr/0003` §11.1, `adr/0009` |
| Nutzungsbedingungen und Haftungsausschluss der Plattform; Esri World Imagery (Basiskarte) | offen | Log 19.09.2026, `prototyp-inventar.md` F2 |
| Ratenbegrenzung pro IP oder Nutzer | offen | D6 |

### Weitere Vorgemerkte

| Punkt | Stand | Quelle |
|---|---|---|
| Bug-Report Stufe 2 | offen | D9 |
| Helle Basiskarte passend zum Theme | offen | D10 |
| Viewer-Pakete Swipe und Export | offen | `plans/m2-format-und-viewer.md` |
| Datensätze ohne im Browser darstellbaren Quicklook: Verhalten ohne AOI („Draw an AOI to view this dataset“) ist Vorschlag, nicht endgültig | Vorschlag | Log 26.09.2026 (M3-12) |

### Neu, Vorschlag: Lock-Datei mit festen Versionen für die Backend-Pakete

**Anlass:** Am 28.09.2026 scheiterte die Installation von `stac-fastapi.types`
(nach Ottos Hinweis vom 30.09.2026; der Fehler selbst steht nicht im Repo).
`backend/requirements.txt` pinnt nur einige Pakete exakt (`rio-tiler`,
`pypgstac`, `stac-fastapi.pgstac`, `titiler.core`, `zarr` mit Kappe); alle
übrigen Pakete und **alle transitiven Abhängigkeiten** löst `pip` bei jedem
Lauf neu auf: in der CI (`pip install -r backend/requirements-dev.txt`), im
Image (`backend/Dockerfile`, `pip install -r requirements.txt`) und im
SessionStart-Hook. Eine neue Veröffentlichung irgendwo im Baum kann also alle
drei zugleich brechen, ohne dass sich das Repo geändert hat.

**Vorschlag (Otto entscheidet; kein Code in M3-15):**

1. Eine Lock-Datei mit exakten Versionen und Hashes, erzeugt aus den
   bestehenden Anforderungsdateien (z. B. `pip-compile --generate-hashes` oder
   `uv pip compile`), eingecheckt als `backend/requirements.lock` und
   `backend/requirements-dev.lock`.
2. CI, `Dockerfile` und SessionStart-Hook installieren aus der Lock-Datei
   (`pip install --require-hashes -r …`); die `.txt`-Dateien bleiben die
   Eingabe für das Erzeugen.
3. Ein Erneuern der Lock-Datei ist ein eigener, bewusster PR (regelmäßig oder bei
   Sicherheitsmeldungen), kein Nebeneffekt jedes Laufs.
4. Ein Test wie `test_frontend_deps_hook.py` prüft, dass Lock-Datei und
   Anforderungsdateien zueinander passen.

Kosten: Stufe B, weil `.github/`, `Dockerfile` und Hook betroffen sind (Änderung
an `.github/` und `.claude/` nur mit ausdrücklicher Erlaubnis). Nutzen: gleiche
Versionen in CI, Image und Sitzung; ein Installationsfehler wie am 28.09.2026
lässt sich auf einen Lock-Wechsel zurückführen. Entscheidung offen; als Vorschlag
im Log vermerkt.

---

## Zusammenfassung

Alle neun Kriterien aus `docs/plans/m3-dritte-quelle-und-interface.md`
Abschnitt 5 sind mit Test-, Code- und Log-Belegen erfüllt. Zwei Punkte gehören
Otto: **(a)** die Abweichung bei `readers` (Frage 1) und **(b)** die lokale
Prüfung der Kriterien 1, 4 und 5 nach Abschnitt 10. Die Läufe der Sitzung
(Backend 1769, Frontend 689 Tests, Lint, Typen, 12 von 12 Importverträgen) sind
grün. Mit Ottos Abnahme wird der M3-Plan als abgeschlossen markiert und die
Log-Zeile „M3 abgenommen“ mit Datum und PR-Nummer ergänzt.
