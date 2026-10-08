# M4-13 — Frontend: Processing-Panel, Kostenschätzung, Vorschau, Job-Status: Plan

**Aufgabe:** M4-13 aus `docs/plans/m4-processing-kern.md` §4.
**Stufe B** — **von Otto am 08.10.2026 freigegeben:** F1–F9 wie empfohlen
(je Option 1), K1–K12 angenommen. Umsetzung in drei PRs (F7): M4-13a (Backend,
§3.1, §3.2 und die Backend-Tests aus §3.8) in dieser Session, M4-13b (Panel,
Formular, Schätzung, Start, Job-Status, Download) und M4-13c (Vorschau,
„Preview“) je in einer neuen Session nach dem Merge des vorigen. Die
Statusanzeige aus M4-13b nutzt später M4-11b. Siehe §10.
**Ort im Repo:** `docs/plans/m4-13-processing-panel.md`
**Grundlagen:** `adr/0014` §5.3, §5.5, §5.6, §6.1–§6.3 (Auflage F9), §9,
§15c, §15d; `adr/0013` §5.4, §5.5; `plans/m4-processing-kern.md` §1.1 (Q8,
Q9, Q10), §1.2, M4-13; `plans/m4-08b-job-api.md` §3, §5 („Kostenschätzung als
eigene Route vor dem Auftrag: M4-13“); `plans/m4-09-band-math.md` §3.4, §4, §6
(„Das Panel baut die URL kanonisch“), §8 (F2: „resampled“ für M4-13
abrufbar); `projektuebersicht.md` §2 (Prinzipien 7, 9, 10); `KLAERUNGEN.md`
B10, B11. Code auf `main` nach PR #132: `api/processing_route.py`,
`api/processing_docs.py`, `api/intake.py`, `api/tiler.py`,
`processing/plan.py`, `catalog/collection.py`; Frontend `store.ts`, `api.ts`,
`mapLayers.ts`, `render.ts`, `components/`.

---

## 1. Ergebnis in drei Sätzen

Ein Panel baut aus dem Schema von `GET /processing/processes/recipe?dataset=…`
für die aktuelle Auswahl (Datensatz, eine Szene, AOI) eine Schrittfolge aus den
Operatoren, die dieser Datensatz erlaubt, zeigt vor dem Start eine
Kostenschätzung aus einer neuen Route und startet den Job über die
vorhandene Job-API. Solange die Schritte einen Anfang mit T1-Operatoren haben,
zeigt die Karte eine Vorschau über die Kachel-Route mit `op`/`op_version`/`params`
und kennzeichnet sie als „Preview“, sobald die Zoomstufe nicht die native Ebene
liest (Auflage F9). Der Status eines Jobs kommt per SSE, mit Rückfall auf
Abfragen; ist er fertig, bietet das Panel `result.tif`, `mask.tif` und
`recipe.json` zum Download und zeigt, ob das Ergebnis resampelt wurde.

---

## 2. Stand vor dieser Aufgabe (gelesen, 08.10.2026, `main` nach PR #132)

**Backend, vorhanden:**
- `GET /processing/processes/recipe?dataset=<id>` (`processing_docs.py`
  `process_description`) liefert den Auftrag als JSON Schema 2020-12: `steps`
  als `oneOf` mit `discriminator: op` über die Definitionen
  `step_<op>_v<version>`, nur Operatoren mit T2, die `applicable` für diesen
  Datensatz sind; `inputs[0].dataset` als `const`; `output` als
  `RasterOutput` (`kind`, `format`, `dtype`). Die Parameter sind heute flach:
  `band_math` v1 hat `expression` (Text, 1–256 Zeichen), `reproject` v2 hat
  `crs` (Text mit `pattern`), `resolution` (Zahl, `exclusiveMinimum: 0`),
  `resampling` (`enum`), `align` (bool mit `default`). Das ganze Dokument für
  Sentinel-2 hat 9,2 kB [M, Sitzung].
- **Lücke 1:** Das Schema sagt nicht, welche Schritte T1 können (`tiers`) und
  welche `kind` sie haben. Der Planer (`adr/0014` §6.1) braucht beides, um die
  Vorschau abzuschneiden.
- `POST /processing/processes/recipe/execution` mit `{"inputs": {"recipe": <Auftrag>}}`
  → `201`, `Location`, `statusInfo` mit `jobID`, `recipeID`, `expires`,
  `skippedItems`. `GET /jobs/{jobID}`, `DELETE /jobs/{jobID}`,
  `GET /jobs/{jobID}/events` (SSE, Ereignis `status` mit dem `statusInfo`,
  schließt nach dem Endstatus), `GET /jobs/{jobID}/results` (Links mit
  `properties` des Ergebnisses, darin `earthx:resampled`) und
  `GET /jobs/{jobID}/results/{name}` (`303` auf eine signierte URL, `410` nach
  Ablauf). Fehler sind `application/problem+json` mit `title` und `detail`.
- **Ein Item je Job:** `processing.check_scope` (`core.py` Z. 171) nimmt nur
  ein Item einer Gruppe einer Eingabe; mehr ist `422` („mosaics and several
  groups come with M4-11/M4-12“), auch über `execution`
  (`processing_route.py` Z. 498). Ein Überflug, dessen AOI zwei Kacheln
  berührt, geht also heute nicht als Job (F8).
- **Lücke 2:** Es gibt keine Route für die Schätzung vor dem Auftrag.
  `processing.plan.estimate(recipe, operators)` rechnet ohne Lesen aus AOI,
  `gsd` und Datentyp; `jobs/submit.py` nutzt es nur für den Laufzeitdeckel.
  Es braucht ein Rezept, also die Stufen 1–6 von `accept_order` (Items holen,
  Assets auflösen, Bänder lesen). Die Fassungen (Stufe 7, bei COGs ohne
  Prüfsumme ein `HEAD` je Asset) braucht die Schätzung nicht; im Code laufen
  sie aber **vor** dem Rezeptbau, `check_recipe_hosts` und `check_bands`
  (`intake.py` Z. 200, 221, 228, 230).
