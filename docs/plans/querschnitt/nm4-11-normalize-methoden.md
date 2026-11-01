# NM4-11 — Normalize klarer und mit mehreren Methoden

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 11 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für Plan und Recherche, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach NM4-10 (Bandnamen); höchstens zwei Stufe-B-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-11 aus `docs/plans/querschnitt/nm4-11-normalize-methoden.md` aus.“

## 1. Anlass

`normalize` v1 kennt nur „linear von [a, b] nach [c, d]“; im Panel ist schwer zu verstehen, was der Schritt tut.

## 2. Soll

- **Klarer:** Das Panel zeigt kurz, was der Schritt tut, mit Beispiel (NDVI −1…1 → 0…1) und der Formel der gewählten Methode (im Tooltip). Felder mit verständlichen Namen.
- **Methoden (Vorschlag):** linear (wie heute), Z-Score, über Perzentile (etwa 2–98 %) auf einen Zielbereich mit Clip, eventuell robust (Median/Interquartilsabstand).

## 3. Im Plan klären (mit Optionen und Empfehlung)

- **Recherche mit Quellen (Pflicht):** Stand der Technik (GDAL/rio-tiler-Statistik, scikit-learn-Skalierer, Verfahren in der Fernerkundung).
- Z-Score und Perzentile brauchen Statistik über die ganze Eingabe: zwei Durchgänge oder Statistik vorab; Rechenzeit, Speicher (500 MB) und Bitgleichheit (zweimal, Cloud gegen Runner) müssen halten.
- Vorschau: keine Statistik je Kachel (Kacheln passten nicht zusammen). Optionen: Statistik einmal je Auftrag vorab (Route wie M4-19c), oder Vorschau nur für die lineare Methode.
- Stehen die Werte (Mittelwert, Perzentile) im Rezept, damit Rezept und Ergebnis eindeutig sind, oder entstehen sie im Lauf?
- Perzentile deterministisch wie M4-32 (festes Histogramm), Weg wiederverwenden. Je Band oder ein Bereich für alle Bänder.
- Neue `op_version` bzw. Parameter `method`; Kostenfaktor messen; Nachtrag `adr/0014`.

## 4. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests je Methode gegen eine unabhängige Rechnung; zweimal bitgleich; Runner gleich Kern; Speichertest unter 500 MB.
- Gegenprobe: Mit dem alten Code scheitern die neuen Tests.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n) mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat, siehe Kopf des Backlogs).
- Vor „fertig“ ist main geholt.

---

# Plan (30.10.2026)

Belegstufen wie in `adr/0009`: [M] gemessen, [P] am Primärdokument oder im Code gelesen, [S] Zusammenfassung oder Suchtreffer, [A] eigene Ableitung. Grundlage ist das Rezeptmodell aus `adr/0020` (Bandvorrat, `normalize.bands`, §4, §15a Auslegung 1). Gelesen auf `main` = `b87a9b2`.

**Zeitpunkt der Umsetzung.** Im Startsatz stand „Code erst nach NM4-43e“. Otto hat das am 30.10.2026 für das Backend aufgehoben (§13, Antwort 7): Das Backend (NM4-11a) wird jetzt umgesetzt, das Frontend (NM4-11b, §15) in einer neuen Session nach NM4-43e. Nachträge heißen nach der Aufgabe („§15 Nachtrag NM4-11“).

## 6. Kurzfassung

- **Jede vorgeschlagene Methode ist eine Gerade je Band** [A]: linear `(x − a) / (b − a) · (d − c) + c`; Perzentile dieselbe Gerade mit `a`, `b` = p_low, p_high; Z-Score `(x − mean) / stddev`; robust `(x − median) / (p75 − p25)`. Der Unterschied liegt nur darin, **woher die Zahlen kommen**. Der Kern bleibt der heutige: Grundrechenarten in getrennten numpy-Schritten, bitstabil (§15c, §15m).
- **Empfehlung (Frage 1, W1): Die Zahlen stehen im Rezept.** Das Panel misst sie vor dem Lauf über die bestehende Route `POST /collections/{dataset}/statistics` (NM4-19) für den Anfang der Kette bis vor den Schritt, über die AOI, mit dem festen Histogramm von M4-32. Im Rezept stehen Methode, gewählte Perzentile und die gemessenen Werte je Band. Damit bleiben Rezept und Ergebnis eindeutig, Kachel und Job bitgleich, Cloud und Runner bitgleich, Speicher und Laufzeit des Jobs wie heute, und die Vorschau zeigt jede Methode. Das ist die Linie von M4-18 F5 (Otto, 20.10.2026: „im Rezept stehen feste Zahlen“), nur dass das Panel jetzt misst statt vorschlägt.
- **Preis von W1:** Über 2048² Pixel misst die Route gröber (`exact: false`, NM4-19 G1); die Zahlen sind dann bis rund 3 % der Spanne neben dem exakten Perzentil (NM4-19 §7.6 [M]). Das Ergebnis bleibt trotzdem eindeutig und reproduzierbar; der Methodentext sagt es. Die Alternative W2 (Statistik im Lauf, zwei Durchgänge) ist immer exakt, kostet aber einen zweiten Lesedurchgang und bricht die Vorschau.
- **Methoden (Frage 2):** linear, Perzentile (0–100, 1–99, 2–98, 5–95 %), Z-Score, robust (Median, Interquartilsabstand). Robust kostet in W1 fast nichts dazu (gleiches Histogramm, gleicher Kern wie Z-Score).
- **Je Band** (Frage 3), wie scikit-learn, Earth Engine, QGIS und rio-tiler es tun; ein gemeinsamer Bereich ist eine spätere Option.
- **`normalize` Version 3** mit Feld `method` (Frage 4); Version 2 bleibt angenommen, nicht mehr gelistet. Keine neue Abhängigkeit.
- **Ohne AOI und nach `reproject`** misst die Route nicht (NM4-19 F6, KE6). Die statistischen Methoden sind dann gesperrt, mit Grund im Tooltip (Frage 5).
- **Schnitt (Frage 7):** zwei PRs nach NM4-43e: Backend (Operator, Perzentile der Route, Nachträge), dann Frontend (Panel, Messung, Texte).

## 7. Befunde

### 7.1 `normalize` heute [P]

- `processing/operators/normalize.py`: Version 1 (alle Bänder, ein Bereich) und Version 2 (NM4-43c, Feld `bands`, sonst gleich). Parameter `in_min`, `in_max`, `out_min`, `out_max`, `clip`, alle Pflicht (B10). Kern `_convert`: `subtract`, `divide`, `multiply`, `add`, optional `clip`, in `float64`, Ergebnis `float32` mit NaN. Faktor 0,3 (§15m), `{T1, T2}` in Version 1, Version 2 bis NM4-43d nur `T2`.
- Der Modulkopf hält fest: „no statistic of the scene or the AOI enters (F5), which is why the tile and the job give the same bytes. A panel may *suggest* the input range from a statistic; the recipe then holds plain numbers.“ Das ist Ottos Antwort F5 auf M4-18 (`plans/m4/m4-18-masking-normalisierung.md` §7, §8): Perzentile waren dort Option 2 „nur in T2 als eigene Art von Schritt mit zweitem Lesedurchgang“, nicht gewählt.
- Das Panel baut die Felder aus dem Schema (`frontend/src/schemaForm.ts`): nur flache Parameter, `oneOf` nur aus dokumentierten Konstanten. Ein Feld, das von einer Methode abhängt, kann das Formular nicht; `StepForm.tsx` hat dafür schon einen Sonderfall (`ClassPicker` für `mask`).

