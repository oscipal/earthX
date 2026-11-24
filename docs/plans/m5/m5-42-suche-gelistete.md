# M5-42 — Gelistete Einträge in der Suche (Befund, Umsetzung lexikalisch, Plan Vektorarm)

- **Auftrag:** Otto, 23.11.2026 (Fehler „Suche im Data catalogue findet gelistete Einträge nicht, teils auch volle nicht“). Umfasst M5-42 (lexikalische Suche indexfähig, M5-35 B7) und den Teil von M5-23, der gelistete Einträge betrifft.
- **Autonomiestufe:** B. Draft-PR gegen `main`.
- **Grundlage:** `adr/0026` §4, §14 Punkt 1 („volle und gelistete Einträge in einer Suchtabelle mit einer Spalte und einem Index“); `plans/m5/m5-40-gelistete-in-postgres.md` F7; `plans/m5/m5-35-skalierbarkeit.md` §6.3 (B7); `plans/m5/m5-41-pgvector.md` §4.2.
- **Belegstufen** wie in `adr/0026`: **M** gemessen in dieser Sitzung, **P** im Repo gelesen, **A** eigene Ableitung.

Punkt 2 des Auftrags (lexikalisch und Vektor) ist größer als ein Nachtrag, und den Vektorarm gibt es noch nicht (§1). Dieser PR bringt deshalb nach Punkt 3 des Auftrags den Befund mit Test und den lexikalischen Teil; der Vektorarm steht hier als Plan mit Fragen (§4, §5).

## 1. Wie die Suche heute läuft und warum sie nichts Gelistetes findet [P, M]

