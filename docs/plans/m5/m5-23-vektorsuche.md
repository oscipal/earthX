# M5-23 — Suche Teil 2: Vektorarm, Modellwahl, alle Arme gleichzeitig

- **Auftrag:** Otto, 27.11.2026, Stufe B (`plans/m5/m5-discovery-und-suche.md` §6.2, Zeile M5-23).
- **Status:** F1–F8 von Otto am 27.11.2026 beantwortet, alle = 1 (§10a). Umgesetzt wie empfohlen.
- **Grundlage:** `adr/0026` §4.3, §4.4, §6 Schritte 3 und 4, §8, §14, §15; `plans/m5/m5-41-pgvector.md` §6, §8, §9; `plans/m5/m5-42-suche-gelistete.md` §4, F6; `plans/m5/m5-66-breite-suche.md` §2a, F4, F8; `plans/m5/m5-43-postgres-pgvector.md` (pgvector 0.8.7 in Compose, CI und Cloud-Umgebung); Entscheidungslog bis 27.11.2026.
- **Belegstufen** wie in `adr/0026`: **M** in dieser Sitzung gemessen, **P** im Repo oder an der Primärquelle selbst gelesen, **P\*** Primärquelle über einen Hilfsagenten gelesen, **S** nur Suchtreffer, **A** eigene Ableitung.
- **Zwei Draft-PRs:** PR 1 (`claude/upbeat-brown-zzfsrn`) dieser Plan und der Vektorarm (§4); PR 2 (`claude/upbeat-brown-zzfsrn-broad`, baut auf PR 1 auf) breite Wörter, Glossar im Volltext, Klassennamen, neue Fragen des Sets und das Messskript (§5, §6, §9). Die Schwelle des Trigramm-Arms bleibt (§6a).
- **Netz der Sitzung:** `huggingface.co` war gesperrt. Für die Modellwahl hat Otto in der Sitzung sechs Hosts von Hugging Face in der Umgebung „earthX“ freigegeben (Frage F8). Echte Datenquellen wurden nicht abgerufen.

## 1. Kurzfassung

1. **Heute** (lexikalisch, `main` vom 27.11.) [M]: Deutsch Recall@5 0,789, MRR@10 0,763; Englisch 0,976 / 0,964; Filterfragen 5/5, Negativfragen 4/5. Auf Deutsch fehlen Q16 „Satellitenbilder in Echtfarben“, Q18 „Radarbilder bei Bewölkung“, Q38 „Schneebedeckung“, Q39 „Wasserflächen erkennen“. (Der Auftrag nennt 0,727; das war der Stand nach M5-22c, vor M5-42.)
2. **Modell:** `ibm-granite/granite-embedding-97m-multilingual-r2` (Apache-2.0, 97 Mio. Parameter, 384 Dimensionen), ONNX in fp32 (390 MB, im Prozess `api` rund 690 MB). Unter sieben Kandidaten ist es das einzige, mit dem das Set F5 besteht: Deutsch 0,947 / 0,868, Englisch 1,0 / 0,929, Negativfragen 4/5, Filterfragen 5/5 [M, §3.2; gleich im Test der CI, §4.6]. Die int8-Fassungen desselben Modells verlieren (Deutsch 0,895) [M].
3. **Was eingebettet wird:** die Teile A und B des Suchtexts (Kennung, Titel, Titel der Dubletten, Schlagworte, Ortsnamen, Kategorie), ohne Beschreibung. Mit Beschreibung besteht kein Modell [M].
4. **Mindestähnlichkeit relativ zur Anfrage:** Ein Treffer zählt im Vektorarm, wenn sein Kosinus mindestens 2,7 Standardabweichungen über dem mittleren Kosinus derselben Anfrage zu 46 festen Hintergrundtexten liegt. Eine feste Kosinusschwelle besteht mit keinem Modell, weil Negativfragen und gesuchte Treffer im selben Bereich liegen [M, §3.3].
5. **Index und Weg** wie `adr/0026` §14: Spalte `halfvec(384)`, HNSW, gefiltert exakt bis 5·10⁴ Zeilen. Tiefe wie die lexikalischen Arme (§15).
6. **Gleichzeitig:** Die Anfrage wird eingebettet, während der Volltext läuft; Volltext und Vektorarm laufen auf zwei Verbindungen gleichzeitig; der Trigramm-Arm danach nur unter 20 Volltext-Treffern (§4.5).
7. **Einbetten** nur, was neu ist oder sich geändert hat, in Stapeln mit eigener Transaktion nach dem Hauptlauf von `catalog-load` (M5-42 §4, F6).
8. **Dauer bei Otto:** ~102 000 gelistete Einträge einmal einbetten: in der Sitzung gemessen **26,6 Minuten** auf 4 vCPU (64 Texte/s mit Index und Schreiben, Spitze 0,94 GB im Prozess); auf Ottos Rechner je nach Kernen etwa **15 bis 55 Minuten** (§7). Ein Lauf ohne Änderung bettet nichts ein (0,2 s).
9. **Breite Wörter bei 10⁵** (PR 2, §5a): alle unter 1 s ohne Filter, auch „Karte“ (0,87 s) und „Gewässer“ (2,96 s auf `main`, jetzt 0,83 s), ohne Änderung der ersten Seite. Langsam bleiben Tippfehler ohne Volltext-Treffer („watr“ 1,36 s), wie auf `main`.
10. **Schwelle 20 des Trigramm-Arms** bleibt (§6a); **vier neue Fragen** mit breiten Wörtern; damit sie bestehen, kommen Klassennamen in den Suchtext und eine Glossargruppe [Karte, map] (§9a, Frage F6).

## 2. Stand der Technik

Recherche eines Hilfsagenten am 27.11.2026; Hugging Face und arXiv waren für ihn gesperrt, Modellkarten deshalb nur Suchtreffer, Metadaten und Messwerte aus dem Repository von MTEB (P\*). Was `adr/0026` §3 und `plans/m5/m5-41-pgvector.md` §3 schon belegen (RRF, pgvector 0.8.7, HNSW, iterative Scans, `halfvec` bei 10⁶ synthetisch), steht hier nicht noch einmal.

### 2.1 Modelle bis zur Größe von e5-base (F2 b)

