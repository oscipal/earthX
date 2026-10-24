# M4-18 — Operatoren Masking und Normalisierung: Plan

**Aufgabe:** M4-18 aus `docs/plans/m4-processing-kern.md` §4.
**Stufe B (S4) — von Otto am 20.10.2026 freigegeben:** F1–F6 und F8 je
Option 1, K1–K8 angenommen, F7 mit Beleg [P] und Auflagen (§8). Umgesetzt wird
in derselben Session nur **M4-18a**; M4-18b und M4-18c sind je eine neue Session
nach dem Merge (M4-18c: §13). Wo §3 und §8 sich widersprechen, gilt §8.
**Ort im Repo:** `docs/plans/m4-18-masking-normalisierung.md`
**Grundlagen:** `adr/0014` §5.1–§5.7, §6.1–§6.4, §15c, §15d; `adr/0016` §3.3,
§12a; `plans/m4-processing-kern.md` §1.1b (R3, R5), §1.1c (S4), §1.2, M4-18;
`plans/m4-09-band-math.md` §3, §9, §10; `plans/m4-13-processing-panel.md` §13;
`architekturplan.md` 7.1; `KLAERUNGEN.md` B9, B10, B11. Code in
`processing/operators/` (`base.py`, `registry.py`, `band_math.py`),
`processing/source.py`, `processing/tile.py`, `processing/plan.py`,
`api/tiler.py`, `api/intake.py`, `catalog/registry.py`, `catalog/datasets.py`,
`frontend/src/processingPreview.ts`, `frontend/src/schemaForm.ts`.

---

## 1. Ergebnis in drei Sätzen

Ein neues Registry-Feld `mask` nennt je Datensatz die Klassifikationsschicht
(Asset, Bandname, Tabelle der Klassen), dazu kommen die Flags `masking` und
`normalization` in `Capabilities`, beide ohne Vorgabewert (B10); das DEM setzt
keine Maske und lehnt `mask` deshalb ab. Der Operator `mask` (`op_version` 1,
`pixel`, T1 und T2) blendet alle Bänder dort aus, wo die Schicht eine der im
Rezept genannten Klassen trägt, und lässt die Schicht selbst weg; `normalize`
(`op_version` 1, `pixel`, T1 und T2) bildet einen Wertebereich aus dem Rezept
linear auf einen Zielbereich aus dem Rezept ab, ohne Statistik der Szene. Beide
rechnen nur mit Vergleichen und Grundrechenarten, sind damit bitstabil im Sinn
von R5 und `adr/0014` §15c, und ein Vergleichstest zeigt T1 gegen T2 wie bei
Band-Math (COG bitgleich, Zarr nach §15d).

---

## 2. Stand vor dieser Aufgabe (gelesen am 20.10.2026, `main` = `f17de87`)

**Code:**
- **Operatoren:** `REGISTRY` hält `band_math` (v1) und `reproject` (v2, v3).
  `Operator` hat `requires` (Flags, Datenklassen, Lizenzstufe),
  `extra_requirements(params)` und `properties(params)`; eine Prüfung gegen
  Felder des Eintrags außer den Flags gibt es nicht. `applicable` prüft nur
  Flags, Datenklasse und Lizenzstufe (`registry.py`).
- **Bänder im Kern:** Ein `pixel`-Schritt bekommt ein `ImageData` mit allen
  Bändern aller Assets des Auftrags, in physikalischen Werten und mit Namen
  (COG: Asset-Schlüssel; Zarr: Variable). Assets verschiedener Auflösung
  liest der Kern nach M4-09 F2 mit `nearest` auf das feinste Raster und setzt
  `earthx:resampled` (`source.py`, `common_grid`).
- **Kachel-Pfad:** Eine Kachel-URL trägt genau einen Operator (`op`,
  `op_version`, `params`, je einmal; `api/tiler.py::_operator_request`). Das
  Panel zeigt als Vorschau nur den ersten Schritt
  (`processingPreview.ts::planPreview`, „the tile route takes one operator“).
  `adr/0014` §6.1 sieht dagegen den **längsten Anfang** aus T1-`pixel`-Schritten
  als Kachelparameter vor.
- **Panel-Formulare:** `schemaForm.ts` kennt `string`, `number`, `integer`,
  `boolean`, `enum` und `const`; ein Feld vom Typ Liste ist „not supported by
  this panel“.
- **Ganzzahlige Ausgabe:** `core._nodata_for` verlangt dafür ein gemeinsames,
  endliches nodata aller Bänder; ein Band mit NaN-nodata (Band-Math) macht
  jede Ganzzahl-Ausgabe unmöglich (`plans/m4-13-processing-panel.md` §13).

**Quellen [M]** (5 Anfragen an Datenquellen, je mindestens 1 s Abstand, keine
AOI; Rohdaten im Scratchpad der Sitzung):

| Was | Ergebnis |
|---|---|
| Earth Search, Item von `sentinel-2-c1-l2a` (das aus M4-09 §10) | Asset `scl`, Titel „Scene classification map (SCL)“, `gsd` 20, `raster:bands` `[{"nodata": 0, "data_type": "uint8", "spatial_resolution": 20}]`, **keine** `classification:classes`, kein `scale`/`offset`. Daneben `cloud` und `snow` (Wahrscheinlichkeiten, `uint8`, nodata 0) |
| Earth Search, Collection `sentinel-2-c1-l2a` | `item_assets.scl` wie oben, ohne Klassentabelle; `classification` nicht unter den Erweiterungen |
| EOPF, Collection `sentinel-2-l2a-zarr3` und das neueste Item | Assets `SCL_20m` (`…/conditions/mask/l2a_classification/r20m`) und `SCL_60m`, Rollen `data`, `mask`, Band `scl`, `uint8`, nodata 0; keine Klassentabelle |
| EOPF, `scl/zarr.json` des Items | `uint8`, `fill_value` 0, Attribute `scale_factor` 1, `add_offset` 0, `_FillValue` 0, `valid_min` 1; **kein** `flag_values`/`flag_meanings` |
| `cop-dem-glo-30` | ein Asset `data`, keine Klassifikationsschicht im Bucket (`adr/0009`) |

**Nicht erreicht aus der Sitzung:** Die Klassentabelle der SCL steht in keiner
Quellenantwort. Die Primärdokumente liegen auf gesperrten Hosts:
`sentiwiki.copernicus.eu` (Proxy `403`; über WebFetch: Name nicht auflösbar),
`step.esa.int` (`403`), `documentation.dataspace.copernicus.eu` (`403`). Otto hat
die Tabelle am 20.10.2026 im Chat am Primärdokument gelesen und den Beleg
nachgereicht (F7, §8): jetzt **[P]**.

---

## 3. Umsetzung

### 3.1 Registry (`catalog/registry.py`, `catalog/datasets.py`)

**Neue Flags in `Capabilities`** (B10, ohne Vorgabe, nach dem Muster von R3):
- `masking: bool` — der Datensatz trägt eine Schicht, aus der `mask` liest.
- `normalization: bool` — `normalize` ist freigeschaltet (generisch wie
  Band-Math, aber nach B10 ausdrücklich je Eintrag, F2).