- Kachel-Route mit Operator (M4-09): `…/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=red&asset=nir&op=band_math&op_version=1&params=<JSON>`
  plus die üblichen `rescale`, `colormap_name`. `statistics`, `info`, `point`
  weisen `op` mit `400` ab. `tilejson.json` nennt die freigegebene Spanne aus
  `earthx:viewer`, nicht die native Ebene.
- **Lücke 3:** Für Zarr-Datensätze ist der Asset-Schlüssel einer Variablen
  `<asset><Trenner><variable>` (`SR_10m:b04`); den Trenner
  (`zarr.variable_separator`) gibt keine Schnittstelle heraus (F9). Das
  Frontend kennt ihn heute nur implizit aus `default_render.assets`.
- **Bandangaben im Item:** Der EOPF-Adapter legt die Bandnamen nach
  `eo:bands`, `raster:bands` trägt dann nur `nodata`, `data_type` und
  `spatial_resolution` (`adapters/eopf_stac.py` Z. 257–269). Die Zahl der
  Bänder eines COG steht in `raster:bands` bzw. `bands` (`intake.py`
  Z. 404–418). Der Frontend-Typ `StacAsset` kennt keines dieser Felder
  (`types.ts` Z. 8–22), nur `gsd`. `gsd` liest das Backend in der Reihenfolge
  Asset-`gsd`, `raster:bands[0].spatial_resolution`, `properties.gsd`
  (`access/download.py` Z. 409–424).
- Alle drei Registry-Einträge haben die Lizenzstufe *processing* und erlauben
  beide Operatoren (`catalog/datasets.py` Z. 109, 290, 488).

**Frontend, vorhanden** (React 19, zustand, MapLibre, vitest mit jsdom, keine
Testing Library; Komponententests mit `createRoot` und `act`):
- Auswahl: `datasetId`, `groups`, `activeGroupIndex`, `selectedIds`, `aoi`
  (`store.ts` Z. 539–680). `aoi` ist immer eine Fläche: Für einen Punkt hält
  der Store das gepufferte Quadrat, `aoiPoint` nennt die Herkunft
  (Z. 542–547). `downloadRequestForSelection(dataset, groups, aoi)`
  (`download.ts` Z. 210) baut `groups` und `aoi` für den Zuschnitt.
- Karte: `placeRaster` (`mapLayers.ts` Z. 176) legt Raster-Quellen an,
  `syncFocusRaster` (Z. 549) die Fokusansicht je Item; `mapZoom` und
  `viewportBbox` stehen im Store (`setMapViewport`, nur bei `moveend`).
- Darstellung: `ViewerControls` mit Stretch, Colormap und „Apply“ (F18);
  „Auto stretch“ ruft `/statistics` — mit `op` wäre das ein `400`.
- Lizenzstufe je Datensatz in `earthx:license_flags.tier` (`types.ts` Z. 137).
- `api.ts`: `jsonOrThrow` (nicht exportiert), `HttpError` mit `status`,
  `detail`, `retryAfter`, ohne `title`; kein `AbortController`. Kein Code zu `/processing`, `EventSource` oder `op=`.
- `vite.config.ts`: Proxy für `/stac`, `/coverage`, `/aoi`, `/geocode` (→ `api`)
  und `/collections` (→ `tiler`); `/processing` fehlt. Das Frontend läuft
  lokal über `npm run dev`; `docker-compose.yml` hat keinen Frontend-Dienst.

---

## 3. Umsetzung

### 3.1 Backend: Schätzroute (F2)

`POST /processing/processes/recipe/estimate`, Hülle und Grenzen wie
`execution` (`_read_body`, `_unwrap`: 1 MiB, nur JSON, keine Eingabe per
Referenz). Ablauf:
- `intake.py`: Die Stufen 1–6 (bis einschließlich `targets`) werden eine
  eigene Funktion `_targets`, die `_accept` unverändert aufruft; Reihenfolge,
  Abweisungen und Logs von `accept_order` bleiben gleich (bestehende Tests
  grün). Neu daneben `estimate_order`: `_targets`, Rezept mit
  `version: None` für jede Eingabe, ohne `recipe_id`, dann
  `check_recipe_hosts` und `check_bands` wie in `_accept`.
- Die Route ruft `estimate_order`, `check_scope` und `plan.estimate` und
  antwortet `200` mit `Cache-Control: no-store` (die Zahlen hängen an der AOI):
  `{"estimate": {"size", "duration", "outputPixels", "inputPixels",
  "inputBytes", "assets", "units"}, "skippedItems": [...]}`.
  `size` (Bytes der Ausgabe) und `duration` (ISO 8601, nur Sekunden,
  `PT12.3S`) heißen wie bei openEO (F2), die übrigen sind eigen.
- **Abweisungen:** dieselben Stufen und Codes wie `execution` bis Stufe 6
  und für `check_scope`. Was erst Stufe 7 findet (ein Asset, das beim `HEAD`
  fehlt, `404`/`410` → `422`; ein Fehler der Quelle → `502`), erkennt die
  Schätzung **nicht**; dann scheitert der Start trotz Schätzung, und das Panel
  zeigt den Fehler des Starts. Kein `HEAD`, keine Zeile in der Queue, kein
  `recipe_id`.
- Log: eine Zeile „order estimated“ mit Datensatz, Zahl der Items und Assets,
  Operatoren und den gerundeten Zahlen; nie AOI, Adresse, Hash (`adr/0014`
  §4.7).
- Die API-Beschreibung nennt die Route als Erweiterung außerhalb der OGC-Form
  („no conformance claimed“ gilt ohnehin, `adr/0014` §15d).

### 3.2 Backend: Angaben für das Panel (K1, F9, K3)

- **K1:** Jede Definition `step_<op>_v<n>` trägt zusätzlich
  `"x-earthx-tiers": ["T1", "T2"]` und `"x-earthx-kind": "pixel" | "grid"`.
  JSON Schema 2020-12 lässt unbekannte Schlüsselwörter als Anmerkung zu; die
  Prüfung in `parse_request` sieht sie nicht.
