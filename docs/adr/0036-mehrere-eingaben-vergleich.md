# ADR 0036 — Mehrere Eingaben: zwei Bilder verarbeiten und vergleichen

- **Status:** **Entwurf** (Stufe C), Fragen an Otto in §14. Die Nummer 0036 war beim Start frei: Auf `main` endet die Reihe mit 0035, der einzige offene PR (#368, M5-37) legt kein ADR an. Beim Merge prüfen, ob M5-31 sie inzwischen belegt.
- **Datum:** 2026-11-16
- **Aufgabe:** M5-26 laut `docs/plans/m5/m5-discovery-und-suche.md` §6.2, **vorgezogen und erweitert** (Otto, 11.11.2026, M5-Plan §2 Punkt 10): `adr/0030` F10 hatte diesen ADR für die Zeit nach M5-11 vorgesehen. Er entsteht jetzt, bevor die Zeitachse der Meteorologie steht; was davon abhängt, ist in §9 als Wiedervorlage markiert.
- **Autonomiestufe:** C. Kein Produktivcode.
  - Geändert sind nur dieses ADR und eine Zeile im Entscheidungslog.
  - Unverändert bleiben `backend/`, `frontend/`, Registry, Fixtures, M5-Plan, `.importlinter`, `.github/`, `.claude/`, `CODEOWNERS` und `CLAUDE.md`.
- **Vorab fest:**
  - Otto (11.11.2026): **zwei Bilder gleichzeitig verarbeiten und vergleichen**, ausdrücklich gleicher Datensatz zu zwei Zeitpunkten und zwei verschiedene Datensätze.
  - Sentinel-1 nur in Radargeometrie, solange es keine richtige Bearbeitung gibt (DS-04d, `adr/0018` §9.5).
  - Ein Ergebnis ist keine Eingabe; Weiterrechnen auf einem Ergebnis rechnet den ganzen Auftrag neu (`adr/0019` Option 2).
  - Darstellung als Vorgabe am Operator, nicht im Frontend je Datensatz (`adr/0035`).
  - Modulgrenzen (`architekturplan.md` 3.1), `gateway` für jeden Abruf (B8), Worker-Kern zustandslos (B9), jede Fähigkeit je Eintrag ausdrücklich (B10), Lizenzstufen (B11).
  - Neue Abhängigkeiten nur mit Otto (`adr/0014` K9).
- **Grundlage:**
  - `KLAERUNGEN.md` B8–B11; `projektuebersicht.md` Prinzipien (Ehrlichkeit, Registry statt Sonderfälle).
  - `architekturplan.md` 7.1 (Rezept, Lizenzkombination), 7.3 (Stufen T1/T2); `projektplan.md` Viewer-Strang VP1/VP2 und §5 („Vorher/Nachher“ bisher M7).
  - `adr/0014` §4–§6, §15k, §15m, §15u, §15v, Nachträge NM4-43c, M5-28, DS-04d; `adr/0018` §4.4, §9.5; `adr/0019`; `adr/0020`; `adr/0029` §5.4, §8a.2; `adr/0030` §5, §7, F10; `adr/0034` (Keys der Nutzer); `adr/0035`.
  - Pläne `plans/m5/m5-28-nodata-ergebnisse.md`, `plans/m5/ds-04d-radargeometrie.md`.
- **Betroffen (erst mit einer Entscheidung):** `processing` (Rezept, Planer, Kern, neue Operatoren), `api` (Annahme, Anwendbarkeit, Prozessbeschreibung, `tiler`), Runner, Registry (neue Capability und Block, §7), Frontend (Swipe, Processing-Panel mit Reitern UI-07, Ergebnis-Details).

---

## Methode und Belegstufen

Belegstufen wie in `adr/0030` und `adr/0034`:

- **M:** in dieser Sitzung gemessen, Verfahren im Text (§3.3).
- **P:** am Primärdokument gelesen, im Repo mit Pfad und Zeile.
- **S:** Suchtreffer oder Zusammenfassung, Wortlaut nicht geprüft. Ein Hilfsagent recherchierte den Stand der Technik; die Hosts von openEO, Google Earth Engine, Sentinel Hub und rioxarray waren aus der Sitzung nicht abrufbar. Alle Aussagen aus §4 tragen deshalb höchstens **S**.
- **A:** eigene Ableitung, ein Argument und kein Beleg.

**Keine Anfragen an Datenquellen.** Die Messung rechnet auf synthetischen Zahlen.

---

## 0. Kurzfassung

1. **Rezept mit zwei Zweigen (F1).** Jede der zwei Eingaben behält ihre eigene, heute schon gebaute Schrittfolge (Zweig). Danach folgt genau ein **Vergleichsschritt**, der beide auf ein Gitter bringt und verknüpft, dann wahlweise gemeinsame Schritte. Das ist ein eng begrenzter Graph („zwei Ketten, ein Knoten, eine Kette“), kein allgemeiner. Er bleibt mechanisch nach openEO übersetzbar.
2. **Ein Zielgitter, immer ausdrücklich im Rezept (F2).** Das Gitter einer der beiden Eingaben ist das Ziel (`like`); das Panel schlägt das gröbere vor. Sind beide Gitter gleich (gleicher Datensatz, gleiche Kachel), wird nichts resampelt; die Pixelpaare sind dann bitgleich die der Quelle. Ausschnitt ist die AOI; Pixel, die eine Eingabe nicht deckt, sind nodata nach M5-28.
3. **Vergleichsoperatoren (F3).** Ein Operator `compare` mit den Methoden Differenz, Verhältnis, Log-Ratio (dB), normierte Differenz und freiem Ausdruck über beide Eingaben; dazu immer die **Paarstatistik** (Mittel beider, Differenz, RMSE, Korrelation, gültige Pixel). Veränderungsklassen entstehen über einen allgemeinen Schritt `classify` mit **ausdrücklichen** Schwellen. `mask_by` (Klassen der einen Eingabe maskieren die andere) und `transition` (Klasse vorher → nachher) kommen im zweiten Schnitt.
4. **Was je Datensatz zulässig ist, steht in der Registry (F4).** Neue Capability `comparison` und ein Block `comparison` mit den Item-Eigenschaften, die gleich sein müssen, den zulässigen Partnern und den zulässigen Methoden. Ohne Eintrag kein Vergleich.
5. **Sentinel-1 rechnet vorerst keinen Vergleich (F5).** `adr/0018` §4.4 schließt den Vergleich über Bahnen **und Zeiten** aus, und in Radargeometrie liegen zwei Szenen nicht pixelgleich (DS-04d). Mit σ⁰ und Geländekorrektur (M5-31, DS-05d) oder einem RTC-Produkt: Log-Ratio, nur gleiche relative Bahn und Polarisation. Der Swipe (Anzeige) bleibt erlaubt.
6. **Kosten:** Rechnen ist fast gratis, Lesen kostet. Gemessen braucht die Differenz 0,02 s für 16,8 Mpx, das Angleichen 0,11–0,47 s [M]. Ein Vergleich liest zwei Quellen; Schätzung, Speicher und Grenzen zählen beide Zweige (§10).
7. **Anzeige (F7):** Zuerst der **Swipe** aus VP1 als reine Frontend-Aufgabe, für zwei beliebige Ebenen, ohne Rezept. Das Ergebnis eines Vergleichs ist ein Layer mit Look am Operator (`adr/0035`): divergierend und symmetrisch um 0 für Differenzen, Klassenfarben für `classify`.
8. **Vorschau (F6):** Die Kachel kann denselben Vergleich rechnen, wenn beide Zweige nur T1-Schritte haben. Beide Eingaben landen in der Kachel ohnehin auf demselben Gitter. Sie ist „Preview“ und teilt das Budget je Kachel.
9. **Bezug zu `adr/0019` (F8):** „Compare with…“ an einem Ergebnis-Layer baut aus den Aufträgen zweier Jobs einen Auftrag mit zwei Zweigen und rechnet neu. Es gibt kein Ergebnis per Referenz.
10. **Zeitschritte (F10):** Ein Zeitschritt der Meteorologie ist ein Item (`adr/0029` F2). Zwei Zeitschritte sind also zwei Eingaben desselben Datensatzes auf demselben Gitter, der einfachste Fall. Aggregation über viele Zeitschritte (Monatsmittel, Frosttage, Zeitkomposit) ist eine andere Operator-Art und bekommt nach M5-11 einen eigenen ADR.

---

## 1. Kontext und Frage

Heute verarbeitet ein Job genau eine Eingabe: eine Szene oder die Szenen eines Überflugs. Otto will zwei Bilder gleichzeitig verarbeiten und vergleichen. Die Fragen dieses ADR:

1. Wie sehen Rezept und Job mit mehreren Eingaben aus, und wie werden die Raster angeglichen (CRS, Auflösung, Ausschnitt, nodata)?
2. Welche Vergleichsoperatoren gibt es (Differenz, Verhältnis, Veränderung, Statistik beider)?
3. Was ist je Datensatz fachlich zulässig, und wo steht das?
4. Was kostet es, wo liegen die Grenzen?
5. Wie wird es angezeigt (nebeneinander, Swipe)?
6. Wie hängt es mit Zeitschritten (M5-11, NetCDF) und mit `adr/0014`, `adr/0019`, `adr/0035` zusammen?

**Fälle, an denen sich die Optionen messen lassen** (aus `adr/0030` §5, Baustein B6):

| # | Fall | Eingaben | Gitter | Frage |
|---|---|---|---|---|
| V1 | dNBR, dNDVI (Brand, Vegetation) | Sentinel-2, zwei Daten | gleich, wenn dieselbe MGRS-Kachel; sonst zwei UTM-Zonen | Index je Zeitpunkt, dann Differenz |
| V2 | Höhenänderung (Gletscher, Rutschung, Abbau) | swissALTI3D, zwei Stände | gleich (1-km-Kacheln LV95) | Differenz in m |
| V3 | Meteorologie Tag A gegen Tag B | MeteoSchweiz (M5-11), zwei Zeitschritte | gleich (1 km, LV95) | Differenz in °C oder mm |
| V4 | NDVI nur auf Ackerland | Sentinel-2 und WorldCover | 10 m UTM gegen ≈ 10 m EPSG:4326 | Maske aus Klassen der anderen Eingabe |
| V5 | Hochwasser | Sentinel-1, vor und nach dem Ereignis | Radargeometrie, nicht pixelgleich | Log-Ratio, gleiche Bahn |
| V6 | DEM gegen DEM | GLO-30 und swissALTI3D bzw. BEV | 30 m EPSG:4326 gegen 0,5 m LV95 | Differenz; verschiedene Höhenbezüge |
| V7 | Landbedeckung 2020 → 2021 | WorldCover 2020 und 2021 | gleich | Klassenwechsel; verschiedene Algorithmen |
| V8 | Zwei Bilder nur ansehen | beliebig | egal | Swipe, keine Rechnung |

---

## 2. Kriterien

| | Kriterium |
|---|---|
| K1 | Deckt die Fälle V1–V4 und V8 ohne Sonderfall; V5–V7 lassen sich sperren |
| K2 | Kern rein: alles Nötige im Rezept, Hash und Cache wie `adr/0014` §4.4–§4.5, Runner unverändert offline |
| K3 | Ehrlichkeit: jedes Resampling steht im Rezept, im Methodentext und im Panel |
| K4 | Zulässigkeit aus der Registry, nie aus Code je Datensatz (B10, M5-Plan §2 Punkt 7) |
| K5 | Wiederverwendung: bestehende Operatoren, Planer, Blockschleife, nodata-Regel, Looks |
| K6 | Kosten vor dem Start bekannt; Grenzen gelten für beide Eingaben zusammen |
| K7 | Unbekanntes abweisen, mit Grund (`422`, `UnsupportedRecipe`) |
| K8 | Überschaubar (`adr/0014` K9); keine neue Abhängigkeit ohne Otto |
| K9 | Offen für mehr als zwei Eingaben und für Zeitreihen, ohne sie jetzt zu bauen |

---

## 3. Befunde

### 3.1 Code [P]

- **Schema kennt mehrere Eingaben, der Kern nicht.** `RecipeRequest.inputs` und `Recipe.inputs` sind Listen (`processing/recipe.py:460`, `:486`), Namen eindeutig (`:445`). `check_scope` weist jedes Raster-Rezept mit mehr als einer Eingabe oder Gruppe ab: „a raster run reads one group of one input“ (`processing/core.py:248`); der Export ebenso (`processing/export.py:307`). `adr/0014` §4.2 hielt mehrere Datensätze im Schema ausdrücklich offen.
- **Schritte sind eine Kette** über der einen Eingabe (`adr/0014` §4.1, R1); `api` begrenzt sie auf 16 (`api/intake.py:178`, `MAX_ORDER_STEPS`).
- **Operator-Arten** `pixel`, `focal`, `grid` (`processing/operators/base.py:246`); `grid` läuft nur in T2 und schreibt eine lokale Arbeitsdatei (`processing/core.py:346–378`, M4-07a F3).
- **Mosaik eines Überflugs** ist eine Gruppe mehrerer Items einer Eingabe (`processing/mosaic.py:135`). Jede Eingabe eines Vergleichs kann also schon heute ein Mosaik sein.
- **Grenzen eines Jobs:** 1,5 GB geschätzter Speicher (`processing/plan.py:125`; 300 MB Basis, 33 MB je Band, `:131–:141`), 5 GB rohe Ausgabe (`access/crop_rules.py:124`, das Arbeitsverzeichnis braucht bis etwa das Doppelte).
- **Registry:** `Capabilities` ohne Vorgabe (`catalog/registry.py:340–367`); `reprojection` und `interpolation` getrennt; WorldCover nur `nearest` (`catalog/datasets/esa-worldcover-2020.yaml:65–68`); Sentinel-1 `reprojection: false`, `georeferencing: gcp_tps` (`sentinel-1-grd.yaml:42`, `:63`).
- **Eigenheiten der Einträge, die einen Vergleich betreffen:**
  - WorldCover 2020 und 2021 sind zwei Einträge; die Beschreibung sagt selbst: „made with different algorithm versions and are not directly comparable“ (`esa-worldcover-2020.yaml:15`).
  - swissALTI3D lädt **nur den jüngsten Stand** je Kachel; eine Fläche mischt Stände verschiedener Jahre (`swissalti3d.yaml:16–18`). V2 braucht also zuerst ältere Stände (vorgemerkt im M5-Plan §6.2, ohne Nummer).
  - Höhenbezüge: swissALTI3D LN02 (`swissalti3d.yaml:16`), BEV „Meter über Adria“ (`bev-als-dgm.yaml:14–15`), GLO-30 ohne Angabe im Eintrag.
  - Sentinel-2 trägt weder `sat:relative_orbit` noch `sat:orbit_state` (`sentinel-2-c1-l2a.yaml:304`); Sentinel-1 führt `sat:relative_orbit` als Filter (`sentinel-1-grd.yaml:218`).

### 3.2 Entscheidungen, die schon gelten [P]

- **Physikalische Werte** in Band-Math (`adr/0014` F7, F7a): Skalierung und Offset aus `raster:bands` je Item. Das deckt den Wechsel der Sentinel-2-Prozessierung ab, wenn das Item seinen Offset trägt (§4.3).
- **nodata (M5-28):** Gleitkomma → NaN; Ganzzahl: Randwert, Verschieben bei Kollision, Klemmen. Die Regel gilt für jeden Weg, der Dateien schreibt, also auch für einen Vergleich.
- **Kein Ergebnis per Referenz** (`adr/0019`, Option 2): Der Gewinn wäre Rechenzeit, der Preis Fassung, Ablauf, Runner, Permalink und Herkunft.
- **Looks am Operator** (`adr/0035`): `Look(colormap, scale, low, high)` mit `scale` ∈ `measured`, `percentiles`, `fixed`; das Frontend liest `x-earthx-looks`.
- **Sentinel-1 GRD:** Band-Math nur innerhalb einer Szene; „Mosaik oder Vergleich über Bahnen und Zeiten: nein“ (`adr/0018` §4.4); Ergebnisse in Radargeometrie ohne CRS (§9.5).
- **NetCDF:** ein Item je Zeitschritt, Variablen als Assets (`adr/0029` F2, F6). Zwei Zeitschritte sind zwei Items.

### 3.3 Messung: Rechnen gegen Angleichen [M]

Synthetisch, ein Thread, im Speicher, ohne Blockplan und ohne Datei-I/O. rasterio 1.5.2, GDAL 3.12.2, numpy 2.5.3, numexpr. Zwei `float32`-Raster mit 4096 × 4096 Pixeln (16,8 Mpx, bei 10 m 1 678 km², 67 MB je Band). Bestes von drei Läufen.

| Rechnung | Zeit |
|---|---|
| Differenz `b − a` | 0,020 s |
| Verhältnis `b / a` | 0,020 s |
| Log-Ratio `10·log10(b/a)` (numexpr) | 0,039 s |
| normierte Differenz (numexpr) | 0,017 s |
| Paarstatistik (Maske, Mittel, Std, RMSE, Korrelation in float64) | 0,63 s |
| Warp 30 m → 10 m, `nearest` / `bilinear` / `cubic` | 0,27 / 0,37 / 0,47 s |
| Warp 10 m → 30 m, `nearest` / `bilinear` / `average` | 0,11 / 0,20 / 0,23 s |
| Warp UTM 32N → EPSG:2056, 10 m, `bilinear` | 0,18 s |

**Folgerung [A]:** Die Verknüpfung ist gegenüber Lesen und Angleichen vernachlässigbar. Die Statistik in float64 kostet mehr als die Rechnung selbst; im Job läuft sie ohnehin blockweise (`adr/0014` §15k). Die Werte aus `adr/0014` §5.5 (Reprojektion `bilinear` 9,0 s für 64 Mpx) liegen je Mpx etwa fünfmal höher, weil sie Blockplan und Datei-I/O enthalten. Für die Schätzung gelten weiter die Faktoren aus `adr/0014`.

---

## 4. Stand der Technik [S]

### 4.1 Mehrere Eingaben und Zielgitter

Alle betrachteten Systeme bringen die Eingaben vor dem Rechnen auf **ein** Gitter, das entweder ausdrücklich genannt oder von einem Referenzobjekt übernommen wird:

| System | Wer bestimmt das Gitter | Resampling |
|---|---|---|
| openEO | Nutzer: `resample_cube_spatial` auf das Gitter eines Ziel-Cubes oder `resample_spatial`, danach `merge_cubes` mit `overlap_resolver` | je Aufruf, z. B. `near`, `average` (Q1, Q2) |
| Google Earth Engine | die Ausgabe (Anfrage, Anzeige, Export); `reproject` „rarely needed“ | Vorgabe nearest, `resample()`, `reduceResolution()` zum Aggregieren (Q3) |
| Sentinel Hub | die Anfrage (Ausschnitt, CRS, Auflösung); mehrere `input.data` (Data Fusion) | NEAREST, BILINEAR, BICUBIC (Q4) |
| odc-stac | `crs` + `resolution` oder `like`/`geobox` | Parameter `resampling` (Q5) |
| rioxarray | `reproject_match` übernimmt Gitter und Ausschnitt eines Referenzrasters | Vorgabe nearest (Q6) |
| GDAL | ausdrücklich: `-t_srs`, `-tr`, `-te`, `-tap` | `-r`, Vorgabe `near` (Q7) |

- Eine feste Regel „feinste“ oder „gröbste“ Eingabe fand sich in keiner Quelle; die Wahl liegt beim Nutzer oder beim Referenzobjekt.
- **Kategoriale Daten** nie bilinear oder kubisch (Q8); kontinuierliche beim Vergröbern mit `average`.
- **Stolperstein:** `resample_cube_spatial` schneidet bei manchen openEO-Backends zu, ohne dass die Definition es sagt (Q9). Das spricht für ein Gitter, das das Rezept selbst vollständig beschreibt.

### 4.2 Kosten und Grenzen

- GDAL zerlegt den Warp in Teile, wenn Ein- und Ausgabe die Warp-Speichergrenze überschreiten (Q7). Die Plattform macht dasselbe mit eigener Blockschleife (`adr/0014` §3.4, F10).
- Sentinel Hub: Process API laut FAQ bis 2 500 × 2 500 Pixel Ausgabe, asynchron bis 10 000 je Seite (Q10, nicht primär belegt). Eine Processing Unit ist 512 × 512 Pixel mit drei Eingabebändern; Data Fusion zählt mehr (Q11).
- Google Earth Engine: „User memory limit exceeded“ als typischer Fehler; Gegenmittel `scale`, `maxPixels`, `tileScale`, Export (Q12). Zahlen nicht belegt.
- **Verfahren nach Aufwand [A]:** Differenz, Verhältnis, Log-Ratio und normierte Differenz sind pixelweise O(N) wie Band-Math. Change Vector Analysis ist O(N·Bänder). Statistische Tests für SAR (Wishart, Conradsen et al.) brauchen Kovarianzmatrizen, also mindestens Dual-Pol-SLC und Multilooking. ML-Verfahren brauchen Modelle und sind eine andere Größenordnung.

### 4.3 Fachliche Regeln für Veränderung

- **Optik:** dNBR mit Sentinel-2 (B8A, B12) und Einteilung nach Schwellen (Q13); `adr/0030` §5.1 hält schon fest, dass Schwellen lokal zu prüfen sind. Change Vector Analysis: Betrag als Distanz im Merkmalsraum, Richtung als Winkel (Q14).
- **Sentinel-2 über die Zeit:** Ab Processing Baseline 04.00 (25.01.2022) gilt ρ = (DN + BOA_ADD_OFFSET)/10 000 mit Offset −1000. Maßgeblich ist die Baseline des Produkts, nicht das Aufnahmedatum (Q15). Mit physikalischen Werten aus dem Item (§3.2) ist das abgedeckt, **sofern** das Item den Offset seiner Baseline trägt; das ist an je einer Szene vor und nach 2022 zu prüfen (`adr/0030` §5.1 nennt dieselbe Prüfung).
- **SAR:** Verhältnis statt Differenz; der Quotient der Intensitäten ist eine Likelihood-Ratio-Teststatistik, Differenzen haben in hellen Flächen größere Varianz (Q16). Hochwasser: Nachher durch Vorher, in dB, geglättet, gleiche Überflugrichtung (Q17); gleiche relative Bahn (Q18). Gleiche Polarisation ist fachlich zwingend [A].
- **Wishart-Tests** (Conradsen et al. 2003, 2016) gelten für polarimetrische Kovarianzen (Q19), nicht für GRD-Amplituden.

### 4.4 Anzeige

| Bibliothek | Prinzip |
|---|---|
| `@maplibre/maplibre-gl-compare` | zwei synchronisierte Karten, Regler dazwischen (Q20) |
| `leaflet-side-by-side` und Abkömmlinge | eine Karte, Layer links und rechts beschnitten (Q21) |
| OpenLayers „Layer Swipe“ | eine Karte, `ctx.clip()` vor dem Zeichnen bzw. `gl.scissor()` bei WebGL (Q22) |

MapLibre hat keine Beschneidung je Layer in der API [A]; für das Frontend der Plattform (MapLibre) liegt daher das Muster mit zwei Karten nahe.

### 4.5 Zeitachse

openEO löst „vorher gegen nachher“ mit zwei Cubes verschiedener Zeitfilter, je über `t` reduziert, dann subtrahiert (Q23). Zeitachsen in NetCDF folgen CF (`units` wie `days since …`, Q24). Das ist dasselbe Muster wie zwei Eingaben eines Datensatzes [A].

---

## 5. Rezept und Job

### 5.1 Optionen

| | R-A gemeinsame Kette | **R-B zwei Zweige, ein Vergleichsschritt** | R-C allgemeiner Graph | R-D zwei Jobs, Vergleich auf den Ergebnissen |
|---|---|---|---|---|
| Form | `inputs: [a, b]`, alle Schritte nach dem Angleichen auf dem gemeinsamen Stapel | je Eingabe eine Kette (`inputs[i].steps`), dann `combine`, dann gemeinsame Kette | openEO-Prozessgraph | Ergebnis per Referenz als Eingabe |
| K1 V1 (Index je Zeitpunkt) | ~ nur als ein langer Ausdruck über beide | ✓ derselbe Index-Schritt in beiden Zweigen | ✓ | ✓ |
| K1 V4 (Wolkenmaske je Datum, Maske aus anderem Datensatz) | ✗ `mask` weiß nicht, welche Eingabe | ✓ `mask` im Zweig | ✓ | ✓ |
| K4 Anwendbarkeit | ✗ ein Schritt nach dem Angleichen gehört zu keinem Datensatz | ✓ jeder Zweig wie heute gegen seinen Datensatz, der Vergleich gegen die Paarregel (§7) | ~ je Knoten herzuleiten | ✓ |
| K5 Wiederverwendung | ✓ | ✓ jeder Zweig ist ein heutiges Rezept ohne Ausgabe | ✗ | ✗ |
| K2 Hash, Runner | ✓ | ✓ | ✓ | ✗ (`adr/0019` §5) |
| K8 überschaubar | ✓ | ✓ fester Aufbau | ✗ (`adr/0014` R3) | ✗ |
| K9 offen | ~ | ✓ N Zweige später möglich | ✓ | ~ |

**Empfehlung R-B.** Jeder Zweig ist genau das, was der Kern heute rechnet; neu sind nur der Vergleichsschritt und die gemeinsame Kette dahinter. R-A scheitert an der Anwendbarkeit: `mask` (Klassen des Datensatzes) oder `terrain` hätten nach dem Angleichen keinen Datensatz mehr. R-C bleibt aus den Gründen von `adr/0014` §4.1 verworfen; R-D aus denen von `adr/0019`.

### 5.2 Skizze (Vorschlag, nicht gebaut)

```json
{
  "recipe_version": 3,
  "inputs": [
    {"name": "a", "dataset": "sentinel-2-c1-l2a", "groups": [["<item-2023>"]], "resolved": ["…"],
     "steps": [{"op": "mask", "op_version": 2, "params": {"…": "SCL-Wolken"}},
               {"op": "band_math", "op_version": 2, "params": {"expression": "(nir08-swir22)/(nir08+swir22)", "name": "nbr"}}]},
    {"name": "b", "dataset": "sentinel-2-c1-l2a", "groups": [["<item-2024>"]], "resolved": ["…"],
     "steps": ["… dieselben zwei Schritte …"]}
  ],
  "aoi": {"type": "Polygon", "coordinates": ["…"]},
  "combine": {
    "op": "compare", "op_version": 1,
    "params": {"method": "difference", "pairs": [["nbr", "nbr"]], "names": ["dnbr"]},
    "grid": {"like": "a", "resampling": {"b": "bilinear"}}
  },
  "steps": [{"op": "classify", "op_version": 1, "params": {"breaks": [-0.1, 0.1, 0.27, 0.44, 0.66]}}],
  "output": {"kind": "raster", "format": "cog", "dtype": "float32", "bands": ["dnbr"]}
}
```

- **Genau zwei Eingaben** mit den festen Namen `a` und `b`; `a` ist der frühere Zeitpunkt bzw. der zuerst gewählte Datensatz. Die Differenz ist immer `b − a` („nachher minus vorher“).
- **Zweige:** `inputs[i].steps` nimmt die heutigen Operatoren, je gegen den eigenen Datensatz geprüft. Ein Zweig ohne Schritte liefert seine Bänder unverändert.
- **`combine`** ist Pflicht bei zwei Eingaben und verboten bei einer. Er trägt Operator, Version, Parameter und das Zielgitter (§6).
- **`steps`** danach sind gemeinsame Schritte auf dem Ergebnis des Vergleichs. Zugelassen nur Operatoren ohne Datensatzbezug: `band_math`, `normalize`, `mask_values`, `classify`, `reproject`; nicht `mask` und keine Operatoren mit datensatzgebundener Capability (`terrain`, `sar_db`).
- **Version:** `recipe_version` 3. Rezepte mit einer Eingabe bleiben bytegleich, wenn `steps` je Eingabe und `combine` bei Nichtgebrauch aus dem Dump fallen (Muster von `footprints`, `line_times`, `processing/recipe.py:424`); ob der Kern 2 und 3 annimmt oder Aufträge mit einer Eingabe weiter als 2 schreibt, legt die Umsetzung fest [A].
- **Hash und Cache** wie `adr/0014` §4.5: beide Eingaben mit Fassung, beide Zweige, `combine` mit Gitter. Treffer nur, wenn **beide** Eingaben eine Fassung tragen (Q11 aus M4).
- **Grenzen der Schritte:** 16 gilt für die Summe aller Schritte (zwei Zweige, Vergleich, gemeinsame Kette).

### 5.3 Ablauf im Kern [A]

1. **Zweig a, Zweig b:** je ein heutiger Lauf bis zur Arbeitsdatei, mit dem Unterschied, dass das Lesefenster schon das Zielgitter kennt (nur der Teil der AOI, nur dieser Ausschnitt).
2. **Angleichen:** die Eingabe, die nicht `like` ist, wird auf das Zielgitter gewarpt, blockweise wie `reproject` (Arbeitsdatei). Gleiches Gitter → kein Warp.
3. **Vergleich:** ein Pixel-Durchgang über beide Arbeitsdateien in Blöcken von 1024 px, nodata vereinigt (§6.3), Paarstatistik in demselben Durchgang.
4. **Gemeinsame Kette, Ausgabe, Statistik** wie heute.

Der Worker-Kern bleibt zustandslos (B9); die Arbeitsdateien sind lokal und verschwinden mit dem Lauf. Der Runner rechnet dasselbe mit beiden Hosts in der Allowlist (`adr/0016` F4).

### 5.4 Job, Herkunft, Lizenz

- **Ein Job**, nicht zwei; Fortschritt über beide Zweige.
- **Herkunft:** `derived_from` auf beide Items, Attribution beider Datensätze (je „modified“), Zitierangabe beider, Methodentext je Zweig und Vergleich (`adr/0014` §15r).
- **Lizenz:** beide Eingaben brauchen die Stufe *Processing* (B11). Die Kombination prüft `api` bei der Annahme (`architekturplan.md` 7.1); die strengere Bedingung gilt für das Ergebnis (z. B. `commercial_use = false`).
- **Keys der Nutzer (`adr/0034`):** braucht eine Eingabe einen Key, gilt die Freigabe je Lauf für diesen Zweig; der Vergleich mit einer freien Eingabe ändert daran nichts. Für den Ergebnis-Link gilt die Bedingung aus `adr/0034` F6 für jede Eingabe.

---

## 6. Angleichen der Raster

### 6.1 Zielgitter: Optionen

| | G1 **ausdrücklich, `like` einer Eingabe, Panel schlägt das gröbere vor** | G2 immer Eingabe a | G3 immer das feinste | G4 freies Gitter (CRS, Auflösung) |
|---|---|---|---|---|
| Ehrlichkeit (K3) | ✓ steht im Rezept | ✓ | ✓ | ✓ |
| fachlich | ✓ Vergröbern erfindet keine Details | ~ hängt von der Reihenfolge ab | ✗ 30 m auf 0,5 m erfindet Details und vervielfacht die Pixel | ✓ |
| Kosten | ✓ meist das kleinere Raster | ~ | ✗ swissALTI3D gegen GLO-30: 3 600-mal so viele Pixel wie GLO-30 [A] | ~ zwei Warps |
| Einfachheit | ✓ ein Warp | ✓ | ✓ | ~ |

**Empfehlung G1.** `grid.like` nennt die Eingabe, deren Gitter (CRS, Pixelgröße, Ausrichtung, nach ihrem Zweig) das Ziel ist. Das Panel setzt die Eingabe mit der größeren Pixelfläche ein; bei Gleichstand `a`. Ein abweichendes Ziel geht über einen `reproject`-Schritt im Zweig (G4 bleibt damit möglich, ohne eigenes Feld). Das entspricht `reproject_match` bzw. `like` bei odc-stac (§4.1).

### 6.2 Resampling

- `grid.resampling` nennt die Methode **für die Eingabe, die gewarpt wird**; ohne Vorgabe im Kern (K7). Das Panel schlägt vor:
  - kategorial (Datensatz mit Klassen in `mask` oder `interpolation: false`): `nearest`; beim Vergröbern `mode` [A, `mode` in rasterio vorhanden, Empfehlung für Klassen aus §4.1 nicht primär belegt];
  - kontinuierlich, vergröbern: `average`;
  - kontinuierlich, verfeinern: `bilinear`.
- Die Methode muss für den gewarpten Datensatz zulässig sein (`reprojection`, außer `nearest` auch `interpolation`; `adr/0014` F6). Sentinel-1 ist damit ohnehin ausgeschlossen (`reprojection: false`).
- **Gleiches Gitter:** gleiche CRS, gleiche Pixelgröße und ein ganzzahliger Pixelversatz → kein Warp, nur ein Fenster. Der Methodentext nennt dann kein Resampling.
- Wird gewarpt, nennt das Ergebnis es (Prinzip Ehrlichkeit, `adr/0014` §5.6): Feld im STAC-Item und Zeile im Methodentext.

### 6.3 Ausschnitt und nodata

- **Ausschnitt:** die AOI, gerastert auf das Zielgitter (wie heute bei einer Eingabe). Ohne AOI: Schnitt der Footprints beider Eingaben.
- **Gültig** ist ein Pixel nur, wenn es in **beiden** Eingaben gültig ist. Außerhalb eines Footprints oder bei nodata in einer Eingabe wird das Ergebnis nodata. Ergebnistyp und nodata folgen M5-28: Differenz, Verhältnis, Log-Ratio → `float32` mit NaN; `classify` → Ganzzahl mit Randwert als nodata.
- **Division:** `b/a` mit `a = 0` ergibt nodata, nicht ±∞; Log-Ratio mit einem Wert ≤ 0 ebenso. Das ist die Regel von Band-Math (`0/0`, `x/0` → maskiert, `processing/operators/band_math.py:26`, `:275`), auf beide Eingaben übertragen [A].
- **Leere Schnittmenge:** `api` prüft vor der Annahme aus den Footprints, dass AOI, a und b sich überlappen; sonst `422` mit Grund.
- **Anteil gültiger Pixel** steht in der Paarstatistik; das Panel kann unter einem Anteil warnen (Tooltip), nicht abweisen.

### 6.4 Bänder

- `pairs` ordnet je ein Band aus a einem aus b zu. Gleicher Datensatz: Vorgabe gleiche Namen. Verschiedene Datensätze: der Nutzer wählt.
- **Einheiten:** Differenz nur zwischen Bändern gleicher Einheit (`band_units`, `adr/0014` §15n); das Ergebnis trägt diese Einheit. Verhältnis und normierte Differenz sind einheitenlos, Log-Ratio in dB. Ein Band aus Band-Math ohne Einheit lässt nur einheitenlose Methoden zu [A].
- **Namen** der Ausgabe vorbelegt und änderbar (`d_<band>`, `r_<band>`), wie Ottos Regel für bandverändernde Schritte (M5-Plan §6.2, M5-34; `adr/0020`).

---

## 7. Zulässigkeit je Datensatz (Registry)

### 7.1 Optionen

| | Z1 **Capability `comparison` plus Block `comparison`** | Z2 nur derselbe Datensatz | Z3 jede Paarung, Hinweis im Tooltip |
|---|---|---|---|
| B10 ausdrücklich | ✓ | ✓ | ✗ |
| V4 (Sentinel-2 mit WorldCover) | ✓ | ✗ | ✓ |
| Sperre V5–V7 | ✓ | ~ V6 und V7 sind verschiedene Einträge, V5 nicht | ✗ |
| Aufwand | Block je Eintrag | ein Flag | keiner |

**Empfehlung Z1.**

### 7.2 Block `comparison` (Vorschlag, alle Felder Pflicht, wenn das Flag gesetzt ist)

| Feld | Inhalt | Beispiel |
|---|---|---|
| `match` | Item-Eigenschaften, die bei einem Vergleich **mit sich selbst** gleich sein müssen; `api` prüft sie bei der Annahme | Sentinel-1 (später): `sat:relative_orbit`, Polarisationen, `sar:instrument_mode` |
| `methods` | zulässige Methoden von `compare` mit sich selbst | Sentinel-2: alle; SAR: nur `ratio`, `log_ratio` |
| `partners` | andere Einträge, mit denen verglichen werden darf, je mit `methods` | Sentinel-2 → WorldCover mit `mask_by` |
| `quantity` | was ein Band misst, wo es für Paarungen über Datensätze zählt (Höhe mit Höhenbezug, Reflexion, Temperatur) | DEM: `height`, `vertical_datum: LN02` |

- **Prüfung beim Start** (wie `step_presets`): `partners` nennt nur Einträge mit gesetztem Flag; jede Partnerschaft steht auf beiden Seiten (sonst Startfehler); Methoden passen zu den Bändern.
- **Was nicht geht, erscheint nicht** (M5-Plan §6.5): Das Panel zeigt „Compare with…“ nur für Datensätze mit Flag und als Partner nur, was `partners` nennt.

### 7.3 Vorschlag je Datensatz

| Datensatz | `comparison` | mit sich selbst | Partner | Begründung |
|---|---|---|---|---|
| `sentinel-2-c1-l2a` | ja | alle Methoden; `match` leer | WorldCover (`mask_by`, zweiter Schnitt) | georeferenziert, physikalische Werte; verschiedene Kacheln und Zonen gehen über den Warp |
| `sentinel-1-grd` | **nein** (F5) | — | — | `adr/0018` §4.4: kein Vergleich über Bahnen und Zeiten; DN unkalibriert; Radargeometrie nicht pixelgleich (DS-04d) |
| `cop-dem-glo-30` | nein | — (ein Stand, `single_coverage_product`) | — vorerst (F9) | Höhenbezug fehlt im Eintrag |
| `swissalti3d` | ja, **sobald ältere Stände geladen sind** | `difference`; `match` leer | — vorerst (F9) | gleicher Höhenbezug, gleiches Gitter; heute nur der jüngste Stand je Kachel (§3.1) |
| `bev-als-dgm` | nein | — (ein Stand) | — vorerst (F9) | wie GLO-30 |
| `esa-worldcover-2020`, `-2021` | ja, nur als Partner | — | Sentinel-2 (`mask_by`) | 2020 gegen 2021 nicht: verschiedene Algorithmen, vom Eintrag selbst gesagt (F12) |
| MeteoSchweiz (M5-11) | ja | `difference`, `ratio` je Größe | — | gleiches Gitter je Datensatz; Wiedervorlage mit M5-11 |

---

## 8. Vergleichsoperatoren

### 8.1 Optionen für den Umfang

| | O1 **`compare` mit festen Methoden und freiem Ausdruck, `classify` allgemein** | O2 nur Band-Math über beide Eingaben | O3 wie O1, dazu Change Vector Analysis und SAR-Tests |
|---|---|---|---|
| K3 Ehrlichkeit | ✓ Methode benannt, Look je Methode | ~ Ausdruck ohne Bedeutung | ✓ |
| K4 Registry | ✓ `methods` je Datensatz | ✗ nur alles oder nichts | ✓ |
| Kosten | O(N) | O(N) | CVA O(N·Bänder); SAR-Tests brauchen Daten, die es nicht gibt |
| Nutzen jetzt | V1–V4 | V1–V3 | wie O1 |

**Empfehlung O1.**

### 8.2 Operator `compare` (Art `combine`, neu)

| Methode | Formel | Einheit | Look (`adr/0035`) | Bemerkung |
|---|---|---|---|---|
| `difference` | `b − a` | wie die Eingabe | `rdbu`, symmetrisch um 0 | dNDVI, dNBR, Höhenänderung, Temperatur |
| `ratio` | `b / a` | — | divergierend um 1, logarithmisch | |
| `log_ratio` | `10·log10(b/a)` für Leistung bzw. `20·…` für Amplitude, aus `sar_quantity` (`adr/0030` §8) | dB | `rdbu`, symmetrisch um 0 | SAR, erst mit σ⁰ |
| `normalized_difference` | `(b − a)/(b + a)` | — | `rdbu`, fest −1…1 | |
| `expression` | Band-Math über `a_<band>` und `b_<band>`, gleiche Prüfung wie `band_math` | keine | wie Band-Math | für alles andere |
| `mask_by` (zweiter Schnitt) | Werte von a, wo b in den gewählten Klassen liegt | wie a | wie a | b braucht `mask`; `nearest`/`mode` |
| `transition` (zweiter Schnitt) | `a·256 + b` als `uint16`, Tabelle „von → nach“ | Klassen | Klassenfarben | nur gleiche Legende, nicht für WorldCover (F12) |

- **Looks:** „symmetrisch um 0“ ist eine neue Art von `scale` (± größter Betrag aus 2. und 98. Perzentil); Ergänzung zu `adr/0035` §4 Punkt 4 [A].
- **T1:** alle Methoden außer `transition` sind Pixel-Rechnungen und damit kachelfähig (§11).

### 8.3 Paarstatistik

Jeder Vergleich schreibt in die Eigenschaften des Ergebnisses: gültige Pixel beider und gemeinsam; Mittel, Std, Min, Max von a, b und Ergebnis; RMSE und Korrelation (Pearson) von a und b. Sie läuft im selben Blockdurchgang wie die heutige Statistik (`adr/0014` §15k). Die Details eines Ergebnisses zeigen sie; eine Ausgabe „nur Statistik, kein Raster“ ist eine spätere Ergänzung [A].

### 8.4 Veränderung: `classify` statt eigener Methode

- `classify` ist ein allgemeiner Pixel-Operator (eine Eingabe): Grenzen `breaks` aufsteigend, Ausgabe Klasse 1…n in Ganzzahl, Look mit Klassenfarben, Namen optional.
- Er dient der Veränderung (Abnahme / keine / Zunahme bei Schwellen ±t), der Brandschwere (dNBR) und allem anderen, das ein Band in Stufen teilt.
- **Keine Vorgabeschwellen im Operator.** Schwellen aus der Literatur kommen nur als Schritt-Preset eines Datensatzes (`step_presets`, `adr/0030` F7) mit Quelle, und nur wo sie fachlich gelten (nicht auf DN, `adr/0018` §4.4).

### 8.5 Nicht empfohlen

- **Change Vector Analysis** jetzt: Nutzen nur mit mehreren Bändern gleicher Bedeutung; über `expression` als Betrag nachbildbar. Wiedervorlage bei Bedarf.
- **Wishart- und andere SAR-Tests:** brauchen Kovarianzen (SLC, Quad- oder Dual-Pol); es gibt keine solche Quelle ohne Key (`adr/0030` §5.2.3). Nicht generalisieren (`decomp.py`-Regel sinngemäß).
- **ML-Verfahren:** M7 (`projektplan.md` §5).

---

## 9. Zeitschritte (M5-11, NetCDF)

- **Zwei Zeitschritte** eines Meteorologie-Datensatzes sind zwei Items (`adr/0029` F2), also zwei Eingaben desselben Datensatzes auf demselben Gitter. Kein Warp, bitgleiche Pixelpaare; das ist V3 und der billigste Fall.
- **Wiedervorlage mit M5-11:** ob Variablen eines Zeitschritts als Assets eines Items vorliegen (`adr/0029` F6) und ob `TminD`/`TmaxD` zusammenliegen; davon hängt ab, ob „Tmax(b) − Tmax(a)“ ein Paar oder ein Ausdruck ist.
- **Aggregation über viele Zeitschritte** (Monatsmittel, Frosttage nach ETCCDI, wolkenfreies Zeitkomposit, Zeitreihe am Punkt aus VP1) ist eine **Reduktion über eine Gruppe von Items**, keine Paarung. Das heutige Feld `groups` (Items einer Eingabe) könnte sie tragen; dazu kommt eine Operator-Art „Reduktion über die Zeit“ im Zweig. Das bleibt einem eigenen ADR nach M5-11 vorbehalten, wie `adr/0030` F10 es vorsah.
- **Offenheit (K9):** R-B schließt N Eingaben nicht aus; die Grenze „genau zwei“ steht im Validator, nicht im Schema.

---

## 10. Kosten und Grenzen

### 10.1 Schätzung

- Einheiten (`adr/0014` §5.5): Summe der Zweige (je Megapixel ihres Lesefensters × Faktoren) + Warp der nicht-`like`-Eingabe (Faktor `reproject` je Methode, Pixel des Zielgitters) + `compare` (Faktor 1,0 wie Band-Math, Messung §3.3) + gemeinsame Kette.
- Dauer: dazu je Eingabe die Öffnungszeit über das Netz (`adr/0014` §5.5: etwa 1 s je Asset).
- Die Schätzung nennt den Warp ausdrücklich (Nachtrag NM4-65: „was der Job still auf ein Raster umrechnet“).

### 10.2 Grenzen

| Grenze | heute | mit zwei Eingaben (Vorschlag) |
|---|---|---|
| Speicher je Job | 1,5 GB geschätzt | Bänder beider Zweige zählen zusammen; die Formel bleibt |
| Ausgabe je Job | 5 GB roh | unverändert für die Ausgabe; die Arbeitsdateien beider Zweige zählen zusätzlich gegen ein Arbeitsverzeichnis von höchstens dem Dreifachen [A] |
| Schritte | 16 | 16 über alles |
| Gleichzeitige Läufe je Host | `adr/0013`, `hosts.yaml` (M5-36) | ein Job mit zwei Hosts belegt auf beiden einen Platz; gleicher Host: ein Platz |
| Kachel (Vorschau) | 4 s, 32 Dateien je Kachel (M5-30b) | Summe beider Eingaben innerhalb desselben Budgets |

**Beispiele [A]:** V1 mit 100 km² Sentinel-2 bei 10 m: 2 × 1 Mpx, unkritisch. V2 mit 100 km² swissALTI3D bei 0,5 m: 2 × 400 Mpx, 1,6 GB je `float32`-Band und Zweig; das passt nur knapp unter die Grenzen. Das Panel sollte dort das 2-m-Asset vorschlagen (`adr/0030` §5.4).

---

## 11. Vorschau in der Kachel (T1)

| | T-A **Vorschau, wenn beide Zweige und der Vergleich T1 sind** | T-B nur Job |
|---|---|---|
| Nutzen | Ergebnis vor dem Start sehen, wie heute bei Band-Math | erst nach dem Job |
| Aufwand | `tiler` liest zwei Eingaben; das Angleichen ist frei, weil beide ohnehin in das Kachelgitter gelesen werden [A] | keiner |
| Kosten | doppelte Lesekosten je Kachel, Budget geteilt | — |
| Genauigkeit | „Preview“: Resampling in der Kachel statt im Zielgitter; nicht bitgleich zum Job | — |

**Empfehlung T-A**, gekennzeichnet als „Preview“ wie Übersichtsstufen (`adr/0014` F9). Der Planer (`adr/0014` §6.1) gilt je Zweig: Ist ein Schritt eines Zweiges nicht T1 (`grid`, `focal` nicht vorn), gibt es keine Vorschau des Vergleichs.

---

## 12. Anzeige

### 12.1 Zwei Bilder ansehen (V8): Swipe

| | A1 **zwei synchronisierte Karten (Swipe und Split)** | A2 eine Karte, Layer beschnitten | A3 nur nebeneinander im Layer-Manager |
|---|---|---|---|
| MapLibre | Muster von `maplibre-gl-compare` (Q20) | keine API zum Beschneiden je Layer; eigener WebGL-Layer nötig [A] | vorhanden |
| Aufwand | mittel: Kamera, Kompass, 3D und Globus synchron halten (UI-06) | hoch | keiner |
| Kosten | Basiskarte zweimal geladen | einmal | — |

**Empfehlung A1**, als eigene Frontend-Aufgabe vor dem Rezept-Teil (VP1-Teil):

- Swipe für zwei beliebige Ebenen des Layer-Managers (Eingaben, Suchergebnisse, Job-Ergebnisse), ohne Rezept und ohne Backend.
- Split (zwei Hälften) als zweite Art derselben Funktion.
- Eigener kleiner Code nach dem Muster von `maplibre-gl-compare` oder das Paket selbst; das Paket wäre eine neue Abhängigkeit (Lizenz vor Aufnahme prüfen, Otto).
- Leitfaden: keine Zusatztexte, Bedienung über ein Symbol, Erklärungen nur im Tooltip (M5-Plan §2 Punkt 9).

### 12.2 Ergebnis eines Vergleichs

- Ein Layer wie jedes Job-Ergebnis, Look aus dem Operator (§8.2): divergierend, symmetrisch um 0; Klassenfarben bei `classify`.
- Details des Ergebnisses: Paarstatistik (§8.3), beide Eingaben mit Datum, das Resampling.
- Mit dem Swipe lassen sich Ergebnis und je eine Eingabe nebeneinanderlegen.

### 12.3 Processing-Panel (UI-07)

- „Compare with…“ im Reiter „General“: zweite Eingabe wählen (aus Suche oder Layer-Manager), Methode, Bandpaare, Zielgitter (vorbelegt), Resampling (vorbelegt).
- Zweige: Die Schritte von a werden für b vorgeschlagen (gleicher Datensatz), änderbar.
- UI-07 hängt von diesem ADR ab (M5-Plan §6.2) und übernimmt die Bedienung im Einzelnen.

---

## 13. Bezug zu bestehenden ADRs

| ADR | Was sich ändert | Was bleibt |
|---|---|---|
| `adr/0014` | `recipe_version` 3; `inputs[].steps`, `combine`; Operator-Art `combine`; Planer je Zweig; Schätzung als Summe; Methodentext je Zweig | R1 als Grundform (jeder Zweig ist eine Kette), Hash `c1`, Cache-Schlüssel, `op_version`, Toleranzregeln, keine Konformität mit openEO erklärt |
| `adr/0019` | „Compare with…“ an einem Ergebnis: Auftrag mit zwei Zweigen aus den Aufträgen beider Jobs, neu gerechnet | Option 2: kein Ergebnis per Referenz |
| `adr/0035` | Looks für `compare` und `classify`; neue Skala „symmetrisch um 0“ | Ort der Vorgabe am Operator |
| `adr/0018` | keiner; §4.4 gilt; die Sperre aus §4.4 („Datacube- oder Zeitreihen-Operator braucht für GRD eine eigene Sperre“) wird `comparison: false` | Radargeometrie, kein Vergleich auf DN |
| `adr/0029` | keiner; Zeitschritt = Item macht V3 zum einfachsten Fall | Aggregation eigener ADR |
| `adr/0030` | F10 wird hiermit für Paarungen beantwortet; Aggregation bleibt offen | Rangfolge, Capabilities |
| `adr/0034` | Freigabe je Lauf gilt je Zweig | sonst nichts |

---

## 14. Fragen an Otto

**F1 — Rezeptmodell?**
1. Zwei Zweige mit eigener Kette, ein Vergleichsschritt, dann gemeinsame Kette (R-B, §5) **(Empfehlung)**
2. Gemeinsame Kette nach dem Angleichen (R-A)
3. Allgemeiner Graph wie openEO (R-C)

**F2 — Zielgitter?**
1. Ausdrücklich im Rezept als Gitter einer Eingabe (`like`), Panel schlägt das gröbere vor; anderes Ziel über `reproject` im Zweig (G1) **(Empfehlung)**
2. Immer Eingabe a
3. Immer das feinste Gitter

**F3 — Vergleichsoperatoren im ersten Schnitt?**
1. `compare` mit `difference`, `ratio`, `log_ratio`, `normalized_difference`, `expression` und Paarstatistik; `classify` mit ausdrücklichen Schwellen; `mask_by` und `transition` im zweiten Schnitt (O1) **(Empfehlung)**
2. Nur Band-Math über beide Eingaben
3. Wie 1, dazu Change Vector Analysis

**F4 — Zulässigkeit in der Registry?**
1. Capability `comparison` plus Block mit `match`, `methods`, `partners`, `quantity` (Z1) **(Empfehlung)**
2. Nur derselbe Datensatz, ein Flag
3. Jede Paarung, Hinweis im Tooltip

**F5 — Sentinel-1?**
1. Kein rechnender Vergleich, bis σ⁰ und Geländekorrektur (M5-31, DS-05d) oder ein RTC-Produkt da sind; dann nur `log_ratio`/`ratio`, gleiche relative Bahn und Polarisation; Swipe erlaubt **(Empfehlung)**
2. Schon jetzt `log_ratio` in Radargeometrie für Szenen derselben Bahn, mit Hinweis im Tooltip (braucht Koregistrierung, die es nicht gibt)
3. Sentinel-1 auch im Swipe ausnehmen

**F6 — Vorschau in der Kachel?**
1. Ja, wenn beide Zweige und der Vergleich T1 sind, als „Preview“, im Budget je Kachel (T-A) **(Empfehlung)**
2. Nur im Job

**F7 — Anzeige?**
1. Swipe und Split mit zwei synchronisierten Karten als eigene Frontend-Aufgabe zuerst, für beliebige zwei Ebenen (A1) **(Empfehlung)**
2. Eine Karte mit beschnittenem Layer (A2)
3. Nur nebeneinander im Layer-Manager (A3)

**F7a — Für 1: eigener Code oder Paket `@maplibre/maplibre-gl-compare`?**
1. Eigener kleiner Code nach dem Muster **(Empfehlung)**, keine neue Abhängigkeit
2. Paket nach Lizenzprüfung

**F8 — Vergleich zweier vorhandener Ergebnisse?**
1. „Compare with…“ baut einen Auftrag mit zwei Zweigen und rechnet neu (`adr/0019` Option 2) **(Empfehlung)**
2. Ergebnis per Referenz (`adr/0019` Option 1)

**F9 — Höhenmodelle über Datensätze (GLO-30, swissALTI3D, BEV)?**
1. Vorerst nicht; erst mit `quantity`/Höhenbezug in der Registry und einer Umrechnung der Höhenbezüge (eigene Aufgabe, Datei im Image wie M5-33) **(Empfehlung)**
2. Freigeben, Höhenbezug nur im Methodentext
3. Nie

**F10 — Zeitschritte und Aggregation?**
1. Zwei Zeitschritte sind zwei Eingaben (jetzt); Aggregation über viele Zeitschritte bekommt nach M5-11 einen eigenen ADR (wie `adr/0030` F10) **(Empfehlung)**
2. Aggregation in diesen ADR aufnehmen, bevor M5-11 steht

**F11 — Schnitt der Umsetzung?** (Nummern vergibt der Planungs-Chat; je Aufgabe ein PR, höchstens zwei)
1. **(Empfehlung)** in dieser Reihenfolge:
   1. Swipe und Split (Frontend, Stufe B);
   2. Rezept v3 und Kern mit zwei Eingaben **auf gleichem Gitter**, `compare`, Paarstatistik, Registry-Flag und Block, Sentinel-2 als erster Datensatz (Stufe B, Backend);
   3. Angleichen verschiedener Gitter (`like`, Warp), `classify`, Looks (Stufe B);
   4. Panel „Compare with…“ und Vorschau in der Kachel (mit UI-07);
   5. `mask_by` mit WorldCover, `transition` (Stufe B);
   6. ältere Stände von swissALTI3D als Voraussetzung für V2 (eigene Aufgabe).
2. Alles Backend in einem Schritt, Frontend danach

**F12 — WorldCover 2020 gegen 2021?**
1. Kein Vergleich, nur als Maske für andere Datensätze (`mask_by`) **(Empfehlung)**; der Eintrag sagt selbst „not directly comparable“
2. `transition` mit Hinweis im Tooltip

---

## 15. Was offen bleibt und vor einer Umsetzung zu prüfen ist

- **Sentinel-2-Offset über die Baseline:** an je einer Szene vor und nach 25.01.2022 prüfen, dass `raster:bands` den passenden Offset trägt (§4.3).
- **Primärquellen aus §4** an der Quelle lesen (openEO-Prozesse, GEE, Sentinel Hub, rioxarray); die Hosts waren aus der Sitzung nicht erreichbar.
- **dNBR-Schwellen** (USGS) und UN-SPIDER-Schwelle der Log-Ratio an der Quelle lesen, bevor ein Schritt-Preset sie übernimmt.
- **Lizenz** von `@maplibre/maplibre-gl-compare`, falls F7a = 2.
- **Höhenbezug** von GLO-30 (laut Produktbeschreibung EGM2008 [S]) in den Eintrag; Umrechnung LN02/LHN95 und österreichische Gebrauchshöhen gegen ellipsoidische Höhen klären (F9).
- **Mehrere Instanzen:** zwei Hosts in einem Job gegen die Grenzen je Host (M5-36, M5-37) messen.
- **Messung im Job:** Faktor von `compare` und Zeit der Paarstatistik blockweise mit Datei-I/O nachmessen (§3.3 ist ohne).

---

## 16. Quellen

Alle gelesen am 2026-11-16 über Suchtreffer [S]; die Seiten selbst waren für den Hilfsagenten nicht abrufbar, wo nicht anders gesagt.

- Q1 openEO `resample_cube_spatial`/`merge_cubes` im CDSE-Forum: https://forum.dataspace.copernicus.eu/t/co-registering-land-cover-and-dem-raster/1059
- Q2 openEO `merge_cubes` im EODC-Forum: https://discuss.eodc.eu/t/merging-datacubes/310 · https://discuss.eodc.eu/t/merge-cubes-from-different-collections/635
- Q3 Google Earth Engine, Resampling und `reproject`: https://developers.google.com/earth-engine/guides/resample · https://developers.google.com/earth-engine/apidocs/ee-image-reproject
- Q4 Sentinel Hub Data Fusion: https://docs.sentinel-hub.com/api/latest/data/data-fusion/ · https://forum.sentinel-hub.com/t/resampling-with-sentinel-hub-py/3992
- Q5 odc-stac `load`: https://odc-stac.readthedocs.io/en/latest/_api/odc.stac.load.html
- Q6 rioxarray `reproject_match`: https://corteva.github.io/rioxarray/html/examples/reproject_match.html
- Q7 `gdalwarp`: https://gdal.org/programs/gdalwarp · https://manpages.debian.org/bullseye/gdal-bin/gdalwarp.1.en.html
- Q8 Resampling kategorialer Daten (ArcGIS): https://pro.arcgis.com/en/pro-app/2.6/tool-reference/data-management/resample.htm
- Q9 `resample_cube_spatial` schneidet zu (CDSE-Forum): https://forum.dataspace.copernicus.eu/t/resample-cube-spatial-inconsistent-behavior/948
- Q10 Sentinel Hub FAQ und Async API: https://www.sentinel-hub.com/faq/ · https://docs.sentinel-hub.com/api/latest/api/async-process/
- Q11 Processing Unit (CDSE): https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/ProcessingUnit.html
- Q12 Google Earth Engine, Fehlersuche: https://developers.google.com/earth-engine/guides/debugging
- Q13 UN-SPIDER, Burn Severity: https://un-spider.org/advisory-support/recommended-practices/recommended-practice-burn-severity/in-detail
- Q14 Change Vector Analysis: https://andrewsforest.oregonstate.edu/sites/default/files/lter/pubs/pdf/pub2235.pdf · https://mdpi.com/2072-4292/3/11/2473
- Q15 Sentinel-2 Baseline 04.00, Offset: https://forum.step.esa.int/t/info-introduction-of-additional-radiometric-offset-in-pb04-00-products/35431 · https://sentinel.esa.int/web/sentinel/technical-guides/sentinel-2-msi/level-2a-algorithms-products
- Q16 Sentinel-1 Change Detection, Teil 2 (GEE-Tutorial): https://developers.google.com/earth-engine/tutorials/community/detecting-changes-in-sentinel-1-imagery-pt-2
- Q17 UN-SPIDER, Hochwasser mit Sentinel-1: https://un-spider.org/advisory-support/recommended-practices/recommended-practice-google-earth-engine-flood-mapping/step-by-step
- Q18 AI4Copernicus, S1 Change Detection: https://www.ai4europe.eu/sites/default/files/2023-11/AI4Copernicus_S1ChangeDetection.pdf
- Q19 Conradsen et al., Wishart-Test über k Zeitpunkte (IEEE TGRS 54(5), 2016, DOI 10.1109/TGRS.2015.2510160): https://orbit.dtu.dk/en/publications/change-detection-in-a-time-series-of-polarimetric-sar-images/
- Q20 `@maplibre/maplibre-gl-compare`: https://npmjs.com/package/@maplibre/maplibre-gl-compare
- Q21 `leaflet-side-by-side`: https://github.com/moklick/leaflet-side-by-side
- Q22 OpenLayers Layer Swipe: https://openlayers.org/en/latest/examples/layer-swipe.html · https://openlayers.org/en/latest/examples/webgl-layer-swipe.html
- Q23 openEO, vorher und nachher (CDSE-Forum): https://forum.dataspace.copernicus.eu/t/s1-before-and-after-imagery/3310
- Q24 CF-Konventionen 1.7 §4.4 (Zeit): https://cfconventions.org/Data/cf-conventions/cf-conventions-1.7/build/ch04s04.html
