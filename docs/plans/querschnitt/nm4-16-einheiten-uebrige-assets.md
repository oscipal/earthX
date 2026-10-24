# NM4-16 — Einheiten für die übrigen Sentinel-2-Assets

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 16 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort mittel.
**Start:** sofort möglich (Backend/Registry).
**Startsatz:** „Führe Aufgabe NM4-16 aus `docs/plans/querschnitt/nm4-16-einheiten-uebrige-assets.md` aus.“

## 1. Anlass

Seit M4-19b nennt die Registry Einheiten je Asset (`earthx:band_units`). `aot`, `wvp`, `cloud`, `snow` und `preview` haben keine, weil die Session keine Quelle dafür gelesen hat.

## 2. Soll

- Einheiten mit Quelle (Produktspezifikation Sentinel-2 L2A, Item-Metadaten) nachtragen; wo keine Einheit sinnvoll ist (etwa `preview`), das bewusst vermerken.
- Einheit „1“ wird im Frontend nirgends angezeigt; im Layer-Manager stehen nie Einheiten (Otto, 24.10.2026).

## 3. Umfang

- Quelle je Asset im PR zitieren; gilt auch für den EOPF-Datensatz, solange es ihn gibt (NM4-15).

## 4. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Test: Collection nennt die neuen Einheiten; Hinweis im PR: Die Änderung ändert den Hash (`adr/0014` §15n), also einmal kein Cache-Treffer.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.
