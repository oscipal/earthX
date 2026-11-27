# M5-66 — Schnelle Suche bei breiten Wörtern, schnelleres `catalog-load`

- **Auftrag:** Otto, 27.11.2026 (Stufe B). Folgt aus `plans/m5/m5-42-suche-gelistete.md` F5 = 1 (Otto, 23.11.2026) und der Zeile M5-66 in `plans/m5/m5-discovery-und-suche.md` §6.2.
- **Grundlage:** `adr/0026` §3.1, §4.4, §14; `plans/m5/m5-40-gelistete-in-postgres.md` F4 (Trefferzahl genau bis 10 000, darüber weggelassen); `plans/m5/m5-42-suche-gelistete.md` §2, §3, F2, F5; `plans/m5/m5-65-suche-mit-flaeche.md`; Entscheidungslog bis 27.11.2026.
- **Belegstufen** wie in `adr/0026`: **M** gemessen in dieser Sitzung, **P** im Repo gelesen, **G** Quelle gelesen, **S** nur Suchtreffer, **A** eigene Ableitung.
- **Unverändert:** Treffermenge jeder Anfrage, Trefferzahl bis 10 000, Bewertungs-Set, Ergebnis eines Laufs von `catalog-load`. Keine neue Migration.
- **Zwei Draft-PRs:** PR 1 dieser Plan und die Suche (§2, §3), PR 2 `catalog-load` (§4).

## 1. Befund Suche [P, M]

**Weg einer Anfrage mit Text** (`api/collection_search.py`, `catalog/search.py`): `search_datasets` holt alle Treffer beider Arme (Volltext, Trigramme) ohne die Filter für Kategorie, Region und Art des Eintrags, rankt und fusioniert sie in Python. Danach filtert die Route: volle Einträge nach der Kategorie der Registry und nach Regionen (`full_entries`), gelistete nach Kategorie und Region (`matching_listed` mit allen Kennungen als Liste). `numberMatched` ist die Länge der gefilterten Liste, also immer genau. Jede Seite (20 Treffer, `offset`) wiederholt die ganze Suche.

**Messung** auf einem synthetischen Bestand (§5): 102 313 veröffentlichte gelistete Einträge und die 9 vollen, über `POST /stac/collections` im Prozess (wie die Integrationstests), bester von 3 Läufen:

| Anfrage | Treffer | `main` |
|---|---|---|
| data | 102 144 | 1 402 ms |
| map | 21 891 | 773 ms |
| water | 28 215 | 961 ms |
| Karte | 55 364 | 1 659 ms |
| Wasser Pegel Messstelle | 7 849 | 1 726 ms |
| data + Kategorie `water` | 11 248 | 1 304 ms |
| map + Region DE-RP | 2 822 | 766 ms |
| water + Region CH | 3 993 | 979 ms |
| water + `boundaries` + DE | 5 586 | 963 ms |

**Wo die Zeit liegt** (`EXPLAIN ANALYZE`, „water“):

- **Volltext, 525 ms:** Jede getroffene Zeile wird gerankt; `ts_rank_cd` muss dazu den `tsvector` der Zeile entpacken (im Mittel 1,8 KB, komprimiert). Der Rang wurde erst nach dem Gruppieren je Datensatz gebildet, deshalb trug die Sortierung für das Gruppieren den `tsvector` jeder Zeile mit und lief auf die Platte (13 MB bei 28 041 Treffern, `work_mem` 4 MB).
- **Volltext mit mehreren Wörtern, 1,2 s:** „Wasser Pegel Messstelle“ trifft 90 075 Paare aus Zeile und Wort, aber nur 750 Zeilen tragen alle drei Wörter (Regel `KNOWN`). Gerankt wurden alle 90 075 Paare.
- **Trigramme, 390 ms:** `word_similarity` wird je Kandidat zweimal gerechnet (Prüfung des Index, dann der Wert) und liest dazu 10⁴ Zeilen der Tabelle.
- **Python und Route, 100–300 ms:** Fusion über alle Treffer, Filter mit Listen aus 10⁴–10⁵ Kennungen.
- **JIT** spielt bei der Suche keine Rolle (gemessen mit `jit = on` und `off`).