### 7.2 Was die Statistik schon kann [P]

- `processing/statistics.py` (M4-32): je Band Minimum, Maximum, Anzahl exakt; Mittelwert exakt und einmal gerundet; `stddev` wie GDAL (Welford je Block, Chan über die Blöcke, durch `count`, also Populations-Standardabweichung); Perzentile aus einem festen Histogramm (Ganzzahl bis 16 bit ein Fach je Wert, sonst 65 536 Fächer, relative Breite 2⁻⁷), nearest rank, untere Grenze unter 50 %, obere darüber, also nach außen gerundet. `_percentile(percent, …)` nimmt schon jedes ganzzahlige Prozent; ausgegeben werden heute nur 2 und 98 (`PERCENTILES`).
- `processing/core.py::area_statistics` und `api/area_statistics.py` (NM4-19): Die Route nimmt den Auftrag, wie das Panel ihn für den Job baut, und antwortet mit der `statistics` der AOI, die das Ergebnis tragen würde, Feld für Feld gleich bis 2048² Pixel; darüber gröber um ganzzahliges k (`exact: false`, `factor`). Grenzen: AOI Pflicht (ohne `422`, Otto F6), nur `pixel`-Schritte (`reproject` → `422`, KE6), höchstens 16 Dateien, 1 MB Body, 20 000 Positionen. Cache 7 Tage über SHA-256 des Rezepts, nie geloggt. Kalt 3,3–4,5 s für zwei Assets bei 2048² (NM4-19 §7.5 [M]).
- Die Route misst **nach** der Umwandlung in den Ausgabetyp des Auftrags (`_cast`). Für die Eingabe eines `normalize`-Schritts heißt das: Das Panel schickt den Anfang der Kette (Schritte vor dem Schritt) mit `output.bands` = `normalize.bands` und `dtype` `float64`; `float64` ist der Typ, in dem der Kern zwischen den Schritten rechnet (`_INTERMEDIATE_DTYPE`, Kern `_convert` in `float64`), die Umwandlung ändert also nichts [A].

### 7.3 Stand der Technik [P] [S]

Abgerufen am 30.10.2026 über `raw.githubusercontent.com` (Quelltext der Doku bzw. Code, Stand `master`/`main`); die gerenderten Seiten von `gdal.org`, `developers.google.com` und `pro.arcgis.com` sind aus der Sitzung nicht erreichbar, dort nur Suchtreffer [S]. Die Lesung [P] lief über das Abrufwerkzeug der Sitzung, nicht Zeile für Zeile.

| Methode | GDAL | rio-tiler / TiTiler | scikit-learn | openEO | Earth Engine | QGIS |
|---|---|---|---|---|---|---|
| linear | `gdal raster scale` (ab 3.11) begrenzt ohne `--no-clip` auf den Eingabebereich; `gdal_translate -scale` begrenzt nur mit `-exponent` [P] | `linear_rescale` begrenzt auf `in_range`, dann linear: die heutige Formel mit `clip` [P] | `MinMaxScaler`, `clip=False` [P] | `linear_scale_range` begrenzt auf `[inputMin, inputMax]` [P] | `unitScale` ohne Begrenzung [S] | „Stretch to MinMax“ [P] |
| Perzentile | kein Befehl; `gdalinfo --stats`/`--hist` ohne Perzentile [P] | Statistik mit `percentiles` [2, 98] (Vorgabe), dann `rescale` vom Client [P] | — (`QuantileTransformer` hat ein anderes Ziel und zieht eine Zufallsstichprobe) [P] | `quantiles` (Hyndman-Fan Typ 7), dann `linear_scale_range` [P] | `Reducer.percentile`, große Mengen aus einem Histogramm (`maxBuckets`, `maxRaw`) [P] | „Cumulative count cut“, Vorgabe 2–98 %, aus einem Histogramm [P] |
| Z-Score | — | `mean`, `std` (÷ N) [P] | `StandardScaler`, ÷ N; Varianz 0 → Teiler 1 [P] | kein Prozess gefunden | `mean`, `stdDev`, Rest selbst [S] | „Mean ± n · σ“, n = 2,0; σ mit ÷ (N − 1) [P] |
| robust | — | — | `RobustScaler`, `quantile_range` (25, 75), Median; `unit_variance` optional [P] | über `quantiles` | über `Reducer.percentile` | — |

- **Zwei Schritte sind üblich:** erst die Statistik über das Gebiet, dann die Gerade als reiner Pixel-Schritt mit festen Zahlen. So TiTiler (`/statistics`, dann `rescale`), openEO (`quantiles`, dann `linear_scale_range`), Earth Engine (`reduceRegion`, dann `unitScale`) und Sentinel Hub (Statistical API, dann feste Zahlen im Evalscript [S]). Eine Kachel trägt keine Statistik des Gebiets. Das stützt W1 [A].
- **Histogramm statt Sortieren** für große Mengen: GDAL (`GetHistogram`, 256 Fächer), QGIS (Perzentile aus dem Histogramm, Ganzzahlen nach außen gerundet), Earth Engine. Unser festes Histogramm (M4-32) ist von dieser Art und dazu bitgleich über Rechner.
- **Standardabweichung:** GDAL, rio-tiler und scikit-learn teilen durch N wie `processing/statistics.py`; QGIS durch N − 1. Der Plan bleibt bei N; der Methodentext sagt „population standard deviation“.
- **Konstantes Band:** scikit-learn setzt den Teiler bei Spanne 0 auf 1 (`StandardScaler`, `MinMaxScaler`), statt abzulehnen. Übernommen in KE10.
- **Je Band oder gemeinsam:** Alle Werkzeuge rechnen die Statistik je Band. Ein Praxistext zu Sentinel-2-Echtfarbe rät für RGB zu gemeinsamen Grenzen, weil sich je Band die Farbbalance verschiebt [S]; eine zweite Quelle fehlt. Das spricht für Option 2 von Frage 3 als spätere Ergänzung für Komposite, nicht für Analysebänder.
- **ArcGIS** (Percent Clip, Standard Deviation) ist nur über Suchtreffer belegt, die Vorgaben nicht; daher nicht als Bezug genommen.

### 7.4 Jede Methode als Gerade [A]

| Methode | Formel je Band | Zahlen | Wertebereich danach |
|---|---|---|---|
| linear (heute) | `(x − in_min) / (in_max − in_min) · (out_max − out_min) + out_min`, optional begrenzt | vom Benutzer | Zielbereich (mit `clip`) |
| Perzentile | dieselbe Gerade mit `in_min` = p_low, `in_max` = p_high, optional begrenzt | gemessen | Zielbereich (mit `clip`) |
| Z-Score | `(x − mean) / stddev` | gemessen | offen, Mittel 0, Streuung 1 über die AOI |
| robust | `(x − median) / (p75 − p25)` | gemessen | offen, Median 0 |

