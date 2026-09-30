# M3-10 — Datensatz-Filter in der Suchkachel: Plan-Schritt

**Status (30.09.2026):** Freigegeben (Otto: F1 (1), F2 (1), F3 (1), F4 (1),
**F5 (2)**, F6 (1), F7 (1), F8 (1), F9 (1)). **Teil 1 (M3-10a) umgesetzt** im
selben Draft-PR, Stand in §10; **Teil 2 (M3-10b)** folgt nach dem Merge in einer
neuen Session. Details in `ENTSCHEIDUNGSLOG.md`, Zeilen vom 30.09.2026.
**Geändert nach Ottos lokaler Prüfung (30.09.2026):** Umschalt-Knöpfe statt
Textfilter, Dropdown statt aufklappbarer Abschnitte, Coverage-Map im Control
Center, Layout des Control Centers (§11). §3, §4.1 und §4.3 beschreiben den
neuen Stand; die Antwort auf F2 (Akkordeon) ist damit ersetzt.
**Zweite Rückmeldung (30.09.2026, §12):** Karte folgt dem Dropdown (ersetzt
F5 (2)), Datensatz-Knöpfe als 2×2-Raster, abgesetztes Dropdown, Coverage-Knopf
im Fuß, heller Hintergrund hinter der Weltkugel.
**Teil 2 (M3-10b) umgesetzt** (30.09.2026, eigener Draft-PR): „Load more“,
Fallback für den im Dropdown gewählten Datensatz, Namenssuche über alle
angehakten Datensätze; Stand und Auslegungen in §13.
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

## 3. Bedienung (Stand nach Ottos Prüfung, 30.09.2026)

**Datensatz-Auswahl im Control Center** an der Stelle der früheren Knopfzeile,
wieder als Knöpfe, jetzt als **Umschalter mit Mehrfachauswahl**:

```
Datasets                                  2 selected
[ Sentinel-2 L2A     ] [ Sentinel-2 L2A (Za… ]   <- gewählt, hervorgehoben
[ Copernicus DEM GLO ] [ Landsat Collection  ]
  (ab dem fünften Datensatz scrollt das Raster)
--------------------------------------------------
[ ▦ Coverage ] [            Search             ]   <- Fuß, immer sichtbar
```

- Ein Knopf je Datensatz aus `/stac/collections`: Klick wählt aus (Rahmen,
  getönte Fläche, Glühen, fette Schrift, `aria-pressed`), erneuter Klick wählt
  ab. Keine Kontrollkästchen, **kein Textfilter**.
- Vier Datensätze sind zugleich sichtbar, als **Raster 2×2** (zweite
  Rückmeldung); gibt es mehr, scrollt das Raster.
- Reifegrad-Chip im Knopf, Beschreibung im `title`. Nicht anzeigbare
  Datensätze bleiben gelistet, abgeschaltet, Grund im `title`.
- `DatasetNotes` zeigt die Reifegrad-Sätze aller gewählten Datensätze, je mit
  Titel, sobald mehr als einer gewählt ist.
- Vorauswahl beim Laden: der erste anzeigbare Datensatz.
- Keine gewählten Datensätze: „Search“ ist abgeschaltet, Hinweis „Select at
  least one dataset.“
- Die Auswahl zu ändern, leert die Trefferliste (sie passt nicht mehr zur
  Suche); während einer laufenden Suche ist sie gesperrt.
- **Coverage-Knopf „Coverage“** im Fuß neben „Search“, immer sichtbar und von
  den Datensatz-Knöpfen abgesetzt (Symbol, gestrichelter Rahmen, bis er an ist).
  Ein Datensatz gewählt: ein Klick zeigt dessen Coverage, der nächste blendet sie
  aus. Mehrere gewählt: erst der Klick öffnet die Auswahl, von welchem Datensatz
  (mit „Hide coverage“, wenn sie an ist); bis dahin wird nichts gezeichnet.
  Ohne gewählten Datensatz ist der Knopf sichtbar, aber aus. Legende und
  Histogramm stehen im scrollenden Teil, mit dem Datensatz im Titel.

**Layout:** Das Control Center ist höchstens so hoch wie das Fenster abzüglich
zweimal 16 px (oben und unten derselbe Abstand). Der Inhalt scrollt; „Search“,
Trefferzahl und Hinweise stehen in einem festen Fuß darunter und sind bei jeder
Fensterhöhe sichtbar.

