# ADR 0030 — Operatoren und Quick processings je Datensatz

- **Status:** **Entwurf**, offen. Fragen F1–F10 in §10.
  - Nummer 0030 fest laut `docs/plans/m5/m5-discovery-und-suche.md` §6.1.
- **Datum:** 2026-11-06
- **Aufgabe:** M5-12 laut `docs/plans/m5/m5-discovery-und-suche.md` §6.1 (Zusatz Otto vom 06.11.2026, §2 Punkt 8).
- **Autonomiestufe:** C. Kein Produktivcode.
  - Keine Änderung an `backend/`, `frontend/`, `scripts/`, Fixtures, `.importlinter`, `.github/`, `.claude/`, `CLAUDE.md` oder den Lock-Dateien.
  - Gemessen wurden nur Metadaten an drei öffentlichen Buckets (Abschnitt „Methode“).
- **Vorab fest:**
  - Je Datensatz ist festzulegen, welche Processing-Operatoren und welche Quick processings sinnvoll sind. Ottos Beispiel: Sentinel-1 mit Interferometrie als Processing und der Pauli-Zerlegung als Quick processing (M5-Plan §2 Punkt 8).
  - Eigenheiten je Datensatz stehen in der Registry, nicht im Code des Frontends (M5-Plan §2 Punkt 7; DS-00).
  - Was für einen Datensatz nicht geht, erscheint nicht. „Quick processing“ zeigt nur, was gilt (`docs/ui/leitfaden.md` §1 Punkt 5; UI-03 §7.12).
  - `decomp.py` ruht und wird nicht generalisiert. Er wird nur als Operator mit Quad-Pol-Capability übernommen. Sentinel-1 ist Dual-Pol (`ENTSCHEIDUNGEN` §3).
  - Generische Operatoren werden je Datensatz freigeschaltet. Datensatzspezifische hängen an einer Capability, die nur passende Daten setzen (`KLAERUNGEN` B10).
  - Operatoren auf Sentinel-1 GRD nach `adr/0018` F3:
    - erlaubt: Band-Math innerhalb einer Szene, Normalisierung, Reprojektion, Mosaik je Durchgang;
    - nicht erlaubt: feste Schwellen, Index-Knöpfe, Vergleich über Bahnen.
  - Geländeoperator mit Capability `terrain` für Höhenmodelle (`adr/0023` F5; Aufgabe M5-10).
  - Quellen nur ohne Konto. Konto-Quellen in M5 nur als Katalogeintrag mit Link (`adr/0027`).
  - Ausgehende Requests nur über `gateway` (B8). Der Worker-Kern ist zustandslos (B9).
  - Neue Abhängigkeiten nur mit Otto (NM4-14 Plan §4; `adr/0014` K9).
- **Grundlage:**
  - `ENTSCHEIDUNGEN_2026-09-18.md` §2 (polarimetrische Auswertung als Beispiel), §3.
  - `KLAERUNGEN.md` B8, B9, B10, B11.
  - `projektuebersicht.md` §2 (Prinzipien 1, 8, 9, 10), §8 (Band-Math als Weg zu Presets, „Pauli RGB bei SAR“, zeitliche Angleichung).
  - `architekturplan.md` 7.2, 7.3.
  - `adr/0014` §3.5, §5.2, §5.5, §6.1, §6.3, §12, §15c, §15m, §15 NM4-14.
  - `adr/0016` §12a; `adr/0018` §3, §4.2, §4.4, §6, F1–F6; `adr/0020`; `adr/0021`; `adr/0022`; `adr/0023` §6, §7.1, §8.3, F5, F6; `adr/0027` §3.7, §4.
  - Pläne: `plans/querschnitt/nm4-14-index-knoepfe.md`; `plans/vp3/ui-03-seitenleiste-und-processing.md` §7.12; `plans/ds/ds-05-sar-operatoren.md`.
- **Betroffen (erst mit einer Entscheidung):**
  - Registry (`catalog/registry.py`, `catalog/datasets.py`): Capabilities und Preset-Felder (§8).
  - `processing` (Operator-Art mit Nachbarschaft, neue Operatoren) und `api/tiler.py` (Kachel mit Rand).
  - Frontend „Quick processing“.
  - Pläne DS-05 (§9), M5-10, M5-11.

---

## Methode und Belegstufen

Belegstufen wie in `adr/0018` und `adr/0027`:

- **M:** in dieser Sitzung gemessen; das Verfahren steht im Text.
- **P:** am Primärdokument selbst gelesen (im Repo mit Pfad, sonst mit URL in §12).
- **P\*:** Primärdokument über das Abrufwerkzeug eines Hilfsagenten gelesen. Das Werkzeug fasst Seiten zusammen; Zitate sind sinngemäß und vor einer Annahme an der Quelle zu prüfen.
- **S:** Suchtreffer oder Zusammenfassung, Wortlaut nicht geprüft.
- **A:** eigene Ableitung, ein Argument und kein Beleg.

**Gemessen [M], am 06.11.2026, nur Metadaten, anonym mit `curl`:**

- Bucket `sentinel1-slc` (LiveEO, `eu-west-1`):
  - Listing `200`;
  - `?requestPayment` `AccessDenied`;
  - Präfixe der Jahre 2014 bis 2022; der letzte Tag ist der 08.12.2022, danach keine Schlüssel;
  - je Szene eine entpackte SAFE-Gliederung mit sechs Messdateien (TIFF, je 1,2 bis 1,6 GB) sowie Kalibrier- und Rauschdateien (XML, je rund 1 MB bzw. 0,15 MB);
  - `HEAD` auf eine Messdatei: `Accept-Ranges: bytes`, ETag und Last-Modified;
  - Range-GET über 1 KB: `206`.
- `s1-orbits` (`us-west-2`): `README.html` `200`.
- `sentinel-1-global-coherence-earthbigdata` (`us-west-2`): Listing `200`.

**Gelesen [P]:** die Registry-YAMLs dieser drei Buckets und des Buckets `sentinel1-slc-seasia-pds` im AWS Open Data Registry (§12, Q1–Q4). Dazu der Code-Stand im Repo, mit Pfad und Zeile im Text.

**Nicht erreichbar:** Ein Hilfsagent las Fachquellen. Viele Hosts waren aus der Sitzung nicht erreichbar, darunter gdal.org, step.esa.int, sentinels.copernicus.eu, un-spider.org und nature.com. Deshalb tragen viele Fachaussagen nur **S**. Was vor einer Umsetzung an der Quelle zu prüfen ist, steht in §11.

**Anfragen an Datenquellen:** keine Datenpixel. Nur Listings, `HEAD` und 1 KB Range.

---

## 0. Kurzfassung

1. **Was es heute gibt [P]:** sechs generische Operatoren:
   - `band_math`, `mask`, `mask_values` und `normalize` laufen auf Kachel und Job;
   - `reproject` und `select_bands` nur im Job.
   - Dazu Index-Presets nur für Sentinel-2 (NDVI, NDWI, NDSI, NBR, EVI).
   - `band_math` kennt nur bitstabile Funktionen; `log` lehnt es ab (`adr/0014` §15c).
   - **Ein Operator mit Nachbarschaft** (Speckle-Filter, Hangneigung) **hat heute keinen Platz.** Es gibt nur `pixel` und `grid`, und die Blockschleife liest ohne Rand (§2).
2. **Pauli geht mit Sentinel-1 nicht.** Pauli braucht die komplexe Streumatrix aller vier Kanäle [S]. Sentinel-1 ist Dual-Pol, und die Plattform hat nur detektierte GRD.
   - **Statt Pauli:** ein Dual-Pol-Komposit VV / VH / VV÷VH als Quick processing und die dB-Darstellung (§5.2).
   - Nach einer σ⁰-Kalibrierung kommen der Radar-Vegetationsindex RVI und Schwellenmasken dazu.
   - Dual-Pol-H-α und DpRVI brauchen SLC [S] und entfallen.
3. **Interferometrie und Kohärenz brauchen SLC.**
   - Eine weltweite SLC-Quelle ohne Konto gibt es nicht; anonym sind nur zwei regionale Bestände [P][S].
   - Der einzige anonyme europäische Bestand (LiveEO, Deutschland) endet am 08.12.2022 [M]. Eine Szene hat rund 8,5 GB [M].
   - Eine eigene InSAR-Kette kostet Stunden je Stapel und bringt eine neue Werkzeugkette mit [S].
   - **Empfehlung:** keine eigene Interferometrie in M5. Fertige Kohärenzprodukte als eigene Datensätze prüfen (Global Coherence, CC BY 4.0, 2019/20 [P]; LiCSAR [S]); EGMS nur als Katalogeintrag (Konto) (§5.2.4, F6).
