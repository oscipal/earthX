# M2-08 — Onboarding-Checkliste v1 als Test, Sentinel-2 vollständig: Umsetzungsplan

**Status:** **Von Otto am 22.09.2026 vollständig freigegeben.** F1, F3, F4, F5
und F6 wie empfohlen. **F2 gegen alle Vorschläge:** Punkt 10 heißt in M2 „der
Datensatz ist vom T-D-Smoke abgedeckt", das sichtbare Prüfdatum kommt mit M5
(§4.4, Fassung v1.1 von D4 im `ENTSCHEIDUNGSLOG.md`). Die Umsetzung läuft als
drei PRs (§7): **M2-08-1** (Punkte 1–8) ist umgesetzt, **M2-08-2** (Punkt 9) ist
dieser PR, **M2-08-3** (Punkt 10) folgt.
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

**Der erste Vorschlag (Dauer-PR mit `GITHUB_TOKEN`) ist gefallen.** Otto hat ihn
prüfen lassen; er trägt aus zwei voneinander unabhängigen Gründen nicht.

**Erstens, die Checks laufen nicht von selbst.** Die Sperre steht in GitHubs
eigener Dokumentation. Wörtlich, aus dem Textbaustein
`data/reusables/actions/actions-do-not-trigger-workflows.md` des Repos
`github/docs` (Zweig `main`, gelesen am 22.09.2026 — `docs.github.com` ist aus
dieser Umgebung gesperrt, die Quelldatei nicht):

> „When you use the repository's `GITHUB_TOKEN` to perform tasks, events
> triggered by the `GITHUB_TOKEN` will not create a new workflow run, with the
> following exceptions: […] `pull_request` events with the `opened`,
> `synchronize`, or `reopened` activity types: when a workflow using
> `GITHUB_TOKEN` creates or updates a pull request, the resulting `pull_request`
> event creates workflow runs in an **approval-required** state. The pull request
> displays a banner in the merge box, and a user with write access to the
> repository can start the runs by selecting **Approve workflows to run**."

Und für den reinen Push auf denselben Zweig, ohne Ausnahme:

> „For example, if a workflow run pushes code using the repository's
> `GITHUB_TOKEN`, a new workflow will not run even when the repository contains a
> workflow configured to run when `push` events occur."

Die Pflicht-Checks des geschützten `main` liefen auf so einem PR also nur, wenn
Otto sie **bei jeder Aktualisierung** von Hand freigibt — täglich. Die
Dokumentation nennt als Ausweg ausdrücklich ein GitHub-App- oder
Personal-Access-Token statt `GITHUB_TOKEN`; beides ist ein Secret und damit
ausgeschlossen.

**Zweitens, und unabhängig davon:** Otto müsste den PR laufend mergen, sonst
zeigt die Plattform ein altes Datum, das wie „geprüft" aussieht. Dieser Einwand
allein hätte gereicht.

**Was die Prüfung außerdem zutage gefördert hat.** Die Kette hat drei Glieder,
und jeder Weg entscheidet sich, welches er anfasst:

1. Actions → Repo: der Workflow hält fest, dass er grün war.
2. Repo → laufende Plattform: über einen Build, ein Deployment oder einen Abruf.
3. Plattform → Collection: die Collections liegen in **pgstac**, befüllt einmalig
   vom Dienst `catalog-load`. Ein Wert, der sich täglich ändert, wird also nicht
   schon dadurch aktuell, dass er im Repo aktuell ist — irgendwer muss ihn
   nachziehen.

Daraus folgt eine Abwägung, die keiner der Wege auflöst: **automatisch aktuell**
und **im Test überprüfbar** sind nicht dasselbe. Liegt die Datei im Repo, kann
der Checklisten-Test ihren Inhalt wirklich prüfen; wird sie zur Laufzeit geholt,
prüft der Test nur noch, dass der Mechanismus trägt.

**Ottos Entscheidung (22.09.2026): keiner der drei Wege, D4 wird enger gefasst.**
Punkt 10 heißt in M2 **„der Datensatz ist vom T-D-Smoke abgedeckt"** — die
Hälfte, die eine Aufnahmeregel ist und im Repo ohne Netz prüfbar bleibt. Jedes
Modul in `tests_live/` trägt `@pytest.mark.live_dataset("<id>")`; der
Checklisten-Test hält die Marker gegen die Registry. Mit F3 (zweiter Job) gilt
die Abdeckung für beide Datensätze.

Das **sichtbare Prüfdatum** kommt erst mit den eigenen Health-Checks in M5. Bis
dahin zeigt die Plattform gar keines — lieber keine Angabe als eine, die
altert und dabei wie eine Messung aussieht. Festgehalten als Fassung v1.1 von
Punkt 10 in `projektuebersicht.md` §5 und als Zeile im `ENTSCHEIDUNGSLOG.md`.