**Lesart [A]:** Den Rang jedes Treffers zu rechnen, kostet etwa 9 µs je Treffer und lässt sich ohne Änderung der Reihenfolge nicht vermeiden (§6 Punkt 5). Gewinnen lässt sich, (1) was nach dem Ranken mit allen Treffern geschieht, (2) dass Filter nach dem Ranken greifen, (3) dass Paare gerankt werden, die nie Treffer sind.

## 2. Umsetzung Suche (PR 1)

1. **Filter in jedem Arm (Auftrag Punkt 1):** `search_datasets` nimmt `Kept(entry, category, full_ids, regions)`. Die Bedingungen stehen in beiden Armen vor jedem Rang:
   - gelistete Zeile: `e.category`, `e.regions && regions` (GIN-Index aus Migration 021);
   - volle Zeile: Kategorie über die Kennungen der Registry (`full_ids`, die Kategorie steht nicht im Index), Region nach derselben Regel wie bisher (`full_entries`: die Box überlappt die Region mehr als an der Grenze), jetzt über die Spalte `geometry` aus Migration 038;
   - `entry=full` bzw. `listed` lässt die andere Art Zeile ganz weg.
   Die Route filtert danach nichts mehr; `matching_listed` entfällt.
   **Auslegung A2 (aus dem Review):** Damit vergibt jeder Arm seine Plätze unter den Treffern des Filters, nicht mehr unter allen. Ein weggefilterter Treffer nimmt keinen Platz mehr ein, und die RRF kann behaltene Treffer anders ordnen als auf `main`, auch ohne Tiefe. Beispiel: Volltext A, B, C, X, Y; Trigramme B, C, X, Y, A; der Filter behält A, B, C. Auf `main` hat A im Trigramm-Arm Platz 5: B 0,032522, C 0,032002, A 0,031778. Jetzt Platz 3, weil X und Y nicht mehr davor stehen: B 0,032522, A 0,032266, C 0,032002. A rückt vor C. In den gemessenen Anfragen mit Filter (Tabelle unten) waren die ersten 20 trotzdem gleich wie auf `main`. Die Plätze über alle Treffer zu bilden und erst danach zu filtern, hieße, mit Filter wieder alle Treffer zu ranken und zu übertragen; der Gewinn mit Filter (3- bis 6-fach) ginge verloren (F6).
2. **Tiefe je Arm 1 000 (`DEPTH`):** Jeder Arm gibt seine besten 1 000 Treffer an die Fusion (RRF, k = 60). Gerankt wird in SQL wie bisher jeder Treffer (§1, Lesart), aber nur die besten verlassen Postgres gerankt. Die Fusion hat damit höchstens etwa 2 000 Einträge statt 10⁵.
3. **Ein Gleichstand wird nie geteilt (Auslegung A1):** Die Tiefe gilt nach dem Platz `rank()` (1, 2, 2, 4), nicht nach der Zeilenzahl. Alle Treffer mit demselben Wert wie Platz 1 000 kommen mit. Grund: Im Trigramm-Arm teilen sich bei breiten Wörtern Tausende Treffer einen Wert („map“: 13 144 Treffer mit Ähnlichkeit 1,0, nur 2 verschiedene Werte). Ein Schnitt nach Titel nähme daraus 1 000 alphabetisch – im ersten Versuch fehlte dadurch der bisher erste Treffer, und schon Platz 1 änderte sich bei 12 von 15 Anfragen. Mit der Regel A1 bleiben die ersten 20 in allen 15 gemessenen Anfragen gleich (§3). Folge: Bei breiten Wörtern kann ein Arm mehr als 1 000 Treffer liefern (gemessen bis 13 465).
4. **Trefferzahl (Auftrag Punkt 1, M5-40 F4):** Jeder Arm liefert zusätzlich die Zahl seiner Treffer. Hat ein Arm höchstens 10 000, liefert er alle Kennungen, und `numberMatched` ist die Größe der Vereinigung beider Arme, genau. Hat ein Arm mehr als 10 000 oder die Vereinigung mehr, fehlt `numberMatched`. Die Zahl zählt nach allen Filtern, wie bisher.
5. **Rang ohne `tsvector` in der Gruppierung:** Bei einem Wort wird der Rang beim Lesen der Zeile gebildet; jede Zeile trifft dann genau einmal, es gibt nichts zu gruppieren.
6. **Zwei Schritte bei mehreren Wörtern:** Welche Wörter eine Zeile trifft, kommt aus dem GIN-Index ohne Entpacken. Nur die Zeilen, die die Regel `KNOWN` behält, werden über ihre Zeilen-ID (`ctid`, gleiche Transaktion) erneut gelesen und je getroffenem Wort gerankt, in der Reihenfolge der Wörter wie seit M5-65. Gruppiert wird nach der Zeilen-ID statt nach Kennung und Titel.
7. **Blättern:** Die Liste endet am Ende der Fusion. Eine Seite dahinter ist leer und hat keinen Link `next`, auch wenn `numberMatched` mehr nennt (F2). Das Frontend blättert die Suche per `offset` und liest `numberMatched` bei der Suche nicht (`frontend/src/api.ts`, `fetchCatalogueSearch`).
8. **Unverändert:** Seiten ohne Text (`_catalogue_page`), Start bei Fläche oder Text (M5-65), Regeln zu Zahlen in Namen, Glossar, `ignored_filters`.

