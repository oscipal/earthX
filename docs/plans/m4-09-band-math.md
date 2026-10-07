# M4-09 — Operator Band-Math (T1, T2): Plan

**Aufgabe:** M4-09 aus `docs/plans/m4-processing-kern.md` §4.
**Stufe B** (R1) — **von Otto am 07.10.2026 freigegeben** mit F1–F5 je Option 1
und Auflagen zu F2, F3, F4 (§8). Umsetzung siehe §9. Wo §3 und §8 sich
widersprechen, gilt §8.
**Ort im Repo:** `docs/plans/m4-09-band-math.md`
**Grundlagen:** `adr/0014` §3.2, §3.3, §5.2–§5.6, §6.1–§6.4, §15a (F7, F7a,
F9), §15c; `adr/0016` §3.3, §12a, §14.4, §14.5; `plans/m4-processing-kern.md`
§1.1b (R1, R5), §1.2, M4-09; `plans/m4-07a-processing-kern.md` §3, §8 (F2);
`plans/m4-07b-annahme.md` §3.4; `adr/0006` §5; `adr/0001` Z4; `KLAERUNGEN.md`
B8–B11. Code in `processing/core.py`, `processing/scaling.py`,
`processing/operators/`, `api/tiler.py`, `api/intake.py`, `access/tiles.py`,
`readers/zarr_reader.py`; rio-tiler 9.4.6 (`expression.py`, `models.py`),
titiler.core 2.3.0, numexpr 2.14.2, numpy 2.5.3.

---

## 1. Ergebnis in drei Sätzen

Ein Operator `band_math` (`kind="pixel"`, `tiers={T1, T2}`, `op_version` 1)
rechnet einen Ausdruck über die Bänder einer Eingabe in physikalischen Werten
zu einem `float32`-Band mit Nodata; sein Parametermodell prüft den Ausdruck nach
R5, bevor numexpr ihn sieht. Der `tiler` bekommt eine Pfad-Abhängigkeit für
mehrere Assets eines Items und einen eigenen `process_dependency`, sodass eine
Kachel-URL mit `op`, `op_version` und `params` denselben Kern mit derselben
Skalierung rechnet wie der Job. Ein Vergleichstest zeigt T1 gegen T2 bitgleich
auf der nativen Ebene (COG mit Skalierung und Offset, Mini-Zarr mit
CF-Attributen), ein zweiter zeigt jede erlaubte Funktion unter den
Einstellungen A und D aus `adr/0016` §3.3 mit denselben Bytes.

---

## 2. Stand vor dieser Aufgabe (gelesen, 07.10.2026, `main` nach PR #124)

- **Registry (M4-07a, M4-10):** `processing/operators/registry.py` hält nur
  `REPROJECT`; der Kommentar dort nennt M4-09 als nächsten Eintrag. `Operator`
  hat `params`, `requires`, `tiers`, `kind`, `cost_factor`, `transform`, `run`,
  `lineage`, `extra_requirements`. Alle drei Datensätze setzen
  `capabilities.band_math=True` (`datasets.py` Z. 87, 271, 469).
- **Kern (`processing/core.py`):** Ein `pixel`-Abschnitt liest je Block jedes
  Asset mit `part()` im eigenen Raster, wendet `apply_scaling` an, fügt die
  Bänder zusammen (`_merge`, Bandname = Asset-Schlüssel bzw. Zarr-Variable) und
  ruft die Kerne. Assets mit verschiedenem Raster → `GridMismatch` mit dem Text
  „resampling them comes with M4-09“ (Ottos Auflage F2 zu M4-07a: „Bänder
  verschiedener Auflösung ergänzt M4-09“).
- **Skalierung (`processing/scaling.py`):** `scaling_for_cog`,
  `scaling_for_zarr`, `apply_scaling` nach §5.4 und F7a; ausdrücklich dafür
  gebaut, dass T1 dieselbe Funktion aufruft. Die Logik, die je Asset Reader,
  Skalierung und Bandnamen zusammenbringt, steckt heute privat in
  `core._Source`.
- **Annahme (`api/intake.py`, M4-07b):** `_bands_of` und `_scaling_of` leiten
  Bandangaben und Skalierungsquelle aus dem Item ab; `_check_steps` prüft
  Operator, Stufe T2 und `applicable` (Abweisung `422`, Stufe `applicable`).
- **Kachel-Pfad heute (`api/tiler.py`, `access/tiles.py`):**
  - `dataset_asset_path` nimmt genau ein `asset` aus der Query.
  - `EarthxTilerFactory` lässt `layer_dependency` und `process_dependency` auf
    TiTilers Vorgaben: **`BidxExprParams` nimmt einen freien Parameter
    `expression`, und `Algorithms` nimmt `algorithm` und `algorithm_params`**
    [P, gelesen an `TilerFactory.__attrs_attrs__`]. Ein solcher Ausdruck geht
    heute ohne R5 an numexpr, rechnet auf Rohwerten (DN, ohne Skalierung des
    Items) und ist durch rio-tilers eigene Prüfung begrenzt, die jede
    numexpr-Funktion erlaubt (`rio_tiler/expression.py` Z. 31–48, auch `log`,
    `exp`, `sin`).
  - Das Frontend setzt `expression` nur, wenn die Registry in
    `default_render.expression` einen Ausdruck trägt (`render.ts` Z. 33,
    `mapLayers.ts` Z. 208); alle drei Einträge tragen `None`.