**Neues Feld `DatasetConfig.mask: MaskSource | None`**, ohne Vorgabe:

```python
@dataclass(frozen=True, slots=True)
class MaskClass:
    value: int          # 0..65535
    label: str          # English, shown in the panel

@dataclass(frozen=True, slots=True)
class MaskSource:
    asset: str                       # the order's asset key: "scl", "SCL_20m:scl"
    band: str                        # the band name the kernel sees: "scl"
    classes: tuple[MaskClass, ...]   # every class the layer knows, ascending
    suggested: frozenset[int]        # what the panel ticks first; never applied without the recipe naming it
    reference: str                   # where the table comes from (https URL of the primary document)
```

**Prüfungen beim Laden (Registry-Test, B10):** `masking` genau dann `True`,
wenn `mask` gesetzt ist; Werte eindeutig, aufsteigend, `suggested ⊆ classes`;
`asset` ist ein Asset, das der Eintrag kennt (bei Zarr mit Trenner `:` und
`band` = Variable); `reference` ist `https`.

**Werte der drei Einträge (Vorschlag):**

| Eintrag | `masking` | `normalization` | `mask` |
|---|---|---|---|
| `sentinel-2-c1-l2a` | `True` | `True` | `asset="scl"`, `band="scl"`, Tabelle SCL, `suggested={3, 8, 9, 10}` |
| `sentinel-2-l2a-zarr3` | `True` | `True` | `asset="SCL_20m:scl"`, `band="scl"`, dieselbe Tabelle, dieselbe Auswahl |
| `cop-dem-glo-30` | `False` | `True` | `None` |

**Tabelle SCL [P]** (SentiWiki „S2 Processing“, L2A Algorithms → Scene
Classification → Table 3 „Scene classification values“, gelesen von Otto am
20.10.2026): 0 NO_DATA, 1 SATURATED_OR_DEFECTIVE, 2 CAST_SHADOWS, 3
CLOUD_SHADOWS, 4 VEGETATION, 5 NOT_VEGETATED, 6 WATER, 7 UNCLASSIFIED, 8
CLOUD_MEDIUM_PROBABILITY, 9 CLOUD_HIGH_PROBABILITY, 10 THIN_CIRRUS, 11 SNOW or
ICE. Ältere Darstellungen benennen 2 und 7 anders („Dark Area Pixels“, „Clouds
Low Probability / Unclassified“); die Werte sind gleich. `suggested` folgt dem
Beispiel in `architekturplan.md` 7.1 (`[3, 8, 9, 10]`); `0` ist ohnehin
nodata und damit maskiert (§3.2). `reference` ist die SentiWiki-Seite.

`SCL_20m`, nicht `SCL_60m`: Die 20-m-Schicht passt verschachtelt auf das
10-m-Raster (`source.py`, F2 von M4-09) wie `scl` bei Earth Search.

**Nach außen:** Die Collection trägt `earthx:mask` (Asset, Band, Klassen mit
Label, `suggested`, `reference`, `note`), damit das Panel die Klassen mit Namen zeigen kann
(`catalog/collection.py`, wie `earthx:default_render`).

### 3.2 Operator `mask` (`processing/operators/mask.py`)

**Parameter (`MaskParams`, strikt, `extra="forbid"`, eingefroren, alles
Pflicht):**
- `source: str` — der Bandname der Schicht (`scl`), 1–64 Zeichen ASCII.
- `classes: list[int]` — 1 bis 64 Werte, je 0..65535, **aufsteigend und ohne
  Doppel** (sonst `ValueError`: zwei Schreibweisen derselben Maske gäben zwei
  Rezept-Hashes, K3).

**Kern (`run(image, params)`):**
- Ein Pixel fällt in allen übrigen Bändern aus, wo `source` eine der Klassen
  trägt **oder** selbst maskiert ist (nodata 0 bzw. CF-Füllwert; F3).
- Vergleich exakt: `numpy.isin` auf den Werten der Schicht, wie gelesen
  (`uint8` beim COG; `float32`/`float64` nach CF-Dekodierung beim Zarr, ganze
  Zahlen bleiben dort exakt).
- Das Band `source` fällt aus dem Ergebnis; die übrigen Bänder behalten Namen,
  Werte und Datentyp, nur die Maske wächst. Bleibt kein Band → `RecipeInvalid`.

**Weitere Felder:**
- `requires`: `masking`, alle Datenklassen, Lizenzstufe *Processing*.
- **Neu im Operator:** `dataset_check(config, params) -> list[str]`, mit
  Vorgabe „nichts“ wie `extra_requirements`; `applicable` ruft es mit `params`
  auf. Für `mask`: `source == config.mask.band` und
  `classes ⊆ config.mask.classes`, sonst Gründe → `422` in Annahme und Kachel.
  `processing` liest dafür nur die übergebene `DatasetConfig` aus
  `catalog.registry` (§5.3, `adr/0011` §6.2); der Kern selbst ruft es nie.
- `transform`: `source` muss unter den Bändern sein (`RecipeInvalid` vor dem
  ersten Block, wie Band-Math); Ergebnis ohne das Band, `resampled` bleibt.
- `lineage`: „mask: scl classes 3, 8, 9, 10“.
- `properties`: `earthx:mask` = `{"source": …, "classes": […]}`.
- `cost_factor`: Startwert 0,2 **[A]**, in der Umsetzung gegen den Kern von
  Band-Math je Megapixel gemessen und im PR belegt (`projektplan.md` 7
  Punkt 7).

**Wie die Schicht in den Auftrag kommt:** Das Rezept nennt `scl` (bzw.
`SCL_20m:scl`) unter `assets`, wie jedes andere Asset. Nichts wird still
ergänzt („Ehrlichkeit“, `architekturplan.md` 7.1). Die Annahme prüft mit dem
vorhandenen `check_bands`, dass `source` unter den Bändern ist.

### 3.3 Operator `normalize` (`processing/operators/normalize.py`)

**Parameter (`NormalizeParams`, strikt, alles Pflicht, B10):**
- `in_min`, `in_max: float` — endlich, `in_min < in_max`.
- `out_min`, `out_max: float` — endlich, verschieden (`out_min > out_max`
  kehrt um, erlaubt).
- `clip: bool` — Werte außerhalb von `[in_min, in_max]` auf den Zielbereich
  begrenzen oder linear fortsetzen.

**Kern:** je Band, in float64, in fester Reihenfolge
`(x − in_min) / (in_max − in_min) * (out_max − out_min) + out_min`, mit
`clip` danach `numpy.clip` auf den Zielbereich, Ergebnis float32, nodata NaN.
Getrennte numpy-Ufuncs, kein numexpr, keine Zusammenziehung zu FMA. Ein
Bereich für alle Bänder (F4). Maske unverändert; nicht endliche Ergebnisse
werden maskiert (kann nur bei Überlauf auftreten).

**Weitere Felder:** `requires`: `normalization`, Lizenzstufe *Processing*;
`transform`: alle Bänder float32, NaN; `lineage`: „normalize: [a, b] → [c, d],
clipped“; `properties`: keine; `cost_factor` wie bei `mask` gemessen.

