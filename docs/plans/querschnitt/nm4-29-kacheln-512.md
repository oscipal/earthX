# NM4-29 — 512er-Kacheln prüfen

**Stand:** 28.10.2026, Plan freigegeben (§15); Backend umgesetzt (§16, #227), das Frontend ist die eigene Aufgabe NM4-29b (§17). Beauftragt am 24.10.2026 von Otto (Backlog-Punkt 29 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für Messung und Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach dem Merge von NM4-26; nicht gleichzeitig mit NM4-04 oder NM4-19 (`tiler`).
**Startsatz:** „Führe Aufgabe NM4-29 aus `docs/plans/querschnitt/nm4-29-kacheln-512.md` aus.“

## 1. Anlass

NM4-26 (26.10.2026) hat gezeigt: Der Browser öffnet über HTTP/1.1 nur 6 Verbindungen, die Kacheln warten dort in einer Schlange. Größere Kacheln (512 statt 256 px) hießen ein Viertel der Anfragen für dieselbe Fläche. Otto hat das als eigene Aufgabe vorgesehen.

## 2. Soll

- Entscheiden mit Messung, ob Kacheln mit 512 px eine Ansicht spürbar schneller machen, und wenn ja, umstellen.

## 3. Im Plan klären (mit Optionen und Empfehlung)

- **Messung** mit `scripts/tile-bench` (aus NM4-26): Gesamtzeit einer Ansicht und gelesene Bytes je Kachelgröße, bei unbegrenzter Leitung und 100 Mbit/s.
- **Folgen:** Zoomlogik der Karte, freigegebene Zoomstufen (Mosaik ab Zoom 8, Grenzen der Item-Kachel), Grenzen der Mosaik-Kachel (Items je Kachel), Statistik-Routen, TileJSON (`tileSize`), Bitgleichheit Kachel ↔ Job (`adr/0014` §6.3) auf der nativen Ebene.
- Gilt die Umstellung für alle Kachel-Arten (Szene, Mosaik, Vorschau, Ergebnis) oder nur einige?

## 4. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Messung vorher/nachher im PR; Bitgleich-Tests grün; Prüfung im echten Browser.
- Nachtrag in `adr/0006` bzw. `adr/0014`, falls `tileSize` oder Zoomgrenzen sich ändern.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n) mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat, siehe Kopf des Backlogs).
- Vor „fertig“ ist main geholt.

---

# Plan (28.10.2026)

Bis zur Freigabe ist kein Produktivcode geändert; geändert sind nur Messskripte unter `scripts/tile-bench/`. Belegstufen wie in `adr/0009`: [M] gemessen, [P] am Primärdokument oder im Code gelesen, [S] Zusammenfassung oder Suchtreffer, [A] eigene Ableitung.

## 6. Kurzfassung

- **Weniger Anfragen, aber nicht ein Viertel:** Für einen Bildschirmausschnitt fragt MapLibre mit 512 px 2,2- bis 3-mal weniger Kacheln als mit 256 px, nicht 4-mal weniger. 512er-Kacheln ragen weiter über den Rand hinaus. Der `tiler` liest und kodiert deshalb 1,3- bis 1,8-mal so viele Pixel, und zum Browser gehen 24–59 % mehr Bytes [M, A].
- **Spürbar schneller, wo viele Kacheln warten:** Für eine Ansicht mit vielen Ebenen oder ein Mosaik kommt die letzte Kachel 7–51 % früher (z. B. NDVI über 13 Szenen 25,4 → 19,9 s, Mosaik aus 12 Szenen 29,1 → 14,3 s). Mit einer Leitung von 100 Mbit/s sind es noch 9–19 % [M].
- **Langsamer, wo die Leitung zählt:** Eine einzelne Ebene im schmalen Fenster und `visual` über 13 Szenen bei 100 Mbit/s brauchen 6–11 % länger (+0,3 bis +3 s). Bei begrenzter Leitung zählen die Bytes von der Quelle, und 512er-Kacheln lesen bei Übersichtsstufen bis zu 50 % mehr Fläche [M].
- **Bitgleichheit Kachel ↔ Job bleibt:** Die T1↔T2-Tests (`adr/0014` §6.3) laufen auf dem 512er-Raster grün. Eine 512er-Kachel ist aber nicht pixelgleich mit ihren vier 256er-Kacheln: Auf der nativen Ebene weichen 1,1 % der Pixel ab. Die Ursache ist die Näherung im GDAL-Warp (0,125 px); es entstehen keine neuen Werte. Mit exakter Transformation sind beide gleich [M].
- **Folgen im Code:** sieben Stellen im Frontend rechnen fest mit 256 px, darunter der AOI-Zuschnitt im Browser, der 512er-Kacheln falsch beschneiden würde. Freigegebene Stufen und Mosaik-Grenzen gelten je Stufe und bleiben. Der `tiler` nimmt heute jede `tilesize` an: Eine NDVI-Kachel mit 4096 px kostet 12,6 s [M].
- **Empfehlung:** auf 512 px umstellen, für alle vier Kachel-Arten (Option 1), dazu `tilesize` am `tiler` auf 256 und 512 beschränken. Fünf Fragen in §12.

## 7. Messung

### 7.1 Methode

Gerüst aus NM4-26 (`scripts/tile-bench/`, dort §8.1): der echte `tiler` mit Postgres, ein Prozess wie in `docker-compose.yml`, eine nachgebaute ferne Quelle (170 ms je Anfrage, 350 ms je Verbindung, wahlweise 100 Mbit/s), synthetische COGs im Aufbau der Earth-Search-Dateien. Gemessen am heutigen Stand von `main`, also mit dem GDAL-Profil aus NM4-26 (`SERIAL`, 256 MiB Cache). Jede Zeile ist ein frischer Prozess mit leerem Item- und Statistik-Cache.

Neu für NM4-29:

