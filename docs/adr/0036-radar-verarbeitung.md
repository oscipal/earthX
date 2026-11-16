# ADR 0036 — Radar-Verarbeitung für Sentinel-1 GRD (Reiter „Radar“)

- **Status:** **Entwurf** (Stufe C), Fragen an Otto in §13.
- **Datum:** 2026-11-16
- **Aufgabe:** M5-31 laut `docs/plans/m5/m5-discovery-und-suche.md` §6.2 und §2 Punkt 10. Die Nummer 0036 war beim Start frei: Auf `main` (af1ca04) endet die Reihe mit 0035, kein offener Branch legt ein ADR 0036 an. Beim Merge erneut prüfen.
- **Autonomiestufe:** C. Kein Produktivcode.
  - Geändert sind nur dieses ADR und eine Zeile im Entscheidungslog.
  - Unverändert bleiben `backend/`, `frontend/`, `scripts/`, Registry, Fixtures, M5-Plan, `.importlinter`, `.github/`, `.claude/`, `CODEOWNERS` und `CLAUDE.md`.
- **Vorab fest (Otto, 11.11.2026, M5-Plan §2 Punkt 10):**
  - Im Processing-Panel gibt es einen Reiter „Radar“ mit der Standard-Verarbeitung für Sentinel-1 GRD: Orbit, thermisches Rauschen und Randrauschen, Kalibrierung σ⁰/γ⁰, Speckle, Terrain Flattening, Geländekorrektur GTC/RTC, dB, Verhältnisse.
  - **Kein InSAR** (`adr/0030` F6 bleibt).
  - Sentinel-1 bleibt ohne richtige Bearbeitung (σ⁰ und Geländekorrektur) in Radargeometrie (DS-04d, `adr/0018` §9.5).
  - Keys der Nutzer sind erlaubt (`adr/0034`); Jobs mit Key kommen mit M5-48.
- **Weiter fest:**
  - Modulgrenzen nach `architekturplan.md` 3.1; ausgehende Requests nur über `gateway` (B8); Worker-Kern zustandslos und ohne Plattformdienste (B9).
  - Unterschiede je Datensatz stehen in der Registry, nicht im Code des Frontends; was nicht geht, erscheint nicht (B10, DS-00).
  - `decomp.py` ruht; Sentinel-1 ist Dual-Pol (`ENTSCHEIDUNGEN` §3).
  - Neue Abhängigkeiten nur mit Otto (`adr/0014` K9).
  - Keine Anfrage an echte Quellen aus dieser Sitzung; Messungen nur synthetisch (Auftrag).
- **Grundlage:**
  - `ENTSCHEIDUNGEN_2026-09-18.md` §1, §3; `KLAERUNGEN.md` B8, B9, B10, B11.
  - `architekturplan.md` 3.1, 7.3, 7.7; `projektuebersicht.md` Prinzipien 9, 10.
  - `adr/0014` (Kern, Bitgleichheit, Speicher), `adr/0016` (Runner), `adr/0018` (Sentinel-1, Teil C und F6), `adr/0030` (Operatoren je Datensatz, §5.2, F2–F6), `adr/0034` (Keys, M5-48), `adr/0035` (Looks am Operator).
  - Pläne: `plans/ds/ds-04-s1-anbinden.md`, `plans/m5/ds-04d-radargeometrie.md`, `plans/ds/ds-05-sar-operatoren.md`.
- **Betroffen (erst mit einer Entscheidung):** Registry (`sentinel-1-grd.yaml`, Capabilities, neue SAR-Angaben), `readers` (Annotation), `processing` (neue Operatoren, Planer: Georeferenz nach dem Schritt), Runner-Image, UI-07, Pläne DS-05d und folgende.

---

## Methode und Belegstufen

Belegstufen wie in `adr/0016` und `adr/0018`:

- **M:** in dieser Sitzung gemessen, nur an synthetischen Daten; Verfahren in §5.
- **M′:** in einer früheren Sitzung an echten Daten gemessen (Fundstelle genannt).
- **P:** am Primärdokument selbst gelesen (Quelltext auf GitHub, Paketcode oder Repo), mit Quelle in §15.
- **P\*:** über das Abrufwerkzeug eines Hilfsagenten gelesen; sinngemäß, vor einer Annahme zu prüfen.
- **S:** Suchtreffer oder Zusammenfassung, Wortlaut nicht geprüft.
- **A:** eigene Ableitung, ein Argument und kein Beleg.

**Anfragen an Datenquellen:** keine. Gelesen wurden nur Dokumentationen und Quelltexte auf GitHub und PyPI (Paketinstallation im Kratzverzeichnis). Für die Hilfsagenten waren `sentinel.esa.int`, `sentinels.copernicus.eu`, `forum.step.esa.int`, `mdpi.com`, `ceos.org`, `doi.org`, `planetarycomputer.microsoft.com`, `asf.alaska.edu` und `hyp3-docs.asf.alaska.edu` nicht erreichbar. Viele Fachaussagen tragen deshalb nur **S**; was vor einer Umsetzung zu lesen ist, steht in §14.

---

## 0. Kurzfassung

