# ADR 0018 — Quelle für Sentinel-1

- **Status:** **Angenommen** von Otto am 2026-10-26 (**Fassung 2**).
  - F1, F2, F3, F5 und F6 nach Empfehlung (Option 1); F4 mit Option 3 und der
    Präzisierung „Originale nur als signierter Link“ (§9.1).
  - Zwei Nachfragen zu F4 sind offen (§9.3); sie betreffen nur Teil B.
  - Teil B hängt an Ottos eigener Messung (§11 C). Fällt sie negativ aus,
    entfällt Teil B.
  - Fassung 1 hat Otto am 26.10.2026 beantwortet, aber nicht angenommen; er
    hat die Teile A bis C in Auftrag gegeben (§9.2).
- **Datum:** 2026-10-26
- **Aufgabe:** DS-01 laut `docs/plans/ds/ds-01-s1-quelle.md` (Paket DS,
  `docs/plans/ds/ds-00-paket.md`).
- **Autonomiestufe:** C. Kein Produktivcode, keine Änderung an `backend/`,
  `frontend/`, Fixtures, `.github/`, `.claude/`, `CLAUDE.md` oder den
  Lock-Dateien. Gemessen wurde mit `curl` und kurzen Skripten im
  Kratzverzeichnis der Sitzung; sarsen lief nur dort in einer eigenen
  Umgebung (§6.2).
- **Vorab fest (Otto, 26.10.2026, Antwort auf Fassung 1):**
  - Keine regionale Quelle: DE Africa, DEA und Indigo scheiden aus.
  - Sentinel-1 soll weltweit verfügbar sein; auch Level-1 (GRD) wird
    angeboten.
  - Earth Search `sentinel-1-grd` wird ein eigener Level-1-Datensatz: Download
    der Originale und Zuschnitt wie üblich, Anzeige mit dem Hinweis
    „approximate geolocation“ (Teil A, §4).
  - Planetary Computer `sentinel-1-rtc` wird als RTC-Datensatz mit anonymem
    SAS-Token geprüft, unter Ottos Auflagen (Teil B, §5).
  - Eigene Geländekorrektur als Job ist ein späterer Weg (Teil C, §6).
  - Umsetzung mit oder nach M5. Der Backlog bleibt unverändert.
- **Weiter fest:**
  - Die Plattform enthält nichts, was einen Token braucht (`ENTSCHEIDUNGEN`
    §1); Token-Logik wird nicht übernommen und nicht generalisiert (§3);
    Token-Logik ist nicht Teil von `gateway` (`KLAERUNGEN` B8). Teil B
    berührt diese Regeln; das ist Frage F4.
  - `decomp.py` bleibt ruhend und wird nicht generalisiert; Sentinel-1 ist
    Dual-Pol (`ENTSCHEIDUNGEN` §3).
  - Unterschiede je Datensatz stehen als Daten in der Registry; was nicht geht,
    erscheint nicht (DS-00).
- **Grundlage:** `ENTSCHEIDUNGEN_2026-09-18.md` §1, §3, §4; `KLAERUNGEN.md`
  B8, B9, B10, B11, B12; `projektuebersicht.md` §2 (Prinzipien 2, 9, 10),
  §5 (Checkliste); `architekturplan.md` 3.1, 6.2, 6.4, 6.5, 7.3, 7.7;
  `projektplan.md` M7 Paket 7g; `adr/0003` §6, §10, §11; `adr/0004`;
  `adr/0005` §5; `adr/0007` §12; `adr/0014` §3.1, §6.3; `adr/0017`;
  Entscheidungslog 2026-09-20 (Asset-Proxy aufgehoben).
- **Betroffen (erst mit der Umsetzung):** Registry (`catalog/registry.py`,
  `catalog/datasets.py`), `readers` (Georeferenz aus GCPs, §4.1), `access`
  (Zuschnitt), Allowlist der Umgebung, `docs/cloud-umgebung.md`, DS-02
  (Suchfelder), DS-04, DS-05.

---

## Methode und Belegstufen

Belegstufen wie in `adr/0016` und `adr/0017`:

- **M:** in dieser Sitzung gemessen; das Verfahren steht im Text oder in §11.
- **P:** am Primärdokument selbst gelesen (im Repo mit Pfad und Zeile).
- **P\*:** Primärdokument über das Abrufwerkzeug eines Hilfsagenten gelesen,
  der Seiten zusammenfasst; Zitate sinngemäß, vor einer Annahme an der Quelle
  zu prüfen.
- **S:** Suchtreffer oder Zusammenfassung, Wortlaut nicht geprüft.
- **A:** eigene Ableitung, ein Argument und kein Beleg.

**Anfragen an Datenquellen:** STAC-Metadaten, Bucket-Listen, Range-`GET`s auf
Köpfe und Übersichten; für die Messungen in §4.1 und §6.2 zusätzlich eine
ganze GRD-Szene (VV, rund 0,9 GB) und eine DEM-Kachel im Kratzverzeichnis.
Item-IDs, `href` und genaue Flächen stehen nicht in diesem Dokument.

**Messung über `gateway` — hier nicht möglich [M].** `gateway` verbindet
absichtlich zur geprüften Adresse; der Proxy der Sitzung arbeitet
namensbasiert und weist das ab (Entscheidungslog, Zeile „`gateway` erreicht
die Quelle aus einer Cloud-Sitzung nicht“, offen). Die Zugriffe sind deshalb
mit `curl` über den Proxy gemessen, ohne Anmeldung, ohne Kopfzeilen außer
`Range` (und `x-amz-checksum-mode` in §4.1). Der Check über `gateway` selbst
gehört in den Live-Smoke der Umsetzung (CI ohne Proxy) und in Ottos Prüfung
(§11 E).

**Gesperrt in dieser Sitzung [M]:** `planetarycomputer.microsoft.com`, die
Blob-Hosts des Planetary Computer, CDSE, ASF, DE Africa und `cdn.proj.org`.
Teil B ist deshalb **nicht gemessen** (§5.1).

---

## 0. Kurzfassung

**Entscheidung (Otto, 26.10.2026):** Teil A mit TPS überall, beiden
Hinweisen und den Operatoren nach §4.4; die Regel „token-frei“ wird
präzisiert (F4 Option 3), wirksam erst nach einer positiven Messung von Teil B;
Teil C als eigener ADR nach DS-04. Die Punkte unten sind der Stand vor der
Entscheidung.

1. **Earth Search `sentinel-1-grd` ist weltweit und anonym lesbar** [M][P]:
   Der Bucket ist nicht mehr Requester Pays, auch wenn die STAC-Items es noch
   behaupten (§3.1). Inhalt: GRD in Radargeometrie, unkalibriert (DN),
   georeferenziert nur über GCPs.
2. **Teil A — „approximate geolocation“ heißt heute zweierlei Lage [M].**
   Kachel (rio-tiler, affine Näherung) und Zuschnitt (GDAL, Polynom) legen
   dasselbe Pixel im Median 92 bis 410 m und bis knapp 2 km auseinander.
   Gegen eine Geokodierung mit DEM liegen im Hügelland die Kachel im Median
   219 m, der Zuschnitt 102 m und eine **Thin-Plate-Spline (TPS)** aus den
   GCPs 40 m daneben (höchstens 141 m). Empfehlung: **eine** Methode (TPS) in
   Kachel, Zuschnitt und Job, als allgemeine Fähigkeit der Reader (F1).
   Operatoren auf GRD sind nur eingeschränkt fachlich zulässig (§4.4, F3).
3. **Teil B — Planetary Computer ist hier nicht messbar** (Hosts gesperrt).
   Nach den Quellen: Token-Pflicht für jedes Asset seit Oktober 2025, anonym
   rund 45 min gültig, Ratenlimit nicht veröffentlicht und offenbar klein,
   **Betreiberschlüssel sind nicht mehr erhältlich** (Maintainer, 20.10.2026)
   [P\*]. Die Collection-Beschreibung von `sentinel-1-rtc` sagt sogar: „A
   Planetary Computer account is required to retrieve SAS tokens to read the
   RTC data“ [P]. Dazu widerspricht der Weg „Download über die Plattform“
   `architekturplan.md` 6.4. Die nötige Klarstellung der Regel „token-frei“
   steht als F4; die Messung als F5 und §11 C.
4. **Teil C — eigene Geländekorrektur mit sarsen ist machbar, aber kein kleiner
   Schritt** [M][P]. Gemessen: RTC einer Fläche von rund 28 × 24 km in
   10 m in 51 s und 11,8 GB Spitzenspeicher auf 4 Kernen. sarsen ist Beta,
   Apache-2.0 und bringt **19 neue Pakete** mit; das DEM muss auf
   Ellipsoidhöhen umgerechnet werden, das Geoid-Gitter liegt auf einem hier
   gesperrten Host.
