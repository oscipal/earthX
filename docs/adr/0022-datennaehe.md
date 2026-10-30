# ADR 0022 — Datennähe: Hauptquelle und Rechenort

- **Status:** **Angenommen** von Otto am 2026-10-30. F1–F7 jeweils nach Empfehlung (§9); die Rechtsfrage zur Datenhaltung in der Schweiz (F7) bleibt bis M6 offen. **Stufe 2 der Messung (Test-VMs, kostet Geld) läuft nur nach ausdrücklicher Freigabe durch Otto** (§8.3).
  - Nummer 0022: Am 30.10.2026 gab es weder auf `main` noch in einem offenen PR ein `adr/0022`.
- **Datum:** 2026-10-30
- **Aufgabe:** NM4-48 laut `docs/plans/querschnitt/nm4-48-datennaehe.md` (Backlog Nr. 48).
- **Autonomiestufe:** C. Kein Produktivcode. Es gibt keine Änderung an `backend/`, `frontend/`, `scripts/`, Fixtures, `.github/`, `.claude/` oder `CLAUDE.md`. Gemessen wurde nur lokal mit dem vorhandenen Gerüst `scripts/tile-bench/` gegen eine synthetische Quelle (§3).
- **Vorab fest:**
  - Föderation bleibt (Aufgabe §3.5).
  - Die Plattform läuft in der EU oder der Schweiz (`projektuebersicht.md` §4).
  - Die fertige Plattform enthält nichts, was einen Token braucht (`ENTSCHEIDUNGEN` §1). Ausnahme ist nur der anonym ausgestellte Nachweis nach `adr/0018` F4, und auch der erst nach positiver Messung.
  - Ausgehende Zugriffe auf Datenquellen laufen nur über `gateway` (`KLAERUNGEN` B8).
  - Die Wahl des Cloud-Anbieters fällt in M6 (`projektplan.md`), die Auswahl der Quellen in M5.
- **Grundlage:**
  - `projektuebersicht.md` §2 (Prinzipien 2, 10, 11, 16), §4 und §16 (Cloud-Provider).
  - `architekturplan.md` §2 (Zeile „Wo die Daten liegen“), 3.1, 6.4, 7.3, 7.7, 12.1–12.3 und 15.3.
  - `adr/0002` (aus Cloud-Sitzungen keine Messung gegen Quellen), `adr/0003` §10, `adr/0005` §3.6, `adr/0006` §8 (Nachtrag NM4-26), `adr/0011`, `adr/0017`, `adr/0018`.
  - `plans/querschnitt/nm4-26-kachel-leistung.md` §8 und §17.
- **Betroffen (erst mit einer Entscheidung):**
  - Registry (Feld `data_region`, §7.2);
  - die Auswahl der Quellen in M5;
  - die Shortlist der Anbieter in M6;
  - `architekturplan.md` 12.2.

---

## Methode und Belegstufen

Belegstufen wie in `adr/0018`:

- **M:** in dieser Sitzung gemessen; Verfahren in §3.
- **P:** am Primärdokument selbst gelesen (im Repo mit Pfad).
- **P\*:** Primärdokument über das Abrufwerkzeug eines Hilfsagenten gelesen. Das Werkzeug fasst Seiten zusammen, Zitate sind deshalb sinngemäß und vor einer Annahme an der Quelle zu prüfen. Das gilt auch für Preislisten als JSON und für die Quelltexte von Doku-Seiten auf GitHub.
- **S:** Suchtreffer oder Zusammenfassung, Wortlaut nicht geprüft.
- **A:** eigene Ableitung, ein Argument und kein Beleg.

**Was in dieser Sitzung nicht ging [M]:**

- Der Proxy der Sitzung sperrt fast alle Anbieterseiten. Gesperrt waren unter anderem CDSE (Doku, STAC, Forum), CloudFerro, CREODIAS, Open Telekom Cloud, `planetarycomputer.microsoft.com`, `learn.microsoft.com`, `azure.microsoft.com`, `aws.amazon.com` und `docs.aws.amazon.com`.
- Erreichbar waren unter anderem `earth-search.aws.element84.com`, `registry.opendata.aws`, die AWS-Preislisten (`pricing.us-east-1.amazonaws.com`), `dataspace.copernicus.eu`, `stac.core.eopf.eodc.eu`, `data.eodc.eu` und GitHub.
- Die CDSE-Doku ist deshalb aus ihrem Quelltext gelesen (Repo `eu-cdse/documentation`, Branch `publish`). Die Doku zum Planetary Computer stammt aus `microsoft/PlanetaryComputerDataCatalog`.
- Preise von Azure, CloudFerro und Open Telekom Cloud sind höchstens **S**.
- Echte Latenzen zu den Quellen sind hier nicht messbar (`adr/0002`). Das ist der Grund für den Messplan (§8).

**Anfragen an Datenquellen:** keine. Die Hilfsagenten lasen öffentliche Katalog- und Doku-Seiten. Item-IDs, `href`, Tokens und genaue Flächen stehen nicht in diesem Dokument.

---

## 0. Kurzfassung

1. **Ottos Frage, kurz beantwortet:** Ja, die Daten sollen nah am Rechner liegen. Aber „nah“ heißt nach der Modellmessung **gleicher Kontinent, nicht gleicher Anbieter** [M][A]:
   - Kalte Mosaik-Kachel wie am 28.10.2026: rund **3,6 s** bei einer Quelle in Oregon, **1,1 s** bei einer Quelle rund 25 ms entfernt und **0,7 s** in derselben Region (§3).
   - Der Schritt Oregon → EU bringt also den Großteil. Der Schritt EU → dieselbe Region bringt noch 0,4 s.
2. **Wo die Daten liegen [P\*]:**
   - In AWS `us-west-2` liegen nur die Sentinel-2-COGs von Earth Search und Landsat (Requester Pays).
   - Sentinel-1 GRD, Copernicus DEM, Sentinel-3, Sentinel-5P, WorldCover und Sentinel-2 als JP2 liegen anonym in AWS `eu-central-1` (Frankfurt).
   - Das CDSE-Archiv liegt in Warschau, EOPF-Zarr in Wien, der Planetary Computer in Azure West Europe (Niederlande).
   - Alles außer zwei Beständen liegt also schon in der EU.
