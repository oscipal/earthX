# M2-08 — Onboarding-Checkliste v1 als Test, Sentinel-2 vollständig: Umsetzungsplan

**Status:** Plan, Stufe B laut `projektplan.md` 1.2. **Wartet auf Ottos Freigabe**
(§11). Es ist noch nichts umgesetzt.
**Ort im Repo:** `docs/plans/m2-08-onboarding-checkliste.md`
**Aufgabe:** M2-08 aus `docs/plans/m2-format-und-viewer.md`.
**Grundlage:** `projektuebersicht.md` §5 (die zehn Punkte, Fassung v1 nach D4);
`KLAERUNGEN.md` B10 (Capability-Flags vollständig), B11 (Lizenzstufen), B12
(Punkt 10), B13 (Registry als Dataclass); `adr/0002` §2 T-D und der Nachtrag vom
20.09.2026 (Live-Smoke nur in Actions, `curl` statt Sitzungslauf); `adr/0003`
§10.1, §11.2 (Erreichbarkeit, Lizenz); `adr/0004` §5 (Anbieter-Begriff,
Vollständigkeitsprobe); `adr/0006` §5 (Standard-Visualisierung);
`architekturplan.md` 3.1 (Modulgrenzen) und 5.1 (die `earthx:`-Felder).
**Voraussetzungen:** erfüllt. M2-05b (Coverage-Route), M2-06 (Zuschnitt-Download),
M2-07d (Download im Frontend) sind laut `ENTSCHEIDUNGSLOG.md` am 22.09.2026
umgesetzt. M2-10 ist **nicht** vorausgesetzt, wirkt aber auf F3.

---

## 1. Ziel in einem Satz

Die zehn Punkte der Onboarding-Checkliste sind ein Test, der über **alle**
Registry-Einträge läuft, `sentinel-2-c1-l2a` besteht ihn vollständig, und ein
Eintrag, dem ein Punkt fehlt, lässt ihn fallen.

---

## 2. Ausgangslage: die zehn Punkte gegen den Code gehalten

Gelesen wurden `catalog/registry.py`, `catalog/datasets.py`, `catalog/collection.py`,
`catalog/coverage.py`, `tests/catalog/*`, `tests_live/*` und beide Workflows.

| # | Punkt | woher prüfbar | `sentinel-2-c1-l2a` | `sentinel-2-l2a-zarr3` |
|---|---|---|---|---|
| 1 | Beschreibung | `DatasetConfig.description` | ✅ | ✅ |
| 2 | Coverage-Anbieter zugeordnet, Vollständigkeitsprobe greift | `CoverageInfo.provider`, `coverage.check_completeness` | ✅ `UPSTREAM_AGGREGATION` | ✅ `SAMPLE` |
| 3 | DOI, sonst persistente Zitierangabe | `DatasetConfig.doi` / `.citation` | ❌ **beide `None`** | ✅ DOI |
| 4 | Lizenz geprüft, Flags gesetzt | `LicenseInfo` | ✅ | ✅ |
| 5 | Cloud-natives Format | `DataFormat` | ✅ `COG` | ✅ `ZARR` |
| 6 | Anonymer Zugriffs-Check bestanden | `AccessInfo.token_free_checked_at` | ✅ 2026-09-18 | ✅ 2026-09-22 |
| 7 | Datentyp-Klasse und Capability-Flags | `DataClass`, `Capabilities` | ✅ | ✅ |
| 8 | Standard-Visualisierung | `DefaultRender` | ✅ | ✅ |
| 9 | End-to-End: Suche → Anzeige → Zuschnitt-Download | — | ❌ **gibt es nicht** | ❌ |
| 10 | „Zuletzt erfolgreich geprüft" gesetzt und sichtbar | `HealthInfo.last_checked_ok` | ⚠️ **falscher Wert** | ⚠️ |

Drei Befunde tragen den Rest dieses Plans:

**(a) Punkt 3 fällt heute für den ersten Datensatz.** Der Eintrag sagt das selbst
(`datasets.py` Z. 59–62: „Onboarding checklist point 3 is open"). §3 löst das mit
einer Messung an der Quelle.

**(b) Punkt 9 existiert nirgends.** Es gibt Tests für jedes Glied der Kette
(`test_earth_search.py`, `test_tiler.py`, `test_download_route.py`), aber keinen,
der sie als Kette je Datensatz durchläuft. Für den COG-Pfad fehlt außerdem die
Grundlage: es gibt ein synthetisches Mini-Zarr (`tests/earthx/readers/mini_zarr.py`),
aber **kein synthetisches Mini-COG** — die COG-Tests fälschen den Lesevorgang.

**(c) Punkt 10 hat ein Feld, aber den falschen Inhalt.** `HealthInfo.last_checked_ok`
steht in beiden Einträgen fest verdrahtet auf dem **Erreichbarkeitsdatum des
Onboardings** (`_REACHABILITY_CHECKED`, `_EOPF_CHECKED`) — also auf demselben Wert
wie Punkt 6, nicht auf dem letzten grünen T-D-Lauf. Im Frontend ist das Feld
zudem gar nicht bekannt: `types.ts` kennt `earthx:access`, aber kein
`earthx:health`. „Gesetzt **und sichtbar**" ist damit an beiden Enden offen.

Der Live-Smoke (`.github/workflows/live-smoke.yml`) läuft täglich um 05:17 UTC mit
`permissions: contents: read`, einem Job, und beprobt ausschließlich
`SENTINEL_2_L2A`. Er schreibt nichts zurück; sein Ergebnis lebt allein als
Rot/Grün in der Actions-Oberfläche.

---

## 3. Was in dieser Sitzung an der Quelle nachgesehen wurde

Über `curl` gegen `https://earth-search.aws.element84.com/v1/collections/sentinel-2-c1-l2a`
am 22.09.2026, `200`. Der Weg über `gateway` steht einer Cloud-Sitzung nicht offen
(`adr/0002` §2, Nachtrag M2-13) — deshalb `curl`, wie bei M2-07c und M2-14.

**Die Collection führt einen `cite-as`-Link.** Genau die Naht, aus der der zweite
Datensatz seinen DOI hat:

```
rel="cite-as"  https://doi.org/10.5270/S2_-742ikth
               "Copernicus Sentinel-2 MSI Level-2A (L2A) Bottom-of-Atmosphere Radiance"
```

Das ist ein **anderer** DOI als der des Zarr-Eintrags (`S2_-znk9xsj`), und das ist
richtig so: die beiden Links benennen zwei Produktvarianten, nicht zweimal dasselbe.
`adr/0003` hat den Link nicht gesehen, weil M1 nichts aus der Quelle gelesen hat.
Punkt 3 ist damit keine offene Frage mehr, sondern ein einzutragender Wert.

**Die Extents sind ebenfalls ablesbar** und weichen von den M1-Platzhaltern ab:

| | im Eintrag (Platzhalter M1) | an der Quelle, 22.09.2026 |
|---|---|---|
| `spatial.bbox` | `(-180, -90, 180, 90)` | `[-180, -90, 180, 90]` — gleich |
| `temporal.interval` | `(None, None)` | `["2015-06-27T10:25:31.456000Z", null]` |

Der Kommentar im Eintrag sagt „M2 replaces both extents with the ones the upstream
collection reports" (`datasets.py` Z. 65–68). Kein Punkt der Checkliste verlangt
das, aber „Sentinel-2 vollständig" ist die Überschrift dieser Aufgabe, und der
Zeitraum ist das, woran die Zeitleiste ihre Grenzen setzt — siehe F5.

Die Lizenz-URL der Quelle (`sentinel.esa.int/…`) ist der Alias, den `adr/0003`
bereits kennt; der kanonische Link im Eintrag bleibt unangetastet.

---

## 4. Aufbau

### 4.1 Die Prüfung ist Testcode, kein Produktivcode

Die Checkliste ist eine **Aufnahmeregel des Projekts**, keine Laufzeiteigenschaft
der Plattform: kein Endpunkt, kein `earthx:`-Feld, keine Route liefert sie aus.
Sie gehört deshalb nach `backend/tests/catalog/test_onboarding_checklist.py` und
nicht nach `earthx/catalog/`. Das hält `architekturplan.md` 5.1 unverändert und
erspart ein Feld, das niemand liest.

Aufbau im Testmodul:

```python
@dataclass(frozen=True)
class Finding:
    point: int
    rule: str          # der Wortlaut aus projektuebersicht.md §5
    detail: str

def evaluate(config: DatasetConfig, smoke: Mapping[str, LiveSmokeRun]) -> list[Finding]
```

`evaluate` prüft die Punkte 1–8 und 10 (Punkt 9 ist eine eigene Kette, §4.3) und
gibt je fehlendem Punkt einen `Finding` zurück. Darauf setzen zwei Testarten:

- **positiv,** über `pytest.mark.parametrize` aus `REGISTRY` — jeder Eintrag,
  automatisch auch der dritte, den es noch nicht gibt;
- **negativ,** je Punkt einer, aufgebaut mit dem vorhandenen `vary()`-Muster aus
  `tests/catalog/conftest.py`: ein Fall ändert genau eine Sache und erwartet genau
  diesen `Finding`. Das ist die Abnahmebedingung „ein Eintrag mit fehlendem Punkt
  lässt ihn fallen", neunfach belegt statt einmal behauptet.

Was `evaluate` **nicht** nachprüft, ist was `DatasetConfig.__post_init__` schon
erzwingt (Lizenz identifizierbar, Tier-Anforderungen, `asset_hosts`-Form). Die
Checkliste liegt eine Schicht darüber und prüft, was die Dataclass zulässt, die
Aufnahmeregel aber nicht: `doi`/`citation` beide leer, `default_render=None`,
`viewer=None`, Format `LEGACY`, fehlender Smoke-Eintrag.

Punkt 2 heißt seit D4 „Anbieter zugeordnet **und** Vollständigkeitsprobe greift".
Der Anbieter ist ein Pflichtfeld; das zweite Stück wird als Aufruf von
`coverage.check_completeness` über eine Antwortform geprüft, die zum Anbieter des
Eintrags passt — `UPSTREAM_AGGREGATION` muss `COMPLETE`/`TRUNCATED` erreichen
können, `SAMPLE` muss `SAMPLE` liefern. Damit ist der Punkt eine Prüfung und
nicht das Ablesen eines Enums.

### 4.2 Punkt 3 und die Extents: der erste Eintrag wird vollständig

`SENTINEL_2_L2A` bekommt `doi="https://doi.org/10.5270/S2_-742ikth"` mit dem
Kommentar, woher er stammt (der `cite-as`-Link der Collection, gemessen am
22.09.2026) — wortgleich zum Muster des Zarr-Eintrags, damit beide Einträge
denselben Beleg führen. `citation` bleibt `None`: der DOI ist die persistente
Angabe, die Punkt 3 verlangt.

Die Extents werden auf die gemessenen Werte gesetzt (F5).

### 4.3 Punkt 9: die Kette gegen synthetische Daten

Ein Test je Registry-Eintrag, der **Suche → Kachel → Zuschnitt-Download** durch
den Produktivpfad schickt, ohne Netz:

1. **Suche.** `adapters.search_items` mit dem Adapter des Eintrags, gegen ein
   `httpx.MockTransport` im `Gateway` (das eingeführte Muster aus
   `tests/earthx/adapters/conftest.py`). Die Antwort ist ein synthetisches
   STAC-Item, dessen `properties` genau die Schlüssel aus
   `config.viewer.group_by` tragen und dessen Asset auf die synthetischen Daten
   aus Schritt 2 zeigt. Geprüft wird zusätzlich, dass `catalog.group_key` auf dem
   Item einen Schlüssel bildet — Punkt 9 und D19 hängen zusammen.
2. **Anzeige.** Die Kachelroute per `TestClient`, `app.state.earthx_item_source`
   auf das Item aus Schritt 1 gesetzt, wie `test_tiler.py` es tut. Gelesen werden
   **echte Bytes**: für `ZARR` das vorhandene `mini_zarr` über
   `serve_store`, für `COG` ein neues **`tests/earthx/readers/mini_cog.py`**, das
   mit `rio_cogeo` (steht bereits in `requirements.txt`) ein kleines COG mit
   Overviews auf `tmp_path` schreibt. Kein zweites Fake — sonst beweist Punkt 9
   nur, dass der Fake funktioniert.
3. **Zuschnitt-Download.** Die Download-Route mit einer AOI innerhalb der
   synthetischen Ausdehnung; geprüft wird, dass ein ZIP mit Raster **und**
   Hinweisdatei herauskommt und die Hinweisdatei Attribution und `terms_notice`
   des Eintrags trägt (M2-06, M2-15).

Die Formatabhängigkeit steckt in **einem** Helfer,
`tests/earthx/readers/synthetic_asset.py`, der nach `config.format` entscheidet.
Ein neuer Datensatz in einem der beiden Formate bekommt Punkt 9 dadurch
geschenkt; ein drittes Format fällt sichtbar mit „kein synthetisches Asset für
`<format>`" — das ist die richtige Meldung, kein stilles Überspringen.

Zur Tiefe der Kette siehe F4: `/stac/search` selbst hängt an pgstac, die beiden
anderen Routen nicht.

### 4.4 Punkt 10: wie der Zeitpunkt in die Plattform kommt

Die Aufgabe verlangt ausdrücklich einen Vorschlag: **ohne Secret** und **ohne
dass die Cloud-Sitzung live zugreift**. Gemessen an der Lage:

- `main` ist geschützt (über die GitHub-API geprüft, `protected: true`). Ein
  Direkt-Push aus einem Workflow scheitert daran, und Branch-Schutz zu lockern
  ist ohne Otto ausgeschlossen (`CLAUDE.md`).
- `GITHUB_TOKEN` ist kein selbstverwaltetes Secret; es entsteht je Lauf. Eine
  `permissions:`-Zeile im Live-Smoke-Workflow genügt.
- Die Sitzung selbst muss nichts abrufen: der Test liest eine Datei.

**Vorgeschlagener Weg (F2 a).** Der Live-Smoke schreibt sein Ergebnis in eine
kleine Datei und hält damit **einen einzigen, dauerhaften Chore-PR** gegen `main`
aktuell.

- **Wer weiß, welcher Datensatz beprobt wurde?** Die Live-Tests selbst. Jedes
  Modul in `tests_live/` bekommt `@pytest.mark.live_dataset("<id>")` (in
  `pyproject.toml` registriert, `--strict-markers` ist an). Ein Hook in
  `tests_live/conftest.py` sammelt die Datensätze der **bestandenen** Tests und
  schreibt am Sitzungsende **nur bei fehlerfreiem Lauf** die Datei.
- **Was steht drin?** `backend/earthx/catalog/live_smoke_status.json`, ein
  Eintrag je `dataset_id`: `checked_at` (UTC, ISO 8601), `run_url`. Nichts
  weiter — keine Messwerte, keine Hostnamen, keine AOIs.
- **Wie kommt sie ins Repo?** Ein Schritt nach `pytest` (ohne `if: always()`,
  also nur bei Grün) committet die Datei auf den festen Zweig
  `chore/live-smoke-status` und öffnet dort einen PR, falls keiner offen ist.
  `permissions: contents: write, pull-requests: write` nur in diesem Workflow;
  `ci.yml` bleibt bei `contents: read`.
- **Wie liest die Plattform sie?** Neues Modul `catalog/live_smoke.py`:
  `load_live_smoke_status(path=None) -> Mapping[str, LiveSmokeRun]`, Vorgabepfad
  neben dem Modul, fehlende Datei ergibt eine leere Zuordnung (kein Absturz),
  kaputtes JSON einen definierten Fehler. `to_stac_collection` nimmt die
  Zuordnung als zweites, vorgabefreies Argument und **überschreibt** damit
  `earthx:health.last_checked_ok`. Kein neues `earthx:`-Feld, 5.1 bleibt wie es
  ist. `catalog` liest eine lokale Datei — keine neue Importkante.

Der Eintrag behält sein eigenes `HealthInfo` als das, was es ist: der Befund des
Onboardings. Die Kommentare an beiden Einträgen werden entsprechend
richtiggestellt, damit nicht länger dort steht, das sei Punkt 10.

**Ehrlich benannter Preis:** angezeigt wird der letzte grüne Lauf, den ein
gemergter Stand kennt — nicht der letzte grüne Lauf überhaupt. Der offene PR
zeigt den jeweils aktuellen Wert. Eine Alterungsregel („älter als N Tage heißt
`degraded`") wird **nicht** erfunden; das ist eine Messung und gehört zu den
eigenen Health-Checks in M5, die diesen ganzen Behelf ablösen (D4: „Fassung v1").
F2 stellt die beiden teureren Wege daneben.

### 4.5 Sichtbar im Viewer

`types.ts` bekommt `EarthxHealth { status; last_checked_ok }` und das Feld
`'earthx:health'` an `Collection`. Unter der Datensatzauswahl im `ControlPanel`
steht eine Zeile „Last checked <Datum>", bei fehlendem Wert „Last checked —
never". Die Formatierung liegt in `frontend/src/lastChecked.ts` als reine
Funktion mit Vitest-Fällen (Datum, `null`, unlesbarer Wert) — Oberflächentests
gibt es weiterhin nicht (F2 aus dem M2-Plan). Alle Texte englisch (D25).

---

## 5. Tests

| Was | Wo | Art |
|---|---|---|
| Punkte 1–8, 10 je Registry-Eintrag | `tests/catalog/test_onboarding_checklist.py` | T-A |
| Je Punkt ein Negativfall über `vary()` | ebenda | T-A |
| Punkt 9 als Kette je Eintrag | `tests/catalog/test_onboarding_endtoend.py` | T-A (F4 a) |
| Mini-COG: Overviews vorhanden, lesbar, definierte Ausdehnung | `tests/earthx/readers/test_mini_cog.py` | T-A |
| `load_live_smoke_status`: fehlende Datei, kaputtes JSON, unbekannte ID, fehlende Pflichtfelder | `tests/catalog/test_live_smoke_status.py` | T-A |
| `to_stac_collection` überschreibt `last_checked_ok`, lässt es ohne Eintrag stehen | `tests/catalog/test_collection.py` (erweitert) | T-A |
| Marker-Hook schreibt nichts bei rotem Lauf | `tests/test_live_smoke_writer.py` | T-A |
| `lastChecked.ts` | `frontend/src/lastChecked.test.ts` | Vitest |

Zweckfremde Nutzung, die ausdrücklich geprüft wird: eine Statusdatei mit einem
Datensatz, den die Registry nicht kennt; ein `checked_at` in der Zukunft; ein
Eintrag mit `format=LEGACY` (Punkt 5 fällt); ein Eintrag, dessen Coverage-Anbieter
zur Antwortform nicht passt (Punkt 2 fällt). `tests_live` selbst läuft in der
Sitzung nicht und wird nicht angefasst außer um den Marker.

---

## 6. Was nicht angefasst wird

- `earthx:`-Felder in `architekturplan.md` 5.1 — es kommt keines dazu.
- Die Erreichbarkeitsdaten (`token_free_checked_at`) beider Einträge; Punkt 6
  ist erfüllt und wird nur gelesen.
- `ci.yml` (bleibt `contents: read`), `CODEOWNERS`, Branch-Schutz.
- Der Coverage-Pfad, der Kachelpfad, der Download — Punkt 9 ruft sie auf, ändert
  sie nicht.
- Eine Alterungsregel für `earthx:health.status` (M5).
- Das Entfernen des Prototyps (M2-11) und die Anzeige von `earthx:maturity`
  (M2-10) — die „Last checked"-Zeile ist so gebaut, dass die Statusmarke daneben
  passt.

---

## 7. Reihenfolge der Umsetzung

Empfohlener Schnitt in drei PRs (F1), jeder für sich grün und abnehmbar:

**M2-08-1 — Checkliste, Punkte 1–8.** `test_onboarding_checklist.py` mit
`evaluate`, Positiv- und Negativfällen; Punkt 3 im Eintrag geschlossen; Extents
gesetzt (je nach F5). Punkt 9 und 10 sind darin als noch nicht geprüft benannt.
*Rund 300 Zeilen.*

**M2-08-2 — Punkt 9.** `mini_cog.py`, `synthetic_asset.py`,
`test_onboarding_endtoend.py`. *Rund 320 Zeilen.*

**M2-08-3 — Punkt 10.** Marker und Hook in `tests_live`, Workflow-Schritt,
`catalog/live_smoke.py`, `to_stac_collection`, Frontend-Zeile, Punkt 10 in
`evaluate` scharf gestellt, Zeile im `ENTSCHEIDUNGSLOG.md`. *Rund 350 Zeilen.*

In einem PR wären das rund 970 Zeilen — weit über dem Richtwert von 400.

---

## 8. Risiken

1. **Der Chore-PR bleibt liegen.** Dann altert der angezeigte Wert still. Gegenmittel:
   der PR-Titel trägt das Datum, und die Zeile im Viewer zeigt das Datum selbst,
   nicht „geprüft ✓". F2 b/c vermeiden das Risiko gegen höheren Preis.
2. **Der zweite Datensatz hat keinen Live-Smoke** (F3). Ohne Antwort fällt Punkt
   10 für `sentinel-2-l2a-zarr3` — und M2-10 verlangt die Checkliste grün für
   **beide**.
3. **`rio_cogeo` erzeugt ein COG, das der Produktivpfad anders liest als ein
   echtes Sentinel-2-Asset.** Gegenmittel: das Mini-COG trägt Overviews, eine
   CRS und eine Nodata-Angabe, und der Test liest es über dieselbe Route wie ein
   echtes. Es bleibt eine Nachbildung — was sie nicht abdeckt, deckt der
   Live-Smoke ab.
4. **„Bestandene Tests je Datensatz" ist im Hook leicht zu weit gefasst.** Ein
   übersprungener Test darf nicht als bestanden zählen. Der Hook zählt allein
   `passed` und schreibt gar nichts, sobald ein `failed` oder `error` vorliegt.

---

## 9. Abnahme (nach der Freigabe)

- `ruff check backend`, `pytest`, `lint-imports --config .importlinter` grün;
  im Frontend `npm run lint`, `npx tsc -b`, `npm test` grün.
- Der Checklisten-Test ist grün für `sentinel-2-c1-l2a`, und je Punkt zeigt ein
  Negativfall, dass ein fehlender Punkt den Eintrag fallen lässt.
- Die „Last checked"-Zeile ist lokal mit `docker compose up` und `npm run dev`
  sichtbar; die Anleitung steht im PR.

---

## 10. Abnahme dieses Plans

Otto beantwortet §11. Danach wird in der Reihenfolge aus §7 umgesetzt. Bis dahin
wird kein Produktivcode angefasst.

---

## 11. Fragen an Otto

**F1 — Schnitt.** M2-08 in einem PR liegt bei rund 970 Zeilen.

a) **Drei PRs wie in §7** (Punkte 1–8 / Punkt 9 / Punkt 10). *(Empfehlung)*
b) Zwei PRs: Punkte 1–8 und 9 zusammen, Punkt 10 getrennt.
c) Einer, Richtwert deutlich überschritten.

