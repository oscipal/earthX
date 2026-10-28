# NM4-35 — Relief (Schummerung) als Overlay und optional als Basemap

**Stand:** 27.10.2026, beauftragt von Otto (Backlog-Punkt 35; Vorschlag aus dem Plan von UI-02, §6); Plan mit Recherche am 28.10.2026 (§6), von Otto am 28.10.2026 freigegeben (§6.10). Der Code wartet auf den Merge von UI-02c und einen freien Frontend-Platz; Otto meldet beides.
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für Recherche und Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach dem Merge von UI-02a (Basemap-Menü). Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-35 aus `docs/plans/querschnitt/nm4-35-relief.md` aus.“

## 1. Anlass

UI-02 hat eine Schummerung aus dem eigenen Copernicus DEM geprüft: Der `tiler` weist `algorithm` heute ab, und eine weltweite Grundkarte ginge nur mit einer vorab gerechneten Pyramide im eigenen Speicher. Otto möchte das Relief trotzdem (27.10.2026) – als Overlay über jeder Basemap und optional als eigene Basemap „Relief“.

## 2. Soll

- Schalter „Relief“ in der Gruppe „Overlays“ des Basemap-Menüs (UI-02): halbtransparente Schummerung über jeder Basemap, unter den eigenen Bildern und unter den Labels.
- Optional eine Basemap „Relief“ (graue Schummerung allein).
- Die Wahl wird im Browser gemerkt wie die übrigen Einstellungen des Menüs; Permalink wie Basemap und Projektion (gilt für die Ansicht, überschreibt die gespeicherte Vorgabe nicht, UI-02 Frage 8).

## 3. Im Plan klären (mit Optionen und Empfehlung)

- **Option A (Vorschlag):** MapLibre zeichnet die Schummerung selbst im Browser (Ebene `hillshade`, Quelle `raster-dem`) aus freien Höhenkacheln ohne Schlüssel, etwa AWS „Terrain Tiles“ (Terrarium) aus der Registry of Open Data. Kein Backend, keine Pyramide. Mit Quellen prüfen: Lizenz und Attribution der Höhendaten, Verfügbarkeit, Ratenlimits, CORS, Datenschutz (Kacheln lädt der Browser direkt, wie die Basemaps).
- **Option B:** Höhenkacheln aus dem eigenen Copernicus DEM über den `tiler` (Terrarium- oder Terrain-RGB-Kodierung) und Schummerung in MapLibre; dafür vorab gerechnete Pyramide für niedrige Zoomstufen im eigenen Speicher. Aufwand, Speicher, Kosten.
- **Option C:** Schummerung als fertiges Bild aus dem `tiler` (Algorithmus `hillshade`). Kosten je Kachel, Zoomgrenzen.
- Darstellung: Beleuchtungsrichtung, Überhöhung, Deckkraft (feste Vorgabe, keine Einstellmöglichkeit nötig); Verhalten im Globus.

## 4. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip.
- Keine neue Abhängigkeit ohne Frage an Otto; keine Schlüssel oder Secrets.
- Bei Option A gilt die Regel „ausgehende Requests nur über `gateway`“ nicht (Browser lädt direkt, wie Basemaps); im Plan ausdrücklich festhalten.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: Schalter und Basemap aus dem Menü, Reihenfolge der Ebenen (Relief unter eigenen Bildern und Labels), Merken im Browser, Permalink.
- Prüfung im echten Browser (Playwright), Hell/Dunkel, Mercator und Globus; Prüfanleitung für Otto im PR.
- Attribution der Höhendaten sichtbar (UI-02 Frage 4).
- Alle vier Pflicht-Checks grün; Log-Zeile mit PR-Nummer (Backlog pflegt der Planungs-Chat).
- Vor „fertig“ ist main geholt.

## 6. Plan (28.10.2026, von Otto am 28.10.2026 freigegeben)

