# M2-07a — Frontend: API-Client, Suche, Quicklooks, Zeitleiste: Umsetzungsplan

**Status:** **Plan, wartet auf Ottos OK.** **Stufe B** laut `projektplan.md` 1.2:
Plan zuerst als Draft-PR, Umsetzung erst nach dem OK. Die sechs Fragen in §12
hängen an; §12 F1–F3 ändern den Zuschnitt, F4–F6 nur Details.
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
**Voraussetzung — erledigt:** Der Tag `prototype-biomass` steht auf `main`
(`48d573c`, am 20.09.2026 von Otto gesetzt). Der Stand des Prototyp-Frontends
ist damit dauerhaft erreichbar; dieser Plan darf im Arbeitsbaum löschen.

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
`GET /stac/collections` ist damit die Datensatzliste des Viewers. Zwei Felder, die
07a braucht, fehlen dort heute: der Gruppierungsschlüssel und die Quicklook-Angaben
(§5, §12 F1/F2).

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
zweiter Datensatz (M2-10); alles im Backend außer dem einen Registry-Feld aus §5;
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
gebaut, die Mitglieder tragen ihr `grid:code` als Beschriftung. Empfehlung für
Sentinel-2: `keys = ["s2:datatake_id"]` — eine Gruppe ist damit **ein Überflug**,
und die benachbarten MGRS-Kacheln einer AOI liegen zusammen in einer Gruppe, so
wie beim Prototyp die Frames eines Tracks. Siehe §12 F1.

### 4.4 `src/mapLayers.ts` — Quicklooks ohne Proxy

