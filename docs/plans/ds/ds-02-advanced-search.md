# DS-02 — „Advanced search“ mit Filtern je Datensatz

**Stand:** 26.10.2026, beauftragt von Otto. Paket „Datensatzabhängige Suche und Prozessierung“ (DS), nach VP3 und vor M5; Übersicht in `docs/plans/ds/ds-00-paket.md`.
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach UI-01g (Suchergebnisse angedockt). Höchstens zwei Stufe-B-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe DS-02 aus `docs/plans/ds/ds-02-advanced-search.md` aus.“

## 1. Anlass

Otto möchte einen Knopf „Advanced search“, der die Filter zeigt, die zum gewählten Datensatz passen. Heute gibt es für Sentinel-2 einen Wolkenfilter; einen allgemeinen Weg für Filter je Datensatz gibt es nicht. `projektuebersicht.md` §7: „Qualitätsfilter, wo sinnvoll“.

## 2. Soll

- „Advanced search“ im Control-Menü öffnet die Filter des gewählten Datensatzes bzw. der gewählten Datensätze.
- Die Filter kommen aus der Registry je Datensatz (Feldname, Typ, Bereich bzw. Werte, Beschriftung, Einheit), nach dem Vorbild des Processing-Panels aus Schemas; wo die Quelle STAC-„queryables“ anbietet, wird das genutzt bzw. abgeglichen.
- Sentinel-2 bekommt seinen bestehenden Wolkenfilter über denselben Weg; nichts geht verloren.
- Filter, die ein Datensatz nicht kennt, erscheinen nicht. Bei mehreren gewählten Datensätzen gilt ein Filter nur für die Datensätze, die ihn kennen (sichtbar gekennzeichnet).
- Zusammenspiel mit `ignored_filters` (architekturplan, `time_range=False`) und mit der Coverage-Karte (Filter wirken auch dort, `adr/0004` K1).

## 3. Im Plan klären (mit Optionen und Empfehlung)

- Registry-Feld (Form, Validierung, Übersetzung in die Suchanfrage je Adapter, `adr/0011`); Kombination mit `query`/`filter` (CQL2) der Quelle.
- Wo „Wolken in der AOI“ (DS-03) später andockt.
- Permalinks (M4-19e) und „Clear search results“ (NM4-17): Filter gehören zu den Sucheinstellungen.

## 4. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip. Nicht anwendbare Möglichkeiten werden ausgeblendet, nicht ausgegraut (Otto, 26.10.2026).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Ausgehende Requests nur über `gateway`; keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Kein datensatzspezifischer Code: Unterschiede je Datensatz stehen als Daten in der Registry.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: Filter aus der Registry, Anfrage an die Quelle, Datensatz ohne Filter, mehrere Datensätze, Coverage reagiert.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), Hell/Dunkel, schmales Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n).
- Vor „fertig“ ist main geholt.

## 6. Plan (28.10.2026, Vorschlag, wartet auf Freigabe durch Otto)

Stufe B: Bis zur Freigabe ist kein Produktivcode geändert. Grundlage ist `main` nach #214 (UI-01g #209 gemergt). Belegstufen wie in `adr/0014`: [P] Code oder Primärquelle gelesen, [M] in der Sitzung gemessen (Wegwerf-Aufrufe, nicht im Repo), [A] eigene Ableitung.

### 6.0 Kurzfassung

