# M5 — Discovery und Suche

**Stand:** 31.10.2026, **Fassung 1.1** (Rahmen, Vorgaben, Antworten Otto, Aufgaben für die Entscheidungsvorlagen). Der Schnitt der Umsetzung kommt mit Fassung 2 nach den ADRs.
**Grundlage:** `projektplan.md` §4 M5, `architekturplan.md` Abschnitte 4 (Discovery) und 5 (Katalog), `projektuebersicht.md` §5, `KLAERUNGEN.md` B10–B13, `adr/0018` (Sentinel-1), `adr/0021` (Suchfilter), `adr/0022` (Datennähe), Backlog `docs/plans/nach-m4-backlog.md`.
**Rangfolge:** ENTSCHEIDUNGEN_2026-09-18.md > KLAERUNGEN.md > dieser Plan > CLAUDE.md.

## 1. Ziel (Projektplan)

Der eigentliche „Datacrawler“: Datensätze finden, prüfen, freigeben und auffindbar machen.

- **Inhalt:** Trichter Stufen 0 und 1 (STAC Index/Atlas, STAC-Collection-Suche, CKAN, DCAT-AP, OAI-PMH nach Bedarf); Pipeline mit Zustandsautomat, Rohspeicherung, Inhalts-Hash; Verify; Dedupe mit Distributionen; Git-basierter Review; Health-Checks; Hybrid-Suche mit pgvector, Volltext und RRF; Bewertungs-Set für Suchqualität.
- **Funktionen:** AOI-zuerst-Suche; Verfügbarkeits-Zeitleiste; Eignungskarte pro Datensatz; „zuletzt erfolgreich geprüft“ sichtbar; Datensatz-Wünsche und Fehlermeldungen; JSON-LD und Sitemap für eigene Auffindbarkeit.
- **Abnahme (Entwurf aus dem Projektplan):** Ein Harvest-Lauf erzeugt Review-Vorschläge als PRs; ein erneuter Lauf ohne Quelländerung kostet nur bedingte Requests; Bewertungs-Set besteht.

## 2. Vorgaben von Otto (31.10.2026)

Wörtlich:

> ich will mich bei den datenquellen auf den DACH raum vorerst fokussieren, also so ESA bzw satellitendaten sowieso immer (auch von JAXA oder NASA usw) aber ich will auch daten von den nationalen behörden der Dach länder (also metereologie usw.)) Ich will eigentlich nur frei verfügbare quellen haben die ohne key funktionieren und rechtlich abgesichert sind. ABer ich will (nur für mich jetzt im prototypen, in de released version sollen die wieder verschwinden) auch daten haben die rechtlich fraglich sind ob sie verwendet werden dürfen. und wegen anonymen api keys haben wir eh schon mal gesprochen.

Daraus:

1. **Satellitendaten immer:** ESA/Copernicus, dazu JAXA, NASA, USGS und andere Raumfahrtagenturen, soweit frei.
2. **DACH-Behörden zuerst:** nationale Stellen in Deutschland, Österreich, Schweiz (und Liechtenstein), z. B. Wetterdienste, Vermessung/Geodaten, Umwelt, Hydrologie.
3. **Nur frei und ohne Schlüssel:** kein Konto, kein eigener API-Key. Ein **anonymes Token**, das die Quelle ohne Anmeldung ausgibt (wie beim Planetary Computer, `adr/0018` §11 C), gilt als „ohne Schlüssel“.
4. **Rechtlich abgesichert:** Lizenz geprüft und nach B11 eingestuft (Katalogeintrag / Anzeige / Processing); Lizenz-Freigabe immer durch Otto.
5. **Prototyp-Quellen (neu):** Für Ottos eigene Erprobung im Prototyp auch Quellen mit **unklarer Rechtslage**. Sie verschwinden in der veröffentlichten Version. Das weicht von B11 ab und braucht eine eigene, technisch abgesicherte Regel (§4, ADR D).
6. **Kostenlose Konten (Ziel, Otto 31.10.2026):** Quellen, die ein kostenloses Konto verlangen (z. B. CDSE-Download, NASA Earthdata), zählen vorerst **nicht** als „ohne Schlüssel“. Otto will aber an einer Lösung arbeiten, sie zu ermöglichen (ADR E).
7. **Jeder Datensatz hat Eigenheiten (Otto, 31.10.2026):** beim Processing (Fähigkeiten, eigene Operatoren), bei der erweiterten Suche (Filter, DS-02) und bei Schnellrechnungen (Index-Knöpfe, NM4-14). Das Onboarding jedes Datensatzes legt diese drei Teile ausdrücklich fest; sie stehen in der Registry, nicht im Code des Frontends.