**F2 — Wie kommt der Zeitpunkt des letzten grünen T-D-Laufs in die Plattform?**
(§4.4). `main` ist geschützt, ein Direkt-Push aus dem Workflow scheidet damit aus.

a) **Statusdatei im Repo, vom Live-Smoke über einen dauerhaften Chore-PR
   aktuell gehalten.** Kein Secret, kein Laufzeit-Zugriff nach außen, keine neue
   Importkante, keine Änderung am Branch-Schutz. Preis: angezeigt wird der letzte
   **gemergte** grüne Lauf. *(Empfehlung — M5 löst den Behelf ohnehin ab, D4
   nennt ihn „Fassung v1")*
b) Die Plattform liest den Wert zur Laufzeit über `gateway` von einer
   öffentlichen URL (Statuszweig oder Actions-API). Der ehrlichste Wert, aber:
   ein plattformeigener Host in der Allowlist, die `policy_from_registry` heute
   nicht kennt (D12), plus Cache und Rückfall — eine Architekturänderung für ein
   Anzeigefeld.
c) Der Workflow committet auf einen ungeschützten Statuszweig, das Deployment
   holt die Datei (M6). Kein Merge-Zwang, aber in M2 ist kein Deployment da, das
   sie holen könnte — der angezeigte Wert bliebe bis M6 der eingecheckte.

