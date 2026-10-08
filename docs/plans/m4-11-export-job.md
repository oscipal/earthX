# M4-11 — Export über dem Deckel als Job: Plan

**Aufgabe:** M4-11 aus `docs/plans/m4-processing-kern.md` §4.
**Stufe B** — **von Otto am 08.10.2026 freigegeben** (§10), mit einer Ergänzung
aus M4-13 (mehrere Items und Gruppen im Kern). Geschnitten in **M4-11a**
(Backend, dieser PR) und **M4-11b** (Frontend, nach dem Merge von M4-13). §3
beschreibt die freigegebene Fassung; §8 bleibt als Wortlaut der Fragen stehen.
**Ort im Repo:** `docs/plans/m4-11-export-job.md`
**Grundlagen:** `plans/m3-dritte-quelle-und-interface.md` P19, P20, P21;
`plans/m3-18-download-deckel-maske.md` §3, §10.3, §13; `adr/0014` §4.1, §4.3,
§5.5, §10; `adr/0013` §5.1, §5.6; `adr/0015` §6, §8.1; `plans/m4-08a-jobs-queue.md`
F4; `plans/m4-08b-job-api.md` F3, K6; `plans/m4-07a-processing-kern.md` F2, F6, F9;
`plans/m4-07b-annahme.md` F5; `ENTSCHEIDUNGSLOG.md` „M4-14, Antworten Otto“
(07.10.2026); `architekturplan.md` 3.1; `KLAERUNGEN.md` B8, B9, B11.

---

## 1. Ergebnis in drei Sätzen

Liegt ein Zuschnitt über 500 MB roh, antwortet die Download-Route weiter mit
`413`, sagt aber mit `X-Export-Job: available` zusätzlich, ob dieselbe Auswahl
als Job laufen kann; der Auftrag dafür hat `steps: []` und die Ausgabe `crop`.
Der Kern (`processing`) rechnet diese Ausgabe selbst, blockweise auf die Platte,
je berührter Gruppe und Asset eine Rasterdatei samt Maske, mit derselben
Rasterregel wie der Zuschnitt (EPSG:4326, nativ, `nearest`, erstes gültiges
Pixel), und packt sie mit `aoi.geojson`, `ATTRIBUTION.txt`, `recipe.json` und
`citation.bib` in ein `export.zip`. Der Nutzer lädt es über den Ergebnis-Link
aus M4-08b (`303` auf eine signierte URL, Range-Anfragen erlaubt), 7 Tage lang;
den Dialog dafür baut M4-11b.

---

## 2. Stand vor dieser Aufgabe (gelesen am 08.10.2026, `main` = `de42d53`)

