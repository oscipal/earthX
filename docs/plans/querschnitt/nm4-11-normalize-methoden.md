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

**Zeitpunkt der Umsetzung (Otto, Startsatz dieser Session, 30.10.2026):** Code erst nach NM4-43e. Bis dahin liegt hier nur der Plan; die Umsetzung beginnt nach dem Merge beider PRs von NM4-43e (Panel und Vorschau), weil sie das neue Panel, die Bandchips und die Kachel mit Bandvorrat (NM4-43d) braucht. Nachträge heißen nach der Aufgabe („§15 Nachtrag NM4-11“).

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

_Folgt im nächsten Commit (Recherche läuft)._

### 7.4 Jede Methode als Gerade [A]

| Methode | Formel je Band | Zahlen | Wertebereich danach |
|---|---|---|---|
| linear (heute) | `(x − in_min) / (in_max − in_min) · (out_max − out_min) + out_min`, optional begrenzt | vom Benutzer | Zielbereich (mit `clip`) |
| Perzentile | dieselbe Gerade mit `in_min` = p_low, `in_max` = p_high, optional begrenzt | gemessen | Zielbereich (mit `clip`) |
| Z-Score | `(x − mean) / stddev` | gemessen | offen, Mittel 0, Streuung 1 über die AOI |
| robust | `(x − median) / (p75 − p25)` | gemessen | offen, Median 0 |

- 0–100 % ist „Minimum–Maximum der AOI“; ein eigener Eintrag „min–max“ entfällt damit.
- Z-Score und robust teilen einen Kern (`subtract`, `divide`); Perzentile teilen den Kern von linear. Es kommen keine Rechenarten dazu, die vom Prozessor abhängen; die Bitstabilität von §15c gilt weiter, ein Test unter A und D von `adr/0016` §3.3 hält sie fest.
- Nicht definiert sind `stddev` = 0, `p75 = p25` und `p_low = p_high` (konstantes Band in der AOI) und ein Band ohne gültigen Wert. Dann misst das Panel keine Zahl, der Schritt nennt den Grund, „Start“ ist gesperrt; das Rezept lehnt solche Werte ab (`422`).

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

- `measured.bands` nennt genau die Bänder von `bands`, je mit den Werten der Methode (endlich; `low < high`, `stddev > 0`, `p25 < p75`, `p25 ≤ median ≤ p75`); `factor` ist das k der Route (1 = exakt), damit der Methodentext ehrlich ist.
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

## 10. Tests (Abnahme)

Backend (`pytest`, synthetische Raster wie `processing/test_core_statistics.py`):

1. **Je Methode gegen eine unabhängige Rechnung:** linear, Perzentile, Z-Score, robust je auf einem kleinen Array gegen eine Rechnung in Python (`fractions.Fraction` bzw. `float64` von Hand), Ergebnis `float32` gleich; Maske und NaN bleiben; Bänder außerhalb von `bands` unverändert (Typ und Werte).
2. **Messung gegen unabhängige Rechnung:** Route mit `uint16`-Band (Perzentile exakt) gegen `numpy.percentile(method="inverted_cdf")` auf denselben Pixeln der AOI; `float32`-Band innerhalb eines Fachs (2⁻⁷ relativ) und nach außen gerundet; `mean` exakt, `stddev` gegen `numpy.std(ddof=0)`.
3. **Ende zu Ende:** Auftrag mit den gemessenen Zahlen als Job: Statistik des Ergebnisses passt zur Methode (Perzentile: p_low → `out_min`, p_high → `out_max` bis auf ein Fach; Z-Score: Mittel ~0, Streuung ~1 über die AOI).
4. **Bitgleich:** derselbe Auftrag zweimal → gleiche SHA-256 von `result.tif`; Einstellungen A und D von `adr/0016` §3.3; Runner gegen Kern (`runner/test_compare.py`) je Methode; Kachel gegen Job auf der nativen Ebene (COG).
5. **Speicher:** `test_memory_mask_normalize.py` um Version 3 (Z-Score, vier Bänder, 4096²) unter 500 MB.
6. **Fehleingaben (`422`):** unbekannte Methode; Felder einer anderen Methode (`extra="forbid"`); `measured.bands` ohne ein Band von `bands` oder mit einem fremden; `stddev` 0, negativ, NaN, ∞; `low ≥ high`; `p25 > median`; `low` 3 (kein erlaubtes Paar); `factor` 0; leere `bands`; Groß-/Kleinschreibung doppelt. Version 2 weiter angenommen und bitgleich zu Version 3 `linear`.
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

_Folgen mit §7.3._
