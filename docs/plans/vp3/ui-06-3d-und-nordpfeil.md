# UI-06 — 3D-Ansicht und Nordpfeil

**Stand:** 11.11.2026, beauftragt von Otto am 10.11.2026; Plan mit Fragen F1–F14 (§9), **angenommen von Otto am 11.11.2026** mit Abweichungen bei F2–F5 (§9a). §5 und §7 sind an die Antworten angepasst, die Regeln stehen im Leitfaden mit der Markierung *(folgt mit UI-06)*. Neue Fragen F15–F17 (§9b), beantwortet von Otto am 11.11.2026 (jeweils Option 1); Umsetzung gestartet am 11.11.2026 (§10).
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

**Folge (Otto, 11.11.2026, F1):** UI-06 hebt D27 **teilweise** auf: Drehen und Kippen gibt es nur mit 3D an. In 2D gilt D27 weiter, die Karte verschiebt und zoomt nur. Eigene Zeile im Entscheidungslog.

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

### 5.1 Kompass (Wunsch 1; Otto, F2 und F3)

- **Immer sichtbar,** auch bei nicht gedrehter Karte und in 2D; dort zeigt er nach Norden, also nach oben (F2).
- **Aussehen wie bei Google Maps** (F3): runder Knopf, darin eine Kompassnadel aus zwei Spitzen, die **Nordhälfte rot** (`--danger`), die Südhälfte in Textfarbe (`--text`), Fläche `--panel-bg`, Rand wie die übrigen Knöpfe über der Karte. Die Nadel dreht sich mit der Karte (Winkel = −Drehung der Karte), in hellem und dunklem Thema mit denselben Tokens. Bei Neigung bleibt sie flach (kein Stauchen wie bei MapLibre `visualizePitch`), damit sie lesbar bleibt.
- **Klick:** `resetNorthPitch`: Norden oben und Neigung 0, als kurze Bewegung (MapLibre-Vorgabe, bei `prefers-reduced-motion` ohne Bewegung). In 2D und schon nach Norden ausgerichtet tut der Klick nichts und ist doch nicht gesperrt (er hat keinen Grund, gesperrt zu sein; F16).
- **Ziehen am Kompass (Vorschlag, F15):** in 3D dreht Ziehen um den Kompass die Karte (Winkel des Zeigers um die Mitte des Knopfs = Drehung); ein Klick ohne Bewegung (unter 4 px) richtet aus. In 2D gibt es kein Ziehen (D27). Per Tastatur: Fokus auf dem Kompass, ←/→ drehen in 3D um 15°, Enter oder Leertaste richtet aus.
- **Tooltip** (advanced, Leitfaden §8a): „Reset north and tilt“; `aria-label` gleich. Der Name ist selbsterklärend genug für „advanced“; wer das Symbol nicht kennt, findet es per `aria-label`.
- **Lage:** oberster Knopf der Gruppe unten rechts, über Zoom + (§5.2).
- **Zeichnung:** Lucide hat keine Nadel mit roter Nordhälfte (`compass` ist eine einfarbige Raute im Kreis, `navigation-2` ein Pfeil). Die Nadel ist damit eine **eigene Zeichnung**, die zweite Ausnahme von Leitfaden §3 nach dem Symbol „Settings“; sie steht in einer Datei (`components/CompassNeedle.tsx`) und im Leitfaden (F17).

### 5.2 3D (Wunsch 2; Otto, F4 und F5)