**Was „Normalisierung“ hier nicht ist (F5):** keine Perzentile, keine
Statistik der Szene oder der AOI, kein z-Score. Das Panel darf die Zahlen aus
einer Statistik **vorschlagen** (heute `/statistics` je Asset, mit M4-32 die
Statistik eines Ergebnisses); im Rezept stehen dann feste Zahlen, und T1 und T2
rechnen dasselbe.

### 3.4 Kachel-Pfad (T1)

- **Ein Operator je Kachel geht ohne Änderung:** `mask` und `normalize` sind
  T1-`pixel`-Operatoren und laufen über `_operator_request` und
  `OperatorTileReader` wie Band-Math. Mit `mask` liest die Kachel `scl`
  (20 m) verschachtelt auf das 10-m-Raster (M4-09 F2).
- **Kette in der Kachel (F1):** Masking ist erst mit einem Folgeschritt
  nützlich (maskiertes NDVI). Vorschlag: `op`, `op_version` und `params`
  dürfen wiederholt werden, gleich oft, höchstens 4, in Reihenfolge der
  Schritte; jeder Schritt muss T1 und `pixel` sein, `applicable` gilt je
  Schritt, `transform` läuft die Kette vor dem ersten Pixel ab. Die heutige
  Form mit einem Operator ist der Fall n = 1 und bleibt gültig. Das Panel
  zeigt dann den längsten Anfang aus T1-Schritten (`adr/0014` §6.1) statt nur
  den ersten.
- `params` je Schritt höchstens 2048 Zeichen wie heute.

### 3.5 Panel (Frontend, F6)

- `normalize`: Zahlen und Wahrheitswert, das Formular kann das heute.
- `mask`: `classes` ist eine Liste, die `schemaForm.ts` nicht kennt. Neu ein
  Feld „Classes to hide“ mit Kästchen und Labels aus `earthx:mask` der
  Collection, vorbelegt mit `suggested`; `source` ist kein Eingabefeld, sondern
  kommt aus `earthx:mask.band`. Das Asset `earthx:mask.asset` nimmt das Panel
  in den Auftrag auf, sichtbar in „Review“.

### 3.6 Tests

Fixtures nur synthetisch (`tests/earthx/processing/sources.py`,
`readers/mini_zarr*.py`); externe Quellen nur über `tests/fixtures`.

- **Registry:** jedes Flag gesetzt (vorhandene Prüfung); `masking` ⇔ `mask`;
  Klassen eindeutig und aufsteigend, `suggested ⊆ classes`, `asset` bekannt,
  `reference` https; je ein Eintrag mit Widerspruch wird beim Laden abgewiesen.
- **`mask`:** synthetische SCL-Rampe (alle 12 Klassen) gegen eine Formel;
  nodata der Schicht maskiert; Schicht fällt aus dem Ergebnis; nur Schicht im
  Auftrag → `RecipeInvalid`; `source` nicht unter den Bändern → Fehler vor dem
  ersten Block; Parameter abgewiesen: leer, unsortiert, doppelt, negativ,
  > 65535, `bool`, Text, 65 Werte, Zusatzfelder.
- **Zweckfremd:** `source` auf ein Reflexionsband (`red`) → `422` aus
  `dataset_check` in Annahme und Kachel, ohne Abruf des Items; Klasse 12 → `422`;
  `mask` auf dem DEM → `422` (`masking=False`); `normalize` auf einem Eintrag
  mit `normalization=False` → `422`.
- **`normalize`:** Werte gegen die Formel, mit und ohne `clip`, umgekehrter
  Zielbereich; abgewiesen: `in_min == in_max`, `in_min > in_max`,
  `out_min == out_max`, `inf`, `nan`, Text statt Zahl, fehlendes Feld,
  Zusatzfelder.
- **T1 ↔ T2 (Abnahme):** COG-Paar `red` 10 m + `scl` 20 m mit
  Skalierung am `red` (Rampen aus `sources.py`): Kachel über die echte Route
  gegen den Job, `nearest`, native Ebene, `numpy.array_equal` über gültige
  Pixel und gleiche Masken — für `mask`, für `normalize` und mit F1 für die
  Kette `mask → band_math`. Mini-Zarr mit CF-Attributen nach der Regel von
  `adr/0014` §15d (Grenzpixel).
- **Bitstabilität über CPU-Stufen:** der Kindprozess aus M4-09
  (`adr/0016` §12a, Einstellungen A und D) rechnet beide Kerne; gleiche
  SHA-256 verlangt, sonst Überspringen nur mit Grund.
- **T2 ↔ T2L:** ein Rezept `mask → normalize` im vorhandenen Vergleich
  Kern gegen Runner.
- **Checkliste v2** (`test_onboarding_processing.py`, Q14) bleibt grün und
  unverändert.
- **Frontend (mit F6):** Formular für `classes`, Vorbelegung aus `suggested`,
  das Asset der Maske im Auftrag, Vorschau des längsten T1-Anfangs.

### 3.7 Doku und Log

- `ENTSCHEIDUNGSLOG.md`: Freigabe und je Teil die Umsetzung, am Ende.
- `adr/0014`: Nachtrag `§15m` zu §5.2/§5.3 (neue Operatoren, `dataset_check`,
  Flags) und §6.3 (Zeilen für `mask`, `normalize`).
- `plans/m4-processing-kern.md` §3: Stand von M4-18.

---

## 4. Nicht in dieser Aufgabe

- Maske aus einer Wahrscheinlichkeit mit Schwelle (`cloud`, `snow` bei Earth
  Search) oder aus einem Wertebereich eines Bands (etwa Höhen unter 0 m); das
  wäre eine zweite Art von `MaskSource` mit eigener `op_version`.
- Maske über mehrere Aufnahmen (Komposit), Puffer um Wolken, Morphologie.
- Perzentile, z-Score, Statistik der Szene (F5).
- Bereich je Band bei `normalize` (F4).
- Ganzzahlige Ausgabe nach `normalize` (nodata NaN, `core._nodata_for`; offene
  Frage aus `plans/m4-13-processing-panel.md` §13).
- `decomp.py`, `gateway`, `jobs`, `objectstore`, `.importlinter`, `.github/`.

---

## 5. Umfang und Schnitt

Geschätzt [A]: Registry und Collection 70 Zeilen, `mask.py` 130,
`normalize.py` 100, `dataset_check` 20; Kette im `tiler` 60, Panel 150;
Tests rund 600. Zusammen deutlich über dem Richtwert von 400 Zeilen. Schnitt
nach F8. Commits je Thema, etwa:

1. `catalog`: Flags `masking`, `normalization` und Feld `mask`, drei Einträge
2. `processing`: `dataset_check` im Operator und in `applicable`
3. `processing`: Operator `mask`
4. `processing`: Operator `normalize`
5. Tests: T1 ↔ T2, CPU-Stufen, T2 ↔ T2L
6. `api`, Frontend: Kette in der Kachel, Vorschau des T1-Anfangs (F1)
7. Frontend: Formular der Maske (F6)
8. Doku, ADR-Nachtrag, Log

Vor dem Fertigmelden: `main` holen, `pytest`, `ruff check backend`,
`PYTHONPATH=backend lint-imports --config .importlinter`, im Frontend
`npm run lint`, `npx tsc -b --pretty false` und die Tests; Ergebnisse im PR.

