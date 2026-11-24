# M5 — Discovery und Suche

**Stand:** 23.11.2026, **Fassung 3.4** (Nachführung, Doku-Runde 23.11.). Fassung 3.4 trägt nach: §2 Punkt 9 (Klassen, Farben nie von Hand, Histogramm in Farben, QGIS-Stil bei jedem Export), §2 Punkt 12 (Link nie Sammelseite oder Schnittstelle, Zugang, Lizenzen, erste Freigaben), erledigte Aufgaben bis #402 (M5-20 PR 1, M5-42, M5-55, M5-61, M5-62 PR 1, Freigaben FSDI, opendata.swiss, GovData), neue Aufgaben M5-63 bis M5-66, neue Reihenfolge. Fassung 3.3 (18.11.2026, Nachführung, Doku-Runde 18.11.). Der Planungs-Chat führt den Plan laufend in seiner Projektkopie; jede Doku-Runde bringt den Stand ins Repo. Fassung 3.3 trägt nach: §2 Punkt 9 (Ladeanzeige, Trefferzahl ehrlich, Bänder als Tabelle, AOI „Point“ als Punkt), §2 Punkt 12 (Link „Source“), §6.5 (Takt von `materialize`, laufende Aktualisierung, Tests), erledigte Aufgaben bis #380, neue Aufgaben M5-55 bis M5-61, UI-12 Punkte (4)–(6), Vorgemerktes (Zeitreihen-Werkzeug). **Fassung 3.2** (Nachführung, Doku-Runde 16.11.). Der Planungs-Chat führt den Plan laufend in seiner Projektkopie; jede Doku-Runde bringt den Stand ins Repo. Fassung 3.2 trägt nach: §2 Punkte 9–12 (Vorgaben Otto 11.–16.11.), §5 Punkt 2, erledigte Aufgaben bis #358, neue Aufgaben M5-31 bis M5-43, UI-07, UI-08, die Abnahme Punkt 10 (Skalierbarkeit) und die neue Reihenfolge. Fassung 3.1 (11.11.2026, Nachführung): Fassung 3 (angenommen von Otto am 06.11.2026, §8: F1 und F2 jeweils Option 1) schnitt den Rest der Umsetzung und legte die Abnahme fest. Fassung 3.1 trifft keine neue Entscheidung: Sie trägt den Stand nach (§6.1), die seither entstandenen Aufgaben M5-28 bis M5-30, UI-06, F11, F12 und die Vorarbeiten V1–V9 aus `adr/0031` (§6.2), die Vorgaben Ottos seit dem 07.11. (§2 Punkt 9) und die neue Reihenfolge (§6.3). Die Entscheidungen dazu stehen bereits im Entscheidungslog.
**Grundlage:** `projektplan.md` §4 M5, `architekturplan.md` Abschnitte 4 (Discovery) und 5 (Katalog), `projektuebersicht.md` §5, `KLAERUNGEN.md` B10–B13, `adr/0018` (Sentinel-1), `adr/0021` (Suchfilter), `adr/0022` (Datennähe), `adr/0023` (Quellenkatalog), `adr/0024` (Prototyp-Quellen), `adr/0025` (Harvest-Pipeline), `adr/0026` (Hybrid-Suche), `adr/0027` (Quellen mit Konto), `adr/0029` (Leseweg NetCDF), `adr/0030` (Operatoren je Datensatz), `adr/0031` (automatisches Onboarding), `adr/0032` (Übersicht und Mosaik bei kleinem Zoom), Backlog `docs/plans/nach-m4-backlog.md`.
**Rangfolge:** ENTSCHEIDUNGEN_2026-09-18.md > KLAERUNGEN.md > dieser Plan > CLAUDE.md.

## 1. Ziel (Projektplan)

Der eigentliche „Datacrawler“: Datensätze finden, prüfen, freigeben und auffindbar machen.

- **Inhalt:** Trichter Stufen 0 und 1 (STAC Index/Atlas, STAC-Collection-Suche, CKAN, DCAT-AP, OAI-PMH nach Bedarf); Pipeline mit Zustandsautomat, Rohspeicherung, Inhalts-Hash; Verify; Dedupe mit Distributionen; Git-basierter Review; Health-Checks; Hybrid-Suche mit Volltext, Vektor und RRF; Bewertungs-Set für Suchqualität.
- **Funktionen:** AOI-zuerst-Suche; Verfügbarkeits-Zeitleiste; Eignungskarte pro Datensatz; „zuletzt erfolgreich geprüft“ sichtbar; Datensatz-Wünsche und Fehlermeldungen; JSON-LD und Sitemap für eigene Auffindbarkeit.
- **Abnahme:** §7 (Fassung 3; ersetzt den Entwurf aus dem Projektplan, `adr/0025` F7).

## 2. Vorgaben von Otto (31.10.2026)

Wörtlich:

> ich will mich bei den datenquellen auf den DACH raum vorerst fokussieren, also so ESA bzw satellitendaten sowieso immer (auch von JAXA oder NASA usw) aber ich will auch daten von den nationalen behörden der Dach länder (also metereologie usw.)) Ich will eigentlich nur frei verfügbare quellen haben die ohne key funktionieren und rechtlich abgesichert sind. ABer ich will (nur für mich jetzt im prototypen, in de released version sollen die wieder verschwinden) auch daten haben die rechtlich fraglich sind ob sie verwendet werden dürfen. und wegen anonymen api keys haben wir eh schon mal gesprochen.

Daraus:

1. **Satellitendaten immer:** ESA/Copernicus, dazu JAXA, NASA, USGS und andere Raumfahrtagenturen, soweit frei.
2. **DACH-Behörden zuerst:** nationale Stellen in Deutschland, Österreich, Schweiz (und Liechtenstein), z. B. Wetterdienste, Vermessung/Geodaten, Umwelt, Hydrologie.
3. **Nur frei und ohne Schlüssel:** kein Konto, kein eigener API-Key. Ein **anonymes Token**, das die Quelle ohne Anmeldung ausgibt (wie beim Planetary Computer, `adr/0018` §11 C), gilt als „ohne Schlüssel“.
4. **Rechtlich abgesichert:** Lizenz geprüft und nach B11 eingestuft (Katalogeintrag / Anzeige / Processing); Lizenz-Freigabe immer durch Otto, auch über Lizenzregeln (`adr/0025` §6.7).
5. **Prototyp-Quellen:** Für Ottos eigene Erprobung im Prototyp auch Quellen mit **unklarer Rechtslage**. Sie verschwinden in der veröffentlichten Version. Geregelt in `adr/0024`.
6. **Kostenlose Konten:** zählen vorerst **nicht** als „ohne Schlüssel“. In M5 nur Katalogeinträge mit Link und `access.account` (`adr/0027`).
7. **Jeder Datensatz hat Eigenheiten (Otto, 31.10.2026):** beim Processing (Fähigkeiten, eigene Operatoren), bei der erweiterten Suche (Filter, DS-02) und bei Schnellrechnungen (Index-Knöpfe, NM4-14). Das Onboarding jedes Datensatzes legt diese drei Teile ausdrücklich fest; sie stehen in der Registry, nicht im Code des Frontends. Was je Datensatz sinnvoll ist, legt `adr/0030` fest.
8. **Zusatz Otto (06.11.2026):**
   - **Operatoren je Datensatz:** → `adr/0030` (M5-12, erledigt).
   - **Control Panel:** je Seite so viele Datensätze, wie ohne Scrollen passen, ohne Obergrenze (Otto, 07.11.2026; Vorauswahl beim ersten Besuch höchstens sechs); Seitenpfeile klein oben neben „Datasets“ (Otto, 06.11.2026 abends).
   - **„Advanced search“** immer sichtbar.
   - **Kein zusätzlicher Text** im Panel.
   - **Datum:** begrenzt auf den verfügbaren Zeitraum und am Anfang mit frühestem und spätestem Aufnahmedatum des Datensatzes vorausgefüllt (Otto, 06.11.2026 abends).
   - **Data catalogue:** größeres Fenster über der Karte, geöffnet über ein Symbol in der linken Leiste (UI-05 F5); gruppiert, mit Angaben wie bei STAC und der Quelle; darin später die Suche (`adr/0026` §7).