- **Knopf an der Karte, kein Eintrag im Panel „Settings“** (F4): ein kleiner Knopf mit dem Text „3D“ direkt unter Zoom −. **Reihenfolge unten rechts: Kompass, Zoom +, Zoom −, 3D**, als eine Gruppe.
- **Form:** quadratischer Knopf wie Zoom + und − (`.icon-btn` in der Gruppe), Text „3D“ statt Symbol, weil kein Lucide-Symbol „3D“ eindeutig sagt (`box`, `rotate-3d` sind Würfel und Drehpfeile). **An** ist sichtbar wie jeder gedrückte Schalter (`aria-pressed="true"`, Leitfaden §7): gefüllt in Akzent mit Text `--on-accent` (Form der gewählten Segment-Knöpfe), aus wie Zoom + und −. Tooltip (advanced): „Show the terrain in 3D“ bzw. „Show the map flat“; das (i)-artige Detail zum Datenschutz („Elevation tiles load from amazonaws.com.“) steht als zweiter Satz im selben Tooltip, wie beim Overlay „Relief“.
- **An** (F5): `setTerrain({ source: 'terrain', exaggeration: 1.5 })` auf eine eigene Quelle `terrain` (`raster-dem`, Terrarium, dieselbe Adresse und Attribution wie `relief.ts`, `maxzoom: 12`), `setMaxPitch(60)`, Drehen und Kippen frei, dann `easeTo({ pitch: 50 })` um die Mitte; Drehung bleibt, wie sie ist (in 2D also Norden).
- **Aus** (F5): `easeTo({ pitch: 0, bearing: 0 })`, danach `setTerrain(null)`, `setMaxPitch(0)`, Drehen und Kippen wieder gesperrt wie heute (D27).
- **Gemerkt** (F12): 3D an/aus je Browser als `earthx.terrain` (`preferences.ts`); ein Besuch mit gemerktem 3D öffnet mit Gelände und 50° Neigung wie beim Einschalten. Neigung und Drehung selbst werden nicht gemerkt. Ein Permalink öffnet immer flach (F11) und lässt die gemerkte Wahl unberührt.
- **Globus:** 3D gilt in beiden Projektionen (Gelände auf dem Globus gemessen [M]); der Wechsel der Projektion soll es anlassen, das prüft der Browser-Test [A].
- **Bauteil:** Kompass, Zoom +, Zoom − und 3D werden ein eigenes `MapControls` (React, Tokens, Lucide `plus` und `minus`) und ersetzen `NavigationControl` von MapLibre. Grund: eine Gruppe aus vier Knöpfen mit einer Form, beide Themen über Tokens (heute sind Zoom + und − im dunklen Thema weiß), Steuerhöhe 28 px bzw. 44 px bei Touch und unter 900 px (Leitfaden §7). Zoom + und − behalten ihr Verhalten (`zoomIn`, `zoomOut`) und ihre Texte „Zoom in“ und „Zoom out“.

### 5.3 Bedienung

| Eingabe | Drehen | Kippen | Zurück |
|---|---|---|---|
| Maus | rechte Taste oder Strg + Ziehen links/rechts; Ziehen am Kompass (F15) | dieselbe Geste auf/ab | Klick auf den Kompass |
| Touch | zwei Finger drehen; Ziehen am Kompass (F15) | zwei Finger senkrecht schieben | Kompass |
| Tastatur | Karte im Fokus: Umschalt + ←/→; Kompass im Fokus: ←/→ (F15) | Karte im Fokus: Umschalt + ↑/↓ | Kompass im Fokus: Enter |

Die Gesten an der Karte sind Vorgaben von MapLibre, nur eingeschaltet, solange 3D an ist. In 2D bleibt die Karte wie heute (D27, F1); der Kompass steht dort und zeigt nach Norden (F2). Die Zeitleiste fängt ←/→ ab, außer in Feldern, Listen, Dialogen und am Regler (`stepKeys.ts`); der Kompass kommt als weitere Ausnahme dazu, damit er im Fokus seine Pfeiltasten behält.

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

- 3D ist **aus** als Vorgabe und wird nur auf Wunsch eingeschaltet (F13).
- Neigung höchstens 60° begrenzt die Kacheln (§4).
- Verliert die Karte den WebGL-Kontext (`webglcontextlost`) mit 3D an, geht 3D aus und die Statusmeldung sagt „3D was turned off: the graphics card ran out of memory“ (F13). Eine Erkennung „schwacher Rechner“ vorab gibt es nicht; sie wäre geraten.

## 6. Nachtrag Leitfaden (eingetragen am 11.11.2026)

Die Regeln standen zuerst mit der Markierung *(folgt mit UI-06)* im Leitfaden; mit der Umsetzung (§10) ist sie entfallen.

