# M4-13c — Vorschau, „Preview“ und Processing im Viewer: Plan

**Aufgabe:** M4-13c aus `docs/plans/m4-processing-kern.md` §3 (Plan des Ganzen:
`plans/m4-13-processing-panel.md` §3.7, F3, F4) mit dem Zusatz
`plans/m4-zusaetze-2026-10-12.md` §2 (Punkte 1–7).
**Stufe B:** Plan im Draft-PR #152, **freigegeben von Otto am 15.10.2026** (§10).
**Stand:** 14.10.2026, `main` nach PR #148 (M4-12b und M4-11b-1 gemergt).
**Ort im Repo:** `docs/plans/m4-13c-vorschau-und-viewer.md`

Aus dem ursprünglichen Plan gelten unverändert (Freigabe 08.10.2026): Planer nach
`adr/0014` §6.1, kanonisches JSON in der Kachel-URL, F3 (1) Wertebereich und
Colormap von Hand mit Startwerten −1 bis 1 und `rdylgn`, F4 (1) vorsichtige
„Preview“-Regel aus `gsd` und Kachelstufe, „Auto stretch“ für die Vorschau
gesperrt. Neu zu entscheiden ist, was der Zusatz §2 dazulegt.

---

## 1. Ergebnis in drei Sätzen

Das Zusammenstellen eines Auftrags bekommt eine breite Seitenleiste am rechten
Rand, die Jobliste bleibt ein kleines Fenster; der Auftrag gilt wahlweise für die
ganzen Szenen (Vorgabe) oder nur die AOI, und dieselben Schritte lassen sich als
Batch je Szene oder je Überflug starten. Band-Math erscheint sofort als
T1-Vorschau auf der Karte, mit „Preview“, solange die Kachel gröber als die Daten
ist, und lässt sich wie ein fertiges Job-Ergebnis als Layer anheften oder an die
Stelle des Quell-Layers setzen; Job-Ergebnisse liest dafür der `tiler` über
`objectstore`. Die Zielauflösung von Reproject zeigt die Einheit des Ziel-CRS aus
einer kleinen Route mit `pyproj` und bei Grad die Größe am Boden.

---

## 2. Stand vor dieser Aufgabe (gelesen am 14.10.2026)

**Frontend:**
- `ProcessingPanel.tsx` (350 Zeilen) ist ein `Draggable` von 360 px Breite
  (`index.css` `.processing-panel`), oben rechts unter den Kartenknöpfen; die
  Jobliste (`JobList.tsx`) hängt unten im selben Fenster. „⚙ Jobs (n)“ oben
  rechts öffnet das Panel, wenn es zu ist (`App.tsx`).
- `processingStore.ts::orderView`: Kandidaten sind die gewählten Szenen, deren
  Footprint die AOI schneidet (`candidateItems`); `passesOf` teilt sie in
  Überflüge; mehrere Überflüge → Wahl eines „Pass“. `buildOrder` verlangt immer
  eine Fläche als AOI und schickt sie (`processingOrder.ts`).
  `processBlockReason` sperrt „⚙ Process“ ohne Fläche.
- Ein Wechsel von Datensatz **oder AOI** verwirft den ganzen Entwurf
  (Schritte eingeschlossen; `useAppStore.subscribe` am Ende von
  `processingStore.ts`).
- **Bänder aus dem Ausdruck (Zusatz Punkt 5):** `orderAssets` nimmt jedes Band,
  das ein Band-Math-Ausdruck nennt und genau einem Asset gehört, in den Auftrag,
  ohne Klick auf einen Chip. Belegt in `processingOrder.test.ts` Z. 158–163 und
  indirekt im Komponententest „Start job waits for an estimate“
  (`ProcessingPanel.test.tsx` Z. 351 ff.: Ausdruck getippt, gesendet
  `assets: ['red', 'nir']`). Otto hat recht; es fehlt nur ein Test, der genau
  das benennt.
- Karte: `syncFocusRaster` (`mapLayers.ts`) legt je Szene eine Raster-Quelle mit
  `tileSize: 256` an, zugeschnitten über `clipTileUrl` (AOI nur im Browser, nie
  in der URL). Layer (`layers.ts`) halten `overlays` (`image` oder `raster` mit
  `tileUrl`) und `restore` (Auswahl, AOI, `cropToAoi`, Datensatz);
  `selectLayer` stellt die Auswahl wieder her.
- Vollauflösung: `ViewerControls` (Stretch, Colormap, „Apply“, „Add to layers“,
  „Exit“); `ViewBar` (nur ohne Vollauflösung) trägt „⚙ Process“.

**Backend** (Fundstellen aus `backend/earthx/`):
- Kachel-Route mit Operator: `api/tiler.py` `_operator_request` (Z. 367–407):
  `op`, `op_version`, `params` zusammen, `params` höchstens 2048 Zeichen,
  nur T1 und `pixel`, sonst `422`; höchstens 16 Assets (Z. 348, 481).
- Schätzung: `POST /processing/processes/recipe/estimate` meldet einen Auftrag
  über dem Deckel selbst mit **`413`** (`processing_route.py` Z. 689–700;
  `MAX_JOB_BYTES` = 5 GB, `access/crop_rules.py` Z. 111). Ein Auftrag ohne
  `aoi` nimmt die Vereinigung der Footprints (`intake.py` Z. 298,
  `_whole_scenes_aoi` Z. 561–589); für Schätzung und Start gleich.
- Grenzen: `MAX_ORDER_ITEMS` 25, `MAX_ORDER_ASSETS` 16, `MAX_ORDER_STEPS` 16
  (`intake.py` Z. 139–141). Queue: global 4, je Host 2
  (`catalog/migrations/006_jobs.sql` Z. 37).
- Ergebnisse: signierte URL 15 min (`objectstore/results.py` Z. 36), Ablauf
  7 Tage (Z. 31), 60-s-Regel (Z. 37); die URL ist für `S3_PUBLIC_ENDPOINT`
  signiert (lokal `http://localhost:3900`). Keine CORS-Regel am Bucket
  (Garage, `compose/objectstore/`). Die Ergebnis-Eigenschaften tragen
  `proj:code` bzw. `proj:wkt2`, `gsd` nur bei projiziertem CRS, `bands`,
  `earthx:resampled` (`processing/core.py` Z. 305–329); keine `bbox`.
- `objectstore` dürfen laut `.importlinter` alle außer den Fachmodulen
  importieren; `earthx.api` (und damit `api/tiler.py`) ist nicht beschränkt.
  Der Dienst `tiler` hat in `docker-compose.yml` aber **keinen Schlüssel** für
  den Objektspeicher; `api` hat den Leseschlüssel (nur Signieren), `jobs` den
  Schreibschlüssel (`adr/0015`).
- `reproject` v2: `crs` mit `pattern ^EPSG:[0-9]{4,6}$`, geprüft mit
  `rasterio.crs.CRS`; `resolution` „Pixel size in the units of the target CRS,
  square pixels.“ (`processing/operators/reproject.py` Z. 67–90). `pyproj ≥ 3.6`
  steht in `requirements.txt`, genutzt nur in `access/aoi_upload.py`. Keine
  Route gibt die Einheit eines CRS heraus.
- Jobs haben keinen Titel, weder in der API noch in der Queue.

---

## 3. Vorschlag

### 3.1 Fenster (Zusatz Punkt 1, F1)

