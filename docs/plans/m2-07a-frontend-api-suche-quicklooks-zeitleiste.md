# M2-07a — Frontend: API-Client, Suche, Quicklooks, Zeitleiste: Umsetzungsplan

**Status:** **Plan von Otto angenommen am 20.09.2026, alle sechs Fragen beantwortet**
(§12). **Stufe B** laut `projektplan.md` 1.2: Plan zuerst als Draft-PR, Umsetzung
nach dem OK. Aus Antwort 2 folgt eine **neue Abhängigkeit: M2-07a hängt jetzt an
M2-04**, weil das Feld `earthx:viewer` dort angelegt wird (§5). M2-04 ist noch
nicht umgesetzt; der Stand der Umsetzung steht in §13.
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
**Voraussetzungen:** Der Tag `prototype-biomass` steht auf `main` (`48d573c`, am
20.09.2026 von Otto gesetzt) — der Stand des Prototyp-Frontends ist damit dauerhaft
erreichbar, dieser Plan darf im Arbeitsbaum löschen. **Offen: M2-04**, das
`earthx:viewer` anlegt (§5, §12 Antwort 2).

---

## 1. Ziel in einem Satz

Der Viewer sucht Sentinel-2-Szenen über `/stac` von `earthx`, zeigt ihre
Quicklooks direkt vom Asset-Host als Overlays, führt sie über die Zeitleiste
als Zeitschritte vor — und ruft dabei keine Route des Prototyps mehr auf.

## 2. Ausgangslage (gemessen am Code, Stand `48d573c`)

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

**Was das Frontend heute nicht bekommt:** Kacheln, Statistik, Coverage und
Download gibt es in `earthx` noch nicht — `access`, `jobs`, `discovery` sind
`/health`-Stubs. Sie kommen mit M2-04, M2-05, M2-06 und landen im Frontend mit
M2-07b bis M2-07d. Eine Ortssuche gibt es in `earthx` nicht und soll es in M2
auch nicht geben (F1 = a).

**Registry → Frontend.** Eine eigene Datensatz-Route gibt es nicht und braucht es
nicht: `catalog/collection.py:93–154` bildet jeden Registry-Eintrag auf eine STAC
Collection mit den acht `earthx:`-Feldern aus `architekturplan.md` 5.1 ab.
`GET /stac/collections` ist damit die Datensatzliste des Viewers. Was 07a dort
zusätzlich braucht — Gruppierungsschlüssel und Quicklook-Angaben — kommt als
neuntes Feld `earthx:viewer` hinzu, angelegt von M2-04 (§5).

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
`viewerConfigOf(collection)` (Gruppierung und Quicklook-Angaben mit
dokumentierten Vorgabewerten, falls das Feld aus §5 fehlt).

### 4.3 `src/grouping.ts` → generisch

Der Schlüssel kommt aus dem Datensatzeintrag statt aus Regex auf der Item-ID:

```
key = <Datum aus item.datetime> | <Wert von properties[k] für jedes k aus grouping.keys>
```

`typeRank`, `trackOf`, `productTypeOf`, `isGnItem` und die BIOMASS-Etiketten
entfallen. Die Sortierung bleibt „neuestes Datum zuerst", danach stabil nach
Schlüssel. Das Etikett einer Gruppe wird aus Datum und den Schlüsselwerten
gebaut.

**Für Sentinel-2 entschieden (§12 Antwort 1): `grouping_keys = ["grid:code"]`.**
Ein Zeitschritt ist damit **eine MGRS-Kachel an einem Datum** und führt auf genau
ein Item — nach D11 gibt es in M2 kein Mosaik im Kachel-Pfad, eine Gruppe muss
also auf genau eine Kachel-URL führen, und ein Datatake umfasst viele Kacheln.
`s2:datatake_id` bleibt erhalten, aber als **angezeigte Eigenschaft** der Gruppe
(`display_properties`, §5), nicht als Teil des Schlüssels. Dass eine Gruppe damit
in der Regel genau ein Item hat, ist kein Sonderfall: Die Gruppe bleibt eine
Menge, und der zweite Datensatz darf mehr als eines hineinlegen.