- **Ansicht wie MapLibre:** `view.py --viewport WxH --map-zoom Z` fragt genau die Kacheln, die MapLibre für einen Ausschnitt anfordert. Die Stufe ist `round(Z + log2(512 / tileSize))` (`covering_tiles.ts` Z. 163–168, maplibre-gl 5.24.0 [P]), Kacheln außerhalb des Fußabdrucks entfallen wie bei einer Quelle mit `bounds`. Der feste Block aus NM4-26 (5×5 gegen 3×3) bevorzugt 512 px, weil 3×3 Kacheln mit 512 px mehr Fläche zeigen als 5×5 mit 256 px.
- **Gegenprobe im Browser:** `maplibre_tiles.cjs` zählt im Chromium der Sitzung, was MapLibre für dieselben Ausschnitte wirklich fragt. Die Zahlen stimmen in allen sechs Ausschnitten mit `view.py` überein (z. B. 1280×800 bei Zoom 10,2: 18 gegen 6 Kacheln). Mit Globus statt Mercator sind es gleich viele oder weniger [M].
- **Mosaik:** `view.py --mosaic` fragt je Position eine Mosaik-Kachel aller Szenen. Die Szenen des Gerüsts haben denselben Fußabdruck; mit 13 Szenen antwortet der `tiler` `422`, weil höchstens 12 Szenen je Kachel erlaubt sind (`MAX_SCENES_PER_TILE`). Gemessen ist deshalb ein Mosaik aus 12 Szenen [M].
- **Wie oft das vorkommt:** Über 20 000 zufällige Ausschnitte (Kartenzoom 9–14, zufälliger Mittelpunkt) braucht 512 px im Mittel 2,8× (1280×800), 3,0× (1920×1080) und 2,2× (360×640) weniger Kacheln, aber 1,43×, 1,32× und 1,79× so viele Pixel [A, gerechnet].

### 7.2 Ergebnis

Rechner der Sitzung: 4 Kerne, 16 GB. „erste / Hälfte / alle“: Zeit bis die erste Kachel, die Hälfte und alle Kacheln im Client angekommen sind (wie die Spalte „Time“ in DevTools, mit Warten auf eine Verbindung). „Kachel“: Median im `tiler`. „Quelle“: Bytes von der Quelle, in Klammern davon gebraucht. „Browser“: Bytes der Antworten.

| Ansicht | Leitung | Anfragen | 256 px: erste / Hälfte / alle | 512 px: erste / Hälfte / alle | alle | Kachel | Quelle (gebraucht) | Browser |
|---|---|---|---|---|---|---|---|---|
| NDVI, 13 Szenen je eigene Ebene, 1280×800, Zoom 10,2 | unbegrenzt | 234 → 78 | 2,7 / 14,9 / 25,2 s | 2,7 / 12,3 / 19,8 s | **−21 %** (Wdh. 25,8 → 19,7 s) | 0,51 → 1,26 s | 212 → 284 MB (212 → 284) | 27 → 37 MB |
| | 100 Mbit/s | 234 → 78 | 4,5 / 23,4 / 34,9 s | 7,3 / 22,5 / 31,6 s | **−10 %** | 0,55 → 1,88 s | 215 → 292 MB | |
| `visual`, 13 Szenen, 1280×800, Zoom 10,2 | unbegrenzt | 234 → 78 | 1,9 / 11,7 / 20,3 s | 2,0 / 10,6 / 19,1 s | **−7 %** | 0,43 → 1,30 s | 165 → 212 MB (159 → 212) | 31 → 41 MB |
| | 100 Mbit/s | 234 → 78 | 3,7 / 18,6 / 27,2 s | 5,8 / 20,6 / 30,3 s | **+11 %** (Wdh. 27,6 → 30,1 s) | 0,44 → 1,75 s | 166 → 212 MB | |
| NDVI-Mosaik aus 12 Szenen, eine Ebene, 1920×1080, Zoom 11,5 | unbegrenzt | 77 → 24 | 4,8 / 16,4 / 29,1 s | 4,9 / 9,5 / 14,3 s | **−51 %** | 1,94 → 2,86 s | 273 → 237 MB (197) | 16 → 19 MB |
| | 100 Mbit/s | 77 → 24 | 9,0 / 27,6 / 41,0 s | 10,9 / 28,4 / 33,3 s | **−19 %** | 1,93 → 7,42 s | 299 → 349 MB (197) | |
| NDVI, 1 Szene, 1920×1080, Zoom 13 (native Ebene) | unbegrenzt | 40 → 15 | 2,5 / 3,6 / 4,7 s | 2,1 / 2,9 / 3,6 s | **−23 %** | 0,34 → 0,57 s | 33 → 31 MB (20 → 20) | 4,0 → 5,9 MB |
| | 100 Mbit/s | 40 → 15 | 3,9 / 4,9 / 5,8 s | 3,4 / 4,7 / 5,3 s | **−9 %** | 0,24 → 0,84 s | 33 → 30 MB | |
| NDVI, 1 Szene, 360×640 (schmal), Zoom 11,5 | unbegrenzt | 15 → 6 | 2,2 / 2,6 / 3,3 s | 2,3 / 2,6 / 2,9 s | **−13 %** | 0,63 → 2,57 s | 30 → 40 MB (20 → 30) | 3,1 → 4,9 MB |
| | 100 Mbit/s | 15 → 6 | 2,8 / 3,7 / 4,9 s | 4,3 / 4,9 / 5,4 s | **+10 %** (Wdh. 5,0 → 5,3 s) | 1,03 → 4,72 s | 31 → 40 MB | |

Speicher des `tiler` nach der Ansicht: 335–602 MB bei Einzelszenen, 897–941 MB beim Mosaik, je Größe ungefähr gleich [M]. Die Kachel im `tiler` kodiert mit 512 px rund 3× so lange (PNG, 43 → 149 ms bei NDVI).

### 7.3 Was die Zahlen sagen

