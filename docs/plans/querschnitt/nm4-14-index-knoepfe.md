# NM4-14 — Schnellrechnungen (Index-Knöpfe)

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 14 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für Plan und Recherche, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach NM4-07 und NM4-10; nicht gleichzeitig mit NM4-20 (Panel). Höchstens zwei Stufe-B-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-14 aus `docs/plans/querschnitt/nm4-14-index-knoepfe.md` aus.“

## 1. Anlass

`projektuebersicht.md` §8 sieht datensatzspezifische Presets auf Band math vor. Otto möchte an einem passenden Layer (etwa „Crop & merge to AOI“ bei Sentinel-2) Knöpfe für häufige Indizes.

## 2. Soll

- Knöpfe etwa für NDVI, NDWI, NDSI, NBR, EVI. Ein Klick erzeugt einen normalen Band-math-Schritt mit Vorschau; Start als Job wie gewohnt.
- **Kein zweiter Weg:** Die Knöpfe füllen nur das Rezept; Vorschau, Job, Cache, Runner und `recipe.json` bleiben dieselben.
- **Daten, nicht Code:** Presets stehen je Datensatz in der Registry (Name, Ausdruck, Wertebereich, Colormap-Vorgabe, Quelle der Formel). Nur Datensätze mit passenden Bändern zeigen sie. Kein datensatzspezifischer Code.

## 3. Im Plan klären (mit Optionen und Empfehlung)

- **Formeln mit Quelle** (etwa Awesome Spectral Indices, Montero et al. 2023, *Scientific Data*); Konstanten (EVI) mit Quelle.
- Welche Indizes zuerst; Ort der Knöpfe (Layer, Panel, beides; Abstimmung mit UI-01).
- Setzt ein Preset die Bänder (NM4-07) und den Ergebnisnamen (NM4-10, etwa `NDVI`)?
- Mosaik (NM4-04) und Kette mit `mask` („NDVI cloud-free“)?

## 4. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: Preset erzeugt dasselbe Rezept wie der von Hand eingegebene Ausdruck; Datensatz ohne passende Bänder zeigt keinen Knopf; Formeln gegen Referenzwerte.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n) mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat, siehe Kopf des Backlogs).
- Vor „fertig“ ist main geholt.

---

# Plan (30.10.2026)

Belegstufen wie in `adr/0009`: [M] gemessen, [P] am Primärdokument oder im Code gelesen, [S] Zusammenfassung oder Suchtreffer, [A] eigene Ableitung. Grundlage ist das Bandmodell aus `adr/0020` (angenommen): Ein `band_math`-Schritt (Version 2) fügt ein Band mit eigenem Namen hinzu (§4, §6), die Ausgabe wählt `output.bands` (§5), ein neues Ergebnis ist angehakt (§9), die Vorschau zeigt ein Band (§10). Für NM4-14 steht dort schon (§12): „ein Knopf = ein `band_math`-Schritt mit Namen aus dem Preset (`NDVI`), sein Ergebnis angehakt. Zwei Knöpfe = zwei Schritte, zwei Bänder. Trägt der Datensatz schon ein Band dieses Namens, hängt das Panel eine Zahl an (`NDVI_2`).“ Gelesen auf `main` = `f2d0c96`.

**Zeitpunkt der Umsetzung.** Laut Startsatz kommt der Code erst nach NM4-43e. NM4-43e ist am 30.10.2026 weder begonnen noch gemergt (Backlog Punkt 43, Entscheidungslog). Dieser Draft-PR enthält deshalb nur den Plan. Nachträge heißen nach der Aufgabe („§15 Nachtrag NM4-14“).

## 6. Kurzfassung

- **Kein neuer Rechenweg.** `band_math` Version 2 kann alle fünf Formeln schon heute: Bandnamen, Zahlen, `+ − * /` (R5). Ein Klick legt denselben Schritt an wie „＋ Band math“, nur mit `expression` und `name` aus dem Preset. Rezept, Hash, Vorschau, Job, Cache, Runner und Methodentext sind dieselben wie von Hand. Es gibt keine neue `op_version`, keine neue `recipe_version`, keine Markierung „Preset“ im Rezept, und `earthx.__version__` bleibt.
- **Empfehlung Frage 1 (R1): ein Registry-Feld `index_presets` je Datensatz.** Je Preset stehen dort `name`, `title`, `expression` in den Bandnamen des Datensatzes, Wertebereich und Colormap (Feldnamen der STAC-Render-Extension wie bei `default_render`), die Formel im Wortlaut von Awesome Spectral Indices (ASI) und die Quelle. Das Feld hat keine Vorgabe (B10). Der DEM trägt eine leere Liste und zeigt keinen Knopf. Die Collection liefert das Feld als `earthx:index_presets`.
- **Indizes zuerst (Frage 2):** NDVI, NDWI (McFeeters), NDSI, NBR, EVI, wie Otto sie nennt. Alle fünf sind in ASI belegt [P] und in Sentinel Hub mit denselben Bändern gerechnet [P]. Die EVI-Konstanten (G 2,5, C1 6, C2 7,5, L 1) stehen in ASI `constants.json` [P] und im EVI-Skript von Sentinel Hub [P].
- **Ort (Frage 3):** eine Zeile „Index“ unter „Add step“ im Panel. Das Panel öffnet sich vom Layer bzw. von „Crop & merge to AOI“ aus wie heute. Die Zeilen im Layer-Manager bleiben, wie UI-01 §6.11 sie festlegt.
- **Darstellung (Frage 4):** Wertebereich und Colormap des Presets gelten für jedes Band, dessen Ausdruck gleich dem Ausdruck eines Presets des Datensatzes ist. Das gilt in der Vorschau und am Ergebnis-Layer, aus den Daten abgeleitet und ohne gespeicherten Zustand. Wer den Ausdruck ändert, bekommt die heutige Regel.
- **Mosaik und Maske (Frage 5):** Ein Knopf legt nur den `band_math`-Schritt an. „NDVI cloud-free“ ist ein Klick auf „＋ Mask“ dazu. Die Reihenfolge spielt dabei keine Rolle (`adr/0020` §4). EVI mit Maske braucht 4 Assets und passt unter die Grenze der Mosaik-Kachel.
- **Schnitt (Frage 6):** zwei PRs nach NM4-43e, Backend (Registry, Prüfung, Collection, Nachträge) und Frontend (Knöpfe, Darstellung).