- **Trenner der Zarr-Variablen nach F9 (1):** Mit `?dataset=` trägt
  `InputRequest.assets` im Schema `"x-earthx-variable-separator": ":"`, wenn
  der Eintrag ein `zarr`-Feld hat; sonst fehlt der Schlüssel (B10: nichts
  geraten). Die Angabe gehört zum Auftrag, also in dessen Schema, nicht in
  die Collection.
- **K3:** Ein Backend-Test vergleicht `process_description` für jeden
  Registry-Eintrag mit einer Datei `frontend/src/fixtures/processes/<id>.json`;
  die Frontend-Tests bauen das Formular aus genau diesen Dateien. Ändert sich
  ein Parametermodell, fällt der Backend-Test, bis die Datei mit einem Skript
  (`scripts/write-process-fixtures.py`) neu geschrieben ist. So kann das Panel
  nicht still hinter dem Schema zurückbleiben.

### 3.3 Frontend: API-Client `processing.ts`

- `fetchProcess(datasetId)`, `estimateOrder(order)`, `placeJob(order)`,
  `fetchJob(jobId)`, `dismissJob(jobId)`, `fetchResults(jobId)`,
  `resultUrl(jobId, name)`. Alle über `jsonOrThrow` (dafür exportiert);
  `HttpError` bekommt `title` aus dem Problemdokument, `detail` liest
  `errorDetail` schon, `Retry-After` geht in `HttpError.retryAfter`.
- `AbortController` für Schätzung und Schema, damit ein Wechsel der Auswahl
  eine laufende Anfrage verwirft.
- Der Auftrag:
  `{recipe_version: 1, inputs: [{name: "input", dataset, groups, assets}], aoi, steps, output: {kind: "raster", format: "cog", dtype}}`.
- `vite.config.ts`: `/processing` → `apiTarget`.

### 3.4 Frontend: Formular aus dem Schema (F1)

Nach Empfehlung F1 (1) ein eigener, kleiner Formularbau
`schemaForm.ts` + `components/StepForm.tsx`:
- Unterstützt genau, was die Parameter heute brauchen: `string` (mit
  `minLength`, `maxLength`, `pattern`), `number`/`integer` (mit `minimum`,
  `maximum`, `exclusiveMinimum`, `exclusiveMaximum`), `boolean` (mit
  `default`), `enum` von Texten, `const`, `$ref` auf `#/$defs/…`,
  `title`/`description` als Beschriftung und Hilfetext, `required`.
- **Wächter:** Ein Parameterschema mit einem Schlüsselwort außerhalb dieser
  Liste (etwa `oneOf`, `array`, `object` mit Unterobjekten) gilt als „not
  supported by this panel“: Der Operator steht im Menü, ist aber deaktiviert
  und nennt den Grund. Der Test über die Fixtures aus K3 verlangt, dass jeder
  Operator jedes Datensatzes unterstützt ist.
- Prüfung im Browser nur als Hilfe (Pflichtfeld, Länge, Muster, Grenzen);
  verbindlich prüft der Server (`422` mit Text, wird am Schritt angezeigt).
  Kein `eval`, kein `new Function`; `pattern` wird mit `new RegExp(p, "u")`
  geprüft, ein Muster, das so nicht kompiliert, wird nicht geprüft (der Server
  prüft).
- Felder ohne `default` bleiben leer, auch `resampling` („No default: the
  choice changes the values“, B10).

### 3.5 Frontend: Panel `ProcessingPanel.tsx` und Store-Teil (K4, K7–K12)

- **Öffnen:** Knopf „Process“ in der `ViewBar` neben „Download“, für die
  aktuelle Auswahl. Deaktiviert mit Grund, wenn die Lizenzstufe nicht
  `processing` ist (B11), keine Fläche als AOI gezeichnet ist (ein Punkt reicht
  nicht) oder nichts ausgewählt ist. Das Panel ist ein `Draggable` wie die
  `ViewerControls`, mit den vorhandenen HUD-Klassen.
- **AOI:** wie beim Zuschnitt, also auch das gepufferte Quadrat eines Punkts
  (K11).
- **Ein Item (F8 (1)):** Der Auftrag nennt genau ein Item. Von den Items der
  aktiven Gruppe kommen die in Frage, deren Footprint die AOI schneidet. Ist
  es eines, wird es genommen; sind es mehrere, wählt der Nutzer eines aus, und
  das Panel sagt „The result covers only this scene; several scenes in one job
  come with a later version.“
- **Inhalt, von oben nach unten:**
  1. Auswahl in Worten: Datensatz, Datum, gewählte Szene (nie die AOI als
     Zahlen).
  2. **Bands:** Liste der Bandnamen, die die Auswahl bietet (K7), als Chips;
     ein Klick fügt den Namen in den Ausdruck ein. Die Assets des Auftrags sind
     die Bänder, die der Ausdruck nennt bzw. die der Nutzer ausgewählt hat
     (höchstens 16).
  3. **Steps:** geordnete Liste; „Add step“ mit den Operatoren aus dem
     Schema; je Schritt das Formular aus 3.4, „Remove“, „Up“/„Down“; höchstens
     `maxItems` (16).
  4. **Output:** `dtype` (K9).
  5. **Review:** holt die Schätzung (K4) und zeigt „about N MP, N MB,
     about N s, N units“ plus übersprungene Items; Text „An estimate, not a
     promise.“
  6. **Start job:** erst nach einer Schätzung für genau diesen Auftrag
     aktiv; jede Änderung am Auftrag verwirft die Schätzung.
  7. **Jobs:** je gestartetem Job eine Zeile mit Status, Fortschrittsbalken,
     „Cancel“ (`DELETE`), Ablaufzeit; fertig: Links „Result (COG)“, „Mask“,
     „Recipe“ und der Hinweis „Resampled to a common grid“, wenn
     `earthx:resampled` `true` ist (Prinzip 2.9; das Feld steht immer im
     Ergebnis, `core.py` Z. 290); gescheitert: `title` aus dem
     Problemdokument von `/results`.
