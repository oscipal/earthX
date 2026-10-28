# NM4-04 — Mosaik mit Operator im Kachel-Pfad

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 4 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** sofort möglich; nicht gleichzeitig mit NM4-19 (beide ändern `tiler`-Routen).
**Startsatz:** „Führe Aufgabe NM4-04 aus `docs/plans/querschnitt/nm4-04-mosaik-mit-operator.md` aus.“

## 1. Anlass

M4-17 zeigt das Mosaik eines Überflugs als Kachel, M4-18b erlaubt Operator-Ketten in der Kachel – aber nur für ein einzelnes Item. Eine Vorschau des Mosaik-Jobs mit Band math (etwa NDVI über einen ganzen Überflug) fehlt (M4-17, Frage 4).

## 2. Soll

- Die Mosaik-Kachel nimmt dieselben Parameter `op`, `op_version`, `params` (wiederholbar, höchstens 4) wie die Item-Kachel.
- Tile ↔ Job bitgleich auf der nativen Ebene wie in `adr/0014` §6.3, für ein Mosaik-Rezept mit Band math.
- Das Panel zeigt die Vorschau für Mosaik-Aufträge („One job“ über einen Überflug).

## 3. Im Plan klären (mit Optionen und Empfehlung)

- Reihenfolge: erst Mosaik, dann Operator je Pixel, oder Operator je Szene und dann Mosaik? Der Job macht es auf eine bestimmte Weise – die Kachel muss genau dasselbe tun (Beleg am Code).
- Kosten je Kachel: bis 12 Items je Kachel (M4-17) mal Operator; Messung mit Quellen und Zahlen, Grenzen (Zoom, Items).
- Statistik für die Farbskala der Mosaik-Vorschau (M4-19c) – gleiche Route oder Grenze.
- URL-Länge bei vielen Items plus Parametern (414/431); keine AOI in der URL.

## 4. Grenzen

- Kein Zustand im `tiler` außer dem bestehenden Item-Cache (`adr/0001`).
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: Mosaik-Kachel mit Band math gleich Mosaik-Job (nativ, bitgleich); Kette mit `mask`; Abweisungen (zu viele Schritte, unbekanntes Band, Zoom zu klein) vor dem Abruf.
- Gegenprobe: Mit dem alten Code scheitern die neuen Tests.
- Nachtrag in `adr/0014` bzw. `adr/0006`.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n) mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat, siehe Kopf des Backlogs).
- Vor „fertig“ ist main geholt.

---

# Plan (27.10.2026)

Belegstufen wie in `adr/0009`: [M] gemessen, [P] am Primärdokument oder im Code gelesen, [S] Zusammenfassung oder Suchtreffer, [A] eigene Ableitung. Die Messskripte liegen unter `scripts/tile-bench/`, die Aufrufe stehen in §13.

## 6. Kurzfassung

- **Reihenfolge: erst Mosaik, dann Operator je Pixel.** So rechnet der Job [P]: je Asset ein Mosaik der Szenen (je Band und Pixel das erste gültige Element, in physikalischen Werten), dann die Assets zusammen, dann die Kerne der Schritte. Die Kachel muss genau das tun. Die heutige Vorschau im Panel macht es umgekehrt (Operator je Szene, dann gestapelt). Bei `mask` ist das ein anderes Produkt: Der Job lässt eine Wolke der ersten Szene als Loch stehen, die Vorschau füllt sie aus der nächsten.
- **Umsetzung:** ein Lesen mit `mosaic_reader` und `FirstMethod` über die Szenen, je Szene die Assets in physikalischen Werten zusammengelegt. `FirstMethod` wählt je Band und Pixel [P], das ist dieselbe Regel wie `merge_first_valid` des Jobs. Danach die Kerne als `process_dependency`, wie bei der Item-Kachel. Kein Zustand, keine neue Abhängigkeit.
- **Bitgleich gilt für Szenen auf dem Raster des Mosaiks** (Ziel-CRS, gleiches Pixelraster), wie bei der Item-Kachel auf der nativen Ebene. Eine Szene der anderen UTM-Zone verzerrt der Job zweimal (auf das Mosaikraster, beim Vergleich auf die Kachel), die Kachel einmal. Dort stimmen nur ~56 % der Pixel überein [M]. Das gilt schon heute für die Mosaik-Kachel ohne Operator. Frage 2.
- **Kosten:** Eine Mosaik-Kachel mit Operator liest höchstens, was die heutige Vorschau je Szene für dieselbe Kartenkachel liest, aber in einer Anfrage statt in bis zu 12. Lokal kostet NDVI 1,3–1,8 × und `mask → band_math` 1,5–1,9 × die Mosaik-Kachel ohne Operator [M]. Vorschlag: höchstens 4 Assets je Mosaik-Kachel mit Operator, also höchstens 48 geöffnete Dateien je Kachel (Frage 3).
- **Farbskala:** keine Statistik auf der Mosaik-Route. Die Messung bleibt auf einer Szene, künftig der ersten in Mosaik-Reihenfolge. Die Messung über AOI und Mosaik gehört zu NM4-19 (Frage 4).
- **URL:** typisch 2,5–4,7 kB; im ungünstigsten Fall rund 30 kB. Der `tiler` nimmt bis 65 535 Byte [M], ein späterer Proxy oder ein CDN oft nur 8 kB [S]. Vorschlag: Obergrenze von 7 168 Byte für die Anfrage einer Mosaik-Kachel, `414` vor dem ersten Item-Abruf; das Panel fällt dann auf die Vorschau je Szene zurück (Frage 5).
- **Schnitt:** zwei PRs, Backend und Frontend (Frage 7).

## 7. Befunde

### 7.1 Wie der Mosaik-Job rechnet [P]