4. **Zwei neue Bausteine tragen die meisten Vorschläge (§3):**
   - eine **Operator-Art mit Nachbarschaft** (`focal`): Rand in Blockschleife und Kachel. M5-10 (Gelände) braucht sie zuerst, DS-05 nutzt sie für Speckle-Filter. Die Kachel ist dabei nur „Preview“, weil sie im Kachelraster rechnet; bitgleich zum Job wäre sie nur mit einem eigenen Kachelweg im Quellraster (F3);
   - **Presets über mehr als einen Index:** Komposit-Presets (drei Bänder als RGB) und Schritt-Presets (ein Schritt eines Operators mit festen Parametern), damit Quick processing auch Gelände und SAR abdeckt (F7).
5. **Je Datensatz (§5, Rangfolge in §6):**
   - **Sentinel-2:** vier weitere Index-Presets (NDMI, MNDWI, NDREI, SAVI); Falschfarben-Komposite. NDBI nicht: Es ist genau −NDMI.
   - **Sentinel-1 GRD:** dB über eine Wertetabelle (bitgleich überall), Komposit, Speckle-Filter, später σ⁰.
   - **Copernicus DEM, swissALTI3D, BEV:** Geländeoperator (M5-10) mit Hangneigung, Exposition und Schummerung als Quick processing; TRI/TPI später; kein TWI.
   - **WorldCover:** Klassenanteile in der AOI aus der vorhandenen Ergebnis-Statistik (für `uint8` exakt); kein Vergleich 2020↔2021.
   - **MeteoSchweiz:** zunächst nur generische Operatoren. Anomalien bringt MeteoSchweiz als eigene Produkte. Zeitliche Aggregation braucht Operatoren über mehrere Zeitschritte und einen eigenen ADR.
6. **DS-05 ändert sich (§9):**
   - dB nicht als `band_math`-Preset;
   - Speckle-Filter erst mit `focal`;
   - Pauli gestrichen;
   - RVI und Schwellen erst nach σ⁰;
   - Aufteilung in DS-05a bis DS-05d.
7. **Neu in der Registry (§8):**
   - Capabilities `terrain` (fest), `sar_backscatter`, `sar_calibration`;
   - Felder `composite_presets`, `step_presets` und die Größe je SAR-Band (Amplitude oder Intensität).

---

## 1. Kontext und Frage

> Für jeden Datensatz durchgehen, welche Processing-Operatoren und welche Quick processings sinnvoll wären (Beispiel Otto: Sentinel-1 mit Radar-Processing wie Interferometrie, Quick processing wie Pauli-Zerlegung). (M5-Plan §2 Punkt 8, 06.11.2026)

**Begriffe (UI-03, Leitfaden §2):**

- **Processing:** Schritte im Processing-Panel. Ein Rezept läuft als Kachel (T1) oder als Job (T2/T2L).
- **Quick processing:** der Abschnitt der Seitenleiste mit Knöpfen, die die Darstellung füllen. Heute sind das die Index-Presets und „Enhance contrast“. Ein Index kommt in die Felder und wird mit „Apply“ als Kachel gezeichnet, ohne Job (UI-03 §7.12, Nachtrag 03.11.2026).

**Datensätze laut Auftrag:**

- Sentinel-2 L2A und Copernicus DEM (im Code);
- Sentinel-1 GRD (nach DS-04);
- ESA WorldCover 2020/2021 (M5-07), swissALTI3D (M5-08), BEV ALS-DGM 1 m (M5-09);
- MeteoSchweiz-Klimagitter (M5-11).

**Je Vorschlag gefragt:** Nutzen; Voraussetzungen (Datenlevel, Polarisation, Capability nach B10); Stand der Technik mit Quellen; Rechenkosten; Aufwand; Priorität.

---

## 2. Bestand im Code

**Operatoren** (`processing/operators/registry.py` Z. 87–102) [P]:

| Operator | Capability | Stufen | Art | Kostenfaktor |
|---|---|---|---|---|
| `band_math` v1/v2 | `band_math` | T1, T2 | pixel | 1,2 (1,0 plus Statistik, `adr/0014` §15k) |
| `mask` v1/v2 | `masking` | T1, T2 | pixel | 0,2 |
| `mask_values` | `value_masking` | T1, T2 | pixel | 0,2 |
| `normalize` v1–v3 / v4 | `normalization` | T1, T2 / nur T2 | pixel | 0,3 |
| `reproject` v1–v3 | `reprojection` (+ `interpolation` außer `nearest`/`mode`) | T2 | grid | je Methode 0,5–2,4 |
| `select_bands` | — | T2 | pixel | 0 (nicht in `REGISTRY`) |

- **Planer [P]:** Der längste Anfang aus `pixel`-Schritten mit T1 wird Kachel, höchstens vier Schritte (`processing/plan.py` Z. 368–371; `api/tiler.py` `MAX_OPERATOR_STEPS`). Der Rest wird Job.
- **Bitgleichheit [P]:** Kachel und Job sind auf der nativen Ebene bitgleich; T2 und T2L auf derselben Maschine (`adr/0014` §6.3, §15c).
- **`band_math` [P]:** nur `+ − * /`, ganzzahlige Potenzen, Vergleiche, `where`, `abs`, `minimum`, `maximum`, `sqrt`.
  - „`log`, `exp`, the trigonometric functions and fractional powers are refused; they come back later with a tolerance of their own“ (`processing/operators/band_math.py` Z. 21–22).
  - Rechnet auf physikalischen Werten (Skalierung `adr/0014` §5.4).
- **Nachbarschaft [P]:**
  - Die Blockschleife liest Fenster ohne Rand (`processing/core.py` `_blocks`, Z. 197–200).
  - `adr/0014` §3.5 sagt nur, die Blockgröße ändere bei *punktweisen* Operatoren nichts.
  - Ein Halo, ein Kachelrand (`buffer`) oder eine dritte Operator-Art ist nirgends beschrieben.
- **Capabilities [P]** (`catalog/registry.py` Z. 212–238): `roi`, `time_range`, `band_math`, `interpolation`, `reprojection`, `masking`, `value_masking`, `normalization`, `ml_processing`, `quad_pol`, `single_coverage_product`. `quad_pol` ist überall `False`.
- **Index-Presets [P]:** `IndexPreset` (`catalog/registry.py` Z. 971–987).
  - Felder `name`, `title`, `expression`, `rescale`, `colormap_name`, `formula`, `reference`.
  - Ein Preset ist **ein** `band_math`-Ausdruck. Es braucht `band_math` und wird beim Start von `api` geprüft (`processing/index_presets.py`).
  - Sentinel-2 hat fünf Presets (`catalog/datasets.py` Z. 494–542), der DEM keine.
- **RGB [P]:** Die Kachel zeigt ein Band oder drei als Rot, Grün und Blau. Die Bänder dürfen aus Assets *und aus Schritten* kommen (`api/tiler.py`, `COLOUR_BANDS`, `MAX_BAND_CHARS`). Ein Komposit aus berechneten Bändern ist also schon zeichenbar.
- **Statistik [P]:** `processing/statistics.py` zählt je Ergebnisband blockweise, für die AOI und die ganze Datei.
  - Das Histogramm ist für Ganzzahlen bis 16 Bit exakt (ein Fach je Wert).
- **`decomp.py` [P]:** `datasets/quad_pol_reference/decomp.py`, ohne Aufrufer und ohne Registry-Eintrag.
  - Die Registrierung ist skizziert in `adr/0014` §12: `quad_pol_decomposition`, `grid`, T2, Capability `quad_pol`.
- **Gelände [P]:**
  - Serverseitig gibt es keine Schummerung. Der tiler lehnt TiTiler-`algorithm` ab (`api/tiler.py` `_refuse_free_parameters`).
  - Das Relief (NM4-35) ist ein MapLibre-Layer im Frontend (`frontend/src/relief.ts`).

---

## 3. Bausteine

Jeder Vorschlag in §5 nutzt einen dieser Bausteine. Die Bausteine B0 und B1 gibt es, alle anderen sind neu.

