# M1-04 — Datensatz-Registry, Katalogmodell, pgstac: Plan

**Aufgabe:** `docs/plans/m1-fundament.md` §4, M1-04. **Autonomiestufe B** — dieser
Plan geht als Draft-PR an Otto; die Umsetzung beginnt erst nach seinem OK.

**Grundlagen:** `KLAERUNGEN.md` B10 (Capability-Flags), B11 (Lizenzstufen),
B12 (Onboarding-Checkliste), B13 (Registry gestuft); `architekturplan.md` 3.1
(Modulgrenzen), 5.1 (`earthx:`-Felder), 5.2 (zweistufiger Katalog), 5.3 (pgstac);
`adr/0003` §6, §11.2 (erster Datensatz, Lizenz); `adr/0004` §5, §6 (drei
Coverage-Felder); `adr/0005` Regel I (`earthx:source` als Verzweigungspunkt);
`adr/0002` §2 (T-A, T-C).

**Stand der Vorbedingungen:** M1-02 ist erledigt — `backend/earthx/` existiert mit
allen elf Modulen, `.importlinter` ist scharf und gatet jeden PR. M1-01
(strukturierte Logs) und M1-03 (Gateway) liegen noch nicht vor; M1-04 hängt laut
Plan auch nicht an ihnen. Dieser Plan setzt deshalb nichts aus `gateway` voraus:
In M1-04 geht kein Request nach draußen.

---

## 1. Ziel und Abgrenzung

**Ziel:** Sentinel-2 L2A ist als Collection mit allen `earthx:`-Feldern im eigenen
pgstac, erzeugt aus genau einem Registry-Eintrag.

**In M1-04:**

- `DatasetConfig` als Dataclass (B13, Stufe M1–M4), alle Capability-Flags
  ausdrücklich gesetzt (B10), Quad-Pol `false`.
- Die drei Coverage-Felder aus `adr/0004` §6.
- Der Eintrag Sentinel-2 L2A laut `adr/0003`.
- Abbildung `DatasetConfig` → STAC Collection mit den acht `earthx:`-Feldern aus
  `architekturplan.md` 5.1.
- Versionierte Migrationen und idempotentes Laden nach pgstac.
- Tests T-A (reine Validierung) und T-C (gegen Postgres, Sitzung und CI).

**Nicht in M1-04:** Coverage-Anbieter selbst (M2), Item-Suche und Such-Cache
(M1-06), STAC-API nach außen (M1-07), Hybrid-Suche und Embeddings, YAML-Kuratierung
(B13 Stufe ab M5), Lizenz-Einstufung (ist in `adr/0003` §11.2 entschieden, wird nur
übernommen).

---

## 2. Offene Punkte — von Otto beantwortet am 19.09.2026

**Alle fünf wie empfohlen: 1a, 2a, 3a, 4a, 5a.** Mit zwei Zusätzen von Otto:

- **Zu 3a:** M1-08 (PR #24) bringt `pypgstac` und einen `pgstac-migrate`-Dienst in
  die compose-Topologie. **M1-04b baut darauf auf** und benutzt dieselbe gepinnte
  Version aus `requirements.txt` — es gibt keine zweite Pin-Stelle.
  **Erledigt: #24 ist am 19.09.2026 gemergt**, `requirements.txt` führt
  `pypgstac[psycopg]==0.9.12`. Damit ist 04b nicht mehr blockiert.
- **Zu 4a:** Zu prüfen, welche STAC-Version wir ausgeben. `proprietary` ist ab
  STAC 1.1 durch `other` ersetzt. **Geprüft, siehe §3.3** — der Hinweis trifft zu.

Damit ist dieser Plan freigegeben;
die Antworten stehen als eine Zeile in `docs/ENTSCHEIDUNGSLOG.md`, und `KLAERUNGEN.md`
B13 nennt jetzt das Modul, in dem die Registry liegt. Die Fragen bleiben unten
stehen, weil die Begründungen erklären, warum die Umsetzung so aussieht, wie sie
aussieht.

### Frage 1 — Wo liegt die Registry?

**Antwort: (a) `catalog`.**

Zwei Dokumente widersprechen sich. B13 sagt „`DatasetConfig` als Python-Dataclass
in `datasets.py`". `architekturplan.md` 3.1 sagt, `datasets/<id>` sei
„Datensatzspezifika, die kein generischer Operator abdeckt" und werde „von nichts
Generischem importiert" — die Importregel `datasets-isolated` in `.importlinter`
setzt das durch. Läge die Registry unter `earthx/datasets/`, dürfte `catalog` sie
nicht lesen und könnte die Collection nicht bauen.

1. **`catalog`** — `earthx/catalog/registry.py` trägt den Typ, `earthx/catalog/datasets.py`
   die Einträge. `earthx/datasets/<id>/` bleibt reserviert für datensatzspezifischen
   **Code** (Operatoren, Eigenheiten), der isoliert bleibt. *(Empfehlung)*
   Begründung: 3.1 weist `catalog` ausdrücklich „Lizenz- und Capability-Felder" zu;
   B13 ist älter als die Isolationsregel und meint den Dateinamen, nicht das Modul.
2. **`datasets`** — Registry unter `earthx/datasets/`, und `api` (darf alles
   importieren) reicht die Einträge an `catalog` weiter. Hält B13 wörtlich ein,
   kostet aber eine Umleitung für jeden Aufruf und macht `catalog` für sich
   untestbar.
3. Etwas anderes.

Bei 1 wird `KLAERUNGEN.md` B13 im Umsetzungs-PR um einen Halbsatz ergänzt, damit
der Widerspruch nicht stehen bleibt.

### Frage 2 — Ein PR oder zwei?

**Antwort: (a) zwei PRs.**

M1-04 liegt als Ganzes deutlich über dem Richtwert von 400 Zeilen; `m1-fundament.md`
§6 sieht das Teilen ausdrücklich vor.

1. **Zwei PRs** *(Empfehlung)*: **M1-04a** Registry, Validierung, Collection-Abbildung,
   Sentinel-2-Eintrag, T-A-Tests — ohne Datenbank. **M1-04b** Migrationen, Laden nach
   pgstac, T-C-Tests, Postgres in CI und im Setup-Skript. 04a ist ohne 04b nutzlos,
   aber vollständig prüfbar.
2. Ein PR über dem Richtwert, mit Begründung im PR.

### Frage 3 — Postgres in CI und im Setup-Skript

**Antwort: (a) beide Dateien dürfen geändert werden.**

T-C verlangt Tests gegen Postgres in Sitzung **und** CI (`adr/0002` §2). Dafür sind
zwei Dateien zu ändern, die sonst tabu wären:

- `.github/workflows/ci.yml`: ein Service-Container `postgis/postgis:16-3.4` für einen
  neuen Job `catalog`. `CLAUDE.md` erlaubt `.github/`-Änderungen, „was die jeweilige
  Aufgabe ausdrücklich verlangt" — T-C in CI verlangt es. Zugangsdaten sind
  Wegwerfwerte im Workflow, keine Secrets.
- `scripts/setup-cloud-session.sh`: `pypgstac migrate` gegen die lokale Datenbank,
  idempotent. Heute richtet das Skript nur PostGIS ein; pgstac fehlt, obwohl
  `cloud-umgebung.md` §5 es als geprüft führt. Kostet beim ersten Sitzungsstart
  einmalig Zeit.

**Empfehlung:** beides so. Wenn Otto `.github/` selbst anfassen will, liefert der PR
den Job-Block als Vorschlag im Text statt als Diff — dann bleiben die T-C-Tests bis
dahin CI-seitig ungeprüft, was im PR zu benennen wäre.

### Frage 4 — Lizenzfeld ohne SPDX-Kennung

**Antwort: (a) `spdx_id = None` plus Name und URL.**

Die Onboarding-Checkliste verlangt ein maschinenlesbares Lizenzfeld, „SPDX-Kennung,
sonst Freitext + manuelle Einstufung". Für das Sentinel Data Legal Notice gibt es
keine SPDX-Kennung; Earth Search selbst trägt `proprietary`.

1. `spdx_id = None`, dazu `license_name = "Sentinel Data Legal Notice"` und
   `license_url`; die STAC-Collection trägt `"license": "proprietary"` wie upstream.
   Ein Test verlangt: entweder SPDX-Kennung **oder** Name und URL. *(Empfehlung)*
2. Eine eigene Kennung erfinden. Nicht empfohlen — SPDX ist ein geschlossener Raum.

### Frage 5 — Eigene Migrationen neben pgstac

**Antwort: (a) beides.**

pgstac bringt sein eigenes Schema und seine eigene Migration mit (`pypgstac migrate`).
„Migrationen versioniert" aus der Aufgabe kann zweierlei heißen:

1. **Beides** *(Empfehlung)*: die pgstac-Version wird gepinnt und beim Laden geprüft;
   daneben ein schmaler eigener Läufer für nummerierte SQL-Dateien unter
   `earthx/catalog/migrations/`, der angewandte Stände in einer Tabelle festhält.
   In M1-04 gibt es genau eine Datei — die, die diese Tabelle anlegt. Der Platz für
   den Anwendungs-Cache (E4, M1-06) ist damit da, bevor er gebraucht wird.
2. **Nur pgstac** in M1; ein eigener Läufer entsteht erst, wenn M1-06 die erste
   eigene Tabelle braucht. Weniger Code jetzt, eine Entscheidung mehr später.

---

## 3. Umsetzung

Die Modulpfade unten stehen unter dem Vorbehalt von Frage 1 (Empfehlung: `catalog`).

### 3.1 `DatasetConfig` — `earthx/catalog/registry.py`

Eingefrorene Dataclasses (`frozen=True`, `slots=True`), **ohne Vorgabewerte**, wo
B10 „ausdrücklich gesetzt" verlangt. Das ist der eigentliche Mechanismus: Wer ein
Flag vergisst, bekommt einen `TypeError` beim Anlegen des Eintrags, nicht erst in
einem Test.

| Gruppe | Felder |
|---|---|
| Identität | `dataset_id`, `title`, `description`, `data_class` (Enum: Raster-Zeitreihe, statisches Raster) |
| Format | `format` (Enum `ZARR > COG > LEGACY`, Reihenfolge laut Checkliste Punkt 5) |
| `capabilities` | `roi`, `time_range`, `band_math`, `interpolation`, `ml_processing`, `quad_pol`, `single_coverage_product` — alle ohne Vorgabewert |
| `license` | `spdx_id`, `name`, `url`, Flags `commercial_use`, **`distribution`**, `derivatives`, `share_alike`, `attribution_required`, `tier` (Enum `CATALOG/DISPLAY/PROCESSING`), `attribution_modified`, `attribution_unmodified`, `terms` (`terms_url` + `terms_notice` je Sprache) |
| Zitierung | `doi`, `citation` — Checklistenpunkt 3 (`scientific`-Extension) |
| `access` | `token_free_checked_at`, `method`, `cors` |
| `source` | `adapter` (Enum, hier `EARTH_SEARCH_V1`), `source_collection_id`, `endpoint`, `harvest_run` (in M1 `None`) |
| `coverage` | `provider` (Enum `UPSTREAM_AGGREGATION/LOCAL_SQL/SAMPLE`), `typical_footprint_km`, `max_geotile_level` |
| `default_render` | Bänder, Stretch, Colormap |
| `health` | `status`, `last_checked_ok` |

Drei Prüfungen in `__post_init__`, jede mit eigener Fehlermeldung:

1. **B11-Stufe gegen Flags:** `DISPLAY` und `PROCESSING` verlangen `distribution=True`
   **und** `derivatives=True`; ein ND-Datensatz auf Stufe `PROCESSING` wird abgelehnt.
   `distribution` ist beim Review als eigenes Flag hinzugekommen — B11 nennt beide
   Bedingungen, und ohne das Flag hätte die Prüfung nur die halbe Regel abgebildet.
2. **Attribution:** `attribution_required=True` ohne Attributionstext wird abgelehnt.
3. **Lizenz identifizierbar:** SPDX-Kennung, sonst Name und URL.
4. **Fehlerhafte Eingaben:** verdrehte oder leere `bbox`, Zeitraum der vor seinem
   Beginn endet, leerer oder umgekehrter Stretch, `health = ok` ohne Prüfdatum,
   Endpunkt ohne `https` (B8), negative Gitterstufe.
5. **Coverage-Deckel:** `max_geotile_level` muss zur typischen Footprint-Größe passen
   und darf sie nicht unterschreiten (`adr/0004` §5: für Sentinel-2 L2A höchstens z8).
   `single_coverage_product=True` schließt `provider=UPSTREAM_AGGREGATION` aus — ein
   Einmal-Produkt hat keine Dichte, sondern seine Ausdehnung.

Die Registry selbst ist eine Abbildung `dataset_id → DatasetConfig` mit einem
Nachschlagen, das für einen unbekannten Schlüssel eine eigene Ausnahme wirft. Das ist
der Punkt, an dem M1-06 Regel I (`404` statt leerer Trefferliste) später ansetzt.

### 3.2 Eintrag Sentinel-2 L2A — `earthx/catalog/datasets.py`

Genau ein Eintrag, alle Werte belegt aus `adr/0003`:

- Quelle Earth Search v1, `source_collection_id = "sentinel-2-c1-l2a"` (§6).
- B11-Stufe **Processing**; `commercial_use=True`, `derivatives=True`,
  `share_alike=False`, `attribution_required=True` (§11.2).
- Attribution „Contains modified Copernicus Sentinel data [Jahr]" für bearbeitete,
  „Copernicus Sentinel data [Jahr]" für unveränderte Daten. Dazu die **Bedingungen
  der Quelle** statt eines eigenen Haftungsausschlusses (Ottos Entscheidung vom
  19.09.2026): `terms_url` auf das Legal Notice und `terms_notice` je Sprache. Die
  Platzhalter `{year}` und `{terms_url}` füllt der Download — M1-04 hält die Vorlage.
- `format = COG`, `data_class = Raster-Zeitreihe`, `quad_pol = False`,
  `single_coverage_product = False`.
- `coverage.provider = UPSTREAM_AGGREGATION`, `max_geotile_level = 8`.
- `access.token_free_checked_at` aus `adr/0003` §10.1; `health.last_checked_ok` ebenso
  (Checkliste Punkt 10).

Offen bleibt bewusst, was `adr/0003` §6 als „noch zu prüfen" führt: ob
`sentinel-2-c1-l2a` ein Thumbnail-Asset führt. Das gehört zu F6 und M2, nicht hierher;
der PR benennt es.

### 3.3 Abbildung auf eine STAC Collection — `earthx/catalog/collection.py`

Eine Funktion `to_stac_collection(config) -> dict`. Sie erzeugt die Pflichtfelder einer
STAC Collection und darunter alle acht `earthx:`-Felder aus 5.1 — auch die, die in M1
leer bleiben (`earthx:distributions`, `earthx:default_render`), damit die Form
vollständig ist und M2 nichts nachzurüsten hat.

**Die drei Coverage-Felder bleiben aus der Collection heraus.** `adr/0004` §5 sagt,
der **Registry-Eintrag** entscheide den Coverage-Weg; ein neuntes `earthx:`-Feld wäre
eine Erweiterung von 5.1 und damit eine Architekturentscheidung, die diese Aufgabe
nicht trifft. DOI und Zitierung liegen nicht unter `earthx:`, sondern in der
`scientific`-Extension, die 5.1 ohnehin nennt.

**STAC-Version und Lizenzwert hängen zusammen (Ottos Zusatz zu 4a, geprüft).** Der
Hinweis trifft zu: STAC 1.1 hat `proprietary` durch `other` ersetzt. Sichtbar wurde
das beim Rücklesen mit `pystac` 1.15, das `proprietary` beim Einlesen stillschweigend
zu `other` normalisiert. Wir geben **STAC 1.0.0 mit `proprietary`** aus, weil pgstac
und Earth Search das sprechen. Damit die beiden nicht auseinanderlaufen, ist der
Lizenzwert **aus der Version abgeleitet** statt fest eingetragen: eine SPDX-Kennung
wird in beiden Versionen unverändert geschrieben, ohne Kennung sagt 1.0 `proprietary`
und 1.1 `other`. Welche Version wir tatsächlich ausliefern, entscheidet die
`stac-fastapi-pgstac`-Version, die **M1-07** pinnt — dann ist eine Zeile zu ändern,
nicht eine Suche nach Fundstellen.

Keine neue Abhängigkeit: Das Ergebnis ist ein Dictionary. `pystac` liegt als
Abhängigkeit bereits vor und wird **nur im Test** benutzt, um das Ergebnis gegen die
STAC-Spezifikation zu prüfen. `earthx:source` bekommt die Form, die `adr/0005` Regel I
braucht: Adapter-Kennung und Quell-Collection, damit M1-07 daran verzweigen kann.

### 3.4 Migrationen und Laden — `earthx/catalog/pgstac.py`

- Verbindung ausschließlich aus der Umgebung (`PGHOST` usw.), nie aus Code; keine
  Vorgabewerte, die auf eine echte Datenbank zeigen.
- `pypgstac[psycopg]` gepinnt auf die in `cloud-umgebung.md` §5 gemessene Version.
  Beim Laden wird die vorgefundene pgstac-Version gelesen und gegen den Pin geprüft;
  eine Abweichung ist ein Fehler mit beiden Versionen im Text, kein stilles Weiter.
- Laden über `pgstac.upsert_collection` — dieselbe Wahrheit wie die Registry (B13
  Punkt 3), und **idempotent**: zweimaliges Laden ergibt eine Zeile mit gleichem Inhalt.
- Eigener Migrationsläufer (Frage 5, Option 1) in `catalog/schema.py`: nummerierte
  `.sql`-Dateien unter `catalog/migrations/`, Datei und Buchungszeile in einer
  Transaktion, Prüfsumme gegen nachträglich geänderte Migrationen.
  **Abweichung vom Plan:** Die Buchführungstabelle `earthx_migrations` gehört dem
  Läufer und wird von ihm angelegt, nicht als Datei `001` ausgeliefert. Sonst müsste
  jedes Migrationsverzeichnis sie mitbringen — die Tests haben das sofort gezeigt.
  `migrations/` ist damit in M1-04 leer; ein README sagt, warum, und die erste echte
  Migration ist der Anwendungs-Cache aus E4 in **M1-06**.
- Kein Import aus `gateway`: hier geht nichts nach draußen.
- **Suchpfad:** Vor pgstac-Aufrufen wird `search_path` auf `pgstac, public` gesetzt.
  pgstac's eigene Trigger sprechen ihre Tabellen unqualifiziert an (ein Löschvorgang
  läuft in `DELETE FROM partition_stats`); ohne das scheitert er an einer Relation,
  die weder im Befehl noch in der Collection vorkommt. Unsere Buchführung ist deshalb
  ausdrücklich `public.earthx_migrations` — sonst landete sie im pgstac-Schema und
  wäre bei dessen Neuaufbau still weg.