### 4.4 `src/mapLayers.ts` — Quicklooks ohne Proxy

Nur der Beschaffungsweg ändert sich; `keyBlackToTransparent`, `loadTransparent`,
`placeImage`, der Generationszähler `syncGen` und die Obergrenze von 40 Overlays
bleiben wie sie sind. Die URL ist künftig `item.assets[<quicklook>].href`,
gewählt generisch: Asset mit Rolle `thumbnail`, sonst `overview`, sonst das erste
Asset mit `image/*`-Typ. **`img.crossOrigin = 'anonymous'` ist ab jetzt die tragende Zeile** und darf beim
Umbau nicht verlorengehen: Ohne sie sperrt der Browser das Canvas, sobald das Bild
nicht mehr same-origin über den Proxy kommt, und `getImageData` wirft — das Keying
fiele still aus. Die Zeile steht bereits (`mapLayers.ts:71`), der Asset-Host sendet
`Access-Control-Allow-Origin: *` (`adr/0006` §3.6, gemessen), damit trägt der Weg.
Ein Test kann das nicht zeigen (F2 = a: keine Oberflächentests), deshalb steht es
als Punkt in der Vorführung (§9) und als Kommentar an der Zeile. Der
BIOMASS-Sonderfall `rotate180` für `S[123]_SCS|DGM` in `geoUtils.ts:104` entfällt;
die Ecken kommen weiter aus `footprintCorners`. Der Schwellwert für „schwarz ist
Nodata" kommt aus `earthx:viewer` statt als Konstante im Code (Inventar F6, §5).

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

## 5. `earthx:viewer` — die Form, die M2-04 anlegt

