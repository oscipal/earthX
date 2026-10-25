# NM4-15b — EOPF-Datensatz `sentinel-2-l2a-zarr3` entfernen

**Stand:** 25.10.2026, beauftragt von Otto (Backlog-Punkt 15; Entscheidung in `docs/adr/0017-ein-sentinel-2-datensatz.md`, §9 Fragen 1–6 je Option 1).
**Stufe A:** direkt umsetzen nach `adr/0017`, ein Draft-PR.
**Modell:** Sonnet, Effort hoch (entfernt einen Datensatz mit Belegen und Tests).
**Start:** nach dem Merge von #189 (`adr/0017` angenommen). Nicht gleichzeitig mit NM4-16 (Einheiten) und NM4-26 (Kachel-Leistung).
**Startsatz:** „Führe Aufgabe NM4-15b aus `docs/plans/querschnitt/nm4-15b-eopf-datensatz-entfernen.md` aus.“

## 1. Grundlage

`adr/0017` (angenommen 25.10.2026): Option 1 – `sentinel-2-l2a-zarr3` verlässt Registry und Katalog; der Zarr-Reader und alles Formatgenerische bleiben und werden auf dem synthetischen Mini-Zarr getestet. Was nur der EOPF-Quelle dient, geht mit. Alte Permalinks und `recipe.json` → `410` mit Grund. `load_registry` räumt die Collection in pgstac auf. Earth Search v2 ist davon unabhängig. Wiedervorlage Anfang 2027 bzw. sobald EOPF operative Zarr-Produkte meldet.

## 2. Umfang

- Registry-Eintrag, EOPF-Adapter, Coverage-Stichprobe, EOPF-Fixtures und EOPF-Live-Smoke entfernen (Liste im PR, je mit Grund).
- **Liste ausgeschiedener Datensätze** mit Lizenzblock und Zitat, damit fertige Jobs dieses Datensatzes bis zu ihrem Ablauf Attribution, Nutzungsbedingungen und `citation.bib` im ZIP behalten (`adr/0017`).
- **Annahme:** Aufträge, Permalinks (M4-19e) und „Load recipe…“ (M4-19d) mit dem alten Datensatz → `410` mit Grund (Englisch), vor jedem Abruf.
- **pgstac:** `load_registry` entfernt die Collection und ihre Items; Test, dass andere Collections unberührt bleiben. Keine Änderung an bestehenden Migrationen (Prüfsummen-Test).
- **Belege erhalten:** Der Zarr-Fall des Vergleichs Kachel ↔ Job (`test_onboarding_processing.py`, `adr/0014` §15d) und der Maskentest mit Zarr-Variable (M4-18c, `SCL_20m:scl`) ziehen auf einen synthetischen Testeintrag um. Gegenprobe: Ohne Umzug fehlt der Fall – ein Test stellt sicher, dass der Zarr-Vergleich in der CI läuft.
- **Frontend:** keine Stelle nennt den Datensatz mehr; Datensatzwahl, Fixtures, Prüfanleitungen anpassen.
- **Doku:** `adr/0007` und `adr/0014` §15d mit Verweis auf `adr/0017`; `ADDING_ESA_DATASETS.md`; Wiedervorlage-Zeile im Log; NM4-16 verliert seinen EOPF-Teil (Vermerk im Backlog).

## 3. Grenzen

- Zarr-Reader und formatgenerischer Code bleiben; nichts davon wird datensatzspezifisch.
- Keine neue Abhängigkeit. `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert – Verweise auf den Datensatz dort listet die Session im PR.

## 4. Abnahme

- Tests: `410` für Auftrag, Permalink und Rezept mit altem Datensatz; ZIP eines alten fertigen Jobs mit Attribution und Zitat; pgstac-Aufräumen; Zarr-Vergleich und Zarr-Maske auf dem Testeintrag grün.
- Suche im Repo: Der Name `sentinel-2-l2a-zarr3` kommt nur noch in der Liste ausgeschiedener Datensätze, in Tests dazu, in ADRs und im Log vor.
- Prüfanleitung für Otto (PowerShell 5.1 und Browser): Datensatzwahl ohne EOPF-Eintrag; `catalog-load` endet mit 0 auf bestehender Datenbank; alter Permalink zeigt die Meldung.
- Alle vier Pflicht-Checks grün; Log-Zeile; Backlog-Punkt 15 als erledigt.
- Vor „fertig“ ist main geholt.

## 5. Stand der Umsetzung (25.10.2026)

Umgesetzt in einem Draft-PR ([#195](https://github.com/oscipal/earthX/pull/195)). Die Liste der entfernten Dateien mit Grund und die Verweise auf `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` stehen in der PR-Beschreibung.

### Prüfanleitung für Otto (Windows PowerShell 5.1 und Browser)

Voraussetzung: der Stack läuft (`docker compose up`), der Branch ist ausgecheckt und neu gebaut (`docker compose up --build`).

**A. Datensatzwahl ohne EOPF-Eintrag.**

```powershell
$c = Invoke-RestMethod http://localhost:8000/stac/collections
$c.collections | ForEach-Object { $_.id }
#   (sentinel-2-c1-l2a und cop-dem-glo-30, sonst nichts)
```

Im Browser `http://localhost:5173`: Die Datensatzwahl der Suchkachel zeigt nur „Sentinel-2 L2A“ und „Copernicus DEM GLO-30“.

**B. `catalog-load` endet mit 0 auf der bestehenden Datenbank.**

```powershell
docker compose run --rm catalog-load
$LASTEXITCODE
#   (0; beim ersten Lauf "collections removed: sentinel-2-l2a-zarr3", beim zweiten "collections removed: none")
```

**C. Die alte ID wird mit Grund abgewiesen (410).**

```powershell
try {
  Invoke-WebRequest "http://localhost:8000/processing/processes/recipe?dataset=sentinel-2-l2a-zarr3" -UseBasicParsing
} catch { $_.Exception.Response.StatusCode.value__; (New-Object IO.StreamReader($_.Exception.Response.GetResponseStream())).ReadToEnd() }
#   (410 und ein Problem-Dokument mit "dataset 'sentinel-2-l2a-zarr3' was retired on 2026-10-25: …; use 'sentinel-2-c1-l2a' instead")
try { Invoke-WebRequest http://localhost:8000/stac/collections/sentinel-2-l2a-zarr3 -UseBasicParsing } catch { $_.Exception.Response.StatusCode.value__ }
#   (404, wie jede unbekannte Collection)
```

**D. Alter Permalink im Browser.** Ein Permalink, der vor dem Umbau mit dem alten Datensatz gespeichert wurde (`?permalink=<id>` an die Adresse des Viewers), öffnet sich als Link weiter (`GET /processing/permalinks/<id>` antwortet `200`); die Oberfläche fragt den Datensatz beim Server nach und zeigt die Fehlerzeile „Dataset retired: dataset 'sentinel-2-l2a-zarr3' was retired on 2026-10-25: …“. Es wird nichts verändert. Ein neuer Permalink für den alten Datensatz lässt sich nicht anlegen (`410`). Fehlt ein alter Permalink, entfällt Schritt D; die Tests `test_a_stored_link_still_opens_because_the_order_is_the_users` (Backend) und `says a dataset that left the catalog has been retired …` (Frontend) belegen das Verhalten.