| Modell | Param. | Dim. | Lizenz | Präfix, Pooling | MIRACL-de nDCG@10 | ONNX im Repo (Datei, Größe) [M] |
|---|---|---|---|---|---|---|
| multilingual-e5-small | 118 M | 384 | MIT | `query: `/`passage: `, Mittel | 48,75 | `onnx/model_qint8_avx512_vnni.onnx`, 118 MB |
| multilingual-e5-base | 278 M | 768 | MIT | wie oben | 52,05 | dasselbe, 279 MB |
| granite-embedding-107m-multilingual | 107 M | 384 | Apache-2.0 | keines, CLS | 45,14 | `model.onnx` fp32, 428 MB |
| **granite-embedding-97m-multilingual-r2** (29.04.2026) | 97 M | 384 | Apache-2.0 | keines, CLS [P, `1_Pooling/config.json`] | — | `onnx/model.onnx` fp32 390 MB, `onnx/model_quint8_avx2.onnx` 98 MB |
| jina-embeddings-v2-base-de | 161 M | 768 | Apache-2.0 | keines, Mittel | — | `onnx/model_quantized.onnx`, 162 MB |
| paraphrase-multilingual-MiniLM-L12-v2 (Vergleich) | 118 M | 384 | Apache-2.0 | keines, Mittel | 22,43 | `onnx/model_qint8_avx512_vnni.onnx`, 118 MB |

- MIRACL-Werte: Teilmenge `de`, dev, mteb 1.18.0, aus `embeddings-benchmark/results` [P\*]; e5 und granite haben MIRACL im Training, die Werte sind nicht neutral [P\*].
- granite-97m-r2: laut README von IBM 59,6 im mehrsprachigen Retrieval von MTEB gegen 50,9 (e5-small) und 52,7 (e5-base), eine Selbstangabe [P\*]; 52 Sprachen mit Retrieval-Training, darunter Deutsch [P, Modellkarte in der Sitzung gelesen].
- Neuere Modelle außerhalb der Vorgabe: microsoft/harrier-oss-v1-270m (MIT, Decoder, kein ONNX gefunden) [P\*/S], jina-embeddings-v5-text-nano (CC-BY-NC-4.0, ausgeschlossen) [S], gte-multilingual-base und EmbeddingGemma-300m über 278 M [P\*].
- **Kurze Suchwörter** wie hier misst keiner der Benchmarks; GermanQuAD (Frage gegen Absatz) liegt für alle über 90 [P\*]. Die Wahl trifft deshalb das Set (§3).

### 2.2 Quantisierung

- **int8 (dynamisch, ONNX Runtime):** sentence-transformers nennt „roughly equivalent speedups“ ohne Zahlen im Text [P\*]. Eine Gemeinschaftsmessung findet für e5-small Spuren um höchstens 0,12 bewegt, für granite-97m-r2 unter 8 Bit aber Einbrüche bis 0,00–0,25 [P\*, GitHub-Issue]. Eine MTEB-Messung int8 gegen fp32 für e5 wurde nicht gefunden.
- **Hier gemessen [M]:** granite-97m-r2 fp32 besteht das Set, die Fassung `quint8_avx2` aus dem Repo und eine in der Sitzung gerechnete `qint8` nicht (Deutsch 0,895 / 0,781 bzw. 0,895 / 0,842). e5-small int8 und fp32 liegen gleich. int8 ist also je Modell zu prüfen; für das gewählte Modell bleibt fp32 (Frage F1).
- **`halfvec`:** Recall@10 0,974 / 0,970 gegen 0,984 / 0,971 mit `vector` bei 76 000 bzw. 197 000 Vektoren (1 024 Dim., `ef_search` 40) [P\*, Gemeinschaftsmessung]; bei uns bei 10⁶ synthetisch gleich (M5-41 §4.3).
- **Binär:** ohne Neusortierung 0,955 / 0,939, mit Neusortierung von 160 Kandidaten 0,993 [P\*]; bei 384 Dimensionen in M5-41 zu schwach. Nicht nötig.

### 2.3 Index (pgvector)

- 0.8.1 bis 0.8.7 ändern an `ef_search`, `iterative_scan` und `max_scan_tuples` nichts; 0.8.2 behebt einen Pufferüberlauf beim parallelen HNSW-Bau, 0.8.3/0.8.4 Fehler beim Vacuum [P\*, CHANGELOG `v0.8.7`].
- **Grenze:** `hnsw.ef_search` geht höchstens bis 1 000 [P\*, `src/hnsw.h`]. Die Tiefe eines Arms wächst mit der Seite über 1 000 hinaus (M5-66 F2 = 2); dort liefert der iterative Scan (`relaxed_order`) die Zeilen über `ef_search` hinaus (M5-41 §4.3).
- Der Filter auf den Abstand gehört außerhalb der `MATERIALIZED`-CTE (README, schon in M5-41 §3.1).

### 2.4 Mindestähnlichkeit und Gewichte in der Fusion

- e5 sagt selbst, dass seine Kosinuswerte eng beieinander liegen (Temperatur 0,01) und nur die Reihenfolge zählt [S, Modellkarte]. Eine feste Schwelle trennt fachfremde Anfragen deshalb schlecht; empfohlen wird Kalibrieren an Daten [S].
- Elasticsearch hat am kNN-Retriever eine Mindestähnlichkeit (`similarity`) [P\*]; ein Verfahren, die Schwelle je Modell für Kurzanfragen festzulegen, ist nirgends dokumentiert [P\*/S]. Die Normierung je Anfrage an festen Hintergrundtexten (§3.3) ist eigene Ableitung [A].
- Gewichte je Arm in der RRF bieten Elasticsearch (`weight`), OpenSearch und Qdrant an [P\*]. Hier nicht nötig: das Set besteht mit Gewicht 1.

## 3. Modellwahl am Bewertungs-Set [M]

### 3.1 Aufbau

- Katalog wie im Test des Sets: die 9 vollen Einträge und die 2 Handeinträge, geladen mit `catalog-load` in eine leere Datenbank. 52 Fragen, davon 51 aktiv.
- Lexikalische Arme unverändert (Volltext, Trigramme, Schwelle 20); Vektorarm mit denselben harten Filtern (Fläche, Zeit). RRF mit k = 60 über alle drei.
- Je Modell zwei bis fünf Texte zum Einbetten: Teile A und B, A–C, A–D, A+B+D (§4.1 von `adr/0026`). Präfixe und Pooling wie in der Modellkarte. ONNX Runtime 1.32, Tokenizer `tokenizers` 0.23, auf der CPU der Sitzung (4 vCPU Xeon 2,1 GHz mit AVX-512).
- **Bestanden** heißt F5: Recall@5 ≥ 0,9 und MRR@10 ≥ 0,8 je Sprache, alle Filterfragen, höchstens eine Negativfrage mit Treffer (A9 aus M5-22).
- Skripte nur in der Sitzung, nicht im Repo.

### 3.2 Ergebnis