- **Registry:** neues Feld `search_filters` am `DatasetConfig`, ohne Vorgabewert (B10): ein Tupel von `SearchFilter` mit STAC-Eigenschaft, Art (`range` oder `values`), Bereich bzw. Werten, Beschriftung, Einheit und Tooltip. Veröffentlicht als `earthx:search_filters` in der Collection, in den Wörtern von JSON Schema bzw. STAC-Queryables (`type`, `minimum`, `maximum`, `enum`, `title`, `description`). Der DEM bekommt ein leeres Tupel.
- **Eigene API:** `POST /stac/search` nimmt `query` in der Form der STAC-Query-Extension an, aber **nur** mit Eigenschaften und Operatoren, die die Registry nennt (`gte`/`lte` für Bereiche, `in` für Werte); alles andere ist `400`. `/coverage` nimmt dasselbe `query` als Parameter und ersetzt damit `max_cloud_cover`.
- **Mehrere Datensätze:** Ein Filter gilt je Collection, die ihn kennt; für die anderen fällt er weg und steht in `ignored_filters_by_collection`, wie heute `datetime` bei `time_range=False`.
- **Adapter (`adr/0011`):** `FilterSupport` bekommt `query: bool`; Earth Search `True` [M]. Ein Datensatz mit Filtern braucht eine Quelle mit `query` (Prüfung beim Bau der App). Materialisierte Datensätze dürfen vorerst keine Filter tragen.
- **Queryables:** Die Registry ist die Wahrheit, weil die Queryables der Quelle unvollständig sind [M]; ein Live-Test gleicht ab.
- **Oberfläche:** Im Control-Menü unter den Daten ein Knopf „Advanced search“, der einen Abschnitt mit den Filtern der gewählten Datensätze aufklappt. Er erscheint nur, wenn ein gewählter Datensatz Filter hat. Filter gehören zu den Sucheinstellungen: Sie wirken auf Suche, „Load more“, Datums-Fallback und Coverage, bleiben bei „Clear search results“ und gehen nicht in den Permalink.
- **Schnitt:** drei PRs, DS-02a Backend Suche, DS-02b Backend Coverage, DS-02c Frontend.

### 6.1 Stand im Code [P]

- **Es gibt keinen Wolkenfilter in der Suche.** `SearchParams` (`adapters/federated_search.py`) kennt `bbox`, `intersects`, `ids`, Zeit, `limit`, Marke. `query`, `filter`, `sortby`, `fields` weist `/stac/search` mit `400` ab (`api/federating_client.py`, `_DISALLOWED_QUERY_KEYS`, M3-13 F5), weil sie sonst still verworfen würden.
- **Der „bestehende Wolkenfilter“ ist `max_cloud_cover` an `GET /coverage/{id}`** (M2-05): geprüft 0–100 (`catalog/coverage.py`), übersetzt in `query={"eo:cloud_cover":{"lt":X}}` an `/aggregate` (`adapters/earth_search_coverage.py::_params`), im Cache-Schlüssel, auf dem Flächenweg des DEM verworfen und in `ignored_filters` genannt. Das Frontend hat den Parameter in `CoverageParams.maxCloudCover`, aber kein Bedienelement setzt ihn (`adr/0010` §2 sagt das auch). Der Wert ist im Code fest auf `eo:cloud_cover` verdrahtet, also datensatzspezifisch.
- **`ignored_filters` und `ignored_filters_by_collection`** bilden `api/federating_client.py::_partition_sources` und `_ignored_filters_of` je Quelle; das Frontend zeigt je Abschnitt „Filter not applied: <name>“ (`sections.ts::ignoredFilterNote`), für `datetime` einen eigenen Satz.
- **Adapter-Fähigkeiten** stehen als Daten in `adapters/spec.py::FilterSupport` (`intersects`, `ids`, `cql2`); Earth Search `cql2=False`. `adr/0011` B12 trennt Fähigkeiten der Quelle von denen des Datensatzes.
- **Processing-Panel aus Schemas:** `frontend/src/schemaForm.ts` baut ein Formular aus einem kleinen Teil von JSON Schema (`type`, `minimum`, `maximum`, `enum`, `oneOf` mit Titeln). Ein Suchfilter braucht aber einen Bereich bzw. eine Mehrfachwahl, keinen einzelnen Wert; das Vorbild ist das Vokabular, nicht die Komponente.
- **Sucheinstellungen im Frontend:** `store.ts::runSearch` baut `query` aus AOI, Datum und Datensätzen; `ctx.query` trägt sie für „Load more“; `dateFallback.ts` sucht mit derselben Anfrage; `refreshCoverage` fragt die Coverage für `coverageDatasetId` mit Datum und merkt sich Antworten je Datensatz, Stufe, Datum und Ausschnitt (`cachedViewportCoverage`). `clearSearchResults` lässt AOI, Zeitraum, Datensatzwahl und Filter stehen (Log 26.10.2026, UI-01g). Permalinks (M4-19e) tragen nur Auftrag und Kartenansicht, keine Sucheinstellungen (`permalink.ts`).

### 6.2 Messungen an der Quelle [M]

