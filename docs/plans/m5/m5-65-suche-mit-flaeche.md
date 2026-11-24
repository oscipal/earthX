# M5-65 — Suche mit Fläche schneller

- **Auftrag:** Otto, 24.11.2026 (Stufe A). Folgt aus `plans/m5/m5-42-suche-gelistete.md` F4 = 1: Die Flächenbedingung für gelistete Zeilen über den GiST-Index von `earthx_listed_entry.footprint` vorziehen, für volle über eine Spalte `geometry`.
- **Grundlage:** `plans/m5/m5-discovery-und-suche.md` Zeile M5-65; `adr/0026` §4; `plans/m5/m5-42-suche-gelistete.md` §2 Punkt 5 und §3; Entscheidungslog bis 24.11. (M5-67: ein Eintrag mit ungeprüftem Link ist `link_hidden` und unsichtbar).
- **Belegstufen** wie in `adr/0026`: **M** gemessen in dieser Sitzung, **P** im Repo gelesen, **A** eigene Ableitung.
- **Unverändert:** Treffermenge und Trefferzahl jeder Anfrage; Bewertungs-Set (alle 52 Fragen mit denselben Rangpositionen, Deutsch 15/19, Englisch 41/42, MRR gleich).

## 1. Befund [P, M]

- **Kein Index für die Fläche:** Die Bedingung stand in einem `CASE` über die Art der Zeile und über eine Verbindung `earthx_dataset_search` ⟕ `earthx_listed_entry`. In dieser Form kann Postgres den GiST-Index nicht benutzen. Der Plan bei 10⁵ Zeilen [M, „Götterbaum“ mit Fläche Zürich]: erst der Volltext (42 656 Zeilen über den GIN-Index), dann je Zeile ein Zugriff auf `earthx_listed_entry` über den Schlüssel, erst danach `ST_Intersects` ohne Index; 1 758 Zeilen bleiben.
- **Kollation:** `earthx_listed_entry.dataset_id` ist `COLLATE "C"`, `earthx_dataset_search.dataset_id` nicht (hier `C.UTF-8`, in Ottos Postgres wohl `en_US.utf8`). Ein Vergleich beider Spalten läuft in `"C"`; der Primärschlüssel von `earthx_dataset_search` kann ihn nicht bedienen. Von den Footprints nach den Suchzeilen kam Postgres deshalb nur per Lesen der ganzen Tabelle (100 002 Zeilen), nicht per Index.
- **Der Planer kann hier nicht entscheiden:** Er schätzt die Treffer eines Texts immer auf 0,5 % der Zeilen, egal welche Wörter. Und seine Schätzung für `footprint && Fläche` lag in der Messung bei 1 Zeile statt 2 624, weil wenige große Footprints über jede kleine Fläche reichen. Ob er die Fläche zuerst nahm, war Zufall der Statistik; mit einer Fläche, die er zu klein schätzt, wäre ein seltenes Wort bei vielen Kandidaten von 6 ms auf Sekunden gefallen (Zwischenstand der Sitzung, ganze Schweiz: 1,6 s). Das zeigte sich auch beim Verbindungspool: psycopg bereitet eine Abfrage nach fünf gleichen Aufrufen vor, danach rechnet Postgres mit einem Plan ohne die Fläche.
- **Reihenfolge nicht stabil:** `sum(ts_rank_cd(...))` addiert `real`-Werte in der Reihenfolge, in der der Plan die Zeilen liefert. Dieselbe Anfrage gab mit Fläche andere Summen (`9.6` gegen `9.599999`) als ohne, und gleiche Summen entscheiden die Fusion.
- **Zusätzlich:** Die Klausel „Zahlen von Namen“ (`'{}'::text[] <@ ARRAY(SELECT … unnest …)`) stand bei jeder Anfrage in der Abfrage und wurde für jede Zeile ausgewertet, auch wenn die Liste leer und die Klausel damit immer wahr war (42 656 Auswertungen bei „Götterbaum“).

## 2. Umsetzung

