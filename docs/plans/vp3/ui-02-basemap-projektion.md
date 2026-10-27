# UI-02 — Basemap-Auswahl und Projektion
 
**Stand:** 12.10.2026, beauftragt von Otto; ergänzt am 24.10.2026 (§3 Permalink); Plan mit Recherche am 27.10.2026 (§6), wartet auf Freigabe.
**Meilenstein:** UI, direkt nach M4 (nach M4-20).
**Stufe B mit Recherche:** Plan mit Quellen im Draft-PR, Otto gibt frei, dann Code.
**Modell:** Opus (Effort hoch) für Plan und Recherche, Sonnet (Effort hoch) für die Umsetzung.
**Start:** Nach M4-20. Läuft nicht gleichzeitig mit UI-01, weil beide die Kartenschalter berühren.
**Startsatz:** „Führe Aufgabe UI-02 aus `docs/plans/vp3/ui-02-basemap-projektion.md` aus.“
 
## 1. Wünsche von Otto (12.10.2026)
 
1. Der Button „Mercator“ oben rechts entfällt. Ein Basemap-Menü ersetzt ihn.
2. **Basemaps:**
   - Satellitenbild
   - Straßenkarte
   - nur Umrisse (Küsten, Grenzen)
   - weitere Vorschläge willkommen
3. **Projektionen** im selben Menü:
   - Mercator
   - Globus
   - Equal Earth, falls möglich
Vorschläge für weitere Ebenen, im Plan zu bewerten:
- Schummerung aus dem eigenen Copernicus DEM
- Beschriftungen ein- und ausblendbar
- Gradnetz
- Sentinel-2-Kachelraster (MGRS) als Overlay
- der heutige Schalter „Light“ und gegebenenfalls „Dark“, eingegliedert ins Menü
## 2. Recherche mit Quellen (Pflicht vor jeder Empfehlung)
 
1. **Anbieter je Basemap.** Für jeden Anbieter:
   - **Lizenz:** Ist kommerzielle Nutzung erlaubt? Das Repo ist AGPL, die Plattform kann später kommerziell betrieben werden. Viele Satelliten-Basemaps sind nur nichtkommerziell nutzbar.
   - **Nutzungsregeln:** zum Beispiel die Tile Usage Policy von OSM, die keine starke Nutzung erlaubt.
   - **Attribution**
   - **API-Schlüssel:** Keine Secrets im Repo. Anbieter ohne Schlüssel bevorzugen. Braucht ein Anbieter einen Schlüssel, ist das eine Frage an Otto.
   - **Selbst hosten:** etwa PMTiles oder Protomaps, mit Aufwand und Speicherbedarf.
2. **Datenschutz.** Basemap-Kacheln lädt der Browser direkt bei Dritten. Die Regel „ausgehende Requests nur über `gateway`“ gilt für das Backend. Klären:
   - ob ein Hinweis für die Nutzer nötig ist,
   - ob ein Weg über die eigene Plattform sinnvoll wäre.
3. **Projektionen.**
   - Welche Projektionen kann die Kartenbibliothek des Frontends (Version im Lockfile)? Globus und Mercator wahrscheinlich ja.
   - Equal Earth: Geht das mit Kachelkarten überhaupt? Mit welchem Aufwand, etwa Wechsel der Bibliothek oder Reprojektion im Browser?
   - Was passiert mit den eigenen Ebenen (Kacheln aus dem Tiler, AOI-Zeichnung, Footprints, Coverage-Map) in jeder Projektion?
   - Am Code prüfen, nicht annehmen.
4. **Schummerung aus dem DEM.**
   - Geht das über den vorhandenen Tiler?
   - Wie steht es um die Regeln für `expression` und Algorithmen (`DefaultRender`, R5 aus M4-09)?
   - Was kostet es?
## 3. Im Plan mit Optionen und Empfehlung
 
- Auswahl der Basemaps und Anbieter, mit einer Tabelle zu Lizenz, Nutzungsregeln, Schlüssel und Attribution.
- Welche Projektionen jetzt kommen, welche später und welche nicht.
- Aufbau des Menüs (Englisch) und die Vorgabe beim ersten Start.
- Wird die Wahl des Nutzers im Browser gemerkt?
- **Permalink (aus M4-19e, 24.10.2026):** Der Permalink speichert heute keine Basemap, weil es nur eine gibt. Mit der Auswahl kommen Basemap und Projektion in den gespeicherten Zustand des Permalinks; ältere Permalinks ohne diese Felder öffnen mit der Vorgabe.
## 4. Grenzen
 
- Keine Secrets im Repo. Keine neue Abhängigkeit ohne Frage an Otto.
- Oberflächentexte nur auf Englisch.
- Attribution immer sichtbar, wie es die Lizenz verlangt.
- Backend nur, falls die Schummerung es braucht, und dann im Plan begründet.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.
## 5. Abnahme
 