3. **Keine der drei Kandidaten taugt als „eine Hauptquelle mit Server daneben“:**
   - **A** (AWS `us-west-2`): verletzt EU/CH-Hosting (AOIs sind personenbezogen); nur für Sentinel-2 und Landsat schneller.
   - **B** (CDSE + CloudFerro/OTC): Download nur mit Konto (Regel §1). Das Kontingent gilt je Konto, nicht je Plattform: 4 Verbindungen, 20 MB/s je Verbindung, 12 TB je 30 Tage, **50 000 direkte COG-Anfragen im Monat** [P\*]. Eine kalte Kachel braucht rund 32 Anfragen [M]. Sentinel-2 gibt es nur als SAFE/JP2.
   - **C** (Planetary Computer + Azure): Der Token ist laut Bedingungen nicht an Dritte weiterzugeben [P\*]. Die Dienstbedingungen sind die einer Preview. Der Betrieb war 2026 wackelig: Sentinel-1 RTC ohne Aktualisierung seit 25.06.2026 (Issue #489) [P\*]; eine Datenqualitätsmeldung vom 29.10.2026 nennt Sentinel-2-L2A-Bilder seit dem 27.10.2026 „potentially affected“ durch eine fehlerhafte Umrechnung (Issue #516) [P\*]. Einzelheiten in §4.3.
4. **Empfehlung (§6):** **Region statt Anbieter.**
   - Rechenort in der EU im Raum Frankfurt; Kandidaten: AWS `eu-central-1` und andere Anbieter mit Rechenzentrum dort, Auswahl in M6.
   - Föderation ohne exklusive Hauptquelle. Die Lage der Daten wird ein Feld der Registry (`data_region`) und ein Kriterium der Quellenauswahl in M5.
   - Sentinel-2 als einziger großer Bestand in Oregon wandert in die EU, sobald EOPF-Zarr operativ ist (Wiedervorlage aus `adr/0017`). Bis dahin bleibt es bei Earth Search mit Cache.
   - CDSE wird Katalogquelle mit Link, keine Lesequelle.
   - Planetary Computer bleibt auf Teil B von `adr/0018` beschränkt.
5. **Messplan (§8):** Stufe 1 auf Ottos Rechner, kostenlos, PowerShell 5.1. Stufe 2 auf Test-VMs in drei bis vier Regionen, kostenpflichtig (grob unter 10 €), **nur nach ausdrücklicher Freigabe durch Otto**. Messgrößen und Schwellen stehen vorab fest, damit die Zahlen entscheiden.

---

## 1. Kontext und Frage

> Wäre es nicht smart eine datenquelle zu nehmen wo ich möglichst viele daten von der gleichen quelle haben kann und wo ich auch einen server laufen lassen kann? also für processing speed und rendering speed? (Otto, 28.10.2026)

**Anlass:** Am 28.10.2026 hat Otto lokal eine kalte Mosaik-Kachel gemessen: 4 Szenen über die UTM-Grenze 31/32, `red` + `nir`, NDVI, z10, 512 px. Kalt dauerte sie 6,0 s, warm 0,16 s (Backlog Nr. 48; `plans/nach-m4-backlog.md` Nr. 32). Sentinel-2 kommt von Earth Search aus AWS `us-west-2`.

**Die Zeit einer Kachel zerfällt in drei Wege [A]:**

| Weg | Was | Hängt ab von |
|---|---|---|
| U | Browser ↔ Server: Anfrage, PNG zurück | Ort des Servers relativ zum Nutzer |
| Q | Server ↔ Quelle: Item holen, COG-Köpfe, Blöcke | Ort des Servers relativ zur Quelle, Leitung |
| R | Rechnen: dekomprimieren, umprojizieren, Operator, PNG | CPU, Prozesse |

- Warm fällt Q fast weg (Cache), daher 0,16 s.
- Kalt dominiert Q, weil GDAL die Blöcke nacheinander holt (`SERIAL`, `adr/0006` §8 Nachtrag NM4-26). Jede Anfrage kostet eine volle Rundlaufzeit.
- Datennähe verkürzt Q. U verkürzt sie nur, wenn der Server auch nah am Nutzer steht.

**Frage dieses ADR:** Sollen wir eine Hauptquelle wählen und daneben rechnen? Wenn ja, welche, und was folgt daraus für Föderation, M5 und M6?

---

## 2. Kriterien

| # | Kriterium | Woher |
|---|---|---|
| K1 | Lesen ohne Konto und ohne Token (sonst Regeländerung nötig) | `ENTSCHEIDUNGEN` §1; Prinzip 2; `adr/0018` F4 |
| K2 | Abdeckung: S1 GRD/RTC, S2 L1C/L2A, S3, S5P, Landsat, Copernicus DEM, CLMS | Aufgabe §3.1 |
| K3 | Format und Metadaten: COG oder Zarr, STAC mit den Filtern aus DS-02 | Prinzip 3; `adr/0021` |
| K4 | Latenz und Durchsatz Server ↔ Quelle (Q) und Nutzer ↔ Server (U) | Anlass |
| K5 | EU/CH-Hosting, DSGVO/revDSG für Konten und AOIs | `projektuebersicht.md` §4 |
| K6 | Kosten: Rechnen, Egress, Requester Pays | Prinzip 10 |
| K7 | Betrieb: Zusagen, Limits, Stabilität 2026 | Prinzip 11 |
| K8 | Bindung: Wechsel von Rechenort oder Quelle ohne Umbau | Prinzip 16; `architekturplan.md` 1.1 |
| K9 | Machbar für 1 bis 3 Personen | `architekturplan.md` 1.1 |

---

## 3. Wie viel Datennähe bringt — Modellmessung [M]

**Verfahren:** Gerüst aus NM4-26 (`scripts/tile-bench/`, Aufruf wie `plans/querschnitt/nm4-26-kachel-leistung.md` §17.1).

- Der echte `tiler` liest synthetische COGs im Aufbau der Earth-Search-Dateien (10980², Blöcke 1024).
- Die Quelle ist ein lokaler Server mit künstlicher Verzögerung: `RTT_MS` je Anfrage, `CONNECT_MS` je neuer Verbindung, `ITEM_MS` für den Item-Abruf.
- Jeder Lauf startet kalt: frischer Prozess, leere Caches in Postgres.
- Rechner der Sitzung: 4 Kerne, 16 GB.
- Gemessen wurde die Mosaik-Kachel wie bei Otto: 4 Szenen, NDVI, z10, 512 px (`view.py --mosaic --scenes 4 --z 10 --side 1 --tilesize 512`). Dazu kam eine Ansicht 1280 × 800 px bei Kartenzoom 10,2 (`--viewport 1280x800 --map-zoom 10.2`, 6 Kacheln).

**Profile [A]:** Die Latenzen sind gesetzt, nicht bei Otto gemessen.

- „Oregon“ 170/350/300 ms: wie NM4-26, abgeleitet aus 0,37 s TLS und 0,48 s bis zum ersten Byte von der Sitzung nach `us-west-2`.
- „EU-Nachbar“ 25/60/80 ms: etwa Zürich ↔ Wien oder Warschau; belegt ist das nicht, siehe §4.6.
- „gleiche Region“ 2/5/30 ms.

| Profil | Leitung | Kachel kalt (3 Läufe) | Ansicht 6 Kacheln kalt | Anfragen an die Quelle (Kachel / Ansicht) | MB von der Quelle (Kachel / Ansicht) |
|---|---|---|---|---|---|
| Oregon | unbegrenzt | 3,7 / 3,6 / 3,6 s | 4,9 s | 32 / 125 | 24,7 / 129 |
| Oregon | 100 Mbit/s | 5,0 / 4,8 / 4,9 s | 13,3 s | 32 / 136 | 24,7 / 134 |
| EU-Nachbar | unbegrenzt | 1,1 / 1,1 / 1,1 s | 2,7 s | 32 / 100 | 24,7 / 104 |
| gleiche Region | unbegrenzt | 0,7 / 0,6 / 0,7 s | 2,3 s | 32 / 84 | 24,7 / 89 |
| gleiche Region | 1 Gbit/s | 0,8 / 0,8 / 0,8 s | 2,4 s | 32 / 91 | 24,7 / 101 |

Phasen der einzelnen Kachel (`summary.py`):

- `open` (COG-Köpfe): 1116 ms (Oregon), 235 ms (EU-Nachbar), 82 ms (gleiche Region).
- PNG kodieren: rund 110 ms in allen Profilen.

**Was die Zahlen sagen:**

- **D1 Die kalte Kachel ist eine Kette von Rundläufen.** 32 Anfragen über 5 Verbindungen. Von Oregon nach EU fällt die Zeit um den Faktor 3,3. Von EU nach „gleiche Region“ fällt sie nur noch um 0,4 s.
- **D2 Ab EU-Nähe rechnet der Server.** In „gleiche Region“ ist die Ansicht CPU-gebunden (2,3 s für 6 Kacheln in einem Prozess). Mehr Nähe hilft dann nicht mehr, mehr Prozesse schon (NM4-26 B5, S4).
- **D3 Die Leitung zählt, wo der Server weit weg und schmal angebunden ist.** Ottos 6,0 s liegen zwischen „Oregon unbegrenzt“ und „Oregon 100 Mbit/s“. Seine Messung hat zusätzlich zwei UTM-Zonen und echte Item-Abrufe.
- **D4 Modell, nicht Wirklichkeit.**
  - Alle Szenen sind dieselbe Datei.
  - Kein Wechsel der UTM-Zone.
  - Die Server von S3, Blob oder Ceph antworten real anders.
  - Die Latenzen sind gesetzt.
  - Die Messung in §8 prüft genau diese Annahmen.

---

## 4. Befunde je Anbieter

### 4.1 Earth Search / AWS Open Data — A und D

**Wo die Daten liegen [P\*]:** Registry (`registry.opendata.aws`) und Items von Earth Search, abgerufen am 30.10.2026.

| Bestand | Bucket | Region | Format | Zugang |
|---|---|---|---|---|
| S2 L2A COG (`sentinel-2-l2a`, `sentinel-2-c1-l2a`) | `sentinel-cogs`, `e84-earth-search-sentinel-data` | `us-west-2` | COG | anonym (`https`) |
| S2 L2A JP2 | `sentinel-s2-l2a` | `eu-central-1` | JP2 | laut Registry ohne Konto [P\*]; früher Requester Pays, Messpunkt §8 |
| S2 L1C | `sentinel-s2-l1c` | `eu-central-1` | JP2 | Requester Pays |
| S1 GRD (`sentinel-1-grd`) | `sentinel-s1-l1c` | `eu-central-1` | TIFF mit GCPs | anonym gemessen (`adr/0018` §3.1 [M]); die Metadaten sagen weiter Requester Pays |
| Copernicus DEM GLO-30/90 | `copernicus-dem-30m`/`-90m` | `eu-central-1` | COG | anonym |
| Sentinel-3 (MEEO) | `meeo-s3`, `meeo-s3-cog` | `eu-central-1` | Original, COG | „No AWS account required“ |
| Sentinel-5P L2 (MEEO) | `meeo-s5p` | `eu-central-1` | NetCDF, COG | „No AWS account required“ |
| ESA WorldCover | `esa-worldcover` | `eu-central-1` | COG | anonym |
| Landsat C2 L2 | `usgs-landsat` | `us-west-2` | COG | **Requester Pays** (Konto) |
| S1 RTC (Indigo) | `sentinel-s1-rtc-indigo` | `us-west-2` | COG | nur USA, „updates are paused“ |

**Weitere Befunde:**

- Ein Sentinel-2-COG-Spiegel in einer EU-Region ist nicht gefunden. Eine Ankündigung von Element 84 dazu auch nicht [P\*][S].
- Earth Search v1 hat 9 Collections, Query-, Sort-, Fields- und Aggregation-Extension; CQL2 ist nicht gelistet [P\*]. Die Betriebszusage lautet „does not come with any guaranteed service … best effort“ (README) [P\*]. Ratenlimits: keine erkennbar (`adr/0005` §3.6 [M]).
- **Preise [P\*]** aus den AWS-Preislisten, Stand 15.10. bzw. 16.09.2026:
  - S3 Standard: 0,023 USD/GB-Monat (`us-west-2`), 0,0245 (`eu-central-1`), 0,02695 (`eu-central-2` Zürich).
  - Internet-Egress: 100 GB/Monat frei, danach 0,09 USD/GB.
  - Transfer `us-west-2` → Frankfurt oder Zürich: 0,02 USD/GB.
  - EKS: 0,10 USD je Cluster-Stunde (Zürich [P\*], sonst [S]).
  - EC2 m7i.xlarge (4 vCPU, 16 GiB) nur **S**: 0,20 (`us-west-2`), 0,24 (`eu-central-1`), 0,27 USD/h (`eu-central-2`).
- **Wer zahlt den Transfer aus einem offenen Bucket ohne Requester Pays:** nicht belegt. Wahrscheinlich der Betreiber über das Open-Data-Programm, und der Empfang ist bei allen Anbietern frei [A].
- **Datenschutz [S]:** Für die Schweiz gibt es einen AWS DPA mit Swiss Addendum. Rechnen in `us-west-2` mit Konten und AOIs ist ein Drittlandtransfer. Der Stand des EU-US Data Privacy Framework am 30.10.2026 ist offen: Berufung C-703/25 P, Ausgang nicht verifiziert.

### 4.2 Copernicus Data Space Ecosystem mit CloudFerro bzw. Open Telekom Cloud — B

Gelesen aus `eu-cdse/documentation` [P\*], dazu `dataspace.copernicus.eu`.

**Abdeckung [P\*]:**

- S1 GRD ab 2014. Davon eine COG-Fassung „GRD COG_SAFE“ per `gdal_translate`, Vollständigkeit nicht dokumentiert.
- S1 RTC (CARD-BS) nur auf Anfrage über die On-Demand-Production-API, „limited pool of resources“.
- S2 L1C/L2A global ab 2015, als Kachel-Produkte. COG gibt es nur für Mosaike. SAFE/JP2 als Format ist Vorwissen [A].
- Sentinel-3 und Sentinel-5P sind vorhanden, Sentinel-6 auch.
- Landsat 8: „Full product download is not available to general users“.
- COP-DEM als STAC-Collection; Format offen.
- CLMS mit rund 60 Produkten; das Onboarding läuft „until the end of 2026“.
- **Inhaltlich die breiteste Quelle.**

**Metadaten [P\*]:** STAC 1.1.0 unter `stac.dataspace.copernicus.eu/v1`, CQL2, Queryables, **anonym durchsuchbar**. Die Form der `href` (https oder s3) ist offen. OData ist anonym durchsuchbar.

**Zugang [P\*]:**

- Download nur „authorized users“: Token mit 10 min Gültigkeit oder S3-Schlüssel.
- Kontingent je Konto (`Quotas.qmd`):
  - 12 TB je 30 Tage;
  - 20 MB/s je Verbindung;
  - **4 gleichzeitige Verbindungen**;
  - S3 2000 Anfragen/min;
  - **direkter HTTP-Zugriff auf COGs 50 000 Anfragen/Monat**;
  - danach 1 MB/s und 1 Verbindung.
- FAQ: öffentliche Anwendungen „will have to implement your own authentication service“.
- Bedingungen §9: keine Mehrfachkonten, um Limits zu umgehen.
- Höhere Kontingente gibt es „under commercial terms“, ohne Zahlen.

**Rechnung für eine Plattform mit einem Konto [A]:**

- Eine kalte Kachel braucht rund 32 Anfragen, eine kalte Ansicht 84–136 (§3).
- 50 000 COG-Anfragen reichen für rund 1 500 kalte Kacheln im Monat. 4 Verbindungen gelten für alle Nutzer zusammen.
- Ob in CloudFerro-VMs ein anderes Kontingent gilt (früher `/eodata` gemountet), ist **offen** [S].

**Rechenort:**

- Das EODATA-Archiv liegt „in Warsaw/Poland“ (FAQ) [P\*].
- CloudFerro nach Selbstauskunft auf der CDSE-Seite: nur EU-Rechenzentren, ISO 27001, managed Kubernetes, „no egress fee“, 250 Startguthaben [P\*].
- Regionen WAW3-1/WAW3-2/WAW4-1 (Polen) und FRA1-2 (Frankfurt) [S].
- Open Telekom Cloud: Regionen EU-DE und EU-NL, CCE (Kubernetes), C5 [S].
- Ein Schweizer Standort ist für keinen der beiden belegt.

**Betrieb:**

- 11.02.2025 Störung von EODATA [P\*].
- 2026 nur Suchtreffer [S]: Brand in einem Rechenzentrum in den Niederlanden am 07.05.2026; Forum-Titel „STAC Catalogue Missing Sentinel-2 L2A Data since 2026-06-11“.
- SLA und Statusseite: nicht gefunden.

**Bedingungen:**

- Kommerzielle Dienste darauf sind erlaubt („similar to the Copernicus Open Licence“, FAQ) [P\*].
- Für die Sentinel-Daten gilt die Legal Notice, von Otto geprüft (Log 2026-09-18; B11-Stufe Processing).

### 4.3 Microsoft Planetary Computer mit Azure West Europe — C

**Abdeckung [P\*][S]:**

- S1 GRD, S1 RTC, S2 L2A (COG, global ab 2016), Landsat C2, Sentinel-3, Sentinel-5P, Copernicus DEM und WorldCover.
- S2 L1C und CLMS nicht gefunden.

**Ort [P\*]:** „The Planetary Computer stores its data in Azure Blob Storage in the West Europe region“.

**Zugang [P\*]:**

- Ein SAS-Token je Container, anonym erhältlich.
- Limits „should be generous“, aber ohne Zahlen. 2026 gemeldet: `429` nach 10–12 Token-Anfragen (#506), `429` mit `Retry-After` (#511).
- Aus West Europe gilt „most un-throttled access“.
- Betreiberschlüssel: „No.“ (Maintainer, 20.10.2026, #511).
- CORS der Token-API: offen (`adr/0018` §11 C).

**Bedingungen [P\*]:** „Supplemental Terms of Use for Microsoft Planetary Computer Previews“ (Januar 2023):

- „solely for evaluation and testing“;
- „may change or discontinue Previews“;
- „Tokens may not be sublicensed to, distributed to, or shared with third parties“ und „Tokens may not be monetized“.

Ob diese Sätze für anonyme Daten-Tokens gelten, ist offen.

**Betrieb 2026 [P\*]** (GitHub-Issues):

- April: Sentinel-2 rund 10 Tage, Landsat 18 Tage im Rückstand (#475).
- Suche ab Mai mit vielen Timeouts (#476, #498).
- Sentinel-1 RTC ohne Aktualisierung seit 25.06.2026 (#489).
- Sentinel-2 seit 17.04.2026 ohne `nodata=0` (#513).
- Sentinel-2 L2A: Issue #516 „Data quality alert: Sentinel-2 Level-2A data conversion issue - 10/27/2026 21:00 UTC“, eröffnet am 29.10.2026, offen, am 30.10.2026 ohne Kommentare [P\*]. Wortlaut: „pixel values were incorrectly converted through uint8“; Bilder „published since approximately 21:00 UTC on October 27“ seien „potentially affected until the scope is confirmed“ und bräuchten „reprocessing“. Die Ursache nennt der Text „October 27 update to our processing pipeline“. Das klingt nach dem Betreiber; ob der Autor zu Microsoft gehört, zeigt die Seite nicht. Umfang und Behebung: offen.
- Antworten der Maintainer: selten.

**Rechenort [S]:**

- AKS: Free 0 USD, Standard 0,10 USD je Cluster-Stunde.
- Egress: 100 GB/Monat frei.
- West Europe ↔ Switzerland North: 17–22 ms.
- VM-Preise: nicht belastbar gefunden.
- Die EU Data Boundary umfasst die EFTA.

### 4.4 EOPF Sentinel Zarr Samples (ESA, EODC Wien)

- STAC `stac.core.eopf.eodc.eu`: anonym, 15 Collections (S1 GRD/SLC/OCN, S2 L1C/L2A, S3 OLCI/SLSTR) [P\*].
- Assets liegen auf `data.eodc.eu` als Zarr v3. `zarr.json` ist ohne Zugangsdaten lesbar [P\*].
- `sentinel-2-l2a-zarr3` hat neue Szenen nach rund 2,5 h [P\*].
- Die Collection `sentinel-2-l2a` meldet ein Zeitintervall ab 2017. Ob die Items wirklich dort liegen, ist nicht geprüft [P\*]. `adr/0017` §3.1 hatte am 25.10.2026 drei Monate gemessen.
- Status weiter „staging“, ausdrücklich kein Rechendienst. Betriebsstart laut FAQ „late 2026 or early 2027“ (`adr/0017` §3.1) [P][S].
- Erfüllt K1, K3 und K5. Für K7 noch nicht.

### 4.5 Weitere geprüfte Kandidaten — ausgeschieden

- **CODE-DE, WEkEO, Terrascope:** Konto nötig bzw. ungeklärt; Rechnen nur auf Antrag oder mit Kontingent [S].
- **Google Cloud** `gcp-public-data-sentinel-2`: EU-Multiregion, JP2 L1C, ohne STAC [S].
- **Source Cooperative:** liegt in `us-west-2` [S].
- **Swiss Data Cube:** Produkte auf Zenodo, kein Rechenangebot [S].
- **Schweizer Rechenorte** (Exoscale, Infomaniak, Azure Switzerland North, AWS Zürich, Google `europe-west6`): Preise nur **S**. Keiner liegt neben einer der Quellen. Sie sind nur für U interessant (Nutzer in CH) und für eine mögliche Pflicht, Daten in der Schweiz zu halten.

### 4.6 Netzentfernungen [S]

| Strecke | RTT | Quelle |
|---|---|---|
| Zürich ↔ Frankfurt (AWS) | ~10 ms | economize.cloud |
| Frankfurt ↔ Amsterdam | ~6 ms | hatsnet.io |
| Azure West Europe ↔ Switzerland North | 17–22 ms | azurespeed (Microsoft-Tabelle) |
| `us-west-2` ↔ `eu-central-1` | ~144–147 ms | economize.cloud |
| Zürich ↔ Wien, Zürich ↔ Warschau | nicht gefunden; geschätzt 15–40 ms [A] | — |

Frankfurt liegt damit zu allen EU-Beständen (AWS Frankfurt, EODC Wien, CDSE Warschau, Azure Amsterdam) in einem Bereich, den §3 als „EU-Nachbar“ oder besser modelliert. Belegen muss das die Messung.

---

## 5. Vergleich

| | A: AWS `us-west-2` | B: CDSE + CloudFerro/OTC | C: Planetary Computer + Azure WE | D: Rechnen in Frankfurt, Föderation |
|---|---|---|---|---|
| K1 ohne Konto | ✓ für S2 COG; Landsat ✗ (Requester Pays) | ✗ Download nur mit Konto | ~ anonymer Token; Bedingungen gegen Weitergabe | ✓ für alle heutigen Quellen |
| K2 Abdeckung | S2, Landsat, DEM (über Earth Search) | **am breitesten** (S1–S6, Landsat-Katalog, DEM, CLMS) | breit; ohne S2 L1C, CLMS | wie die angebundenen Quellen; EU-Bestände in AWS Frankfurt, EODC, CDSE-Katalog |
| K3 Format, STAC | COG, STAC ohne CQL2 | S2 als SAFE/JP2; STAC 1.1 mit CQL2 | COG; STAC | COG (AWS), Zarr (EOPF) |
| K4 Q (Modell) | S2 0,7 s; EU-Bestände ~3,6 s | ~0,7 s für alles im Archiv, wenn das Kontingent reicht | ~0,7 s für alles | EU-Bestände ~0,7–1,1 s; S2 bis EOPF ~3,6 s |
| K4 U (Zürich) | ~150 ms je Anfrage | ~15–40 ms | ~20 ms | ~10 ms |
| K5 EU/CH | ✗ Drittland für Konten und AOIs | ✓ EU (kein CH-Standort belegt) | ✓ EU | ✓ EU (CH möglich, Zürich-Regionen) |
| K6 Kosten | EC2 am billigsten [S] | Preise nicht öffentlich belegt; „no egress fee“ | unklar [S] | EC2 ~20 % über Oregon [S]; Transfer aus Oregon zahlt vermutlich der Betreiber [A] |
| K7 Betrieb | best effort | Kontingent je Konto, Störungen | Preview, Fehler 2026 | wie die Quellen; kein einzelner Engpass |
| K8 Bindung | an AWS-Region | an Konto und Kontingent | an Token und Bedingungen | gering: portable Bausteine, Quellen unabhängig |
| K9 Machbarkeit | einfach | Konto- und Token-Logik nötig | Token-Logik nötig | einfach |

---

## 6. Optionen und Empfehlung

### Option 1 — Rechnen in Frankfurt, Föderation, EU-Quellen bevorzugen (empfohlen)

**Was:**

- Rechenort in einer EU-Region im Raum Frankfurt. Welcher Anbieter, entscheidet M6 nach Messung und Kriterien (`projektuebersicht.md` §16).
- Keine exklusive Hauptquelle.
- Die Lage der Daten wird ein Feld der Registry (`data_region`) und in M5 ein Kriterium der Quellenauswahl: EU vor Übersee bei gleichem Inhalt.
- Sentinel-2: Earth Search bleibt, bis EOPF-Zarr operativ ist. Dann wird EOPF Vorgabe (Wiedervorlage `adr/0017`, F5).
- Den Rest von Q fängt der Cache: warme Kacheln 0,16 s, CDN mit M6.

**Für:** K1, K5, K8, K9 ohne Regeländerung. Nach §3 der größte Teil des Gewinns.

**Gegen:** Sentinel-2 bleibt bis EOPF kalt bei rund 3,6 s (Modell). Ein zweiter Worker-Pool in Oregon (`architekturplan.md` 12.2) wäre die Ausweichstufe, falls die Messung das verlangt.

### Option 2 — CDSE als Hauptquelle, Rechnen bei CloudFerro (B)

**Was:** Ein Betreiberkonto (S3-Schlüssel als Secret); Lesen aus EODATA; Rechnen in WAW3 oder FRA1-2.

**Voraussetzungen:**

- Regeländerung in `ENTSCHEIDUNGEN` §1 und Prinzip 2 (Konto statt anonym).
- Ein neuer Weg für Secrets in `gateway`.
- Ein JP2-Lesepfad für Sentinel-2.
- Eine schriftliche Klärung mit CDSE zu Betreiberkonto, Kontingent in CloudFerro-VMs und höheren Kontingenten (F4).

**Für:** die breiteste Abdeckung, EU, alles an einem Ort.

**Gegen:**

- Das Kontingent je Konto (4 Verbindungen, 50 000 COG-Anfragen) trägt nach §4.2 keinen Mehrnutzerbetrieb.
- Bindung an Konto und Kontingent; JP2 statt COG; der lokale Runner bräuchte ein Konto je Nutzer.

### Option 3 — Rechnen in AWS `us-west-2` (A)

**Für:** Sentinel-2 und Landsat schnell; günstigste VMs.

**Gegen:**

- Drittland für Konten und AOIs (K5).
- Die EU-Bestände (S1, DEM, S3, S5P) werden langsam.
- U für Nutzer in Europa rund 150 ms je Anfrage.
- Landsat braucht trotzdem ein Konto (Requester Pays).

Allenfalls als **reiner Worker-Pool ohne Personendaten** denkbar. Das ist Rechtsfrage und erst nach Messung ein Thema.

### Option 4 — Planetary Computer als Hauptquelle, Rechnen in Azure West Europe (C)

**Für:** breite Abdeckung, EU, Daten und Rechnen an einem Ort.

**Gegen:**

- Token-Logik im ganzen Lesepfad (Kachel, Job, Runner). `adr/0018` F4 erlaubt sie nur unter (a)–(d), und (d) steht gegen den Satz „Tokens may not be … shared with third parties“.
- Preview-Bedingungen, Fehler im Betrieb 2026, keine Betreiberschlüssel.

### Empfehlung

**Option 1.** Ottos Ziel, Rechnen und Rendern nah an den Daten, wird erreicht, weil fast alle Bestände schon in der EU liegen und EU-Nähe nach §3 den Großteil bringt. Der Preis ist die Wartezeit für Sentinel-2 bis EOPF.

- B und C bringen Abdeckung, aber jeweils eine Regeländerung und eine Bindung an Konto oder Token.
- A bringt Tempo nur für zwei Bestände und verletzt K5.

Die Messung (§8) kann die Empfehlung kippen. Das ist der Fall, wenn Frankfurt mit Earth Search für Sentinel-2 deutlich schlechter abschneidet als das Modell, oder wenn eine EU-Quelle real deutlich langsamer ist als 25 ms (Schwellen in §8.4).

---

## 7. Föderation, Registry und Folgen

### 7.1 Was „Hauptquelle“ heißt

**„Hauptquelle“ ist keine Systemrolle, sondern eine Auswahlregel [A].**

- Jeder Datensatz hat genau eine Quelle (wie heute, `adr/0017`).
- Für neue Datensätze wird in M5 die EU-Quelle bevorzugt, wenn sie K1 und K3 erfüllt.
- Adapter, `AdapterSpec` und `gateway` ändern sich dadurch nicht (`adr/0011`).

### 7.2 Registry

Neues Datenfeld `data_region`, zum Beispiel `aws:eu-central-1`, `aws:us-west-2` oder `eodc:vienna` [A]. Es ist eine Angabe am Datensatz, keine Logik je Datensatz. Ein Startcheck prüft es gegen `asset_hosts`, wo der Host die Region verrät (`*.s3.<region>.amazonaws.com`).

Nutzen:

1. Kriterium in M5.
2. Später Wahl des Worker-Pools (`architekturplan.md` 12.2), nur bei Bedarf.
3. Eingabe der Kostenschätzung (Transfer).
4. Anzeige in der Beschreibung des Datensatzes.

`architekturplan.md` §2 nennt `data_region` schon als Eigenschaft des Datensatzes; gebaut ist es nicht.

### 7.3 Health-Checks und Ausfall

- Unverändert je Quelle (M5). Fällt eine Quelle aus, sind nur ihre Datensätze betroffen.
- Mit einer einzigen Hauptquelle (Option 2 oder 4) hinge alles an einem Konto bzw. Token. Das ist ein weiteres Argument für Option 1.
- Ein automatischer Wechsel auf einen Spiegel (etwa EOPF ↔ Earth Search für Sentinel-2) ist **nicht** Teil dieses ADR. Item-IDs, Format und Prozessierung unterscheiden sich, und `adr/0017` hat bewusst einen Sentinel-2-Datensatz.

### 7.4 Bindung an einen Anbieter

Der Rechenort bleibt austauschbar: Container, Postgres, S3-API, Kubernetes oder compose (`architekturplan.md` 12.1). Die Quellen sind vom Rechenort unabhängig. Die Wahl in M6 ist damit reversibel, die Wahl von B oder C als Hauptquelle wäre es weniger.

### 7.5 Folgen für M5

- **Quellenauswahl:** `data_region` und K1 als Kriterien.
- **DS-04** (S1 GRD, `eu-central-1`) passt zu Option 1.
- **Kandidaten in der EU, anonym:**
  - Sentinel-3 und Sentinel-5P (MEEO, `eu-central-1`, auch COG);
  - WorldCover (`eu-central-1`, CC BY 4.0, B11-Einstufung durch Otto).
- **Landsat** über AWS bleibt durch Requester Pays ausgeschlossen (K1).
- **CLMS** gibt es über CDSE nur mit Konto, also höchstens als Katalogeintrag mit Link (B11).
- **CDSE-STAC** ist als Discovery-Quelle für Collections brauchbar: anonym, CQL2.

### 7.6 Folgen für M6

- **Shortlist Rechenort:** Anbieter mit Region im Raum Frankfurt und managed Kubernetes oder Containern:
  - AWS `eu-central-1`;
  - Azure Germany West Central oder West Europe;
  - Open Telekom Cloud EU-DE;
  - CloudFerro FRA1-2;
  - Exoscale und Google `europe-west3` nach Preisen.
- **Zürich-Regionen** nur, falls Daten in der Schweiz bleiben müssen (Rechtsfrage zu §4).
- **CDN vor dem `tiler`** fängt warme Kacheln für Nutzer weltweit.
- Die Messung Stufe 2 läuft vor dieser Wahl.

### 7.7 Punkt 46 (eigene Daten, Projekte) und Runner

- Der Objektspeicher je Projekt liegt in derselben Region wie der Rechenort. Uploads laufen über U.
- Lokale Dateien (Stufe 1 von Punkt 46) sind von der Datennähe nicht berührt.
- Der Runner liest von der IP des Nutzers (`architekturplan.md` 7.7). Für Nutzer in Europa gewinnt er mit EU-Quellen genauso. Mit B oder C bräuchte er Konto bzw. Token.

---

## 8. Messplan

### 8.1 Was gemessen wird

| Code | Größe | Weg | Wie |
|---|---|---|---|
| Q1 | erstes Byte, neue Verbindung (TCP + TLS + Antwort), 16 KiB | Q | Median aus 3 |
| Q2 | erstes Byte auf offener Verbindung | Q | Median aus 10 |
| Q3 | Durchsatz, 16 MiB am Stück | Q | 1 Lauf |
| Q4 | STAC-Suche, `limit=1` | Q | Median aus 5 |
| P1 | Mosaik-Kachel kalt (2–4 Szenen eines Überflugs, NDVI, z10, 512 px) | U+Q+R | nach Neustart des `tiler` und leerem Cache, 3 Läufe |
| P2 | dieselbe Kachel warm | U+R | Median aus 5 |
| P3 | Zuschnitt `red`+`nir`, 0,05° | U+Q+R | 1 Lauf, kalt |
| P4 | ein Job (`scripts/try-job.ps1`) | U+Q+R | Gesamtzeit des Skripts |

**Quellen:**

| Kürzel | Quelle | Ort |
|---|---|---|
| ES-S2 | Earth Search S2 COG | `us-west-2` |
| ES-S1 | S1 GRD | `eu-central-1` |
| DEM | Copernicus DEM | `eu-central-1` |
| S2-JP2 | Sentinel-2 L2A JP2 (Messpunkt: anonym oder `403`?) | `eu-central-1` |
| EOPF | EOPF-Zarr | Wien |
| PC | Planetary Computer S2 L2A, anonymes Token nach `adr/0018` §11 C | West Europe |
| CDSE | CDSE, nur STAC (Q4) ohne Konto, Download nur nach F4 | Warschau |

**Regeln:**

- Ausgegeben werden nur Kürzel, Status, Millisekunden und MB/s. Nie URLs, Item-IDs, Tokens oder Koordinaten.
- Die Fläche ist die synthetische Fläche der Prüfskripte (7° O / 46° N, offenes Gelände, wie `scripts/checks/nm4-19-statistics.ps1`).
- Ergebnisse an Claude bzw. in den PR nur als Tabelle.

### 8.2 Stufe 1 — Ottos Rechner (kostenlos)

Windows PowerShell 5.1, aus dem Repo-Wurzelverzeichnis. Für P1–P4 läuft der Stack (`docker compose up -d --build`, README). **Nicht ausgeführt:** In der Sitzung gibt es kein PowerShell, und die Quellen sind gesperrt. Die Befehle folgen den Mustern aus `adr/0018` §11 und `scripts/checks/`.

**Vorbereitung:**

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
[Net.ServicePointManager]::DefaultConnectionLimit = 8
$ProgressPreference = 'SilentlyContinue'
$Box = '6.9,45.9,7.1,46.1'; $Period = '2025-07-01T00:00:00Z/2025-08-31T23:59:59Z'
function Get-Median($v) { $s = @($v | Where-Object { $null -ne $_ } | Sort-Object); if ($s.Count) { $s[[int][math]::Floor($s.Count / 2)] } }
function Measure-Range([string]$Url, [long]$From, [long]$To, [switch]$Cold) {   # gibt nie die URL aus
  try {
    $r = [Net.HttpWebRequest]::Create($Url); $r.AddRange($From, $To); $r.Timeout = 60000; $r.ReadWriteTimeout = 120000
    if ($Cold) { $r.ConnectionGroupName = [guid]::NewGuid().ToString() }          # erzwingt eine neue Verbindung
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $x = $r.GetResponse(); $ttfb = $sw.Elapsed.TotalMilliseconds
    $s = $x.GetResponseStream(); $buf = New-Object byte[] 262144; $n = 0
    while (($k = $s.Read($buf, 0, $buf.Length)) -gt 0) { $n += $k }
    $all = $sw.Elapsed.TotalMilliseconds; $code = [int]$x.StatusCode; $x.Close()
    [pscustomobject]@{ Status = $code; Ttfb = [math]::Round($ttfb); Ms = [math]::Round($all); MB = $n / 1MB }
  } catch { [pscustomobject]@{ Status = "Fehler $([int]$_.Exception.InnerException.Response.StatusCode)"; Ttfb = $null; Ms = $null; MB = 0 } }
}
function Test-Source([string]$Name, [string]$Url) {
  $cold = @(1..3 | ForEach-Object { Measure-Range $Url 0 16383 -Cold })
  $warm = @(1..10 | ForEach-Object { Measure-Range $Url 16384 32767 })
  $bulk = Measure-Range $Url 0 16777215
  [pscustomobject]@{ Quelle = $Name; Status = $cold[0].Status; Q1_ms = Get-Median ($cold | ForEach-Object Ttfb)
    Q2_ms = Get-Median ($warm | ForEach-Object Ttfb); Q3_MBs = $(if ($bulk.Ms) { [math]::Round($bulk.MB / ($bulk.Ms / 1000), 1) }) }
}
function Test-Search([string]$Name, [string]$Url) {
  $ms = @(1..5 | ForEach-Object { (Measure-Command { Invoke-RestMethod $Url | Out-Null }).TotalMilliseconds })
  [pscustomobject]@{ Quelle = $Name; Q4_ms = [math]::Round((Get-Median $ms)) }
}
```

**A. Quellen direkt (Q1–Q4):**

```powershell
$es = 'https://earth-search.aws.element84.com/v1'
$i2 = (Invoke-RestMethod "$es/search?collections=sentinel-2-c1-l2a&bbox=$Box&datetime=$Period&limit=1").features[0]
$i1 = (Invoke-RestMethod "$es/search?collections=sentinel-1-grd&bbox=$Box&datetime=$Period&limit=1").features[0]
$ij = (Invoke-RestMethod "$es/search?collections=sentinel-2-l2a&bbox=$Box&datetime=$Period&limit=1").features[0]
$s1 = ($i1.assets.vv.href -replace '^s3://sentinel-s1-l1c/', 'https://sentinel-s1-l1c.s3.eu-central-1.amazonaws.com/')
$jp = ($ij.assets.'red-jp2'.href -replace '^s3://sentinel-s2-l2a/', 'https://sentinel-s2-l2a.s3.eu-central-1.amazonaws.com/')
$dem = 'https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N46_00_E007_00_DEM/Copernicus_DSM_COG_10_N46_00_E007_00_DEM.tif'
$eo = (Invoke-RestMethod "https://stac.core.eopf.eodc.eu/search?collections=sentinel-2-l2a-zarr3&bbox=$Box&limit=1").features[0]
$ez = @($eo.assets.PSObject.Properties | Where-Object { $_.Value.type -like '*zip*' })[0].Value.href
$pc = 'https://planetarycomputer.microsoft.com'
$t = Invoke-RestMethod "$pc/api/sas/v1/token/sentinel-2-l2a"                  # Token nie ausgeben
$ip = (Invoke-RestMethod "$pc/api/stac/v1/search?collections=sentinel-2-l2a&bbox=$Box&datetime=$Period&limit=1").features[0]
@(
  Test-Source 'ES-S2 (us-west-2)'      $i2.assets.red.href
  Test-Source 'ES-S1 (eu-central-1)'   $s1
  Test-Source 'DEM (eu-central-1)'     $dem
  Test-Source 'S2-JP2 (eu-central-1)'  $jp
  Test-Source 'EOPF (Wien)'            $ez
  Test-Source 'PC (West Europe)'       ($ip.assets.B04.href + '?' + $t.token)
) | Format-Table -AutoSize
@(
  Test-Search 'Earth Search' "$es/search?collections=sentinel-2-c1-l2a&bbox=$Box&limit=1"
  Test-Search 'EOPF'         "https://stac.core.eopf.eodc.eu/search?collections=sentinel-2-l2a-zarr3&bbox=$Box&limit=1"
  Test-Search 'PC'           "$pc/api/stac/v1/search?collections=sentinel-2-l2a&bbox=$Box&limit=1"
  Test-Search 'CDSE'         "https://stac.dataspace.copernicus.eu/v1/search?collections=sentinel-2-l2a&bbox=$Box&limit=1"
) | Format-Table -AutoSize
Remove-Variable t
```

Erwartet:

- `206` überall, nur bei S2-JP2 `206` oder `403` (Requester Pays).
- Q1 nach Oregon um 400–600 ms, in die EU unter 150 ms; Q2 grob die halbe Q1.
- Liefert eine Zeile einen Fehler, bleiben die anderen gültig. Dann den Fehlercode notieren.

**B. Plattform lokal (P1–P4):** Stack läuft; Earth Search ohne VPN erreichbar.

```powershell
$Api = 'http://localhost:8000'; $Tiler = 'http://localhost:8001'; $Ds = 'sentinel-2-c1-l2a'
function Get-Tile([double]$Lon, [double]$Lat, [int]$Z) {
  $n = [math]::Pow(2, $Z); $r = $Lat * [math]::PI / 180
  "$Z/$([math]::Floor(($Lon + 180) / 360 * $n))/$([math]::Floor((1 - [math]::Log([math]::Tan($r) + 1 / [math]::Cos($r)) / [math]::PI) / 2 * $n))"
}
function Reset-Cold {   # nur lokal; auf einer VM denselben Befehl in der SSH-Sitzung (Stufe 2)
  docker compose restart tiler | Out-Null
  docker compose exec -T postgres sh -c 'psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "delete from earthx_search_cache; delete from earthx_stats_cache"' | Out-Null
  foreach ($k in 1..60) { try { Invoke-WebRequest "$Tiler/health" -UseBasicParsing | Out-Null; return } catch { Start-Sleep -Milliseconds 500 } }
}
function Time-Request([string]$Method, [string]$Url, [string]$Body) {
  $a = @{ Uri = $Url; Method = $Method; UseBasicParsing = $true; TimeoutSec = 600 }
  if ($Body) { $a.Body = $Body; $a.ContentType = 'application/json' }
  $sw = [Diagnostics.Stopwatch]::StartNew()
  try { $r = Invoke-WebRequest @a; $s = [int]$r.StatusCode }
  catch { $s = "Fehler $([int]$_.Exception.Response.StatusCode)" }
  [pscustomobject]@{ Status = $s; Ms = [math]::Round($sw.Elapsed.TotalMilliseconds) }
}
$search = '{"collections":["' + $Ds + '"],"bbox":[' + $Box + '],"datetime":"' + $Period + '","limit":100,"query":{"eo:cloud_cover":{"lte":20}}}'
$found = (Invoke-RestMethod -Method Post "$Api/stac/search" -Body $search -ContentType 'application/json').features
$pass = $found | Group-Object { ([string]$_.properties.datetime).Substring(0, 10) + '|' + $_.properties.'s2:datatake_id' } |
  Where-Object Count -ge 2 | Sort-Object Count -Descending | Select-Object -First 1
$ids = @($pass.Group | Select-Object -First 4 | ForEach-Object id | Sort-Object)
"Szenen im Ueberflug: $($ids.Count)"                                             # 2 bis 4
$params = [uri]::EscapeDataString('{"expression":"(nir-red)/(nir+red)"}')
$q = (($ids | ForEach-Object { "item=$_" }) -join '&') + "&asset=red&asset=nir&op=band_math&op_version=1&params=$params&rescale=-1,1&colormap_name=rdylgn&tilesize=512"
$TileUrl = "$Tiler/collections/$Ds/mosaic/tiles/WebMercatorQuad/$(Get-Tile 7.0 46.0 10).png?$q"
$ring = '[[6.975,45.975],[7.025,45.975],[7.025,46.025],[6.975,46.025],[6.975,45.975]]'
$crop = '{"groups":[["' + $ids[0] + '"]],"assets":["red","nir"],"aoi":{"type":"Polygon","coordinates":[' + $ring + ']},"resolution":1}'

$p1 = foreach ($k in 1..3) { Reset-Cold; Time-Request Get $TileUrl }
$p2 = foreach ($k in 1..5) { Time-Request Get $TileUrl }
Reset-Cold; $p3 = Time-Request Post "$Tiler/collections/$Ds/download" $crop
$p4 = (Measure-Command { .\scripts\try-job.ps1 | Out-Null }).TotalMilliseconds
[pscustomobject]@{ P1_kalt_ms = ($p1 | ForEach-Object Ms) -join ' / '; P1_Status = $p1[0].Status
  P2_warm_ms = Get-Median ($p2 | ForEach-Object Ms); P3_crop_ms = $p3.Ms; P3_Status = $p3.Status; P4_job_ms = [math]::Round($p4) }
```

Erwartet: P1 in der Größe von 6,0 s, P2 um 0,16 s (Messung vom 28.10.2026). P4 enthält auch den zweiten Auftrag (Cache-Treffer) und das Löschen.

### 8.3 Stufe 2 — Test-VMs in den Regionen (kostenpflichtig)

**Nur nach ausdrücklicher Freigabe durch Otto** (Otto, 30.10.2026). Die Antwort F2 = 1 legt den Umfang fest (R1 und R2 vor der Wahl in M6), gibt aber keine Kosten frei. Vor dem Start nennt eine Session Regionen, VM-Typ, Dauer und geschätzte Kosten und wartet auf Ottos Freigabe. Keine Session legt Konten, VMs oder kostenpflichtige Dienste selbst an.

**Regionen**, je eine VM mit 4 vCPU, 16 GB und Ubuntu LTS:

| | Region | Rolle |
|---|---|---|
| R1 | AWS `eu-central-1` (Frankfurt) | Kern der Empfehlung |
| R2 | AWS `us-west-2` (Oregon) | Gegenprobe für A |
| R3 | CloudFerro WAW3-2 oder FRA1-2 | Startguthaben; nur sinnvoll mit F4 = 1 |
| R4 | Azure West Europe | nur falls F6 C offen hält |

**Kosten [A]:**

- Rund 3 h je VM.
- Mit den Preisen aus §4.1 [S] etwa 1 USD je AWS-VM, dazu Speicher und Egress unter 1 USD.
- Gesamt grob unter 10 €.
- Konten und Zahlung legt Otto an. Keine Zugangsdaten ins Repo, in Logs oder in den PR.

**Ablauf je VM:**

1. Docker installieren, Repo klonen, `.env` aus `.env.example` (README), `docker compose up -d --build`. Keine Ports öffnen.
2. **Quellen von der VM (Q1–Q4)** mit `curl`. Ausgabe nur Kürzel und Zahlen:

```bash
set -u; box=6.9,45.9,7.1,46.1; per=2025-07-01T00:00:00Z/2025-08-31T23:59:59Z; es=https://earth-search.aws.element84.com/v1
probe() {   # $1 Kürzel, $2 Adresse (wird nie ausgegeben)
  cold=$(for i in 1 2 3; do curl -s -o /dev/null -r 0-16383 -w '%{time_starttransfer}\n' "$2"; done | sort -n | sed -n 2p)
  warm=$(curl -s -r 16384-32767 $(for i in $(seq 10); do printf -- '-o /dev/null %s ' "$2"; done) -w '%{time_starttransfer}\n' | tail -n 9 | sort -n | sed -n 5p)
  mbs=$(curl -s -o /dev/null -r 0-16777215 -w '%{speed_download}' "$2")
  awk -v n="$1" -v c="$cold" -v w="$warm" -v m="$mbs" 'BEGIN { printf "%-22s Q1=%4.0f ms Q2=%4.0f ms Q3=%6.1f MB/s\n", n, c*1000, w*1000, m/1048576 }'
}
s2=$(curl -s "$es/search?collections=sentinel-2-c1-l2a&bbox=$box&datetime=$per&limit=1" | jq -r '.features[0].assets.red.href')
s1=$(curl -s "$es/search?collections=sentinel-1-grd&bbox=$box&datetime=$per&limit=1" | jq -r '.features[0].assets.vv.href' | sed 's#^s3://sentinel-s1-l1c/#https://sentinel-s1-l1c.s3.eu-central-1.amazonaws.com/#')
probe 'ES-S2 (us-west-2)' "$s2"; probe 'ES-S1 (eu-central-1)' "$s1"
probe 'DEM (eu-central-1)' 'https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N46_00_E007_00_DEM/Copernicus_DSM_COG_10_N46_00_E007_00_DEM.tif'
ez=$(curl -s "https://stac.core.eopf.eodc.eu/search?collections=sentinel-2-l2a-zarr3&bbox=$box&limit=1" | jq -r '[.features[0].assets[] | select(.type // "" | test("zip"))][0].href')
probe 'EOPF (Wien)' "$ez"
tok=$(curl -s https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-2-l2a | jq -r .token)
b04=$(curl -s "https://planetarycomputer.microsoft.com/api/stac/v1/search?collections=sentinel-2-l2a&bbox=$box&datetime=$per&limit=1" | jq -r '.features[0].assets.B04.href')
probe 'PC (West Europe)' "$b04?$tok"; unset tok
for u in "$es/search?collections=sentinel-2-c1-l2a&bbox=$box&limit=1" "https://stac.dataspace.copernicus.eu/v1/search?collections=sentinel-2-l2a&bbox=$box&limit=1"; do
  for i in 1 2 3 4 5; do curl -s -o /dev/null -w '%{time_total}\n' "$u"; done | sort -n | sed -n 3p | awk '{ printf "Q4 %.0f ms\n", $1*1000 }'
done
```

3. **Plattform auf der VM, Sicht des Servers (P1 und P2 ohne U):** Block B aus §8.2 lässt sich nicht direkt übernehmen. Deshalb fragt Otto die Adresse `$TileUrl` von seinem Rechner aus über den Tunnel (Schritt 4). In der SSH-Sitzung auf der VM misst er zusätzlich mit `curl -s -o /dev/null -w '%{time_total}\n' '<TileUrl mit localhost:8001>'`. Die Adresse kopiert er aus PowerShell (`$TileUrl`) über die Zwischenablage; sie kommt in keinen Text.

   Vor jedem kalten Lauf in der SSH-Sitzung:

```bash
cd earthX && docker compose restart tiler && docker compose exec -T postgres sh -c 'psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "delete from earthx_search_cache; delete from earthx_stats_cache"'
```

4. **Sicht des Nutzers (P1–P3 mit U):** Tunnel von Ottos Rechner, ohne offene Ports:

```powershell
ssh -N -L 8000:localhost:8000 -L 8001:localhost:8001 <Nutzer>@<VM>    # eigenes Fenster; lokaler Stack vorher stoppen
```

   Dann Block B aus §8.2 im zweiten Fenster. `Reset-Cold` dabei weglassen und stattdessen den Befehl aus Schritt 3 auf der VM ausführen. P4 entfällt, weil `try-job.ps1` lokale Logs liest.

5. VM und Speicher löschen, Kosten notieren.

### 8.4 Auswertung und Schwellen

Ergebnis je Ort als eine Tabelle mit Q1–Q4 je Quelle und P1–P4.

Die Empfehlung (Option 1) gilt, wenn alle drei Punkte zutreffen:

- **S1** R1 (Frankfurt): P1 serverseitig für Sentinel-2 (Oregon) ≤ 4 s (Modell 3,6 s).
- **S2** R1: Q1 zu ES-S1, DEM und EOPF ≤ 60 ms (Modell „EU-Nachbar“: 60 ms je neue Verbindung).
- **S3** R2 (Oregon): P1 aus Nutzersicht bei Otto **nicht** schneller als R1 aus Nutzersicht.

Sie kippt, wenn

- R1 bei P1 für Sentinel-2 über 6 s liegt (dann Worker-Pool in Oregon für Sentinel-2 oder S2 aus JP2 in Frankfurt prüfen), oder
- eine EU-Quelle bei Q2 über 100 ms liegt (Anbieter dieser Quelle als Rechenort prüfen).

Stufe 1 allein beantwortet: wie weit Ottos Anschluss von jeder Quelle entfernt ist, ob S2-JP2 anonym ist und wie stark die Leitung bei P1 zählt (Q3 gegen §3, Zeile 100 Mbit/s).

---

## 9. Fragen an Otto — beantwortet am 2026-10-30

**Antworten (Otto, 30.10.2026):** F1 = 1, F2 = 1, F3 = 1, F4 = 2, F5 = 1, F6 = 1, F7 = 1, jeweils wie empfohlen. Die Rechtsfrage zur Datenhaltung in der Schweiz (F7) bleibt bis M6 offen. Stufe 2 der Messung nur nach ausdrücklicher Freigabe durch Otto (§8.3).

**F1 — Grundsatz Rechenort und Hauptquelle?**
1. Rechnen in der EU im Raum Frankfurt, Föderation ohne exklusive Hauptquelle, EU-Quellen bevorzugen (Option 1) **(Empfehlung)**
2. CDSE als Hauptquelle mit Betreiberkonto, Rechnen bei CloudFerro (Option 2, Regeländerung §1)
3. AWS `us-west-2` (Option 3, Ausnahme von EU/CH)
4. Planetary Computer + Azure West Europe (Option 4)

**F2 — Messung?**
1. Stufe 1 jetzt (Ottos Rechner, kostenlos); Stufe 2 mit R1 und R2 vor der Wahl in M6, Kosten grob unter 10 € **(Empfehlung)**
2. Nur Stufe 1; Stufe 2 erst in M6
3. Stufe 1 und 2 sofort, alle vier Regionen

**F3 — `data_region` in der Registry?**
1. Ja, als Datenfeld mit Startcheck gegen `asset_hosts`, eingeführt mit der YAML-Registry in M5 (B13) **(Empfehlung)**
2. Erst mit einem zweiten Worker-Pool
3. Nein

**F4 — CDSE?**
1. Otto legt privat ein kostenloses Konto an, misst S3 auf R3 (Schlüssel nur als Umgebungsvariable, nie im Repo) und fragt CDSE schriftlich: Betreiberkonto für eine Plattform erlaubt? Kontingent in CloudFerro-VMs? Höhere Kontingente? Nur sinnvoll bei F1 = 2.
2. CDSE nur als Katalog- und Discovery-Quelle (anonymes STAC), Daten nicht lesen **(Empfehlung)**

**F5 — Sentinel-2 in der EU?**
1. Wiedervorlage EOPF-Zarr aus `adr/0017` behalten. Sobald EOPF operativ ist, wird es die Quelle für Sentinel-2; bis dahin Earth Search mit Cache. Stufe 1 prüft, ob die Collection `sentinel-2-l2a` von EOPF jetzt ein volles Archiv hat **(Empfehlung)**
2. Zusätzlich Sentinel-2 aus JP2 in `eu-central-1` lesen lassen (eigener Lesepfad, JP2 ist nicht cloud-optimiert; erst nach Messung S2-JP2)
3. Sentinel-2 bleibt bei Earth Search, ohne Wiedervorlage

**F6 — Planetary Computer?**
1. Keine Hauptquelle. Er bleibt auf Teil B von `adr/0018` (S1 RTC nach Ottos Messung) beschränkt; die Bedingung (d) dort prüft den Satz „Tokens may not be … shared with third parties“ **(Empfehlung)**
2. Weiter als Hauptquelle prüfen (dann R4 in Stufe 2)

**F7 — Datenhaltung in der Schweiz?**
1. EU reicht für Konten und AOIs (DSGVO, revDSG über Angemessenheit); Zürich-Regionen nur, wenn ein Kunde es verlangt **(Empfehlung, Rechtsfrage offen)**
2. Konten und AOIs müssen in der Schweiz bleiben; dann Rechenort Zürich, Quellen in der EU (U schnell, Q wie §3 „EU-Nachbar“)

---

## 10. Was offen bleibt

- **Messung:** Stufe 1 durch Otto; Stufe 2 erst nach seiner ausdrücklichen Freigabe (§8.3). Die Zahlen in §3 sind ein Modell.
- **CDSE:**
  - Form der `href` im STAC;
  - Filter nach Orbit, Polarisation und MGRS;
  - Format des DEM;
  - Kontingent in CloudFerro-VMs;
  - Preise und AVV von CloudFerro und OTC.
- **AWS:**
  - wer den Transfer aus offenen Buckets zahlt;
  - ob `sentinel-s2-l2a` anonym ist (Widerspruch Registry ↔ Vorwissen);
  - EC2-Preise aus der Preisliste selbst;
  - Ratenlimit und Bedingungen von Earth Search.
- **Planetary Computer:**
  - ob die Preview-Bedingungen für anonyme Daten-Tokens gelten;
  - CORS der Token-API (`adr/0018` §11 C).
- **EOPF:** ob das Archiv seit 2017 tatsächlich gefüllt ist; Termin des Betriebs.
- **DPF:** Ausgang der Berufung C-703/25 P (nur relevant für Option 3).
- **Netzentfernungen:** Zürich ↔ Wien und Zürich ↔ Warschau.
- **Datenhaltung in der Schweiz** (F7): Rechtsfrage, offen bis M6.
- **Folgeänderungen aus Option 1** (angenommen; mit der nächsten Doku-Aufgabe oder durch Otto):
  - `architekturplan.md` 12.2 (Frankfurt statt „Clouds, in denen die Copernicus-Daten liegen“);
  - `projektuebersicht.md` §16 (Cloud-Provider: Kriterium Region, Shortlist §7.6);
  - Plan für M5 (Kriterium `data_region`).

---

## 11. Quellen

Abgerufen am 30.10.2026. Belegstufe in Klammern.

**AWS / Earth Search:**

- Registry (P\*):
  - https://registry.opendata.aws/sentinel-2-l2a-cogs/
  - https://registry.opendata.aws/sentinel-2/
  - https://registry.opendata.aws/sentinel-1/
  - https://registry.opendata.aws/usgs-landsat/
  - https://registry.opendata.aws/copernicus-dem/
  - https://registry.opendata.aws/sentinel-3/
  - https://registry.opendata.aws/sentinel5p/
  - https://registry.opendata.aws/esa-worldcover-vito/
  - https://registry.opendata.aws/sentinel-1-rtc-indigo/
- Earth Search (P\*):
  - https://earth-search.aws.element84.com/v1/ (Landing Page, `/collections`, `/queryables`, `/search`)
  - https://github.com/Element84/earth-search (README: „best effort“)
  - https://github.com/Element84/earth-search/issues/31
- Preislisten (P\*): https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/ (AmazonS3, AWSDataTransfer, AmazonEKS; Stände 16.09.–27.10.2026)
- Nur S:
  - EC2 m7i.xlarge: https://www.doit.com/compute/spot/us-west-2/m7i.xlarge und https://www.devzero.io/instances/aws/m7i.xlarge
  - revDSG: https://aws.amazon.com/blogs/alps/using-aws-in-light-of-the-new-swiss-data-protection-act/
  - DPF: https://www.wilmerhale.com/en/insights/blogs/wilmerhale-privacy-and-cybersecurity-law/20251201-european-court-of-justice-to-review-challenge-to-eu-us-data-privacy-framework
  - Latenz: https://www.economize.cloud/resources/aws/latency/us-west-2-vs-eu-central-1/ und https://www.economize.cloud/resources/aws/latency/eu-central-2-vs-eu-central-1/

**CDSE, CloudFerro, Open Telekom Cloud:**

- Doku-Quelltext (P\*), Repo https://raw.githubusercontent.com/eu-cdse/documentation/publish/:
  - Kontingente: `Quotas.qmd`
  - Schnittstellen: `APIs/STAC.qmd`, `APIs/S3.qmd`, `APIs/OData.qmd`, `APIs/Token.qmd`, `APIs/On-Demand%20Production%20API.qmd`
  - Allgemein: `FAQ.qmd`, `Data/collections.json`
  - Missionen: `Data/SentinelMissions/Sentinel1.qmd`, `Data/SentinelMissions/Sentinel2.qmd`, `Data/Others/Sentinel1_COG.qmd`
  - Weitere Daten: `Data/ComplementaryData/Landsat8.qmd`, `Data/CopernicusServices/CLMS.qmd`
- Bedingungen und Kontingente (P\*):
  - https://dataspace.copernicus.eu/terms-and-conditions
  - https://dataspace.copernicus.eu/node/1454 (12 TB)
  - https://dataspace.copernicus.eu/node/2298 (STAC anonym)
  - https://dataspace.copernicus.eu/node/1777 und /node/3068 (openEO)
- CloudFerro, Selbstauskunft (P\*): https://dataspace.copernicus.eu/node/2820
- Störung (P\*): https://sentinels.copernicus.eu/-/cdse-eodata-access-issue
- Nur S:
  - https://creodias.docs.cloudferro.com/en/latest/eodata/How-to-get-credentials-used-for-accessing-EODATA-on-a-cloud-VM-on-Creodias.html
  - https://www.open-telekom-cloud.com/en/products-services/cloud-container-engine
  - https://forum.dataspace.copernicus.eu/t/stac-catalogue-missing-sentinel-2-l2a-data-since-2026-06-11/5216

**Planetary Computer, Azure:**

- Doku und Bedingungen (P\*):
  - https://github.com/microsoft/PlanetaryComputerDataCatalog/blob/main/docs/concepts/sas.md
  - https://github.com/microsoft/PlanetaryComputerDataCatalog/blob/develop/src/pages/Terms.js
  - https://github.com/microsoft/AIforEarthDataSets/blob/main/storage-docs/sentinel-2-storage.md
  - https://raw.githubusercontent.com/microsoft/PlanetaryComputerExamples/main/quickstarts/using-the-data-api.ipynb
- Issues und Diskussionen (P\*), alle unter https://github.com/microsoft/PlanetaryComputer/:
  - Issues 476, 489, 498, 506, 511, 512, 513, 516
  - Discussions 475, 482, 508
- Nur S:
  - https://learn.microsoft.com/azure/aks/uptime-sla
  - https://azure.microsoft.com/en-gb/pricing/details/bandwidth/
  - https://www.azurespeed.com/Azure/RegionToRegionLatency/WestEurope
  - https://learn.microsoft.com/sk-sk/industry/sovereignty/eu-data-boundary

**EOPF und weitere:**

- EOPF (P\*):
  - https://stac.core.eopf.eodc.eu/ (dort `/collections/sentinel-2-l2a`, `/collections/sentinel-2-l2a-zarr3`, `/collections/sentinel-1-l1-grd`)
  - https://zarr.eopf.copernicus.eu/
- Nur S:
  - https://knowledgebase.code-de.org/en/latest/eodata/How-To-Create-S3-Credentials-on-CODE-DE.html
  - https://docs.terrascope.be/QuotasAndLimitations.html
  - https://cloud.google.com/storage/docs/public-datasets/sentinel-2?hl=de
  - https://docs.source.coop/infrastructure
  - https://hatsnet.io/docs/network/latency/pairs/fra-ams-rtt

**Im Repo (P):** `adr/0002`, `adr/0005` §3.6, `adr/0006` §8, `adr/0017` §3.1, `adr/0018` §3–§5, §11, `plans/querschnitt/nm4-26-kachel-leistung.md` §8, §17, `scripts/tile-bench/`.
