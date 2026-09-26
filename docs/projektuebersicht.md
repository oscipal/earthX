# EarthX — Projektübersicht (überarbeitet)

> **Rangfolge:** Bei Widerspruch gilt `ENTSCHEIDUNGEN_2026-09-18.md`, danach `KLAERUNGEN.md`, danach dieses Dokument. Angepasst am 18.09.2026.

2026-09-18 · Überarbeitung der unbewerteten Gedankensammlung

Markierungen: *(neu)* = ergänzt, *(geändert)* = gegenüber der Ursprungsversion angepasst. Alles ohne Markierung ist inhaltlich unverändert übernommen. Der bisherige Sechs-Phasen-Plan ist bewusst nicht enthalten; an seiner Stelle steht eine phasenunabhängige Priorisierung (Abschnitt 15).

---

## 1. Vision & Kernidee

- Web-Plattform, die keine Rohdaten dauerhaft hostet, sondern als Zugriffs- und Verarbeitungsschicht über bestehende, verteilte Datenquellen fungiert. *(geändert)*
- Datenviewer/Downloader: bestehende Datensätze durchsuchen, ansehen und herunterladen, ohne die Rohdaten selbst zu speichern.
- Cloud Computing in zwei Modi *(geändert, vorher "in Echtzeit")*:
  - On-the-fly auf Tile-Ebene für kleine Ausschnitte und einfache Operationen.
  - Asynchrone Jobs mit Queue für alles Größere, mit AOI-Limits und Kostenschätzung vor dem Start.
- KI-gestützte Datensuche: spezialisierter Chatbot/Agent stellt gezielte Rückfragen, um den passenden Datensatz (und perspektivisch das passende Modell) zu identifizieren.
- Wissenschaftliche Rückverfolgbarkeit: gilt für Modelle (Paper-Pflicht) und für jedes Processing-Ergebnis (Rezept, siehe Prinzip 2.8). *(geändert)*
- Optionales Client-Side Computing (WASM/WebGPU) als spätere Ausbaustufe.

---

## 2. Produktprinzipien

