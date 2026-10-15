# M4-11b — Export-Job im Download-Dialog und Ergebnis als ein ZIP: Plan

**Aufgabe:** M4-11b aus `docs/plans/m4-processing-kern.md` §4, mit dem Zusatz
aus `docs/plans/m4-zusaetze-2026-10-12.md` §1.
**Stufe B** — **von Otto am 13.10.2026 freigegeben** (§10), mit Ergänzungen zu
F1 (Recherche, ZIP64-Test, CRC-Herkunft, Nachtrag `adr/0015`). Geschnitten in
**M4-11b-1** (Backend, dieser PR) und **M4-11b-2** (Frontend, neue Session nach
dem Merge). §3 beschreibt die freigegebene Fassung; §8 bleibt als Wortlaut der
Fragen stehen. **M4-11b-2** mit dem Zusatz `plans/m4-zusaetze-2026-10-12.md` §1a:
§12 (Plan zu §1a, von Otto am 15.10.2026 beantwortet, §12.7) und §13.2 (Umsetzung).
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
| **`zipstream-ng`** | „Can calculate the total size of the resulting zip file before generation even begins“, wenn nichts komprimiert wird; verfolgt `last_modified`; „Automatically uses Zip64 extensions, but only if they are required“ **[S]** — README, <https://github.com/pR0Ps/zipstream-ng>. Zu `Range` und zur Herkunft der CRC sagt die README nichts | Größe vorab ja; einen Byte-Bereich mitten im ZIP erwähnt die README nicht. Eine neue Abhängigkeit braucht eine erneuerte Lock-Datei (`CLAUDE.md`) |
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
Größen und CRC (keine Datendeskriptoren) braucht rund 350 Zeilen mit Kommentaren, Prüfungen und der Bereichsauswertung; die einzige
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
  dieser Änderung (höchstens 7 Tage alt) haben es nicht und damit kein `bundle`;
  ihr ZIP-Link antwortet `409` mit Grund (K5, unten).
- **Warum `409` und kein Nachrechnen** (Otto, 14.10.2026, die einfachere Wahl):
  Nachrechnen hieße, beim ersten ZIP-Abruf bis zu 5 GB aus dem Speicher zu lesen
  (rund 0,5 s je GB nur für die CRC, dazu die Übertragung) und aus `api` in die
  Tabelle der Queue zu schreiben, die bisher nur der Aufseher beschreibt; dazu ein
  Rennen zweier Abrufe und ein Weg, wie die Zahl zurück in den Lauf kommt, den
  mehrere Aufträge teilen. Das alles für ein Ergebnis, das höchstens 7 Tage lebt,
  nur einmal pro alter Lauf gebraucht wird und dessen Einzellinks (`303`, `recipe.json`)
  weiter gehen. Die Lücke schließt sich von selbst: sieben Tage nach dem Merge hat
  jedes lebende Ergebnis `files_meta`.
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
  (`{dataset}_{operatoren}_{Tag}`, Tag nach §3.1.7), darin `result.tif`, `mask.tif`,
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
  der Fehlerart, ein Export → `404` (sein ZIP heißt `export.zip`). Ein Raster-Ergebnis
  **ohne `files_meta`** (vor dieser Änderung gemacht, oder ein Eintrag, den
  `reported_files` nicht als beide Dateien mit Größe und CRC lesen kann) → **`409`**,
  Typ `urn:earthx:no-bundle`, Titel „No bundle“, Text „this result was created
  before bundles existed; use the single links (result.tif, mask.tif, recipe.json)“.
  Die Reihenfolge der Prüfungen: `410` vor `404` (nicht fertig) vor Problem
  (gescheitert) vor `409`; das Ergebnisdokument nennt `bundle` für ein solches
  Ergebnis nicht, die Einzellinks gehen.
- **Antwort:** `200` mit dem ganzen ZIP oder `206` für genau **einen** Bereich
  (`bytes=a-b`, `bytes=a-`, `bytes=-n`). Mehrere Bereiche, ein anderer
  Einheitenname oder ein Bereich, der nicht der Syntax folgt oder dessen Ende vor
  dem Anfang liegt, werden überhört (RFC 9110 §14.2, §14.1.1 erlauben es) und
  geben `200` ganz; ein Bereich hinter dem Ende (oder Suffix `-0`) gibt `416` mit
  `Content-Range: bytes */<Länge>`. Kopfzeilen: `Accept-Ranges: bytes`,
  `Content-Length`, `Content-Range` bei `206`, `ETag` (starker Hash über Namen,
  Größen, CRC und Zeitstempel der Einträge, 128 Bit; er enthält weder
  `result_id` noch Rezeptwerte), `Last-Modified` (Ende des Laufs),
  `If-Range` nur mit dem `ETag` (das Datum des Laufs bewegt sich nicht, wenn sich die
  Attribution oder Zitation der Registry und damit `recipe.json` und `citation.bib`
  ändern; RFC 9110 §13.1.5), `Cache-Control: no-store`,
  `Content-Disposition: attachment; filename="…"` mit dem Namen der Einzellinks
  (`{dataset}_{operatoren}_{Tag}.zip`, Tag nach §3.1.7).
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
  and citation in one ZIP“, `application/zip`, ohne `length`: die Länge steht erst
  fest, wenn `recipe.json` und `citation.bib` gebaut sind, und kommt als
  `Content-Length` der Antwort), nur wenn `files_meta` beide Dateien nennt. Die Prozessbeschreibung nennt den Ausgang
  immer, und die frontend-Fixtures der Prozessbeschreibungen werden mit dem
  Skript neu geschrieben.

