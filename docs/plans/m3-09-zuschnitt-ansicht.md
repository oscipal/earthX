# M3-09 — Vollauflösung zeigt nur den Zuschnitt: Umsetzungsplan

**Aufgabe:** M3-09 aus `docs/plans/m3-dritte-quelle-und-interface.md` §4.
**Stufe B** — **von Otto am 24.09.2026 freigegeben**: F1 (1), F2 (eigener
Wortlaut „Crop to AOI“ / „View full selection“, unter einer gemeinsamen
„Full resolution“-Beschriftung), F3 (Download folgt der Ansicht, begrenzt auf
die eine ganze Szene, die F3 nennt — siehe §8). Der Plan-Schritt ist damit
abgeschlossen, die Umsetzung liegt in diesem Branch/PR; §5–§7 sind auf den
tatsächlichen Stand nachgezogen (**Fassung 2**).
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

## 5. Umsetzung von Weg A (Fassung 2: wie tatsächlich gebaut)

**Neues Modul `frontend/src/aoiClip.ts`.** Es importiert von `maplibre-gl`
bewusst **nur Typen** (`import type`, zur Bauzeit entfernt): `store.ts` und
`mapLayers.ts` brauchen daraus nur `clipTileUrl`, sind aber ihrerseits von
praktisch jeder Komponente importiert, und ein echter Wertimport von
`maplibre-gl` dort hätte die Bibliothek in jeden Test gezogen, der den Store
berührt — sie stürzt außerhalb eines echten Browser-Canvas ab (auch unter
jsdom, siehe Abnahme). Die Registrierung `addProtocol('earthx-clip',
aoiClipProtocol)` steht deshalb allein in `MapView.tsx`, das ohnehin schon
echten `maplibre-gl`-Code lädt und in genau den betroffenen Tests weggemockt
wird.

1. **Registrierung.** Einmal pro Seite (nicht pro Karten-Instanz), in
   `MapView.tsx` beim Modul-Import.
2. **URL ohne AOI.** `clipTileUrl(template, aoi)` liefert
   `earthx-clip://<key>/{z}/{x}/{y}/<template>` — `<template>` unverändert,
   nicht kodiert: MapLibre ersetzt `{z}/{x}/{y}` mit einer einzigen globalen
   Ersetzung über die ganze URL (`TileID.url`, Quelltext geprüft), trifft also
   beide Kopien gleich. `key` ist ein Zähler, vergeben über ein `WeakMap<AOI-
   Objekt, key>` — dieselbe AOI-Objektreferenz bekommt immer denselben
   Schlüssel (mehrere angeheftete Overlays aus einer Ansicht teilen sich
   einen Eintrag), eine neu gezeichnete AOI (`store.setAoi` legt ein neues
   Objekt an) einen eigenen, ohne dass der alte aktiv ausgetragen werden muss.
   Ohne AOI, oder wenn die Geometrie keine lesbare bbox hat, bleibt die
   Vorlage unverändert — kein Protokoll, keine Änderung an der Kachel-URL.
3. **Einordnen, bevor geladen wird.** Grober Ablehnungstest in Lon/Lat
   (AOI-bbox gegen Kachel-Lon/Lat-Grenzen aus der Standard-Slippy-Map-Formel):
   überschneiden sie sich nicht, liefert die Funktion ein transparentes
   1×1-`ImageBitmap` **ohne Request** — dieselbe Antwort, die der Server für
   Kacheln außerhalb des Footprints schon gibt (F10). Überschneiden sie sich,
   wird immer geladen und maskiert, auch wenn die Kachel eigentlich ganz
   innerhalb liegt — die vereinfachende Entscheidung gegen einen dritten Fall
   „ganz innen, ungemaskt“, weil ein overzoomter oder abgeschnittener
   Sonderfall dort mehr Fehlerfläche gekostet hätte als die eingesparte
   Canvas-Arbeit wert ist.