**Zeitraum:** Die Datumsfelder sperren sich nur, wenn **alle** gewählten
Datensätze keine Zeitachse haben. Ist mindestens einer ohne Zeitachse gewählt,
steht unter den Feldern je solcher Datensatz eine Zeile „<Titel>: No time
axis – acquired Dec 2010 to Jan 2015“ (Text aus M3-12, fest).

---

## 4. Vorgeschlagene Umsetzung

### 4.1 Datensätze (`datasets.ts`)

Kein Filter mehr (Otto, 30.09.2026): Die Funktionen `datasetMatches`,
`filterDatasets` und `keywordsOf` sind entfernt. Das Feld `keywords` bleibt in
Registry und STAC-Collection (und im Typ `Collection`) für den künftigen
Datensatz-Browser, den das Frontend heute nicht liest.

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
- **`setOpenSection(datasetId)`**: die Wahl im Dropdown (§4.3, ersetzt das
  Aufklappen des Akkordeons aus F2): setzt `datasetId`, übernimmt dessen
  `items`/`groups`, setzt Zeitschritt und Auswahl zurück und verlässt die
  Vollauflösung. Es gibt kein „keiner offen“ mehr; dieselbe Wahl noch einmal ist
  wirkungslos. Den AOI-Zuschnitt eines `full_resolution`-Datensatzes startet
  **nicht** die Wahl, sondern die Suche selbst (F5 (2), §4.5).
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

### 4.3 Trefferliste (`ResultsPanel.tsx`) — Dropdown statt Abschnitte

```
Results                                  412   Clear all
[ Sentinel-2 L2A                       214  ▾ ]   <- Box: gewählter Datensatz
  Sentinel-2 L2A (Zarr3)  staging      196        <- Dropdown (geöffnet)
  Sentinel-1 GRD                         0
     Results incomplete: the source timed out.
▾ 2026-09-12 · R065                     12
    [ ] thumbnail S2B_…
▸ 2026-09-07 · R108                     10
```

- Oben eine **Box mit Dropdown**: Sie nennt den Datensatz, dessen Treffer die
  Liste zeigt (Titel, Reifegrad-Chip, Trefferzahl), und öffnet eine Liste aller
  gesuchten Datensätze. Die Liste steht im Fluss des Panels (kein Popup, das der
  Panelrand abschneiden könnte); Klick auf die Box, Escape oder ein Klick
  außerhalb schließen sie.
- **Die gewählte Option ist der aktive Datensatz**: Heatmap, Quicklooks,
  Zeitleiste, Vollauflösung und Download folgen ihr wie bisher (§4.5).
- Die Hinweise je Datensatz stehen in der Box (für den gewählten) und in seiner
  Option im Dropdown:
  - `ignored_filters_by_collection[id]` enthält `datetime` → der Text aus
    `acquisitionNote` (fest aus M3-12); jeder andere ignorierte Filter →
    „Filter not applied: <name>“.
  - `incomplete_collections` → „Results incomplete: the source timed out“ /
    „… was not reachable“ / „… reported an error“ / „… sent an unreadable
    answer“; unbekannter Grund → „Results incomplete (<reason>)“.
  - Fallback → der bestehende `fallbackNotice`-Text.
  - Leer → „No scenes for this area.“
- Darunter die Gruppen je Überflug wie heute (`GroupBlock`,
  `results_group_by`); den offenen Zeitschritt merkt sich der Store über den
  Gruppen-Schlüssel, nicht über den Index, damit „Load more“ ihn nicht
  verschiebt (§4.4).
- **Anfangs gewählt:** der erste Datensatz mit Treffern in der Reihenfolge der
  Datensatzliste; hat keiner Treffer, der zuvor aktive.
- **Das Fenster verschwindet nie durch die Wahl.** Es gibt kein „nichts
  gewählt“; auch ein Datensatz ohne Treffer ist wählbar und zeigt seine Hinweise
  in der Box. Das Fenster fehlt nur, wenn ein einzelner Datensatz nichts fand
  (dann spricht der Such-Hinweis) oder noch nicht gesucht wurde. Mit nur einem
  gesuchten Datensatz ist die Box ohne Dropdown.