- **B1 Die Schlange im Browser wird kürzer.** Bei 234 Anfragen über 6 Verbindungen und ohne Leitungsgrenze kommt die Hälfte der Kacheln mit 512 px 1,1–2,6 s früher, die letzte 1,2–5,4 s früher. Beim Mosaik (77 → 24 Anfragen, teure Kacheln) halbiert sich die Zeit bis zur letzten Kachel.
- **B2 Die erste Kachel kommt nicht früher, bei begrenzter Leitung später.** Eine 512er-Kachel braucht im `tiler` das 2- bis 4-Fache einer 256er. Ohne Leitungsgrenze gleicht sich das aus (erste Kachel 2,0–4,9 s, wie mit 256 px). Bei 100 Mbit/s kommt die erste Kachel meist 1,5–2,8 s später, nur auf der nativen Ebene 0,5 s früher. Die Fläche füllt sich in größeren Stücken.
- **B3 Mehr Fläche heißt mehr Bytes.** Auf Übersichtsstufen liest eine 512er-Kachel einen größeren Ausschnitt außerhalb des Bildschirms: 212 → 284 MB von der Quelle (+34 %) für dieselbe NDVI-Ansicht, im schmalen Fenster +50 %. Auf der nativen Ebene liegen die Blöcke (1024 px) ohnehin über den Rand hinaus, dort bleibt es bei 20 MB.
- **B4 Bei begrenzter Leitung entscheidet das.** Mit 100 Mbit/s zählt vor allem, wie viele Bytes von der Quelle kommen (NM4-26 B4). Wo die Ansicht wenige Anfragen hat (eine Ebene, schmales Fenster) oder die Bytes stark steigen (`visual` +34 %), ist 512 px langsamer: +0,3 bis +3 s.
- **B5 Das Mosaik gewinnt am meisten** (−51 % bzw. −19 %), weil seine Kacheln teuer sind und je Position nur eine Anfrage stehen. Bei 100 Mbit/s holt es mit 512 px aber 349 statt 299 MB für 197 MB gebrauchte: Mehrere kalte Kacheln lesen dieselben Blöcke gleichzeitig (NM4-26 B3), und eine 512er-Kachel liest je Szene mehr Blöcke parallel.
- **B6 Zum Browser gehen 24–59 % mehr Bytes.** Lokal unter `docker compose` spielt das keine Rolle, mit einer langsamen Leitung des Nutzers schon. Mit M6 (CDN, HTTP/2) wird die Schlange im Browser kürzer, und der Vorteil von 512 px schrumpft. In NM4-26 (S4: 24 Verbindungen, 4 Prozesse, fester Block) lag 512 px dort trotzdem vorn (13,3 gegen 19,0 s) [M].

## 8. Bitgleichheit Kachel ↔ Job (`adr/0014` §6.3)

**T1 ↔ T2 auf dem 512er-Raster [M]:** Die vier Testklassen „…EqualsTheJobOnTheNativeLevel“ habe ich lokal (nicht eingecheckt) auf Stufe 13 mit `tilesize=512` umgestellt. Stufe 13 mit 512 px hat dieselbe Pixelgröße wie Stufe 14 mit 256 px, also die native Ebene der 10-m-Daten. Der Job wird dazu mit `nearest` auf dieselbe 512er-Kachel gelesen.
- Band-Math über COG-Paare, Ketten, `mask`/`normalize` und Mosaik mit Schritten: **bitgleich**, Masken gleich (22 Tests grün). Zwei Hilfsfunktionen der Tests rechnen fest mit 256 px (`_tile_at`, die URL einer Einzelszene im Mosaik-Test); angepasst laufen auch diese zwei Tests grün.
- Zarr mit CF-Attributen (synthetisch; einen Zarr-Datensatz gibt es nicht mehr in der Registry, der Leser bleibt): Kachel gegen den exakt nächsten Quellpixel 1 von 6462 Pixeln anders (vorher 0), Kachel gegen Job 138 von 6462 (2,1 %, vorher 13 von 3489 = 0,4 %). Alle Abweichungen liegen innerhalb von 0,125 px an einer Pixelgrenze, wie es der Test für diesen Fall zulässt. Seine Grenze von 2 % reißen sie knapp.

**512er-Kachel gegen ihre vier 256er-Kacheln [M]** (`stitch.py`, echter `tiler`, je 786 432 Werte):

| Stufe 512 / 256 | NDVI | `visual` | NDVI-Mosaik |
|---|---|---|---|
| 10 / 11 (Übersicht) | 488 anders (0,06 %) | 493 | 488 |
| 13 / 14 (nativ) | 8975 (1,1 %) | 9002 | 8975 |
| 15 / 16 (darüber) | 559 (0,07 %) | 556 | 559 |

Masken sind überall gleich. **Ursache:** Der Warp von rio-tiler (`WarpedVRT`) rechnet die Transformation mit einer Näherung, Toleranz 0,125 px [P]. Über eine 512 px lange Zeile fällt die Näherung anders aus als über zwei 256 px lange. Wo ein Zielpixel fast genau auf einer Quellpixelgrenze liegt, wählt `nearest` dann den anderen Nachbarn. Mit `tolerance=1e-6` sind 512er-Kachel und die vier 256er in allen drei Stufen gleich (0 Abweichungen, direkt mit `rio_tiler.io.Reader` am selben COG) [M].

**Folgen:**
- Die Zusage in §6.3 gilt für „das Kachelraster einer Zoomstufe“. Mit 512 px ist das das Raster der 512er-Kachel, und dort hält sie. Die Tests müssen auf der Größe laufen, die ausgeliefert wird.
- Nach der Umstellung zeigt jede Kachel an ~1 % der Pixel (nativ) den Nachbarpixel statt des heutigen. Es entstehen keine neuen Werte, Job-Ergebnisse ändern sich nicht. Ein Vergleich „Kachel von heute gegen Kachel von morgen“ ist also nicht byte-identisch.
- Die Toleranz auf 0 zu setzen, ist nicht Teil dieser Aufgabe: Es ändert die Pixel aller Kacheln und kostet Rechenzeit (ungemessen).

## 9. Folgen im Code

