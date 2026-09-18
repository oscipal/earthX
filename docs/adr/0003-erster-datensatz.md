# ADR 0003 — Erster token-freier Datensatz

- **Status:** Vorschlag. Entscheidung liegt bei Otto.
- **Datum:** 2026-09-18
- **Aufgabe:** M0 Schritt 6 laut `ENTSCHEIDUNGEN_2026-09-18.md` §6.
- **Autonomiestufe:** C — nur recherchiert und berichtet. Kein Produktivcode
  geändert, keine Daten heruntergeladen.
- **Grundlage:** `ENTSCHEIDUNGEN_2026-09-18.md` §2, §3, §6;
  `KLAERUNGEN.md` B8, B9, B11, B12, B13; `docs/prototyp-inventar.md` F1–F21;
  Entscheidungslog-Zeile „Format-Hierarchie Zarr > COG > Altformate".
- **Betroffen:** `architekturplan.md` 6.2, 6.3, 13; `projektuebersicht.md` §5
  (Onboarding-Checkliste); Entscheidungslog.

> **ADR 0002 ist nicht vergeben.** Die Nummer bleibt für das angekündigte
> Coverage-Map-ADR reserviert (Entscheidungslog, Zeile „Technische Umsetzung der
> Coverage Map"). Dieses Dokument ist deshalb 0003.

---

## Methode und Grenzen — bitte zuerst lesen

**Der geforderte Erreichbarkeitstest aus der Cloud-Umgebung war nicht möglich.**
Die Netzwerk-Policy dieser Sitzung sperrt jeden ausgehenden Zugriff auf die
Kandidaten-Endpunkte. Zwei Wege, beide gesperrt:

| Weg | Ziel | Ergebnis |
|---|---|---|
| `curl` (HTTPS-Proxy) | `stac.core.eopf.eodc.eu`, `earth-search.aws.element84.com`, `planetarycomputer.microsoft.com` | `CONNECT tunnel failed, response 403` — `connect_rejected (organization policy)` |
| Seitenabruf des Agenten | dieselben Hosts, dazu `zarr.eopf.copernicus.eu`, `dataspace.copernicus.eu`, `registry.opendata.aws` | `EGRESS_BLOCKED` |

Es funktionierte **ausschließlich die Websuche**. Daraus folgt für dieses
Dokument eine Einschränkung, die bei jeder Aussage mitzulesen ist:

- Keine Aussage zu Lizenz, Zugang oder Laufzeit ist am **Primärdokument**
  geprüft. Alle Belege sind Suchtreffer samt Link; der Link ist die Quelle, an
  der Otto die Aussage nachlesen kann.
- Jede Zeile trägt eine Spalte **Beleg**: `S` = aus Suchtreffer, Link vorhanden,
  Primärdokument nicht gelesen. `P` = Plandokument im Repo. Ein `✓` für
  „Primärquelle gelesen" kommt in diesem Dokument nirgends vor.
- Nichts wurde ersetzt oder angenommen, wo der Beleg fehlt. Wo etwas offen ist,
  steht „unbelegt" statt einer Schätzung.

**Was fehlt, konkret benannt:** eine Egress-Freigabe für die Hosts
`stac.core.eopf.eodc.eu`, `objects.eodc.eu` bzw. `zarr.eodc.eu`,
`earth-search.aws.element84.com`, `*.s3.us-west-2.amazonaws.com`,
`copernicus-dem-30m.s3.amazonaws.com`. Ohne sie lassen sich weder die
Erreichbarkeit noch die tatsächlichen STAC-Antworten (Collections, Item-Zahl,
Asset-Struktur, `license`-Feld) prüfen. Die Frage dazu steht am Ende.

---

## 1. Kontext und Entscheidungsbedarf

Die fertige Plattform enthält nichts, was einen Token braucht
(`ENTSCHEIDUNGEN` §1). Der Prototyp hängt heute vollständig an BIOMASS über
MAAP. Gesucht ist der **erste token-freie Datensatz**, auf den die Funktionen
F1–F21 des Inventars übertragen werden — also der Datensatz, an dem der Umbau
tatsächlich stattfindet und an dem sich entscheidet, wie viel vom Prototyp
unverändert weiterläuft.

Die Entscheidung ist deshalb keine Katalogfrage, sondern die Wahl des
Migrationsträgers. Zwei Kriterien ziehen gegeneinander:

- Die **Format-Hierarchie** (Entscheidungslog, 13.08.2026) stellt Zarr über COG.
- Die **Übertragbarkeit** der Prototyp-Funktionen spricht für COG, weil F9, F10,
  F11 und F18 heute auf rasterio/rio-tiler/GDAL stehen.

Dieses ADR legt beide Wege nebeneinander.

## 2. Bewertungskriterien

Aus der Aufgabenstellung, ergänzt um `KLAERUNGEN.md` B11 (Lizenzstufen) und B12
(Onboarding-Pflichten):

1. **Zugang** ohne Token und ohne Registrierung
2. **Lizenz**, eingestuft nach B11 (Katalogeintrag / Anzeige / Processing)
3. **Format** nach Hierarchie und Vorhandensein einer STAC-API
4. **Dauerhaftigkeit**: offizieller Dienst oder Sample-Angebot
5. **Abdeckung und Datendichte** für die gefilterte Coverage-Heatmap
   (`ENTSCHEIDUNGEN` §2)
6. **Übertragbarkeit** der Funktionen aus `prototyp-inventar.md`
7. **Erreichbarkeit** aus der Cloud-Umgebung

## 3. Optionen

### Option A — EOPF Sentinel Zarr Samples (Kandidat der früheren Planung)

ESA-finanzierter Dienst, der Sentinel-1/-2/-3 im EOPF-Zarr-Format bereitstellt;
Konsortium unter Leitung von EODC, Hosting auf CEPH-Objektspeicher in Wien.
STAC-API unter `stac.core.eopf.eodc.eu`, Browser unter
`stac.browser.user.eopf.eodc.eu`, 12 Collections, STAC 1.1.0, IDs an das
Copernicus Data Space Ecosystem angeglichen, öffentlicher Lesezugriff über
HTTPS. Datenbestand laut FAQ ein **rollierendes Ein-Jahres-Archiv**; die
S1-SLC-Collection deckt 2023–2025 ab, S2-L2A „über Europa" ist verfügbar.
Operative Zarr-Produkte werden für „Ende 2026 oder Anfang 2027" erwartet — der
Dienst ist damit ausdrücklich ein Vorgriff, kein Zielsystem.
*(Beleg S: [zarr.eopf.copernicus.eu](https://zarr.eopf.copernicus.eu/),
[FAQ (PDF, Stand 16.12.25)](https://zarr.eopf.copernicus.eu/wp-content/uploads/2025/12/EOPF-Sentinel-Zarr-Samples_FAQ.pdf),
[CDSE-Dienstseite](https://dataspace.copernicus.eu/ecosystem/services/eopf-sentinel-zarr-samples),
[STAC-Browser](https://stac.browser.user.eopf.eodc.eu/),
[DLR-Projektseite](https://www.dlr.de/en/eoc/research-transfer/projects-missions/eopf-sentinel-zarr-samples-service))*

Passend dazu existiert **titiler-eopf**, ein GeoZarr-nativer Kachelserver mit
Reader für hierarchische Zarr-DataTrees und GeoZarr-v1-`multiscales`,
Apache-2.0, betrieben unter anderem als Live-Deployment bei Copernicus.
*(Beleg S: [Titiler-Integration im EOPF-Explorer](https://explorer.eopf.copernicus.eu/software-services/titiler/),
[titiler-eopf API-Referenz](https://developmentseed.org/datacube-guide/latest/visualization/titiler/apis/titiler-eopf.html))*
Das ist genau der Baustein, den `architekturplan.md` §6.2 zu prüfen verlangt.

### Option B — Sentinel-2 L2A COGs über Earth Search v1 (AWS Open Data)

Von Element 84 betriebene STAC-API unter `earth-search.aws.element84.com/v1`,
Daten im Registry of Open Data on AWS. Collection `sentinel-2-l2a` führt pro
Band ein COG-Asset (us-west-2) und das JP2K-Original (eu-central-1);
`sentinel-2-c1-l2a` (Collection 1) soll sie ablösen und enthält nur noch COGs ab
Baseline 5.0. Zugriff nach Doku-Beispielen anonym, ohne Authentifizierung.
*(Beleg S: [Earth Search](https://element84.com/earth-search/),
[Earth Search v1 Ankündigung](https://element84.com/geospatial/introducing-earth-search-v1-new-datasets-now-available/),
[README im Repo Element84/earth-search](https://github.com/Element84/earth-search/blob/main/README.md),
[Registry of Open Data](https://registry.opendata.aws/sentinel-2-l2a-cogs/))*

### Option C — Microsoft Planetary Computer

Öffentliche STAC-API, anonym abfragbar. Der Pixelzugriff läuft jedoch über
**SAS-signierte URLs**: signieren ist ohne Konto möglich und dient „vorerst nur
als Request-Audit", anonymer Download wird aber gedrosselt; ein API-Key hebt die
Grenzen an.
*(Beleg S: [Using Tokens for Data Access](https://planetarycomputer.microsoft.com/docs/concepts/sas/),
[Planetary Computer Docs](https://planetarycomputer.microsoft.com/docs))*

### Option D — Copernicus DEM GLO-30 (AWS Open Data)

Globales Höhenmodell als Cloud-Optimized GeoTIFF, STAC-1.0.0-Endpunkt,
Open-Data-Sponsorship-Programm, „no subscription is required"; die
öffentliche GLO-30-Fassung lässt einzelne Länder aus.
*(Beleg S: [Registry of Open Data: Copernicus DEM](https://registry.opendata.aws/copernicus-dem/),
[readme.html im Bucket](https://copernicus-dem-30m.s3.amazonaws.com/readme.html))*

## 4. Kriterienmatrix

Beleg-Spalte: `S` = Suchtreffer mit Link, Primärdokument ungelesen; `P` = Plandokument.

| Kriterium | A — EOPF Zarr Samples | B — Earth Search S2 L2A | C — Planetary Computer | D — Copernicus DEM | Beleg |
|---|---|---|---|---|---|
| Token / Registrierung | keine; „public, read-only HTTPS access" | keine nach Doku-Beispielen | STAC frei; Pixel nur über SAS-Signatur, anonym aber gedrosselt | keine; „no subscription is required" | S |
| Lizenz | Copernicus Sentinel Legal Notice: „free, full and open", Bearbeitung und Weitergabe erlaubt, Namensnennung „Contains modified Copernicus Sentinel data [Jahr]" | dieselbe (Sentinel-Daten) | je Collection unterschiedlich, nicht einheitlich | Copernicus-DEM-Lizenz, eigenes Dokument, **unbelegt** ob Bearbeitung ausdrücklich erlaubt | S |
| Einstufung nach B11 | **Processing** | **Processing** | Processing nur je Collection prüfbar | mindestens Katalogeintrag; Anzeige/Processing **unbelegt** | P + S |
| Format | **Zarr (EOPF/GeoZarr)** — Rang 1 | COG — Rang 2 | COG — Rang 2 | COG — Rang 2 | P + S |
| STAC-API | ja, STAC 1.1.0, 12 Collections | ja, STAC-API v1 | ja | ja, STAC 1.0.0 | S |
| Dauerhaftigkeit | **Sample-Dienst**; operative Zarr-Produkte „Ende 2026/Anfang 2027" erwartet, Archiv rollierend ein Jahr, Ausweitung „in Diskussion mit ESA" | Open-Data-Sponsorship, laufender Betrieb, Collection-1-Umstellung angekündigt | Betreiberabhängig, kommerzieller Anbieter | Open-Data-Sponsorship, statisches Produkt | S |
| Abdeckung | Ausschnitt: rollierendes Jahr, S2-L2A „über Europa", S1-SLC 2023–2025 | globales Sentinel-2-Archiv, dichte Zeitreihe | breit, viele Missionen | global, **eine** Abdeckung ohne Zeitachse | S |
| Eignung Coverage-Heatmap | **schwach** — dünne, ungleiche Stichprobe; die Heatmap zeigte eher den Sample-Zuschnitt als die Aufnahmedichte | **stark** — hohe Dichte, echte Zeitfilterung | stark | **untauglich als Heatmap**; §2 sieht dafür „Ausdehnung allein" vor (Einmal-Produkt) | P + S |
| Erreichbarkeit aus dieser Umgebung | **nicht prüfbar, Egress gesperrt** | **nicht prüfbar, Egress gesperrt** | **nicht prüfbar, Egress gesperrt** | **nicht prüfbar, Egress gesperrt** | gemessen |

## 5. Übertragbarkeit der Prototyp-Funktionen

Grundlage: `docs/prototyp-inventar.md`. „Direkt" heißt: läuft nach dem Entfernen
der Token-Logik ohne fachliche Änderung.

| Funktion | bei B (COG) | bei A (Zarr) |
|---|---|---|
| F1 AOI-Auswahl, F3 Upload/letzte AOI | direkt | direkt |
| F2 Ortssuche (Geocoding) | direkt, Request künftig über `gateway` (B8) | ebenso |
| F4 STAC-Suche | Anpassung: `products.ts`-Regex raus, echte Collection-/Property-Filter, Asset-Wahl aus der Registry statt Namensheuristik | dieselbe Anpassung **plus** Asset-Auflösung auf Zarr-Gruppenpfad statt Dateiendung |
| F5 Gruppierung zu Zeitschritten | Anpassung: Schlüssel aus dem Datensatzeintrag; bei S2 naheliegend Datum + MGRS-Kachel | ebenso |
| F6 Quicklook-Overlays, F7 Zeitleiste, F8 Ablauf | direkt, sofern ein Thumbnail-Asset vorliegt | direkt, sofern ein Thumbnail-Asset vorliegt; **unbelegt**, ob die EOPF-Items eines führen |
| F9 AOI-Zuschnitt (partielle COG-Reads) | **direkt**, nur `auth.get_access_token()` entfällt | **Neubau.** xarray/zarr statt rasterio, Chunk-Zugriffe statt GDAL-Blöcke, Auswahl über Dimensions- und Variablennamen. Die Naht „AOI-Fenster als Array + Maske + Transform" bleibt (Inventar F9) |
| F10 Zweistufige Anzeige / XYZ-Kacheln | **direkt** über die COG-Übersichtsstufen | **Neubau**, aber mit fertigem Baustein: GeoZarr-`multiscales` sind das Äquivalent, titiler-eopf liest sie |
| F11 Stitching | **direkt**; das Verfahren ist formatneutral, die Leseseite trägt | Leseseite über den Zarr-Reader; Rechenteil unverändert |
| F12 Coverage Map | **direkt** — reine Metadaten, formatunabhängig | **direkt**, aber inhaltlich schwach (siehe Matrix) |
| F13 Platten-Cache, F14 Streckbereichs-Cache | entfallen bzw. werden ersetzt (ADR 0001) | ebenso |
| F15 Asset-Proxy | direkt, ohne Token-Injektion, Allowlist bleibt | ebenso |
| F16 MAAP-Anmeldung | entfällt ersatzlos | entfällt ersatzlos |
| F17 Dekomposition | ruht — Sentinel-2 ist kein SAR | ruht — Sentinel-1 ist Dual-Pol (`ENTSCHEIDUNGEN` §3) |
| F18 Darstellungssteuerung | direkt; Bandmathematik über rio-tiler bleibt | Neubau auf dem Zarr-Kachelpfad |
| F19 Layer-Manager, F20, F21 | direkt | direkt |

**Kurzfassung:** Bei B sind F9, F10, F11 und F18 — die vier teuersten
Backend-Funktionen — ohne fachliche Änderung übertragbar; die Arbeit besteht im
Entfernen der Token-Logik und im Ersetzen der BIOMASS-Produktkenntnis durch
Registry-Einträge. Bei A sind dieselben vier Funktionen neu zu bauen, weil der
gesamte Lesepfad wechselt.

## 6. Empfehlung

**Zwei Schritte, in dieser Reihenfolge:**

1. **Erster Datensatz: Option B**, Collection `sentinel-2-c1-l2a` über Earth
   Search v1. Begründung: Der erste Datensatz ist der Träger des Umbaus. Bei B
   bleibt der Umbau auf das beschränkt, was ohnehin beschlossen ist —
   Token-Logik raus (`ENTSCHEIDUNGEN` §3), Zustand raus (ADR 0001),
   Produktkenntnis in die Registry (B13), Requests über `gateway` (B8). Der
   Lesepfad ist dabei die Kontrollgröße, die unverändert bleibt und zeigt, ob
   der Umbau sonst gelungen ist. Zusätzlich ist B der einzige Kandidat, an dem
   sich die gefilterte Coverage-Heatmap überhaupt belastbar bauen lässt: sie
   braucht Dichte und eine echte Zeitachse.
2. **Zweiter Datensatz, unmittelbar danach: Option A.** Der Zarr-Reader ist
   Pflicht — die Format-Hierarchie steht, und ein Zweitdatensatz in einem
   anderen Format ist die einzige ehrliche Probe darauf, ob die Registry und die
   Reader-Naht tragen. titiler-eopf ist dafür der zu prüfende Baustein
   (`architekturplan.md` §6.2).

**Zur Format-Hierarchie:** Die Empfehlung setzt sie nicht außer Kraft. Die
Hierarchie sagt, welches Format zu bevorzugen ist, wenn dieselben Daten in
mehreren vorliegen. Sie sagt nichts darüber, an welchem Datensatz ein Umbau
durchgeführt wird. Wer A zuerst nimmt, ändert Token-Logik, Zustandshaltung und
Lesepfad gleichzeitig und hat bei einem Fehler keine Kontrollgröße.

**Gegen C:** Die SAS-Signatur ist technisch ein Token. Auch wenn sie ohne Konto
zu bekommen ist, widerspräche sie `ENTSCHEIDUNGEN` §1 dem Sinn nach und brächte
genau die Signier-Logik zurück, die aus `gateway` herausgehalten werden soll
(B8). Nicht als erster Datensatz.

**Gegen D als ersten:** Ein Einmal-Produkt ohne Zeitachse kann F5, F7 und die
Heatmap nicht auslasten. D ist ein guter **dritter** Datensatz, weil er den Fall
„Einmal-Produkt, Coverage = Ausdehnung" aus `ENTSCHEIDUNGEN` §2 abdeckt.

**Was vor der Umsetzung noch zu prüfen ist** (jeweils am Primärdokument, sobald
Egress offen ist): Lizenzfeld und Attributionspflicht im STAC-`license` der
gewählten Collection; ob `sentinel-2-c1-l2a` ein Thumbnail-Asset für F6 führt;
Ratengrenzen des Anbieters; ob die AWS-Region us-west-2 für den geplanten
Betriebsort Kosten oder Latenz verursacht.

## 7. Token-freie Quelle für komplexe Quad-Pol-SAR-Daten

Eigener Punkt, weil `ENTSCHEIDUNGEN` §3 ihn offen führt: `decomp.py` braucht
komplexe Quad-Pol-Daten (Betrag und Phase, HH/HV/VH/VV).

**Ergebnis: In dieser Recherche wurde keine token-freie, registrierungsfreie
Quelle gefunden.** Was geprüft wurde:

| Quelle | Quad-Pol? | Zugang | Beleg |
|---|---|---|---|
| Sentinel-1 | nein, Dual-Pol | offen | P (`ENTSCHEIDUNGEN` §3) |
| NISAR | teilweise — Dual-Pol global, Quad-Pol nur über „a limited set of targets", Schwerpunkt Indien und USA; L1-SLC und Kovarianzprodukte (COV) vorgesehen; öffentliche Freigabe seit 20.07.2026 | über ASF DAAC / NASA Earthdata → **Earthdata-Login** | S: [NISAR Polarimetry](https://science.nasa.gov/mission/nisar/polarimetry/), [NISAR L-Band Data Now Publicly Available](https://www.earthdata.nasa.gov/data/alerts-outages/nisar-l-band-data-now-publicly-available), [NISAR Data User Guide](https://nisar-docs.asf.alaska.edu/availability-overview/) |
| UAVSAR (luftgestützt, voll polarimetrisch) | ja | SLC-Anforderung nur mit **registriertem Konto** | S: [UAVSAR SLC-Anforderung](https://uavsar.jpl.nasa.gov/science/documents/request-SLC.html), [File Downloads](https://uavsar.jpl.nasa.gov/cgi-bin/download-files.pl) |
| ALOS/ALOS-2 PALSAR | ja in L1.1 | **Registrierung** (JAXA bzw. ASF/Earthdata) | S: [ALOS open and free](https://www.eorc.jaxa.jp/ALOS/en/dataset/alos_open_and_free_e.htm), [ASF PALSAR-Doku](https://docs.asf.alaska.edu/datasets/palsar/) |
| SAOCOM | ja | Zugang auf europäisches Territorium beschränkt | S (nur Suchtreffer, Primärquelle **unbelegt**) |
| ICEYE Open Data | **nein** — alle Modi Single-Pol VV | ohne Registrierung | S: [ICEYE Open Data](https://sar.iceye.com/6.0.6/opendata/opendata/) |
| Umbra Open Data | **unbelegt** | ohne Registrierung | S: [Umbra Open Data](https://umbra.space/open-data/) |
| BELSAR (ESA-Kampagne 2018, luftgestützt, mono- und bistatisch voll polarimetrisch, L-Band) | **ja** | „available upon request" über ESA-DOI; ein integrierter Datensatz liegt zusätzlich auf figshare | S: [Scientific Data](https://www.nature.com/articles/s41597-024-03320-1), [ESA BelSAR-Kampagne](https://earth.esa.int/eogateway/campaigns/belsar-campaign-2018), [figshare-Collection](https://springernature.figshare.com/collections/The_BELSAR_dataset_Mono-_and_bistatic_full-pol_L-band_SAR_for_agriculture_and_hydrology/6717786/1) |

**Einschätzung.** Der Befund bestätigt `ENTSCHEIDUNGEN` §3: Der Operator ruht
weiter mit synthetischen Tests. Die aussichtsreichste Spur ist **BELSAR** — ein
abgeschlossener, publizierter Kampagnendatensatz mit DOI, dessen figshare-Ablage
möglicherweise ohne Registrierung erreichbar ist. Das ist eine Spur, keine
Aussage: Lizenz und Zugangsweg sind **unbelegt** und ohne Egress nicht prüfbar.
Ein einzelner Kampagnendatensatz trüge ohnehin keine Coverage Map und käme nur
als schmaler Capability-Datensatz für den Operator in Frage — was nach B10
zulässig ist, weil Capabilities je Datensatz gesetzt werden.

**Nicht entschieden, nicht geraten:** Ob ein Datensatz, der nur „auf Anfrage"
herausgegeben wird, als token-frei im Sinne von §1 gilt, steht in `docs/` nicht
und ist keine Auslegung, die dieses ADR treffen darf.

## 8. Folgen der Entscheidung

- Der Datensatz wird nach der Onboarding-Checkliste `projektuebersicht.md` §5
  aufgenommen, inklusive Punkt 10 und Coverage Map (B12).
- `DatasetConfig` entsteht als Dataclass in `datasets.py` (B13, Stufe M1–M4).
  Alle Capability-Flags werden ausdrücklich gesetzt (B10); die Quad-Pol-Capability
  bleibt in jedem der vier Kandidaten `false`.
- `stac.py` wird zum ersten Adapter gegen die gewählte Quelle
  (`architekturplan.md` §13); der Katalogzugriff geht über `gateway` (B8).
- Mit dem ersten laufenden token-freien Datensatz ist die Bedingung aus
  `ENTSCHEIDUNGEN` §3 für das Entfernen des BIOMASS-Codes erfüllt — die
  Entscheidung darüber bleibt bei Otto (Stufe B). Damit endet auch die befristete
  Ausnahme für das OIDC-Client-Secret.

## 9. Offene Fragen an Otto

**Frage 1 — Egress.** Die Erreichbarkeitsprüfung ist ohne Freigabe nicht
nachholbar, und keine Lizenz- oder Laufzeitangabe dieses Dokuments ist am
Primärdokument geprüft.

1. Egress für die in „Methode und Grenzen" genannten Hosts freigeben; dann wird
   dieses ADR in einer Folgesitzung mit geprüften Primärquellen und einem echten
   Erreichbarkeitstest nachgezogen. *(Empfehlung)*
2. Otto prüft die Links selbst und bestätigt die Angaben im Chat.
3. Entscheidung ohne weitere Prüfung auf Basis der Suchtreffer.

**Frage 2 — Reihenfolge.** Welcher Datensatz ist der erste?

1. Option B (Sentinel-2 L2A COG) zuerst, Option A (EOPF Zarr) unmittelbar als
   zweiter. *(Empfehlung, siehe Abschnitt 6)*
2. Option A zuerst, damit die Format-Hierarchie auch im ersten Schritt gilt.
3. Beide parallel von Anfang an.
