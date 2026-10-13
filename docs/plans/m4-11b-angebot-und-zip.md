# M4-11b — Export-Job im Download-Dialog und Ergebnis als ein ZIP: Plan

**Aufgabe:** M4-11b aus `docs/plans/m4-processing-kern.md` §4, mit dem Zusatz
aus `docs/plans/m4-zusaetze-2026-10-12.md` §1.
**Stufe B** — Plan zur Freigabe; die Session hält an, bis Otto antwortet (§8).
**Ort im Repo:** `docs/plans/m4-11b-angebot-und-zip.md`
**Grundlagen:** `plans/m4-11-export-job.md` (F2, F4, F7, F8, K5–K7, §11
Punkt 7); `plans/m4-13-processing-panel.md` §12; `plans/m4-08b-job-api.md`
(Ergebnislinks, F5); `adr/0015` §6 (F4–F6), §8.1; `adr/0014` §10;
`architekturplan.md` 3.1; `KLAERUNGEN.md` B8, B9.

---

## 1. Ergebnis in drei Sätzen

Antwortet der Zuschnitt mit `413` und `X-Export-Job: available`, bietet der
Download-Dialog „Export as job“ an, zeigt vorher die Schätzung (Größe, Dauer)
und sperrt den Knopf mit Begründung, wenn sie über 5 GB liegt; der gestartete
Job läuft durch dieselbe Statuszeile und denselben Tracker wie im
Processing-Panel (SSE mit Rückfall) und erscheint danach auch dort. Das
Ergebnis eines Raster-Jobs gibt es zusätzlich als ein ZIP mit `result.tif`,
`mask.tif`, `recipe.json` und `citation.bib` (Raster ohne erneute Kompression);
`api` setzt es beim Download aus den Objekten im Speicher zusammen, mit
Range-Anfragen, sodass ein abgebrochener Download fortgesetzt werden kann
(Vorschlag F1). Das Panel zeigt je Job nur noch „Download (ZIP)“ — für einen
Export `export.zip`, für einen Raster-Job das neue ZIP —, die Einzellinks der
API bleiben.

---

## 2. Stand vor dieser Aufgabe (gelesen am 13.10.2026, `main` = `41ddc22`)

