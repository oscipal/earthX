# DS-05a — dB für Sentinel-1: Operator `sar_db`, Capability `sar_backscatter`, „VV dB“ und „VH dB“

**Stand:** 27.11.2026, Plan mit Fragen F1–F6 und Auslegungen A1–A9, umgesetzt nach den Empfehlungen in zwei Draft-PRs (§11, §12); Antworten Otto offen.
**Stufe B.** Höchstens zwei PRs (Auftrag Otto, 27.11.2026).
**Aufgabe (Otto, 27.11.2026):**

> Führe Aufgabe DS-05a (Stufe B) aus `docs/plans/m5/m5-discovery-und-suche.md` (§6.2) aus; Grundlage `adr/0018`, `adr/0030` §9 und `adr/0036`. Inhalt: Operator `sar_db` mit Wertetabelle, `sar_backscatter`, Schritt-Presets „VV dB“ und „VH dB“ im Processing-Panel. Werte physikalisch wie seit M5-68, Darstellung und Legende passend (Look je Band nach M5-60), Export mit QGIS-Stil nach M5-64. Was für Sentinel-1 nicht geht, erscheint nicht (Registry). Browser-Checks mit einer Sentinel-1-Szene bei 1280×800 und 360×740.

**Grundlagen:** `adr/0030` §5.2, §7, §8 (mit Nachträgen M5-14), §9, F2, F7; `adr/0018` F3 mit §9.4 (Nachtrag M5-12: „VV dB“, „VH dB“ freigegeben) und §9.5 (Radargeometrie); `adr/0036` §7, Tabelle §8 (Zeile „VV dB, VH dB“), §9 (`capabilities.sar_backscatter`); `adr/0035` (Look am Operator); `plans/m5/m5-60-darstellung-je-band.md` §15 (M5-68); `plans/m5/m5-64-qgis-stil.md`; `KLAERUNGEN` B9, B10; M5-Plan §6.5.

