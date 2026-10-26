# ADR 0018 — Quelle für Sentinel-1

- **Status:** Entwurf, wartet auf Otto (Fragen in §9).
- **Datum:** 2026-10-26
- **Aufgabe:** DS-01 laut `docs/plans/ds/ds-01-s1-quelle.md` (Paket DS,
  `docs/plans/ds/ds-00-paket.md`).
- **Autonomiestufe:** C. Kein Produktivcode, keine Änderung an `backend/`,
  `frontend/`, Fixtures, `.github/`, `.claude/`, `CLAUDE.md` oder den
  Lock-Dateien. Gemessen wurde mit `curl` und kurzen Skripten im
  Kratzverzeichnis der Sitzung (§11).
- **Vorab fest:**
  - Die Plattform enthält nichts, was einen Token braucht (`ENTSCHEIDUNGEN`
    §1); Onboarding-Punkt 6 verlangt den anonymen Zugriffs-Check
    (`projektuebersicht.md` §5).
  - Der Planetary Computer bleibt gesperrt, Option C aus `adr/0003` wird
    nicht weiterverfolgt, weil die SAS-Signatur technisch ein Token ist
    (`adr/0003` §6, §10.2).
  - `decomp.py` bleibt ruhend und wird nicht generalisiert; Sentinel-1 ist
    Dual-Pol (`ENTSCHEIDUNGEN` §3).
  - Unterschiede je Datensatz stehen als Daten in der Registry, nicht als Code
    je Datensatz; was nicht geht, erscheint nicht (Otto, 26.10.2026, DS-00).
- **Grundlage:** `ENTSCHEIDUNGEN_2026-09-18.md` §1, §3, §4; `KLAERUNGEN.md`
  B8, B9, B10, B11, B12; `projektuebersicht.md` §5 (Checkliste);
  `architekturplan.md` 3.1, 6.2, 7.3 (Stufe T4); `projektplan.md` M7 Paket 7g;
  `adr/0003` §6, §10, §11; `adr/0004`; `adr/0005` §5 (Regeln, CQL2);
  `adr/0007` §12; `adr/0014` §3.1; `adr/0017`.
- **Betroffen (erst mit DS-04):** Registry (`catalog/registry.py`,
  `catalog/datasets.py`), Allowlist der Umgebung, `docs/cloud-umgebung.md`,
  DS-02 (Suchfelder), DS-05 (SAR-Operatoren).

---

## Methode und Belegstufen

Belegstufen wie in `adr/0016` und `adr/0017`:

- **M:** in dieser Sitzung gemessen; die Anfrage steht in §11.
- **P:** am Primärdokument gelesen (im Repo mit Pfad und Zeile).
- **P\*:** Primärdokument über das Abrufwerkzeug eines Hilfsagenten gelesen,
  der Seiten zusammenfasst; Zitate sinngemäß.
- **S:** Suchtreffer oder Zusammenfassung, Wortlaut nicht geprüft.
- **A:** eigene Ableitung, ein Argument und kein Beleg.

**Anfragen an Datenquellen:** STAC-Metadaten, Bucket-Listen und je Asset
höchstens ein Range-`GET` auf die ersten Kilobyte bzw. ein Overview-Block.
Keine AOI, keine Downloads ganzer Dateien. Item-IDs und `href` stehen nicht in
diesem Dokument.

**Messung über `gateway` — hier nicht möglich [M].** `gateway` verbindet
absichtlich zur geprüften Adresse; der Proxy der Sitzung arbeitet
namensbasiert und weist das ab. Gemessen am 26.10.2026: Earth Search und
EOPF über `gateway` → `UpstreamUnreachable`; Planetary Computer, CDSE, ASF,
CMR und DE Africa → `AddressRejected` (Name löst in der Sitzung nicht auf).
Das ist der bekannte Stand (Entscheidungslog, Zeile „`gateway` erreicht die
Quelle aus einer Cloud-Sitzung nicht“, offen). Die Befunde zum anonymen
Zugriff unten sind deshalb mit `curl` über den Proxy gemessen, ohne
Anmeldung, ohne Kopfzeilen außer `Range`. Der Check über `gateway` selbst
gehört in den Live-Smoke von DS-04 (CI ohne Proxy) und in Ottos Prüfung
(§11 E).

---


## 0. Kurzfassung

1. **Der Ausgangsbefund stimmt nicht mehr ganz.** Der Bucket hinter Earth
   Search `sentinel-1-grd` ist **nicht mehr Requester Pays**: Ein anonymer
   Range-`GET` auf ein Asset antwortet `206`, `?requestPayment` meldet
   `BucketOwner`, der AWS-Registry-Eintrag sagt `RequesterPays: False` [M][P].
   Nur die STAC-Items sagen weiter `storage:requester_pays: true` und tragen
   `s3://`-Adressen [M]. Eine Betriebszusage gibt es nicht.
2. **Weltweit gibt es Sentinel-1 anonym nur als GRD**, also ohne
   Geländekorrektur. Earth Search (und gleichwertig EOPF, CDSE) liefert
   Detektionswerte in **Radargeometrie**, georeferenziert nur über GCPs. Die
   Näherung, mit der rio-tiler solche Dateien kachelt (eine affine
   Transformation aus den GCPs), liegt in drei gemessenen IW-Szenen im Median
   130 bis 490 m und bis 2,2 km daneben; im Gelände bleiben auch mit einem
   Polynom 3. Ordnung bis rund 670 m [M] (§3.1). Dazu sind die Werte
   unkalibriert (DN), σ⁰ braucht die Kalibrier-LUT aus den Annotationen.