### 9.1 Zoomlogik der Karte (Frontend) [P]

| Stelle | heute | mit 512 px |
|---|---|---|
| `mapLayers.ts` `placeRaster` (Z. 223), `syncPreview` (Z. 546) | `tileSize: 256` | 512 |
| `api.ts` `buildTileTemplate`, `buildMosaicTileTemplate`, `buildOperatorTileTemplate`, `buildMosaicOperatorTileTemplate` | ohne `tilesize`; die Route nimmt dann 256 (Raster der TMS) | `tilesize=512` in jeder Vorlage. Die Mosaik-URL wird 13 Bytes länger; `mosaicRequestBytes` zählt die Vorlage mit, die Grenze 7168 Bytes bleibt stimmig |
| `resultLayer.ts` `resultTileTemplate` | `?tilesize=256` | 512 |
| `mosaic.ts` `TILE_LEVEL_AHEAD` | 1,5: Stufe L wird ab Kartenzoom L − 1,5 gefragt | 0,5. Gilt für `hideFrom` der Szenen unter einem Mosaik (`mosaic.ts`, `processingPreview.ts`), den Zoomhinweis (`zoomHint.ts`) und `fixtures/zoomMap.ts` |
| `processingPreview.ts` `previewMaxZoom`, `tileResolution` | Pixelgröße einer 256er-Kachel | eine Stufe tiefer, damit die Vorschau gröber als die Daten bleibt (Otto, 19.10.2026) |
| `resultLayer.ts` `isOverview`, `tileMetres` | Stufe und Pixelgröße für 256 px | für 512 px; sonst steht das Abzeichen „Overview“ eine Zoomstufe zu lang |
| `aoiClip.ts` `TILE_PX = 256` | Maske im 256er-Pixelraum | Pixelraum des geladenen Bildes (`bitmap.width`). Sonst schneidet der Zuschnitt einer 512er-Kachel nur das linke obere Viertel richtig zu |

Nicht betroffen: Basemaps (eigene Quellen mit eigener `tileSize`), Quicklooks (Bild-Overlays), die Abdeckungskarte (`coverage.ts`, eigenes Raster). Gespeichert wird keine Kachel-URL: Permalinks tragen Kennungen und Schlüssel, die Job-Ablage Job-Kennungen. Es gibt also nichts umzuschreiben.

### 9.2 Freigegebene Zoomstufen

- `ViewerInfo.min_zoom`/`max_zoom` sind Kachelstufen (`registry.py`). Eine Stufe deckt mit 512 px dieselbe Fläche, nur mit viermal so vielen Pixeln, und MapLibre fragt sie eine Kartenzoomstufe später. Die Prüfung im `tiler` (`_check_zoom_released`) bleibt gleich [P].
- Sentinel-2 (z0–z19) und DEM (z0–z15): unten ändert sich nichts. Oben überzoomt die Karte ab Kartenzoom 19,5 statt 18,5. Das kostet kaum etwas: Die native Stufe liegt weit darunter (Sentinel-2 bei 47° N: z13 mit 512 px), darüber liest eine Kachel nur kleinere Fenster derselben Blöcke. Auslegung (Vorschlag): Die Stufen bleiben, wie sie sind.
- Mosaik-Kachel ab z8 (`MIN_MOSAIC_ZOOM`): Die Grenze hängt an der Fläche einer Stufe (höchstens 9 Szenen bei z8, M4-17 §2.2) und gilt mit 512 px unverändert. Das Mosaik erscheint aber erst ab Kartenzoom 7,5 statt 6,5. Darunter zeigt die Karte die Einzelszenen in `earthx:order`, eine Zoomstufe länger als heute. Mit Stufe 7 käme das Mosaik wieder bei 6,5, eine Kachel berührte dann aber bis zu 13 Szenen [M aus M4-17] (Frage 3).

### 9.3 Grenzen der Mosaik-Kachel

- Szenen je Kachel (12), Items je URL (64), Assets je Szene mit Schritten (4), gleichzeitige Item-Abrufe (4): Sie hängen an der Fläche oder an der Quelle, nicht an den Pixeln, und bleiben.
- Eine Mosaik-Kachel kostet mit 512 px mehr: im Median 1,9 → 2,9 s ohne Leitungsgrenze, 1,9 → 7,4 s bei 100 Mbit/s [M]. Ein Zeitlimit je Kachel gibt es nicht; das TileJSON hat im Client 60 s (`MOSAIC_TILEJSON_TIMEOUT_MS`), es liest keine Pixel.

### 9.4 Statistik-Routen

Nicht betroffen. `statistics` liest die Übersicht mit höchstens 1024 px (`processing/tile.py`), die Statistik über die AOI (NM4-19) das Fenster des Auftrags. Keine hängt an der Kachelgröße [P].

### 9.5 TileJSON und `tileSize`

- Das Modell `TileJSON` von `titiler.core` 2.3.0 hat kein Feld `tileSize` [P], TileJSON 3.0 auch nicht. MapLibre nimmt `tileSize` aus der Quelle des Stils, nicht aus dem Dokument [P].
- Unser `tilejson.json` setzt `tilesize=512` in die URL unter `tiles`, wenn die Anfrage keine nennt (Vorgabe von TiTiler, `access/tiles.py` Z. 270–323) [P]. Heute gibt das Dokument also 512er-Kacheln aus, der Viewer zeichnet aber 256er aus eigenen Vorlagen. Das Frontend liest aus dem TileJSON nur `bounds`, `minzoom`, `maxzoom` und `earthx:order`.
- Nach der Umstellung passen beide zusammen. Ein Nachtrag in `adr/0006` hält fest, dass die Kachelgröße 512 ist und wo sie steht.

### 9.6 `tilesize` ist frei [M]

Alle Kachel-Routen nehmen jede `tilesize` größer 0 an. Gemessen an einer NDVI-Kachel z10 einer Szene, Quelle ohne Latenz:

| `tilesize` | Antwort | Zeit |
|---|---|---|
| 256 | 39 kB | 0,10 s |
| 512 | 206 kB | 0,26 s |
| 2048 | 4,5 MB | 4,5 s |
| 4096 | 10,5 MB | 12,6 s |

Eine einzelne Anfrage bindet so einen Thread und Speicher für Sekunden. Vorschlag: nur 256 und 512 zulassen, sonst `400` (Frage 2). Das verschärft eine Grenze und lockert keine.

## 10. Gilt die Umstellung für alle Kachel-Arten?

| Art | Wirkung von 512 px [M, A] |
|---|---|
| Szene (eine Ebene je Szene, auch Zeitreihen) | −7 bis −23 %, wenn viele Kacheln warten; +6 bis +11 % bei einer einzelnen Ebene oder `visual` mit begrenzter Leitung |
| Mosaik | −51 % bzw. −19 %: größter Gewinn |
| Vorschau (Item- und Mosaik-Kachel mit Schritten) | wie Szene bzw. Mosaik; die NDVI-Zeilen sind Vorschau-Kacheln |
| Ergebnis (aus dem eigenen Objektspeicher, eine Ebene) | ungemessen. Eine Ebene, die Quelle ist im selben Netz: wenig Gewinn, wenig Verlust [A] |

Gemischte Größen auf einer Karte gingen technisch, denn jede Quelle hat ihre eigene `tileSize`. Dann gälte aber `TILE_LEVEL_AHEAD` je Quelle, und die Szenen unter einem Mosaik müssten mit der Stufe des Mosaiks rechnen. Das ist eine zweite Regel an jeder Stelle aus §9.1, für einen Vorteil, der nur bei begrenzter Leitung auftritt.

## 11. Optionen und Empfehlung

| # | Option | Für | Gegen |
|---|---|---|---|
| **O1** | **512 px für alle vier Arten**, eine Konstante im Frontend | eine Regel; große Ansichten 1–15 s schneller; TileJSON und Viewer passen zusammen | bei begrenzter Leitung eine einzelne Ebene 0,3–0,5 s und `visual` über 13 Ebenen 2,5–3 s langsamer; +24–59 % Bytes zum Browser; ~1 % der Pixel wählen einen anderen Nachbarn (§8) |
| O2 | 512 px nur für Mosaik und Mosaik-Vorschau | größter Gewinn, Einzelszenen unverändert | zwei Kachelgrößen auf einer Karte, `TILE_LEVEL_AHEAD` je Quelle (§10); Zeitreihen mit vielen Ebenen gewinnen nichts |
| O3 | nicht umstellen | nichts zu tun | die längsten Wartezeiten bleiben (Mosaik 29 s, Zeitreihe 25 s) |

**Empfehlung: O1.** In allen fünf gemessenen Ansichten kommt die letzte Kachel ohne Leitungsgrenze 7–51 % früher, und die größten Gewinne liegen dort, wo heute am längsten gewartet wird (Mosaik, Zeitreihe, Vorschau). Langsamer wird es nur bei begrenzter Leitung: um 0,3–0,5 s bei einer einzelnen Ebene im schmalen Fenster und um rund 10 % bei `visual` über 13 Ebenen. Die Umstellung ist eine Konstante und die Stellen aus §9.1. Dazu `tilesize` auf 256 und 512 beschränken (§9.6).

## 12. Fragen an Otto

Kurz beantwortbar: je Frage eine Nummer.

**Frage 1 — Umstellen?**
1. Ja, 512 px für Szene, Mosaik, Vorschau und Ergebnis (O1). **(Empfehlung)**
2. Nur Mosaik und Mosaik-Vorschau (O2).
3. Nicht umstellen (O3); dann bleibt nur Frage 2.

**Frage 2 — `tilesize` am `tiler`?**
1. Nur 256 und 512, sonst `400`, auf allen Kachel-Routen und im TileJSON. 256 bleibt für API-Clients. **(Empfehlung)**
2. Nur 512.
3. Frei lassen wie heute.

**Frage 3 — Ab welchem Kartenzoom das Mosaik?**
1. `MIN_MOSAIC_ZOOM` bleibt 8. Das Mosaik erscheint ab Kartenzoom 7,5 statt 6,5, darunter die Einzelszenen wie heute. **(Empfehlung)**
2. Stufe 7, damit es wie heute bei 6,5 beginnt. Eine Kachel berührt dann bis zu 13 Szenen; `MAX_SCENES_PER_TILE` müsste auf 14 steigen, und eine Kachel kostet mehr.

**Frage 4 — Bitgleich-Tests?**
1. Die T1↔T2-Tests laufen für 256 und 512 px, weil beide ausgeliefert werden. Für den Zarr-Test mit 512 px steigt die Grenze von 2 auf 3 %; die strenge Bedingung „keine Abweichung außerhalb von 0,125 px an einer Grenze“ bleibt. **(Empfehlung)**
2. Nur noch 512 px.

**Frage 5 — Nachtrag zu den Abweichungen 512 ↔ 256 (§8)?**
1. Nachtrag in `adr/0014` §6.3: Die Zusage gilt je Kachelgröße; zwischen den Größen wählt `nearest` an ~1 % der Pixel einen anderen Nachbarn. **(Empfehlung)**
2. Zusätzlich eine eigene Aufgabe, die Warp-Toleranz der Kacheln auf 0 zu setzen (ändert alle Kacheln, Kosten erst messen).

## 13. Umsetzung nach Freigabe (O1, Fragen je Option 1)

Ein Branch, ein Draft-PR, kleine Commits; Richtwert unter 400 Zeilen ohne Messgerüst. Geschätzt rund 250 Zeilen, die Hälfte davon Tests.