1. **Keine dauerhafte Rohdatenhaltung.** Metadaten-Katalog + Live-Zugriff auf Originalquellen. Abgeleitete Produkte (Quicklooks, Tile-Caches, Processing-Ergebnisse, Datacubes) werden nur flüchtig mit Ablaufdatum gespeichert. Auch durchgeleitete Tiles und Ableitungen gelten lizenzrechtlich als Weitergabe bzw. Bearbeitung. *(geändert)*
2. **Nur token-freie Datenquellen.** Datenquellen, die selbst einen externen Token/Account voraussetzen, werden nicht angebunden. Betrifft die Datenquelle, nicht den Login auf der eigenen Plattform. Die fertige Plattform enthält nichts, was einen Token braucht; BIOMASS kommt darin nicht vor (ENTSCHEIDUNGEN §1).
3. **Breite vor Tiefe bei den Quellen.** Mehrere unterschiedlich strukturierte Quellen anbinden, bevor generalisiert wird. Es gibt zwei Variationsachsen: Katalogprotokoll (STAC vs. Nicht-STAC) und Datenformat (COG vs. Zarr). Beide müssen gestresst werden. *(geändert)*
4. **Das `DataSourceAdapter`-Interface entsteht organisch** aus dem Stresstest realer Quellen und wird nicht vorab designt. Voraussetzung: mindestens eine Nicht-STAC-Quelle ist angebunden, bevor vereinheitlicht wird. *(geändert)*
5. **Standards rein.** Standard-Adapter statt Einzellösungen, wo möglich (STAC, CKAN, DCAT-AP, OAI-PMH).
6. **Standards raus.** *(neu)* Der eigene Katalog wird als STAC-API angeboten, Layer als XYZ/COG-URLs, Processing perspektivisch über openEO oder OGC API Processes. Dadurch funktionieren QGIS, Python-Clients und externe Engines ohne Sonderlösungen.
7. **API-first.** *(neu)* Alles, was die UI kann, kann die API. Chatbot, Python-Snippet und QGIS-Anbindung sind nur Clients dieser API. Der Chatbot hat keine Sonderrechte.
8. **Reproduzierbarkeit.** *(neu)* Jedes Ergebnis trägt ein Rezept: Quell-Item-IDs, Parameter, Softwareversionen, Zitierangaben. Dieses Rezept ist zugleich Permalink, Python-Snippet und Metadaten-Historie.
9. **Ehrlichkeit in der Anzeige.** *(neu)* Alles, was nicht dem Original entspricht (abweichendes Datum, interpoliert, resampelt, reprojiziert), wird sichtbar gekennzeichnet, in der UI und in den Metadaten.
10. **Kostenbewusstsein.** *(neu)* Downloads wo möglich direkt von der Quelle statt durch das eigene Backend (Egress). Compute in der Cloud-Region der Daten. Jedes Feature bekommt eine grobe Kostenabschätzung pro Request. Vor Entscheidungen mit hohem Compute-Einsparpotenzial wird der State of the Art recherchiert.
11. **Robustheit gegen Quellenausfälle.** *(neu)* Health-Status pro Quelle in der UI, Metadaten-Cache, saubere Fehlermeldungen statt leerer Karten.
12. **Automatisierung mit Kontrollpunkt.** Discovery/Harvesting weitgehend automatisieren, Lizenzprüfung nie ohne Stichprobenkontrolle.
13. **Nische vor Breite (inhaltlich).** Fokus auf Geo-/Satellitendaten (Raster), bevor andere Domänen oder Datentypen dazukommen.
14. **Erweiterbarkeit.** Neue Quellen, Processing-Methoden und Processing-Backends (z. B. externe Engine wie GAMMA Remote Sensing) sollen leicht andockbar sein. Bevorzugter Andockpunkt: standardisierte Processing-Schnittstelle (siehe 2.6). *(geändert)*
15. **Security by Design.** Sicherheit ist von Anfang an Teil der Architektur. Jede externe Quelle wird als nicht vertrauenswürdig behandelt (konkret: Abschnitt 4).
16. **Skalierbar und cloud-portabel von Anfang an.** *(neu)* Alles wird so implementiert, dass möglichst viele Nutzer gleichzeitig arbeiten können. Entwickelt wird lokal, das Ziel ist die Migration zu einem Cloud-Hosting-/Processing-Anbieter, ohne Umbau der Architektur. Leitsatz: skalierbar entwerfen, aber nicht vorzeitig skalieren. Lokal läuft dieselbe Architektur in klein, nicht eine andere (konkret: Abschnitt 13).

---

## 3. Arbeitsweise *(neu als eigener Abschnitt, vorher unter Kernprinzipien)*

- Architektur-Entscheidungen werden am echten Code verankert (Repo wird inspiziert, nicht nur theoretisch geplant).
- Planungsdokumente werden iteriert, bevor implementiert wird. Gegengewicht: Planung darf die Umsetzung des aktuellen Fokus nicht blockieren. *(geändert)*
- Scope wird progressiv verengt; die Grenze zwischen verengtem und ursprünglichem Scope wird explizit gemacht.
- Neue Funktionen werden nach Implementierung committed und auf GitHub gepusht.
- Neue Funktionen werden ausführlich getestet: Fehlerfälle, fehlerhafte Eingaben, zweckfremde Verwendung.
- Tests gegen externe Quellen: Contract-Tests mit aufgezeichneten Antworten plus regelmäßige Live-Smoke-Tests, damit Quellenausfälle die Test-Suite nicht brechen. *(neu)*
- Die Architektur soll sauber, intuitiv und konsistent mit der Grundarchitektur sein.

---

## 4. Sicherheit & Datenschutz *(geändert, konkretisiert)*