**Umfang:** etwa 230 geänderte Zeilen in `search.py`, `collection_search.py` und `listed_search.py`, dazu 170 Zeilen Tests (§7).

**Messung nach PR 1** [M], gleicher Bestand und gleiche Art wie §1, bester von 3:

| Anfrage | Treffer | `main` | PR 1 |
|---|---|---|---|
| data | 102 144 | 1 402 ms | 859 ms |
| map | 21 891 | 773 ms | 601 ms |
| water | 28 215 | 961 ms | 773 ms |
| Karte | 55 364 | 1 659 ms | 1 261 ms |
| Bebauungsplan | 21 283 | 929 ms | 781 ms |
| Wasser Pegel Messstelle | 7 849 | 1 726 ms | 793 ms |
| Sentinel-2 | 3 | 13 ms | 13 ms |
| data + Kategorie `water` | 11 248 | 1 304 ms | 231 ms |
| map + Region DE-RP | 2 822 | 766 ms | 297 ms |
| water + Region CH | 3 993 | 979 ms | 325 ms |
| water + `boundaries` + DE | 5 586 | 963 ms | 395 ms |
| data + Box Zürich | 454 | 48 ms | 50 ms |
| map + Fläche Bayern | 1 455 | 262 ms | 270 ms |
| data, nur gelistete | 102 138 | 1 553 ms | 837 ms |
| data, ab Platz 200 | 102 144 | 1 553 ms | 850 ms |

`numberMatched` ist in allen Fällen bis 10 000 gleich wie auf `main` und fehlt darüber. **Was bleibt [M]:** Bei einem breiten Wort ohne Filter kostet das Ranken aller Treffer im Volltext etwa 0,5 s je 5·10⁴ Treffer, der Trigramm-Arm 0,2–0,4 s, Übertragung und Fusion großer Gleichstände bis 0,3 s („Karte“: 19 384 Einträge in der Fusion). Beide Arme laufen nacheinander (F4).

## 3. Reihenfolge der ersten Treffer [M]

- **Ohne Tiefe gleich:** Mit unbegrenzter Tiefe (`depth=10⁹`) liefert der neue Code für alle 15 gemessenen Anfragen dieselben ersten 20 wie `main`. Ohne Filter ändert die Umstellung keine Reihenfolge; mit Filter kann sie es nach A2 (§2 Punkt 1), in den Messungen nicht auf den ersten 20.
- **Mit Tiefe 1 000 und A1:** Die ersten 20 sind in allen 15 Anfragen gleich wie auf `main`, ebenso die Seite ab Platz 200 („data“). Die bestehenden Tests der Suche und das Bewertungs-Set haben weit weniger als 1 000 Treffer je Arm; für sie ist das Ergebnis gleich (§7).
- **Wo es sich ändert:** Die Fusion verliert den Beitrag eines Arms, in dem ein Treffer hinter Platz 1 000 liegt. Erster Unterschied der ganzen Liste: „data“ ab Platz 818, „map“ 947, „Karte“ 972, „water“ 1 060, „Gewässer“ 328, „Bebauungsplan“ keiner. Früh liegt er bei mehreren Wörtern:

  **Beispiel „Wasser Pegel Messstelle“, Platz 40 und 41** (zwei synthetische Einträge A und B):

  | | Volltext | Trigramme | RRF bisher | RRF mit Tiefe 1 000 |
  |---|---|---|---|---|
  | A | Platz 13 | Platz 1 646 | 1/73 + 1/1 706 = 0,014285 | 1/73 = 0,013699 |
  | B | Platz 114 | Platz 58 | 1/174 + 1/118 = 0,014222 | 0,014222 |

  Bisher stand A auf Platz 40 vor B, jetzt steht B vor A: Der Beitrag von 1/1 706 für einen Trigramm-Platz jenseits von 1 000 fällt weg. Das ist die übliche Folge eines Fensters bei RRF; Elasticsearch schreibt dazu, dass sich die Reihenfolge mit der Größe des Fensters ändern kann (§6 Punkt 3).