- **Abhängigkeiten erfüllt:** M4-08b (#128) und M4-14 (#129) sind gemergt.
- **Synchroner Zuschnitt** (`api/tiler.py::download_crop`,
  `access/download.py`):
  - Prüfreihenfolge: Datensatz, Lizenzstufe *Processing* (B11), AOI, Faktor,
    Items, Gruppen ohne Berührung fallen weg, `compute_crop_region` je Gruppe,
    25 Items, dann `plan_outputs` + `check_output_size_cap` (500 MB roh mit
    Masken) → `413` mit Faktorvorschlag.
  - **Raster:** `reader.part(bbox)` bzw. `_native_crop_grid` schreiben in
    **EPSG:4326** in der nativen Auflösung, die `calculate_default_transform`
    liefert, mit `nearest` (rio-tiler 9.4.6: `dst_crs = dst_crs or bounds_crs`,
    `bounds_crs` = WGS84; gelesen in `Reader.part`).
  - **Datei je Gruppe und Asset**, Mosaik über `mosaic_reader` mit
    `FirstMethod`, Maske je Asset (`uint8`, 1 innen, `all_touched`), Ausdehnung
    `bbox(AOI ∩ Footprints der Gruppe)`, eigener nodata-Wert je Band.
  - **Alles im Speicher** (`MemoryFile`, `BytesIO`): 500 MB roh → 3,1 GB
    Spitze auch fensterweise (`m3-18` §10.3). Nur ein einzelnes COG-Item in
    nativer Auflösung liest blockweise (`_write_native_windowed_cog`).
- **Kern** (`processing/core.py`): `check_scope` nimmt nur `RasterOutput` und
  genau ein Item (M4-07a F2); Raster der Quelle; die Rastergrenze ersetzt die
  Footprints, die der Kern nicht sieht (M4-07a F9). `CropOutput` ist
  „beschrieben, nicht gerechnet“.
- **Das Kind lädt heute schon `access.download`:** `processing/recipe.py`
  (`RESOLUTION_FACTORS`) und `processing/plan.py` (`estimate_output_dims`,
  `MAX_OUTPUT_SIDE_PX`) importieren es.
- **Queue** (`jobs/submit.py`): gleiche Aufträge teilen einen Lauf, ein fertiges
  Ergebnis ist Cache-Treffer (Q11); das Kind bekommt nur `recipe.json`; der
  Aufseher lädt fest `result.tif` und `mask.tif` hoch.
- **Importregeln:** `jobs` darf weder `catalog` noch `access`; `processing`
  darf `access`, `readers` und aus `catalog` nur `catalog.registry`. Wer
  `ATTRIBUTION.txt` und `citation.bib` baut, braucht den Registry-Eintrag: das
  kann nur `api`.
- **Ein Größendeckel je Job** ist bisher nirgends festgelegt.

---

## 3. Umsetzung (freigegebene Fassung)

### 3.1 Auftrag

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

Beim Ausführen optional als zweiter Eingang (F4):
`{"inputs": {"recipe": …, "aoiProvenance": {"attribution": …, "license": …,
"source": …}}}`, je ein String ohne Zeilenumbruch, höchstens 200 Zeichen, nicht
Teil von Rezept und Hash, nur für Exporte.

### 3.2 Gemeinsame Regeln (`access/crop_rules.py`, neu; F1)

Zuschnitt und Kern nutzen **eine** Rasterregel, aus reinen Funktionen, die aus
`access/download.py` herausgeschnitten werden (dort weiter unter denselben Namen
erreichbar): `native_crop_grid`, `compute_crop_region` mit `AoiOutsideItems`,
`rasterize_aoi`, das Profil der Maske und der COG, `estimate_output_dims`, die
Bytes je Pixel, `PlannedOutput`, die Dateinamen (`crop_filename`,
`mask_filename`, `group_dirname`, `aoi.geojson`, `ATTRIBUTION.txt`,
`recipe.json`, `citation.bib`), `RESOLUTION_FACTORS` und der Deckel
`MAX_EXPORT_JOB_BYTES = 5_000_000_000` (F5, die eine Stelle). `processing`
importiert nur noch dieses Modul, nicht mehr `access.download`; ein Test prüft,
dass das Kind `earthx.access.download` nicht lädt. `.importlinter` bleibt
unverändert.

### 3.3 Rezept (`processing/recipe.py`)

- **Footprints im Rezept (Auslegung, §11).** Die Ausdehnung `bbox(AOI ∩
  Footprints)` braucht die Footprints der Items; der Kern sieht sie bisher nicht
  (M4-07a F9). `Input` bekommt `footprints: {item_id: Polygon | MultiPolygon |
  null}`, Pflicht bei der Ausgabe `crop`, verboten bei `raster`. Ein Rezept ohne
  Footprints wird ohne das Feld ausgegeben: Hash und `recipe.json` der
  Raster-Jobs ändern sich nicht. Auch `recipe.json` des synchronen Zuschnitts
  trägt die Footprints und beschreibt damit vollständig, was gerechnet wurde.
- Das Provenienz-Dokument von `recipe.json` zieht aus `api/intake.py` nach
  `recipe.py` (K4); `api` und das Kind rufen dieselbe Funktion.

### 3.4 Kosten und Deckel (`processing/plan.py`, F5)

`estimate` rechnet für `crop` wie `plan_outputs` des Zuschnitts: je Gruppe die
Region aus AOI und Footprints, je Asset die feinste `gsd` und die größten Bytes
je Pixel der Items, Daten plus Maske. Über `MAX_EXPORT_JOB_BYTES` wirft es
`ExportTooLarge` (eine `UnsupportedRecipe`); die Annahme macht daraus `413`,
`check_scope` prüft es vor dem Einreihen und im Kind noch einmal.

### 3.5 Rechnen im Kern (`processing/export.py`, neu; F1, Ergänzung)

- `run` verzweigt nach der Ausgabe. `crop` darf **mehrere Gruppen und Items**
  haben; sie werden **nacheinander** verarbeitet. Für `raster` bleibt die
  Abweisung von mehr als einem Item (M4-07a F2).
- `check_scope` für `crop`: `steps: []`, Faktor 1 (K1), nur COG-Eingaben
  (F6: Zarr → `UnsupportedRecipe`), Größe unter dem Deckel.
- Je Gruppe und Asset:
  1. Region = `compute_crop_region(Footprints der Gruppe, AOI)`.
  2. Raster = `native_crop_grid(Datensatz des ersten Items, Region)`.
  3. Je Block von 1024 px: die Items der Gruppe in der Reihenfolge des Auftrags
     über `WarpedVRT` (EPSG:4326, dieses Raster, `nearest`) lesen; das erste
     gültige Element je Band und Pixel gewinnt, wie `FirstMethod`; sind alle
     Elemente des Blocks gefüllt, werden die übrigen Items für diesen Block nicht
     gelesen. Gleichzeitig die Maske des Blocks (`rasterize_aoi`, ursprüngliche
     AOI).
  4. Kein gültiges Pixel in der AOI → `AoiOutsideInputs` (wie `AoiOutsideItems`
     beim Zuschnitt, der dann `400` gibt).
  5. GeoTIFF im Arbeitsordner, dann `cog_translate` auf die Platte, Maske als
     GeoTIFF; beide werden vollständig zurückgelesen (M3-22).
- **Speicher je Item:** Es ist immer nur ein Block je Item im Speicher, die
  Items einer Gruppe sind gleichzeitig offen, aber werden nacheinander gelesen;
  die Spitze wächst nicht mit der Zahl der Items (Test über zwei Items).
- **ZIP:** `export.zip` mit den Namen des Zuschnitts, `.tif` als `ZIP_STORED`
  (F2), Textdateien deflate, ZIP64; jede Datei wird nach dem Hinzufügen
  gelöscht (Spitze auf der Platte ≈ Summe + größte Datei); CRC-Prüfung zum
  Schluss. `recipe.json` schreibt das Kind aus dem eigenen Rezept (mit
  `recipe_id`, F3) und der Provenienz des Laufs; `ATTRIBUTION.txt`,
  `citation.bib` und `aoi.geojson` kommen fertig von `api` (§3.6).
- Fortschritt je Block über alle Gruppen und Assets, das Packen als letzter
  Schritt; ein Abbruch räumt alle Dateien weg. Logs: Zahlen, nie AOI, Adresse,
  Hash.

### 3.6 Begleitdateien und Queue (`api`, `jobs`; F3, K3)

- `api` baut bei der Annahme `ATTRIBUTION.txt` (`build_notice_text` wie der
  Zuschnitt: Gruppen, ganz weggefallene Gruppen, Herkunft der Orts-AOI aus
  `aoiProvenance`), `citation.bib` (Tag der Annahme) und `aoi.geojson` (AOI mit
  der Herkunft als `properties`, wie beim Zuschnitt). Dazu die Attribution für
  die Provenienz. **Abweichung von K3:** `aoi.geojson` kommt dazu, weil die
  Herkunft (F4) sonst nicht ins Kind käme; Grenze je Datei 64 KiB, für
  `aoi.geojson` 2 MiB (der Rumpf eines Auftrags hat höchstens 1 MiB).
- `submit(…, attachments=…)`: Ein Export bekommt immer einen **eigenen Lauf**
  (`cacheable = false`, Laufschlüssel mit der eigenen `recipe_id`), hängt sich
  nie an und wird nie Treffer. Die Begleitdateien liegen am Lauf (Migration
  `007`, Spalte `earthx_run.attachments jsonb`); `jobs` prüft nur die Namen, nicht
  den Inhalt.
- Der Aufseher schreibt sie als `attachments.json` in den Arbeitsordner und lädt
  hoch, was das Kind meldet: `result.tif` + `mask.tif` oder `export.zip`
  (`objectstore.RESULT_NAMES` bekommt `export.zip`).

### 3.7 Job-Schnittstelle (`api/processing_route.py`, `processing_docs.py`)

- Eingang `aoiProvenance` wie §3.1; für einen Raster-Auftrag `400`.
- Ergebnisdokument eines Exports: `export` (`export.zip`, mit `length`) und
  `recipe`; `…/results/export.zip` → `303`, Dateiname
  `{dataset}_export_{YYYYMMDD}.zip` (K6). Der Link eines Namens, den der Job
  nicht hat, ist `404`.
- `recipe.json` des Links und die Datei im ZIP sind dieselbe Datei (Zeiten des
  Laufs aus dem Bericht des Kindes).

### 3.8 Download-Route (`api/tiler.py`, K5)

Über 500 MB roh bleibt es bei `413` mit Faktorvorschlag. Bei Faktor 1, einem
COG-Datensatz und höchstens `MAX_EXPORT_JOB_BYTES` trägt die Antwort zusätzlich
`X-Export-Job: available`.

### 3.9 Range-Anfragen (F2)

Signierte URLs von S3 erlauben `Range` ohne Zutun; `compose/objectstore/smoke.py`
belegt es in der CI gegen das offizielle Garage-Image für eine URL, wie
`signed_download` sie baut (öffentlicher Endpunkt, `response-content-disposition`,
Schlüssel von `api`): `Range: bytes=n-` → `206`, `Content-Range`, Inhalt gleich,
zwei Teile ergeben das Ganze. In der Sitzung läuft kein Docker-Dienst.

### 3.10 Tests

| Was | Test |
|---|---|
| Grenze | Schätzung genau 500 MB → Zuschnitt läuft; 500 MB + 1 Pixel → `413` mit `X-Export-Job: available`; über 5 GB → `413` ohne Kennung, und die Annahme weist denselben Auftrag mit `413` ab |
| bitgleich | synthetische COGs, Deckel des Zuschnitts im Test gesenkt: ein Item, Mosaik aus zwei Items, zwei Gruppen, Orts-AOI. Synchrones ZIP gegen `export.zip`: Daten und Masken bytegleich, `aoi.geojson` und `citation.bib` gleich, `ATTRIBUTION.txt` gleich bis auf die Zeile `Generated` |
| Speicher je Item | Export einer großen synthetischen COG im eigenen Prozess, einmal mit einem, einmal mit zwei Items: `VmHWM` unter der Grenze, und zwei Items brauchen nicht mehr als eins plus einen kleinen Rest |
| Platte | Spitze im Arbeitsordner ≤ Summe der Dateien + größte Datei |
| Abbruch | `RunCancelled` mitten im Mosaik → Arbeitsordner leer |
| eigener Lauf | zwei gleiche Exporte → zwei Läufe, zwei `result_id`; ein Raster-Auftrag teilt weiter |
| zweckfremd | Export mit Schritten, mit Faktor ≠ 1, Zarr, `aoiProvenance` zu einem Raster-Auftrag, falsche Herkunftsfelder, unbekannter Name in den Begleitdateien, `export.zip` eines Raster-Jobs → `400`/`404`/`422` |
| Logs | kein AOI-Wert, keine Adresse, kein Hash |
| Importregeln | `lint-imports` grün; das Kind lädt weder psycopg noch `earthx.access.download` |

---

## 4. Abnahme

- **Test über die Grenze** (§3.10) grün in der CI.
- **Prüfanleitung für Otto mit einer großen AOI** (§9) im PR.
- `pytest`, `ruff check backend`, `PYTHONPATH=backend lint-imports --config
  .importlinter` grün; der CI-Lauf im PR, mit dem Range-Beleg aus §3.9.

---

## 5. Nicht in dieser Aufgabe

- **M4-11b:** das Angebot im Download-Dialog, nach dem Merge von M4-13 und mit
  dessen Statusanzeige (SSE mit Rückfall), ohne eigene Abfrage-Schleife; Proxy
  `/processing`.
- Export-Job für Zarr blockweise (F6; offene Zeile im Log).
- Mosaik ganzer Szenen je Überflug: M4-12. Permalink über `recipe_id`: M4-19.
- Gröbere Faktoren als Job (K1).
- Items einer Gruppe in verschiedenen UTM-Zonen: wie beim Zuschnitt das Raster
  des ersten Items; keine eigene Regel.

---

## 6. Umfang und Commits (M4-11a)

Geschätzt rund 900 Zeilen Code (davon rund 250 aus `download.py` verschoben)
und rund 900 Zeilen Tests. Commits, je eine Sache:

1. `access`: Regeln des Zuschnitts nach `crop_rules.py`; `processing` nutzt sie.
2. `processing`: Footprints und Provenienz-Dokument im Rezept.
3. `processing`: Kosten und Deckel des Exports.
4. `processing`: Ausgabe `crop` im Kern, `export.zip`.
5. `jobs`/`objectstore`: Migration `007`, eigener Lauf, Begleitdateien, Upload je Ausgabe.
6. `api`: Annahme, `aoiProvenance`, Begleitdateien, Links, `X-Export-Job`.
7. Tests über die Grenze, Bitgleichheit, Speicher.
8. `compose`: Range im Smoke-Test.
9. Doku: Nachträge `adr/0013` §5.1 und `adr/0014`, Log, Status.

---

## 7. Risiken

- **Bitgleichheit im Mosaik:** `mosaic_reader` liest je Item mit `part()` in
  dessen eigenem Raster, der Kern auf dem Raster des ersten Items. Für Items mit
  gleicher Auflösung im Zielraster ist das dasselbe; der Test deckt es ab.
- **Platte des Workers:** Der Arbeitsordner liegt im Container; zwei Slots mit
  je einem Export am Deckel brauchen bis zu rund 2 × (5 GB + größte Datei).
- **Slots:** Ein großer Export belegt einen Slot für Minuten.
- **Speicherplatz im Objektspeicher:** 7 Tage × Exporte bis zum Deckel; ohne
  Konten keine Grenze je Absender (Q9, M6).

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

## 9. Prüfanleitung für Otto (M4-11a, nach dem Merge, PowerShell)

Das Angebot im Dialog kommt mit M4-11b; bis dahin geht der Export über die
Job-Schnittstelle. Die Fläche wählst du selbst: ein Rechteck von etwa 1 × 1 Grad
(mehr als eine Sentinel-2-Kachel), die Werte unten sind Platzhalter.

```powershell
docker compose up -d --build
docker compose ps        # api, tiler, worker, objectstore: healthy

$W, $S, $E, $N = 10.0, 49.0, 11.0, 50.0          # Platzhalter: eigene Fläche eintragen
$aoi = @{ type = 'Polygon'; coordinates = @(,@(@($W,$S), @($E,$S), @($E,$N), @($W,$N), @($W,$S))) }
$search = @{ collections = @('sentinel-2-c1-l2a'); intersects = $aoi
             datetime = '2025-07-01T00:00:00Z/2025-07-31T23:59:59Z'; limit = 100 } | ConvertTo-Json -Depth 10
$items = (Invoke-RestMethod -Method Post -Uri http://localhost:8000/stac/search `
          -ContentType application/json -Body $search).features