## 7. Befunde

### 7.1 `band_math` reicht für alle fünf Formeln [P]

- `processing/operators/band_math.py`: Ein Ausdruck darf Bandnamen, endliche Zahlen, `+ - * /`, unäres `-`, `**` mit ganzzahligem Exponent bis 50, Vergleiche und `where`, `abs`, `minimum`, `maximum`, `sqrt` enthalten. Erlaubt sind höchstens 256 Zeichen, nur druckbares ASCII und mindestens ein Bandname (`check_expression`). Die längste Formel (EVI) hat 49 Zeichen.
- Gerechnet wird in `float64` mit `numexpr`, das Ergebnis ist `float32`. Ein nicht endliches Ergebnis (`0/0`, `x/0`) wird maskiert (NaN). Ein Pixel, in dem ein genanntes Band maskiert ist, wird ebenfalls maskiert. Bei Normalized Differences gibt es damit kein `inf`.
- Version 2 (NM4-43c): Parameter `expression` und `name` (Regel `^[A-Za-z][A-Za-z0-9_]{0,31}$`, kein Schlüsselwort, kein Funktionsname, eindeutig ohne Groß-/Kleinschreibung), `listed=False` bis NM4-43e.
- Der Kern rechnet auf physikalischen Werten (`adr/0014` §5.4). Bei Sentinel-2 C1 tragen die Items `scale` 0.0001 und `offset` −0.1 (`tests/fixtures/earth_search/search_real_shape.json`), die Reflexion liegt also bei 0…1. Das ist die Voraussetzung für die Konstante L = 1 in EVI [A], weil EVI für Reflexion von 0 bis 1 gilt.
- Methodentext (NM4-08) von Version 2: „A band named NDVI was computed per pixel from the expression '(nir - red) / (nir + red)' …“. Für ein Preset ist er unverändert.

### 7.2 Registry und Collection [P]

- Zwei Datensätze: `sentinel-2-c1-l2a` und `cop-dem-glo-30` (`catalog/datasets.py`). Sentinel-1 kommt erst mit DS-04, die SAR-Presets mit DS-05 („nach NM4-14“).
- `DatasetConfig` (`catalog/registry.py:887`): Jedes Feld ist ohne Vorgabe (B10), geprüft wird in `__post_init__`. Vorbilder für ein neues Feld: `auxiliary_assets` (NM4-07), `search_filters` (DS-02) und `default_render` mit den Feldnamen der Render-Extension (`rescale`, `colormap_name`).
- Die Bandnamen kennt die Registry über die Schlüssel von `band_units`. Bei Sentinel-2 sind das `coastal, blue, green, red, rededge1–3, nir, nir08, nir09, swir16, swir22` sowie `aot`, `wvp`, `cloud`, `snow`, `scl`, `visual`, `preview`. Bei Earth Search sind die Asset-Schlüssel genau die STAC-`eo:common_name` [P]. `eo:common_name` selbst führt die Registry nicht.
- Die Collection liefert jedes Feld als `earthx:…` (`catalog/collection.py:193–233`). Das Frontend liest diese Felder in `types.ts:197–213` und in `processingOrder.ts` (`earthx:auxiliary_assets`, `earthx:mask`). Ein neues Feld bekommt eine Zeile in `architekturplan.md` 5.1, wie `earthx:search_filters`.
- **Importgrenzen:** `catalog` darf `processing` nicht importieren (`.importlinter`), kann also `band_math.check_expression` nicht aufrufen. Das Vorbild dafür ist `adapters.check_adapter_specs(registry, adapters)`: Es wird beim Bau der App aufgerufen (`api/main.py:169`, `api/tiler.py`) und stoppt den Start, wenn ein Eintrag etwas verlangt, das es nicht gibt.

### 7.3 Panel heute und nach NM4-43e [P]

- „Add step“: `components/ProcessingPanel.tsx:656–679`, je Operator ein Knopf „＋ Band math“. Er ist gesperrt, wenn der Operator nicht unterstützt wird oder die Schritte voll sind (Grund im Tooltip).
- `processingStore.ts:1257–1272` `addStep(op, opVersion)`: Die Werte kommen aus `initialValues` des Schemas. Bei `mask` kommen sie zusätzlich aus der Registry (`maskStepValues`), das ist ein Vorbild für „Werte aus der Registry in einen normalen Schritt“.
- NM4-43e (`plans/querschnitt/nm4-43-ausgabe-baender.md` §6.5) bringt: das Feld „Name“ am Schritt (Vorgabe `Band_Math_<n>`), die Namensregeln im Panel, die Ausgabe am Ende mit dem neuen Ergebnis angehakt, die Vorschau mit „Show“ (Vorgabe: letztes Ergebnis) und `band=` an der Kachel. NM4-14 setzt darauf auf und baut nichts davon selbst.
- „Crop & merge to AOI“ ist ein Knopf der Ansicht (`components/ViewBar.tsx:52`). Das Panel öffnet sich dort über `openProcessing()` (`:90`), im Layer-Manager über `processLayer`.

### 7.4 Darstellung heute [P]

- `render.ts:140–161` `scaleOf` und `resultLayer.ts:72–88` `resultRender` bestimmen die Darstellung eines Ergebnisses in dieser Reihenfolge: Ganzzahl wie sie ist; der Bereich des Benutzers; die Index-Regel (Band-math-Ergebnis mit 2–98 % in −1…1 → −1…1 in `rdylgn`); sonst 2–98 % in `viridis`. Die Vorschau im Panel nimmt `INDEX_RANGE`/`INDEX_COLORMAP` als Vorgabe (`processingPreview.ts:57–81`).
- Die Auswahl im Panel: `render.ts:11–25` `COLORMAPS` (13 Namen, ohne `rdbu` und `blues`). Der Tiler nimmt die Namen von rio-tiler: In der Sitzung hat rio-tiler 9.4.6 211 Namen, darunter `rdylgn`, `rdbu`, `blues`, `brbg`, `ylgn` [M].

### 7.5 Formeln und Quellen [P]