1. **Migration 038:**
   - Spalte `geometry` in `earthx_dataset_search`, von Postgres berechnet (`GENERATED ALWAYS AS … STORED`): die Hülle der Box einer vollen Zeile, bei einer gelisteten Zeile leer. Kein Schreiber kann sie von der Box abweichen lassen; `write_search_index` und die Tests ändern sich dafür nicht.
   - GiST-Index darauf, teilweise für volle Zeilen: Er findet die wenigen vollen Zeilen, ohne die gelisteten zu lesen. Die Flächenbedingung einer vollen Zeile bleibt ein `CASE` (ein materialisierter Datensatz mit Items wird über seine Items getroffen, nicht über die Box), der Index bedient also nur das Auffinden, nicht die Fläche selbst.
   - Zweiter Schlüssel auf `dataset_id COLLATE "C"` (eindeutig), damit der Weg vom Footprint zur Suchzeile über einen Index läuft.
2. **Abfragen** (`catalog/search.py`):
   - Gelistete und volle Zeilen sind zwei flache Abfragen statt einer Verbindung mit `CASE`; die Treffer werden erst danach vereinigt. Mit einer Vereinigung unterhalb der Verbindung kann Postgres den Volltext nicht in die Zweige schieben (gemessen: Sequenzscan über alles).
   - Der Zustand `published` steht in der Abfrage jeder gelisteten Zeile, wie vorher: Ein Eintrag mit `link_hidden` (M5-67), `in_review` und alles andere ist nie Treffer, mit und ohne Fläche, mit und ohne Text.
   - **Start (`Start`):** Die Suche zählt und sagt Postgres, wo es anfangen soll, statt es raten zu lassen. Zwei Zählungen, jeweils nur bis zur Grenze:
     - Footprints, deren Box die Fläche trifft: höchstens `AREA_FIRST_MAX` = 5 000?
     - Treffer des Volltexts: mehr als `TEXT_FIRST_MAX` = 500?
     - Trifft beides zu, beginnt die Suche bei den Footprints (`Start.AREA`): GiST-Index, dann je Eintrag ein Zugriff über den Schlüssel `"C"`, erzwungen mit `LATERAL` und `OFFSET 0`. Sonst beginnt sie beim Text wie bisher (`Start.TEXT`); die Fläche prüft dort `NOT ST_Disjoint` auf den Treffern, damit Postgres sie nicht doch mit dem Index vorzieht. Ohne Fläche steht keine Bedingung auf einer Geometrie in der Abfrage.
   - Die Abfragen laufen mit `prepare=False`, damit jeder Plan die tatsächliche Fläche kennt.
   - Die Summe der Ränge läuft in fester Reihenfolge der Einheiten (`sum(… ORDER BY u.ord)`); die Reihenfolge ist damit unabhängig vom Plan.
   - Eine leere Liste „Zahlen von Namen“ (`named_numbers`, `numbers`, `codes`) gibt keine Klausel mehr.
3. **`search_datasets`** nimmt `area_first_max` und `text_first_max` als Schlüsselwörter, wie `threshold` und `joining` für das Bewertungs-Set; die Tests erzwingen damit beide Wege.

**Umfang:** etwa 260 geänderte Zeilen in `search.py` (ein Fünftel Docstrings), 20 Zeilen Migration (überwiegend Kommentar) und 175 Zeilen Tests; zusammen leicht über dem Richtwert von 400.

## 3. Messung bei 10⁵ gelisteten Einträgen [M]

Synthetische Einträge (`source_id = 'bench'`) in einer Kopie der Test-Datenbank (Postgres 16, PostGIS 3.4, ein Client, `shared_buffers` 128 MB), danach gelöscht; Skripte nur in der Sitzung.

- **Texte:** Titel aus 3, Beschreibung aus 30 von 60 deutschen Wörtern. Ein Wort steht in rund 40 % aller Einträge. „Götterbaum“ trifft 42 656 Einträge.
- **Footprints:** in der Schweiz; 70 % klein (0,01° bis 0,1°), 25 % mittel (bis 0,5°), 5 % groß (2° bis 4°); 2 % ohne Footprint; jeder zweite mit Zeitraum. Die großen Footprints liegen über jeder Fläche: schon 0,01° trifft 2 624 Boxen.
- **Flächen:** 0,01° (2 624 Kandidaten), Zürich 0,3° × 0,15° (4 047), Kanton 0,8° × 0,6° (11 364), die ganze Schweiz (98 010).
- **Messung:** `search_datasets`, je bester von 5 Läufen, alte und neue Fassung nacheinander auf derselben Datenbank; Zeiten in ms, „alt → neu“. Die Zahlen sind nicht mit der Tabelle in `m5-42` §3 vergleichbar (andere Daten: längere Texte, große Footprints).