**Freigabe (Otto, 28.10.2026, zu #222):** Option A mit AWS Terrain Tiles, Basemap „Relief“ als Schummerung allein, Kacheln nur bis Zoom 12, Meeresboden bleibt sichtbar. Abweichend von den Empfehlungen: Attribution nur mit Beleg (§6.11), der Code wartet auf UI-02c (Frage 5), das Overlay „Relief“ kommt nicht in den Permalink (Frage 6). Antworten in §6.10; §6.0, §6.6, §6.7 und §6.8 sind angepasst. Bis zu Ottos Meldung kein Produktivcode.

Stufe B: Bis zur Freigabe ist kein Produktivcode geändert. Grundlage ist `main` nach #219 mit UI-02a und UI-02b; UI-02c (Basemap und Projektion im Permalink) ist noch nicht umgesetzt. Belegstufen wie in UI-02 §6: [P] Code oder Primärquelle gelesen, [M] in der Sitzung gemessen (Wegwerf-Skript, nicht im Repo), [S] nur Suchtreffer, [A] eigene Ableitung. Lizenzfragen entscheidet Otto (CLAUDE.md); alles hier ist Vorschlag.

**Zur Quellenlage:** Aus der Sitzung erreichbar waren `s3.amazonaws.com` (AWS Terrain Tiles), `registry.opendata.aws`, `github.com` und `raw.githubusercontent.com`. Nicht erreichbar waren `mapterhorn.com` und `tiles.mapterhorn.com` sowie, wie in UI-02, Esri und OpenFreeMap. Mapterhorn ist deshalb nur aus seinem öffentlichen Repo belegt (`mapterhorn/mapterhorn`, Stand 26.10.2026: Webseite, Quellkatalog, Beispiele).

### 6.0 Kurzfassung

- **Empfehlung Option A:** MapLibre rechnet die Schummerung im Browser (`hillshade`-Ebene auf einer `raster-dem`-Quelle) aus den **AWS Terrain Tiles** (Terrarium-PNG, kein Schlüssel). Kein Backend, keine Pyramide, keine neue Abhängigkeit. Mapterhorn ist die bessere Datengrundlage, aber aus der Sitzung nicht prüfbar (Frage 2).
- **Overlay „Relief“** liegt über der Basemap und unter allen Bildern der App, damit auch unter Labels und Graticule. **Basemap „Relief“**: die Schummerung allein, kräftiger, auf dem Hintergrund des Themas (Frage 4).
- **Option B** (eigenes DEM als Terrarium) kostet eine Vorabrechnung bis Zoom 7 (rund 22 000 Kacheln, rund 1 GB [A]) und darüber Kacheln live aus dem `tiler`, mit einem neuen Operator. **Option C** (fertige Schummerung aus dem `tiler`) hat dieselben Kosten, dazu Nähte an den Kachelrändern und eine feste Farbe für beide Themen. Beide sind Backend-Arbeit für eine Funktion, die A ohne Backend liefert.
- **Gemessen [M]:** 24 Höhenkacheln je Ansicht (1280×800 px), 0,5–1,8 MB; CORS offen; Schummerung in Mercator und auf dem Globus richtig gezeichnet. Mit `maxzoom: 12` sinkt die Zahl bei Zoom 14 auf 2 Kacheln, und die Störungen der Kacheln von Zoom 15 entfallen.
- **Regel „nur über `gateway`“** gilt hier nicht: Der Browser lädt die Höhenkacheln selbst, wie die Basemaps (§6.6).
- **Permalink:** Die Basemap „Relief“ kommt über den Mechanismus von UI-02c hinein, das Overlay nicht (Otto, Frage 5 und 6). Der Code beginnt erst nach dem Merge von UI-02c.
- **Attribution:** Kurzform in der Kartenecke, volle Liste hinter dem Link; eine Kurzform allein ist an den offiziellen Angaben nicht für alle Quellen belegt (§6.11).
- **Fragen an Otto:** 6, beantwortet am 28.10.2026 (§6.10).

### 6.1 Stand im Code [P]

- **Menü und Katalog:** `basemaps.ts` (vier Basemaps, Präfix `bm-`), `overlays.ts` (Labels, Graticule, Präfix `ov-`), `components/BasemapMenu.tsx` baut die Gruppen aus beiden Katalogen. Ein neuer Eintrag in einem Katalog erscheint ohne Änderung am Menü.
- **Zusammensetzen:** `mapStyles.ts::composeStyle` legt die Ebenen in dieser Folge: `background`, Ebenen der Basemap (`bm-…`), eigene Ebenen der App bis unter `aoi-fill`, Overlays (`ov-…`), `aoi-fill` und darüber. Der Wechsel geht als Stil-Diff (`setStyle(…, { diff: true, transformStyle })`); die eigenen Ebenen bleiben unberührt.
- **Merken:** `preferences.ts::loadOverlays` liest `earthx.overlays` als JSON und nimmt nur die Schlüssel aus `OVERLAY_IDS`. Ein gespeicherter Wert ohne `relief` gibt damit „Relief aus“, ohne Sonderfall.
- **Karte:** Drehen und Neigen sind abgeschaltet (`MapView.tsx`: `dragRotate: false`, `maxPitch: 0`). Die Lichtrichtung bleibt damit immer zur Karte gleich.
- **Tiler:** `algorithm` wird auf jeder Route mit `400` abgewiesen (`api/tiler.py::_refuse_free_parameters`, M4-09 F3). Das DEM ist `cop-dem-glo-30` in `catalog/datasets.py`, 1°×1°-COGs aus dem AWS-Bucket; die Mosaikkachel nimmt 2 bis 64 Items ab Zoom 8 (M4-17).
- **MapLibre 5.24** (`@maplibre/maplibre-gl-style-spec`, `latest.json`): `raster-dem` kennt die Kodierungen `terrarium`, `mapbox` und `custom`. `hillshade` hat `hillshade-method` (`standard`, `basic`, `combined`, `igor`, `multidirectional`), Richtung (Vorgabe 335°), Höhe (45°), Anker (`viewport`/`map`), Überhöhung (0–1, Vorgabe 0,5) und drei Farben (Schatten, Licht, Akzent). **Eine Deckkraft gibt es nicht**; sie kommt über den Alphawert der drei Farben. `draw_hillshade` hat einen Globus-Zweig (UI-02 §6.3).

### 6.2 Recherche: Quellen der Höhenkacheln

| Quelle | Daten | Lizenz, Attribution | Betrieb | Schlüssel | CORS | Datenschutz |
|---|---|---|---|---|---|---|
| **AWS Terrain Tiles** (`elevation-tiles-prod`, Tilezen Joerd) | SRTM, GMTED, ETOPO1 (Meeresboden), EU-DEM 30 m, 3DEP 10 m, nationale Modelle (UK 2 m, AT, NO 10 m) [P]; Terrarium 256 px, Zoom 0–15 [P][M]; Stand 2017 (`Last-Modified` der geprüften Kacheln: 15.11.2017) [M] | alle offen (Public Domain, CC BY 3.0/4.0, OGL UK und Kanada, INEGI); Pflicht ist eine Liste von elf Quellen, „in a place that is reasonable to the medium“ [P] | AWS Open Data, Bucket `us-east-1`, keine Nutzungsgrenze genannt [P]; der Spiegel `elevation-tiles-prod-eu` antwortet `403` [M] | nein [P] | `Access-Control-Allow-Origin: *` [M] | IP, Referer, Kachel an Amazon (USA); kein `Cache-Control`, der Browser speichert nach Heuristik [M] |
| **Mapterhorn** (`tiles.mapterhorn.com`) | Copernicus GLO-30 weltweit (dasselbe DEM wie `cop-dem-glo-30`) plus 152 nationale Modelle, bis Zoom 17; Terrarium-WebP 512 px [P] | Code BSD-3; Daten nach Quellkatalog alle offen, keine NC- oder ND-Lizenz unter 153 Einträgen [P]; Beispiel der Attribution: „© Mapterhorn“ mit Link auf die Quellenliste [P] | gehostet bei Cloudflare als Sponsor; keine Nutzungsbedingungen, Grenzen oder SLA im Repo gefunden [P]; Projekt seit 2025 | nein [P] | nicht prüfbar | protokolliert IP, Referer, User-Agent u. a. 30 Tage (eigene Datenschutzseite, Stand 07.07.2026) [P] |
| **Natural Earth II** (Schummerung, bei OpenFreeMap) | Rasterbild, farbig, nur bis Zoom 6 [P] (in Liberty schon enthalten) | Public Domain | OpenFreeMap | nein | – | wie Streets |
| **Eigenes DEM** (Option B, C) | Copernicus GLO-30 | im Katalog: „© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS …“ [P] | eigener Speicher und `tiler` | nein | eigen | kein Dritter |

Quellen (abgerufen am 28.10.2026): [AWS Registry: Terrain Tiles](https://registry.opendata.aws/terrain-tiles/), [Registry-Eintrag als YAML](https://raw.githubusercontent.com/awslabs/open-data-registry/main/datasets/terrain-tiles.yaml), [Joerd: Attribution](https://github.com/tilezen/joerd/blob/master/docs/attribution.md), [Joerd: Datenquellen](https://github.com/tilezen/joerd/blob/master/docs/data-sources.md), [Joerd: Formate und Zoom](https://github.com/tilezen/joerd/blob/master/docs/use-service.md), [Mapterhorn README](https://github.com/mapterhorn/mapterhorn) mit `website/` (Data Access, Attribution, Privacy Policy, Beispiele) und `source-catalog/*/metadata.json`, [OSM Liberty bei OpenFreeMap](https://github.com/hyperknot/openfreemap-styles) (`styles/liberty/style.json`, Quelle `ne2_shaded`).

**Folgerungen [A]:**

- **AWS Terrain Tiles** sind ohne Schlüssel, offen lizenziert, seit 2017 unverändert und aus der Sitzung geprüft. Schwächen: alte Daten, in hohen Zoomstufen Störungen (§6.4), lange Pflichtliste der Attribution, Server in den USA. Die frühere Notiz „Buckets für EC2 gedacht“ (UI-02 §6.2) fand ich im heutigen Registry-Eintrag nicht mehr; dort steht keine Nutzungsgrenze.
- **Mapterhorn** ist neuer und genauer und beruht auf demselben GLO-30 wie das eigene DEM, die Attribution ist kurz. Dagegen: Betrieb hängt an einem Sponsor, Nutzungsbedingungen sind nicht auffindbar, und aus der Sitzung lässt es sich weder laden noch messen. Kodierung und Ebene sind dieselben wie bei AWS; der Wechsel ist eine Adresse, `tileSize` und die Attribution im Katalog.
- **Natural Earth II** scheidet aus: farbig statt grau und nur bis Zoom 6.

### 6.3 Optionen

| | A: Schummerung im Browser aus fremden Höhenkacheln | B: eigenes DEM als Terrarium, Schummerung im Browser | C: fertige Schummerung aus dem `tiler` |
|---|---|---|---|
| Backend | keins | neuer Operator mit Terrarium-Ausgabe (`adr/0014`), Vorabrechnung, Ablage im Objektspeicher, Auslieferung | neuer Operator `hillshade` mit Rand (Nachbarpixel), sonst wie B |
| Niedrige Zoomstufen | ja | nur mit Pyramide: Zoom 0–7 sind 21 845 Kacheln, bei rund 50 kB je Kachel rund 1 GB [A]; bis Zoom 12 nennt VersaTiles 407 GB (UI-02 §6.4) | wie B |
| Ab Zoom 8 | ja | live über `gateway`: je Ansicht 24 Kacheln mit 1–4 COGs; eine Kachel braucht im `tiler` rund 0,9 s, im Browser stehen die Anfragen in einer Schlange von 6 Verbindungen (NM4-26 B1) [A] | wie B |
| Darstellung | in beiden Themen anpassbar, über den Stil | wie A | festes Bild: eine Farbe für Hell und Dunkel, Nähte ohne Rand |
| Globus | ja [M] | ja | ja (Rasterkachel) |
| Kosten | keine | Rechenlauf über rund 26 000 DEM-Kacheln, Speicher, Verkehr, Betrieb | wie B, dazu Rechenzeit je Kachel |
| Dritter im Browser | ja, Datenschutz wie Basemaps | nein | nein |
| Aufwand | ~120 Zeilen Code im Frontend | mehrere PRs, Backend und Betrieb | wie B |

**Empfehlung: Option A** mit AWS Terrain Tiles (Frage 1, 2). Sie erfüllt das Soll ohne Backend und ohne Kosten. Weil die Quelle nur eine Zeile im Katalog ist, bleibt der spätere Wechsel auf Mapterhorn oder auf eine eigene Pyramide (Option B, etwa vor dem öffentlichen Start, wie das Selbst-Hosting der Vektorkacheln in UI-02 Frage 9) ohne Umbau möglich.

### 6.4 Messung im Browser [M]

Wegwerf-Skript, nicht im Repo: Chromium der Sitzung (Software-Rendering), MapLibre 5.24 aus `frontend/node_modules`, echte Kacheln von `s3.amazonaws.com`, Ansicht 1280×800 px, Schummerung mit Richtung 315°, Anker `map`, Überhöhung 0,5, Schatten `rgba(0,0,0,0.45)`, Licht `rgba(255,255,255,0.25)`.

| Ansicht | Kacheln | Daten | Zoom der Kacheln |
|---|---|---|---|
| Alpen, Zoom 3, Mercator | 24 | 494 kB | 4 |
| Alpen, Zoom 9, Mercator | 24 | 1777 kB | 10 |
| Alpen, Zoom 9, Globus | 24 | 742 kB | 10 |
| Welt, Zoom 1, Globus | 11 | 453 kB | 2 |
| Norwegen, Zoom 9, Globus | 24 | 943 kB | 10 |
| Alpen, Zoom 12, `maxzoom` 15 / 12 | 24 / 6 | 1355 / 266 kB | 13 / 12 |
| Alpen, Zoom 14, `maxzoom` 15 / 12 | 24 / 2 | 989 / 133 kB | 15 / 12 |

- MapLibre lädt 256-px-Kacheln eine Stufe über dem Kartenzoom; eine Ansicht braucht damit rund 24 Kacheln, gleich welcher Zoom.
- Kein Fehler und keine Antwort außer `200` bei den Höhenkacheln. Die Schummerung sieht in Mercator und auf dem Globus gleich aus; auf dem Globus folgt sie der Krümmung.
- **Meeresboden:** ETOPO1 bringt den Meeresboden mit. Bei Weltansicht und über dem Atlantik zeigt die Schummerung Bruchzonen, Seeberge und Schelfkanten (§6.5 Punkt 5).
- **Hohe Zoomstufen:** Die Kacheln von Zoom 15 zeigen Streifen und Rauschen; mit `maxzoom: 12` wird das Bild weich, aber ruhig, bei einem Zwölftel der Kacheln. 30-m-Daten (SRTM, EU-DEM) tragen über Zoom 12 ohnehin nichts bei.
- **Hell:** Auf weißem Hintergrund ist dieselbe Schummerung gut lesbar; für die Basemap „Relief“ auf `#e9ecef` reichen Schatten und Licht mit Alpha 0,6.
- **Nicht belegt:** Esri und OpenFreeMap als Grund (aus der Sitzung nicht erreichbar), also wie die Schummerung über dem Satellitenbild und über Streets wirkt; das prüft die Anleitung (§6.8). Mapterhorn nicht geladen.

### 6.5 Darstellung und Lage (Vorschlag, feste Werte)

1. **Lage:** Overlay „Relief“ direkt über allen Ebenen der Basemap, unter den Bildern der App. Damit liegt es auch unter Labels und Graticule (beide liegen über den Bildern, UI-02b). Bei Streets und Grey liegt es damit auch über Straßen und Flächen der Basemap; das ist auf jeder Basemap dieselbe Regel (Einfügen zwischen bestimmten Ebenen eines veröffentlichten Stils wäre ein Sonderfall je Stil).
2. **Licht:** Richtung 315° (Nordwest, kartografische Gewohnheit; MapLibres Vorgabe 335°), Höhe 45°, Anker `map`. Methode `standard`.
3. **Overlay:** Überhöhung 0,5, Schatten `rgba(0,0,0,0.45)`, Licht `rgba(255,255,255,0.25)`, Akzent `rgba(0,0,0,0.15)`. Gleich in beiden Themen, weil es über der Basemap liegt, nicht über dem Hintergrund.
4. **Basemap „Relief“:** dieselbe Quelle, Überhöhung 0,6, Schatten und Licht mit Alpha 0,6, auf dem Hintergrund des Themas (`--map-bg`, dunkel bzw. weiß). Labels und Graticule gehen darauf wie auf Outlines (Labels aus dem Stil von Grey, UI-02b §9.1 Punkt 3).
5. **Meeresboden bleibt sichtbar** (§6.4). Ihn auszublenden bräuchte eine Wasserfläche von OpenFreeMap auch über dem Satellitenbild.
6. **Overlay auf der Basemap „Relief“:** Der Haken bleibt wählbar (Regel vom 26.10.2026), die Schummerung wird dort aber nicht ein zweites Mal gezeichnet. Beide nutzen dieselbe Quelle, es gibt keine doppelten Abrufe.
7. **Quelle:** `maxzoom: 12` (§6.4), darüber vergrößert MapLibre.
8. **Globus:** keine eigene Behandlung; ab Zoom 12 flach wie alles andere.

### 6.6 Merken, Permalink, Attribution, Datenschutz

- **Im Browser:** Overlay „Relief“ in `earthx.overlays` (`{"labels":…,"graticule":…,"relief":…}`), Basemap „Relief“ in `earthx.basemap` (`relief`). Ältere Werte ohne `relief` gelten als „aus“ (§6.1). Vorgabe: Relief aus, Basemap Satellite.
- **Permalink (Otto, Frage 5 und 6):** Die Basemap „Relief“ kommt über den Mechanismus von UI-02c in den Permalink, als weiterer Wert der Basemap (`satellite` | `streets` | `grey` | `outlines` | `relief`). Wie dort gilt sie für die geöffnete Ansicht und überschreibt die gemerkte Wahl nicht (UI-02 Frage 8). Das Overlay „Relief“ kommt nicht hinein, einheitlich mit Labels und Graticule (UI-02 §6.6); die Vorgabe aus §2 ist damit zurückgenommen. Ein Permalink, der mit der Basemap „Relief“ geteilt wird, zeigt das Relief also immer, ein Overlay „Relief“ dagegen nur bei dem, der es selbst eingeschaltet hat.
- **Attribution:** MapLibre zeigt die Attribution der sichtbaren Quellen; die der Höhenkacheln steht damit nur da, wenn Relief an ist oder die Basemap „Relief“ gewählt ist. Wortlaut und Beleg in §6.11.
- **Datenschutz (Otto, 28.10.2026: wie bei den Basemaps, UI-02 §6.7):** Der Browser lädt die Höhenkacheln direkt bei AWS, nicht über die Plattform. Hinweis wie bei den Basemaps (UI-02 Frage 9, Option 1): Tooltip „Elevation tiles load from amazonaws.com.“ IP und Kartenausschnitt gehen an Amazon in den USA; der EU-Spiegel ist nicht öffentlich lesbar [M].
- **Regel „ausgehende Requests nur über `gateway`“:** Sie gilt für das Backend und bleibt dort unverändert. Die Höhenkacheln lädt der Browser des Nutzers selbst, wie die Kacheln der Basemaps (UI-02 §6.7); das Backend fragt die Quelle nie an. Option A ändert an `gateway`, der Allowlist und den Importregeln nichts.

### 6.7 Umsetzung nach der Freigabe (NM4-35a, Frontend)

- `overlays.ts`: `relief` in `OverlayId`, `OVERLAY_IDS`, `NO_OVERLAYS`, `OVERLAYS` (Name „Relief“, Tooltip mit Quelle und Host).
- `relief.ts` (neu, klein): die `raster-dem`-Quelle mit Adresse, `encoding: 'terrarium'`, `tileSize: 256`, `maxzoom: 12` und Attribution; `reliefLayer(look: 'overlay' | 'basemap')`.
- `basemaps.ts`: Basemap `relief` mit lokalem Stil (Quelle und Ebene aus `relief.ts`).
- `mapStyles.ts::composeStyle`: Overlay „Relief“ zwischen die Ebenen der Basemap und die eigenen Ebenen; bei Basemap „Relief“ nicht doppelt (§6.5 Punkt 6). Der Rest (Diff, Umschalter, Rückfall bei Fehlern) bleibt.
- `BasemapMenu.tsx`, `preferences.ts`, `store.ts`: nichts außer dem, was sich aus den Katalogen ergibt (§6.1).
- Keine neue Abhängigkeit, kein Backend, keine Änderung an `.github/`.
- Schätzung: rund 120 Zeilen Code, 300–400 Zeilen Tests.
- Beginn erst nach dem Merge von UI-02c und Ottos Meldung (Frage 5). Dann `relief` als weiterer Wert der Basemap im Permalink, über den Mechanismus von UI-02c (Frontend und die Aufzählung in `PermalinkView`, falls UI-02c sie dort festlegt). Das Overlay bleibt draußen.

### 6.8 Tests, Prüfanleitung, Abnahme

**Vitest (CI, ohne Netz):**

- Menü: „Relief“ in Overlays und in Basemap, Haken, `aria-checked`, Tooltip; Wahl setzt Store und `localStorage`.
- Lage: Overlay „Relief“ über allen `bm-`-Ebenen und unter der ersten eigenen Ebene, unter Labels und Graticule, auf jeder Basemap; angehakter Quicklook (`overlays-base`) bleibt darüber.
- Basemap „Relief“: Stil mit `raster-dem`-Quelle und `hillshade`-Ebene; mit Overlay an keine zweite Ebene und keine zweite Quelle.
- Diff: Einschalten ist nur `addSource`/`addLayer` (bzw. Entfernen), die eigenen Ebenen bleiben unberührt (wie `mapStyles.overlays.test.ts`).
- Attribution: genau der Wortlaut aus §6.11 mit dem Link auf die volle Liste, an der Quelle der Höhenkacheln; nur sichtbar, wenn Relief an ist oder die Basemap „Relief“ gewählt ist.
- Speicher: Rundreise, alter Wert ohne `relief`, kaputter Wert, gesperrter Speicher, `relief` als Basemap.
- Permalink (mit dem Mechanismus von UI-02c): Basemap „Relief“ wird gespeichert und beim Öffnen übernommen, ohne die gemerkte Wahl zu überschreiben; das Overlay „Relief“ steht nicht im Permalink und bleibt beim Öffnen so, wie der Betrachter es gemerkt hat; `relief` als unbekannter Wert eines älteren Backends wird wie jeder andere unbekannte Wert behandelt.
- Fehlerfälle: Quelle ohne Schlüssel in der Adresse; Werte der Darstellung im erlaubten Bereich der Style-Spec (Prüfung mit `@maplibre/maplibre-gl-style-spec`, schon `devDependency`).

**Echter Browser (Playwright, Wegwerf-Skript wie UI-02a/b, nicht im Repo):** Mercator und Globus, Hell und Dunkel, Overlay über Satellite (Ersatzkachel) und Basemap „Relief“, Ebenenfolge im laufenden Stil, Bildpunkte unter einem eigenen Bild unverändert, echte Höhenkacheln von AWS.

**Prüfanleitung für Otto (Kurzfassung, die volle Fassung kommt mit NM4-35a):**

1. Start mit leerem Speicher: kein Relief, Attribution nur von Esri.
2. „Relief“ anhaken: Gebirge treten plastisch hervor, auf jeder Basemap; Attribution „Terrain: USGS, NOAA, EU-DEM (Copernicus) and others“ erscheint unten rechts; der Link öffnet die volle Liste (§6.11). Eine Szene öffnen: sie deckt die Schummerung zu, Labels und Graticule liegen darüber.
3. Basemap „Relief“: graue Schummerung allein, in Hell und Dunkel lesbar.
4. Globus: Schummerung folgt der Kugel; Zoom 12 und mehr: weich, ohne Streifen.
5. Permalink mit Basemap „Relief“ teilen und in einem privaten Fenster öffnen: Relief wie geteilt; danach neu laden: wieder die gemerkte Basemap. Mit Overlay „Relief“ geteilt: im privaten Fenster ohne Relief.
6. Neu laden: Wahl bleibt. Sperre von `s3.amazonaws.com`: die Karte bleibt, nur das Relief fehlt.

**Pflicht-Checks:** `npm run lint`, `npx tsc -b`, Vitest, `ruff check backend`, `pytest`, `lint-imports`; Log-Zeile mit PR-Nummer; `main` holen vor „fertig“.

### 6.9 Fragen an Otto (beantwortet am 28.10.2026, §6.10)

1. **Option:** (1) A, Schummerung im Browser aus fremden Höhenkacheln (**Empfehlung**); (2) B, eigenes DEM als Terrarium mit Pyramide bis Zoom 7 und `tiler` darüber; (3) C, fertige Schummerung aus dem `tiler`.
2. **Quelle bei A:** (1) AWS Terrain Tiles (**Empfehlung**: in der Sitzung geprüft, CORS offen, offene Lizenzen, seit 2017 stabil); (2) Mapterhorn (neuer, genauer, kurze Attribution, aber Betrieb über Sponsor, keine Bedingungen auffindbar, aus der Sitzung nicht prüfbar); (3) AWS jetzt, Mapterhorn als Backlog-Punkt prüfen, wenn der Host erreichbar ist.
3. **Attribution:** (1) kurz in der Ecke „Terrain: USGS, NOAA, EU-DEM (Copernicus) and others“ mit Link auf die volle Liste (**Empfehlung**); (2) die elf Sätze der Joerd-Liste in der Ecke; (3) anderer Wortlaut.
4. **Basemap „Relief“:** (1) ja, Schummerung allein auf dem Hintergrund des Themas (**Empfehlung**, wie §2 „optional“); (2) ja, mit blasser Wasserfläche von OpenFreeMap, damit die Küsten erkennbar sind (Dritter mehr); (3) nein, nur das Overlay.
5. **Permalink und UI-02c:** (1) NM4-35a jetzt ohne Permalink; UI-02c nimmt `relief` in die Basemaps auf und gegebenenfalls das Overlay (Frage 6); der Abnahmepunkt „Permalink“ wandert zu UI-02c (**Empfehlung**, kein doppeltes Anfassen von `PermalinkView`); (2) NM4-35 wartet, bis UI-02c gemergt ist; (3) NM4-35 setzt UI-02c mit um (Backend und Frontend, größerer PR).
6. **Overlay „Relief“ im Permalink:** (1) ja, als eigenes Feld, wie in §2 verlangt; Labels und Graticule bleiben draußen (**Empfehlung**, weicht für dieses eine Overlay von UI-02 §6.6 ab); (2) nein, nur die Basemap „Relief“ kommt hinein, wie UI-02 §6.6 für alle Overlays.

### 6.10 Antworten von Otto (28.10.2026, zu #222)

1. **Option:** A.
2. **Quelle:** AWS Terrain Tiles. Mapterhorn wird nicht weiter verfolgt.
3. **Attribution:** Option 1, aber belegt: An den offiziellen Lizenz- und Attributionsangaben der Terrain Tiles prüfen, ob eine Kurzform mit Link zulässig ist, und die Stelle zitieren. Ist sie nicht zulässig, kommt die Kurzform in die Kartenecke und die volle Liste hinter den Link, nicht alle Sätze in die Ecke. Ergebnis in §6.11.
4. **Basemap „Relief“:** Option 1, die Schummerung allein.
5. **Permalink und UI-02c:** Option 2. Der Code wartet, bis UI-02c gemergt ist (läuft gerade); danach kommt „Relief“ als Basemap über den Mechanismus von UI-02c in den Permalink. Außerdem wartet der Code auf einen freien Frontend-Platz; Otto meldet beides.
6. **Overlay „Relief“ im Permalink:** Option 2, nicht hinein, einheitlich mit Labels und Graticule (UI-02 §6.6). Die Basemap „Relief“ schon. Die Vorgabe aus §2 ist damit zurückgenommen.

Dazu angenommen: Höhenkacheln nur bis Zoom 12 laden (§6.5 Punkt 7); der Meeresboden bleibt sichtbar (§6.5 Punkt 5). Datenschutz wie bei den Basemaps (UI-02 §6.7): Der Browser lädt die Kacheln direkt bei AWS (§6.6).

### 6.11 Attribution: Prüfung der Kurzform (zu Frage 3)

**Offizielle Angabe der Terrain Tiles.** Der Registry-Eintrag nennt als Lizenz genau eine Seite: `License: https://github.com/tilezen/joerd/blob/master/docs/attribution.md` ([YAML](https://raw.githubusercontent.com/awslabs/open-data-registry/main/datasets/terrain-tiles.yaml), gelesen am 28.10.2026) [P]. Dort steht:

- „Attribution is required for many terrain tile data providers. Example language is provided below, but you are responsible for researching each project to follow their license terms.“
- Unter „***Required attribution:***“ folgen elf Sätze, je Quelle einer (ArcticDEM, Australien, Österreich, Kanada, EU-DEM, ETOPO1, Mexiko, Neuseeland, Norwegen, Vereinigtes Königreich, USGS für 3DEP, GMTED2010 und SRTM).
- Abschnitt „Where to attribute“: „Attribution needs to "appear in a place that is reasonable to the medium or means you are utilising."“ Dazu ein Verweis auf Beispiele der OSM Foundation.

([attribution.md](https://github.com/tilezen/joerd/blob/master/docs/attribution.md), gelesen am 28.10.2026 [P].)

**Ergebnis:** Die offizielle Seite erlaubt eine Kurzform mit Link **nicht ausdrücklich**. Sie nennt die elf Sätze „required“ und verweist für die Form auf die einzelnen Lizenzen. Diese Lizenzen sind verschieden deutlich:

| Quelle | Lizenz | Stelle zur Form der Nennung | Kurzform mit Link |
|---|---|---|---|
| Norwegen (Kartverket), Australien | CC BY 4.0 | §3(a)(2): „You may satisfy the conditions in Section 3(a)(1) in any reasonable manner based on the medium, means, and context in which You Share the Licensed Material. For example, it may be reasonable to satisfy the conditions by providing a URI or hyperlink to a resource that includes the required information.“ | ausdrücklich erlaubt |
| Vereinigtes Königreich | OGL UK 3.0 | „If you are using Information from several Information Providers and listing multiple attributions is not practical in your product or application, you may include a URI or hyperlink to a resource that contains the required attribution statements.“ | ausdrücklich erlaubt |
| Kanada | OGL Canada 2.0 | „… if you are using information from several information providers and multiple attributions are not practical for your product or application, you must use the following attribution statement: Contains information licensed under the Open Government Licence – Canada.“ | ein fester Satz; wo er stehen muss, sagt die Lizenz nicht |
| Österreich | CC BY 3.0 AT | §4 b): „Die nach diesem Abschnitt 4.b) erforderlichen Angaben können in jeder angemessenen Form gemacht werden …“ | angemessene Form, Link nicht genannt |
| Neuseeland (LINZ) | CC BY 3.0 NZ | „… ensure that You credit the Licensor / Original Author as appropriate to the media used.“ | dem Medium angemessen, Link nicht genannt |
| 3DEP, SRTM, GMTED2010 (USGS), ETOPO1 (NOAA), ArcticDEM | gemeinfrei bzw. ohne Lizenz | laut Joerd nur eine Bitte um Nennung („the USGS does request that proper credit be given“; ArcticDEM „Requested citation“) | keine Pflicht zur Form |
| EU-DEM | Copernicus (EEA) | Joerd nennt nur den Satz „Produced using Copernicus data and information funded by the European Union - EU-DEM layers.“ | Form nicht geregelt |
| Mexiko (INEGI) | Términos de libre uso | nicht gelesen (Seite aus der Sitzung nicht erreichbar) | offen |

Die Lizenztexte stammen aus der [SPDX License List](https://github.com/spdx/license-list-data) (`text/CC-BY-4.0.txt`, `OGL-UK-3.0.txt`, `OGL-Canada-2.0.txt`, `CC-BY-3.0-AT.txt`) und aus dem Repo von Creative Commons ([cc-legal-tools-data](https://github.com/creativecommons/cc-legal-tools-data), `docs/licenses/by/3.0/nz/legalcode.en.html`), gelesen am 28.10.2026 [P]. Die Originalseiten (`creativecommons.org`, `nationalarchives.gov.uk`, `open.canada.ca`, `inegi.org.mx`) waren aus der Sitzung nicht erreichbar.

**Folge (nach Ottos Regel für den Fall „nicht zulässig“):** Weil die Kurzform allein nicht für alle Quellen belegt ist, gilt: Kurzform in der Kartenecke, volle Liste hinter dem Link, nicht alle Sätze in der Ecke.

- **In der Ecke:** „Terrain: USGS, NOAA, EU-DEM (Copernicus) and others“. Der ganze Text ist ein Link, damit er auffällt.
- **Hinter dem Link:** die volle Liste, und zwar die offizielle Seite [`tilezen/joerd/docs/attribution.md`](https://github.com/tilezen/joerd/blob/master/docs/attribution.md). Sie enthält alle elf Sätze, wird von den Herausgebern der Kacheln gepflegt und ist dieselbe Seite, auf die der Registry-Eintrag verweist. Eine eigene Seite mit der Liste kann vor dem öffentlichen Start zum Impressum dazukommen, wie für die Stil-Lizenzen (UI-02 §7.4).
- **Rest-Risiko für Ottos Einstufung:** Für CC BY 3.0 AT und NZ, OGL Canada, EU-DEM und INEGI erlaubt kein gelesener Text ausdrücklich einen Link; sie verlangen eine „angemessene“ bzw. „dem Medium angemessene“ Nennung. Die volle Liste bleibt mit einem Klick aus der Ecke erreichbar. Eine eindeutige Auskunft gäbe nur eine Rechtsprüfung.