- **Grenze [A]:** Auf die ersten 20 wirkt die Tiefe nur, wenn ein Treffer in einem Arm unter den ersten etwa 20 und im anderen hinter Platz 1 000 liegt und ein Nachbar fast denselben Wert hat. Die Seite ab Platz 40 kann sich ändern, die erste Seite hat sich in keiner Messung geändert.

## 4. `catalog-load` ohne Änderung (PR 2)

**Messung je Schritt** [M], gleicher Bestand (dazu 81 500 nicht veröffentlichte Zeilen: `not_geodata`, `needs_rule`, Dubletten), zweiter Lauf ohne Änderung, Zeit von `main()` ohne Start des Interpreters (≈ 0,4 s):

| Schritt | Zeit | Was er ohne Änderung tut |
|---|---|---|
| Lizenzdateien lesen (`load_licences`) | 2,0–2,1 s | `grants/govdata.yaml` (1,1 MB) mit dem YAML-Leser in reinem Python |
| Hash-Vergleich gelisteter Zeilen (`write_listed_search_index`) | 1,0–2,0 s | Hash der Eingaben von 102 313 Einträgen; Postgres kompiliert die Abfrage per JIT (0,85 s) |
| Handeinträge (`write_hand_entries`) | 1,35–1,5 s | Fläche aus `coverage_states` (Vereinigung von Staatsgrenzen) für jeden Handeintrag, auch unverändert |
| Suchindex voller Einträge (`write_search_index`) | 0,6 s | Ortsnamen je Box (`place_terms`): geodätische Fläche jedes Landes in der Box, auch bei globalen Boxen |
| Gemeinden (`write_municipalities`) | 0,3–0,6 s | rund 2 100 Anfragen, eine je Gemeinde |
| Rücknahme von Lizenzen (`withdraw`) | 0,05–0,3 s | — |
| Registry lesen | 0,15–0,2 s | YAML wie oben |
| Regionen, Dubletten, Rest | 0,3 s | — |
| **zusammen** | **≈ 7,1–7,4 s** | |

**Bei Otto 30,8 s [A]:** Der Lauf misst dort wohl `docker compose run --rm catalog-load` als Ganzes: Start der Container `pgstac-migrate` (Abhängigkeit, `pypgstac migrate` bei jedem Start) und `catalog-load`, Docker Desktop unter Windows. Welcher Teil davon wo liegt, zeigt erst die neue Zeitausgabe (Punkt 1 unten). Die Befehle in §8 messen beides getrennt.

**Maßnahmen**, jede ohne Wirkung auf das Ergebnis:

1. **Zeit je Schritt ausgeben:** `catalog-load` schreibt am Ende eine Zeile je Schritt (`step <name>: <s> s`), ohne Kennungen, Texte oder Flächen.
2. **YAML mit libyaml:** Derselbe strenge Leser (YAML 1.2 core, keine Anker, Aliase, doppelten Schlüssel) auf dem C-Parser von PyYAML. Anker und Aliase prüft ein Durchgang über die Ereignisse des C-Parsers (0,08 s für `govdata.yaml`); gemessen 0,4 s statt 1,6 s. Findet libyaml einen Fehler oder einen Anker, oder enthält der Text einen Tab (libyaml nimmt Tabs an, wo der Python-Leser ablehnt; Befund des Reviews), liest der Python-Leser die Datei, damit die Meldung gleich bleibt. Fehlt libyaml, liest der Python-Leser wie bisher. Gleiche Daten für alle 44 YAML-Dateien des Repos.
3. **JIT aus in der Transaktion von `catalog-load`** (`SET LOCAL jit = off`): Die Abfragen laufen einmal je Lauf, die Übersetzung kostet mehr, als sie spart (Hash-Vergleich 1,6 s → 1,0 s). Die Hashes der Dubletten einmal gruppiert statt je Eintrag eine Unterabfrage brachte nichts (gemessen) und ist nicht drin. Der Rest (0,7 s) ist der Hash selbst; ihn anders zu bilden, hieße neue `text_hash` und einmal alle 10⁵ Zeilen neu schreiben (bei 10⁵ etwa 50 s, M5-42 §3).
4. **Handeinträge:** Vor dem Upsert fragt eine Abfrage die gespeicherte Zeile mit genau seiner Bedingung (veröffentlicht, gleiches Dokument, gleiche Datei, gleicher Sortiertitel, gleicher Fußabdruck als Bytes); trifft sie, entfällt der Upsert. Teuer war nicht die Fläche (0,05 s), sondern die Regionen der CORINE-Fläche über Europa, die der Upsert vor dem Vergleich ableitet (1,3 s). Nach dem Review ersetzt diese Abfrage einen Vergleich ohne Fußabdruck, der bei anders gemessener Fläche (z. B. neues PostGIS) nicht geschrieben hätte.
5. **Ortsnamen:** Liegt ein Land ganz in der Box, zählt es mit seiner beim Lesen gemessenen Fläche, ohne geodätische Fläche der Schnittmenge (0,7 → 0,2 s). Die `text_hash` aller Registry-Einträge sind gleich.
6. **Gemeinden und Regionen:** eine Anfrage für alle Zeilen (`unnest`) mit derselben Bedingung `IS DISTINCT FROM`.
7. **Embeddings:** Es gibt sie noch nicht (Vektorarm M5-23). `plans/m5/m5-42-suche-gelistete.md` §4 Punkt 2 legt schon fest, dass nur Zeilen mit geändertem `text_hash` neu eingebettet werden; das bleibt die Vorgabe für M5-23.

**Gemessen nach PR 2** [M], gleicher Bestand, Zeitzeilen von `catalog-load`, drei Läufe:

| Schritt | `main` | PR 2 |
|---|---|---|
| Dateien lesen (Registry, Lizenzen, Freigaben, Gemeinden) | 2,5 s | 0,7–0,8 s |
| Suchindex voller Einträge | 0,6 s | 0,2 s |
| Regionen (mit erstem Laden von PostGIS) | 0,1–0,2 s | 0,3 s |
| Gemeinden | 0,3–0,6 s | 0,1 s |
| Handeinträge und Sperrliste | 1,35–1,5 s | 0,05 s |
| Rücknahme von Lizenzen | 0,05–0,3 s | 0,3 s |
| Suchindex gelisteter Einträge | 1,0–2,0 s | 1,1 s |
| Rest | 0,1 s | 0,05 s |
| **zusammen** | **7,1–7,4 s** | **2,7–2,9 s** |

Alle Zähler des Laufs sind 0 wie vorher. Bei Otto kommt der Start der Container dazu (§8 misst ihn getrennt).

## 5. Der synthetische Bestand [M]

Skripte nur in der Sitzung (wie M5-42, M5-65), danach gelöscht; keine echten Quellen abgerufen.

- **Quellen und Mengen** wie die Freigaben vom 21.–23.11.: govdata 94 258, opendata-swiss 7 748, fsdi-stac 305 veröffentlicht, dazu 2 Handeinträge; nicht veröffentlicht 66 000 `not_geodata`, 15 584 `needs_rule`, 916 Dubletten.
- **Herausgeber** aus `licenses/grants/*.yaml` mit freigegebener Lizenz, sonst nimmt `withdraw` die Einträge zurück.
- **Kategorien** nach den Signalen der Lauf-Berichte: `boundaries` 40 %, `infrastructure` 14 %, `water` 11 %, `nature` 10 %, Rest verteilt.
- **Ausdehnung:** govdata 42 % mit Footprint in Deutschland, sonst nur Regionen (`DE` und ein Land, gewichtet nach den Wartelisten); opendata-swiss 60 % Footprint in der Schweiz, sonst `CH` und ein Kanton; fsdi-stac immer Footprint.
- **Texte:** Titel aus den Arten der Stichproben („Bebauungsplan“, „Grundwassermessstelle“, „Topographische Karte“, Ortsnamen, Nummern), opendata-swiss mehrsprachig; Beschreibung log-normal, Median 260 Zeichen (govdata) bzw. 420 (opendata-swiss), höchstens 6 000; Schlagworte 1–6 aus einer Liste mit „opendata“, „geodaten“, „map“, „water“. „data“ trifft damit fast alle Einträge: der ungünstige Fall.
- Postgres 16, PostGIS 3.4, `shared_buffers` 128 MB, `work_mem` 4 MB, ein Client. Tabelle `earthx_dataset_search` 356 MB.