---

## 6. Risiken

- **Klassentabelle:** Beleg [P] von Otto aus dem Chat; die Session hat das
  Dokument nicht selbst gelesen. Die Namen in der Registry stehen wörtlich so
  wie in §3.1.
- **Wechsel des Verarbeitungsstands:** Ältere Prozessierungsbasen benennen
  manche Klassen (2, 7) anders, die Werte sind gleich. Earth Search Collection 1
  beginnt mit Baseline 5.0 (`adr/0003` §6); für EOPF ist der Bestand nicht
  geprüft. Der Hilfetext sagt es (§8).
- **Maske aus 20 m auf 10 m:** Die Maske ist blockig (2 × 2), und das Ergebnis
  trägt `earthx:resampled=true`, auch wenn nur die Maske verdoppelt wurde.
  Ehrlich, aber für Nutzer erklärungsbedürftig.
- **Kette in der Kachel (F1):** Wiederholte Query-Parameter sind schwerer zu
  lesen als ein JSON; dafür bleibt die Ein-Schritt-Form gültig, und das
  Frontend baut die URL ohnehin kanonisch.
- **Leere Kachel:** Bei 100 % Wolken liefert die Kachel nur Maske; das ist
  richtig, sieht aber wie ein Fehler aus.

---

## 7. Fragen an Otto

**F1 — Kette von Operatoren in der Kachel (§3.4)**
1. `op`, `op_version`, `params` wiederholbar, gleich oft, höchstens 4; das
   Panel zeigt den längsten T1-Anfang (`adr/0014` §6.1). Maskiertes NDVI hat
   dann eine Vorschau **(Empfehlung)**
2. Ein Operator je Kachel bleibt; maskiertes NDVI gibt es nur als Job, die
   Vorschau zeigt nur die Maske
3. Ein neuer Parameter `steps` mit JSON-Liste statt der drei Parameter

**F2 — Flag für `normalize` (§3.1)**
1. Eigenes Flag `normalization`, alle drei Einträge `True` (B10, wie R3)
   **(Empfehlung)**
2. Kein eigenes Flag, nur Lizenzstufe *Processing*
3. Unter `band_math`

**F3 — Was mit Pixeln ohne Klasse passiert (§3.2)**
1. Wo die Schicht selbst nodata ist, fällt der Pixel immer aus **(Empfehlung)**
2. Nur, wenn das Rezept `0` unter `classes` nennt

**F4 — Bereich bei `normalize` (§3.3)**
1. Ein Bereich für alle Bänder in `op_version` 1; je Band später mit
   `op_version` 2 **(Empfehlung)**
2. Je Band ein Bereich schon jetzt (Liste je Band; braucht ein neues
   Formularfeld)

**F5 — Perzentile (§3.3)**
1. Nicht in M4. Das Panel schlägt `in_min`/`in_max` aus einer vorhandenen
   Statistik vor, im Rezept stehen feste Zahlen; T1 und T2 bleiben bitgleich
   **(Empfehlung)**
2. Perzentile nur in T2 als eigene Art von Schritt mit zweitem Lesedurchgang
   über die AOI (neuer Kernpfad, eigene Messung zu Speicher und Zeit)

**F6 — Frontend in M4-18 (§3.5)**
1. Ja: Formular „Classes to hide“ mit Labels, `source` und Asset aus
   `earthx:mask`, dazu die Vorschau des T1-Anfangs nach F1 **(Empfehlung)**
2. Nein: nur Backend; das Panel zeigt `mask` als „not supported by this panel“
   bis nach M4

**F7 — Beleg der SCL-Tabelle (§2, §3.1)**
1. Otto gibt einen der Hosts für diese Session frei
   (`sentiwiki.copernicus.eu` oder `step.esa.int`); die Session liest die
   Tabelle dort und setzt `reference` auf diese Seite **(Empfehlung)**
2. Otto nennt Dokument und Seite; die Session übernimmt die Tabelle von dort
3. Werte ohne Labels in die Registry (nur Zahlen im Panel), Labels später

**F8 — Schnitt in PRs (§5)**
1. Drei PRs: M4-18a Registry, beide Operatoren, Tests (T1 mit einem Operator);
   M4-18b Kette in der Kachel und Vorschau des T1-Anfangs (F1); M4-18c Panel
   für die Maske (F6). b und c nach a, b und c unabhängig voneinander
   **(Empfehlung)**
2. Ein PR über dem Richtwert
3. Zwei PRs: Backend (a und der `tiler`-Teil von b) und Frontend

**Kleinentscheidungen** (gelten mit der Freigabe, wenn Otto nichts sagt):
- **K1:** `op_version` 1 für `mask` und für `normalize`.
- **K2:** `mask` lässt das Band der Schicht im Ergebnis weg; wer es braucht,
  liest es ohne Maske.
- **K3:** `classes` aufsteigend und ohne Doppel, sonst abgewiesen (ein Rezept,
  ein Hash); 1 bis 64 Werte, je 0..65535.
- **K4:** Der Name in den Parametern ist `source` wie in `architekturplan.md`
  7.1 und meint den Bandnamen, nicht den Asset-Schlüssel.
- **K5:** `dataset_check` ist ein neues Feld von `Operator` mit Vorgabe
  „keine Gründe“; nur `applicable` ruft es, nie der Kern.
- **K6:** `suggested` ist kein Vorgabewert im Sinn von B10: Das Rezept nennt
  die Klassen immer selbst, das Panel kreuzt sie nur vor.
- **K7:** Die Collection trägt `earthx:mask`; ohne Maske fehlt das Feld.
- **K8:** `cost_factor` beider Operatoren wird in der Umsetzung gemessen; bis
  dahin 0,2 [A].

---

## 8. Freigabe (Otto, 20.10.2026)

F1 (1), F2 (1), F3 (1), F4 (1), F5 (1), F6 (1), F8 (1); K1–K8 angenommen.
**F7:** keine Änderung der Host-Freigabe. Beleg [P], von Otto im Chat am
Primärdokument gelesen: SentiWiki „S2 Processing“
(`https://sentiwiki.copernicus.eu/web/s2-processing`), Abschnitt L2A Algorithms
→ Scene Classification → Table 3 „Scene classification values“; die Namen
stehen in §3.1. Registry und Plan nehmen diese Namen und diese Quelle.

**Auflagen:**
- **Raster der Maske:** `scl` (20 m) wird nur mit `nearest` auf das Bandraster
  gebracht, es entstehen keine neuen Werte; das Ergebnis trägt
  `earthx:resampled`. Dazu ein Test.
- **Hilfetext:** Er weist darauf hin, dass ältere Prozessierungsbasen manche
  Klassen anders benennen (`MaskSource.note`, `earthx:mask.note`).

**Schnitt (F8 (1)):** M4-18a (Registry, beide Operatoren, Tests, Kachel mit einem
Operator) in dieser Session; M4-18b (Kette in der Kachel, Vorschau des
T1-Anfangs, F1) und M4-18c (Panel, F6) je als neue Session nach dem Merge von
M4-18a.