1. **Frontend:** eine Konstante `TILE_SIZE = 512`, daraus `TILE_LEVEL_AHEAD` (0,5) abgeleitet. Dazu alle Stellen aus §9.1. Tests:
   - Jede Rasterquelle der App und jede Kachelvorlage nennt dieselbe Größe.
   - Stufe L erscheint ab Kartenzoom L − 0,5; ein Mosaik ab z8 löst die Einzelszenen bei 7,5 ab.
   - `previewMaxZoom` liegt eine Stufe tiefer.
   - Der AOI-Zuschnitt einer 512er-Kachel maskiert die ganze Kachel.
   - Am alten Code scheitern diese Tests.
2. **Backend:** `tilesize` nur 256 oder 512 auf Kachel-, Mosaik- und Ergebnis-Routen und im TileJSON (Frage 2), `400` mit Grund. Die T1↔T2-Tests der vier Klassen werden für 256 und 512 parametrisiert (Frage 4).
3. **Dokumente:** Nachträge in `adr/0006` (Kachelgröße 512, `tilesize` begrenzt, TileJSON) und `adr/0014` §6.3 (Raster je Kachelgröße, §8). Log-Zeile mit PR-Nummer.
4. **Messung nachher:** dieselben Zeilen wie §7.2 am neuen Code; die Zeilen mit 512 px sind schon die Vorhersage. Dazu `stitch.py` zur Bitgleichheit und `maplibre_tiles.cjs`.
5. **Browser** (Chromium der Sitzung, echter `tiler` des Messgerüsts, nachgestellte Suchantwort): hell und dunkel, 1280 px und 360 px breit. Geprüft wird:
   - Die Kachel-URLs tragen `tilesize=512`, die Bilder sind 512 px groß.
   - Die Zahl der Anfragen sinkt wie in §7.2.
   - Der AOI-Zuschnitt sitzt an der AOI.
   - Mosaik und Zoomhinweis wechseln bei den neuen Kartenzoomstufen.
6. Vor „fertig“: `main` holen, `ruff check backend`, `pytest`, `lint-imports`, Frontend `npm run lint`, `npx tsc -b`, `npm test`.

**Prüfanleitung für Otto (nach der Umsetzung, PowerShell 5.1 und Browser):**

```powershell
docker compose up -d --build tiler
# Eine Kachel-URL aus DevTools kopieren (Rechtsklick -> Copy -> Copy URL), sie traegt tilesize=512.
$url = "<Kachel-URL aus DevTools>"
(Invoke-WebRequest $url -UseBasicParsing).StatusCode                                   # 200
try { Invoke-WebRequest ($url -replace 'tilesize=512', 'tilesize=4096') -UseBasicParsing } catch { $_.Exception.Response.StatusCode.value__ }   # 400
```

Im Browser: DevTools → Network, Filter `tiles`, „Disable cache“ an, dieselbe Ansicht wie vorher öffnen (z. B. NDVI-Vorschau über mehrere Szenen). Zu vergleichen:
- die Zahl der Anfragen (etwa ein Drittel),
- „Finish“ in der Fußzeile,
- dass jede Kachel-URL `tilesize=512` trägt.

Mit einer AOI und „Crop“ muss der Rand des Zuschnitts an der AOI liegen, nicht nur im linken oberen Viertel einer Kachel.

## 14. Messanhang

### 14.1 Aufruf

Wie NM4-26 §17.1 (Postgres mit Migrationen, COGs aus `make_cogs.py`):

```bash
source .venv/bin/activate; set -a; source .env.test; set +a
export COGS=/tmp/tb/cogs OUT=/tmp/tb/out
for size in 256 512; do
  scripts/tile-bench/bench.sh ndvi13_$size --viewport 1280x800 --map-zoom 10.2 --tilesize $size
  MBIT=100 scripts/tile-bench/bench.sh ndvi13_${size}_100 --viewport 1280x800 --map-zoom 10.2 --tilesize $size
  scripts/tile-bench/bench.sh visual13_$size --mode visual --viewport 1280x800 --map-zoom 10.2 --tilesize $size
  scripts/tile-bench/bench.sh mosaic12_$size --mosaic --scenes 12 --viewport 1920x1080 --map-zoom 11.5 --tilesize $size
  scripts/tile-bench/bench.sh native1_$size --scenes 1 --viewport 1920x1080 --map-zoom 13 --tilesize $size
  scripts/tile-bench/bench.sh narrow1_$size --scenes 1 --viewport 360x640 --map-zoom 11.5 --tilesize $size
done
CLIENT=stitch.py scripts/tile-bench/bench.sh stitch --scenes 2     # 512 gegen 4 x 256
node scripts/tile-bench/maplibre_tiles.cjs                          # Kacheln je Ausschnitt in Chromium
```

Die Zeiten je Kachel (erste/Hälfte/alle) stehen in `$OUT/view_<tag>.jsonl` (Feld `ms`), die Bytes zum Browser im Feld `bytes`.

### 14.2 Warp-Toleranz

Direkt mit `rio_tiler.io.Reader` am synthetischen `B04.tif`, `nearest`, Mittelpunkt von `view.py`: 512er-Kachel z gegen die vier 256er z+1. Mit der Vorgabe weichen 175 (z10), 3058 (z13) und 188 (z15) von 262 144 Pixeln ab, mit `vrt_options={"tolerance": 1e-6}` keines. `tolerance=0` lehnt GDAL beim Anlegen des Warps ab.

### 14.3 Die Bitgleich-Tests auf 512 px

Lokal geändert und danach verworfen: `ZOOM = 13` statt 14, `tilesize=512` in den URLs der vier Testmodule und in `_job_tile`/`_job_bands`, 512 statt 256 in `_source_position` und `_tile_at`. Dann `pytest -k "NativeLevel or OnZarr"` über `test_tiler_operator.py`, `test_tiler_chain.py`, `test_tiler_mask_normalize.py` und `test_tiler_mosaic_operator.py`.

## 15. Freigabe (Otto, 28.10.2026)