- **Zusammenstellen** in einer festen Seitenleiste am rechten Rand, von unter den
  Kartenknöpfen (64 px) bis über die Statusleiste, Breite
  `clamp(420px, 36vw, 600px)`, nicht ziehbar. Solange sie offen ist, ist die
  Trefferliste rechts eingeklappt (sie läge darunter). Die Karte bleibt links
  frei, damit die Vorschau beim Bearbeiten sichtbar ist.
- **Innen:** eine Spalte mit festem Kopf (Titel, Schließen, Auswahl in Worten,
  „Area“) und festem Fuß („Review“, Schätzung, „Start job“); dazwischen
  scrollen Bänder, Schritte, Ausgabe, Vorschau. Das Ausdrucksfeld wird mehrzeilig
  (`textarea`, Enter fügt keine Zeile ein; der Ausdruck bleibt einzeilig).
- **Jobliste** wird ein eigenes kleines Fenster (das heutige `Draggable`,
  360 px), geöffnet über „⚙ Jobs (n)“; es bleibt, bis UI-01 den
  Processing-Manager baut. „Start job“ öffnet es, falls zu.
- **Schmale Bildschirme** (unter 900 px Breite): die Leiste wird ein Blatt von
  unten über die volle Breite, höchstens 60 % der Höhe, mit Griff zum Auf- und
  Zuklappen; die Karte bleibt oben sichtbar.

```
≥ 900 px                                    < 900 px
┌──────────────────────────┬───────────┐   ┌───────────────────┐
│ Controls │  Karte         │PROCESSING │   │ Karte             │
│          │  (Vorschau,    │ Kopf      │   │  [Preview]        │
│          │   [Preview])   │ ……scroll… │   ├────═════──────────┤
│          │                │ Fuß       │   │ PROCESSING (60 %) │
└──────────────────────────┴───────────┘   └───────────────────┘
```

### 3.2 Ganze Szene oder nur AOI (Zusatz Punkt 2)

Von Otto entschieden: Umschalter, Vorgabe „Whole scene“. Ausgestaltung (K1–K4):
- Umschalter „Area: Whole scene | AOI only“ im Kopf. **Whole scene:** Kandidaten
  sind alle gewählten Szenen (nicht nach AOI gefiltert), geteilt in Überflüge wie
  heute; der Auftrag hat kein `aoi`. **AOI only:** wie heute.
- **K1:** „⚙ Process“ braucht keine AOI mehr; ohne AOI ist „AOI only“
  deaktiviert mit „Draw an AOI first“. (Folgt aus „ohne `aoi`“; sonst wäre
  „Whole scene“ nur mit einer AOI erreichbar, die dann nichts bedeutet.)
- **K2:** Antwortet „Review“ mit `413`, zeigt das Panel den Text des Servers und
  darunter „The whole scene is too large for one job. Try “AOI only”.“ mit einem
  Knopf, der umschaltet (ohne AOI: „Draw an AOI to process a part of the
  scene.“). Keine eigene Grenze im Browser.
- **K3:** Ein neuer AOI verwirft nicht mehr den Entwurf, nur die Schätzung (die
  hängt ohnehin am Auftragstext, K4 aus M4-13). Ein Wechsel des Datensatzes
  verwirft ihn weiter. Grund: mit „Whole scene“ ist die AOI oft gar nicht Teil
  des Auftrags, und Schritte neu einzugeben kostet.
- **K4:** Die Maske (`mask.tif`) deckt bei „Whole scene“ die Vereinigung der
  Footprints; der Hinweis unter dem Umschalter sagt „The result covers the whole
  scenes; the mask marks where they have data.“
- Der Ablauf „Crop & merge to AOI“ beim Download bleibt unberührt.

### 3.3 T1-Vorschau und „Preview“ (Plan M4-13 §3.7, unverändert)

- Planer: längster Anfang mit `T1` und `pixel`; leer → „No preview: the first
  step runs only as a job“. Mehr als ein T1-Schritt → nur der erste, mit
  Hinweis (die Kachel-Route nimmt ein `op`).
- Eine Raster-Quelle je Szene des Auftrags (höchstens 40 wie in der
  Fokusansicht), Kachel-URL `…/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=…&op=…&op_version=…&params=<kanonisches JSON>&rescale=…&colormap_name=…`;
  bei „AOI only“ über `clipTileUrl` zugeschnitten, bei „Whole scene“ nicht.
  Die Vorschau erscheint erst, wenn der Schritt gültig ist (Formularprüfung),
  und erneuert sich mit 400 ms Verzögerung nach der letzten Eingabe.
- Abschnitt „Preview on the map“ im Panel: Wertebereich, Colormap, „Apply“
  (Startwerte −1 bis 1, `rdylgn`; F3 (1)), „Auto stretch“ gesperrt mit Grund.
- **Badge „Preview“** an der Karte und im Panel nach F4 (1):
  `156543.03392 · cos(φ) / 2^z` m je Pixel an der äquatornächsten Breite des
  Ausschnitts, `z = min(round(mapZoom + 1), max_zoom)`, gegen das feinste `gsd`
  der Assets (Asset-`gsd`, `raster:bands[0].spatial_resolution`,
  `properties.gsd`); ohne `gsd` immer.
- Mosaik-Überlappung: Die Vorschau legt die Szenen in der Reihenfolge der
  Fokusansicht übereinander, der Job nach `mosaic_order` des Servers. Wo sich
  Szenen überlappen, kann die Vorschau eine andere Szene zeigen als das
  Ergebnis; das Mosaik im Kachel-Pfad ist M4-17. Im Hinweis bei mehreren Szenen
  steht es.

### 3.4 Ergebnis direkt im Viewer (Zusatz Punkt 3, F2)

- **Band-Math (T1):** „＋ Add preview to layers“ und „Replace source layer“ im
  Abschnitt „Preview on the map“. Der Layer hält die Kachel-URL mit
  `op`/`params` (Overlay `raster`, wie heute) und heißt „Preview · <Operator>“;
  er trägt das Badge-Recht weiter (Overlay bekommt `gsd`).
- **Job-Ergebnis (T2):** In der Jobzeile eines fertigen Jobs „Show on map“ mit
  „As a new layer“ und „Replace source layer“. „Source layer“ ist der Layer, aus
  dem das Panel geöffnet wurde (§3.5), sonst die Fokusansicht; ohne beides gibt
  es nur „As a new layer“.
- **Ersetzen** heißt: der Quell-Layer wird ausgeblendet (nicht gelöscht), der neue
  Layer steht an seiner Stelle in der Liste. Zurück über das Auge des Quell-Layers.