---

## 9. Umsetzung von M4-18a (20.10.2026)

Umgesetzt wie freigegeben, in thematischen Commits im selben Draft-PR. Keine neue
Abhängigkeit, keine Lock-Datei geändert; `.github/`, `.claude/`, `CLAUDE.md` und
`.importlinter` unberührt, `lint-imports` hält alle 16 Verträge.

**Geliefert:**
- **Registry:** `Capabilities.masking` und `.normalization`, `DatasetConfig.mask`
  (`MaskSource`, `MaskClass`), Prüfungen beim Laden, die drei Einträge nach §3.1,
  `earthx:mask` in der Collection. `MaskSource.note` trägt den Hinweis auf die
  abweichenden Namen älterer Prozessierungsbasen (Auflage).
- **Operatoren:** `mask` v1 und `normalize` v1, `Operator.dataset_check`, von
  `applicable` aufgerufen. `mask` lässt die Schicht aus dem Ergebnis weg (K2);
  an einer maskierten Stelle behalten die Bänder ihren Wert, nur die Maske wächst
  (anders als bei Band-Math, das dort NaN schreibt).
- **Kachel mit einem Operator:** keine Änderung am `tiler` nötig; `mask` und
  `normalize` laufen über denselben Weg wie `band_math`. Die Kette (F1) ist
  M4-18b.
- **Frontend:** nur die erzeugten Prozess-Fixtures (`scripts/write-process-fixtures.py`)
  und drei Erwartungen in `processingOrder.test.ts`. Das Panel zeigt `normalize`
  mit seinem Formular und `mask` als „not supported by this panel“, bis M4-18c die
  Klassenauswahl bringt; auf dem DEM bietet es `mask` gar nicht an.

**Faktoren (§3.2, K8), gemessen:** Kern auf einem Block von 1024² (kleinster Wert
aus 15 Läufen, zwei Durchgänge, x86_64): Band-Math NDVI 14,6–15,5 ms, `mask` mit
zwei Bändern und der Schicht 5,3–7,1 ms, `normalize` mit zwei Bändern 27,1–29,3 ms.
Gegen 146 ms je Megapixel für einen ganzen Band-Math-Lauf (`adr/0014` §3.5)
ergibt das aufgerundet **0,1** für `mask` und **0,2** für `normalize`. Nach dem Merge
von M4-32a (Statistik-Durchgang, Zuschlag +12,1 % wie bei Band-Math) gelten nach Ottos Regel
„aufrunden“ **0,2** und **0,3** (§11). Das Skript
liegt im Scratchpad der Sitzung; es liest keine Datenquelle.

**Tests (neu):**
- `tests/catalog/test_mask_source.py`: Namen und Werte der SCL, beide Assets, der
  Hinweistext, das DEM ohne Schicht, jeder Widerspruch im Eintrag, die Collection.
- `tests/earthx/processing/test_mask.py`: Parameter (18 abgewiesene Formen),
  Kern (Klassen, nodata der Schicht, Float-Schicht wie aus Zarr, fehlende Schicht),
  Metadaten, `applicable` (Aufklärung zu `red`, Klasse 12, DEM, Display-Stufe) und
  Läufe über eine 20-m-Schicht.
- `tests/earthx/processing/test_normalize.py`: Parameter, Kern gegen die Formel,
  Umkehr, `clip`, Überlauf, kein Blick auf Nachbarpixel, Lauf gegen die Formel,
  Bitstabilität unter den Einstellungen A und D (`GLIBC_TUNABLES` wirkt in der
  Sitzung, der Test lief also, ohne Überspringen).
- `tests/earthx/api/test_tiler_mask_normalize.py`: Kachel gleich Job auf der
  nativen Ebene (COG, vier Fälle, jeweils mit der Maske des Jobs), Abweisungen
  (`422` für Schicht und Klassen, fehlende Fähigkeit, Display-Stufe; `400` für
  Parameter; kein Abruf des Items vor einer Abweisung).
- **Auflage Raster der Maske:** `test_the_layer_is_repeated_with_nearest_…` liest
  eine 20-m-Schicht zu einem 10-m-Band, prüft, dass die Menge der Werte der
  verdoppelten Schicht die der Schicht ist, dass die Maske des Ergebnisses genau
  die Formel aus den verdoppelten Klassen und dem nodata beider Quellen ist, und
  dass `earthx:resampled` im Ergebnis und in `meta` gesetzt ist.

**Abweichungen und Befunde:**
1. **Mini-Zarr nicht mit `mask` verglichen** (erledigt am 22.10.2026, §10).
   §3.6 nannte den Vergleich T1 ↔ T2 auch für einen Mini-Zarr mit CF-Attributen.
   Der Test deckte zunächst nur COG ab, weil der vorhandene Mini-Zarr keine
   Klassenschicht hatte.
2. **Kachel unter einer Maske hat keine NaN unter der Maske.** Wo die Maske etwas
   ausblendet, behält die Kachel den Wert des Bands, die Alpha-Schicht der Kachel
   trägt die Maske. Der Hilfsbau `_decode` in `test_tiler_operator.py` verlangt
   NaN unter der Maske und gilt nur für Band-Math; der neue Test hat einen eigenen.
3. **Bestehende Tests angepasst:** Die Liste der Operatoren in vier Tests
   (`test_operators.py`, `test_processing_docs.py`) und drei Erwartungen im
   Frontend; Fixtures neu erzeugt.

**Nicht gemessen** (erledigt am 22.10.2026, §10): Speicher von `mask` und
`normalize` gegen die Grenze von 500 MB.

**Offen für M4-18b und M4-18c:** Kette in der Kachel (F1), Vorschau des
T1-Anfangs, Formular „Classes to hide“, Asset der Maske im Auftrag.

---

## 10. Nacharbeit (Otto, 22.10.2026)

Drei Punkte aus Ottos Auftrag vom 22.10.2026, alle in diesem PR:

1. **ADR-Nummer.** Der Nachtrag in `adr/0014` heißt §15m (M4-32a hat §15k, M4-19a
   §15l). Umbenannt in `adr/0014`, in den Docstrings von `catalog/registry.py`,
   `processing/operators/` und den Tests, in §3.7 dieses Plans und im Log.