- **rio-tilers Band-Math [P]:** `ImageData.apply_expression` schreibt den
  Ausdruck klein (`get_expression_blocks`, Z. 92), rechnet mit
  `numexpr.evaluate` ohne `optimization`-Angabe und ersetzt das Ergebnis mit
  `numpy.nan_to_num` (`0/0` → `0.0`, `±inf` → `±1,8·10³⁰⁸`).

**Messungen dieser Sitzung [M]** (Skripte im Scratchpad, je auf festen
Zufallsdaten 2048², x86_64 mit AVX-512; 0 Anfragen an Datenquellen):

| Prüfung | Ergebnis |
|---|---|
| `GLIBC_TUNABLES=glibc.cpu.hwcaps=-AVX2,-FMA,-AVX512F,…` wirkt in der Sitzung | ja: `ld.so --list-diagnostics` zeigt `0x7ed83203` → `0x7ed82203` (FMA-Bit weg), wie `adr/0016` §14.4 |
| Einstellung A gegen D, numexpr mit `optimization="aggressive"`, float32 und float64: NDVI, `where`+Vergleich, `abs`, `minimum`, `maximum`, `sqrt`, `x**2`, `x**3`, `x**7`, `x**-2`, `x**50` | **gleich** in allen 22 Fällen |
| dasselbe für `x**51` (float64), `log`, `exp` (float64), `x**1.7` | **anders** (wie `adr/0016` §3.3, §12a) |
| Rechentyp bei float32-Eingaben | bleibt float32 für Grundrechenarten, `where`, `abs`, `sqrt`, ganzzahlige Potenzen; wird **float64** bei `minimum`/`maximum` und gebrochenen Potenzen |
| Zeit NDVI je Block 1024², 1 Aufruf | float32 0,98 ms, float64 1,04 ms, Umwandlung beider Bänder nach float64 1,1–1,2 ms; gegen 146 ms je Megapixel für einen ganzen Band-Math-Lauf (`adr/0014` §3.5) vernachlässigbar |
| Kachel eines 20-m-COG gegen Kachel desselben Inhalts, mit `nearest` auf 10 m verdoppelt (gleicher Ursprung), rio-tiler `Reader.tile`, `nearest` | **100 % gleich** auf z13 (56 Kacheln, 2,9 Mio. Pixel), z14 (182, 11,3 Mio.), z15 (675, 43,7 Mio.) |

---

## 3. Umsetzung

### 3.1 Operator `processing/operators/band_math.py`

**Parameter (`BandMathParams`, strikt, `extra="forbid"`, eingefroren):**
- `expression: str`, 1–256 Zeichen, nur ASCII (R5). Ein Ausdruck ergibt ein
  Band; `;` (rio-tilers Trenner für mehrere Bänder) ist abgewiesen (K2).
- Keine weiteren Felder in `op_version` 1.

**Prüfung des Ausdrucks im Modell (R5, eingeengt; `adr/0014` §15c),** über
`ast.parse(mode="eval")` und eine Positivliste der Knoten:

| erlaubt | Bedingung |
|---|---|
| Namen | gültige Python-Bezeichner, keine numexpr-Funktion, kein Schlüsselwort; Groß- und Kleinschreibung bleibt (K4). Ob sie Bänder der Eingabe sind, prüft §3.3 |
| Zahlen | `int` oder `float`, endlich; kein `bool`, `complex`, Text (K5) |
| `+ - * /`, einstelliges `-` und `+` | — |
| `**` | Exponent ist eine ganze Zahl als Literal, auch mit einstelligem `-`, \|n\| ≤ 50 (K5) |
| Vergleiche `< <= > >= == !=` | — |
| Aufrufe | nur `where(c, a, b)`, `abs(x)`, `minimum(a, b)`, `maximum(a, b)`, `sqrt(x)`, mit genau dieser Zahl von Argumenten, Name direkt (kein Attribut) |
| `& \| ~` | **nur nach F4** |

Alles andere wird abgewiesen: Attribute, Indizes, Lambdas, Schlüsselwortargumente,
`%`, `//`, Bitverschiebungen, jede andere Funktion — ausdrücklich `log`, `exp`,
Winkelfunktionen und `x**0.5`. Die Fehlermeldung nennt Knoten oder Namen, nie
den ganzen Ausdruck.

**Kern (`run(image, params) -> ImageData`), nach F1:**
- Eingaben als float64, `numexpr.evaluate(expr, local_dict=…,
  optimization="aggressive", truediv=True, sanitize=True)`, Ergebnis float32.
  numexprs eigene Prüfung (`sanitize`) bleibt als zweite Linie hinter R5.
- Maske = ODER der Bandmasken (wie rio-tiler, `models.py` Z. 710), dazu nach
  F1 jedes nicht endliche Ergebnis (`0/0`, `x/0`).