**Sicherheit**
- SSRF-Schutz: Das Backend ruft URLs aus fremden Katalogen ab. Allowlist für Hosts/Schemata, keine internen Adressen, Redirects prüfen.
- Härtung der Datei-Verarbeitung: GDAL/rasterio gegen präparierte Dateien absichern (Größenlimits, Timeouts, Treiber-Allowlist).
- Modell-Container laufen ohne Netzwerkzugang und mit Ressourcenlimits.
- Vom Chatbot erzeugter Analysecode läuft ausschließlich in einer Sandbox.
- Gecrawlte und externe Inhalte gelten für das LLM als Daten, nie als Anweisungen (Prompt Injection).
- Rate Limiting und Quotas pro Nutzer/IP.
- Secrets und später hinterlegte Nutzer-Tokens verschlüsselt speichern.
- Sicherheitsstandards werden laufend überprüft (Dependency-Scanning, regelmäßiger Review).

**Datenschutz**
- DSGVO und Schweizer revDSG einhalten.
- Datenminimierung: AOIs und Suchanfragen sind personenbezogene, potenziell sensible Daten. Sparsam loggen, Aufbewahrungsfristen festlegen.
- Chatbot: Auftragsverarbeitungsvertrag mit dem LLM-Anbieter; klar kommunizieren, welche Eingaben an Dritte gehen.
- Hosting in EU/CH.
- Besonderes Augenmerk auf die Sicherheit der Kundendaten.

---

## 5. Daten & Lizenz

**Datentyp-Klassen** *(neu)*
- Jeder Datensatz gehört zu einer Klasse (z. B. Raster-Zeitreihe, statisches Raster; später ggf. Vektor, Tabelle).
- Capability-Flags pro Datensatz steuern, welche Funktionen angeboten werden (ROI, Zeitraum, Interpolation, Band-Math, ML-Processing usw.).
- Aktueller Fokus: nur Raster-Klassen.

**Lizenz** *(geändert)*
- Lizenz ist ein maschinenlesbares Pflichtfeld (SPDX-Kennung, sonst Freitext + manuelle Einstufung).
- Aufnahmekriterium gestuft nach KLAERUNGEN B11: Katalogeintrag immer, Anzeige nur bei erlaubter Weitergabe und Bearbeitung, Processing zusätzlich mit Tier-Regel. NC ist in Ordnung, ND-Datensätze bleiben Katalogeintrag mit Link.
- Lizenz-Flags steuern das Verhalten der Plattform: `commercial_use`, `derivatives`, `share_alike`, `attribution_required`.
- NC-Datensätze bleiben bis zur rechtlichen Klärung vollständig im Gratis-Tier.
- Bei Kombination mehrerer Datensätze (Datacube) gilt die restriktivste Lizenz aller Bestandteile; inkompatible Kombinationen (z. B. ShareAlike-Konflikte) werden blockiert oder mit Warnung versehen.
- Attribution wird bei jedem Download und Export automatisch mitgeliefert.

**Onboarding-Checkliste pro Datensatz** *(geändert, formalisiert)*
1. Beschreibung vorhanden.
2. Coverage Map / Footprint-Layer vorhanden (Pflicht). Seit `adr/0004` (angenommen 19.09.2026) heißt der Punkt genauer: **ein Coverage-Anbieter ist zugeordnet** (Upstream-Aggregation, eigenes SQL oder ausgewiesene Stichprobe) **und die Vollständigkeitsprobe greift** — die Antwort trägt `vollstaendig`, `gekappt` oder `stichprobe`.
3. DOI verlinkt, wo vorhanden; sonst persistente Zitierangabe (Landing Page, Version, Herausgeber). *(geändert: DOI ist kein Ausschlusskriterium)*
4. Lizenz geprüft und als Feld mit Flags erfasst.
5. Cloud-natives Format bevorzugt (Zarr > COG > Legacy).
6. Anonymer Zugriffs-Check bestanden (HTTP 200 statt 401/403).
7. Datentyp-Klasse und Capability-Flags gesetzt.
8. Standard-Visualisierung definiert (Bänder, Stretch, Colormap).
9. Mindestens ein Processing-Schritt End-to-End getestet (Suche → Verarbeitung → Download). **Fassung v1 (D4, 2026-09-20):** Solange es in M2 noch keinen Processing-Schritt gibt, gilt als End-to-End-Test die Kette **Suche → Anzeige → Zuschnitt-Download** gegen Fixtures; der echte Processing-Schritt löst diese Fassung mit M4 ab.
10. "Zuletzt erfolgreich geprüft" ist gesetzt und sichtbar (KLAERUNGEN B12). ~~**Fassung v1 (D4, 2026-09-20):** Bis eigene Health-Checks kommen (M5), ist das der Zeitpunkt des letzten grünen T-D-Smoke-Laufs.~~ **Fassung v1.1 (Otto, 2026-09-22, ersetzt die Fassung v1):** In M2 heißt der Punkt **„der Datensatz ist vom T-D-Smoke abgedeckt"**, geprüft über den Marker in `backend/tests_live/`. Ein sichtbares Prüfdatum zeigt die Plattform in M2 **nicht**; es kommt mit den eigenen Health-Checks in M5. Grund: den Zeitpunkt des letzten grünen Laufs aus GitHub Actions in die laufende Plattform zu bringen, geht weder ohne Secret noch ohne laufende Handarbeit (M2-08 Plan §4.4). Das heutige `earthx:health.last_checked_ok` ist das Datum des Onboarding-Checks und darf nirgends als „zuletzt geprüft" erscheinen.

