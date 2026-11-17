# M5-14 — Komposit- und Schritt-Presets unter „Quick processing“

**Stand:** 17.11.2026, freigegeben von Otto (Antworten in §8a); PR A gemergt (#370), PR B in Arbeit (§10).
**Stufe B.** Erst Plan mit Fragen im Draft-PR, Umsetzung nach Ottos Antworten im selben PR; höchstens zwei PRs (M5-Plan §2 Punkt 11).
**Aufgabe:** M5-14 aus `docs/plans/m5/m5-discovery-und-suche.md` §6.2.
**Grundlage:** `adr/0030` F7 (Felder `composite_presets` und `step_presets`), §3 B2/B3, §5.1, §5.3, §8, §12; `adr/0035` (Darstellung am Operator); M5-10 (`terrain`, F5: „Hillshade“ als Knopf mit M5-14; G1: Ketten unter `min_zoom` auf der Übersicht); NM4-14 (Index-Presets), NM4-64 (`true_color`), UI-03d (Quick processing, Ebene eines Index).
**Vorgaben Otto zu dieser Aufgabe:** Presets als Registry-Angaben je Datensatz, nicht im Frontend-Code; Anzeige unter „Quick processing“; was ein Datensatz nicht kann, erscheint nicht; keine Marken außer „Overview“; nie verschwindet ein Bild.

## 1. Ziel

„Quick processing“ zeigt heute nur Index-Presets (ein `band_math`-Ausdruck) und „Enhance contrast“. M5-14 bringt die zwei Felder aus `adr/0030` F7:

- **`composite_presets` (B2):** drei Ausdrücke als Rot, Grün, Blau, z. B. Falschfarben-Infrarot auf Sentinel-2.
- **`step_presets` (B3):** ein Schritt eines T1-Operators mit festen Parametern, z. B. „Hillshade“ und „Slope“ auf den Höhenmodellen.

Beide füllen gewöhnliche Schritte wie heute ein Index-Preset: kein eigener Operator, keine `op_version`, gleicher Hash, gleiche Kachel, gleicher Job (`adr/0030` §3 „B2 und B3“).

Nicht Teil: „VV dB“/„VH dB“ (DS-05a, braucht `sar_db`), „Dual-pol RGB“ (DS-05c), Index-Presets selbst (unverändert).

## 2. Befund im Code (Stand `main`, af1ca04)

| Stelle | Heute | Folge |
|---|---|---|
| `catalog/registry.py` `IndexPreset`, `_check_index_presets`, `_check_true_color` | Form der Presets, Namen, Bänder, `band_math` muss an sein | zwei neue Dataclasses und Prüfungen daneben; Felder ohne Vorgabe (B10) |
| `catalog/entry_files.py` | liest jede Dataclass streng über pydantic | neue Felder ohne Zusatzcode; alle sieben YAML-Einträge bekommen beide Felder (leer, wo nichts gilt) |
| `processing/index_presets.py`, Aufruf in `api/main.py::build_app` | prüft beim Start von `api` gegen `band_math` und die Colormaps des Tilers | daneben `check_quick_presets`: Komposit-Ausdrücke gegen `band_math`; Schritt-Presets gegen Parametermodell, `applicable()`, T1 und Art (`pixel` oder `focal`) |
| `catalog/collection.py` | veröffentlicht `earthx:index_presets`, `earthx:true_color` | dazu `earthx:composite_presets`, `earthx:step_presets` |
| `catalog/search_text.py` | Namen und Titel der Index-Presets im Suchtext | ebenso die neuen Presets |
| `processing/operators/terrain.py` `_LOOKS` | Darstellung der drei Produkte am Operator (`adr/0035`) | Schritt-Presets brauchen keine eigene Darstellung (F1) |
| `api/tiler.py` | Kachel mit bis zu vier Schritten, `focal` nur als erster; ein oder drei Bänder als Bild, `rescale` je Band | Komposit mit höchstens drei `band_math`-Schritten und Schritt-Preset passen ohne Änderung [A, im Test prüfen] |
| Übersichtsroute (`_overview_chain`, M5-10 PR B) | rechnet eine Kette auf Pyramide bzw. Ersatz unter `min_zoom`, auch `focal` | „Hillshade“ auf GLO-30, swissALTI3D und BEV hat unter `min_zoom` ein Bild |
| Frontend `indexPresets.ts`, `viewIndex.ts` | lesen Index-Presets, bauen den einen `band_math`-Schritt, Kachel, Mosaik, Statistik, Übersichtskette | Kern der Verallgemeinerung: ein Preset = Schritte + gezeigte Bänder + Darstellung |
| `AppliedRender.index`, `restore.indexOnly`, `indexDownload.ts`, „Process“ an einer Index-Ebene | ein Index ist Teil des Looks; angeheftet steht er allein; Download und Processing nehmen den Schritt mit | gleiche Wege für alle Presets (F5) |
| `ViewerControls.tsx` | Abschnitt „Quick processing“ nur, wenn Index-Presets oder RGB | erscheint auch bei Komposit- oder Schritt-Presets; sonst unverändert |
| `catalogue.ts` Zeile „Quick processing“ | Titel der Index-Presets und „Enhance contrast“ | dazu die Titel der neuen Presets |
| `displayLook.ts` | liest `x-earthx-looks` aus der Prozessbeschreibung (`fetchProcess(datasetId)`) | Schritt-Presets nehmen diesen Look |

Registry heute: `terrain` an bei `cop-dem-glo-30`, `swissalti3d`, `bev-als-dgm`; Sentinel-2 hat `true_color` und neun Index-Presets; Sentinel-1 GRD, WorldCover 2020/2021 haben keine Presets.

## 3. Vorschlag Registry (Backend)

### 3.1 `CompositePreset`

| Feld | Inhalt |
|---|---|
| `name` | Kennung, Muster wie Bandnamen (`false_colour_ir`); einmal je Datensatz über alle drei Preset-Arten |
| `title` | Text des Knopfs, kurz (≤ 24 Zeichen), z. B. „False colour (IR)“ |
| `red`, `green`, `blue` | je ein Ausdruck in den Bändern des Datensatzes; ein reiner Bandname braucht keinen Schritt |
| `rescale` | je Kanal ein Paar (drei Paare), F4 |
| `reference` | `https://`-Quelle der Kombination |

Prüfung in `catalog`: Form, Namen, nur Bänder der Daten (Regel von `_preset_problem`), drei Kanäle nicht alle gleich; ein Kanal mit Rechnung braucht `band_math`. Beim Start von `api`: Ausdrücke über `check_expression`.

**Kachel:** Kanäle, die nur ein Band nennen, liest die Kachel direkt; jeder andere wird ein `band_math`-Schritt mit festem Namen (`<name>_r`, `_g`, `_b`). Höchstens drei Schritte, die Grenze von vier hält.

### 3.2 `StepPreset`

| Feld | Inhalt |
|---|---|
| `name` | Name des Bands, das der Schritt hinzufügt (`hillshade`); einmal je Datensatz, nicht der eines Bands der Daten |
| `title` | Text des Knopfs, z. B. „Hillshade“ |
| `op`, `op_version` | Operator und Version |
| `params` | Parameter des Schritts ohne `name` (der kommt aus `name`); Bänder in den Namen des Datensatzes |

Keine Felder für die Darstellung (F1): Der Look kommt vom Operator (`adr/0035`). Ein Schritt-Preset auf einem Operator ohne Look wird beim Start abgewiesen, damit nie eine Kachel ohne festgelegte Darstellung entsteht [A].

Prüfung in `catalog`: Form, Name, `op` als Text; die gelesenen Bänder (aus `params`) sind Bänder der Daten. Beim Start von `api` (`processing/quick_presets.py`): Operator und Version stehen in der Registry und sind `listed`; Parameter gehen durch das Modell (`strict`); `applicable(operator, config, params)` ist leer; Operator hat T1 und Art `pixel` oder `focal`; Look vorhanden. Damit kann ein Preset, das der Datensatz nicht kann, gar nicht erst entstehen („was nicht geht, erscheint nicht“).

### 3.3 Einträge (Inhalt nach F2, F3)

- `cop-dem-glo-30`, `swissalti3d`, `bev-als-dgm`: `step_presets` „Hillshade“, „Slope“ und „Aspect“ (F2 = 2) auf dem Höhenband (`data`, `dtm`, je Eintrag); `composite_presets: []`.
- `sentinel-2-c1-l2a`: `composite_presets` „False colour (IR)“ (`nir`, `red`, `green`) und „SWIR“ (`swir22`, `nir08`, `red`, Antwort Otto 17.11.2026) nach `adr/0030` §5.1; `step_presets: []`.
- Sentinel-1 GRD, WorldCover 2020/2021: beide leer.
- Kommentare in den YAML-Dateien nennen Quelle und Entscheidung wie bei den Index-Presets.

### 3.4 Veröffentlichung

`earthx:composite_presets` (Kanäle als `expressions: [r, g, b]`, `rescale` wie die Render-Erweiterung) und `earthx:step_presets` (`op`, `op_version`, `params` mit `name`) in der Collection; Suchtext nimmt Namen und Titel auf.

## 4. Vorschlag Frontend

- **Ein Begriff „Preset“** statt „Index“ im Kern (`quickPresets.ts` aus `indexPresets.ts`): Art (`index`, `composite`, `step`), Knopftext, Tooltip, die Schritte der Kachel, die Assets, die gezeigten Bänder (eines oder drei) und die Darstellung (Index: `rescale`/Colormap; Komposit: `rescale` je Kanal; Schritt: Look aus der Prozessbeschreibung).
- **`AppliedRender.index`** bleibt der Schlüssel (Name des Presets), damit gespeicherte Ebenen gültig bleiben; Bedeutung: „ein Preset des Datensatzes“.
- **Ansicht:** Knöpfe in der Reihenfolge Index, Komposit, Schritt, dann „Enhance contrast“; Index-Knöpfe zeigen wie heute den Namen, die anderen den Titel. Ein Klick füllt die Felder, „Apply“ zeichnet, zweiter Klick zurück (wie heute). Komposit: drei Kanalzeilen wie bei RGB, „Enhance contrast“ wirkt darauf. Schritt mit Look `percentiles`/`measured`: Bereich aus der Statistik der Kachelroute mit demselben Schritt (wie „Auto-scale“ beim Index); `fixed` ohne Messung.
- **Unter `min_zoom`:** dieselbe Kette über die Übersichtsroute (`indexChainOf` → `presetChainOf`), Marke „Overview“ wie überall dort (UI-08); kein anderer Hinweis.
- **Nie verschwindet ein Bild:** Beim Umschalten bleibt das bisherige Bild, bis die neuen Kacheln da sind (Verhalten der Index-Kacheln heute, im Test festhalten). Mosaik eines Durchgangs: Auswahl über die Assets des Presets wie beim Index.
- **Data catalogue:** Zeile „Quick processing“ nennt alle Titel.
- Keine neuen Texte außer Knopftiteln aus der Registry; Erklärungen nur im Tooltip.

## 5. Umfang und Schnitt

Geschätzt Backend 250–300 Zeilen mit Tests, Frontend 600–800 mit Tests (die Index-Wege sind breit verdrahtet: Ansicht, Mosaik, Übersicht, Anheften, Download, „Process“, Ergebnis-Layer). Vorschlag (F5): zwei PRs.

- **PR A (dieser):** Plan, Registry, Prüfungen, Einträge, Collection, Suchtext; Frontend lesen und zeichnen in Ansicht, Übersicht und angehefteter Ebene, Data catalogue.
- **PR B (gestapelt):** „Process“ an einer Preset-Ebene (Schritte gesperrt vorn, wie beim Index), „Download“ des gerechneten Bands bzw. der drei Kanäle, Wiedererkennen in Ergebnis-Layern.

## 6. Tests

- `catalog`: jede Regel mit Gut- und Schlechtfall (fremdes Band, Hilfsasset, Name doppelt über Preset-Arten, Name eines Bands, falscher Typ statt Tupel, Kanal mit Rechnung ohne `band_math`, `rescale` verkehrt, Referenz ohne `https://`).
- `api`-Start: unbekannter Operator, nicht gelistete Version, Parameter abgewiesen, Capability fehlt (z. B. `terrain` auf Sentinel-2), Operator nur T2 (`reproject`), `grid`, Operator ohne Look, unbekannte Colormap.
- YAML-Lader: Felder fehlen → Fehler (B10); Round-Trip `to_plain`.
- Kachel: Komposit mit einem `band_math`-Kanal und Schritt-Preset „Hillshade“ über `TestClient` mit Fixture-Raster; Übersichtsroute mit der Kette.
- Frontend: unvollständige Einträge werden verworfen; Knöpfe nur bei vorhandenen Presets; Klick, Apply, zweiter Klick; angeheftete Ebene; Kachel-URL und Übersichtskette; Data catalogue.
- Browser-Check: „Hillshade“ auf GLO-30 von z10 bis z0, hell und dunkel; Komposit auf Sentinel-2 (Bilder nicht ins Repo).

## 7. Grenzen

- Modulgrenzen: `catalog` prüft nur die Form; alles, was Operatoren kennt, in `processing` beim Start von `api` (Muster `index_presets`).
- Keine Live-Abrufe aus der Cloud-Session; Tests nur mit Fixtures.
- Lizenz und Attribution unverändert; Composites sind Darstellungen derselben Daten.
- Entscheidungslog: eine Zeile mit den Antworten; Nachtrag in `adr/0030` §8, falls F1 = 1 (Darstellung nicht im Feld).

## 8. Fragen an Otto

**F1 — Darstellung der Schritt-Presets?** (`adr/0030` §8 sah `rescale` und `colormap_name` am Feld vor; `adr/0035` legte die Darstellung an den Operator.)
1. Keine Darstellung am Preset; der Look des Operators gilt (Hillshade `greys_r` 0/100 %, Slope `rdylgn_r` 2–98 %); `adr/0030` §8 bekommt einen Nachtrag **(Empfehlung)**
2. Pflichtfelder `rescale` und `colormap_name` am Preset wie in `adr/0030` §8, sie gehen dem Look des Operators vor
3. Wie 1, aber ein optionales Feld überschreibt den Look

**F2 — Welche Presets kommen mit M5-14 in die Registry?**
1. Höhenmodelle (GLO-30, swissALTI3D, BEV): „Hillshade“, „Slope“; Sentinel-2: „False colour (IR)“ und „SWIR“ **(Empfehlung)**
2. Wie 1, dazu „Aspect“ bei den Höhenmodellen
3. Nur „Hillshade“ und „Slope“; Komposite erst mit DS-05c

**F3 — Parameter der Schritt-Presets?**
1. Wie `gdaldem`: Horn; Hillshade Azimut 315°, Höhe 45°, z-Faktor 1, ein Licht; Slope in Grad **(Empfehlung)**
2. Wie 1, Hillshade aber `multidirectional` (vier Lichter, weniger Richtungsabhängigkeit)
3. Wie 1, Slope in Prozent

**F4 — Farbbereich der Komposite?**
1. Fest je Kanal in der Registry (`adr/0030` §8), Reflektanz `nir` 0–0,5, `red`/`green` 0–0,3, `swir22` 0–0,4 [A]; „Enhance contrast“ streckt auf Wunsch **(Empfehlung)**
2. Ohne festen Bereich: beim Klick 2.–98. Perzentil je Kanal wie „Enhance contrast“

**F5 — Umfang und Schnitt?**
1. Presets können alles, was ein Index kann (Ansicht, Übersicht, Anheften, „Process“, Download, Ergebnis-Layer); zwei PRs nach §5 **(Empfehlung)**
2. Nur Ansicht, Übersicht und Anheften in einem PR; „Process“ und Download als eigene Aufgabe später

## 8a. Antworten von Otto (17.11.2026)

F1 = 1, F2 = 2, F3 = 1, F4 = 1, F5 = 1.

- **F2 = 2:** Die Höhenmodelle bekommen „Hillshade“, „Slope“ und „Aspect“. Die Darstellung von „Aspect“ folgt `adr/0035`: `hsv`, fest 0–360°.
- **Reihenfolge:** PR A (dieser PR, [#370](https://github.com/oscipal/earthX/pull/370)) umsetzen, `main` holen, fertig melden; PR B danach.

## 9. Umsetzung PR A (17.11.2026)

Umgesetzt nach §3 und §4 mit F1–F5 aus §8a. Befunde und Auslegungen, gelten bis Widerspruch:

**Backend**
- `CompositePreset` und `StepPreset` in `catalog/registry.py`, Felder `composite_presets` und `step_presets` ohne Vorgabe; alle sieben YAML-Einträge nennen beide.
- **Abweichung von §3.1:** Jeder Kanal eines Komposits wird ein `band_math`-Schritt (`<name>_r`, `_g`, `_b`), auch ein reiner Bandname. Grund: Die Kachel nimmt `band` nur hinter Schritten an (`api/tiler.py`, „band is for tiles with op“). Ein Komposit braucht deshalb immer `band_math`.
- Ein Name gilt einmal über Index-, Komposit- und Schritt-Presets (Groß- und Kleinschreibung gleich) und darf kein Band der Daten sein. Knopftitel höchstens 24 Zeichen.
- `processing/quick_presets.py` prüft beim Start von `api`: Operator und Version gelistet; T1, Art `pixel` oder `focal`; Parameter durch das Modell; `applicable()`; das hinzugefügte Band heißt wie das Preset; gelesene Bänder gehören zu den Daten; der Operator hat einen Look, dessen Colormap der Tiler kennt.
- Quellen der Komposite: Sentinel Hub Custom Scripts („False color infrared“, „SWIR“). Die Seiten waren aus der Cloud-Session nicht erreichbar. „SWIR“ nimmt wie dort B12, B8A, B04 (`swir22`, `nir08`, `red`; Otto, 17.11.2026, Nachtrag zu `adr/0030` §5.1).

**Frontend**
- `quickPresets.ts`: ein Preset = Schritte, gelesene Assets, gezeigte Bänder (eines oder drei), Darstellung. Die Index-Wege (`viewIndex.ts`, Mosaik-Auswahl, Übersicht unter `min_zoom`, Statistik, Anheften, Messung der AOI) nehmen es unverändert; `AppliedRender.index` nennt das Preset jeder Art.
- Komposit: drei Kanäle mit den festen Bereichen, Farbbild ohne Colormap; „Enhance contrast“ wirkt darauf.
- Schritt: Der Look kommt aus der Prozessbeschreibung des Datensatzes (`presetLooks.ts`, einmal je Datensatz). Fest (Aspect): sofort. Sonst wird das Band so gemessen, wie es gezeichnet wird (Statistik-Route mit demselben Schritt). „Auto-scale“ nimmt den Bereich des Looks (Hillshade 0/100 %), die Colormap bleibt.
- Kommt die Beschreibung nicht, erscheint eine Meldung, und es wird kein Bereich erfunden.
- Bis PR B: Eine Ebene eines Komposits oder Schritts bietet keinen Download „als Index“; „Process“ öffnet sie mit den Bändern der Daten wie eine gewöhnliche Ebene.

**Nachtrag Otto (17.11.2026), Fehler seit UI-09:** Beim Wechsel des Produkts im Schritt „Terrain“ folgten Name und Darstellung nicht. Zwei Ursachen:
- Der Name blieb stehen.
- „Auto-scale“ hielt die Colormap des Looks fest, als hätte der Nutzer sie gewählt.

Jetzt gilt:
- Der Name folgt dem Produkt, außer der Nutzer hat ihn selbst vergeben. Das gezeigte Band folgt mit.
- „Auto-scale“ hält nur eine Colormap, die nicht die des Looks ist.

Damit gelten Vorgabename und Look in Vorschau, angehefteter Ebene und Ergebnis-Layer (der Auftrag trägt den neuen Namen und das neue Produkt). Tests in `ProcessingTerrainProduct.test.tsx`; zwei davon sind ohne die Korrektur rot.

**Nicht geprüft:** Browser-Check gegen echte Daten. Die Cloud-Session hat keinen Zugang zu den Quellen.

### 9.1 Prüfanleitung für Otto

1. Diesen Branch lokal, `docker compose build`, dann `docker compose up`. `catalog-load` läuft vor `api` und schreibt die Collections mit den neuen Feldern.
2. GLO-30 öffnen, Szene ansehen: unter „Quick processing“ stehen „Hillshade“, „Slope“, „Aspect“. Jeweils klicken, „Apply“:
   - Hillshade in Grau (beleuchtete Hänge hell);
   - Slope grün bis rot;
   - Aspect in Regenbogenfarben 0–360°.

   Von z10 bis z0 herauszoomen: Das Bild bleibt, mit der Marke „Overview“ unter `min_zoom`.
3. swissALTI3D und BEV ebenso.
4. Sentinel-2: „False colour (IR)“ und „SWIR“ nach den Indizes. Vegetation erscheint rot bzw. grün; „Enhance contrast“ streckt die drei Kanäle.
5. Anheften („Add to layers“): Die Ebene zeigt das Preset allein.
6. GLO-30, „Hillshade“: Drehknopf ziehen und mit den Pfeiltasten stellen, Höhe schieben; das Bild folgt sofort, das Licht kommt aus der gewählten Richtung. „Slope“: Degrees/Percent umschalten, der Bereich folgt.
7. Processing-Panel, Schritt „Terrain“: Slope → Hillshade → Aspect. Name und Farbskala folgen jedes Mal, auch nach „Auto-scale“. Ein selbst vergebener Name bleibt.

### 9.2 Nachtrag Otto (17.11.2026): einstellbare Parameter

**Registry:** `StepPreset.adjustable` nennt die Parameter, die man unter „Quick processing“ ändern kann; der Rest bleibt fest.
- „Hillshade“: `azimuth`, `altitude`.
- „Slope“: `slope_unit`.
- „Aspect“: keine.
- Prüfung: `catalog` prüft, dass jeder Name in `params` gesetzt ist und keine Bänder nennt; der Start von `api` prüft, dass der Operator ihn kennt.
- `terrain` kennzeichnet Azimut und Höhe mit `x-earthx-unit: deg`; die Fixtures der Prozessbeschreibungen sind neu geschrieben.

**Frontend:**
- **Bedienelement aus dem Schema:** Auswahl → Segment-Knöpfe („Degrees“, „Percent“); Winkel `deg` von 0 bis unter 360 → Drehknopf `AngleDial`; Zahl mit zwei Grenzen → Schieber mit Wert, bei `deg` mit „°“.
- **Drehknopf:** Norden oben, im Uhrzeigersinn. Ziehen im Kreis, Pfeiltasten ±1°, mit Umschalt ±15°, ganze Grad 0–359, Wert daneben. Für Screenreader ist er ein `slider`.
- **Zeichnen:** Die Werte stehen im Look (`AppliedRender.presetParams`). Damit nehmen Kachel, Mosaik, Übersicht unter `min_zoom`, Messung und angeheftete Ebene sie mit.
  - Eine Änderung zeichnet sofort, sobald Look und Bereich da sind.
  - Ist der Bereich gemessen (Hillshade, Slope), wird er 400 ms nach der letzten Änderung neu gemessen und gezeichnet.
  - Ein erneuter Klick auf das Preset setzt die Werte der Registry zurück.
- **Angeheftete Ebene:** Eine Ebene eines Schritts zeigt unter „Quick processing“ nur seine Parameter.

**Leitfaden:** Der Drehknopf ist die dritte Ausnahme von „kein eigenes `<svg>`“ (§3, Tabelle §10, `uiRules.test.ts`).

**Tests:** `paramControls.test.ts`, `components/AngleDial.test.tsx`, `components/ViewQuickPresets.test.tsx`, `quickPresets.test.ts`; Backend `test_quick_presets.py`.

**Browser-Check:** `frontend/e2e/preset-params.cjs` mit `preset-params-harness.html`, die echten Bauteile und Stile in der Breite der Seitenleiste, hell und dunkel. Geprüft werden:
- Ziehen nach N/O/S/W ergibt 0/90/180/270°;
- Pfeiltasten und Umschalt, auch über Norden;
- Farben gleich `--accent`, `--line`, `--muted` des jeweiligen Themas;
- kein Scrollen in 320 px;
- Schieber 0–90;
- Umschalten der Einheit.

Grün am 17.11.2026; der Screenshot liegt nicht im Repo. Nicht geprüft: die ganze Seite gegen echte Daten (die Cloud-Session hat keinen Zugang); dafür §9.1 Punkt 2 mit Drehknopf, Schieber und Einheit.

### 9.3 Browserprüfung Otto (17.11.2026): ruhiges Layout, Zahlen per Tastatur

**Befund:** Beim Drehen des Azimuts verschwand das Histogramm bei jedem Grad und kam wieder. Grund: Jeder Grad war eine neue Frage an die Statistik, und bis zur Antwort gab `useHistograms` nichts zurück. Das Panel sprang um 32 px.

**Behoben:**
- **Histogramm:** `useHistograms` kennt eine Familie. Dasselbe Bild mit anderen Parameterwerten (Bild, Preset, Zuschnitt) behält die Histogramme der letzten Antwort, bis die neuen da sind. Gefragt wird erst nach 400 ms Ruhe. Ein anderes Bild beginnt wie bisher leer.
- **Zeichnen:** Eine Parameteränderung setzt Drehknopf, Schieber und Feld sofort. Gezeichnet und gemessen wird nach 300 ms Ruhe, nicht bei jedem Grad.
- **Zahlenfelder:** Neben Drehknopf und Schieber steht je ein Zahlenfeld mit „°“, schmal und in jeder Zeile gleich breit.
  - Enter oder Verlassen des Felds übernimmt.
  - Werte außerhalb werden begrenzt: Azimut 0–360°, 360 = Norden (0), also 400 → 0; Höhe 0–90°, also −5 → 0 und 120 → 90.
  - Ein Text, der keine Zahl ist, ändert nichts. Ganze Grad.
  - Drehknopf, Schieber und Feld bleiben synchron.
  - Gilt für jeden Parameter mit Drehknopf oder Schieber unter „Quick processing“.

**Tests:** `components/useHistograms.test.tsx`, `components/ViewQuickPresets.test.tsx` (unter anderem keine Messung bei Zwischenwerten).

**Browser-Check:** `frontend/e2e/view-params.cjs` mit `view-params-harness.html`: echte Seitenleiste, Store und Stile, Statistik mit Histogramm nach 250 ms, hell und dunkel.
- Geprüft wird beim langsamen Ziehen über einen halben Kreis, je 5°: Drehknopf, Histogramm, „Quick processing“ und Schieber bewegen sich um keinen Pixel; keine Statistik-Abfrage während des Ziehens; danach eine.
- Dazu: Zahl neben dem Knopf, getippte Werte samt Begrenzung, kein Scrollen.
- Grün am 17.11.2026. Gegenprobe mit dem alten `useHistograms` und `store.ts`: rot (Sprung 32 px, Histogramm weg, 27 Abfragen beim Ziehen).

## 10. Umsetzung PR B (17.11.2026)

Umgesetzt nach §5 mit F5 = 1: Komposit- und Schritt-Presets können jetzt alles, was ein Index kann. Nur Frontend; Registry, Backend und Kachel bleiben unverändert.

**Download („Download crop“ einer angehefteten Ebene)**
- Eine Ebene eines Komposits oder Schritts lädt wie eine Index-Ebene das gerechnete Ergebnis, nicht mehr die Bänder der Szenen.
- Der Auftrag entsteht aus den Schritten des Presets über die Felder des Panels (`draftFromOrder`, dann `buildOrder`). Damit sind Rezept und Hash dieselben wie bei einem Job von Hand.
  - Komposit: drei `band_math`-Schritte, Ausgabe die drei Kanäle `<name>_r`, `_g`, `_b`.
  - Schritt: der Schritt der Registry mit den gewählten Werten der einstellbaren Parameter, Ausgabe das eine Band.
- Der Dialog nennt das Preset mit seinem Knopftext. Dahinter steht beim Index die Formel, beim Komposit die drei Kanäle; beim Schritt nichts.
- Der Hinweis für ganze Szenen nennt das Preset: „NDVI of whole scenes is computed by a job: start one in Processing.“
- Kann der Auftrag nicht gebaut werden (Operator fehlt dem Datensatz, unbekannter Parameter), beginnt die Meldung mit „<Preset> cannot be computed for this dataset“, die Gründe stehen im Tooltip.

**„Process“ an einer Preset-Ebene**
- Das Panel öffnet wie bei einem Index auf dem Auftrag des Presets: seine Schritte vorn und gesperrt, die erzeugten Bänder als ganzer Bestand, keine Rohbänder.
- Ein Schritt nimmt die Werte mit, die in der Ebene gewählt sind (z. B. Azimut 90°).
- Kennt der Datensatz das Preset nicht mehr, öffnet die Ebene wie bisher auf den Bändern der Szenen.

**Komposit als Farbbild (Auslegung, bestätigt von Otto am 17.11.2026: Vorrang = 1, alle Auslegungen von §10 gelten)**
- **Erkennen:** Ein Komposit wird an den Ausdrücken der `band_math`-Schritte erkannt, wie ein Index (`presetFor`), nicht am Namen. Es gilt das erste Komposit der Registry, dessen drei Ausdrücke unter den Bändern stehen.
- **Vorrang:** Es gibt weiter genau einen Eintrag „RGB“. Die echte Farbe (`earthx:true_color`) geht vor, sobald ihre drei Bänder in der Ausgabe bzw. Datei stehen; so bleibt sie immer erreichbar. Das Komposit ist „RGB“ nur dort, wo die echte Farbe fehlt – so bei „Process“ an einer Komposit-Ebene, deren Bestand nur die drei Kanäle sind.
- **Vorschau im Panel:** Ist „RGB“ das Komposit, wird es mit dem festen Bereich je Kanal aus der Registry und ohne Colormap gezeichnet. Die Vorschau beginnt mit „RGB“, solange die drei Kanäle die einzigen Ergebnisse sind; ein einzelner Kanal ist kein Bild des Komposits. Ein danach angelegter Schritt wird wie jedes neue Ergebnis gezeigt (Regel „zuletzt hinzugefügt“).
- **Ergebnis-Layer:** Ein Ergebnis mit den drei Kanälen (ohne die echte Farbe) bietet „RGB“ als dieses Farbbild, in der Reihenfolge Rot, Grün, Blau, wo immer die Kanäle in der Datei stehen. Es beginnt mit dem Band, das die Vorschau zeigte (Regel vom 31.10.2026); ist das nicht bekannt, mit „RGB“.
- **Fehlt ein Kanal**, gilt wie bisher die echte Farbe des Datensatzes (gestreckt nach der Messung des Jobs) oder kein Farbbild.
- **Bezeichnung:** Der Eintrag heißt weiter „RGB“, nicht nach dem Titel des Komposits; ein eigener Name bräuchte ein neues Feld in gespeicherten Ebenen.
- **Ein gewöhnlicher Job** mit den Ausdrücken `nir`, `red`, `green` in drei `band_math`-Schritten wird ebenfalls als „False colour (IR)“ gezeigt. Das ist gewollt wie beim Index: dieselbe Rechnung sieht überall gleich aus.

**Schritt-Presets im Ergebnis-Layer:** Ohne Änderung. Das Band trägt den Look des Operators seit M5-10 (`resultBands` mit `looks`), auch mit geänderten Parametern.

**Tests:**
- `presetOrders.test.ts`: Aufträge, auch Operator fehlt, unbekannter Parameter, keine Szenen.
- `quickPresets.test.ts`: Erkennen eines Komposits (Reihenfolge, Leerzeichen, fehlender Kanal, einzelner Kopier-Schritt, zwei Komposite).
- `indexDownload.test.ts`: Download einer Komposit-Ebene bis zur ZIP, Sperren für ganze Szenen und Lizenz unter „processing“.
- `components/ProcessingPresetLayer.test.tsx`: „Process“, Vorschau als Farbbild, neuer Schritt dahinter, Vorrang der echten Farbe, gesendeter Auftrag.
- `components/ProcessingResultPreset.test.tsx`: Ergebnis-Layer eines Komposits, Vorrang der echten Farbe.
- Gegenprobe: Ohne die Änderungen an Vorschau und Ergebnis-Layer sind vier dieser Tests rot; die Tests zu Vorrang der echten Farbe und neuem Schritt hinter dem Komposit sind gegen den Stand vor dem Review rot.
- Vor dem PR hat der Subagent `reviewer` den Diff geprüft: kein Blocker. Eingearbeitet: Vorrang der echten Farbe, Regel „zuletzt hinzugefügt“ hinter einem Komposit, Tests für Fehlerfälle, Texte und Kommentare.

**Nicht geprüft:** Browser-Check gegen echte Daten; die Cloud-Session hat keinen Zugang zu den Quellen.

### 10.1 Prüfanleitung für Otto

1. Diesen Branch lokal, `docker compose build`, `docker compose up`.
2. Sentinel-2, AOI zeichnen, „Crop and merge“, „False colour (IR)“ anwenden, „Add to layers“. In der Ebene „Download“: Der Dialog nennt „False colour (IR) (nir, red, green)“ und schätzt einen Job; die ZIP enthält die drei Kanäle.
3. Dieselbe Ebene „Process“: Das Panel zeigt die drei Kanäle, keine Rohbänder, keine Schritte zum Ändern; die Vorschau ist das Falschfarbenbild, „Show“ steht auf „RGB“. Job starten, Ergebnis auf die Karte: wieder das Falschfarbenbild mit denselben Bereichen.
4. GLO-30: „Hillshade“, Azimut auf 90° drehen, anheften. „Download“ rechnet die Schummerung mit 90°; „Process“ zeigt das Band `hillshade`, der Job trägt Azimut 90.
5. Gegenprobe Index: NDVI-Ebene wie bisher (Download, „Process“, Ergebnis in `rdylgn`).

