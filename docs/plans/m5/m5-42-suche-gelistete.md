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
   - B: Schlagworte, die Namen seiner Regionen (`earthx_region.name`) und das Wort seiner Kategorie.
   - C: Beschreibung.
   - D: Herausgeber und Zugang („free account required“, „requester pays“).
   - Trigramme: Kennung, Titel, Titel der Dubletten, Schlagworte.
   - **Auslegung A1:** Die Ortsbegriffe der vollen Einträge (`place_terms`, deutsch und englisch aus Natural Earth) kosten je Eintrag 1,1 ms [M], bei 10⁵ Einträgen fast zwei Minuten je Lauf, und liefern für kleine Flächen nichts. Für gelistete Einträge stehen deshalb die Namen der Regionen im Text, die M5-40 schon abgeleitet hat (ein Name je Region, z. B. „Switzerland“, „Zürich“). Deutsche Staatsnamen wie „Schweiz“ fehlen damit (Frage F3).
3. **Pflege des Index** (`search_index.py`, `write_listed_search_index`), am Ende von `catalog-load`, nachdem die Freigaben veröffentlicht sind:
   - Die Funktion baut den Text jedes veröffentlichten Eintrags. Neu geschrieben (mit `to_tsvector`) werden nur Zeilen, bei denen sich der Hash des Textes, die Box oder der Zeitraum geändert hat.
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

**Umfang:** etwa 330 geänderte Zeilen Code und 225 Zeilen Tests und Browser-Check; über dem Richtwert von 400 nur durch die Tests.

## 3. Messung bei 10⁵ gelisteten Einträgen [M]

Synthetische Einträge (`source_id = 'bench'`), lokal in der Cloud-Sitzung (Postgres 16, ein Client), danach wieder gelöscht. Skript nur in der Sitzung, nicht im Repo.

- **Titel und Beschreibungen:** aus 60 deutschen Wörtern. Das ist der ungünstige Fall: Ein Wort steht in rund der Hälfte aller Einträge. Bei echten Daten trifft „Götterbaum“ einige Dutzend Einträge, nicht 53 000.
- **Footprints:** in der Schweiz; jeder zweite Eintrag mit Zeitraum.

**`catalog-load`, Teil der gelisteten Einträge:**

| Lauf | Zeit | geschrieben |
|---|---|---|
| erster Lauf, 10⁵ neu | 39,9 s | 100 000 |
| zweiter Lauf, nichts geändert | 11,8 s | 0 |
| 10 % geändert | 14,4 s | 10 000 |

- Spitzenspeicher des Prozesses 352 MiB (Python, ganzer Lauf).
- Tabelle und Indizes `earthx_dataset_search`: 429 MiB bei 10⁵ Zeilen (der `tsvector` hält jeden Teil in drei Konfigurationen).
- **Bewertung [A]:** 12 s ohne Änderung sind spürbar und wachsen linear: bei 10⁶ rund zwei Minuten je `catalog-load`, auch wenn nichts geschah. Der Lauf baut jeden Text in Python, um den Hash zu vergleichen. Vorschlag in F2.

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
   - Neu eingebettet wird nur eine Zeile, deren `text_hash` oder `embedding_model` sich geändert hat (`adr/0026` §4.6). Der `text_hash` steht seit diesem PR für jede gelistete Zeile.
   - `catalog-load` holt nach dem Schreiben des Textes die Zeilen mit `embedding IS NULL OR embedding_model <> :model`, bettet sie in Stapeln ein (z. B. 256) und schreibt die Vektoren zurück.
   - Ein Lauf ohne Änderung bettet nichts ein.
   - Damit ein abgebrochener Lauf die geschriebenen Texte nicht verliert, schreibt er je Stapel. Offen ist, ob in eigenen Transaktionen (F6).
3. **Zahlen:**
   - **Speicher [M aus M5-41 §4.2]:** Bei 10⁵ Zeilen, D = 384, `halfvec` kommen etwa 89 MB Tabelle und 112 MB HNSW-Index (11 s Bau) dazu; bei D = 768 159 MB und 195 MB.
   - **Einbetten [A, nicht gemessen]:** Hugging Face ist aus der Sitzung gesperrt [M, 403 des Proxys am 23.11.2026]. Annahme für e5-small int8 auf CPU: einige Hundert Texte je Sekunde und Kern. Danach brauchen 10⁵ Einträge beim ersten Lauf etwa 5–20 Minuten, ein Tag mit 1 % Änderungen Sekunden. Gemessen wird das in M5-23 mit dem gewählten Modell.
   - Ohne inkrementelles Einbetten würde jeder Start von `catalog-load` den ersten Lauf wiederholen. Das ist der Grund für Punkt 2.

## 5. Fragen an Otto

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