Earth Search v1, `sentinel-2-c1-l2a`, Box 10–11° O / 47–48° N, Juni 2024, `limit=100` (28.10.2026):

| Anfrage | Treffer | Folge |
|---|---|---|
| ohne `query` | 42 | Bezug |
| `eo:cloud_cover` `lt` 20 | 7 | wirkt |
| `eo:cloud_cover` `gte` 20, `lte` 50 | 8 | `gte`/`lte` wirken, auch zusammen |
| `platform` `in` `["sentinel-2a"]` / `eq` `"sentinel-2b"` | 21 / 21 | Wertelisten wirken |
| `s2:nodata_pixel_percentage` `lt` 5 | 24 | wirkt |
| unbekannte Eigenschaft `foo:bar` | **0** | still leer, kein Fehler |
| unbekannter Operator `between` | **42** | still übergangen |
| falscher Typ (`lt: "abc"`) | **400** mit Interna der Suchmaschine | darf nie durchgehen |
| CQL2-`filter` `eo:cloud_cover < 20` | **42** | still übergangen (wie `adr/0005`) |
| `/aggregate` `total_count` mit denselben `query` | 42 / 7 / 21 / 24, kombiniert 1 | Coverage folgt den Filtern (K1) |

- `GET /collections/sentinel-2-c1-l2a/queryables` nennt nur `eo:cloud_cover`, als `$ref` ohne Bereich oder Beschriftung; `/queryables` der ganzen API ist leer. Die Collection-`summaries` nennen weder Wolken- noch No-Data-Anteil. Für Sentinel-1 nennt die Quelle nur `sar:polarizations`, obwohl sechs Felder filterbar sind (`adr/0018` §3).
- Die Landing Page weist `item-search#query` und `#sort` aus, kein CQL2.
- Folge [A]: Die Quelle prüft nichts, was sie nicht kennt; drei der vier Fehlerformen sehen wie eine gültige Antwort aus. Deshalb prüft die Plattform jede Eigenschaft, jeden Operator und jeden Typ gegen die Registry, bevor etwas hinausgeht.

### 6.3 Registry-Feld

**Optionen für die Form:**

| | Form | Für | Gegen |
|---|---|---|---|
| **O1** | eigene Dataclass `SearchFilter`, veröffentlicht als `earthx:search_filters` in Queryables-Wörtern | geprüft wie `MaskSource`, klein, ein Feld je Angabe; später ohne Umbau als Queryables ausgebbar | eigenes Feld nach außen |
| O2 | wie O1, dazu eine eigene Route `/stac/collections/{id}/queryables` aus der Registry; das Frontend liest dort | Standard nach außen | eine Anfrage je Datensatz mehr, mehr Code, Queryables beschreiben Eigenschaften, nicht die Bedienung (Bereich, Einheit) |
| O3 | rohes JSON Schema im Eintrag | flexibel | kaum prüfbar, jede Ausgabe muss es interpretieren |

**Empfehlung O1.** O2 bleibt als spätere Ergänzung möglich (Abbildung, kein Umbau).

**Form (Vorschlag):**

```python
@dataclass(frozen=True, slots=True)
class FilterValue:
    value: str
    label: str

@dataclass(frozen=True, slots=True)
class SearchFilter:
    property: str            # STAC-Eigenschaft wie an der Quelle, z. B. "eo:cloud_cover"
    kind: FilterKind         # RANGE oder VALUES
    title: str               # Oberfläche, englisch, kurz: "Cloud cover"
    description: str         # Tooltip, englisch
    unit: str | None         # "%", None
    minimum: float | None    # nur RANGE
    maximum: float | None    # nur RANGE
    integer: bool            # nur RANGE: ganze Zahlen (z. B. relativer Orbit)
    values: tuple[FilterValue, ...]  # nur VALUES, aufsteigend nach Anzeige
```

Kein Vorgabewert, auch kein voreingestellter Filterwert: Ein Filter wirkt erst, wenn der Nutzer ihn setzt.

