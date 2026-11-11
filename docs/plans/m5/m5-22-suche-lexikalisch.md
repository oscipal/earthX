# M5-22 — Suche Teil 1: Bewertungs-Set, Suchtext, lexikalischer Arm, Collection Search: Plan-Schritt

**Status (11.11.2026):** Plan angenommen (Otto, 11.11.2026; Antworten in §8a). Drei Teile nach F1: M5-22a umgesetzt im Draft-PR [#325](https://github.com/oscipal/earthX/pull/325) (§10); M5-22b umgesetzt im Draft-PR [#334](https://github.com/oscipal/earthX/pull/334) (§11); M5-22c folgt als eigener PR.
**Aufgabe:** M5-22 aus `docs/plans/m5/m5-discovery-und-suche.md` §6.2. **Stufe B.** Hängt von M5-13 ab (gemergt mit #311). M5-23 (Vektorarm, Suchfeld im Data catalogue) und M5-25 (JSON-LD, Sitemap) warten auf den Merge.
**Grundlagen:** `adr/0026` §4.1–§4.6, §6 Schritte 1 und 2, §8, §10, §11 (F1–F9), §12 Folgen 2, 4, 6, 9, 10; `adr/0024` R5, R7; `adr/0027` §6.1; `KLAERUNGEN.md` B10, B13; `architekturplan.md` 3.1, 5.1, 5.3, 10; Glossar-Begriffe aus `plans/m5/m5-07-worldcover.md` §10, `plans/m5/m5-08-stac-adapter-swissalti3d.md` §9, `plans/ds/ds-04-s1-anbinden.md` §8.

Belegstufen wie in `adr/0026`: **P** am Quelltext gelesen (Stand `main` 4440257), **M** in dieser Sitzung gemessen (nur das lokale Postgres der Sitzung, ohne Netz), **A** eigene Ableitung. Keine Quelle wird abgerufen.

---

## 1. Ziel

Die ersten beiden Stufen der Hybrid-Suche aus `adr/0026` §6 und ihre Schnittstelle:

1. **Bewertungs-Set** (§8 des ADR) als Fixture und Test, mit den Maßen aus §8.1 und der Regel für ruhende Fragen; Messung des Nullpunkts (keine Suche).
2. **Suchtext** je Datensatz (§4.1), **Suchindex** in Postgres, gebaut in `catalog-load` (§4.6).
3. **Lexikalischer Arm** (§4.2): Volltext in `simple`, `german` und `english` mit `unaccent`, Trigramme für Tippfehler, **Glossar** de/en als YAML; die beiden Ranglisten per RRF (k = 60, §4.4) vereint.
4. **Harte Filter** für Raum und Zeit vor dem Rang (§4.4).
5. **STAC Collection Search mit `q`** auf `/stac/collections`, Fläche nur per `POST` (§4.5, F9).
6. Messung am Set nach Schritt 2; die Zahlen stehen im PR. Sie entscheiden nach `adr/0026` §6 mit, ob der Vektorarm (M5-23) in M5 kommt.

**Nicht in M5-22:** Embeddings, Modell, Dockerfile-Stufe, Startprüfung „Index gegen Modell“ und RRF mit dem Vektorarm (M5-23); Suchfeld und AOI-Schalter im Data catalogue (M5-23); JSON-LD und Sitemap (M5-25); Harvest (M5-19 ff.).

---

## 2. Ausgangslage

### 2.1 Im Code [P]

- **Katalog heute:** sechs Einträge unter `backend/catalog/datasets/`: `sentinel-2-c1-l2a`, `cop-dem-glo-30`, `sentinel-1-grd`, `esa-worldcover-2020`, `esa-worldcover-2021`, `swissalti3d`. Gelistete Einträge (M5-17) und Prototyp-Einträge gibt es noch nicht.
- **Textfelder je Eintrag:** `title`, `description`, `keywords`, `category` (Gruppe, UI-05), `providers`, `data_class`, `band_units`, `index_presets` (Name und Titel), `true_color`, `access.account`. Schlagworte de/en stehen bei WorldCover, Sentinel-1 und swissALTI3D; Sentinel-2 und der Copernicus DEM haben nur englische (vor F7 angelegt).
- **`/stac/collections`:** kommt aus `stac-fastapi-pgstac` 6.4.1 (`CoreCrudClient.all_collections`, geerbt von `FederatingCoreCrudClient`). Eingeschaltet ist nur `pagination` (`api/main.py`, `_ENABLED_EXTENSIONS`); Collection Search und Free-text sind aus. Ohne Collection Search gibt die Route alle Collections zurück (`limit` 10000); das Frontend lädt sie einmal ohne Parameter (`frontend/src/api.ts:126`).
- **Collection Search in der Bibliothek:** `CollectionSearchExtension` (nur `GET`) baut das Modell aus den eingeschalteten Teil-Extensions; die Free-text-Extension bringt `q` und ihre Konformitätsklasse mit. `POST /collections` gibt es nur über `CollectionSearchPostExtension`, die `instantiate_api` nicht selbst anlegt; sie ruft `post_all_collections` des Clients. Mit Collection Search gilt die Offset-Paginierung der Bibliothek (Vorgabe `limit` 10).
- **pgstac und `q`:** sucht fest englisch und ohne Index (`adr/0026` §3.3); die Suche reicht `q` deshalb nicht an pgstac durch.
- **`catalog-load`:** `python -m earthx.catalog.load` in Compose und CI; Migrationen, dann alle Einträge als Collections, in einer Transaktion. Migrationen sind nummerierte SQL-Dateien (zuletzt `015_job_deleted.sql`).
- **Importregeln:** `catalog` darf nur `gateway`; die Operator-Registry liegt in `processing`. Der Suchtext kann Operatoren deshalb nicht aus `processing` lesen (§3.2, F5).
- **Operatoren heute:** nur allgemeine (`band_math`, `mask`, `mask_values`, `normalize`, `reproject`, `select`). Datensatzeigene kommen ab M5-10 (`terrain`).
- **Zugangsprotokoll:** schreibt nie den Query-String (`logging.py`, `RequestIdMiddleware`); Bodies werden nicht protokolliert.
- **Image:** das `Dockerfile` kopiert `catalog/datasets` und `catalog/retired.yaml`, sonst nichts aus `catalog/`.

### 2.2 Gemessen [M]

Im lokalen Postgres 16 der Sitzung:

- `unaccent` ist installiert, `pg_trgm` verfügbar (in dieser Sitzung angelegt); `vector` fehlt (wie `adr/0026` [M]). Die Rolle der Sitzung ist Superuser; beide Erweiterungen sind ab Postgres 13 „trusted“ [A].
- `unaccent('Höhenmodell Österreich Straße')` → `Hohenmodell Osterreich Strasse`.
- Der deutsche Stemmer faltet Umlaute selbst: `to_tsvector('german', 'Höhenmodell Höhe Rückstreuung')` → `hohenmodell`, `hoh`, `ruckstreu`. Komposita bleiben ganz (`satellitenbild`, `wasserflach`, `gelandemodell`).
- `websearch_to_tsquery('simple', 'Radarbilder bei Bewölkung')` verlangt auch `bei` (`simple` kennt keine Stoppwörter); `german` lässt `bei` fallen. Eine reine UND-Anfrage über `simple` scheitert also an jedem Füllwort; das ODER der drei Konfigurationen fängt das auf.
- `Sentinel-2` wird zu `'sentinel' <-> '-2'`; die Kennung `sentinel-2-c1-l2a` zerfällt in `sentinel`, `-2`, `c1-l2a`, `c1`, `l2a`.
- Trigramme: `similarity('sentinal 2', 'sentinel-2')` = 0,57; `similarity('worldcovr', 'worldcover')` = 0,62; `word_similarity('worldcovr', 'esa worldcover 2020')` = 0,80.

---

## 3. Umsetzung

### 3.1 Bewertungs-Set als Fixture

- **Datei:** `backend/tests/fixtures/search/evaluation_set.yaml`, die 50 Fragen aus `adr/0026` §8.3 wörtlich, mit Kennung, Sprache, Text, Art, Kontext und Noten (2, 1, `never`). Dazu eine Tabelle der Kürzel (`S2` → `sentinel-2-c1-l2a`, …); Kürzel ohne Kennung (MCH, HYR, CLC, LS; BEV vorläufig `bev-als-dgm`) stehen mit `null` bzw. der vorläufigen Kennung.
- **Kontext:** AOI als grobe Box in ganzen Grad mit Namen (`adr/0026` §8.1), Zeitraum als Jahresgrenzen, Voraussetzung als Bedingung, die aus den Daten prüfbar ist: Q34, Q35 `requires: terrain` (aktiv, sobald ein Eintrag die Capability `terrain` hat; M5-10). So braucht der Test `processing` nicht.
- **Ruhen** (`adr/0026` §8.1): aktiv, wenn mindestens ein Datensatz mit Note 2 geladen ist und die Voraussetzung gilt; Fragen ohne Note 2 sind immer aktiv. Gemessen wird nur gegen geladene Datensätze. Stand heute: **36 aktiv** (30 mit Note 2, 2 Filterfragen Q29 und Q32, 4 Negativfragen), **14 ruhen** (Q06, Q08, Q19–Q23, Q25, Q26, Q34, Q35, Q41, Q45, Q46).
- **Maße** wie §8.1: Recall@5, MRR@10, nDCG@10 (nur berichtet), Filterfragen, Negativfragen; je Sprache und gesamt. Reine Namen und Kürzel (Q01, Q03, Q04, Q05, Q07, Q40, Q42, Q43, Q44, Q46) nur im Gesamtmaß. Heute je Sprache: 11 deutsche, 10 englische Fragen mit Note 2.
- **Auswerter:** `backend/tests/search_evaluation.py` (Maße, Ruhen, Bericht), getrennt vom Test, damit M5-23 ihn mit dem Vektorarm wiederverwendet. Eigener Code statt `ranx`: vier Maße über wenige Dutzend Fragen brauchen keine Abhängigkeit [A]; der gepaarte Vergleich zweier Varianten (`ranx`) kommt mit M5-23, wo er gebraucht wird.
- **Bericht:** je Frage Rang der Datensätze mit Note 2, Treffer mit `never`, aktiv oder ruhend; als Text in der Ausgabe von `pytest` (`-s`) und als Tabelle im PR.
- **Grenze im Test (F3 = 1):** M5-22a hat noch keine Suche; der Test prüft den Auswerter und den Nullpunkt. Ab M5-22b sind alle Filterfragen und drei von vier Negativfragen hart, Recall@5 und MRR@10 haben eine Untergrenze aus der eigenen Messung (Sperrklinke). Die Grenze aus `adr/0026` F5 gilt ab M5-23.
- **Nullpunkt:** der Auswerter mit einer Suche, die nichts liefert. Ergebnis vorab [A]: Recall@5 und MRR@10 = 0, alle vier Filterfragen (Q27, Q28, Q29, Q32) und alle vier Negativfragen bestanden. Steht im PR.

### 3.2 Suchtext je Datensatz (`adr/0026` §4.1)

`catalog/search_text.py` baut aus einem `DatasetConfig` vier gewichtete Teile:

| Gewicht | Inhalt |
|---|---|
| A | Kennung, Titel |
| B | Schlagworte, Ortsbegriffe (F4), Name der Gruppe (`category`, englisch) |
| C | Beschreibung |
| D | Bandnamen mit Einheit; Namen und Titel der Quick processings (`index_presets`); „true color“, wenn `true_color` gesetzt ist; Datentyp-Klasse in Worten (`raster-time-series` → „raster time series“); Namen der Anbieter; Zugang (`free_account` → „free account required“, `requester_pays` → „requester pays“); Begriffe je Capability (F5) |

- **Abweichung vom ADR (Auslegung A1):** Das ADR setzt Kennung, Titel **und** Schlagworte auf A. Dann stehen bei „Sentinel-2“ Sentinel-2 und beide WorldCover-Einträge gleich (WorldCover hat `sentinel-2` als Schlagwort), und der Gleichstand nach Titel setzt WorldCover vor Sentinel-2 [A, aus den Texten P]. Schlagworte deshalb auf B, die Beschreibung auf C. Die Gewichte sind Startwerte; geändert wird nur mit Messung am Set, im PR berichtet.
- **Prüfwert:** SHA-256 über die vier Teile und eine Fassungsnummer des Suchtexts (`SEARCH_TEXT_VERSION`). M5-23 nimmt die Modellkennung dazu.
- **Was nicht geht, erscheint nicht:** nur Quick processings, die der Eintrag hat, nur Begriffe von Capabilities, die er hat. Allgemeine Operatoren, die jeder Datensatz hat, stehen in keinem Text (sie unterscheiden nichts).

### 3.3 Glossar (`adr/0026` §4.2, F7)

- **Datei:** `backend/catalog/glossary.yaml`, Liste von Gruppen gleichbedeutender Begriffe (je Gruppe deutsch und englisch, Kürzel erlaubt), mit Kommentar zur Herkunft. Im Image (für `api` und `catalog-load`), Review über Git (B13).
- **Startinhalt:** die Begriffe aus den Plan-Dateien von M5-07 §10, M5-08 §9 und DS-04 §8 (sie ziehen damit um, `adr/0026` Folge 9), die Beispiele aus `adr/0026` §4.2 (Höhenmodell/DEM, Geländemodell/DGM/DTM/bare-earth model, Oberflächenmodell/DOM/DSM getrennt) und die Begriffe, die aktive Fragen brauchen (z. B. Bodenreflexion ↔ surface reflectance, Echtfarben ↔ true color, Vegetationsindex ↔ vegetation index, Schneebedeckung ↔ snow cover, Wasserflächen ↔ water bodies, Radarbild ↔ radar image). Otto prüft die Gruppen im PR.
- **Prüfung beim Laden:** jede Gruppe mindestens zwei Begriffe, kein Begriff in zwei Gruppen (nach Kleinschreibung und `unaccent`), keine leeren Begriffe; Fehler mit Datei, Gruppe und Grund.
- **Anwendung nur auf die Anfrage:** Die Anfrage wird normalisiert (klein, ohne Akzente, Bindestrich und Leerzeichen gleich) und von links nach rechts mit dem längsten passenden Begriff zerlegt. Ein Glossar-Treffer wird zur Alternative „Begriff ODER jeder andere Begriff der Gruppe“ (je als Phrase). Die Suchtexte bleiben unverändert; das Glossar wirkt so ohne neuen Index, sobald es sich ändert.
- **Pflicht beim Onboarding:** `projektuebersicht.md` §5 Punkt 11 (neu in diesem PR, `adr/0026` F7): Schlagworte deutsch und englisch, neue Fachbegriffe ins Glossar.

### 3.4 Suchindex und Laden (`adr/0026` §4.6)

- **Migration `016_dataset_search.sql`:** `CREATE EXTENSION IF NOT EXISTS unaccent`, `pg_trgm`; Tabelle `public.earthx_dataset_search` mit `dataset_id` (Schlüssel), `text_a` bis `text_d`, `text_hash`, `document tsvector`, `trigram_text text`, `bbox geometry(Polygon, 4326)`, `time_start`, `time_end` (offen = `NULL`), `has_time_axis`, `item_holding` (föderiert oder materialisiert); GIN-Index auf `document`, GIN-Trigramm-Index auf `trigram_text`. Name nach dem Muster der übrigen Tabellen (`earthx_job`, `earthx_permalink`); `architekturplan.md` 10 nennt sie `dataset_embedding`, M5-23 ergänzt die Spalten für das Embedding (Auslegung A2).
- **`document`:** je Teil `setweight(to_tsvector(cfg, unaccent(teil)), gewicht)` für `cfg` in `simple`, `german`, `english`, alle verbunden. Beim Schreiben gerechnet, nicht als generierte Spalte (`unaccent` ist nicht `IMMUTABLE`).
- **`trigram_text`:** Kennung, Titel und Schlagworte, klein und ohne Akzente.
- **In `catalog-load`:** nach den Collections, in derselben Transaktion: für jeden geladenen Eintrag eine Zeile schreiben, wenn `text_hash` oder Ausdehnung sich geändert hat; Zeilen ohne Eintrag löschen. Die Ausgabe nennt geschriebene und gelöschte Zeilen. Prototyp-Einträge stehen nur dort im Index, wo sie geladen sind (`adr/0024` R5).
- **Startprüfung in `api`:** jeder Eintrag der Registry hat eine Zeile mit dem `text_hash`, den `api` selbst rechnet, und es gibt keine Zeile ohne Eintrag; sonst Startfehler mit den Kennungen (wie `check_item_holdings`). So kann ein `api` mit neuem Suchtext nicht still auf einem alten Index laufen (Auslegung A3).

### 3.5 Lexikalischer Arm (`adr/0026` §4.2)

- **Volltext:** die Anfrage (nach Glossar, §3.3) als `tsquery`, je Wort bzw. Glossar-Gruppe das ODER der drei Konfigurationen über `unaccent`, nur als Parameter an SQL. Wie die Wörter untereinander verknüpft werden (UND, UND ohne unbekannte Wörter, ODER mit Mindestanteil), entscheidet F2. Rang `ts_rank_cd` mit den Gewichten aus §3.2; für die Fusion zählt nur die Reihenfolge.
- **Trigramm:** `word_similarity` der Anfrage gegen `trigram_text`, als zweite Rangliste; eine Schwelle (Startwert 0,5, über der Vorgabe 0,3) hält Zufallstreffer aus den Negativfragen fern. Die Schwelle wird am Set festgelegt und steht im PR.
- **Fusion:** RRF mit k = 60 über die beiden Listen (§4.4). M5-23 fügt den Vektorarm als dritte Liste hinzu, ohne die Fusion umzubauen.
- **Gleichstand:** nach Titel, dann Kennung.
- **Ort:** `catalog/search.py` (Modul `catalog` ist für „Suche“ zuständig, `architekturplan.md` 3.1); `api` ruft es über den Pool, den es schon hat.

### 3.6 Harte Filter (`adr/0026` §4.4)

- **Raum:** Bei materialisierten Datensätzen ein `EXISTS` über die Items in pgstac (`ST_Intersects` mit den Footprints), sonst die Bbox der Collection. Ohne geladene Items fällt ein materialisierter Datensatz auf seine Bbox zurück (Auslegung A4: sonst verschwände er in jeder lokalen Instanz, in der Otto die Items noch nicht geladen hat).
- **Zeit:** Überlappung mit der zeitlichen Ausdehnung, offenes Ende heißt heute. Datensätze ohne Zeitachse fallen nie wegen eines Zeitraums heraus und stehen in `ignored_filters` der Antwort, in der Form von `/stac/search`.
- **Zugang, Lizenz:** nach F7.
- **Ohne Text** (nur Fläche und/oder Zeit): die gefilterte Liste in der heutigen Reihenfolge, ohne Rang. Das braucht der AOI-Schalter ohne Text in M5-23 (`adr/0026` §7).

### 3.7 Schnittstelle (`adr/0026` §4.5, F9)

- **`GET /stac/collections`:** `q`, `bbox`, `datetime`, `limit`, `offset`. **`POST /stac/collections`** (über `CollectionSearchPostExtension`): dieselben Felder im Body, Fläche nach F6. Das eigene Frontend sucht mit Fläche nur per `POST`.
- **Ohne jeden Parameter:** unverändert alle Collections (das Frontend lädt so den Katalog). Die Vorgabe `limit` 10 der Bibliothek gilt dort nicht (Auslegung A5).
- **Mit `q`:** höchstens 20 Treffer je Seite (`limit` größer wird auf 20 gesenkt, Auslegung A5), Blättern per `offset` mit `next`-Link. Antwort: die Collection-Dokumente aus pgstac in der Rangfolge; keine Punktzahl.
- **Eingaben:** `q` höchstens 200 Zeichen, sonst `400`; nur Leerzeichen gilt als kein Text. Kommas in `q` sind gewöhnliche Trennzeichen (keine Free-text-Syntax).
- **Konformität:** Die Landing Page erklärt Collection Search, aber nicht Free-text (`adr/0026` §4.5). Der Parameter `q` kommt deshalb über eine Free-text-Extension ohne Konformitätsklasse; ein Test prüft `/stac/conformance`. `filter`, `sort`, `query` und `fields` bleiben für Collections aus.
- **Logs:** weder `q` noch Fläche in einer Logzeile; ein Test prüft das Zugangsprotokoll für `GET` mit `q` und `POST` mit Fläche.

### 3.8 Was sich für bestehende Aufrufer ändert

Nichts, solange sie `/stac/collections` ohne Parameter rufen. `catalog-load` schreibt zusätzlich den Suchindex; `api` startet nicht ohne passenden Index (§3.4). Für bestehende Datenbanken genügt ein Lauf von `catalog-load` (in Compose ohnehin vor `api`).

---

## 4. Tests

- **Bewertungs-Set** (`tests/integration/test_search_evaluation.py`): lädt die Registry in die Datenbank des Workers, baut den Index, stellt jede aktive Frage über `catalog.search`, berichtet und prüft die Grenze nach F3. Dazu Einheitstests des Auswerters mit einem synthetischen Katalog (Maße, Ruhen, Sprachzählung, Negativ- und Filterfragen).
- **Suchtext:** Teile und Gewichte, Prüfwert stabil und abhängig von jedem Teil; Quick processings nur bei vorhandenen Presets; kein allgemeiner Operator im Text.
- **Glossar:** Laden und Fehlerfälle (Doppelte, leere Gruppe, Begriff in zwei Gruppen, unbekannter Schlüssel); Zerlegung der Anfrage (längster Treffer, Bindestrich, Umlaut, Groß-/Kleinschreibung); DSM und DTM in getrennten Gruppen.
- **Index:** `catalog-load` schreibt, ändert nur bei neuem Prüfwert, löscht verwaiste Zeilen, ist idempotent; Migration läuft auf leerer und bestehender Datenbank.
- **Suche:** Wörter mit Sonderzeichen, SQL-Zeichen (`'`, `;`, `\`), nur Satzzeichen, 200 und 201 Zeichen, Emoji, leere Anfrage; Tippfehler über Trigramme; Gleichstand stabil; Raum (Bbox und Footprint, ohne Items Bbox) und Zeit (offenes Ende, ohne Zeitachse, `ignored_filters`).
- **Route:** `GET` und `POST` mit und ohne `q`; ohne Parameter dieselbe Antwort wie heute; `limit` über 20; `offset`; Fläche in `GET` nur als `bbox`; ungültige Fläche, ungültiger Zeitraum, unbekanntes Feld im Body → `400`; Konformität ohne Free-text; nichts von `q` oder Fläche im Log; Startfehler bei fehlendem oder veraltetem Index.
- Alles ohne Netz; Fixtures synthetisch bzw. die Fragen aus dem ADR.

---

## 5. Auslegungen

- **A1** Gewichte: Schlagworte auf B statt A (§3.2), Startwerte, Änderung nur mit Messung.
- **A2** Tabellenname `earthx_dataset_search` statt `dataset_embedding`; M5-23 ergänzt die Embedding-Spalten in einer eigenen Migration.
- **A3** Startprüfung des Index in `api` schon in M5-22 (das ADR nennt sie für das Modell, §4.6); sonst liefe ein neuer Suchtext still gegen einen alten Index.
- **A4** Materialisierter Datensatz ohne geladene Items: Raumfilter über die Bbox.
- **A5** Ohne Parameter alle Collections wie heute; mit `q` höchstens 20 je Seite, ein größeres `limit` wird gesenkt (die Spezifikation erlaubt dem Server weniger zu liefern [A]).
- **A6** Ohne Text, aber mit Fläche oder Zeit: gefilterte Liste ohne Rang in der heutigen Reihenfolge.
- **A7** (bestätigt 11.11.2026) Filterfragen zählen nach den Kürzeln in `never`, auch wenn ein Kürzel noch keine Kennung hat (M5-22a, §10).
- **A8** (bestätigt 11.11.2026) Eine Sprache ohne gemessene Frage verfehlt die Grenze: Nichts belegt, dass sie erreicht ist.
- **A9** (bestätigt 11.11.2026) „Drei von vier Negativfragen“ heißt: höchstens eine aktive Negativfrage darf Treffer haben, auch wenn per PR weitere hinzukommen.

---

## 6. Doku mit der Umsetzung

- **`architekturplan.md` 5.3 und 10:** Nachtrag zu `adr/0026` F3 (in diesem PR, als erster PR der Umsetzung, `adr/0026` Folge 10).
- **`projektuebersicht.md` §5 Punkt 11:** Onboarding-Punkt aus `adr/0026` F7 (in diesem PR).
- README: Collection Search mit `q`, `catalog-load` baut den Index, Glossar pflegen.
- `backend/catalog/migrations/README.md`: Eintrag `016`.
- Entscheidungslog: eine Zeile für den Plan, eine für die Umsetzung (bzw. je Teil nach F1).

---

## 7. Umfang und Schnitt

Grob geschätzt [A], ohne Fixture: Auswerter und Test rund 300 Zeilen, Suchtext, Glossar, Index und Arm rund 450, Schnittstelle rund 300, dazu Tests. Das Set als YAML hat rund 350 Zeilen, das Glossar rund 100. Zusammen weit über dem Richtwert von 400 Zeilen; Vorschlag deshalb drei Teile (F1):

1. **M5-22a** (dieser PR): Plan, Nachtrag Architekturplan, Bewertungs-Set als Fixture, Auswerter, Nullpunkt.
2. **M5-22b:** Suchtext, Glossar, Migration, Index in `catalog-load`, Startprüfung, lexikalischer Arm, harte Filter, Messung am Set.
3. **M5-22c:** Collection Search mit `q` (`GET`, `POST`), Konformität, Logs, README.

---

## 8. Fragen an Otto — beantwortet am 11.11.2026 (§8a)

**F1 — Schnitt (§7)?**
1. Drei PRs: a) Set und Auswerter (dieser PR), b) Index und lexikalischer Arm, c) Schnittstelle **(Empfehlung)**
2. Zwei PRs: a) mit b), dann c)
3. Ein PR für alles (weit über 400 Zeilen)

**F2 — Wie werden die Wörter einer Anfrage im Volltext verknüpft (§3.5)?** UND ist genau, scheitert aber an Wörtern wie „berechnen“ oder „erkennen“ (Q34, Q39); ODER findet mehr, kann aber Negativfragen mit einem einzelnen Treffer füllen („hourly *weather* forecast“, Q50). Ein Treffer des lexikalischen Arms bleibt auch nach RRF in der Liste.
1. Am Set wählen unter: UND; UND ohne Wörter, die in keinem Suchtext vorkommen; ODER mit Mindestanteil der Wörter. Gewinnt die Variante mit dem höchsten Recall@5, die alle Filterfragen und mindestens drei von vier Negativfragen besteht; du bestätigst im PR **(Empfehlung)**
2. UND, fest (`websearch_to_tsquery`-Verhalten)
3. ODER, fest; Genauigkeit soll später der Vektorarm bringen

**F3 — Grenze des Bewertungs-Sets in der CI ab M5-22?** Die Grenze aus `adr/0026` F5 (Recall@5 ≥ 0,9, MRR@10 ≥ 0,8 je Sprache) wird der lexikalische Arm allein vermutlich nicht erreichen (Sprachwechsel ohne gemeinsames Wort).
1. Ab M5-22b hart: alle Filterfragen, drei von vier Negativfragen; Recall@5 und MRR@10 mit Untergrenze aus der eigenen Messung (Sperrklinke, nur nach oben verschiebbar). Die Grenze aus F5 gilt ab M5-23 **(Empfehlung)**
2. Grenze aus F5 sofort; der Test ist bis M5-23 als erwartetes Scheitern markiert
3. Bis M5-23 nur berichten, keine Grenze

**F4 — Woher kommen die Ortsbegriffe aus der Ausdehnung (`adr/0026` F8)?** Die Bbox allein reicht nicht für einen Abgleich mit Länder-Boxen: Die Box von swissALTI3D läge zu mehr als der Hälfte in der Box Italiens [A].
1. Ländergrenzen von **Natural Earth 1:50m** (Public Domain, schon in UI-02 geprüft), auf Name de/en und vereinfachte Umrisse reduziert, mit Skript, Fassung und Prüfsumme unter `backend/catalog/`. Regel: Ein Land kommt in den Suchtext, wenn mindestens die Hälfte seiner Fläche in der Bbox des Datensatzes liegt; ebenso ein Kontinent. Bbox über fast die ganze Erde: „global, worldwide, weltweit“. Du bestätigst die Einstufung der Datei **(Empfehlung)**
2. Handgepflegte Liste der DACH-Länder und Nachbarn mit groben Boxen in `catalog`
3. Nur „global/weltweit“ automatisch; Länder weiter über die Schlagworte (weicht von F8 ab)

**F5 — Operatoren im Suchtext (§3.2)?** `catalog` darf die Operator-Registry (`processing`) nicht importieren; heute gibt es nur allgemeine Operatoren, datensatzeigene erst ab M5-10.
1. Begriffe je Capability als YAML in `catalog` (z. B. `terrain`: slope, aspect, hillshade, Hangneigung, Exposition, Schummerung); ein Test vergleicht sie mit der Operator-Registry, damit kein Operator ohne Begriffe bleibt. In M5-22 leer, M5-10 trägt `terrain` ein **(Empfehlung)**
2. `catalog-load` bekommt seinen Einstieg in `api` (darf alles importieren) und liest die Operator-Registry direkt; Compose ruft den neuen Befehl
3. Erst mit M5-10 entscheiden

**F6 — Fläche im Body von `POST /stac/collections`?**
1. `bbox` (Standard) und `intersects` (GeoJSON-Geometrie, wie bei `/stac/search`); `GET` nur `bbox`; das Frontend schickt die AOI als `intersects` **(Empfehlung)**
2. Nur `bbox`; das Frontend schickt die Bbox der AOI (gröber bei schrägen oder L-förmigen AOIs)

**F7 — Zugang und Lizenz als Filter über die Schnittstelle (`adr/0026` §4.4)?** Ohne CQL2 (aus, `adr/0005` Regel VI) gibt es dafür keinen Standardparameter.
1. Nicht in M5; kommt mit dem ersten Bedarf (Chatbot M7 oder Python-Client) als eigene Entscheidung **(Empfehlung)**
2. Eigene Felder im `POST`-Body (`earthx:account`, `earthx:license_tier`) schon in M5-22c

**F8 — Deutsche Schlagworte für Sentinel-2 und Copernicus DEM nachziehen?** Beide entstanden vor `adr/0026` F7.
1. Ja, in M5-22b (z. B. „Bodenreflexion“, „multispektral“ bzw. „Höhenmodell“, „Oberflächenmodell“); Messung vorher und nachher im PR **(Empfehlung)**
2. Nein, das Glossar reicht

## 8a. Antworten Otto (11.11.2026)

- **F1–F8 jeweils Option 1.** Damit: drei PRs (a, b, c); Wortverknüpfung am Set gewählt, Bestätigung im PR von M5-22b; Filter- und Negativfragen ab M5-22b hart, Sperrklinke für Recall@5 und MRR@10, Grenze aus `adr/0026` F5 ab M5-23; Begriffe je Capability als YAML in `catalog`; `POST` mit `bbox` und `intersects`; kein Zugangs- und Lizenzfilter in M5; deutsche Schlagworte für Sentinel-2 und Copernicus DEM in M5-22b.
- **Auslegung A1 angenommen:** Schlagworte auf Gewicht B.
- **Auslegungen A7, A8, A9 bestätigt (Otto, 11.11.2026, nach der Umsetzung von M5-22a).**
- **F4, Natural Earth:** als Public Domain bestätigt; Einstufung frei, eine Quellenangabe ist nicht Pflicht. Freiwillig in den Hinweisen zu Dritten nennen (mit M5-22b, das die Datei bringt).

---

## 9. Grenzen

- Modulgrenzen laut `architekturplan.md` 3.1: Suche in `catalog`, Route in `api`; keine neue Importregel, keine Lockerung.
- Keine ausgehende Anfrage: Suche und Laden rufen nichts außerhalb der Datenbank.
- Keine AOI, kein Suchtext in Logs oder URLs der eigenen Oberfläche; Fragen des Sets nur mit groben, benannten Boxen.
- Keine Prototyp-Datensätze im Set (`adr/0024` R7).
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert; Compose nur nach F5 Option 2.
- Vor „fertig“: `main` geholt, Lint, Typprüfung, Tests und Importregeln grün.

---

## 10. Umsetzung Teil 1: M5-22a (11.11.2026)

- **Fixture** `backend/tests/fixtures/search/evaluation_set.yaml`: die 50 Fragen aus `adr/0026` §8.3 wörtlich, die Kürzel aus §8.2 mit Kennung (`null`, solange keine feststeht; BEV mit `provisional: true`), Hinweise aus §8.3 als Kommentare. AOI als Box in ganzen Grad, Zeitraum als `years: [erstes, letztes]`.
- **Auswerter** `backend/tests/search_evaluation.py`: liest die Fixture mit dem strengen Lader der Registry (`entry_files.read_yaml`) und prüft die Regeln aus §8.1 (Noten getrennt, Negativfrage ohne Noten, ganze Grad, kein `proto-`); `evaluate` stellt die aktiven Fragen an eine beliebige Suche, die nur Text, AOI und Zeitraum sieht (`Query`), nie die Noten; `shortfalls` vergleicht mit einer Grenze (`ADR_0026_F5` als Konstante), `report` schreibt den Bericht je Frage. Eine Antwort mit doppelter oder unbekannter Kennung ist ein Fehler der Suche.
- **Filterfragen** zählen nach den Kürzeln, nicht nach den Kennungen: Q29 prüft MCH, das noch keine Kennung hat, und bleibt so eine (bestandene) Filterfrage (Auslegung A7).
- **Tests** `backend/tests/catalog/test_search_evaluation.py`: die Fixture gegen das ADR (Kennungen, Sprachen, Negativfragen, reine Namen, Voraussetzungen, Boxen, Zeiträume), feste Kennungen in der Registry, Maße auf einem synthetischen Katalog (mit einem Datensatz, der eine Kennung hat, aber nicht geladen ist, wie BEV), 26 fehlerhafte Fixtures, Nullpunkt mit festen Zahlen; eine vorläufige Kennung darf noch nicht in der Registry stehen (Erinnerung beim Einzug von BEV).

**Nullpunkt** (keine Suche, Katalog der Registry mit sechs Einträgen; `pytest -n 0 -s backend/tests/catalog/test_search_evaluation.py`):

| | Fragen mit Note 2 | Recall@5 | MRR@10 | nDCG@10 |
|---|---|---|---|---|
| de | 11 | 0 | 0 | 0 |
| en | 10 | 0 | 0 | 0 |
| gesamt | 30 | 0 | 0 | 0 |

36 Fragen aktiv, 14 ruhend (wie §3.1). Filterfragen 4 von 4 (Q27, Q28, Q29, Q32), Negativfragen 4 von 4 bestanden. Gegen die Grenze aus F5 fehlen Recall@5 und MRR@10 in beiden Sprachen, sonst nichts.

---

## 11. Umsetzung Teil 2: M5-22b (11.11.2026)

Draft-PR [#334](https://github.com/oscipal/earthX/pull/334). Belegstufen wie oben; **M** heißt hier: im lokalen Postgres 16 der Sitzung gemessen, ohne Netz außer dem einmaligen Abruf der Natural-Earth-Datei.

### 11.1 Was gebaut ist

- **Ortsbegriffe (F4):** `backend/catalog/places.json` aus Natural Earth 1:50m „Admin 0 – Countries“, Release 5.1.2 (Public Domain), mit Release, Dateiname und SHA-256 der Quelle; 242 Länder mit Kennung, Name englisch und deutsch, Kontinent und Umriss (auf 0,1° vereinfacht, zwei Nachkommastellen, wo das keine gültige Fläche lässt vier; 345 kB). Erzeugt mit `scripts/write-place-outlines.py` aus einer lokalen Kopie; das Skript ruft nichts ab und verweigert eine Datei mit anderer Prüfsumme. `catalog/places.py` rechnet geodätisch (WGS 84): Land bzw. Kontinent, wenn mindestens die Hälfte seiner Fläche in der Box liegt. Nennung in `backend/THIRD_PARTY_NOTICES.md` (freiwillig, §8a).
- **Glossar:** `backend/catalog/glossary.yaml`, 37 Gruppen (Namen und Kürzel, Höhe in drei getrennten Gruppen, Landbedeckung aus M5-07 §10, Radar aus DS-04 §8, M5-08 §9, optische Begriffe der aktiven Fragen). Die Begriffe der drei Plan-Dateien sind damit umgezogen (`adr/0026` Folge 9). `catalog/glossary.py` prüft beim Laden und zerlegt die Anfrage (längster Treffer, Bindestrich = Leerzeichen, ohne Akzente; doppelte Einheiten zählen einmal).
- **Begriffe je Capability (F5):** `backend/catalog/capability_terms.yaml` mit `general` (die fünf Capabilities der allgemeinen Operatoren) und leerem `terms`; ein Test hält die Datei gegen die Operator-Registry.
- **Suchtext:** `catalog/search_text.py`, vier Teile wie §3.2 mit A1; Prüfwert über die Teile und `SEARCH_TEXT_VERSION` = 1.
- **Index:** Migration `016_dataset_search.sql`, Tabelle `public.earthx_dataset_search`; geschrieben von `catalog-load` (`catalog/search_index.py`) in derselben Transaktion wie die Collections; ein zweiter Lauf schreibt keine Zeile. Startprüfung in `api` (`check_search_index`): fehlende Zeile, alter Prüfwert, veraltete Box, Zeitausdehnung, Zeitachse oder Item-Haltung oder eine Zeile ohne Eintrag halten den Start an (über §3.4 hinaus: ein neues Missionsende ändert kein Wort des Suchtexts, aber den Zeitfilter).
- **Lexikalischer Arm und Filter:** `catalog/search.py` (`search_datasets`), noch ohne Route (M5-22c).
- **Schlagworte deutsch (F8):** Sentinel-2 `optisch`, `multispektral`, `Bodenreflexion`; Copernicus DEM `Höhe`, `Höhenmodell`, `Oberflächenmodell`, `Gelände`.
- **Tests:** Orte, Glossar, Suchtext und Begriffe je Capability ohne Datenbank; Index, Startprüfung, Suche und Bewertungs-Set gegen Postgres (`tests/integration/test_search_index.py`, `test_search.py`, `test_search_evaluation.py`).

### 11.2 Wortverknüpfung (F2) und Schwelle der Trigramme, gemessen [M]

Alle drei Varianten am Set, Schwelle 0,5, Katalog der Registry mit sechs Einträgen (36 Fragen aktiv, 14 ruhend):

| Variante | de Recall@5 | de MRR@10 | en Recall@5 | en MRR@10 | gesamt Recall@5 | gesamt MRR@10 | gesamt nDCG@10 | Filter | Negativ |
|---|---|---|---|---|---|---|---|---|---|
| UND | 0,636 | 0,636 | 1,000 | 1,000 | 0,867 | 0,844 | 0,843 | 4/4 | 4/4 |
| **UND ohne unbekannte Wörter** | **0,727** | **0,727** | **1,000** | **1,000** | **0,900** | **0,878** | **0,877** | **4/4** | **3/4** |
| ODER mit Mindestanteil ½ | 0,727 | 0,727 | 1,000 | 1,000 | 0,900 | 0,878 | 0,877 | 4/4 | 3/4 |

- Nach der Regel aus F2 gewinnt die höchste Recall@5 mit allen Filterfragen und mindestens drei von vier Negativfragen: Gleichstand zwischen „UND ohne unbekannte Wörter“ und „ODER mit Mindestanteil“. **Gewählt: UND ohne unbekannte Wörter** (`Joining.KNOWN`), weil sie keinen weiteren Parameter braucht (der Anteil ½ ist nicht belegt) und bei Wörtern, die der Katalog kennt, so genau bleibt wie UND. **Otto bestätigt im PR.**
- Unterschied zu UND: Q16 „Satellitenbilder in Echtfarben“ (kein Suchtext kennt „Satellitenbild“). Preis: Q48 „ocean salinity“ findet den Copernicus DEM („Oceans carry no tiles“ in der Beschreibung), weil „salinity“ unbekannt ist und wegfällt; das ist die eine erlaubte Negativfrage (A9).
- **Schwelle der Trigramme:** 0,4 und 0,5 messen gleich, 0,6 und 0,7 verlieren Q43 „Worldcovr“ (gesamt Recall@5 0,867). Festgelegt: **0,5** (der Startwert, die höhere der beiden gleich guten).
- **Deutsche Schlagworte (F8), vorher und nachher:** in allen drei Varianten dieselben Zahlen. Das Glossar überbrückte die Begriffe schon; die Schlagworte helfen Anfragen außerhalb des Glossars und später dem Vektorarm.

### 11.3 Ergebnis je Frage (gewählte Variante) [M]

Nicht unter den ersten fünf: Q18 „Radarbilder bei Bewölkung“ (kein Suchtext kennt „Radarbild“ oder „Bewölkung“), Q38 „Schneebedeckung“ und Q39 „Wasserflächen erkennen“ (Sentinel-2 nennt nur „Snow Index“ und „Water Index“; Q38 findet WorldCover über die Trigramme von „Bodenbedeckung“). Alle drei sind deutsch und brauchen ein Wort, das in keinem Text steht: der Fall des Vektorarms (M5-23). Q42 „Sentinal 2“ findet Sentinel-2 auf Rang 3 (hinter den beiden WorldCover-Einträgen, die `sentinel-2` als Schlagwort tragen). Alle übrigen 26 gemessenen Fragen haben einen Datensatz mit Note 2 auf Rang 1.

Sperrklinke (F3) in `test_search_evaluation.py`: Recall@5 und MRR@10 deutsch ≥ 8/11, englisch = 1,0; alle Filterfragen; höchstens eine Negativfrage mit Treffern. Gegen die Grenze aus `adr/0026` F5 fehlt nur Deutsch (0,727 statt 0,9 bzw. 0,8).

### 11.4 Auslegungen der Umsetzung (gelten, bis Otto widerspricht)

- **A10** Global heißt: jeder Kontinent außer der Antarktis liegt mindestens zur Hälfte in der Box (WorldCover endet bei 60° S und ist global). Ein globaler Datensatz bekommt nur „global, worldwide, weltweit“, keine Länderliste.
- **A11** Das Skript liegt unter `scripts/`, die reduzierte Datei mit Release und Prüfsumme unter `backend/catalog/` (F4 nannte beides dort; `scripts/` ist der Ort aller Skripte des Repos).
- **A12** Die Box steht im Index als vier Zahlen, nicht als `geometry`: die eigenen Datenbanken der Warteschlangen-Tests haben kein PostGIS, und die Migration soll überall laufen. Der Raumfilter baut die Box mit `ST_MakeEnvelope`.
- **A13** Ein Wort, das im Deutschen oder Englischen ein Stoppwort ist („bei“, „in“, „the“), ist keine Bedingung, in jeder Variante (wie `websearch_to_tsquery` je Sprache). Ein Glossar-Begriff ist nie eines.
- **A14** Gleiche Werte in einem Arm teilen sich vor der Fusion den Rang (1, 2, 2, 4). Sonst entschiede der Titel schon im Trigramm-Arm, und „ESA WorldCover“ läge bei „Sentinel-2“ vor Sentinel-2 (gemessen: Q01 fiel auf Rang 2). Nach Titel und Kennung wird erst nach der Fusion sortiert (§3.5).
- **A15** Ohne Text, nur mit Fläche oder Zeit, kommt die Liste nach Kennung (A6, „heutige Reihenfolge“; ob `/stac/collections` heute genau so sortiert, prüft M5-22c an der Route).
- **A16** Bandnamen ohne Einheit „1“ (Reflexion, Indizes), Hilfsassets (`visual`, `preview`) stehen nicht im Suchtext; Zugang ohne Anforderung (`none`, `anonymous_token`) fügt keine Wörter hinzu.
- **A17** Die Integrationstests, die `api` mit eigener Registry starten, schreiben vor der Startprüfung den Index genau dieser Registry (`tests/integration/conftest.py`), wie `catalog-load` es für die Registry des Prozesses tut; die Prüfung selbst läuft unverändert und hat eigene Tests.

### 11.5 Review vor dem PR

Ein Review-Subagent fand drei Fehler, alle behoben: (1) Der Importvertrag `runner` nannte die fünf neuen Module von `catalog` nicht (`test_module_boundaries.py` rot); sie stehen jetzt in der Verbotsliste, eine Verschärfung. (2) Die geodätische Fläche behandelte lange Kanten der Box entlang eines Breitenkreises als Geodäten (Box über Sibirien: 0,11 statt 0,51 von Russland); die Kanten werden vorher auf 0,5° geteilt, die Ortsbegriffe der heutigen Einträge bleiben gleich. (3) Die Startprüfung verglich nur den Prüfwert des Texts; jetzt auch die Spalten der Filter. Hinweise ohne Änderung, für M5-22c: Box mit `west > east` und Zeitraum mit vertauschten Enden prüft die Route; `word_similarity` als Funktion nutzt den Trigramm-Index nicht (bei sechs Zeilen ohne Belang); unter „UND ohne unbekannte Wörter“ kann eine Anfrage nach einem fehlenden Datensatz („Sentinel-3“) über die Trigramme einen ähnlich benannten finden.