- Nodata des Ergebnisbands: NaN (der Kern schreibt float-Ausgaben schon so,
  `core._nodata_for`).
- Ein bool-Ergebnis (`red > 0.1`) wird 1.0/0.0.

**Weitere Felder des Eintrags:**
- `requires`: `band_math`, alle Datenklassen, Lizenzstufe *Processing*;
  `extra_requirements` keine.
- `cost_factor` 1,0 (`adr/0014` §5.5).
- `transform`: ein Band `band_math`, `float32`, Nodata NaN, Einheit keine;
  prüft die Namen gegen die Bänder des `RasterMeta` (§3.3) und kompiliert den
  Ausdruck einmal mit `numexpr.validate` gegen Platzhalter (K6). Fehler →
  `InvalidParams` bzw. `UnsupportedRecipe`, bevor ein Block gelesen ist.
- `lineage`: „band math: <Ausdruck>“; `RunResult.properties` bekommt
  `processing:expression` = `{"format": "numexpr", "expression": …}` (K1).
- Registriert in `REGISTRY`; Export in `operators/__init__.py`.

### 3.2 Gemeinsames Lesen in physikalischen Werten (T1 und T2)

Damit T1 und T2 nicht zwei Wege haben, zieht die heutige Klasse `core._Source`
(Reader, Skalierung nach §5.4, Bandnamen, Datentypen, Nodata) in ein Modul
`processing/source.py` und wird öffentlich. Der Kern nutzt sie wie bisher; der
`tiler` liest damit Kacheln statt Blöcke. Neu darin:

- **Bandnamen** an einer Stelle: einbandiges COG → Asset-Schlüssel,
  mehrbandiges → `<asset>_<i>`, Zarr → Variablenname (heute so im Kern).
- **Gemeinsames Raster nach F2.** Mit Option 1: Haben die Assets dasselbe CRS,
  ganzzahlige Verhältnisse der Pixelgrößen und Ursprünge auf dem Raster des
  gröbsten Assets, liest der Kern die gröberen Assets mit `nearest` auf das
  feinste Raster (reine Verdopplung, §2 Messung). Das Ergebnis trägt
  `earthx:resampled=true` (Prinzip 2.9). Andernfalls bleibt es bei
  `GridMismatch` mit neuem Text. Der Text in `core.py` Z. 26 und Z. 230 wird
  angepasst.

### 3.3 Bandnamen gegen die Eingabe prüfen

Das Parametermodell kennt die Eingabe nicht; die Namen prüft:
- **T2:** `transform` beim Start des Laufs, gegen die Bandnamen aus §3.2,
  bevor der erste Block gelesen wird (verbindlich).
- **Annahme (`api/intake.py`):** `_check_steps` prüft zusätzlich gegen die
  Namen, die sich aus dem Auftrag ableiten lassen (Asset-Schlüssel,
  Zarr-Variablen; bei mehrbandigen COGs nur, wenn das Item die Zahl der Bänder
  nennt) → `422`, Stufe `applicable`. Ein Rezept mit unbekanntem Namen kommt
  so nicht in die Queue.
- **T1:** die Abhängigkeit aus §3.4, gegen die Assets der URL → `422`.

### 3.4 Kachel-Pfad (T1, `adr/0014` §6.2)

**URL (K3):** `…/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=red&asset=nir&op=band_math&op_version=1&params=<JSON>`
- `asset` darf wiederholt werden (höchstens 16, wie `MAX_ORDER_ASSETS`), aber
  nur zusammen mit `op`; mehrere Assets ohne `op` → `400`. Ohne `op` bleibt
  alles wie heute (ein Asset, DN, Standard-Visualisierung).
- `params` ist JSON im Query-Parameter, geprüft mit demselben Modell wie im
  Rezept (`strict`). Keine Rezept-Kennung, kein Hash, keine AOI (Q8).
- Nur `tile` und `tilejson` nehmen `op`. `statistics`, `info` und `point`
  weisen `op` und mehrere Assets mit `400` ab; Statistik eines Ergebnisses
  kommt, falls das Panel sie braucht, mit M4-13.

**Bausteine:**
- `api/tiler.py`: `dataset_asset_path` wird zu einer Abhängigkeit, die ein
  Asset wie heute oder, mit `op`, eine `OperatorInput` liefert: je Asset die
  geprüfte `AssetPath`/`ZarrAsset` (für Skalierung `item` bei Zarr mit
  `decode_cf=False`), Bandangaben und Skalierungsquelle. Diese kommen aus
  denselben Funktionen wie in der Annahme: `_bands_of` und `_scaling_of` in
  `api/intake.py` werden öffentlich und von beiden genutzt.
- Vor dem Abruf des Items: Operator bekannt, T1 in `tiers`, Parameter gültig,
  `applicable(operator, config, params)` (sonst `422`, wie die Annahme). Ein
  abgewiesener Auftrag kostet keine Anfrage an die Quelle.
- `processing/tile.py` (neu): ein Reader für `OperatorInput` auf Grundlage von
  rio-tilers `MultiBaseReader` (gibt das `Env` je Asset weiter,
  `@inherit_rasterio_env`, `adr/0014` §3.6). `tile()` liest je Asset die
  Kachel mit derselben `source.py`-Logik (Skalierung, Namen, Rasterregel aus
  F2), fügt die Bänder wie der Kern zusammen und gibt ein `ImageData` zurück.