## 6. Stand der Technik: Tiefe je Arm und Zusammenführung

Was `adr/0026` §3.1 schon hat (Formel von Cormack et al. 2009, k = 60, Beispiel von pgvector), steht hier nicht noch einmal. Recherche eines Hilfsagenten am 27.11.2026; `www.elastic.co` und `plg.uwaterloo.ca` waren aus der Sitzung gesperrt, die Doku von Elasticsearch ist aus ihrem Repository gelesen.

1. **Tiefe bei Cormack et al. 2009:** nicht belegt. Die Läufe von TREC geben üblicherweise 1 000 Dokumente je Thema ab; dass RRF dort über 1 000 je Liste lief, ist Vermutung [S].
2. **Tiefe in Suchsystemen:**
   - Elasticsearch: `rank_window_size` ist die Größe jeder Einzelliste, mindestens `size`; Blättern mit `from` geht nur innerhalb des Fensters, dahinter kommen 0 Treffer [G]. Die Vorgabe nennt die Doku auf `main` mit 10, die Doku zu 8.x mit `size` [G, S].
   - OpenSearch: `pagination_depth` der Hybrid-Abfrage ist die Zahl der Treffer je Teilabfrage und Shard; sie muss beim Blättern gleich bleiben, eine Seite dahinter ist leer [G].
   - Azure AI Search: der Textarm einer Hybrid-Abfrage liefert bis `maxTextRecallSize` Treffer, Vorgabe 1 000, höchstens 10 000 [S].
   - Vespa: die globale Phase mit `reciprocal_rank_fusion` rechnet standardmäßig über die besten 100 [G].
   - Supabase: Beispiel `hybrid_search` mit `least(match_count, 30) * 2` je Arm [G]; pgvector-python `rrf.py` mit 20 je Arm [G].
3. **Wirkung auf die Reihenfolge:** Elasticsearch: „If `rank_window_size` changes, then the order of the results might change as well, even for the same ranks.“ Ein Dokument jenseits des Fensters ist der Fusion unbekannt [G]. OpenSearch sagt dasselbe für `pagination_depth` [G].
4. **Trefferzahl getrennt zählen:** Elasticsearch zählt mit `track_total_hits` standardmäßig bis 10 000 genau, darüber nur „mindestens“ [S]; beim RRF-Retriever ist die Gesamtzahl nach dem Beispiel der Doku nicht auf das Fenster begrenzt [G]. Azure zählt mit `countAllResults` auch Treffer außerhalb des Fensters [S]. Das entspricht der Zahl hier (bis 10 000 genau, darüber weggelassen, M5-40 F4).
5. **Top-k ohne Rang jedes Treffers:** Postgres selbst kann das nicht: „Ranking can be expensive since it requires consulting the tsvector of each matching document“ [G]. Der Index RUM (Postgres Pro, PostgreSQL License) sortiert über einen eigenen Abstand `<=>`, der nicht `ts_rank_cd` ist; er ist nicht im Image `postgis/postgis` und hieße eigenes Image und andere Reihenfolge [G, S]. Kein Thema für M5-66.
6. **Gleichstände am Schnitt:** In den gelesenen Quellen nicht behandelt. A1 (§2 Punkt 3) ist eigene Ableitung.

**Lesart [A]:** 1 000 je Arm liegt im üblichen Bereich (Azure 1 000, TREC-Tradition); Elasticsearch und OpenSearch halten das Fenster wie hier fest und lassen eine Seite dahinter leer.

**Quellen** (abgerufen 27.11.2026):