- **Einstiegspunkt** `python -m earthx.catalog.load`: migriert, prüft die Version,
  schreibt alle Einträge und **committet**. Ohne ihn wäre das Abnahmekriterium nur in
  einer zurückgerollten Testtransaktion erfüllt.

### 3.5 Tests

**T-A (`backend/tests/catalog/`, kein Netz, keine Datenbank):**

| Test | Erwartung |
|---|---|
| Eintrag ohne ein Capability-Flag | `TypeError` — Abnahmekriterium der Aufgabe |
| ND-Datensatz auf Stufe `PROCESSING` | abgelehnt (B11) |
| `attribution_required` ohne Text | abgelehnt |
| `max_geotile_level` feiner als der Footprint erlaubt | abgelehnt (`adr/0004` §5) |
| Einmal-Produkt mit `UPSTREAM_AGGREGATION` | abgelehnt |
| unbekannte `dataset_id` | eigene Ausnahme, kein `KeyError`, kein `None` |
| Sentinel-2-Eintrag | `quad_pol is False`, Stufe `PROCESSING`, Attributionstext und Haftungssatz vorhanden |
| `to_stac_collection` | alle acht `earthx:`-Felder vorhanden; Ergebnis ist eine gültige STAC Collection (`pystac`) |
| `to_stac_collection` zweimal | gleiches Ergebnis, keine gemeinsam genutzten veränderlichen Objekte |

