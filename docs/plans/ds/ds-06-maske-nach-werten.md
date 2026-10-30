# DS-06 — Maske nach Werten eines Bandes

**Stand:** 26.10.2026, beauftragt von Otto. Paket „Datensatzabhängige Suche und Prozessierung“ (DS), nach VP3 und vor M5; Übersicht in `docs/plans/ds/ds-00-paket.md`.
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach UI-01; nicht gleichzeitig mit NM4-10 (Bandnamen). Höchstens zwei Stufe-B-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe DS-06 aus `docs/plans/ds/ds-06-maske-nach-werten.md` aus.“

## 1. Anlass

`mask` (M4-18) blendet heute nur Klassen einer Klassifizierungsschicht aus (`SCL`). Otto möchte auch Pixel nach Werten eines beliebigen Bandes ausblenden (etwa NDVI < 0,2 oder Höhe > 2000 m). Mit Band math und `where` lässt sich ein Wert ersetzen, aber nicht sauber als „kein Wert“ (nodata) markieren.

## 2. Soll

- Pixel werden ausgeblendet (nodata), wenn ein gewähltes Band eine Bedingung erfüllt: kleiner, größer, zwischen, gleich (für Klassen).
- Das Band kann ein Band des Datensatzes oder das Ergebnis eines früheren Schritts sein (NM4-10).
- Verfügbar für jeden Datensatz; die Maske nach Klassen (`SCL`) bleibt für Datensätze mit Klassifizierung.

## 3. Im Plan klären (mit Optionen und Empfehlung)

- Eigener Operator, neue Version von `mask` (Parameter `by: classes | values`) oder Band-math-Erweiterung (etwa ein `nodata`-Literal)? Empfehlung mit Begründung.
- Bitgleichheit Kachel ↔ Job; Versionierung (`op_version`), Nachtrag `adr/0014`; Kostenfaktor.

## 4. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip. Nicht anwendbare Möglichkeiten werden ausgeblendet, nicht ausgegraut (Otto, 26.10.2026).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Ausgehende Requests nur über `gateway`; keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Kein datensatzspezifischer Code: Unterschiede je Datensatz stehen als Daten in der Registry.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: Bedingungen gegen eine unabhängige Rechnung, Kette mit Band math, Kachel ↔ Job bitgleich.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), Hell/Dunkel, schmales Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n).
- Vor „fertig“ ist main geholt.

---

# Plan (30.10.2026)