1. `processing/mosaic.py` `open_mosaic` (Z. 246–292) öffnet jede Szene je Asset und gibt **je Asset eine** `MosaicSource` zurück.
2. `MosaicSource.read` (Z. 218) liest jede Szene über `Source.read`, also in physikalischen Werten, und mischt mit `merge_first_valid`: je Band und Pixel das erste gültige Element in der Reihenfolge des Rezepts.
3. `processing/core.py` `_run_pass` (Z. 545): `merge_images([source.read(…) for source in sources])` legt die Mosaike der Assets zu einem Bild zusammen; erst dann laufen die Kerne der Schritte (`_pixel_kernels`).

Der Job rechnet also: **Mosaik je Asset und Band → Assets zusammen → Operator je Pixel.** `_check_alike` (Z. 230) verlangt dabei, dass alle Szenen in Bandnamen, Datentyp, nodata, Einheit und Skalierung übereinstimmen, sonst `UnsupportedRecipe`.

### 7.2 Warum die Reihenfolge zählt [A]

- **NDVI:** Fehlt in Szene A an einem Pixel nur `nir`, nimmt der Job `red` aus A und `nir` aus B. Operator je Szene gäbe dort ein Loch in A und füllt das Pixel ganz aus B. Bei Sentinel-2 fallen nodata der Bänder fast immer zusammen; am Rand eines 20-m-Assets neben 10-m-Bändern aber nicht.
- **`mask → band_math`:** Der Job mischt zuerst die SCL. Trägt die erste Szene an einem Pixel eine Wolke, fällt das Pixel aus, auch wenn die zweite Szene dort klar ist. Operator je Szene maskiert in A, dann füllt B das Loch. Das ist ein wolkenfreies Komposit, also ein anderes Produkt.
- **Die heutige Vorschau** (`frontend/src/processingPreview.ts` `previewSpec`, Z. 248ff.) legt je Szene eine eigene Kachel-URL mit den Schritten an und stapelt sie; sie rechnet also „Operator je Szene, dann Mosaik“, in Auswahlreihenfolge statt in Mosaik-Reihenfolge (M4-17 §2.1). An Überlappungen weicht sie damit vom Job ab.

### 7.3 Dieselbe Regel in einem Lesen [P]

- rio-tiler 9.4.6, `FirstMethod.feed`: `pidex = self.mosaic.mask & ~array.mask` über das ganze Feld (Bänder × Zeilen × Spalten). Gewählt wird je **Band** und Pixel, wie in `merge_first_valid` (`access/crop_rules.py` Z. 416ff.).
- Folge: Ein Mosaik über die Szenen, in dem jede Szene ihre Assets schon zusammengelegt trägt, ist dasselbe wie je Asset ein Mosaik und danach zusammenlegen. Die Kachel kann deshalb **ein** `mosaic_reader` über die Szenen nehmen, mit Portionen zu 4 und „fertig, sobald jedes Pixel jedes Bandes gefüllt ist“ (M4-17 Frage 5).
- Physikalische Werte vor dem Mischen: Der Job skaliert je Szene vor `merge_first_valid`. Die Kachel tut dasselbe (`Source.read_tile` → `physical`). Weil alle Szenen dieselbe Skalierung tragen müssen (`_check_alike`), muss die Kachel auch diese Prüfung machen, sonst zeigte sie ein Mosaik, das der Job ablehnt.

### 7.4 Wo bitgleich gilt [M]

- **Szenen auf dem Raster des Mosaiks** (gleiches CRS, gleiche Pixelgröße, Ursprung um ganze Pixel versetzt; `processing/mosaic.py` `lies_on_grid`) liest der Job ohne Warp. Die Kachel liest jede davon mit `nearest` direkt auf das Kachelraster. Beide wählen je Kachelpixel dieselbe Zelle desselben Gitters; der Vergleich nach `adr/0014` §6.4 (Job mit `nearest` auf das Kachelraster) ist bitgleich wie bei der Item-Kachel [A, Test in §10].
- **Szenen außerhalb des Rasters** (andere UTM-Zone): Der Job verzerrt sie mit `nearest` auf das Mosaikraster; der Vergleich bringt das Ergebnis noch einmal mit `nearest` auf die Kachel. Die Kachel verzerrt einmal. Gemessen an einer Szene in EPSG:32633 am Westrand der Zone, Werte eindeutig je Pixel, je 9 Kacheln: **z13 56,3 %, z14 56,2 %** identische gültige Pixel (§13.2). Jede Abweichung ist höchstens ein Pixel der Quelle daneben (gemessen), also ein Nachbarpixel derselben Szene.
- Das gilt heute schon für die Mosaik-Kachel ohne Operator. M4-17 prüft dort deshalb nur „dieselbe Szene gewinnt an denselben Stellen“ (`test_tiler_mosaic.py::TestTheRuleOfTheMosaicJob`), keine Bitgleichheit.
- Der einzige Weg zur Bitgleichheit auch dort wäre, in der Kachel das Raster des Jobs nachzubauen (Fenster des Mosaikrasters lesen, dann auf die Kachel verzerren). Unterhalb der nativen Ebene müsste die Kachel dafür die volle Auflösung lesen; bei z8 sind das bis zu 15 000² Pixel je Asset. Nicht tragbar (Frage 2, Option 3).

### 7.5 Kosten je Kachel [M, A]

**Lokal gemessen** (§13.1): 4 Kerne, synthetische COGs wie Sentinel-2 (10 m, `uint16` mit `scale`/`offset`, Blöcke 1024, 2048² Pixel; SCL 20 m), lokale Dateien, warmer Dateicache, `boto3` beiseite wie im Image (NM4-26 §8.1). Kachel z14, 256 px, Portionen zu 4. „best“: die erste Szene füllt die Kachel; „worst“: jede Szene füllt nur einen Streifen, alle werden gelesen. Median aus 15 Läufen in ms:

| Szenen | Fall | ohne Operator (M4-17) | NDVI (`red`, `nir`) | `mask → band_math` (+ `scl`) |
|---|---|---|---|---|
| 1 | best | 54 | 96 | 103 |
| 2 | best / worst | 73 / 61 | 127 / 101 | 134 / 113 |
| 4 | best / worst | 124 / 95 | 160 / 127 | 192 / 155 |
| 8 | best / worst | 111 / 190 | 173 / 258 | 192 / 311 |
| 12 | best / worst | 122 / 192 | 177 / 257 | 192 / 324 |

- Mit Operator kostet die Kachel 1,3–1,8 × (NDVI) bzw. 1,5–1,9 × (Kette) der Mosaik-Kachel ohne Operator. Der Kern selbst ist klein (NDVI 15 ms auf 1024², `adr/0014` §15m, also rund 1 ms auf 256²); der Aufschlag kommt vom zweiten und dritten Asset je Szene und vom Skalieren auf `float32`.
- „best“ mit 4, 8 oder 12 Szenen kostet gleich viel: Die erste Portion liest 4 Szenen parallel, danach ist die Kachel voll.
- Der schlimmste lokale Fall (12 Szenen, alle gelesen, 3 Assets) braucht 324 ms. Lokal begrenzt die CPU, im Betrieb das Netz (unten).

**Netz [A]** aus den gemessenen Zahlen von `adr/0006` §3.4 und NM4-26 §8: Eine kalte Szene kostet je Asset rund 1 s (Kopf und Verbindung), warm 54–193 ms je Kachel. Die Mosaik-Kachel öffnet je Portion 4 Szenen gleichzeitig, je Szene alle Assets nacheinander. Kalt, 12 Szenen × 3 Assets: 3 Portionen × 3 Assets × ~1 s ≈ **9 s** für die erste Kachel. Danach liegen die Köpfe im `/vsicurl/`-Cache von 256 MiB (NM4-26), und es zählen die Bytes. Die heutige Vorschau je Szene braucht für dieselbe Kartenkachel dieselben Bytes, aber 12 Anfragen statt einer. Im Browser stehen davon je 6 in der Schlange (NM4-26 B1). An Bytes wird es also nicht teurer, eher billiger, weil die Mosaik-Kachel nach einer gefüllten Portion aufhört.

**Grenzen heute:** höchstens 12 Szenen je Kachel, ab z8, 64 Items je URL (M4-17 §5). Die Item-Kachel mit Operator nimmt bis 16 Assets. Zusammen wären das bis 192 geöffnete Dateien in einer Anfrage (Frage 3).

### 7.6 Statistik für die Farbskala (M4-19c) [P]

- Die Vorschau misst heute die **erste Szene der Auswahl** über `/statistics` der Item-Route mit den Schritten (`processingPreview.ts` Z. 258, `OperatorTileReader.preview`, höchstens 1024 px).
- Die Mosaik-Fabrik hat absichtlich keine `/statistics` („a route nobody needs is a route nobody secures“, `access/mosaic_tiles.py`).
- Eine Statistik über das ganze Mosaik läse bei 64 Szenen × 3 Assets 192 Dateien über ihre Übersichten [A]: kalt bei 4 gleichzeitigen Abrufen rund 50 s.
- NM4-19 (Auto stretch über die AOI) nennt „Mehrere Szenen bzw. Mosaik eines Überflugs“ als eigenen Klärungspunkt und darf nicht gleichzeitig laufen.

### 7.7 URL-Länge [M, P]

| Was | Länge |
|---|---|
| Sentinel-2 C1, 64 IDs à 30 Zeichen, `red`+`nir`, NDVI, `rescale`, Colormap | 2 546 Byte |
| dasselbe mit `scl` und `mask → band_math → normalize` | 2 798 Byte |
| Zarr, 64 IDs à 60 Zeichen, 3 Assets, dieselbe Kette | 4 746 Byte |
| ungünstigster Fall: 64 × 60, 16 Assets, 4 × `params` à 2 048 Zeichen, alle Zeichen escaped | ~30 kB |

Grenzen:

- uvicorn 0.54 mit `httptools` 0.8 (Vorgabe, wenn installiert; so im Image): Ziel der Anfrage bis **65 535 Byte**, ab 65 536 `400` [M]. Mit `h11` bis 127 920 Byte [M]; dokumentiert sind dort 16 384 Byte je unvollständigem Ereignis (M4-17 §2.7), die Grenze greift offenbar nur, solange die Anfrage nicht ganz angekommen ist [A].
- nginx `large_client_header_buffers` Vorgabe `4 8k`: Anfragezeile über 8 kB → `414`; CloudFront und Fastly 8 kB (M4-17 §2.7) [P, S].
- Eine AOI steht nie in der URL; die Kachel braucht keine (`adr/0014` §6.2).

### 7.8 Frontend heute [P]

- `mosaic.ts` zeigt einen Überflug ab z8 als Mosaik-Kachel und darunter die Einzelszenen in `earthx:order` gestapelt (M4-17c). Die Reihenfolge kommt aus dem TileJSON.
- Die Vorschau (`processingPreview.ts`) kennt nur Einzelszenen, höchstens 40, je Szene eine URL mit den Schritten. Sie fragt das TileJSON der ersten Szene als Probe für die Kette (`probeChain`) und deren Statistik für die Farbskala.
- `orderView` (`processingStore.ts` Z. 402ff.): Bei „One job“ ist der Überflug `chosen`; bei „One job per pass“ oder „per scene“ hängt die Vorschau heute alle Szenen aller Einheiten an.

