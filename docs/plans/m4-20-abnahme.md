# M4-20 — Abnahme von M4: Belege je Kriterium

**Ziel:** Otto kann M4 anhand dieses Berichts und des zugehörigen PR abnehmen,
ohne Code zu lesen.
**Ort im Repo:** `docs/plans/m4-20-abnahme.md`
**Grundlage:** `docs/plans/m4-processing-kern.md` Abschnitt 5 („Abnahme von M4“,
Kriterien 1–10), Stand `main` bei Commit `b60c3b4` (Merge von PR #169,
24.10.2026). Alle Aufgaben von M4-00 bis M4-32b außer M4-20 sind gemergt (Tabelle
in `m4-processing-kern.md` §3, in diesem PR nachgezogen; Übersicht in Abschnitt 13).
**Muster:** `docs/plans/m3-15-abnahme.md`.
**Stufe A, keine Codeänderung.** Dieser PR ändert nur Dokumente (Bericht, §3 des
Plans, README, Log).

**Was dieser Bericht nicht ersetzt:** die lokale Prüfung durch Otto (Abschnitt
11) und die Prüfung gegen echte Quellen. `gateway` erreicht die realen Quellen
aus einer Cloud-Sitzung nicht (`adr/0002`, Nachtrag M2-13); der Egress-Proxy
der Sitzung lehnt das `CONNECT` ab (Log 20.10.2026). Compose, Docker-Bau und
Browser laufen in dieser Sitzung nicht, sondern in der CI bzw. bei Otto. Was die
Belege aus früheren Aufgaben zitieren, ist hier nicht neu gemessen; was diese
Sitzung selbst gelaufen ist, steht in Abschnitt 12.

**Zusammenfassung des Ergebnisses**

| # | Kriterium | Ergebnis |
|---|---|---|
| 1 | Dasselbe Rezept: T1-Vorschau, Job (T2), lokaler Runner (T2L) übereinstimmend; Vergleichstest in der CI | **erfüllt**, drei Belege (Abschnitt 1); eine Grenze benannt (Image gegen Kern aus derselben CI) |
| 2 | Zweiter identischer Auftrag aus dem Cache; lokal nie; Export rechnet neu | erfüllt; der Lauf gegen eine echte Quelle (`try-job.ps1`, Schritt 4) liegt bei Otto |
| 3 | `processing` ohne Datenbank, Queue, Objektspeicher, `gateway`; Importregeln grün | erfüllt (16 von 16 Verträgen KEPT) |
| 4 | Ergebnisse privat, nur signierte URLs; Ablauf 7 Tage; zufällige Job-IDs; kein Hash und keine AOI in URLs oder Logs | erfüllt; das tatsächliche Löschen durch den Speicher nach 7 Tagen ist nicht im Lauf zu beobachten (Abschnitt 4) |
| 5 | Export über dem Deckel und Mosaik je Überflug als Job im Viewer, mit Attribution, Terms, `citation.bib`, `recipe.json` | erfüllt; Prüfung im Browser bei Otto |
| 6 | Band-Math und Reprojektion registriert, im Panel aus Schemas bedienbar, Kostenschätzung vor dem Start | erfüllt; Prüfung im Browser bei Otto |
| 7 | Mosaik im Kachel-Pfad zustandslos, ohne exakte AOI in der URL | erfüllt; Prüfanleitung A von Otto bestanden, B Schritte 1–2 bestanden, Schritte 3–6 **offen** (Abschnitt 7) |
| 8 | Onboarding-Checkliste Fassung v2 grün je Datensatz | erfüllt |
| 9 | M4-01a und M4-01b umgesetzt; Pflicht-CI grün aus der Lock-Datei | erfüllt |
| 10 | Masking und Normalisierung registriert (M4-18); Permalink und Methodentext (M4-19) | erfüllt; Prüfung im Browser bei Otto |

---

## 1. Dasselbe Rezept liefert Vorschau, Job und lokalen Runner mit übereinstimmendem Ergebnis; Vergleichstest in der CI

**Wortlaut:** „Übereinstimmend“ heißt für T1 ↔ T2 bei Band-Math: COG bitgleich
ohne Einschränkung; Zarr bitgleich außerhalb von 0,125 Quellpixel an einer
Pixelgrenze, wo `nearest` den Nachbarn wählen darf, und die Formel stimmt
überall; T2 ↔ T2L bleibt bitgleich (`adr/0014` §15d, Log 2026-10-07).

**Drei verlangte Belege für T2 ↔ T2L (Job ↔ lokaler Runner):**

