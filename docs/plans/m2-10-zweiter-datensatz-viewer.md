# M2-10 — Zweiter Datensatz im Viewer: Umsetzungsplan

**Aufgabe:** M2-10 aus `docs/plans/m2-format-und-viewer.md` §4.
**Stufe B** — **von Otto am 22.09.2026 freigegeben** (F1 (a) bis F6 (a), dazu zwei
Zusätze; §10). Der Plan-Schritt ist damit abgeschlossen, die Umsetzung läuft.
**Ort im Repo:** `docs/plans/m2-10-zweiter-datensatz-viewer.md`
**Grundlagen:** `plans/m2-format-und-viewer.md` (D8, D14, D19, D20, D23, D25, D26,
Abnahmekriterium 1); `adr/0006` (Kachel-Pfad); `adr/0007` §12.7 (kein Quicklook),
§12.10 (Zoomstufen z8–z14), §12.11 Punkt 8 und 14; `adr/0004` (Coverage);
`projektuebersicht.md` §5 (Onboarding-Checkliste, Punkte 2, 9, 10) und §7
(„Health-Status der Quelle sichtbar"); `architekturplan.md` 5.1.
**Stand der Vorarbeit:** M2-09b ist gemergt (#55, #57, #58, #60). Der zweite
Datensatz steht in Registry und Katalog, der Zarr-Lesepfad, die
Gruppenadressierung, die Stichproben-Coverage und die Kachelroute sind da.

---

## 1. Ziel in einem Satz

`sentinel-2-l2a-zarr3` ist im selben Viewer wählbar wie `sentinel-2-c1-l2a` —
mit Kacheln, Coverage, Zuschnitt-Download und einem Ersatz für den Quicklook,
den diese Quelle nicht führt — und das Frontend verzweigt dabei an keiner Stelle
auf eine Datensatz-ID.

---

## 2. Ausgangslage: was schon trägt

Vieles ist mit M2-07a bis M2-07d generisch gebaut worden und trägt den zweiten
Datensatz bereits ohne Änderung:

| Was | Wo | Trägt den zweiten Datensatz, weil |
|---|---|---|
| Datensatz-Auswahl | `frontend/src/components/ControlPanel.tsx::DatasetSelector` | listet `/stac/collections`, nicht eine feste Liste |
| Gruppierung der Zeitleiste | `frontend/src/grouping.ts`, `datasets.ts::groupByOf` | liest `earthx:viewer.group_by`; beide Einträge setzen `("datetime", "grid:code")` |
| Suche je Datensatz | `store.ts::runSearch` | nennt immer genau eine Collection (D8) |
| Datums-Rückfall | `dateFallback.ts` | rein zeitlich, quellenunabhängig |
| Volle Auflösung, Streckbereich, „Apply" | `store.ts::enterFocus`, `render.ts` | nimmt `earthx:default_render` — der zarr3-Eintrag hat seit #58 genau einen Asset-Schlüssel `SR_10m:b04,b03,b02` |
| Statistik / Auto-Stretch | `api.ts::fetchStatistics` | Backend rechnet sie auf der gröbsten Stufe (`adr/0007` §12.11 Punkt 8) |
| Coverage | `coverage.ts`, `ControlPanel::CoverageControls` | `completenessNote` kennt `sample` schon; der Anbieter kam mit #60 |
| Zuschnitt-Download | `download.ts`, `api.ts::downloadCrop` | `AccessInfo`-Lizenzstufe ist bei beiden `processing`; `access/download.py` nimmt `AssetPath` **und** `ZarrAsset` |

Was dieser Plan anfasst, ist deshalb klein und liegt an vier Stellen.

---

## 3. Befunde dieser Sitzung — was heute nicht trägt

Gelesen wurde der Code, nicht die Quelle: `adr/0002` T-D hält fest, dass ein
Live-Smoke aus einer Cloud-Sitzung nicht nachfahrbar ist. Die Belege unten sind
Fundstellen im Repo.

### 3.1 Ohne Thumbnail-Asset zeigt der Viewer in der Übersicht gar nichts

`datasets.ts::quicklookAsset` sucht Rolle `thumbnail`, dann `overview`, dann das
erste `image/*`-Asset. `sentinel-2-l2a-zarr3` führt keines davon (`adr/0007`
§12.7: über 20 geprüfte Items nur `data`, `metadata`, `archive`, `atmosphere`,
`mask`, `reflectance`). Die Folge heute:

- `mapLayers.ts::addQuicklook` kehrt ohne Overlay zurück (`if (!coords || !asset) return`),
- `store.ts::addCurrentToLayers` legt im Browse-Modus **keine** Ebene an und meldet
  „Nothing to add",
- `ResultsPanel.tsx::Row` zeigt den leeren Platzhalter ohne Begründung.

Der Zeitschritt ist also auswählbar, aber unsichtbar, bis man auf volle Auflösung
geht. `adr/0007` §12.7 und §6 Punkt 5 legen den Ersatz fest: **eine Vorschau aus
der gröbsten Auflösungsstufe über denselben Kachelpfad** — gemessen 38 kB und
0,6 s, und ohne eigenen Endpunkt, weil es eine Kachel-URL ist.

Zusätzlich greift der Sonderweg der Quicklooks hier ohnehin nicht:
`mapLayers.ts::loadTransparent` lädt das Bild per `crossOrigin` und keyt
Schwarz auf transparent — das ist für eine JPEG-Vorschau mit schwarzem Rand
gebaut. Eine Kachel aus unserem eigenen Prozess kommt bereits mit Alphakanal
(rio-tiler maskiert), braucht dieses Verfahren also nicht.

### 3.2 Die freigegebenen Zoomstufen stehen als Konstante im Frontend

`mapLayers.ts` hat `MAX_RASTER_ZOOM = 19`, und der Kommentar darüber sagt selbst,
warum: „No registry field names a dataset's ground sample distance yet (only the
Zarr candidate's D23 gives zoom bounds, and only for that one dataset)". Mit M2-10
ist genau das fällig. D23 und `adr/0007` §12.10/F9 geben für `sentinel-2-l2a-zarr3`
**z8 bis z14** vor, Überzoom darüber erlaubt; unterhalb z8 ist die Coverage-Karte
zuständig, nicht der Kachelpfad. Der Aufgabentext von M2-10 verlangt ausdrücklich,
dass „auch die freigegebenen Zoomstufen" aus der Registry kommen.

Kostenband aus `adr/0007` §12.10, das die Untergrenze trägt: z8–z10 unter 0,4 MB
für eine Echtfarb-Kachel, ab z11 rund 3,7–4,3 MB und rund 5 s kalt.

### 3.3 „staging" ist im Katalog, aber nicht im Viewer

`earthx:maturity` steht am Eintrag (`catalog/datasets.py`) und wird serialisiert
(`catalog/collection.py`), aber `frontend/src/types.ts::Collection` kennt das Feld
nicht, und keine Komponente zeigt es. D23 macht die Sichtbarkeit zur Auflage
(„Status ‚staging' sichtbar in Registry **und Viewer**", `adr/0007` §12.11 Punkt 14).

Für `earthx:health` galt derselbe Befund, und die Folgerung daraus ist
**zurückgezogen** (Otto, 22.09.2026, nach dem Befund von M2-08 in #62): Punkt 10
der Onboarding-Checkliste verlangt zwar „zuletzt erfolgreich geprüft ist gesetzt
**und sichtbar**", aber das Feld trägt heute das Datum der *Aufnahme* des
Datensatzes, nicht das einer Prüfung. Eine Zeile daraus hätte behauptet, was die
Plattform nicht weiß. Sie bleibt weg, bis die Health-Checks in M5 ein echtes
Prüfdatum liefern — Punkt 10 ist dann offen statt scheinbar erfüllt.

### 3.4 Der ZIP-Eintrag des Zuschnitts trägt bei Zarr einen unzulässigen Dateinamen

`access/download.py::build_download_zip` schreibt `f"{crop.asset}.tif"`. Beim
ersten Datensatz ist das `visual.tif`. Beim zweiten ist der Asset-Schlüssel der
Gruppen-plus-Variablen-Schlüssel aus D23/§12.11 — also
`SR_10m:b04,b03,b02.tif`. Ein `:` ist unter Windows im Dateinamen nicht zulässig;
je nach Entpacker schlägt das Auspacken fehl oder der Name wird stillschweigend
verändert. Es gibt heute auch keinen Test, der den Zuschnitt über einen
**Zarr**-Pfad führt (`tests/earthx/access/test_download.py` und
`tests/earthx/api/test_download_route.py` nennen `zarr` an keiner Stelle),
obwohl `crop_asset` `ZarrAsset` bereits annimmt und `ZarrReader.feature`
existiert.

### 3.5 Die Checkliste v1 als Test gibt es noch nicht

M2-10s Abnahme sagt „Checkliste v1 grün für beide Datensätze". Die Checkliste
**als Test** ist aber M2-08, und M2-08 steht in der Wellenordnung (§3 des
Aufgabenschnitts) hinter M2-10. Das ist kein Widerspruch im Plan, sondern eine
offene Reihenfolgefrage — §10 F5.

---

## 4. Was neu entsteht, Modul für Modul

### 4.1 `catalog` — die freigegebenen Zoomstufen als Registry-Feld

`ViewerInfo` bekommt zwei Felder, ohne Vorgabewert (KLAERUNGEN B10):

```python
@dataclass(frozen=True, slots=True)
class ViewerInfo:
    group_by: tuple[str, ...]
    min_zoom: int   # unterhalb: Sache der Coverage-Karte, nicht des Kachelpfads
    max_zoom: int   # darüber: Überzoom auf der feinsten Stufe, keine neuen Reads
```

Prüfungen in `__post_init__`: beide ganzzahlig und in `0..MAX_TILE_ZOOM`,
`min_zoom <= max_zoom`. Der obere Riegel steht bei **22**, MapLibres eigener
Obergrenze — dort ist eine Kachel am Äquator rund 4 cm breit. Derselbe Gedanke wie
`MAX_GEOTILE_LEVEL` in `catalog/coverage.py`: eine Stufe jenseits jeder
Bildauflösung ist ein Eintragsfehler, kein gültiger Wunsch.

Werte:

| Datensatz | `min_zoom` | `max_zoom` | Beleg |
|---|---|---|---|
| `sentinel-2-c1-l2a` | 0 | 19 | heutiges Verhalten unverändert (`mapLayers.ts`, #47) |
| `sentinel-2-l2a-zarr3` | 8 | 14 | D23 / `adr/0007` §12.10, F9 (a) |

**Ottos Zusatz 2 zu F2:** Die `0..19` des ersten Datensatzes stehen ausdrücklich
in seinem Registry-Eintrag, nicht als Vorgabewert im Code. Das ist KLAERUNGEN B10
in Reinform — ein Feld ohne Vorgabewert zwingt jeden Eintrag, die Stufen bewusst
zu setzen, und ein vergessenes Feld ist ein `TypeError` am Eintrag statt einer
falschen Antwort später.

`collection.py::to_stac_collection` gibt beide unter `earthx:viewer` mit aus.
`architekturplan.md` 5.1 bekommt in der `earthx:viewer`-Zeile den Zusatz, dass das
Feld in M2 nicht mehr nur `group_by` trägt — eine Dokumentänderung, die an F1 hängt.

### 4.1b `api/tiler.py` — der Tiler setzt die Stufen selbst durch

**Ottos Zusatz 1 zu F1.** Die Registry allein genügt nicht: sie sagt dem *Viewer*,
welche Stufen er anfragen darf, hindert aber keinen anderen Client daran, `z20`
zu verlangen — bei diesem Datensatz eine Kachel, die auf `r10m` gelesen wird.
Der Kachelpfad prüft die Stufe deshalb selbst.

- Eine Anfrage, die `z`/`x`/`y` nennt (also eine Kachel, keine Statistik und kein
  Zuschnitt), wird gegen `viewer.min_zoom`/`max_zoom` des Datensatzes geprüft,
  **bevor** das Item geholt wird — eine abgewiesene Stufe kostet dann keinen
  Request nach außen.
- Außerhalb: **HTTP 400** mit einem Text, der die erlaubte Spanne nennt und keine
  Adresse enthält. 400 und nicht 404, weil die Anfrage selbst falsch ist: 404
  gehört der Kachel, die den Datenbestand verfehlt (`TileOutsideBounds`), und
  beides auseinanderzuhalten ist der Punkt eines definierten Fehlers.
- Ein Datensatz ohne `viewer` wird nicht stillschweigend durchgelassen, sondern
  mit **501** abgewiesen — dasselbe Nichtraten wie im Frontend (§4.2), und
  derselbe Code, mit dem ein Format ohne Reader abgewiesen wird: die Plattform
  ist für diesen Datensatz nicht eingerichtet, der Aufrufer hat nichts falsch
  gemacht.

Damit das trägt, gehören zwei Dinge dazu, die der Review gefunden hat:

- **Nur ein Kachelraster.** Die freigegebene Spanne ist eine Spanne von
  *WebMercatorQuad*-Stufen (`adr/0007` §12.10). `z14` in `WorldCRS84Quad` ist rund
  eine WebMercator-Stufe feiner — mit mehreren Rastern bedeutet dieselbe Zahl zwei
  Auflösungen, und die teure Anfrage geht durch. `supported_tms` steht deshalb auf
  `WebMercatorQuad`, dem einzigen Raster, das der Client anfragt.
- **`/preview` entfällt.** Die Route trägt keine Stufe *und* rechnet keine
  Zielauflösung, liest bei Zarr also die native Stufe — genau der Lesevorgang, den
  die Spanne verhindern soll. Sie wird nicht mehr registriert; niemand fragt sie an.

**Offen geblieben, bewusst:** `/tilejson.json` weist weiterhin die Zoomstufen
seines *Readers* aus statt der freigegebenen. Ein Client, der dem TileJSON folgt
statt URLs selbst zu bauen, wird damit auf Stufen geschickt, die der Riegel
abweist. Der billige Weg ist zu — `minzoom`/`maxzoom` der rio-tiler-Reader sind
berechnete Eigenschaften, nicht setzbar —, es bliebe also, TiTilers Route
nachzubauen. Das ist eine eigene kleine Aufgabe und keine Zeile in diesem PR.

### 4.2 `frontend/src/types.ts`, `datasets.ts` — drei Felder und zwei reine Funktionen

- `EarthxViewer` um `min_zoom`/`max_zoom` erweitert; `Collection` um
  `earthx:maturity` und `earthx:health`.
- `zoomRangeOf(collection)` → `{ min, max } | null`. `null` heißt: der Eintrag sagt
  es nicht — dann rendert der Viewer keine Kacheln und sagt das, statt einen Wert
  zu raten. Das ist dieselbe Haltung wie bei `groupByOf` (ein fehlendes Feld ist
  eine Lücke im Onboarding, kein Fall für eine Vermutung).
- `DatasetOption` trägt `zoom`, `maturity` und `lastCheckedOk` mit.
- `quicklookPlan(item, dataset)` → `{ kind: 'image', href }` wenn das Item ein
  Vorschau-Asset führt, sonst `{ kind: 'tiles', asset }` aus
  `earthx:default_render.assets[0]`, sonst `null`. **Die Verzweigung hängt am Item
  und am Registry-Eintrag, nicht an einer Datensatz-ID** — das ist die
  Kernforderung von M2-10.

### 4.3 `frontend/src/mapLayers.ts`, `store.ts`, `layers.ts` — Overlay mit Zoombereich

- `placeRaster` nimmt `minZoom`/`maxZoom` statt der Konstanten; `MAX_RASTER_ZOOM`
  entfällt. MapLibre verhält sich dann genau nach `adr/0007` §12.10: unter
  `minZoom` wird nichts angefragt, über `maxZoom` wird überzoomt.
- `LayerOverlay.raster` trägt den Zoombereich mit, damit eine angeheftete Ebene
  ihn nach `setStyle()` behält.
- **Quicklook-Ersatz:** `addQuicklook` wird zu `addPreview` und legt für
  `kind: 'tiles'` eine Rasterquelle an, deren `minZoom` **und** `maxZoom` beide auf
  `zoom.min` stehen. Damit liest der Browse-Modus ausschließlich die gröbste
  freigegebene Stufe (bei z8 rechnet `api/tiler.py::_target_gsd` die Zielauflösung
  auf ~600 m und der Reader wählt `r720m`: die gemessenen 38 kB, `adr/0007` §12.4)
  und überzoomt sie darüber. Eine Vorschau ist damit definiert als „die gröbste
  freigegebene Stufe", nicht als ein weiteres Registry-Feld.
- `addCurrentToLayers` heftet im Browse-Modus für solche Items eine
  `raster`-Ebene statt gar keiner an. Herunterladbar wird sie dadurch **nicht**:
  `download.ts::downloadRequestFor` verlangt `restore.focusMode`, und das ist im
  Browse-Modus `false`.
- `enterFocus` reicht den Zoombereich des Datensatzes in `DownloadedInfo` durch.

### 4.4 Oberfläche — zwei Hinweise, beide englisch (D25)

1. **Reifegrad am Datensatzknopf.** Ein Chip „staging" neben dem Titel, Titeltext
   „provider marks this collection staging — it may disappear without notice".
2. ~~**Zuletzt geprüft.**~~ **Zurückgezogen am 22.09.2026 (Otto).** Der Befund
   aus M2-08 (#62): `earthx:health.last_checked_ok` trägt heute das Datum der
   Aufnahme, nicht das einer Prüfung. Die Zeile hätte also etwas behauptet, was
   die Plattform nicht weiß. Ein echtes Prüfdatum kommt mit den Health-Checks in
   M5; Punkt 10 der Checkliste bleibt bis dahin offen, statt scheinbar erfüllt
   zu sein.
3. **Unterhalb der Untergrenze.** Steht die Karte unter `zoom.min`, sagt eine Zeile,
   auf welche Stufe zu zoomen ist, statt eine leere Karte zu zeigen. Dieselbe Stelle
   nennt die Coverage-Karte als das, was auf dieser Zoomstufe zuständig ist
   (`adr/0007` §12.10).

   **Nachtrag 22.09.2026, von Otto lokal gefunden:** Der Hinweis erschien nie. Er
   hing im `ControlPanel`, und `runSearch` setzt `panelCollapsed: true` — die Tafel
   ist also genau dann weggeschoben, wenn es Szenen gibt, die verschwinden könnten.
   Verdeckt hat ihn kein React-Zustand, sondern ein `transform: translateX(-100%)`
   im CSS, weshalb weder Typprüfung noch eine Prüfung der Regel ihn fangen konnte.
   Er steht jetzt in der `StatusBar`, der einzigen Auflage, die immer sichtbar ist,
   und erscheint erst, wenn eine Suche etwas gefunden hat. Die Regel selbst liegt
   als `datasets.ts::zoomFloorHint` rein daneben. Belegt durch einen Render-Test
   (`components/StatusBar.test.tsx`), der die Tafel ausdrücklich eingeklappt setzt;
   er schlägt fehl, sobald der Hinweis wieder aus der `StatusBar` verschwindet.

`ResultsPanel` behält den Platzhalter, bekommt aber einen `title`, der sagt warum
(„this source publishes no preview image") — siehe F4.

### 4.5 `access/download.py` — der Dateiname im ZIP, und ein zweiter Befund

Der ZIP-Eintrag heißt künftig nicht mehr roh nach dem Asset-Schlüssel: alles
außerhalb von `[A-Za-z0-9._-]` wird zu `_`, mehrfaches `_` zusammengezogen.
`visual.tif` bleibt `visual.tif`; `SR_10m:b04,b03,b02` wird
`SR_10m_b04_b03_b02.tif`. Die Hinweisdatei im ZIP nennt zusätzlich den
ursprünglichen Asset-Schlüssel, damit die Zuordnung nicht verloren geht.

**Beim Schreiben des ersten Zuschnitt-Tests über das zweite Format gefunden:**
`crop_asset` fing nur `TileOutsideBounds`/`PointOutsideBounds` ab, die rio-tiler
für ein COG wirft. Über `XarrayReader.feature` wirft rioxarray stattdessen
`NoDataInBounds` — dieselbe Tatsache, anderer Typ. Eine AOI neben der Szene
ergab bei Zarr also `500`, wo dieselbe AOI bei COG `400` ergibt. Alle drei
zählen jetzt gleich, im Mosaik ebenso (dort heißt es: diese Szene überspringen).

---

## 5. Tests

Fixtures ausschließlich synthetisch (`ENTSCHEIDUNGEN` §4, KLAERUNGEN B2); die
Zarr-Pixel kommen aus dem Mini-Zarr von M2-09a.

| Was | Wo | Fehlerfälle und zweckfremde Nutzung, die dazugehören |
|---|---|---|
| `ViewerInfo` Zoomfelder | `backend/tests/catalog/test_registry.py` | `min_zoom > max_zoom`; Stufe negativ; Stufe über 24; Feld fehlt → `TypeError` am Eintrag |
| Tiler weist eine Stufe außerhalb ab | `backend/tests/earthx/api/test_tiler.py` | `z` über `max_zoom` → 400; `z` unter `min_zoom` → 400; die Grenzen selbst sind erlaubt; die Abweisung holt kein Item (kein Request nach außen); `/statistics` und der Zuschnitt sind nicht betroffen |
| Beide Einträge tragen die Stufen | `tests/catalog/test_sentinel_2_l2a.py`, `…_zarr3.py` | zarr3 ist genau `8..14` (D23), COG unverändert `0..19` |
| Serialisierung | `tests/catalog/test_collection.py` | `earthx:viewer` trägt alle drei Felder |
| ZIP-Eintragsname | `tests/earthx/access/test_download.py` | Asset mit `:` und `,`; Asset, das nur aus Sonderzeichen besteht; zwei Assets, die auf denselben bereinigten Namen fielen |
| Zuschnitt über einen Zarr-Pfad | `tests/earthx/access/test_download.py` | AOI außerhalb des Mini-Zarr → `AoiOutsideItems`; unbekannte Variable → definierter Fehler |
| `zoomRangeOf` | `frontend/src/datasets.test.ts` | Feld fehlt → `null`; `min > max` → `null`; Stufe keine Zahl → `null` |
| `zoomFloorHint` (Regel) und die `StatusBar` (Anzeige) | `frontend/src/datasets.test.ts`, `frontend/src/components/StatusBar.test.tsx` | an der Untergrenze selbst kein Hinweis; über ihr keiner; Datensatz ab z0 nie; kein Datensatz gewählt; vor der ersten Suche keiner; gebrochene Kartenzoomstufe zählt zur noch nicht erreichten Stufe |
| `quicklookPlan` | `frontend/src/datasets.test.ts` | Thumbnail vorhanden → `image`; keins, aber `default_render` → `tiles`; weder noch → `null`; `default_render.assets` leer → `null` |
| Kachel-URL der Vorschau | `frontend/src/mapLayers.test.ts` | der Asset-Schlüssel mit `:` und `,` wird genau einmal enkodiert (Z4: dieselbe URL, dasselbe Bild) |
| Reifegrad-Text | `frontend/src/datasets.test.ts` | `stable` erzeugt keinen Chip; unbekannter Wert wird angezeigt, nicht verschluckt |

**Was hier bewusst nicht steht:** ein Test gegen die echte Quelle (`adr/0002` T-D,
M2-13). Die Vorführung gegen `stac.core.eopf.eodc.eu` ist Teil der Abnahme durch
Otto, nicht der CI.

---

## 6. Was nicht angefasst wird

- **`gateway`.** Die Adress-Bindung ist eine Sicherheitseigenschaft aus M1-03.
- **Die Kachelroute und `_target_gsd`.** Die Stufenwahl bleibt gerechnet, nicht
  nachgeschlagen (`adr/0007` §12.10). Der Quicklook-Ersatz braucht daran nichts:
  er ist eine Kachel-URL auf einer Zoomstufe, die das vorhandene Verfahren schon
  richtig beantwortet.
- **Mosaik im Kachelpfad** (D11). Der Vorschau-Ersatz legt eine Rasterquelle **je
  Item** an, wie der Browse-Modus es heute mit je einem Bild-Overlay tut. Es
  entsteht kein Mosaik-Endpunkt.
- **Die Coverage-Heatmap** (D26, Minimalumfang). M2-10 prüft nur, dass die
  Stichprobe des zweiten Datensatzes im Viewer als `sample` ausgewiesen wird.
- **Die Ortssuche** (F1 aus dem Aufgabenschnitt, M3) und der **Theme-Umschalter**
  (V-1, gemergt).
- **Das Entfernen des Prototyps** (M2-11).

---

## 7. Reihenfolge der Umsetzung

Jeder Schritt ist ein eigener Commit.

1. `catalog`: `ViewerInfo` um die Zoomfelder, beide Einträge, Serialisierung, Tests.
2. `api`: der Tiler weist eine Stufe außerhalb der freigegebenen Spanne ab (Zusatz 1), mit Test.
3. `frontend`: Typen, `zoomRangeOf`, `quicklookPlan`, Vitest — reine Logik, ohne Karte.
4. `frontend`: `placeRaster` mit Zoombereich, `MAX_RASTER_ZOOM` entfällt.
5. `frontend`: Vorschau-Ersatz im Browse-Modus und im Layer-Manager.
6. `frontend`: die drei Hinweise (Reifegrad, zuletzt geprüft, Untergrenze).
7. `access`: ZIP-Eintragsname und der Zarr-Zuschnitt-Test.
8. `docs`: Entscheidungslog, `architekturplan.md` 5.1, Aufgabenschnitt auf erledigt.

Richtwert: unter 400 geänderte Zeilen ohne generierte Dateien. Die Schätzung
liegt bei rund 300 — der größte Einzelposten ist Schritt 4.

---

## 8. Risiken

| Risiko | Wirkung | Gegenmittel |
|---|---|---|
| Der Browse-Modus zeigt bis zu 40 Items gleichzeitig; jede Vorschau ist eine eigene Rasterquelle | 40 Kachelanfragen statt 40 Thumbnail-Ladungen | Die Vorschau liest ausschließlich `zoom.min` (bei zarr3: `r720m`, 38 kB je Kachel) und überzoomt darüber; `MAX_MOSAIC_LAYERS = 40` bleibt die Obergrenze |
| Unter z8 zeigt der zweite Datensatz nichts | wirkt wie ein Fehler | Hinweiszeile (§4.4 Punkt 3) |
| `sentinel-2-l2a-zarr3` ist „staging" und kann verschwinden | Vorführung fällt aus | D24: die M2-Abnahme hängt nicht am Fortbestand; der Lesepfad gegen das synthetische Zarr aus M2-09a genügt. Die Frontend-Tests laufen ohnehin gegen Fixtures |
| Kalte Kachel ab z11 rund 5 s (`adr/0007` §12.10) | volle Auflösung fühlt sich zäh an | Nicht Gegenstand von M2-10; der HTTP-Cache ist bei diesem Datensatz Voraussetzung und steht als eigene Zeile im Log |

---

## 9. Abnahme dieses Plans

- Die Fragen in §10 sind beantwortet.
- Danach erst Code: ein Branch, ein Draft-PR, Tests und Lint grün
  (`ruff check backend`, `pytest`, `lint-imports --config .importlinter`,
  `npm run lint`, `npx tsc -b`, `npm run test`), Ergebnis im PR zusammengefasst.
- Vorführbar: Abnahmekriterium 1 aus §5 des Aufgabenschnitts — beide Datensätze
  im selben Viewer, suchen, ansehen, Zuschnitt herunterladen.

---

## 10. Fragen an Otto — **beantwortet am 22.09.2026**

Otto hat alle sechs Empfehlungen angenommen: **F1 (a), F2 (a), F3 (a), F4 (a),
F5 (a), F6 (a)**, dazu zwei Zusätze:

- **Zu F1:** Der Tiler setzt die Zoomstufen aus `earthx:viewer` ebenfalls durch
  und antwortet außerhalb davon mit einem definierten Fehler, belegt mit Test —
  sonst kann jeder Client teure Zarr-Kacheln weit über z14 anfordern. Umgesetzt
  in §4.1b.
- **Zu F2:** Die Stufen `0..19` stehen ausdrücklich im Registry-Eintrag von
  Sentinel-2, nicht als Vorgabewert im Code (KLAERUNGEN B10). Umgesetzt in §4.1.

Die Fragen bleiben im Wortlaut stehen, damit nachlesbar ist, wogegen entschieden
wurde.

**F1 — Wo stehen die freigegebenen Zoomstufen?**
(a) Zwei neue Felder `min_zoom`/`max_zoom` in `earthx:viewer`; die Zeile in
`architekturplan.md` 5.1 sagt dann nicht mehr „in M2 genau ein Feld".
**Empfehlung.**
(b) Ein eigener Block `earthx:tiles` daneben. Sauberer getrennt, aber eine elfte
Zeile in 5.1 für zwei Zahlen.
(c) Konstante im Frontend lassen und z8–z14 dort festschreiben. **Abzulehnen** —
das ist genau die datensatzspezifische Verzweigung, die M2-10 verbietet.

**F2 — Welche Stufen bekommt der erste Datensatz (COG)?**
(a) `0..19`, also exakt das heutige Verhalten aus #47. **Empfehlung** — M2-10
soll den zweiten Datensatz tragen, nicht den ersten stillschweigend ändern.
(b) `0..14`, passend zur nativen Bodenauflösung von 10 m. Ändert das Verhalten
des ersten Datensatzes und gehört dann in eine eigene Messung.

**F3 — Welche Form hat der Quicklook-Ersatz?**
(a) Rasterkacheln auf der gröbsten freigegebenen Stufe (z8 → `r720m`, gemessen
38 kB / 0,6 s), darüber Überzoom. Kein neuer Endpunkt. **Empfehlung.**
(b) Ein serverseitig gerendertes Einzelbild je Szene über `/preview`. Braucht
eine Backend-Änderung (sonst liest `preview` die native 10-m-Stufe) und liegt in
der UTM-Projektion der Szene, also schief auf der Webkarte.
(c) Kein Ersatz, nur Footprints. Widerspricht dem Ziel von M2-10.

**F4 — Was zeigt die Trefferliste je Szene, wenn die Quelle kein Vorschaubild führt?**
(a) Der heutige Platzhalter, ergänzt um eine Begründung im Titeltext.
**Empfehlung** — hält den PR klein, die Karte zeigt das Bild ohnehin.
(b) Zusätzlich die z8-Kachel, in der der Szenenmittelpunkt liegt, als Miniatur.
Schöner, aber eine Anfrage je Zeile und etwas Geotile-Arithmetik im Frontend.

**F5 — „Checkliste v1 grün für beide Datensätze": jetzt oder mit M2-08?**
(a) M2-10 führt die Kette Suche → Anzeige → Zuschnitt-Download für beide
Datensätze vor (lokal und über Fixtures in den Tests); die Checkliste **als
Test** bleibt M2-08, wie die Wellenordnung es vorsieht. **Empfehlung.**
(b) Den Checklisten-Test nach M2-10 vorziehen. Macht den PR deutlich größer und
doppelt Arbeit, die M2-08 ohnehin macht.

**F6 — Der ZIP-Eintragsname des Zuschnitts (§3.4).**
(a) In M2-10 bereinigen, mit Test — wenige Zeilen, und ohne das ist der
Zuschnitt des zweiten Datensatzes auf Windows nicht auspackbar. **Empfehlung.**
(b) Als eigene Zeile ins Log und M2-08 überlassen.
