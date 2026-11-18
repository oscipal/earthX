# M5-19 — Harvest-Kern: Tabellen, Fetch und Extract für STAC-API und CKAN, Lauf-Befehl

**Status (17.11.2026):** Plan angenommen (Otto, 17.11.2026: F1, F2, F5–F8 je 1, A1–A6 gelten, Zusatz „Ausdehnung unbekannt“, §9a); F3 und F4: CORINE und Landsat bleiben unverändert. **Stufe B**. PR 1 in [#375](https://github.com/oscipal/earthX/pull/375) gemergt; PR 2 (CKAN, README) im Draft-PR, Stand §12.3.
**Aufgabe:** M5-19 aus `docs/plans/m5/m5-discovery-und-suche.md` §6.2, Auftrag von Otto vom 17.11.2026, mit Zusatz zum Link „Source“ (§6).
**Grundlagen:** `adr/0025` (Schnitt 4, §5.1–§5.4, §6.2 mit Nachtrag M5-37), `adr/0033` (§5, §7, §11, §13 Zeile M5-19), M5-Plan §2 Punkt 12 (alle Datentypen gelistet); `plans/m5/m5-37-zeiger-je-host.md` (Zeiger, Plätze, Unterbrecher je Host, `open_source_gateway`); `plans/m5/m5-40-gelistete-in-postgres.md` (A10, G6, A11: Aufrufe im Harvest); `plans/m5/m5-18-gateway-ruecksicht.md` (`User-Agent`, `obey_robots`, `HostResting`); `plans/m5/m5-36-grenzen-je-host.md` (`hosts.yaml`); `architekturplan.md` 3.1, 4.3; KLAERUNGEN B8, B9.

Belegstufen wie in `adr/0025`: **P** am Quelltext gelesen (Stand `main` cd58da8), **M** gemessen (nur aus den ADRs übernommen, mit Fundstelle), **S** Sekundärquelle oder Vorwissen, **A** eigene Ableitung. Aus dieser Sitzung geht keine Anfrage an eine echte Quelle (`adr/0002`, Auftrag); was an den Quellen zu prüfen ist, steht in §8 als Befehl für Ottos lokalen Lauf.

---

## 1. Ziel

Der erste Teil der Pipeline aus `adr/0025` §5.1, für die beiden Protokolle mit dem größten Bestand:

1. **Tabellen** für Läufe, Rohantworten, Zustand und Übergänge (`adr/0025` §5.3).
2. **Seed:** Quellen als YAML unter `backend/catalog/sources/`, streng gelesen (`adr/0025` §5.2 mit Nachtrag `adr/0033`).
3. **Fetch** über `gateway` mit Zeiger, Plätzen und Unterbrecher je Host aus M5-37, bedingt wo die Quelle es kann, `robots.txt` beachtet, Inhalts-Hash je Fund.
4. **Extract** je Protokoll (STAC-API, CKAN) in eine Zwischenform für **alle Datentypen** (M5-Plan §2 Punkt 12, `adr/0033` §13): kein Rasterfilter und kein Filter nach räumlicher Angabe (Funde ohne sie tragen „Ausdehnung unbekannt“, Zusatz Otto 17.11., §5.3), Personenfelder verworfen, Link „Source“ nach der Regel aus §6.
5. **Lauf-Befehl** `python -m earthx.discovery.harvest <source_id>` mit Lauf-Bericht, im Compose-Profil `harvest` wie `materialize`.
6. **Zusatz Otto (17.11.2026):** Link „Source“ so direkt wie möglich zu den Daten (§6), Handeinträge CORINE und Landsat nachgezogen (§7), Zeile im Entscheidungslog.

**Nicht Teil von M5-19** (`adr/0033` §13, M5-Plan §6.2):

- Lizenzkatalog, `grants/`, Warteliste, Lauf-Stapel, Bericht mit Stichprobe, Freigabedatei, `discovery publish`, Verify, Enrich der Ausdehnung (Ortsnamen → Geometrie), Dedupe, Kandidaten, Grabsteine geernteter Einträge: **M5-20**.
- GeoSphere, INSPIRE-ATOM, STAC Index als Register: **M5-21**.
- Prozess `harvester` als Takt, Health-Checks: **M5-24**. Der Prozess bleibt eine leere Hülle.
- Kein geernteter Fund wird in M5-19 sichtbar: In `earthx_listed_entry` schreibt erst M5-20 (F5).

## 2. Ausgangslage im Code [P]

| Stelle | Heute | Folge für M5-19 |
|---|---|---|
| `discovery/` | `materialize.py`, `source_gateway.py` (`open_source_gateway`, M5-37), leerer Prozess `main.py` | Harvest als neues Modul daneben, Muster `materialize`: Lauf gegen offene Verbindung und offenes `Gateway`, CLI nur als Hülle |
| `gateway` | `user_agent` Pflicht, `obey_robots`, `HostResting`, `RobotsDisallowed`; `get(headers=…)`; `304` kommt als Antwort durch (`REDIRECT_STATUS` ohne 304, Fehler erst ab 400); Antwort höchstens 8 MB | Bedingte Anfragen ohne Änderung an `gateway`; CKAN-Seiten müssen unter 8 MB bleiben (§4.3) |
| `catalog/source_hosts.py`, Migrationen 022, 023 | Zeiger, Plätze mit Frist und Herzschlag, Unterbrecher je Host in Postgres | gilt für jede Anfrage des Harvest über `open_source_gateway`; nichts Neues an der Mechanik |
| `backend/catalog/hosts.yaml` | Grenzen je Host; Prüfung: jeder Host eines vollen Eintrags hat einen Eintrag, **jeder Eintrag gehört zu einem Host eines vollen Eintrags** | Katalog-Hosts der Seed-Liste (`www.govdata.de`, `ckan.opendata.swiss`, `www.data.gv.at`) brauchen Einträge, und die Prüfung muss Quellen des Seeds als Besitzer kennen (F6) |
| `catalog/listed.py` | `ListedEntry` mit `source_url` („landing page at the source“), `listed_keywords`, `link_host`; `HAND_SOURCE = "listed"` | Extract ruft `listed_keywords`; die Quell-ID `listed` ist reserviert (M5-40 A10) |
| `catalog/categories.py` | `category_of(Evidence)` rein; „den Aufruf im Harvest macht M5-19“ (M5-40 G6) | Extract ruft es mit INSPIRE-Themen, EU-Themen, CKAN-Gruppen, Schlagworten |
| Migration 021 | `earthx_listed_entry.run_id` ohne Fremdschlüssel, „bis M5-19 `earthx_harvest_run` anlegt“ | Fremdschlüssel in der neuen Migration |
| `frontend/src/catalogue.ts` | `sourceRow`: gelistet → `earthx:listing.source_url`; voll → `earthx:source.endpoint` (die API-Adresse) | Für gelistete Einträge reicht ein besserer Wert im Feld; volle Einträge zeigen heute eine API, keine Seite (F2) |
| `.importlinter` | `discovery` darf `adapters`, `catalog`, `gateway` | Extraktoren unter `discovery`; reine Hilfen, die `catalog-load` auch braucht, bleiben in `catalog` |

## 3. Tabellen (Migration 024)

Neue Tabellen in `public`, Namen wie in `adr/0025` §5.3. Keine AOI, keine Adressen von Dateien in Spalten, die geloggt werden.

| Tabelle | Inhalt |
|---|---|
| `earthx_harvest_run` | je Lauf und Quelle: `run_id`, `source_id`, Art (`incremental`, `full`), Beginn, Ende, Status (`running`, `done`, `interrupted`, `failed`), Frist und Herzschlag (`lease_until`), Anfragen gesamt, davon `304`, Bytes, Funde neu / geändert / unverändert / ungültig / weg / mit unbekannter Ausdehnung, Grund eines Abbruchs (`host_resting`, `robots`, `request_budget`, `upstream`, `shape`) ohne Adresse |
| `earthx_raw_record` | je Fund (`source_id`, `source_key`): letzte Rohantwort gzip (höchstens 1 MB), SHA-256, `ETag`, `Last-Modified` (wo die Quelle sie je Fund liefert), geholt am, Lauf |
| `earthx_record_state` | je Fund: Zustand (`extracted`, `invalid`, `gone`; die übrigen aus `adr/0025` §5.4 und `adr/0033` §7 kommen mit M5-20), Zwischenform als `jsonb`, ihr SHA-256, Kennzeichen „Ausdehnung unbekannt“, Grund bei `invalid`, zuletzt gesehen in Lauf |
| `earthx_state_transition` | von, nach, wann, Lauf, Grundcode |
| `earthx_harvest_source` | je Quelle `ETag` und `Last-Modified` ihrer Liste, nur wenn die Liste auf eine Seite passt: dann heißt `304` „Liste als Ganzes unverändert“ (§4.2) |

- **Lauf-Sperre je Quelle (A1):** Ein Lauf legt seine Zeile mit `lease_until` = jetzt + 5 min an und erneuert sie nach jeder Seite (5 min, weil das Warten auf einen Platz bis 60 s und die Versuche einer Anfrage zusammen länger dauern können als 60 s); ein zweiter Lauf derselben Quelle bricht ab, solange eine Zeile mit `running` und lebender Frist besteht. Gleiche Form wie die Plätze aus M5-37 (Otto 16.11.: Frist und Herzschlag), kein Advisory-Lock: Der überlebt keinen Verbindungsabbruch sichtbar und lässt sich nicht abfragen.
- **Fremdschlüssel** `earthx_listed_entry.run_id → earthx_harvest_run` (Migration 021, Kommentar dort).
- **Grenzen:** Die Rohantwort eines Fundes über 1 MB wird nicht gespeichert; der Fund wird `invalid` mit Grund `too_large`, sein Hash bleibt (Vergleich im nächsten Lauf).

## 4. Seed und Fetch

### 4.1 Seed-Dateien

`backend/catalog/sources/<source_id>.yaml`, gelesen nur von `discovery` (und der Prüfung in §4.4), streng wie die Einträge (`entry_files.read_yaml`, unbekanntes oder fehlendes Feld ist ein Ladefehler, B10):

| Feld | Inhalt |
|---|---|
| `source_id` | wie der Dateiname; `listed` und `proto-*` abgelehnt (M5-40 A10, `adr/0024`) |
| `protocol` | `stac-api` oder `ckan` (M5-21 ergänzt) |
| `endpoint` | `https`-Adresse des Katalogs (STAC: Wurzel; CKAN: `…/api/3/action/`) |
| `catalog_page` | Vorlage der Seite eines Datensatzes im Katalog, z. B. `https://opendata.swiss/de/dataset/{name}`, oder `null` (letzter Rang der Link-Regel, §6) |
| `filter` | STAC: Liste von Collection-Präfixen oder leer (alle); CKAN: `fq` wörtlich oder leer. Ein Filter nach räumlicher Angabe gehört nicht hierher (§5.3) |
| `max_requests_per_run` | Obergrenze, danach endet der Lauf `interrupted` mit `request_budget` |
| `full_every_days` | Abstand voller Läufe (CKAN, `adr/0025` §6.2: wöchentlich) |
| `maturity` | wie in der Registry |
| `enabled` | `false` hält die Quelle an, ohne die Datei zu löschen (F7) |

- Die Grenzen je Host stehen **nicht** in der Seed-Datei, sondern in `hosts.yaml` (ein Host, eine Regel, M5-36). `adr/0025` §5.2 nannte `min_interval_s` je Host im Seed; das lag vor M5-36 (F6).
- Die Herausgeberliste entfällt als Filter (`adr/0033` F9 = 1, Nachtrag in `adr/0025` §5.2).

### 4.2 Fetch je Protokoll

Alle Anfragen über **ein** `Gateway` je Lauf aus `open_source_gateway(policy)` (M5-37): Zeiger, Plätze und Unterbrecher je Host gelten über alle Läufe und Instanzen; `Policy` mit den Hosts der Quelle, Grenzen aus `hosts.yaml`, `obey_robots=True` (`adr/0025` §6.2). Der Harvest holt nur Kataloge, nie eine Datei eines Datensatzes; die Adressen in den Antworten werden gespeichert, nicht abgefragt (K4, Verify erst M5-20).

| | STAC-API (FSDI, Earth Search) | CKAN (GovData, opendata.swiss, data.gv.at) |
|---|---|---|
| Liste | `GET /collections`, Seiten über `rel=next`; ein Fund = eine Collection aus der Liste, kein Abruf je Collection | `package_search` mit `fq`, `rows=100`, `sort=id asc`, `start` als Versatz; ein Fund = ein Paket samt `resources` |
| bedingt | `If-None-Match`/`If-Modified-Since` nur auf die erste Seite und nur, wenn die Liste beim letzten Lauf auf eine Seite passte (`earthx_harvest_source`); `304` heißt dann: Lauf ohne Folgearbeit (Earth Search `304` [M], `adr/0025` §3) | keine (`ETag` fehlt [M], `adr/0025` §3) |
| ohne `ETag` | Hash je Seite und je Fund; gleicher Hash, keine Folgearbeit (FSDI: 6 Seiten [M]) | Hash je Fund |
| inkrementell | — (Listen sind klein) | `fq` zusätzlich `metadata_modified:[<letzter Lauf − 1 h> TO *]`; voll, wenn `--full` oder der letzte volle Lauf älter als `full_every_days` ist |
| weg | Fund fehlt in einem vollständigen Lauf → `gone` | nur nach einem vollen Lauf → `gone` (A3) |

### 4.3 Grenzen des Fetch [A]

- **Seitengröße CKAN:** 10 Pakete von GovData sind 181 KB [M] (`adr/0025` §3), 100 also rund 1,8 MB, unter der Grenze von 8 MB in `gateway`. Ohne Filter nach räumlicher Angabe (§5.3) braucht ein voller Lauf über die 165 427 Datensätze von GovData [M] (`adr/0033` §2.2) mit 1 s Abstand rund 1 650 Anfragen, knapp 28 min; `max_requests_per_run` der Seed-Datei liegt darüber.
- **`rel=next`** muss auf denselben Host zeigen; eine Adresse zum zweiten Mal im selben Lauf beendet ihn mit `shape` (Schleife).
- **`HostResting`** (Unterbrecher oder nächster Platz über 60 s, M5-37): Lauf endet `interrupted` mit `host_resting`; ungesehene Funde ändern ihren Zustand nicht (A2).
- **`RobotsDisallowed`:** Lauf endet `interrupted` mit `robots`; der Bericht nennt den Host, nie die Adresse.
- Logzeilen nennen Quelle, Host, Status, Zahlen; nie Adressen, `href`, Schlüssel einzelner Funde oder Ausdehnungen (M5-Plan §10).

### 4.4 `hosts.yaml`

Neue Einträge für die Katalog-Hosts (F6): `www.govdata.de`, `ckan.opendata.swiss`, `www.data.gv.at`. `data.geo.admin.ch` und `earth-search.aws.element84.com` stehen schon darin (je 6 Verbindungen; FSDI 1 s). Die Prüfung in `DatasetRegistry` wird „jeder Eintrag gehört zu einem Host eines vollen Eintrags **oder einer Quelle des Seeds**“; jeder Host einer Seed-Datei muss einen Eintrag haben.

## 5. Extract

### 5.1 Zwischenform

Eine Dataclass `Extracted` in `discovery`, als `jsonb` mit Hash in `earthx_record_state` (F5). Felder, alle in der Sprache der Quelle:

- `source_key` (STAC: Collection-ID; CKAN: Paket-`id`), `title`, `description`, `publisher` (CKAN: `publisher_name` bzw. `organization.title`, je Quelle in der Seed-Datei benannt; STAC: `providers` mit Rolle `licensor`/`producer`), `doi`;
- `licence_statements`: jede Lizenzangabe **wörtlich** (STAC `license` und Link `rel=license`; CKAN `license_id`, `license_url`, je Ressource `license`), für die Regel in M5-20;
- `spatial`: Rechteck, wo die Quelle eine Geometrie gibt (STAC `extent.spatial`, GovData `extras.spatial` als GeoJSON), die Geometrie selbst bis 64 KB; sonst `spatial_text` (z. B. Ortsname bei opendata.swiss [S]), Auflösung in M5-20 (Enrich); fehlt beides, `extent_known: false` (§5.3);
- `temporal`: Intervall, offen erlaubt;
- `data_kind`, `delivery`, `account` nach §5.2; `category` aus `category_of`, `keywords` aus `listed_keywords` (M5-40 G6, A11);
- `source_url` nach §6 und daneben `landing_url` (die Seite des Datensatzes, für die Stichprobe in M5-20);
- `distributions`: je Ressource bzw. Asset Adresse, Format, Medientyp, Titel — gespeichert, nie abgefragt.

### 5.2 Datentyp, Lieferweg, Zugang [A]

- **`data_kind`** aus Formaten bzw. Medientypen, Daten vor Dienst vor Dokument: Raster (GeoTIFF, TIFF, JPEG2000, NetCDF, HDF, Zarr, ASCII-Grid), Vektor (Shapefile, GeoJSON, GML, GeoPackage, KML, FlatGeobuf, GeoParquet), Tabelle (CSV, XLSX, XLS, ODS), Dienst (WMS, WMTS, WFS, WCS, OGC API, ATOM), Dokument (PDF, DOC/DOCX); sonst `other`. STAC-Collections ohne Medientyp in `item_assets`: `raster`. Die Formatlisten liegen als Tabelle im Code mit Tests je Schreibweise (EU-URIs und Freitext, `adr/0025` §3).
- **`delivery`:** `download`, wenn eine Ressource eine Datei ist; sonst `service`, wenn ein Dienst da ist; sonst leer. `order` und `on_request` erkennt Extract nicht sicher; ein leerer Wert macht den Fund in M5-20 `invalid` (Warteliste), nie geraten.
- **`account`:** DCAT `access_rights` „public“ → `none`; „restricted“/„non-public“ → leer (M5-20, Otto); fehlt die Angabe und gibt es eine Datei oder einen Dienst → `none`.

### 5.3 Filter und Personendaten

- **Ohne räumliche Angabe (Zusatz Otto, 17.11.2026):** Ein Fund ohne `spatial` und ohne `spatial_text` wird **nicht** verworfen. Er bleibt `extracted` mit `extent_known: false` und wird im Lauf-Bericht gezählt; ob und wie er gelistet und gefiltert wird, entscheidet M5-20 (M5-Plan §2 Punkt 12). Das ersetzt für M5-19 den Filter „räumliche Angabe vorhanden“ aus `adr/0033` §5 und §13; die Seed-Datei von GovData filtert deshalb nicht serverseitig nach `extras_spatial`.
- **„Keine Geodaten“:** Eine Regel dafür gibt es nicht, und M5-19 schlägt keine automatische vor [A]: Formate allein trennen nicht (eine CSV mit Messstationen ist Geodaten, M5-Plan §2 Punkt 12), und ohne räumliche Angabe ist ein Fund nur „Ausdehnung unbekannt“. Verworfen wird nur, was Otto sperrt: `blocked.yaml` mit Grund `not_geodata` (`adr/0033` §9), angewandt ab M5-20. Eine Formatregel wäre eine Frage an M5-20, wenn der erste Lauf zeigt, dass sie sich lohnt.
- **Pflichtfelder:** ohne Titel oder ohne einen Link nach §6 → `invalid` mit Grund.
- **Personen:** `author`, `maintainer`, ihre Mail-Felder, DCAT-Kontaktpunkte und Personen-`providers` kommen nicht in die Zwischenform (`adr/0033` §5). Die Rohantwort behält sie bis zum nächsten Lauf (`adr/0025` §5.3); sie wird nie geloggt.

## 6. Link „Source“ (Vorgabe Otto, 17.11.2026)

**Wortlaut:** Der Link „Source“ jedes Eintrags führt so direkt wie möglich zu den Daten – zuerst Viewer oder Download-Seite beim Anbieter, wo man sie direkt laden kann; sonst die Seite des Datensatzes; nie nur die Startseite des Anbieters. Beim Extract die direkteste Angabe der Quelle nehmen (bei CKAN Ressourcen-URL bzw. Viewer vor Paketseite).

**Regel im Extract (Vorschlag, F1 = 1):** Die Kandidaten des Fundes werden nach Rang geordnet; der erste gültige gewinnt.

| Rang | Was | CKAN | STAC-API |
|---|---|---|---|
| 1 | **Viewer oder Download-Seite beim Anbieter** | Ressource mit Format HTML bzw. Medientyp `text/html` (DCAT `accessURL` ohne `downloadURL`), die keine Doku ist (Ressourcentyp `documentation` oder Titel mit „Dokumentation“, „Metadaten“, „Beschreibung“ fallen weg) | Link `rel=via` oder `alternate` mit `type: text/html` |
| 2 | **Seite des Datensatzes beim Anbieter** | Paketfeld `url` (DCAT `landingPage`) | Link `rel=about` mit `text/html` |
| 3 | **Seite des Datensatzes im Katalog** | `catalog_page` der Seed-Datei mit dem Paketnamen; dort stehen alle Ressourcen mit Download | `catalog_page` der Seed-Datei mit der Collection-ID (z. B. der STAC-Browser der FSDI [S]) |

- **Gültig** ist nur: `https`, ohne Benutzerteil, Host ein Name (keine IP), höchstens 2 048 Zeichen, kein Steuerzeichen; **nicht die Startseite**: Pfad leer, `/` oder nur ein Sprachkürzel (`/de`, `/fr/` …) ohne Abfrage. Ein `http`-Link wird nicht umgeschrieben, sondern übersprungen (Prinzip 15).
- **Dienste** (WMS, WFS, WCS, OGC API, ATOM) sind nie der Link „Source“: eine Capabilities-Antwort ist keine Seite für Menschen. Sie bleiben Distributionen.
- **Einzelne Dateien** sind nach F1 = 1 nie der Link „Source“: Ein Klick lädt sonst ohne Ansage eine große Datei, und bei mehreren Dateien wäre eine davon nur ein Teil. Sie bleiben Distributionen; mit F1 = 2 käme eine einzige Datei als Rang zwischen 1 und 2.
- **Kein gültiger Kandidat:** Fund `invalid` mit Grund `no_link`, im Bericht gezählt.
- **Ein Wechsel des Hosts** des gewählten Links ist nach `adr/0033` §11 (U1) freigabepflichtig; das prüft M5-20. M5-19 vergleicht ihn nur und zählt ihn im Lauf-Bericht.
- Die Vorgabe kommt als Zeile ins Entscheidungslog (in diesem PR) und mit der Umsetzung als Nachtrag in `adr/0033` §5 (Zeile „Link zur Quelle“) und in den Docstring von `ListedEntry.source_url`.

## 7. Handeinträge CORINE und Landsat (Vorgabe Otto, 17.11.2026)

Heute zeigen beide auf eine Übersichtsseite (`backend/catalog/listed/`, M5-17, [#367](https://github.com/oscipal/earthX/pull/367)). Nach derselben Regel, **ungeprüft aus der Sitzung [S]**. **F3 und F4 sind offen (Otto, 17.11.2026):** Otto sieht sich die Links im Browser an; bis zu seiner Entscheidung bleiben Links und Zugang beider Einträge unverändert.

| Eintrag | heute | Vorschlag | Was man dort bekommt [S] |
|---|---|---|---|
| CORINE | https://land.copernicus.eu/en/products/corine-land-cover | https://land.copernicus.eu/en/products/corine-land-cover/clc2018 | Seite des Datensatzes CLC 2018 mit Reiter „Download“ (Vektor und Raster 100 m); Laden nach Anmeldung mit EU Login, Zugang bleibt `free_account` |
| Landsat | https://www.usgs.gov/landsat-missions/landsat-commercial-cloud-data-access | https://landsatlook.usgs.gov/ | Kartenviewer der USGS mit Suche und Vorschau der Szenen; Laden der Dateien nach Anmeldung mit einem kostenlosen Konto der USGS (EROS Registration System), dann `free_account` statt `requester_pays` |

## 8. Befehle für Ottos lokalen Lauf (PowerShell, nach der Umsetzung)

Ein Compose-Dienst `harvest` im Profil `harvest` wie `materialize`, nie bei einem einfachen `docker compose up`. Mit PR 1 laufen die beiden STAC-Quellen; GovData und opendata.swiss kommen mit PR 2 (CKAN). Befehle für PowerShell, aus dem Checkout:

```powershell
git fetch origin
git switch claude/exciting-pascal-qdtaff
git pull
docker compose build
docker compose up -d
docker compose run --build --rm harvest fsdi-stac
docker compose run --rm harvest earth-search
docker compose run --rm harvest fsdi-stac
docker compose run --rm harvest earth-search
"SELECT run_id, source_id, status, stop_reason, requests, not_modified, found_new, found_changed, found_unchanged, invalid, gone, extent_unknown FROM earthx_harvest_run ORDER BY run_id;" | docker compose exec -T postgres sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB'
"SELECT source_id, state, reason, extent_known, count(*) FROM earthx_record_state GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 4;" | docker compose exec -T postgres sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB'
"SELECT source_id, extracted->>'title' AS title, extracted->>'source_rank' AS rank, extracted->>'source_url' AS source FROM earthx_record_state WHERE state = 'extracted' ORDER BY random() LIMIT 10;" | docker compose exec -T postgres sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB'
```

- Jeder Lauf druckt einen kurzen Bericht (Anfragen, davon `304`, Funde neu/geändert/unverändert/ungültig/weg, Ausdehnung unbekannt); Rückgabe 0 nur bei `done`.
- **Zweiter Lauf** je Quelle: FSDI ohne `ETag` mit `found_unchanged` = alle und ohne neue Übergänge; Earth Search mit einer Anfrage und `not_modified` 1. Das ist die Abnahme M5-Plan §7 Punkt 3 für diese beiden Quellen.
- **Links:** Die dritte Abfrage zeigt zehn zufällige Funde mit dem Link „Source“ und seinem Rang (1 Viewer/Download-Seite, 2 Seite beim Anbieter, 3 Seite im Katalog). Bitte einige im Browser öffnen; die Adressen bleiben in deiner Datenbank, nicht im Repo.
- **Neu ableiten ohne Abruf** nach einer Codeänderung: `docker compose run --build --rm harvest fsdi-stac --reextract`.
- Zu prüfen bei deinem ersten Lauf: ob der STAC-Browser der FSDI (Rang 3) die Collection zeigt; Zahl der Collections je Quelle.

`--build` beim ersten Lauf ist nötig, weil `docker compose build` Dienste in einem Profil nicht mitbaut (Befund 15.11.2026, M5-30-Plan §8.10).

- Der zweite Lauf von `fsdi-stac` zeigt die Abnahme M5-Plan §7 Punkt 3 für diese Quelle: keine geänderten Funde, ohne `ETag` nur die Liste, Hash gleich.
- Zu prüfen bei Ottos erstem Lauf: Endpunkt und Felder von data.gv.at (aus Sitzungen nicht erreichbar, `adr/0025` §10), Feld der räumlichen Angabe bei opendata.swiss und data.gv.at, Zahl der Geodatensätze je Quelle (M5-35 F-Messung „erst messen“), ob die Links aus §6 auf die richtige Seite führen (zehn Funde je Quelle ansehen; eine Abfrage dafür kommt mit der Umsetzung).

## 9. Fragen an Otto

**F1 — Rangfolge des Links „Source“ (§6)?**
1. Viewer/Download-Seite → Seite des Datensatzes beim Anbieter → Seite im Katalog; nie eine einzelne Datei, nie ein Dienst, nie die Startseite **(Empfehlung)**
2. wie 1, aber eine **einzige** Daten-Datei zwischen Rang 1 und 2
3. Datei zuerst, wo es genau eine gibt

**F2 — Gilt die Regel auch für die sieben vollen Einträge?** Heute zeigt „Source“ dort die API-Adresse (z. B. die STAC-API), keine Seite.
1. Ja, als eigene kleine Aufgabe danach (neues Feld je YAML für die Seite, Frontend nimmt es), nicht in M5-19 **(Empfehlung)**
2. Ja, in M5-19 PR 2
3. Nein, nur gelistete Einträge

**F3 — CORINE: Link „Source“?**
1. Seite des Datensatzes CLC 2018 mit Download im CLMS-Portal **(Empfehlung)**
2. Produktseite wie heute (alle Jahre, je mit eigener Seite)
3. Anderer Link (bitte nennen)

**F4 — Landsat: Link „Source“?**
1. LandsatLook (Viewer mit Download); `access` nach deinem Klick: `free_account` mit Konto der USGS, falls Laden eines verlangt **(Empfehlung)**
2. EarthExplorer der USGS (ebenfalls Konto)
3. Wie heute (Zugang über den Cloud-Bucket, `requester_pays`)

**F5 — Wo endet M5-19?**
1. Bei der Zwischenform je Fund in `earthx_record_state` mit Hash und Zustand (`extracted`, `filtered`, `invalid`, `gone`); keine Zeile in `earthx_listed_entry`, sichtbar wird erst mit M5-20 **(Empfehlung)**
2. M5-19 schreibt schon unsichtbare Zeilen in `earthx_listed_entry` (Zustand `needs_rule`)

**F6 — Grenzen der neuen Katalog-Hosts (`www.govdata.de`, `ckan.opendata.swiss`, `www.data.gv.at`) in `hosts.yaml`?**
1. Je 2 Verbindungen und 1 s Abstand; Prüfung in `hosts.yaml` kennt Seed-Quellen als Besitzer **(Empfehlung)**
2. Je 1 Verbindung und 1 s
3. Je 6 Verbindungen und 1 s

**F7 — Seed-Dateien in M5-19?** Der Merge einer Datei ist die Freigabe der Quelle (`adr/0033` §4).
1. Alle fünf (FSDI, Earth Search, GovData, opendata.swiss, data.gv.at); data.gv.at mit `enabled: false`, bis dein erster Lauf den Endpunkt bestätigt **(Empfehlung)**
2. Nur FSDI und GovData, die übrigen mit M5-20
3. Alle fünf aktiv

**F8 — Schnitt in zwei PRs?**
1. **PR 1 (dieser):** Plan, Log-Zeile, Handeinträge (§7), Migration 024, Seed-Lader und -Dateien, `hosts.yaml`, Fetch mit Lauf-Sperre, Lauf-Befehl und Compose-Profil, STAC-Extraktor, Link-Regel. **PR 2:** CKAN-Extraktor mit inkrementellem und vollem Lauf, Datentyp- und Formattabellen, Anleitung in der README **(Empfehlung)**
2. PR 1 nur Tabellen, Seed, Fetch und Lauf-Befehl; PR 2 beide Extraktoren, Link-Regel und Handeinträge

## 9a. Antworten Otto (17.11.2026)

- **F1 = 1:** nur Seiten, keine einzelne Datei, kein Dienst, nie die Startseite.
- **F2 = 1:** volle Einträge als eigene kleine Aufgabe danach, **M5-55**.
- **F3, F4 offen:** Otto prüft die Links aus §7 im Browser; bis dahin Links und Zugang von CORINE und Landsat unverändert. Die Handeinträge kommen nach seiner Entscheidung.
- **F3, F4 (Otto, 17.11.2026, nach Prüfung):** CORINE und Landsat bleiben unverändert, Links und Zugang; nichts nachziehen. Damit ist PR 1 komplett; PR 2 (CKAN, README) macht eine neue Session nach dem Merge von PR 1.
- **F5 = 1, F6 = 1, F7 = 1, F8 = 1.** A1–A6 gelten.
- **Zusatz:** Funde ohne räumliche Angabe nicht verwerfen, sondern mit „Ausdehnung unbekannt“ in der Zwischenform halten; Listen und Filtern entscheidet M5-20. Verworfen wird nur, was nach einer Regel keine Geodaten ist (eine solche Regel gibt es nicht, §5.3). Personenfelder weiter verwerfen.

## 10. Auslegungen (gelten, wenn Otto nicht widerspricht)

- **A1** Lauf-Sperre je Quelle als Lauf-Zeile mit Frist und Herzschlag (§3), nicht als Advisory-Lock (`adr/0025` §8 nannte ihn; M5-37 „Lauf-Zeile mit Frist“).
- **A2** `HostResting` und `RobotsDisallowed` beenden den Lauf `interrupted`; ungesehene Funde behalten ihren Zustand. `adr/0025` §6.2 („Funde gehen nach `stale`“) betrifft veröffentlichte Einträge; die gibt es aus dem Harvest erst mit M5-20, der den Übergang dann baut.
- **A3** Ein Fund ist `gone` nur nach einem vollständigen Lauf ohne ihn; Grabstein mit `source_removed` beim zweiten Fehlen kommt mit M5-20 (`adr/0033` §9), weil erst dann geerntete Einträge veröffentlicht sind.
- **A4** Die Zwischenform ist die Grundlage des Hashes für „geändert“; ändert nur der Code die Ableitung, leitet `--reextract` aus der gespeicherten Rohantwort neu ab, ohne neu zu holen (`adr/0025` §5.1).
- **A5** Fixtures sind synthetisch (eigene kleine Antworten in der Form von STAC und CKAN), keine Kopien echter Katalogantworten: Die Lizenz der Metadaten der Kataloge ist offen (`adr/0033` §15); geklärt wird sie mit der Freigabe der Quelle in M5-20.
- **A6** `--reextract` und `--full` sind Schalter des Lauf-Befehls; der Bericht ist Text auf der Konsole (Deutsch, Zahlen je Zustand und Grund, ohne Adressen). Der Bericht mit Stichprobe und Freigabedatei ist M5-20.
- **A7** (PR 2) Ein Text, den die Quelle je Sprache gibt (opendata.swiss: Titel, Beschreibung, Schlagworte, Organisation [S]), wird in der Reihenfolge Deutsch, Englisch, Französisch, Italienisch gelesen, dann weitere Sprachen alphabetisch; der erste nicht leere gewinnt. Grund: Die Suche kennt Deutsch und Englisch (`adr/0026`), Englisch ergänzt das Review (`adr/0025` §8). Die übrigen Sprachen bleiben in der Rohantwort.
- **A8** (PR 2) CKAN blättert mit `start` über eine nach `id` sortierte Liste (§4.2); jede Seite beginnt mit dem letzten Paket der vorigen. Ändert sich die Zahl der Pakete oder fehlt dieses Paket am Seitenanfang, hat sich die Liste beim Lesen verschoben, und ein Paket kann übersprungen sein. Ein voller Lauf endet dann `done`, setzt aber nichts auf `gone` („weg nicht geprüft“); ebenso, wenn die volle Liste leer ist (neu aufgebauter Index, Filter passt nicht mehr). Ein inkrementeller Lauf endet `interrupted` mit `listing_moved` (Migration 026) und zählt nicht als letzter Lauf, der nächste fragt also ab dem Lauf davor. Das hält A3 auch bei einer Liste, die sich beim Lesen bewegt.
- **A9** (PR 2) Die Zwischenform bekommt die Felder `geometry` (§5.1, bis 64 KB, nur Typ und geprüfte Koordinaten) und je Distribution `format`. Bei STAC sind beide leer; weil sich die Form ändert, zählt der erste Lauf nach dem Merge die gültigen STAC-Funde einmal als „geändert“, ohne Übergang.
- **A10** (PR 2, 18.11.2026) Auch ein inkrementeller CKAN-Lauf ist ein Durchgang mit gespeichertem Stand (unter einem Seitenbudget kann er mehrere Läufe brauchen). Verschiebt sich seine Liste beim Lesen, läuft er trotzdem durch und rückt den Stand vor; was die Verschiebung übersprungen hat, liest der nächste volle Durchgang (höchstens `full_every_days` später). Der Bericht sagt es. Grund: Ein inkrementeller Durchgang, der bei jeder Verschiebung zurückgehalten würde, wüchse bei opendata.swiss (rund 1 000 Änderungen am Tag) über jedes Budget. Das ersetzt für inkrementelle Läufe den Abbruch mit `listing_moved` aus A8.

## 11. Tests (Plan)

Ohne Netz, mit `tests/fixtures` und einer Transport-Attrappe am `Gateway` wie bei `materialize` (KLAERUNGEN, `adr/0025` K7):

- **Seed:** unbekanntes/fehlendes Feld, `listed`, `proto-`, `http`-Endpunkt, Host ohne Eintrag in `hosts.yaml`, Dateiname ≠ `source_id`, `enabled: false`.
- **Fetch:** `304` auf gespeichertes `ETag`; zweiter Lauf ohne Änderung ohne Folgearbeit (Abnahme §7 Punkt 3); `rel=next` auf fremden Host; Schleife; `max_requests_per_run`; `HostResting`; `RobotsDisallowed`; `5xx` nach den Versuchen; kaputtes JSON; Antwort über der Grenze; Lauf-Sperre: zweiter Lauf derselben Quelle bricht ab, abgelaufene Frist wird übernommen.
- **Extract:** jeder Datentyp; gemischte Formate; Personenfelder nicht in der Zwischenform und nicht im Log; ohne räumliche Angabe `extracted` mit `extent_known: false`; ohne Titel `invalid`; mehrere Lizenzangaben wörtlich; Schreibvarianten der Formate.
- **Link-Regel:** jeder Rang; Startseite (leer, `/`, `/de/`) verworfen; `http`, IP, Benutzerteil, `javascript:`, Überlänge, Steuerzeichen verworfen; Dienst und Datei nie gewählt (F1 = 1); kein Kandidat → `invalid`.
- **Integration (Postgres):** Migration 024 auf 023; Übergänge protokolliert; Fremdschlüssel `run_id`.
- **Handeinträge:** bestehende Tests von `listed/` grün mit den neuen Links.

## 12. Umsetzung

### 12.1 PR 1 ([#375](https://github.com/oscipal/earthX/pull/375)), Stand 17.11.2026

- **Migration 024** (`catalog/migrations/024_harvest.sql`): `earthx_harvest_run` mit Lauf-Sperre (eindeutiger Teilindex auf `running`, Frist 5 min), `earthx_harvest_source`, `earthx_raw_record`, `earthx_record_state`, `earthx_state_transition`; Fremdschlüssel `earthx_listed_entry.run_id`. SQL in `catalog/harvest_store.py`.
- **Seed:** `catalog/sources.py` (streng, `listed` und `proto-` vergeben), fünf Dateien unter `backend/catalog/sources/` (data.gv.at `enabled: false`), im Image. Kein CKAN-Filter nach räumlicher Angabe (Zusatz Otto).
- **`hosts.yaml`:** drei Katalog-Hosts mit 2 Verbindungen und 1 s; die Prüfung der Registry kennt die Hosts der Seed-Dateien (F6). `.importlinter`: die zwei neuen `catalog`-Module stehen in der Verbotsliste des `runner` (verschärft, nicht gelockert).
- **Lauf:** `discovery/harvest.py` (`run_harvest`, Bericht, CLI mit `--reextract`; `--full` erst mit CKAN wirksam), alle Anfragen über `open_source_gateway` mit `obey_robots`, Obergrenze je Lauf; Compose-Dienst `harvest` im Profil `harvest`.
- **STAC:** `discovery/stac.py` (Seiten über `rel=next`, bedingt nur bei einseitiger Liste, Schleifenschutz; Collection → Zwischenform), `discovery/extract.py` (Zwischenform, Datentyp nach Medientyp), `discovery/links.py` (Link-Regel F1 = 1).
- **Nachtrag** in `adr/0033` §5 und §13 (Link „Source“, „Ausdehnung unbekannt“) und im Docstring von `ListedEntry.source_url`.
- **Nicht in PR 1:** CKAN und README-Abschnitt (PR 2, neue Session); CORINE und Landsat bleiben unverändert (F3, F4).
- **Auslegung bei der Umsetzung:** Ein Fund, der eine Seite der Liste ohne gültige ID erreicht, wird gezählt (`ungültig`), aber nicht gespeichert, weil er keinen Schlüssel hat.
- **Nach dem Review (Subagent, 17.11.2026):** Ein Fund mit fremder Form (NUL, einzelne Surrogate, falsche Typen) macht nur sich selbst `invalid` mit Grund `shape`, nicht den ganzen Lauf; Texte werden davon bereinigt. Ein Lauf, dessen Sperre ein anderer nach abgelaufener Frist geschlossen hat, schreibt nichts mehr (`interrupted`, `lease_expired`). Eine Rohantwort über 1 MB wird nicht gespeichert und bleibt auch nach `--reextract` `too_large`. Herausgeber nur aus Providern mit Rolle `licensor` oder `producer`. Die Startseiten-Regel erkennt auch Index-Dateien und eine Abfrage, die nur die Sprache wählt. Ein Datenbankfehler zeigt auf der Konsole nur seine Art, nie seinen Text. Eine Collection, die beim Blättern doppelt kommt, zählt einmal; ein neuer Grund bei `invalid` gilt als Änderung mit Übergang.

### 12.2 Befund aus Ottos lokalem Lauf (17.11.2026) und Nachtrag in PR 1

**Befund Otto:** `fsdi-stac` Lauf 1 neu 515, Lauf 2 unverändert 515 (ohne `304`, Hash) – ok. `earth-search` Lauf 1 „neu 9, ungültig 9“; Lauf 2 eine Anfrage, `304`, „unverändert 9, ungültig 0“.

**1. Ursache der 9 ungültigen [A, aus dem Code; die Collections von Earth Search sind aus der Sitzung nicht lesbar, auf GitHub liegen sie nicht]:** Ein Fund wird nur aus vier Gründen ungültig (`no_title`, `no_link`, `shape`, `too_large`). Earth-Search-Collections tragen Titel, und ein Formfehler wäre ab dem Review `shape`. Bleibt `no_link`: Die Seed-Datei `earth-search.yaml` hat keine Katalogseite (`catalog_page: null`), und der Extraktor nimmt für Rang 1 und 2 nur Links mit `type: text/html` (`via`, `alternate`, `about`). Die Collections von Earth Search haben offenbar keinen solchen Link. Das ist kein Fehler im Code, sondern eine Lücke in der Regel für Quellen ohne eigene Seite je Collection; welche Seite stattdessen gilt, ist eine Entscheidung (F9, unten). Der Bericht nennt den Grund jetzt selbst (Punkt 2); Ottos nächster Lauf bestätigt ihn.

**2. Bericht eindeutig:** zwei Zeilen statt einer. „Dieser Lauf“: neu, geändert, unverändert, weg. „Stand der Quelle“: gültig (davon Ausdehnung unbekannt), ungültig mit Gründen; das gilt auch für Funde, die ein `304` oder ein gleicher Hash unverändert ließ. In `earthx_harvest_run` sind `invalid` und `extent_unknown` ebenso der Stand nach dem Lauf. Kollektionen ohne gültige ID stehen nur im Bericht („ohne Kennung übersprungen“), weil sie keinen Schlüssel haben.

**3. Neu auswerten bei neuer Extraktor-Version:** Migration 025 gibt `earthx_record_state` eine Spalte `extractor_version`. Die Version ist ein Fingerabdruck aus dem Code des Extraktors und der Link-Regel, den Tabellen der Kategorien und Katalog-Tags und der Einstellung `catalog_page` der Quelle; sie ändert sich mit jeder Änderung daran, ohne Pflege von Hand. Ein Fund mit gleichem Hash, aber anderer Version wird neu ausgewertet; hinter einem `304` aus der gespeicherten Rohantwort, ohne Anfrage. Zustände von vor Migration 025 gelten als veraltet. Für Earth Search heißt das: Sobald F9 entschieden und die Seed-Datei geändert ist, macht der nächste Lauf die 9 Funde ohne neue Anfrage gültig.

**F9 — Link „Source“ für Earth Search?** Die Collections tragen keinen Link auf eine Seite für Menschen; Element 84 hat keine Seite je Collection auf eigenem Host. Bis zur Antwort bleibt `earth-search.yaml` unverändert, die 9 Funde bleiben ungültig.
1. STAC Browser von Radiant Earth als Katalogseite: `https://radiantearth.github.io/stac-browser/#/external/earth-search.aws.element84.com/v1/collections/{id}` – zeigt Collection, Items und Dateien zum Laden, für jede Collection; Host ist nicht der Anbieter **(Empfehlung)**
2. Dokuseite von Element 84 auf GitHub, `https://github.com/Element84/earth-search/blob/main/docs/collections/{id}.md` – Seite des Anbieters, aber nicht für jede Collection vorhanden (z. B. `sentinel-2-c1-l2a` fehlt [P\*])
3. Links ohne `type` als Seite zulassen (`about`, `via`), wenn sie nicht auf Datei, JSON oder Dienst zeigen – ob Earth Search solche hat, ist nicht belegt; gilt dann für alle STAC-Quellen

**Antwort Otto zu F9 (17.11.2026): 1.** Der STAC Browser von Radiant Earth ist die Katalogseite von `earth-search.yaml`, als Einstellung dieser Quelle, nicht als allgemeine Ausnahme. Weil die Katalogseite Teil der Extraktor-Version ist, wertet der nächste Lauf die 9 Funde aus den gespeicherten Rohantworten neu aus, auch hinter `304`.

### 12.3 PR 2 (CKAN, README), Stand 17.11.2026

- **CKAN:** `discovery/ckan.py`: `package_search` mit `rows=100`, `sort=id asc`, `start` als Versatz, `fq` der Seed-Datei; die Abfrage setzt `gateway` zusammen. Ein Fund = ein Paket samt Ressourcen, Schlüssel ist die Paket-`id`, Hash je Paket (kein `ETag`, §4.2).
- **Inkrementell und voll:** Voll ist der erste Lauf, jeder mit `--full` und jeder, dessen letzter voller Lauf `full_every_days` oder länger zurückliegt; sonst fragt der Lauf zusätzlich `metadata_modified:[<Beginn des letzten erfolgreichen Laufs − 1 h> TO *]` (UTC). Ein abgebrochener Lauf zählt nicht als letzter, ein `--reextract` auch nicht (er fragt die Quelle nicht). Nur ein voller Lauf setzt `gone` (A3, A8). Die Art steht in `earthx_harvest_run.kind` und im Bericht.
- **Extract:** Titel, Beschreibung (`notes` bzw. `description`), Herausgeber nach `publisher_field` (Paket oder `extras`), DOI (nur in DOI-Form), Lizenzangaben wörtlich (`license_id`, `license_url`, je Ressource `license` und `rights` [S]), räumliche Angabe aus `spatial` (in `extras` oder am Paket: GeoJSON → Rechteck und Geometrie, sonst Text als `spatial_text`), Zeit aus `temporal_start`/`temporal_end` bzw. `temporals`, Kategorie aus INSPIRE-Themen (`theme` und Schlagworte als URI), EU-Themen (`theme` und Gruppen mit dem Namen eines EU-Themas [S]), Gruppen und Schlagworten. Personenfelder (`author`, `maintainer`, Mail, Kontaktpunkte) kommen nicht in die Zwischenform.
- **Datentyp, Lieferweg, Zugang** nach §5.2 aus einer Formattabelle in `discovery/extract.py` (Freitext und EU-URIs, ein Test je Schreibweise). Eine Ressource ist eine Datei, wenn ihr Format eine ist oder sie eine `download_url` ohne Dienst- oder Seitenformat hat.
- **Link „Source“** (§6, F1 = 1): Rang 1 eine Ressource mit Format HTML bzw. `text/html` ohne `download_url`, keine Doku (Ressourcentyp oder Titel mit Dokumentation, Metadaten, Beschreibung, auch auf Englisch, Französisch, Italienisch) und keine Capabilities-Adresse; Rang 2 das Paketfeld `url`; Rang 3 `catalog_page` mit dem Paketnamen.
- **Extraktor-Version** je Protokoll (`extract.extractor_version`): Code des Extraktors, gemeinsamer Code, Tabellen, `catalog_page` und bei CKAN `publisher_field`.
- **README:** Abschnitt „Quellen ernten (M5-19)“; Felder der Seed-Dateien in `backend/catalog/sources/README.md`.
- **Nach dem Review (Subagent, 17.11.2026):** Eine riesige Ganzzahl als Koordinate (auch im STAC-`extent`) und ein `type`, der keine Zeichenkette ist, machen nur die Ausdehnung unbekannt statt den Lauf abzubrechen. Eine leere volle Liste setzt nichts auf `gone`. Die Seiten überlappen um ein Paket, damit auch eine Verschiebung bei gleicher Zahl auffällt (A8). Ein inkrementeller Lauf wertet danach die Funde neu aus, die ein älterer Extraktor beurteilt hat, aus ihren Rohantworten. Eine Seite mit mehreren Paketen ohne neues beendet den Lauf mit `shape` (Quelle ignoriert `start`). Das Paketfeld `url` ist kein Link „Source“, wenn es auf eine Datei oder einen Dienst zeigt. Eine `http`-`access_url` verdeckt keine `https`-`url` derselben Ressource.
- **Nicht in PR 2:** data.gv.at bleibt `enabled: false`, bis Ottos erster Lauf den Endpunkt bestätigt (F7). Kein Abruf echter Kataloge aus der Sitzung; Fixtures synthetisch (A5).
- **Zu prüfen bei Ottos Lauf:** ob die Felder [S] bei GovData und opendata.swiss so heißen (`publisher_name`, `spatial`, `temporals`, `keywords` je Sprache, `rights`); ob tiefe Versätze bei GovData (bis `start` ≈ 165 000) ohne Zeitüberschreitung antworten; Größe der Tabellen nach einem vollen Lauf von GovData; wie oft sich die Liste von GovData während eines vollen Laufs (rund 30 min) verschiebt – geschieht das fast immer, setzt der Harvest dort praktisch nie `gone`, und es braucht eine andere Prüfung (z. B. Abgleich der IDs).

### 12.4 Befund aus Ottos Lauf (18.11.2026) und Nachtrag in PR 2

**Befund Otto:** `opendata-swiss` und `govdata` brachen sofort mit „robots.txt verbietet den Abruf“ ab (einmal Zeitüberschreitung beim Lesen von `robots.txt`, also `host_resting`); `fsdi-stac` 515 und `earth-search` 9 „geändert“, wie nach A9 erwartet. Die `robots.txt` von `ckan.opendata.swiss` ist die Standarddatei von CKAN (`Disallow: /api/`, `Crawl-delay: 10`); `www.govdata.de` erlaubt nur großen Suchmaschinen etwas, sonst `Disallow: /`.

**Entscheidung Otto (18.11.2026), umgesetzt:**

- **Ausnahme je Quelle:** neues Pflichtfeld `robots_exception` in jeder Seed-Datei, `null` oder `path` und `evidence`. Der Pfad muss genau der Pfad des `endpoint` mit `/` am Ende sein (nur die Metadaten-API), `evidence` die `https`-Adresse der Anbieter-Doku. `gateway` liest `robots.txt` weiter und hebt nur das `Disallow` für diesen Pfad auf genau diesem Host auf; ein Pfad mit `.`- oder `..`-Segment fällt nie darunter. Der Bericht nennt die Ausnahme mit „angewandt“ oder „nicht gebraucht“.
- **`Crawl-delay`:** galt schon (`gateway` nimmt den größeren Wert aus `hosts.yaml` und `Crawl-delay`); ein Test hält das jetzt auch unter einer Ausnahme fest. Bei opendata.swiss heißt das 10 s je Anfrage, ein voller Lauf also rund 165 Anfragen in knapp 30 min.
- **opendata.swiss:** Ausnahme für `/api/3/action/`, Beleg das Handbuch „opendata.swiss API nutzen“. Die Adresse der Seite stammt aus einer Suche [S] und wurde aus der Sitzung nicht geöffnet.
- **GovData:** `endpoint` jetzt `https://ckan.govdata.de/api/3/action` (API-Host laut Doku; Sekundärquellen nennen auch `www.govdata.de/ckan/api/3/action` [S]); `hosts.yaml` führt `ckan.govdata.de` statt `www.govdata.de` mit denselben Grenzen. Keine Ausnahme: Ob `ckan.govdata.de` die API sperrt, zeigt Ottos nächster Lauf; nur dann kommt eine Ausnahme mit Beleg dazu. Die Katalogseite (Rang 3 des Links „Source“) bleibt auf `www.govdata.de`, sie wird nie abgefragt.

### 12.5 Befund aus Ottos erstem vollem Lauf von opendata.swiss (18.11.2026) und Nachtrag in PR 2

**Befund Otto:** Ausnahme von `robots.txt` angewandt, 10 s Abstand eingehalten. Nach 102 Seiten (10 099 Funde, alle gültig, **4 561 ohne Ausdehnung**, 146 MB, rund 1,4 MB je Seite) ab Seite 103 dreimal `429` im 10-s-Takt; der Unterbrecher pausierte den Host 300 s, der Lauf endete `failed`.

**Ursache [P]:** `gateway` wiederholt einen `429` bis zu dreimal und wartet dabei höchstens 10 s (`Retry-After` gekappt), also praktisch im Takt von `Crawl-delay`; nach dem dritten Fehlschlag öffnet der Unterbrecher, und der Harvest wertete die letzte `429` als Fehler der Quelle.

**Entscheidung Otto (18.11.2026), umgesetzt:**

1. **`429`:** Die `Policy` des Harvest hat `retry_rate_limited = false`: `gateway` gibt einen `429` sofort mit seinem `Retry-After` zurück. Der Harvest wartet dann selbst: nach `Retry-After` (Sekunden oder HTTP-Datum), sonst 2 min, danach jeweils doppelt so lang bis 30 min; ein Host, den der Unterbrecher nach diesen `429` pausiert, wird genauso abgewartet. Während des Wartens erneuert der Lauf seine Frist (Herzschlag je Minute). Mehr als 60 min Warten insgesamt beendet den Lauf `interrupted` mit `rate_limited` (Migration 027), mit gespeichertem Stand. Der Bericht nennt Zahl der `429` und die Wartezeit.
2. **Fortsetzen:** Ein voller CKAN-Lauf ist ein **Durchgang** über einen oder mehrere Läufe (Migration 027, `earthx_harvest_source`): Nach jeder geschriebenen Seite steht dort der Versatz der nächsten Seite und das Paket, mit dem sie beginnen muss (Überlappung aus A8), dazu Zahl und Prüfstand der Liste. Ein Lauf, der abbricht (Obergrenze, `429`, Host ruht, Fehler der Quelle), endet `interrupted`; der nächste Lauf setzt den Durchgang dort fort, auch mit `--full`. Gespeicherte Funde bleiben gültig. `gone` setzt erst der Lauf, mit dem der Durchgang durchläuft, für alles, was kein Lauf des Durchgangs gesehen hat, und nur, wenn sich die Liste über alle Läufe nicht verschoben hat (A3, A8). Danach fragt ein inkrementeller Lauf ab dem Beginn des Durchgangs minus 1 h, weil früh gelesene Seiten sich während der Pause geändert haben können. Den abgebrochenen Lauf vom 18.11. übernimmt Migration 027: Die Liste ist nach `id` sortiert, also geht der Durchgang beim Paket mit der größten gespeicherten `id` weiter, an Versatz „Zahl der Funde − 1“ (bei 10 099 Funden der Anfang von Seite 103).
3. **Datenmenge, `fl` [P\*, Quelltext CKAN `ckan/logic/action/get.py`, `ckan/lib/search/query.py`]:** Mit `fl` liefert `package_search` nicht das Paket, sondern die flachen Felder des Suchindex (`extras_<key>` als `<key>`, Ressourcen nur als parallele Listen wie `res_url`, `res_format`, sofern indiziert); ohne `fl` das gespeicherte Paket (`validated_data_dict`). Einen Parameter, der das Paket ohne große Felder liefert, gibt es nicht. **`fl` würde die Zwischenform ändern:** ein eigener Extraktor auf Indexfeldern; ob Organisationstitel, Texte je Sprache (opendata.swiss), Ressourcentitel und -typen dort stehen, ist offen. Deshalb noch kein `fl` im Lauf, sondern eine Messung: `python -m earthx.discovery.harvest <ckan-quelle> --measure` holt die erste Seite einmal wie der Harvest und einmal mit `fl` (die Indexfelder, die der Extract braucht), und nennt Größe (wie übergeben und als gzip), Kompression der Quelle, die größten Felder der Pakete und Ressourcen und welche `fl`-Felder gefüllt zurückkommen. Nichts wird gespeichert, keine Adresse ausgegeben. Hinweis: Die 146 MB sind entpackte Bytes; sendet die Quelle gzip, ist die Übertragung kleiner. **F10 = 1 (Otto, 18.11.2026):** erst die Messung (`--measure`) ansehen; lohnt sich `fl` (Seite deutlich kleiner, nötige Felder gefüllt), kommt ein eigener Extraktor auf Indexfeldern als kleine Folgeaufgabe, sonst kein `fl`. Bis dahin liest der Harvest ohne `fl`.
4. **Für M5-20 festgehalten:** Bei opendata.swiss trugen nach 102 Seiten **4 561 von 10 099 Funden (45 %) keine räumliche Angabe** (weder Geometrie noch Ortstext). Enrich der Ausdehnung (M5-20) betrifft also fast die Hälfte eines CKAN-Katalogs; ob solche Einträge gelistet, gefiltert oder zurückgestellt werden, entscheidet M5-20 (Zusatz Otto, 17.11.2026, §5.3). Die Stichproben aus #379 (Ortstexte, Felder) zeigen, ob die Angabe fehlt oder unter einem anderen Feld steht.

### 12.6 Befund aus Ottos Fortsetzungslauf (18.11.2026, nachmittags) und Nachtrag in PR 2

**Befund Otto:** Fortsetzung ab Paket 10 098: Die erste Anfrage bekam sofort `429`, danach Warten 2/4/8/16/30 min, jede Anfrage wieder `429`; nach 60 min `interrupted`, Stand gespeichert. Kein `Retry-After`. Gesperrt seit dem ersten `429` (~13:12 MEZ) mehr als 2 h; vorher rund 100 Seiten / 146 MB in 17 min. Eine Grenze dokumentiert opendata.swiss nicht; vermutlich ein Tages- oder Mengenkontingent.

**Entscheidung Otto (18.11.2026), umgesetzt:**

1. **Seiten je Lauf:** neues Pflichtfeld `max_pages_per_run` in jeder Seed-Datei, `null` (ohne Grenze) oder eine Zahl; nur für CKAN. opendata.swiss: **40** (rund 4 000 Pakete, etwa 56 MB je Lauf, weniger als die Hälfte dessen, was vor der Sperre durchging); ein voller Durchgang von rund 165 Seiten braucht so fünf Läufe, einen am Tag. Ist das Budget erreicht, endet der Lauf `interrupted` mit `page_budget` (Migration 028), und der nächste setzt fort. Damit das auch für inkrementelle Läufe gilt, sind sie ebenfalls Durchgänge (A10).
2. **Sperrfrist:** Endet ein Lauf `rate_limited`, ruht die Quelle (`rest_until`, Migration 028): mit `Retry-After` so lange wie verlangt, sonst bis zum Beginn des nächsten Tages (00:00 UTC, 01:00 MEZ). Ein Lauf davor startet nicht; der Befehl sagt, bis wann die Quelle ruht. `--reextract` fragt die Quelle nicht und läuft weiter.
3. **`--measure`** hält dieselben Regeln: Es startet nicht, solange die Quelle ruht; es liest zwei Seiten und lehnt ab, wenn `max_pages_per_run` kleiner ist; ein `429` setzt dieselbe Sperrfrist.
4. **GovData:** `max_pages_per_run: null`, der Wert folgt nach dem ersten Lauf.

**Offen für später [A]:** Ein voller Durchgang über fünf Tage sieht bei opendata.swiss fast sicher neue oder gelöschte Pakete; die Überlappungsprüfung meldet das, und der Durchgang setzt dann nichts auf `gone` (A8). Ein Abgleich der IDs am Ende (z. B. `package_list`, eine Anfrage für alle Namen) könnte `gone` trotzdem erlauben; das ist eine Frage für M5-20 oder M5-24, wenn sich das Muster bestätigt.