$day = $items[0].properties.datetime.Substring(0, 10)          # ein Überflug
$group = @($items | Where-Object { $_.properties.datetime.StartsWith($day) } | ForEach-Object id)
$group.Count

# 1) Der Zuschnitt sagt 413 und bietet den Job an
$crop = @{ groups = @(,$group); assets = @('visual'); aoi = $aoi } | ConvertTo-Json -Depth 10
[IO.File]::WriteAllText("$PWD\crop.json", $crop)       # UTF-8 ohne BOM
curl.exe -s -i -X POST -H "Content-Type: application/json" --data-binary "@crop.json" `
  http://localhost:8001/collections/sentinel-2-c1-l2a/download -o crop-answer.txt
Get-Content crop-answer.txt -TotalCount 12        # HTTP 413, X-Export-Job: available, detail mit MB

# 2) Derselbe Export als Job
$order = @{ recipe_version = 1; aoi = $aoi; steps = @()
            inputs = @(@{ name = 'input'; dataset = 'sentinel-2-c1-l2a'; groups = @(,$group); assets = @('visual') })
            output = @{ kind = 'crop'; format = 'cog'; resolution_factor = 1
                        extent = 'bbox(aoi ∩ footprints)'; mask = 'file' } }
$body = @{ inputs = @{ recipe = $order } } | ConvertTo-Json -Depth 12
$job = Invoke-RestMethod -Method Post -Uri http://localhost:8000/processing/processes/recipe/execution `
       -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
