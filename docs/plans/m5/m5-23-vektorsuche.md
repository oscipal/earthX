# M5-23 — Suche Teil 2: Vektorarm, Modellwahl, alle Arme gleichzeitig

- **Auftrag:** Otto, 27.11.2026, Stufe B (`plans/m5/m5-discovery-und-suche.md` §6.2, Zeile M5-23).
- **Grundlage:** `adr/0026` §4.3, §4.4, §6 Schritte 3 und 4, §8, §14, §15; `plans/m5/m5-41-pgvector.md` §6, §8, §9; `plans/m5/m5-42-suche-gelistete.md` §4, F6; `plans/m5/m5-66-breite-suche.md` §2a, F4, F8; `plans/m5/m5-43-postgres-pgvector.md` (pgvector 0.8.7 in Compose, CI und Cloud-Umgebung); Entscheidungslog bis 27.11.2026.
- **Belegstufen** wie in `adr/0026`: **M** in dieser Sitzung gemessen, **P** im Repo oder an der Primärquelle selbst gelesen, **P\*** Primärquelle über einen Hilfsagenten gelesen, **S** nur Suchtreffer, **A** eigene Ableitung.
- **Zwei Draft-PRs:** PR 1 dieser Plan und der Vektorarm (§4); PR 2 breite Wörter, Glossar im Volltext, Schwelle des Trigramm-Arms, neue Fragen des Sets und das Messskript (§5, §6, §9).
- **Netz der Sitzung:** `huggingface.co` war gesperrt. Für die Modellwahl hat Otto in der Sitzung sechs Hosts von Hugging Face in der Umgebung „earthX“ freigegeben (Frage F8). Echte Datenquellen wurden nicht abgerufen.

## 1. Kurzfassung

1. **Heute** (lexikalisch, `main` vom 27.11.) [M]: Deutsch Recall@5 0,789, MRR@10 0,763; Englisch 0,976 / 0,964; Filterfragen 5/5, Negativfragen 4/5. Auf Deutsch fehlen Q16 „Satellitenbilder in Echtfarben“, Q18 „Radarbilder bei Bewölkung“, Q38 „Schneebedeckung“, Q39 „Wasserflächen erkennen“. (Der Auftrag nennt 0,727; das war der Stand nach M5-22c, vor M5-42.)
2. **Modell:** `ibm-granite/granite-embedding-97m-multilingual-r2` (Apache-2.0, 97 Mio. Parameter, 384 Dimensionen), ONNX in fp32 (390 MB). Unter sieben Kandidaten ist es das einzige, mit dem das Set F5 besteht: Deutsch 0,947 / 0,868, Englisch 1,0 / 0,929, Negativfragen 4/5, Filterfragen 5/5 [M, §3.2]. Die int8-Fassungen desselben Modells verlieren (Deutsch 0,895) [M].
3. **Was eingebettet wird:** die Teile A und B des Suchtexts (Kennung, Titel, Titel der Dubletten, Schlagworte, Ortsnamen, Kategorie), ohne Beschreibung. Mit Beschreibung besteht kein Modell [M].
4. **Mindestähnlichkeit relativ zur Anfrage:** Ein Treffer zählt im Vektorarm, wenn sein Kosinus mindestens 2,7 Standardabweichungen über dem mittleren Kosinus derselben Anfrage zu 48 festen Hintergrundtexten liegt. Eine feste Kosinusschwelle besteht mit keinem Modell, weil Negativfragen und gesuchte Treffer im selben Bereich liegen [M, §3.3].
5. **Index und Weg** wie `adr/0026` §14: Spalte `halfvec(384)`, HNSW, gefiltert exakt bis 5·10⁴ Zeilen. Tiefe wie die lexikalischen Arme (§15).
6. **Gleichzeitig:** Die Anfrage wird eingebettet, während der Volltext läuft; Volltext und Vektorarm laufen auf zwei Verbindungen gleichzeitig; der Trigramm-Arm danach nur unter 20 Volltext-Treffern (§4.5).
7. **Einbetten** nur, was neu ist oder sich geändert hat, in Stapeln mit eigener Transaktion nach dem Hauptlauf von `catalog-load` (M5-42 §4, F6).
8. **Dauer bei Otto:** ~102 000 gelistete Einträge einmal einbetten: in der Sitzung 77 Texte/s auf 4 vCPU, also **rund 22 Minuten**; auf Ottos Rechner je nach Kernen etwa **10 bis 45 Minuten** (§7). Danach kostet ein Lauf ohne Änderung nichts.

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
- **Mit granite-97m-r2 fp32** findet der Vektorarm Q16 und Q18 auf Platz 1 bzw. unter den ersten fünf; Q38 und Q39 (Quick processings NDSI, NDWI) bleiben darunter. Q50 „hourly weather forecast“ trifft die Tageswerte von MeteoSchweiz und ist die eine Negativfrage mit Treffer.
- **Q51 „Sentinel-3“:** Jedes Modell legt es neben Sentinel-2. Der Vektorarm hält deshalb dieselbe Regel für Zahlen in Namen wie der Volltext (§4.4); damit bleibt die Liste leer.
- **Grenzen [A]:** 19 deutsche Fragen; ein Wechsel einer Frage verschiebt Recall@5 um 0,05. Das Fenster der Schwelle ist schmal (2,5–2,8). Die Wahl ist eine am Set, keine allgemeine Aussage über die Modelle.