Bester Wert je Modell, bei dem Filter- und Negativfragen bestehen; die Schwelle ist die relative aus §3.3, jeweils am Set gewählt:

| Modell | Text | Deutsch R@5 / MRR | Englisch R@5 / MRR | besteht F5 | Datei | Texte/s (4 vCPU) |
|---|---|---|---|---|---|---|
| heute, nur lexikalisch | — | 0,789 / 0,763 | 0,976 / 0,964 | nein | — | — |
| e5-small int8 | alle | 0,789 / 0,763 | 0,976 / 0,964 | nein | 118 MB | 288 |
| e5-base int8 | alle | 0,789 / 0,763 | 0,976 / 0,964 | nein | 279 MB | — |
| granite-107m int8 | A–C | 0,842 / 0,781 | 0,976 / 0,964 | nein | ~110 MB | — |
| jina-v2-base-de int8 | A+B+D | 0,842 / 0,800 | 0,976 / 0,946 | nein | 162 MB | — |
| MiniLM-L12 int8 | A–C | 0,895 / 0,842 | 0,976 / 0,964 | nein (knapp) | 118 MB | — |
| granite-97m-r2 int8 | A+B | 0,895 / 0,842 | 1,0 / 0,964 | nein | 98 MB | — |
| **granite-97m-r2 fp32** | **A+B** | **0,947 / 0,868** | **1,0 / 0,929** | **ja** (Schwelle 2,5–2,8) | 390 MB | 77 |

- **Ohne Mindestähnlichkeit** erreicht jedes Modell Deutsch Recall@5 1,0: Der Vektorarm liefert dann jeden der 11 Einträge, und die gesuchten stehen unter den ersten fünf. Dafür hat jede Negativfrage Treffer. Der Engpass sind die Negativfragen, nicht der Rang.
- **Bei e5** liegen die Kosinuswerte der Negativfragen (0,80–0,84) über denen mancher gesuchten Treffer (Q34 „Hangneigung berechnen“ 0,79–0,80) [M]. Mit e5 bringt der Vektorarm am Set deshalb nichts.
- **Mit granite-97m-r2 fp32** findet der Vektorarm Q16 und Q18 unter den ersten fünf; in der Umsetzung (§4.6, CI-Form mit Fixture) auch Q39 auf Platz 1, nur Q38 „Schneebedeckung“ fehlt noch. Die eine Negativfrage mit Treffer ist Q48 „ocean salinity“ (zwei Treffer; einer davon kam schon vom Trigramm-Arm).
- **Q51 „Sentinel-3“:** Jedes Modell legt es neben Sentinel-2. Der Vektorarm hält deshalb dieselbe Regel für Zahlen in Namen wie der Volltext (§4.4); damit bleibt die Liste leer.
- **Grenzen [A]:** 19 deutsche Fragen; ein Wechsel einer Frage verschiebt Recall@5 um 0,05. Das Fenster der Schwelle ist schmal (2,5–2,8). Die Wahl ist eine am Set, keine allgemeine Aussage über die Modelle.

### 3.3 Mindestähnlichkeit relativ zur Anfrage

- **Absolut** (Kosinus ≥ s) besteht mit keinem Modell: Für granite-97m-r2 fp32 kostet jede Schwelle, die vier Negativfragen leert (ab 0,82), Deutsch unter 0,9 [M].
- **Relativ:** Für jede Anfrage q werden μ(q) und σ(q) der Kosinuswerte zu 46 festen Hintergrundtexten gerechnet (23 deutsch, 23 englisch, kurze Titel wie „Abfallkalender und Wertstoffhöfe“, „road noise map“, ohne Bezug zu Fernerkundung). Ein Treffer zählt, wenn `(cos − μ(q)) / σ(q) ≥ 2,7`. Das gleicht aus, dass manche Anfragen zu allem ähnlich sind.
- **Gemessen [M]:** besteht bei 2,5–2,8 mit allen 46 Texten, bei 2,7–2,9 nur mit den deutschen, bei 2,6–2,8 nur mit den englischen, mit der ersten Hälfte der Liste nicht (dann 3 von 5 Negativfragen). Gewählt 2,7.
- **Bekanntes Risiko (Otto, 27.11.2026):** Das Fenster ist schmal (2,5–2,8). Es hängt an wenigen Fragen: Bei 19 deutschen Fragen verschiebt eine Frage Recall@5 um 0,05, und welche Negativfrage Treffer hat, entscheidet ein Abstand von wenigen Zehnteln. Eine andere Liste von Hintergrundtexten verschiebt das Fenster. **Neu geprüft wird es, sobald das Set wächst** (neue Fragen, neue Datensätze mit Note 2) oder das Modell, die Hintergrundtexte oder der eingebettete Text sich ändern: dieselbe Abtastung von z in Schritten von 0,1 wie hier, Ergebnis im PR der Änderung. Liegt 2,7 dann nicht mehr im Fenster, wird nachgestellt; verschwindet das Fenster, ist die Mindestähnlichkeit neu zu entscheiden.
- Die Hintergrundtexte liegen als YAML in `catalog` (`backend/catalog/search_background.yaml`), ihre Vektoren rechnet `api` beim Start (46 Texte; Start mit Modell 2,3 s [M]). Kein Text aus Nutzeranfragen.

## 4. Umsetzung (PR 1)

### 4.1 Datenbank (Migration 039)

- `CREATE EXTENSION IF NOT EXISTS vector` (pgvector 0.8.7 aus M5-43; die Erweiterung ist nicht „trusted“, die Migration läuft wie alle als Eigentümer der Datenbank, in Compose und CI Superuser).
- Spalten in `earthx_dataset_search`: `embedding halfvec(384)`, `embedding_model text`, beide leer oder beide gesetzt (CHECK). HNSW `halfvec_cosine_ops` mit `m` 16, `ef_construction` 64 (`adr/0026` §14 Punkt 1).
- Ein neuer oder geänderter Text (`text_hash`) setzt das Embedding seiner Zeile auf leer (im Upsert); Box oder Zeitraum allein nicht, außer bei gelisteten Zeilen, deren `text_hash` die Eingaben insgesamt zählt (M5-42 §2 Punkt 3).

### 4.2 Modell im Image (`backend/Dockerfile`)

