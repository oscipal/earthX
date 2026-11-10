# UI-06 — 3D-Ansicht und Nordpfeil

**Stand:** 10.11.2026, beauftragt von Otto; Plan mit Fragen F1–F14 (§9). Bis zu Ottos Meldung kein Produktivcode.
**Stufe B:** Erst dieser Plan im Draft-PR, Otto beantwortet die Fragen, dann setzt dieselbe Session um.
**Gilt dazu:** `docs/ui/leitfaden.md` (alle Regeln; Oberflächentexte englisch), NM4-35 (`docs/plans/querschnitt/nm4-35-relief.md`, Höhenkacheln, Attribution, Datenschutz), UI-02 §6.7 (Browser lädt Kacheln direkt), D27 (`docs/plans/m2/m2-format-und-viewer.md`).
**Startsatz:** „Führe Aufgabe UI-06 aus `docs/plans/vp3/ui-06-3d-und-nordpfeil.md` aus.“

Belegstufen wie in NM4-35 §6: [P] Code oder Primärquelle gelesen, [M] in der Sitzung gemessen (Wegwerf-Skript, nicht im Repo), [A] eigene Ableitung.

## 1. Wunsch (Otto, 10.11.2026)

1. **Nordpfeil:** Ist die Karte gedreht, zeigt ein kleiner Kompass die Richtung nach Norden; ein Klick richtet nach Norden aus und kippt zurück. Vorschlag, wann er sichtbar ist.
2. **3D:** Ein Schalter legt die Karte über ein Höhenmodell (MapLibre `setTerrain` mit den AWS Terrain Tiles wie das Relief, NM4-35; der Browser lädt sie direkt) und erlaubt Kippen. Zuerst klären, wo und warum das Kippen heute abgeschaltet ist.
3. Im Plan als Fragen: Bedienung, Überhöhung, Zoomgrenze, Layer auf dem Gelände, AOI bei gekippter Karte, Umrisse und Coverage, Basemap-Wechsel, Permalink, Leistung, Nachtrag Leitfaden; optional ein eigenes Höhenmodell als Gelände.

## 2. Wo und warum Drehen und Kippen heute abgeschaltet sind [P]

**Wo:** an einer Stelle, `frontend/src/components/MapView.tsx`, beim Anlegen der Karte:

- Konstruktor: `dragRotate: false`, `pitchWithRotate: false`, `touchPitch: false`, `maxPitch: 0`.
- Danach `map.touchZoomRotate.disableRotation()` und `map.keyboard.disableRotation()`.
- `new NavigationControl({ showCompass: false })` unten rechts: nur Zoom + und −, kein Kompass.
- `e2e/map-gl6.cjs` Punkt 3 prüft „pitch 0“ als Regel; `relief.ts` begründet die feste Lichtrichtung damit („it cannot turn or tilt here“).

