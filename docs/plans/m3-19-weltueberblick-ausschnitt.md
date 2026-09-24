# M3-19 — Weltüberblick ohne AOI: sichtbarer Ausschnitt, Zellstufe folgt dem Kartenzoom

**Status:** Umgesetzt. Otto hat §7 am 24.09.2026 wie empfohlen freigegeben
(F1 (a) `N = 2 000`, F2 (a) Footprints ohne AOI zeigen, F3 (a) Cache-Frist
5 min/Route unverändert, F4 (a) Farbskala je Antwort). Umsetzung in derselben
Session, Diff im PR.
**Datum:** 2026-09-24
**Aufgabe:** M3-19 aus `plans/m3-dritte-quelle-und-interface.md`, **geänderte
Vorgabe** von Otto am 23.09.2026 (ersetzt `adr/0010` Antwort 6a „ohne AOI immer
z6“; Log-Zeile vom 23.09.2026).
**Grundlage:** `adr/0004` §3.3, §5 (Deckel, Regel V, 500-kB-Schwelle);
`adr/0010` §3.2, §3.8, §3.9; `adr/0005` Regel II; `plans/m2-05-coverage.md`;
Code: `frontend/src/store.ts` (`refreshCoverage`), `frontend/src/coverage.ts`,
`frontend/src/components/MapView.tsx`, `backend/earthx/api/coverage_route.py`,
`backend/earthx/catalog/coverage.py` (`level_for_viewport`, `WORLD_LEVEL_CAP`),
`backend/earthx/adapters/earth_search_coverage.py`,
`backend/earthx/adapters/eopf_sample_coverage.py`.

**Neues Ziel.** Ohne AOI fragt die Heatmap nur den sichtbaren Kartenausschnitt
ab. Die Zellstufe folgt dem Kartenzoom, sodass auf dem Bildschirm ungefähr
gleich viele Zellen liegen. Mit AOI bleibt alles wie heute.

**Belegstufen** wie in `adr/0004`: **M** gemessen in dieser Sitzung, **P**
Primärdokument oder Code gelesen, **A** eigene Ableitung.

---

## 0. Heute

- `refreshCoverage` schickt `zoom = floor(Kartenzoom)` und `bbox` nur aus der
  AOI **[P]**. Ohne AOI fehlt `bbox`, die Route deckelt über `WORLD_LEVEL_CAP`
  auf höchstens z6, aber nicht nach unten: beim Start (Zoom 1,6) kommt Stufe 1,
  also vier Zellen für die ganze Welt.
- Jedes `moveend` löst nach 400 ms Entprellung eine neue Anfrage aus, auch beim
  bloßen Verschieben; geladene Antworten werden im Frontend nicht
  wiederverwendet **[P]**.
- Im Branch liegt noch der Commit „immer z6“ aus der ersten Fassung von M3-19.
  Er ist durch die geänderte Vorgabe überholt und wird im Umsetzungsschritt
  ersetzt.

---

## 1. Formel Kartenzoom → Zellstufe

MapLibre zeichnet die Welt bei Kartenzoom `Z` mit `512 · 2^Z` CSS-Pixeln
Breite. Eine Geotile-Zelle der Stufe `L` ist damit `s = 512 · 2^(Z − L)` Pixel
breit, und ein Ausschnitt von `W × H` Pixeln enthält höchstens
`N = W · H / s²` Zellen **[A]**. Nach `L` aufgelöst, für eine Zielzahl `N`:

```
L = clamp( round( Z + log2( 512 · sqrt(N / (W · H)) ) ),  L_min,  L_max )
```

| Größe | Vorschlag | Begründung |
|---|---|---|
| Zielzahl `N` | **2 000** Zellen je Bildschirm | bei 1920 × 1080 genau `L = Z + 4`, Zellen 23–45 px; durch `round` schwankt die Zahl zwischen `N/2` und `2N` |
| `W`, `H` | Größe des Karten-Containers in CSS-Pixeln | so bleibt die Zellzahl auch auf anderen Bildschirmen gleich; auf 2560 × 1440 ergibt sich `L ≈ Z + 3,6` |
| **Untergrenze** `L_min` | **4** | ergibt sich bei Zoom 0 auf einem üblichen Bildschirm ohnehin; hält einen sehr kleinen Container davon ab, gröber als 16 × 16 Zellen zu werden |
| **Obergrenze** `L_max` | **Registry-Deckel** `coverage.max_geotile_level` | Sentinel-2 L2A und EOPF: **z8**. Die Route deckelt ohnehin (`level_for_viewport`); das Frontend liest den Wert nicht, es schickt die Stufe und bekommt die benutzte zurück (`level` in der Antwort) |

Beispiele für 1920 × 1080: Start (Zoom 1,6) → **z6**, Zoom 2,5 → z7, Zoom 3,5
→ z8, ab Zoom 3,5 bleibt z8 (Deckel); die Zellen wachsen dann auf dem
Bildschirm, bis die Footprints übernehmen (ab Zoom 4, `FOOTPRINT_MIN_ZOOM`,
wenn die Quelle unter 500 Treffer meldet).

**Mit AOI** bleibt es bei `floor(Z)` und der AOI als `bbox` wie heute.

Die Formel ist eine reine Funktion in `frontend/src/coverage.ts` (Zoom,
Containergröße → Stufe), getestet mit Vitest.

---

## 2. Zellen und Größe je Zoomstufe — [M]

Gemessen am 24.09.2026 gegen Earth Search, `sentinel-2-c1-l2a`, ganzer
Katalog, ohne Datum und Wolkenfilter, eine Anfrage je Zeile. Ausschnitt
1920 × 1080 um 10° O / 50° N (Europa, dicht belegt), sofern nicht anders
genannt. „Zellen“ ist, was die Quelle liefert (auch Zellen knapp außerhalb,
weil sie Items zählt, deren Footprint den Ausschnitt schneidet); in Klammern
die Zellen mit Mittelpunkt im Ausschnitt. „Antwort“ ist die Zellenliste in
unserem Format (`{"k","n"}`, F4 aus M2-05).

| Kartenzoom | Stufe | Zellen (im Ausschnitt) | Antwort | Roh von der Quelle | Zeit | Regel V |
|---|---|---|---|---|---|---|
| 1,6 (Start, 10° O / 20° N) | z6 | 2 142 (2 098) | 54 kB | 131 kB | 0,91 s | vollständig |
| 2 | z6 | 1 757 (1 695) | 44 kB | 109 kB | 1,22 s | vollständig |
| 2,5 | z7 | 3 740 (3 527) | 94 kB | 220 kB | 1,11 s | vollständig |
| 3 | z7 | 1 856 (1 684) | 46 kB | 114 kB | 0,40 s | vollständig |
| 3,5 | z8 | 3 296 (3 189) | 85 kB | 198 kB | 0,55 s | vollständig |
| 4 | z8 | 1 798 (1 666) | 46 kB | 112 kB | 0,41 s | vollständig |
| 5 | z8 (Deckel) | 602 (510) | 16 kB | 44 kB | 0,31 s | vollständig |
| 6 | z8 (Deckel) | 160 (120) | 4 kB | 19 kB | 0,31 s | vollständig |
| 7 | z8 (Deckel) | 54 (32) | 1 kB | 13 kB | 0,29 s | vollständig |

Weitere Fälle:

| Fall | Stufe | Zellen | Antwort | Zeit | Regel V |
|---|---|---|---|---|---|
| 2560 × 1440, Zoom 3 | z7 | 3 310 | 83 kB | 0,71 s | vollständig |
| Afrika (20° O / 0°), Zoom 3 | z7 | 1 431 | 35 kB | 0,44 s | vollständig |
| Ausschnitt + 25 % Rand je Seite, Zoom 3 | z7 | 4 158 | 104 kB | 0,79 s | vollständig |
| Ausschnitt + 25 % Rand je Seite, Zoom 4 | z8 | 3 794 | 98 kB | 0,51 s | vollständig |
| feiner: `L = Z + 5`, Zoom 2 | z7 | 6 510 | 163 kB | 0,97 s | vollständig |
| feiner: `L = Z + 5`, Zoom 3 | z8 | 6 972 | 179 kB | 0,71 s | vollständig |

**Bezug auf die Grenzen.**

- **10 000-Zellen-Kappung von Earth Search** (`adr/0004` §3.3, `adr/0010`
  §3.2): Mit `N = 2 000` liegt der gemessene Höchstwert bei 3 740 Zellen, also
  bei gut einem Drittel der Kappung. Jede Messung war nach Regel V
  vollständig. Die Reserve deckt das Aufrunden des Ausschnitts auf das Raster
  (§3, bis etwa × 1,5 **[A]**) und breitere Bildschirme ab. Mit `L = Z + 5`
  läge man schon bei 7 000 Zellen; davon rate ich ab.
- **500-kB-Schwelle aus `adr/0004` §5** (unkomprimiert): höchstens 94 kB
  gemessen, mit Rand 104 kB. Selbst eine gekappte Antwort mit 10 000 Zellen
  läge bei rund 260 kB **[A]**. Die Schwelle ist in keinem Fall nah.
- Der Weltüberblick über die ganze Welt auf z7 wäre gekappt (`adr/0010`
  §3.2). Das tritt mit der Formel nicht ein: z7 kommt erst ab Zoom 2,5, dann
  zeigt ein 1920er Bildschirm höchstens 240° Länge. Falls doch (sehr breiter
  Bildschirm), meldet Regel V `truncated`, und die Legende sagt es.

---

## 3. Entprellen und Wiederverwendung

Ziel: keine Anfrageflut an die Quelle. Vorschlag, alles im Frontend:

1. **Entprellen wie heute:** 400 ms nach `moveend`, nicht während der
   Bewegung.
2. **Ausschnitt auf das Raster runden.** Die Anfrage-`bbox` ist der
   Ausschnitt, nach außen aufgerundet auf das Geotile-Raster der Stufe
   `L − 3` (Blöcke aus 8 × 8 Zellen). Kleine Verschiebungen ergeben damit
   dieselbe `bbox`: derselbe Cache-Schlüssel im Backend, und keine exakte
   Kartenposition in der Anfrage.
3. **Geladenes wiederverwenden.** Das Frontend hält die letzten 8 Antworten
   (Schlüssel: Datensatz, Zeitraum, Stufe, gerundete `bbox`). Liegt der neue
   Ausschnitt bei gleicher Stufe ganz in einer geladenen `bbox`, wird **keine**
   Anfrage gestellt. Das deckt Verschieben innerhalb des Rands und Hin- und
   Herzoomen ab.
4. **Beim Stufenwechsel** bleiben die alten Zellen stehen, bis die neuen da
   sind; kein leeres Bild dazwischen. Veraltete Antworten verwirft der
   vorhandene Generationszähler (`coverageGen`).
5. **Folge für die Last [A]:** höchstens eine Anfrage je ruhender Ansicht
   außerhalb des Geladenen, im Backend-Cache zwischen Nutzern geteilt. Ein
   Zoom vom Start bis z8 kostet rund drei Anfragen (z6, z7, z8). Heute löst
   jedes Verschieben eine Anfrage aus.

**Verworfen: Anfrage je fester Kachel** (z. B. Blöcke der Stufe `L − 5`, je
eine Anfrage). Das würde Wiederverwendung und Cache zwischen Nutzern
verbessern, kostet aber 6–12 Anfragen je erster Ansicht. Außerdem zählt die
Quelle ein Item in jeder Kachel, die sein Footprint schneidet. Die Zellen
müssten dann auf ihre Kachel beschnitten werden, und die Summe passte nicht
mehr zu `total_count`: Regel V wäre je Anfrage nicht mehr prüfbar (so auch in
`adr/0010` §3.3).

**Antimeridian und Weltkopien.** Überschreitet der Ausschnitt ±180° (Pazifik
oder Weltkopien bei kleinem Zoom), wird ein Band über die volle Länge
−180…180 in der Breite des Ausschnitts angefragt, statt zwei Anfragen zu
mischen. Zwei Anfragen würden ein Item, das über die Grenze reicht, doppelt
zählen. Das Band ist meist Ozean; wird es doch gekappt, zeigt Regel V das.
**Globus-Projektion:** Ob `getBounds()` dort den sichtbaren Teil liefert, wird
im Umsetzungsschritt im Browser geprüft. Wenn nicht, fällt die Anfrage auf das
Band bzw. die ganze Welt zurück.

---

## 4. Passt die Coverage-Route?

**Ja, ohne Änderung [P].** Das Frontend schickt die berechnete Stufe als `zoom`
(die Route beschreibt `zoom` schon als „Stufe vor den Deckeln“) und den
gerundeten Ausschnitt als `bbox`. Folgen:

- `level_for_viewport` deckelt auf den Registry-Wert (z8). Der Weltdeckel
  `WORLD_LEVEL_CAP` greift nicht, weil eine `bbox` da ist. Das ist gewollt, denn
  die Formel hält die Zellzahl klein (§2). Für Anfragen ohne `bbox` (andere
  Clients) bleibt er stehen.
- Der Cache-Schlüssel enthält die `bbox` als Hash (keine Koordinate im
  Klartext); durch das Runden trifft er.
- EOPF (Stichprobe) funktioniert mit `bbox` schon heute. Die Stichprobe wird
  damit je Ausschnitt gezogen statt weltweit, was aussagekräftiger ist. Kosten:
  bis zu 5 Suchseiten je neuer Ansicht (M2-09b: rund 2 s), seitenweise
  gecacht. Das Frontend behandelt beide Datensätze gleich, ohne Sonderfall.

**Zwei Punkte, die ohne Routenänderung bleiben, aber zu wissen sind:**

1. **Cache-Frist.** Die Route kann den Ausschnitt nicht von einer AOI
   unterscheiden. Eine Ausschnitts-Anfrage ohne Datum hält deshalb 5 min
   (offener Rand, `adr/0005` Regel II), nicht 24 h wie der bisherige
   Weltüberblick (F3). Bei 0,3–1,2 s je Anfrage (§2) ist das tragbar. Mehr als
   ein Parameter `area=viewport` für die 24-h-Frist wäre nicht nötig; ich
   empfehle ihn erst, wenn die Last es zeigt (Frage F3).
2. **Log.** Der Ausschnitt ist keine AOI, aber eine Kartenposition. Die Route
   selbst loggt keine `bbox`, und seit M3-16 (in `main`) schreibt das
   Access-Log keinen Query-String mehr (`earthx/logging.py`) **[P]**. Ein
   Vitest prüft zusätzlich, dass die gerundete `bbox` nicht genauer ist als
   das Raster `L − 3`.

---

## 5. Messung z9 und z10 — [M]

Nur als Grundlage für eine Entscheidung über den Deckel; **der Deckel bleibt
z8**. Gleicher Aufbau wie §2 (1920 × 1080), je eine Anfrage:

| Ausschnitt | Stufe | Zellen | Antwort | Zeit | Anfragen | Regel V |
|---|---|---|---|---|---|---|
| Europa, Zoom 4 | z9 | 6 351 | 162 kB | 0,48 s | 1 | vollständig |
| Europa, Zoom 5 (Formel) | z9 | 2 092 | 53 kB | 0,22 s | 1 | vollständig |
| Europa, Zoom 5, + 25 % Rand | z9 | 3 980 | 101 kB | 0,43 s | 1 | vollständig |
| Afrika, Zoom 5 (Formel) | z9 | 1 920 | 50 kB | 0,34 s | 1 | vollständig |
| Europa, Zoom 5 | z10 | 5 732 | 147 kB | 0,41 s | 1 | vollständig |
| Europa, Zoom 6 (Formel) | z10 | 1 587 | 41 kB | 0,28 s | 1 | vollständig |
| Europa, Zoom 6, + 25 % Rand | z10 | 3 407 | 87 kB | 0,39 s | 1 | vollständig |
| Afrika, Zoom 6 (Formel) | z10 | 1 662 | 43 kB | 0,29 s | 1 | vollständig |

**Ergebnis:** Technisch kosten z9 und z10 im sichtbaren Ausschnitt nicht mehr
als z8: eine Anfrage je Ansicht, unter 0,5 s, weit unter Kappung und Schwelle.
Anders als der Weltüberblick (`adr/0010` §3.2) braucht der Ausschnitt keine
Zerlegung. Gegen z9/z10 spricht allein der fachliche Grund des Deckels
(`adr/0004` §5): Eine z9-Zelle ist rund 78 km breit, eine z10-Zelle rund
39 km. Ein Sentinel-2-Footprint misst 110 km, und die Zählung nach Mittelpunkt
zeichnet dort ein Punktmuster statt einer Abdeckung. Das ist nicht gemessen,
sondern aus der Geometrie abgeleitet **[A]**; ob es im Bild stört, zeigt nur
ein Blick auf die Karte.

**Last dieser Messung:** 25 Anfragen an `earth-search.aws.element84.com`
(1 Erreichbarkeitsprüfung, 24 × `/aggregate`), streng nacheinander, höchstens
1 Anfrage pro Sekunde, nur Metadaten, zusammen rund 4,1 MB. Kein Fehler, keine
Drosselung durch die Quelle. Messskript außerhalb des Repos.

---

## 6. Umsetzung (nach Freigabe)

| Datei | Änderung |
|---|---|
| `frontend/src/coverage.ts` | Formel aus §1; Runden des Ausschnitts auf das Raster `L − 3`; Band bei ±180°; Prüfung „liegt in geladener `bbox`“. Alles reine Funktionen. Der z6-Commit wird ersetzt |
| `frontend/src/store.ts` | `refreshCoverage` ohne AOI: Ausschnitt statt Welt, Stufe aus §1, kleiner Antwort-Cache (§3); mit AOI unverändert. Store hält Ausschnitt und Containergröße statt nur `mapZoom`. Kommentar über dem Ausschnitt anpassen |
| `frontend/src/components/MapView.tsx` | bei `moveend` Ausschnitt (`getBounds`) und Containergröße mitgeben |
| Tests | Vitest: Formel (Zoom 0, 1,6, 3,5, 20; kleiner und großer Container; Deckel), Runden, Band über ±180° und Weltkopien, Wiederverwendung (keine Anfrage bei kleiner Verschiebung, eine beim Stufenwechsel), mit AOI unverändert, ungültige Eingaben (Container 0 × 0, NaN-Zoom) |
| Backend | keine Änderung |
| Docs | `adr/0004` §5 Nachtrag „Ausschnitt statt Welt ohne AOI“ mit Verweis hierher |

Umfang: rund 150–250 Zeilen, unter dem Richtwert.

---

## 7. Fragen an Otto

1. **F1 — Zielzahl der Zellen.** (a) *Empfehlung:* `N = 2 000` (bei
   1920 × 1080 `L = Z + 4`, Zellen 23–45 px, gemessen höchstens 3 740 Zellen).
   (b) `N = 8 000` (`L = Z + 5`, Zellen 11–23 px, gemessen bis 7 000 Zellen, nah
   an der Kappung). (c) Stufe nur aus dem Zoom, ohne Containergröße
   (`L = round(Z) + 4`).
2. **F2 — Footprints ohne AOI.** Mit dem Ausschnitt kann die Quelle auch ohne
   AOI unter 500 Treffer melden, etwa bei engem Zeitraum und Zoom ≥ 4. (a)
   *Empfehlung:* dann Footprints zeigen, abgefragt mit derselben
   Ausschnitts-`bbox`, wie ENTSCHEIDUNGEN §2 („ab einer bestimmten Zoomstufe
   oder bei wenigen Aufnahmen“). (b) Footprints weiter nur mit AOI.
3. **F3 — Cache-Frist der Ausschnitts-Anfragen.** (a) *Empfehlung:* Route
   unverändert, 5 min. (b) Parameter `area=viewport`, ohne Datum und
   Wolkenfilter 24 h wie der bisherige Weltüberblick.
4. **F4 — Farbskala.** Die Farbstufen kommen aus dem Maximum der jeweiligen
   Antwort (`adr/0004` §5), ändern sich also beim Verschieben. (a)
   *Empfehlung:* so lassen, die Legende nennt das Maximum. (b) Skala je Stufe
   festhalten, bis Datensatz oder Zeitraum wechseln.
