# ADR 0026 — Hybrid-Suche und Bewertungs-Set

- **Status:** Angenommen (fest, Otto, 06.11.2026; Antworten in §11). F1 und F4–F9 jeweils Option 1, F2 Option 1 mit zwei Bedingungen, F3 Option 2 (kein pgvector in M5). Die Nummer 0026 ist im M5-Plan fest vergeben (`plans/m5/m5-discovery-und-suche.md` §5a).
- **Datum:** 2026-11-06 (Entwurf, Draft-PR #301); angenommen 2026-11-06.
- **Aufgabe:** M5-04 laut `docs/plans/m5/m5-discovery-und-suche.md` §5a (Entscheidungsvorlage C, §4).
- **Autonomiestufe:** C. Kein Produktivcode.
  - Geändert werden nur dieses ADR und eine Zeile im Entscheidungslog.
  - Unverändert bleiben `backend/`, `frontend/`, `scripts/`, Registry, Fixtures, Backlog, M5-Plan, `.github/`, `.claude/` und `CLAUDE.md`.
- **Vorab fest:**
  - Hybrid-Suche in Postgres: Volltext, Vektorähnlichkeit mit pgvector und strukturierte Filter, zusammengeführt per Reciprocal Rank Fusion (RRF); kein eigener Such- oder Vektordienst, solange die Mengen ihn nicht erzwingen (`architekturplan.md` 0 Punkt 9, 5.3; `projektplan.md` M5).
  - Embeddings aus einem eigenen Embedding-Modell, kein Chat-Modell; Auswahl per Bewertungs-Set (`projektplan.md` 3.4).
  - Bewertungs-Set: Die Session entwirft 30–50 Testfragen, Otto ergänzt und gibt frei (M5-Plan §5 Antwort 6). Es enthält deutsche und englische Fragen (`adr/0023` §7.5). Inhalt sind die Quellen aus `adr/0023` §11 (Vorgabe Otto zu dieser Aufgabe).
  - Prototyp-Datensätze kommen im Bewertungs-Set nie vor (`adr/0024` R7).
  - Konto-Quellen erscheinen in M5 nur als Katalogeintrag mit Link und `access.account` (`adr/0027` F2, F8).
  - Die Suche bekommt ihren Platz im „Data catalogue“ (UI-05, M5-Plan §6.1; Vorgabe Otto zu dieser Aufgabe). UI-05 hält den Platz frei, ohne die Suche vorwegzunehmen.
  - **Nachtrag Otto (06.11.2026, UI-05 F5):** Der „Data catalogue“ ist ein größeres Fenster über der Karte mit rotem x, geöffnet über ein Symbol in der linken Leiste, kein linkes Panel (§7).
  - Oberflächentexte englisch, Regeln aus `docs/ui/leitfaden.md`.
- **Grundlage:**
  - `ENTSCHEIDUNGEN_2026-09-18.md` §4 (öffentliches Repo).
  - `KLAERUNGEN.md` B8, B10, B11, B13.
  - `projektuebersicht.md` §2 (Prinzipien 6, 7, 9, 10, 11, 16), §7 („Auswahl & Suche“), §10 (Chatbot).
  - `architekturplan.md` 3.1, 4.3 (Enrich), 5.1, 5.2, 5.3, 8.3, 10, 15.2 (Spike „Hybrid-Suche“).
  - `projektplan.md` 3.4, M5, M7 Paket 7a.
  - `adr/0005` (föderierte Item-Suche, Regel VI zu Extensions), `adr/0021` (Suchfilter je Datensatz), `adr/0023` §7.5, §8.3, §11, `adr/0024` R7, R8, `adr/0027` §4.1, §6.1.
- **Betroffen:** Fassung 3 des M5-Plans; `catalog` (Suchindex, Glossar), `api` (Collection-Suche, Vektorvergleich, Modell nur im Image von `api`), `backend/Dockerfile` (eigene Stufe für das Modell); das Frontend des „Data catalogue“ (nach UI-05); Onboarding-Checkliste (F7); `adr/0025` (wo Embeddings entstehen); `architekturplan.md` 5.3 und 10 (Nachtrag, F3). Nicht betroffen nach F3: Postgres-Image, `docker-compose.yml` (Dienst `postgres`), `.github/workflows/ci.yml`.

---

## Methode und Belegstufen

Belegstufen wie in `adr/0023`:

- **M:** in dieser Sitzung gemessen.
- **P:** am Primärdokument selbst gelesen (hier vor allem Code und Dokumente des Repos).
- **P\*:** Primärdokument über das Abrufwerkzeug eines Hilfsagenten gelesen, sinngemäß.
- **S:** Suchtreffer oder Zusammenfassung, Wortlaut nicht geprüft.
- **A:** eigene Ableitung, ein Argument und kein Beleg.

**Was in dieser Sitzung gemessen ist [M]:**

- Die Postgres-Installation der Cloud-Sitzung hat `postgis`, `pg_trgm`, `unaccent` und `fuzzystrmatch`, aber **kein `vector`** (pgvector). Das Paket `postgresql-16-pgvector` steht in den Paketquellen der Distribution in Version **0.6.0**.
- Die Textsuche-Daten von Postgres enthalten Stoppwortlisten für Deutsch, Englisch, Französisch und Italienisch, aber keine Wörterbücher mit Zerlegung von Komposita (nur die Beispieldateien `hunspell_sample*`, `ispell_sample*`).
- `huggingface.co` ist aus der Sitzung nicht erreichbar (keine Verbindung), PyPI schon. Ein Embedding-Modell lässt sich hier also nicht laden und nicht messen.

**Was im Repo steht [P]:**

- Compose und der Postgres-Dienst der CI nutzen beide `postgis/postgis:16-3.4` (`docker-compose.yml`, `.github/workflows/ci.yml`).
- Die eigene STAC-API läuft auf `stac-fastapi.pgstac==6.4.1` und `pypgstac==0.9.12` (`backend/requirements.txt`). Von den Extensions ist nur `pagination` eingeschaltet (`api/main.py`, `_ENABLED_EXTENSIONS`, `adr/0005` Regel VI).
- Eine Textsuche über Datensätze gibt es nicht mehr. Der Filter aus M3-10 (Titel, Beschreibung und `keywords` im Client) ist durch die Knöpfe je Datensatz ersetzt (M4-29; `ControlPanel.tsx`).
- Die Registry hat drei Textfelder je Datensatz: `title`, `description` und `keywords` (mindestens ein Schlagwort, ohne Vorgabe, `registry.py` `_check_keywords`). Alle Texte sind englisch. Ein Feld für Anbieter (`providers`) gibt es in der Collection nicht (`collection.py`).
- Das Zugangsprotokoll schreibt Methode, Pfad, Status und Dauer, **nie den Query-String** (`backend/earthx/logging.py`, `RequestIdMiddleware`).

**Anfragen an Datenquellen:** keine. Der Hilfsagent las öffentliche Seiten zu Verfahren, Modellen und Standards (§3).

---

## 0. Kurzfassung

1. **Was gesucht wird:** Datensätze (STAC-Collections), nicht Szenen. Heute sind es zwei; mit M5 rund zehn, nach dem Harvest vielleicht einige Hundert bis Tausend (§1). Die Szenen bleiben bei der föderierten Item-Suche (`adr/0005`).
2. **Entscheidung (§6, Otto 06.11.2026):** Hybrid-Suche mit Postgres und dem Prozess `api`, mit fünf Festlegungen:
   - **Lexikalischer Arm:** Volltext mit drei Konfigurationen zugleich (`simple`, `german`, `english`) plus `unaccent`, dazu Trigramme für Tippfehler und ein kuratiertes **Glossar** de/en, das die Anfrage erweitert.
   - **Vektorarm:** ein kleines, mehrsprachiges Embedding-Modell mit offener Lizenz, höchstens so groß wie multilingual-e5-base, bevorzugt int8, **lokal im Prozess** `api` (ONNX auf CPU), kein gehosteter Dienst (F2). **Kein pgvector in M5 (F3):** Die Vektoren liegen als Spalte in Postgres, die harten Filter laufen in SQL, der Vergleich exakt im Prozess `api`. Ein Mindestmaß an Ähnlichkeit erlaubt „kein Treffer“.
   - **Fusion:** RRF mit k = 60 über beide Arme. Raum, Zeit und Zugang sind **harte Filter vor der Fusion**, keine Rangpunkte.
   - **Schnittstelle:** STAC Collection Search mit Freitext `q`; eine AOI nur im Body (`POST`), nie in der URL.
   - **Index:** Text, `tsvector` und Embedding je Datensatz entstehen beim Laden des Katalogs (`catalog-load`) und nur bei geändertem Text oder Modell.
3. **Bewertungs-Set (§8):** 50 Fragen, je zur Hälfte deutsch und englisch, über die Datensätze aus `adr/0023` §11 und die vorhandenen. Sie prüfen Namen, Themen, Sprachwechsel, Region, Zeit, Fähigkeiten, Abkürzungen und Tippfehler, Konto-Einträge und vier Fragen ohne passenden Datensatz. Eine Frage ruht, bis ihr Datensatz im Katalog steht.
4. **Wie das Set läuft (§8.4):** als Test in der CI **ohne Modell und ohne Netz**, mit vorab gerechneten Vektoren als Fixture. Ein Prüfwert zum Text erzwingt, dass die Vektoren neu gerechnet werden, wenn sich ein Text ändert.
5. **Oberfläche (§7):** ein Suchfeld oben im „Data catalogue“. Leer zeigt der Katalog seine Gruppen (UI-05); mit Text eine gerankte Liste derselben Zeilen mit der Gruppe als Marke. Dazu ein Schalter für die AOI (F6). Keine Punktzahlen, kein Zusatztext.
6. **Kein Image-Wechsel der Datenbank:** pgvector fehlt im Postgres-Image von Compose und CI [P] und in der Cloud-Sitzung [M]. Nach F3 (Option 2) bleibt das so: Postgres-Image, `.github/workflows/ci.yml` und Cloud-Umgebung ändern sich in M5 nicht. pgvector kommt erst, wenn die Menge einen Index verlangt.
7. **Nicht gemessen:** die Qualität eines Modells am Set. Hugging Face ist aus der Sitzung gesperrt [M]. Die Auswahl des Modells ist deshalb Teil der Umsetzung (F2), mit einer Vorauswahl nach Lizenz und Größe (§3.4).

---

## 1. Kontext und Frage

M5 baut den „Datacrawler“ (Projektplan §4 M5). Zum Inhalt gehören eine Hybrid-Suche mit pgvector, Volltext und RRF sowie ein Bewertungs-Set für die Suchqualität. Zur Abnahme gehört: „Bewertungs-Set besteht“. Der Architekturplan nennt dazu einen Spike: „Reicht pgvector + Volltext mit RRF auf einem Testkatalog für die Bewertungs-Anfragen?“ (15.2).

**Fragen dieses ADR:**

1. Wie ist die Suche über Datensätze gebaut: Felder, Sprachen, Modell, Fusion, Filter, Schnittstelle, Index?
2. Wie sieht das Bewertungs-Set aus, wann besteht es, und wie läuft es in der CI?
3. Wo sitzt die Suche in der Oberfläche, und was heißt das für UI-05?

**Nicht Teil dieses ADR:**

- die Suche nach Szenen (Items): bleibt föderiert (`adr/0005`), mit den Filtern aus `adr/0021`;
- die Harvest-Pipeline (`adr/0025`) und der YAML-Lader;
- der Chatbot (M7 Paket 7a); er nutzt später dieselbe Schnittstelle und dasselbe Set (`architekturplan.md` 8.3);
- die Gruppierung des „Data catalogue“ und das Feld dafür (UI-05).

**Ausgangslage [P]:**

- Der Katalog hat heute zwei Datensätze: `sentinel-2-c1-l2a` und `cop-dem-glo-30`.
- In M5 kommen dazu: Sentinel-1 GRD (DS-04), WorldCover 2020 und 2021 (M5-07), swissALTI3D (M5-08), BEV ALS-DGM 1 m (M5-09), eine Meteorologie-Quelle (M5-11) und Konto-Quellen als Katalogeinträge (`adr/0027` W0). Das sind rund zehn bis zwanzig Datensätze.
- Erst die Pipeline (`adr/0025`) bringt größere Mengen; der Architekturplan rechnet mit „tausenden“ Collections (5.2).
- Die Texte der Registry sind englisch. Harvest-Quellen liefern ihre Texte in der eigenen Sprache: DWD und BEV deutsch, die FSDI de/fr/it/en (`adr/0023` §7.5).
- Nutzer fragen deutsch oder englisch, meist mit zwei bis sechs Wörtern [A].

---

## 2. Kriterien

| # | Kriterium | Woher |
|---|---|---|
| K1 | Findet deutsche und englische Anfragen gleich gut, auch über die Sprache hinweg (deutsche Frage, englischer Text) | `adr/0023` §7.5; Otto |
| K2 | Besteht das Bewertungs-Set; Qualität ist messbar und regressionsfest | Projektplan M5, Abnahme |
| K3 | Eine Datenbank, kein zusätzlicher Dienst | `architekturplan.md` 0 Punkt 9 |
| K4 | Keine Daten an fremde Dienste zur Laufzeit; keine Secrets; Modellnamen in der Konfiguration | `ENTSCHEIDUNGEN` §4; Projektplan 3.4; `CLAUDE.md` |
| K5 | Läuft in der CI ohne Netz und ohne großes Modell | `CLAUDE.md` („Externe Quellen nur über `tests/fixtures`“) |
| K6 | Kosten je Anfrage klein; keine kostenpflichtigen Dienste ohne Otto | Prinzip 10; `CLAUDE.md` |
| K7 | Skaliert von zehn auf einige Tausend Datensätze ohne Umbau | Prinzip 16 |
| K8 | Standards raus: als STAC-Schnittstelle nutzbar; API-first | Prinzipien 6, 7 |
| K9 | Ehrlich: kein Treffer, wo nichts passt; Filter sind Filter, kein Rang | Prinzip 9; `architekturplan.md` 5.1 (`ignored_filters`) |
| K10 | Keine AOI in URLs oder Logs | M5-Plan §9; `CLAUDE.md` |
| K11 | Passt in den „Data catalogue“ ohne Zusatztext | Leitfaden §1 Punkt 4; M5-Plan §2 Punkt 8 |

---

## 3. Stand der Technik

Gelesen hat ein Hilfsagent am 06.11.2026. Erreichbar waren nur `github.com`, `raw.githubusercontent.com` und `pypi.org`. Papers (arXiv), Modellkarten (Hugging Face), die Seiten von postgresql.org, stacspec.org und der Cloud-Anbieter waren gesperrt. Deshalb stehen Modellangaben auf den Metadaten im Code von `mteb` und auf READMEs, die Postgres-Doku auf ihrem Quelltext im Repository von PostgreSQL. Belegstufen je Aussage; Quellen in §13.

### 3.1 Reciprocal Rank Fusion

- **Verfahren:** Cormack, Clarke, Büttcher, SIGIR 2009: unüberwachte Fusion mehrerer Ranglisten, `score(d) = Σ 1 / (k + rang_i(d))` mit k = 60 [S, Paper nicht gelesen]. Warum gerade 60, geben Sekundärquellen verschieden wieder [S].
- **Praxis:** Das Beispiel zur Hybrid-Suche im Repository von pgvector nutzt genau diese Form: k = 60, Konfiguration `english`, `ts_rank_cd` [P\*].
- **Nutzen:** Auf MIRACL (18 Sprachen) liegt eine Hybrid-Suche aus BM25 und einem dichten Modell bei nDCG@10 57,8 gegen 39,3 (BM25) und 41,5 (mDPR) [S]. Eine Studie von Elastic auf BEIR findet für RRF rund 18 % mehr nDCG@10 als BM25 und eine geringe Empfindlichkeit gegen den Parameter (rund 5 % zwischen bester und schlechtester Wahl) [S].
- **Nicht gefunden:** Messungen mit deutschen Kurzanfragen oder mit Katalogen unter einigen Tausend Dokumenten. Für diese Größe sagen Benchmarks wenig [A]; das Set misst es.

### 3.2 pgvector

- **Stand:** Version 0.8.7 (Oktober 2026), PostgreSQL License [P\*].
- **Suche:** Ohne Index ist die Suche exakt („perfect recall“). Indizes: HNSW und IVFFlat. Bei einem ANN-Index wirkt ein `WHERE` erst nach dem Index-Scan, es können zu wenige Zeilen zurückkommen; seit 0.8.0 hilft `hnsw.iterative_scan` [P\*]. Bei einigen Tausend Zeilen braucht es keinen Index [A].
- **Speicher:** `halfvec` halbiert den Platz [P\*].
- **Verwaltetes Postgres:** pgvector 0.8.0 bei AWS RDS (seit November 2024) und Aurora (seit April 2025), als Erweiterung `vector` bei Azure [S]. Google Cloud SQL nicht geklärt. Für die Wahl des Anbieters (M6) ist pgvector also kein Ausschluss [A].
- **Images:** `postgis/postgis` enthält kein pgvector [P\*]. Der übliche Weg ist ein eigenes Dockerfile auf dem PostGIS-Image mit dem Paket `postgresql-16-pgvector` [P\*]. Die Paketquellen der Distribution in der Cloud-Sitzung haben nur 0.6.0 [M]; die Paketquellen von PostgreSQL (PGDG) führen neuere Fassungen [A, nicht geprüft].

### 3.3 Volltext in Postgres

- **`websearch_to_tsquery`:** Wörter mit UND, Anführungszeichen als Phrase, `or` als ODER, `-` als NICHT; wirft **nie** einen Syntaxfehler [P\*]. Für Eingaben aus einem Suchfeld ist das die passende Funktion [A].
- **Rang:** `ts_rank` und `ts_rank_cd` nutzen keine globalen Angaben, also kein IDF wie BM25 [P\*]. Für RRF zählt nur die Reihenfolge; bei einem kleinen Katalog ist der Unterschied gering [A].
- **Sprachen:** Snowball-Stemmer gibt es u. a. für Deutsch, Englisch und Französisch; `simple` schreibt nur klein [P\*].
- **Komposita:** Postgres setzt von Hunspell nur die „basic compound word operations“ um; Wörterbücher dafür liegen nicht bei [P\*]. Ein Bericht findet, dass „Wasserkraft“ auch mit Hunspell nicht zerlegt wird [S]. Dass Snowball keine Komposita zerlegt, ist nicht am Text belegt, aber sicher [A]. In der Sitzung ist kein solches Wörterbuch installiert [M].
- **`unaccent`** ist ein filterndes Wörterbuch vor dem Stemmer [P\*]. Wie es Umlaute und „ß“ abbildet, steht nicht in der Doku; die Umsetzung prüft es mit einem Test.
- **`pg_trgm`:** `similarity` und `word_similarity`, Schwelle 0,3, GIN- und GiST-Indizes [P\*].
- **BM25 in Postgres:** ParadeDB `pg_search` und VectorChord-bm25 stehen unter AGPL-3.0 (VectorChord wahlweise ELv2) [P\*]; `pg_textsearch` von Timescale unter PostgreSQL License, aber für PG 17/18 [P\*]. Keine davon ist für M5 nötig [A]; sie kommen erst in Frage, wenn das Set am Rang des Volltexts scheitert.
- **pgstac:** pgstac kann `q` bei der Collection-Suche seit 0.9.2 [P\*]. Die Anfrage läuft dort fest mit `to_tsquery('english', …)` und `to_tsvector('english', …)` über Beschreibung, Titel und Schlagworte, inline berechnet und ohne Index; das Changelog nennt die Textsuche selbst „un-indexed“ [P\*]. Für deutsche Texte und Anfragen taugt das nicht. Die Suche baut deshalb ihren eigenen Index (§4.2), statt `q` an pgstac durchzureichen [A].

### 3.4 Embedding-Modelle

Angaben aus den Metadaten von `mteb` [P\*]; „MMTEB-Retrieval“ ist der Mittelwert aus der Tabelle des Qwen3-README (Juni 2025) [P\*], wo vorhanden.

| Modell | Parameter | Dim. | Lizenz | Präfix | MMTEB-Retrieval | Einschätzung [A] |
|---|---|---|---|---|---|---|
| multilingual-e5-small | 118 M | 384 | MIT | `query: ` / `passage: ` | — | **Kandidat 1:** klein, auf Retrieval trainiert |
| multilingual-e5-base | 278 M | 768 | MIT | wie oben | — | **Kandidat 2** |
| bge-m3 | 568 M | 1024 | MIT | keines | 54,60 | **Kandidat 3:** stark auf MIRACL [S], aber groß |
| Qwen3-Embedding-0.6B | 596 M | 1024 | Apache-2.0 | Instruktion an der Anfrage | 64,64 | stärkster Wert, aber Decoder-Modell, auf CPU vermutlich langsam; nur wenn 1–3 scheitern |
| gte-multilingual-base | 305 M | 768 | Apache-2.0 | keines | — | Ersatz für Kandidat 2 |
| paraphrase-multilingual-MiniLM-L12-v2, -mpnet-base-v2 | 118 M, 278 M | 384, 768 | Apache-2.0 | keines | — | auf Ähnlichkeit von Sätzen trainiert, nicht auf Retrieval; nur als Vergleich |
| multilingual-e5-large(-instruct) | 560 M | 1024 | MIT | wie e5 bzw. Instruktion | 57,12 (instruct) | wie bge-m3, ohne Vorteil |
| EmbeddingGemma-300m | 308 M | 768 | eigene Bedingungen („gemma“) | ja | — | nur nach Prüfung der Bedingungen durch Otto |
| nomic-embed-text-v2-moe | 475 M | 768 | Apache-2.0 | ja | — | möglich, wenig verbreitet |
| jina-embeddings-v3 | 572 M | 1024 | **CC-BY-NC-4.0** | Adapter | — | **ausgeschlossen:** nicht kommerziell |

- **Laufzeit:** `fastembed` (Apache-2.0, 0.9.1) bringt ONNX-Modelle für die CPU; eingebaut sind u. a. multilingual-e5-large und die beiden paraphrase-Modelle; e5-small, e5-base und bge-m3 gehen als eigenes Modell [P\*]. Ob fertige ONNX-Exporte für alle Kandidaten bestehen, ist nicht geprüft. Die Alternative ist ONNX Runtime mit `tokenizers` direkt [A].
- **Präfixe:** e5 verlangt „query: “ bzw. „passage: “ vor dem Text [P\*]. Das gehört in den Code der Einbettung, nicht in den Suchtext.
- **Nicht gemessen:** keines der Modelle an deutschen Kurzanfragen. Zahlen für e5-small und e5-base auf derselben Skala fehlen. Die Wahl trifft das Set (F2).

### 3.5 STAC API

- **Collection Search:** Reife „Candidate“, Konformität v1.0.0. Pflicht sind `bbox`, `datetime` und `limit`; `q`, Filter (CQL2) und Sortierung sind optional [P\*].
- **Free-text Search:** Reife „Proposal“ [P\*]. Zwei Stufen:
  - einfach: Kommas trennen ODER-Begriffe (`q=EO,Earth Observation`);
  - erweitert: Phrasen in Anführungszeichen, `AND`, `OR`, Klammern, `+` und `-`.
  - Eine Implementierung wählt eine der beiden; welche Felder durchsucht werden, bleibt ihr überlassen [P\*].
- **Folge [A]:** Die Extension beschreibt eine Bool'sche Suche. Eine Hybrid-Suche kann sie nur so weit erfüllen, wie sie Ergebnisse mit allen Wörtern zurückgibt; sie gibt zusätzlich Treffer ohne gemeinsames Wort. Wegen der Reife „Proposal“ und dieser Abweichung erklärt die Landing Page die Free-text-Konformität nicht (§4.5).
- **stac-fastapi-pgstac:** Collection Search mit Free-text seit 4.0.0, `q` als Zeichenkette seit 6.0.0 [P\*]. Die Version im Repo (6.4.1) hat beides, schaltet es aber nicht ein (`_ENABLED_EXTENSIONS`) [P].

### 3.6 Vorarbeiten

- **Development Seed, `stac-semantic-search`:** natürlichsprachige Suche über STAC-Collections mit Sentence-Transformers und einer Vektordatenbank, „very early stages“ [P\*].
- **Development Seed, `stac-fastapi-collection-discovery`:** Prototyp, der eine Anfrage per LLM in Thema, Ort und Zeit zerlegt, den Ort geokodiert und neu rankt [S]. Das ist Option 2 von F8 mit einem LLM.
- **NASA:** Arbeiten zur Suche nach Erdbeobachtungsdaten kombinieren BM25, ein dichtes Modell und LLM-Reranking [S]. Ein produktiver Endpunkt mit Embedding-Suche im CMR wurde nicht gefunden.
- **Google Dataset Search:** sammelt schema.org-Metadaten ein [S]; das passt zu JSON-LD und Sitemap in M5, nicht zur Rangfolge.

### 3.7 Bewertung mit wenigen Fragen

- **Maße:** nDCG@k für gestufte Relevanz, Recall@k, MRR [A]. `ranx` (MIT) rechnet sie, dazu RRF und gepaarte Signifikanztests [P\*]; `pytrec_eval` (MIT) bindet `trec_eval` an [P\*].
- **Fragen ohne richtige Antwort:** Standardmaße werten sie mit null oder lassen sie weg [A]. Sie werden deshalb getrennt gezählt (§8.1).
- **Größe:** Ältere Arbeiten nennen 25 Fragen als Untergrenze und 50 als besser; 50 gelten als zu klein für feine Unterschiede [S]. Mit 50 Fragen zeigt das Set große Unterschiede und Rückfälle einzelner Fragen, keine Unterschiede von wenigen Prozent [A]. Vergleiche zweier Varianten laufen deshalb mit gepaartem Test (§8.1).

### 3.8 Gehostete Embedding-Dienste

- **Preise** laut Drittseiten zwischen 0,02 und 0,13 USD je Million Token (OpenAI, Voyage, Mistral, Cohere) [S]. Der Katalog kostete einmalig weniger als einen Dollar [A]; die Kosten sind kein Argument.
- **Dagegen [A]:** Jede Suchanfrage ginge an einen fremden Dienst, mit einem Schlüssel als Secret, an `gateway` vorbei oder mit einer neuen Ausnahme darin, und mit Abhängigkeit von Verfügbarkeit und Modellversion des Anbieters. EU-Regionen wurden nicht geprüft.

---

## 4. Bausteine

Jeder Baustein hat eine Empfehlung [A]; die Gesamtoptionen stehen in §5.

### 4.1 Was durchsucht wird: der Suchtext je Datensatz

Der Architekturplan nennt Titel, Beschreibung, Schlagworte, Variablen und Bänder, Plattform und Instrument sowie kuratierte Synonyme (5.3). Vorschlag für den Text, aus dem beide Arme lesen:

| Teil | Gewicht im Volltext | Quelle | Beispiel |
|---|---|---|---|
| Kennung, Titel, Schlagworte | A | Registry | `swissalti3d`, „swissALTI3D“, `elevation`, `dtm` |
| Beschreibung | B | Registry bzw. Quelle | „digital terrain model of Switzerland and Liechtenstein …“ |
| Bänder mit Namen, Beschreibung und Einheit | C | Registry (`band_units` und Bandnamen) | „elevation · m“ |
| Namen der angebotenen Operatoren und Quick processings | C | Operator-Registry über die Capabilities (B10), `index_presets` | „slope, aspect, hillshade“ (mit `terrain`), „NDVI“ |
| Datentyp-Klasse, Anbieter, Zugang | C | Registry | „static raster“, „swisstopo“, „free account required“ |
| Ortsbegriffe aus der Ausdehnung | B | beim Laden abgeleitet (F8) | „Switzerland, Schweiz, Liechtenstein“; bei globalen Datensätzen „global, weltweit“ |

- Operatoren und Quick processings im Text machen Fragen wie „Hangneigung“ oder „NDVI“ beantwortbar. Sie folgen den Capabilities: Was ein Datensatz nicht kann, steht nicht in seinem Text (§2 Punkt 7 des M5-Plans: „was nicht geht, erscheint nicht“).
- Die Texte aus Harvest-Quellen bleiben in ihrer Sprache. Englische Titel und Beschreibungen ergänzt das Review, wo sie fehlen (Weitergabe an `adr/0025`).
- **Empfehlung:** dieser Text, ein Mal je Datensatz gebaut, mit einem Prüfwert (Hash) über Text und Modellkennung.

### 4.2 Lexikalischer Arm

- **Sprachen:** Eine Anfrage hat keine Sprachangabe, und eine Erkennung bei zwei bis sechs Wörtern ist unsicher [A]. Deshalb sucht der Arm in drei Konfigurationen zugleich: `simple` (Kennungen, Namen, Abkürzungen wie „S2“, „DGM“), `german` und `english`. Die drei Anfragen werden mit ODER verbunden.
- **`unaccent`** gleicht Umlaute und Akzente an („Höhe“ findet „Hohe“, „Schnee“ bleibt „Schnee“).
- **Komposita:** Der deutsche Snowball-Stemmer zerlegt keine Komposita, und Wörterbücher mit Zerlegung sind nicht installiert (§3.3). „Höhenmodell“ findet „Modell“ nicht. Das Glossar fängt die wichtigen Fälle ab; der Vektorarm den Rest.
- **Tippfehler:** Trigramme (`pg_trgm`) über Kennung, Titel und Schlagworte, als eigene Rangliste in der Fusion. „Sentinal 2“ und „Worldcovr“ finden so ihren Datensatz.
- **Glossar:** eine kuratierte Liste gleichbedeutender Begriffe in Deutsch und Englisch, als YAML in `catalog` (B13, Review über Git). Beispiel zweier Gruppen: „Höhenmodell, elevation model, DEM“ (allgemein) und „Geländemodell, DGM, DTM, digital terrain model, bare-earth model“ (nur Gelände ohne Bewuchs und Bauten). Steht ein Begriff der Gruppe in der Anfrage, sucht der lexikalische Arm auch nach den anderen. Der Vektorarm bekommt die Anfrage unverändert.
  - Das Glossar liegt in der Anwendung, nicht als Thesaurus-Datei im Server von Postgres. Ein verwaltetes Postgres in der Cloud erlaubt keine eigenen Dateien im Verzeichnis `tsearch_data` [A].
  - Eine Gruppe darf keine Begriffe enthalten, die nur ähnlich sind („DSM“ ist nicht „DTM“; das Set prüft genau das mit Q11 und Q12).
- **Rang im Arm:** `ts_rank_cd` mit den Gewichten aus §4.1. Für die Fusion zählt nur die Reihenfolge, nicht der Wert.

### 4.3 Vektorarm

- **Modell:** mehrsprachig, offene Lizenz (MIT oder Apache-2.0; nicht „nicht kommerziell“), klein genug für die CPU im Prozess `api`. Die Vorauswahl steht in §3.4; ausgewählt wird per Set (F2). Präfixe wie „query: “ bei e5 setzt der Code der Einbettung, nicht der Suchtext.
- **Größe (F2, Bedingung b):** Kandidaten höchstens bis zur Größe von multilingual-e5-base (278 Mio. Parameter), bevorzugt int8. Damit bleiben aus §3.4 multilingual-e5-small und -base sowie zum Vergleich die beiden paraphrase-Modelle; bge-m3, Qwen3, gte-multilingual-base und die großen e5 fallen weg. Der PR der Umsetzung nennt den gemessenen Speicher je Prozess `api`.
- **Ort der Rechnung:** Die Anfrage wird im Prozess `api` eingebettet (ONNX Runtime, CPU). Die Texte der Datensätze werden beim Laden des Katalogs eingebettet (§4.6).
  - **Nur im Image von `api` (F2, Bedingung a):** Heute bauen alle Dienste das Ziel `app`, und der Runner baut darauf auf (`backend/Dockerfile`, `FROM app AS runner`) [P]. Die Modelldateien kommen deshalb in eine eigene Stufe über `app`, die nur `api` nutzt; der Runner bleibt ohne Modell. `catalog-load` rechnet die Embeddings (§4.6) und nutzt dieselbe Stufe wie `api`. Ein Test prüft, dass das Runner-Image keine Modelldatei enthält. **Bestätigt von Otto am 06.11.2026.**
  - Die Modelldateien liegen im Image; der Pfad kommt aus der Konfiguration (`EARTHX_…`, Name in der Umsetzung). Zur Laufzeit gibt es keinen Abruf aus dem Netz, also nichts, was an `gateway` vorbei ginge.
  - Woher die Dateien beim Bau des Images kommen (Hugging Face, Revision und Prüfsumme festgeschrieben), legt die Umsetzung fest. Hugging Face ist aus der Cloud-Sitzung gesperrt [M].
- **Vergleich im Prozess `api`, ohne pgvector (F3 = 2):** Die Vektoren liegen als Spalte (z. B. `real[]`) in der Tabelle des Suchindex. Eine SQL-Abfrage liefert die Datensätze, die die harten Filter bestehen, mit ihren Vektoren; `api` vergleicht exakt (Kosinus über normierte Vektoren, numpy). Bei bis zu einigen Tausend Zeilen ist das schnell genug [A, §3.2]. Exakt heißt auch: Filter und Vektor vertragen sich ohne die Fallen gefilterter ANN-Suche. pgvector mit Index (HNSW) kommt erst, wenn die Menge einen Index verlangt; die Spalte lässt sich dann in `vector` umwandeln, ohne die Embeddings neu zu rechnen.
- **Mindestähnlichkeit:** RRF hat keinen absoluten Wert; der Vektorarm liefert sonst immer einen „nächsten“ Datensatz, auch zu „Bevölkerungsdichte“. Deshalb zählt im Vektorarm nur, was über einer Schwelle liegt. Die Schwelle hängt vom Modell ab und wird am Set festgelegt (Negativfragen Q47–Q50).

### 4.4 Fusion und Filter

- **RRF:** `score(d) = Σ 1 / (k + rang_i(d))` über die Arme Volltext, Trigramm und Vektor, k = 60 (§3.1). Ein Datensatz, den kein Arm liefert, erscheint nicht. Volltext und Trigramm ranken in SQL, der Vektorarm in `api`; die Fusion rechnet `api`.
- **Harte Filter vor der Fusion** (alle Arme sehen nur, was passt):
  - **Raum:** Die Abdeckung des Datensatzes schneidet die AOI. Wo es Footprints gibt (materialisierte Items, `LOCAL_SQL`), zählen die Footprints; sonst die Bbox der Collection. Die Bbox allein wäre bei regionalen Datensätzen zu grob: Die Bbox der Schweiz reicht bis über 10° O nach Tirol hinein [A].
  - **Zeit:** Die zeitliche Ausdehnung überlappt den Zeitraum; ein offenes Ende heißt heute. Datensätze ohne Zeitachse (`time_range = false`) fallen nie wegen eines Zeitraums heraus. Das ist dieselbe Regel wie bei `/coverage` und `/stac/search` (`architekturplan.md` 5.1); die Antwort nennt den ignorierten Filter in `ignored_filters`.
  - **Zugang und Lizenz:** B11-Stufe und `access.account` als Filter, sobald die Felder da sind (YAML-Lader, `adr/0027` §6.1). In M5 nur auf Wunsch über die Schnittstelle, nicht in der Oberfläche.
  - **Prototyp:** Ein `proto-`-Datensatz ist nur dort im Index, wo er geladen ist (`adr/0024` R5, R6). In der veröffentlichten Version gibt es ihn also nicht.
- **Kein Rangfaktor** aus Health, Beliebtheit oder Datum. Ein Datensatz mit `broken` bleibt in der Liste und zeigt seinen Status (Prinzip 11); die Suche versteckt nichts.
- **Gleichstand:** nach Titel, dann Kennung, damit dieselbe Anfrage immer dieselbe Liste gibt.
- **Größe der Antwort:** höchstens 20 Treffer je Seite, Blättern über die Paginierung der STAC-API.

### 4.5 Schnittstelle

- **Form:** STAC API Collection Search mit dem Parameter `q` auf `/stac/collections` (§3.5). Damit können QGIS, Python-Clients und später der Chatbot dieselbe Suche nutzen (Prinzipien 6, 7).
- **Semantik von `q`:** Die Free-text-Extension beschreibt eine Bool'sche Textsuche und ist erst ein „Proposal“ (§3.5). Die Hybrid-Suche rankt dagegen auch Treffer ohne gemeinsames Wort. Die Landing Page erklärt deshalb Collection Search, aber nicht Free-text (wie `adr/0005` Regel VI: nur, was erfüllt ist); was `q` hier heißt, steht in der Beschreibung der Route.
- **Nicht über pgstac:** pgstac sucht `q` fest auf Englisch und ohne Index (§3.3). Die Route reicht `q` nicht an pgstac durch, sondern fragt den eigenen Index (§4.6).
- **AOI nur im Body:** Eine Fläche als `bbox` oder `intersects` in der URL wäre eine AOI in der URL (M5-Plan §9). Die Oberfläche sucht mit Fläche deshalb nur per `POST`. `GET` nimmt `bbox`, weil Collection Search es verlangt (§3.5); das nutzen fremde Clients, nie das eigene Frontend. Der Query-String erscheint in keinem Log [P].
- **Ohne `q`:** Die Antwort ist die heutige Liste aller Collections, in fester Reihenfolge; ohne Text gibt es keinen Rang.
- **Kosten:** ein Embedding der Anfrage und eine SQL-Abfrage mit drei Teilabfragen (§9).

### 4.6 Wann der Index entsteht

- **Beim Laden des Katalogs** (`catalog-load`, heute aus der Registry, später aus dem YAML-Lader, B13): Für jeden Datensatz wird der Suchtext gebaut (§4.1), der `tsvector` gerechnet und, wenn sich der Prüfwert geändert hat, das Embedding. Gespeichert wird beides in einer eigenen Tabelle neben pgstac mit Modellkennung und Prüfwert (`architekturplan.md` 10 nennt sie `dataset_embedding`); das Embedding als gewöhnliche Spalte, nicht als `vector` (F3).
- **Nicht im Harvester:** Die Stufe „Enrich“ des Architekturplans (4.3) nennt das Embedding. Würde der Harvester es rechnen, gäbe es zwei Orte mit Modell und zwei Wahrheiten. Der Harvester liefert Texte, der Lader rechnet (Weitergabe an `adr/0025`).
- **Modellwechsel:** neue Modellkennung, alle Embeddings neu; der Lader prüft beim Start, dass Index und Modell zusammenpassen, sonst Startfehler im Prozess `api` (wie die Startprüfungen der Registry).

---

## 5. Optionen

| Option | Lexikalisch | Vektor | Wo | Erfüllt | Verfehlt |
|---|---|---|---|---|---|
| **A** Hybrid in Postgres, Modell lokal | Volltext, Trigramm, Glossar | pgvector, Modell im `api` (ONNX) | eine Datenbank | K1–K11 | braucht pgvector im Image (F3), Modell im Image (Größe, RAM) |
| **B** Gestuft: erst nur lexikalisch mit Glossar, Vektor erst, wenn das Set es verlangt | wie A | später | eine Datenbank | K3–K11, kein Modell und kein Image-Wechsel in M5 | K1 nur so weit, wie das Glossar reicht; Sprachwechsel ohne gemeinsames Wort fällt aus |
| **C** Hybrid in Postgres, Embeddings über einen gehosteten Dienst | wie A | pgvector, Anfrage an fremden Dienst | Datenbank + Dienst | K1, K2, K3, K7 | K4 (Anfragen verlassen die Plattform, Schlüssel nötig), K5, K6 (kostenpflichtig) |
| **D** Eigener Suchdienst (OpenSearch, Meilisearch o. Ä.) | BM25, Sprachanalyse | eingebaut | zweiter Dienst | K1, K2, K7 | K3; Betrieb, Synchronisation mit pgstac |
| **E** Suche im Client wie M3-10 | Wortsuche im Browser | — | Browser | K5, K6 | K1, K2, K8 (nicht API-first), K7 |

Bewertung [A]:

- **E** scheidet aus: Die Suche muss über die API gehen, weil Chatbot und Python-Client sie nutzen (Prinzip 7).
- **D** scheidet nach `architekturplan.md` 0 Punkt 9 aus, solange die Mengen es nicht erzwingen. Bei einigen Tausend Datensätzen tun sie das nicht.
- **C** verletzt K4 und K6: Jede Anfrage ginge an einen Anbieter, mit Schlüssel als Secret und einem kostenpflichtigen Dienst (§3.8). Die Beträge wären klein; das Argument ist der Abfluss jeder Anfrage und die Abhängigkeit vom Anbieter.
- **B** ist der kleinste Schritt und fände die meisten Fragen des Sets über Glossar und Schlagworte. Es verschiebt aber die Arbeit, die das Set ohnehin verlangt (Sprachwechsel ohne gemeinsames Wort, z. B. Q16, Q18, Q37–Q39), und die Plattform bekäme in M5 keine Antwort auf den Spike aus 15.2.
- **A** ist der geplante Weg und erfüllt alle Kriterien. Sein Preis sind pgvector im Image und ein Modell im Image.

**Nach Ottos Antworten (06.11.2026):** A gilt (F1), aber ohne pgvector in M5 (F3 = 2): Der Vektorvergleich liegt im Prozess `api`, das Postgres-Image bleibt. Das Modell liegt nur im Image von `api` (F2).

---

## 6. Empfehlung

**Entschieden (Otto, 06.11.2026): Option A** (F1), mit dem Vektorvergleich im Prozess `api` statt in pgvector (F3 = 2) und einem Modell bis zur Größe von e5-base (F2). Gebaut in dieser Reihenfolge, damit jede Stufe für sich am Set gemessen wird [A]:

1. Bewertungs-Set als Fixture und Test (§8.4); Messung der heutigen Lage (keine Suche) als Nullpunkt.
2. Lexikalischer Arm mit Glossar (§4.2). Messung am Set.
3. Vektorarm mit dem ausgewählten Modell (§4.3) und RRF (§4.4). Messung am Set, je Arm und zusammen.
4. Schnittstelle (§4.5) und Feld im „Data catalogue“ (§7).

Liegt nach Schritt 2 das Set schon über der Grenze aus F5, entscheidet Otto, ob Schritt 3 in M5 kommt oder später (dann gilt B). Der Vergleich der Arme beantwortet den Spike aus `architekturplan.md` 15.2 mit Zahlen.

---

## 7. Oberfläche: Suche im „Data catalogue“

Der „Data catalogue“ ist ein **größeres Fenster über der Karte** mit allen Datensätzen, gruppiert, zum Hinzufügen ins Control Panel. Es öffnet über ein Symbol in der linken Leiste und schließt mit dem roten x; es ist kein linkes Panel (UI-05, M5-Plan §2 Punkt 8, §6.1; Nachtrag Otto zu UI-05 F5, 06.11.2026). Die Suche sitzt darin. Vorschlag [A], mit den Regeln aus `docs/ui/leitfaden.md`:

- **Ort:** Suchfeld und AOI-Schalter **oben im Fenster**, unter dem Kopf mit Titel und rotem x, über der Liste. Bauteil wie die Ortssuche (`ClearableInput`), `autoComplete="off"` (Leitfaden §8b). Platzhalter „Search datasets“. Kein Satz darunter; was die Suche kann (Deutsch und Englisch, Namen, Themen), steht hinter einem (i) neben dem Feld (Leitfaden §4).
- **Leeres Feld:** Der Katalog zeigt seine Gruppen wie in UI-05. Die Suche ändert daran nichts.
- **Mit Text:** eine gerankte Liste statt der Gruppen. Jede Zeile ist **dieselbe Zeile** wie in der Gruppenansicht (Name, Marken, Hinzufügen bzw. Entfernen, Angaben aufklappbar); dazu der Name der Gruppe als kleine Marke. Keine Punktzahl, kein Rang als Zahl. Kein Tooltip am Namen (Leitfaden §4: keine Tooltips an Namen).
- **Ohne Treffer:** ein Leerzustand, der sagt, was zu tun ist (Leitfaden §4), etwa „No matching datasets — try other words“, mit eingeschaltetem AOI-Filter „… or include datasets outside the AOI“. Fragen ohne passenden Datensatz bekommen so eine ehrliche Antwort statt eines nächstbesten Treffers (K9).
- **AOI:** ein Schalter oben im Fenster, neben oder unter dem Suchfeld: nur Datensätze, die die AOI berühren. Der Name kommt zuerst in den Leitfaden (§2) und darf nicht mit „Filter within AOI only“ verwechselbar sein, das in „Advanced search“ etwas anderes heißt. Gesperrt ohne AOI, Grund im Tooltip mit dem vorhandenen Text „Draw an AOI to use this filter“ (`LOCK_NEEDS_AOI`, `frontend/src/aoiFilter.ts`). Vorgabe: F6. Er wirkt auch ohne Text auf die Gruppenansicht. Das ist die „AOI-zuerst-Suche“ aus dem Projektplan (M5, Funktionen). Leitfaden §7 erlaubt heute genau einen Schalter (`role="switch"` nur im Filter der AOI); ein zweiter braucht einen Nachtrag dort.
- **Zeitraum:** kein Filter im Katalog. Die Daten des Control Panels gelten je Datensatz und sind auf dessen Zeitraum begrenzt (UI-05); ein zweiter Zeitraum im Katalog wäre doppelt [A]. Die Schnittstelle kann ihn trotzdem (§4.4), für Chatbot und Python-Client.
- **Marken:** „Prototype“ (`adr/0024` R8) und der Hinweis für Konto-Quellen (`adr/0027` §4.1 und F2: Link „kostenloses Konto nötig“; Form und Begriff legt UI-05 bzw. der Leitfaden fest) stehen in der Trefferzeile wie in der Gruppenansicht. „Last checked“ steht in den Angaben, sobald es Health-Checks gibt.
- **Verhalten:** Die Anfrage geht nach einer kurzen Pause im Tippen an die API (keine Taste nötig), ab zwei Zeichen. Eine ältere Antwort überschreibt nie eine neuere. Fehler der API: der Fehler sichtbar mit „Retry“ (Leitfaden §2), die Gruppenansicht bleibt nutzbar.
- **Merken:** Der Suchtext bleibt für die Sitzung stehen wie die Einstellungen von „Advanced search“, nicht im Browserspeicher und nicht im Permalink (wie DS-03c, Log 06.11.2026).
- **Schließen und Leeren:** Das Fenster schließt mit dem roten x (Leitfaden §5, `CloseButton`); ein zweiter Klick auf das Symbol der Leiste schließt es ebenfalls, wenn UI-05 das so festlegt. Esc schließt nichts und leert das Feld nicht (Leitfaden §5); geleert wird nur mit „Clear“ von `ClearableInput`. Ob ein Klick daneben schließt, legt UI-05 fest (Leitfaden §5 kennt beides). Suchtext und Schalter bleiben beim Schließen und Wiederöffnen für die Sitzung stehen.
- **Schmale Fenster:** Das Fenster deckt die Karte; Suchfeld und Schalter bleiben oben stehen, die Liste scrollt.

**Was das für UI-05 heißt (Weitergabe):**

1. Der obere Bereich des Fensters „Data catalogue“ (unter Titel und rotem x) lässt sich später um das Suchfeld und den AOI-Schalter ergänzen, ohne Umbau. Keine sichtbar leere Fläche; UI-05 baut beides nicht.
2. Die Zeile eines Datensatzes ist ein eigenes Bauteil, das auch ohne Gruppe stehen kann (mit der Gruppe als Marke).
3. Keine Pflicht für UI-05: Dass die Gruppenansicht auf eine Teilmenge eingeschränkt werden kann (AOI-Schalter ohne Text), baut die Aufgabe der Suche in Fassung 3.
4. Die Gruppe kommt aus einem Registry-Feld (UI-05 legt es fest). Dieses ADR schlägt kein eigenes vor; die Suche liest das Feld nur für die Marke.

Läuft UI-05 anders, stimmt sich ab, wer später holt (wie M5-Plan §6.2 für Registry-Felder).

---

## 8. Bewertungs-Set

### 8.1 Regeln

- **Form:** je Frage eine Kennung, die Sprache, der Text, ein optionaler Kontext und die Erwartung. Als Fixture später eine YAML-Datei (§8.4).
- **Noten je Datensatz:** **2** = gesucht (soll vorne stehen), **1** = passend (darf vorkommen), **nie** = darf nicht vorkommen (prüft einen harten Filter). Alle übrigen Datensätze haben Note 0.
- **Kontext:** eine AOI als **grobe Box in ganzen Grad**, nach einer Region benannt (keine Fläche eines Nutzers, keine genaue Grenze; `CLAUDE.md`), oder ein Zeitraum.
- **Ruhen:** Eine Frage ist aktiv, sobald mindestens ein Datensatz mit Note 2 im Katalog steht und ihre Voraussetzung erfüllt ist. Gemessen wird nur gegen vorhandene Datensätze. Fragen ohne Note 2 (Negativ- und reine Filterfragen) sind immer aktiv. So läuft das Set ab heute und wächst mit dem Katalog.
- **Keine Prototyp-Datensätze** (`adr/0024` R7). Konto-Quellen dürfen vorkommen; sie sind gewöhnliche Katalogeinträge.
- **Maße:**
  - **Recall@5:** Anteil der Datensätze mit Note 2 unter den ersten fünf Treffern, gemittelt über die aktiven Fragen mit Note 2.
  - **MRR@10:** Kehrwert des Rangs des ersten Datensatzes mit Note 2 unter den ersten zehn, gemittelt.
  - **nDCG@10** mit den Gewinnen 2 und 1: nur berichtet, ohne Grenze.
  - **Filterfragen:** bestanden, wenn kein Datensatz mit „nie“ in der Liste steht, auf keinem Rang.
  - **Negativfragen:** bestanden, wenn die Liste leer ist.
  - Alle Maße getrennt für Deutsch, Englisch und zusammen. In die Maße **je Sprache** zählen nur Fragen mit mindestens einem Wort der Sprache; reine Namen und Kürzel (Q01, Q03, Q04, Q05, Q07, Q40, Q42, Q43, Q44, Q46) zählen nur im Gesamtmaß.
- **Bestehen:** Grenzen in F5. Vorschlag: Recall@5 ≥ 0,9 und MRR@10 ≥ 0,8, **je Sprache**; alle Filterfragen; drei von vier Negativfragen.
- **Vergleich zweier Varianten** (Modelle, Arme, Parameter): gepaart über dieselben Fragen, mit Test und Konfidenzintervall (`ranx`). Mit 50 Fragen zeigt das große Unterschiede und Rückfälle einzelner Fragen, keine feinen (§3.7).
- **Änderung:** Neue Fragen und geänderte Noten kommen per PR mit Begründung; Otto gibt sie frei. Eine Frage verschwindet nicht, weil sie scheitert.

### 8.2 Datensätze des Sets

Inhalt sind die Quellen aus `adr/0023` §11 (WorldCover, swissALTI3D, BEV ALS-DGM 1 m, die Meteorologie mit MeteoSchweiz-Klimagittern und DWD HYRAS, der Geländeoperator) und die Datensätze, die es schon gibt oder die M5 sicher bringt. Dazu je ein Konto-Eintrag als Katalogeintrag nach `adr/0027` W0.

| Kürzel | Datensatz | Kennung | im Katalog ab |
|---|---|---|---|
| S2 | Sentinel-2 L2A | `sentinel-2-c1-l2a` | heute |
| DEM | Copernicus DEM GLO-30 (Oberflächenmodell, DSM) | `cop-dem-glo-30` | heute |
| S1 | Sentinel-1 GRD | `sentinel-1-grd` (vorläufig, wie Earth Search) | DS-04 |
| WC20 | ESA WorldCover 2020 | `esa-worldcover-2020` | M5-07 |
| WC21 | ESA WorldCover 2021 | `esa-worldcover-2021` | M5-07 |
| ALTI | swisstopo swissALTI3D (Geländemodell, DTM, CH und FL) | `swissalti3d` (vorläufig, `adr/0023` §8.3) | M5-08 |
| BEV | BEV ALS-DGM 1 m (Geländemodell, DTM, AT) | `bev-als-dgm` (vorläufig, `adr/0023` §8.3) | M5-09 |
| MCH | MeteoSchweiz, räumliche Klimaanalysen 1 km (`ch.meteoschweiz.ogd-surface-derived-grid`: Niederschlag, Temperatur, relative Sonnenscheindauer) | offen | M5-11 |
| HYR | DWD HYRAS-DE (Niederschlag 1 km, Temperatur 5 km, täglich) | offen | nach M5-11, keine Aufgabe in M5 |
| CLC | CORINE Land Cover (CLMS) als Katalogeintrag mit `access.account = free_account` | offen | erster W0-Eintrag (`adr/0027`) |
| LS | Landsat Collection 2 Level-2 als Katalogeintrag mit `access.account = requester_pays` | offen | erster W0-Eintrag (`adr/0027`) |

Fragen zum Geländeoperator setzen voraus, dass er gebaut ist (M5-10), weil erst dann „slope, aspect, hillshade“ im Suchtext der Höhenmodelle stehen (§4.1).

### 8.3 Fragen

25 deutsch, 25 englisch, dazu Q51 (Nachtrag M5-22c). Art: **N** Name, **T** Thema, **X** Region im Text, **R** Region als AOI, **Z** Zeit, **F** Fähigkeit, **S** Abkürzung oder Tippfehler, **K** Konto-Eintrag, **0** ohne passenden Datensatz.

| ID | Spr. | Frage | Kontext | Note 2 | Note 1 | nie | Art |
|---|---|---|---|---|---|---|---|
| Q01 | en | Sentinel-2 | — | S2 | — | — | N |
| Q02 | de | Sentinel-2 Bodenreflexion | — | S2 | — | — | N |
| Q03 | en | Copernicus DEM | — | DEM | — | — | N |
| Q04 | de | swissALTI3D | — | ALTI | — | — | N |
| Q05 | en | ESA WorldCover | — | WC20, WC21 | — | — | N |
| Q06 | de | BEV Höhenraster 1 m | — | BEV | ALTI | — | N |
| Q07 | en | Sentinel-1 GRD | — | S1 | — | — | N |
| Q08 | de | MeteoSchweiz Klimagitter | — | MCH | — | — | N |
| Q09 | de | Höhenmodell | — | DEM, ALTI, BEV | — | — | T |
| Q10 | en | elevation model | — | DEM, ALTI, BEV | — | — | T |
| Q11 | en | digital terrain model bare earth | — | ALTI, BEV | DEM | — | T |
| Q12 | de | digitales Oberflächenmodell | — | DEM | ALTI, BEV | — | T |
| Q13 | de | Landbedeckung | — | WC20, WC21, CLC | — | — | T |
| Q14 | en | land cover classification | — | WC20, WC21, CLC | — | — | T |
| Q15 | en | multispectral optical imagery | — | S2 | LS | — | T |
| Q16 | de | Satellitenbilder in Echtfarben | — | S2 | LS | — | T |
| Q17 | en | radar backscatter | — | S1 | — | — | T |
| Q18 | de | Radarbilder bei Bewölkung | — | S1 | — | — | T |
| Q19 | de | Niederschlag | — | MCH, HYR | — | — | T |
| Q20 | en | precipitation grid | — | MCH, HYR | — | — | T |
| Q21 | en | daily air temperature | — | MCH, HYR | — | — | T |
| Q22 | de | Sonnenscheindauer | — | MCH | — | — | T |
| Q23 | de | Höhenmodell Österreich | — | BEV | DEM | — | X |
| Q24 | en | terrain model Switzerland | — | ALTI | DEM | — | X |
| Q25 | en | rainfall Germany | — | HYR | — | — | X |
| Q26 | de | Höhenmodell | AOI „Österreich Mitte“ 14–15° O, 47–48° N | BEV | DEM | ALTI | R |
| Q27 | en | elevation | AOI „Western Switzerland“ 7–8° O, 46–47° N | ALTI | DEM | BEV | R |
| Q28 | en | land cover | AOI „Kenya“ 36–37° O, 1° S–0° | WC20, WC21 | — | ALTI, BEV, MCH, HYR, CLC | R |
| Q29 | de | Niederschlag | AOI wie Q26 | — | — | MCH | R |
| Q30 | de | Landbedeckung 2021 | — | WC21 | WC20 | — | Z |
| Q31 | en | land cover 2020 | — | WC20 | WC21 | — | Z |
| Q32 | en | radar | Zeitraum 2000–2005 | — | DEM | S1 | Z |
| Q33 | de | Höhenmodell | Zeitraum 2024 | DEM, ALTI, BEV | — | — | Z |
| Q34 | de | Hangneigung berechnen | M5-10 gebaut | DEM, ALTI, BEV | — | — | F |
| Q35 | en | hillshade | M5-10 gebaut | DEM, ALTI, BEV | — | — | F |
| Q36 | en | NDVI | — | S2 | — | — | F |
| Q37 | de | Vegetationsindex | — | S2 | — | — | F |
| Q38 | de | Schneebedeckung | — | S2 | WC20, WC21 | — | F |
| Q39 | de | Wasserflächen erkennen | — | S2 | WC20, WC21, S1 | — | F |
| Q40 | en | S2 L2A | — | S2 | — | — | S |
| Q41 | de | DGM 1m | — | BEV | ALTI | — | S |
| Q42 | en | Sentinal 2 | — | S2 | — | — | S |
| Q43 | de | Worldcovr | — | WC20, WC21 | — | — | S |
| Q44 | en | SAR | — | S1 | — | — | S |
| Q45 | en | CORINE land cover | — | CLC | WC20, WC21 | — | K |
| Q46 | de | Landsat | — | LS | S2 | — | K |
| Q47 | de | Luftqualität Stickstoffdioxid | — | — | — | — | 0 |
| Q48 | en | ocean salinity | — | — | — | — | 0 |
| Q49 | de | Bevölkerungsdichte | — | — | — | — | 0 |
| Q50 | en | hourly weather forecast | — | — | — | — | 0 |
| Q51 | en | Sentinel-3 | — | — | — | — | 0 |

Hinweise zu einzelnen Fragen:

- **Q11, Q12:** prüfen, dass DSM und DTM nicht gleichgesetzt werden. Der Copernicus DEM ist ein Oberflächenmodell; swissALTI3D und BEV sind Geländemodelle (`adr/0023` §3.1, §4.2).
- **Q23–Q25:** Region nur im Text, ohne AOI. Sie hängen an den Ortsbegriffen im Suchtext (§4.1, F8).
- **Q26, Q27:** Q26 liegt ganz in Österreich und östlich der Bbox der Schweiz (bis 10,5° O). Q27 liegt westlich von Österreich (ab 9,5° O); am Südrand streift die Box Italien, was für die Frage nichts ändert. Beide prüfen den Raumfilter, nicht die Grenze von Bbox und Footprint.
- **Q28:** WorldCover ist global, CORINE nur Europa (`nie`).
- **Q29:** Niederschlag in der Mitte Österreichs: MeteoSchweiz deckt es nicht ab; GeoSphere ist nicht im Katalog. Erwartet ist eine Liste ohne MCH. Ob das Gitter von HYRAS über Deutschland hinausreicht (Einzugsgebiete), ist nicht belegt; HYR kommt erst nach dieser Prüfung als „nie“ dazu. Eine erste Fassung mit einer Box in Tirol hätte deutsches Gebiet (Werdenfelser Land) geschnitten.
- **Q32:** Sentinel-1 beginnt 2014 (`nie`). Der Copernicus DEM stammt aus Radar (TanDEM-X) und hat keine Zeitachse; er darf erscheinen.
- **Q33:** Datensätze ohne Zeitachse fallen nicht wegen eines Zeitraums heraus (§4.4).
- **Q38, Q39:** Quick processings (NDSI, NDWI) stehen im Suchtext von Sentinel-2 (§4.1).
- **Q42, Q43:** Tippfehler; der Trigramm-Arm muss sie finden.
- **Q47–Q50:** Nichts im Katalog passt, je zwei Fragen auf Deutsch und Englisch. Erwartet ist eine leere Liste; dafür braucht der Vektorarm die Mindestähnlichkeit (§4.3).
- **Q51** (Nachtrag M5-22c, Otto 11.11.2026, `plans/m5/m5-22-suche-lexikalisch.md` §11.7, §12): ein bekannter Name mit einer Zahl, die kein Datensatz hat. Die Zahl darf nicht wegfallen und den Namen allein Sentinel-1, Sentinel-2 und WorldCover finden lassen. Reiner Name, zählt nur im Gesamtmaß. „Landsat 9“ ist keine eigene Frage: LS enthält Landsat 9 und machte sie zur gesuchten.

### 8.4 Wie das Set läuft

- **Fixture:** die Fragen als YAML unter `backend/tests/fixtures/` und dazu die Embeddings aller Fragen und aller Suchtexte des Katalogs für das gewählte Modell, mit Modellkennung, Revision und dem Prüfwert je Text. Bei rund 50 Fragen und zehn bis zwanzig Datensätzen sind das wenige Hundert Kilobyte [A].
- **Test in der CI:** lädt den Katalog in das Postgres der CI, setzt die Embeddings aus der Fixture statt aus dem Modell und stellt jede aktive Frage. Er berichtet alle Maße und scheitert unter der Grenze aus F5. So läuft das Set ohne Modell und ohne Netz (K5).
- **Frische:** Weicht der Prüfwert eines Suchtextes von dem in der Fixture ab, scheitert der Test mit dem Hinweis, die Embeddings neu zu rechnen. Das geht mit einem Skript unter `scripts/` auf einem Rechner mit Modell (Ottos Rechner oder eine Sitzung mit freigegebenem Host).
- **Echte Anfrage:** Ein zweiter, seltener Lauf rechnet die Embeddings der Fragen mit dem echten Modell und vergleicht sie mit der Fixture (Abweichung durch andere Hardware oder Version). Er gehört zu `tests_live` und läuft nicht in der normalen CI.
- **Bericht:** je Frage Rang der erwarteten Datensätze und Treffer mit „nie“, damit eine Regression einer einzelnen Frage sichtbar wird, auch wenn der Mittelwert hält.

---

## 9. Kosten

Abschätzung [A]; gemessen wird in der Umsetzung.

- **Je Anfrage:** ein Embedding der Anfrage auf der CPU (kleines Modell, wenige Wörter: Millisekunden bis wenige Dutzend Millisekunden), dazu eine SQL-Abfrage mit drei Teilabfragen über höchstens einige Tausend Zeilen. Das liegt weit unter einer Kachel.
- **Beim Laden:** ein Embedding je geändertem Datensatz. Bei Tausend Datensätzen und einem neuen Modell einige Minuten auf der CPU, einmalig.
- **Speicher:** das Modell im Prozess `api` und im Image von `api`. Mit int8 sind die Gewichte rund 0,12 GB (e5-small, 118 Mio. Parameter) bzw. 0,28 GB (e5-base, 278 Mio.), in float32 das Vierfache; dazu kommt der Bedarf der Laufzeit [A, aus §3.4]. Jeder Prozess `api` hält es einmal. Der PR der Umsetzung nennt den gemessenen Wert (F2).
- **Datenbank:** ein Vektor je Datensatz (384 oder 768 Zahlen) als Spalte, dazu ein `tsvector`; bei Tausend Datensätzen wenige Megabyte. Je Anfrage liest `api` die Vektoren der gefilterten Datensätze: bei Tausend Datensätzen und 768 Zahlen rund 3 MB als float32 [A]; wird das spürbar, hält `api` sie im Speicher oder pgvector kommt.
- **Keine laufenden Kosten** für einen fremden Dienst (Option C entfällt).

---

## 10. Sicherheit, Datenschutz, Grenzen

- **Keine AOI in URLs:** Fläche nur im Body (§4.5). Der Query-String wird nicht protokolliert [P]; der Suchtext erscheint auch in keiner anderen Logzeile.
- **Kein Abruf zur Laufzeit:** Das Modell liegt im Image; die Suche ruft nichts nach außen. `gateway` bleibt unberührt.
- **Eingaben:** Länge der Anfrage begrenzt (z. B. 200 Zeichen), Anfrage nur als Parameter an SQL, nie als Text eingesetzt. `websearch_to_tsquery` wirft bei keiner Eingabe einen Syntaxfehler [§3.3].
- **Lizenz des Modells:** nur MIT, Apache-2.0 oder eine gleichwertige offene Lizenz; Eintrag in den Hinweisen zu Dritten. Die Einstufung prüft Otto mit der Wahl (F2).
- **Prototyp und Konto:** wie §4.4 und §7.
- **Grenze:** Die Suche findet Datensätze nach ihrem Text und ihrer Ausdehnung. Sie prüft nicht, ob in der AOI zu einem Zeitpunkt wirklich Szenen liegen; das tun Coverage und Item-Suche.

---

## 11. Fragen an Otto und Antworten

Otto hat am 06.11.2026 alle neun Fragen beantwortet. Die Antworten stehen unter der jeweiligen Frage.

**F1 — Gesamtweg (§5, §6)?**
1. Option A: Hybrid in Postgres mit lokalem Modell, gebaut in vier gemessenen Stufen (§6) **(Empfehlung)**
2. Option B: in M5 nur lexikalisch mit Glossar; Vektor erst, wenn das Set es verlangt
3. Option C: Embeddings über einen gehosteten Dienst

**Antwort F1 (Otto, 06.11.2026): 1, fest.**

**F2 — Embedding-Modell?**
1. Auswahl per Set in der Umsetzung unter den Kandidaten aus §3.4 (offene Lizenz, CPU); das kleinste Modell, das die Grenze aus F5 erreicht, gewinnt; Otto bestätigt Modell und Lizenz im PR **(Empfehlung)**
2. Jetzt multilingual-e5-small festlegen (MIT, kleinster Kandidat)
3. Das größte Modell der Liste, Größe egal

**Antwort F2 (Otto, 06.11.2026): 1, fest, mit zwei Bedingungen:**
- (a) Modelldateien nur im Image von `api`, nicht im Runner-Image (umgesetzt in §4.3). **Bestätigt (Otto, 06.11.2026):** eigene Stufe im `backend/Dockerfile` für `api` und `catalog-load`, Test, dass das Runner-Image kein Modell enthält;
- (b) Kandidaten höchstens bis zur Größe von e5-base, bevorzugt int8; der PR nennt den Speicher je Prozess `api` (§4.3, §9).

**F3 — pgvector in die Datenbank?**
1. Eigenes Postgres-Image (PostGIS mit pgvector aus den Paketquellen von PostgreSQL) für Compose und CI, dazu das Paket im Setup der Cloud-Umgebung; die Änderung an `.github/workflows/ci.yml` erlaubst du hiermit **(Empfehlung)**
2. Ohne pgvector: Vektoren als Spalte, Vergleich im Prozess `api` (numpy), solange es wenige Tausend sind
3. Erst entscheiden, wenn Schritt 2 aus §6 gemessen ist

**Antwort F3 (Otto, 06.11.2026): 2, fest.** Kein pgvector in M5: Vektoren als Spalte, harte Filter in SQL, Vergleich exakt im Prozess `api` (§4.3, §4.4). pgvector erst, wenn die Menge einen Index verlangt. Folge: Nachtrag zu `architekturplan.md` 5.3 und 10 (§12); Postgres-Image und `ci.yml` bleiben unverändert.

**F4 — Bewertungs-Set (§8.3)?**
1. So freigeben; du ergänzt Fragen im PR **(Empfehlung)**
2. Freigeben und Fragen auf Französisch und Italienisch ergänzen (FSDI)
3. Erst überarbeiten (bitte sagen, was)

**Antwort F4 (Otto, 06.11.2026): 1, fest.** Otto ergänzt gegebenenfalls Fragen im PR.

**F5 — Wann besteht das Set (§8.1)?**
1. Recall@5 ≥ 0,9 und MRR@10 ≥ 0,8 je Sprache, alle Filterfragen, drei von vier Negativfragen **(Empfehlung)**
2. Strenger: jede aktive Frage einzeln (alle Datensätze mit Note 2 unter den ersten fünf)
3. In M5 nur berichten, keine Grenze

**Antwort F5 (Otto, 06.11.2026): 1, fest.**

**F6 — AOI im „Data catalogue“ (§7)?**
1. Schalter, Vorgabe aus; an nur auf Klick, dann bleibt er für die Sitzung an **(Empfehlung: beim Zeichnen einer AOI verschwindet so kein Datensatz ohne Zutun, Leitfaden §1 Punkt 5, Prinzip 9)**
2. Schalter, an, sobald eine AOI da ist
3. Kein Schalter: Mit AOI filtert der Katalog immer

**Antwort F6 (Otto, 06.11.2026): 1, fest.** Schalter mit Vorgabe aus.

**F7 — Begriffe beim Onboarding (§4.2)?**
1. Neuer Punkt der Onboarding-Checkliste: Schlagworte in Deutsch und Englisch, neue Fachbegriffe ins Glossar; gilt ab M5-07 **(Empfehlung)**
2. Nur das Glossar pflegen, kein Punkt der Checkliste
3. Keine Pflicht; das Modell soll es richten

**Antwort F7 (Otto, 06.11.2026): 1, fest.** Neuer Punkt der Onboarding-Checkliste ab M5-07 (Folge 9 und 10 in §12).

**F8 — Ortsnamen in der Anfrage (§4.1)?**
1. Ortsbegriffe (Länder, de/en) beim Laden aus der Ausdehnung regionaler Datensätze in den Suchtext; globale bekommen „global, weltweit“ **(Empfehlung)**
2. Zusätzlich Ortsnamen in der Anfrage per Geokodierung in einen Raumfilter übersetzen
3. Keine Ortsbegriffe; Region nur über die AOI

**Antwort F8 (Otto, 06.11.2026): 1, fest.**

**F9 — Schnittstelle (§4.5)?**
1. STAC Collection Search mit `q` auf `/stac/collections`, Fläche nur per `POST`; Konformität nur, soweit erfüllt **(Empfehlung)**
2. Eigene Route außerhalb von `/stac`
3. Beides: STAC-Route und eine schmale eigene Route für die Oberfläche

**Antwort F9 (Otto, 06.11.2026): 1, fest.**

---

## 12. Folgen

Eingabe für Fassung 3 des M5-Plans. Diese Liste legt keine Plan-Dateien an und ändert weder Backlog noch M5-Plan.

1. **Datenbank:** ~~pgvector im Postgres von Compose, CI und Cloud-Umgebung~~ **entfällt (F3 = 2).** Postgres-Image, `docker-compose.yml` (Dienst `postgres`), `.github/workflows/ci.yml` und Cloud-Umgebung bleiben in M5 unverändert. pgvector wird eine eigene Entscheidung, sobald die Menge einen Index verlangt.
2. **`catalog`:** Suchtext (§4.1), Tabelle für `tsvector`, Embedding als Spalte, Modellkennung und Prüfwert (`architekturplan.md` 10), Glossar als YAML, Laden in `catalog-load` (§4.6), Startprüfung Index gegen Modell, exakter Vektorvergleich und RRF im Prozess `api` (§4.3, §4.4). Keine neue Importregel: Modell, ONNX Runtime und numpy sind Bibliotheken ohne Netz.
3. **Modell:** Auswahl per Set (F2) unter Modellen bis zur Größe von e5-base, bevorzugt int8; ONNX-Dateien mit festgeschriebener Revision und Prüfsumme in einer eigenen Stufe des Dockerfiles nur für `api` (und `catalog-load`, §4.3), nicht im Runner-Image, mit Test; Speicher je Prozess `api` im PR; Lizenz in den Hinweisen zu Dritten.
4. **`api`:** Collection Search mit `q` (F9), Fläche per `POST`, `ignored_filters` wie bei `/stac/search`, Konformität nur soweit erfüllt.
5. **Frontend:** Suchfeld und AOI-Schalter im „Data catalogue“ (§7), **nachdem UI-05 gemergt ist**. Neue Begriffe zuerst in den Leitfaden (§2).
6. **Bewertungs-Set:** Fixture, Test, Skript zum Neurechnen, Lauf in `tests_live` (§8.4).
7. **An UI-05:** Der „Data catalogue“ ist ein Fenster über der Karte mit rotem x, geöffnet über ein Symbol der linken Leiste (Nachtrag Otto zu UI-05 F5). Sein oberer Bereich ist für Suchfeld und AOI-Schalter ergänzbar; die Zeile eines Datensatzes ist ein eigenes Bauteil. Die Einschränkung der Gruppenansicht baut die Suche selbst (§7). Das Fenster als neue Form gehört zuerst in den Leitfaden (§5, §7); das legt UI-05 fest.
8. **An `adr/0025`:** Der Harvester rechnet keine Embeddings; er liefert Texte in der Sprache der Quelle, das Review ergänzt englische Titel und Beschreibungen, wo sie fehlen (§4.1, §4.6).
9. **An M5-07, M5-08, M5-09, M5-11, DS-04:** Beschreibungen nennen Region und Inhalt; Schlagworte in Deutsch und Englisch, neue Fachbegriffe ins Glossar (F7 = 1, ab M5-07). Solange das Glossar noch nicht gebaut ist, stehen die Begriffe in der Plan-Datei der Aufgabe und ziehen mit Fassung 3 um.
10. **Dokumente:**
    - **`architekturplan.md` 5.3 und 10, Nachtrag (F3):** Die Vektorähnlichkeit der Hybrid-Suche rechnet in M5 der Prozess `api` exakt über eine Spalte in Postgres, nicht pgvector; pgvector kommt, wenn die Menge einen Index verlangt. Entsprechend 0 Punkt 9 („pgvector“) und die Tabelle `dataset_embedding` in 10. Der Nachtrag kommt mit Fassung 3 des M5-Plans bzw. dem ersten PR der Umsetzung, nicht in diesem ADR-PR (Stufe C).
    - `projektuebersicht.md` §5: neuer Punkt der Onboarding-Checkliste (F7).
    - `docs/ui/leitfaden.md` §2 (neue Begriffe) und §7 (zweiter Schalter).
    - Entscheidungslog.
11. **Chatbot (M7 7a):** nutzt dieselbe Schnittstelle und dasselbe Set (`architekturplan.md` 8.3).

---

## 13. Quellen

Abgerufen am 06.11.2026. Belegstufe in Klammern.

**Im Repo gelesen (P):** `docker-compose.yml`, `.github/workflows/ci.yml`, `backend/requirements.txt`, `backend/earthx/api/main.py`, `backend/earthx/logging.py`, `backend/earthx/catalog/registry.py`, `backend/earthx/catalog/collection.py`, `backend/earthx/catalog/datasets.py`, `frontend/src/components/ControlPanel.tsx`, `docs/ui/leitfaden.md`.

**Gemessen (M):** Erweiterungen und Textsuche-Daten der Postgres-Installation der Sitzung; `apt-cache policy postgresql-16-pgvector`; Erreichbarkeit von `huggingface.co` und `pypi.org`.

**Über das Abrufwerkzeug gelesen (P\*):**

- pgvector: https://github.com/pgvector/pgvector (README, LICENSE, CHANGELOG); Beispiel RRF: https://raw.githubusercontent.com/pgvector/pgvector-python/master/examples/hybrid_search/rrf.py
- PostGIS-Image: https://github.com/postgis/docker-postgis
- PostgreSQL-Doku als Quelltext: https://raw.githubusercontent.com/postgres/postgres/master/doc/src/sgml/textsearch.sgml, `pgtrgm.sgml`, `unaccent.sgml`
- BM25-Erweiterungen: https://github.com/paradedb/paradedb, https://github.com/timescale/pg_textsearch, https://github.com/tensorchord/VectorChord-bm25
- STAC: https://github.com/stac-api-extensions/collection-search, https://github.com/stac-api-extensions/freetext-search
- pgstac: https://raw.githubusercontent.com/stac-utils/pgstac/main/CHANGELOG.md, https://raw.githubusercontent.com/stac-utils/pgstac/main/src/pgstac/sql/002b_cql.sql
- stac-fastapi-pgstac: https://raw.githubusercontent.com/stac-utils/stac-fastapi-pgstac/main/CHANGES.md
- Modelle: https://github.com/embeddings-benchmark/mteb (Modell-Metadaten in `mteb/models/model_implementations/`), https://github.com/QwenLM/Qwen3-Embedding, https://github.com/FlagOpen/FlagEmbedding/tree/master/research/BGE_M3, https://pypi.org/project/fastembed/ und `qdrant/fastembed` (`fastembed/text/*.py`)
- Bewertung: https://github.com/AmenRa/ranx, https://github.com/cvangysel/pytrec_eval
- Vorarbeiten: https://github.com/developmentseed/stac-semantic-search

**Suchtreffer und Sekundärquellen (S):**

- Cormack, Clarke, Büttcher: Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods, SIGIR 2009, DOI 10.1145/1571941.1572114: https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf (gesperrt, nicht gelesen)
- Zur Wahl von k: https://arxiv.org/pdf/2410.13118, https://bigdataboutique.com/blog/reciprocal-rank-fusion-how-it-works-and-when-to-use-it
- Elastic, Hybrid-Suche auf BEIR: https://www.elastic.co/search-labs/blog/improving-information-retrieval-elastic-stack-hybrid
- BEIR: https://arxiv.org/abs/2104.08663; MIRACL-Reproduktion: https://arxiv.org/pdf/2302.14723
- bge-m3 auf MIRACL: https://api.emergentmind.com/topics/bge-m3-embedding-model
- pgvector bei AWS: https://aws.amazon.com/about-aws/whats-new/2024/11/amazon-rds-for-postgresql-pgvector-080/, https://aws.amazon.com/about-aws/whats-new/2025/04/pgvector-0-8-0-aurora-postgresql; Azure: https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-use-pgvector
- Komposita mit Hunspell: https://postgrespro.com/list/id/5566F66C.3070701@tbz-pariv.de
- Development Seed, Collection Discovery mit LLM: https://github.com/developmentseed/stac-fastapi-collection-discovery/pull/25
- NASA, Suche nach Erdbeobachtungsdaten: https://arxiv.org/html/2601.14176v1
- Google Dataset Search: https://research.google/pubs/pub47845/
- Größe von Testsets: https://www.staff.city.ac.uk/~sbrp622/papers/FewerTopics.pdf
- Preise gehosteter Embeddings: https://aiapiprices.com/embeddings-api-pricing/