**Speicher und Bandbreite, gemessen im PR (§11):** je Download rund +3 MB bei 1 GB,
bei 4 gleichzeitigen +17 MB (der Block ist 1 MiB). Jedes Byte geht zweimal durch `api` (vom
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

#### 3.1.7 Das Datum im Dateinamen (Otto, 14.10.2026)

**Entscheidung.** Das Datum im Namen jedes Downloads eines Jobs (ZIP, `result.tif`,
`mask.tif`, `recipe.json`, `export.zip`) ist das **Aufnahmedatum der Szene**: der
UTC-Tag des Überflugs, aus dem Schlüssel nach `results_group_by`. Hat der Datensatz
kein einzelnes Aufnahmedatum (DEM), gilt der Tag des Laufs mit Präfix `run`:
`cop-dem-glo-30_reproject_run20261014.zip`.

**Was bisher galt.** `{dataset}_{operatoren}_{YYYYMMDD}` mit dem UTC-Tag, an dem der
Lauf endete (`finished_at`, sonst `created_at` des Jobs), ohne Präfix; festgelegt in
`plans/m4-08b-job-api.md` K6 (Einzellinks), für den Export in `plans/m4-11-export-job.md`
K6, ohne Datum der Szene; `adr/0015` §6.5 nennt nur „Datum“. Der Tag eines Laufs sagt
nichts über die Daten und wechselt bei einem Cache-Treffer (7 Tage später) nicht
mit dem Auftrag.

**Die Regel an zwei Stellen, je einer.**

| Frage | Stelle |
|---|---|
| Welchen Tag hat eine Szene? | `catalog.registry.acquisition_day(item, viewer)`: enthält `results_group_by` den STAC-Zeitpunkt `datetime`, ist dessen UTC-Tag der Tag der Szene (derselbe Schritt wie `group_key`, nur für diesen Teil des Schlüssels: fehlt der Item etwas anderes im Schlüssel, etwa den Datatake, hat er den Tag trotzdem). Sonst, bei fehlender Eigenschaft oder wenn sie kein Zeitpunkt ist: kein Tag, der Auftrag wird deswegen nicht abgewiesen |
| Welchen Tag hat ein Auftrag? | `api.intake._acquired_on`: alle Szenen, die im Rezept bleiben (die vom AOI nicht berührten fallen vorher weg), haben denselben Tag → er; sonst keiner |
| Was steht im Namen? | `api.processing_route._day_of_name(status)`: `YYYYMMDD` des Tages, sonst `run` + Tag des Laufs; `_download_name` benutzt nur sie, für alle Namen |

**Fälle.** Sentinel-2 (COG und Zarr): `results_group_by = (datetime, …)` → Tag des
Überflugs; ein Mosaik ganzer Szenen liegt nach `_one_overpass` ohnehin in einem
Überflug. DEM: `results_group_by = (start_datetime,)` → kein Tag (sein `datetime` ist
`null`, die Kachel gehört einem Zeitraum): `run…`. **Auslegung, Otto bitte
bestätigen:** Ein Export über Szenen verschiedener Tage hat keinen einzelnen Tag und
bekommt `run…` (Ottos Satz nennt nur den Fall „Datensatz ohne Aufnahmedatum“);
liegen alle Szenen eines Exports auf einem Tag, ist es dieser. Ebenso `run…` für Jobs
von vor dieser Änderung, bei denen der Tag fehlt.

**Wo der Tag liegt.** Spalte `earthx_job.acquired_on date` (Migration `009`), von
`api` bei der Annahme gesetzt und von `jobs` nur gespeichert und zurückgegeben
(`JobStatus.acquired_on`). Verworfen: im Rezept (jedes neue Feld wäre Teil von Hash
und `recipe.json`, `adr/0014` §4.3), aus der Quelle beim Abruf des Links (eine
Anfrage an die Quelle je Link, und der Link ginge nicht, wenn die Quelle nicht
antwortet), aus der Item-Kennung (dafür gibt es keine datensatzübergreifende Regel).
Je Job und nicht je Lauf: gleiche Aufträge teilen einen Lauf, aber jeder nennt seine
Szenen selbst.

**Folgen.** Die Namen laufender Links ändern sich (das Datum des Laufs wird zum Tag
der Szene bzw. zu `run…`); gespeichert ist kein Name, jeder Link baut ihn je Abruf
neu. Ein laufender Download behält den Namen seiner ersten Antwort, ein fortgesetzter
mit `If-Range` ist vom Namen nicht berührt. Im Namen stehen weiter nur Datensatz,
Operatoren und ein Tag, nie AOI, Hash oder `jobID`; der Tag einer Szene sagt, welche
Daten verarbeitet wurden, nicht wo.

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
| Route | `200`; `206` für `a-b`, `a-`, `-n`; `416`; mehrere Bereiche, falsche Syntax und vertauschte Bereiche → `200` ganz; `If-Range` mit eigenem ETag → `206`, mit fremdem oder mit dem Datum → `200`; `ETag` gleich bei jedem Abruf, anders bei einem anderen Ergebnis; `Content-Length` gleich der Summe der Bytes; die Bytes gleich `Layout`; `recipe.json` im ZIP gleich dem Einzellink |
| 410 (F2) | ab `expires_at − 60 s` `410` für den ganzen Abruf und für eine Range-Anfrage danach; ein Abruf kurz davor geht, derselbe eine Minute später nicht (Ablauf mit der Zeit des Tests) |
| Alte Ergebnisse (Otto, 14.10.) | Raster-Ergebnis ohne `files_meta`, mit zu wenig oder falsch geformtem `files_meta` → `409` mit Typ `urn:earthx:no-bundle` und dem Grund; die Einzellinks (`303`, `recipe.json`) und das Ergebnisdokument (ohne `bundle`) gehen weiter; `410` und `404` (nicht fertig) haben Vorrang; ein Export bleibt `404`; nichts wird geschrieben (die Zeile in der Queue bleibt, wie sie war) |
| Namen | Export, nicht fertig, gescheitert, unbekannt oder verworfen → die Antworten der Einzellinks (`404` bzw. Problem); der Ordner und der Dateiname tragen nie AOI, Hash oder `jobID` |
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
- **K5** Ergebnisse ohne `files_meta` (vor dieser Änderung) haben kein ZIP: der
  Link antwortet `409` mit Grund (Otto, 14.10.2026); das Panel zeigt dann die
  Einzellinks, weil das Ergebnisdokument `bundle` nicht nennt.
- **K6** Die Schätzung im Dialog wird beim Erscheinen des Angebots einmal
  abgefragt, nicht erst auf Knopfdruck.
- **K7** Der Export-Job des Dialogs erscheint auch in der Jobliste des Panels
  (ein Store, ein Tracker); im Dialog zeigt dieselbe `JobRow` den Status.
- **K8** Die Fehlertexte stehen im Frontend je `type` des Problems; das Backend
  ändert seine festen Titel nicht.
- **K9** `X-Export-Job: too-large` beim `413` über 5 GB (Faktor 1, COG); der
  Wert `available` bleibt, wie er ist. Erweitert M4-11 K5 um einen Wert.

---

## 9. Prüfanleitung für Otto (M4-11b-1, nach dem Merge, PowerShell 5.1)

Das Angebot im Dialog und „Download (ZIP)“ im Panel kommen mit M4-11b-2; bis dahin
geht der Raster-Job über die Job-Schnittstelle. Die Fläche wählst du selbst; die
Werte sind Platzhalter (etwa 0,1 × 0,1 Grad, eine Szene). Die Auftragsform ist
einmal gegen `parse_request` geprüft.

```powershell
docker compose up -d --build
docker compose ps        # api, tiler, worker, objectstore: healthy

$W, $S, $E, $N = 10.0, 49.0, 10.1, 49.1          # Platzhalter: eigene Fläche eintragen
$aoi = @{ type = 'Polygon'; coordinates = @(,@(@($W,$S), @($E,$S), @($E,$N), @($W,$N), @($W,$S))) }
$search = @{ collections = @('sentinel-2-c1-l2a'); intersects = $aoi
             datetime = '2025-07-01T00:00:00Z/2025-07-31T23:59:59Z'; limit = 10 } | ConvertTo-Json -Depth 10
$items = (Invoke-RestMethod -Method Post -Uri http://localhost:8000/stac/search `
          -ContentType application/json -Body $search).features