| | Baustein | Kachel (T1)? | Neu? | Wo |
|---|---|---|---|---|
| **B0** | vorhandener generischer Operator (Band-Math, Maske, Normalisierung, Reprojektion) | wie heute | nein | Registry-Flags |
| **B1** | Index-Preset (ein `band_math`-Ausdruck) | ja | nein | `index_presets` |
| **B2** | Komposit-Preset: drei Ausdrücke als RGB | ja, höchstens vier Schritte | Feld neu, Kachel kann es [P] | `composite_presets` (§8) |
| **B3** | Schritt-Preset: ein Schritt eines T1-Operators mit festen Parametern | ja | Feld neu | `step_presets` (§8) |
| **B4** | Operator mit Nachbarschaft (`focal`): liest einen Rand von h Pixeln mit | ja, mit Kachelrand | Operator-Art neu | `processing`, `api/tiler.py` |
| **B5** | Operator mit Hilfsdaten der Szene (z. B. Kalibrier-LUT) | erst Job | neu | `processing`, `readers` |
| **B6** | Operator über mehrere Eingaben oder Zeitschritte (Komposit über Zeit, Differenz zweier Stände) | nein | neu, eigener ADR | Rezept, Planer |
| **B7** | Auswertung einer vorhandenen Ergebnis-Statistik (Klassenanteile) | — | Anzeige neu | `api`, Frontend |
| **B8** | fertiges Produkt als eigener Datensatz statt eigener Rechnung | wie jeder Datensatz | Onboarding | M5-Pipeline |

**B4 im Einzelnen [A]:**

- **Job:** Die Blockschleife liest je Block das Fenster um h Pixel größer, der Operator gibt den inneren Block zurück. Außerhalb der Daten gilt die Maske.
  - Bei Blöcken zu 1024 px und h = 3 (Fenster 7×7) kostet das rund 1,2 % mehr Lesen: (1030/1024)² ≈ 1,012.
- **Kachel:** Die Kachel liest einen Rand mit; rio-tiler kennt dafür einen `buffer` (nicht geprüft für die Version der Lock-Datei).
- **Bitgleichheit Kachel ↔ Job:** Hier geht die Regel für Pixel-Operatoren nicht über.
  - Die Kachel rechnet im Kachelraster (Web Mercator), der Job im Zielraster. Auch auf der nativen Ebene mit `nearest` sind Kachelpixel nicht 1:1 Quellpixel; einzelne werden doppelt gezogen oder übersprungen [A].
  - Für punktweise Operatoren schadet das nicht. Für eine Nachbarschaft schon: Das Fenster enthält andere Pixel, die Neigung rechnet aus doppelten Pixeln.
  - Auch der `buffer` von rio-tiler zählt in Pixeln der Kachel, nicht der Quelle.
  - **Bitgleich wäre nur:** die Kachel liest das Quellfenster mit Rand, rechnet `focal` im Quellraster und warpt erst danach. Das ist ein eigener Kachelweg (F3, Option 2).
  - **Sonst:** Die Kachel ist immer „Preview“, auch auf der nativen Ebene, wie `normalize` auf Overviews (`adr/0014` §0 Punkt 7). Der Job rechnet exakt. Die Abnahme „Kachel ↔ Job bitgleich“ in DS-05 §5 gilt dann für `focal` nicht.
- **Bitgleichheit Job ↔ Runner:** Gleitende Summen in Gleitkomma hängen vom Startpunkt des Blocks ab. Deshalb in ganzen Zahlen summieren, wo die Eingabe ganzzahlig ist (DN und DN² von `uint16` in `int64` sind exakt), sonst jedes Fenster in fester Reihenfolge direkt summieren [A].
- **Ränder der AOI:** Pixel, deren Fenster über die Daten hinausreicht, werden aus den gültigen Nachbarn gerechnet oder maskiert. Die Regel gehört in den Plan, mit Test gegen eine unabhängige Rechnung.
- **Reihenfolge:** Ein `focal`-Schritt in der Kachelkette braucht den Rand aller Schritte davor. Einfachste Regel: `focal` steht in der Kachel nur als erster Schritt.

**B2 und B3:** Beide füllen gewöhnliche Schritte, wie heute ein Index-Preset `band_math` füllt. Hash, Kachel und Job sind dieselben wie bei getippten Schritten (`adr/0014` §15 NM4-14). Kein eigener Operator, keine `op_version`.

---

## 4. Kriterien

| | Kriterium |
|---|---|
| K1 | fachlicher Nutzen für die Daten des Datensatzes (Prinzip 9: nur was die Daten hergeben) |
| K2 | Voraussetzungen erfüllt: Datenlevel, Polarisation, Kalibrierung, Capability (B10) |
| K3 | ausführbar als Kachel (Quick processing) oder nur als Job |
| K4 | bitgleich Kachel ↔ Job auf nativer Ebene, T2 ↔ T2L (`adr/0014` §6.3) |
| K5 | Rechenkosten je AOI (Prinzip 10) |
| K6 | Aufwand in PRs; neue Abhängigkeiten (nur mit Otto) |
| K7 | Regeln: ohne Konto, nur `gateway`, Worker-Kern ohne Plattformdienste, `decomp.py` unangetastet |

**Prioritäten in §5:**

- **P1:** jetzt, mit vorhandenen Bausteinen oder als Teil einer geplanten Aufgabe.
- **P2:** braucht einen neuen Baustein mit klarem Nutzen; Stufe B.
- **P3:** später oder eigener ADR.
- **—:** nicht empfohlen, mit Grund.

---

## 5. Vorschläge je Datensatz

### 5.1 Sentinel-2 L2A (`sentinel-2-c1-l2a`)

**Daten:** 12 Reflektanzbänder (10/20/60 m), SCL-Maske. Alle Flags außer `quad_pol` und `single_coverage_product` gesetzt [P].

| Vorschlag | Baustein | Nutzen | Voraussetzung | Stand der Technik | Kosten | Aufwand | Prio |
|---|---|---|---|---|---|---|---|
| NDMI `(nir − swir16)/(nir + swir16)` | B1 | Feuchte der Vegetation | `band_math` | ASI „NDMI“/„NDII“ [P\*] (Q10) | wie NDVI | Registry-Eintrag | P1 |
| MNDWI `(green − swir16)/(green + swir16)` | B1 | Wasser, trennt bebaute Flächen besser als NDWI | `band_math` | Xu 2006 über ASI [P\*] (Q10, Q11) | wie NDVI | Registry-Eintrag | P1 |
| NDREI `(nir − rededge1)/(nir + rededge1)` | B1 | Chlorophyll bei dichter Vegetation | `band_math` | ASI „NDREI“ [P\*] (Q10); Bandwahl in der Literatur uneinheitlich [S] | wie NDVI | Registry-Eintrag | P1 |
| SAVI `1.5 · (nir − red)/(nir + red + 0.5)` | B1 | NDVI bei offenem Boden | `band_math` | Huete 1988 über ASI [P\*] (Q10); L = 0,5 nicht gelesen [A] | wie NDVI | Registry-Eintrag | P1 |
| NDBI | B1 | — | — | `(swir16 − nir)/(swir16 + nir)` = −NDMI [P\*][A] | — | — | — (doppelt) |
| Komposit Falschfarbe IR (nir, red, green) | B2 | Vegetation rot | — (drei Bänder ohne Schritt, §2) | verbreitet [S] | 3 Bänder, kein Rechnen | mit B2 | P2 |
| Komposit SWIR (swir22, nir, red) | B2 | Brandflächen, Boden | — | verbreitet [S] | wie oben | mit B2 | P2 |
| Zonale Statistik je Polygon | B7 | Mittel/Anteile je Feld | — | Projektübersicht §8 | gering | eigene Aufgabe | P3 |
| Wolkenfreies Zeitkomposit (Median) | B6 | Mosaik ohne Wolken | `masking`, Zeitachse | Standard [S] | n Szenen × Fläche | groß | P3 |
| dNBR (vor − nach) | B6 | Brandschwere | zwei Zeitpunkte | Key & Benson; Schwellen lokal prüfen [S] (Q12) | 2 × NBR | mit B6 | P3 |

- **Skalierung [S]:** Ab Processing Baseline 04.00 gilt ρ = (DN + BOA_ADD_OFFSET)/10 000 (Q13). Presets rechnen auf physikalischen Werten (`adr/0014` §5.4) [P]. Wie die Skalierung je Asset aus den Metadaten kommt, prüft die Umsetzung an einer Szene vor und nach 04.00 [A].
- **Gemischte Auflösungen:** NDMI und MNDWI mischen 10 m und 20 m wie das vorhandene NDSI; die Schätzung bemisst das Raster nach dem feinsten Asset (`adr/0014` §15v) [P]. Neu ist dabei nichts.
- Die Darstellung folgt NM4-14 §8.5 (−1…1, `rdylgn` bzw. `rdbu`).