**F3 — Bekommt `sentinel-2-l2a-zarr3` einen Live-Smoke?** Ohne einen fällt Punkt
10 für ihn, und M2-10 verlangt die Checkliste grün für beide. Du hattest zu
M2-09b F7 entschieden, die Quelle **nicht** zur Abnahmegrundlage zu machen; hier
geht es um die laufende Überwachung, nicht um die Abnahme.

a) **Zweiter Job in `live-smoke.yml`** für die EOPF-Quelle, nach dem Muster des
   ersten (zwei Metadaten-Anfragen). Ein roter Lauf färbt keinen PR rot, er lässt
   das Datum stehenbleiben — genau das, was ein „staging"-Status sichtbar machen
   soll. *(Empfehlung)*
b) Kein Live-Smoke; Punkt 10 für diesen Eintrag bis M2-10 als `xfail` mit
   Begründung geführt.
c) Punkt 10 gilt nur für Einträge mit `maturity = stable`. Sauber begründbar,
   verschiebt aber eine Aufnahmeregel wegen eines Werkzeugproblems.

**F4 — Wie tief geht Punkt 9?** (§4.3). Kachel- und Download-Route laufen ohne
Postgres; `/stac/search` nicht, die hängt an pgstac.

a) **Suche über den Adapter, Kachel und Download über die Routen** (`TestClient`).
   Ohne Postgres, läuft überall, prüft jedes Glied im Produktivpfad. Was
   ausgelassen wird, ist die Föderationsschicht, die `test_api_federating.py`
   bereits abdeckt. *(Empfehlung)*