- 0–100 % ist „Minimum–Maximum der AOI“; ein eigener Eintrag „min–max“ entfällt damit.
- Z-Score und robust teilen einen Kern (`subtract`, `divide`); Perzentile teilen den Kern von linear. Es kommen keine Rechenarten dazu, die vom Prozessor abhängen; die Bitstabilität von §15c gilt weiter, ein Test unter A und D von `adr/0016` §3.3 hält sie fest.
- Ist die Spanne 0 (`stddev` = 0, `p75 = p25`, `p_low = p_high`: ein konstantes Band in der AOI), teilt der Kern durch 1, wie scikit-learn (KE10). Ein Band ohne gültigen Wert in der AOI hat keine Zahl; der Schritt nennt den Grund, „Start“ ist gesperrt.

## 8. Optionen und Empfehlung

### 8.1 Woher die Werte kommen (Frage 1)

| | W1 vorab gemessen, im Rezept | W2 im Lauf gemessen | W3 die Annahme misst |
|---|---|---|---|
| Ablauf | Panel ruft die Route für den Anfang der Kette, schreibt Werte ins Rezept | Kern liest die Eingabe des Schritts zweimal: erst zählen, dann anwenden | `api` ruft beim Annehmen dieselbe Messung und schreibt die Werte ins Rezept |
| Rezept und Ergebnis eindeutig | ✓ Werte im Rezept, Hash darüber | ✓ deterministisch, aber die Werte stehen erst im Ergebnis (Eigenschaften, Methodentext) | ✓ wie W1 |
| bitgleich zweimal, Cloud gegen Runner | ✓ Kern wie heute | ✓ mit festem Histogramm und fester Blockfolge | ✓ wie W1 |
| Vorschau | ✓ jede Methode, Kachel rechnet die Gerade (`T1`) | ✗ je Kachel keine Statistik; nur über die Route vorab, also W1 für die Vorschau und W2 für den Job, gleich nur bis 2048² | ✓ wie W1, wenn das Panel vorher misst |
| Rechenzeit Job | wie heute (Faktor wie linear) | zweiter Lesedurchgang der Quellen (Lesen ist der größte Teil eines Laufs, §15m: Kerne 7–29 ms je Block, ganzer Lauf 146 ms je Mi Pixel) oder Zwischendatei `float64` des Vorrats (9,5 Mi Pixel, 17 Bänder: 1,3 GB Platte) [A] | wie heute; die Annahme wird um die Messung langsamer (Sekunden, synchron) |
| Speicher (500 MB) | unverändert | Histogramm 512 KB je Band; sonst wie heute [A] | unverändert |
| große AOI | über 2048² gröber gemessen, bis ~3 % der Spanne (NM4-19 §7.6 [M]); im Methodentext genannt | immer exakt | wie W1 |
| Runner | rechnet die Zahlen des Rezepts, misst nichts (B9 unberührt) | misst selbst, gleich dem Job | wie W1 |
| Aufwand | Route: weitere Perzentile; Operator; Panel misst | neue Art Segment im Planer, Zwischendatei oder Doppel-Lesen, Schätzung, Kachel-Ausnahme | wie W1 und Messung in der Annahme, Zeitgrenze |

**Empfehlung W1.** Sie hält alles, was Abnahme und Grenzen verlangen (bitgleich, Runner gleich Kern, 500 MB, Vorschau), ohne neuen Kernpfad, und folgt M4-18 F5. Die Grenze der exakten Messung ist dieselbe, die Otto für die Farbskala angenommen hat (NM4-19 F2). W3 verschiebt nur die Messung vom Panel in die Annahme und macht `POST` langsam; der Benutzer sähe die Zahlen erst im Ergebnis.

**Ehrlichkeit des Rezepts.** `api` kann nicht prüfen, ob die Zahlen wirklich die Perzentile der AOI sind (das hieße messen, also W3). Ein Rezept von Hand mit falschen Zahlen rechnet trotzdem eindeutig; der Methodentext nennt die Zahlen und sagt „as measured before the run“. Das Panel übernimmt Zahlen nie aus einer geladenen `recipe.json` oder einem Permalink, sondern misst neu für die aktuelle Auswahl (KE3).

### 8.2 Methoden (Frage 2)

1. **linear, Perzentile, Z-Score, robust** **(Empfehlung)**. Robust braucht nur p25, Median, p75 aus demselben Histogramm und den Kern des Z-Scores.
2. linear, Perzentile, Z-Score; robust später.
3. linear und Perzentile; Z-Score und robust später.

Perzentile als feste Paare 0–100, 1–99, 2–98 (Vorgabe im Panel, wie QGIS), 5–95 %, im Rezept `low` ∈ {0, 1, 2, 5} und `high` ∈ {95, 98, 99, 100} (KE1). Ein freies Prozent bringt wenig und vergrößert die Antwort der Route und den Cache.

### 8.3 Je Band oder ein Bereich (Frage 3)

1. **Je Band** eigene Werte **(Empfehlung)**. So rechnen scikit-learn (je Merkmal), Earth Engine (`reduceRegion` je Band), QGIS und rio-tiler (Statistik je Band). Bänder verschiedener Herkunft (NDVI neben B08) bekommen jedes seinen Bereich.
2. Ein Bereich für alle genannten Bänder aus dem gemeinsamen Histogramm. Erhält das Verhältnis der Bänder (Farbbalance eines RGB), braucht aber ein vereinigtes Histogramm in der Route und denselben Typ in allen Bändern.
3. Beides, mit einem Schalter.

Ein Bereich für alle bleibt für linear wie heute (`in_min` … gelten für alle genannten Bänder).

### 8.4 Parameter und Version (Frage 4)

**Empfehlung:** `normalize` `op_version` 3, Parameter mit `method` als Unterscheidung (Pydantic, diskriminierte Union), alles Pflicht (B10):

```json
{"op": "normalize", "op_version": 3, "params": {
  "method": "percentile", "bands": ["NDVI"], "low": 2, "high": 98,
  "out_min": 0, "out_max": 1, "clip": true,
  "measured": {"factor": 1, "bands": {"NDVI": {"low": -0.12, "high": 0.83}}}}}

{"op": "normalize", "op_version": 3, "params": {
  "method": "zscore", "bands": ["B04", "B08"],
  "measured": {"factor": 3, "bands": {"B04": {"mean": 0.081, "stddev": 0.034}, "B08": {"mean": 0.27, "stddev": 0.06}}}}}

{"op": "normalize", "op_version": 3, "params": {
  "method": "robust", "bands": ["NDVI"],
  "measured": {"factor": 1, "bands": {"NDVI": {"p25": 0.21, "median": 0.44, "p75": 0.61}}}}}

{"op": "normalize", "op_version": 3, "params": {
  "method": "linear", "bands": ["NDVI"], "in_min": -1, "in_max": 1, "out_min": 0, "out_max": 1, "clip": true}}
```

(Zahlen erfunden, nur zur Form.)

- `measured.bands` nennt genau die Bänder von `bands`, je mit den Werten der Methode (endlich; `low ≤ high`, `stddev ≥ 0`, `p25 ≤ median ≤ p75`); `factor` ist das k der Route (1 = exakt), damit der Methodentext ehrlich ist.
- Das Streichen des Planers (`restrict`) nimmt mit einem Band auch seinen Eintrag aus `measured.bands`.
- Version 2 bleibt registriert und angenommen (Rezepte ab NM4-43e), wird nicht mehr gelistet (wie `reproject` 3 neben 4). Das Panel liest einen Schritt Version 2 aus einer `recipe.json` als Version 3 `linear` mit denselben Zahlen; der Kern ist derselbe, die Werte sind bitgleich (KE4). Die Python-Umdeutung von Version 1 (`processing/upgrade.py`) bleibt, wie sie ist.
- `earthx.__version__` bleibt: Kein bestehendes Rezept ändert seine Bytes (KE5).