- **Download (K6):** einfache Links auf
  `/processing/jobs/{jobID}/results/{name}`; der Browser folgt dem `303`. Ab
  `expires` minus 60 s (`MIN_REMAINING`) zeigt die Zeile „Expired“ statt der
  Links, weil ein Link einen `410` nur als JSON-Seite zeigen könnte.
- **Store:** ein Teil `processing` mit Schema je Datensatz, Entwurf der
  Schritte, Schätzung, Jobs; Aktionen `openProcessing`, `addStep`,
  `updateStep`, `moveStep`, `removeStep`, `reviewOrder`, `startJob`,
  `cancelJob`. Der Entwurf wird verworfen, wenn sich Datensatz oder AOI ändert.

### 3.6 Frontend: Job-Status (K5, F5)

`jobTracker.ts`:
- `EventSource` auf `/processing/jobs/{jobID}/events`, Ereignis `status`,
  Daten als `statusInfo` geprüft; eine unbekannte Form oder eine fremde
  `jobID` wird verworfen, nicht angezeigt. Beim Endstatus `close()`, sonst
  verbände sich `EventSource` von selbst neu.
- **Rückfall auf Abfragen:** Weist der Server die Verbindung ab (`404`, `503`
  bei zu vielen Verfolgern; beides vor dem Stream,
  `processing_route.py` Z. 673–684), gibt `EventSource` ohne Neuverbindung
  auf (`readyState === CLOSED`). Dann wechselt der Tracker **sofort** auf
  Abfragen. Bei einem Abbruch mitten im Stream verbindet `EventSource` selbst
  neu (`CONNECTING`); nach drei solchen Fehlern in Folge wechselt der Tracker
  ebenfalls. Ohne `EventSource` fragt er von Anfang an. Abfragen:
  `GET /jobs/{jobID}` alle 2 s, mit `Retry-After`, wenn der Server eines
  schickt. `404` heißt „gone“ (abgelaufen oder verworfen) und beendet das
  Verfolgen.
- Jobs werden nach F5 (1) in `sessionStorage` gehalten: nur `jobID` und
  `expires`, kein Auftrag, keine AOI (Q8). Nach dem Neuladen nimmt der Tracker
  sie wieder auf; abgelaufene fallen weg; ein Eintrag, der nicht die Form einer
  `jobID` hat, wird verworfen. Ist `sessionStorage` gesperrt (wirft), läuft
  das Panel ohne Wiederaufnahme weiter.

### 3.7 Frontend: Vorschau auf der Karte (F3, F4)

- **Planer** wie `adr/0014` §6.1: der längste Anfang der Schritte mit T1 in
  `x-earthx-tiers` und `x-earthx-kind = "pixel"`. Ist er leer, gibt es keine
  Vorschau des Ergebnisses (Hinweis „No preview: the first step runs only as a
  job“); die Karte zeigt weiter die Eingabe in der Fokusansicht, wie
  `adr/0014` §6.1 es beschreibt.
- In M4 ist der Anfang höchstens ein Schritt (`band_math`); mehrere T1-Schritte
  in einer Kachel nimmt die Kachel-Route heute nicht (ein `op` je URL). Hat der
  Anfang mehr als einen Schritt, zeigt die Vorschau nur den ersten und sagt es.
- **URL:** eine Raster-Quelle für das gewählte Item (F8), wie in der
  Fokusansicht, mit
  `asset` je Band, `op`, `op_version`, `params` als **kanonisches JSON**
  (Schlüssel sortiert, keine Leerzeichen; `plans/m4-09-band-math.md` §6), dazu
  `rescale` und `colormap_name` aus F3. Zuschnitt auf die AOI wie die
  Fokusansicht.
- **„Preview“-Kennzeichnung nach F4 (1):** sichtbar als Badge an der Karte und
  im Panel, solange die Bodenauflösung einer Kachel gröber ist als das feinste
  `gsd` der gewählten Assets, gerechnet an der Breite des Ausschnitts, die dem
  Äquator am nächsten liegt (dort ist die Kachel am gröbsten). Ohne `gsd`
  steht das Badge immer.
  - Bodenauflösung: `156543.03392 · cos(φ) / 2^z` m je Pixel (Web Mercator,
    256 px).
  - `z` ist die Stufe der **Kacheln**, nicht `mapZoom`: Die Quellen haben
    `tileSize: 256` (`mapLayers.ts` Z. 189), MapLibre lädt dann Kacheln der
    Stufe `round(mapZoom + 1)`, höchstens `max_zoom` aus `earthx:viewer`.
  - `gsd` je Asset in derselben Reihenfolge wie `asset_gsd` im Backend:
    Asset-`gsd`, `raster:bands[0].spatial_resolution`, `properties.gsd`.
  - Wie die Bandnamen (K7) ist das eine Anzeigehilfe im Frontend, kein
    Ergebnis; Prinzip 2.7 betrifft Ergebnisse, die nur das Panel liefern
    könnte (F2).
- „Auto stretch“ ist für die Vorschau deaktiviert (`/statistics` nimmt kein
  `op`), mit Grund im Tooltip.

### 3.8 Tests

Fixtures nur synthetisch; das Frontend erreicht kein Backend, `fetch` und
`EventSource` sind gestubbt.

**Backend** (`tests/earthx/api/test_processing_estimate.py`, Ergänzungen):
- Schätzung: gültiger Auftrag → `200` mit allen Feldern und `no-store`;
  dieselben Abweisungen wie `execution` bis Stufe 6 (falsche Hülle,
  Referenz-Eingabe, 413, 415, ein Auftrag mit `resolved` oder `recipe_id` →
  `400`, Ausgabe `crop` → `422`, unbekannter Datensatz, Lizenz unter
  *processing* → `403`, nicht anwendbarer Operator, Bandname, AOI außerhalb
  → `422`) und `check_scope` (zwei Items → `422`); **kein `HEAD`** über das
  Gateway (gezählt), **keine Zeile** in der Queue, kein `recipe_id` in der
  Antwort; kein Log mit AOI-Koordinaten oder Adresse (`own_log_text`).
