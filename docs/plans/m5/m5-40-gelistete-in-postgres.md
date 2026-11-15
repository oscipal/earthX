# M5-40 — Gelistete Einträge in Postgres: Plan-Schritt

**Status (15.11.2026):** Plan mit Fragen F1–F10 im Draft-PR; Umsetzung nach Ottos Antworten im selben PR, höchstens zwei PRs (F2).
**Aufgabe:** M5-40 aus `docs/plans/m5/m5-discovery-und-suche.md` §6.2 (Folgeaufgabe aus `plans/m5/m5-35-skalierbarkeit.md` §10). **Stufe B.** Hängt von M5-39 ab (`adr/0033`, gemergt mit #352). M5-17 wartet auf den Merge.
**Grundlagen:** `adr/0033` (angenommen, F1–F11 = 1; F12: Nachträge als erster Commit dieses PR, erledigt), `plans/m5/m5-35-skalierbarkeit.md` §6.1 (B5), §8a (F3, F4), `adr/0025` §6.1a, §7, `adr/0031` §8, `adr/0027` §6.1, `adr/0017`, `adr/0024` R1, `KLAERUNGEN.md` B11, B13, `projektuebersicht.md` Prinzip 16, `plans/vp3/ui-05-data-catalogue.md`.

Belegstufen wie in `adr/0025`: **P** am Quelltext gelesen (Stand `main` 943f950), **M** in dieser Sitzung gemessen (lokal, synthetisch, ohne Netz), **A** eigene Ableitung.

---

## 1. Ziel

Gelistete Einträge (alle Datentypen, auch ohne direkten Download) liegen in Postgres statt als YAML in Git, ausgelegt auf 10⁶ (M5-35 F3 = 1). Dazu:

1. Ablage mit den neuen Feldern aus `adr/0033` §5: `access.account` mit `paid`, `access.delivery`, `earthx:data_kind`, `earthx:regions`, räumliche und zeitliche Ausdehnung, Herkunft je Eintrag (Regel, Lauf, Freigabedatei).
2. Sperrliste `backend/catalog/blocked.yaml` mit Prüfung beim Laden und Grabstein in Postgres; `api` antwortet für die ID mit `410`.
3. `/stac/collections` und der Data catalogue blättern statt der Gesamtliste; Filter nach AOI, Region und Zeit über Indizes vorbereitet (API, keine Bedienelemente).
4. Kein Prozess hält gelistete Einträge ganz im Speicher; jede `api`-Instanz kann jede Seite beantworten.
5. Handeinträge unter `backend/catalog/listed/` liest nur `catalog-load` und schreibt sie in dieselbe Tabelle (`adr/0033` F11).

**Nicht in M5-40** (`adr/0033` §13): Lizenzkatalog, `grants/`, Warteliste, Lauf-Bericht, Stichprobe, Freigabedatei und `discovery publish` (M5-20); Harvest (M5-19, M5-21); Health-Checks (M5-24); Textsuche über gelistete Einträge (F7, M5-42); Suchfeld und AOI-Schalter im Data catalogue (M5-23); erste echte Handeinträge CORINE und Landsat (M5-17).

---

## 2. Ausgangslage im Code [P]

- **Registry:** `catalog.datasets.registry()` liest alle YAML unter `backend/catalog/datasets/` einmal je Prozess (`@cache`). `listed/` gibt es nicht. Gelistete Einträge dürfen nicht dorthin (M5-35 B5).
- **`catalog-load`** (`catalog/load.py`): eine Transaktion; Migrationen, Collections nach pgstac (`pgstac.py` `load_registry`), Entfernen weggefallener föderierter Collections, Suchindex `earthx_dataset_search` (Migration 016). Migrationen bis 019.
- **`GET /stac/collections`** (`api/federating_client.py:687–707`): ohne Parameter alle Collections aus pgstac bis `MAX_PAGE` 10 000 in einer Antwort; mit `q`, `bbox`, `datetime`, `limit`, `offset` die Collection Search (`api/collection_search.py`) über `catalog.search.search_datasets`, Seiten per `offset`, `numberMatched` exakt. `GET /stac/collections/{id}` ist der Weg von stac-fastapi-pgstac ohne eigene Übersteuerung.
- **Ausgeschiedene Einträge** (`adr/0017`): `RetiredDatasetError` → `410` an Rezepten, Kacheln, Jobs; die Collection ist aus pgstac entfernt.
- **`AccountKind`** (`catalog/registry.py:231`): `none`, `anonymous_token`, `free_account`, `requester_pays`. Kein `paid`, kein `delivery`.
- **Frontend** (Bericht des `explorer`): `fetchCollections()` (`frontend/src/api.ts:124–129`) holt einmal je Start `GET /stac/collections` ohne Parameter; `datasetsFrom` (`datasets.ts:208–238`) macht aus jeder Collection ein `DatasetOption` im Store. Der Data catalogue (`components/DataCatalogue.tsx`, `catalogue.ts`) zeigt alle Einträge in Gruppen nach `earthx:category`, ohne Blättern; eine Collection ohne bekannte Kategorie steht in der Gruppe „Other“ am Ende (UI-05 (e)). Marken: „Prototype“, „Account“ (bei `account` ≠ `none`, dann Link „Source“ statt „Add“), Maturity. Control Panel, Suche, Layer-Manager, Permalink und Downloads brauchen nur Einträge, die sich hinzufügen lassen, also volle.
- **Image** (`backend/Dockerfile:57–63`): kopiert `datasets/`, `retired.yaml` und drei Dateien einzeln.

## 3. Messung: pgstac oder eigene Tabelle bei 10⁶ [M]

**Verfahren.** Eigene Wegwerf-Datenbank im lokalen Postgres 16 der Sitzung (PostGIS 3.4.2, pgstac 0.9.12, `shared_buffers` 128 MB, 4 Kerne), danach gelöscht. 10⁶ synthetische Einträge aus `generate_series` mit festem Startwert: 85 % Boxen im Raum DACH, 10 % Europa, 5 % weltweit, Kantenlänge log-gleichverteilt 0,003°–6°, 0,5 % global; 65 % mit Zeitraum (20 % davon offen); zwei Regionen je Eintrag (Staat, Unterteilung); Datentyp, Konto und Lieferweg nach festen Anteilen; Titel und Beschreibung aus einem Wortschatz von 90 Wörtern. Dieselben Zeilen einmal als pgstac-Collections (`INSERT INTO pgstac.collections`), einmal in einer eigenen Tabelle mit Spalten `footprint geometry`, `time_span tstzrange`, `regions text[]` und partiellen Indizes (GiST, GiST, GIN, B-Baum) auf `state = 'published'`. Je Abfrage 5 Läufe, Median; Seite zu 50 Einträgen. Keine echten Daten, kein Netz.

| Abfrage (Treffer) | pgstac ohne eigene Indizes | pgstac mit GiST und B-Baum auf `datetime` | eigene Tabelle: Seite | eigene Tabelle: Zählung |
|---|---|---|---|---|
| erste Seite (10⁶) | 177 ms | 29 ms | 1,4 ms | 40 ms |
| Seite bei Eintrag 900 000 | 1 422 ms (`offset`) | 1 268 ms | 1,4 ms (Keyset) | — |
| Box einer Stadt (22 019) | 293 ms | 190 ms | 92 ms | 83 ms |
| Box eines Landes (634 527) | 310 ms | 605 ms | 11 ms | 2 411 ms (bis 10 001 gezählt: 22–73 ms) |
| ein Jahr (pgstac 572 223, eigene 222 230) | 202 ms | 48 ms | 2,0 ms | 59 ms |
| Region (29 747) | 3 122 ms (CQL2 `a_contains`) | 3 209 ms | 2,2 ms | 118 ms |
| Stadt + Zeitraum + Datentyp | 442 ms | 392 ms | 94 ms | 89 ms |
| Land + Region + Jahr (6 464) | — | — | 43 ms | 90 ms |
| `q` mit zwei Wörtern | 21 470 ms | — | nicht gemessen (F7) | — |

- **Laden:** 10⁶ Collections in pgstac 47,6 s; eigene Tabelle mit Indizes rund 18 s. Größe beider rund 1,6 GB mit Collection-JSON.
- **Warum pgstac langsamer bleibt:** `collection_search` zählt bei **jeder** Seite alle Treffer (`collection_search_matched`, `count(*)` über die Sicht `collections_asitems`), blättert nur mit `offset` und filtert Felder außerhalb von Geometrie und Zeit über JSON-Ausdrücke ohne Index; `q` rechnet `to_tsvector` je Zeile. Die Zahlen bei „ein Jahr“ unterscheiden sich, weil pgstac Collections ohne Zeitraum mitzählt.
- **Folgen [A]:** (1) Eine eigene Tabelle mit Keyset-Blättern hält jede Seite unter 100 ms, ohne Gesamtliste. (2) Eine exakte Zahl der Treffer kostet bei weiten Filtern Sekunden; bis 10 001 gezählt bleibt sie unter 100 ms (F4). (3) Die Seite der Stadt-Box liest 22 000 Zeilen vom Heap und sortiert sie; bei kaltem Cache der teuerste Fall, aber unter 100 ms.
- Grenzen: ein Rechner, ein Lauf je Datensatz, kleiner Cache; Größenordnungen, keine Zusage für den Betrieb. Die Messung wird mit dem fertigen Schema wiederholt (§5.6).

## 4. Fragen an Otto

**F1 — Ablage gelisteter Einträge (§3)?**
1. Eigene Tabelle `earthx_listed_entry` neben pgstac mit Indizes für Fläche, Zeit, Region und Blättern; pgstac hält weiter nur volle Einträge **(Empfehlung)**
2. pgstac-Collections mit zusätzlichen Indizes
3. pgstac als Ablage, eigene Tabelle nur als Index daneben

**F2 — Schnitt in höchstens zwei PRs?**
1. Dieser PR: Nachträge, Plan, Backend (Tabelle, Lader für `listed/` und `blocked.yaml`, Grabstein, `/stac/collections` mit Seiten und Filtern, Messskript); ohne Parameter bleibt die Antwort bis PR 2 wie heute. PR 2: Frontend blättert, und ohne Parameter kommt nur noch die erste Seite **(Empfehlung)**
2. Alles in diesem PR (deutlich über 400 Zeilen)
3. Dieser PR nur Backend ohne API, PR 2 API und Frontend

**F3 — `GET /stac/collections` ohne Parameter?**
1. Erste Seite statt Gesamtliste: `limit` Vorgabe 100, höchstens 1 000; Link `next` mit Keyset-Marke `token` statt `offset`; Reihenfolge nach Titel, dann ID; volle und gelistete Einträge gemischt; neuer Parameter `entry` (`full`, `listed`), damit das Frontend die vollen ganz laden kann **(Empfehlung)**
2. Wie 1, aber Reihenfolge nach ID wie heute
3. Gesamtliste bleibt, höchstens 10 000, wie heute

**F4 — `numberMatched` bei großen Treffermengen (§3: exakt bis 2,4 s)?**
1. Exakt bis 10 000; darüber fehlt das Feld (STAC erlaubt das), das Frontend zeigt ohnehin keine Zahl **(Empfehlung)**
2. Immer exakt
3. Schätzung des Planers

**F5 — Gelistete Einträge im Data catalogue?**
1. In der vorhandenen Gruppe „Other“ am Ende, nach Titel; die nächste Seite lädt beim Scrollen von selbst, ohne Knopf und ohne Zähler **(Empfehlung)**
2. Wie 1, aber mit Knöpfen „Previous“/„Next“ wie im Control Panel
3. Eigene Gruppen je Datentyp (Raster, Vektor, Tabelle, …)

**F6 — Marken an gelisteten Einträgen?**
1. Keine: Die Zeile zeigt Titel und den Link „Source“ statt „Add“, auch bei Konto oder `paid`; die Marken voller Einträge bleiben wie heute **(Empfehlung)**
2. „Account“ wie bei vollen Konto-Einträgen (W0), sonst keine
3. Neue Marken für Lieferweg und Datentyp

**F7 — Textsuche `q` über gelistete Einträge?**
1. Noch nicht: `q` sucht bis M5-42 nur volle Einträge; gelistete findet man über Blättern und die Filter. Das Frontend hat bis M5-23 kein Suchfeld, es fehlt also nichts Sichtbares **(Empfehlung)**
2. Jetzt in den Suchindex aus M5-22 aufnehmen (volle Tabellenscans, Sekunden je Anfrage bei 10⁶)

**F8 — Grenzen für `earthx:regions` (Staaten ISO 3166-1, Länder und Kantone ISO 3166-2, `adr/0033` §5)?**
1. Natural Earth (Public Domain), Staaten weltweit und die Unterteilungen von DE, AT, CH, LI, vereinfacht als Datei im Repo (rund 1 MB); die Lizenz stufst du ein, `license-checker` legt einen Vorschlag mit Beleg vor **(Empfehlung)**
2. Amtliche Grenzen von BKG, BEV und swisstopo (Namensnennung, drei Lizenzen)
3. In M5-40 nur Spalte, Index und Filter; Regionen leer, Ableitung mit M5-19

**F9 — „Nichts verschwindet“, so gemeint?**
1. (a) Jeder Eintrag bleibt durch Blättern erreichbar, keine stille Obergrenze wie heute bei 10 000; (b) ein entfernter gelisteter Eintrag antwortet `410` mit Grund statt `404`; (c) alle sechs vollen Einträge und alle Funktionen des Frontends bleiben, wie sie sind **(Empfehlung)**
2. Anders (bitte kurz sagen)

**F10 — Zeitfilter und Einträge ohne Zeitraum (35 % in der Messung)?**
1. Wie bei vollen Einträgen heute: Sie fallen nicht heraus und stehen je Seite in `ignored_filters_by_collection` **(Empfehlung)**
2. Sie fallen bei einem Zeitfilter heraus

## 5. Umsetzung (mit den Empfehlungen)

### 5.1 Tabelle (Migration `020_listed_entry.sql`)

Eine Zeile je gelistetem Eintrag; der Grabstein ist dieselbe Zeile ohne Inhalt.

| Spalte | Inhalt |
|---|---|
| `dataset_id` | Primärschlüssel; nie mit `proto-` (`adr/0033` F8); nie eine ID aus `datasets/` oder `retired.yaml` mit Zustand `published` |
| `source_id`, `source_key` | Quelle und Schlüssel bei der Quelle, eindeutig zusammen; Handeinträge: `listed` und die ID (A3) |
| `state` | `published`, `in_review`, `needs_rule`, `blocked`, `tombstone`, `superseded` (Zustände aus `adr/0033` §7, §9, §11, schon jetzt, damit M5-20 den `CHECK` nicht ändert); sichtbar ist nur `published` |
| `content` | Collection-JSON, wie `api` es ausliefert; `NULL` genau bei `tombstone` |
| `content_sha256` | Hash der Normalform (für §11 in M5-20) |
| `sort_title` | Titel klein, ohne Akzente, für die Reihenfolge |
| `footprint` | `geometry(Geometry, 4326)`, aus der Ausdehnung; über die Datumsgrenze als zwei Teile |
| `time_span` | `tstzrange`, offenes Ende erlaubt; `NULL` ohne Zeitraum |
| `regions`, `data_kind`, `account`, `delivery`, `publisher`, `link_host`, `license_ref` | Filter- und Sperrfelder, je mit `CHECK` auf die festen Werte |
| `license_rule`, `rule_files_sha256`, `run_id`, `approval_file`, `approval_sha256`, `approved_on`, `published_at`, `harvested_at`, `checked_at` | Herkunft (`adr/0033` §10); `run_id` ohne Fremdschlüssel, bis M5-19 `earthx_harvest_run` anlegt |
| `removed_reason`, `removed_on` | beim Grabstein: `provider_request`, `not_geodata`, `quality`, `legal`, `other`, `source_removed` |

Indizes, alle partiell auf `state = 'published'`: GiST auf `footprint`, GiST auf `time_span`, GIN auf `regions`, B-Baum auf `(sort_title, dataset_id)` fürs Blättern. Dazu eindeutig `(source_id, source_key)` und B-Baum auf `(source_id, publisher)` und `link_host` für die Sperrliste. `data_kind`, `account`, `delivery` ohne eigenen Index (wenige Werte, nur zusammen mit anderen Filtern).

### 5.2 Eintrag, Felder und Lader

- **`ListedEntry`** (neu, `catalog/listed.py`): derselbe Kopf wie `DatasetConfig` (`adr/0025` §6.1a: ID, Titel, Beschreibung, Schlagworte, DOI/Zitat, `providers`, `maturity`, Ausdehnung, `license` mit `tier = catalog`, `legal_status: cleared`, `source` mit Link) plus `data_kind`, `access` (`account`, `delivery`), `regions` (abgeleitet, nie aus der Datei). Gleiche Kopfprüfungen, strenges Lesen wie M5-13; `tier` immer `catalog`; Link nur `https://`.
- **`AccountKind.PAID`** neu; in `datasets/` ein Ladefehler (nur gelistet). **`DeliveryKind`** (`download`, `service`, `order`, `on_request`) und **`DataKind`** (`raster`, `vector`, `table`, `document`, `service`, `other`) neu. Volle Einträge bekommen kein `delivery` (A4).
- **Collection-JSON** gelisteter Einträge: STAC-Kopf, `extent`, `links` (`via` zur Quelle, `license`), `earthx:entry: "listed"`, `earthx:data_kind`, `earthx:regions`, `earthx:access` (`account`, `delivery`), `earthx:legal_status`, `earthx:license_flags`, `earthx:listing` (Quelle, Lizenzregel, Datum der Freigabe, „zuletzt geerntet“, „zuletzt geprüft“). Kein `earthx:viewer`, keine Capabilities, kein `earthx:source.item_holding`; volle Einträge bekommen `earthx:entry: "full"`.
- **Regionen:** `catalog-load` schreibt die Grenzen (F8) in eine Tabelle `earthx_region` und leitet `regions` beim Schreiben eines Eintrags per `ST_Intersects` ab.

### 5.3 `catalog-load`

In derselben Transaktion wie heute, nach den vollen Einträgen:

1. `blocked.yaml` lesen und prüfen; `listed/` lesen und prüfen. Ein Fehler in einer der Dateien bricht den ganzen Lauf ab (wie heute).
2. Handeinträge schreiben (Upsert nur bei geändertem Hash), mit `approval_file = listed/<id>.yaml`, `approval_sha256` und `approved_on` aus der Datei, ohne Lauf und ohne Lizenzregel (A3).
3. Ein Handeintrag, der aus `listed/` verschwunden ist, wird Grabstein mit `source_removed` (A5).
4. Eine ID, die in `datasets/` steht, setzt die gelistete Zeile auf `superseded` (`adr/0033` §11).
5. Sperrliste anwenden: passende Zeilen werden Grabstein (Inhalt `NULL`, Grund, Datum). Indexgestützte `UPDATE`s, nie Zeile für Zeile in Python.
6. Ausgabe: Zahlen geschrieben, unverändert, Grabsteine neu, abgelöst.

### 5.4 Sperrliste `backend/catalog/blocked.yaml`

- Liste von Einträgen mit genau den Feldern `scope` (`entry`, `publisher`, `host`, `source`), `source_id`, `source_key` (nur bei `entry`), `publisher` (nur bei `publisher`), `host` (nur bei `host`), `reason` (Grundcode aus §5.1 ohne `source_removed`), `blocked_on`, optional `licence_hash` (für M5-20, `adr/0033` §9). **Kein Freitextfeld**, damit kein Name, keine Mail-Adresse und kein Wortlaut einer Anfrage hineinkommt; ein unbekanntes Feld ist ein Ladefehler.
- Prüfung beim Laden: doppelte Zeilen, Felder passend zum `scope`, Host als Name ohne Schema, Datum nicht in der Zukunft.
- Ins Image, gelesen nur von `catalog-load` (und ab M5-19 vom Harvester). `listed/` ebenso; ein Test prüft den Text des `Dockerfile` wie bei `prototype/`.

### 5.5 Lesepfad `api`

- **`GET /stac/collections/{id}`:** voller Eintrag aus pgstac; sonst gelisteter mit `published`; sonst Grabstein → `410` mit einem allgemeinen englischen Satz je Grundcode (kein Name, keine Quelle der Anfrage); sonst `404`.
- **`GET`/`POST /stac/collections`:** Seiten mit `limit` (Vorgabe 100, höchstens 1 000; mit `q` weiter 20) und `token` (Keyset aus Titel und ID, nicht signiert; eine kaputte Marke ist `400`). Filter `bbox`/`intersects`, `datetime`, neu `region` (Liste, ein Treffer genügt) und `entry`. Volle Einträge (≤ 10³) kommen wie heute aus `search_datasets`; gelistete aus der Tabelle; beide in einer SQL-Abfrage nach `(sort_title, dataset_id)` gemischt. `numberMatched` nach F4. `offset` bleibt für `q`.
- **Items:** `/stac/collections/{id}/items` und `/stac/search` mit einer gelisteten ID antworten wie eine Collection ohne Items (leere Liste), nie mit einer Anfrage an die Quelle (A6).
- **Mehrere Instanzen:** kein Zustand im Prozess; die Marke trägt alles, was die nächste Seite braucht. Die Allowlist von `gateway` bleibt aus vollen Einträgen (M5-35 B5).
- Nichts loggt Fläche, Region oder Marke (wie M5-22 §3.7).

### 5.6 Messskript

`scripts/listed-bench/` mit dem Verfahren aus §3 gegen das fertige Schema und den echten Lesepfad (SQL der API), Ergebnis in der PR-Beschreibung. Nur lokal, legt eine eigene Datenbank an und löscht sie. Indizes nach Bedarf aus dieser Messung.

### 5.7 Frontend (PR 2 nach F2)

- `fetchCollections` lädt die vollen Einträge mit `entry=full` und folgt den `next`-Links bis zum Ende (≤ 10³); Store, Control Panel, Suche, Layer-Manager, Permalink und Downloads bleiben unverändert.
- Data catalogue: Gruppen der vollen Einträge wie heute; die Gruppe „Other“ hängt Seiten mit `entry=listed` an, sobald ihr Ende sichtbar wird (F5). Seiten liegen im Zustand der Komponente, nicht im globalen Store.
- Zeile eines gelisteten Eintrags: Titel, Link „Source“, keine Marke (F6); Details aus den vorhandenen Zeilen von `catalogueRows`, keine neuen Zeilen (A7).
- Keine Filter-Bedienelemente (kommen mit M5-23).

### 5.8 Tests

- **Lader:** gültige Handeinträge; fehlendes und unbekanntes Feld; `paid` in `datasets/`; `proto-`-ID; `tier` ≠ `catalog`; Link ohne `https`; ID in `datasets/` und `listed/` zugleich; YAML-1.1-Werte. Sperrliste: jeder `scope`, falsche Feldkombination, unbekannter Grund, Freitextfeld, Datum in der Zukunft, Dubletten.
- **`catalog-load` (Integration, Datenbank der Tests):** idempotent (zweiter Lauf schreibt nichts); Grabstein bei Sperre je `scope`; Handeintrag entfernt → Grabstein; voller Eintrag mit gleicher ID → `superseded`; Abbruch lässt die Datenbank, wie sie war.
- **API:** Seiten bis zum Ende ohne Lücke und Dublette, auch wenn zwischen zwei Seiten ein Eintrag dazukommt oder geht; Marke kaputt, fremd, zu lang; `limit` 0 und über 1 000; `410` mit Text je Grund und ohne Inhalt; `404`; Filter Fläche über die Datumsgrenze, Region unbekannt, Zeit offen; Items einer gelisteten ID leer; zwei App-Instanzen gegen dieselbe Datenbank liefern dieselben Seiten; keine Fläche im Log.
- **Frontend:** Laden der vollen Einträge über mehrere Seiten; „Other“ lädt nach und hört am Ende auf; Fehler einer Folgeseite; keine Marke an gelisteten Zeilen.
- Alle Fixtures synthetisch.

## 6. Auslegungen

- **A1** „Filter vorbereiten“ heißt: API-Parameter und Indizes, keine Bedienelemente im Frontend.
- **A2** „Keine Hinweise oder Marken im Frontend“ heißt: M5-40 fügt keinen Text, keine Marke und keinen Zähler hinzu; Vorhandenes bleibt (F6 für Konto-Einträge).
- **A3** Handeinträge sind durch Ottos Merge der Datei freigegeben wie volle Einträge; ihre Herkunft ist die Datei mit Hash und Datum, `source_id` ist `listed`. Commits stehen nicht im Image; statt des Commits speichert die Zeile den SHA-256 der Datei, der sich in der Git-Geschichte wiederfinden lässt (gilt in M5-20 ebenso für Regeldateien und Freigabedateien).
- **A4** `access.delivery` nur für gelistete Einträge; volle Einträge sind lesbar und brauchen es nicht.
- **A5** Ein Handeintrag, den Otto aus `listed/` löscht, wird Grabstein mit `source_removed` statt still zu verschwinden.
- **A6** Gelistete Einträge haben keine Items; Items-Abfragen antworten leer und STAC-konform.
- **A7** Neue Felder (`data_kind`, `delivery`, `regions`) stehen in der Collection, aber nicht als Zeilen im Data catalogue.

## 7. Risiken

- **Zwei Ablagen für Collections** (pgstac für volle, eigene Tabelle für gelistete): Der Lesepfad mischt beide; Tests prüfen die gemeinsame Reihenfolge. Ein gelisteter Eintrag wird nie nach pgstac geschrieben.
- **Grenzdatei (F8):** Lizenz-Einstufung durch Otto nötig, bevor sie ins Repo kommt; bis dahin ist `regions` leer.
- **Kalter Cache:** Die Stadt-Box liest rund 22 000 Zeilen vom Heap; bei viel kleineren AOIs weniger. Bei Bedarf später Inhalt und Filterfelder in zwei Tabellen trennen.
- **Größe:** PR 1 liegt mit Migration, Lader, Lesepfad und Tests voraussichtlich bei 600–800 Zeilen ohne Fixtures; der Richtwert von 400 ist ohne einen dritten PR nicht zu halten.