**Prüfungen beim Start (`ConfigError`):**
- `property` hat die Form einer STAC-Eigenschaft (`[a-z0-9_]+(:[a-z0-9_]+)?`), kommt je Eintrag einmal vor, beginnt nicht mit `earthx:` (reserviert für Filter, die die Plattform selbst rechnet, §6.9), ist nicht `datetime` (das hat sein eigenes Feld).
- `RANGE`: `minimum < maximum`, beide endlich, `values` leer; `VALUES`: mindestens zwei Werte, jeder einmal, Beschriftung nicht leer, `minimum`/`maximum` leer.
- `title`, `description` nicht leer; `unit` wie bei `band_units`.
- Ist das Tupel nicht leer, muss der Datensatz föderiert sein (§6.5) und seine Quelle `query` können (Prüfung in `check_adapter_specs`, wie heute Suche und Coverage).
- Über die ganze Registry: Dieselbe `property` hat in jedem Eintrag dieselbe Art, Einheit und Beschriftung. So wird im Frontend aus zwei Datensätzen eine Zeile (§6.7); ein Widerspruch hält den Start an.

**Sentinel-2 (Frage 4):** `eo:cloud_cover`, `RANGE` 0–100 %, „Cloud cover“, Tooltip „Share of the whole scene (about 110 × 110 km) covered by clouds, as reported by the source.“ Empfohlen zusätzlich `s2:nodata_pixel_percentage`, `RANGE` 0–100 %, „No data“, Tooltip „Share of the scene tile without image data, e.g. at the edge of a swath.“ Beide [M].

### 6.4 Eigene Schnittstelle

**Optionen für die Form der Filter in `/stac/search`:**

| | Form | Für | Gegen |
|---|---|---|---|
| **A** | `query` der STAC-Query-Extension, eingeschränkt auf die Registry | Standard, den die Quelle spricht [M]; Übersetzung fast 1:1; STAC-Clients kennen die Form | Query-Extension gilt neben CQL2 als die ältere Form |
| B | `filter` als CQL2-JSON-Teilmenge (`and`, `<=`, `>=`, `in`), je Adapter in `query` übersetzt | Zukunftsform, pgstac kann sie | mehr Code (Parser), Earth Search kann es nicht [M], also immer Übersetzung |
| C | eigenes Feld (`earthx:filters`) | einfach | kein STAC, jeder Client lernt es neu |

**Empfehlung A.** Regeln:
1. Erlaubte Operatoren: `gte` und `lte` für `RANGE` (beide Grenzen schließen ein, wie die Anzeige „0–20 %“), `in` für `VALUES`. Alles andere `400` mit eigenem Text.
2. Werte werden geprüft: Zahl (kein `bool`, endlich), innerhalb `minimum`–`maximum`, ganzzahlig wo `integer`, `gte ≤ lte`; bei `in` eine nicht leere Liste bekannter Werte, jeder einmal. Eine Grenze gleich dem Rand des Bereichs bleibt erlaubt.
3. Eine Eigenschaft, die **keine** der genannten Collections kennt: `400` („unknown filter“). Sie kennt **ein Teil**: Der Filter geht nur an diese; die übrigen nennen ihn in `ignored_filters_by_collection`, `ignored_filters` nennt ihn, sobald er irgendwo wegfiel. Der Name im Feld ist die Eigenschaft (`eo:cloud_cover`), das Frontend kennt den Titel aus der Registry.
4. Fehlertexte nennen Eigenschaft und Regel, nie einen Wert der Anfrage (wie die bbox-Texte).
5. Nur `POST`. `GET /stac/search` und `GET …/items` weisen `query` weiter ab, mit Hinweis auf `POST` (das Frontend sucht nur per `POST`, M3-08). `filter`, `sortby`, `fields` bleiben abgewiesen.
6. Keine Konformitätsklasse `#query` auf der Landing Page: Wir beantworten eine erklärte Teilmenge, nicht beliebige Eigenschaften (wie `/processing`, das keine Konformität erklärt). Nachtrag zu `adr/0005` Regel VI.
7. `/coverage/{id}` nimmt `query` als JSON im Parameter (wie `/aggregate` [M]) mit denselben Prüfungen; ein Filter, den der Datensatz nicht kennt, ist hier `400`, weil die Route genau einen Datensatz fragt. `max_cloud_cover` entfällt (Frage 3); der Flächenweg nennt verworfene Filter wie bisher in `ignored_filters`, nur ist er nie erreichbar, weil der DEM keine Filter hat.
8. Logs: wie bisher nur Datensatz, Stufe, Herkunft; dazu höchstens die **Namen** der gesetzten Filter, keine Werte.