$item = $items[0].id

# 1) NDVI als Raster-Job
$order = @{ recipe_version = 1; aoi = $aoi
            inputs = @(@{ name = 'input'; dataset = 'sentinel-2-c1-l2a'; groups = @(,@($item)); assets = @('red', 'nir') })
            steps = @(@{ op = 'band_math'; op_version = 1; params = @{ expression = '(nir - red) / (nir + red)' } })
            output = @{ kind = 'raster'; format = 'cog'; dtype = 'float32' } }
$body = @{ inputs = @{ recipe = $order } } | ConvertTo-Json -Depth 12
$job = Invoke-RestMethod -Method Post -Uri http://localhost:8000/processing/processes/recipe/execution `
       -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
do { Start-Sleep 3; $st = Invoke-RestMethod "http://localhost:8000/processing/jobs/$($job.jobID)"; "$($st.status) $($st.progress)" } `
  while ($st.status -in 'accepted', 'running')

# 2) Das Ergebnisdokument nennt das ZIP, dann laden und auspacken
$base = "http://localhost:8000/processing/jobs/$($job.jobID)/results"
Invoke-RestMethod $base                          # result, mask, recipe und bundle
curl.exe -s -D headers.txt -o result.zip "$base/result.zip"
Get-Content headers.txt -TotalCount 12           # HTTP 200, Accept-Ranges: bytes, Content-Length, ETag, Last-Modified
(Get-Item result.zip).Length                     # gleich dem Content-Length
Expand-Archive result.zip -DestinationPath out -Force; Get-ChildItem out -Recurse

# 3) Fortsetzen: zwei Teile ergeben dieselbe Datei
curl.exe -s -D - -o part1.bin -r 0-1023 "$base/result.zip"     # HTTP 206, Content-Range: bytes 0-1023/...
curl.exe -s -o part2.bin -r 1024- "$base/result.zip"
cmd /c copy /b part1.bin+part2.bin joined.zip
Get-FileHash result.zip, joined.zip              # beide Hashwerte gleich

# 4) Die Einzellinks gibt es weiter
curl.exe -s -i "$base/result.tif" | Select-String "HTTP/", "Location"    # 303 auf die signierte URL
```

Zu sehen: im ZIP ein Ordner `sentinel-2-c1-l2a_band_math_JJJJMMTT` (der Tag der Szene, nicht von heute) mit
`result.tif`, `mask.tif`, `recipe.json` und `citation.bib`; die `.tif` in QGIS
wie die Einzeldateien; `recipe.json` gleich dem Einzellink
(`Invoke-RestMethod "$base/recipe.json"`); `Expand-Archive` von Windows läuft ohne
Fehler. Ein Download eines großen Ergebnisses, den du im Browser abbrichst, lässt
sich fortsetzen, sofern der Browser `Range` mit `If-Range` sendet (nicht
gemessen). Nach Ablauf der 7 Tage (oder mit einer Restlaufzeit unter 60 s) gibt
dieselbe Adresse `410`.

Für den Zuschnitt über 5 GB: ein Zuschnitt mit sehr vielen Assets und Szenen
antwortet `413` mit der Kopfzeile `X-Export-Job: too-large`, bis 5 GB mit
`available` (`curl.exe -s -i -X POST …/collections/sentinel-2-c1-l2a/download`, wie in
`plans/m4-11-export-job.md` §9).

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


---

## 11. Umsetzung M4-11b-1 (13.10.2026)

**Gebaut** wie §3.1. Commits: Plan und Antworten; Größe und Byte-Bereich im
Objektspeicher; `files_meta` im Aufseher; `result_zip.py`; Route und Ausgang
`bundle`; `X-Export-Job: too-large`; Doku.

**Gemessen (Sitzung, Loopback, Stand-in für den Speicher; nicht das Netz von
Produktion):**

- **CRC-32 und Größe beim Hochladen:** 0,47 s für 1,07 GB (drei Läufe 0,45 bis
  0,49 s, Datei im Seitencache); auf kalter Platte bestimmt deren Lesegeschwindigkeit
  die Zeit. Unter dem Herzschlag des Aufsehers, also ohne Folgen für die Lease.
