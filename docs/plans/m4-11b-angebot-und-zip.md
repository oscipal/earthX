# M4-11b — Export-Job im Download-Dialog und Ergebnis als ein ZIP: Plan

**Aufgabe:** M4-11b aus `docs/plans/m4-processing-kern.md` §4, mit dem Zusatz
aus `docs/plans/m4-zusaetze-2026-10-12.md` §1.
**Stufe B** — **von Otto am 13.10.2026 freigegeben** (§10), mit Ergänzungen zu
F1 (Recherche, ZIP64-Test, CRC-Herkunft, Nachtrag `adr/0015`). Geschnitten in
**M4-11b-1** (Backend, dieser PR) und **M4-11b-2** (Frontend, neue Session nach
dem Merge). §3 beschreibt die freigegebene Fassung; §8 bleibt als Wortlaut der
Fragen stehen.
**Ort im Repo:** `docs/plans/m4-11b-angebot-und-zip.md`
**Grundlagen:** `plans/m4-11-export-job.md` (F2, F4, F7, F8, K5–K7, §11
Punkt 7); `plans/m4-13-processing-panel.md` §12; `plans/m4-08b-job-api.md`
(Ergebnislinks, F5); `adr/0015` §6 (F4–F6), §8.1; `adr/0014` §10;
`architekturplan.md` 3.1; `KLAERUNGEN.md` B8, B9.

---

## 1. Ergebnis in drei Sätzen

Das Ergebnis eines Raster-Jobs gibt es zusätzlich als **ein ZIP** mit einem
Ordner, der den Namensstamm der ZIP-Datei trägt, und darin `result.tif`,
`mask.tif`, `recipe.json` und `citation.bib` (Raster ohne erneute Kompression):
`api` setzt es beim Download aus den Objekten im Speicher zusammen, mit
`Content-Length` und Range-Anfragen, sodass ein abgebrochener Download
fortgesetzt werden kann; die 60-Sekunden-Regel der Einzellinks gilt bei jeder
Anfrage. Dazu sagt der `413` des Zuschnitts über 5 GB mit
`X-Export-Job: too-large`, dass der Export auch als Job nicht läuft. Das
Frontend (Angebot im Download-Dialog, Schätzung, Sperre, „Download (ZIP)“ im
Panel) folgt als **M4-11b-2** in einer neuen Session und ist in §3.2 bis §3.4
nur beschrieben.

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

## 3. Umsetzung (freigegebene Fassung)

### 3.1 Backend: das ZIP eines Raster-Jobs (M4-11b-1, dieser PR)

#### 3.1.1 Stand der Technik: ZIPs aus Dateien im Speicher streamen

Geprüft sind die verbreiteten Wege, ein ZIP aus Einzeldateien beim Abruf zu
bauen. Belegstufen wie `adr/0009`.