- `process_dependency`: liest `op`, `op_version`, `params` aus der Query und
  ruft `operator.run(image, params)` — dieselbe Funktion wie der Kern. Ohne
  `op` gibt er das Bild unverändert zurück.
- `reader` der Fabrik: eine kleine Weiche in `api/tiler.py`
  (`OperatorInput` → `processing.tile`, sonst `access.tiles.open_asset`).
  `access` importiert nichts aus `processing` (§6.2, `.importlinter`
  unverändert).
- **Freie Ausdrücke im `tiler` nach F3.** Mit Option 1: `layer_dependency`
  nimmt nur noch `bidx`; `expression`, `algorithm` und `algorithm_params`
  werden mit `400` abgewiesen, der Text verweist auf `op=band_math`. Die
  Registry weist `default_render.expression` ungleich `None` beim Laden ab,
  bis M4-13 die Standard-Visualisierung auf `op` abbildet. Das Frontend bleibt
  unverändert (es setzt `expression` nur aus der Registry).

### 3.5 Tests

Fixtures nur synthetisch, alle Quellen über `tests/fixtures` bzw. die
vorhandenen Umlenkungen (`tests/earthx/processing/sources.py`,
`readers/mini_zarr*.py`).

- **R5 (Parametermodell):** erlaubte Ausdrücke (NDVI, `where` mit Vergleich,
  `abs`, `minimum`, `maximum`, `sqrt`, `x**2`, `x**-3`, `x**50`, Konstanten mit
  Exponent `1e-4`); abgewiesen: unbekannte Funktionen (`log`, `exp`, `sin`,
  `arctan2`, `copy`), Attribute (`red.real`, `__class__`), Aufrufe über
  Attribute, Indizes, Lambdas, Schlüsselwortargumente, `%`, `//`, `<<`,
  `x**51`, `x**-51`, `x**0.5`, `x**y`, `x**(1+1)`, `True`,
  `1j`, Text, 257 Zeichen, Nicht-ASCII, `;`, leerer Ausdruck, falsche Zahl von
  Argumenten, Bandname gleich Funktionsname. Dazu: das JSON Schema enthält
  kein `pattern` (§5.1).
- **Kern:** NDVI auf bekannten Rampen gegen eine Formel; `0/0` und `x/0`
  nach F1; Maske als ODER; bool-Ergebnis; float32-Ausgabe; unbekannter Name
  → Fehler vor dem ersten Block.
- **Skalierung (Auflage F7):** synthetisches Item mit `raster:bands`
  (Skalierung, Offset, Nodata) → physikalische Werte in T1 und T2; Abweichung
  Item gegen Datei → `ScalingMismatch` in T1 (`502`) und T2.
- **Fehlende Capability und Lizenz:** Datensatz mit `band_math=False` bzw.
  Stufe *Display* → `422` in Kachel und Annahme; kein Abruf des Items.
- **Kachel-Route:** mehrere Assets ohne `op` → `400`; `expression`,
  `algorithm` → `400` (F3); `op` an `statistics`/`info`/`point` → `400`;
  unbekannter Operator, `op_version` 2, ungültiges JSON in `params`,
  Zusatzfelder → `422`; ein Host außerhalb `asset_hosts` → `502` wie heute;
  die OpenAPI hat weiter keinen freien `url`-Parameter.
- **Vergleich T1 ↔ T2 (§6.4, Abnahme):** COG-Paar `uint16` mit
  `scale`/`offset` (Rampen aus `sources.py`), Mini-Zarr mit CF-Attributen
  (`mini_zarr_cf.py`); T1 über die echte Route mit `TestClient`, `nearest`;
  T2 über `processing.run`, das Ergebnis mit rio-tilers `Reader.tile` und
  `nearest` auf dieselben Kacheln gebracht. `numpy.array_equal` über gültige
  Pixel, Masken gleich, auf einer Zoomstufe der nativen Ebene. Mit F2 Option 1
  zusätzlich ein Paar 10 m / 20 m.
- **Bitstabilität über CPU-Stufen (`adr/0016` §12a, K7):** ein Kindprozess
  rechnet jede erlaubte Funktion und die Potenzen 2, 3, 7, −2, 50 über den
  Kern auf festen Daten und gibt SHA-256 aus; einmal mit Einstellung A, einmal
  mit D (`NPY_DISABLE_CPU_FEATURES`, `GLIBC_TUNABLES`). Gleiche Bytes
  verlangt. Wirkt `GLIBC_TUNABLES` nicht (kein glibc, Prüfung über
  `ld.so --list-diagnostics`), wird der Test mit Grund übersprungen, nie still.
- **Bestehende Tests** zu Kachel, Zarr-Kachel, TileJSON, Statistik, Download
  und Kern bleiben grün; `test_core_run.py` bekommt den neuen
  `GridMismatch`-Fall nach F2.

### 3.6 Doku und Log

