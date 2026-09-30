# M3-10 — Datensatz-Filter in der Suchkachel: Plan-Schritt

**Status (30.09.2026):** Freigegeben (Otto: F1 (1), F2 (1), F3 (1), F4 (1),
**F5 (2)**, F6 (1), F7 (1), F8 (1), F9 (1)). **Teil 1 (M3-10a) umgesetzt** im
selben Draft-PR, Stand in §10; **Teil 2 (M3-10b)** folgt nach dem Merge in einer
neuen Session. Details in `ENTSCHEIDUNGSLOG.md`, Zeilen vom 30.09.2026.
**Aufgabe:** M3-10 aus `docs/plans/m3-dritte-quelle-und-interface.md` §4 (P9),
mit dem Nachtrag vom 26.09.2026 (M3-11b F11) und Ottos Vorgaben vom
26.09.2026 zum Start dieser Aufgabe (unten O1–O3, Log). **Stufe B.** Hängt an
M3-07b und M3-12 (beide auf `main`) und nutzt die gemischte Suche aus M3-13
(auf `main`).
**Grundlagen:** `plans/m3-13-gemischte-suche.md` §3, §4.3–4.5, §4.8, §10;
`plans/m3-12-frontend-sonderfaelle.md` §4.3–4.6, §4.8; `adr/0005` Regel III;
`ENTSCHEIDUNGEN_2026-09-18.md` §2 (Coverage Map); `KLAERUNGEN.md` B10.

Belegstufen: **M** gemessen in dieser Sitzung, **P** am Quelltext gelesen
(Stand `main` a3decdc), **A** eigene Ableitung.

Ottos Vorgaben vom 26.09.2026, fest:

| # | Vorgabe | Abschnitt |
|---|---|---|
| O1 | Der Datensatz-Filter ist eine Mehrfachauswahl; der Viewer sucht mehrere Datensätze zugleich über die gemischte Suche (ein Zeitraum, mehrere Datensätze) | §4.1, §4.2 |
| O2 | Die Trefferliste hat je Datensatz einen eigenen aufklappbaren Abschnitt, Name und Trefferzahl im Kopf; darin bleibt die Gruppierung je Überflug | §4.3 |
| O3 | Hinweise aus `ignored_filters_by_collection` (z. B. „No time axis“) und `incomplete_collections` stehen im Kopf des jeweiligen Abschnitts | §4.3 |

Dazu die Aufträge für diesen Plan-Schritt: „Mehr laden“ mit der gemischten
Seitenmarke (§4.4, F1), welcher Abschnitt anfangs offen ist (§4.3, F2), was
Heatmap, Quicklooks und Vollauflösung bei mehreren Datensätzen zeigen (§4.5,
F3–F5).

---

## 1. Ziel

Datensätze werden über einen Filter gewählt statt über feste Knöpfe, und zwar
mehrere zugleich. Eine Suche fragt alle gewählten Datensätze in einem Aufruf
ab. Die Trefferliste trennt die Datensätze in eigene Abschnitte. Alles, was
heute für „den einen Datensatz“ gilt (Karte, Zeitleiste, Vollauflösung,
Download, Heatmap), folgt einem **aktiven Datensatz**. Das Frontend kennt
weiterhin keine Datensatz-Kennung.

---

## 2. Befund am Code — **[P]**

### 2.1 Die „festen Blöcke“ heute

`ControlPanel.tsx::DatasetSelector` zeichnet je Eintrag aus `/stac/collections`
einen Knopf in einer Zeile (`.level-select` / `.level-btn`, im CSS noch als
„product-level selector“ überschrieben, ein Rest des Prototyps). Genau ein
Knopf ist aktiv (`aria-pressed`); ein nicht anzeigbarer Datensatz ist
abgeschaltet, der Grund steht im `title`. Der Reifegrad erscheint als Chip im
Knopf (`maturityLabel`) und darunter als Satz (`DatasetNotes`).

Grenzen: Die Knöpfe teilen sich die Breite der Kachel (`flex: 1`); ab vier
oder fünf Datensätzen werden die Titel unlesbar. Es gibt keine Suche und keine
Mehrfachauswahl.

### 2.2 Ein Datensatz im Store

