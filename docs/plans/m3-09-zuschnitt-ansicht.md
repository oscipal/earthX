# M3-09 — Vollauflösung zeigt nur den Zuschnitt: Umsetzungsplan

**Aufgabe:** M3-09 aus `docs/plans/m3-dritte-quelle-und-interface.md` §4.
**Stufe B** — **wartet auf Freigabe durch Otto** (Fragen in §8). Bis dahin
kein Produktivcode.
**Ort im Repo:** `docs/plans/m3-09-zuschnitt-ansicht.md`
**Grundlagen:** `plans/m3-dritte-quelle-und-interface.md` (P11, P12, P19,
§4 M3-09, M3-17, M3-18); `adr/0001` (Zustand, Z2, Z9); `adr/0006` (Kachel-Pfad,
§3.5 Mosaik, Antwort „Mosaik nur im Zuschnitt“); `prototyp-inventar.md` F10;
`architekturplan.md` 3.1, 7.3 (Stufe T0), 12.3.

---

## 1. Ziel in einem Satz

Nach „View full resolution“ zeigt die Karte von den gewählten Szenen nur den
Teil innerhalb der AOI, in derselben Überdeckung wie die heruntergeladene
Datei; außerhalb bleibt die Basiskarte sichtbar, und die AOI verlässt dafür
den Browser nicht.

---

## 2. Heutiger Stand am Code

| Stelle | Heute | Folge für M3-09 |
|---|---|---|
| `components/ViewBar.tsx` | ein Knopf „View full resolution“, ruft `store.enterFocus()` | Beschriftung hängt künftig an der AOI (§6) |
| `store.ts::enterFocus` | legt je gewählter Szene einen Eintrag in `downloaded` an: Kachel-Vorlage des `tiler`, `bounds` = Item-bbox, Zoomspanne aus der Registry | die AOI wird hier nicht gebraucht; sie kommt beim Zeichnen aus `store.aoi` |
| `mapLayers.ts::syncFocusRaster` → `addTiles` → `placeRaster` | je Szene eine MapLibre-`raster`-Quelle mit den Kacheln `/collections/{ds}/items/{id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=…`, eingefügt jeweils direkt unter `aoi-fill` | **die zuletzt eingefügte Szene liegt oben** (siehe Befund unten) |
| `mapLayers.ts::syncLayers` | angeheftete Layer im Layer-Manager, Overlays vom Typ `raster` mit `tileUrl`, AOI in `restore.aoi` | angeheftete Vollauflösungs-Layer sind heute ungeschnitten (F3 in §8) |
| `access/download.py::crop_asset` | `mosaic_reader` mit `FirstMethod`: **das erste Item der Anfrage gewinnt**; die Reihenfolge der Anfrage ist die der Auswahl (`selectionItemsFrom`), `filter_items_intersecting_aoi` erhält sie | maßgeblich für die Reihenfolge in der Ansicht |
| `access/download.py::parse_aoi_geometry` | nur `Polygon`/`MultiPolygon` gelten als AOI; Punkt und Linie werden abgewiesen | dieselbe Regel für den Zuschnitt der Ansicht |
| Maske im Download | rio-tiler 9.4.6 `Reader.feature` rastert die Geometrie mit `all_touched=True` in die Maske; in der Datei landet heute laut M3-18 trotzdem die Bounding Box | M3-18 macht die Datei zur Polygonmaske (§7) |

**Befund Reihenfolge.** Die Ansicht stapelt heute umgekehrt zum Download:
`syncFocusRaster` fügt die Szenen in Auswahlreihenfolge ein, jede neue direkt
unter der AOI-Linie, also über der vorigen. Oben liegt damit die **letzte**
Szene, im Download gewinnt die **erste**. Wo sich zwei Szenen überlappen, zeigt
die Karte heute also nicht das, was in der Datei steht. M3-09 behebt das mit:
die erste Szene wird zuoberst gezeichnet. Transparente Kachelpixel (nodata,
Maske des Readers) lassen die darunterliegende Szene durchscheinen — das ist
dieselbe Regel wie „erster gültiger Pixel“, weil Kacheln und Zuschnitt
dieselbe Maske aus demselben Reader bekommen.

---

## 3. Stand der Technik