- `ENTSCHEIDUNGSLOG.md`: Freigabe (F1–F5, K1–K8) und Umsetzung je eine Zeile
  am Ende.
- `plans/m4-processing-kern.md` §3: Stand von M4-09.
- `adr/0014` bleibt unverändert; Abweichungen von §5.2 (eigener Kern statt
  `apply_expression`, F1) und §5.6 (`format`, K1) stehen in der Log-Zeile.

---

## 4. Nicht in dieser Aufgabe

- `log`, `exp`, Winkelfunktionen, gebrochene Potenzen (R5, später mit eigener
  Toleranz in ULP).
- Mehrere Ausgabebänder je Schritt; benannte Ausgabebänder.
- Statistik, Info und Punktabfrage eines Band-Math-Ergebnisses (M4-13, falls
  nötig).
- Panel, Kennzeichnung „Preview“ auf Übersichtsstufen, Abbildung von
  `default_render.expression` auf `op` (M4-13).
- Mosaik mehrerer Items (M4-11, M4-12, M4-17).
- `.importlinter`, `gateway`, `jobs`, `objectstore`, `datasets/`, Frontend,
  `.github/`.

---

## 5. Umfang und Commits

Geschätzt rund 450 Zeilen Code (`band_math.py` 170, `source.py` mit
Rasterregel 120 davon 70 umgezogen, `tile.py` 90, `api/tiler.py` 100,
`api/intake.py` 20, Registry-Prüfung 10) und 600 Zeilen Tests, also über dem
Richtwert von 400 Zeilen. Teilen nach F5. Commits, je ein Thema:

1. `processing`: `source.py` aus `core._Source`, ohne Verhaltensänderung
2. `processing`: Operator `band_math` mit R5-Prüfung, registriert
3. `processing`: gemeinsames Raster nach F2
4. `api`: Bandnamen in der Annahme prüfen; `bands_of`/`scaling_of` öffentlich
5. `processing`, `api`: Kachel-Pfad mit mehreren Assets und `process_dependency`
6. `api`, `catalog`: freie Ausdrücke im `tiler` schließen (F3)
7. Tests: Vergleich T1 ↔ T2, CPU-Stufen
8. Doku und Log

Vor dem Fertigmelden: `main` holen, `pytest`, `ruff check backend`,
`PYTHONPATH=backend lint-imports --config .importlinter`; Ergebnisse im PR.

---

## 6. Risiken

- **Kachel-Cache vor dem `tiler`:** Dieselben Parameter mit anderer
  JSON-Schreibweise ergeben eine andere URL, also einen Fehltreffer, nie ein
  falsches Bild. Das Panel (M4-13) baut die URL kanonisch.
- **Übersichtsstufen:** Auf Zoomstufen unterhalb der nativen Ebene liest
  rio-tiler Übersichten; T1 ist dort eine Annäherung (Auflage F9). Bei
  gemischten Auflösungen (F2) erreicht das 20-m-Asset seine Übersicht später
  als das 10-m-Asset; die Messung in §2 deckt nur native Ebenen ab.
- **numexpr-Version:** `op_version` 1 hängt an numexpr 2.14.2 aus der
  Lock-Datei; der Cache-Schlüssel enthält die Version schon (F3 von
  `adr/0014`).
- **Schließen von `expression` (F3 Option 1)** ändert eine Route, die heute
  niemand ruft (alle `default_render.expression` sind `None`). Ein externer
  Client mit eigenem Ausdruck bekäme `400` statt eines Bildes auf DN.
- **CI-Maschine ohne AVX2/FMA:** Dann sind A und D dieselbe Stufe, der Test
  ist grün ohne Aussage. Der Test schreibt die aktiven CPU-Merkmale ins
  Protokoll.

---

## 7. Fragen an Otto

**F1 — Der Kern und `0/0` (§3.1, `adr/0014` §3.2, §5.2)**
1. Eigener Kern in `band_math.py`: `numexpr.evaluate` direkt mit
   `optimization="aggressive"`, Eingaben float64, Ergebnis float32; nicht
   endliche Ergebnisse werden Nodata; Groß- und Kleinschreibung bleibt. T1 und
   T2 rufen dieselbe Funktion. Der Rechentyp hängt nicht vom Ausdruck ab
   (gemessen: rio-tiler bliebe bei float32, außer `minimum`/`maximum`, dann
   float64) **(Empfehlung)**
2. rio-tilers `ImageData.apply_expression`, wie §5.2 skizziert: `0/0` → 0,0
   als gültiger Wert, `x/0` → ±1,8·10³⁰⁸ (in float32 ±inf), Ausdruck klein
   geschrieben, Rechentyp je nach Ausdruck
3. Wie 1, aber mit rio-tilers Regel `nan_to_num` (`0/0` → 0,0)

**F2 — Bänder verschiedener Auflösung (§3.2; Auflage F2 zu M4-07a)**
1. Verschachtelte Raster (gleiches CRS, ganzzahliges Verhältnis, Ursprünge auf
   dem groben Raster): gröbere Assets mit `nearest` auf das feinste Raster,
   `earthx:resampled=true`; sonst `GridMismatch`. Gemessen bleibt T1 dabei
   bitgleich (§2) **(Empfehlung)**