### 6.5 Übersetzung je Adapter (`adr/0011`)

- `FilterSupport` bekommt `query: bool` (gemessen, wie `cql2`). Earth Search `query=True` [M]. Ohne Vorgabewert, also bekommt jeder `AdapterSpec` ihn ausdrücklich.
- `SearchParams` bekommt `query: Mapping[str, Mapping[str, Any]] | None`, normalisiert (Zahlen als `float`, Wertelisten sortiert und ohne Doppel). Die Prüfung gegen die Registry macht `api` vor dem Adapter (wie `datetime`, `adr/0011` B12); `SearchParams` prüft nur die Form.
- `search_fingerprint` und `mixed_fingerprint` nehmen `query` nur auf, wenn gesetzt: Suchen ohne Filter behalten Fingerabdruck, Cache-Einträge und Seitenmarken; `TOKEN_VERSION` bleibt 2. Mit Filter ist es eine andere Suche, also ein anderer Cache-Eintrag (sonst käme eine ungefilterte Seite aus dem Cache).
- `earth_search._search_body` setzt `body["query"]`; `earth_search_coverage._params` und `_cache_key` ebenso, `is_unfiltered` beachtet `query`. Die feste Verdrahtung auf `eo:cloud_cover` entfällt.
- Gemischte Suche: `_partition_sources` teilt `query` je Quelle wie `datetime` (eine föderierte Collection ist eine eigene Quelle); was eine Quelle nicht kennt, fällt dort weg.
- Materialisierte Datensätze (pgstac, Flächenweg) dürfen vorerst keine Filter tragen (Registry-Prüfung). Braucht ein eigener Datensatz später Filter, ist das pgstac-CQL2 bzw. SQL auf der Flächenseite: eigene Aufgabe, `adr/0005` Regel VI sagt das schon.
- Eine künftige Quelle mit CQL2 statt `query` bekommt ihre Übersetzung im Adapter; die Registry-Form bleibt gleich.

### 6.6 Queryables der Quelle

**Optionen:** (1) Registry ist die Wahrheit, ein Live-Test gleicht ab; (2) Filter zur Laufzeit aus den Queryables lesen; (3) beim Onboarding aus den Queryables vorschlagen (Harvester, M5).

**Empfehlung (1), (3) als Notiz für M5.** (2) scheidet aus, weil die Queryables unvollständig sind und weder Bereich noch Beschriftung tragen [M]. Der Live-Test (`backend/tests_live`, nicht in der CI) prüft je Datensatz und Filter: Die Quelle antwortet ohne Fehler, der Filter verengt die Trefferzahl einer festen Probe (ohne AOI im Log), und wo die Queryables die Eigenschaft nennen, passt der Typ (`number`/`integer` zu `RANGE`, `string` zu `VALUES`). Fehlt die Eigenschaft in den Queryables, ist das ein Hinweis im Testprotokoll, kein Fehler.

### 6.7 Oberfläche (englisch)

- **Ort:** Im Control-Menü nach „Acquisition date“ ein Knopf „Advanced search“ (Aufklapper ▸/▾). Er erscheint nur, wenn mindestens ein gewählter Datensatz Filter hat. Sind Filter gesetzt, steht ihre Zahl daneben („Advanced search · 1“), auch zugeklappt.
- **Inhalt:** eine Zeile je Eigenschaft über alle gewählten Datensätze (gleiche `property` = eine Zeile). Filter nicht gewählter Datensätze erscheinen nicht.
  - `RANGE`: zwei kleine Zahlenfelder „from“/„to“ mit Einheit, Platzhalter sind die Grenzen (0, 100); leer heißt „keine Grenze“. Keine neue Abhängigkeit, kein Doppelschieber.
  - `VALUES`: Häkchen je Wert; keines angehakt heißt „kein Filter“.
  - Titel mit Tooltip aus `description`.
  - Bei mehreren gewählten Datensätzen und einem Filter, den nicht alle kennen: kleiner Zusatz unter dem Titel „Only <Titel des Datensatzes>“ bzw. bei mehr als einem „Only 2 of 3 datasets“ mit den Namen im Tooltip.
  - Unten „Reset filters“ (nur sichtbar, wenn etwas gesetzt ist).