**T-C (Postgres, Sitzung und CI):** eigenes Testschema je Lauf, danach verworfen.

| Test | Erwartung |
|---|---|
| Laden, dann lesen | Collection liegt in pgstac, `earthx:`-Felder unverändert im JSON |
| zweimal laden | eine Zeile, gleicher Inhalt — idempotent |
| Eintrag ändern, erneut laden | Änderung ist drin, immer noch eine Zeile |
| `PG*` nicht gesetzt | klarer Fehler, der sagt, was fehlt — kein stilles Überspringen, kein Double |
| Postgres erreichbar, aber pgstac fehlt | Fehler, der `pypgstac migrate` nennt |
| pgstac-Version weicht ab | Fehler mit beiden Versionen (Test setzt die Version in der Datenbank um) |
| Migration nach dem Anwenden geändert | Fehler mit beiden Prüfsummen |
| Migration schlägt mitten im SQL fehl | nichts gebucht, Transaktion zurückgerollt |

Die letzte Zeile ist bewusst so: `adr/0002` §6 verlangt, dass jeder Test an
mindestens zwei Orten läuft. Ein T-C-Test, der sich mangels Datenbank selbst
überspringt, wäre in der Praxis nirgends grün und niemandem aufgefallen.

Der `no_network`-Wächter in `backend/tests/conftest.py` lässt `127.0.0.1` durch;
die T-C-Tests brauchen daran nichts geändert. Das ist beabsichtigt und wird im PR
festgehalten, damit niemand den Wächter später „aufräumt".