## 8. Optionen und Empfehlung

### 8.1 Reihenfolge (Frage 1)

| | Option | gleich Job | Aufwand | Bewertung |
|---|---|---|---|---|
| **R1** | **Erst Mosaik je Band, dann Operator je Pixel** (wie der Job, §7.1) | ja | ein Reader in `processing/tile.py`, Route in `api` | **Empfehlung** |
| R2 | Operator je Szene, dann Mosaik (wie die heutige Vorschau) | nein, an Überlappungen und bei `mask` grundsätzlich (§7.2) | klein | verworfen |
| R3 | Den Job auf R2 umstellen | — | ändert Ergebnisse und Hash bestehender Rezepte, `earthx.__version__`; das wolkenfreie Komposit wäre ein eigenes Produkt | nicht in dieser Aufgabe |

**Wie R1 liest (Vorschlag):**

1. `api` prüft wie bisher (Lizenz, Zoom, Form der Anfrage, Länge, Schritte), holt die Items, prüft den Überflug und die Gleichheit der Bänder und Skalierung über **alle** Items der URL (aus den Item-Metadaten, ohne eine Datei zu öffnen), sortiert nach `mosaic_order`, filtert nach Footprint und gibt die Szenen mit je Asset `ResolvedInput` und geprüfter Adresse weiter.
2. `processing/tile.py` bekommt einen `MosaicOperatorTileReader`. Er öffnet in `__enter__` nur die erste Szene. Daraus kommen Bandnamen und Einheiten, und die Schritte werden der Reihe nach geprüft (`transform`), bevor das erste Pixel gelesen wird.
3. Je Szene liest er in einem Thread alle Assets über `Source.read_tile` (physikalisch, `nearest`), legt sie zusammen (`merge_images`) und prüft sie gegen die erste Szene (wie `_check_alike`, sonst `422`). `mosaic_reader` mit `FirstMethod`, `threads=4`, `chunk_size=4` mischt; nur `TileOutsideBounds` überspringt eine Szene. Die GDAL-Konfiguration der Route geht in jeden Thread mit, wie bei `MosaicTileReader`.
4. Die Kerne laufen als `process_dependency` der Mosaik-Fabrik, dieselbe Funktion wie bei der Item-Kachel (`operator_post_process`). `_no_post_process` gilt nur noch ohne `op`.
5. `access` importiert weiter nichts aus `processing`. Der Reader kommt über die Fabrik von `api` herein, wie bei der Item-Kachel (`_open_reader`); `processing` lädt der `tiler` erst bei der ersten Kachel mit `op` (`test_tiler_start_is_light`).

### 8.2 Bitgleichheit bei Szenen außerhalb des Rasters (Frage 2)

| | Option | Bewertung |
|---|---|---|
| **B1** | **Bitgleich zugesagt und getestet für Szenen auf dem Mosaikraster.** Szenen der anderen Zone: „dieselbe Szene gewinnt an denselben Stellen“ wie in M4-17; Nachtrag in `adr/0014` §6.3 mit der Messung aus §7.4 | **Empfehlung**; ehrlich, kein Mehraufwand |
| B2 | Die Mosaik-Kachel mit Operator nur dann liefern, wenn alle berührten Szenen auf dem Raster liegen; sonst `422` | schützt die Zusage, zeigt aber an jeder Zonengrenze nichts |
| B3 | Das Raster des Jobs in der Kachel nachbauen (§7.4 letzter Punkt) | unterhalb der nativen Ebene nicht tragbar |

### 8.3 Kosten und Grenzen (Frage 3)

| | Option | Dateien je Kachel höchstens | Bewertung |
|---|---|---|---|
| **K1** | **Höchstens 4 Assets je Mosaik-Kachel mit Operator**; 12 Szenen je Kachel und z8 bleiben. Mehr Assets: `400` vor dem ersten Item-Abruf; das Panel zeigt dann die Vorschau je Szene | 48 | **Empfehlung**: deckt NDVI (2), `mask → band_math` (3) und EVI mit Maske (4) |
| K2 | Wie die Item-Kachel: bis 16 Assets | 192 | eine Anfrage kann kalt Minuten brauchen |
| K3 | Mit Operator erst ab z10 (dort bis 8 Szenen je Kachel, M4-17 §2.2) | 128 bei 16 Assets | weniger Vorschau beim Herauszoomen, ohne die Spitze wirklich zu senken |

### 8.4 Statistik für die Farbskala (Frage 4)

| | Option | Bewertung |
|---|---|---|
| **S1** | **Keine Statistik auf der Mosaik-Route.** Die Vorschau misst weiter eine Szene über die Item-Route, künftig die **erste in Mosaik-Reihenfolge** (`earthx:order[0]` aus dem TileJSON der Probe). Das ist die Szene, die an Überlappungen gewinnt. Mosaik und AOI klärt NM4-19 | **Empfehlung** |
| S2 | `/statistics` mit `op` auf der Mosaik-Route über die ganze Fläche, höchstens 1024 px | bis 192 Dateien je Messung, kalt ~50 s (§7.6); überschneidet sich mit NM4-19 |
| S3 | Wie heute: die erste Szene der Auswahl | kann eine Szene sein, die im Mosaik nirgends gewinnt |

### 8.5 URL-Länge (Frage 5)

| | Option | Bewertung |
|---|---|---|
| **U1** | **Obergrenze 7 168 Byte für die Anfrage einer Mosaik-Kachel** (Pfad und Query, wie sie ankommen), mit und ohne `op`. Darüber `414` vor dem ersten Item-Abruf. Das Frontend rechnet dieselbe Länge und zeigt darüber die Vorschau je Szene, mit Hinweis im Tooltip | **Empfehlung**: Was lokal geht, geht später auch hinter nginx oder einem CDN mit 8 kB; 1 kB Luft für Präfix und Anfragezeile |
| U2 | Keine eigene Grenze: bis 65 535 Byte (httptools) | geht lokal, scheitert später mit einem `414`, den nicht die App schreibt |
| U3 | Liste und Schritte im Body (`POST`) | nicht cachebar; widerspricht `adr/0006` §5 |

### 8.6 Panel (Frage 6)

| | Option | Bewertung |
|---|---|---|
| **P1** | **„One job“ über einen Überflug mit 2 bis 64 Szenen:** ab z8 die Mosaik-Kachel mit den Schritten, darunter die Einzelszenen mit denselben Schritten in `earthx:order` gestapelt (wie M4-17c). Die Probe der Kette fragt das TileJSON des Mosaiks; es liefert auch `earthx:order`. Rückfall auf die heutige Vorschau je Szene, mit Hinweis im Tooltip: mehr als 4 Assets, URL über der Grenze, über 64 Szenen, Datensatz nur unter z8 freigegeben, Mosaik abgewiesen | **Empfehlung** |
| P2 | Wie P1, aber unter z8 nichts | beim Herauszoomen leer |
| P3 | Nur das Backend jetzt, das Panel später | erfüllt das Soll nicht |

**KE-P (gilt, sofern du nicht widersprichst):** Bei „One job per pass“ zeigt die Vorschau jeden Überflug als eigenes Mosaik, denn jeder dieser Jobs ist ein Mosaik. Ein Überflug mit einer Szene und „One job per scene“ bleiben bei der Vorschau je Szene.

## 9. Kleinentscheidungen

Gelten, sofern du nicht widersprichst:

- **KE1 „Vor dem Abruf“:** Zu viele Schritte, unbekannter Operator, Operator ohne `T1`/`pixel`, ungültige `params`, zu viele Assets, Zoom unter z8 und eine zu lange URL werden **vor dem ersten Item-Abruf** abgewiesen; der Test zählt die Abrufe bei der Quelle (0). Ein **unbekanntes Band** lässt sich erst prüfen, wenn das Item sagt, wie viele Bänder ein Asset hat. Es wird deshalb nach dem Item-Abruf, aber **vor dem Öffnen der ersten Datei** abgewiesen, aus den Item-Metadaten wie `check_bands` der Annahme. Der Test zählt die geöffneten Dateien (0). Sagt das Item nichts über die Bänder, prüft der Reader vor dem ersten Pixel (wie bei der Item-Kachel).
- **KE2 Gleiche Ablehnungen wie die Annahme:** Mit `op` weist die Mosaik-Kachel ab, was die Annahme des Mosaik-Jobs abweist: einen Datensatz ohne `reprojection` (`api/intake.py` `_one_overpass`) und Zarr-Szenen in zwei CRS (`check_scope`), mit demselben Text, `422`. Ohne `op` bleibt alles wie in M4-17 (KE1 dort).
- **KE3 Wortlaut und Platz:** Die Ablehnung eines Schritts nennt ab zwei Schritten den Platz („step 1: …“) wie die Item-Kachel; das Panel liest sie unverändert (`refusedStepOf`).
- **KE4 TileJSON:** Das TileJSON der Mosaik-Kachel mit `op` trägt wie bisher `earthx:order` und dieselben Ablehnungen wie die Kachel. Es ist die billige Probe für das Panel.
- **KE5 Log:** Die bestehende Zeile „mosaic tile reads N of M scenes“ bleibt die einzige; keine Parameter, kein Ausdruck, keine Koordinate.

## 10. Tests (Abnahme)

Backend (`pytest`, synthetische COGs, wie `test_tiler_mosaic.py` und `processing/test_mosaic.py`):

1. **Band math bitgleich:** Szenen A und B in Zone 32 auf einem Raster, überlappend, Assets `red` und `nir` mit `scale`/`offset`. In der Überlappung fehlt in A an einigen Pixeln nur `nir`. Kachel auf der nativen Ebene über die echte Route gegen den Mosaik-Job (`run`) mit `nearest` auf das Kachelraster: gleiche gültige Pixel (`numpy.array_equal`), gleiche Maske. Damit ist auch belegt, dass `red` aus A und `nir` aus B kommt.
2. **Kette `mask → band_math` bitgleich:** zusätzlich `scl` (20 m), Wolke in A in der Überlappung, B dort klar. Kachel gleich Job, also ein Loch, kein Pixel aus B.
3. **Abweisungen vor dem Abruf (KE1):** 5 Schritte, 5 Assets, z7, unbekannter Operator, `reproject`, ungültige `params`, URL über 7 168 Byte → `400`/`422`/`414`, 0 Item-Abrufe. Unbekanntes Band → `422` mit Platz, 0 geöffnete Dateien.
4. **Gleiche Ablehnungen wie der Job (KE2):** verschiedene Skalierung der Szenen, Datensatz ohne `reprojection`, Zarr in zwei CRS → `422`.
5. **Andere Zone:** Szene in Zone 33: dieselbe Szene gewinnt wie im Job (wie M4-17), keine Bitgleichheit verlangt.
6. **Zweckfremd und fehlerhaft:** `expression`/`algorithm` auf der Mosaik-Route weiter `400`; `op` ohne `params`; `params` doppelt so oft wie `op`; mehrere Assets ohne `op` weiter `400`; `bbox`, `aoi` weiter `400`; Mosaik-Kachel mit `op` und einer Szene → `400` (2 bis 64).
7. **Zustandslos:** zwei frische Apps, dieselbe URL mit `op` → dieselben Bytes.
8. **URL-Länge:** 64 IDs à 60 Zeichen plus die Kette aus §7.7 gehen durch den echten Server (uvicorn, `httptools`); 7 169 Byte → `414`.
9. **Start bleibt leicht:** `test_tiler_start_is_light` grün; OpenAPI ohne `url`, `aoi`, `bbox`.
10. **Gegenprobe:** Die Tests 1–4 und 6–8 laufen gegen den Code vor der Änderung und scheitern dort (heute: `op` auf der Mosaik-Route → `400` „a mosaic tile takes item, asset and the parameters of its display only“).

Frontend (`vitest`):

11. „One job“ über einen Überflug: eine Mosaik-URL mit sortierten `item`, den Assets und den Schritten; unter z8 Einzelszenen in `earthx:order`; Messung über `earthx:order[0]`.
12. Rückfälle (P1): 5 Assets, URL über der Grenze, 65 Szenen, eine Szene, Datensatz unter z8, abgewiesenes Mosaik → Vorschau je Szene, Hinweis im Tooltip. „One job per pass“: je Überflug ein Mosaik (KE-P).

## 11. Fragen an Otto

Kurz beantwortbar: je Frage eine Nummer.

**Frage 1 — Reihenfolge**
1. Erst Mosaik je Band, dann Operator je Pixel, wie der Job (R1). **(Empfehlung)**
2. Operator je Szene, dann Mosaik (R2): weicht vom Job ab.
3. Den Job umstellen (R3): eigene Aufgabe.

**Frage 2 — Szenen der anderen UTM-Zone**
1. Bitgleich nur für Szenen auf dem Mosaikraster; sonst „dieselbe Szene gewinnt“; Nachtrag in `adr/0014` mit den 56 % (B1). **(Empfehlung)**
2. Mosaik-Kachel mit Operator an Zonengrenzen abweisen (B2).

**Frage 3 — Grenze für Assets**
1. Höchstens 4 Assets je Mosaik-Kachel mit Operator; 12 Szenen und z8 bleiben (K1). **(Empfehlung)**
2. 16 wie die Item-Kachel (K2).
3. Mit Operator erst ab z10 (K3).

**Frage 4 — Farbskala**
1. Keine Statistik auf der Mosaik-Route; Messung über die erste Szene in Mosaik-Reihenfolge; Mosaik und AOI in NM4-19 (S1). **(Empfehlung)**
2. Statistik über das ganze Mosaik (S2).
3. Wie heute, erste Szene der Auswahl (S3).

**Frage 5 — URL-Länge**
1. 7 168 Byte für jede Mosaik-Kachel, `414` vor dem Abruf, Rückfall im Panel (U1). **(Empfehlung)**
2. Keine eigene Grenze (U2).

**Frage 6 — Panel**
1. Mosaik ab z8, darunter Einzelszenen in `earthx:order`, Rückfall je Szene mit Hinweis (P1). **(Empfehlung)**
2. Unter z8 nichts (P2).

**Frage 7 — Schnitt** (Schätzung: Backend ~260 Zeilen Code und ~330 Zeilen Tests; Frontend ~150 und ~150; Doku ~60)
1. Zwei PRs in dieser Session: NM4-04a Backend (Reader, Route, Grenzen, `adr/0014`/`adr/0006`), danach NM4-04b Frontend (Panel, Rückfälle) auf NM4-04a gestapelt. **(Empfehlung)**
2. Ein PR mit rund 950 Zeilen.
3. Zwei PRs, NM4-04b erst nach dem Merge von NM4-04a in einer neuen Session.

## 12. Umsetzung nach Freigabe

Ersetzt durch §14 (Freigabe), §15 (NM4-04b Frontend) und §16 (Umsetzung des Backends). Laut Frage 7, Option 3 setzt diese Session nur das Backend um.

## 13. Messanhang

### 13.1 Kosten je Kachel (§7.5)

`scripts/tile-bench/mosaic_op_cost.py`: rio-tiler `Reader` und `mosaic_reader` wie `access/mosaic_tiles.py`, der Operator-Kern aus `earthx.processing.operators.REGISTRY` (`band_math` v1, `mask` v1). „raw“ ist die Mosaik-Kachel von M4-17 (ein Asset, Rohwerte); „op“ und „chain“ lesen je Szene die Assets, skalieren auf `float32`, mischen mit `FirstMethod` und rechnen danach den Kern. Ohne PNG-Kodierung, ohne Netz.

```bash
PYTHONPATH=backend python -W ignore scripts/tile-bench/mosaic_op_cost.py
```

### 13.2 Szene außerhalb des Rasters (§7.4)

`scripts/tile-bench/off_grid_identity.py` (Aufruf `python -W ignore scripts/tile-bench/off_grid_identity.py`): Szene 3000² Pixel in EPSG:32633 ab Ostwert 300 000, Werte eindeutig je Pixel (`uint32`-Rampe). (a) `Reader.tile` mit `nearest` direkt; (b) `WarpedVRT` mit `nearest` und `tolerance` 0,125 auf ein 10-m-Raster in EPSG:32632, dann `Reader.tile` mit `nearest`. Je 9 Kacheln um die Mitte auf z13 und z14; gezählt werden gleiche Werte unter den in beiden gültigen Pixeln und der größte Versatz in Pixeln der Quelle (Zeile/Spalte aus dem Wert zurückgerechnet): 1.

### 13.3 URL-Länge (§7.7)

`scripts/tile-bench/url_length.py` kodiert wie `URLSearchParams` (`python -I scripts/tile-bench/url_length.py`). `scripts/tile-bench/url_limit.py` startet `uvicorn` 0.54 mit einer leeren ASGI-App (`--http auto`, also `httptools` 0.8, und `--http h11`), schickt Anfragen wachsender Länge und sucht die Grenze durch Halbieren: `httptools` größtes angenommenes Ziel 65 535 Byte, ab 65 536 `400 Bad Request`; `h11` 127 920 Byte.