do { Start-Sleep 5; $s = Invoke-RestMethod "http://localhost:8000/processing/jobs/$($job.jobID)"; "$($s.status) $($s.progress)" } `
  while ($s.status -in 'accepted', 'running')

# 3) Herunterladen, auspacken, ansehen
Invoke-RestMethod "http://localhost:8000/processing/jobs/$($job.jobID)/results"
Invoke-WebRequest "http://localhost:8000/processing/jobs/$($job.jobID)/results/export.zip" -OutFile export.zip
Expand-Archive export.zip -DestinationPath export -Force; Get-ChildItem export -Recurse
Get-Content export\ATTRIBUTION.txt              # die .tif-Dateien in QGIS öffnen: EPSG:4326, Maske daneben
```

Zu sehen: `413` mit `X-Export-Job: available`; der Job läuft mit Fortschritt
bis `successful`; im ZIP je Asset Daten und Maske (bei mehreren Gruppen in
`group-NN/`), `aoi.geojson`, `ATTRIBUTION.txt`, `recipe.json` (mit `recipe_id`,
`provenance.kind = "job"`, `footprints`), `citation.bib`. Gegenprobe: dieselbe
Auswahl mit einer kleinen Fläche (etwa 0,1 × 0,1 Grad) lädt direkt als ZIP, ohne
Job, mit denselben Dateinamen. Ein abgebrochener Download des ZIP lässt sich im
Browser fortsetzen (Range, §3.9).