- **Weg:** Das Suchfeld des Data catalogue schickt nach 300 ms Pause `POST /stac/collections` mit `q` (`frontend/src/api.ts`, `fetchCatalogueSearch`). Eine eigene Such-Route gibt es nicht: Das ist die Collection Search aus M5-22c (`adr/0026` §4.5). Die übrigen `POST /stac/collections` im Log sind die Seiten der Gruppen (eine Anfrage je Kategorie, weitere beim Scrollen).
- **Suche:** `api/collection_search.py` ruft `catalog/search.py` `search_datasets` auf: Volltext (`simple`, `german`, `english`, `unaccent`, Glossar) und Trigramme, per RRF zusammengeführt, über die Tabelle `earthx_dataset_search`. **Einen Vektorarm gibt es noch nicht:** M5-23 ist offen und setzt das Postgres-Image mit pgvector voraus (M5-43); im Repo gibt es weder Modell noch Spalte für ein Embedding.
- **Ursache:** `catalog-load` schrieb nur die Einträge der Registry in den Index (`write_search_index`, 9 volle Einträge), und die Route warf jede Kennung weg, die kein voller Eintrag war. Das war so geplant: „`q` sucht bis M5-42 nur volle Einträge“ (M5-40 F7). Ein Test hielt genau das fest (`test_with_text_only_full_entries_are_searched_until_m5_42`), und die übrigen Tests der Suche löschen die gelisteten Einträge vorher. Deshalb fiel die Lücke nach dem ersten großen Harvest (#400, 7 748 Einträge) erst in der Oberfläche auf.
- **„search index written: none“** ist kein Fehler: Die Zeile nennt nur volle Einträge, und die schreibt ein zweiter Lauf nicht neu (idempotent, M5-22b).
- **„Landsat“:** `landsat-c2-l2` ist ein gelisteter Handeintrag (M5-17), kein voller. Es ist dieselbe Ursache. Volle Einträge findet die Suche [M, vor der Änderung, über die Route]: „Sentinel-2“, „swissalti3d“, „Höhenmodell“ und „elevation“ liefern ihre Datensätze. „Landsat“ lieferte vorher die beiden WorldCover-Einträge: Das Trigramm „land“ aus „land cover“ erreicht genau die Schwelle 0,5. Jetzt steht Landsat selbst vorn. Vermisst Otto einen anderen vollen Datensatz, bitte das Suchwort nennen (Frage F1).
- **Test:** `test_api_listed.py::test_text_finds_a_listed_entry_like_a_full_one` ersetzt den Test von F7; auf `main` findet `q` den gelisteten Eintrag nicht.

## 2. Umsetzung in diesem PR (lexikalisch)

1. **Migration 035:** Spalte `entry` (`full` oder `listed`) in `earthx_dataset_search`; gelistete Zeilen haben keine Haltung der Items.
2. **Suchtext eines gelisteten Eintrags** (`search_text.py`, `listed_search_text`), in den vier Teilen von `adr/0026` §4.1:
   - A: Kennung, Titel und die **Titel seiner Dubletten** (`state = 'duplicate'`, `duplicate_of`). So findet „Götterbaum“ den Haupteintrag, auch wenn nur eine Dublette das Wort im Titel trägt.
   - B: Schlagworte, die Namen seiner Regionen aus `place_names.yaml` (Abschnitt `places`, deutsch, englisch, französisch, italienisch, z. B. „Schweiz“, „Switzerland“, „Zürich“; F3 = 1) und das Wort seiner Kategorie. Eine Region ohne Eintrag dort trägt keinen Namen bei.
   - C: Beschreibung.
   - D: Herausgeber und Zugang („free account required“, „requester pays“).
   - Trigramme: Kennung, Titel, Titel der Dubletten, Schlagworte.
   - **Auslegung A1:** Die Ortsbegriffe der vollen Einträge (`place_terms`, aus Natural Earth) kosten je Eintrag 1,1 ms [M], bei 10⁵ Einträgen fast zwei Minuten je Lauf, und liefern für kleine Flächen nichts. Gelistete Einträge nehmen deshalb die Regionen, die M5-40 schon abgeleitet hat. `catalog` liest dafür nur den Abschnitt `places` der Datei; `discovery` liest sie weiter selbst (`catalog` darf `discovery` nicht importieren).
3. **Pflege des Index** (`search_index.py`, `write_listed_search_index`), am Ende von `catalog-load`, nachdem die Freigaben veröffentlicht sind:
   - **F2 = 2:** Postgres rechnet je veröffentlichtem Eintrag einen Hash der Eingaben: ein Salz aus Textversion, Ortsnamen und Wörtern der Kategorien, `content_sha256`, Regionen, Schlagworte, Kategorie, Herausgeber, Zugang, Box, Zeitraum und die `content_sha256` der Dubletten. Nur Einträge, deren Hash von `text_hash` ihrer Zeile abweicht, kommen nach Python. Dort wird ihr Text gebaut, und je 2 000 werden mit `to_tsvector` geschrieben.
   - Eine gelistete Zeile trägt diesen Hash der Eingaben als `text_hash`; M5-23 bettet neu ein, wenn er sich ändert (§4).
   - Zeilen von Einträgen, die nicht mehr veröffentlicht sind oder deren Kennung ein voller Eintrag übernommen hat, werden gelöscht.
   - Die Startprüfung von `api` und `write_search_index` lassen die gelisteten Zeilen in Ruhe.
4. **Suche** (`search.py`):
   - Eine gelistete Zeile zählt nur, solange ihr Eintrag `published` ist (Join auf `earthx_listed_entry`). Nimmt der Harvest einen Eintrag zwischen zwei Läufen von `catalog-load` zurück, ist er sofort kein Treffer mehr.
   - Die Fläche wird gegen den Footprint geprüft, wie bei den Seiten ohne Text.
   - Ein Eintrag ohne Zeitraum fällt nicht heraus und wird in `ignored_filters` genannt, wie bei den vollen Einträgen.
   - Ohne Text bleibt die Liste bei den vollen Einträgen, die Seiten des Katalogs holen die gelisteten wie bisher selbst.
5. **Index-Nutzung (M5-35 B7):**
   - Der Volltext verbindet eine Zeile nur noch mit den Einheiten, die sie trifft (`JOIN … ON document @@ query`, GIN-Index), statt jede Zeile mit jeder Einheit zu kreuzen. Das Ergebnis ist dasselbe, weil eine Einheit ohne Treffer nichts zum Rang beiträgt.
   - Der Trigramm-Arm fragt `<%` mit der Schwelle als Einstellung der Transaktion statt `word_similarity() >= t` (Trigramm-Index, gleiche Bedeutung).
   - Die Namen vor einer Zahl („Landsat 9“) liest die Suche nur aus Zeilen, die das Wort enthalten (`LIKE ANY` über den Trigramm-Index), statt aus allen.
   - `ranks()` war quadratisch in der Zahl der Treffer. Bei 5·10⁴ Treffern hing eine Anfrage minutenlang in Python [M]; jetzt sortiert die Funktion einmal.
   - Die Fläche läuft weiter ohne räumlichen Index über die Box (B7, dritter Punkt). Das bleibt offen (F4).
6. **Route** (`collection_search.py`): Gelistete Treffer behalten ihren Rang. Kategorie und Region prüft die Route an der Zeile des Eintrags, nicht an der Registry. Ein Treffer ist dasselbe Dokument wie `/stac/collections/{id}` (mit `earthx:also_at`). `entry=full` und `entry=listed` wirken auch mit Text.

7. **Bewertungs-Set (F7 = 1):** CLC und LS tragen ihre Ids (`corine-land-cover`, `landsat-c2-l2`); ein Id des Sets darf ein voller Eintrag oder ein Handeintrag von `catalog/listed/` sein. Die Auswertung läuft über den Index, den `catalog-load` schreibt. Geweckt sind Q13–Q16, Q45 und Q46.
   - Ergebnis: Deutsch 15 von 19 unter den ersten fünf (vorher 9 von 12), Englisch 41/42. Q14 „land cover classification“ findet CORINE nicht, weil das Wort „classification“ nur WorldCover trägt und der lexikalische Arm jedes bekannte Wort verlangt. Das schließt erst der Vektorarm.
   - Die Untergrenzen im Test folgen den aktiven Fragen wie beim Wecken von Q34/Q35: Deutsch 15/19 und 29/38, Englisch 41/42 und 27/28. Für dieselben Fragen sinken sie nie.

**Umfang:** etwa 380 geänderte Zeilen Code und 340 Zeilen Tests, Fixture und Browser-Check; über dem Richtwert durch F2, F3 und F7 (Otto, 23.11.2026) und die Tests.

8. **Einträge ohne Fußabdruck (Fehler beim Test von Otto, 23.11.2026):** `catalog-load` brach nach ~140 s ab: „null value in column "west"“ bei einem Eintrag von opendata-swiss, dessen Ausdehnung nur über Regionen bekannt ist.
   - **Ursache:** Der Index nahm an, jeder veröffentlichte gelistete Eintrag habe einen Footprint, und die Spalten der Box waren `NOT NULL`. Einträge ohne Footprint sind aber gewollt (`extent_basis` `publisher`, `catalog`, `none`; M5-20 F1, F11, A19). Die Tests legten nur Einträge mit Footprint an.
   - **Korrektur:**
     - **Migration 036:** Die Box einer gelisteten Zeile darf fehlen; eine volle Zeile hat immer eine, und eine Box hat alle vier Kanten oder keine (CHECK). 036 ist eine eigene Migration, weil 035 bei Otto schon angewandt ist. Der Runner wendet sie beim nächsten `catalog-load` von selbst an, ohne Handarbeit.
     - **Hash der Eingaben unverändert:** `concat_ws` überspringt die fehlenden Kanten. Zeilen, die schon im Index stehen, werden deshalb nicht neu gebaut.
   - **Verhalten:** Ohne Footprint trifft der Flächenfilter den Eintrag nie; Text, Kategorie und Region finden ihn. Die Ortsnamen seiner Regionen stehen im Suchtext.
   - **Tests:** Ein `catalog-load` mit gemischten Einträgen (Footprint, nur Regionen, gar keine Ausdehnung) läuft durch, ein zweiter Lauf schreibt nichts. Dazu kommen Index, Suche und Route je mit diesen Fällen.
9. **Abbruch von `catalog-load` [P, M]:** Der Lauf ist eine einzige Transaktion (`load.py`). Bricht ein Schritt ab, rollt Postgres alles zurück, auch die Hand- und Sperreinträge und die Veröffentlichung der Freigaben; halb steht nichts. In der Sitzung nachgestellt: einen Handeintrag gelöscht, einen Eintrag ohne Footprint angelegt, `catalog-load` scheiterte am Index, und der Handeintrag fehlte danach weiterhin. Test: `test_a_load_that_fails_at_the_index_leaves_nothing_of_its_earlier_steps`. Folge für Otto: Die Freigabe von govdata war nach dem Abbruch nicht veröffentlicht; der nächste Lauf mit diesem Stand holt sie nach und baut dabei den Index aller gelisteten Einträge einmal (bei 10⁵ etwa 50 s, §3).

## 3. Messung bei 10⁵ gelisteten Einträgen [M]

Synthetische Einträge (`source_id = 'bench'`), lokal in der Cloud-Sitzung (Postgres 16, ein Client), danach wieder gelöscht. Skript nur in der Sitzung, nicht im Repo.

- **Titel und Beschreibungen:** aus 60 deutschen Wörtern. Das ist der ungünstige Fall: Ein Wort steht in rund der Hälfte aller Einträge. Bei echten Daten trifft „Götterbaum“ einige Dutzend Einträge, nicht 53 000.
- **Footprints:** in der Schweiz; jeder zweite Eintrag mit Zeitraum.

**`catalog-load`, Teil der gelisteten Einträge:**

| Lauf | erste Fassung | nach F2 | geschrieben |
|---|---|---|---|
| erster Lauf, 10⁵ neu | 39,9 s | 50,6 s | 100 000 |
| nichts geändert | 11,8 s | **0,9 s** | 0 |
| 10 % geändert | 14,4 s | 5,9 s | 10 000 |

- **`catalog-load` als Ganzes, nichts geändert:** 7,3 s mit 10⁵ gelisteten Einträgen, 6,5 s mit den 2 Handeinträgen. Der Rest sind Regionen, Gemeinden, pgstac und Freigaben.
- Spitzenspeicher des Prozesses: 174 MiB nach F2 (vorher 352 MiB), weil nur noch geänderte Einträge und je ein Stapel in Python liegen.
- Tabelle und Indizes `earthx_dataset_search`: 369 MiB bei 10⁵ Zeilen (der `tsvector` hält jeden Teil in drei Konfigurationen).
- Der erste Lauf ist langsamer als vorher, weil die Texte jetzt die mehrsprachigen Ortsnamen tragen (F3) und Postgres die Hashes rechnet.

**Suche, `search_datasets`, je bester von 3 Läufen:**

| Anfrage | Treffer | `main` (SQL von vorher) | dieser PR | mit Fläche (Zürich) |
|---|---|---|---|---|
| Sentinel-2 | 3 | 1 991 ms | 7 ms | 7 ms |
| Landsat 9 | 0 | – | 7 ms | 9 ms |
| Götterbaum | 53 338 | 2 236 ms | 1 423 ms | 721 ms (645 Treffer) |
| Neophyten Kanton | 53 607 | 3 600 ms | 2 905 ms | 1 588 ms (621 Treffer) |
| Hochwasser Gefahren Karte | 18 922 | 3 013 ms | 2 708 ms | 1 634 ms (248 Treffer) |

- Für die Spalte `main` ist `ranks()` schon ersetzt, sonst endet die Anfrage nicht.
- **Lesart [A]:** Seltene Wörter sind jetzt schnell, weil die Indizes greifen. Bei Wörtern, die zehntausende Einträge tragen, kostet der Rang (`ts_rank_cd` über jede getroffene Zeile) und die Fusion in Python über alle Treffer. Abhilfe: nur die besten N je Arm ranken (Tiefe der Liste für die RRF, wie `ef_search` in `adr/0026` §14) und `numberMatched` dann schätzen oder kappen (F5).

## 4. Plan: Vektorarm für volle und gelistete Einträge

Voraussetzung ist M5-43 (Postgres-Image mit pgvector, Erlaubnis für `.github/` und das Setup). Danach kommt M5-23 mit der Wahl des Modells am Bewertungs-Set. Gelistete Einträge brauchen darin nur drei Dinge:

1. **Spalte und Index:**
   - `embedding halfvec(D)` und `embedding_model text` in `earthx_dataset_search`, für beide Arten von Zeilen. HNSW wie in `adr/0026` §14.
   - Gelistete Einträge brauchen keinen eigenen Index, weil die Tabelle schon gemeinsam ist.
2. **Inkrementelles Einbetten:**
   - Neu eingebettet wird nur eine Zeile, deren `text_hash` oder `embedding_model` sich geändert hat (`adr/0026` §4.6). Bei gelisteten Zeilen ist `text_hash` seit diesem PR der Hash der Eingaben (§2 Punkt 3).
   - Wer eine Zeile neu schreibt, setzt ihr Embedding auf `NULL`. `catalog-load` holt danach die Zeilen mit `embedding IS NULL OR embedding_model <> :model`, bettet sie in Stapeln ein (z. B. 256) und schreibt die Vektoren zurück.
   - Ein Lauf ohne Änderung bettet nichts ein.
   - **F6 = 1:** Jeder Stapel läuft in einer eigenen Transaktion nach dem Hauptlauf. Ein Abbruch lässt Zeilen ohne Vektor, die der nächste Lauf nachholt; der Vektorarm überspringt sie bis dahin.
3. **Zahlen:**
   - **Speicher [M aus M5-41 §4.2]:** Bei 10⁵ Zeilen, D = 384, `halfvec` kommen etwa 89 MB Tabelle und 112 MB HNSW-Index (11 s Bau) dazu; bei D = 768 159 MB und 195 MB.
   - **Einbetten [A, nicht gemessen]:** Hugging Face ist aus der Sitzung gesperrt [M, 403 des Proxys am 23.11.2026]. Annahme für e5-small int8 auf CPU: einige Hundert Texte je Sekunde und Kern. Danach brauchen 10⁵ Einträge beim ersten Lauf etwa 5–20 Minuten, ein Tag mit 1 % Änderungen Sekunden. Gemessen wird das in M5-23 mit dem gewählten Modell.
   - Ohne inkrementelles Einbetten würde jeder Start von `catalog-load` den ersten Lauf wiederholen. Das ist der Grund für Punkt 2.

## 5. Antworten Otto (23.11.2026)

| Frage | Antwort | Folge |
|---|---|---|
| F1 | 1 | Otto testet nach dem Merge und nennt Suchwörter, falls ein voller Datensatz fehlt |
| F2 | 2 | in diesem PR (§2 Punkt 3); `catalog-load` ohne Änderung bei 10⁵: 0,9 s statt 11,8 s für den Index, 7,3 s als Ganzes (§3) |
| F3 | 1 | in diesem PR: Ortsnamen aus `place_names.yaml` (§2 Punkt 2) |
| F4 | 1 | eigene Aufgabe **M5-65** im M5-Plan |
| F5 | 1, Trefferzahl wie M5-40 F4 (genau bis 10 000, darüber weggelassen) | nicht in diesem PR: nur die besten 1 000 je Arm ranken; die Filter für Kategorie und Region müssen dazu vor die Tiefe in die SQL-Abfrage, sonst stimmt die Zahl nicht. Eigene Aufgabe **M5-66** (Otto, 23.11.2026) |
| F6 | 1 | gilt für M5-23 (§4 Punkt 2) |
| F7 | 1, in diesem PR | §2 Punkt 7; Untergrenzen Deutsch 15/19, Englisch 41/42 bestätigt (Otto, 23.11.2026), für vorher aktive Fragen gilt „nie senken“ weiter |

Die Fragen stehen unten unverändert als Historie.

## 6. Fragen an Otto (beantwortet, §5)

**F1 — Volle Datensätze, die fehlen.** Volle Einträge findet die Suche in der Sitzung (§1). Landsat ist gelistet.

1. Bitte die Suchwörter nennen, bei denen ein voller Datensatz fehlt; ich prüfe sie nach dem Merge **(Empfehlung)**
2. Es war nur Landsat; erledigt

**F2 — Lauf von `catalog-load` ohne Änderung (12 s bei 10⁵).**

1. Jetzt so lassen. In einem Folge-PR speichert die Tabelle einen Hash der Eingaben (`content_sha256`, Regionen, Schlagworte, Hashes der Dubletten), den Postgres selbst vergleicht. Dann baut Python nur geänderte Texte **(Empfehlung)**
2. Gleich in diesem PR (etwa +60 Zeilen)
3. So lassen, auch bei 10⁶

**F3 — Ortsnamen gelisteter Einträge (A1).**

1. Namen aus `place_names.yaml` (mehrsprachig, „Schweiz“, „Genf“) statt `earthx_region.name`; die Datei wandert dazu von `discovery` nach `catalog` oder wird dort gelesen **(Empfehlung)**
2. So lassen (ein Name je Region)
3. `place_terms` wie bei vollen Einträgen, trotz 1,1 ms je Eintrag

**F4 — Fläche mit räumlichem Index (B7, dritter Punkt).** Mit Fläche brauchen breite Anfragen noch 0,7–1,6 s.

1. Eigene kleine Aufgabe: die Bedingung der Fläche für gelistete Zeilen über den GiST-Index von `earthx_listed_entry.footprint` vorziehen, für volle über eine Spalte `geometry` **(Empfehlung)**
2. Mit M5-23

**F5 — Tiefe der Liste je Arm.** Breite Anfragen kosten 1,4–2,9 s bei 10⁵ (§3).

1. Nur die besten 1 000 je Arm ranken, `numberMatched` bis zu dieser Zahl genau, darüber weglassen (wie M5-40 F4) **(Empfehlung)**
2. Alle Treffer ranken wie jetzt

**F6 — Einbetten in Stapeln.**

1. Jeder Stapel in eigener Transaktion nach dem Hauptlauf; ein Abbruch lässt Zeilen ohne Vektor, die der nächste Lauf nachholt, und der Vektorarm überspringt sie bis dahin **(Empfehlung)**
2. Alles in der einen Transaktion von `catalog-load`

**F7 — Bewertungs-Set.** CLC und LS stehen in `evaluation_set.yaml` mit `id: null` „bis M5-42“ (M5-17 A2).

1. Ids `corine-land-cover` und `landsat-c2-l2` eintragen, die ruhenden Fragen damit wecken, in einem eigenen kleinen PR **(Empfehlung)**
2. Erst mit M5-23