### 5.2 Sentinel-1 GRD (nach DS-04)

**Daten (`adr/0018` §3.1, §4) [P]:**

- VV+VH (bzw. HH+HV) als `uint16`-DN, also **Amplitude, unkalibriert**;
- Lage aus GCPs per TPS („approximate geolocation“);
- Kalibrier- und Rausch-XML liegen je Szene im Bucket.

#### 5.2.1 Was mit GRD fachlich geht

| Vorschlag | Baustein | Nutzen | Voraussetzung | Stand der Technik | Kosten | Aufwand | Prio |
|---|---|---|---|---|---|---|---|
| dB-Darstellung `20·log10(DN)` | neuer Pixel-Operator `sar_db` (F2) | lesbare Helligkeit; Grundlage aller SAR-Knöpfe | `sar_backscatter`; Größe des Bandes (Amplitude → 20, Intensität → 10) | `adr/0018` §4.2 [A] | Faktor ≈ 0,2 [A] (Tabelle) | 1 PR | P1 (DS-05a) |
| Komposit „Dual-pol“ R = VV, G = VH, B = VV÷VH | B2 auf `sar_db` bzw. `band_math` | trennt Wasser, Vegetation, Bebauung; **Ersatz für Pauli** | `sar_backscatter`; Verhältnis nur innerhalb der Szene, näherungsweise (`adr/0018` §4.4) | Sentinel Hub „RGB ratio“ (VV, VH, VH/VV mit Verstärkung) [S] (Q14); feste Belegung nicht normiert [S] | 1–2 Schritte | mit B2 | P2 (DS-05c) |
| Speckle-Filter Boxcar, Lee | B4 | glättet Speckle, erhält Kanten (Lee) | `sar_backscatter`; Rechnung auf Intensität (DN²) [A] | SNAP bietet Boxcar, Median, Frost, Gamma-MAP, Lee, Refined Lee, Lee Sigma, IDAN [S] (Q15); Fenster 5×5 bis 7×7 in Anleitungen [S] | Faktor ≈ 1–2 mit Summen in ganzen Zahlen [A], messen | 1–2 PRs nach B4 | P2 (DS-05b) |
| Refined Lee, Gamma-MAP, Lee Sigma | B4 | bessere Kanten- und Punktzielerhaltung | wie oben | Lopes 1990 [S]; Lee et al. 2009 (Q16) [S] | höher, messen | je 1 PR | P3 |
| Multitemporaler Filter | B6 | Speckle über die Zeit | gleiche Bahn, σ⁰ | Quegan & Yu 2001 (Q17) [S] | n Szenen | groß | P3 |
| σ⁰-Kalibrierung `σ⁰ = DN²/A²` mit LUT, optional Rauschabzug | B5 (F5) | vergleichbare Werte; erlaubt danach Schwellen und RVI | `sar_calibration`; LUT aus der Annotation über `gateway` | LUT bilinear je Pixel interpoliert, Rauschen mit LUT skaliert [S] (Q18, Q19) | + 1 Hilfsband, Warp `nearest` (0,5) [A]; je Szene 1–2 XML | 2 PRs | P2 (DS-05d) |
| RVI `4·σVH/(σVV + σVH)` | B1 auf σ⁰ | Vegetationsdichte | **nach σ⁰**; `adr/0018` F3 schließt Index-Knöpfe auf DN aus | Nasirzadehdizaji 2019 nach Trudel 2012 [S] (Q20) | wie NDVI | Registry nach DS-05d | P3 |
| Wassermaske (Schwelle in dB) | B0 `mask_values` mit Schwelle des Nutzers | Hochwasser | **nach σ⁰**; Schwelle regional | Werte zwischen −15 und −20 dB in Anleitungen, nicht einheitlich [S] (Q21) | gering | vorhanden (DS-06) | P3, kein Preset |
| Änderung zweier Szenen (Log-Ratio) | B6 | Änderungen, Hochwasser | gleiche relative Bahn, σ⁰; `adr/0018` F3 verbietet Vergleich über Bahnen | Standardverfahren [S] | 2 Szenen | mit B6 | P3 |
| RTC (γ⁰) | eigener ADR (`adr/0018` F6) | Geländekorrektur | DEM, sarsen (19 Pakete) | `adr/0018` §6 [P] | Minuten je AOI | 4–6 PRs | P3, unverändert |

**dB ohne Toleranz [A] (Grund für F2):**

- Die Eingabe ist `uint16`. `20·log10(DN)` hat also höchstens 65 536 Werte.
- Eine Wertetabelle, einmal mit Pythons `decimal` (korrekt gerundetes `log10`) erzeugt und auf `float32` gerundet, ist auf jeder Maschine bitgleich. Damit gilt auch T2 ↔ T2L über Maschinen.
- Ein `log10` aus numpy oder numexpr ist es nicht: Deshalb lehnt `band_math` `log` heute ab (§2).
- Für Gleitkomma-Eingaben (nach Filter oder Kalibrierung) gilt das nicht. Dort braucht dB eine Toleranzregel (F2).
- DN = 0 ist bei GRD Nodata (`adr/0018` §3.1); `log10(0)` ist −∞. Die Tabelle führt 0 deshalb als maskiert, mit eigenem Testfall.

**Geometrie des Filters [A]:**

- `adr/0018` §4.4 nennt die Radargeometrie als fachlich besten Ort für Speckle-Filter.
- Die Plattform liest Blöcke aber schon im Zielraster (TPS-Warp in `readers`). Auf nativer Auflösung mit `nearest` bleibt die Speckle-Statistik je Pixel erhalten. Das Fenster ist dann ein Kartenfenster, kein Radarfenster.
- Der Unterschied ist bei 10 m Ausgabe klein, bei Reprojektion auf ein gröberes Raster nicht. Deshalb: Filter vor jeder Reprojektion; die Umsetzung prüft das an einer Szene gegen SNAP.

**Kalibrierung ohne Radargeometrie [A]:**

- Die LUT liegt im Zeilen-/Spaltenraster der Szene. Sie wird als zusätzliches Band in Radargeometrie aufgebaut und mit derselben TPS und `nearest` gewarpt wie die DN.
- Dann gehört zu jedem Zielpixel genau der LUT-Wert seines Quellpixels, und σ⁰ = DN²/A² ist exakt dieselbe Rechnung wie in Radargeometrie.
- **Offen:** ob Earth Search die Kalibrier-XML als Asset führt oder ob der Pfad aus `manifest.safe` kommt (`adr/0018` §3.1 nennt nur `schema-product-*` als Assets).

#### 5.2.2 Pauli und andere Zerlegungen

- **Pauli** braucht die komplexe Streumatrix mit HH, HV, VH und VV und deren Phase [S] (Q22). Sentinel-1 misst zwei Polarisationen; GRD ist detektiert, ohne Phase. **Geht nicht.**
- **Dual-Pol H-α** (Cloude 2007) und **DpRVI** (Mandal 2020) rechnen auf der 2×2-Kovarianzmatrix C2 mit dem komplexen Kreuzterm [S] (Q23, Q24). Sie brauchen also SLC. **Geht mit GRD nicht.**
- **`decomp.py`** bleibt ruhend mit synthetischen Tests (`ENTSCHEIDUNGEN` §3). Eine Quelle für komplexe Quad-Pol-Daten ohne Konto gibt es weiter nicht (`adr/0023` §6.3).
- **Verhältnis zu `adr/0018` F3:** F3 schließt „Index-Knöpfe“ auf GRD aus, weil sie für optische Daten gelten. „VV dB“, „VH dB“ und „Dual-pol RGB“ sind keine optischen Indizes, sondern Darstellungen derselben Szene, die F3 erlaubt (dB, Verhältnis innerhalb der Szene). Als Quick processing brauchen sie trotzdem Ottos Zustimmung als Nachtrag zu F3; F1 und F7 schließen sie ein.
- **Ersatz im Sinne von Ottos Beispiel:** Quick processing „Dual-pol RGB“ (VV, VH, VV÷VH) und „VV dB“/„VH dB“. Beide zeigen auf einen Blick, was die Pauli-Darstellung bei Quad-Pol zeigt: Oberfläche, Volumen, Doppelreflexion. Das ist eine Näherung [A].

#### 5.2.3 Interferometrie und Kohärenz