1. **Die Annotation fehlt im AWS-Bucket nicht** [M′][P]. Produkt-Annotation, Kalibrier- und Rausch-XML liegen je Szene im anonymen Bucket von Earth Search; DS-04d hat die Produkt-Annotation dort gelesen. Falsch ist nur der Verweis der STAC-Assets `schema-product-*` (zeigt auf die RFI-Annotation, #343). Kalibrierung und Rauschen sind ordentliche Assets. **Die ganze GRD-Kette geht damit token-frei aus derselben Quelle wie heute**; ein CDSE-Key (M5-48) ist dafür keine Voraussetzung (§3).
2. **Kette (§4):** Rauschabzug und Kalibrierung sind eine Pixelrechnung mit zwei LUTs und laufen blockweise im Worker-Kern: synthetisch 0,02 s je Megapixel und rund 100 MB bei Blöcken von 1024² [M]. Orbit aus den Zustandsvektoren der Annotation genügt für GRD (so macht es Sentinel Hub) [P]. Randrauschen setzt ESA seit IPF 2.90 (März 2018) selbst auf 0 [S]. Speckle in Radargeometrie (DS-05b). Geländekorrektur (GTC) und Terrain Flattening (RTC) brauchen Bahn, DEM und Geoid; das ist ein Job.
3. **Werkzeuge (§4.3):** sarsen (Apache-2.0, pip, Beta, 19 neue Pakete) passt als Bibliothek in den Kern, wenn die Plattform selbst liest und sarsen ein eigenes Produktobjekt gibt (kein I/O in sarsen, B8) [M][P]. SNAP/pyroSAR (GPL-3, Java) nur als Container (T3), ISCE3/OPERA nur für SLC-Bursts (conda) [P]. GDAL kalibriert SAFE seit 3.4, ohne Rauschabzug [P].
4. **Speicher (§5):** sarsen wächst mit der Fläche: synthetisch RTC 1,0 GB bei 4,2 Mpx und 1,7 GB bei 9,4 Mpx (Dask synchron) [M]; an echten Daten 11,8 GB bei 6,7 Mpx (`adr/0018` §6.2) [M′]. Nacheinander je Zielkachel gerechnet folgt der Speicher der Kachel, nicht der AOI (§5.2) [M]. Damit passt RTC unter die Grenze von 1,5 GB je Kindprozess.
5. **Fertige RTC-Produkte (§6):** keines ist anonym. OPERA RTC-S1 ist nahezu global (30 m, GLO-30, CC BY 4.0), aber nur mit Earthdata-Konto [P]; Planetary Computer verlangt ein Konto [P]; die Monatsmosaike von CDSE (20 m, RTC) nur mit CDSE-Konto über Sentinel Hub [P]. Als **Ergänzung** über Keys (`adr/0034`) sinnvoll, als **Ersatz** der eigenen Kette nicht.
6. **Nach richtiger Bearbeitung (§7):** Ein Ergebnis aus GTC oder RTC hat ein Kartenraster mit CRS. Damit gehen georeferenzierter Download, Reprojektion, Mosaik über Durchgänge und Bahnen, Vergleich mit anderen Datensätzen, Schwellen und später Zeitreihen. Radargeometrie bleibt für alles davor.
7. **Reiter „Radar“ (§8):** M5 wie geplant DS-05a–d (dB, Speckle, Komposit, σ⁰), DS-05d erweitert um Rauschabzug, Wahl σ⁰/β⁰/γ⁰-Ellipsoid und den Ort der Annotation; **M6** GTC/RTC als Job mit georeferenziertem Ergebnis, danach dB auf Gleitkomma, Wassermaske, RVI; **später** multitemporale Verfahren (eigener ADR, `adr/0030` F10) und fertige Produkte mit Key.

---

## 1. Kontext und Frage

Sentinel-1 GRD liegt heute als unkalibrierte DN in Radargeometrie vor (`adr/0018` Teil A, DS-04d). Für den Nutzer heißt das: kein σ⁰, keine Schwellen, kein georeferenzierter Download, kein Vergleich über Bahnen. Otto will im Processing-Panel einen Reiter „Radar“ mit der üblichen Standard-Verarbeitung (Vorgabe oben). `adr/0018` F6 hat dafür einen eigenen ADR zur Geländekorrektur nach DS-04 verlangt, mit der Kernfrage Speicher. Dieses ADR ist er, erweitert um die ganze Kette.

**Fragen des Auftrags:**

1. Die übliche GRD-Kette: Werkzeuge, Eingaben, Rechenzeit und Speicher je Szene und AOI, was im Worker-Kern und im Runner-Image geht.
2. Selbst rechnen oder fertige RTC-Produkte als Quelle: Genauigkeit, Abdeckung DACH, Lizenz, Zugang nach unseren Regeln.
3. Was mit georeferenziertem Download nach richtiger Bearbeitung möglich wird (DS-04d).
4. Welche Verarbeitungen in den Reiter „Radar“ gehören (inkl. DS-05a–d), als Registry-Angaben je Datensatz, und was in M5, M6 oder später.

---

## 2. Kriterien

| # | Kriterium | Woher |
|---|---|---|
| K1 | Zugang nach den Regeln: anonym zuerst, mit Key nur nach `adr/0034` | Prinzip 2; `adr/0034` |
| K2 | Fachlich richtig: physikalische Größe (σ⁰/γ⁰), Lage über DEM, ehrlich gekennzeichnet | Prinzip 9 |
| K3 | Worker-Kern zustandslos, Lesen nur über `gateway`, keine Plattformdienste | B8, B9 |
| K4 | Speicher je Kindprozess ≤ 1,5 GB (`processing/plan.py` `MAX_JOB_MEMORY_BYTES`); Speicher folgt dem Block, nicht der Szene | `adr/0014` M4-07a F11; `adr/0020` F5 |
| K5 | Bitgleich T2 ↔ T2L auf derselben Maschine; Abweichung zwischen Maschinen nur nach `adr/0014` §6.3 | `adr/0014`, `adr/0016` F8 |
| K6 | Abhängigkeiten: Lizenz verträglich mit AGPL-3.0-or-later, pip-Wheels, Größe im Runner-Image | `adr/0014` K9; M4-00b |
| K7 | Abdeckung DACH, Archiv tief, aktuell | M5-Plan §2 Punkte 1, 2 |
| K8 | Aufwand für 1 bis 3 Personen | `architekturplan.md` 1.1 |

---

## 3. Befund: Was die anonyme Quelle schon liefert

**Im Bucket je Szene** (`adr/0018` §3.1, gemessen 26.10.2026) [M′]: 27 Objekte in SAFE-Gliederung, darunter `manifest.safe`, `annotation/`, `annotation/calibration/`, `measurement/`. Die Messdateien sind eine COG-Umwandlung mit gekürzten Namen.

| Eingabe der Kette | im AWS-Bucket? | Beleg |
|---|---|---|
| Messdaten VV/VH (DN) | ja, COG mit GCPs | `adr/0018` §3.1 [M′] |
| Produkt-Annotation (`annotation/iw-<pol>.xml`): Zeiten, Bahn-Zustandsvektoren, Geolocation Grid, Slant-/Ground-Range-Umrechnung | **ja**; DS-04d hat sie gelesen. Nur der STAC-Verweis `schema-product-*` zeigt auf `annotation/rfi/…` | DS-04d Plan §2 [M′]; Log 11.11.2026 |
| Kalibrier-LUTs β⁰, σ⁰, γ, DN | ja, Asset `schema-calibration-<pol>` | DS-04 Plan §2 [M′] |
| Rausch-LUTs (Range, Azimut) | ja, Asset `schema-noise-<pol>` | `sentinel-1-grd.yaml` `auxiliary_assets` [P] |
| Pixelraster der Messdatei = Raster der Annotation | ja: GCPs der TIFF gleich dem Geolocation Grid (< 10⁻¹³°), Zeilenzeiten auf die µs | DS-04d Plan §2 [M′] |
| Präzise Bahn (POEORB) | eigener anonymer Bucket `s1-orbits` (ASF, `us-west-2`) | `adr/0030` §5.2.3 [P][M′]; §15 Q12 [P] |
| DEM | Copernicus DEM GLO-30, schon ein Datensatz der Plattform | `cop-dem-glo-30.yaml` [P] |
| Geoid EGM2008 (GLO-30 hat Höhen über EGM2008) | **nein**; sarsen holt es mit `PROJ_NETWORK=ON` von `cdn.proj.org` | `adr/0018` §6.2 [P]; sarsen README [P] |

**Folgerung [A]:** Die Prämisse „im AWS-Bucket fehlt die Annotation“ (M5-Plan §2 Punkt 10) stimmt so nicht. Es fehlt nur der richtige STAC-Verweis. Die Kette lässt sich aus der heutigen, anonymen Quelle rechnen, ohne CDSE und ohne Key. Offen bleibt, ob die COG-Umwandlung die DN unverändert lässt (zu erwarten bei verlustfreier Kompression, aber nicht gemessen; Messpunkt MP1 in §14). Die CDSE-COGs sind laut Doku per `gdal_translate -of COG … -co COMPRESS=ZSTD` gemacht, also verlustfrei [P].

**Lesen der Annotation [A]:** Der Pfad der Produkt-Annotation folgt aus dem fehlerhaften Asset durch eine feste Regel (`annotation/rfi/rfi-<x>.xml` → `annotation/<x>.xml`) oder aus `manifest.safe` mit der Namensabbildung des Buckets. Beides gehört als Angabe in die Registry, nicht in Code je Datensatz (§9).

---

## 4. Punkt 1: Die übliche GRD-Kette

### 4.1 Schritte und Stand der Technik

| # | Schritt | Was er tut | Stand der Technik | Wo im System [A] |
|---|---|---|---|---|
| 1 | Orbit | Bahn für die Geokodierung | POEORB nach rund 20 Tagen, cm-genau; RESORB nach rund 3 h [S]. Sentinel Hub nutzt die Zustandsvektoren der Annotation: „We find these more than sufficient for GRD use.“ [P] Absolute Lagegenauigkeit IW: Spezifikation 7 m (3σ) [S] | Annotation reicht für 10–20 m; POEORB später optional |
| 2 | Thermisches Rauschen | η aus Range- und Azimut-LUT abziehen | ESA-Technote MPC-0392; Azimut-Vektoren ab IPF 2.90; (DN² − η)/A², negative Werte auf 0 [S]; die IPF zieht es nicht selbst ab [S] | Pixelrechnung mit Hilfsbändern (B5), in Radargeometrie, mit Schritt 4 |
| 3 | Randrauschen | Ränder ohne gültige Werte | Seit IPF 2.90 (13.03.2018) setzt ESA sie in GRD selbst auf 0 [S]; ältere Produkte brauchen eine Maske; „The areas of border noise are not displayed by Sentinel Hub“ [P] | Registry-Grenze: Szenen vor IPF 2.90 ohne RTC oder mit Randmaske (F6) |
| 4 | Kalibrierung | β⁰/σ⁰/γ aus DN über LUT | β⁰ = DN²/A_β², σ⁰ = DN²/A_σ², LUTs bilinear [S]; GDAL kalibriert SAFE seit 3.4 (SIGMA0, BETA0, GAMMA), ohne Rauschabzug [P] | DS-05d; Pixelrechnung |
| 5 | Speckle | Glätten | Sentinel Hub filtert „right after calibration and noise removal … on source data“, Lee 1–7 [P]; `adr/0018` §4.4: Radargeometrie ist der beste Ort | DS-05b auf `focal` in Radargeometrie |
| 6 | Terrain Flattening | β⁰ → γ⁰ über die beleuchtete Fläche | Small 2011 (Flächenintegration) in SNAP, sarsen, Sentinel Hub, Catalyst [P]; winkelbasierte Näherung in GEE (Vollrath 2020, Mullissa 2021) [S] | Job (§4.2) |
| 7 | GTC/RTC | Range-Doppler-Geokodierung auf ein DEM-Raster | sarsen: „Terrain-corrected images will have the same pixels as the input DEM“ [P, `adr/0018` §6.2]; OPERA: flächenbasierte Projektion (Shiroma 2022) [P] | Job, Ausgabe mit CRS (§7) |
| 8 | dB | 10·log10 | am Ende [S] (Filipponi 2019) | `sar_db` (DS-05a); auf Gleitkomma mit Toleranzregel (`adr/0030` F2) |

**Ergebnisstandard:** CEOS-ARD „Normalised Radar Backscatter“ (NRB), aktuell v5.5: γ⁰ RTC, ungefiltert, je Pixel lokaler Einfallswinkel, Streufläche, Verhältnis σ→γ und Datenmaske (Layover, Schatten) [S]. OPERA RTC-S1 ist danach zertifiziert [S]. Die Plattform muss NRB nicht erfüllen, sollte aber dieselben Hilfsbänder liefern (§7.2) [A].

### 4.2 Was je Schritt nötig ist und wo es läuft [A]

- **Schritte 2 und 4** brauchen nur die Szene, ihre XML und Pixelrechnung. Sie laufen blockweise im Kern wie jeder Pixeloperator, in Radargeometrie, auch als Kachel (T1) möglich, wenn die LUT als Hilfsband mit derselben TPS gewarpt wird (`adr/0030` §5.2.1). Speicher folgt dem Block (§5.1).
- **Schritte 6 und 7** brauchen dazu Bahn, DEM und Geoid und eine Nachbarschaft, die weit über eine Kachel reicht (Layover hängt an Hängen außerhalb). Sie laufen nur als **Job** (T2, T2L). Die Kachel zeigt das Ergebnis über `/results`.
- **Reihenfolge:** 2+4 → 5 → 6+7 → 8. Speckle vor der Geokodierung, weil DS-04d die Daten bis dahin in Radargeometrie hält.

### 4.3 Werkzeuge

| Werkzeug | Lizenz | Schritte | Eingaben | Paketierung | Im Kern? |
|---|---|---|---|---|---|
| **sarsen** 0.9.6 (bopen, 23.06.2026) | Apache-2.0 [P] | GTC, RTC (Small 2011), Kalibrierung β⁰ über xarray-sentinel; **kein Rauschabzug, kein Randrauschen, kein Speckle** (kein Wort „noise“ im Paket) [P]; Status „beta“ [P]; offene Issues: Speicher (#75: 46,5 GiB bei einem 64-GiB-Worker, vor 0.9.6), RTC gegen SNAP 12 (#85: mit Geoid-korrigiertem DEM vergleichbar), Ergebnis hängt von der Chunkgröße ab (#89, bis rund 0,03) [P\*] | SAFE lokal/fsspec **oder** eigenes Produktobjekt (`GroundRangeSarProduct`) [P]; DEM auf Ellipsoid | pip; 19 Pakete nicht im Lock (dask, xarray, scipy, flox, xarray-sentinel …) [M] | ja, als Bibliothek ohne eigenes I/O (§5) |
| **xarray-sentinel** 0.9.7 (04.11.2026) | Apache-2.0 [P\*] | liest GRD und SLC, Kalibrier- und Rausch-LUTs, Bahn, GCPs [P]; Rauschen nur als Metadaten, kein Abzug [P\*] | SAFE | pip | nur, wenn SAFE-Namen stimmen (Bucket kürzt sie) |
| **pyroSAR** 0.40.0 + **SNAP** | pyroSAR MIT [P\*]; SNAP und Microwave Toolbox **GPL-3** [P]; s1tbx seit 08.04.2026 archiviert [P\*]; SNAP 14.0 vom 18.08.2026 [S] | ganze Kette nach Filipponi: Orbit, Rauschen, Randrauschen, Kalibrierung, Speckle, Range-Doppler-TC, dB [P\*] | SAFE/ZIP, Java 21 [S] | conda empfohlen [P\*]; Image mit SNAP 9 1,4–2 GB [P\*]; RAM laut Forum 12–16 GB, 20–27 min je Szene [S] | nein; nur T3-Container |
| **s1ard** 2.14 (Prototyp-NRB-Prozessor, auf pyroSAR) | MIT [P\*] | NRB aus GRD [P] | wie SNAP (SNAP 13) [P\*] | Dockerfile, mamba [P\*] | nein |
| **ISCE3** + **s1-reader** + OPERA `RTC` | Apache-2.0 [P] | RTC aus **SLC-Bursts**; s1-reader lädt Bursts aus SLC [P] | SLC, Orbit, DEM | conda-forge [P] | nein: kein GRD |
| **GDAL** (SAFE-Treiber) | MIT | Kalibrierung SIGMA0/BETA0/GAMMA seit 3.4 [P]; kein Rauschterm im Treiber [P\*] | SAFE mit Originalnamen | vorhanden | nur Kalibrierung, ohne Rauschen; Namen im Bucket passen nicht |
| **GAMMA** (HyP3), eo-tools, GEE-S1-ARD | GAMMA kommerziell [S]; eo-tools MIT, nur SLC-Bursts [P\*]; GEE-S1-ARD MIT, nur in Earth Engine [P\*] | — | — | — | nein |
| **Eigene Implementierung** (numpy, GDAL) | AGPL | alles außer Werkzeug-Validierung | Annotation, DEM | nichts Neues | ja, Aufwand groß (§10) |

---

## 5. Messung (synthetisch)

### 5.1 Rauschabzug und Kalibrierung [M]

`bench_calib.py` (Kratzverzeichnis): LUTs in der Form der GRD-Annotation (Vektoren alle 400 Zeilen, Werte alle 40 Pixel, Azimut-Rauschen je Zeile), separabel bilinear interpoliert, σ⁰ = max(DN² − η, 0)/A² in `float32`, numpy 2.5 der Projekt-venv, ein Kern.

| Raster | Block | Zeit | s je Mpx | Spitze (ganzer Prozess) |
|---|---|---|---|---|
| 4096² | 512² | 0,36 s | 0,022 | 51 MB |
| 4096² | 1024² | 0,39 s | 0,024 | 105 MB |
| 4096² | 2048² | 0,62 s | 0,037 | 257 MB |
| 16384² (268 Mpx) | 1024² | 5,7 s | 0,021 | 95 MB |

Eine ganze IW-Szene (rund 25 000 × 17 000 Pixel je Polarisation) braucht damit rund 9 s Rechnung je Polarisation; der Speicher folgt dem Block. Für eine AOI zählen nur ihre Pixel. Die Kosten liegen beim Lesen, nicht beim Rechnen [A].

### 5.2 GTC und RTC mit sarsen [M]

`bench_sarsen.py`: Kreisbahn in 693 km Höhe, rechts blickend, Einfallswinkel rund 35°; DEM in UTM 32N mit 10 m Pixeln und Relief von rund 1 500 m; GRD-Raster mit Zufallswerten, das die Fläche mit Rand deckt; sarsen bekommt ein **eigenes Produktobjekt** (Unterklasse von `GroundRangeSarProduct`) statt einer SAFE, wie es die Plattform täte. Aufruf `apps.do_terrain_correction`, RTC mit `gamma_bilinear`, Interpolation `nearest`. Ein Lauf je Prozess, Spitze als `ru_maxrss`; 4 Kerne, 15 GB. Leerlauf nach Import: 197 MB.

| DEM (Mpx, 10 m) | Fläche | GTC Dask-Threads | GTC synchron | RTC Dask-Threads | RTC synchron |
|---|---|---|---|---|---|
| 1024² (1,0) | 10 × 10 km | 1,7 s / 545 MB | 1,5 s / 446 MB | 2,6 s / 871 MB | 2,7 s / 611 MB |
| 2048² (4,2) | 20 × 20 km | 4,8 s / 1 417 MB | 6,0 s / 779 MB | 6,5 s / 1 829 MB | 11,4 s / 1 040 MB |
| 3072² (9,4) | 31 × 31 km | 10,0 s / 1 858 MB | 13,4 s / 1 223 MB | 14,2 s / 2 547 MB | 25,3 s / 1 688 MB |
| 4096² (16,8) | 41 × 41 km | 16,7 s / 2 498 MB | 23,5 s / 1 640 MB | 25,1 s / 3 688 MB | 45,5 s / 2 596 MB |

**Nacheinander je Zielkachel** (`bench_tiled.py`: Zielkacheln von 1024² mit Rand 128, je Kachel ein eigener Aufruf, Ergebnis nur innen behalten):

TILEDTABLE

**Gegen die Messung an echten Daten** [M′] (`adr/0018` §6.2): RTC 10 m über 6,7 Mpx in 51 s mit 11,8 GB (Dask-Threads), GTC 16 s mit 2,2 GB. Synthetisch ist RTC rund dreimal schneller und braucht ein Viertel des Speichers [A]. Wahrscheinlicher Grund: Dort war die ganze Szene (rund 430 Mpx) das Produkt, und `geocode_grd_chunk` interpoliert aus dem ganzen β⁰-Feld; hier deckt das Produkt nur die AOI mit Rand. Die Plattform schneidet ohnehin zuerst das Pixel-Fenster der AOI aus (`access/radar.py`, DS-04d) und gäbe sarsen nur dieses [A]. Ob das an echten Daten so aufgeht, ist Messpunkt MP2.

**Folgerungen [A]:**

- sarsen ohne Kacheln wächst mit der Fläche; mit 1,5 GB je Kindprozess hielte RTC synchron nur bis rund 6 Mpx (≈ 25 × 25 km bei 10 m).
- Je Zielkachel nacheinander gerechnet bleibt der Speicher bei der Kachel; die Fläche bestimmt nur die Zeit. Das ist dieselbe Regel wie im Kern („der Speicher folgt dem Block“, `adr/0014` M4-07a F11).
- **Dask synchron**, nicht mit Threads: weniger Speicher, und die Reihenfolge der Summen in `flox` hängt dann nicht von Fäden ab (K5). Bitgleich zwischen Maschinen ist es wegen `float64`-Newton-Iterationen und `sin`/`cos` in PROJ nicht (`adr/0016` F8 gilt).
- Zeit: rund 2,7 s je Mpx RTC synchron, synthetisch; an echten Daten eher das Mehrfache. Eine AOI von 20 × 20 km in 10 m: Sekunden bis eine Minute, dazu das Lesen. Eine ganze Szene in 10 m (rund 430 Mpx): grob 20 min auf einem Kern; die README nennt rund 25 min auf einem 32-GB-Laptop [P]. In 20 m ein Viertel.

### 5.3 Runner-Image [M][A]

- sarsen 0.9.6 installiert sich gegen `backend/requirements.lock` ohne Konflikt und bringt dieselben **19 Pakete** wie am 26.10.2026 (`adr/0018` §6.2) [M]; sarsen ist weiter 0.9.6, xarray-sentinel 0.9.7 [M, PyPI-Index].
- Dazu käme das Geoid-Gitter EGM2008 ins Image (Größe offen, Messpunkt MP3), weil `PROJ_NETWORK=ON` an `gateway` vorbei ins Netz ginge (B8) [A].
- SNAP käme nur als eigenes Container-Image (T3) in Frage; Java, GPL-3 und mehrere GB [S]. GPL-3 ist mit AGPL-3.0 verträglich, solange SNAP ein getrenntes Programm bleibt [A].

---

## 6. Punkt 2: Selbst rechnen oder fertige RTC-Produkte

| Produkt | DACH | Zugang | Lizenz | DEM, Raster | Anmerkungen |
|---|---|---|---|---|---|
| **Eigene Kette** aus Earth Search GRD | ja | anonym | Sentinel Data Legal Notice, wie heute | GLO-30, Raster nach Wahl (UTM, 10/20 m) | gleiche Szenen wie der GRD-Datensatz; Validierung eigene Aufgabe |
| Planetary Computer `sentinel-1-rtc` (Catalyst) | ja (global) | „A Planetary Computer account is required to retrieve SAS tokens to read the RTC data“, `msft:requires_account: true` [P]; alle Assets nur mit Token [P] | CC-BY-4.0 [P] | PlanetDEM, UTM, „not shifted to any specific grid“ [P] | Ottos Messung F5 (`adr/0018` §11 C) steht aus; gemeldete Lücken [S] |
| NASA/JPL **OPERA RTC-S1** | ja: „near global scope“ [P] | `ControlledAccess` mit Earthdata-Zugang [P]; Earthdata Login [S] | CC BY 4.0 [P] | GLO-30, Burst je Produkt, UTM 30 m [P]; aus SLC [P] | Lagegenauigkeit < 6 m (Anforderung) [S]; ab 2016-04-14 laufend [P]; statische Layer separat [P]; Key-Weg nach `adr/0034` §6.2 (Earthdata) |
| ASF HyP3 On-Demand RTC (GAMMA) | ja, auf Abruf | Konto, 8 000 Credits/Monat, RTC 10 m = 60 Credits [S] | HyP3+ CC0, Basic offen [S] | GLO-30, 10/20/30 m [S] | Auftragsdienst, externe Engine (T4) |
| CDSE Sentinel Hub `GAMMA0_TERRAIN` | ja | CDSE-Konto, OAuth, Processing Units [P] | Copernicus | Copernicus DEM 10/30 m [P] | gerechnete Bilder, keine Datei der Quelle; `adr/0034` F4 hat zuerst nur S3-Schlüssel gewählt |
| CDSE **Sentinel-1 Monthly Mosaics** (Level 3) | ja | Sentinel Hub BYOC mit OAuth [P] | Copernicus Legal Notice [S] | Copernicus DEM **10 m über Europa**, 20 m (IW), UTM-Kacheln 100 km, COG 16 Bit [P] | Monatsmittel, keine Einzelszenen; RTC mit Flächenintegration, Gewichtung nach Small 2012 [P] |
| ESA Sentinel-1 NRB | offen | nicht belegt | — | MGRS, 10 m (Spezifikation) [S] | in Entwicklung [S] |
| DLR S1-NRB (terrabyte) | offen | vermutlich Konto [S] | CC BY 4.0 [S] | 10 m [S] | prüfen |
| EODC/TU Wien SIG0 20 m, ACube (AT), Swiss Data Cube (CH) | ja / AT / CH | teils STAC offen, Daten offen unklar [S] | offen [S] | σ⁰ ohne Flattening bzw. GAMMA-RTC [S] | prüfen, Lizenz durch Otto |

**Bewertung [A]:**

- **Keines der fertigen Produkte ist anonym.** Nach `adr/0034` ginge OPERA mit Earthdata-Key und die CDSE-Mosaike mit CDSE-Key; beides sind eigene Datensätze mit Onboarding und Lizenz-Einstufung durch Otto.
- **Genauigkeit:** OPERA ist validiert (Anforderung < 6 m) und NRB-konform [S]; eine eigene Kette mit sarsen ist es nicht (keine veröffentlichte Validierung, `adr/0018` §6.2). Für die eigene Kette braucht es einen Vergleich, am einfachsten gegen OPERA an derselben Stelle (Messpunkt MP4 für Otto mit Earthdata-Konto).
- **Fertige Produkte decken den Reiter „Radar“ nicht ab:** Sie sind ein anderer Datensatz (30 m, Burst-Raster, Monatsmittel), nicht ein Schritt auf der GRD-Szene, die der Nutzer gerade sieht. Der Reiter verarbeitet *die ausgewählte Szene*.
- **Empfehlung:** eigene Kette als Hauptweg (anonym, gleiche Szenen, Raster nach Wahl); OPERA RTC-S1 und die CDSE-Mosaike als **Ergänzung** über Keys nach M6 prüfen (F3). Planetary Computer bleibt an Ottos Messung (`adr/0018` F5).

---

## 7. Punkt 3: Nach richtiger Bearbeitung georeferenziert

### 7.1 Was sich ändert [A]

DS-04d: „ohne richtige Bearbeitung (σ⁰ und Geländekorrektur) nie georeferenziert“. Ein Ergebnis aus GTC oder RTC liegt im Raster des DEM bzw. eines Zielrasters mit CRS; die Lage kommt aus Bahn und DEM, nicht aus den Passpunkten. Damit wird möglich, was `adr/0018` §4.4 und DS-04d heute sperren:

| Heute gesperrt | nach GTC/RTC |
|---|---|
| Download nur als Pixel-Fenster ohne CRS mit GCPs | COG mit CRS, Geotransform und Übersichten; GIS liest es direkt |
| `reprojection: false` | Reprojektion des Ergebnisses (auf Raster anderer Datensätze) |
| Mosaik nur je Durchgang in Radargeometrie | Mosaik über Durchgänge, Bahnen und Satelliten im Kartenraster |
| kein Vergleich über Bahnen | Vergleich auf- und absteigend (γ⁰ RTC macht sie vergleichbar, Restunterschiede bleiben) |
| keine festen Schwellen auf DN | Schwellen auf σ⁰/γ⁰ in dB (Wasser), wie `adr/0030` F5 nach σ⁰ |
| kein Vergleich mit anderen Datensätzen | zwei Bilder vergleichen (M5-26), Stapel mit Sentinel-2 oder dem DEM |
| keine Zeitreihe | Grundlage für Operatoren über mehrere Zeitschritte (eigener ADR, `adr/0030` F10) |

### 7.2 Was das Ergebnis tragen muss [A]

- **Bänder:** γ⁰ (RTC) oder σ⁰ (GTC) linear in `float32`; dazu als Hilfsbänder Layover-/Schattenmaske und lokaler Einfallswinkel, wie NRB [S]; im Band-Menü mit Einheit „1“ bzw. „°“.
- **Provenienz:** DEM-Datensatz und Fassung, Geoid, Orbit-Quelle (Annotation oder POEORB), Werkzeug und Version, Zielraster, Chunking (`adr/0018` §6.2: Ergebnis hängt von der Chunkgröße ab).
- **Namensnennung:** zusätzlich zur Sentinel-Nennung die des abgeleiteten DEM, „produced using Copernicus WorldDEM-30“ (`cop-dem-glo-30.yaml` `attribution_modified`) [P]. Ob die Nennung des DEM für ein Produkt nötig ist, das das DEM nur zur Korrektur nutzt, legt Otto fest (Lizenzfrage).
- **Planer:** Der Schritt GTC/RTC wechselt die Georeferenz des Stroms von `gcp_tps` auf `crs`. Erst danach erscheint „Reproject“. Allgemein als Eigenschaft des Operators (Ausgabe-Georeferenz), nicht als Ausnahme für Sentinel-1.
- **Zielraster:** UTM-Zone der AOI-Mitte, 10 oder 20 m; das DEM wird bilinear auf das Zielraster gebracht, weil sarsen im DEM-Raster rechnet [P]. Für GLO-30 (30 m) heißt 10 m ein feineres Raster als das DEM; die Genauigkeit des Flattenings hängt daran (Truckenbrodt 2019 untersucht genau das [S]). Vorschlag: Vorgabe 20 m, 10 m wählbar (F5).
- **„Approximate geolocation“** entfällt für das Ergebnis; die Grenze „Lage über DEM 30 m, Höhenfehler GLO-30 < 4 m LE90 [S]“ steht in `limitations` des Ergebnisses.

---

## 8. Punkt 4: Inhalt des Reiters „Radar“

### 8.1 Verarbeitungen

| Eintrag im Reiter | Operator / Preset | Stufe | Eingabe | Capability | Aufgabe | wann |
|---|---|---|---|---|---|---|
| VV dB, VH dB | `sar_db` (Wertetabelle) als `step_presets` | T1, T2 | DN | `sar_backscatter` | DS-05a | M5 (Abnahme) |
| Dual-pol RGB | `composite_presets` | T1 | DN bzw. σ⁰ | `sar_backscatter` | DS-05c | M5 |
| Speckle Boxcar, Lee | `focal` in Radargeometrie | T1 Preview, T2 | DN bzw. σ⁰ | `sar_backscatter` | DS-05b | M5 oder danach |
| Kalibrierung σ⁰ (β⁰, γ-Ellipsoid wählbar) mit Rauschabzug | Pixeloperator mit Hilfsbändern (B5) | T2, später T1 | DN + LUTs | `sar_calibration` | DS-05d (erweitert, F6) | M5 oder danach |
| VV/VH-Verhältnis, Differenz in dB | `band_math` | T1, T2 | σ⁰ | `band_math` | vorhanden | mit DS-05d |
| RVI 4·σVH/(σVV+σVH) | `index_presets` | T1 | σ⁰ | `sar_calibration` | nach DS-05d | M5/M6 |
| **Geländekorrektur GTC (σ⁰) / RTC (γ⁰)**, Ausgabe mit CRS, Masken, lokaler Einfallswinkel | neuer Job-Operator `sar_terrain` | T2, T2L | σ⁰/β⁰ + Annotation + DEM | `sar_terrain_correction` (neu) | DS-05e (neu) | **M6** |
| dB auf Gleitkomma | `sar_db` mit Toleranzregel | T1, T2 | σ⁰/γ⁰ | `sar_backscatter` | `adr/0030` F2 (später) | M6 |
| Wassermaske mit Schwelle des Nutzers | `mask_values` | T1, T2 | σ⁰/γ⁰ in dB | `value_masking` (nach σ⁰ freigeben) | DS-06 | M6 |
| Reproject, Mosaik über Bahnen | vorhanden | T2 | Ergebnis mit CRS | `reprojection` am Ergebnis | DS-05f (neu, Planer) | M6 |
| Präzise Bahn (POEORB) | Option am Operator | T2 | `s1-orbits` | — | DS-05e oder später | später |
| Multitemporaler Speckle (Quegan), Log-Ratio, Zeitmittel | Mehrere Eingaben (B6) | T2 | γ⁰ einer Bahn | — | ADR nach M5-11 (`adr/0030` F10) | später |
| OPERA RTC-S1, CDSE-Mosaike | eigene Datensätze mit Key | — | — | — | Onboarding nach `adr/0034` | nach M6 |
| InSAR, Kohärenz, Pauli, H-α | — | — | — | — | ausgeschlossen (`adr/0030` F6) | nie (bis neue Lage) |

Die Reihenfolge im Reiter folgt der Kette (§4.1). Was eine Capability des Datensatzes nicht freischaltet, erscheint nicht (B10). Der Reiter ist eine Eigenschaft des Operators bzw. Presets (wie die Looks in `adr/0035`), nicht des Datensatzes; UI-07 legt die Form fest.

### 8.2 Registry-Angaben je Datensatz (Vorschlag)

| Angabe | Sentinel-1 GRD | Zweck |
|---|---|---|
| `capabilities.sar_backscatter` | `true` | DS-05a (schon in `adr/0030` §8) |
| `capabilities.sar_calibration` | `true` | DS-05d |
| `capabilities.sar_terrain_correction` | `true` | neu: GTC/RTC; setzt `sar_calibration` und `georeferencing: gcp_tps` voraus |
| `sar_quantity` | `{vv: amplitude, vh: amplitude, hh: amplitude, hv: amplitude}` | `adr/0030` §8 |
| `sar_annotation` | Ort von Produkt-Annotation, Kalibrierung, Rauschen je Polarisation: Asset-Schlüssel oder Pfadregel (heute: Kalibrierung und Rauschen als Asset, Produkt über die Regel `annotation/rfi/rfi-` → `annotation/`) | neu; Befund #343 |
| `sar_orbit` | `annotation` (später `poeorb` mit Quelle) | neu |
| `sar_terrain_dem` | `cop-dem-glo-30` (Datensatz-ID der Registry), Geoid `egm2008` | neu; das DEM ist ein zweiter Eingang des Rezepts, aufgelöst beim Planen (B9) |
| `sar_ipf_min` | Szenen vor IPF 2.90 ohne `sar_terrain_correction` oder mit Randmaske | neu (F6) |

Für Ergebnisse: Der Operator `sar_terrain` meldet `output_georeferencing: crs`; der Planer schaltet `reprojection` für die folgenden Schritte frei. Keine Angabe je Datensatz nötig.

### 8.3 M5, M6, später

- **M5** (Abnahme: DS-04 und DS-05a; `adr/0030` F1, M5-Plan §7 Punkt 9): DS-05a, DS-05c; DS-05b und DS-05d dürfen nach M5 folgen. DS-05d wird erweitert (F6).
- **M6:** DS-05e (GTC/RTC als Job), DS-05f (georeferenzierte Ergebnisse im Planer, Reprojektion und Mosaik danach), dB auf Gleitkomma, Wassermaske, RVI.
- **Später:** POEORB, multitemporale Verfahren (eigener ADR), fertige RTC-Produkte mit Key, Validierung gegen OPERA.

Grund für RTC erst in M6 [A]: M5 ist Discovery und Suche; die Abnahme von M5 verlangt nur DS-05a. RTC bringt 19 Pakete und das Geoid ins Runner-Image, einen neuen Operator mit zweitem Eingang (DEM) und eine Planerregel. Das ist eher die Größe eines eigenen Pakets (rund vier PRs, `adr/0018` §6.3).

---

## 9. Worker-Kern, `gateway` und Runner [A]

- **Lesen:** GRD-Fenster über `readers` (wie DS-04d, `CogReader.raw`), Annotation, LUTs und DEM über `gateway` und `readers`. sarsen bekommt nur Arrays und ein Produktobjekt; sein eigenes Lesen (fsspec, `PROJ_NETWORK`) bleibt aus. Gemessen geht das: §5.2 nutzt genau diesen Weg [M].
- **Kein Plattformdienst:** Der Operator braucht weder Datenbank noch Objektspeicher; das DEM ist ein aufgelöster Eingang des Rezepts wie die Szene (B9).
- **Kein Key:** Die Kette läuft auf der anonymen Quelle; M5-48 ist keine Voraussetzung (§3). Ein CDSE-Datensatz mit Key könnte denselben Operator später nutzen, wenn er dieselbe Annotation liefert.
- **Speicher:** je Zielkachel nacheinander (§5.2), Schätzung in `plan.memory_needed` mit eigenem Faktor; Dask synchron.
- **Runner (T2L):** derselbe Kern; das Image wächst um die 19 Pakete und das Geoid (MP3). Die Zusage zur Bitgleichheit gilt wie `adr/0016` F8 präzisiert: gleich auf derselben Maschine.
- **Importregeln:** sarsen, dask und xarray nur in `processing` (bzw. einem Untermodul für SAR); `gateway`-Regeln unverändert. Ob sarsen `fsspec` oder `requests` importiert, prüft die Umsetzung mit `lint-imports`; die Verbotsliste `http-only-in-gateway` darf dafür nicht gelockert werden (nur Otto).

---

## 10. Optionen im Überblick

| Option | Kette | Werkzeug GTC/RTC | Quelle | Aufwand | Abhängigkeiten |
|---|---|---|---|---|---|
| **1 (Empfehlung)** | σ⁰ mit Rauschabzug in M5 (DS-05d), GTC/RTC als Job in M6 | sarsen als Bibliothek, eigenes Produktobjekt, kachelweise, synchron | Earth Search GRD, anonym | mittel (DS-05d erweitert; DS-05e/f je 1–2 PRs) | 19 Pakete, Geoid im Image |
| 2 | wie 1 | eigene Implementierung (Range-Doppler mit Newton, Flächenprojektion nach Small 2011) in numpy | wie 1 | groß; Genauigkeit selbst nachweisen | keine neuen Pakete |
| 3 | wie 1 | SNAP über pyroSAR im eigenen Container (T3) | wie 1, SAFE nachgebaut | groß; Image mehrere GB, Java | GPL-3, Java |
| 4 | nur σ⁰ (DS-05d); RTC nur als fertiges Produkt (OPERA, CDSE-Mosaike) über Keys | — | Earthdata/CDSE mit Key | Onboarding je Datensatz, M5-48 nötig | keine; Konten der Nutzer |

| | K1 | K2 | K3 | K4 | K5 | K6 | K7 | K8 |
|---|---|---|---|---|---|---|---|---|
| 1 | ✓ | ~ (nicht validiert, MP4) | ✓ ohne I/O in sarsen | ✓ kachelweise | ~ gleiche Maschine | ~ 19 Pakete, Beta | ✓ | ✓ |
| 2 | ✓ | ~ (selbst zu validieren) | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |
| 3 | ✓ | ✓ (verbreitet) | ✗ T3 ohne Netz, Eingaben vorab | ✗ GB je Lauf | ~ | ✗ | ✓ | ✗ |
| 4 | ~ Key | ✓ (OPERA validiert) | ✓ | ✓ | — | ✓ | ~ nicht die Szene des Nutzers | ~ |

---

## 11. Empfehlung

1. **Quelle bleibt Earth Search GRD** (anonym): Annotation über eine Registry-Regel, Kalibrierung und Rauschen als Assets (F1).
2. **DS-05d erweitern:** σ⁰ mit Rauschabzug (Range und Azimut), Wahl β⁰/σ⁰/γ-Ellipsoid, Grenze für Szenen vor IPF 2.90 (F6).
3. **GTC/RTC in M6 als Job-Operator `sar_terrain`** mit sarsen als Bibliothek, eigenem Produktobjekt, kachelweise und synchron; DEM GLO-30 als zweiter Eingang; Geoid EGM2008 im Image; Bahn aus der Annotation (F2, F7, F8).
4. **Nach GTC oder RTC** ist das Ergebnis georeferenziert (F4) mit Masken, Einfallswinkel und Provenienz.
5. **Fertige Produkte** als Ergänzung über Keys nach M6 prüfen (OPERA zuerst, dann CDSE-Mosaike); Planetary Computer nach Ottos Messung (F3).
6. **Reiter „Radar“** nach §8.1; Reiter als Eigenschaft des Operators (F5).

---

## 12. Schnitt (Vorschlag)

| Aufgabe | Inhalt | Stufe | wann | hängt ab von |
|---|---|---|---|---|
| DS-05d (erweitert) | σ⁰/β⁰/γ-Ellipsoid mit Rauschabzug, `sar_annotation`, `sar_ipf_min`; Tests synthetisch gegen unabhängige Rechnung | B | M5 oder danach | DS-05a; F1, F6 |
| DS-05e | Operator `sar_terrain` (GTC/RTC), sarsen und Geoid ins Image, Messung an zwei echten Szenen (Hügel- und Bergland) mit Speicher und Zeit, Vergleich GTC ↔ TPS-Lage | B | M6 | DS-05d; F2, F7, F8; MP1–MP3 |
| DS-05f | Planer: Ausgabe-Georeferenz am Operator, Reprojektion und Mosaik nach `sar_terrain`; Download mit CRS; Namensnennung DEM | B | M6 | DS-05e; F4 |
| UI-07 | Reiter im Processing-Panel, Radar nach §8.1 | B | wie geplant | dieses ADR, M5-26, `adr/0034` |
| Prüfung OPERA RTC-S1 | Datensatz-Vorlage mit Earthdata-Key; Vergleich mit eigener RTC (MP4) | C | nach M6 | `adr/0034` |

---

## 13. Fragen an Otto

**F1 — Quelle der Radar-Kette?**
1. Earth Search GRD (anonym, wie heute); Produkt-Annotation über eine Registry-Regel, weil der STAC-Verweis auf die RFI-Datei zeigt **(Empfehlung)**
2. CDSE mit Key des Nutzers (vollständige SAFE), erst nach M5-48
3. Beide: anonym als Vorgabe, CDSE für Szenen, die auf AWS fehlen

**F2 — Werkzeug für GTC/RTC?**
1. sarsen als Bibliothek im Kern, ohne eigenes I/O, kachelweise, synchron; 19 neue Pakete in Image und Runner **(Empfehlung)**
2. Eigene Implementierung in numpy ohne neue Pakete (größerer Aufwand, Genauigkeit selbst nachweisen)
3. SNAP/pyroSAR als eigener Container (T3)
4. Keine eigene GTC/RTC; nur fertige Produkte mit Key

**F3 — Fertige RTC-Produkte?**
1. Als Ergänzung nach M6 prüfen: OPERA RTC-S1 (Earthdata-Key) zuerst, dann CDSE-Monatsmosaike (CDSE-Key); Planetary Computer bleibt an deiner Messung **(Empfehlung)**
2. Statt der eigenen Kette
3. Nicht weiter verfolgen

**F4 — Was zählt als „richtige Bearbeitung“ für einen georeferenzierten Download (DS-04d)?**
1. GTC (σ⁰, geokodiert mit DEM) und RTC (γ⁰) **(Empfehlung)**
2. Nur RTC (γ⁰)
3. Auch σ⁰ ohne Geländekorrektur (über die TPS)

**F5 — Reiter „Radar“ und Zielraster?**
1. Inhalt und Zuordnung M5/M6/später wie §8.1; Reiter als Angabe am Operator; Zielraster der Geländekorrektur UTM, Vorgabe 20 m, 10 m wählbar **(Empfehlung)**
2. Wie 1, Vorgabe 10 m
3. Erst M5-Teil (DS-05a–d), GTC/RTC und Reiter-Inhalt nach M6 neu vorlegen

**F6 — DS-05d erweitern?**
1. Ja: Rauschabzug (Range und Azimut), Wahl β⁰/σ⁰/γ-Ellipsoid, Ort der Annotation als Registry-Angabe, Szenen vor IPF 2.90 (März 2018) ohne Geländekorrektur **(Empfehlung)**
2. Nur σ⁰ wie in `adr/0030` F5 beschrieben, Rest mit DS-05e
3. Wie 1, aber alte Szenen mit eigener Randmaske statt Sperre

**F7 — Bahn?**
1. Zustandsvektoren der Annotation; POEORB aus `s1-orbits` (anonym) später als Option **(Empfehlung)**
2. POEORB von Anfang an (neuer Host, Szenen jünger als rund 20 Tage ohne RTC oder mit RESORB)

**F8 — Geoid für GLO-30?**
1. Gitter EGM2008 im Image, kein Netz für PROJ (B8) **(Empfehlung)**
2. `cdn.proj.org` über `gateway` freigeben (`PROJ_NETWORK` geht an `gateway` vorbei, braucht eigene Lösung)

---

## 14. Was offen bleibt

**Messpunkte** (keine Anfrage aus dieser Sitzung):

- **MP1** DN der Bucket-COG gleich den DN der ESA-TIFF? Ein Block einer Szene im AWS-Bucket gegen dieselbe Szene bei CDSE (Otto mit eigenem Konto, oder DS-05e über `gateway`).
- **MP2** sarsen an echten Szenen nur auf dem AOI-Fenster mit Rand: Zeit, Speicher, Unterschied zur ganzen Szene; Lage gegen die TPS (DS-05e).
- **MP3** Größe des EGM2008-Gitters im Image; Lizenz des Gitters (PROJ-data).
- **MP4** Vergleich eigene RTC ↔ OPERA RTC-S1 an zwei DACH-Stellen (Otto mit Earthdata-Konto; keine Stelle ins Repo).
- **MP5** Ob sarsen beim Import `fsspec`/`requests` lädt (Importregeln).

**Zu lesen** (Hosts in dieser Sitzung gesperrt): ESA-Technote MPC-0392 (Rauschen) und ESA-EOPG-CSCOP-TN-0002 (Kalibrierung), IPF-2.90-Hinweis zum Randrauschen, CEOS-ARD NRB v5.5, Truckenbrodt 2019 (DEM-Auflösung und Flattening), OPERA-Produktspezifikation (Genauigkeit), Bedingungen der CDSE-Mosaike, Lizenz und Zugang von DLR S1-NRB, EODC SIG0, ACube und Swiss Data Cube.

**Offen ohne Messung:** Lizenzfrage DEM-Nennung in RTC-Ergebnissen (Otto); Faktor für die Kostenschätzung von `sar_terrain`; ob die Kachel σ⁰ zeigen soll (B5 als T1).

---

## 15. Quellen

Abgerufen am 16.11.2026.

**Gelesen [P] (Quelltext auf GitHub bzw. installiertes Paket):**

- **Q1** sarsen, README und Paketcode 0.9.6 (`apps.py`, `datamodel.py`, `radiometry.py`): https://github.com/bopen/sarsen, https://pypi.org/project/sarsen/0.9.6/
- **Q2** xarray-sentinel, README: https://github.com/bopen/xarray-sentinel
- **Q3** OPERA `RTC`, README und LICENSE: https://github.com/opera-adt/RTC
- **Q4** s1-reader, README: https://github.com/isce-framework/s1-reader
- **Q5** ISCE3, README und LICENSE: https://github.com/isce-framework/isce3
- **Q6** AWS Open Data Registry, OPERA RTC-S1: https://github.com/awslabs/open-data-registry/blob/main/datasets/nasa-operal2rtc-s1v1.yaml
- **Q7** Planetary Computer, `sentinel-1-rtc` Template und Beschreibung: https://github.com/microsoft/planetary-computer-tasks/tree/main/datasets/sentinel-1-rtc/collection; `sas.md`: https://github.com/microsoft/PlanetaryComputerDataCatalog/blob/main/docs/concepts/sas.md
- **Q8** CDSE-Doku, Sentinel-1 Monthly Mosaics (Algorithmus, Zugang): https://github.com/eu-cdse/documentation/blob/publish/Data/Others/Sentinel1_Mosaic_Algorithm.qmd, …/Sentinel1_Mosaic_access.qmd
- **Q9** CDSE-Doku, Sentinel Hub S1 GRD (Verarbeitungskette, `backCoeff`, Speckle, Orbit, Rauschen): https://github.com/eu-cdse/documentation/blob/publish/APIs/SentinelHub/Data/S1GRD.qmd
- **Q10** CDSE-Doku, Sentinel-1 COG: https://github.com/eu-cdse/documentation/blob/publish/Data/Others/Sentinel1_COG.qmd
- **Q11** GDAL, SAFE-Treiber: https://github.com/OSGeo/gdal/blob/master/doc/source/drivers/raster/safe.rst
- **Q12** AWS Open Data Registry, `s1-orbits.yaml`: https://github.com/awslabs/open-data-registry/blob/main/datasets/s1-orbits.yaml
- **Q13** SNAP Engine und Microwave Toolbox, LICENSE (GPL-3): https://github.com/senbox-org/snap-engine, https://github.com/senbox-org/microwave-toolbox
- **Q14** pyroSAR, README: https://github.com/johntruckenbrodt/pyroSAR; s1ard, README: https://github.com/SAR-ARD/s1ard

**Über Hilfsagenten gelesen [P\*]:**

- **Q15** sarsen, Releases und Issues #75, #85, #89: https://github.com/bopen/sarsen/issues
- **Q16** xarray-sentinel auf PyPI: https://pypi.org/project/xarray-sentinel/; pyroSAR auf PyPI: https://pypi.org/project/pyroSAR/; s1ard, Releases und Installation: https://github.com/SAR-ARD/s1ard
- **Q17** s1tbx (archiviert): https://github.com/senbox-org/s1tbx; SNAP-Image: https://github.com/mundialis/esa-snap; Filipponi, Referenzkette: https://github.com/ffilipponi/Sentinel-1_GRD_preprocessing
- **Q18** GDAL `safedataset.cpp`: https://github.com/OSGeo/gdal/blob/master/frmts/safe/safedataset.cpp; eo-tools: https://github.com/odhondt/eo_tools; GEE-S1-ARD: https://github.com/adugnag/gee_s1_ard

**Über Suchtreffer [S]** (Hilfsagenten; Hosts nicht abrufbar):

- **Q20** ESA, Radiometric Calibration of Level-1 Products: https://sentinels.copernicus.eu/web/sentinel/radiometric-calibration-of-level-1-products
- **Q21** ESA, Thermal Denoising of Products Generated by the S-1 IPF (MPC-0392): https://sentinel.esa.int/documents/247904/2142675/Thermal-Denoising-of-Products-Generated-by-Sentinel-1-IPF
- **Q22** ESA, Masking „No-value“ Pixels on GRD Products (IPF 2.90): https://sentinel.esa.int/documents/247904/2142675/Sentinel-1-masking-no-value-pixels-grd-products-note
- **Q23** D. Small, „Flattening Gamma“, IEEE TGRS 49(8), 2011, https://doi.org/10.1109/TGRS.2011.2120616
- **Q24** A. Vollrath et al., Remote Sens. 12(11), 1867 (2020), https://doi.org/10.3390/rs12111867; A. Mullissa et al., Remote Sens. 13(10), 1954 (2021), https://doi.org/10.3390/rs13101954
- **Q25** J. Truckenbrodt et al., „Towards Sentinel-1 SAR Analysis-Ready Data“, Data 4(3), 93 (2019), https://doi.org/10.3390/data4030093
- **Q26** F. Filipponi, „Sentinel-1 GRD Preprocessing Workflow“, Proceedings 18(1), 11 (2019), https://sciforum.net/paper/6201
- **Q27** CEOS-ARD NRB PFS v5.5: https://ceos.org/ard/
- **Q28** G. Shiroma et al., „An Area-Based Projection Algorithm for SAR Radiometric Terrain Correction and Geocoding“, IEEE TGRS (2022), https://doi.org/10.1109/TGRS.2022.3147472 (über Q6)
- **Q29** JPL, OPERA RTC-Produkt (Genauigkeit): https://www.jpl.nasa.gov/go/opera/products/rtc-product/
- **Q30** ASF HyP3, RTC-Guide, DEMs, Credits: https://hyp3-docs.asf.alaska.edu/
- **Q31** Copernicus DEM, Product Handbook Issue 5.0: https://dataspace.copernicus.eu/sites/default/files/media/files/2024-06/geo1988-copernicusdem-spe-002_producthandbook_i5.0.pdf
- **Q32** Sentinel-1 Lagegenauigkeit (ALE), Remote Sens. 9(6), 607: https://mdpi.com/2072-4292/9/6/607; Orbits: https://registry.opendata.aws/s1-orbits/
- **Q33** ESA, Sentinel-1 ARD NRB: https://sentinel.esa.int/web/sentinel/sentinel-1-ard-normalised-radar-backscatter-nrb-product; DLR S1-NRB: https://geoservice.dlr.de/data-assets/4sc3nyjt0o76.html
- **Q34** EODC/TU Wien SIG0: https://tuw-geo.github.io/microwave-remote-sensing/; ACube: https://acube.eodc.eu/; Swiss Data Cube: https://geonetwork.swissdatacube.org/

**Im Repo:** `adr/0014`, `adr/0016`, `adr/0018` §3.1, §4.4, §6, §9.5; `adr/0030` §5.2, §8, §9; `adr/0034` §6, §10; `adr/0035`; `plans/m5/ds-04d-radargeometrie.md` §2; `plans/ds/ds-04-s1-anbinden.md` §2; `backend/catalog/datasets/sentinel-1-grd.yaml`, `cop-dem-glo-30.yaml`; `backend/earthx/processing/plan.py` (`MAX_JOB_MEMORY_BYTES`).