3. **Fertig geländekorrigiert (RTC) und anonym** gibt es nur regional: Digital
   Earth Africa `s1_rtc` (γ⁰, COG, EPSG:4326, Afrika, aktuell bis heute) [M].
   Weltweite RTC gibt es bei Planetary Computer (SAS-Token), CDSE (Anmeldung)
   und ASF/OPERA (Earthdata Login) — alle drei scheiden nach K1 aus [P][M].
4. **Empfehlung: Option 3, in zwei Schritten.** DS-04 bindet zuerst
   **DE Africa `s1_rtc`** an: Die Daten passen ohne Sondercode in den
   bestehenden COG-Pfad (CRS, Übersichten, physikalische Werte). Earth Search
   `sentinel-1-grd` kommt als zweiter, globaler Datensatz erst, wenn die
   Geländekorrektur entschieden ist — als eigener ADR, voraussichtlich Stufe
   T4 (externe Engine, M7 Paket 7g) oder ein Job-Operator mit neuer
   Abhängigkeit (§5, F2).
5. **Vor DS-04 nötig:** Freigabe des STAC-Hosts von DE Africa für die
   Umgebung (in dieser Sitzung gesperrt, F3) und Ottos Lizenz-Einstufung des
   abgeleiteten Produkts (F4).
6. **Quad-Pol:** Keine der Quellen liefert Quad-Pol; `decomp.py` ruht weiter
   (`ENTSCHEIDUNGEN` §3).

---

## 1. Kontext und Frage

Otto möchte Sentinel-1 anbieten, mit eigener Suche (Orbitrichtung,
Polarisation, Aufnahmemodus) und eigener Prozessierung (DS-01 §1). Die
naheliegenden Quellen galten als nicht token-frei: S1 GRD bei AWS als
„Requester Pays“, Planetary Computer mit SAS-Token, CDSE mit Anmeldung.

**Frage:** Welche Quelle erfüllt die Onboarding-Checkliste — vor allem den
anonymen Zugriffs-Check — und liefert Daten, die sich mit dem bestehenden
COG-Pfad (Kacheln, Zuschnitt, Operatoren) richtig darstellen und rechnen
lassen? Und was heißt Geländekorrektur dabei?

---

## 2. Kriterien

| # | Kriterium | Woher |
|---|---|---|
| K1 | Anonym, ohne Token, Konto, SAS oder Requester Pays (Metadaten **und** Assets) | `ENTSCHEIDUNGEN` §1; Checkliste Punkt 6 |
| K2 | Lizenz erlaubt Anzeige und Processing (B11), Attribution bekannt | `KLAERUNGEN` B11; Checkliste Punkt 4 |
| K3 | Geometrie: Pixel liegen ohne eigene SAR-Prozessierung an der richtigen Stelle | `architekturplan.md` 6.2, 6.3 |
| K4 | Radiometrie: Werte sind physikalisch (σ⁰/γ⁰) ohne Code je Datensatz | DS-00 Grundsätze; DS-05 |
| K5 | Kachelbar: COG mit Übersichten und CRS | `adr/0006`; Checkliste Punkte 5, 8 |
| K6 | Abdeckung global, Archiv tief, neue Szenen zeitnah | `adr/0003` §4; `adr/0005` Regel II |
| K7 | Suchfelder der Quelle (Orbitrichtung, Polarisation, Modus, relativer Orbit) | DS-02 |
| K8 | Fassung je Asset für den Cache | `adr/0014` §3.1 |
| K9 | Coverage-Anbieter zuzuordnen | Checkliste Punkt 2; `adr/0004` |
| K10 | Quelle dauerhaft betrieben, Kosten trägt nicht die Plattform | Prinzip 11; `adr/0007` K9 |
| K11 | Grenzen unverändert: B8, B9, Modulgrenzen, keine neue Abhängigkeit | `CLAUDE.md`; `architekturplan.md` 3.1 |

---

## 3. Befunde je Kandidat

### 3.1 Earth Search v1 `sentinel-1-grd` (Element 84, AWS) — [M] und [P]

**Collection [M]** (Q1): Titel „Sentinel-1 Level-1C Ground Range Detected
(GRD)“, STAC 1.0.0, `license: proprietary` mit Link auf das Sentinel Data Legal
Notice, `extent.spatial` global, zeitlich ab 2014-10 offen. `/aggregate` meldet
3 800 419 Items, `datetime_min` 2014-06-15, `datetime_max` heute 09:50 UTC
(das README nennt noch „~2.7 million“, Q11). Modi IW, EW, SM; Plattformen bis
S1C.

**Anonymer Zugriff [M]:**

| Anfrage, ohne Anmeldung und ohne `x-amz-request-payer` | Antwort |
|---|---|
| Collection, Items, `/search`, `/aggregate` | `200` |
| Range-`GET` auf ein Daten-Asset (COG), Szene vom 26.10.2026 | `206`, `ETag` 32 Hex, `Last-Modified` |
| derselbe Abruf auf eine Szene vom 01.06.2015 | `206` |
| Thumbnail (PNG), `safe-manifest` (XML) | `206` |
| `?requestPayment` am Bucket | `<Payer>BucketOwner</Payer>` |
| `?policyStatus` am Bucket | `<IsPublic>true</IsPublic>` |

- **Widerspruch in den Metadaten [M]:** Collection und Items tragen
  `storage:requester_pays: true`, `storage:region: eu-central-1`, und jedes
  Asset hat eine `s3://`-Adresse. Das Earth-Search-README erklärt genau das als
  Zeichen für Requester Pays: „When STAC Item assets … are in a requester pays
  bucket they are provided with an `s3://` style URL“ (Q11) [P].
- **Der AWS-Registry-Eintrag ist nachgezogen [P]:** `RequesterPays: False`,
  „ManagedBy: Element 84“ (Q12). Der Commit dazu (06.02.2026) begründet:
  „buckets were changed to non-Requester pays more than 1.5 years ago“ und
  „management of replication has been taken over by Element[84] more than a
  year ago“ (Q13) [P\*]. Eine Ankündigung von Element 84, Sinergise oder AWS
  wurde nicht gefunden [S].
- **Keine Betriebszusage [P]:** „This public API does not come with any
  guaranteed service.“ (Q11). Die Kosten trägt der Bucket-Eigentümer
  (AWS-Open-Data-Programm, `aws-pds`) [A].
- **Folgerung [A]:** K1 ist erfüllt, aber nur messbar, nicht zugesagt. Weil
  die Metadaten etwas anderes sagen, muss ein Live-Smoke den Zustand selbst
  prüfen (§7.2). Der Adapter müsste `s3://sentinel-s1-l1c/` auf den
  HTTPS-Host abbilden; `gateway` lässt nur `https` zu
  (`readers/cog.py` Z. 15) — eine neue, allgemeine Registry-Angabe, kein
  Sondercode.

**Format und Kachelbarkeit [M]:**

- Je Polarisation ein COG: `uint16`, Deflate, Blöcke 1024 × 1024, Übersichten
  2 bis 64. **Keine CRS, nur GCPs** (168 bis 294 je Szene, mit Höhe). Das ist
  GRD in Radargeometrie: „Sentinel-1 is not distributed as gridded data“
  (Q14) [P].
- Die Item-Felder `proj:epsg: 4326` und `proj:transform` beschreiben keine
  Gitterlage der Datei [M][A].
- **rio-tiler** (9.4.6, `io/rasterio.py` Z. 99–103) legt für GCP-Dateien ein
  `WarpedVRT` mit `transform.from_gcps` an, also **eine affine Näherung** [P].
  Abstand der GCPs zur Näherung, drei IW-Szenen vom 26.10.2026:

  | Szene (Höhe der GCPs) | affin, Median / max | Polynom 2. Ordnung | Polynom 3. Ordnung |
  |---|---|---|---|
  | flach (0 m) | 127 / 570 m | 4 / 16 m | 0 / 0 m |
  | bis 535 m | 130 / 528 m | 63 / 448 m | 41 / 411 m |
  | bis 826 m | 490 / 2 192 m | 74 / 700 m | 60 / 669 m |

  Das ist der Abstand **an den GCPs**; zwischen ihnen kommt der Fehler aus dem
  Relief hinzu. Im Gelände folgt keine glatte Funktion der Lage: Dafür braucht
  es ein DEM, also Geländekorrektur (§5) [A].

**Radiometrie [M][P]:** Die Werte sind DN (Amplitude), `nodata: 0`. σ⁰ ergibt
sich erst mit der Kalibrier-LUT aus `annotation/calibration/*.xml` (Assets
`schema-calibration-*`), dazu Rauschabzug aus `schema-noise-*`. Ohne das zeigt
eine dB-Darstellung Helligkeit, aber keine vergleichbare Größe [A].

**Suchfelder [M]:** Earth Search kennt die Query-Extension, kein CQL2
(`adr/0005` §3.1). Gemessen per `POST /search`:

| Feld | Werte (Summaries) | mit `query` filterbar |
|---|---|---|
| `sat:orbit_state` | ascending, descending | ja |
| `sat:relative_orbit` | 1–175 | ja |
| `sar:instrument_mode` | IW, EW, SM | ja |
| `sar:polarizations` | VV+VH, HH+HV, VV, VH, HH, HV | ja als `{"eq": "VH"}` (enthält); `{"eq": [...]}` → `400` |
| `s1:resolution` | full, high, medium | ja |
| `s1:product_timeliness` | NRT-10m … Reprocessing | ja |
| `platform` | sentinel-1a/b/c | ja [A, nicht einzeln gemessen] |

- `/queryables` nennt nur `sar:polarizations` [M]. Für DS-02 heißt das: Die
  Felder stehen in der Registry, nicht aus `queryables` abgeleitet.
- **Fallstrick [M]:** Ein CQL2-`filter` wird nicht abgewiesen, sondern
  **still übergangen**: `matched` = Gesamtzahl. Das bestätigt die Regel aus
  `adr/0005` §5, CQL2 nicht auszuweisen.

**Aktualität [M]:** fünf neueste Items, Aufnahme → `created` 59 bis 82 min.
**Fassung [M]:** keine `file:checksum`; `ETag` (32 Hex, kein
Multipart-Suffix) und `Last-Modified` per `HEAD`, eine Anfrage je Asset wie
beim DEM (`adr/0014` §3.1). **Coverage [M]:**
`/aggregate?aggregations=grid_geohex_frequency` antwortet für die Collection
(562 Zellen auf Stufe 1 für Oktober 2026) — derselbe Upstream-Anbieter wie für
Sentinel-2 (`adr/0004`). **Quicklook:** PNG je Szene, ebenfalls in
Radargeometrie [M][A].

### 3.2 Digital Earth Africa `s1_rtc` — [M], [P] und [S]

- **Produkt [M]:** γ⁰ RTC, VV und VH als `float32` linear, `nodata` NaN,
  dazu `mask`, `area`, `angle` je Kachel. COG, Deflate, Blöcke 1024,
  Übersichten 2, 4, 8, **EPSG:4326**, 0,0002° (rund 20 m), Kacheln zu 1° ×
  1° (5000 × 5000). Werte einer Kachel vom 24.10.2026 (Übersicht 3): VV
  p5/p50/p95 = −9,0 / −7,3 / −5,8 dB — plausibel für Vegetation [M][A].
- **Herkunft [M][S]:** Das Item verweist mit `derived_from` auf genau die
  GRD-Szene in `sentinel-s1-l1c` aus §3.1. Prozessiert nach CEOS CARD4L, nach
  Registry durch DE Africa, laut Doku mit Sentinel Hub und dem Copernicus-DEM
  nach Small 2011 (Q15, Q16) [P für CARD4L, S für die Einzelheiten].
- **Anonymer Zugriff [M]:** Bucket-Liste `200`, Range-`GET` auf ein COG `206`,
  `ETag` 32 Hex. Registry: `RequesterPays: False`, Zugriff mit
  `--no-sign-request` (Q15) [P].
- **STAC-API [M]:** `explorer.digitalearth.africa` ist in dieser Sitzung
  **gesperrt** (Proxy verweigert). Gemessen sind nur die STAC-Items, die im
  Bucket neben den Daten liegen (`*_metadata.json`, STAC 1.0.0-beta.2):
  `sat:orbit_state`, `sat:relative_orbit`, `sat:absolute_orbit`,
  `sar:instrument_mode`, `sar:polarizations`, `platform`; **keine**
  `file:checksum`. Ob die API `query` oder CQL2 kann und eine Aggregation für
  die Coverage hat, ist **offen** (F3).
- **Abdeckung und Aktualität [M][P]:** Afrika. Kacheln in Uganda, Südafrika und
  Nigeria haben Daten von 2018 bis zum 24. bzw. 26.10.2026. Wiederholung nach
  Registry rund 12 Tage (Q15) [P].
- **Lizenz [P][S]:** Die Registry nennt nur das Copernicus Legal Notice
  (Q15). Ob DE Africa für das abgeleitete Produkt eine eigene Lizenz setzt
  (ein Suchtreffer nennt CC BY 4.0), ist ungeprüft [S]. Einstufung liegt bei
  Otto (F4).
- **Kachelbarkeit [M][A]:** passt in den bestehenden COG-Pfad. Nur drei
  Übersichtsstufen: Unter etwa z8 liest eine Kartenkachel viele 1°-Dateien;
  `min_zoom` und Coverage-Karte übernehmen die kleinen Zoomstufen, wie bei
  Sentinel-2.

### 3.3 EOPF Sentinel Zarr Samples (ESA/EODC) — [M]

| Collection | Zeitraum (`extent`) | Format | Bemerkung |
|---|---|---|---|
| `sentinel-1-l1-grd` | 2017-02 bis 25.10.2026 | Zarr v2 | `data.eodc.eu`, freigegeben |
| `sentinel-1-l1-slc` / `-slc-zarr3` | 2023-11 bis 2026-07 | Zarr v2 / v3 | regional, Europa/Nordatlantik |
| `sentinel-1-l2-ocn` | 2025-02 bis 2025-09 | — | Ozean-Produkt |

- GRD-Store gemessen: `grd` als `uint16` 13 523 × 26 441 in Chunks zu 2048,
  **eine** Auflösung (keine Übersichten), Achsen `line`/`pixel`
  (Radargeometrie), GCPs als 8 × 21-Gitter, Kalibrier-LUTs (σ⁰, β⁰, γ)
  im Store. Kein `ETag`, kein `Last-Modified`; CORS offen.
- Queryables nur `id`, `datetime`, `geometry`. Ein CQL2-Filter auf
  `sat:orbit_state` wurde angenommen und lieferte ein passendes erstes Item;
  ob er wirklich filtert, ist nicht geprüft.
- Der Dienst ist ein Musterdienst ohne Zusage (`adr/0017` §3.1) [P].
- **Folgerung [A]:** gleiche Geometriefrage wie §3.1, dazu ohne Übersichten
  nicht kachelbar und ohne Fassung je Asset. Kein Kandidat; beobachten,
  sobald operative Zarr-Produkte kommen (Wiedervorlage aus `adr/0017` F4).

### 3.4 Microsoft Planetary Computer (`sentinel-1-grd`, `sentinel-1-rtc`) — [P]

- Host in dieser Sitzung gesperrt; Otto lässt ihn bewusst gesperrt
  (`adr/0003` §10.2).
- Assets nur mit SAS-Token: „Anyone can get a token from our Data
  Authentication API - you don't have to be a registered Planetary Computer
  user“ (Q17). Ein Token bleibt ein Token: scheidet nach K1 aus, wie
  `adr/0003` §6 Option C.
- `sentinel-1-rtc`: `license: CC-BY-4.0`, `msft:requires_account: true` im
  Collection-Template (Q18) [P]; global, γ⁰, 10 m [P\*]. `sentinel-1-grd`:
  GRD als COG, Legal Notice [P\*].
- Nur zur Einordnung: Nutzer melden 2026 Lücken und Versätze in der RTC
  (Issues #472, #492) [P\*].

### 3.5 Copernicus Data Space Ecosystem — [P]

- Suche: STAC unter `stac.dataspace.copernicus.eu/v1`; der alte Endpunkt
  `catalogue.dataspace.copernicus.eu/stac` ist seit 17.11.2025 abgekündigt
  (Q19). Beide Hosts in dieser Sitzung gesperrt [M].
- Download: „For downloading products you need an authorization token as only
  authorized users are allowed to download data products.“ (Q20). S3
  (`eodata`): „you must have a registered account“, Schlüssel aus dem
  Key-Manager (Q21). Ein anonymer Weg zu den Assets wurde nicht gefunden.
- Die GRD-COGs der CDSE sind per `gdal_translate` aus dem GRD-TIFF gemacht
  (Q22) [P], also dieselbe Radargeometrie wie §3.1 [A]. CARD-BS (γ⁰ RTC) nur
  auf Bestellung, Mosaike β⁰ [P\*].
- Scheidet nach K1 aus.

### 3.6 ASF und OPERA RTC-S1 — [M] und [P]

- ASF-Hosts in dieser Sitzung gesperrt [M]. Suche öffentlich [S], Download
  „An authenticated session is generally required“ (Q23) [P\*]; HyP3 (RTC auf
  Bestellung, GAMMA) verlangt einen Earthdata Login (Q24) [P\*].
- OPERA RTC-S1 (CC BY 4.0, global, γ⁰, 30 m): Der Bucket
  `asf-cumulus-prod-opera-products` antwortet anonym `403` auf Liste und
  Objekt [M]; Registry: „ControlledAccess“ über Earthdata (Q25) [P].
- Scheidet nach K1 aus.

### 3.7 Weitere anonyme Quellen — [M] und [P]

| Quelle | Inhalt | Zugriff | Lizenz | Warum kein Kandidat |
|---|---|---|---|---|
| Earth Big Data, Global Coherence and Backscatter | γ⁰ und Kohärenz je Jahreszeit, 12/2019–11/2020 | anonym `200` [M] | CC BY 4.0 [P] | Einmal-Produkt, „No updates“ (Q26) |
| Digital Earth Pacific `dep_s1_geomad` | Jahreskomposit, 10 m, Pazifik | anonym `200` [M] | CC BY 4.0 [P] | Komposit, keine Szenen (Q27) |
| Indigo `sentinel-s1-rtc-indigo` | RTC, USA | anonym `200` [M] | eigene „Indigo Atlas Sentinel License“ [P] | Updates „paused“ (Q28), keine offene Lizenz |
| SLC auf AWS (LiveEO, Südostasien) | SLC, regional | anonym [P\*] | — | SLC, regional |

Die beiden ersten können später eigene Datensätze werden (Einmal-Produkt bzw.
Komposit); für „Sentinel-1 mit Suche nach Orbit und Polarisation“ taugen sie
nicht.

---

## 4. Optionen

### Option 1 — Earth Search GRD jetzt, global, mit Näherungsgeometrie

Datensatz `sentinel-1-grd`, Kacheln über den bestehenden GCP-Pfad von
rio-tiler, Darstellung DN in dB. Suche, Coverage und Fassung sind wie bei
Sentinel-2 vorhanden. **Preis:** Lagefehler von Hunderten Metern bis über
2 km (§3.1), Werte ohne Kalibrierung; jeder Zuschnitt und jede Band-Math
rechnet auf falsch liegenden, nicht vergleichbaren Werten. Das ließe sich
nach Prinzip 9 (Ehrlichkeit in der Anzeige) nur kennzeichnen, nicht beheben
[A].

### Option 2 — Nur DE Africa `s1_rtc`

Ein Datensatz mit richtiger Geometrie und physikalischen Werten, ohne
Sondercode. **Preis:** nur Afrika; globale Sentinel-1-Daten gibt es nicht.

### Option 3 — Zwei Schritte: DE Africa zuerst, Earth Search GRD nach der Geländekorrektur (empfohlen)

1. **DS-04** bindet `s1_rtc` an (wie Option 2).
2. Ein eigener ADR **„Geländekorrektur für Sentinel-1 GRD“** (Stufe C) wägt
   die Wege aus §5 ab. Erst danach kommt `sentinel-1-grd` als globaler
   Datensatz — dessen Kacheln und Jobs zeigen dann γ⁰ aus der Korrektur,
   nicht die GRD-Rohwerte.
3. Bis dahin kann Earth Search GRD optional als **Katalogeintrag ohne
   Anzeige** erscheinen (B11 Stufe 1: Suche, Footprints, Coverage, Link zur
   Quelle) — Otto entscheidet (F2).

### Option 4 — Warten

Keine Anbindung, bis eine globale, anonyme RTC-Quelle oder operative
EOPF-Produkte kommen. Kein Termin in Sicht (§3.3, §3.4).

### Verworfen ohne eigene Option

- Planetary Computer, CDSE, ASF/OPERA: verlangen Token, Anmeldung oder
  Earthdata Login (K1).
- EOPF-GRD: Musterdienst, ohne Übersichten, ohne Fassung (§3.3).

---

## 5. Was Geländekorrektur bedeutet

Der Weg von GRD zu einem Bild, das richtig liegt und vergleichbare Werte hat
[P\* für die Verfahren, Q16, Q24, Q29]:

1. **Kalibrierung:** DN → β⁰/σ⁰/γ über die LUT der Annotationen
   (σ⁰ = DN² / A²), dazu Abzug des thermischen Rauschens.
2. **Terrain Flattening** (Small 2011): Normierung auf die beleuchtete
   Fläche → γ⁰ RTC; ohne sie sind Hänge zum Sensor hin zu hell.
3. **Geokodierung mit DEM** (Range-Doppler): Jeder Pixel kommt an seine
   Bodenposition; Layover und Schatten werden maskiert.

**Fertig von der Quelle** gibt es das anonym nur bei DE Africa (§3.2).
**Selbst rechnen** hieße [A]:

| Weg | Werkzeug (Lizenz) | Stufe | Bemerkung |
|---|---|---|---|
| a | sarsen (Apache-2.0, Beta) als Job-Operator | T2/T2L | **neue Abhängigkeit**; DEM (Copernicus GLO-30 ist schon Datensatz) |
| b | SNAP/s1tbx (GPL-3.0), ISCE3 (Apache-2.0), pyroSAR (MIT, braucht SNAP oder GAMMA) als Container | T3 | eigenes Image je Werkzeug |
| c | externe Engine (openEO-Backend mit SAR-Prozessen, HyP3) | T4, M7 Paket 7g | HyP3 braucht Earthdata Login → K1 |

Als **Kachelrechnung (T1)** ist das nicht realistisch: Kalibrierung und
Geokodierung brauchen die ganze Szene, ihre Annotationen und ein DEM, und
Layover hängt von Nachbarpixeln weit außerhalb der Kachel ab [A]. Damit liegt
die Geländekorrektur bei T2/T3/T4, und die Darstellung im Viewer kommt aus
einem Job-Ergebnis, nicht aus den Quelldaten. Das ist ein eigener ADR wert
(F2).

---

## 6. Bewertung

| | K1 | K2 | K3 | K4 | K5 | K6 | K7 | K8 | K9 | K10 | K11 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Earth Search GRD | ✓ gemessen, nicht zugesagt | ✓ (wie S2, `adr/0003` §11.2) | ✗ 0,1–2 km | ✗ DN | ~ GCPs | ✓ global, ab 2014, ~1 h | ✓ `query` | ~ ETag per `HEAD` | ✓ Aggregation | ~ | ~ `s3://`-Abbildung |
| DE Africa `s1_rtc` | ✓ Bucket; STAC-Host offen | offen (F4) | ✓ | ✓ γ⁰ | ✓ | ~ nur Afrika, ab 2018 | ~ Felder da, API offen | ~ ETag per `HEAD` | offen | ~ | ✓ |
| EOPF GRD | ✓ | ✓ | ✗ | ✗ DN | ✗ keine Übersichten | ~ | ~ | ✗ | offen | ✗ Musterdienst | ✓ |
| PC, CDSE, ASF | ✗ | — | — | — | — | — | — | — | — | — | — |

Option 3 nimmt aus jeder Zeile das Belastbare: richtige Daten sofort, wo es
sie anonym gibt, und den globalen Datensatz erst, wenn er richtig gerechnet
werden kann.

---

## 7. Folgen

### 7.1 Für DS-04 (bei Option 3)

- Registry-Eintrag `s1_rtc` mit `asset_hosts` für den Bucket, Capability
  `quad_pol = false`, Standarddarstellung γ⁰ in dB (eine Band-Math
  `10*log10(vv)` über `op=band_math`, Plan M4-09 F3), Suchfelder aus §3.2 für
  DS-02.
- Vorab in einer **neuen** Sitzung mit freigegebenem STAC-Host messen:
  `query`/CQL2, Aggregation (Coverage-Anbieter), Lizenzfeld,
  `file:checksum`, Zeitraum (F3).
- Live-Smoke über `gateway` (CI) als eigentlicher anonymer Zugriffs-Check.

### 7.2 Für einen späteren Earth-Search-GRD-Datensatz

- Allgemeine Registry-Angabe „`s3://`-Präfix → HTTPS-Host“ (kein Sondercode).
- Live-Smoke prüft den Requester-Pays-Zustand selbst (anonymer Range-`GET`
  `206`, `?requestPayment` = `BucketOwner`); die STAC-Angabe allein genügt
  nicht (§3.1).
- Anzeige erst nach der Geländekorrektur (§5).

### 7.3 In jeder Option

- Lizenz: Copernicus Sentinel Legal Notice wie bei Sentinel-2 (`adr/0003`
  §11.2), Attribution „Contains modified Copernicus Sentinel data [Jahr]“;
  für DE Africa zusätzlich deren Angabe (F4).
- `decomp.py` ruht; keine Quelle liefert Quad-Pol.
- Keine Importregel ändert sich; keine neue Abhängigkeit durch diesen ADR.

---

## 8. Was offen bleibt

- Lizenz, Suchfähigkeit und Coverage der DE-Africa-STAC-API (F3, F4).
- Ob Element 84 die Metadaten (`requester_pays`, `s3://`) nachzieht; eine
  Betriebszusage gibt es nicht.
- Der ADR zur Geländekorrektur (F2), mit DS-05 abzustimmen.

---

## 9. Fragen an Otto

**F1 — Welche Option?**
1. Option 3: DE Africa `s1_rtc` zuerst (DS-04), Earth Search GRD nach einem ADR zur Geländekorrektur **(Empfehlung)**
2. Option 1: Earth Search GRD jetzt, global, mit Näherungsgeometrie und DN
3. Option 2: nur DE Africa, kein globaler Datensatz geplant
4. Option 4: warten

**F2 — Earth Search GRD bis zur Geländekorrektur (bei F1 = 1)?**
1. Gar nicht sichtbar; ADR „Geländekorrektur“ (Stufe C) nach DS-04 **(Empfehlung)**
2. Schon jetzt als Katalogeintrag ohne Anzeige (Suche, Footprints, Coverage, Link), ADR wie 1
3. Kein ADR zur Geländekorrektur; Sentinel-1 bleibt regional

**F3 — Hosts für die Umgebung freigeben (bei F1 = 1 oder 3)?**
1. `explorer.digitalearth.africa` (STAC) und `docs.digitalearthafrica.org` (Lizenz, Doku) freigeben; DS-04 misst dann in einer neuen Sitzung **(Empfehlung)**
2. Nur `explorer.digitalearth.africa`
3. Nicht freigeben; Otto prüft STAC und Lizenz selbst (§11 C)

**F4 — Lizenz von DE Africa `s1_rtc`?**
1. Vor DS-04 einen Vorschlag des `license-checker` mit Belegstellen; Otto stuft ein **(Empfehlung)**
2. Otto stuft direkt ein (Browser, §11 C)

---

## 10. Entscheidungen nach Ottos Antwort

Folgen, sobald F1–F4 beantwortet sind: Status, Zeile im Entscheidungslog,
Nachtrag in `docs/plans/ds/ds-04-s1-anbinden.md` (Quelle, Produktart).

---

## 11. Prüfanleitung für Otto

Nur Metadaten und je Datei die ersten Kilobyte, keine AOI. Windows PowerShell
5.1 oder Browser.

Vorab, nur in Windows PowerShell 5.1 nötig: TLS 1.2 einschalten.

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$es = 'https://earth-search.aws.element84.com/v1'
$s1 = 'https://sentinel-s1-l1c.s3.eu-central-1.amazonaws.com'
$af = 'https://deafrica-sentinel-1.s3.af-south-1.amazonaws.com'
function Get-FirstKb($u) {   # Range-GET ohne Anmeldung, gibt Status und ETag aus
  $r = [Net.HttpWebRequest]::Create($u); $r.AddRange(0, 1023)
  try { $x = $r.GetResponse(); "$([int]$x.StatusCode) $($x.Headers['ETag'])"; $x.Close() }
  catch { "Fehler: $($_.Exception.InnerException.Response.StatusCode)" }
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
$i.assets.PSObject.Properties.Name               # (vv vh … oder hh hv …, thumbnail, safe-manifest, schema-*)
$i.properties.datetime; $i.properties.created    # (rund eine Stunde Abstand)
```

**B. Earth Search: der Bucket ist trotzdem anonym (§3.1).**

```powershell
$a = ($i.assets.vv, $i.assets.hh | Where-Object { $_ })[0].href -replace '^s3://sentinel-s1-l1c/', "$s1/"
Get-FirstKb $a                                   # (206 "…32 Hex-Zeichen…")
(Invoke-WebRequest "$s1/?requestPayment" -UseBasicParsing).Content
#   (… <Payer>BucketOwner</Payer> …)
```

**C. DE Africa (§3.2) und Lizenz (F4).**

```powershell
$l = (Invoke-WebRequest "$af/?list-type=2&delimiter=/&prefix=s1_rtc/N00E030/2026/10/" -UseBasicParsing).Content
([regex]::Matches($l, '<Prefix>[^<]+</Prefix>')).Value   # (Tage im Oktober 2026)
```

Im Browser:

1. `https://explorer.digitalearth.africa/stac/collections/s1_rtc` — Feld
   `license`, `extent`; in einem Item (Link „items“) prüfen, ob Assets
   `file:checksum` tragen.
2. `https://docs.digitalearthafrica.org/en/latest/data_specs/Sentinel-1_specs.html`
   — Lizenz und Zitierhinweis des abgeleiteten Produkts.
3. `https://registry.opendata.aws/sentinel-1/` — „RequesterPays“ steht auf
   „False“ (bzw. kein Hinweis auf Requester Pays mehr).

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

## 12. Quellen

Alle abgerufen am 26.10.2026.

- **Q1** Earth Search v1, Collection `sentinel-1-grd`, `/search`,
  `/aggregate`, `/queryables`: https://earth-search.aws.element84.com/v1/collections/sentinel-1-grd — [M]
- **Q2** Bucket `sentinel-s1-l1c` (eu-central-1): Liste, `?requestPayment`,
  `?policyStatus`, Range-`GET` auf drei Assets — [M]
- **Q3** Bucket `deafrica-sentinel-1` (af-south-1): Liste, Item-JSON,
  Range-`GET`, Overview-Block — [M]
- **Q4** EOPF-STAC, Collections und erstes GRD-Item, `.zmetadata`:
  https://stac.core.eopf.eodc.eu/collections — [M]
- **Q5** Buckets `asf-cumulus-prod-opera-products`, `sentinel-s1-rtc-indigo`,
  `sentinel-1-global-coherence-earthbigdata`, `dep-public-data` — [M]
- **Q11** Element84, Earth Search, README:
  https://github.com/Element84/earth-search/blob/main/README.md — [P]
- **Q12** AWS Open Data Registry, `sentinel-1.yaml`:
  https://github.com/awslabs/open-data-registry/blob/main/datasets/sentinel-1.yaml — [P]
- **Q13** Commit `63c938c` im Open Data Registry, 06.02.2026:
  https://github.com/awslabs/open-data-registry/commit/63c938c85613ba76422c45d54a7369648f73e8d7 — [P\*]
- **Q14** Element84, `docs/collections/sentinel-1-grd.md`:
  https://github.com/Element84/earth-search/blob/main/docs/collections/sentinel-1-grd.md — [P]
- **Q15** AWS Open Data Registry, `deafrica-sentinel-1.yaml`:
  https://github.com/awslabs/open-data-registry/blob/main/datasets/deafrica-sentinel-1.yaml — [P]
- **Q16** DE Africa, Sentinel-1 specs:
  https://docs.digitalearthafrica.org/en/latest/data_specs/Sentinel-1_specs.html — [S]
- **Q17** Planetary Computer, „Using tokens for data access“:
  https://github.com/microsoft/PlanetaryComputerDataCatalog/blob/main/docs/concepts/sas.md — [P]
- **Q18** Planetary Computer, Collection-Template `sentinel-1-rtc`:
  https://github.com/microsoft/planetary-computer-tasks/blob/main/datasets/sentinel-1-rtc/collection/template.json — [P]
- **Q19** CDSE-Doku, STAC: https://github.com/eu-cdse/documentation/blob/publish/APIs/STAC.qmd — [P]
- **Q20** CDSE-Doku, OData: https://github.com/eu-cdse/documentation/blob/publish/APIs/OData.qmd — [P]
- **Q21** CDSE-Doku, S3: https://github.com/eu-cdse/documentation/blob/publish/APIs/S3.qmd — [P]
- **Q22** CDSE-Doku, Sentinel-1 COG:
  https://github.com/eu-cdse/documentation/blob/publish/Data/Others/Sentinel1_COG.qmd — [P]
- **Q23** ASF, `asf_search`: https://github.com/asfadmin/Discovery-asf_search — [P\*]
- **Q24** ASF HyP3, Zugang und RTC-Produkt:
  https://github.com/ASFHyP3/hyp3-docs (`docs/using/requesting_access.md`,
  `docs/guides/rtc_product_guide.md`) — [P\*]
- **Q25** AWS Open Data Registry, OPERA RTC-S1:
  https://registry.opendata.aws/nasa-operal2rtc-s1v1/ — [P]
- **Q26** AWS Open Data Registry, Global Coherence and Backscatter:
  https://registry.opendata.aws/ebd-sentinel-1-global-coherence-backscatter/ — [P]
- **Q27** AWS Open Data Registry, `dep-s1-geomads`:
  https://registry.opendata.aws/dep-s1-geomads/ — [P]
- **Q28** AWS Open Data Registry, `sentinel-1-rtc-indigo`:
  https://registry.opendata.aws/sentinel-1-rtc-indigo/ — [P]
- **Q29** D. Small, „Flattening Gamma: Radiometric Terrain Correction for SAR
  Imagery“, IEEE TGRS 49(8), 2011: https://doi.org/10.1109/TGRS.2011.2120616 — [S];
  Werkzeuge: https://github.com/bopen/sarsen, https://github.com/senbox-org/snap-engine,
  https://github.com/isce-framework/isce3, https://github.com/johntruckenbrodt/pyroSAR — [P\*]

Im Repo: `adr/0003` §6, §10.2, §11.2; `adr/0004`; `adr/0005` §3.1, §5;
`adr/0007` §12; `adr/0014` §3.1, F3; `adr/0017` §3.1, F4;
`backend/earthx/readers/cog.py` Z. 15; rio-tiler 9.4.6 `io/rasterio.py`
Z. 99–103; Entscheidungslog (Zeile „`gateway` erreicht die Quelle aus einer
Cloud-Sitzung nicht“).