- **Weg der Kacheln eines Job-Ergebnisses** — F2 (a), freigegeben mit Auflage
  (§10): der `tiler` liest das Ergebnis über `objectstore`, **ohne Datenbank**.
  - **Welche Datei:** Die Datei eines Ergebnisses liegt unter
    `results/{result_id}/result.tif`; `result_id` ist zufällig, nie die `jobID`
    oder ein Hash (`objectstore/results.py` Kopf, `adr/0015` §8.1). Die Zuordnung
    `jobID` → `result_id` kennt nur die Queue. Deshalb gibt sie `api` heraus: Das
    Ergebnisdokument `GET /processing/jobs/{jobID}/results` bekommt für ein
    Raster-Ergebnis einen Link `tiles` auf
    `/results/{result_id}/tilejson.json` (Prinzip 2.7: auch die API kann es).
    `result_id` steht schon heute im Pfad jeder signierten URL (`Location` des
    `303`); der Link gibt also nichts heraus, was der Browser nicht schon sieht.
  - **Neue Routen im `tiler`:** `/results/{result_id}/tilejson.json` und
    `/results/{result_id}/tiles/WebMercatorQuad/{z}/{x}/{y}` (`rescale`,
    `colormap_name`, `bidx`; kein `expression`, kein `op`). Proxy `/results` →
    `tiler` in `vite.config.ts`. Ein `result_id`, der nicht die Form von
    `token_urlsafe(16)` hat, gibt `404`, bevor etwas gelesen wird.
  - **Woher der `tiler` das Ablaufdatum kennt:** aus dem Objektspeicher selbst.
    Ein `HEAD` auf `result.tif` (über `objectstore`, mit dem eigenen
    Leseschlüssel) liefert `Last-Modified`; das Ablaufdatum ist
    `Last-Modified + RESULT_TTL` (7 Tage). Das ist dieselbe Regel, nach der die
    Bucket-Regel das Objekt löscht (`adr/0015` §7.3; `lifecycle_ok` prüft, dass
    beide gleich sind). Der Aufseher lädt hoch, **bevor** er den Lauf
    abschließt, und setzt dann `expires_at = Abschluss + 7 Tage`
    (`jobs/queue.py::finish_successful`); deshalb gilt
    `Last-Modified + 7 Tage ≤ expires_at`: der `tiler` hört nie nach dem Ablauf
    der API auf, höchstens um die Dauer des Hochladens früher. Ab diesem Datum
    minus 60 s (`MIN_REMAINING`) antwortet er `410`; fehlt das Objekt (gelöscht),
    `404`. Das Ergebnis des `HEAD` hält der Prozess höchstens 60 s (kurzlebiger
    Cache, kein Zustand). Neu in `objectstore`: `result_modified(store,
    result_id, name)` neben `result_size`.
  - **Lesen:** `objectstore` gibt dem `tiler` eine für den **internen**
    Endpunkt (`S3_ENDPOINT`) signierte URL mit höchstens 15 min Gültigkeit; GDAL
    öffnet sie, `access` bekommt nur den geöffneten Pfad wie heute (es importiert
    kein `objectstore`). Der `tiler` signiert neu, bevor eine URL abläuft; die 15
    Minuten betreffen den Browser nicht. In c-5 zu prüfen: dass die
    GDAL-Optionen des `gateway` (`gdal_options(policy)`) den internen Endpunkt
    nicht sperren, und wenn doch, wie die Ausnahme auf `objectstore` begrenzt
    bleibt.
  - **Eigener Leseschlüssel (Auflage):** `compose/objectstore/bootstrap.py`
    legt einen dritten Dienstschlüssel `earthx-tiler` an, nur `read`
    (wie `earthx-api`, nicht der Schlüssel des Workers mit `write`); eigenes
    Volume `objectstore-key-tiler`, `S3_*` für den Dienst `tiler`. Nachtrag
    `adr/0015` (dritter Dienst mit Schlüssel, nur lesen; GDAL-Abruf über eine von
    `objectstore` signierte URL als Fall der Ausnahme B8) und
    `architekturplan.md` 3.1. Keine neue Importregel: `.importlinter` erlaubt
    `api → objectstore` schon.
  - **Bestehende Installation (Otto, 15.10.2026):** Eine lokale Installation mit
    vorhandenem Volume `objectstore-secrets` bekommt den Schlüssel beim nächsten
    `docker compose up -d --build`, ohne Datenverlust und ohne Handarbeit. Das
    trägt der Weg, über den M4-06 die Schlüssel `jobs` und `api` in die Volumes
    aus M3-23 brachte (`plans/m4-06-objectstore.md` §7 „Bestehende Volumes“):
    - `SERVICE_KEYS` in `bootstrap.py` bekommt den dritten Eintrag (`tiler`,
      `earthx-tiler`, `OBJECTSTORE_TILER_KEY_DIR`, `/keys/tiler`, nur `read`).
      Das neue Volume `objectstore-key-tiler` hängt beschreibbar an
      `objectstore-secrets` und nur lesend an `objectstore-init` und `tiler`.
      `tiler` wartet wie heute auf `objectstore-init`
      (`service_completed_successfully`).
    - Beim nächsten `up` legt Compose das leere Volume an und baut die beiden
      Einmal-Dienste neu, weil sich ihre Mounts ändern; beide laufen wieder.
    - `secrets` schreibt nur, was fehlt (`_ensure_service_key`: vorhandene
      Dateien bleiben, „already present, unchanged“). Also nur den Schlüssel
      des `tiler`. RPC-Secret, Admin-Token, S3-Schlüssel, Bucket-Name und die
      Schlüssel `jobs` und `api` bleiben unverändert.
    - `init` importiert nur den neuen Schlüssel und gibt ihm `read` am Bucket.
      Bucket, Objekte und Regel bleiben.
    - Kein `down -v`, kein Löschen eines Volumes, kein Schritt von Hand. Ergebnisse
      der letzten 7 Tage bleiben abrufbar.
    - Belegt durch Tests (§3.8) und Schritt 10 der Prüfanleitung (§9).
      Scheitert der Weg in der Umsetzung, schreibt c-5 die genauen Schritte für
      Otto in die Prüfanleitung, statt ihn stillschweigend zu ändern.
  - **Grenze:** Ein verworfener Job (`DELETE`) beendet die Kacheln nicht, solange
    die Datei liegt (ein Lauf kann mehreren Jobs gehören, M4-08b Cache); wer den
    Link hat, sieht die Kacheln bis zum Ablauf, so wie eine schon geladene Datei.
  - Kennzeichnung: Layer „Result · <Operator>“; Badge „Overview“, solange die
    Kachel gröber ist als die Auflösung des Ergebnisses (dieselbe Regel wie §3.3,
    `gsd` aus den Eigenschaften oder bei geografischem CRS aus `tilejson`
    `bounds` und Breite). „Resampled to a common grid“ steht wie in der Jobzeile
    auch am Layer (Prinzip 2.9). Das Frontend zeigt ab `expires` − 60 s
    „Expired“ und lädt keine Kacheln mehr; der `410` des `tiler` ist die Sperre
    dahinter.
  - Kosten: Kacheln lesen über das interne Netz aus dem eigenen Speicher, kein
    Egress zur Quelle; ein Ergebnis-COG hat Übersichten [A] (`plan.py` Z. 380
    rechnet sie mit 4/3 ein; in c-5 zu prüfen).

### 3.5 Einstiege (Zusatz Punkt 4, F3)

Empfehlung F3 (1): Beide Einstiege stellen zuerst die Auswahl her, dann öffnet
das Panel; das Panel liest wie heute nur die Auswahl.
- **Layer-Manager:** je Layer ein Knopf „⚙“ („Process this layer“).
  `selectLayer(id)` stellt Datensatz, Szenen, Gruppen, AOI und Ansicht wieder her;
  das Panel öffnet mit „AOI only“, wenn der Layer mit „Crop & merge to AOI“
  angelegt wurde, sonst mit „Whole scene“. Für Szenen aus mehreren Überflügen
  gilt die Wahl aus §3.6. Gesperrt mit Grund für Layer eines Job-Ergebnisses
  („A result cannot be processed further yet.“), einer Vorschau (dasselbe) und
  für Datensätze unter *processing* (B11).
- **Vollauflösung:** „⚙ Process“ in `ViewerControls`, für die Szenen der
  Fokusansicht; Fläche nach `cropToAoi` wie oben.
