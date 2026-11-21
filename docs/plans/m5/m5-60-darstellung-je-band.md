# M5-60 — Darstellung je Band

**Stand:** 21.11.2026, **Entwurf mit offenen Fragen F1–F7** (§9). Umsetzung erst nach Ottos Antworten.
**Stufe B.** Höchstens zwei PRs (M5-Plan §2 Punkt 11).
**Aufgabe (Otto, 21.11.2026; M5-Plan §6.2):**

> Darstellung je Band (Farbskala, Startbereich), damit ein einzeln gewähltes Band nicht grau erscheint. Grundsatz von Otto (20.11.2026, wie bei den Klassenfarben in M5-62): Nichts wird je Datensatz und Band von Hand gepflegt. Farbskala und Bereich kommen automatisch – aus der Quelle (z. B. STAC raster:bands, Statistik, Wertebereich der Einheit wie 0–100 % oder 0–1), sonst aus einer festen Regel nach Einheit bzw. Bandart; ein Eintrag von Hand nur als Ausnahme. Rangfolge Hand > Preset > Look (adr/0035) bleibt. Die Darstellung muss so beschrieben sein, dass M5-64 (QGIS-Stil .qml bei jedem Export) sie später 1:1 übernehmen kann.

**Grundlagen:** M5-Plan §2 Punkte 7 und 9 und §6.2 (Zeile M5-60), `plans/m5/m5-11-meteoschweiz.md` §11.9 (H1 = 1), `plans/m5/m5-62-klassenlegende.md` §9 (Grundsatz „nie von Hand“, Form `colours: file | stac | palette`, A6), `adr/0035` (Looks am Operator), `adr/0031` §7 (Onboarding schreibt die YAML aus einer Probe der Quelle), `projektuebersicht.md` §5 Punkte 8, 12, 13, `KLAERUNGEN.md` B10, B13, `architekturplan.md` 3.1 und `.importlinter`.