Beides rechnet mit der Phase zweier Aufnahmen derselben Bahn. Es braucht also **SLC**, präzise Bahndaten und eine Koregistrierung.

**SLC-Quellen ohne Konto:**

| Quelle | Abdeckung | Zeitraum | Zugang | Beleg |
|---|---|---|---|---|
| `sentinel1-slc` (LiveEO, `eu-west-1`) | Deutschland („Europa geplant“) | 2014 bis **08.12.2022**; YAML sagt „updated continuously“ | anonym, Range `206` | [P] Q1, [M] |
| `sentinel1-slc-seasia-pds` (EOS, `ap-southeast-1`) | Süd- und Südostasien, Japan | laufend laut YAML | anonym laut YAML | [P] Q2 |
| ASF, CDSE | weltweit | laufend | **Konto** (`adr/0018` §3.4, `adr/0027`) | [P] |
| Bahndaten `s1-orbits` (ASF, `us-west-2`) | Mission | POEORB gesamt, RESORB 90 Tage | anonym | [P] Q3, [M] |

**Was eine eigene Kette kostete [S][A]:**

- **Daten:** Eine IW-SLC-Szene hat rund 8,5 GB in sechs Messdateien [M]. Ein Interferogramm über eine AOI liest mindestens zwei Bursts je Szene und Datum.
- **Rechnen:** Der OPERA-Ablauf (ISCE3, dolphin) braucht 6 bis 8 h je Stapel von 15 Daten auf 32 vCPU; das Entfalten der Phase dominiert [S] (Q25).
- **Werkzeuge:** ISCE3, SNAP oder GMTSAR wären neue, große Abhängigkeiten (K6).
- **Worker-Kern:** Der Kern müsste große Zwischenstände halten. Das passt nur zu T3 (Container-Job) oder T4 (externe Engine) (`architekturplan.md` 7.3).

**Fertige Produkte (B8):**

| Produkt | Inhalt | Zugang, Lizenz | Bewertung |
|---|---|---|---|
| Global Seasonal Coherence and Backscatter (Earth Big Data/Gamma, Kellndorfer et al. 2022) | Kohärenz 6–48 Tage je Jahreszeit, γ⁰ VV/VH/HH/HV, Zerfallsmodell; 1°-Kacheln 3″ (≈ 90 m), Mosaike 0,01° als COG; 1.12.2019–30.11.2020, ohne Fortschreibung | anonym [M], CC BY 4.0 [P] (Q4) | gut als **eigener Datensatz** (statisch, je Jahreszeit); `data_region` `aws:us-west-2` → Prüfung nach `adr/0022` |
| COMET LiCSAR (Lazecký et al. 2020) | Interferogramme und Kohärenz je Frame, ≈ 100 m, GeoTIFF | laut einem CEDA-Eintrag ohne Registrierung, UK OGL v3 [S] (Q26) | prüfen: Abdeckung der Alpen, Zugang, Format (Overviews?) |
| EGMS (Copernicus) | Bodenbewegung aus InSAR, Europa | EU Login [S] (Q27) | nur Katalogeintrag mit Link (`adr/0027` W0); zudem Punktdaten (CSV), nicht Raster |
| OPERA DISP-S1 / CSLC-S1 | Bewegung, koregistrierte SLC | Earthdata Login [S] (Q28) | `adr/0027` |

**Empfehlung (F6):**

- Keine eigene Interferometrie in M5.
- Global Coherence als Kandidat für die Pipeline aus `adr/0025`; LiCSAR prüfen; EGMS als Katalogeintrag.
- Den LiveEO-Bestand nicht anbinden: nur Deutschland, seit fast vier Jahren nicht fortgeschrieben, Datenmenge je Szene groß.
- Eigene InSAR erst mit einer weltweiten SLC-Quelle ohne Konto oder über `adr/0027` (W2a/W4), dann als eigener ADR mit T3/T4.

### 5.3 Copernicus DEM GLO-30 (`cop-dem-glo-30`)

**Daten:** Höhe in m, 30 m, EPSG:4326 [P]. `band_math`, `value_masking`, `normalization`, `reprojection` gesetzt; `masking` nicht.

| Vorschlag | Baustein | Nutzen | Voraussetzung | Stand der Technik | Kosten | Aufwand | Prio |
|---|---|---|---|---|---|---|---|
| Hangneigung (Grad/Prozent), Exposition, Schummerung | B4, Operator `terrain` (M5-10) | Grundauswertung jedes DEM | `terrain` (fest) | `gdaldem`: Horn (Vorgabe) oder Zevenbergen-Thorne; Schummerung mit Azimut, Höhe, z-Faktor, „multidirectional“ [P\*] (Q29) | 3×3, Faktor ≈ 1 [A] | M5-10 | P1 |
| Quick processing „Slope“, „Hillshade“ | B3 auf `terrain` | ein Klick in der Ansicht | `terrain`, B3 | — | wie oben | mit B3 | P2 |
| TRI (Riley), TPI, Rauheit | B4, Parameter von `terrain` | Rauheit, Geländeposition | `terrain` | `gdaldem`: TRI Riley (Vorgabe seit GDAL 3.3) oder Wilson; TPI nach Wilson et al. 2007 [P\*] (Q29) | 3×3 | klein nach M5-10 | P3 |
| Krümmung | B4 | Geomorphologie | `terrain` | Zevenbergen-Thorne [S] | 3×3 | klein | P3 |
| Topographic Wetness Index, Einzugsgebiete | — | Hydrologie | Fließakkumulation über das ganze Einzugsgebiet | nicht blockweise rechenbar [A] | — | — | — |
| Höhenstufen | B0 `mask_values` | Maske nach Höhe | vorhanden | — | gering | vorhanden | P1 (nichts zu tun) |

- **EPSG:4326 [P\*][A]:** Neigung braucht Meter in beiden Achsen. `gdaldem` nimmt dafür `-s 111120` und empfiehlt fern vom Äquator eine Reprojektion; ab GDAL 3.11 bestimmt es die Skala aus dem CRS (Q29).
  - Für den Operator heißt das: Pixelgröße in Metern je Zeile aus der Breite, oder Neigung nur nach einer Reprojektion. Das entscheidet M5-10 (dort Pflichtpunkt).
- **Schummerung im `tiler`:** `adr/0023` F5 und M5-10 verlangen, die Schummerung auch als Algorithmus im `tiler` zu prüfen (Ergänzung zu NM4-35). Das wäre eine reine Darstellung ohne Rezeptschritt. Ein Schritt-Preset „Hillshade“ (B3) dagegen ist ein Schritt mit Hash, Download und Provenienz. Beide schließen sich nicht aus; M5-10 legt fest, welcher Weg die Ansicht bedient, F7 nur das Registry-Feld.
- **Index-Presets:** keine (wie NM4-14 KE5).

### 5.4 swissALTI3D und BEV ALS-DGM 1 m (M5-08, M5-09)

Wie §5.3, mit drei Unterschieden:

- **Pixelzahl [A]:** 0,5 m sind 4 Mpx/km², 1 m 1 Mpx/km², GLO-30 rund 0,001 Mpx/km². Eine AOI von 100 km² hat mit swissALTI3D 400 Mpx: ein Job, keine Vorschau aus nativer Ebene.
  - swissALTI3D hat ein 2-m-Asset (`adr/0023` §3.1). Für große AOIs sollte die Registry es als zweite Wahl führen.
- **Projektion:** LV95 bzw. EPSG:3035, metrisch. Kein Gradproblem.
- **Mehrere Stände je Kachel** (Regel aus M5-08): Die Differenz zweier Stände (Gletscher, Rutschungen, Abbau) wäre ein starker Nutzen. Sie braucht zwei Eingaben (B6) und gleiche Höhenbezüge; **P3**.

### 5.5 ESA WorldCover 2020 / 2021 (M5-07)

**Daten:** `uint8`, elf Klassen, Farbtabelle, ≈ 10 m (`adr/0023` §6.1) [P]. Eigenheiten fest nach `adr/0023` §8.3: Maske über die Klassen, `value_masking`, kein `band_math`, nur `nearest`, `index_presets` leer.