---

## 6. Auth & Konten *(geändert)*

Zwei Themen, die getrennt behandelt werden:

- **Plattform-Login:** nötig, sobald Compute Geld kostet (Jobs, Quotas, API-Keys, Pro-Funktionen). Kommt deshalb früher als die Token-Verwaltung.
- **Token-Verwaltung pro Connector:** Nutzer hinterlegen optional eigene Keys für token-pflichtige Quellen. Bleibt ein fernes Zukunftsthema; die bestehende MAAP-Token-Logik wird dafür nicht als Vorlage übernommen.

Vorschlag zur Registrierungspflicht (Entscheidung offen, siehe Abschnitt 16): anonymes Suchen und Ansehen, Login erst für Jobs, größere Downloads, API-Keys und Chatbot. Senkt die Einstiegshürde und reduziert die Menge personenbezogener Daten.

---

## 7. GUI & Viewer

**Grundsätze**
- Cleanes Design, das auf dem Vorhandenen aufbaut.
- Möglichst intuitiv und selbsterklärend.
- Nur 2D, keine 3D-Ansicht.

**Auswahl & Suche**
- ROI-Auswahl pro Datensatz: Punkt, Bounding Box, Polygon; dazu Zeitraum-Auswahl.
- Eigene AOI hochladen (GeoJSON, KML, Shapefile). *(neu)*
- Ortssuche: Ort eingeben → Umriss als Polygon, optional dessen Bounding Box. Bei OSM/Nominatim Nutzungsregeln und ODbL-Attribution beachten. *(geändert)*
- Verfügbarkeits-Zeitleiste pro AOI: zeigt, für welche Zeitpunkte Daten existieren. *(neu)*
- Fallback, falls für das gewählte Datum nichts verfügbar ist: nächstgelegener Datensatz (davor/danach) mit klar ersichtlichem Hinweis.
- Qualitätsfilter, wo sinnvoll (z. B. Wolkenbedeckung bei optischen Daten). *(neu)*
- Health-Status der Quelle sichtbar. *(neu)*

**Anzeige**
- Quicklooks anzeigbar, downloadbar, in Full Resolution darstellbar.
- Histogramm-Stretch und Colormap-Wahl pro Layer. *(neu)*
- Pixel-Inspektor: Klick zeigt Wert(e); bei Zeitreihen Diagramm am Punkt mit CSV-Export. *(neu)*

**Layer Manager**
- Pro Layer: ausblenden, Transparenz, Einzel-Download (mit/ohne Processing).
- Mehrere Layer gemeinsam herunterladen (mit/ohne Processing).
- Vergleich über Swipe-/Split-Ansicht mit synchronisierten Karten. *(geändert: ersetzt das freie Skalieren eines Layers "wie in Word", weil das den Raumbezug zerstört und das Vergleichsziel schlechter erfüllt)*
- Button "Layer auf aktuelle Ansicht zuschneiden" bleibt.