Alternativen:
2. Eigene Operatoren je Methode (`normalize` linear, dazu `stretch`, `standardize`): jedes Schema flach, das Formular aus dem Schema reicht; aber mehr Knöpfe unter „Add step“ und gegen „ein Schritt mit Methoden“ im Soll (§2).
3. Version 2 um `method` erweitern statt Version 3: geht nicht, sobald NM4-43e Rezepte der Version 2 schreibt; ein `op_version` ändert seine Form nicht (`adr/0014` §4).

### 8.5 Die Messung (Route NM4-19)

- **Was das Panel schickt:** den Auftrag des Jobs (bei mehreren Aufträgen: Frage 6) mit den Schritten **vor** dem `normalize`-Schritt, `output.bands` = `bands` des Schritts, `dtype` `float64` (§7.2). Zwei `normalize`-Schritte in einer Kette: Der zweite misst den Anfang einschließlich des ersten mit dessen Zahlen; deshalb misst das Panel der Reihe nach.
- **Was die Route dazu braucht:** weitere Perzentile. Vorschlag: Die Antwort trägt je Band zusätzlich `percentile_1`, `_5`, `_25`, `_50`, `_75`, `_95`, `_99` (neben 2 und 98), aus demselben Histogramm, Präfix des Cache-Schlüssels `area-statistics/v2`. Ergebnisdokument und `result.tif` bleiben bei 2 und 98 (keine Byteänderung). Für p50 gilt die untere Grenze des Fachs (heutige Regel „unter oder gleich 50 → unten“); bei Ganzzahlen bis 16 bit ist jedes Perzentil exakt.
- **Kosten:** eine Messung je `normalize`-Schritt mit statistischer Methode, kalt 3–5 s bis 2048², mit Cache eine Datenbankabfrage. Die Wartezeit der Vorschau (`MEASURE_WAIT_MS`, 5 s) gilt nicht: Ohne Zahlen gibt es kein Rezept, „Review“ und „Start“ warten, mit Grund im Tooltip (KE2).

### 8.6 Ohne AOI und nach `reproject` (Frage 5)

1. **Statistische Methoden gesperrt**, Grund im Tooltip: ohne AOI „Draw an AOI; the values are measured over it“, nach einem `reproject` „Move Normalize above Reproject; values are measured before a reprojection“. Linear geht immer. **(Empfehlung)** Die Route bleibt, wie Otto sie freigegeben hat (F6, KE6).
2. Die Route misst auch ohne AOI (ganze Szenen, immer gröber, k ≈ 6 für eine Sentinel-2-Szene) und vor `reproject` (den Anfang ohne den Warp; die Werte weichen dann leicht ab, der Methodentext sagt es).

### 8.7 Mehrere Aufträge (Frage 6)

„One job per pass“ bzw. „per scene“ sind bis zu 25 Aufträge (`MAX_BATCH_JOBS`).

1. **Jeder Auftrag misst für sich** beim Schätzen („Review“), parallel wie die Schätzungen (`ESTIMATE_PARALLEL` 4); jedes Rezept trägt die Werte seiner Fläche. Kalt bis rund 25 s für 25 Aufträge [A]. **(Empfehlung)** Nur so stimmt „Z-Score über die Eingabe“ für jeden Job.
2. Alle Aufträge bekommen die Werte des ersten (wie die Vorschau, NM4-19 F5): eine Messung, Ergebnisse vergleichbar, aber für die anderen Szenen nicht die eigene Statistik; der Methodentext müsste das sagen.
3. Statistische Methoden nur bei „One job“.

### 8.8 Panel (nach NM4-43e, Texte englisch, UI-01 §4)

```
1. Normalize                                    ↑ ↓ ✕
   Rescale values, e.g. NDVI −1…1 → 0…1.  ⓘ
   Method   [ Percentile stretch ▾ ]            ← Tooltip: Formel der Methode
   Bands    (NDVI ✕) (+)                         ← Chips aus NM4-43e
   Range    [ 2–98 % ▾ ]   To [ 0 ] … [ 1 ]   ☑ Clip
   Measured over the AOI ✓                      ← Tooltip: Werte je Band; „coarser read“ bei factor > 1
```

- Methoden im Dropdown mit je einer Zeile Hilfe (wie M4-24): „Fixed range“, „Percentile stretch“, „Z-score“, „Robust (median, IQR)“.
- Formeln im Tooltip, z. B. Z-score: „(x − mean) / standard deviation, measured over the AOI“; Percentile stretch: „(x − p2) / (p98 − p2) × (to max − to min) + to min“.
- Feldnamen statt `in_min` …: „From“ … „To“ für linear, „Range“ für Perzentile; die Namen im Rezept bleiben (`in_min`, …), damit Version 2 und 3 linear dieselben Parameter tragen.
- Messung: automatisch, sobald die Methode gewählt ist und sich der Anfang der Kette, die AOI, die Szenen oder `bands` ändern (Schlüssel wie NM4-19b nur im Speicher). Während der Messung „Measuring…“ am Schritt.

### 8.9 Schnitt (Frage 7)

Schätzung [A]: Backend ~200 Zeilen Code, ~350 Tests (Operator Version 3, Perzentile der Route, Prozessbeschreibung, Methodentext, Nachträge); Frontend ~250 Code, ~300 Tests (Formular, Messung, Batch, Umdeutung Version 2, Texte).

1. **Zwei PRs nach NM4-43e in dieser Session, gestapelt:** NM4-11a Backend, NM4-11b Frontend. **(Empfehlung)**
2. NM4-11a in dieser Session, NM4-11b nach dem Merge in neuer Session (wie NM4-19).
3. Ein PR (~1100 Zeilen).

## 9. Kleinentscheidungen

Gelten, sofern du nicht widersprichst:

- **KE1 Perzentile:** Paare 0–100, 1–99, 2–98, 5–95 %; Vorgabe im Panel 2–98 % (wie QGIS und die Farbskala von M4-32). Im Rezept `low` und `high` als dokumentierte Konstanten.
- **KE2 Warten auf die Messung:** „Review“ und „Start“ gesperrt, solange eine Messung fehlt, läuft oder scheiterte; Grund im Tooltip („Normalize: measuring the bands…“, „Normalize: the measurement failed: <Grund der Route>“). Kein Text im Panel außer am Schritt.
- **KE3 Gemessene Werte sind abgeleitet:** Das Panel zeigt sie nur (Tooltip), der Benutzer tippt sie nicht. Wer feste Zahlen will, nimmt „Fixed range“; der Tooltip der Messung bietet dafür nichts an (kein zweiter Weg). Beim Laden einer `recipe.json`, eines Permalinks oder eines Eltern-Rezepts (NM4-05b) misst das Panel neu; ein Permalink derselben Auswahl trifft den Cache und bekommt dieselben Zahlen.
- **KE4 Version 2 in alten Dateien:** wird im Panel zu Version 3 `linear` (bitgleich); `api` nimmt Version 2 weiter an.
- **KE5 Versionen:** `normalize` Version 3 gelistet, Version 2 nicht mehr; `earthx.__version__` bleibt; `recipe_version` bleibt 2.
- **KE6 Kachel:** Version 3 ist `T1` und `T2` (die Kachel rechnet die Gerade mit den Zahlen des Rezepts; NM4-43d liefert den Bandvorrat in der Kachel).
- **KE7 Faktor:** je Methode auf einem Block 1024² gemessen wie §15m (kleinster Wert aus 15 Läufen) und mit dem Zuschlag des Statistik-Durchgangs (+12,1 %) aufgerundet; erwartet 0,3 für alle vier, weil der Kern derselbe ist [A]. Die Messung im Panel kostet den Job nichts.
- **KE8 Methodentext** (NM4-08), z. B.: „The band NDVI was stretched from its 2nd to 98th percentile over the AOI (−0.12 to 0.83, as measured before the run) onto 0 to 1, values outside limited to the target range, in 32-bit floating point.“ Bei `factor` > 1 dazu „measured on a read 3 times coarser than the result“. Z-Score: „… standardized with its mean and standard deviation over the AOI (mean …, standard deviation …), (x − mean) / standard deviation …“.
- **KE9 Log:** nichts Neues; die Route loggt wie bisher eine Zeile ohne AOI, Item-ID und Schlüssel. Gemessene Werte stehen in keinem Log.
- **KE10 Spanne 0:** Teiler 1 wie scikit-learn (`StandardScaler`, `MinMaxScaler`): Z-Score und robust geben dann `x − mean` bzw. `x − median`, Perzentile `out_min` plus den Abstand zu p_low; ein Test hält es fest. Der Methodentext nennt es („constant over the AOI“).

## 10. Tests (Abnahme)

Backend (`pytest`, synthetische Raster wie `processing/test_core_statistics.py`):

1. **Je Methode gegen eine unabhängige Rechnung:** linear, Perzentile, Z-Score, robust je auf einem kleinen Array gegen eine Rechnung in Python (`fractions.Fraction` bzw. `float64` von Hand), Ergebnis `float32` gleich; Maske und NaN bleiben; Bänder außerhalb von `bands` unverändert (Typ und Werte).
2. **Messung gegen unabhängige Rechnung:** Route mit `uint16`-Band (Perzentile exakt) gegen `numpy.percentile(method="inverted_cdf")` auf denselben Pixeln der AOI; `float32`-Band innerhalb eines Fachs (2⁻⁷ relativ) und nach außen gerundet; `mean` exakt, `stddev` gegen `numpy.std(ddof=0)`.
3. **Ende zu Ende:** Auftrag mit den gemessenen Zahlen als Job: Statistik des Ergebnisses passt zur Methode (Perzentile: p_low → `out_min`, p_high → `out_max` bis auf ein Fach; Z-Score: Mittel ~0, Streuung ~1 über die AOI).
4. **Bitgleich:** derselbe Auftrag zweimal → gleiche SHA-256 von `result.tif`; Einstellungen A und D von `adr/0016` §3.3; Runner gegen Kern (`runner/test_compare.py`) je Methode; Kachel gegen Job auf der nativen Ebene (COG).
5. **Speicher:** `test_memory_mask_normalize.py` um Version 3 (Z-Score, vier Bänder, 4096²) unter 500 MB.
6. **Fehleingaben (`422`):** unbekannte Methode; Felder einer anderen Methode (`extra="forbid"`); `measured.bands` ohne ein Band von `bands` oder mit einem fremden; `stddev` negativ, NaN, ∞; `low > high`; `p25 > median`; `low` 3 (kein erlaubtes Paar); `factor` 0; leere `bands`; Groß-/Kleinschreibung doppelt. Version 2 weiter angenommen und bitgleich zu Version 3 `linear`.
7. **Streichen:** Ein gestrichenes Band verlässt `bands` und `measured.bands`; mit und ohne Streichen bitgleich (`adr/0020` §4).
8. **Zweckfremd:** Route mit `normalize` statistisch im Anfang der Kette ohne Zahlen → `422`; Methode auf einer Maskenschicht (`scl`) geht (Zahlen), ist aber kein Sonderfall; Auftrag mit 17 Dateien → `413` wie bisher.
9. **Gegenprobe:** Tests 1–8 laufen gegen den Code vor der Änderung und scheitern (Version 3 unbekannt, Perzentile fehlen in der Antwort); Ergebnis im PR.

Frontend (`vitest`, NM4-11b):

10. Formular je Methode; Messung mit dem Anfang der Kette und `float64` (gebauter Body im Test); Sperre und Tooltip von „Review“/„Start“; neu messen bei AOI, Szenen, Bändern, vorigen Schritten; keine AOI in einer URL; Batch je Auftrag; Version 2 aus `recipe.json` als Version 3 `linear`.
11. Prüfung im echten Browser (Chromium/Playwright der Sitzung) mit nachgestellten Antworten, hell und dunkel, schmales Fenster; im PR beschrieben, Bilder nicht ins Repo.
12. Prüfanleitung für Otto im PR (Browser und PowerShell 5.1: Route mit Perzentilen, Job je Methode, Methodentext).

## 11. Fragen an Otto

Kurz beantwortbar: je Frage eine Nummer.

**Frage 1 — Woher die Werte kommen**
1. Vorab gemessen über die Route von NM4-19, Werte im Rezept (W1). **(Empfehlung)**
2. Im Lauf gemessen, zweiter Durchgang (W2); Vorschau nur für linear.
3. Die Annahme misst und schreibt die Werte ins Rezept (W3).

**Frage 2 — Methoden**
1. Linear, Perzentile, Z-Score, robust. **(Empfehlung)**
2. Ohne robust.
3. Nur linear und Perzentile.

**Frage 3 — Je Band oder ein Bereich**
1. Je Band. **(Empfehlung)**
2. Ein Bereich für alle genannten Bänder.
3. Beides mit Schalter.

**Frage 4 — Form im Rezept**
1. `normalize` Version 3 mit `method` und `measured` (§8.4). **(Empfehlung)**
2. Eigene Operatoren je Methode.

**Frage 5 — Ohne AOI und nach `reproject`**
1. Statistische Methoden dort gesperrt, Grund im Tooltip; Route unverändert. **(Empfehlung)**
2. Route misst auch ganze Szenen und den Anfang vor `reproject`.

**Frage 6 — Mehrere Aufträge**
1. Jeder Auftrag misst für sich. **(Empfehlung)**
2. Alle nehmen die Werte des ersten.
3. Statistische Methoden nur bei „One job“.

**Frage 7 — Schnitt**
1. Zwei PRs nach NM4-43e in dieser Session, gestapelt. **(Empfehlung)**
2. Backend in dieser Session, Frontend in neuer Session nach dem Merge.
3. Ein PR.

## 12. Quellen