1. **`test_compare` aus M4-16a (PR #160),**
   `backend/tests/earthx/runner/test_compare.py`, läuft im Backend-Job der CI
   (Teil von `pytest`). Job-Kind (`earthx.jobs.child.run_child`) und Runner
   (`earthx.runner.cli.main`) laufen in je einem `spawn`-Prozess mit demselben
   Rezept; `result.tif` und `mask.tif` sind pixelgleich und als Datei mit
   gleichem SHA-256 (`TestTheJobAndTheRunnerComputeTheSameBits`:
   `test_band_math_on_scaled_cogs`, `test_reprojection_bilinear_on_a_cf_zarr`,
   `test_the_runner_marks_its_result_as_its_own`). Dazu die Gegenproben
   (`TestTheCounterTest`: `test_another_constant_in_the_expression`,
   `test_another_resampling`), die zeigen, dass der Vergleich fallen kann
   (`plans/m4-16-lokaler-runner.md` §9, §10.1).
2. **Schichtvergleich in der CI, M4-16b (PR #164),** Compose-Job in
   `.github/workflows/ci.yml` („Compose topology“): die Stufe `runner` wird
   gebaut; die Engine-Versionen des Runners gleichen dem Block `engine` des
   Dienstes `worker` (`versions` unter `--network none`); **das Image des
   Runners trägt dieselben Schichten wie das Image von `worker`** (die Stufe
   fügt nur `ENV`, `USER` und `ENTRYPOINT` hinzu), UID 10001; `check` nennt auf
   dem synthetischen Rezept genau einen Host; `run` ohne Netz endet mit Exit-Code
   4 und lässt keine Datei zurück. Was `test_compare` für den Code zeigt, gilt
   damit für die Dateien im Image (`plans/m4-16-lokaler-runner.md` §10.1).
3. **Ottos lokaler Hash-Vergleich vom 24.10.2026,** Log-Zeile vom 2026-10-24
   („Lokaler Beleg für Kriterium 1 erneuert“, PR #169): Cloud-Job aus
   `scripts/try-job.ps1` gegen das Runner-Image `earthx-runner:0.4.2`
   (`runner_version` **0.4.2+gcb03706**, offline, gehärtet) auf `main` nach
   M4-19: SHA-256 von **`result.tif` und `mask.tif` je gleich (True)**;
   `provenance.json` mit `execution: local`, `self_attested: true`. Das ersetzt
   den Beleg vom 2026-10-20 (Runner 0.4.1+g7768ab6, nur `result.tif`).
   Die Messung hat Otto gemacht; diese Sitzung hat sie nicht wiederholt (kein
   Docker, keine echte Quelle).

**Ergänzend, zum selben Kriterium (T1 ↔ T2):** Das Kriterium nennt auch die
Vorschau. `backend/tests/catalog/test_onboarding_processing.py::test_the_tile_equals_the_job_on_the_native_level`
rechnet dasselbe Band-Math-Rezept als Kachel (T1) und als Job (T2) und
vergleicht auf der nativen Ebene: COG ohne Toleranz, Zarr bis auf Pixel
innerhalb 0,125 Quellpixel einer Pixelgrenze (`adr/0014` §15d); die Gegenprobe
`test_a_tile_of_a_different_expression_is_not_the_job` fällt bei einem anderen
Ausdruck. Unterhalb der nativen Ebene ist die Kachel eine Vorschau und wird nicht
als gleich behauptet (`test_tiler_operator.py::test_a_tile_below_the_native_level_is_a_preview_and_not_asserted_equal`).

**Grenzen, offen benannt (`plans/m4-16-lokaler-runner.md` §10.1):**

- Ein Hash **im Image** gegen den Kern **aus derselben CI** ist nicht nachgewiesen,
  nur über gleiche Schichten und Versionen geschlossen. Der Grund: `gateway`
  lässt nur `https`-Adressen auf erklärten Hosts zu; eine lokale Eingabe ginge
  nur über eine Naht, die es nur in `pytest` gibt (B8, B9). Ottos Beleg
  (Nr. 3) füllt genau diese Lücke mit einer echten Quelle.
- „Gleiche Bits“ gilt nur bei gleichem Image und gleicher Maschine; auf einem
  anderen Prozessor kann das letzte Bit abweichen (`README.md`, „Lokaler Runner“;
  Log 05.10.2026, Nebenfund (2)). Ottos Beleg gilt für seinen Rechner
  (Windows, Docker Desktop, x86_64).

**Ergebnis:** Kriterium 1 erfüllt.

---

## 2. Zweiter identischer Auftrag aus dem Cache; lokal nie; Export rechnet neu

- **Treffer bei Fassung:** `backend/tests/earthx/jobs/test_submit.py`,
  `TestCacheHit`: `test_a_hit_hangs_the_new_job_on_the_finished_run`;
  kein Treffer bei weniger als 24 Stunden Restlaufzeit, bei einem Lauf, der nicht
  gelang, **bei fehlender Fassung** (`test_a_result_without_versions_is_no_hit`)
  und **bei geänderter Fassung einer Eingabe** (`test_a_changed_input_version_is_no_hit`);
  ohne Fassung hängt sich ein Auftrag nur an den laufenden Lauf
  (`test_an_order_without_versions_attaches_to_the_active_run_but_is_not_cacheable`).
- **Ein Treffer verlängert die Frist nicht** (Log 20.10.2026, Frage 12):
  `test_cleanup.py::TestRecipes::test_a_cache_hit_gives_the_new_recipe_the_life_of_the_result_it_uses`.
- **Export rechnet immer neu:** `test_submit.py::TestAnExportHasARunOfItsOwn::test_two_equal_exports_make_two_runs_that_are_not_cacheable`.
- **Lokale Ergebnisse nie im Cache:** Der Runner hat keinen Zugriff auf
  Datenbank und Objektspeicher (Vertrag `no-platform-services-in-runner`, Abschnitt
  3), schreibt nur in einen Ordner und kennzeichnet das Ergebnis mit
  `execution: local`, `self_attested: true`
  (`test_compare.py::test_the_runner_marks_its_result_as_its_own`).
- **Gegen eine echte Quelle:** `scripts/try-job.ps1` schickt denselben Auftrag
  zweimal und erwartet beim zweiten Mal „successful at once, no new run“
  (Schritt 4). Das läuft bei Otto (Abschnitt 11, Punkt A); in dieser Sitzung
  nicht.

**Ergebnis:** Kriterium 2 erfüllt.

---

## 3. `processing` ohne Datenbank, Queue, Objektspeicher und `gateway`; Importregeln grün

`PYTHONPATH=backend lint-imports --config .importlinter` (dieser Lauf, siehe
Abschnitt 12): **16 Verträge, 16 KEPT, 0 broken.** Die Relevanten:

- `processing imports only access, readers and catalog` — verbietet `gateway`,
  `adapters`, `jobs`, `api`, `objectstore`, `runner` u. a. als Import.
  **Lesart:** Der Vertrag zählt direkte Importe (`allow_indirect_imports = True`).
  `processing` liest über `readers`, und `readers` nutzt `gateway`; das ist der
  erlaubte Weg („Lesen der Datenquellen über `gateway`“, `CLAUDE.md`). Frage 3.
- `the worker core reaches no database` (`no-database-in-worker-core`): zählt
  Ketten bis `psycopg`, `psycopg_pool`, `asyncpg`.
- `the worker core reaches no object store` (`no-object-store-in-worker-core`):
  Ketten bis `earthx.objectstore` und `botocore`. Die Queue liegt in Postgres
  (`adr/0013`) und fällt unter die Datenbank-Regel.
- `jobs import only processing and objectstore`: `jobs` und `api` nutzen das
  Modul für Plattformdienste; `gateway` ist dafür **nicht gelockert** — der
  Vertrag `gateway imports nothing domain-specific` ist unverändert.
- `HTTP and S3 clients live only in gateway` (`http-only-in-gateway`): **eine**
  ausdrückliche Ausnahme, `earthx.objectstore.client -> botocore` (eigener
  Objektspeicher, `KLAERUNGEN` B8 Nachtrag, `adr/0015`); jedes andere Modul mit
  `botocore` bricht den Vertrag.
- `runner imports only processing, catalog.datasets and catalog.registry` und
  `the local runner reaches no database and no object store`.
- `backend/tests/earthx/processing/test_import_is_pure.py` und
  `test_no_direct_open.py` halten `processing` rein; `backend/tests/test_module_boundaries.py`
  gleicht die Module mit der Platte ab.

Zum Vergleich: bei M3-15 waren es 12 Verträge.

**Ergebnis:** Kriterium 3 erfüllt.

---

## 4. Ergebnisse privat, nur signierte URLs; Ablauf nach 7 Tagen; zufällige Job-IDs; weder Hash noch AOI in URLs oder Logs

- **Privat, signiert:** `backend/tests/earthx/objectstore/test_results.py`:
  `test_a_signed_url_points_at_the_public_endpoint_with_the_file_name`,
  `test_a_signed_url_never_outlives_the_result`,
  `test_no_signed_url_with_less_than_a_minute_left`,
  `test_a_naive_expiry_is_refused`,
  `test_nothing_in_the_store_names_the_access_key_outside_signed_urls`. Die
  Job-API antwortet auf einen Link mit `303` auf eine eben signierte URL
  (`api/test_processing_route.py::test_a_link_is_a_303_to_a_url_signed_just_now`).
- **Zufällige Kennungen:** `test_results.py::test_a_new_result_id_is_random_and_well_formed`;
  fremde oder fehlerhafte Kennungen finden nichts und erreichen die Datenbank
  nicht (`jobs/test_submit.py`: `test_an_identifier_that_is_foreign_or_malformed_is_unknown`,
  `test_a_malformed_identifier_never_reaches_the_database`); `test_processing_route.py`
  `test_an_unknown_identifier`, `test_a_malformed_identifier`.
- **Ablauf nach 7 Tagen (`RESULT_TTL`, Q10):**
  - die Regel `results/` → 7 Tage im Bucket setzt das Bootstrap
    (`compose/objectstore/bootstrap.py::_set_lifecycle_rule`) und liest sie zurück;
    `objectstore/results.py::lifecycle_ok` erkennt sie am Inhalt (aktiv,
    Präfix `results/`, 7 Tage, Abbruch offener Uploads nach 1 Tag; Konfiguration
    `lifecycle_check`, Vorgabe `required`;
    `test_results.py::test_no_lifecycle_configuration_is_not_ok`); der Smoke im
    Compose-Job liest die Konfiguration nur (`tests/compose/test_objectstore_smoke_output.py`);
  - der Aufräumer in `jobs` löscht Läufe, Objekte, Rezepte und Permalinks nach
    Ablauf, Objekte vor Zeilen, in Stapeln, mit einem Aufseher
    (`jobs/test_cleanup.py`: `TestExpiry`, `TestObjectsBeforeRows`, `TestBatches`,
    `TestRecipes`, `TestPermalinks`).
  - **Grenze:** Das Löschen der Objekte durch Garage nach 7 Tagen ist in keinem
    Lauf zu beobachten (die Zeit lässt sich nicht beschleunigen); belegt sind die
    Regel samt Rücklesen und der eigene Aufräumer.
- **Weder Hash noch AOI in URLs oder Logs:**
  `api/test_intake.py::test_nothing_in_any_log_names_an_aoi_an_address_or_a_hash`;
  `jobs/test_worker.py::test_no_log_line_of_any_way_a_run_can_end_names_the_recipe_the_hash_the_address_the_aoi_or_an_id`;
  `api/test_processing_route.py`: `test_it_has_no_hash_no_run_no_area_no_address_and_no_result_id`,
  `test_the_name_has_no_area_hash_job_or_result_identifier`,
  `test_the_access_log_hides_whatever_stands_where_an_identifier_would`;
  `api/test_download_route.py`: `test_no_aoi_coordinate_reaches_the_log`,
  `test_recipe_json_has_neither_hash_nor_identifier`. `scripts/try-job.ps1`
  Schritt 6 sucht zusätzlich in `docker compose logs api` nach den Job-IDs (bei
  Otto).
- **Permalinks (M4-19e):** eigene zufällige Kennung, Löschschlüssel nur als
  SHA-256, Frist 30 Tage ab Erstellung, Öffnen verlängert nie
  (`api/test_permalink_route.py`, `jobs/test_cleanup.py::TestPermalinks`).

**Ergebnis:** Kriterium 4 erfüllt, mit der genannten Grenze beim Löschen nach 7 Tagen.

---

## 5. Export über dem Deckel und Mosaik ganzer Szenen je Überflug laufen im Viewer als Job, mit Attribution, Terms, `citation.bib`, `recipe.json`

- **Export als Job, Backend (M4-11a, #133):** `backend/tests/earthx/processing/test_export.py`
  (bitgleich zum synchronen Zuschnitt für ein Item, ein Mosaik und zwei Gruppen,
  Plan `m4-11-export-job.md`); Kennung im `413` des Zuschnitts.
- **Ergebnis als ein ZIP (M4-11b-1, #145; M4-30, #159):**
  `backend/tests/earthx/api/test_result_zip_files.py`: das ZIP hält genau die
  Dateien des Zuschnitt-ZIPs (`TEXT_FILES` in `access/crop_rules.py`; die Terms stehen in `ATTRIBUTION.txt`:
  `aoi.geojson`, `recipe.json`, `citation.bib`, `ATTRIBUTION.txt`,
  `methods.txt`) plus `result.tif` und `mask.tif` und keine anderen
  (`test_it_holds_the_files_of_the_crops_zip_and_the_two_rasters_and_no_other`);
  die Attribution ist der Text der Registry
  (`test_the_attribution_is_the_text_of_the_registry_with_the_year_of_the_run`
  — das Jahr stammt aus dem Datum des Laufs, nicht der Aufnahme; Punkt 1 in
  Abschnitt 14); das ZIP ist byteweise stabil; kein Job, Hash oder keine
  Koordinate im Text.
- **Mosaik je Überflug als Job (M4-12a, #136):** `test_mosaic.py`
  (`TestAMosaicOverTwoZones`: Zone mit den meisten Szenen, die erste Szene gewinnt
  an Überlappungen, Kopieren statt Resampling, Blockgröße ohne Wirkung, Maske
  folgt der AOI).
- **Im Viewer (M4-11b-2, #151; M4-12b, #148):** Angebot „Export as job“ im
  Download-Dialog bei `X-Export-Job: available`, gesperrt bei `too-large`;
  bei mehreren Szenen unter „Download originals“ die Wahl „Merged per pass (job)“ und je Überflug mit mindestens zwei Szenen „Start job“ (`OriginalFiles.tsx`, `MosaicJobs.tsx`);
  Status über `JobRow` mit SSE (Rückfall auf Abfragen); „Download (ZIP)“ im Panel
  (`frontend/src/components/DownloadDialog.test.tsx`, `ProcessingPanel.test.tsx`,
  `MosaicJobs.test.tsx`; Plan `m4-11b-angebot-und-zip.md` §12, §13, Log 13.–15.10.2026).
- **Prüfung im Browser bei Otto** (Abschnitt 11, Punkt B); in dieser Sitzung nicht
  gelaufen.

**Ergebnis:** Kriterium 5 erfüllt.

---

## 6. Band-Math und Reprojektion registriert, im Panel aus Schemas bedienbar, mit Kostenschätzung vor dem Start

- **Registry:** `test_operators.py::test_the_platform_registry_holds_the_four_operators`
  (Band-Math, `reproject`, `mask`, `normalize`); `test_both_test_operators_apply_to_every_registry_entry`.
- **Schema im Prozess:** `GET /processing/processes/recipe` trägt das Schema des
  Auftrags und `x-earthx-tiers`/`x-earthx-kind` (M4-13a, #134;
  `api/test_process_fixtures.py`, `test_processing_docs.py`).
- **Schätzung vor dem Start:** Route `POST /processing/processes/recipe/estimate`
  (`api/test_processing_estimate.py`, `processing/test_plan.py`; M4-25 für
  Raster in geografischem CRS); im Panel wartet „Start job“ auf eine Schätzung
  genau dieses Auftrags (`ProcessingPanel.test.tsx`: `"Start job" waits for an
  estimate of exactly this order`, `drops an estimate still on its way when the
  selection changes`).
- **Formular aus dem Schema:** eigener Formularbau (M4-13b, #138), M4-18c (#177)
  erweitert ihn um Listen ganzer Zahlen (Klassen der Maske, `mask`).
  Reprojektion im Panel: `ProcessingPanel.test.tsx` (`reprojectDem`).
- **Weitere Resampling-Methoden** (`average`, `mode`, `cubicspline`, `lanczos`)
  mit Messung gegen `adr/0014` §6.3: M4-24 (#158).
- **Prüfung im Browser bei Otto** (Abschnitt 11, Punkt B).

**Ergebnis:** Kriterium 6 erfüllt.

---

## 7. Mosaik im Kachel-Pfad zustandslos und ohne exakte AOI in der URL

- **Zustandslos:** Die URL trägt die Liste der Items (kein Such-Hash, keine
  Sitzung); zwei frische Apps antworten auf dieselbe URL mit denselben Bytes
  (`api/test_tiler_mosaic.py::test_two_fresh_apps_answer_the_same_url_with_the_same_bytes`;
  `access/test_mosaic_tiles.py` ebenso); die Reihenfolge der IDs in der URL ändert
  die Bytes nicht (`test_the_order_of_the_ids_in_the_url_does_not_change_the_bytes`);
  die Reihenfolge bestimmt der Job, nicht die URL (`test_the_order_is_the_jobs_not_the_urls`).
- **Ohne AOI in der URL:** `test_the_schema_has_no_parameter_that_could_carry_an_area_or_an_address`
  (kein `aoi`, `bbox`, `geometry`, `intersects`, `expression`, `op`, `params`);
  der Zuschnitt auf die AOI geschieht im Browser um die Kachel-URL
  (`frontend/src/store.mosaic.test.ts`: `pins the mosaic and the scenes under it
  as one layer per time step, cut to the AOI`).
- **Ohne Item-Cache:** klare Meldung statt `500` (`test_without_a_pool_a_mosaic_is_a_503_that_says_why_and_the_tile_of_one_item_goes_on`).
- **Gleiche Mosaikregel wie der Job (S5):** `access/crop_rules.py`
  (`mosaic_order`), Vergleichstest in M4-17a (#167).
- **Gegen eine echte Quelle (Otto, lokal, Antwort vom 24.10.2026).** In der
  Cloud-Sitzung erreicht das `gateway` Earth Search nicht (Log 20.10.2026 und
  22.10.2026, beide „offen“); die Läufe hat Otto auf seinem Rechner gemacht, diese
  Sitzung hat sie nicht wiederholt:
  - **Prüfanleitung A von M4-17 (Backend): bestanden.** Zu M4-17b: Antwort `200`,
    Hash `True`, z7 → `400`, gemischte Überflüge → `422`.
  - **Prüfanleitung B von M4-17 (Viewer): Schritte 1–2 am 22.10.2026 bestanden**
    (ein TileJSON, Kacheln nur über `/mosaic/tiles/`, eine Fläche ohne Lücke, ein
    Layer-Eintrag je Überflug). **Schritte 3–6 stehen aus;** Otto reicht das Ergebnis nach.
  - Außerdem belegt: die Verdrahtung gegen eine echte MapLibre-Karte mit
    synthetischen Kacheln (`plans/m4-17-mosaik-kachel-pfad.md` §14, §15).

**Ergebnis:** Kriterium 7 erfüllt; offen bleiben die Schritte 3–6 der
Prüfanleitung B.

---

## 8. Onboarding-Checkliste Fassung v2 grün für jeden Datensatz

`backend/tests/catalog/test_onboarding_checklist.py`: `ENTRIES = list(REGISTRY)`,
`test_every_registry_entry_passes_the_checklist` läuft für `sentinel-2-c1-l2a`,
`sentinel-2-l2a-zarr3` und `cop-dem-glo-30`; Punkt 9 in Fassung v2 („je Datensatz
ein Operator-Lauf gegen Fixtures“) steht in `backend/tests/catalog/test_onboarding_processing.py`
(M4-15, #135): `test_every_registry_entry_has_an_operator`,
`test_a_fourth_entry_without_an_operator_is_found`, dazu je Eintrag die Kette
Suche → Auflösung → Rezept → Kern → COG → `recipe.json` und Zitat. Fixtures sind
synthetisch (Mini-COG, Mini-Zarr).

**Ergebnis:** Kriterium 8 erfüllt.

---

## 9. M4-01a und M4-01b umgesetzt; Pflicht-CI grün mit Installation aus der Lock-Datei

- **M4-01a (#112)** Zugriffsauflösung nach `access`; **M4-01b (#122)**
  `AdapterSpec`, Signaturen mit `DatasetConfig`, Fehlerklassen. `harvest_run`
  kommt im Code nicht mehr vor (`grep -rn harvest_run backend/earthx` ohne
  Treffer; `tests/catalog/test_registry.py::test_an_entry_names_no_harvest_run`).
  Abnahme-Test über jeden Adapter: `tests/earthx/adapters/test_spec.py`,
  `test_dispatch.py`, `test_item_contract.py` (M4-22, #139).
- **Lock-Datei (M4-00b, #113):** `tests/test_backend_lock.py` — jede Anforderung ist
  auf eine erlaubte Version festgelegt, jede Installationsstelle installiert aus
  der Lock-Datei mit Hashes (`test_every_install_site_installs_from_the_lock_with_hashes`,
  `test_no_workflow_installs_the_backend_any_other_way`). In
  `.github/workflows/ci.yml` installieren Backend-Job (Zeile 70), Importregel-Job
  (Zeile 122) und der Smoke (Zeile 293) mit `pip install --require-hashes`.
- **Pflicht-CI:** Der Lauf „CI“ Nr. 704 auf `main` (Commit `cb03706`, Merge von
  PR #180 = M4-19c, der letzte Code-Stand) ist **erfolgreich** abgeschlossen (GitHub
  Actions, abgefragt am 24.10.2026). Der Lauf Nr. 707 auf `b60c3b4` (Merge von #169,
  nur Dokumente) lief bei der Abfrage noch. Dazu die lokalen Läufe dieser
  Sitzung (Abschnitt 12).

**Ergebnis:** Kriterium 9 erfüllt.

---

## 10. Masking und Normalisierung registriert (M4-18); Permalink und Methodentext funktionieren (M4-19)

- **Masking und Normalisierung:** `processing/test_mask.py` (Klassen der Schicht
  und `nodata` der Schicht verbergen jedes Band), `processing/test_normalize.py`;
  Registry-Feld `mask` und Flags `masking`, `normalization` ohne Vorgabewert (S4,
  B10); die Kachel verkettet Schritte (M4-18b, #175); Panel-Formular „Classes to
  hide“ (M4-18c, #177, `ProcessingMask.test.tsx`); Beide Operatoren sind bitstabil unter den
  Einstellungen A und D von `adr/0016` §3.3 (`adr/0014` §15, Toleranz).
- **Methodentext (M4-19a):** `processing/test_methods.py` (Daten, Skalierung,
  Schritte, Ausgabe, Fläche, Software; Reihenfolge der Schritte; Mosaik und
  Resampling genannt); `methods.txt` in Zuschnitt, Export, Job-ZIP und im Runner.
- **Einheiten (M4-19b, #178), Farbskala der Vorschau (M4-19c, #180),
  „Load recipe…“ (M4-19d, #176):** `processing/test_units.py`,
  `ProcessingRecipe.test.tsx`, `ProcessingPreview.test.tsx`.
- **Permalink (M4-19e, #179):** `api/test_permalink_route.py` (Rückgabe samt
  Frist, zwei Links zu einem Auftrag sind zwei Kennungen und zwei Schlüssel,
  Schlüssel nur als Hash, richtiger Schlüssel löscht), `jobs/test_cleanup.py::TestPermalinks`,
  `ProcessingShare.test.tsx` (stellt Datensatz, Szenen, AOI, Schritte und Ansicht
  wieder her, liest den Link einmal, fasst fremde Adressen nicht an).
- **Prüfung im Browser bei Otto** (Abschnitt 11, Punkt C).

**Ergebnis:** Kriterium 10 erfüllt.

---

## 11. Von Otto lokal zu prüfen (Windows / PowerShell 5.1)

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
`catalog-load`, `objectstore-secrets`, `objectstore-init`) beenden sich. Den DEM
lädt einmalig `docker compose run --rm materialize cop-dem-glo-30` (rund 30
Anfragen an den Bucket). Viewer: `cd frontend; npm install; npm run dev`, dann
`http://localhost:5173`.

**A. Job durchspielen (Kriterien 2 und 4).**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\try-job.ps1
```

Erwartet: jeder Schritt `OK` (Auftrag mit `201`, Status `successful`, Ergebnisse
nach `.\try-job-output\`, **zweiter identischer Auftrag sofort `successful` ohne
neuen Lauf**, beide Jobs verworfen, **kein Treffer der Job-IDs in
`docker compose logs api`**), Exit-Code 0. Mit `-Dataset cop-dem-glo-30` für den DEM.

**B. Panel, Export und Mosaik im Viewer (Kriterien 5, 6, 7).** Sentinel-2
suchen (kleine AOI, Juli 2025), zwei angrenzende Szenen eines Überflugs wählen:
„⚙ Process“ öffnet das Panel; Band-Math (z. B. NDVI) und `reproject` sind aus dem
Formular bedienbar; „Review“ zeigt die Schätzung, „Start job“ ist vorher
gesperrt; „Preview“ erscheint als Kennzeichnung auf der Karte. Ein Überflug mit
mehreren Szenen erscheint als **ein** Layer (Mosaik); beim Heranzoomen ab z8 lädt
es nach. Im Download-Dialog bei einer sehr großen AOI „Export as job“; bei mehreren
Szenen unter „Download originals“ die Wahl „Merged per pass (job)“ und „Start job“
je Überflug; fertige Jobs bieten „Download (ZIP)“ mit
`result.tif`, `mask.tif`, `aoi.geojson`, `recipe.json`, `citation.bib`,
`ATTRIBUTION.txt`, `methods.txt`.

**C. Masking, Normalisierung, Teilen (Kriterium 10).** Im Panel den Schritt
`mask` (Klassen angekreuzt) und `normalize` hinzufügen, Vorschau prüfen. „Share“
erzeugt einen Link (`?permalink=…`), im neuen Tab stellt er Auswahl, AOI und
Schritte wieder her; das rote Kreuz löscht ihn.

**D. Lokaler Runner (Kriterium 1).** Nach `README.md`, Abschnitt „Lokaler Runner“, in der PowerShell-Fassung:

```powershell
docker build --target runner --build-arg "EARTHX_COMMIT=$(git rev-parse --short HEAD)" -t earthx-runner:0.4.2 backend
docker run --rm --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges -v "${PWD}\in:/in:ro" -v "${PWD}\out:/out" earthx-runner:0.4.2 run /in/recipe.json
```

(`recipe.json` aus dem Download des Jobs nach `.\in`; dann SHA-256 von
`result.tif` und `mask.tif` mit `Get-FileHash` gegen die Dateien des
Cloud-Jobs vergleichen. Das hast du am 24.10.2026 mit `0.4.2+gcb03706` getan.)
Der Runner nennt seine Version in `provenance.json`.

**E. Nach der Abnahme (Punkt 13 im Abschnitt 14):** Wer `docs/plans/` umbaut,
tut es ohne laufende Session.

---

## 12. Testlauf dieser Sitzung (2026-10-24, Stand `main` + Doku dieses PR)

| Prüfung | Befehl | Ergebnis |
|---|---|---|
| Backend-Lint | `ruff check backend` | grün („All checks passed!“) |
| Backend-Tests | `pytest` (aus der Repo-Wurzel, ohne `tests_live`) | **5762 passed, 8 skipped** (PowerShell `pwsh` ist in der Sitzung nicht installiert, die CI hat es), 1102 Warnungen, 19 min 23 s |
| Importregeln | `PYTHONPATH=backend lint-imports --config .importlinter` | grün, **16 Verträge KEPT, 0 broken** |
| Frontend-Lint | `npm run lint` (oxlint) | grün, keine Funde |
| Frontend-Typprüfung | `npx tsc -b --pretty false` | grün, Exit 0 |
| Frontend-Tests | `npx vitest run` | grün, **1786 Tests in 55 Dateien** |

Nicht gelaufen: `tests_live` (echte Quellen; aus der Sitzung nicht erreichbar),
Compose-Topologie, Image-Bau der Stufe `runner` und Browsertests (nie in der
Cloud-Sitzung, `adr/0002`; der Bau scheitert in der Sitzung an der TLS-Kette des
Proxys, `plans/m4-16-lokaler-runner.md` §10). Sie laufen in der CI bzw. bei Otto.
Dieser PR ändert keinen Code; die Läufe belegen den Stand von `main`.

---

## 13. Stand aller M4-Aufgaben

Die Tabelle in `plans/m4-processing-kern.md` §3 ist in diesem PR nachgezogen:
doppelte Zeilen (M4-11b, M4-12a, M4-12b) sind zusammengeführt, jede Aufgabe trägt
ihre PR-Nummer. Alle Aufgaben von M4-00 bis M4-32b sind gemergt, die PR-Nummern
reichen von #111 bis #180. **M4-20** ist diese Aufgabe (Entwurfs-PR). Abweichungen
zwischen dem ursprünglichen Schnitt und dem Ergebnis stehen im Log und in den
Plänen der Aufgaben (`plans/m4-xx-*.md`).

---

## 14. Nach M4 vorgemerkt

Dieser Abschnitt übernimmt `docs/plans/nach-m4-backlog.md` (Stand 24.10.2026) **vollständig**,
in der Nummerierung der Datei, und ergänzt unter „Ergänzt aus Log und Plänen“ die
Punkte, die dort nicht stehen. Die Datei bleibt als Quelle liegen; die Reihenfolge
ist, wie dort vermerkt, noch offen.

### Neu, noch ohne Plan-Datei

1. **Jahr in der Copernicus-Attribution** (Fund vom 20.10.2026, `provenance.json` des Runners).
   - **Befund:** Dort steht „Contains modified Copernicus Sentinel data 2026“, die Szene ist aber vom 29.07.2025.
   - **Vermutung:** Das Jahr kommt aus dem aktuellen Datum statt aus der Aufnahme.
   - **Aufgabe (Stufe A):**
     - zuerst den Wortlaut der Copernicus Sentinel Data Terms mit Quelle prüfen,
     - dann das Jahr aus dem Aufnahmedatum ableiten, bei mehreren Jahren als Spanne, etwa „2024–2025“,
     - eine Stelle für alle Downloads (Zuschnitt, Export, Job, Runner, Linkliste der Originale) und für `citation.bib`.
2. **Zuschnitt und Export auf die Sortierung des Mosaik-Jobs angleichen** (M4-17, Frage 2, 20.10.2026).
   - **Befund:** Die Regel „erstes gültiges Pixel“ ist überall dieselbe, die Reihenfolge der Szenen aber nicht:
     - Mosaik-Job und Mosaik-Kachel sortieren nach Ziel-CRS und Item-ID,
     - Zuschnitt und Export folgen der Reihenfolge der Auswahl.
   - **Folge:** In schmalen Überlappungen kann die Vorschau eine andere Szene zeigen als der Zuschnitt.
   - **Aufgabe (Stufe A):** dieselbe Sortierfunktion für Zuschnitt und Export verwenden. Weil sich dadurch die Bytes des Zuschnitts ändern, gehört die Änderung in die Versionierung.
3. **Absolute URL für den Link `tiles`** im Ergebnisdokument (M4-13c-5). Heute ist der Link relativ, ein API-Client ohne den gemeinsamen Proxy findet den `tiler` damit nicht. Spätestens mit der öffentlichen API in M6 nötig.
4. **Mosaik mit Operator im Kachel-Pfad,** also eine Vorschau des Mosaik-Jobs mit Band math (M4-17, Frage 4).
5. **Processing auf einem Ergebnis** (Otto, 20.10.2026), also ein Job-Ergebnis als Eingabe eines neuen Rezepts.
   - **Warum eine Vorlage nötig ist:** Das ist eine neue Art von Eingabe neben Datensatz und Item. Sie berührt „Eingaben per Referenz“ (S3), B8, Herkunft und Ablauf nach 7 Tagen.
   - **Aufgabe:** zuerst eine Entscheidungsvorlage (Stufe C), dann die Umsetzung.
   - **Abgrenzung zu UI-01:** UI-01 sperrt bis dahin den Processing-Knopf bei Ergebnis-Layern mit Grund (UI-01 §1 Punkt 11).
6. **Gemergter Zuschnitt als ein Objekt im Panel** (Otto, 20.10.2026).
   - **Heute:** Wird Processing aus einem Layer gestartet, der schon gemergt und auf die AOI zugeschnitten ist, bietet das Panel trotzdem „Run as: One job / per pass / per scene“ an.
   - **Soll:**
     - kein „Run as“,
     - „Area“ fest auf „AOI only“,
     - genau ein Auftrag (Mosaik des Überflugs mit AOI).
   - **Sonderfall:** Bei Szenen mehrerer Überflüge sagt das Panel mit Grund, dass ein einzelner Auftrag nicht geht.
   - **Aufgabe:** Stufe A, nur Frontend. Ein ausgearbeiteter Entwurf liegt vor (`m4-33-zuschnitt-als-ein-objekt.md`, noch nicht im Repo). Beim Aufgreifen nach M4 bekommt er eine neue Nummer.
7. **Bandauswahl im Panel** (Otto, 22.10.2026).
   - **Ein Band:** Hat das Item bzw. Asset nur ein Band (etwa DEM `data` oder ein Ergebnis), ist es beim Öffnen des Panels automatisch gewählt.
   - **Alle Bänder:** Mit einem Knopf „Select all bands“ (und „Clear“) werden alle Bänder gewählt.
   - **Grenze:** Je Auftrag gilt die Obergrenze von 16 Assets bzw. Bändern (M4-07b F5). Hat ein Datensatz mehr, wählt „Select all“ keine stille Teilmenge, sondern sagt es mit Grund. Welche Assets dabei als Bänder zählen, prüft die Aufgabe; Hilfs-Assets wie `visual`, `thumbnail` oder `scl` zählen eher nicht. Bei Unklarheit ist das eine Frage an Otto.
   - **Aufgabe:** Stufe A, nur Frontend. Bänder aus dem Ausdruck kommen weiter automatisch dazu (M4-13c).
8. **Methodentext ins Rezept, `methods.txt` entfällt** (Otto, 22.10.2026).
   - **Soll:** `recipe.json` trägt den Methodentext im Block `provenance` als Feld `methods`. Dieser Block geht nicht in den Hash ein, und der Runner trennt ihn beim Einlesen ab (M4-16 F3). Die eigene Datei `methods.txt` entfällt im ZIP und im Runner.
   - **Folgen:**
     - die Definition der Download-Inhalte aus M4-30 und `TEXT_FILES` (M4-19a) anpassen,
     - der Runner schreibt den Text ebenfalls in seine `recipe.json`,
     - Link und Ausgang `methods` in der API: im Plan klären, ob sie bleiben oder entfallen,
     - Nachtrag in `adr/0014`.
   - **Kein Knopf zum Kopieren,** nirgends im Frontend (Otto, 22.10.2026). Die Einträge „Methods“ und „Copy“ der Jobliste entfernt UI-01 (§1 Punkt 12).
   - **Aufgabe:** Stufe A, Backend und Runner.
9. **Feste Gruppenköpfe in den Suchergebnissen** (Otto, 22.10.2026).
   - **Soll:** Beim Scrollen durch die Suchergebnisse bleibt der Kopf der aktuellen Gruppe oben stehen, solange Einträge dieser Gruppe sichtbar sind. Der Kopf der nächsten Gruppe schiebt ihn dann hinaus („sticky header“).
   - **Gilt mit allem, was im Kopf steht:** Name der Gruppe, Anzahl („loaded (of N)“), „Select all“ der Gruppe (M4-29) und Auf- und Zuklappen.
   - **Zu prüfen:** Der Kopf verdeckt keinen Eintrag, das Nachladen weiterer Treffer am Listenende greift weiter, und das Verhalten passt auch auf schmalen Bildschirmen.
   - **Aufgabe:** Stufe A, nur Frontend. Weil UI-01 die Leisten und Panels neu ordnet, kommt der Punkt nach UI-01 oder wird dort mit aufgenommen.

10. **Laufnummer und Band-Chips für Ergebnisse von Schritten** (Otto, 22.10.2026).
   - **Format (Otto):** Schritt-Titel „1. Band_Math_1“, „2. Normalize_2“ usw. Die Nummer steckt auch im Namen des Ergebnisbands: Schritt 1 gibt das Band `Band_Math_1` aus, nicht mehr `band_math`.
   - **Eigener Name (Otto):** Der Name des Ergebnisbands lässt sich je Schritt umbenennen, etwa `ndvi`. `Band_Math_1` ist nur die Vorgabe. Der eigene Name steht im Rezept, erscheint als Chip und im Titel und gilt in den folgenden Schritten. Im Plan zu klären: erlaubte Zeichen und Länge, keine Doppel innerhalb der Kette, keine Kollision mit Bandnamen des Datensatzes, Umbenennen nachdem spätere Schritte den alten Namen schon nutzen (mitziehen oder Hinweis).
   - **Gleiches Format wie die Bänder:** Das Ergebnisband eines Schritts erscheint in den folgenden Schritten als Chip im selben runden Format wie die Bänder des Datensatzes (M4-13c). Ein Klick fügt es in den Ausdruck ein, wie bei den Band-Chips. So ist klar, womit man weiterarbeiten kann.
   - **Nur verfügbare Bänder:** Ein späterer Schritt zeigt nur die Chips, die nach den vorigen Schritten noch vorhanden sind (nach Band math nur dessen Ergebnisband, nach `mask` die Bänder ohne die Schicht). Die Regel kommt aus dem Backend, das Frontend baut sie nicht nach (wie in M4-18b).
   - **Folgen, im Plan zu klären:**
     - Der Bandname ändert Rezept, Hash und Bytes des Ergebnisses (Bandbeschreibung in `result.tif`), gehört also in die Versionierung (`op_version` bzw. `earthx.__version__`), mit Nachtrag in `adr/0014`.
     - Woher die Laufnummer kommt (Platz in der Kette, ab 1), und ob alte Rezepte mit `band_math` weiter angenommen werden.
     - Groß- und Kleinschreibung sowie erlaubte Zeichen gegen die bestehenden Regeln für Bandnamen im Ausdruck prüfen; bei Konflikt Frage an Otto.
     - Kachel-Pfad (M4-18b), Runner und Methodentext ziehen mit.
   - **Aufgabe:** Stufe B (ändert Ergebnis-Bytes), Backend und Frontend.

11. **Normalize klarer und mit mehreren Methoden** (Otto, 22.10.2026).
   - **Klarer:** Im Panel steht kurz, was der Schritt tut, mit Beispiel (etwa „NDVI −1…1 → 0…1“) und der Formel der gewählten Methode. Die Felder tragen verständliche Namen und Hilfetexte (Englisch).
   - **Methoden, Vorschlag:**
     - linear von einem festen Bereich auf einen anderen (heute, `normalize` v1),
     - Z-Score: (x − Mittelwert) / Standardabweichung,
     - über Perzentile, etwa 2–98 %, auf einen Zielbereich, mit Clip,
     - eventuell robust über Median und Interquartilsabstand.
   - **Kern der Sache, im Plan zu klären:** Z-Score und Perzentile brauchen Statistik über die ganze Eingabe.
     - Im Job heißt das zwei Durchgänge oder eine Statistik vorab; Rechenzeit, Speicher (500 MB) und Bitgleichheit (zweimal gerechnet, Cloud gegen Runner) müssen halten.
     - In der Kachel-Vorschau darf die Statistik nicht je Kachel gerechnet werden, sonst passen Kacheln nicht zusammen und die Vorschau weicht vom Job ab. Optionen: Statistik einmal je Auftrag vorab, oder Vorschau nur für die lineare Methode.
     - Ob die Werte (Mittelwert, Perzentile) im Rezept stehen, damit Rezept und Ergebnis eindeutig sind, oder erst im Lauf entstehen.
     - Perzentile deterministisch wie in M4-32 (festes Histogramm), Weg wiederverwenden.
     - Je Band oder ein Bereich für alle Bänder.
   - **Vorher:** Stand der Technik mit Quellen recherchieren (Compute-Relevanz), etwa rio-tiler/GDAL-Statistik, scikit-learn-Skalierer, übliche Verfahren in der Fernerkundung.
   - **Aufgabe:** Stufe B, Backend und Frontend; neue `op_version` bzw. neuer Parameter `method`, Nachtrag in `adr/0014`, Kostenfaktor messen.

12. **Anheften ohne zweiten Klick** (Otto, 22.10.2026, aus M4-17c).
   - **Heute:** „Add to layers“ bei einer Teilauswahl, deren Mosaik noch lädt, weist ab („The mosaic of this time step is still loading — add it to the layers in a moment.“); erst ein zweiter Klick heftet an.
   - **Soll:** Der Knopf zeigt „Loading…“ und heftet den Layer automatisch an, sobald das TileJSON da ist. Bei einem Fehler bleibt die bestehende Meldung.
   - **Aufgabe:** Stufe A, nur Frontend; Test, der am heutigen Code scheitert.

13. **`docs/plans/` je Meilenstein aufräumen** (Otto, 22.10.2026).
   - **Soll:** ein Unterordner je Meilenstein, etwa `docs/plans/m0/` … `docs/plans/m4/`, `docs/plans/vp3/` (UI-01, UI-02); Dateinamen bleiben.
   - **Zeitpunkt:** nach M4-20 und vor dem Start von UI-01, wenn keine Session läuft. Grund: Startsätze und Verweise laufender Sessions zeigen auf die alten Pfade.
   - **Umfang:**
     - Verschieben mit `git mv`, damit die Historie erhalten bleibt.
     - Alle Verweise nachziehen: Pläne untereinander, `adr/`, `ENTSCHEIDUNGSLOG.md`, `KLAERUNGEN.md`, `projektplan.md`, `architekturplan.md`, README, Kommentare im Code und in Tests. Verweise in `CLAUDE.md`, `.github/` und `.claude/` nur mit Ottos Erlaubnis; die Session listet sie im PR.
     - Prüfung, dass kein Verweis auf `docs/plans/<datei>` ohne Unterordner übrig ist (Suche im PR belegen), am besten als kleiner Test.
     - Neue Startsätze lauten dann etwa „Führe Aufgabe UI-01 aus `docs/plans/vp3/ui-01-app-rahmen.md` aus.“
   - **Zu klären im PR:** wohin Querschnittsdateien ohne Meilenstein gehören (etwa Zusätze über mehrere Aufgaben); Vorschlag: zum Meilenstein, in dem sie entstanden sind.
   - **Aufgabe:** Stufe A, nur Doku, Sonnet mittel.

14. **Schnellrechnungen (Index-Knöpfe)** (Otto, 22.10.2026; Grundlage `projektuebersicht.md` §8: „datensatzspezifische Presets … bauen auf Band-Math auf“).
   - **Soll:** An einem Layer eines passenden Datensatzes (etwa „Crop & merge to AOI“ von Sentinel-2) gibt es Knöpfe für häufige Indizes, etwa NDVI, NDWI, NDSI, NBR, EVI. Ein Klick erzeugt einen ganz normalen Band-math-Schritt mit Vorschau; Start als Job wie gewohnt.
   - **Kein zweiter Weg:** Die Knöpfe füllen nur das Rezept. Vorschau, Job, Cache, Runner, Methodentext und `recipe.json` bleiben dieselben.
   - **Je Datensatz, nicht im Code:** Die Bandnamen unterscheiden sich je Quelle (COG gegen EOPF-Zarr). Die Presets stehen deshalb als Daten in der Registry je Datensatz (Name, Ausdruck, Wertebereich, Colormap-Vorgabe, Quelle der Formel); nur Datensätze mit passenden Bändern zeigen sie. Kein datensatzspezifischer Code.
   - **Quellen:** Formeln mit Beleg, etwa Awesome Spectral Indices (Montero et al., 2023, *Scientific Data*) oder Index DataBase; bei Indizes mit Konstanten (EVI) die Werte mit Quelle.
   - **Zu klären im Plan:** Welche Indizes zuerst; ob die Knöpfe am Layer, im Panel oder an beiden Stellen sitzen (Abstimmung mit UI-01); ob ein Preset die Bänder automatisch wählt (Punkt 7) und den Ergebnisnamen setzt (Punkt 10, etwa `NDVI`); Verhalten bei Mosaik (Punkt 4) und mit `mask` davor („NDVI cloud-free“ als Preset-Kette?).
   - **Aufgabe:** Stufe B (Registry-Feld, Panel), Backend und Frontend.

15. **Nur ein Sentinel-2-L2A-Datensatz sichtbar** (Otto, 22.10.2026).
   - **Wunsch:** Die Plattform bietet nicht mehrere Datensätze an, die dasselbe zeigen. Heute gibt es `sentinel-2-c1-l2a` (Earth Search, COG) und `sentinel-2-l2a-zarr3` (EOPF, Zarr). Otto will den Zarr-Datensatz loswerden.
   - **Warum zuerst eine Vorlage (Stufe C):** Der Zarr-Datensatz trägt Belege und Entscheidungen: zweites Format (`adr/0007`), Zarr-Vergleich T1 ↔ T2 (`adr/0014` §15d, Kriterium 1 der M4-Abnahme), Tests und Fixtures, Prüfanleitungen, `SCL_20m:scl` in der Maske (M4-18c).
   - **Optionen für die Vorlage:**
     1. EOPF-Datensatz aus Katalog und Registry entfernen; der Zarr-Reader bleibt als generische Fähigkeit mit synthetischen Tests für künftige Zarr-Quellen (`ADDING_ESA_DATASETS.md`).
     2. Ein sichtbarer Datensatz „Sentinel-2 L2A“ mit zwei Quellen dahinter (eine primär, eine als Rückfall, `adr/0005` föderierte Suche); der Nutzer sieht nur einen Eintrag.
     3. Earth Search entfernen und EOPF behalten.
   - **Vorher recherchieren, mit Quellen:** Betriebsstatus des EOPF-Zarr-Dienstes (Muster oder operativ), Zeitplan von Earth Search v2 (Punkt „Earth Search v2“ unten), Abdeckung und Aktualität beider Quellen, Unterschiede bei Skalierung (Zarr-Item ohne `raster:scale`), Bandnamen und Prüfsummen (`adr/0014` §3.1, Cache-Fähigkeit).
   - **Folgen in jedem Fall:** Abnahmebelege aus M4 bleiben gültig (sie belegen den Stand von M4); Registry, Fixtures, Tests, Prüfanleitungen und Doku nachziehen; bestehende Permalinks und `recipe.json` mit dem alten Datensatz: abweisen mit Grund oder umleiten (im Plan klären).
   - **Aufgabe:** Stufe C (Entscheidungsvorlage), danach Umsetzung.

16. **Einheiten für die übrigen Sentinel-2-Assets** (aus M4-19b, 23.10.2026).
   - **Heute:** `aot`, `wvp`, `cloud`, `snow` und `preview` haben in der Registry keine Einheit (`earthx:band_units`), weil die Session keine Quelle dafür gelesen hat.
   - **Aufgabe (Stufe A):** Einheiten mit Quelle nachtragen (Produktspezifikation Sentinel-2 L2A bzw. Item-Metadaten); wo keine Einheit sinnvoll ist (etwa `preview`), das bewusst vermerken. Hinweis: Eine Korrektur der Einheit ändert den Hash (`adr/0014` §15n), also einmal kein Cache-Treffer.

17. **„Clear all“ wird „Clear search results“** (Otto, 24.10.2026).
   - **Soll:** Der Knopf in den Suchergebnissen heißt „Clear search results“ und löscht nur die Ergebnisliste. Danach öffnet sich wieder das Control-Panel.
   - **Bleibt bestehen:** alle Sucheinstellungen, also AOI, Zeitraum, Datensatzwahl, Filter (etwa Wolkenbedeckung). Ein neuer Klick auf „Search“ sucht mit denselben Einstellungen.
   - **Im Plan zu klären:** was mit angehefteten Layern, offener Ansicht (Mosaik aus M4-17) und Jobs passiert (Vorschlag: angeheftete Layer und Jobs bleiben, die offene Ansicht schließt); wo man AOI und Einstellungen künftig zurücksetzt (eigener Knopf im Control-Panel, falls es keinen gibt); Abstimmung mit UI-01 (linke Leiste, Control-Menü).
   - **Aufgabe:** Stufe A, nur Frontend; Test, dass nach dem Löschen alle Einstellungen erhalten sind.

18. **Abspielen in der Timeline ohne Lücken** (Otto, 24.10.2026).
   - **Soll:** Bei „Play“ wechselt die Karte erst zum nächsten Zeitschritt, wenn dessen Kacheln für den sichtbaren Ausschnitt geladen sind. Zwischen zwei Bildern ist nie die Basemap zu sehen.
   - **Beschriftung:** Während des Abspielens steht nur das Datum der Gruppe (des Überflugs), kein Szenenname.
   - **Im Plan zu klären:**
     - Vorladen des nächsten Schritts im Hintergrund (unsichtbarer Layer oder Kachel-Cache der Kartenbibliothek), Speicher- und Anfrage-Grenzen, Wirkung auf den `tiler` (Mosaik-Kacheln aus M4-17).
     - Mindestdauer je Bild und was bei langsamem Laden passiert (das aktuelle Bild bleibt stehen; Hinweis „Loading…“).
     - Verhalten bei einem Schritt, der nicht lädt (Zeitlimit, überspringen mit Hinweis).
     - Verhalten beim Zoomen oder Verschieben während des Abspielens.
   - **Aufgabe:** Stufe A, nur Frontend; Test, dass der Wechsel erst nach dem Laden erfolgt (mit verzögerten Kacheln).

19. **Auto stretch der Vorschau über die AOI** (Otto, 24.10.2026).
   - **Heute (M4-19c):** Die Messung für die Farbskala der Vorschau gilt für die erste Szene der Karte, auch bei „AOI only“ für die ganze Szene. Das Job-Ergebnis nimmt dagegen die Statistik über die AOI-Maske (M4-32). Vorschau und Ergebnis können sich deshalb unterscheiden.
   - **Soll:** Bei „AOI only“ misst auch die Vorschau über die AOI, damit Vorschau und Ergebnis dieselbe Farbskala zeigen.
   - **Harte Grenze:** Keine AOI in URLs oder Logs. Die AOI geht nur im Body an den `tiler` (etwa `POST /statistics` wie bei rio-tiler, mit der Geometrie als GeoJSON), nie als Query; Caching dann über einen Hash im Body, der nicht geloggt wird.
   - **Im Plan zu klären:** Schnittstelle (POST-Route, Größen- und Punktgrenze der Geometrie wie bei der Annahme), Cache-Schlüssel ohne AOI im Klartext, Messung über mehrere Szenen bzw. Mosaik eines Überflugs, gleiche Methode wie im Job (festes Histogramm, M4-32a) damit die Werte übereinstimmen, Kosten.
   - **Aufgabe:** Stufe B (neue Route im `tiler`, Datenschutz), Backend und Frontend.

20. **Processing-Panel klarer gegliedert** (Otto, 24.10.2026).
   - **Soll:** Die Bereiche „Bands“, „Processing steps“, „Output“ und „Preview“ sind deutlich voneinander abgesetzt (etwa eigene Karten oder Abschnitte mit Überschrift, Abstand, Trennlinie, ggf. einklappbar).
   - **Im Plan zu klären:** Gestaltung in Hell- und Dunkelmodus, Reihenfolge, schmale Bildschirme; Abstimmung mit UI-01 (größeres Fenster, linke Leiste) und mit den Punkten 7, 10 und 14 (Bandauswahl, Band-Chips der Schritte, Index-Knöpfe).
   - **Aufgabe:** Stufe A, nur Frontend; Prüfung im echten Browser (Playwright), nicht nur jsdom.
21. **Einheitliches Zahlenformat in der ganzen Web-App** (Otto, 24.10.2026).
   - **Soll:** Angezeigte Zahlen haben höchstens drei Nachkommastellen. Sehr kleine (und sehr große) Beträge erscheinen wissenschaftlich, etwa 0.000000052 → `5.2e-8`.
   - **Eine Stelle:** eine gemeinsame Formatierfunktion im Frontend für alle Anzeigen (Min/Max der Vorschau und des Ergebnisses, Statistik, Pixelwerte, Schätzung, Auflösung usw.), keine verstreuten `toFixed`.
   - **Im Plan zu klären:**
     - Schwellen für die wissenschaftliche Form (Vorschlag: Betrag < 0.001 außer 0, und ≥ 1e6) und Anzahl gültiger Stellen dort (Vorschlag: bis zu drei, ohne nachgestellte Nullen).
     - Eingabefelder: Was angezeigt wird, ist auch der angewandte Wert (keine versteckte Genauigkeit), oder intern bleibt der volle Wert. Vorschlag: Vorgaben aus der Statistik werden gerundet übernommen; was der Nutzer tippt, gilt genau so.
     - Ausnahmen: Koordinaten, IDs, Daten, Zählungen, Dateigrößen und Werte in `recipe.json`/API bleiben unberührt (nur die Anzeige ändert sich).
   - **Aufgabe:** Stufe A, nur Frontend; Tests für die Grenzfälle (0, negative Werte, 0.001, 0.0009, 1e6, NaN).

22. **Weniger Text in der Oberfläche** (Otto, 24.10.2026).
   - **Grundsatz:** Die Oberfläche zeigt so wenig Text wie möglich. Erklärungen, Hinweise und Gründe stehen im Tooltip (Hover und Tastaturfokus, für Screenreader erreichbar), nicht als Absatz unter Knöpfen oder Feldern – wie bei „Share processing“ (M4-19e).
   - **Sichtbar bleiben nur:** Beschriftungen, Werte, Fehlermeldungen, die eine Handlung verlangen, und Pflichtangaben (Attribution, Lizenz, Datenschutzhinweis).
   - **Umfang:** Durchgang durch Panel, Suchergebnisse, Layer-Manager, Control-Panel; Liste der gekürzten bzw. verschobenen Texte im PR.
   - **Aufgabe:** Stufe A, nur Frontend, zusammen mit Punkt 20 oder in UI-01; gilt ab sofort als Regel für jede neue Oberfläche.

### In UI-01 aufgenommen (20.–22.10.2026)

- Reihenfolge im Layer-Manager greift manchmal nicht (UI-01 §1 Punkt 10, Diagnose mit Test zuerst; Otto liefert die Schritte zum Nachstellen).
- Klick auf einen Ergebnis-Layer öffnet die Darstellung: vmin, vmax, Colormap, Vorgabe aus M4-32 (UI-01 §1 Punkt 11).
- Gleiche Breite der Layer-Zeilen mit festen Knopfpositionen (Punkt 8).
- Download eines Ergebnisses aus dem Layer-Manager (Punkt 9).
- Je fertigem Job nur „Download (ZIP)“, kein „Methods“, kein „Copy“ (Punkt 12).
- Handbereich der Farbskala je Job dauerhaft speichern (§3 Punkt 1).
- Stapelung zwischen Überflügen: Ansicht und angeheftete Layer stapeln verschieden (bekannte Grenze aus M4-17c §15), Prüffall in UI-01 §1 Punkt 10.

### Offen im Entscheidungslog (bewusst nach M4)

23. Earth Search v2: `sentinel-2-c1-l2a` wird durch `sentinel-2-l2a` ersetzt (Termin offen, Quelle im Log von M4-12a).
24. Originale als ZIP über die Plattform. Das kostet Bandbreite und gibt Daten über die Plattform weiter, und ein Abbruch lässt sich nicht fortsetzen (M4-11b-2).
25. Festes nodata je Ganzzahltyp für Quellen ohne nodata, dazu die Kollision gültiger Werte mit nodata nach dem Klemmen (M4-26).
26. Triage-Routine bei rotem Live-Smoke (projektplan §6, nicht eingerichtet; M4-27 §4).
27. Punkte aus S3 (M4-Plan Fassung 3):
    - Export-Job für Zarr blockweise,
    - schnelleres COG-Profil,
    - Laufzeitdeckel an echten Läufen kalibrieren,
    - Zähler der Verbindungen je Lauf,
    - Job-Schnittstelle in eigenem Prozess,
    - Eingaben per Referenz (siehe Punkt 5),
    - Datei-Cache des Runners.
28. CI: Umstellung von `ubuntu-latest` auf Ubuntu 26, Node-20-Warnungen der Actions, kein `cancel-in-progress`. Entschieden, `.github/` nicht zu ändern (19.10.2026). Neu entscheiden, sobald die CI ohne Codeänderung an Systempaketen scheitert.

### Danach geplant

29. VP3: UI-01 (App-Rahmen, Processing-Manager, Batch, „Download all“, Layer-Manager mit den Punkten 8–12), dann UI-02 (Basemap, Projektion). Siehe `projektplan.md` v1.5.

### Verworfen bzw. nur bei Bedarf

- Zarr im Viewer generell durch COG ersetzen (Daten umwandeln): nein. Davon getrennt steht Punkt 15 (Zarr-Datensatz als Doppel entfernen). Jeder Datensatz bleibt bei seiner Quelle. Nur falls Zarr im Viewer langsam auffällt, folgt eine Messung (Stufe C) zu GeoZarr-Multiscales und Quicklooks.
- „Replace source layer“ für Vorschau und Job-Ergebnis: von Otto entfernt (20.10.2026).
- Knopf zum Kopieren des Methodentexts: von Otto abgelehnt (22.10.2026).

### Ergänzt aus Log und Plänen (nicht in der Datei oben)

Geprüft gegen die Zeilen „offen“ im `ENTSCHEIDUNGSLOG.md`, die Abschnitte „Nicht
in M4“ (`m4-processing-kern.md` §2) und „Nach M3 vorgemerkt“ (`m3-15-abnahme.md`
§12) und die Pläne `m4-*.md`. Punkte, die oben schon stehen (etwa Earth Search
v2, Originale als ZIP, festes nodata, Punkte aus S3, CI), sind nicht noch einmal
aufgeführt.

**Aus M4 selbst**

E1. **Prüfanleitung B von M4-17, Schritte 3–6, gegen eine echte Quelle** (Log 22.10.2026, „offen“).
   - A hat Otto bestanden, B Schritte 1–2 ebenfalls (Abschnitt 7); das Ergebnis der Schritte 3–6 reicht Otto nach und kommt als Log-Zeile.
   - Belegt ist sonst die Verdrahtung mit synthetischen Kacheln und einer echten MapLibre-Karte (`plans/m4-17-mosaik-kachel-pfad.md` §14, §15).
E2. **Ein gescheiterter Job nennt keinen konkreten Grund** (Log 12.10.2026, „M4-13b, offen (2)“).
   - Die Queue speichert nur `error_kind`; Titel und Detail der API sind fest, der Text der Ausnahme geht verloren (Absicht, `adr/0014` §4.7).
   - Vorschlag im Log: je Fehlerart ein fester Satz ohne Werte aus `error_kind` und einem Unterschlüssel; ändert Worker, Queue und API.
   - Aufgabe: eigene Aufgabe (`plans/m4-13-processing-panel.md` §13).
E3. **Ein Cache-Treffer kann wenige ULP von einer Neuberechnung abweichen,** wenn Worker auf CPUs mit anderen SIMD-Erweiterungen laufen; der Cache-Schlüssel (`adr/0014` E2) enthält die CPU-Stufe nicht (Log 05.10.2026, Nebenfund M4-05 (2), „offen“). Hängt mit der Zusage „gleiche Bits“ zusammen (README, „Lokaler Runner“; Abschnitt 1, Grenzen).
E4. **Klassenbänder sind in Items nicht erkennbar** (Log 12.10.2026, „M4-13b, offen (1)“): `scl`, `cloud`, `snow` würden mit bilinear empfohlen, richtig wäre `nearest`. Im Log „aufgehoben“: Das Panel empfiehlt kein Resampling mehr; der Rest gilt nur für eine spätere Automatik (Adapter setzt eine Klassifikation) und blieb für M4-23 offen.
E5. **Hash im Image gegen den Kern aus derselben CI** ist nicht nachgewiesen, nur über gleiche Schichten und Versionen geschlossen (`plans/m4-16-lokaler-runner.md` §10.1, „Offen“). Ottos Beleg vom 24.10.2026 füllt die Lücke von Hand. Offen auch: Podman nicht geprüft, ARM außerhalb der Zusage (README).
E6. **Worker-Einstieg in `jobs` darf `datasets` nicht importieren;** betrifft den ruhenden Quad-Pol-Operator, zu lösen bei dessen Registrierung (Log 02.10.2026, `adr/0014` §12). `decomp.py` ruht weiter (ENTSCHEIDUNGEN §3).
E7. **Basiskarte im Permalink:** kommt mit UI-02 (siehe Punkt 29; Log 24.10.2026, M4-19e, Antwort 1); in M4 steht sie nicht in der Ansicht.

**Aus „Nicht in M4“ (`m4-processing-kern.md` §2) und Planständen, weiter offen**

| Punkt | Wohin | Quelle |
|---|---|---|
| Login, Quotas, Ratenbegrenzung je Nutzer oder IP | M6 (D6) | §2; `m3-15-abnahme.md` §12 |
| Datacube (Kombination mehrerer Datensätze mit Lizenzprüfung) | M6 | §2; `projektplan.md` M6 |
| Verbundener Runner und Runner-Auswahl in der Oberfläche | 7f | §2; `adr/0016` |
| Runner-Image veröffentlichen (Registry) | nicht in M4 (Q12), später | §2; `adr/0016` |
| Container-Stufe T3 und externe Engines | M7 | §2 |
| Bug-Report Stufe 2 und 3 (M4 liefert die Rezept-ID als Grundlage) | offen (D9, Q15) | §2; `m3-15-abnahme.md` §12 |
| Health-Status je Quelle, Harvester-Zeitplan, Zählwürfel, STAC-API-Dialekt | M5 | §2; `adr/0011` F6 |
| COG-Header-Cache; Uvicorn-Worker des `tiler` | M5 / offen | §2; Log 20.09.2026 |
| CQL2 je Collection ausweisen (nirgends ausgewiesen) | offen | M3-13, `adr/0005` Regel VI |
| Zenodo als Metadatenquelle; Hybrid-Suche; Datensatz-Browser; Verfügbarkeits-Zeitleiste | M5 | `m3-15-abnahme.md` §12 |
| Helle Basiskarte passend zum Theme; Viewer-Pakete Swipe und Export | offen (D10) / UI-02 | `m3-15-abnahme.md` §12; `m2-format-und-viewer.md` |

**Vor dem ersten öffentlichen Deployment** (Stand `m3-15-abnahme.md` §12, in M4
nicht neu entschieden): AGPL §13 (Link zum Quellcode für Nutzer); Nominatim und
ODbL (Bedingungen des öffentlichen Dienstes, gecachte Treffer, AOI im ZIP);
Copernicus-Attributionstext und Sentinel Legal Notice (zusammen mit Punkt 1
oben: das Jahr); Nutzungsbedingungen und Haftungsausschluss der Plattform, Esri
World Imagery (Basiskarte); die Lizenz-Einstufung jedes Datensatzes bleibt bei
Otto (B11).

**Erledigt in M4, nicht mehr offen:** weitere Resampling-Methoden für `reproject`
(M4-24, #158; war in S3); Frist für Rezepte hinter Permalinks (30 Tage ab
Erstellung, M4-19e); Zeilenenden (M4-21); Kernfeld `bands` (M4-23); die drei
Testlücken (M4-22); Lock-Datei (M4-00b).

---

## 15. Fragen an Otto

Nummeriert, Empfehlung zuerst.

1. **M4 abnehmen?**
   - (1) **Empfehlung:** M4 mit den Belegen in Abschnitt 1–10 abnehmen. Kriterium 1 trägt Ottos Hash-Vergleich vom 24.10.2026 (Runner 0.4.2+gcb03706) neben `test_compare` und dem Schichtvergleich; die benannte Grenze (Image gegen Kern aus derselben CI) ist damit von Hand geschlossen.
   - (2) Erst abnehmen, wenn die Läufe in Abschnitt 11 (A bis C) durch sind.
   - (3) Anders.
2. **Prüfanleitung B von M4-17, Schritte 3–6** (E1; Kriterium 7). A ist bestanden, B Schritte 1–2 auch.
   - (1) **Empfehlung:** Die Abnahme hängt nicht daran. Du reichst das Ergebnis der Schritte 3–6 nach (die Anleitung steht in `plans/m4-17-mosaik-kachel-pfad.md`); es kommt als Log-Zeile.
   - (2) Vor der Abnahme prüfen.
   - (3) Anders.
3. **Lesart von Kriterium 3 („ohne `gateway`“).**
   - (1) **Empfehlung:** Es heißt: `processing` importiert `gateway` nicht direkt (Vertrag mit direkten Importen). Das Lesen der Datenquellen läuft über `readers`, das `gateway` nutzt, wie es `CLAUDE.md` erlaubt. Keine Änderung.
   - (2) Auch indirekt verbieten. Das bräche das Lesen und verlangt eine Änderung der Architektur.
   - (3) Anders.
4. **Arbeitsweise nach M4 (Projekte in Claude Code, nicht entschieden).**
   - (1) **Empfehlung:** Unverändert lassen (ein Branch, ein Draft-PR, Startsatz je Aufgabe), bis UI-01 abgeschlossen ist, dann neu entscheiden: UI-01 und UI-02 bauen auf der bestehenden Arbeitsweise und den Startsätzen auf.
   - (2) Sofort wechseln; dann zuerst Punkt 13 im Abschnitt 14 (`docs/plans/` je Meilenstein), weil sich die Pfade der Startsätze ändern.
   - (3) Anders.
5. **Reihenfolge nach M4** (Abschnitt 14 lässt sie offen).
   - (1) **Empfehlung:** Punkt 13 (`docs/plans/` aufräumen, ohne laufende Session), dann UI-01 und UI-02; Punkt 1 (Jahr der Attribution) und Punkt 2 (Sortierung von Zuschnitt und Export) als Stufe-A-Aufgaben daneben, weil Punkt 1 vor einem öffentlichen Deployment geklärt sein muss.
   - (2) Zuerst Punkt 1 und 2, dann 13.
   - (3) Anders.

---

## Zusammenfassung

Alle zehn Kriterien aus `docs/plans/m4-processing-kern.md` Abschnitt 5 sind mit
Test-, Code- und Log-Belegen erfüllt; Kriterium 1 trägt die drei verlangten
Belege (`test_compare` aus M4-16a, der Schichtvergleich in der CI aus M4-16b und
Ottos lokaler Hash-Vergleich vom 24.10.2026 mit Runner 0.4.2+gcb03706:
`result.tif` und `mask.tif` je True). Offen und bei Otto: die lokale Prüfung
(Abschnitt 11), die Schritte 3–6 der Prüfanleitung B von M4-17 gegen eine echte Quelle
(Frage 2; A und B 1–2 hat Otto bestanden) und das Löschen nach 7 Tagen, das in keinem Lauf zu beobachten ist
(Kriterium 4). Die Läufe der Sitzung (Abschnitt 12) sind grün. Mit Ottos Abnahme
wird M4 im Plan als abgeschlossen markiert und die Log-Zeile „M4 abgenommen“ mit
Datum und PR-Nummer ergänzt.