ASI, `output/spectral-indices-dict.json`, `constants.json` und `bands.json` am Commit `835fea7` (gelesen mit `curl`, Werte mit Python ausgegeben). ASI steht unter MIT-Lizenz („Copyright (c) 2021 David Montero Loaiza“). Zitiert wird Montero et al. 2023, *Scientific Data* 10, 197, https://doi.org/10.1038/s41597-023-02096-0 (README; Wortlaut der Zitation über einen Extraktor gelesen, [P]).

| Preset | ASI `long_name` | ASI `formula` | Ausdruck Sentinel-2 C1 (Vorschlag) | Quelle der Formel laut ASI | Sentinel Hub `custom-scripts` |
|---|---|---|---|---|---|
| NDVI | Normalized Difference Vegetation Index | `(N - R)/(N + R)` | `(nir - red) / (nir + red)` | https://ntrs.nasa.gov/citations/19740022614 | `index(B08, B04)` |
| NDWI | Normalized Difference Water Index | `(G - N) / (G + N)` | `(green - nir) / (green + nir)` | https://doi.org/10.1080/01431169608948714 (McFeeters 1996) | `index(B03, B08)` |
| NDSI | Normalized Difference Snow Index | `(G - S1) / (G + S1)` | `(green - swir16) / (green + swir16)` | https://doi.org/10.1109/IGARSS.1994.399618 | `index(B03, B11)`, Schnee über 0,42 |
| NBR | Normalized Burn Ratio | `(N - S2) / (N + S2)` | `(nir - swir22) / (nir + swir22)` | https://doi.org/10.3133/ofr0211 | `(B08 - B12) / (B08 + B12)` |
| EVI | Enhanced Vegetation Index | `g * (N - R) / (N + C1 * R - C2 * B + L)` | `2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)` | https://doi.org/10.1016/S0034-4257(96)00112-5 | `2.5 * (B08 - B04) / ((B08 + 6.0 * B04 - 7.5 * B02) + 1.0)` |

- **Konstanten EVI** (`constants.json`): `g` 2.5 „Gain factor“, `C1` 6.0 und `C2` 7.5 „Coefficient … for the aerosol resistance term“, `L` 1.0 „Canopy background adjustment“. Zweite Quelle mit denselben Werten: das EVI-Skript von Sentinel Hub (`sentinel-2/evi/script.js:39`). Die USGS-Seite zum Landsat-EVI nennt dieselben Werte; sie war aus der Sitzung nicht erreichbar [S].
- **Bänder** (`bands.json`): N = `nir` = Sentinel-2 **B8** (760–900 nm), N2 = `nir08` = B8A, R = `red` = B4, G = `green` = B3, B = `blue` = B2, S1 = `swir16` = B11, S2 = `swir22` = B12. Für N nimmt das Preset also `nir` (B08), nicht `nir08`. Sentinel Hub tut dasselbe für NDVI, NDWI, NBR und EVI.
- **Namen:** ASI und Sentinel Hub nennen den Index nach McFeeters (Grün/NIR) „NDWI“. Den Index nach Gao (NIR/SWIR) führt ASI als NDMI bzw. NDII. NDSI und MNDWI haben in ASI dieselbe Formel (`(G - S1) / (G + S1)`).
- **Wertebereich:** Die vier Normalized Differences liegen in −1…1, weil die Reflexion nicht negativ ist [A]. Die Reflexion von Sentinel-2 C1 kann nach dem Offset leicht negativ sein (−0,1 bei DN 0), dann sind auch Werte außerhalb möglich [A]. EVI ist nicht beschränkt, wenn der Nenner nahe 0 liegt [A]. Der HLS-VI-Guide nennt −1…1 als gültigen Bereich [S]. Das ist für die Darstellung relevant, für die Rechnung nicht: `band_math` schneidet nichts ab.
- **Nicht geklärt:** der Titel der Arbeit hinter der EVI-DOI von ASI (nicht die DOI von Huete et al. 2002, Remote Sensing of Environment 83). Das Preset nennt die DOI so, wie ASI sie führt.

### 7.6 Andere Plattformen [P] [S]

| Plattform | Index-Presets | Bandzuordnung |
|---|---|---|
| Sentinel Hub `custom-scripts` | ein Skript je Index, mit fester Farbrampe (NDWI grün–weiß–blau von −0,8 bis 0,8; EVI eigene Rampe) [P] | feste Bänder je Sensor im Skript [P] |
| openEO Python-Client `openeo.extra.spectral_indices` | `compute_index`, `append_index` u. a. über die gebündelten ASI-Dateien, „new experimental API“ [P, über Extraktor] | über `platform` und ASI `bands.json`, sonst `variable_map` von Hand; nicht über `eo:common_name` [P, über Extraktor] |
| STAC Render Extension v2.1.0 | Render-Objekt mit `assets`, `expression` („format is defined by the rendering application“), `rescale`, `colormap_name`; Beispiel NDVI mit `rescale [[-1,1]]`, `colormap_name ylgn` [P, über Extraktor] | Asset-Schlüssel |
| Earth Engine `normalizedDifference`, QGIS | nicht geprüft (Seite gesperrt bzw. nicht gelesen) | — |

Andere Plattformen pflegen also auch je Index eine Formel und je Sensor die Bänder. Den Index selbst berechnet überall Band math; kein Anbieter hat einen eigenen Operator je Index.

## 8. Optionen und Empfehlung

### 8.1 Wo die Presets stehen (Frage 1)

| | R1 Feld je Datensatz, Ausdruck in den Bandnamen des Datensatzes | R2 eine Formeltabelle in ASI-Schreibweise und je Datensatz eine Zuordnung `N → nir` | R3 als STAC `renders` an der Collection |
|---|---|---|---|
| Daten, nicht Code | ✓ | ✓ Tabelle und Zuordnung; der Ausdruck entsteht durch eine allgemeine Ersetzung | ✓ |
| Fehlerquelle | Abschreiben je Datensatz; ein Test rechnet gegen die ASI-Formel (§10) | die Zuordnung (B8 gegen B8A); Konstanten je Sensor | wie R1 |
| Neue Teile | ein Feld, eine Prüfung | Feld, Tabelle, Ersetzer | ein Feld, aber `expression` ist dort Sache des Renderers. Unser Tiler nimmt keinen freien Ausdruck (M4-09), ein STAC-Client, der `renders` an einen TiTiler schickt, bekäme `400` |
| Nutzen ab | heute (ein optischer Datensatz) | ab dem zweiten optischen Datensatz (Landsat) | — |