- Für jede Basemap und Projektion gibt es einen Test, dass die Auswahl greift und die Attribution stimmt.
- Die eigenen Ebenen bleiben in jeder angebotenen Projektion lagerichtig, belegt mit einem Test oder einer Prüfanleitung.
- Alle vier Pflicht-Checks der CI sind grün.
- Prüfanleitung für Otto (Browser).
- Log-Zeilen.
- Vor „fertig“ ist main geholt.

## 6. Plan (27.10.2026, zur Freigabe durch Otto)

Stufe B: Bis zur Freigabe ist kein Produktivcode geändert. Grundlage ist `main` nach #209 (UI-01g gemergt, kein offener UI-PR). Belegstufen wie in `adr/0014`: [P] Code oder Primärquelle gelesen, [M] in der Sitzung gemessen bzw. mit einem Wegwerf-Test nachgestellt (nicht im Repo), [S] nur Zusammenfassung einer Websuche (Originalseite nicht abrufbar, vor einer Entscheidung gegenzuprüfen), [A] eigene Ableitung.

**Zur Quellenlage:** Das Netz der Cloud-Sitzung ließ nur `github.com` und `raw.githubusercontent.com` durch. Seiten von Esri, OSMF, CARTO, EOX, OpenFreeMap, Gerichten und Behörden waren nur als Suchtreffer erreichbar und tragen deshalb [S]. Lizenzfragen entscheidet Otto (CLAUDE.md); alles hier ist Vorschlag.

### 6.0 Kurzfassung

- **Menü:** Ein Knopf „🗺 Map“ oben rechts ersetzt „Mercator/Globe“ und „Light/Dark“. Er öffnet ein Menü mit vier Gruppen: Basemap, Overlays, Projection, Interface (§6.5).
- **Basemaps jetzt:** Satellite (Esri World Imagery wie heute), Streets (OpenFreeMap Liberty), Grey (OpenFreeMap Positron), Outlines (Küsten und Grenzen aus denselben Vektorkacheln). Kein Schlüssel, keine neue Abhängigkeit (§6.2, §6.4).
- **Overlays jetzt:** Labels (ein/aus, auch über dem Satellitenbild) und Graticule (im Browser erzeugt). **Später:** Schummerung aus dem eigenen DEM (braucht Backend), Sentinel-2-Kachelraster (Lizenz und Datei ungeklärt).
- **Projektionen:** Mercator und Globus jetzt. **Equal Earth nicht:** MapLibre GL JS 5.24 kennt nur `mercator`, `globe` und `vertical-perspective` [P]. Es ginge nur mit einem Wechsel der Kartenbibliothek.
- **Befund Globus [M]:** Mit MapLibres eingebautem Globus liegen eigene Rasterkacheln und GeoJSON bei Zoom 8 bis 11,5 bis zu rund 20 px neben der Stelle, an die `map.project` sie rechnet. Geht der Globus schon bei Zoom 6–7 in Mercator über, liegt alles pixelgleich wie in Mercator. Empfehlung: diesen Übergang setzen (§6.3, Frage 5).
- **Gemerkt** wird die Wahl im Browser (`localStorage`, wie heute Thema und Projektion). **Permalink:** Basemap und Projektion kommen in die gespeicherte Ansicht; das braucht eine kleine Änderung am Modell im Backend (§6.6).
- **Esri ohne Schlüssel** ist für einen kommerziellen Betrieb nicht belegbar zulässig [S]. Für die heutige, nicht kommerzielle Phase bleibt es; vor dem kommerziellen Start muss es ersetzt oder lizenziert werden (Frage 1).
- **Attribution:** heute beim Start eingeklappt (V-7). Die OSMF-Richtlinie verlangt Sichtbarkeit ohne Interaktion [S]. Empfehlung: immer ausgeklappt (Frage 4).
- **Datenschutz:** Die Kacheln lädt der Browser bei Dritten; dabei gehen IP-Adresse und Kartenausschnitt dorthin. Empfehlung: jetzt Hinweis im Tooltip je Basemap, vor dem kommerziellen Start Selbst-Hosting der Vektorkacheln (Frage 9).
- **Schnitt:** drei PRs UI-02a bis UI-02c (§6.9). **Fragen an Otto:** 10 (§6.10).

### 6.1 Stand im Code [P]