## 3. Was mit M5 zusätzlich ansteht

- **DS-04** Sentinel-1 anbinden (`adr/0018` Fassung 2), **DS-05** SAR-Operatoren.
- **`data_region`** als Registry-Feld und Auswahlkriterium (`adr/0022` F3); Messung Stufe 1 liegt vor (Backlog 48).
- **Datensatz-Browser** (vorgemerkt seit M3, Log 30.09.2026): alle Datensätze mit Beschreibung durchsehen und ins Control-Menü übernehmen; passt zur Hybrid-Suche.
- **Health-Checks** je Quelle (Architekturplan 4.5), „zuletzt erfolgreich geprüft“ sichtbar (B12, Checkliste Punkt 10).
- **Earth Search v2** (Backlog 36): Collection-Wechsel, sobald er kommt.
- Bestehender Dienst `harvester` im Compose-Stack: Stand prüfen (was er heute kann), darauf aufbauen.

## 4. Nötige Entscheidungsvorlagen (Stufe C, je eigene Session, Opus)

| | Thema | Inhalt |
|---|---|---|
| **A** | Quellenkatalog DACH und Satellit | Recherche mit Quellen: welche Stellen (z. B. DWD, BKG, GeoSphere Austria, BEV/basemap.at, MeteoSwiss, swisstopo, BAFU, Landesämter; ESA/Copernicus-Dienste, JAXA, NASA/USGS) bieten welche Rasterdaten **ohne Schlüssel** an, über welche Schnittstelle (STAC, OGC API, WMS/WCS, Datei-Server), welche Lizenz (z. B. dl-de/by-2-0, CC BY 4.0, OGD Schweiz), wo liegen die Daten (`data_region`), welche Formate. Ergebnis: Rangliste der ersten Quellen für M5 mit B11-Einstufung als **Vorschlag** (Freigabe Otto). |
| **B** | Harvest-Pipeline | Trichter Stufen 0/1, Zustandsautomat, Rohspeicherung, Inhalts-Hash, bedingte Requests (ETag/Last-Modified), Dedupe mit Distributionen, Review als PR, Health-Checks; Bezug auf den vorhandenen `harvester`. Modulgrenzen nach Architekturplan 3.1; ausgehend nur über `gateway`. |
| **C** | Hybrid-Suche | Volltext + Vektor (pgvector) + RRF, Wahl des Embedding-Modells (lokal, ohne Datenabfluss), Bewertungs-Set (Fragen, erwartete Treffer, Kennzahl), Kosten und Speicher. Rechenrelevant: Stand der Technik mit Quellen. |
| **D** | Prototyp-Quellen | Wie Quellen mit unklarer Rechtslage markiert im Repo stehen, nur im Prototyp für Otto geladen werden und nie in eine veröffentlichte Version gelangen (Antwort 3). |
| **E** | Quellen mit kostenlosem Konto | Wie Quellen mit Konto später möglich werden (Antwort 4). |

Sentinel-1 (DS-04/05) läuft nach den bestehenden Plänen, nicht über diese ADRs.

## 5. Antworten Otto (31.10.2026)