**Export**
- Kartenausschnitt als PNG oder SVG speichern, optional ohne Hintergrundkarte.
- Schlanker Export-Dialog: Titel, Colorbar, Maßstab, Nordpfeil, Attribution. *(geändert)*
- Für alles darüber hinaus: generiertes matplotlib-Snippet, das den Plot reproduziert und frei anpassbar ist. *(geändert: ersetzt den vollen Plot-Editor im Browser)*
- Permalink / teilbarer Zustand der aktuellen Ansicht und Einstellungen. *(neu)*

---

## 8. Processing

**Aufbau**
- Processing-Panel mit Reitern nach Kategorie (Standard, Machine Learning, ...), jeweils mit den wichtigsten Parametern.
- Parameter entweder custom eintragen oder von einem anderen Datensatz übernehmen, gesamt oder einzeln.
- Vor Jobstart: Schätzung von Datenmenge, Dauer und ggf. Kosten. *(neu)*

**Standard-Parameter**
- Resolution, Koordinatensystem, Ausgabeformat, Masking, Normalisierung.
- Resampling-Methode mit datentyp-abhängigem Default (kategoriale Daten: Nearest Neighbour). *(neu)*
- Band-Math-Ausdrücke (z. B. NDVI) als generischer Weg zu den häufigsten Analysen; datensatzspezifische Presets (wie Pauli RGB bei SAR) bauen darauf auf. *(neu)*
- Zonale Statistik pro Polygon. *(neu)*

**Machine Learning**
- Überlappung der Chips und Padding einstellbar.
- Domain-Shift-Hinweis, wenn Eingabedaten nicht zur Trainingsdomäne des Modells passen.

**Zeitliche Angleichung** *(geändert)*
- Interpolation zwischen Datensätzen davor/danach; Methode und Anzahl einbezogener Datensätze wählbar.
- Nur freigeschaltet für Datentypen, bei denen das fachlich sinnvoll ist (kontinuierliche Größen wie NDVI, Temperatur). Gesperrt für kategoriale Daten; für SAR-Backscatter/Phase nur mit ausdrücklicher Warnung oder gar nicht.
- Ergebnis wird als synthetisches Produkt gekennzeichnet (UI + Metadaten).

**Datacube**
- Mehrere Layer als Datacube herunterladen (z. B. Multiband-TIFF, Zarr); räumliche und zeitliche Auflösung müssen angeglichen sein.
- Lizenzprüfung der Kombination (siehe Abschnitt 5).

**Metadaten & Provenienz**
- Metadaten werden nach jedem Schritt angepasst; das vollständige Rezept wird mitgeliefert (siehe Prinzip 2.8).

**Erweiterbarkeit**
- Neue Methoden leicht hinzufügbar; externe Anbieter (z. B. GAMMA Remote Sensing) über eine standardisierte Processing-Schnittstelle andockbar.
- Vor dem Bau einer eigenen Processing-Schicht prüfen: titiler (baut auf rio-tiler auf, On-the-fly-Algorithmen, Zarr-Variante) und openEO (Prozessgraphen, bestehende Clients). *(neu)*

---

## 9. API, Standards & Integrationen *(geändert)*

- Öffentliche API als Fundament (Prinzip 2.7); API-Keys pro Nutzer.
- Python: Für die auf der Plattform gewählten Einstellungen wird ein Code-Snippet generiert, das Daten bzw. Ergebnis direkt in Python lädt.
- Katalog als STAC-API, Layer als XYZ/COG-URLs.
- QGIS: zunächst über diese Standards (STAC und XYZ sind in QGIS direkt nutzbar), eigenes Plugin erst, wenn das nicht reicht.
- Automatischer Zitierexport (BibTeX) für Datensatz, Modell und Processing-Rezept. *(neu)*

---

## 10. Chatbot