| Vorschlag | Baustein | Nutzen | Voraussetzung | Stand der Technik | Kosten | Aufwand | Prio |
|---|---|---|---|---|---|---|---|
| Klassenanteile in der AOI (Fläche und %) | B7 | Hauptfrage an eine Landbedeckung | Klassentabelle aus `mask`; Ergebnis-Statistik (exakt für `uint8`) [P] | Standard (zonales Histogramm) [A] | keine Rechnung zusätzlich | 1 PR (API und Anzeige) | P1 nach M5-07 |
| Maske je Klasse | B0 `mask` | „nur Wald“ usw. | vorhanden | — | 0,2 | vorhanden | P1 |
| Änderung 2020 → 2021 | B6 | — | — | Algorithmuswechsel v100 → v200; Unterschiede teils methodisch (PUM v2.0) [S] (Q30) | — | — | — |
| Klassenmaske für andere Datensätze (z. B. NDVI nur auf Acker) | B6 | Kombination | zwei Datensätze | — | gering | mit B6 | P3 |

- **Quick processing:** keine. Die Klassen sind die Darstellung.
- **Klassenanteile ohne neue Capability:** Wie `earthx:aoi_cloud_cover` aus `mask` abgeleitet wird (DS-02 §6.9, DS-03), leiten sich die Anteile aus `mask` ab.

### 5.6 MeteoSchweiz-Klimagitter (M5-11)

**Daten [P\*] (Q31):**

- `ogd-surface-derived-grid`: 1 km, NetCDF, LV95.
- Niederschlag `RhiresD/M` (`RprelimD` vorläufig), Temperatur `TabsD/M`, relative Sonnenscheindauer `SrelD/M`.
- Minimum und Maximum als `TminD`/`TmaxD` laut Produktdokumentation [S].
- **Monatliche Anomalien gegen 1991–2020 gibt es als eigene Produkte** (z. B. `TanomM9120`).
- Wie Variablen auf Assets und Bänder abgebildet werden, entscheidet der Leseweg (M5-06, `adr/0029`).

| Vorschlag | Baustein | Nutzen | Voraussetzung | Stand der Technik | Kosten | Aufwand | Prio |
|---|---|---|---|---|---|---|---|
| Band-Math, Werte-Maske, Normalisierung, Reprojektion aus LV95 | B0 | Schwellen („Tage über …“ je Zeitschritt), Einheiten | Flags beim Onboarding | — | 1 px/km², vernachlässigbar | Registry | P1 (M5-11) |
| Anomalien | B8 | Abweichung von der Norm | Produkte von MeteoSchweiz | MeteoSchweiz liefert sie selbst [P\*] (Q31) | — | Onboarding | P2 |
| Zeitliche Aggregation (Monats-, Jahreszeitenmittel bzw. -summe) | B6 | Klimaauswertung | Zeitachse in Registry und Rezept (`adr/0029`) | Standard [A] | n Zeitschritte × Fläche | eigener ADR | P3 |
| Schwellentage (Frosttage Tmin < 0 °C, Sommertage Tmax > 25 °C) | B6 | Klimaindikatoren | `TminD`/`TmaxD`, Zeitachse | ETCCDI (Zhang et al. 2011): FD Tmin < 0 °C, SU Tmax **> 25 °C** [S] (Q32) | wie oben | mit B6 | P3 |
| Zeitliche Interpolation | B6 | Lücken | — | Projektübersicht §8 („zeitliche Angleichung“) | — | eigener ADR | P3 |

- **Quick processing:** zunächst keine. Ein Index-Preset braucht Bänder desselben Items; ob `TminD` und `TmaxD` zusammen in einem Item liegen, zeigt erst M5-11.

---

## 6. Rangfolge über alle Datensätze

| Rang | Was | Datensatz | Baustein | Aufgabe |
|---|---|---|---|---|
| 1 | Geländeoperator inkl. Operator-Art `focal` (B4) | DEM, swissALTI3D, BEV | B4 | M5-10 (geplant) |
| 2 | Vier Index-Presets (NDMI, MNDWI, NDREI, SAVI) | Sentinel-2 | B1 | neu, Stufe A |
| 3 | Klassenanteile in der AOI | WorldCover | B7 | neu, Stufe A/B nach M5-07 |
| 4 | dB über Wertetabelle mit Capability `sar_backscatter` | Sentinel-1 | Pixel-Operator | DS-05a |
| 5 | Komposit- und Schritt-Presets (B2, B3) | alle | B2, B3 | neu, Stufe B (Registry und Frontend) |
| 6 | Speckle-Filter Boxcar und Lee | Sentinel-1 | B4 | DS-05b |
| 7 | σ⁰-Kalibrierung, danach RVI und Schwellen | Sentinel-1 | B5 | DS-05d |
| 8 | Global Coherence als Datensatz | — | B8 | Pipeline (Fassung 3) |
| 9 | Mehrere Eingaben und Zeitschritte (Zeitkomposit, dNBR, Differenz der Stände, Klimaaggregation, Log-Ratio) | S2, S1, DEM, Meteo | B6 | eigener ADR |
| — | Pauli, H-α, DpRVI, eigene InSAR, TWI, WorldCover-Änderung, NDBI | — | — | nicht empfohlen |

**Warum `focal` zuerst mit M5-10 [A]:**

- M5-10 liegt in Welle 3, DS-05 in Welle 4 (M5-Plan §6.2).
- M5-10 nennt „Nachbarpixel über den Blockrand“ schon als Pflichtpunkt.
- Baut M5-10 die Operator-Art allgemein (Rand h als Eigenschaft des Operators, Kachelrand im tiler), braucht DS-05b nur noch die Filter.

---

## 7. Rechenkosten

Einheit wie `adr/0014` §5.5: Megapixel der Ausgabe × Summe der Faktoren. Neue Faktoren sind Schätzungen [A]; die Umsetzung misst sie.

| Operator | Faktor (Schätzung) | Begründung |
|---|---|---|
| `sar_db` (Wertetabelle) | 0,2 | ein Tabellenzugriff je Pixel, wie `mask` |
| Boxcar/Lee 7×7 | 1–2 | Fenstersummen in ganzen Zahlen bzw. in fester Reihenfolge (§3), Rand +1,2 % |
| `terrain` 3×3 | 1 | neun Nachbarn, Gradient, `atan2` |
| σ⁰-Kalibrierung | 0,5 + 0,2 | ein Hilfsband mit `nearest` gewarpt, dann Pixelrechnung; dazu 1–2 XML je Szene |
| InSAR (nur zum Vergleich) | — | Stunden je Stapel [S] (Q25) |

**Pixel je 100 km² Ausgabe [A]:**

| Datensatz | Mpx |
|---|---|
| Sentinel-1/-2 (10 m) | 1 |
| GLO-30 | 0,11 am Äquator, ≈ 0,15 in den Alpen (1″ ≈ 31 × 21 m) |
| BEV (1 m) | 100 |
| swissALTI3D (0,5 m) | 400 |
| MeteoSchweiz (1 km) | 0,0001 je Zeitschritt |

---

## 8. Was in der Registry neu wäre

Getrennt ausgewiesen, wie verlangt (M5-Plan §6.1). Alles Vorschlag [A], außer `terrain`.

**Capabilities (B10, je Eintrag ausdrücklich, ohne Vorgabe):**

| Flag | Gesetzt für | Schaltet frei | Stand |
|---|---|---|---|
| `terrain` | Copernicus DEM, swissALTI3D, BEV | Geländeoperator | **fest** (`adr/0023` F5) |
| `sar_backscatter` | Sentinel-1 GRD (später RTC) | `sar_db`, Speckle-Filter, SAR-Komposit | neu (F2) |
| `sar_calibration` | Sentinel-1 GRD | σ⁰-Operator; setzt voraus, dass die Szene ihre Kalibrier-LUT mitbringt | neu (F5) |
| `quad_pol` | niemand | `decomp` | unverändert |

Für Interferometrie, Kohärenz oder Dual-Pol-Zerlegungen gibt es **kein** neues Flag, solange es keine SLC-Quelle gibt.

**Felder:**

| Feld | Inhalt | Prüfung |
|---|---|---|
| `composite_presets` | `name`, `title`, drei Ausdrücke (R, G, B) in den Bändern des Datensatzes, `rescale` je Kanal, `reference`. Erweitert das vorhandene `true_color` (`catalog/registry.py`, NM4-64), das nur die Echtfarben nennt; `true_color` bleibt | wie `index_presets`: Form in `catalog`, Ausdrücke beim Start von `api`; höchstens vier Schritte (Kachelgrenze) |
| `step_presets` | `name`, `title`, `op`, `op_version`, `params`, Darstellung (`rescale`, `colormap_name`) | beim Start von `api` gegen das Parameterschema des Operators und `applicable()`; nur T1-Operatoren |
| Größe je SAR-Band, z. B. `sar_quantity: {"vv": "amplitude", "vh": "amplitude"}` | Amplitude, Intensität, σ⁰, γ⁰; bestimmt den Faktor 20 oder 10 in dB und den Text in Rezept und Provenienz | Pflicht, wenn `sar_backscatter` gesetzt ist |
| Ort der Kalibrierdaten | Asset-Schlüssel oder Pfadregel zur Kalibrier-XML je Polarisation | Pflicht, wenn `sar_calibration` gesetzt ist; offen, siehe §5.2.1 |