- **Speicher von `api` je Download:** ein Download von 1,07 GB: Spitze von
  `api` +3 MB (`VmHWM` 189 → 192 MB); vier gleichzeitige: +17 MB (189 → 206 MB).
  Gemessen wird `_archive_bytes` mit dem echten botocore-Client gegen einen
  HTTP-Stand-in, der `HeadObject` und `GetObject` mit `Range` beantwortet
  (`mod_zip`-artig: Blöcke zu 1 MiB, ein Thread-Wechsel je Block). Das ist die
  Zahl für §3.1.5 („unter 10 MB“ war zu knapp geschätzt: vier gleichzeitige
  kosten rund 17 MB).
- **Bandbreite und CPU:** ein Download rund 1 000 MB/s bei 0,5 s CPU je GB
  (50 % eines Kerns); vier gleichzeitige zusammen rund 2 000 MB/s bei 128 % eines
  Kerns. Jedes Byte geht durch `api` (herein und hinaus); in Produktion begrenzt
  das Netz, nicht `api`. Der Lesepuffer ist der Block von 1 MiB.
- **ZIP64 gegen einen unabhängigen Leser:** ein echtes ZIP mit einem Eintrag von
  4,5 GB (Nullbytes), 4 500 003 487 Bytes, geschrieben aus `Layout`; Info-ZIP
  `unzip -t` (UnZip 6.00, Debian) meldet für alle drei Einträge „OK“ und „No errors
  detected“ [M]. Der CI-Test liest dieselbe Anordnung mit `zipfile` ohne Platte (§3.4).
  Gegenprobe: Ohne die ZIP64-Erweiterung im lokalen Kopf, ohne den Versatz im
  Zentralverzeichnis oder ohne die ZIP64-Endsätze scheitern jeweils zwei bis drei
  der fünf ZIP64-Tests.

**Befunde und Auslegungen:**

1. **Namenskonflikt `Literal`:** Das Segment „feste Bytes“ heißt in `result_zip.py`
   `Literal`; `processing_route.py` benutzt `typing.Literal`. Dort steht darum
   `result_zip.Literal`.
2. **Der Strom endet nicht von selbst.** Beim Abbruch des Clients lässt
   Starlette den Generator hängen, bis er eingesammelt wird: Der Lesestrom zum
   Speicher blieb offen. Die Gegenprobe im Test zeigte es; `_SlotResponse.__call__`
   schließt den Generator jetzt selbst (`aclose`) und gibt den Platz frei, auch
   bei Fehlern.
3. **Unter einem echten `uvicorn`** (Test mit `uvicorn.Server` in einem Thread,
   Speicher `moto`): `Content-Length` stimmt mit den gesendeten Bytes überein, es
   gibt kein `Transfer-Encoding`, ein Fortsetzen mit `Range` und `If-Range` ergibt
   das Ganze; endet der Speicher zu früh, sieht der Client einen Fehler
   (`RemoteProtocolError`), nie ein kürzeres, scheinbar fertiges ZIP.
4. **Kein `length` im Ergebnisdokument** für `bundle` (§3.1.5): die Länge steht
   erst nach dem Bau von `recipe.json` und `citation.bib` fest und kommt als
   `Content-Length` der Antwort.
5. **Der Pfad im Zugriffslog** ist die Vorlage (`/processing/jobs/{jobID}/results/result.zip`),
   nicht die Kennung (bestehende Eigenschaft von `RequestIdMiddleware`); der Test
   bestätigt es für die neue Route.
6. **Fixtures der Prozessbeschreibung:** Der neue Ausgang `bundle` steht in der
   Prozessbeschreibung; die drei Dateien unter `frontend/src/fixtures/processes/`
   sind mit dem Skript neu geschrieben (der Test `test_process_fixtures` verlangt es).
   Das ist die einzige Änderung unter `frontend/` in diesem PR.
7. **Unbekannter Datensatz:** Kennt die Registry den Datensatz eines Jobs nicht
   mehr, hat das ZIP kein `citation.bib` (und `recipe.json` keine Attribution, wie
   der Einzellink).
8. **Ungültige Bereiche:** Ein `Range`, das der Syntax nicht folgt, mehrere
   Bereiche, eine andere Einheit und ein Ende vor dem Anfang geben `200` ganz
   (RFC 9110 erlaubt es); ein Anfang hinter dem Ende oder `-0` gibt `416`.
9. **Platte des Aufsehers:** `files_meta` kostet einen weiteren Lesedurchgang,
   keine zusätzliche Platte. Die Formel der Plattenprüfung (M4-11a Punkt 12) bleibt.
10. **Offen für M4-11b-2:** Das Frontend liest `X-Export-Job` nur über die Antwort
    des Zuschnitts (same-origin, kein CORS); `too-large` ist ein dritter Wert neben
    `available` und „keine Kopfzeile“.
11. **Durchsicht vor dem PR** (Agent `reviewer`): keine blockierenden Befunde. Behoben:
    `If-Range` mit dem Datum des Laufs konnte nach einer Änderung der Registry (Attribution,
    Zitation) ein anderes Archiv fortsetzen; es zählt jetzt nur der `ETag` (Test geändert);
    das Format steht im `ETag` (`FORMAT`); `files_meta` wird über die Konstante gelesen;
    `416` und `500` stehen nur an der Route des ZIP in der API-Beschreibung; Grenztests
    für das ZIP64-Ende (Zentralverzeichnis bei `0xFFFFFFFE`/`0xFFFFFFFF`, 65 534/65 535
    Einträge); Zeilenangabe des Schreibers korrigiert. Nicht getestet bleibt eine
    Zentralverzeichnis-Größe von `0xFFFFFFFF` (bräuchte Millionen Einträge).
12. **Alte Ergebnisse (Frage von Otto vor dem Merge, 14.10.2026).** Der Link `result.zip`
    eines Raster-Ergebnisses ohne `files_meta` antwortete `404 "there is no such result"`,
    ohne Grund. Jetzt `409` mit Typ `urn:earthx:no-bundle` und dem Satz „this result was
    created before bundles existed; use the single links (result.tif, mask.tif,
    recipe.json)“ (§3.1.2, Begründung dort). Die Prüfung steht hinter `410` und `404`
    (nicht fertig, gescheitert), vor dem Namensvergleich; ein Export bleibt `404`.
    Getestet mit einem Ergebnis ohne `files_meta`, einem mit nur einer Datei, einem mit
    falsch geformten Zahlen und einem knapp vor dem Ablauf.