2. In M4 weiter `GridMismatch`; gemischte Auflösungen kommen später über einen
   vorangestellten `grid`-Schritt
3. Wie 1, aber auf das gröbste Raster mit `average`; verlangt zusätzlich
   `interpolation`

**F3 — Freie Ausdrücke im `tiler` (§3.4)**
1. Schließen: `expression`, `algorithm` und `algorithm_params` → `400` mit
   Verweis auf `op=band_math`; die Registry lässt `default_render.expression`
   nur `None` zu, bis M4-13 die Standard-Visualisierung auf `op` abbildet
   **(Empfehlung)**
2. `expression` bleibt, geht aber durch R5 und den Kern aus F1 (zwei
   Schreibweisen für dasselbe)
3. Bleibt wie heute; offene Zeile im Log

**F4 — `&`, `|`, `~` in Bedingungen (§3.1, R5)**
1. Zulassen, nur zwischen Vergleichen bzw. auf deren Ergebnis; bitgenau wie
   Vergleiche, und `where((red > 0) & (nir > 0), …)` ist die übliche Form
   **(Empfehlung)**
2. Nicht zulassen, R5 bleibt wörtlich; Bedingungen werden mit
   verschachteltem `where` geschrieben

**F5 — Ein PR oder zwei (§5)**
1. Ein PR über dem Richtwert (rund 450 Zeilen Code, 600 Tests); die Abnahme
   (Vergleich T1 ↔ T2) braucht beide Hälften **(Empfehlung)**
2. Zwei PRs: M4-09 (Operator, R5, T2, CPU-Stufen) und M4-09b (Kachel-Pfad,
   F3, Vergleich T1 ↔ T2)

**Kleinentscheidungen K1–K8** (gelten mit der Freigabe, wenn Otto nichts
sagt):
- **K1:** `processing:expression.format` ist `numexpr`, nicht `rio-calc` wie
  in `adr/0014` §5.6: `rio calc` von rasterio hat eine Lisp-Syntax
  (`rasterio/rio/calc.py`, Docstring) [P], unsere Ausdrücke sind
  numexpr-Infix.
- **K2:** Ein Ausdruck, ein Ausgabeband mit Namen `band_math`; `;` abgewiesen.
- **K3:** URL-Form wie §3.4: `asset` wiederholt, höchstens 16, nur mit `op`;
  `params` als JSON; `op` nur an `tile` und `tilejson`.
- **K4:** Bandnamen sind Python-Bezeichner, keine numexpr-Funktionen, Groß-
  und Kleinschreibung bleibt.
- **K5:** Konstanten nur endliche `int`/`float`; der Exponent von `**` nur als
  ganzzahliges Literal mit \|n\| ≤ 50.
- **K6:** Der Ausdruck wird vor dem ersten Block mit `numexpr.validate`
  kompiliert; Fehler sind `422` bzw. `InvalidParams`.
- **K7:** Der Test über CPU-Stufen läuft als Kindprozess und wird nur mit
  Grund übersprungen, wenn `GLIBC_TUNABLES` nicht wirkt.
- **K8:** Bandnamen prüft verbindlich der Kern beim Start; Annahme und Kachel
  prüfen vorher, soweit die Namen dort bekannt sind (§3.3).

---

## 8. Freigabe (Otto, 07.10.2026)

F1 (1), F2 (1), F3 (1), F4 (1), F5 (1); K1–K8 angenommen, einschließlich
`processing:expression.format = "numexpr"` als Nachtrag in `adr/0014`.

**Auflagen:**
- **F3:** Freie `expression`- und `algorithm`-Parameter im `tiler` werden mit
  `400` und Verweis auf `op=band_math` abgewiesen, je ein Test; vorher im
  Frontend belegen, dass keiner davon genutzt wird. Eigene Log-Zeile
  (Verhaltensänderung des `tiler`).
- **F4:** `&`, `|`, `~` nur auf booleschen Ausdrücken (Vergleiche und ihre
  Verknüpfungen); auf Zahlen definierter `400` aus der R5-Prüfung, nie ein
  `500` aus numexpr. R5 in §1.1b des M4-Plans um diese Erweiterung ergänzen,
  mit Log-Zeile.
- **F2:** Die Markierung „resampled“ steht in der Provenienz des Jobs und ist
  für M4-13 abrufbar.

---

## 9. Umsetzung (07.10.2026)

Umgesetzt wie freigegeben, in thematischen Commits in PR #127. `main` war beim
Start schon im Branch (nichts nachzuholen). Keine neue Abhängigkeit, keine
Lock-Datei geändert; `.github/`, `.claude/`, `CLAUDE.md` und `.importlinter`
unberührt, `lint-imports` hält alle 14 Verträge.

**Belege zu den Auflagen:**
- **F3, Frontend:** `grep` über `frontend/src` (ohne Tests): `algorithm` kommt
  nirgends vor. `expression` kommt in vier Zeilen vor: das Feld
  `EarthxDefaultRender.expression` (`types.ts`), `AppliedRender.expression`
  (`types.ts`), die Übernahme `appliedRenderFrom` (`render.ts`) und der
  Query-Parameter in `buildTileUrl` (`mapLayers.ts`). Der Wert stammt nur aus
  `default_render.expression` der Registry; alle drei Einträge setzen `None`.
  `bidx` setzt nichts. Kein Eingabefeld des Frontends erzeugt einen Ausdruck.