- Datensatzsuche für das eigene Vorhaben über gezielte Rückfragen (Thema, Raum/Zeit, Format, Lizenz, Datenmenge).
- Zunächst nur Empfehlung, kein automatischer Jobstart.
- Arbeitet ausschließlich über die öffentliche API (Prinzip 2.7). *(neu)*
- Free: nur Datensatzsuche. Pro: Analysefunktionen (z. B. Scatterplot aus einem Bild, direkt downloadbar), Modellauswahl.
- Suche außerhalb der Plattform: findet noch nicht verfügbare Datensätze und schlägt sie zur Aufnahme vor. Aufnahme läuft über die Onboarding-Checkliste und menschliche Lizenzfreigabe, nicht vollautomatisch. *(geändert)*

---

## 11. Business Model

- Freemium: einfache Prozessierung, Download und Datensuche gratis; aufwändigere Prozessierung kostenpflichtig.
- Bezahlt wird für Compute, nicht für Daten. NC-Datensätze bleiben bis zur rechtlichen Klärung im Gratis-Tier. *(neu)*
- Mögliche Pro-Funktionen: große Jobs, Chatbot-Analyse, Benachrichtigung bei neuen Daten für gespeicherte AOIs. *(neu)*
- Reselling kostenpflichtiger Datensätze: Zukunftsziel, aktuell nicht umzusetzen.

---

## 12. Modell-Registry

- Modell-Katalog analog zum Datenkatalog (Quellen: Papers with Code, Hugging Face Model Hub, Zenodo).
- Paper-Referenz ist Pflichtfeld.
- Modell-Lizenz wird wie die Datenlizenz als Feld erfasst. *(neu)*
- Standardisiertes Container-Interface pro Modell (Input-/Output-Ordner, Manifest); Adapter wird pro Modell einmalig gebaut.
- Domain-Shift-Warnhinweise (Trainingsdaten-Domäne und Validierungsmetriken transparent anzeigen).
- Physikalische Modelle: eigener, langsamerer Track mit überwiegend manuellen Wrappern.

---

## 13. Architektur & bestehender Code

- Bestehender Prototyp `biomass-viewer` (github.com/oscipal/biomass-viewer): FastAPI-Backend + React/Vite/TypeScript-Frontend.
- Prototyp integriert den ESA-MAAP-STAC-Katalog, nutzt Bearer-Token-Auth via `.env`, liefert COG-Tiles über rio-tiler, rendert eine MapLibre-Karte.
- Der Prototyp bleibt als lokale Referenz erhalten. Behalten werden seine **Funktionen und Designentscheidungen**, nicht der Datensatz; sie werden auf token-freie Datensätze übertragen (ENTSCHEIDUNGEN §2). Entfernt wird er, sobald das gelungen ist (Entscheidung Otto, Stufe B).
- Format-Präferenz-Hierarchie: Zarr > COG > Legacy-Formate.
- Zarr-Quellen brauchen ein neues `zarr_reader.py`-Modul, getrennt von `cog.py`.
- `DatasetConfig`-Dataclass-Registry in neuem `datasets.py` mit `format`-Feld für das Reader-Dispatching. Kandidaten für weitere Felder: Datentyp-Klasse, Capability-Flags, Lizenz-Flags, Zitierangabe. *(geändert)*
- Backend-Routen sowie `stac.py` und `store.py` werden mit einem `dataset`-Argument parametrisiert. `auth.py` wird nicht übernommen.
- Frontend `ControlPanel.tsx` und `store.ts` werden von hardcodierten BIOMASS-Labels generalisiert.
- Coverage Map ist Pflicht für jeden neuen Datensatz (Punkt 2 der Onboarding-Checkliste, §5); Vorlage ist `/api/coverage` im Prototyp, die technische Umsetzung steht in `adr/0004`.
- Die sieben Hard Constraints aus `ADDING_ESA_DATASETS.md` sind aufgehoben; bestehender Code darf umgebaut, verschoben und umbenannt werden.
- `decomp.py` (polarimetrische Dekomposition für komplexe Quad-Pol-Daten) wird Operator mit Quad-Pol-Capability und nie generalisiert.