- GDAL `gdal raster scale`: https://raw.githubusercontent.com/OSGeo/gdal/master/doc/source/programs/gdal_raster_scale.rst [P]
- GDAL `gdal_translate`: https://raw.githubusercontent.com/OSGeo/gdal/master/doc/source/programs/gdal_translate.rst [P]
- GDAL `gdal raster info`: https://raw.githubusercontent.com/OSGeo/gdal/master/doc/source/programs/gdal_raster_info.rst [P]
- GDAL `gdal raster`: https://raw.githubusercontent.com/OSGeo/gdal/master/doc/source/programs/gdal_raster.rst [P]
- GDAL VRT (`ScaleRatio`, `LUT`): https://raw.githubusercontent.com/OSGeo/gdal/master/doc/source/drivers/raster/vrt.rst [P]
- GDAL `ComputeStatistics`, `GetHistogram`, `GetDefaultHistogram`: https://raw.githubusercontent.com/OSGeo/gdal/master/gcore/gdalrasterband.cpp [P]
- rio-tiler `get_array_statistics`, `linear_rescale`: https://raw.githubusercontent.com/cogeotiff/rio-tiler/main/rio_tiler/utils.py [P]
- rio-tiler `ImageData.statistics`, `rescale`: https://raw.githubusercontent.com/cogeotiff/rio-tiler/main/rio_tiler/models.py [P]
- TiTiler `rescale`, `percentiles`: https://raw.githubusercontent.com/developmentseed/titiler/main/src/titiler/core/titiler/core/dependencies.py [P]
- scikit-learn Skalierer: https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/sklearn/preprocessing/_data.py [P]
- openEO `linear_scale_range`: https://raw.githubusercontent.com/Open-EO/openeo-processes/master/linear_scale_range.json [P]
- openEO `quantiles`: https://raw.githubusercontent.com/Open-EO/openeo-processes/master/quantiles.json [P]
- Earth Engine `Reducer.percentile`: https://raw.githubusercontent.com/google/earthengine-api/master/python/ee/reducer.py [P]
- Earth Engine `unitScale`: https://developers.google.com/earth-engine/apidocs/ee-image-unitscale [S]
- QGIS Vorgaben (`CUMULATIVE_CUT_LOWER/UPPER`, `DEFAULT_STDDEV_FACTOR`): https://raw.githubusercontent.com/qgis/QGIS/master/src/core/raster/qgsrasterminmaxorigin.h [P]
- QGIS `cumulativeCut`: https://raw.githubusercontent.com/qgis/QGIS/master/src/core/raster/qgsrasterinterface.cpp [P]
- QGIS Handbuch, Raster-Eigenschaften: https://raw.githubusercontent.com/qgis/QGIS-Documentation/master/docs/user_manual/working_with_raster/raster_properties.rst [P]
- Sentinel Hub Statistical API: https://docs.sentinel-hub.com/api/latest/api/statistical [S]
- ArcGIS Pro Stretch: https://pro.arcgis.com/en/pro-app/latest/help/analysis/raster-functions/stretch-function.htm [S]
- Sentinel-2-Stretch je Band gegen gemeinsam: https://mdsumner.github.io/gdal-r-python/sentinel2_stretch.html [S]
- Intern: `plans/m4/m4-18-masking-normalisierung.md` §3.3, §7 F4/F5, §8; `plans/m4/m4-32-ergebnis-statistik.md`; `plans/querschnitt/nm4-19-auto-stretch-ueber-aoi.md` §7, §8, §14; `adr/0014` §15c, §15k, §15m, §15u; `adr/0020` §4, §10, §11, §15a.

## 13. Freigabe (Otto, 30.10.2026, zu #244)

| Frage | Antwort |
|---|---|
| 1 Woher die Werte kommen | **1: W1.** Vorab über die Route von NM4-19 gemessen, die Werte stehen im Rezept |
| 2 Methoden | **alle vier** (linear, Perzentile, Z-Score, robust) |
| 3 Je Band oder ein Bereich | **je Band** |
| 4 Form im Rezept | **`normalize` Version 3 mit `method`** |
| 5 Ohne AOI und nach `reproject` | **Option 1:** statistische Methoden gesperrt, Grund im Tooltip; linear immer möglich |
| 6 Mehrere Aufträge | **Option 1:** jeder Auftrag misst für sich. **Wiedervorlage:** Option 2 „gleiche Werte für alle Aufträge“ (Vergleichbarkeit von Zeitreihen), siehe §14 |
| 7 Schnitt | **abweichend:** diese Session setzt das Backend um (NM4-11a), ohne auf NM4-43e zu warten; das Frontend ist NM4-11b in einer neuen Session nach NM4-43e (§15) |

Die Kleinentscheidungen KE1–KE10 aus §9 gelten. Die Fragen aus §11 sind damit beantwortet.

## 14. Umsetzung NM4-11a (Backend, 30.10.2026)