1. **Umstellen:** Option 2. 512 px nur für Mosaik und Mosaik-Vorschau (Mosaik-Kachel ohne und mit Schritten); Szene, Item-Vorschau und Ergebnis bleiben bei 256 px. Begründung: Der Vorteil kommt aus der Grenze von 6 Verbindungen je Host bei HTTP/1.1.
   - **Wiedervorlage M6:** Mit HTTP/2 bzw. CDN vor dem `tiler` neu messen, ob 512 px für Mosaik und Mosaik-Vorschau dann noch schneller ist und ob es sich für weitere Kachel-Arten lohnt.
   - Die sieben Stellen aus §9.1 rechnen künftig mit der Kachelgröße der jeweiligen Quelle, nicht fest mit 256 px. Dazu gehört der AOI-Zuschnitt im Browser. TileJSON und Viewer passen zusammen.
2. **`tilesize`:** Option 1, nur 256 und 512, sonst `400`.
3. **Mosaik-Zoom:** Option 1, `MIN_MOSAIC_ZOOM` bleibt 8.
4. **Bitgleich-Tests:** Option 1, für 256 und 512 px; Zarr-Grenze für 512 px 3 %.
5. **Nachtrag:** Option 1, in `adr/0014` §6.3.

**Schnitt:** ein PR. Das Backend (Grenze für `tilesize`, Tests) kommt jetzt. Mit dem Frontend beginnt die Session erst, wenn Otto einen freien Frontend-Platz meldet.

## 16. Umsetzung Backend (28.10.2026)

- **`tilesize`:** `access/tiles.py` hat `TILE_SIZES = (256, 512)` und `tile_size_allowed`. Die Prüfung hängt als Abhängigkeit am Router von `EarthxTilerFactory` und gilt damit für jede Route der Fabriken von Szene, Mosaik und Ergebnis, auch für Statistik und TileJSON. Sie läuft vor der Pfad-Abhängigkeit: Für eine andere Größe wird kein Item geholt und keine Datei geöffnet, die Antwort ist `400` „tilesize is 256 or 512“.
- **TileJSON:** `EarthxTilerFactory.tile_size` ist die Größe, die das Dokument ausgibt, wenn die Anfrage keine nennt: 256 für Szene und Ergebnis, 512 für das Mosaik (`EarthxMosaicTilerFactory`). Bisher waren es 512 für alle.
- **Tests:**
  - `access/test_tile_size.py`: an einer Fabrik ohne Leser. Zehn falsche Schreibweisen auf vier Routen und zwei Größen in einer Anfrage ergeben `400`, ohne dass etwas geöffnet wird; 256, 512 und keine Größe kommen durch; jede Route prüft zuerst.
  - `api/test_tile_size_routes.py`: jede Route der echten App unter den drei Präfixen (aus dem OpenAPI-Schema) antwortet auf 4096 mit `400`.
  - Je Route Ende-zu-Ende: Szene (Größe der Kachel, TileJSON 256), Mosaik (nichts geholt bei 1024/4096, TileJSON 512, Kachel 512 px), Ergebnis (nichts gelesen, TileJSON 256).
  - Am alten Code scheitern 25 dieser Tests, das neue Modul unter `access` lädt nicht.
- **Bitgleich-Tests (Frage 4):** Die T1↔T2-Tests der vier Module laufen für 256 px auf z14 und für 512 px auf z13, 17 Fälle mehr, alle grün. Zarr: Grenze 3 % für 512 px; gegen den exakt nächsten Quellpixel ist bei 512 px eine Abweichung nur innerhalb von 0,125 px an einer Grenze erlaubt, bei 256 px keine.
- **Dokumente:** Nachtrag NM4-29 in `adr/0006` §5, `adr/0014` §15 Nachtrag NM4-29.
- **Offen:** das Frontend. Es ist die eigene Aufgabe NM4-29b (§17).

