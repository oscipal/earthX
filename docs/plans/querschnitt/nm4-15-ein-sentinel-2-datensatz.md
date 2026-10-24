# NM4-15 — Nur ein Sentinel-2-L2A-Datensatz sichtbar (Entscheidungsvorlage)

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 15 in `docs/plans/nach-m4-backlog.md`).
**Stufe C:** nur Entscheidungsvorlage als ADR-Entwurf unter `docs/adr/`, kein Produktivcode. Die Umsetzung bekommt nach Ottos Entscheidung eine eigene Aufgabe.
**Modell:** Opus, Effort hoch.
**Start:** sofort möglich (nur Doku).
**Startsatz:** „Führe Aufgabe NM4-15 aus `docs/plans/querschnitt/nm4-15-ein-sentinel-2-datensatz.md` aus.“

## 1. Anlass

Heute gibt es `sentinel-2-c1-l2a` (Earth Search, COG) und `sentinel-2-l2a-zarr3` (EOPF, Zarr). Otto will nicht mehrere Datensätze anbieten, die dasselbe zeigen, und den Zarr-Datensatz loswerden. Am Zarr-Datensatz hängen Belege und Entscheidungen: `adr/0007` (zweites Format), Zarr-Vergleich in `adr/0014` §15d (M4-Abnahme Kriterium 1), Tests, Fixtures, Prüfanleitungen, `SCL_20m:scl` (M4-18c).

## 2. Soll

- Ein ADR-Entwurf mit Optionen, Empfehlung und Folgen; Otto entscheidet.

## 3. Umfang

- Optionen mindestens: (1) EOPF-Datensatz entfernen, Zarr-Reader bleibt generisch mit synthetischen Tests; (2) ein sichtbarer Eintrag „Sentinel-2 L2A“ mit zwei Quellen dahinter (primär und Rückfall, `adr/0005`); (3) Earth Search entfernen, EOPF behalten.
- **Recherche mit Quellen (Pflicht):** Betriebsstatus des EOPF-Zarr-Dienstes, Zeitplan von Earth Search v2 (Backlog „Earth Search v2“), Abdeckung, Aktualität, Skalierung (Zarr-Item ohne `raster:scale`), Bandnamen, Prüfsummen (`adr/0014` §3.1).
- Folgen je Option: Registry, Fixtures, Tests, Prüfanleitungen, Doku; bestehende Permalinks und `recipe.json` mit dem alten Datensatz (abweisen mit Grund oder umleiten); M4-Belege bleiben als Stand von M4 gültig.

## 4. Grenzen

- Kein Produktivcode.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- ADR-Entwurf im PR mit Quellen, Fragen an Otto nummeriert mit Empfehlung.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.