**Warum:** Entscheidung **D27** (Log 20.09.2026, umgesetzt in V-1, #56): „Karte ohne Drehen und Kippen, Globus umschaltbar. Maus und Touch verschieben und zoomen nur.“ Ziel von V-1: „Die Karte ist ruhig zu bedienen.“ Ein technischer Zwang steht nirgends; es war eine Bedienentscheidung. Die Abnahme von V-1 verlangte ausdrücklich, dass Drehen und Kippen mit Maus und Touch nicht möglich sind.

**Folge:** UI-06 hebt D27 teilweise auf. Das ist eine Entscheidung von Otto (F1) und bekommt eine eigene Zeile im Entscheidungslog.

## 3. Weitere Befunde im Code [P]

- **MapLibre 6.16.0** (`frontend/node_modules`): `setTerrain({ source, exaggeration })`, `setMaxPitch` (0–180, über 60 „experimental“ laut Typdeklaration), `resetNorthPitch`, `NavigationControl` mit `showCompass` und `visualizePitch`, `TerrainControl`, `centerClampedToGround`. Keine neue Abhängigkeit nötig.
- **Basemap-Wechsel:** `mapStyles.ts::composeStyle` übernimmt `terrain` (mit `sky`, `projection`, `bearing`, `pitch`) aus dem vorigen Stil (`MAP_OWN`). Quellen mit Präfix `bm-` oder `ov-` werden dabei neu gebaut, nur eigene Quellen bleiben. **Die Quelle des Geländes darf daher kein `ov-`-Präfix tragen** und kann nicht die Quelle des Overlays „Relief“ (`ov-relief`) sein; sonst zeigt `terrain` nach dem Wechsel auf eine fehlende Quelle [A].
- **Coverage:** `reportViewport` meldet `map.getBounds()`; `store.ts::refreshCoverage` nimmt die Stufe aus Zoom und Fenstergröße (`levelForViewport`, #286) und den Ausschnitt aus diesen Grenzen. Bei gekippter Karte reichen die Grenzen bis zum Horizont: der Ausschnitt wird viel größer, als die Stufe annimmt, also viele mehr Zellen je Anfrage [A].
- **Permalink:** `PermalinkView` im Backend (`api/processing_route.py`) ist `extra="forbid"` mit `center`, `zoom`, `range`, `basemap`, `projection`. Drehung, Neigung oder 3D im Permalink brauchen dort neue Felder.
- **AOI:** Terra Draw 1.32 mit dem MapLibre-Adapter 1.4.1 (Punkt, Rechteck, Polygon). Der Adapter rechnet über `map.unproject`, das in MapLibre das Gelände berücksichtigt. Eine gezeichnete AOI lässt sich heute **nicht verschieben oder bearbeiten** (kein Auswahlmodus); „verschieben“ kann hier also nur das Verschieben der Karte beim Zeichnen meinen (F9).
- **Tastatur:** Die Zeitleiste fängt ←/→ ohne Umschalt-, Strg-, Alt- und Meta-Taste ab (`stepKeys.ts`). MapLibre dreht mit Umschalt+←/→ und kippt mit Umschalt+↑/↓; das stößt sich nicht.
- **Symbole (Lucide, im Paket):** `compass`, `navigation-2`, `mountain`, `rotate-3d`, `move-3d`, `axis-3d`.

## 4. Messung im Browser [M]

Wegwerf-Skript, nicht im Repo: Chromium der Sitzung (Software-Rendering, also nur Kacheln und Daten aussagekräftig, nicht die Zeiten), MapLibre 6.16 aus `frontend/node_modules`, echte Kacheln von `s3.amazonaws.com`, 1280×800 px, Alpen (10.5° O, 47° N), Zoom 9, Gelände und Schummerung aus zwei Quellen mit derselben Adresse, `maxzoom: 12`, Überhöhung 1,5, Drehung 30°.

| Ansicht | Höhenkacheln | Daten | bis zur Ruhe (Software) |
|---|---|---|---|
| Gelände, Neigung 0° | 16 | 1,7 MB | 2,6 s |
| Neigung 45° | 28 | 3,4 MB | 6,4 s |
| Neigung 60° | 54 | 6,3 MB | 12 s |
| Neigung 75° | 76 | 8,6 MB | 19 s |
| Neigung 85° | 83 | 9,7 MB | 24 s |
| Globus, Zoom 3, Neigung 60° | 48 | 4,0 MB | 9,8 s |
| Neigung 60°, Zoom 13 | 41 | 5,7 MB | 26 s |

- Gelände und Schummerung werden in Mercator und auf dem Globus ohne Fehler gezeichnet; die Bildschirmfotos zeigen ein stimmiges Relief.
- Last steigt mit der Neigung stark: 60° kostet rund das Dreieinhalbfache von 0°; über 60° kommt wenig Bild und viel Horizont dazu.
- Zum Vergleich: das Overlay Relief allein brauchte 24 Kacheln je Ansicht (NM4-35 §6.4).

## 5. Vorschlag

### 5.1 Nordpfeil (Wunsch 1)

- **Bauteil:** der Kompass von MapLibre im vorhandenen `NavigationControl` unten rechts (`showCompass: true`, `visualizePitch: true`), über Zoom + und −. Er zeigt nach Norden, wird bei Neigung flacher gezeichnet, und ein Klick ruft `resetNorthPitch` auf: Norden oben und Neigung 0. Kein eigenes Symbol, kein neues Bauteil; `title` ist an Steuerelementen von MapLibre erlaubt (Leitfaden §4). Text über `locale` englisch: „Reset north and tilt“ (F3).
- **Sichtbar:** nur, wenn die Karte gedreht **oder** gekippt ist (Drehung oder Neigung über 0,5°); sonst ausgeblendet (eine Klasse am Steuerelement, gesetzt bei `rotate` und `pitch`). Nach dem Klick verschwindet er, sobald die Bewegung endet (F2).
- **Tastatur:** der Kompass ist ein Knopf von MapLibre, erreichbar mit Tab, Enter richtet aus.

### 5.2 3D (Wunsch 2)

- **Schalter:** im Panel „Settings“ (Leitfaden §9: neue Einstellungen dieser Art kommen dorthin), neuer Abschnitt „Terrain“ mit der Box „3D“, gedrückt = an, Form wie ein Overlay (F4). Tooltip (advanced): „Lay the map over the terrain and allow tilting. Elevation tiles load from amazonaws.com.“
- **An:** `setTerrain({ source: 'terrain', exaggeration })` auf eine eigene Quelle `terrain` (`raster-dem`, Terrarium, dieselbe Adresse und Attribution wie `relief.ts`, `maxzoom: 12`), `setMaxPitch(60)`, Drehen und Kippen frei (§5.3). Die Karte kippt beim Einschalten nicht von selbst (F5).
- **Aus:** `easeTo({ pitch: 0, bearing: 0 })`, dann `setTerrain(null)`, `setMaxPitch(0)`, Drehen und Kippen wieder gesperrt wie heute.
- **Gemerkt:** je Browser als `earthx.terrain` (`preferences.ts`), wie Projektion und Overlays; Neigung und Drehung werden nicht gemerkt (F12).
- **Globus:** 3D gilt in beiden Projektionen (Gelände auf dem Globus gemessen [M]); der Wechsel der Projektion soll es anlassen, das prüft der Browser-Test [A].

### 5.3 Bedienung

| Eingabe | Drehen | Kippen | Zurück |
|---|---|---|---|
| Maus | rechte Taste oder Strg + Ziehen links/rechts | dieselbe Geste auf/ab | Klick auf den Kompass |
| Touch | zwei Finger drehen | zwei Finger senkrecht schieben | Kompass |
| Tastatur (Karte im Fokus) | Umschalt + ←/→ | Umschalt + ↑/↓ | Tab zum Kompass, Enter |

Alles Vorgaben von MapLibre, nur eingeschaltet, solange 3D an ist. In 2D bleibt die Karte wie heute (D27), der Kompass erscheint dort nie (F1).

### 5.4 Darstellung

- **Überhöhung:** fest 1,5 (F6). Bei 1,0 wirken die Alpen bei Zoom 8–10 flach; 2,0 verzerrt Täler.
- **Zoomgrenze der Höhenkacheln:** `maxzoom: 12` wie beim Relief (NM4-35 §6.4: darüber Streifen, und 30-m-Daten tragen nichts bei); darüber vergrößert MapLibre. Bei Zoom 13 gemessen ohne Fehler [M] (F7).
- **Neigung:** höchstens 60° (F7). Darüber nennt MapLibre die Darstellung experimentell, und die Last steigt ohne Gewinn (§4).
- **Relief zusammen mit 3D:** bleibt ein eigenes Overlay, unverändert. Lichtrichtung bleibt fest zur Karte (`anchor: map`), dreht also mit der Karte mit; so bleibt die Schummerung dem Gelände treu.
- **Himmel:** `sky` bleibt wie heute (Hintergrund des Themas); kein Nebel, keine Atmosphäre im flachen Modus. Der Horizont zeigt die Farbe des Themas.

### 5.5 Layer, AOI, Umrisse und Coverage auf dem Gelände

- **Bilder** (Ansicht, Layer, Ergebnis-Layer, Quicklooks, Mosaik) und **Flächen und Linien** (AOI, Umrisse, Coverage-Zellen, Graticule) legt MapLibre bei Gelände auf die Oberfläche; Beschriftungen stehen in der Höhe [P]. Keine eigene Behandlung nötig; die Prüfung im Browser deckt jede Art ab (§7).
- **AOI zeichnen bei gekippter Karte:** bleibt erlaubt; Punkte landen dort, wo der Zeiger das Gelände trifft. Ein Rechteck bleibt ein Rechteck in Länge und Breite und sieht gekippt schräg aus. Vorschlag: nicht automatisch flach stellen (F9).
- **Coverage:** Die Anfrage nimmt bei gekippter Karte nicht die Grenzen bis zum Horizont, sondern den Ausschnitt, den die Karte bei derselben Mitte und demselben Zoom ohne Neigung hätte (aus `unproject` der Ecken bei Neigung 0, rein gerechnet). So passen Stufe (#286) und Ausschnitt zusammen, und die Zahl der Zellen bleibt wie heute (F10).
- **„Zoom to selection“:** behält Drehung und Neigung (`fitBounds` mit aktueller Drehung); Prüfung im Browser.

### 5.6 Basemap-Wechsel, Permalink, Attribution, Datenschutz

- **Basemap-Wechsel:** Gelände bleibt über `composeStyle` (`MAP_OWN`), weil die Quelle `terrain` eine eigene ist (§3). Test in `mapStyles.diff.test.ts`.
- **Permalink:** 3D, Drehung und Neigung kommen nicht hinein, wie die Overlays (NM4-35 Frage 6); ein Link öffnet flach und nach Norden. Kein Eingriff ins Backend (F11).
- **Attribution:** dieselbe wie beim Relief (`TERRAIN_ATTRIBUTION`), sichtbar, solange 3D an ist.
- **Datenschutz und `gateway`:** wie NM4-35 §6.6: der Browser lädt die Kacheln direkt bei AWS; das Backend fragt nichts an, `gateway` und Importregeln bleiben unberührt. Hinweis im Tooltip der Box.

### 5.7 Leistung auf schwächeren Rechnern

- 3D ist **aus** als Vorgabe und wird nur auf Wunsch eingeschaltet.
- Neigung höchstens 60° begrenzt die Kacheln (§4).
- Verliert die Karte den WebGL-Kontext (`webglcontextlost`) mit 3D an, geht 3D aus und die Statusmeldung sagt „3D was turned off: the graphics card ran out of memory“ (F13). Eine Erkennung „schwacher Rechner“ vorab gibt es nicht; sie wäre geraten.

## 6. Nachtrag Leitfaden (nach der Umsetzung)

- §2 Begriffe: „3D“ (Box im Abschnitt „Terrain“), „Reset north and tilt“ (Kompass); „Basemap, Overlays, Projection, Terrain, Appearance, Tooltips“ als die sechs Abschnitte des Panels.
- §3 Symbole: der Kompass ist das Steuerelement von MapLibre, kein Lucide-Symbol (wie Zoom + und −); kein neues Symbol in `icons.ts`.
- §9 Karte: Drehen und Kippen nur mit 3D (§5.3), höchstens 60°, Kompass nur bei Drehung oder Neigung, 3D je Browser gemerkt (`earthx.terrain`), nicht im Permalink; Coverage misst den flachen Ausschnitt.
- §10 Prüfungen: Zeile für Kompass, 3D und Sperre in 2D.

## 7. Umsetzung, Tests, Abnahme

**Schnitt:** ein PR, Frontend allein, geschätzt rund 250 Zeilen ohne Tests [A]. Dateien: `MapView.tsx`, neue `terrain.ts` (Quelle, Ein/Aus, Sperren), `relief.ts` (gemeinsame Adresse und Attribution), `SettingsPanel.tsx`, `preferences.ts`, `store.ts` (Wert und Setter, flacher Ausschnitt für die Coverage), `index.css` (Kompass ausblenden, nur Tokens), Leitfaden.

**Tests (Vitest):**
- `terrain.test.ts`: An setzt Gelände, Neigungsgrenze und gibt Drehen frei; Aus kippt zurück, sperrt wieder; doppeltes An oder Aus ändert nichts; Aufruf ohne geladenen Stil wirft nicht.
- `preferences.test.ts`: `earthx.terrain` gemerkt; kaputter, fremder oder gesperrter Speicher gibt „aus“.
- `mapStyles.diff.test.ts`: Wechsel der Basemap behält `terrain` und seine Quelle; mit Relief an bleiben beide Quellen.
- `SettingsPanel.test.tsx`: Abschnitt „Terrain“, Box „3D“ mit `aria-pressed`, gleiche Größe wie die anderen Boxen.
- Coverage: gekippter Ausschnitt gibt dieselbe Anfrage wie flach bei gleicher Mitte und gleichem Zoom.
- `uiRules.test.ts`: Begriffe, Tooltip-Stufe, kein `title` außer an MapLibre.

**Browser (Playwright, `e2e/terrain-3d.cjs`):** Hell und Dunkel, 1280 und 360 px, Maus und Touch: in 2D kein Drehen und Kippen, kein Kompass; 3D an, kippen und drehen per Maus, Touch und Tastatur, Kompass erscheint, Klick richtet aus und verschwindet; Wechsel der Basemap und der Projektion lässt 3D an; Ansicht, Layer, AOI und Coverage auf dem Gelände; AOI zeichnen gekippt (Punkt, Rechteck, Polygon); Neigung nicht über 60°. `map-gl6.cjs` Punkt 3 gilt dann für 2D.

**Abnahme:** Lint, Typprüfung, Vitest, Importregeln und Backend-Tests grün; Prüfanleitung für Otto im PR; Zeile im Entscheidungslog; vor „fertig“ `main` geholt.

## 8. Optional: eigenes Höhenmodell als Gelände (später)

Copernicus DEM (`cop-dem-glo-30`) oder swissALTI3D (M5-08c) als Gelände bräuchten Höhenkacheln in Terrarium-Kodierung aus dem `tiler` (heute weist er `algorithm` ab) und für niedrige Zoomstufen eine vorab gerechnete Pyramide; das ist Option B aus NM4-35 §6.3 mit denselben Kosten. Gewinn: genauere Daten (swissALTI3D 0,5–2 m), keine Anfrage bei AWS. Vorschlag: nicht in UI-06, eigene Aufgabe mit Plan, frühestens vor dem öffentlichen Start (F14).

## 9. Fragen an Otto

Antwort je Frage mit der Nummer der Option genügt.

**F1 — Wann darf die Karte drehen und kippen?**
1. Nur mit 3D an; in 2D bleibt D27 (**Empfehlung**)
2. Drehen immer, Kippen nur mit 3D
3. Beides immer, 3D legt nur das Gelände darunter

**F2 — Wann ist der Kompass sichtbar?**
1. Nur bei Drehung oder Neigung (**Empfehlung**)
2. Immer, solange 3D an ist
3. Immer

**F3 — Kompass als Bauteil**
1. Kompass von MapLibre im vorhandenen Zoom-Steuerelement, Tooltip „Reset north and tilt“ (**Empfehlung**)
2. Eigener Knopf mit Lucide `navigation-2`, gedreht nach Norden, oben rechts bei „Zoom to selection“

**F4 — Wo steht der Schalter „3D“?**
1. Panel „Settings“, neuer Abschnitt „Terrain“, Box „3D“ (**Empfehlung**)
2. Vierte Box unter „Overlays“
3. Eigener Knopf über der Karte (z. B. `TerrainControl` von MapLibre bei Zoom + und −)

**F5 — Was passiert beim Einschalten von 3D?**
1. Nur Gelände, die Karte bleibt flach, bis der Nutzer kippt (**Empfehlung**)
2. Die Karte kippt sanft auf 45°

**F6 — Überhöhung**
1. Fest 1,5 (**Empfehlung**)
2. Fest 1,0 (echte Höhen)
3. Wählbar im Abschnitt „Terrain“ (1×, 1.5×, 2×)

**F7 — Grenzen**
1. Höhenkacheln bis Zoom 12, Neigung höchstens 60° (**Empfehlung**)
2. Neigung bis 85° (gemessen: rund 50 % mehr Kacheln als bei 60°)

**F8 — Datensatz- und Ergebnis-Layer auf dem Gelände**
1. Alle Bilder liegen auf dem Gelände, ohne Ausnahme (**Empfehlung**, so zeichnet MapLibre)
2. 3D gesperrt, solange eine Ansicht oder ein Layer offen ist

**F9 — AOI bei gekippter Karte**
1. Zeichnen erlaubt, die Karte bleibt gekippt (**Empfehlung**)
2. Beim Wählen eines Werkzeugs stellt die Karte sich flach und nach Norden
3. „Verschieben“ meint eine verschiebbare AOI: das wäre eine eigene Aufgabe (heute gibt es keine Bearbeitung der AOI)

**F10 — Coverage bei gekippter Karte**
1. Anfrage über den flachen Ausschnitt bei gleicher Mitte und gleichem Zoom (**Empfehlung**)
2. Anfrage über die Grenzen bis zum Horizont (mehr Zellen, langsamer)
3. Coverage gesperrt, solange die Karte gekippt ist

**F11 — Permalink**
1. Nichts davon hinein; ein Link öffnet flach (**Empfehlung**, Frontend allein)
2. 3D, Drehung und Neigung hinein (neue Felder in `PermalinkView`, Backend und Frontend)

**F12 — Merken im Browser**
1. 3D an/aus gemerkt, Drehung und Neigung nicht (**Empfehlung**)
2. Nichts gemerkt, jede Sitzung beginnt in 2D

**F13 — Schwächere Rechner**
1. Vorgabe aus, Neigung begrenzt, bei Verlust des WebGL-Kontexts 3D aus mit Meldung (**Empfehlung**)
2. Dazu ein Hinweis im (i) neben „3D“, dass es mehr Daten und Grafikleistung braucht

**F14 — Eigenes Höhenmodell später (optional)**
1. Später als eigene Aufgabe mit Plan, frühestens vor dem öffentlichen Start (**Empfehlung**)
2. Nicht verfolgen; AWS Terrain Tiles bleiben
3. Jetzt in UI-06 mitplanen