Eine Wiederholung von `mosaic_op_cost.py` aus dem Repo am 27.10.2026 ergab Werte innerhalb von ±15 % der Tabelle in §7.5 (z. B. 12 Szenen, alle gelesen: 183 / 243 / 282 ms).

## 14. Freigabe (Otto, 27.10.2026, zu #215)

1. Option 1: Reihenfolge wie der Job (erst Mosaik je Asset und Band, dann Operator).
2. Option 1: bitgleich nur auf dem Mosaikraster, sonst „dieselbe Szene gewinnt“.
3. Option 1: höchstens 4 Assets mit Operator. Darüber derselbe Rückfall wie bei 5.
4. Option 1: Farbskala über die erste Szene in Mosaik-Reihenfolge; Mosaik und AOI in NM4-19.
5. Option 1: höchstens 7 168 Byte, darüber `414` vor dem Abruf, Rückfall auf die Vorschau je Szene. Der Rückfall ist erkennbar: ein kurzer Hinweis im Tooltip der Vorschau, etwa „Preview per scene – may differ from the job where scenes overlap“. Kein Text im Panel.
6. Option 1: ab z8 Mosaik, darunter Einzelszenen in Mosaik-Reihenfolge.
7. Option 3: Diese Session setzt nur das Backend um (ein PR, #215). Das Frontend folgt nach dem Merge als neue Aufgabe in einer neuen Session (§15).

KE1–KE5 und KE-P angenommen. Dazu: Backlog nicht in dieser Aufgabe pflegen (das tut der Planungs-Chat), Messskripte nach `scripts/tile-bench/`, im PR belegen, dass die Kachel-URL keine AOI, keine Job- oder Permalink-Kennung und keinen Hash trägt, und die Schätzung „~9 s kalt für die erste Kachel im ungünstigsten Fall“ als Prüfschritt in die Prüfanleitung.

## 15. NM4-04b Frontend (Folgeaufgabe, neue Session)

**Stufe A**, nur Frontend, nach dem Merge von #215. Branch von `main`, ein Draft-PR. Der Abschnitt ist ohne das Gespräch zu NM4-04 verständlich; maßgeblich sind §14 und `adr/0006`, Nachtrag NM4-04.

### 15.1 Ausgangslage

- Das Backend (#215) liefert die Mosaik-Kachel mit Schritten: `GET /collections/{dataset}/mosaic/tiles/WebMercatorQuad/{z}/{x}/{y}?item=…&item=…&asset=…&op=…&op_version=…&params=…` und das TileJSON unter `…/mosaic/WebMercatorQuad/tilejson.json` mit denselben Parametern. Das TileJSON trägt `earthx:order` (die Szenen in der Reihenfolge, in der die Kachel sie liest) und `unit`.
- Grenzen des Backends: 2 bis 64 Items, 1 bis 4 Assets mit Schritten, höchstens 4 Schritte, ab z8, höchstens 7 168 Byte für Pfad und Query (`backend/earthx/api/mosaic_tiles.py`: `MIN_MOSAIC_ITEMS`, `MAX_MOSAIC_ITEMS`, `MAX_MOSAIC_OPERATOR_ASSETS`, `MAX_MOSAIC_REQUEST_BYTES`, `MIN_MOSAIC_ZOOM`). Darüber `400`/`414`; Ablehnungen eines Schritts nennen ab zwei Schritten den Platz („step 1: …“).
- Heute zeigt die Vorschau im Panel (`frontend/src/processingPreview.ts` `previewSpec`) jede Szene als eigene Kachel-URL mit den Schritten und stapelt sie in Auswahlreihenfolge. Sie rechnet damit „Operator je Szene, dann Mosaik“ und weicht an Überlappungen vom Job ab (§7.2).

### 15.2 Umfang

1. **Mosaik-Vorschau bei „One job“:** Besteht der Auftrag aus einem Überflug mit 2 bis 64 Szenen, zeigt die Vorschau ab z8 die Mosaik-Kachel mit den Schritten und darunter die Einzelszenen mit denselben Schritten, gestapelt nach `earthx:order` (gleiches Muster wie `frontend/src/mosaic.ts` für die Ansicht ohne Schritte, `TILE_LEVEL_AHEAD`). Die `item` der URL sind nach ID sortiert (Cache, KE5 aus M4-17).
2. **„One job per pass“ (KE-P):** jeder Überflug mit mindestens 2 Szenen als eigenes Mosaik; ein Überflug mit einer Szene und „One job per scene“ bleiben bei der Vorschau je Szene.
3. **Probe der Kette:** `probeChain` fragt das TileJSON des Mosaiks statt das der ersten Szene; dessen `earthx:order` liefert die Reihenfolge für die Stapelung unter z8.
4. **Farbskala (F4):** Die Messung (`measure`) fragt `/statistics` der Item-Route mit den Schritten für die **erste Szene in Mosaik-Reihenfolge** (`earthx:order[0]`), nicht für die erste Szene der Auswahl. Keine Statistik auf der Mosaik-Route.
5. **Rückfall auf die Vorschau je Szene** (wie heute), wenn: mehr als 4 Assets; URL über 7 168 Byte (dieselbe Länge rechnen wie der Server: Pfad und Query, wie sie beim `tiler` ankommen); mehr als 64 Szenen; Datensatz nur unter z8 freigegeben; TileJSON des Mosaiks abgewiesen (außer bei einer Ablehnung eines Schritts, die wie heute den Platz zeigt). Der Rückfall ist erkennbar: ein kurzer Hinweis **im Tooltip der Vorschau**, etwa „Preview per scene – may differ from the job where scenes overlap“. **Kein Text im Panel** (F5, UI-01 §4).
6. Eine Konstante je Grenze im Frontend mit Verweis auf die Konstante im Backend (wie `MIN_MOSAIC_ZOOM`, `MAX_MOSAIC_SCENES` in `mosaic.ts`).

### 15.3 Abnahme

- `vitest`: „One job“ über einen Überflug → eine Mosaik-URL mit sortierten `item`, den Assets und den Schritten; unter z8 Einzelszenen in `earthx:order`; Messung über `earthx:order[0]`. Rückfälle: 5 Assets, URL über 7 168 Byte, 65 Szenen, eine Szene, Datensatz unter z8, abgewiesenes Mosaik → Vorschau je Szene mit dem Hinweis im Tooltip; eine Ablehnung eines Schritts zeigt weiter den Platz. „One job per pass“ → je Überflug ein Mosaik.
- Gegenprobe: Die neuen Tests scheitern gegen den Code vor der Änderung.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung) mit nachgestellten Antworten, hell und dunkel, schmales Fenster; im PR beschrieben.
- Keine AOI, Job-, Rezept- oder Permalink-Kennung und kein Hash in einer Kachel- oder TileJSON-URL (Test über die gebauten URLs).
- `npm run lint`, `npx tsc -b --pretty false`, `npm test` grün; Prüfanleitung für Otto im PR; Log-Zeile; vor „fertig“ `main` holen.

## 16. Umsetzung des Backends (27.10.2026)

- `processing/tile.py`: `MosaicOperatorTileReader` (§8.1), `judge_steps` (die Prüfung der Schritte, jetzt auch von `OperatorTileReader` benutzt) und `judge_described_bands` (die Bänder aus den Items, KE1). `UnsupportedRecipe` wird wie `RecipeInvalid` zu `422`.
- `processing/mosaic.py`: `check_alike` öffentlich (vorher `_check_alike`), damit Job und Kachel dieselbe Regel nehmen.
- `api/mosaic_tiles.py`: `MAX_MOSAIC_OPERATOR_ASSETS = 4`, `MAX_MOSAIC_REQUEST_BYTES = 7168`, `check_length`; `check_query` nimmt mit Schritten 1 bis 4 Assets.
- `api/tiler.py`: `mosaic_scenes` prüft Länge, Zoom, Form, Schritte und `reprojection` vor dem ersten Item-Abruf, dann über alle Items Skalierung, Einheiten, das CRS bei Zarr und die Bänder der Schritte (`_describe_mosaic`), bevor eine Datei geöffnet wird; `MosaicOperatorInput`, `mosaic_post_process`, `_open_mosaic_reader`. Die drei Query-Parameter der Schritte sind für Item- und Mosaik-Kachel dieselben Typen.
- `access/mosaic_tiles.py`: Das TileJSON trägt mit Schritten auch `unit`.
- Tests: `api/test_tiler_mosaic_operator.py` (28 Fälle: bitgleich mit Band math und `mask → band_math`, `red` aus A und `nir` aus B, das Loch der Wolke bleibt, Reihenfolge der IDs und frische App, TileJSON, Ablehnungen vor dem Abruf und vor dem Öffnen); `api/test_mosaic_item_fetches.py` (64 IDs à 60 Zeichen plus drei Schritte durch uvicorn); `api/test_tiler_mosaic.py` angepasst (die drei Parameter der Schritte stehen jetzt im Schema; „halber Schritt“ bleibt `400`).
- **Gegenprobe:** Gegen `main` scheitern 16 der 28 neuen Fälle, darunter beide Bitgleichheitstests und „das Loch der Wolke bleibt“ (dort weist `main` `op` mit `400` ab). Die 12 übrigen sind Ablehnungen, die `main` aus anderem Grund ebenfalls mit `400` beantwortet; sie sichern das Verhalten.
- Doku: `adr/0014` §15t, `adr/0006` Nachtrag NM4-04, Log-Zeilen.

## 17. Umsetzung des Frontends (28.10.2026, NM4-04b)

- `api.ts`: URL von Kachel und TileJSON des Mosaiks mit Schritten (`buildMosaicOperatorTileTemplate`, `buildMosaicOperatorTileJsonUrl`). `mosaic.ts`: `MIN_MOSAIC_SCENES`, `MAX_MOSAIC_OPERATOR_ASSETS`, `MAX_MOSAIC_REQUEST_BYTES` mit Verweis auf das Backend und `mosaicRequestBytes` (Länge wie `check_length`).
- `processingPreview.ts`: `previewSpec` nimmt die Szenen je Job (`jobs`) und die Antworten der Probe (`answers`); `PreviewSpec` trägt `mosaics`, `perScene`, Szenen mit `below`. `probeMosaic` liest `earthx:order` oder fällt auf die Szenen zurück; `previewOverlays` legt Mosaik und Szenen darunter (`hideFrom`).
- `processingStore.ts`: `settle` fragt zuerst die Mosaike (`chainRefusal`), danach wie bisher die erste Szene; bei einem abgelehnten Schritt wird das Mosaik der gekürzten Kette neu gefragt. `previewSettling` und `previewTilesLoading` tragen den Ladehinweis.
- Ladehinweis (Otto, 28.10.: kalt 6,0 s, warm 0,16 s): `components/usePreviewLoading.ts` (erst nach 600 ms), Badge in `PreviewBadge` und in der Überschrift der Vorschau; `mapLayers.ts::watchPreviewLoading` beobachtet nur die Quellen der Vorschau.
- Tests: `processingPreview.test.ts`, `mosaic.test.ts`, `mapLayers.test.ts`, `components/ProcessingPreview.test.tsx`. **Gegenprobe:** gegen `main` scheitern 64 Tests. Browser: `frontend/e2e/mosaic-preview.cjs`.