- **Eingabefehler:** „from“ > „to“, außerhalb des Bereichs oder keine ganze Zahl, wo nötig: Feld markiert, kurzer Text darunter, „Search“ gesperrt, bis es stimmt. Der Server prüft trotzdem.
- **Wirkung:** Wie das Datum: Die Suche nimmt die Filter beim nächsten „Search“; die Coverage-Karte reagiert sofort (entprellt, wie beim Datum) mit den Filtern, die ihr Datensatz kennt.
- **Hinweis in den Ergebnissen (Frage 6):** Empfohlen: kein Hinweis im Abschnitt eines Datensatzes, der den Filter nicht kennt; die Kennzeichnung steht in „Advanced search“. `sections.ts` zeigt dann für verworfene Filter-Eigenschaften nichts mehr, für `datetime` bleibt alles wie heute.
- Hell/Dunkel über die vorhandenen Farbtoken, schmales Fenster wie das übrige Control-Menü.

### 6.8 Filter als Sucheinstellung

- **Store:** `searchFilters: Record<property, {gte?, lte?} | {in: string[]}>` neben `dateFrom`/`dateTo`. Wechselt die Datensatzwahl, bleiben Werte stehen; gesendet und gezählt werden nur die, die ein gewählter Datensatz kennt (ausgeblendete Werte wirken nicht).
- **Suche:** `buildSearchBody` sendet `query`; `ctx.query` trägt sie für „Load more“; der Datums-Fallback sucht mit denselben Filtern (sonst fände er ein Datum, an dem es nur ungefiltert Treffer gibt).
- **Coverage:** `fetchCoverage` sendet die Filter, die `coverageDatasetId` kennt; der Speicher `cachedViewportCoverage`/`rememberViewportCoverage` nimmt sie in den Schlüssel; die Footprint-Suche der Coverage ebenso.
- **„Clear search results“ (NM4-17, UI-01g):** Filter bleiben, wie schon entschieden; ein neues „Search“ sucht mit ihnen. Zurücksetzen über „Reset filters“.
- **Permalink (M4-19e):** keine Änderung. Er trägt Auftrag und Ansicht; der Auftrag nennt die Szenen selbst, ein Filter ändert ihn nicht. Sucheinstellungen im Permalink wären eine eigene Aufgabe (dann mit AOI auf dem Server).
- **Merken im Browser:** nein, wie Datum und Datensatzwahl.

### 6.9 Andockpunkt für DS-03 („Clouds in AOI“)

- Präfix `earthx:` ist für Filter reserviert, die die Plattform selbst rechnet (etwa `earthx:aoi_cloud_cover`). Sie stehen nicht in `search_filters`, sondern leiten sich aus vorhandenen Registry-Daten ab (DS-03: aus `mask`, wie `earthx:mask`), damit nichts doppelt gepflegt wird.
- Das Frontend baut „Advanced search“ aus einer Liste von Beschreibungen derselben Form (`property`, Art, Bereich, Titel, Einheit, Tooltip). DS-03 hängt seine Beschreibung an diese Liste an, die Bedienung bleibt gleich.
- Die Anfrage trägt `earthx:`-Filter im selben `query`; `api` nimmt sie heraus, bevor die Quelle gefragt wird, und wendet sie nach der Vorauswahl an (DS-03 klärt Rechnung, Obergrenze und schrittweise Anzeige). DS-02 baut davon nur die Reservierung und die Ablehnung (`400` für `earthx:` bis DS-03).

### 6.10 Tests, Prüfung, Abnahme