- Überschrift „Time steps“ wird „Results“; die Zahl im Kopf ist die Summe.

### 4.4 „Load more“ und die gemischte Seitenmarke (→ F1)

Die gemischte Marke gilt für die **ganze** Suche: Ihr Fingerabdruck umfasst
alle Collections (M3-13 §4.3), und für den Client ist sie undurchsichtig
(`adr/0005` Regel III). Eine Fortsetzung je Datensatz gibt es damit nicht,
ohne das Backend zu ändern oder die Marke im Client aufzuschlüsseln.

**Vorschlag: ein gemeinsamer Knopf.** Nach Ottos Änderung vom 30.09.2026
(Dropdown, §4.3) sitzt er **unter der Liste des im Dropdown gewählten
Datensatzes** und ist die Fortsetzung der ganzen Suche: Er lädt die nächste
Seite der gemischten Marke, neue Items landen in ihrem Datensatz, und die
Trefferzahlen im Dropdown wachsen. Er ist an den gewählten Datensatz gebunden,
soweit sein Satz und sein Platz betroffen sind — nicht seine Wirkung, denn eine
Fortsetzung nur eines Datensatzes braucht eine Marke je Collection (Backend, oben
Option 2 von F1, verworfen). Der Satz unter dem Knopf nennt deshalb nicht den
gewählten Datensatz als den mit „mehr“.

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
- Datensätze aus dem ±90-Tage-Fallback (§4.2) blättern nicht mit; der Fallback
  lädt ohnehin den ganzen Tag.
- **Fallback je Datensatz (F7, nach Ottos Änderung):** Er bezieht sich auf den
  im Dropdown gewählten Datensatz: Wählt der Nutzer einen Datensatz mit
  Zeitachse, der keine Treffer im Zeitraum hat, läuft für ihn (nur für ihn) der
  ±90-Tage-Fallback; das Ergebnis und sein Hinweis stehen in seiner Box und
  seiner Option. Keine parallelen Fallback-Suchen beim Suchen.
- Mit einem einzigen gewählten Datensatz ist es dieselbe Bedienung; die Marke
  ist dann die des Adapters oder von pgstac.

`api.searchAllPages` bekommt dafür eine optionale Start-Marke und gibt die
letzte Marke zurück, dazu `ignoredFiltersByCollection`.

### 4.5 Heatmap, Quicklooks, Vollauflösung (→ F3, F4, F5)

Leitgedanke (Otto, 30.09.2026, zweite Rückmeldung): **Die Karte folgt dem
Dropdown.** Zu sehen ist nur der im Dropdown gewählte Datensatz — seine
Quicklooks, sein automatischer Zuschnitt, seine Footprints. Andere Datensätze
der Suche sind unsichtbar, außer der Nutzer hat eine Ebene davon im
Layer-Manager angeheftet; angeheftete Ebenen (`LayerRestore.datasetId`) bleiben
immer zu sehen und liegen übereinander.

- **Coverage (F3, ersetzt):** Die Coverage-Map gehört nicht mehr zum aktiven
  Datensatz. Der Knopf „Coverage“ im Fuß des Control Centers (§3) zeigt sie für
  einen gewählten Datensatz (`coverageDatasetId`), unabhängig vom Dropdown; die
  Auswahl in der Legende aus M3-10a entfällt, weil der Knopf sie ersetzt.
- **Quicklooks (F4):** nur die des offenen Zeitschritts im gewählten Datensatz,
  wie heute. Die Zeitleiste zeigt die Überflüge dieses Datensatzes.
- **Automatischer Zuschnitt (ersetzt F5 (2) vom 30.09.2026, zweite
  Rückmeldung):** Ein Datensatz mit `browse: 'full_resolution'` (der DEM)
  erscheint als auf die AOI zugeschnittene Vollauflösung, **sobald er im
  Dropdown gewählt ist** — nicht mehr als angeheftete Ebene. Der Zuschnitt
  gehört zu den Suchergebnissen seines Datensatzes (`searchCrops` im Store, je
  Zeitschritt eine Ebene, `searchLayers.ts`); er ist auf der Karte, solange sein
  Datensatz gewählt ist, und geht mit den Ergebnissen (neue Suche, Auswahl
  geändert, „Clear all“). Anheften kann ihn der Nutzer selbst („＋ Pin to
  layers“ unter dem Dropdown, `pinSearchCrops`); die Kopie bleibt dann, egal
  welcher Datensatz gewählt ist. Die Zeichenreihenfolge „unter den Quicklooks“
  ist damit gegenstandslos (Quicklooks und Zuschnitt gehören nie zum selben
  Datensatz), die Markierungsebene dafür ist entfernt. Die Vollauflösungs-Ansicht
  mit Stretch-Steuerung (`focusMode`) bleibt dem, was der Nutzer selbst startet.