**Empfehlung: R1.** Bei einem optischen Datensatz ist es das Einfachste. Die Feldnamen für die Darstellung folgen der Render-Extension (`rescale`, `colormap_name`), wie bei `default_render`. R2 kann mit den YAML-Einträgen ab M5 (B13) kommen, ohne dass sich die Form in der Collection ändert. Der Ausdruck je Datensatz bleibt dann abgeleitet.

**Form (Vorschlag):**

```python
index_presets=(
    IndexPreset(
        name="NDVI",
        title="Normalized Difference Vegetation Index",
        expression="(nir - red) / (nir + red)",
        rescale=(-1.0, 1.0),
        colormap_name="rdylgn",
        formula="(N - R)/(N + R)",
        reference="https://ntrs.nasa.gov/citations/19740022614",
    ),
    ...
)
```

- `name`: Name des Ergebnisbandes und Text des Knopfes (Regeln von `check_name`).
- `title`: steht im Tooltip.
- `expression`: in den Bandnamen des Datensatzes, so wie ein Mensch ihn tippt.
- `rescale`, `colormap_name`: Darstellung (§8.4).
- `formula`: Wortlaut von ASI.
- `reference`: die Quelle der Formel, wie ASI sie nennt.
- Am Modul steht einmal die Herkunft: ASI mit Commit und die Zitation Montero et al. 2023.
- In der Collection steht dasselbe als `earthx:index_presets`, `rescale` als `[[-1, 1]]` wie in `earthx:default_render`.

**Prüfung beim Laden** (Vorschlag), zweistufig wegen der Importgrenze (§7.2):

1. In `catalog`, `__post_init__`:
   - `name` nach der Regel von §6 in `adr/0020` (Muster als Konstante in `catalog`) und eindeutig ohne Groß-/Kleinschreibung;
   - keine Kollision mit einem Schlüssel von `band_units`;
   - jeder Bezeichner in `expression` ist ein Schlüssel von `band_units`, kein Hilfs-Asset und nicht die Maskenschicht;
   - `rescale` endlich mit `low < high`;
   - `reference` beginnt mit `https://`;
   - Presets nur bei `capabilities.band_math`.
2. In `processing`, eine Funktion `check_index_presets(registry)` nach dem Vorbild von `check_adapter_specs`, aufgerufen beim Bau von `api` und `tiler`:
   - `band_math.check_expression` und `check_name` für jedes Preset;
   - `colormap_name` unter den Namen von rio-tiler.

   Ein Fehler stoppt den Start mit Datensatz und Preset im Text.

### 8.2 Welche Indizes zuerst (Frage 2)

1. **NDVI, NDWI, NDSI, NBR, EVI** (Ottos Liste), alle mit Sentinel-2-Bändern, die Earth Search liefert. **(Empfehlung)**
2. Wie 1, dazu NDMI (`(nir - swir16) / (nir + swir16)`, Feuchte) und SAVI. Bei SAVI ist L in ASI 1.0, Huete 1988 empfiehlt 0,5 [S]. Das wäre ein Wert, den Otto festlegt.
3. Nur NDVI und NDWI.

NDWI heißt im Knopf „NDWI“. Im Tooltip steht der Titel mit „(McFeeters 1996)“, damit niemand den Gao-Index erwartet (KE2).

### 8.3 Ort der Knöpfe (Frage 3, Abstimmung mit UI-01)

| | O1 im Panel unter „Add step“ | O2 wie O1, dazu „Index ▾“ in der Leiste der Ansicht neben „Crop & merge to AOI“ | O3 im Layer-Manager (Menü ⚙ der Zeile) |
|---|---|---|---|
| Weg zum Index | Ansicht → Process → NDVI (wie heute zum Band math) | Ansicht → Index ▾ → NDVI öffnet das Panel mit dem Schritt | Zeile → ⚙ → NDVI |
| UI-01 | keine neue Spalte, nichts verschoben | neuer Knopf in der Ansicht | gegen die festen Spalten der Zeile (§6.11) |
| Ein Weg | ✓ | zwei Einstiege, ein Schritt | zwei Einstiege |
| Text | eine Zeile Knöpfe | ein Menü | ein Menü |

**Empfehlung: O1.** Das Panel ist der Ort, an dem Schritte entstehen. NM4-20 ordnet das Panel später ohnehin neu.

### 8.4 Name, Bänder, Ausgabe (aus NM4-07 und NM4-10; entschieden mit `adr/0020`)

- **Name:** Der Schritt bekommt `name` aus dem Preset (`NDVI`). Ein zweiter Klick auf NDVI oder ein Name, der in der Kette schon vorkommt, ergibt `NDVI_2`, `NDVI_3` (`adr/0020` §12). Die Prüfung von 8.1 verhindert eine Kollision mit einem Band des Datensatzes. Der Name lässt sich umbenennen wie jeder andere (NM4-43e).
- **Bänder:** Nach NM4-43e gibt es keine Eingabeauswahl mehr; `api` leitet die Assets aus dem Ausdruck ab. Ein Preset wählt also nichts aus.
- **Ausgabe:** Das neue Ergebnis ist angehakt (`adr/0020` §9 Punkt 1). Sonst wird nichts angehakt.
- **Vorschau:** „Show“ springt auf das letzte Ergebnis, also auf den geklickten Index (NM4-43e).

### 8.5 Darstellung (Frage 4)

| | D1 Preset setzt nur beim Klick den Bereich der Vorschau | D2 Bereich und Colormap gelten für jedes Band, dessen Ausdruck gleich dem eines Presets ist | D3 keine Vorgabe, die Index-Regel bleibt |
|---|---|---|---|
| Vorschau | ✓, bis der Benutzer etwas ändert | ✓ | −1…1 `rdylgn`, wenn 2–98 % in −1…1 liegen |
| Ergebnis-Layer | Index-Regel | ✓, aus dem Ausdruck des Ergebnisbandes | Index-Regel |
| Datei, Permalink, Ablage | Index-Regel | ✓, gleiche Regel | Index-Regel |
| Zustand | ein Bereich im Store | keiner, abgeleitet aus Datensatz und Ausdruck | keiner |
| Vergleichbar zwischen Jobs | nein | ja, fester Bereich je Index | nur für Indizes, deren Werte in −1…1 liegen |