Belegstufen: **M** in dieser Session gemessen, **P** am Quelltext gelesen (Stand `main` nach #431), **A** eigene Ableitung.

---

## 1. Ziel

Eine Sentinel-1-GRD-Szene lässt sich in dB zeigen, prozessieren und exportieren:

- **Operator `sar_db`** (T1 und T2, Pixel-Operator): fügt dem Bestand ein Band in dB hinzu, `20·log10(DN)` für Amplitude, `10·log10(DN)` für Intensität. Für ganzzahlige Eingaben über eine **Wertetabelle**, die auf jeder Maschine bitgleich ist (`adr/0030` F2).
- **Capability `sar_backscatter`** (nur Sentinel-1 GRD) und **Feld `sar_quantity`** (Größe je SAR-Band, `adr/0030` §8).
- **Schritt-Presets „VV dB“ und „VH dB“** unter „Quick processing“ (Registry `step_presets`); der Operator steht für jedes SAR-Band im Processing-Panel.
- Darstellung mit dem Look des Operators, Legende mit der Einheit „dB“, Export mit QGIS-Stil wie jede andere Ebene.
- Was die Szene nicht kann, erscheint nicht: kein `sar_db` außerhalb von Sentinel-1, kein „VV dB“ auf einer HH/HV-Szene.

**Nicht Teil:** dB auf Gleitkomma (nach Filter oder Kalibrierung, `adr/0030` F2 „später mit Toleranzregel“; `adr/0036` §8: M6), Speckle-Filter (DS-05b), Komposit „Dual-pol RGB“ (DS-05c), σ⁰ (DS-05d), Reiter „Radar“ (UI-07).

---

## 2. Ausgangslage [P]

| Baustein | Stand | Fundstelle |
|---|---|---|
| Schritt-Presets | vorhanden (M5-14): `StepPreset` in der Registry, Prüfung beim Start von `api` gegen Operator, `applicable()` und Look (`processing/quick_presets.py`); Frontend `quickPresets.ts` | `catalog/registry.py::StepPreset`, `cop-dem-glo-30.yaml` (Hillshade, Slope, Aspect) |
| Look am Operator | `Operator.looks` (`Looks(param, by_value)`), im Prozess als `x-earthx-looks`; das Frontend zeichnet Vorschau, Ergebnis und Ebene damit | `operators/base.py`, `frontend/src/displayLook.ts` |
| Capabilities | zwölf Flags ohne Vorgabe (B10), in jeder YAML gesetzt; `sar_backscatter` fehlt | `registry.py::Capabilities` |
| Sentinel-1-Eintrag | `band_units` `DN` für `vv`, `vh`, `hh`, `hv`; `step_presets: []` mit Verweis auf DS-05a; Look `DN` → `greys_r` (M5-60) | `backend/catalog/datasets/sentinel-1-grd.yaml` |
| `log` in `band_math` | abgelehnt (nicht bitstabil, `adr/0014` §15c) | `operators/band_math.py` |
| Physikalische Werte | Kern skaliert vor dem ersten Schritt; Sentinel-1-COG hat keine Skalierung, die Werte bleiben `uint16`-DN | `processing/scaling.py` |
| QGIS-Stil | Ergebnis-Band ohne `earthx:source_values` (von einem Schritt gemacht): Grau vom 2. bis 98. Perzentil der Statistik, oder der mitgeschickte Look der Ebene | `access/qgis_style.py::result_renderer` |
| Legende | Ebene eines Ergebnisses: Einheit aus dem Ergebnis-Band. **Ansicht und angeheftete Ebene mit Schritt-Preset: Einheit des gelesenen Bands** (`datasetUnit(dataset, scene.asset, …)`), nicht der des gemachten | `frontend/src/mapLegend.ts` |
| Presets je Szene | „Quick processing“ zeigt alle Presets der Collection, ohne Blick auf die Bänder der Szene | `ViewerControls.tsx` |
| Panel, Schritte mit Band | operatorbezogene Listen: `addsBand` (`band_math`, `terrain`), gelesene `bands` (`normalize`, `terrain`), „Rename“ (`band_math`, `terrain`) | `processingBands.ts`, `processingStore.ts`, `StepForm.tsx` |

**Befund Legende [P]:** Bei „Hillshade“ auf einem Höhenmodell steht heute „m“ an den Enden der Legende, bei „VV dB“ stünde nichts (DN gilt nicht als physikalische Einheit, `shownUnit`). Der Server kennt die Einheit des gemachten Bands: Die Statistik der Ansicht (`POST /collections/{d}/statistics` mit den Schritten) nennt sie je Band (`processing/core.py`). F5.

---

## 3. Operator `sar_db` [A]

**Parameter** (streng, `extra="forbid"`):

| Feld | Typ | Bedeutung |
|---|---|---|
| `bands` | genau ein Name | das Band in DN (Amplitude oder Intensität) |
| `name` | Name nach `check_name` | das neue Band, frei im Bestand |
| `quantity` | `amplitude` \| `intensity` | Größe des Bands: Faktor 20 bzw. 10; muss zu `sar_quantity` des Eintrags passen (F1) |

**Rechnung:**

- Eingabe: ganze Zahlen von 0 bis 65 535, geprüft an den Werten jedes Blocks (A2). Andere Werte: `RecipeInvalid` „sar_db reads whole numbers from 0 to 65535 (digital numbers); … holds others“ (F2 aus `adr/0030`: Gleitkomma später).
- Wertetabelle `T[n] = float32(20·log10(n))` für `n = 1 … 65535`, `T[0]` maskiert (DN = 0 ist Nodata bei GRD, `adr/0030` §5.2.1). Intensität: `T[n] / 2`. Die Halbierung ist in `float32` exakt, also ebenso bitgleich.
- Ausgabe `float32`, Nodata `NaN`, maskiert, wo die Eingabe maskiert oder 0 ist. Einheit `dB`.
- `passes_values = MAKES_VALUES` (neue Werte, kein Ganzzahltyp im Ergebnis).
- Kosten: `adr/0030` §7 schätzt 0,2 für den Tabellenzugriff allein. Mit dem Anhängen an den Bestand braucht der Kern 0,77 der Zeit von `band_math` [M, 4 Mpx]; dazu die Statistik des Ergebnisses wie bei `band_math`: Faktor 1,0.

**Bitgleich (A1):** Die Tabelle entsteht so, als wäre jeder Eintrag mit Pythons `decimal` gerechnet und gerundet (`float(Decimal)`, dann `float32`). Ganz in `decimal` dauert das 2,8 s je Prozess [M] — zu lang für den ersten Kachelaufruf. Deshalb rechnet der Operator `20·log10` in `float64` mit numpy und rechnet nur die Einträge mit `decimal` nach, bei denen `float32(v·(1 − 10⁻¹²))` und `float32(v·(1 + 10⁻¹²))` verschieden sind. Für alle anderen liegt jede `float64`-Zahl im Abstand 10⁻¹² denselben `float32` nah; der Fehler von `log10` in `float64` ist um Größenordnungen kleiner. Das Ergebnis ist damit Eintrag für Eintrag gleich der `decimal`-Tabelle, unabhängig von der libm der Maschine. Ein Test vergleicht beide Tabellen ganz (65 535 Einträge). In dieser Session waren alle Einträge schon ohne Nachrechnen gleich [M].

**Look (F4):** `greys_r` auf der üblichen Skala (2. bis 98. Perzentil des Gemessenen), für `amplitude` und `intensity` gleich. Wie das DN-Band (M5-60, `DN` → `greys_r`): dB ändert die Helligkeitsverteilung, nicht die Farbe. Ein fester Bereich in dB passt nicht, weil die Werte unkalibriert sind (`notices: uncalibrated_dn`).

**Text in Rezept und Provenienz:** `lineage` „sar_db: vv_db = 20·log10(vv) (amplitude)“; `method` „A band named vv_db was computed as 20·log10 of the amplitude in vv, from a table of exact values for whole numbers; pixels of value 0 were left empty.“ Eigenschaft `earthx:sar_db` mit den Parametern (wie `earthx:terrain`).

**Registry-Bindung:** `requires` = `sar_backscatter`, Lizenzstufe `processing`, alle Datenklassen. `dataset_check`: das gelesene Band ist ein Band des Eintrags mit `sar_quantity`, und `quantity` ist dessen Größe; ein Band aus einem früheren Schritt kann es nicht sein, weil `sar_db` nur Ganzzahlen liest und kein Schritt Ganzzahlen macht, die nicht Werte der Quelle sind (A2).

---

## 4. Registry [A]

- `Capabilities.sar_backscatter: bool`, ohne Vorgabe (B10): in allen neun Einträgen gesetzt, `true` nur bei `sentinel-1-grd`; in der Collection als `earthx:capabilities.sar_backscatter`.
- `DatasetConfig.sar_quantity: Mapping[str, SarQuantity]` (`amplitude` | `intensity`), leer als Vorgabe wie `band_looks` (A3). Prüfung beim Laden: `sar_backscatter` gesetzt ⇔ `sar_quantity` nicht leer; jeder Schlüssel ist ein Band aus `band_units`, kein Hilfs-Asset, keine Maske; jedes Band mit Einheit `DN` eines Eintrags mit `sar_backscatter` hat eine Größe.
- Sentinel-1: `sar_quantity: {vv: amplitude, vh: amplitude, hh: amplitude, hv: amplitude}` (`adr/0030` §5.2: „uint16-DN, also Amplitude, unkalibriert“).
- `step_presets` (F2, F3):

```yaml
step_presets:
- name: vv_db
  title: VV dB
  op: sar_db
  op_version: 1
  params: {bands: [vv], quantity: amplitude}
  adjustable: []
- name: vh_db
  title: VH dB
  op: sar_db
  op_version: 1
  params: {bands: [vh], quantity: amplitude}
  adjustable: []
```

- Prozessbeschreibung je Datensatz: Hat der Eintrag nur eine Größe, steht `quantity` dort als `const` (A4). Das Panel zeigt dann kein Feld und schickt den Wert mit (`schemaForm.ts`: `const` wird nicht angezeigt). Das ist ein Haken am Operator (`dataset_schema`), kein Name eines Operators in `api`.

---

## 5. Frontend [A]

1. **Presets je Szene (Registry, „erscheint nicht“):** „Quick processing“ zeigt nur Presets, deren Bänder die gezeigte Szene hat (`bandAssetsOf`, A7). Auf einer HH/HV-Szene fehlen „VV dB“ und „VH dB“; ohne Presets fehlt der Abschnitt (Leitfaden §1 Punkt 5). Kennt die Ansicht die Bänder nicht (keine Szene, Zarr), bleibt alles wie heute.
2. **Panel:** `sar_db` ist ein Schritt, der `bands` liest und ein Band `name` hinzufügt, wie `terrain`: eine gemeinsame Liste statt der Namen an drei Stellen. Vorschlag beim Hinzufügen: das erste Datenband mit Einheit `DN`, Name `<band>_db` (frei gemacht mit `defaultName`). Ändert man das Band und trägt der Name noch den Vorschlag, folgt er (wie beim Produkt von `terrain`).
3. **Legende (F5):** Die Ansicht merkt sich die Einheit, die der Server beim Messen eines Schritt-Presets für dessen Band nennt (je Datensatz und Schritt mit Parametern, `presetLooks.ts`); die Legende einer Ansicht oder Ebene mit Schritt-Preset nimmt sie. Ohne Messung (fester Look, Permalink vor dem ersten Messen) keine Einheit statt einer falschen. Ein Index zeigt keine Einheit.
4. **Export:** nichts Neues. „Download crop“ einer Ebene mit „VV dB“ läuft wie bei jedem Schritt-Preset als Job (`indexDownload.ts`) und schickt den Look der Ebene als `exportStyle` mit (M5-64); der Browser-Check prüft den Auftrag.

---

## 6. Physikalische Werte (M5-68) [A]

- Die Sentinel-1-DN haben keine Skalierung; der Kern liest sie als `uint16` und reicht sie unverändert an `sar_db` (`scaling = none`).
- Das dB-Band ist ein von einem Schritt gemachtes Band: Felder, Histogramm, Auto-scale und Legende rechnen in dB, ohne Umrechnung (`buildTileUrl` rechnet nur bei Bändern ohne Schritte um).
- Ein Datensatz, dessen SAR-Band skaliert ist, käme als `float32` beim Operator an und würde abgewiesen (A2). Es gibt keinen solchen; die Regel steht in der Meldung.

---

## 7. Fragen an Otto

**F1 — Woher weiß der Kern, ob 20 oder 10?**
1. Parameter `quantity` im Rezept; `api` prüft ihn gegen `sar_quantity` der Registry. Hat der Datensatz nur eine Größe, steht er in der Beschreibung als fester Wert, und das Panel zeigt kein Feld **(Empfehlung)**: Rezept und Provenienz nennen die Größe selbst, der Kern bleibt ohne Registry (B9).
2. Nur Amplitude in Version 1 (Faktor 20 fest); Intensität mit Version 2, wenn ein Datensatz sie braucht. `sar_quantity` dient dann nur der Prüfung.

**F2 — Name des neuen Bands und Titel der Knöpfe?**
1. `vv_db` / `vh_db` (klein wie die Bänder), Knöpfe „VV dB“ / „VH dB“ **(Empfehlung)**
2. `VV_dB` / `VH_dB`

**F3 — HH- und HV-Szenen (polare Gebiete, EW)?**
1. Nur „VV dB“ und „VH dB“ wie freigegeben (`adr/0018` §9.4); auf HH/HV-Szenen erscheinen sie nicht. `sar_db` steht im Processing-Panel für alle vier Bänder **(Empfehlung)**
2. Zusätzlich „HH dB“ und „HV dB“ als Presets (Nachtrag zu `adr/0018` F3 nötig)

**F4 — Look des dB-Bands?**
1. `greys_r` auf der üblichen Skala (2.–98. Perzentil), wie das DN-Band **(Empfehlung)**
2. Fester Bereich in dB (z. B. 35–55 dB auf DN); passt nicht zu unkalibrierten Werten
3. `viridis`

**F5 — Einheit in der Legende einer Ansicht oder Ebene mit Schritt-Preset (Befund §2)?**
1. Die Einheit, die der Server beim Messen des Bands nennt, im Look der Ebene; ohne Messung keine Einheit. Behebt nebenbei „m“ bei „Hillshade“ **(Empfehlung)**
2. Einheit je Schritt-Preset in der Collection, beim Start von `api` aus dem Operator errechnet; falsch, sobald ein einstellbarer Parameter die Einheit ändert („Slope“: Grad oder Prozent)
3. Bei Schritten keine Einheit

**F6 — Zwei PRs?**
1. PR 1 Backend mit Plan und Log, PR 2 Frontend und Browser-Check auf PR 1 **(Empfehlung)**
2. Ein PR (deutlich über 400 Zeilen ohne erzeugte Dateien)

### 7.1 Auslegungen (gelten, wenn du nicht widersprichst)

- **A1** Wertetabelle wie §3: gleich der `decimal`-Tabelle, aber in Millisekunden gebaut; der Test vergleicht beide ganz.
- **A2** `sar_db` Version 1 liest nur ganze Zahlen von 0 bis 65 535; Brüche, negative, zu große oder nicht endliche Werte weisen den Schritt mit Grund ab (im Job: der Job scheitert mit der Meldung). Geprüft wird an den Werten, nicht am Typ [P]: Die Kachel kennt die Typen der Datei nicht (sie führt jedes Band als `float32`), die Schätzung in `api` nimmt `float64`, wo das Item keinen Typ nennt, und ein Bestand mit einem `float32`-Band hält jedes Band als `float32` (zweiter `sar_db`-Schritt nach einem ersten). dB auf Gleitkomma kommt mit eigener Toleranzregel später (`adr/0030` F2, `adr/0036` §8: M6).
- **A3** `sar_quantity` hat wie `band_looks` eine leere Vorgabe; Pflicht ist es über die Prüfung „`sar_backscatter` ⇔ nicht leer“. Die Capability selbst hat keine Vorgabe (B10).
- **A4** Die Beschreibung je Datensatz setzt `quantity` als `const`, wo der Eintrag nur eine Größe hat (Muster: `reproject` ohne `interpolation`, M5-07).
- **A5** Kategorie des Operators `radar`, Titel „SAR dB“; der Reiter „Radar“ ordnet ihn später ein (UI-07).
- **A6** Die Hinweise „Uncalibrated (DN)“ und „Approximate geolocation“ gelten weiter; `sar_db` ändert sie nicht. Der Methodentext nennt „amplitude“, nicht „backscatter“.
- **A7** Presets einer Szene: ausgeblendet nur, wo ein Band, das sie lesen, ein Band des Datensatzes (`earthx:band_units`) ist und der gezeigten Szene fehlt. Kennt die Ansicht die Bänder der Szene nicht, bleibt alles wie heute.
- **A8** Der Browser-Check nutzt eine synthetische Sentinel-1-Szene in der Form von Earth Search und gemockte Antworten; Collection und Prozessbeschreibung sind die der Registry (erzeugt). Live-Abrufe laufen nicht aus der Cloud-Session (`adr/0002`, M5-Plan §6.5); die echte Szene prüft Otto lokal (§10).
- **A9** Kein neues Paket, keine neue Abhängigkeit.

---

## 8. Tests und Checks

- **Backend:** `test_sar_db.py` (Tabelle gleich `decimal` für alle 65 535 Werte; 0 maskiert; Amplitude 20, Intensität 10 gegen unabhängige Rechnung; `uint8`; Gleitkomma, fehlendes Band, Name doppelt abgewiesen; Job und Runner bitgleich; Kachel gleich Kern auf der nativen Ebene), `test_quick_presets.py` (Sentinel-1-Presets, falsche Größe, Band ohne Größe), Registry-Tests (`sar_quantity` ohne Capability, Capability ohne `sar_quantity`, Band nicht in `band_units`, Hilfs-Asset), `test_processing_docs.py` (`const` je Datensatz, kein `sar_db` bei Sentinel-2), Prozess-Fixtures neu geschrieben (`scripts/write-process-fixtures.py`).
- **Frontend:** Vitest der geänderten Module (Presets je Szene, Panel-Vorschlag, Legende mit Einheit).
- **Browser-Check** `frontend/e2e/ds-05a-sar-db.cjs`: Sentinel-1-Szene VV+VH und HH+HV, hell und dunkel, 1280×800 und 360×740.
- `ruff check backend`, `lint-imports`, `npm run lint`, `npx tsc -b`; Tests nur der geänderten Module (M5-Plan §6.5), nie zwei Läufe gleichzeitig.

---

## 9. Schnitt

- **PR 1 (Backend, dieser Plan, Log):** Operator, Tabelle, Capability, `sar_quantity`, Presets im Eintrag, Beschreibung je Datensatz, Fixtures, Tests.
- **PR 2 (Frontend, auf PR 1):** §5 Punkte 1–3, Vitest, Browser-Check.

---

## 10. Was Otto lokal prüft (nach PR 2)

1. `docker compose up`, Sentinel-1 über Österreich suchen, eine IW-Szene (VV+VH) öffnen.
2. „Quick processing“ zeigt „VV dB“ und „VH dB“. „VV dB“, dann „Apply“: grau, Felder und Legende in dB (Werte um 35–50 dB, unkalibriert).
3. Eine EW-Szene mit HH/HV (Polarmeer): kein „VV dB“/„VH dB“.
4. „Download crop“ der Ebene „VV dB“: ZIP mit `result.tif` und `result.qml`; in QGIS grau mit demselben Bereich.
5. Processing-Panel: „Add step“ → „SAR dB“, Band `vh`, Name `vh_db`; Vorschau und Job.

---

## 11. Umsetzung PR 1: Plan und Backend (27.11.2026, #435)

- `catalog`: `Capabilities.sar_backscatter`, `DatasetConfig.sar_quantity` mit Prüfung (A3), `earthx:capabilities.sar_backscatter`, Suchbegriffe in `capability_terms.yaml`; alle neun Einträge setzen das Flag.
- `processing/operators/sar_db.py`: Operator, Tabelle (`db_table`, `exact_db_table`), Look, `dataset_check`, `dataset_schema`; neuer Haken `Operator.dataset_schema`, aufgerufen in `api/processing_docs.py`.
- Sentinel-1: `sar_quantity`, Presets `vv_db`, `vh_db`.
- Prozess-Fixture `frontend/src/fixtures/processes/sentinel-1-grd.json` neu geschrieben; die übrigen unverändert.
- **Laufen lassen:** `pytest backend/tests/catalog backend/tests/earthx/processing backend/tests/earthx/api` (8573 grün; 8 Tests mit Listen der Operatoren und Presets nachgezogen, danach grün), `test_image_catalog_entries.py`, `test_live_smoke_dry_run.py`, `integration/test_api_collection_search.py`, `ruff check backend`, `lint-imports` (17 Verträge).
- **Befund:** Die Kachel bitgleich zum Job auf der nativen Ebene [M] (`test_tiler_sar_db.py`); der Job bei Blockgröße 64 und 256 dieselben Bytes; die Tabelle ohne Nachrechnen schon gleich der `decimal`-Tabelle, mit einem um 10⁻¹³ verfälschten `log10` nach dem Nachrechnen ebenso (Test).

## 12. Umsetzung PR 2: Frontend und Browser-Check (27.11.2026)

- Panel: `readsBandsAddsBand` (`terrain`, `sar_db`) statt des Namens an jeder Stelle; Vorschlag erstes `DN`-Band und `<band>_db`; der Name folgt dem Band, bis man ihn selbst vergibt (wie das Produkt bei `terrain`). Nebenbei: Ein falsches Band eines `terrain`-Schritts steht jetzt am Feld „Bands“, nicht an einem Feld „expression“, das der Schritt nicht hat.
- „Quick processing“ je Szene (A7), Legende (F5).
- **Befund aus dem Browser-Check:** Die Kachel-URL der Ansicht trägt die Schritte nicht (die Ansicht zeichnet aus der Vorlage der Szene und ihrem Look); die Legende erkennt das Preset deshalb am Look (`index`), nicht an `op` in der URL.
- **Laufen lassen:** Vitest aller Dateien zu Processing, Store, Presets, Legende und Ansicht (97 Dateien, 2869 Tests grün), `npm run lint`, `npx tsc -b`. Browser-Checks: neu `e2e/ds-05a-sar-db.cjs` (hell und dunkel, 1280×800 und 360×740: grün), dazu `quick-processing.cjs`, `preset-params.cjs`, `map-legend.cjs` grün. `s1-pass.cjs` und `processing-panel.cjs` scheitern auf `main` ebenso (Selektoren, die es seit früheren Umbauten nicht mehr gibt); nicht Teil dieser Aufgabe.