### 3.3 Mindestähnlichkeit relativ zur Anfrage

- **Absolut** (Kosinus ≥ s) besteht mit keinem Modell: Für granite-97m-r2 fp32 kostet jede Schwelle, die vier Negativfragen leert (ab 0,82), Deutsch unter 0,9 [M].
- **Relativ:** Für jede Anfrage q werden μ(q) und σ(q) der Kosinuswerte zu 48 festen Hintergrundtexten gerechnet (24 deutsch, 24 englisch, kurze Titel wie „Abfallkalender und Wertstoffhöfe“, „road noise map“, ohne Bezug zu Fernerkundung). Ein Treffer zählt, wenn `(cos − μ(q)) / σ(q) ≥ 2,7`. Das gleicht aus, dass manche Anfragen zu allem ähnlich sind.
- **Gemessen [M]:** besteht bei 2,5–2,8 mit allen 48 Texten, bei 2,7–2,9 nur mit den deutschen, bei 2,6–2,8 nur mit den englischen, mit der ersten Hälfte der Liste nicht (dann 3 von 5 Negativfragen). Vorschlag 2,7.
- Die Hintergrundtexte liegen als YAML in `catalog`, ihre Vektoren rechnet `api` beim Start (48 Texte, unter 1 s). Kein Text aus Nutzeranfragen.

## 4. Umsetzung (PR 1)

### 4.1 Datenbank (Migration 039)

- `CREATE EXTENSION IF NOT EXISTS vector` (pgvector 0.8.7 aus M5-43; die Erweiterung ist nicht „trusted“, die Migration läuft wie alle als Eigentümer der Datenbank, in Compose und CI Superuser).
- Spalten in `earthx_dataset_search`: `embedding halfvec(384)`, `embedding_model text`, beide leer oder beide gesetzt (CHECK). HNSW `halfvec_cosine_ops` mit `m` 16, `ef_construction` 64 (`adr/0026` §14 Punkt 1).
- Ein neuer oder geänderter Text (`text_hash`) setzt das Embedding seiner Zeile auf leer (im Upsert); Box oder Zeitraum allein nicht, außer bei gelisteten Zeilen, deren `text_hash` die Eingaben insgesamt zählt (M5-42 §2 Punkt 3).

### 4.2 Modell im Image (`backend/Dockerfile`)

