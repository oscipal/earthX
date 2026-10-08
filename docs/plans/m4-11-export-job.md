# M4-11 — Export über dem Deckel als Job: Plan

**Aufgabe:** M4-11 aus `docs/plans/m4-processing-kern.md` §4.
**Stufe B** — Plan-Schritt. Umgesetzt wird erst nach Ottos Antworten auf §8.
**Ort im Repo:** `docs/plans/m4-11-export-job.md`
**Grundlagen:** `plans/m3-dritte-quelle-und-interface.md` P19, P20, P21;
`plans/m3-18-download-deckel-maske.md` §3, §10.3, §13; `adr/0014` §4.1, §4.3,
§5.5, §10; `adr/0013` §5.1, §5.6; `adr/0015` §6, §8.1; `plans/m4-08a-jobs-queue.md`
F4; `plans/m4-08b-job-api.md` F3, K6; `plans/m4-07b-annahme.md` F5;
`ENTSCHEIDUNGSLOG.md` „M4-14, Antworten Otto“ (07.10.2026); `architekturplan.md`
3.1; `KLAERUNGEN.md` B8, B9, B11.

---

## 1. Ergebnis in drei Sätzen

Liegt ein Zuschnitt über 500 MB roh, antwortet die Download-Route weiter mit
`413`, sagt aber zusätzlich, ob dieselbe Auswahl als Job laufen kann; der
Download-Dialog bietet dann „Export as job“ an und stellt einen Auftrag mit
`steps: []` und der Ausgabe des Zuschnitts. Der Worker schreibt dieselben
Dateien wie der synchrone Zuschnitt (gleiches Raster, gleiche Mosaikregel,
Maske, `aoi.geojson`, `ATTRIBUTION.txt`, `recipe.json`, `citation.bib`), nur
blockweise auf die Platte statt in den Speicher, und packt sie in ein ZIP im
Objektspeicher. Der Nutzer lädt es über den Ergebnis-Link aus M4-08b (`303` auf
eine signierte URL), 7 Tage lang.

---

## 2. Stand vor dieser Aufgabe (gelesen am 08.10.2026, `main` = `de42d53`)