- Grenze der Schätzung: Ein Asset, das erst beim `HEAD` fehlt, besteht die
  Schätzung und scheitert beim Start (Test belegt beides).
- `accept_order` nach dem Herauslösen von `_targets`: bestehende Tests
  unverändert grün.
- K1: jede Schritt-Definition trägt `x-earthx-tiers` und `x-earthx-kind`
  passend zum Operator; `parse_request` weist einen Schritt mit diesen
  Schlüsseln weiter ab (`additionalProperties`).
- F9: `x-earthx-variable-separator` für den Zarr-Eintrag, fehlt bei den
  COG-Einträgen und ohne `?dataset=`.
- K3: Fixture-Dateien gleich `process_description`; Gegenprobe im PR: ein
  geändertes Parametermodell lässt den Test fallen.

**Frontend** (vitest):
- `schemaForm`: jeder unterstützte Typ, Pflichtfelder, Grenzen,
  `exclusiveMinimum`, `pattern`, `enum`, `default`; ein Schema mit `oneOf`
  oder Unterobjekt → „not supported“; alle Fixtures aus K3 voll unterstützt.
- Auftrag: Hülle, ein Item und AOI aus der Auswahl; gepuffertes Quadrat eines
  Punkts wie beim Zuschnitt; mehrere Items, die die AOI schneiden → Auswahl
  einer Szene mit Hinweis (F8); mehr als 16 Assets oder Schritte → im Panel
  blockiert.
- Wechsel der Auswahl während einer Schätzung → die Anfrage wird abgebrochen
  (`AbortController`), ihre Antwort nicht angezeigt.
- Kanonisches JSON und Kachel-URL: Schlüsselreihenfolge, `&`, `#`, `+` und
  Nicht-ASCII im Ausdruck werden kodiert und landen nicht als eigener
  Parameter in der URL.
- Bandnamen (K7): COG mit einem Band je Asset, COG mit mehreren Bändern
  (`<asset>_1` …), Zarr mit Namen aus `eo:bands` und Trenner aus F9, Zarr ohne
  Trenner → keine Bandliste; Asset ohne Bandangaben → kein Chip.
- Preview-Regel: Kachelstufe aus `mapZoom` und `max_zoom`; Grenzfälle an
  Äquator und 60° N; `gsd` aus jeder der drei Quellen; ohne `gsd`; gemischte
  `gsd`.
- Tracker: Folge von `status`-Ereignissen bis `successful` → `close()`;
  Ereignis mit kaputtem JSON oder fremder `jobID` → verworfen; Abweisung vor
  dem Stream (`CLOSED`) → sofort Abfragen; drei Abbrüche (`CONNECTING`) →
  Abfragen; `Retry-After`; `404` → „gone“; keine `EventSource` → sofort
  Abfragen.
- `sessionStorage`: Wiederaufnahme, abgelaufene und falsch geformte Einträge
  verworfen; gesperrter Speicher → keine Wiederaufnahme, kein Fehler; kein
  Auftrag und keine AOI im Speicher.
- Download: Links bis `expires` − 60 s, danach „Expired“; `earthx:resampled`
  `false` → kein Hinweis.
- Panel (Komponente): Aufbau aus der Sentinel-2-Fixture; ein Operator, den
  eine synthetische Prozessbeschreibung nicht enthält, fehlt im Menü; „Start
  job“ erst nach „Review“; Änderung verwirft die Schätzung; `422`-Text am
  Schritt; erfolgreiche Schätzung, dann `502` beim Start → Fehler des Starts
  sichtbar; `503` mit Hinweis „try again“; Lizenzstufe *display*
  (synthetischer Datensatz) → Knopf deaktiviert mit Grund.

### 3.9 Doku und Log

- `ENTSCHEIDUNGSLOG.md`: Plan-Schritt (diese Zeile), später Freigabe und
  Umsetzung, je eine Zeile am Ende.
- `plans/m4-processing-kern.md` §3: Stand von M4-13.
- Prüfanleitung (§9) im PR.

---

## 4. Abnahme

| Punkt aus M4-13 | Beleg |
|---|---|
| Panel aus dem Schema, nur anwendbare Operatoren | Schema mit `?dataset=` (vorhanden, filtert nach `applicable`); Frontend-Test baut das Panel aus den Fixtures aus K3; mit einer synthetischen Prozessbeschreibung ohne `reproject` fehlt der Operator im Menü (alle drei echten Einträge erlauben beide) |
| Kostenschätzung vor dem Start | Route aus §3.1 mit Tests; „Start job“ erst nach „Review“ (Komponententest) |
| T1-Vorschau, „Preview“ auf Übersichtsstufen | Planer- und URL-Tests; Preview-Regel mit Grenzfällen; Prüfanleitung Schritt 4 |
| Job-Status per SSE mit Rückfall | Tracker-Tests (Ereignisse, Fehler, Abfragen, `404`) |
| Ergebnis-Download | Links aus `/results`; Prüfanleitung Schritt 6 |
| Oberflächentexte nur Englisch | Durchsicht im PR |

---

## 5. Nicht in dieser Aufgabe

- Automatische Skalierung und Einheiten, Methodentext, Permalinks,
  „Parameter übernehmen“: M4-19.
- Abbildung von `default_render.expression` auf `op` (F6).
- Statistik, Info und Punktabfrage mit `op` im `tiler`.
- Anzeige eines **Job-Ergebnisses** auf der Karte (`plans/m4-08b-job-api.md`
  §5: nicht in M4a).
- Mehrere Eingaben je Auftrag, Mosaik als Job (M4-11, M4-12).
- Job-Liste über Sitzungen hinweg (ohne Konten keine, Q9).
- `.github/`, `.importlinter`, `processing`, `jobs`, `gateway`, `objectstore`.

---

## 6. Umfang und Commits