### 3.6 Abhängigkeiten und Umgebung

- Keine neue Abhängigkeit für 04b: `pypgstac[psycopg]==0.9.12` steht seit M1-08 in
  `requirements.txt` und bringt `psycopg` mit, das `catalog` zur Laufzeit braucht.
  Der Pin wird **nicht** wiederholt, und 04b prüft ihn beim Laden gegen die
  vorgefundene pgstac-Version (§3.4).
- `scripts/setup-cloud-session.sh` und `.github/workflows/ci.yml` laut Frage 3.
- `docs/ENTSCHEIDUNGSLOG.md`: je eine Zeile für die Antworten auf die Fragen oben.

---

## 4. Reihenfolge der Umsetzung

1. `DatasetConfig`, Enums, Prüfungen in `__post_init__` — mit den T-A-Tests im selben Commit.
2. Eintrag Sentinel-2 L2A.
3. `to_stac_collection` und sein Test.
4. *(04b)* Setup-Skript, CI-Job; `pypgstac` kommt aus dem Pin, den M1-08 in
   `requirements.txt` gesetzt hat.
5. *(04b)* Laden nach pgstac, Versionsprüfung, T-C-Tests.
6. Entscheidungslog, Aufräumen, `ruff check backend`, `pytest`,
   `lint-imports --config .importlinter`.