- **F3, Registry:** `DefaultRender` weist `expression` ungleich `None` ab (und
  verlangt jetzt ein Asset), solange M4-13 die Standard-Visualisierung nicht auf
  `op` abbildet. Der bisherige Test „ein Ausdruck allein genügt“ wurde zur
  Abweisung umgeschrieben.
- **F4:** Die Prüfung typisiert den Syntaxbaum (Zahl oder Wahrheitswert):
  `&`, `|`, `~` nehmen nur Vergleiche und ihre Verknüpfungen, `where` verlangt
  einen Wahrheitswert als Bedingung. `red & nir`, `~red`, `red > 0 & nir > 0`
  (Pythons Vorrang bindet `&` stärker) sind `ValueError` der Prüfung → `400`
  im `tiler`, `422` in der Annahme; 65 abgewiesene Formen stehen im Test.
- **F2:** `resampled` steht an drei Stellen: `RunResult.meta.resampled`, dem
  STAC-Feld `earthx:resampled` im Ergebnis und dem Bericht des Kindes
  (`jobs/child.py`, Schlüssel `resampled`). Dieser Bericht wird als
  `earthx_run.result` gespeichert (`queue.finish_successful`); M4-08b reicht ihn
  an M4-13 weiter. Die Rezeptmodelle sind unverändert (`Provenance` wird nicht
  gehasht und bleibt, wie es ist).

**Abweichungen vom Plan und Befunde beim Bauen:**

1. **Maske nur aus den Bändern, die der Ausdruck nennt.** §3.1 sagte „ODER
   aller Bandmasken wie rio-tiler“. Ein Ausdruck über `red` soll nicht dort
   ausfallen, wo ein ungenanntes Asset des Auftrags `nodata` hat. Bei der
   üblichen Eingabe (genau die genannten Assets) ist das dasselbe.
2. **Status der Tile-Route: `400` für Form, `422` für „nicht hier“.** `400`:
   Query fehlerhaft oder `params` ungültig (R5 eingeschlossen, Ottos Auflage F4);
   `422`: wohlgeformt, aber unbekannter Operator oder Version, läuft nicht als
   Kachel, Datensatz erlaubt es nicht, Bandname nicht an den Assets
   (`RecipeInvalid` → `422`), nicht passende Raster (`GridMismatch` → `422`).
   `ScalingMismatch` (Item und Datei widersprechen sich) ist `502`: die Seite
   der Quelle.
3. **Zarr: T1 ↔ T2 nicht in jedem Pixel bitgleich, am Rand der Näherung.**
   Das COG-Paar ist bitgleich (über 1 Mio. gültige Pixel und die Maske des
   `nodata`-Ecks, drei Ausdrücke). Beim Mini-Zarr weichen von 3489 gültigen
   Pixeln einer z14-Kachel 13 ab, ein weiteres liegt nur in einer der beiden
   Masken. Ursache [M]: Die Kachel (T1) liest `XarrayReader`, die Referenz
   liest das COG-Ergebnis des Jobs über `Reader.tile`; beides sind
   `nearest`-Warps mit verschiedener Näherung. Wo der Mittelpunkt eines
   Kachelpixels bis 0,003 Quellpixel von einer Pixelgrenze entfernt liegt,
   wählen sie verschiedene Nachbarn. Die Kachel selbst ist in **jedem** Pixel
   die Formel auf dem exakt nächsten Quellpixel (unabhängig nachgerechnet, mit
   und ohne Item-Skalierung). Der Test verlangt deshalb beides: Kachel =
   Formel auf dem nächsten Quellpixel überall; Kachel = Job überall außer
   innerhalb von 0,125 Quellpixel (GDALs Näherungsschwelle) von einer Grenze,
   und dort höchstens 2 % der Pixel. **Die Abnahme „bitgleich“ gilt damit für
   COG ohne Einschränkung und für Zarr bis auf diese Grenzpixel; Otto hat das am
   07.10.2026 mit Option 1 entschieden (§10).**
4. **`estimate` zählt jetzt die Bänder aller Assets.** Bisher kam das
   Ausgabe-Raster der Schätzung nur aus dem ersten Asset. Die Namensprüfung vor
   der Warteschlange braucht alle Bandnamen, und ein Lauf ohne Schritt schreibt
   auch alle Bänder; der Test `test_a_band_math_like_run` erwartete deshalb ein
   Band zu wenig (4 statt 8 Byte je Pixel für die zwei Bänder von `scale`).
5. **Ganzzahlige Ausgabe mit NaN-`nodata`** (Band-Math in `uint16`) fiel erst
   beim Schreiben als GDAL-Fehler auf. `core._nodata_for` weist sie jetzt als
   `UnsupportedRecipe` ab, vor dem ersten Block.