- **Angeheftete Ebenen (F4 (1), Otto 30.09.2026):** Ebenen verschiedener
  Datensätze bleiben im Layer-Manager und auf der Karte zugleich sichtbar,
  unabhängig vom gewählten Datensatz, von der Auswahl im Control Center und von
  der nächsten Suche. Eine Ebene zu wählen macht ihren Datensatz zum aktiven und
  öffnet seinen Abschnitt (ist er nicht mehr angehakt, wird er wieder
  angehakt).
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
| M3-10a | Umschalt-Knöpfe, Mehrfachauswahl, Dropdown der Treffer, aktiver Datensatz, Coverage-Schalter, Heatmap-Legende, `ignoredFiltersByCollection`, F6 | ≈ 500, davon ≈ 250 (tatsächlich mehr, §10) |
| M3-10b | „Load more“, Fallback für den gewählten Datensatz, Namenssuche über mehrere | ≈ 330, davon ≈ 170 |

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
- **Zeichenreihenfolge (Otto, 30.09.2026, Option 2) — ersetzt am 30.09.2026, §12:
  Markierungsebene und `fromSearch` sind entfernt.** Die automatisch gesetzten
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

---

## 11. Nachbesserung nach Ottos lokaler Prüfung (30.09.2026)

Alle sechs Punkte im selben PR umgesetzt.

1. **Umschalt-Knöpfe** mit Mehrfachauswahl statt Liste mit Kontrollkästchen
   (`DatasetPicker`, `.dataset-toggle`); gewählte Knöpfe sind getönt, umrandet,
   glühen und sind fett.
2. **Vier Zeilen sichtbar**, darüber scrollt die Liste (`max-height` aus
   Zeilenhöhe und Abstand).
3. **Kein Textfilter mehr;** Filterfunktionen entfernt (§4.1), `keywords` bleibt.
4. **Layout:** `.control-panel` ist höchstens `100dvh − 32px` hoch (oben wie unten
   16 px), Inhalt scrollt in `.control-scroll`, „Search“ und Hinweise stehen in
   `.control-footer`; dazu kompakter (Abstände, Werkzeugleiste dreispaltig).
   Beleg mit Chromium (Playwright, Datensatzliste mit sechs Einträgen): Abstand
   oben 16 px; unten 16 px, sobald der Inhalt die Fensterhöhe füllt, sonst mehr;
   „Search“ liegt in allen geprüften Höhen im Fenster (600, 720, 768, 900,
   1080 px); ab 720 px Höhe scrollt nichts.
5. **Trefferliste:** Dropdown-Box statt Abschnitten (§4.3). Ursache des
   verschwindenden Fensters: `App.tsx` blendete die Ergebnisleiste aus, sobald
   `groups` leer war, was beim Zuklappen des offenen Abschnitts geschah. Jetzt
   gibt es kein Zuklappen mehr, und die Leiste hängt an `hasResultsPanel`
   (`sections.ts`), nicht an den Gruppen des gewählten Datensatzes.
6. **Coverage-Map** im Control Center (`CoverageControls`), Zeile im
   Layer-Manager entfernt.

Tests: `ControlPanel.test.tsx` (Umschalter, kein Filter, Vierzeilen-Liste,
Coverage-Schalter, Fuß mit „Search“), `ResultsPanel.test.tsx` (Dropdown),
`LayerManager.test.tsx` (neu, keine Coverage-Zeile), `store.sections.test.ts`
(immer ein Datensatz gewählt, leerer Datensatz wählbar). Nicht in einem Test
prüfbar ist die Pixelgeometrie; dafür der Beleg oben.

---