- https://raw.githubusercontent.com/elastic/elasticsearch/main/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion.md [G]
- https://raw.githubusercontent.com/elastic/elasticsearch/main/docs/reference/elasticsearch/rest-apis/retrievers/rrf-retriever.md [G]
- https://raw.githubusercontent.com/elastic/elasticsearch/main/docs/reference/elasticsearch/rest-apis/paginate-search-results.md [G]
- https://www.elastic.co/guide/en/elasticsearch/reference/8.17/rrf.html, https://www.elastic.co/guide/en/elasticsearch/reference/7.0/search-request-track-total-hits.html [S]
- https://raw.githubusercontent.com/opensearch-project/documentation-website/main/_vector-search/ai-search/hybrid-search/pagination.md [G]
- https://raw.githubusercontent.com/opensearch-project/documentation-website/main/_search-plugins/search-pipelines/score-ranker-processor.md [G]
- https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking [S]
- https://raw.githubusercontent.com/vespa-engine/documentation/master/en/ranking/phased-ranking.html [G]
- https://raw.githubusercontent.com/supabase/supabase/master/apps/docs/content/guides/ai/hybrid-search.mdx [G]
- https://raw.githubusercontent.com/pgvector/pgvector-python/master/examples/hybrid_search/rrf.py [G]
- https://raw.githubusercontent.com/postgres/postgres/master/doc/src/sgml/textsearch.sgml [G]
- https://raw.githubusercontent.com/postgrespro/rum/master/README.md [G]

## 7. Tests

- `test_search.py`:
  - **Filter in SQL:** Kategorie, Region, Art des Eintrags und Kombinationen treffen dieselbe Menge wie Suche ohne Filter und Filter danach; eine volle Zeile mit Region nach der Grenzregel; eine Kategorie, die kein voller Eintrag hat; leere Kennungsliste.
  - **Tiefe:** Mit kleiner Tiefe (Schlüsselwort `depth`) fällt ein Treffer aus der Fusion eines Arms; ein Gleichstand am Schnitt bleibt ganz; mit Tiefe 1 und lauter Gleichständen gleiche Reihenfolge wie ohne Tiefe.
  - **Zahl:** genau bis zur Grenze (Schlüsselwort `count_up_to`), ein Treffer darüber ergibt `None`; Vereinigung beider Arme ohne Doppelzählung; ohne Text die Zahl der Liste.
  - **Mehrere Wörter:** gleiche Reihenfolge und Ränge wie die einstufige Form (Vergleich über das Raster aus M5-65).
  - **Fehlerfälle:** unbekannte Art des Eintrags kommt nicht an (Route prüft weiter mit `400`); Region ohne Zeile in `earthx_region` trifft nichts.
- `test_api_listed.py`, `test_api_collection_search.py`: `numberMatched` fehlt über der Grenze, Seite hinter dem Ende leer ohne `next`, Filter weiter wirksam mit Text.
- Bewertungs-Set: unverändert (Deutsch 15/19, Englisch 41/42, alle Rangpositionen).
- PR 2: Zeitzeile ohne Kennungen; strenger YAML-Leser auf beiden Wegen gleich (gleiche Daten, gleiche Fehler für Anker, Alias, doppelten Schlüssel, Datum als Text, Syntaxfehler); Handeintrag ohne Änderung rechnet keine Fläche, nach Änderung der Grenzen schon; zweiter Lauf schreibt nichts; Gemeinden und Regionen gleich wie vorher.

## 8. Messung bei Otto (PowerShell 5.1, nur `docker compose`)