b) Ganz durch `/stac/search` mit pgstac, also als T-C-Integrationstest. Näher an
   „End-to-End", bindet den Punkt aber an eine laufende Datenbank.
c) Nur auf Funktionsebene, ohne Routen. Am schnellsten, am wenigsten wert.

**F5 — Extents des ersten Eintrags** (§3). Der Eintrag trägt M1-Platzhalter; die
Quelle meldet `2015-06-27T10:25:31.456000Z` als Beginn, die Fläche ist gleich.

a) **Jetzt mitnehmen**, mit der Messung als Beleg im Kommentar. Ein Feld, zwei
   Zeilen, und die Zeitleiste kennt ihre Untergrenze. *(Empfehlung)*
b) Nicht mitnehmen — kein Punkt der Checkliste verlangt es; eigene kleine Aufgabe.

**F6 — Braucht F2 einen ADR-Entwurf?** `CLAUDE.md` verlangt ihn für
Architekturentscheidungen.

a) **Nein, eine Zeile im `ENTSCHEIDUNGSLOG.md` genügt** — der Weg ist
   ausdrücklich ein Behelf bis M5 und berührt kein Modul und kein `earthx:`-Feld.
   *(Empfehlung, gilt für F2 a und c)*
b) Ja, `adr/0008`. Angemessen, falls du F2 b wählst: dort kommt ein
   plattformeigener Host in die Allowlist, und das ist eine Architekturentscheidung.