- Neue Stufe `model-files` auf demselben Basis-Image wie `app`: lädt `onnx/model.onnx` und `tokenizer.json` von Hugging Face an der festen Revision `835ad14087e140460703cf0fae09f97d469d65c2` und prüft je Datei den SHA-256 (Python `urllib`, kein zusätzliches Paket). Bricht bei Abweichung ab.
- Neue Stufe `search` = `app` + die Modelldateien unter `/app/models/` + `EARTHX_EMBEDDING_MODEL`. Die Dienste `api` und `catalog-load` bauen `target: search`; alle anderen, auch `runner`, bleiben auf `app` ohne Modell (`adr/0026` F2 a). Test: der Runner baut auf `app`, keine Stufe außer `search` kopiert aus `model-files`.
- Zur Laufzeit kein Netz: `tokenizers` liest nur `Tokenizer.from_file`. `tokenizers` bringt `huggingface_hub` als Abhängigkeit mit; es steht deshalb auf der Verbotsliste von `http-only-in-gateway`, ein Test verbietet `from_pretrained`, und das Image setzt `HF_HUB_OFFLINE=1`.
- Neue Abhängigkeiten in `requirements.txt` und Lock: `onnxruntime`, `tokenizers` (MIT bzw. Apache-2.0). Hinweis zu Dritten für das Modell (Apache-2.0).
- **Speicher je Prozess `api`** [M]: das geladene Modell mit Tokenizer kostet rund **690 MB** RSS (ohne Modell 87 MB für die Imports der Suche); `enable_cpu_mem_arena` und `enable_mem_pattern` ändern daran nichts (662 MB je Sitzung von ONNX Runtime). Zum Vergleich wären es mit MiniLM-L12 int8 (118 MB Datei) deutlich weniger, dafür besteht das Set nicht (F1).
- **Wie oft das Modell lokal geladen wird [P]:** Compose startet einen Container `api` mit einem Prozess (`uvicorn` ohne `--workers`, keine Replikate). Dieser Prozess lädt das Modell einmal beim Start (`load_query_vectors` im Lifespan) und nutzt dieselbe Sitzung von ONNX Runtime für alle Anfragen, je Anfrage in einem Thread mit einem Faden. Dazu lädt `catalog-load` es während seines Laufs (einmaliger Container, bis 0,94 GB). `tiler`, `worker`, `harvester` und der Runner bauen `target: app` und haben kein Modell. Ein Umbau ist lokal nicht nötig.
- **Vermerk für M6 (mehrere Instanzen):** Jede Instanz `api` lädt das Modell selbst, also rund 0,7 GB RAM je Instanz; mit `--workers n` in einem Container n-mal, weil jeder Prozess eine eigene Sitzung hat. Wege, wenn das zu teuer wird: (a) Instanzen mit einem Prozess und mehr Instanzen statt Worker; (b) ein eigener kleiner Dienst nur fürs Einbetten der Anfrage (ein Modell für alle `api`, eine Anfrage ~15 ms, Aufruf intern ohne `gateway`, da Plattformdienst; braucht eine Entscheidung zur Modulgrenze und zum Ausfallverhalten); (c) ein kleineres Modell, wenn das Set es trägt. `catalog-load` bleibt einmalig. Zu entscheiden mit der Planung von M6.

### 4.2a Bauzeit mit dem Modell [M]

- **CI, Job `compose-topology`, Schritt „Build images“** (`docker compose build`, alle Dienste): auf `main` 69 s (Lauf 2166), mit der Stufe `model-files` 86 s (Lauf 2170, PR 1); der ganze Job 2:23 gegen 2:46 min. Der Job hat keinen Cache über Läufe hinweg; jeder Lauf baut die Stufe kalt und lädt das Modell (415 MB) neu. Innerhalb des Laufs nutzt der folgende Bau des Runners die Schichten (1–2 s wie auf `main`). Die vier Test-Teile bauen nur das Postgres-Image und sind nicht betroffen.
- **Mit Cache** gibt es in der CI also heute nicht. Gemessen in der Sitzung, nur die Stufe `model-files`: kalt 47 s, aus dem Cache 0,3 s. Ein Cache vom Typ `gha` für `compose-topology` (wie bei Postgres in M5-43) hieße eine Änderung an `.github/workflows/ci.yml`; nicht in diesem PR, nur mit Erlaubnis.
- **Bei Otto:** Der erste `docker compose build` lädt das Modell einmal; danach liegt die Stufe im lokalen Cache und kostet nichts, solange Revision und Prüfsummen gleich bleiben.

### 4.3 Einbetten in `catalog-load`

- Nach dem Commit des Hauptlaufs, je Stapel von 256 Zeilen eine Transaktion (M5-42 F6 = 1): Zeilen ohne Embedding oder mit anderem `embedding_model`, nach Kennung; geschrieben nur, wenn `text_hash` sich seit dem Lesen nicht geändert hat.
- Ein Lauf ohne Änderung bettet nichts ein und kostet eine Abfrage. Ein Abbruch lässt Zeilen ohne Vektor; der nächste Lauf holt sie nach, der Vektorarm überspringt sie bis dahin.
- Ausgabe: Zahl je 10 000 und am Ende Zeilen, Sekunden, Texte je Sekunde; Zeitzeile `time embeddings`. Keine Kennungen, keine Texte.
- Ohne Modell (Entwicklung ohne die Stufe `search`, Tests) entfällt der Schritt mit einer Zeile in der Ausgabe.

### 4.4 Vektorarm in der Suche (`catalog/search.py`)

- `api` bettet die Anfrage ein (ein Faden je Anfrage, ~15 ms [M]) und gibt den Vektor an `search_datasets`.
- Dieselben Quellen und harten Filter wie die lexikalischen Arme (`_sources`, `Kept`, Zeit, Fläche), dazu die Regel für Zahlen in Namen (Auslegung A6): Mit „Sentinel 3“ kommen nur Zeilen in Frage, die das Wort „sentinel“ (über den Trigramm-Index, `LIKE`) und die Zahl 3 tragen. Ohne das Namenswort lieferte der Vektorarm für „Sentinel-2“ bei 10⁵ jede Zeile mit einer 2 im Titel („… Nr. 2“), und der iterative Scan suchte dafür 0,6 s [M].
- **Wege (§14 Punkt 2):** Volle Zeilen sind wenige und werden immer exakt verglichen. Gelistete Zeilen ohne jeden harten Filter gehen gleich zum HNSW-Index; das Zählen vorab kostete bei 10⁵ 0,11 s [M]. Mit Filter wird gezählt, bis T + 1 (T = 5·10⁴, Konfiguration): bis T exakt, darüber HNSW mit `hnsw.iterative_scan = relaxed_order` und `hnsw.ef_search = min(1 000, max(200, Tiefe))` in einer `MATERIALIZED`-CTE. Die HNSW-Abfrage mit Tiefe 1 000 kostet bei 10⁵ 14 ms [M].
- **Mindestähnlichkeit** (§3.3) als Grenze des Abstands außerhalb der CTE.
- **Tiefe** wie die anderen Arme (`DEPTH`, wächst mit der Seite), Gleichstand ganz.
- **Trefferzahl:** Der Vektorarm zählt seine Treffer exakt, solange er sie alle liefert; ist er im Index-Weg an der Tiefe voll, ist seine Zahl unbekannt und `numberMatched` fehlt (Frage F4). **Gemessen bei 10⁵ [M]:** Ohne Filter liegen für fast jede Anfrage mehr als 1 000 Einträge über der Mindestähnlichkeit („Sentinel-2“: alle 1 000 nächsten); `numberMatched` fehlt dann bei Text fast immer, mit Filter (exakter Weg) bleibt es („map + Region DE-RP“ 2 276).
- **Startprüfung:** Ist ein Modell gesetzt, braucht jede volle Zeile ein Embedding dieses Modells, sonst startet `api` nicht (wie `check_search_index`); gelistete dürfen fehlen (F6 von M5-42).