**Schnitt geändert (Otto, 28.10.2026, zu #227):** Der PR #227 enthält nur das Backend und wird so gemergt. Das Frontend ist die eigene Aufgabe NM4-29b (§17), in einer neuen Session.

## 17. NM4-29b Frontend

**Stufe A**, nur Frontend; der Plan ist freigegeben (§15). **Modell:** Sonnet, Effort hoch. **Start:** nach dem Merge von #227 (NM4-29 Backend), wenn Otto einen freien Frontend-Platz meldet. Nicht gleichzeitig mit anderen Aufgaben an `frontend/src/mapLayers.ts`, `mosaic.ts`, `processingPreview.ts`, `aoiClip.ts` oder `resultLayer.ts`.
**Startsatz:** „Führe Aufgabe NM4-29b aus `docs/plans/querschnitt/nm4-29-kacheln-512.md` §17 aus.“

**Ausgangslage.**

- **Messung (§7):** Der Browser öffnet über HTTP/1.1 höchstens 6 Verbindungen je Host; die Kacheln einer Ansicht warten dort in einer Schlange (NM4-26). Mit Kacheln von 512 statt 256 px fragt MapLibre für denselben Ausschnitt 2,2- bis 3-mal weniger Kacheln, jede ist aber teurer. Beim Mosaik lohnt das am meisten: Ein NDVI-Mosaik aus 12 Szenen auf 1920×1080 braucht 14,3 statt 29,1 s ohne Leitungsgrenze und 33,3 statt 41,0 s bei 100 Mbit/s. Bei einer einzelnen Ebene und begrenzter Leitung ist 512 px langsamer.
- **Entscheidung (§15):** 512 px nur für die **Mosaik-Kachel** und die **Mosaik-Vorschau** (Mosaik-Kachel mit Schritten). Szene, Item-Vorschau und Ergebnis bleiben bei 256 px. `MIN_MOSAIC_ZOOM` bleibt 8. Mit HTTP/2 bzw. CDN (M6) wird neu gemessen.
- **Backend (#227, §16):** Der `tiler` nimmt `tilesize` nur als 256 oder 512, sonst `400`. Ohne `tilesize` liefert die Kachel-Route weiter 256 px. Das TileJSON des Mosaiks nennt in `tiles` 512 px, das von Szene und Ergebnis 256 px.
- **MapLibre (§7.1):** Eine Rasterquelle wird ab Kartenzoom `round(z + log2(512 / tileSize))` auf Stufe L gefragt (maplibre-gl 5.24.0, `covering_tiles.ts`). Stufe L erscheint damit mit 256 px ab Kartenzoom L − 1,5, mit 512 px ab L − 0,5. Ein Mosaik ab z8 erscheint also ab Kartenzoom 7,5 statt 6,5. Darunter zeigt die Karte wie bisher die Einzelszenen in `earthx:order`.

**Umfang.**

1. **Kachelgröße je Quelle.** Jede Rasterquelle der App trägt ihre Größe; keine Stelle rechnet mehr fest mit 256 px. Mosaik und Mosaik-Vorschau bekommen 512 px, alles andere bleibt bei 256 px. Die Größe gehört zur Vorlage (`tilesize` in der URL) und zur Quelle (`tileSize` in MapLibre); beide müssen übereinstimmen. Die sieben Stellen (§9.1):
   1. `mapLayers.ts` `placeRaster` und `syncPreview`: `tileSize: 256` → die Größe der Quelle.
   2. `api.ts` `buildMosaicTileTemplate` und `buildMosaicOperatorTileTemplate`: `tilesize=512` in der URL. `buildTileTemplate` und `buildOperatorTileTemplate` bleiben ohne `tilesize` (256 px). Die Mosaik-URL wird damit 13 Bytes länger. `mosaicRequestBytes` zählt die Vorlage mit, die Grenze `MAX_MOSAIC_REQUEST_BYTES` (7168) bleibt stimmig.
   3. `resultLayer.ts` `resultTileTemplate`: bleibt `tilesize=256`, aus derselben Größe wie die Quelle des Ergebnisses statt als fester Text.
   4. `mosaic.ts` `TILE_LEVEL_AHEAD = 1.5` → abhängig von der Größe (1,5 bei 256 px, 0,5 bei 512 px). Benutzt in `hideFrom` der Einzelszenen unter einem Mosaik (`mosaic.ts`, `processingPreview.ts`), im Zoomhinweis (`zoomHint.ts`: `isDrawnAt`, `zoomInTo`) und in `fixtures/zoomMap.ts`. Unter einem Mosaik mit 512 px verschwinden die Einzelszenen ab Kartenzoom 7,5.
   5. `processingPreview.ts` `previewMaxZoom`, `tileResolution`: Pixelgröße der Kachel aus ihrer Größe. Die Mosaik-Vorschau endet eine Stufe tiefer, damit sie gröber als die Daten bleibt (Otto, 19.10.2026).
   6. `resultLayer.ts` `isOverview`, `tileMetres`: Stufe und Pixelgröße aus der Größe der Quelle (bleibt 256 px).
   7. `aoiClip.ts` `TILE_PX = 256`: die Maske im Pixelraum des geladenen Bildes (`bitmap.width`/`bitmap.height`). Sonst schneidet „AOI only“ eine 512er-Kachel nur im linken oberen Viertel richtig zu.
2. **Keine Migration:** Permalinks und Job-Ablage speichern keine Kachel-URL (§9.1); nichts umzuschreiben.
3. **Messung nachher:** dieselbe Mosaik-Ansicht wie §7.2 im echten Browser (Chromium der Sitzung, `tiler` aus `scripts/tile-bench`, nachgestellte Suchantwort), vorher (`main`) und nachher: Zahl der Kachelanfragen, Zeit bis zur letzten Kachel, Größe der Bilder. Dazu `scripts/tile-bench/bench.sh` mit `--mosaic --scenes 12 --viewport 1920x1080 --map-zoom 11.5` für 256 und 512 px am aktuellen `tiler` (Aufruf §14.1).

**Abnahme.**

- **Tests**, die am alten Code scheitern:
  - Jede Rasterquelle nennt in `tileSize` dieselbe Größe wie ihre Vorlage in `tilesize`: Mosaik und Mosaik-Vorschau 512, Szene, Item-Vorschau und Ergebnis 256.
  - Stufe L einer 512er-Quelle erscheint ab Kartenzoom L − 0,5, einer 256er ab L − 1,5. Unter einem Mosaik ab z8 verschwinden die Einzelszenen bei 7,5, und der Zoomhinweis nennt die richtige Stufe.
  - `previewMaxZoom` einer Mosaik-Vorschau liegt eine Stufe tiefer als die einer Item-Vorschau derselben Daten.
  - „AOI only“ auf einer 512er-Kachel maskiert die ganze Kachel an der AOI.
  - Die Längengrenze der Mosaik-URL rechnet `tilesize=512` mit.
- **Prüfung im echten Browser** (Chromium/Playwright der Sitzung, nicht nur jsdom), in Hell- und Dunkelmodus und bei schmalem Fenster (360 px), im PR beschrieben:
  - Mosaik-Kacheln tragen `tilesize=512` und sind 512 px groß; Szene, Item-Vorschau und Ergebnis bleiben bei 256 px.
  - Der Rand von „AOI only“ liegt an der AOI.
  - Mosaik und Einzelszenen wechseln bei Kartenzoom 7,5.
- **Messung vorher/nachher** (Umfang 3) im PR.
- **Prüfanleitung für Otto** (Browser und/oder PowerShell 5.1) im PR, z. B. DevTools → Network, Filter `tiles`: Zahl der Mosaik-Anfragen und „Finish“ vor und nach dem Wechsel, `tilesize=512` in den Mosaik-URLs.
- **Dokumente:** Nachtrag NM4-29b in `adr/0006` (Kachelgröße je Quelle im Frontend, Mosaik ab Kartenzoom 7,5); Log-Zeile mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern.
- Frontend `npm run lint`, `npx tsc -b --pretty false`, `npm test`; alle vier Pflicht-Checks der CI grün; vor „fertig“ ist `main` geholt.
- **Grenzen:** Oberflächentexte nur auf Englisch, wenig Text, Erklärungen im Tooltip (UI-01 §4). Keine neue Abhängigkeit ohne Frage an Otto. Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs. `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.