- **Backend (CI, synthetische Registry und Fixtures):** Registry-Prüfungen (jede Regel in §6.3, auch der Widerspruch über zwei Einträge); Collection trägt `earthx:search_filters`; Anfrage an die Quelle trägt genau das erwartete `query` (`gateway_for`/`body_of` aus `tests/earthx/adapters/conftest.py`); unbekannte Eigenschaft, unbekannter Operator, falscher Typ, Bereich verletzt, `gte > lte`, leere oder unbekannte Werteliste, `earthx:`-Präfix → `400` ohne Werte im Text; Datensatz ohne Filter; zwei Datensätze, einer kennt den Filter → nur dorthin gesendet, beim anderen in `ignored_filters_by_collection`; Fingerabdruck ohne Filter unverändert (Marken alter Suchen gelten), mit Filter anders; Coverage sendet `query` an `/aggregate`, Cache-Schlüssel ändert sich; `GET` mit `query` → `400`; kein Filterwert im Log.
- **Live (lokal, `tests_live`):** Abgleich mit Quelle und Queryables (§6.6).
- **Frontend (vitest):** Knopf nur mit Filtern; Zeilen aus der Registry; Vereinigung über Datensätze und Kennzeichnung; Eingabefehler sperren „Search“; Suche, „Load more“, Fallback und Coverage senden die Filter; Coverage-Speicher trennt nach Filtern; „Clear search results“ behält sie; „Reset filters“.
- **Browser (Chromium/Playwright der Sitzung):** Klickweg Sentinel-2 + DEM gewählt, Filter setzen, Suche und Coverage beobachten (Anfragen gemockt, wo die Quelle sonst gebraucht würde), Hell/Dunkel, schmales Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und PowerShell 5.1, `Invoke-RestMethod` gegen `/stac/search` mit `query`), Log-Zeilen, vier Pflicht-Checks grün, `main` geholt.
- **Doku mit der Umsetzung:** ADR-Entwurf `adr/0020-suchfilter-je-datensatz.md` (kurz, verweist auf diesen Plan), Nachträge in `architekturplan.md` 5.1 (Zeile `earthx:search_filters`), `adr/0005` Regel VI und `adr/0011` (`FilterSupport.query`).

### 6.11 Schnitt

1. **DS-02a, Backend Suche:** `SearchFilter` und Prüfungen, `earthx:search_filters`, Einträge Sentinel-2/DEM, `FilterSupport.query`, `SearchParams.query`, Fingerabdrücke, Earth-Search-Body, Prüfung und Aufteilung in `/stac/search`, Live-Test, ADR und Nachträge. Geschätzt 300–350 Zeilen Code, dazu Tests.
2. **DS-02b, Backend Coverage:** `query` an `/coverage`, `CoverageQuery`, `/aggregate`, Cache-Schlüssel, Wegfall von `max_cloud_cover`. Geschätzt 100–150 Zeilen, dazu Tests.
3. **DS-02c, Frontend:** „Advanced search“, Store, Suche/Load more/Fallback/Coverage, Hinweise in `sections.ts`, Browserprüfung. Geschätzt 350–400 Zeilen, dazu Tests.

Je PR ein Draft-PR, Log-Zeile, Prüfanleitung, `main` holen vor „fertig“. DS-03 beginnt nach DS-02c.

### 6.12 Fragen an Otto

1. **Form des Registry-Felds:** (1) eigene Dataclass, als `earthx:search_filters` in Queryables-Wörtern veröffentlicht; (2) dazu eigene `/queryables`-Route; (3) rohes JSON Schema. **Empfehlung 1.**
2. **Filter in der eigenen Suche:** (1) `query` der STAC-Query-Extension, beschränkt auf die Registry, nur `POST`; (2) CQL2-`filter`-Teilmenge mit Übersetzung; (3) eigenes Feld. **Empfehlung 1.**
3. **`max_cloud_cover` an `/coverage`:** (1) entfällt, ersetzt durch `query` (kein Aufrufer im Frontend); (2) bleibt als zweiter Weg daneben. **Empfehlung 1.**
4. **Filter für Sentinel-2 jetzt:** (1) nur Cloud cover; (2) Cloud cover und No data; (3) zusätzlich Satellit (S2A/B/C) als Werteliste. **Empfehlung 2.**
5. **Werte-Filter (`VALUES`) jetzt bauen:** (1) ja, mit synthetischen Tests, damit DS-04 (Stufe A) nur Daten einträgt; (2) erst mit DS-04. **Empfehlung 1.**
6. **Hinweis in den Ergebnissen, wenn ein Datensatz einen Filter nicht kennt:** (1) keiner, die Kennzeichnung steht in „Advanced search“; (2) „Filter not applied: Cloud cover“ im Abschnitt, wie heute bei `datetime`. **Empfehlung 1.**
7. **Ort des Knopfs:** (1) Aufklapper im Control-Menü nach „Acquisition date“; (2) eigenes Popover; (3) eigenes Panel in der Leiste. **Empfehlung 1.**