1. **Reihenfolge:** ja – zuerst ADR A und zwei bis drei Quellen von Hand, dann die Pipeline (ADR B). Jeder Datensatz hat Eigenheiten bei Processing, erweiterter Suche und Schnellrechnungen (§2 Punkt 7).
2. **Datentypen:** zunächst nur Raster.
3. **Prototyp-Quellen:** dürfen ins öffentliche Repo, aber **markiert**. ADR D legt Markierung und Absicherung fest (z. B. Registry-Feld für den Rechtsstatus, Laden nur mit Schalter, in veröffentlichten/Cloud-Konfigurationen technisch ausgeschlossen, Kennzeichnung in der Oberfläche, keine Weitergabe per Permalink oder geteiltem Cache).
4. **Anonyme Tokens** zählen als „ohne Schlüssel“, kostenlose Konten nicht – mit dem Ziel, Konten später zu ermöglichen (ADR E).
5. **Discovery-Umfang:** feste Liste bekannter Quellen plus STAC Index, dazu CKAN/DCAT-AP für GovData, data.gv.at und opendata.swiss; offene Suche in Paket 7b.
6. **Bewertungs-Set:** Session entwirft 30–50 Testfragen, Otto ergänzt und gibt frei.

## 5a. Aufgaben für die Entscheidungsvorlagen

Feste ADR-Nummern, damit parallele Sessions nicht kollidieren. Alle Stufe C (nur ADR-Entwurf, Messskripte unter `scripts/` ohne eigene HTTP-Aufrufe außerhalb von `gateway`, Netzschritte als Einmal-Schritt), Opus, Effort hoch. Abnahme je ADR: Entwurf mit Quellen und Belegstufe, Optionen, Empfehlung, Fragen F1 … Fn; Log-Zeile mit PR-Nummer, Status „offen“; Backlog nicht ändern; vor „fertig“ main holen.

| Aufgabe | ADR | Thema | Start |
|---|---|---|---|
| **M5-01** | `adr/0023-quellenkatalog-dach.md` | Quellenkatalog DACH und Satellit (§4 A): Stellen, Schnittstellen, Lizenzen (B11-Vorschlag), `data_region`, Formate, Eigenheiten je Datensatz (§2 Punkt 7); Rangliste der ersten zwei bis drei Quellen | sofort |
| **M5-02** | `adr/0024-prototyp-quellen.md` | Prototyp-Quellen (§4 D, Antwort 3) | sofort |
| **M5-03** | `adr/0025-harvest-pipeline.md` | Harvest-Pipeline (§4 B, Antwort 5); Stand des vorhandenen `harvester` | nach M5-01 |
| **M5-04** | `adr/0026-hybrid-suche.md` | Hybrid-Suche und Bewertungs-Set (§4 C, Antwort 6) | nach M5-01 |
| **M5-05** | `adr/0027-quellen-mit-konto.md` | Quellen mit kostenlosem Konto (Antwort 4): Optionen wie Plattform-Konto mit Secret nur im Betrieb, Konto je Nutzer (M6/M7, „Token pro Connector“), Kontingente (z. B. CDSE 4 Verbindungen, 50 000 Anfragen/Monat je Konto, `adr/0022`), Lizenz- und Nutzungsbedingungen der Konten, Datenschutz | sofort |

Startsatz je Aufgabe: „Führe Aufgabe M5-0x aus `docs/plans/m5/m5-discovery-und-suche.md` (§5a) aus.“

## 6. Nächste Schritte

1. Otto beantwortet §5.
2. Stufe-C-Sessions M5-01, M5-02 und M5-05 sofort, M5-03 und M5-04 nach M5-01.
3. Fassung 2 dieses Plans mit dem Schnitt in Aufgaben, Abnahme und Reihenfolge; dazu der Abschluss der offenen Aufgaben vor M5 (Backlog).

## 7. Grenzen (gelten für alle M5-Aufgaben)

- Modulgrenzen laut `architekturplan.md` 3.1 (Import-Linter); ausgehende Requests nur über `gateway`; Worker-Kern zustandslos; `decomp.py` nie generalisieren.
- Keine Secrets im Repo (öffentlich, AGPL-3.0-or-later); Prototyp-Quellen nur markiert und nach ADR D abgesichert (Antwort 3).
- Keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Lizenz-Einstufung und Freigabe jedes Datensatzes immer durch Otto.
- Bilder der Browserprüfung nicht ins Repo; Nachträge heißen nach der Aufgabe.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` nur mit ausdrücklicher Erlaubnis.