13. **Datum im Dateinamen (Otto, 14.10.2026, §3.1.7).** Der Tag im Namen ist jetzt der
    Tag der Szene, sonst `run` + Tag des Laufs. Neu: `catalog.registry.acquisition_day`,
    `api.intake._acquired_on`, `api.processing_route._day_of_name`, Migration `009`
    (`earthx_job.acquired_on`), `submit(…, acquired_on=)` und `JobStatus.acquired_on`.
    Getestet: die Regel je Item (UTC-Tag am Zeitzonenrand, Teil irgendwo im Schlüssel,
    fehlender Datatake, Zeitraum statt Zeitpunkt, fehlende Eigenschaft); die Annahme
    (eine Szene, Mosaik, Export an einem und an zwei Tagen, nicht berührte Szene, DEM,
    Item ohne Zeitpunkt); das Speichern und Zurückgeben im Queue; die Namen für alle
    vier Endungen und `run20261014`; Sentinel- und DEM-ZIP samt Ordner; Jobs von vor der
    Änderung. Die bestehenden Erwartungen mit dem Tag des Laufs sind auf den Tag der
    Szene (`20260601`) bzw. `run20260305` umgestellt.

---

## 12. M4-11b-2: Plan zu Zusatz §1a (Vorschlag 14.10.2026, beantwortet 15.10.2026)

**Aufgabe:** M4-11b-2 (§3.2 bis §3.4, freigegeben) mit dem Zusatz
`plans/m4-zusaetze-2026-10-12.md` §1a (Otto, 14.10.2026). Die Punkte aus §1a lagen
hier zuerst als Plan vor (Stufe B) und wurden nach Ottos Antwort (§12.7) gebaut.

### 12.1 Stand (gelesen am 14.10.2026, `main` = `cc584e1`)

- **Trefferansicht** (`components/ViewBar.tsx`, erscheint bei gewählten Szenen): ein
  Knopf „⇩ Download“. Was er tut, entscheidet `download.ts::decideDownloadOutcome`
  (M3-17 §4) aus AOI und Format: mit AOI immer `crop`, ohne AOI bei COG `originals`,
  ohne AOI bei Zarr gesperrt. Mit AOI gibt es also keine Originale.
- **Originale** (`DownloadDialog.tsx`, Fall `originals`): eine Liste von Links direkt
  zur Quelle (`<a href download>`), nach Gruppe (Überflug) geordnet, nur das
  Standard-Asset der Ansicht (`defaultRenderOf(...).assets[0]`), nur `https` auf
  Hosts der Registry (`earthx:source.asset_hosts`, D12). Kein CORS, kein Byte über
  die Plattform. Darunter `MosaicJobs.tsx` (M4-12b): je Überflug mit mindestens zwei
  Szenen ein Knopf „Merge scenes of this pass (job)“, Auftrag ohne `aoi`.
- **Layer-Manager** (`LayerManager.tsx`): ein Download-Knopf je Ebene; das Ergebnis
  folgt der Ansicht, aus der die Ebene stammt (`decideDownloadOutcomeForLayer`).
- **Grenzen:** eine Suchseite hat 100 Treffer (`store.ts::PAGE_LIMIT`), gewählt
  werden kann über mehrere Seiten; ein Auftrag nennt höchstens 25 Szenen
  (`api/intake.py::MAX_ORDER_ITEMS`); die Queue rechnet 4 Jobs gleichzeitig, 2 je
  Host (M4-08a), die übrigen warten.
- **Lizenz** (KLAERUNGEN B11): ein Link zur Quelle ist schon auf der Stufe
  „Katalogeintrag“ erlaubt; Zuschnitt und Mosaik brauchen die Stufe `processing`.

### 12.2 Vorschlag

**Trefferansicht.** „⇩ Download“ wird zu zwei Knöpfen:

| Knopf | gesperrt, wenn | Begründung im `title` |
|---|---|---|
| „Download crop“ | keine AOI | „Draw an AOI to download a crop“ |
| „Download originals“ | Datensatz nicht `earthx:format = cog` | „{Datensatz} has no single original file per scene (Zarr). Use Download crop.“ |

„Download crop“ öffnet den heutigen Dialog des Zuschnitts (mit dem Angebot „Export
as job“ aus §3.2). „Download originals“ öffnet den Dialog der Originale, unabhängig
davon, ob eine AOI gezeichnet ist. `decideDownloadOutcome` entscheidet in der
Trefferansicht nichts mehr; der Layer-Manager behält es (F7).

**Dialog „Download original files“.**

- **Eine Szene:** keine Wahl, die Links wie heute.
- **Mehrere Szenen:** oben die Frage „How do you want the original files?“ mit zwei
  Knöpfen; vorher wird nichts geladen und nichts gestartet:
  - „Each scene separately“ → die Liste der Links wie heute, nach Überflug geordnet.
  - „Merged per pass (job)“ → je Überflug eine Zeile: Überflüge mit mindestens zwei
    Szenen bekommen den Knopf „Start job“ (Auftrag wie M4-12b: ganze Szenen, kein
    `aoi`, keine Schritte), Überflüge mit einer Szene den Link auf ihre Datei (ein
    Mosaik aus einer Szene ist das Original, K11). Status über `JobRow` wie heute.
  - Ein Link „Change“ führt zur Frage zurück; gestartete Jobs bleiben im Panel.
- Die Wahl „Merged per pass (job)“ ist gesperrt, wenn die Lizenz kein Processing
  erlaubt (Grund wie heute in `MosaicJobs`); „Each scene separately“ bleibt dann
  möglich (B11).
- Der Abschnitt „Merged mosaic of a pass“ mit seinem eigenen Knopf entfällt; sein
  Inhalt (Hinweis auf UTM-Zonen, Zuschreibung veränderter Daten) steht unter
  „Merged per pass (job)“.

### 12.3 Originale: Einzellinks oder ZIP? (F5)