`store.ts` hält genau einen `datasetId`. Daran hängen `runSearch` (schickt
`collections: [dataset.id]`), `findSceneByName`, `enterFocus`,
`addCurrentToLayers`, `openDownloadForSelection`/`confirmDownload`,
`autoStretch`, die Coverage (`refreshCoverage`) und außerhalb des Stores
`MapView` (Quicklooks, Vollauflösung), `StatusBar` (`zoomFloorHint`),
`ViewBar`, `ViewerControls`, `LayerManager` und `DownloadDialog`.
`setDatasetId` leert Treffer, Auswahl, Vollauflösung und Coverage.

`items`, `groups`, `activeGroupIndex` und `expandedGroupIndex` beschreiben eine
flache Trefferliste eines Datensatzes; `TimeSlider` und `MapView` lesen sie
direkt.

### 2.3 Suche und Paging

`api.searchAllPages` blättert bis 300 Items (`MAX_SEARCH_ITEMS`) und verwirft
danach die Seitenmarke. Ein „Mehr laden“ gibt es nicht; `foundNotice` rät bei
mehr Treffern, AOI oder Zeitraum zu verkleinern. Eine gemischte Antwort trägt
kein `numberMatched` (M3-13 §4.2).

`api.ts` liest `ignored_filters` und `incomplete_collections`, aber **nicht**
`ignored_filters_by_collection` (M3-13 F4, Backend liefert es seit #103).

### 2.4 Schlagworte

Die Registry hat kein Feld für Schlagworte, und `to_stac_collection`
(`catalog/collection.py`) gibt kein STAC-`keywords` aus. Ein Filter über
„Titel, Beschreibung und Schlagworte“ (Umfang M3-10) fände heute nur Titel
und Beschreibung (→ F6).

### 2.5 Kennungen im Frontend

`backend/tests/test_frontend_no_dataset_literals.py` (M3-12 §4.8) prüft
bereits, dass keine `dataset_id` aus der Registry im Frontend-Code steht. Die
Abnahme „mit drei Datensätzen keine Datensatz-Kennung im Frontend-Code nötig“
ist damit ein bestehender Test, der grün bleiben muss.

---

## 3. Bedienung (Vorschlag)

**Filter in der Suchkachel** an der Stelle der heutigen Knopfzeile:

```
Datasets                                  2 selected
[ Filter datasets…                              ]
[x] Sentinel-2 L2A
[x] Sentinel-2 L2A (Zarr3)            staging
[ ] Copernicus DEM GLO-30
```

- Ein Textfeld „Filter datasets“, darunter eine Liste mit Kontrollkästchen,
  eine Zeile je Datensatz: Titel und Reifegrad-Chip wie heute. Die
  Beschreibung steht im `title` der Zeile.
- Filter im Client: ohne Groß-/Kleinschreibung und ohne Akzente; jedes durch
  Leerzeichen getrennte Wort muss in Titel, Beschreibung oder Schlagworten
  vorkommen. Die Eingabe ist Text, kein regulärer Ausdruck.
- **Gewählte Datensätze bleiben immer sichtbar**, auch wenn der Filter sie
  nicht trifft; er grenzt nur die übrigen ein. So verschwindet keine Auswahl
  hinter einem Suchwort.
- Trifft der Filter nichts: „No dataset matches“.
- Nicht anzeigbare Datensätze bleiben gelistet, Kontrollkästchen
  abgeschaltet, Grund im `title` (wie heute).
- `DatasetNotes` zeigt die Reifegrad-Sätze aller gewählten Datensätze, je mit
  Titel.
- Vorauswahl beim Laden: der erste anzeigbare Datensatz (wie heute).
- Keine gewählten Datensätze: „Search“ ist abgeschaltet, Hinweis „Select at
  least one dataset.“
- Die Auswahl zu ändern, leert die Trefferliste (wie heute `setDatasetId`),
  denn sie passt nicht mehr zur Suche.

**Zeitraum:** Die Datumsfelder sperren sich nur, wenn **alle** gewählten
Datensätze keine Zeitachse haben. Ist mindestens einer ohne Zeitachse gewählt,
steht unter den Feldern je solcher Datensatz eine Zeile „<Titel>: No time
axis – acquired Dec 2010 to Jan 2015“ (Text aus M3-12, fest).

---

## 4. Vorgeschlagene Umsetzung

### 4.1 Datensätze und Filter (`datasets.ts`)

- `datasetMatches(dataset, query): boolean` und
  `filterDatasets(datasets, query, selectedIds): DatasetOption[]` als reine
  Funktionen (Vitest).
- `keywordsOf(collection)` liest STAC-`keywords`, nur Zeichenketten, sonst
  leer (→ F6).
- Neues Feld im Typ `Collection`: `keywords?: string[] | null`.

### 4.2 Store: Auswahl, Abschnitte, aktiver Datensatz

- **`selectedDatasetIds: string[]`** (neu): die Auswahl des Filters, in der
  Reihenfolge der Datensatzliste. `toggleDatasetSelected(id)` ersetzt
  `setDatasetId` im Filter; eine nicht anzeigbare oder unbekannte Kennung wird
  ignoriert.
- **`datasetId`** behält seinen Namen und heißt ab jetzt „aktiver
  Datensatz“. Alle Stellen aus §2.2 bleiben damit unverändert. Er wird gesetzt
  durch: Vorauswahl, Wahl in der Heatmap-Legende (§4.5), Aufklappen eines
  Abschnitts (§4.3). Wird der aktive Datensatz abgewählt, wird der erste
  gewählte aktiv.
- **`sections: ResultSection[]`** (neu), ein Eintrag je gesuchtem Datensatz,
  in der Reihenfolge der Auswahl:
  `{ datasetId, items, groups, notes: string[] }`.
- `items`, `groups`, `activeGroupIndex`, `expandedGroupIndex` bleiben und
  spiegeln den **offenen** Abschnitt. `TimeSlider`, `MapView`, Download und
  Vollauflösung lesen sie wie bisher und brauchen keine Änderung.
- **`setOpenSection(datasetId | null)`**: klappt genau einen Abschnitt auf
  (→ F2), setzt `datasetId`, übernimmt dessen `items`/`groups`, setzt
  Zeitschritt und Auswahl zurück und verlässt die Vollauflösung. Zuklappen
  leert `items`/`groups`; die Karte zeigt dann keine Quicklooks. Den
  AOI-Zuschnitt eines `full_resolution`-Datensatzes startet **nicht** das
  Aufklappen, sondern die Suche selbst (F5 (2), §4.5).
- **`runSearch`** schickt `collections: selectedDatasetIds` (nur anzeigbare).
  Die Items werden nach `item.collection` auf die Abschnitte verteilt und dort
  je Datensatz mit dessen `resultsGroupBy` gruppiert. Ein Item ohne
  `collection` oder mit einer nicht gesuchten Collection wird nicht still
  verworfen: Es fällt heraus, und der Such-Hinweis nennt die Zahl.
  `MissingProperty` bei einem Datensatz leert nur dessen Abschnitt, mit dem
  Fehler im Kopf; die anderen bleiben.
- **±90-Tage-Fallback** je Datensatz mit Zeitachse, dessen Abschnitt leer ist
  und der nicht in `incomplete_collections` steht (→ F7). Der Fallback fragt
  nur diesen Datensatz; sein Hinweis steht im Kopf des Abschnitts.
- **Namenssuche** (`findSceneByName`) → F8.

### 4.3 Trefferliste (`ResultsPanel.tsx`)

```
Results                          412   Clear all
▾ Sentinel-2 L2A                 214
    ▸ 2026-09-12 · R065           12
    ▾ 2026-09-07 · R108           10
        [ ] thumbnail S2B_…
▸ Sentinel-2 L2A (Zarr3)  staging 196
▸ Copernicus DEM GLO-30             2
    No time axis – acquired Dec 2010 to Jan 2015
[ Load more ]   More scenes may be available.
```

- Je Abschnitt ein Kopf mit Aufklapp-Pfeil, Titel, Reifegrad-Chip und
  Trefferzahl. Darunter, **auch zugeklappt**, die Hinweise des Abschnitts
  (O3):
  - `ignored_filters_by_collection[id]` enthält `datetime` → der Text aus
    `acquisitionNote` (fest aus M3-12); jeder andere ignorierte Filter →
    „Filter not applied: <name>“.
  - `incomplete_collections` → „Results incomplete: the source timed out“ /
    „… was not reachable“ / „… reported an error“ / „… sent an unreadable
    answer“; unbekannter Grund → „Results incomplete (<reason>)“.
  - Fallback → der bestehende `fallbackNotice`-Text.
  - Leer → „No scenes for this area.“
- Innerhalb des Abschnitts die Gruppen je Überflug wie heute (`GroupBlock`,
  `results_group_by`).
- Nur ein Abschnitt ist offen (Akkordeon, → F2); den offenen Zeitschritt
  merkt sich der Store über den Gruppen-Schlüssel, nicht über den Index, damit
  „Load more“ ihn nicht verschiebt (§4.4).
- **Anfangs offen** (→ F2): der erste Abschnitt mit Treffern in der
  Reihenfolge der Datensatzliste; hat keiner Treffer, bleibt alles zu.
- Überschrift „Time steps“ wird „Results“; die Zahl im Kopf ist die Summe.

### 4.4 „Load more“ und die gemischte Seitenmarke (→ F1)

Die gemischte Marke gilt für die **ganze** Suche: Ihr Fingerabdruck umfasst
alle Collections (M3-13 §4.3), und für den Client ist sie undurchsichtig
(`adr/0005` Regel III). Eine Fortsetzung je Datensatz gibt es damit nicht,
ohne das Backend zu ändern oder die Marke im Client aufzuschlüsseln.

**Vorschlag: ein gemeinsamer Knopf.**

- Die erste Suche blättert wie heute bis 300 Items. Bleibt danach eine Marke
  übrig, steht am Ende der Liste „Load more“ mit dem Satz „More scenes may be
  available.“ Welcher Datensatz noch mehr hat, kann der Client nicht sagen;
  der Satz behauptet es deshalb für keinen.
- „Load more“ führt die gespeicherte Marke fort, wieder bis 300 Items. Das
  Backend verteilt die Anteile neu auf die noch offenen Quellen (M3-13 F1);
  ein erschöpfter Datensatz bekommt nichts mehr, die übrigen teilen sich die
  Seite.
- Neue Items landen in ihrem Abschnitt, dessen Gruppen werden neu gebildet.
  Offener Abschnitt und offener Zeitschritt bleiben (Schlüssel statt Index).
  Hinweise aus `incomplete_collections` kommen dazu, wenn eine Quelle erst
  später ausfällt.
- Der Knopf ist gesperrt, solange er lädt. Ein Fehler (z. B. `400`, weil die
  Marke nach einem Deployment nicht mehr gilt) lässt die geladenen Treffer
  stehen und sagt: „Could not load more results — search again.“
- Suche, Auswahl, AOI oder Zeitraum zu ändern, verwirft die Marke.
- Abschnitte aus dem ±90-Tage-Fallback (§4.2) blättern nicht mit; der
  Fallback lädt ohnehin den ganzen Tag.
- Mit einem einzigen gewählten Datensatz ist es dieselbe Bedienung; die Marke
  ist dann die des Adapters oder von pgstac.

`api.searchAllPages` bekommt dafür eine optionale Start-Marke und gibt die
letzte Marke zurück, dazu `ignoredFiltersByCollection`.

### 4.5 Heatmap, Quicklooks, Vollauflösung (→ F3, F4, F5)

Leitgedanke: **Die Karte zeigt zu jeder Zeit einen Datensatz: den aktiven.**
Vergleiche über Datensätze gehen über den Layer-Manager: Angeheftete Ebenen
tragen schon heute ihren eigenen Datensatz (`LayerRestore.datasetId`) und
liegen übereinander.

- **Heatmap (F3):** zeigt den aktiven Datensatz. Die Legende nennt seinen
  Titel. Sind mehrere gewählt, hat die Legende eine Auswahl unter ihnen; die
  Wahl macht den Datensatz aktiv und klappt nach einer Suche auch seinen
  Abschnitt auf (dieselbe Handlung wie §4.3). Vor der ersten Suche ist der
  aktive der erste gewählte.
- **Quicklooks (F4):** nur die des offenen Zeitschritts im offenen Abschnitt,
  wie heute. Die Zeitleiste zeigt die Überflüge dieses Abschnitts.
- **Vollauflösung (F5 (2), Otto 30.09.2026):** Ein Datensatz mit
  `browse: 'full_resolution'` (der DEM) erscheint **nach jeder Suche sofort**
  als auf die AOI zugeschnittene Vollauflösung, gleich welcher Abschnitt offen
  ist und auch bei einer Suche zusammen mit Sentinel-2 („direkt die Daten laden
  für die AOI nach der Suche“). Umsetzung: Die Suche heftet den Zuschnitt je
  Zeitschritt als Ebene an (`searchLayers.ts`, gleiche Form wie „Crop & merge to
  AOI“, M3-09 §10), gekennzeichnet mit `fromSearch`; eine Wiederholung ersetzt
  sie, statt sie zu stapeln. Die Karte zeichnet angeheftete Ebenen unabhängig
  vom offenen Abschnitt. Die Vollauflösungs-Ansicht mit Stretch-Steuerung
  (`focusMode`) bleibt dem, was der Nutzer selbst startet (Auswahl, „Crop &
  merge to AOI“) oder über die Ebene im Layer-Manager wählt.
- **Angeheftete Ebenen (F4 (1), Otto 30.09.2026):** Ebenen verschiedener
  Datensätze bleiben im Layer-Manager und auf der Karte zugleich sichtbar,
  unabhängig vom offenen Abschnitt, von der Auswahl im Filter und von der
  nächsten Suche (nur die eigenen Such-Zuschnitte des erneut gesuchten
  Datensatzes werden ersetzt). Eine Ebene zu wählen macht ihren Datensatz zum
  aktiven und öffnet seinen Abschnitt.
- Download, „Add to layers“ und Auto-Stretch folgen dem aktiven Datensatz,
  ohne Änderung am Code (§4.2). Die Auswahl von Szenen gilt je Abschnitt und
  wird beim Wechsel geleert; Item-Kennungen sind nur innerhalb einer
  Collection eindeutig.
- `zoomFloorHint` (StatusBar) spricht für den aktiven Datensatz, wie heute.

### 4.6 Schlagworte in der Registry (→ F6)

Bei F6 (1): `DatasetConfig.keywords: tuple[str, ...]` ohne Vorgabewert (B10),
`to_stac_collection` gibt es als STAC-Kernfeld `keywords` aus, die
Registry-Prüfung verlangt mindestens ein Schlagwort. Vorschlag für die drei
Einträge (Inhalt entscheidet Otto):

| Datensatz | `keywords` |
|---|---|
| Sentinel-2 L2A | `sentinel-2`, `optical`, `multispectral`, `surface reflectance`, `copernicus` |
| Sentinel-2 L2A (Zarr3) | `sentinel-2`, `optical`, `multispectral`, `surface reflectance`, `copernicus`, `zarr` |
| Copernicus DEM GLO-30 | `elevation`, `dem`, `dsm`, `terrain`, `copernicus`, `tandem-x` |

Kein Suchendpunkt im Backend (Umfang M3-10); die Onboarding-Checkliste
bekommt keinen neuen Punkt.

### 4.7 Nicht anfassen

`readers`, `access`, Tiler-, Coverage- und Download-Route, die gemischte Suche
selbst (`api/mixed_search.py`, `federating_client.py`), Registry außer F6,
`MAX_SEARCH_ITEMS`, Hybrid-Suche (M5).

---

## 5. Tests (Abnahme)

Vitest, alle Quellen über synthetische Collections und Items:

- **Filter** (`datasets.test.ts`): Titel, Beschreibung, Schlagworte; Groß- und
  Kleinschreibung, Akzente; mehrere Wörter (UND); leere und nur aus
  Leerzeichen bestehende Eingabe → alle; Sonderzeichen wie `(`, `.*`, `\`
  werden als Text gelesen; sehr lange Eingabe; gewählte bleiben sichtbar;
  `keywords` fehlt, ist `null` oder enthält Nicht-Zeichenketten.
- **Store** (`store.test.ts`): Auswahl umschalten, nicht anzeigbare und
  unbekannte Kennung ignoriert, letzte abgewählt → Suche gesperrt; Suche
  schickt alle gewählten Collections; Aufteilung auf Abschnitte; Item ohne
  oder mit fremder `collection` fällt heraus und wird gezählt;
  `MissingProperty` in einem Datensatz lässt die anderen stehen; Hinweise je
  Abschnitt aus `ignored_filters_by_collection` und `incomplete_collections`;
  anfangs offener Abschnitt; Akkordeon; Wechsel leert Auswahl und verlässt die
  Vollauflösung; `full_resolution` beim Aufklappen; Fallback nur im leeren
  Abschnitt mit Zeitachse.
- **„Load more“**: Items landen im richtigen Abschnitt, offener Zeitschritt
  bleibt über den Schlüssel; keine Marke → kein Knopf; Fehler lässt Treffer
  stehen; Auswahländerung verwirft die Marke; kein Doppelklick-Doppelaufruf.
- **Komponenten**: Filterliste (Tastatur, `aria`), Abschnittsköpfe mit
  Hinweisen auch zugeklappt, Heatmap-Legende mit Auswahl.
- **`api.test.ts`**: `ignored_filters_by_collection` gelesen und über Seiten
  gesammelt, fehlend → leer, falsche Form → leer; Start-Marke wird
  mitgeschickt.
- **Backend** (nur bei F6 (1)): `keywords` im Collection-Dokument; Eintrag
  ohne Schlagworte fällt in der Registry-Prüfung durch.
- Bestehend und grün zu halten: `test_frontend_no_dataset_literals.py`.

Otto prüft lokal: drei Datensätze gewählt, eine AOI mit Sentinel-2-Treffern
und DEM-Kachel, Abschnitte und Hinweise, „Load more“, Heatmap-Wechsel,
DEM-Abschnitt öffnet den Zuschnitt.

---

## 6. Umfang und Schnitt (→ F9)

Grobe Schätzung **[A]**, ohne generierte Dateien:

| Teil | Inhalt | Zeilen, davon Tests |
|---|---|---|
| M3-10a | Filter, Mehrfachauswahl, Abschnitte, aktiver Datensatz, Heatmap-Legende, `ignoredFiltersByCollection`, F6 | ≈ 500, davon ≈ 250 |
| M3-10b | „Load more“, Fallback je Abschnitt, Namenssuche über mehrere | ≈ 330, davon ≈ 170 |

---

## 7. Risiken

- **`store.ts` wird größer** (heute 1319 Zeilen). Die Aufteilung auf Abschnitte
  und das Mischen bei „Load more“ gehen als reine Funktionen in eine eigene
  Datei `sections.ts`, der Store ruft sie nur.
- **Parallele Fallback-Suchen** (F7 (1)): bis zu einer Probe-Folge je leerem
  Datensatz mit Zeitachse. Heute zwei solche Datensätze; bleibt klein.
- **Verwechslung „aktiv“ und „gewählt“**: Die Legende und der offene
  Abschnitt nennen den aktiven Datensatz ausdrücklich beim Titel.

---

## 8. Doku und Log

- `ENTSCHEIDUNGSLOG.md`: Ottos Vorgaben O1–O3 (fest) und dieser Plan-Schritt
  (Vorschlag); nach der Freigabe eine Zeile mit den Antworten.
- `plans/m3-dritte-quelle-und-interface.md`: M3-10 auf „Plan-Schritt“, Verweis
  auf diese Datei.
- Nach der Umsetzung: §9 dieser Datei um den Stand ergänzen; `architekturplan.md`
  5.1 nur bei F6 (1) (neues Registry-Feld).

---

## 9. Fragen an Otto

**F1 — „Load more“ (§4.4)**
1. Ein gemeinsamer Knopf am Ende der Liste; führt die eine gemischte Marke
   fort, je Klick bis 300 Items; neue Items landen in ihrem Abschnitt.
   **(Empfehlung)**
2. Je Abschnitt ein eigener Knopf. Braucht eine Backend-Änderung (Marke je
   Collection in der Antwort) oder eine neue Einzelsuche, die schon geladene
   Items noch einmal holt; außerhalb des Umfangs.
3. Kein „Load more“; wie heute 300 Items und der Rat, AOI oder Zeitraum zu
   verkleinern.

**F2 — Offene Abschnitte (§4.3)**
1. Akkordeon, anfangs der erste Abschnitt mit Treffern in Listenreihenfolge.
   **(Empfehlung)**
2. Akkordeon, anfangs der Abschnitt mit den meisten Treffern.
3. Mehrere Abschnitte zugleich offen; der zuletzt aufgeklappte ist aktiv.

**F3 — Heatmap bei mehreren Datensätzen (§4.5)**
1. Heatmap des aktiven Datensatzes, Auswahl in der Legende. **(Empfehlung)**
2. Summe über alle gewählten Datensätze in einer Heatmap (Zählweisen und
   Skalen der Datensätze passen nicht zusammen).
3. Je Datensatz eine eigene Heatmap-Ebene übereinander.

**F4 — Quicklooks (§4.5)**
1. Nur der offene Zeitschritt im offenen Abschnitt, wie heute.
   **(Empfehlung)**
2. Je Abschnitt der offene Zeitschritt, alle zugleich auf der Karte.

**F5 — Vollauflösung (§4.5)**
1. Nur für den offenen Abschnitt; Wechsel verlässt sie; DEM-Zuschnitt beim
   Aufklappen seines Abschnitts. Vergleich über angeheftete Ebenen.
   **(Empfehlung)**
2. DEM-Zuschnitt sofort nach jeder Suche, auch wenn ein anderer Abschnitt
   offen ist, als eigene Ebene unter den Quicklooks. **(Otto: gewählt)**

**F6 — Schlagworte (§2.4, §4.6)**
1. Neues Registry-Feld `keywords` ohne Vorgabewert, als STAC-`keywords`
   ausgeliefert, die drei Einträge mit den Werten aus §4.6. **(Empfehlung)**
2. Filter nur über Titel und Beschreibung; Schlagworte später (M5, YAML).

**F7 — ±90-Tage-Fallback bei mehreren Datensätzen (§4.2)**
1. Je leerem Abschnitt mit Zeitachse, Hinweis im Abschnittskopf.
   **(Empfehlung)**
2. Nur, wenn alle Abschnitte leer sind.
3. Kein Fallback, sobald mehr als ein Datensatz gewählt ist.

**F8 — Namenssuche bei mehreren gewählten Datensätzen**
1. Fragt alle gewählten Datensätze parallel; ein Treffer landet in seinem
   Abschnitt, jeder Datensatz ohne Treffer sagt es im Kopf.
   **(Empfehlung)**
2. Nur mit genau einem gewählten Datensatz; sonst „Select one dataset to look
   up a scene name.“

**F9 — Schnitt (§6)**
1. Zwei PRs: M3-10a (≈ 500 Zeilen, davon ≈ 250 Tests), M3-10b (≈ 330, davon
   ≈ 170). **(Empfehlung)**
2. Ein PR mit getrennten Commits, ≈ 830 Zeilen, davon ≈ 420 Tests.

---

## 10. Umsetzung M3-10a (30.09.2026)

Ottos Antworten wie im Kopf; F5 (2) statt der Empfehlung. Umgesetzt ist der
erste PR (F9 (1)); §4.4 („Load more“), der Fallback je Abschnitt (F7) und die
Namenssuche über mehrere Datensätze (F8) sind **M3-10b**.

- **Filter (§3, §4.1):** `datasets.ts`: `keywordsOf`, `datasetMatches`,
  `filterDatasets`; `ControlPanel.tsx`: `DatasetFilter` (Textfeld, Liste mit
  Kontrollkästchen, Reifegrad-Chip, Beschreibung im `title`); die alte Knopfzeile
  und ihr CSS (`.level-select`) sind weg. Ausgewählte Datensätze bleiben
  gelistet, auch wenn der Filter sie nicht trifft.
- **Store (§4.2):** neu `selectedDatasetIds`, `sections`, `openSectionId`,
  `toggleDatasetSelected`, `setOpenSection`; `datasetId` heißt „aktiver
  Datensatz“, `setDatasetId` macht einen Datensatz aktiv (öffnet seinen
  Abschnitt, wenn die Suche einen hat). Die Aufteilung auf Abschnitte steht als
  reine Funktion in `sections.ts`. `items`/`groups` spiegeln den offenen
  Abschnitt; `TimeSlider`, `MapView`, Download und Vollauflösung blieben
  unverändert.
- **Suche:** `runSearch` schickt alle ausgewählten anzeigbaren Collections in
  einem Aufruf. Ein Item ohne oder mit fremder `collection` fällt heraus und
  wird im Hinweis gezählt; bei genau einem Datensatz gehören alle Items ihm. Der
  ±90-Tage-Fallback läuft bis M3-10b nur bei genau einem ausgewählten Datensatz
  mit Zeitachse; bei mehreren gibt es „No scenes found for this area and date
  range.“.
- **Trefferliste (§4.3):** `ResultsPanel.tsx` mit einem Abschnitt je Datensatz
  (Akkordeon, Name, Reifegrad, Trefferzahl); Hinweise aus
  `ignored_filters_by_collection`, `incomplete_collections` und Gruppierfehlern
  stehen im Kopf, auch zugeklappt. Anfangs offen: der erste Abschnitt mit
  Treffern (F2 (1)).
- **Heatmap (F3 (1)):** Die Legende nennt den aktiven Datensatz; mit mehreren
  ausgewählten Datensätzen wählt man dort (`select`), was auch den Abschnitt
  öffnet.
- **F5 (2) und F4 (1):** siehe §4.5. Zwei Nebenfunde: (1) `addCurrentToLayers`
  bildete Ebenen-Kennungen aus der Uhr allein; zwei Ebenen in derselben
  Millisekunde bekamen dieselbe Kennung (`nextBatchId`, ein Zähler dazu). (2)
  `selectLayer` ließ den aktiven Datensatz unberührt, sodass die Liste von einem
  anderen Datensatz sprach als die gewählte Ebene; jetzt wird ihr Datensatz
  aktiv (ist er nicht mehr angehakt, wird er wieder angehakt, die Ergebnisse
  bleiben). Wird ein Datensatz ohne eigenen Abschnitt aktiv, gehen Liste,
  Auswahl und Vollauflösung des vorigen Datensatzes; die Auswahl im Filter ist
  während einer laufenden Suche gesperrt.
- **Zeichenreihenfolge (Otto, 30.09.2026, Option 2):** Die automatisch gesetzten
  Zuschnitte (`fromSearch`) liegen unter den Quicklooks, wie bei F5 (2)
  formuliert. Umsetzung in `mapLayers.ts`: eine unsichtbare Markierungsebene
  (`layer-floor`, `background`, `visibility: none`) unter allem, was die App
  sonst zeichnet; `syncLayers` setzt Such-Zuschnitte direkt darunter, alles
  andere weiterhin unter die AOI-Kontur. Damit gilt es unabhängig davon, was
  zuerst gezeichnet wird. Von Hand angeheftete Ebenen und deren Reihenfolge im
  Layer-Manager bleiben unverändert; Such-Zuschnitte liegen unter allen
  anderen Ebenen, untereinander gilt die Listenreihenfolge. Test:
  `mapLayers.test.ts`, „draw order: automatic crops under the quicklooks“.
- **Schlagworte (F6 (1)):** `DatasetConfig.keywords` (ohne Vorgabewert, mindestens
  ein nicht leeres Schlagwort, Registry-Prüfung), als STAC-`keywords` in
  `to_stac_collection`; Werte wie in §4.6; `architekturplan.md` 5.1 nachgezogen.

**Geändert:** `backend/earthx/catalog/registry.py`, `datasets.py`,
`collection.py`; `frontend/src/api.ts`, `types.ts`, `datasets.ts`, `layers.ts`,
`store.ts`, `sections.ts` (neu), `searchLayers.ts` (neu),
`components/ControlPanel.tsx`, `ResultsPanel.tsx`, `index.css`. Tests:
`backend/tests/catalog/test_registry.py`, `test_collection.py`, `conftest.py`;
`frontend/src/datasets.test.ts`, `api.test.ts`, `sections.test.ts` (neu),
`searchLayers.test.ts` (neu), `store.sections.test.ts` (neu), `store.test.ts`,
`mapLayers.test.ts`, `components/ControlPanel.test.tsx`,
`components/ResultsPanel.test.tsx` (neu).
