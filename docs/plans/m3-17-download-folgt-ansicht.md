# M3-17 — Download folgt der Ansicht: Umsetzungsplan

**Aufgabe:** M3-17 aus `docs/plans/m3-dritte-quelle-und-interface.md` §4.
**Stufe B.** **Freigegeben (Otto, 26.09.2026): alle Fragen in §9 nach
Empfehlung (F1–F6 jeweils Option 1).** Umgesetzt in diesem Branch/PR; §9 ist
um die gewählte Option ergänzt, §10 hält den tatsächlichen Stand fest.
**Abhängigkeit geändert (Otto, 23.09.2026):** M3-17 hängt nicht mehr von M3-12
ab. Die Gruppierung je Überflug hat PR #84 gebaut (`store.groups`,
`groupIndexOfItem`, ein Layer je Gruppe); M3-17 verwendet sie wieder und baut
keine neue datensatzspezifische Stelle (Plan §3, `ENTSCHEIDUNGSLOG.md`).
**Ort im Repo:** `docs/plans/m3-17-download-folgt-ansicht.md`
**Grundlagen:** `plans/m3-dritte-quelle-und-interface.md` (P12, P19, §4 M3-09,
M3-12, M3-17, M3-18); `plans/m3-09-zuschnitt-ansicht.md` §7, §8, §10;
`plans/m3-18-download-deckel-maske.md` §10, §13; `ENTSCHEIDUNGSLOG.md`, Zeilen
vom 23.09.2026 (P19) und 24.09.2026 (M3-09 F3, M3-18); `architekturplan.md`
3.1, 5.1, 6.2, 6.4; `KLAERUNGEN.md` B8, B9, B10, B11; `adr/0003` §11.2.

---

## 1. Ziel in einem Satz

Der Download liefert, was die Karte zeigt: sichtbarer Zuschnitt → je Gruppe
eine gemergte Datei in einem ZIP; ganze COG-Szene sichtbar → die Originaldatei
direkt von der Quelle durch den Browser; Zarr → immer Zuschnitt, ohne AOI ist
der Knopf deaktiviert.

---

## 2. Heutiger Stand am Code