- „Source layer“ für §3.4 ist der Layer, aus dem geöffnet wurde (nur im
  Speicher des Tabs).

### 3.6 Batch: dieselben Schritte für mehrere Szenen (Zusatz Punkt 7, F4, F5)

- Im Kopf unter „Area“: **„Run as“** mit „One job“ (heute: ein Überflug, bei
  mehreren mit Wahl des „Pass“), „One job per pass (N)“ und „One job per scene
  (N)“. Die Einträge mit N = 1 fehlen.
- Je Einheit ein eigener Auftrag mit denselben Schritten, Bändern und demselben
  Datentyp; bei „AOI only“ nur Szenen, die die AOI trifft. Annahme, Queue und
  Deckel je Job wie heute; **kein Backend-Code**.
- **Ein Datensatz:** Die Auswahl gehört heute immer zu einem Datensatz; der
  Auftragsbau prüft es trotzdem und weist mit Grund ab (Test).
- **Höchstens 25 Aufträge** je Batch (F5), wie `MAX_ORDER_ITEMS`; darüber ist
  „Run as“ für diese Einheit deaktiviert mit „At most 25 jobs at once“.
- **Schätzung:** „Review“ schätzt jeden Auftrag (höchstens 4 Anfragen
  gleichzeitig, eine `AbortController` für alle) und zeigt die Summe:
  „N jobs · about X MP, Y GB, Z units in total“. Die Dauer als Summe der
  Rechenzeit („about N min of work“) mit dem Satz „Jobs run 2 at a time per
  source; the rest wait.“ Teile, die der Server abweist (etwa `413`), stehen
  einzeln mit Grund darunter.
- **Start:** „Start N jobs“ startet die geschätzten Teile nacheinander; ein
  abgewiesener Start hält die übrigen nicht an. Teile, die schon die Schätzung
  abwies, startet er nicht, und der Knopf sagt es („Start 23 of 25 jobs“).
- **Titel:** Jeder Job eines Batches trägt im Panel „<Operatoren> ·
  <Datensatz> · 3/25“; Einzeljobs „<Operatoren> · <Datensatz>“. Der Titel liegt
  mit `jobID` und `expires` im `sessionStorage` (K5).

### 3.7 Auflösung mit Einheit (Zusatz Punkt 6, F6)

- Empfehlung F6 (1): **neue Route** `GET /processing/crs/{code}`, z. B.
  `/processing/crs/EPSG:3035`, in `api` mit `pyproj`:
  `{"code", "name", "kind": "projected"|"geographic"|"other", "unit": {"name", "kind": "linear"|"angular", "toBase"}}`
  (`toBase` = Faktor auf Meter bzw. Grad, aus `pyproj` `unit_conversion_factor`).
  Dieselbe Prüfung wie `reproject` (`pattern`, `CRS`), sonst `422`; ein CRS ohne
  Einheit an den Achsen → `422` „the CRS names no unit for its axes“.
  `Cache-Control: public, max-age=86400`.
- **Kein Netz (Auflage):** `api` schaltet beim Start das PROJ-Netz ab
  (`pyproj.network.set_network_enabled(False)`), unabhängig von
  `PROJ_NETWORK` in der Umgebung; die Route lädt keine Gitter und keine
  Definitionen nach. Ein Test setzt `PROJ_NETWORK=ON`, sperrt jeden
  Socket-Aufbau und zeigt, dass alle Fälle der Route trotzdem antworten und
  `pyproj.network.is_network_enabled()` falsch ist.
- **Unbekannter Code:** `422` mit Grund, z. B. „EPSG:99999 is not a CRS this
  platform knows“; ein Code außerhalb des Musters „not an EPSG code like
  EPSG:3035“.
- Das Feld zeigt unter `resolution`, sobald `crs` gültig ist (Abfrage 300 ms
  nach der letzten Eingabe, verwerfbar):
  - linear in Meter: „Cell size: 10 m × 10 m“;
  - andere lineare Einheit: „Cell size: 10 US survey foot × 10 US survey foot
    (≈ 3.05 m)“;
  - Grad: „Cell size: 0.0003° × 0.0003° ≈ 33 m (N–S) × 23 m (E–W) at 47.3° N“,
    mit den WGS84-Näherungen für Meter je Grad
    (N–S `111132.954 − 559.822·cos 2φ + 1.175·cos 4φ`,
    E–W `111412.84·cos φ − 93.5·cos 3φ + 0.118·cos 5φ`);
  - unbekannt: der Name der Einheit aus der Antwort; `422` → Text am Feld und
    „Review“ gesperrt.
- φ ist die mittlere Breite des Ausschnitts: bei „AOI only“ die Mitte der
  AOI-`bbox`, bei „Whole scene“ die Mitte der `bbox` aller Szenen des Auftrags
  (im Batch: aller Szenen des Batches). Neu berechnet bei jeder Änderung.
- Die Parameter von `reproject` bleiben unverändert. Ob `reproject` selbst ein
  CRS ohne Einheit abweist, gehört nicht hierher (K6).

### 3.8 Tests

Frontend (vitest, `fetch`/`EventSource` gestubbt, synthetisch):
- Fenster: Leiste öffnet und schließt, Jobliste getrennt, „Start job“ öffnet sie;
  Layout-Klasse unter 900 px (jsdom kann kein Layout messen, geprüft wird die
  Klasse).
- Area: „Whole scene“ ohne `aoi` im Auftrag, Szenen ohne AOI-Filter; „AOI only“
  gesperrt ohne AOI; `413` mit Vorschlag und Umschalten; neue AOI behält die
  Schritte, verwirft die Schätzung.
- Bänder aus dem Ausdruck (Punkt 5): getippt, ohne Chip → im gesendeten
  Auftrag; Name entfernt → Band raus; doppelter Zarr-Name → keines.
- Vorschau: Planer (leer, ein, zwei T1-Schritte), URL mit kanonischem JSON und
  Sonderzeichen, Zuschnitt nur bei „AOI only“, Preview-Regel mit Grenzfällen
  (Äquator, 60° N, `gsd` aus drei Quellen, ohne `gsd`), „Auto stretch“ gesperrt,
  Layer anheften und ersetzen.
- Job-Ergebnis als Layer: URL, `410` → „Expired“, Ersetzen und zurück.
- Einstiege: Layer-Knopf stellt Auswahl her und setzt „Area“; gesperrt für
  Ergebnis-Layer und Stufe *display*; „⚙ Process“ in der Vollauflösung.
- Batch: Aufträge je Szene und je Überflug, Summe, Teilabweisung, Start mit
  einem abgewiesenen Teil, Grenze 25, Titel im Speicher, fremder Datensatz
  abgewiesen.
- Einheit: Meter, Fuß, Grad mit Bodengröße auf 0° und 47,3°, unbekannte Einheit,
  `422`, Neuberechnung bei neuer AOI.
- Vertragsdateien (`processingContract.test.ts`): ein Auftrag „Whole scene“ mit
  Schritten und ein Batch-Teil; der Backend-Test `test_frontend_orders.py` nimmt
  sie von selbst.

Backend (pytest, synthetisch):
- `/processing/crs/{code}`: projiziert, geografisch, Fuß, unbekannter und
  kaputter Code `422` mit Grund, CRS ohne Einheit `422`, Cache-Kopf, kein Log
  mit mehr als dem Code; kein Netz trotz `PROJ_NETWORK=ON` (Sockets gesperrt).