### 4.5 Alle Arme gleichzeitig (M5-66 F4)

- Einbetten der Anfrage in einem Faden, während der Volltext auf seiner Verbindung läuft; der Vektorarm auf einer zweiten Verbindung aus einer eigenen kleinen Menge (`earthx_vector_pool`), sobald der Vektor da ist.
- Eine eigene Menge, damit nie eine Anfrage eine Verbindung hält und auf eine zweite derselben Menge wartet: Unter Last würden sonst alle Anfragen gegenseitig warten (Auslegung A3).
- Der Trigramm-Arm läuft danach, nur wenn der Volltext unter 20 Treffer hat (M5-66 §2a); er ist dann schnell.
- Folge: Die Arme sehen nicht mehr denselben Schnappschuss. Ein `catalog-load`, der genau zwischen zwei Armen festschreibt, kann einen Treffer in einem Arm fehlen lassen; die nächste Anfrage sieht wieder alles gleich [A].

### 4.6 Bewertungs-Set in der CI (`adr/0026` §8.4)

- Fixture `backend/tests/fixtures/search/embeddings.json`: Modell, Revision, Dimension, die Vektoren aller Fragen, der Hintergrundtexte und der eingebetteten Texte des Katalogs, je mit SHA-256 des Textes. Die CI rechnet nichts mit dem Modell.
- Der Test schreibt die Vektoren aus der Fixture in die Spalte und stellt jede Frage über `search_datasets` mit Vektorarm. Weicht ein Text vom Prüfwert ab, scheitert er mit dem Hinweis auf das Skript zum Neurechnen.
- Grenze ab M5-23: F5 bindet (Recall@5 ≥ 0,9 und MRR@10 ≥ 0,8 je Sprache, alle Filterfragen, höchstens eine Negativfrage mit Treffer); die Ratsche der lexikalischen Arme bleibt für den Test ohne Vektorarm.
- Skript zum Neurechnen: `scripts/m5-23-embeddings.py`, läuft im Image `search` gegen eine Datenbank nach `catalog-load` (Befehl im Kopf des Skripts). Die Fixture hat 106 Vektoren (110 mit PR 2), 225 KB.

## 5. Breite Wörter und Glossar im Volltext (PR 2)

- **Ziel** (M5-66 F1, M5-23): ein breites Wort ohne Filter unter 1 s bei 10⁵, auch „Karte“ (1,26 s nach M5-66 PR 1) und die Glossargruppe „Gewässer“ (1,7 s, M5-66 F8).
- **Synthetischer Bestand** wie M5-66 §5 [M]: 102 311 veröffentlichte gelistete Einträge (govdata 94 258, opendata-swiss 7 748, fsdi-stac 305) und die 2 Handeinträge; Kategorien `boundaries` 40 %, `infrastructure` 14 %, `water` 11 %, `nature` 10 %; Titel aus Arten wie „Bebauungsplan“, „Pegel“, „Topographische Karte“ mit Orten, opendata-swiss teils französisch und italienisch; Beschreibung log-normal (Median 260 bzw. 420 Zeichen); 1–6 Schlagworte aus einer Liste mit „opendata“, „map“, „water“, „Gewässer“, „Karte“. „Gewässer“ trifft damit 57 452 Einträge, „data“ fast alle: der ungünstige Fall. Postgres 16 mit pgvector 0.8.7, `shared_buffers` 512 MB, `work_mem` 16 MB wie in Compose (M5-43), 4 vCPU. Skripte nur in der Sitzung.

### 5a. Ergebnis [M]

**Ursache bei „Gewässer“:** Gefunden sind die 57 452 Treffer in 0,12 s. Der Rest ist `ts_rank_cd` mit der Anfrage der Glossargruppe: 5 Begriffe in 3 Konfigurationen sind 15 Glieder, 4 davon Phrasen („water bodies“, „permanent water bodies“). `ts_rank_cd` zahlt je Zeile für jedes Glied, für eine Phrase am meisten, auch wenn die Zeile sie nicht hat: 2,47 s mit allen 15, 0,19 s mit einem; die Phrasen allein 0,92 s, obwohl keine Zeile sie hat.

**Umsetzung** (`search.py`, `_unit_query`, `_UNITS`, `_rank`), Treffer und Ränge unverändert:
1. Jedes Glied einer Einheit steht nur einmal in ihrer Anfrage (`gewass` aus `german` und `english` gleich) und nur, wenn eine Zeile des Index es hat (vorher geprüft, 69 ms für 15 Glieder). Hat keine Zeile ein Glied, ist die Einheit unbekannt (`known` ist jetzt „Anfrage nicht leer“, die eigene Abfrage entfällt).
2. Eine Zeile, die keine Phrase der Einheit trifft, wird mit den Einzelwörtern gerankt, sonst mit der ganzen Anfrage. Geprüft: gleiche Ränge in allen 57 452 Zeilen (größte Abweichung 0) und gleiche erste Seite; Test in `test_search.py`.

**Zeiten** (`search_datasets` mit zwei Verbindungen, bester von 3 nach einem Lauf zum Aufwärmen; ohne Aufbau der Antwort in der Route, den die Messung bei Otto mit misst):