Daraus folgt eine Aufräumarbeit, die zu M2-08-3 gehört: `HealthInfo.last_checked_ok`
trägt heute das Datum des Onboarding-Checks und heißt trotzdem „zuletzt
erfolgreich geprüft". Das darf so nicht stehen bleiben. Zwei Wege, beide klein:

- **den Namen richtigstellen** (`onboarding_checked_at` o. ä.), oder
- **das Feld streichen** und `earthx:health` auf `status` zurücknehmen — die
  Angabe steckt bereits in `AccessInfo.token_free_checked_at` (Punkt 6), und ein
  zweites Feld mit demselben Inhalt und einem irreführenden Namen ist genau die
  Verwechslung, die Otto ausgeschlossen hat. Berührt die Gestalt von
  `earthx:health` in `architekturplan.md` 5.1, deshalb mit Nachtrag dort.

Der Vorschlag wird mit M2-08-3 vorgelegt; bis dahin ändert sich am Feld nichts.

### 4.5 Was der Viewer zeigt — und was nicht

**Nichts Neues.** Das Frontend kennt `earthx:health` heute nicht (`types.ts` führt
`earthx:access`, aber kein `health`), und nach der Entscheidung zu F2 bleibt das
in M2 so: kein „Last checked" im `ControlPanel`, keine `lastChecked.ts`, keine
Vitest-Fälle dafür. Ein Prüfdatum anzuzeigen, das keine Prüfung belegt, wäre ein
Verstoß gegen Prinzip 9 der Projektübersicht („Ehrlichkeit in der Anzeige").
Die Anzeige kommt mit M5, zusammen mit dem Wert, den sie zeigen soll.

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

**M2-08-1 — Checkliste, Punkte 1–8.** *(umgesetzt, dieser PR.)* `test_onboarding_checklist.py` mit
`evaluate`, Positiv- und Negativfällen; Punkt 3 im Eintrag geschlossen; Extents
gesetzt (je nach F5). Punkt 9 und 10 sind darin als noch nicht geprüft benannt.
*Rund 300 Zeilen.*

**M2-08-2 — Punkt 9.** `mini_cog.py`, `synthetic_asset.py`,
`test_onboarding_endtoend.py`. *Rund 320 Zeilen.*

**M2-08-3 — Punkt 10 in der Fassung v1.1.** Marker `live_dataset` in
`tests_live`, zweiter Live-Smoke-Job für die EOPF-Quelle (F3), Punkt 10 in
`evaluate` scharf gestellt als Abdeckungsprüfung, und die Aufräumarbeit an
`HealthInfo.last_checked_ok` aus §4.4. Kein Statuszweig, kein Abruf zur
Laufzeit, keine Frontend-Zeile. *Rund 200 Zeilen statt der ursprünglich
geschätzten 350.*

In einem PR wären das rund 820 Zeilen — weit über dem Richtwert von 400.

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

**Alle beantwortet am 22.09.2026.** F1, F3, F4, F5 und F6 wie empfohlen; **F2
gegen alle drei Vorschläge** — stattdessen wird D4 enger gefasst (§4.4).

**F1 — Schnitt.** ✅ *(a)* M2-08 in einem PR liegt bei rund 970 Zeilen.

a) **Drei PRs wie in §7** (Punkte 1–8 / Punkt 9 / Punkt 10). *(Empfehlung)*
b) Zwei PRs: Punkte 1–8 und 9 zusammen, Punkt 10 getrennt.
c) Einer, Richtwert deutlich überschritten.

**F2 — Wie kommt der Zeitpunkt des letzten grünen T-D-Laufs in die Plattform?**
✅ **Beantwortet am 22.09.2026: keiner der drei Wege.** D4 wird stattdessen enger
gefasst — Punkt 10 heißt in M2 „vom T-D-Smoke abgedeckt", geprüft über den
Marker in `tests_live/`; ein sichtbares Prüfdatum kommt erst mit M5 (§4.4, §4.5).
Die drei Wege bleiben als Historie stehen.

Sie kamen alle **ohne Secret** und **ohne laufende Handarbeit** aus; der
Unterschied lag darin, wie aktuell der angezeigte Wert ist und wie viel davon ein
Test prüfen kann.