- **Abhängigkeiten erfüllt:** M4-08b (#128) und M4-14 (#129) sind gemergt. Keine
  offenen PRs; M4-12 und M4-13 haben noch nicht begonnen.
- **Synchroner Zuschnitt** (`api/tiler.py::download_crop`,
  `access/download.py`):
  - Prüfreihenfolge: Datensatz, Lizenzstufe *Processing* (B11), AOI, Faktor,
    Items, Gruppen ohne Berührung fallen weg, `compute_crop_region` je Gruppe,
    25 Items, dann `plan_outputs` + `check_output_size_cap` (500 MB roh mit
    Masken) → `413` mit Faktorvorschlag. Ab 100 MB höchstens einer zugleich je
    Prozess (`503`).
  - **Raster:** `reader.part(bbox)` bzw. `_native_crop_grid` schreiben in
    **EPSG:4326** in der nativen Auflösung, die `calculate_default_transform`
    liefert, mit `nearest` (rio-tiler 9.4.6: `dst_crs = dst_crs or bounds_crs`,
    `bounds_crs` = WGS84; gelesen in `Reader.part`). Nicht im UTM-Raster der
    Quelle.
  - **Datei je Gruppe und Asset**, Mosaik über `mosaic_reader` mit
    `FirstMethod`, `threads=1`; Maske je Asset (`uint8`, 1 innen); Ausdehnung
    `bbox(AOI ∩ Footprints der Gruppe)`; eigener nodata-Wert je Band.
  - **Alles im Speicher** (`MemoryFile`, `BytesIO`). Gemessen: 500 MB roh →
    3,1 GB Spitze auch fensterweise, 1 005 MB roh → 5,1 GB
    (`m3-18` §10.3). Nur ein einzelnes COG-Item in nativer Auflösung liest
    blockweise (`_write_native_windowed_cog`); Mosaik, Zarr und gröbere Faktoren
    lesen das ganze Fenster.
  - ZIP: `ZIP_DEFLATED` für alles, `group-NN/` ab zwei Gruppen,
    `aoi.geojson` mit `properties` einer Orts-AOI, `recipe.json` aus
    `crop_recipe_json` (ohne `recipe_id`, Ausgabe `kind: "crop"`),
    `citation.bib`, `ATTRIBUTION.txt` mit Herkunftszeile der Orts-AOI.
- **Kern** (`processing/core.py`): `check_scope` nimmt nur `RasterOutput` und
  genau ein Item; schreibt `result.tif` und `mask.tif` im Raster der Quelle,
  wendet die Skalierung des Items an. `CropOutput` ist „beschrieben, nicht
  gerechnet“.
- **Annahme** (`api/intake.py`): `_check_scope` weist jede Ausgabe außer
  `raster` ab; 25 Items, 16 Assets.
- **Queue** (`jobs/submit.py`): gleiche Aufträge teilen einen Lauf
  (`run_key`), ein fertiges Ergebnis ist Cache-Treffer (Q11). Das Kind bekommt
  nur `recipe.json` im Arbeitsordner; der Aufseher lädt fest `result.tif` und
  `mask.tif` hoch (`RESULT_FILES`). `recipe.json` liegt nicht im Speicher, `api`
  baut sie je Job, damit niemand die `recipe_id` eines anderen sieht
  (M4-08a F4).
- **Importregeln:** `jobs` darf weder `catalog` noch `access` importieren;
  `processing` darf `access`, `readers` und aus `catalog` nur `catalog.registry`.
  Wer `ATTRIBUTION.txt` und `citation.bib` baut, braucht den Registry-Eintrag:
  das kann nur `api`.
- **Laufzeitgrenze:** 2 × Schätzung, mindestens 10 min; die Schätzung kennt den
  Export schon (`EXPORT_FACTOR`, `adr/0014` §5.5). Einen Größendeckel je Job
  gibt es noch nicht (`adr/0014` §5.5: „Pixeldeckel je Job ist Sache von
  `adr/0013` und M4-08“, dort nicht festgelegt).
- **Frontend:** Der Dialog kennt den `413` nur als Fehlertext; kein Client für
  `/processing`, kein Proxy-Eintrag in `vite.config.ts` (M4-08b §5: M4-13).

---

## 3. Umsetzung (nach den Empfehlungen in §8)

### 3.1 Auftrag (F1)

Der Auftrag ist ein gewöhnlicher Auftrag aus `adr/0014` §4.1 mit der Ausgabe,
die `recipe.json` des Zuschnitts schon heute trägt:

```json
{
  "recipe_version": 1,
  "inputs": [{"name": "input", "dataset": "sentinel-2-c1-l2a",
              "groups": [["<item>", "<item>"], ["<item>"]], "assets": ["visual"]}],
  "aoi": {"type": "Polygon", "coordinates": ["…"]},
  "steps": [],
  "output": {"kind": "crop", "format": "cog", "resolution_factor": 1,
             "extent": "bbox(aoi ∩ footprints)", "mask": "file"}
}
```

Kein neues Schema, keine neue `recipe_version`. Ein Zuschnitt und ein Export
über dieselbe Auswahl beschreiben dasselbe; der Unterschied ist nur die
Provenienz (`sync-download` gegen `job`).

### 3.2 Annahme in `api` (`intake.py`)

- `_check_scope` lässt `kind: "crop"` zu, aber nur mit `steps: []` und
  `resolution_factor: 1` (K1); sonst `422`.
- Nach Stufe 5 (Gruppen, die die AOI berühren) schätzt die Annahme die Größe
  wie der Zuschnitt: je Gruppe `compute_crop_region` und `plan_outputs`, Summe
  mit Masken. Über dem Deckel des Jobs (F5) `413` mit Text ohne Zahlen der AOI.
- Bei F6 Option 1: ein Zarr-Datensatz → `422` „export jobs read COG assets
  only for now“.
- Dazu baut `api` bei der Annahme die Begleitdateien, die einen
  Registry-Eintrag brauchen: `ATTRIBUTION.txt` (`build_notice_text` mit Gruppen,
  übersprungenen Items und Herkunft der Orts-AOI nach F4) und `citation.bib`
  (`api/citation.py`, Datum der Annahme). Sie gehen als fertiger Text an
  `submit` (K3).

### 3.3 Queue und Aufseher (`jobs`, F3)

- `submit(conn, recipe, *, attachments=…)`: Ein Auftrag mit `kind: "crop"`
  bekommt immer einen **eigenen Lauf** (`cacheable = false`, Laufschlüssel mit
  der eigenen `recipe_id`), hängt sich nie an einen anderen und wird nie
  Treffer (F3). Die Begleitdateien liegen am Lauf (neue Spalte
  `earthx_run.attachments jsonb`, Migration `007`; nur Name → Text, Namen aus
  einer festen Liste).
- Der Aufseher schreibt sie neben `recipe.json` in den Arbeitsordner, ohne sie zu
  lesen, und lädt je nach Ausgabe `result.tif` + `mask.tif` oder `export.zip`
  hoch. `objectstore.RESULT_NAMES` bekommt `export.zip`
  (`application/zip`).
- `jobs` bleibt ohne `catalog` und `access`; die Importverträge ändern sich
  nicht.

### 3.4 Rechnen im Kind (`processing/export.py`, neu; `access/download.py`, F1)

- `run` verzweigt nach der Ausgabe: `crop` → `export(recipe, workdir,
  progress)`. `check_scope` lässt `crop` mit `steps: []` und beliebig vielen
  Gruppen und Items zu.
- `export` nutzt die Bausteine des Zuschnitts, damit es nur **eine**
  Rechenvorschrift gibt (K2):
  - `access.download` bekommt einen Schreiber, der blockweise in eine Datei im
    Arbeitsordner schreibt statt in eine `MemoryFile`; `_write_native_windowed_cog`
    nutzt denselben Kern mit Ziel Speicher, das Verhalten des Zuschnitts bleibt
    gleich (bestehende Tests).
  - **Mosaik blockweise:** je Block die Items der Gruppe in der Reihenfolge des
    Auftrags über `WarpedVRT` auf das Raster des Zuschnitts, das erste gültige
    Pixel je Band gewinnt, Abbruch je Block, sobald alles gefüllt ist (die
    Regel von `FirstMethod`). Raster und Vorfilter wie beim Zuschnitt.
  - COG per `cog_translate(in_memory=False)` im Arbeitsordner, Maske wie heute.
  - Gelesen wird über `open_asset_ref` mit der Policy aus dem Rezept
    (`read_access_for`), wie im Kern (B8, `adr/0014` §7.3).
- **ZIP im Kind:** `export.zip` mit genau den Namen des Zuschnitts
  (`crop_filename`, `mask_filename`, `group_dirname`, `aoi.geojson`,
  `ATTRIBUTION.txt`, `citation.bib`, `recipe.json`). COG und Masken als
  `ZIP_STORED` (sie sind schon deflate-komprimiert; eine zweite Kompression
  kostet bei GB nur Rechenzeit), Textdateien `ZIP_DEFLATED`, ZIP64 erlaubt.
  Jede Datei wird nach dem Hinzufügen gelöscht: Spitze auf der Platte ≈ Summe
  der Dateien + größte Datei. CRC-Prüfung wie `_verify_zip`.
- **`recipe.json` im ZIP** schreibt das Kind aus dem Rezept im Arbeitsordner
  (mit der eigenen `recipe_id`, F3) und der Provenienz des Laufs (`kind: "job"`,
  Zeiten, `engine`, Attribution aus den Begleitdateien). Die Funktion dafür
  zieht aus `api/intake.py::job_recipe_json` nach `processing/recipe.py` um,
  damit der Link `/results/recipe.json` und die Datei im ZIP dieselbe Datei sind
  (K4).
- Fortschritt je Block über alle Gruppen und Assets, das Packen als letzter
  Schritt; Abbruch räumt alle Dateien weg (wie `run`).
- Logs: Datensatz, Zahl der Gruppen, Items, Assets, Blöcke, Bytes, Sekunden;
  nie AOI, Adresse, Hash.

### 3.5 Ergebnis-Links (`api/processing_route.py`)

- Ein Export-Job hat im Ergebnisdokument die Links `export` (`export.zip`,
  mit `length`) und `recipe` (`recipe.json`); `LINK_NAMES` und `_SUFFIXES`
  bekommen `export.zip` → `{dataset}_export_{YYYYMMDD}.zip` (K6 aus M4-08b,
  „export“ ohne Schritte ist dort schon vorgesehen).
- `303` auf die signierte URL, `410` am Ende der Frist: unverändert.

### 3.6 Download-Route (`api/tiler.py`)

- Über 500 MB roh bleibt es bei `413` mit Faktorvorschlag. Liegt dieselbe
  Auswahl in nativer Auflösung unter dem Deckel des Jobs, trägt die Antwort
  zusätzlich `X-Export-Job: available` (K5), wie heute schon
  `X-Skipped-Groups` nur eine Kennung, keine Geometrie.
- Sonst ändert sich am Zuschnitt nichts.

### 3.7 Frontend (F7)

- `vite.config.ts`: Proxy `/processing` → `api`.
- `api.ts`: `submitExportJob(order)`, `jobStatus(jobId)`, `dismissJob(jobId)`;
  die Fehlertexte wie bei den übrigen Aufrufen.
- `DownloadDialog.tsx` und `store.ts`:
  - `413` mit `X-Export-Job: available` → der Dialog zeigt den Text des `413`
    und darunter „This export is larger than a direct download allows. Run it
    as a job: the file is prepared on the server and stays available for 7
    days.“ mit Knopf „Export as job“.
  - Auftrag aus derselben Auswahl (Gruppen, Assets, AOI) wie der Zuschnitt;
    `skippedItems` der Antwort wie `X-Skipped-Groups` heute.
  - Status alle 5 s per `GET /processing/jobs/{jobID}` (Polling, kein SSE,
    F7), Fortschrittsbalken, „Cancel“ → `DELETE`; fertig → Link „Download
    export (ZIP, … MB)“ auf `…/results/export.zip`; Fehler mit dem Titel des
    Problems.
  - Die `jobID` lebt nur im Zustand der Seite (K7): Hinweis „Keep this tab
    open until the export is ready.“
- Alle Texte Englisch.

### 3.8 Tests

| Was | Test |
|---|---|
| Grenze | synthetische Items, deren Schätzung genau 500 MB ergibt → Zuschnitt läuft; 500 MB + 1 Pixel → `413` mit `X-Export-Job: available`; über dem Deckel des Jobs → `413` ohne Kennung, und die Annahme weist denselben Auftrag mit `413` ab |
| gleiche Dateien | kleine synthetische COGs, Deckel des Zuschnitts im Test gesenkt: ein Item, Mosaik aus zwei Items, zwei Gruppen, Orts-AOI. Synchrones ZIP gegen `export.zip`: Daten und Masken pixelgleich (Werte, nodata, Raster, CRS), `aoi.geojson`, `citation.bib`, `ATTRIBUTION.txt` gleich bis auf die Zeile `Generated` |
| Speicher | Export einer synthetischen COG von rund 1 GB roh im eigenen Prozess: `VmHWM` unter einer Grenze, die der PR misst und nennt (Ziel: unter 500 MB) |
| Platte | Spitze im Arbeitsordner ≤ Summe der Dateien + größte Datei |
| Abbruch | `RunCancelled` mitten im Mosaik → Arbeitsordner leer |
| eigener Lauf | zwei gleiche Export-Aufträge → zwei Läufe, zwei `result_id`, kein Treffer; ein Raster-Auftrag teilt weiter |
| zweckfremd | Export mit Schritten, mit Faktor ≠ 1, mit Zarr (F6), mit `resolved` oder `recipe_id` (`recipe.json` des Zuschnitts erneut eingereicht) → `400`/`422`; fremde `export.zip` eines anderen Jobs nicht erreichbar; unbekannter Name in `attachments` → Fehler beim Einreihen |
| Logs | kein AOI-Wert, keine Adresse, kein Hash in `api`, Aufseher und Kind |
| Importregeln | `lint-imports` unverändert grün; das Kind lädt kein psycopg (`test_child`) |
| Frontend | Dialog zeigt das Angebot nur mit der Kennung; Auftrag aus der Auswahl; Fortschritt, Abbruch, Link; Fehler des Jobs |

---

## 4. Abnahme

- **Test über die Grenze** (§3.8, Zeile „Grenze“) grün in der CI.
- **Prüfanleitung für Otto mit einer großen AOI** (§9) im PR.
- `pytest`, `ruff check backend`, `PYTHONPATH=backend lint-imports --config
  .importlinter`, `npm run lint`, `npx tsc -b --pretty false` grün; Zahlen im PR.

---

## 5. Nicht in dieser Aufgabe

- Mosaik ganzer Szenen je Überflug: M4-12. Processing-Panel, Job-Liste, SSE im
  Frontend: M4-13. Permalink über `recipe_id`: M4-19.
- Gröbere Faktoren als Job (K1).
- Exporte über mehrere UTM-Zonen in einer Gruppe: wie beim Zuschnitt (Raster des
  ersten Items, EPSG:4326); keine eigene Regel.
- Quotas je Absender: M6 (Q9).

---

## 6. Umfang und Commits

Geschätzt Backend rund 650 Zeilen Code (`processing/export.py` 250,
`access/download.py` 120 umgebaut, `intake.py` 80, `jobs` 80 mit Migration,
`processing_route.py` 30, `tiler.py` 20, `recipe.py` 40, `objectstore` 5) und
rund 700 Zeilen Tests; Frontend rund 250 Zeilen Code und 250 Zeilen Tests. Das
liegt deutlich über dem Richtwert von 400 Zeilen (F8).

Commits (Backend):
1. `access`: blockweiser Schreiber mit Ziel Datei oder Speicher; Zuschnitt
   unverändert.
2. `processing`: Mosaik blockweise, `export`, ZIP; `check_scope`, `run`.
3. `processing`: Provenienz-Dokument aus `api` nach `recipe.py`.
4. `jobs`: Migration `007`, `attachments`, eigener Lauf für Exporte, Upload je
   Ausgabe; `objectstore`: `export.zip`.
5. `api`: Annahme (Ausgabe `crop`, Deckel, Begleitdateien), Ergebnis-Links,
   Kennung im `413`.
6. Tests über die Grenze, Gleichheit, Speicher, zweckfremd.
7. Doku: Nachtrag `adr/0013` §5.1 (Exporte teilen keinen Lauf), Log, Status.

Commits (Frontend): Proxy und Client; Dialog und Zustand; Tests.

---

## 7. Risiken

- **Gleichheit mit dem Zuschnitt:** `mosaic_reader` liest je Item mit
  `part()` in dessen eigenem Raster; der blockweise Weg rechnet auf einem Raster.
  Für Items mit gleichem CRS und gleicher Auflösung (eine Gruppe aus einem
  Überflug) ist das dasselbe; der Gleichheitstest deckt Mosaik und zwei Gruppen
  ab. Weicht es bei einem Grenzfall ab, nennt der PR ihn.
- **Platte des Workers:** Der Arbeitsordner liegt im Container
  (`/tmp/earthx-runs`, kein Volume). Zwei Slots mit je einem Export am Deckel
  brauchen bis zu 2 × (Deckel + größte Datei). Der PR nennt die Zahl; ein
  eigenes Volume ist eine Frage für M6.
- **Slots:** Ein großer Export belegt einen Slot für Minuten; bei Deckel 4 und
  2 Slots je Container warten Band-Math-Jobs dahinter. Ein eigener `pool` für
  Exporte (die Spalte gibt es) ist möglich, aber nicht vorgesehen.
- **Speicherplatz im Objektspeicher:** 7 Tage × Exporte bis zum Deckel; ohne
  Konten gibt es keine Grenze je Absender (Q9, M6).
- **Lauf ohne Cache:** Zwei gleiche Exporte rechnen doppelt (F3). Der Dialog
  verhindert den Doppelklick.

---

## 8. Fragen an Otto

**F1 — Wie rechnet der Job? (§3.4)**
1. Mit dem Code des Zuschnitts, nur blockweise und mit Ziel Platte: gleiches
   Raster (EPSG:4326, nativ, `nearest`), gleiche Mosaikregel, gleiche Dateien.
   Für dieselbe Auswahl unter dem Deckel sind die Dateien gleich (Test)
   **(Empfehlung)**
2. Mit dem Kern (`run`, `steps: []`): Raster der Quelle (UTM), ohne
   Umprojektion, alle Assets einer Gruppe als Bänder einer Datei; ein anderes
   Ergebnis als der Zuschnitt, Mosaik über zwei Zonen erst mit M4-12

**F2 — ZIP oder einzelne Dateien? (§3.4, im Aufgabenschnitt offen)**
1. Ein ZIP `export.zip`, aufgebaut wie beim Zuschnitt; COG ohne zweite
   Kompression, ZIP64; ein Link **(Empfehlung)**
2. Einzelne Dateien je Gruppe und Asset, je Datei ein Link (15 min gültig);
   Hinweisdateien als eigene Links von `api`

**F3 — Teilen Exporte einen Lauf? (§3.3)**
1. Nein: jeder Export ein eigener Lauf, nie Cache-Treffer. Dann darf das ZIP die
   eigene `recipe_id`, die Herkunft der Orts-AOI und das eigene Datum tragen,
   ohne dass ein anderer Auftraggeber sie sieht (M4-08a F4). Zwei gleiche
   Exporte rechnen doppelt **(Empfehlung)**
2. Ja, wie andere Jobs: `recipe.json` im ZIP ohne `recipe_id` (wie beim
   Zuschnitt), die eigene über den Link; die Herkunftszeile einer Orts-AOI fehlt
   im ZIP

**F4 — Herkunft einer Orts-AOI (© OpenStreetMap, ODbL) im Job-ZIP**
Das Rezept trägt die AOI ohne `properties`; ein neues Feld im Auftrag bräuchte
nach `adr/0014` §4.3 `recipe_version` 2.
1. Ein zweiter, optionaler Eingang `aoiProvenance` beim Ausführen
   (`attribution`, `license`, `source`, je höchstens 200 Zeichen, wie
   `_aoi_provenance_field`), nicht Teil von Rezept und Hash; landet in
   `ATTRIBUTION.txt` und `aoi.geojson`. Erweitert M4-08b F3 („ein Eingang“)
   **(Empfehlung, setzt F3 Option 1 voraus)**
2. Im Job-ZIP keine Herkunftszeile; der Dialog zeigt sie vor dem Start
3. Feld im Auftrag mit `recipe_version` 2

**F5 — Deckel eines Export-Jobs (roh, mit Masken, wie der Zuschnitt zählt)**
Startwert [A]: Bei 0,041–0,046 s/MB lokal (`m3-18` §10.3) sind 5 GB rund 4 min
ohne Netz; die Laufzeitgrenze (2 × Schätzung, mindestens 10 min) trägt das;
Platte je Slot bis rund 2 × Deckel. Der PR misst Zeit, Speicher und Platte bei
1 GB und nennt die Zahlen.
1. 5 GB (zehnfacher Zuschnitt) **(Empfehlung)**
2. 2 GB
3. 10 GB

**F6 — Zarr (`sentinel-2-l2a-zarr3`) als Export-Job?**
Der Zuschnitt liest Zarr ganz in den Speicher; blockweise in EPSG:4326 braucht
einen eigenen Weg und eine eigene Messung.
1. In M4-11 nur COG-Datensätze; Zarr `422` mit Hinweis, eine eigene Aufgabe
   folgt **(Empfehlung)**
2. Zarr in M4-11 über den heutigen Weg (ganzes Fenster je Asset), Spitze im PR
   gemessen; der Deckel für Zarr folgt aus der Messung
3. Zarr in M4-11 blockweise

**F7 — Wie viel Frontend in M4-11?**
1. Das Angebot im Download-Dialog mit Polling alle 5 s, Fortschritt, Abbruch
   und Link; Proxy und Client für `/processing` legt M4-11 an, M4-13 baut darauf
   auf (SSE, Panel) **(Empfehlung)**
2. Wie 1, aber mit SSE
3. Kein Frontend; der Dialog folgt mit M4-13

**F8 — Schnitt**
1. Zwei PRs nacheinander auf diesem Plan: M4-11a Backend, M4-11b Frontend (je
   rund 1 400 bzw. 500 Zeilen mit Tests) **(Empfehlung)**
2. Ein PR mit rund 1 900 Zeilen

**Kleinentscheidungen** (gelten, wenn Otto nicht widerspricht):

- **K1** Der Job rechnet nur native Auflösung (Aufgabenschnitt: „in voller
  Auflösung“). Ein gröberer Faktor über 500 MB bleibt `413` mit
  Faktorvorschlag, ohne Job-Angebot.
- **K2** Eine Rechenvorschrift: Die Bausteine bleiben in `access.download`;
  `processing/export.py` ruft sie. `access` importiert `processing` nicht.
- **K3** `api` baut `ATTRIBUTION.txt` und `citation.bib` bei der Annahme und
  gibt sie als Text an `submit`; am Lauf gespeichert, vom Aufseher ungelesen in
  den Arbeitsordner geschrieben. Nur die Namen `ATTRIBUTION.txt` und
  `citation.bib`, je höchstens 64 KiB.
- **K4** Das Provenienz-Dokument von `recipe.json` (heute
  `api/intake.py::job_recipe_json`) zieht nach `processing/recipe.py`; `api`
  und das Kind rufen dieselbe Funktion.
- **K5** Kennung im `413` als Kopfzeile `X-Export-Job: available`; kein
  geändertes Format des Fehlertexts.
- **K6** Dateiname der ZIP `{dataset}_export_{YYYYMMDD}.zip`; im ZIP die Namen
  des Zuschnitts.
- **K7** Die `jobID` lebt im Frontend nur im Zustand der Seite; kein
  `localStorage` (eine `jobID` ist ohne Konten der einzige Schlüssel zum
  Ergebnis, Q9).
- **K8** Die Grenze von 25 Items je Auftrag bleibt (gleich dem Zuschnitt);
  M4-11 hebt sie nicht.

---

## 9. Prüfanleitung für Otto (Entwurf, kommt mit dem PR)

```powershell
docker compose up -d --build
docker compose ps        # api, tiler, worker, objectstore: healthy
cd frontend; npm run dev
```

Im Browser `http://localhost:5173`: Sentinel-2 (`sentinel-2-c1-l2a`), eine AOI,
die mehr als eine ganze Kachel überdeckt (etwa 120 × 120 km), einen Überflug
mit zwei bis vier Szenen wählen, Asset `visual` und dazu ein 10-m-Band,
„Download“ → der Dialog nennt die Größe und bietet „Export as job“ an. Starten,
Fortschritt beobachten, nach dem Ende „Download export“. Im ZIP: je Asset Daten
und Maske, `aoi.geojson`, `ATTRIBUTION.txt`, `recipe.json` (mit `recipe_id`,
`provenance.kind = "job"`), `citation.bib`. Gegenprobe: dieselbe Auswahl mit
kleiner AOI lädt direkt, ohne Job.