Geschätzt [A]: Backend rund 150 Zeilen Code (Teilung von `accept_order` 40,
Route 60, K1/F9 20, Fixture-Skript 30) und 250 Zeilen Tests; Frontend rund
950 Zeilen Code (`processing.ts` 120, `schemaForm.ts` 160, `StepForm.tsx`
120, `ProcessingPanel.tsx` 260, `jobTracker.ts` 130, Store 120, Vorschau und
Bandnamen 100, CSS 40) und 800 Zeilen Tests. Zusammen weit über dem Richtwert
von 400 Zeilen; Schnitt nach F7.

Commits, je ein Thema (bei F7 (1) verteilt auf drei PRs):
1. `api`: `prepare_order` aus `accept_order`, ohne Verhaltensänderung
2. `api`: Route `…/estimate`
3. `api`: `x-earthx-tiers`/`x-earthx-kind`, `x-earthx-variable-separator`
4. Fixtures der Prozessbeschreibung und Gleichheitstest (K3)
5. `frontend`: Client `processing.ts`, Proxy
6. `frontend`: Formular aus dem Schema
7. `frontend`: Panel, Store, Schätzung, Start
8. `frontend`: Job-Status mit SSE und Rückfall, Download
9. `frontend`: Vorschau und „Preview“
10. Doku und Log

Vor dem Fertigmelden: `main` holen; `ruff check backend`, `pytest`,
`PYTHONPATH=backend lint-imports --config .importlinter`; im Frontend
`npm run lint`, `npx tsc -b --pretty false`, `npm test`.

---

## 7. Risiken

- **Schätzung kostet Abrufe:** Jede Schätzung holt die Items über die
  Item-Quelle (das Panel schickt eines, die Route nimmt wie `execution` bis
  25). Deshalb nur auf „Review“, nicht bei jeder Eingabe (K4). Ein Missbrauch
  bleibt bis M6 (Quotas) offen wie bei `execution`.
- **Schätzung ohne Stufe 7:** Sie sagt nicht zu, dass der Start gelingt
  (§3.1); das Panel sagt „An estimate, not a promise.“
- **Kachel-Cache:** Nur kanonisch gebaute `params` treffen denselben
  Cache-Eintrag; ein anderer Client mit anderer Schreibweise verfehlt ihn, nie
  mit falschem Bild (`plans/m4-09-band-math.md` §6).
- **Preview-Regel ist vorsichtig:** Sie kennzeichnet auch Zoomstufen, die
  schon die native Ebene lesen (zwischen `gsd` und der ersten Übersicht, bei
  Sentinel-2 10 m etwa z13 auf 48° N), als „Preview“. Das ist ehrlich im Sinn
  von Prinzip 2.9; genauer ginge es nur mit Wissen über die Übersichten der
  Datei (F4 (2)).
- **Signierte URL im Browser:** Der Download folgt dem `303` auf den
  öffentlichen Endpunkt des Objektspeichers; lokal muss der Endpunkt aus der
  Konfiguration vom Browser erreichbar sein (Prüfanleitung).
- **`EventSource` und Proxy:** Ein Proxy, der Antworten puffert, hält die
  Ereignisse zurück; der Vite-Proxy puffert `text/event-stream` nicht [A].
  Der Rückfall auf Abfragen fängt es ab, wenn nicht.

---

## 8. Fragen an Otto

**F1 — Formular aus dem Schema: eigener Bau oder Bibliothek (§3.4)**

Befunde (Abruf 08.10.2026; gzip-Größen nicht ermittelbar, weil
Bundlephobia & Co. aus der Sitzung gesperrt sind — entpackte npm-Größen):

| | react-jsonschema-form (`@rjsf/core` 6.11.0) | JSON Forms (`@jsonforms/*` 3.8.0) | eigener Bau |
|---|---|---|---|
| letztes Release | 29.09.2026 [P] | 16.06.2026, rund 3 Releases in 12 Monaten [P] | — |
| Lizenz | Apache-2.0 [P] | MIT [P] | AGPL wie das Repo |
| React 19 | Peer `react >=18` [P] | ausdrücklich seit 3.5.0 [P] | ja |
| JSON Schema 2020-12 | nur mit `ajv/dist/2020`; Doku: „draft-2020-12 has breaking changes and hasn't been fully tested“ [P] | Maintainer: „advanced 2020-12 features“ nicht unterstützt (Issue #2567) [P] | genau die Schlüsselwörter aus §3.4 |
| `oneOf` + `discriminator` | belegt (`getDiscriminatorFieldFromSchema`) [P] | nichts gefunden | trivial: `op` ist je Variante ein `const` |
| entpackt | core 2,5 MB + utils 2,8 MB + Validator 0,3 MB [P] | core 1,2 + react 0,3 + vanilla 0,6 MB [P] | — |
| transitive Abhängigkeiten | rund 12, darunter ajv [A] | rund 9, darunter ajv und lodash [A] | 0 |
| ohne `new Function` (CSP ohne `unsafe-eval`) | nur mit vorkompilierten Validatoren (Schema zur Build-Zeit) oder `validator-cfworker`, der kein `discriminator` kann [P] | nein; Issue #1498 seit 2019 offen, Entkopplung von ajv erst für 4.0 geplant [P] | ja |

Quellen: npm-Registry (`@rjsf/core`, `@rjsf/utils`, `@jsonforms/core`,
`@jsonforms/react`, `@jsonforms/vanilla-renderers`, `ajv`); rjsf
`packages/docs/docs/usage/validation.md`,
`…/api-reference/utility-functions.md`, `…/validator-cfworker.md`, Release
6.8.0; ajv `docs/security.md` („unsafe-eval“); JSON Forms Issues #1498,
#2043, #2567, PR #2644. uniforms 4.0.0 hat Peer `react ^16.8 || ^17 || ^18`
und fällt aus [P].