| Stelle | Heute | Folge für M3-17 |
|---|---|---|
| `components/ViewBar.tsx` | Knopf „⇩ Download“ im Browse-Modus, öffnet `store.openDownloadForSelection` | Modus hängt künftig an Ansicht, AOI und Format (§4) |
| `components/LayerManager.tsx` | ⇩ je Layer, sichtbar über `canDownloadLayer` | dieselbe Entscheidung wie oben, aus `layer.restore` |
| `download.ts::downloadRequestFor` / `downloadRequestForSelection` | verlangen **immer** eine AOI und bauen **einen** Request mit allen Items | wird eine Entscheidung mit drei Ausgängen (§4) |
| `store.ts::confirmDownload` | ein `POST /collections/{ds}/download`, ZIP per Blob-URL | Zuschnitt bleibt so, Originale laufen nicht über die Plattform |
| `store.ts::addCurrentToLayers` (PR #84, F5) | im Zuschnitt-Modus ein Layer je Gruppe über `groupIndexOfItem(s.groups, id)` | **die Gruppierung, die M3-17 wiederverwendet** |
| `grouping.ts::buildGroups`, `displayGroupBy` | Gruppen der Trefferliste (heute Tag + `s2:datatake_id`, sonst `earthx:viewer.group_by`) | Quelle der Gruppen; den festen Namen `s2:datatake_id` räumt M3-12 in die Registry, M3-17 fügt nichts hinzu |
| `api/tiler.py::DownloadRequest` | `items: list[str]`, ein Mosaik über alle Items | braucht Gruppen (§5) |
| `access/download.py::build_download_zip` | ein Mosaik je Asset, `compute_crop_region` über alle Items | je Gruppe ein Mosaik und eine eigene Region |
| `catalog/collection.py` | `DatasetConfig.format` (`cog`/`zarr`/`legacy`) wird **nicht** veröffentlicht | das Frontend kann COG und Zarr heute nicht unterscheiden (§6) |
| `DownloadDialog.tsx` | Titel „Download crop“, Auflösungswahl, geänderte Attribution | für Originale: Liste von Links, ungeänderte Attribution, keine Auflösungswahl |

**Befund Gruppen im ZIP.** P19 verlangt verschiedene Gruppen als getrennte
Dateien **im selben ZIP**. Heute gilt das nur mittelbar: Seit PR #84 ist ein
zugeschnittener Layer genau eine Gruppe, sein Download also ein ZIP je Gruppe.
Der Download einer Auswahl aus der Trefferliste über mehrere Gruppen mergt
dagegen alle Items in **ein** Mosaik — das widerspricht P19 und wird mit
dieser Aufgabe behoben.

**Befund Deckel.** P19 nennt „Deckel 4096 px und 200 MB bleiben“. Beides ist
seit M3-18 überholt (Log 23.09.2026: immer native Auflösung, kein `max_size`;
Log 24.09.2026, F10a: 500 MB roh `MAX_TOTAL_OUTPUT_BYTES`, dazu höchstens ein
großer Download gleichzeitig). M3-17 übernimmt den Stand von M3-18 und prüft
die Deckel über die Summe aller Gruppen eines Requests (§5).

---

## 3. Randbedingungen

- Keine neue datensatzspezifische Stelle im Frontend. Die Gruppen kommen aus
  `store.groups` bzw. aus dem, was beim Anheften daraus festgehalten wurde.
  Ändert M3-12 später die Quelle des Gruppierungsschlüssels, folgt der
  Download ohne Änderung.
- Originale laufen nicht über die Plattform (`architekturplan.md` 6.4: „Kein
  Byte läuft durch das eigene Backend“). Der Browser lädt von der Quelle, wie
  im lokalen Runner (B9: Zugriff von der IP des Nutzers). `gateway` (B8)
  betrifft nur Requests der Plattform und ist nicht berührt.
- Keine AOI in URLs oder Logs: Der Zuschnitt schickt die AOI wie bisher im
  `POST`-Rumpf; Originale brauchen keine AOI. Die Log-Zeile von
  `download_crop` bekommt nur Zählwerte (Gruppen, Items, Assets, Bytes).
- Zustandslos (`adr/0001`), kein Zwischenspeicher.
- `readers` unverändert (M3-Abnahme).

---

## 4. Entscheidung je Fall

Eine reine Funktion in `download.ts` entscheidet aus Ansicht, AOI und Format
genau einen von drei Ausgängen: **Zuschnitt je Gruppe**, **Originale**, oder
**deaktiviert mit Hinweis**.

| Ansicht | AOI | Format | Ausgang | Quelle der Regel |
|---|---|---|---|---|
| Zuschnitt sichtbar („Crop & merge to AOI“ oder zugeschnittener Layer) | ja | beliebig | Zuschnitt, je Gruppe eine Datei | P19 |
| ganze Szene(n) sichtbar („View full selection“ oder Layer mit `cropToAoi: false`) | egal | COG | Originale, je Szene und Asset ein Link | P19 |
| ganze Szene(n) sichtbar | ja | Zarr | Zuschnitt je Gruppe | P19 („Zarr immer als Zuschnitt“) |
| ganze Szene(n) sichtbar | nein | Zarr | deaktiviert, „Draw an AOI to download“ | P19 |
| Browse (Quicklooks) oder Quicklook-Layer | ja | beliebig | Zuschnitt je Gruppe | Vorschlag, F5 |
| Browse oder Quicklook-Layer | nein | COG | Originale | Vorschlag, F5 |
| Browse oder Quicklook-Layer | nein | Zarr | deaktiviert, „Draw an AOI to download“ | P19 |

Die dritte Zeile weicht bewusst von „Download folgt der Ansicht“ ab: P19 legt
für Zarr den Zuschnitt fest, ein Zarr-Speicher ist keine einzelne Datei.

Das Muster „Knopf deaktiviert + Tooltip mit Begründung“ kommt aus M3-09
(„Crop & merge to AOI“ ohne AOI, `ViewBar.tsx`). Die bekannte Abweichung aus
`m3-09-zuschnitt-ansicht.md` §7 („View full selection“ mit AOI lädt den
Zuschnitt) ist mit Zeile 2 aufgelöst.

---

## 5. Zuschnitt je Gruppe

**Übergabe (F3, Empfehlung 1).** Der Rumpf von
`POST /collections/{ds}/download` bekommt `groups: list[list[str]]` statt
`items`. Das Frontend füllt die Listen aus der vorhandenen Gruppierung
(`groupIndexOfItem(store.groups, id)`, dieselbe Aufteilung wie
`addCurrentToLayers`). Das Backend kennt keinen Gruppierungsschlüssel, es
nimmt die Listen, wie sie kommen. So zeigt die Datei genau die Gruppen der
Trefferliste und der gelben Umrandung aus PR #84.

**Layer.** `LayerRestore` bekommt `groupItemIds: string[][]`, beim Anheften aus
`store.groups` festgehalten. Der Download eines Layers hängt damit nicht an
der laufenden Suche, wie schon `restore.itemIds` (V-6). Ein zugeschnittener
Layer aus PR #84 hat genau eine Liste.

**Backend.**
- Je Gruppe: `filter_items_intersecting_aoi`, `compute_crop_region` (AOI ∩
  Footprints **dieser** Gruppe), ein `mosaic_reader`-Mosaik je Asset mit
  `FirstMethod`, Reihenfolge der Items wie übergeben.
- Eine Gruppe, die die AOI nicht trifft, fällt weg und steht in der
  `ATTRIBUTION.txt` als „not covered by the AOI“. `400` nur, wenn keine Gruppe
  die AOI trifft (wie heute bei keinem Item).
- Deckel über den ganzen Request: `MAX_DOWNLOAD_ITEMS` über alle Gruppen,
  `MAX_TOTAL_OUTPUT_BYTES` als Summe der geplanten Ausgaben aller Gruppen, die
  Sperre für große Downloads ebenso. Speicher und Laufzeit gehören zum
  Request, nicht zur Gruppe.
- Prüfungen vor dem Lesen: leere Gruppe, leere Liste, dieselbe Item-ID in zwei
  Gruppen → `422`.
- ZIP-Aufbau: eine Gruppe → flach wie heute (bestehende Dateien und Tests
  bleiben gleich). Mehrere Gruppen → je Gruppe ein Ordner `group-01/`,
  `group-02/` … mit Datendatei und Maske je Asset; `aoi.geojson` und
  `ATTRIBUTION.txt` einmal im Wurzelverzeichnis; die Notiz nennt je Ordner die
  Items. Ordnernamen erzeugt das Backend, kein vom Client gelieferter Text wird
  Pfad im ZIP.

---

## 6. Originale

**COG oder Zarr erkennen (F4, Empfehlung 1).** `catalog/collection.py`
veröffentlicht das vorhandene `DatasetConfig.format` als `earthx:format`
(`cog`, `zarr`, `legacy`). Kein neues Registry-Feld: `format` ist schon Pflicht
und ohne Vorgabewert (B10); `collection.py` bildet ab und deutet nicht. Neue
Zeile in `architekturplan.md` 5.1. Das Frontend bietet Originale nur für `cog`
an; jeder andere oder fehlende Wert gilt wie Zarr (nur Zuschnitt), damit ein
unbekannter Wert nie zu einem Link auf einen Speicher statt einer Datei führt.
Die Regel steht an einer Stelle (`download.ts`) und nennt ein Format, keinen
Datensatz.

**Welche Dateien (F1, Empfehlung 1).** Die Assets der sichtbaren Darstellung:
im Fokus-Modus `downloaded[id].asset`, sonst `earthx:default_render.assets`.
Bei Earth Search ist das heute ein Asset (`visual`).

**Woher die Adressen kommen.** Aus dem STAC-Item: bei der Auswahl aus
`store.items`, bei einem Layer per `api.fetchItem` beim Öffnen des Dialogs
(über `api`, wie jede andere Item-Abfrage). Verlinkt wird nur ein `href` mit
Schema `https` und einem Host aus `earthx:source.asset_hosts` (D12). Alles
andere zeigt der Dialog als „not available as a direct download“. Grund: Die
Items kommen föderiert von fremden Quellen; ein `javascript:`- oder fremder
Link darf nicht in der Oberfläche landen.

**Wie der Browser lädt (F2, Empfehlung 1).** Der Dialog zeigt die
Attribution und die Nutzungsbedingungen, darunter je Szene und Asset einen
Link `<a href download target="_blank" rel="noopener noreferrer">`, nach Gruppe
geordnet (Label aus `store.groups`). Der Nutzer klickt jede Datei selbst. Das
braucht kein CORS (M3-09 §7, Fund 2), keinen Speicher im Browser und löst
keine Sperre für mehrere automatische Downloads aus. `noreferrer`, damit die
Quelle die Adresse der Seite nicht erfährt. Ein Zusammenfassen der Originale
zu einem Mosaik je Überflug bleibt M4 (P19, Vorschlag).

**Lizenz und Attribution (B11, `adr/0003` §11.2).** Ein Link zur Quelle ist
laut B11 schon auf Stufe „Katalogeintrag“ erlaubt. Die Originale verlangen
deshalb nicht Stufe „Processing“, der Zuschnitt weiterhin schon (`403` im
Backend, `canExportLicense` im Dialog). Das Original ist ungeändert: Der
Dialog zeigt `attribution_unmodified`, der Zuschnitt weiterhin
`attribution_modified`. Weil kein ZIP mit `ATTRIBUTION.txt` entsteht, stehen
Attribution, Nutzungsbedingungen und `terms_url` sichtbar vor den Links.

**Öffentlich über https.** Die Asset-Hosts beider COG-/Zarr-Datensätze sind
`https`-Adressen und werden vom Kachelpfad schon heute ohne Token gelesen
(Checkliste Punkt 6, `earthx:access.token_free_checked_at`). Das ist derselbe
anonyme `GET`, den der Browser macht. In dieser Sitzung habe ich keine
Messung an der Quelle gemacht (0 Anfragen). Otto prüft den Link lokal (§8).

---

## 7. Umsetzung

| Datei | Änderung |
|---|---|
| `backend/earthx/api/tiler.py` | `DownloadRequest.groups`, Prüfungen (§5), Schleife über Gruppen, Log nur mit Zählwerten |
| `backend/earthx/access/download.py` | `build_download_zip` nimmt Gruppen (je Gruppe `AssetCrop`s und Region), Ordner bei mehreren Gruppen, Notiz je Gruppe; Deckelsumme |
| `backend/earthx/catalog/collection.py` | `earthx:format` |
| `frontend/src/download.ts` | Entscheidung §4 als reine Funktion; Gruppenlisten; Link-Prüfung auf `https` + `asset_hosts`; Attribution je Ausgang |
| `frontend/src/components/DownloadDialog.tsx` | zwei Ansichten: Zuschnitt (wie heute) und Originale (Links, keine Auflösungswahl) |
| `frontend/src/components/ViewBar.tsx`, `LayerManager.tsx` | Knopf deaktiviert mit „Draw an AOI to download“ im Zarr-Fall; Tooltip nach Ausgang |
| `frontend/src/store.ts`, `layers.ts` | `groupItemIds` beim Anheften; `confirmDownload` schickt `groups`; Items eines Layers per `fetchItem` für Originale |
| `frontend/src/api.ts`, `types.ts` | `groups` im Request, `earthx:format` im Collection-Typ |
| `docs/architekturplan.md` 5.1 | Zeile `earthx:format` |

**Umfang.** Geschätzt 250 Zeilen Produktivcode und 350 Zeilen Tests, über dem
Richtwert von 400 Zeilen. Deshalb F6.

---

## 8. Abnahme

**Vitest** (`download.test.ts`, `store.test.ts`), je Fall aus P19:
- Zuschnitt, eine Gruppe → Request mit einer Liste.
- Zuschnitt, mehrere Gruppen → Request mit einer Liste je Gruppe, Aufteilung
  wie `store.groups`.
- Eine ganze COG-Szene → ein Link, `href` gleich dem Asset-`href`.
- Zarr ohne AOI → deaktiviert, Hinweis „Draw an AOI to download“; Zarr mit AOI
  bei „View full selection“ → Zuschnitt.
- Mehrere ganze COG-Szenen → je Szene und Asset ein Link, nach Gruppe
  geordnet.
- Fehlerfälle: `href` mit `http:`, `javascript:`, `s3:` oder fremdem Host →
  kein Link; fehlendes oder unbekanntes `earthx:format` → kein Original;
  Layer ohne `groupItemIds` (vor M3-17 angeheftet) → eine Gruppe aus
  `itemIds`.
- Kein Link und kein Request-Pfad enthält eine AOI-Koordinate.

**pytest** (`backend/tests/…/test_download*.py`):
- Zwei Gruppen → ZIP mit `group-01/` und `group-02/`, je Ordner eine
  gemergte Datei und Maske je Asset, `aoi.geojson` und `ATTRIBUTION.txt` einmal.
- Eine Gruppe → ZIP-Aufbau unverändert.
- Eine Gruppe verfehlt die AOI → fehlt im ZIP, steht in der Notiz; alle
  verfehlen → `400`.
- Deckel über die Summe: zwei Gruppen je unter, zusammen über
  `MAX_TOTAL_OUTPUT_BYTES` → `413`; Items über alle Gruppen über
  `MAX_DOWNLOAD_ITEMS` → `413`.
- Leere Gruppe, keine Gruppe, doppelte Item-ID → `422`.
- Log mit echtem Logging-Setup: keine Koordinate.
- `earthx:format` erscheint in `/stac/collections` für beide Einträge.

**Otto lokal:** AOI über zwei Überflüge, „Crop & merge to AOI“, Download aus
der Auswahl: ein ZIP, zwei Ordner, jede Datei deckt sich mit der gelben
Umrandung ihrer Gruppe. „View full selection“ mit einer Earth-Search-Szene:
der Link lädt die Originaldatei von der Quelle; im Netzwerk-Tab keine Anfrage
an die Plattform für diese Datei. EOPF ohne AOI: Knopf deaktiviert.

Vor dem Fertigmelden: `ruff check backend`, `pytest`,
`lint-imports --config .importlinter`, `npm run lint`,
`npx tsc -b --pretty false`, `npx vitest run`.

---

## 9. Fragen an Otto — beantwortet 26.09.2026 (alle nach Empfehlung, Option 1)

**F1 — Welche Dateien bei „Original“?**
1. Nur die Assets der sichtbaren Darstellung (heute bei Earth Search `visual`).
   **Empfehlung**: „Download folgt der Ansicht“ wörtlich, kleinster Umfang.
2. Alle Assets mit Rolle `data`.
3. Auswahl im Dialog, sichtbare Darstellung vorausgewählt.

**F2 — Wie lädt der Browser mehrere Originale?**
1. Liste von Links im Dialog, jede Datei ein Klick. **Empfehlung**: kein CORS,
   kein Speicher im Browser, keine Sperre für Mehrfach-Downloads.
2. Ein Knopf „Download all“, der die Links nacheinander auslöst; der Browser
   fragt beim zweiten Download nach Erlaubnis oder verwirft ihn still.
3. Im Browser laden und zu einem ZIP packen: braucht CORS auf dem Asset-Host
   und hält ganze Szenen im Speicher des Browsers.

**F3 — Wie kommen die Gruppen in den Request?**
1. `groups: list[list[str]]` statt `items`, gefüllt aus `store.groups`; ein
   ZIP, bei mehreren Gruppen ein Ordner je Gruppe. **Empfehlung**: nutzt die
   Gruppierung aus PR #84, das Backend braucht keinen Schlüssel.
2. Ein Request je Gruppe, mehrere ZIPs: widerspricht „im selben ZIP“ (P19).
3. Das Backend gruppiert selbst nach `earthx:viewer.group_by`: weicht von der
   Trefferliste ab (Tag + Kachel statt Tag + Überflug) und bräuchte eine neue
   datensatzspezifische Stelle im Backend.

**F4 — Woran erkennt das Frontend COG oder Zarr?**
1. `DatasetConfig.format` als `earthx:format` veröffentlichen, Zeile in 5.1.
   **Empfehlung**: kein neues Registry-Feld, nur Abbildung.
2. Neues Registry-Feld ohne Vorgabewert, z. B. `ViewerInfo.original_download`.
3. Je Asset aus dem STAC-Feld `type` (Media-Type): EOPF-Assets tragen keinen,
   der Fall bräuchte einen Rückfall.

**F5 — Download aus der Trefferliste (Browse-Modus), Quicklooks ganz
sichtbar?**
1. Mit AOI Zuschnitt je Gruppe, ohne AOI Originale (COG) bzw. deaktiviert
   (Zarr). **Empfehlung**: wer eine AOI zeichnet, will sie im Download;
   entspricht dem heutigen Verhalten mit AOI.
2. Immer wie „ganze Szene sichtbar“: Originale, auch mit AOI.
3. Download-Knopf im Browse-Modus entfernen; Download nur über die
   Vollauflösung bzw. den Layer-Manager.

**F6 — Umfang über 400 Zeilen?**
1. Ein PR wie geplant, etwa 600 Zeilen mit Tests. **Empfehlung**: die Teile
   sind nur zusammen prüfbar (Otto lokal).
2. Aufteilen in M3-17a (Backend: `groups`, `earthx:format`) und M3-17b
   (Frontend), je eigene Session und eigener PR.

**Beschriftung (Vorschlag, keine eigene Frage):** Der Knopf bleibt „⇩ Download“;
der Tooltip nennt den Ausgang („Download the AOI crop, one file per group“ /
„Download the original files straight from the source“ / „Draw an AOI to
download“). Der Dialog heißt „Download crop“ bzw. „Download original files“.

---

## 10. Umsetzung (wie tatsächlich gebaut)

**Backend.**
- `access/download.py`: `GroupCrop` + `group_dirname` (F3). `build_download_zip`
  bekam `additional_groups: Sequence[GroupCrop] = ()` und `skipped_item_ids`,
  **ohne** die bestehende Signatur zu brechen — ein Aufruf ohne
  `additional_groups` (jeder Aufrufer vor M3-17, die meisten Tests) erhält
  genau das flache ZIP-Layout von vorher. Mit mehr als einer Gruppe schreibt
  jede Gruppe in einen eigenen `group-NN/`-Ordner; `aoi.geojson` und
  `ATTRIBUTION.txt` bleiben je ZIP einmal im Wurzelverzeichnis.
  `build_notice_text` bekam `group_item_ids`/`skipped_item_ids` für die
  „Group N (group-NN/): …“- bzw. „Not covered by the AOI, left out: …“-Zeilen.
- `api/tiler.py`: `DownloadRequest.groups: list[list[str]]` ersetzt `items`,
  mit einem `field_validator`, der leere Gruppen und eine über zwei (oder
  innerhalb einer) Gruppen wiederholte Item-ID mit `422` abweist. Der Ablauf
  in `download_crop` filtert und plant jede Gruppe einzeln
  (`filter_items_intersecting_aoi`, `compute_crop_region`); eine Gruppe, die
  die AOI nicht trifft, fällt weg statt die Anfrage scheitern zu lassen —
  `400` nur, wenn keine Gruppe übrig bleibt. Deckel (`check_item_count_cap`,
  `check_output_size_cap`) rechnen über die Summe aller übrig gebliebenen
  Gruppen.
- `catalog/collection.py`: `earthx:format` aus `DatasetConfig.format`
  (F4), Zeile in `architekturplan.md` 5.1.

**Frontend.**
- `download.ts`: `decideDownloadOutcome` ist die ganze Tabelle aus §4 als eine
  reine Funktion (Eingabe: `cropToAoi`, `hasAoi`, `isCog`). `isCogFormat`/
  `assetHostsOf` lesen `earthx:format`/`earthx:source.asset_hosts`.
  `isDirectDownloadHref` + `originalFileLinks` bauen die Originaldatei-Links
  (nur `https` und ein Host aus `asset_hosts`, F4/B11). `downloadRequestFor`/
  `downloadRequestForSelection` liefern jetzt `groups: string[][]` statt einer
  flachen Liste, gefüllt über `grouping.ts::groupItemIdsFor` (F3) — dieselbe
  Aufteilung, die `store.ts::addCurrentToLayers` (PR #84, F5) schon zieht,
  keine zweite, download-eigene Gruppierung.
- `layers.ts`: `LayerRestore.groupItemIds: string[][]`, beim Anheften gefüllt;
  ein vor M3-17 angehefteter Layer hat keins und fällt auf eine Gruppe zurück.
- `store.ts`: `openDownloadForSelection` entscheidet den Ausgang sofort (Items
  liegen schon in `store.items`, kein Fetch nötig). `openDownloadDialog` ist
  jetzt asynchron: Für einen Layer im Zuschnitt- oder deaktivierten Fall steht
  der Ausgang sofort fest; für „Originale“ holt es einmalig die STAC-Items des
  Layers (`api.fetchItem`), weil `restore` nur Kachel-Infos, keine
  Asset-`href`s trägt.
- `ViewBar.tsx`, `LayerManager.tsx`: der Download-Knopf bleibt sichtbar, wird
  im Zarr-ohne-AOI-Fall deaktiviert mit Tooltip „Draw an AOI to download“ —
  dasselbe Muster wie „Crop & merge to AOI“ in M3-09.
- `DownloadDialog.tsx`: verzweigt auf `store.downloadOutcome`. Zuschnitt wie
  bisher (Szenenzahl jetzt aus `req.groups.flat()`), Originale als reine
  Link-Liste je Gruppe (F2), mit `attribution_unmodified` (neuer dritter
  Parameter `modified` an `attributionText`) und ohne Lizenzstufen-Sperre
  (B11: ein Link reicht schon auf Stufe „Katalogeintrag“).

**F6 (Umfang):** wie geplant ein PR, siehe Diff.

## 11. Abnahme

- **pytest**: neue Fälle in `test_download_route.py` (zwei Gruppen als
  getrennte Ordner im selben ZIP, eine Gruppe bleibt das flache Layout, eine
  Gruppe fällt weg und die andere lädt trotzdem, alle Gruppen fallen weg →
  `400` wie zuvor, leere/doppelte Item-ID → `422`, Item-Deckel über die Summe
  aller Gruppen) sowie `earthx:format` in `test_collection.py`. `pytest`
  (Repo-Wurzel): grün. `ruff check backend`: grün.
  `lint-imports --config .importlinter`: 12/12 Verträge gehalten.
- **Vitest**: neue Fälle in `download.test.ts` (die ganze
  `decideDownloadOutcome`-Tabelle, `isCogFormat`, `assetHostsOf`,
  `isDirectDownloadHref` inkl. `javascript:`/`data:`/fremder Host,
  `originalFileLinks`, `downloadRequestForSelection` mit Gruppen),
  `grouping.test.ts` (`groupItemIdsFor`) und `store.test.ts`
  (`openDownloadForSelection`/`openDownloadDialog` für alle drei Ausgänge,
  Fetch-Fehler, unbekannte Layer-ID, Layer ohne `groupItemIds`). `npx vitest
  run`: grün. `npm run lint` (oxlint): grün. `npx tsc -b --pretty false`:
  grün.
- **Otto lokal (noch offen):** AOI über zwei Überflüge, „Crop & merge to
  AOI“, Download aus der Auswahl — ein ZIP, zwei Ordner, jede Datei deckt
  sich mit der gelben Umrandung ihrer Gruppe (PR #84). „View full selection“
  mit einer Earth-Search-Szene: der Link lädt die Originaldatei direkt von
  der Quelle; im Netzwerk-Tab keine Anfrage an die Plattform für diese Datei.
  EOPF ohne AOI: Knopf deaktiviert.