---

## 10. Antworten (Otto, 08.10.2026)

- **F1:** Ergebnis wie der synchrone Zuschnitt (EPSG:4326, gleiche Maske, native
  Auflösung), aber **gerechnet im Kern**: Ausgabeform `crop` in `processing`
  (M4-07a F6), blockweise auf die Platte. Das Kind importiert weiterhin nur
  `processing`, kein `access.download`; `.importlinter` bleibt unverändert. Wo
  nötig, gemeinsame reine Funktionen so schneiden, dass Zuschnitt und Kern
  dieselbe Rasterregel nutzen; Vergleichstest Zuschnitt ↔ Job auf einer kleinen
  AOI (bitgleich).
- **F2:** Option 1, ein `export.zip` wie beim Zuschnitt; die `.tif`-Dateien
  ohne erneute Kompression (`ZIP_STORED`). Der signierte Link muss
  Range-Anfragen erlauben (fortsetzbarer Download); kurz mit Garage belegen.
- **F3:** Option 1, jeder Export rechnet für sich, nie aus dem Cache.
  `ATTRIBUTION.txt` und `citation.bib` baut `api` und gibt sie dem Job mit;
  nicht Teil des Rezept-Hashes.
- **F4:** Option 1, `aoiProvenance` als optionaler zweiter Eingang.
- **F5:** Option 1, 5 GB als Startwert, als Konstante an einer Stelle; die
  Kostenschätzung weist darüber ab.
