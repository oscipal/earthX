# M5-17 — Stufe „gelistet“ für alle Datentypen und erste Handeinträge

**Status (16.11.2026):** F1–F3 = 1, Lizenz-Einstufung und Attribution bestätigt (Otto, 16.11.2026, §4a); umgesetzt im Draft-PR [#367](https://github.com/oscipal/earthX/pull/367). Offen: F4 (Regionen aus dem Rechteck, §4b).
**Aufgabe:** M5-17 aus `docs/plans/m5/m5-discovery-und-suche.md` §6.2. **Stufe B.** Hängt von M5-40 ab (gemergt mit #356, #358).
**Grundlagen:** `adr/0033` (§5, §13: „erste Handeinträge als YAML unter `listed/`, nur von `catalog-load` gelesen“), `adr/0027` §4.1 (W0), §6.1 (`access.account`, Nachtrag `paid`, `access.delivery`), `adr/0025` §6.1a, `adr/0026` §8.2 (Kürzel CLC, LS), M5-40-Plan §5.2, §6 (A7, A11), §9a; M5-Plan §2 Punkt 9 (keine Marken) und Punkt 12.

Belegstufen: **P** am Quelltext gelesen (Stand `main` eb7079c), **S** Vorwissen ohne Abruf, vor dem Merge von Otto per Klick zu prüfen, **A** eigene Ableitung. Aus der Session geht keine Anfrage an CLMS, USGS oder AWS (Auftrag; `adr/0002`).

---

## 1. Ziel

1. **Stufe „gelistet“ für alle Datentypen** (M5-Plan §2 Punkt 12) im Entscheidungslog festhalten; die Zeile fehlte bisher.
2. **Erste zwei Handeinträge** unter `backend/catalog/listed/`: CORINE Land Cover (`free_account`) und Landsat Collection 2 Level-2 (`requester_pays`), je mit Art des Zugangs (`access.account`, `access.delivery`), `category`, `keywords`, abgeleiteten `regions`, räumlicher und zeitlicher Ausdehnung und dem Link „Source“.
3. Tests, dass die echten Einträge lesen, mit den Kategorien und Schlagworten zusammenpassen, nie in die Registry geraten und in Postgres mit Regionen ankommen.

## 2. Ausgangslage im Code [P]

- `catalog.listed.ListedEntry` mit `data_kind` (`raster` … `other`), `access` (`account`, `account_provider`, `delivery`), `category`, `keywords`, Ausdehnung, `source_url`, `approved_on`; Lader `load_listed()` für `listed/`, streng wie M5-13. `tier` immer `catalog`, `legal_status` immer `cleared`, Link nur `https://`, `free_account` braucht `account_provider`.
- `catalog-load` schreibt Handeinträge nach `earthx_listed_entry`, leitet `regions` aus der Ausdehnung gegen `regions.json` ab und normalisiert die Schlagworte (`listed_keywords`, A11, `catalog_tags.yaml`).
- Data catalogue (M5-40 PR 2): gelistete Einträge stehen in der Gruppe ihrer `category`, rechts der Link „Source“ (Tooltip „Open at the source“), **keine Marke** (`Marks` gibt für gelistete `null` zurück, M5-40 F6). Neue Felder erscheinen nicht als Zeilen (A7). Am Frontend ändert M5-17 deshalb nichts.
- `listed/` ist leer bis auf die README; das `Dockerfile` kopiert das Verzeichnis schon.
- Das Bewertungs-Set der Suche führt CLC und LS mit `id: null` (`tests/fixtures/search/evaluation_set.yaml`).

## 3. Die beiden Einträge (Vorschlag)

| Feld | CORINE Land Cover | Landsat Collection 2 Level-2 |
|---|---|---|
| `dataset_id` | `corine-land-cover` | `landsat-c2-l2` (wie Earth Search und Planetary Computer, `adr/0023`; ein späterer voller Eintrag löst die Zeile ab, `adr/0033` §11) |
| Umfang | die Reihe 1990, 2000, 2006, 2012, 2018 mit Änderungsschichten, ein Eintrag (F1) | Level-2 (Oberflächenreflexion und -temperatur) von Landsat 4–9, wie `adr/0026` §8.2 |
| `data_kind` | `vector` (F2) | `raster` |
| `category` | `land_cover` | `optical` |
| `access.account` | `free_account` | `requester_pays` |
| `access.account_provider` | `EU Login` (Konto des CLMS-Portals) [S] | `Amazon Web Services` |
| `access.delivery` | `download` | `download` (Objekte im Bucket `usgs-landsat`, `us-west-2`) [S] |
| Link „Source“ | `https://land.copernicus.eu/en/products/corine-land-cover` [S] | `https://www.usgs.gov/landsat-missions/landsat-commercial-cloud-data-access` (F3) [S] |
| Herausgeber | European Environment Agency (EEA) | U.S. Geological Survey |
| Räumlich | EEA-39 ohne Überseegebiete: `[-31.5, 27.5, 45.0, 71.5]`, nach außen gerundet [S] | weltweit `[-180, -90, 180, 90]` [S] |
| Zeitlich | 1986-01-01 bis 2018-12-31 (Bezugsjahre von CLC 1990 ab 1986, von CLC 2018 bis 2018) [S] | ab 1982-08-22 (erste TM-Szenen von Landsat 4), offen [S] |
| Lizenz (Vorschlag, §5) | Copernicus-Datenpolitik (Verordnung (EU) 1159/2013), frei mit Quellenangabe | gemeinfrei (U.S. Public Domain), Nennung erbeten, nicht verlangt |

- **Schlagworte** deutsch und englisch (`adr/0026` F7); `catalog-load` schreibt sie klein (A11).
- **DOI und Zitat** `null`: Beide Produkte haben DOIs je Fassung bzw. je Sensor; ohne Abruf trage ich keine ein [A].
- **`approved_on`** ist der Tag der Datei; Otto setzt den Tag des Merge, falls er abweicht (M5-40-Plan A3).
- **Keine Marken:** Konto und Requester Pays stehen nur in `earthx:access` der Collection; der Data catalogue zeigt für gelistete Einträge keine Marke und keinen Hinweistext, nur „Source“ (M5-Plan §2 Punkt 9; `adr/0027` F2 sah einen Hinweistext vor, Punkt 9 geht vor).

## 4. Fragen an Otto

**F1 — CORINE: ein Eintrag für die Reihe oder einer je Bezugsjahr?**
1. Ein Eintrag `corine-land-cover` für die ganze Reihe; die Seite der Quelle führt zu allen Jahren **(Empfehlung)**
2. Je Bezugsjahr ein Eintrag (`corine-land-cover-2018` …), wie WorldCover 2020/2021
3. Nur CLC 2018

**F2 — CORINE: `data_kind`?**
1. `vector`: das Ausgangsprodukt sind Polygone (Mindestfläche 25 ha), das 100-m-Raster ist daraus abgeleitet **(Empfehlung)**
2. `raster`

**F3 — Landsat: wohin führt „Source“?**
1. USGS-Seite „Landsat Commercial Cloud Data Access“, die den Zugang mit Requester Pays beschreibt **(Empfehlung)**
2. Seite des Datensatzes in der AWS Open Data Registry (`registry.opendata.aws/usgs-landsat`)
3. USGS-Seite der Level-2-Produkte (dort auch EarthExplorer mit kostenlosem Konto, also eher `free_account`)

## 4a. Antworten Otto (16.11.2026)

- **F1 = 1, F2 = 1, F3 = 1:** wie in den Dateien umgesetzt, keine Änderung nötig.
- **Lizenz-Einstufung und Attribution bestätigt** wie §5: CORINE Copernicus-Datenpolitik mit Nennung wie vorgeschlagen; Landsat gemeinfrei, Nennung erbeten; beide `tier: catalog`.
- **Prüfauftrag:** CORINE soll alle abgedeckten Länder als Regionen tragen, wenn `regions.json` alle Staaten kennt.

## 4b. Befund zu den Regionen und Frage F4

**Befund [M], lokal ohne Netz:** `regions.json` kennt alle Staaten (Natural Earth 1:50m) und die Unterteilungen von DE, AT, CH und LI. Mit dem Rechteck `[-31.5, 27.5, 45.0, 71.5]` bekommt CORINE 70 Staaten und 62 Unterteilungen. **Alle 39 EEA-Länder sind dabei** (der Satz „nur DE, AT, CH, LI“ im ersten Bericht war ungenau: der Test prüfte nur diese vier als Mindestmenge; jetzt prüft er alle 39). Zu viel sind rund 30 Staaten, die CORINE nicht abdeckt, z. B. MA, DZ, TN, LY, EG, EH, IL, JO, LB, SY, IQ, IR, SA, RU, UA, BY, MD, GE, AM, AZ, GL, FO.

**Ursache [P]:** Ein gelisteter Eintrag hat als räumliche Ausdehnung nur ein Rechteck (`SpatialExtent.bbox`); `catalog-load` leitet die Regionen aus allen Grenzstücken ab, die das Rechteck mehr als am Rand berühren (M5-40-Plan §5.2). Die Regionen kommen nach M5-40 §5.2 nie aus der Datei. Dasselbe Rechteck gilt im Filter mit der AOI: eine AOI in Marokko findet CORINE. Ein Rechteck um Europa erfasst Nordafrika und den Nahen Osten zwangsläufig.

**F4 — Wie bekommt ein Handeintrag die genaue Abdeckung?**
1. Neues Feld `coverage_states` im Handeintrag (Staaten nach ISO 3166-1); `catalog-load` bildet die Ausdehnung aus deren Umrissen in `regions.json`, Regionen und AOI-Filter folgen daraus, das Rechteck bleibt die Hülle. Für CORINE die 39 EEA-Länder. Kleine Änderung an `ListedEntry` und `listed_store`, ohne Migration (`footprint` ist schon eine beliebige Geometrie) **(Empfehlung)**
2. Feld `footprint` mit eigenem Umriss (GeoJSON) im Handeintrag, wie es der Harvest aus der Quelle liest; genauer an Küsten, aber große Datei und von Hand kaum prüfbar
3. So lassen: Rechteck reicht für die Stufe „gelistet“; die genaue Geometrie kommt mit dem Harvest (M5-19, M5-20)

Bis zur Antwort bleibt CORINE beim Rechteck; F4 = 1 oder 2 wäre ein eigener kleiner Schritt (in diesem PR oder als Folgeaufgabe, je nach Größe).

## 5. Zur Bestätigung im PR (Lizenz-Einstufung und Attribution, nie durch die Session)

| | CORINE Land Cover | Landsat C2 L2 |
|---|---|---|
| `spdx_id` | `null` | `null` |
| Name, URL | Copernicus data and information policy, `https://land.copernicus.eu/en/data-policy` [S] | U.S. Public Domain (USGS), `https://www.usgs.gov/information-policies-and-instructions/crediting-usgs` [S] |
| `commercial_use`, `distribution`, `derivatives` | ja, ja, ja | ja, ja, ja |
| `share_alike`, `attribution_required` | nein, ja | nein, nein |
| `tier` | `catalog` (gelistet, `adr/0025` §6.1a) | `catalog` |
| Attribution unverändert | © European Union, Copernicus Land Monitoring Service <Jahr>, European Environment Agency (EEA) | Landsat image courtesy of the U.S. Geological Survey |
| Attribution verändert | wie oben, mit „(modified)“ | wie oben, mit „(modified)“ |

`<Jahr>` steht in der Datei als `1990–2018`, weil der Eintrag die Reihe meint (F1 = 1).

## 6. Auslegungen

- **A1** Der Eintrag „Stufe gelistet für alle Datentypen“ ist eine Log-Zeile, kein Code: `DataKind` deckt alle Typen seit M5-40 ab; Karte und Processing bleiben Raster.
- **A2** CLC und LS bleiben im Bewertungs-Set `null`, bis M5-42 gelistete Einträge in die Suche bringt; mit einer Kennung müsste der Eintrag in der Registry stehen, und dort steht ein gelisteter nie (M5-35 B5).
- **A3** Keine Zeile in `hosts.yaml`: Die Plattform fragt die Hosts gelisteter Einträge nie an; den Link prüft später der rotierende Health-Check (M5-24).
- **A4** Keine Coverage Map: Ein gelisteter Eintrag hat nur seine Ausdehnung (B11 Stufe „Katalogeintrag“, `adr/0033` §5).

## 7. Umsetzung

1. Log-Zeilen (§2 Punkt 12; M5-17 mit Auslegungen) und dieser Plan.
2. `backend/catalog/listed/corine-land-cover.yaml`, `backend/catalog/listed/landsat-c2-l2.yaml`; jeder Wert mit seiner Herkunft im Kommentar wie bei `datasets/`.
3. Tests: Einträge des Repos lesen und gehen ohne Verlust durch `to_plain`; Kategorie aus `categories.yaml`; Schlagworte überleben die Normalisierung ohne Ersatzwörter und enthalten deutsche und englische; keine Kennung zugleich in `datasets/` oder `retired.yaml`; `registry()` kennt sie nicht; Zugang wie bestellt. Integration: `write_hand_entries` mit den echten Einträgen und `regions.json` gibt CORINE die DACH-Staaten und Landsat alle Regionen; `api` liefert beide mit `earthx:access` und Link „Source“.
4. `test_api_collection_search.py` leert nach `catalog-load` die Tabelle gelisteter Einträge: Seit M5-17 schreibt `catalog-load` die zwei Handeinträge, und diese Tests prüfen die erste Seite der vollen Einträge.
5. `ruff`, `pytest`, `lint-imports`.

Lokal bei Otto nach dem Merge (die Session ruft nichts ab):

```bash
docker compose run --rm catalog-load
```

Danach im Data catalogue: CORINE unter „Land cover and land use“, Landsat unter „Optical imagery“, je mit „Source“; beide Links per Klick prüfen (§3, [S]).