**Skalierbarkeit & Cloud-Portabilität** *(neu, konkretisiert Prinzip 2.16)*
- Zustandsloses Backend: kein Nutzer- oder Sitzungszustand im Prozessspeicher oder auf der lokalen Platte. Jede Anfrage kann von jeder Instanz beantwortet werden, damit horizontal skaliert werden kann.
- Zustand liegt nur in austauschbaren Diensten: Datenbank (Postgres), Cache (z. B. Redis), Objektspeicher (S3-kompatibel) für flüchtige Ergebnisse. Lokal durch leichte Entsprechungen ersetzt (z. B. Garage, lokaler Redis), hinter derselben Schnittstelle.
- Schwere Arbeit nie im Request: Processing läuft über eine Job-Queue mit getrennten Workern, die unabhängig vom Web-Backend skaliert werden. Lokal ein Worker, in der Cloud viele.
- Alles containerisiert (Docker), Konfiguration ausschließlich über Umgebungsvariablen, keine hardcodierten Pfade oder Hosts.
- Anbieter-Neutralität: nur portable Bausteine verwenden (Container, Postgres, S3-API, Standard-Queue). Proprietäre Cloud-Dienste nur hinter einer eigenen Abstraktionsschicht, damit die Anbieterwahl offen bleibt.
- Caching auf mehreren Ebenen: Katalog-Metadaten, Tiles (CDN-fähige URLs, Cache-Header), wiederholte Processing-Ergebnisse über das Rezept als Cache-Schlüssel.
- Fairness bei vielen Nutzern: Quotas, Rate Limits, Job-Prioritäten und Limits pro Nutzer, damit ein einzelner Großjob die Plattform nicht blockiert.
- Rücksicht auf die Quellen: gleichzeitige Zugriffe auf externe Datenquellen bündeln und begrenzen (Connection-Pooling, Backoff), damit viele Nutzer nicht zu einer Sperre durch die Quelle führen.
- Async-I/O im Backend für alle Zugriffe auf externe Quellen; CPU-lastiges (rasterio/GDAL) gehört in Worker, nicht in den Event-Loop.
- Beobachtbarkeit von Anfang an: strukturierte Logs, Metriken (Latenz, Queue-Länge, Fehlerquote pro Quelle), damit Engpässe sichtbar werden, bevor skaliert wird.
- Im bestehenden Prototyp zu prüfen: wo liegt Zustand im Speicher oder Dateisystem (`store.py`, lokale Caches)? Das sind die Stellen, die eine Mehrnutzer-Skalierung zuerst blockieren.

---

## 14. Tools & Stack

- Backend: FastAPI, Python 3.12, `pystac-client`, `rasterio`, `rio-tiler`; Abhängigkeiten per pip aus `backend/requirements.txt`, kein conda mehr (seit M3-03, `plans/m3-03-python-312.md`). *(geändert)*
- Frontend: React, Vite, TypeScript, MapLibre GL.
- Datenzugriff: ESA-MAAP-STAC-Katalog, EOPF Sentinel Zarr Samples Service (Kandidat), Copernicus Data Space Ecosystem.
- Formate: COG (aktuell), Zarr (Priorität für neue Quellen).
- Zu evaluieren: titiler / titiler-xarray, openEO. *(neu)*
- Repo: github.com/oscipal/earthX (aus `biomass-viewer` umbenannt).

---

## 15. Priorisierung *(neu, ersetzt den Phasenplan)*

Maßstab für "Jetzt": Was beweist den Kern Suche → Verarbeitung → Download an unterschiedlich strukturierten Quellen?