| Anfrage | ohne Fläche | 0,01° | Zürich | Kanton | ganze Schweiz |
|---|---|---|---|---|---|
| Sentinel-2 | 3 Tr.: 7 → 8 | 3 Tr.: 6 → 15 | 3 Tr.: 6 → 17 | 3 Tr.: 6 → 15 | 3 Tr.: 5 → 12 |
| Landsat 9 | 1 Tr.: 16 → 19 | 1 Tr.: 17 → 30 | 1 Tr.: 16 → 29 | 1 Tr.: 17 → 26 | 1 Tr.: 18 → 22 |
| Götterbaum | 42 656 Tr.: 1 062 → 824 | 1 155 Tr.: 627 → 98 | 1 758 Tr.: 810 → 149 | 4 811 Tr.: 801 → 459 | 41 797 Tr.: 1 388 → 949 |
| Neophyten Kanton | 20 799 Tr.: 1 846 → 1 470 | 527 Tr.: 1 012 → 131 | 806 Tr.: 1 419 → 186 | 2 386 Tr.: 1 546 → 764 | 20 373 Tr.: 2 275 → 1 406 |
| Hochwasser Gefahren Karte | 8 243 Tr.: 2 870 → 1 796 | 221 Tr.: 955 → 155 | 335 Tr.: 2 094 → 199 | 961 Tr.: 2 005 → 1 025 | 8 083 Tr.: 3 283 → 2 146 |

Dazu ohne Text, nur mit Fläche (volle Zeilen): 0–1 ms vorher und nachher.

**Fläche in Schritten** („Götterbaum“, Mitte Zürich, Breite : Höhe = 3 : 2):

| Breite | Kandidaten | alt | neu | Start |
|---|---|---|---|---|
| 0,02° | 2 659 | 607 | 101 | Fläche |
| 0,2° | 3 620 | 660 | 124 | Fläche |
| 0,4° | 5 265 | 859 | 382 | Text |
| 1,0° | 13 463 | 858 | 395 | Text |
| 2,5° | 43 014 | 996 | 561 | Text |
| 4,5° | 94 826 | 1 287 | 859 | Text |

- **Lesart [A]:**
  - **Breite Wörter mit kleiner Fläche** (bis 5 000 Kandidaten) sind 6- bis 9-mal so schnell. Der Gewinn geht auf die Zeit, die der Volltext sonst mit 42 656 Zeilen verbringt.
  - **Über 5 000 Kandidaten** führt der Text wie bisher; der Gewinn von 1,3- bis 2-fach dort kommt aus der flachen Abfrage und der gestrichenen leeren Klausel, nicht aus der Fläche.
  - **Seltene Wörter** kosten mit Fläche etwa 10 ms mehr (die zwei Zählungen); ohne Fläche ändert sich nichts. Ohne die Zählung des Texts, also mit der Fläche immer zuerst, waren es bis zu 100 ms mehr (Zwischenstand der Sitzung, Sentinel-2 mit Zürich 102 ms).
  - **Was bleibt:** Das Ranken vieler Treffer. Eine Anfrage mit 42 656 Treffern kostet auch ohne Fläche 0,8 s. Das ist M5-66 (nur die besten 1 000 je Arm ranken).
- **Migration 038:** 5 s bei 10⁵ Zeilen (neu schreiben der Tabelle für die Spalte, einmalig, im Lauf von `catalog-load`); Tabelle und Indizes 233 → 237 MB, der neue Schlüssel allein 3,1 MB. Ein `catalog-load` ohne Änderung mit 10⁵ gelisteten Einträgen: 8,2 s, wie vorher (die Spalte ändert nichts am Hash der Eingaben).

## 4. Auslegungen und Abweichungen

- **A1 — Zählung statt Planer:** siehe §1 und §2. Die zwei Grenzen sind meine Wahl: 5 000 Kandidaten (5 % bei 10⁵) sind höchstens etwa 125 ms bei seltenem Wort, 500 Treffer höchstens etwa 15 ms. Beide stehen als Konstanten in `search.py` und sind Schlüsselwörter von `search_datasets`; nach der Messung mit echten Footprints ist eine andere Grenze eine Zeile.
- **A2 — Reihenfolge bei Gleichständen (Abweichung von „Reihenfolge bleibt gleich“):**
  - Ohne Fläche sind alle 5 gemessenen Anfragen in Menge und Reihenfolge gleich wie vorher; das gilt auch für das Bewertungs-Set (Deutsch 15/19, Englisch 41/42, alle 52 Fragen mit denselben Rangpositionen).
  - Mit Fläche sind Menge und Zahl der Treffer gleich, die Reihenfolge ist es in 25 von 29 Messfällen. Die vier Abweichungen betreffen nur „Hochwasser Gefahren Karte“ (drei Einheiten); dort stand die Reihenfolge von Treffern mit fast gleichem Rang bisher nur durch die Rundung der `real`-Summe fest, und die hing vom Plan ab (ohne Fläche anders als mit). Die Summe wird jetzt für jeden Plan in derselben Reihenfolge gebildet, wie ohne Fläche.
  - Die alte Reihenfolge ist nicht nachbaubar, weil sie vom Plan abhing.