| | Einzellinks zur Quelle (heute) | ZIP über die Plattform | ZIP im Browser |
|---|---|---|---|
| Bandbreite der Plattform | keine | jedes Byte zweimal durch `api`/`gateway` (herein von der Quelle, hinaus zum Browser) | keine |
| Fortsetzen | der Browser setzt jeden Link selbst fort (Range an der Quelle) | nur mit Größe und CRC-32 vorab; die Quelle nennt keine CRC, also Datendeskriptoren (§3.1.1), ohne `Content-Length` und ohne Range; ein Abbruch beginnt von vorn | nein |
| Lizenz | Katalogeintrag reicht (B11) | die Plattform gibt Originaldaten weiter: braucht Weitergabe, also mindestens die Stufe „Anzeige“; eigener Entscheid | wie Einzellinks |
| Voraussetzungen | keine | neue Route, Grenze gleichzeitiger Downloads, Last für `gateway` (Grenzen je Host), Nachtrag zu `adr/0015` F4 | CORS an jeder Quelle (nicht in unserer Hand), bis zu mehreren GB im Speicher des Browsers |

**Empfehlung: Einzellinks wie heute.** Ein ZIP über die Plattform wäre ein eigener
Entscheid (Otto) mit eigenem Plan; der Nutzen (eine Datei statt mehrerer) wiegt
die Bandbreite und die fehlende Fortsetzung nicht auf. Für viele Szenen siehe F6.

### 12.4 Viele Szenen (F6)

- **„Each scene separately“:** Die Liste zeigt alle Links, nach Überflug geordnet,
  in einem Bereich mit eigener Bildlaufleiste. Dazu ein Knopf „Save link list“: eine
  Textdatei mit einer URL je Zeile, im Browser erzeugt (kein Byte über die
  Plattform), für einen Download-Manager oder `curl`/`wget`. Keine Obergrenze: Die
  Links kosten die Plattform nichts.
- **„Merged per pass (job)“:** je Überflug ein eigener Knopf, kein „Start all“. Ein
  Überflug mit mehr als 25 Szenen ist gesperrt mit Grund („A job takes at most 25
  scenes; select fewer scenes of this pass.“), statt erst den `400` des Servers zu
  zeigen. Wer zehn Überflüge startet, sieht zehn Zeilen; die Queue rechnet vier
  gleichzeitig, die übrigen zeigen „Waiting for a worker“.

### 12.5 Fragen an Otto

**F5 — Originale: Einzellinks oder ZIP?**
1. Einzellinks direkt zur Quelle wie heute **(Empfehlung)**
2. Ein ZIP, das `api` über `gateway` aus der Quelle streamt (ohne Fortsetzen; eigener
   Plan, Nachtrag `adr/0015`, Lizenzstufe mindestens „Anzeige“)
3. Ein ZIP, das der Browser baut (CORS an der Quelle, Speicher des Browsers)

**F6 — Viele Szenen**
1. Liste ohne Obergrenze mit eigener Bildlaufleiste und „Save link list“ (`.txt`);
   bei „Merged per pass“ je Überflug ein Knopf, über 25 Szenen gesperrt mit Grund
   **(Empfehlung)**
2. Wie 1, aber ohne „Save link list“
3. Wie 1, dazu „Start all“ für alle Überflüge auf einmal (höchstens 10 Jobs)

**F7 — Layer-Manager**
1. Bleibt wie heute: ein Knopf, das Ergebnis folgt der Ansicht der Ebene (M3-17);
   §1a nennt nur die Trefferansicht **(Empfehlung)**
2. Auch dort zwei Knöpfe „Download crop“ und „Download originals“

**F8 — Schnitt**
1. §1a im selben PR nach deiner Antwort, als eigene Commits; der PR wächst auf rund
   1 100 geänderte Zeilen mit Tests (über dem Richtwert von 400) **(Empfehlung:
   Dialog und Tests werden ohnehin zusammen umgebaut)**
2. Dieser PR nur §3.2 bis §3.4; §1a als M4-11b-3 in einer neuen Session nach dem
   Merge

**Kleinentscheidungen** (gelten, wenn Otto nicht widerspricht):

- **K10** Bei einer Szene fragt „Download originals“ nicht, sondern zeigt die Links; ebenso, wenn jeder Überflug nur eine Szene hat (Otto, 15.10.2026, §12.7).
- **K11** „Merged per pass (job)“: ein Überflug mit einer Szene bekommt den Link auf
  die Originaldatei statt eines Jobs.
- **K12** Die Frage hat keine Vorauswahl; erst ein Klick lädt Links oder bietet Jobs an.
- **K13** Gesperrte Knöpfe nennen den Grund im `title` (wie heute).
- **K14** „Merged per pass (job)“ ist nur gesperrt, wenn die Lizenz kein Processing
  erlaubt; „Each scene separately“ braucht nur den Link (B11).

### 12.6 Tests (nach Freigabe)

| Was | Test |
|---|---|
| Trefferansicht | zwei Knöpfe in allen Fällen; „Download crop“ ohne AOI gesperrt mit Grund; „Download originals“ bei Zarr gesperrt mit Grund, bei COG mit und ohne AOI offen |
| Dialog | eine Szene → Links ohne Frage; mehrere → Frage, nichts geladen; „Each scene separately“ → Links; „Merged per pass“ → Knopf je Überflug mit ≥ 2 Szenen, Link bei einer Szene, gesperrt über 25 Szenen; Auftrag ohne `aoi` auch mit gezeichneter AOI; Lizenz ohne Processing → nur „Each scene separately“; „Change“ zurück zur Frage |
| Linkliste | eine URL je Zeile, nur geprüfte Links (`isDirectDownloadHref`), keine AOI im Inhalt |
| Layer-Manager | unverändert (F7 Option 1) |

---

## 13. Umsetzung M4-11b-2, §3.2 bis §3.4 (14.10.2026)

**Gebaut** wie §3.2 und §3.3. Zusatz §1a (§12) ist **nicht** gebaut und wartet auf
Otto. Commits: Plan zu §1a; `HttpError` mit `type` und `exportJob`; Auftrag des
Exports und `aoiProvenance`; Angebot im Dialog; ein ZIP-Link und Texte im Panel;
Befunde der Durchsicht.

**Wo es steht:**