## 5. Abnahme laut Aufgabe

| Kriterium | Beleg |
|---|---|
| Collection im pgstac mit korrekten Flags | T-C „Laden, dann lesen" |
| Eintrag ohne ausdrücklich gesetzte Capability wird abgelehnt | T-A, erste Zeile |
| Laden ist idempotent | T-C „zweimal laden" |

## 6. Risiken

| Risiko | Umgang |
|---|---|
| pgstac-Version in CI und Sitzung driftet auseinander | Pin, plus Prüfung beim Laden (§3.4) |
| PR über 400 Zeilen | Teilung laut Frage 2 |
| B13 und 3.1 widersprechen sich beim Ort der Registry | Frage 1; die Umsetzung beginnt nicht ohne Antwort |
| Setup-Skript wird langsamer | `pypgstac migrate` ist idempotent und läuft nur beim ersten Start; das Ergebnis wird zwischengespeichert |
| 04b hing an M1-08 | erledigt: PR #24 ist gemergt, der Pin steht in `requirements.txt` |
| Sentinel-2-Eintrag bleibt in drei Feldern offen (`default_render`, `liability_notice`, `citation`) | jeweils als `None` gesetzt und im PR benannt, statt einen Wert zu erfinden; `m1-fundament.md` §2 sieht die Standard-Visualisierung ohnehin erst in M2 |
