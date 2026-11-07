# M5-13 — YAML-Lader für die Registry: Plan-Schritt

**Status (07.11.2026):** Plan angenommen (Otto, 07.11.2026; Antworten in §8a), umgesetzt im selben Draft-PR.
**Aufgabe:** M5-13 aus `docs/plans/m5/m5-discovery-und-suche.md` §6.2. **Stufe B.** Hängt von UI-05b ab (gemergt mit #310). M5-08, M5-22, M5-15, M5-17, M5-19 und M5-14 warten auf den Merge.
**Grundlagen:** `adr/0025` §7 (Lader, Ablage, Pflichtfelder, Startprüfung), §8 Schnitt Schritt 1, F8; `adr/0024` R3, R4, R5, R10, §6a, Tests 1–5; `adr/0027` §6.1 (F8); `KLAERUNGEN.md` B10, B13; `architekturplan.md` 3.1, 5.1.

Belegstufen wie in `adr/0025`: **P** am Quelltext gelesen (Stand `main` d6c0e39), **M** in dieser Sitzung gemessen (nur lokal, ohne Netz), **A** eigene Ableitung. Keine Quelle wird abgerufen.

---

## 1. Ziel

Die Registry-Einträge wandern aus Python in YAML (B13 Stufe 2). Aufrufer merken nichts: Der Lader baut dieselben `DatasetConfig`-Objekte mit denselben Prüfungen. Dazu kommen:

1. die Pflichtfelder `legal_status` (mit `legal_note`) und `access.account` (mit `account_provider`, `account_paths`), ohne Vorgabe (B10);
2. die Startprüfung für Prototyp-Einträge (`adr/0024` R5) mit der neuen Variable `EARTHX_PROFILE`;
3. ein `Dockerfile`, das nur die freigegebenen Einträge ins Image kopiert.

**Nicht in M5-13:** gelistete Einträge und `listed/` (M5-17), Seed und `sources/` (M5-19), Kandidaten (M5-20), die erste Prototyp-Quelle und die übrigen Regeln aus `adr/0024` (R6 Aufräumen, R7/R11 Weitergabe-Sperren und `no-store`, R8 Oberfläche), Embeddings (M5-23). Die Werte aller vier Einträge ändern sich nicht; neu sind nur die beiden Pflichtfelder.

---

## 2. Ausgangslage im Code [P]

- **Einträge:** `catalog/datasets.py` (992 Zeilen) hält vier `DatasetConfig` als Modulkonstanten (`SENTINEL_2_L2A`, `COP_DEM_GLO_30`, `ESA_WORLDCOVER_2020`, `ESA_WORLDCOVER_2021`), dazu `RETIRED` (ein Eintrag) und `REGISTRY`. Zwei Hilfsfunktionen erzeugen Teile: `_scene_share` (Suchfilter von Sentinel-2) und `_worldcover(year, version, doi)` (beide WorldCover-Einträge).
- **Prüfungen:** alle in `__post_init__` der Dataclasses in `catalog/registry.py`; `DatasetRegistry` prüft doppelte IDs, `RETIRED` und Nachfolger.
- **Importe von `REGISTRY`** im Produktivcode, sechs Stellen wie in `adr/0025` §7.2: `catalog/load.py`, `api/main.py` (Vorgabe-Argument von `create_app`), `api/tiler.py` (dito), `discovery/materialize.py`, `runner/cli.py`, `runner/recipe_file.py`. Der Prozess `worker` und `jobs` lesen die Registry nicht.
- **Tests:** rund 100 Testdateien importieren die Konstanten (`SENTINEL_2_L2A` allein 37-mal, `REGISTRY` 13-mal, dazu `DEM_ACQUISITION_START`/`_END`).
- **`AccessInfo`:** `token_free_checked_at: date` (Pflicht, nie leer), `method`, `cors`. In der Collection unter `earthx:access`.
- **Frontend:** liest `earthx:legal_status`, `earthx:legal_note` (`catalogue.ts:61`) und `earthx:access.account` (`catalogue.ts:54`) schon seit UI-05b; fehlen sie, gilt „cleared“ bzw. „none“. `token_free_checked_at` ist dort schon `string | null`.
- **Abhängigkeiten:** `pyyaml==6.0.3` und `pydantic==2.13.5` stehen schon in beiden Lock-Dateien (über `uvicorn[standard]` bzw. `fastapi`), aber nicht in `requirements.txt`.
- **Image:** `Dockerfile` kopiert nur `earthx/`; `WORKDIR /app`; das Runner-Image baut auf `app` auf. `.dockerignore` schließt `tests/` aus. Compose bindet keinen Quelltext ein.
- **`EARTHX_PROFILE`** kommt nirgends vor; `CI` setzt GitHub Actions selbst.

**Spike [M]:** `pydantic.TypeAdapter` liest die vorhandenen Dataclasses streng (`strict`, `extra="forbid"`) aus JSON und baut alle vier Einträge und `RETIRED` gleich (`==`) wieder auf; ein unbekanntes Feld, ein fehlendes Feld, `"no"` für ein `bool` und eine Zahl für einen Text werden abgelehnt. Die Einstellung muss an jeder Dataclass hängen (`__pydantic_config__`), als Argument von `TypeAdapter` lehnt pydantic sie ab.

---

## 3. Umsetzung

### 3.1 Ablage (`adr/0025` §7.1, F8 = 1)

| Pfad | Inhalt | im Image | geladen |
|---|---|---|---|
| `backend/catalog/datasets/<dataset_id>.yaml` | ein voller Eintrag je Datei | ja | immer |
| `backend/catalog/retired.yaml` | `RETIRED` als Liste | ja | immer |
| `backend/catalog/prototype/` | nur `README.md` (Regeln aus `adr/0024`), noch kein Eintrag | **nie** | nur nach §3.4 |

- Der Ort im Image ist eine Konstante des Pakets: `CATALOG_DIR = Path(earthx.__file__).parents[1] / "catalog"`, also `backend/catalog` im Repo und `/app/catalog` im Image.
- Dateiname = `dataset_id` + `.yaml`; sonst Ladefehler.
- In `datasets/` und `prototype/` liegen nur `*.yaml` und höchstens ein `README.md`. Jede andere Datei (z. B. ein vergessenes `.yml`) ist ein Ladefehler.

### 3.2 Lader (`adr/0025` §7.2)

- **Eine Stelle:** `catalog.datasets.registry() -> DatasetRegistry`, einmal je Prozess gebaut (`functools.cache`). Die sechs Importstellen rufen sie. `create_app(registry=None)` in `api/main.py` und `api/tiler.py` nimmt `registry()`, wenn kein Argument kommt; Tests reichen weiter eine eigene Registry hinein.
- **Bauteile:** `load_entry(path) -> DatasetConfig`, `load_retired(path)` und `load_registry(catalog_dir, prototype_dir=None)`. Tests rufen diese mit eigenen Verzeichnissen; `registry()` nur liest die Umgebung und ruft `load_registry`.
- **Dieselben Objekte:** YAML → `DatasetConfig` über `pydantic.TypeAdapter` im Strict-Modus über die vorhandenen Dataclasses, ohne zweites Schema (Spike §2; F1). `__post_init__` läuft wie heute, jede Prüfung gilt weiter.
- **Streng lesen (Auslegung A1):** eigener `SafeLoader` nach YAML-1.2-Kernschema: nur `true`/`false` sind Wahrheitswerte (`yes`, `no`, `on`, `off` bleiben Text und scheitern dann an der Typprüfung), keine Umdeutung von Datum oder Zeit (Datumsangaben als Text, pydantic liest ISO 8601); doppelte Schlüssel, Anker und Aliase sind Ladefehler. Danach JSON-Form, dann `validate_json(strict=True)`.
- **Fehlermeldung:** Datei, Feldpfad und Grund (`datasets/cop-dem-glo-30.yaml: license.tier: …`); kein Wert eines Felds.
- **Einstellung der Dataclasses:** jede Dataclass in `registry.py`, die in einem Eintrag vorkommt, bekommt `__pydantic_config__ = {"strict": True, "extra": "forbid"}` als einfaches `dict`; `registry.py` importiert pydantic dafür nicht.
- **Abhängigkeiten:** `pyyaml` und `pydantic` kommen ausdrücklich in `requirements.txt` (sie werden jetzt direkt importiert); die Lock-Dateien behalten die Versionen, nur die Herkunftszeilen ändern sich (`scripts/lock-backend.sh`).

### 3.3 Umzug bitgleich

- Die YAML-Dateien entstehen aus den Python-Objekten (Skript nur in der Sitzung, nicht im Repo) in der Reihenfolge der Dataclass-Felder; die Begründungen aus den Python-Kommentaren gehen von Hand als YAML-Kommentare mit, jeweils am Feld.
- **Nachweis (F2):** Im Umzugs-Commit liegen alter und neuer Stand nebeneinander; ein Test verlangt für jeden Eintrag `yaml == python` (ganzes `DatasetConfig`, auch was nicht in der Collection steht), gleiche `to_stac_collection`-Ausgabe und gleiches `RETIRED`. Ergebnis in der PR-Beschreibung. Der nächste Commit entfernt die Python-Einträge und mit ihnen diesen Test.
- **Dauerhaft:** Round-Trip-Test je Datei (laden → zurück in die JSON-Form → gleich der gelesenen Datei), damit kein Feld still verloren geht.
- **WorldCover (Auslegung A2):** zwei vollständige Dateien, ohne Vorlage. Sie unterscheiden sich in Jahr, Version und DOI; ein Kommentar oben nennt die andere Datei.
- **Tests (Auslegung A3):** ein Hilfsmodul `tests/catalog/entries.py` stellt `SENTINEL_2_L2A`, `COP_DEM_GLO_30`, `ESA_WORLDCOVER_2020`, `ESA_WORLDCOVER_2021`, `REGISTRY`, `RETIRED`, `DEM_ACQUISITION_START`, `DEM_ACQUISITION_END` aus `registry()` bereit. In den rund 100 Testdateien ändert sich nur die Importzeile (mechanisch, eigener Commit). Das Produktivpaket behält keine Konstanten.

### 3.4 Neue Pflichtfelder (`adr/0025` §7.3, `adr/0024` R3, `adr/0027` §6.1)

**`DatasetConfig.legal_status: LegalStatus`** (`cleared` · `unclear`) und **`DatasetConfig.legal_note: str | None`**, beide ohne Vorgabe.

- `unclear` ⇔ ID beginnt mit `proto-`; bei `unclear` ist `legal_note` ein nicht leerer Satz, bei `cleared` leer.
- Lader zusätzlich: in `datasets/` nur `cleared`, in `prototype/` nur `unclear`.

**`AccessInfo`** neu: `account: AccountKind` (`none` · `anonymous_token` · `free_account` · `requester_pays`), `account_provider: str | None`, `account_paths: tuple[AccountPath, ...]` (`W2a` · `W2b` · `W3` · `W4`); `token_free_checked_at` wird `date | None`. Prüfungen in `DatasetConfig.__post_init__` (Startcheck aus `adr/0027` §6.1):

| `account` | Stufe (`license.tier`) | `account_paths` | `account_provider` | `token_free_checked_at` |
|---|---|---|---|---|
| `none` | jede | leer | leer | gesetzt |
| `anonymous_token` | höchstens `catalog` (F3, §8a) | leer | leer | gesetzt |
| `free_account` | höchstens `catalog`, solange `account_paths` leer | in M5 leer | gesetzt | leer |
| `requester_pays` | höchstens `catalog` | immer leer | gesetzt oder leer | leer |

- `account_paths` ist in M5 bei jedem Wert leer (kein Weg außer W0 ist freigegeben); die Prüfung verlangt das ausdrücklich, damit ein Wert dort erst mit einer Entscheidung Ottos entsteht.
- Alle vier Einträge bekommen `legal_status: cleared` und `access.account: none`.

**Collection** (`collection.py`): `earthx:legal_status`, `earthx:legal_note` (Auslegung A4: immer da, `null` bei `cleared`) und in `earthx:access` zusätzlich `account`, `account_provider`, `account_paths`; `token_free_checked_at` darf `null` sein. Das Frontend liest diese Felder schon (§2); im Frontend ändert sich nur der Kommentar „Absent until the YAML loader sets them“ in `types.ts`.

### 3.5 Startprüfung (`adr/0024` R5, `adr/0025` §7.4)

In `registry()` beim ersten Aufruf, also beim Start von `api`, `tiler`, `catalog-load`, `materialize` und dem Runner:

| `EARTHX_PROTOTYPE_SOURCES` | `EARTHX_PROFILE` | `CI` | Ergebnis |
|---|---|---|---|
| nicht gesetzt oder leer | beliebig gültig oder leer | beliebig | nur freigegebene Einträge |
| Verzeichnis | `local` | leer | freigegebene und Prototyp-Einträge |
| gesetzt | nicht `local` | — | **Startfehler** |
| gesetzt | `local` | gesetzt | **Startfehler** |
| gesetzt, aber kein Verzeichnis | `local` | leer | **Startfehler** |
| — | gesetzt, aber nicht `local`, `ci` oder `cloud` | — | **Startfehler** |

- `EARTHX_PROFILE` ist ohne Prototyp-Pfad freiwillig; in M5 wirkt nur `local` (Auslegung A5). `CI` gilt als gesetzt, sobald der Wert nicht leer ist, auch bei `false` (Auslegung A6, vorsichtige Seite).
- Die Meldung nennt die Variablen, nie den Pfad (wie M5-18).
- **Runner:** baut mit `registry(prototype=False)`, liest `EARTHX_PROTOTYPE_SOURCES` also nie und lädt keine Prototyp-Einträge; ein `recipe.json` mit `proto-`-Datensatz ist dort „unbekannt“ (Test 5 aus `adr/0024`). Ist die Variable gesetzt, schreibt der Runner eine Warnung mit ihrem Namen (Auslegung A7).
- **Compose:** `EARTHX_PROFILE: ${EARTHX_PROFILE:-}` bei `catalog-load`, `api`, `tiler` und `materialize`; `EARTHX_PROTOTYPE_SOURCES` und der Mount kommen erst mit der Override-Datei (F4). Dazu `.env.example` und README.

### 3.6 Image

- `Dockerfile` (Stufe `app`): zusätzlich `COPY catalog/datasets ./catalog/datasets` und `COPY catalog/retired.yaml ./catalog/retired.yaml`, einzeln, nie `COPY catalog`. Das Runner-Image erbt beides.
- `.dockerignore`: `catalog/prototype/` und `catalog/candidates/` als zweiter Riegel.
- Test am Text des `Dockerfile` (neben `test_runner_image_definition.py`): kopiert `catalog/datasets` und `retired.yaml`, nie `catalog/prototype`, `catalog/candidates` oder das ganze `catalog`; `.dockerignore` nennt beide (Test 4 aus `adr/0024`). Ein Bau des Images ist in der Cloud-Sitzung nicht möglich; Otto baut lokal einmal (`docker compose build`).

---

## 4. Tests

Alle ohne Netz, mit synthetischen Einträgen in `tmp_path` (Muster: `tests/catalog/synthetic_zarr.py`).

- **Umzug:** `yaml == python` je Eintrag und für `RETIRED` (nur im Umzugs-Commit, §3.3); Round-Trip je Datei; `registry()` enthält genau die Dateien unter `datasets/`.
- **Strenges Lesen, Fehleingaben:** unbekanntes Feld (oben und verschachtelt), fehlendes Feld, `yes`/`no`/`on` für ein `bool`, unquotiertes Datum für `token_free_checked_at` liest richtig, Zahl statt Text, Text statt Zahl, `null` für ein Pflichtfeld ohne `None`, doppelter Schlüssel, Anker und Alias, leere Datei, Datei mit Liste statt Mapping, ungültiges YAML, Binärmüll, Dateiname ≠ `dataset_id`, `.yml` neben `.yaml`, unbekannter Enum-Wert; jede Meldung nennt Datei und Feldpfad, keinen Wert.
- **`legal_status`:** `unclear` ohne `proto-`, `proto-` mit `cleared`, `unclear` ohne oder mit leerer `legal_note`, `cleared` mit `legal_note`; `cleared` unter `prototype/`, `unclear` unter `datasets/`.
- **`access.account`:** jede Zeile der Tabelle §3.4 in beide Richtungen (z. B. `free_account` mit Stufe `display`, `none` mit `account_provider`, `requester_pays` mit `account_paths`, `free_account` mit `token_free_checked_at`, `none` ohne `token_free_checked_at`); Collection trägt die neuen Felder.
- **Startprüfung:** jede Zeile der Tabelle §3.5 (über `monkeypatch.setenv`); Registry ohne Schalter enthält keinen `unclear`-Eintrag und keine `proto-`-ID (Test 1); Runner mit gesetztem Schalter lädt keinen Prototyp-Eintrag und lehnt ein Rezept mit `proto-`-Datensatz als unbekannt ab (Test 5); Meldung enthält den Pfad nicht.
- **Prototyp-Verzeichnis im Repo (R10):** jede `*.yaml` unter `backend/catalog/prototype/` wird geparst und geprüft, ohne Registry (heute keine; der Test läuft leer durch und greift mit der ersten Quelle).
- **Image:** §3.6.

---

## 5. Auslegungen

- **A1:** „Streng lesen“ (`adr/0025` §7.2) heißt YAML-1.2-Kernschema plus pydantic Strict; zusätzlich sind Anker und Aliase verboten, damit jede Datei für sich lesbar ist und kein Wert unsichtbar aus einer anderen Stelle kommt.
- **A2:** Keine Vorlagen oder Includes zwischen Einträgen; Wiederholung (WorldCover, die Suchfilter von Sentinel-2) ist gewollt, weil eine Datei = ein Eintrag im Review.
- **A3:** Testkonstanten im Hilfsmodul unter `tests/`, nicht im Paket; nur die Importzeilen der Tests ändern sich.
- **A4:** `earthx:legal_note` steht in jeder Collection, `null` bei `cleared`; so hat jedes `earthx:`-Feld eine feste Form.
- **A5:** `EARTHX_PROFILE` ist nur Pflicht, wenn der Prototyp-Pfad gesetzt ist (`adr/0024` S2); ein ungültiger Wert ist immer ein Startfehler. CI und `ci.yml` bleiben unverändert (`CI` setzt GitHub selbst).
- **A6:** `CI` mit beliebigem nicht leerem Wert zählt als CI.
- **A7:** Der Runner ignoriert den Schalter mit Warnung statt mit Startfehler, weil `adr/0025` §7.4 „lädt nie, auch mit gesetztem Schalter“ sagt und ein Nutzer des Runners die Variable aus einer `.env` mitbringen kann.

---

## 6. Doku mit der Umsetzung

- `architekturplan.md` 5.1: Zeilen `earthx:legal_status`, `earthx:legal_note`; Zeile `earthx:access` um `account`, `account_provider`, `account_paths` ergänzt.
- `KLAERUNGEN.md` B13: Nachtrag zu Stufe 2 (Einträge als YAML unter `backend/catalog/`, Lader `catalog.datasets.registry()`), wie in `adr/0025` §12 vorgesehen.
- `adr/0024` R4: Nachtrag, dass das Verzeichnis `backend/catalog/prototype/` heißt (`adr/0025` §12).
- `docs/cloud-umgebung.md`: R10 (Cloud-Sitzungen schreiben Prototyp-Einträge, rufen die Quelle nicht ab).
- README und `.env.example`: `EARTHX_PROFILE`; wie man einen Eintrag ändert (Datei unter `backend/catalog/datasets/`).
- `docs/ENTSCHEIDUNGSLOG.md`: Zeile mit Ottos Antworten, dann Zeile zur Umsetzung; M5-Plan §6.1.

---

## 7. Umfang und Schnitt

Geschätzt [A], ohne Umzug: Lader und strenges Lesen ~170, neue Felder und Prüfungen ~90, Startprüfung ~50, sechs Aufrufstellen ~30, Collection ~10, `Dockerfile`/`.dockerignore`/Compose ~15; Tests ~400. Dazu mechanisch: Umzug (~950 Zeilen Python weg, ~850 Zeilen YAML neu) und ~100 Importzeilen in Tests. Ohne den mechanischen Teil rund 750 Zeilen, deutlich über dem Richtwert; daher F5.

Commits (je eine Sache): (1) `pyyaml` und `pydantic` direkt in `requirements.txt`; (2) Lader und strenges Lesen; (3) YAML-Dateien neben den Python-Einträgen mit Vergleichstest; (4) Python-Einträge weg, `registry()` an den sechs Stellen; (5) Testimporte; (6) `legal_status`; (7) `access.account`; (8) Startprüfung und `EARTHX_PROFILE`; (9) `Dockerfile` und `.dockerignore`; (10) Doku und Log.

---

## 8. Fragen an Otto

**F1 — Typprüfung beim Laden?**
1. pydantic im Strict-Modus über die vorhandenen Dataclasses (kein zweites Schema; Spike §2 zeigt, dass alle Einträge gleich herauskommen); `pyyaml` und `pydantic` direkt in `requirements.txt`, beide schon in der Lock-Datei **(Empfehlung)**
2. Eigener kleiner Umwandler über die Typangaben der Dataclasses (~120 Zeilen mehr, ohne pydantic im `catalog`)

**F2 — Nachweis „bitgleich“?**
1. Vergleichstest im Umzugs-Commit (ganzes `DatasetConfig`, Collection, `RETIRED`), Ergebnis im PR; danach dauerhaft der Round-Trip-Test je Datei **(Empfehlung)**
2. Zusätzlich dauerhaft eine Golden-Datei der vier Collections; jede spätere Änderung an einem Eintrag erzeugt sie neu

**F3 — `access.account: anonymous_token` bis zum Nachtrag aus `adr/0018` §12?**
1. Prüfung wie `free_account` bei der Stufe (höchstens `catalog`), aber mit Prüfdatum; DS-04 hebt das mit dem Nachtrag auf (`adr/0027` §6.1: „bis dahin wie `free_account`“) **(Empfehlung)** — Korrektur Otto in §8a
2. Nur die Prüfungen aus `adr/0025` §7.3 (Pfade leer, kein Anbieter), keine Grenze der Stufe

**F4 — Compose-Override für Prototyp-Einträge (`adr/0024` R4)?**
1. Kommt mit der ersten Prototyp-Quelle bzw. der Umsetzung von `adr/0024`; M5-13 liefert Startprüfung, Verzeichnis mit `README.md` und `EARTHX_PROFILE` **(Empfehlung)**
2. Schon jetzt eine Datei `compose/prototype.yml` mit Mount und beiden Variablen

**F5 — Schnitt (rund 750 Zeilen plus mechanischer Umzug, §7)?**
1. Ein PR mit getrennten Commits; der Umzug ist durch den Vergleichstest belegt **(Empfehlung)**
2. Zwei PRs: M5-13a Lader und Umzug bitgleich (ohne neue Felder); M5-13b `legal_status`, `access.account`, Startprüfung, `Dockerfile`. M5-08 wartet auf beide

## 8a. Antworten Otto (07.11.2026)

F1–F5 jeweils **Option 1**, Auslegungen A1–A7 (§5) angenommen.

**Korrektur zu F3:** Die Grenze für `anonymous_token` (Stufe höchstens `catalog`) hebt **nicht DS-04** auf; Sentinel-1 GRD über Earth Search braucht kein Token (`adr/0018` Teil A). Aufgehoben wird sie erst, wenn der Satz aus `adr/0018` §12 in `ENTSCHEIDUNGEN_2026-09-18.md` übernommen ist (Teil B, Planetary Computer RTC). So steht es auch im Kommentar an der Prüfung in `catalog/registry.py`.