- **F6:** Option 1, Zarr `422`; offene Zeile im Log („Export-Job für Zarr
  blockweise“).
- **F7/F8:** zwei PRs. M4-11a (Backend) jetzt. M4-11b (Frontend) erst nach dem
  Merge von M4-13 und mit dessen Statusanzeige (SSE mit Rückfall), keine eigene
  Abfrage-Schleife. M4-11b als eigene Zeile in §3 des M4-Plans.
- **K1–K8** angenommen.
- **Ergänzung (Befund aus M4-13):** Der Export-Job verhält sich wie der
  Zuschnitt und liefert je berührter Gruppe eine eigene Rasterdatei samt Maske
  im selben `export.zip`. Dafür darf `run` für die Ausgabeform `crop` mehrere
  Items nacheinander verarbeiten; für andere Ausgabeformen bleibt die
  Abweisung. Die Speichergrenze gilt je Item, belegt mit einem Test über zwei
  Items.


---

## 11. Umsetzung M4-11a (08.10.2026)

**Gebaut** wie §3. Commits: Regeln nach `access/crop_rules.py`; Footprints und
Provenienz-Dokument im Rezept; Schätzung und Deckel; Ausgabe `crop` im Kern;
`jobs` (eigener Lauf, Begleitdateien, Migration `007`, Upload je Ausgabe);
Annahme; Job-Schnittstelle; Kennung im `413`; Range im Smoke-Test; Doku.