**Empfehlung: D2.** Die Regel in `resultRender` wird: Ganzzahl → Bereich des Benutzers → **Preset des Datensatzes mit gleichem Ausdruck** → Index-Regel → 2–98 %. Gleich heißt token-gleich nach demselben Zerleger wie die Chips: `(nir-red)/(nir+red)` und `(nir - red) / (nir + red)` zählen gleich, `(red-nir)/(red+nir)` nicht. Ein geänderter Ausdruck fällt auf die heutige Regel zurück. Den Ausdruck je Band trägt das Ergebnis in `processing:expression` (`band_math.py:382`). Welche Stelle ihn bei mehreren Ergebnisbändern je Band hält, prüft die Umsetzung [A].

**Vorgaben (Vorschlag, KE3):**

| Preset | Bereich | Colormap | Grund |
|---|---|---|---|
| NDVI | −1…1 | `rdylgn` | wie die Index-Regel heute |
| NDWI | −1…1 | `rdbu` | Wasser positiv, blau; Sentinel Hub zeigt grün–weiß–blau |
| NDSI | −1…1 | `rdbu` | Schnee positiv, blau |
| NBR | −1…1 | `rdylgn` | verbrannt niedrig, rot |
| EVI | −1…1 | `rdylgn` | Vegetation; Bereich nach dem HLS-Guide [S] |

`rdbu` kommt in die Auswahl `COLORMAPS` des Frontends. Das ist ein Name mehr in der Liste und keine neue Abhängigkeit.

### 8.6 Mosaik und Kette mit `mask` (Frage 5)

- **Mosaik (NM4-04):** Es gibt nichts Besonderes. Ein Preset ist ein `band_math`-Schritt, und die Mosaik-Kachel rechnet ihn wie den von Hand. Mit NM4-43d öffnet die Kachel nur die Assets des gezeigten Bandes: NDVI 2, EVI 3, EVI mit Maske 4 (`scl`). Das passt unter `MAX_MOSAIC_OPERATOR_ASSETS = 4` [P].
- **„NDVI cloud-free“:**

| | K1 Knopf = nur `band_math`; Maske ist ein eigener Klick „＋ Mask“ | K2 Preset-Ketten in der Registry (`mask` + `band_math`) | K3 Schalter „Cloud-free“ in der Zeile „Index“: fügt eine Maske ein, wenn keine da ist |
|---|---|---|---|
| Klicks | 2 | 1 | 1 (Schalter einmal) |
| Neue Teile | keine | Ketten als Datenform, Konflikt mit vorhandener Maske | ein Schalter, eine Regel |
| Reihenfolge | egal, `mask` wirkt auf den ganzen Vorrat (`adr/0020` §4) | fest | egal |

  **Empfehlung: K1.** Die Maske kommt mit `suggested`-Klassen aus der Registry schon vorbelegt (M4-18), und eine Maske gilt für alle Indizes der Kette.

### 8.7 Panel-Skizze (nach NM4-43e, Texte englisch, UI-01 §4)

```
  Steps
    1. NDVI          band math
       Expression [ (nir - red) / (nir + red)     ]          ▲ ▼ ✕
       Name       [ NDVI         ]
    Add step:  ＋ Band math   ＋ Mask   ＋ Normalize   ＋ Reproject
    Index:     ＋ NDVI   ＋ NDWI   ＋ NDSI   ＋ NBR   ＋ EVI
               └ ⓘ tooltip on NDVI: "Normalized Difference Vegetation Index: (N - R)/(N + R).
                  Formula: Awesome Spectral Indices."
```

- Die Zeile „Index“ erscheint nur, wenn der Datensatz Presets hat und `band_math` in der Prozessbeschreibung steht. Sonst ist sie ausgeblendet (Regel vom 26.10.2026: nicht Mögliches ausblenden).
- Ein Knopf ist gesperrt, wenn „＋ Band math“ gesperrt ist (Schritte voll, Operator nicht unterstützt), mit demselben Grund im Tooltip.
- Der Klick ruft dieselbe Funktion wie „＋ Band math“ (`addStep`) mit `expression` und `name` aus dem Preset auf. Danach ist der Schritt ein gewöhnlicher Schritt: Ausdruck und Name lassen sich ändern.
- Kein Text unter den Knöpfen. Titel, Formel und Quelle stehen im Tooltip (`title` und `aria-label`, für Screenreader erreichbar).

### 8.8 Schnitt (Frage 6)

Schätzung [A]: Backend ~120 Zeilen Code und ~200 Zeilen Tests (Feld, Prüfung, Collection, Daten der fünf Presets, Nachträge). Frontend ~150 Zeilen Code und ~250 Zeilen Tests (Typ, Zeile „Index“, Darstellung D2, `COLORMAPS`).

1. **Zwei PRs nach NM4-43e in dieser Session, gestapelt:** NM4-14a Backend, NM4-14b Frontend. **(Empfehlung, folgt dem Startsatz)**
2. NM4-14a sofort, weil es das Panel nicht berührt (wie NM4-11a), NM4-14b nach NM4-43e.
3. Ein PR (~720 Zeilen, über dem Richtwert).

## 9. Kleinentscheidungen

Gelten, sofern du nicht widersprichst:

- **KE1 Versionen:** keine neue `op_version`, `recipe_version` 2 bleibt, `earthx.__version__` bleibt (kein Ergebnis ändert seine Bytes). Ein Rezept aus einem Preset ist nicht vom getippten zu unterscheiden.
- **KE2 Texte:**
  - Knopf mit dem Kurznamen (`＋ NDVI`).
  - Tooltip: `<title>: <ASI-Formel>. Formula: Awesome Spectral Indices.`
  - NDWI mit „(McFeeters 1996)“ im Titel.
  - Die Quelle (`reference`) steht in der Collection, im Tooltip nicht als Link.