- Neue Stufe `model-files` auf demselben Basis-Image wie `app`: lädt `onnx/model.onnx` und `tokenizer.json` von Hugging Face an der festen Revision `835ad14087e140460703cf0fae09f97d469d65c2` und prüft je Datei den SHA-256 (Python `urllib`, kein zusätzliches Paket). Bricht bei Abweichung ab.
- Neue Stufe `search` = `app` + die Modelldateien unter `/app/models/` + `EARTHX_EMBEDDING_MODEL`. Die Dienste `api` und `catalog-load` bauen `target: search`; alle anderen, auch `runner`, bleiben auf `app` ohne Modell (`adr/0026` F2 a). Test: der Runner baut auf `app`, keine Stufe außer `search` kopiert aus `model-files`.
- Zur Laufzeit kein Netz: `tokenizers` liest nur `Tokenizer.from_file`; `huggingface_hub` ist keine Abhängigkeit. Ein Test prüft, dass `earthx` weder `from_pretrained` aufruft noch `huggingface_hub` importiert.
- Neue Abhängigkeiten in `requirements.txt` und Lock: `onnxruntime`, `tokenizers` (MIT bzw. Apache-2.0). Hinweis zu Dritten für das Modell (Apache-2.0).
- **Speicher je Prozess `api`:** wird im PR gemessen (Gewichte 390 MB fp32).

### 4.3 Einbetten in `catalog-load`

- Nach dem Commit des Hauptlaufs, je Stapel von 256 Zeilen eine Transaktion (M5-42 F6 = 1): Zeilen ohne Embedding oder mit anderem `embedding_model`, nach Kennung; geschrieben nur, wenn `text_hash` sich seit dem Lesen nicht geändert hat.
- Ein Lauf ohne Änderung bettet nichts ein und kostet eine Abfrage. Ein Abbruch lässt Zeilen ohne Vektor; der nächste Lauf holt sie nach, der Vektorarm überspringt sie bis dahin.
- Ausgabe: Zahl je 10 000 und am Ende Zeilen, Sekunden, Texte je Sekunde; Zeitzeile `time embeddings`. Keine Kennungen, keine Texte.
- Ohne Modell (Entwicklung ohne die Stufe `search`, Tests) entfällt der Schritt mit einer Zeile in der Ausgabe.

### 4.4 Vektorarm in der Suche (`catalog/search.py`)

- `api` bettet die Anfrage ein (ein Faden je Anfrage, ~15 ms [M]) und gibt den Vektor an `search_datasets`.
- Dieselben Quellen und harten Filter wie die lexikalischen Arme (`_sources`, `Kept`, Zeit, Fläche), dazu die Regel für Zahlen in Namen („Sentinel 3“ verlangt eine 3 im Namen).
- **Wege (§14 Punkt 2):** zählen, wie viele Zeilen die Filter bestehen, bis T + 1 (T = 5·10⁴, Konfiguration). Bis T exakt (Index-Scans aus, Sortierung nach Abstand); darüber HNSW mit `hnsw.iterative_scan = relaxed_order` und `hnsw.ef_search = min(1 000, max(200, Tiefe))` in einer `MATERIALIZED`-CTE. Ohne jeden Filter immer HNSW.
- **Mindestähnlichkeit** (§3.3) als Grenze des Abstands außerhalb der CTE.
- **Tiefe** wie die anderen Arme (`DEPTH`, wächst mit der Seite), Gleichstand ganz.
- **Trefferzahl:** Der Vektorarm zählt seine Treffer exakt, solange er sie alle liefert; ist er im Index-Weg an der Tiefe voll, ist seine Zahl unbekannt und `numberMatched` fehlt (Frage F4).
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
- Skript zum Neurechnen: `scripts/m5-23-embeddings.py`, läuft im Image `search` (Befehl in §8).

## 5. Breite Wörter und Glossar im Volltext (PR 2)

- **Ziel** (M5-66 F1, M5-23): ein breites Wort ohne Filter unter 1 s bei 10⁵, auch „Karte“ (1,26 s nach M5-66 PR 1) und die Glossargruppe „Gewässer“ (1,7 s, M5-66 F8).
- **Synthetischer Bestand** wie M5-66 §5 (102 313 veröffentlichte gelistete Einträge, Texte und Kategorien nach den Lauf-Berichten), dazu die Embeddings mit dem gewählten Modell. Skripte nur in der Sitzung.
- Gemessen werden vorher und nachher je Anfrage: Zeit der Route, Zeit je Arm, erste Seite (Hash), `numberMatched`. Ergebnisse in §5a mit PR 2.