4. **Maske.** Kein Scanline-Code: Jeder Ring (Außenring und Löcher, über alle
   Polygone eines `MultiPolygon`) wird nach Web-Mercator-Metern projiziert und
   in Kachel-Pixel (0–256) umgerechnet, dann als ein gemeinsamer `Path2D` mit
   `ctx.clip(path, 'evenodd')` auf ein `OffscreenCanvas` angewandt, bevor das
   geladene Bild hineingezeichnet wird. `evenodd` macht die Windungsrichtung
   von Löchern gleichgültig (der Leaflet-Präzedenzfall in §3 muss das mit
   `nonzero` noch selbst sicherstellen). Die Projektion (`lonLatToMerc`,
   `tileLonLatBounds`/`tileMercBounds`, `ringsToTilePixels`) ist reine
   Mathematik ohne Canvas und ohne `maplibre-gl` und deshalb vollständig in
   Vitest geprüft; nur der Canvas-Teil selbst läuft ungetestet (Browser-API).
5. **Kein gesonderter `bounds`-Vorfilter mehr auf der Quelle.** Der Ablehnungstest
   in Schritt 3 übernimmt diese Rolle bereits pro Kachel; eine zusätzliche
   `bounds`-Einschränkung auf der MapLibre-Quelle hätte nichts beigetragen.
6. **Abbruch und Fehler.** `abortController.signal` geht an `fetch`; ein
   HTTP-Fehler des `tiler` oder eine unbekannte/verfallene AOI wird als
   `Error` weitergegeben statt als leere Kachel verschluckt.
7. **Überzoom.** Unverändert wie besprochen — MapLibre vergrößert die bereits
   maskierte Kachel oberhalb der höchsten freigegebenen Stufe.

**Reihenfolge (§2, Befund).** `mapLayers.ts::syncFocusRaster` zeichnet die
Einträge aus `downloaded` (Objekt-Einfügereihenfolge = Auswahlreihenfolge) in
umgekehrter Reihenfolge in die Karte, sodass die zuerst gewählte Szene zuletzt
eingefügt wird und damit (wie `placeRaster`/`beforeAoi` es für jede weitere
Ebene ohnehin tun) obenauf landet — passend zum `FirstMethod`-Mosaik des
Downloads.

**Wo geklippt wird.** Für die aktive Ansicht direkt in `syncFocusRaster`
(`clip = cropToAoi ? aoi : null`, live nachgeführt, auch wenn die AOI während
der Vollauflösung neu gezeichnet wird). Für einen angehefteten Layer wird der
Zuschnitt **beim Anheften einmal fest in die `tileUrl` gebacken**
(`store.ts::addCurrentToLayers`) statt später erneut entschieden — ein
angehefteter Layer behält damit den Zuschnitt, mit dem er angeheftet wurde,
auch wenn sich die aktuelle AOI danach ändert.

**Welche AOI zählt.** Nur `Polygon`/`MultiPolygon`, wie im Download — eine
andere Geometrie liefert keine lesbare bbox und bleibt damit automatisch
ungeklippt, ganz ohne eigene Fallunterscheidung.

**Geänderte Dateien:** `aoiClip.ts` + `aoiClip.test.ts` (neu), `mapLayers.ts`
(Klippen, Reihenfolge, neue Tests), `MapView.tsx` (Registrierung, `aoi`/
`cropToAoi` an `syncFocusRaster`/`syncMosaic`), `store.ts` (`cropToAoi`-Feld,
`enterFocus(cropToAoi)`, `addCurrentToLayers`, `selectLayer`), `layers.ts`
(`LayerRestore.cropToAoi`), `download.ts` + `download.test.ts`
(„Download folgt der Ansicht“, §8 F3), `ViewBar.tsx`, `ViewerControls.tsx`,
`AppTopBar.test.tsx`, `index.css`. Kein Backend, keine Registry, keine neuen
Abhängigkeiten.

---

## 6. Beschriftung des Knopfs (Otto, F2)

Aus einem Knopf wurden zwei, beide führen in dieselbe Vollauflösung — dafür
unter einer gemeinsamen Beschriftung „Full resolution“ gruppiert
(`ViewBar.tsx`, `role="group" aria-label="View full resolution"`), damit
sichtbar bleibt, dass es sich nicht um zwei verschiedene Funktionen handelt:

| Knopf | Wann aktiv | Tooltip |
|---|---|---|
| **Crop to AOI** | nur mit gezeichneter AOI | View the selected scene(s) at full resolution, cut to your AOI |
| **View full selection** | immer | View the whole selected scene(s) at full resolution, tiled straight from the source |

