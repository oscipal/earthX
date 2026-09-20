# M2-07a — Frontend: API-Client, Suche, Quicklooks, Zeitleiste: Umsetzungsplan

**Status:** **Plan fertig und von Otto angenommen** (20.09.2026, §12). **Stufe B**
laut `projektplan.md` 1.2: Plan zuerst als Draft-PR, Umsetzung nach dem OK — sie
beginnt als **eigene Sitzung**. Die Abhängigkeit von M2-04 ist erfüllt: `#39` ist
gemergt, `earthx:viewer` liegt auf `main` (§5).
**Aufgabe:** M2-07a aus `docs/plans/m2-format-und-viewer.md` §4 („M2-07 — Frontend
auf `earthx`", Abschnitt „Gemeinsam für 07a–07d" und „M2-07a").
**Grundlage:** `ENTSCHEIDUNGEN_2026-09-18.md` §1–§3 (BIOMASS bleibt nicht, was vom
Prototyp erhalten bleibt); `KLAERUNGEN.md` B8 (Gateway), B10 (Capability-Flags),
B13 (Registry gestuft); `architekturplan.md` 3.1 (Modulgrenzen), 5.1 (`earthx:`-Felder),
8.1 (API-first), 8.2 (Frontend); `projektuebersicht.md` §2 Prinzip 7 („API-first"),
9 („Ehrlichkeit in der Anzeige"), 11 („Robustheit gegen Quellenausfälle");
`prototyp-inventar.md` F1, F3–F8, F15, Teil 3 (HUD); `adr/0003` §10.3, §11.2;
`adr/0005` (föderierte Suche, Seitenmarke); `adr/0006` §3.6 (Quicklook ohne Proxy),
§3.7 (Asset-Host); Log-Zeilen vom 20.09.2026 (D7, D8, D14, F1 = a, F2 = a).
**Voraussetzungen — beide erfüllt:** Der Tag `prototype-biomass` steht auf `main`
(`48d573c`) — der Stand des Prototyp-Frontends ist damit dauerhaft erreichbar,
dieser Plan darf im Arbeitsbaum löschen. **M2-04 ist gemergt** (`#39`): `asset_hosts`,
Kachel- und Statistikrouten, `earthx:default_render` und `earthx:viewer` liegen auf
`main`.

---

## 1. Ziel in einem Satz

Der Viewer sucht Sentinel-2-Szenen über `/stac` von `earthx`, zeigt ihre
Quicklooks direkt vom Asset-Host als Overlays, führt sie über die Zeitleiste
als Zeitschritte vor — und ruft dabei keine Route des Prototyps mehr auf.

## 2. Ausgangslage (gemessen am Code, Stand `main` nach `#39`)

**Frontend.** `frontend/src/api.ts` ist der einzige Ort mit Prototyp-Aufrufen:
neun `fetch` auf `/api/config`, `/api/search`, `/api/download`, `/api/decompose`,
`/api/stitch`, `/api/coverage`, `/api/geocode`, `/api/asset`, `/api/tiles`
(`api.ts:32–124`). `vite.config.ts:14` leitet `/api` auf `localhost:8000`.
`products.ts` ist reines BIOMASS-Wissen (fünf Produkte mit Collection-Namen,
Regex auf der Item-ID, Bandzuordnung der Polarisationen, Dekompositionen).
`grouping.ts` gruppiert über `Produkttyp | Datum | Orbitrichtung | Track`, mit
`typeRank` für BIOMASS-Produkttypen und Track aus `/_T(\d{3})_F\d{3}_/`.
`store.ts` (545 Zeilen) hält Karten-, UI- und Serverzustand zusammen.
`index.html:7` und `ControlPanel.tsx:118` tragen den Namen „BIOMASS VIEWER".

**Backend.** `earthx.api` liefert seit M1-07 eine STAC-API unter `/stac`
(`api/main.py:37`): Landing Page, `/conformance`, `/collections`,
`/collections/{id}`, `/collections/{id}/items`, `/collections/{id}/items/{item_id}`,
`GET`/`POST` `/search`. Erlaubte Extensions sind fest auf `query`, `fields`,
`pagination` gesetzt — **kein `sort`, kein `filter`/CQL2** (`api/main.py:36`).
Suchparameter: `collections`, `bbox`, `datetime`, `limit` (1–100, Vorgabe 10),
`token`. Rückwärts blättern ist abgelehnt (`federating_client.py:84`), eine Suche
über zwei Quellen ergibt `400` (`federating_client.py:281`, D8). Die Antwort trägt
`numberMatched`, `numberReturned` und einen `next`-Link mit eigener Seitenmarke.

Seit M2-04 (`#39`) gibt es außerdem Kacheln und Statistik unter
`/collections/{dataset}/items/{item}/…` mit `?asset=` als Pflichtparameter. **07a
benutzt sie nicht** — sie sind die Aufgabe von 07b. **Coverage und Download fehlen
weiter** (M2-05, M2-06; 07c und 07d holen sie ins Frontend). Eine Ortssuche gibt es
in `earthx` nicht und soll es in M2 auch nicht geben (F1 = a).

**Registry → Frontend.** Eine eigene Datensatz-Route gibt es nicht und braucht es
nicht: `catalog/collection.py:93–154` bildet jeden Registry-Eintrag auf eine STAC
Collection mit den acht `earthx:`-Feldern aus `architekturplan.md` 5.1 ab.
`GET /stac/collections` ist damit die Datensatzliste des Viewers. Seit `#39` steht
dort als neunte Zeile `earthx:viewer` mit dem Gruppierungsschlüssel — genau das,
was 07a zusätzlich braucht (§5). `earthx:access.cors` steht für Sentinel-2 jetzt
auf `true` statt auf `null`, gemessen in `adr/0006` §3.6; das ist die Bedingung,
unter der der Quicklook ohne Proxy auskommt (§4.4).

### 2.1 Eigene Messung an der Quelle (20.09.2026)

Ein einzelner anonymer `GET` auf
`…/v1/collections/sentinel-2-c1-l2a/items?limit=1`, um die Feldnamen zu belegen,
statt sie zu raten (Item `S2B_T29QLG_20260920T112238_L2A`):

| Was | Wert |
|---|---|
| Zeitbezug | `datetime` (`2026-09-20T11:34:36.739000Z`) |
| Kachel | `grid:code` = `MGRS-29QLG`; dazu `mgrs:utm_zone`, `mgrs:latitude_band`, `mgrs:grid_square` |
| Aufnahme (Überflug) | `s2:datatake_id` = `GS2B_20260920T112109_049827_N05.12` |
| Relativer Orbit | **kein eigenes Feld**; nur im `s2:product_uri` als `R037` |
| Wolken | `eo:cloud_cover` = 0,16 |
| Quicklook | Asset `thumbnail`, `image/jpeg`, Rolle `thumbnail`, `L2A_PVI.jpg` |
| Asset-Host | `e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com` (deckt `adr/0006` §3.7) |
| Nodata | `s2:nodata_pixel_percentage` = 93,7 % bei diesem Item |

Die letzte Zeile ist der Grund, warum das Nodata-Keying aus F6 des Inventars
für Sentinel-2 gebraucht wird: Ein PVI-Quicklook kann fast ganz aus schwarzem
Rand bestehen und würde die Karte sonst zudecken. `stac_version` der Items ist
`1.0.0` — die Normalisierung aus D18 betrifft nur den zweiten Datensatz.

## 3. Abgrenzung

**In 07a:** API-Client gegen `/stac`; Datensatzauswahl aus `/stac/collections`;
AOI-Auswahl, Upload und „letzte AOI" unverändert im Client (F1, F3);
Suche je Datensatz mit eigener Seitenmarke (F4, D8); generische Gruppierung zu
Zeitschritten (F5); Quicklook-Overlays direkt vom Asset-Host ohne Proxy (F6, D14);
Zeitleiste mit Abspielen (F7); Ablauf anklicken → auswählen (F8); Datums-Fallback
mit sichtbarem Hinweis; Ortssuche ausgebaut (F1 = a); Vitest eingerichtet und im
CI-Job `frontend`; Umbenennung des Viewers.

**Nicht in 07a:** Kacheln, Darstellungssteuerung, Layer-Manager-Ausbau (07b);
Coverage-Heatmap und Zeit-Histogramm (07c); Download (07d); Theme-Umschalter (V-1);
zweiter Datensatz (M2-10); das gesamte Backend, `earthx:viewer` eingeschlossen (§5);
`backend/app/` (der Prototyp bleibt bis M2-11 lauffähig); Oberflächentests (F2 = a:
nur reine Logik).

## 4. Der Umbau, Datei für Datei

### 4.1 `src/api.ts` → schmaler `earthx`-Client

Ersetzt vollständig. Neue Form, ohne `/api`:

```ts
const BASE = import.meta.env.VITE_API_BASE ?? '';   // same-origin, Vite proxied /stac

export async function fetchCollections(): Promise<Collection[]>          // GET /stac/collections
export async function searchItems(q: SearchQuery): Promise<ItemPage>     // GET /stac/search
```

- `SearchQuery` = `{ collection, bbox, datetime?, limit?, token? }`. **Ein**
  Datensatz je Suche — D8 verlangt es, und `federating_client.py:281` erzwingt es
  mit `400`.
- `ItemPage` = `{ features, numberMatched, nextToken }`. `nextToken` wird aus
  `links[rel=next]` gezogen (Parameter `token` der `href`), nicht aus einem
  geratenen Format; fehlt der Link, ist die Seite die letzte.
- AOI → `bbox`: Gesucht wird mit der Bounding-Box der AOI, wie im Prototyp
  (`prototyp-inventar.md` F4). `intersects` gibt es in der GET-Suche nicht, und
  der Zuschnitt auf das Polygon passiert ohnehin erst beim Download (M2-06).
- Fehler: `jsonOrThrow` bleibt, ergänzt um die STAC-Fehlerform
  (`{code, description}`) neben FastAPIs `{detail}`.
- **Kein** `assetUrl` mehr. Quicklook-Adressen kommen aus dem Item selbst (§4.4).

### 4.2 `src/products.ts` → `src/datasets.ts`

`products.ts` wird gelöscht (BIOMASS-Produktmodell, Polarisationen,
Dekompositionen — D7). An seine Stelle tritt `datasets.ts`: Typen für die
Collection samt der `earthx:`-Felder und zwei reine Funktionen —
`datasetsFrom(collections)` (Auswahlliste für die Oberfläche) und
`groupByOf(collection)`, das `earthx:viewer.group_by` liest. Fehlt es, liefert
`groupByOf` keinen Ersatz, sondern kennzeichnet den Datensatz als nicht anzeigbar
(§5).

### 4.3 `src/grouping.ts` → generisch

Der Schlüssel kommt aus dem Datensatzeintrag statt aus Regex auf der Item-ID, und
er wird genauso gebaut wie im Backend (§5):

```
key = groupKey(item, collection['earthx:viewer'].group_by)
```

Für Sentinel-2 ist `group_by` gleich `["datetime", "grid:code"]`, der Schlüssel
also `("2026-07-24", "MGRS-32TMS")` — **ein Aufnahmetag je MGRS-Kachel**. Ein
Zeitschritt führt damit auf genau ein Item und später auf genau eine Kachel-URL;
nach D11 gibt es in M2 kein Mosaik im Kachel-Pfad, und ein Datatake umfasst viele
Kacheln. Dass eine Gruppe in der Regel genau ein Item hat, ist kein Sonderfall:
Sie bleibt eine Menge, und ein anderer Datensatz darf mehrere hineinlegen.

`typeRank`, `trackOf`, `productTypeOf`, `isGnItem` und die BIOMASS-Etiketten
entfallen. Die Sortierung bleibt „neuestes Datum zuerst", danach stabil nach
Schlüssel. Das Etikett eines Zeitschritts sind die Schlüsselteile in ihrer
Reihenfolge — bei Sentinel-2 Datum und MGRS-Kachel. `s2:datatake_id` wird **nicht**
angezeigt: `ViewerInfo` trägt dafür kein Feld, und es ohne Feld anzuzeigen wäre
datensatzspezifischer Code im Frontend (§5).

Die Fehler sind dieselben wie im Backend, nicht stillschweigend übersprungen:
`groupKey` wirft `MissingProperty`, wenn ein Item eine Eigenschaft des Schlüssels
nicht trägt. `buildGroups` reicht den Fehler durch, der Store macht daraus eine
Meldung mit Item-Kennung und Eigenschaftsnamen und zeigt **keine** Gruppen — ein
Schlüssel, der still einen Teil verliert, würde zwei Zeitschritte zu einem
verschmelzen.

### 4.4 `src/mapLayers.ts` — Quicklooks ohne Proxy

Nur der Beschaffungsweg ändert sich; `keyBlackToTransparent`, `loadTransparent`,
`placeImage`, der Generationszähler `syncGen` und die Obergrenze von 40 Overlays
bleiben wie sie sind. Die URL ist künftig `item.assets[<quicklook>].href`,
gewählt generisch: Asset mit Rolle `thumbnail`, sonst `overview`, sonst das erste
Asset mit `image/*`-Typ. **`img.crossOrigin = 'anonymous'` ist ab jetzt die tragende Zeile** und darf beim
Umbau nicht verlorengehen: Ohne sie sperrt der Browser das Canvas, sobald das Bild
nicht mehr same-origin über den Proxy kommt, und `getImageData` wirft — das Keying
fiele still aus. Die Zeile steht bereits (`mapLayers.ts:71`), der Asset-Host sendet
`Access-Control-Allow-Origin: *` (`adr/0006` §3.6, gemessen; seit `#39` steht das
auch als `earthx:access.cors = true` an der Collection), damit trägt der Weg.
Ein Test kann das nicht zeigen (F2 = a: keine Oberflächentests), deshalb steht es
als Punkt in der Vorführung (§9) und als Kommentar an der Zeile. Der
BIOMASS-Sonderfall `rotate180` für `S[123]_SCS|DGM` in `geoUtils.ts:104` entfällt;
die Ecken kommen weiter aus `footprintCorners`. Der Schwellwert für „schwarz ist
Nodata" **bleibt die benannte Konstante 16** des Prototyps: `ViewerInfo` trägt in M2
nur `group_by`, ein Feld dafür gibt es nicht. Inventar F6 will ihn am Datensatz —
das steht als offene Zeile im Entscheidungslog und wird entschieden, sobald ein
Datensatz eine andere Schwelle braucht (§5).

### 4.5 `src/store.ts` — Datensatz statt Produkt

- `product: Product` → `datasetId: string`; `PRODUCTS` → die geladenen
  Collections; `loadConfig` → `loadDatasets` (`GET /stac/collections`, wählt die
  erste Collection vor). Die Token-Meldung entfällt ersatzlos (D7).
- `runSearch` sucht je Datensatz, blättert mit `nextToken` bis höchstens
  **300 Items** (der Richtwert des Prototyps, `max_search_items`) oder bis kein
  `next`-Link mehr kommt, und meldet über `numberMatched`, wenn mehr da wäre.
  `limit=100` je Seite (die Obergrenze der API).
- Der Nachfilter über `ProductDef.match` entfällt: Die Collection **ist** der
  Filter.
- **Datums-Fallback** (§12 Antwort 5): Bleibt die Suche im gewählten Zeitraum leer,
  sucht der Store in bis zu drei Stufen mit erweitertem Fenster (±7, ±30, ±90 Tage
  um den Zeitraum) und nimmt aus der ersten Stufe mit Treffern das Item mit dem
  kleinsten zeitlichen Abstand zum gewählten Zeitraum. Details in §4.5.1.
- `runDownload`, `runDecompose`, `loadCoverage`, `applyRender`, `setPolMode`,
  `setPolBand`, `setDecompMethod`, `focusMode` und die Felder für Streckbereich
  und Colormap entfallen hier und kommen mit 07b/07c/07d zurück (§12 Antwort 3).
- `addCurrentToLayers` bleibt, aber nur mit Quicklook-Overlays; der
  `restore`-Block verliert `downloaded` und `appliedRender`.

#### 4.5.1 Datums-Fallback: `limit` und Seitenmarke im Fenster

Weil `sort` in `earthx` abgeschaltet ist (`api/main.py:36`) und die Reihenfolge
der Quelle nirgends zugesichert ist, darf „das nächstgelegene Item" nicht aus der
Position in der Antwort abgeleitet werden — es muss aus dem Zeitstempel jedes
zurückgegebenen Items berechnet werden. Damit das mit einem Fenster funktioniert,
das mehr als eine Seite trifft, ist der Fallback in **zwei Schritte** geteilt:

1. **Sonde je Stufe — genau eine Seite, `limit=100`, ohne Seitenmarke.** Die Sonde
   sucht nicht den vollständigen Bestand des Fensters, sondern nur ein Datum. Aus
   den zurückgegebenen Items wird das mit dem kleinsten Abstand zum gewählten
   Zeitraum genommen; bei Gleichstand das ältere (deterministisch, im Test
   festgehalten). Leer ⇒ nächste Stufe. Alle drei Stufen leer ⇒ kein Fallback,
   Meldung „Kein Treffer im gewählten Zeitraum und auch nicht ±90 Tage daneben".
2. **Vollständige Suche für das gefundene Datum.** Mit dem Datum als Zeitraum
   (`T00:00:00Z/T23:59:59Z`) läuft die **normale** Suche aus §4.5, mit Blättern
   über die Seitenmarke bis 300 Items. Was der Viewer am Ende anzeigt, ist also
   vollständig, nicht das Stichprobenergebnis der Sonde.

**Ehrlich bleibt es dadurch:** Trifft eine Sonde mehr, als eine Seite fasst
(`numberMatched > numberReturned`), dann ist „das nächstgelegene Datum" nicht
bewiesen, sondern das nächstgelegene **gefundene**. Genau so steht es dann auch
im Hinweis (Prinzip 9, „Ehrlichkeit in der Anzeige"):

| Fall | Hinweis |
|---|---|
| Sonde vollständig gesehen | „Kein Treffer im gewählten Zeitraum — nächstgelegene Aufnahme: TT.MM.JJJJ" |
| Sonde gekappt | „Kein Treffer im gewählten Zeitraum — nächstgelegene **gefundene** Aufnahme: TT.MM.JJJJ (Stichprobe aus n von m Treffern ±k Tagen)" |

Der gekappte Fall ist bei der kleinsten Stufe (±7 Tage, AOI-Bounding-Box) selten,
aber er ist möglich und wird deshalb nicht weggerundet. Höchstens drei zusätzliche
Anfragen für die Sonden, dann die normale Suche.

### 4.6 Oberfläche

| Datei | Änderung |
|---|---|
| `components/SearchBox.tsx` | **gelöscht** — Ortssuche ist in M2 ausgeblendet (F1 = a, kommt mit M3) |
| `components/ControlPanel.tsx` | `ProductSelector` → `DatasetSelector` (aus `/stac/collections`); `CoverageToggle` raus (kommt mit 07c); `SearchBox` raus; Marke „EarthX" |
| `components/ResultsPanel.tsx` | Quicklook direkt aus dem Item; `cog_key`/`quicklook_key` und die Abzeichen `PREVIEW`/`HI-RES` raus; Auswahl bleibt (F8) |
| `components/TimeSlider.tsx` | unverändert bis auf die Etiketten aus der neuen Gruppierung (F7) |
| `components/ViewerControls.tsx`, `components/DownloadBar.tsx` | **gelöscht** (Polarisation, Dekomposition, Download — 07b/07d bauen neu) |
| `components/LayerManager.tsx`, `layers.ts` | nur der `restore`-Block wird schmaler |
| `App.tsx` | `focusMode`-Zweig und `DownloadBar` raus |
| `types.ts` | `BiomassItem` → `StacItem` (ohne `quicklook_key`/`cog_key`), `AppConfig`, `TokenStatus`, `GeocodeResult`, `DownloadResponse`, `DownloadResult`, `DownloadedInfo` raus; `MosaicGroup` → `TimeStepGroup` |
| `index.html`, `frontend/README.md` | Titel und README auf EarthX; die README ist heute noch die Vite-Vorlage |
| `vite.config.ts` | Proxy `/api` → `/stac` auf denselben Zielhost; `VITE_API_PROXY` bleibt der Schalter |

Das HUD-Design bleibt unangetastet: `index.css`, `App.css`, `Draggable`,
`Toolbar`, `StatusBar`, `MapView`, die Farbtoken und die Bedienmuster aus
Inventar Teil 3 werden nicht angefasst.

## 5. `earthx:viewer` — was auf `main` liegt

Das Feld ist da: M2-04 hat es mit #39 gebaut, M2-07a **liest es nur**. Dieser
Abschnitt beschreibt den vorhandenen Stand, er bestellt nichts mehr.

**`ViewerInfo` in `backend/earthx/catalog/registry.py:234`** trägt in M2 genau
einen Wert:

```python
group_by: tuple[str, ...]   # Item-Eigenschaften in Schlüsselreihenfolge
```

`properties.` ist impliziert und darf nicht geschrieben werden; ohne Eintrag
wirft das Feld beim Laden der Registry (kein Vorgabewert, B10). Für
`sentinel-2-c1-l2a` steht dort `("datetime", "grid:code")`
(`catalog/datasets.py:186`) — **Aufnahmetag je MGRS-Kachel**. In der Collection
erscheint es als `"earthx:viewer": {"group_by": ["datetime", "grid:code"]}`
(`catalog/collection.py:159`), als neunte Zeile von `architekturplan.md` 5.1.

**Die eine Regel, die zum Feld gehört** (Feldbeschreibung und 5.1, wörtlich):

> Eine Eigenschaft, die einen STAC-Zeitpunkt hält, geht als ihr **UTC-Datum** in
> den Schlüssel ein.

Denn eine Zeitleiste gruppiert einen Aufnahmetag, keine Sekunde — und zwar den
Tag in UTC, damit derselbe Moment nicht je nach Schreibweise der Quelle in zwei
Schritte fällt. `earthx.catalog.registry.group_key` (`registry.py:286`) ist die
**Referenzumsetzung** dieser Regel, `backend/tests/catalog/test_group_key.py`
hält sie mit 12 Fällen fest.

**Was das Frontend daraus macht:** `groupKey(item, groupBy)` in `grouping.ts`
spiegelt `group_key` Teil für Teil —

| `group_key` (Python) | `groupKey` (TypeScript) |
|---|---|
| Zeitpunkt ⇒ UTC-Datum `YYYY-MM-DD` | `new Date(v).toISOString().slice(0, 10)` nach geprüftem Parsen |
| alles andere ⇒ sein eigener Text | Zeichenkette unverändert, Zahl über `String(v)` |
| Reihenfolge wie in der Registry | dieselbe |
| `MissingProperty`, nie stillschweigend übersprungen | eigener Fehlertyp `MissingProperty`, nie stillschweigend übersprungen |

**Wo TypeScript anders ausgehen könnte als Python.** `Date.parse` nimmt mehr an
als `datetime.fromisoformat`. `"MGRS-32TMS"` ist für beide kein Zeitpunkt, aber
eine Zahl wie `137` wäre für `new Date(137)` einer. Deshalb hält das Frontend
dieselbe Reihenfolge wie `_key_part` im Backend: **nur Zeichenketten** werden
überhaupt auf einen Zeitpunkt geprüft, Zahlen gehen direkt über `String(v)`.
Geprüft wird auf das ISO-Muster mit Zeitanteil; ein bloßes Datum wie `2026-07-24`
läuft dadurch über den Textweg statt über den Zeitweg — **mit demselben
Ergebnis**, weil das Backend es zum selben Datum auflöst. Beide Fälle stehen als
eigene Vitest-Fälle (§6.1, Fall 7 und 8).

**Keine Vorgabewerte (Otto, 20.09.2026).** Fehlt `earthx:viewer` oder sein
`group_by`, **baut das Frontend keinen Ersatzschlüssel**. Das ist ein Fehler des
Datensatzes, und der Viewer sagt ihn: der Datensatz erscheint in der Auswahl als
nicht anzeigbar, mit der Meldung, welches Feld fehlt. Ebenso bei einem Item ohne
die verlangte Eigenschaft — der Fehler nennt Item-Kennung und Eigenschaft, und
es werden **keine** Gruppen gezeigt, statt falsche zu zeigen.

**Was `ViewerInfo` bewusst nicht trägt.** Das Feld ist auf `group_by` beschränkt
(seine eigene Beschreibung: „stays that narrow until something else is actually
needed"). Zwei Folgen für 07a:

- **`s2:datatake_id` wird in M2 nicht angezeigt.** Der Vorschlag aus der ersten
  Planfassung (`display_properties`) ist damit überholt; das Etikett eines
  Zeitschritts ist Datum und MGRS-Kachel. Eine Anzeige des Datatakes wäre ohne
  Feld datensatzspezifischer Code im Frontend und fiele unter dieselbe Regel.
- **Die Nodata-Schwelle des Quicklook-Keyings hat kein Feld.** Inventar F6 will
  sie am Datensatz; bis es eines gibt, bleibt sie die benannte Konstante 16 des
  Prototyps, und das Quicklook-Asset wird generisch über die Rolle gewählt
  (§4.4). Als offene Zeile im Entscheidungslog festgehalten, zu entscheiden,
  sobald ein Datensatz eine andere Schwelle braucht.

## 6. Tests (Vitest, F2 = a)

Eingerichtet wird `vitest` als einzige neue Entwicklungsabhängigkeit, ohne
DOM-Umgebung: geprüft wird **nur reine Logik**, keine Oberfläche. Konfiguration
im vorhandenen `vite.config.ts` (`test: { include: ['src/**/*.test.ts'] }`),
Skript `"test": "vitest run"`, Import der Prüf-Funktionen aus `vitest` statt
über globale Namen, damit keine `types`-Zeile in `tsconfig.app.json` nötig wird.

| Datei | Fälle |
|---|---|
| `api.test.ts` | URL-Bau der Suche (bbox-Reihenfolge, `datetime`-Bereich, `limit`, `token`); Seitenmarke aus dem `next`-Link gezogen; **kein** `next`-Link ⇒ `nextToken === null`; Fehlerkörper in beiden Formen (`detail`, `{code, description}`); `400` der Mehrquellensuche kommt als lesbare Meldung an |
| `grouping.test.ts` | **Die 12 Fälle aus `backend/tests/catalog/test_group_key.py`, eins zu eins gespiegelt** (Tabelle unten); dazu die Gruppenbildung selbst: Sortierung neuestes zuerst, leere Eingabe ⇒ leere Liste, `MissingProperty` kommt aus `buildGroups` heraus statt ein Item zu verschlucken |
| `dateFallback.test.ts` | Fensterfolge ±7/±30/±90; Auswahl des zeitlich nächsten Items bei Treffern auf beiden Seiten; Gleichstand ⇒ das ältere; alle drei Stufen leer ⇒ kein Fallback, klare Meldung; kaputtes `datetime` wird übersprungen; **gekappte Sonde** (`numberMatched > numberReturned`) ⇒ der Hinweis sagt „gefundene" und nennt die Zahlen (§4.5.1) |
| `datasets.test.ts` | **`earthx:viewer` fehlt oder `group_by` ist leer ⇒ der Datensatz ist nicht anzeigbar, kein Ersatzschlüssel** (Otto, 20.09.2026); die Meldung nennt das fehlende Feld; die übrigen Datensätze der Liste bleiben wählbar; Quicklook-Asset: Rolle `thumbnail` vor `overview` vor `image/*`, keines vorhanden ⇒ `null` |

### 6.1 Die 12 Fälle aus `test_group_key.py`, gespiegelt

Otto hat sie am 20.09.2026 ausdrücklich verlangt, damit `group_key` und die
Frontend-Umsetzung nicht auseinanderlaufen. Gleiche Reihenfolge, gleiche Werte,
gleiche Benennung der Absicht — wer eine Seite ändert, sieht die andere fallen.

| # | Fall (Python-Name) | Erwartung im Frontend |
|---|---|---|
| 1 | `the_time_of_day_drops_out_of_the_key` | `2026-07-24T10:38:17.453000Z` ⇒ `["2026-07-24"]` |
| 2 | `two_scenes_of_the_same_day_land_in_one_group` | `10:38:17Z` und `22:01:03Z`, gleiche Kachel ⇒ derselbe Schlüssel |
| 3 | `the_date_is_the_one_in_utc_not_the_local_one` | `2026-07-24T23:30:00Z` und `2026-07-25T01:30:00+02:00` ⇒ beide `["2026-07-24", "MGRS-32TMS"]` |
| 4 | `a_second_across_midnight_is_another_day` | `23:59:59Z` ⇒ `2026-07-24`, `00:00:00Z` ⇒ `2026-07-25` |
| 5 | `an_instant_that_is_already_a_datetime_is_read_the_same_way` | ein bereits geparstes `Date` ergibt denselben Schlüssel wie die Zeichenkette |
| 6 | `a_grid_code_is_carried_over_unchanged` | `MGRS-32TMS` ⇒ `["MGRS-32TMS"]` |
| 7 | `a_bare_date_stays_the_date_it_is` | `2026-07-24` ⇒ `["2026-07-24"]` |
| 8 | `a_number_becomes_its_text_rather_than_a_type_error` | `137` ⇒ `["137"]`, **nicht** als Zeitpunkt gelesen |
| 9 | `the_parts_keep_the_order_the_registry_names` | `["datetime","grid:code"]` und `["grid:code","datetime"]` ergeben die zwei Reihenfolgen |
| 10 | `a_property_the_item_does_not_carry` | `MissingProperty`, die Meldung nennt `grid:code` |
| 11 | `an_item_without_properties_at_all` | `MissingProperty` |
| 12 | `the_key_of_the_registered_dataset_is_the_acquisition_day_per_tile` | mit `group_by` aus der Collection: `["2026-07-24", "MGRS-32TMS"]` |

Fall 5 und Fall 8 sind die beiden, an denen TypeScript anders ausgehen kann als
Python: `Date.parse` nimmt mehr an als `datetime.fromisoformat`. Deshalb prüft
das Frontend nur Zeichenketten auf einen Zeitpunkt, und nur solche mit Zeitanteil
(§5); Fall 7 hält fest, dass ein bloßes Datum als Text durchgeht, und Fall 8, dass
eine Zahl keine Zeit wird.

Damit sind die Fälle aus `CLAUDE.md` abgedeckt: Fehlerfälle (Upstream-Fehler,
`400`), fehlerhafte Eingaben (kaputtes `datetime`, fehlende Properties) und
zweckfremde Nutzung (Suche über zwei Datensätze, Rückwärts-Seitenmarke).
Externe Antworten kommen als handgeschriebene Fixtures im Test, nie live.

**CI.** In `.github/workflows/ci.yml`, Job `frontend`, ein Schritt nach der
Typprüfung: `- name: Tests (vitest)` / `run: npm test`. Der Jobname wird zu
„Frontend — lint, types and tests". Das ist die eine ausdrücklich erlaubte
Änderung an `.github/` (F2 = a, Log-Zeile vom 20.09.2026).

## 7. Reihenfolge der Commits

1. `chore(frontend): set up vitest and add it to the CI frontend job`
2. `feat(frontend): talk to the earthx STAC API instead of the prototype` (api.ts, vite.config.ts, types.ts)
3. `feat(frontend): pick the dataset from /stac/collections` (datasets.ts, ControlPanel, store)
4. `feat(frontend): group items into time steps from the registry key` (grouping.ts + Test)
5. `feat(frontend): load quicklooks straight from the asset host` (mapLayers.ts, geoUtils.ts, ResultsPanel)
6. `feat(frontend): fall back to the nearest date and say so` (store + Test)
7. `refactor(frontend): drop the BIOMASS-only paths until 07b–07d rebuild them` (Löschungen)
8. `docs: record M2-07a in the decision log`

Das Backend kommt in keinem Commit vor: `earthx:viewer` legt M2-04 an (§5).

## 8. Umfang

Geschätzt rund 300 neue und geänderte Zeilen plus rund 400 gelöschte
(`products.ts` 121, `ViewerControls.tsx` 189, `DownloadBar.tsx` 66,
`SearchBox.tsx` 92, dazu Teile von `store.ts`). Der Richtwert von 400 Zeilen
(`CLAUDE.md`) ist damit überschritten, überwiegend durch Löschungen — von Otto
am 20.09.2026 so entschieden (§12 Antwort 3).

## 9. Abnahme

- `npm run lint`, `npx tsc -b --pretty false` und `npm test` grün. Das Backend wird
  nicht angefasst, `ruff` und `pytest` laufen trotzdem einmal als Gegenprobe.
- `grep -rn "/api/" frontend/src` findet nichts mehr (M2-Abnahmekriterium 7).
- Lokal vorführbar mit `docker compose up` und `npm run dev`: Datensatz wählen,
  AOI zeichnen oder hochladen, suchen, Quicklooks auf der Karte, Zeitleiste
  abspielen, Szene anklicken und auswählen; ein Zeitraum ohne Treffer zeigt den
  Datums-Hinweis. Die Anleitung steht im PR.
- **Ausdrücklich vorgeführt, weil kein Test es abdeckt:** Ein Quicklook auf der
  Karte zeigt den Nodata-Rand durchsichtig, nicht schwarz — das ist der Beleg,
  dass das Canvas-Keying über die Herkunftsgrenze hinweg trägt (§4.4).
- Der Viewer zeigt zwischen 07a und 07b keine vollaufgelösten Bilder mehr, nur
  Quicklooks; das steht so im PR (§13).
- Eine Suche, die zwei Datensätze umfasst, ist in der Oberfläche gar nicht
  erst auslösbar; der `400` der API ist trotzdem als Meldung geprüft.

## 10. Was diese Aufgabe nicht anfasst

`backend/app/` (Prototyp bis M2-11), `docker-compose.yml`, `.importlinter`,
`index.css`/`App.css` und das HUD-Design, `MapView.tsx`, die Zeichenwerkzeuge,
`aoiFile.ts`, **das gesamte Backend** (`earthx:viewer` legt M2-04 an, §5),
`CODEOWNERS`, `.claude/`. An `.github/workflows/ci.yml` nur der Vitest-Schritt.

## 11. Risiken

| Risiko | Umgang |
|---|---|
| Form des `next`-Links weicht von der Erwartung ab | Der Client liest den Parameter aus der `href` statt ein Format anzunehmen; Test deckt „kein Link" ab; im Umsetzungsschritt einmal gegen die laufende API geprüft |
| 300 Items in bis zu drei Seiten sind für eine große AOI zu wenig | `numberMatched` wird angezeigt, der Hinweis rät zur Eingrenzung; echtes Nachladen gehört zu 07c (Coverage entscheidet über die Last) |
| Nodata-Keying entfernt dunkles Wasser | Schwelle am Datensatz statt im Code (§5); für Sentinel-2 bleibt es bei 16 wie im Prototyp, nachjustierbar ohne Codeänderung |
| Der Viewer kann nach 07a vorübergehend weniger als der Prototyp | Beabsichtigt (Strangler); der Stand des Prototyps hängt am Tag `prototype-biomass`; 07b–07d bauen Kacheln, Coverage und Download neu. Im PR ausdrücklich vermerkt (§13) |
| `earthx:viewer` wird für den zweiten Datensatz zu eng | Das Feld ist bewusst schmal und wird erweitert, wenn M2-09b/M2-10 etwas braucht; das Frontend erfindet dafür nichts, sondern meldet, was fehlt (§5) |
| `group_key` und die Frontend-Umsetzung laufen auseinander | Die 12 Fälle aus `test_group_key.py` stehen gespiegelt als Vitest-Fälle (§6.1); wer eine Seite ändert, sieht die andere fallen |
| Ein Zeitschritt mit genau einem Item wirkt wie eine überflüssige Ebene | Die Gruppe bleibt eine Menge; der zweite Datensatz (M2-10) darf mehrere Items hineinlegen, ohne dass sich etwas ändert |

## 12. Antworten von Otto (20.09.2026)

| # | Frage | Antwort | Folge im Plan |
|---|---|---|---|
| 1 | Gruppierungsschlüssel für Sentinel-2 | **(b) Datum + `grid:code`.** Begründung: Nach D11 gibt es in M2 kein Mosaik im Kachel-Pfad, eine Gruppe muss also auf genau ein Item und damit eine Kachel-URL führen; ein Datatake umfasst viele Kacheln. `s2:datatake_id` sollte als angezeigte Eigenschaft erhalten bleiben — **überholt durch `#39`:** `ViewerInfo` trägt nur `group_by`, der Datatake wird in M2 nicht geführt | §4.3, §5 |
| 2 | Wo steht der Schlüssel | **(a) Neues Feld `earthx:viewer`**, neunte Zeile in `architekturplan.md` 5.1 — freigegeben und **in M2-04 gebaut** (`#39`). M2-07a liest es nur | §5 beschreibt den Stand; §7 ohne Backend-Commit |
| 3 | Zuschnitt des PR | **(a) Ein PR mit dem Abbau.** Im PR ausdrücklich vermerken, dass der Viewer auf `main` zwischen 07a und 07b keine Bilder zeigt | §8, §9, §13 |
| 4 | TypeScript-Client | **(a) Handgeschrieben in M2;** die Generierung aus dem OpenAPI-Schema wird eine eigene Aufgabe nach M2-06 | §4.1 unverändert; eigene Log-Zeile |
| 5 | Datums-Fallback | **(a) ±7/±30/±90 Tage, zeitlich nächstes Item, sichtbarer Hinweis.** Da die Quelle nicht sortiert, muss das Fenster innerhalb einer Suche auswertbar bleiben; `limit` und Seitenmarke sind im Plan zu benennen | **§4.5.1** neu |
| 6 | Serverzustand | **(a) Bei `zustand` bleiben** | §4.5 unverändert, keine neue Abhängigkeit |

Dazu ein Hinweis für die Umsetzung, der in §4.4 eingearbeitet ist: Die Quicklooks
kommen direkt vom Asset-Host (D14); für das Canvas-Keying aus Inventar F6 muss das
Bild mit `crossOrigin="anonymous"` geladen werden, sonst ist das Canvas gesperrt.
Der Host sendet laut `adr/0006` `Access-Control-Allow-Origin: *`.

## 13. Stand der Umsetzung

**Der Plan ist fertig.** Die Abhängigkeit aus Antwort 2 ist erfüllt: M2-04 ist mit
`#39` gemergt, `earthx:viewer` mit `group_by = ["datetime", "grid:code"]` liegt auf
`main`, und §5 beschreibt seitdem den vorhandenen Stand statt einer Bestellung.
Vorgezogen wurde 07a nicht (Otto, 20.09.2026).

**Die Umsetzung startet als eigene Sitzung.** Sie beginnt mit `main` im Branch,
arbeitet die Commits aus §7 ab und meldet sich mit einem eigenen Draft-PR.

**Was der Umsetzungs-PR beim Fertigmelden ausdrücklich sagen muss** (Antwort 3):
Zwischen dem Merge von 07a und dem von 07b zeigt der Viewer auf `main` **keine
vollaufgelösten Bilder** — Kacheln, Darstellungssteuerung, Coverage und Download
sind ausgebaut und kommen mit 07b bis 07d zurück. Sichtbar bleiben in dieser Zeit
die Quicklook-Overlays und die Footprints.