- Ergebnis-Kacheln: Kachel aus einem Objektspeicher-Double, `410` ab
  `Last-Modified` + 7 Tage − 60 s, `404` für fehlendes Objekt und falsch geformte
  `result_id`, kein `op`, kein `result_id` im Log, keine Datenbank im Pfad
  (Route läuft ohne Pool); `tiles`-Link im Ergebnisdokument; Schlüssel des
  `tiler` nur `read` (Test über `bootstrap.py`); Importregeln grün.
- Bestehende Installation (`tests/compose/test_objectstore_bootstrap.py`,
  `test_compose_objectstore_wiring.py`): Ein Geheimnis-Ordner mit den Dateien
  aus M4-06 (ohne `tiler`) → `secrets` legt nur den Schlüssel des `tiler` an,
  alle übrigen Dateien bleiben byte-gleich. `init` gegen die nachgebildete
  Admin-API importiert nur `earthx-tiler`, nur mit `read`, legt keinen Bucket
  an und setzt die Regel unverändert. Ein zweiter Lauf ändert nichts. Die
  Compose-Datei hängt `objectstore-key-tiler` an genau die drei Dienste,
  beschreibbar nur an `objectstore-secrets`.

### 3.9 Doku und Log

- `ENTSCHEIDUNGSLOG.md`: Plan-Schritt (diese Zeile), später Freigabe und
  Umsetzung.
- `plans/m4-processing-kern.md` §3: Zeile M4-13c und Teilung nach F7.
- Mit c-5: Nachtrag `adr/0015` und `architekturplan.md` 3.1 (`tiler` liest
  Ergebnisse über `objectstore` mit eigenem Leseschlüssel, ohne Datenbank).

---

## 4. Abnahme

| Punkt | Beleg |
|---|---|
| T1-Vorschau, „Preview“ auf Übersichtsstufen (M4-13) | Planer-, URL- und Regeltests; Prüfanleitung Schritte 3–4 |
| Größeres Fenster (Zusatz 1) | Komponententest; Prüfanleitung Schritt 1 |
| Whole scene / AOI only (Zusatz 2) | Auftragstests, Vertragsdatei, `413`-Test |
| Ergebnis im Viewer (Zusatz 3) | Layer-Tests; Backend-Tests der Ergebnis-Kacheln; Prüfanleitung Schritt 6 |
| Einstiege (Zusatz 4) | Komponententests |
| Bänder aus dem Ausdruck (Zusatz 5) | eigener Test |
| Auflösung mit Einheit (Zusatz 6) | Routen- und Anzeigetests |
| Batch (Zusatz 7) | Store- und Komponententests |
| Oberflächentexte nur Englisch | Durchsicht im PR |

---

## 5. Nicht in dieser Aufgabe

- Processing-Manager mit Titeln zum Umbenennen, Archiv, Gruppen: UI-01.
- Automatische Skalierung, Methodentext, Permalinks, „Parameter übernehmen“:
  M4-19.
- Mosaik im Kachel-Pfad (eine Vorschau über Szenengrenzen nach der Regel des
  Jobs): M4-17.
- Ein Job-Ergebnis als Eingabe eines weiteren Jobs.
- Statistik, Info und Punktabfrage mit `op` oder auf Job-Ergebnissen.
- `.github/`, `.importlinter` (keine Änderung nötig), `processing`, `jobs`,
  `gateway`.

---

## 6. Teilung, Umfang und Commits (F7)

Geschätzt [A], ohne Tests: Fenster und Area 250 Zeilen, Vorschau mit Badge,
Layern und Einstiegen 450, Einheit 200 (davon Backend 60), Batch 300,
Ergebnis-Kacheln 350 (davon Backend 200, Compose und Doku 50). Zusammen rund
1550 Zeilen Code und ebenso viel Tests; weit über dem Richtwert von 400.

Empfehlung F7 (1), fünf PRs, nacheinander:
- **M4-13c-1** Fenster, „Whole scene / AOI only“, Test Bänder aus dem Ausdruck
  (§3.1, §3.2, Punkt 5); in dieser Session nach der Freigabe.
- **M4-13c-2** T1-Vorschau, „Preview“, Vorschau als Layer, Einstiege (§3.3, §3.4
  erster Punkt, §3.5). M4-19 wartet nur auf diesen Teil.
- **M4-13c-3** Auflösung mit Einheit (§3.7), Backend und Frontend.
- **M4-13c-4** Batch (§3.6).
- **M4-13c-5** Job-Ergebnis als Layer (§3.4 ab „Weg der Kacheln“), Backend,
  Compose, Nachtrag `adr/0015`.

Jede ab c-2 als neue Session nach dem Merge der vorigen; c-3 bis c-5 berühren
verschiedene Teile, ändern aber alle das Panel, deshalb nicht gleichzeitig.

Vor jedem „fertig“: `main` holen; `ruff check backend`, `pytest`,
`PYTHONPATH=backend lint-imports --config .importlinter`; im Frontend
`npm run lint`, `npx tsc -b --pretty false`, `npm test`.

---

## 7. Risiken

- **Ganze Szenen kosten mehr:** Die Vorgabe „Whole scene“ macht jeden Job größer
  als einen Zuschnitt (ein Sentinel-2-NDVI rund 0,5 GB Ausgabe [A]); Mosaike
  langer Überflüge stoßen an die 5 GB. K2 fängt es mit dem Vorschlag ab.
- **Batch belastet die Quelle:** 25 Schätzungen holen je ihre Items, 25 Starts
  je einen `HEAD` je Asset. Die Begrenzung auf 4 gleichzeitige Schätzungen und
  den Start nacheinander hält die Last bei der heutigen eines Nutzers mal vier.
  Quoten kommen mit M6.
- **Ergebnis-Kacheln:** Die `result_id` steht in der Kachel-URL; sie steht
  schon heute im Pfad jeder signierten URL. Nicht im Log (`--no-access-log`,
  Test), aber im Verlauf der Entwicklerwerkzeuge des Browsers. Ein verworfener
  Job beendet die Kacheln nicht (§3.4 „Grenze“).
- **Vorschau ≠ Ergebnis bei Überlappung** (§3.3), bis M4-17.
- **Bodengröße bei Grad ist eine Näherung** (WGS84-Reihe, Fehler unter 0,1 %
  [A]); das „≈“ steht immer davor.

---

## 8. Fragen an Otto

**F1 — Form des Fensters (§3.1)**
1. Feste Seitenleiste rechts, `clamp(420px, 36vw, 600px)`, volle Höhe; unter
   900 px ein Blatt von unten (60 %); Jobliste bleibt ein kleines Fenster
   **(Empfehlung)**
2. Zentrierter Dialog (bis 960 px, zwei Spalten); verdeckt die Karte und damit
   die Vorschau beim Bearbeiten
3. Das heutige ziehbare Fenster, nur breiter (560 px)

**F2 — Weg der Kacheln eines Job-Ergebnisses (§3.4)**

