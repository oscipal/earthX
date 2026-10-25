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