2. **`Operator.method` aus M4-19a (#171).** Beim ersten Holen von `main` am 22.10.2026
   war #171 noch nicht gemergt; M4-19a sollte die Sätze ergänzen. Es ist inzwischen
   gemergt und die Sätze stehen hier (§11).
3. **Zwei Lücken aus §9 geschlossen:**
   - **(a) Speicher bei 4096².** `tests/earthx/processing/test_memory_mask_normalize.py`
     misst wie `test_memory_reproject.py` den Gipfel `VmHWM` eines Kindprozesses
     (`memory_run.py` kennt die Schritte `mask` und `normalize`; für `mask` mit einer
     20-m-Klassenschicht als zweitem COG), `GDAL_CACHEMAX` 64 MB, Szene mit zwei Bändern
     `uint16` zu 2048² und 4096². Gemessen in der Sitzung (x86_64):

     | Schritt | 2048² | 4096² | Wachstum |
     |---|---|---|---|
     | `mask` | 284,8 MB | 353,3 MB | 68,5 MB |
     | `normalize` | 290,0 MB | 365,9 MB | 75,9 MB |

     Nach dem Merge von M4-32a (Statistik-Durchgang im Lauf) neu gemessen: `mask` 282,9 und
     351,4 MB (Wachstum 68,5 MB), `normalize` 289,7 und 369,8 MB (Wachstum 80,1 MB).

     Verlangt sind unter 500 MB bei 4096² und höchstens 100 MB Wachstum (ein Drittel
     Reserve; ein Kern, der die Szene in `float64` hielte, wüchse um 192 MB). Der Wert
     für `imports_mb` liegt bei 163,5 MB wie bei den anderen Operatoren.
   - **(b) Kachel gegen Job für `mask` auf Zarr.** Der CF-Mini-Zarr
     (`tests/earthx/readers/mini_zarr_cf.py`) trägt die Gruppe `scl20m` mit der
     Variablen `scl` (24² Pixel zu 20 m über derselben Ausdehnung, `uint8`, Klassen 0 bis
     11, CF-Attribute `scale_factor 1`, `add_offset 0`, `_FillValue 0` wie bei EOPF).
     `TestTheTileEqualsTheJobOnZarr` prüft zwei Dinge, wie bei Band-Math (`adr/0014`
     §15d): Die Kachel ist in **jedem** Pixel die Formel auf dem nächsten Quellpixel
     beider Raster (Maske exakt, Werte des Bands bis auf 1e-6 relativ); und der Job,
     auf dieselbe Kachel gelesen, gibt dieselben Werte und dieselbe Maske überall außer
     innerhalb von 0,125 Quellpixel einer Grenze beider Raster, und dort weniger als
     5 % der gültigen Pixel. Gemessen: 3 von 2236 gültigen Pixeln einer z14-Kachel
     haben verschiedene Masken, alle an einer Grenze. Die Werte der Kachel kommen als
     `float64` aus dem Store, die des Jobs als `float32` aus der Datei; verglichen wird
     als `float32`.

Die zwei offenen Log-Zeilen aus §9 stehen auf „erledigt (2026-10-22)“.

---

## 11. Nach dem Merge von `main` (M4-19a, M4-32a; 22.10.2026)

`main` brachte M4-32a (#168) und M4-19a (#171) in den Branch. Konflikte gab es nur in
Dokumenten (`ENTSCHEIDUNGSLOG.md`, `adr/0014`, `plans/m4-processing-kern.md`); beide Seiten
bleiben stehen, §15m kommt hinter §15k und §15l.

- **`Operator.method` (Pflichtfeld aus M4-19a).** `mask` und `normalize` haben ihre Sätze:
  - `mask`: „Pixels were hidden in every band where the classification layer scl held class
    3, 8, 9, 10 or had no value; the layer itself was left out.“
  - `normalize`: „Every band was mapped linearly from the range 0 to 0.5 onto the range 0 to
    255, values outside the source range limited to the target range, in 32-bit floating
    point.“ (bei `clip=false`: „continued along the same line“).
  
  Der Wächtertest `TestEveryOperatorSaysItsStep` hat Beispielparameter für beide und
  bestätigt, dass jeder Satz mit Punkt endet und keinen Platzhalter trägt.
- **Faktoren nach dem Statistik-Durchgang (`adr/0014` §15k).** Otto hat am 22.10.2026 die Regel
  gesetzt: Jeder Faktor eines Laufs, der den Statistik-Durchgang durchläuft, bekommt dessen
  gemessenen Zuschlag und wird auf eine Nachkommastelle aufgerundet. Beide neuen Operatoren
  laufen im selben Durchgang wie Band-Math und bekommen dessen Zuschlag von +12,1 %: `mask`
  0,1 → **0,2**, `normalize` 0,2 → **0,3**. Das ist die Anwendung der Regel auf Faktoren,
  die in der Tabelle von §15k noch nicht stehen; eine eigene Messung des Zuschlags für diese
  beiden Operatoren gibt es nicht.
- **Speicher** mit dem Statistik-Durchgang neu gemessen (§10 Punkt 3a): unverändert unter den
  Grenzen.
- **Frontend-Fixtures** nach dem Merge neu erzeugt: kein Unterschied.

---

## 12. Umsetzung von M4-18b (22.10.2026)

Kette von Operatoren in der Kachel und Vorschau des längsten T1-Anfangs (F1, §3.4, §8); ohne das
Formular der Maske (M4-18c). Keine neue Abhängigkeit, `.github/`, `.claude/`, `CLAUDE.md` und
`.importlinter` unberührt.

**Geliefert:**
- **`api/tiler.py`:** `op`, `op_version` und `params` dürfen in der Kachel-URL wiederholt werden, gleich
  oft und in der Reihenfolge der Schritte, höchstens 4 (`MAX_OPERATOR_STEPS`). Ungleich oft oder mehr als 4:
  `400`. Jeder Schritt wird für sich geprüft (bekannte Version, `T1` und `pixel`, Parameter strikt,
  `applicable` mit `dataset_check`), vor dem Abruf des Items; ab zwei Schritten beginnt die Meldung mit
  „step n: “ (n ab 0, wie in der Annahme). Die Form mit einem Operator ist der Fall n = 1, ihre Meldungen sind unverändert.
  `OperatorInput` trägt jetzt `steps` statt `operator` und `params`; `operator_post_process` ruft die
  Kerne nacheinander.
- **`processing/tile.py`:** Der Reader lässt `transform` der Reihe nach über die Bänder laufen, vor dem
  ersten Pixel: ein Schritt, der ein Band nennt, das der vorige entfernt hat (die Schicht nach `mask`),
  wird mit `422` abgewiesen, wie im Auftrag; die Meldung nennt den Schritt.
- **Frontend:** `planPreview` plant den längsten Anfang aus Kachel-Schritten (höchstens 4, wie der
  `tiler`); ein unvollständiger oder nicht zeichenbarer Schritt beendet ihn. Ist schon der erste nicht
  zeichenbar, bleibt es bei „No preview: the first step runs only as a job.“, ist er unvollständig, bei
  „Complete the step …“. `buildOperatorTileTemplate` nimmt eine Liste von Schritten; der Titel der Vorschau
  verbindet die Titel („Band math → Normalize“); der Hinweis unter der Vorschau nennt die Zahl der gezeigten
  Schritte (`furtherNote`).

**Tests (neu):**
- `tests/earthx/api/test_tiler_chain.py`: Kachel gleich Job auf der nativen Ebene für `mask → band_math`,
  `mask → normalize`, `mask → band_math → normalize` und `normalize → band_math` (COG-Paar mit
  20-m-Schicht; `numpy.array_equal` über die gültigen Pixel, gleiche Masken, alle Bänder); `mask → band_math`
  auf dem CF-Mini-Zarr nach der Regel von `adr/0014` §15d (Kachel gegen die Formel auf dem nächsten
  Quellpixel beider Raster; Job gegen Kachel überall außer innerhalb von 0,125 Quellpixel einer Grenze);
  die Maske des ersten Schritts erreicht den Index des zweiten; die Reihenfolge der URL ist die der
  Schritte. Abweisungen: fünf Schritte, ungleich oft, Schritt ohne Kachel (`reproject`), unbekannte
  Version, Parameter eines späteren Schritts, zu lange Parameter, Datensatz ohne Maske und falsche
  Schicht (beide ohne Abruf des Items), ein Band, das der erste Schritt entfernt hat, zweite Maske,
  fehlende Schicht im Auftrag; TileJSON trägt die Kette; `statistics` und `info` weisen sie ab.
- Frontend: `processingPreview.test.ts` (Anfang, Reihenfolge, Ende an einem unvollständigen und an einem
  nicht zeichenbaren Schritt, Obergrenze, URL mit wiederholten Parametern, Schlüssel je Reihenfolge) und
  `ProcessingPreview.test.tsx` (Kette in der Vorschau, Hinweis).

**Nicht Teil von M4-18b** (bleibt M4-18c): Das Panel zeigt `mask` weiter als „not supported by this
panel“, also kann es `mask` im Anfang nicht zeichnen. Die Kette `mask → band_math` ist auf der Route
und im Vergleich belegt, aber im Panel erst mit dem Formular erreichbar; das Asset der Schicht kommt mit
M4-18c in den Auftrag.

**Kette mit einem Band, das ein früherer Schritt entfernt hat (Otto, 22.10.2026):** Das Panel baut die Bandlogik nicht
nach. Hat die Vorschau mindestens zwei Schritte, fragt es das TileJSON derselben Kette der ersten Szene (`buildOperatorTileJsonUrl`,
`probeChain`); der Reader des `tiler` prüft dort jeden Schritt auf den Bändern des vorigen und antwortet mit `422`, dessen Text
mit `step <n>: ` beginnt (`processing/tile.py`). Das Panel zeigt dann die Schritte davor und den Grund aus der Antwort:
„Preview shows step 1 of 2. Step 2: expression names unknown band(s): red; the input has: band_math.“ Trifft es den ersten
Schritt, steht „No preview. Step 1: …“ und keine Karte. Eine Antwort ohne Schritt (Quelle nicht erreichbar, `5xx`) lässt die ganze
Kette stehen; ein Schritt allein wird nicht gefragt. Gemerkt wird nur eine Ablehnung, bis das Panel nichts mehr zeigt.
- **Zählung:** `step <n>` zählt wie alle Ablehnungen der Annahme ab 0 (`processing/recipe.py`, `api/intake.py`,
  `stepOfRefusal`): der zweite Schritt heißt `step 1`. So findet das Panel den Schritt für „Review“; nur der Hinweistext
  rechnet auf „Step 2“ um.
- **Annahme:** `plan.check_bands` setzt dasselbe `step <n>: ` vor die Ablehnung, wenn der Auftrag mehr als einen Schritt hat. „Review“
  (`/estimate`) und „Start“ (`/execution`) weisen denselben Auftrag mit `422` (`urn:earthx:order-refused:applicable`) und diesem
  Grund ab; nichts kommt in die Warteschlange (`TestAChainThatNamesABandAnEarlierStepRemoved` in `test_processing_route.py`). Das Panel
  zeigt die Ablehnung am Schritt und sperrt „Start job“ (`ProcessingPanel.test.tsx`).

**Nach dem Review:** Ziffern anderer Schriften in `op_version` werden mit `400` abgewiesen, bevor das Item geholt wird (vorher
las `int()` sie, und FastAPI wies sie danach mit `422` ab); `tests/earthx/api/test_tiler_chain.py` prüft das, leere Teile und die
Reihenfolge der Schritte mit einer Kette, deren Reihenfolge die Werte ändert. Die Obergrenze 4 steht im Backend
(`MAX_OPERATOR_STEPS`) und im Frontend (`MAX_PREVIEW_STEPS`) je einmal; kein Test bindet beide aneinander.
`NO_PREVIEW` sagt für `mask` als ersten Schritt „runs only as a job“, bis M4-18c das Formular bringt (behoben in M4-18c, §13).

**Nummer des Schritts:** In den Meldungen der Kachel und der Annahme steht `step 0:` für den ersten Schritt; die erste
Fassung dieses Abschnitts zählte ab 1 und hätte im Panel am falschen Schritt gehangen. Die Tests oben nennen die Zählung ab 0.

---

## 13. Umsetzung von M4-18c (22.10.2026)

Panel für die Maske (F6, §3.5) und die Berichtigung der Vorschau-Meldung aus M4-18b. Nur Frontend; kein Backend,
keine neue Abhängigkeit, `.github/`, `.claude/`, `CLAUDE.md` und `.importlinter` unberührt.

**Geliefert:**
- **Listenfeld im Schema-Formular (`schemaForm.ts`):** Ein Parameter vom Typ `array` mit ganzzahligen `items`
  (`minimum`, `maximum`) und `minItems`/`maxItems` ist das Feld `integers`, bearbeitet als Text („3, 8, 9, 10“). Gesendet
  wird aufsteigend und ohne Doppel, weil die Annahme jede andere Schreibweise derselben Liste abweist (K3). Jede andere
  Form eines Arrays bleibt „not supported by this panel“.
- **`earthx:mask` lesen (`processingOrder.ts::maskLayerOf`):** Nur ein vollständiger Eintrag zählt; Vorschläge, die nicht in
  der Tabelle stehen, fallen weg, und `reference` bleibt nur bei `https://`, weil das Panel dorthin verlinkt.
  Hat der Datensatz keine Schicht, bleibt das Schema-Formular (zwei Textfelder).
- **Formular „Classes to hide“ (`StepForm.tsx`):** ein Kästchen je Klasse mit Wert und Name aus der Registry, die
  vorgeschlagenen (`suggested`) bei „Add step“ angekreuzt und als „(suggested)“ gekennzeichnet; das Rezept nennt genau die
  angekreuzten Klassen (K6). `source` ist kein Feld: Es kommt aus `earthx:mask.band` und steht im neuen Schritt. Unter den
  Kästchen stehen der Hinweis der Registry zu älteren Prozessierungsbasen (Auflage in §8), der Verweis auf die Klassentabelle
  und der Satz, dass die Schicht gelesen und nicht ins Ergebnis übernommen wird.
- **Die Schicht im Auftrag:** Solange ein `mask`-Schritt im Auftrag steht, nimmt `orderView` das Asset aus
  `earthx:mask.asset` in `assets` auf (`orderAssets`, vierter Parameter), ohne dass der Nutzer es wählt, und nur, wenn die
  Szene es kennt. Der Chip der Schicht ist gedrückt und lässt sich nicht abwählen, solange der Schritt da ist; sein Hinweis
  sagt warum. Bei „Review“ steht „The order also reads the mask layer scl; it is not in the result.“, oder, fehlt das Asset
  in der Szene, ein Fehlertext (der Server weist den Auftrag auch dann ab, `check_bands`). Das Panel ergänzt sonst nichts.
- **Ausgabetyp:** Die Schicht (`uint8`) geht nicht in die Wahl des Datentyps ein, weil das Ergebnis sie weglässt; sonst
  hätte sie jede Maske auf `uint16`-Bändern auf `float32` gezwungen.
- **Vorschau:** Ein `mask` als erster Schritt wird gezeichnet (T1, `pixel`, Formular da); `scl` steht in den `asset`-Parametern
  der Kachel-URL. Die Kette `mask → band_math` ist damit im Panel erreichbar (M4-18b hatte sie nur auf der Route belegt).

**Berichtigung aus M4-18b (#175), `NO_PREVIEW`:** Der Text „No preview: the first step runs only as a job.“ erschien für jeden
ersten Schritt, den das Panel nicht zeichnen konnte, auch für `mask`, das als Kachel läuft und nur kein Formular hatte.
`tileStep` nennt jetzt den Grund, und `planPreview` zeigt je Grund einen Text: `NO_PREVIEW` nur für Schritte, die wirklich
nicht als Kachel laufen (nicht `T1` oder nicht `pixel`), `NO_PREVIEW_FORM` („this panel has no form for the first step yet“)
für einen Kachel-Schritt ohne Formular, `NO_PREVIEW_UNLISTED` für einen Schritt, den der Datensatz nicht aufführt. Mit dem
Formular wird `mask` ohnehin gezeichnet; die Texte bleiben für den nächsten Operator ohne Formular richtig. Die alten Tests
nannten Reproject v2, das die Fixtures nicht aufführen (nur v3): Sie bestanden, weil „nicht aufgeführt“ denselben Text
bekam wie „nur als Job“. Sie nehmen v3 und prüfen beide Gründe getrennt.

**Tests (neu):**
- `schemaForm.test.ts`: Listenfeld lesen, aufsteigend ohne Doppel, leer, Nicht-Zahlen (`1.5`, `1e2`, `0x10`, Ziffern anderer
  Schriften), Grenzen je Wert und der Liste, zu große Zahl, Vorgabe, Formen, die nicht unterstützt bleiben.
- `processingOrder.test.ts`: `maskLayerOf` (acht kaputte Formen, nur `https`, Vorschläge nur aus der Tabelle),
  `maskStepValues`, `maskAssetOf`, `orderAssets` mit nötigem Asset, die Schicht unter den Variablen eines Zarr-Items.
- `processingPreview.test.ts`: `mask` als erster Schritt mit Parametern, Reihenfolge der Klassen, unvollständige Maske,
  die drei Gründe getrennt; die Fixtures-Prüfung verlangt jetzt für jeden Operator ein Formular.
- `components/ProcessingMask.test.tsx` (20): Kästchen mit Namen und Vorbelegung, kein Feld für `source`, Hinweis und Link, die
  angekreuzten Klassen im gesendeten Auftrag (aufsteigend), keine Klasse → kein Auftrag, Rückfall ohne `earthx:mask`, die
  Schicht im Auftrag und ihr Chip, Hinweis bei fehlender Schicht, Datentyp ohne die Schicht (Gegenprobe: ohne die Ausnahme
  schlägt der Test fehl), Vorschau von `mask` und `mask → band_math` mit den Assets in der URL, Reproject bleibt „only as a job“.

**Datentyp nach `normalize` (Otto, 22.10.2026, in M4-18c behoben):** `chooseDtype`, `dtypeOptions` und `integerNote` kannten nur
`band_math` als Schritt, der in `float32` mit NaN endet. Auf ganzzahligen, unskalierten Bändern mit nodata schlug das Panel
deshalb für `normalize` den Quelltyp vor, den der Lauf ablehnt (`core._nodata_for`). Die Prozessbeschreibung liefert keinen
Ausgabetyp je Operator (nur `x-earthx-tiers` und `x-earthx-kind`); deshalb steht `normalize` wie `band_math` in einer kleinen
Tabelle in `processingDefaults.ts` (`FLOAT_RESULT`): Empfehlung `float32` („Normalize gives fractions.“), Ganzzahltypen nicht
angeboten („not after normalize“), kein Hinweis zu nodata. Sind beide im Auftrag, nennt die Meldung den ersten. `mask` allein
behält den Quelltyp. Der Test mit ganzzahligen, unskalierten Bändern mit nodata (`processingDefaults.test.ts`, dazu im Panel
`ProcessingMask.test.tsx`) schlug vor der Änderung fehl (vier Tests). Ein Feld „Ausgabetyp“ in der Beschreibung wäre der
saubere Weg, brauchte aber eine Änderung in `api/processing_docs.py`; sie ist nicht gemacht.

**Grund, wenn `mask` nicht angeboten wird:** Das Panel zeigt unter den Schritten „Mask: this dataset has no classification layer
to read.“, wenn der Datensatz keine Schicht (`earthx:mask`) hat und `mask` nicht in der Beschreibung steht (DEM). Vorher fehlte
der Knopf ohne Text.

**Prüfanleitung im Browser (Otto):** Die Darstellung ist nur in jsdom getestet. Zu prüfen, mit laufendem Stack (`docker compose up`):
1. Sentinel-2 L2A (COG): eine Szene wählen, „Process“ öffnen, „＋ Mask“. Erwartet: „Classes to hide“ mit zwölf Klassen, 3, 8, 9
   und 10 angekreuzt, Klassentabelle verlinkt, Hinweis zu älteren Prozessierungsbasen; Chip `scl` gedrückt und nicht abwählbar.
2. „＋ Band math“, `(nir - red) / (nir + red)`. Erwartet: Vorschau auf der Karte mit „Mask → Band math“, Wolken, Schatten und
   Zirrus als leere Stellen (nicht als Werte); bei Szenen ohne Wolken ist kein Unterschied zu sehen, dann eine bewölkte nehmen.
   Dann Klasse 6 (Wasser) ankreuzen: Wasser wird leer.
3. „Review“. Erwartet: „The order also reads the mask layer scl; it is not in the result.“ und eine Schätzung. „Start job“, das
   Ergebnis hat keine Bänder `scl` und dieselben leeren Stellen wie die Vorschau (bis auf die Stellen aus §3.6, wo Kachel und Job
   an Rastergrenzen abweichen dürfen).
4. EOPF-Zarr, falls als Datensatz da (`sentinel-2-l2a-zarr3`): dasselbe mit dem Asset `SCL_20m:scl`; der Chip heißt so. Das ist die
   offene Stelle aus Befund 2: Sie bestätigt, dass die Variable in echten Items so heißt.
5. DEM (`cop-dem-glo-30`): kein „＋ Mask“, darunter der Satz „Mask: this dataset has no classification layer to read.“; „＋ Normalize“
   und „＋ Band math“ sind da. Danach auf einer Szene „＋ Normalize“: Datentyp `float32`, Ganzzahltypen mit „(not after normalize)“.

**Befunde, nicht in dieser Aufgabe:**
1. **Nicht gegen echte Items geprüft.** Dass `SCL_20m:scl` aus einem echten EOPF-Item als Quelle entsteht, ist aus §2 [M]
   (Asset `SCL_20m`, Band `scl`) und einem synthetischen Item belegt, nicht aus einem Abruf in dieser Sitzung.
2. **Im Browser nicht gesehen.** Die Darstellung (`.pp-classes`) ist in jsdom getestet, nicht gerendert und angeschaut; die
   Prüfanleitung oben und im PR ist dafür da.
