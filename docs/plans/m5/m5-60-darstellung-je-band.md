# M5-60 — Darstellung je Band

**Stand:** 21.11.2026, Plan **angenommen** (Otto, 21.11.2026: F1–F7 je Option 1, A1–A5; Vorgabe zum gemessenen Bereich §11; Histogramm für PR 2 §12). PR 1 (Backend) in diesem Draft-PR (§13); PR 2 (Frontend) in einer neuen Session nach dem Merge und erst nach M5-62 PR 2.
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

In der Collection je Band in `earthx:bands` (M5-59) zwei Felder: `earthx:look` (Form §3.1) und `earthx:look_origin` (Herkunft, §4: `manual`, `stac`, `standard`, `unit`, `default`). Kein Feld bei Klassenbändern, Hilfs-Assets und dem Band des Echtfarbbilds. Keine Migration: die Collections schreibt `catalog-load` neu (§8). Falls doch eine nötig wird: Nummer 035 oder höher.

---

## 4. Woher der Look kommt (Rangfolge in der Registry)

Aufgelöst **einmal beim Laden des Eintrags** im Backend (`DatasetConfig.look_of(band)`), nicht im Frontend. Die erste Stufe, die etwas weiß, gilt:

| # | Herkunft (`earthx:look_origin`) | Was | Wer schreibt es |
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
    origin: stac          # stac | manual
    scale: fixed
    low: 0.3
    high: 5.5
    # colormap fehlt: aus der Regel nach Einheit (Stufe 4/5)