- §2 Begriffe: „3D“ (der Knopf an der Karte), „Reset north and tilt“ (Kompass), „Zoom in“, „Zoom out“.
- §3 Symbole: Kompass als zweite Ausnahme (eigene Nadel, Nordhälfte `--danger`), Zoom mit `plus` und `minus`, 3D als Text.
- §7 Bauteile: `MapControls` (Kompass, Zoom +, Zoom −, 3D, unten rechts).
- §9 Karte: Drehen und Kippen nur mit 3D (D27 in 2D), höchstens 60°, Einschalten kippt auf 50°, Ausschalten auf 0; Kompass immer sichtbar; 3D je Browser gemerkt (`earthx.terrain`), nicht im Permalink; Coverage misst den flachen Ausschnitt; schmale Fenster.
- §10 Prüfungen: Zeile für Kompass, 3D und die Sperre in 2D.

**Hell und dunkel, schmale Fenster:**
- Alle vier Knöpfe nehmen Fläche, Rand, Text und Akzent aus `tokens.css`; die Nadel `--danger` und `--text`, also in beiden Themen lesbar. Keine feste Farbe.
- Unter 900 px und bei Touch 44 px je Knopf (`--control-height-touch`); die Gruppe ist dann 4 × 44 px hoch und steht wie heute über der Attribution. Wo eine Seitenleiste oder ein Blatt rechts offen ist, rückt die Gruppe mit (die vorhandenen Regeln für `.maplibregl-ctrl-bottom-right` gelten für die neue Gruppe).
- Bei 320 px Breite darf die Gruppe kein Panel der Leiste und keine Statusmeldung überdecken, die man bedienen muss; Prüfung in `narrow-windows.cjs`.

## 7. Umsetzung, Tests, Abnahme

**Schnitt:** ein PR, Frontend allein, geschätzt rund 350 Zeilen ohne Tests [A]. Dateien: `MapView.tsx` (ohne `NavigationControl`), neue `terrain.ts` (Quelle, Ein/Aus, Sperren), neue `components/MapControls.tsx` und `components/CompassNeedle.tsx`, `relief.ts` (gemeinsame Adresse und Attribution), `icons.ts` (`MinusIcon`), `preferences.ts`, `store.ts` (Wert und Setter, flacher Ausschnitt für die Coverage), `index.css` (nur Tokens), Leitfaden (Markierung entfernen).

**Tests (Vitest):**
- `terrain.test.ts`: An setzt Gelände, Neigungsgrenze und gibt Drehen frei; Aus kippt zurück, sperrt wieder; doppeltes An oder Aus ändert nichts; Aufruf ohne geladenen Stil wirft nicht.
- `preferences.test.ts`: `earthx.terrain` gemerkt; kaputter, fremder oder gesperrter Speicher gibt „aus“.
- `mapStyles.diff.test.ts`: Wechsel der Basemap behält `terrain` und seine Quelle; mit Relief an bleiben beide Quellen.
- `MapControls.test.tsx`: Reihenfolge Kompass, Zoom +, Zoom −, 3D; Kompass immer da, Nadel folgt der Drehung, Klick ruft das Zurücksetzen; Ziehen dreht nur in 3D; Pfeiltasten am Kompass nur in 3D; „3D“ mit `aria-pressed`, An kippt auf 50°, Aus auf 0 und Norden; Tooltips mit Stufe „advanced“, `aria-label` überall.
- `SettingsPanel.test.tsx`: kein Abschnitt „Terrain“, keine Box „3D“ (Gegenprobe).
- Coverage: gekippter Ausschnitt gibt dieselbe Anfrage wie flach bei gleicher Mitte und gleichem Zoom.
- `uiRules.test.ts`: Begriffe, Tooltip-Stufe, kein `title` außer an MapLibre; die Nadel als einzige zweite eigene Zeichnung (`<svg>` nur in `RangeHistogram` und am Kompass).
- `icons.test.tsx`: `MinusIcon` benutzt.

**Browser (Playwright, `e2e/terrain-3d.cjs`):** Hell und Dunkel, 1280, 360 und 320 px, Maus und Touch: Reihenfolge und Größe der Gruppe; in 2D kein Drehen und Kippen, Kompass nach Norden; 3D an kippt auf 50°, kippen und drehen per Maus, Touch, Tastatur und Kompass, die Nadel dreht mit, Klick richtet aus; 3D aus setzt Neigung und Drehung auf 0; Wechsel der Basemap und der Projektion lässt 3D an; Ansicht, Layer, AOI und Coverage auf dem Gelände; AOI zeichnen gekippt (Punkt, Rechteck, Polygon); Neigung nicht über 60°. `map-gl6.cjs` Punkt 3 gilt dann für 2D.

**Abnahme:** Lint, Typprüfung, Vitest, Importregeln und Backend-Tests grün; Prüfanleitung für Otto im PR; Zeile im Entscheidungslog; vor „fertig“ `main` geholt.

## 8. Optional: eigenes Höhenmodell als Gelände (später)

Copernicus DEM (`cop-dem-glo-30`) oder swissALTI3D (M5-08c) als Gelände bräuchten Höhenkacheln in Terrarium-Kodierung aus dem `tiler` (heute weist er `algorithm` ab) und für niedrige Zoomstufen eine vorab gerechnete Pyramide; das ist Option B aus NM4-35 §6.3 mit denselben Kosten. Gewinn: genauere Daten (swissALTI3D 0,5–2 m), keine Anfrage bei AWS. Vorschlag: nicht in UI-06, eigene Aufgabe mit Plan, frühestens vor dem öffentlichen Start (F14).

## 9. Fragen an Otto (10.11.2026)


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

## 9a. Antworten Otto (11.11.2026)

| Frage | Antwort |
|---|---|
| F1 | Option 1: Drehen und Kippen nur mit 3D; **D27 gilt für 2D weiter** (teilweise Aufhebung, Log) |
| F2 | **abweichend:** Der Kompass ist immer sichtbar, auch bei nicht gedrehter Karte; in 2D zeigt er nach Norden |
| F3 | **abweichend:** wie bei Google Maps: runder Knopf mit Kompassnadel (Nordhälfte rot), dreht mit der Karte, Klick richtet nach Norden aus und setzt die Neigung zurück; in 3D optional Drehen durch Ziehen am Kompass (Vorschlag im Plan, F15); über den Zoom-Knöpfen |
| F4 | **abweichend:** kein Eintrag im Panel „Settings“, sondern ein kleiner Knopf „3D“ direkt unter den Zoom-Knöpfen (Lucide oder Text, Tooltip nach Leitfaden, aktiv sichtbar); Reihenfolge Kompass, Zoom +, Zoom −, 3D |
| F5 | **abweichend:** Einschalten kippt gleich auf etwa 50°; Ausschalten setzt Neigung und Drehung auf 0 |
| F6–F14 | jeweils Option 1 |

Dazu: hell und dunkel, schmale Fenster (§6); Antworten im Leitfaden. Umsetzung erst auf Ottos Signal.

## 9b. Neue Fragen aus den Antworten

**F15 — Ziehen am Kompass**
1. In 3D dreht Ziehen um den Kompass die Karte, Klick ohne Bewegung richtet aus; im Fokus drehen ←/→ um 15° (**Empfehlung**, §5.1)
2. Kein Ziehen, nur Klick

**F16 — Kompass in 2D, schon nach Norden**
1. Nicht gesperrt, der Klick tut nichts (**Empfehlung**: er ist kein Knopf, der „gerade nicht geht“)
2. Gesperrt mit Grund „Already facing north“

**F17 — Eigene Zeichnung der Nadel** (Leitfaden §3 erlaubt keine eigenen Zeichnungen)
1. Zweite Ausnahme neben „Settings“: zwei Spitzen als SVG in `CompassNeedle.tsx`, Nord `--danger`, Süd `--text`, im Leitfaden vermerkt (**Empfehlung**; anders ist eine rote Nordhälfte nicht zu haben)
2. Lucide `navigation-2` in Rot, gedreht (Pfeil statt Nadel)

**Antworten Otto (11.11.2026):** F15, F16 und F17 jeweils Option 1: Ziehen am Kompass dreht in 3D, Klick ohne Bewegung richtet aus, im Fokus ←/→ um 15°; der Kompass ist in 2D nicht gesperrt; die Nadel ist eine eigene Zeichnung als zweite Ausnahme von Leitfaden §3. Umsetzung freigegeben.

## 10. Umgesetzt (11.11.2026)