- `api.ts`: Alle Fehler gehen über eine Stelle (`httpErrorOf`). `HttpError` trägt
  jetzt `type` (der `type` des Problems) und `exportJob`. `downloadCrop` wirft
  `HttpError` und liest `X-Export-Job` nur bei einem `413`. Andere Werte als
  `available` und `too-large` gelten als „keine Kopfzeile“.
- `processingOrder.ts`: `buildExportOrder` (M4-11 §3.1, Faktor 1, AOI über
  `orderAoi`) und `aoiProvenanceOf` (die drei Felder einer Orts-AOI, nur Strings).
  `processing.ts`: `Order.output` ist Raster oder Zuschnitt;
  `placeJob(order, {aoiProvenance})`.
- `store.ts`: Ein `413` mit `exportJob` setzt bei Faktor 1 und einer Fläche
  `downloadExportOffer` statt der Fehlerzeile. Das Angebot entfällt beim Schließen,
  bei einem anderen Faktor und beim nächsten Versuch.
- `components/ExportJobOffer.tsx` (neu): der Text des `413`, die Schätzung (einmal,
  K6), die Sperre mit Grund, „Try again“, „Export as job“ und danach `JobRow`.
  `processingStore.placeOrder` (vorher `placeMosaic`) legt den Job in denselben
  Store und Tracker wie das Panel (K7).
- `processingStore.ts`: `resultFiles` wählt `export.zip` oder `result.zip` als
  einen Link „Download (ZIP)“, sonst die Einzellinks. `failureText` gibt Texte je
  Fehlerart (K8). Ein `410` von `/results` setzt `expired`.

**Befunde und Auslegungen:**

1. **Text bei Ablauf.** §3.3 nennt „Expired: results are kept for 7 days. Start the
   export again.“ Dieselbe `JobRow` zeigt auch Raster- und Mosaik-Jobs, deshalb
   steht dort „… Start the job again.“ (`JobList.tsx::EXPIRED_TEXT`). Eine
   Unterscheidung je Art des Jobs bräuchte die Art im Store, auch für Jobs, die aus
   `sessionStorage` zurückkommen. **Otto bitte bestätigen.**
2. **`disk_space`** zeigt weiter den Titel des Backends. Ein eigener Text gilt nur für
   `runtime_exceeded`. Zarr-`422` und andere Ablehnungen zeigen den `detail` des
   Backends.
3. **Jeder `413` der Schätzung** gilt als „über 5 GB“ und sperrt mit dem festen Satz.
   Der Server antwortet dort mit `413` nur bei der Größe des Exports und bei einem
   zu großen Body, den der Dialog nicht schicken kann.
4. **„Download“ bleibt im Dialog** neben dem Angebot. Bei Faktor 1 bekommt er wieder
   denselben `413`; mit einem gröberen Faktor kann der Zuschnitt direkt gehen. Ein
   anderer Faktor nimmt das Angebot weg, weil ein Export nur mit Faktor 1 läuft.
5. **Durchsicht** (Agent `reviewer`): keine Blocker. Behoben:
   - Zwei Angebote mit gleichem Text teilten den `key` der Komponente; jetzt hat
     jedes Angebot eine eigene `id`.
   - Eine Schätzung nach einem Abbruch wird verworfen.
   - Der Start prüft die Sperre selbst.
   - Nach einem `410` fehlt „Kept until …“.
   - Neue Tests: Schließen während der Schätzung, ein neues Angebot, Doppelklick.
6. **Umfang:** rund 320 Zeilen Code und 710 Zeilen Tests, ohne den Plan zu §1a.

**Prüfungen:** `npx tsc -b --pretty false`, `npm run lint` und `npx vitest run`
(947 Tests) sind grün. `pytest` (4 587 bestanden, 8 übersprungen), `ruff check
backend` und `lint-imports` (14 Verträge) sind ebenfalls grün. Das Backend ist
unverändert.

### 13.1 Prüfanleitung für Otto (M4-11b-2, nach dem Merge)

```powershell
docker compose up -d --build
cd frontend; npm run dev        # Viewer unter http://localhost:5173
```

1. **Angebot:**
   - Wähle `sentinel-2-c1-l2a`, zeichne eine große AOI (einige Zehntel Grad) und
     wähle zwei oder drei Szenen eines Überflugs.
   - Klicke auf „⇩ Download crop“ und dann im Dialog auf „Download“ (Native).
   - Erwartet: Statt „Download failed“ erscheint „Too large for a direct download“.
     Darunter stehen der Text des Servers und „About … GB · about … min“.
2. **Export starten:**
   - Klicke auf „Export as job“.
   - Erwartet: Die Zeile zeigt „Waiting for a worker“ bzw. „Running · n%“, dann
     „Finished“ mit einem Link „Download (ZIP)“.
   - Der Job steht auch im Processing-Panel unter „Jobs“ und bleibt dort, wenn du
     den Dialog schließt.
3. **ZIP:** Lade das ZIP und öffne es. Darin liegen je Überflug das Raster und die
   Maske, dazu `recipe.json`, `citation.bib`, `ATTRIBUTION.txt` und `aoi.geojson`.
4. **Ortssuche:** Wiederhole Schritt 1 und 2 mit einer AOI aus der Ortssuche.
   `aoi.geojson` im ZIP nennt dann OpenStreetMap als Quelle.
5. **Über 5 GB:** Wähle eine sehr große AOI mit vielen Szenen.
   - Erwartet: Das Angebot ist gesperrt mit „An export job may write at most 5 GB.
     Draw a smaller area or choose fewer assets.“
6. **Panel:** Starte einen NDVI-Job im Processing-Panel.
   - Erwartet: Fertig zeigt er nur „Download (ZIP)“, und das ZIP (`result.zip`)
     enthält einen Ordner mit `result.tif`, `mask.tif`, `recipe.json` und
     `citation.bib`.
   - Ein Ergebnis von vor M4-11b-1 zeigt weiter die Einzellinks.

### 12.7 Antworten (Otto, 15.10.2026)