- **KE3 Darstellung:** die Tabelle in §8.5.
- **KE4 Methodentext und Jobtitel:** unverändert. Der Methodentext nennt Name und Ausdruck schon. Der Vorgabetitel bleibt „Band math · Sentinel-2 L2A · 1 Oct“ (UI-01 §6.5).
- **KE5 DEM:** `index_presets=()` ausdrücklich, also kein Knopf.
- **KE6 Nachträge:**
  - `architekturplan.md` 5.1, Zeile `earthx:index_presets`;
  - `adr/0014` „§15 Nachtrag NM4-14“: Presets füllen nur das Rezept, keine `op_version`, die Prüfung beim Start;
  - `adr/0020` §12 bleibt.
- **KE7 Log:** keine neue Logzeile im Code; Fehler der Prüfung beim Start nennen Datensatz und Preset, keine Adressen.
- **KE8 Herkunft:** Die Formeln stammen aus ASI am Commit `835fea7` (MIT). Es wird nichts aus ASI ins Repo kopiert außer den Formeltexten in `formula`, mit Quelle. Keine neue Abhängigkeit, auch nicht `spyndex`.

## 10. Tests (Abnahme)

Backend (`pytest`):

1. **Referenzwerte:** Jedes Preset von Sentinel-2 läuft durch den Kern von `band_math` Version 2 auf einem kleinen synthetischen Raster und wird gegen eine Rechnung mit `fractions.Fraction` verglichen. Ergebnis `float32` gleich. Beispiel mit blue 0.05, green 0.08, red 0.06, nir 0.40, swir16 0.20, swir22 0.10: NDVI 0.73913…, NDWI −0.66667…, NDSI −0.42857…, NBR 0.6, EVI 0.61372… [M, mit Python gerechnet].
2. **Gegen die ASI-Formel:** `formula` mit der Zuordnung N→`nir`, R→`red`, G→`green`, B→`blue`, S1→`swir16`, S2→`swir22` und den Konstanten aus `constants.json` (g, C1, C2, L) ergibt auf denselben Werten dasselbe wie `expression`. Die Zuordnung steht nur im Test. Das fängt Abschreibfehler wie `nir08` statt `nir`.
3. **Gleiches Rezept:** Ein Auftrag mit dem Schritt aus dem Preset und einer mit dem getippten Ausdruck und Namen ergeben dasselbe Rezept und denselben Hash.
4. **Registry, Fehleingaben:** jeweils mit Grund im Text abgewiesen:
   - Name doppelt oder in anderer Schreibweise doppelt;
   - Name gleich einem Band (`red`), Schlüsselwort, Funktionsname, 33 Zeichen;
   - Ausdruck mit unbekanntem Band, mit einem Hilfs-Asset (`visual`) oder der Maskenschicht (`scl`);
   - Ausdruck mit `log`;
   - `rescale` leer, umgekehrt oder NaN;
   - unbekannte Colormap;
   - `reference` ohne `https://`;
   - Presets bei `band_math=False`;
   - fehlendes Feld (keine Vorgabe, B10).
5. **Collection:** `earthx:index_presets` für Sentinel-2 mit fünf Einträgen, für den DEM eine leere Liste; die Form ist im Vertragstest festgehalten.
6. **Start:** Ein Eintrag mit einem Preset, das `check_expression` nicht besteht, stoppt den Bau von `api` und `tiler` mit Datensatz und Preset im Text.
7. **Gegenprobe:** Die Tests 4–6 scheitern gegen den Code vor der Änderung (das Feld fehlt); Ergebnis im PR.

Frontend (`vitest`, NM4-14b):

8. Ein Klick auf NDVI ergibt denselben Auftrag (JSON) wie „＋ Band math“, getippter Ausdruck und Name `NDVI`.
9. Ein Datensatz ohne Presets (DEM) zeigt keine Zeile „Index“. Ein Datensatz mit Presets, aber ohne `band_math` in der Prozessbeschreibung, zeigt sie auch nicht.
10. Ein zweiter Klick ergibt `NDVI_2`; das Ergebnis ist angehakt; „Show“ steht auf dem neuen Band; bei vollen Schritten ist der Knopf gesperrt, mit Grund.
11. Darstellung D2 in Vorschau, Ergebnis-Layer und Datei bzw. Permalink:
    - gleicher Ausdruck mit anderen Leerzeichen → Preset;
    - geänderter Ausdruck → Index-Regel;
    - Bereich des Benutzers geht vor;
    - ein Ausdruck eines anderen Datensatzes zählt nicht.
12. Tooltips (Titel, Formel, Quelle) erreichbar über `aria-label`; kein Text unter den Knöpfen.
13. Prüfung im echten Browser (Chromium/Playwright der Sitzung) mit nachgestellten Antworten, hell und dunkel, schmales Fenster; im PR beschrieben, Bilder nicht ins Repo.
14. Prüfanleitung für Otto im PR: Browser, dazu PowerShell 5.1 mit `GET /collections/sentinel-2-c1-l2a` und einem Auftrag NDVI aus dem Preset gegen einen getippten (gleicher Hash).

## 11. Fragen an Otto

Kurz beantwortbar: je Frage eine Nummer.

**Frage 1 — Wo die Presets stehen**
1. Feld `index_presets` je Datensatz, Ausdruck in den Bandnamen des Datensatzes (R1). **(Empfehlung)**
2. Formeltabelle in ASI-Schreibweise und Zuordnung je Datensatz (R2).
3. Als STAC `renders` an der Collection (R3).

**Frage 2 — Indizes zuerst**
1. NDVI, NDWI (McFeeters), NDSI, NBR, EVI. **(Empfehlung)**
2. Wie 1, dazu NDMI und SAVI (L festlegen).
3. Nur NDVI und NDWI.

**Frage 3 — Ort der Knöpfe**
1. Zeile „Index“ im Panel unter „Add step“ (O1). **(Empfehlung)**
2. Wie 1, dazu „Index ▾“ in der Ansicht neben „Crop & merge to AOI“ (O2).
3. Im Layer-Manager, Menü ⚙ (O3).

**Frage 4 — Darstellung**
1. Bereich und Colormap des Presets für jedes Band mit gleichem Ausdruck, in Vorschau und Ergebnis (D2). **(Empfehlung)**
2. Nur beim Klick als Bereich der Vorschau (D1).
3. Keine Vorgabe, Index-Regel wie heute (D3).

