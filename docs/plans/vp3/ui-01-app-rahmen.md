# UI-01 — App-Rahmen mit linker Leiste und Processing-Manager

**Stand:** 12.10.2026, ergänzt am 20.10.2026 (§1 Punkte 6–7, §3 Punkt 7, §4), 22.10.2026 (§1 Punkte 10 und 12) und 24.10.2026 (§1 Punkte 6 und 11), beauftragt von Otto.
**Meilenstein:** UI, direkt nach M4 (nach M4-20). Nummer und Name des Meilensteins stehen in `projektplan.md` noch aus.
**Stufe B:** Erst kommt der Plan im Draft-PR, Otto gibt ihn frei, dann folgt der Code.
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** Nach M4-20. Die Aufgabe läuft nicht gleichzeitig mit einer anderen Aufgabe, die das Frontend-Layout ändert.
**Startsatz:** „Führe Aufgabe UI-01 aus `docs/plans/vp3/ui-01-app-rahmen.md` aus.“

## 1. Wünsche von Otto (12.10. und 20.10.2026)

1. **Linke Leiste.** Am linken Rand gibt es eine schmale, immer sichtbare Leiste mit je einem Symbol für:
   - das Control-Menü,
   - den Layer-Manager,
   - den Processing-Manager.
2. **Layer-Manager.** Er hängt fest am linken Rand neben der Leiste und ist nicht mehr frei schwebend wie heute.
3. **Processing-Manager.** Er zeigt nur laufende und fertige Jobs, je Job genau:
   - den Titel, vom Nutzer umbenennbar,
   - den Fortschritt,
   - das Ablaufdatum.
4. **Nicht löschbar.** Jobs lassen sich nicht löschen, nur archivieren und in eigene Gruppen einordnen (anlegen, umbenennen, zuordnen).
5. **Filter.** Man wählt zwischen „Active“ und „All“ (aktive und archivierte Jobs).
6. **Batch als ein Eintrag (20.10.2026).** Die Jobs eines Batches aus M4-13c-4 („One job per pass/scene“) erscheinen als **ein** Eintrag:
   - mit gemeinsamem Titel, Gesamtfortschritt (fertig, laufend, abgewiesen, gescheitert) und dem frühesten Ablaufdatum,
   - aufklappbar zu den einzelnen Teilen.

   Im Backend bleiben es einzelne Jobs: ein Raster je Job, Cache je Teil, Fehler je Teil getrennt, parallel in der Queue (M4-12 §5).

   **Share bei einem Batch (24.10.2026):** In M4-19e ist „Share“ für Stapel gesperrt. Der Plan schlägt vor, ob UI-01 einen Permalink für den ganzen Batch anbietet (ein Link, mehrere Aufträge) oder es bei der Sperre mit Grund bleibt.
7. **„Download all (ZIP)“ (20.10.2026).** Je Batch gibt es ein ZIP mit allen fertigen Teilergebnissen, je Teil ein Ordner mit dem Inhalt des Job-ZIP (Sollliste aus M4-30). Teile, die abgelaufen oder gescheitert sind, fehlen; welche das sind, steht in einer kurzen Liste im ZIP.
8. **Gleiche Breite der Layer-Zeilen (20.10.2026).** Alle Einträge im Layer-Manager sind gleich breit. Die Knöpfe stehen immer an derselben Stelle, auch wenn bei einem Layer ein Knopf fehlt, etwa „Download“. Ein fehlender Knopf lässt einen leeren Platz, statt die anderen zu verschieben.
9. **Ergebnisse aus dem Layer-Manager laden (20.10.2026).** Ein Ergebnis-Layer (Job-Ergebnis, M4-13c-5) hat einen Download-Knopf. Er lädt dasselbe Job-ZIP wie das Panel (Sollliste aus M4-30), ohne zweiten Weg. Ist das Ergebnis abgelaufen, ist der Knopf gesperrt und nennt den Grund.
10. **Reihenfolge greift immer (20.10.2026).**
    - **Befund:** Auch nach M4-28 ändert sich auf der Karte manchmal nichts, wenn man die Reihenfolge der Layer ändert.
    - **Vorgehen:** Zuerst die Ursache finden, mit einem Test, der am Code vor UI-01 scheitert. Otto liefert beim Start die Schritte, mit denen es auftritt.
    - **Ort der Behebung:** in der gemeinsamen Layer-Logik (`mapLayers`, Store), nicht nur in der neuen Optik.
    - **Prüfung:** nach jedem Umsortieren mit allen Layer-Arten (Quicklook, Vollauflösung, Vorschau, Ergebnis, Mosaik aus M4-17).
    - **Stapelung zwischen Überflügen (22.10.2026):** Die offene Ansicht und die angehefteten Layer stapeln mehrere Überflüge heute verschieden (bekannte Grenze aus M4-17c, Plan §15). Soll: gleiche Auswahl, gleiche Reihenfolge, gleiches Bild; dazu ein Test, der am Code vor UI-01 scheitert.
11. **Klick auf einen Ergebnis-Layer (20.10.2026).**
    - **Heute:** Es erscheinen die Suchergebnisse.
    - **Soll:** Es erscheint dieselbe Ansicht wie bei anderen Layern, bezogen auf das Ergebnis: Wertebereich (vmin, vmax), Colormap und Deckkraft, mit der Vorgabe aus der Statistik (M4-32).
    - **Keine Einheiten im Layer-Manager (Otto, 24.10.2026):** Weder Zeilen noch Darstellung im Layer-Manager zeigen eine Einheit, bei keiner Layer-Art. Einheiten stehen im Processing-Panel (Band-Chips, M4-19b) und in den Daten (`bands[].unit`).
    - **Nicht in UI-01:** Processing auf einem Ergebnis, also ein Ergebnis als Eingabe eines neuen Rezepts. Das braucht vorher eine Entscheidungsvorlage (Stufe C, siehe `docs/plans/nach-m4-backlog.md`). Bis dahin ist der Processing-Knopf bei Ergebnis-Layern gesperrt und nennt den Grund.
12. **Nur „Download (ZIP)“ je fertigem Job (22.10.2026).**
    - Ein fertiger Job zeigt in Liste und Details nur noch „Download (ZIP)“.
    - Die Einträge „Methods“ und „Copy“ aus M4-19a entfallen. Es gibt **nirgends** einen Knopf, der den Methodentext kopiert.
    - Der Methodentext bleibt im ZIP. Er wandert nach M4 als Feld in `recipe.json` (`docs/plans/nach-m4-backlog.md`).
    - Der Link `methods` im Ergebnisdokument der API bleibt bestehen.

## 2. Stand vor der Aufgabe