| Anfrage | `main` | PR 1 (mit Vektorarm) | PR 1 + 2 | erste Seite PR 1 + 2 gegen `main` |
|---|---|---|---|---|
| data | 568 ms | 554 ms | 475 ms | anders (Vektorarm) |
| map | 312 ms | 311 ms | 869 ms | anders (Glossar [Karte, map]) |
| water | 352 ms | 355 ms | 368 ms | anders (Vektorarm) |
| Karte | 669 ms | 695 ms | 874 ms | anders (Glossar, Vektorarm) |
| Gewässer | 2 961 ms | 2 933 ms | **830 ms** | Volltext gleich, Fusion anders (Vektorarm) |
| Wasser Pegel Messstelle | 438 ms | 445 ms | 494 ms | anders (Vektorarm) |
| Bebauungsplan | 46 ms | 55 ms | 61 ms | anders (Vektorarm) |
| Sentinel-2 | 14 ms | 27 ms | 32 ms | gleiche 3 Treffer, andere Folge |
| Satellitenbilder in Echtfarben | 37 ms | 61 ms | 83 ms | anders (Vektorarm) |
| watr (Tippfehler) | 1 308 ms | 1 325 ms | 1 357 ms | anders (Vektorarm) |
| data + Kategorie water | 244 ms | 252 ms | 294 ms | anders (Vektorarm) |
| water + Region CH | 145 ms | 149 ms | 200 ms | anders (Vektorarm) |
| Gewässer + Region DE | 2 733 ms | 2 735 ms | 842 ms | Volltext gleich |
| map + Region DE-RP | 102 ms | 107 ms | 414 ms | anders (Glossar) |

- „Volltext gleich“: Die Liste nur aus dem Volltext (ohne Vektorarm) hat auf PR 1 + 2 denselben Hash wie auf `main`.
- **Vektorarm gleichzeitig:** kostet bei breiten Wörtern nichts, bei schmalen 10–45 ms (Einbetten der Anfrage 15 ms, dann die HNSW-Abfrage). Nacheinander statt gleichzeitig wären es bei breiten Wörtern 100–150 ms mehr [M].
- **Glossargruppe [Karte, map]** (§9a): „map“ und „Karte“ suchen jetzt beide nach beiden Wörtern, also nach der Vereinigung ihrer Treffer; deshalb 0,87 s statt 0,31 s für „map“. Unter 1 s, aber eine Folge von F6.
- **Was bleibt:** Tippfehler ohne Volltext-Treffer („watr“ 1,36 s, „Gewaesser“ 1,5 s): dort rechnet der Trigramm-Arm die Ähnlichkeit jedes Kandidaten (M5-66 §2a). Unverändert gegen `main`; siehe §6a.

## 6. Schwelle des Trigramm-Arms neu bewerten (PR 2)

### 6a. Ergebnis [M]

- **Am Bewertungs-Set** mit Vektorarm sind alle Maße für die Schwelle 0, 1, 20 und unbegrenzt gleich (Deutsch 0,947 / 0,868, Englisch 1,0 / 0,929). Die beiden Tippfehler des Sets (Q42 „Sentinal 2“, Q43 „Worldcovr“) findet auch der Vektorarm.
- **Am Bestand** ändert die Schwelle nichts an breiten Wörtern: Ab 20 Volltext-Treffern läuft der Trigramm-Arm ohnehin nicht. Teuer bleiben Anfragen ohne jeden Volltext-Treffer; dort läuft er bei jeder Schwelle, und dort braucht man ihn: Für „watr“ liefert der Vektorarm vorn „Windkraftanlagen …“, nur die Trigramme bringen Einträge mit „water“.
- **Vorschlag:** Schwelle 20 bleibt (F5 = 1). Tippfehler schneller zu machen (z. B. GiST-KNN nur, wenn der Volltext nichts findet; verworfen in M5-66 §2a wegen Gleichständen bei breiten Wörtern, die es hier nicht gibt) wäre eine eigene Aufgabe (F5 = 2). Schreibweisen mit „ae“, „oe“, „ue“ („Gewaesser“) sind ein eigener Fall: `unaccent` macht aus „ä“ ein „a“, nicht „ae“.

## 7. Dauer des ersten Einbettens bei Otto

- **Gemessen [M], Modell allein:** granite-97m-r2 fp32 auf 4 vCPU (Xeon 2,1 GHz, AVX-512) mit Texten wie denen gelisteter Einträge (Teile A und B, im Mittel 65 Tokens): 25 Texte/s mit einem Faden, 45 mit zwei, 77 mit vier (Stapel 32). Eine Anfrage: 15 ms mit einem Faden.
- **Gemessen [M], `catalog-load` am Bestand (§5):** erster Lauf 102 311 Zeilen in **1 599 s = 26,6 Minuten (64/s)**, dazu 73 s für den Suchindex der gelisteten Einträge; Spitze 0,94 GB im Prozess. Zweiter Lauf: 0 Zeilen, 0,2 s für den Schritt, 4,2 s für den ganzen Lauf.
- **Gerechnet [A]:** Die Rate wächst etwa mit den Kernen (1 → 4 Fäden: 25 → 77/s). Docker Desktop gibt seiner VM unter Windows meist alle logischen Kerne [S]. Mit 8 Kernen etwa 15 Minuten, mit 4 rund 27, auf einer älteren CPU ohne AVX-512 eher das Doppelte: **15 bis 55 Minuten**.
- `catalog-load` meldet unterwegs je 10 000 Zeilen und am Ende die Rate; die Zahl bei Otto ersetzt diese Schätzung.

## 8. Befehle für Otto (Windows, PowerShell 5.1, nur `docker compose`)