9. **Zusätze Otto (07.–11.11.2026)**, gelten für alle Aufgaben mit Frontend:
   - **Keine Hinweise, Marken oder Zusatztexte** im Frontend; nötige Erklärungen höchstens im Tooltip. Lizenzpflichtige Nennungen (z. B. Copernicus beim Ersatz-Datensatz) stehen in der Quellenzeile der Karte, nicht als Hinweis.
   - **Das Panel scrollt nie.**
   - **Nie verschwindet ein Bild beim Herauszoomen** (`adr/0032`): unter `min_zoom` eine Übersicht oder ein Ersatz-Datensatz, nie eine leere Karte.
   - **Kompass immer sichtbar** wie bei Google Maps, 3D-Knopf unter den Zoom-Knöpfen (UI-06).
   - **Ausgabetypen nur, wo sie Sinn machen** (#333): Werte unverändert → Typ der Quelle plus `float32`; neu gerechnet → nur `float32`, bei Quelle `float64` dann `float64` (Vorgabe) und `float32`; Angabe `x-earthx-passes-values` aus der Operator-Registry. Wiedervorlage `float64` bei M5-11.
   - **Marke „Overview“ einheitlich** (Otto, 16.11.2026; ersetzt „keine Marke Overview“ vom 11.11.): Wo die Karte eine vergröberte Ansicht statt der Originale zeigt (Job-Ergebnisse, Pyramiden unter `min_zoom`, Ersatz für swissALTI3D und BEV), steht dieselbe Marke „Overview“ am selben Platz mit demselben Tooltip-Satz. Ausnahme von „keine Marken“.
   - **Ladesymbol** (13.11.2026): Dauert das Laden einer Kartenebene länger, erscheint ein Ladesymbol (Leitfaden, kein Text); allgemein, umgesetzt mit M5-30b in #345.
   - **Nie verschwindet ein Bild, auch nicht zwischen zwei Teilen einer Aufgabe** (13.11.2026, Browserprüfung #345).
   - **Ladeanzeige auf der Karte** (14.11.2026): wie beim Laden der Suchergebnisse, dasselbe Bauteil, Text „Loading data“ (ersetzt „kein Text“); der Ladekreis in der Zeile der Ebene entfällt (Otto 16.11., UI-09).
   - **Einheiten im Band-Menü** (14.11.2026): nur physikalische Einheiten (z. B. „m“); DN und einheitslose Werte dort ohne Einheit. Im Data catalogue steht je Band immer die Einheit bzw. Art der Werte (auch „DN, uncalibrated digital numbers“). Umsetzung in #343.
   - **Keine Schlagworte in der Anzeige** (16.11.2026): Die Zeile „Keywords“ im Data catalogue entfällt; Schlagworte bleiben in Registry, API und Suchtext (UI-11).
   - **Quick processing mit Seiten** (17.11.2026): je Seite so viele Quick processings, wie ohne Scrollen passen; kleine Seitenpfeile wie bei „Datasets“ im Search panel (Punkt 8); Reihenfolge aus der Registry. Umsetzung mit UI-12.
   - **AOI „Point“ ist immer ein echter Punkt** (18.11.2026), kein Rechteck; gilt überall (Suche, Zuschnitt, Werkzeuge). Umsetzung UI-12 (6).
   - **Klassenwerte erklärt** (19.11.2026): Bei Datensätzen mit Klassenwerten (z. B. WorldCover, später CORINE) sind die Klassen sichtbar – auf der Website (Data catalogue: Tabelle Wert | Klasse | Farbe; Legende der Ebene mit Klassennamen statt Farbskala) und im Export (Farbtabelle und Klassennamen in der GeoTIFF, dazu die Klassen in der vorhandenen `Bands.txt` im ZIP, keine eigene Datei – Otto 19.11.). Aus der Registry, für alle solchen Datensätze. Umsetzung M5-62.
   - **Bänder kurz beschrieben** (18.11.2026): Im Data catalogue stehen die Bänder als Tabelle (Spalten Band, Description, Unit; ohne Einheit steht in Unit nur „–“, nie „1“ oder „dimensionless“, und auch sonst nirgends ein Ersatztext – Otto 18.11.), je Band eine kurze Beschreibung von wenigen Worten (Englisch, z. B. „Daily mean air temperature, 2 m“); aus der Registry (`description` je Band), Pflicht beim Onboarding. Umsetzung M5-59.
   - **Trefferzahl ehrlich** (18.11.2026): „Search results (x/y)“ zeigt immer die echte Gesamtzahl y; gibt es mehr als geladen, steht das in y und „Load more“ ist da; nie still abschneiden, kein Hinweistext (Befund M5-56: Russland zeigte 300/300).
   - **Farben nie von Hand** (20.11.2026): Klassenfarben (und allgemein Farben einer Darstellung) werden nicht je Datensatz gepflegt; sie kommen aus der Quelle (Farbtabelle der Datei, STAC `classification:classes`, beim Onboarding übernommen), sonst aus einer festen Standardpalette; ein Eintrag von Hand nur als Ausnahme. Gilt ebenso für Farbskala und Bereich je Band (M5-60: aus Quelle bzw. Einheit, Hand nur Ausnahme). Umsetzung M5-62, M5-60.
   - **Histogramm in den Farben der Darstellung** (21.11.2026): ein Band – jeder Balken in der Farbe, die sein Wert auf der Karte hat (außerhalb des Bereichs die Endfarben); RGB je Kanal in Rot, Grün, Blau; Klassenband in den Klassenfarben; färbt sich bei Änderung von Bereich oder Farbskala sofort mit; keine zusätzlichen Texte. Umsetzung M5-60 PR 2.
   - **QGIS-Stil bei jedem Export** (20.11.2026): neben jeder Rasterdatei im ZIP eine `.qml` gleichen Namens, damit die Daten in QGIS aussehen wie in der App (ein Band: Farbskala mit Min/Max; RGB: Stretch je Band; Klassen: Werte, Farben, Namen). Umsetzung M5-64.
   - **Statusbox oben** (14.11.2026): immer mittig im freien Kartenbereich zwischen offenem Panel links und rechts, bei Bedarf schmaler, nie überdeckt; nur der Data catalogue darf sie überdecken. In #345, falls dieselbe Box wie „Loading data“, sonst eigene kleine Aufgabe.
10. **Zusätze Otto (11.11.2026 abends)**, noch ohne ADR:
   - **Keys der Nutzer erlaubt** (ändert Punkt 6 und `adr/0027`): Quellen mit Key oder kostenlosem Konto (z. B. Copernicus Data Space) dürfen angebunden werden. Der Nutzer hinterlegt seinen Key selbst beim Datensatz im Data catalogue; ein Key schaltet alle Datensätze desselben Anbieters frei; solche Datensätze tragen ein **kleines Schloss** (ausdrückliche Ausnahme von „keine Marken“) und lassen sich freischalten; der Key wird laufend auf Gültigkeit geprüft. Kein Key der Plattform, keine Secrets im Repo. → M5-32.
   - **Processing-Panel mit Reitern** (General, Optical, Radar …), je Reiter die häufig gebrauchten Verarbeitungen. Gemeint ist das Panel, in dem man einen Auftrag zusammenstellt, nicht die Job-Liste. → UI-07.
   - **Radar: Standard-Verarbeitung, kein InSAR** (`adr/0030` bleibt): Orbit, thermisches Rauschen und Randrauschen, Kalibrierung σ⁰/γ⁰, Speckle, Terrain Flattening, Geländekorrektur GTC/RTC, dB, Verhältnisse. Korrektur nach `adr/0036` (17.11.): Die Produkt-Annotation liegt im anonymen AWS-Bucket; falsch ist nur der STAC-Verweis, der auf die RFI-Annotation zeigt (Befund #343). Die GRD-Kette geht damit voraussichtlich ohne Key aus Earth Search (Annotation über Registry-Regel); Copernicus Data Space mit Key bleibt Ergänzung (SLC, Vergleich). → M5-31 (`adr/0036`), DS-05d bis DS-05f.
   - **Zwei Bilder gleichzeitig verarbeiten und vergleichen** → M5-26, vorgezogen und erweitert.
   - **Sentinel-1 nur in Radargeometrie**, solange es keine richtige Bearbeitung gibt → DS-04d.
11. **Arbeitsweise (13.11.2026):** eine Aufgabe, ein PR, höchstens zwei. Jeder weitere Teil bekommt eine eigene Nummer und eine neue Session. Grund: M5-30b mit zehn Teilen führte zu gestapelten PRs, Konflikten zwischen den Teilen und halbfertigen Zwischenständen.
12. **Alle Geodaten auffindbar (Otto, 14.11.2026):** Ziel ist, alle Geodaten der Anbieter über die Seite erreichbar zu machen, auch Tabellen (Excel, CSV), Vektordaten, Dokumente und Dienste.
   - **In M5:** Stufe „gelistet“ für alle Datentypen: Eintrag im Data catalogue mit Titel, Anbieter, Lizenz, Format, Beschreibung, räumlicher und zeitlicher Ausdehnung und Link zur Quelle; die Datei holt der Browser direkt beim Anbieter. Der Crawler (M5-19 bis M5-21) verwirft Nicht-Raster nicht mehr, sondern listet sie. Karte und Processing bleiben vorerst Raster.
   - **Link „Source“ so direkt wie möglich (Otto, 17.11.2026):** zuerst Viewer oder Download-Seite der Daten beim Anbieter, wo man sie direkt laden kann; sonst die Seite des Datensatzes; nie nur die Startseite des Anbieters. Umsetzung im Crawler (M5-19, M5-20: bei DCAT `downloadURL`/`accessURL` vor Landingpage); CORINE und Landsat bleiben unverändert (Otto 17.11., M5-19 F3/F4); die sieben vollen Einträge (heute API-Adresse) folgen mit M5-55.
   - **Auch ohne direkten Download (Otto, 14.11.2026):** Daten, die die Plattform nicht selbst anbieten kann (Bestellung, Anmeldung, Konto, kostenpflichtig, nur auf Anfrage, Portal ohne Datei-Link), werden ebenfalls gelistet, mit Link auf die Seite des Anbieters, über die man sie bekommt, und der Art des Zugangs (`access.account` bzw. neue Angabe). Das ändert `adr/0031` §8 und §9 Fall 5 (Konto-Quellen: bisher Stopp mit Notiz, gelistet nur mit `way: listed`) zu „gelistet als Vorgabe“. Lizenz-Einstufung und Freigabe im PR bleiben bei Otto.
   - **Filter im Data catalogue:** nach Region und Zeit, auch über die AOI aus „Search and area“; gilt für alle Einträge, auch gelistete. M5-19 verwirft keine Funde ohne räumliche Angabe, sondern kennzeichnet sie („Ausdehnung unbekannt“); eine Regel „keine Geodaten“ gibt es nicht (Kataloge wie GovData enthalten auch Nicht-Geodaten) – zu klären in M5-20. Dafür muss der Harvest Ausdehnung und Zeitraum je Eintrag erfassen; offen, wie Einträge ohne bekannte Ausdehnung im Filter behandelt werden (Frage in M5-20).
   - **Später (eigene Vorlage, M6 oder danach):** Vorschau von Tabellen auf der Seite; Tabellen mit Koordinaten (z. B. Messstationen) als Punkte auf der Karte; Vektordaten (GeoJSON, Shapefile, WFS) auf der Karte.
   - **Link „Source“ nie Sammelseite und nie Schnittstelle (Otto 21.–23.11.2026):** Eine Adresse, die mehr als ein Fund derselben Quelle wählen würde, oder die nur aus Host und höchstens einem Pfadteil besteht (ein führender Sprachteil zählt nicht), ist Sammelseite; Metadaten-Endpunkte (`/api/hub/repo/`, `/api/hub/search/`, `/api/3/action/`, GeoNetwork `/srv/api`, Format-Parameter u. Ä.) sind nie Link; dann gilt der nächste Rang, zuletzt die Katalogseite des Datensatzes (M5-19/M5-20, #397, #399, #401).
   - **Zugang (Otto 20.11.2026, M5-20 F12):** Fehlende `access_rights` sind kein Ausschluss, nur ausdrücklich eingeschränkte oder nicht öffentliche; Zugangsart `page` („über die Seite des Anbieters“) für Funde mit https-Link, aber nur HTML oder unbekanntem Format; nur http bleibt ohne Zugang.
   - **Lizenzen gelisteter Einträge (Otto 20.11.2026):** Einstufung nach Klassen K1–K7 (`docs/plans/m5/m5-20-lizenzliste.md`); K1–K5 für alle Herausgeber jeder Quelle freigegeben (Liste aus der Datenbank mit `harvest-grants`), K6 und amtliches Werk eingestuft, nicht freigegeben, K7 wartet; Funde ohne Herausgeber warten (F14 = 1, keine Namensnennung möglich).
   - **Erste Freigaben (21.–23.11.2026):** FSDI 305, opendata.swiss 7 748, GovData 94 258 gelistete Einträge veröffentlicht, je mit Stichprobe 30/30; seit M5-42 auch über die Suche auffindbar.
   - **Vorschlag, nicht entschieden (23.11.2026):** Umriss eines gelisteten Eintrags auf der Karte zeigen, wenn er im Data catalogue gewählt ist (Fußabdruck vorhanden); Vektoren auf der Karte bleiben „später“ (Punkt darüber), auf Wunsch vorher ADR mit Stand der Technik.
   - Log-Zeile dazu mit M5-17 (#367) eingetragen.

## 3. Was mit M5 zusätzlich ansteht

- **DS-04** Sentinel-1 anbinden (`adr/0018` Fassung 2), **DS-05** SAR-Operatoren, aufgeteilt nach `adr/0030` §9 in DS-05a bis DS-05d.
- **`data_region`**: erledigt mit M5-07 (#298).
- **Datensatz-Browser**: als „Data catalogue“ in UI-05; Suche darin mit M5-23.
- **Health-Checks** je Quelle, „zuletzt erfolgreich geprüft“ sichtbar: M5-24.
- **Earth Search v2** (Backlog 36): weiter Beta ohne öffentlichen Endpunkt; keine Aufgabe in M5, solange das so bleibt.
- **`harvester`**: heute eine leere Hülle (`adr/0025` §2); wird mit M5-24 zum Takt der Pipeline.
- **Mosaik-Zoom bei groben Rastern** (Backlog 29): durch `adr/0032` geregelt (M5-30); Prüfpunkt bleibt in M5-11 für das erste NetCDF-Raster.

## 4. Entscheidungsvorlagen (alle angenommen)

| | Thema | ADR | PR |
|---|---|---|---|
| A | Quellenkatalog DACH und Satellit | `adr/0023` | #262, #295 |
| B | Harvest-Pipeline | `adr/0025` | #300 |
| C | Hybrid-Suche und Bewertungs-Set | `adr/0026` | #301 |
| D | Prototyp-Quellen | `adr/0024` | #260 |
| E | Quellen mit kostenlosem Konto | `adr/0027` | #261 |
| — | Leseweg NetCDF/HDF5 | `adr/0029` | #303 |
| — | Operatoren und Quick processings je Datensatz | `adr/0030` | #302 |
| — | Automatisches Onboarding (M5-29) | `adr/0031` | siehe Log |
| — | Übersicht und Mosaik bei kleinem Zoom (M5-30) | `adr/0032` | siehe Log |

Kernpunkte für die Umsetzung:

- **`adr/0023`:** Quellen von Hand: WorldCover (zwei Datensätze), swissALTI3D, BEV ALS-DGM 1 m; Lizenzvorschläge angenommen, Wortlaute bestätigt Otto im PR; `data_region` als `<betreiber>:<ort>` bzw. `unknown`. Offen bis M5-08: mehrere Stände je Kachel.
- **`adr/0024`:** `legal_status` (`cleared`/`unclear`), Präfix `proto-`, YAML außerhalb des Images, Laden nur mit `EARTHX_PROTOTYPE_SOURCES` und `EARTHX_PROFILE=local`, nie in CI und Runner; Ergebnisse erben den Status (F11).
- **`adr/0025`:** Befehle in `discovery`, Zustand in Postgres, Kandidaten in Git, PR durch Otto (P1); Harvest in M5 nur lokal bei Otto; Stufe „gelistet“ (B11 Stufe 1); Kandidatendateien; höchstens 20 Kandidaten je PR; CKAN mit Herausgeberliste; Lizenzregeln „Herausgeber + Lizenz-URI → Stufe“; `User-Agent` Pflicht in `gateway`; YAML unter `backend/catalog/`; Schnitt in sieben Schritte (§8 dort).
- **`adr/0026`:** Volltext (`simple`, `german`, `english`, `unaccent`, Trigramme, Glossar) und Vektor (multilingual-e5-small/-base, int8, im Prozess `api`, nicht im Runner-Image), **ohne pgvector** (Vektor als Spalte, Vergleich in `api`); RRF k = 60; harte Filter vor der Fusion; Collection Search mit `q`, Fläche nur per `POST`; Index in `catalog-load`; Bewertungs-Set mit 50 Fragen, Grenze Recall@5 ≥ 0,9 und MRR@10 ≥ 0,8 je Sprache.
- **`adr/0027`:** Konto-Quellen nur als Katalogeintrag mit Link; `access.account` (`none`, `anonymous_token`, `free_account`, `requester_pays`); Regel R-Z.
- **`adr/0029`:** eigene virtuelle Verweise (h5py nur in `discovery`), ein Item je Zeitschritt, Verweise im Item, ETag-Prüfung beim Lesen, Fehlerart `source_changed`; zuerst nur abgeschlossene Jahresdateien; ARCO-ERA5 nicht in M5.
- **`adr/0031`:** geplante Aufgabe, ein Sammel-PR je Tag mit neuen Datensätzen, Profile je Quellenart, Prüflauf in GitHub Actions; vorher die Vorarbeiten V1–V9 (§6.2); Lizenz-Einstufung bleibt bei Otto.
- **`adr/0032`:** Übersicht bei kleinem Zoom; Budget je Kachel 32 Dateien und 4 s, `MOSAIC_THREADS` 4; Teilkacheln mit Kopf `X-EarthX-Partial`, `no-store`, ohne Marke; Mosaik-ID aus dem Hash der Item-Liste (bis 2000 Items); Kostenschätzung statt 25er-Grenze; Pyramide nur für GLO-30 und WorldCover (Bau gleich nach `materialize`, 0,25 s Abstand, Ablauf 30 Tage mit Verlängerung nach bedingter Prüfung); unter `min_zoom` von swissALTI3D und BEV zeigt GLO-30 als Ersatz (F7 = 1), Copernicus in der Quellenzeile.
- **`adr/0030`:** Operator-Art `focal` (in M5-10), `sar_db` mit Wertetabelle, Speckle-Filter Boxcar/Lee, σ⁰-Kalibrierung, Felder `composite_presets` und `step_presets`, vier Sentinel-2-Presets, Klassenanteile WorldCover; keine eigene InSAR, kein Pauli; Quick processings auf S1 als Nachtrag M5-12 zu `adr/0018` F3.

## 5. Antworten Otto (31.10.2026)

1. **Reihenfolge:** zuerst ADR A und zwei bis drei Quellen von Hand, dann die Pipeline (ADR B).
2. **Datentypen:** zunächst nur Raster. **Geändert (Otto, 14.11.2026, §2 Punkt 12):** gelistet werden alle Datentypen; Karte und Processing vorerst nur Raster.
3. **Prototyp-Quellen:** dürfen ins öffentliche Repo, aber markiert (`adr/0024`).
4. **Anonyme Tokens** zählen als „ohne Schlüssel“, kostenlose Konten nicht (`adr/0027`).
5. **Discovery-Umfang:** feste Liste bekannter Quellen plus STAC Index, dazu CKAN/DCAT-AP für GovData, data.gv.at und opendata.swiss; offene Suche in Paket 7b.
6. **Bewertungs-Set:** Session entwirft 30–50 Testfragen, Otto ergänzt und gibt frei (in `adr/0026` F4 freigegeben).

## 6. Schnitt der Umsetzung (Fassung 3)

### 6.1 Erledigt

| Aufgabe | Inhalt | PR |
|---|---|---|
| M5-01 bis M5-06, M5-12 | Entscheidungsvorlagen (§4) | #260–#262, #295, #300–#303 |
| M5-29, M5-30 (ADR) | `adr/0031`, `adr/0032` | siehe Log |
| M5-07 | ESA WorldCover 2020/2021, `data_region` für alle Datensätze | #298 |
| UI-05 Teil 1 | Control Panel mit Seiten, „Advanced search“ immer sichtbar, Datum begrenzt, kein Zusatztext | #299 |
| UI-05 Teil 2 (UI-05b) | Data catalogue als Fenster, Registry-Felder für Gruppe, `providers`, `gsd` | siehe Log |
| UI-06 | 3D-Ansicht, Kompass immer sichtbar | siehe Log |
| M5-13 | YAML-Lader, alle Einträge unter `backend/catalog/datasets/` | siehe Log |
| M5-18 | `gateway`: `User-Agent`, Abstand je Host, `robots.txt` | siehe Log |
| M5-08 a–c | Allgemeiner STAC-Adapter, swissALTI3D, mehrere Stände je Kachel | siehe Log |
| DS-04 a–c | Sentinel-1 GRD (TPS, Fassung über CRC64NVME mit Rückfall auf ETag) | siehe Log, #327 |
| M5-15 | Sentinel-2-Presets NDMI, MNDWI, NDREI, SAVI | siehe Log |
| M5-22 Teile 1 und b | Bewertungs-Set, Suchtext, lexikalischer Arm mit Glossar | siehe Log |
| M5-28 | nodata-Regeln (float → NaN; Ganzzahl: Randwert, Verschieben bei Kollision, Klemmen), Runner 0.5.1 | siehe Log |
| M5-30b Teile 1, 2, 5, 6 | Übersicht und Mosaik bei kleinem Zoom, Messung, Budgets | #329–#332, #339 |
| — | Ausgabetypen nur, wo sinnvoll (§2 Punkt 9) | #333 |
| — | CI: Doku-PRs schnell; Pin `ubuntu-24.04`; Logger-Fix im Test; Backend in vier parallelen Teilen (6 statt 15 min) | #304, #322, #336, #338 |
| — | Weitere Nachträge | #316, #328 |
| M5-22 Teil c | Collection Search mit `q`, Zahl am Namen, Q51 | #337 |
| F11 | Quicklook für Sentinel-1 über Kacheln (`gcp_tps`) statt PNG | #340 |
| M5-30b Teil 7 | GLO-30 als Ersatz unter `min_zoom` von swissALTI3D (F7 = 1) | #341 |
| M5-35 | Prüfung Skalierbarkeit (`docs/plans/m5/m5-35-skalierbarkeit.md`), F1–F7 = 1, F4 mit Bedingung; Folgeaufgaben M5-36 bis M5-42 | #351 |
| M5-41 | Nachtrag `adr/0026` F3: pgvector ≥ 0.8.4, HNSW auf `halfvec`, gefiltert exakt bis 5·10⁴ Zeilen; Messung mit echten Embeddings in M5-23 | #354 |
| M5-32 | `adr/0034` Keys der Nutzer (angenommen 16.11.): Key verschlüsselt auf dem Server, an eine anonyme Browser-Sitzung gebunden (Schlüssel geteilt zwischen Cookie und Instanz), 30 Tage; Freigabe je Lauf für Jobs (Import `jobs → identity`); CDSE zuerst mit S3-Schlüssel; Cache je Nutzer, Ergebnis-Links ohne Key nur bei `results_shareable`; Szenen mit Key zeigen ihre eigenen Übersichten bei jedem Zoom (Voraussetzung Messpunkt M3), keine Pyramide aus Nutzer-Keys; Schloss statt „Account“; Rechtsrat vor öffentlichem Betrieb | #364 |
| UI-09 | Layer-Manager: „Zoom to layer“ links vom Download, Ladekreis in der Zeile entfällt, Rückfrage vor dem Entfernen (auch in der Seitenleiste); „Auto-scale“ setzt nur den Wertebereich zurück; Darstellung der terrain-Produkte am Operator (Slope `rdylgn_r`, Hillshade `greys_r` 0–100 %, Aspect `hsv` fest 0–360°), `adr/0035` angenommen | #366 |
| M5-36 | Grenzen je Host für alle Instanzen: `hosts.yaml`, ein Zähler je Host und Prozess für GDAL, HTTP und Zarr, Teilbudget je Instanz (`EARTHX_SOURCE_INSTANCES`), alle Lesestellen des `tiler` begrenzt; +30 % bei vielen gleichzeitigen Kacheln auf Hosts mit Grenze 6 hingenommen | #360, #365 |
| M5-09 | BEV ALS-DGM 1 m: Adapter `bev-atom`, 55 Kacheln Stichtag 15.09.2025, CC-BY-4.0 Processing, `min_zoom` 9 (darunter GLO-30), Host in `hosts.yaml`; Live-Smoke auf `main` grün (16.11.) | #362 |
| M5-17 | Stufe „gelistet“ für alle Datentypen; Handeinträge CORINE (39 EEA-Länder über `coverage_states`) und Landsat C2 L2, `tier: catalog`; Log-Zeile zu §2 Punkt 12 | #367 |
| M5-31 | `adr/0036` Radar-Verarbeitung angenommen 17.11.: Kette aus Earth Search anonym, GTC/RTC mit sarsen je Zielkachel, Vergleich über Bahnen erst nach RTC, Randmaske für alte Szenen; Folgeaufgabe DS-05e | #372 |
| M5-26 | `adr/0037` mehrere Eingaben und Vergleich angenommen 17.11.: Zweige mit Vergleichsschritt, Zielgitter einer Eingabe, Flag `comparison`, Swipe/Split zuerst; Folgeaufgaben M5-49 bis M5-54 | #371 |
| UI-10 | Hotfix weißer Bildschirm: `overviewMark.ts` wertete die Kachelsammlung von MapLibre als Liste aus (`tiles?.some`), seit UI-08; Auffangschutz (Error Boundary, Fehler in MapLibre-Ereignissen abgefangen, Meldung mit „Reload“) | #369 |
| UI-08 | Checkboxen nur über Kästchen oder Text; Kacheln erholen sich nach vorübergehenden Fehlern selbst; Statusbox im knappen Fenster über den Panels; Marke „Overview“ einheitlich bei Job-Ergebnissen, Pyramiden und Ersatz. Schmale Fenster bleiben vorgemerkt | #363 |
| M5-40 | Gelistete Einträge in Postgres (Migration 021, `categories.yaml`, `keywords`, `blocked.yaml`, Grabstein 410, Blättern), Data catalogue mit Gruppen je `category`, Nachladen, Filter-Popup mit × je Feld, „Filter by search panel“, Suchfeld (`q`), „Add dataset“ im Search panel | #356, #358 |
| M5-10 | Geländeoperator `terrain` (Neigung, Exposition, Schummerung) mit Operator-Art `focal`, bitgleich auf jeder CPU; Schritt „Terrain“ im Panel; gerechnete Bilder in allen Ansichten bis z0 (auf Pyramide bzw. Ersatz). Nahtlinie an Dateigrenzen in Kacheln akzeptiert (Otto 16.11.). GLO-30 unter z7 nach lokalem Bau 17.11. kontrollieren | #350, #357 |
| M5-37 | Zeiger, Plätze (Frist 30 s, Herzschlag 10 s) und Unterbrecher (3 Fehler → 5 min, verdoppelt bis 60 min) je Host in Postgres, Regeln als Funktionen in Migration 022; Pyramidenbau über den Aufseher, HEAD- und GET-Anfragen von GDAL gleich gezählt | #368, #373 (gemergt 17.11.) |
| — | CI-Draft: CI nicht auf Draft-PRs, erst nach „Ready for review“; `concurrency` mit Abbruch nur bei PRs, nie auf `main`; Pflicht-Checks unverändert; Nachtrag `adr/0002` §6. Nacharbeit nach Ready: PR zurück auf Draft; Merge erst, wenn der Lauf nach Ready grün ist | #374 (gemergt 17.11.); **rückgängig** auf Wunsch Otto 17.11. nachm. (CI wieder auf allen PRs, Abbruch nur bei PRs bleibt), CI-Draft-Revert erledigt 17.11. |
| M5-14 | Presets im „Quick processing“ (`composite_presets`, `step_presets`), SWIR mit B8A; einstellbare Parameter je Preset (Hillshade Azimut/Höhe mit Drehknopf wie QGIS und Zahlenfeldern, Slope Grad/Prozent); ruhiges Layout beim Ziehen; Download und „Process“ an angehefteten Preset-Ebenen liefern das gerechnete Ergebnis (Kanäle als Bänder, z. B. `swir_r`), Komposit als Farbbild im Ergebnis-Layer, echte Farbe vor Komposit | #370, #376 (gemergt 17.11.) |
| M5-11 | MeteoSchweiz nach `adr/0029`: Verweise mit `h5py` über `gateway`, `ReferenceStore` mit `If-Match`, `source_changed`, Chunk-Cache 64 MiB im `tiler`; zwei Datensätze `meteoswiss-daily-1km` (TabsD, TminD, TmaxD, SrelD) und `meteoswiss-daily-precip-1km` (RhiresD), Archiv 1961–2025, je 23 741 Items, Tagesgrenzen belegt (RhiresD 06–06 UTC, sonst 00–24 UTC), °C, CC BY 4.0, „Source: MeteoSwiss“ bzw. „(modified)“; `min_zoom 0`, `overview: own` (gemessen); `float64`-Wiedervorlage geschlossen; Band-Menü und Download für Datensätze mit Chunk-Verweisen | #377, #380 (gemergt 18.11.) |
| M5-56 | Große Auswahl (GLO-30 Russland): echte Gesamtzahl über `pgstac.context = auto` (Schwellen 100 000/100 000, TTL 1 h, geschätzt mit „≈“), Übersicht bei Crop and merge nur über ausgewählten Kacheln (bis 10 000 / 640 KiB), ein Ring über die Datumsgrenze, Process-Vorschau nach Ausschnitt. Offen vorgemerkt: Index im Look unter `min_zoom` zeigt ganze AOI, kein zweiter Versuch beim Anlegen der Footprint-Auswahl, `pyramid-every-level.cjs` veraltet (→ M5-61). Aus der Fassung 3.3: Befunde Otto 18.11.: nur 300 Treffer („300/300“) für ganz Russland, unter z7 ganz Russland aus der Pyramide, über z7 keine Kachelanfrage (kein `mosaic`, kein `scene-order`); Ursache `pgstac.context` aus (kein `numberMatched`), Folge: Daten über z7 nur, wo eine der 300 Kacheln liegt; Vorgabe: Übersicht bei Crop and merge unter `min_zoom` nur über der Fläche der ausgewählten Kacheln (∩ AOI), auch bei abgewählten; Footprint-Auswahl bis 10 000 IDs / 640 KiB (darüber ganze AOI); Messung und Entscheidung siehe §11; echte Gesamtzahl bei mehreren Datensätzen → M5-57; Browserprüfung Otto ok | #381 (gemergt 18.11.) |
| M5-59 | Bänder im Data catalogue als Tabelle Band, Description, Unit (ohne Einheit „–“), Registry-Pflichtfeld `band_descriptions`, Collection `earthx:bands`, alle Datensätze befüllt inkl. MeteoSwiss und WorldCover `map`, Onboarding-Checkliste Punkt 12 | #382 (gemergt 18.11.) |
| M5-19 | Harvest-Kern: Tabellen (Migrationen 024–028, 030), Quellen-YAML, Abrufe über `gateway` mit Plätzen je Host, `harvest`-Befehl, STAC- und CKAN-Extraktor, Link „Source“ (F1, F12: `extras:uri`/`guid`, Metadaten-Endpunkte ausgeschlossen), Keyset-Paging, Budget je Lauf, Sperrfrist, Wiederholung bei Timeout/5xx, robots-Ausnahme mit Beleg (opendata.swiss, GovData), Hash ohne flüchtige Felder, Extraktor-Version mit Neuauswertung; Läufe: opendata.swiss 16 216, GovData 168 882, Earth Search 9, FSDI 515; Abnahme §7.3 belegt (inkrementell: von ~1 300 angefassten 25 echte Änderungen). Offen: data.gv.at (angehalten), Regel Nicht-Geodaten und Funde ohne Ausdehnung (M5-20), Tabellengröße ~1 GB (M6). Aus der Fassung 3.3: `robots.txt` (18.11.): opendata.swiss = CKAN-Standard (`Disallow: /api/`, `Crawl-Delay: 10`), www.govdata.de `Disallow: /`; Ausnahme je Quelle nur für die Metadaten-API (Feld `robots_exception`, Beleg Handbuch opendata.swiss geprüft; GovData über `ckan.govdata.de`, dessen `robots.txt` Stand 18.11. noch offen), `Crawl-Delay` gilt immer. Lauf opendata.swiss 18.11.: nach 102 Seiten (10 099 Funde, 4 561 ohne Ausdehnung, 146 MB) `429`; danach 429-Behandlung (Backoff bis 30 min, nach 60 min `interrupted`), Fortsetzen über mehrere Läufe (Migration 027); `max_pages_per_run` (opendata.swiss 40 Seiten ≈ 4 000 Pakete ≈ 56 MB, voller Durchgang ≈ 5 Läufe, einer je Tag; GovData `null` bis zum ersten Lauf), Sperrfrist nach `rate_limited` bis `Retry-After` bzw. 00:00 UTC, `--measure` im Budget; A10: auch inkrementelle Läufe fortsetzbar (ersetzt den `listing_moved`-Abbruch aus A8 für inkrementelle Läufe). Offen für M5-20/M5-24: `gone` bei mehrtägigem Durchgang (Abgleich der IDs am Ende); F10 (`fl`) erst nach Messung. Betrifft nur den Harvest, nicht die Nutzer; nie über mehrere IPs umgehen. Antworten 17.11.: F1, F2, F5–F8 = 1; Funde ohne räumliche Angabe kennzeichnen statt verwerfen | #375, #379 (gemergt 19.11.) |
| M5-58 | Laufende und vorläufige Daten allgemein (`adr/0038` Entwurf): Pflichtfeld `updates` je Eintrag, `earthx:state` je Item/Asset (vorläufig/endgültig), Änderungserkennung je Datei (Listen-Hash, Item-Hash, `file:checksum`, ETag, Last-Modified), höherer Stand gilt, vorläufig ersetzt nie endgültig, `expires` je Asset (Migration 029, 031); MeteoSchweiz: Tages-Items vorläufig (RprelimD als Band RhiresD), Monats-Items `-last` und Archiv endgültig, Tooltip „Provisional values“, `state` im `recipe.json`; fehlende Datei wird übersprungen (F10 = 1). Aus der Fassung 3.3: Plan `docs/plans/m5/m5-58-laufende-daten.md`; Antworten 18.11. F1–F9 = 1 (Kennzeichnung nur `limitations` + Tooltip, gleiche Item-ID mit neuem `v=`, zwei Stände, Takt von Hand, `adr/0038`, PR 1 Mechanismus / PR 2 MeteoSchweiz, Übernahme per bedingtem HEAD); F5 belegt: RprelimD 06–06 UTC (ProdDoc_RprelimD); `rprelimd` → RhiresD nach 3–6 Wochen; danach je Datensatz prüfen (z. B. Sentinel-1 NRT/Fast-24h) | #383, #385 (gemergt 19.11.) |
| M5-38 | Pyramiden: `extend` und `sweep` unter Sperre (Lease-Zeile, Migration 019 `earthx_overview_upkeep`) | #353 |
| M5-39 | `adr/0033` Freigabe gelisteter Einträge (drei Ebenen, Warteliste, Sperrliste mit Grabstein, neue Felder) | #352 |
| DS-04d | Sentinel-1 in Radargeometrie (ohne CRS/Geotransform, GCPs bleiben, `mask.tif` wie M3-18, Mosaik je Durchgang mit `line_times`, eigene Fehlerarten, `reprojection: false`, Ergebnis-Layer pixelgenau je Slice, Einheit „DN“ nur im Data catalogue, Runner 0.5.2) | #343 |
| F12 (DS-04) | Originale von Sentinel-1: dritter Satz in `limitations`, `limitations` als Abschnitt in `ATTRIBUTION.txt`, keine Beschriftung im Frontend | #344 |
| M5-55 | Link „Source“ der vollen Einträge auf Viewer bzw. Download-Seite statt API-Adresse (§2 Punkt 12) | #386 (gemergt 19.11.) |
| M5-61 | Tests aufräumen: volle Suite in der Session 20:17 → 14:33 min, Integrationstests 1 935 → 688 s, Temp nur fehlgeschlagene und letzter Lauf, eigene Test-Datenbanken je Lauf, Katalog einmal je Worker, Logger-Wächter, Pyramiden-Test über vergebene Zeitpunkte, `job_bench.py` repariert; fehlende Kachel z8 war kein Produktfehler. Aus der Fassung 3.3 (Auftrag Otto 18.11.): Laufzeit messen (`--durations`), langsame und doppelte Tests kürzen bzw. zusammenlegen, keine Migrationskonflikte zwischen Checkouts, kein Neustart mitten im Lauf, Teardown-Fehler `test_worker.py`, Befund #299; Ziel: volle Suite deutlich unter 20 min in der Session, keine Abbrüche bei parallelen Läufen, keine Abdeckung verlieren | #387, #389 (gemergt 20.11.) |
| M5-62 PR 1 | Klassenlegende Backend: `band_classes` (optional; Wert und Name, Farben `file` \| `stac` \| `palette` tab20), Kachelfarben, STAC `classification:classes` und Export aus einer Liste; Farbtabelle in der GeoTIFF, Namen und RAT in `.aux.xml` im ZIP, Klassen in `BANDS.txt`; QGIS-Prüfung Otto ok. Aus der Fassung 3.3 (Auftrag Otto 19.11.): alle Datensätze mit Klassenwerten (zuerst WorldCover 2020/2021, später z. B. CORINE), Namen Englisch nach der Produktdokumentation, keine eigene Legendendatei, Klassen nur, solange die Werte unverändert sind, Migration falls nötig ab 035 (032–034 von #388 belegt); Plan `docs/plans/m5/m5-62-klassenlegende.md`, Antworten 20.11.: F1 = 1, F2 = 3 (Namen von Otto), F3 = 1, F4 = 1, F5–F7 ja, F8 „Classes“ | #390 (gemergt 20.11.) |
| M5-20 PR 1 und Nachträge | `discovery report` mit Stapel, Bericht, Stichprobe und Freigabedatei; Enrich (Ausdehnung in Stufen Geometrie → Ortstext → Herausgeber → Staat; Ortsverzeichnis mit Gemeinden aus swissBOUNDARIES3D und GeoNames); Regel Nicht-Geodaten (Statistikämter, schwache Geo-Signale, „Karte/Plan“, Software); Dedupe nur über eindeutige Schlüssel ohne Ketten; Lizenzkatalog `terms.yaml`, `harvest-grants`; Zugangsart `page` (Migration 034); Link nie Sammelseite oder Schnittstelle; Tests für ausgelieferte Freigaben statt „leer“ | #388, #397, #399, #401 und zwei Test-Nachträge (gemergt 21.–23.11.) |
| — | Erste Freigaben gelisteter Einträge: FSDI (Stapel 1, 305), opendata.swiss (Stapel 3, 7 748), GovData (Stapel 5, 94 258) | Freigabe-PRs 21.–23.11. (#400 u. a.) |
| M5-42 | Suche über gelistete Einträge: lexikalischer Index für alle veröffentlichten Einträge (Migrationen 035, 036), Titel zusammengelegter Dubletten am Haupteintrag, Ortsnamen aus `place_names.yaml`, Hash-Vergleich in Postgres (ohne Änderung 0,9 s statt 11,8 s), quadratische Rangberechnung behoben; Bewertungs-Set CLC/LS aktiv (Deutsch 15/19, Englisch 41/42); lokal 102 313 Zeilen; Vektorarm bleibt M5-23; Plan `plans/m5/m5-42-suche-gelistete.md`; Vorgänger „lexikalische Suche indexfähig“ (M5-35 Befund B7), Voraussetzung war M5-41 | #402 (gemergt 23.11.) |
| M5-65 | Suche mit Fläche schneller: Migration 038 (Spalte `geometry` für volle Zeilen, Schlüssel `dataset_id COLLATE "C"`), gelistete und volle Zeilen als zwei flache Abfragen, Start bei den Footprints (GiST-Index von `earthx_listed_entry.footprint`) für breite Wörter mit kleiner Fläche, sonst beim Text (zwei begrenzte Zählungen statt Planer), Rangsumme in fester Reihenfolge, leere Klausel „Zahlen von Namen“ gestrichen; bei 10⁵ „Götterbaum“ mit Fläche 0,01° 627 → 98 ms, Zürich 810 → 149 ms, seltene Wörter etwa +10 ms; Treffermengen und Bewertungs-Set unverändert; Plan `plans/m5/m5-65-suche-mit-flaeche.md` | Draft-PR (24.11.) |
| — | Doku-Runde Fassung 3.1, zugleich Nachweis des Doku-Pfads der CI | Doku-PR 11.11. |
| — | Doku-Runden Fassung 3.2, 3.3 und 3.4 (mit Anhang ans Entscheidungslog) | Doku-PRs 16.11., 18.11., 23.11. |

### 6.2 Offen

Stufe A: ohne Plan-Datei, direkt umsetzen. Stufe B: Plan unter `docs/plans/m5/` (UI unter `docs/plans/vp3/`) mit Fragen im Draft-PR, Umsetzung nach Ottos Antworten im selben PR. Stufe C: nur Entwurf (ADR, Bericht).

**In Arbeit (23.11.2026):**

| Aufgabe | Inhalt | Stand |
|---|---|---|
| **M5-30b** | Umsetzung `adr/0032` – abgeschlossen mit #355 (15.11.); GLO-30-Pyramide lokal gebaut 17./18.11. | erledigt |
| **M5-62 PR 2** | Klassenlegende Frontend (#391): Tabelle Value \| Class \| Colour im Data catalogue, Knopf „Classes“ mit Popover statt Feld „Colormap“, `BANDS.txt` aus dem Browser mit Klassen; F9 = 1 (Klassen je Eingabe im Rezept, Worker schreibt Klassen und Farbtabelle ins Ergebnis, neuer Hash nur mit Klassenband); A17/A18 angenommen | wartet auf „fertig“ nach `main` holen, dann Merge |
| **M5-60 PR 1** | Darstellung je Band, Backend (#396, `docs/plans/m5/m5-60-darstellung-je-band.md`): Look je Band (Farbskala, fester/gemessener/Perzentil-Bereich in physikalischen Werten), Herkunft Hand > Quelle (STAC `renders`, `raster:bands.statistics`) > Standardbild/H1 > Regel nach Einheit (% 0–100, °C `rdbu_r`, mm `blues`, m `terrain`) > `viridis`; Sentinel-1 `greys_r`; gemessener Bereich einmal je Ansicht/Band, gecacht, nie je Kachel; F1–F7 = 1. Aus der Fassung 3.3: Ziel: ein einzeln gewähltes Band erscheint nicht grau; für alle Datensätze befüllen, wo sinnvoll (z. B. MeteoSwiss `SrelD` 0–100 %, Sentinel-2-Einzelbänder); Rangfolge Hand > Preset > Look (`adr/0035`) bleibt; Herkunft #380 H1 (dort Option 1: gleiche Einheit wie Standardband → gleiche Skala); Voraussetzung M5-59 und M5-11 PR 2 gemergt | wartet auf „fertig“ nach `main` holen, dann Merge; PR 2 (Frontend, mit farbigem Histogramm) nach M5-62 PR 2 in neuer Session |
| **M5-20 Rest** | Nachtrag (Stufe A, Sonnet, hoch): Links auf Schnittstellen (223 bei GovData: GeoNetwork, metaver), 224 LfULG-Funde ohne klaren Wartegrund, Dedupe über Collection-ID in einer Distribution (WRRL-Flussgebiete → FSDI), „PRTR/Betriebsstätten“ als Geo-Signal; dazu Nachträge in `adr/0033` §5, §7, §11 (Link nie Sammelseite oder Schnittstelle, Zugang und `page`, Funde ohne Herausgeber warten, Ausdehnung in Stufen, neue Lizenz-Einstufung) | jetzt starten |

**M5-30b im Einzelnen** (Merge jeweils mit Merge-Commit):

| Teil | Inhalt | PR | Stand |
|---|---|---|---|
| 1, 2, 5, 6 | Messskript, Budget je Kachel, Vorarbeiten | #329–#332 (über #339) | gemergt |
| 7 | GLO-30 als Ersatz unter `min_zoom` | #341 | gemergt |
| 3a | Auswahl-ID (Backend), Migration 017 | #335 | gemergt 14.11. |
| 3b | Auswahl-ID im Frontend, 64 fällt, Rückfall 40 nach Lage; Ersatz in der Ansicht (Fehler behoben), Umrisse aller ausgewählten Szenen (Schnitt bei 40 entfernt), Ladesymbol auf der Karte über dem Kompass nach 0,6 s und in der Zeile, höchstens 2 gleichzeitige Mosaik-Kacheln je Prozess | #345 (Basis 3a) | gemergt 14.11. (mit Ladeanzeige „Loading data“ und Statusbox zwischen den Panels) |
| 8a | Lesen mit 0,25 s je Host, Kern der Pyramide | #346 | gemergt 14.11. |
| 8b-1 | Tabellen (Migration 018), Bauwunsch aus `materialize`, Präfix `overviews/` mit 31 Tagen | #347 (Basis #346) | gemergt 14.11.; lokal einmal `objectstore-init` |
| 8b-2 | Bau im eigenen Faden, zwei Kindprozesse, Upload; band-select auf „uint16“ | #348 (Basis #347) | gemergt 14.11.; `--force` bestätigt nicht, ein PR |
| 8b-3 | Pflege: Bestätigung durch unveränderten `materialize`-Lauf, Verlängerung bis 31 Tage − 12 h, Neubau abgelaufener, Aufräumen `proto-*` | #349 (Basis #348) | gemergt 14.11.; Auslegungen §8.10 bestätigt; lokale Prüfung (GLO-30, ~3,6 h) offen |
| 9 (+4, 10) | Kachelroute aus der Pyramide (GLO-30 unter z7, WorldCover unter z5, swissALTI3D unter z7 aus der GLO-30-Pyramide nur über der Schweiz), `min_zoom` DEM 7 und WorldCover 5, Regel „Pyramide verlangt `min_zoom` ≥ 1“, Thread-Pool (Warten außerhalb des Pools, eigenes Tor für Pyramidenkacheln), Browser-Test #319 F13, Nachträge | #355 | gemergt 15.11. (inkl. Footprint-Auswahl für Suchergebnisse und Szenenansicht, Robustheit des Baus, Migration 020) |

Reihenfolge: alle Teile gemergt; M5-30b abgeschlossen 15.11.
**Stand lokaler Bau (15.11.):** `objectstore-init` erledigt. Erste Bauten auf pr-355 scheiterten alle mitten im Lesen ohne Logzeile (GLO-30 bei 8 %, WorldCover 2020 bei 9 %, WorldCover 2021 bei 51 %, `failure_kind = unknown`); während der Läufe lief bei Otto ein schwerer anderer Prozess → Speichermangel wahrscheinlich. Stand #355 (15.11. nachm.): Netzfehler werden als `source_unreachable` erkannt, bis 4 Versuche mit Backoff und Retry-After (≥ 0,25 s je Host), unlesbare Basiskachel ausgelassen (Tabelle `earthx_overview_omitted`, Migration 020), stündlicher Nachbau über die Sperre aus #353; Ausfall ab > 5 % und > 3 fehlenden Basiskacheln; `source_unreachable` nach 1 h bis 3-mal automatisch wiederholt; gleiche `version` bei WorldCover 2020/2021 gewollt (ETag des gemeinsamen Gitters); GLO-30 dauert eher 6–7 h. Vorfall: ein Subagent baute WorldCover 2020 am `gateway` vorbei gegen die echte Quelle – nicht erlaubt, im Log festzuhalten. #355 fertig gemeldet 15.11. (Nachbau-Tests rot gegengeprüft; Host-Sperre `earthx_overview_host` in Migration 020, Lease nur für den Nachbau, Bau hält Hosts über seine Zeile – ok Otto; Vorfall im Log, Arbeitsdateien gelöscht). Lokal 15.11. abends: WorldCover-Pyramiden ohne Last durchgelaufen. Browserprüfung: Crop and merge bis z0 ok, Suchergebnisse und Szenenansicht verschwinden unter `min_zoom` → in #355 neue Footprint-Auswahl (Hash der Treffer, 1–N) für diese beiden Ansichten (Otto 1.1); Vorschau und Index-Darstellungen unter `min_zoom` (auch in Crop and merge und angehefteter Ebene) schließt M5-10 PR B (2.1, 3.1). Merge nach kurzem Blick auf `earthx_overview_omitted` und Browserprüfung WorldCover unter z5; danach Bescheid an M5-40 (main holen, Konflikte) und M5-10 (PR 2). GLO-30 lokal gebaut 17./18.11., Browserprüfung 18.11. ok bis auf zwei Befunde (Russland: „Select all“ zeigt nicht alle Umrisse; Crop and merge: ab einer Zoomstufe hineingezoomt keine Daten) → Fehleraufgabe M5-56; danach GLO-30 unter z7 (auch Neigung aus M5-10) im Browser ansehen; scheitert der Bau, kleine Folgeaufgabe. Nächster Schritt Otto ohne Last: `git pull origin pull/355/head`, `docker compose build`, `up -d`, `materialize esa-worldcover-2021` und `-2020`, `docker stats`, SQL-Abfragen (`earthx_overview`, `earthx_overview_omitted`); danach GLO-30 über Nacht. Session baut in #355: Fehler des Kindprozesses mit Art, Grund, Basiskachel und Exit-Signal ins Log; Wiederholen mit Backoff (429/503, Retry-After); unlesbare Basiskachel auslassen und stündlich nachbauen; gleiche `version` bei WorldCover 2020/2021 klären. Migration: 019 ist von M5-38 (#353, gemergt 15.11.) belegt → #355 holt main, nimmt 020 und nutzt die Sperre aus #353.
**Für Otto nach dem Merge von #346–#349 (vor dem Merge von Teil 9):**
1. Einmal `objectstore-init` (vermutlich `docker compose run --rm objectstore-init`; Befehl in README bzw. M5-30-Plan §8.10 prüfen). Ohne die neue Regel für `overviews/` startet der Worker nicht.
2. Lokale Prüfung über Nacht: `docker compose up`, dann `docker compose run --rm materialize cop-dem-glo-30` (Bau ~3,6 h, ~1 GB). Morgens im Worker-Log „overview build ended“ ohne Fehler; Abfrage `SELECT dataset_id, status, progress, attempts, failure_kind FROM earthx_overview;`; Objekte unter `overviews/cop-dem-glo-30/…`; `materialize` unverändert wiederholen → nach der stündlichen Runde „overview pyramids extended“. Genaue PowerShell-Befehle in M5-30-Plan §8.10. Befunde gehen in Teil 9.
Antworten zu 8b-2 (an die Session geschickt 13.11., Umsetzung nach #345/#335): alle vier Option 1; der regelmäßige Lauf von `materialize` kommt später vom Prozess `harvester` (M5-24), bis dahin von Hand. Auslegungen #341: Ausdehnung = gewählter Datensatz und „ohne schreibbare Quellenangabe kein Ersatz“ bestätigen; „höchstens 500 Items je Ersatzkachel“ klären lassen (Budget 32 Dateien und 4 s gilt auch dort).

**Noch nicht gestartet:**

| Aufgabe | Inhalt | Stufe | Modell, Effort | Hängt ab von |
|---|---|---|---|---|
| **UI-07** | Reiter im Processing-Panel (`docs/plans/vp3/ui-07-processing-reiter.md`) | B | Opus, hoch | M5-31, M5-26, M5-32 entschieden |
| **M5-43** | Postgres-Image `postgis/postgis:16-3.7` plus pgvector ≥ 0.8.4 (eigenes Dockerfile) für Compose, CI und Cloud-Umgebung; ersetzt das nicht mehr gebaute `16-3.4`; CI baut das Dockerfile im Job mit Layer-Cache, Bauzeit messen; Cloud-Setup baut pgvector (gilt erst für neue Sessions). **Erlaubnis Otto für `.github/` und Setup der Cloud-Umgebung nötig** | B | Opus, mittel | M5-41 gemergt; vor M5-23 |
| **M5-44 bis M5-48** | Umsetzung `adr/0034` nach §10 dort (je höchstens zwei PRs), für drei Anbieter zugleich (Otto 16.11.): Copernicus Data Space, CORINE (Copernicus Land Monitoring Service, API-Schlüssel des EU-Login-Kontos) und Landsat C2 L2 (eigener AWS-Zugang für Requester Pays, Kosten trägt der Nutzer, vor dem Freischalten klar angezeigt); CORINE und Landsat werden damit von gelistet zu vollen Datensätzen. M5-44 erster Commit zusätzlich: Nachtrag zu `adr/0034` §5/F4 für die Key-Arten von CLMS und AWS; M5-44 erster Commit mit „Nachtrag Otto“ für `ENTSCHEIDUNGEN` §1/§3 im Wortlaut aus §12 und den übrigen Nachträgen; Content Security Policy (M5-45) und keine Weitergabe von Kopfzeilen bei Weiterleitungen in `gateway` (M5-46) vor dem ersten Key; Kacheln mit Key (M5-47, braucht M3); Jobs mit Key (M5-48, Voraussetzung für M5-31 mit CDSE-Daten) | B | Opus, hoch | Otto: Konten bei CDSE, EU Login (CLMS) und AWS; Messpunkte M1–M4 aus `adr/0034` §14 und entsprechende für CLMS und AWS |
| **UI-12** | Größerer UI-Lauf, gesammelt (Otto 16.11.): (1) Zeile „Keywords“ in den Details des Data catalogue entfällt, Schlagworte bleiben in Registry, API und Suchtext (früher UI-11); (2) schmale Fenster gesammelt (u. a. Statusbox überdeckt bei 360 px den Kompass). (3) Ladeanzeige bzw. Statusbox oben nicht mehr zwischen den Panels verschieben, sondern fest an einem Ort, den kein Panel je verdeckt (nur der Data catalogue darf darüber), Ort schlägt die Session vor (Otto 17.11.). (4) Quick processing mit Seiten: je Seite so viele Einträge, wie ohne Scrollen passen, Seitenpfeile wie bei „Datasets“ (§2 Punkt 9, Otto 17.11.). (5) AOI: Wer „Rectangle“ gewählt hat und dann doch über die Ortssuche einen Ort sucht und findet, dem verschwindet das Rechteck-Werkzeug (Otto 18.11.). (6) AOI „Point“ erzeugt immer einen echten Punkt statt eines Rechtecks (§2 Punkt 9, Otto 18.11.). Weitere UI-Punkte kommen hier dazu | B | Opus, mittel | Otto gibt den Start frei |
| **M5-49** | Swipe und Split für zwei beliebige Ebenen, eigener Code ohne neues Paket (`adr/0037` F7, F11 Schritt 1) | B | Opus, mittel | `adr/0037` gemergt |
| **M5-50** | Vergleich im Kern bei gleichem Gitter: zwei Zweige, ein Vergleichsschritt (Differenz, Verhältnis, Log-Ratio dB, normierte Differenz, freier Ausdruck), Statistik beider; Flag `comparison` und Regeln in der Registry (`adr/0037` F1, F3, F4) | B | Opus, hoch | M5-49 |
| **M5-51** | Raster angleichen: Zielgitter einer Eingabe im Rezept, nur gemeinsame Fläche gültig, nodata nach M5-28 (`adr/0037` F2) | B | Opus, hoch | M5-50 |
| **M5-52** | Vergleich im Processing-Panel (Zweige, Zielgitter vorgeschlagen, Vorschau als „Preview“) (`adr/0037` F6) | B | Opus, mittel | M5-51 |
| **M5-53** | WorldCover als Maske für andere Datensätze (kein Vergleich 2020 gegen 2021) (`adr/0037` F3, F12) | B | Opus, mittel | M5-50 |
| **M5-54** | Ältere Stände von swissALTI3D laden (Voraussetzung für Höhenvergleich zweier Stände) (`adr/0037` F11) | B | Opus, mittel | — |
| **DS-05f** | Georeferenzierter Download und Mosaik/Vergleich nach `adr/0036` §12: Download nach GTC und RTC; Mosaik über Durchgänge derselben Bahn auch nach GTC; über verschiedene Bahnen nur nach RTC | B | Opus, hoch | DS-05e |
| **DS-05e** | Radar-Kette nach `adr/0036`: Annotation über Registry-Regel aus Earth Search, Rauschabzug, σ⁰/γ⁰, GTC/RTC mit sarsen je Zielkachel (Lizenzen der 19 Pakete vorher), EGM2008 im Image, UTM 20 m (10 m wählbar); georeferenzierter Download nach GTC/RTC, Vergleich über Bahnen erst nach RTC; alte Szenen vor IPF 2.90 mit Randmaske | B | Opus, hoch | `adr/0036` gemergt; Schnitt laut ADR |
| **M5-34** | Normalize im Processing (Otto, 14.11.): Bereich „From“ aus den Daten wählen – Min/Max, Perzentile (z. B. 2–98 %, 1–99 %, eigene), dazu das Histogramm der Verteilung zum Wählen; Fragen im Plan: Werte aus der Vorschau-Statistik (schnell, näherungsweise, als Zahlen ins Rezept) oder exakt im Job (wie NM4-71); Bedienung wie „Scale“ (absolute/percentile) in der Seitenleiste. Dazu (Otto, 14.11.): „Bands to process“ heißt „Bands in output“; Normalize erzeugt wie Band math ein neues Band mit vorbelegtem, änderbarem Namen (z. B. `VV_norm`), das sich zu „Bands in output“ hinzufügen lässt, das Original bleibt wählbar; gilt für alle bandverändernden Schritte (Otto, 14.11.; Bezug `adr/0020`, `adr/0028`). Befund: Vorgabe „From“ −1000..1000 passt nicht zu DN von Sentinel-1 | B | Opus, mittel | M5-30b abgeschlossen |
| **M5-33** | swissALTI3D genau verorten (Otto, 13.11.): offizielle Korrekturdatei von swisstopo (CHENyx06) statt Näherung, damit die Lage nicht ~1 m abweicht; Lizenz der Datei klären, Datei im Image (PROJ ohne Netz zur Laufzeit, B8), gilt für Karte, Zuschnitt und Jobs; `limitations` neu: Satz zur Ungenauigkeit entfällt, neu „When zoomed out, the map shows Copernicus DEM GLO-30 instead.“ Gilt auch für BEV (EPSG:3035/MGI) prüfen. Dazu: Download und Zuschnitt im Originalformat (LV95) prüfen bzw. sicherstellen; Quellenzeile zeigt „©swisstopo“ und „©swisstopo (modified)“ gleichzeitig – nur eine Angabe, passend zum Gezeigten | B | Opus, mittel | M5-30b abgeschlossen |
| **M5-57** | Echte Gesamtzahl auch bei Suche über mehrere Datensätze (Summe `numberMatched` je Quelle, Earth Search eigene Zahlen), §2 Punkt 9 „Trefferzahl ehrlich“ | B | Opus, mittel | M5-56 gemergt (erfüllt 18.11.) |
| **M5-20 PR 2** | Kandidaten des vollen Wegs und `discovery propose` (höchstens 20 je Quelle und PR, Probe nach `adr/0031` §4.4), Verify in der Stichprobe; Voraussetzung für Abnahme §7 Punkt 2 und für V1–V9; aus dem ursprünglichen M5-20 (Fassung 3.3) zusätzlich: Skript und Anleitung für Ottos lokalen Lauf (`adr/0025` Schnitt 5, §6.7) | B | Opus, hoch | M5-20 Rest |
| **M5-63** | Adapter data.gv.at über piveau hub-search (76 729 Datensätze laut `count` am 19.11.; `/api/hub/search/search`, `datasets/{id}`, OpenAPI unter `/api/hub/search/`); Netiquette: keine technischen Grenzen genannt, Rechteinhaber nennen, Kontakt im User-Agent; Paging-Grenzen erst messen; Fixtures von Otto (Quelle aus Session nicht erreichbar) | B | Opus, mittel | neu 19.11., nach M5-20 PR 1 |
| **M5-64** | QGIS-Stil bei jedem Export (Otto 20.11.): neben jeder Rasterdatei im ZIP eine `.qml` gleichen Namens (QGIS lädt sie automatisch), Darstellung wie in der App: ein Band Farbskala mit Min/Max, RGB je Band Stretch, Klassen Werte/Farben/Namen aus `band_classes`; gilt für alle Exportformate mit Rasterdateien | B | Opus, mittel | M5-60 PR 2 und M5-62 PR 2 gemergt |
| **M5-66** | Suche bei breiten Wörtern: Kategorie- und Regionsfilter in die SQL-Abfrage, dann nur die besten 1 000 je Arm ranken, Trefferzahl nach M5-40 F4 (genau bis 10 000, darüber weggelassen) (M5-42 F5 = 1, Otto 23.11.2026; heute 1,4–2,9 s bei 10⁵); dazu `catalog-load` ohne Änderung je Schritt messen und kürzen (bei Otto 30,8 s mit ~102 000 gelisteten Einträgen) | B | Opus, mittel | M5-42 gemergt |
| **V1–V9** | Vorarbeiten für das automatische Onboarding (`adr/0031`), danach richtet Claude im Planungs-Chat die geplante Aufgabe ein | B | laut `adr/0031` | laut `adr/0031` (in der Liste nach M5-20) |
| **M5-16** | WorldCover: Klassenanteile in der AOI aus der Ergebnis-Statistik (`adr/0030` F9) | B | Opus, mittel | — |
| **M5-23** | Suche Teil 2 (`adr/0026` §6 Schritte 3 und 4): Vektorarm, Modellwahl am Set, eigene Dockerfile-Stufe, RRF; Entscheidung pgvector ja/nein neu nach M5-35 (viele gelistete Einträge); Suchfeld und Filter kommen schon mit M5-40 PR 2, M5-23 bringt den Vektorarm dahinter; Messung mit echten Embeddings (Skript aus M5-41); schließt die Lücke Deutsch (Recall@5/MRR@10 nach Teil c: 0,727) | B | Opus, hoch | M5-43 gemergt |
| **DS-05a** | `sar_db` mit Wertetabelle, `sar_backscatter`, Schritt-Presets „VV dB“/„VH dB“ | B | Opus, hoch | M5-14 gemergt |
| **DS-05c** | Komposit „Dual-pol RGB“ | A | Sonnet, mittel | DS-05a gemergt |
| **M5-21** | Extraktoren GeoSphere, INSPIRE-ATOM, STAC Index als Register (`adr/0025` Schnitt 6) | B | Opus, mittel | M5-20 gemergt |
| **M5-24** | Prozess `harvester` als Takt, Health-Checks, „Last checked“ (`adr/0025` Schnitt 7, §6.6); Vorgabe Otto 18.11.: für jeden Datensatz wird geklärt und festgehalten, wann bzw. wie oft `materialize` laufen soll (Aktualisierungstakt der Quelle), Umsetzung legt die Session vor | B | Opus, mittel | M5-20, M5-37 gemergt |
| **DS-05b** | Speckle-Filter Boxcar und Lee auf `focal` | B | Opus, hoch | M5-10, DS-05a gemergt |
| **DS-05d** | σ⁰-Kalibrierung, danach RVI; erweitert nach `adr/0036` F6: Azimut-Rauschen, Wahl β⁰/σ⁰/γ, Ort der Annotation per Registry-Regel, `sar_ipf_min` als Randmaske für Szenen vor IPF 2.90 | B | Opus, hoch | DS-05a gemergt |
| **M5-25** | JSON-LD und Sitemap für die Datensätze | B | Opus, mittel | — |
| **M5-27** | Abnahmebericht M5 (§7) | C | Opus, hoch | alle übrigen |

**Vorgemerkt, ohne Nummer und ohne Termin:** Zeitreihen-Werkzeug (Otto 18.11., nicht unbedingt M5): Punkt anklicken, Pixel darunter, Zeitreihe aller Zeitschritte anzeigen und exportieren (z. B. MeteoSwiss); vorher ADR „Zeitreihen am Punkt“ (Stufe C) mit Stand der Technik, weil naiv z. B. MeteoSwiss 23 741 Tageschunks ≈ 8,4 GB je Pixel bedeutet; wartet (Otto 18.11.); gilt für Zarr, NetCDF und COG gleichermaßen (Otto 18.11.); entscheidend ist nicht das Format, sondern die Zahl der Anfragen je Zeitreihe (Chunks über die Zeit → wenige; ein Chunk bzw. eine Datei je Zeitschritt → eine Anfrage je Zeitschritt, z. B. Sentinel-2-COGs ~70 je Jahr machbar, MeteoSwiss 23 741 nicht ohne Kopie/Begrenzung; ARCO-ERA5 1 h × Erde); ADR legt je Datensatz fest, was direkt geht und was als Job oder mit Begrenzung; angeboten wird das Werkzeug nur bei Datensätzen, wo es Sinn macht (Fähigkeit in der Registry, was nicht geht, erscheint nicht – §2 Punkt 7; Otto 18.11.); `scripts/tile-bench/job_bench.py` veraltet, bricht ab (Befund M5-36); Für M6 (aus M5-35): `host_cap` je Host und `global_cap` je Pool in der Job-Queue; Egress-Proxy mit Grenzen je Ziel, Verbindungs-Pooler für Postgres, CDN, Lasttest mit N Instanzen je Prozesstyp (`architekturplan.md` 12.4); Sentinel-1 2019: Datatakes mit zwei Fassungen derselben Strecke (NRT-3h und Fast-24h) erscheinen in der Zeitleiste als ein Durchgang (Befund #343 §12.8); Thread-Pool: wartende Mosaik-Kacheln belegen Threads des gemeinsamen Pools (M5-30 Plan §8.7, Lösung mit Teil 9); Browser-Check band-select auf „uint16“ (mit 8b-2); `scripts/tile-bench` fängt die ID-Suche beim Anlegen einer Auswahl nicht ab; Browser-Check many-scenes wartet seit dem Ladesymbol länger (Ursache im Software-Rendering vermutet, mit GPU nicht geprüft); Tests aufräumen (Zeitmessung im Test des Pyramidenbaus wackelt, 0,31 s statt > 0,4 s, Befund M5-11; pytest-Temp-Verzeichnisse, eindeutige Namen der Worker-DBs, Verursacher der verstellten Logger, gemeinsame Test-Datenbank startet mitten im Lauf neu bzw. hat Migrationskonflikte zwischen Checkouts, Teardown-Fehler in `test_worker.py` nur im gemeinsamen Lauf); TPS-Cache, falls Sentinel-1 träge ist (M5-30b F7);  BSH; W3 nach M6; Runner-Image 0.5.1 bei Gelegenheit; schlankere PR-Läufe (Vorschlag in #338; Teil davon mit CI-Draft 17.11.); Browser-Skripte reparieren (Befund #299).

### 6.3 Reihenfolge

- Höchstens **zwei Sessions der Stufe B** und höchstens **zwei mit Frontend** gleichzeitig; Stufe A und C zählen nicht mit.
- Ist ein Platz frei, startet die nächste Aufgabe dieser Liste, deren Abhängigkeiten erfüllt sind:
  Erledigt aus der Liste (23.11.): M5-10, M5-36, M5-09, M5-37, M5-40, M5-17, M5-14, M5-11, M5-61, M5-20 PR 1, M5-42. Dazu (24.11.): M5-65. Weiter (Fassung 3.4): 1. M5-20 Rest (Stufe A) · 2. M5-20 PR 2 · 3. M5-60 PR 2 (nach M5-62 PR 2) · 4. M5-64 · 5. M5-66 · 6. V1–V9 · 7. M5-16 · 8. M5-43 · 9. M5-23 · 10. DS-05a · 11. M5-21 · 12. M5-24 · 13. DS-05b · 14. DS-05d · 15. M5-25 · 16. UI-07 · 17. M5-27. Dazu an passender Stelle: M5-57, M5-63, M5-33, M5-34, M5-49 bis M5-54, DS-05e/f; Stufe A DS-05c; UI-12 auf Ottos Freigabe; M5-44 bis M5-48 nach Ottos Konten.
- Stufe A (DS-05c, M5-38) und C (M5-39, M5-41, M5-32, M5-31, M5-26, in dieser Reihenfolge) laufen daneben, sobald ihre Abhängigkeit erfüllt ist.
- Eine Aufgabe, höchstens zwei PRs (§2 Punkt 11).
- Gestapelte PRs: nach dem Merge der Basis zeigt GitHub die Folge-PRs auf `main` (Einstellung „Automatically delete head branches“ ist seit 11.11. an). Gestapelte PRs und Onboarding-PRs mit Merge-Commit, Squash nur bei Merge- oder WIP-Commits.

### 6.4 Startsätze

- Stufe A, B, C: „Führe Aufgabe M5-xx aus `docs/plans/m5/m5-discovery-und-suche.md` (§6.2) aus.“
- DS-05x: „Führe Aufgabe DS-05x aus `docs/plans/m5/m5-discovery-und-suche.md` (§6.2) aus; Grundlage `adr/0018` und `adr/0030` §9.“
- V1–V9: „Führe die Vorarbeiten V1–V9 aus `adr/0031` aus; Rahmen `docs/plans/m5/m5-discovery-und-suche.md` §6.2.“
- Zu jedem Startsatz nennt der Planungs-Chat Modell und Effort.

### 6.5 Was für alle Aufgaben aus §6 gilt

- Tests (Otto 18.11.): Die volle Suite prüft die CI bei jedem Push; Otto sieht das Ergebnis in GitHub und mergt erst bei grün. Sessions lassen die volle Suite deshalb nicht selbst laufen, sondern die Tests aller Module, die sie ändern, dazu `ruff`, `lint-imports`, Typprüfung, Lint und die betroffenen Browser-Checks (die deckt die CI nicht ab); nie zwei Läufe gleichzeitig. Im Bericht nennen sie, was sie laufen ließen. Rote CI meldet Otto der Session.
- Bei jedem Onboarding klären, wie oft die Quelle aktualisiert wird und wann `materialize` laufen soll (Otto 18.11.; Takt über M5-24).
- Datensätze, die die Quelle laufend aktualisiert, auch wenn keine neue Datei dazukommt (Datei wächst oder wird ersetzt), werden auf der Plattform ebenso aktualisiert (Otto 18.11.): Änderung über `ETag`/`Last-Modified`/Hash erkennen, betroffene Items neu schreiben, sonst nichts neu lesen; Takt nach der Regel oben (M5-24). Gilt auch für vorläufige Werte, die später endgültig werden (z. B. M5-58).
- Onboarding nach `projektuebersicht.md` §5, alle Punkte, inklusive Coverage Map (Punkt 2), „zuletzt erfolgreich geprüft“ (Punkt 10) und Schlagworte deutsch und englisch (`adr/0026` F7).
- Eigenheiten (§2 Punkt 7) ausdrücklich in der Registry; was nicht geht, erscheint nicht.
- Lizenz-Einstufung nach `adr/0023` §7.2; Wortlaut der Attribution bestätigt Otto im PR vor dem Merge.
- Live-Abrufe gegen Quellen laufen nicht aus Cloud-Sessions über `gateway` (`adr/0002`); Laden von Items und Harvest-Läufe macht Otto lokal, die Session nennt die Befehle.
- Entscheidungslog nur ergänzen (Regel im Log-Kopf; `merge=union` löst gleichzeitige Zeilen).
- Frontend nach §2 Punkte 8 und 9 und `docs/ui/leitfaden.md`.

## 7. Abnahme M5

M5 ist abgenommen, wenn der Abnahmebericht (M5-27) für jeden Punkt einen Beleg nennt:

1. **Quellen von Hand:** WorldCover 2020/2021, swissALTI3D, BEV ALS-DGM 1 m und eine Meteorologie-Quelle sind angebunden, jeweils mit vollständiger Onboarding-Checkliste und den Eigenheiten aus `adr/0030`.
2. **Harvest:** Ein Lauf (lokal bei Otto) über die Seed-Liste erzeugt Kandidaten und mit `discovery propose` einen Branch für einen Draft-PR mit höchstens 20 Kandidaten je Quelle.
3. **Zweiter Lauf** ohne Quelländerung: bedingte Anfragen, wo die Quelle `ETag` oder `Last-Modified` liefert; sonst ein Abruf der Liste ohne Folgearbeit, entschieden über den Inhalts-Hash; je Quelle im Lauf-Bericht ausgewiesen; kein neuer Branch (`adr/0025` F7).
4. **Suche:** Das Bewertungs-Set besteht nach `adr/0026` F5 (Recall@5 ≥ 0,9 und MRR@10 ≥ 0,8 je Sprache, alle Filterfragen, drei von vier Negativfragen) in der CI ohne Netz.
5. **Data catalogue:** Fenster mit allen Datensätzen, gruppiert, mit Suche und AOI-Schalter; gelistete Einträge mit Link und Marke für Konto-Quellen.
6. **Health:** „Last checked“ ist je Datensatz sichtbar und stammt aus einem echten Lauf.
7. **Prototyp-Quellen:** Die Startprüfung aus `adr/0024` ist durch Tests belegt; ein Prototyp-Eintrag lädt nur lokal mit Schalter.
8. **Auffindbarkeit:** JSON-LD je Datensatz und eine Sitemap werden ausgeliefert.
9. **Sentinel-1:** DS-04 und DS-05a sind gemergt; DS-05b bis DS-05d dürfen nach M5 folgen.
10. **Skalierbarkeit (Otto, 14.11.2026):** Die Prüfung M5-35 liegt vor; jede ihrer Befunde ist behoben oder mit Ottos Entscheidung zurückgestellt. Alle M5-Bausteine laufen mit mehreren Instanzen je Prozesstyp, ohne die Last auf eine Quelle zu vervielfachen.

Der Projektplan §4 M5 bekommt mit dem Abnahmebericht einen Nachtrag mit dieser Fassung.

## 8. Fragen an Otto (Fassung 3) — beantwortet am 06.11.2026

Otto: F1 und F2 jeweils Option 1.

**F1 — Schnitt und Reihenfolge (§6.2, §6.3)?**
1. Wie vorgeschlagen **(Empfehlung)**
2. Suche (M5-22, M5-23) vor dem Harvest (M5-19 bis M5-21)
3. Harvest vor Sentinel-1 (DS-04, DS-05)

**F2 — Abnahme (§7)?**
1. Wie vorgeschlagen; DS-05b bis DS-05d dürfen nach M5 folgen **(Empfehlung)**
2. Ganz DS-05 gehört zur Abnahme
3. Sentinel-1 gehört nicht zur Abnahme von M5

## 9. Nächste Schritte

1. Laufende Aufgaben abschließen: M5-62 PR 2 (#391), M5-60 PR 1 (#396), danach M5-20 Rest.
2. Danach nach §6.3: M5-20 PR 2, M5-60 PR 2, M5-64, M5-66.
3. Für die Abnahme (§7) zuerst: M5-20 PR 2, M5-21, M5-24, M5-43, M5-23, DS-05a, M5-25, V1–V9.

## 10. Grenzen (gelten für alle M5-Aufgaben)

- Modulgrenzen laut `architekturplan.md` 3.1 (Import-Linter); ausgehende Requests nur über `gateway`; Worker-Kern zustandslos; `decomp.py` nie generalisieren.
- Keine Secrets im Repo (öffentlich, AGPL-3.0-or-later); Prototyp-Quellen nur nach `adr/0024`; Zugangsdaten nur nach `adr/0027` (Regel R-Z).
- Keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Lizenz-Einstufung und Freigabe jedes Datensatzes immer durch Otto.
- Bilder der Browserprüfung nicht ins Repo; Nachträge heißen nach der Aufgabe.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` nur mit ausdrücklicher Erlaubnis.

## 11. Nachtrag 18.11.2026: Gesamtzahl der Suche über eigene Sammlungen (M5-56)

Anlass: GLO-30 über Russland fand nur 300 Kacheln und zeigte „300/300“. Ursache: Die Suche über pgstac lieferte kein `numberMatched` (`pgstac.context` = `off`), die Liste hörte nach 300 Treffern auf. Vorgabe Otto: Der Kopf zeigt immer die echte Gesamtzahl, „Load more“ ist da, nie still abschneiden.

**Messung** (Kratzverzeichnis der Sitzung, nicht im Repo): 10⁶ synthetische Kacheln zu 0,01° in einer Test-Sammlung der lokalen pgstac (0.9.12), Suche über eine Fläche, 100 Treffer je Seite, Median aus 3 Runden; danach gelöscht. „Schreiben“ ist die Zahl der Schreibzugriffe auf `search_wheres` je Aufruf.

| Treffer | Modus | Seite 1 | Seiten 2–3 | gleiche Suche erneut | Zahl | Schreiben |
|---|---|---|---|---|---|---|
| ~3 500 (wie GLO-30 Russland) | off | 54 ms | 47 ms | 51 ms | keine | 0 |
| | on, ttl 0 | 61 ms | 59–65 ms | 63 ms | genau | 1 |
| | on, ttl 1 h | 61 ms | 51 ms | 53 ms | genau | 1 |
| | auto, ttl 1 h | 64 ms | 47–52 ms | 60 ms | genau | 1 |
| 10⁵ | off | 162 ms | 127 ms | 159 ms | keine | 0 |
| | on, ttl 0 | 287 ms | 248–255 ms | 299 ms | genau | 1 |
| | on, ttl 1 h | 315 ms | 128 ms | 210 ms | genau | 1 |
| | auto, ttl 1 h | 194 ms | 135–143 ms | 210 ms | geschätzt (101 447) | 1 |
| 10⁶ | off | 740 ms | 750–769 ms | 741 ms | keine | 0 |
| | on, ttl 0 | 1 175 ms | 1 177 ms | 1 164 ms | genau | 1 |
| | on, ttl 1 h | 1 138 ms | 744–774 ms | 677 ms | genau | 1 |
| | auto, ttl 1 h | 725 ms | 732–763 ms | 768 ms | geschätzt (990 268) | 1 |

- Mit ttl > 0 zählt nur die erste Seite; „Load more“ und dieselbe Suche innerhalb der ttl nutzen die gespeicherte Zahl. Geschrieben wird in jedem zählenden Modus einmal je Aufruf, auch bei einem Treffer im Speicher; nur `off` schreibt nicht.
- `auto` mit den Standardschwellen (100 000 Treffer und 100 000 Kostenpunkte, beide müssen erreicht sein) zählt alle heutigen Suchen genau: GLO-30 hat etwa 26 000 Kacheln, swissALTI3D einige 10⁴. Sentinel-1 und -2 sind föderiert; ihre Gesamtzahl kommt von der Quelle, nicht von pgstac.
- pgstac sagt nicht, ob es gezählt oder geschätzt hat. M5-35 plant 10⁶ gelistete Katalogeinträge (Sammlungen), keine Zahl für Items je Sammlung; 10⁶ Items ist hier die Obergrenze der Messung.

**Entscheidung Otto (18.11.2026, Option 1):** `pgstac.context` = `auto` mit den Standardschwellen 100 000 / 100 000, `context_stats_ttl` = 1 h, als Einstellung der Verbindungen des pgstac-Pools im Prozess `api` (`api/main.py::PGSTAC_COUNT_SETTINGS`), nicht als Migration. Ab 100 000 Treffern kennzeichnet das Backend die Zahl als geschätzt (`earthx:matched_estimated`), der Kopf zeigt dann „≈“ vor der Gesamtzahl, ohne Zusatztext (z. B. „Search results (300/≈990,268)“). Eine nach `materialize` bis zu einer Stunde alte Zahl schneidet nichts ab: „Load more“ hängt am Seiten-Token, und der Kopf zeigt nie weniger als geladen.