M2-07a soll „F5 Gruppierung mit Schlüssel **aus der Registry**" umsetzen, und das
Inventar verlangt dasselbe für die Nodata-Schwelle und den Quicklook (F6: „gehören
als Felder an den Datensatz statt in den Code"). Otto hat das Feld am 20.09.2026
freigegeben (§12 Antwort 2) und zugleich festgelegt: **angelegt wird es in M2-04**,
das die Registry ohnehin um `asset_hosts` und die Standard-Visualisierung erweitert.
**M2-07a liest es nur.** Dieser Abschnitt ist deshalb die Bestellung an M2-04.

**Dataclass in `backend/earthx/catalog/registry.py`:**

```python
@dataclass(frozen=True)
class ViewerInfo:
    """Datensatzabhängige Angaben, die nur der Viewer braucht (Inventar F5, F6)."""

    # STAC-Property-Schlüssel, die zusätzlich zum Datum den Zeitschritt bilden.
    grouping_keys: tuple[str, ...]
    # Properties, die am Zeitschritt angezeigt, aber nicht gruppiert werden.
    display_properties: tuple[str, ...]
    # Asset-Schlüssel des Quicklooks; None ⇒ der Client sucht über die Rolle.
    quicklook_asset: str | None
    # Schwelle, unter der ein Kanal als Nodata gilt; None ⇒ kein Canvas-Keying.
    quicklook_nodata_threshold: int | None
```

**Wert für `sentinel-2-c1-l2a` in `catalog/datasets.py`:**

```python
viewer=ViewerInfo(
    grouping_keys=("grid:code",),          # Otto, 20.09.2026: ein Zeitschritt = eine MGRS-Kachel (D11)
    display_properties=("s2:datatake_id",),  # der Überflug, angezeigt statt gruppiert
    quicklook_asset="thumbnail",           # L2A_PVI.jpg, gemessen (§2.1)
    quicklook_nodata_threshold=16,         # Schwelle des Prototyps (mapLayers.ts)
)
```

**Abbildung in `catalog/collection.py`,** als neunte `earthx:`-Zeile:

```python
"earthx:viewer": {
    "grouping_keys": list(config.viewer.grouping_keys),
    "display_properties": list(config.viewer.display_properties),
    "quicklook_asset": config.viewer.quicklook_asset,
    "quicklook_nodata_threshold": config.viewer.quicklook_nodata_threshold,
},
```

Dazu gehören in M2-04: die neunte Zeile in der Tabelle `architekturplan.md` 5.1
(`earthx:viewer` | Gruppierung und Quicklook-Angaben des Viewers), ein Test auf
die Abbildung und einer auf vollständig gesetzte Felder je Eintrag (B10).
Modulgrenzen bleiben unberührt; `viewer` ist ein Feld an `DatasetConfig` neben
`coverage` und `default_render`, kein neues Modul.

**Das Frontend kommt auch ohne aus.** Fehlt `earthx:viewer` — etwa weil 07a vor
M2-04 gemergt wird oder ein künftiger Eintrag es nicht setzt —, gelten dokumentierte
Vorgabewerte: nur Datum als Schlüssel, keine angezeigten Properties, Quicklook über
die Rolle (`thumbnail`, dann `overview`, dann `image/*`), **kein** Keying. Kein
Sonderfall im Code, keine Fehlermeldung.

## 6. Tests (Vitest, F2 = a)

Eingerichtet wird `vitest` als einzige neue Entwicklungsabhängigkeit, ohne
DOM-Umgebung: geprüft wird **nur reine Logik**, keine Oberfläche. Konfiguration
im vorhandenen `vite.config.ts` (`test: { include: ['src/**/*.test.ts'] }`),
Skript `"test": "vitest run"`, Import der Prüf-Funktionen aus `vitest` statt
über globale Namen, damit keine `types`-Zeile in `tsconfig.app.json` nötig wird.

| Datei | Fälle |
|---|---|
| `api.test.ts` | URL-Bau der Suche (bbox-Reihenfolge, `datetime`-Bereich, `limit`, `token`); Seitenmarke aus dem `next`-Link gezogen; **kein** `next`-Link ⇒ `nextToken === null`; Fehlerkörper in beiden Formen (`detail`, `{code, description}`); `400` der Mehrquellensuche kommt als lesbare Meldung an |
| `grouping.test.ts` | Schlüssel aus Datum + `grouping_keys` (`grid:code`); zwei MGRS-Kacheln am selben Tag ⇒ zwei Zeitschritte, derselbe Datatake trennt sie nicht; `display_properties` landen am Etikett, **nicht** im Schlüssel; fehlende Property ⇒ eigene Gruppe statt Absturz; fehlendes `datetime` ⇒ Gruppe „ohne Datum"; Sortierung neuestes zuerst; leere Eingabe ⇒ leere Liste |
| `dateFallback.test.ts` | Fensterfolge ±7/±30/±90; Auswahl des zeitlich nächsten Items bei Treffern auf beiden Seiten; Gleichstand ⇒ das ältere; alle drei Stufen leer ⇒ kein Fallback, klare Meldung; kaputtes `datetime` wird übersprungen; **gekappte Sonde** (`numberMatched > numberReturned`) ⇒ der Hinweis sagt „gefundene" und nennt die Zahlen (§4.5.1) |
| `datasets.test.ts` | `earthx:viewer` fehlt ⇒ dokumentierte Vorgabewerte (nur Datum, Rolle, kein Keying); Collection ohne `earthx:`-Felder bricht die Auswahl nicht; Quicklook-Asset: `quicklook_asset` vor Rolle vor Typ, keines vorhanden ⇒ `null`; `quicklook_nodata_threshold = null` ⇒ kein Keying |

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
| `earthx:viewer` wird in M2-09b/M2-10 zu eng | Frontend hat dokumentierte Vorgabewerte und kommt ohne das Feld aus |
| M2-04 legt `earthx:viewer` anders an als §5 bestellt | §5 nennt Dataclass, Werte und JSON-Abbildung wörtlich; weicht M2-04 ab, ändert sich im Frontend nur `datasets.ts` |
| Ein Zeitschritt mit genau einem Item wirkt wie eine überflüssige Ebene | Die Gruppe bleibt eine Menge und trägt `display_properties`; der zweite Datensatz (M2-10) darf mehrere Items hineinlegen, ohne dass sich etwas ändert |

## 12. Antworten von Otto (20.09.2026)

| # | Frage | Antwort | Folge im Plan |
|---|---|---|---|
| 1 | Gruppierungsschlüssel für Sentinel-2 | **(b) Datum + `grid:code`.** Begründung: Nach D11 gibt es in M2 kein Mosaik im Kachel-Pfad, eine Gruppe muss also auf genau ein Item und damit eine Kachel-URL führen; ein Datatake umfasst viele Kacheln. `s2:datatake_id` bleibt als angezeigte Eigenschaft der Gruppe | §4.3, §5 (`grouping_keys` / `display_properties`), §6 |
| 2 | Wo steht der Schlüssel | **(a) Neues Feld `earthx:viewer`** in Registry und Collection, neunte Zeile in `architekturplan.md` 5.1 — **freigegeben**. Angelegt wird es aber **in M2-04**, das die Registry ohnehin erweitert. M2-07a liest das Feld nur und **hängt damit an M2-04** | §5 ist die Bestellung an M2-04; §7 ohne Backend-Commit; §13 |
| 3 | Zuschnitt des PR | **(a) Ein PR mit dem Abbau.** Im PR ausdrücklich vermerken, dass der Viewer auf `main` zwischen 07a und 07b keine Bilder zeigt | §8, §9, §13 |
| 4 | TypeScript-Client | **(a) Handgeschrieben in M2;** die Generierung aus dem OpenAPI-Schema wird eine eigene Aufgabe nach M2-06 | §4.1 unverändert; eigene Log-Zeile |
| 5 | Datums-Fallback | **(a) ±7/±30/±90 Tage, zeitlich nächstes Item, sichtbarer Hinweis.** Da die Quelle nicht sortiert, muss das Fenster innerhalb einer Suche auswertbar bleiben; `limit` und Seitenmarke sind im Plan zu benennen | **§4.5.1** neu |
| 6 | Serverzustand | **(a) Bei `zustand` bleiben** | §4.5 unverändert, keine neue Abhängigkeit |

Dazu ein Hinweis für die Umsetzung, der in §4.4 eingearbeitet ist: Die Quicklooks
kommen direkt vom Asset-Host (D14); für das Canvas-Keying aus Inventar F6 muss das
Bild mit `crossOrigin="anonymous"` geladen werden, sonst ist das Canvas gesperrt.
Der Host sendet laut `adr/0006` `Access-Control-Allow-Origin: *`.

## 13. Stand der Umsetzung

Aus Antwort 2 folgt die Reihenfolge **M2-04 vor M2-07a**: Das Feld `earthx:viewer`
entsteht dort, und M2-07a liest es. M2-04 ist zum Zeitpunkt dieses Plans **nicht
umgesetzt** (Welle 2 laut `m2-format-und-viewer.md` §3, M2-07a ist Welle 3). Die
Umsetzung von M2-07a beginnt deshalb, sobald M2-04 gemergt ist.

Technisch ginge 07a auch vorher: Das Frontend hat für ein fehlendes `earthx:viewer`
dokumentierte Vorgabewerte (§5), und die Gruppierung liefe dann bis zum Merge von
M2-04 auf „nur Datum" statt auf `grid:code`. Ob 07a so vorgezogen wird, entscheidet
Otto; der Plan setzt es nicht voraus.

**Was der PR beim Fertigmelden ausdrücklich sagen muss** (Antwort 3): Zwischen dem
Merge von 07a und dem von 07b zeigt der Viewer auf `main` **keine vollaufgelösten
Bilder** — Kacheln, Darstellungssteuerung, Coverage und Download sind ausgebaut und
kommen mit 07b bis 07d zurück. Sichtbar bleiben in dieser Zeit die Quicklook-Overlays
und die Footprints.