## 6. Schwelle des Trigramm-Arms neu bewerten (PR 2)

Die Schwelle 20 (M5-66 Weg 3) wird mit dem Vektorarm am Set und am synthetischen Bestand gemessen: 0 (Trigramme nie), 20, unbegrenzt. Ergebnis und Vorschlag in §6a mit PR 2 (Frage F5).

## 7. Dauer des ersten Einbettens bei Otto

- **Gemessen [M]:** granite-97m-r2 fp32 auf 4 vCPU (Xeon 2,1 GHz, AVX-512) mit Texten wie denen gelisteter Einträge (Teile A und B, im Mittel 65 Tokens): 25 Texte/s mit einem Faden, 45 mit zwei, **77 mit vier** (Stapel 32). Eine Anfrage: 15 ms mit einem Faden.
- **Gerechnet [A]:** 102 000 Einträge / 77 je s ≈ **22 Minuten** auf 4 Kernen. Docker Desktop gibt seiner VM unter Windows meist alle logischen Kerne [S]. Bei 8 Kernen etwa 11–15 Minuten, auf einer älteren CPU ohne AVX-512 eher das Doppelte: **10 bis 45 Minuten**. Dazu kommt das Einfügen in den HNSW-Index (wird mit PR 2 am Bestand gemessen).
- `catalog-load` meldet unterwegs je 10 000 Zeilen und am Ende die Rate; die Zahl bei Otto ersetzt diese Schätzung.

## 8. Befehle für Otto (Windows, PowerShell 5.1, nur `docker compose`)