Draft-PR [#244](https://github.com/oscipal/earthX/pull/244) trägt Plan und Backend.

**Abweichungen und Auslegungen von Claude** (gelten, bis Otto widerspricht):

1. **Namen im Rezept.** §8.4 nannte die gemessenen Werte des Perzentil-Stretchs `low` und `high`, dieselben Namen wie die Prozente. Das ist missverständlich. Im Rezept heißen die Prozente `low` und `high`, die gemessenen Werte je Band `p_low` und `p_high` (`measured.bands.<Band>.p_low`).
2. **Ein flaches Modell statt einer Union.** `NormalizeParamsV3` ist ein Modell mit `method` und den Feldern aller Methoden; die Felder einer anderen Methode sind verboten und die der eigenen Pflicht (`422`/`400` mit dem Feld im Text). Grund: Der Operator verlangt ein strenges Modell mit `extra="forbid"`, das eine Union an der Wurzel nicht sein kann; so bleibt das Schema flach für das Formular.
3. **Spanne 0.** Eine konstante Spanne (`stddev` = 0, `p25` = `p75`, `p_low` = `p_high`) ist gültig und teilt durch 1 (KE10). Gesperrt ist nur ein Band ohne gültigen Wert, und das ist Sache des Panels (keine Zahl, keine Messung).
4. **Nicht gelistet.** `normalize` Version 3 ist `listed=False`, bis das Panel sie schickt (NM4-11b); die Prozessbeschreibung listet weiter, was sie vor dieser Aufgabe listete. Ein Test hält fest, dass sie sie nach dem Umschalten bietet.
5. **Kachel.** Version 3 läuft als Kachel (`T1`) und als Job. Die URL trägt die Zahlen in `params`; die Grenze von 2048 Zeichen (`MAX_OPERATOR_PARAMS_CHARS`) gilt, das sind je nach Methode etwa 25 bis 40 Bänder mit Zahlen. Darüber antwortet die Kachel `400` mit dem Grund, und das Panel zeigt den Anfang der Kette bis vor den Schritt (wie bei jedem nicht zeichenbaren Schritt, `adr/0014` §15m).
6. **Route.** `POST /collections/{dataset}/statistics` liefert je Band zusätzlich `percentile_1`, `_5`, `_25`, `_50`, `_75`, `_95`, `_99`; das Ergebnisdokument und `result.tif` tragen weiter nur 2 und 98 (keine geänderten Bytes, `__version__` bleibt). Der Cache-Schlüssel trägt `area-statistics/v2`; Einträge der älteren Form werden nicht mehr getroffen und laufen nach 7 Tagen ab.
7. **Methodentext und Herkunft.** Der Text nennt die Zahlen der Rezeptes (`as measured before the run`, bei `factor` > 1 `on a read N times coarser than the result`). Er nennt wie bei Version 2 alle Bänder des Schritts, auch die der Planer streicht.

**Abnahme NM4-11a.**

- **Je Methode gegen eine unabhängige Rechnung** (`test_normalize_methods.py`): der Kern gegen Python-`float` und exakte Brüche; die Perzentile der Route gegen `numpy.percentile(method="inverted_cdf")` (16 Bit exakt, `float32` innerhalb eines Fachs); ein Lauf mit den gemessenen Zahlen tut, was die Methode sagt.
- **Bitgleich:** zweimal derselbe Lauf; Einstellungen A und D von `adr/0016` §3.3; Kachel gegen Job auf der nativen Ebene (`test_tiler_normalize_methods.py`, 256 und 512 px, jede Methode und nach `mask`); Runner gegen Job-Kind (`runner/test_compare.py`, jede Methode, mit Gegenprobe); Version 1, 2 und 3 `linear` bitgleich.
- **Speicher** unter 500 MB (bei 4096² 356 bis 372 MB, Wachstum höchstens 81 MB von 2048² auf 4096²); Kernzeit nicht über der des festen Bereichs, Faktor 0,3 bleibt (`scripts/nm4-11-normalize/measure_kernel.py`, `adr/0014` Nachtrag NM4-11).
- **Fehlerfälle und zweckfremde Nutzung:** unbekannte Methode, Felder einer anderen Methode, fehlende, fremde oder doppelte Bänder in `measured`, negative Streuung, Quartile in falscher Ordnung, nicht endliche Zahlen, `factor` 0 oder zu groß, zu viele Bänder, zu lange Kachel-URL, Band, das der Vorrat nicht hat, Datensatz ohne `normalization`; die Annahme (`422`/`400`) und die Kachel (`400`/`422`) sagen den Grund, die AOI steht in keiner Antwort.
- **Gegenprobe:** Gegen den Code vor dieser Aufgabe (`6df083b`) scheitern 28 der neuen und geänderten Tests, und zwei Testdateien lassen sich dort nicht einmal laden (`NORMALIZE_V3`, `MEASURE_PERCENTILES` fehlen).
- `ruff check backend`, `lint-imports` (16 Verträge gehalten), ganze Backend-Suite grün (7493 bestanden, 14 übersprungen: PowerShell fehlt in der Sitzung); Frontend unverändert (`npm run lint`, `npx tsc -b` sauber).
- **Prüfanleitung für Otto:** `scripts/checks/nm4-11-normalize.ps1` (Windows PowerShell 5.1, Stack läuft, Netz zur Quelle): misst, lässt je Methode einen Job laufen und prüft sein Ergebnis gegen die Methode, dazu zwei Ablehnungen und das Log. Die Sitzung hatte kein PowerShell: Das Skript ist nur statisch geprüft (`backend/tests/test_nm4_11_check_script.py`), seine Helfer sind die von `nm4-19-statistics.ps1`.

**Wiedervorlage (Frage 6, Option 2).** „Gleiche Werte für alle Aufträge“ macht Ergebnisse mehrerer Szenen oder Überflüge vergleichbar (Zeitreihen). Sie bräuchte eine gemeinsame Messung über die Vereinigung der Aufträge, also eine Entscheidung zur Fläche (Vereinigung der Footprints oder der erste Auftrag) und zur Kennzeichnung im Methodentext. Otto legt sie wieder vor, sobald Zeitreihen gebaut werden. Das Backlog pflegt der Planungs-Chat.

## 15. NM4-11b — Frontend: Methoden im Panel (Aufgabe für eine neue Session)

**Stufe A**, nur Frontend und eine Zeile im Backend (die Auflistung, siehe Punkt 8), **zwei PRs** (Richtwert über 400 Zeilen): (1) Formular, Messung, Sperren; (2) mehrere Aufträge, Laden und Umdeutung. **Modell:** Sonnet, Effort hoch.
**Start:** nach dem Merge von NM4-43e (beide PRs) und von NM4-11a (#244). Höchstens zwei Frontend-Sessions gleichzeitig; nicht gleichzeitig mit NM4-20, NM4-45 oder NM4-14 (alle ändern den Bandbereich des Panels).
**Startsatz:** „Führe Aufgabe NM4-11b aus `docs/plans/querschnitt/nm4-11-normalize-methoden.md` §15 aus.“

**Ausgangslage.** Das Backend kann `normalize` Version 3 (§14): vier Methoden, die Zahlen der statistischen stehen im Rezept (`measured`), Kachel und Job geben dieselben Bytes. Die Route `POST /collections/{dataset}/statistics` (NM4-19, Frontend NM4-19b in `processingStore.ts`/`processingPreview.ts`) misst die AOI und antwortet je Band mit `minimum`, `maximum`, `mean`, `stddev` und den Perzentilen 1, 2, 5, 25, 50, 75, 95, 98, 99, dazu `exact` und `factor`. Version 3 ist `listed=False`; das Panel nach NM4-43e schickt `normalize` Version 2 (mit `bands`). Das Panel ist nach NM4-43e das mit Bandvorrat, Bandchips und „Select Bands that are processed“ (`adr/0020` §14). Entscheidungen und Begründung: §6–§14 dieses Dokuments; `adr/0014` „§15 Nachtrag NM4-11“; Oberflächentexte nur auf Englisch, wenig Text, Erklärungen im Tooltip (UI-01 §4).

**PR 1 — Formular, Messung, Sperren.**

1. **Schritt „Normalize“:** eine kurze Zeile, was der Schritt tut, mit Beispiel („Rescale values, e.g. NDVI −1…1 → 0…1“), und ein Auswahlfeld „Method“ mit vier Einträgen, je mit einem Satz Hilfe: „Fixed range“ (`linear`), „Percentile stretch“ (`percentile`), „Z-score“ (`zscore`), „Robust (median, IQR)“ (`robust`). Die Formel der gewählten Methode steht im Tooltip: `(x − from) / (to − from) × (max − min) + min`; Perzentile: dieselbe mit den Werten der Perzentile; Z-score: `(x − mean) / standard deviation`; robust: `(x − median) / (p75 − p25)`; je „measured over the AOI“. Felder mit verständlichen Namen: „From“/„To“ für den festen Bereich (Rezept: `in_min`, `in_max`), „Range“ mit den Paaren 0–100, 1–99, 2–98 (Vorgabe), 5–95 % (Rezept: `low`, `high`), „To“ mit `out_min`/`out_max` und „Clip“. „Bands“ als Chips aus dem Bandvorrat (wie NM4-43e), das letzte Ergebnis als Vorschlag. Das Formular entsteht nicht aus dem Schema (`schemaForm.ts` kennt kein `oneOf` von Objekten); wie `ClassPicker` für `mask` ist es ein Sonderfall im `StepForm`.
2. **Messung (Frage 1, W1).** Für eine statistische Methode misst das Panel automatisch, sobald sie gewählt ist und sich ändert: der Anfang der Kette (die Schritte vor dem Schritt), die AOI, die Szenen oder `bands`. Der Body ist der Auftrag, den das Panel für den Job baut, mit den Schritten **vor** dem Schritt, `output.bands` gleich den `bands` des Schritts und `dtype` `float64`. Die Abbildung aus der Antwort in `measured` (je Band):
   - Perzentile: `p_low` ist `minimum`, wenn `low` 0 ist, sonst `percentile_<low>`; `p_high` ist `maximum`, wenn `high` 100 ist, sonst `percentile_<high>`;
   - Z-score: `mean`, `stddev` (fehlt `stddev` in der Antwort, weil es nicht endlich ist, hat das Band keine Zahl);
   - robust: `p25` = `percentile_25`, `median` = `percentile_50`, `p75` = `percentile_75`;
   - `factor` ist der `factor` der Antwort. Hat ein Band keinen gültigen Wert (`count` 0, nur `valid_percent`), hat es keine Zahl.
   Die Zahlen schreibt das Panel in `params.measured`; der Benutzer tippt sie nie (KE3). Die Antwort gilt nur im Speicher (Schlüssel nie in einer URL oder einem Log); die AOI geht nur im Body.
3. **Warten und Sperren (KE2).** Solange eine Messung fehlt, läuft oder scheiterte, sind „Review“ und der Start-Knopf gesperrt; der Grund steht im Tooltip („Normalize: measuring the bands…“ bzw. „Normalize: the measurement failed: <Grund der Route>“, ohne AOI). Am Schritt steht während der Messung „Measuring…“. Eine Messung mit `exact: false` zeigt im Tooltip der Zahlen „measured on a read N times coarser“. Die Wartezeit der Vorschau (`MEASURE_WAIT_MS`) gilt hier nicht.
4. **Gesperrt (Frage 5, Option 1).** Ohne AOI und nach einem `reproject` (der Schritt steht in der Kette hinter einem `reproject`) sind die drei statistischen Methoden gesperrt, nicht ausgeblendet; der Grund steht im Tooltip: „Draw an AOI; the values are measured over it“ bzw. „Move Normalize above Reproject; the values are measured before a reprojection“. „Fixed range“ geht immer.
5. **Vorschau.** Die Kachel-Kette zeigt den Schritt mit den Zahlen in `params` (Version 3 läuft als Kachel). Wird die URL zu lang (`MAX_OPERATOR_PARAMS_CHARS` 2048, höchstens 4 Schritte) oder fehlt eine Zahl, endet die gezeigte Kette vor dem Schritt, mit dem bestehenden Hinweis „The map shows the first N steps“. Vorschau und Ergebnis zeigen dieselbe Farbskala.
6. **Auftrag.** Das Panel schickt `normalize` Version 3 (`method`, `bands`, die Felder der Methode, `measured`); die Felder einer anderen Methode fehlen. Version 2 schickt es nicht mehr.
7. **Tests** (vitest): Formular je Methode; der gebaute Body der Messung (Schritte davor, `float64`, `bands`); die Abbildung der Antwort in `measured` je Methode, mit `low` 0 und `high` 100; Sperre und Tooltip von „Review“/„Start“ in allen Zuständen (misst, gescheitert, fertig); Sperre ohne AOI und nach `reproject`; neu messen bei Änderung von AOI, Szenen, `bands`, vorigen Schritten; keine AOI in einer URL (Test über alle gebauten URLs); kein Zahl-Eintrag von Hand.
8. **Backend, eine Zeile:** `NORMALIZE_V3.listed` auf `True`, `NORMALIZE_V2.listed` auf `False` (`processing/operators/normalize.py`), damit die Prozessbeschreibung Version 3 bietet; im PR begründet. Der Test `test_the_process_description_offers_it_once_it_is_listed` (`tests/earthx/processing/test_normalize_methods.py`) wird dafür von der Hilfskopie auf die echte Registry umgestellt.

**PR 2 — mehrere Aufträge, Laden, Umdeutung.**

9. **Mehrere Aufträge (Frage 6, Option 1).** Bei „One job per pass“ und „per scene“ misst jeder Auftrag für sich beim Schätzen („Review“), parallel wie die Schätzungen (`ESTIMATE_PARALLEL`); jedes Rezept trägt die Werte seiner Fläche. Bis 25 Aufträge. Ein Auftrag, dessen Messung scheitert, ist gesperrt, mit Grund im Tooltip dieses Auftrags.
10. **Laden.** Beim Laden einer `recipe.json`, eines Permalinks, bei der Ablage im Browser und bei „⚙“ am Ergebnis (NM4-05b) misst das Panel neu für die aktuelle Auswahl; gespeicherte Zahlen werden nicht übernommen (KE3). Ein Schritt `normalize` Version 2 aus einer Datei wird im Panel zu Version 3 `linear` mit denselben Zahlen (KE4, bitgleich).
11. **Tests:** Batch (n Aufträge, n Messungen, je eigener Fehler), Laden mit alten und neuen Dateien, Umdeutung Version 2 nach 3.

**Abnahme (beide PRs).**

- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster, mit nachgestellten Antworten der Route; im PR beschrieben. **Bilder nicht ins Repo.**
- Prüfanleitung für Otto im PR (Browser und/oder PowerShell 5.1: Route mit Perzentilen, Job je Methode, Methodentext in der `recipe.json`).
- Alle vier Pflicht-Checks der CI grün: Lint (`npm run lint`), Typprüfung (`npx tsc -b --pretty false`), Tests, Backend-Tests.
- Nachtrag `adr/0014` „§15 Nachtrag NM4-11b“ (Panel, Messung, Sperren), Log-Zeile mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat). Vor „fertig“ ist `main` geholt.
- Grenzen: Oberflächentexte nur auf Englisch; keine neue Abhängigkeit ohne Frage an Otto; keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs; `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 16. Umsetzung NM4-11b (Frontend, 01.11.2026)

Draft-PR [#269](https://github.com/oscipal/earthX/pull/269) trägt das Frontend und die Auflistung (§15 Punkt 8). Statt zweier PRs (§15) steht alles in einem (Otto, 01.11.2026: ein PR genügt), in Commits an der Naht von PR 1 (Formular, Messung, Sperren, Vorschau) und PR 2 (mehrere Aufträge, Laden); der Richtwert von 400 Zeilen ist überschritten.

**Auslegungen von Claude** (gelten, bis Otto widerspricht): siehe die Log-Zeile vom 01.11.2026 und `adr/0014` „§15 Nachtrag NM4-11b“. Otto hat entschieden: Die Bänder bleiben Chips (Beschriftung „Band“, wie bei „Mask by value“), nicht ein Dropdown; der Zielbereich ist mit 0 bis 1 vorbelegt; die gesperrten Schritte eines Ergebnisses („⚙“) behalten ihre gemessenen Zahlen und messen nicht neu, Rezeptdatei, Permalink und Ablage messen neu (`adr/0019` „Nachtrag NM4-11b“). `test_the_item_is_fetched_once` bleibt unangetastet (Backlog 68).

**Abnahme NM4-11b.**

- **Vitest:** `normalizeMethods.test.ts` (Formular aus dem Schema, Regeln, Abbildung der Antwort je Methode mit `low` 0 und `high` 100, Fragen und Zustände von `buildOrder`), `ProcessingNormalize.test.tsx` (Formular je Methode, gebauter Body der Messung, Warten und Sperren in allen Zuständen, neu messen bei AOI, Band, Szene und Schritten davor, keine AOI in einer Adresse, Stapel, Laden, Vorschau, Sperren), dazu Vorschau und Entwurf.
- **Browser:** `frontend/e2e/normalize-methods.cjs`, 12 Fälle (Chromium, hell/dunkel, 1280/360 px), alle ohne Befund.
- **Backend:** die Auflistung (`NORMALIZE_V3.listed=True`, `NORMALIZE_V2.listed=False`), der Test der Prozessbeschreibung auf die echte Registry umgestellt.
- **Prüfanleitung für Otto:** im PR.