1. Eigener kleiner Formularbau für flache Parameter (§3.4), mit Wächter für
   alles andere; keine neue Abhängigkeit, kein `eval`, volles HUD-Styling.
   Umdenken, sobald ein Operator verschachtelte Objekte, Listen oder
   bedingte Felder braucht; dann wäre rjsf der erste Kandidat
   **(Empfehlung)**
2. `@rjsf/core` mit `validator-ajv8` und `ajv/dist/2020`; eigene Widgets für
   das HUD; braucht `unsafe-eval` oder vorkompilierte Validatoren und eine
   Lock-Datei-Änderung im Frontend
3. JSON Forms mit Vanilla-Renderern; ajv mit `new Function` lässt sich nicht
   abschalten, `discriminator` unbelegt

**F2 — Kostenschätzung vor dem Auftrag (§3.1)**

Befunde (Abruf 08.10.2026):
- openEO API 1.2.0: `GET /jobs/{job_id}/estimate` auf einem schon angelegten
  Job; Antwort `costs`, `duration` (ISO 8601), `size` (Bytes),
  `downloads_included`, `expires`; „The estimate SHOULD be the upper limit of
  the costs“. Angelegt wird mit `POST /jobs` (Status `created`), gestartet mit
  `POST /jobs/{job_id}/results` [P] (`openeo-api`, Tag 1.2.0,
  `openapi.yaml`).
- OGC API – Processes Part 1 Core 1.0 kennt keine Schätzung [S]. Part 4 „Job
  Management“ (Entwurf 24-051) legt Jobs mit `POST /jobs` im Status
  `created` an und startet sie mit `POST /jobs/{jobID}/results`, ohne
  Schätzung [P] (`ogcapi-processes`, `extensions/job_management`,
  `clause_6_job_management.adoc`, `statusCode.yaml`). Die Erweiterung
  „quotation“ ist dort nur ein Platzhalter ohne Inhalt [P].
- Prinzip 2.7 (API-first): Was das Panel zeigt, muss auch die API liefern.

1. Eigene Route `POST /processing/processes/recipe/estimate` mit derselben
   Hülle wie `execution`; Stufen 1–6 der Annahme, kein `HEAD`, keine Zeile in
   der Queue. Wo die Bedeutung gleich ist, heißen die Felder wie bei openEO
   (`size` in Bytes, `duration` als ISO 8601), dazu die eigenen
   (`outputPixels`, `units`, …). Ein späterer Wechsel zu Option 3 behält
   damit die Antwort; er braucht aber den neuen Zustand `created` in der
   Queue **(Empfehlung)**
2. Schätzung im Frontend aus AOI, `gsd`, Datentyp und Faktoren, die das
   Schema mitliefert. Verdoppelt `plan.estimate` und verstößt gegen
   Prinzip 2.7
3. Ablauf nach openEO bzw. OGC Part 4: Job anlegen (`created`), schätzen,
   starten. Braucht einen neuen Zustand in der Queue (`jobs`, Migration) und
   ändert die Job-API aus M4-08b; nicht in M4

**F3 — Darstellung der Vorschau (§3.7)**
1. Wertebereich und Colormap im Panel von Hand, mit „Apply“ wie in den
   `ViewerControls`; Startwerte −1 bis 1 und `rdylgn`, sichtbar und
   änderbar; die automatische Skalierung kommt mit M4-19 **(Empfehlung)**
2. `/statistics` im `tiler` nimmt `op` (Backend-Änderung im Kachel-Pfad) und
   „Auto stretch“ misst den Bereich wie heute (F18)
3. Wie 1, aber ohne Startwerte: Die Vorschau erscheint erst, wenn ein Bereich
   eingetragen ist

**F4 — Wann „Preview“ steht (§3.7, Auflage F9)**
1. Vorsichtige Regel im Frontend aus `gsd` und Zoomstufe: „Preview“, solange
   eine Kachel gröber ist als das feinste `gsd`; ohne `gsd` immer
   **(Empfehlung)**
2. Der `tiler` meldet je Datensatz bzw. Asset die Zoomstufe, ab der die native
   Ebene gelesen wird (etwa in `tilejson.json`); genauer, aber eine Änderung
   im Kachel-Pfad und abhängig von den Übersichten jeder Datei
3. Die Vorschau heißt immer „Preview“

**F5 — Jobs nach dem Neuladen (§3.6)**
1. `sessionStorage`: nur `jobID` und Ablaufzeit, je Tab, bis zum Ablauf
   **(Empfehlung)**
2. Nur im Speicher; nach dem Neuladen ist der Job aus dem Panel verschwunden
3. `localStorage`: über Tabs und Neustarts des Browsers hinweg; die `jobID`
   ist der Schlüssel zum Ergebnis (Q9) und läge dann länger im Browser

**F6 — `default_render.expression` auf `op` abbilden
(`plans/m4-09-band-math.md` §3.4)**
1. Nicht in M4-13: Kein Eintrag braucht es, die Registry weist
   `expression` weiter ab; eine offene Zeile im Log **(Empfehlung)**
2. In M4-13: `DefaultRender` bekommt `op`, `op_version`, `params` (neue
   Registry-Felder ohne Vorgabe, B10) und die Standardansicht nutzt sie

**F7 — Schnitt (§6)**
1. Drei PRs: **M4-13a** Backend (Schätzroute, K1, F9, K3) in dieser Session
   auf diesem Branch; **M4-13b** Panel, Schätzung, Start, Job-Status,
   Download; **M4-13c** Vorschau und „Preview“; b und c je eine eigene
   Session nach diesem Plan, c nach b **(Empfehlung)**
2. Ein PR über dem Richtwert (rund 1100 Zeilen Code, 1050 Tests)
3. Zwei PRs: Backend mit Panel ohne Vorschau, dann Vorschau

**F8 — Ein Item je Job (§2, §3.5; `core.py` Z. 171)**

Der Kern rechnet heute genau ein Item; ein Überflug, dessen AOI zwei Kacheln
berührt, ist als Job ein `422`. Mosaik ganzer Szenen kommt mit M4-12.
1. Das Panel nimmt das eine Item der aktiven Gruppe, das die AOI schneidet;
   sind es mehrere, wählt der Nutzer eines, und das Panel sagt, dass das
   Ergebnis nur diese Szene abdeckt **(Empfehlung)**