**Code** (Frontend allein, kein Backend, keine neue Abhängigkeit):
- `terrain.ts`: Ein und Aus. An: eigene Quelle `terrain` (AWS Terrain Tiles, `maxzoom` 12), Überhöhung 1,5, Neigung bis 60°, Drehen und Kippen frei, Flug auf 50°. Aus: erst zurück nach Norden und flach, dann ohne Gelände und gesperrt (D27). Wird während des Rückflugs wieder eingeschaltet, bleibt das Gelände. `prefers-reduced-motion` und der erste Besuch springen ohne Flug. `flatViewBounds` gibt den flachen Ausschnitt für die Coverage (F10).
- `components/MapControls.tsx` mit `CompassNeedle.tsx` ersetzt `NavigationControl`: Kompass, Zoom +, Zoom −, 3D. Der Kompass dreht mit der Karte, ein Klick ruft `resetNorthPitch`. In 3D dreht Ziehen am Kompass und ←/→ (15°) im Fokus; in 2D tut beides nichts. Er ist nie gesperrt. Zoom + und − sind an der Grenze gesperrt, mit Grund im Tooltip.
- `MapView.tsx`: Die Gruppe steht in MapLibres Ecke unten rechts und rückt damit wie bisher neben Seitenleiste und Blatt. Der Platzhalter trägt bewusst **nicht** die Klasse `maplibregl-ctrl`, weil MapLibres Hover-Regel für Knöpfe dort sonst die Füllung von „3D“ überschreibt (im Browser gefunden). Ein Verlust des WebGL-Kontexts schaltet 3D für den Besuch aus, mit Meldung.
- `preferences.ts`, `store.ts`: `earthx.terrain`; ein Permalink öffnet flach und lässt die gemerkte Wahl stehen (`showSharedLook`).
- `stepKeys.ts`: Der Kompass gehört zu den Stellen mit eigenen Pfeiltasten.
- `index.css`: Gruppe, runder Kompass, Nadel in `--danger` und `--text`; nur Tokens.

**Tests:** `terrain.test.ts`, `components/MapControls.test.tsx`, `store.terrain.test.ts`, `preferences.test.ts`, `mapStyles.diff.test.ts` (Basemap-Wechsel in 3D, mit und ohne Relief), `uiRules.test.ts` (kein `NavigationControl`, kein „3D“ in „Settings“, Begriffe, zweite eigene Zeichnung, Farben der Nadel). Browser: `e2e/terrain-3d.cjs` (hell und dunkel, 1280, 360 und 320 px, Maus und Touch); `map-gl6.cjs` prüft die Sperre jetzt ausdrücklich für 2D, `settings-box.cjs` sucht Zoom + unter dem neuen Namen.

**Grenzen der Prüfung:** Die Sitzung erreicht Esri und OpenFreeMap nicht; die Bildschirmfotos zeigen deshalb das Gelände ohne Bild darüber. Gesten mit zwei Fingern sind MapLibres eigene und werden im Browser-Test nicht gefahren; mit Touch prüft er Tippen auf Kompass und „3D“.

**Prüfanleitung für Otto:**
1. Karte in 2D: Kompass oben in der Gruppe unten rechts, Nadel nach oben (Nord rot). Rechts ziehen, Strg + Ziehen und Umschalt + Pfeiltasten drehen und kippen nichts.
2. „3D“ drücken: Knopf gefüllt, Karte kippt auf etwa 50° über das Gelände (am besten in den Alpen, Zoom 9–11, Basemap Satellite, gern mit Overlay „Relief“). In der Attribution steht „Terrain: …“.
3. Rechts ziehen dreht und kippt (höchstens 60°); die Nadel dreht mit. Am Kompass ziehen dreht die Karte; Tab auf den Kompass, ←/→ dreht um 15°. Ein Klick auf den Kompass richtet nach Norden aus und legt die Karte flach, 3D bleibt an.
4. Gekippt: Basemap, Projektion (Globus) und Relief wechseln, das Gelände bleibt. Coverage einschalten: sie fragt nicht bis zum Horizont. Punkt und Polygon zeichnen.
5. Neu laden: die Karte öffnet in 3D. „3D“ aus: zurück nach Norden und flach, kein Kippen mehr.
6. Hell und dunkel, ein schmales Fenster (unter 900 px): Knöpfe 44 px, nichts verdeckt.