**Frage 5 — „NDVI cloud-free“**
1. Knopf = nur `band_math`; Maske mit „＋ Mask“ dazu (K1). **(Empfehlung)**
2. Ketten als Preset in der Registry (K2).
3. Schalter „Cloud-free“ in der Zeile „Index“ (K3).

**Frage 6 — Schnitt**
1. Zwei PRs nach NM4-43e in dieser Session, gestapelt. **(Empfehlung)**
2. Backend sofort, Frontend nach NM4-43e.
3. Ein PR.

## 12. Quellen

- Awesome Spectral Indices, `output/spectral-indices-dict.json`, `output/constants.json`, `output/bands.json`, `LICENSE` am Commit `835fea7`: https://raw.githubusercontent.com/awesome-spectral-indices/awesome-spectral-indices/main/output/spectral-indices-dict.json (und die Nachbardateien) [P]
- Montero, D., Aybar, C., Mahecha, M. D., Martinuzzi, F., Söchting, M., Wieneke, S. (2023): A standardized catalogue of spectral indices to advance the use of remote sensing in Earth system research. *Scientific Data* 10, 197. https://doi.org/10.1038/s41597-023-02096-0 [P, README über Extraktor]
- Sentinel Hub `custom-scripts` am Commit `63464a4`, `sentinel-2/{ndvi,ndwi,ndsi,nbr,evi}/script.js`: https://raw.githubusercontent.com/sentinel-hub/custom-scripts/main/sentinel-2/evi/script.js (und die Nachbardateien) [P]
- STAC Render Extension v2.1.0 (Commit `eb448fd`): https://raw.githubusercontent.com/stac-extensions/render/main/README.md [P, über Extraktor]
- STAC EO Extension, Common Names: https://raw.githubusercontent.com/stac-extensions/eo/main/README.md [P, über Extraktor]
- openEO Python-Client, `openeo/extra/spectral_indices/spectral_indices.py`: https://raw.githubusercontent.com/Open-EO/openeo-python-client/master/openeo/extra/spectral_indices/spectral_indices.py [P, über Extraktor]
- USGS, Landsat Enhanced Vegetation Index: https://www.usgs.gov/landsat-missions/landsat-enhanced-vegetation-index [S, Seite gesperrt]
- NASA LP DAAC, HLS Vegetation Indices User Guide v2: https://lpdaac.usgs.gov/documents/2088/HLS_VI_User_Guide_V2.pdf [S]
- rio-tiler 9.4.6, `rio_tiler.colormap.cmap.list()` in der Sitzung [M]
- Gesperrt oder nicht auflösbar: `www.usgs.gov`, `www.ncbi.nlm.nih.gov`, `developers.google.com`, `open-eo.github.io`, `cogeotiff.github.io`.
- Intern: `adr/0020` §4, §6, §9, §10, §12; `adr/0014` §5.4, §15c; `plans/querschnitt/nm4-43-ausgabe-baender.md` §6.5; `plans/querschnitt/nm4-04-mosaik-mit-operator.md` §6; `plans/vp3/ui-01-app-rahmen.md` §4, §6.11; `projektuebersicht.md` §8; `KLAERUNGEN.md` B10, B13.

## 13. Freigabe (Otto, 30.10.2026, zu #251)