- **F5:** Option 1, Einzellinks direkt zur Quelle. Ein ZIP der Originale über die
  Plattform ist **nicht** Teil dieser Aufgabe; im Log steht es als offen („Bandbreite
  und Weitergabe über die Plattform, nicht fortsetzbar“).
- **F6:** Option 1, Liste ohne Obergrenze mit „Save link list“ (Textdatei); „Merged
  per pass“ je Überflug ein Knopf, über 25 Szenen gesperrt mit Grund.
- **F7:** Option 1, der Layer-Manager bleibt unverändert (Umbau mit UI-01).
- **F8:** Option 1, §1a im selben PR.
- **§13.2 Punkt 4 (15.10.2026):** Die Frage nur, wenn mindestens ein Überflug zwei
  oder mehr Szenen hat; sonst gleich die Links.
- **K10 bis K14** angenommen. Der Ablauftext „Expired: results are kept for 7 days.
  Start the job again.“ (§13 Punkt 1) ist bestätigt.

### 13.2 Umsetzung Zusatz §1a (15.10.2026)

**Gebaut** wie §12.2 bis §12.4 mit den Antworten aus §12.7. Commits: Log der
Antworten; zwei Knöpfe in der Trefferansicht; Frage und Linkliste bei den Originalen;
Doku.

- `ViewBar.tsx`: „⇩ Download crop“ (ohne AOI gesperrt, `DRAW_AOI_TO_CROP`) und
  „⇩ Download originals“ (bei Zarr gesperrt, `noOriginalsReason`), immer beide.
  `store.openDownloadForSelection(kind)` nimmt, welcher gedrückt wurde; die
  Originale gehen auch mit gezeichneter AOI (Ganzszenen, die AOI spielt keine Rolle).
  `decideDownloadOutcome` entscheidet in der Trefferansicht nichts mehr, der
  Layer-Manager benutzt es unverändert (F7).
- `components/OriginalFiles.tsx` (neu): bei einer Szene die Links wie bisher; bei
  mehreren die Frage „How do you want the original files?“ ohne Vorauswahl (K12).
  „Each scene separately“ zeigt die Links nach Überflug in einem Bereich mit
  eigener Bildlaufleiste (`.dialog-original-links`) und „Save link list“
  (`linkListText`: eine Adresse je Zeile, nur die geprüften Links, im Browser
  erzeugt, Dateiname `{dataset}-original-links.txt`). „Change“ führt zur Frage
  zurück; gestartete Jobs bleiben in Sicht und im Panel.
- `components/MosaicJobs.tsx`: der Abschnitt „Merged mosaic of a pass“ mit seinem
  eigenen Knopf entfällt; „Merged per pass (job)“ zeigt je Überflug „Start job“
  (Auftrag wie M4-12b: ganze Szenen, kein `aoi`, keine Schritte), bei einer Szene
  den Link auf ihre Datei (K11), über 25 Szenen (`MAX_JOB_SCENES`, gleich
  `api/intake.py::MAX_ORDER_ITEMS`) gesperrt mit dem Grund. Ohne Lizenzstufe
  `processing` ist die Wahl „Merged per pass (job)“ gesperrt und nennt den Grund;
  „Each scene separately“ geht weiter (K14).

**Auslegungen:**

1. Die Frage erscheint auch im Dialog, der aus dem Layer-Manager kommt, wenn dessen
   Ergebnis die Originale sind: Es ist derselbe Dialog (der Knopf selbst bleibt
   unverändert, F7).
2. „Save link list“ erscheint ab zwei Links; bei einem einzelnen wäre die Datei nur
   ein Umweg.
3. `noOriginalsReason` nennt kein „(Zarr)“, weil alles außer `cog` (auch ein fehlender
   oder unbekannter `earthx:format`) keine Datei je Szene hat.
4. Die Frage kommt nur, wenn mindestens ein Überflug zwei oder mehr Szenen hat
   (Otto, 15.10.2026; §12.2 sagte „mehrere Szenen“). Besteht jede Gruppe aus einer
   Szene, zeigt der Dialog gleich die Links, auch bei mehreren Gruppen; „Save link
   list“ gibt es ab zwei Links.
5. Die Zuschreibung für unveränderte Daten steht oben im Dialog, die für veränderte
   Daten (Mosaik) zusätzlich unter „Merged per pass (job)“, wie bisher.

**Prüfungen:** `npx tsc -b --pretty false`, `npm run lint` und `npx vitest run`
(973 Tests, darunter Knöpfe, Frage, Linkliste mit fremdem Host, 25-Szenen-Grenze,
Lizenz, erneutes Öffnen, Start ohne `aoi` auch mit gezeichneter AOI) sind grün;
`pytest` (4 589 bestanden, 8 übersprungen), `ruff check backend` und `lint-imports`
(14 Verträge) ebenfalls. **Durchsicht** (Agent `reviewer`): keine Blocker; behoben
sind der Test zum fremden Host, der Fall eines einzelnen Links, das erneute Öffnen,
veraltete Kommentare, die Prüfung der Sperren im Start selbst und die Prüfanleitung.

### 13.3 Prüfanleitung für Otto: Zusatz §1a (nach dem Merge)

1. Wähle mehrere Szenen von `sentinel-2-c1-l2a` aus zwei Überflügen. Erwartet: In der
   Leiste stehen „⇩ Download crop“ und „⇩ Download originals“. Ohne AOI ist der
   Zuschnitt gesperrt (Hinweis beim Überfahren), mit AOI sind beide offen.
2. Bei einem Zarr-Datensatz ist „⇩ Download originals“ gesperrt und nennt den Grund.
3. „⇩ Download originals“ (mit und ohne AOI): Der Dialog fragt „How do you want the
   original files?“. „Each scene separately“ zeigt alle Links; „Save link list“
   speichert eine `.txt` mit einer Adresse je Zeile.
4. „Merged per pass (job)“: je Überflug mit mindestens zwei Szenen „Start job“, bei
   einer Szene deren Link. Der Job läuft ohne Zuschnitt, auch mit gezeichneter AOI.
5. Bei einer Auswahl, in der jeder Überflug nur eine Szene hat (auch eine einzelne
   Szene), fragt der Dialog nicht, sondern zeigt die Links.