- **A3 — `prepare=False`:** Die Anfragen der Suche sind selten genug, dass die Kosten des Planens (2 bis 6 ms) vor dem Gewinn verschwinden; ein Verbindungspool käme sonst nach fünf Anfragen in den Plan ohne Fläche (§1).
- **A4 — Kein neuer Index auf `earthx_listed_entry`:** Der vorhandene GiST-Index (Migration 021, `WHERE state = 'published'`) genügt; die Bedingung `e.state = 'published'` steht in der Abfrage, damit er passt.
- **A5 — Kein ADR:** Es ist eine Abfrageänderung unter `adr/0026` §4; die Auslegungen stehen hier und im Entscheidungslog.

## 5. Tests

- `test_search.py`, neue Fälle:
  - **Zustand:** Ein Eintrag, dessen Link seit dem letzten Lauf von `catalog-load` durchgefallen ist (`link_hidden`), ist mit und ohne Fläche, mit und ohne Text und mit beiden Starts kein Treffer.
  - **Fehlerfall:** Eine Fläche, die keine Geometrie ist, ist ein Fehler.
  - **Spalte:** `geometry` ist die Hülle der Box einer vollen Zeile und folgt ihr, bei einer gelisteten Zeile leer.
  - **Start:** Die Wahl des Starts bei vielen und bei wenigen Treffern, bei kleiner und bei großer Fläche, ohne Fläche und bei einer Anfrage aus Stoppwörtern; der Plan beginnt mit dem Footprint-Index und dem Schlüssel `"C"`.
  - **Gleichheit:** Beide Starts finden und ordnen gleich (60 × 60 Raster aus 3 600 gelisteten Einträgen und die Einträge der Suche), auch mit einem Zeitraum und seinem Hinweis `ignored_filters`; die Abfrage enthält ohne Fläche keine Bedingung auf einer Geometrie, und die Rangsumme steht mit `ORDER BY u.ord` in der Abfrage.
- `test_migrations.py`: Die Liste der Migrationen kennt `038`.
- **Vorhandene Tests der betroffenen Module** (Suche, Index, Route, Katalogzustand, Bewertungs-Set, Linkprüfung, Laden): 3 089 bestanden.

## 6. Fragen an Otto

**F1 — Reihenfolge bei Gleichständen (A2).** Die Reihenfolge mit Fläche ändert sich bei Treffern mit fast gleichem Rang.

1. So lassen: Die Reihenfolge hängt nicht mehr vom Plan ab **(Empfehlung)**
2. Die Summe wieder ohne feste Reihenfolge; dann bleibt sie ohne Fläche gleich, mit Fläche hängt sie vom Plan ab

**F2 — Grenzen (A1).**

1. 5 000 Kandidaten und 500 Treffer so lassen, nach der Messung mit Ottos echten Footprints neu prüfen **(Empfehlung)**
2. Ich messe sie vorher an einem Auszug von Ottos Daten (nur wenn Otto die Footprint-Verteilung zeigt)

## 7. Nicht in diesem PR

- **M5-66:** Ranken nur der besten 1 000 je Arm, Kategorie und Region in der Abfrage, `catalog-load` messen und kürzen. Die Zeit der Anfragen mit vielen Treffern liegt dort.
- **Nachfolge möglich, wenn die zwei Zählungen stören:** die Hülle der Footprint-Box auch für gelistete Zeilen in `earthx_dataset_search` (mit GiST-Index), dann könnte Postgres Text und Fläche in einem Bitmap-Durchlauf verbinden, ohne zu zählen. Das widerspricht dem Auftrag („Index von `earthx_listed_entry.footprint`“) und kostet eine zweite Geometrie je Zeile; deshalb nicht ohne Ottos Wort.