a) **Statuszweig, und `catalog-load` holt die Datei.** Der Live-Smoke pusht bei
   Grün mit `GITHUB_TOKEN` (`contents: write`) auf den ungeschützten Zweig
   `live-smoke-status` — kein PR, kein Merge, keine Freigabe, und dass ein
   solcher Push keine Workflows auslöst, ist hier erwünscht. Der Dienst
   `catalog-load` liest die Datei beim Befüllen von pgstac über `gateway`, mit
   einer **eigenen, schmalen Policy** nur für `raw.githubusercontent.com`,
   getrennt von der Registry-Allowlist — die Regel „was in der Registry steht und
   sonst nichts" bleibt für den Datenpfad unangetastet. Fehlt die Datei oder ist
   sie unlesbar, zeigt der Viewer „never" statt eines falschen Datums.
   Aktualität: so frisch wie der letzte `catalog-load`-Lauf, in Compose also
   jeder Stack-Start, ab M6 ein Zeitplan. Der Test prüft die Abdeckung im Repo
   und die Verdrahtung gegen eine Fixture, nicht den Wert selbst.
   *(Empfehlung)*

b) **Statuszweig, aber kein Netz zur Laufzeit.** Derselbe Push; die Datei kommt
   nur über einen Build oder ein Deployment in die Plattform. Nichts Neues im
   `gateway`, und der Checklisten-Test prüft den eingecheckten Wert wirklich.
   Preis: in M2 gibt es kein Deployment, das sie holt — angezeigt würde bis M6
   der Stand des Checkouts, also genau das veraltete Datum, das du bei a) des
   ersten Vorschlags nicht wolltest.

c) **Der Actions-Bot darf auf `main` schreiben** (Ausnahme in der
   Branch-Schutz-Regel). Dann committet der Workflow direkt, der Wert ist im Repo
   und aktuell, und der Test prüft ihn wirklich. Preis: Rulesets können eine
   solche Ausnahme nicht auf einen Pfad begrenzen — der Bot dürfte dann alles auf
   `main` schreiben. Das ist eine Lockerung des Branch-Schutzes und deine
   Entscheidung, nicht meine.

Wenn dir keiner der drei den Aufwand wert ist, gibt es noch den Weg, die Frage zu
ändern statt sie zu beantworten: Punkt 10 zeigt weiterhin das Erreichbarkeitsdatum
des Onboardings, im Viewer als das benannt, was es ist, und der letzte grüne
T-D-Lauf kommt erst mit den eigenen Health-Checks in M5. Das wäre eine Änderung
an D4 und deshalb keine Option, die ich ohne dich wähle.

**F3 — Bekommt `sentinel-2-l2a-zarr3` einen Live-Smoke?** ✅ *(a)* Ohne einen fällt Punkt
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

**F4 — Wie tief geht Punkt 9?** ✅ *(a)* (§4.3). Kachel- und Download-Route laufen ohne
Postgres; `/stac/search` nicht, die hängt an pgstac.

a) **Suche über den Adapter, Kachel und Download über die Routen** (`TestClient`).
   Ohne Postgres, läuft überall, prüft jedes Glied im Produktivpfad. Was
   ausgelassen wird, ist die Föderationsschicht, die `test_api_federating.py`
   bereits abdeckt. *(Empfehlung)*
b) Ganz durch `/stac/search` mit pgstac, also als T-C-Integrationstest. Näher an
   „End-to-End", bindet den Punkt aber an eine laufende Datenbank.
c) Nur auf Funktionsebene, ohne Routen. Am schnellsten, am wenigsten wert.

**F5 — Extents des ersten Eintrags** ✅ *(a)* (§3). Der Eintrag trägt M1-Platzhalter; die
Quelle meldet `2015-06-27T10:25:31.456000Z` als Beginn, die Fläche ist gleich.

a) **Jetzt mitnehmen**, mit der Messung als Beleg im Kommentar. Ein Feld, zwei
   Zeilen, und die Zeitleiste kennt ihre Untergrenze. *(Empfehlung)*
b) Nicht mitnehmen — kein Punkt der Checkliste verlangt es; eigene kleine Aufgabe.

**F6 — Braucht F2 einen ADR-Entwurf?** ✅ *(a)* `CLAUDE.md` verlangt ihn für
Architekturentscheidungen.

a) **Nein, eine Zeile im `ENTSCHEIDUNGSLOG.md` genügt** — der Weg ist
   ausdrücklich ein Behelf bis M5 und berührt kein Modul und kein `earthx:`-Feld.
   *(Empfehlung; trägt für die neuen F2 b und c. Bei F2 a siehe unten.)*
b) Ja, `adr/0008`. Angemessen, falls du das neue **F2 a** wählst: dort bekommt
   `gateway` eine zweite, plattformeigene Policy neben der aus der Registry. Das
   hebt die Regel „was in der Registry steht und sonst nichts“ für einen zweiten
   Zweck auf, und das ist eine Architekturentscheidung. Ich lege den Entwurf dann
   vor dem dritten PR vor.