- **Basiskarte:** `frontend/src/mapStyles.ts` baut einen einzigen Stil mit einer Rasterquelle `satellite` (Esri World Imagery, `server.arcgisonline.com`, ohne Schlüssel, `maxzoom: 19`, Attribution „Imagery © Esri, Maxar, Earthstar Geographics, and the GIS User Community“) über einer `background`-Ebene in der Themenfarbe `--map-bg`; dazu `sky` für den Globus.
- **Schalter:** `App.tsx` hat oben rechts „⤢ Zoom to selection“, „🌐 Globe/🗺 Mercator“ (`toggleProjection`) und „☀ Light/☾ Dark“ (`toggleTheme`). Beide Wahlen liegen in `store.ts` und über `preferences.ts` im `localStorage` (`earthx.projection`, `earthx.theme`). Tests: `AppTopBar.test.tsx` (Beschriftung nach dem Ziel des Klicks), `preferences.test.ts`, `mapStyles.test.ts`.
- **Projektion:** `MapView.tsx` ruft `map.setProjection({ type: 'mercator' | 'globe' })` in `style.load` und in einem Effekt auf den Store-Wert.
- **Stilwechsel:** Der Stil wird heute nie getauscht. `onStyleLoad` legt bei jedem `style.load` alle eigenen Quellen und Ebenen neu an (AOI, Coverage, Quicklooks, Mosaik, angeheftete Layer, Ergebnisse, Vorschau, Terra Draw).
- **Eigene Ebenen:** nur `raster` (Kacheln aus dem Tiler im Raster `WebMercatorQuad`, `api.ts`; Bild-Overlays als `image`-Quelle mit vier Ecken, `mapLayers.ts`), `fill`, `line` und `background`. Kein `symbol`, also brauchen die eigenen Ebenen heute keine Glyphen.
- **Zeichnen:** Terra Draw 1.32 mit `terra-draw-maplibre-gl-adapter` 1.4.1; der Adapter rechnet über `map.project`/`map.unproject` und folgt damit der Projektion der Karte.
- **Attribution:** `attributionControl: { compact: true }`, nach dem Erzeugen sofort eingeklappt (V-7, Otto 23.09.2026).
- **Permalink:** `permalink.ts` (`PermalinkView`: `center`, `zoom`, `range`), im Backend `api/processing_route.py::PermalinkView` mit `extra="forbid"` und `strict=True`. Ein unbekanntes Feld wird dort mit `422` abgewiesen.
- **Tiler:** `expression`, `algorithm` und `algorithm_params` werden auf jeder Route mit `400` abgewiesen (`api/tiler.py::_refuse_free_parameters`, M4-09 F3); Rechnen nur über registrierte Operatoren (`op=…`). Die Mosaikkachel (M4-17) nimmt 2 bis 64 Items ab Zoom 8.
- **Keine CSP** im Repo, die neue Kachel-Hosts sperren würde.

### 6.2 Recherche: Anbieter

| Anbieter | Typ | kommerziell | Regeln, Limits | Schlüssel | Attribution | Selbst hosten |
|---|---|---|---|---|---|---|
| Esri World Imagery, ohne Schlüssel (heute) | Raster | nicht belegt; ein Esri-Community-Beitrag sagt „nicht ohne Lizenz“ [S] | Export/Offline nicht vorgesehen [S] | offiziell Konto bei ArcGIS Location Platform nötig [S] | „Powered by Esri“ + Datenquellen; genauer Wortlaut nicht belegt [S] | nein |
| Esri über ArcGIS Location Platform | Raster/Vektor | ja, im Abo enthalten [S] | 2 Mio. Kacheln/Monat frei, dann 0,15 USD je 1000 [S] | ja (Frage an Otto) | wie oben | nein |
| EOX Sentinel-2 cloudless 2016 | Raster | ja, CC BY 4.0 [S] | Kachelserver laut EOX frei für nicht-kommerzielle Anwendungen [S] | nein | „Sentinel-2 cloudless – https://s2maps.eu by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2016)“ [S] | Originalkacheln ladbar, Größe unbekannt [S] |
| EOX Sentinel-2 cloudless 2018 und später | Raster | nein, CC BY-NC-SA 4.0; kommerziell nur mit EOX-Lizenz [S] | wie oben | nein | wie oben | – |
| OpenStreetMap `tile.openstreetmap.org` | Raster | nicht geregelt; Zugang jederzeit sperrbar, kein „heavy use“ [S] | User-Agent und Referer Pflicht, kein Vorabladen [S] | nein | „© OpenStreetMap contributors“, sichtbar ohne Interaktion [S] | – |
| CARTO (Positron, Dark Matter, Voyager) | Raster/Vektor | bis 1 Mio. Kacheln/Monat frei, dann 500 USD/Monat; FAQ widerspricht [P README][S] | widerruflich | ja (seit 2026) [P] | „© OpenStreetMap contributors, © CARTO“ [P] | nein |
| **OpenFreeMap** (Liberty, Bright, Positron) | Vektor | Bedingungen schweigen; Code MIT, Stil-Design CC BY 4.0, Daten ODbL [P] | „keine Limits“, kein SLA, Dienst kann enden [P] | nein [P] | kommt aus dem Stil: „OpenFreeMap © OpenMapTiles Data from OpenStreetMap“ [P] | ja, Planet ~170 GB, Server ~200 GB [P] |
| VersaTiles | Vektor | Bedingungen schweigen [P] | Rate-Limit je IP (`429`), keine Garantie, CDN empfohlen [P] | nein [P] | OSM (+ ESA WorldCover beim Tileset `osm`) [P] | ja, 62–64 GB [P] |
| Protomaps (PMTiles) | Vektor | ja, Daten ODbL, Design CC0 [P] | Hotlinking der Builds unerwünscht [P] | nur die gehostete API [S] | „© OpenStreetMap“ [P] | ja, Planet ~120 GB; braucht im Browser das Paket `pmtiles` (neue Abhängigkeit) [P] |
| Stadia/Stamen, MapTiler | Raster/Vektor | nur bezahlt (ab 20 bzw. 30 USD/Monat) [S] | Freikontingent nur nicht-kommerziell [S] | ja | Pflicht | nein |
| Natural Earth | Vektordaten | ja, Public Domain [P] | – | nein | nicht verlangt | Dateien: Küste 50m 1,6 MB, Grenzen 50m 0,7 MB, 10m bis 12,7 MB [P] |
| Mapterhorn, AWS Terrain Tiles (Gelände) | Raster-DEM | ungeklärt [P] | AWS: Buckets „für EC2 gedacht“ [P] | nein | Quellenliste [P] | ja (PMTiles bzw. Bucket) |

