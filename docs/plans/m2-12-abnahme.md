# M2-12 — Abnahme von M2: Belege je Kriterium

**Ziel:** Otto kann M2 anhand dieses Berichts und des zugehörigen PR abnehmen,
ohne Code zu lesen.
**Ort im Repo:** `docs/plans/m2-12-abnahme.md`
**Grundlage:** `docs/plans/m2-format-und-viewer.md` Abschnitt 5 ("Abnahme von
M2"), Stand nach dem Merge aller Aufgaben bis einschließlich M2-17 und V-1 bis
V-4 (`main`, Commit `5e40d04`, Fassung 5 des Plans, PR #69–#71). M2-12 ist
laut Fassung 5 die letzte offene Aufgabe des Schnitts.

Für dieses Kriterium gilt eine Einschränkung durch die Aufgabenstellung:

- **Kriterium 3:** Belegt wird nur die Coverage-**Route**; die Qualität der
  Heatmap im Frontend ist nicht Teil dieser Abnahme (D26).
- **Kriterium 1:** Für den Zarr-Datensatz genügt der Lesepfad gegen das
  synthetische Zarr aus M2-09a; die Abnahme hängt nicht am Fortbestand der
  externen Quelle `sentinel-2-l2a-zarr3` (D24). Die reale Quelle ist zusätzlich
  belegt (Tests gegen den realen Adapter/Registry-Eintrag), aber nicht
  Voraussetzung.

Alle Befehle unten liefen aus dem Repo-Wurzelverzeichnis in dieser Sitzung; die
Ergebnisse stehen unter "Testlauf dieser Sitzung" am Ende.

---

## 1. Zwei Formate (COG und Zarr): suchen, Quicklooks, Kacheln, Download

Beide Datensätze stehen in der Registry (`backend/earthx/catalog/datasets.py`):

- `SENTINEL_2_L2A` (`sentinel-2-c1-l2a`, `format=DataFormat.COG`, Zeilen
  48–206).
- `SENTINEL_2_L2A_ZARR3` (`sentinel-2-l2a-zarr3`, `format=DataFormat.ZARR`,
  Zeilen 218–366, `earthx:maturity = staging`, D23).

**Suche gegen beide, föderiert:**
`backend/tests/integration/test_api_federating.py:23` importiert beide
Registry-Einträge; Zeilen 248 und 260 suchen über beide Datensätze hinweg
(D8: getrennt je Datensatz, kein Mischen).

**Kacheln — dieselbe URL-Form für beide Formate:**
`backend/tests/earthx/api/test_tiler_zarr.py::test_the_url_a_client_builds_is_the_same_for_both_formats`
(Zeilen 159–163) vergleicht die Kachel-URL für den Zarr- und den
COG-Datensatz bei identischem Muster; Zeilen 143–150 bestätigen eine
tatsächlich gerenderte PNG-Kachel aus dem Zarr-Store.

**Zuschnitt-Download — auch für Zarr:**
`backend/tests/earthx/access/test_download_zarr.py` (95 Zeilen) baut den
Zuschnitt gegen einen synthetischen Zarr-Store auf und prüft den ZIP-Inhalt.

**Quicklooks:** Für `sentinel-2-c1-l2a` lädt das Frontend das Thumbnail direkt
vom Asset-Host (D14, `AccessInfo.cors = True`); für `sentinel-2-l2a-zarr3`
gibt es keinen Quicklook der Quelle (registriert, `earthx:maturity`), der
Ersatz kommt aus dem Kachelpfad auf der gröbsten freigegebenen Stufe (M2-10,
ENTSCHEIDUNGSLOG 2026-09-22).

**Coverage-Heatmap vorhanden und einschaltbar, standardmäßig aus:**
`frontend/src/components/LayerManager.tsx:46-60` — eigene Zeile mit
Augensymbol, ohne Vorauswahl (Kommentar "Off by default (M2-07c)"). Die
Qualität der Heatmap (Gitterstufe, Footprint-Umschaltpunkt) ist laut
Aufgabenstellung **nicht** Teil dieser Abnahme (D26).

**Zarr-Lesepfad unabhängig von der externen Quelle (D24):**
`backend/tests/earthx/readers/test_zarr_reader.py` liest ausschließlich gegen
ein per Skript erzeugtes synthetisches Mini-Zarr (`tests/earthx/readers/
mini_zarr.py`, In-Memory-Store); kein Netzzugriff, kein Abhängen von
`data.eodc.eu`. Damit besteht dieser Teil von Kriterium 1 unabhängig davon,
ob die echte `sentinel-2-l2a-zarr3`-Quelle online bleibt.

### Lokale Vorführung

Kriterium 1 verlangt ausdrücklich, dass Otto lokal prüft, nicht nur, dass
Tests grün sind ("Otto prüft lokal", Abschnitt 5 Punkt 1 des Plans). Otto hat
das am 22./23.09.2026 während der Reviews von M2-10, V-1 bis V-4 und M2-17 im
laufenden Viewer getan und dabei für **beide** Datensätze bedient: Suche,
Quicklooks (`sentinel-2-c1-l2a`, direkt vom Asset-Host) bzw. Ersatzkacheln auf
der gröbsten freigegebenen Stufe (`sentinel-2-l2a-zarr3`, ohne Quicklook der
Quelle), Ansicht in voller Auflösung, den Zuschnitt-Download als ZIP, die
Szenensuche per Namen (M2-17) sowie Globus und Theme-Umschalter (V-1). Die
einzelnen Befunde aus diesen Sitzungen und ihre Behebung stehen in
`docs/ENTSCHEIDUNGSLOG.md` unter den Einträgen zu M2-10, V-1 bis V-4, M2-16
und M2-17 sowie in den Nachbesserungsrunden in
`docs/plans/m2-format-und-viewer.md` (V-6 bis V-12, M2-17b) — sie sind selbst
der Beleg, dass ein Mensch beide Datensätze tatsächlich bedient hat, nicht nur
ein automatisierter Test.

Schritte, mit denen ein Dritter dieselbe Vorführung nachvollzieht, stehen in
`README.md` Abschnitt 2, Unterabschnitt "Den Viewer starten (Frontend)":
`docker compose up`, danach `cd frontend && npm run dev`,
`http://localhost:5173` öffnen, zwischen den beiden Datensätzen wechseln, je
eine AOI suchen oder eine Szene per Namen finden, in voller Auflösung
ansehen, herunterladen, Globus/Theme umschalten und in "Layers" die
Coverage-Heatmap einschalten.

**Ergebnis:** Kriterium 1 erfüllt.

---

## 2. Dieselbe Kachel-URL liefert dasselbe Bild; kein Endpunkt nimmt eine freie URL an

**Determinismus der URL-Form über beide Formate:**
`backend/tests/earthx/api/test_tiler_zarr.py::test_the_url_a_client_builds_is_the_same_for_both_formats`
(s. o.) — die Kachel-URL hängt an `dataset`/`item`/`asset`, nie an einem
freien `url`-Parameter.

**Kein Endpunkt nimmt eine freie URL an (OpenAPI-Schema + Umgehungsversuche):**
- `backend/tests/earthx/api/test_tiler.py::test_no_endpoint_declares_a_url_parameter`
  (Zeilen 114–125) parst das OpenAPI-Schema und prüft, dass kein
  Query-Parameter `url` (oder ein `url` enthaltender Name) an irgendeinem
  Endpunkt existiert.
- `backend/tests/earthx/api/test_tiler.py::test_an_address_smuggled_into_the_query_is_not_read`
  (Zeilen 150–158) versucht drei Umgehungen (`url`, `src_path`, `path`) als
  zusätzliche Query-Parameter; FastAPI verwirft sie, ausgeliefert wird immer
  nur das vom Katalog aufgelöste Asset.
- Ein Asset-Host, der nicht in der Registry (`asset_hosts`) steht, wird von
  `gateway` abgewiesen (M2-04-Abnahme, unverändert; Kriterium 6 unten belegt
  den Mechanismus).

**Ergebnis:** Kriterium 2 erfüllt.

---

## 3. Coverage-Route: `complete`/`truncated`/`sample`, Latenz

**Nur die Route ist Gegenstand dieser Abnahme (D26); die Heatmap-Qualität im
Frontend ist es nicht.**

**Pflichtfeld mit den drei Werten:**
`backend/earthx/api/coverage_route.py:215` liefert
`"completeness": result.completeness.value`. Tests:
- `backend/tests/earthx/api/test_coverage_route.py:112` —
  `assert body["completeness"] == "complete"` (Earth-Search-Pfad,
  `UPSTREAM_AGGREGATION`).
- `backend/tests/earthx/api/test_coverage_route.py:214` —
  `assert body["completeness"] == "sample"` (`sentinel-2-l2a-zarr3`,
  `CoverageProvider.SAMPLE`, weil die Quelle weder `numberMatched` noch eine
  Aggregation liefert, adr/0007 §12).
- `truncated` ist über `adr/0004` §3.3 (Kappungsfalle) und den zugehörigen
  Zoom-/Geotile-Deckel abgedeckt (`TestBadInput`/Umschaltpunkt-Tests in
  derselben Datei).

**Fehlerfälle (Route, nicht Quelle):**
`backend/tests/earthx/api/test_coverage_route.py`:
- `TestUnknownDataset.test_answers_404` (Zeilen 91–96): unbekannter Datensatz
  → `404`, vor jedem Upstream-Aufruf.
- `TestBadInput` (Zeilen 133–154, parametrisiert): fehlerhafte Geometrien,
  ungültige bbox, offene Ringe → `400`, ohne Netzzugriff.
- `TestUpstreamErrors` (Zeilen 161–183): Upstream-4xx/5xx/Timeout/kaputte
  Antwort → definierter Statuscode; der Antwortkörper der Quelle gelangt
  weder in Antwort noch Log (M2-05b-Vorgabe).
- Geleerter Cache macht nur langsamer (E5), separat getestet in derselben
  Datei.

**Latenz — Zielwert unter 1 s, typisch unter 0,5 s:**
Aus einer Cloud-Sitzung heraus ist die reale Quelle nicht erreichbar
(`gateway` bindet an die geprüfte Adresse, der Sitzungs-Proxy weist `CONNECT`
ab — M2-13, `adr/0002` Nachtrag T-D). Die Messung stammt deshalb aus dem PR,
der M2-05b eingeführt hat (#43), per `curl` gegen die Route:
`docs/plans/m2-05-coverage.md` §3.2–3.3 (Zeilen 104–123, datiert 20.09.2026):
gefilterte bbox+Jahr-Anfragen auf z8 0,44–0,83 s, gefiltert (enger) 0,33 s,
der ungefilterte Weltüberblick z0–z6 durchgehend unter 1,1 s (typisch
0,60–0,88 s). Festgehalten außerdem in `docs/ENTSCHEIDUNGSLOG.md`
(Zeile zum 19.09.2026, "Latenzziel der gefilterten Coverage: unter 1 s,
typisch unter 0,5 s").

**Ausdrücklich:** Diese Zahlen stammen unverändert vom 20.09.2026 aus PR #43
(M2-05b). Diese Sitzung hat sie **nicht neu gemessen** — aus demselben Grund,
aus dem sie hier überhaupt per `curl`-Beleg statt per Live-Lauf geführt
werden: `gateway` erreicht die reale Quelle aus einer Cloud-Sitzung nicht
(M2-13). Der Beleg ist damit ein Zitat des seinerzeitigen Messwerts, keine
Bestätigung, dass die Latenz heute noch in diesem Bereich liegt.

**Ergebnis:** Kriterium 3 erfüllt (Route; Heatmap-Qualität ausdrücklich nicht
Teil dieser Abnahme).

---

## 4. Download liefert ZIP mit COG und Hinweisdatei; nichts wird gespeichert

**ZIP-Inhalt:**
`backend/tests/earthx/api/test_download_route.py::test_a_successful_crop_is_a_zip_with_the_notice_file`
(Zeilen 161–172): Antwort ist `application/zip`, enthält `visual.tif` (COG)
und `ATTRIBUTION.txt`; die Hinweisdatei führt die Attribution ("Contains
modified Copernicus Sentinel data …") und den `terms_notice` samt
`terms_url`.

**Nichts wird auf Platte oder in den Objektspeicher geschrieben:**
`backend/tests/earthx/access/test_download.py::test_nothing_is_ever_written_outside_gdals_in_memory_filesystem`
(Zeilen 220–243) patcht `rasterio.open` global und prüft, dass jeder
Schreibmodus-Aufruf mit `/vsimem/` beginnt (GDALs In-Memory-Dateisystem); die
Liste der geschriebenen Pfade ist nicht leer, der Test übt also den echten
Pfad aus, nicht einen leeren.

**Zuschnitt auch für den Zarr-Datensatz:**
`backend/tests/earthx/access/test_download_zarr.py` (Kriterium 1 oben).

**Ergebnis:** Kriterium 4 erfüllt.

---

## 5. Onboarding-Checkliste v1 als Test grün für jeden Datensatz

`backend/tests/catalog/test_onboarding_checklist.py`:
- Zeile 254: `ENTRIES = list(REGISTRY)` — lädt **alle** Registry-Einträge,
  nichts ist hartkodiert.
- Zeile 258: `@pytest.mark.parametrize("config", ENTRIES, ids=ENTRY_IDS)`.
- Zeilen 259–260: `test_every_registry_entry_passes_the_checklist` ruft
  `evaluate(config)` und verlangt `not findings` — die Punkte 1–8 laufen hier;
  die Punkte 9 (Suche → Anzeige → Zuschnitt-Download, M2-08-2) und 10 (T-D-
  Smoke-Abdeckung, M2-08-3) sind eigene, im selben Modul dokumentierte Tests
  (Zeilen 74–78 der Datei).
- Beide Registry-Mitglieder (`sentinel-2-c1-l2a`, `sentinel-2-l2a-zarr3`)
  laufen durch dieselbe parametrisierte Prüfung und bestehen; Zeilen 264–281
  pinnen zusätzlich ihre DOI-Werte und den zugeordneten Coverage-Anbieter.
- Ein Registry-Eintrag ohne einen der acht Punkte lässt den Test parametrisch
  für genau diesen Eintrag fallen (per Definition von `evaluate`/`findings`).

**Ergebnis:** Kriterium 5 erfüllt.

---

## 6. Importregeln grün, kein ausgehender Request außerhalb von `gateway`

**Verträge (`.importlinter`), nach D2:**
- Zeilen 14–23: Die neun Modulgrenzverträge (`gateway` bis `identity`) tragen
  `allow_indirect_imports = True`, sodass nur ein **direkter** Import gegen
  einen verbotenen Baustein zählt (erlaubt z. B. `access → readers →
  gateway`, `processing → catalog → gateway`).
- Zeilen 178–192: `datasets-isolated` zählt weiterhin Ketten (kein
  generischer Code importiert `earthx.datasets.*`).
- Zeilen 194–201: `no-database-in-worker-core` zählt weiterhin Ketten
  (KLAERUNGEN B9: `jobs`/`processing` erreichen `psycopg` über keine Kette).
- Zeilen 203–250: `http-only-in-gateway` verbietet den direkten Import jedes
  HTTP/S3-Clients (`httpx`, `httpx2`, `requests`, `urllib`, `pystac_client`,
  `aiohttp`, `boto3`, `obstore`) außerhalb von `gateway`.

**Tests, dass die Vertragsdatei selbst zur Tabelle in `architekturplan.md`
3.1 passt:**
`backend/tests/test_module_boundaries.py`:
- Zeilen 88–100: alle neun Modulgrenzverträge tragen das Flag.
- Zeilen 103–112: `datasets-isolated` und `no-database-in-worker-core` tragen
  es **nicht**.
- Zeilen 115–120: `http-only-in-gateway` verbietet genau die genannten
  Clients.
- Zeilen 123–131: `jobs`/`processing` erreichen `psycopg` über keine Kette.

**Kein ausgehender Request außerhalb von `gateway` (statisch geprüft):**
`backend/tests/earthx/test_no_outbound_outside_gateway.py`:
- Zeilen 66–72: `test_no_module_outside_the_gateway_imports_a_client` läuft
  eine AST-Analyse über jedes Nicht-`gateway`-Modul und bestätigt, dass
  nirgends ein HTTP-/S3-Client importiert wird.
- Zeilen 81–89: `test_no_module_imports_the_stac_reader_of_rio_tiler` prüft
  zusätzlich, dass `rio_tiler.io.stac` (das eigene HTTP macht, aber vom
  Importvertrag allein nicht erfassbar wäre) nirgends importiert wird (D15).

**Gegenproben aus M2-01 (#33), unverändert:** ein direkter Import
`access → gateway` fällt; eine Kette `access → readers → gateway` besteht;
eine Kette `processing → catalog → psycopg` fällt.

**`lint-imports` in dieser Sitzung:** grün, 12 von 12 Verträgen "KEPT" (siehe
Testlauf unten).

**Ergebnis:** Kriterium 6 erfüllt.

---

## 7. Das Frontend ruft keine Route des Prototyps mehr auf

- `frontend/src/api.ts:3` — Kommentar im API-Client: "Never talks to the
  prototype's `/api/…` routes." Alle Aufrufe gehen gegen `/stac`,
  Kachel-/Statistik-Routen, `/coverage`, `/download`.
- `frontend/src/store.ts:21` — Kommentar bestätigt, dass es keinen
  `/api/config`-Endpunkt mehr gibt (Prototyp entfernt).
- Der Prototyp selbst existiert nicht mehr im Arbeitsbaum:
  `backend/app/` liefert bei einer Glob-Suche keine Treffer mehr
  (`chore(prototype): remove backend/app, the BIOMASS prototype`,
  Commit `4570b8a`, `docs/adr/0008-prototyp-entfernen.md`). Der Stand bleibt
  über den Tag `prototype-biomass` erreichbar (README Kopfzeile).

**Ergebnis:** Kriterium 7 erfüllt.

---

## 8. Pflicht-CI grün (Backend, Frontend, Modulgrenzen, `compose-topology`)

`.github/workflows/ci.yml`:
- `backend` (Zeilen 25–79): `ruff check backend` (Zeile 71), `pytest`
  (Zeile 79).
- `frontend` (Zeilen 81–106): `npm run lint` (oxlint, Zeile 100),
  `npx tsc -b --pretty false` (Zeile 103), `npm test` (Vitest, Zeile 106).
- `import-boundaries` (Zeilen 108–122): `lint-imports --config
  .importlinter` (Zeile 122).
- `compose-topology` (Zeilen 124–204): baut und startet die sechs Dienste
  (`postgres`, `minio`, `api`, `tiler`, `worker`, `harvester`) per
  `docker compose`.

Alle vier laufen auf `pull_request`/`push` und sind damit Pflicht-CI für
diesen PR. `.github/workflows/live-smoke.yml` läuft dagegen nur auf
`schedule` (täglich) und `workflow_dispatch` (Zeilen 15–19), mit eigenen
Jobs `earth-search` und `eopf` — bewusst **nicht** blockierend, weil eine
Cloud-Sitzung die realen Quellen nicht erreicht (M2-13).

**Ergebnis:** Kriterium 8 wird von der CI dieses PR selbst geprüft; lokal
liefen die vier fachlichen Prüfungen bereits grün (siehe unten).

---

## Testlauf dieser Sitzung (2026-09-23, vor dem PR)

| Prüfung | Befehl | Ergebnis |
|---|---|---|
| Backend-Lint | `ruff check backend` | grün, keine Funde |
| Backend-Tests | `pytest` (ohne `tests_live`, das gegen echte Quellen geht) | **1067 passed**, 728 Warnungen (u. a. Zarr-Konsolidierungs-Hinweise, unschädlich) |
| Importregeln | `lint-imports --config .importlinter` | grün, **12 von 12 Verträgen "KEPT"** |
| Frontend-Lint | `npm run lint` (oxlint) | grün |
| Frontend-Typprüfung | `npx tsc -b --pretty false` | grün, keine Ausgabe |
| Frontend-Tests | `npx vitest run` | grün, **222 passed** (13 Testdateien) |

`tests_live` lief nicht (erwartet: `gateway` erreicht die realen Quellen aus
einer Cloud-Sitzung nicht, M2-13); das ist der separate, nicht blockierende
`live-smoke`-Workflow (Kriterium 8).

---

## Zusammenfassung

Alle acht Kriterien aus `docs/plans/m2-format-und-viewer.md` Abschnitt 5 sind
mit Code- und Testbelegen erfüllt, unter den beiden in der Aufgabenstellung
genannten Einschränkungen (Kriterium 3: nur die Route; Kriterium 1: beim
Zarr-Datensatz genügt der Lesepfad gegen das synthetische Zarr). M2 ist aus
Sicht dieses Berichts abnahmereif; die lokale Vorführung (STAC-Browser,
Viewer, beide Datensätze) steht in `README.md` Abschnitt 2.