| Quelle | Befund |
|---|---|
| MapLibre GL JS, Diskussion [#3237 „Add mask“](https://github.com/maplibre/maplibre-gl-js/discussions/3237) (2023–2025) | Maskieren eines `raster`-Layers per Polygon gibt es in MapLibre nicht. Ein Stencil-Beweis über `CustomLayerInterface` funktioniert nur in Mercator, nicht im Globus; ein inverses Füllpolygon verdeckt auch die Basiskarte. Der Maintainer rät, den Zuschnitt in der Quelle bzw. im Protokoll-Plugin (COG-Protokoll) zu machen, nicht im Kern |
| MapLibre-Diskussion [#5353](https://github.com/maplibre/maplibre-gl-js/discussions/5353) | Stencil-Maske über `CustomLayerInterface` stört die Layer darüber — der Weg ist fehleranfällig |
| Mapbox Style Spec, [`clip`-Layer](https://docs.mapbox.com/style-spec/reference/layers/) | Nur Mapbox GL JS v3, nicht MapLibre, und entfernt nur `model`- und `symbol`-Layer, keine Raster |
| Mapbox GL JS, [Issue #7018](https://github.com/mapbox/mapbox-gl-js/issues/7018) | dieselbe Anfrage („mask layer by GeoJSON“), dort ebenfalls nicht für Raster gelöst |
| MapLibre [`addProtocol`](https://maplibre.org/maplibre-gl-js/docs/API/functions/addProtocol/), im Quelltext 5.24.0 geprüft | Ein eigenes URL-Schema lädt Kacheln über eine eigene Funktion im Hauptthread. Für Rasterkacheln darf die Funktion **direkt ein `ImageBitmap`** zurückgeben (`doImageRequest`: „User using addProtocol can directly return HTMLImageElement/ImageBitmap“), es muss also nichts neu als PNG kodiert werden. Die offiziellen Beispiele (COG-Quelle, PMTiles) nutzen genau diesen Haken |
| Leaflet-Plugin [`leaflet-boundary-canvas`](https://github.com/aparshin/leaflet-boundary-canvas), ähnlich [`leaflet-tilelayer-clip`](https://github.com/frogcat/leaflet-tilelayer-clip) | Seit Jahren verbreitetes Muster: jede Kachel im Canvas auf ein Polygon zuschneiden. Anmerkung dort: Löcher brauchen beim Canvas-Füllen die Gegenrichtung (non-zero); mit `evenodd` entfällt das |
| TiTiler / rio-tiler (im Projekt, 9.4.6) | Zuschnitt auf ein Polygon nur als Bild (`/feature`, `/bbox`, POST mit GeoJSON), nicht für XYZ-Kacheln. Mosaik-IDs gibt es über registrierte Suchen (titiler-pgstac) — das wäre Serverzustand und Mosaik im Kachel-Pfad, beides nicht M3 (P11, `adr/0001`) |
| Prototyp F10 | Stufe 1 war ein georeferenziertes Bild aus einem zwischengelegten Zuschnitt-COG, Stufe 2 Kacheln daraus mit `aoi=<hash>` in der URL — beides Zustand (Z2, Z9 in `adr/0001`) und genau das, was die Randbedingungen ausschließen |

Offen blieb die OpenLayers-Seite „Layer Clipping“: `openlayers.org` ist in der
Umgebung gesperrt; sie wird für den Weg nicht gebraucht.

---

## 4. Wege

| | Weg | AOI verlässt Browser | Zustand | Vollauflösung beim Zoomen | Übereinstimmung mit Datei | Aufwand |
|---|---|---|---|---|---|---|
| **A** | **Jede Kachel im Browser maskieren** (`addProtocol`) | nein | keiner | ja, unverändert | Rand ±1 Pixel (§7) | nur Frontend |
| B | Georeferenziertes Bild aus dem Zuschnitt-Pfad per `POST` (wie F10 Stufe 1) | ja, im Rumpf | keiner | nein: ein Bild mit fester Auflösung (Deckel 4096 px) | pixelgleich (derselbe Code) | neuer `tiler`-Endpunkt mit Render-Parametern; jedes „Apply“ liest alles neu von der Quelle |
| C | AOI als Request-Header an jede Kachel (`transformRequest`), Maske im `tiler` | ja, bei jeder Kachel | keiner | ja | wie A | Backend und Frontend; Kacheln nicht mehr CDN-fähig (`Vary`), AOI geht hundertfach übers Netz |
| D | Stencil-Maske als `CustomLayerInterface` in WebGL | nein | keiner | ja | wie A | hoch; laut #3237 nur Mercator, nicht Globus (V-1 hat den Globus) |

**Empfehlung: A.** Einzig A erfüllt alle Randbedingungen zugleich: keine AOI in
Kachel-URLs oder Logs (sie geht gar nicht übers Netz), zustandslos, kein
Mosaik im Kachel-Pfad, nichts Datensatzspezifisches, volle Auflösung beim
Zoomen, Globus und flache Karte. Es ist Ausführungsstufe T0
(`architekturplan.md` 7.3: Darstellung im Browser, kein zitierfähiges
Ergebnis) — das zitierfähige Ergebnis bleibt die Datei aus dem Zuschnitt-Pfad.
B verliert die Vollauflösung, C schickt die AOI öfter übers Netz als heute, D
bricht den Globus.

Ein ADR halte ich für A nicht für nötig: Modulgrenzen, Backend und Kachel-URLs
bleiben unverändert. Die Entscheidung kommt als Zeile ins Log.

---

## 5. Umsetzung von Weg A

**Neues Modul `frontend/src/aoiClip.ts`**, rein und ohne MapLibre-Abhängigkeit
bis auf den Protokoll-Adapter:

1. **Registrierung.** `maplibregl.addProtocol('earthx-clip', …)` einmal beim
   Anlegen der Karte in `MapView.tsx`.
2. **URL ohne AOI.** Eine geschnittene Quelle bekommt statt der Kachel-Vorlage
   `earthx-clip://<clipKey>/{z}/{x}/{y}/<kodierte Original-Vorlage>`. `clipKey`
   ist ein Zähler, der bei jeder AOI-Änderung weiterzählt — keine Koordinate,
   kein Hash der Geometrie. Die AOI selbst liegt nur in einer Modulvariablen
   (`clipKey → Geometrie`). Die an `fetch` übergebene URL ist Zeichen für
   Zeichen die heutige Kachel-URL.
3. **Kachel einordnen, bevor geladen wird.** Aus `z/x/y` die Kachelgrenzen in
   Web-Mercator; AOI-Ringe einmal je AOI nach Mercator umgerechnet.
   - Kachel ganz außerhalb der AOI → leeres, transparentes `ImageBitmap`,
     **kein Request** (spart Anfragen an den `tiler` und an die Quelle).
   - Kachel ganz innerhalb → Kachel unverändert durchreichen, keine
     Pixelarbeit.
   - Kachel am Rand → laden, dekodieren (`createImageBitmap`), in ein
     `OffscreenCanvas` zeichnen, Maske anwenden, `ImageBitmap` zurück.
4. **Maske als reine Funktion.** Scanline mit Regel „gerade/ungerade“ über die
   Pixelmitten der 256×256-Kachel: je Zeile die Schnittpunkte mit allen
   Ringkanten, dazwischen füllen. Kosten Zeilen × Kanten, unabhängig von der
   Pixelzahl; Löcher und `MultiPolygon` ohne Sonderfall. Die Funktion gibt ein
   `Uint8Array` (256×256) zurück und ist damit ohne Canvas in Vitest prüfbar.
5. **Vorfilter über `bounds`.** Die Quelle bekommt als `bounds` den Schnitt aus
   Item-bbox und AOI-bbox; MapLibre fragt außerhalb gar nicht erst an.
6. **Abbruch und Fehler.** Der `AbortController` von MapLibre wird an `fetch`
   durchgereicht; ein HTTP-Fehler des `tiler` wird als Fehler weitergegeben,
   nicht als leere Kachel verschluckt (Prinzip 11: keine leere Karte ohne
   Meldung).
7. **Überzoom.** Oberhalb der höchsten freigegebenen Stufe vergrößert MapLibre
   die bereits maskierte Kachel; der Rand wird dann so grob wie die Daten
   selbst. Das bleibt so.

**Welche AOI zählt.** Nur `Polygon` und `MultiPolygon`, wie im Download. Ohne
AOI oder mit einer anderen Geometrie zeigt die Ansicht die ganze Szene wie
heute und der Knopf trägt die Beschriftung „ganze Szene“. Die Maske folgt der
aktuellen `store.aoi`; zeichnet der Nutzer in der Vollauflösung eine neue AOI,
zählt `clipKey` weiter und die Kacheln werden neu maskiert — wie der Download
aus der Auswahl, der ebenfalls die aktuelle AOI nimmt.

**Reihenfolge (§2, Befund).** `syncFocusRaster` zeichnet die Szenen so, dass
die erste der Auswahl oben liegt. Eine Hilfsfunktion `drawOrder(ids)` liefert
die Reihenfolge und wird in Vitest geprüft.

**Geänderte Dateien (Schätzung):** `aoiClip.ts` (neu, ~150 Zeilen),
`aoiClip.test.ts` (neu), `mapLayers.ts` (`placeRaster` mit optionaler AOI,
Reihenfolge), `MapView.tsx` (Registrierung, AOI an `syncFocusRaster`),
`ViewBar.tsx` (Beschriftung), bei F3 = 1 zusätzlich `layers.ts` und
`store.ts::addCurrentToLayers`. Unter 400 Zeilen ohne Tests. Kein Backend,
keine Registry, keine neuen Abhängigkeiten.

---

## 6. Beschriftung des Knopfs

Ein Knopf wie bisher (P12), die Beschriftung sagt, was kommt:

| Lage | Vorschlag | Tooltip |
|---|---|---|
| mit AOI | **View AOI at full resolution** | Show the selected scenes at full resolution, cut to your AOI |
| ohne AOI, eine Szene | **View scene at full resolution** | Show the whole scene at full resolution |
| ohne AOI, mehrere | **View scenes at full resolution** | Show the whole scenes at full resolution |

Alternativen in §8, F2.

---

## 7. Übereinstimmung mit der Datei — was genau gleich ist

- **Szenen und Reihenfolge:** gleich (erste Szene oben = erster gültiger Pixel).
- **Innen/außen:** gleich bis auf den Rand. Die Karte entscheidet je
  Kachelpixel nach der Pixelmitte in Web-Mercator; rio-tiler rastert im
  Zuschnitt mit `all_touched=True` im Raster der Ausgabe. Am Polygonrand kann
  die Karte daher um bis zu ein Pixel der Datei schmaler wirken. Genauer geht
  es nicht, weil Kachelraster und Datenraster verschieden sind.
- **Abhängigkeit M3-18:** Heute enthält die Datei beim Polygon-AOI noch die
  ganze Bounding Box; erst M3-18 maskiert sie auf das Polygon. Otto kann die
  Abnahme „Karte und Datei stimmen überein“ deshalb **mit einer Rechteck-AOI
  sofort**, mit einem schrägen Polygon erst nach dem Merge von M3-18 prüfen.
- **Nicht Teil von M3-09:** was heruntergeladen wird, wenn keine AOI da ist
  (P19, M3-17).

---

## 8. Fragen an Otto

**F1 — Weg.**
1. A: jede Kachel im Browser maskieren (§4, §5) — *Empfehlung*
2. B: ein georeferenziertes Bild aus dem Zuschnitt-Pfad per `POST`
3. C: AOI als Header an den `tiler`

**F2 — Beschriftung.**
1. „View AOI at full resolution“ / „View scene(s) at full resolution“ (§6) — *Empfehlung*
2. „View crop at full resolution“ / „View full scene“
3. „View full resolution“ unverändert, Unterschied nur im Tooltip

**F3 — Angeheftete Layer im Layer-Manager.** Ein aus der Vollauflösung
angehefteter Layer zeigt heute die ganze Szene, sein Download schneidet aber
auf `restore.aoi`.
1. Mit anschneiden: der Layer zeigt, was beim Anheften zu sehen war, mit
   seiner eigenen AOI — *Empfehlung*
2. Nicht in M3-09; eigene kleine Aufgabe später

---

## 9. Abnahme

- **Vitest** (`aoiClip.test.ts`, `mapLayers.test.ts`):
  - Maske: Rechteck, schräges Polygon, Polygon mit Loch, `MultiPolygon` mit
    zwei Teilen in einer Kachel, Kachel ganz innen, ganz außen, AOI über den
    Kachelrand; Pixelmitten auf der Kante.
  - Einordnung: außen → kein `fetch`; innen → Kachel unverändert; Rand →
    maskiert.
  - Fehlerfälle und zweckfremde Nutzung: `Point`, `LineString`, leere
    Geometrie, `null`, unbekannter `clipKey`, fehlerhafte `z/x/y` im URL,
    `fetch` mit 404/500 wird Fehler, Abbruch reicht bis `fetch` durch.
  - **Keine AOI in einer Kachel-URL:** Test mit einer AOI aus markanten
    Koordinaten; weder die Protokoll-URL noch die an `fetch` gegebene URL
    enthält eine davon, und die an `fetch` gegebene URL ist die heutige
    Kachel-URL.
  - Reihenfolge: erste Szene der Auswahl wird zuoberst gezeichnet.
  - Beschriftung des Knopfs in allen drei Lagen (`AppTopBar.test.tsx`).
- `npm run lint`, `npx tsc -b --pretty false`, `npx vitest run` grün.
- **Otto lokal:** AOI über zwei überlappende Szenen, „View AOI at full
  resolution“, dann Download; Karte und Datei stimmen überein (Rechteck sofort,
  Polygon nach M3-18, §7). Im Netzwerk-Tab des Browsers steht keine Koordinate
  in einer Kachel-URL.

Nach Freigabe: Entscheidung als Zeile ins `ENTSCHEIDUNGSLOG.md`, Status dieses
Plans auf „freigegeben“, Umsetzung im selben Branch und Draft-PR.