- **Vorher lesen:** den Stand des Frontends nach M4-13c lesen (Panel, Jobliste „⚙ Jobs (n)“, Batch aus c-4, Layer-Manager nach M4-28, Control-Menü, Kartenschalter).
- **Pläne:** `plans/m4/m4-13-processing-panel.md`, `plans/m4/m4-13c-vorschau-und-viewer.md` und `plans/m4/m4-zusaetze-2026-10-12.md` §2.
- **Keine Konten bis M6.** Ein Job ist nur über seine zufällige `jobID` erreichbar. Eine Liste aller Jobs gibt es absichtlich nicht (`adr/0013`).
- **Ablauf.** Ergebnisse laufen nach 7 Tagen ab (`410`).
- **Wieder starten.** Ein Job lässt sich erst mit M4-19 (Permalinks, „Parameter übernehmen“) wieder starten.
- **Speicher im Browser.** Die Titel der Jobs liegen seit M4-13c-4 im `sessionStorage` und gehen beim Schließen des Tabs verloren.
- **Job-ZIP.** Seit M4-11b-1 streamt `api` das ZIP eines Jobs, mit Fortsetzen über ETag und ZIP64; den Inhalt legt M4-30 an einer Stelle fest.

## 3. Im Plan mit Optionen und Empfehlung klären

1. **Ablage.** Titel, Gruppen, Batch-Zugehörigkeit, der Status „archiviert“ und ein von Hand gesetzter Farbbereich je Job (M4-32b) liegen bis M6 nur im Browser, dauerhaft und nicht mehr im `sessionStorage`. An der API für einzelne Jobs ändert sich nichts.
   - Wie wird gespeichert (Schlüssel, Version des Formats, Übernahme der Titel aus dem `sessionStorage`)?
   - Was passiert in einem privaten Fenster oder bei gelöschten Browserdaten?
   - Der Nutzer erfährt das in einem Satz (Englisch).
2. **Vorgabetitel.** Der Titel wird aus Operator, Datensatz und Datum gebildet, zum Beispiel „NDVI · sentinel-2-c1-l2a · 12 Oct“.
3. **Abgelaufene Jobs.** Sie bleiben mit dem Status „Expired“ sichtbar. Bleibt eine Kopie von `recipe.json` im Browser, damit M4-19 den Job später wieder starten kann? Die AOI bleibt dabei nur im Browser.
4. **„Nicht löschbar“ und laufende Jobs.**
   - Bleibt „Cancel“ für laufende Jobs (OGC `dismiss`), auch für einen ganzen Batch?
   - Ruft das Panel `DELETE` für fertige Jobs gar nicht mehr auf?
5. **Details eines Jobs.** Die Liste zeigt nur Titel, Fortschritt und Ablaufdatum. Wo erscheinen Schritte, Download und Fehlermeldung? Vorschlag: Ein Klick auf den Job öffnet das Processing-Fenster mit diesem Job. Als Aktion gibt es dort nur „Download (ZIP)“, keine Anzeige und kein Kopieren des Methodentexts (§1 Punkt 12).
6. **Leiste und Panels.**
   - Breite, Symbole, Tooltips (Englisch), Tastatur und Screenreader.
   - Was passiert auf schmalen Bildschirmen?
   - Darf mehr als ein Panel gleichzeitig offen sein?
   - Wohin wandert das heutige „⚙ Jobs (n)“?
7. **„Download all (ZIP)“.**
   - **Neue Route:** Nötig ist eine Route in `api`, etwa `POST /processing/bundles`, mit der Liste der `jobID`s im Body (nie in der URL). Sie setzt das ZIP aus den einzelnen Job-ZIPs zusammen und nutzt dabei denselben Code wie M4-11b-1 (Streaming, ZIP64, Inhalt aus der Definition von M4-30). Keine neue Ablage im Objektspeicher.
   - **Grenzen:** höchstens 25 Teile wie beim Batch, Größe und Deckel. Klären, ob 5 GB je Bündel gelten oder eine eigene Grenze.
   - **Fortsetzen:** Ist das fortsetzbar wie das Job-ZIP? Wie entsteht der ETag aus den Teilen?
   - **Datenschutz:** keine `jobID`s und keine AOI in Logs oder URLs.

## 4. Grenzen

- Schwerpunkt Frontend.
- Backend nur für die Bündel-Route aus §3 Punkt 7, mit Wiederverwendung des Codes aus M4-11b-1 und M4-30 und ohne neue Abhängigkeit. Für einzelne Jobs ändert sich an der API nichts.
- Oberflächentexte ausschließlich auf Englisch.
- **Wenig Text (Otto, 24.10.2026):** Erklärungen und Gründe stehen im Tooltip (Hover und Fokus, für Screenreader erreichbar), nicht als Text unter Knöpfen oder Feldern. Sichtbar bleiben Beschriftungen, Werte, Fehlermeldungen mit Handlungsbedarf und Pflichtangaben (Attribution, Lizenz).
- Bestehende Funktionen bleiben erreichbar. Der Plan listet jede verschobene Funktion mit ihrem neuen Ort auf.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests sind grün für:
  - Leiste, Manager, Archiv, Gruppen, Filter, Umbenennen und Neuladen mit gespeicherten Jobs,
  - Batch als ein Eintrag mit Aufklappen und Gesamtfortschritt,
  - „Download all (ZIP)“ mit allen Teilen, mit abgelaufenen bzw. gescheiterten Teilen und über der Grenze,
  - gleiche Breite und feste Knopfpositionen der Layer-Zeilen, auch ohne Download-Knopf,
  - Download eines Ergebnis-Layers, auch im abgelaufenen Zustand,
  - Reihenfolge nach jedem Umsortieren mit allen Layer-Arten; der Test zum Befund aus Punkt 10 scheitert am alten Code,
  - Ansicht und angeheftete Layer stapeln mehrere Überflüge gleich (Punkt 10),
  - Klick auf einen Ergebnis-Layer öffnet die Ansicht für Darstellung (vmin, vmax, Colormap), nicht die Suchergebnisse,
  - ein fertiger Job zeigt nur „Download (ZIP)“; kein „Methods“ und kein „Copy“ irgendwo im Frontend (Gegenprobe gegen den Stand nach M4-19a).
- Alle vier Pflicht-Checks der CI sind grün.
- Im PR liegt eine Prüfanleitung für Otto (Browser und PowerShell).
- Log-Zeilen für Ottos Antworten.
- Vor „fertig“ ist main geholt.

## 6. Plan (24.10.2026, zur Freigabe durch Otto)

Stufe B: Bis zur Freigabe ist kein Produktivcode geändert. Grundlage ist `main` nach #184 (M4 abgenommen, DOC-01 gemergt). Belegstufen wie in `adr/0014`: [P] Code oder Primärquelle gelesen, [M] in der Sitzung gemessen bzw. mit einem Wegwerf-Test nachgestellt (nicht im Repo), [S] Sekundärquelle, [A] eigene Ableitung.

**Kurzfassung.**

- **Rahmen:** Eine 48 px breite Leiste am linken Rand mit drei Symbolen (Control-Menü, Layer-Manager, Processing-Manager). Die Panels docken rechts neben der Leiste an, eines zur Zeit (Frage 3). „☰ Layers (n)“ und „⚙ Jobs (n)“ oben rechts entfallen und wandern in die Leiste. Das Processing-Fenster rechts (Auftrag bauen) bleibt, wo es ist, und zeigt zusätzlich die Details eines Jobs.
- **Processing-Manager:** je Eintrag nur Titel, Fortschritt und Ablaufdatum; Batch als ein Eintrag mit Aufklappen; Archivieren, Gruppen, Filter „Active / All“; kein Löschen mehr (das heutige „✕ Remove this row“ entfällt). Ein Klick öffnet die Details im Processing-Fenster. Einzige Aktion eines fertigen Jobs ist „Download (ZIP)“; „Methods“ und „Copy“ entfallen.
- **Ablage:** ein Schlüssel `earthx.processing.manager` im `localStorage` mit Formatversion 1; die Titel aus dem `sessionStorage` werden einmal übernommen. Ohne nutzbaren Speicher läuft alles für die Sitzung weiter. Der Hinweis steht als Tooltip am Kopf des Managers.
- **Befund Punkt 10 [P][M]:** Drei Ursachen im Code gefunden, an denen eine Änderung der Reihenfolge auf der Karte nichts oder das Falsche bewirkt, dazu eine gewollte Überdeckung durch die Live-Vorschau (§6.2). Welche davon Ottos Befund ist, klären die Schritte, die Otto beim Start liefern wollte (Frage 1). Behebung in `mapLayers.ts`, `viewLayer.ts` und `store.ts`.
- **Stapelung zwischen Überflügen [P]:** Ursache ist der Aufbau der Overlays eines angehefteten Layers (`store.ts::overlaysOfEntries`, dazu `processingStore.ts::pinPreview`). Er wird an die Regel der Ansicht angeglichen: Der zuerst gewählte Überflug bzw. die zuerst gewählte Szene liegt oben.
- **Layer-Manager:** feste Spalten im Raster (CSS-Grid), ein fehlender Knopf lässt seinen Platz leer; Hinweise als Symbol mit Tooltip statt Zeile darunter. Ergebnis-Layer bekommen „Download (ZIP)“ (gesperrt mit Grund, wenn abgelaufen) und beim Klick eine Darstellung mit vmin, vmax, Colormap und Deckkraft, Vorgabe aus der Statistik (M4-32), ohne Einheit.
- **„Download all (ZIP)“:** neue Route `POST /processing/bundles` in `api`, Liste der `jobID`s im Body, dasselbe `Layout` wie `result.zip` (M4-11b-1) und dieselben Hinweisdateien (M4-30). Fehlende Teile stehen in `MISSING.txt`. Grenzen: höchstens 25 Teile, eigene Größengrenze (Frage 7). Nicht fortsetzbar, weil `Range` nur für `GET` definiert ist; die Teile bleiben einzeln fortsetzbar (Frage 8).
- **Schnitt:** fünf PRs UI-01a bis UI-01e, je unter etwa 400 Zeilen (§6.14).
- **Fragen an Otto:** 13, je mit Empfehlung (§6.13).

### 6.1 Stand vor der Aufgabe [P]

| Was | Wo heute | Bemerkung |
|---|---|---|
| Control-Menü | `App.tsx` `.panel-dock` oben links, eingeklappt über `‹`/`›` (`togglePanel`) | Suche, AOI, Datensätze |
| Layer-Manager | `LayerManager.tsx` in einem `Draggable`, frei schwebend; geöffnet über „☰ Layers (n)“ oben rechts; öffnet sich selbst bei jedem „Add to layers“ (`layerManagerOpen: true`) | Zeile `display: flex`, Knöpfe fallen weg statt Platz zu lassen; Hinweise als eigene Zeile (`lm-note`) |
| Jobliste | `JobList.tsx` in einem `Draggable` (`.jobs-dock`); „⚙ Jobs (n)“ oben rechts, nur wenn es Jobs gibt und die Liste zu ist; „Start job“ öffnet sie | `JobRow` zeigt Zustand, „Cancel“ bzw. „✕ Remove this row“, Fortschritt, „Kept until“, „Add to layers“, Links (ZIP und „Methods“ mit „Copy“), „Resampled …“, Fehler |
| `JobRow` woanders | `ExportJobOffer.tsx` (Export im Download-Dialog), `MosaicJobs.tsx` (Mosaik-Jobs im Download-Dialog) | dieselbe Zeile |
| Jobs eines Batches | `processingStore.ts::startBatch`: je Teil ein eigener Eintrag mit Titel „… · i/n“; abgewiesene Teile nur als `batchStartRefusals` im Panel | keine Batch-Kennung |
| Ablage | `jobTracker.ts`: `sessionStorage` `earthx.processing.jobs`, je Job `jobID`, `expires`, `title` (≤ 200 Zeichen), abgelaufene werden beim Laden verworfen | Handbereich (`JobEntry.range`) geht beim Neuladen verloren |
| Ergebnis als Layer | `showResultOnMap` (M4-13c-5) aus der Jobliste („Add to layers“) | Darstellung nach `resultLayer.ts::resultRender` (M4-32b) |
| Klick auf Layer-Namen | `store.ts::selectLayer` | Ergebnis-Layer: `restore.focusMode = false`, `selectedIds = []` → es erscheinen die Suchergebnisse (Punkt 11 „Heute“) |
| Processing-Knopf am Ergebnis | `layerProcessBlock`: „A result cannot be processed further yet.“ | bleibt (Punkt 11) |
| „Share“ | `ShareLink.tsx` im Panel, für den Entwurf, nicht für einen Job; bei Stapeln gesperrt („A link holds one order: choose “One job”.“) | M4-19e, Otto 24.10.2026 |

### 6.2 Befund Punkt 10: Reihenfolge greift nicht (Diagnose)

Otto hat beim Start keine Schritte geliefert (Frage 1). Die Diagnose am Code findet drei Stellen, an denen ein Umsortieren auf der Karte nichts oder das Falsche bewirkt (H1–H3), und eine gewollte Überdeckung (H4). `syncLayers`, `restack` und die IDs aus M4-28 sind dabei in Ordnung: Ein Wegwerf-Test mit `fixtures/liveMap.ts` legt nach jedem Verschieben die Liste in der richtigen Reihenfolge auf die Karte [M].

**H1 — Die Ansicht liegt über den Layern und zeigt oft dasselbe Bild wie einer von ihnen [P].** Seit M4-28 liegt die offene Ansicht immer über allen angehefteten Layern (`mapLayers.ts::beforeAoi`, `LAYERS_TOP`). Nur wenn die Ansicht genau ein angehefteter Layer ist, zeichnet der Layer sie (`viewLayer.ts::viewLayerOf`). Das gilt aber nur für die Vollauflösung und nur nach einem Klick auf den Namen (`viewLayerId`). Drei häufige Fälle sind nicht erfasst:
- **(a) „Add to layers“ aus der Vollauflösung:** `addCurrentToLayers` setzt `viewLayerId` nicht (M4-28 §6.5, „Nicht umgesetzt“). Die Ansicht bleibt als Kopie des neuen Layers obenauf. Verschiebt man diesen Layer nach unten, ändert sich auf der Karte nichts.
- **(b) Browse-Modus:** Die Quicklooks der aufgeklappten Gruppe (`syncBrowseMosaic`) liegen über allen Layern. Wer zwei Zeitschritte nacheinander anheftet, sieht oben immer den aufgeklappten, egal wie die Liste steht.
- **(c) Quicklook-Unterlage unter der freigegebenen Stufe:** `syncFocusRaster` setzt die Unterlage (`addQuicklookUnderlay`) auch dann, wenn der Layer die Ansicht zeichnet (`tilesInLayer`), und zwar über `LAYERS_TOP`. Beim Herauszoomen unter `min_zoom` (Sentinel-2: z8) deckt sie alle Layer zu; dort wirkt kein Umsortieren.

**H2 — Das Budget von 200 Overlays zählt von unten [P][M].** `wantedOverlaysOf` geht die Liste von unten nach oben durch und hört bei `MAX_LAYER_OVERLAYS` (200) auf. Wird es knapp, verliert also der **oberste** Layer seine Overlays, und bei einem Mosaik zuerst das Mosaik selbst, denn es ist das letzte Overlay (`mosaic.ts::viewOfPass`). Nachgestellt mit vier Layern zu je 65 Overlays (ein Überflug mit 64 Szenen): Der oberste Layer behält 5 von 65 Overlays. Schiebt man ihn nach unten, ist er vollständig, und nun verliert der neue oberste Layer seine Overlays [M]. Auf der Karte erscheint der Layer, den man nach oben schiebt, nicht oben.

**H3 — Stapelung innerhalb eines Layers (siehe §6.3) [P].** Hat ein Layer mehrere Überflüge oder Einzelszenen, liegt darin eine andere Szene oben als in der Ansicht. Klickt man auf den Namen, wechselt die Ansicht zu diesem Layer, und an Überlappungen ist ein anderes Bild zu sehen, ohne dass sich die Reihenfolge geändert hätte.

**H4 — Live-Vorschau des Panels [P].** Solange das Panel offen ist, liegt die Vorschau über allem (`PREVIEW_LYR`, M4-13c-2). Das ist gewollt und wird nicht geändert. Im Prüffall wird das Panel deshalb geschlossen.

**Behebung (Vorschlag, Frage 12):**
- **Zu H1 (eine Regel in der gemeinsamen Logik):** Was ein angehefteter, sichtbarer Layer schon zeichnet, zeichnet die Ansicht nicht noch einmal obendrauf. „Dasselbe“ heißt dieselbe Signatur des Overlays (`overlaySignature`: Kachel-URL, Grenzen, Stufen bzw. Bild-URL, Ecken, Freistellung). So hat es M4-28 §6.5 Nr. 1 schon für die Such-Zuschnitte gemacht.
  - Damit sind (a) und (b) erfasst; (a) zusätzlich, indem `addCurrentToLayers` bei genau einem neuen Layer `viewLayerId` setzt.
  - Die Unterlage (c) gehört zu den Kacheln ihrer Szene: Sie wird nur gezeichnet, wo die Ansicht die Kacheln selbst zeichnet.
  - Ein ausgeblendeter Layer zeichnet nichts. Dann zeichnet die Ansicht wieder selbst, wie heute.
- **Zu H2:** Das Budget zählt von oben. Die Layer oben in der Liste, also oben auf der Karte, sind immer vollständig. Wird gekürzt, nennt eine Meldung die Zahl der nicht gezeichneten Bilder, in Anlehnung an `mosaic.ts::oversizeNote`.
- **Zu H3:** §6.3.
- **Test zuerst:** Je Ursache ein Fall, der am Code vor UI-01 scheitert; Gegenprobe im PR. Dazu eine Matrix in `mapLayers.test.ts`: fünf Layer, einer je Art (Quicklook, Vollauflösung, angeheftete Vorschau, Ergebnis, Mosaik aus M4-17). Nach jedem Verschieben (oben, mitte, unten, ganz nach oben, ganz nach unten) entspricht die Reihenfolge der Layer auf der Karte der Liste, jeweils mit Ansicht im Browse-Modus, mit Vollauflösung und mit einer Ansicht, die ein Layer ist.
- **Ottos Schritte (Frage 1):** Sie kommen als eigener Testfall dazu. Passt keine der Ursachen H1–H3, wird weiter gesucht, bevor UI-01a als fertig gilt.

### 6.3 Stapelung zwischen Überflügen (Punkt 10, 22.10.2026) [P]

- **Ansicht:** `syncFocusRaster` zeichnet die Überflüge und darin die Szenen in umgekehrter Auswahlreihenfolge. Der **zuerst** gewählte Überflug bzw. die zuerst gewählte Szene liegt oben („first valid pixel wins“, M3-09).
- **Angehefteter Layer:** `store.ts::overlaysOfEntries` hängt die Überflüge in Auswahlreihenfolge an, und `wantedOverlaysOf` legt die Overlays eines Layers von unten nach oben. Oben liegt also der **zuletzt** gewählte Überflug.
- **Gleicher Fehler bei der Vorschau:** `syncPreview` legt die erste Szene oben, `pinPreview` übernimmt `previewOverlays` unverändert, also liegt im angehefteten Vorschau-Layer die letzte oben.
- **Behebung:**
  - Die Overlays eines Layers bleiben „von unten nach oben“ (so lesen sie `wantedOverlaysOf` und die Mosaik-Planung).
  - Beide Erzeuger bauen sie in derselben Reihenfolge, in der die Ansicht zeichnet. Dafür kommt eine Funktion `stackLikeView` nach `mosaic.ts`, die `syncFocusRaster`, `overlaysOfEntries` und `pinPreview` gemeinsam nutzen.
  - Innerhalb eines Mosaiks ändert sich nichts: Dort sortiert schon der Server, und die Einzelszenen darunter liegen nach `earthx:order`.
- **Nicht geändert:** Im Browse-Modus liegt die zuletzt gewählte Szene oben, bei Ansicht und Layer gleich. Das bleibt so; es folgt aus M3-09, das nur die Vollauflösung betraf.
- **Test (scheitert am alten Code):** zwei Überflüge mit Überlappung, dazu zwei Einzelszenen ohne Mosaik. Ansicht und angehefteter Layer legen dieselben Kachel-URLs in derselben Reihenfolge auf die Karte, auch nach Klick auf den Namen. Derselbe Fall für eine angeheftete Vorschau.
- **Folge:** Die Zeile im Log vom 22.10.2026 („Angeheftete Layer stapeln Einzelszenen anders als die Ansicht“) wird mit UI-01a geschlossen.

### 6.4 Ablage im Browser (§3 Punkt 1)

**Format (Vorschlag):** ein Schlüssel im `localStorage`, ein JSON-Objekt:

```text
earthx.processing.manager = {
  "v": 1,
  "jobs":    [{ "jobID", "expires", "title", "createdAt", "archived", "groupId"?, "batchId"?, "part"?, "range"?, "order"? }],
  "batches": [{ "id", "title", "createdAt", "archived", "groupId"?, "refused": [{ "label", "message" }] }],
  "groups":  [{ "id", "name" }]
}
```

- **Felder:**
  - `title` ≤ 200 Zeichen, wie heute.
  - `part` ist die Beschriftung des Teils im Batch (Überflug bzw. Szenen-ID, `BatchUnit.label`).
  - `range` ist der Handbereich aus M4-32b, dazu ein im Layer-Manager gesetzter Bereich (§6.8).
  - `order` ist die Kopie des Auftrags (§6.6, Frage 4).
  - Ein archivierter Batch archiviert alle seine Teile.
  - IDs von Batches und Gruppen erzeugt der Browser zufällig (`crypto.randomUUID`); sie verlassen den Browser nie.
- **Version:**
  - Ein Format mit unbekanntem `v` wird nicht überschrieben. Der Manager arbeitet dann nur im Speicher und sagt es mit derselben Meldung wie ohne Speicher.
  - Ein neueres Format kommt mit eigener Übernahme.
  - Fehlerhafte Einträge werden wie heute einzeln verworfen.
- **Übernahme:** Beim ersten Start mit UI-01 wird `earthx.processing.jobs` aus dem `sessionStorage` dieses Tabs übernommen (`jobID`, `expires`, `title`) und dort entfernt. Ein Job, der schon im `localStorage` steht, wird nicht doppelt angelegt.
- **Mehrere Tabs:** Der Speicher gilt jetzt für alle Tabs eines Browsers. Das Ereignis `storage` gleicht die anderen Tabs ab. Jede Änderung liest vor dem Schreiben neu; bei gleichzeitiger Änderung desselben Eintrags gilt die letzte.
- **Verfolgen:** Auch ein Job aus einem anderen Tab wird verfolgt (SSE bzw. Abfrage, `jobTracker.ts` unverändert), aber nur, solange er läuft und sein Manager offen ist oder er zu einem offenen Batch gehört. Sonst wären bei 25 Teilen in mehreren Tabs 25 Ströme je Tab offen (`503` bei zu vielen Verfolgern).
- **Dauer:** Einträge bleiben, auch abgelaufene (§6.6). Nur die Auftragskopien werden bei Platzmangel verdrängt, die ältesten zuerst. Ein Eintrag ohne Kopie bleibt sichtbar. Grobe Rechnung [A]: ein Eintrag ohne Kopie etwa 300 B, also 10 000 Jobs etwa 3 MB.
- **Privates Fenster, gelöschte Daten, gesperrter Speicher:**
  - Im privaten Fenster gilt der Speicher bis zum Schließen.
  - Nach dem Löschen der Browserdaten sind Titel, Gruppen und Archiv weg. Die Jobs selbst laufen auf dem Server weiter, sind aber ohne `jobID` nicht mehr erreichbar (`adr/0013`, keine Liste).
  - Bei gesperrtem Speicher (`getItem` wirft) arbeitet der Manager nur im Speicher.
- **Satz für den Nutzer (Tooltip am ⓘ im Kopf des Managers):** „Jobs are kept in this browser only: a private window or clearing the browser's data loses them.“
- **Ohne Speicher (sichtbar, weil Handlung nötig):** „This browser does not keep your jobs. Download results before you close the tab.“
- **API:** An der API für einzelne Jobs ändert sich nichts.

### 6.5 Vorgabetitel (§3 Punkt 2)

- **Vorschlag (Frage 5):** `<Operatoren> · <Datensatz-ID> · <Tag>`, also „Band math · sentinel-2-c1-l2a · 12 Oct“.
  - Operatoren als Titel aus der Prozessbeschreibung, wie heute (`jobTitle`).
  - Der Datensatz als ID wie in Ottos Beispiel; heute steht dort der Titel.
  - Der Tag ist der Aufnahmetag, wenn die Szenen des Auftrags einen gemeinsamen haben, sonst der Starttag. Das ist dieselbe Regel wie im Dateinamen der Downloads (`_day_of_name`, Otto 14.10.2026). Format `d MMM` in Englisch, mit Jahr nur, wenn es nicht das laufende ist.
- **„NDVI“:** Ein Name wie „NDVI“ setzt eine Zuordnung von Ausdruck zu Index voraus. Die gibt es nicht; sie gehört zu den Index-Knöpfen aus dem Backlog (Punkt 10). Bis dahin steht dort der Operator.
- **Batch:** Der Eintrag trägt den Titel ohne Zusatz; die Teile zeigen beim Aufklappen ihre Beschriftung (Überflug bzw. Szene). Das heutige „· 3/25“ entfällt im Titel.
- **Jobs aus dem Download-Dialog:**
  - Export: „Export · <Datensatz-ID> · <Tag>“.
  - Mosaik: „Mosaic · <Datensatz-ID> · <Tag>“.
  - Heute haben beide keinen Titel.
- **Umbenennen:** im Detailfenster und über das Menü der Zeile. Ein leerer Titel stellt die Vorgabe wieder her.

### 6.6 Abgelaufene Jobs und Kopie des Auftrags (§3 Punkt 3)

- **Anzeige:** Ein Job bleibt nach dem Ablauf mit Status „Expired“ in der Liste; sein Ablaufdatum steht weiter da.
- **„Gone“:** `404`, also abgelaufen, aufgeräumt oder abgebrochen, erscheint als „Expired“ bzw. „Cancelled“. Nach dem Ablauf wird nicht mehr nachgefragt.
- **Kopie des Auftrags (Frage 4):** Beim Start legt der Browser den gesendeten Auftrag (`Order`, kanonisches JSON) zum Job. Damit kann der Job später wieder geöffnet werden, über den vorhandenen Weg `processingStore.restoreOrder` (M4-19e) mit „Open in panel“ in den Details.
  - Die AOI bleibt dabei im Browser.
  - Bis 64 KB je Auftrag. Ein größerer, also eine sehr feine AOI, wird nicht kopiert; die Details sagen das im Tooltip.
  - `recipe.json` selbst wird nicht kopiert. Es ist größer, und `draftFromOrder` braucht den Auftrag.

### 6.7 Nicht löschbar, „Cancel“ (§3 Punkt 4)

- **„Cancel“ bleibt** für laufende und wartende Jobs (OGC `dismiss`, `DELETE /processing/jobs/{jobID}`).
  - **Batch (Frage 10):** „Cancel all“ am Eintrag bricht alle laufenden Teile ab, einzeln nacheinander; „Cancel“ gibt es auch je Teil.
  - Ein abgebrochener Job bleibt als „Cancelled“ in der Liste.
- **Kein `DELETE` für fertige Jobs:** Das Panel ruft `DELETE` nur für einen Job auf, dessen zuletzt bekannter Status `accepted` oder `running` ist (Wächter in `cancelJob`, nicht nur am Knopf).
  - **Bekannte Grenze [A]:** Endet der Job zwischen dem letzten Status und dem Eintreffen des `DELETE`, verwirft der Server das fertige Ergebnis. Ohne Änderung der API ist das nicht zu verhindern; das Fenster ist eine Abfragezeit (2 s) bzw. ein SSE-Ereignis.
- **Entfällt:** `removeJob` und „✕ Remove this row“. Die Dialoge für Export und Mosaik zeigen ihre Jobs weiter, aber ohne Entfernen.

### 6.8 Details eines Jobs (§3 Punkt 5, §1 Punkt 12)

- **Ort:** Ein Klick auf einen Job im Manager öffnet das Processing-Fenster (rechts) im Modus „Job“. Kopf: „‹ Order“ zurück zum Entwurf. Der Entwurf bleibt dabei unverändert.
- **Inhalt:**
  - Titel (umbenennbar), Zustand mit Fortschritt, Ablaufdatum.
  - Die Schritte aus der Kopie des Auftrags (Operator und Werte, ohne AOI-Koordinaten).
  - Die Fehlermeldung eines gescheiterten Jobs (K8, unverändert).
  - „Resampled to a common grid“ als Symbol mit Tooltip; sichtbar wegen Prinzip 2.9.
- **Aktionen:**
  - Fertig: nur „Download (ZIP)“ (`result.zip` bzw. `export.zip`).
  - Laufend: „Cancel“.
  - Abgelaufen, mit Kopie: „Open in panel“ (Frage 4).
- **„Add to layers“:** Es ist keine Datei, entfällt aber aus der Liste. Wo es bleibt, entscheidet Frage 2. Vorschlag: in den Details als „Show on map“, neben „Download (ZIP)“.
- **Entfällt im ganzen Frontend:** „Methods“, `CopyMethods`, `fetchMethodsText`, `METHODS_FILE`, die Einzel-Links aus der Zeit vor den ZIPs (`resultFiles` ohne Archiv). Alle Ergebnisse von vor M4-11b-1 (15.10.2026) sind abgelaufen.
  - **Gegenprobe:** Ein Test durchsucht den gerenderten Manager und das Detailfenster nach „Methods“ und „Copy“.
  - `CopyButton` bleibt für „Copy link“ unter „Share“ und für die Suchergebnisse; dieser Knopf kopiert keinen Methodentext.
  - Der Link `methods` der API bleibt.

### 6.9 Leiste und Panels (§3 Punkt 6)

- **Leiste:** `nav` mit `aria-label="Main"`, 48 px breit, volle Höhe, am linken Rand, im Stil der HUD-Tafeln. Drei Knöpfe mit Symbol als Inline-SVG (keine neue Abhängigkeit):

  | Knopf | Tooltip und `aria-label` | Badge |
  |---|---|---|
  | Control-Menü | „Search and area“ | – |
  | Layer-Manager | „Layers“ | Zahl der Layer |
  | Processing-Manager | „Processing jobs“ | Zahl der laufenden Jobs |

- **Tastatur:**
  - Die Knöpfe tragen `aria-expanded` und `aria-controls`.
  - Tab erreicht sie der Reihe nach; Pfeiltasten wechseln innerhalb der Leiste (Roving Tabindex).
  - `Esc` schließt das offene Panel und gibt den Fokus an seinen Knopf zurück.
  - Der Badge geht in den Namen ein („Layers, 3“).
- **Panels:**
  - Breite 340 px, volle Höhe neben der Leiste, nicht verschiebbar. `Draggable` entfällt für Layer-Manager und Jobliste.
  - Ein Panel zur Zeit (Frage 3). Ein zweiter Klick auf das offene Symbol schließt es.
  - Beim Start ist das Control-Menü offen, wie heute.
  - „Add to layers“ öffnet den Layer-Manager nicht mehr von selbst; der Badge zählt hoch. Sonst würde das Control-Menü zugehen.
  - „Start job“ öffnet den Processing-Manager nicht; der Badge zeigt den neuen Job. Bei einem Panel zur Zeit bleibt das Processing-Fenster sichtbar.
- **Schmale Bildschirme (< 900 px, wie heute beim Processing-Fenster):** Die Leiste bleibt. Ein Panel liegt über der Karte bis zum rechten Rand. Das Processing-Fenster bleibt das Blatt von unten (60 vh).
- **Verschobene Funktionen:**

  | Funktion | Heute | Neu |
  |---|---|---|
  | Control-Menü ein/aus | `‹`/`›` am Rand des Panels | Symbol in der Leiste; `‹`/`›` entfällt |
  | Layer-Manager öffnen | „☰ Layers (n)“ oben rechts | Symbol in der Leiste mit Badge |
  | Jobliste öffnen | „⚙ Jobs (n)“ oben rechts; „Start job“ öffnet sie | Symbol in der Leiste mit Badge |
  | Job-Details, Download, Fehler | Zeile der Jobliste | Detailfenster im Processing-Fenster; Download zusätzlich als Symbol in der Zeile |
  | „Add to layers“ eines Ergebnisses | Zeile der Jobliste | Frage 2 |
  | „✕ Remove this row“ | Zeile der Jobliste | entfällt (nicht löschbar) |
  | „Methods“, „Copy“ | Zeile der Jobliste | entfällt (Punkt 12) |
  | „Zoom to selection“, „Globe/Mercator“, „Light/Dark“ | oben rechts | bleiben dort; Basemap und Projektion kommen mit UI-02 |

### 6.10 Processing-Manager (Punkte 3–6)

- **Zeile:** Titel, Fortschritt als Balken mit Prozent bzw. als Zustand („Waiting“, „Finished“, „Failed“, „Cancelled“, „Expired“), Ablaufdatum („until 31 Oct, 14:02“).
  - Bei einem fertigen Job dazu das Symbol „Download (ZIP)“ an fester Stelle.
  - Ein Menü „⋯“ mit „Rename“, „Move to group…“, „Archive“ bzw. „Unarchive“, bei laufenden Jobs „Cancel“.
  - Die Zeile selbst ist ein Knopf zu den Details.
- **Batch:** eine Zeile mit gemeinsamem Titel und Gesamtfortschritt als Zähler, etwa „12 done · 3 running · 1 refused · 1 failed“. Ablaufdatum ist das früheste der Teile. Dazu „Download all (ZIP)“ (§6.12) und ein Pfeil zum Aufklappen.
  - Aufgeklappt: die Teile als eigene Zeilen, eingerückt, mit Beschriftung, Fortschritt und Download.
  - Abgewiesene Teile ohne `jobID` stehen dort mit Grund im Tooltip.
- **Gruppen:**
  - Abschnitte mit Überschrift, „Ungrouped“ zuerst, dann in der Reihenfolge des Anlegens.
  - „New group“ im Kopf; „Rename“ an der Überschrift.
  - Zuordnen über „Move to group…“, für Jobs und ganze Batches; ein Teil folgt seinem Batch.
  - Eine leere Gruppe darf entfernt werden (Frage 9). Das ist kein Löschen von Jobs.
- **Filter:** ein Schalter „Active / All“ im Kopf. „Active“ zeigt alle nicht archivierten Einträge, also auch fertige, gescheiterte und abgelaufene; „All“ zeigt dazu die archivierten, gekennzeichnet. Der Filter wird gespeichert.
- **Sortierung:** neueste zuerst, innerhalb jeder Gruppe.
- **Leere Liste:** „No jobs yet.“

### 6.11 Layer-Manager (Punkte 2, 8, 9, 11)

- **Ort:** fest neben der Leiste (§6.9).
- **Zeile als Raster mit festen Spalten:** Auge, Name (Rest, mit Auslassungspunkten, voller Name im Tooltip), Deckkraft, ▲, ▼, ⚙, ⇩, Hinweis, ✕. Jede Spalte hat feste Breite. Fehlt ein Knopf, steht dort ein leeres Feld gleicher Größe (`aria-hidden`), etwa ⇩ bei Vorschau-Layern.
  - Hinweise („Expired“, „Resampled to a common grid“) werden ein Symbol ⚠ in der Spalte „Hinweis“ mit Tooltip. Die Zeilenhöhe bleibt gleich.
  - Test: Alle Zeilen haben dieselbe Spaltenvorlage, und die Spalte jedes Knopfes ist dieselbe, mit und ohne ⇩ (Prüfung der Klassen in jsdom und, in der Prüfanleitung, der Pixel im Browser).
- **Download eines Ergebnis-Layers (Punkt 9):** ⇩ ist ein Link auf das Job-ZIP (`/processing/jobs/{jobID}/results/result.zip`), dieselbe Adresse wie in den Details.
  - Ist das Ergebnis abgelaufen, ist der Knopf gesperrt mit Tooltip „Expired: results are kept for 7 days.“
  - Kein zweiter Weg: Der Layer kennt seine `jobID` (`ResultLayerInfo`).
- **Klick auf einen Ergebnis-Layer (Punkt 11):** öffnet unten die Darstellung „RESULT · <Titel>“, an derselben Stelle wie `ViewerControls`.
  - Inhalt: Colormap, vmin, vmax, „Auto“ (zurück zur Vorgabe aus der Statistik, `resultRender` ohne Handbereich), Deckkraft, „Apply“.
  - Die Suchergebnisse klappen zu wie in der Vollauflösung. Der Layer bleibt an seinem Platz in der Liste.
  - „Apply“ baut die Kachel-URL des Layers neu. Die Quelle wird dabei neu angelegt, weil sich die Signatur ändert; das passiert nur bei „Apply“.
  - Der Bereich wird je Job gespeichert (§6.4) und gilt für jeden späteren Layer desselben Jobs.
  - Neu ist `store.resultViewLayerId`; `focusMode` bleibt aus.
  - **Keine Einheit,** weder in Zeilen noch in der Darstellung, bei keiner Art von Layer. Ein Test prüft, dass keine Einheit (`bands[].unit`) im Layer-Manager und in der Darstellung erscheint.
- **Processing-Knopf am Ergebnis-Layer:** bleibt gesperrt; der Grund steht im Tooltip (heute schon so).

### 6.12 „Download all (ZIP)“ (§3 Punkt 7)

- **Route:** `POST /processing/bundles` in `api`, im Modul `api/processing_route.py` neben `result.zip`.
  - **Body:** `jobs=<id>,<id>,…` als `application/x-www-form-urlencoded`. Der Browser schickt es als verstecktes Formular und speichert die Antwort selbst, ohne das ZIP im Speicher zu halten. Gelesen wird der Body mit `urllib.parse`, ohne `python-multipart`, also ohne neue Abhängigkeit.
  - **Prüfungen:** Grenze `MAX_BODY_BYTES`; 1 bis 25 `jobID`s, jede in der Form einer `jobID`, keine doppelt; sonst `422`.
  - Die Liste steht nie in der URL.
- **Inhalt:**
  - `<Name>/NN_<Stamm des Teils>/…`: je Teil der Inhalt seines `result.zip`. Es sind dieselben `Member`s, gebaut von derselben Funktion, die aus `_bundle_response` herausgezogen wird (Rasterdateien aus dem Speicher plus `TEXT_FILES` aus M4-30). Bei einem Export ist es der Inhalt von `export.zip` als ein Eintrag.
  - `NN` ist die Stelle in der Liste (01–25). Das trennt Teile mit gleichem Stamm, etwa „One job per scene“ am selben Tag.
  - **`MISSING.txt`:** eine Zeile je fehlendem Teil, „NN <Stamm>: expired“, „…: failed“, „…: not finished“ bzw. „NN: no longer available“ (keine Zeile mehr in der Datenbank). Fehlt nichts, gibt es die Datei nicht.
  - **Name des ZIPs:** `<Stamm des ersten Teils>_batch-<n>.zip`, ohne `jobID`, AOI oder Hash (`_download_name`).
  - Ist kein Teil vorhanden: `410` (alle abgelaufen) bzw. `409`, kein leeres ZIP.
- **Grenzen:** 25 Teile; die Größengrenze nach Frage 7, sonst `413` mit der Summe. Das Frontend sperrt den Knopf vorher mit Grund, sofern die Größen bekannt sind (`length` im Ergebnisdokument). Das Bündel nimmt einen Platz aus `DownloadSlots` (vier ZIPs je Prozess), sonst `503` mit `Retry-After`.
- **ETag:** `Layout.etag` über alle Einträge (Namen, Größen, CRC, Zeitstempel, `FORMAT`); `MISSING.txt` ist ein Eintrag wie jeder andere. Der Zeitstempel ist das späteste Ende der Teile. Gleiche Teile in gleichem Zustand ergeben dieselben Bytes.
- **Fortsetzen:** nach Frage 8.
- **Datenschutz:**
  - Keine `jobID`, keine AOI und keine Liste in Logs oder URL. Die Warnungen aus `_archive_bytes` tragen keine `jobID`, wie heute.
  - Ein Test prüft die Log-Zeilen (`caplog`) auf `jobID`s.
  - Keine neue Ablage im Objektspeicher.
- **Doku:** Nachtrag in `adr/0015` (neue Route, Grenze, Fortsetzen); Zeile im Log.

### 6.13 Fragen an Otto

**Frage 1 – Schritte zum Befund Punkt 10.**
1. **Otto schickt die Schritte; UI-01a behebt H1–H3 und nimmt die Schritte als Test auf (Empfehlung).**
2. Ohne Schritte: H1–H3 beheben und den Befund mit der Prüfanleitung von UI-01a gegenprüfen.

**Frage 2 – Wo bleibt „Add to layers“ eines Ergebnisses?**
1. **In den Details als „Show on map“, neben „Download (ZIP)“; in der Liste nur der Download (Empfehlung).** „Nur Download (ZIP)“ betrifft die Dateien.
2. Ein fertiges Raster-Ergebnis erscheint von selbst als Layer, ausgeblendet.
3. Auch in der Zeile, als zweites Symbol.

**Frage 3 – Mehrere Panels gleichzeitig?**
1. **Eines zur Zeit links (Empfehlung).** Übersichtlich, die Karte bleibt frei, gleiches Verhalten auf schmalen Bildschirmen.
2. Control-Menü und ein Manager nebeneinander (zusammen etwa 730 px).

**Frage 4 – Kopie des Auftrags und Wiederstart.**
1. **Kopie bis 64 KB; „Open in panel“ in den Details abgelaufener Jobs (Empfehlung).**
2. Kopie ja, Knopf erst in einer späteren Aufgabe.
3. Keine Kopie.

**Frage 5 – Vorgabetitel.**
1. **„Band math · sentinel-2-c1-l2a · 12 Oct“: Operator-Titel, Datensatz-ID, Aufnahmetag, sonst Starttag (Empfehlung).**
2. Wie 1, aber mit Datensatz-Titel („Sentinel-2 L2A“) wie heute.

**Frage 6 – „Share“ für einen Batch.**
1. **Sperre bleibt, Grund im Tooltip (Empfehlung).** Ein Permalink hält heute einen Auftrag (M4-19e). Mehrere Aufträge brauchen Tabelle, Routen und `adr/0015` F13 neu; das liegt außerhalb der Grenze aus §4 (Backend nur für die Bündel-Route).
2. Ein Link für den ganzen Batch: ein Auftrag mit allen Szenen plus „Run as“ in der Ansicht, eigene Aufgabe danach.

**Frage 7 – Größengrenze des Bündels.** Ein Job darf bis 5 GB schreiben (`MAX_JOB_BYTES`); 25 Teile ergeben bis zu 125 GB.
1. **Eigene Grenze 25 GB je Bündel, als Startwert [A] (Empfehlung).** 25 ganze Szenen NDVI (`float32`, 10980², etwa 0,5 GB je Teil) passen. Ein Bündel belegt einen der vier ZIP-Plätze, solange es lädt.
2. 5 GB wie ein Job. Viele Batches mit ganzen Szenen gingen dann nicht als ein ZIP.
3. Keine eigene Grenze (bis 125 GB).

**Frage 8 – Fortsetzen.**
1. **Nicht fortsetzbar: `POST` als Formular, der Browser lädt direkt auf die Platte; jeder Teil bleibt einzeln fortsetzbar (Empfehlung).** `Range` ist nur für `GET` definiert (RFC 9110 §14.2 [S], die Quelle war in der Sitzung nicht erreichbar). Der ETag wird trotzdem gesetzt.
2. Fortsetzbar: `POST` legt einen kurzlebigen Bündel-Eintrag mit zufälliger ID in der Datenbank an (kein Objektspeicher), dann `GET /processing/bundles/{id}` mit `Range` und `If-Range`. Kostet Tabelle, Migration und Aufräumer.

**Frage 9 – Gruppen entfernen.**
1. **Nur leere Gruppen dürfen entfernt werden (Empfehlung).**
2. Gruppen bleiben immer.

**Frage 10 – „Cancel“ bei einem Batch.**
1. **„Cancel all“ am Eintrag und „Cancel“ je Teil (Empfehlung).**
2. Nur je Teil.

**Frage 11 – Schnitt in fünf PRs (§6.14).**
1. **Wie vorgeschlagen, a bis e nacheinander (Empfehlung).**
2. Weniger, größere PRs mit Begründung der Größe.

**Frage 12 – Ansicht über den Layern (Änderung an M4-28).**
1. **Was ein sichtbarer Layer schon zeichnet (gleiche Signatur), zeichnet die Ansicht nicht noch einmal; die Unterlage nur, wo die Ansicht selbst zeichnet (Empfehlung).**
2. Nur „Add to layers“ setzt `viewLayerId`. Kleiner, deckt aber Browse-Modus und Unterlage nicht ab.

**Frage 13 – Backlog-Punkte 9 und 22 in UI-01?**
1. **Nicht aufnehmen. Die Regel „wenig Text“ gilt für alles, was UI-01 neu baut (Empfehlung).**
2. Punkt 22 (Durchgang durch alle Texte) mit aufnehmen.

### 6.14 Umsetzung nach Freigabe

Schnitt (Frage 11). Jeder Teil ist ein eigener Draft-PR von `main`, in neuer Session, nach dem Merge des vorigen.

| PR | Inhalt | Dateien (Schwerpunkt) |
|---|---|---|
| **UI-01a** | Punkt 10: H1–H3, Stapelung §6.3, Budget von oben; Matrix-Test, Gegenprobe | `mapLayers.ts`, `viewLayer.ts`, `mosaic.ts`, `store.ts`, `processingStore.ts::pinPreview`, Tests |
| **UI-01b** | Ablage §6.4 (neues Modul `jobShelf.ts`), Übernahme, Batch-Kennung in `startBatch`, abgewiesene Teile, Vorgabetitel §6.5, Wächter für `DELETE`, `removeJob` raus | `jobTracker.ts`, `processingStore.ts`, `processingBatch.ts`, Tests |
| **UI-01c** | Leiste, Panels, Processing-Manager (Gruppen, Archiv, Filter, Batch), Details im Processing-Fenster; „Methods“/„Copy“ raus | `App.tsx`, neue `AppRail.tsx`, `ProcessingManager.tsx`, `JobDetails.tsx`, `JobList.tsx` (raus), `index.css` |
| **UI-01d** | Layer-Manager: Raster, Download des Ergebnis-Layers, Darstellung des Ergebnisses, Handbereich je Job | `LayerManager.tsx`, neue `ResultControls.tsx`, `store.ts`, `resultLayer.ts` |
| **UI-01e** | Bündel-Route mit Tests (alle Teile, abgelaufene und gescheiterte, über der Grenze, 26 Teile, doppelte, fremde Form, Logs), Nachtrag `adr/0015`; Frontend „Download all (ZIP)“ | `api/processing_route.py`, `api/result_zip.py` (unverändert oder kleine Hilfsfunktion), Tests, `ProcessingManager.tsx` |

- **Tests je PR:** wie §5. Fehlerfälle und zweckfremde Nutzung sind dabei: kaputter oder fremder Speicherinhalt, unbekannte Version, voller und gesperrter Speicher, zwei Tabs, abgewiesene Teile, Job aus einem anderen Tab, `404`/`410` bei Details und Download, Doppelklick auf „Cancel all“.
- **Prüfanleitung für Otto:** im jeweiligen PR, Browser und PowerShell. Für UI-01e: `Invoke-WebRequest -Method Post -Body "jobs=…" -OutFile …` und das Auspacken mit `Expand-Archive`.
- **Doku je PR:** Log-Zeilen; UI-01 in `projektplan.md` (VP3); am Ende diese Datei §7 mit der Umsetzung.