| Frage | Antwort |
|---|---|
| 1 Wo die Presets stehen | **1: R1.** Feld `index_presets` je Datensatz, Ausdruck in den Bandnamen des Datensatzes |
| 2 Indizes zuerst | **1:** NDVI, NDWI (McFeeters), NDSI, NBR, EVI |
| 3 Ort der Knöpfe | **1: O1.** Zeile „Index“ im Panel unter „Add step“ |
| 4 Darstellung | **1: D2.** Bereich und Colormap des Presets für jedes Band mit gleichem Ausdruck, in Vorschau und Ergebnis |
| 5 „NDVI cloud-free“ | **1: K1.** Knopf = nur `band_math`, Maske mit „＋ Mask“ dazu |
| 6 Schnitt | **abweichend:** Diese Session setzt das Backend jetzt um (NM4-14a, §14), ohne auf NM4-43e zu warten; NM4-43e läuft bereits (#250). Das Frontend ist NM4-14b in einer neuen Session nach dem Merge von NM4-43e PR 2 (§15) |

Die EVI-Quelle bleibt als Suchtreffer markiert (§7.5). Die Kleinentscheidungen KE1–KE8 aus §9 gelten. Die Fragen aus §11 sind damit beantwortet.

## 14. Umsetzung NM4-14a (Backend, 30.10.2026, in #251)

- **Registry** (`catalog/registry.py`): `IndexPreset` (`name`, `title`, `expression`, `rescale`, `colormap_name`, `formula`, `reference`) und das Pflichtfeld `DatasetConfig.index_presets`. `_check_index_presets` prüft die Form, wie §8.1 Stufe 1 sie beschreibt.
- **Daten** (`catalog/datasets.py`): Sentinel-2 hat die fünf Presets aus §7.5 mit den Vorgaben aus §8.5, der DEM `index_presets=()`. Am Feld stehen Herkunft (Awesome Spectral Indices, Commit `835fea7`, MIT; Montero et al. 2023) und Bandzuordnung (N = `nir`, B08).
- **Collection** (`catalog/collection.py`): `earthx:index_presets`, `rescale` als `[[low, high]]` wie bei `earthx:default_render`.
- **Start** (`processing/index_presets.py`): `check_index_presets(registry)` prüft `check_name` und `check_expression` von `band_math`, die Bänder aus dem Syntaxbaum noch einmal gegen den Eintrag (ein Netz unter der Textprüfung in `catalog`) und die Colormap gegen die Namen von rio-tiler. Python-Schlüsselwörter zählt `catalog` nicht als Bänder; `band_math` weist sie beim Start mit eigenem Grund ab. Aufgerufen wird es in `api.main.build_app` direkt nach `check_adapter_specs`. Fehler heißen `IndexPresetMismatch` (eine `ConfigError`), mit allen Problemen in einem Text.
- **Abweichung von §8.1:** Der `tiler` prüft nicht. Er baut seine App beim Import (`app = build_app()`), und sein Start soll `processing` nicht laden (`test_tiler_start_is_light`, M4-14); die Prüfung braucht `band_math`. Es reicht `api`: Es liefert die Collection aus, aus der das Panel die Presets liest, und startet mit einem kaputten Preset nicht.
- **Nachträge:** `architekturplan.md` 5.1 (Zeile `earthx:index_presets`), `adr/0014` „§15 Nachtrag NM4-14“.
- **Tests:**
  - `tests/catalog/test_index_presets.py`: Einträge, Collection, Fehleingaben der Form;
  - `tests/earthx/processing/test_index_presets.py`: Referenzwerte in Brüchen, Formel von Awesome Spectral Indices mit Konstanten und Zuordnung von `bands.json`, Bereich der Normalized Differences, Division durch 0, Prüfung beim Start und Bau von `api`;
  - `tests/earthx/api/test_index_presets_intake.py`: Preset gleich getipptem Ausdruck (Rezept und Hash), gelesene Assets.
- **Bestehende Tests**, die Sentinel-2 mit `band_math=False` nachbauen, setzen dazu `index_presets=()`, weil Presets `band_math` voraussetzen.

## 15. NM4-14b — Frontend: Index-Knöpfe im Panel (Aufgabe für eine neue Session)

**Stufe A**, nur Frontend, ein Draft-PR (Richtwert unter 400 Zeilen; sonst zwei: Knöpfe, dann Darstellung). **Modell:** Sonnet, Effort mittel.
**Start:** nach dem Merge von NM4-43e PR 2 (#250 und sein Folge-PR) und von NM4-14a (#251). Höchstens zwei Frontend-Sessions gleichzeitig; nicht gleichzeitig mit NM4-20, NM4-45 oder NM4-11b (alle ändern den Bandbereich des Panels).
**Startsatz:** „Führe Aufgabe NM4-14b aus `docs/plans/querschnitt/nm4-14-index-knoepfe.md` §15 aus.“

**Ausgangslage.**
- **Backend (§14):** Die Collection liefert `earthx:index_presets`, je Eintrag `name`, `title`, `expression`, `rescale` (`[[low, high]]`), `colormap_name`, `formula` und `reference`. Sentinel-2 hat NDVI, NDWI, NDSI, NBR und EVI, der DEM eine leere Liste. Ein älteres Backend liefert das Feld nicht; das gilt dann wie eine leere Liste.
- **Panel nach NM4-43e:** Name am Schritt (Vorgabe `Band_Math_<n>`), Namensregeln, das neue Ergebnis in der Ausgabe angehakt, „Show“ auf dem letzten Ergebnis, der Zerleger der Chips.
- **Entschieden:** §13 (O1, D2, K1) und `adr/0020` §12 (Name aus dem Preset, bei Kollision eine Zahl dazu).
- Texte nur auf Englisch, wenig Text, Erklärungen im Tooltip (UI-01 §4).

**Umfang.**

1. **Typ und Lesen:** `'earthx:index_presets'` in `types.ts`, gelesen und Eintrag für Eintrag geprüft wie `searchFilters.ts`. Ein Eintrag, der nicht passt, fällt mit einer Konsolenzeile ohne Daten weg.
2. **Zeile „Index“** unter „Add step“ (§8.7):
   - je Preset ein Knopf `＋ <name>`;
   - nur sichtbar, wenn der Datensatz Presets hat und `band_math` Version 2 in der Prozessbeschreibung steht, sonst ausgeblendet;
   - gesperrt mit demselben Grund wie „＋ Band math“ (Schritte voll, Operator nicht unterstützt);
   - Tooltip und `aria-label` nach KE2: `<title>: <formula>. Formula: Awesome Spectral Indices.`;
   - kein Text unter den Knöpfen.
3. **Klick:** Er ruft dasselbe `addStep('band_math', 2)` auf, mit `expression` aus dem Preset und `name` = `name` des Presets. Ist der Name in der Kette schon vergeben (ohne Rücksicht auf Groß-/Kleinschreibung), heißt der Schritt `NDVI_2`, `NDVI_3` usw. Es gibt keinen eigenen Zustand „Preset“, und danach ist der Schritt ein gewöhnlicher Schritt.
4. **Darstellung D2 (§8.5):**
   - Eine gemeinsame Funktion sucht zu (Datensatz, Ausdruck) das Preset; der Vergleich ist token-gleich über den Zerleger der Chips.
   - Reihenfolge in `resultRender` und in der Vorgabe der Vorschau: Ganzzahl → Bereich des Benutzers → Preset → Index-Regel → 2–98 %.
   - Gilt für die Vorschau („Show“ auf einem Band mit Preset-Ausdruck), für den Ergebnis-Layer (Ausdruck je Band aus den Eigenschaften des Ergebnisses bzw. dem Rezept des Jobs) und nach dem Laden aus Datei, Permalink oder Ablage.
   - `rdbu` kommt in `COLORMAPS` (`render.ts`).
5. **Tests** (`vitest`), Punkte 8–12 aus §10:
   - Klick ergibt denselben Auftrag (JSON) wie getippt;
   - DEM ohne Zeile; ohne `band_math` keine Zeile;
   - zweiter Klick `NDVI_2`, Ergebnis angehakt, „Show“ auf dem neuen Band, gesperrt bei vollen Schritten;
   - D2 mit anderen Leerzeichen, geändertem Ausdruck, eigenem Bereich und einem Ausdruck eines anderen Datensatzes;
   - Tooltips über `aria-label`;
   - Feld fehlt oder ist kaputt.

**Abnahme.**

- Gegenprobe: Die neuen Tests scheitern gegen den Code vor der Änderung.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster, mit nachgestellten Antworten; im PR beschrieben. **Bilder nicht ins Repo.**
- Prüfanleitung für Otto im PR: Browser (NDVI klicken, Vorschau −1…1 in `rdylgn`, Job, Ergebnis-Layer gleiche Farbskala) und PowerShell 5.1 (`GET /collections/sentinel-2-c1-l2a`, Feld `earthx:index_presets`).
- Alle vier Pflicht-Checks der CI grün.
- Nachtrag `adr/0014` „§15 Nachtrag NM4-14b“ (Knöpfe, Darstellung D2), Log-Zeile mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat). Vor „fertig“ ist `main` geholt.
- Grenzen: keine neue Abhängigkeit ohne Frage an Otto; keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs; `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.