5. **Empfehlung (§8):** Teil A wie entschieden, mit TPS überall und zwei
   Hinweisen. RTC zuerst über Teil C (token-frei) als eigener ADR nach
   DS-04; Planetary Computer nur nach bestandener Messung und Ottos
   Regelentscheidung (F4, F5).

---

## 1. Kontext und Frage

Otto möchte Sentinel-1 anbieten, mit eigener Suche (Orbitrichtung,
Polarisation, Aufnahmemodus) und eigener Prozessierung (DS-01 §1). Fassung 1
empfahl, mit dem regionalen RTC-Produkt von DE Africa zu beginnen. Otto hat
das abgelehnt: Sentinel-1 soll weltweit verfügbar sein, Level-1 (GRD) wird
angeboten, und für RTC sind Planetary Computer und eine eigene
Geländekorrektur zu prüfen.

**Fragen der Fassung 2:**

- A: Was heißt „GRD als eigener Level-1-Datensatz mit approximate
  geolocation“ für Kacheln, Zuschnitt, Download, Coverage und Processing?
- B: Ist `sentinel-1-rtc` des Planetary Computer mit einem anonymen SAS-Token
  unter Ottos Auflagen tragbar, und was müsste an den Regeln geklärt werden?
- C: Was kostet eine eigene Geländekorrektur als Job (Aufwand, Rechenzeit,
  Genauigkeit, Abhängigkeiten)?

---

## 2. Kriterien

| # | Kriterium | Woher |
|---|---|---|
| K1 | Anonym, ohne Konto und Zugangsdaten (Metadaten **und** Assets); was ein anonym ausgestellter Token ist, klärt F4 | `ENTSCHEIDUNGEN` §1; Checkliste Punkt 6 |
| K2 | Lizenz erlaubt Anzeige und Processing (B11), Attribution bekannt | `KLAERUNGEN` B11; Checkliste Punkt 4 |
| K3 | Geometrie: wie genau liegen die Pixel, und liegen Kachel, Zuschnitt und Job gleich | `architekturplan.md` 6.3, 7.3 („Vorschau und Ergebnis übereinstimmen“) |
| K4 | Radiometrie: physikalische Werte (σ⁰/γ⁰) oder ehrlich gekennzeichnet | Prinzip 9; DS-05 |
| K5 | Kachelbar: COG mit Übersichten | `adr/0006`; Checkliste Punkte 5, 8 |
| K6 | Weltweit, Archiv tief, neue Szenen zeitnah | Otto 26.10.2026; `adr/0005` Regel II |
| K7 | Suchfelder (Orbitrichtung, Polarisation, Modus, relativer Orbit) | DS-02 |
| K8 | Fassung je Asset für den Cache | `adr/0014` §3.1 |
| K9 | Coverage-Anbieter zuzuordnen | Checkliste Punkt 2; `adr/0004` |
| K10 | Quelle dauerhaft betrieben; Kosten und Limits tragbar | Prinzipien 10, 11 |
| K11 | Grenzen: B8, B9, Modulgrenzen; neue Abhängigkeit nur mit Otto | `CLAUDE.md`; `architekturplan.md` 3.1 |

---

## 3. Befunde je Quelle

### 3.1 Earth Search v1 `sentinel-1-grd` (Element 84, AWS) — [M] und [P]

**Collection [M]** (Q1): „Sentinel-1 Level-1C Ground Range Detected (GRD)“,
STAC 1.0.0, `license: proprietary` mit Link auf das Sentinel Data Legal
Notice, global, ab 2014. `/aggregate` meldet 3 800 419 Items, das neueste vom
selben Tag (das README nennt noch „~2.7 million“, Q11). Modi IW, EW, SM;
Plattformen bis S1C.

**Anonymer Zugriff [M]:**

| Anfrage, ohne Anmeldung und ohne `x-amz-request-payer` | Antwort |
|---|---|
| Collection, Items, `/search`, `/aggregate` | `200` |
| Range-`GET` auf ein Daten-Asset, Szenen vom 26.10.2026 und 01.06.2015 | `206` |
| Thumbnail (PNG), `manifest.safe`, Annotationen (XML) | `206` bzw. `200` |
| `?requestPayment` am Bucket | `<Payer>BucketOwner</Payer>` |
| `?policyStatus` am Bucket | `<IsPublic>true</IsPublic>` |

- **Widerspruch in den Metadaten [M]:** Collection und Items tragen
  `storage:requester_pays: true` und `s3://`-Adressen; das README nennt
  genau das als Zeichen für Requester Pays (Q11) [P].
- **Registry nachgezogen [P]:** `RequesterPays: False`, „ManagedBy: Element
  84“ (Q12). Der Commit dazu (06.02.2026): „buckets were changed to
  non-Requester pays more than 1.5 years ago“ (Q13) [P\*]. Eine Ankündigung
  wurde nicht gefunden [S].
- **Keine Betriebszusage [P]:** „This public API does not come with any
  guaranteed service.“ (Q11).

**Format [M]:** je Polarisation ein COG (`uint16`, Deflate, Blöcke 1024,
Übersichten 2 bis 64), **keine CRS, nur GCPs** (168 bis 294 je Szene, mit
Höhe). „Sentinel-1 is not distributed as gridded data“ (Q14) [P]. Die
Item-Felder `proj:epsg: 4326` und `proj:transform` beschreiben keine Gitterlage
der Datei. Werte: DN (Amplitude), `nodata: 0`.

**Was im Bucket liegt [M]:** je Szene 27 Objekte in SAFE-Gliederung
(`manifest.safe`, `annotation/`, `annotation/calibration/`, `measurement/`,
`preview/`, `support/`). Eine IW-Szene hat rund 1,0 bis 1,5 GB (VV 607 bis
900 MB, VH rund 400 MB). Zwei Abweichungen vom ESA-Produkt:

- Die Dateinamen sind gekürzt (`measurement/iw-vv.tiff`), `manifest.safe`
  nennt die Originalnamen. Werkzeuge, die ein SAFE über das Manifest lesen,
  brauchen eine Umbenennung (§6.2).
- Die Messdateien sind eine COG-Umwandlung, nicht die TIFFs der ESA (Q11).
- Die STAC-Assets `schema-product-*` zeigen auf `annotation/rfi/…` statt auf
  die Produkt-Annotation `annotation/iw-*.xml`; diese ist kein Asset.

**Fassung [M]:** keine `file:checksum`. Jedes Objekt trägt aber eine
**CRC64NVME-Prüfsumme über die ganze Datei**: Ein `HEAD` mit
`x-amz-checksum-mode: ENABLED` liefert `x-amz-checksum-crc64nvme` und
`x-amz-checksum-type: FULL_OBJECT`. Dazu `ETag` (32 Hex) und
`Last-Modified`. Eine Anfrage je Asset, wie beim DEM (`adr/0014` §3.1).

**Suchfelder [M]:** Query-Extension, kein CQL2 (`adr/0005` §3.1).

| Feld | Werte (Summaries) | mit `query` filterbar |
|---|---|---|
| `sat:orbit_state` | ascending, descending | ja |
| `sat:relative_orbit` | 1–175 | ja |
| `sar:instrument_mode` | IW, EW, SM | ja |
| `sar:polarizations` | VV+VH, HH+HV, VV, VH, HH, HV | ja als `{"eq": "VH"}` (enthält); `{"eq": [...]}` → `400` |
| `s1:resolution` | full, high, medium | ja |
| `s1:product_timeliness` | NRT-10m … Reprocessing | ja |

- `/queryables` nennt nur `sar:polarizations`; die Felder gehören deshalb in
  die Registry (DS-02).
- **Fallstrick [M]:** Ein CQL2-`filter` wird still übergangen (`matched` =
  Gesamtzahl), bestätigt `adr/0005` §5.

**Aktualität [M]:** Aufnahme → `created` 59 bis 82 min (fünf neueste Items).
**Coverage [M]:** `/aggregate?aggregations=grid_geohex_frequency` antwortet
für die Collection, derselbe Upstream-Anbieter wie für Sentinel-2
(`adr/0004`); die Footprints hat Element 84 neu berechnet (Q14) [P].

### 3.2 Digital Earth Africa `s1_rtc` — ausgeschieden

Anonym lesbar, γ⁰ RTC als COG in EPSG:4326, aktuell [M]; aber nur Afrika.
**Otto, 26.10.2026: keine regionale Quelle.** Dasselbe gilt für Indigo (USA)
und DEA. Die Messwerte stehen in Fassung 1 (Git-Historie dieser Datei).

### 3.3 EOPF Sentinel Zarr Samples — kein Kandidat [M]

`sentinel-1-l1-grd` (2017 bis heute, Zarr v2): Radargeometrie, **eine**
Auflösung ohne Übersichten, kein `ETag`; Musterdienst ohne Zusage
(`adr/0017` §3.1). Beobachten, sobald operative Zarr-Produkte kommen
(Wiedervorlage aus `adr/0017` F4).