Vom Wurzelverzeichnis des Repos, Ausgaben nach `..\earthx-ausgaben\m5-23\`, nie ins Repo. Das Messskript `scripts/m5-23-messung.ps1` kommt mit PR 2.

**Vorher** (Stand `main`, Skript aus dem Branch von PR 2 geholt):

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

**Erstes Einbetten** (beide PRs zusammen auf einem lokalen Branch, nichts davon wird gepusht; der Bau lädt das Modell einmal, 415 MB):

```powershell
git fetch origin claude/upbeat-brown-zzfsrn claude/upbeat-brown-zzfsrn-broad
git switch -c m5-23-messung origin/claude/upbeat-brown-zzfsrn
git merge --no-edit origin/claude/upbeat-brown-zzfsrn-broad
docker compose build api catalog-load pgstac-migrate
docker compose stop api
docker compose run --rm catalog-load 2>&1 | Tee-Object -FilePath ..\earthx-ausgaben\m5-23\einbetten.txt
docker compose run --rm catalog-load 2>&1 | Tee-Object -FilePath ..\earthx-ausgaben\m5-23\einbetten-2.txt
```

Erwartet: `embeddings written: …` mit rund 102 000 im ersten und 0 im zweiten Lauf, je mit Rate in Texten je Sekunde.

**Nachher:**

```powershell
docker compose up -d api
powershell -NoProfile -ExecutionPolicy Bypass -File ..\earthx-ausgaben\m5-23\messung.ps1 -Label nachher
docker stats --no-stream --format "{{.Name}} {{.MemUsage}}" | Out-File -Encoding utf8 ..\earthx-ausgaben\m5-23\speicher.txt
git switch main
```

Bricht das erste Einbetten ab (Fenster zu, Rechner schläft): einfach den Befehl wiederholen; der Lauf holt nur die fehlenden Zeilen nach.

## 9. Neue Fragen des Bewertungs-Sets (PR 2, Vorschlag; Otto gibt frei)

Breite Wörter und Glossarwörter (M5-66 F8), gegen die Datensätze des Sets benotet. Vorschlag in §9a mit PR 2.

## 10. Fragen an Otto

**F1 — Modell?**
1. granite-embedding-97m-multilingual-r2 in fp32 (Apache-2.0, 390 MB), das einzige, mit dem das Set F5 besteht **(Empfehlung)**
2. paraphrase-multilingual-MiniLM-L12-v2 int8 (118 MB), Deutsch knapp darunter (0,895)
3. multilingual-e5-small int8 (118 MB); am Set ohne Gewinn

**F2 — Mindestähnlichkeit?**
1. Relativ zur Anfrage gegen 48 feste Hintergrundtexte, Schwelle 2,7 in der Konfiguration **(Empfehlung)**
2. Feste Kosinusschwelle (besteht am Set mit keinem Modell)
3. Keine Schwelle; F5 für Negativfragen ändern

**F3 — Was eingebettet wird?**
1. Teile A und B: Kennung, Titel, Titel der Dubletten, Schlagworte, Ortsnamen, Kategorie **(Empfehlung)**
2. Alle vier Teile wie der Volltext

**F4 — `numberMatched` mit Vektorarm?**
1. Vektortreffer zählen mit, solange der Arm alle liefert; ist er im Index-Weg an der Tiefe voll, fehlt `numberMatched` **(Empfehlung)**
2. `numberMatched` zählt nur die lexikalischen Arme (die Liste kann dann länger sein als die Zahl)

**F5 — Schwelle des Trigramm-Arms:** folgt mit PR 2 (§6a).

**F6 — Neue Fragen des Sets:** folgen mit PR 2 (§9a).

**F7 — Modell beim Bau aus Hugging Face?**
1. Ja, feste Revision und SHA-256 je Datei; auch der Job `compose-topology` der CI lädt es dann (415 MB je Bau ohne Cache) **(Empfehlung)**
2. Eigene Ablage (z. B. Release-Asset im Repo), nur mit deiner Freigabe

**F8 — Hosts der Cloud-Umgebung „earthX“** (in der Sitzung freigegeben: `huggingface.co`, `us.aws.cdn.hf.co`, `cas-bridge.xethub-eu.hf.co`, dazu ungenutzt `cdn-lfs.hf.co`, `cdn-lfs-us-1.hf.co`, `cas-bridge.xethub.hf.co`)?
1. Die drei genutzten behalten, die drei ungenutzten entfernen (in den Einstellungen der Umgebung) **(Empfehlung)**
2. Alle sechs entfernen
3. Alle sechs behalten

## 11. Auslegungen

- **A1:** Ohne konfiguriertes Modell (Tests, Entwicklung ohne die Stufe `search`) läuft die Suche lexikalisch wie bisher, `api` meldet das beim Start. Im Image ist das Modell immer gesetzt.
- **A2:** Die Regel für Zahlen in Namen gilt auch im Vektorarm (Q51).
- **A3:** Der Vektorarm hat eine eigene Verbindungsmenge (§4.5).
- **A4:** Die Startprüfung verlangt Embeddings nur für volle Einträge (§4.4).
- **A5:** Die Hintergrundtexte sind erfunden und allgemein, keine Titel echter Einträge.

## 12. Tests

- `catalog`: Migration 039 (Spalten, CHECK, Index); Upsert leert das Embedding nur bei neuem Text; Einbetten in Stapeln schreibt nur Fehlende, ein zweiter Lauf nichts, eine zwischendurch geänderte Zeile nicht; ohne Modell kein Schritt.
- Vektorarm: exakter und Index-Weg liefern bei kleinem T dieselbe Reihenfolge; Mindestähnlichkeit leert die Liste; harte Filter, `Kept` und Zahlenregel wirken; Zeilen ohne Vektor fehlen; Tiefe und Zahl; falsche Dimension wird abgewiesen.
- Gleichzeitigkeit: beide Verbindungen werden genutzt; Ergebnis gleich wie nacheinander.
- `api`: Startprüfung ohne Embeddings der vollen Einträge; Route mit und ohne Modell.
- Image: Stufen, Runner ohne Modell, Prüfsummen gesetzt; kein `from_pretrained`, kein `huggingface_hub`.
- Bewertungs-Set mit Vektorarm besteht F5; Prüfwerte der Fixture.

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