## 12. Zweite Rückmeldung nach Ottos lokaler Prüfung (30.09.2026)

1. **Karte folgt dem Dropdown** (§4.5): Quicklooks, automatischer Zuschnitt und
   Footprints nur für den gewählten Datensatz; angeheftete Ebenen bleiben.
   `searchCrops` statt angehefteter Ebenen mit Flag; `layersOnMap`
   (`searchLayers.ts`) bestimmt, was `MapView` zeichnet; `pinSearchCrops` ist der
   eigene Schritt des Nutzers. Die Markierungsebene für „unter den Quicklooks“
   ist entfernt (gegenstandslos). Ersetzt F5 (2) vom 30.09.2026.
2. **Datensatz-Knöpfe als Raster 2×2** (`.dataset-list`, `grid`), darüber scrollt
   es. Lange Titel umbrechen auf zwei Zeilen, neben dem Reifegrad-Chip bleibt es
   eine.
3. **Dropdown abgesetzt:** eigene getönte Karte mit Beschriftung „Showing
   dataset“, Akzentlinie darunter, darüber „Scenes by time step“ als Kopf der
   Liste. Ein Skill `frontend-design` gab es in dieser Umgebung nicht; die
   Gestaltung folgt den vorhandenen Theme-Tokens und dem HUD-Muster aus
   `prototyp-inventar.md`.
4. **Coverage-Knopf** wie in §3; `coverageDatasetId` im Store, `showCoverageFor`
   und `hideCoverage` ersetzen `toggleCoverage`; `setDatasetId` und die
   Legenden-Auswahl entfallen. Wird der Datensatz der Coverage abgewählt, geht sie
   aus.
5. **Hintergrund hinter der Weltkugel:** Token `--map-bg` (Tech: dunkel, Hell:
   `#ffffff`); `.app` malt ihn, der `body` hat keine feste Farbe mehr, und
   `background`-Ebene und `sky` der Karte bekommen den Tokenwert beim Erzeugen und
   bei jedem Themenwechsel (`mapStyles.ts::applyMapBackground`).

Tests: `store.sections.test.ts` (Sichtbarkeit je Dropdown-Wahl, angeheftete Ebenen
bleiben, Coverage unabhängig vom Dropdown), `searchLayers.test.ts`
(`layersOnMap`), `ControlPanel.test.tsx` (Coverage-Auswahl erst beim Klick),
`ResultsPanel.test.tsx` (abgesetzte Karte, Pin-Zeile), `mapStyles.test.ts` (neu,
Token in beiden Themen, Stil, Umfärben).

Beleg mit Chromium (Playwright, Antworten gemockt): Raster mit 2 Spalten und 2
Zeilen, der fünfte Knopf verdeckt und das Raster scrollt; „Coverage“ und „Search“
im Fuß, „Search“ im Fenster; vor der Auswahl in der Coverage-Wahl wird nichts
gezeichnet; `.app` malt im Hell-Modus `rgb(255, 255, 255)`, im Dunkel-Modus
`rgb(4, 7, 10)`. Das Globus-Bild selbst (Kacheln) ließ sich ohne Netz nicht
prüfen.

---

## 13. Umsetzung M3-10b (30.09.2026)

Grundlage: F1 (1), F7 (1), F8 (1), übertragen auf das Dropdown und die Karte, die
ihm folgt (§4.3–§4.5, §12).

- **„Load more“ (F1, §4.4):** `api.searchAllPages` nimmt eine Start-Marke und gibt
  die übrige Marke zurück. Der Store hält die Suche, zu der die Treffer gehören
  (`searchContext`: Anfrage, AOI und Zeitraum der Suche, geladene Items,
  gesammelte Antwort, Marke). Der Knopf steht unter der Liste des gewählten
  Datensatzes, mit „More scenes may be available.“, und führt die gemischte Marke
  der ganzen Suche fort, je Klick bis 300 Items. Neue Items landen in ihrem
  Datensatz; gewählter Datensatz, aktiver und offener Zeitschritt (über den
  Gruppen-Schlüssel) und die ausgewählten Szenen bleiben. Ein Item, das schon
  geladen ist (gleiche Collection und Kennung), kommt nicht doppelt dazu. Die
  Trefferzahlen und der Such-Hinweis wachsen mit; mit einem Datensatz sagt der
  Hinweis bei verbleibender Marke nur noch „… matched in total.“, ohne den Rat,
  die Suche zu verkleinern.