| | (a) `tiler` über `objectstore` | (b) Browser liest die COG über die signierte URL | (c) `api` leitet weiter |
|---|---|---|---|
| Modulgrenzen | `api/tiler.py` darf `objectstore` schon importieren; `access` bleibt frei davon; keine neue Importregel. Neu: der Dienst `tiler` bekommt den Leseschlüssel (Compose, Nachtrag `adr/0015`) | keine Backend-Änderung außer einer CORS-Regel am Bucket; neue Frontend-Abhängigkeit (COG-Leser, Lock-Datei) | der `tiler` müsste die Datei über eine Adresse von `api` lesen: ein Abruf außerhalb von `gateway` und `objectstore` (verletzt „nur über gateway“, B8) oder eine Ausnahme im `gateway` für einen internen Host |
| 15 min der URL | betrifft den Browser nicht, der `tiler` signiert neu | jede Viertelstunde eine neue URL; braucht eine Route, die die URL als JSON statt `303` liefert | wie (a), wenn `api` neu signiert |
| 7 Tage | `410` der Kachel-Route, Layer „Expired“ | `403` des Speichers nach Ablauf, im Browser schwer zu deuten | wie (a) |
| Ergebnis in fremdem CRS (z. B. EPSG:3035) | der `tiler` reprojiziert wie bei jeder Quelle | MapLibre zeigt nur Web Mercator; der Browser müsste reprojizieren | wie (a) |
| „Preview“ ↔ Ergebnis | Kacheln aus dem Ergebnis, Badge „Overview“ nach derselben Regel | Darstellung im Browser, weicht vom `tiler` ab | wie (a) |

1. (a) **(Empfehlung)**
2. (b)
3. (c)

**F3 — Fläche und Szenen beim Einstieg aus Layer-Manager und Vollauflösung (§3.5)**
1. Auswahl des Layers bzw. der Fokusansicht herstellen, dann das Panel öffnen;
   „AOI only“, wenn der Layer zugeschnitten war, sonst „Whole scene“
   **(Empfehlung)**
2. Das Panel bekommt eine eigene Eingabe (Kopie des Layers), unabhängig von der
   Auswahl; zwei Wege zum selben Auftrag
3. Immer „Whole scene“, egal wie der Layer angelegt wurde

**F4 — Einheit eines Batches (§3.6)**
1. Beides wählbar: „One job per pass“ und „One job per scene“ **(Empfehlung,
   Ottos Vorschlag)**
2. Nur je Szene
3. Nur je Überflug

**F5 — Höchstzahl je Batch (§3.6)**
1. 25 Aufträge, wie `MAX_ORDER_ITEMS`; die Queue lässt davon 2 je Quelle
   gleichzeitig laufen, der Rest wartet als „Waiting for a worker“
   **(Empfehlung)**
2. 10 Aufträge, damit ein Batch die Queue nicht lange für andere sperrt
3. Keine Grenze im Panel

**F6 — Woher die Einheit des Ziel-CRS kommt (§3.7)**
1. Kleine Route `GET /processing/crs/{code}` mit `pyproj`; die Anzeige kommt
   beim Tippen, unabhängig von „Review“ **(Empfehlung)**
2. In der Antwort der Schätzung; die Einheit erscheint erst nach „Review“, und
   ein fertiger Auftrag ist dafür nötig
3. In der Prozessbeschreibung als Liste erlaubter CRS mit Einheiten; legt eine
   feste Liste fest, die es heute nicht gibt

**F7 — Teilung (§6)**
1. Fünf PRs c-1 bis c-5 wie in §6; c-1 in dieser Session **(Empfehlung)**
2. Zwei PRs: Frontend ohne Ergebnis-Kacheln, dann Ergebnis-Kacheln mit Backend
   und Einheit
3. Ein PR (rund 3000 Zeilen mit Tests)

**Kleinentscheidungen** (gelten mit der Freigabe, wenn Otto nichts sagt):
- **K1:** „⚙ Process“ braucht keine AOI mehr (§3.2).
- **K2:** `413` bei „Review“ → Vorschlag „AOI only“ mit Knopf (§3.2).
- **K3:** Ein neuer AOI verwirft nur die Schätzung, nicht die Schritte (§3.2).
- **K4:** Hinweis zur Maske bei „Whole scene“ (§3.2).
- **K5:** Der Titel eines Jobs liegt zusätzlich zu `jobID` und `expires` im
  `sessionStorage` (erweitert M4-13 F5; ohne AOI, ohne Auftrag).
- **K6:** `reproject` bleibt unverändert; ein CRS ohne Einheit sperrt nur das
  Panel (die Route sagt es). Soll auch der Operator es abweisen, wäre das eine
  eigene Aufgabe mit neuer `op_version`.
- **K7:** Die Vorschau erneuert sich 400 ms nach der letzten Eingabe und nur für
  einen gültigen Schritt (§3.3).

---

## 9. Prüfanleitung für Otto (je PR im PR-Text; hier das Ganze, PowerShell)

```powershell
docker compose up -d --build
cd frontend
npm ci
npm run dev
```

Im Browser `http://localhost:5173`:
1. Datensatz `sentinel-2-c1-l2a`, Fläche zeichnen, suchen, einen Überflug mit
   wenig Wolken wählen; „⚙ Process“: die Leiste steht rechts, die Karte links
   frei. Fenster schmaler als 900 px ziehen: Blatt von unten.
2. „Area“ steht auf „Whole scene“; „＋ Band math“, `(nir - red) / (nir + red)`
   tippen, ohne Chip: „Review“ nennt zwei Bänder und die Größe der ganzen Szene.
3. Die Karte zeigt die Vorschau (−1 bis 1, `rdylgn`) mit „Preview“.
4. Hineinzoomen bis etwa Kartenzoom 12,5 (10 m auf 48° N): „Preview“
   verschwindet. „＋ Add preview to layers“: der Layer steht im Layer-Manager.
5. „AOI only“: Vorschau und Auftrag auf die Fläche zugeschnitten.
6. „Start job“; fertig: „Show on map“ → „As a new layer“; der Layer heißt
   „Result · band_math“, beim Herauszoomen mit „Overview“.
7. `cop-dem-glo-30`, „＋ Reproject“, `crs` `EPSG:4326`, `resolution` `0.0003`:
   unter dem Feld „≈ 33 m (N–S) × 23 m (E–W) at …“; `EPSG:3035`, `30`:
   „30 m × 30 m“.
8. Zwei Überflüge wählen, „Run as: One job per scene“: „Review“ zeigt
   „N jobs“ und die Summe; „Start N jobs“; die Jobliste zeigt „… · 1/N“ usw.
9. Im Layer-Manager „⚙“ an einem Layer aus „Crop & merge to AOI“: das Panel
   öffnet mit „AOI only“.
10. (c-5) Bestehende Installation: Vor dem Update einen Job laufen lassen und
    seinen „Result (COG)“-Link merken. Dann den Branch holen und nur
    `docker compose up -d --build` ausführen, ohne `down` und ohne `-v`.
    `docker compose logs objectstore-secrets objectstore-init` zeigt „service key
    for tiler created“ bzw. „… imported“, für `jobs` und `api` „already present,
    unchanged“ bzw. „already imported“. Der alte Link lädt weiter, und sein
    Ergebnis lässt sich als Layer zeigen.

---

## 10. Freigabe (Otto, 15.10.2026)

**F1–F7 je Option 1, K1–K7 angenommen.** Zwei Auflagen, oben eingearbeitet:
- **F2:** Nach `expires_at` liefert der `tiler` für ein Ergebnis keine Kacheln
  mehr (`410`). Er kennt das Ablaufdatum ohne Datenbank: aus `Last-Modified`
  des Objekts plus 7 Tage, der Regel der Bucket-Löschung (§3.4). Eigener
  Leseschlüssel nur zum Lesen für den `tiler`, nicht der Schlüssel des Workers;
  Nachtrag `adr/0015`.