Vom Wurzelverzeichnis des Repos, Ausgaben nach `..\earthx-ausgaben\m5-23\`, nie ins Repo. Das Messskript `scripts/m5-23-messung.ps1` liegt im Branch von PR 2, der auf PR 1 aufbaut; es ließ sich in der Sitzung nicht ausführen (kein PowerShell), es ist aus `scripts/m5-66-messung.ps1` abgeleitet. Es misst die Route `POST /stac/collections` mit den Anfragen aus §5a (den Umlaut in „Gewässer“ baut es aus dem Zeichencode, weil die Kopie als ASCII geschrieben wird), `catalog-load` und den Speicher je Container. Es schreibt keine Kennungen, Titel oder Flächen.

**1. Vorher** (Stand `main`, Skript aus dem Branch von PR 2):

```powershell
git switch main
git pull
New-Item -ItemType Directory -Force ..\earthx-ausgaben\m5-23 | Out-Null
git fetch origin claude/upbeat-brown-zzfsrn-broad
git show FETCH_HEAD:scripts/m5-23-messung.ps1 | Set-Content -Encoding ASCII ..\earthx-ausgaben\m5-23\messung.ps1
docker compose build api catalog-load pgstac-migrate
docker compose up -d api
powershell -NoProfile -ExecutionPolicy Bypass -File ..\earthx-ausgaben\m5-23\messung.ps1 -Label vorher
```

**2. Erstes Einbetten** (PR 2 enthält PR 1; ein lokaler Branch, nichts davon wird gepusht). Der Bau lädt das Modell einmal von Hugging Face (415 MB, Prüfsummen fest). `catalog-load` wendet dabei die Migration 039 an:

```powershell
git switch -c m5-23-messung origin/claude/upbeat-brown-zzfsrn-broad
docker compose build api catalog-load pgstac-migrate
docker compose stop api
cmd /c "docker compose run --rm catalog-load 2>&1" | Tee-Object -FilePath ..\earthx-ausgaben\m5-23\einbetten.txt
cmd /c "docker compose run --rm --no-deps catalog-load 2>&1" | Tee-Object -FilePath ..\earthx-ausgaben\m5-23\einbetten-2.txt
```

Erwartet: im ersten Lauf `migrations applied: 039`, alle 10 000 Zeilen eine Zeile `embeddings written: … of …` und am Ende `embeddings written: <rund 102 000> of <dieselbe Zahl> in … s (…/s)`; im zweiten `embeddings written: 0 of 0`. Bricht der erste Lauf ab (Fenster zu, Rechner schläft), den Befehl wiederholen: Jeder Stapel ist schon gespeichert, der nächste Lauf holt nur die fehlenden Zeilen nach.

**3. Nachher:**

```powershell
docker compose up -d api
powershell -NoProfile -ExecutionPolicy Bypass -File ..\earthx-ausgaben\m5-23\messung.ps1 -Label nachher
git switch main
```

Zurückschicken: `vorher-suche.csv`, `nachher-suche.csv`, `*-laden.txt`, `*-speicher.txt` und die letzten 20 Zeilen von `einbetten.txt` (dort stehen nur Zahlen und Zeiten).

## 9. Neue Fragen des Bewertungs-Sets (PR 2, Vorschlag; Otto gibt frei)

### 9a. Vorschlag und Ergebnis [M]

| ID | Spr. | Frage | Note 2 | Note 1 | Art |
|---|---|---|---|---|---|
| Q53 | de | Gewässer | WC20, WC21 | S2, CLC, S1 | T |
| Q54 | en | water | WC20, WC21 | S2, CLC, S1, MCHP | T |
| Q55 | de | Karte | WC20, WC21, CLC | DEM, ALTI, BEV, MCH, MCHP | T |
| Q56 | en | map | WC20, WC21, CLC | DEM, ALTI, BEV, MCH, MCHP | T |

- Gesucht sind die Karten der Landbedeckung (WorldCover hat die Klasse „Permanent water bodies“); Note 1 haben Datensätze, die Wasser zeigen oder andere Karten sind.
- **Ohne weitere Änderung** finden „Gewässer“ und „Karte“ nichts, auch nicht mit Vektorarm (keine Zeile liegt über der Mindestähnlichkeit), und „water“ nur Sentinel-2: Deutsch 0,857 / 0,786, Englisch 0,938 / 0,875, F5 nicht bestanden.
- **Zwei Lücken im Suchtext:**
  - Die Klassen eines Bands (M5-62, `band_classes`) stehen nicht im Text. Mit ihnen in Teil D findet die Gruppe „Gewässer“ WorldCover über „Permanent water bodies“, „water“ ebenso. Betrifft nur volle Einträge mit Klassen (WorldCover, Sentinel-2 mit der Szenenklassifikation).
  - Das Glossar hat keine Gruppe [Karte, map]; die Texte sagen „land cover map“.
- **Mit beiden** besteht das Set mit den vier neuen Fragen F5: Deutsch 0,952 / 0,849, Englisch 1,0 / 0,906, Filterfragen 5/5, Negativfragen 4/5. Die lexikalischen Arme allein: Deutsch 17/21, Englisch 47/48 (neue Untergrenzen der Ratsche; die alten Fragen unverändert).
- Beides ist in PR 2 umgesetzt (je ein Commit), als Vorschlag zu F6.

## 10. Fragen an Otto

**F1 — Modell?**
1. granite-embedding-97m-multilingual-r2 in fp32 (Apache-2.0, 390 MB), das einzige, mit dem das Set F5 besteht **(Empfehlung)**
2. paraphrase-multilingual-MiniLM-L12-v2 int8 (118 MB), Deutsch knapp darunter (0,895)
3. multilingual-e5-small int8 (118 MB); am Set ohne Gewinn

**F2 — Mindestähnlichkeit?**
1. Relativ zur Anfrage gegen 46 feste Hintergrundtexte, Schwelle 2,7 in der Konfiguration **(Empfehlung)**
2. Feste Kosinusschwelle (besteht am Set mit keinem Modell)
3. Keine Schwelle; F5 für Negativfragen ändern

**F3 — Was eingebettet wird?**
1. Teile A und B: Kennung, Titel, Titel der Dubletten, Schlagworte, Ortsnamen, Kategorie **(Empfehlung)**
2. Alle vier Teile wie der Volltext

**F4 — `numberMatched` mit Vektorarm?**
1. Vektortreffer zählen mit, solange der Arm alle liefert; ist er im Index-Weg an der Tiefe voll, fehlt `numberMatched` (bei 10⁵ ohne Filter fast immer, §4.4) **(Empfehlung: nie eine falsche Zahl, wie M5-40 F4)**
2. `numberMatched` zählt nur die lexikalischen Arme (die Liste kann dann länger sein als die Zahl)

**F5 — Schwelle des Trigramm-Arms (§6a)?**
1. Bleibt bei 20 **(Empfehlung)**
2. Bleibt bei 20; Tippfehler ohne Volltext-Treffer (1,3–1,5 s bei 10⁵) schneller machen als eigene Aufgabe
3. Trigramm-Arm aus, wo der Vektorarm läuft (Tippfehler schnell, aber „watr“ findet dann „Windkraftanlagen“)

**F6 — Neue Fragen Q53–Q56 (§9a)?**
1. So freigeben, mit den Klassennamen im Suchtext und der Glossargruppe [Karte, map] **(Empfehlung)**
2. Fragen freigeben, aber ohne die beiden Ergänzungen (dann besteht das Set F5 nicht: Deutsch 0,857)
3. Andere Noten (bitte nennen)

**F7 — Modell beim Bau aus Hugging Face?**
1. Ja, feste Revision und SHA-256 je Datei; auch der Job `compose-topology` der CI lädt es dann (415 MB je Bau ohne Cache) **(Empfehlung)**
2. Eigene Ablage (z. B. Release-Asset im Repo), nur mit deiner Freigabe

**F8 — Hosts der Cloud-Umgebung „earthX“** (in der Sitzung freigegeben: `huggingface.co`, `us.aws.cdn.hf.co`, `cas-bridge.xethub-eu.hf.co`, dazu ungenutzt `cdn-lfs.hf.co`, `cdn-lfs-us-1.hf.co`, `cas-bridge.xethub.hf.co`)?
1. Die drei genutzten behalten, die drei ungenutzten entfernen (in den Einstellungen der Umgebung) **(Empfehlung)**
2. Alle sechs entfernen
3. Alle sechs behalten

### 10a. Antworten Otto (27.11.2026)

F1–F8 = 1. Dazu vor dem Abschluss (Otto, 27.11.2026): Speicher und Vermerk für M6 (§4.2), das schmale Fenster der Schwelle als bekanntes Risiko (§3.3), `test_module_boundaries[runner]` (§12), Bauzeit der CI mit dem Modell (§4.2a), Hosts der Umgebung (F8: entfernt werden `cdn-lfs.hf.co`, `cdn-lfs-us-1.hf.co`, `cas-bridge.xethub.hf.co`; es bleiben `huggingface.co`, `us.aws.cdn.hf.co`, `cas-bridge.xethub-eu.hf.co`).

## 11. Auslegungen

- **A1:** Ohne konfiguriertes Modell (Tests, Entwicklung ohne die Stufe `search`) läuft die Suche lexikalisch wie bisher, `api` meldet das beim Start. Im Image ist das Modell immer gesetzt.
- **A2:** Die Regel für Zahlen in Namen gilt auch im Vektorarm (Q51).
- **A3:** Der Vektorarm hat eine eigene Verbindungsmenge (§4.5).
- **A4:** Die Startprüfung verlangt Embeddings nur für volle Einträge (§4.4).
- **A5:** Die Hintergrundtexte sind erfunden und allgemein, keine Titel echter Einträge.
- **A6:** Mit einer Zahl in einem Namen sucht der Vektorarm nur unter Zeilen mit diesem Namen und dieser Zahl (§4.4).
- **A7:** Eine Glossar-Einheit trägt in ihrer Anfrage jedes Glied nur einmal und nur, wenn eine Zeile es hat; eine Zeile ohne Phrase der Einheit wird mit den Einzelwörtern gerankt (§5a). Treffer und Ränge bleiben gleich.

## 12. Tests

- `catalog`: Migration 039 (Spalten, CHECK, Index); Upsert leert das Embedding nur bei neuem Text; Einbetten in Stapeln schreibt nur Fehlende, ein zweiter Lauf nichts, eine zwischendurch geänderte Zeile nicht; ohne Modell kein Schritt.
- Vektorarm: exakter und Index-Weg liefern bei kleinem T dieselbe Reihenfolge; Mindestähnlichkeit leert die Liste; harte Filter, `Kept` und Zahlenregel wirken; Zeilen ohne Vektor fehlen; Tiefe und Zahl; falsche Dimension wird abgewiesen.
- Gleichzeitigkeit: beide Verbindungen werden genutzt; Ergebnis gleich wie nacheinander.
- `api`: Startprüfung ohne Embeddings der vollen Einträge; Route mit und ohne Modell.
- Image: Stufen, Runner ohne Modell, Prüfsummen gesetzt; kein `from_pretrained`, kein `huggingface_hub`.
- Bewertungs-Set mit Vektorarm besteht F5; Prüfwerte der Fixture; gleichzeitig und nacheinander gleiche Antworten.
- `test_module_boundaries[runner]`: Der Vertrag `runner` verbietet jedes Modul von `catalog`, das der Runner nicht braucht, auch ein neues (`adr/0016` F2). `catalog.embedding` fehlte dort; der Test war in der CI rot, auf `main` grün. Mein erster Befund „scheitert auch auf `main`“ war falsch: Die Gegenprobe lief mit `git stash`, das die damals unversionierte Datei `embedding.py` liegen ließ. Behoben in `.importlinter`. Ebenso fehlte 039 in der Liste von `test_migrations.py`.
- PR 2: gleiche Ränge mit den Einzelwörtern einer Einheit; eine Glossargruppe ohne Glied im Index ist unbekannt; Klassennamen im Suchtext; Zählung und Ratsche des Sets mit Q53–Q56.

## 13. Quellen

Abgerufen am 27.11.2026.

- In der Sitzung gelesen und gemessen (P, M): Modell-Repositorys auf Hugging Face über `https://huggingface.co/api/models/<repo>` (Dateien, Größen, Revisionen, Lizenz), Modellkarte und `1_Pooling/config.json` von `ibm-granite/granite-embedding-97m-multilingual-r2` an Revision `835ad14`; `vector.control` von pgvector 0.8.7 in der Sitzung.
- MTEB-Metadaten und -Ergebnisse (P\*): https://github.com/embeddings-benchmark/mteb (`mteb/models/model_implementations/e5_models.py`, `ibm_granite_models.py`, `sentence_transformers_models.py`), https://github.com/embeddings-benchmark/results (`MIRACLRetrieval.json` je Modell)
- IBM Granite Embedding, README (P\*): https://raw.githubusercontent.com/ibm-granite/granite-embedding-models/main/README.md
- sentence-transformers, Effizienz und Quantisierung (P\*): https://raw.githubusercontent.com/huggingface/sentence-transformers/main/docs/sentence_transformer/usage/efficiency.rst, https://raw.githubusercontent.com/UKPLab/sentence-transformers/master/examples/sentence_transformer/applications/embedding-quantization/README.md
- Gemeinschaftsmessungen (P\*): https://github.com/oscardvs/zoteus/issues/43 (int8, Durchsatz), https://github.com/MHarris-SgyMd/OB1/pull/67 (`halfvec`, binär), https://github.com/ryanjkendrick/PillionProgrammer/pull/77, https://github.com/sadrmanesh/persian-rag/pull/10
- pgvector 0.8.7 (P\*): https://raw.githubusercontent.com/pgvector/pgvector/v0.8.7/CHANGELOG.md, `README.md`, `src/hnsw.h`
- Elasticsearch (P\*): https://raw.githubusercontent.com/elastic/elasticsearch/main/docs/reference/elasticsearch/rest-apis/retrievers/knn-retriever.md, `.../retrievers/rrf-retriever.md`; Qdrant: https://raw.githubusercontent.com/qdrant/qdrant-client/master/qdrant_client/hybrid/fusion.py
- Suchtreffer (S): https://huggingface.co/intfloat/multilingual-e5-base/discussions/17, https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/rrf/, https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking
