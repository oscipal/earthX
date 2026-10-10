# M4-12 — Mosaik ganzer Szenen je Überflug als Job: Plan

**Aufgabe:** M4-12 aus `docs/plans/m4-processing-kern.md` §4.
**Stufe B** — Plan-Schritt. Die Session hält nach diesem PR an; umgesetzt wird
erst nach Ottos Freigabe (§8).
**Ort im Repo:** `docs/plans/m4-12-mosaik-ueberflug.md`
**Grundlagen:** `plans/m3-dritte-quelle-und-interface.md` P19; `adr/0011`
§8.1; `adr/0014` §3.4, §4.2, §4.3, §5.3, §5.5, §6.3, §7.2; `adr/0006` §3;
`plans/m4-07a-processing-kern.md` F2, F3, F9; `plans/m4-07b-annahme.md` F4, F5;
`plans/m4-processing-kern.md` M4-10b und `processing/operators/reproject.py`
(M4-10, M4-10b);
`plans/m4-11-export-job.md` §3, §5, §11; `plans/m4-13-processing-panel.md` F8;
`ENTSCHEIDUNGSLOG.md` 23.09.2026 und 26.09.2026 (Mosaik ganzer Szenen als
Processing-Job), „M4 Q7“ (02.10.2026), „M4-11a“ (08.10.2026);
`KLAERUNGEN.md` B8, B9, B10, B11.

---

## 1. Ergebnis in drei Sätzen

Ein Auftrag nennt die Szenen eines Überflugs als eine Gruppe und lässt die AOI
weg; `api` prüft, dass alle Szenen denselben Überflug-Schlüssel der Registry
tragen (`results_group_by`), und setzt als AOI die Vereinigung ihrer Footprints.
Der Kern rechnet die Gruppe als ein Mosaik im Raster der UTM-Zone, in der die
meisten Szenen liegen: Szenen dieser Zone liest er ohne Warp, Szenen anderer
Zonen mit dem Warp aus M4-10 und `nearest`, und in Überlappungen gewinnt das
erste gültige Pixel, zuerst aus Szenen ohne Warp; danach laufen die Schritte
des Rezepts wie bei einem einzelnen Item. Das Ergebnis ist ein gewöhnlicher
Job (`result.tif`, `mask.tif`, `recipe.json`, Cache nach Q11); dasselbe Mosaik
gilt für einen Auftrag mit AOI, dessen Fläche mehrere Szenen eines Überflugs
berührt, was heute als Job ein `422` ist (M4-13 F8).

---

## 2. Stand vor dieser Aufgabe (gelesen am 10.10.2026, `main` = `74b2e30`)

- **Abhängigkeiten erfüllt:** M4-08b (#128) und M4-10 (#125, #126) sind
  gemergt, ebenso M4-11a (#133) und M4-13a (#134).
- **Kern** (`processing/core.py`): `check_scope` lässt für die Ausgabe `raster`
  genau eine Eingabe, eine Gruppe und ein Item zu („mosaics come with M4-12“,
  M4-07a F2). Der erste Durchgang liest die Assets des Items ohne Warp im
  Raster des feinsten Assets (`source.common_grid`, `Source.read`); das
  Fenster ist `bbox(AOI ∩ Rastergrenze)` (`plan.crop_window`, M4-07a F9).
  Schritte vom Typ `grid` (heute nur `reproject`) lesen die Datei des vorigen
  Durchgangs im Arbeitsordner (M4-07a F3).
- **Reprojektion** (`processing/operators/reproject.py`, `op_version` 2):
  `WarpedVRT` je Block, `TOLERANCE` 0,125 Quellpixel, `WARP_MEM_LIMIT_MB` 64,
  `nearest`/`bilinear`/`cubic`, Seitenlänge höchstens `MAX_SIDE_PX` = 32 768.
  Braucht `reprojection`, außer bei `nearest` auch `interpolation`.
- **Export** (`processing/export.py`, M4-11a): mosaikiert schon mehrere Items
  einer Gruppe, aber nur für die Ausgabe `crop` (EPSG:4326, nur COG, ZIP, nie
  Cache). Dort gelöst und wiederverwendbar: erstes gültiges Pixel je Band in
  der Reihenfolge des Auftrags, Lesecache der gleichzeitig offenen Items
  geteilt (64 MB / Zahl der Items), Abweisung von Items mit anderen Bändern.
  Mehrere UTM-Zonen löst der Export, indem er alles nach EPSG:4326 warpt
  (M4-11 §5: „keine eigene Regel“).
- **Annahme** (`api/intake.py`): Aufträge mit Gruppen gibt es schon (Zuschnitt,
  Export); `MAX_ORDER_ITEMS` = 25 (M4-07b F5, „M4-12 darf die Grenze mit
  Begründung anheben“). Gruppen und Items, die die AOI nicht berühren, fallen
  weg (M4-07b F4). Eine Prüfung, dass die Items einer Gruppe zusammengehören,
  gibt es nicht.
- **Registry:** `ViewerInfo.results_group_by` ist der Überflug-Schlüssel der
  Trefferliste und der Gruppen des Downloads (P19, M3-17):
  `("datetime", "s2:datatake_id")` für `sentinel-2-c1-l2a`,
  `("datetime", "eopf:datatake_id")` für `sentinel-2-l2a-zarr3`,
  `("start_datetime",)` für `cop-dem-glo-30`. `catalog.registry.group_key`
  rechnet heute nur `group_by`.
- **Capabilities:** Alle drei Einträge setzen `band_math`, `interpolation` und
  `reprojection` auf `true` (R3). Ein Flag für Mosaike gibt es nicht; der
  Zuschnitt und der Export mosaikieren für jeden Datensatz ab der Lizenzstufe
  *Processing* (B11).
- **Frontend:** Bei mehreren gewählten ganzen Szenen (COG, „View full
  selection“) bietet der Download-Dialog die Originale einzeln an
  (`download.ts::decideDownloadOutcome` → `originals`); das gemergte Mosaik je
  Überflug ist seit dem 26.09.2026 als Job für M4 vorgemerkt (P19). Das Panel
  (M4-13b, offen) schickt nach M4-13 F8 genau ein Item.
- **Kein Größendeckel für Raster-Jobs:** Bisher begrenzt das eine Item die
  Ausgabe (eine Sentinel-2-Kachel hat höchstens 10 980² px), dazu
  `MAX_SIDE_PX` für `reproject`. Ein Mosaik aus 25 Kacheln hätte keinen Deckel.

---

## 3. Vorschlag

Die Abschnitte beschreiben die Empfehlung jeder Frage aus §8.

### 3.1 Auftrag

Mosaik ganzer Szenen eines Überflugs, ohne AOI (F5):

```json
{
  "recipe_version": 1,
  "inputs": [{"name": "input", "dataset": "sentinel-2-c1-l2a",
              "groups": [["<item>", "<item>", "<item>"]], "assets": ["visual"]}],
  "steps": [],
  "output": {"kind": "raster", "format": "cog", "dtype": "uint8"}
}
```

Mit AOI ist es derselbe Auftrag wie heute, nur dürfen in der einen Gruppe
mehrere Items stehen. Mit Schritten (Band-Math, Reprojektion) gilt das Mosaik
als Eingabe der Schritte.

### 3.2 Annahme in `api` (F5, F6)

- **Ein Überflug je Auftrag (F6):** eine Eingabe, eine Gruppe. Die Items der
  Gruppe holt `api` wie heute über die Item-Quelle; alle tragen denselben
  Schlüssel nach `results_group_by`, sonst `422` mit den Item-IDs der
  abweichenden Szenen. `group_key` bekommt dafür die Felder als Argument; die
  Regel (STAC-Zeitpunkt → UTC-Datum) bleibt eine. Mehrere Überflüge sind
  mehrere Jobs.
- **Ohne AOI (F5):** `RecipeRequest.aoi` wird optional, nur für die Ausgabe
  `raster`. `api` setzt im Rezept die Vereinigung der Footprints der Items
  (`shapely.unary_union`, als `Polygon` oder `MultiPolygon` in EPSG:4326); ein
  Item ohne Footprint geht mit seiner `bbox` ein. Das Rezept selbst ändert sich
  nicht: Es trägt wie immer eine AOI, der Kern merkt keinen Unterschied, und
  `recipe_version` bleibt 1 (der Auftrag wird nachgiebiger, nicht strenger,
  `adr/0014` §4.3). Eine Vereinigung über den Antimeridian ist `422`.
- **Fläche über mehrere Szenen mit AOI:** wie heute fallen Items ohne Berührung
  weg (`skippedItems`); es bleibt eine Gruppe.
- **Zarr (F8):** Ein Mosaik aus Zarr-Items ist nur zulässig, wenn alle Items
  dasselbe CRS tragen (`ResolvedAssetModel.crs`, geprüft in `check_scope`, also
  vor dem Einreihen); sonst `422` mit Hinweis. Liegt ein Zarr-Item im selben
  CRS nicht auf dem Raster, scheitert der Lauf mit `UnsupportedRecipe`. Über
  Zonen hinweg folgt Zarr mit der offenen Zeile „Export-Job für Zarr
  blockweise“.
- **Flags (F2):** Jedes Mosaik (mehr als ein Item) verlangt `reprojection` am
  Datensatz (`422` sonst), weil es Items warpen kann, wie ein
  `reproject`-Schritt mit `nearest`. Das lässt sich bei der Annahme prüfen,
  ohne eine Datei zu öffnen. Kein neues Flag.
- **Deckel (F7):** Schätzung über `MAX_RASTER_JOB_BYTES` → `413`, wie beim
  Export (§3.5).

### 3.3 Mosaikraster im Kern (`processing/mosaic.py`, neu; F3, F4, K1–K7)

- **Ziel-CRS (F4):** das CRS, das die meisten Items der Gruppe tragen
  (`ResolvedAssetModel.crs`, sonst das CRS der geöffneten Datei); bei
  Gleichstand das CRS des ersten Items in der Reihenfolge des Auftrags. Die
  Regel ist eine reine Funktion des Rezepts.
- **Raster:** Anker ist das erste Item im Ziel-CRS, darin das feinste Asset
  (wie `common_grid`). Ausdehnung = `bbox(AOI ∩ Vereinigung der
  Item-Ausdehnungen)` im Ziel-CRS, nach außen auf das Pixelraster des Ankers
  gerundet; kein eigener Seitendeckel, es begrenzt der Deckel F7 (K6).
- **Items ohne Warp:** Ein Item liegt *auf dem Raster*, wenn CRS und
  Pixelgröße gleich sind und sein Ursprung um ganze Pixel vom Anker abweicht
  (Toleranz wie `source._GRID_TOLERANCE`). Es wird mit `Source.read` ohne Warp
  gelesen. Für Sentinel-2 gilt das für alle Kacheln einer Zone (§7,
  Stichprobe).
- **Items mit Warp (K1):** jedes andere Item, über `WarpedVRT` auf der
  geöffneten COG-Datei in das Mosaikraster, mit `nearest` und denselben
  Konstanten wie `reproject` (`TOLERANCE`, `WARP_MEM_LIMIT_MB`, aus dem
  Operator importiert, nicht kopiert); danach dieselbe Skalierung (§5.4) wie
  `Source.read`. Das Ergebnis trägt `earthx:resampled = true`.
- **Überlappung (F3):** je Block und Band gewinnt das erste gültige Pixel; die
  Reihenfolge ist: zuerst die Items auf dem Raster, dann die gewarpten, je in
  der Reihenfolge des Auftrags. Gültig heißt: nicht nodata, nicht von der
  Skalierung maskiert (dieselbe Maske wie `Source.read`).
- **Lesen je Block (K3):** Nur Items, deren Ausdehnung den Block schneidet,
  werden gelesen; sind alle Elemente des Blocks gefüllt, werden die übrigen
  nicht mehr gelesen (wie der Export).
- **Assets je Item:** wie heute (`common_grid`: gleiches Raster oder
  verschachtelt). Alle Items einer Gruppe haben je Asset dieselbe Zahl Bänder
  und denselben Datentyp, sonst `UnsupportedRecipe` mit Namen (wie der Export).
- **Speicher (K4):** Die Items einer Gruppe sind gleichzeitig offen und teilen
  sich den Lesecache eines Items (`export._cache_per_item`, nach
  `processing/source.py` oder `readers` gezogen, eine Stelle).

### 3.4 Kern (`processing/core.py`)

- `check_scope`: Ausgabe `raster` mit einer Eingabe und einer Gruppe; mehrere
  Items in der Gruppe sind ein Mosaik. Mehrere Gruppen bleiben
  `UnsupportedRecipe`.
- Der erste Durchgang nimmt für ein Mosaik das Mosaikraster statt
  `crop_window` des einen Items und liest je Block über `mosaic.py`; alles
  danach (Pixel-Schritte, `grid`-Schritte, Maske, COG) bleibt unverändert. Ein
  Rezept mit einem Item läuft wie heute, bitgleich (bestehende Tests).
- `processing:lineage` beginnt mit `mosaic of N scenes`; `earthx:resampled`
  ist `true`, sobald ein Item gewarpt wurde oder Assets verschachtelt sind.
- Logs: Zahl der Items, Zahl der gewarpten Items, Blöcke; nie AOI, Adresse,
  Hash, Item-ID mit Ort.

### 3.5 Kosten, Deckel, Platte (`processing/plan.py`; F7)

- `estimate` für ein Mosaik: Ausgabe = Mosaikraster aus AOI-`bbox` und `gsd`
  (wie heute je Item), Eingabe = Summe je Item über `AOI ∩ bbox des Items`.
  Die Laufzeit misst der PR wie M4-11a (eins, zwei, acht Items) und setzt die
  Konstanten danach.
- **Deckel (F7):** `MAX_RASTER_JOB_BYTES` = 5 GB roh (Ausgabe in ihrem
  Datentyp plus Maske), in `access/crop_rules.py` neben
  `MAX_EXPORT_JOB_BYTES`; darüber `RasterJobTooLarge` → `413`. Gilt für jeden
  Raster-Job, auch mit einem Item (dort heute nicht erreichbar).
- `disk_needed` rechnet mit dem Mosaikraster (float64-Durchgang über alle
  Bänder, wie heute).

### 3.6 Frontend (M4-12b, F9)

Nach dem Merge von M4-13b, mit dessen Statusanzeige (SSE mit Rückfall), wie
M4-11b:

- Download-Dialog im Fall `originals` mit mehreren Szenen eines Überflugs:
  zusätzlich „Merge scenes of this pass (job)“ je Gruppe; startet je Überflug
  einen Job ohne AOI, `steps: []`, `dtype` aus den Bändern des Items.
- Panel: schickt die ganze Gruppe der AOI statt eines Items (hebt M4-13 F8
  auf, sobald beide gemergt sind).

### 3.7 Tests (M4-12a)

| Was | Test |
|---|---|
| zwei Zonen | synthetische COGs beidseits eines Zonenrands (EPSG:32631/32632, gleiche Bänder, Werte je Item verschieden): Ziel-CRS nach F4 (2:1 und 1:2), Items auf dem Raster bitgleich zur Quelle, gewarpte Pixel gleich einem unabhängigen `rasterio.warp.reproject` mit `nearest` und denselben Konstanten, Maske = Footprints |
| Überlappung | Pixel in der Überlappung zweier Items: native vor gewarpt, sonst Reihenfolge des Auftrags; Gegenprobe mit vertauschter Reihenfolge |
| ein Item | bestehende Kern-Tests unverändert grün; fester Hash und `recipe.json` eines Raster-Rezepts unverändert |
| ohne AOI | AOI im Rezept = Vereinigung der Footprints; Item ohne Footprint → `bbox`; Antimeridian → `422` |
| Überflug | Items mit anderem `results_group_by`-Schlüssel → `422` mit IDs; mehrere Gruppen → `422`; synthetische DEM-Kacheln (ein Schlüssel, EPSG:4326, zwei Pixelbreiten) → Mosaik |
| Flags, Zarr | Mosaik ohne `reprojection` → `422`; Zarr über zwei CRS → `422` vor dem Einreihen; Zarr in einem CRS → Mosaik |
| Deckel | Schätzung genau am Deckel → angenommen, ein Pixel darüber → `413`; die Annahme ruft keinen Kern |
| Speicher | Mosaik einer großen synthetischen Kachel im eigenen Prozess mit einem und mit zwei Items: `VmHWM` unter 500 MB, zwei Items höchstens +16 MB (wie M4-11a) |
| Lesen je Block | ein Block, der nur ein Item schneidet, öffnet keinen Lesevorgang am anderen (gezählt) |
| Abbruch | `RunCancelled` mitten im Mosaik → Arbeitsordner leer |
| Cache | zwei gleiche Mosaik-Aufträge teilen einen Lauf; ein Item mehr → anderer Schlüssel |
| Logs | kein AOI-Wert, keine Adresse, kein Hash |
| Importregeln | `lint-imports` grün; das Kind lädt weder psycopg noch `earthx.access.download` |

---

## 4. Abnahme

- **Test mit synthetischen Szenen über zwei Zonen** (§3.7, erste Zeile) grün
  in der CI.
- **Prüfanleitung für Otto** (§9) im PR von M4-12a.
- `pytest`, `ruff check backend`, `PYTHONPATH=backend lint-imports --config
  .importlinter` grün.

---

## 5. Nicht in dieser Aufgabe

- Mosaik im Kachel-Pfad, auch als T1-Vorschau eines Mosaik-Jobs: M4-17.
- Mosaik über mehrere Überflüge oder Tage (Kompositbildung, Wolkenmaske): nicht
  geplant; ein Auftrag ist ein Überflug.
- Mehrere Gruppen in einem Raster-Job (je Gruppe eine Datei): nicht nötig, das
  Frontend startet je Überflug einen Job.
- Zarr über mehrere CRS: mit der offenen Zeile „Export-Job für Zarr
  blockweise“.
- Ein `reproject`-Schritt direkt hinter dem Mosaik warpt gewarpte Items ein
  zweites Mal; ein gemeinsamer Warp in das Zielraster ist eine spätere
  Optimierung mit eigener Messung.
- Den Export (`crop`) auf das UTM-Raster umstellen: nein; er bleibt beim
  Raster des Zuschnitts (M4-11 F1).

---

## 6. Umfang und Commits (M4-12a)

Geschätzt rund 450 Zeilen Code und rund 650 Zeilen Tests, über dem Richtwert
von 400 Zeilen wegen der Tests. Commits, je eine Sache:

1. `catalog`: `group_key` mit Feldern als Argument.
2. `processing`: Mosaikraster, Ziel-CRS, Lesen je Block (`mosaic.py`).
3. `processing`: Mosaik im ersten Durchgang von `run`, `check_scope`.
4. `processing`: Schätzung und Deckel für Raster-Jobs.
5. `api`: Auftrag ohne AOI, Prüfung des Überflugs, Flags, Zarr.
6. Tests über zwei Zonen, Überlappung, Speicher.
7. Doku: Nachtrag `adr/0014`, Log, Status in `m4-processing-kern.md` §3.

M4-12b (Frontend) rund 250 Zeilen mit Tests.

---

## 7. Risiken

- **Pixelraster der Sentinel-2-Kacheln:** Stichprobe [M] (eine Anfrage an Earth
  Search, Fläche 3° × 1,5° um 12° O, ein Tag, 10.07.2025): drei
  Kacheln desselben Datatakes in EPSG:32632 und EPSG:32633; in Zone 33 liegen
  die Ursprünge (300 000 / 5 300 040 und 300 000 / 5 400 000) um 9 996 Pixel
  zu 10 m auseinander, auch ganzzahlig für 20 m und 60 m. Ein Überflug über
  zwei Zonen ist also der Normalfall am Zonenrand, und Kacheln einer Zone
  liegen auf einem Raster. Fällt die Annahme für ein Item, wird es gewarpt
  (`nearest`), nur langsamer.
- **Werte in der Überlappung:** Benachbarte Kacheln eines Überflugs können sich
  in der Überlappung unterscheiden (Atmosphärenkorrektur je Kachel, siehe
  Recherche in §10); die Regel F3 macht das Ergebnis eindeutig, nicht
  „richtiger“.
- **Größe:** Eine Kachel `visual` (3 × `uint8`, 10 m) ist roh rund 360 MB plus
  120 MB Maske; 5 GB fassen höchstens rund zehn Kacheln, weniger, weil der
  Deckel die `bbox` des schräg liegenden Überflugs zählt. Längere Überflüge
  brauchen mehrere Jobs; die Schätzung sagt es vor dem Start.
- **Laufzeit:** Ein Mosaik von zehn Kacheln liest rund 1,2 Gpx; die Laufzeit
  misst der PR, das Netz nicht (wie M4-11a).
- **Slots und Platte:** wie M4-11a; `disk_needed` und die Plattenprüfung des
  Aufsehers gelten unverändert.

---

## 8. Fragen an Otto

**F1 — Welcher Weg? (§3.3, §3.4)**
1. Raster-Lauf des Kerns: Mosaik im UTM-Raster, Items anderer Zonen über den
   Warp aus M4-10; Ergebnis `result.tif` + `mask.tif` wie jeder Job, Schritte
   dahinter möglich, Cache nach Q11; hebt nebenbei M4-13 F8 auf
   **(Empfehlung)**
2. Export-Weg: Auftrag `crop` mit der Vereinigung der Footprints als AOI; alles
   in EPSG:4326, ZIP, nie Cache, keine Schritte. Kaum neuer Code, aber kein
   UTM-Raster und keine Reprojektion aus M4-10
3. Beides

**F2 — Eigenes Capability-Flag? (§3.2; im Aufgabenschnitt offen)**
1. Nein. Ein Mosaik ist kein Operator; mehrere Items einer Gruppe lesen
   Zuschnitt und Export schon heute für jeden Datensatz ab *Processing*. Weil
   es Items warpen kann, verlangt jedes Mosaik `reprojection`, wie ein
   `reproject` mit `nearest` **(Empfehlung)**
2. Neues Flag `mosaic` in `Capabilities`, ohne Vorgabewert (B10), alle drei
   Einträge setzen es ausdrücklich; zusätzlich `reprojection`

**F3 — Regel für Überlappungen (im Aufgabenschnitt offen)**
1. Erstes gültiges Pixel, zuerst Items ohne Warp, dann gewarpte, je in der
   Reihenfolge des Auftrags; so stammt jedes Pixel, wo möglich, unverändert
   aus der Quelle **(Empfehlung)**
2. Erstes gültiges Pixel streng in der Reihenfolge des Auftrags, wie Zuschnitt
   und Export (`FirstMethod`)
3. Mittelwert in der Überlappung (neue Werte; bräuchte `interpolation`)

**F4 — Ziel-CRS bei mehreren Zonen (§3.3)**
1. Das CRS der meisten Items, bei Gleichstand das des ersten Items; vom Kern
   aus dem Rezept bestimmt **(Empfehlung)**
2. Das CRS der meisten Items, bei Gleichstand die kleinere EPSG-Zahl
   (unabhängig von der Reihenfolge, §10)
3. Das CRS des ersten Items im Auftrag
4. Der Auftrag nennt das CRS, Pflicht bei mehreren Zonen (wie stackstac)

**F5 — Wie kommt „ganze Szenen“ in den Auftrag? (§3.2)**
1. Der Auftrag lässt `aoi` weg; `api` setzt die Vereinigung der Footprints ins
   Rezept. Das Rezept bleibt Version 1 **(Empfehlung)**
2. Das Frontend schickt die Vereinigung der Footprints als AOI
   (`polyclip-ts` ist vorhanden); keine Änderung am Auftrag

**F6 — Was ist ein Überflug, und wer sucht die Szenen? (`adr/0011` §8.1)**
1. Der Auftrag nennt die Items (aus der Suche, die der Viewer über `api`
   gemacht hat); `api` prüft, dass sie einen Schlüssel nach `results_group_by`
   tragen; eine Gruppe je Auftrag **(Empfehlung)**
2. Wie 1, ohne Prüfung des Schlüssels
3. Der Auftrag nennt Datensatz und Überflug-Schlüssel; `api` sucht selbst alle
   Items des Überflugs (bis zur Item-Grenze)

**F7 — Deckel eines Raster-Jobs (§3.5)**
1. 5 GB roh (Ausgabe plus Maske) als eigene Konstante neben dem Deckel des
   Exports, für jeden Raster-Job **(Empfehlung)**
2. 2 GB
3. Ein gemeinsamer Deckel für Export und Raster-Job (eine Konstante)

**F8 — Zarr (`sentinel-2-l2a-zarr3`)**
1. Zarr-Mosaik nur, wenn alle Items im Mosaik-CRS liegen (ohne Warp); über
   Zonen `422`, mit der offenen Zeile zu Zarr blockweise **(Empfehlung)**
2. Zarr-Mosaike ganz `422`
3. Zarr über Zonen über die Reprojektion des Readers (eigener Warp, eigene
   Messung)

**F9 — Schnitt**
1. Zwei PRs: M4-12a Backend jetzt in dieser Session; M4-12b Frontend nach dem
   Merge von M4-13b mit dessen Statusanzeige, keine eigene Abfrage-Schleife
   **(Empfehlung)**
2. Ein PR mit Frontend (wartet auf M4-13b)

**Kleinentscheidungen** (gelten, wenn Otto nicht widerspricht):

- **K1** Items aus anderen Zonen werden immer mit `nearest` gewarpt: keine
  neuen Werte, nur ein Versatz um höchstens ein halbes Pixel. Kein Parameter
  im Auftrag; wer eine andere Methode will, hängt `reproject` an.
- **K2** `MAX_ORDER_ITEMS` bleibt 25; der Deckel F7 begrenzt vorher (rund zehn
  Kacheln `visual` in 10 m).
- **K3** Je Block werden nur Items gelesen, deren Ausdehnung ihn schneidet.
- **K4** Lesecache wie im Export geteilt, eine Funktion für beide.
- **K5** Die Mosaikregeln (F3, F4, K1, Raster) liegen im Code, nicht im
  Rezept; eine Änderung erhöht `earthx.__version__`, das in den Cache-Schlüssel
  eingeht (wie `BLOCK_SIZE`, `adr/0014` §3.4). Nachtrag in `adr/0014`.
- **K6** Das Mosaikraster hat keinen eigenen Seitendeckel; der Deckel F7
  begrenzt es (bei 1 Byte je Pixel und Maske rund 50 000 px je Seite). Ein
  `reproject` dahinter behält seinen Deckel von 32 768 px; bei 10 m sind das
  rund 330 km.
- **K7** `processing:lineage` beginnt mit `mosaic of N scenes`.
- **K8** Item-IDs in Texten von `422` nennen keine Koordinaten; Logs zählen
  nur.

---

## 9. Prüfanleitung für Otto (M4-12a, nach dem Merge, PowerShell)

Ohne Frontend über die Job-Schnittstelle. Die Fläche wählst du selbst: ein
Rechteck über einem Zonenrand (etwa 12° O, Grenze der UTM-Zonen 32 und 33);
die Werte unten sind Platzhalter.

```powershell
docker compose up -d --build
docker compose ps        # api, tiler, worker, objectstore: healthy

$W, $S, $E, $N = 11.5, 47.5, 12.5, 48.0          # Platzhalter: eigene Fläche eintragen
$aoi = @{ type = 'Polygon'; coordinates = @(,@(@($W,$S), @($E,$S), @($E,$N), @($W,$N), @($W,$S))) }
$search = @{ collections = @('sentinel-2-c1-l2a'); intersects = $aoi
             datetime = '2025-07-01T00:00:00Z/2025-07-31T23:59:59Z'; limit = 100 } | ConvertTo-Json -Depth 10
$items = (Invoke-RestMethod -Method Post -Uri http://localhost:8000/stac/search `
          -ContentType application/json -Body $search).features
$first = $items[0].properties
$pass = @($items | Where-Object { $_.properties.'s2:datatake_id' -eq $first.'s2:datatake_id' })
$pass | ForEach-Object { "$($_.id)  $($_.properties.'proj:code')$($_.properties.'proj:epsg')" }   # zwei Zonen sollten vorkommen

# 1) Ganze Szenen eines Überflugs als ein Mosaik (ohne AOI)
$order = @{ recipe_version = 1; steps = @()
            inputs = @(@{ name = 'input'; dataset = 'sentinel-2-c1-l2a'; groups = @(,@($pass | ForEach-Object id)); assets = @('visual') })
            output = @{ kind = 'raster'; format = 'cog'; dtype = 'uint8' } }
$body = @{ inputs = @{ recipe = $order } } | ConvertTo-Json -Depth 12
$job = Invoke-RestMethod -Method Post -Uri http://localhost:8000/processing/processes/recipe/execution `
       -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
do { Start-Sleep 5; $s = Invoke-RestMethod "http://localhost:8000/processing/jobs/$($job.jobID)"; "$($s.status) $($s.progress)" } `
  while ($s.status -in 'accepted', 'running')
Invoke-WebRequest "http://localhost:8000/processing/jobs/$($job.jobID)/results/result.tif" -OutFile mosaic.tif
Invoke-WebRequest "http://localhost:8000/processing/jobs/$($job.jobID)/results/recipe.json" -OutFile mosaic-recipe.json

# 2) Gegenprobe: Szenen zweier Überflüge in einer Gruppe → 422
```

Zu sehen: `mosaic.tif` in QGIS im CRS der Zone mit den meisten Kacheln, ohne
Naht am Zonenrand und ohne Lücke in den Überlappungen; `mask.tif` deckt die
Szenen ab; `recipe.json` trägt die Vereinigung der Footprints als `aoi`,
`processing:lineage` beginnt mit `mosaic of`, `earthx:resampled` ist `true`,
wenn zwei Zonen beteiligt sind. Ein zweiter gleicher Auftrag ist sofort fertig
(Cache). Bei zu vielen Kacheln antwortet die Annahme `413` mit der Größe.

---

## 10. Recherche (Stand der Technik, 10.10.2026)

Belegstufen wie `adr/0009`: [M] gemessen, [P] am Primärdokument gelesen,
[S] Zusammenfassung, [A] eigene Ableitung. Aus der Sitzung erreichbar waren nur
GitHub und Earth Search; ESA-, Sentinel-Hub- und GDAL-Seiten nicht, deshalb
stehen deren Aussagen auf [S].

| Befund | Beleg | Stufe | Folge hier |
|---|---|---|---|
| rio-tiler: `mosaic_reader` nimmt standardmäßig `FirstMethod` (füllt nur maskierte Pixel), sortiert nicht selbst | [`rio_tiler/mosaic/reader.py`](https://github.com/cogeotiff/rio-tiler/blob/main/rio_tiler/mosaic/reader.py), `methods/defaults.py` | P | F3: erstes gültiges Pixel wie Zuschnitt und Export |
| odc-stac: die Fusion kopiert nur, wo noch kein gültiges Pixel liegt; Reihenfolge `time, id`, auf Wunsch die der Eingabe | [`odc/stac/_stac_load.py`](https://github.com/opendatacube/odc-stac/blob/develop/odc/stac/_stac_load.py) | P | dieselbe Regel; die Reihenfolge ist eine Wahl |
| stackstac `mosaic()`: Standard `reverse=False`, das letzte Element gewinnt | [`stackstac/ops.py`](https://github.com/gjoseph92/stackstac/blob/main/stackstac/ops.py) | P | „first“ ist verbreitet, aber nicht allgemein |
| gdalbuildvrt: die zuletzt gelistete Datei gewinnt, nodata fällt auf frühere zurück | [`gdalbuildvrt.rst`](https://github.com/OSGeo/gdal/blob/master/doc/source/programs/gdalbuildvrt.rst) | P | wie stackstac |
| openEO `merge_cubes`: ohne `overlap_resolver` bei Überlappung ein Fehler | [`merge_cubes.json`](https://github.com/Open-EO/openeo-processes/blob/draft/merge_cubes.json) | P | die Regel gehört ausdrücklich beschrieben (K5, Nachtrag `adr/0014`) |
| Sentinel Hub: `mosaickingOrder` mostRecent (Standard), leastRecent, leastCC | Sentinel-Hub-Doku, Forum | S | Kriterien über mehrere Tage; hier nicht nötig (ein Überflug) |
| odc-stac: ohne `crs` das häufigste (CRS, Auflösung, Anker) der Items | [`odc/stac/_mdtools.py`](https://github.com/opendatacube/odc-stac/blob/develop/odc/stac/_mdtools.py) | P | stützt F4 Option 1 |
| stackstac: ohne `epsg` müssen alle Items dasselbe `proj:epsg` haben | [`stackstac/stack.py`](https://github.com/gjoseph92/stackstac/blob/main/stackstac/stack.py) | P | Gegenmodell F4 Option 3 |
| `nearest` ist Standard in gdalwarp, rio-tiler (`reproject_method`), stackstac, openEO `resample_spatial` | Quellen wie oben, [`gdalwarp.rst`](https://github.com/OSGeo/gdal/blob/master/doc/source/programs/gdalwarp.rst) | P | stützt K1; dass `nearest` für L2A beim Zonenwechsel „üblich“ ist, ist nicht belegt |
| Ein Datatake über zwei Zonen: `GS2C_20261010T123131_010947_N05.13`, 4 Items in EPSG:32625, 2 in EPSG:32626 | Earth Search `/v1/search`, Subagent, eine Anfrage | P | zweiter Fall neben der Stichprobe in §7 |
| Ursprünge der Kacheln einer Zone sind Vielfache von 60 m (6 Items) | dieselbe Anfrage | P (Regel: A) | stützt „auf dem Raster“ in §3.3 |
| Kachel rund 110 km bei 100 km Gitterschritt, Überlappung in einer Zone rund 5 km | ESA Product Types, NASA HLS Tiling | S | Überlappungen sind schmal; an Zonengrenzen breiter |
| L2A-Werte benachbarter Kacheln eines Datatakes können in der Überlappung abweichen (Aerosol je Kachel geschätzt) | [STEP-Forum 33178](https://forum.step.esa.int/t/sen2cor-intensity-differences-between-adjacent-tiles-of-same-acquisition/33178) | S | §7: Nähte möglich; F3 macht das Ergebnis eindeutig |
| Earth Search: nodata 0, `offset` aus `raster:bands` vor dem Fusionieren beachten | [`docs/collections/sentinel-2-l2a.md`](https://github.com/Element84/earth-search/blob/main/docs/collections/sentinel-2-l2a.md) | P | Gültigkeit nach der Skalierung wie `Source.read` (§3.3) |

**Abweichungen von der Recherche-Empfehlung:**
- Gleichstand im Ziel-CRS: die Recherche schlägt die kleinere EPSG-Zahl vor,
  F4 das CRS des ersten Items. Beides ist deterministisch; das erste Item gibt
  dem Auftrag die Wahl, ohne ein Feld dafür. Otto kann in F4 die EPSG-Regel
  wählen.
- Reihenfolge der Überlappung: die Recherche schlägt eine feste Sortierung nach
  Kachel-ID vor; F3 bleibt bei der Reihenfolge des Auftrags (wie Zuschnitt und
  Export), die im Rezept und damit im Hash steht.

**Nebenbefund (nicht Teil dieser Aufgabe):** Laut Earth-Search-Doku wird
`sentinel-2-c1-l2a` in Earth Search v2 durch `sentinel-2-l2a` ersetzt [P].
Eine eigene Log-Zeile schlage ich vor, sobald es einen Termin gibt.