6. **`Operator.properties`** (neues Feld mit Vorgabe) trägt
   `processing:expression` ins Ergebnis, ohne dass der Kern den Operator
   kennt. Zwei Band-Math-Schritte ergeben eine Liste.
7. **`Source` ist öffentlich** (`processing/source.py`, vorher `core._Source`)
   und hält die Rasterregel von F2; `merge_images` zog mit. Der Test
   `test_gdal_env_threads.py` greift darauf zu.
8. **Namensprüfung vor der Warteschlange** (`plan.check_bands`, aufgerufen in
   `accept_order`, Stufe `applicable`): nur wo das Item die Zahl der Bänder
   nennt; sonst prüft der Kern vor dem ersten Block. Die Annahme nennt bei
   einem ungültigen Ausdruck Feld und Fehlerart, nicht den Text (Vorgabe von
   `adr/0014` §4.7); den Grund liefert die Kachel-Route im `400`.
9. **`tilejson` mit `op`:** getestet; die Kachel-URL darin trägt `asset`
   (wiederholt), `op`, `op_version` und `params` weiter. `info()` des Readers
   ist leer (keine Bandbeschreibung, Typ `float32`).
10. **Nicht gemessen:** Zarr-Kacheln unterhalb der nativen Ebene (Vorschau) und
    Mosaik. Der Test für z11 prüft nur `200`.

**Gemessen am Ende (Sitzung, x86_64):** Setting A gegen D (`GLIBC_TUNABLES`
wirkt: `0x7ed83203` → `0x7ed82203`) liefert für 14 Ausdrücke in float32 und
float64 dieselben SHA-256; die Gegenprobe mit `log`, `exp`, `x**51` weicht ab.

---

## 10. Antworten (Otto, 07.10.2026) und Prüfanleitung

- **Zarr T1 ↔ T2: Option 1.** `adr/0014` §15d präzisiert §6.3: COG bitgleich
  ohne Einschränkung; Zarr bitgleich außerhalb von 0,125 Quellpixel an einer
  Pixelgrenze, an der Grenze darf `nearest` den Nachbarn wählen; die Formel
  stimmt überall; T2 ↔ T2L bleibt bitgleich. Abnahmekriterium 1 in §5 des
  M4-Plans verweist darauf. Die Log-Zeile steht auf „fest am 2026-10-07
  (Otto)“.
- **Abweichungen 1–4 aus §9 angenommen.**
- **Roter Test aus M4-08a** (`test_worker.py::TestLogs`, die Koordinate `9.0`
  steckt im Zeitstempel): nicht hier, eigene Session (M4-08a-fix, #130, gemergt).
  `main` ist danach geholt, der CI-Lauf im PR genannt.

**Lokale Prüfanleitung (Windows/PowerShell).** Dieselbe Szene, die `scripts/try-job.ps1`
(M4-08b) für sein Standardgebiet und seinen Standardzeitraum wählt: die neueste von 18
Szenen im Juli 2025, `S2B_T32UNV_20250729T102457_L2A` (Wolkenbedeckung 60 %; geprüft
am 07.10.2026 mit einer Suchanfrage an Earth Search aus der Sitzung, wie sie der
Viewer stellt). Die Kachel `14/8669/5591` liegt vollständig im Footprint der Szene und
enthält das Westende des Standardgebiets. Gerendert gegen die echte Quelle wurde
nicht, das ist die Prüfung hier; mit den synthetischen Daten der Tests liefern
dieselben Aufrufe `200` (PNG) bzw. `400`.

```powershell
docker compose up -d --build
docker compose ps        # api und tiler: healthy

$tile = "http://localhost:8001/collections/sentinel-2-c1-l2a/items/S2B_T32UNV_20250729T102457_L2A/tiles/WebMercatorQuad/14/8669/5591.png"

# 1. NDVI als Operator: 200, ein 256 x 256 PNG (rot-gelb-grün, -1 bis 1)
$ndvi = "$tile?asset=red&asset=nir&op=band_math&op_version=1&params=%7B%22expression%22%3A%22%28nir-red%29%2F%28nir%2Bred%29%22%7D&rescale=-1,1&colormap_name=rdylgn"
Invoke-WebRequest -Uri $ndvi -OutFile ndvi.png
Start-Process ndvi.png

# 2. freier expression-Parameter: 400 mit Verweis auf op=band_math
$free = "$tile?asset=red&asset=nir&expression=(nir-red)/(nir%2Bred)&rescale=-1,1"
try { Invoke-WebRequest -Uri $free -OutFile free.png } catch { [int]$_.Exception.Response.StatusCode; $_.ErrorDetails.Message }
```

Erwartet bei 2: `400` und `{"detail":"'expression' is not accepted; ask for an
expression with op=band_math&op_version=1&params=…"}`. Beide Adressen lassen sich
auch im Browser öffnen (die erste als Bild, die zweite zeigt den Fehlertext).
Zusatz: mit `params=%7B%22expression%22%3A%22log%28red%29%22%7D` statt NDVI
antwortet der `tiler` mit `400` und nennt die erlaubten Funktionen (`log` liegt
außerhalb von R5). In den Logs (`docker compose logs tiler`) steht weder der
Ausdruck noch eine AOI.