| Weg | Was die Quelle sagt | Folge für uns |
|---|---|---|
| **nginx `mod_zip`** (Evan Miller) | Das Backend liefert eine Liste „CRC-32, Größe, Ort, Name“ je Datei, der Server baut das ZIP im Strom und holt die Teile selbst. Fortsetzen über `Range` und `If-Range` gehe, „although these feature require the server to know the file checksums (CRC-32's) in advance“; mit `-` statt der CRC „mod_zip will disable support for the `Range` header“. Ein Fehler bei einem Teil breche den Download ab. Ein `Last-Modified` des Backends brauche `If-Range`, derselbe Zeitstempel gelte für alle Einträge, damit das Archiv bei jeder Anfrage byte-gleich sei **[S]** — README, <https://github.com/evanmiller/mod_zip> | Das ist unser Muster: CRC und Größe vorher, ein Zeitstempel, byte-gleiches ZIP je Anfrage. Wir brauchen kein nginx, weil `api` den Strom ohnehin liefert (siehe unten) |
| **`zipstream-ng`** | „Can calculate the total size of the resulting zip file before generation even begins“, wenn nichts komprimiert wird; verfolgt `last_modified`; „Automatically uses Zip64 extensions, but only if they are required“ **[S]** — README, <https://github.com/pR0Ps/zipstream-ng>. Zu `Range` und zur Herkunft der CRC sagt die README nichts | Größe vorab ja; einen Byte-Bereich mitten im ZIP kann die Bibliothek nach ihrer README nicht liefern. Eine neue Abhängigkeit braucht eine erneuerte Lock-Datei (`CLAUDE.md`) |
| **`stream-zip`** (uktrade) | „Creates both Zip32/2.0/Legacy and Zip64 files“, ohne das ganze ZIP im Speicher oder auf der Platte zu halten **[S]** — README, <https://github.com/uktrade/stream-zip>. Dass unkomprimierte Einträge ganz gepuffert werden und das Format vorab gewählt werden muss, steht in Zusammenfassungen der Dokumentation, die in der Sitzung nicht erreichbar war **[S]** | Für Rasterdateien bis 5 GB ungeeignet, falls das stimmt; belegt ist es nicht |
| **`zipfile` der Standardbibliothek** | schreibt in einen Strom mit Datendeskriptoren; die CRC rechnet es aus den Daten, nicht aus einer Vorgabe; `ZIP64_LIMIT = (1 << 31) - 1`; die ZIP64-Erweiterung enthält erst die Größe, dann die gepackte Größe, im Zentralverzeichnis zuletzt den Versatz; ZIP64-Ende, wenn die Zahl der Einträge, der Versatz oder die Größe des Zentralverzeichnisses die Grenze überschreitet **[P]** — `/usr/lib/python3.12/zipfile/__init__.py` des Projekt-Python 3.12.3, Z. 52 (`ZIP64_LIMIT`), 168–174 (Strukturen), 486–493, 2037–2043 | als Leser im Test ideal, als Schreiber für ein ZIP mit vorab bekannten CRC nicht |
| **Presigned URLs** (unser Weg bei `export.zip` und den Einzelfiles) | `303` auf eine signierte URL, Range ohne Zutun **[M]** (`plans/m4-11-export-job.md` §11 Punkt 7) | gilt weiter für alle Einzeldateien; ein ZIP aus mehreren Objekten und einem Dokument je Job lässt sich so nicht liefern |

Die READMEs von `mod_zip`, `zipstream-ng` und `stream-zip` hat die Sitzung mit
dem Abrufwerkzeug gelesen, das den Inhalt zusammenfasst; ihr Wortlaut ist darum
nur **[S]**. Die Dokumentation von `stream-zip` und die PKWARE-APPNOTE waren
von der Sitzung aus nicht erreichbar.

**Warum `api` hier passt.** Das ZIP braucht Inhalt, den es im Speicher nicht gibt
(`recipe.json` je Job mit eigener `recipe_id`, `citation.bib`), und Teile, die
mehrere Aufträge teilen (das Raster, Q11). Es bleibt also kein anderer Ort als
eine Stelle, die beides kennt: `api` kennt die Rezepte und den Leseschlüssel
(`adr/0015` F6). Der Worker kann es nicht fertig ablegen, ohne `recipe.json` von
der `recipe_id` zu trennen (F1 Option 4, verworfen), und der Browser nicht
bauen, ohne bis zu 5 GB im Speicher zu halten (F1 Option 3). Die Last, die
`adr/0015` F4 dazu bewogen hat, `api` nicht streamen zu lassen („Hunderte MB“),
wird hier durch den Aufbau begrenzt: ein Lesepuffer von 1 MiB je Download, kein
Zwischenspeichern, kein Neuberechnen (kein Komprimieren, keine CRC im Abruf),
höchstens 4 Downloads gleichzeitig je Prozess. Nachtrag in `adr/0015` §14b (d).

**Eigener Schreiber, keine neue Abhängigkeit.** Das Format mit vorab bekannten
Größen und CRC (keine Datendeskriptoren) ist knapp 150 Zeilen; die einzige
Bibliothek, die Byte-Bereiche mitten im ZIP könnte, ist `mod_zip`, und das ist
ein nginx-Modul. Als Gegenprobe liest `zipfile` das Ergebnis im Test.

#### 3.1.2 Herkunft von CRC-32 und Größe (c)

- **Wer rechnet:** der **Aufseher** (`jobs/worker.py::_upload_and_finish`), nicht
  das Kind. Er liest jede Datei vor dem Hochladen einmal in Blöcken zu 1 MiB
  (`zlib.crc32`), im selben Thread und unter demselben Herzschlag wie das
  Hochladen (`_while_beating`); die CRC gilt damit für genau die Bytes, die
  hochgeladen werden. Das Kind bleibt unverändert (B9).
- **Wohin:** in das Ergebnis des Laufs, `earthx_run.result` (jsonb), Schlüssel
  `files_meta`: `{"result.tif": {"bytes": n, "crc32": c}, "mask.tif": {…}}`.
  **Keine Migration**; `result` ist schon ein freies Dokument. Nur Raster-Läufe;
  `export.zip` braucht es nicht.
- **Cache-Treffer:** teilen den Lauf und damit `files_meta`. Ergebnisse von vor
  dieser Änderung (höchstens 7 Tage alt) haben es nicht und damit kein `bundle`
  (K5).
- **Hilfsfunktion** `file_facts(path)` neben `upload_result` in
  `objectstore/results.py` (dort ist sie neutral und `jobs` darf sie nutzen);
  der Schlüsselname steht dort als Konstante, `api` liest ihn gegen dieselbe.
- **Kosten** [A]: rund 1–2 s je GB auf der lokalen Platte, gemessen im PR.

#### 3.1.3 Objektspeicher: Größe und Byte-Bereich lesen

`objectstore/client.py`: `S3.head_size(key)` (`HeadObject`) und
`S3.get_range(key, start, end)` (`GetObject` mit `Range`, ein lesbarer Strom mit
`read(n)` und `close()`); `objectstore/results.py`: `result_size(store,
result_id, name)` und `open_result_range(store, result_id, name, start, end)`.
Wie alle Funktionen dort nehmen sie nur `Store`, `result_id` und einen Namen aus
der festen Menge; kein Endpunkt, keine URL. `.importlinter` bleibt unverändert.

#### 3.1.4 Aufbau des ZIP (`api/result_zip.py`, neu)

- **Inhalt** (F3, Otto): ein Ordner mit dem Namensstamm der ZIP-Datei
  (`{dataset}_{operatoren}_{YYYYMMDD}`), darin `result.tif`, `mask.tif`,
  `recipe.json`, `citation.bib` in dieser Reihenfolge. Ein Eintrag für den Ordner
  selbst gibt es nicht (jeder Entpacker legt ihn aus den Pfaden an).
- **Alle Einträge `ZIP_STORED`** (K1), ohne Datendeskriptor (Größe und CRC stehen
  im lokalen Kopf), UTF-8-Kennung gesetzt, ein fester Zeitstempel für alle
  (Ende des Laufs, UTC, nicht vor 1980), Unix-Rechte `0644`.
- **ZIP64 je Eintrag**, wo die Größe `0xFFFFFFFF` erreicht (lokaler Kopf: die
  Erweiterung 0x0001 mit Größe und gepackter Größe, beide Felder des Kopfes
  `0xFFFFFFFF`, Version 45); im Zentralverzeichnis zusätzlich der Versatz, wo er
  `0xFFFFFFFF` erreicht. **ZIP64-Ende** (Datensatz und Verweis), wo das
  Zentralverzeichnis hinter `0xFFFFFFFF` beginnt oder die Zahl der Einträge 
  `0xFFFF` erreicht. Das Format folgt dem von `zipfile` gelesenen und
  geschriebenen (CPython 3.12, §3.1.1) **[P]**; die Spezifikation (PKWARE
  APPNOTE) war in der Sitzung nicht erreichbar und ist nicht gelesen.
- **Vorab berechnet:** `Layout` hält die Abschnitte (Kopf, Daten, …,
  Zentralverzeichnis, Ende) mit festen Versätzen. Daraus folgen `total`
  (`Content-Length`) und `segments(start, end)`: die Abschnitte eines
  Byte-Bereichs, entweder fertige Bytes (Köpfe, `recipe.json`, `citation.bib`,
  Verzeichnis) oder ein Stück einer Datei im Speicher.

#### 3.1.5 Route `GET /processing/jobs/{jobID}/results/result.zip`

- **Gleiche Prüfungen wie die Einzellinks** (F2, Otto): Job unbekannt oder
  verworfen → `404`; ab `expires_at − 60 s` bis zum Löschen der Zeilen `410`,
  **bei jeder Anfrage, auch jeder Range-Anfrage**; ein fortgesetzter Download
  nach dem Ablauf gibt also `410`. Nicht fertig → `404`, gescheitert → Problem
  der Fehlerart, ein Export oder ein Ergebnis ohne `files_meta` → `404`.
- **Antwort:** `200` mit dem ganzen ZIP oder `206` für genau **einen** Bereich
  (`bytes=a-b`, `bytes=a-`, `bytes=-n`). Mehrere Bereiche, ein anderer
  Einheitenname oder ein Bereich, der nicht der Syntax folgt oder dessen Ende vor
  dem Anfang liegt, werden überhört (RFC 9110 §14.2, §14.1.1 erlauben es) und
  geben `200` ganz; ein Bereich hinter dem Ende (oder Suffix `-0`) gibt `416` mit
  `Content-Range: bytes */<Länge>`. Kopfzeilen: `Accept-Ranges: bytes`,
  `Content-Length`, `Content-Range` bei `206`, `ETag` (starker Hash über Namen,
  Größen, CRC und Zeitstempel der Einträge, 128 Bit; er enthält weder
  `result_id` noch Rezeptwerte), `Last-Modified` (Ende des Laufs),
  `If-Range` mit `ETag` oder genau diesem Datum, `Cache-Control: no-store`,
  `Content-Disposition: attachment; filename="…"` mit dem Namen der Einzellinks
  (`{dataset}_{operatoren}_{YYYYMMDD}.zip`).
- **Vor dem Strom** (`HeadObject` auf beide Dateien): fehlt eine oder weicht die
  Größe vom Bericht ab → `500` mit festem Text, ein Logeintrag ohne Schlüssel
  und Adresse. Ein Speicher, der nicht antwortet → `503` mit `Retry-After: 5`
  wie bei den signierten Links.
- **Strom:** Blöcke zu 1 MiB im Threadpool; bricht der Browser ab, endet der
  Strom und schließt den Lesestrom zum Speicher, ohne dass etwas zurückbleibt.
  Liefert der Speicher weniger Bytes als versprochen, bricht `api` die
  Verbindung ab (der Client sieht einen unvollständigen Download, nie ein
  kürzeres, scheinbar fertiges ZIP) und loggt es ohne Schlüssel.
- **Grenze** (K4): höchstens **4 gleichzeitige ZIP-Downloads je `api`-Prozess**;
  der fünfte gibt `503` mit `Retry-After: 5`. Der Platz wird beim Ende der
  Antwort frei, auch bei Abbruch oder Fehler.
- **Dateiinhalt:** `recipe.json` im ZIP sind dieselben Bytes wie der Einzellink
  (`job_recipe_json`); `citation.bib` ist `citation_bib(config, downloaded=<Tag
  des Laufendes>)` (K2). Kennt die Registry den Datensatz nicht mehr, entfällt
  `citation.bib` (wie `recipe.json` dann ohne Attribution kommt).
- **Ergebnisdokument:** Ausgang `bundle` → `result.zip` („Result, mask, recipe
  and citation in one ZIP“, `application/zip`, mit `length`), nur wenn
  `files_meta` beide Dateien nennt. Die Prozessbeschreibung nennt den Ausgang
  immer, und die frontend-Fixtures der Prozessbeschreibungen werden mit dem
  Skript neu geschrieben.

**Speicher und Bandbreite [A], gemessen im PR (§11):** je Download 1–2 MiB Puffer,
bei 4 gleichzeitigen unter 10 MB. Jedes Byte geht zweimal durch `api` (vom
Speicher herein, zum Browser hinaus); lokal im selben Netz unkritisch, in
Produktion trägt `api` den Ausgang statt des S3-Anbieters. Ein Download von
5 GB hält einen der vier Plätze für seine Dauer.

**Abbruch:** nichts aufzuräumen. Der Browser setzt mit `Range` und `If-Range`
fort, solange das Ergebnis lebt; danach `410`. Läuft das Ergebnis während eines
Downloads ab, kann der Strom abbrechen; ein neuer Versuch bekommt `410`.

**Export unverändert:** `export.zip` liegt fertig im Speicher und bleibt beim
`303` (M4-11a §11 Punkt 7); sein Aufbau ändert sich nicht.

#### 3.1.6 `X-Export-Job: too-large` (K9)

`api/tiler.py`: Bei Faktor 1 und COG, aber über `MAX_JOB_BYTES`, trägt der `413`
`X-Export-Job: too-large`; nur so kann der Dialog (M4-11b-2) die Sperre über
5 GB von einem Zarr-Datensatz oder einem gröberen Faktor unterscheiden. Der Wert
`available` bleibt, wie er ist; ohne Kopfzeile bleibt es für alles andere.

### 3.2 Frontend: Angebot im Download-Dialog (M4-11b-2, nicht in diesem PR)

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

### 3.3 Frontend: Panel zeigt „Download (ZIP)“ (M4-11b-2, nicht in diesem PR)

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

**M4-11b-1 (Backend, dieser PR):**

| Was | Test |
|---|---|
| Aufbau | synthetische Dateien: `zipfile` liest das ZIP, `testzip()` ohne Fehler, alle Namen unter dem Ordner des Namensstamms, Inhalte gleich, alle Einträge `ZIP_STORED`; dieselben Bytes bei jedem Aufbau (kein Zeitstempel der Wanduhr) |
| Bereiche | jeder Byte-Bereich gleich dem Ausschnitt des ganzen ZIP: Zufallsbereiche, jede Grenze zwischen den Abschnitten (±1), erster und letzter Byte, ein Bereich über mehrere Abschnitte |
| ZIP64 (b) | ein Stub ohne Platte: Eintrag von 4,5 GB Nullbytes mit bekannter Größe und CRC, dahinter ein kleiner Eintrag (Versatz und Zentralverzeichnis hinter 4 GiB). Eine Datei, die `Layout` byteweise liest, ohne das ZIP zu bauen; `zipfile` liest Größen, `header_offset` des zweiten Eintrags über `2**32` und Inhalt und CRC beider Einträge. Grenzfälle: Größe `0xFFFFFFFE` ohne ZIP64-Erweiterung, `0xFFFFFFFF` mit; ZIP64-Ende erst, wo das Zentralverzeichnis hinter `0xFFFFFFFF` beginnt |
| CRC und Größe (c) | der Aufseher meldet `files_meta` mit der CRC der hochgeladenen Bytes (gegen `zlib.crc32` des Objekts im Speicher); kein `files_meta` bei einem Export; ein Cache-Treffer erbt es; ein Lauf von vor der Änderung hat kein `bundle` |
| Speicher | `head_size`, `get_range` gegen `moto`: Bereich, Suffix, außerhalb, fehlendes Objekt (`ResultNotFound`), kein Schlüssel und keine Adresse in den Fehlertexten |
| Route | `200`; `206` für `a-b`, `a-`, `-n`; `416`; mehrere Bereiche, falsche Syntax und vertauschte Bereiche → `200` ganz; `If-Range` mit eigenem ETag → `206`, mit fremdem → `200`; `ETag` gleich bei jedem Abruf, anders bei einem anderen Ergebnis; `Content-Length` gleich der Summe der Bytes; die Bytes gleich `Layout`; `recipe.json` im ZIP gleich dem Einzellink |
| 410 (F2) | ab `expires_at − 60 s` `410` für den ganzen Abruf und für eine Range-Anfrage danach; ein Abruf kurz davor geht, derselbe eine Minute später nicht (Ablauf mit der Zeit des Tests) |
| Namen | Export, Ergebnis ohne `files_meta`, nicht fertig, gescheitert, unbekannt oder verworfen → die Antworten der Einzellinks (`404` bzw. Problem); der Ordner und der Dateiname tragen nie AOI, Hash oder `jobID` |
| Speicher abweichend | Größe im Speicher ≠ Bericht, Objekt fehlt, Speicher antwortet nicht → `500`, `500`, `503`; liefert der Speicher mitten im Strom weniger, bricht die Antwort ab (Client sieht einen Fehler, kein kürzeres ZIP) |
| Grenze (K4) | der fünfte gleichzeitige Download → `503` mit `Retry-After`; ein Platz wird frei nach dem Ende, nach einem Abbruch des Clients und nach einem Fehler im Strom; der Lesestrom wird geschlossen |
| Beschreibung | Prozessbeschreibung und Ergebnisdokument nennen `bundle` nur, wo es das ZIP gibt; `outputs` mit `bundle` bei einem Raster-Auftrag geht, bei einem Export `400` |
| Logs | kein Schlüssel, keine Adresse, keine AOI, kein Hash; zuerst geprüft, dass Zeilen da sind (`own_log_text`) |
| Kopfzeile (K9) | Faktor 1, COG, über 5 GB → `too-large`; Zarr oder Faktor ≠ 1 → keine; bis 5 GB → `available` (bestehender Test) |
| Regeln | `lint-imports`, die Prozess-Fixtures des Frontends sind neu geschrieben |

**M4-11b-2 (Frontend, neue Session, hier nur beschrieben):**

| Was | Test |
|---|---|
| Dialog | `413` mit `available` → Angebot; mit `too-large` → Angebot gesperrt mit Grund; ohne → heutiger Text; Schätzung über 5 GB → Knopf gesperrt mit Grund; Start schickt `aoiProvenance` nur bei Orts-AOI; Status über `JobRow`; Fehlertexte für `disk_space`, Zarr-`422`, Laufzeitgrenze, abgelaufen |
| Panel | Raster-Job → ein Link „Download (ZIP)“ auf `result.zip`; Export → `export.zip`; ohne `bundle` → Einzellinks |
| Regeln | Wächtertest ohne Datensatz-Literale im Frontend, `npm run lint`, `npx tsc -b --pretty false`, `npm test` |

---

## 4. Abnahme

- **M4-11b-1:** Backend-Tests aus §3.4 grün, `pytest`, `ruff check backend` und
  `PYTHONPATH=backend lint-imports --config .importlinter` grün; Messung von
  Speicher, Bandbreite und CRC-Zeit im PR (§11); Prüfanleitung für Otto (§9).
- **M4-11b-2:** Frontend-Tests für Angebot, Sperre über 5 GB, Status und Fehler;
  Prüfanleitung für Otto: Zuschnitt über 500 MB im Viewer, Job starten, ZIP laden
  und öffnen.

---

## 5. Nicht in dieser Aufgabe

- **M4-11b-2 (Frontend):** Angebot im Download-Dialog, Schätzung, Sperre,
  `aoiProvenance`, „Download (ZIP)“ im Panel, Fehlertexte (§3.2, §3.3). Neue
  Session nach dem Merge dieses PR; Startsatz: „Führe Aufgabe M4-11b-2 aus
  `docs/plans/m4-processing-kern.md` aus (Plan: `docs/plans/m4-11b-angebot-und-zip.md`).“
- Processing-Manager (Jobliste, Titel, Archiv): `ui-01-app-rahmen.md`.
- `ATTRIBUTION.txt` und `aoi.geojson` im ZIP eines Raster-Jobs (der Zusatz
  nennt vier Dateien).
- Export-Job für Zarr (S3), Mosaik-Angebot (M4-12b), Vorschau (M4-13c).
- Eine Grenze gleichzeitiger ZIP-Downloads über mehrere `api`-Prozesse.

---

## 6. Umfang und Commits

**M4-11b-1:** geschätzt rund 450 Zeilen Code und 650 Zeilen Tests, damit über
dem Richtwert von 400 geänderten Zeilen; das ist F4 (zwei PRs) schon, weiter
lässt sich das ZIP nicht trennen (Schreiber, Route und Messwerte gehören
zusammen). **M4-11b-2:** rund 350 Zeilen Code und 400 Zeilen Tests. Commits des
ersten PR, je eine Sache:

1. Doku: dieser Plan, Antworten Otto, Zeilen im Log.
2. `objectstore`: Größe und CRC einer Datei; Größe und Byte-Bereich eines Objekts.
3. `jobs`: `files_meta` beim Hochladen eines Raster-Ergebnisses.
4. `api`: ZIP-Aufbau (`result_zip.py`).
5. `api`: Route `result.zip`, Ausgang `bundle`, Grenze gleichzeitiger Downloads,
   Fixtures der Prozessbeschreibungen.
6. `api`: `X-Export-Job: too-large` im `413` des Zuschnitts.
7. Doku: Nachtrag `adr/0015` §14b, Log, Status, Messwerte.

---

## 7. Risiken

- **Gewicht von `api`:** Ein ZIP-Download hält einen von 4 Plätzen und eine
  Verbindung zum Speicher für Minuten. Bei vielen Nutzern ist das die erste
  Stelle, die eng wird; die Einzellinks (`303`) bleiben als Weg ohne `api`.
- **Fortsetzen im Browser:** Der Server liefert, was ein fortsetzender Client
  braucht (`Accept-Ranges`, starker `ETag`, `Last-Modified`, `If-Range`). Ob ein
  bestimmter Browser damit fortsetzt, ist nicht gemessen [A]; ohne Fortsetzen
  beginnt der Download neu (wie heute bei einem Ablauf der signierten URL).
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

## 9. Prüfanleitung für Otto (M4-11b-1, nach der Umsetzung)

Wird mit der Umsetzung geschrieben (§11).

---

## 10. Antworten (Otto, 13.10.2026)

- **F1:** Option 1, `api` streamt das ZIP, fortsetzbar. Ergänzt um (a) den
  Stand der Technik mit Quellen und die Begründung, warum `api` hier passt
  (§3.1.1), (b) einen ZIP64-Test mit einem Eintrag über 4 GiB, ohne 4 GiB zu
  schreiben, über einen Stub mit bekannter Größe und CRC (§3.4), (c) die
  Herkunft von CRC-32 und Größe, und wo ein neu gespeicherter Wert hinkommt
  (§3.1.2: Aufseher, `earthx_run.result["files_meta"]`, keine Migration) und
  (d) einen Nachtrag in `adr/0015` zu F4 mit Begründung, Speicher je Download
  und Bandbreite (`adr/0015` §14b).
- **F2:** Option 1 mit der 60-Sekunden-Regel wie bei den Einzellinks; ein
  fortgesetzter Download nach dem Ablauf gibt `410` (§3.1.5). Nicht Option 2.
- **F3:** Option 1, dazu **ein Ordner im ZIP** mit demselben Namensstamm wie die
  ZIP-Datei; darin `result.tif`, `mask.tif`, `recipe.json`, `citation.bib`
  (§3.1.4).
- **F4:** Option 1, aber dieser PR **nur Backend** (M4-11b-1). Das Frontend
  folgt als neue Session nach dem Merge als **M4-11b-2**, eigene Zeile in §3 des
  M4-Plans.
- **K1–K9** angenommen.
- **Log:** Die Zeile zu M4-21 steht von „Vorschlag“ auf „fest“.