- **Abhängigkeiten erfüllt:** M4-11a (#133), M4-13b (#138), M4-21 (#142) sind
  gemergt. M4-12b und M4-13c sind offen; M4-13c berührt die Karte, nicht den
  Download-Dialog (Dateikonflikte §3 des M4-Plans).
- **Zuschnitt im Frontend:** `api.ts` `downloadCrop` (POST
  `/collections/{id}/download`, über den Vite-Proxy an den `tiler`) wirft bei
  jedem Fehler ein schlichtes `Error(detail)`; Status und Kopfzeilen gehen
  verloren. `store.ts` `confirmDownload` macht daraus „Download failed: …“.
  `X-Export-Job` liest das Frontend nirgends.
- **Backend zum `413`:** `api/tiler.py` setzt `X-Export-Job: available` bei
  Faktor 1, COG und höchstens `MAX_JOB_BYTES` (5 GB). Same-origin, kein CORS
  nötig.
- **Processing-Frontend (M4-13b):**
  - `processing.ts`: `estimateOrder`, `placeJob(order)` (nur das Rezept als
    Eingang), `fetchResults`, `resultUrl`.
  - `jobTracker.ts`: `trackJob` (SSE, nach drei Fehlern Abfragen mit
    `Retry-After`); Jobliste in `sessionStorage` (nur `jobID`, `expires`).
  - `processingStore.ts`: Jobs, `FILE_LABELS` (`export.zip` → „Export (ZIP)“
    gibt es schon), `resultFiles` aus dem Ergebnisdokument; Fehlertext eines
    Jobs aus dem `title` des Problems von `/results`.
  - `components/JobList.tsx`: `JobRow({job})` zeigt Status, Fortschritt,
    Abbruch, „Kept until …“, „Expired“ ab `expires − 60 s` und die Links.
    `JobRow` holt `cancelJob`/`removeJob` selbst aus dem Store.
- **AOI-Herkunft:** `placeSearch.ts` hängt an eine AOI der Ortssuche
  `properties = {source, attribution, license}` (`PLACE_SEARCH_PROVENANCE`);
  `orderAoi` nimmt für Aufträge nur `type` und `coordinates`.
- **Ergebnislinks (`api/processing_route.py`):** `LINK_NAMES` = `result.tif`,
  `mask.tif`, `export.zip`, `recipe.json`. Dateien im Speicher → `303` auf eine
  signierte URL (15 min, nie über `expires_at`), ab `expires_at − 60 s` `410`.
  `recipe.json` baut `api` je Job (eigene `recipe_id`); sie liegt nicht im
  Speicher. Ein Raster-Ergebnis wird zwischen gleichen Aufträgen geteilt
  (Q11), `recipe.json` nie.
- **`citation.bib`** gibt es heute nur beim Zuschnitt und im `export.zip`
  (`api/citation.py::citation_bib(config, downloaded=…)`); ein Raster-Job hat
  keine.
- **Objektspeicher-Client** (`objectstore/client.py`): `put`, Multipart,
  `list`, `delete`, `presign_get`; **kein `get_object`**. `api` hat den
  Leseschlüssel (`adr/0015` F6). botocore hält höchstens 10 Verbindungen je
  Client (Vorgabe).
- **Raster-Ergebnis:** bis `MAX_JOB_BYTES` = 5 GB (`processing/plan.py`), also
  ZIP64 nötig. Das Kind meldet `bytes` von `result.tif`, nicht von `mask.tif`,
  und keine Prüfsumme.
- **`adr/0015` F4 (Antwort 1):** stabiler Link in `api` mit `303`; R3 („`api`
  streamt“) wurde verworfen, weil `api` sonst Hunderte MB trägt. Ein ZIP, das
  `api` zusammensetzt, weicht davon ab und braucht Ottos Entscheidung (F1).

---

## 3. Umsetzung (Vorschlag, mit den Empfehlungen aus §8)

### 3.1 Backend: das ZIP eines Raster-Jobs

**Kind** (`jobs/child.py`): nach dem Schreiben je Datei CRC-32 und Größe
(`zlib.crc32`, Blöcke zu 1 MiB, ein Lesedurchgang auf der Platte, rund 1 s je
GB [A]); gemeldet in `result` als `files_meta: {"result.tif": {"bytes", "crc32"},
"mask.tif": {…}}`. Am Lauf gespeichert wie der übrige Bericht; keine
Migration.

**Objektspeicher** (`objectstore/client.py`, `results.py`): `open_result(store,
result_id, name, start, end)` → lesbarer Strom eines Byte-Bereichs (`GetObject`
mit `Range`), mit dem Leseschlüssel. Kein Endpunkt, keine URL nach außen;
`.importlinter` unverändert.

**ZIP-Aufbau** (`api/result_zip.py`, neu, reine Funktionen):
- Reihenfolge `result.tif`, `mask.tif`, `recipe.json`, `citation.bib`; alle
  Einträge `ZIP_STORED` (die Texte sind wenige KB; das spart einen zweiten
  Weg). Feste Zeit je Eintrag (Ende des Laufs, UTC), UTF-8-Kennung, ZIP64-Felder
  nur, wo eine Größe oder ein Versatz 4 GiB erreicht.
- Weil Größen und CRC aller Einträge vorher bekannt sind, ist das ganze ZIP
  vorab berechnet: eine Liste von Abschnitten (Kopf aus Bytes, Daten aus dem
  Speicher, Verzeichnis aus Bytes) mit festen Versätzen. Daraus folgen
  `Content-Length` und jeder beliebige Byte-Bereich, ohne das ZIP je zu bauen.
- Rund 150 Zeilen; `zipfile` der Standardbibliothek kann das nicht, weil es die
  CRC selbst aus den Daten rechnet und ohne Suchen Datendeskriptoren schreibt.

**Route** `GET /processing/jobs/{jobID}/results/result.zip`:
- Gleiche Prüfungen wie die Einzellinks: Name des Jobs (ein Export hat kein
  `result.zip` → `404`), `410` ab `expires_at − 60 s` (bei jeder Anfrage, auch
  jeder Range-Anfrage), `404` vor dem Ende, Problem bei `failed`.
- `200` mit dem ganzen ZIP oder `206` für **einen** Bereich (`bytes=a-b`,
  `a-`, `-n`); mehrere Bereiche → `200` ganz; außerhalb → `416` mit
  `Content-Range: bytes */<Länge>`. `Accept-Ranges: bytes`, `ETag`
  (`"<result_id>-zip"`, die `result_id` steht ohnehin in jeder signierten URL
  des Jobs), `Last-Modified` = Ende des Laufs, `If-Range` beachtet,
  `Cache-Control: no-store`, `Content-Disposition` mit dem Namen aus F3.
- Gelesen wird in Blöcken zu 1 MiB im Threadpool (`iterate_in_threadpool`);
  bricht der Browser ab, endet der Generator und schließt den Strom aus dem
  Speicher; es bleibt nichts liegen.
- Höchstens **4 gleichzeitige ZIP-Downloads je `api`-Prozess** [A]; darüber
  `503` mit `Retry-After: 5` (wie bei SSE `TooManyFollowers`).
- Größen am Anfang einmal per `HeadObject` gegen den Bericht geprüft; passt
  etwas nicht → `500` mit festem Text, Log ohne Schlüssel und Adresse.
- `recipe.json` im ZIP = Bytes des Einzellinks (`job_recipe_json`).
  `citation.bib` = `citation_bib(config, downloaded=<Tag des Laufendes>)`: fest
  je Job, damit ein fortgesetzter Download dieselben Bytes bekommt.
- Ergebnisdokument: neuer Eintrag `bundle` → `result.zip` („Result, mask,
  recipe and citation in one ZIP“, mit `length`), nur wenn der Bericht
  `files_meta` trägt; Prozessbeschreibung und `_check_outputs` kennen
  `bundle`. Ein Ergebnis von vor dieser Änderung (bis 7 Tage alt, auch als
  Cache-Treffer) hat kein `bundle`.
- `adr/0015`: Nachtrag zu §6.1 (R3 nur für dieses ZIP, mit Begründung und
  Grenzen).

**Speicher und Bandbreite [A]:** je Download rund 1–2 MiB Puffer, bei 4
gleichzeitigen unter 10 MB. Jedes Byte geht zweimal durch `api` (vom Speicher
herein, zum Browser hinaus); lokal im selben Netz unkritisch, in Produktion
trägt `api` den Ausgang statt des S3-Anbieters (Kosten und Gewicht von `api`,
vgl. S3 „Job-Schnittstelle in eigenem Prozess“). Ein Download von 5 GB hält
einen der 4 Plätze für die Dauer des Downloads.

**Abbruch:** nichts aufzuräumen. Der Browser setzt über `Range` mit `If-Range`
fort, solange das Ergebnis lebt; danach `410`. Läuft das Ergebnis während eines
Downloads ab (Aufräumen nach `expires_at`), bricht der Strom ab; ein neuer
Versuch bekommt `410`.

**Export unverändert:** `export.zip` liegt fertig im Speicher und bleibt beim
`303` (Range über die signierte URL, M4-11a §11 Punkt 7).

### 3.2 Frontend: Angebot im Download-Dialog

- `api/tiler.py` (K9): Bei Faktor 1 und COG, aber über 5 GB, sagt der `413`
  `X-Export-Job: too-large` statt nichts. Nur so kann der Dialog die Sperre über
  5 GB zeigen; heute fehlt die Kopfzeile dann, und der Dialog sähe denselben
  `413` wie bei Zarr oder einem gröberen Faktor.
- `api.ts` `downloadCrop` wirft bei Fehlern `HttpError` (Status, `detail`) mit
  dem neuen Feld `exportJob` (`available`, `too-large` oder keins).
- `store.ts` `confirmDownload`: `413` mit `exportJob` → Zustand `exportOffer`
  (Datensatz, Gruppen, Assets, AOI) statt Fehlertext; ohne Kopfzeile bleibt der
  heutige Text mit dem Faktorvorschlag.
- `DownloadDialog.tsx`, Abschnitt „Too large for a direct download“:
  - Text des `413`, darunter die Schätzung, die beim Erscheinen des Angebots
    einmal abgefragt wird (`estimateOrder`, Rezept mit `steps: []`, Ausgabe
    `crop` wie M4-11 §3.1, AOI über `orderAoi`): „About 1.8 GB · about 4 min“.
  - `too-large` oder Schätzung über 5 GB (`413` der Schätzung) → Knopf
    gesperrt, Begründung: „An export job may write at most 5 GB. Draw a smaller
    area or choose fewer assets.“ Andere Fehler der Schätzung → Text und „Try
    again“.
  - „Export as job“ → `placeJob(order, {aoiProvenance})`; `aoiProvenance` nur,
    wenn die AOI `properties` der Ortssuche trägt (drei Felder, wie sie sind).
  - Danach zeigt der Dialog die `JobRow` dieses Jobs (Status, Fortschritt,
    „Cancel“, „Download (ZIP)“). Der Job liegt im selben Store wie die Jobs des
    Panels und wird einmal mit `trackJob` verfolgt; geschlossen bleibt er in der
    Jobliste des Panels. Keine eigene Abfrage-Schleife.
- `processing.ts` `placeJob` nimmt optional `aoiProvenance` als zweiten Eingang.

### 3.3 Frontend: Panel zeigt „Download (ZIP)“

- `processingStore.ts`: Aus dem Ergebnisdokument wird **ein** Link gewählt:
  `export` (`export.zip`) oder `bundle` (`result.zip`), Beschriftung „Download
  (ZIP)“. Fehlt beides (Ergebnis von vor dieser Änderung), bleiben die
  Einzellinks wie heute.
- Fehlertexte (englisch, verständlich), aus dem `type` des Problems:
  - `…:disk_space` → Titel des Backends (nennt schon „choose a smaller area …
    or try later“);
  - `…:runtime_exceeded` → „The job took longer than allowed. Choose a smaller
    area or fewer assets.“;
  - Zarr (`422` bei Schätzung oder Start) → `detail` des Backends;
  - abgelaufen (`expires − 60 s` oder `410` von `/results`) → „Expired: results
    are kept for 7 days. Start the export again.“

### 3.4 Tests

| Was | Test |
|---|---|
| ZIP-Aufbau | synthetische Dateien: `zipfile` liest das ZIP, `testzip()` ohne Fehler, Inhalte gleich, Rasterdateien `ZIP_STORED`; Bytes jedes Bereichs gleich dem Ausschnitt des ganzen ZIP (Zufallsbereiche, Ränder, letzter Byte) |
| ZIP64 | Inhalt über 4 GiB aus einem Strom von Nullbytes ohne Platte; `zipfile` liest Größen und CRC (eigener, langsamer Test) |
| Route | `200`, `206`, `416`, mehrere Bereiche → `200`, `If-Range` mit fremdem ETag → `200`; `410` ab `expires − 60 s` auch für Range; Export → `404`; nicht fertig → `404`; `failed` → Problem; fünfter gleichzeitiger Download → `503`; Größe im Speicher ≠ Bericht → `500` |
| Abbruch | Client bricht nach dem ersten Block ab → Strom aus dem Speicher geschlossen, Platz wieder frei |
| Bitgleich | `recipe.json` im ZIP = Einzellink; zweimal geladen am anderen Tag → gleiche Bytes |
| Bericht | Kind meldet `files_meta` mit richtiger CRC und Größe; Ergebnis ohne `files_meta` → kein `bundle` |
| zweckfremd | `result.zip` eines Exports, unbekannter Name, `Range: bytes=abc`, negative und vertauschte Bereiche |
| Logs | kein Schlüssel, keine Adresse, keine AOI, kein Hash; zuerst geprüft, dass Zeilen da sind |
| Kopfzeile | Faktor 1, COG, über 5 GB → `too-large`; Zarr oder Faktor ≠ 1 → keine; bis 5 GB → `available` (bestehender Test) |
| Frontend Dialog | `413` mit `available` → Angebot; mit `too-large` → Angebot gesperrt mit Grund; ohne → heutiger Text; Schätzung über 5 GB → Knopf gesperrt mit Grund; Start schickt `aoiProvenance` nur bei Orts-AOI; Status über `JobRow`; Fehlertexte für `disk_space`, Zarr-`422`, Laufzeitgrenze, abgelaufen |
| Frontend Panel | Raster-Job → ein Link „Download (ZIP)“ auf `result.zip`; Export → `export.zip`; ohne `bundle` → Einzellinks |
| Regeln | `lint-imports`, Wächtertest ohne Datensatz-Literale im Frontend |

---

## 4. Abnahme

- Frontend-Tests für Angebot, Sperre über 5 GB, Status und Fehler (M4-11b);
  Backend-Tests aus §3.4.
- `pytest`, `ruff check backend`, `PYTHONPATH=backend lint-imports --config
  .importlinter`, `npm run lint`, `npx tsc -b --pretty false`, `npm test` grün.
- Prüfanleitung für Otto (§9).

---

## 5. Nicht in dieser Aufgabe

- Processing-Manager (Jobliste, Titel, Archiv): `ui-01-app-rahmen.md`.
- `ATTRIBUTION.txt` und `aoi.geojson` im ZIP eines Raster-Jobs (der Zusatz
  nennt vier Dateien).
- Export-Job für Zarr (S3), Mosaik-Angebot (M4-12b), Vorschau (M4-13c).
- Eine Grenze gleichzeitiger ZIP-Downloads über mehrere `api`-Prozesse.

---

## 6. Umfang und Commits

Geschätzt: Backend rund 350 Zeilen Code und 450 Zeilen Tests; Frontend rund
350 Zeilen Code und 400 Zeilen Tests. Zusammen deutlich über dem Richtwert von
400 Zeilen, deshalb F4. Commits, je eine Sache:

1. `jobs`: Größe und CRC je Ergebnisdatei im Bericht.
2. `objectstore`: Lesen eines Byte-Bereichs.
3. `api`: ZIP-Aufbau (`result_zip.py`).
4. `api`: Route `result.zip`, Eintrag `bundle`, Grenze gleichzeitiger Downloads.
5. `api`: `X-Export-Job: too-large` im `413` des Zuschnitts.
6. Frontend: `HttpError` mit `exportJob` im Zuschnitt.
7. Frontend: Angebot, Schätzung und Start im Download-Dialog, `aoiProvenance`.
8. Frontend: ein Link „Download (ZIP)“ und Fehlertexte.
9. Doku: Nachtrag `adr/0015` §6.1, Log, Status im M4-Plan.

---

## 7. Risiken

- **Gewicht von `api`:** Ein ZIP-Download hält einen von 4 Plätzen und eine
  Verbindung zum Speicher für Minuten. Bei vielen Nutzern ist das die erste
  Stelle, die eng wird; die Einzellinks (`303`) bleiben als Weg ohne `api`.
- **Fortsetzen im Browser:** Chrome und Firefox setzen über `Range` + `If-Range`
  fort; ob jeder Browser es tut, ist nicht gemessen. Ohne Fortsetzen beginnt
  der Download neu (wie heute bei einem Ablauf der signierten URL).
- **Eigener ZIP-Schreiber:** Fehler im Format fallen erst beim Entpacken auf.
  Gegenprobe mit `zipfile` der Standardbibliothek im Test, mit Windows
  (`Expand-Archive`) in Ottos Prüfanleitung.
- **Alte Ergebnisse** haben 7 Tage lang kein ZIP; das Panel zeigt dann die
  Einzellinks.

---

## 8. Fragen an Otto

**F1 — Wer setzt das ZIP eines Raster-Jobs zusammen?**
`recipe.json` ist je Job (eigene `recipe_id`), das Ergebnis wird zwischen
gleichen Aufträgen geteilt (Q11); ein fertiges ZIP im Speicher passt deshalb
nicht ohne Weiteres.
1. `api` streamt das ZIP aus den Objekten im Speicher, Layout vorab berechnet
   (Größe und CRC meldet das Kind): `Content-Length`, Range und Fortsetzen,
   rund 1–2 MiB Speicher je Download, Bytes zweimal durch `api`, höchstens 4
   gleichzeitig; Nachtrag zu `adr/0015` F4 **(Empfehlung)**
2. Wie 1, aber mit `zipfile` und Datendeskriptoren: weniger Code, keine Änderung
   am Kind; ohne `Content-Length` und ohne Range, ein Abbruch beginnt von vorn
3. Der Browser baut das ZIP aus den signierten URLs: `api` trägt nichts; braucht
   CORS am Bucket und einen ZIP-Schreiber im Frontend, und ein Ergebnis bis 5 GB
   liegt im Speicher des Browsers (außer mit der File System Access API, nur
   Chromium)
4. Der Worker legt das ZIP fertig im Speicher ab: `303` und Range wie beim
   Export, kein Gewicht in `api`; dann aber `recipe.json` des Laufs ohne eigene
   `recipe_id` (wie beim Zuschnitt), gegen Zusatz §1 Punkt 2

**F2 — `303` und `410`**
1. Der ZIP-Link antwortet direkt (`200`/`206`) statt `303`; `410` wie die
   Einzellinks ab `expires_at − 60 s`, bei jeder Anfrage auch beim Fortsetzen;
   die Einzellinks bleiben beim `303` **(Empfehlung, folgt aus F1 Option 1)**
2. Wie 1, aber `api` weist einen ZIP-Download schon ab, wenn die Restlaufzeit
   kürzer ist als die Dauer, die der Download bei 10 MB/s bräuchte (`410` mit
   eigenem Text); vermeidet Abbrüche kurz vor dem Ablauf, sperrt dafür früher

**F3 — Dateiname**
1. Außen wie die Einzellinks und der Export: `{dataset}_{operatoren}_{YYYYMMDD}.zip`
   (Tag des Laufendes, nie AOI, Hash oder `jobID`); innen die festen Namen
   `result.tif`, `mask.tif`, `recipe.json`, `citation.bib` aus dem Zusatz
   **(Empfehlung)**
2. Außen wie 1; innen mit demselben Stamm wie die Einzellinks
   (`…_20261013.tif`, `…_mask.tif`, `…_recipe.json`, `…_citation.bib`), damit
   zwei entpackte Ergebnisse im selben Ordner sich nicht überschreiben

**F4 — Schnitt**
1. Zwei PRs auf diesem Plan: **M4-11b1** Backend (ZIP, §3.1) und **M4-11b2**
   Frontend (§3.2, §3.3), je rund 800 Zeilen mit Tests. M4-11b2 braucht einen
   zweiten Branch: in dieser Session nur mit deiner Erlaubnis für den Branch,
   sonst als neue Session **(Empfehlung)**
2. Ein PR mit rund 1 550 Zeilen auf diesem Branch

**Kleinentscheidungen** (gelten, wenn Otto nicht widerspricht):

- **K1** Alle vier Einträge `ZIP_STORED`, auch die Texte (wenige KB).
- **K2** `citation.bib` mit `urldate` = Tag des Laufendes, nicht Tag des
  Downloads, damit ein fortgesetzter Download dieselben Bytes bekommt; die
  Quelle wurde an diesem Tag gelesen.
- **K3** Der neue Ausgang heißt `bundle`, die Datei `result.zip`.
- **K4** Höchstens 4 gleichzeitige ZIP-Downloads je `api`-Prozess, Konstante an
  einer Stelle; darüber `503` mit `Retry-After`.
- **K5** Ergebnisse ohne `files_meta` (vor dieser Änderung) haben kein ZIP; das
  Panel zeigt dann die Einzellinks.
- **K6** Die Schätzung im Dialog wird beim Erscheinen des Angebots einmal
  abgefragt, nicht erst auf Knopfdruck.
- **K7** Der Export-Job des Dialogs erscheint auch in der Jobliste des Panels
  (ein Store, ein Tracker); im Dialog zeigt dieselbe `JobRow` den Status.
- **K8** Die Fehlertexte stehen im Frontend je `type` des Problems; das Backend
  ändert seine festen Titel nicht.
- **K9** `X-Export-Job: too-large` beim `413` über 5 GB (Faktor 1, COG); der
  Wert `available` bleibt, wie er ist. Erweitert M4-11 K5 um einen Wert.

---

## 9. Prüfanleitung für Otto (nach der Umsetzung, PowerShell 5.1)

Wird nach der Freigabe gegen die Antwortform geprüft und im PR ergänzt.
Entwurf:

```powershell
docker compose up -d --build
docker compose ps        # api, tiler, worker, objectstore: healthy
cd frontend; npm run dev  # http://localhost:5173
```

1. **Angebot:** Im Viewer eine Sentinel-2-Szene wählen, eine AOI von etwa
   1 × 1 Grad zeichnen und mehrere Assets wählen, bis der Zuschnitt über 500 MB
   liegt, „Crop & merge to AOI“ → statt „Download failed“ der
   Abschnitt „Too large for a direct download“ mit Schätzung und „Export as
   job“.
2. **Sperre:** eine AOI über mehrere Szenen eines Überflugs und alle Assets,
   bis der Zuschnitt über 5 GB liegt → Angebot mit gesperrtem Knopf, Grund
   darunter.
3. **Job:** „Export as job“ → Fortschritt im Dialog; Dialog schließen → derselbe
   Job im Processing-Panel; am Ende „Download (ZIP)“ → `…_export_YYYYMMDD.zip`.
4. **Raster-Job im Panel:** NDVI starten; am Ende nur „Download (ZIP)“.

```powershell
$job = '<jobID aus dem Panel>'
$base = "http://localhost:8000/processing/jobs/${job}/results"
Invoke-RestMethod $base                                 # bundle -> result.zip, mit length
Invoke-WebRequest "${base}/result.zip" -OutFile result.zip
Expand-Archive result.zip -DestinationPath result -Force; Get-ChildItem result
curl.exe -s -D - -o part.bin -r 0-1023 "${base}/result.zip"   # HTTP/1.1 206, Content-Range: bytes 0-1023/...
```

Zu sehen: im ZIP `result.tif`, `mask.tif`, `recipe.json`, `citation.bib`; die
`.tif` öffnen in QGIS wie die Einzeldateien; `206` mit `Content-Range`. Ein im
Browser abgebrochener Download des ZIP lässt sich fortsetzen.