2. Das Panel sperrt „Start job“, solange mehr als ein Item die AOI schneidet,
   mit dem Hinweis, die Fläche zu verkleinern
3. M4-13b wartet auf M4-12; dann schickt das Panel die ganze Gruppe

**F9 — Woher das Panel den Trenner der Zarr-Variablen kennt (§3.2)**

Für Zarr ist der Asset-Schlüssel einer Variablen `<asset><Trenner><variable>`;
der Trenner steht nur in der Registry.
1. Im Schema des Auftrags mit `?dataset=`:
   `InputRequest.assets` trägt `x-earthx-variable-separator`. Die Angabe
   gehört zum Auftrag; keine neue Collection-Eigenschaft **(Empfehlung)**
2. Neues Feld `earthx:zarr.variable_separator` in der Collection; das ist
   eine Erweiterung der `earthx:`-Felder aus `architekturplan.md` 5.1, mit
   Nachtrag dort und Log-Zeile
3. Das Frontend liest ihn aus `default_render.assets`; bricht, sobald eine
   Standardansicht keine Variable nennt

**Kleinentscheidungen K1–K12** (gelten mit der Freigabe, wenn Otto nichts
sagt):
- **K1:** `x-earthx-tiers` und `x-earthx-kind` je Schritt-Definition im
  Schema (§3.2).
- **K2:** entfällt (jetzt F9).
- **K3:** Fixtures der Prozessbeschreibung im Frontend, Gleichheitstest im
  Backend, Skript zum Neuschreiben (§3.2).
- **K4:** Schätzung nur auf „Review“, nicht bei jeder Eingabe; „Start job“
  erst nach einer Schätzung für genau diesen Auftrag (§3.5).
- **K5:** SSE mit `close()` beim Endstatus; Rückfall auf Abfragen alle 2 s,
  sofort bei einer Abweisung vor dem Stream (`readyState === CLOSED`), nach
  drei Abbrüchen in Folge oder ohne `EventSource`; `Retry-After` gilt
  (§3.6).
- **K6:** Download als Links auf `/processing/jobs/{jobID}/results/{name}`;
  der Browser folgt dem `303`. Ab `expires` − 60 s „Expired“ statt Links.
- **K7:** Bandnamen im Frontend nach derselben Regel wie
  `processing.source.expected_band_names`: COG mit einem Band → Asset-Schlüssel,
  mit mehreren → `<asset>_1`, `<asset>_2` …; die Zahl der Bänder aus
  `raster:bands` bzw. `bands`. Zarr → Namen aus `eo:bands[].name` (so legt
  der EOPF-Adapter sie ab), je Band ein Asset `<asset><Trenner><variable>`.
  Chips nur für Assets, die Bänder beschreiben; das ist eine Anzeigehilfe,
  verbindlich prüft der Server. `StacAsset` bekommt dafür die drei Felder.
- **K8:** Proxy `/processing` → `api` in `vite.config.ts`.
- **K9:** `dtype` startet mit `float32`, wenn ein `band_math`-Schritt dabei
  ist, sonst mit dem Datentyp des ersten Bandes; änderbar.
- **K10:** Eingabename im Auftrag fest `input`.
- **K11:** AOI wie beim Zuschnitt, also auch das gepufferte Quadrat eines
  Punkts.
- **K12:** Der Knopf „Process“ sitzt in der `ViewBar`; das Panel ist ein
  `Draggable`.

---

## 9. Prüfanleitung für Otto (nach dem Merge, PowerShell)

```powershell
docker compose up -d --build
cd frontend
npm ci
npm run dev
```

Im Browser `http://localhost:5173`:
1. Datensatz `sentinel-2-c1-l2a`, eine kleine Fläche zeichnen, die ganz in
   einer Szene liegt, und einen Überflug mit wenig Wolken auswählen.
2. „Process“ → „Add step“ → „Band math“; Bänder `nir` und `red` anklicken,
   Ausdruck `(nir - red) / (nir + red)`.
3. Die Karte zeigt die Vorschau (−1 bis 1, `rdylgn`) mit dem Badge
   „Preview“.
4. Hineinzoomen, bis das Badge verschwindet (bei 10 m auf 48° N ab
   Kachelstufe 14, also Kartenzoom etwa 12,5); die Vorschau liest dort die
   native Ebene.
5. „Review“ zeigt Größe, Dauer und Einheiten; „Start job“; die Zeile zeigt
   `accepted`, `running` mit Fortschritt, dann `successful`.
6. „Result (COG)“ lädt eine `.tif`, „Recipe“ eine `_recipe.json`; die Datei
   öffnet sich in QGIS mit Werten zwischen −1 und 1.
7. Gegenprobe ohne Vorschau: Datensatz `cop-dem-glo-30`, ein Schritt
   „Reproject“ (z. B. `EPSG:3035`, 30, `bilinear`): Die Karte zeigt keine
   Vorschau, das Panel sagt „No preview: the first step runs only as a job“;
   der Job läuft trotzdem.
8. Gegenprobe mehrere Szenen: eine Fläche über einer Kachelgrenze zeichnen;
   das Panel lässt eine Szene wählen und sagt, dass das Ergebnis nur diese
   abdeckt (F8 (1)).

Die Gegenprobe zur Lizenzstufe gibt es nur als Frontend-Test: Alle drei
Einträge haben die Stufe *processing*.

---

## 10. Freigabe (Otto, 08.10.2026) und Umsetzung

**Freigabe:** F1–F9 je Option 1 (Empfehlung), K1–K12 angenommen. Oberflächentexte
nur Englisch.

**Schnitt (F7):** Die Teilaufgaben stehen als M4-13a bis M4-13c in
`plans/m4-processing-kern.md` §3. M4-11b hängt an M4-13b.

**M4-13a — Umsetzung:** siehe unten, nach dem Fertigmelden ergänzt.