```

Prüfungen beim Laden (der Eintrag lädt sonst nicht): Band aus `band_units`, kein Hilfs-Asset, kein Klassenband; `origin` ∈ `stac | manual`; bei `manual` Look vollständig (mit `colormap`); `low < high`, endliche Zahlen; `percentiles` nur 0–100 oder 2–98 (Grenze aus `adr/0035` §4 Punkt 3). Ein Test hält fest, dass der Tiler jede Farbskala der Regeltabelle und der Einträge kennt (wie bei `terrain`).

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

- **PR 1** (nach den Antworten in diesem Draft-PR): Plan, dann Backend — `Look` nach `catalog`, Feld `band_looks` mit Prüfungen, Regeltabelle, Auflösung Stufen 1–5, `earthx:look` und `earthx:look_origin` in `earthx:bands`, Onboarding-Checkliste (A1), Nachtrag zu `adr/0035` (A2). Geschätzt 200–300 Zeilen ohne Tests.
- **PR 2** (neue Session nach Merge): Frontend — `bandLookOf`, `chooseViewBand`, Auto-scale, Ergebnis-Ebenen (F5), Browser-Check. Geschätzt 150–250 Zeilen ohne Tests.

**Tests (ohne Netz, synthetische Fixtures):**

- Registry: `band_looks` fehlt → lädt; unbekanntes Band, Hilfs-Asset, Klassenband, `origin` unbekannt, `manual` ohne `colormap`, `low ≥ high`, NaN/∞, `percentiles` 5–95 → lädt nicht.
- Auflösung: je Stufe ein Fall; Rangfolge (manual vor stac vor standard vor unit vor default); `stac` ohne Farbskala nimmt die der Regel; jedes wählbare Band aller Einträge hat einen Look, kein Klassenband einen.
- Collection: `earthx:look`/`earthx:look_origin` je Band; nichts bei Klassen-, Hilfs- und Echtfarbbändern; der Tiler kennt jede Farbskala.
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

- **A1:** Onboarding-Checkliste `projektuebersicht.md` §5 Punkt 8 bekommt den Nachsatz: „Die Darstellung je Band kommt automatisch (Quelle, sonst Regel nach Einheit); das Onboarding übernimmt `renders` bzw. `statistics` der Quelle als `band_looks` mit `origin: stac`; ein Look von Hand nur als Ausnahme.“ Dazu eine Zeile im Entscheidungslog.
- **A2:** Kein neues ADR; ein Nachtrag zu `adr/0035` („Looks auch je Band, aus der Registry; `Look` liegt in `catalog`“), weil Form und Rangfolge dort stehen.
- **A3:** Der Look gilt nur für den Startbereich; was der Nutzer anwendet, geht vor (Hand) und wird wie heute gespeichert („Apply to all“, Permalink). Gespeicherte Arbeitszustände ändern sich nicht.
- **A4:** Das Standardbild (`default_render`) bleibt unverändert und wird nicht aus dem Look abgeleitet; ein Band, das das Standardbild ist, bekommt trotzdem einen Look (für Ergebnis-Ebenen und M5-64), bei einem Band mit Farbskala und Bereich im Standardbild genau diesen.
- **A5:** Werte des Looks in physikalischen Einheiten (§3.1); ein Item ohne lesbare Skalierung gilt als unskaliert (wie `viewMeasure.ts`).

---

## 10. Antworten von Otto (21.11.2026)

> F1 = 1, F2 = 1, F3 = 1, F4 = 1, F5 = 1, F6 = 1 (Backend hier; Frontend in einer neuen Session nach Merge, und erst nach M5-62 PR 2), F7 = 1. A1–A5 angenommen.
>
> Vorgabe zum gemessenen Bereich: Er wird nie je Kachel bestimmt, sondern einmal je Ansicht bzw. Band – aus raster:bands.statistics, der Übersicht oder einer einmaligen Messung – und gecacht. Alle Kacheln einer Ansicht nutzen denselben Bereich; beim Zoomen und Verschieben ändert er sich nicht (kein Farbsprung, kein Verschwinden). Keine zusätzliche Rechenlast je Kachelanfrage. Beschreibe im Plan, wo gemessen und wo gecacht wird, und was es kostet.
>
> Nachtrag: Für PR 2 (Frontend) in den Plan aufnehmen: Das Histogramm wird in den Farben der aktiven Darstellung gezeichnet. Ein Band: jeder Balken in der Farbe, die sein Wert auf der Karte hat (außerhalb des Bereichs die Endfarben). RGB: je Kanal in Rot, Grün, Blau. Klassenband: Balken in den Klassenfarben (M5-62). Ändern sich Bereich oder Farbskala, färbt sich das Histogramm sofort mit. Keine zusätzlichen Texte oder Legenden.

Folgen: Regeltabelle §5 wie vorgeschlagen (`%` fest 0–100 `viridis`; Temperatur `rdbu_r`; `mm` `blues`; `m` `terrain`; `1` `viridis`; `DN` `greys_r`; sonst `viridis`, alles außer `%` gemessen). H1 bleibt als Stufe 3. Keine Bandart. Ergebnis-Ebenen erben den Look in PR 2.

**Name des Felds (Auslegung A6):** Die Herkunft heißt in der YAML `origin`, nicht `from` wie im Entwurf (§4), weil `from` in Python kein Feldname sein kann und die Registry-Dataclasses die Form der YAML sind (`entry_files`, M5-13); in der Collection entsprechend `earthx:look_origin`.

**Standardbild (Auslegung A7, von Otto am 24.11.2026 abgelehnt, §14):** Stufe 3 nimmt `rescale` des Standardbilds als physikalische Werte. Das trifft für die heutigen Einträge mit einem Band im Standardbild zu (Höhen in m, MeteoSchweiz in °C und mm, keine Skalierung in den Einträgen); ein künftiger Eintrag mit skaliertem Standardband bekäme dort einen Bereich in Rohwerten. Das Onboarding schreibt `default_render` aus der Quelle; fällt so ein Fall an, ist er in der Probe sichtbar.

---

## 11. Gemessener Bereich: wo gemessen, wo gecacht, was es kostet

Die Vorgabe ist für die Ansicht heute schon so gebaut [P]; M5-60 ändert daran nichts, sondern legt nur fest, *welche* Messung ein Look mit `measured`/`percentiles` nimmt.

**Ein Bereich je Ansicht und Band, nie je Kachel.**

- Der Bereich steht als `rescale` (mit `colormap_name`) in der Kachel-URL der Ansicht (`render.ts`). Jede Kachel der Ansicht trägt dieselbe URL-Vorlage, also denselben Bereich. Der Tiler rechnet je Kachel nur die lineare Abbildung Wert → Farbe, die er ohnehin rechnet; er misst je Kachel nichts.
- Zoomen und Verschieben ändern die URL nicht; neu gemessen wird nur, wenn sich die Frage ändert: ein anderes Band oder Preset (`chooseViewBand`, `quickIndex`), eine neue Ansicht (`store.ts`, „A view that stays keeps the fields it has“) oder der Nutzer drückt „Auto-scale“/„Enhance contrast“. Ein Schritt der Zeitleiste behält den Bereich der Ansicht, damit gleiche Werte gleiche Farben haben.
- Ein Look `fixed` (z. B. `%` 0–100, Temperatur −20…30 °C) braucht keine Messung.

**Woher die Messung kommt, in dieser Reihenfolge:**

| # | Quelle | Wo | Kosten |
|---|---|---|---|
| 1 | `raster:bands.statistics` bzw. `renders` der Quelle | vom Onboarding in `band_looks` (`origin: stac`, `fixed`) übernommen, also gar keine Messung zur Laufzeit | keine |
| 2 | Messung über die AOI, wenn die Ansicht auf sie zugeschnitten ist | `POST /collections/{id}/statistics` (`api/area_statistics.py`), liest höchstens 2048 × 2048 Pixel (`processing/core.py::MAX_AREA_PIXELS`), über einer großen AOI aus einem gröberen Raster | eine Anfrage je Ansicht und Band; Cache in Postgres (`earthx_stats_cache`), Schlüssel = Hash über das Rezept, Lebensdauer wie ein Rezept (`AREA_STATISTICS_TTL_S`) |
| 3 | Messung der ersten Szene | `GET …/statistics` des Tilers (`access/tiles.py::_read_statistics`), auf der gröbsten Stufe der Datei (`preview`, Übersicht der COG, höchstens 1024 px Kante), bei Datensätzen mit Pyramide unter `min_zoom` aus deren Übersicht | eine Anfrage je Szene und Band, kalt rund 1 s (`adr/0006` §3.4), danach aus dem Cache (`catalog/stats_cache.py`, 30 Tage, Schlüssel = Hash über Datensatz, Item, Asset, Parameter) |

Die Messung liegt damit immer vor der ersten Kachel einer Ansicht, einmal; die Kacheln selbst kosten nicht mehr als heute. Der Look ändert nur, welche Zahlen der Antwort genommen werden (`measured`: 2.–98. Perzentil; `percentiles` 0/100: Minimum/Maximum), nicht die Messung.

**Für M5-64 (Export):** Ein QGIS-Stil braucht Zahlen. Bei `fixed` sind es die des Looks; bei `measured` nimmt der Export den Bereich, den die Ansicht gezeichnet hat (kommt mit dem Auftrag), sonst misst er einmal das exportierte Raster, das er ohnehin vollständig in der Hand hat (bei Jobs steht die Statistik schon heute in `result.tif`, M4-32). Kosten je Export einmal, nie je Kachel.

---

## 12. Histogramm in den Farben der Darstellung (PR 2, Nachtrag Otto)

Das Histogramm der Einstellungsleiste (Feld „Scale“) wird in den Farben der aktiven Darstellung gezeichnet:

- **Ein Band:** jeder Balken in der Farbe, die sein Wert auf der Karte hat: Mitte des Balkens → Stelle im Bereich → Farbe der Farbskala; unterhalb bzw. oberhalb des Bereichs die Endfarben. Die Farben der Skala kommen aus derselben Liste wie die Vorschau der Farbskalen (`GET /colormaps`, `PREVIEW_STOPS`), keine eigene Tabelle im Frontend.
- **RGB (Echtfarbe, Komposite):** je Kanal in Rot, Grün, Blau.
- **Klassenband:** Balken in den Klassenfarben (M5-62, `classification:classes`).
- Ändern sich Bereich oder Farbskala (auch vor „Apply“, in den Feldern), färbt sich das Histogramm sofort mit; keine neue Messung.
- Keine zusätzlichen Texte oder Legenden.

Tests (PR 2): Balken innerhalb, unter und über dem Bereich; umgekehrte Skala (`_r`); RGB-Kanäle; Klassenfarben; Wechsel der Farbskala färbt ohne neue Anfrage um. Ausnahme „Farben von Daten“ in `uiRules.test.ts` wie bei M5-62.

---

## 13. Umsetzung PR 1: Backend (21.11.2026)

### 13.1 Was gebaut ist

| Teil | Stelle |
|---|---|
| `Look` aus `processing/operators/base.py` nach `catalog/registry.py` verschoben (unverändert bis auf den Docstring); `base.py` und `terrain.py` importieren ihn von dort | `backend/earthx/catalog/registry.py`, `backend/earthx/processing/operators/base.py`, `.../terrain.py` |
| `LookOrigin` (`manual`, `stac`, `standard`, `unit`, `default`), `UNIT_LOOKS` (Regel §5 nach F1, F4, F7), `DEFAULT_LOOK`, `BandLook` (Form der YAML), `ResolvedLook` | `backend/earthx/catalog/registry.py` |
| Feld `band_looks` (optional, leerer Standard wie `band_classes`), Prüfungen beim Laden (§4), `DatasetConfig.look_of(band)` mit der Rangfolge §4 | `backend/earthx/catalog/registry.py` |
| `earthx:look` und `earthx:look_origin` je Band in `earthx:bands`; nichts bei Klassen- und Hilfs-Assets | `backend/earthx/catalog/collection.py` |
| Onboarding-Checkliste Punkt 8 (A1), Nachtrag `adr/0035` §5 (A2), Entscheidungslog | `docs/` |

Kein Eintrag trägt `band_looks`; die Looks der heutigen Einträge sind die aus §6 (Test `TestTheEntries`). Keine Migration.

### 13.2 Tests

Neu: `backend/tests/catalog/test_band_looks.py` — die Looks aller Einträge, jedes wählbare Band hat einen und kein Klassen- oder Hilfs-Asset, der Tiler kennt jede Farbskala der Einträge und der Regel; die Rangfolge (Hand, Quelle mit und ohne Farbskala, Standardbild und gleiche Einheit, Einheit, Standard; Standardbild ohne Farbskala, ohne Bereich, mit mehreren Bereichen); Fehlerfälle (unbekanntes Band, Muster, Klassenband, Hilfs-Asset, Herkunft `unit`/`standard` geschrieben, Hand ohne Farbskala, leere Farbskala, leerer Bereich, ein Ende, `measured` mit Enden, NaN, ∞, Perzentile außerhalb 0–100 und andere als 0/100, 2/98); Lesen aus der YAML (Rundlauf, strenge Prüfung: unbekannte Herkunft, unbekannte Skala, unbekanntes Feld, Zahl als Text); Collection. Angepasst: `test_entry_files.py` (Feld mit Standardwert wird nicht geschrieben).

### 13.3 Was Otto lokal ausführt

Nach dem Merge einmal `catalog-load` (die Collections tragen `earthx:look`). Sichtbar wird es erst mit PR 2.

### 13.4 PR 2 (Frontend, neue Session nach dem Merge und nach M5-62 PR 2)

§7 (`bandLookOf` statt `standardLookOfBand`, `chooseViewBand`, Auto-scale, Ergebnis-Ebenen nach F5) und §12 (Histogramm in den Farben der Darstellung), Browser-Check.

---

## 14. Rückmeldung Otto zu PR 1 (24.11.2026)

> Zu A7: nicht so lassen. Übernimmt ein Band den Bereich des Standardbilds, rechne ihn mit scale/offset des Bandes in physikalische Werte um. Ist das nicht eindeutig (z. B. Standardbild über mehrere Bänder mit verschiedener Skalierung), soll der Eintrag beim Laden mit einer klaren Meldung abbrechen, bis er ein eigenes band_looks trägt. Test mit einem synthetischen skalierten Band. Entscheidungslog und Plan §10 nachführen.

### 14.1 Befund [P]

Die Registry kennt `scale` und `offset` eines Bands nicht. Sie stehen nur in `raster:bands` der Items der Quelle (Sentinel-2: `scale` 0.0001, `offset` −0.1, Fixture `earth_search/search_real_shape.json`); kein Feld eines Eintrags trägt sie, und beim Laden liest die Registry keine Items. Eine Prüfung „beim Laden“ braucht die Skalierung deshalb im Eintrag. Wo sie herkommt, ist nicht entschieden → F8. Bis zur Antwort ruht dieser Teil; PR 1 bleibt sonst, wie er ist.

Heute betroffen ist kein Eintrag: Die Standardbilder aus einem Band (Höhen, MeteoSchweiz) sind unskaliert, Sentinel-2 hat ein Echtfarb-Standardbild, Sentinel-1 eines ohne Farbskala (keine Stufe 3).

### 14.2 Frage F8 — Woher die Registry `scale`/`offset` kennt

1. **Neues optionales Feld `band_scaling`** je Band (`scale`, `offset`), vom Onboarding aus `item_assets` bzw. `raster:bands` der Quelle übernommen (wie `band_units`); fehlt ein Band, gilt „unskaliert“ (1, 0). Stufe 3 rechnet `rescale` mit der Skalierung des Standardbands in physikalische Werte um. Abbruch beim Laden mit Meldung („… set band_looks for …“), wenn die Bänder des Standardbilds verschieden skaliert sind oder ein Standardband als Muster (`*`) mit mehreren Skalierungen steht. Heute ohne Wirkung auf die Einträge; Sentinel-2 bekommt das Feld trotzdem befüllt (Reflexion 0.0001/−0.1, `aot`/`wvp` 0.001/0), damit es künftig stimmt. **(Empfehlung)**
2. Wie 1, aber Pflichtfeld für jedes Band (B10): jeder Eintrag sagt die Skalierung ausdrücklich, auch „1, 0“.
3. Kein neues Feld: Stufe 3 gilt nur, wenn das Standardbild ausdrücklich unskaliert ist; sonst bricht der Eintrag ab, bis er `band_looks` trägt. Das hieße, ein Eintrag sagt „unskaliert“ an anderer Stelle (z. B. ein Schalter in `default_render`).

**Auslegung A8 (gilt mit F8 = 1 oder 2):** „Mehrere Bänder“ im Sinne der Rückmeldung heißt: Stufe 3 gilt künftig auch für ein Standardbild aus mehreren Assets, von denen eines gezeichnet wird (`asset_selection: first_present`, z. B. `vv`/`hh`), mit Farbskala und einem Bereich je Asset. Ergeben alle nach der Umrechnung denselben physikalischen Bereich, gilt er; sonst Abbruch.