Nur der Beschaffungsweg ändert sich; `keyBlackToTransparent`, `loadTransparent`,
`placeImage`, der Generationszähler `syncGen` und die Obergrenze von 40 Overlays
bleiben wie sie sind. Die URL ist künftig `item.assets[<quicklook>].href`,
gewählt generisch: Asset mit Rolle `thumbnail`, sonst `overview`, sonst das erste
Asset mit `image/*`-Typ. `img.crossOrigin = 'anonymous'` steht bereits
(`mapLayers.ts:71`) und ist jetzt die tragende Zeile: Der Asset-Host sendet
`Access-Control-Allow-Origin: *` (`adr/0006` §3.6, gemessen), das Canvas bleibt
damit unverwehrt. Der BIOMASS-Sonderfall `rotate180` für `S[123]_SCS|DGM` in
`geoUtils.ts:104` entfällt; die Ecken kommen weiter aus `footprintCorners`.
Der Schwellwert für „schwarz ist Nodata" kommt aus dem Datensatzeintrag statt
als Konstante im Code (Inventar F6, §12 F2/F6).

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
- **Datums-Fallback:** Bleibt die Suche im gewählten Zeitraum leer, sucht der
  Store in bis zu drei Stufen mit erweitertem Fenster (±7, ±30, ±90 Tage um den
  Zeitraum) weiter und nimmt das Item mit dem kleinsten zeitlichen Abstand zum
  gewählten Zeitraum. Gefunden wird dann dessen Zeitschritt, und `notice` sagt
  sichtbar: „Kein Treffer im gewählten Zeitraum — nächstgelegene Aufnahme: TT.MM.JJJJ".
  Bewusst ohne Verlass auf die Sortierung der Quelle: `sort` ist in `earthx`
  abgeschaltet (`api/main.py:36`), die Reihenfolge der Quelle ist nirgends
  zugesichert. Prinzip 9 („Ehrlichkeit in der Anzeige") verlangt den Hinweis.
- `runDownload`, `runDecompose`, `loadCoverage`, `applyRender`, `setPolMode`,
  `setPolBand`, `setDecompMethod`, `focusMode` und die Felder für Streckbereich
  und Colormap entfallen hier und kommen mit 07b/07c/07d zurück (§12 F3).
- `addCurrentToLayers` bleibt, aber nur mit Quicklook-Overlays; der
  `restore`-Block verliert `downloaded` und `appliedRender`.

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

## 5. Die eine Backend-Änderung: der Gruppierungs- und Quicklook-Schlüssel

M2-07a soll „F5 Gruppierung mit Schlüssel **aus der Registry**" umsetzen, und
das Inventar verlangt dasselbe für die Nodata-Schwelle und den Quicklook (F6:
„gehören als Felder an den Datensatz statt in den Code"). Beides braucht ein
Feld, das es heute nicht gibt. Vorschlag: **ein** neues Feld statt zweier —

```python
@dataclass(frozen=True)
class ViewerInfo:
    grouping_keys: tuple[str, ...]      # STAC-Property-Schlüssel, zusätzlich zum Datum
    member_label_property: str | None   # Beschriftung der Gruppenmitglieder
    quicklook_asset: str | None         # None ⇒ über die Rolle suchen
    quicklook_nodata_threshold: int | None   # None ⇒ kein Keying
```

für Sentinel-2: `("s2:datatake_id",)`, `"grid:code"`, `"thumbnail"`, `16`.
Abgebildet in `catalog/collection.py` als **`earthx:viewer`** — das wäre die
**neunte** Zeile in `architekturplan.md` 5.1, also eine Architekturänderung, die
Otto entscheidet (§12 F2). Der Umfang im Backend ist klein: Dataclass in
`catalog/registry.py`, Wert in `catalog/datasets.py`, Abbildung in
`catalog/collection.py`, je ein Test dazu, eine Zeile in 5.1 und eine im
Entscheidungslog. Modulgrenzen bleiben unberührt.

Das Frontend behandelt ein fehlendes `earthx:viewer` nicht als Fehler, sondern
fällt auf „nur Datum, Quicklook über die Rolle, kein Keying" zurück — so bleibt
der zweite Datensatz aus M2-10 ohne Sonderfall bedienbar.

## 6. Tests (Vitest, F2 = a)

Eingerichtet wird `vitest` als einzige neue Entwicklungsabhängigkeit, ohne
DOM-Umgebung: geprüft wird **nur reine Logik**, keine Oberfläche. Konfiguration
im vorhandenen `vite.config.ts` (`test: { include: ['src/**/*.test.ts'] }`),
Skript `"test": "vitest run"`, Import der Prüf-Funktionen aus `vitest` statt
über globale Namen, damit keine `types`-Zeile in `tsconfig.app.json` nötig wird.

| Datei | Fälle |
|---|---|
| `api.test.ts` | URL-Bau der Suche (bbox-Reihenfolge, `datetime`-Bereich, `limit`, `token`); Seitenmarke aus dem `next`-Link gezogen; **kein** `next`-Link ⇒ `nextToken === null`; Fehlerkörper in beiden Formen (`detail`, `{code, description}`); `400` der Mehrquellensuche kommt als lesbare Meldung an |
| `grouping.test.ts` | Schlüssel aus Datum + `grouping_keys`; fehlende Property ⇒ eigene Gruppe statt Absturz; fehlendes `datetime` ⇒ Gruppe „ohne Datum"; Sortierung neuestes zuerst; leere Eingabe ⇒ leere Liste |
| `dateFallback.test.ts` | Fensterfolge ±7/±30/±90; Auswahl des zeitlich nächsten Items bei Treffern auf beiden Seiten; Gleichstand deterministisch; alle drei Stufen leer ⇒ kein Fallback, klare Meldung; kaputtes `datetime` wird übersprungen |
| `datasets.test.ts` | `earthx:viewer` fehlt ⇒ dokumentierte Vorgabewerte; Collection ohne `earthx:`-Felder bricht die Auswahl nicht; Quicklook-Asset: Rolle vor Typ, keines vorhanden ⇒ `null` |

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
2. `feat(catalog): add the viewer hints (grouping, quicklook) to the registry` — nur, wenn §12 F2 = a
3. `feat(frontend): talk to the earthx STAC API instead of the prototype` (api.ts, vite.config.ts, types.ts)
4. `feat(frontend): pick the dataset from /stac/collections` (datasets.ts, ControlPanel, store)
5. `feat(frontend): group items into time steps from the registry key` (grouping.ts + Test)
6. `feat(frontend): load quicklooks straight from the asset host` (mapLayers.ts, geoUtils.ts, ResultsPanel)
7. `feat(frontend): fall back to the nearest date and say so` (store + Test)
8. `refactor(frontend): drop the BIOMASS-only paths until 07b–07d rebuild them` (Löschungen)
9. `docs: record M2-07a in the decision log`

## 8. Umfang

Geschätzt rund 300 neue und geänderte Zeilen plus rund 400 gelöschte
(`products.ts` 121, `ViewerControls.tsx` 189, `DownloadBar.tsx` 66,
`SearchBox.tsx` 92, dazu Teile von `store.ts`). Der Richtwert von 400 Zeilen
(`CLAUDE.md`) ist damit überschritten, überwiegend durch Löschungen. §12 F3
stellt die Teilung zur Wahl.

## 9. Abnahme

- `npm run lint`, `npx tsc -b --pretty false` und `npm test` grün; `ruff check backend`
  und `pytest` grün, falls §5 umgesetzt wird.
- `grep -rn "/api/" frontend/src` findet nichts mehr (M2-Abnahmekriterium 7).
- Lokal vorführbar mit `docker compose up` und `npm run dev`: Datensatz wählen,
  AOI zeichnen oder hochladen, suchen, Quicklooks auf der Karte, Zeitleiste
  abspielen, Szene anklicken und auswählen; ein Zeitraum ohne Treffer zeigt den
  Datums-Hinweis. Die Anleitung steht im PR.
- Eine Suche, die zwei Datensätze umfasst, ist in der Oberfläche gar nicht
  erst auslösbar; der `400` der API ist trotzdem als Meldung geprüft.

## 10. Was diese Aufgabe nicht anfasst

`backend/app/` (Prototyp bis M2-11), `docker-compose.yml`, `.importlinter`,
`index.css`/`App.css` und das HUD-Design, `MapView.tsx`, die Zeichenwerkzeuge,
`aoiFile.ts`, alle Backend-Module außer den drei Dateien aus §5, `CODEOWNERS`,
`.claude/`. An `.github/workflows/ci.yml` nur der Vitest-Schritt.

## 11. Risiken

| Risiko | Umgang |
|---|---|
| Form des `next`-Links weicht von der Erwartung ab | Der Client liest den Parameter aus der `href` statt ein Format anzunehmen; Test deckt „kein Link" ab; im Umsetzungsschritt einmal gegen die laufende API geprüft |
| 300 Items in bis zu drei Seiten sind für eine große AOI zu wenig | `numberMatched` wird angezeigt, der Hinweis rät zur Eingrenzung; echtes Nachladen gehört zu 07c (Coverage entscheidet über die Last) |
| Nodata-Keying entfernt dunkles Wasser | Schwelle am Datensatz statt im Code (§5); für Sentinel-2 bleibt es bei 16 wie im Prototyp, nachjustierbar ohne Codeänderung |
| Der Viewer kann nach 07a vorübergehend weniger als der Prototyp | Beabsichtigt (Strangler); der Stand des Prototyps hängt am Tag `prototype-biomass`; 07b–07d bauen Kacheln, Coverage und Download neu |
| `earthx:viewer` wird in M2-09b/M2-10 zu eng | Frontend hat dokumentierte Vorgabewerte und kommt ohne das Feld aus |

## 12. Fragen an Otto

**F1 — Gruppierungsschlüssel für Sentinel-2.** Ein Zeitschritt ist beim Prototyp
„ein Überflug", also die Menge benachbarter Szenen, die eine AOI gemeinsam
abdecken. `adr/0003` §10.3 nennt als naheliegend „Datum + MGRS-Kachel"; gemessen
(§2.1) gibt es dafür `grid:code`, für den Überflug `s2:datatake_id`, einen
relativen Orbit als Feld jedoch nicht.

- **(a) Datum + `s2:datatake_id`** — eine Gruppe ist ein Überflug, die benachbarten
  MGRS-Kacheln liegen darin zusammen und sind später mosaikfähig. **Empfehlung.**
- (b) Datum + `grid:code` — jede MGRS-Kachel wird ein eigener Zeitschritt; die
  Zeitleiste läuft dann über Kacheln statt über Aufnahmen.
- (c) Nur Datum — am einfachsten, verliert aber die Trennung zweier Überflüge
  am selben Tag.

**F2 — Wo steht dieser Schlüssel?** Heute nirgends.

- **(a) Neues Feld `earthx:viewer`** in Registry und Collection (§5). Das ist eine
  **neunte** Zeile in `architekturplan.md` 5.1, also eine Architekturänderung:
  Log-Zeile und Tabellenzeile, aus meiner Sicht ohne eigenes ADR. **Empfehlung.**
- (b) Das bestehende `earthx:default_render` erweitern — kein neues Feld, aber es
  vermischt Darstellung mit Gruppierung.
- (c) Vorerst fest im Frontend, Registry-Feld erst mit M2-09b — spart die
  Architekturänderung jetzt, widerspricht aber „Schlüssel aus der Registry".

**F3 — Zuschnitt des PR.** Die Pfade ohne `earthx`-Backend (Kacheln, Download,
Dekomposition, Stitching, Coverage, `/api/config`) hängen am selben Code wie die
Suche.

- **(a) In 07a mit abbauen**, rund 700 geänderte Zeilen, davon etwa 400
  Löschungen; danach ruft das Frontend nachweislich keine Prototyp-Route mehr auf.
  **Empfehlung.**
- (b) 07a in zwei PRs teilen: erst Abbau und API-Client, dann Suche, Quicklooks,
  Zeitleiste.
- (c) Die Prototyp-Aufrufe bis 07d stehen lassen — dann bleibt der `/api`-Proxy
  und das M2-Abnahmekriterium 7 offen.

**F4 — TypeScript-Client aus dem OpenAPI-Schema.** `architekturplan.md` 8.1 sagt,
der Client werde generiert. Empfehlung: in M2 **handgeschrieben** (er hat zwei
Funktionen), Generierung als eigene Aufgabe nach M2-06, wenn Kachel-, Coverage-
und Download-Routen stehen. Einverstanden?

**F5 — Datums-Fallback.** Empfehlung: Fenster in drei Stufen erweitern
(±7/±30/±90 Tage) und das zeitlich nächste Item nehmen — höchstens drei
zusätzliche Anfragen, unabhängig von der Sortierung der Quelle, die in `earthx`
abgeschaltet ist. Alternative: eine einzige Sonde ohne Zeitraum, die sich auf die
Reihenfolge der Quelle verlässt (weniger Last, nicht zugesichert). Einverstanden?

**F6 — Serverzustand.** `architekturplan.md` 8.2 nennt eine Trennung von Server-
und UI-Zustand (z. B. TanStack Query). Empfehlung: in M2 **bei `zustand` bleiben**,
keine neue Abhängigkeit; die Trennung lohnt sich, wenn mit 07b/07c mehrere
parallele Abfragen dazukommen. Einverstanden?