**Jetzt**
- Dataset-Registry generalisieren (`datasets.py`, `dataset`-Argument, Frontend-Labels).
- Zarr-Reader.
- 2–4 weitere token-freie Quellen, davon mindestens eine Nicht-STAC-Quelle.
- Onboarding-Checkliste inkl. Lizenzfeld und Zugriffs-Check.
- ROI- und Zeitraum-Auswahl, AOI-Upload, Ortssuche, Datums-Fallback mit Hinweis.
- Layer Manager Basis (ausblenden, Transparenz, Einzel-Download).
- Quicklooks, Stretch/Colormap.
- Standard-Processing (Resolution, CRS, Format, Band-Math) mit Rezept in den Metadaten.
- Sicherheits-Basis: SSRF-Schutz, Limits bei Datei-Verarbeitung, Rate Limiting.
- Skalierbarkeits-Basis: zustandsloses Backend, Konfiguration über Umgebungsvariablen, Docker-Setup, Speicher- und Queue-Zugriffe hinter Schnittstellen (auch wenn lokal nur eine Instanz läuft).

**Bald**
- Plattform-Login, asynchrone Jobs mit getrennten Workern, Kostenschätzung, Quotas.
- Migration auf Cloud-Hosting, Lasttests mit simulierten gleichzeitigen Nutzern, Metriken/Monitoring.
- Swipe-/Split-Vergleich, Pixel-Inspektor mit Zeitreihe, Verfügbarkeits-Zeitleiste.
- Mehrfach-Download und Datacube inkl. Lizenzprüfung.
- Öffentliche API, Python-Snippet, STAC-API nach außen, Zitierexport.
- Kartenexport (schlank), Permalinks.
- Health-Status der Quellen, Harvesting, semantische Suche.

**Später**
- Chatbot (erst Suche, dann Analyse/Pro).
- Modell-Registry und ML-Processing.
- Zeitliche Interpolation.
- Externe Processing-Engines (GAMMA), openEO-Anbindung.
- Discovery-Agent für Quellen ohne Standard-API.
- Token-Verwaltung pro Connector.
- QGIS-Plugin (falls Standards nicht reichen), Client-Side Computing.
- Bezahl-Tiers, Benachrichtigungen, Reselling, weitere Domänen/Datentypen.

**Verworfen / ersetzt**
- Freies Skalieren eines Layers in der Kartenansicht → Swipe-/Split-Vergleich.
- Voller matplotlib-artiger Plot-Editor im Browser → schlanker Export + generiertes Snippet.
- DOI als Ausschlusskriterium → DOI wo vorhanden, sonst persistente Zitierangabe.
- "Echtzeit"-Processing als pauschales Versprechen → zwei Modi (on-the-fly / Jobs).
- 3D-Ansicht.

---

## 16. Offene Entscheidungen

| Thema | Stand / Empfehlung |
|---|---|
| Registrierungspflicht für alles vs. anonymes Suchen/Ansehen | Empfehlung: anonym ansehen, Login ab Jobs/Downloads/API |
| Processing auf NC-Daten hinter Bezahlschranke | Rechtsrat einholen; bis dahin NC nur im Gratis-Tier |
| ESA-only-Scope vs. ursprüngliche Quellenbreite | Empfehlung: mindestens eine Nicht-STAC-Quelle (Hansen-Bucket oder Zenodo), bevor das Adapter-Interface vereinheitlicht wird |
| Konkrete Auswahl der nächsten 2–4 Datenquellen | offen |
| Eigene Processing-Schicht vs. titiler/openEO | zu evaluieren, bevor viel Eigenbau entsteht |
| Cloud-Provider/Orchestrierung (Managed vs. eigenes K8s) | offen; Kriterien: Nähe zu den Daten, Egress-Kosten, EU/CH-Standort, kein Lock-in (portable Bausteine) |
| Aufbewahrungsdauer für Ergebnisse und Logs | offen (Kosten + Datenschutz) |
| Rechtliche Prüfung Redistribution/Aggregation (ToS je Quelle) | laufend, pro Quelle |
| Zielarchitektur `DataSourceAdapter` (Methodensignaturen) | wird aus der Erfahrung mit realen Quellen abgeleitet |
| Reselling: Reseller-Rechte je Quelle | Zukunftsthema, Rechtslage offen |
| Nicht-Raster-Datentypen (Vektor, Tabellen; CKAN/OAI-PMH-Quellen) | offen; aktuell außerhalb des Fokus |