Belegstufen wie in `adr/0009`: [M] gemessen, [P] am Primärdokument oder im Code gelesen, [S] Zusammenfassung ohne geprüften Wortlaut, [A] eigene Ableitung. Grundlage ist das Bandmodell aus `adr/0020` (Bandvorrat, lineare Kette, `output.bands`, Streichen im Planer; §4, §12 Zeile DS-06). Gelesen auf `main` = `f121972` (nach NM4-43e PR 1, #250). Nachträge heißen nach der Aufgabe („§15 Nachtrag DS-06“). Bilder der Browser-Prüfung kommen nicht ins Repo.

## 6. Kurzfassung

- **`adr/0020` §12 legt die Wirkung schon fest:** Die Bedingung nennt ein Band des Vorrats, auch ein Ergebnis (`NDVI < 0.2`), und blendet wie `mask` in **allen** Bändern aus. Offen ist nur die Form im Rezept, die Bedingungen und die Oberfläche.
- **Empfehlung (Frage 1): eigener Operator `mask_values` Version 1**, `pixel`, `T1` und `T2`, Parameter `band`, `condition` (`lt`, `gt`, `between`, `eq`) und `values`. `mask` Version 2 (Klassen der `SCL`) bleibt unverändert, ebenso jedes bestehende Rezept und sein Hash. Neues Capability-Flag `value_masking` ohne Vorgabe, in allen drei Einträgen `True` (B10).
- **Kern:** ein Vergleich je Pixel, keine Gleitkommarechnung, also bitstabil im Sinn von `adr/0014` §15c wie `mask`; Kachel und Job rufen dieselbe Funktion. Gemessen kostet der Kern auf 1024² 0,7–1,8 ms, weniger als `mask` (2,8 ms) [M]; Kostenfaktor wie `mask` **0,2**.
- **Vergleich im Typ des Bandes** (Frage 3): ein Gleitkomma-Band vergleicht in seinem eigenen Typ (so dass `NDVI = 0.2` den Wert trifft, den Statistik und Tooltip als 0.2 zeigen), ein ganzzahliges exakt. Das ist auch die Regel von numpy (NEP 50) [P].
- **Pixel ohne Wert im Bedingungsband werden ausgeblendet** (Frage 4), wie bei `mask` (M4-18 F3).
- **Versionen:** `recipe_version` bleibt 2, `earthx.__version__` bleibt 0.5.0 (kein Byte eines bestehenden Rezepts ändert sich; wie NM4-11). Nachtrag `adr/0014` „§15 Nachtrag DS-06“, kurzer Nachtrag in `adr/0016` (älterer Runner weist den Operator ab).
- **Panel:** neuer Knopf „＋ Mask by value“; Felder Band (Dropdown: frühere Ergebnisse, dann Bänder des Datensatzes), Bedingung, Wert(e) mit Einheit. Der heutige Hinweis „Mask: this dataset has no classification layer to read.“ entfällt (Regel vom 26.10.2026: ausblenden statt erklären).
- **Schnitt (Frage 6):** zwei PRs, DS-06a Backend und DS-06b Frontend, je unter 400 Zeilen.

## 7. Befunde

### 7.1 `mask` heute [P]

- `backend/earthx/processing/operators/mask.py`: Version 2 nimmt `source` (Bandname der Klassenschicht) und `classes` (aufsteigend, je einmal, 1–64), blendet in allen Bändern des Vorrats aus, wo die Schicht eine der Klassen trägt **oder** selbst maskiert ist, und lässt die Schicht im Vorrat (`_run_v2`). Vergleich `numpy.isin`, keine Gleitkommarechnung.
- Gebunden an `Capabilities.masking`, und `masking` ist laut Registry genau dort `True`, wo `DatasetConfig.mask` eine Klassenschicht beschreibt (`catalog/registry.py:1140`). `dataset_check` verlangt `source == mask.band` und Klassen aus der Liste der Schicht. Eine Maske über `red` oder über ein Ergebnis ist damit ausdrücklich ausgeschlossen.
- Für `cop-dem-glo-30` ist `masking=False`; das Panel zeigt dort den Satz „Mask: this dataset has no classification layer to read.“ (`frontend/src/components/ProcessingPanel.tsx:736`).

### 7.2 Band math und „kein Wert“ [P]

- `band_math` maskiert ein Pixel seines Ergebnisses, wo der Ausdruck nicht endlich ist (`_computed`: `mask | ~isfinite(result)`). `where(NDVI < 0.2, 0/0, NDVI)` ergibt heute schon „kein Wert“ — aber nur im **neuen** Band, die übrigen Bänder des Vorrats bleiben. Das ist der Umweg aus §1, nicht das Soll.
- Ein Literal `nodata` hätte dieselbe Grenze (wirkt auf ein Band) und ändert die Ausdruckssprache R5, deren Umfang wegen der Bitstabilität eng gehalten ist (`adr/0014` §15c).

### 7.3 Bandvorrat, Streichen und Kachel [P]

- `BandUse(reads=…, adds=…, acts_on=…)` (`operators/base.py`) sagt dem Planer, was ein Schritt braucht. Eine Maske nach Werten ist `reads={band}`, `adds=None`, `acts_on=None` (alle) — dieselbe Form wie `mask` Version 2. Streichen, `output.bands` und die Ableitung der Assets in `api` brauchen nichts Neues.
- Die Kachel rechnet die Kette aus `T1`-`pixel`-Schritten (höchstens 4) und mit `band=` nur das gezeigte Band (NM4-43d, #245). Ein neuer `T1`-`pixel`-Operator läuft dort ohne Änderung an `processing/tile.py`.
- STAC-Eigenschaften eines Schritts fasst der Kern zusammen: ein Schritt → Objekt, mehrere → Liste (`processing/core.py:441–444`). Zwei Wertmasken (`< 0.2` und `> 0.8`) sind damit ohne eigene Regel abgebildet.
- Der Vorrat ist ein Array **eines** Typs: `band_math` Version 2 hebt ihn auf `promote_types(…, float32)` (`band_math.py:_run_v2`). Eine ganzzahlige Klassenschicht steht nach einem `band_math`-Schritt als `float32` im Vorrat, ihre Werte bleiben exakt.

### 7.4 Andere Plattformen [P] [S]

- **openEO** [P]: Vergleich und Maske sind getrennte Prozesse. `lt`/`gt` vergleichen streng, `between` schließt beide Grenzen ein (`exclude_max` optional), `eq` vergleicht exakt mit optionalem `delta`; `mask` ersetzt Pixel, deren Maskenwert wahr ist, durch nodata. Ein no-data-Operand ergibt im Vergleich no-data.
- **numpy NEP 50** [P]: Ein Python-Skalar ist „schwach typisiert“; `float32_array < 0.2` vergleicht in `float32`.
- **Earth Engine** [S]: `image.updateMask(image.select('NDVI').gte(0.2))` — Vergleich als Bild, dann Maske auf alle Bänder des Bildes.

### 7.5 Messung des Kerns [M]

Prototyp eines Kerns (nur Messung, kein Produktivcode; Skript in der Sitzung, nicht im Repo) gegen die bestehenden Kerne auf einem Vorrat aus drei `float32`-Bändern zu 1024², kleinster Wert aus 15 Läufen, zwei Durchgänge, x86_64, 4 Kerne:

| Kern | ms |
|---|---|
| `band_math` v2 NDVI | 8,2–16,6 (numexpr-Threads streuen) |
| `mask` v2, 4 Klassen | 2,8–2,9 |
| Wertmaske `lt` / `gt` | 0,7–0,8 |
| Wertmaske `between` | 1,1 |
| Wertmaske `eq`, 4 Werte | 1,7–1,8 |

Gegenprobe zur Typregel: `float32(0.2)` ist im eigenen Typ gleich `0.2`, in `float64` weder gleich noch kleiner [M].

## 8. Optionen und Empfehlung

### 8.1 Form im Rezept (Frage 1)

| | O1 eigener Operator `mask_values` | O2 `mask` Version 3 mit `by: classes \| values` | O3 Band math mit `nodata`-Literal |
|---|---|---|---|
| Wirkung laut `adr/0020` §12 (alle Bänder) | ✓ | ✓ | ✗ nur das neue Band |
| Bestehende Rezepte, Hash | unverändert | `mask` v2 bleibt angenommen; das Panel schickt v3, jede Klassenmaske bekommt einen neuen Hash, Umdeutung v2 → v3 in `recipeUpgrade.ts` | unverändert |
| Capability (B10) | neues Flag `value_masking`; `masking` behält seine Bedeutung (Klassenschicht) | `masking` müsste zwei Dinge heißen oder per `extra_requirements` je Variante gelten; Auflistung je Datensatz muss die Variante kennen | `band_math` |
| Parameter (B10: alles ausdrücklich) | ein flaches Modell, jedes Feld Pflicht | Felder der anderen Variante verboten oder `oneOf` von Objekten; das Formular aus dem Schema kann das nicht (`schemaForm.ts` kennt `oneOf` nur für Konstanten) | Erweiterung von R5 |
| Panel | zweiter Knopf; ausblenden über die Auflistung | ein Knopf, Umschalter im Schritt, der beim DEM ausgeblendet wird | kein neuer Schritt |
| openEO | `lt`/`gt`/`between`/`eq` + `mask` | gleich | `if` + `mask` je Band |

**Empfehlung: O1.** Es ändert nichts Bestehendes, die Bedeutung von `masking` bleibt scharf, das Parametermodell ist flach und ohne Ausnahmen, und die Regel „nicht Mögliches ausblenden“ erledigt die Auflistung je Datensatz. O3 erfüllt das Soll nicht (§7.2). Eine Maske über ein Ergebnis mit Klassen (`mask` mit `source` beliebig) wäre ein weiterer Weg, deckt aber nur „gleich“ ab und ist in O1 als `eq` enthalten.

**Form (O1):**

```json
{"op": "mask_values", "op_version": 1, "params": {"band": "NDVI", "condition": "lt", "values": [0.2]}}
```

| `condition` | Panel | Pixel wird ausgeblendet, wenn | `values` |
|---|---|---|---|
| `lt` | below | `x < v` | genau 1 |
| `gt` | above | `x > v` | genau 1 |
| `between` | between | `lo ≤ x ≤ hi` (beide eingeschlossen, wie openEO) | genau 2, `lo < hi` |
| `eq` | equal to | `x` ist einer der Werte | 1 bis 64, aufsteigend, je einmal (wie `mask.classes`, K3: eine Maske, eine Schreibweise) |

Jeder Wert ist eine endliche Zahl. `band` ist ein Bandname des Vorrats an dieser Stelle (Band des Datensatzes oder Ergebnis eines früheren Schritts), geprüft wie heute: `api` an der Beschreibung der Collection, der Kern in `transform` vor dem ersten Block.

Beispiele: Ottos Fälle `{"band": "NDVI", "condition": "lt", "values": [0.2]}` und, beim DEM, `{"band": "data", "condition": "gt", "values": [2000]}`.

### 8.2 Bedingungen (Frage 2)

Empfohlen sind die vier aus §2 (kleiner, größer, zwischen, gleich), streng bzw. eingeschlossen wie openEO. `≤`, `≥` und „außerhalb“ bringen keine neue Fähigkeit: Bei Klassen ist `< 3` gleich `≤ 2`, bei Gleitkomma ist der Unterschied eine Grenze von Maß null, und „außerhalb von 0.2–0.8“ sind zwei Schritte (`lt 0.2`, `gt 0.8`). Sie können später als weitere Werte von `condition` dazukommen, ohne neue Version der vier bestehenden.

### 8.3 Vergleich und Datentyp (Frage 3)

| | T1 im Typ des Bandes | T2 immer `float64` |
|---|---|---|
| Regel | Gleitkomma-Band: der Wert wird auf den Typ des Bandes gerundet, dann verglichen; ganzzahliges Band: exakt in `float64` (jede `uint16`/`int32` ist dort exakt) | Band in `float64` aufgeweitet (exakt), Wert als `float64` |
| `NDVI eq 0.2`, Pixel `float32(0.2)` | ausgeblendet | bleibt (`0.2000000030 ≠ 0.2`) |
| `NDVI lt 0.2`, Pixel `float32(0.2)` | bleibt | bleibt |
| Was die Person sieht | Statistik, Tooltip und Farbskala zeigen `float32` gerundet; die Regel trifft, was dort steht | eine Grenze, die man nicht sieht |
| numpy | Vorgabe (NEP 50) | ausdrücklich zu schreiben |
| bitgleich Kachel ↔ Job | ✓ (gleiche Funktion, kein Rechnen) | ✓ |

**Empfehlung: T1.** Der Methodentext nennt den Wert wie im Rezept; der Tooltip im Panel sagt „compared in the band's data type“.

### 8.4 Pixel ohne Wert im Bedingungsband (Frage 4)

**Empfehlung: ausblenden**, wie `mask` (M4-18 F3) und wie openEO (ein no-data-Operand gibt kein „falsch“). Ein Pixel, über das die Bedingung nichts sagen kann, bleibt nicht als gültig stehen. Die Alternative „stehen lassen“ würde etwa bei `NDVI < 0.2` die Pixel behalten, deren NDVI wegen `0/0` fehlt.

### 8.5 Bitgleichheit, Version, Nachtrag, Kostenfaktor

- **Bitgleich Kachel ↔ Job [A]:** Der Kern vergleicht nur und verknüpft Masken; Kachel (`T1`) und Job (`T2`) rufen dieselbe Funktion auf demselben `ImageData`. Auf der nativen Ebene (COG) bitgleich, auf Zarr gilt die Regel von `adr/0014` §15d. Ein gröberes Bedingungsband kommt wie jedes Band mit der Regel der verschachtelten Raster auf das feine Raster (M4-09 F2); das macht die Ausgabe nicht „resampled“, solange es nicht selbst in der Ausgabe steht (`BandMeta.resampled`, NM4-43c).
- **Bitstabil über Rechner:** wie `mask` ohne Gleitkommarechnung; Test unter den Einstellungen A und D von `adr/0016` §3.3 (SHA-256).
- **Version:** `mask_values` Version 1. `recipe_version` 2 bleibt. `earthx.__version__` bleibt 0.5.0, weil sich für kein bestehendes Rezept ein Byte ändert (wie NM4-11, `adr/0016` Nachtrag NM4-11); ein älterer Runner weist ein Rezept mit `mask_values` als unbekannten Operator ab (Exit-Code 2).
- **Nachträge:** `adr/0014` „§15 Nachtrag DS-06: der Operator `mask_values`“ (zu §5.2, §5.3, §5.5, §6.3, §15m; `adr/0020` §12) mit Parametern, Flag, Typregel, Faktor, Toleranz, Speicher. `adr/0016` ein Absatz „Nachtrag DS-06“ (Runner-Tag, Abweisung durch ältere Fassungen).
- **Kostenfaktor:** **0,2**, wie `mask`. Der Kern ist kleiner als der von `mask` (§7.5) und fällt nach der Regel aus §15m (Anteil am Lauf von 146 ms je Megapixel, aufgerundet auf eine Nachkommastelle → 0,1; Zuschlag Statistik-Durchgang +12,1 % → 0,2) auf denselben Wert. In der Umsetzung wird nach dem Verfahren von §15m nachgemessen.
- **Speicher:** läuft im Durchgang des Lesens, fügt kein Band hinzu; Speicherschätzung (NM4-43c PR 2) unverändert. `test_memory_mask_normalize.py` bekommt einen Fall unter 500 MB.

### 8.6 Panel (nach NM4-43e, Texte englisch, UI-01 §4)

```
  Steps
    1. NDVI          band math
       Expression [ (nir-red)/(nir+red)  ]
       Name       [ NDVI ]
    2. Mask_values_2   mask by value                              ↑ ↓ ✕
       Band ⓘ        [ NDVI ▾ ]
       Hide where ⓘ  [ below ▾ ]   [ 0.2 ]          ← between: [ 0.2 ] and [ 0.8 ]
                                                    ← equal to: [ 3, 8, 9 ]
    Add step:  ＋ Band math  ＋ Mask  ＋ Mask by value  ＋ Normalize  ＋ Reproject
```

- **Knopf** „＋ Mask by value“ nur, wo die Prozessbeschreibung `mask_values` für den Datensatz listet (heute überall). „＋ Mask“ bleibt nur bei Datensätzen mit Klassenschicht, der Satz darunter für Datensätze ohne Schicht entfällt.
- **Band:** Dropdown mit den Ergebnissen früherer Schritte, dann den Bändern des Datensatzes aus „Bands“ (ohne Hilfs-Assets). Ein Band, das erst ein späterer Schritt hinzufügt, oder das es nicht gibt, meldet am Feld wie ein Ausdruck (`'x' is added by a later step`, `'x' is not a band name`) und sperrt „Add step“, „Review“ und „Start job“ (Regel aus `adr/0020` §18.1).
- **Hide where:** Auswahl below / above / between / equal to; je nach Wahl ein Zahlenfeld, zwei Felder oder ein Feld für eine Liste („3, 8, 9“, das Panel sortiert und entfernt Doppelte). Die Einheit des Bandes klein neben der Beschriftung (`in m`), wenn bekannt.
- **Tooltips (ⓘ):** Band: „The band whose values decide. Pixels are hidden in every band.“ Hide where: „below and above leave the value itself; between includes both ends. Physical values, compared in the band's data type. Pixels where the band has no value are hidden too.“
- **Umbenennen** eines Ergebnisses zieht `band` mit (`adr/0020` §6 nennt die Maske ausdrücklich).
- **Vorschau:** keine eigene Logik; der Schritt ist `T1` und steht in der Kette der Kachel.

Die Idee `by: classes | values` aus §3 lässt sich auch mit O1 nur im Panel abbilden: ein Knopf „＋ Mask“, im Schritt ein Umschalter, dahinter zwei Operatoren. Das spart einen Knopf, kostet aber einen Umschalter, der ohne Klassenschicht ausgeblendet werden muss. Frage 5.

### 8.7 Schnitt (Frage 6)

| PR | Inhalt | Richtwert |
|---|---|---|
| DS-06a Backend | Operator, Flag `value_masking` in Registry und Einträgen, Registrierung, Prozessbeschreibung, Nachträge `adr/0014` und `adr/0016`, Tests 1–9 (§10) | ca. 150 Zeilen Code, 250 Tests |
| DS-06b Frontend | Knopf, Formular, Band-Dropdown, Umbenennen, Wegfall des Hinweises, Tests 10–12 | ca. 150 Zeilen Code, 200 Tests |

DS-06b berührt `StepForm.tsx` und `ProcessingPanel.tsx`; es sollte nicht gleichzeitig mit NM4-43e PR 2, NM4-11b oder NM4-14b laufen (Bandbereich und Schritte des Panels).

## 9. Kleinentscheidungen

Gelten, sofern du nicht widersprichst:

- **KE1 Name und Titel:** `op` `mask_values`, Kategorie `quality`, Titel „Mask by value“, Beschreibung „Hide the pixels where a band's value is below, above, between or equal to the values given.“ Schritt-Titel im Panel wie bei anderen Schritten ohne eigenes Band: „<n>. Mask_values_<n>“.
- **KE2 Flag:** `Capabilities.value_masking`, ohne Vorgabe (B10), in `sentinel-2-c1-l2a`, `sentinel-2-l2a-zarr3` und `cop-dem-glo-30` `True`; erscheint mit den übrigen Flags in `earthx:capabilities`. Kein datensatzspezifischer Code.
- **KE3 `band`:** 1–64 Zeichen druckbares ASCII ohne Leerzeichen (wie `mask.source`, damit Zarr-Namen passen); ob es das Band gibt, prüfen `api` und Kern. Kein `dataset_check` nötig: Jedes Band des Vorrats ist erlaubt, auch die Klassenschicht.
- **KE4 Werte:** JSON-Zahlen, strikt (kein `true`, kein Text), endlich und auch in `float32` endlich (Betrag unter 3,4·10³⁸), damit die Typregel aus §8.3 keinen Wert zu ∞ rundet.
- **KE5 Methodentext** (NM4-08): „Pixels were hidden in every band where NDVI was below 0.2 or had no value.“ / „… between 0.2 and 0.8 (both included) …“ / „… equal to 3, 8 or 9 …“. `processing:lineage`: „mask values: NDVI < 0.2“. Eigenschaft `earthx:mask_values`: `{"band", "condition", "values"}`, bei mehreren Schritten eine Liste (Regel des Kerns).
- **KE6 Streichen:** `bands_used` = `reads={band}`; das Bedingungsband wird gelesen, solange ein Schritt danach oder die Ausgabe etwas braucht, und muss nicht in der Ausgabe stehen.
- **KE7 Log:** nichts Neues im Betrieb; Werte, Bandnamen und Bedingungen stehen in keinem Log.
- **KE8 Klassenmaske:** `mask` Version 2 bleibt unverändert, Titel „Mask“ bleibt (außer Frage 5 sagt anders).
- **KE9 Ganzzahlige Ausgabe:** Eine Ausgabe nur aus `uint8`/`uint16`-Bändern bekommt nodata nach der bestehenden Regel des Kerns (wie bei `mask`); nichts Neues.

## 10. Tests (Abnahme)

Backend (`pytest`, synthetische Raster, DS-06a):

1. **Bedingungen gegen eine unabhängige Rechnung:** je Bedingung auf kleinen Arrays (`uint16`, `float32`) gegen eine Schleife in reinem Python über `fractions.Fraction`; Grenzwerte genau auf der Schwelle und je ein ULP darüber und darunter (`numpy.nextafter`); `eq` mit mehreren Werten; die Typregel (`float32(0.2)` bei `eq 0.2` ausgeblendet, bei `lt 0.2` nicht).
2. **Wirkung:** alle Bänder des Vorrats an denselben Pixeln ausgeblendet, das Bedingungsband eingeschlossen; Werte und Typ der übrigen Pixel unverändert; schon maskierte Pixel bleiben maskiert; Pixel ohne Wert im Bedingungsband ausgeblendet.
3. **Kette mit Band math:** `band_math` NDVI → `mask_values` NDVI `lt 0.2`, Ausgabe `NDVI` und `red`: ausgeblendet genau dort, wo eine unabhängige NDVI-Rechnung < 0,2 ist; Reihenfolge Maske vor `band_math` (NDVI aus maskierten Bändern) gleich Maske danach, wie `adr/0020` §4.
4. **Kachel ↔ Job bitgleich** auf der nativen Ebene (COG) für die Kette aus 3, mit `band=`; Zarr nach §15d.
5. **Bitstabil:** derselbe Auftrag zweimal gleiche SHA-256 von `result.tif`; Einstellungen A und D (`adr/0016` §3.3); Runner gegen Kern.
6. **Streichen:** mit und ohne Streichen bitgleich; Bedingungsband nicht in der Ausgabe → gelesen, nicht geschrieben.
7. **Fehleingaben (`422`, Text nennt Feld und Grund):** unbekannte `condition`; falsche Zahl an `values` je Bedingung; `between` mit `lo ≥ hi`; `eq` unsortiert, doppelt, mehr als 64; NaN, ∞, zu groß, Text, `true`; leeres oder fremdes `band`; Band eines späteren Schritts; Felder von `mask` (`source`, `classes`) im Schritt.
8. **Zweckfremd:** Datensatz mit `value_masking=False` (Test-Registry) → nicht gelistet, Auftrag `422`, Kachel `422`; Registry ohne `value_masking` lädt nicht (B10); fünf Schritte in der Kachel → bestehende Grenze; alles ausgeblendet → Verhalten wie heute bei leerer Maske.
9. **Speicher** unter 500 MB (`test_memory_mask_normalize.py`); **Gegenprobe:** Tests 1–8 laufen gegen den Code vor der Änderung und scheitern (Operator unbekannt), Ergebnis im PR.

Frontend (`vitest`, DS-06b):

10. Knopf nur, wo gelistet; Formular je Bedingung, gebauter Auftrag; Band-Dropdown (Ergebnisse, Bänder, keine Hilfs-Assets); Fehler am Feld und Sperren; Umbenennen zieht `band` mit; `recipe.json` und Permalink hin und zurück; Hinweis „no classification layer“ entfällt.
11. Prüfung im echten Browser (Chromium/Playwright der Sitzung) mit nachgestellten Antworten: hell und dunkel, schmales Fenster; im PR beschrieben, Bilder nicht ins Repo.
12. Prüfanleitung für Otto im PR (Browser; PowerShell 5.1 mit `Invoke-RestMethod` gegen `/processes` und einen Auftrag mit `mask_values`).

Dazu: `ruff check backend`, `pytest`, `lint-imports`, `npm run lint`, `npx tsc -b`; alle vier Pflicht-Checks der CI grün; vor „fertig“ `main` geholt; Log-Zeilen.

## 11. Fragen an Otto

Kurz beantwortbar: je Frage eine Nummer.

**Frage 1 — Form im Rezept**
1. Eigener Operator `mask_values` mit `band`, `condition`, `values`; `mask` bleibt (O1). **(Empfehlung)**
2. `mask` Version 3 mit `by: classes | values` (O2).
3. Band math mit `nodata`-Literal (O3; blendet nur das neue Band aus).

**Frage 2 — Bedingungen**
1. below (`<`), above (`>`), between (beide Grenzen eingeschlossen), equal to (eine oder mehrere Zahlen). **(Empfehlung)**
2. Dazu `≤`, `≥` und „outside“.
3. Wie 1, aber between ohne die obere Grenze.

**Frage 3 — Vergleich**
1. Im Datentyp des Bandes (`float32`-Wert 0.2 ist gleich 0.2). **(Empfehlung)**
2. Immer in `float64`.

**Frage 4 — Pixel ohne Wert im gewählten Band**
1. Werden ausgeblendet, wie bei der Klassenmaske. **(Empfehlung)**
2. Bleiben stehen.

**Frage 5 — Knöpfe im Panel**
1. Zwei Knöpfe: „Mask“ (Klassen, nur mit Klassenschicht) und „Mask by value“; Hinweis „no classification layer“ entfällt. **(Empfehlung)**
2. Ein Knopf „Mask“; im Schritt ein Umschalter „Classes / Values“, ausgeblendet ohne Klassenschicht.
3. Wie 1, aber „Mask“ heißt „Mask by class“.

**Frage 6 — Schnitt**
1. Zwei PRs in dieser Session, Frontend auf dem Backend gestapelt. **(Empfehlung)**
2. Backend in dieser Session, Frontend in einer neuen Session nach dem Merge.
3. Ein PR.

## 12. Quellen

- openEO `between`: https://raw.githubusercontent.com/Open-EO/openeo-processes/master/between.json [P]
- openEO `lt`: https://raw.githubusercontent.com/Open-EO/openeo-processes/master/lt.json [P]
- openEO `eq` (mit `delta`): https://raw.githubusercontent.com/Open-EO/openeo-processes/master/eq.json [P]
- openEO `mask`: https://raw.githubusercontent.com/Open-EO/openeo-processes/master/mask.json [P]
- numpy NEP 50, Typregel für Python-Skalare: https://raw.githubusercontent.com/numpy/numpy/main/doc/neps/nep-0050-scalar-promotion.rst [P]
- Earth Engine `Image.updateMask`: https://developers.google.com/earth-engine/apidocs/ee-image-updatemask [S]
- Intern: `adr/0020` §4, §6, §10, §12, §18; `adr/0014` §5.2, §5.3, §5.5, §6.3, §15c, §15d, §15m; `adr/0016` §3.3, Nachtrag NM4-11; `plans/m4/m4-18-masking-normalisierung.md` F3; `processing/operators/mask.py`, `band_math.py`, `base.py`, `processing/core.py:441`, `catalog/registry.py:1140`, `frontend/src/components/ProcessingPanel.tsx:736`, `frontend/src/schemaForm.ts:171`.