**Keine neuen Felder:**

- Klassenanteile kommen aus `mask` (§5.5).
- Gelände-Parameter gehören zum Operator, nicht zum Datensatz.
- Hinweise „Approximate geolocation“ und „Uncalibrated (DN)“ regelt DS-04 (`adr/0018` F2).

**Leere Felder** bleiben Pflicht und leer, wo nichts gilt (B10). Beispiele: `index_presets = ()` bei WorldCover, `composite_presets = ()` beim DEM. Dann fehlt der Abschnitt „Quick processing“ (Leitfaden §1 Punkt 5).

---

## 9. Abgleich mit DS-05 (Folgen)

`plans/ds/ds-05-sar-operatoren.md` nennt als Kandidaten: linear ↔ dB, Speckle-Filter (Lee, Refined Lee, Gamma-MAP), Verhältnis- und Differenz-Darstellungen, RGB-Komposite als Presets. Dazu „Pauli RGB“ über `projektuebersicht.md` §8.

| Punkt in DS-05 | Folge aus diesem ADR |
|---|---|
| dB als Preset über Band-Math | geht nicht: `band_math` lehnt `log` ab (§2). Statt dessen Operator `sar_db` mit Wertetabelle für Ganzzahlen (F2) |
| Speckle-Filter | braucht die Operator-Art `focal` (B4). Sie kommt aus M5-10; DS-05 baut darauf auf (F3). Zuerst Boxcar und Lee (F4) |
| T1-Vorschau des Filters | „Preview“ auch auf nativer Ebene, weil die Kachel im Kachelraster rechnet; bitgleich nur mit eigenem Kachelweg im Quellraster (§3, F3). Die Abnahme in DS-05 §5 ist dafür anzupassen |
| Verhältnis und Differenz | Verhältnis innerhalb der Szene mit Hinweis (`adr/0018` F3); in dB als Differenz über `band_math` nach `sar_db` |
| RGB-Komposite als Presets | brauchen `composite_presets` (F7); die Kachel kann drei berechnete Bänder schon zeigen (§2) |
| Pauli RGB | **entfällt** für Sentinel-1 (§5.2.2); `decomp.py` bleibt ruhend |
| feste Schwellen, RVI | erst nach σ⁰-Kalibrierung (F5); bis dahin wie `adr/0018` F3 |
| Kalibrierung | neu als DS-05d (F5) |

**Vorgeschlagene Aufteilung [A]:**

| | Inhalt | Stufe | Hängt ab von |
|---|---|---|---|
| DS-05a | `sar_db` mit Wertetabelle, Capability `sar_backscatter`, Feld für die Größe je Band, Schritt-Presets „VV dB“ / „VH dB“ | B | DS-04; B3 (F7) |
| DS-05b | Boxcar und Lee auf `focal` | B | M5-10 gemergt |
| DS-05c | Komposit „Dual-pol RGB“ | A | DS-05a; B2 (F7) |
| DS-05d | σ⁰-Kalibrierung, danach RVI-Preset | B | DS-05a; F5 |

`docs/plans/ds/ds-05-sar-operatoren.md` wird nach Ottos Antwort angepasst; das ist nicht Teil dieses PR.

**Nebenbefund:** `docs/plans/ds/ds-04-s1-anbinden.md` enthält denselben Text wie `ds-00-paket.md` (Überschrift „DS-00 — Paket …“). Der Nachtrag dazu ist ohnehin offen (`adr/0018` §10, letzter Punkt). Der Plan für DS-04 sollte vor dem Start von DS-04 neu geschrieben werden.

---

## 10. Fragen an Otto

**F1 — Rangfolge und Schnitt (§6)?**
1. Wie in §6: Rang 1–3 mit M5, Rang 4–7 über DS-05 und eine Aufgabe für B2/B3, Rang 8–9 mit Fassung 3 bzw. eigenem ADR **(Empfehlung)**
2. Nur was ohne neuen Baustein geht (Rang 2, 3), alles andere nach M5
3. Sentinel-1 zuerst (Rang 4–7 vor 2, 3, 5)

**F2 — dB für Sentinel-1?**
1. Eigener Pixel-Operator `sar_db` (T1, T2) an Capability `sar_backscatter`, für Ganzzahlen über eine Wertetabelle (überall bitgleich); dB auf Gleitkomma (nach Filter/Kalibrierung) später mit eigener Toleranzregel **(Empfehlung)**
2. `log10` in `band_math` aufnehmen, mit Toleranz zwischen Maschinen (T2 ↔ T2L nicht mehr bitgleich)
3. dB nur als Darstellung im tiler, kein Band im Ergebnis

**F3 — Operatoren mit Nachbarschaft?**
1. Neue Operator-Art `focal` mit Rand h, gebaut in M5-10 und von DS-05 genutzt. Job und Runner exakt und bitgleich; die Kachel rechnet im Kachelraster und ist immer „Preview“; in der Kachel nur als erster Schritt **(Empfehlung)**
2. Wie 1, aber die Kachel rechnet `focal` im Quellraster mit Rand und warpt danach: Kachel und Job bitgleich auf nativer Ebene, dafür ein eigener Kachelweg
3. `focal` nur als Job (T2), keine Vorschau

**F4 — Welche Speckle-Filter zuerst?**
1. Boxcar und Lee (Fenster 3–11, Vorgabe 7×7); Refined Lee, Gamma-MAP und Lee Sigma auf Wunsch später **(Empfehlung)**
2. Alle Filter aus SNAP auf einmal
3. Keine Speckle-Filter

**F5 — σ⁰-Kalibrierung für Sentinel-1 GRD?**
1. Ja, als DS-05d nach DS-04: LUT aus der Annotation über `gateway`, als Hilfsband mit derselben TPS gewarpt, Rauschabzug wählbar; für kalibrierte Bänder gelten dann Schwellen und RVI (Nachtrag zu `adr/0018` F3) **(Empfehlung)**
2. Nein, nur über RTC (`adr/0018` F6)
3. RVI schon auf DN, mit Hinweis „uncalibrated“

**F6 — Interferometrie und Kohärenz?**
1. Keine eigene InSAR. Global Coherence als Datensatz-Kandidat für die Pipeline (Datennähe nach `adr/0022` prüfen), LiCSAR prüfen, EGMS als Katalogeintrag mit Link **(Empfehlung)**
2. Zusätzlich ein Spike (Stufe C) mit dem LiveEO-Bestand (Deutschland, bis 12/2022), um Aufwand und Werkzeuge zu messen
3. Thema für M5 ganz zurückstellen

**F7 — Quick processing über Index-Presets hinaus?**
1. Zwei neue Registry-Felder: `composite_presets` (RGB aus drei Ausdrücken) und `step_presets` (ein T1-Schritt mit festen Parametern, z. B. „Hillshade“, „VV dB“); geprüft beim Start von `api` wie `index_presets` **(Empfehlung)**
2. Nur `composite_presets`; Gelände und dB bleiben im Processing-Panel
3. Nur Index-Presets wie heute

**F8 — Weitere Index-Presets für Sentinel-2?**
1. NDMI, MNDWI, NDREI, SAVI (L = 0,5), als Registry-Änderung der Stufe A; NDBI nicht, weil es −NDMI ist **(Empfehlung)**
2. Nur NDMI und MNDWI
3. Keine weiteren

**F9 — Klassenanteile bei WorldCover?**
1. Aus der vorhandenen Ergebnis-Statistik (für `uint8` exakt) mit Namen und Farben aus `mask`, als Folgeaufgabe nach M5-07 **(Empfehlung)**
2. Eigener Operator „zonales Histogramm“
3. Keine

**F10 — Operatoren über mehrere Eingaben oder Zeitschritte (Zeitkomposit, dNBR, Differenz der DEM-Stände, Klimaaggregation, Log-Ratio)?**
1. Eigener ADR (Stufe C) nach M5-11, wenn die Zeitachse der Meteorologie steht **(Empfehlung)**
2. Eigener ADR jetzt, parallel zu Welle 2
3. Nicht vor M6

---