In der Vollauflösung selbst zeigt `ViewerControls`' Kopfzeile zusätzlich, in
welchem Modus die Ansicht gerade ist: „FULL-RESOLUTION VIEW · {Datensatz} ·
cropped to AOI“ bzw. „· whole selection“.

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
- **Download folgt der Ansicht (Otto, F3, 24.09.2026):** Der Download eines
  angehefteten Layers folgt dem, was beim Anheften sichtbar war, nicht mehr
  nur der zuletzt gezeichneten AOI. Bei „Crop to AOI“ unverändert (`restore.aoi`
  nötig). Bei „View full selection“ und **genau einer** ganzen Szene liefert
  der Download diese Szene, ohne AOI-Pflicht — über denselben Zuschnitt-
  Endpunkt, mit der Bounding Box der Szene selbst als „AOI“ (bei einer
  rechteckigen Szene faktisch kein echter Zuschnitt). Mehrere ganze Szenen
  gleichzeitig uncropped angeheftet bleiben ohne Download-Knopf: Otto nannte
  hier ausdrücklich „eine ganze Szene“ (Singular), und mehrere Originale
  einzeln, direkt von der Quelle statt gemergt über diesen Endpunkt, ist
  P19s eigener Punkt für **M3-17** — das wird hier nicht vorweggenommen.
- **Sonst nicht Teil von M3-09:** die COG-Direktweiterleitung ohne Umweg über
  die Plattform, und der ZIP-Download mehrerer ganzer Originale (M3-17, P19).

---

## 8. Fragen an Otto — beantwortet 24.09.2026

**F1 — Weg. Antwort: 1** (jede Kachel im Browser maskieren, §4/§5).

**F2 — Beschriftung. Antwort: eigener Wortlaut**, nicht einer der drei
Vorschläge: „Crop to AOI“ und „View full selection“, beide unter der
gemeinsamen Beschriftung „Full resolution“ gruppiert, damit deutlich bleibt,
dass beide zur Vollauflösung führen (§6).

**F3 — Angeheftete Layer im Layer-Manager.** Ursprünglich nach „mit AOI
anschneiden“ gefragt; Ottos Antwort geht weiter und macht daraus einen
allgemeinen Grundsatz: der Download lädt herunter, was sichtbar ist — zeigt
ein Layer eine ganze Szene ohne „Crop to AOI“, wird beim Download auch nicht
auf die AOI zugeschnitten. Umgesetzt für den Fall, den Otto nennt (eine ganze
Szene); mehrere ganze Szenen gleichzeitig bleiben M3-17 vorbehalten (§7).

---

## 9. Abnahme

- **Vitest** — neu in `aoiClip.test.ts` (23 Tests: URL-Wrapping/Parsing samt
  Rundreise durch eine simulierte MapLibre-Ersetzung, „keine AOI-Koordinate in
  der gewickelten URL“, Mercator-Projektion, Kachelgrenzen, bbox-Überschneidung,
  Ring-Projektion für Rechteck/Loch/`MultiPolygon`/außerhalb, Fehlerfälle wie
  falsches Schema, zu wenige Segmente, nicht-ganzzahlige z/x/y, fehlende innere
  URL) und ergänzt in `mapLayers.test.ts` (Reihenfolge, Klippen an/aus),
  `download.test.ts` (Download folgt der Ansicht, §7/§8 F3) und
  `AppTopBar.test.tsx` (beide Knöpfe, gemeinsame Gruppen-Beschriftung).
  **Ergebnis:** `npx vitest run` — 14 Testdateien, **251 grün**, 0 rot.
- `npm run lint` (oxlint): grün, keine Funde.
- `npx tsc -b --pretty false`: grün, keine Fehler.
- Backend unverändert; zur Kontrolle trotzdem ausgeführt: `ruff check backend`
  grün, `lint-imports --config .importlinter` 12/12 Verträge gehalten,
  `pytest` (Repo-Wurzel) **1113 passed**, keine neuen Warnungen.
- **Otto lokal (noch offen):** AOI über zwei überlappende Szenen, „Crop to
  AOI“, dann den Layer aus dem Layer-Manager herunterladen; Karte und Datei
  stimmen überein (mit einem Rechteck sofort prüfbar, mit einem schrägen
  Polygon erst nach M3-18, §7). Im Netzwerk-Tab des Browsers steht keine
  Koordinate in einer Kachel-URL.

Umgesetzt in diesem Branch/PR. Entscheidungslog-Zeile in
`ENTSCHEIDUNGSLOG.md`.