Skript `scripts/m5-66-messung.ps1` (PR 1). Es läuft vom Wurzelverzeichnis des Repos, wo immer die Datei liegt, und schreibt nach `..\earthx-ausgaben\m5-66\`, nie ins Repo: `<Label>-suche.csv` (je Anfrage bester Wert und Median in ms, `numberReturned`, `numberMatched`, ob es eine nächste Seite gibt, ein Hash der Kennungen der Seite in ihrer Reihenfolge) und `<Label>-laden.txt` (Dauer von `catalog-load` mit und ohne `pgstac-migrate`, die Zeitzeilen und Zähler). Keine Kennungen, Titel oder Flächen; die einzigen Texte sind die drei Wörter „data“, „map“, „water“, je ohne Filter, mit Kategorie `water`, mit Region DE, mit Kategorie `boundaries` und Region DE, mit Region CH, dazu „data“ ab Platz 200.

Vorher (Stand `main`, das Skript aus dem Branch von PR 1 geholt):

```powershell
git switch main
git pull
git fetch origin claude/gracious-brahmagupta-30310c
New-Item -ItemType Directory -Force ..\earthx-ausgaben\m5-66 | Out-Null
git show FETCH_HEAD:scripts/m5-66-messung.ps1 | Set-Content -Encoding ASCII ..\earthx-ausgaben\m5-66\messung.ps1
docker compose build api catalog-load pgstac-migrate
docker compose up -d api
powershell -NoProfile -ExecutionPolicy Bypass -File ..\earthx-ausgaben\m5-66\messung.ps1 -Label vorher
```

Nachher (beide PRs zusammen auf einem lokalen Branch, nichts davon wird gepusht):

```powershell
git fetch origin claude/gracious-brahmagupta-30310c claude/gracious-brahmagupta-30310c-load
git switch -c m5-66-messung origin/claude/gracious-brahmagupta-30310c
git merge --no-edit origin/claude/gracious-brahmagupta-30310c-load
docker compose build api catalog-load pgstac-migrate
docker compose up -d api
powershell -NoProfile -ExecutionPolicy Bypass -File ..\earthx-ausgaben\m5-66\messung.ps1 -Label nachher
git switch main
```

Gleicher Hash in der Spalte `Reihenfolge` heißt: gleiche Treffer in gleicher Reihenfolge auf der ersten Seite.

## 9. Fragen an Otto

**F1 — Zielwerte Suche** (bei 10⁵ gelisteten Einträgen, über die Route, bei Otto nachgemessen).

1. Breites Wort ohne Filter unter 1 s, mit Kategorie oder Region unter 0,5 s; mehr nur mit Folgeaufgabe F4 **(Empfehlung)**
2. Jede Anfrage unter 0,5 s; dann gehört F4 in diese Aufgabe
3. Keine Zielwerte; was M5-66 bringt, genügt

**F2 — Blättern hinter dem Ende der Fusion** (§2 Punkt 7).

1. Die Liste endet nach den fusionierten Treffern (bei breiten Wörtern einige Tausend); `numberMatched` nennt die Zahl aller Treffer bis 10 000 **(Empfehlung)**
2. Die Tiefe wächst mit `offset` (Tiefe = max(1 000, offset + 20)); jede Seite ist erreichbar, die Reihenfolge kann sich zwischen Seiten verschieben

**F3 — Gleichstand am Schnitt (A1).**

1. Ein Gleichstand bleibt ganz, auch wenn ein Arm dadurch über 1 000 liefert **(Empfehlung)**
2. Genau 1 000 je Arm, Gleichstand nach Titel geteilt; schneller, aber schon Platz 1 kann sich ändern (§2 Punkt 3)

**F4 — Was danach bleibt** (gemessen in der Sitzung: breite Wörter ohne Filter 0,6–1,3 s).

1. Eigene Folgeaufgabe, erst nach Ottos Messung: beide Arme gleichzeitig auf zwei Verbindungen (Zeit des langsameren statt Summe, geschätzt −30 bis −40 %) **(Empfehlung)**
2. Gleich in diesem PR
3. Nichts weiter

**F6 — Plätze mit Filter (A2, aus dem Review).**

1. Plätze unter den Treffern des Filters, wie gebaut; die Reihenfolge kann sich gegenüber `main` verschieben, wenn weggefilterte Treffer vor behaltenen standen **(Empfehlung)**
2. Plätze unter allen Treffern, danach filtern; Reihenfolge wie `main`, mit Filter aber kein Gewinn (wieder 0,8–1,3 s)

**F5 — Zielwert `catalog-load` ohne Änderung.**

1. Innerhalb von `catalog-load` (Zeitzeilen) unter 3 s bei 10⁵; den Start der Container misst Otto getrennt und entscheidet danach, ob `pgstac-migrate` bei jedem Lauf nötig ist **(Empfehlung)**
2. Der ganze Befehl `docker compose run --rm catalog-load` unter 10 s; dazu gehört dann eine Änderung an `docker-compose.yml` (Abhängigkeit `pgstac-migrate`)
3. Keine Zielwerte