Quellen (Auswahl, alle abgerufen oder gesucht am 27.10.2026):
[OpenFreeMap README](https://github.com/hyperknot/openfreemap), [OpenFreeMap ToS](https://raw.githubusercontent.com/hyperknot/openfreemap/main/website/content/policies/tos.md), [OpenFreeMap Selbst-Hosting](https://github.com/hyperknot/openfreemap/blob/main/docs/self_hosting.md),
[VersaTiles-Server](https://raw.githubusercontent.com/versatiles-org/versatiles-documentation/main/guides/use_tiles_versatiles_org.md), [VersaTiles-Tilesets](https://raw.githubusercontent.com/versatiles-org/versatiles-documentation/main/basics/tilesets.md),
[Protomaps Downloads](https://raw.githubusercontent.com/protomaps/docs/main/basemaps/downloads.md), [PMTiles in MapLibre](https://raw.githubusercontent.com/protomaps/docs/main/pmtiles/maplibre.md),
[CARTO basemap-styles README](https://raw.githubusercontent.com/CartoDB/basemap-styles/master/README.md), [CARTO Basemap Terms](https://carto.com/legal/basemap-terms/) [S],
[Natural Earth Lizenz](https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/LICENSE.md), [Natural Earth GeoJSON](https://github.com/nvkelso/natural-earth-vector/tree/master/geojson),
[OSM Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/) [S], [OSMF Attribution Guidelines](https://osmfoundation.org/wiki/Licence/Attribution_Guidelines) [S],
[Esri Community: World Imagery](https://community.esri.com/t5/arcgis-location-platform-developers-ques/inquiry-about-world-imagery/td-p/1569266) [S], [ArcGIS Static Basemap Tiles](https://developers.arcgis.com/rest/static-basemap-tiles/) [S], [Location Platform Preise](https://location.arcgis.com/pricing/) [S], [Esri-Attribution](https://developers.arcgis.com/documentation/esri-and-data-attribution/) [S],
[EOX Lizenz](https://cloudless.eox.at/documentation/license) [S], [EOX 2022](https://eox.at/2023/10/sentinel-2-cloudless-2022/) [S],
[Stadia Preise](https://stadiamaps.com/pricing/) [S], [MapTiler Cloud-Terms](https://www.maptiler.com/terms/cloud/) [S],
[Mapterhorn](https://github.com/mapterhorn/mapterhorn), [AWS Terrain Tiles](https://raw.githubusercontent.com/awslabs/open-data-registry/main/datasets/terrain-tiles.yaml), [Joerd: Nutzung](https://raw.githubusercontent.com/tilezen/joerd/master/docs/use-service.md).

**Folgerungen [A]:**

- **Satellit:** Es gibt keinen Anbieter, der ohne Schlüssel und eindeutig kommerziell nutzbar ist. EOX 2016 ist offen lizenziert, aber zehn Jahre alt, mit 10 m Auflösung, und der EOX-Kachelserver ist nur für nicht-kommerzielle Anwendungen frei; kommerziell müsste man die Kacheln selbst hosten. Esri über Location Platform ist sauber, braucht aber Konto und Schlüssel.
- **Straße und Grau:** OpenFreeMap passt am besten: kein Schlüssel, keine Limits, Stile fertig, MapLibre setzt die Attribution selbst. Risiken: kein SLA, und die Bedingungen schweigen zur kommerziellen Nutzung. Ausweg ist derselbe Datenstand selbst gehostet (~200 GB), ohne neue Abhängigkeit im Browser, weil OpenFreeMap normale z/x/y-Kacheln ausliefert. `tile.openstreetmap.org` scheidet für eine Plattform aus.
- **Umrisse:** Zwei Wege. (a) Aus denselben Vektorkacheln nur die Ebenen für Wasserlinien und Grenzen zeigen: genau in jedem Zoom, aber Dritter. (b) Natural Earth lokal im Frontend: kein Dritter, aber im Maßstab 1:50 Mio. Bei Zoom 10 und mehr, wo man AOIs zeichnet, liegen die Linien Kilometer daneben. Dazu kommt die Frage der Sichtweise bei umstrittenen Grenzen (Natural Earth hat eigene Dateien je Land, OSM folgt der Lage vor Ort).

### 6.3 Recherche: Projektionen

**Was MapLibre 5.24 kann [P].** Version laut `frontend/package-lock.json`: `maplibre-gl` 5.24.0. `src/geo/projection/projection_factory.ts` kennt genau `mercator`, `globe` und `vertical-perspective`; jeder andere Name fällt mit einer Warnung auf Mercator zurück. `globe` ist dort selbst ein Ausdruck: `vertical-perspective` bis Zoom 11, ab Zoom 12 `mercator`. Ein eigener Ausdruck mit anderen Stufen ist erlaubt (`ProjectionSpecification`, Array-Zweig in der Fabrik). Alle Zeichenwege (`draw_raster`, `draw_fill`, `draw_line`, `draw_symbol`, `draw_heatmap`, `draw_hillshade`) haben einen Globus-Zweig.

**Equal Earth [P][A].** Nicht in MapLibre GL JS. Wege wären: (a) Wechsel auf eine Bibliothek, die Rasterkacheln im Browser umprojiziert (etwa OpenLayers mit proj4). Das heißt `MapView.tsx`, `mapLayers.ts`, `aoiClip.ts` und das Zeichnen neu zu schreiben, dazu neue Abhängigkeiten. (b) Eine zweite, statische Übersichtskarte (etwa mit d3-geo) neben der Karte, ohne Kacheln aus dem Tiler und ohne Zeichnen; auch das ist eine neue Abhängigkeit. Empfehlung: **nicht anbieten**; neu prüfen, wenn MapLibre weitere Projektionen bekommt.

**Eigene Ebenen in jeder Projektion [M].** Wegwerf-Test im Chromium der Sitzung (Software-Rendering SwiftShader, 800×600 px), mit MapLibre aus `node_modules` und drei synthetischen Flächen bei 55–70° N: Rasterkacheln im Raster `WebMercatorQuad`, im Browser erzeugt wie die Kacheln des Tilers; ein Bild als `image`-Quelle mit vier Ecken wie die Quicklook-Overlays; ein GeoJSON-Polygon wie AOI und Footprints. Gemessen wurde an jeder Ecke der Abstand zwischen dem Punkt aus `map.project` und dem ersten gemalten Pixel (Terra Draw und Klicks rechnen über `map.project`/`unproject`).

| Projektion | Zoom 3–7 | Zoom 8–11,5 | ab Zoom 12 |
|---|---|---|---|
| Mercator | alle drei 0–2 px (Kantenglättung) | 0–2 px | 0–2 px |
| `globe` (MapLibre-Vorgabe) | Kacheln bis 5 px, Bild und GeoJSON 0–2 px | Kacheln bis 24 px, GeoJSON bis 16 px daneben | 0–2 px |
| Globus mit Übergang Zoom 6 → 7 auf Mercator | 0–2 px | 0–2 px | 0–2 px |

Folgerungen: In Mercator liegen alle eigenen Ebenen exakt. Der eingebaute Globus hat im Übergangsbereich bis Zoom 11,5 einen Versatz zwischen Gemaltem und `map.project`; das betrifft das Zeichnen der AOI und den Klick auf eine Szene genau in den Zoomstufen, in denen man arbeitet. Ob ein echter Grafikprozessor dasselbe zeigt, prüft die Anleitung (§6.8). Empfehlung (Frage 5): Globus als `['interpolate', ['linear'], ['zoom'], 6, 'vertical-perspective', 7, 'mercator']`. Der Globus bleibt für die Übersicht bis Zoom 6; darüber ist er ohnehin kaum von Mercator zu unterscheiden.

**Weitere Folgen des Globus [P].** `map.getBounds()` ist im Globus eine Näherung aus acht Randpunkten und setzt bei sichtbarem Pol die volle Länge (`vertical_perspective_transform.ts`). Das nutzt die Coverage-Abfrage ohne AOI (`MapView.tsx::reportViewport`); bei einem ganz sichtbaren Globus wird die Abfrage damit weltweit, was sie heute bei Zoom 1,6 in Mercator auch ist. Kein Handlungsbedarf, Prüfpunkt in §6.8.

### 6.4 Recherche: Schummerung aus dem eigenen DEM [P][A]

- **Über den Tiler heute nicht:** `algorithm=hillshade` von TiTiler wird mit `400` abgewiesen (M4-09 F3). Es bräuchte einen neuen Operator in der Registry (`adr/0014`), etwa `hillshade` oder eine Ausgabe als Terrarium für die `hillshade`-Ebene von MapLibre. R5 betrifft nur `expression`; `DefaultRender` nimmt seit M4-13 `op`, `op_version`, `params`, das wäre der Weg für eine Standarddarstellung.
- **Als Basemap nicht tragbar:** Das DEM liegt als 1°×1°-Kacheln vor. Eine Kachel bei Zoom 3 überdeckt rund 45°×45°, also bis zu 2000 COGs; die Mosaikkachel nimmt höchstens 64 Items und erst ab Zoom 8. Jede Kachel liest live über `gateway` aus dem AWS-Bucket; reine `visual`-Kacheln brauchten vor #197 2,6–4,2 s (Backlog Punkt 26).
- **Was es kosten würde:** eine vorab gerechnete Pyramide (Terrarium oder fertige Schummerung) im eigenen Objektspeicher. VersaTiles nennt für ein globales Terrarium bis Zoom 12 407 GB, für eine Schummerung als Vektor bis Zoom 12 105 GB [P]. Dazu Rechenzeit über alle Kacheln des DEM (rund 26 000 [A]). Das ist Backend, Speicher und Betrieb.
- **Empfehlung:** nicht in UI-02. Als eigener Backlog-Punkt (Stufe B, Backend) mit Plan zu Operator, Vorabrechnung und Speicher. Fremde Geländekacheln (Mapterhorn, AWS) erst nach Klärung ihrer Bedingungen.

### 6.5 Menü (Oberfläche englisch)

Ein Knopf oben rechts neben „⤢ Zoom to selection“: **„🗺 Map“**, Tooltip „Basemap, overlays and projection“. Er öffnet ein Menü über die vorhandene `Popover`-Komponente (Tastatur, `Esc`, Klick daneben schließt). Inhalt:

- **Basemap** (eine Wahl): `Satellite` · `Streets` · `Grey` · `Outlines`. Tooltip je Eintrag mit Quelle und Hinweis, woher die Kacheln kommen, etwa „Esri World Imagery. Tiles load from arcgisonline.com.“
- **Overlays** (an/aus): `Labels` · `Graticule`.
- **Projection** (eine Wahl): `Mercator` · `Globe`.
- **Interface** (eine Wahl): `Dark` · `Light` (heute „☀ Light/☾ Dark“, Frage 6).

„Grey“ statt „Light“, damit es sich nicht mit dem Thema „Light“ verwechselt. Alle Einträge sind immer wählbar; Labels gibt es auf jeder Basemap. Damit gibt es nichts auszublenden oder zu sperren (Regel vom 26.10.2026).

**Vorgabe beim ersten Start:** Satellite, Mercator, Labels aus, Graticule aus, Dark. Das ist der heutige Stand.

**Umsetzung [A], keine neue Abhängigkeit:**

- Ein Katalog `frontend/src/basemaps.ts`: je Basemap Id, Name, Tooltip und der Weg zu ihrem Stil (Raster-Definition für Satellite, Stil-URL bei OpenFreeMap für die anderen, bei Outlines mit einer festen Liste der zu zeigenden Ebenen).
- **Wechsel ohne Neuaufbau der eigenen Ebenen:** `map.setStyle(next, { diff: true, transformStyle })`. `transformStyle` nimmt den Stil der Basemap und hängt alle eigenen Quellen und Ebenen des bisherigen Stils unverändert an; Basemap-Ebenen tragen das Präfix `bm-`. MapLibre wendet dann nur die Differenz an, auch Glyphen und Sprite (`Map.setStyle` geht mit `diff` über `Style.setState`, das zuerst `transformStyle` anwendet und dann nur die Differenz ausführt; `setGlyphs` und `setSprite` gehören zu den Diff-Befehlen, `style/style.ts`, `style-spec/src/diff.ts`) [P]. So verschwindet beim Wechsel kein eigenes Bild (Vorgabe „Bild verschwindet nie“, UI-01a). Fällt MapLibre doch auf einen vollen Neuaufbau zurück, greift das bestehende `onStyleLoad`. Ob der Diff wirklich greift, prüft ein Test in UI-02a.
- **Labels:** die `symbol`-Ebenen der Basemap; über dem Satellitenbild die Beschriftungen aus dem Positron-Stil. Lage über den eigenen Bildern, unter AOI-Linie und Zeichnung (Frage 7).
- **Graticule:** im Browser erzeugtes GeoJSON, Linien alle 30° (Zoom < 3), 10° (< 6), 5° (< 8) und 1° darüber; ohne Gradzahlen, weil eine Beschriftung Glyphen eines Dritten bräuchte.
- **Hintergrund und Globus-Himmel** bleiben die Themenfarbe (`--map-bg`, `applyMapBackground`).

### 6.6 Merken und Permalink

- **Im Browser:** ja, wie heute in `preferences.ts`: `earthx.basemap`, `earthx.overlays` (neu), `earthx.projection`, `earthx.theme` (wie bisher). Unbekannte oder fehlende Werte fallen still auf die Vorgabe.
- **Permalink:** Die Ansicht bekommt zwei Felder, `basemap` (`satellite` | `streets` | `grey` | `outlines`) und `projection` (`mercator` | `globe`). Overlays und Thema kommen nicht hinein (Vorschlag: Sie sind Geschmack des Betrachters).
- **Backend:** `PermalinkView` in `api/processing_route.py` bekommt beide Felder als optionale Aufzählung (Vorgabe `None`). Begründung für die Backend-Änderung: Das Modell weist unbekannte Felder mit `422` ab (`extra="forbid"`), ohne die Änderung könnte das Frontend die Felder nicht speichern. Gespeicherte Permalinks bleiben gültig.
- **Ältere Permalinks** ohne die Felder öffnen mit der Vorgabe: Satellite und Mercator, unabhängig von der gemerkten Wahl. `permalink.ts::parseView` liest fehlende Felder als Vorgabe und weist unbekannte Werte ab wie heute.
- **Beim Öffnen** setzt der Permalink Basemap und Projektion wie eine eigene Wahl, die dann auch gemerkt wird (Frage 8).

### 6.7 Attribution und Datenschutz

**Attribution.**

- Heute ist sie beim Start eingeklappt (V-7). Die OSMF-Richtlinie von 2021 verlangt, dass man nicht mit der Karte interagieren muss, um die Attribution zu sehen [S]. Für Streets, Grey und Outlines (OSM-Daten) wäre das Einklappen damit nicht konform.
- Empfehlung (Frage 4): `compact: false`, immer offen, klein gesetzt in der Ecke unten rechts.
- Den Text liefert die jeweilige Quelle (MapLibre zeigt die Attribution der sichtbaren Quellen). Bei Esri kommt „Powered by Esri“ dazu; der genaue Wortlaut ist vor dem kommerziellen Start an der Esri-Seite zu prüfen.

**Datenschutz [S][A].**

- **Was geht an Dritte:** IP-Adresse, User-Agent, Referer und die Kachelkoordinaten, also grob, wohin der Nutzer schaut.
- **Die Regel „nur über `gateway`“** gilt für das Backend, nicht für den Browser.
- **Rechtslage:** Zu Kartenkacheln fand die Recherche keine Rechtsprechung ([eRecht24](https://www.e-recht24.de/dsg/12709-openstreetmaps.html) [S]). Die Begründung des LG München I zu Google Fonts (20.01.2022, 3 O 17493/20: dynamische IP personenbezogen; kein berechtigtes Interesse, weil selbst hostbar) ist übertragbar ([gesetze-bayern.de](https://www.gesetze-bayern.de/Content/Document/Y-300-Z-GRURRS-B-2022-N-612?view=Print) [S]). Die DSK-Orientierungshilfe Telemedien sieht die Weitergabe der IP an Dritte in der Regel nicht durch Art. 6 Abs. 1 lit. f gedeckt ([DSK 2022](https://www.datenschutzkonferenz-online.de/media/oh/20221130_OH_Telemedien_Version_1.1.pdf) [S]). Die Vorlage des BGH an den EuGH zur Personenbezogenheit dynamischer IPs ist offen (VI ZR 258/24 [S]).
- **Optionen:**
  1. Hinweis in Tooltip und Datenschutzerklärung.
  2. Wie 1, dazu eine Vorgabe ohne US-Anbieter.
  3. Selbst-Hosting der Vektorkacheln (~200 GB) oder Proxy.
- **Bewertung:** Ein Proxy wäre ein ausgehender Backend-Pfad über `gateway` mit eigenem Verkehr; die OSM-Policy rät davon ab [S]. Satellitenbilder lassen sich weder so noch durch Selbst-Hosting ohne passende Lizenz abdecken.
- **Empfehlung (Frage 9):** jetzt Option 1, weil die Plattform noch nicht öffentlich läuft. Selbst-Hosting als Backlog-Punkt mit der Bedingung „vor dem öffentlichen oder kommerziellen Start“. Rechtliche Prüfung durch Otto bzw. einen Anwalt.

### 6.8 Tests, Prüfanleitung, Abnahme

**Vitest (in CI, ohne Netz, Stil-Fixtures synthetisch unter `frontend/src/fixtures`):**

- Je Basemap: Die Wahl im Menü setzt den Store, landet im `localStorage` und ergibt einen Stil mit der erwarteten Quelle und genau der erwarteten Attribution.
- Je Projektion: Die Wahl ergibt die erwartete `ProjectionSpecification` (Globus mit Übergang).
- Beim Wechsel der Basemap bleiben alle eigenen Quellen und Ebenen in Reihenfolge erhalten (`transformStyle`), Basemap-Ebenen liegen unter ihnen, Labels nach Frage 7.
- Fehlerfälle: unbekannter Wert im `localStorage`; gesperrter Speicher; Stil-Fixture ohne erwartete Ebenen (Outlines zeigt dann nur den Hintergrund, kein Absturz); Permalink mit unbekannter Basemap (abgewiesen), ohne Felder (Vorgabe), mit Feldern (übernommen).
- Menü: Tastaturbedienung, `aria-checked`, `Esc`; „Mercator/Globe“ und „Light/Dark“ sind nicht mehr oben rechts (Gegenprobe zu `AppTopBar.test.tsx`).

**Pytest:** `PermalinkView` nimmt beide Felder an und lässt sie weg, weist unbekannte Werte und Fremdtypen ab (`strict`); ein gespeichertes Dokument ohne die Felder liest sich weiter.

**Lagerichtigkeit:** Ein Pixeltest wie der Wegwerf-Test in §6.3 bräuchte `@playwright/test` als neue Abhängigkeit. Empfehlung (Frage 10): Prüfanleitung statt Pixeltest in CI; der Wegwerf-Test wird im PR als Skript-Text beschrieben, nicht eingecheckt.

**Prüfanleitung für Otto (Browser, Kurzfassung, die volle Fassung kommt mit UI-02a):**

1. Erster Start mit leerem Speicher: Satellite, Mercator, Dark. Attribution unten rechts sichtbar.
2. Jede Basemap wählen: Bild wechselt, Attribution wechselt mit, angeheftete Layer und offene Ansicht bleiben ohne Aufblitzen stehen.
3. Labels und Graticule an und aus, auf jeder Basemap.
4. Lagerichtigkeit je Projektion: Szene in voller Auflösung bei hoher Breite (etwa Skandinavien) öffnen, AOI-Rechteck zeichnen, bei Zoom 6, 9 und 11 prüfen, dass Zuschnitt, AOI-Linie und Bildkante übereinanderliegen und ein Klick auf die Szene sie trifft. Coverage an und aus.
5. Neu laden: Die Wahl ist noch da. Permalink teilen, in einem privaten Fenster öffnen: Basemap und Projektion wie geteilt. Einen Permalink von vor UI-02c öffnen: Satellite und Mercator.

### 6.9 Schnitt

1. **UI-02a, Frontend:** Katalog, Menü, Wechsel per Diff, Streets/Grey/Outlines, Thema ins Menü, Globus mit Übergang, Attribution, Merken. Tests. Geschätzt 350–400 Zeilen.
2. **UI-02b, Frontend:** Labels (inklusive über Satellite) und Graticule. Geschätzt 150–200 Zeilen.
3. **UI-02c, Backend und Frontend:** Basemap und Projektion im Permalink. Geschätzt 100–150 Zeilen.

Je PR: Log-Zeile, Prüfanleitung, `main` holen vor „fertig“. Dazu Backlog-Punkte (Vorschlag): Schummerung aus dem DEM (Stufe B, Backend), Sentinel-2-Kachelraster (ESA-Datei rund 106 MB KML, Lizenz ungeklärt [S]), Selbst-Hosting der Vektorkacheln vor dem öffentlichen Start, Satellit lizenzieren vor dem kommerziellen Start, Equal Earth bei neuer MapLibre-Version prüfen.

### 6.10 Fragen an Otto

1. **Satellite:** (1) Esri ohne Schlüssel bleibt, mit Pflicht zur Ablösung vor dem kommerziellen Start (**Empfehlung**); (2) jetzt Esri Location Platform mit Schlüssel; (3) ersetzen durch EOX Sentinel-2 cloudless 2016.
2. **Streets, Grey:** (1) OpenFreeMap Liberty und Positron (**Empfehlung**); (2) VersaTiles; (3) gleich selbst hosten.
3. **Outlines:** (1) aus den Vektorkacheln von OpenFreeMap, genau in jedem Zoom (**Empfehlung**); (2) Natural Earth lokal, ohne Dritten, aber grob ab Zoom 10.
4. **Attribution:** (1) immer offen, `compact: false` (**Empfehlung**, hebt V-7 auf); (2) bleibt beim Start eingeklappt.
5. **Globus:** (1) Übergang auf Mercator bei Zoom 6–7 (**Empfehlung**); (2) MapLibre-Vorgabe mit dem gemessenen Versatz bis Zoom 11,5.
6. **Light/Dark:** (1) ins Menü unter „Interface“ (**Empfehlung**); (2) eigener Knopf bleibt.
7. **Labels:** (1) über den eigenen Bildern, unter AOI-Linie und Zeichnung (**Empfehlung**); (2) unter den eigenen Bildern.
8. **Permalink öffnen:** (1) Basemap und Projektion gelten und werden gemerkt (**Empfehlung**); (2) gelten nur für diesen Besuch.
9. **Datenschutz:** (1) jetzt Hinweis im Tooltip, Selbst-Hosting vor dem öffentlichen Start als Backlog-Punkt (**Empfehlung**); (2) jetzt selbst hosten; (3) Proxy über `gateway`.
10. **Beleg Lagerichtigkeit:** (1) Prüfanleitung, kein Pixeltest in CI (**Empfehlung**, keine neue Abhängigkeit); (2) Pixeltest mit `@playwright/test` als neue Entwicklungsabhängigkeit.