## 11. Was offen bleibt und vor einer Umsetzung zu prüfen ist

- **Quellen mit Stufe S** an der Primärquelle lesen:
  - SNAP-Vorgaben der Speckle-Filter (Q15);
  - ESA-Kalibrierformel und Rauschabzug (Q18, Q19);
  - WorldCover-PUM (Q30);
  - EGMS-Lizenz (Q27);
  - LiCSAR-Zugang und Abdeckung (Q26);
  - `TminD`/`TmaxD` bei MeteoSchweiz (Q31);
  - Originalarbeiten Horn 1981, Zevenbergen & Thorne 1987, Lee 1980/1981.
  
  Dafür braucht eine Sitzung gdal.org, step.esa.int, sentinels.copernicus.eu, un-spider.org und nature.com, oder Otto liest sie.
- **SAVI:** L = 0,5 ist Modellwissen, im ASI-Eintrag nicht gelesen [A].
- **Kalibrier-XML bei Earth Search:** Asset oder Pfad aus `manifest.safe` (§5.2.1).
- **rio-tiler `buffer`:** in der Version der Lock-Datei prüfen (§3).
- **Faktoren in §7:** messen.
- **Komposit-Presets und Ansicht:** Die Kachel kann drei berechnete Bänder zeigen [P]. Ob die Ansicht (UI-03, NM4-64) RGB aus Schritten anbietet, prüft die Aufgabe zu F7.
- **Global Coherence:** Format der Mosaike (Overviews, Kacheln), Lizenz-Einstufung nach B11 (Otto), Datennähe (`adr/0022`).
- **ETCCDI:** Sommertage sind Tmax **> 25 °C**, nicht ≥ (Q32).

---

## 12. Quellen

Abgerufen am 06.11.2026.

**Gelesen bzw. gemessen:**

- **Q1** AWS Open Data Registry, `sentinel1-slc.yaml` (LiveEO): https://github.com/awslabs/open-data-registry/blob/main/datasets/sentinel1-slc.yaml — [P]; Bucket `sentinel1-slc` — [M]
- **Q2** AWS Open Data Registry, `sentinel1-slc-seasia-pds.yaml`: https://github.com/awslabs/open-data-registry/blob/main/datasets/sentinel1-slc-seasia-pds.yaml — [P]
- **Q3** AWS Open Data Registry, `s1-orbits.yaml`: https://github.com/awslabs/open-data-registry/blob/main/datasets/s1-orbits.yaml — [P]; README des Buckets — [M]
- **Q4** AWS Open Data Registry, `ebd-sentinel-1-global-coherence-backscatter.yaml`: https://github.com/awslabs/open-data-registry/blob/main/datasets/ebd-sentinel-1-global-coherence-backscatter.yaml — [P]; Bucket-Listing — [M]; J. Kellndorfer et al., „Global seasonal Sentinel-1 interferometric coherence and backscatter data set“, Scientific Data 9, 73 (2022), https://doi.org/10.1038/s41597-022-01189-6 — [S]

**Über Hilfsagenten gelesen [P\*] oder nur als Suchtreffer [S]:**

- **Q10** Awesome Spectral Indices, `spectral-indices-dict.json`: https://github.com/awesome-spectral-indices/awesome-spectral-indices — [P\*] (Teil gelesen); D. Montero et al., Scientific Data 10, 197 (2023), https://doi.org/10.1038/s41597-023-02096-0 — [S]
- **Q11** H. Xu, „Modification of normalised difference water index (NDWI)…“, Int. J. Remote Sens. 27 (2006), https://doi.org/10.1080/01431160600589179 — [S]
- **Q12** Disasters Charter, Burned Area Severity: https://docs.disasterscharter.org/services/burned-area-severity/service-specs/ — [S]
- **Q13** ESA, Sentinel-2 L2A Algorithmen und Produkte: https://sentinel.esa.int/web/sentinel/technical-guides/sentinel-2-msi/level-2a-algorithms-products — [S]
- **Q14** Sentinel Hub Custom Scripts, „RGB ratio“ und „Radar vegetation index“: https://custom-scripts.sentinel-hub.com/sentinel1-monthly-mosaic/rgb_ratio, https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel-1/radar_vegetation_index/ — [S]
- **Q15** STEP-Forum, Speckle-Filter in SNAP: https://forum.step.esa.int/t/s1tbx-speckle-filter-lee-sigma/25991 — [S]
- **Q16** J.-S. Lee et al., „Improved Sigma Filter for Speckle Filtering of SAR Imagery“, IEEE TGRS 47(1), 2009, https://doi.org/10.1109/TGRS.2008.2002881 — [S]
- **Q17** S. Quegan, J. J. Yu, „Filtering of multichannel SAR images“, IEEE TGRS 39(11), 2001, https://doi.org/10.1109/36.964973 — [S]
- **Q18** ESA, Sentinel-1 Level-1 Post-Processing Algorithms: https://sentinels.copernicus.eu/web/sentinel/level-1-post-processing-algorithms — [S]
- **Q19** ESA, „Thermal Denoising of Products Generated by the Sentinel-1 IPF“: https://sentinel.esa.int/documents/247904/2142675/Thermal-Denoising-of-Products-Generated-by-Sentinel-1-IPF — [S]
- **Q20** M. Nasirzadehdizaji et al., Applied Sciences 9(4), 655 (2019); Trudel et al. 2012 — über Q14 [S]
- **Q21** UN-SPIDER, Recommended Practice Flood Mapping: https://un-spider.org/advisory-support/recommended-practices/recommended-practice-flood-mapping/step-by-step — [S]
- **Q22** Orfeo Toolbox, SARDecompositions: https://www.orfeo-toolbox.org/Applications/SARDecompositions.html — [S]
- **Q23** PolSARpro, Decompositions: https://polsarpro.readthedocs.io/en/latest/decompositions/; S. R. Cloude, „The Dual Polarisation Entropy/Alpha Decomposition“, 2007 — [S]
- **Q24** D. Mandal et al., „Dual polarimetric radar vegetation index…“, Remote Sens. Environ. 247, 111954 (2020), https://doi.org/10.1016/j.rse.2020.111954 — [S]
- **Q25** OPERA DISP-S1 (Rechenaufwand): https://arxiv.org/abs/2511.12051 — [S]
- **Q26** M. Lazecký et al., „LiCSAR: An Automatic InSAR Tool…“, Remote Sens. 12(15), 2430 (2020), https://doi.org/10.3390/rs12152430; CEDA-Katalog: https://catalogue.ceda.ac.uk/uuid/52cda2e0e6c04272ae15ac836c1e8493/ — [S]
- **Q27** Copernicus Land, EGMS-Leitfaden: https://land.copernicus.eu/en/technical-library/guidelines-european-ground-motion-service-product-analysis-in-qgis — [S]
- **Q28** NASA Earthdata, OPERA: https://www.earthdata.nasa.gov/data/projects/opera — [S]
- **Q29** GDAL, `gdaldem` (Quelltext der Doku): https://github.com/OSGeo/gdal/blob/master/doc/source/programs/gdaldem.rst — [P\*]
- **Q30** ESA WorldCover, Product User Manual v2.0: https://pure.iiasa.ac.at/18983/1/WorldCover_PUM_V2.0.pdf — [S]
- **Q31** MeteoSchweiz, Open-Data-Doku „Spatial climate analyses“: https://opendatadocs.meteoswiss.ch/c-climate-data/c3-ground-based-climate-data — [P\*]; Produktdokumentation TabsD — [S]
- **Q32** ETCCDI, Liste der 27 Indizes: https://etccdi.pacificclimate.org/list_27_indices.shtml; X. Zhang et al., WIREs Climate Change 2 (2011), https://doi.org/10.1002/wcc.147 — [S]

**Im Repo:**

- Code:
  - `backend/earthx/processing/operators/registry.py`, `band_math.py`;
  - `backend/earthx/processing/core.py`, `plan.py`, `statistics.py`, `index_presets.py`;
  - `backend/earthx/catalog/registry.py`, `datasets.py`;
  - `backend/earthx/api/tiler.py`;
  - `backend/earthx/datasets/quad_pol_reference/decomp.py`;
  - `frontend/src/relief.ts`.
- ADRs: `adr/0014` §3.5, §5.2, §5.5, §6.1, §6.3, §12, §15c, §15k, §15v, §15 NM4-14; `adr/0018`; `adr/0023`; `adr/0027`.
- Pläne: NM4-14, UI-03 §7.12, DS-00, DS-05.