### 3.4 Copernicus Data Space Ecosystem und ASF/OPERA — ausgeschieden [P][M]

- CDSE: Download „you need an authorization token as only authorized users
  are allowed to download data products“ (Q20); S3 nur mit „registered
  account“ (Q21). Die GRD-COGs der CDSE sind per `gdal_translate` aus dem
  GRD-TIFF gemacht (Q22), also dieselbe Radargeometrie wie §3.1.
- ASF: Download mit Earthdata Login (Q23) [P\*]; OPERA RTC-S1 anonym `403`
  [M], „ControlledAccess“ (Q25) [P].
- Beide verlangen ein Konto und scheiden nach K1 aus, unabhängig von F4.

### 3.5 Weitere anonyme Quellen — keine weltweiten Szenen [M][P]

Earth Big Data Global Coherence (einmalig 2019/20), Digital Earth Pacific
(Jahreskomposit, regional), SLC-Ausschnitte auf AWS (regional). Keine liefert
weltweite Szenen mit Suche nach Orbit und Polarisation (Q26, Q27).

---

## 4. Teil A — Earth Search GRD als Level-1-Datensatz

### 4.1 Kacheln und Zuschnitt: eine Lage, nicht zwei — [M]

**Heute zwei Wege [P]:**

- Kacheln: rio-tiler 9.4.6 legt für GCP-Dateien ein `WarpedVRT` mit
  `transform.from_gcps` an, eine **affine** Näherung
  (`rio_tiler/io/rasterio.py` Z. 99–103).
- Zuschnitt und Job: `access/download.py` und `processing/warped.py` öffnen
  `WarpedVRT(dataset, crs=…)` ohne Quell-Transformation; GDAL nimmt dann
  seine GCP-Transformation (Polynom) [P][A].

**Wie weit die beiden auseinanderliegen [M]:** drei IW-Szenen vom 26.10.2026,
40 × 40 Punkte über die Szene, Abstand derselben Bildposition:

| Szene | affin ↔ GDAL-Polynom, Median / max | affin ↔ TPS | Polynom ↔ TPS |
|---|---|---|---|
| Hügelland (GCP-Höhen bis 535 m) | 92 / 341 m | 126 / 513 m | 63 / 434 m |
| flach (0 m) | 116 / 555 m | 116 / 570 m | 3 / 17 m |
| Hügelland (bis 826 m) | 410 / 1 972 m | 435 / 2 205 m | 75 / 714 m |

Ohne Änderung zeigt die Kachel also eine andere Lage als die Datei, die der
Nutzer herunterlädt. Das verletzt die Regel „Vorschau und Ergebnis
übereinstimmen“ (`architekturplan.md` 7.3).

**Welche Näherung am besten liegt [M]:** Vergleich mit einer Geokodierung mit
DEM (sarsen GTC, §6.2) auf einer Fläche von rund 28 × 24 km im Hügelland, 20 m
Raster, 16 Fenster mit einem Relief von im Median 517 m; Versatz je Fenster per
Phasenkorrelation (Auflösung 20 m):

| Methode | Median | 90 % | max |
|---|---|---|---|
| affin aus GCPs (heutige Kachel) | 219 m | 332 m | 505 m |
| GDAL-Polynom (heutiger Zuschnitt) | 102 m | 235 m | 428 m |
| **TPS aus GCPs** | **40 m** | **112 m** | **141 m** |

Einschränkungen: Die Referenz nutzt eine konstante Geoid-Höhe (+34 m), weil
kein Geoid-Gitter erreichbar war; ±5 m Geoid verschieben um rund 5 bis 9 m.
Ein Fensterversatz mittelt; an Steilhängen ist die Abweichung örtlich größer
[A]. Grund: Die GCPs tragen die Höhe des Geländes an ihrem Ort; die TPS geht
genau durch sie, das Polynom und die affine Näherung glätten darüber hinweg.
Zwischen den GCPs (Abstand rund 10 bis 20 km) bleibt das Relief
unberücksichtigt; der Fehler wächst mit dem Höhenunterschied zur
Interpolation, etwa um Δh / tan θ (θ 30° bis 46°) [A].

**Folgerung [A]:** „Approximate geolocation“ heißt mit TPS: einige zehn bis
rund 150 m im Hügelland, mehr im Hochgebirge, wenige Meter im Flachen. Dafür
braucht es eine **allgemeine Fähigkeit** „Georeferenz aus GCPs per TPS“, die
Kachel, Zuschnitt, Job und Runner gleich nutzen (GDAL-Option
`SRC_METHOD=GCP_TPS`); bei rio-tiler heißt das, die affine Näherung für
GCP-Dateien zu ersetzen. Kein Sondercode für Sentinel-1: Die Methode ist eine
Registry-Angabe (F1). Ob TPS im Kachelpfad schnell genug ist, misst die
Umsetzung.

**Kosten der Kacheln [M]:** Die Übersichten werden genutzt. Grobe Messung mit
rio-tiler (affiner Pfad), zwei Szenen: z7 rund 0,1 bis 0,2 MB je Kachel, z9 0,4
bis 2,4 MB, z11 bis z13 2 bis 4 MB (Blöcke zu 1024 × 1024).

### 4.2 Darstellung und Hinweise — [A]

- **Werte:** DN, also unkalibriert. Eine dB-Darstellung (`20·log10(DN)`) zeigt
  Helligkeit, aber keine σ⁰-Werte; über Szenen und Bahnen hinweg sind die
  Zahlen nicht vergleichbar (Kalibrier-LUT, Rauschen, Einfallswinkel).
- **Hinweise:** Otto verlangt „approximate geolocation“. Ehrlich nach Prinzip 9
  wäre ein zweiter Hinweis „uncalibrated (DN)“ (F2). Beide gehören in die
  Oberfläche (kurz, Erklärung im Tooltip), in Rezept und Provenienz und in die
  Textdatei des Downloads, als Registry-Angaben ohne Code je Datensatz.
- **Quicklook:** Das PNG der Szene liegt ebenfalls in Radargeometrie (bei
  aufsteigender Bahn gespiegelt) [M][A]. Die Anzeige sollte über Kacheln
  laufen, nicht über `browse=QUICKLOOK`.

### 4.3 Download der Originale, Coverage, Suche — [M][A]

- **Originale:** Link-Liste wie bei Sentinel-2 (`OriginalFiles.tsx`), direkt
  vom Bucket. Dafür braucht die Registry eine allgemeine Abbildung
  `s3://sentinel-s1-l1c/` → `https://sentinel-s1-l1c.s3.eu-central-1.amazonaws.com/`;
  heute zeigt das Frontend `s3://`-Adressen bewusst nicht
  (`frontend/src/download.ts`, `isDirectDownloadHref`) [P]. Die Liste besteht
  aus den Assets des Items; die Produkt-Annotation fehlt dort (§3.1).
  Beschriftung: Die Dateien sind die COG-Fassung des Bucket-Betreibers, kein
  ESA-SAFE.
- **Zuschnitt:** wie üblich, mit der Methode aus §4.1, `uint16` DN, beide
  Hinweise in der Textdatei.
- **Coverage:** Upstream-Aggregation wie Sentinel-2 [M].
- **Suche:** Felder aus §3.1 für DS-02.
- **Fassung:** CRC64NVME per `HEAD` (§3.1), eine Anfrage je Asset.
- **Live-Smoke:** prüft auch den Requester-Pays-Zustand selbst (Range-`GET`
  `206`, `?requestPayment` = `BucketOwner`), weil die STAC-Angabe allein nicht
  stimmt.

### 4.4 Welche Operatoren auf GRD fachlich zulässig sind — [A]

Bezug: die Operatoren in `processing/operators` (Band-Math, Maske,
Normalisierung, Reprojektion), Zuschnitt und Mosaik je Durchgang, dazu DS-05.

| Operation | zulässig | Begründung |
|---|---|---|
| Zuschnitt, Download | ja | Pixel unverändert; Hinweise in der Textdatei |
| dB-Umrechnung als Darstellung | ja | relative Helligkeit, kein σ⁰ |
| Band-Math **innerhalb einer Szene** (VV/VH, Differenz in dB) | ja, mit Hinweis | gleiche Geometrie; die Kalibrier-LUTs der beiden Polarisationen sind ähnlich, aber nicht gleich → Verhältnis nur näherungsweise |
| Band-Math mit festen Schwellen (z. B. Wasser unter −18 dB) | nein | DN sind kein σ⁰; Schwellen aus der Literatur gelten nicht |
| Maske nach Werten (DS-06) | nur relativ (Perzentil, Bereich der Szene) | wie oben |
| Normalisierung | ja | Darstellung |
| Reprojektion, Resampling | ja, mit derselben Methode wie §4.1 | Ergebnis bleibt „approximate geolocation“ |
| Mosaik je Durchgang (aufeinanderfolgende Slices einer Bahn) | ja | gleiche Bahn, gleiche Geometrie; Nähte möglich |
| Mosaik oder Vergleich über Bahnen und Zeiten | nein | verschiedene Geometrie und Kalibrierung; Lagefehler addieren sich |
| Speckle-Filter (DS-05) | ja, fachlich sogar am besten in Radargeometrie | T1 schwierig (Nachbarschaft), siehe DS-05 |
| Index-Knöpfe, ML | nein | gelten für optische Daten |
| Dekomposition (`decomp.py`) | nein | Dual-Pol |

Die Capability-Flags der Registry sind ja/nein. „Ja mit Hinweis“ hieße: Flag
gesetzt, Hinweise aus §4.2 in Rezept und Ergebnis. Was „nein“ ist, erscheint
nicht (DS-00). Ein künftiger Datacube- oder Zeitreihen-Operator braucht für
GRD eine eigene Sperre (F3).

---

## 5. Teil B — Planetary Computer `sentinel-1-rtc` mit anonymem SAS-Token

### 5.1 Messung: in dieser Sitzung nicht möglich — [M]

`planetarycomputer.microsoft.com` (Token- und STAC-API) und die Blob-Hosts
(`sentinel1euwestrtc.blob.core.windows.net` u. a.) sind in dieser Sitzung
gesperrt (Proxy verweigert die Verbindung). **Was fehlt:** die Freigabe dieser
beiden Hosts für die Umgebung, wirksam erst in einer neu gestarteten Sitzung
(`docs/cloud-umgebung.md`, Regel zur Allowlist), oder Ottos Messung nach §11 C.
Zu messen ist:

1. `GET /api/sas/v1/token/sentinel-1-rtc` ohne Kopfzeilen → `200`,
   `msft:expiry`, Länge des Tokens (das Token selbst wird nicht ausgegeben).
2. Collection und ein Item per STAC → `200`; Felder `license`,
   `msft:requires_account`, `file:checksum`, Übersichten.
3. Range-`GET` auf ein Asset **ohne** Token → erwartet `403`/`404`; **mit**
   Token → `206`.
4. Gültigkeit: `msft:expiry` minus Abrufzeit.

### 5.2 Was die Quellen sagen — [P] und [P\*]

**Zugang:**

- „Anyone can get a token from our Data Authentication API - you don't have
  to be a registered Planetary Computer user“; „Datasets in the Planetary
  Computer are anonymously accessible: you don't need to supply a
  subscription key to get a SAS token“ (Q17) [P].
- **Widerspruch:** Die Beschreibung von `sentinel-1-rtc` sagt „A Planetary
  Computer account is required to retrieve SAS tokens to read the RTC data“,
  mit Link auf einen Abschnitt „when an account is needed“, den `sas.md` nicht
  mehr enthält (Q18) [P]. Das Collection-Template trägt
  `msft:requires_account: true`; bei `sentinel-1-grd` fehlt das Feld [P].
  Maintainer schrieben 2024, man brauche kein Konto mehr (Q30) [P\*]. Erst
  die Messung (§5.1) entscheidet.
- Seit Oktober 2025 ist das Token für **jedes** Asset Pflicht; anonymer Zugriff
  auf die Blobs ist abgeschaltet (Q31) [P\*].
- Ein Token gilt für einen ganzen Container (Q32) [P\*]. Gültigkeit anonym
  „45 minutes“, an anderer Stelle rund 1 h; mit Schlüssel und aus West
  Europe „8-24+ hours“ (Q31) [P\*]. Das SDK erneuert unter 60 s Restzeit
  (Q33) [P].
- Der `sign`-Endpunkt liefert signierte URLs, die im Beispiel an eine IP
  gebunden sind (`sip=…`) (Q17) [P].

**Ratenlimits und Schlüssel:**

- Zahlen werden nicht veröffentlicht (Q31) [P\*]. „Rate limiting and token
  expiry are dependent on“ Rechenzentrum (West Europe) und „a valid API
  subscription key“ (Q17) [P].
- Am 25.09.2026 meldete ein Nutzer `429` nach rund 10 bis 12 Token-Anfragen;
  das Limit sei in den Wochen davor kleiner geworden. Empfehlung der
  Maintainer: ein Token je Collection holen und zwischenspeichern (Q32)
  [P\*].
- **Betreiberschlüssel:** Am 20.10.2026 antwortete ein Maintainer auf „can a
  key still be obtained?“ mit „No.“ und verwies auf „Reusing or caching“
  (Q34) [P\*]. Ottos Ausbaustufe „Betrieb mit einem Schlüssel des Betreibers
  (Secret im Deployment, M6)“ ist damit nach heutigem Stand **nicht
  verfügbar**.
- Für die Plattform heißt das [A]: Alle Nutzer teilen sich die Limits der
  Plattform-IP. Ein Token je Prozess und Container mit Erneuerung vor Ablauf
  braucht wenige Token-Anfragen je Stunde; die Blob-Abrufe (Kacheln, Jobs,
  Downloads über die Plattform) sind die eigentliche Last, und dafür gibt es
  keine Zahlen.

**Lizenz und Bedingungen:**

- `sentinel-1-rtc`: `"license": "CC-BY-4.0"`, Catalyst als Prozessierer,
  Microsoft als Host und Lizenzgeber (Q18) [P]. Ein Wortlaut für die
  Namensnennung steht nicht im Template; die Copernicus-Bedingungen der
  Ausgangsdaten gelten zusätzlich [A]. B11-Einstufung: Otto.
- Nutzungsbedingungen des Dienstes: gefunden wurden nur die „Supplemental
  Terms of Use for Microsoft Planetary Computer Previews“ (Q35) [P]: „Previews
  are provided solely for evaluation and testing“, „as-is,“ „with all
  faults,“ and „as available“, Haftung „only direct damages up to USD$10“,
  „Microsoft may change or discontinue Previews“. Ob die Daten-API heute noch
  als Preview gilt und welche allgemeinen Microsoft-Bedingungen greifen, ist
  **offen** (die Seite selbst war nicht erreichbar).

**Betriebsstatus 2026 [P\*]:**

- Daten und APIs laufen weiter, seit der Hub 2024 abgeschaltet wurde (Q30).
- 15.09.2026: Umzug des Backends mit bis zu 4 h Ausfall „wegen gestiegener
  Anfragezahl“ (Q36).
- `sentinel-1-rtc`: Meldungen zu fehlenden Szenen (Februar 2026, Szenen erst
  nach über einer Woche da), Versatz zwischen S1A und S1C (Juli/August 2026)
  und null-gefüllten Szenen, jeweils ohne Antwort der Maintainer (Q37).
- Planetary Computer Pro ist ein separates Azure-Produkt für eigene Daten [S].

**Produkt [P]:** Catalyst, Gamma-Flattening nach Small 2011, DEM „PlanetDEM“,
nur IW; „orthorectified to the appropriate UTM projection“, „not shifted to any
specific grid“ — jede Szene hat ihr eigenes Raster (Q18). Übersichten,
`file:checksum` und Szenengröße: offen (§5.1).

### 5.3 Was Ottos Auflagen technisch heißen — [A]

Ottos Auflagen: Das Backend holt das Token über `gateway`, speichert es
zwischen und erneuert es vor Ablauf; es erreicht nie den Browser, nie Logs und
nie URLs außerhalb des Backends; die Originale lädt der Nutzer über die
Plattform.

| Stelle | Folge |
|---|---|
| `gateway` | Neue Fähigkeit „Zugangsnachweis anfordern“: Token-Endpunkt aus der Registry (allowlisted), Cache je Prozess, Erneuerung vor Ablauf, Backoff bei `429`. Widerspricht heute B8 („Token-Logik ist nicht Teil des Gateways“) und `ENTSCHEIDUNGEN` §3 (F4) |
| GDAL (Kacheln, Zuschnitt, Jobs) | Eine signierte URL in `/vsicurl/` landet in GDAL-Fehlertexten und im Debug-Log. Ausweg: `/vsiaz/` mit `AZURE_STORAGE_SAS_TOKEN` als Konfiguration, das Token steht dann nicht im Pfad [S, GDAL-Doku nicht gelesen]. Die Adress-Pinnung von `gateway` greift dort wie bei `/vsicurl/` nur als Vorprüfung |
| Rezept, Permalink, Cache-Schlüssel, Provenienz | nur die unsignierte Adresse; die Fassung darf nicht vom Token abhängen |
| Worker-Kern (B9) | holt sein Token selbst über `gateway`, ohne Plattformdienst; ein Token je Kindprozess |
| Lokaler Runner (T2L) | holt ein eigenes anonymes Token von der IP des Nutzers, oder der Datensatz ist dort nicht verfügbar (F5) |
| Download der Originale | über die Plattform gestreamt: widerspricht `architekturplan.md` 6.4 („Kein Byte läuft durch das eigene Backend“) und Prinzip 10; Egress und Blob-Limits trägt die Plattform. Der 2026-09-20 aufgehobene Asset-Proxy käme für diesen Datensatz zurück |
| Logs | `gateway` loggt schon heute keine Query-Strings (HMAC); Token-Endpunkt-Antworten dürfen nicht geloggt werden; ein Test prüft das |

### 5.4 Die Regel „token-frei“ — was zu klären ist

Heute steht an drei Stellen dasselbe, verschieden scharf:

- `ENTSCHEIDUNGEN` §1: „Die fertige Plattform enthält **nichts, was einen
  Token braucht**.“ §3: Token-Logik wird „nicht in die Zielarchitektur
  übernommen und nicht generalisiert“.
- `projektuebersicht.md` §2 Prinzip 2: Quellen, „die selbst einen externen
  Token/Account voraussetzen, werden nicht angebunden“.
- Checkliste Punkt 6: „Anonymer Zugriffs-Check bestanden (HTTP 200 statt
  401/403).“

Ein anonym ausgestellter SAS-Token fällt unter den Wortlaut von §1 („braucht
einen Token“), aber nicht unbedingt unter Prinzip 2 („externen
Token/Account voraussetzen“), wenn ihn jeder ohne Konto bekommt. `adr/0003` §6
hat ihn als Token gewertet. Die Frage dazu ist F4.

### 5.5 Bewertung Teil B — [A]

Für `sentinel-1-rtc` spricht: weltweit, γ⁰ RTC fertig, CC BY 4.0, COG in UTM.
Dagegen sprechen heute, selbst wenn F4 den Token erlaubt: der Widerspruch
„account required“ (§5.2), kein erhältlicher Betreiberschlüssel, kleine und
geteilte Ratenlimits ohne Zahlen, Preview-Bedingungen mit Änderungsvorbehalt,
offene Qualitätsmeldungen ohne Antwort, und der Download über die Plattform
gegen 6.4 und Prinzip 10. Teil B ist erst nach der Messung (§5.1) belastbar zu
entscheiden.

---

## 6. Teil C — eigene Geländekorrektur als Job

### 6.1 Was zu rechnen ist — [P\*][A]

1. **Kalibrierung:** DN → β⁰/σ⁰/γ über die LUT der Annotationen
   (σ⁰ = DN² / A²), dazu Abzug des thermischen Rauschens.
2. **Terrain Flattening** (Small 2011, Q29): Normierung auf die beleuchtete
   Fläche → γ⁰ RTC.
3. **Geokodierung mit DEM** (Range-Doppler): Jedes Pixel an seine
   Bodenposition; Layover und Schatten maskieren.

Als **Kachelrechnung (T1)** ist das nicht realistisch: Es braucht die ganze
Szene, ihre Annotationen und ein DEM, und Layover hängt von Pixeln weit
außerhalb der Kachel ab. Die Korrektur ist ein Job (T2/T3, oder T4 in M7
Paket 7g); der Viewer zeigt dann das Job-Ergebnis über `/results` [A].

### 6.2 sarsen mit Copernicus DEM — gemessen [M] und [P]

**sarsen [P]** (Q38): Version 0.9.6 vom 23.06.2026, Apache-2.0, „in the
**beta** phase“; GRD und SLC in IW/EW/SM; GTC und RTC („gamma flattening“,
nach Small 2011); liest SAFE lokal oder über fsspec; „Terrain-corrected images
will have the same pixels as the input DEM“; Referenzzahl: RTC einer ganzen
GRD in 10 m „approx 25 minutes on a 32Gb MacBook Pro“. Microsoft hat die
GRD-Unterstützung und das Gamma-Flattening gesponsert. Ein Notebook des
Planetary Computer nennt rund 10 min (Q38) [P\*].

**Abhängigkeiten [M]:** sarsen 0.9.6 installiert sich gegen
`backend/requirements.lock` ohne Konflikt, bringt aber **19 Pakete** mit, die
heute nicht im Lock stehen: cloudpickle, dask, elementpath, flox, fsspec,
locket, markdown-it-py, mdurl, numpy-groupies, partd, pygments, rich, sarsen,
scipy, shellingham, toolz, typer, xarray-sentinel, xmlschema. Neue
Abhängigkeiten nur mit Otto (K11).

**Probelauf [M]:** eine IW-Szene vom 26.10.2026 aus dem Earth-Search-Bucket
(nur VV), Dateien nach `manifest.safe` umbenannt (§3.1); Copernicus DEM GLO-30
aus dem Bucket des bestehenden Datensatzes, Ausschnitt rund 28 × 24 km im
Hügelland (Relief bis rund 1 100 m), nach UTM gebracht; Rechner der Sitzung
mit 4 Kernen und 15 GB.

| Lauf | Raster | Zeit | Spitzenspeicher |
|---|---|---|---|
| GTC | 20 m (1 186 × 1 420) | 8 s | 1,6 GB |
| RTC (γ⁰) | 20 m | 11 s | 1,8 GB |
| GTC | 10 m (2 372 × 2 839) | 16 s | 2,2 GB |
| RTC (γ⁰) | 10 m | 51 s | 11,8 GB |

- γ⁰ in 20 m: p5/p50/p95 = −18,5 / −9,0 / −3,2 dB, keine Lücken — plausibel
  für bewaldetes Hügelland [M][A].
- Hochgerechnet auf eine ganze IW-Szene (rund 250 × 170 km, rund 60-mal die
  Fläche) wären es bei linearer Skalierung rund eine Stunde auf 4 Kernen; der
  Speicher wächst ohne Chunking über jede Grenze. sarsen verarbeitet in
  Chunks mit Dask; die README-Zahl (25 min, 32 GB) ist der bessere Anhalt
  [A]. Für einen Zuschnitt auf eine AOI, wie die Plattform ihn rechnet,
  zählt die Fläche der AOI, nicht die der Szene: wenige Minuten [A].

**Genauigkeit [M][P\*]:** Gegen die GCP-Näherungen siehe §4.1 (TPS 40 m im
Median). Eine veröffentlichte Validierung von sarsen (Corner Reflectors,
Vergleich mit SNAP) wurde nicht gefunden; ein Nutzer meldet mit einem auf das
Geoid korrigierten DEM SNAP-ähnliche Ergebnisse, ein anderer, dass die
Chunkgröße das Ergebnis leicht ändert (bis rund 0,03) (Q39) [P\*]. Zum
Vergleich: OPERA RTC-S1 nennt eine Geolokalisierung unter 6 m für 80 % der
Validierungsdaten [S].

**Was offen oder schwierig ist:**

- **Geoid:** GLO-30 hat Höhen über EGM2008; sarsen braucht Ellipsoidhöhen und
  holt das Gitter mit `PROJ_NETWORK=ON` von `cdn.proj.org` (Q38) [P] — hier
  gesperrt [M]. Entweder Host freigeben oder das Gitter ins Image legen.
- **Rauschabzug** und präzise Orbitdateien: in sarsen nicht beschrieben;
  Orbit kommt aus der Annotation [P\*].
- **Eingabe:** SAFE nach Manifest; der Bucket hat gekürzte Namen (§3.1). Eine
  Abbildung ist nötig — datensatzbezogen, also im Operator mit Capability wie
  `decomp.py`, nicht in `readers` [A].
- **Bitgleichheit T2 ↔ T2L** (`adr/0014` §6.3): Ergebnis hängt von der
  Chunkgröße ab [P\*]; Chunking muss fest im Rezept stehen [A].
- **Leap seconds:** „may crash the code or silently return wrong results“
  (Q38) [P].

### 6.3 Aufwand — [A]

| Baustein | Umfang |
|---|---|
| ADR „Geländekorrektur“ (Stufe C): Stufe T2 oder T3, Zielraster (UTM, 10/20 m), Rauschabzug, Maske | ein PR |
| DEM-Vorbereitung: Mosaik aus GLO-30, Geoid, Reprojektion auf das Zielraster | ein Operator-Baustein, Tests synthetisch |
| Operator „S1 GRD → γ⁰“ mit Capability, SAFE-Abbildung, Chunking fest | ein bis zwei PRs, Tests mit einer synthetischen Mini-SAFE |
| Container oder Worker-Image mit sarsen (19 Pakete) | ein PR, Frage an Otto |
| Anzeige der Ergebnisse, Hinweise, Provenienz | vorhanden über `/results`; Feinschliff |

Rund vier bis sechs PRs der Stufe B, mit oder nach M5. Rechenzeit je Auftrag:
Minuten je AOI, nicht Sekunden; ein Kachel-„Live“-Bild aus RTC gibt es auf
diesem Weg nicht.

---

## 7. Optionen und Bewertung

### Option 1 — GRD jetzt (Teil A); RTC über eigene Korrektur (Teil C) später (empfohlen)

GRD als Level-1-Datensatz mit TPS überall und zwei Hinweisen; RTC als
Job-Ergebnis aus GRD nach einem eigenen ADR. Alles token-frei, eine Quelle,
weltweit.

### Option 2 — GRD jetzt; RTC über Planetary Computer

Wie Option 1 Teil A, dazu `sentinel-1-rtc` als zweiter Datensatz. Setzt F4
(Regel) und eine bestandene Messung F5 voraus, dazu Änderungen an B8,
`ENTSCHEIDUNGEN` §3, `architekturplan.md` 6.4 und 7.7.

### Option 3 — GRD jetzt; RTC über beide Wege

Planetary Computer als schnelle Anzeige fertiger RTC, eigene Korrektur für
Szenen und Zeiträume, die dort fehlen. Doppelter Aufwand; zwei RTC-Produkte
mit verschiedenen DEMs und Rastern zeigen dasselbe verschieden (vgl.
`adr/0017`: nicht zwei Datensätze, die dasselbe zeigen).

| | K1 | K2 | K3 | K4 | K5 | K6 | K7 | K8 | K10 | K11 |
|---|---|---|---|---|---|---|---|---|---|---|
| Teil A: ES GRD | ✓ | ✓ (`adr/0003` §11.2) | ~ TPS 40 m Median | ~ DN, gekennzeichnet | ✓ | ✓ | ✓ | ✓ CRC64 | ~ ohne Zusage | ✓ (Reader-Fähigkeit) |
| Teil B: PC RTC | offen (F4, F5) | ~ CC BY 4.0, Dienst „Preview“ | ✓ | ✓ γ⁰ | offen | ~ nur IW, Lücken | offen | offen | ✗ kein Schlüssel, Limits | ✗ B8, 6.4 |
| Teil C: eigene RTC | ✓ | ✓ | ✓ DEM | ✓ γ⁰ | ✓ (Ergebnis) | ✓ wie A | ✓ wie A | ✓ wie A | ✓ Rechenkosten | ✗ 19 Pakete (Frage) |

---

## 8. Empfehlung

Stand vor Ottos Entscheidung; was gilt, steht in §9.1 (F4 weicht ab: Option 3).

1. **Teil A wie entschieden**, mit **TPS** als einziger Georeferenz in Kachel,
   Zuschnitt, Job und Runner (F1), den Hinweisen „Approximate geolocation“ und
   „Uncalibrated (DN)“ (F2) und den Operatoren nach §4.4 (F3). Umsetzung als
   DS-04, mit oder nach M5.
2. **RTC zuerst über Teil C** (Option 1): token-frei, dieselbe Quelle wie A,
   Genauigkeit über ein DEM, das die Plattform schon führt. Eigener ADR nach
   DS-04 (F6); die 19 Pakete sind dort Ottos Frage.
3. **Planetary Computer nicht vor der Messung:** Die Regel „token-frei“ bleibt
   bis dahin wie sie ist (F4, Empfehlung 1); die Messung (F5) klärt „account
   required“, Gültigkeit und Limits. Besteht sie, entscheidet Otto mit diesen
   Zahlen neu.

---

## 9. Fragen an Otto

### 9.1 Fassung 2 — beantwortet am 2026-10-26

**F1 — Georeferenz des GRD-Datensatzes?**
1. TPS aus den GCPs in Kachel, Zuschnitt, Job und Runner, als allgemeine Reader-Fähigkeit über die Registry **(Empfehlung)**
2. GDAL-Polynom überall (einfacher, im Hügelland rund 100 m statt 40 m im Median)
3. Wie heute: Kachel affin, Zuschnitt Polynom (Kachel und Datei liegen bis 2 km auseinander)

**Antwort F1: (1)** TPS überall als Reader-Fähigkeit über die Registry; die
Kosten je Kachel misst die Umsetzung.

**F2 — Hinweise am GRD-Datensatz?**
1. „Approximate geolocation“ und „Uncalibrated (DN)“, kurz mit Tooltip, dazu in Rezept, Provenienz und Download-Text **(Empfehlung)**
2. Nur „Approximate geolocation“

**Antwort F2: (1)** „Approximate geolocation“ und „Uncalibrated (DN)“.

**F3 — Operatoren auf GRD?**
1. Nach §4.4: Zuschnitt, Band-Math innerhalb der Szene, Normalisierung, Reprojektion, Mosaik je Durchgang; keine festen Schwellen, keine Index-Knöpfe, kein Vergleich über Bahnen **(Empfehlung)**
2. Alle generischen Operatoren freischalten, nur Hinweise
3. Nur Zuschnitt und Download, keine Operatoren

**Antwort F3: (1)** Operatoren nach §4.4.

**F4 — Klarstellung der Regel „token-frei“ (`ENTSCHEIDUNGEN` §1/§3, `KLAERUNGEN` B8, Prinzip 2, Checkliste Punkt 6)?**
1. **Streng:** „Token-frei heißt: ohne Konto und ohne Zugangsdaten jeder Art. Auch ein Zugangsnachweis, den die Quelle jedem anonym ausstellt (z. B. ein SAS-Token), zählt als Zugangsdaten.“ Planetary Computer bleibt draußen **(Empfehlung, bis die Messung F5 vorliegt)**
2. **Präzisiert:** „Token-frei heißt: ohne Konto, ohne Schlüssel und ohne Zugangsdaten, die eine Person oder der Betreiber beantragen muss. Ein Zugangsnachweis, den die Quelle jedem anonym ausstellt, ist zulässig, wenn (a) der anonyme Zugriffs-Check ihn ohne Konto erhält, (b) das Backend ihn nur über `gateway` holt, zwischenspeichert und vor Ablauf erneuert, (c) er nie den Browser, Logs, Rezepte, Permalinks, Cache-Schlüssel oder URLs außerhalb des Backends erreicht und (d) die Quelle seine Weiterverwendung so erlaubt.“ Folgeänderungen: `ENTSCHEIDUNGEN` §1/§3, B8 (Nachtrag), Prinzip 2, Checkliste Punkt 6 („HTTP 200 ohne Konto und Zugangsdaten im Sinne dieser Regel“), `architekturplan.md` 6.4 (Ausnahme Download über die Plattform) und 7.7 (Runner)
3. Präzisiert wie 2, aber nur für Anzeige und Jobs; Originale nur als Link zur Quellseite, kein Download über die Plattform (6.4 bleibt)

**Antwort F4: (3)** Ein anonym ausgestellter Token ist unter den Bedingungen
(a)–(d) zulässig; Originale **nur als signierter Link**, kein Byte durch das
Backend (`architekturplan.md` 6.4 bleibt). Die Folgeänderungen in
`KLAERUNGEN.md` und der Onboarding-Checkliste werden als Nachtrag vorbereitet
(§12). Zwei Nachfragen dazu: §9.3.

**F5 — Messung Planetary Computer?**
1. Otto misst nach §11 C, oder gibt `planetarycomputer.microsoft.com` und `sentinel1euwestrtc.blob.core.windows.net` für eine neue Sitzung frei; danach Entscheidung über Teil B mit den Zahlen **(Empfehlung)**
2. Teil B ohne Messung verwerfen; RTC nur über Teil C
3. Teil B ohne weitere Messung einplanen (Option 2)

**Antwort F5: (1)** Otto misst den Planetary Computer selbst nach §11 C,
insbesondere: gibt es für `sentinel-1-rtc` ein Token ohne Konto? Fällt die
Messung negativ aus, entfällt Teil B.

**F6 — Eigene Geländekorrektur (Teil C)?**
1. Eigener ADR „Geländekorrektur für Sentinel-1 GRD“ (Stufe C) nach DS-04, sarsen als Ausgangspunkt, mit Messung an ganzen Szenen und der Paketfrage **(Empfehlung)**
2. Erst nach der Entscheidung über Teil B
3. Nicht weiter verfolgen

**Antwort F6: (1)** Eigener ADR zur Geländekorrektur nach DS-04: on demand als
Job für die AOI, Ergebnis im Cache. Kernfrage dort ist der Speicher: 11,8 GB im
Probelauf (§6.2) gegen die Grenze von 500 MB für den ganzen Kindprozess des
Workers (`adr/0014`, Abnahmegrenze M4-07a).

### 9.2 Fassung 1 — beantwortet am 26.10.2026

Die Fragen F1–F4 der Fassung 1 (DE Africa zuerst, GRD bis zur
Geländekorrektur, Host-Freigabe DE Africa, Lizenz DE Africa) sind durch Ottos
Antwort erledigt: keine regionale Quelle; Sentinel-1 weltweit, Level-1 (GRD)
wird angeboten; GRD als eigener Level-1-Datensatz mit „approximate
geolocation“; Planetary Computer und eigene Geländekorrektur prüfen; ADR nicht
annehmen, sondern ergänzen; Umsetzung mit oder nach M5; Backlog unverändert.

### 9.3 Nachfragen zu F4 — offen

**N1 — „Signierter Link“ und Bedingung (c).** Ein signierter Link trägt das
Token im Browser; Bedingung (c) schließt genau das aus. Dazu bindet der
`sign`-Endpunkt im Beispiel der Doku die Signatur an eine IP (`sip=…`, Q17):
Ein Link, den das Backend signiert, liefe beim Nutzer dann gar nicht. Was ist
gemeint?
1. Der Link zeigt auf die **unsignierte** Adresse oder die Seite des Items beim Planetary Computer; der Nutzer holt sich das Token dort selbst. (c) bleibt ohne Ausnahme **(Empfehlung)**
2. Das Backend signiert beim Klick und leitet weiter (`302`); (c) bekommt eine Ausnahme genau für diesen Link. Nur möglich, wenn das Token nicht an die IP gebunden ist (Ottos Messung, §11 C)
3. Kein Link auf Originale für diesen Datensatz

**N2 — Wo die Regel steht.** `ENTSCHEIDUNGEN` §1 („nichts, was einen Token
braucht“) und §3 (Token-Logik nicht übernehmen) gehen `KLAERUNGEN.md` vor.
Ein Nachtrag nur in `KLAERUNGEN.md` stünde unter einer Regel, die er
aufhebt.
1. Ein Satz als Nachtrag in `ENTSCHEIDUNGEN` §1 und §3, der auf B8 und die neue Auslegung verweist; Otto trägt ihn ein **(Empfehlung)**
2. Nur `KLAERUNGEN.md` und Checkliste; die Log-Zeile vom 26.10.2026 gilt als Ottos Entscheidung über `ENTSCHEIDUNGEN`

---

## 10. Was offen bleibt

- **Teil A** wird DS-04, mit oder nach M5: TPS als Reader-Fähigkeit mit
  Messung der Kosten je Kachel, beide Hinweise, Operatoren nach §4.4,
  `s3://`-Abbildung, Fassung per CRC64NVME, Live-Smoke mit
  Requester-Pays-Prüfung.
- **Teil B:** Ottos Messung (§11 C); bei positivem Ergebnis die Nachfragen N1
  und N2, dann die Nachträge aus §12 und die Lizenz-Einstufung von
  `sentinel-1-rtc` (B11, Otto). Offen bleibt dann auch der lokale Runner
  (holt dessen `gateway` ein eigenes Token?). Bei negativem Ergebnis entfällt
  Teil B; die Nachträge werden nicht eingetragen.
- **Teil C:** eigener ADR nach DS-04; Kernfrage Speicher (F6).
- Ob Element 84 die Metadaten (`requester_pays`, `s3://`, `schema-product-*`)
  nachzieht; eine Betriebszusage gibt es nicht.
- TPS im Kachelpfad: Geschwindigkeit, misst die Umsetzung.
- Nachtrag in `docs/plans/ds/ds-04-s1-anbinden.md` (Quelle, Produktart,
  Hinweise): mit der nächsten Doku-Aufgabe oder durch Otto; der Backlog bleibt
  unverändert.

---

## 11. Prüfanleitung für Otto

Nur Metadaten und je Datei die ersten Kilobyte, keine AOI. Windows PowerShell
5.1 oder Browser.

Vorab, nur in Windows PowerShell 5.1 nötig: TLS 1.2 einschalten.

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$es = 'https://earth-search.aws.element84.com/v1'
$s1 = 'https://sentinel-s1-l1c.s3.eu-central-1.amazonaws.com'
$pc = 'https://planetarycomputer.microsoft.com'
function Get-FirstKb($u) {   # Range-GET, gibt nur Status und ETag aus, nie die URL
  $r = [Net.HttpWebRequest]::Create($u); $r.AddRange(0, 1023)
  try { $x = $r.GetResponse(); "$([int]$x.StatusCode) $($x.Headers['ETag'])"; $x.Close() }
  catch { "Fehler: $([int]$_.Exception.InnerException.Response.StatusCode)" }
}
```

**A. Earth Search: Metadaten sagen Requester Pays (§3.1).**

```powershell
$c = Invoke-RestMethod "$es/collections/sentinel-1-grd"
$c.title; $c.license; $c.summaries.'storage:requester_pays'
#   (Sentinel-1 Level-1C Ground Range Detected (GRD); proprietary; True)
$body = '{"collections":["sentinel-1-grd"],"limit":1,"query":{"sar:instrument_mode":{"eq":"IW"},"sat:orbit_state":{"eq":"ascending"}}}'
$i = (Invoke-RestMethod -Method Post "$es/search" -Body $body -ContentType 'application/json').features[0]
$i.properties.'sar:instrument_mode'; $i.properties.'sat:orbit_state'; $i.properties.'sar:polarizations'
#   (IW; ascending; VV VH oder HH HV)
$i.properties.datetime; $i.properties.created    # (rund eine Stunde Abstand)
```

**B. Earth Search: der Bucket ist trotzdem anonym, mit Prüfsumme (§3.1).**

```powershell
$a = ($i.assets.vv, $i.assets.hh | Where-Object { $_ })[0].href -replace '^s3://sentinel-s1-l1c/', "$s1/"
Get-FirstKb $a                                   # (206 "…32 Hex-Zeichen…")
(Invoke-WebRequest "$s1/?requestPayment" -UseBasicParsing).Content
#   (… <Payer>BucketOwner</Payer> …)
$h = Invoke-WebRequest $a -Method Head -Headers @{ 'x-amz-checksum-mode' = 'ENABLED' } -UseBasicParsing
$h.Headers['x-amz-checksum-type']                # (FULL_OBJECT)
```

**C. Planetary Computer: anonymes Token für `sentinel-1-rtc` (§5.1, F5).**
Das Token nie ausgeben, nie in ein Issue, einen PR oder einen Chat kopieren.

```powershell
$t = Invoke-RestMethod "$pc/api/sas/v1/token/sentinel-1-rtc"
$t.token.Length; $t.'msft:expiry'                # (Länge > 0; Ablaufzeit)
([datetime]$t.'msft:expiry' - (Get-Date).ToUniversalTime()).TotalMinutes   # (Gültigkeit in Minuten)
$col = Invoke-RestMethod "$pc/api/stac/v1/collections/sentinel-1-rtc"
$col.license; $col.'msft:requires_account'       # (CC-BY-4.0; ?)
$r = (Invoke-RestMethod "$pc/api/stac/v1/collections/sentinel-1-rtc/items?limit=1").features[0]
([uri]$r.assets.vv.href).Host                    # (sentinel1euwestrtc.blob.core.windows.net)
$r.assets.vv.PSObject.Properties.Name            # (file:checksum dabei?)
$t.token -match '(^|&)sip='                      # (True heißt: an die IP gebunden, N1 Option 2 entfällt)
Get-FirstKb $r.assets.vv.href                    # ohne Token: (403 oder 404)
Get-FirstKb ($r.assets.vv.href + '?' + $t.token) # mit Token: (206)
Remove-Variable t
```

Antwortet schon der erste Befehl mit `401`/`403` oder einem Hinweis auf ein
Konto, ist F4 Option 2 für diesen Datensatz gegenstandslos.

**D. Kein Produktivcode im PR.**

```powershell
git fetch origin
git diff --stat origin/main...origin/claude/serene-allen-hwmp89
#   (nur Dateien unter docs/)
```

**E. Optional: der Zugriffs-Check über `gateway` (lokal, ohne Proxy).** Aus
dem Repo-Wurzelverzeichnis mit der Backend-Umgebung:

```powershell
$env:PYTHONPATH = 'backend'
python -c "import asyncio; from earthx.gateway import Gateway, Policy; u='https://sentinel-s1-l1c.s3.eu-central-1.amazonaws.com/?requestPayment'; g=Gateway(Policy(allowed_hosts=frozenset({'sentinel-s1-l1c.s3.eu-central-1.amazonaws.com'}))); print(asyncio.run(g.get(u)).status_code)"
#   (200)
```

---

## 12. Vorbereitete Nachträge (F4) — erst nach positiver Messung eintragen

Wortlaut zum Eintragen, sobald Ottos Messung (§11 C) positiv ist und N1 und
N2 beantwortet sind. Die Stellen in eckigen Klammern hängen von N1 ab.

**`KLAERUNGEN.md`, B8, neuer Nachtrag:**

> **Nachtrag [Datum] (`adr/0018` F4):** Ein Zugangsnachweis, den eine Quelle
> jedem anonym ausstellt (etwa ein SAS-Token), gilt nicht als Zugangsdatum im
> Sinne der Regel „token-frei“, wenn (a) der anonyme Zugriffs-Check ihn ohne
> Konto und Schlüssel erhält, (b) das Backend ihn nur über `gateway` von einem
> in der Registry genannten Endpunkt holt, zwischenspeichert und vor Ablauf
> erneuert, (c) er nie den Browser, Logs, Rezepte, Permalinks,
> Cache-Schlüssel oder URLs außerhalb des Backends erreicht [N1 Option 2: —
> ausgenommen der signierte Link auf die Originale, den das Backend beim Klick
> erzeugt] und (d) die Quelle seine Weiterverwendung so erlaubt. `gateway`
> bekommt dafür die Fähigkeit, einen solchen Nachweis anzufordern; Konten,
> Schlüssel und Zugangsdaten, die eine Person oder der Betreiber beantragen
> muss, bleiben ausgeschlossen. Originale werden nur verlinkt; kein Byte läuft
> durch das Backend (`architekturplan.md` 6.4). Erster Fall: `sentinel-1-rtc`
> des Planetary Computer.

**`projektuebersicht.md` §5, Checkliste Punkt 6, Nachtrag:**

> *Nachtrag ([Datum], `adr/0018` F4):* „Anonym“ heißt: ohne Konto, Schlüssel
> oder beantragte Zugangsdaten. Stellt die Quelle jedem einen Zugangsnachweis
> aus, besteht der Check, wenn der Nachweis ohne Konto zu bekommen ist und mit
> ihm `200`/`206` folgt; die Bedingungen stehen in `KLAERUNGEN.md` B8
> (Nachtrag [Datum]).

**`projektuebersicht.md` §2, Prinzip 2, Nachtrag (zur Einheitlichkeit):**

> *Nachtrag ([Datum]):* Ein Zugangsnachweis, den die Quelle jedem anonym
> ausstellt, ist kein externer Token im Sinne dieses Prinzips
> (`KLAERUNGEN.md` B8, Nachtrag [Datum]).

**`ENTSCHEIDUNGEN_2026-09-18.md` §1 und §3 (nur bei N2 Option 1, von Otto):**

> *Nachtrag ([Datum], Otto):* „Token“ meint hier Zugangsdaten, die ein Konto
> oder einen Schlüssel voraussetzen. Ein anonym ausgestellter Zugangsnachweis
> ist unter den Bedingungen von `KLAERUNGEN.md` B8 (Nachtrag [Datum]) zulässig.

---

## 13. Quellen

Alle abgerufen am 26.10.2026.

**Gemessen:**

- **Q1** Earth Search v1, Collection `sentinel-1-grd`, `/search`,
  `/aggregate`, `/queryables`: https://earth-search.aws.element84.com/v1/collections/sentinel-1-grd — [M]
- **Q2** Bucket `sentinel-s1-l1c` (eu-central-1): Liste, `?requestPayment`,
  `?policyStatus`, Range-`GET`s, `HEAD` mit `x-amz-checksum-mode`, eine ganze
  VV-Messdatei für §4.1 und §6.2 — [M]
- **Q3** Copernicus DEM GLO-30, eine 1°-Kachel aus `copernicus-dem-30m` — [M]
- **Q4** EOPF-STAC, Collections und erstes GRD-Item:
  https://stac.core.eopf.eodc.eu/collections — [M]
- **Q5** Buckets `deafrica-sentinel-1`, `asf-cumulus-prod-opera-products`,
  `sentinel-s1-rtc-indigo`, `sentinel-1-global-coherence-earthbigdata`,
  `dep-public-data` — [M]

**Gelesen:**

- **Q11** Element84, Earth Search, README:
  https://github.com/Element84/earth-search/blob/main/README.md — [P]
- **Q12** AWS Open Data Registry, `sentinel-1.yaml`:
  https://github.com/awslabs/open-data-registry/blob/main/datasets/sentinel-1.yaml — [P]
- **Q13** Commit `63c938c` im Open Data Registry, 06.02.2026:
  https://github.com/awslabs/open-data-registry/commit/63c938c85613ba76422c45d54a7369648f73e8d7 — [P\*]
- **Q14** Element84, `docs/collections/sentinel-1-grd.md`:
  https://github.com/Element84/earth-search/blob/main/docs/collections/sentinel-1-grd.md — [P]
- **Q17** Planetary Computer, „Using tokens for data access“:
  https://github.com/microsoft/PlanetaryComputerDataCatalog/blob/main/docs/concepts/sas.md — [P]
- **Q18** Planetary Computer, `sentinel-1-rtc` Collection-Template und
  Beschreibung; `sentinel-1-grd` Template:
  https://github.com/microsoft/planetary-computer-tasks/tree/main/datasets/sentinel-1-rtc/collection,
  https://github.com/microsoft/planetary-computer-tasks/blob/main/datasets/sentinel-1-grd/collection/template.json — [P]
- **Q20** CDSE-Doku, OData: https://github.com/eu-cdse/documentation/blob/publish/APIs/OData.qmd — [P]
- **Q21** CDSE-Doku, S3: https://github.com/eu-cdse/documentation/blob/publish/APIs/S3.qmd — [P]
- **Q22** CDSE-Doku, Sentinel-1 COG:
  https://github.com/eu-cdse/documentation/blob/publish/Data/Others/Sentinel1_COG.qmd — [P]
- **Q23** ASF, `asf_search`: https://github.com/asfadmin/Discovery-asf_search — [P\*]
- **Q25** AWS Open Data Registry, OPERA RTC-S1:
  https://registry.opendata.aws/nasa-operal2rtc-s1v1/ — [P]
- **Q26** AWS Open Data Registry, Global Coherence and Backscatter:
  https://registry.opendata.aws/ebd-sentinel-1-global-coherence-backscatter/ — [P]
- **Q27** AWS Open Data Registry, `dep-s1-geomads`:
  https://registry.opendata.aws/dep-s1-geomads/ — [P]
- **Q29** D. Small, „Flattening Gamma: Radiometric Terrain Correction for SAR
  Imagery“, IEEE TGRS 49(8), 2011: https://doi.org/10.1109/TGRS.2011.2120616 — [S]
- **Q30** Planetary Computer, Discussions #347 (Hub-Abschaltung, „Data and
  APIs will remain available“) und #395 (kein Konto mehr nötig):
  https://github.com/microsoft/PlanetaryComputer/discussions/347,
  https://github.com/microsoft/PlanetaryComputer/discussions/395 — [P\*]
- **Q31** Planetary Computer, Issue #457 (Token-Pflicht seit Oktober 2025,
  Gültigkeit, Limits nicht veröffentlicht):
  https://github.com/microsoft/PlanetaryComputer/issues/457 — [P\*]
- **Q32** Planetary Computer, Issue #506 (`429` nach rund 10 bis 12
  Token-Anfragen; Token je Container):
  https://github.com/microsoft/PlanetaryComputer/issues/506 — [P\*]
- **Q33** `planetary-computer-sdk-for-python`, `planetary_computer/sas.py`
  (Erneuerung unter 60 s, `Ocp-Apim-Subscription-Key` nur mit Schlüssel):
  https://github.com/microsoft/planetary-computer-sdk-for-python/blob/main/planetary_computer/sas.py — [P]
- **Q34** Planetary Computer, Issue #511 (kein Schlüssel mehr erhältlich,
  20.10.2026): https://github.com/microsoft/PlanetaryComputer/issues/511 — [P\*]
- **Q35** Planetary Computer, „Supplemental Terms of Use for Microsoft
  Planetary Computer Previews“ (Quelltext der Seite):
  https://github.com/microsoft/PlanetaryComputerDataCatalog/blob/main/src/pages/Terms.js — [P]
- **Q36** Planetary Computer, Discussion #500 (Umzug des Backends, 15.09.2026):
  https://github.com/microsoft/PlanetaryComputer/discussions/500 — [P\*]
- **Q37** Planetary Computer, Issues #472, #492, #493 zu `sentinel-1-rtc`:
  https://github.com/microsoft/PlanetaryComputer/issues/472,
  https://github.com/microsoft/PlanetaryComputer/issues/492 — [P\*]
- **Q38** sarsen, README (Paketbeschreibung 0.9.6) und PyPI:
  https://github.com/bopen/sarsen, https://pypi.org/project/sarsen/0.9.6/ — [P];
  Notebook „customizable-rtc-sentinel1“ des Planetary Computer — [P\*]
- **Q39** sarsen, Issues #75, #85, #89:
  https://github.com/bopen/sarsen/issues — [P\*]

Im Repo: `adr/0003` §6, §11.2; `adr/0004`; `adr/0005` §3.1, §5; `adr/0007`
§12; `adr/0014` §3.1, §6.3; `adr/0017` §3.1, F4; `architekturplan.md` 6.4, 6.5,
7.3, 7.7; `backend/earthx/access/download.py` (`WarpedVRT` im Zuschnitt);
`backend/earthx/processing/warped.py`; `frontend/src/download.ts`
(`isDirectDownloadHref`); rio-tiler 9.4.6 `io/rasterio.py` Z. 99–103;
Entscheidungslog 2026-09-20 (Asset-Proxy) und Zeile „`gateway` erreicht die
Quelle aus einer Cloud-Sitzung nicht“.