**Befunde und Auslegungen:**

1. **Footprints im Rezept** (§3.3, `adr/0014` §15e): nicht in §8 gefragt, aber
   nötig, damit der Kern die Ausdehnung des Zuschnitts kennt und das Rezept
   vollständig bleibt. Nur für `crop`; Hash und `recipe.json` der
   Raster-Rezepte unverändert (die festen Hashwerte aus M4-07a halten).
2. **Lesecache je Item.** Gemessen (6144², drei Bänder `uint8`, eigener
   Prozess): ein Item 353–357 MB, zwei Items zuerst 419–424 MB, drei 506 MB.
   Ursache: `VSI_CACHE_SIZE` (64 MB, `readers.process_gdal_options`) gilt je
   geöffneter Datei; der Zuschnitt öffnet die Items nacheinander, der Export
   hält die einer Gruppe gleichzeitig offen. Der Warp-Puffer war es nicht
   (gleiche Zahlen mit 8 MB `warp_mem_limit`), reines rasterio mit zwei
   `WarpedVRT` kostete +7 MB. **Lösung:** Die Items einer Gruppe teilen sich das
   Budget eines Items (64 MB / Zahl der Items, mindestens 1 MB). Danach: eins
   355–357 MB, zwei 361–364 MB, acht 375 MB. Der Test über zwei Items erlaubt
   höchstens +16 MB und 500 MB insgesamt.
3. **Bitgleich**: Daten-COG und Maske gleichen dem Zuschnitt Byte für Byte, für
   ein Item (dessen fensterweiser Weg), ein Mosaik aus zwei Items (der Weg über
   `mosaic_reader`) und zwei Gruppen. Gegenprobe: mit vertauschter Reihenfolge
   im Mosaik scheitern zwei der drei Fälle.
4. **Mosaik ohne nodata:** Ein Item ohne nodata wird im Mosaik wie in
   `rio_tiler.reader.read` über ein Alpha-Band maskiert, allein wie im
   fensterweisen Weg des Zuschnitts. Im Test nicht belegt (alle synthetischen
   Szenen haben nodata 0); betrifft etwa Kacheln des DEM, das heute je Kachel
   eine Gruppe ist.
5. **Notiz im ZIP:** Wie beim Zuschnitt nennt `ATTRIBUTION.txt` nur Gruppen, die
   ganz wegfielen; einzelne Items, die in einer Gruppe wegfallen, nennt die
   Antwort auf den Auftrag (`skippedItems`).
6. **Abweichung von K3:** `aoi.geojson` ist eine dritte Begleitdatei, weil die
   Herkunft aus `aoiProvenance` (F4) sonst nicht ins Kind käme.
7. **Range (F2):** Der Beleg gegen Garage steht im Smoke-Test der CI
   (`compose-topology`); in der Sitzung läuft kein Docker-Dienst.