Belegstufen: **M** in dieser Session gemessen, **P** am Quelltext gelesen (Stand `main` nach #395), **A** eigene Ableitung.

---

## 1. Ziel

Jedes Band, das man in der Ansicht einzeln wählen kann, startet mit einer **Farbskala und einem Startbereich**, die automatisch feststehen, nie grau und nie ohne Farbskala. Dieselbe Beschreibung („Look“ eines Bands) gilt

1. in der Ansicht beim Wählen im Band-Menü,
2. für Ergebnis-Ebenen, deren Band ein unverändertes Band der Quelle ist (F5),
3. später für den QGIS-Stil im Export (M5-64), ohne dass dort etwas neu abgeleitet wird.

Die Rangfolge bleibt: **Hand** (Bereich bzw. Farbskala, die der Nutzer anwendet) **> Preset** (Index, Komposit) **> Look** (Operator nach `adr/0035`, neu auch Band) **>** übliche Messung.

**Nicht Teil:** das Standardbild eines Datensatzes (`default_render` bleibt, wie es ist), Klassenbänder (M5-62: Farben aus `band_classes`), eine sichtbare Farbskala-Legende auf der Karte (wie in M5-62 §1 „nicht Teil“), der QGIS-Stil selbst (M5-64).

---

## 2. Ausgangslage [P]

| Stelle | Heute |
|---|---|
| Band-Menü der Ansicht (`frontend/src/store.ts::chooseViewBand`) | Ein gewähltes Band bekommt den gemessenen Bereich (2.–98. Perzentil, `autoStretch`) und **keine Farbskala** → Graustufen. |
| Regel H1 (`frontend/src/viewBand.ts::standardLookOfBand`, M5-11) | Ein Band mit derselben Einheit wie das Standardbild (genau ein Band, mit Farbskala und Bereich) übernimmt beides: `TminD`, `TmaxD` wie `TabsD` (`rdbu_r`, −20…30 °C). Greift heute nur bei MeteoSchweiz und `swissalti3d` (`dtm_2m` wie `dtm`). Der Kommentar verweist auf M5-60. |
| Looks am Operator (`processing/operators/base.py::Look`, `adr/0035`) | `Look(colormap, scale ∈ measured \| percentiles \| fixed, low, high)`, veröffentlicht als `x-earthx-looks`; im Frontend `displayLook.ts` (`lookRange`, `percentOfLook`). Liegt in `processing`; `catalog` darf `processing` nicht importieren (`.importlinter`, Vertrag „catalog imports only gateway“). |
| Index- und Komposit-Presets (Registry) | `rescale` und `colormap_name` je Preset, in physikalischen Werten (die Kette rechnet mit `unscale`). |
| Einheiten (`band_units`, UCUM) | MeteoSchweiz °C, %, mm; DEMs m; Sentinel-2 Reflexion `1`, `aot` `1`, `wvp` cm, `cloud`/`snow` %, `scl` Klassen; Sentinel-1 `DN`; WorldCover Klassen. |
| Werte der Kacheln (`viewMeasure.ts`, Kopfkommentar) | Kacheln eines Bands zeichnen die **Rohwerte der Datei**; die Messung über die AOI rechnet physikalisch und wird mit `scale`/`offset` des Items in Rohwerte zurückgerechnet. Sentinel-2: `scale` 0.0001, `offset` −0.1 (Fixture `earth_search/search_real_shape.json`). |
| Quelle | Earth Search führt bei Sentinel-2 in `raster:bands` nur `nodata`, `data_type`, `spatial_resolution`, `scale`, `offset`, **keine** `statistics` (Fixture). Ob Quell-Collections `renders` (STAC Render Extension) tragen, ist für die heutigen Einträge nicht belegt; die Session ruft keine Quelle ab (`adr/0002`). |

Grau erscheinen heute also: alle Sentinel-2-Einzelbänder, `SrelD`, die vier Sentinel-1-Polarisationen (dort ist schon das Standardbild grau, F4) und jedes Band eines künftigen Eintrags.

---

## 3. Form der Beschreibung

### 3.1 Ein Look je Band, dieselbe Form wie am Operator

Der Look eines Bands hat **genau die Form von `adr/0035`**: `colormap` (Name aus der Liste des Tilers, `GET /colormaps`), `scale` ∈ `fixed | measured | percentiles`, bei `fixed`/`percentiles` dazu `low`, `high`. So nutzen Ansicht, Ergebnis-Ebene und Export dieselbe Rechnung (`displayLook.ts::lookRange`), und M5-64 bekommt eine einzige Form.

- `Look` wandert von `processing/operators/base.py` nach `catalog` (Registry), weil `catalog` `processing` nicht importieren darf; `processing` importiert ihn von dort (erlaubt). Keine Lockerung der Importregeln.
- **Werte physikalisch:** `low`/`high` stehen in der Einheit aus `band_units` (nach `scale`/`offset`), wie die Presets. Wo die Kacheln Rohwerte zeichnen, rechnet das Frontend den Bereich mit `scale`/`offset` des Items zurück, wie heute schon die Messung (`viewMeasure.ts`). Ein Bereich in Rohwerten in der Registry gibt es nicht (er gälte nur für eine Kodierung der Datei).

### 3.2 Was M5-64 daraus macht (Abgleich mit QGIS) [A]

Ein QGIS-Stil für ein Band mit Messwerten ist `singlebandpseudocolor` mit `colorrampshader`: Farbrampe, `minimumValue`, `maximumValue`, Interpolation, nodata durchsichtig. Aus dem Look folgt das 1:1:

| QML | aus dem Look |
|---|---|
| Farbrampe (`colorramp`, Stopps) | `colormap`: dieselbe Tabelle mit 256 Farben, die der Tiler zeichnet (rio-tiler bzw. `colormap_data/`), als Stopps; `_r` umgekehrt |
| `minimumValue`, `maximumValue` | `fixed`: `low`, `high`. `measured`/`percentiles`: am exportierten Raster mit derselben Funktion gemessen wie in der Ansicht |
| Interpolation | linear (wie der Tiler) |
| Klassenband | nicht der Look, sondern `band_classes` → `paletted` (M5-62) |

Hat der Nutzer in der Ansicht selbst etwas angewandt (Hand) oder ein Preset gewählt, schickt das Frontend den gezeichneten Look mit derselben Form im Export-Auftrag mit; M5-64 entscheidet das. Offen für M5-64, hier nicht gemessen: ob QGIS `scale`/`offset` der GeoTIFF beim Zeichnen anwendet; der physikalische Bereich (§3.1) ist dafür die sichere Ausgangsform.

### 3.3 Veröffentlichung

In der Collection je Band in `earthx:bands` (M5-59) zwei Felder: `earthx:look` (Form §3.1) und `earthx:look_from` (Herkunft, §4: `manual`, `stac`, `standard`, `unit`, `default`). Kein Feld bei Klassenbändern, Hilfs-Assets und dem Band des Echtfarbbilds. Keine Migration: die Collections schreibt `catalog-load` neu (§8). Falls doch eine nötig wird: Nummer 035 oder höher.

---

## 4. Woher der Look kommt (Rangfolge in der Registry)

Aufgelöst **einmal beim Laden des Eintrags** im Backend (`DatasetConfig.look_of(band)`), nicht im Frontend. Die erste Stufe, die etwas weiß, gilt:

| # | Herkunft (`earthx:look_from`) | Was | Wer schreibt es |
|---|---|---|---|
| 1 | `manual` | Ausnahme von Hand: vollständiger Look mit Grund als YAML-Kommentar | Otto im Review, nur als Ausnahme |
| 2 | `stac` | aus der Quelle: Render Extension der Quell-Collection (`renders` mit genau diesem einen Asset: `colormap_name`, `rescale`), sonst `statistics.minimum`/`maximum` aus `raster:bands` in `item_assets` der Quell-Collection (→ `fixed`); fehlt der Quelle die Farbskala, kommt sie aus Stufe 4/5 | das Onboarding (`adr/0031` §7) aus der Probe, wörtlich übernommen (wie `colours: stac`, M5-62 A6) |
| 3 | `standard` | das Band des Standardbilds selbst (ein Band mit Farbskala und Bereich, A4) und nach Regel H1 (M5-11) jedes Band gleicher Einheit → dessen Look (`fixed`) | nichts, Regel (F2) |
| 4 | `unit` | feste Regel nach Einheit (§5) | nichts, Tabelle im Code |
| 5 | `default` | jede andere Einheit, auch unbekannte (`null`, nicht Klasse): Standard-Farbskala, `measured` | nichts |

Damit hat **jedes** wählbare Band einen Look; kein Band bleibt grau, ohne dass ein Eintrag etwas trägt.

**Registry-Feld** `band_looks` (nur Stufen 1 und 2), optional wie `band_classes` (fehlt es, gilt die Regel; kein Eintrag, auch kein Prototyp, scheitert daran):

```yaml
band_looks:
  wvp:
    from: stac            # stac | manual
    scale: fixed
    low: 0.3
    high: 5.5
    # colormap fehlt: aus der Regel nach Einheit (Stufe 4/5)
```

Prüfungen beim Laden (der Eintrag lädt sonst nicht): Band aus `band_units`, kein Hilfs-Asset, kein Klassenband; `from` ∈ `stac | manual`; bei `manual` Look vollständig (mit `colormap`); `low < high`, endliche Zahlen; `percentiles` nur 0–100 oder 2–98 (Grenze aus `adr/0035` §4 Punkt 3). Ein Test hält fest, dass der Tiler jede Farbskala der Regeltabelle und der Einträge kennt (wie bei `terrain`).

---

## 5. Feste Regel nach Einheit (F1)

Vorschlag, eine Tabelle im Code neben `CLASS_PALETTE` (keine Pflege je Datensatz):

| Einheit (UCUM) | Farbskala | Bereich | Begründung |
|---|---|---|---|
| `%` | `viridis` | fest 0–100 | Wertebereich der Einheit (Ottos Beispiel) |
| `Cel`/`°C`, `K` | `rdbu_r` | gemessen | Temperatur: kalt blau, warm rot, wie `TabsD` |
| `mm` | `blues` | gemessen | Niederschlag, wie `RhiresD` |
| `m` | `terrain` | gemessen | heute nur Höhen; wie die DEMs |
| `1` | `viridis` | gemessen | Reflexion und andere Verhältnisse; 0–1 fest wäre für Reflexion fast schwarz (typisch 0–0,3), F1 Option 2 |
| `DN` | F4 | gemessen | unkalibrierte Rohwerte (Sentinel-1) |
| jede andere, `null` | `viridis` | gemessen | Standard (Stufe 5) |

„Gemessen“ ist `scale: measured` (2.–98. Perzentil wie heute); `Auto-scale` setzt den Bereich nach `adr/0035` zurück (fest → die festen Werte, gemessen → 2/98).

**Bandart** (Ottos „Einheit bzw. Bandart“): Die Registry kennt beim Laden nur Einheit und Beschreibung, keine Bandart. Eine Bandart (z. B. „Reflexion“ aus `eo:common_name` der Quelle, „Rückstreuung“ aus `sar:polarizations`) bräuchte ein neues Feld, das das Onboarding aus der Quelle füllt, oder eine Ableitung zur Laufzeit aus dem Item. → F3.

---

## 6. Befüllung der heutigen Einträge [P, A]

Kein Eintrag braucht `band_looks`; alles kommt aus Stufe 3–5. Ob eine Quelle `renders` oder `statistics` hat, prüft das Onboarding künftig; für die heutigen Einträge ist nichts davon belegt (§2).

| Eintrag | Band | Look (Herkunft) |
|---|---|---|
| `meteoswiss-daily-1km` | `TminD`, `TmaxD` | `rdbu_r`, −20…30 °C (`standard`, wie heute) |
| | `SrelD` | `viridis`, 0–100 % (`unit`) — **neu** |
| `sentinel-2-c1-l2a` | 12 Reflexionsbänder, `aot` | `viridis`, gemessen (`unit`, `1`) — **neu** |
| | `wvp` | `viridis`, gemessen (`default`, cm) — **neu** |
| | `cloud`, `snow` | `viridis`, 0–100 % (`unit`) — **neu** |
| | `scl` | Klassen (M5-62), kein Look |
| `swissalti3d` | `dtm_2m` | `terrain`, 0–5000 m (`standard`, wie heute) |
| `sentinel-1-grd` | `vv`, `vh`, `hh`, `hv` | F4 (`unit`, `DN`) |
| Übrige (ein Band, das Standardbild) | – | nicht wählbar als zweites Band; unverändert |

---

## 7. Frontend

- `viewBand.ts::standardLookOfBand` wird zu `bandLookOf(collection, band)`: liest `earthx:look` aus `earthx:bands` (unvollständige Looks werden verworfen wie in `displayLook.ts`). H1 rechnet dann das Backend (Stufe 3); das Frontend leitet nichts mehr selbst ab.
- `chooseViewBand`: `fixed` → Bereich sofort, mit `scale`/`offset` des Items in Rohwerte umgerechnet (gleiche Rechnung wie `viewMeasure.ts`; ohne bekannte Skalierung physikalisch = roh); `measured`/`percentiles` → Farbskala sofort, Bereich nach der Messung (`autoStretch`), wie bei einem Operator-Schritt (`fillStepRange`).
- „Auto-scale“ nimmt die Perzentile bzw. festen Werte des Looks (`percentOfLook`), wie bei Operator-Looks.
- Ergebnis-Ebenen (F5): ein Band, das ein Band der Quelle mit unveränderten Werten ist (Regel aus M5-62 §6, `passes_values`), bekommt dessen Look, eingereiht nach Preset und vor der üblichen Messung (`ResultBand.look`). Neu gerechnete Bänder bekommen keinen Band-Look (dort gilt weiter der Operator-Look bzw. die Messung).
- Keine neuen Texte im Frontend; das Feld „Colormap“ zeigt die Farbskala wie bei jeder anderen Wahl.

Berührungspunkt M5-62 PR 2 (Frontend, noch offen): beide ändern `ViewerControls.tsx`/Ergebnis-Ebenen; wer später kommt, baut auf dem anderen auf.

---

## 8. Schnitt, Tests, was Otto ausführt

**Schnitt (F6):**

- **PR 1** (nach den Antworten in diesem Draft-PR): Plan, dann Backend — `Look` nach `catalog`, Feld `band_looks` mit Prüfungen, Regeltabelle, Auflösung Stufen 1–5, `earthx:look` und `earthx:look_from` in `earthx:bands`, Onboarding-Checkliste (A1), Nachtrag zu `adr/0035` (A2). Geschätzt 200–300 Zeilen ohne Tests.
- **PR 2** (neue Session nach Merge): Frontend — `bandLookOf`, `chooseViewBand`, Auto-scale, Ergebnis-Ebenen (F5), Browser-Check. Geschätzt 150–250 Zeilen ohne Tests.

**Tests (ohne Netz, synthetische Fixtures):**

- Registry: `band_looks` fehlt → lädt; unbekanntes Band, Hilfs-Asset, Klassenband, `from` unbekannt, `manual` ohne `colormap`, `low ≥ high`, NaN/∞, `percentiles` 5–95 → lädt nicht.
- Auflösung: je Stufe ein Fall; Rangfolge (manual vor stac vor standard vor unit vor default); `stac` ohne Farbskala nimmt die der Regel; jedes wählbare Band aller Einträge hat einen Look, kein Klassenband einen.
- Collection: `earthx:look`/`earthx:look_from` je Band; nichts bei Klassen-, Hilfs- und Echtfarbbändern; der Tiler kennt jede Farbskala.
- Frontend (PR 2): `fixed` mit Skalierung (Sentinel-2 0–100 % `cloud` ohne Skalierung, Reflexion mit `scale`/`offset`) → richtiger Rohbereich; `measured` → Farbskala sofort, Bereich nach Messung; Hand und Preset gehen weiterhin vor; Ergebnis-Ebene mit unverändertem Band erbt, mit Band math nicht; unvollständiger Look verworfen.

Laufen lassen: Tests der geänderten Module (`backend/tests/catalog`, `backend/tests/earthx/processing` für den verschobenen `Look`, betroffene API-Tests), `ruff check backend`, `lint-imports --config .importlinter`; in PR 2 `npm run lint`, `npx tsc -b --pretty false`, Vitest der geänderten Dateien, betroffene Browser-Checks. Nie zwei Läufe gleichzeitig.

**Otto lokal nach dem Merge von PR 1:** einmal `catalog-load` (die Collections tragen `earthx:look`). Nach PR 2: Sentinel-2-Einzelband, `SrelD`, `TminD` im Browser wählen.

---

## 9. Fragen an Otto

**F1 — Regeltabelle nach Einheit (§5)**
1. Wie §5: `%` fest 0–100, Temperatur `rdbu_r`, `mm` `blues`, `m` `terrain`, sonst `viridis`; alles außer `%` gemessen. **(Empfehlung)**
2. Wie 1, aber `1` fest 0–1 (Wertebereich der Einheit; Reflexion wirkt dann sehr dunkel).
3. Eine einzige Farbskala (`viridis`) für alle Einheiten, nur `%` fest 0–100.

**F2 — Regel H1 (gleiche Einheit wie das Standardbild)**
1. Bleibt als Stufe 3 vor der Einheitenregel; `TminD`/`TmaxD` bleiben bei −20…30 °C. **(Empfehlung)**
2. Entfällt; Temperatur dann nach Einheitenregel (`rdbu_r`, gemessen).

**F3 — Bandart**
1. Vorerst keine Bandart; die Einheit reicht (Reflexion und `aot` teilen sich `1`, beide gemessen). Eine Bandart kommt, wenn eine Einheit zwei Arten trennt, die verschieden gezeichnet werden müssen. **(Empfehlung)**
2. Neues Registry-Feld je Band (`reflectance`, `backscatter`, …), vom Onboarding aus der Quelle gefüllt (`eo:common_name`, `sar:polarizations`).
3. Ableitung zur Laufzeit aus dem Item (dann rechnen Frontend und Export getrennt, keine eine Stelle).

**F4 — Sentinel-1 `DN` (Radar)**
1. `greys_r`, gemessen: Radarbilder werden üblich grau gezeigt, wie das Standardbild. **(Empfehlung)**
2. `viridis`, gemessen: auch Radar nie grau.

**F5 — Ergebnis-Ebenen**
1. Ein unverändertes Band der Quelle (Regel M5-62 §6) erbt den Look auch als Ergebnis-Ebene, in PR 2. **(Empfehlung)**
2. Nur die Ansicht; Ergebnisse eigene kleine Aufgabe.

**F6 — Schnitt**
1. Zwei PRs: Backend (dieser), Frontend (neue Session). **(Empfehlung)**
2. Ein PR (voraussichtlich über 400 Zeilen).

**F7 — Standard-Farbskala (Stufe 5 und `%`, `1`)**
1. `viridis` (verbreitet, gleichmäßig hell, farbsehschwächen-tauglich, in QGIS vorhanden). **(Empfehlung)**
2. `magma` oder `cividis`.

### 9.1 Auslegungen (gelten, wenn du nicht widersprichst)

- **A1:** Onboarding-Checkliste `projektuebersicht.md` §5 Punkt 8 bekommt den Nachsatz: „Die Darstellung je Band kommt automatisch (Quelle, sonst Regel nach Einheit); das Onboarding übernimmt `renders` bzw. `statistics` der Quelle als `band_looks` mit `from: stac`; ein Look von Hand nur als Ausnahme.“ Dazu eine Zeile im Entscheidungslog.
- **A2:** Kein neues ADR; ein Nachtrag zu `adr/0035` („Looks auch je Band, aus der Registry; `Look` liegt in `catalog`“), weil Form und Rangfolge dort stehen.
- **A3:** Der Look gilt nur für den Startbereich; was der Nutzer anwendet, geht vor (Hand) und wird wie heute gespeichert („Apply to all“, Permalink). Gespeicherte Arbeitszustände ändern sich nicht.
- **A4:** Das Standardbild (`default_render`) bleibt unverändert und wird nicht aus dem Look abgeleitet; ein Band, das das Standardbild ist, bekommt trotzdem einen Look (für Ergebnis-Ebenen und M5-64), bei einem Band mit Farbskala und Bereich im Standardbild genau diesen.
- **A5:** Werte des Looks in physikalischen Einheiten (§3.1); ein Item ohne lesbare Skalierung gilt als unskaliert (wie `viewMeasure.ts`).