- **F6:** Die Route lädt nichts aus dem Netz (PROJ-Netz aus, auch wenn
  `PROJ_NETWORK=ON` gesetzt ist); ein Test belegt es. Unbekannter Code → `422`
  mit Grund (§3.7).

**Teilung (F7):** c-1 in dieser Session (Branch `claude/dreamy-brown-nwdzid`,
PR #152). c-2 bis c-5 je als neue Session nach dem Merge des vorigen, in dieser
Reihenfolge, mit diesen Startsätzen:
- „Führe Aufgabe M4-13c-2 aus `docs/plans/m4-processing-kern.md` aus (Plan:
  `docs/plans/m4-13c-vorschau-und-viewer.md` §3.3, §3.4 erster und zweiter Punkt
  ohne Job-Ergebnis, §3.5).“
- „Führe Aufgabe M4-13c-3 aus `docs/plans/m4-processing-kern.md` aus (Plan:
  `docs/plans/m4-13c-vorschau-und-viewer.md` §3.7 mit der Auflage aus §10).“
- „Führe Aufgabe M4-13c-4 aus `docs/plans/m4-processing-kern.md` aus (Plan:
  `docs/plans/m4-13c-vorschau-und-viewer.md` §3.6).“
- „Führe Aufgabe M4-13c-5 aus `docs/plans/m4-processing-kern.md` aus (Plan:
  `docs/plans/m4-13c-vorschau-und-viewer.md` §3.4 Job-Ergebnis mit der Auflage
  aus §10).“

Jede Session liest diesen Plan ganz, schreibt ihren Stand als eigenen
Abschnitt ans Ende und eine Log-Zeile.

## 11. M4-13c-1 — Umsetzung (15.10.2026)

**Gebaut** (nur `frontend/`, Branch `claude/dreamy-brown-nwdzid`, PR #152):
- **Seitenleiste (§3.1):** `ProcessingPanel.tsx` steht fest am rechten Rand
  (`.processing-sheet`, Breite `clamp(420px, 36vw, 600px)`), mit festem Kopf
  (Titel, Auswahl in Worten, „Area“), scrollender Mitte (Szenen und Überflug,
  Bänder, Schritte, Ausgabe) und festem Fuß („Review“, „Start job“, Schätzung,
  Abweisungen). Unter 900 px ein Blatt von unten, höchstens 60 % der Höhe, mit
  Griff „▾/▴“ zum Einklappen. Die Trefferliste ist eingeklappt, solange die Leiste
  offen ist (ihr Umschalter fehlt dann). Der Band-Math-Ausdruck ist ein
  `textarea`, das umbricht und einzeilig bleibt (Enter fügt nichts ein, ein
  eingefügter Zeilenumbruch wird ein Leerzeichen); Chips fügen weiter an der
  Cursorstelle ein.
- **Jobliste (§3.1):** `JobList.tsx` ist ein eigenes kleines Fenster
  (`Draggable`, 360 px), links neben der Leiste, solange beide offen sind.
  „⚙ Jobs (n)“ öffnet es (vorher: das Panel); „Start job“ öffnet es auch.
- **„Area: Whole scene | AOI only“ (§3.2):** Vorgabe „Whole scene“. Dann nimmt
  der Auftrag alle gewählten Szenen des Überflugs ohne AOI-Filter und schickt kein
  `aoi` (`buildOrder` mit `area`). „AOI only“ wie bisher, ohne AOI deaktiviert;
  verschwindet die AOI danach, sagt das Panel „Draw an AOI first, or choose
  “Whole scene”.“ und sperrt „Review“. K1: „⚙ Process“ braucht keine AOI
  (`processBlockReason` ohne AOI). K2: `413` bei „Review“ unter „Whole scene“ →
  Text des Servers und „The whole scene is too large for one job. Try “AOI
  only”.“ mit Knopf „Use AOI only“, ohne AOI „Draw an AOI to process a part of the
  scene.“ K3: Ein neuer AOI verwirft nur eine laufende Schätzung; die Schritte
  bleiben, eine gezeigte Schätzung bleibt, solange der Auftragstext gleich ist
  (bei „Whole scene“ also ja). K4: Hinweis „The result covers the whole scene;
  the mask marks where they have data.“
- **Punkt 5:** bestätigt, dass getippte Bandnamen ohne Chip in den Auftrag
  kommen; eigener Test.

**Tests** (vitest, synthetisch): `ProcessingPanel.test.tsx` (Area: Vorgabe ohne
`aoi`, „AOI only“ mit `aoi`, ohne AOI bedienbar, AOI weg unter „AOI only“; `413`
mit Umschalten, ohne AOI, unter „AOI only“ kein Vorschlag; neue AOI behält die
Schritte, verwirft die Schätzung von „AOI only“, behält die von „Whole scene“;
neuer Datensatz verwirft den Entwurf; Bänder aus dem Ausdruck; einzeiliger
Ausdruck; Jobliste öffnet beim Start, Panel ohne Jobzeilen; Einklappen),
`AppTopBar.test.tsx` („⚙ Jobs (n)“ öffnet die Jobliste, Leiste und Jobliste
nebeneinander, Trefferliste eingeklappt ohne Umschalter, untere Leiste daneben), `processingOrder.test.ts` (`area`), Vertragsdatei
`ndvi-on-whole-scenes-without-aoi.json` (der Backend-Test
`test_frontend_orders.py` nimmt sie; grün). Gegenprobe in der Sitzung: Mit
„AOI only“ als Vorgabe fallen sechs Komponententests.

**Befunde des Reviewers, behoben:** Die Seitenleiste lag über der unteren Leiste
(Auswahl, Zeitleiste, die den Überflug wählt) → sie steht, solange die Leiste
offen ist, mittig in der freien Karte links davon, auf schmalen Bildschirmen über
dem Blatt (Abweichung von §3.1, das es nicht regelte); die Jobliste deckte auf
schmalen Bildschirmen den Fuß des Blatts → sie endet darüber; ein neuer AOI brach
auch bei „Whole scene“ eine laufende Schätzung ab → nur noch bei „AOI only“; der
Griff des Blatts hat einen Namen für Screenreader; Enter während einer
IME-Eingabe bleibt unberührt. Offen gelassen (Hinweise): Die Jobliste verliert
beim Schließen ihre Zugposition; zwischen 900 und 1000 px Breite liegt sie über
dem Control-Panel (ziehbar).

**Ergebnis der Prüfungen:** Frontend 923 Tests grün, `tsc` und `oxlint` ohne
Befund; Backend `ruff` ohne Befund, `pytest` 4589 grün (8 übersprungen: `pwsh`
fehlt in der Sitzung), Importregeln 14 eingehalten.

**Prüfanleitung für Otto** (Windows PowerShell; die Sitzung hat die Oberfläche
nur in Tests gesehen):

```powershell
docker compose up -d --build
cd frontend
npm ci
npm run dev
```

Im Browser `http://localhost:5173`:
1. `sentinel-2-c1-l2a`, Fläche zeichnen, suchen, eine Szene wählen, „⚙ Process“:
   die Leiste steht rechts über die ganze Höhe, die Trefferliste ist eingeklappt.
   Das Fenster schmaler als 900 px ziehen: ein Blatt von unten mit „▾“.
2. „Area“ steht auf „Whole scene“. „＋ Band math“, `(nir - red) / (nir + red)`
   tippen, ohne Chip; „Review“ zeigt die Größe der ganzen Szene.
3. „AOI only“, „Review“: die Größe der Fläche. Eine neue Fläche zeichnen: der
   Schritt bleibt, „Start job“ wartet auf ein neues „Review“.
4. „Start job“: die Jobliste öffnet links neben der Leiste.
5. Die AOI löschen: „⚙ Process“ bleibt aktiv, „AOI only“ ist grau.

## 12. M4-13c-2 — Umsetzung (15.10.2026)

**Gebaut** (nur `frontend/`, Branch `claude/jolly-cori-d0mda9`):
- **Planer und Kachel-URL (§3.3):** `processingPreview.ts`. Die Vorschau ist der
  erste Schritt, wenn er `T1` und `pixel` ist und seine Felder vollständig sind;
  sonst steht „No preview: the first step runs only as a job.“ bzw. „Complete the
  step to see the preview.“ Weitere Schritte (T1 oder nicht) zeigt die Karte nicht;
  das Panel sagt es. Je Szene des Auftrags (höchstens 40) eine Raster-Quelle mit
  `asset` je Band, `op`, `op_version`, `params` als kanonischem JSON, `rescale` und
  `colormap_name`; bei „AOI only“ über `clipTileUrl` im Browser zugeschnitten, die
  AOI steht nie in einer URL. Szenen ohne `bbox` fallen heraus.
- **Zeitpunkt (K7):** `processingStore.ts` hält `preview`; eine Änderung am Entwurf
  oder an der Auswahl erneuert es 400 ms nach der letzten Eingabe, eine wegfallende
  Vorschau (Panel zu, Schritt leer oder ungültig) sofort. Ein Wechsel des
  Datensatzes verwirft sie mit dem Entwurf.
- **Darstellung (F3 (1)):** Abschnitt „Preview on the map“ mit Wertebereich
  (Start −1 bis 1), Colormap (`rdylgn`) und „Apply“ wie in der Vollauflösung;
  „Auto stretch“ gesperrt mit Grund. Ein Bereich, der keiner ist, sperrt „Apply“
  und lässt das gezeigte Bild stehen.
- **„Preview“ (F4 (1)):** `isCoarserThanData` wie im Plan: `156543.03392·cos φ /
  2^z`, φ die äquatornächste Breite der Kartenansicht, `z = min(round(Zoom + 1),
  max_zoom)`, gegen das feinste `gsd` der Assets (Asset, `raster:bands[0]`, Item);
  ohne `gsd` immer. Badge an der Karte (unten links) und im Abschnitt; es steht
  auch für eine angeheftete Vorschau, solange ihr Layer eingeschaltet ist.
- **Karte:** `mapLayers.ts::syncPreview` legt die Quellen über alle Raster und
  unter die AOI-Linie; Raster, die später ankommen (Quicklooks), landen darunter
  (`beforeAoi`).
- **Als Layer (§3.4):** „＋ Add preview to layers“ heftet „Preview · <Operator>“
  oben an; „Replace source layer“ setzt ihn direkt über den Quell-Layer und blendet
  diesen aus (das Auge bringt ihn zurück). Quell-Layer ist der Layer, aus dem das
  Panel geöffnet wurde, sonst die Fokusansicht (dort wird das Bild ausgeblendet);
  aus der Auswahl heraus gibt es nur „Add“. Ein Layer trägt `derived: 'preview'`
  und seine Overlays `preview: { gsd }`; der Download-Knopf fehlt bei ihm.
- **Einstiege (§3.5):** „⚙“ je Layer und „⚙ Process“ in der Vollauflösung stellen
  die Auswahl her (`selectLayer`, Szenen des Layers bzw. der Ansicht), setzen „Area“
  (zugeschnitten und AOI da → „AOI only“, sonst „Whole scene“) und öffnen das
  Panel. Gesperrt mit Grund: Vorschau-Layer („A result cannot be processed further
  yet.“), Datensätze unter *processing*.

**Tests** (vitest, synthetisch, 68 neue): `processingPreview.test.ts` (Planer mit
leer/ein/zwei Schritten, nicht-T1 zuerst, unvollständig; URL mit kanonischem JSON
und Sonderzeichen; Zuschnitt nur bei „AOI only“; `gsd` aus drei Quellen und Zarr;
Regel für „Preview“ am Äquator, bei 47° N, 60° N, über den Äquator, mit
`max_zoom`, ohne `gsd`), `ProcessingPreview.test.tsx` (Abschnitt, Verzögerung,
Wertebereich, Badge, Anheften, Ersetzen aus Layer und Fokusansicht, Einstiege,
Sperren), `mapLayers.test.ts` (`syncPreview`, Reihenfolge). Gegenprobe in der
Sitzung: Zuschnitt immer aus, Ersetzen ohne Ausblenden, `beforeAoi` ohne Vorschau
und umgedrehte Regel lassen je Tests fallen.

**Offen, Frage an Otto (1):** `selectLayer` stellt die Auswahl her, aber nicht die
Trefferliste. Liegen die Szenen eines Layers nicht mehr in den Treffern auf dem
Bildschirm (neue Suche), öffnet „⚙“ das Panel nicht und sagt „The scenes of this
layer are not in the results on screen. Search again to process them.“ Der Plan
(§3.5) setzt voraus, dass die Szenen da sind.
1. So lassen; wer neu sucht, kann verarbeiten **(Empfehlung, kein neuer Code)**
2. Das Panel holt die fehlenden Szenen mit `fetchItem` nach und hält sie neben der
   Auswahl; die Überflüge kämen aus den `groupItemIds` des Layers (rund 80 Zeilen,
   berührt `orderView`)

**Geprüft:** siehe unten (Ergebnis der Läufe); die Oberfläche selbst nur in Tests,
nicht im Browser.

**Prüfanleitung für Otto** (Windows PowerShell):

```powershell
docker compose up -d --build
cd frontend
npm ci
npm run dev
```

Im Browser `http://localhost:5173`:
1. `sentinel-2-c1-l2a`, Fläche zeichnen, suchen, einen Überflug mit wenig Wolken
   wählen, „⚙ Process“, „＋ Band math“, `(nir - red) / (nir + red)` tippen: nach
   einem Moment liegt die Vorschau (−1 bis 1, `rdylgn`) auf den Szenen, dazu
   „Preview“ unten links und im Abschnitt „Preview on the map“.
2. Hineinzoomen bis etwa Kartenzoom 12,5 (10 m auf 48° N): „Preview“ verschwindet.
   Wieder herauszoomen: es kommt zurück.
3. „AOI only“: die Vorschau ist auf die Fläche zugeschnitten. Wertebereich ändern:
   erst nach „Apply“ ändert sich das Bild.
4. „＋ Add preview to layers“: der Layer „Preview · Band math“ steht im
   Layer-Manager, ohne „⇩“, mit gesperrtem „⚙“. Das Auge schaltet „Preview“ mit ihm
   ab.
5. Einen Layer aus „Crop & merge to AOI“ anlegen, im Layer-Manager dessen „⚙“: das
   Panel öffnet mit „AOI only“. Vorschau schreiben, „Replace source layer“: der
   neue Layer steht über dem alten, der alte ist ausgeblendet; sein Auge holt ihn
   zurück.
6. In der Vollauflösung „⚙ Process“: das Panel öffnet für die Szenen der Ansicht;
   „Replace source layer“ blendet das Bild der Ansicht aus.