- **Fehler und Verwerfen:** Ein Fehler lässt die Treffer stehen, sagt „Could not
  load more results — search again.“ und verwirft die Marke. AOI oder Zeitraum zu
  ändern verwirft nur die Marke, die Treffer bleiben; Auswahl ändern, neue Suche,
  Namenssuche und „Clear all“ verwerfen die ganze Suche. Eine Antwort, die danach
  kommt, wird nicht mehr angezeigt (Zähler `searchGen`); das gilt auch für den
  Fallback.
- **Fallback (F7):** Er läuft für den im Dropdown gewählten Datensatz, wenn dessen
  Box leer ist, der Datensatz eine Zeitachse hat, ein Zeitraum gesucht wurde und
  seine Quelle vollständig geantwortet hat (`sections.ts::needsFallback`). Bei der
  Suche selbst betrifft das nur den Datensatz, mit dem das Dropdown öffnet — also
  nur, wenn kein Datensatz Treffer hat; sonst, sobald ein leerer Datensatz gewählt
  wird. Keine parallelen Fallback-Suchen. Er fragt nur diesen Datensatz, mit AOI
  und Zeitraum der Suche, und läuft einmal je Suche. Ergebnis und Hinweis stehen
  in Box und Option des Datensatzes; solange er läuft, steht dort „Looking for the
  nearest date with scenes…“. Ein Fehler steht ebenfalls dort („Could not look for
  the nearest date: …“) statt als Fehler der ganzen Suche. Mit einem Datensatz
  sagt der Such-Hinweis es wie bisher.
- **Fallback und „Load more“:** Ein Datensatz im Fallback blättert nicht mit und
  behält den Fallback, solange die fortgesetzte Suche nichts für ihn bringt.
  Bringt sie doch Treffer im Zeitraum (möglich, wenn sich eigene Collections eine
  Quelle der gemischten Suche teilen und die ersten 300 Items von einer anderen
  kamen), ersetzen diese den Fallback — er stand nur für „nichts im Zeitraum“.
- **Namenssuche (F8):** Sie fragt alle angehakten anzeigbaren Datensätze parallel.
  Der erste Datensatz in Listenreihenfolge mit der Szene öffnet im Dropdown, die
  Karte fliegt hin, die Szene ist ausgewählt; jeder andere sagt in seiner Box, was
  er geantwortet hat („No scene named …“, „Not a valid scene name for this
  dataset.“, „Scene lookup failed: …“). Hat keiner die Szene, ändert sich nur der
  Fehler (M2-17 F4): kein Datensatz fand sie, alle lehnten den Namen ab, oder eine
  Quelle fiel aus (mit Titel). Mit einem Datensatz ist die Bedienung wie bisher.
  Ein Treffer in einem Datensatz ohne Vorschau (DEM) zeigt die Vollauflösung,
  sobald sein Datensatz im Dropdown gewählt ist, nicht nur, wenn er als erster
  öffnet. Während der Namenssuche ist die Datensatz-Auswahl gesperrt wie während
  der Suche.
- **Nebenfund:** Die Namenssuche ließ die Zuschnitte der vorigen AOI-Suche
  (`searchCrops`) stehen; fand sie eine DEM-Kachel, lagen die alten Zuschnitte
  wieder auf der Karte. Jetzt leert sie sie.

**Geändert:** `frontend/src/api.ts`, `sections.ts`, `store.ts`,
`components/ResultsPanel.tsx`, `components/ControlPanel.tsx`, `index.css`. Tests:
`api.test.ts`, `sections.test.ts`, `store.sections.test.ts`, `store.test.ts`,
`components/ResultsPanel.test.tsx`, `components/ControlPanel.test.tsx`.

Otto prüft lokal: drei Datensätze, eine AOI und ein Zeitraum mit mehr als 300
Sentinel-2-Treffern („Load more“, Zahlen im Dropdown, offener Zeitschritt bleibt);
ein Zeitraum ohne Treffer für einen Datensatz (Wahl im Dropdown startet den
Fallback nur für ihn); ein Szenenname mit mehreren angehakten Datensätzen.
